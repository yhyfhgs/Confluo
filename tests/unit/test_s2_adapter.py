"""s2/adapter.py 单测（MockTransport 注入，零真实网络；aggregators.md §5.4）。

覆盖：capabilities 空集 + duck-typed 协议一致性、`enrich_batch`（无 key 直接
CONFIG 不发请求/有 key POST batch/去重/≤500 固定切分/错误映射 429/400/500/404/
`x-api-key` 头随请求发出）、healthcheck（无 key→NotImplementedError/有 key 结构性
PENDING/精确匹配/漂移/不可达/404→GONE）、HttpClient 注入与惰性自建、post_json 请求体。
"""

from __future__ import annotations

import json
from collections.abc import Callable

import httpx
import pytest

from helpers.s2_fixtures import fixture_bytes, http_fixture
from paper_crawler.adapter import ApiKeyConsumer, EnrichmentSource, HttpClientConsumer
from paper_crawler.adapters.s2.adapter import S2Adapter, _batch_url, _default_user_agent
from paper_crawler.errors import CrawlerError, ErrorClass
from paper_crawler.http import HttpClient
from paper_crawler.types import AuthLevel, Capability

_UA = "PaperCrawler/test (personal research; mailto:test@example.com)"
Handler = Callable[[httpx.Request], httpx.Response]


def _adapter(handler: Handler, *, api_key: str | None = "test-key") -> S2Adapter:
    client = HttpClient(user_agent=_UA, transport=httpx.MockTransport(handler))
    adapter = S2Adapter(http=client)
    adapter.set_api_key(api_key)
    return adapter


def _resp(body: bytes, status: int = 200) -> httpx.Response:
    return httpx.Response(status, content=body)


def _never(_request: httpx.Request) -> httpx.Response:
    raise AssertionError("no network expected for this path")


# --- 元数据/能力面 ---------------------------------------------------------------------------


def test_adapter_attributes() -> None:
    adapter = S2Adapter()
    assert adapter.adapter_id == "s2"
    assert adapter.family == "aggregator"
    assert adapter.capabilities == Capability(0)
    assert not adapter.capabilities
    for cap in Capability:
        assert cap not in adapter.capabilities
    assert adapter.auth_requirement is AuthLevel.NONE
    assert adapter.domains == ("api.semanticscholar.org",)
    assert adapter.default_rate.requests_per_minute > 0
    assert adapter.default_rate.source_note != ""


def test_adapter_is_enrich_source_and_api_key_consumer_and_http_client_consumer() -> None:
    adapter = S2Adapter()
    assert isinstance(adapter, EnrichmentSource)
    assert isinstance(adapter, ApiKeyConsumer)
    assert isinstance(adapter, HttpClientConsumer)


def test_undeclared_capabilities_raise_capability_not_supported() -> None:
    from helpers import make_mock_venue
    from paper_crawler.errors import CapabilityNotSupported
    from paper_crawler.types import IssueRef, PaperStub

    adapter = S2Adapter()
    venue = make_mock_venue()
    with pytest.raises(CapabilityNotSupported):
        list(adapter.discover_timeline(venue))
    with pytest.raises(CapabilityNotSupported):
        list(adapter.enumerate_issue(venue, IssueRef(venue_id=venue.id)))
    with pytest.raises(CapabilityNotSupported):
        adapter.resolve_assets(venue, PaperStub(title="T", identifiers=(("doi", "10.1/x"),)))


# --- enrich_batch：无 key → 直接 CONFIG，不发请求 ------------------------------------------------


def test_enrich_batch_no_key_raises_config_without_any_request() -> None:
    """§5.4：直接判定，不靠状态码推断——`_never` handler 若被调用会 AssertionError。

    对照 `tests/fixtures/s2/02_single_not_found_404.http`：真实无 key 请求会被服务端
    受理并返回 404 "not found"（连已收录 DOI 亦然）——正因为该状态码无法区分"真缺"
    与"没 key"，本层才选择完全不发这次请求、靠 key 存在性直接判定。
    """
    adapter = _adapter(_never, api_key=None)
    with pytest.raises(CrawlerError) as exc:
        adapter.enrich_batch(["10.1/a"])
    assert exc.value.error_class is ErrorClass.CONFIG
    assert "key" in str(exc.value)


def test_enrich_batch_never_configured_key_raises_config() -> None:
    """从未调用过 `set_api_key` 的全新实例（`_api_key` 恒 `None`）同样拦截。"""
    with pytest.raises(CrawlerError) as exc:
        S2Adapter().enrich_batch(["10.1/a"])
    assert exc.value.error_class is ErrorClass.CONFIG


