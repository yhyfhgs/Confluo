"""s2/parse.py 单测（design/adapters/aggregators.md §5.4 字段映射逐行）。

零真实网络：全部输入取自 `tests/fixtures/s2/`（合成，见该目录 fixture 加载器
docstring）。覆盖：正常 batch（含 citationCount/tldr/fieldsOfStudy/openAccessPdf/
DOI 同名 pdf_url 竞合字段）、未命中（null）不算错误、缺标题跳过、顶层非数组→PARSE、
单条 healthcheck 解析。
"""

from __future__ import annotations

import json

import pytest

from helpers.s2_fixtures import fixture_bytes
from paper_crawler.adapters.s2 import parse
from paper_crawler.errors import CrawlerError, ErrorClass

# --- parse_batch_response：正常/未命中/缺标题 --------------------------------------------------


def test_normal_batch_yields_one_stub_one_not_found_one_skipped() -> None:
    result = parse.parse_batch_response(fixture_bytes("01_batch_normal.json"))

    assert len(result.stubs) == 1
    assert result.not_found == 1
    assert result.skipped_untitled == 1


def test_full_field_mapping() -> None:
    result = parse.parse_batch_response(fixture_bytes("01_batch_normal.json"))
    stub = result.stubs[0]

    assert stub.title == "Attention Is All You Need"
    assert ("s2", "204e3073870fae3d05bcbc2f6a8e263d9b72e776") in stub.identifiers
    assert ("doi", "10.48550/arxiv.1706.03762") in stub.identifiers
    assert stub.abstract is None  # §5.4 未列 abstract，不越权
    assert stub.authors == ()  # §5.4 未列 authors
    meta = dict(stub.meta)
    assert meta["citation_count"] == "100000"
    assert "Transformer" in meta["tldr"]
    assert json.loads(meta["fields_of_study"]) == ["Computer Science"]
    assert meta["pdf_url"] == "https://arxiv.org/pdf/1706.03762"
    assert meta["oa_status"] == "GREEN"
    assert "oa_license" not in meta  # license 为 null，不入 meta


def test_null_entry_counts_as_not_found_not_error() -> None:
    result = parse.parse_batch_response(b"[null]")
    assert result.stubs == ()
    assert result.not_found == 1
    assert result.skipped_untitled == 0


def test_entry_missing_title_is_skipped() -> None:
    data = json.dumps([{"paperId": "abc", "citationCount": 1}]).encode()
    result = parse.parse_batch_response(data)
    assert result.stubs == ()
    assert result.skipped_untitled == 1


def test_entry_blank_title_is_skipped() -> None:
    data = json.dumps([{"paperId": "abc", "title": "   "}]).encode()
    result = parse.parse_batch_response(data)
    assert result.stubs == ()
    assert result.skipped_untitled == 1


def test_non_dict_entry_is_skipped() -> None:
    result = parse.parse_batch_response(b'["not-an-object"]')
    assert result.stubs == ()
    assert result.skipped_untitled == 1


def test_entry_missing_all_identifiers_is_skipped() -> None:
    """极端防御边界：连 `paperId` 都缺失，不产违反"至少 1 个 identifier"约定的 stub。"""
    data = json.dumps([{"title": "Title Without Any Identifier"}]).encode()
    result = parse.parse_batch_response(data)
    assert result.stubs == ()
    assert result.skipped_untitled == 1


def test_stub_with_paperid_only_no_doi_is_still_produced() -> None:
    data = json.dumps([{"paperId": "abc123", "title": "No DOI Here"}]).encode()
    result = parse.parse_batch_response(data)
    assert len(result.stubs) == 1
    assert result.stubs[0].identifiers == (("s2", "abc123"),)


def test_empty_array_yields_nothing() -> None:
    result = parse.parse_batch_response(b"[]")
    assert result.stubs == ()
    assert result.not_found == 0
    assert result.skipped_untitled == 0


def test_top_level_not_array_raises_parse() -> None:
    with pytest.raises(CrawlerError) as exc:
        parse.parse_batch_response(fixture_bytes("06_batch_malformed.json"))
    assert exc.value.error_class is ErrorClass.PARSE


def test_malformed_json_raises_parse() -> None:
    with pytest.raises(CrawlerError) as exc:
        parse.parse_batch_response(b"[not valid json")
    assert exc.value.error_class is ErrorClass.PARSE


# --- meta 字段的类型防御（畸形值静默忽略，不炸整条记录）------------------------------------------


def test_non_int_citation_count_is_ignored() -> None:
    data = json.dumps([{"paperId": "x", "title": "T", "citationCount": "not-an-int"}]).encode()
    stub = parse.parse_batch_response(data).stubs[0]
    assert "citation_count" not in dict(stub.meta)


def test_bool_citation_count_is_ignored() -> None:
    """`bool` 是 `int` 子类——显式排除。"""
    data = json.dumps([{"paperId": "x", "title": "T", "citationCount": True}]).encode()
    stub = parse.parse_batch_response(data).stubs[0]
    assert "citation_count" not in dict(stub.meta)


def test_empty_fields_of_study_list_is_omitted() -> None:
    data = json.dumps([{"paperId": "x", "title": "T", "fieldsOfStudy": []}]).encode()
    stub = parse.parse_batch_response(data).stubs[0]
    assert "fields_of_study" not in dict(stub.meta)


def test_tldr_without_text_is_omitted() -> None:
    data = json.dumps([{"paperId": "x", "title": "T", "tldr": {"model": "v2"}}]).encode()
    stub = parse.parse_batch_response(data).stubs[0]
    assert "tldr" not in dict(stub.meta)


def test_external_ids_non_string_or_blank_doi_is_omitted() -> None:
    data = json.dumps([{"paperId": "x", "title": "T", "externalIds": {"DOI": "   "}}]).encode()
    stub = parse.parse_batch_response(data).stubs[0]
    assert stub.identifiers == (("s2", "x"),)


def test_falsy_open_access_pdf_fields_are_omitted() -> None:
    data = json.dumps(
        [
            {
                "paperId": "x",
                "title": "T",
                "openAccessPdf": {"url": "", "status": "", "license": ""},
            }
        ]
    ).encode()
    stub = parse.parse_batch_response(data).stubs[0]
    assert dict(stub.meta) == {}


# --- parse_single_paper_title（healthcheck）----------------------------------------------------


def test_parse_single_paper_title_returns_normalized_title() -> None:
    title = parse.parse_single_paper_title(fixture_bytes("07_single_paper_healthcheck.json"))
    assert title == "Attention Is All You Need"


def test_parse_single_paper_title_missing_raises_parse() -> None:
    with pytest.raises(CrawlerError) as exc:
        parse.parse_single_paper_title(b'{"paperId": "abc"}')
    assert exc.value.error_class is ErrorClass.PARSE


def test_parse_single_paper_title_top_level_not_object_raises_parse() -> None:
    with pytest.raises(CrawlerError) as exc:
        parse.parse_single_paper_title(b"[1,2,3]")
    assert exc.value.error_class is ErrorClass.PARSE


def test_parse_single_paper_title_collapses_whitespace() -> None:
    title = parse.parse_single_paper_title(b'{"title": "  Spaced   Out   Title  "}')
    assert title == "Spaced Out Title"
