"""watch 编排的纯逻辑面（Phase 6 T5）：请求合成、adapter 接缝、退出码、日报路径。

带 DB 的端到端四场景在 `tests/integration/test_subs_watch_e2e.py`（mock_platform 载体），
CLI 层在 `tests/integration/test_cli_subs_watch.py`。本文件只测不需要 sqlite 的部分。
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import date
from pathlib import Path

import httpx
import pytest

from helpers.nber_fixtures import fixture_bytes
from paper_crawler.adapter import AdapterBase, AdapterFamily
from paper_crawler.errors import CrawlerError, ErrorClass
from paper_crawler.http import HttpClient
from paper_crawler.subs.compile import compile_subscription
from paper_crawler.subs.model import SOURCE_FIELDS, parse_subscription
from paper_crawler.subs.types import PlanStep, ReportEntry, RunSummary, WatchOutcome
from paper_crawler.subs.watch import (
    MERGE_SOURCE,
    SUPPORTED_SOURCES,
    AdapterFetcher,
    NberRssFetcher,
    RoutingFetcher,
    SourceRequest,
    build_requests,
    daily_report_path,
    exit_code_for,
    overload_brief,
)
from paper_crawler.types import (
    AuthLevel,
    Capability,
    IssueRef,
    PaperStub,
    RatePolicy,
    VenueNames,
    VenueSpec,
)

# ---------------------------------------------------------------------------
# 清单漂移自断言（同 `compile.SUPPORTED_SOURCES` 的守法：注册了却没接线 = 静默漏源）
# ---------------------------------------------------------------------------


def test_composer_registry_covers_every_dsl_source() -> None:
    assert SUPPORTED_SOURCES == set(SOURCE_FIELDS)


def test_merge_source_table_covers_every_dsl_source() -> None:
    assert set(MERGE_SOURCE) == set(SOURCE_FIELDS)


# ---------------------------------------------------------------------------
# 请求合成
# ---------------------------------------------------------------------------


def _step(source: str, *pushdown: tuple[str, str]) -> PlanStep:
    return PlanStep(source=source, pushdown=tuple(pushdown))


def test_arxiv_window_is_anded_into_the_same_search_query() -> None:
    """arxiv 的 submittedDate 不是独立参数——必须并进同一个 search_query。"""
    step = _step("arxiv", ("search_query", "(cat:cs.AI OR cat:cs.LG)"))
    window = (("submittedDate", "[202607190000 TO 202607262359]"),)

    (request,) = build_requests("s", step, window)

    assert request.params == (
        (
            "search_query",
            "(cat:cs.AI OR cat:cs.LG) AND submittedDate:[202607190000 TO 202607262359]",
        ),
    )
    assert request.since is None  # arxiv 的窗只以查询式形态存在，无独立 ISO 下界


def test_arxiv_without_static_query_emits_window_only() -> None:
    (request,) = build_requests("s", _step("arxiv"), (("submittedDate", "[A TO B]"),))
    assert request.params == (("search_query", "submittedDate:[A TO B]"),)


def test_arxiv_without_anything_still_emits_one_request() -> None:
    (request,) = build_requests("s", _step("arxiv"), ())
    assert request.params == ()


def test_crossref_repeated_issn_fans_out_one_request_each() -> None:
    """重复键逐条展开：`as_params()` 的 last-wins 会静默丢掉 n-1 个刊。"""
    step = _step("crossref", ("issn", "0304-405X"), ("issn", "0022-1082"))
    window = (("from-pub-date", "2026-07-19"),)

    requests = build_requests("s", step, window)

    assert [request.params for request in requests] == [
        (("issn", "0304-405X"), ("from-pub-date", "2026-07-19")),
        (("issn", "0022-1082"), ("from-pub-date", "2026-07-19")),
    ]
    assert {request.since for request in requests} == {"2026-07-19"}


def test_nber_repeated_program_fans_out_and_has_no_window() -> None:
    step = _step("nber", ("program", "AP"), ("program", "CF"))

    requests = build_requests("s", step, ())

    assert [request.params for request in requests] == [(("program", "AP"),), (("program", "CF"),)]
    assert {request.since for request in requests} == {None}


def test_fanout_source_without_values_still_emits_one_request() -> None:
    requests = build_requests("s", _step("crossref"), (("from-pub-date", "2026-07-19"),))
    assert [request.params for request in requests] == [(("from-pub-date", "2026-07-19"),)]


def test_openalex_filters_are_merged_into_one_comma_joined_param() -> None:
    """openalex 的重复 `filter` 是 AND 关系——展开成两条请求会把它变成 OR。"""
    step = _step("openalex", ("filter", "concepts.id:C1"), ("filter", "type:preprint"))
    window = (("from_publication_date", "2026-07-19"),)

    (request,) = build_requests("s", step, window)

    assert request.params == (
        ("filter", "concepts.id:C1,type:preprint,from_publication_date:2026-07-19"),
    )
    assert request.since == "2026-07-19"


def test_openalex_without_filters_keeps_window_only() -> None:
    (request,) = build_requests("s", _step("openalex"), (("from_publication_date", "2026-07-19"),))
    assert request.params == (("filter", "from_publication_date:2026-07-19"),)


def test_openalex_with_no_params_at_all_emits_empty_request() -> None:
    (request,) = build_requests("s", _step("openalex"), ())
    assert request.params == ()


def test_s2_window_is_a_flat_parameter_with_range_suffix_stripped_for_since() -> None:
    step = _step("s2", ("venue", "JF"))
    (request,) = build_requests("s", step, (("publicationDateOrYear", "2026-07-19:"),))

    assert request.params == (("venue", "JF"), ("publicationDateOrYear", "2026-07-19:"))
    assert request.since == "2026-07-19"  # 单参数区间语法的尾冒号不属于日期


def test_ssrn_window_keeps_both_ends_flat() -> None:
    window = (("from-created-date", "2026-07-18"), ("until-created-date", "2026-07-26"))
    (request,) = build_requests("s", _step("ssrn"), window)

    assert request.params == window
    assert request.since == "2026-07-18"


def test_build_requests_rejects_unknown_source() -> None:
    with pytest.raises(CrawlerError) as excinfo:
        build_requests("s", _step("scholar"), ())
    assert excinfo.value.error_class is ErrorClass.CONFIG


def test_build_requests_carries_note_and_subscription_through() -> None:
    step = PlanStep(source="ssrn", note="ssrn 无下推")
    (request,) = build_requests("asset-pricing-wp", step, ())
    assert request.subscription == "asset-pricing-wp"
    assert request.note == "ssrn 无下推"


def test_compiled_plan_feeds_build_requests_end_to_end() -> None:
    """T2 编译产物直接喂 T5 合成器（两卡接缝的形状一致性）。"""
    subscription = parse_subscription(
        {
            "name": "wp",
            "sources": {"crossref": {"issns": ["0304-405X", "0022-1082"]}},
        }
    )
    plan = compile_subscription(subscription)
    requests = build_requests(plan.subscription, plan.steps[0], (("from-pub-date", "2026-07-19"),))
    assert len(requests) == 2


# ---------------------------------------------------------------------------
# AdapterFetcher
# ---------------------------------------------------------------------------


class _TwoIssueAdapter(AdapterBase):
    """最小 DISCOVER/ENUMERATE adapter：记录收到的 `since` 与 venue。"""

    adapter_id = "fake"
    family: AdapterFamily = "open_access"
    capabilities = Capability.DISCOVER | Capability.ENUMERATE
    default_rate = RatePolicy(600)
    auth_requirement = AuthLevel.NONE
    domains: tuple[str, ...] = ("fake.local",)

    def __init__(self) -> None:
        self.seen_since: list[str | None] = []
        self.seen_quirks: list[dict[str, object]] = []

    def discover_timeline(self, venue: VenueSpec, since: str | None = None) -> Iterable[IssueRef]:
        self.seen_since.append(since)
        self.seen_quirks.append(dict(venue.quirks))
        return [IssueRef(venue_id=venue.id, volume="1", number=str(n)) for n in (1, 2)]

    def enumerate_issue(self, venue: VenueSpec, issue: IssueRef) -> Iterable[PaperStub]:
        return [
            PaperStub(
                title=f"P{issue.number}",
                identifiers=(("doi", f"10.1/{venue.id}.{issue.number}"),),
            )
        ]


class _DatedAdapter(AdapterBase):
    """DISCOVER/ENUMERATE adapter：产出带 `pub_date` 的条目（客户端窗收窄的被测面）。"""

    adapter_id = "dated"
    family: AdapterFamily = "open_access"
    capabilities = Capability.DISCOVER | Capability.ENUMERATE
    default_rate = RatePolicy(600)
    auth_requirement = AuthLevel.NONE
    domains: tuple[str, ...] = ("dated.local",)

    def discover_timeline(self, venue: VenueSpec, since: str | None = None) -> Iterable[IssueRef]:
        del since
        return [IssueRef(venue_id=venue.id, volume="1", number="1", year=2026)]

    def enumerate_issue(self, venue: VenueSpec, issue: IssueRef) -> Iterable[PaperStub]:
        del venue, issue
        return [
            PaperStub(title="早于窗", identifiers=(("doi", "10.1/a"),), pub_date="2026-01-15"),
            PaperStub(title="窗内", identifiers=(("doi", "10.1/b"),), pub_date="2026-07-20"),
            PaperStub(title="窗下界当天", identifiers=(("doi", "10.1/c"),), pub_date="2026-07-19"),
            PaperStub(title="无日期", identifiers=(("doi", "10.1/d"),)),
        ]


def test_adapter_fetcher_drives_discover_then_enumerate() -> None:
    adapter = _TwoIssueAdapter()
    fetcher = AdapterFetcher({"crossref": adapter})
    request = SourceRequest(
        subscription="s", source="crossref", params=(("issn", "0304-405X"),), since="2026-07-19"
    )

    stubs = list(fetcher.fetch(request))

    assert [stub.title for stub in stubs] == ["P1", "P2"]
    assert adapter.seen_since == ["2026-07-19"]  # 增量窗下界经 DISCOVER 的 since= 传下去
    assert adapter.seen_quirks == [{"issn": "0304-405X"}]  # 请求参数落合成 venue 的 quirks


def test_deliverable_table_covers_every_dsl_source() -> None:
    """下达面表按源穷举——新增源忘了回答"参数能不能下达"会被这条抓住。"""
    from paper_crawler.subs.watch import _DELIVERABLE_PARAMS

    assert set(_DELIVERABLE_PARAMS) == set(SOURCE_FIELDS)


def test_crossref_issn_param_reaches_the_venue_identifiers() -> None:
    """P1-A#2：编译出的 issn 必须真的进请求——crossref adapter 读的是 identifiers.issn。"""
    fetcher = AdapterFetcher({"crossref": _TwoIssueAdapter()})
    spec = fetcher.venue_for(
        SourceRequest(subscription="s", source="crossref", params=(("issn", "0304-405X"),))
    )
    assert spec.identifiers["issn"] == ["0304-405X"]


