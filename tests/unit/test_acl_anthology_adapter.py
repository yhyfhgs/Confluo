"""acl_anthology/adapter.py 单测（design/adapters/acl-anthology.md §4/§6; T1/T3 网络编排层）。

`httpx.MockTransport` 全量替身，零真实网络。覆盖 design §7 T3 全部 error_class
（⑤畸形→parse ⑥raw 404→legal-empty ⑦PDF 404→gone ⑧5xx→transient ⑨429→rate_limited
⑩github 403→rate_limited 域级重分类 ⑪400→config）+ discover 的 24h 缓存语义 +
enumerate 的清单热/冷两路径（热：零网络存在性短路；冷：新式→旧式构造探测）。
"""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from helpers import make_acl_anthology_venue
from helpers.acl_anthology_fixtures import fixture_bytes, http_fixture
from paper_crawler.adapters.acl_anthology.adapter import AclAnthologyAdapter
from paper_crawler.errors import CrawlerError, ErrorClass
from paper_crawler.http import HttpClient
from paper_crawler.types import AssetKind, IssueRef, PaperStub

_UA = "PaperCrawler/test (personal research; mailto:test@example.com)"
_TREE_BODY = fixture_bytes("10_github_tree_sample.json")
_SCHEMA_BODY = (
    b"Collection = element collection { attribute id { xsd:string } }\n"
    b"Paper = element paper { attribute id { xsd:positiveInteger } }\n"
)
_VENUE = make_acl_anthology_venue()


def _handler(
    *,
    tree_response: httpx.Response | None = None,
    schema_response: httpx.Response | None = None,
    homepage_response: httpx.Response | None = None,
    raw_files: dict[str, httpx.Response] | None = None,
    pdf_response: httpx.Response | None = None,
    request_log: list[str] | None = None,
) -> Callable[[httpx.Request], httpx.Response]:
    """通用调度：按 host/path 分流到各响应生成器；`request_log` 记录每次请求 URL。"""
    raw_files = raw_files or {}

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if request_log is not None:
            request_log.append(url)
        if request.url.host == "api.github.com":
            if tree_response is not None:
                return tree_response
            return httpx.Response(200, content=_TREE_BODY)
        if url.endswith("/data/xml/schema.rnc"):
            if schema_response is not None:
                return schema_response
            return httpx.Response(200, content=_SCHEMA_BODY)
        if request.url.host == "raw.githubusercontent.com":
            filename = url.rsplit("/", 1)[-1]
            if filename in raw_files:
                return raw_files[filename]
            return httpx.Response(404, content=b"synthetic 404")
        if url.rstrip("/") == "https://aclanthology.org":
            if homepage_response is not None:
                return homepage_response
            return httpx.Response(200, content=b"<html>home</html>")
        if url.endswith(".pdf"):
            if pdf_response is not None:
                return pdf_response
            return httpx.Response(200, content=b"%PDF-1.4\nsynthetic\n%%EOF\n")
        if "/attachments/" in url:
            return httpx.Response(200, content=b"synthetic attachment bytes")
        return httpx.Response(404, content=b"unhandled synthetic 404")

    return handler


def _adapter(
    handler: Callable[[httpx.Request], httpx.Response], *, clock: Callable[[], float] | None = None
) -> AclAnthologyAdapter:
    client = HttpClient(user_agent=_UA, transport=httpx.MockTransport(handler))
    if clock is not None:
        return AclAnthologyAdapter(http=client, clock=clock)
    return AclAnthologyAdapter(http=client)


def _raw_ok(name: str) -> httpx.Response:
    return httpx.Response(200, content=fixture_bytes(name))


def _http_response(name: str) -> httpx.Response:
    status, headers, body = http_fixture(name)
    return httpx.Response(status, headers=headers, content=body)


# --- discover_timeline：git-tree 驱动的候选年份 + 字段分解 ----------------------------------------


def test_discover_timeline_yields_issue_refs_for_candidate_years() -> None:
    adapter = _adapter(_handler())
    issues = list(adapter.discover_timeline(_VENUE))
    years = {i.year for i in issues}
    assert {2007, 2018, 2019, 2022, 2023} <= years
    sample = next(i for i in issues if i.year == 2023)
    assert sample == IssueRef(
        venue_id="emnlp",
        volume=None,
        number=None,
        year=2023,
        label="2023",
        pub_date=None,
        paper_count_claimed=None,
    )


