"""AAAI OJS `oai_dc` 体层解析器 + DOI 归一单测（design/adapters/aaai-ojs.md §3/§4/§7 T1）。

零真实网络：内联 oai_dc XML / HTML 片段（正式十一件套由 fixtures 层加载，见
test_aaai_fixtures.py）覆盖：DOI 解析/归一矩阵（卷号抽取/小写化/非法形态拒绝）、
oai_dc 体层（title/creator*/description/date/双 identifier 择 DOI/relation→pdf_url）、
GetRecord canary 外壳（idDoesNotExist→GONE）、PaperStub 字段映射、对账路径解析器。
信封层（resumptionToken/墓碑/错误码）由共享核 test_oai_envelope.py 另测。
"""

from __future__ import annotations

import pytest

from paper_crawler.adapters.aaai_ojs import parse
from paper_crawler.adapters.aaai_ojs.parse import AaaiRecord
from paper_crawler.errors import CrawlerError, ErrorClass

# --- 内联 oai_dc 构造工具 ----------------------------------------------------------------------

_NS = (
    'xmlns="http://www.openarchives.org/OAI/2.0/" '
    'xmlns:oai_dc="http://www.openarchives.org/OAI/2.0/oai_dc/" '
    'xmlns:dc="http://purl.org/dc/elements/1.1/"'
)


def _list_page(*dc_bodies: str) -> bytes:
    """把若干 ``<oai_dc:dc>…</oai_dc:dc>`` 内层片段包成一页 ListRecords。"""
    records = "".join(
        f"<record><header><identifier>oai:x:{i}</identifier></header>"
        f"<metadata><oai_dc:dc>{body}</oai_dc:dc></metadata></record>"
        for i, body in enumerate(dc_bodies)
    )
    envelope = f'<?xml version="1.0"?><OAI-PMH {_NS}><ListRecords>{records}</ListRecords></OAI-PMH>'
    return envelope.encode()


def _get_record(inner: str) -> bytes:
    return (
        f'<?xml version="1.0"?><OAI-PMH {_NS}><GetRecord><record>'
        f"<header><identifier>oai:x:1</identifier></header>"
        f"<metadata><oai_dc:dc>{inner}</oai_dc:dc></metadata>"
        f"</record></GetRecord></OAI-PMH>"
    ).encode()


_FULL = (
    "<dc:title>Emergency Department Online Patient-Caregiver Scheduling</dc:title>"
    "<dc:creator>Rosemarin, Hanan</dc:creator>"
    "<dc:creator>Sarne, David</dc:creator>"
    "<dc:description>An abstract about scheduling.</dc:description>"
    "<dc:date>2019-07-21</dc:date>"
    "<dc:identifier>https://ojs.aaai.org/index.php/AAAI/article/view/3745</dc:identifier>"
    "<dc:identifier>10.1609/aaai.v33i01.3301695</dc:identifier>"
    "<dc:source>Proceedings of the AAAI Conference; Vol. 33 No. 01: AAAI-19; 695-701</dc:source>"
    "<dc:relation>https://ojs.aaai.org/index.php/AAAI/article/view/3745/3623</dc:relation>"
)


def _only_record(data: bytes) -> AaaiRecord:
    records = parse.parse_oai_page(data).records
    assert len(records) == 1
    return records[0]


# --- DOI 归一矩阵 ------------------------------------------------------------------------------


def test_normalize_doi_lowercases_and_strips_no_prefix_change() -> None:
    assert parse.normalize_doi("  10.1609/AAAI.V40I1.36958  ") == "10.1609/aaai.v40i1.36958"


@pytest.mark.parametrize(
    ("doi", "expected"),
    [
        ("10.1609/aaai.v40i1.36958", "40"),
        ("10.1609/aaai.v33i01.3301695", "33"),  # 零填充 issue（i01）不影响卷号抽取
        ("10.1609/aaai.v39i12.99999", "39"),
        ("10.1000/not-an-aaai-doi", None),  # 非 AAAI 形态 → 无卷号
    ],
)
def test_volume_from_doi(doi: str, expected: str | None) -> None:
    assert parse.volume_from_doi(doi) == expected


