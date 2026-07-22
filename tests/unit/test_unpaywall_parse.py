"""unpaywall parse.py 单测（design/adapters/aggregators.md §5.5）：响应解析、
`url_for_pdf` 回退链、landing 兜底、version 精确串/非正式版判定、畸形输入 → PARSE。

十二件 fixture（`tests/fixtures/unpaywall/`）→ 预期解析形态或 error_class 落点，
覆盖 §8 unpaywall 行全部 error_class（正常/closed 非错误 + config/gone/rate_limited/
transient/parse），零真实网络（纯字节 → 解析，无 HTTP 层）。
"""

from __future__ import annotations

import pytest

from helpers.unpaywall_fixtures import fixture_bytes
from paper_crawler.adapters.unpaywall import parse
from paper_crawler.errors import CrawlerError, ErrorClass

_ANCHOR_DOI = "10.1371/journal.pmed.0020124"


# --- ① 正常 OA 响应（gold，触发回退链；D-019 锚点，aggregators.md §7）--------------------------


def test_01_normal_gold_is_oa_true_and_status_gold() -> None:
    record = parse.parse_response(fixture_bytes("01_normal_gold_fallback.json"), doi=_ANCHOR_DOI)
    assert record.doi == _ANCHOR_DOI
    assert record.is_oa is True
    assert record.oa_status == "gold"
    assert len(record.oa_locations) == 4


def test_01_best_oa_location_url_for_pdf_is_null() -> None:
    record = parse.parse_response(fixture_bytes("01_normal_gold_fallback.json"), doi=_ANCHOR_DOI)
    assert record.best_oa_location is not None
    assert record.best_oa_location.url_for_pdf is None
    assert record.best_oa_location.version == parse.PUBLISHED_VERSION


def test_01_select_pdf_location_falls_back_to_first_hit_in_oa_locations() -> None:
    """回退链：best 无 pdf → 遍历 oa_locations[] 取首个带 url_for_pdf 的项（非最后一个）。"""
    record = parse.parse_response(fixture_bytes("01_normal_gold_fallback.json"), doi=_ANCHOR_DOI)
    location = parse.select_pdf_location(record)
    assert location is not None
    assert location.url_for_pdf == "https://repo.example.org/pdf/0020124-first.pdf"
    assert location.url_for_pdf != "https://repo.example.org/pdf/0020124-second.pdf"
    assert location.version == parse.PUBLISHED_VERSION


def test_01_landing_url_of_reads_best_oa_location() -> None:
    record = parse.parse_response(fixture_bytes("01_normal_gold_fallback.json"), doi=_ANCHOR_DOI)
    assert parse.landing_url_of(record) == (
        "https://journals.plos.org/plosmedicine/article?id=10.1371/journal.pmed.0020124"
    )


# --- ② 直接命中 pdf（无需回退，hybrid + 非正式版 acceptedVersion）------------------------------


def test_02_direct_pdf_hit_no_fallback_needed() -> None:
    record = parse.parse_response(
        fixture_bytes("02_direct_pdf_hit_hybrid.json"), doi="10.9999/synthetic.direct-pdf-hybrid"
    )
    assert record.is_oa is True
    assert record.oa_status == "hybrid"
    location = parse.select_pdf_location(record)
    assert location is not None
    assert location is record.best_oa_location  # 直接命中 best，未经回退遍历
    assert location.url_for_pdf == "https://publisher.example.org/articles/direct-pdf-hybrid.pdf"


def test_02_accepted_version_is_informal() -> None:
    record = parse.parse_response(
        fixture_bytes("02_direct_pdf_hit_hybrid.json"), doi="10.9999/synthetic.direct-pdf-hybrid"
    )
    location = parse.select_pdf_location(record)
    assert location is not None
    assert location.version == parse.ACCEPTED_VERSION
    assert location.version in parse.INFORMAL_VERSIONS


# --- ③ url_for_pdf 全线为空，仅 landing（★裁决 J4）-------------------------------------------


def test_03_no_pdf_anywhere_select_returns_none() -> None:
    record = parse.parse_response(
        fixture_bytes("03_landing_only_no_pdf_anywhere.json"), doi="10.9999/synthetic.landing-only"
    )
    assert record.is_oa is True
    assert record.oa_status == "green"
    assert parse.select_pdf_location(record) is None


def test_03_landing_url_of_has_value_despite_no_pdf() -> None:
    record = parse.parse_response(
        fixture_bytes("03_landing_only_no_pdf_anywhere.json"), doi="10.9999/synthetic.landing-only"
    )
    assert parse.landing_url_of(record) == "https://repo.example.org/landing/landing-only"


def test_03_submitted_version_is_informal() -> None:
    record = parse.parse_response(
        fixture_bytes("03_landing_only_no_pdf_anywhere.json"), doi="10.9999/synthetic.landing-only"
    )
    assert record.best_oa_location is not None
    assert record.best_oa_location.version == parse.SUBMITTED_VERSION
    assert record.best_oa_location.version in parse.INFORMAL_VERSIONS


# --- ④ closed（非错误，is_oa false）------------------------------------------------------------


def test_04_closed_is_oa_false_no_locations() -> None:
    record = parse.parse_response(fixture_bytes("04_closed.json"), doi="10.9999/synthetic.closed")
    assert record.is_oa is False
    assert record.oa_status == "closed"
    assert record.best_oa_location is None
    assert record.oa_locations == ()
    assert parse.select_pdf_location(record) is None
    assert parse.landing_url_of(record) is None


