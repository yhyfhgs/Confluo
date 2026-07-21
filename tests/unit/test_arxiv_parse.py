"""Atom/OAI 解析器单测（design/adapters/arxiv.md §3/§5；T4 纯逻辑件）。

用内联 XML 样例（非录制 fixture——正式 fixture 八件套由 T5 建，见 arxiv.md §6）
覆盖：两代 id entry、多作者、缺 abstract、空白折行归一、resumptionToken 各态、
两类 OAI error code、totalResults 异常态、XML 语法错误、记录级必需字段缺失。

fixture 字符串刻意顶格书写（不跟随 Python 代码缩进），保证标签内文本内容可
从源码直接读出、不必心算缩进空白——除了专门测试"空白折行归一"的
`ATOM_WHITESPACE_ENTRY`，那条刻意通过显式拼接控制换行位置。
"""

import pytest

from paper_crawler.adapters.arxiv.parse import (
    ArxivRecord,
    OaiListPage,
    oai_resumption_token,
    parse_atom_feed,
    parse_oai_list_records,
    parse_oai_page,
    to_paper_stub,
)
from paper_crawler.errors import CrawlerError, ErrorClass

# --- Atom fixtures -----------------------------------------------------------------------------

ATOM_TWO_ENTRIES = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/" xmlns:arxiv="http://arxiv.org/schemas/atom">
<title type="html">ArXiv Query Result</title>
<id>http://arxiv.org/api/cHxbiOdZaP56ODnBPIenZhzg5f8</id>
<updated>2024-01-16T00:00:00-05:00</updated>
<opensearch:totalResults>2</opensearch:totalResults>
<opensearch:startIndex>0</opensearch:startIndex>
<opensearch:itemsPerPage>10</opensearch:itemsPerPage>
<entry>
<id>http://arxiv.org/abs/2401.12345v2</id>
<published>2024-01-15T18:00:00Z</published>
<updated>2024-01-16T09:00:00Z</updated>
<title>A Robust Approach to Something Interesting</title>
<summary>We study a robust approach. Results are promising.</summary>
<author><name>Ada Lovelace</name></author>
<author><name>Alan Turing</name></author>
<arxiv:doi>10.1000/j.example.2024.01.001</arxiv:doi>
<arxiv:journal_ref>J. Example 12, 345 (2024)</arxiv:journal_ref>
<link href="http://arxiv.org/abs/2401.12345v2" rel="alternate" type="text/html"/>
<link title="pdf" href="http://arxiv.org/pdf/2401.12345v2" rel="related" type="application/pdf"/>
<arxiv:primary_category term="cs.LG" scheme="http://arxiv.org/schemas/atom"/>
<category term="cs.LG" scheme="http://arxiv.org/schemas/atom"/>
<category term="stat.ML" scheme="http://arxiv.org/schemas/atom"/>
</entry>
<entry>
<id>http://arxiv.org/abs/hep-th/9901001v1</id>
<published>1999-01-06T12:00:00Z</published>
<updated>1999-01-06T12:00:00Z</updated>
<title>An Old Style Identifier Paper</title>
<summary>Abstract text for the old style entry.</summary>
<author><name>Grace Hopper</name></author>
<link href="http://arxiv.org/abs/hep-th/9901001v1" rel="alternate" type="text/html"/>
<arxiv:primary_category term="hep-th" scheme="http://arxiv.org/schemas/atom"/>
<category term="hep-th" scheme="http://arxiv.org/schemas/atom"/>
</entry>
</feed>
"""

ATOM_EMPTY_RESULT = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">
<opensearch:totalResults>0</opensearch:totalResults>
<opensearch:startIndex>0</opensearch:startIndex>
<opensearch:itemsPerPage>10</opensearch:itemsPerPage>
</feed>
"""

ATOM_TOTAL_NONZERO_BUT_NO_ENTRIES = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">
<opensearch:totalResults>5</opensearch:totalResults>
</feed>
"""

ATOM_NO_TOTAL_RESULTS_ELEMENT = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
<entry>
<id>http://arxiv.org/abs/2401.00007</id>
<title>Feed Without opensearch Namespace At All</title>
</entry>
</feed>
"""

