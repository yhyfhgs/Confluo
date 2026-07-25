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
from paper_crawler.adapters.crossref.adapter import (
    CrossrefAdapter,
    _date_field_of,
    _default_user_agent,
    _enum_key_of,
)
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


# --- enumerate 日窗（Phase 6 F7：订阅 watch 的日粒度增量窗经 quirks 下推）------------------


def _capture_filters(venue: VenueSpec, issue: IssueRef) -> list[str]:
    """跑一次 enumerate，返回逐请求的 `filter=` 值（首页即空 → 一次请求）。"""
    captured: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(str(request.url.params.get("filter")))
        return _resp(fixture_bytes("02_works_empty.json"))

    list(_adapter(handler).enumerate_issue(venue, issue))
    return captured


def test_day_window_quirk_narrows_the_published_axis_filter() -> None:
    """期刊 watch：`quirks.from/until-pub-date` 把整年窗收成日窗（不再整年枚举）。"""
    venue = _venue().model_copy(
        update={"quirks": {"from-pub-date": "2026-07-19", "until-pub-date": "2026-07-26"}}
    )
    assert _capture_filters(venue, IssueRef(venue_id="qje", year=2026)) == [
        "from-pub-date:2026-07-19,until-pub-date:2026-07-26"
    ]


def test_day_window_quirk_narrows_the_created_axis_filter() -> None:
    """ssrn 走的 created 轴同一通道（键名随 date-field 轴变，无第二张映射表）。"""
    venue = _prefix_venue(prefix="10.2139", venue_id="ssrn", date_field="created").model_copy(
        update={
            "quirks": {
                "crossref_date_field": "created",
                "from-created-date": "2026-07-19",
                "until-created-date": "2026-07-26",
            }
        }
    )
    assert _capture_filters(venue, IssueRef(venue_id="ssrn", year=2026)) == [
        "from-created-date:2026-07-19,until-created-date:2026-07-26"
    ]


def test_day_window_is_intersected_with_the_bucket_year_not_replacing_it() -> None:
    """跨年窗 × 桶年 = 交集：桶年那一侧的边界由年首/年末给，不被窗的另一端顶出去。"""
    venue = _venue().model_copy(
        update={"quirks": {"from-pub-date": "2025-12-26", "until-pub-date": "2026-01-02"}}
    )
    assert _capture_filters(venue, IssueRef(venue_id="qje", year=2025)) == [
        "from-pub-date:2025-12-26,until-pub-date:2025-12-31"
    ]
    assert _capture_filters(venue, IssueRef(venue_id="qje", year=2026)) == [
        "from-pub-date:2026-01-01,until-pub-date:2026-01-02"
    ]


def test_only_one_end_declared_leaves_the_other_at_the_year_boundary() -> None:
    """crossref watch 只推下界（`DateCursor` 无 until_param）——上界仍是年末。"""
    venue = _venue().model_copy(update={"quirks": {"from-pub-date": "2026-07-19"}})
    assert _capture_filters(venue, IssueRef(venue_id="qje", year=2026)) == [
        "from-pub-date:2026-07-19,until-pub-date:2026-12-31"
    ]


def test_day_window_disjoint_from_the_bucket_year_makes_zero_requests() -> None:
    """窗与桶年无交集 → 空序列 + **零请求**（`_never` 不被调用）。"""
    venue = _venue().model_copy(
        update={"quirks": {"from-pub-date": "2026-07-19", "until-pub-date": "2026-07-26"}}
    )
    assert list(_adapter(_never).enumerate_issue(venue, IssueRef(venue_id="qje", year=2024))) == []


def test_invalid_day_window_quirk_raises_config_before_any_request() -> None:
    """畸形日期不许原样拼进 filter=（换回一个 400 看不出是谁写坏的）；急切校验、零请求。"""
    venue = _venue().model_copy(update={"quirks": {"from-pub-date": "2026-07"}})
    with pytest.raises(CrawlerError) as exc:
        list(_adapter(_never).enumerate_issue(venue, IssueRef(venue_id="qje", year=2026)))
    assert exc.value.error_class is ErrorClass.CONFIG
    assert "from-pub-date" in str(exc.value)


