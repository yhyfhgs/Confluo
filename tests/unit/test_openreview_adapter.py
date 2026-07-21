"""OpenReviewAdapter 主体单测（design/adapters/openreview.md §3-§6；T1）。

零真实网络：网络型方法（enumerate/fetch/healthcheck）经 `HttpClient(transport=
httpx.MockTransport(...))` 注入受控响应；纯逻辑（discover/resolve）无 http 依赖。覆盖
discover 缺届/字段分解、enumerate 版本判定+翻页+accepted 过滤+403 重分类、resolve
pdf/无 pdf/SI、fetch gone 嗅探、healthcheck 双端。
"""

from __future__ import annotations

import json
from collections.abc import Callable

import httpx
import pytest

from helpers import FakeFetchIO, make_openreview_venue
from paper_crawler.adapters.openreview import parse
from paper_crawler.adapters.openreview.adapter import OpenReviewAdapter
from paper_crawler.errors import CrawlerError, ErrorClass
from paper_crawler.http import HttpClient
from paper_crawler.types import AssetKind, AuthLevel, Capability, IssueRef, PaperStub, UrlStrategy

_UA = "PaperCrawler/test (personal research; mailto:test@example.com)"

Handler = Callable[[httpx.Request], httpx.Response]


def _adapter(handler: Handler, *, extra_headers: dict[str, str] | None = None) -> OpenReviewAdapter:
    client = HttpClient(
        user_agent=_UA, transport=httpx.MockTransport(handler), extra_headers=extra_headers
    )
    return OpenReviewAdapter(http=client)


def _json(obj: object, status: int = 200) -> httpx.Response:
    return httpx.Response(status, content=json.dumps(obj).encode("utf-8"))


def _issue(year: int) -> IssueRef:
    return IssueRef(venue_id="iclr", year=year, label=f"{year:04d}")


def _v2_group(venueid: str) -> dict[str, object]:
    return {"groups": [{"id": venueid, "domain": venueid}], "count": 1}


def _v1_group(venueid: str) -> dict[str, object]:
    return {"groups": [{"id": venueid, "members": []}], "count": 1}


def _v2_note(forum: str, venueid: str, *, pdf: str | None = None) -> dict[str, object]:
    content: dict[str, object] = {
        "title": {"value": f"Paper {forum}"},
        "venueid": {"value": venueid},
    }
    if pdf is not None:
        content["pdf"] = {"value": pdf}
    return {"id": forum, "forum": forum, "content": content}


# --- discover（零网络）---------------------------------------------------------------------


def test_discover_capability_declared() -> None:
    a = OpenReviewAdapter()
    assert Capability.DISCOVER in a.capabilities
    assert Capability.SEARCH not in a.capabilities
    assert a.auth_requirement is AuthLevel.FREE_ACCOUNT


def test_discover_yields_issue_per_year_skipping_missing() -> None:
    a = OpenReviewAdapter()
    issues = list(a.discover_timeline(make_openreview_venue()))
    years = [i.year for i in issues]
    assert 2015 not in years and 2016 not in years  # 缺届
    assert 2013 in years and 2024 in years


def test_discover_field_decomposition_is_fixed() -> None:
    a = OpenReviewAdapter()
    issue = next(i for i in a.discover_timeline(make_openreview_venue()) if i.year == 2024)
    assert issue.venue_id == "iclr"
    assert issue.volume is None
    assert issue.number is None
    assert issue.year == 2024
    assert issue.label == "2024"
    assert issue.pub_date is None
    assert issue.paper_count_claimed is None  # discover 不打 notes 端点


def test_discover_since_narrows_years() -> None:
    a = OpenReviewAdapter()
    issues = list(a.discover_timeline(make_openreview_venue(), since="2020"))
    assert all(i.year is not None and i.year >= 2020 for i in issues)


# --- enumerate：版本判定 + accepted 过滤 + 翻页 -------------------------------------------


def test_enumerate_v2_filters_accepted_by_venueid() -> None:
    venueid = "ICLR.cc/2024/Conference"

    def handler(request: httpx.Request) -> httpx.Response:
        if "/groups" in request.url.path:
            return _json(_v2_group(venueid))
        notes = [
            _v2_note("acc1", venueid, pdf="/pdf/" + "a" * 40 + ".pdf"),
            _v2_note("rej1", venueid + "/Submission"),  # 未接收
            _v2_note("acc2", venueid, pdf="/pdf/" + "b" * 40 + ".pdf"),
            _v2_note("wd1", venueid + "/Withdrawn_Submission"),  # 撤稿
        ]
        return _json({"notes": notes, "count": 4})

    stubs = list(_adapter(handler).enumerate_issue(make_openreview_venue(), _issue(2024)))
    forums = [f for s in stubs for scheme, f in s.identifiers if scheme == "openreview"]
    assert forums == ["acc1", "acc2"]  # 仅接收，被拒/撤稿排除


