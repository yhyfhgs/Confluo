"""econsoc/parse.py 单测（零网络纯函数；design/adapters/econsoc.md §3/§4/§7 T1）。

覆盖：DOI 后缀路由（ecta/te/qe 抽刊别 + 归一 + 非法拒绝）；oai_dc 体层薄解析器（**自写**，
title/creator*/description/date/identifier→DOI/rights + PARSE 分支）；ECMA 分段路由判定
（econometricsociety.org/doi.wiley.com/jstor 三态 + 10.2307 前缀 + crossref link 陈旧 caveat
+ 乐观默认）；volume/galley 抽取；OAI 信封复用（`_oai` 守门，本文件测体层回调接线）。
"""

from __future__ import annotations

import pytest

from paper_crawler.adapters.econsoc import parse
from paper_crawler.adapters.econsoc.parse import EcmaSegment
from paper_crawler.errors import CrawlerError, ErrorClass

_NS = (
    'xmlns="http://www.openarchives.org/OAI/2.0/" '
    'xmlns:oai_dc="http://www.openarchives.org/OAI/2.0/oai_dc/" '
    'xmlns:dc="http://purl.org/dc/elements/1.1/"'
)


def _dc_record(
    *,
    doi: str = "10.3982/TE6021",
    landing: str = "https://econtheory.org/ojs/index.php/te/article/view/6021",
    title: str = "A Theoretical Economics Paper",
    creators: tuple[str, ...] = ("Alpha, Ann", "Beta, Bob"),
    description: str | None = "An abstract.",
    date: str | None = "2024-05-02",
    relation: str | None = "https://econtheory.org/ojs/index.php/te/article/view/6021/galley",
    source: str | None = "Vol 19, No 2 (2024); 601-640",
    rights: str | None = "Creative Commons Attribution-NonCommercial 4.0",
) -> str:
    parts = [f"<dc:title>{title}</dc:title>"]
    parts += [f"<dc:creator>{c}</dc:creator>" for c in creators]
    if description is not None:
        parts.append(f"<dc:description>{description}</dc:description>")
    if date is not None:
        parts.append(f"<dc:date>{date}</dc:date>")
    parts.append(f"<dc:identifier>{landing}</dc:identifier>")
    parts.append(f"<dc:identifier>{doi}</dc:identifier>")
    if source is not None:
        parts.append(f"<dc:source>{source}</dc:source>")
    if relation is not None:
        parts.append(f"<dc:relation>{relation}</dc:relation>")
    if rights is not None:
        parts.append(f"<dc:rights>{rights}</dc:rights>")
    body = "".join(parts)
    return f"<metadata><oai_dc:dc>{body}</oai_dc:dc></metadata>"


def _list_records(records_xml: str, *, token: str | None = None) -> bytes:
    token_el = (
        f'<resumptionToken completeListSize="656">{token}</resumptionToken>'
        if token is not None
        else "<resumptionToken />"
    )
    return (
        f'<?xml version="1.0"?><OAI-PMH {_NS}><ListRecords>'
        f"{records_xml}{token_el}</ListRecords></OAI-PMH>"
    ).encode()


def _one_page(record_metadata: str) -> bytes:
    return _list_records(
        f"<record><header><identifier>oai:x:1</identifier></header>{record_metadata}</record>"
    )


# --- DOI 后缀路由 journal_of_doi -------------------------------------------------------------


@pytest.mark.parametrize(
    ("doi", "expected"),
    [
        ("10.3982/ECTA23709", "ecma"),  # Econometrica 后缀 ecta → venue ecma
        ("10.3982/te6021", "te"),
        ("10.3982/QE2297", "qe"),
        ("https://doi.org/10.3982/ECTA23709", "ecma"),  # URL 前缀经 normalize_doi 剥离
        ("  10.3982/TE6021  ", "te"),  # 首尾空白归一
    ],
)
def test_journal_of_doi_extracts_journal(doi: str, expected: str) -> None:
    assert parse.journal_of_doi(doi) == expected


@pytest.mark.parametrize(
    "doi",
    [
        "10.2307/1912227",  # JSTOR pre-DOI 旧前缀（非 10.3982）
        "10.1111/jofi.13123",  # Wiley（他源）
        "10.3982/foobar",  # 10.3982 但后缀非 ecta/te/qe（无编号）
        "10.3982/te",  # 后缀 te 但缺编号 → 非本源形态
        "",
        "not-a-doi",
    ],
)
def test_journal_of_doi_rejects_non_econsoc(doi: str) -> None:
    assert parse.journal_of_doi(doi) is None


# --- ECMA 分段路由 classify_ecma_segment（design §3.3 三态 + caveat）--------------------------


def test_ecma_segment_current_on_self_hosted_domain() -> None:
    seg = parse.classify_ecma_segment(
        "10.3982/ECTA23709", landing_domain="www.econometricsociety.org"
    )
    assert seg is EcmaSegment.CURRENT