def test_discover_timeline_since_filters_lower_years() -> None:
    adapter = _adapter(_handler())
    issues = list(adapter.discover_timeline(_VENUE, since="2020-01"))
    assert all(i.year is not None and i.year >= 2020 for i in issues)
    assert 2023 in {i.year for i in issues}
    assert 2019 not in {i.year for i in issues}


def test_discover_timeline_caches_within_ttl_using_injected_clock() -> None:
    calls: list[str] = []
    time_box = [1000.0]
    adapter = _adapter(_handler(request_log=calls), clock=lambda: time_box[0])

    list(adapter.discover_timeline(_VENUE))
    github_calls_after_first = sum(1 for u in calls if "api.github.com" in u)
    assert github_calls_after_first == 1

    time_box[0] += 3600.0  # 1h 后仍在 24h TTL 内
    list(adapter.discover_timeline(_VENUE))
    assert sum(1 for u in calls if "api.github.com" in u) == 1  # 未触发第二次拉取


def test_discover_timeline_refetches_tree_after_ttl_expires() -> None:
    calls: list[str] = []
    time_box = [1000.0]
    adapter = _adapter(_handler(request_log=calls), clock=lambda: time_box[0])

    list(adapter.discover_timeline(_VENUE))
    time_box[0] += 24 * 3600.0 + 1.0  # 超过 24h TTL
    list(adapter.discover_timeline(_VENUE))
    assert sum(1 for u in calls if "api.github.com" in u) == 2


def test_discover_timeline_github_403_reclassified_rate_limited() -> None:
    adapter = _adapter(_handler(tree_response=_http_response("08_github_403.http")))
    with pytest.raises(CrawlerError) as exc:
        list(adapter.discover_timeline(_VENUE))
    assert exc.value.error_class is ErrorClass.RATE_LIMITED
    assert "github_403_ratelimit" in exc.value.detail


def test_discover_timeline_truncated_tree_raises_parse() -> None:
    body = b'{"truncated": true, "tree": []}'
    adapter = _adapter(_handler(tree_response=httpx.Response(200, content=body)))
    with pytest.raises(CrawlerError) as exc:
        list(adapter.discover_timeline(_VENUE))
    assert exc.value.error_class is ErrorClass.PARSE


# --- enumerate_issue：CONFIG 前置校验 --------------------------------------------------------


def test_enumerate_issue_requires_year() -> None:
    adapter = _adapter(_handler())
    with pytest.raises(CrawlerError) as exc:
        list(adapter.enumerate_issue(_VENUE, IssueRef(venue_id="emnlp", label="?")))
    assert exc.value.error_class is ErrorClass.CONFIG


# --- enumerate_issue：热清单路径（discover 已缓存）——零网络存在性短路 -----------------------------


def test_enumerate_warm_cache_short_circuits_nonexistent_year_without_network() -> None:
    calls: list[str] = []
    adapter = _adapter(_handler(request_log=calls))
    list(adapter.discover_timeline(_VENUE))  # 预热清单缓存
    calls.clear()

    stubs = list(
        adapter.enumerate_issue(_VENUE, IssueRef(venue_id="emnlp", year=2099, label="2099"))
    )
    assert stubs == []
    assert calls == []  # 清单已证实两代候选、findings 均不存在——零网络


def test_enumerate_warm_cache_full_join_matches_anchor_shape() -> None:
    adapter = _adapter(
        _handler(
            raw_files={
                "2023.emnlp.xml": _raw_ok("01_emnlp_main_2023_excerpt.xml"),
                "2023.findings.xml": _raw_ok("02_findings_2023_excerpt.xml"),
            }
        )
    )
    list(adapter.discover_timeline(_VENUE))  # 预热清单缓存

    stubs = list(
        adapter.enumerate_issue(_VENUE, IssueRef(venue_id="emnlp", year=2023, label="2023"))
    )
    tracks = [dict(s.meta)["track"] for s in stubs]
    assert tracks.count("main") == 2
    assert tracks.count("tutorial") == 1
    assert tracks.count("demo") == 1
    assert tracks.count("industry") == 1
    assert tracks.count("findings") == 2  # 仅 emnlp volume（join 过滤掉 acl volume）
    assert len(stubs) == 7
    for stub in stubs:
        assert isinstance(stub, PaperStub)
        assert len(stub.identifiers) >= 1