ATOM_NON_NUMERIC_TOTAL_RESULTS = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">
<opensearch:totalResults>not-a-number</opensearch:totalResults>
</feed>
"""

ATOM_MISSING_TITLE = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">
<opensearch:totalResults>1</opensearch:totalResults>
<entry>
<id>http://arxiv.org/abs/2401.99999</id>
<summary>No title here.</summary>
</entry>
</feed>
"""

ATOM_BLANK_TITLE = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">
<opensearch:totalResults>1</opensearch:totalResults>
<entry>
<id>http://arxiv.org/abs/2401.99998</id>
<title>   </title>
</entry>
</feed>
"""

ATOM_ID_NOT_ABS_URL = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">
<opensearch:totalResults>1</opensearch:totalResults>
<entry>
<id>http://arxiv.org/weird/2401.99999</id>
<title>Weird Id Url</title>
</entry>
</feed>
"""

ATOM_MALFORMED_XML = b"<feed><entry><id>http://arxiv.org/abs/2401.00001</id>"

_WRAPPED_TITLE = "A Title That\n    Wraps Across\n  Several   Lines"
ATOM_WHITESPACE_ENTRY = (
    """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">
<opensearch:totalResults>1</opensearch:totalResults>
<entry>
<id>http://arxiv.org/abs/2401.55555</id>
<title>"""
    + _WRAPPED_TITLE
    + """</title>
<summary>   </summary>
</entry>
</feed>
"""
).encode()

