"""ArxivAdapter 主体单测（design/adapters/arxiv.md §3-§6；T5）。

零真实网络：网络型方法（enumerate/fetch/healthcheck）经 `HttpClient(transport=
httpx.MockTransport(...))` 注入受控响应；纯逻辑方法（discover/resolve）无 http 依赖。
用内联 XML 覆盖 adapter 主体逻辑（分页/子分类过滤/墓碑观测/窗口构造/错误映射/
gone 嗅探/canary 比对）；真实响应结构的八件套 fixture 由集成/契约层加载（fixtures/arxiv/）。
"""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from helpers import FakeFetchIO, make_arxiv_venue
from paper_crawler.adapters.arxiv.adapter import ArxivAdapter, build_user_agent
from paper_crawler.errors import CrawlerError, ErrorClass
from paper_crawler.http import HttpClient
from paper_crawler.types import AssetKind, AuthLevel, Capability, IssueRef, PaperStub, UrlStrategy

_TEST_UA = "PaperCrawler/test (personal research; mailto:test@example.com)"

Handler = Callable[[httpx.Request], httpx.Response]


def _adapter(handler: Handler) -> ArxivAdapter:
    client = HttpClient(user_agent=_TEST_UA, transport=httpx.MockTransport(handler))
    return ArxivAdapter(http=client)


def _bucket(*, year: int = 2024, number: str = "01") -> IssueRef:
    """一个月度桶 IssueRef（形如 buckets.month_buckets 的产物）。"""
    return IssueRef(
        venue_id="arxiv_cs_lg",
        volume=None,
        number=number,
        year=year,
        label=f"{year:04d}-{number}",
        paper_count_claimed=None,
    )


# --- 内联 XML fixtures ------------------------------------------------------------------------

# 第一页：cs.LG 命中 + 1 墓碑(deleted) + cs.CL(被子分类过滤排除) + resumptionToken。
_OAI_PAGE1 = b"""<?xml version="1.0" encoding="UTF-8"?>
<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">
<responseDate>2024-02-01T00:00:00Z</responseDate>
<request verb="ListRecords" from="2024-01-01" until="2024-01-31" metadataPrefix="arXiv" set="cs">http://oaipmh.arxiv.org/oai</request>
<ListRecords>
<record>
<header><identifier>oai:arXiv.org:2401.00001</identifier><datestamp>2024-01-05</datestamp><setSpec>cs</setSpec></header>
<metadata><arXiv xmlns="http://arxiv.org/OAI/arXiv/">
<id>2401.00001</id><created>2024-01-05</created>
<authors><author><keyname>Turing</keyname><forenames>Alan</forenames></author></authors>
<title>A Kept CS Learning Paper</title><categories>cs.LG stat.ML</categories>
<abstract>Kept.</abstract></arXiv></metadata>
</record>
<record>
<header status="deleted"><identifier>oai:arXiv.org:2401.00099</identifier>
<datestamp>2024-01-06</datestamp></header>
</record>
<record>
<header><identifier>oai:arXiv.org:2401.00003</identifier><datestamp>2024-01-07</datestamp></header>
<metadata><arXiv xmlns="http://arxiv.org/OAI/arXiv/">
<id>2401.00003</id><created>2024-01-07</created>
<title>A Filtered Out Computation And Language Paper</title>
<categories>cs.CL</categories></arXiv></metadata>
</record>
<resumptionToken cursor="0" completeListSize="3">tok-page2</resumptionToken>
</ListRecords>
</OAI-PMH>
"""

# 第二页：老格式 id（cs.LG/0501001）命中；无 token（收割结束）。
_OAI_PAGE2 = b"""<?xml version="1.0" encoding="UTF-8"?>
<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">
<responseDate>2024-02-01T00:00:00Z</responseDate>
<request verb="ListRecords" resumptionToken="tok-page2">http://oaipmh.arxiv.org/oai</request>
<ListRecords>
<record>
<header><identifier>oai:arXiv.org:cs.LG/0501001</identifier><datestamp>2024-01-08</datestamp></header>
<metadata><arXiv xmlns="http://arxiv.org/OAI/arXiv/">
<id>cs.LG/0501001</id><created>2005-01-03</created>
<title>An Old Style Learning Paper</title><categories>cs.LG</categories></arXiv></metadata>
</record>
</ListRecords>
</OAI-PMH>
"""