# --- enumerate_issue：冷清单路径——新式→旧式构造探测 ----------------------------------------------


def test_enumerate_cold_cache_new_style_success_no_probing_needed() -> None:
    calls: list[str] = []
    adapter = _adapter(
        _handler(
            request_log=calls,
            raw_files={"2023.emnlp.xml": _raw_ok("01_emnlp_main_2023_excerpt.xml")},
        )
    )
    stubs = list(
        adapter.enumerate_issue(_VENUE, IssueRef(venue_id="emnlp", year=2023, label="2023"))
    )
    assert len(stubs) == 5  # 主文件 main(2)+tutorial(1)+demo(1)+industry(1)，无 findings 文件
    raw_calls = [u for u in calls if "raw.githubusercontent.com" in u]
    # 新式一击即中：仅 2023.emnlp.xml（成功） + 2023.findings.xml（探测 404）各一次。
    assert sum(1 for u in raw_calls if u.endswith("2023.emnlp.xml")) == 1
    assert not any("D23" in u for u in raw_calls)  # 未尝试旧式候选


def test_enumerate_cold_cache_falls_back_to_old_style_after_new_style_404() -> None:
    adapter = _adapter(_handler(raw_files={"D19.xml": _raw_ok("03_d19_legacy_excerpt.xml")}))
    stubs = list(
        adapter.enumerate_issue(_VENUE, IssueRef(venue_id="emnlp", year=2019, label="2019"))
    )
    assert len(stubs) == 4  # D19 excerpt 的 4 篇（无 2019.findings.xml → 无追加）
    assert stubs[0].identifiers[0] == ("anthology", "D19-1001")


def test_enumerate_cold_cache_both_styles_404_is_legal_empty_not_an_error() -> None:
    adapter = _adapter(_handler())  # raw_files 全空 → 一切 404
    stubs = list(
        adapter.enumerate_issue(_VENUE, IssueRef(venue_id="emnlp", year=2099, label="2099"))
    )
    assert stubs == []  # legal-empty：非错误，正常完成


def test_enumerate_findings_file_missing_yields_only_primary_papers() -> None:
    adapter = _adapter(
        _handler(raw_files={"2023.emnlp.xml": _raw_ok("01_emnlp_main_2023_excerpt.xml")})
    )
    stubs = list(
        adapter.enumerate_issue(_VENUE, IssueRef(venue_id="emnlp", year=2023, label="2023"))
    )
    assert all(dict(s.meta)["track"] != "findings" for s in stubs)
    assert len(stubs) == 5


# --- enumerate_issue：T3 error_class 矩阵（主文件 GET 层面）--------------------------------------


def test_enumerate_malformed_primary_xml_raises_parse() -> None:
    adapter = _adapter(_handler(raw_files={"2023.emnlp.xml": _raw_ok("04_malformed.xml")}))
    with pytest.raises(CrawlerError) as exc:
        list(adapter.enumerate_issue(_VENUE, IssueRef(venue_id="emnlp", year=2023, label="2023")))
    assert exc.value.error_class is ErrorClass.PARSE


def test_enumerate_5xx_raises_transient() -> None:
    adapter = _adapter(_handler(raw_files={"2023.emnlp.xml": _http_response("06_5xx.http")}))
    with pytest.raises(CrawlerError) as exc:
        list(adapter.enumerate_issue(_VENUE, IssueRef(venue_id="emnlp", year=2023, label="2023")))
    assert exc.value.error_class is ErrorClass.TRANSIENT


def test_enumerate_429_raises_rate_limited() -> None:
    adapter = _adapter(
        _handler(raw_files={"2023.emnlp.xml": _http_response("07_429_ratelimit.http")})
    )
    with pytest.raises(CrawlerError) as exc:
        list(adapter.enumerate_issue(_VENUE, IssueRef(venue_id="emnlp", year=2023, label="2023")))
    assert exc.value.error_class is ErrorClass.RATE_LIMITED
    assert "retry_after_s=30" in exc.value.detail