def test_no_day_window_quirk_keeps_the_whole_year_window() -> None:
    """零回归：venue YAML 不声明日窗（生产 backfill 主路径）时窗仍是整年。"""
    assert _capture_filters(_venue(), IssueRef(venue_id="qje", year=2024)) == [
        "from-pub-date:2024-01-01,until-pub-date:2024-12-31"
    ]


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


# --- 两轴参数化：enum-key（issn XOR prefix）+ date-field（published|created）（Phase 5 T1）----


def _prefix_venue(
    prefix: str = "10.3386",
    venue_id: str = "nber",
    *,
    date_field: str | None = None,
) -> VenueSpec:
    """构造前缀模式 venue（identifiers.crossref_prefix + 可选 quirks.crossref_date_field）。"""
    quirks: dict[str, object] = {}
    if date_field is not None:
        quirks["crossref_date_field"] = date_field
    return VenueSpec(
        id=venue_id,
        kind="preprint_channel",
        names={"full": "NBER Working Papers", "aliases": ["NBER"]},
        field=["econ"],
        identifiers={"crossref_prefix": prefix},
        metadata_source="crossref",
        fulltext_source="mock_platform",
        quirks=quirks,
    )


def _both_keys_venue() -> VenueSpec:
    return VenueSpec(
        id="ambiguous",
        kind="journal",
        names={"full": "Ambiguous"},
        field=["econ"],
        identifiers={"issn": ["0033-5533"], "crossref_prefix": "10.3386"},
        metadata_source="crossref",
        fulltext_source="mock_platform",
    )


# -- enum-key XOR 校验（_enum_key_of 直测）--


def test_enum_key_issn_only() -> None:
    assert _enum_key_of(_venue(issn="0033-5533")) == ("issn", "0033-5533")


def test_enum_key_prefix_only() -> None:
    assert _enum_key_of(_prefix_venue(prefix="10.3386")) == ("prefix", "10.3386")


def test_enum_key_both_present_raises_config() -> None:
    """issn + crossref_prefix 同现（歧义）→ CONFIG 响亮（XOR 校验）。"""
    with pytest.raises(CrawlerError) as exc:
        _enum_key_of(_both_keys_venue())
    assert exc.value.error_class is ErrorClass.CONFIG
    assert "XOR" in str(exc.value)


def test_enum_key_neither_present_raises_config() -> None:
    """issn 与 crossref_prefix 都缺（无枚举键）→ CONFIG 响亮。"""
    venue = VenueSpec(
        id="no_key",
        kind="journal",
        names={"full": "No Key"},
        field=["econ"],
        identifiers={},
        metadata_source="crossref",
        fulltext_source="mock_platform",
    )
    with pytest.raises(CrawlerError) as exc:
        _enum_key_of(venue)
    assert exc.value.error_class is ErrorClass.CONFIG


def test_enum_key_malformed_issn_no_prefix_raises_config() -> None:
    """畸形 issn（空 list）+ 无 prefix → 视作都缺 → CONFIG（畸形 issn 非有效枚举键）。"""
    venue = VenueSpec(
        id="bad_issn",
        kind="journal",
        names={"full": "Bad ISSN"},
        field=["econ"],
        identifiers={"issn": []},
        metadata_source="crossref",
        fulltext_source="mock_platform",
    )
    with pytest.raises(CrawlerError) as exc:
        _enum_key_of(venue)
    assert exc.value.error_class is ErrorClass.CONFIG


# -- date-field（_date_field_of 直测）--


def test_date_field_defaults_published() -> None:
    assert _date_field_of(_venue()) == "published"


def test_date_field_created_from_quirk() -> None:
    assert _date_field_of(_prefix_venue(prefix="10.2139", date_field="created")) == "created"


def test_date_field_explicit_published_from_quirk() -> None:
    assert _date_field_of(_prefix_venue(date_field="published")) == "published"


