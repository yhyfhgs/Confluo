"""PmlrAdapter 主体单测（design/adapters/pmlr.md §3-§5；T5）。

零真实网络：网络型方法（enumerate/fetch/healthcheck）经 `HttpClient(transport=
httpx.MockTransport(...))` 注入受控响应；纯逻辑方法（discover/resolve）无 http
依赖。用内联 HTML/bib 片段覆盖 adapter 主体逻辑（volume_map 路由/0-div 消歧/
域无关 resolve/错误映射）；真实响应结构的七件套 fixture 由集成/契约层加载
（tests/fixtures/pmlr/）。
"""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from helpers import FakeFetchIO, make_pmlr_venue
from helpers.pmlr_fixtures import fixture_bytes
from paper_crawler.adapters.pmlr.adapter import PmlrAdapter
from paper_crawler.errors import CrawlerError, ErrorClass
from paper_crawler.http import HttpClient
from paper_crawler.types import AssetKind, AuthLevel, Capability, IssueRef, PaperStub, UrlStrategy

_TEST_UA = "PaperCrawler/test (personal research; mailto:test@example.com)"

Handler = Callable[[httpx.Request], httpx.Response]


def _adapter(handler: Handler) -> PmlrAdapter:
    client = HttpClient(user_agent=_TEST_UA, transport=httpx.MockTransport(handler))
    return PmlrAdapter(http=client)


def _issue(*, volume: str = "235", year: int = 2024) -> IssueRef:
    return IssueRef(venue_id="icml", volume=volume, number=None, year=year, label=f"v{volume}")


def _volume_page(*divs: str) -> bytes:
    body = "\n".join(divs)
    return f"<html><body><div id='content'>{body}</div></body></html>".encode()


def _paper_div(slug: str, *, title: str = "T", pdf_host: str = "raw.githubusercontent.com") -> str:
    if pdf_host == "raw.githubusercontent.com":
        pdf = f"https://raw.githubusercontent.com/mlresearch/v235/main/assets/{slug}/{slug}.pdf"
    else:
        pdf = f"https://proceedings.mlr.press/v202/{slug}/{slug}.pdf"
    return (
        '<div class="paper">'
        f'<p class="title">{title}</p>'
        f'<p class="details"><span class="authors">A Author</span><br>PMLR 235:1-10, 2024.</p>'
        f'<p class="links">[<a href="v235/{slug}.html">abs</a>]'
        f'[<a href="{pdf}">Download PDF</a>]</p>'
        "</div>"
    )


# --- 元数据 ------------------------------------------------------------------------------------


def test_adapter_metadata_matches_pmlr_md_verdicts() -> None:
    a = PmlrAdapter()
    assert a.adapter_id == "pmlr"
    assert a.family == "open_access"
    assert a.capabilities == (
        Capability.DISCOVER | Capability.ENUMERATE | Capability.RESOLVE | Capability.FETCH
    )
    assert Capability.SEARCH not in a.capabilities
    assert a.auth_requirement == AuthLevel.NONE
    assert a.domains == ("proceedings.mlr.press", "raw.githubusercontent.com")
    assert a.default_rate.requests_per_minute == 30.0
    assert a.default_rate.source_note != ""


def test_set_http_client_injection_overrides_lazy_env_build() -> None:
    adapter = PmlrAdapter()
    injected = HttpClient(user_agent=_TEST_UA)
    adapter.set_http_client(injected)
    assert adapter._client() is injected


def test_lazy_client_builds_and_caches_httpclient_when_http_none() -> None:
    a = PmlrAdapter()
    client = a._client()
    assert isinstance(client, HttpClient)
    assert a._client() is client
    client.close()


# --- discover（零网络）------------------------------------------------------------------------


def test_discover_yields_issues_sorted_by_year_from_volume_map() -> None:
    issues = list(PmlrAdapter().discover_timeline(make_pmlr_venue()))
    assert [i.year for i in issues] == [2023, 2024]
    first = issues[0]
    assert first.venue_id == "icml"
    assert first.volume == "202"
    assert first.number is None
    assert first.label == "v202"
    assert first.pub_date is None
    assert first.paper_count_claimed is None


