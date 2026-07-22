"""elsevier_sd/adapter.py 单测（MockTransport 注入，零真实网络；elsevier-sd.md §3/§5）。

覆盖：能力/元数据面 + consumer 协议、undeclared（discover/enumerate）→CapabilityNotSupported、
resolve（无 key→AuthRequired / entitled true→PDF plan(+xml quirk) / entitled false→
NO_ENTITLEMENT / 缺 doi→CONFIG）、错误映射（401→auth_expired / 403→auth_expired 重分类 /
404→gone / 429→rate_limited / 5xx→transient）、**429 当日熔断**（B-M2：trips + 同日短路不触网）、
fetch（流式 PDF / 429 熔断 / 403 / 无 key→AuthRequired）、healthcheck（无 key→NotImplementedError /
PENDING 结构性 / 精确匹配 / 漂移 / 不可达 / parse 失败）、HttpClient 注入/惰性自建/UA、URL 构造
（httpAccept，key 不入 URL）。fixture 回放 01/02/03/04。
"""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from helpers import FakeFetchIO, make_elsevier_venue
from helpers.elsevier_fixtures import body_bytes, http_fixture
from paper_crawler.adapter import ApiKeyConsumer, HttpClientConsumer
from paper_crawler.adapters.elsevier_sd.adapter import (
    _HEALTHCHECK_DOI,
    ElsevierScienceDirectAdapter,
    _default_user_agent,
)
from paper_crawler.errors import AuthRequired, CapabilityNotSupported, CrawlerError, ErrorClass
from paper_crawler.http import HttpClient
from paper_crawler.types import AssetKind, AuthLevel, Capability, IssueRef, PaperStub, UrlStrategy

_UA = "PaperCrawler/test (personal research; mailto:test@example.com)"
_DOI = "10.1016/j.jfineco.2011.03.021"
_PDF = b"%PDF-1.4\n% elsevier contract\n" + b"0" * 128 + b"\n%%EOF\n"

Handler = Callable[[httpx.Request], httpx.Response]


def _paper(doi: str = _DOI) -> PaperStub:
    return PaperStub(title="A JFE paper", identifiers=(("doi", doi),))


def _adapter(handler: Handler, *, api_key: str | None = "test-key") -> ElsevierScienceDirectAdapter:
    client = HttpClient(user_agent=_UA, transport=httpx.MockTransport(handler))
    adapter = ElsevierScienceDirectAdapter(http=client)
    adapter.set_api_key(api_key)
    return adapter


def _entitled_handler(entitled_fixture: str) -> Handler:
    """entitlement 端点 → 指定 fixture body；article 端点 → %PDF。"""

    def handler(request: httpx.Request) -> httpx.Response:
        if "/entitlement/" in request.url.path:
            status, _headers, body = http_fixture(entitled_fixture)
            return httpx.Response(status, content=body)
        return httpx.Response(200, content=_PDF)

    return handler


def _never(_request: httpx.Request) -> httpx.Response:
    raise AssertionError("no network expected for this path")


# --- 元数据 / 能力面 --------------------------------------------------------------------------


def test_adapter_attributes() -> None:
    adapter = ElsevierScienceDirectAdapter()
    assert adapter.adapter_id == "elsevier_sd"
    assert adapter.family == "auth_gated"
    assert adapter.capabilities == Capability.RESOLVE | Capability.FETCH
    assert Capability.DISCOVER not in adapter.capabilities
    assert Capability.ENUMERATE not in adapter.capabilities
    assert adapter.auth_requirement is AuthLevel.INSTITUTIONAL
    assert adapter.domains == ("api.elsevier.com",)
    assert adapter.default_rate.requests_per_minute == 120.0
    assert adapter.default_rate.source_note != ""
    assert "⚠" not in adapter.default_rate.source_note  # 非占位（真实出处）
    assert adapter.resolve_offline is False  # 网络 resolve（entitlement 预检）


def test_adapter_is_consumer_protocols() -> None:
    adapter = ElsevierScienceDirectAdapter()
    assert isinstance(adapter, HttpClientConsumer)
    assert isinstance(adapter, ApiKeyConsumer)


def test_undeclared_capabilities_raise_capability_not_supported() -> None:
    adapter = ElsevierScienceDirectAdapter()
    venue = make_elsevier_venue()
    with pytest.raises(CapabilityNotSupported):
        list(adapter.discover_timeline(venue))
    with pytest.raises(CapabilityNotSupported):
        list(adapter.enumerate_issue(venue, IssueRef(venue_id=venue.id)))