_OAI_NO_RECORDS_MATCH = b"""<?xml version="1.0" encoding="UTF-8"?>
<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">
<responseDate>2024-02-01T00:00:00Z</responseDate>
<request verb="ListRecords">http://oaipmh.arxiv.org/oai</request>
<error code="noRecordsMatch">Empty window.</error>
</OAI-PMH>
"""

_OAI_BAD_RESUMPTION = b"""<?xml version="1.0" encoding="UTF-8"?>
<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">
<responseDate>2024-02-01T00:00:00Z</responseDate>
<request verb="ListRecords">http://oaipmh.arxiv.org/oai</request>
<error code="badResumptionToken">Expired.</error>
</OAI-PMH>
"""

# Query API Atom：3 条 canary（与 adapter._CANARIES 对齐；一元素一行以内避免超长）。
_ATOM_HEALTHCHECK = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
<entry>
<id>http://arxiv.org/abs/2401.00001v1</id>
<title>A Robust Canary for Machine Learning</title>
<arxiv:primary_category term="cs.LG" scheme="http://arxiv.org/schemas/atom"/>
</entry>
<entry>
<id>http://arxiv.org/abs/2312.00002v1</id>
<title>An Econometrics Canary for Empirical Methods</title>
<arxiv:primary_category term="econ.EM" scheme="http://arxiv.org/schemas/atom"/>
</entry>
<entry>
<id>http://arxiv.org/abs/2311.00003v2</id>
<title>A Quantitative Finance Canary on Pricing</title>
<arxiv:primary_category term="q-fin.PR" scheme="http://arxiv.org/schemas/atom"/>
</entry>
</feed>
"""


# --- 元数据 ----------------------------------------------------------------------------------


def test_adapter_metadata_matches_arxiv_md_verdicts() -> None:
    a = ArxivAdapter()
    assert a.adapter_id == "arxiv"
    assert a.family == "open_access"
    # arxiv.md §1：无 SEARCH。
    assert a.capabilities == (
        Capability.DISCOVER | Capability.ENUMERATE | Capability.RESOLVE | Capability.FETCH
    )
    assert Capability.SEARCH not in a.capabilities
    assert a.auth_requirement == AuthLevel.NONE
    assert a.domains == ("export.arxiv.org", "oaipmh.arxiv.org", "arxiv.org")
    # 1 req/3s = 20 rpm；source_note 出处强制（ToU）。
    assert a.default_rate.requests_per_minute == 20.0
    assert "Terms of Use" in a.default_rate.source_note


def test_build_user_agent_is_d014_shaped() -> None:
    ua = build_user_agent("me@example.com", version="9.9.9")
    assert ua == "PaperCrawler/9.9.9 (personal research; mailto:me@example.com)"


def test_build_user_agent_omits_mailto_when_email_none() -> None:
    """config `[identity].email` 未配置（None）→ UA 省略 mailto 段（不硬编码占位地址）。"""
    ua = build_user_agent(None, version="9.9.9")
    assert ua == "PaperCrawler/9.9.9 (personal research)"


def test_build_user_agent_omits_mailto_when_email_empty() -> None:
    """空串等价未配置（防御性）——同样省略 mailto 段。"""
    assert build_user_agent("", version="9.9.9") == "PaperCrawler/9.9.9 (personal research)"


def test_set_http_client_injection_overrides_lazy_env_build() -> None:
    """`set_http_client` 注入的 client 优先于惰性 env 兜底（显式注入 > config > env）。"""
    adapter = ArxivAdapter()  # http=None：否则会惰性自建
    injected = HttpClient(user_agent=_TEST_UA)
    adapter.set_http_client(injected)
    # 私有字段验证注入生效（_client() 不再惰性自建）。
    assert adapter._client() is injected


# --- discover（零网络）------------------------------------------------------------------------


def test_discover_yields_monthly_buckets_from_inception() -> None:
    # http=None 且不触发网络：discover 纯本地。
    issues = list(ArxivAdapter().discover_timeline(make_arxiv_venue()))
    assert issues  # inception 2024-01 <= 今日 → 非空
    first = issues[0]
    assert first.venue_id == "arxiv_cs_lg"
    assert first.label == "2024-01"
    assert first.volume is None
    assert first.number == "01"
    assert first.year == 2024
    assert first.paper_count_claimed is None
    # 连续月份 + 全部 <= 今日（不钉死数量，避免钟表脆弱）。
    labels = [i.label for i in issues]
    assert labels == sorted(labels)
    assert len(set(labels)) == len(labels)


def test_discover_falls_back_to_global_inception_when_quirk_absent() -> None:
    venue = make_arxiv_venue()
    venue.quirks.pop("inception")
    first = next(iter(ArxivAdapter().discover_timeline(venue)))
    assert first.label == "1991-08"  # arXiv 全局起点


def test_discover_future_inception_is_empty_not_error() -> None:
    assert list(ArxivAdapter().discover_timeline(make_arxiv_venue(inception="2099-01"))) == []


def test_discover_since_narrows_start_month() -> None:
    venue = make_arxiv_venue(inception="2020-01")
    first = next(iter(ArxivAdapter().discover_timeline(venue, since="2023-06-15")))
    assert first.label == "2023-06"


# --- resolve（零网络）-------------------------------------------------------------------------


def test_resolve_builds_latest_version_pdf_plan_new_style_id() -> None:
    paper = PaperStub(title="T", identifiers=(("arxiv", "2401.00001"),))
    plans = ArxivAdapter().resolve_assets(make_arxiv_venue(), paper)
    assert len(plans) == 1
    plan = plans[0]
    assert plan.kind is AssetKind.PDF
    assert plan.url == "https://arxiv.org/pdf/2401.00001"
    assert plan.version is None  # 最新版语义
    assert plan.url_strategy is UrlStrategy.DIRECT
    assert plan.auth_needed is AuthLevel.NONE


def test_resolve_old_style_id_keeps_slash_in_pdf_url() -> None:
    paper = PaperStub(title="T", identifiers=(("arxiv", "hep-th/9901001"),))
    plans = ArxivAdapter().resolve_assets(make_arxiv_venue(), paper)
    assert plans[0].url == "https://arxiv.org/pdf/hep-th/9901001"


def test_resolve_without_arxiv_identifier_is_config_error() -> None:
    paper = PaperStub(title="T", identifiers=(("doi", "10.1/x"),))
    with pytest.raises(CrawlerError) as exc:
        ArxivAdapter().resolve_assets(make_arxiv_venue(), paper)
    assert exc.value.error_class is ErrorClass.CONFIG


# --- enumerate（OAI-PMH）----------------------------------------------------------------------


def test_enumerate_pages_through_resumption_token_and_filters_subcategory() -> None:
    seen_urls: list[httpx.URL] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_urls.append(request.url)
        if "resumptionToken" in request.url.params:
            return httpx.Response(200, content=_OAI_PAGE2)
        return httpx.Response(200, content=_OAI_PAGE1)

    stubs = list(_adapter(handler).enumerate_issue(make_arxiv_venue(), _bucket()))

    # cs.LG 命中 2 条（新+老格式）；cs.CL 被子分类过滤、deleted 墓碑被跳过。
    assert [dict(s.identifiers)["arxiv"] for s in stubs] == ["2401.00001", "cs.lg/0501001"]
    # 首请求带月度桶窗口 + set=cs + metadataPrefix；次请求带 resumptionToken。
    first = seen_urls[0]
    assert first.params["set"] == "cs"
    assert first.params["from"] == "2024-01-01"
    assert first.params["until"] == "2024-01-31"
    assert first.params["metadataPrefix"] == "arXiv"
    assert seen_urls[1].params["resumptionToken"] == "tok-page2"


def test_enumerate_logs_tombstone_skip_debug_event(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[dict[str, object]] = []
    monkeypatch.setattr(
        "paper_crawler.adapters.arxiv.adapter.log_event",
        lambda level, msg, **kw: events.append({"level": level, "msg": msg, **kw}),
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if "resumptionToken" in request.url.params:
            return httpx.Response(200, content=_OAI_PAGE2)
        return httpx.Response(200, content=_OAI_PAGE1)

    list(_adapter(handler).enumerate_issue(make_arxiv_venue(), _bucket()))

    tombstone_events = [e for e in events if e["msg"] == "oai tombstones skipped"]
    assert len(tombstone_events) == 1
    ev = tombstone_events[0]
    assert ev["level"] == "DEBUG"
    assert ev["venue"] == "arxiv_cs_lg"
    assert ev["stage"] == "enumerate"
    assert ev["bucket"] == "2024-01"
    assert ev["skipped_tombstones"] == 1


def test_enumerate_no_records_match_completes_empty() -> None:
    handler: Handler = lambda request: httpx.Response(200, content=_OAI_NO_RECORDS_MATCH)  # noqa: E731
    assert list(_adapter(handler).enumerate_issue(make_arxiv_venue(), _bucket())) == []


def test_enumerate_without_subcategory_keeps_all_records() -> None:
    # venue 无 arxiv_category（只 arxiv_set）→ 不做子分类过滤（cs.CL 也留下）。
    venue = make_arxiv_venue()
    venue.quirks.pop("arxiv_category")

    def handler(request: httpx.Request) -> httpx.Response:
        if "resumptionToken" in request.url.params:
            return httpx.Response(200, content=_OAI_PAGE2)
        return httpx.Response(200, content=_OAI_PAGE1)

    ids_out = [
        dict(s.identifiers)["arxiv"] for s in _adapter(handler).enumerate_issue(venue, _bucket())
    ]
    assert ids_out == ["2401.00001", "2401.00003", "cs.lg/0501001"]


@pytest.mark.parametrize(
    ("status", "content", "expected"),
    [
        (503, _OAI_NO_RECORDS_MATCH, ErrorClass.RATE_LIMITED),  # 503+Retry-After
        (400, _OAI_NO_RECORDS_MATCH, ErrorClass.CONFIG),  # offset>30000 类
    ],
)
def test_enumerate_http_error_status_maps_to_error_class(
    status: int, content: bytes, expected: ErrorClass
) -> None:
    headers = {"Retry-After": "120"} if status == 503 else {}
    handler: Handler = lambda request: httpx.Response(status, headers=headers, content=content)  # noqa: E731
    with pytest.raises(CrawlerError) as exc:
        list(_adapter(handler).enumerate_issue(make_arxiv_venue(), _bucket()))
    assert exc.value.error_class is expected


def test_enumerate_bad_resumption_token_is_transient() -> None:
    handler: Handler = lambda request: httpx.Response(200, content=_OAI_BAD_RESUMPTION)  # noqa: E731
    with pytest.raises(CrawlerError) as exc:
        list(_adapter(handler).enumerate_issue(make_arxiv_venue(), _bucket()))
    assert exc.value.error_class is ErrorClass.TRANSIENT


def test_enumerate_non_monthly_issue_is_config_error() -> None:
    handler: Handler = lambda request: httpx.Response(200, content=_OAI_PAGE1)  # noqa: E731
    bad_issue = IssueRef(venue_id="arxiv_cs_lg", number=None, year=None)
    with pytest.raises(CrawlerError) as exc:
        list(_adapter(handler).enumerate_issue(make_arxiv_venue(), bad_issue))
    assert exc.value.error_class is ErrorClass.CONFIG


def test_enumerate_current_month_bucket_caps_until_at_today() -> None:
    from datetime import UTC, datetime

    today = datetime.now(UTC).date()
    seen: list[httpx.URL] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url)
        return httpx.Response(200, content=_OAI_NO_RECORDS_MATCH)

    current = _bucket(year=today.year, number=f"{today.month:02d}")
    list(_adapter(handler).enumerate_issue(make_arxiv_venue(), current))
    assert seen[0].params["from"] == today.replace(day=1).isoformat()
    assert seen[0].params["until"] == today.isoformat()  # 收窄到今日（watch 整窗）


# --- fetch（流式 + gone 嗅探）-----------------------------------------------------------------


def test_fetch_streams_pdf_bytes_ok() -> None:
    pdf = b"%PDF-1.5\n" + b"payload-bytes " * 64 + b"\n%%EOF\n"
    handler: Handler = lambda request: httpx.Response(200, content=pdf)  # noqa: E731
    plan = ArxivAdapter().resolve_assets(
        make_arxiv_venue(), PaperStub(title="T", identifiers=(("arxiv", "2401.00001"),))
    )[0]
    io = FakeFetchIO()
    result = _adapter(handler).fetch_asset(plan, io)
    assert result.ok is True
    assert result.bytes_written == len(pdf)
    assert io.data == pdf
    assert io.data.startswith(b"%PDF")


def test_fetch_html_withdrawn_page_is_gone() -> None:
    html = b"<!DOCTYPE html>\n<html><head><title>Withdrawn</title></head><body>gone</body></html>"
    handler: Handler = lambda request: httpx.Response(200, content=html)  # noqa: E731
    plan = ArxivAdapter().resolve_assets(
        make_arxiv_venue(), PaperStub(title="T", identifiers=(("arxiv", "2401.09999"),))
    )[0]
    with pytest.raises(CrawlerError) as exc:
        _adapter(handler).fetch_asset(plan, FakeFetchIO())
    assert exc.value.error_class is ErrorClass.GONE


def test_fetch_http_404_is_gone_via_httpclient() -> None:
    handler: Handler = lambda request: httpx.Response(404, content=b"not found")  # noqa: E731
    plan = ArxivAdapter().resolve_assets(
        make_arxiv_venue(), PaperStub(title="T", identifiers=(("arxiv", "2401.09999"),))
    )[0]
    with pytest.raises(CrawlerError) as exc:
        _adapter(handler).fetch_asset(plan, FakeFetchIO())
    assert exc.value.error_class is ErrorClass.GONE


# --- healthcheck（Query API canary）----------------------------------------------------------


def test_healthcheck_all_canaries_match_is_healthy() -> None:
    handler: Handler = lambda request: httpx.Response(200, content=_ATOM_HEALTHCHECK)  # noqa: E731
    report = _adapter(handler).healthcheck()
    assert report.healthy is True


def test_healthcheck_queries_all_three_canary_ids() -> None:
    seen: list[httpx.URL] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url)
        return httpx.Response(200, content=_ATOM_HEALTHCHECK)

    _adapter(handler).healthcheck()
    id_list = seen[0].params["id_list"]
    assert id_list == "2401.00001v1,2312.00002v1,2311.00003v2"


def test_healthcheck_title_drift_is_unhealthy() -> None:
    drifted = _ATOM_HEALTHCHECK.replace(
        b"A Robust Canary for Machine Learning", b"Some Totally Different Title"
    )
    handler: Handler = lambda request: httpx.Response(200, content=drifted)  # noqa: E731
    report = _adapter(handler).healthcheck()
    assert report.healthy is False
    assert "drift" in report.detail


def test_healthcheck_missing_canary_is_unhealthy() -> None:
    # 只回 1 条 canary → 另外两条 missing。
    partial = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom" xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">
<opensearch:totalResults>1</opensearch:totalResults>
<entry><id>http://arxiv.org/abs/2401.00001v1</id><title>A Robust Canary for Machine Learning</title>
<arxiv:primary_category term="cs.LG" scheme="http://arxiv.org/schemas/atom"/></entry>
</feed>
"""
    handler: Handler = lambda request: httpx.Response(200, content=partial)  # noqa: E731
    report = _adapter(handler).healthcheck()
    assert report.healthy is False
    assert "missing" in report.detail


