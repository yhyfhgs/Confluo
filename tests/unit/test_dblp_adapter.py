"""`adapters.dblp.adapter.DblpAdapter` 单测（design/adapters/aggregators.md
§1/§3/§4/§5.2）。

覆盖：①adapter 元数据声明（capabilities/default_rate/domains/auth）；
②`discover_timeline`（索引页解析→IssueRef，since 过滤，venue 配置缺陷早失败）；
③`enumerate_issue`（正常路径、字段透传、404 一次性自愈全枚举、非 GONE 错误
原样透传、恶意/合法边界态）；④`HttpClientConsumer`/`CapabilityNotSupported`
两个协议层断言（不声明 RESOLVE/FETCH）。
"""

from __future__ import annotations

import httpx
import pytest

from helpers.dblp_fixtures import fixture_bytes, http_fixture, make_dblp_venue
from paper_crawler.adapter import HttpClientConsumer
from paper_crawler.adapters.dblp.adapter import DblpAdapter
from paper_crawler.errors import CapabilityNotSupported, CrawlerError, ErrorClass
from paper_crawler.http import HttpClient
from paper_crawler.types import AssetKind, AssetPlan, AuthLevel, Capability, IssueRef, PaperStub

_UA = "PaperCrawler/test (personal research; mailto:test@example.com)"
_INDEX_URL = "https://dblp.org/db/conf/icml/"
_XML_URL_TMPL = "https://dblp.org/db/conf/icml/{slug}.xml"


def _client(handler: httpx.MockTransport) -> HttpClient:
    return HttpClient(user_agent=_UA, transport=handler)


def _mock(handler: httpx.MockTransport) -> DblpAdapter:
    return DblpAdapter(http=_client(handler))


# --- ①adapter 元数据声明 ---------------------------------------------------------------------


def test_adapter_metadata() -> None:
    adapter = DblpAdapter()
    assert adapter.adapter_id == "dblp"
    assert adapter.family == "aggregator"
    assert adapter.capabilities == Capability.DISCOVER | Capability.ENUMERATE
    assert Capability.SEARCH not in adapter.capabilities
    assert Capability.RESOLVE not in adapter.capabilities
    assert Capability.FETCH not in adapter.capabilities
    assert adapter.auth_requirement is AuthLevel.NONE
    assert adapter.domains == ("dblp.org",)


def test_default_rate_matches_robots_crawl_delay_4() -> None:
    rate = DblpAdapter.default_rate
    assert rate.requests_per_minute == 15.0  # 60s / 4s
    assert rate.burst == 1
    assert "Crawl-delay: 4" in rate.source_note
    assert rate.source_note != ""


def test_is_http_client_consumer() -> None:
    assert isinstance(DblpAdapter(), HttpClientConsumer)


def test_undeclared_capabilities_raise_capability_not_supported() -> None:
    adapter = DblpAdapter()
    venue = make_dblp_venue()
    paper = PaperStub(title="T", identifiers=(("dblp", "conf/icml/X23"),))
    plan = AssetPlan(kind=AssetKind.PDF, url="https://dblp.org/x")

    with pytest.raises(CapabilityNotSupported):
        adapter.resolve_assets(venue, paper)
    with pytest.raises(CapabilityNotSupported):
        adapter.fetch_asset(plan, io=None)  # type: ignore[arg-type]


def test_set_http_client_overrides_lazily_built_client() -> None:
    adapter = DblpAdapter()
    client = HttpClient(user_agent=_UA)
    adapter.set_http_client(client)
    assert adapter._client() is client  # type: ignore[attr-defined]


def test_lazy_client_builds_and_caches_httpclient_when_http_none() -> None:
    adapter = DblpAdapter()
    client = adapter._client()  # type: ignore[attr-defined]  # 惰性自建，零真实网络
    assert isinstance(client, HttpClient)
    assert adapter._client() is client  # type: ignore[attr-defined]  # 幂等缓存
    client.close()


def test_default_user_agent_uses_env_email(monkeypatch: pytest.MonkeyPatch) -> None:
    from paper_crawler.adapters.dblp import adapter as mod

    monkeypatch.setenv(mod._CONTACT_EMAIL_ENV, "real@lab.edu")
    ua = mod._default_user_agent()
    assert ua.startswith("PaperCrawler/")
    assert ua.endswith("(personal research; mailto:real@lab.edu)")


def test_default_user_agent_falls_back_to_placeholder(monkeypatch: pytest.MonkeyPatch) -> None:
    from paper_crawler.adapters.dblp import adapter as mod

    monkeypatch.delenv(mod._CONTACT_EMAIL_ENV, raising=False)
    ua = mod._default_user_agent()
    assert ua.endswith("(personal research; mailto:anonymous@paper-crawler.invalid)")


# --- ②discover_timeline ----------------------------------------------------------------------