# --- resolve：无 key → AuthRequired（BLOCKER-1 离线分支）--------------------------------------


def test_resolve_no_key_raises_auth_required_without_network() -> None:
    adapter = _adapter(_never, api_key=None)
    with pytest.raises(AuthRequired) as exc:
        adapter.resolve_assets(make_elsevier_venue(), _paper())
    assert exc.value.error_class is ErrorClass.AUTH_EXPIRED
    assert "api_key" in exc.value.detail


def test_resolve_never_configured_key_raises_auth_required() -> None:
    adapter = ElsevierScienceDirectAdapter(http=HttpClient(user_agent=_UA))
    with pytest.raises(AuthRequired):
        adapter.resolve_assets(make_elsevier_venue(), _paper())


def test_resolve_empty_string_key_raises_auth_required() -> None:
    with pytest.raises(AuthRequired):
        _adapter(_never, api_key="").resolve_assets(make_elsevier_venue(), _paper())


# --- resolve：entitlement 分支 --------------------------------------------------------------


def test_resolve_entitled_true_yields_pdf_plan() -> None:
    plans = _adapter(_entitled_handler("01_entitlement_true.http")).resolve_assets(
        make_elsevier_venue(), _paper()
    )
    assert len(plans) == 1
    plan = plans[0]
    assert plan.kind is AssetKind.PDF
    assert plan.url_strategy is UrlStrategy.API_CALL
    assert plan.expected_type == "application/pdf"
    assert plan.auth_needed is AuthLevel.INSTITUTIONAL
    assert "httpAccept=application" in plan.url
    assert "api.elsevier.com/content/article/doi/" in plan.url


def test_resolve_xml_quirk_appends_source_plan() -> None:
    plans = _adapter(_entitled_handler("01_entitlement_true.http")).resolve_assets(
        make_elsevier_venue(elsevier_want_xml_source=True), _paper()
    )
    assert [p.kind for p in plans] == [AssetKind.PDF, AssetKind.SOURCE]
    xml = plans[1]
    assert xml.expected_type == "text/xml"
    assert "httpAccept=text" in xml.url


def test_resolve_api_key_not_in_url() -> None:
    """凭证红线：key 绝不入 URL（随专属 client 的 X-ELS-APIKey 头承载）。"""
    plans = _adapter(_entitled_handler("01_entitlement_true.http")).resolve_assets(
        make_elsevier_venue(), _paper()
    )
    assert "test-key" not in plans[0].url
    assert "apiKey" not in plans[0].url
    assert "APIKey" not in plans[0].url


def test_resolve_entitled_false_raises_no_entitlement() -> None:
    with pytest.raises(CrawlerError) as exc:
        _adapter(_entitled_handler("02_entitlement_false.http")).resolve_assets(
            make_elsevier_venue(), _paper()
        )
    assert exc.value.error_class is ErrorClass.NO_ENTITLEMENT
    assert exc.value.status_code == 200  # 判定源于 200 响应体语义
    assert _DOI in str(exc.value)


def test_resolve_missing_doi_raises_config() -> None:
    paper = PaperStub(title="no doi", identifiers=(("pii", "S0304405X11000000"),))
    with pytest.raises(CrawlerError) as exc:
        _adapter(_never).resolve_assets(make_elsevier_venue(), paper)
    assert exc.value.error_class is ErrorClass.CONFIG


def test_resolve_entitlement_uses_json_accept_and_entitlement_path() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        if "/entitlement/" in request.url.path:
            return httpx.Response(200, content=_entitlement_true_body())
        return httpx.Response(200, content=_PDF)

    _adapter(handler).resolve_assets(make_elsevier_venue(), _paper())
    ent_req = next(r for r in captured if "/entitlement/" in r.url.path)
    assert ent_req.headers.get("Accept") == "application/json"
    assert "/content/article/entitlement/doi/" in ent_req.url.path


# --- 错误映射（经 HttpClient 冻结映射 + adapter 重分类）----------------------------------------


def _err_on_entitlement(status: int, *, headers: dict[str, str] | None = None) -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, headers=headers or {}, content=b'{"error-response":{}}')

    return handler


def test_resolve_401_maps_auth_expired() -> None:
    with pytest.raises(CrawlerError) as exc:
        _adapter(_err_on_entitlement(401)).resolve_assets(make_elsevier_venue(), _paper())
    assert exc.value.error_class is ErrorClass.AUTH_EXPIRED