# --- ⑤/⑥ oa_status 枚举代表值覆盖（gold①/hybrid②/green③⑤/bronze⑥/closed④）------------------


def test_05_oa_status_green_with_direct_pdf_and_submitted_version() -> None:
    record = parse.parse_response(
        fixture_bytes("05_oa_status_green_submitted.json"), doi="10.9999/synthetic.green-submitted"
    )
    assert record.oa_status == "green"
    location = parse.select_pdf_location(record)
    assert location is not None
    assert location.version == parse.SUBMITTED_VERSION


def test_06_oa_status_bronze_with_direct_pdf_and_published_version() -> None:
    record = parse.parse_response(
        fixture_bytes("06_oa_status_bronze.json"), doi="10.9999/synthetic.bronze"
    )
    assert record.oa_status == "bronze"
    location = parse.select_pdf_location(record)
    assert location is not None
    assert location.version == parse.PUBLISHED_VERSION
    assert location.version not in parse.INFORMAL_VERSIONS


@pytest.mark.parametrize(
    ("fixture_name", "doi", "expected_status"),
    [
        ("01_normal_gold_fallback.json", _ANCHOR_DOI, "gold"),
        ("02_direct_pdf_hit_hybrid.json", "10.9999/synthetic.direct-pdf-hybrid", "hybrid"),
        ("03_landing_only_no_pdf_anywhere.json", "10.9999/synthetic.landing-only", "green"),
        ("05_oa_status_green_submitted.json", "10.9999/synthetic.green-submitted", "green"),
        ("06_oa_status_bronze.json", "10.9999/synthetic.bronze", "bronze"),
        ("04_closed.json", "10.9999/synthetic.closed", "closed"),
    ],
)
def test_oa_status_enum_representative_values_all_five(
    fixture_name: str, doi: str, expected_status: str
) -> None:
    """§8「oa_status 各枚举代表值」：gold/green/hybrid/bronze/closed 五个枚举全覆盖。"""
    record = parse.parse_response(fixture_bytes(fixture_name), doi=doi)
    assert record.oa_status == expected_status


# --- ⑦/⑧（malformed → parse）------------------------------------------------------------------


def test_11_malformed_json_raises_parse() -> None:
    with pytest.raises(CrawlerError) as exc:
        parse.parse_response(fixture_bytes("11_malformed.json"), doi="10.9999/synthetic.malformed")
    assert exc.value.error_class is ErrorClass.PARSE


def test_12_missing_is_oa_field_raises_parse() -> None:
    """有效 JSON 但缺 `is_oa`（防御性覆盖——JSON 语法错误之外的「有效 JSON、错形状」场景）。"""
    with pytest.raises(CrawlerError) as exc:
        parse.parse_response(
            fixture_bytes("12_missing_required_fields.json"), doi="10.9999/synthetic.missing-is-oa"
        )
    assert exc.value.error_class is ErrorClass.PARSE


def test_parse_response_top_level_not_object_raises_parse() -> None:
    with pytest.raises(CrawlerError) as exc:
        parse.parse_response(b"[1, 2, 3]", doi="10.9999/x")
    assert exc.value.error_class is ErrorClass.PARSE


def test_parse_response_non_bool_is_oa_raises_parse() -> None:
    with pytest.raises(CrawlerError) as exc:
        parse.parse_response(b'{"is_oa": "yes"}', doi="10.9999/x")
    assert exc.value.error_class is ErrorClass.PARSE


# --- doi 键入参优先于响应体自身的 doi 字段（§6：以输入 DOI 为键）-----------------------------


def test_parse_response_uses_caller_supplied_doi_not_response_body_doi() -> None:
    data = b'{"doi": "10.0000/body-echoed-doi", "is_oa": false}'
    record = parse.parse_response(data, doi="10.1234/caller-supplied")
    assert record.doi == "10.1234/caller-supplied"


# --- 边界：best_oa_location/oa_locations 畸形元素的宽松兜底 -------------------------------------


def test_best_oa_location_null_is_not_an_error() -> None:
    record = parse.parse_response(b'{"is_oa": false, "best_oa_location": null}', doi="10.0/x")
    assert record.best_oa_location is None


def test_oa_locations_non_list_falls_back_to_empty_tuple() -> None:
    record = parse.parse_response(b'{"is_oa": true, "oa_locations": "not-a-list"}', doi="10.0/x")
    assert record.oa_locations == ()


def test_oa_locations_skips_non_dict_entries() -> None:
    data = b'{"is_oa": true, "oa_locations": [null, 42, {"url_for_pdf": "https://x/y.pdf"}]}'
    record = parse.parse_response(data, doi="10.0/x")
    assert len(record.oa_locations) == 1
    assert record.oa_locations[0].url_for_pdf == "https://x/y.pdf"


def test_empty_string_fields_normalize_to_none() -> None:
    """空字符串（非 null）字段按 `_str_or_none` 归一为 None（如 `oa_status: ""` 的防御性形态）。"""
    data = b'{"is_oa": false, "oa_status": "", "best_oa_location": {"url_for_pdf": ""}}'
    record = parse.parse_response(data, doi="10.0/x")
    assert record.oa_status is None
    assert record.best_oa_location is not None
    assert record.best_oa_location.url_for_pdf is None