def _index_handler(request: httpx.Request) -> httpx.Response:
    assert str(request.url) == _INDEX_URL
    return httpx.Response(200, content=fixture_bytes("01_conf_index_normal.html"))


def test_discover_timeline_parses_index_page_into_issue_refs() -> None:
    adapter = _mock(httpx.MockTransport(_index_handler))
    venue = make_dblp_venue()
    issues = list(adapter.discover_timeline(venue))
    assert issues == [
        IssueRef(
            venue_id="icml",
            volume=None,
            number=None,
            year=2024,
            label="icml2024",
            pub_date=None,
            paper_count_claimed=None,
        ),
        IssueRef(
            venue_id="icml",
            volume=None,
            number=None,
            year=2023,
            label="icml2023",
            pub_date=None,
            paper_count_claimed=None,
        ),
        IssueRef(
            venue_id="icml",
            volume=None,
            number=None,
            year=2022,
            label="icml2022",
            pub_date=None,
            paper_count_claimed=None,
        ),
        IssueRef(
            venue_id="icml",
            volume=None,
            number=None,
            year=2022,
            label="icml2022w",
            pub_date=None,
            paper_count_claimed=None,
        ),
    ]


def test_discover_timeline_since_filters_by_year_lower_bound() -> None:
    adapter = _mock(httpx.MockTransport(_index_handler))
    issues = list(adapter.discover_timeline(make_dblp_venue(), since="2023-01-01"))
    assert {issue.year for issue in issues} == {2023, 2024}


def test_discover_timeline_empty_index_is_legal_empty() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=fixture_bytes("03_conf_index_empty.html"))

    adapter = _mock(httpx.MockTransport(handler))
    assert list(adapter.discover_timeline(make_dblp_venue())) == []


def test_discover_timeline_missing_dblp_key_raises_config() -> None:
    adapter = DblpAdapter()
    venue = make_dblp_venue()
    venue = venue.model_copy(update={"identifiers": {}})
    with pytest.raises(CrawlerError) as exc_info:
        list(adapter.discover_timeline(venue))
    assert exc_info.value.error_class is ErrorClass.CONFIG


def test_discover_timeline_dblp_key_without_conf_prefix_raises_config() -> None:
    adapter = DblpAdapter()
    venue = make_dblp_venue().model_copy(update={"identifiers": {"dblp_key": "icml"}})
    with pytest.raises(CrawlerError) as exc_info:
        list(adapter.discover_timeline(venue))
    assert exc_info.value.error_class is ErrorClass.CONFIG


def test_discover_timeline_empty_acr_after_prefix_raises_config() -> None:
    adapter = DblpAdapter()
    venue = make_dblp_venue().model_copy(update={"identifiers": {"dblp_key": "conf/"}})
    with pytest.raises(CrawlerError) as exc_info:
        list(adapter.discover_timeline(venue))
    assert exc_info.value.error_class is ErrorClass.CONFIG


# --- ③enumerate_issue：正常路径 --------------------------------------------------------------

_ISSUE_2023 = IssueRef(venue_id="icml", year=2023, label="icml2023")


def _volume_handler(request: httpx.Request) -> httpx.Response:
    assert str(request.url) == _XML_URL_TMPL.format(slug="icml2023")
    # 生产实际 schema（bht/dblpcites/r 包装，2026-07-23 审查真实交叉验证核实）
    # ——不是批量导出 dblp.xml.gz 的平铺 schema。见 fixture 头注释的抓取出处。
    return httpx.Response(200, content=fixture_bytes("10_volume_xml_bht_schema_normal.xml"))


def test_enumerate_issue_normal_path_yields_expected_papers() -> None:
    adapter = _mock(httpx.MockTransport(_volume_handler))
    stubs = list(adapter.enumerate_issue(make_dblp_venue(), _ISSUE_2023))
    assert len(stubs) == 5
    keys = [dict(stub.meta) | {"__id__": stub.identifiers} for stub in stubs]
    assert keys[0]["__id__"] == (("dblp", "conf/icml/AamandACINS23"),)
    # 真实内容保真度：真实标题（非占位符）经完整 enumerate 链路正确透出。
    assert stubs[0].title == "Data Structures for Density Estimation."
    doi_ids = [i for stub in stubs for i in stub.identifiers if i[0] == "doi"]
    assert ("doi", "10.1007/978-3-030-99999-9_1") in doi_ids
    assert ("doi", "10.1007/978-3-030-99999-9_2") in doi_ids
    # 护栏：容器 DOI 绝不作为任何一篇论文的 identifier 出现（"container_dois 恒
    # 空集自证通过"复发防护——本行断言的失败模式恰恰就是那种回归）。
    assert ("doi", "10.1007/978-3-030-99999-9") not in doi_ids


