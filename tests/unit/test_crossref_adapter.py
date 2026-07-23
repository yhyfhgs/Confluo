"""crossref/adapter.py 单测（MockTransport 注入，零真实网络；aggregators.md §5.1）。

覆盖：discover facet 逐年 IssueRef + since 过滤、enumerate cursor 两页续拉 + 终止、
首页 total>0 items 空 → PARSE、合法空窗、title/DOI 跳过 obslog、healthcheck（PENDING
结构态 / 精确匹配 / 漂移 / 空 title / 不可达）、错误映射（429/400/500 经 HttpClient）、
URL 构造、CONFIG 早失败（缺 issn/year/非法 since）、HttpClient 注入与惰性自建。
"""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from helpers.crossref_fixtures import fixture_bytes, http_fixture
from paper_crawler.adapters.crossref.adapter import CrossrefAdapter, _default_user_agent
from paper_crawler.errors import CrawlerError, ErrorClass
from paper_crawler.http import HttpClient
from paper_crawler.types import IssueRef, VenueSpec

_UA = "PaperCrawler/test (personal research; mailto:test@example.com)"
Handler = Callable[[httpx.Request], httpx.Response]


def _adapter(handler: Handler) -> CrossrefAdapter:
    client = HttpClient(user_agent=_UA, transport=httpx.MockTransport(handler))
    return CrossrefAdapter(http=client)


def _resp(body: bytes, status: int = 200) -> httpx.Response:
    return httpx.Response(status, content=body)


def _venue(issn: str = "0033-5533", venue_id: str = "qje") -> VenueSpec:
    return VenueSpec(
        id=venue_id,
        kind="journal",
        names={"full": "Quarterly Journal of Economics", "aliases": ["QJE"]},
        field=["econ"],
        identifiers={"issn": [issn]},
        metadata_source="crossref",
        fulltext_source="mock_platform",
    )


def _never(_request: httpx.Request) -> httpx.Response:
    raise AssertionError("no network expected for this path (eager CONFIG check)")


# --- discover（facet 逐年）------------------------------------------------------------------


def test_discover_yields_year_issue_refs() -> None:
    issues = list(
        _adapter(lambda r: _resp(fixture_bytes("05_facet_published.json"))).discover_timeline(
            _venue()
        )
    )
    assert [i.year for i in issues] == [2022, 2023, 2024]  # 升序
    assert [i.paper_count_claimed for i in issues] == [41, 44, 46]
    assert [i.label for i in issues] == ["2022", "2023", "2024"]
    assert all(i.venue_id == "qje" for i in issues)
    assert all(i.volume is None and i.number is None for i in issues)


def test_discover_since_filters_years() -> None:
    issues = list(
        _adapter(lambda r: _resp(fixture_bytes("05_facet_published.json"))).discover_timeline(
            _venue(), since="2023"
        )
    )
    assert [i.year for i in issues] == [2023, 2024]


def test_discover_since_accepts_full_date_prefix() -> None:
    issues = list(
        _adapter(lambda r: _resp(fixture_bytes("05_facet_published.json"))).discover_timeline(
            _venue(), since="2024-06-01"
        )
    )
    assert [i.year for i in issues] == [2024]


def test_discover_missing_issn_raises_config() -> None:
    venue = VenueSpec(
        id="no_issn",
        kind="journal",
        names={"full": "No ISSN"},
        field=["econ"],
        identifiers={},
        metadata_source="crossref",
        fulltext_source="mock_platform",
    )
    with pytest.raises(CrawlerError) as exc:
        list(_adapter(_never).discover_timeline(venue))
    assert exc.value.error_class is ErrorClass.CONFIG


def test_discover_invalid_since_raises_config() -> None:
    with pytest.raises(CrawlerError) as exc:
        list(_adapter(_never).discover_timeline(_venue(), since="not-a-year"))
    assert exc.value.error_class is ErrorClass.CONFIG


def test_facet_url_shape() -> None:
    captured: list[httpx.URL] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request.url)
        return _resp(fixture_bytes("05_facet_published.json"))

    list(_adapter(handler).discover_timeline(_venue(issn="0033-5533")))
    url = captured[0]
    assert url.path == "/journals/0033-5533/works"
    assert url.params.get("rows") == "0"
    assert url.params.get("facet") == "published:*"


# --- enumerate（cursor 深翻）---------------------------------------------------------------


