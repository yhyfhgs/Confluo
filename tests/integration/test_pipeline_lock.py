"""pipeline 进程级互斥锁（独立审查 P1-6 / 修复批 R3d）。

被修复的缺陷：`PipelineRunner.__init__` 无条件 `cleanup_tmp()`（删 tmp 下全部 `*.part`）
+ `queue.recover_running()`（全库 RUNNING→PENDING，无进程范围）。`.part` 文件名恒为
`{asset_id}.part`，故 cron `watch` 与交互式 `pull` 重叠时，后启动的进程会删掉前者正在
写的 part、抢走前者已 claim 的 RUNNING 任务——落盘字节与 DB `sha256` 可以不符，且只有
事后 `verify` 才看得见。修复是一把 `fcntl.flock` 排他锁（先例：
`adapters/openalex/budget.py::_locked`）：`<config-home>/state/.pipeline.lock`——落在
`state/`（既有运行态目录，同 cooldown/budget）而非 `data/`，因为 AC-1.2 有一条
"dry-run 后 data/ 零写入"的可执行判据，见 `pipeline_lock_path` docstring。

本文件的断言按锁的**语义边界**组织，而非按实现细节：

1. 锁被别人持有时，第二实例**响亮失败**（`CrawlerError(CONFIG)` + 含锁路径的消息），
   不等待、不静默降级；
2. 且失败**发生在破坏之前**——陈旧 `.part` 未被删、RUNNING 任务未被抢（这条才是
   "锁覆盖了 cleanup_tmp + recover_running"的行为证据）；
3. 一次 drain **会话进行中**第二实例同样被拒（覆盖面不止 `__init__`）；
4. 会话结束即释放——**同进程内先后两个实例**（且前一个仍被引用）必须都能跑，否则
   `typer.testing.CliRunner` 一类"异常回溯持有旧帧"的场景会把锁泄漏到整个进程寿命；
5. 崩溃自动释放：持锁进程被 SIGKILL 后无需任何陈旧锁文件清理，下一实例即可获取
   （`flock` 随 fd 关闭由内核回收——`budget.py` 同款理由）。

真 `flock`、真子进程，零 mock：同一进程内两个独立 `open()` 得到两个 file description，
`flock` 视其为互相冲突（POSIX/BSD 语义，macOS 实测 `BlockingIOError(EAGAIN)`），因此
"第二实例"既可以是真子进程（用例 5/6），也可以是同进程内的第二个 `PipelineRunner`
（用例 1-4）——两者走的是同一条内核路径。
"""

from __future__ import annotations

import contextlib
import fcntl
import subprocess
import sys
import textwrap
from collections.abc import Iterator
from io import TextIOWrapper
from pathlib import Path

import pytest

from integration.test_pipeline_e2e import VENUE, PipelineEnv, make_env
from paper_crawler.errors import CrawlerError, ErrorClass
from paper_crawler.pipeline.runner import PipelineRunner, pipeline_lock_path


@pytest.fixture
def env(tmp_path: Path) -> Iterator[PipelineEnv]:
    e = make_env(tmp_path)
    yield e
    e.close()


@contextlib.contextmanager
def _foreign_holder(lock_path: Path) -> Iterator[TextIOWrapper]:
    """以"另一个进程"的身份持有真 flock（同进程独立 fd，内核语义等价）。"""
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(lock_path, "a", encoding="utf-8")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield handle
    finally:
        handle.close()


def _stale_part(env: PipelineEnv) -> Path:
    """模拟"另一进程正在写的下载临时文件"。"""
    tmp_dir = env.config.data_dir / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    part = tmp_dir / "01JZZZ-inflight.part"
    part.write_bytes(b"bytes in flight")
    return part


# -- 1/2：第二实例响亮失败，且失败在破坏之前 ---------------------------------


def test_second_instance_fails_loudly_while_lock_held(env: PipelineEnv) -> None:
    lock = pipeline_lock_path(env.config.home)
    with _foreign_holder(lock), pytest.raises(CrawlerError) as exc_info:
        env.make_runner()

    assert exc_info.value.error_class is ErrorClass.CONFIG
    message = str(exc_info.value)
    assert "另一 pipeline 实例正在运行" in message
    assert str(lock) in message  # 消息里给出锁路径（用户可据此定位对手进程）