def test_discover_since_filters_to_year_lower_bound() -> None:
    issues = list(PmlrAdapter().discover_timeline(make_pmlr_venue(), since="2024"))
    assert [i.year for i in issues] == [2024]


def test_discover_missing_volume_map_is_config_error() -> None:
    venue = make_pmlr_venue()
    venue.quirks.pop("volume_map")
    with pytest.raises(CrawlerError) as exc:
        list(PmlrAdapter().discover_timeline(venue))
    assert exc.value.error_class is ErrorClass.CONFIG


def test_discover_non_dict_volume_map_is_config_error() -> None:
    with pytest.raises(CrawlerError) as exc:
        list(PmlrAdapter().discover_timeline(make_pmlr_venue(volume_map="not-a-dict")))
    assert exc.value.error_class is ErrorClass.CONFIG


def test_discover_volume_map_with_illegal_entry_is_config_error() -> None:
    with pytest.raises(CrawlerError) as exc:
        list(PmlrAdapter().discover_timeline(make_pmlr_venue(volume_map={"abc": "xyz"})))
    assert exc.value.error_class is ErrorClass.CONFIG


def test_discover_since_invalid_format_is_config_error() -> None:
    with pytest.raises(CrawlerError) as exc:
        list(PmlrAdapter().discover_timeline(make_pmlr_venue(), since="not-a-year"))
    assert exc.value.error_class is ErrorClass.CONFIG


def test_discover_accepts_string_keyed_volume_map() -> None:
    # PyYAML 给无引号整数键 int；有引号则给 str——两种形态都要接受。
    issues = list(PmlrAdapter().discover_timeline(make_pmlr_venue(volume_map={"2024": "235"})))
    assert issues[0].year == 2024
    assert issues[0].volume == "235"


# --- resolve（零网络，域无关）------------------------------------------------------------------


def test_resolve_passes_through_github_hosted_pdf_url_verbatim() -> None:
    paper = PaperStub(
        title="T",
        identifiers=(("pmlr", "pmlr-v235-x24a"),),
        meta=(
            (
                "pdf_url",
                "https://raw.githubusercontent.com/mlresearch/v235/main/assets/x24a/x24a.pdf",
            ),
            ("landing_url", "https://proceedings.mlr.press/v235/x24a.html"),
        ),
    )
    plans = PmlrAdapter().resolve_assets(make_pmlr_venue(), paper)
    assert len(plans) == 1
    plan = plans[0]
    assert plan.kind is AssetKind.PDF
    assert plan.url == (
        "https://raw.githubusercontent.com/mlresearch/v235/main/assets/x24a/x24a.pdf"
    )
    assert plan.url_strategy is UrlStrategy.DIRECT
    assert plan.auth_needed is AuthLevel.NONE
    assert plan.version is None


def test_resolve_passes_through_self_hosted_pdf_url_verbatim() -> None:
    paper = PaperStub(
        title="T",
        identifiers=(("pmlr", "pmlr-v202-y23a"),),
        meta=(
            ("pdf_url", "https://proceedings.mlr.press/v202/y23a/y23a.pdf"),
            ("landing_url", "https://proceedings.mlr.press/v202/y23a.html"),
        ),
    )
    plans = PmlrAdapter().resolve_assets(make_pmlr_venue(), paper)
    assert plans[0].url == "https://proceedings.mlr.press/v202/y23a/y23a.pdf"


def test_resolve_without_pdf_url_meta_yields_zero_plans_not_error() -> None:
    paper = PaperStub(title="T", identifiers=(("pmlr", "pmlr-v235-x24a"),), meta=())
    assert PmlrAdapter().resolve_assets(make_pmlr_venue(), paper) == []


# --- enumerate（单请求主源 + 0-div 消歧）--------------------------------------------------------


def test_enumerate_normal_page_single_request_no_bib_fetch() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, content=_volume_page(_paper_div("x24a"), _paper_div("y24b")))

    stubs = list(_adapter(handler).enumerate_issue(make_pmlr_venue(), _issue()))
    assert len(calls) == 1  # 常态单请求：不触发 bib
    assert calls[0] == "https://proceedings.mlr.press/v235/"
    assert [dict(s.identifiers)["pmlr"] for s in stubs] == [
        "pmlr-v235-x24a",
        "pmlr-v235-y24b",
    ]
    assert stubs[0].year == 2024