def test_enrich_batch_empty_string_key_raises_config() -> None:
    adapter = _adapter(_never, api_key="")
    with pytest.raises(CrawlerError) as exc:
        adapter.enrich_batch(["10.1/a"])
    assert exc.value.error_class is ErrorClass.CONFIG


def test_enrich_batch_no_key_raises_config_even_with_empty_dois() -> None:
    """key 检查先于空输入检查——`dois=[]` 不能绕过"未配置 key"的响亮报错。"""
    adapter = _adapter(_never, api_key=None)
    with pytest.raises(CrawlerError) as exc:
        adapter.enrich_batch([])
    assert exc.value.error_class is ErrorClass.CONFIG


def test_enrich_batch_empty_dois_with_key_returns_empty_without_request() -> None:
    """有 key 时空输入提前返回空列表，不发任何请求（无 DOI 可查）。"""
    assert _adapter(_never, api_key="k").enrich_batch([]) == []


# --- enrich_batch：有 key，正常/去重/批切分/头注入 ------------------------------------------------


def test_enrich_batch_normal_response_produces_stub() -> None:
    stubs = _adapter(lambda r: _resp(fixture_bytes("01_batch_normal.json"))).enrich_batch(
        ["10.48550/arXiv.1706.03762"]
    )
    assert len(stubs) == 1
    assert stubs[0].title == "Attention Is All You Need"


def test_enrich_batch_dedupes_and_skips_blank() -> None:
    captured: list[bytes] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request.content)
        return _resp(b"[]")

    _adapter(handler).enrich_batch(["10.1/a", "10.1/a", "", "10.1/b"])

    body = json.loads(captured[0])
    assert body["ids"] == ["DOI:10.1/a", "DOI:10.1/b"]


def test_enrich_batch_request_body_prefixes_doi() -> None:
    captured: list[bytes] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request.content)
        return _resp(b"[]")

    _adapter(handler).enrich_batch(["10.1/x"])
    assert json.loads(captured[0]) == {"ids": ["DOI:10.1/x"]}


def test_enrich_batch_url_has_fields_param() -> None:
    captured: list[httpx.URL] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request.url)
        return _resp(b"[]")

    _adapter(handler).enrich_batch(["10.1/x"])
    fields = captured[0].params.get("fields", "")
    assert "title" in fields
    assert "citationCount" in fields
    assert "tldr" in fields
    assert "fieldsOfStudy" in fields
    assert "openAccessPdf" in fields


def test_enrich_batch_x_api_key_header_present_on_request() -> None:
    """凭证隔离验证：本单测直接把 key 携带头挂在测试 client 上（模拟 CLI 专属 client
    装配结果），确认该头确实随请求发出——`x-api-key` 头本身由调用方（CLI）负责注入
    专属 client（见 adapter.py `set_http_client` docstring），adapter 自身不做头注入。
    """
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return _resp(b"[]")

    client = HttpClient(
        user_agent=_UA,
        transport=httpx.MockTransport(handler),
        extra_headers={"x-api-key": "secret-header-key"},
    )
    adapter = S2Adapter(http=client)
    adapter.set_api_key("secret-header-key")
    adapter.enrich_batch(["10.1/x"])

    assert captured[0].headers.get("x-api-key") == "secret-header-key"


def test_enrich_batch_splits_into_500_item_chunks() -> None:
    request_bodies: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        request_bodies.append(json.loads(request.content))
        return _resp(b"[]")

    many = [f"10.1/{i:05d}" for i in range(1200)]
    _adapter(handler).enrich_batch(many)

    assert len(request_bodies) == 3  # ceil(1200/500) = 3
    assert [len(body["ids"]) for body in request_bodies] == [500, 500, 200]


