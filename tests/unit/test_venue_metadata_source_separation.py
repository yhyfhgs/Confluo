"""VenueSpec `metadata_source` 分离语义单测（D-005，plan §2-2；crossref 是第一消费者）。

纯附加变更（`metadata_source: str` → `str | None = None`）落地校验，独立成文件避免触
共享花名册断言（5 线并行纪律）。覆盖：
- None 默认 = 沿用 adapter 自身（VenueSpec 接受省略；route 回退 fulltext_source 平台 adapter）；
- 同源写法（metadata_source==fulltext_source）不触发 aggregator 约束（既有全部 venue 形态）；
- 真分离 + aggregator（crossref≠elsevier_sd）通过；
- 真分离 + 非 aggregator → lint 报"须为 aggregator"；
- 声明但未注册 → lint 报"未注册"（既有行为保持）；
- 期刊 + crossref → issn 必填（D-015 既有规则保持）。
"""

from pathlib import Path

import pytest

from paper_crawler.adapter import SourceAdapter, load_adapters
from paper_crawler.registry import LintIssue, VenueRegistry
from paper_crawler.types import VenueSpec


@pytest.fixture
def adapters() -> dict[str, SourceAdapter]:
    return load_adapters()


def _write(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines), encoding="utf-8")


def _issues_for_field(issues: list[LintIssue], field: str) -> list[LintIssue]:
    return [issue for issue in issues if issue.field == field]


# -- types 层：字段可选（纯附加） -------------------------------------------------


def test_venue_spec_accepts_omitted_metadata_source() -> None:
    """省略 metadata_source → 默认 None（不再必填；纯附加放宽）。"""
    spec = VenueSpec(
        id="omit_meta",
        kind="conference",
        names={"full": "Omit Meta Venue"},
        field=["cs_ai"],
        fulltext_source="mock_platform",
    )
    assert spec.metadata_source is None
    assert spec.fulltext_source == "mock_platform"


def test_venue_spec_still_accepts_explicit_metadata_source() -> None:
    """既有显式声明写法不受影响（零回归）。"""
    spec = VenueSpec(
        id="explicit_meta",
        kind="conference",
        names={"full": "Explicit Meta Venue"},
        field=["cs_ai"],
        metadata_source="crossref",
        fulltext_source="elsevier_sd",
    )
    assert spec.metadata_source == "crossref"


# -- route 层：None 回退 adapter 自身 --------------------------------------------


def test_route_none_metadata_source_falls_back_to_fulltext_adapter(
    adapters: dict[str, SourceAdapter], tmp_path: Path
) -> None:
    """metadata_source 省略（None）→ route.metadata_adapter = fulltext_source 平台 adapter。"""
    _write(
        tmp_path / "none-meta.yaml",
        [
            "id: none_meta",
            "kind: conference",
            "names: {full: None Meta Venue}",
            "field: [cs_ai]",
            "fulltext_source: mock_platform",
        ],
    )
    reg = VenueRegistry(adapters)
    assert reg.load_dirs([tmp_path]) == []
    route = reg.route("none_meta")
    assert route.metadata_adapter.adapter_id == "mock_platform"
    assert route.fulltext_adapter.adapter_id == "mock_platform"


def test_route_separated_metadata_source_binds_aggregator(
    adapters: dict[str, SourceAdapter], tmp_path: Path
) -> None:
    """真分离（crossref≠elsevier_sd）→ metadata_adapter=crossref、fulltext_adapter=elsevier_sd。"""
    _write(
        tmp_path / "sep-meta.yaml",
        [
            "id: sep_meta",
            "kind: journal",
            "names: {full: Separated Journal}",
            "field: [finance]",
            "identifiers: {issn: ['0304-405X']}",
            "metadata_source: crossref",
            "fulltext_source: elsevier_sd",
            "auth: {level: institutional}",
        ],
    )
    reg = VenueRegistry(adapters)
    assert reg.load_dirs([tmp_path]) == []
    route = reg.route("sep_meta")
    assert route.metadata_adapter.adapter_id == "crossref"
    assert route.fulltext_adapter.adapter_id == "elsevier_sd"


# -- lint 层：aggregator 约束（仅真分离时触发） ----------------------------------