ATOM_MINIMAL_ENTRY_NO_OPTIONAL_FIELDS = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">
<opensearch:totalResults>1</opensearch:totalResults>
<entry>
<id>http://arxiv.org/abs/2401.66666</id>
<title>Minimal Entry</title>
</entry>
</feed>
"""


# --- OAI fixtures --------------------------------------------------------------------------


OAI_LIST_RECORDS_NORMAL = b"""<?xml version="1.0" encoding="UTF-8"?>
<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">
<responseDate>2024-01-16T00:00:00Z</responseDate>
<request verb="ListRecords" from="2024-01-01" until="2024-01-31" metadataPrefix="arXiv" set="cs">http://export.arxiv.org/oai2</request>
<ListRecords>
<record>
<header>
<identifier>oai:arXiv.org:2401.00001</identifier>
<datestamp>2024-01-01</datestamp>
<setSpec>cs</setSpec>
</header>
<metadata>
<arXiv xmlns="http://arxiv.org/OAI/arXiv/">
<id>2401.00001</id>
<created>2024-01-01</created>
<authors>
<author><keyname>Smith</keyname><forenames>John A.</forenames></author>
<author><keyname>Doe</keyname></author>
<author><affiliation>Ghost Affiliation With No Name</affiliation></author>
</authors>
<title>A Sample OAI Paper Title</title>
<categories>cs.LG stat.ML</categories>
<journal-ref>Proc. Example Conf. 2024</journal-ref>
<doi>10.1000/oai.example.2024</doi>
<abstract>This is the abstract text for the OAI record.</abstract>
</arXiv>
</metadata>
</record>
<record>
<header status="deleted">
<identifier>oai:arXiv.org:2401.00002</identifier>
<datestamp>2024-01-02</datestamp>
<setSpec>cs</setSpec>
</header>
</record>
<record>
<header>
<identifier>oai:arXiv.org:hep-th/9901001</identifier>
<datestamp>2024-01-03</datestamp>
<setSpec>cs</setSpec>
</header>
<metadata>
<arXiv xmlns="http://arxiv.org/OAI/arXiv/">
<id>hep-th/9901001</id>
<created>1999-01-06</created>
<authors>
<author><keyname>Hopper</keyname><forenames>Grace</forenames></author>
</authors>
<title>Old Style OAI Record</title>
<categories>hep-th</categories>
<abstract>Old style abstract.</abstract>
</arXiv>
</metadata>
</record>
<resumptionToken cursor="0" completeListSize="3">abc123XYZtoken</resumptionToken>
</ListRecords>
</OAI-PMH>
"""

OAI_LIST_RECORDS_EMPTY_TOKEN = b"""<?xml version="1.0" encoding="UTF-8"?>
<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">
<responseDate>2024-01-16T00:00:00Z</responseDate>
<request verb="ListRecords">http://export.arxiv.org/oai2</request>
<ListRecords>
<record>
<header>
<identifier>oai:arXiv.org:2401.00001</identifier>
<datestamp>2024-01-01</datestamp>
</header>
<metadata>
<arXiv xmlns="http://arxiv.org/OAI/arXiv/">
<id>2401.00001</id>
<title>Last Page Record</title>
</arXiv>
</metadata>
</record>
<resumptionToken cursor="100" completeListSize="101"></resumptionToken>
</ListRecords>
</OAI-PMH>
"""

OAI_LIST_RECORDS_NO_TOKEN_ELEMENT = b"""<?xml version="1.0" encoding="UTF-8"?>
<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">
<responseDate>2024-01-16T00:00:00Z</responseDate>
<request verb="ListRecords">http://export.arxiv.org/oai2</request>
<ListRecords>
<record>
<header>
<identifier>oai:arXiv.org:2401.00001</identifier>
<datestamp>2024-01-01</datestamp>
</header>
<metadata>
<arXiv xmlns="http://arxiv.org/OAI/arXiv/">
<id>2401.00001</id>
<title>No Resumption Token At All</title>
</arXiv>
</metadata>
</record>
</ListRecords>
</OAI-PMH>
"""

OAI_ERROR_BAD_RESUMPTION_TOKEN = b"""<?xml version="1.0" encoding="UTF-8"?>
<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">
<responseDate>2024-01-16T00:00:00Z</responseDate>
<request verb="ListRecords">http://export.arxiv.org/oai2</request>
<error code="badResumptionToken">resumptionToken is invalid or expired.</error>
</OAI-PMH>
"""

OAI_ERROR_BAD_ARGUMENT = b"""<?xml version="1.0" encoding="UTF-8"?>
<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">
<responseDate>2024-01-16T00:00:00Z</responseDate>
<request>http://export.arxiv.org/oai2</request>
<error code="badArgument">Illegal argument.</error>
</OAI-PMH>
"""

OAI_ERROR_BAD_VERB = b"""<?xml version="1.0" encoding="UTF-8"?>
<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">
<responseDate>2024-01-16T00:00:00Z</responseDate>
<request>http://export.arxiv.org/oai2</request>
<error code="badVerb">Illegal OAI verb.</error>
</OAI-PMH>
"""

OAI_ERROR_CANNOT_DISSEMINATE = b"""<?xml version="1.0" encoding="UTF-8"?>
<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">
<responseDate>2024-01-16T00:00:00Z</responseDate>
<request verb="ListRecords" metadataPrefix="bogus">http://export.arxiv.org/oai2</request>
<error code="cannotDisseminateFormat">Unsupported metadataPrefix.</error>
</OAI-PMH>
"""

OAI_ERROR_ID_DOES_NOT_EXIST = b"""<?xml version="1.0" encoding="UTF-8"?>
<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">
<responseDate>2024-01-16T00:00:00Z</responseDate>
<request verb="GetRecord" identifier="oai:arXiv.org:9999.99999">http://export.arxiv.org/oai2</request>
<error code="idDoesNotExist">No matching identifier.</error>
</OAI-PMH>
"""

OAI_ERROR_UNKNOWN_CODE = b"""<?xml version="1.0" encoding="UTF-8"?>
<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">
<responseDate>2024-01-16T00:00:00Z</responseDate>
<request>http://export.arxiv.org/oai2</request>
<error code="someBrandNewCode">Unclassified error.</error>
</OAI-PMH>
"""

# arxiv.md §5 勘误：noRecordsMatch 是空窗口/空桶的合法响应，不是错误。
OAI_ERROR_NO_RECORDS_MATCH = b"""<?xml version="1.0" encoding="UTF-8"?>
<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">
<responseDate>2024-01-16T00:00:00Z</responseDate>
<request verb="ListRecords" from="2024-01-01" until="2024-01-31" metadataPrefix="arXiv" set="cs">http://export.arxiv.org/oai2</request>
<error code="noRecordsMatch">Empty list for the given from, until, set combination.</error>
</OAI-PMH>
"""

OAI_RECORD_HEADER_ONLY_NO_METADATA = b"""<?xml version="1.0" encoding="UTF-8"?>
<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">
<responseDate>2024-01-16T00:00:00Z</responseDate>
<request verb="ListRecords">http://export.arxiv.org/oai2</request>
<ListRecords>
<record>
<header>
<identifier>oai:arXiv.org:2401.00003</identifier>
<datestamp>2024-01-04</datestamp>
</header>
</record>
<record>
<header>
<identifier>oai:arXiv.org:2401.00004</identifier>
<datestamp>2024-01-04</datestamp>
</header>
<metadata>
<arXiv xmlns="http://arxiv.org/OAI/arXiv/">
<id>2401.00004</id>
<title>Follows The Metadata-less Record</title>
</arXiv>
</metadata>
</record>
</ListRecords>
</OAI-PMH>
"""

OAI_METADATA_MISSING_ARXIV_ELEMENT = b"""<?xml version="1.0" encoding="UTF-8"?>
<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">
<responseDate>2024-01-16T00:00:00Z</responseDate>
<request verb="ListRecords">http://export.arxiv.org/oai2</request>
<ListRecords>
<record>
<header>
<identifier>oai:arXiv.org:2401.00099</identifier>
<datestamp>2024-01-05</datestamp>
</header>
<metadata>
<oai_dc:dc xmlns:oai_dc="http://www.openarchives.org/OAI/2.0/oai_dc/">
<dc:title xmlns:dc="http://purl.org/dc/elements/1.1/">Wrong Format</dc:title>
</oai_dc:dc>
</metadata>
</record>
</ListRecords>
</OAI-PMH>
"""

OAI_NEITHER_ERROR_NOR_LIST_RECORDS = b"""<?xml version="1.0" encoding="UTF-8"?>
<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">
<responseDate>2024-01-16T00:00:00Z</responseDate>
<request verb="Identify">http://export.arxiv.org/oai2</request>
</OAI-PMH>
"""

OAI_MALFORMED_XML = b"<OAI-PMH><ListRecords><record>"


# --- parse_atom_feed -----------------------------------------------------------------------


def test_parse_atom_feed_yields_records_for_both_id_generations() -> None:
    records = list(parse_atom_feed(ATOM_TWO_ENTRIES))
    assert len(records) == 2

    new_style, old_style = records
    assert new_style.base_id == "2401.12345"
    assert new_style.version == 2
    assert new_style.title == "A Robust Approach to Something Interesting"
    assert new_style.abstract == "We study a robust approach. Results are promising."
    assert new_style.authors == ("Ada Lovelace", "Alan Turing")
    assert new_style.categories == ("cs.LG", "stat.ML")
    assert new_style.primary_category == "cs.LG"
    assert new_style.journal_ref == "J. Example 12, 345 (2024)"
    assert new_style.doi == "10.1000/j.example.2024.01.001"
    assert new_style.submitted == "2024-01-15T18:00:00Z"

    assert old_style.base_id == "hep-th/9901001"
    assert old_style.version == 1
    assert old_style.title == "An Old Style Identifier Paper"
    assert old_style.authors == ("Grace Hopper",)
    assert old_style.categories == ("hep-th",)
    assert old_style.primary_category == "hep-th"
    assert old_style.journal_ref is None
    assert old_style.doi is None


def test_parse_atom_feed_empty_result_is_not_an_error() -> None:
    assert list(parse_atom_feed(ATOM_EMPTY_RESULT)) == []


def test_parse_atom_feed_total_results_positive_but_no_entries_is_parse_error() -> None:
    with pytest.raises(CrawlerError) as exc_info:
        list(parse_atom_feed(ATOM_TOTAL_NONZERO_BUT_NO_ENTRIES))
    assert exc_info.value.error_class is ErrorClass.PARSE


def test_parse_atom_feed_missing_total_results_element_does_not_raise() -> None:
    records = list(parse_atom_feed(ATOM_NO_TOTAL_RESULTS_ELEMENT))
    assert len(records) == 1
    assert records[0].base_id == "2401.00007"


def test_parse_atom_feed_non_numeric_total_results_is_treated_as_unknown() -> None:
    # 非数字 totalResults 视为"无法核验"，不阻断解析（也没有 entry 可矛盾）。
    assert list(parse_atom_feed(ATOM_NON_NUMERIC_TOTAL_RESULTS)) == []


def test_parse_atom_feed_missing_title_is_parse_error() -> None:
    with pytest.raises(CrawlerError) as exc_info:
        list(parse_atom_feed(ATOM_MISSING_TITLE))
    assert exc_info.value.error_class is ErrorClass.PARSE


def test_parse_atom_feed_blank_title_is_parse_error() -> None:
    with pytest.raises(CrawlerError) as exc_info:
        list(parse_atom_feed(ATOM_BLANK_TITLE))
    assert exc_info.value.error_class is ErrorClass.PARSE


def test_parse_atom_feed_id_not_abs_url_is_parse_error() -> None:
    with pytest.raises(CrawlerError) as exc_info:
        list(parse_atom_feed(ATOM_ID_NOT_ABS_URL))
    assert exc_info.value.error_class is ErrorClass.PARSE


def test_parse_atom_feed_malformed_xml_is_parse_error() -> None:
    with pytest.raises(CrawlerError) as exc_info:
        list(parse_atom_feed(ATOM_MALFORMED_XML))
    assert exc_info.value.error_class is ErrorClass.PARSE


def test_parse_atom_feed_normalizes_wrapped_whitespace_and_blank_summary_is_none() -> None:
    records = list(parse_atom_feed(ATOM_WHITESPACE_ENTRY))
    assert records[0].title == "A Title That Wraps Across Several Lines"
    assert records[0].abstract is None


def test_parse_atom_feed_minimal_entry_has_none_and_empty_optional_fields() -> None:
    records = list(parse_atom_feed(ATOM_MINIMAL_ENTRY_NO_OPTIONAL_FIELDS))
    record = records[0]
    assert record.abstract is None
    assert record.authors == ()
    assert record.categories == ()
    assert record.primary_category is None
    assert record.journal_ref is None
    assert record.doi is None
    assert record.submitted is None
    assert record.version is None


# --- parse_oai_list_records ------------------------------------------------------------------


def test_parse_oai_list_records_yields_records_and_skips_deleted() -> None:
    records = list(parse_oai_list_records(OAI_LIST_RECORDS_NORMAL))
    assert len(records) == 2  # 第二条 deleted 记录被跳过

    new_style, old_style = records
    assert new_style.base_id == "2401.00001"
    assert new_style.version is None  # OAI arXiv schema 不携带版本信息
    assert new_style.title == "A Sample OAI Paper Title"
    assert new_style.abstract == "This is the abstract text for the OAI record."
    # 第二作者缺 forenames（仅 keyname）；第三作者 keyname/forenames 均缺（只有
    # affiliation）——静默跳过，不产出空字符串条目。
    assert new_style.authors == ("John A. Smith", "Doe")
    assert new_style.categories == ("cs.LG", "stat.ML")
    assert new_style.primary_category == "cs.LG"
    assert new_style.journal_ref == "Proc. Example Conf. 2024"
    assert new_style.doi == "10.1000/oai.example.2024"
    assert new_style.submitted == "2024-01-01"

    assert old_style.base_id == "hep-th/9901001"
    assert old_style.authors == ("Grace Hopper",)
    assert old_style.journal_ref is None
    assert old_style.doi is None


def test_parse_oai_list_records_bad_resumption_token_is_transient() -> None:
    with pytest.raises(CrawlerError) as exc_info:
        list(parse_oai_list_records(OAI_ERROR_BAD_RESUMPTION_TOKEN))
    assert exc_info.value.error_class is ErrorClass.TRANSIENT


# arxiv.md §5 + 2026-07-22 勘误：OAI 错误码逐类归并（noRecordsMatch 单列于下方）。
@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        (OAI_ERROR_BAD_RESUMPTION_TOKEN, ErrorClass.TRANSIENT),
        (OAI_ERROR_BAD_ARGUMENT, ErrorClass.CONFIG),
        (OAI_ERROR_BAD_VERB, ErrorClass.CONFIG),
        (OAI_ERROR_CANNOT_DISSEMINATE, ErrorClass.CONFIG),
        (OAI_ERROR_ID_DOES_NOT_EXIST, ErrorClass.GONE),
        (OAI_ERROR_UNKNOWN_CODE, ErrorClass.PARSE),
    ],
)
def test_parse_oai_error_code_taxonomy(payload: bytes, expected: ErrorClass) -> None:
    with pytest.raises(CrawlerError) as exc_info:
        list(parse_oai_list_records(payload))
    assert exc_info.value.error_class is expected


def test_parse_oai_no_records_match_is_legal_empty_state_not_an_error() -> None:
    # 勘误核心：noRecordsMatch 不抛错，解析为空记录序列正常完成（watch 空日常态）。
    assert list(parse_oai_list_records(OAI_ERROR_NO_RECORDS_MATCH)) == []
    assert oai_resumption_token(OAI_ERROR_NO_RECORDS_MATCH) is None
    page = parse_oai_page(OAI_ERROR_NO_RECORDS_MATCH)
    assert page == OaiListPage(records=(), resumption_token=None, skipped_tombstones=0)


# --- parse_oai_page（记录 + 令牌 + 墓碑跳过数，单遍解析）--------------------------------------


def test_parse_oai_page_exposes_records_token_and_skipped_tombstone_count() -> None:
    # NORMAL 页：3 条 record，其中 1 条 deleted 墓碑；records=2、skipped=1、token 非空。
    page = parse_oai_page(OAI_LIST_RECORDS_NORMAL)
    assert isinstance(page, OaiListPage)
    assert page.skipped_tombstones == 1
    assert tuple(r.base_id for r in page.records) == ("2401.00001", "hep-th/9901001")
    assert page.resumption_token == "abc123XYZtoken"


def test_parse_oai_page_counts_metadata_less_record_as_tombstone() -> None:
    # header 存在但整条缺 <metadata>：与 deleted 同归墓碑跳过计数（防御性跳过）。
    page = parse_oai_page(OAI_RECORD_HEADER_ONLY_NO_METADATA)
    assert page.skipped_tombstones == 1
    assert tuple(r.base_id for r in page.records) == ("2401.00004",)


def test_parse_oai_page_last_page_has_no_token_and_zero_tombstones() -> None:
    page = parse_oai_page(OAI_LIST_RECORDS_EMPTY_TOKEN)
    assert page.resumption_token is None
    assert page.skipped_tombstones == 0
    assert len(page.records) == 1


def test_parse_oai_page_metadata_missing_arxiv_element_is_parse_not_tombstone() -> None:
    # <metadata> 存在但缺 <arXiv> 子元素是真实解析失败 → PARSE（不能被墓碑计数吞掉）。
    with pytest.raises(CrawlerError) as exc_info:
        parse_oai_page(OAI_METADATA_MISSING_ARXIV_ELEMENT)
    assert exc_info.value.error_class is ErrorClass.PARSE


def test_parse_oai_list_records_record_without_metadata_element_is_skipped() -> None:
    # header 存在但无 status="deleted"、且整条 record 连 <metadata> 都没有——
    # 防御性跳过（不同于"标记为 deleted"的路径），后续记录正常解析。
    records = list(parse_oai_list_records(OAI_RECORD_HEADER_ONLY_NO_METADATA))
    assert len(records) == 1
    assert records[0].base_id == "2401.00004"


def test_parse_oai_list_records_metadata_missing_arxiv_element_is_parse_error() -> None:
    with pytest.raises(CrawlerError) as exc_info:
        list(parse_oai_list_records(OAI_METADATA_MISSING_ARXIV_ELEMENT))
    assert exc_info.value.error_class is ErrorClass.PARSE


def test_parse_oai_list_records_malformed_xml_is_parse_error() -> None:
    with pytest.raises(CrawlerError) as exc_info:
        list(parse_oai_list_records(OAI_MALFORMED_XML))
    assert exc_info.value.error_class is ErrorClass.PARSE


def test_parse_oai_list_records_neither_error_nor_list_records_yields_nothing() -> None:
    assert list(parse_oai_list_records(OAI_NEITHER_ERROR_NOR_LIST_RECORDS)) == []


def test_parse_oai_list_records_minimal_record_has_empty_optional_fields() -> None:
    records = list(parse_oai_list_records(OAI_LIST_RECORDS_EMPTY_TOKEN))
    record = records[0]
    assert record.title == "Last Page Record"
    assert record.abstract is None
    assert record.authors == ()
    assert record.categories == ()
    assert record.primary_category is None
    assert record.journal_ref is None
    assert record.doi is None
    assert record.submitted is None


# --- oai_resumption_token ------------------------------------------------------------------


def test_oai_resumption_token_returns_token_text() -> None:
    assert oai_resumption_token(OAI_LIST_RECORDS_NORMAL) == "abc123XYZtoken"


def test_oai_resumption_token_empty_text_means_end_of_list() -> None:
    assert oai_resumption_token(OAI_LIST_RECORDS_EMPTY_TOKEN) is None


def test_oai_resumption_token_missing_element_returns_none() -> None:
    assert oai_resumption_token(OAI_LIST_RECORDS_NO_TOKEN_ELEMENT) is None


def test_oai_resumption_token_neither_error_nor_list_records_returns_none() -> None:
    assert oai_resumption_token(OAI_NEITHER_ERROR_NOR_LIST_RECORDS) is None


def test_oai_resumption_token_raises_same_as_parser_on_error_response() -> None:
    with pytest.raises(CrawlerError) as exc_info:
        oai_resumption_token(OAI_ERROR_BAD_RESUMPTION_TOKEN)
    assert exc_info.value.error_class is ErrorClass.TRANSIENT


# --- to_paper_stub -------------------------------------------------------------------------


def _make_record(**overrides: object) -> ArxivRecord:
    defaults: dict[str, object] = {
        "base_id": "2401.12345",
        "version": 2,
        "title": "A Title",
        "abstract": "An abstract.",
        "authors": ("Ada Lovelace",),
        "categories": ("cs.LG",),
        "primary_category": "cs.LG",
        "journal_ref": None,
        "doi": None,
        "submitted": "2024-01-15T18:00:00Z",
    }
    defaults.update(overrides)
    return ArxivRecord(**defaults)  # type: ignore[arg-type]


def test_to_paper_stub_identifiers_is_single_arxiv_scheme_tuple() -> None:
    stub = to_paper_stub(_make_record(base_id="2401.12345"))
    assert stub.identifiers == (("arxiv", "2401.12345"),)


def test_to_paper_stub_puts_journal_ref_and_doi_in_meta_never_as_identifier() -> None:
    stub = to_paper_stub(
        _make_record(journal_ref="J. Example 12, 345 (2024)", doi="10.1000/example")
    )
    assert dict(stub.meta) == {
        "journal_ref": "J. Example 12, 345 (2024)",
        "doi": "10.1000/example",
    }
    schemes = {scheme for scheme, _ in stub.identifiers}
    assert schemes == {"arxiv"}  # journal_ref/doi 绝不产出为 identifier


def test_to_paper_stub_meta_empty_when_journal_ref_and_doi_absent() -> None:
    stub = to_paper_stub(_make_record(journal_ref=None, doi=None))
    assert stub.meta == ()


def test_to_paper_stub_derives_year_from_submitted() -> None:
    stub = to_paper_stub(_make_record(submitted="2024-01-15T18:00:00Z"))
    assert stub.year == 2024


def test_to_paper_stub_year_is_none_when_submitted_is_none() -> None:
    stub = to_paper_stub(_make_record(submitted=None))
    assert stub.year is None


def test_to_paper_stub_carries_title_abstract_authors_and_pub_date() -> None:
    stub = to_paper_stub(
        _make_record(
            title="A Title",
            abstract="An abstract.",
            authors=("Ada Lovelace", "Alan Turing"),
            submitted="2024-01-15T18:00:00Z",
        )
    )
    assert stub.title == "A Title"
    assert stub.abstract == "An abstract."
    assert stub.authors == ("Ada Lovelace", "Alan Turing")
    assert stub.pub_date == "2024-01-15T18:00:00Z"


def test_to_paper_stub_end_to_end_from_parsed_atom_entry() -> None:
    record = next(iter(parse_atom_feed(ATOM_TWO_ENTRIES)))
    stub = to_paper_stub(record)
    assert stub.identifiers == (("arxiv", "2401.12345"),)
    assert dict(stub.meta) == {
        "journal_ref": "J. Example 12, 345 (2024)",
        "doi": "10.1000/j.example.2024.01.001",
    }
    assert stub.year == 2024


def test_to_paper_stub_end_to_end_from_parsed_oai_record() -> None:
    record = next(iter(parse_oai_list_records(OAI_LIST_RECORDS_NORMAL)))
    stub = to_paper_stub(record)
    assert stub.identifiers == (("arxiv", "2401.00001"),)
    assert dict(stub.meta) == {
        "journal_ref": "Proc. Example Conf. 2024",
        "doi": "10.1000/oai.example.2024",
    }
    assert stub.year == 2024