def test_enumerate_issue_against_full_real_1828_record_capture() -> None:
    """未裁剪真实响应（1828 条）端到端跑通 `enumerate_issue`——2026-07-23 审查
    阻断项的直接回归证据：修复前，`root.tag != "dblp"` 门禁会让*任何*真实卷
    立即 `parse` 失败，本测试若通过即证明该阻断项对 `enumerate_issue`（不仅
    healthcheck）确实已修复。"""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=fixture_bytes("11_volume_xml_bht_schema_full_real_icml2023.xml")
        )

    adapter = _mock(httpx.MockTransport(handler))
    stubs = list(adapter.enumerate_issue(make_dblp_venue(), _ISSUE_2023))
    assert len(stubs) == 1828
    assert stubs[0].identifiers[0] == ("dblp", "conf/icml/AamandACINS23")
    assert stubs[-1].identifiers[0] == ("dblp", "conf/icml/ZouCLG23")
    # 真实 ICML/PMLR 数据全程无 DOI-form ee；容器同样无 DOI——1828 篇论文里
    # 不应有任何一个 doi identifier（真实规模下的"零假阳性"证据）。
    assert not [i for stub in stubs for i in stub.identifiers if i[0] == "doi"]


def test_enumerate_issue_missing_label_raises_config() -> None:
    adapter = DblpAdapter()
    bad_issue = IssueRef(venue_id="icml", year=2023, label=None)
    with pytest.raises(CrawlerError) as exc_info:
        list(adapter.enumerate_issue(make_dblp_venue(), bad_issue))
    assert exc_info.value.error_class is ErrorClass.CONFIG


def test_enumerate_issue_missing_year_raises_config() -> None:
    adapter = DblpAdapter()
    bad_issue = IssueRef(venue_id="icml", year=None, label="icml2023")
    with pytest.raises(CrawlerError) as exc_info:
        list(adapter.enumerate_issue(make_dblp_venue(), bad_issue))
    assert exc_info.value.error_class is ErrorClass.CONFIG


def test_enumerate_issue_empty_volume_yields_no_papers() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=fixture_bytes("05_volume_xml_empty.xml"))

    adapter = _mock(httpx.MockTransport(handler))
    assert list(adapter.enumerate_issue(make_dblp_venue(), _ISSUE_2023)) == []


def test_enumerate_issue_logs_skipped_missing_title_records_without_failing() -> None:
    xml = (
        b"<dblp>"
        b'<inproceedings key="conf/icml/NoTitle23"></inproceedings>'
        b'<inproceedings key="conf/icml/HasTitle23"><title>Has Title.</title></inproceedings>'
        b"</dblp>"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=xml)

    adapter = _mock(httpx.MockTransport(handler))
    stubs = list(adapter.enumerate_issue(make_dblp_venue(), _ISSUE_2023))
    assert [s.identifiers[0][1] for s in stubs] == ["conf/icml/HasTitle23"]


def test_enumerate_issue_malformed_xml_propagates_parse_uncaught() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=fixture_bytes("06_volume_xml_malformed.xml"))

    adapter = _mock(httpx.MockTransport(handler))
    with pytest.raises(CrawlerError) as exc_info:
        list(adapter.enumerate_issue(make_dblp_venue(), _ISSUE_2023))
    assert exc_info.value.error_class is ErrorClass.PARSE


# --- ③enumerate_issue：非 GONE 错误原样透传（不触发自愈）------------------------------------


def test_enumerate_issue_rate_limited_propagates_unmodified() -> None:
    status, headers, body = http_fixture("08_ratelimit_429_with_retry_after.http")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, headers=headers, content=body)

    adapter = _mock(httpx.MockTransport(handler))
    with pytest.raises(CrawlerError) as exc_info:
        list(adapter.enumerate_issue(make_dblp_venue(), _ISSUE_2023))
    assert exc_info.value.error_class is ErrorClass.RATE_LIMITED


def test_enumerate_issue_server_error_propagates_unmodified() -> None:
    status, headers, body = http_fixture("09_server_error_500.http")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, headers=headers, content=body)

    adapter = _mock(httpx.MockTransport(handler))
    with pytest.raises(CrawlerError) as exc_info:
        list(adapter.enumerate_issue(make_dblp_venue(), _ISSUE_2023))
    assert exc_info.value.error_class is ErrorClass.TRANSIENT


# --- ③enumerate_issue：404 一次性自愈（§5.2 错误映射表）--------------------------------------