def test_healthcheck_unreachable_returns_unhealthy_not_raise() -> None:
    handler: Handler = lambda request: httpx.Response(503, content=b"down")  # noqa: E731
    report = _adapter(handler).healthcheck()
    assert report.healthy is False
    assert "unreachable" in report.detail


def test_healthcheck_primary_category_drift_is_unhealthy() -> None:
    # title 匹配但 primary_category 漂移（cs.LG→cs.AI）→ 双字段比对第二字段捕获。
    drifted = _ATOM_HEALTHCHECK.replace(b'term="cs.LG"', b'term="cs.AI"')
    handler: Handler = lambda request: httpx.Response(200, content=drifted)  # noqa: E731
    report = _adapter(handler).healthcheck()
    assert report.healthy is False
    assert "primary_category drift" in report.detail


def test_healthcheck_malformed_response_is_unhealthy_not_raise() -> None:
    handler: Handler = lambda request: httpx.Response(200, content=b"<feed><entry>")  # noqa: E731
    report = _adapter(handler).healthcheck()
    assert report.healthy is False
    assert "parse failed" in report.detail


# --- 覆盖补强：UA 惰性自建 / venue set 推导 / 窗口边界 / gone 嗅探缓冲 ------------------------


def test_default_user_agent_uses_env_email(monkeypatch: pytest.MonkeyPatch) -> None:
    from paper_crawler.adapters.arxiv import adapter as mod

    monkeypatch.setenv(mod._CONTACT_EMAIL_ENV, "real@lab.edu")
    ua = mod._default_user_agent()
    assert ua.startswith("PaperCrawler/")
    assert ua.endswith("(personal research; mailto:real@lab.edu)")