def test_resolve_403_reclassified_to_auth_expired() -> None:
    """elsevier API 403 = key/insttoken 失效 → 重分类 auth_expired（非 no_entitlement）。"""
    with pytest.raises(CrawlerError) as exc:
        _adapter(_err_on_entitlement(403)).resolve_assets(make_elsevier_venue(), _paper())
    assert exc.value.error_class is ErrorClass.AUTH_EXPIRED
    assert "403" in str(exc.value)


def test_resolve_404_maps_gone() -> None:
    with pytest.raises(CrawlerError) as exc:
        _adapter(_err_on_entitlement(404)).resolve_assets(make_elsevier_venue(), _paper())
    assert exc.value.error_class is ErrorClass.GONE


def test_resolve_500_maps_transient() -> None:
    with pytest.raises(CrawlerError) as exc:
        _adapter(_err_on_entitlement(500)).resolve_assets(make_elsevier_venue(), _paper())
    assert exc.value.error_class is ErrorClass.TRANSIENT


# --- 429 保守当日熔断（B-M2）-----------------------------------------------------------------


def test_resolve_429_maps_rate_limited() -> None:
    status, headers, body = http_fixture("04_quota_429_exceeded.http")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, headers=headers, content=body)

    with pytest.raises(CrawlerError) as exc:
        _adapter(handler).resolve_assets(make_elsevier_venue(), _paper())
    assert exc.value.error_class is ErrorClass.RATE_LIMITED
    assert "retry_after_s=604800" in exc.value.detail  # Retry-After 经 HttpClient 入 detail


def test_keyless_429_fixture_maps_rate_limited_no_retry_after() -> None:
    """R0 [LIVE] keyless 429（无 Retry-After）→ RATE_LIMITED（detail 无 retry_after_s 段）。"""
    status, headers, body = http_fixture("03_keyless_429_rate_limit_exceeded.http")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, headers=headers, content=body)

    with pytest.raises(CrawlerError) as exc:
        _adapter(handler).resolve_assets(make_elsevier_venue(), _paper())
    assert exc.value.error_class is ErrorClass.RATE_LIMITED
    assert "retry_after_s" not in exc.value.detail


def test_429_trips_circuit_then_short_circuits_without_network() -> None:
    """任意 429 → 当日熔断：同日后续 resolve 短路为 RATE_LIMITED，**不再触网**（B-M2）。"""
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(429, content=b'{"error-response":{"error-code":"QUOTA_EXCEEDED"}}')

    adapter = _adapter(handler)
    with pytest.raises(CrawlerError) as first:
        adapter.resolve_assets(make_elsevier_venue(), _paper())
    assert first.value.error_class is ErrorClass.RATE_LIMITED
    assert calls["n"] == 1

    with pytest.raises(CrawlerError) as second:
        adapter.resolve_assets(make_elsevier_venue(), _paper())
    assert second.value.error_class is ErrorClass.RATE_LIMITED
    assert "熔断" in str(second.value) or "circuit" in second.value.detail
    assert calls["n"] == 1  # 第二次未触网（熔断短路）


def test_circuit_short_circuits_fetch_too() -> None:
    """熔断对 fetch 同样生效（同一 adapter 实例，同日）。"""
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(429, content=b"{}")

    adapter = _adapter(handler)
    with pytest.raises(CrawlerError):
        adapter.resolve_assets(make_elsevier_venue(), _paper())
    plan_url = "https://api.elsevier.com/content/article/doi/x?httpAccept=application/pdf"
    from paper_crawler.types import AssetPlan

    plan = AssetPlan(kind=AssetKind.PDF, url=plan_url, url_strategy=UrlStrategy.API_CALL)
    with pytest.raises(CrawlerError) as exc:
        adapter.fetch_asset(plan, FakeFetchIO())
    assert exc.value.error_class is ErrorClass.RATE_LIMITED
    assert calls["n"] == 1


# --- fetch --------------------------------------------------------------------------------


def _pdf_plan(http_accept: str = "application/pdf"):  # type: ignore[no-untyped-def]
    from paper_crawler.types import AssetPlan

    url = f"https://api.elsevier.com/content/article/doi/{_DOI}?httpAccept={http_accept}"
    return AssetPlan(
        kind=AssetKind.PDF,
        url=url,
        expected_type="application/pdf",
        url_strategy=UrlStrategy.API_CALL,
        auth_needed=AuthLevel.INSTITUTIONAL,
    )


def test_fetch_streams_pdf() -> None:
    adapter = _adapter(lambda r: httpx.Response(200, content=_PDF))
    io = FakeFetchIO()
    result = adapter.fetch_asset(_pdf_plan(), io)
    assert result.ok is True
    assert result.bytes_written == len(_PDF)
    assert io.data.startswith(b"%PDF")