def test_enumerate_400_raises_config() -> None:
    adapter = _adapter(
        _handler(raw_files={"2023.emnlp.xml": _http_response("09_400_bad_request.http")})
    )
    with pytest.raises(CrawlerError) as exc:
        list(adapter.enumerate_issue(_VENUE, IssueRef(venue_id="emnlp", year=2023, label="2023")))
    assert exc.value.error_class is ErrorClass.CONFIG


# --- resolve_assets：纯构造零网络 ------------------------------------------------------------


def test_resolve_assets_pdf_plan_url() -> None:
    adapter = _adapter(_handler())
    paper = PaperStub(title="T", identifiers=(("anthology", "2023.emnlp-main.1"),))
    plans = adapter.resolve_assets(_VENUE, paper)
    assert len(plans) == 1
    plan = plans[0]
    assert plan.kind is AssetKind.PDF
    assert plan.url == "https://aclanthology.org/2023.emnlp-main.1.pdf"
    assert plan.auth_needed.value == "none"


def test_resolve_assets_produces_si_plan_per_attachment() -> None:
    adapter = _adapter(_handler())
    paper = PaperStub(
        title="T",
        identifiers=(("anthology", "D19-1001"),),
        meta=(
            ("acl_anthology_attachment", "D19-1001.Attachment.pdf"),
            ("acl_anthology_attachment", "D19-1001.Extra.zip"),
        ),
    )
    plans = adapter.resolve_assets(_VENUE, paper)
    assert len(plans) == 3  # 1 pdf + 2 si
    si_urls = {p.url for p in plans if p.kind is AssetKind.SI}
    assert si_urls == {
        "https://aclanthology.org/attachments/D19-1001.Attachment.pdf",
        "https://aclanthology.org/attachments/D19-1001.Extra.zip",
    }


def test_resolve_assets_without_anthology_identifier_raises_config() -> None:
    adapter = _adapter(_handler())
    paper = PaperStub(title="T", identifiers=(("doi", "10.1/x"),))
    with pytest.raises(CrawlerError) as exc:
        adapter.resolve_assets(_VENUE, paper)
    assert exc.value.error_class is ErrorClass.CONFIG


# --- fetch_asset --------------------------------------------------------------------------


def test_fetch_asset_streams_pdf_bytes() -> None:
    from helpers import FakeFetchIO

    adapter = _adapter(_handler(pdf_response=httpx.Response(200, content=b"%PDF-1.4\nabc\n")))
    paper = PaperStub(title="T", identifiers=(("anthology", "2023.emnlp-main.1"),))
    plan = adapter.resolve_assets(_VENUE, paper)[0]
    io = FakeFetchIO()
    result = adapter.fetch_asset(plan, io)
    assert result.ok is True
    assert io.data.startswith(b"%PDF")


def test_fetch_asset_404_propagates_gone() -> None:
    from helpers import FakeFetchIO

    adapter = _adapter(_handler(pdf_response=httpx.Response(404, content=b"not found")))
    paper = PaperStub(title="T", identifiers=(("anthology", "2023.emnlp-main.999"),))
    plan = adapter.resolve_assets(_VENUE, paper)[0]
    with pytest.raises(CrawlerError) as exc:
        adapter.fetch_asset(plan, FakeFetchIO())
    assert exc.value.error_class is ErrorClass.GONE


# --- healthcheck ----------------------------------------------------------------------------


def test_healthcheck_healthy_when_schema_and_homepage_reachable() -> None:
    adapter = _adapter(_handler())
    report = adapter.healthcheck()
    assert report.healthy is True


def test_healthcheck_unhealthy_when_schema_unreachable() -> None:
    adapter = _adapter(_handler(schema_response=_http_response("06_5xx.http")))
    report = adapter.healthcheck()
    assert report.healthy is False
    assert "schema.rnc" in report.detail


def test_healthcheck_unhealthy_on_schema_drift() -> None:
    adapter = _adapter(_handler(schema_response=httpx.Response(200, content=b"nothing useful")))
    report = adapter.healthcheck()
    assert report.healthy is False
    assert "drift" in report.detail or "wrong ref" in report.detail


