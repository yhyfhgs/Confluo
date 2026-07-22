"""UnpaywallAdapter 主体单测（design/adapters/aggregators.md §5.5）：RESOLVE-only 能力面、
url_for_pdf 回退链→AssetPlan、landing-only/closed→空结果、错误映射、邮箱注入优先级、
healthcheck 锚点比对。零真实网络（`httpx.MockTransport` 注入受控响应）。
"""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from helpers import make_mock_venue
from helpers.unpaywall_fixtures import fixture_bytes, http_fixture
from paper_crawler.adapter import EmailConsumer, HttpClientConsumer
from paper_crawler.adapters.unpaywall.adapter import UnpaywallAdapter
from paper_crawler.errors import CrawlerError, ErrorClass
from paper_crawler.http import HttpClient
from paper_crawler.types import (
    AssetKind,
    AuthLevel,
    Capability,
    IssueRef,
    PaperStub,
    UrlStrategy,
)

_TEST_UA = "PaperCrawler/test (personal research; mailto:test@example.com)"
_ANCHOR_DOI = "10.1371/journal.pmed.0020124"

Handler = Callable[[httpx.Request], httpx.Response]


def _adapter(handler: Handler, *, email: str | None = "test@example.com") -> UnpaywallAdapter:
    client = HttpClient(user_agent=_TEST_UA, transport=httpx.MockTransport(handler))
    return UnpaywallAdapter(http=client, email=email)


def _fixture_handler(fixture_name: str) -> Handler:
    body = fixture_bytes(fixture_name)
    return lambda request: httpx.Response(200, content=body)


def _http_fixture_handler(fixture_name: str) -> Handler:
    status, headers, body = http_fixture(fixture_name)
    return lambda request: httpx.Response(status, headers=headers, content=body)


def _paper_with_doi(doi: str) -> PaperStub:
    return PaperStub(title="T", identifiers=(("doi", doi),))


# --- 元数据/能力面 --------------------------------------------------------------------------


def test_adapter_attributes() -> None:
    adapter = UnpaywallAdapter()
    assert adapter.adapter_id == "unpaywall"
    assert adapter.family == "aggregator"
    assert adapter.capabilities == Capability.RESOLVE
    assert Capability.DISCOVER not in adapter.capabilities
    assert Capability.ENUMERATE not in adapter.capabilities
    assert Capability.SEARCH not in adapter.capabilities
    assert Capability.FETCH not in adapter.capabilities
    assert adapter.auth_requirement is AuthLevel.NONE
    assert adapter.domains == ("api.unpaywall.org",)
    assert adapter.default_rate.requests_per_minute == 300.0
    assert adapter.default_rate.source_note != ""


def test_adapter_is_http_client_consumer_and_email_consumer() -> None:
    adapter = UnpaywallAdapter()
    assert isinstance(adapter, HttpClientConsumer)
    assert isinstance(adapter, EmailConsumer)


def test_undeclared_capabilities_raise_capability_not_supported() -> None:
    from paper_crawler.errors import CapabilityNotSupported

    adapter = UnpaywallAdapter()
    venue = make_mock_venue()
    with pytest.raises(CapabilityNotSupported):
        list(adapter.discover_timeline(venue))
    with pytest.raises(CapabilityNotSupported):
        list(adapter.enumerate_issue(venue, IssueRef(venue_id=venue.id)))


# --- resolve_assets：正常/回退链/landing-only/closed ------------------------------------------


def test_resolve_assets_direct_pdf_hit_no_fallback() -> None:
    adapter = _adapter(_fixture_handler("02_direct_pdf_hit_hybrid.json"))
    paper = _paper_with_doi("10.9999/synthetic.direct-pdf-hybrid")

    plans = adapter.resolve_assets(make_mock_venue(), paper)

    assert len(plans) == 1
    plan = plans[0]
    assert plan.kind is AssetKind.PDF
    assert plan.url == "https://publisher.example.org/articles/direct-pdf-hybrid.pdf"
    assert plan.url_strategy is UrlStrategy.DIRECT
    assert plan.auth_needed is AuthLevel.NONE
    assert plan.version == "acceptedVersion"


def test_resolve_assets_falls_back_through_oa_locations_for_pdf() -> None:
    adapter = _adapter(_fixture_handler("01_normal_gold_fallback.json"))
    paper = _paper_with_doi(_ANCHOR_DOI)

    plans = adapter.resolve_assets(make_mock_venue(), paper)

    assert len(plans) == 1
    assert plans[0].url == "https://repo.example.org/pdf/0020124-first.pdf"
    assert plans[0].version == "publishedVersion"


def test_resolve_assets_landing_only_produces_no_asset_plan() -> None:
    """★裁决 J4：url_for_pdf 全线为空但 landing 有值 → 0 AssetPlan（不下载 landing）。"""
    adapter = _adapter(_fixture_handler("03_landing_only_no_pdf_anywhere.json"))
    paper = _paper_with_doi("10.9999/synthetic.landing-only")

    plans = adapter.resolve_assets(make_mock_venue(), paper)

    assert plans == []


