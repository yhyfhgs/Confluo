"""pipeline 端到端集成（进程内，全部经 `PipelineRunner`，不经 CLI）。

覆盖：pull 级联全绿 / 幂等重跑全 skipped / force 重跑的 handler 级幂等跳过 /
dry-run 零副作用与 AC-1.2 口径 / Selector（volume+issue、filter、limit、dois）/
--extract / 单阶段执行 / 启动崩溃恢复与 tmp 清理。
Refs: FR-05, FR-09, FR-10, D-004, AC-1.1, AC-1.2。

环境构建器 `make_env` 同时被 `test_pipeline_errors.py` 复用（`tests/` 无顶层包，
按 tests/helpers 先例以 `integration.test_pipeline_e2e` 顶层包名导入）。
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
import yaml

from paper_crawler.adapter import load_adapters
from paper_crawler.config import Config
from paper_crawler.obslog import setup_logging
from paper_crawler.pipeline import PipelineRunner, Selector, StageContext, validate_pdf_magic
from paper_crawler.ratelimit import RateLimiter
from paper_crawler.registry import VenueRegistry
from paper_crawler.storage.db import Database
from paper_crawler.storage.repo import Repo
from paper_crawler.tasks import TaskQueue

VENUE = "mock_journal"

DEFAULT_QUIRKS: dict[str, object] = {
    "volumes": 3,
    "issues_per_volume": 2,
    "papers_per_issue": 5,
    "seed": 42,
}


@dataclass
class PipelineEnv:
    """一套隔离的 pipeline 运行环境（home + venues 目录 + 打开的 DB）。"""

    config: Config
    venues_dir: Path
    db: Database
    repo: Repo
    queue: TaskQueue
    sleeps: list[float]

    def write_venue(
        self, quirks: dict[str, object], *, rate_limit_rpm: float | None = None
    ) -> None:
        """写/改 mock venue YAML（测试经改 quirks 注入/解除故障，模拟人工修复）。"""
        doc: dict[str, object] = {
            "id": VENUE,
            "kind": "journal",
            "names": {"full": "Mock Journal", "aliases": ["MJ"]},
            "field": ["cs_ai"],
            "tier": "T1",
            "identifiers": {"issn": ["0000-0000"]},
            "metadata_source": "mock_platform",
            "fulltext_source": "mock_platform",
            "auth": {"level": "none"},
            "quirks": quirks,
            "status": "active",
        }
        if rate_limit_rpm is not None:
            doc["rate_limit"] = {"requests_per_minute": rate_limit_rpm}
        (self.venues_dir / "mock-journal.yaml").write_text(
            yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8"
        )

    def make_runner(self, *, dry_run: bool = False) -> PipelineRunner:
        """新建 runner（重载 registry 与 limiter）——模拟"每条 CLI 命令一个新进程"。"""
        registry = VenueRegistry(load_adapters())
        assert registry.load_dirs(list(self.config.venues_dirs)) == []
        ctx = StageContext(
            config=self.config,
            db=self.db,
            repo=self.repo,
            registry=registry,
            queue=self.queue,
            limiter=RateLimiter(scale=self.config.rate_scale),
            sleeper=self.sleeps.append,  # 假 sleeper：只记录、不真睡
            dry_run=dry_run,
        )
        return PipelineRunner(ctx)

    def close(self) -> None:
        self.db.close()


def make_env(
    tmp_path: Path,
    *,
    quirks: dict[str, object] | None = None,
    retry_scale: float = 1.0,
) -> PipelineEnv:
    home = tmp_path / "home"
    venues_dir = tmp_path / "venues"
    venues_dir.mkdir(parents=True, exist_ok=True)
    config = Config(
        home=home,
        data_dir=home / "data",
        db_path=home / "catalog.sqlite",
        log_dir=home / "logs",
        reports_dir=home / "reports",
        venues_dirs=(venues_dir,),
        rate_scale=1.0,
        retry_scale=retry_scale,
    )
    setup_logging(config.log_dir, console_level="CRITICAL")
    db = Database(config.db_path)
    db.migrate()
    env = PipelineEnv(
        config=config,
        venues_dir=venues_dir,
        db=db,
        repo=Repo(db),
        queue=TaskQueue(db),
        sleeps=[],
    )
    env.write_venue(dict(quirks if quirks is not None else DEFAULT_QUIRKS))
    return env


@pytest.fixture
def env(tmp_path: Path) -> Iterator[PipelineEnv]:
    e = make_env(tmp_path)
    yield e
    e.close()


# -- 共享断言小件 -------------------------------------------------------------


def pdf_files(env: PipelineEnv) -> list[Path]:
    pdf_root = env.config.data_dir / "pdf"
    return sorted(pdf_root.rglob("*.pdf")) if pdf_root.is_dir() else []


def data_files(env: PipelineEnv) -> list[Path]:
    if not env.config.data_dir.is_dir():
        return []
    return [p for p in env.config.data_dir.rglob("*") if p.is_file()]


def success_fetch_logs(env: PipelineEnv) -> list[sqlite3.Row]:
    return [r for r in env.repo.fetch_logs() if r["error_class"] is None]


def log_text(env: PipelineEnv) -> str:
    return "".join(p.read_text(encoding="utf-8") for p in env.config.log_dir.glob("*.jsonl"))


# -- e2e：级联全绿 + 幂等重跑（AC-1.1 / AC-1.3 判据）--------------------------


def test_pull_year_end_to_end(env: PipelineEnv) -> None:
    """Closes: AC-1.1（mock venue 端到端 pull 产出文件+DB 一致）。"""
    report = env.make_runner().pull(VENUE, Selector(year=2024))

    assert report.succeeded == 10
    assert report.failed == 0
    assert report.blocked == 0
    # planned_* 仅 dry-run 填充（T7b 渲染契约）
    assert report.planned_downloads == 0 and report.planned_bytes == 0

    assert env.repo.counts(VENUE) == {
        "issues": 2,
        "papers": 10,
        "assets_planned": 10,
        "assets_fetched": 10,
    }

    files = pdf_files(env)
    assert len(files) == 10
    expected_dir = env.config.data_dir / "pdf" / VENUE / "2024"
    assert all(f.parent == expected_dir for f in files)  # design/06 §4 布局
    assert all(validate_pdf_magic(f) for f in files)
    assert len(success_fetch_logs(env)) == 10

    # 级联溯源：全部子任务 parent_id → pull 任务
    pulls = env.db.query("SELECT id FROM task WHERE kind = 'pull'")
    assert len(pulls) == 1
    children = env.db.query("SELECT kind, parent_id FROM task WHERE kind != 'pull'")
    assert children and all(r["parent_id"] == pulls[0]["id"] for r in children)

    # ingest 尾部推进 paper 状态；报告落盘
    states = {r["ingest_state"] for r in env.repo.list_papers(VENUE)}
    assert states == {"fetched"}
    assert any("ingest[" in note for note in report.notes)
    assert (env.config.reports_dir / "last-run.md").is_file()
    assert (env.config.reports_dir / "history.jsonl").is_file()


def test_pull_rerun_is_all_skipped(env: PipelineEnv) -> None:
    """重跑同命令 → 全 skipped、无新成功 fetch_log（AC-1.3 判据）。"""
    env.make_runner().pull(VENUE, Selector(year=2024))
    before_logs = len(success_fetch_logs(env))

    report = env.make_runner().pull(VENUE, Selector(year=2024))

    assert report.succeeded == 0 and report.failed == 0 and report.blocked == 0
    # 1 discover + 2 enumerate + 10 resolve + 10 fetch 全部 fresh_skip
    assert report.skipped == 23
    assert len(success_fetch_logs(env)) == before_logs
    assert len(pdf_files(env)) == 10
    assert env.repo.counts(VENUE)["assets_fetched"] == 10
    assert '"msg": "skipped"' in log_text(env)  # 日志记 skipped（§5.3）


def test_force_rerun_hits_handler_level_skip(env: PipelineEnv) -> None:
    """--force 绕过入队新鲜度 → fetch handler 级幂等跳过（§5.3：文件在且 sha256 合，
    不产生新的成功 fetch_log 行）。"""
    env.make_runner().pull(VENUE, Selector(year=2024))

    report = env.make_runner().pull(VENUE, Selector(year=2024), force=True)

    assert report.succeeded == 0
    assert report.skipped == 10  # 仅 10 个 fetch 的 handler 级跳过（其余阶段真实重跑）
    assert len(success_fetch_logs(env)) == 10
    assert env.repo.counts(VENUE)["assets_fetched"] == 10


def test_force_rerun_refetches_missing_file(env: PipelineEnv) -> None:
    """文件缺失 → 幂等跳过判据不成立 → force 重跑补下（对账修复路径）。"""
    env.make_runner().pull(VENUE, Selector(year=2024))
    victim = pdf_files(env)[0]
    victim.unlink()

    report = env.make_runner().pull(VENUE, Selector(year=2024), force=True)

    assert report.succeeded == 1
    assert report.skipped == 9
    assert len(pdf_files(env)) == 10
    assert len(success_fetch_logs(env)) == 11


# -- dry-run（AC-1.2）---------------------------------------------------------


def test_dry_run_zero_side_effects_then_real_run_matches(env: PipelineEnv) -> None:
    """Closes: AC-1.2（dry-run 与实跑清单一致且零下载副作用）。"""
    dry = env.make_runner(dry_run=True).pull(VENUE, Selector(year=2024))

    assert dry.planned_downloads == 10
    assert dry.planned_bytes == 0  # mock 的 resolve 不带内容长度（stages docstring 契约）
    assert dry.succeeded == 0
    assert any("dry-run" in note for note in dry.notes)

    assert data_files(env) == []  # data/ 零写入
    assert env.repo.list_assets(state="fetched") == []  # DB 无 fetched
    assert env.db.query("SELECT id FROM task WHERE kind = 'fetch'") == []  # 不建 fetch 任务
    assert env.repo.counts(VENUE)["assets_planned"] == 10  # resolve 已落库（级联到 resolve）

    real = env.make_runner().pull(VENUE, Selector(year=2024))
    assert real.succeeded == dry.planned_downloads == 10  # AC-1.2 口径
    assert real.planned_downloads == 0


# -- Selector ----------------------------------------------------------------


def test_selector_volume_issue(env: PipelineEnv) -> None:
    report = env.make_runner().pull(VENUE, Selector(volume="1", issue="1"))
    assert report.succeeded == 5
    assert env.repo.counts(VENUE) == {
        "issues": 1,
        "papers": 5,
        "assets_planned": 5,
        "assets_fetched": 5,
    }


def test_selector_filter_title_substring_case_insensitive(env: PipelineEnv) -> None:
    """filter_expr = 标题大小写不敏感子串；enumerate 全量落库、resolve/fetch 圈定命中。"""
    report = env.make_runner().pull(VENUE, Selector(year=2024, filter_expr="PAPER 1.1.0"))
    counts = env.repo.counts(VENUE)
    assert counts["papers"] == 10  # 清单仍全量
    assert counts["assets_planned"] == 1  # 仅命中者进入 resolve
    assert counts["assets_fetched"] == 1
    assert report.succeeded == 1


def test_selector_limit_is_forward_to_resolve(env: PipelineEnv) -> None:
    """limit 前置到 resolve 圈选（缺陷 C-C）：10 篇中只 resolve 前 3 篇，而非全量后截断。

    深度覆盖（--limit 前置的确定性/对账语义）在 test_ac_pull_usability.py；此处守 e2e
    的计数口径：assets_planned 随 limit 收缩（曾为"resolve 不受 limit 影响 → 10"）。
    """
    report = env.make_runner().pull(VENUE, Selector(year=2024, limit=3))
    counts = env.repo.counts(VENUE)
    assert counts["papers"] == 10  # enumerate 仍全量落库
    assert counts["assets_planned"] == 3  # 只前 3 篇 resolve（前置，非全量 resolve 后截断）
    assert counts["assets_fetched"] == 3
    assert report.succeeded == 3


def test_selector_dois(env: PipelineEnv) -> None:
    dois = (
        f"10.9999/{VENUE}.1.1.0",
        f"10.9999/{VENUE}.1.2.3".upper(),  # DOI 比较大小写不敏感
    )
    report = env.make_runner().pull(VENUE, Selector(year=2024, dois=dois))
    assert report.succeeded == 2
    assert env.repo.counts(VENUE)["assets_fetched"] == 2


def test_selector_no_match_is_clean_noop(env: PipelineEnv) -> None:
    report = env.make_runner().pull(VENUE, Selector(volume="9"))
    assert report.succeeded == 0 and report.failed == 0 and report.blocked == 0
    assert env.repo.counts(VENUE)["issues"] == 0
    assert any("ingest[" in note for note in report.notes)  # ingest 尾部仍跑


# -- extract -----------------------------------------------------------------


def test_pull_with_extract(env: PipelineEnv) -> None:
    """`pull --extract` 全链（Phase 7 真实抽取，D-033）。

    mock adapter 的载荷是**确定性占位字节**（`%PDF-1.4` 头 + 填充 + `%%EOF`），不是结构合法
    的 PDF——真实抽取下它恰好命中 §6.1 **第 2 类**（源文件在、但抽不出）：任务**不 FAILED**、
    落 `state='extract_failed'` + `note='corrupt'` 行、`ingest_state` 停在 `fetched`（失败不进
    单调阶梯，§6.2）。本用例因此同时是「长尾抽不出不飘红」的端到端锁；快乐路径（真实可抽
    PDF → .txt 落盘 + 行字段对账）见 `test_extract_stage.py`。
    """
    report = env.make_runner().pull(VENUE, Selector(year=2024), with_extract=True)
    assert report.succeeded == 10  # succeeded 口径 = fetch 下载数（extract 不计入）
    assert report.failed == 0 and report.blocked == 0  # 第 2 类失败不使任务 FAILED

    rows = env.db.query("SELECT * FROM fulltext ORDER BY paper_id")
    assert len(rows) == 10
    assert all(
        r["extractor"] == "pypdf" and r["state"] == "extract_failed" and r["note"] == "corrupt"
        for r in rows
    )
    assert all(r["text_path"] is None and r["char_count"] == 0 for r in rows)
    assert all(r["asset_id"] and r["source_sha256"] for r in rows)  # asset 级幂等键已落库
    states = {r["ingest_state"] for r in env.repo.list_papers(VENUE)}
    assert states == {"fetched"}
    assert list((env.config.data_dir / "fulltext").rglob("*")) == []  # 失败不落产物文件

    # 幂等：重跑不重插 fulltext（extract 任务 fresh_skip）
    rerun = env.make_runner().pull(VENUE, Selector(year=2024), with_extract=True)
    assert len(env.db.query("SELECT paper_id FROM fulltext")) == 10
    assert rerun.skipped == 33  # 23 + 10 个 extract fresh_skip


# -- 单阶段执行 / drain -------------------------------------------------------


def test_run_single_stage_discover_full_timeline(env: PipelineEnv) -> None:
    """无范围参数的 discover = 全量时间轴（`crawler timeline` 语义）。"""
    runner = env.make_runner()
    report = runner.run_single_stage("discover", VENUE, {})
    assert report.failed == 0
    assert env.repo.counts(VENUE)["issues"] == 6  # 3 卷 x 2 期

    again = runner.run_single_stage("discover", VENUE, {})
    assert again.skipped == 1  # 24h 新鲜度内 fresh_skip


def test_unknown_venue_pull_raises_config(env: PipelineEnv) -> None:
    from paper_crawler.errors import CrawlerError, ErrorClass

    runner = env.make_runner()
    with pytest.raises(CrawlerError) as exc_info:
        runner.pull("no_such_venue", Selector())
    assert exc_info.value.error_class is ErrorClass.CONFIG
    assert env.db.query("SELECT id FROM task") == []  # 未产生任何任务


def test_drain_empty_queue(env: PipelineEnv) -> None:
    report = env.make_runner().drain()
    assert report.succeeded == 0 and report.failed == 0
    assert report.skipped == 0 and report.blocked == 0
    assert report.finished_at != ""


# -- 启动语义：tmp 清理与崩溃恢复 ---------------------------------------------


def test_startup_cleans_stale_part_files(env: PipelineEnv) -> None:
    tmp_dir = env.config.data_dir / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    stale = tmp_dir / "orphan.part"
    stale.write_bytes(b"partial")

    env.make_runner()  # __init__ 即启动清理（design/05 §5.2）
    assert not stale.exists()


def test_startup_recovers_running_zombie_tasks(env: PipelineEnv) -> None:
    """kill-9 残留的 RUNNING 任务在下次启动归还 PENDING（AC-1.3 重跑前提）。"""
    result = env.queue.enqueue("discover", VENUE, {})
    claimed = env.queue.claim_next()
    assert claimed is not None and claimed["id"] == result.task_id
    # 模拟进程在此被 kill-9：任务停在 RUNNING

    runner = env.make_runner()
    row = env.queue.get(str(result.task_id))
    assert row is not None and row["state"] == "PENDING"

    report = runner.drain()  # 恢复后的任务可被正常执行完
    assert report.failed == 0
    row = env.queue.get(str(result.task_id))
    assert row is not None and row["state"] == "DONE"
