"""AaaiOjsAdapter 主体单测（design/adapters/aaai-ojs.md §3-§6；T5）。

零真实网络：网络型方法（enumerate/fetch/healthcheck）经 `HttpClient(transport=
httpx.MockTransport(...))` 注入受控响应；纯逻辑方法（discover/resolve）无 http 依赖。
十一件套真实结构由 fixtures 加载（tests/fixtures/aaai/raw/）；adapter 主体逻辑
（volume_map 路由 / 全库回填 vs 当前届回看窗 / DOI-卷号 partition / view→download /
登录页嗅探）用 fixtures + 内联片段覆盖。
"""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from helpers import FakeFetchIO, make_aaai_venue
from helpers.aaai_fixtures import fixture_bytes
from paper_crawler.adapters.aaai_ojs.adapter import AaaiOjsAdapter
from paper_crawler.errors import CrawlerError, ErrorClass
from paper_crawler.http import HttpClient
from paper_crawler.types import AssetKind, AuthLevel, Capability, IssueRef, PaperStub, UrlStrategy

_UA = "PaperCrawler/test (personal research; mailto:test@example.com)"

Handler = Callable[[httpx.Request], httpx.Response]


def _adapter(handler: Handler) -> AaaiOjsAdapter:
    client = HttpClient(user_agent=_UA, transport=httpx.MockTransport(handler))
    return AaaiOjsAdapter(http=client)


def _issue(*, volume: str, year: int) -> IssueRef:
    return IssueRef(
        venue_id="aaai", volume=volume, number=None, year=year, label=f"AAAI-{year % 100:02d}"
    )


def _two_page_handler(request: httpx.Request) -> httpx.Response:
    """全库 2 页收割：resumptionToken 决定首页/续页（内容含 v40+v33 混合，供 partition）。"""
    if "resumptionToken" in request.url.params:
        return httpx.Response(200, content=fixture_bytes("02_oai_listrecords_page2.xml"))
    return httpx.Response(200, content=fixture_bytes("01_oai_listrecords_page1.xml"))


# --- 元数据 ------------------------------------------------------------------------------------


def test_adapter_metadata_matches_design_verdicts() -> None:
    a = AaaiOjsAdapter()
    assert a.adapter_id == "aaai_ojs"
    assert a.family == "open_access"
    assert a.capabilities == (
        Capability.DISCOVER | Capability.ENUMERATE | Capability.RESOLVE | Capability.FETCH
    )
    assert Capability.SEARCH not in a.capabilities
    assert a.auth_requirement == AuthLevel.NONE
    assert a.domains == ("ojs.aaai.org",)
    assert a.default_rate.requests_per_minute == 30.0
    assert a.default_rate.source_note != ""


def test_set_http_client_injection_overrides_lazy_env_build() -> None:
    adapter = AaaiOjsAdapter()
    injected = HttpClient(user_agent=_UA)
    adapter.set_http_client(injected)
    assert adapter._client() is injected


def test_lazy_client_builds_and_caches_when_http_none() -> None:
    a = AaaiOjsAdapter()
    client = a._client()
    assert isinstance(client, HttpClient)
    assert a._client() is client
    client.close()


# --- discover（零网络，届/年聚合）------------------------------------------------------------


def test_discover_yields_year_aggregated_issues_sorted() -> None:
    issues = list(AaaiOjsAdapter().discover_timeline(make_aaai_venue()))
    assert [(i.year, i.volume, i.label) for i in issues] == [
        (2019, "33", "AAAI-19"),
        (2026, "40", "AAAI-26"),
    ]
    first = issues[0]
    assert first.venue_id == "aaai"
    assert first.number is None  # OJS "No.M" 不建模为 IssueRef 维度（方案 B）
    assert first.pub_date is None
    assert first.paper_count_claimed is None


def test_discover_label_is_two_digit_year_brand_not_session_ordinal() -> None:
    # 站点品牌名 AAAI-YY（=2 位年份），刻意区别于"第 N 届"序号（survey §2.4）。
    issues = {i.year: i for i in AaaiOjsAdapter().discover_timeline(make_aaai_venue())}
    assert issues[2026].label == "AAAI-26"
    assert issues[2019].label == "AAAI-19"