def test_enumerate_cursor_two_page_continuation() -> None:
    calls: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        cursor = request.url.params.get("cursor")
        calls.append(cursor)
        if cursor == "*":
            return _resp(fixture_bytes("04a_works_cursor_page1.json"))
        return _resp(fixture_bytes("04b_works_cursor_page2.json"))

    stubs = list(_adapter(handler).enumerate_issue(_venue(), IssueRef(venue_id="qje", year=2024)))
    assert [s.identifiers[0][1] for s in stubs] == ["10.1093/qje/qjae010", "10.1093/qje/qjae011"]
    # 两次请求：首页 cursor=* → 续页用 page1 的 next-cursor → page2 items 空终止。
    assert calls == ["*", "AoJ4sample4cursor4page2"]


def test_enumerate_url_has_filter_rows_cursor() -> None:
    captured: list[httpx.URL] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request.url)
        return _resp(fixture_bytes("02_works_empty.json"))

    list(
        _adapter(handler).enumerate_issue(
            _venue(issn="0033-5533"), IssueRef(venue_id="qje", year=2024)
        )
    )
    url = captured[0]
    assert url.path == "/journals/0033-5533/works"
    assert url.params.get("filter") == "from-pub-date:2024-01-01,until-pub-date:2024-12-31"
    assert url.params.get("rows") == "1000"
    assert url.params.get("cursor") == "*"


def test_enumerate_first_page_total_gt0_items_empty_raises_parse() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _resp(fixture_bytes("07_works_total_mismatch.json"))

    with pytest.raises(CrawlerError) as exc:
        list(_adapter(handler).enumerate_issue(_venue(), IssueRef(venue_id="qje", year=2024)))
    assert exc.value.error_class is ErrorClass.PARSE


def test_enumerate_empty_window_total_zero_yields_nothing() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _resp(fixture_bytes("02_works_empty.json"))

    stubs = list(_adapter(handler).enumerate_issue(_venue(), IssueRef(venue_id="qje", year=2024)))
    assert stubs == []


def test_enumerate_page_with_skips_yields_valid_and_terminates() -> None:
    responses = iter(["01_works_normal.json", "02_works_empty.json"])

    def handler(request: httpx.Request) -> httpx.Response:
        return _resp(fixture_bytes(next(responses)))

    stubs = list(_adapter(handler).enumerate_issue(_venue(), IssueRef(venue_id="qje", year=2024)))
    # 01 有 3 有效记录（2 跳过），next-cursor → 续 02（空）终止。
    assert len(stubs) == 3


def test_enumerate_skips_are_logged(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[dict[str, object]] = []

    def _capture(level: str, msg: str, **extra: object) -> None:
        events.append({"msg": msg, **extra})

    monkeypatch.setattr("paper_crawler.adapters.crossref.adapter.log_event", _capture)
    responses = iter(["01_works_normal.json", "02_works_empty.json"])

    def handler(request: httpx.Request) -> httpx.Response:
        return _resp(fixture_bytes(next(responses)))

    list(_adapter(handler).enumerate_issue(_venue(), IssueRef(venue_id="qje", year=2024)))
    skip_events = [e for e in events if e["msg"] == "crossref records skipped"]
    assert len(skip_events) == 1
    assert skip_events[0]["skipped_untitled"] == 1
    assert skip_events[0]["skipped_doiless"] == 1
    assert skip_events[0]["venue"] == "qje"


def test_enumerate_missing_year_raises_config() -> None:
    with pytest.raises(CrawlerError) as exc:
        list(_adapter(_never).enumerate_issue(_venue(), IssueRef(venue_id="qje")))
    assert exc.value.error_class is ErrorClass.CONFIG


# --- 错误映射（经 HttpClient 状态映射）-----------------------------------------------------


def test_enumerate_429_maps_rate_limited_with_retry_after() -> None:
    status, headers, body = http_fixture("03_works_429.http")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, headers=headers, content=body)

    with pytest.raises(CrawlerError) as exc:
        list(_adapter(handler).enumerate_issue(_venue(), IssueRef(venue_id="qje", year=2024)))
    assert exc.value.error_class is ErrorClass.RATE_LIMITED
    assert "retry_after_s=5" in exc.value.detail


