"""openalex/parse.py 单测（design/adapters/aggregators.md §5.3 字段映射逐行）。

零真实网络：全部输入取自 `tests/fixtures/openalex/`（合成，见该目录 fixture 加载器
docstring）。覆盖：正常批查（含摘要倒排重建/OA meta/多记录）、空结果、倒排索引畸形→
PARSE、缺标题跳过、缺全部 identifier 跳过、`meta.cost_usd` 提取、单条 healthcheck 解析。
"""

from __future__ import annotations

import pytest

from helpers.openalex_fixtures import fixture_bytes
from paper_crawler.adapters.openalex import parse
from paper_crawler.errors import CrawlerError, ErrorClass

# --- parse_works_batch：正常/多记录 -----------------------------------------------------------


def test_normal_batch_yields_two_stubs_with_cost() -> None:
    page = parse.parse_works_batch(fixture_bytes("01_works_normal.json"))

    assert page.cost_usd == 0.0002
    assert page.skipped_untitled == 0
    assert page.skipped_no_identifier == 0
    assert len(page.stubs) == 2


def test_first_record_full_field_mapping() -> None:
    page = parse.parse_works_batch(fixture_bytes("01_works_normal.json"))
    stub = page.stubs[0]

    assert stub.title == (
        "The State of OA: A Large-Scale Analysis of the Prevalence and Impact "
        "of Open Access Articles"
    )
    assert ("openalex", "W2741809807") in stub.identifiers
    assert ("doi", "10.7717/peerj.4375") in stub.identifiers
    assert stub.year == 2018
    assert stub.pub_date == "2018-02-13"
    assert stub.authors == ("Heather Piwowar", "Jason Priem")
    assert stub.abstract == "Despite growing interest in Open Access (OA) in the literature,"
    meta = dict(stub.meta)
    assert meta["is_oa"] == "true"
    assert meta["oa_status"] == "gold"
    assert meta["oa_url"] == "https://peerj.com/articles/4375.pdf"
    assert meta["pdf_url"] == "https://peerj.com/articles/4375.pdf"


def test_second_record_minimal_no_abstract_no_authors_closed() -> None:
    page = parse.parse_works_batch(fixture_bytes("01_works_normal.json"))
    stub = page.stubs[1]

    assert stub.title == "A Minimal Synthetic Work With No Abstract Or Authors"
    assert stub.abstract is None  # 空字典倒排索引＝无摘要，非畸形
    assert stub.authors == ()
    meta = dict(stub.meta)
    assert meta["is_oa"] == "false"
    assert meta["oa_status"] == "closed"
    assert "oa_url" not in meta  # null 值不入 meta
    assert "pdf_url" not in meta  # best_oa_location 为 null


def test_empty_results_yields_no_stubs_but_reads_cost() -> None:
    page = parse.parse_works_batch(fixture_bytes("02_works_empty.json"))

    assert page.stubs == ()
    assert page.cost_usd == 0.0001
    assert page.skipped_untitled == 0


def test_malformed_abstract_inverted_index_raises_parse() -> None:
    with pytest.raises(CrawlerError) as exc:
        parse.parse_works_batch(fixture_bytes("04_works_malformed_inverted_index.json"))
    assert exc.value.error_class is ErrorClass.PARSE


def test_missing_title_is_skipped_not_raised() -> None:
    data = b'{"meta":{"cost_usd":0.0001},"results":[{"id":"https://openalex.org/W1","doi":"https://doi.org/10.1/x"}]}'
    page = parse.parse_works_batch(data)

    assert page.stubs == ()
    assert page.skipped_untitled == 1


def test_blank_title_is_skipped() -> None:
    data = b'{"meta":{},"results":[{"id":"https://openalex.org/W1","title":"   "}]}'
    page = parse.parse_works_batch(data)
    assert page.stubs == ()
    assert page.skipped_untitled == 1


def test_non_dict_result_item_is_skipped() -> None:
    data = b'{"meta":{},"results":["not-an-object"]}'
    page = parse.parse_works_batch(data)
    assert page.stubs == ()
    assert page.skipped_untitled == 1