def test_discover_since_filters_year_lower_bound() -> None:
    issues = list(AaaiOjsAdapter().discover_timeline(make_aaai_venue(), since="2026"))
    assert [i.year for i in issues] == [2026]


def test_discover_since_accepts_yyyy_prefix() -> None:
    issues = list(AaaiOjsAdapter().discover_timeline(make_aaai_venue(), since="2026-01"))
    assert [i.year for i in issues] == [2026]


def test_discover_missing_volume_map_is_config_error() -> None:
    venue = make_aaai_venue()
    venue.quirks.pop("volume_map")
    with pytest.raises(CrawlerError) as exc:
        list(AaaiOjsAdapter().discover_timeline(venue))
    assert exc.value.error_class is ErrorClass.CONFIG


def test_discover_illegal_volume_map_entry_is_config_error() -> None:
    with pytest.raises(CrawlerError) as exc:
        list(AaaiOjsAdapter().discover_timeline(make_aaai_venue(volume_map={"abc": "xyz"})))
    assert exc.value.error_class is ErrorClass.CONFIG


def test_discover_since_invalid_format_is_config_error() -> None:
    with pytest.raises(CrawlerError) as exc:
        list(AaaiOjsAdapter().discover_timeline(make_aaai_venue(), since="not-a-year"))
    assert exc.value.error_class is ErrorClass.CONFIG


# --- enumerate（OAI 收割 / DOI-卷号 partition / 回看窗）---------------------------------------


def test_enumerate_current_edition_partitions_to_its_volume_only() -> None:
    # v40（当前届）跨 2 页收割 → 只产 v40 记录（A/C/E 页1 + F 页2 = 4），过滤掉 v33。
    stubs = list(
        _adapter(_two_page_handler).enumerate_issue(
            make_aaai_venue(), _issue(volume="40", year=2026)
        )
    )
    dois = [dict(s.identifiers)["doi"] for s in stubs]
    assert dois == [
        "10.1609/aaai.v40i1.36958",
        "10.1609/aaai.v40i2.37001",
        "10.1609/aaai.v40i1.36959",
        "10.1609/aaai.v40i3.37050",
    ]
    assert all(d.startswith("10.1609/aaai.v40") for d in dois)


def test_enumerate_historical_edition_partitions_to_its_volume_only() -> None:
    # v33（历史届）从同一份全库收割里只产 v33 记录（D 页1 + G 页2 = 2）。
    stubs = list(
        _adapter(_two_page_handler).enumerate_issue(
            make_aaai_venue(), _issue(volume="33", year=2019)
        )
    )
    dois = [dict(s.identifiers)["doi"] for s in stubs]
    assert dois == ["10.1609/aaai.v33i01.3301695", "10.1609/aaai.v33i01.3301696"]


def test_enumerate_current_edition_uses_lookback_datestamp_window() -> None:
    seen: list[httpx.URL] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url)
        return _two_page_handler(request)

    list(_adapter(handler).enumerate_issue(make_aaai_venue(), _issue(volume="40", year=2026)))
    # 当前届（volume_map 最大年之卷）加固定回看窗 from=；OAI base 用 ojs_code=AAAI。
    assert str(seen[0]).startswith("https://ojs.aaai.org/index.php/AAAI/oai?")
    assert "from" in seen[0].params
    assert seen[0].params["metadataPrefix"] == "oai_dc"
    # 续页只带 verb + resumptionToken（OAI 规范互斥）。
    assert seen[1].params["resumptionToken"] == "AAAI-RESUME-PAGE2"
    assert "from" not in seen[1].params


def test_enumerate_historical_edition_has_no_datestamp_window() -> None:
    seen: list[httpx.URL] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url)
        return _two_page_handler(request)

    list(_adapter(handler).enumerate_issue(make_aaai_venue(), _issue(volume="33", year=2019)))
    # 历史届全库回填：无 from 日期窗（membership 判据是 DOI 卷号，非日期窗）。
    assert "from" not in seen[0].params