def test_startup_cleanup_and_recover_are_covered_by_the_lock(env: PipelineEnv) -> None:
    """P1-6 的两个破坏面在锁内：拿不到锁就既不删 `.part`、也不抢 RUNNING。"""
    part = _stale_part(env)
    result = env.queue.enqueue("discover", VENUE, {})
    claimed = env.queue.claim_next()  # 模拟"对手进程已 claim、正在执行"
    assert claimed is not None

    with _foreign_holder(pipeline_lock_path(env.config.home)), pytest.raises(CrawlerError):
        env.make_runner()

    assert part.exists(), "拿不到锁的实例删掉了别人正在写的 .part"
    row = env.queue.get(str(result.task_id))
    assert row is not None and row["state"] == "RUNNING", "拿不到锁的实例抢走了别人的 RUNNING 任务"


# -- 3：drain 会话进行中同样互斥 ---------------------------------------------


def test_second_instance_blocked_during_drain_session(
    env: PipelineEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    """锁的覆盖面不止 `__init__`：整个 drain 会话期间第二实例都进不来。"""
    seen: list[CrawlerError] = []
    original = PipelineRunner._drain_loop

    def spy(self: PipelineRunner, report: object) -> None:
        with pytest.raises(CrawlerError) as exc_info:
            env.make_runner()  # 会话中途闯入的第二实例
        seen.append(exc_info.value)
        original(self, report)  # type: ignore[arg-type]

    monkeypatch.setattr(PipelineRunner, "_drain_loop", spy)
    env.make_runner().drain()

    assert len(seen) == 1
    assert seen[0].error_class is ErrorClass.CONFIG
    assert "另一 pipeline 实例正在运行" in str(seen[0])


# -- 4：会话结束即释放（不把锁泄漏到进程寿命）--------------------------------


def test_lock_is_released_at_session_end_even_if_runner_stays_referenced(
    env: PipelineEnv,
) -> None:
    """前一个 runner **仍被引用**时，下一个实例照样能建能跑。

    真实触发场景：`typer.testing.CliRunner` 把 `SystemExit` 连同 `__context__` 的回溯
    一起存进 `Result`，命令函数那一帧（连同其中的 `runner` 局部）因此活到测试结束——
    若锁的释放依赖对象被回收，一次测试里的第二条 CLI 命令就会被自己上一条挡住。

    会话取 discover 单阶段（不碰 merge/ingest）：本文件测的是锁，不该被别的阶段的
    状态牵连。
    """
    runner_a = env.make_runner()
    report_a = runner_a.run_single_stage("discover", VENUE, {})
    assert report_a.failed == 0
    assert env.repo.counts(VENUE)["issues"] > 0

    runner_b = env.make_runner()  # runner_a 仍在作用域内（且刚跑完一次会话）
    report_b = runner_b.run_single_stage("discover", VENUE, {})
    assert report_b.failed == 0
    assert report_b.finished_at != ""

    # 第三次：runner_a 再跑一次会话——同一实例的锁可以反复取放，不自锁死
    assert runner_a.drain().failed == 0


# -- 5/6：真跨进程 + 崩溃自动释放 --------------------------------------------


_HOLDER_SCRIPT = """
import fcntl, sys
handle = open({path!r}, "a")
fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
print("locked", flush=True)
sys.stdin.readline()
"""


def test_real_second_process_blocks_runner_and_sigkill_releases(env: PipelineEnv) -> None:
    """真子进程持锁 → runner 拒启动；子进程被 SIGKILL 后无需清陈旧锁文件即可恢复。"""
    lock = pipeline_lock_path(env.config.home)
    lock.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(
        [sys.executable, "-c", textwrap.dedent(_HOLDER_SCRIPT.format(path=str(lock)))],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert proc.stdout is not None
        assert proc.stdout.readline().strip() == "locked"

        with pytest.raises(CrawlerError) as exc_info:
            env.make_runner()
        assert exc_info.value.error_class is ErrorClass.CONFIG

        proc.kill()  # SIGKILL：模拟崩溃——内核回收 flock，锁文件本身留在原地
        proc.wait(timeout=10)

        assert lock.exists()  # 陈旧锁文件不需要（也不应该）被清理
        report = env.make_runner().drain()  # 崩溃后下一实例直接可用
        assert report.failed == 0
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=10)