def test_enumerate_zero_div_zero_bib_is_legal_empty_not_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "bibliography.bib" in request.url.path:
            return httpx.Response(200, content=b"% empty\n")
        return httpx.Response(200, content=_volume_page())

    stubs = list(_adapter(handler).enumerate_issue(make_pmlr_venue(), _issue()))
    assert stubs == []


def test_enumerate_zero_div_nonzero_bib_is_parse_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "bibliography.bib" in request.url.path:
            return httpx.Response(200, content=b"@InProceedings{x24a,\ntitle={T}\n}\n")
        return httpx.Response(200, content=_volume_page())

    with pytest.raises(CrawlerError) as exc:
        list(_adapter(handler).enumerate_issue(make_pmlr_venue(), _issue()))
    assert exc.value.error_class is ErrorClass.PARSE


def test_enumerate_bib_fetch_failure_propagates_not_swallowed_as_empty() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "bibliography.bib" in request.url.path:
            return httpx.Response(503, content=b"down")
        return httpx.Response(200, content=_volume_page())

    with pytest.raises(CrawlerError) as exc:
        list(_adapter(handler).enumerate_issue(make_pmlr_venue(), _issue()))
    assert exc.value.error_class is ErrorClass.TRANSIENT


def test_enumerate_volume_page_404_is_gone() -> None:
    handler: Handler = lambda request: httpx.Response(404, content=b"not found")  # noqa: E731
    with pytest.raises(CrawlerError) as exc:
        list(_adapter(handler).enumerate_issue(make_pmlr_venue(), _issue()))
    assert exc.value.error_class is ErrorClass.GONE


def test_enumerate_issue_volume_none_is_config_error() -> None:
    handler: Handler = lambda request: httpx.Response(200, content=_volume_page())  # noqa: E731
    bad = IssueRef(venue_id="icml", volume=None, year=2024)
    with pytest.raises(CrawlerError) as exc:
        list(_adapter(handler).enumerate_issue(make_pmlr_venue(), bad))
    assert exc.value.error_class is ErrorClass.CONFIG


def test_enumerate_issue_volume_non_digit_is_config_error() -> None:
    handler: Handler = lambda request: httpx.Response(200, content=_volume_page())  # noqa: E731
    bad = IssueRef(venue_id="icml", volume="v235", year=2024)  # 带前缀 'v'，非裸数字
    with pytest.raises(CrawlerError) as exc:
        list(_adapter(handler).enumerate_issue(make_pmlr_venue(), bad))
    assert exc.value.error_class is ErrorClass.CONFIG


def test_enumerate_unregistered_volume_is_config_error() -> None:
    handler: Handler = lambda request: httpx.Response(200, content=_volume_page())  # noqa: E731
    unregistered = IssueRef(venue_id="icml", volume="9999", year=2099)
    with pytest.raises(CrawlerError) as exc:
        list(_adapter(handler).enumerate_issue(make_pmlr_venue(), unregistered))
    assert exc.value.error_class is ErrorClass.CONFIG
    assert "9999" in str(exc.value)


def test_enumerate_dual_hosted_pdf_urls_pass_through_domain_agnostic() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=_volume_page(
                _paper_div("github24a", pdf_host="raw.githubusercontent.com"),
                _paper_div("selfhosted23a", pdf_host="proceedings.mlr.press"),
            ),
        )

    stubs = list(_adapter(handler).enumerate_issue(make_pmlr_venue(), _issue()))
    pdf_urls = [dict(s.meta)["pdf_url"] for s in stubs]
    assert pdf_urls[0].startswith("https://raw.githubusercontent.com/")
    assert pdf_urls[1].startswith("https://proceedings.mlr.press/")


# --- 全卷 pdf_url 缺失的可观测性（F4 清账，S1 审计"链接正则对标记漂移静默退化为 0 资产"）------