def test_enumerate_v1_path_uses_direct_content() -> None:
    venueid = "ICLR.cc/2014/conference"

    def handler(request: httpx.Request) -> httpx.Response:
        if "/groups" in request.url.path:
            return _json(_v1_group(venueid))  # 无 domain → v1
        assert request.url.host == "api.openreview.net"  # v1 端点
        note = {
            "id": "old1",
            "forum": "old1",
            "content": {"title": "Old Paper", "venueid": venueid},  # 直取，无 .value
        }
        return _json({"notes": [note], "count": 1})

    stubs = list(_adapter(handler).enumerate_issue(make_openreview_venue(), _issue(2014)))
    assert len(stubs) == 1
    assert stubs[0].title == "Old Paper"
    assert stubs[0].year == 2014  # 从 issue.year 派生


def test_enumerate_v2_hits_api2_host() -> None:
    venueid = "ICLR.cc/2024/Conference"
    hosts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        hosts.append(request.url.host)
        if "/groups" in request.url.path:
            return _json(_v2_group(venueid))
        return _json({"notes": [_v2_note("p", venueid)], "count": 1})

    list(_adapter(handler).enumerate_issue(make_openreview_venue(), _issue(2024)))
    assert "api2.openreview.net" in hosts  # notes 走 v2 端点


def test_enumerate_paginates_until_count() -> None:
    venueid = "ICLR.cc/2024/Conference"
    offsets: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if "/groups" in request.url.path:
            return _json(_v2_group(venueid))
        offset = request.url.params.get("offset", "0")
        offsets.append(offset)
        # count=3，每页 2 条 → 两页翻页。
        if offset == "0":
            return _json({"notes": [_v2_note("a", venueid), _v2_note("b", venueid)], "count": 3})
        return _json({"notes": [_v2_note("c", venueid)], "count": 3})

    stubs = list(_adapter(handler).enumerate_issue(make_openreview_venue(), _issue(2024)))
    assert len(stubs) == 3
    assert offsets == ["0", "2"]  # 第二页 offset=2（累计已取 2）


def test_enumerate_empty_result_is_legal_empty() -> None:
    venueid = "ICLR.cc/2024/Conference"

    def handler(request: httpx.Request) -> httpx.Response:
        if "/groups" in request.url.path:
            return _json(_v2_group(venueid))
        return _json({"notes": [], "count": 0})  # 合法空态

    stubs = list(_adapter(handler).enumerate_issue(make_openreview_venue(), _issue(2024)))
    assert stubs == []  # 正常完成、无异常


def test_enumerate_version_cached_one_groups_query_per_venueid() -> None:
    venueid = "ICLR.cc/2024/Conference"
    groups_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal groups_calls
        if "/groups" in request.url.path:
            groups_calls += 1
            return _json(_v2_group(venueid))
        return _json({"notes": [_v2_note("p", venueid)], "count": 1})

    a = _adapter(handler)
    list(a.enumerate_issue(make_openreview_venue(), _issue(2024)))
    list(a.enumerate_issue(make_openreview_venue(), _issue(2024)))
    assert groups_calls == 1  # 进程内缓存：每 venueid 一次 groups 查询


def test_enumerate_year_without_group_raises_config() -> None:
    # 2015 届表 None（缺届）——不应被 discover 产出；若直接 enumerate 该年 → CONFIG。
    a = OpenReviewAdapter()
    with pytest.raises(CrawlerError) as exc:
        list(a.enumerate_issue(make_openreview_venue(), _issue(2015)))
    assert exc.value.error_class is ErrorClass.CONFIG


# --- 403 上下文重分类：no_entitlement → auth_expired（§6）--------------------------------


def test_enumerate_403_reclassified_to_auth_expired() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        # notes/groups 一律 403 ChallengeRequiredError（无 token）。
        return _json({"name": "ChallengeRequiredError", "status": 403}, status=403)

    with pytest.raises(CrawlerError) as exc:
        list(_adapter(handler).enumerate_issue(make_openreview_venue(), _issue(2024)))
    assert exc.value.error_class is ErrorClass.AUTH_EXPIRED  # 冻结默认 no_entitlement→重分类
    assert "openreview_challenge" in exc.value.detail


def test_fetch_403_reclassified_to_auth_expired() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, content=b"<html>challenge</html>")

    from paper_crawler.types import AssetPlan

    plan = AssetPlan(kind=AssetKind.PDF, url="https://openreview.net/pdf/x.pdf")
    with pytest.raises(CrawlerError) as exc:
        _adapter(handler).fetch_asset(plan, FakeFetchIO())
    assert exc.value.error_class is ErrorClass.AUTH_EXPIRED


# --- resolve（零网络纯构造）----------------------------------------------------------------


