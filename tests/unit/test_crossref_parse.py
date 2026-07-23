"""crossref/parse.py 单测（design/adapters/aggregators.md §5.1 字段映射逐行）。

覆盖：works 页解析（title[0]/DOI 归一/日期族选择/author 结构/volume-issue/abstract）、
title 空 & DOI 缺跳过计数、facet 年计数、单条 healthcheck title、PaperStub 映射、
日期 date-parts 边界、JSON/结构错误 → PARSE。
"""

from __future__ import annotations

import pytest

from helpers.crossref_fixtures import fixture_bytes
from paper_crawler.adapters.crossref import parse
from paper_crawler.errors import CrawlerError, ErrorClass


def _json(obj: object) -> bytes:
    import json

    return json.dumps(obj).encode("utf-8")


def _worklist(items: list[dict[str, object]], **message_extra: object) -> bytes:
    message: dict[str, object] = {"items": items, **message_extra}
    return _json({"status": "ok", "message-type": "work-list", "message": message})


# --- parse_works_page：正常页字段映射 -------------------------------------------------------


def test_parse_works_page_normal_counts_and_skips() -> None:
    page = parse.parse_works_page(fixture_bytes("01_works_normal.json"))
    # 5 items：3 有效 + 1 空 title + 1 缺 DOI。
    assert page.item_count == 5
    assert len(page.records) == 3
    assert page.skipped_untitled == 1
    assert page.skipped_doiless == 1
    assert page.total_results == 46  # [LIVE] QJE 2024
    assert page.next_cursor == "AoJ4sample4cursor4page1"


def test_parse_works_page_field_mapping_first_record() -> None:
    page = parse.parse_works_page(fixture_bytes("01_works_normal.json"))
    rec = page.records[0]
    assert rec.doi == "10.1093/qje/qjae001"
    # 标题空白规整化：多空格折叠为单空格。
    assert rec.title == "Market Design and the Allocation of Scarce Resources"
    # 日期族选择：published-print 优先（[[2024, 2]] → 'YYYY-MM'）。
    assert rec.pub_date == "2024-02"
    assert rec.volume == "139"
    assert rec.issue == "1"
    assert rec.abstract == "<jats:p>We study the allocation of scarce resources.</jats:p>"
    assert rec.authors == ("Jane Doe", "John Q. Public")


def test_parse_works_page_doi_normalized_from_url_and_case() -> None:
    page = parse.parse_works_page(fixture_bytes("01_works_normal.json"))
    rec = page.records[1]  # DOI 为 'https://doi.org/10.1093/QJE/QJAE002'
    assert rec.doi == "10.1093/qje/qjae002"
    # 无 published-print → 落 published-online（[[2024, 1, 8]] → 'YYYY-MM-DD'）。
    assert rec.pub_date == "2024-01-08"
    assert rec.volume == "139"
    assert rec.issue is None
    assert rec.abstract is None
    assert rec.authors == ("Ada Lovelace",)


def test_parse_works_page_org_author_and_issued_fallback_and_special_issue() -> None:
    page = parse.parse_works_page(fixture_bytes("01_works_normal.json"))
    rec = page.records[2]
    assert rec.doi == "10.1093/qje/qjae003"
    # 无 print/online → 落 issued（[[2024, 3]] → 'YYYY-MM'）。
    assert rec.pub_date == "2024-03"
    assert rec.issue == "S1"  # 特刊文本原样保留
    assert rec.authors == ("The Editors",)  # 机构作者退化到 name


def test_parse_works_page_empty_window() -> None:
    page = parse.parse_works_page(fixture_bytes("02_works_empty.json"))
    assert page.records == ()
    assert page.item_count == 0
    assert page.total_results == 0
    assert page.next_cursor is None


def test_parse_works_page_non_dict_item_counted_as_untitled() -> None:
    page = parse.parse_works_page(_worklist(["not-an-object", {"title": [], "DOI": "10.x/y"}]))
    assert page.records == ()
    assert page.skipped_untitled == 2  # 非对象 item + 空 title 均计无标题跳过


