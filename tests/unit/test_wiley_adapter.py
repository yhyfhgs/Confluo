"""wiley/adapter.py 单测（MockTransport 注入，零真实网络；design/adapters/wiley.md；
design/11 wiley 节页面兜底 T11）。

覆盖：元数据/能力面 + 协议一致性、token 门控（fetch→AuthRequired、healthcheck→
NotImplementedError，无伪 pass；**resolve 自 T11 起不再早退**——无 token 改产页面兜底
`RENDER_PAGE` 计划，与 TDM `API_CALL` 计划互斥恒一、不双发）、RESOLVE 零网络 +
AssetPlan 字段（两态：TDM/页面兜底）、FETCH（%PDF 落盘 + `Wiley-TDM-Client-Token` 头
随请求发出 + 分块）、错误映射三态（401→auth_expired / 403→no_entitlement /
429→rate_limited 读 Retry-After）、healthcheck 有 token 探针（PDF/质询/非 PDF/不可达）、
双窗口限速映射（假时钟 acquire 序列 0/0/0/12s）。
"""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from helpers import FakeFetchIO, make_wiley_venue
from helpers.wiley_fixtures import fixture_bytes, http_fixture
from paper_crawler.adapter import HttpClientConsumer, SourceAdapter
from paper_crawler.adapters.wiley import parse
from paper_crawler.adapters.wiley.adapter import (
    _HEALTHCHECK_DOI,
    TDM_TOKEN_HEADER,
    WileyAdapter,
)
from paper_crawler.errors import AuthRequired, CapabilityNotSupported, CrawlerError, ErrorClass
from paper_crawler.http import HttpClient
from paper_crawler.ratelimit import RateLimiter
from paper_crawler.types import (
    AssetKind,
    AssetPlan,
    AuthLevel,
    Capability,
    IssueRef,
    PaperStub,
    RatePolicy,
    UrlStrategy,
)

_UA = "PaperCrawler/test (personal research; mailto:test@example.com)"
_TOKEN = "test-token-uuid"
_PAPER = PaperStub(title="A Wiley Paper", identifiers=(("doi", "10.1111/jofi.13123"),))
Handler = Callable[[httpx.Request], httpx.Response]


def _adapter(handler: Handler, *, token: str | None = _TOKEN) -> WileyAdapter:
    """构造携专属 client（`Wiley-TDM-Client-Token` 头 + MockTransport）的 adapter。

    模拟 CLI 装配期的凭证隔离结果（同 s2 单测 `_adapter`）：token 非空 → 头随专属 client
    注入；token 为 None/空 → 不注入头（门控分支在触网前早退，handler 不会被调用）。
    """
    extra = {TDM_TOKEN_HEADER: token} if token else None
    client = HttpClient(user_agent=_UA, transport=httpx.MockTransport(handler), extra_headers=extra)
    return WileyAdapter(http=client, token=token)


def _resp(body: bytes, status: int = 200) -> httpx.Response:
    return httpx.Response(status, content=body)


def _never(_request: httpx.Request) -> httpx.Response:
    raise AssertionError("no network expected for this path")