def test_date_field_invalid_raises_config() -> None:
    """未知 date-field 值 → CONFIG 响亮（防拼写错 / 非法轴）。"""
    with pytest.raises(CrawlerError) as exc:
        _date_field_of(_prefix_venue(date_field="modified"))
    assert exc.value.error_class is ErrorClass.CONFIG


# -- prefix URL 构造（facet + works，两轴分派）--


def test_prefix_facet_url_shape_published() -> None:
    """nber = prefix 10.3386 + published：/prefixes/10.3386/works，facet=published:*。"""
    captured: list[httpx.URL] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request.url)
        return _resp(fixture_bytes("05_facet_published.json"))

    list(_adapter(handler).discover_timeline(_prefix_venue(prefix="10.3386")))
    url = captured[0]
    assert url.path == "/prefixes/10.3386/works"
    assert url.params.get("facet") == "published:*"


def test_prefix_facet_url_shape_created() -> None:
    """ssrn = prefix 10.2139 + created：/prefixes/10.2139/works，facet=created:*。"""
    captured: list[httpx.URL] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request.url)
        return _resp(fixture_bytes("13_facet_created.json"))

    list(
        _adapter(handler).discover_timeline(
            _prefix_venue(prefix="10.2139", venue_id="ssrn", date_field="created")
        )
    )
    url = captured[0]
    assert url.path == "/prefixes/10.2139/works"
    assert url.params.get("facet") == "created:*"


def test_prefix_works_url_created_filter() -> None:
    """created 轴：filter from-created-date/until-created-date；基址 /prefixes/。"""
    captured: list[httpx.URL] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request.url)
        return _resp(fixture_bytes("02_works_empty.json"))

    list(
        _adapter(handler).enumerate_issue(
            _prefix_venue(prefix="10.2139", venue_id="ssrn", date_field="created"),
            IssueRef(venue_id="ssrn", year=2024),
        )
    )
    url = captured[0]
    assert url.path == "/prefixes/10.2139/works"
    assert url.params.get("filter") == "from-created-date:2024-01-01,until-created-date:2024-12-31"
    assert url.params.get("cursor") == "*"


def test_prefix_works_url_published_filter() -> None:
    """prefix + published（nber）：works filter=from-pub-date（pub 缩写），基址 /prefixes/。"""
    captured: list[httpx.URL] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request.url)
        return _resp(fixture_bytes("02_works_empty.json"))

    list(
        _adapter(handler).enumerate_issue(
            _prefix_venue(prefix="10.3386"), IssueRef(venue_id="nber", year=2022)
        )
    )
    url = captured[0]
    assert url.path == "/prefixes/10.3386/works"
    assert url.params.get("filter") == "from-pub-date:2022-01-01,until-pub-date:2022-12-31"


# -- prefix 发现 / 枚举 完整流 --


def test_prefix_discover_created_yields_year_issue_refs() -> None:
    issues = list(
        _adapter(lambda r: _resp(fixture_bytes("13_facet_created.json"))).discover_timeline(
            _prefix_venue(prefix="10.2139", venue_id="ssrn", date_field="created")
        )
    )
    assert [i.year for i in issues] == [2024, 2025, 2026]
    assert [i.paper_count_claimed for i in issues] == [210417, 251908, 152340]
    assert all(i.venue_id == "ssrn" for i in issues)


def test_prefix_enumerate_yields_stubs_to_paper_stub_unchanged() -> None:
    responses = iter(["14_works_prefix.json", "02_works_empty.json"])

    def handler(request: httpx.Request) -> httpx.Response:
        return _resp(fixture_bytes(next(responses)))

    stubs = list(
        _adapter(handler).enumerate_issue(
            _prefix_venue(prefix="10.3386"), IssueRef(venue_id="nber", year=2022)
        )
    )
    assert [s.identifiers[0][1] for s in stubs] == ["10.3386/w30000", "10.3386/w30001"]
    # to_paper_stub 零改：identifiers 仍仅 (doi,)（第二 identifier 增补属 T4 消费侧，非本卡）。
    assert all(s.identifiers == (("doi", s.identifiers[0][1]),) for s in stubs)


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