def test_lint_clean_when_none_metadata_source(
    adapters: dict[str, SourceAdapter], tmp_path: Path
) -> None:
    """省略 metadata_source（None）→ 不触发任何 metadata_source lint。"""
    _write(
        tmp_path / "none-meta.yaml",
        [
            "id: none_meta",
            "kind: conference",
            "names: {full: None Meta Venue}",
            "field: [cs_ai]",
            "fulltext_source: mock_platform",
        ],
    )
    reg = VenueRegistry(adapters)
    reg.load_dirs([tmp_path])
    assert _issues_for_field(reg.lint(), "metadata_source") == []


def test_lint_clean_when_same_source_non_aggregator(
    adapters: dict[str, SourceAdapter], tmp_path: Path
) -> None:
    """同源写法（openreview==openreview，open_access）不触发 aggregator 约束（既有 venue 形态）。"""
    _write(
        tmp_path / "same-src.yaml",
        [
            "id: same_src",
            "kind: conference",
            "names: {full: Same Source Venue}",
            "field: [cs_ai]",
            "metadata_source: openreview",
            "fulltext_source: openreview",
            "auth: {level: free_account}",
        ],
    )
    reg = VenueRegistry(adapters)
    reg.load_dirs([tmp_path])
    assert _issues_for_field(reg.lint(), "metadata_source") == []


def test_lint_clean_when_separated_aggregator(
    adapters: dict[str, SourceAdapter], tmp_path: Path
) -> None:
    """真分离 + aggregator（crossref≠elsevier_sd）→ 无 metadata_source lint。"""
    _write(
        tmp_path / "sep-agg.yaml",
        [
            "id: sep_agg",
            "kind: journal",
            "names: {full: Separated Aggregator Journal}",
            "field: [finance]",
            "identifiers: {issn: ['0304-405X']}",
            "metadata_source: crossref",
            "fulltext_source: elsevier_sd",
            "auth: {level: institutional}",
        ],
    )
    reg = VenueRegistry(adapters)
    reg.load_dirs([tmp_path])
    assert _issues_for_field(reg.lint(), "metadata_source") == []


def test_lint_flags_separated_non_aggregator_metadata_source(
    adapters: dict[str, SourceAdapter], tmp_path: Path
) -> None:
    """真分离 + 非 aggregator（openreview 元数据 / elsevier_sd 全文）→ lint 报"须为 aggregator"。"""
    _write(
        tmp_path / "sep-nonagg.yaml",
        [
            "id: sep_nonagg",
            "kind: journal",
            "names: {full: Separated Non-Aggregator Journal}",
            "field: [finance]",
            "identifiers: {issn: ['0304-405X']}",
            "metadata_source: openreview",  # open_access family，≠ fulltext → 违约
            "fulltext_source: elsevier_sd",
            "auth: {level: institutional}",
        ],
    )
    reg = VenueRegistry(adapters)
    reg.load_dirs([tmp_path])
    hits = _issues_for_field(reg.lint(), "metadata_source")
    assert len(hits) == 1
    assert hits[0].venue_id == "sep_nonagg"
    assert "aggregator" in hits[0].message


def test_lint_flags_unregistered_declared_metadata_source(
    adapters: dict[str, SourceAdapter], tmp_path: Path
) -> None:
    """声明但未注册 → 报"未注册"（既有行为保持；不额外报 aggregator，无法判未注册者的 family）。"""
    _write(
        tmp_path / "unreg-meta.yaml",
        [
            "id: unreg_meta",
            "kind: conference",
            "names: {full: Unregistered Meta Venue}",
            "field: [cs_ai]",
            "metadata_source: made_up_source",
            "fulltext_source: mock_platform",
        ],
    )
    reg = VenueRegistry(adapters)
    reg.load_dirs([tmp_path])
    hits = _issues_for_field(reg.lint(), "metadata_source")
    assert len(hits) == 1
    assert "made_up_source" in hits[0].message
    assert "未注册" in hits[0].message


def test_lint_journal_crossref_requires_issn(
    adapters: dict[str, SourceAdapter], tmp_path: Path
) -> None:
    """期刊 kind + metadata_source=crossref 缺 issn → 报 issn 必填（D-015 既有规则保持）。"""
    _write(
        tmp_path / "crossref-no-issn.yaml",
        [
            "id: crossref_no_issn",
            "kind: journal",
            "names: {full: Crossref Journal No Issn}",
            "field: [finance]",
            "metadata_source: crossref",
            "fulltext_source: elsevier_sd",
            "auth: {level: institutional}",
        ],
    )
    reg = VenueRegistry(adapters)
    reg.load_dirs([tmp_path])
    hits = _issues_for_field(reg.lint(), "identifiers.issn")
    assert len(hits) == 1
    assert hits[0].venue_id == "crossref_no_issn"
