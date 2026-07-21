"""共享 OAI-PMH 信封层核单测（★C，design/adapters/aaai-ojs.md §9）。

用一个与任何真实 schema 无关的**平凡体层回调**（``_body_text``：从 ``<metadata>``
定位 ``<body>`` 子元素取文本）独立验证信封层契约——错误码归类、`noRecordsMatch`
空态、墓碑遍历+计数、`resumptionToken` 各态、体层回调的 `PARSE` 传播、XML 语法错。
arxiv/aaai 的体层单测各自另测；本文件钉死的是**信封核本身**，防止两 adapter 未来
改动时共享核悄悄漂移。
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

from paper_crawler.adapters import _oai
from paper_crawler.errors import CrawlerError, ErrorClass

# --- 平凡体层回调（schema 无关）---------------------------------------------------------------


# 平凡体层 schema 命名空间（模拟 arxiv 的 `http://arxiv.org/OAI/arXiv/`——体元素有自己
# 的 xmlns，不继承 OAI 协议命名空间）。
_BODY_NS = "urn:test:body"


def _body_text(metadata: ET.Element) -> str:
    """从 `<metadata>` 定位 ``<body>`` 子元素取文本；缺失 → `PARSE`（模拟体层 schema 失配）。"""
    body = metadata.find(f"{{{_BODY_NS}}}body")
    if body is None:
        raise CrawlerError(ErrorClass.PARSE, "metadata missing <body>")
    return (body.text or "").strip()


def _page(data: bytes) -> _oai.OaiListPage[str]:
    return _oai.parse_oai_page(data, record_parser=_body_text)


# --- fixtures ---------------------------------------------------------------------------------

_NORMAL = b"""<?xml version="1.0" encoding="UTF-8"?>
<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">
<ListRecords>
<record><header><identifier>a</identifier></header><metadata><body xmlns="urn:test:body">first</body></metadata></record>
<record><header status="deleted"><identifier>b</identifier></header></record>
<record><header><identifier>c</identifier></header><metadata><body xmlns="urn:test:body">second</body></metadata></record>
<resumptionToken cursor="0" completeListSize="3">TOK</resumptionToken>
</ListRecords>
</OAI-PMH>
"""

_EMPTY_TOKEN = b"""<?xml version="1.0" encoding="UTF-8"?>
<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">
<ListRecords>
<record><header><identifier>a</identifier></header><metadata><body xmlns="urn:test:body">only</body></metadata></record>
<resumptionToken></resumptionToken>
</ListRecords>
</OAI-PMH>
"""

_NO_TOKEN = b"""<?xml version="1.0" encoding="UTF-8"?>
<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">
<ListRecords>
<record><header><identifier>a</identifier></header><metadata><body xmlns="urn:test:body">only</body></metadata></record>
</ListRecords>
</OAI-PMH>
"""

_METADATA_LESS = b"""<?xml version="1.0" encoding="UTF-8"?>
<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">
<ListRecords>
<record><header><identifier>a</identifier></header></record>
<record><header><identifier>b</identifier></header><metadata><body xmlns="urn:test:body">survivor</body></metadata></record>
</ListRecords>
</OAI-PMH>
"""

_BODYLESS_METADATA = b"""<?xml version="1.0" encoding="UTF-8"?>
<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">
<ListRecords>
<record><header><identifier>a</identifier></header><metadata><wrong/></metadata></record>
</ListRecords>
</OAI-PMH>
"""

_NO_LIST_RECORDS = b"""<?xml version="1.0" encoding="UTF-8"?>
<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">
<Identify><repositoryName>Whatever</repositoryName></Identify>
</OAI-PMH>
"""


def _error(code: str) -> bytes:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">'
        f'<error code="{code}">msg</error></OAI-PMH>'
    ).encode()


# --- parse_oai_page ---------------------------------------------------------------------------


def test_normal_page_records_token_and_tombstone_count() -> None:
    page = _page(_NORMAL)
    assert isinstance(page, _oai.OaiListPage)
    assert page.records == ("first", "second")  # 中间的 deleted 墓碑被跳过
    assert page.resumption_token == "TOK"
    assert page.skipped_tombstones == 1


def test_metadata_less_record_counted_as_tombstone_next_record_survives() -> None:
    page = _page(_METADATA_LESS)
    assert page.records == ("survivor",)
    assert page.skipped_tombstones == 1


def test_last_page_empty_token_text_means_end() -> None:
    page = _page(_EMPTY_TOKEN)
    assert page.resumption_token is None
    assert page.skipped_tombstones == 0
    assert page.records == ("only",)


def test_missing_token_element_returns_none() -> None:
    assert _page(_NO_TOKEN).resumption_token is None


def test_no_list_records_yields_empty_page() -> None:
    page = _page(_NO_LIST_RECORDS)
    assert page == _oai.OaiListPage(records=(), resumption_token=None, skipped_tombstones=0)


def test_body_layer_parse_error_propagates_not_swallowed_as_tombstone() -> None:
    # <metadata> 在但缺体元素 = 真实解析失败（体层回调抛 PARSE），不能被墓碑计数吞掉。
    with pytest.raises(CrawlerError) as exc:
        _page(_BODYLESS_METADATA)
    assert exc.value.error_class is ErrorClass.PARSE


def test_no_records_match_is_legal_empty_state() -> None:
    page = _page(_error("noRecordsMatch"))
    assert page == _oai.OaiListPage(records=(), resumption_token=None, skipped_tombstones=0)


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("badResumptionToken", ErrorClass.TRANSIENT),
        ("badArgument", ErrorClass.CONFIG),
        ("badVerb", ErrorClass.CONFIG),
        ("cannotDisseminateFormat", ErrorClass.CONFIG),
        ("idDoesNotExist", ErrorClass.GONE),
        ("someBrandNewCode", ErrorClass.PARSE),
    ],
)
def test_error_code_taxonomy(code: str, expected: ErrorClass) -> None:
    with pytest.raises(CrawlerError) as exc:
        _page(_error(code))
    assert exc.value.error_class is expected
    assert exc.value.detail == code  # detail 携带原始 code


def test_malformed_xml_is_parse() -> None:
    with pytest.raises(CrawlerError) as exc:
        _page(b"<OAI-PMH><ListRecords><record>")
    assert exc.value.error_class is ErrorClass.PARSE


# --- raise_if_oai_error（直接，供 GetRecord 等体层外壳复用）-----------------------------------


def test_raise_if_oai_error_ignores_non_error_root() -> None:
    root = _oai.fromstring(_NO_LIST_RECORDS)
    _oai.raise_if_oai_error(root)  # 不抛


def test_raise_if_oai_error_id_does_not_exist_is_gone() -> None:
    root = _oai.fromstring(_error("idDoesNotExist"))
    with pytest.raises(CrawlerError) as exc:
        _oai.raise_if_oai_error(root)
    assert exc.value.error_class is ErrorClass.GONE


# --- XML 小工具 -------------------------------------------------------------------------------


def test_optional_text_normalizes_and_blank_is_none() -> None:
    root = ET.fromstring("<r><a>  hello \n  world </a><b>   </b></r>")
    assert _oai.optional_text(root, "a") == "hello world"
    assert _oai.optional_text(root, "b") is None
    assert _oai.optional_text(root, "missing") is None


def test_required_text_raises_parse_when_missing() -> None:
    root = ET.fromstring("<r></r>")
    with pytest.raises(CrawlerError) as exc:
        _oai.required_text(root, "a", context="ctx")
    assert exc.value.error_class is ErrorClass.PARSE
    assert "ctx" in str(exc.value)


def test_normalize_ws_collapses_runs() -> None:
    assert _oai.normalize_ws("a\n  b\t c") == "a b c"