def test_default_user_agent_falls_back_to_placeholder(monkeypatch: pytest.MonkeyPatch) -> None:
    from paper_crawler.adapters.arxiv import adapter as mod

    monkeypatch.delenv(mod._CONTACT_EMAIL_ENV, raising=False)
    ua = mod._default_user_agent()
    assert ua.endswith("(personal research; mailto:anonymous@paper-crawler.invalid)")


def test_package_version_falls_back_when_distribution_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from importlib import metadata as im

    from paper_crawler import __version__
    from paper_crawler.adapters.arxiv import adapter as mod

    def _raise(_name: str) -> str:
        raise im.PackageNotFoundError(_name)

    monkeypatch.setattr(mod.metadata, "version", _raise)
    assert mod._package_version() == __version__


def test_lazy_client_builds_and_caches_httpclient_when_http_none() -> None:
    a = ArxivAdapter()
    client = a._client()  # 惰性自建（仅构造，不发请求 → 零真实网络）
    assert isinstance(client, HttpClient)
    assert a._client() is client  # 幂等缓存
    client.close()


def test_oai_target_derives_set_from_venue_id_when_quirks_absent() -> None:
    from paper_crawler.adapters.arxiv.adapter import _oai_target

    venue = make_arxiv_venue()
    venue.quirks.pop("arxiv_set")
    venue.quirks.pop("arxiv_category")
    oai_set, sub_category = _oai_target(venue)
    assert oai_set == "cs"  # 从 id 'arxiv_cs_lg' 推导 archive
    assert sub_category is None


