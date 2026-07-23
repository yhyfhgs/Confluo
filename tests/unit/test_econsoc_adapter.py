"""econsoc/adapter.py 单测（MockTransport 零真实网络；design/adapters/econsoc.md §4/§5/§7）。

覆盖：discover（volume_map→IssueRef + since + ECMA 无 volume_map→CONFIG）；enumerate
（DOI 后缀刊别 membership + dc:date 年 partition + 当前刊回看窗 from= + 墓碑跳过）；resolve
（TE/QE 落地页抽 galley；ECMA 分段三分流 current/backfile/pre_doi + 乐观默认；CF 质询→
Challenged；无 galley→0 资产）；fetch（%PDF 透传 / HTML CF 质询→CHALLENGE / HTML 撤稿→GONE）；
healthcheck（Identify repositoryName）；元数据（capabilities/family/rate/domains）。
"""

from __future__ import annotations

import httpx
import pytest

from helpers import FakeFetchIO, make_econsoc_ecma_venue, make_econsoc_teqe_venue
from helpers.econsoc_fixtures import fixture_bytes
from paper_crawler.adapters.econsoc.adapter import EconsocAdapter
from paper_crawler.errors import Challenged, CrawlerError, ErrorClass
from paper_crawler.http import HttpClient
from paper_crawler.types import AssetKind, AuthLevel, Capability, IssueRef, PaperStub

_UA = "PaperCrawler/test (personal research; mailto:test@example.com)"
_PDF = b"%PDF-1.7\nsynthetic econsoc pdf\n%%EOF\n"


def _adapter(handler: object) -> EconsocAdapter:
    client = HttpClient(user_agent=_UA, transport=httpx.MockTransport(handler))  # type: ignore[arg-type]
    return EconsocAdapter(http=client)


def _te_issue(year: int, volume: str) -> IssueRef:
    return IssueRef(venue_id="te", volume=volume, number=None, year=year, label=f"te-{year}")


def _stub(doi: str, meta: tuple[tuple[str, str], ...] = ()) -> PaperStub:
    return PaperStub(title="X", identifiers=(("doi", doi),), meta=meta)


# --- 元数据 -----------------------------------------------------------------------------------


def test_adapter_metadata() -> None:
    a = EconsocAdapter()
    assert a.adapter_id == "econsoc"
    assert a.family == "open_access"
    assert a.capabilities == (
        Capability.DISCOVER | Capability.ENUMERATE | Capability.RESOLVE | Capability.FETCH
    )
    assert a.auth_requirement is AuthLevel.NONE
    assert a.default_rate.source_note  # 非空出处（契约要求）
    assert a.default_rate.requests_per_minute <= 20.0  # ≥3s 硬下限（20rpm=3s）
    assert a.domains[0] == "www.econometricsociety.org"
    assert "econtheory.org" in a.domains  # OAI 域一并声明（route_for alias 到主域桶）
    assert a.resolve_offline is False  # resolve 网络绑定（GET 落地页抽 galley）


# --- discover -------------------------------------------------------------------------------


def test_discover_te_yields_per_year_issues() -> None:
    issues = list(EconsocAdapter().discover_timeline(make_econsoc_teqe_venue("te")))
    assert {(i.year, i.volume) for i in issues} == {(2006, "1"), (2024, "20")}
    for i in issues:
        assert i.venue_id == "te"
        assert i.label == f"te-{i.year}"


def test_discover_since_narrows_start() -> None:
    issues = list(EconsocAdapter().discover_timeline(make_econsoc_teqe_venue("te"), since="2020"))
    assert {i.year for i in issues} == {2024}


def test_discover_ecma_without_volume_map_is_config_error() -> None:
    # ECMA venue 无 volume_map（枚举委 crossref）→ 误调 discover 响亮停机（CONFIG）。
    with pytest.raises(CrawlerError) as exc:
        list(EconsocAdapter().discover_timeline(make_econsoc_ecma_venue()))
    assert exc.value.error_class is ErrorClass.CONFIG


# --- enumerate（DOI 后缀 membership + dc:date 年 partition + 回看窗）--------------------------


def _oai_handler(seen: list[str] | None = None) -> object:
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(str(request.url))
        if "resumptionToken" in request.url.params:
            return httpx.Response(200, content=fixture_bytes("02_oai_listrecords_page2.xml"))
        return httpx.Response(200, content=fixture_bytes("01_oai_listrecords_page1.xml"))

    return handler


