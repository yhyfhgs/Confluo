"""错误分类路由集成（design/05 §4；进程内经 `PipelineRunner`，mock 故障注入驱动）。

覆盖：AUTH_EXPIRED 整批 BLOCKED + resume 后 re-resolve 生效（AC-1.5）/
CHALLENGE、CONFIG 单点 BLOCKED / fail_enumerate → FAILED(parse) / GONE 标 asset
不重试 / NO_ENTITLEMENT 标 asset + FAILED / TRANSIENT 耗尽预算 attempts==4 与
退避序列 × retry_scale / INTEGRITY 重下 1 次 / RATE_LIMITED 循环保护升级 /
非 CrawlerError → TRANSIENT 处置 / blocked 报告计数。
Refs: FR-09, FR-10, D-004, AC-1.5。

环境构建器复用 test_pipeline_e2e 的 `make_env`（tests/ 无顶层包，按 helpers
先例以 `integration.` 顶层包名导入）。
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Iterator
from pathlib import Path

import pytest

from integration.test_pipeline_e2e import (
    DEFAULT_QUIRKS,
    VENUE,
    PipelineEnv,
    make_env,
    pdf_files,
)
from paper_crawler.adapters.mock_platform import MockPlatformAdapter
from paper_crawler.errors import ErrorClass
from paper_crawler.pipeline import PartFileIO, Selector
from paper_crawler.pipeline.stages import fetched_file_ok
from paper_crawler.types import FetchResult, IssueRef, VenueSpec


@pytest.fixture
def env(tmp_path: Path) -> Iterator[PipelineEnv]:
    e = make_env(tmp_path)
    yield e
    e.close()


def quirks_with(**extra: object) -> dict[str, object]:
    quirks = dict(DEFAULT_QUIRKS)
    quirks.update(extra)
    return quirks


def fail_fetch(error_class: str, indexes: list[int]) -> dict[str, object]:
    return quirks_with(fail_fetch={"error_class": error_class, "paper_indexes": indexes})


def fetch_tasks(env: PipelineEnv, state: str | None = None) -> list[sqlite3.Row]:
    if state is None:
        return env.db.query("SELECT * FROM task WHERE kind = 'fetch' ORDER BY created_at, id")
    return env.db.query(
        "SELECT * FROM task WHERE kind = 'fetch' AND state = ? ORDER BY created_at, id", (state,)
    )


def failure_fetch_logs(env: PipelineEnv, error_class: str) -> list[sqlite3.Row]:
    return [r for r in env.repo.fetch_logs() if r["error_class"] == error_class]


def asset_urls(env: PipelineEnv) -> list[str]:
    return [str(r["url"]) for r in env.repo.list_assets(venue_id=VENUE)]


def backoff_sleeps(env: PipelineEnv) -> list[float]:
    """过滤掉限速小等待（<0.9s），留下重试退避序列（mock rpm=600/burst=10 下限速
    欠账等待恒 <1s，而最小退避 2.0×retry_scale≥1.0）。"""
    return [s for s in env.sleeps if s >= 0.9]


# -- AUTH_EXPIRED：整批 BLOCKED + resume 后 re-resolve 生效（AC-1.5）-----------


def test_auth_expired_blocks_batch_then_resume_refetches(env: PipelineEnv) -> None:
    """Closes: AC-1.5（BLOCKED→改配置→resume→重跑全部完成；验证 fetch 前 re-resolve）。"""
    env.write_venue(fail_fetch("auth_expired", [0, 1]))
    report = env.make_runner().pull(VENUE, Selector(volume="1", issue="1"))

    # 首个 fetch 触发 auth_expired → BLOCKED；同 venue 同批其余 4 个连带 BLOCKED
    assert report.blocked == 5
    assert report.blocked > 0  # blocked 时报告计数>0（任务书测试 6）
    assert report.succeeded == 0 and report.failed == 0
    blocked = fetch_tasks(env, state="BLOCKED")
    assert len(blocked) == 5
    assert all(r["attempts"] == 0 for r in blocked)  # block 不占重试次数（§2）
    reasons = [str(r["blocked_reason"]) for r in blocked]
    assert sum("同批连带" in r for r in reasons) == 4
    trigger = [r for r in reasons if "同批连带" not in r]
    assert len(trigger) == 1
    assert "auth_expired" in trigger[0] and "resume --all" in trigger[0]  # 人工动作提示

    # 只有触发者真正执行过：失败 fetch_log 恰 1 行；资产全部停在 planned
    assert len(failure_fetch_logs(env, "auth_expired")) == 1
    assert env.repo.counts(VENUE)["assets_fetched"] == 0
    # 注入编译在 url 查询串（T6 机制）：中毒 url 已入库
    assert sum("fail=auth_expired" in u for u in asset_urls(env)) == 2

    # 人工修复：改 YAML 移除注入 → resume --all（queue.resume 语义）→ 重跑 pull
    env.write_venue(dict(DEFAULT_QUIRKS))
    assert env.queue.resume(all_blocked=True) == 5

    rerun = env.make_runner().pull(VENUE, Selector(volume="1", issue="1"))

    assert rerun.succeeded == 5
    assert rerun.failed == 0 and rerun.blocked == 0
    assert env.repo.counts(VENUE)["assets_fetched"] == 5
    assert len(pdf_files(env)) == 5
    # re-resolve 生效证据：resolve 任务因永久新鲜 fresh_skip（未重跑），中毒 url 却已被
    # fetch 前的现场 re-resolve + refresh_asset_plan 换成干净 url——否则必再次 BLOCKED
    assert rerun.skipped == 12  # discover 1 + enumerate 1 + resolve 5 + fetch(已 DONE) 5
    assert all("fail=" not in u for u in asset_urls(env))
    assert all(r["attempts"] == 0 for r in fetch_tasks(env))  # 全程未消耗重试预算


def test_auth_expired_dois_batch_of_two(env: PipelineEnv) -> None:
    """计划文本口径：批=2 个 fetch 时，1 触发 + 1 连带 → 恰 2 个 BLOCKED（attempts==0）。"""
    env.write_venue(fail_fetch("auth_expired", [0, 1]))
    dois = (f"10.9999/{VENUE}.1.1.0", f"10.9999/{VENUE}.1.1.1")
    report = env.make_runner().pull(VENUE, Selector(volume="1", issue="1", dois=dois))

    assert report.blocked == 2
    blocked = fetch_tasks(env, state="BLOCKED")
    assert len(blocked) == 2
    assert all(r["attempts"] == 0 for r in blocked)
    assert len(fetch_tasks(env)) == 2  # 批就是 2 个，无其他 fetch 任务


# -- CHALLENGE / CONFIG：单点 BLOCKED（无连带）--------------------------------


@pytest.mark.parametrize("error_class", ["challenge", "config"])
def test_challenge_and_config_block_single_task(env: PipelineEnv, error_class: str) -> None:
    env.write_venue(fail_fetch(error_class, [0]))
    report = env.make_runner().pull(VENUE, Selector(volume="1", issue="1"))

    assert report.blocked == 1  # 仅注入者；不像 auth 那样整批连带
    assert report.succeeded == 4
    blocked = fetch_tasks(env, state="BLOCKED")
    assert len(blocked) == 1
    assert str(blocked[0]["blocked_reason"]).startswith(f"{error_class}:")
    assert blocked[0]["attempts"] == 0


# -- fail_enumerate → FAILED(parse)，级联继续 ---------------------------------


def test_enumerate_parse_fails_task_but_cascade_continues(env: PipelineEnv) -> None:
    env.write_venue(quirks_with(fail_enumerate={"volume": "2", "number": "1"}))
    report = env.make_runner().pull(VENUE, Selector(volume="2"))

    assert report.failed == 1
    assert report.failures[0]["stage"] == "enumerate"
    assert report.failures[0]["error_class"] == "parse"
    failed = env.db.query("SELECT * FROM task WHERE kind = 'enumerate' AND state = 'FAILED'")
    assert len(failed) == 1
    assert failed[0]["attempts"] == 1  # parse 不重试（RetrySpec(1)）
    assert failed[0]["error_class"] == "parse"

    # 另一期（2.2）不受影响：5 papers 全部走完
    assert report.succeeded == 5
    assert env.repo.counts(VENUE) == {
        "issues": 2,
        "papers": 5,
        "assets_planned": 5,
        "assets_fetched": 5,
    }


# -- GONE：asset 标 gone、任务 DONE、不重试 -----------------------------------


def test_gone_marks_asset_done_and_never_retries(env: PipelineEnv) -> None:
    env.write_venue(fail_fetch("gone", [2]))
    report = env.make_runner().pull(VENUE, Selector(volume="1", issue="1"))

    assert report.succeeded == 4 and report.failed == 0
    assert report.skipped == 1  # gone 计为预期内跳过
    gone_assets = env.repo.list_assets(venue_id=VENUE, state="gone")
    assert len(gone_assets) == 1
    tasks = fetch_tasks(env)
    assert len(tasks) == 5
    assert all(r["state"] == "DONE" for r in tasks)  # gone 的任务也是 DONE（预期内）
    assert all(r["attempts"] == 0 for r in tasks)
    assert len(failure_fetch_logs(env, "gone")) == 1  # 失败路径也写 fetch_log

    # 重跑：gone 资产不再进候选 → 不重试、不新建任务
    rerun = env.make_runner().pull(VENUE, Selector(volume="1", issue="1"))
    assert rerun.succeeded == 0 and rerun.failed == 0
    assert len(fetch_tasks(env)) == 5  # 无新 fetch 任务
    assert env.repo.counts(VENUE)["assets_fetched"] == 4


# -- NO_ENTITLEMENT：标 asset + FAILED ----------------------------------------


def test_no_entitlement_marks_asset_and_fails(env: PipelineEnv) -> None:
    env.write_venue(fail_fetch("no_entitlement", [1]))
    report = env.make_runner().pull(VENUE, Selector(volume="1", issue="1"))

    assert report.succeeded == 4 and report.failed == 1
    assert report.failures[0]["error_class"] == "no_entitlement"
    marked = env.repo.list_assets(venue_id=VENUE, state="no_entitlement")
    assert len(marked) == 1
    failed = fetch_tasks(env, state="FAILED")
    assert len(failed) == 1
    assert failed[0]["attempts"] == 1  # 不重试


# -- TRANSIENT：重试 3 次后 FAILED 且 attempts==4 -----------------------------


def test_transient_exhausts_retry_budget(env: PipelineEnv) -> None:
    """恒定注入 → 4 次尝试（首次+3 重试）全败 → FAILED；退避序列 2/8/30s 经 sleeper。"""
    env.write_venue(fail_fetch("transient", [0]))
    report = env.make_runner().pull(VENUE, Selector(volume="1", issue="1"))

    assert report.failed == 1 and report.succeeded == 4
    failed = fetch_tasks(env, state="FAILED")
    assert len(failed) == 1
    assert failed[0]["attempts"] == 4
    assert failed[0]["error_class"] == "transient"
    assert backoff_sleeps(env) == [2.0, 8.0, 30.0]  # RETRY_TABLE × retry_scale(=1)
    assert len(failure_fetch_logs(env, "transient")) == 4  # 每次尝试都留审计行


def test_transient_backoff_scaled_by_retry_scale(tmp_path: Path) -> None:
    env = make_env(tmp_path, retry_scale=0.5)
    try:
        env.write_venue(fail_fetch("transient", [0]))
        env.make_runner().pull(VENUE, Selector(volume="1", issue="1"))
        assert backoff_sleeps(env) == [1.0, 4.0, 15.0]  # 2/8/30 × 0.5
    finally:
        env.close()


# -- INTEGRITY：重下 1 次 ------------------------------------------------------


def test_integrity_retries_once_then_fails(env: PipelineEnv) -> None:
    env.write_venue(fail_fetch("integrity", [3]))
    report = env.make_runner().pull(VENUE, Selector(volume="1", issue="1"))

    assert report.failed == 1 and report.succeeded == 4
    failed = fetch_tasks(env, state="FAILED")
    assert len(failed) == 1
    assert failed[0]["attempts"] == 2  # RetrySpec(2)：首次 + 重下 1 次
    assert len(failure_fetch_logs(env, "integrity")) == 2


# -- RATE_LIMITED：不计 attempts + 循环保护升级 --------------------------------


def test_rate_limited_escalates_after_loop_protection(env: PipelineEnv) -> None:
    """恒定 rate_limited 注入不计 attempts（会无限重试）；连续 >3 次后升级按
    transient 处置 → 消耗预算 → FAILED（Phase 1 循环保护，runner docstring）。"""
    env.write_venue(fail_fetch("rate_limited", [0]))
    report = env.make_runner().pull(VENUE, Selector(volume="1", issue="1"))

    assert report.failed == 1 and report.succeeded == 4
    failed = fetch_tasks(env, state="FAILED")
    assert len(failed) == 1
    assert failed[0]["attempts"] == 4  # 前 3 次 rate_limited 不计，升级后 4 次计满
    assert failed[0]["error_class"] == "transient"
    assert len(failure_fetch_logs(env, "rate_limited")) >= 3


# -- 非 CrawlerError → TRANSIENT 处置 -----------------------------------------


def test_unexpected_exception_routed_as_transient(
    env: PipelineEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(
        self: MockPlatformAdapter, venue: VenueSpec, since: str | None = None
    ) -> Iterable[IssueRef]:
        raise RuntimeError("boom")

    monkeypatch.setattr(MockPlatformAdapter, "discover_timeline", boom)
    report = env.make_runner().run_single_stage("discover", VENUE, {})

    assert report.failed == 1
    assert report.failures[0]["error_class"] == "transient"
    assert "unexpected RuntimeError" in str(report.failures[0]["msg"])
    failed = env.db.query("SELECT * FROM task WHERE kind = 'discover' AND state = 'FAILED'")
    assert len(failed) == 1
    assert failed[0]["attempts"] == 4  # 按 TRANSIENT 预算重试后 FAILED


# -- 任务前提损坏 → CONFIG → BLOCKED ------------------------------------------


def test_fetch_task_with_missing_asset_blocks_as_config(env: PipelineEnv) -> None:
    env.queue.enqueue("fetch", VENUE, {"asset": "no_such_asset"})
    report = env.make_runner().drain()

    assert report.blocked == 1
    blocked = fetch_tasks(env, state="BLOCKED")
    assert len(blocked) == 1
    assert str(blocked[0]["blocked_reason"]).startswith("config:")


def test_resolve_task_with_missing_paper_blocks_as_config(env: PipelineEnv) -> None:
    env.queue.enqueue("resolve", VENUE, {"paper": "no_such_paper"})
    report = env.make_runner().drain()
    assert report.blocked == 1


def test_task_without_venue_blocks_as_config(env: PipelineEnv) -> None:
    env.queue.enqueue("ingest", None, {})
    report = env.make_runner().drain()
    assert report.blocked == 1


def test_extract_guards_block_as_config(env: PipelineEnv) -> None:
    """extract 的前提校验：asset 不存在 / 尚未 fetched → CONFIG → BLOCKED。"""
    env.queue.enqueue("extract", VENUE, {"asset": "ghost"})
    assert env.make_runner().drain().blocked == 1

    env.make_runner(dry_run=True).pull(VENUE, Selector(volume="1", issue="1"))  # 资产停在 planned
    planned = env.repo.list_assets(venue_id=VENUE, state="planned")
    env.queue.enqueue("extract", VENUE, {"asset": str(planned[0]["id"])})
    assert env.make_runner().drain().blocked == 1


# -- fetch 边缘分支：re-resolve 空结果 / ok=False / 魔数校验 / 限速覆盖 --------


def _planned_asset_with_fetch_task(env: PipelineEnv) -> str:
    """dry-run 建好 planned 资产后手工挂一个 fetch 任务，返回 asset_id。"""
    env.make_runner(dry_run=True).pull(VENUE, Selector(volume="1", issue="1"))
    asset_id = str(env.repo.list_assets(venue_id=VENUE, state="planned")[0]["id"])
    env.queue.enqueue("fetch", VENUE, {"asset": asset_id})
    return asset_id


def test_re_resolve_empty_plans_marks_gone(
    env: PipelineEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    """fetch 前 re-resolve 不再提供同身份 (kind,version) 计划 → GONE（资产已下架）。"""
    asset_id = _planned_asset_with_fetch_task(env)

    def no_plans(
        self: MockPlatformAdapter,
        venue: VenueSpec,
        paper: object,
        session: object | None = None,
    ) -> list[object]:
        return []

    monkeypatch.setattr(MockPlatformAdapter, "resolve_assets", no_plans)
    report = env.make_runner().drain()

    assert report.skipped == 1  # gone 按预期内跳过计数
    asset = env.repo.get_asset(asset_id)
    assert asset is not None and asset["state"] == "gone"


def test_adapter_ok_false_routed_by_result_error_class(
    env: PipelineEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    """协议允许 `FetchResult(ok=False)`（mock 不用此路径）：按 result.error_class 路由。"""
    asset_id = _planned_asset_with_fetch_task(env)

    def fetch_denied(
        self: MockPlatformAdapter, plan: object, io: object, session: object | None = None
    ) -> FetchResult:
        return FetchResult(ok=False, error_class=ErrorClass.NO_ENTITLEMENT, detail="denied")

    monkeypatch.setattr(MockPlatformAdapter, "fetch_asset", fetch_denied)
    report = env.make_runner().drain()

    assert report.failed == 1
    asset = env.repo.get_asset(asset_id)
    assert asset is not None and asset["state"] == "no_entitlement"


def test_non_pdf_payload_fails_integrity_and_aborts_part(
    env: PipelineEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    """魔数校验（§5.2）：非 %PDF 内容 → INTEGRITY（重下 1 次）→ FAILED；.part 被清理。"""
    _planned_asset_with_fetch_task(env)

    def fetch_html(
        self: MockPlatformAdapter, plan: object, io: PartFileIO, session: object | None = None
    ) -> FetchResult:
        n, sha = io.write_stream([b"<html>not a pdf</html>"])
        return FetchResult(ok=True, bytes_written=n, sha256=sha)

    monkeypatch.setattr(MockPlatformAdapter, "fetch_asset", fetch_html)
    report = env.make_runner().drain()

    assert report.failed == 1
    failed = fetch_tasks(env, state="FAILED")
    assert len(failed) == 1
    assert failed[0]["attempts"] == 2 and failed[0]["error_class"] == "integrity"
    assert list((env.config.data_dir / "tmp").glob("*.part")) == []  # abort 清理


def test_venue_rate_limit_override_takes_min(env: PipelineEnv) -> None:
    """VenueSpec.rate_limit 展开到 fulltext 主域并与 adapter 默认取最保守值。"""
    env.write_venue(dict(DEFAULT_QUIRKS), rate_limit_rpm=120.0)
    runner = env.make_runner()
    report = runner.pull(VENUE, Selector(volume="1", issue="1"))

    assert report.succeeded == 5
    assert runner.ctx.limiter.effective_rpm("mock.local") == 120.0  # min(600, 120)


def test_extract_force_rerun_does_not_duplicate_fulltext(env: PipelineEnv) -> None:
    """幂等键 (asset, extractor_ver)：force 重跑 extract handler，fulltext 不重插。"""
    env.make_runner().pull(VENUE, Selector(volume="1", issue="1"), with_extract=True)
    asset_id = str(env.repo.list_assets(venue_id=VENUE, state="fetched")[0]["id"])
    env.queue.enqueue("extract", VENUE, {"asset": asset_id}, force=True)

    report = env.make_runner().drain()

    assert report.failed == 0
    assert len(env.db.query("SELECT paper_id FROM fulltext")) == 5


def test_fetched_file_ok_requires_path_and_hash(env: PipelineEnv) -> None:
    """幂等跳过判据的负例：无 file_path/sha256 的 fetched 行不满足跳过条件。"""
    env.make_runner(dry_run=True).pull(VENUE, Selector(volume="1", issue="1"))
    asset_id = str(env.repo.list_assets(venue_id=VENUE)[0]["id"])
    env.repo.mark_asset(asset_id, state="fetched")  # 不带 file_path/sha256
    row = env.repo.get_asset(asset_id)
    assert row is not None
    assert fetched_file_ok(row) is False