def test_enrich_batch_skips_and_not_found_are_logged(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[dict[str, object]] = []

    def _capture(level: str, msg: str, **extra: object) -> None:
        events.append({"msg": msg, **extra})

    monkeypatch.setattr("paper_crawler.adapters.s2.adapter.log_event", _capture)
    _adapter(lambda r: _resp(fixture_bytes("01_batch_normal.json"))).enrich_batch(
        ["10.1/a", "10.1/b", "10.1/c"]
    )

    skip_events = [e for e in events if e["msg"] == "s2 enrich_batch records skipped/not-found"]
    assert len(skip_events) == 1
    assert skip_events[0]["not_found"] == 1
    assert skip_events[0]["skipped_untitled"] == 1


# --- 错误映射（经 HttpClient 冻结映射）------------------------------------------------------------


def test_enrich_batch_429_maps_rate_limited() -> None:
    status, headers, body = http_fixture("03_batch_429.http")
    adapter = _adapter(lambda r: httpx.Response(status, headers=headers, content=body))
    with pytest.raises(CrawlerError) as exc:
        adapter.enrich_batch(["10.1/a"])
    assert exc.value.error_class is ErrorClass.RATE_LIMITED
    assert "retry_after_s=2" in exc.value.detail


def test_enrich_batch_400_maps_config() -> None:
    status, headers, body = http_fixture("04_batch_400_bad_fields.http")
    adapter = _adapter(lambda r: httpx.Response(status, headers=headers, content=body))
    with pytest.raises(CrawlerError) as exc:
        adapter.enrich_batch(["10.1/a"])
    assert exc.value.error_class is ErrorClass.CONFIG


def test_enrich_batch_500_maps_transient() -> None:
    status, headers, body = http_fixture("05_batch_500.http")
    adapter = _adapter(lambda r: httpx.Response(status, headers=headers, content=body))
    with pytest.raises(CrawlerError) as exc:
        adapter.enrich_batch(["10.1/a"])
    assert exc.value.error_class is ErrorClass.TRANSIENT


# --- healthcheck -----------------------------------------------------------------------------


def test_healthcheck_no_key_raises_not_implemented() -> None:
    adapter = S2Adapter()
    with pytest.raises(NotImplementedError, match="s2 key 未配置"):
        adapter.healthcheck()


def test_healthcheck_pending_golden_structural_healthy() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "DOI:10.48550" in str(request.url)
        return _resp(fixture_bytes("07_single_paper_healthcheck.json"))

    report = _adapter(handler).healthcheck()
    assert report.healthy is True
    assert "PENDING" in report.detail
    assert "Attention Is All You Need" in report.detail


def test_healthcheck_exact_match_when_golden_captured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "paper_crawler.adapters.s2.adapter._HEALTHCHECK_TITLE", "Attention Is All You Need"
    )
    adapter = _adapter(lambda r: _resp(fixture_bytes("07_single_paper_healthcheck.json")))
    report = adapter.healthcheck()
    assert report.healthy is True
    assert "matched" in report.detail


def test_healthcheck_drift_when_title_differs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "paper_crawler.adapters.s2.adapter._HEALTHCHECK_TITLE", "A Completely Different Title"
    )
    adapter = _adapter(lambda r: _resp(fixture_bytes("07_single_paper_healthcheck.json")))
    report = adapter.healthcheck()
    assert report.healthy is False
    assert "drift" in report.detail


def test_healthcheck_404_not_found_maps_gone_and_unhealthy() -> None:
    """§5.4 "有 key 真缺" 场景（fixture ②）：靠 key 存在性预判区分，本用例走"有 key
    但该固定 DOI 恰好未收录"这一（假设的）分支，HttpClient 原生 404→GONE 映射。
    """
    status, headers, body = http_fixture("02_single_not_found_404.http")
    report = _adapter(lambda r: httpx.Response(status, headers=headers, content=body)).healthcheck()
    assert report.healthy is False
    assert "gone" in report.detail.lower()


def test_healthcheck_empty_title_unhealthy_parse() -> None:
    report = _adapter(lambda r: _resp(b'{"paperId": "abc"}')).healthcheck()
    assert report.healthy is False
    assert "parse" in report.detail.lower()


def test_healthcheck_unreachable_unhealthy() -> None:
    report = _adapter(lambda r: httpx.Response(500, text="down")).healthcheck()
    assert report.healthy is False
    assert "unreachable" in report.detail


# --- HttpClient 注入 / 惰性自建 / UA -------------------------------------------------------------


def test_set_http_client_injects() -> None:
    adapter = S2Adapter()
    client = HttpClient(user_agent=_UA)
    adapter.set_http_client(client)
    assert adapter._client() is client


def test_lazy_client_built_and_cached_without_injection() -> None:
    adapter = S2Adapter()
    client = adapter._client()
    assert isinstance(client, HttpClient)
    assert adapter._client() is client


def test_default_user_agent_uses_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PAPER_CRAWLER_CONTACT_EMAIL", "real@example.org")
    assert "mailto:real@example.org" in _default_user_agent()


def test_default_user_agent_placeholder_when_env_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PAPER_CRAWLER_CONTACT_EMAIL", raising=False)
    assert ".invalid" in _default_user_agent()


def test_batch_url_is_stable_endpoint() -> None:
    url = _batch_url()
    assert url.startswith("https://api.semanticscholar.org/graph/v1/paper/batch?")
    assert "fields=" in url


def test_set_api_key_overrides_previous_value() -> None:
    adapter = S2Adapter()
    adapter.set_api_key("first")
    adapter.set_api_key("second")
    assert adapter._api_key == "second"