def test_enumerate_logs_tombstone_skip_debug_event(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[dict[str, object]] = []
    monkeypatch.setattr(
        "paper_crawler.adapters.aaai_ojs.adapter.log_event",
        lambda level, msg, **kw: events.append({"level": level, "msg": msg, **kw}),
    )
    list(
        _adapter(_two_page_handler).enumerate_issue(
            make_aaai_venue(), _issue(volume="40", year=2026)
        )
    )
    tombstone_events = [e for e in events if e["msg"] == "oai tombstones skipped"]
    assert len(tombstone_events) == 1
    ev = tombstone_events[0]
    assert ev["level"] == "DEBUG"
    assert ev["venue"] == "aaai"
    assert ev["stage"] == "enumerate"
    assert ev["bucket"] == "AAAI-26"
    assert ev["skipped_tombstones"] == 1


def test_enumerate_norecordsmatch_completes_empty() -> None:
    handler: Handler = lambda request: httpx.Response(  # noqa: E731
        200, content=fixture_bytes("03_oai_norecordsmatch.xml")
    )
    stubs = list(
        _adapter(handler).enumerate_issue(make_aaai_venue(), _issue(volume="40", year=2026))
    )
    assert stubs == []


def test_enumerate_bad_resumption_token_is_transient() -> None:
    handler: Handler = lambda request: httpx.Response(  # noqa: E731
        200, content=fixture_bytes("04_oai_bad_resumption_token.xml")
    )
    with pytest.raises(CrawlerError) as exc:
        list(_adapter(handler).enumerate_issue(make_aaai_venue(), _issue(volume="40", year=2026)))
    assert exc.value.error_class is ErrorClass.TRANSIENT


def test_enumerate_bad_argument_is_config() -> None:
    handler: Handler = lambda request: httpx.Response(  # noqa: E731
        200, content=fixture_bytes("05_oai_bad_argument.xml")
    )
    with pytest.raises(CrawlerError) as exc:
        list(_adapter(handler).enumerate_issue(make_aaai_venue(), _issue(volume="40", year=2026)))
    assert exc.value.error_class is ErrorClass.CONFIG


def test_enumerate_malformed_xml_is_parse() -> None:
    handler: Handler = lambda request: httpx.Response(  # noqa: E731
        200, content=fixture_bytes("09_oai_malformed.xml")
    )
    with pytest.raises(CrawlerError) as exc:
        list(_adapter(handler).enumerate_issue(make_aaai_venue(), _issue(volume="40", year=2026)))
    assert exc.value.error_class is ErrorClass.PARSE


def test_enumerate_volume_none_is_config_error() -> None:
    handler: Handler = lambda request: httpx.Response(200, content=b"")  # noqa: E731
    bad = IssueRef(venue_id="aaai", volume=None, year=2026)
    with pytest.raises(CrawlerError) as exc:
        list(_adapter(handler).enumerate_issue(make_aaai_venue(), bad))
    assert exc.value.error_class is ErrorClass.CONFIG


def test_enumerate_volume_non_digit_is_config_error() -> None:
    handler: Handler = lambda request: httpx.Response(200, content=b"")  # noqa: E731
    bad = IssueRef(venue_id="aaai", volume="v40", year=2026)  # 带前缀，非裸数字
    with pytest.raises(CrawlerError) as exc:
        list(_adapter(handler).enumerate_issue(make_aaai_venue(), bad))
    assert exc.value.error_class is ErrorClass.CONFIG


def test_enumerate_unregistered_volume_is_config_error() -> None:
    handler: Handler = lambda request: httpx.Response(200, content=b"")  # noqa: E731
    unregistered = IssueRef(venue_id="aaai", volume="9999", year=2099)
    with pytest.raises(CrawlerError) as exc:
        list(_adapter(handler).enumerate_issue(make_aaai_venue(), unregistered))
    assert exc.value.error_class is ErrorClass.CONFIG
    assert "9999" in str(exc.value)


def test_enumerate_uses_ojs_code_from_quirks() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, content=fixture_bytes("03_oai_norecordsmatch.xml"))

    venue = make_aaai_venue(ojs_code="ICWSM", volume_map={2026: 40})
    list(_adapter(handler).enumerate_issue(venue, _issue(volume="40", year=2026)))
    assert seen[0].startswith("https://ojs.aaai.org/index.php/ICWSM/oai?")