def test_ecma_segment_backfile_on_wiley_domain() -> None:
    # 过刊段（survey §2 [LIVE] ecta12058/2015 → doi.wiley.com 403 CF）→ no_entitlement/skip。
    seg = parse.classify_ecma_segment("10.3982/ECTA12058", landing_domain="doi.wiley.com")
    assert seg is EcmaSegment.BACKFILE


def test_ecma_segment_pre_doi_on_jstor_domain() -> None:
    seg = parse.classify_ecma_segment("10.3982/ECTA9999", landing_domain="www.jstor.org")
    assert seg is EcmaSegment.PRE_DOI


def test_ecma_segment_pre_doi_by_2307_prefix_without_domain() -> None:
    # 10.2307 旧前缀（JSTOR pre-DOI 时代，survey §2 `10.2307/1912227`/1933）→ 前缀即判据。
    seg = parse.classify_ecma_segment("10.2307/1912227", landing_domain=None)
    assert seg is EcmaSegment.PRE_DOI


def test_ecma_segment_optimistic_current_when_domain_unknown() -> None:
    # 无域名信号（crossref 未登记 primary URL / doi.org 未探）→ 乐观归当前段（主路径）。
    seg = parse.classify_ecma_segment("10.3982/ECTA23709", landing_domain=None)
    assert seg is EcmaSegment.CURRENT


def test_ecma_segment_stale_crossref_wiley_link_caveat() -> None:
    """caveat（design §3.3）：若把 crossref 陈旧 Wiley link 域名喂入，本纯函数会误判 BACKFILE
    ——正是"权威信号须取实时落地域名、crossref 登记仅作 pre-filter"结论的反证锚点。"""
    # 一个实为当前段自营的 ECMA DOI，但 crossref 仍登记遗留 onlinelibrary.wiley.com link：
    seg = parse.classify_ecma_segment("10.3982/ECTA23709", landing_domain="onlinelibrary.wiley.com")
    assert seg is EcmaSegment.BACKFILE  # 陈旧域名 → 误判（故运行时以实时落地为权威）


# --- oai_dc 体层薄解析（自写；design §4 字段映射）--------------------------------------------


def test_parse_oai_dc_extracts_all_fields() -> None:
    page = parse.parse_oai_page(_one_page(_dc_record()))
    assert len(page.records) == 1
    rec = page.records[0]
    assert rec.doi == "10.3982/te6021"  # 归一小写
    assert rec.journal == "te"
    assert rec.title == "A Theoretical Economics Paper"
    assert rec.authors == ("Alpha, Ann", "Beta, Bob")  # 多 dc:creator
    assert rec.abstract == "An abstract."
    assert rec.date == "2024-05-02"
    assert rec.source == "Vol 19, No 2 (2024); 601-640"
    assert rec.rights is not None and "Creative Commons" in rec.rights
    assert rec.landing_url == "https://econtheory.org/ojs/index.php/te/article/view/6021"
    assert rec.article_id == "6021"
    assert rec.pdf_view_url is not None and rec.pdf_view_url.endswith("/galley")


def test_parse_oai_dc_missing_title_is_parse_error() -> None:
    xml = _one_page(_dc_record().replace("<dc:title>A Theoretical Economics Paper</dc:title>", ""))
    with pytest.raises(CrawlerError) as exc:
        parse.parse_oai_page(xml)
    assert exc.value.error_class is ErrorClass.PARSE


def test_parse_oai_dc_no_doi_is_parse_error() -> None:
    # 两个 dc:identifier 都非 DOI（landing + 一个非 DOI 串）→ PARSE（design §6）。
    rec = (
        "<metadata><oai_dc:dc>"
        "<dc:title>No DOI Here</dc:title>"
        "<dc:identifier>https://econtheory.org/ojs/index.php/te/article/view/6021</dc:identifier>"
        "<dc:identifier>ISSN 1933-6837</dc:identifier>"
        "</oai_dc:dc></metadata>"
    )
    with pytest.raises(CrawlerError) as exc:
        parse.parse_oai_page(_one_page(rec))
    assert exc.value.error_class is ErrorClass.PARSE


def test_parse_oai_dc_missing_oai_dc_element_is_parse_error() -> None:
    # <metadata> 在但缺 <oai_dc:dc>（schema 漂移）→ PARSE（非墓碑，见 _oai 分层边界）。
    bad = _list_records(
        "<record><header><identifier>oai:x:1</identifier></header>"
        "<metadata><wrong/></metadata></record>"
    )
    with pytest.raises(CrawlerError) as exc:
        parse.parse_oai_page(bad)
    assert exc.value.error_class is ErrorClass.PARSE


# --- OAI 信封复用（_oai 守门；本处测体层回调接线 + 墓碑/token 透传）---------------------------


