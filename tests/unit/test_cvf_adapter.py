"""CVFAdapter 主体单测（design/adapters/cvf.md §3-§6；T1）。

零真实网络：网络型方法（enumerate/resolve 的零网络断言/fetch/healthcheck）经
`HttpClient(transport=httpx.MockTransport(...))` 注入受控响应；discover 纯逻辑
无 http 依赖。覆盖 discover cadence+字段分解+since、enumerate 双形态入口探测
（flat 1 请求 / day_landing 2 请求 / list_mode 覆盖 / 结构漂移→PARSE）、resolve
零网络+expected_type 推断、fetch 流式写入、healthcheck 主路径+退化 menu 路径、
HttpClientConsumer 注入协议、UA 兜底。
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

import httpx
import pytest

from helpers import FakeFetchIO, make_cvf_venue
from paper_crawler.adapters.cvf import parse
from paper_crawler.adapters.cvf.adapter import CVFAdapter
from paper_crawler.errors import CrawlerError, ErrorClass
from paper_crawler.http import HttpClient
from paper_crawler.types import AssetKind, AuthLevel, Capability, IssueRef, PaperStub, UrlStrategy

_UA = "PaperCrawler/test (personal research; mailto:test@example.com)"

Handler = Callable[[httpx.Request], httpx.Response]


def _adapter(handler: Handler, *, current_year: int | None = None) -> CVFAdapter:
    client = HttpClient(user_agent=_UA, transport=httpx.MockTransport(handler))
    return CVFAdapter(http=client, current_year=current_year)


def _issue(year: int) -> IssueRef:
    return IssueRef(venue_id="cvpr", year=year, label=f"{year:04d}")


def _entry_html(
    *,
    title: str,
    pdf_href: str,
    supp_href: str | None = None,
    author_input_name: str = "query_author",
) -> str:
    """`author_input_name` 默认 modern `?day=all` 的真实属性名 `"query_author"`；

    flat 早年页（2013 起）用 `"query"`——两者是 era 差异，非同义写法（2026-07-22
    独立审查对 CVPR2013/ICCV2013 双会活取证实，见 `parse._AUTHOR_INPUT_NAMES`）。
    调用方按所测 era 显式传入。
    """
    return (
        f'<dt class="ptitle"><br><a href="/content/CVPR2023/html/x.html">{title}</a></dt>\n'
        f'<dd><input type="hidden" name="{author_input_name}" value="An Author"></dd>\n'
        "<dd>\n"
        f'[<a href="{pdf_href}">pdf</a>]\n'
        + (f'[<a href="{supp_href}">supp</a>]\n' if supp_href else "")
        + "</dd>\n"
    )


def _page(*entries: str) -> str:
    return f'<html><body><div id="content"><dl>\n{"".join(entries)}\n</dl></div></body></html>'


_DAY_LANDING_HTML = """
<div id="content"><h3>Papers</h3><dl>
<dd>[<a href="/CVPR2023?day=2023-06-20">Day 1: 2023-06-20</a>]<br><br></dd>
<dd>[<a href="/CVPR2023?day=2023-06-21">Day 2: 2023-06-21</a>]<br><br></dd>
<dd>[<a href="/CVPR2023?day=all">All Papers</a>]<br><br></dd>
</dl></div>
"""


# --- discover（零网络）-------------------------------------------------------------------------


def test_discover_capability_declared() -> None:
    a = CVFAdapter()
    assert Capability.DISCOVER in a.capabilities
    assert Capability.ENUMERATE in a.capabilities
    assert Capability.RESOLVE in a.capabilities
    assert Capability.FETCH in a.capabilities
    assert Capability.SEARCH not in a.capabilities
    assert a.auth_requirement is AuthLevel.NONE
    assert a.domains == ("openaccess.thecvf.com",)


def test_discover_field_decomposition_is_fixed() -> None:
    a = CVFAdapter(current_year=2026)
    issue = next(i for i in a.discover_timeline(make_cvf_venue("cvpr")) if i.year == 2023)
    assert issue.venue_id == "cvpr"
    assert issue.volume is None
    assert issue.number is None
    assert issue.year == 2023
    assert issue.label == "2023"
    assert issue.pub_date is None
    assert issue.paper_count_claimed is None


def test_discover_cvpr_annual_with_injected_current_year() -> None:
    a = CVFAdapter(current_year=2026)
    years = [i.year for i in a.discover_timeline(make_cvf_venue("cvpr"))]
    assert years == list(range(2013, 2027))


def test_discover_iccv_odd_years_with_injected_current_year() -> None:
    a = CVFAdapter(current_year=2026)
    years = [i.year for i in a.discover_timeline(make_cvf_venue("iccv"))]
    assert years == [2013, 2015, 2017, 2019, 2021, 2023, 2025]


def test_discover_wacv_annual_from_2020_with_injected_current_year() -> None:
    a = CVFAdapter(current_year=2026)
    years = [i.year for i in a.discover_timeline(make_cvf_venue("wacv"))]
    assert years == list(range(2020, 2027))


def test_discover_since_narrows_lower_bound() -> None:
    a = CVFAdapter(current_year=2026)
    issues = list(a.discover_timeline(make_cvf_venue("cvpr"), since="2020"))
    assert all(i.year is not None and i.year >= 2020 for i in issues)


def test_discover_without_injection_uses_real_clock() -> None:
    a = CVFAdapter()
    assert a._current_year() == datetime.now(UTC).year  # noqa: SLF001


# --- enumerate：入口探测分支（flat/day_landing/list_mode/结构漂移）----------------------------


def test_enumerate_flat_era_single_request() -> None:
    request_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        assert request.url.path == "/CVPR2013"
        html = _page(
            _entry_html(
                title="Old Paper",
                pdf_href="content_cvpr_2013/papers/Smith_Old_Paper_2013_CVPR_paper.pdf",
                author_input_name="query",  # flat era 真实属性名（2026-07-22 审查校正）
            )
        )
        return httpx.Response(200, content=html.encode("utf-8"))

    stubs = list(_adapter(handler).enumerate_issue(make_cvf_venue("cvpr"), _issue(2013)))
    assert request_count == 1  # flat era：1 请求拿全（design §3.2）
    assert len(stubs) == 1
    assert stubs[0].identifiers == (("cvf", "CVPR2013/Smith_Old_Paper_2013_CVPR_paper"),)
    # 回归守卫：flat era 用 name="query" 抽出的 authors 非空（2026-07-22 独立审查
    # HIGH 发现——旧实现硬编码 "query_author" 时本行会以 () 静默失败）。
    assert stubs[0].authors == ("An Author",)


def test_enumerate_day_landing_then_day_all_two_requests() -> None:
    urls_hit: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        urls_hit.append(str(request.url))
        if request.url.params.get("day") == "all":
            html = _page(
                _entry_html(
                    title="Modern Paper",
                    pdf_href="/content/CVPR2023/papers/Doe_Modern_Paper_CVPR_2023_paper.pdf",
                )
            )
            return httpx.Response(200, content=html.encode("utf-8"))
        return httpx.Response(200, content=_DAY_LANDING_HTML.encode("utf-8"))

    stubs = list(_adapter(handler).enumerate_issue(make_cvf_venue("cvpr"), _issue(2023)))
    assert len(urls_hit) == 2  # bare 探测 + ?day=all 二次取全集（design §3.2）
    assert urls_hit[0].endswith("/CVPR2023")
    assert "day=all" in urls_hit[1]
    assert len(stubs) == 1
    assert stubs[0].title == "Modern Paper"


def test_enumerate_structural_drift_zero_entries_no_day_all_link_raises_parse() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"<html><body>unexpected layout</body></html>")

    with pytest.raises(CrawlerError) as exc:
        list(_adapter(handler).enumerate_issue(make_cvf_venue("cvpr"), _issue(2023)))
    assert exc.value.error_class is ErrorClass.PARSE


def test_enumerate_day_all_page_itself_empty_raises_parse() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("day") == "all":
            return httpx.Response(200, content=b"<html><body>drifted all-page</body></html>")
        return httpx.Response(200, content=_DAY_LANDING_HTML.encode("utf-8"))

    with pytest.raises(CrawlerError) as exc:
        list(_adapter(handler).enumerate_issue(make_cvf_venue("cvpr"), _issue(2023)))
    assert exc.value.error_class is ErrorClass.PARSE


def test_enumerate_forced_flat_mode_skips_day_all_probe_on_success() -> None:
    request_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        html = _page(
            _entry_html(
                title="Forced Flat Paper", pdf_href="/content/CVPR2023/papers/forced_flat.pdf"
            )
        )
        return httpx.Response(200, content=html.encode("utf-8"))

    venue = make_cvf_venue("cvpr", list_mode="flat")
    stubs = list(_adapter(handler).enumerate_issue(venue, _issue(2023)))
    assert request_count == 1
    assert len(stubs) == 1


def test_enumerate_forced_flat_mode_zero_entries_raises_parse_without_day_all_check() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        # 即使含 day=all 链接，list_mode=flat 强制下也不应触发二次探测。
        return httpx.Response(200, content=_DAY_LANDING_HTML.encode("utf-8"))

    venue = make_cvf_venue("cvpr", list_mode="flat")
    with pytest.raises(CrawlerError) as exc:
        list(_adapter(handler).enumerate_issue(venue, _issue(2023)))
    assert exc.value.error_class is ErrorClass.PARSE
    assert "list_mode=flat" in str(exc.value)


def test_enumerate_forced_day_all_mode_skips_bare_fetch() -> None:
    urls_hit: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        urls_hit.append(str(request.url))
        html = _page(
            _entry_html(
                title="Forced Day All Paper", pdf_href="/content/CVPR2023/papers/forced_all.pdf"
            )
        )
        return httpx.Response(200, content=html.encode("utf-8"))

    venue = make_cvf_venue("cvpr", list_mode="day_all")
    stubs = list(_adapter(handler).enumerate_issue(venue, _issue(2023)))
    assert len(urls_hit) == 1  # 跳过 bare 探测，直取 ?day=all（省 1 请求）
    assert "day=all" in urls_hit[0]
    assert len(stubs) == 1


def test_enumerate_invalid_list_mode_quirk_raises_config() -> None:
    venue = make_cvf_venue("cvpr", list_mode="weekly")

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("不应发出网络请求：list_mode 校验须在请求前失败")

    with pytest.raises(CrawlerError) as exc:
        list(_adapter(handler).enumerate_issue(venue, _issue(2023)))
    assert exc.value.error_class is ErrorClass.CONFIG


def test_enumerate_missing_issue_year_raises_config() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("不应发出网络请求")

    with pytest.raises(CrawlerError) as exc:
        list(_adapter(handler).enumerate_issue(make_cvf_venue("cvpr"), IssueRef(venue_id="cvpr")))
    assert exc.value.error_class is ErrorClass.CONFIG


def test_enumerate_unregistered_venue_id_raises_config() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("不应发出网络请求")

    venue = make_cvf_venue("eccv")  # 本 adapter 不注册 ECCV（design §1）
    with pytest.raises(CrawlerError) as exc:
        list(_adapter(handler).enumerate_issue(venue, _issue(2023)))
    assert exc.value.error_class is ErrorClass.CONFIG


def test_enumerate_url_built_from_venue_and_year_context_not_parsed_from_html() -> None:
    # canonical_dir 由 venue+issue.year 构造（design §3.2："由 enumerate 上下文已知的
    # venue+year 构造，不解析"）——请求 URL 必须是 /ICCV2021，与响应体内容无关。
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/ICCV2021"
        html = _page(
            _entry_html(
                title="ICCV Paper",
                pdf_href="/content/ICCV2021/papers/x_ICCV_2021_paper.pdf",
            )
        )
        return httpx.Response(200, content=html.encode("utf-8"))

    stubs = list(_adapter(handler).enumerate_issue(make_cvf_venue("iccv"), _issue(2021)))
    assert stubs[0].identifiers[0] == ("cvf", "ICCV2021/x_ICCV_2021_paper")


# --- resolve（零网络纯读 meta）------------------------------------------------------------------


def test_resolve_pdf_and_supp_from_meta() -> None:
    paper = PaperStub(
        title="P",
        identifiers=(("cvf", "CVPR2023/x"),),
        meta=(
            (parse.META_PDF_URL, "https://openaccess.thecvf.com/content/CVPR2023/papers/x.pdf"),
            (
                parse.META_SUPP_URL,
                "https://openaccess.thecvf.com/content/CVPR2023/supplemental/x_supp.pdf",
            ),
        ),
    )

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("resolve 必须零网络")

    plans = _adapter(handler).resolve_assets(make_cvf_venue("cvpr"), paper)
    assert len(plans) == 2
    pdf_plan = next(p for p in plans if p.kind is AssetKind.PDF)
    si_plan = next(p for p in plans if p.kind is AssetKind.SI)
    assert pdf_plan.url == "https://openaccess.thecvf.com/content/CVPR2023/papers/x.pdf"
    assert pdf_plan.auth_needed is AuthLevel.NONE
    assert pdf_plan.url_strategy is UrlStrategy.DIRECT
    assert pdf_plan.version is None
    assert si_plan.expected_type == "application/pdf"


def test_resolve_no_supp_yields_single_pdf_plan() -> None:
    paper = PaperStub(
        title="P",
        identifiers=(("cvf", "CVPR2023/y"),),
        meta=((parse.META_PDF_URL, "https://openaccess.thecvf.com/content/CVPR2023/papers/y.pdf"),),
    )

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("resolve 必须零网络")

    plans = _adapter(handler).resolve_assets(make_cvf_venue("cvpr"), paper)
    assert [p.kind for p in plans] == [AssetKind.PDF]


def test_resolve_missing_pdf_meta_yields_zero_plans() -> None:
    # 防御性场景（正常态下 enumerate 已保证 pdf_url 恒存在——见 parse.to_paper_stub）。
    paper = PaperStub(title="P", identifiers=(("cvf", "CVPR2023/z"),), meta=())

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("resolve 必须零网络")

    assert _adapter(handler).resolve_assets(make_cvf_venue("cvpr"), paper) == []


@pytest.mark.parametrize(
    ("supp_url", "expected_type"),
    [
        ("https://openaccess.thecvf.com/.../x_supplemental.pdf", "application/pdf"),
        ("https://openaccess.thecvf.com/.../x_supplemental.zip", "application/zip"),
        ("https://openaccess.thecvf.com/.../x_supplemental.mp4", "video/mp4"),
        ("https://openaccess.thecvf.com/.../x_supplemental.PDF", "application/pdf"),  # 大小写不敏感
        ("https://openaccess.thecvf.com/.../x_supplemental.docx", "application/octet-stream"),
    ],
)
def test_resolve_supp_expected_type_by_extension(supp_url: str, expected_type: str) -> None:
    paper = PaperStub(
        title="P",
        identifiers=(("cvf", "CVPR2023/w"),),
        meta=(
            (parse.META_PDF_URL, "https://openaccess.thecvf.com/.../w.pdf"),
            (parse.META_SUPP_URL, supp_url),
        ),
    )

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("resolve 必须零网络")

    plans = _adapter(handler).resolve_assets(make_cvf_venue("cvpr"), paper)
    si_plan = next(p for p in plans if p.kind is AssetKind.SI)
    assert si_plan.expected_type == expected_type


# --- fetch（流式写入）---------------------------------------------------------------------------


def test_fetch_pdf_writes_bytes() -> None:
    pdf = b"%PDF-1.7\n" + b"x" * 600

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=pdf)

    from paper_crawler.types import AssetPlan

    plan = AssetPlan(kind=AssetKind.PDF, url="https://openaccess.thecvf.com/x.pdf")
    io = FakeFetchIO()
    result = _adapter(handler).fetch_asset(plan, io)
    assert result.ok is True
    assert io.data.startswith(b"%PDF-")
    assert result.bytes_written == len(pdf)


def test_fetch_404_maps_to_gone() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, content=b"Not Found")

    from paper_crawler.types import AssetPlan

    plan = AssetPlan(kind=AssetKind.PDF, url="https://openaccess.thecvf.com/gone.pdf")
    with pytest.raises(CrawlerError) as exc:
        _adapter(handler).fetch_asset(plan, FakeFetchIO())
    assert exc.value.error_class is ErrorClass.GONE


# --- healthcheck（主路径 + 退化 menu 路径）-------------------------------------------------------


def test_healthcheck_healthy_via_current_year_cvpr_day_all() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/CVPR2026"
        html = _page(_entry_html(title="P", pdf_href="/content/CVPR2026/papers/p.pdf"))
        return httpx.Response(200, content=html.encode("utf-8"))

    report = _adapter(handler, current_year=2026).healthcheck()
    assert report.healthy is True
    assert "CVPR2026" in report.detail


def test_healthcheck_falls_back_to_menu_when_current_year_edition_404() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/CVPR2026":
            return httpx.Response(404, content=b"Not Found")
        assert request.url.path == "/menu"
        return httpx.Response(200, content=b"<dd>CVPR 2026, Denver Colorado [...]</dd>")

    report = _adapter(handler, current_year=2026).healthcheck()
    assert report.healthy is True
    assert "menu" in report.detail.lower() or "退化" in report.detail


def test_healthcheck_falls_back_to_menu_when_current_year_page_parses_empty() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/CVPR2026":
            return httpx.Response(200, content=b"<html><body>no entries here</body></html>")
        return httpx.Response(200, content=b"<dd>CVPR 2026, Denver Colorado [...]</dd>")

    report = _adapter(handler, current_year=2026).healthcheck()
    assert report.healthy is True


def test_healthcheck_unhealthy_when_both_cvpr_and_menu_unreachable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, content=b"boom")

    report = _adapter(handler, current_year=2026).healthcheck()
    assert report.healthy is False


def test_healthcheck_unhealthy_when_menu_lacks_year_anchor() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/CVPR2026":
            return httpx.Response(404, content=b"Not Found")
        return httpx.Response(200, content=b"<dd>CVPR 2013, Portland Oregon [...]</dd>")

    report = _adapter(handler, current_year=2026).healthcheck()
    assert report.healthy is False
    assert "CVPR 2026" in report.detail


# --- 注入协议 + UA 兜底 --------------------------------------------------------------------------


def test_set_http_client_injects_client() -> None:
    from paper_crawler.adapter import HttpClientConsumer

    a = CVFAdapter()
    assert isinstance(a, HttpClientConsumer)
    client = HttpClient(user_agent=_UA)
    a.set_http_client(client)
    assert a._client() is client  # noqa: SLF001


def test_client_lazily_self_constructs_when_not_injected() -> None:
    a = CVFAdapter()
    client = a._client()  # noqa: SLF001
    assert isinstance(client, HttpClient)
    assert a._client() is client  # 惰性构造后缓存，重复调用同一实例  # noqa: SLF001


def test_default_user_agent_uses_env_email(monkeypatch: pytest.MonkeyPatch) -> None:
    from paper_crawler.adapters.cvf import adapter as mod

    monkeypatch.setenv("PAPER_CRAWLER_CONTACT_EMAIL", "me@example.org")
    ua = mod._default_user_agent()
    assert "me@example.org" in ua


def test_default_user_agent_placeholder_when_env_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    from paper_crawler.adapters.cvf import adapter as mod

    monkeypatch.delenv("PAPER_CRAWLER_CONTACT_EMAIL", raising=False)
    ua = mod._default_user_agent()
    assert ".invalid" in ua