def _paper_div_without_pdf_link(slug: str, *, title: str = "T") -> str:
    """模拟 `[Download PDF]` 锚文本漂移：abs 链接仍在（slug 仍可解析），但没有任何锚
    文本恰好等于 "Download PDF"（如站点改渲染成纯 "PDF"）——`_extract_link_href` 找不到
    该文本，pdf_url 解析为 None（单篇层面这是既有设计容忍的非错误态）。
    """
    return (
        '<div class="paper">'
        f'<p class="title">{title}</p>'
        '<p class="details"><span class="authors">A Author</span><br>PMLR 235:1-10, 2024.</p>'
        f'<p class="links">[<a href="v235/{slug}.html">abs</a>]'
        f'[<a href="https://proceedings.mlr.press/v235/{slug}/{slug}.pdf">PDF</a>]</p>'
        "</div>"
    )


def test_enumerate_all_papers_missing_pdf_url_logs_warning_for_markup_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 单篇缺 pdf_url 是既有设计容忍的非错误态（resolve_assets 产 0 pdf plan）；但 PMLR
    # 每篇必有 PDF——若解析出的论文全部缺 pdf_url，大概率是链接正则对该卷 markup 漂移
    # 判其失配（而非全卷恰好都没有 PDF）。此前零日志、纯静默退化为整卷 0 资产；现须
    # 经 obslog 显式 WARNING 可观测。
    events: list[dict[str, object]] = []
    monkeypatch.setattr(
        "paper_crawler.adapters.pmlr.adapter.log_event",
        lambda level, msg, **kw: events.append({"level": level, "msg": msg, **kw}),
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=_volume_page(
                _paper_div_without_pdf_link("x24a"), _paper_div_without_pdf_link("y24b")
            ),
        )

    stubs = list(_adapter(handler).enumerate_issue(make_pmlr_venue(), _issue()))
    assert len(stubs) == 2  # 解析仍成功产出 stub（title/authors/abs 均不受影响）
    assert all("pdf_url" not in dict(s.meta) for s in stubs)  # 确认漂移场景确实全 None

    warnings = [e for e in events if "none have a pdf_url" in str(e["msg"])]
    assert len(warnings) == 1
    assert warnings[0]["level"] == "WARNING"
    assert warnings[0]["paper_count"] == 2
    assert warnings[0]["volume"] == "235"


def test_enumerate_partial_pdf_url_coverage_does_not_log_drift_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 反证：卷内至少一篇仍有 pdf_url（漂移只影响部分论文，或该论文本身就是孤例缺失）
    # 时不触发"全卷疑似漂移"告警——保持既有"单篇缺失非错误"的宽松判定不变。
    events: list[dict[str, object]] = []
    monkeypatch.setattr(
        "paper_crawler.adapters.pmlr.adapter.log_event",
        lambda level, msg, **kw: events.append({"level": level, "msg": msg, **kw}),
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=_volume_page(_paper_div("x24a"), _paper_div_without_pdf_link("y24b")),
        )

    stubs = list(_adapter(handler).enumerate_issue(make_pmlr_venue(), _issue()))
    assert len(stubs) == 2
    assert [e for e in events if "none have a pdf_url" in str(e["msg"])] == []


# --- fetch（流式）------------------------------------------------------------------------------


def test_fetch_streams_pdf_bytes_ok() -> None:
    pdf = b"%PDF-1.5\n" + b"payload-bytes " * 64 + b"\n%%EOF\n"
    handler: Handler = lambda request: httpx.Response(200, content=pdf)  # noqa: E731
    paper = PaperStub(
        title="T",
        identifiers=(("pmlr", "pmlr-v235-x24a"),),
        meta=(("pdf_url", "https://raw.githubusercontent.com/mlresearch/v235/x24a.pdf"),),
    )
    plan = PmlrAdapter().resolve_assets(make_pmlr_venue(), paper)[0]
    io = FakeFetchIO()
    result = _adapter(handler).fetch_asset(plan, io)
    assert result.ok is True
    assert result.bytes_written == len(pdf)
    assert io.data == pdf


def test_fetch_http_404_is_gone_via_httpclient() -> None:
    handler: Handler = lambda request: httpx.Response(404, content=b"not found")  # noqa: E731
    paper = PaperStub(
        title="T",
        identifiers=(("pmlr", "pmlr-v235-x24a"),),
        meta=(("pdf_url", "https://proceedings.mlr.press/v235/x24a.pdf"),),
    )
    plan = PmlrAdapter().resolve_assets(make_pmlr_venue(), paper)[0]
    with pytest.raises(CrawlerError) as exc:
        _adapter(handler).fetch_asset(plan, FakeFetchIO())
    assert exc.value.error_class is ErrorClass.GONE