def test_missing_id_and_doi_is_skipped_as_no_identifier() -> None:
    """极端防御边界：连 `id` 都缺失（正常响应恒有，§5.3），不产违反"至少 1 个
    identifier"约定的 stub。"""
    data = b'{"meta":{},"results":[{"title":"Title Without Any Identifier"}]}'
    page = parse.parse_works_batch(data)
    assert page.stubs == ()
    assert page.skipped_no_identifier == 1


def test_stub_with_only_openalex_id_no_doi_is_still_produced() -> None:
    """无 DOI 时 stub 仍可仅凭 openalex id 成立（identifier(openalex) 恒有）。"""
    data = b'{"meta":{},"results":[{"id":"https://openalex.org/W555","title":"No DOI Here"}]}'
    page = parse.parse_works_batch(data)
    assert len(page.stubs) == 1
    assert page.stubs[0].identifiers == (("openalex", "W555"),)


def test_top_level_not_object_raises_parse() -> None:
    with pytest.raises(CrawlerError) as exc:
        parse.parse_works_batch(b"[1, 2, 3]")
    assert exc.value.error_class is ErrorClass.PARSE


def test_missing_results_key_raises_parse() -> None:
    with pytest.raises(CrawlerError) as exc:
        parse.parse_works_batch(b'{"meta": {}}')
    assert exc.value.error_class is ErrorClass.PARSE


def test_malformed_json_raises_parse() -> None:
    with pytest.raises(CrawlerError) as exc:
        parse.parse_works_batch(b"{not valid json")
    assert exc.value.error_class is ErrorClass.PARSE


def test_cost_usd_missing_defaults_to_zero() -> None:
    data = b'{"meta":{},"results":[]}'
    page = parse.parse_works_batch(data)
    assert page.cost_usd == 0.0


def test_cost_usd_as_string_is_parsed() -> None:
    data = b'{"meta":{"cost_usd":"0.0007"},"results":[]}'
    page = parse.parse_works_batch(data)
    assert page.cost_usd == 0.0007


def test_cost_usd_malformed_string_defaults_to_zero() -> None:
    data = b'{"meta":{"cost_usd":"not-a-number"},"results":[]}'
    page = parse.parse_works_batch(data)
    assert page.cost_usd == 0.0


# --- 倒排索引重建的位置边界 --------------------------------------------------------------------


def test_reconstruct_abstract_handles_gaps_in_positions() -> None:
    data = (
        b'{"meta":{},"results":[{"id":"https://openalex.org/W1","title":"T",'
        b'"abstract_inverted_index":{"Hello":[0],"World":[2]}}]}'
    )
    page = parse.parse_works_batch(data)
    assert page.stubs[0].abstract == "Hello World"  # 位置 1 空缺，join 时跳过 None


def test_reconstruct_abstract_negative_position_raises_parse() -> None:
    data = (
        b'{"meta":{},"results":[{"id":"https://openalex.org/W1","title":"T",'
        b'"abstract_inverted_index":{"bad":[-1]}}]}'
    )
    with pytest.raises(CrawlerError) as exc:
        parse.parse_works_batch(data)
    assert exc.value.error_class is ErrorClass.PARSE


def test_reconstruct_abstract_bool_position_raises_parse() -> None:
    """`bool` 是 `int` 子类——显式排除，防止误判为合法位置。"""
    data = (
        b'{"meta":{},"results":[{"id":"https://openalex.org/W1","title":"T",'
        b'"abstract_inverted_index":{"bad":[true]}}]}'
    )
    with pytest.raises(CrawlerError) as exc:
        parse.parse_works_batch(data)
    assert exc.value.error_class is ErrorClass.PARSE


def test_abstract_inverted_index_non_dict_raises_parse() -> None:
    data = (
        b'{"meta":{},"results":[{"id":"https://openalex.org/W1","title":"T",'
        b'"abstract_inverted_index":"not-an-object"}]}'
    )
    with pytest.raises(CrawlerError) as exc:
        parse.parse_works_batch(data)
    assert exc.value.error_class is ErrorClass.PARSE


