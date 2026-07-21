"""NeuripsProceedingsAdapter 主体单测（design/adapters/neurips-proceedings.md §3-§6；T1/T5）。

零真实网络：网络型方法（enumerate/fetch/healthcheck）经 `HttpClient(transport=
httpx.MockTransport(...))` 注入受控响应；纯逻辑方法（discover/resolve）无 http
依赖。用内联 HTML 片段覆盖 adapter 主体逻辑（quirks 年份边界/后缀回退闭表/错误
映射）；真实站点响应结构的十一件套 fixture 由集成/契约层加载
（tests/fixtures/neurips_proceedings/）。
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

import httpx
import pytest

from helpers import FakeFetchIO, make_neurips_venue
from paper_crawler.adapters.neurips_proceedings.adapter import (
    _CANARIES,
    NeuripsProceedingsAdapter,
)
from paper_crawler.errors import CrawlerError, ErrorClass
from paper_crawler.http import HttpClient
from paper_crawler.types import AssetKind, AuthLevel, Capability, IssueRef, PaperStub, UrlStrategy

_TEST_UA = "PaperCrawler/test (personal research; mailto:test@example.com)"

Handler = Callable[[httpx.Request], httpx.Response]


def _adapter(handler: Handler) -> NeuripsProceedingsAdapter:
    client = HttpClient(user_agent=_TEST_UA, transport=httpx.MockTransport(handler))
    return NeuripsProceedingsAdapter(http=client)


def _li(*, li_class: str, track: str, href: str, title: str, authors: str, badge: str = "") -> str:
    badge_html = f'<span class="paper-track-badge">{badge}</span>' if badge else ""
    return (
        f'<li class="{li_class}" data-track="{track}">'
        '<div class="paper-content">'
        f'<a title="paper title" href="{href}">{title}</a>'
        f'<span class="paper-authors">{authors}</span>'
        f"</div>{badge_html}</li>"
    )


def _legacy_li(*, hash_: str, title: str, year: int = 2021) -> str:
    return _li(
        li_class="",
        track="none",
        href=f"/paper_files/paper/{year}/hash/{hash_}-Abstract.html",
        title=title,
        authors="A. Author",
    )


def _modern_li(*, hash_: str, title: str, track: str, year: int = 2022) -> str:
    suffix = "-Conference" if track == "conference" else "-Datasets_and_Benchmarks"
    badge = "Main Conference Track" if track == "conference" else "Datasets and Benchmarks Track"
    return _li(
        li_class=track,
        track=track,
        href=f"/paper_files/paper/{year}/hash/{hash_}-Abstract{suffix}.html",
        title=title,
        authors="B. Author",
        badge=badge,
    )


def _year_page(*lis: str) -> bytes:
    return f"<html><body><ul class='paper-list'>{''.join(lis)}</ul></body></html>".encode()


# --- 元数据 ------------------------------------------------------------------------------------


def test_adapter_metadata_matches_design_verdicts() -> None:
    a = NeuripsProceedingsAdapter()
    assert a.adapter_id == "neurips_proceedings"
    assert a.family == "open_access"
    assert a.capabilities == (
        Capability.DISCOVER | Capability.ENUMERATE | Capability.RESOLVE | Capability.FETCH
    )
    assert Capability.SEARCH not in a.capabilities
    assert a.auth_requirement == AuthLevel.NONE
    assert a.domains == ("proceedings.neurips.cc", "papers.neurips.cc", "papers.nips.cc")
    assert a.default_rate.requests_per_minute == 30.0
    assert a.default_rate.source_note != ""


def test_set_http_client_injection_overrides_lazy_env_build() -> None:
    adapter = NeuripsProceedingsAdapter()
    injected = HttpClient(user_agent=_TEST_UA)
    adapter.set_http_client(injected)
    assert adapter._client() is injected


def test_lazy_client_builds_and_caches_httpclient_when_http_none() -> None:
    a = NeuripsProceedingsAdapter()
    client = a._client()
    assert isinstance(client, HttpClient)
    assert a._client() is client
    client.close()


# --- discover（零网络）------------------------------------------------------------------------


def test_discover_yields_issues_for_configured_year_range() -> None:
    issues = list(NeuripsProceedingsAdapter().discover_timeline(make_neurips_venue()))
    assert [i.year for i in issues] == [2021, 2022]
    first = issues[0]
    assert first.venue_id == "neurips"
    assert first.volume is None
    assert first.number is None
    assert first.label == "2021"
    assert first.pub_date is None
    assert first.paper_count_claimed is None
    assert issues[1].label == "2022"


def test_discover_since_filters_to_year_lower_bound() -> None:
    issues = list(NeuripsProceedingsAdapter().discover_timeline(make_neurips_venue(), since="2022"))
    assert [i.year for i in issues] == [2022]


def test_discover_since_before_first_year_does_not_widen_start() -> None:
    issues = list(NeuripsProceedingsAdapter().discover_timeline(make_neurips_venue(), since="1900"))
    assert [i.year for i in issues] == [2021, 2022]


def test_discover_default_first_year_is_1987_when_quirk_absent() -> None:
    venue = make_neurips_venue(known_through_year=1990)
    del venue.quirks["first_year"]
    issues = list(NeuripsProceedingsAdapter().discover_timeline(venue))
    assert [i.year for i in issues] == [1987, 1988, 1989, 1990]


def test_discover_default_known_through_year_is_current_utc_year_minus_one() -> None:
    venue = make_neurips_venue(first_year=datetime.now(UTC).year - 1)
    del venue.quirks["known_through_year"]
    issues = list(NeuripsProceedingsAdapter().discover_timeline(venue))
    assert [i.year for i in issues] == [datetime.now(UTC).year - 1]


def test_discover_legal_empty_range_yields_no_issues_not_error() -> None:
    # known_through_year < first_year（例如 quirk 手误/年度切换瞬间）——非法态？不，
    # 是"没有已发布年落入区间"的合法空态；不该报错，只是产 0 个 Issue。
    venue = make_neurips_venue(first_year=2022, known_through_year=2020)
    assert list(NeuripsProceedingsAdapter().discover_timeline(venue)) == []


def test_discover_first_year_non_coercible_is_config_error() -> None:
    with pytest.raises(CrawlerError) as exc:
        list(NeuripsProceedingsAdapter().discover_timeline(make_neurips_venue(first_year="abc")))
    assert exc.value.error_class is ErrorClass.CONFIG


def test_discover_known_through_year_non_coercible_is_config_error() -> None:
    with pytest.raises(CrawlerError) as exc:
        list(
            NeuripsProceedingsAdapter().discover_timeline(
                make_neurips_venue(known_through_year="soon")
            )
        )
    assert exc.value.error_class is ErrorClass.CONFIG


def test_discover_bool_year_quirk_is_config_error() -> None:
    # bool 是 int 子类——True/False 当年份是荒谬值，显式挡掉（openreview 先例）。
    with pytest.raises(CrawlerError) as exc:
        list(NeuripsProceedingsAdapter().discover_timeline(make_neurips_venue(first_year=True)))
    assert exc.value.error_class is ErrorClass.CONFIG


def test_discover_since_invalid_format_is_config_error() -> None:
    with pytest.raises(CrawlerError) as exc:
        list(
            NeuripsProceedingsAdapter().discover_timeline(make_neurips_venue(), since="not-a-year")
        )
    assert exc.value.error_class is ErrorClass.CONFIG


def test_discover_accepts_quoted_string_year_quirks() -> None:
    # PyYAML 对无引号整数给 int，加引号给 str——两种形态都要接受。
    issues = list(
        NeuripsProceedingsAdapter().discover_timeline(
            make_neurips_venue(first_year="2021", known_through_year="2021")
        )
    )
    assert [i.year for i in issues] == [2021]


# --- resolve（零网络，纯构造）------------------------------------------------------------------


def test_resolve_legacy_paper_uses_captured_empty_asset_suffix() -> None:
    paper = PaperStub(
        title="T",
        identifiers=(("neurips", "03004620ea802b9118dd44d69f07af56"),),
        year=1987,
        meta=(("track", "none"), ("asset_suffix", "")),
    )
    plans = NeuripsProceedingsAdapter().resolve_assets(make_neurips_venue(), paper)
    assert len(plans) == 1
    plan = plans[0]
    assert plan.kind is AssetKind.PDF
    assert plan.url == (
        "https://proceedings.neurips.cc/paper_files/paper/1987/file/"
        "03004620ea802b9118dd44d69f07af56-Paper.pdf"
    )
    assert plan.url_strategy is UrlStrategy.DIRECT
    assert plan.auth_needed is AuthLevel.NONE
    assert plan.expected_type == "application/pdf"
    assert plan.version is None


def test_resolve_modern_conference_paper_uses_captured_asset_suffix() -> None:
    paper = PaperStub(
        title="T",
        identifiers=(("neurips", "0001ca33ba34ce0351e4612b744b3936"),),
        year=2023,
        meta=(("track", "conference"), ("asset_suffix", "-Conference")),
    )
    plans = NeuripsProceedingsAdapter().resolve_assets(make_neurips_venue(), paper)
    assert plans[0].url == (
        "https://proceedings.neurips.cc/paper_files/paper/2023/file/"
        "0001ca33ba34ce0351e4612b744b3936-Paper-Conference.pdf"
    )


def test_resolve_modern_db_paper_uses_captured_asset_suffix() -> None:
    paper = PaperStub(
        title="T",
        identifiers=(("neurips", "00ba06ba5c324efdfb068865ca44cf0b"),),
        year=2023,
        meta=(("track", "datasets_and_benchmarks"), ("asset_suffix", "-Datasets_and_Benchmarks")),
    )
    plans = NeuripsProceedingsAdapter().resolve_assets(make_neurips_venue(), paper)
    assert plans[0].url == (
        "https://proceedings.neurips.cc/paper_files/paper/2023/file/"
        "00ba06ba5c324efdfb068865ca44cf0b-Paper-Datasets_and_Benchmarks.pdf"
    )


def test_resolve_falls_back_to_closed_table_when_asset_suffix_key_absent() -> None:
    # meta 缺 asset_suffix 键（如手工构造的 stub，未经 enumerate）——回退 (era,track) 闭表。
    paper = PaperStub(
        title="T",
        identifiers=(("neurips", "0001ca33ba34ce0351e4612b744b3936"),),
        year=2023,
        meta=(("track", "conference"),),
    )
    plans = NeuripsProceedingsAdapter().resolve_assets(make_neurips_venue(), paper)
    assert plans[0].url.endswith("-Paper-Conference.pdf")


def test_resolve_modern_unknown_track_without_asset_suffix_is_config() -> None:
    paper = PaperStub(
        title="T",
        identifiers=(("neurips", "0001ca33ba34ce0351e4612b744b3936"),),
        year=2023,
        meta=(("track", "position_papers"),),
    )
    with pytest.raises(CrawlerError) as exc:
        NeuripsProceedingsAdapter().resolve_assets(make_neurips_venue(), paper)
    assert exc.value.error_class is ErrorClass.CONFIG


def test_resolve_modern_missing_both_asset_suffix_and_track_is_config() -> None:
    paper = PaperStub(
        title="T", identifiers=(("neurips", "0001ca33ba34ce0351e4612b744b3936"),), year=2023
    )
    with pytest.raises(CrawlerError) as exc:
        NeuripsProceedingsAdapter().resolve_assets(make_neurips_venue(), paper)
    assert exc.value.error_class is ErrorClass.CONFIG


def test_resolve_missing_neurips_identifier_is_config() -> None:
    paper = PaperStub(title="T", identifiers=(("doi", "10.1/x"),), year=2023)
    with pytest.raises(CrawlerError) as exc:
        NeuripsProceedingsAdapter().resolve_assets(make_neurips_venue(), paper)
    assert exc.value.error_class is ErrorClass.CONFIG


def test_resolve_malformed_identifier_value_is_config() -> None:
    paper = PaperStub(title="T", identifiers=(("neurips", "not-32-hex"),), year=2023)
    with pytest.raises(CrawlerError) as exc:
        NeuripsProceedingsAdapter().resolve_assets(make_neurips_venue(), paper)
    assert exc.value.error_class is ErrorClass.CONFIG


def test_resolve_missing_year_is_config() -> None:
    paper = PaperStub(
        title="T",
        identifiers=(("neurips", "0001ca33ba34ce0351e4612b744b3936"),),
        meta=(("track", "conference"), ("asset_suffix", "-Conference")),
    )
    with pytest.raises(CrawlerError) as exc:
        NeuripsProceedingsAdapter().resolve_assets(make_neurips_venue(), paper)
    assert exc.value.error_class is ErrorClass.CONFIG


# --- enumerate（1 请求/届）----------------------------------------------------------------------


def test_enumerate_requests_the_expected_year_page_url() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(
            200, content=_year_page(_legacy_li(hash_="03004620ea802b9118dd44d69f07af56", title="T"))
        )

    issue = IssueRef(venue_id="neurips", year=2021, label="2021")
    list(_adapter(handler).enumerate_issue(make_neurips_venue(), issue))
    assert seen == ["https://proceedings.neurips.cc/paper_files/paper/2021"]


def test_enumerate_legacy_page_single_entry() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=_year_page(
                _legacy_li(hash_="03004620ea802b9118dd44d69f07af56", title="Synchronization")
            ),
        )

    issue = IssueRef(venue_id="neurips", year=1987, label="1987")
    stubs = list(_adapter(handler).enumerate_issue(make_neurips_venue(), issue))
    assert len(stubs) == 1
    assert stubs[0].identifiers == (("neurips", "03004620ea802b9118dd44d69f07af56"),)
    assert stubs[0].year == 1987
    assert dict(stubs[0].meta) == {"track": "none", "asset_suffix": ""}


def test_enumerate_modern_page_mixed_tracks() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=_year_page(
                _modern_li(
                    hash_="deadbeefdeadbeefdeadbeefdeadbeef", title="Conf Paper", track="conference"
                ),
                _modern_li(
                    hash_="facefeedfacefeedfacefeedfacefeed",
                    title="DB Paper",
                    track="datasets_and_benchmarks",
                ),
            ),
        )

    issue = IssueRef(venue_id="neurips", year=2022, label="2022")
    stubs = list(_adapter(handler).enumerate_issue(make_neurips_venue(), issue))
    assert len(stubs) == 2
    assert dict(stubs[0].meta)["track"] == "conference"
    assert dict(stubs[1].meta)["track"] == "datasets_and_benchmarks"
    assert dict(stubs[0].meta)["asset_suffix"] == "-Conference"
    assert dict(stubs[1].meta)["asset_suffix"] == "-Datasets_and_Benchmarks"


def test_enumerate_issue_year_none_is_config_error() -> None:
    handler: Handler = lambda request: httpx.Response(200, content=_year_page())  # noqa: E731
    bad = IssueRef(venue_id="neurips", year=None)
    with pytest.raises(CrawlerError) as exc:
        list(_adapter(handler).enumerate_issue(make_neurips_venue(), bad))
    assert exc.value.error_class is ErrorClass.CONFIG


def test_enumerate_year_page_404_is_gone() -> None:
    handler: Handler = lambda request: httpx.Response(  # noqa: E731
        404, content=b"<h1>Page Not Found</h1>"
    )
    issue = IssueRef(venue_id="neurips", year=1986, label="1986")
    with pytest.raises(CrawlerError) as exc:
        list(_adapter(handler).enumerate_issue(make_neurips_venue(), issue))
    assert exc.value.error_class is ErrorClass.GONE


def test_enumerate_zero_entries_is_parse_error_not_legal_empty() -> None:
    # neurips 无合法"200 空列表"态（已发布年恒非空）——0 条目统一判 parse。
    handler: Handler = lambda request: httpx.Response(  # noqa: E731
        200, content=b"<html><body>totally different layout</body></html>"
    )
    issue = IssueRef(venue_id="neurips", year=2021, label="2021")
    with pytest.raises(CrawlerError) as exc:
        list(_adapter(handler).enumerate_issue(make_neurips_venue(), issue))
    assert exc.value.error_class is ErrorClass.PARSE


def test_enumerate_year_page_503_is_transient() -> None:
    handler: Handler = lambda request: httpx.Response(503, content=b"down")  # noqa: E731
    issue = IssueRef(venue_id="neurips", year=2021, label="2021")
    with pytest.raises(CrawlerError) as exc:
        list(_adapter(handler).enumerate_issue(make_neurips_venue(), issue))
    assert exc.value.error_class is ErrorClass.TRANSIENT


# --- fetch（流式）------------------------------------------------------------------------------


def test_fetch_streams_pdf_bytes_ok() -> None:
    pdf = b"%PDF-1.5\n" + b"payload-bytes " * 64 + b"\n%%EOF\n"
    handler: Handler = lambda request: httpx.Response(200, content=pdf)  # noqa: E731
    paper = PaperStub(
        title="T",
        identifiers=(("neurips", "0001ca33ba34ce0351e4612b744b3936"),),
        year=2023,
        meta=(("track", "conference"), ("asset_suffix", "-Conference")),
    )
    plan = NeuripsProceedingsAdapter().resolve_assets(make_neurips_venue(), paper)[0]
    io = FakeFetchIO()
    result = _adapter(handler).fetch_asset(plan, io)
    assert result.ok is True
    assert result.bytes_written == len(pdf)
    assert io.data == pdf


def test_fetch_http_404_is_gone_via_httpclient() -> None:
    handler: Handler = lambda request: httpx.Response(404, content=b"not found")  # noqa: E731
    paper = PaperStub(
        title="T",
        identifiers=(("neurips", "0001ca33ba34ce0351e4612b744b3936"),),
        year=2023,
        meta=(("track", "conference"), ("asset_suffix", "-Conference")),
    )
    plan = NeuripsProceedingsAdapter().resolve_assets(make_neurips_venue(), paper)[0]
    with pytest.raises(CrawlerError) as exc:
        _adapter(handler).fetch_asset(plan, FakeFetchIO())
    assert exc.value.error_class is ErrorClass.GONE


def test_fetch_pdf_url_returning_html_is_gone_sniffed() -> None:
    handler: Handler = lambda request: httpx.Response(  # noqa: E731
        200, content=b"<!DOCTYPE html><html><body>removed</body></html>"
    )
    paper = PaperStub(
        title="T",
        identifiers=(("neurips", "0001ca33ba34ce0351e4612b744b3936"),),
        year=2023,
        meta=(("track", "conference"), ("asset_suffix", "-Conference")),
    )
    plan = NeuripsProceedingsAdapter().resolve_assets(make_neurips_venue(), paper)[0]
    with pytest.raises(CrawlerError) as exc:
        _adapter(handler).fetch_asset(plan, FakeFetchIO())
    assert exc.value.error_class is ErrorClass.GONE


# --- healthcheck（2 请求，跨边界 canary）---------------------------------------------------------


def _canary_li(canary_index: int) -> str:
    canary = _CANARIES[canary_index]
    if canary.track == "none":
        return _legacy_li(hash_=canary.hash, title=canary.title, year=canary.year)
    return _modern_li(hash_=canary.hash, title=canary.title, track=canary.track, year=canary.year)


def _healthy_pages_handler(request: httpx.Request) -> httpx.Response:
    if request.url.path.endswith("/2021"):
        return httpx.Response(
            200,
            content=_year_page(
                _canary_li(0),
                _legacy_li(hash_="0bad0bad0bad0bad0bad0bad0bad0bad", title="Filler 2021 A"),
            ),
        )
    if request.url.path.endswith("/2022"):
        return httpx.Response(
            200,
            content=_year_page(
                _canary_li(1),
                _canary_li(2),
                _modern_li(
                    hash_="cafecafecafecafecafecafecafecafe",
                    title="Filler 2022 Conference",
                    track="conference",
                ),
            ),
        )
    raise AssertionError(f"unexpected healthcheck request: {request.url}")


def test_healthcheck_all_three_canaries_match_is_healthy() -> None:
    report = _adapter(_healthy_pages_handler).healthcheck()
    assert report.healthy is True
    assert "3 canaries matched" in report.detail


def test_healthcheck_requests_exactly_2021_and_2022_year_pages() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return _healthy_pages_handler(request)

    _adapter(handler).healthcheck()
    assert seen == [
        "https://proceedings.neurips.cc/paper_files/paper/2021",
        "https://proceedings.neurips.cc/paper_files/paper/2022",
    ]


def test_healthcheck_missing_canary_is_unhealthy() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/2021"):
            # 2021 canary hash 缺席——两篇不相关的 filler（凑够篇数下限，专测 canary
            # 缺席这一件事，不与"篇数过低"分支混淆）。
            return httpx.Response(
                200,
                content=_year_page(
                    _legacy_li(hash_="0bad0bad0bad0bad0bad0bad0bad0bad", title="Filler A"),
                    _legacy_li(hash_="feedfeedfeedfeedfeedfeedfeedfeed", title="Filler B"),
                ),
            )
        return httpx.Response(200, content=_year_page(_canary_li(1), _canary_li(2)))

    report = _adapter(handler).healthcheck()
    assert report.healthy is False
    assert "canary drift" in report.detail
    assert "missing from response" in report.detail


def test_healthcheck_title_drift_is_unhealthy() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/2021"):
            drifted = _legacy_li(hash_=_CANARIES[0].hash, title="A Completely Different Title")
            filler = _legacy_li(hash_="feedfeedfeedfeedfeedfeedfeedfeed", title="Filler")
            return httpx.Response(200, content=_year_page(drifted, filler))
        return httpx.Response(200, content=_year_page(_canary_li(1), _canary_li(2)))

    report = _adapter(handler).healthcheck()
    assert report.healthy is False
    assert "title drift" in report.detail


def test_healthcheck_track_drift_is_unhealthy() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/2021"):
            filler = _legacy_li(hash_="feedfeedfeedfeedfeedfeedfeedfeed", title="Filler")
            return httpx.Response(200, content=_year_page(_canary_li(0), filler))
        # canary 1（conference）被错误地放进了 D&B track——同 title/hash，track 漂移。
        wrong_track = _modern_li(
            hash_=_CANARIES[1].hash, title=_CANARIES[1].title, track="datasets_and_benchmarks"
        )
        return httpx.Response(200, content=_year_page(wrong_track, _canary_li(2)))

    report = _adapter(handler).healthcheck()
    assert report.healthy is False
    assert "track drift" in report.detail


def test_healthcheck_below_minimum_paper_count_is_unhealthy() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/2021"):
            # 只有 1 篇（含 canary），低于 _HEALTHCHECK_MIN_PAPERS[2021]=2 的下限。
            return httpx.Response(200, content=_year_page(_canary_li(0)))
        return httpx.Response(200, content=_year_page(_canary_li(1), _canary_li(2)))

    report = _adapter(handler).healthcheck()
    assert report.healthy is False
    assert "< 2 floor" in report.detail


def test_healthcheck_year_page_unreachable_is_unhealthy_not_raise() -> None:
    handler: Handler = lambda request: httpx.Response(503, content=b"down")  # noqa: E731
    report = _adapter(handler).healthcheck()
    assert report.healthy is False
    assert "fetch/parse failed" in report.detail
    assert "transient" in report.detail


def test_healthcheck_year_page_parse_failure_is_unhealthy_not_raise() -> None:
    handler: Handler = lambda request: httpx.Response(  # noqa: E731
        200, content=b"<html><body>nothing here</body></html>"
    )
    report = _adapter(handler).healthcheck()
    assert report.healthy is False
    assert "parse" in report.detail


# --- UA 惰性自建 ---------------------------------------------------------------------------------


def test_default_user_agent_uses_env_email(monkeypatch: pytest.MonkeyPatch) -> None:
    from paper_crawler.adapters.neurips_proceedings import adapter as mod

    monkeypatch.setenv(mod._CONTACT_EMAIL_ENV, "real@lab.edu")
    ua = mod._default_user_agent()
    assert ua.startswith("PaperCrawler/")
    assert ua.endswith("(personal research; mailto:real@lab.edu)")


def test_default_user_agent_falls_back_to_placeholder(monkeypatch: pytest.MonkeyPatch) -> None:
    from paper_crawler.adapters.neurips_proceedings import adapter as mod

    monkeypatch.delenv(mod._CONTACT_EMAIL_ENV, raising=False)
    ua = mod._default_user_agent()
    assert ua.endswith("(personal research; mailto:anonymous@paper-crawler.invalid)")