def test_resolve_pdf_path_to_absolute_url() -> None:
    paper = PaperStub(
        title="P",
        identifiers=(("openreview", "f1"),),
        meta=((parse.META_PDF_PATH, "/pdf/" + "a" * 40 + ".pdf"),),
    )
    plans = OpenReviewAdapter().resolve_assets(make_openreview_venue(), paper)
    assert len(plans) == 1
    assert plans[0].kind is AssetKind.PDF
    assert plans[0].url == "https://openreview.net/pdf/" + "a" * 40 + ".pdf"
    assert plans[0].auth_needed is AuthLevel.FREE_ACCOUNT
    assert plans[0].url_strategy is UrlStrategy.DIRECT
    assert plans[0].version is None


def test_resolve_no_pdf_field_yields_zero_plans() -> None:
    # 无 openreview_pdf meta 键（note 无 pdf 字段）→ 0 plan（2013/2014 正文在 arXiv）。
    paper = PaperStub(title="P", identifiers=(("openreview", "f2"),), meta=())
    assert OpenReviewAdapter().resolve_assets(make_openreview_venue(), paper) == []


def test_resolve_si_yields_additional_plan() -> None:
    paper = PaperStub(
        title="P",
        identifiers=(("openreview", "f3"),),
        meta=(
            (parse.META_PDF_PATH, "/pdf/x.pdf"),
            (parse.META_SI_PATH, "/attachment/y.zip"),
        ),
    )
    plans = OpenReviewAdapter().resolve_assets(make_openreview_venue(), paper)
    kinds = {p.kind for p in plans}
    assert kinds == {AssetKind.PDF, AssetKind.SI}


# --- fetch（流式 + gone 嗅探）--------------------------------------------------------------


def test_fetch_pdf_writes_bytes() -> None:
    pdf = b"%PDF-1.7\n" + b"x" * 600

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=pdf)

    from paper_crawler.types import AssetPlan

    plan = AssetPlan(kind=AssetKind.PDF, url="https://openreview.net/pdf/x.pdf")
    io = FakeFetchIO()
    result = _adapter(handler).fetch_asset(plan, io)
    assert result.ok is True
    assert io.data.startswith(b"%PDF-")


def test_fetch_html_page_maps_to_gone() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"<!DOCTYPE html><html>deleted</html>")

    from paper_crawler.types import AssetPlan

    plan = AssetPlan(kind=AssetKind.PDF, url="https://openreview.net/pdf/gone.pdf")
    with pytest.raises(CrawlerError) as exc:
        _adapter(handler).fetch_asset(plan, FakeFetchIO())
    assert exc.value.error_class is ErrorClass.GONE


# --- healthcheck（匿名双端）----------------------------------------------------------------


def test_healthcheck_healthy_when_both_endpoints_reachable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api2.openreview.net":
            return _json(_v2_group("ICLR.cc/2024/Conference"))
        return _json(_v1_group("ICLR.cc/2014/conference"))

    report = _adapter(handler).healthcheck()
    assert report.healthy is True


def test_healthcheck_unhealthy_when_v2_lost_domain() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api2.openreview.net":
            return _json(_v1_group("ICLR.cc/2024/Conference"))  # 丢了 domain
        return _json(_v1_group("ICLR.cc/2014/conference"))

    report = _adapter(handler).healthcheck()
    assert report.healthy is False
    assert "domain" in report.detail


def test_healthcheck_unhealthy_when_endpoint_unreachable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="down")

    report = _adapter(handler).healthcheck()
    assert report.healthy is False


def test_healthcheck_unhealthy_on_parse_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"{not json")

    report = _adapter(handler).healthcheck()
    assert report.healthy is False
    assert "parse" in report.detail.lower()


def test_healthcheck_unhealthy_when_v1_endpoint_missing_group() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api2.openreview.net":
            return _json(_v2_group("ICLR.cc/2024/Conference"))
        return _json({"groups": [{"id": "ICLR.cc/9999/other"}], "count": 1})  # 缺 2014

    report = _adapter(handler).healthcheck()
    assert report.healthy is False
    assert "2014" in report.detail


# --- 注入协议 + UA 兜底 --------------------------------------------------------------------


def test_set_http_client_injects_client() -> None:
    from paper_crawler.adapter import HttpClientConsumer

    a = OpenReviewAdapter()
    assert isinstance(a, HttpClientConsumer)
    client = HttpClient(user_agent=_UA)
    a.set_http_client(client)
    assert a._client() is client  # 注入生效


def test_default_user_agent_uses_env_email(monkeypatch: pytest.MonkeyPatch) -> None:
    from paper_crawler.adapters.openreview import adapter as mod

    monkeypatch.setenv("PAPER_CRAWLER_CONTACT_EMAIL", "me@example.org")
    ua = mod._default_user_agent()
    assert "me@example.org" in ua


def test_default_user_agent_placeholder_when_env_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    from paper_crawler.adapters.openreview import adapter as mod

    monkeypatch.delenv("PAPER_CRAWLER_CONTACT_EMAIL", raising=False)
    ua = mod._default_user_agent()
    assert ".invalid" in ua