def test_enumerate_current_year_keeps_only_te_2024_records() -> None:
    seen: list[str] = []
    papers = list(
        _adapter(_oai_handler(seen)).enumerate_issue(
            make_econsoc_teqe_venue("te"), _te_issue(2024, "20")
        )
    )
    # membership=te（QE 丢）+ partition=2024（2006 丢）+ 墓碑跳过 → te6021/te6022/te6023。
    assert {dict(p.identifiers)["doi"] for p in papers} == {
        "10.3982/te6021",
        "10.3982/te6022",
        "10.3982/te6023",
    }
    # 当前刊（2024=volume_map 最大年）→ 首页 URL 带 from= 回看窗（增量）。
    assert any("from=" in u and "resumptionToken" not in u for u in seen)


def test_enumerate_historical_year_keeps_only_te_2006_records() -> None:
    seen: list[str] = []
    papers = list(
        _adapter(_oai_handler(seen)).enumerate_issue(
            make_econsoc_teqe_venue("te"), _te_issue(2006, "1")
        )
    )
    assert {dict(p.identifiers)["doi"] for p in papers} == {"10.3982/te0001", "10.3982/te0002"}
    # 历史刊（非最大年）→ 无 from= 窗，全量收割。
    assert all("from=" not in u for u in seen)


def test_enumerate_paper_stub_carries_meta() -> None:
    papers = list(
        _adapter(_oai_handler()).enumerate_issue(
            make_econsoc_teqe_venue("te"), _te_issue(2024, "20")
        )
    )
    lead = next(p for p in papers if dict(p.identifiers)["doi"] == "10.3982/te6021")
    assert lead.year == 2024
    assert lead.authors == ("Alpha, Ann", "Beta, Bob")
    meta = dict(lead.meta)
    assert meta["pdf_url"].endswith("6021.PDF")
    assert "Vol 19, No 2" in meta["ojs_source"]


def test_enumerate_unregistered_year_is_config() -> None:
    with pytest.raises(CrawlerError) as exc:
        list(
            _adapter(_oai_handler()).enumerate_issue(
                make_econsoc_teqe_venue("te"), _te_issue(2099, "99")
            )
        )
    assert exc.value.error_class is ErrorClass.CONFIG


def test_enumerate_qe_endpoint_membership_filter() -> None:
    # QE venue（ojs_code=qe）对同一页 fixture 只保留 qe 后缀记录（其余 te 记录丢弃）。
    papers = list(
        _adapter(_oai_handler()).enumerate_issue(
            make_econsoc_teqe_venue("qe"), IssueRef(venue_id="qe", volume="15", year=2024)
        )
    )
    assert {dict(p.identifiers)["doi"] for p in papers} == {"10.3982/qe2297"}


# --- resolve（TE/QE 落地页抽 galley）---------------------------------------------------------


def _landing_handler(landing_body: bytes) -> object:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=landing_body)

    return handler


def test_resolve_te_gets_landing_and_extracts_galley() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, content=fixture_bytes("03_landing_with_galley.html"))

    plans = _adapter(handler).resolve_assets(make_econsoc_teqe_venue("te"), _stub("10.3982/te6021"))
    assert len(plans) == 1
    assert plans[0].kind is AssetKind.PDF
    assert plans[0].auth_needed is AuthLevel.NONE
    assert plans[0].url.endswith("/file/6021.PDF")
    assert httpx.URL(plans[0].url).host == "www.econometricsociety.org"
    # resolve 网络绑定：GET 了 econometricsociety.org/doi/{DOI} 落地页。
    assert any("/doi/10.3982/te6021" in u for u in seen)


def test_resolve_no_galley_returns_zero_assets() -> None:
    body = b"<html><body><p>Subscription required. No galley link here.</p></body></html>"
    plans = _adapter(_landing_handler(body)).resolve_assets(
        make_econsoc_teqe_venue("te"), _stub("10.3982/te6021")
    )
    assert plans == []


def test_resolve_cf_challenge_landing_raises_challenged() -> None:
    handler = _landing_handler(fixture_bytes("04_cf_challenge.html"))
    with pytest.raises(Challenged) as exc:
        _adapter(handler).resolve_assets(make_econsoc_teqe_venue("te"), _stub("10.3982/te6021"))
    assert exc.value.error_class is ErrorClass.CHALLENGE


def test_resolve_missing_doi_is_config() -> None:
    paper = PaperStub(title="X", identifiers=(("arxiv", "2401.00001"),))
    with pytest.raises(CrawlerError) as exc:
        _adapter(_landing_handler(b"")).resolve_assets(make_econsoc_teqe_venue("te"), paper)
    assert exc.value.error_class is ErrorClass.CONFIG