def test_oai_target_derives_set_from_category_when_set_absent() -> None:
    from paper_crawler.adapters.arxiv.adapter import _oai_target

    venue = make_arxiv_venue()
    venue.quirks.pop("arxiv_set")  # 保留 arxiv_category='cs.LG'
    oai_set, sub_category = _oai_target(venue)
    assert oai_set == "cs"  # 'cs.LG'.split('.')[0]
    assert sub_category == "cs.LG"


def test_set_from_venue_id_edge_cases() -> None:
    from paper_crawler.adapters.arxiv.adapter import _set_from_venue_id

    assert _set_from_venue_id("arxiv_cs_lg") == "cs"
    assert _set_from_venue_id("arxiv_") is None  # 前缀后为空
    assert _set_from_venue_id("cs_lg") is None  # 无 arxiv_ 前缀


def test_oai_target_config_error_when_no_set_derivable() -> None:
    from paper_crawler.adapters.arxiv.adapter import _oai_target
    from paper_crawler.types import VenueSpec

    venue = VenueSpec(
        id="notarxiv",
        kind="preprint_channel",
        names={"full": "Not arXiv"},
        field=["cs_ai"],
        metadata_source="arxiv",
        fulltext_source="arxiv",
        quirks={},
    )
    with pytest.raises(CrawlerError) as exc:
        _oai_target(venue)
    assert exc.value.error_class is ErrorClass.CONFIG