def test_injected_venue_keeps_its_own_config_and_gains_the_request_params() -> None:
    """P1-A#2 回归：注入真实 venue 时**不再整份丢弃** params，且原对象不被改写。"""
    adapter = _TwoIssueAdapter()
    injected = VenueSpec(
        id="ssrn",
        kind="preprint_channel",
        names=VenueNames(full="SSRN"),
        field=["econ"],
        fulltext_source="ssrn",
        quirks={"topic_filter": "econ_fin"},
    )
    fetcher = AdapterFetcher({"ssrn": adapter}, venues={"ssrn": injected})

    request = SourceRequest(
        subscription="s", source="ssrn", params=(("from-created-date", "2026-07-18"),)
    )
    spec = fetcher.venue_for(request)

    assert spec is not injected  # 副本，不改 registry 共享的那份
    assert injected.quirks == {"topic_filter": "econ_fin"}
    assert spec.quirks == {"topic_filter": "econ_fin", "from-created-date": "2026-07-18"}
    list(fetcher.fetch(request))
    assert adapter.seen_quirks == [spec.quirks]


def test_undeliverable_params_warn_once_per_source(caplog: pytest.LogCaptureFixture) -> None:
    """下达不了的参数响亮降级（每源一条），而不是静默丢弃。"""
    fetcher = AdapterFetcher({"arxiv": _TwoIssueAdapter()})
    request = SourceRequest(
        subscription="s",
        source="arxiv",
        params=(("search_query", "cat:cs.AI AND submittedDate:[A TO B]"),),
        since=None,
    )
    with caplog.at_level(logging.WARNING, logger="paper_crawler"):
        list(fetcher.fetch(request))
        list(fetcher.fetch(request))

    warnings = [r for r in caplog.records if "无法下达" in r.getMessage()]
    assert len(warnings) == 1
    assert "search_query" in warnings[0].getMessage()