def test_dual_identifier_selects_doi_and_landing_regardless_of_order() -> None:
    # DOI 在前、URL 在后也应正确择出（分类靠形态非顺序）。
    body = (
        "<dc:title>T</dc:title>"
        "<dc:identifier>10.1609/aaai.v40i1.100</dc:identifier>"
        "<dc:identifier>https://ojs.aaai.org/index.php/AAAI/article/view/100</dc:identifier>"
    )
    record = _only_record(_list_page(body))
    assert record.doi == "10.1609/aaai.v40i1.100"
    assert record.landing_url == "https://ojs.aaai.org/index.php/AAAI/article/view/100"
    assert record.article_id == "100"
    assert record.volume == "40"


def test_record_without_doi_identifier_is_parse_error() -> None:
    # 两个 identifier 都不是 DOI（只有 URL + 一个 OJS 内部数字 id）→ 无强锚点 → PARSE。
    body = (
        "<dc:title>T</dc:title>"
        "<dc:identifier>https://ojs.aaai.org/index.php/AAAI/article/view/100</dc:identifier>"
        "<dc:identifier>100</dc:identifier>"
    )
    with pytest.raises(CrawlerError) as exc:
        list(parse.parse_oai_page(_list_page(body)).records)
    assert exc.value.error_class is ErrorClass.PARSE


def test_record_without_title_is_parse_error() -> None:
    body = "<dc:identifier>10.1609/aaai.v40i1.1</dc:identifier>"
    with pytest.raises(CrawlerError) as exc:
        list(parse.parse_oai_page(_list_page(body)).records)
    assert exc.value.error_class is ErrorClass.PARSE


def test_metadata_missing_oai_dc_element_is_parse_error() -> None:
    # <metadata> 在但缺 <oai_dc:dc>（如误配 arXiv schema）= 真实解析失败（非墓碑）→ PARSE。
    data = (
        f'<?xml version="1.0"?><OAI-PMH {_NS}><ListRecords><record>'
        "<header><identifier>oai:x:1</identifier></header>"
        '<metadata><arXiv xmlns="http://arxiv.org/OAI/arXiv/"><id>x</id></arXiv></metadata>'
        "</record></ListRecords></OAI-PMH>"
    ).encode()
    with pytest.raises(CrawlerError) as exc:
        list(parse.parse_oai_page(data).records)
    assert exc.value.error_class is ErrorClass.PARSE


# --- oai_dc 体层字段映射 ----------------------------------------------------------------------


def test_full_record_field_extraction() -> None:
    record = _only_record(_list_page(_FULL))
    assert record.title == "Emergency Department Online Patient-Caregiver Scheduling"
    assert record.authors == ("Rosemarin, Hanan", "Sarne, David")
    assert record.abstract == "An abstract about scheduling."
    assert record.date == "2019-07-21"
    assert record.doi == "10.1609/aaai.v33i01.3301695"
    assert record.volume == "33"
    assert record.landing_url == "https://ojs.aaai.org/index.php/AAAI/article/view/3745"
    assert record.article_id == "3745"
    assert record.pdf_view_url == "https://ojs.aaai.org/index.php/AAAI/article/view/3745/3623"
    assert record.source == "Proceedings of the AAAI Conference; Vol. 33 No. 01: AAAI-19; 695-701"


def test_first_relation_wins_when_secondary_galley_present() -> None:
    # 多 galley（PDF + Video/Poster）：dc:relation 无类型标注，取首个（design §4）。
    body = (
        "<dc:title>T</dc:title>"
        "<dc:identifier>10.1609/aaai.v40i1.5</dc:identifier>"
        "<dc:relation>https://ojs.aaai.org/index.php/AAAI/article/view/5/50</dc:relation>"
        "<dc:relation>https://ojs.aaai.org/index.php/AAAI/article/view/5/99</dc:relation>"
    )
    record = _only_record(_list_page(body))
    assert record.pdf_view_url == "https://ojs.aaai.org/index.php/AAAI/article/view/5/50"