def test_enumerate_future_bucket_makes_no_request_and_is_empty() -> None:
    calls: list[httpx.URL] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url)
        return httpx.Response(200, content=_OAI_PAGE1)

    future = _bucket(year=2099, number="12")  # from > until(=今日) → 空窗口
    assert list(_adapter(handler).enumerate_issue(make_arxiv_venue(), future)) == []
    assert calls == []  # 空窗口零请求


def test_enumerate_invalid_month_number_is_config() -> None:
    handler: Handler = lambda request: httpx.Response(200, content=_OAI_PAGE1)  # noqa: E731
    with pytest.raises(CrawlerError) as exc:
        list(_adapter(handler).enumerate_issue(make_arxiv_venue(), _bucket(number="abc")))
    assert exc.value.error_class is ErrorClass.CONFIG


def test_enumerate_december_bucket_window_ends_dec_31() -> None:
    seen: list[httpx.URL] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url)
        return httpx.Response(200, content=_OAI_NO_RECORDS_MATCH)

    list(_adapter(handler).enumerate_issue(make_arxiv_venue(), _bucket(year=2023, number="12")))
    assert seen[0].params["from"] == "2023-12-01"
    assert seen[0].params["until"] == "2023-12-31"


def test_discover_since_earlier_than_inception_keeps_inception() -> None:
    venue = make_arxiv_venue(inception="2024-01")
    first = next(iter(ArxivAdapter().discover_timeline(venue, since="2020-01")))
    assert first.label == "2024-01"  # since 早于 inception → 起点不收窄