# --- resolve ECMA 分段路由（三分流 + 乐观默认）----------------------------------------------


def test_resolve_ecma_current_domain_fetches_galley() -> None:
    handler = _landing_handler(fixture_bytes("03_landing_with_galley.html"))
    plans = _adapter(handler).resolve_assets(
        make_econsoc_ecma_venue(),
        _stub("10.3982/ecta23709", meta=(("primary_url_domain", "www.econometricsociety.org"),)),
    )
    assert len(plans) == 1 and plans[0].kind is AssetKind.PDF


def test_resolve_ecma_optimistic_current_without_domain() -> None:
    # 无 primary_url_domain（crossref 未登记）→ 乐观归当前段 → 走落地页抽 galley。
    handler = _landing_handler(fixture_bytes("03_landing_with_galley.html"))
    plans = _adapter(handler).resolve_assets(make_econsoc_ecma_venue(), _stub("10.3982/ecta23709"))
    assert len(plans) == 1


def test_resolve_ecma_backfile_wiley_domain_is_no_entitlement() -> None:
    # 过刊段（doi.wiley.com）→ NO_ENTITLEMENT（跨 adapter handoff defer，D-028）；零网络。
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, content=b"should-not-be-called")

    with pytest.raises(CrawlerError) as exc:
        _adapter(handler).resolve_assets(
            make_econsoc_ecma_venue(),
            _stub("10.3982/ecta12058", meta=(("primary_url_domain", "doi.wiley.com"),)),
        )
    assert exc.value.error_class is ErrorClass.NO_ENTITLEMENT
    assert calls == []  # 分段前置判定，未触网


def test_resolve_ecma_pre_doi_jstor_is_zero_assets() -> None:
    # pre-DOI 段（10.2307/JSTOR）→ 界外零资产 skip（非错误）；零网络。
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, content=b"should-not-be-called")

    plans = _adapter(handler).resolve_assets(make_econsoc_ecma_venue(), _stub("10.2307/1912227"))
    assert plans == []
    assert calls == []


# --- fetch（%PDF 透传 / HTML CF 质询→CHALLENGE / HTML 撤稿→GONE）------------------------------


def _stream_handler(body: bytes) -> object:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body)

    return handler


def test_fetch_pdf_passthrough() -> None:
    from paper_crawler.types import AssetPlan

    plan = AssetPlan(kind=AssetKind.PDF, url="https://www.econometricsociety.org/x/file/y.PDF")
    io = FakeFetchIO()
    result = _adapter(_stream_handler(_PDF)).fetch_asset(plan, io)
    assert result.ok is True
    assert io.data == _PDF


def test_fetch_cf_challenge_html_is_challenge() -> None:
    from paper_crawler.types import AssetPlan

    plan = AssetPlan(kind=AssetKind.PDF, url="https://www.econometricsociety.org/x/file/y.PDF")
    handler = _stream_handler(fixture_bytes("04_cf_challenge.html"))
    with pytest.raises(Challenged) as exc:
        _adapter(handler).fetch_asset(plan, FakeFetchIO())
    assert exc.value.error_class is ErrorClass.CHALLENGE


def test_fetch_withdrawn_html_is_gone() -> None:
    from paper_crawler.types import AssetPlan

    plan = AssetPlan(kind=AssetKind.PDF, url="https://www.econometricsociety.org/x/file/y.PDF")
    handler = _stream_handler(fixture_bytes("05_galley_not_pdf.html"))
    with pytest.raises(CrawlerError) as exc:
        _adapter(handler).fetch_asset(plan, FakeFetchIO())
    assert exc.value.error_class is ErrorClass.GONE


# --- healthcheck（TE OAI Identify repositoryName）-------------------------------------------


def _identify_body(repo_name: str) -> bytes:
    return (
        '<?xml version="1.0"?><OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">'
        f"<Identify><repositoryName>{repo_name}</repositoryName>"
        "<protocolVersion>2.0</protocolVersion></Identify></OAI-PMH>"
    ).encode()


def test_healthcheck_ok_when_repository_name_matches() -> None:
    handler = _stream_handler(_identify_body("Theoretical Economics"))
    report = _adapter(handler).healthcheck()
    assert report.healthy is True


def test_healthcheck_unhealthy_on_wrong_repository_name() -> None:
    handler = _stream_handler(_identify_body("Some Other Repository"))
    report = _adapter(handler).healthcheck()
    assert report.healthy is False


def test_healthcheck_unhealthy_when_unreachable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, content=b"down")

    report = _adapter(handler).healthcheck()
    assert report.healthy is False