# --- title 提取边界 -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("title_value", "expected_skip"),
    [
        ([], True),  # 空数组
        ("not-a-list", True),  # 非数组
        ([""], True),  # 首元素空白串
        (["   "], True),  # 首元素纯空白
        ([123], True),  # 首元素非字符串
        (["Valid"], False),
    ],
)
def test_first_title_skip_matrix(title_value: object, expected_skip: bool) -> None:
    page = parse.parse_works_page(_worklist([{"DOI": "10.1/x", "title": title_value}]))
    if expected_skip:
        assert page.records == ()
        assert page.skipped_untitled == 1
    else:
        assert len(page.records) == 1
        assert page.skipped_untitled == 0


# --- 日期 date-parts 边界 -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("date_field", "date_obj", "expected"),
    [
        ("issued", {"date-parts": [[2024, 3, 15]]}, "2024-03-15"),
        ("issued", {"date-parts": [[2024, 3]]}, "2024-03"),
        ("issued", {"date-parts": [[2024]]}, "2024"),
        ("issued", {"date-parts": [[]]}, None),  # 未知日期空内层
        ("issued", {"date-parts": []}, None),  # 空外层
        ("issued", {}, None),  # 无 date-parts
    ],
)
def test_pub_date_formatting(date_field: str, date_obj: object, expected: str | None) -> None:
    page = parse.parse_works_page(
        _worklist([{"DOI": "10.1/x", "title": ["T"], date_field: date_obj}])
    )
    assert page.records[0].pub_date == expected


def test_pub_date_first_element_not_a_list_is_none() -> None:
    # date-parts 首元素非列表（畸形）→ None（防御分支）。
    item = {"DOI": "10.1/x", "title": ["T"], "issued": {"date-parts": ["2024-03"]}}
    assert parse.parse_works_page(_worklist([item])).records[0].pub_date is None


def test_facet_count_bool_is_rejected() -> None:
    # bool 是 int 子类——若无显式 guard，True 会被当作计数 1。_int_or_none 显式拒 bool。
    data = _json(
        {
            "status": "ok",
            "message-type": "work-list",
            "message": {"facets": {"published": {"values": {"2024": True, "2023": 44}}}},
        }
    )
    year_counts, _total = parse.parse_facet_years(data)
    assert year_counts == {2023: 44}


def test_pub_date_family_priority() -> None:
    # print > online > issued：三者齐全取 print。
    item = {
        "DOI": "10.1/x",
        "title": ["T"],
        "published-print": {"date-parts": [[2020, 1]]},
        "published-online": {"date-parts": [[2019, 6]]},
        "issued": {"date-parts": [[2018]]},
    }
    assert parse.parse_works_page(_worklist([item])).records[0].pub_date == "2020-01"


# --- author 结构边界 -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("author_value", "expected"),
    [
        ([{"given": "A", "family": "B"}], ("A B",)),
        ([{"family": "Solo"}], ("Solo",)),  # 仅 family
        ([{"given": "Given"}], ("Given",)),  # 仅 given
        ([{"name": "Org Ltd"}], ("Org Ltd",)),  # 机构 name
        ([{"given": "", "family": "  "}], ()),  # 全空白 → 无作者
        ([{"given": "A", "family": "B"}, "junk"], ("A B",)),  # 非 dict 元素跳过
        ("not-a-list", ()),  # author 非数组
        ([], ()),  # 空作者
    ],
)
def test_authors_matrix(author_value: object, expected: tuple[str, ...]) -> None:
    page = parse.parse_works_page(
        _worklist([{"DOI": "10.1/x", "title": ["T"], "author": author_value}])
    )
    assert page.records[0].authors == expected


# --- facet 年计数（discover）---------------------------------------------------------------


def test_parse_facet_years() -> None:
    year_counts, total = parse.parse_facet_years(fixture_bytes("05_facet_published.json"))
    assert year_counts == {2022: 41, 2023: 44, 2024: 46}
    assert total == 6655  # [LIVE] QJE total_all


def test_parse_facet_years_missing_facets_is_empty() -> None:
    year_counts, total = parse.parse_facet_years(_worklist([], **{"total-results": 5}))
    assert year_counts == {}
    assert total == 5


def test_parse_facet_years_skips_non_integer_buckets() -> None:
    data = _json(
        {
            "status": "ok",
            "message-type": "work-list",
            "message": {
                "facets": {"published": {"values": {"2024": 46, "bad-year": 3, "2023": "not-int"}}},
                "total-results": 46,
            },
        }
    )
    year_counts, _total = parse.parse_facet_years(data)
    assert year_counts == {2024: 46}