def test_deliverable_params_do_not_warn(caplog: pytest.LogCaptureFixture) -> None:
    fetcher = AdapterFetcher({"crossref": _TwoIssueAdapter()})
    with caplog.at_level(logging.WARNING, logger="paper_crawler"):
        list(
            fetcher.fetch(
                SourceRequest(subscription="s", source="crossref", params=(("issn", "1234-5678"),))
            )
        )
    assert [r for r in caplog.records if "无法下达" in r.getMessage()] == []


def test_result_side_window_narrowing_keeps_undated_entries() -> None:
    """P3-3 降级补偿：请求面退化为整年时，结果面按 since 收窄；无 pub_date 者保留。"""
    fetcher = AdapterFetcher({"crossref": _DatedAdapter()})
    request = SourceRequest(subscription="s", source="crossref", since="2026-07-19")

    titles = [stub.title for stub in fetcher.fetch(request)]

    assert titles == ["窗内", "窗下界当天", "无日期"]  # "早于窗"被丢；含端；缺日期保留


def test_no_since_means_no_narrowing() -> None:
    fetcher = AdapterFetcher({"crossref": _DatedAdapter()})
    stubs = fetcher.fetch(SourceRequest(subscription="s", source="crossref"))
    assert len(list(stubs)) == 4


def test_adapter_fetcher_rejects_unregistered_source() -> None:
    fetcher = AdapterFetcher({})
    with pytest.raises(CrawlerError) as excinfo:
        list(fetcher.fetch(SourceRequest(subscription="s", source="arxiv")))
    assert excinfo.value.error_class is ErrorClass.CONFIG