def test_gone_guarded_stream_buffers_pdf_magic_across_small_chunks() -> None:
    from paper_crawler.adapters.arxiv.adapter import _gone_guarded_stream

    # 首块 < 魔数长度 → 缓冲跨块判定；PDF 魔数放行、透传全部字节。
    out = b"".join(_gone_guarded_stream([b"%P", b"DF-", b"1.4 body"]))
    assert out == b"%PDF-1.4 body"


def test_gone_guarded_stream_html_across_chunks_is_gone() -> None:
    from paper_crawler.adapters.arxiv.adapter import _gone_guarded_stream

    with pytest.raises(CrawlerError) as exc:
        list(_gone_guarded_stream([b"<!", b"doctype html><html>gone</html>"]))
    assert exc.value.error_class is ErrorClass.GONE


def test_fetch_empty_response_writes_zero_bytes() -> None:
    handler: Handler = lambda request: httpx.Response(200, content=b"")  # noqa: E731
    plan = ArxivAdapter().resolve_assets(
        make_arxiv_venue(), PaperStub(title="T", identifiers=(("arxiv", "2401.00001"),))
    )[0]
    io = FakeFetchIO()
    result = _adapter(handler).fetch_asset(plan, io)
    assert result.ok is True
    assert result.bytes_written == 0
    assert io.data == b""


def test_fetch_short_non_magic_body_passes_through() -> None:
    # 既非 PDF 又不形似 HTML 的短体：透传，交 pipeline 的 %PDF 权威校验处置。
    handler: Handler = lambda request: httpx.Response(200, content=b"abc")  # noqa: E731
    plan = ArxivAdapter().resolve_assets(
        make_arxiv_venue(), PaperStub(title="T", identifiers=(("arxiv", "2401.00001"),))
    )[0]
    io = FakeFetchIO()
    result = _adapter(handler).fetch_asset(plan, io)
    assert result.ok is True
    assert io.data == b"abc"