def test_optional_fields_absent_are_none_or_empty() -> None:
    body = "<dc:title>Bare</dc:title><dc:identifier>10.1609/aaai.v40i1.7</dc:identifier>"
    record = _only_record(_list_page(body))
    assert record.abstract is None
    assert record.authors == ()
    assert record.date is None
    assert record.landing_url is None
    assert record.pdf_view_url is None
    assert record.article_id is None
    assert record.source is None


def test_whitespace_wrapped_title_is_normalized() -> None:
    body = (
        "<dc:title>A Title That\n    Wraps Across\n  Several   Lines</dc:title>"
        "<dc:identifier>10.1609/aaai.v40i1.8</dc:identifier>"
    )
    record = _only_record(_list_page(body))
    assert record.title == "A Title That Wraps Across Several Lines"


# --- PaperStub 转换（design §3.3 meta 键名定死）------------------------------------------------


def test_to_paper_stub_identifier_is_single_doi_scheme() -> None:
    stub = parse.to_paper_stub(_only_record(_list_page(_FULL)))
    assert stub.identifiers == (("doi", "10.1609/aaai.v33i01.3301695"),)
    schemes = {scheme for scheme, _ in stub.identifiers}
    assert schemes == {"doi"}


def test_to_paper_stub_meta_keys_and_first_class_fields() -> None:
    stub = parse.to_paper_stub(_only_record(_list_page(_FULL)))
    assert dict(stub.meta) == {
        "pdf_url": "https://ojs.aaai.org/index.php/AAAI/article/view/3745/3623",
        "ojs_article_id": "3745",
        "ojs_source": "Proceedings of the AAAI Conference; Vol. 33 No. 01: AAAI-19; 695-701",
    }
    # 摘要/作者走一级字段，不入 meta。
    assert stub.abstract == "An abstract about scheduling."
    assert stub.authors == ("Rosemarin, Hanan", "Sarne, David")
    assert stub.year == 2019
    assert stub.pub_date == "2019-07-21"
    assert stub.title == "Emergency Department Online Patient-Caregiver Scheduling"


def test_to_paper_stub_meta_omits_absent_optional_keys() -> None:
    body = "<dc:title>Bare</dc:title><dc:identifier>10.1609/aaai.v40i1.7</dc:identifier>"
    stub = parse.to_paper_stub(_only_record(_list_page(body)))
    assert stub.meta == ()  # 无 relation/landing/source → meta 全空
    assert stub.year is None


def test_to_paper_stub_year_none_when_date_absent_or_malformed() -> None:
    body = (
        "<dc:title>T</dc:title><dc:identifier>10.1609/aaai.v40i1.9</dc:identifier>"
        "<dc:date>n/a</dc:date>"
    )
    stub = parse.to_paper_stub(_only_record(_list_page(body)))
    assert stub.year is None
    assert stub.pub_date == "n/a"


# --- GetRecord canary 外壳（复用共享核错误识别）----------------------------------------------


def test_parse_get_record_returns_single_record() -> None:
    record = parse.parse_get_record(_get_record(_FULL))
    assert record.doi == "10.1609/aaai.v33i01.3301695"
    assert record.volume == "33"
    assert record.title == "Emergency Department Online Patient-Caregiver Scheduling"


def test_parse_get_record_id_does_not_exist_is_gone() -> None:
    data = (
        f'<?xml version="1.0"?><OAI-PMH {_NS}>'
        '<error code="idDoesNotExist">No matching identifier.</error></OAI-PMH>'
    ).encode()
    with pytest.raises(CrawlerError) as exc:
        parse.parse_get_record(data)
    assert exc.value.error_class is ErrorClass.GONE


def test_parse_get_record_missing_getrecord_wrapper_is_parse() -> None:
    data = f'<?xml version="1.0"?><OAI-PMH {_NS}><Identify/></OAI-PMH>'.encode()
    with pytest.raises(CrawlerError) as exc:
        parse.parse_get_record(data)
    assert exc.value.error_class is ErrorClass.PARSE


def test_parse_get_record_empty_getrecord_missing_record_is_parse() -> None:
    data = f'<?xml version="1.0"?><OAI-PMH {_NS}><GetRecord></GetRecord></OAI-PMH>'.encode()
    with pytest.raises(CrawlerError) as exc:
        parse.parse_get_record(data)
    assert exc.value.error_class is ErrorClass.PARSE