def test_enumerate_ojs_code_defaults_to_venue_id_upper() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, content=fixture_bytes("03_oai_norecordsmatch.xml"))

    venue = make_aaai_venue(volume_map={2026: 40})
    venue.quirks.pop("ojs_code")  # 缺省 → venue.id.upper() = 'AAAI'
    list(_adapter(handler).enumerate_issue(venue, _issue(volume="40", year=2026)))
    assert seen[0].startswith("https://ojs.aaai.org/index.php/AAAI/oai?")


# --- resolve（零网络，view→download 预换）----------------------------------------------------


def test_resolve_converts_view_to_download_url() -> None:
    paper = PaperStub(
        title="T",
        identifiers=(("doi", "10.1609/aaai.v40i1.36958"),),
        meta=(
            ("pdf_url", "https://ojs.aaai.org/index.php/AAAI/article/view/36958/40920"),
            ("ojs_article_id", "36958"),
        ),
    )
    plans = AaaiOjsAdapter().resolve_assets(make_aaai_venue(), paper)
    assert len(plans) == 1
    plan = plans[0]
    assert plan.kind is AssetKind.PDF
    assert plan.url == "https://ojs.aaai.org/index.php/AAAI/article/download/36958/40920"
    assert plan.url_strategy is UrlStrategy.DIRECT
    assert plan.auth_needed is AuthLevel.NONE
    assert plan.version is None


def test_resolve_without_pdf_url_meta_yields_zero_plans() -> None:
    paper = PaperStub(title="T", identifiers=(("doi", "10.1609/aaai.v40i1.1"),), meta=())
    assert AaaiOjsAdapter().resolve_assets(make_aaai_venue(), paper) == []


# --- fetch（流式，登录页/撤稿页首字节嗅探）---------------------------------------------------


def _pdf_plan_adapter(handler: Handler) -> tuple[AaaiOjsAdapter, object]:
    paper = PaperStub(
        title="T",
        identifiers=(("doi", "10.1609/aaai.v40i1.36958"),),
        meta=(("pdf_url", "https://ojs.aaai.org/index.php/AAAI/article/view/36958/40920"),),
    )
    plan = AaaiOjsAdapter().resolve_assets(make_aaai_venue(), paper)[0]
    return _adapter(handler), plan


def test_fetch_streams_pdf_bytes_ok() -> None:
    pdf = b"%PDF-1.7\n" + b"payload " * 64 + b"\n%%EOF\n"
    adapter, plan = _pdf_plan_adapter(lambda r: httpx.Response(200, content=pdf))
    io = FakeFetchIO()
    result = adapter.fetch_asset(plan, io)  # type: ignore[arg-type]
    assert result.ok is True
    assert io.data == pdf


def test_fetch_http_404_is_gone_via_httpclient() -> None:
    adapter, plan = _pdf_plan_adapter(
        lambda r: httpx.Response(404, content=fixture_bytes("07_article_404.html"))
    )
    with pytest.raises(CrawlerError) as exc:
        adapter.fetch_asset(plan, FakeFetchIO())  # type: ignore[arg-type]
    assert exc.value.error_class is ErrorClass.GONE


def test_fetch_login_page_html_is_no_entitlement() -> None:
    # 200 但回登录页（302→/login 落地，未发布/占位 galley）→ no_entitlement（★D）。
    adapter, plan = _pdf_plan_adapter(
        lambda r: httpx.Response(200, content=fixture_bytes("08_issue_login_redirect.html"))
    )
    with pytest.raises(CrawlerError) as exc:
        adapter.fetch_asset(plan, FakeFetchIO())  # type: ignore[arg-type]
    assert exc.value.error_class is ErrorClass.NO_ENTITLEMENT
    assert exc.value.detail == "login-gated"


def test_fetch_login_page_reached_via_real_302_redirect_is_no_entitlement() -> None:
    # 忠实复现 302→/login：httpx follow_redirects 跟随，最终体是登录页 → no_entitlement。
    def handler(request: httpx.Request) -> httpx.Response:
        if "/login" in request.url.path:
            return httpx.Response(200, content=fixture_bytes("08_issue_login_redirect.html"))
        return httpx.Response(
            302, headers={"location": "https://ojs.aaai.org/index.php/AAAI/login?source=%2Fx"}
        )

    adapter, plan = _pdf_plan_adapter(handler)
    with pytest.raises(CrawlerError) as exc:
        adapter.fetch_asset(plan, FakeFetchIO())  # type: ignore[arg-type]
    assert exc.value.error_class is ErrorClass.NO_ENTITLEMENT


