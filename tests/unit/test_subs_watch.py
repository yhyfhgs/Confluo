"""watch 编排的纯逻辑面（Phase 6 T5）：请求合成、adapter 接缝、退出码、日报路径。

带 DB 的端到端四场景在 `tests/integration/test_subs_watch_e2e.py`（mock_platform 载体），
CLI 层在 `tests/integration/test_cli_subs_watch.py`。本文件只测不需要 sqlite 的部分。
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx
import pytest

from helpers import make_ssrn_venue
from helpers.arxiv_fixtures import fixture_bytes as arxiv_fixture_bytes
from helpers.nber_fixtures import fixture_bytes
from helpers.ssrn_fixtures import fixture_bytes as ssrn_fixture_bytes
from paper_crawler.adapter import AdapterBase, AdapterFamily
from paper_crawler.adapters.arxiv.adapter import ArxivAdapter
from paper_crawler.adapters.ssrn.adapter import SsrnAdapter
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
from paper_crawler.subs.watermark import (
    DEFAULT_INITIAL_LOOKBACK_DAYS,
    DateUpperBound,
    Watermark,
    strategy_for,
    window_params,
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
    """arxiv 的 submittedDate 不是独立参数——有 query 时必须并进同一个 search_query。"""
    step = _step("arxiv", ("search_query", '(ti:"agent" OR abs:"agentic")'))
    window = (("submittedDate", "[202607190000 TO 202607262359]"),)

    (request,) = build_requests("s", step, window)

    assert request.params == (
        (
            "search_query",
            '(ti:"agent" OR abs:"agentic") AND submittedDate:[202607190000 TO 202607262359]',
        ),
    )
    # F7：窗值同时解回 ISO 下界喂 DISCOVER 的 since=（此前恒 None → adapter 从 venue 的
    # quirks.inception=1998-01 起枚举 → 被 arXiv OAI 以 badArgument 确定性拒绝）。
    assert request.since == "2026-07-19"


def test_arxiv_window_without_query_rides_since_only_not_a_fake_param() -> None:
    """无 `search_query` 时窗**不再**单独合成一个 search_query 条目（语义自本卡起反转）。

    窗真实生效的两条通道是 `SourceRequest.since`（→ `discover_timeline` 月桶）与结果面
    `_within_since` 收窄。把窗硬造成一个必然"无法下达"的参数，只会对 8 个纯分类预置
    每轮制造一条假警报——F7 立的规矩是"响亮降级不撒谎"，假警报同样是撒谎。
    """
    window = (("submittedDate", "[202607190000 TO 202607262359]"),)
    (request,) = build_requests("s", _step("arxiv"), window)
    assert request.params == ()
    assert request.since == "2026-07-19"


def test_arxiv_categories_fan_out_one_request_each_with_a_derived_set() -> None:
    """逐分类展开：每条请求成对带 `arxiv_category` + 派生 `arxiv_set`，`since` 同值。

    成对是硬要求（见 `_compose_arxiv` docstring）：注入 venue 的静态 `arxiv_set` 会在
    `venue_for` 的 quirks 合并中存活，只推分类名会让跨 archive 的分类恒空。
    """
    step = _step(
        "arxiv",
        ("arxiv_category", "cs.AI"),
        ("arxiv_category", "cs.LG"),
        ("arxiv_category", "cs.CL"),
    )
    window = (("submittedDate", "[202607190000 TO 202607262359]"),)

    requests = build_requests("s", step, window)

    assert [request.params for request in requests] == [
        (("arxiv_category", "cs.AI"), ("arxiv_set", "cs")),
        (("arxiv_category", "cs.LG"), ("arxiv_set", "cs")),
        (("arxiv_category", "cs.CL"), ("arxiv_set", "cs")),
    ]
    assert {request.since for request in requests} == {"2026-07-19"}


def test_arxiv_set_is_derived_from_the_archive_segment_of_the_category() -> None:
    """派生式与 `adapters/arxiv/adapter.py::_oai_target` 的兜底同式（含连字符 archive）。"""
    step = _step("arxiv", ("arxiv_category", "q-fin.PR"), ("arxiv_category", "cs.AI"))

    requests = build_requests("s", step, ())

    assert [request.params for request in requests] == [
        (("arxiv_category", "q-fin.PR"), ("arxiv_set", "q-fin")),
        (("arxiv_category", "cs.AI"), ("arxiv_set", "cs")),
    ]


def test_arxiv_fanout_carries_the_same_windowed_query_on_every_request() -> None:
    """分类 + query 并存：每条 fan-out 请求都带**同一份**"query AND 窗"的 search_query。"""
    step = _step(
        "arxiv",
        ("arxiv_category", "cs.AI"),
        ("arxiv_category", "cs.MA"),
        ("search_query", '(ti:"agent")'),
    )
    window = (("submittedDate", "[202607190000 TO 202607262359]"),)

    requests = build_requests("s", step, window)

    windowed = '(ti:"agent") AND submittedDate:[202607190000 TO 202607262359]'
    assert [request.params for request in requests] == [
        (("arxiv_category", "cs.AI"), ("arxiv_set", "cs"), ("search_query", windowed)),
        (("arxiv_category", "cs.MA"), ("arxiv_set", "cs"), ("search_query", windowed)),
    ]


def test_arxiv_query_without_categories_stays_a_single_request() -> None:
    """零分类退化为单条（恒至少一条请求，零请求 = 静默不拉该源）。"""
    step = _step("arxiv", ("search_query", '(ti:"agent")'))
    (request,) = build_requests("s", step, ())
    assert request.params == (("search_query", '(ti:"agent")'),)


def test_arxiv_since_is_the_watermark_lower_bound_itself() -> None:
    """跨模块契约：T4 产的窗 → T5 解出的 `since` == `DateUpperBound.lower_bound`。

    两侧都从**真实** watermark 件取值（不写死字符串）：窗值形态若在 T4 侧改了，这条
    会立刻红，而不是等到线上再被服务端拒绝一次。
    """
    day = date(2026, 7, 26)
    strategy = strategy_for("arxiv")
    assert isinstance(strategy, DateUpperBound)
    window = window_params(Watermark(), "arxiv", now=day)  # 空 watermark = 首跑

    (request,) = build_requests("s", _step("arxiv"), window)

    assert request.since == strategy.lower_bound(None, now=day).isoformat()
    assert request.since == "2026-07-19"  # 首跑 = 今天 − DEFAULT_INITIAL_LOOKBACK_DAYS(7)


def test_arxiv_window_of_unknown_shape_is_rejected_loudly() -> None:
    """形态认不出 → CONFIG，**不**退回 None：那条静默路径正是 F7 修掉的 bug 本身。"""
    with pytest.raises(CrawlerError) as excinfo:
        build_requests("s", _step("arxiv"), (("submittedDate", "[A TO B]"),))
    assert excinfo.value.error_class is ErrorClass.CONFIG


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
        params=(("search_query", 'ti:"agent" AND submittedDate:[A TO B]'),),
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


def test_ssrn_result_side_window_is_skipped_because_the_axis_differs() -> None:
    """ssrn 豁免结果面收窄：窗轴是 `created`（登记），`pub_date` 是 `published`（刊期）。

    错轴比较会把"本周登记、刊期挂在更早"的 SSRN 记录整批丢掉——窗已在正确的轴上服务端
    下推（`quirks.from/until-created-date`），这一层既冗余又有害。
    """
    fetcher = AdapterFetcher({"ssrn": _DatedAdapter()})
    request = SourceRequest(subscription="s", source="ssrn", since="2026-07-19")

    titles = [stub.title for stub in fetcher.fetch(request)]

    assert titles == ["早于窗", "窗内", "窗下界当天", "无日期"]  # 一条都不丢


def test_arxiv_undeliverable_warning_does_not_claim_a_local_fallback(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """arxiv 的 search_query 既没下推也**没有**本地补偿谓词——WARNING 不许说"本地兜底"。

    分类修复后本条同时锁住"不误报"的一侧：fan-out 的两个键**是**能下达的，故 dropped
    列表只许有 `search_query`，文案也不许再提"分类组"（那会变成假警报）。
    """
    fetcher = AdapterFetcher({"arxiv": _TwoIssueAdapter()})
    request = SourceRequest(
        subscription="s",
        source="arxiv",
        params=(
            ("arxiv_category", "cs.AI"),
            ("arxiv_set", "cs"),
            ("search_query", '(ti:"agent")'),
        ),
        since="2026-07-19",
    )
    with caplog.at_level(logging.WARNING, logger="paper_crawler"):
        list(fetcher.fetch(request))

    (warning,) = [r for r in caplog.records if "无法下达" in r.getMessage()]
    message = warning.getMessage()
    assert "无本地补偿谓词" in message
    assert "其余条件由本地过滤兜底" not in message
    assert "分类组" not in message  # 分类现在真的生效了，再提它就是假警报
    # dropped 列表逐字：只有 search_query——两个 fan-out 键不被误报成"下达不了"。
    assert "编译产物参数 ['search_query'] 无法下达" in message


def test_ssrn_window_params_no_longer_warn_as_undeliverable(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """F7 后 ssrn 的日窗**是**能下达的（经 quirks → 内部 crossref filter），不再降级告警。"""
    fetcher = AdapterFetcher({"ssrn": _TwoIssueAdapter()})
    window = window_params(Watermark(), "ssrn", now=date(2026, 7, 26))
    with caplog.at_level(logging.WARNING, logger="paper_crawler"):
        list(fetcher.fetch(SourceRequest(subscription="s", source="ssrn", params=window)))
    assert [r for r in caplog.records if "无法下达" in r.getMessage()] == []


# ---------------------------------------------------------------------------
# 真实 adapter 上的两条在线可用性接缝（F7；MockTransport 零网络，断言发出的 URL）
# ---------------------------------------------------------------------------


_UA = "PaperCrawler/test (personal research; mailto:test@example.com)"


def _mock_client(handler: Callable[[httpx.Request], httpx.Response]) -> HttpClient:
    return HttpClient(user_agent=_UA, transport=httpx.MockTransport(handler))


def _arxiv_cs_ai_venue() -> VenueSpec:
    """逐字对齐 `venues/preprint/arxiv-cs-ai.yaml` 的 quirks（1998 起点即出自这里）。"""
    return VenueSpec(
        id="arxiv_cs_ai",
        kind="preprint_channel",
        names=VenueNames(full="arXiv cs.AI · Artificial Intelligence"),
        field=["cs_ai"],
        metadata_source="arxiv",
        fulltext_source="arxiv",
        quirks={"inception": "1998-01", "arxiv_set": "cs", "arxiv_category": "cs.AI"},
    )


def _months_spanned(lower: date, upper: date) -> set[str]:
    """`[lower, upper]` 触及的月首日集合（月桶粒度的期望值，随真实时钟变动）。"""
    months = {f"{lower:%Y-%m}-01"}
    months.add(f"{upper:%Y-%m}-01")
    return months


def test_arxiv_since_narrows_the_oai_window_to_the_watermark_month() -> None:
    """F7 ①：DISCOVER 的 `since` 真的收窄了 OAI 的 `from=`——不再从 1998-01 起枚举。

    修复前实测：`from=1998-01-01&until=1998-01-31` 被 arXiv 官方 OAI-PMH 以
    `badArgument`/"start date too early" 确定性拒绝（`docs/testing/records/
    2026-07-26-ac6-acceptance.md` §4.1），任何含 arxiv 源的订阅恒失败。
    """
    captured: list[httpx.URL] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request.url)
        return httpx.Response(200, content=arxiv_fixture_bytes("10_oai_norecordsmatch.xml"))

    # 桶上界走 adapter 内部的真实时钟（`discover_timeline` 的 `until`），故窗也用真实时钟取。
    today = datetime.now(UTC).date()
    window = window_params(Watermark(), "arxiv", now=today)
    (request,) = build_requests("llm-agents", _step("arxiv"), window)
    fetcher = AdapterFetcher(
        {"arxiv": ArxivAdapter(http=_mock_client(handler))},
        venues={"arxiv": _arxiv_cs_ai_venue()},
    )

    list(fetcher.fetch(request))

    lower = today - timedelta(days=DEFAULT_INITIAL_LOOKBACK_DAYS)
    expected = _months_spanned(lower, today)
    assert {str(url.params.get("from")) for url in captured} == expected  # 只有窗触及的月桶
    assert len(captured) == len(expected)
    assert all(url.params.get("set") == "cs" for url in captured)
    assert "1998-01-01" not in {str(url.params.get("from")) for url in captured}
    # 对照：不给 since 时同一 venue 会产出三百多个月桶（= 修复前每次首跑的请求面）。
    unbounded = list(ArxivAdapter().discover_timeline(_arxiv_cs_ai_venue(), None))
    assert len(unbounded) > 300 and unbounded[0].label == "1998-01"


def test_arxiv_fanout_params_override_the_injected_venue_static_quirks() -> None:
    """关键陷阱的直接回归：**成对**下推才压得过注入 venue 的静态 `arxiv_set`。

    `_arxiv_cs_ai_venue()` 静态声明 `arxiv_set: cs` / `arxiv_category: cs.AI`，而
    `venue_for` 的合并是 `{**existing.quirks, **params}`——只推 `arxiv_category=q-fin.PR`
    的话静态 `cs` 会存活，`_oai_target` 就成了"在 set=cs 里按 q-fin.PR 客户端过滤"，
    跨 archive 的分类恒空。故 `_compose_arxiv` 必须把派生的 set 一并推下去。
    """
    fetcher = AdapterFetcher({"arxiv": ArxivAdapter()}, venues={"arxiv": _arxiv_cs_ai_venue()})
    request = SourceRequest(
        subscription="asset-pricing",
        source="arxiv",
        params=(("arxiv_category", "q-fin.PR"), ("arxiv_set", "q-fin")),
    )

    spec = fetcher.venue_for(request)

    assert spec.quirks["arxiv_set"] == "q-fin"  # 压过静态 cs
    assert spec.quirks["arxiv_category"] == "q-fin.PR"  # 压过静态 cs.AI
    assert _arxiv_cs_ai_venue().quirks["arxiv_set"] == "cs"  # 原 spec 未被改写


def test_arxiv_fanout_reaches_the_real_oai_set_of_a_cross_archive_category() -> None:
    """端到端接缝：fan-out 参数 → 真实 `ArxivAdapter` 发出的 OAI URL 带 `set=q-fin`。

    生产路径注入的恒是 `arxiv_cs_ai`（`cli._watch_source_venues` 按 id 序取首个），本测
    正是那条路径：venue 给 cs、订阅给 q-fin.PR，最终请求面必须是订阅说了算。
    """
    captured: list[httpx.URL] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request.url)
        return httpx.Response(200, content=arxiv_fixture_bytes("10_oai_norecordsmatch.xml"))

    today = datetime.now(UTC).date()
    window = window_params(Watermark(), "arxiv", now=today)
    requests = build_requests(
        "asset-pricing", _step("arxiv", ("arxiv_category", "q-fin.PR")), window
    )
    fetcher = AdapterFetcher(
        {"arxiv": ArxivAdapter(http=_mock_client(handler))},
        venues={"arxiv": _arxiv_cs_ai_venue()},
    )

    for request in requests:
        list(fetcher.fetch(request))

    assert captured  # 确有请求发出（fixture 回 noRecordsMatch，故结果为空但 URL 已成形）
    assert {str(url.params.get("set")) for url in captured} == {"q-fin"}
    assert "cs" not in {str(url.params.get("set")) for url in captured}


def test_ssrn_day_window_reaches_the_crossref_filter_and_trims_the_year_buckets() -> None:
    """F7 ②：ssrn 的 7 天窗 → crossref `filter=` 日窗 + 只产窗口触及的年桶（1 次请求）。

    修复前：年桶照产、`filter` 退化成整年（实测 `prefix:10.2139` 2026 全年 155,461 条）。
    """
    captured: list[httpx.URL] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request.url)
        return httpx.Response(200, content=ssrn_fixture_bytes("02_works_empty.json"))

    day = date(2026, 7, 26)
    window = window_params(Watermark(), "ssrn", now=day)
    (request,) = build_requests("asset-pricing", _step("ssrn"), window)
    adapter = SsrnAdapter(
        http=_mock_client(handler), clock=lambda: datetime(2026, 7, 26, tzinfo=UTC)
    )
    fetcher = AdapterFetcher({"ssrn": adapter}, venues={"ssrn": make_ssrn_venue()})

    list(fetcher.fetch(request))

    assert len(captured) == 1  # 年桶只剩 2026 一个（since=2026-07-19），整年翻页没了
    assert captured[0].path == "/prefixes/10.2139/works"
    assert captured[0].params.get("filter") == (
        "from-created-date:2026-07-19,until-created-date:2026-07-26"
    )


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
