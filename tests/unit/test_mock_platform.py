"""mock_platform（T6 实现）单测：quirks 派生的确定性语料、故障注入、golden 快照。

对应 phase1-implementation-plan.md Task 6 的"Mock 语料规格"节——这些用例即该规格的
可执行定义；后续任务（T7 pipeline、T9 验收）依赖此文件锁定的行为作为权威契约。
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from helpers import FakeFetchIO, make_mock_venue
from helpers.golden import assert_matches_golden
from paper_crawler.adapters.mock_platform import MockPlatformAdapter
from paper_crawler.errors import CrawlerError, ErrorClass
from paper_crawler.types import AssetKind, AuthLevel, IssueRef, PaperStub, VenueSpec

GOLDEN_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "mock_platform" / "golden"


@pytest.fixture
def adapter() -> MockPlatformAdapter:
    return MockPlatformAdapter()


@pytest.fixture
def venue() -> VenueSpec:
    return make_mock_venue()


# --- discover_timeline -------------------------------------------------------------------


def test_discover_timeline_default_quirks_yields_six_issues(
    adapter: MockPlatformAdapter, venue: VenueSpec
) -> None:
    issues = list(adapter.discover_timeline(venue))
    assert len(issues) == 6  # volumes=3 x issues_per_volume=2


def test_discover_timeline_year_mapping(adapter: MockPlatformAdapter, venue: VenueSpec) -> None:
    by_key = {(i.volume, i.number): i for i in adapter.discover_timeline(venue)}
    assert by_key[("1", "1")].year == 2024
    assert by_key[("2", "1")].year == 2025
    assert by_key[("3", "1")].year == 2026


def test_discover_timeline_fields(adapter: MockPlatformAdapter, venue: VenueSpec) -> None:
    for issue in adapter.discover_timeline(venue):
        assert isinstance(issue, IssueRef)
        assert issue.venue_id == venue.id
        assert issue.label is None
        assert issue.paper_count_claimed == 5


def test_discover_timeline_ignores_since(adapter: MockPlatformAdapter, venue: VenueSpec) -> None:
    full = list(adapter.discover_timeline(venue))
    with_since = list(adapter.discover_timeline(venue, since="2099-01-01"))
    assert full == with_since


def test_discover_timeline_respects_custom_quirks() -> None:
    venue = make_mock_venue(volumes=1, issues_per_volume=1)
    issues = list(MockPlatformAdapter().discover_timeline(venue))
    assert len(issues) == 1
    assert issues[0].volume == "1"
    assert issues[0].number == "1"
    assert issues[0].year == 2024
    assert issues[0].paper_count_claimed == 5


# --- enumerate_issue ----------------------------------------------------------------------


def test_enumerate_issue_yields_papers_per_issue_count(
    adapter: MockPlatformAdapter, venue: VenueSpec
) -> None:
    issue = IssueRef(venue_id=venue.id, volume="1", number="1", year=2024)
    papers = list(adapter.enumerate_issue(venue, issue))
    assert len(papers) == 5


def test_enumerate_issue_paper_fields(adapter: MockPlatformAdapter, venue: VenueSpec) -> None:
    issue = IssueRef(venue_id=venue.id, volume="1", number="1", year=2024)
    papers = list(adapter.enumerate_issue(venue, issue))
    for i, paper in enumerate(papers):
        assert isinstance(paper, PaperStub)
        assert paper.title.startswith(f"Mock Paper 1.1.{i}: ")
        assert len(paper.identifiers) == 1
        scheme, value = paper.identifiers[0]
        assert scheme == "doi"
        assert value == f"10.9999/{venue.id}.1.1.{i}"
        assert paper.year == 2024
        assert len(paper.authors) == 2


def test_enumerate_issue_is_deterministic_for_same_seed(venue: VenueSpec) -> None:
    issue = IssueRef(venue_id=venue.id, volume="1", number="1", year=2024)
    first = list(MockPlatformAdapter().enumerate_issue(venue, issue))
    second = list(MockPlatformAdapter().enumerate_issue(venue, issue))
    assert first == second


def test_enumerate_issue_differs_across_issues(
    adapter: MockPlatformAdapter, venue: VenueSpec
) -> None:
    issue_a = IssueRef(venue_id=venue.id, volume="1", number="1", year=2024)
    issue_b = IssueRef(venue_id=venue.id, volume="1", number="2", year=2024)
    titles_a = [p.title for p in adapter.enumerate_issue(venue, issue_a)]
    titles_b = [p.title for p in adapter.enumerate_issue(venue, issue_b)]
    assert titles_a != titles_b


def test_enumerate_issue_differs_across_seeds(adapter: MockPlatformAdapter) -> None:
    issue = IssueRef(venue_id="mock_journal", volume="1", number="1", year=2024)
    venue_a = make_mock_venue(seed=42)
    venue_b = make_mock_venue(seed=43)
    titles_a = [p.title for p in adapter.enumerate_issue(venue_a, issue)]
    titles_b = [p.title for p in adapter.enumerate_issue(venue_b, issue)]
    assert titles_a != titles_b


def test_enumerate_issue_fail_enumerate_quirk_raises_parse(adapter: MockPlatformAdapter) -> None:
    venue = make_mock_venue(fail_enumerate={"volume": "2", "number": "1"})
    issue = IssueRef(venue_id=venue.id, volume="2", number="1", year=2025)
    with pytest.raises(CrawlerError) as exc_info:
        list(adapter.enumerate_issue(venue, issue))
    assert exc_info.value.error_class is ErrorClass.PARSE


def test_enumerate_issue_fail_enumerate_quirk_is_scoped_to_target_issue(
    adapter: MockPlatformAdapter,
) -> None:
    venue = make_mock_venue(fail_enumerate={"volume": "2", "number": "1"})
    other_issue = IssueRef(venue_id=venue.id, volume="1", number="1", year=2024)
    papers = list(adapter.enumerate_issue(venue, other_issue))
    assert len(papers) == 5


# --- resolve_assets -----------------------------------------------------------------------


def test_resolve_assets_default_plan(adapter: MockPlatformAdapter, venue: VenueSpec) -> None:
    issue = IssueRef(venue_id=venue.id, volume="1", number="1", year=2024)
    paper = next(iter(adapter.enumerate_issue(venue, issue)))
    plans = adapter.resolve_assets(venue, paper)
    assert len(plans) == 1
    plan = plans[0]
    doi = paper.identifiers[0][1]
    assert plan.kind == AssetKind.PDF
    assert plan.url == f"https://mock.local/pdf/{doi}"
    assert plan.expected_type == "application/pdf"
    assert plan.auth_needed == AuthLevel.NONE


def test_resolve_assets_fail_fetch_quirk_encodes_query_param(
    adapter: MockPlatformAdapter,
) -> None:
    venue = make_mock_venue(fail_fetch={"error_class": "auth_expired", "paper_indexes": [0, 1]})
    issue = IssueRef(venue_id=venue.id, volume="1", number="1", year=2024)
    papers = list(adapter.enumerate_issue(venue, issue))

    failing_plan = adapter.resolve_assets(venue, papers[0])[0]
    assert "fail=auth_expired" in failing_plan.url

    ok_plan = adapter.resolve_assets(venue, papers[2])[0]
    assert "fail=" not in ok_plan.url


def test_resolve_assets_fetch_delay_quirk_encodes_query_param(
    adapter: MockPlatformAdapter,
) -> None:
    venue = make_mock_venue(fetch_delay_ms=200)
    issue = IssueRef(venue_id=venue.id, volume="1", number="1", year=2024)
    paper = next(iter(adapter.enumerate_issue(venue, issue)))
    plan = adapter.resolve_assets(venue, paper)[0]
    assert "delay_ms=200" in plan.url


def test_resolve_assets_fail_fetch_without_paper_indexes_matches_nothing(
    adapter: MockPlatformAdapter,
) -> None:
    # fail_fetch 缺 paper_indexes（或类型不对）时不应误伤——退化为"不匹配任何 index"。
    venue = make_mock_venue(fail_fetch={"error_class": "gone"})
    issue = IssueRef(venue_id=venue.id, volume="1", number="1", year=2024)
    paper = next(iter(adapter.enumerate_issue(venue, issue)))
    plan = adapter.resolve_assets(venue, paper)[0]
    assert "fail=" not in plan.url


def test_resolve_assets_picks_doi_identifier_among_others(
    adapter: MockPlatformAdapter, venue: VenueSpec
) -> None:
    # doi 不一定是第一个 identifier；resolve 必须专门挑出 scheme=="doi" 的那一个。
    paper = PaperStub(
        title="T",
        identifiers=(("isbn", "irrelevant"), ("doi", f"10.9999/{venue.id}.1.1.0")),
    )
    plan = adapter.resolve_assets(venue, paper)[0]
    assert plan.url == f"https://mock.local/pdf/10.9999/{venue.id}.1.1.0"


def test_resolve_assets_raises_config_when_paper_missing_doi(
    adapter: MockPlatformAdapter, venue: VenueSpec
) -> None:
    paper = PaperStub(title="T", identifiers=(("isbn", "irrelevant"),))
    with pytest.raises(CrawlerError) as exc_info:
        adapter.resolve_assets(venue, paper)
    assert exc_info.value.error_class is ErrorClass.CONFIG


def test_resolve_assets_raises_parse_for_doi_from_a_different_venue(
    adapter: MockPlatformAdapter, venue: VenueSpec
) -> None:
    paper = PaperStub(title="T", identifiers=(("doi", "10.9999/some_other_venue.1.1.0"),))
    with pytest.raises(CrawlerError) as exc_info:
        adapter.resolve_assets(venue, paper)
    assert exc_info.value.error_class is ErrorClass.PARSE


# --- quirks 健壮性（畸形/边界输入不崩溃，退回默认值）----------------------------------------


def test_malformed_boolean_quirk_falls_back_to_default(adapter: MockPlatformAdapter) -> None:
    # YAML 1.1 的 `yes`/`no`/`true` 等会被 PyYAML 解析成 bool；bool 是 int 子类，
    # 若不特判会被 int() 静默接受成 0/1，产出的语料量会离谱地偏小。
    venue = make_mock_venue(volumes=True)
    issues = list(adapter.discover_timeline(venue))
    assert len(issues) == 6  # 退回默认 volumes=3 x issues_per_volume=2


def test_uncoercible_quirk_value_falls_back_to_default(adapter: MockPlatformAdapter) -> None:
    venue = make_mock_venue(papers_per_issue=["not", "a", "number"])
    issue = IssueRef(venue_id=venue.id, volume="1", number="1", year=2024)
    papers = list(adapter.enumerate_issue(venue, issue))
    assert len(papers) == 5  # 退回默认 papers_per_issue=5


# --- fetch_asset --------------------------------------------------------------------------


def test_fetch_asset_writes_deterministic_pdf_bytes(
    adapter: MockPlatformAdapter, venue: VenueSpec
) -> None:
    issue = IssueRef(venue_id=venue.id, volume="1", number="1", year=2024)
    paper = next(iter(adapter.enumerate_issue(venue, issue)))
    plan = adapter.resolve_assets(venue, paper)[0]
    doi = paper.identifiers[0][1]

    io = FakeFetchIO()
    result = adapter.fetch_asset(plan, io)

    expected = b"%PDF-1.4\n% " + doi.encode() + b"\n" + b"0" * 2048 + b"\n%%EOF\n"
    assert io.data == expected
    assert result.ok is True
    assert result.bytes_written == len(expected)
    assert result.sha256 == hashlib.sha256(expected).hexdigest()
    assert io.chunk_count >= 2  # 分 2-3 chunk 写以测流式


@pytest.mark.parametrize("error_class", list(ErrorClass))
def test_fetch_asset_fail_fetch_quirk_raises_configured_error_class(
    adapter: MockPlatformAdapter, error_class: ErrorClass
) -> None:
    venue = make_mock_venue(fail_fetch={"error_class": error_class.value, "paper_indexes": [0]})
    issue = IssueRef(venue_id=venue.id, volume="1", number="1", year=2024)
    paper = next(iter(adapter.enumerate_issue(venue, issue)))
    plan = adapter.resolve_assets(venue, paper)[0]

    with pytest.raises(CrawlerError) as exc_info:
        adapter.fetch_asset(plan, io=FakeFetchIO())
    assert exc_info.value.error_class is error_class


def test_fetch_asset_fail_fetch_quirk_spares_other_indexes(
    adapter: MockPlatformAdapter,
) -> None:
    venue = make_mock_venue(fail_fetch={"error_class": "auth_expired", "paper_indexes": [0, 1]})
    issue = IssueRef(venue_id=venue.id, volume="1", number="1", year=2024)
    papers = list(adapter.enumerate_issue(venue, issue))
    plan = adapter.resolve_assets(venue, papers[2])[0]

    result = adapter.fetch_asset(plan, io=FakeFetchIO())
    assert result.ok is True


def test_fetch_asset_delay_quirk_sleeps(
    monkeypatch: pytest.MonkeyPatch, adapter: MockPlatformAdapter
) -> None:
    sleeps: list[float] = []
    monkeypatch.setattr(
        "paper_crawler.adapters.mock_platform.time.sleep", lambda s: sleeps.append(s)
    )
    venue = make_mock_venue(fetch_delay_ms=200)
    issue = IssueRef(venue_id=venue.id, volume="1", number="1", year=2024)
    paper = next(iter(adapter.enumerate_issue(venue, issue)))
    plan = adapter.resolve_assets(venue, paper)[0]

    adapter.fetch_asset(plan, io=FakeFetchIO())
    assert sleeps == [0.2]


def test_fetch_asset_no_delay_quirk_does_not_sleep(
    monkeypatch: pytest.MonkeyPatch, adapter: MockPlatformAdapter, venue: VenueSpec
) -> None:
    sleeps: list[float] = []
    monkeypatch.setattr(
        "paper_crawler.adapters.mock_platform.time.sleep", lambda s: sleeps.append(s)
    )
    issue = IssueRef(venue_id=venue.id, volume="1", number="1", year=2024)
    paper = next(iter(adapter.enumerate_issue(venue, issue)))
    plan = adapter.resolve_assets(venue, paper)[0]

    adapter.fetch_asset(plan, io=FakeFetchIO())
    assert sleeps == []


# --- golden -------------------------------------------------------------------------------


def test_discover_timeline_matches_golden(adapter: MockPlatformAdapter, venue: VenueSpec) -> None:
    issues = list(adapter.discover_timeline(venue))
    assert_matches_golden(issues, GOLDEN_DIR / "timeline.json")


def test_enumerate_v1n1_matches_golden(adapter: MockPlatformAdapter, venue: VenueSpec) -> None:
    issue = IssueRef(venue_id=venue.id, volume="1", number="1", year=2024)
    papers = list(adapter.enumerate_issue(venue, issue))
    assert_matches_golden(papers, GOLDEN_DIR / "issue-v1n1.json")