# --- facet 年计数 date-field 参数化（Phase 5 T1，nber.md §3.1）-------------------------------


def test_parse_facet_years_created_field() -> None:
    """date-field=created：读 `facets.created`（★评审 MAJOR 联动点——ssrn created facet 非空）。"""
    year_counts, total = parse.parse_facet_years(fixture_bytes("13_facet_created.json"), "created")
    assert year_counts == {2024: 210417, 2025: 251908, 2026: 152340}
    assert total == 1414774


def test_parse_facet_years_default_published_empty_on_created_only_fixture() -> None:
    """created-only fixture 用默认 published 解析 → 空 year_counts（证 field 键切换真实生效，

    非恒读 published）；total-results 与 facet 键无关，照常读出。
    """
    year_counts, total = parse.parse_facet_years(fixture_bytes("13_facet_created.json"))
    assert year_counts == {}
    assert total == 1414774


def test_parse_facet_years_explicit_published_equals_default() -> None:
    """显式 field='published' 与默认调用等价（既有 by-ISSN 调用方零改保证）。"""
    fx = fixture_bytes("05_facet_published.json")
    default_counts, _ = parse.parse_facet_years(fx)
    explicit_counts, _ = parse.parse_facet_years(fx, "published")
    assert default_counts == explicit_counts == {2022: 41, 2023: 44, 2024: 46}


def test_parse_facet_years_unknown_field_is_empty() -> None:
    """未知 date-field（facet 无该键）→ 空 year_counts（防御，同缺 facets 口径），total 照读。"""
    year_counts, total = parse.parse_facet_years(
        fixture_bytes("05_facet_published.json"), "created"
    )
    assert year_counts == {}
    assert total == 6655


# --- 单条 healthcheck title -----------------------------------------------------------------


def test_parse_single_work_title() -> None:
    title = parse.parse_single_work_title(fixture_bytes("06_works_healthcheck.json"))
    assert title == "Deep learning"  # fixture 已随 golden 转正（[LIVE] 2026-07-23）


def test_parse_single_work_title_missing_raises_parse() -> None:
    data = _json(
        {"status": "ok", "message-type": "work", "message": {"DOI": "10.1/x", "title": []}}
    )
    with pytest.raises(CrawlerError) as exc:
        parse.parse_single_work_title(data)
    assert exc.value.error_class is ErrorClass.PARSE


# --- PaperStub 映射 -------------------------------------------------------------------------


def test_to_paper_stub_maps_identifier_meta_year() -> None:
    page = parse.parse_works_page(fixture_bytes("01_works_normal.json"))
    stub = parse.to_paper_stub(page.records[0])
    assert stub.title == "Market Design and the Allocation of Scarce Resources"
    assert stub.identifiers == (("doi", "10.1093/qje/qjae001"),)
    assert stub.year == 2024
    assert stub.pub_date == "2024-02"
    assert stub.authors == ("Jane Doe", "John Q. Public")
    assert dict(stub.meta) == {"volume": "139", "issue": "1"}


def test_to_paper_stub_omits_absent_volume_issue() -> None:
    page = parse.parse_works_page(fixture_bytes("01_works_normal.json"))
    stub = parse.to_paper_stub(page.records[1])  # 无 issue
    assert dict(stub.meta) == {"volume": "139"}
    assert stub.abstract is None


def test_to_paper_stub_year_none_when_no_date() -> None:
    page = parse.parse_works_page(_worklist([{"DOI": "10.1/x", "title": ["T"]}]))
    stub = parse.to_paper_stub(page.records[0])
    assert stub.year is None
    assert stub.pub_date is None
    assert stub.meta == ()


# --- JSON / 结构错误 → PARSE ----------------------------------------------------------------


def test_malformed_json_raises_parse() -> None:
    with pytest.raises(CrawlerError) as exc:
        parse.parse_works_page(b"{not valid json")
    assert exc.value.error_class is ErrorClass.PARSE


def test_top_level_not_object_raises_parse() -> None:
    with pytest.raises(CrawlerError) as exc:
        parse.parse_works_page(b"[1, 2, 3]")
    assert exc.value.error_class is ErrorClass.PARSE


def test_missing_message_raises_parse() -> None:
    with pytest.raises(CrawlerError) as exc:
        parse.parse_works_page(b'{"status": "ok"}')
    assert exc.value.error_class is ErrorClass.PARSE
