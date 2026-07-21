"""资产落位路径回归（design/06 §4）：si 全链集成 + pdf 零回归 + 不支持 kind 响亮 BLOCKED。

背景：`stages._asset_final_path` 曾经只认 `kind=pdf`；si 资产一旦 resolve 出计划、
走到 fetch，必抛 `CrawlerError(CONFIG)`，经 pipeline 特判转 BLOCKED 且永不自愈——
si 落位从未被实现，不是"一次性配置错误待人工修复"（cvf adapter 落地时发现并上报；
mock/arxiv/openreview/pmlr 在此之前都不产 si 资产，Phase 1 验收未暴露）。

本文件经真实 `PipelineRunner.pull` 级联（不直接调 `_asset_final_path`，那部分
纯函数契约见 `tests/unit/test_stages_asset_path.py`）钉死修复后的三条路径：
- si 资产：mock 的 `emit_si` quirk（默认关，向后兼容零回归）驱动一条 si
  `AssetPlan` 走完整 discover→enumerate→resolve→fetch→ingest，文件落在
  design/06 §4 的 `data/si/{venue_id}/{year}/{paper_ulid}/{原名}` 布局、DB
  asset 行 kind=si/state=fetched 且 file_path/sha256/bytes 正确；
- 原 pdf 路径零回归：`emit_si=True` 时 pdf 资产的落位/计数与 test_pipeline_e2e
  的既有断言完全一致；
- 真正不受支持的 kind（html/bibtex/source，§4 未给出布局）：响亮 CONFIG→BLOCKED，
  且与其余下载失败路径同构地留下 fetch_log 审计行 + `.part` 清理（而不是静默
  错位，或者失败却查无凭据）。

环境构建器复用 test_pipeline_e2e 的 `make_env`（tests/ 无顶层包，按既有先例以
`integration.` 顶层包名导入）。
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from pathlib import Path

import pytest

from integration.test_pipeline_e2e import DEFAULT_QUIRKS, VENUE, PipelineEnv, make_env
from paper_crawler.adapters.mock_platform import MockPlatformAdapter
from paper_crawler.pipeline import Selector
from paper_crawler.types import AssetKind, AssetPlan, AuthLevel, PaperStub, SessionHandle, VenueSpec

SI_QUIRKS: dict[str, object] = {**DEFAULT_QUIRKS, "emit_si": True}


@pytest.fixture
def si_env(tmp_path: Path) -> Iterator[PipelineEnv]:
    e = make_env(tmp_path, quirks=SI_QUIRKS)
    yield e
    e.close()


@pytest.fixture
def env(tmp_path: Path) -> Iterator[PipelineEnv]:
    e = make_env(tmp_path)
    yield e
    e.close()


def si_files(env: PipelineEnv) -> list[Path]:
    si_root = env.config.data_dir / "si"
    return sorted(p for p in si_root.rglob("*") if p.is_file()) if si_root.is_dir() else []


def pdf_files(env: PipelineEnv) -> list[Path]:
    pdf_root = env.config.data_dir / "pdf"
    return sorted(pdf_root.rglob("*.pdf")) if pdf_root.is_dir() else []


# -- si 全链：文件落位 + DB asset 行（design/06 §4 新增支持）------------------------------


def test_si_asset_pull_lands_file_at_designed_path(si_env: PipelineEnv) -> None:
    """si 资产走 pull 级联：不再 BLOCKED，文件落在 design/06 §4 的 si 布局。"""
    report = si_env.make_runner().pull(VENUE, Selector(volume="1", issue="1"))

    assert report.blocked == 0 and report.failed == 0
    assert report.succeeded == 10  # 5 papers x (pdf + si)

    files = si_files(si_env)
    assert len(files) == 5
    expected_root = si_env.config.data_dir / "si" / VENUE / "2024"
    for f in files:
        assert f.name == "supplement.zip"  # mock emit_si 的固定 basename（保持原名语义）
        assert f.parent.parent == expected_root  # .../si/{venue}/{year}/{paper_ulid}/supplement.zip


def test_si_asset_db_row_has_correct_kind_state_and_landing_columns(
    si_env: PipelineEnv,
) -> None:
    si_env.make_runner().pull(VENUE, Selector(volume="1", issue="1"))

    si_rows = si_env.repo.list_assets(venue_id=VENUE, state="fetched")
    si_rows = [r for r in si_rows if r["kind"] == "si"]
    assert len(si_rows) == 5

    for row in si_rows:
        path = Path(str(row["file_path"]))
        assert path.is_file()
        assert path.name == "supplement.zip"
        assert path.parent.name == str(row["paper_id"])  # si 目录按 paper 一层
        assert row["bytes"] is not None and int(row["bytes"]) > 0
        assert row["sha256"] is not None and len(str(row["sha256"])) == 64
        assert path.read_bytes()  # 落地文件非空
        assert hashlib.sha256(path.read_bytes()).hexdigest() == str(row["sha256"])


def test_si_asset_counts_and_fetch_log(si_env: PipelineEnv) -> None:
    si_env.make_runner().pull(VENUE, Selector(volume="1", issue="1"))

    counts = si_env.repo.counts(VENUE)
    assert counts == {
        "issues": 1,
        "papers": 5,
        "assets_planned": 10,  # 5 pdf + 5 si
        "assets_fetched": 10,
    }
    success_logs = [r for r in si_env.repo.fetch_logs() if r["error_class"] is None]
    assert len(success_logs) == 10


def test_si_asset_pull_rerun_is_idempotent(si_env: PipelineEnv) -> None:
    """重跑：si 资产同 pdf 一样幂等跳过（fetched_file_ok 判据不区分 kind）。"""
    si_env.make_runner().pull(VENUE, Selector(volume="1", issue="1"))
    before = len(si_files(si_env))

    rerun = si_env.make_runner().pull(VENUE, Selector(volume="1", issue="1"))

    assert rerun.succeeded == 0 and rerun.failed == 0 and rerun.blocked == 0
    assert len(si_files(si_env)) == before == 5


# -- pdf 零回归：emit_si=True 时 pdf 落位/计数与既有 e2e 断言完全一致 ----------------------


def test_pdf_landing_unaffected_when_si_also_emitted(si_env: PipelineEnv) -> None:
    si_env.make_runner().pull(VENUE, Selector(volume="1", issue="1"))

    files = pdf_files(si_env)
    assert len(files) == 5
    expected_dir = si_env.config.data_dir / "pdf" / VENUE / "2024"
    assert all(f.parent == expected_dir for f in files)  # design/06 §4 布局不变

    pdf_rows = [
        r for r in si_env.repo.list_assets(venue_id=VENUE, state="fetched") if r["kind"] == "pdf"
    ]
    assert len(pdf_rows) == 5


def test_emit_si_default_off_matches_pre_fix_pdf_only_behavior(env: PipelineEnv) -> None:
    """`emit_si` 未设置（默认 quirks）：行为与修复前完全一致——仅 pdf，向后兼容零回归。"""
    report = env.make_runner().pull(VENUE, Selector(volume="1", issue="1"))

    assert report.succeeded == 5
    assert report.blocked == 0
    assert si_files(env) == []
    assert env.repo.counts(VENUE)["assets_planned"] == 5


# -- 不支持的 kind：响亮 CONFIG → BLOCKED（而非静默错位或裸异常穿透）-----------------------


@pytest.mark.parametrize("kind", [AssetKind.HTML, AssetKind.BIBTEX, AssetKind.SOURCE])
def test_unsupported_asset_kind_blocks_loudly_with_audit_trail(
    env: PipelineEnv, monkeypatch: pytest.MonkeyPatch, kind: AssetKind
) -> None:
    """design/06 §4 未给出布局的 kind：fetch 落位响亮 CONFIG→BLOCKED，且留下与其余
    失败路径同构的审计（fetch_log 行 + `.part` 清理）——不是静默卡死、查无凭据。"""

    def resolve_unsupported(
        self: MockPlatformAdapter,
        venue: VenueSpec,
        paper: PaperStub,
        session: SessionHandle | None = None,
    ) -> list[AssetPlan]:
        doi = paper.identifiers[0][1]
        return [
            AssetPlan(
                kind=kind,
                url=f"https://mock.local/{kind.value}/{doi}",
                expected_type="text/plain",
                auth_needed=AuthLevel.NONE,
            )
        ]

    monkeypatch.setattr(MockPlatformAdapter, "resolve_assets", resolve_unsupported)
    report = env.make_runner().pull(VENUE, Selector(volume="1", issue="1", limit=1))

    assert report.blocked == 1
    assert report.succeeded == 0 and report.failed == 0

    blocked = env.db.query("SELECT * FROM task WHERE kind = 'fetch' AND state = 'BLOCKED'")
    assert len(blocked) == 1
    reason = str(blocked[0]["blocked_reason"])
    assert reason.startswith("config:")
    assert "unsupported asset kind" in reason
    assert kind.value in reason

    # 与其余失败路径同构：留下失败 fetch_log 审计行（T7c 后 landing 解析纳入同一
    # try/except，不再是"落位失败跳过审计"的特例）。
    failure_logs = [r for r in env.repo.fetch_logs() if r["error_class"] == "config"]
    assert len(failure_logs) == 1

    # asset 本身停在 planned（从未落地），且 tmp 目录不留残余 .part。
    assets = env.repo.list_assets(venue_id=VENUE)
    assert all(str(a["state"]) == "planned" for a in assets)
    assert list((env.config.data_dir / "tmp").glob("*.part")) == []


def test_unsupported_asset_kind_does_not_block_other_papers_in_batch(
    env: PipelineEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CONFIG 单点 BLOCKED（同 CHALLENGE 一样无连带）：批内其余 pdf 资产照常成功。"""

    def resolve_html_for_first_only(
        self: MockPlatformAdapter,
        venue: VenueSpec,
        paper: PaperStub,
        session: SessionHandle | None = None,
    ) -> list[AssetPlan]:
        doi = paper.identifiers[0][1]
        if doi.endswith(".0"):
            return [
                AssetPlan(
                    kind=AssetKind.HTML,
                    url=f"https://mock.local/html/{doi}",
                    expected_type="text/html",
                    auth_needed=AuthLevel.NONE,
                )
            ]
        return [
            AssetPlan(
                kind=AssetKind.PDF,
                url=f"https://mock.local/pdf/{doi}",
                expected_type="application/pdf",
                auth_needed=AuthLevel.NONE,
            )
        ]

    monkeypatch.setattr(MockPlatformAdapter, "resolve_assets", resolve_html_for_first_only)
    report = env.make_runner().pull(VENUE, Selector(volume="1", issue="1"))

    assert report.blocked == 1
    assert report.succeeded == 4  # 其余 4 篇 pdf 照常完成
    assert len(pdf_files(env)) == 4