def test_synthesized_venue_id_is_registry_legal() -> None:
    """合成 spec 的 id 必须过 `VenueSpec` 的 `^[a-z][a-z0-9_]*$`（构造即校验）。"""
    spec = AdapterFetcher({}).venue_for(SourceRequest(subscription="s", source="openalex"))
    assert spec.id == "subs_openalex"
    assert spec.fulltext_source == "openalex"


# ---------------------------------------------------------------------------
# nber 专属 RSS fetcher + 路由（P1-B）
# ---------------------------------------------------------------------------


def _rss_client(recorder: list[str]) -> HttpClient:
    def handler(request: httpx.Request) -> httpx.Response:
        recorder.append(str(request.url))
        return httpx.Response(200, content=fixture_bytes("06_rss_program_cf_synth.xml"))

    return HttpClient(user_agent="PaperCrawler/test", transport=httpx.MockTransport(handler))


def test_nber_fetcher_uses_the_rss_channel_and_the_proxy_year() -> None:
    """走 `rss.discover_incremental`，且 `default_year=entry.fetch_year` 必须传（方案 c）。"""
    urls: list[str] = []
    fetcher = NberRssFetcher(_rss_client(urls), now=date(2026, 7, 26))

    stubs = list(
        fetcher.fetch(SourceRequest(subscription="s", source="nber", params=(("program", "CF"),)))
    )

    assert urls == ["https://back.nber.org/rss/newcf.xml"]  # 一 program 一 feed 一请求
    assert [stub.title for stub in stubs][:1] == ["Synthetic Capital Structure Adjustment Speeds"]
    years = [stub.year for stub in stubs]
    assert years[0] == 2026  # pub_date 派生（权威路径）
    assert all(year == 2026 for year in years)  # 缺/畸形 pubDate 者退回 proxy fetch_year
    assert dict(stubs[0].meta)["program"] == "CF"  # 日报分类轴的来源