def test_parse_get_record_record_without_metadata_is_parse() -> None:
    data = (
        f'<?xml version="1.0"?><OAI-PMH {_NS}><GetRecord><record>'
        "<header><identifier>oai:x:1</identifier></header>"
        "</record></GetRecord></OAI-PMH>"
    ).encode()
    with pytest.raises(CrawlerError) as exc:
        parse.parse_get_record(data)
    assert exc.value.error_class is ErrorClass.PARSE


# --- 对账/兜底路径解析器（HTML TOC + citation meta，不接入运行时）------------------------------


def test_parse_issue_toc_extracts_summaries_and_pdf_class_filter() -> None:
    html = (
        b'<div class="obj_article_summary">'
        b'<h3 class="title"><a id="article-100" href="https://ojs.aaai.org/index.php/AAAI/article/view/100">Paper One</a></h3>'  # noqa: E501
        b'<div class="meta"><div class="authors">Ada Lovelace, Alan Turing</div><div class="pages">1-9</div></div>'  # noqa: E501
        b'<ul class="galleys_links">'
        b'<li><a class="obj_galley_link pdf" href="https://ojs.aaai.org/index.php/AAAI/article/view/100/900">PDF</a></li>'
        b'<li><a class="obj_galley_link file" href="https://ojs.aaai.org/index.php/AAAI/article/view/100/901">Video</a></li>'
        b"</ul></div>"
    )
    entries = parse.parse_issue_toc(html)
    assert len(entries) == 1
    entry = entries[0]
    assert entry.article_id == "100"
    assert entry.title == "Paper One"
    assert entry.authors == ("Ada Lovelace", "Alan Turing")
    assert entry.pages == "1-9"
    # PDF class 过滤：只取 obj_galley_link pdf，不取 file（Video）。
    assert entry.pdf_url == "https://ojs.aaai.org/index.php/AAAI/article/view/100/900"


def test_parse_issue_toc_segment_without_title_link_is_parse() -> None:
    html = b'<div class="obj_article_summary"><div class="authors">No title here</div></div>'
    with pytest.raises(CrawlerError) as exc:
        parse.parse_issue_toc(html)
    assert exc.value.error_class is ErrorClass.PARSE


def test_parse_issue_toc_empty_page_yields_empty_tuple() -> None:
    assert parse.parse_issue_toc(b"<html><body>no summaries</body></html>") == ()


def test_parse_issue_toc_title_link_without_article_id_is_parse() -> None:
    # 有 title 链接但 href 不是 /article/view/{id} 形态 → 抽不出 articleId → PARSE。
    html = (
        b'<div class="obj_article_summary">'
        b'<h3 class="title"><a id="x" href="https://ojs.aaai.org/index.php/AAAI/about">T</a></h3>'
        b"</div>"
    )
    with pytest.raises(CrawlerError) as exc:
        parse.parse_issue_toc(html)
    assert exc.value.error_class is ErrorClass.PARSE


def test_parse_article_meta_dc_and_citation() -> None:
    html = (
        b'<meta name="DC.Identifier.DOI" content="10.1609/aaai.v40i1.36958"/>'
        b'<meta name="citation_title" content="Sleep Staging"/>'
        b'<meta name="citation_author" content="Lejun Ai"/>'
        b'<meta name="citation_author" content="Yulong Li"/>'
        b'<meta name="citation_pdf_url" content="https://ojs.aaai.org/index.php/AAAI/article/download/36958/40920"/>'
        b'<meta name="citation_volume" content="40"/>'
        b'<meta name="citation_issue" content="1"/>'
        b'<meta name="citation_firstpage" content="3"/>'
        b'<meta name="citation_lastpage" content="11"/>'
    )
    meta = parse.parse_article_meta(html)
    assert meta.doi == "10.1609/aaai.v40i1.36958"
    assert meta.title == "Sleep Staging"
    assert meta.authors == ("Lejun Ai", "Yulong Li")
    assert meta.pdf_url == "https://ojs.aaai.org/index.php/AAAI/article/download/36958/40920"
    assert (meta.volume, meta.issue, meta.firstpage, meta.lastpage) == ("40", "1", "3", "11")
