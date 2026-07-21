"""cvf cadence 届表生成单测（design/adapters/cvf.md §3.1；T1）。

零依赖（无 http/DB）：cadence 规则生成（cvpr 逐年 / iccv 奇数年 / wacv 2020 起点）、
`cvf_edition_overrides` 合并优先级（单年 include/exclude 修正、不延伸窗口）、
`since_year` 下界裁剪、未登记 venue id 的 CONFIG 早失败、overrides 畸形值校验。
"""

from __future__ import annotations

import pytest

from helpers import make_cvf_venue
from paper_crawler.adapters.cvf import cadence
from paper_crawler.errors import CrawlerError, ErrorClass

# --- cvpr：逐年（annual），2013 起点 ---------------------------------------------------------


def test_cvpr_annual_from_2013_through_current_year() -> None:
    years = cadence.edition_years(make_cvf_venue("cvpr"), current_year=2026)
    assert years == list(range(2013, 2027))


def test_cvpr_current_year_equal_to_inception_yields_single_year() -> None:
    years = cadence.edition_years(make_cvf_venue("cvpr"), current_year=2013)
    assert years == [2013]


def test_cvpr_current_year_before_inception_yields_empty() -> None:
    years = cadence.edition_years(make_cvf_venue("cvpr"), current_year=2012)
    assert years == []


# --- iccv：仅奇数年（biennial_odd），2013 起点 ------------------------------------------------


def test_iccv_only_odd_years_from_2013() -> None:
    years = cadence.edition_years(make_cvf_venue("iccv"), current_year=2026)
    assert years == [2013, 2015, 2017, 2019, 2021, 2023, 2025]
    assert all(y % 2 == 1 for y in years)


def test_iccv_even_current_year_still_stops_at_last_odd() -> None:
    # current_year=2022（偶数）：不产 2022 本身（cadence 不含偶数年），上界仍生效于奇数序列。
    years = cadence.edition_years(make_cvf_venue("iccv"), current_year=2022)
    assert years == [2013, 2015, 2017, 2019, 2021]


# --- wacv：逐年（annual），2020 起点 -----------------------------------------------------------


def test_wacv_annual_from_2020() -> None:
    years = cadence.edition_years(make_cvf_venue("wacv"), current_year=2026)
    assert years == list(range(2020, 2027))


def test_wacv_before_2020_yields_empty() -> None:
    years = cadence.edition_years(make_cvf_venue("wacv"), current_year=2019)
    assert years == []


# --- overrides 合并优先级（单年修正，不改常量表、不延伸窗口）--------------------------------


def test_override_exclude_removes_a_normally_included_year() -> None:
    venue = make_cvf_venue("cvpr", cvf_edition_overrides={2021: "exclude"})
    years = cadence.edition_years(venue, current_year=2023)
    assert 2021 not in years
    assert years == [2013, 2014, 2015, 2016, 2017, 2018, 2019, 2020, 2022, 2023]


def test_override_include_adds_a_normally_excluded_even_iccv_year() -> None:
    # ICCV 偶数年正常被 cadence 排除；override include=一个"补办"年。
    venue = make_cvf_venue("iccv", cvf_edition_overrides={2022: "include"})
    years = cadence.edition_years(venue, current_year=2023)
    assert years == [2013, 2015, 2017, 2019, 2021, 2022, 2023]


def test_override_include_beyond_current_year_has_no_effect() -> None:
    # "不产未来届"：override 无法把窗口延伸到 current_year 之外。
    venue = make_cvf_venue("cvpr", cvf_edition_overrides={2030: "include"})
    years = cadence.edition_years(venue, current_year=2026)
    assert 2030 not in years
    assert years[-1] == 2026


def test_override_string_year_key_is_coerced_to_int() -> None:
    # YAML 年键可能因加引号解析成 str；须与 int 键同等生效。
    venue = make_cvf_venue("cvpr", cvf_edition_overrides={"2021": "exclude"})
    years = cadence.edition_years(venue, current_year=2023)
    assert 2021 not in years