def test_fetch_withdrawn_html_page_200_is_gone() -> None:
    # 200 但回非登录 HTML（撤稿/合并/不存在）→ gone（区别于登录页的 no_entitlement）。
    adapter, plan = _pdf_plan_adapter(
        lambda r: httpx.Response(200, content=fixture_bytes("07_article_404.html"))
    )
    with pytest.raises(CrawlerError) as exc:
        adapter.fetch_asset(plan, FakeFetchIO())  # type: ignore[arg-type]
    assert exc.value.error_class is ErrorClass.GONE


def test_fetch_non_pdf_non_html_bytes_pass_through_to_pipeline() -> None:
    # 既非 PDF 又不形似 HTML（如截断二进制）→ 透传，交 pipeline %PDF 权威校验。
    blob = b"\x00\x01\x02 not a pdf not html " * 8
    adapter, plan = _pdf_plan_adapter(lambda r: httpx.Response(200, content=blob))
    io = FakeFetchIO()
    result = adapter.fetch_asset(plan, io)  # type: ignore[arg-type]
    assert result.ok is True
    assert io.data == blob


# --- healthcheck（OAI Identify）--------------------------------------------------------------

_IDENTIFY_OK = (
    b'<?xml version="1.0"?><OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/"><Identify>'
    b"<repositoryName>Proceedings of the AAAI Conference on Artificial Intelligence</repositoryName>"  # noqa: E501
    b"<protocolVersion>2.0</protocolVersion></Identify></OAI-PMH>"
)


def test_healthcheck_ok_identify_repository_name_contains_aaai() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, content=_IDENTIFY_OK)

    report = _adapter(handler).healthcheck()
    assert report.healthy is True
    assert seen == ["https://ojs.aaai.org/index.php/AAAI/oai?verb=Identify"]


def test_healthcheck_repository_name_without_aaai_is_unhealthy() -> None:
    body = (
        b'<?xml version="1.0"?><OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/"><Identify>'
        b"<repositoryName>Some Other Repository</repositoryName></Identify></OAI-PMH>"
    )
    report = _adapter(lambda r: httpx.Response(200, content=body)).healthcheck()
    assert report.healthy is False
    assert "AAAI" in report.detail


def test_healthcheck_missing_identify_element_is_unhealthy() -> None:
    body = b'<?xml version="1.0"?><OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/"></OAI-PMH>'
    report = _adapter(lambda r: httpx.Response(200, content=body)).healthcheck()
    assert report.healthy is False


def test_healthcheck_malformed_identify_xml_is_unhealthy_not_raise() -> None:
    report = _adapter(lambda r: httpx.Response(200, content=b"<OAI-PMH><Identify>")).healthcheck()
    assert report.healthy is False
    assert "parse failed" in report.detail


def test_healthcheck_unreachable_returns_unhealthy_not_raise() -> None:
    report = _adapter(lambda r: httpx.Response(503, content=b"down")).healthcheck()
    assert report.healthy is False
    assert "unreachable" in report.detail


# --- UA 惰性自建 -------------------------------------------------------------------------------


def test_default_user_agent_uses_env_email(monkeypatch: pytest.MonkeyPatch) -> None:
    from paper_crawler.adapters.aaai_ojs import adapter as mod

    monkeypatch.setenv(mod._CONTACT_EMAIL_ENV, "real@lab.edu")
    ua = mod._default_user_agent()
    assert ua.startswith("PaperCrawler/")
    assert ua.endswith("(personal research; mailto:real@lab.edu)")


def test_default_user_agent_falls_back_to_placeholder(monkeypatch: pytest.MonkeyPatch) -> None:
    from paper_crawler.adapters.aaai_ojs import adapter as mod

    monkeypatch.delenv(mod._CONTACT_EMAIL_ENV, raising=False)
    ua = mod._default_user_agent()
    assert ua.endswith("(personal research; mailto:anonymous@paper-crawler.invalid)")