# --- healthcheck（站点根匿名 ping）--------------------------------------------------------------

# 真实 DOM 形态（独立审查 2026-07-22 真实抓取，见
# tests/fixtures/pmlr/raw/09_site_root_normal.html 文件头注释与来源声明）。
_SITE_ROOT_OK = fixture_bytes("09_site_root_normal.html")


def test_healthcheck_ok_site_root() -> None:
    handler: Handler = lambda request: httpx.Response(200, content=_SITE_ROOT_OK)  # noqa: E731
    report = _adapter(handler).healthcheck()
    assert report.healthy is True


def test_healthcheck_requests_site_root_url() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, content=_SITE_ROOT_OK)

    _adapter(handler).healthcheck()
    assert seen == ["https://proceedings.mlr.press/"]


def test_healthcheck_matches_real_bold_wrapped_early_closing_anchor() -> None:
    """回归：真实站点锚点markup `<a href="v235"><b>Volume 235</b></a> Proceedings
    of ICML 2024`——"Volume N" 被 `<b>` 包裹且锚点在此提前闭合，"Proceedings
    of…" 落在锚点外的纯文本（独立审查 2026-07-22 100% 复现的 HIGH 缺陷，已修复：
    `healthcheck()` 现对 `parse.clean_text()` 转换后的可见文本匹配，不对带标签
    原始 HTML 直接做 `\\s+` 正则）。用单条目最小 fixture 精确复刻该失配形态，
    独立于 `_SITE_ROOT_OK`（多条目）之外单独钉死，防止回归。
    """
    html = (
        b"<html><head><title>Proceedings of Machine Learning Research</title></head>"
        b'<body><a href="v235"><b>Volume 235</b></a> Proceedings of ICML 2024</body></html>'
    )
    handler: Handler = lambda request: httpx.Response(200, content=html)  # noqa: E731
    report = _adapter(handler).healthcheck()
    assert report.healthy is True
    assert report.detail == "site root reachable with expected title + volume anchor"


def test_healthcheck_missing_title_text_is_unhealthy() -> None:
    handler: Handler = lambda request: httpx.Response(  # noqa: E731
        200, content=b"<html><body>nothing relevant here</body></html>"
    )
    report = _adapter(handler).healthcheck()
    assert report.healthy is False
    assert "title" in report.detail


def test_healthcheck_missing_volume_anchor_is_unhealthy() -> None:
    handler: Handler = lambda request: httpx.Response(  # noqa: E731
        200,
        content=b"<html><title>Proceedings of Machine Learning Research</title>no anchors</html>",
    )
    report = _adapter(handler).healthcheck()
    assert report.healthy is False
    assert "anchor" in report.detail


def test_healthcheck_unreachable_returns_unhealthy_not_raise() -> None:
    handler: Handler = lambda request: httpx.Response(503, content=b"down")  # noqa: E731
    report = _adapter(handler).healthcheck()
    assert report.healthy is False
    assert "unreachable" in report.detail


# --- UA 惰性自建 ---------------------------------------------------------------------------------


def test_default_user_agent_uses_env_email(monkeypatch: pytest.MonkeyPatch) -> None:
    from paper_crawler.adapters.pmlr import adapter as mod

    monkeypatch.setenv(mod._CONTACT_EMAIL_ENV, "real@lab.edu")
    ua = mod._default_user_agent()
    assert ua.startswith("PaperCrawler/")
    assert ua.endswith("(personal research; mailto:real@lab.edu)")


def test_default_user_agent_falls_back_to_placeholder(monkeypatch: pytest.MonkeyPatch) -> None:
    from paper_crawler.adapters.pmlr import adapter as mod

    monkeypatch.delenv(mod._CONTACT_EMAIL_ENV, raising=False)
    ua = mod._default_user_agent()
    assert ua.endswith("(personal research; mailto:anonymous@paper-crawler.invalid)")