def test_abstract_inverted_index_null_is_none_not_malformed() -> None:
    data = (
        b'{"meta":{},"results":[{"id":"https://openalex.org/W1","title":"T",'
        b'"abstract_inverted_index":null}]}'
    )
    page = parse.parse_works_batch(data)
    assert page.stubs[0].abstract is None


def test_bare_openalex_id_without_url_prefix_is_kept_as_is() -> None:
    """`id` 已是裸值（无 `https://openalex.org/` 前缀）时原样返回，不误剥。"""
    data = b'{"meta":{},"results":[{"id":"W777","title":"Already Bare Id"}]}'
    page = parse.parse_works_batch(data)
    assert page.stubs[0].identifiers == (("openalex", "W777"),)


def test_word_with_empty_position_list_contributes_nothing() -> None:
    """词条本身合法但位置列表为空——不产位置、不报错，整体摘要按其余词条重建。"""
    data = (
        b'{"meta":{},"results":[{"id":"https://openalex.org/W1","title":"T",'
        b'"abstract_inverted_index":{"Solo":[0],"NoPositions":[]}}]}'
    )
    page = parse.parse_works_batch(data)
    assert page.stubs[0].abstract == "Solo"


def test_authorships_entry_non_dict_is_skipped() -> None:
    data = (
        b'{"meta":{},"results":[{"id":"https://openalex.org/W1","title":"T",'
        b'"authorships":["not-an-object", {"author": {"display_name": "Real Author"}}]}]}'
    )
    page = parse.parse_works_batch(data)
    assert page.stubs[0].authors == ("Real Author",)


def test_authorships_entry_author_field_non_dict_is_skipped() -> None:
    data = (
        b'{"meta":{},"results":[{"id":"https://openalex.org/W1","title":"T",'
        b'"authorships":[{"author": "not-an-object"}]}]}'
    )
    page = parse.parse_works_batch(data)
    assert page.stubs[0].authors == ()


def test_falsy_oa_status_oa_url_pdf_url_are_omitted_from_meta() -> None:
    data = (
        b'{"meta":{},"results":[{"id":"https://openalex.org/W1","title":"T",'
        b'"open_access":{"is_oa":true,"oa_status":"","oa_url":""},'
        b'"best_oa_location":{"pdf_url":""}}]}'
    )
    page = parse.parse_works_batch(data)
    meta = dict(page.stubs[0].meta)
    assert meta == {"is_oa": "true"}


def test_cost_usd_bool_value_defaults_to_zero() -> None:
    """`bool` 是 `int` 子类——显式排除，防止 `meta.cost_usd:true` 被误当 1.0。"""
    data = b'{"meta":{"cost_usd":true},"results":[]}'
    page = parse.parse_works_batch(data)
    assert page.cost_usd == 0.0


# --- parse_single_work_title（healthcheck）-----------------------------------------------------


def test_parse_single_work_title_returns_normalized_title() -> None:
    title = parse.parse_single_work_title(fixture_bytes("08_single_work_healthcheck.json"))
    assert title == (
        "The State of OA: A Large-Scale Analysis of the Prevalence and Impact "
        "of Open Access Articles"
    )


def test_parse_single_work_title_missing_raises_parse() -> None:
    with pytest.raises(CrawlerError) as exc:
        parse.parse_single_work_title(b'{"id": "https://openalex.org/W1"}')
    assert exc.value.error_class is ErrorClass.PARSE


def test_parse_single_work_title_top_level_not_object_raises_parse() -> None:
    with pytest.raises(CrawlerError) as exc:
        parse.parse_single_work_title(b"[1,2,3]")
    assert exc.value.error_class is ErrorClass.PARSE


def test_parse_single_work_title_collapses_whitespace() -> None:
    title = parse.parse_single_work_title(b'{"title": "  A   Title  With   Extra  Spaces  "}')
    assert title == "A Title With Extra Spaces"