def test_nber_fetcher_rejects_unknown_program_loudly() -> None:
    fetcher = NberRssFetcher(_rss_client([]))
    with pytest.raises(CrawlerError) as excinfo:
        list(
            fetcher.fetch(
                SourceRequest(subscription="s", source="nber", params=(("program", "NOPE"),))
            )
        )
    assert excinfo.value.error_class is ErrorClass.CONFIG


def test_routing_fetcher_sends_each_source_to_its_own_channel() -> None:
    calls: list[str] = []

    class _Recorder:
        def __init__(self, tag: str) -> None:
            self.tag = tag

        def fetch(self, request: SourceRequest) -> list[PaperStub]:
            calls.append(f"{self.tag}:{request.source}")
            return []

    router = RoutingFetcher({"nber": _Recorder("rss")}, _Recorder("adapter"))
    list(router.fetch(SourceRequest(subscription="s", source="nber")))
    list(router.fetch(SourceRequest(subscription="s", source="crossref")))

    assert calls == ["rss:nber", "adapter:crossref"]


# ---------------------------------------------------------------------------
# 退出码 / 日报路径 / 熔断简报
# ---------------------------------------------------------------------------


def _summary(**kwargs: object) -> RunSummary:
    base: dict[str, object] = {"subscription": "s", "started_at": "2026-07-26T00:00:00+00:00"}
    base.update(kwargs)
    return RunSummary(**base)  # type: ignore[arg-type]


def test_exit_code_is_zero_for_clean_runs() -> None:
    assert exit_code_for([_summary(new_count=3, ingested_count=3)]) == 0
    assert exit_code_for([]) == 0


def test_exit_code_three_for_truncated_without_failures() -> None:
    assert exit_code_for([_summary(outcome=WatchOutcome.TRUNCATED)]) == 3


def test_exit_code_one_when_any_source_failed_even_alongside_truncation() -> None:
    from paper_crawler.subs.types import FailureEvent

    summaries = [
        _summary(outcome=WatchOutcome.TRUNCATED),
        _summary(failures=(FailureEvent(source="s2", error_class="transient", message="boom"),)),
    ]
    assert exit_code_for(summaries) == 1


def test_daily_report_path_shape() -> None:
    assert daily_report_path(date(2026, 7, 26), root=Path("/tmp/r")) == Path(
        "/tmp/r/daily-2026-07-26.md"
    )
    assert daily_report_path(date(2026, 7, 26)).name == "daily-2026-07-26.md"


def test_overload_brief_is_none_unless_truncated() -> None:
    assert overload_brief(_summary()) is None


def test_overload_brief_reports_the_dominant_axis() -> None:
    entries = tuple(
        ReportEntry(title=f"T{i}", source="arxiv", categories=("cs.AI",)) for i in range(3)
    )
    brief = overload_brief(
        _summary(outcome=WatchOutcome.TRUNCATED, entries=entries, new_count=3, guard_limit=2)
    )
    assert brief is not None
    assert "arxiv" in brief