def test_healthcheck_unhealthy_when_homepage_unreachable() -> None:
    adapter = _adapter(_handler(homepage_response=_http_response("06_5xx.http")))
    report = adapter.healthcheck()
    assert report.healthy is False
    assert "aclanthology.org" in report.detail


# --- 覆盖补强：UA 惰性自建 / 非 403 错误透传 / findings 无目标 volume / 无 legacy prefix ----------


def test_default_user_agent_uses_env_email(monkeypatch: pytest.MonkeyPatch) -> None:
    from paper_crawler.adapters.acl_anthology import adapter as mod

    monkeypatch.setenv(mod._CONTACT_EMAIL_ENV, "real@lab.edu")
    ua = mod._default_user_agent()
    assert ua.startswith("PaperCrawler/")
    assert ua.endswith("(personal research; mailto:real@lab.edu)")


def test_default_user_agent_falls_back_to_placeholder(monkeypatch: pytest.MonkeyPatch) -> None:
    from paper_crawler.adapters.acl_anthology import adapter as mod

    monkeypatch.delenv(mod._CONTACT_EMAIL_ENV, raising=False)
    ua = mod._default_user_agent()
    assert ua.endswith("(personal research; mailto:anonymous@paper-crawler.invalid)")


def test_lazy_client_builds_and_caches_httpclient_when_http_none() -> None:
    adapter = AclAnthologyAdapter()
    client = adapter._client()  # 惰性自建（仅构造，不发请求 → 零真实网络）
    assert isinstance(client, HttpClient)
    assert adapter._client() is client  # 幂等缓存
    client.close()


def test_discover_timeline_non_403_github_error_passes_through_unchanged() -> None:
    """`_reclassify_github_403` 只重分类 403；5xx 等其余错误原样透传（覆盖 fallthrough 分支）。"""
    adapter = _adapter(_handler(tree_response=_http_response("06_5xx.http")))
    with pytest.raises(CrawlerError) as exc:
        list(adapter.discover_timeline(_VENUE))
    assert exc.value.error_class is ErrorClass.TRANSIENT


def test_enumerate_findings_file_present_but_lacks_target_volume_yields_primary_only() -> None:
    """Findings 文件确实存在（该年有 Findings），但恰巧不含目标 venue 的 volume——
    产 primary 论文、findings 部分静默产出 0 篇（非错误，同 legal-empty 精神）。
    """
    findings_without_emnlp = (
        b"<collection id='2023.findings'><volume id='acl' type='proceedings'>"
        b"<meta><year>2023</year><venue>findings</venue></meta>"
        b"<paper id='1'><title>Findings Of ACL Only</title><bibkey>x-2023</bibkey>"
        b"<url hash='aaaaaaaa'>2023.findings-acl.1</url></paper>"
        b"</volume></collection>"
    )
    adapter = _adapter(
        _handler(
            raw_files={
                "2023.emnlp.xml": _raw_ok("01_emnlp_main_2023_excerpt.xml"),
                "2023.findings.xml": httpx.Response(200, content=findings_without_emnlp),
            }
        )
    )
    stubs = list(
        adapter.enumerate_issue(_VENUE, IssueRef(venue_id="emnlp", year=2023, label="2023"))
    )
    assert len(stubs) == 5  # 仅主文件的 5 篇；findings 文件虽 200 但无 emnlp volume
    assert all(dict(s.meta)["track"] != "findings" for s in stubs)


def test_enumerate_cold_cache_no_legacy_prefix_skips_old_style_probe_entirely() -> None:
    """venue 未声明 `anthology_legacy_prefix`：新式 404 后不会尝试构造任何旧式候选，
    直接 legal-empty（覆盖 `_resolve_and_fetch_primary` 的 `prefix is None` 分支）。
    """
    venue = make_acl_anthology_venue(anthology_legacy_prefix=None)
    calls: list[str] = []
    adapter = _adapter(_handler(request_log=calls))  # raw_files 全空 → 新式候选 404
    issue = IssueRef(venue_id="emnlp", year=2019, label="2019")
    stubs = list(adapter.enumerate_issue(venue, issue))
    assert stubs == []
    raw_calls = [u for u in calls if "raw.githubusercontent.com" in u]
    assert len(raw_calls) == 2  # 仅新式主文件 + findings 各探测一次，无旧式候选
