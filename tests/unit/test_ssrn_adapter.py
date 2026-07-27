"""ssrn/adapter.py 单测（MockTransport 注入，零真实网络；ssrn.md §4 + 发现①仲裁令）。

覆盖：
- DISCOVER 纯生成年桶（clock 注入上界 + since 下界 + 越界钳制 + 非法 since CONFIG +
  **零网络**：discover 不发任何请求）。
- ENUMERATE 委内部 crossref（prefix 10.2139 + created URL 形态）+ 后处理增补 (ssrn) id
  （混两类型全收 / 护栏 skipped_non_ssrn obslog + 丢弃 / cursor 两页 / 空窗）。
- RESOLVE landing-only（返 [] + 落 landing 观测；ssrn id / DOI 回退 / 缺失 CONFIG）。
- healthcheck（golden 匹配态 [LIVE 2026-07-24 双源转正] / drift / 未收录 / 不可达；
  经 crossref lookup 打 api.crossref.org）。
- HttpClient 注入转发内部 crossref。
- **AC-5.1a③ 零 SSRN 接触**：全生命周期 MockTransport 记录请求域，断言无 `*.ssrn.com`。
- **AC-5.1a① 7 收割日回放**：重叠窗 + created 延迟注入 → (ssrn) 主键去重无重复无遗漏。
- **§4.4 净效果**：unpaywall SSRN landing-only 响应 → UnpaywallAdapter.resolve 返 []（PDF≈0）。
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

import httpx
import pytest

from helpers import make_ssrn_venue
from helpers.ssrn_fixtures import fixture_bytes, fixture_json, works_page_bytes
from paper_crawler.adapters.crossref.adapter import CrossrefAdapter
from paper_crawler.adapters.ssrn import parse
from paper_crawler.adapters.ssrn.adapter import SsrnAdapter
from paper_crawler.adapters.unpaywall.adapter import UnpaywallAdapter
from paper_crawler.browserfetch import BrowserContextResolver, PageResponse
from paper_crawler.errors import Challenged, CrawlerError, ErrorClass
from paper_crawler.http import HttpClient
from paper_crawler.types import (
    AssetKind,
    AssetPlan,
    AuthLevel,
    Capability,
    IssueRef,
    PaperStub,
    UrlStrategy,
    VenueSpec,
)

_UA = "PaperCrawler/test (personal research; mailto:test@example.com)"
_CLOCK_2026 = lambda: datetime(2026, 7, 24, tzinfo=UTC)  # noqa: E731 (fixed test clock)
Handler = Callable[[httpx.Request], httpx.Response]


def _adapter(handler: Handler, *, clock: Callable[[], datetime] | None = None) -> SsrnAdapter:
    client = HttpClient(user_agent=_UA, transport=httpx.MockTransport(handler))
    return SsrnAdapter(http=client, clock=clock or _CLOCK_2026)


def _resp(body: bytes, status: int = 200) -> httpx.Response:
    return httpx.Response(status, content=body)


def _never(_request: httpx.Request) -> httpx.Response:
    raise AssertionError("no network expected on this path (discover=pure-gen / resolve=offline)")


def _venue(**overrides: object) -> VenueSpec:
    return make_ssrn_venue(**overrides)


# --- DISCOVER（纯生成零网络年桶；controller 发现①仲裁令）------------------------------------


def test_discover_pure_generation_1990_to_clock_year() -> None:
    """纯生成 1990..今年（clock 注入上界）；零网络（_never handler 不被调用）。"""
    issues = list(_adapter(_never).discover_timeline(_venue()))
    assert issues[0].year == 1990
    assert issues[-1].year == 2026  # clock=2026
    assert [i.label for i in issues[:2]] == ["1990", "1991"]
    assert all(i.paper_count_claimed is None for i in issues)  # 规模锚移交 M1 census
    assert all(i.venue_id == "ssrn" for i in issues)


def test_discover_no_dirty_future_years() -> None:
    """脏未来年（2077/2103/2104）天然不产（上界=今年截断，§4.3 + 发现①仲裁令）。"""
    years = {i.year for i in _adapter(_never).discover_timeline(_venue())}
    assert 2077 not in years and 2103 not in years and 2104 not in years
    assert max(years) == 2026


def test_discover_since_narrows_lower_bound() -> None:
    issues = list(_adapter(_never).discover_timeline(_venue(), since="2020"))
    assert issues[0].year == 2020
    assert issues[-1].year == 2026


def test_discover_since_below_inception_clamped_to_1990() -> None:
    """since 早于 1990 起点 → 钳到 1990（§4.3 下界）。"""
    issues = list(_adapter(_never).discover_timeline(_venue(), since="1975"))
    assert issues[0].year == 1990


def test_discover_since_full_date_prefix_accepted() -> None:
    issues = list(_adapter(_never).discover_timeline(_venue(), since="2024-03-01"))
    assert issues[0].year == 2024


def test_discover_invalid_since_raises_config() -> None:
    with pytest.raises(CrawlerError) as exc:
        list(_adapter(_never).discover_timeline(_venue(), since="not-a-year"))
    assert exc.value.error_class is ErrorClass.CONFIG


# --- ENUMERATE（委 crossref prefix+created + 后处理增补 (ssrn) id）--------------------------


def test_enumerate_url_delegates_prefix_10_2139_created_filter() -> None:
    """委内部 crossref → /prefixes/10.2139/works + from/until-created-date（§4.2 消费契约）。"""
    captured: list[httpx.URL] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request.url)
        return _resp(fixture_bytes("02_works_empty.json"))

    list(_adapter(handler).enumerate_issue(_venue(), IssueRef(venue_id="ssrn", year=2024)))
    url = captured[0]
    assert url.host == "api.crossref.org"
    assert url.path == "/prefixes/10.2139/works"
    assert url.params.get("filter") == "from-created-date:2024-01-01,until-created-date:2024-12-31"
    assert url.params.get("cursor") == "*"


def test_enumerate_day_window_quirk_is_pushed_down_to_the_crossref_filter() -> None:
    """F7：venue quirks 带日窗（订阅 watch 注入）→ 内部 crossref 的 filter 收到日粒度窗。

    没有这条通道时 7 天 watch 窗会退化成 `prefix:10.2139` 的整年枚举（实测 2026 全年
    155,461 条，`docs/testing/records/2026-07-26-ac6-acceptance.md` §4.2）。
    """
    captured: list[httpx.URL] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request.url)
        return _resp(fixture_bytes("02_works_empty.json"))

    venue = _venue(**{"from-created-date": "2026-07-19", "until-created-date": "2026-07-26"})
    list(_adapter(handler).enumerate_issue(venue, IssueRef(venue_id="ssrn", year=2026)))

    assert len(captured) == 1
    assert captured[0].params.get("filter") == (
        "from-created-date:2026-07-19,until-created-date:2026-07-26"
    )


def test_enumerate_year_bucket_outside_the_day_window_makes_zero_requests() -> None:
    """窗未触及的年桶零请求——年桶粒度与日窗的差额不该变成一整年的翻页。"""
    venue = _venue(**{"from-created-date": "2026-07-19", "until-created-date": "2026-07-26"})
    stubs = list(_adapter(_never).enumerate_issue(venue, IssueRef(venue_id="ssrn", year=2025)))
    assert stubs == []


def test_enumerate_mixed_types_both_collected_and_augmented() -> None:
    """混 journal-article + posted-content 两类型全收（不加 type: 过滤）；均增补 (ssrn) id。"""
    stubs = list(
        _adapter(lambda r: _resp(fixture_bytes("01_works_mixed_types.json"))).enumerate_issue(
            _venue(), IssueRef(venue_id="ssrn", year=2024)
        )
    )
    assert len(stubs) == 2
    # DOI 锚点保留 + 增补 (ssrn, abstract_id)（下载主键）。
    assert stubs[0].identifiers == (("doi", "10.2139/ssrn.4056799"), ("ssrn", "4056799"))
    assert stubs[1].identifiers == (("doi", "10.2139/ssrn.5001234"), ("ssrn", "5001234"))


def test_enumerate_guardrail_drops_non_ssrn_and_logs_skipped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """护栏：非 ssrn. 中缀 10.2139 DOI → 不增补 + 丢弃 + 计 skipped_non_ssrn 观测（§4.2/§6.1）。"""
    events: list[dict[str, object]] = []
    monkeypatch.setattr(
        "paper_crawler.adapters.ssrn.adapter.log_event",
        lambda level, msg, **extra: events.append({"msg": msg, **extra}),
    )
    stubs = list(
        _adapter(lambda r: _resp(fixture_bytes("03_works_guardrail.json"))).enumerate_issue(
            _venue(), IssueRef(venue_id="ssrn", year=2024)
        )
    )
    # 2 合法 ssrn（增补）+ 1 非-ssrn（丢弃）。
    assert [parse.ssrn_id_of_stub(s) for s in stubs] == ["4056799", "7654321"]
    skip_events = [
        e for e in events if e["msg"] == "ssrn non-ssrn dois skipped (prefix 10.2139 guardrail)"
    ]
    assert len(skip_events) == 1
    assert skip_events[0]["skipped_non_ssrn"] == 1
    assert skip_events[0]["venue"] == "ssrn"


def test_enumerate_no_skip_event_when_all_ssrn(monkeypatch: pytest.MonkeyPatch) -> None:
    """全 ssrn DOI → 不落 skipped_non_ssrn 观测（护栏计数为 0 时静默）。"""
    events: list[str] = []
    monkeypatch.setattr(
        "paper_crawler.adapters.ssrn.adapter.log_event",
        lambda level, msg, **extra: events.append(msg),
    )
    list(
        _adapter(lambda r: _resp(fixture_bytes("01_works_mixed_types.json"))).enumerate_issue(
            _venue(), IssueRef(venue_id="ssrn", year=2024)
        )
    )
    assert "ssrn non-ssrn dois skipped (prefix 10.2139 guardrail)" not in events


def test_enumerate_cursor_two_page_continuation() -> None:
    """cursor 深翻：page1（next-cursor 非空）→ 续 02 空页终止（§4.2 沿 crossref 契约）。"""
    responses = iter(["04a_works_cursor_page1.json", "02_works_empty.json"])

    def handler(request: httpx.Request) -> httpx.Response:
        return _resp(fixture_bytes(next(responses)))

    stubs = list(_adapter(handler).enumerate_issue(_venue(), IssueRef(venue_id="ssrn", year=2024)))
    assert [parse.ssrn_id_of_stub(s) for s in stubs] == ["3000001", "3000002"]


def test_enumerate_empty_window_yields_nothing() -> None:
    stubs = list(
        _adapter(lambda r: _resp(fixture_bytes("02_works_empty.json"))).enumerate_issue(
            _venue(), IssueRef(venue_id="ssrn", year=2024)
        )
    )
    assert stubs == []


# --- RESOLVE（零网络：landing 观测 + 模式 B RENDER_PAGE 计划，§4.4/T11）----------------------


def test_resolve_returns_render_page_plan_and_logs_landing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """模式 B：产一个 `RENDER_PAGE` `AssetPlan`（url=landing 引用，非 volatile Delivery.cfm）
    + 落 landing 观测（纯串，不请求，§4.4 持久化纪律）。"""
    events: list[dict[str, object]] = []
    monkeypatch.setattr(
        "paper_crawler.adapters.ssrn.adapter.log_event",
        lambda level, msg, **extra: events.append({"msg": msg, **extra}),
    )
    paper = PaperStub(
        title="WP", identifiers=(("doi", "10.2139/ssrn.4056799"), ("ssrn", "4056799"))
    )
    plans = _adapter(_never).resolve_assets(_venue(), paper)

    assert len(plans) == 1
    plan = plans[0]
    assert plan.kind is AssetKind.PDF
    assert plan.url == "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4056799"
    assert plan.url_strategy is UrlStrategy.RENDER_PAGE
    assert plan.auth_needed is AuthLevel.FREE_ACCOUNT
    assert plan.expected_type == "application/pdf"

    landing_events = [e for e in events if e["msg"].startswith("ssrn render_page plan")]
    assert len(landing_events) == 1
    assert landing_events[0]["abstract_id"] == "4056799"
    assert landing_events[0]["ssrn_landing_url"] == plan.url


def test_resolve_derives_abstract_id_from_doi_when_no_ssrn_id() -> None:
    """外部直接 resolve（只带 DOI，无 (ssrn) id）→ 由 DOI 抽取 abstract_id 构造计划（不抛）。"""
    paper = PaperStub(title="WP", identifiers=(("doi", "10.2139/ssrn.7654321"),))
    plans = _adapter(_never).resolve_assets(_venue(), paper)
    assert len(plans) == 1
    assert plans[0].url == "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=7654321"


def test_resolve_missing_ssrn_identity_raises_config() -> None:
    """无 (ssrn) id 且非 ssrn DOI（路由缺陷）→ CONFIG 响亮。"""
    paper = PaperStub(title="X", identifiers=(("doi", "10.1038/nature14539"),))
    with pytest.raises(CrawlerError) as exc:
        _adapter(_never).resolve_assets(_venue(), paper)
    assert exc.value.error_class is ErrorClass.CONFIG


def test_resolve_plan_is_produced_regardless_of_any_config() -> None:
    """adapter 侧不做任何 browser-fetch 开关判定（D-029 案 A"能力面恰好等于合规面"）——
    门控(`[browserfetch].enabled` + `--browser`)全在 stages 层；本层恒产计划，交 stages
    的既有三级门在 config 关闭时拦为 `skipped`（fixture 层面只需锁"计划恒存在"）。
    """
    paper = PaperStub(
        title="WP", identifiers=(("doi", "10.2139/ssrn.4056799"), ("ssrn", "4056799"))
    )
    plans = _adapter(_never).resolve_assets(_venue(), paper)
    assert len(plans) == 1
    assert plans[0].url_strategy is UrlStrategy.RENDER_PAGE


def test_capabilities_include_fetch_for_mode_b() -> None:
    """D-030/design/11 §12 裁决①：FETCH 随模式 B 点亮（经 browser-fetch 横切件执行）。"""
    adapter = _adapter(_never)
    assert Capability.FETCH in adapter.capabilities
    assert Capability.DISCOVER in adapter.capabilities
    assert Capability.ENUMERATE in adapter.capabilities
    assert Capability.RESOLVE in adapter.capabilities
    assert Capability.SEARCH not in adapter.capabilities


# --- 模式 B 同批解析（design/11 §4.4 生产端；假 handle，零浏览器零网络）---------------------


class _FakeHandle:
    """假 `BrowserFetchHandle`：按 URL 返响应 + 记调用序列（同批/停手判据载体）。"""

    def __init__(self, response: PageResponse) -> None:
        self.response = response
        self.calls: list[str] = []

    def goto(self, url: str) -> PageResponse:
        self.calls.append(f"goto:{url}")
        return self.response

    def download_via(self, trigger: object, dest: object) -> int:  # pragma: no cover - 不该被调
        raise AssertionError("resolve 闭包不得触发下载")

    def close(self) -> None:  # pragma: no cover - 生命周期归 fetch_one
        raise AssertionError("resolve 闭包不得关闭上下文")


_LANDING_URL = "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4056799"
_DELIVERY_HREF = "Delivery.cfm/SSRN_ID4056799_code1.pdf?abstractid=4056799&mirid=1"


def _landing_page(body: bytes, *, status: int = 200, headers: dict[str, str] | None = None):  # type: ignore[no-untyped-def]
    return PageResponse(
        status=status,
        headers=headers if headers is not None else {"content-type": "text/html"},
        final_url=_LANDING_URL,
        body=body,
    )


def _landing_plan() -> AssetPlan:
    return AssetPlan(
        kind=AssetKind.PDF,
        url=_LANDING_URL,
        url_strategy=UrlStrategy.RENDER_PAGE,
        auth_needed=AuthLevel.FREE_ACCOUNT,
    )


def test_resolve_in_browser_context_returns_volatile_plan() -> None:
    """同 handle 打开 landing → 读出 `Delivery.cfm` href → 产 volatile 计划（其余字段不变）。"""
    handle = _FakeHandle(_landing_page(f"<a href='{_DELIVERY_HREF}'>Download</a>".encode()))
    plan = _landing_plan()

    volatile = _adapter(_never).resolve_in_browser_context(plan, handle)  # type: ignore[arg-type]

    assert handle.calls == [f"goto:{_LANDING_URL}"]  # 恰好一跳，且在同一 handle 上
    assert volatile.url == f"https://papers.ssrn.com/sol3/{_DELIVERY_HREF}"
    assert volatile.url_strategy is UrlStrategy.RENDER_PAGE  # fetch_one 会再校一次
    assert volatile.auth_needed is AuthLevel.FREE_ACCOUNT
    assert plan.url == _LANDING_URL  # 入参计划不被就地改（volatile 只活在返回值/栈上）


def test_resolve_in_browser_context_challenge_stops_immediately() -> None:
    """landing 命中风控 → `Challenged` 停手（**判定不能少一跳**，否则 challenge 被静默降级）。"""
    handle = _FakeHandle(_landing_page(b"403", status=403, headers={"cf-mitigated": "challenge"}))
    with pytest.raises(Challenged):
        _adapter(_never).resolve_in_browser_context(_landing_plan(), handle)  # type: ignore[arg-type]
    assert handle.calls == [f"goto:{_LANDING_URL}"]


def test_resolve_in_browser_context_no_entitlement_verdict_maps_to_error() -> None:
    """判定器判无权限 → `CrawlerError(NO_ENTITLEMENT)`（闭包返回类型无法表达"无权限"）。"""
    handle = _FakeHandle(_landing_page(b"<html>Get access to this paper</html>"))
    with pytest.raises(CrawlerError) as exc:
        _adapter(_never).resolve_in_browser_context(_landing_plan(), handle)  # type: ignore[arg-type]
    assert exc.value.error_class is ErrorClass.NO_ENTITLEMENT
    assert exc.value.detail == "ssrn_landing_no_entitlement"


def test_resolve_in_browser_context_without_delivery_link_is_no_entitlement() -> None:
    """页面正常但无下载链接 → `no_entitlement` + 可读 detail（**不猜 URL**，红线 4）。"""
    handle = _FakeHandle(_landing_page(b"<html><h1>WP</h1><p>abstract only</p></html>"))
    with pytest.raises(CrawlerError) as exc:
        _adapter(_never).resolve_in_browser_context(_landing_plan(), handle)  # type: ignore[arg-type]
    assert exc.value.error_class is ErrorClass.NO_ENTITLEMENT
    assert exc.value.detail == "ssrn_no_delivery_link"


def test_adapter_satisfies_browser_context_resolver_protocol() -> None:
    """生产端按**能力鸭型**被发现（stages 用 isinstance 判，不建 adapter 名单）。"""
    assert isinstance(_adapter(_never), BrowserContextResolver)


# --- healthcheck（经 crossref lookup 打 api.crossref.org；非 SSRN 域）-----------------------


def test_healthcheck_golden_title_match_healthy() -> None:
    """固定 SSRN DOI 经 crossref lookup 命中、title 与 golden 一致 → healthy「matched」。

    golden 真值 [LIVE 2026-07-24]（P5-M1 双源转正：crossref 冒烟 + openalex 第二源一致，
    见 adapter `_HEALTHCHECK_TITLE` 模块常量注释）——本测试用**默认模块状态**（无
    monkeypatch），故 fixture body title 须与实测 golden 逐字一致（沿 crossref
    `test_healthcheck_golden_title_match_healthy` 转正后同款先例）。
    """
    body = (
        b'{"status":"ok","message-type":"work","message":{'
        b'"DOI":"10.2139/ssrn.4056799","title":["Allocating Scarce Information"]}}'
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "api.crossref.org"  # 非 SSRN 域
        assert str(request.url).endswith("/works/10.2139/ssrn.4056799")
        return _resp(body)

    report = _adapter(handler).healthcheck()
    assert report.healthy is True
    assert "matched" in report.detail


def test_healthcheck_anchor_not_found_unhealthy() -> None:
    report = _adapter(lambda r: _resp(b'{"message":"Not found."}', status=404)).healthcheck()
    assert report.healthy is False
    assert "not found" in report.detail


def test_healthcheck_unreachable_unhealthy() -> None:
    report = _adapter(lambda r: httpx.Response(500, text="down")).healthcheck()
    assert report.healthy is False
    assert "unreachable" in report.detail


def test_healthcheck_golden_match_when_captured(monkeypatch: pytest.MonkeyPatch) -> None:
    """golden 真值转正后（UPDATE_GOLDEN）：title 等值 → healthy「canary matched」。"""
    monkeypatch.setattr(
        "paper_crawler.adapters.ssrn.adapter._HEALTHCHECK_TITLE", "A Known SSRN Working Paper"
    )
    body = (
        b'{"status":"ok","message-type":"work","message":{'
        b'"DOI":"10.2139/ssrn.4056799","title":["A Known SSRN Working Paper"]}}'
    )
    report = _adapter(lambda r: _resp(body)).healthcheck()
    assert report.healthy is True
    assert "matched" in report.detail


def test_healthcheck_drift_when_title_differs(monkeypatch: pytest.MonkeyPatch) -> None:
    """golden 转正后 title 漂移 → unhealthy「drift」（catalog 腐化哨兵）。"""
    monkeypatch.setattr(
        "paper_crawler.adapters.ssrn.adapter._HEALTHCHECK_TITLE", "An Expected Golden Title"
    )
    body = (
        b'{"status":"ok","message-type":"work","message":{'
        b'"DOI":"10.2139/ssrn.4056799","title":["A Drifted Title"]}}'
    )
    report = _adapter(lambda r: _resp(body)).healthcheck()
    assert report.healthy is False
    assert "drift" in report.detail


# --- HttpClient 注入转发内部 crossref -------------------------------------------------------


def test_set_http_client_forwards_to_internal_crossref() -> None:
    crossref = CrossrefAdapter()
    adapter = SsrnAdapter(crossref=crossref)
    client = HttpClient(user_agent=_UA)
    adapter.set_http_client(client)
    assert crossref._client() is client  # 转发生效


def test_load_adapters_no_arg_construction() -> None:
    """entry point 无参实例化（load_adapters 路径）：内部自建 crossref，不抛。"""
    adapter = SsrnAdapter()
    assert adapter.adapter_id == "ssrn"
    assert isinstance(adapter._crossref, CrossrefAdapter)


# --- AC-5.1a③ 全生命周期零 SSRN 接触 -------------------------------------------------------


def test_zero_ssrn_contact_across_full_lifecycle() -> None:
    """discover + enumerate + resolve 全程 MockTransport 记录请求域 → 无 `*.ssrn.com`（红线）。"""
    hosts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        host = request.url.host
        hosts.append(host)
        assert not host.endswith("ssrn.com"), f"RED LINE VIOLATED: request to SSRN host {host!r}"
        return _resp(fixture_bytes("01_works_mixed_types.json"))

    adapter = _adapter(handler)
    venue = _venue()
    # discover（纯生成，零请求）
    issues = list(adapter.discover_timeline(venue))
    # enumerate（唯一网络出口 = api.crossref.org）
    stubs = list(adapter.enumerate_issue(venue, issues[-1]))
    # resolve（零请求：产模式 B RENDER_PAGE 计划，url 字段是构造的字符串——不是请求；
    # 红线断言对象是 `hosts`，只由 handler 实际被调用时追加，resolve 从不触发 handler）。
    requests_before_resolve = len(hosts)
    for stub in stubs:
        plans = adapter.resolve_assets(venue, stub)
        assert len(plans) == 1
        assert plans[0].url.startswith("https://papers.ssrn.com/")  # 纯串，非请求
    assert len(hosts) == requests_before_resolve, "resolve 不应发起任何请求（landing-only）"

    assert hosts, "enumerate 应至少发一次 crossref 请求（否则测试无意义）"
    assert all(host == "api.crossref.org" for host in hosts)  # 唯一接触域
    assert not any(host.endswith("ssrn.com") for host in hosts)  # 零 SSRN 接触


# --- AC-5.1a① 7 收割日回放（重叠窗 + created 延迟 → (ssrn) 主键去重无重复无遗漏）-----------


def test_seven_harvest_day_replay_dedup_no_dup_no_omission() -> None:
    spec = fixture_json("06_replay_7days.json")
    days = spec["days"]
    expected = set(spec["expected_abstract_ids"])
    delayed = spec["delayed_abstract_id"]

    all_ids: list[str] = []  # 跨 7 日累计（含重叠重复）
    for day in days:
        page = works_page_bytes(day["dois"])  # 该日 created 窗快照（single-page）
        adapter = _adapter(lambda r, _p=page: _resp(_p))
        stubs = adapter.enumerate_issue(_venue(), IssueRef(venue_id="ssrn", year=2026))
        for stub in stubs:
            ssrn_id = parse.ssrn_id_of_stub(stub)
            assert ssrn_id is not None
            all_ids.append(ssrn_id)

    deduped = set(all_ids)  # (ssrn) identifier 主键去重（重叠窗不产重复行）
    # 无遗漏：7 日累计去重 == 完整期望集（含延迟注入的 1004）。
    assert deduped == expected
    assert delayed in deduped, "created 延迟注入的投稿应被后续重叠窗捕获（无遗漏）"
    # 无重复：去重集每 id 恰一次；且原始累计 > 去重（证重叠窗确有重复被折叠）。
    assert len(all_ids) > len(deduped), "重叠窗应产生重复（去重前 > 去重后）"
    assert sorted(deduped) == sorted(expected)


# --- §4.4 净效果：unpaywall SSRN landing-only → OA-fallback 不产 asset -----------------------


def test_unpaywall_ssrn_landing_only_yields_no_pdf_asset() -> None:
    """SSRN 的 unpaywall 为 landing-only（url_for_pdf=null）→ UnpaywallAdapter.resolve 返 []
    （验证 ssrn.md §4.4「PDF 命中≈0」净效果——全文交 OA-fallback 亦无第三方副本）。"""
    client = HttpClient(
        user_agent=_UA,
        transport=httpx.MockTransport(
            lambda r: _resp(fixture_bytes("05_unpaywall_ssrn_landing_only.json"))
        ),
    )
    unpaywall = UnpaywallAdapter(http=client, email="test@example.com")
    paper = PaperStub(
        title="WP", identifiers=(("doi", "10.2139/ssrn.4056799"), ("ssrn", "4056799"))
    )
    plans = unpaywall.resolve_assets(_venue(), paper)
    assert plans == []  # landing-only：无 PDF 直链 → 不产 asset
