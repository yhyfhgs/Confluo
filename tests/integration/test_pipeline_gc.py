"""会话收尾的 task 表 GC 接线（R3d 整合任务：`TaskQueue.gc_done` 的唯一调用点）。

`gc_done`（R3c 交付）删的是"超出保留窗的 DONE 行"——task 表此前全仓零 `DELETE`，
DONE 行随运行单调累积。本文件锁定的是**接线语义**（GC 本身的行为由 R3c 的
`tests/unit/test_tasks.py` 覆盖，此处不重复）：

1. **会话收尾才 GC**：`_finalize` 里、`report.save()` **之后**——五个公开入口一律在
   `finally` 调 `_finalize`，故单点接线即全覆盖（异常路径也照跑）；
2. **构造实例不 GC**：`__init__` 的启动块**不**含 GC——`crawler list`/`timeline` 这类
   只读用途构造出的 runner 不该顺手删别人的历史行；
3. **GC 在进程锁内**：`_finalize` 整个在 `_exclusive()` 会话锁里，故两个进程的
   `gc_done` 不会交错（R3c 的 SELECT→DELETE 之间没有别人插得进来）；
4. **GC 失败不改变任何既有语义**：吞成 WARNING 日志，报告已落盘、drain 结果不变、
   原异常（若有）照常传播。
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from integration.test_pipeline_e2e import VENUE, PipelineEnv, log_text, make_env
from paper_crawler.errors import CrawlerError
from paper_crawler.pipeline.runner import PipelineRunner
from paper_crawler.tasks import GC_DONE_RETENTION_DAYS, TaskQueue


@pytest.fixture
def env(tmp_path: Path) -> Iterator[PipelineEnv]:
    e = make_env(tmp_path)
    yield e
    e.close()


def _done_task(env: PipelineEnv, *, age_days: float) -> str:
    """造一条 DONE 任务行并把 `updated_at` 拨老 `age_days` 天，返回 task_id。"""
    result = env.queue.enqueue("discover", VENUE, {"marker": str(age_days)})
    claimed = env.queue.claim_next()
    assert claimed is not None
    task_id = str(result.task_id)
    env.queue.complete(task_id)
    aged = (datetime.now(UTC) - timedelta(days=age_days)).isoformat()
    env.db.execute("UPDATE task SET updated_at = ? WHERE id = ?", (aged, task_id))
    return task_id


def _exists(env: PipelineEnv, task_id: str) -> bool:
    return env.queue.get(task_id) is not None


# -- 1：会话收尾回收超窗 DONE 行 ---------------------------------------------


def test_session_end_collects_stale_done_rows(env: PipelineEnv) -> None:
    stale = _done_task(env, age_days=GC_DONE_RETENTION_DAYS + 1)
    fresh = _done_task(env, age_days=0)
    assert _exists(env, stale) and _exists(env, fresh)

    report = env.make_runner().drain()

    assert report.failed == 0
    assert not _exists(env, stale), "会话收尾未回收超出保留窗的 DONE 行"
    assert _exists(env, fresh), "保留窗内的 DONE 行被误删（接线不该改 gc_done 的窗口语义）"


def test_every_entry_gcs_because_finalize_is_the_single_call_site(env: PipelineEnv) -> None:
    """五入口共用 `_finalize` → 任一入口的会话收尾都会 GC（此处以 run_single_stage 取样）。"""
    stale = _done_task(env, age_days=GC_DONE_RETENTION_DAYS + 1)

    env.make_runner().run_single_stage("discover", VENUE, {})

    assert not _exists(env, stale)


# -- 2：构造实例不 GC（只读命令不该删历史）------------------------------------


def test_constructing_a_runner_does_not_collect(env: PipelineEnv) -> None:
    stale = _done_task(env, age_days=GC_DONE_RETENTION_DAYS + 1)

    env.make_runner()  # 只构造，不跑任何会话

    assert _exists(env, stale), "GC 跑进了 __init__ 的启动块（只读用途的构造会误删历史行）"


# -- 3：GC 发生在进程锁内 -----------------------------------------------------


def test_gc_runs_inside_the_process_lock(env: PipelineEnv, monkeypatch: pytest.MonkeyPatch) -> None:
    """`_finalize` 在 `_exclusive()` 内 → GC 执行的那一刻锁仍被本会话持有。

    证法：在 `gc_done` 里试着建第二个实例——拿不到锁即抛（R3d 的互斥语义），
    正说明 GC 跑在锁的保护之下（R3c 的 SELECT→DELETE 不会与另一进程交错）。
    """
    seen: list[CrawlerError] = []
    original = TaskQueue.gc_done

    def spy(self: TaskQueue, *args: object, **kwargs: object) -> int:
        with pytest.raises(CrawlerError) as exc_info:
            env.make_runner()
        seen.append(exc_info.value)
        return int(original(self, *args, **kwargs))  # type: ignore[arg-type]

    monkeypatch.setattr(TaskQueue, "gc_done", spy)
    stale = _done_task(env, age_days=GC_DONE_RETENTION_DAYS + 1)

    env.make_runner().drain()

    assert len(seen) == 1
    assert "另一 pipeline 实例正在运行" in str(seen[0])
    assert not _exists(env, stale)  # 锁内照常完成回收


# -- 4：GC 失败不影响 drain 结果与报告落盘 -------------------------------------


def test_gc_failure_is_swallowed_and_leaves_run_intact(
    env: PipelineEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(self: TaskQueue, *args: object, **kwargs: object) -> int:
        raise RuntimeError("gc exploded")

    monkeypatch.setattr(TaskQueue, "gc_done", boom)
    env.queue.enqueue("discover", VENUE, {})

    report = env.make_runner().drain()  # 不得抛

    assert report.failed == 0
    assert report.finished_at != ""
    assert (env.config.reports_dir / "last-run.md").is_file(), "GC 失败挡住了报告落盘"
    assert "gc exploded" in log_text(env)  # 响亮记一条 WARNING，不静默


def test_gc_failure_does_not_mask_the_original_exception(
    env: PipelineEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    """会话本身出错时，`finally` 里的 GC 故障不得盖掉原异常（P1-5 的同一条纪律）。"""

    def boom(self: TaskQueue, *args: object, **kwargs: object) -> int:
        raise RuntimeError("gc exploded")

    def session_blows_up(self: PipelineRunner, report: object) -> None:
        raise RuntimeError("drain exploded")

    monkeypatch.setattr(TaskQueue, "gc_done", boom)
    monkeypatch.setattr(PipelineRunner, "_drain_loop", session_blows_up)

    with pytest.raises(RuntimeError) as exc_info:
        env.make_runner().drain()

    assert str(exc_info.value) == "drain exploded"  # 不是 "gc exploded"
    assert (env.config.reports_dir / "last-run.md").is_file()  # 报告仍落了盘