def test_enumerate_400_maps_config() -> None:
    status, headers, body = http_fixture("08_400_bad_filter.http")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, headers=headers, content=body)

    with pytest.raises(CrawlerError) as exc:
        list(_adapter(handler).enumerate_issue(_venue(), IssueRef(venue_id="qje", year=2024)))
    assert exc.value.error_class is ErrorClass.CONFIG


def test_enumerate_500_maps_transient() -> None:
    status, headers, body = http_fixture("09_500.http")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, headers=headers, content=body)

    with pytest.raises(CrawlerError) as exc:
        list(_adapter(handler).enumerate_issue(_venue(), IssueRef(venue_id="qje", year=2024)))
    assert exc.value.error_class is ErrorClass.TRANSIENT


# --- healthcheck -----------------------------------------------------------------------------


def test_healthcheck_golden_title_match_healthy() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url).endswith("/works/10.1038/nature14539")
        return _resp(fixture_bytes("06_works_healthcheck.json"))

    report = _adapter(handler).healthcheck()
    assert report.healthy is True


def test_healthcheck_exact_match_when_golden_captured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "paper_crawler.adapters.crossref.adapter._HEALTHCHECK_TITLE",
        "Deep learning",  # golden 已转正（[LIVE] 2026-07-23），与 fixture 真值一致
    )
    report = _adapter(lambda r: _resp(fixture_bytes("06_works_healthcheck.json"))).healthcheck()
    assert report.healthy is True
    assert "matched" in report.detail


def test_healthcheck_drift_when_title_differs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "paper_crawler.adapters.crossref.adapter._HEALTHCHECK_TITLE", "A Different Expected Title"
    )
    report = _adapter(lambda r: _resp(fixture_bytes("06_works_healthcheck.json"))).healthcheck()
    assert report.healthy is False
    assert "drift" in report.detail


def test_healthcheck_empty_title_unhealthy_parse() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = b'{"status":"ok","message-type":"work","message":{"DOI":"10.1/x","title":[]}}'
        return _resp(body)

    report = _adapter(handler).healthcheck()
    assert report.healthy is False
    assert "parse" in report.detail.lower()


def test_healthcheck_unreachable_unhealthy() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="down")

    report = _adapter(handler).healthcheck()
    assert report.healthy is False
    assert "unreachable" in report.detail


# --- HttpClient 注入 / 惰性自建 / UA ---------------------------------------------------------


def test_set_http_client_injects() -> None:
    adapter = CrossrefAdapter()
    client = HttpClient(user_agent=_UA)
    adapter.set_http_client(client)
    assert adapter._client() is client


def test_lazy_client_built_and_cached_without_injection() -> None:
    adapter = CrossrefAdapter()  # http=None
    client = adapter._client()  # 惰性自建（仅构造，不发请求 → 零网络）
    assert isinstance(client, HttpClient)
    assert adapter._client() is client  # 缓存


def test_default_user_agent_uses_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PAPER_CRAWLER_CONTACT_EMAIL", "real@example.org")
    ua = _default_user_agent()
    assert "mailto:real@example.org" in ua


def test_default_user_agent_placeholder_when_env_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PAPER_CRAWLER_CONTACT_EMAIL", raising=False)
    assert ".invalid" in _default_user_agent()


# --- lookup（grab 单篇元数据；Phase 4 T5 引入，T8 补直接单测）-----------------------------------


def test_lookup_success_returns_paper_stub() -> None:
    """`GET /works/{doi}` 命中 → `PaperStub`（title/doi/year 正确映射）。"""
    adapter = _adapter(lambda _req: _resp(fixture_bytes("06_works_healthcheck.json")))
    stub = adapter.lookup("10.1038/nature14539")
    assert stub is not None
    assert stub.title == "Deep learning"
    assert ("doi", "10.1038/nature14539") in stub.identifiers
    assert stub.year == 2015


def test_lookup_404_gone_returns_none() -> None:
    """404（DOI 未收录）→ GONE → `None`（正常空结果，非异常；同 unpaywall 口径）。"""
    adapter = _adapter(lambda _req: _resp(b'{"message":"Resource not found."}', status=404))
    assert adapter.lookup("10.9999/nonexistent") is None


def test_lookup_missing_title_returns_none() -> None:
    """work 缺 title（无强合并锚点）→ `None`（不造无锚点 stub）。"""
    body = b'{"status":"ok","message-type":"work","message":{"DOI":"10.1/x"}}'
    adapter = _adapter(lambda _req: _resp(body))
    assert adapter.lookup("10.1/x") is None