def test_resolve_assets_closed_produces_no_asset_plan() -> None:
    adapter = _adapter(_fixture_handler("04_closed.json"))
    paper = _paper_with_doi("10.9999/synthetic.closed")

    plans = adapter.resolve_assets(make_mock_venue(), paper)

    assert plans == []


def test_resolve_assets_missing_doi_identifier_raises_config() -> None:
    adapter = UnpaywallAdapter()
    paper = PaperStub(title="T", identifiers=(("arxiv", "2401.00001"),))

    with pytest.raises(CrawlerError) as exc:
        adapter.resolve_assets(make_mock_venue(), paper)
    assert exc.value.error_class is ErrorClass.CONFIG


def test_resolve_assets_not_found_doi_returns_empty_not_an_error() -> None:
    """404（DOI 未收录）→ 该 paper 无 OA 副本，正常空结果，不 raise（§5.5）。"""
    adapter = _adapter(_http_fixture_handler("07_not_found_404.http"))
    paper = _paper_with_doi("10.9999/does-not-exist")

    plans = adapter.resolve_assets(make_mock_venue(), paper)

    assert plans == []


def test_resolve_assets_logs_informal_version_observation(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[dict[str, object]] = []
    monkeypatch.setattr(
        "paper_crawler.adapters.unpaywall.adapter.log_event",
        lambda level, msg, **kw: events.append({"level": level, "msg": msg, **kw}),
    )
    adapter = _adapter(_fixture_handler("02_direct_pdf_hit_hybrid.json"))
    paper = _paper_with_doi("10.9999/synthetic.direct-pdf-hybrid")

    adapter.resolve_assets(make_mock_venue(), paper)

    informal_events = [e for e in events if "informal" in str(e["msg"])]
    assert len(informal_events) == 1
    assert informal_events[0]["version"] == "acceptedVersion"
    assert informal_events[0]["doi"] == "10.9999/synthetic.direct-pdf-hybrid"


def test_resolve_assets_published_version_does_not_log_informal_note(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[dict[str, object]] = []
    monkeypatch.setattr(
        "paper_crawler.adapters.unpaywall.adapter.log_event",
        lambda level, msg, **kw: events.append({"level": level, "msg": msg, **kw}),
    )
    adapter = _adapter(_fixture_handler("06_oa_status_bronze.json"))
    paper = _paper_with_doi("10.9999/synthetic.bronze")

    adapter.resolve_assets(make_mock_venue(), paper)

    assert [e for e in events if "informal" in str(e["msg"])] == []


def test_resolve_assets_logs_oa_landing_url_meta_observation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[dict[str, object]] = []
    monkeypatch.setattr(
        "paper_crawler.adapters.unpaywall.adapter.log_event",
        lambda level, msg, **kw: events.append({"level": level, "msg": msg, **kw}),
    )
    adapter = _adapter(_fixture_handler("03_landing_only_no_pdf_anywhere.json"))
    paper = _paper_with_doi("10.9999/synthetic.landing-only")

    adapter.resolve_assets(make_mock_venue(), paper)

    landing_events = [
        e for e in events if e["msg"] == "unpaywall oa landing only (no pdf link found)"
    ]
    assert len(landing_events) == 1
    assert landing_events[0]["oa_landing_url"] == "https://repo.example.org/landing/landing-only"


# --- lookup：错误映射（422/429/5xx/parse 原样 raise，404 → None）------------------------------


def test_lookup_404_returns_none() -> None:
    adapter = _adapter(_http_fixture_handler("07_not_found_404.http"))
    assert adapter.lookup("10.9999/does-not-exist") is None


def test_lookup_missing_email_422_maps_to_config() -> None:
    adapter = _adapter(_http_fixture_handler("08_missing_email_422.http"))
    with pytest.raises(CrawlerError) as exc:
        adapter.lookup("10.9999/x")
    assert exc.value.error_class is ErrorClass.CONFIG


def test_lookup_ratelimit_429_maps_to_rate_limited_with_retry_after() -> None:
    adapter = _adapter(_http_fixture_handler("09_ratelimit_429.http"))
    with pytest.raises(CrawlerError) as exc:
        adapter.lookup("10.9999/x")
    assert exc.value.error_class is ErrorClass.RATE_LIMITED
    assert "retry_after_s=5" in exc.value.detail


def test_lookup_server_error_500_maps_to_transient() -> None:
    adapter = _adapter(_http_fixture_handler("10_server_error_500.http"))
    with pytest.raises(CrawlerError) as exc:
        adapter.lookup("10.9999/x")
    assert exc.value.error_class is ErrorClass.TRANSIENT


def test_lookup_malformed_json_body_maps_to_parse() -> None:
    adapter = _adapter(_fixture_handler("11_malformed.json"))
    with pytest.raises(CrawlerError) as exc:
        adapter.lookup("10.9999/synthetic.malformed")
    assert exc.value.error_class is ErrorClass.PARSE


def test_lookup_normal_response_round_trips_fields() -> None:
    adapter = _adapter(_fixture_handler("01_normal_gold_fallback.json"))
    record = adapter.lookup(_ANCHOR_DOI)
    assert record is not None
    assert record.doi == _ANCHOR_DOI
    assert record.is_oa is True
    assert record.oa_status == "gold"


# --- URL 构造：email 查询参数 + DOI 路径编码 ---------------------------------------------------


def test_request_url_carries_email_and_doi_path() -> None:
    seen_urls: list[httpx.URL] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_urls.append(request.url)
        return httpx.Response(200, content=fixture_bytes("04_closed.json"))

    adapter = _adapter(handler, email="me@example.com")
    adapter.lookup("10.9999/synthetic.closed")

    assert len(seen_urls) == 1
    url = seen_urls[0]
    assert url.params["email"] == "me@example.com"
    assert str(url).startswith("https://api.unpaywall.org/v2/10.9999/synthetic.closed?")


def test_doi_with_slash_is_preserved_as_path_segments() -> None:
    seen_urls: list[httpx.URL] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_urls.append(request.url)
        return httpx.Response(200, content=fixture_bytes("01_normal_gold_fallback.json"))

    adapter = _adapter(handler)
    adapter.lookup(_ANCHOR_DOI)

    assert seen_urls[0].path == f"/v2/{_ANCHOR_DOI}"


# --- 邮箱注入优先级：显式注入 > 环境变量 > .invalid 占位 ---------------------------------------


def test_email_falls_back_to_env_var_when_not_explicitly_injected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PAPER_CRAWLER_CONTACT_EMAIL", "env-contact@example.com")
    seen_urls: list[httpx.URL] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_urls.append(request.url)
        return httpx.Response(200, content=fixture_bytes("04_closed.json"))

    client = HttpClient(user_agent=_TEST_UA, transport=httpx.MockTransport(handler))
    adapter = UnpaywallAdapter(http=client)  # 无显式 email 注入

    adapter.lookup("10.9999/synthetic.closed")

    assert seen_urls[0].params["email"] == "env-contact@example.com"


def test_email_falls_back_to_invalid_placeholder_when_nothing_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PAPER_CRAWLER_CONTACT_EMAIL", raising=False)
    seen_urls: list[httpx.URL] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_urls.append(request.url)
        return httpx.Response(200, content=fixture_bytes("04_closed.json"))

    client = HttpClient(user_agent=_TEST_UA, transport=httpx.MockTransport(handler))
    adapter = UnpaywallAdapter(http=client)

    adapter.lookup("10.9999/synthetic.closed")

    assert seen_urls[0].params["email"].endswith("@paper-crawler.invalid")


def test_set_email_overrides_previously_injected_value() -> None:
    seen_urls: list[httpx.URL] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_urls.append(request.url)
        return httpx.Response(200, content=fixture_bytes("04_closed.json"))

    adapter = _adapter(handler, email="first@example.com")
    adapter.set_email("second@example.com")
    adapter.lookup("10.9999/synthetic.closed")

    assert seen_urls[0].params["email"] == "second@example.com"


def test_set_http_client_injects_shared_client() -> None:
    adapter = UnpaywallAdapter()
    client = HttpClient(user_agent=_TEST_UA)
    adapter.set_http_client(client)
    assert adapter._client() is client  # noqa: SLF001


def test_lazy_self_build_client_uses_resolved_email_in_user_agent() -> None:
    """无注入 http 时 `_client()` 惰性自建（同 arxiv/openreview 先例）；UA 反映已注入邮箱。"""
    adapter = UnpaywallAdapter(email="lazy@example.com")  # 未注入 http

    client = adapter._client()  # noqa: SLF001

    assert client is adapter._client()  # noqa: SLF001  # 幂等：同一实例复用，不重复自建
    assert "lazy@example.com" in client._client.headers["user-agent"]  # noqa: SLF001


# --- healthcheck：D-019 锚点比对 ---------------------------------------------------------------


def test_healthcheck_matching_anchor_is_healthy() -> None:
    adapter = _adapter(_fixture_handler("01_normal_gold_fallback.json"))
    report = adapter.healthcheck()
    assert report.healthy is True
    assert _ANCHOR_DOI in report.detail


def test_healthcheck_drifted_oa_status_is_unhealthy() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=(
                b'{"is_oa": true, "oa_status": "green", '
                b'"best_oa_location": {"url_for_pdf": null}, "oa_locations": []}'
            ),
        )

    adapter = _adapter(handler)
    report = adapter.healthcheck()
    assert report.healthy is False
    assert "drift" in report.detail


def test_healthcheck_anchor_not_found_is_unhealthy() -> None:
    adapter = _adapter(_http_fixture_handler("07_not_found_404.http"))
    report = adapter.healthcheck()
    assert report.healthy is False
    assert "not found" in report.detail


def test_healthcheck_unreachable_is_unhealthy() -> None:
    adapter = _adapter(_http_fixture_handler("10_server_error_500.http"))
    report = adapter.healthcheck()
    assert report.healthy is False
    assert "unreachable" in report.detail