def test_fetch_no_key_raises_auth_required() -> None:
    adapter = _adapter(_never, api_key=None)
    with pytest.raises(AuthRequired):
        adapter.fetch_asset(_pdf_plan(), FakeFetchIO())


def test_fetch_403_reclassified_auth_expired() -> None:
    adapter = _adapter(lambda r: httpx.Response(403, content=b"{}"))
    with pytest.raises(CrawlerError) as exc:
        adapter.fetch_asset(_pdf_plan(), FakeFetchIO())
    assert exc.value.error_class is ErrorClass.AUTH_EXPIRED


def test_fetch_429_maps_rate_limited_and_trips_circuit() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(429, content=b"{}")

    adapter = _adapter(handler)
    with pytest.raises(CrawlerError) as exc:
        adapter.fetch_asset(_pdf_plan(), FakeFetchIO())
    assert exc.value.error_class is ErrorClass.RATE_LIMITED
    # 熔断已开：再 fetch 短路不触网
    with pytest.raises(CrawlerError):
        adapter.fetch_asset(_pdf_plan(), FakeFetchIO())
    assert calls["n"] == 1


# --- healthcheck -----------------------------------------------------------------------------


def test_healthcheck_no_key_raises_not_implemented() -> None:
    with pytest.raises(NotImplementedError, match="api_key"):
        ElsevierScienceDirectAdapter().healthcheck()


def test_healthcheck_empty_key_raises_not_implemented() -> None:
    adapter = ElsevierScienceDirectAdapter(http=HttpClient(user_agent=_UA))
    adapter.set_api_key("")
    with pytest.raises(NotImplementedError):
        adapter.healthcheck()


def test_healthcheck_pending_golden_structural_healthy() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert _HEALTHCHECK_DOI in str(request.url)
        assert "/entitlement/" in request.url.path
        return httpx.Response(200, content=_entitlement_true_body())

    report = _adapter(handler).healthcheck()
    assert report.healthy is True
    assert "PENDING" in report.detail
    assert "entitled=True" in report.detail


def test_healthcheck_exact_match_when_golden_captured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "paper_crawler.adapters.elsevier_sd.adapter._HEALTHCHECK_EXPECT_ENTITLED", True
    )
    report = _adapter(lambda r: httpx.Response(200, content=_entitlement_true_body())).healthcheck()
    assert report.healthy is True
    assert "matched" in report.detail


def test_healthcheck_drift_when_entitlement_differs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "paper_crawler.adapters.elsevier_sd.adapter._HEALTHCHECK_EXPECT_ENTITLED", True
    )
    report = _adapter(
        lambda r: httpx.Response(200, content=_entitlement_false_body())
    ).healthcheck()
    assert report.healthy is False
    assert "drift" in report.detail


def test_healthcheck_unreachable_unhealthy() -> None:
    report = _adapter(lambda r: httpx.Response(500, content=b"down")).healthcheck()
    assert report.healthy is False
    assert "unreachable" in report.detail


def test_healthcheck_parse_failure_unhealthy() -> None:
    report = _adapter(
        lambda r: httpx.Response(200, content=b'{"entitlement-response":{}}')
    ).healthcheck()
    assert report.healthy is False
    assert "parse failed" in report.detail


# --- HttpClient 注入 / 惰性自建 / UA ------------------------------------------------------------


def test_set_http_client_injects() -> None:
    adapter = ElsevierScienceDirectAdapter()
    client = HttpClient(user_agent=_UA)
    adapter.set_http_client(client)
    assert adapter._client() is client


def test_lazy_client_built_and_cached() -> None:
    adapter = ElsevierScienceDirectAdapter()
    client = adapter._client()
    assert isinstance(client, HttpClient)
    assert adapter._client() is client


def test_set_api_key_overrides_previous_value() -> None:
    adapter = ElsevierScienceDirectAdapter()
    adapter.set_api_key("first")
    adapter.set_api_key("second")
    assert adapter._api_key == "second"


def test_default_user_agent_uses_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PAPER_CRAWLER_CONTACT_EMAIL", "real@example.org")
    assert "mailto:real@example.org" in _default_user_agent()


def test_default_user_agent_placeholder_when_env_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PAPER_CRAWLER_CONTACT_EMAIL", raising=False)
    assert ".invalid" in _default_user_agent()


# --- fixture body 辅助（提取 .http 的 JSON body）---------------------------------------------


def _entitlement_true_body() -> bytes:
    return body_bytes("01_entitlement_true.http")


def _entitlement_false_body() -> bytes:
    return body_bytes("02_entitlement_false.http")