def test_enumerate_issue_404_self_heals_via_index_rediscovery() -> None:
    """卷 key 404（`issue.label` 陈旧/错误）→ 回索引页重发现该年真实 slug → 重试
    一次成功。三次请求：陈旧 slug 404 → 索引页 → 正确 slug 成功。
    """
    calls: list[str] = []
    status_404, headers_404, body_404 = http_fixture("07_volume_404.http")

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        calls.append(url)
        if url == _XML_URL_TMPL.format(slug="icml2023-stale"):
            return httpx.Response(status_404, headers=headers_404, content=body_404)
        if url == _INDEX_URL:
            return httpx.Response(200, content=fixture_bytes("01_conf_index_normal.html"))
        if url == _XML_URL_TMPL.format(slug="icml2023"):
            return httpx.Response(200, content=fixture_bytes("10_volume_xml_bht_schema_normal.xml"))
        raise AssertionError(f"unexpected request: {url}")

    adapter = _mock(httpx.MockTransport(handler))
    stale_issue = IssueRef(venue_id="icml", year=2023, label="icml2023-stale")
    stubs = list(adapter.enumerate_issue(make_dblp_venue(), stale_issue))
    assert len(stubs) == 5
    assert calls == [
        _XML_URL_TMPL.format(slug="icml2023-stale"),
        _INDEX_URL,
        _XML_URL_TMPL.format(slug="icml2023"),
    ]


def test_enumerate_issue_404_recovery_finds_no_candidate_for_year_raises_parse() -> None:
    status_404, headers_404, body_404 = http_fixture("07_volume_404.http")

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == _INDEX_URL:
            return httpx.Response(200, content=fixture_bytes("01_conf_index_normal.html"))
        return httpx.Response(status_404, headers=headers_404, content=body_404)

    adapter = _mock(httpx.MockTransport(handler))
    # 索引页只覆盖 2022-2024；用一个索引页里没有的年份触发"重发现也找不到该年份"。
    no_such_year_issue = IssueRef(venue_id="icml", year=1999, label="icml1999")
    with pytest.raises(CrawlerError) as exc_info:
        list(adapter.enumerate_issue(make_dblp_venue(), no_such_year_issue))
    assert exc_info.value.error_class is ErrorClass.PARSE


def test_enumerate_issue_404_recovery_index_fetch_itself_fails_raises_parse() -> None:
    status_500, headers_500, body_500 = http_fixture("09_server_error_500.http")
    status_404, headers_404, body_404 = http_fixture("07_volume_404.http")

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == _INDEX_URL:
            return httpx.Response(status_500, headers=headers_500, content=body_500)
        return httpx.Response(status_404, headers=headers_404, content=body_404)

    adapter = _mock(httpx.MockTransport(handler))
    with pytest.raises(CrawlerError) as exc_info:
        list(adapter.enumerate_issue(make_dblp_venue(), _ISSUE_2023))
    assert exc_info.value.error_class is ErrorClass.PARSE


def test_enumerate_issue_404_recovery_candidate_also_fails_raises_parse() -> None:
    """重发现找到唯一候选 slug（与陈旧 label 不同），但候选本身也 404（候选耗尽）
    → 仍判 parse。stale label 必须与索引页真实 slug 不同——否则会被
    `candidates` 的自我排除过滤掉，误落回"无候选"分支而非本分支。"""
    status_404, headers_404, body_404 = http_fixture("07_volume_404.http")

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == _INDEX_URL:
            return httpx.Response(200, content=fixture_bytes("01_conf_index_normal.html"))
        return httpx.Response(status_404, headers=headers_404, content=body_404)

    adapter = _mock(httpx.MockTransport(handler))
    stale_issue = IssueRef(venue_id="icml", year=2023, label="icml2023-totally-wrong")
    with pytest.raises(CrawlerError) as exc_info:
        list(adapter.enumerate_issue(make_dblp_venue(), stale_issue))
    assert exc_info.value.error_class is ErrorClass.PARSE


def test_enumerate_issue_404_recovery_tries_next_candidate_after_first_also_fails() -> None:
    """重发现同一年份有多个候选（索引页 2022 年恰有 icml2022/icml2022w 两条）时逐个
    重试：首个候选仍失败不应立即放弃，须继续尝试下一个候选，成功即返回——证明
    "候选耗尽才失败"不是唯一路径，`continue` 确实把控制权交回循环下一轮。
    """
    status_404, headers_404, body_404 = http_fixture("07_volume_404.http")

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == _INDEX_URL:
            return httpx.Response(200, content=fixture_bytes("01_conf_index_normal.html"))
        if url == _XML_URL_TMPL.format(slug="icml2022"):
            return httpx.Response(status_404, headers=headers_404, content=body_404)
        if url == _XML_URL_TMPL.format(slug="icml2022w"):
            return httpx.Response(200, content=fixture_bytes("10_volume_xml_bht_schema_normal.xml"))
        return httpx.Response(status_404, headers=headers_404, content=body_404)

    adapter = _mock(httpx.MockTransport(handler))
    stale_issue = IssueRef(venue_id="icml", year=2022, label="icml2022-stale")
    stubs = list(adapter.enumerate_issue(make_dblp_venue(), stale_issue))
    assert len(stubs) == 5