def test_override_action_case_and_whitespace_insensitive() -> None:
    venue = make_cvf_venue("cvpr", cvf_edition_overrides={2021: "  Exclude  "})
    years = cadence.edition_years(venue, current_year=2023)
    assert 2021 not in years


def test_no_overrides_quirk_behaves_as_empty() -> None:
    venue = make_cvf_venue("cvpr")
    assert cadence.resolve_overrides(venue) == {}


def test_cadence_default_included_false_before_inception_direct() -> None:
    # 直接单测这个纯谓词的边界（edition_years 的 range() 恒从 inception 起，不会以
    # < inception 的年份调用它——直接调用验证谓词自身逻辑完整、不依赖调用方保证）。
    spec = cadence.CadenceSpec(inception=2020, cadence=cadence.Cadence.ANNUAL)
    assert cadence._cadence_default_included(spec, 2019) is False
    assert cadence._cadence_default_included(spec, 2020) is True


def test_overrides_non_str_non_int_non_bool_year_key_raises_config() -> None:
    venue = make_cvf_venue("cvpr", cvf_edition_overrides={3.14: "exclude"})
    with pytest.raises(CrawlerError) as exc:
        cadence.edition_years(venue, current_year=2023)
    assert exc.value.error_class is ErrorClass.CONFIG


# --- since_year 下界裁剪（discover_timeline 增量发现）-----------------------------------------


def test_since_year_narrows_lower_bound() -> None:
    years = cadence.edition_years(make_cvf_venue("cvpr"), current_year=2026, since_year=2020)
    assert years == list(range(2020, 2027))


def test_since_year_none_is_unbounded_below() -> None:
    years = cadence.edition_years(make_cvf_venue("cvpr"), current_year=2015, since_year=None)
    assert years[0] == 2013


def test_since_year_above_all_editions_yields_empty() -> None:
    years = cadence.edition_years(make_cvf_venue("wacv"), current_year=2022, since_year=2099)
    assert years == []


# --- 未登记 venue id / 畸形 overrides → CONFIG 早失败 -----------------------------------------


def test_unregistered_venue_id_raises_config() -> None:
    venue = make_cvf_venue("eccv")  # 本 adapter 不注册 ECCV（design §1）
    with pytest.raises(CrawlerError) as exc:
        cadence.edition_years(venue, current_year=2024)
    assert exc.value.error_class is ErrorClass.CONFIG


def test_overrides_not_a_dict_raises_config() -> None:
    venue = make_cvf_venue("cvpr", cvf_edition_overrides=["2021", "exclude"])
    with pytest.raises(CrawlerError) as exc:
        cadence.edition_years(venue, current_year=2023)
    assert exc.value.error_class is ErrorClass.CONFIG


def test_overrides_bad_year_key_raises_config() -> None:
    venue = make_cvf_venue("cvpr", cvf_edition_overrides={"not-a-year": "exclude"})
    with pytest.raises(CrawlerError) as exc:
        cadence.edition_years(venue, current_year=2023)
    assert exc.value.error_class is ErrorClass.CONFIG


def test_overrides_bool_year_key_raises_config() -> None:
    venue = make_cvf_venue("cvpr", cvf_edition_overrides={True: "exclude"})
    with pytest.raises(CrawlerError) as exc:
        cadence.edition_years(venue, current_year=2023)
    assert exc.value.error_class is ErrorClass.CONFIG


def test_overrides_bad_action_value_raises_config() -> None:
    venue = make_cvf_venue("cvpr", cvf_edition_overrides={2021: "delete"})
    with pytest.raises(CrawlerError) as exc:
        cadence.edition_years(venue, current_year=2023)
    assert exc.value.error_class is ErrorClass.CONFIG


def test_overrides_null_action_value_raises_config() -> None:
    venue = make_cvf_venue("cvpr", cvf_edition_overrides={2021: None})
    with pytest.raises(CrawlerError) as exc:
        cadence.edition_years(venue, current_year=2023)
    assert exc.value.error_class is ErrorClass.CONFIG