def test_parse_oai_page_tombstone_and_token_surfaced_via_envelope() -> None:
    xml = _list_records(
        # 一条活记录 + 一条 deleted 墓碑（信封层跳过并计数，体层不参与）。
        f"<record><header><identifier>oai:x:1</identifier></header>{_dc_record(doi='10.3982/QE2297')}</record>"
        '<record><header status="deleted"><identifier>oai:x:2</identifier></header></record>',
        token="NEXT-PAGE-TOKEN",
    )
    page = parse.parse_oai_page(xml)
    assert len(page.records) == 1
    assert page.records[0].journal == "qe"
    assert page.skipped_tombstones == 1
    assert page.resumption_token == "NEXT-PAGE-TOKEN"


def test_parse_oai_page_norecordsmatch_is_empty_not_error() -> None:
    empty = (
        f'<?xml version="1.0"?><OAI-PMH {_NS}>'
        '<error code="noRecordsMatch">nothing</error></OAI-PMH>'
    ).encode()
    page = parse.parse_oai_page(empty)
    assert page.records == ()
    assert page.resumption_token is None


def test_parse_oai_page_malformed_xml_is_parse_error() -> None:
    with pytest.raises(CrawlerError) as exc:
        parse.parse_oai_page(b"<OAI-PMH><ListRecords><record")
    assert exc.value.error_class is ErrorClass.PARSE


# --- GetRecord（canary）+ Identify ------------------------------------------------------------


def test_parse_get_record_single() -> None:
    xml = (
        f'<?xml version="1.0"?><OAI-PMH {_NS}><GetRecord>'
        f"<record><header><identifier>oai:x:1</identifier></header>{_dc_record(doi='10.3982/ECTA23709')}</record>"
        f"</GetRecord></OAI-PMH>"
    ).encode()
    rec = parse.parse_get_record(xml)
    assert rec.doi == "10.3982/ecta23709"
    assert rec.journal == "ecma"


def test_parse_get_record_iddoesnotexist_is_gone() -> None:
    xml = (
        f'<?xml version="1.0"?><OAI-PMH {_NS}>'
        '<error code="idDoesNotExist">no such id</error></OAI-PMH>'
    ).encode()
    with pytest.raises(CrawlerError) as exc:
        parse.parse_get_record(xml)
    assert exc.value.error_class is ErrorClass.GONE


def test_identify_repository_name() -> None:
    xml = (
        f'<?xml version="1.0"?><OAI-PMH {_NS}><Identify>'
        "<repositoryName>Theoretical Economics</repositoryName>"
        "<protocolVersion>2.0</protocolVersion></Identify></OAI-PMH>"
    ).encode()
    assert parse.identify_repository_name(xml) == "Theoretical Economics"


def test_identify_repository_name_missing_is_none() -> None:
    xml = f'<?xml version="1.0"?><OAI-PMH {_NS}></OAI-PMH>'.encode()
    assert parse.identify_repository_name(xml) is None


# --- to_paper_stub（design §3.4 meta 键名）----------------------------------------------------


def test_to_paper_stub_maps_fields_and_meta() -> None:
    rec = parse.parse_oai_page(_one_page(_dc_record())).records[0]
    stub = parse.to_paper_stub(rec)
    assert stub.identifiers == (("doi", "10.3982/te6021"),)  # 本源单一 DOI 锚点（★B）
    assert stub.year == 2024
    assert stub.pub_date == "2024-05-02"
    assert stub.abstract == "An abstract."
    assert stub.authors == ("Alpha, Ann", "Beta, Bob")
    meta = dict(stub.meta)
    assert meta["pdf_url"].endswith("/galley")
    assert meta["landing_url"] == "https://econtheory.org/ojs/index.php/te/article/view/6021"
    assert meta["ojs_article_id"] == "6021"
    assert "Vol 19, No 2" in meta["ojs_source"]
    # 摘要/作者不入 meta（走一级字段）。
    assert "abstract" not in meta


# --- galley 链抽取（design §4 落地页 HTML→ /publications/.../file/{file}.PDF）------------------


def test_extract_galley_url_from_landing_html() -> None:
    # 相对 galley 链（`/publications/.../file/{file}.PDF`，`.PDF` 大写经 IGNORECASE 覆盖）
    # 经 urljoin(landing, …) 归一为绝对同源 URL（survey §4 形态）。
    landing = "https://www.econometricsociety.org/publications/te/2024/05/02/slug"
    html_page = (
        b"<html><body><h1>Some Paper</h1><span>Open Access</span>"
        b'<a href="/publications/te/2024/05/02/slug/file/TE6021.PDF">PDF</a>'
        b"</body></html>"
    )
    url = parse.extract_galley_url(html_page, base_url=landing)
    assert url == (
        "https://www.econometricsociety.org/publications/te/2024/05/02/slug/file/TE6021.PDF"
    )


def test_extract_galley_url_absent_returns_none() -> None:
    html_page = b"<html><body><p>No galley here (subscription wall or withdrawn).</p></body></html>"
    assert (
        parse.extract_galley_url(html_page, base_url="https://www.econometricsociety.org/x") is None
    )