class _FakeClock:
    """手动前进的假时钟（沿 test_ratelimit.py 先例）。"""

    def __init__(self, start: float = 0.0) -> None:
        self._now = start

    def __call__(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds


# --- 元数据 / 能力面 / 协议一致性 --------------------------------------------------------------


def test_adapter_attributes() -> None:
    adapter = WileyAdapter()
    assert adapter.adapter_id == "wiley"
    assert adapter.family == "auth_gated"
    assert adapter.capabilities == Capability.RESOLVE | Capability.FETCH
    assert Capability.DISCOVER not in adapter.capabilities
    assert Capability.ENUMERATE not in adapter.capabilities
    assert Capability.SEARCH not in adapter.capabilities
    assert adapter.auth_requirement is AuthLevel.INSTITUTIONAL
    assert adapter.domains == ("api.wiley.com",)
    assert adapter.resolve_offline is True
    assert adapter.default_rate.source_note != ""


def test_default_rate_is_conservative_dual_window_start_value() -> None:
    """wiley.md §4 起步保守值 rpm=5/burst=3（单桶表达双窗口）。"""
    assert WileyAdapter.default_rate.requests_per_minute == 5.0
    assert WileyAdapter.default_rate.burst == 3


def test_adapter_is_source_adapter_and_http_client_consumer() -> None:
    adapter = WileyAdapter()
    assert isinstance(adapter, SourceAdapter)
    assert isinstance(adapter, HttpClientConsumer)


def test_undeclared_capabilities_raise_capability_not_supported() -> None:
    """DISCOVER/ENUMERATE 未声明 → CapabilityNotSupported 兜底（enumerate 走 crossref）。"""
    adapter = _adapter(_never)
    venue = make_wiley_venue()
    with pytest.raises(CapabilityNotSupported):
        list(adapter.discover_timeline(venue))
    with pytest.raises(CapabilityNotSupported):
        list(adapter.enumerate_issue(venue, IssueRef(venue_id=venue.id)))


# --- token 门控（fetch/healthcheck 无 token → 全部诚实 AuthRequired/skip，无伪 pass）---------
# resolve 的 token 门控自 T11 起收窄：无 token 不再早退，改产页面兜底 RENDER_PAGE 计划
# （design/11 wiley 节"只在 TDM 不可用时"；见下"RESOLVE 页面兜底"分组）。


def test_fetch_no_token_raises_auth_required() -> None:
    adapter = _adapter(_never, token=None)
    plan = AssetPlan(kind=AssetKind.PDF, url=parse.tdm_article_url("10.1111/jofi.13123"))
    with pytest.raises(AuthRequired) as exc:
        adapter.fetch_asset(plan, FakeFetchIO())
    assert exc.value.error_class is ErrorClass.AUTH_EXPIRED


def test_healthcheck_no_token_raises_not_implemented() -> None:
    """无 token → NotImplementedError → canary SKIP（与 fetch AuthRequired→BLOCKED 二义分离）。"""
    with pytest.raises(NotImplementedError, match="wiley token 未配置"):
        WileyAdapter().healthcheck()


def test_never_configured_token_gates_fetch_and_healthcheck() -> None:
    """从未 set_token 的全新实例（`_token` 恒 None）：fetch/healthcheck 仍被门控——
    resolve 改产页面兜底计划（不再门控，见下）。"""
    adapter = WileyAdapter()
    plan = adapter.resolve_assets(make_wiley_venue(), _PAPER)[0]
    assert plan.url_strategy is UrlStrategy.RENDER_PAGE
    with pytest.raises(AuthRequired):
        adapter.fetch_asset(plan, FakeFetchIO())
    with pytest.raises(NotImplementedError):
        adapter.healthcheck()


def test_empty_string_token_is_treated_as_unconfigured() -> None:
    """空白串归一为"未配置"（等价未提供，同全库 token 口径）——resolve 产页面兜底计划、
    healthcheck 门控仍生效。"""
    adapter = WileyAdapter(token="   ")
    plan = adapter.resolve_assets(make_wiley_venue(), _PAPER)[0]
    assert plan.url_strategy is UrlStrategy.RENDER_PAGE
    adapter.set_token("")
    with pytest.raises(NotImplementedError):
        adapter.healthcheck()


# --- RESOLVE（有 token → 零网络纯 URL 构造 TDM 计划）--------------------------------------------


def test_resolve_with_token_builds_tdm_asset_plan_without_network() -> None:
    plans = _adapter(_never).resolve_assets(make_wiley_venue(), _PAPER)
    assert len(plans) == 1
    plan = plans[0]
    assert plan.kind is AssetKind.PDF
    assert plan.url == "https://api.wiley.com/onlinelibrary/tdm/v1/articles/10.1111/jofi.13123"
    assert plan.url_strategy is UrlStrategy.API_CALL
    assert plan.auth_needed is AuthLevel.INSTITUTIONAL
    assert plan.expected_type == "application/pdf"


# --- RESOLVE 页面兜底（无 token → RENDER_PAGE 计划，design/11 wiley 节，T11）------------------


def test_resolve_no_token_returns_render_page_fallback_plan_without_network() -> None:
    """TDM 结构性不可用（无 token）→ 页面兜底 `AssetPlan`（`RENDER_PAGE`），取代此前的
    `AuthRequired` 早退（browser-fetch 落地后"不产不可取回的兜底 plan"的诚实边界失去理由）。
    """
    adapter = _adapter(_never, token=None)
    plans = adapter.resolve_assets(make_wiley_venue(), _PAPER)

    assert len(plans) == 1
    plan = plans[0]
    assert plan.kind is AssetKind.PDF
    assert plan.url == "https://onlinelibrary.wiley.com/doi/pdf/10.1111/jofi.13123"
    assert plan.url_strategy is UrlStrategy.RENDER_PAGE
    assert plan.auth_needed is AuthLevel.INSTITUTIONAL
    assert plan.expected_type == "application/pdf"


def test_resolve_token_and_no_token_plans_are_mutually_exclusive_never_both() -> None:
    """design/11 wiley 节"只在 TDM 不可用时,不与 TDM 双发"——同一 DOI，有/无 token 恒
    产恰好一个计划，且 `url_strategy` 互斥。"""
    with_token = _adapter(_never, token="tok").resolve_assets(make_wiley_venue(), _PAPER)
    without_token = _adapter(_never, token=None).resolve_assets(make_wiley_venue(), _PAPER)

    assert len(with_token) == 1 and len(without_token) == 1
    assert with_token[0].url_strategy is UrlStrategy.API_CALL
    assert without_token[0].url_strategy is UrlStrategy.RENDER_PAGE
    assert with_token[0].url_strategy != without_token[0].url_strategy


def test_resolve_missing_doi_raises_config() -> None:
    """有 token 但 paper 无 doi identifier → CONFIG（路由缺陷，同 unpaywall `_doi_of`）。"""
    paper = PaperStub(title="No DOI", identifiers=(("arxiv", "2401.00001"),))
    with pytest.raises(CrawlerError) as exc:
        _adapter(_never).resolve_assets(make_wiley_venue(), paper)
    assert exc.value.error_class is ErrorClass.CONFIG


# --- FETCH（有 token → 专属 client stream → %PDF 落盘）------------------------------------------


def test_fetch_streams_pdf_and_returns_ok() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "onlinelibrary/tdm/v1/articles/10.1111/jofi.13123" in str(request.url)
        return _resp(fixture_bytes("01_tdm_article_success.pdf.bin"))

    adapter = _adapter(handler)
    plan = adapter.resolve_assets(make_wiley_venue(), _PAPER)[0]
    io = FakeFetchIO()
    result = adapter.fetch_asset(plan, io)

    assert result.ok is True
    assert result.bytes_written > 0
    assert result.sha256
    assert io.data.startswith(b"%PDF")
    assert io.chunk_count >= 1


def test_fetch_sends_tdm_token_header_on_request() -> None:
    """凭证隔离验证：头随专属 client 发出（adapter 不做头注入，见 set_http_client docstring）。"""
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return _resp(fixture_bytes("01_tdm_article_success.pdf.bin"))

    adapter = _adapter(handler)
    plan = adapter.resolve_assets(make_wiley_venue(), _PAPER)[0]
    adapter.fetch_asset(plan, FakeFetchIO())

    assert captured[0].headers.get(TDM_TOKEN_HEADER) == _TOKEN


# --- 错误映射三态（经 HttpClient 冻结映射透传；wiley.md §5）--------------------------------------


def _fetch_error(fixture_name: str) -> CrawlerError:
    status, headers, body = http_fixture(fixture_name)
    adapter = _adapter(lambda r: httpx.Response(status, headers=headers, content=body))
    plan = adapter.resolve_assets(make_wiley_venue(), _PAPER)[0]
    with pytest.raises(CrawlerError) as exc:
        adapter.fetch_asset(plan, FakeFetchIO())
    return exc.value


def test_fetch_401_maps_auth_expired() -> None:
    exc = _fetch_error("02_tdm_401_token_invalid.http")
    assert exc.error_class is ErrorClass.AUTH_EXPIRED
    assert exc.status_code == 401


def test_fetch_403_maps_no_entitlement() -> None:
    exc = _fetch_error("03_tdm_403_no_entitlement.http")
    assert exc.error_class is ErrorClass.NO_ENTITLEMENT
    assert exc.status_code == 403


def test_fetch_429_maps_rate_limited_with_retry_after() -> None:
    exc = _fetch_error("04_tdm_429_rate_limited.http")
    assert exc.error_class is ErrorClass.RATE_LIMITED
    assert exc.status_code == 429
    assert "retry_after_s=30" in exc.detail


# --- healthcheck（有 token → TDM 探针）--------------------------------------------------------


def test_healthcheck_with_token_pdf_probe_healthy() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert _HEALTHCHECK_DOI in str(request.url)
        return _resp(fixture_bytes("01_tdm_article_success.pdf.bin"))

    report = _adapter(handler).healthcheck()
    assert report.healthy is True
    assert "PENDING" in report.detail


def test_healthcheck_with_token_challenge_body_unhealthy() -> None:
    """非 PDF 且 body 命中 Cloudflare 质询特征 → unhealthy(challenge)（ChallengeDetector 复用）。"""
    body = (
        b"<html><body>Just a moment...<script "
        b"src='/cdn-cgi/challenge-platform/x'></script></body></html>"
    )
    report = _adapter(lambda r: _resp(body)).healthcheck()
    assert report.healthy is False
    assert "challenge" in report.detail


def test_healthcheck_with_token_non_pdf_unhealthy() -> None:
    report = _adapter(lambda r: _resp(b"<html>a normal landing page</html>")).healthcheck()
    assert report.healthy is False
    assert "non-PDF" in report.detail


def test_healthcheck_with_token_empty_response_unhealthy() -> None:
    """200 空体（流零块）→ 探针得 b"" → 非 PDF、非质询 → unhealthy（覆盖空响应兜底分支）。"""
    report = _adapter(lambda r: _resp(b"")).healthcheck()
    assert report.healthy is False
    assert "non-PDF" in report.detail


def test_healthcheck_with_token_403_unreachable_unhealthy() -> None:
    """403 探针 → CrawlerError(NO_ENTITLEMENT) → unhealthy（携 error_class，非崩溃）。"""
    report = _adapter(lambda r: httpx.Response(403, content=b"forbidden")).healthcheck()
    assert report.healthy is False
    assert "no_entitlement" in report.detail


# --- 依赖注入 / 惰性自建 ------------------------------------------------------------------------


def test_set_http_client_injects() -> None:
    adapter = WileyAdapter()
    client = HttpClient(user_agent=_UA)
    adapter.set_http_client(client)
    assert adapter._client() is client


def test_lazy_client_built_and_cached_without_injection() -> None:
    adapter = WileyAdapter()
    client = adapter._client()
    assert isinstance(client, HttpClient)
    assert adapter._client() is client


def test_set_token_overrides_previous_value() -> None:
    adapter = WileyAdapter()
    adapter.set_token("first")
    adapter.set_token("second")
    assert adapter._has_token() is True
    assert adapter._token == "second"


# --- 双窗口限速映射（假时钟精确断言；wiley.md §4/§6）-------------------------------------------


def test_dual_window_rate_maps_to_single_bucket_with_frozen_clock() -> None:
    """RatePolicy(rpm=5, burst=3) 注册到限速器：连发 3 个 wait=0，第 4 个 wait=12s（桶数学）。

    60/5=12s：桶空后 rpm=5 → 5/60=0.0833 token/s，欠 1 个 token 需 12s——比"3 req/s 每秒"
    更严（合 wiley.md §4"最保守值起步"）。沿 test_ratelimit.py `test_burst_allows_immediate_
    consumption_up_to_capacity` 先例写法。
    """
    clock = _FakeClock()
    limiter = RateLimiter(clock=clock)
    limiter.register("api.wiley.com", WileyAdapter.default_rate)

    waits = [limiter.acquire("api.wiley.com") for _ in range(3)]
    assert waits == [pytest.approx(0.0, abs=1e-9)] * 3
    assert limiter.acquire("api.wiley.com") == pytest.approx(12.0, abs=1e-9)


def test_effective_rpm_is_five() -> None:
    limiter = RateLimiter(clock=_FakeClock())
    limiter.register("api.wiley.com", WileyAdapter.default_rate)
    assert limiter.effective_rpm("api.wiley.com") == 5.0


def test_rate_policy_is_expressible_by_frozen_single_bucket() -> None:
    """接缝结论自证：双窗口无需扩展 ratelimit.py——单 RatePolicy 即可注册并产出桶数学。"""
    assert isinstance(WileyAdapter.default_rate, RatePolicy)
    clock = _FakeClock()
    limiter = RateLimiter(clock=clock)
    limiter.register("api.wiley.com", WileyAdapter.default_rate)
    # burst 容量恢复：耗尽后前进 12s 再生 1 个 token → 下次立即可用。
    for _ in range(3):
        limiter.acquire("api.wiley.com")
    clock.advance(12.0)
    assert limiter.acquire("api.wiley.com") == pytest.approx(0.0, abs=1e-9)
