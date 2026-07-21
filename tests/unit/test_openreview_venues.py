"""openreview/venues.py 单测（design/adapters/openreview.md §2/§4；T1）。

届表查询矩阵：大小写形态（2013-2017 小写 / 2018+ 大写）、2015/2016 None（缺届）、
overrides 合并优先级（覆盖/新增/掩届）、畸形 overrides → CONFIG。零网络纯逻辑。
"""

from __future__ import annotations

import pytest

from helpers import make_openreview_venue
from paper_crawler.adapters.openreview import venues
from paper_crawler.errors import CrawlerError, ErrorClass

# --- 内置届表：大小写形态 + 缺届 -----------------------------------------------------------


def test_builtin_table_lowercase_conference_2013_to_2017() -> None:
    table = venues.resolve_venue_table(make_openreview_venue())
    assert table[2013] == "ICLR.cc/2013/conference"  # 小写
    assert table[2014] == "ICLR.cc/2014/conference"
    assert table[2017] == "ICLR.cc/2017/conference"


def test_builtin_table_uppercase_conference_from_2018() -> None:
    table = venues.resolve_venue_table(make_openreview_venue())
    assert table[2018] == "ICLR.cc/2018/Conference"  # 大写 C
    assert table[2024] == "ICLR.cc/2024/Conference"
    assert table[2027] == "ICLR.cc/2027/Conference"


def test_builtin_table_2015_and_2016_are_none_missing_years() -> None:
    table = venues.resolve_venue_table(make_openreview_venue())
    assert table[2015] is None  # 主会缺失
    assert table[2016] is None  # 仅 workshop


def test_unknown_venue_id_has_empty_builtin_table() -> None:
    # NeurIPS 等未登记 venue：内置表为空（Phase 2 仅 iclr）。
    venue = make_openreview_venue()
    other = venue.model_copy(update={"id": "neurips"})
    assert venues.resolve_venue_table(other) == {}


# --- issue_years：仅产有主会 id 的年，升序，缺届剔除 ---------------------------------------


def test_issue_years_skips_none_years_and_is_ascending() -> None:
    years = [y for y, _ in venues.issue_years(make_openreview_venue())]
    assert years == sorted(years)
    assert 2015 not in years and 2016 not in years  # 缺届不出现
    assert years[0] == 2013 and 2024 in years


def test_issue_years_pairs_year_with_exact_case_venueid() -> None:
    pairs = dict(venues.issue_years(make_openreview_venue()))
    assert pairs[2013] == "ICLR.cc/2013/conference"
    assert pairs[2018] == "ICLR.cc/2018/Conference"


def test_issue_years_since_year_narrows_lower_bound() -> None:
    years = [y for y, _ in venues.issue_years(make_openreview_venue(), since_year=2020)]
    assert min(years) == 2020
    assert all(y >= 2020 for y in years)


# --- overrides 合并优先级 -------------------------------------------------------------------


def test_overrides_can_fill_a_missing_year() -> None:
    # 2015 内置 None；override 填入真实 id → 该年出现在 issue_years。
    venue = make_openreview_venue(openreview_group_overrides={2015: "ICLR.cc/2015/conference"})
    table = venues.resolve_venue_table(venue)
    assert table[2015] == "ICLR.cc/2015/conference"
    assert 2015 in dict(venues.issue_years(venue))


def test_overrides_can_correct_an_existing_year() -> None:
    venue = make_openreview_venue(
        openreview_group_overrides={2024: "ICLR.cc/2024/Conference/Corrected"}
    )
    assert venues.resolve_venue_table(venue)[2024] == "ICLR.cc/2024/Conference/Corrected"


def test_overrides_null_masks_a_year() -> None:
    # override 值 null → 掩掉该年（即便内置有 id）。
    venue = make_openreview_venue(openreview_group_overrides={2024: None})
    assert venues.resolve_venue_table(venue)[2024] is None
    assert 2024 not in dict(venues.issue_years(venue))


def test_overrides_string_year_key_is_coerced_to_int() -> None:
    # YAML 加引号的年键得 str；归一为 int 后与内置表合并。
    venue = make_openreview_venue(openreview_group_overrides={"2028": "ICLR.cc/2028/Conference"})
    assert venues.resolve_venue_table(venue)[2028] == "ICLR.cc/2028/Conference"


def test_overrides_can_add_a_future_year() -> None:
    venue = make_openreview_venue(openreview_group_overrides={2099: "ICLR.cc/2099/Conference"})
    assert 2099 in dict(venues.issue_years(venue))


# --- 畸形 overrides → CONFIG（响亮停机）----------------------------------------------------


def test_overrides_non_dict_raises_config() -> None:
    venue = make_openreview_venue(openreview_group_overrides="not-a-dict")
    with pytest.raises(CrawlerError) as exc:
        venues.resolve_venue_table(venue)
    assert exc.value.error_class is ErrorClass.CONFIG


def test_overrides_non_year_key_raises_config() -> None:
    venue = make_openreview_venue(openreview_group_overrides={"twenty-fifteen": "x"})
    with pytest.raises(CrawlerError) as exc:
        venues.resolve_venue_table(venue)
    assert exc.value.error_class is ErrorClass.CONFIG


def test_overrides_bool_key_rejected() -> None:
    # bool 是 int 子类——显式挡掉（True→1 之类的怪值）。
    venue = make_openreview_venue(openreview_group_overrides={True: "x"})
    with pytest.raises(CrawlerError) as exc:
        venues.resolve_venue_table(venue)
    assert exc.value.error_class is ErrorClass.CONFIG


def test_overrides_non_string_value_raises_config() -> None:
    venue = make_openreview_venue(openreview_group_overrides={2024: 12345})
    with pytest.raises(CrawlerError) as exc:
        venues.resolve_venue_table(venue)
    assert exc.value.error_class is ErrorClass.CONFIG


def test_overrides_float_year_key_raises_config() -> None:
    # 年键既非 int/str/bool（float）→ catch-all CONFIG。
    venue = make_openreview_venue(openreview_group_overrides={2024.5: "x"})
    with pytest.raises(CrawlerError) as exc:
        venues.resolve_venue_table(venue)
    assert exc.value.error_class is ErrorClass.CONFIG


def test_no_overrides_quirk_uses_builtin_only() -> None:
    # venue 完全不声明 overrides 通道（quirk 缺席）→ 纯内置表。
    venue = make_openreview_venue()
    venue = venue.model_copy(update={"quirks": {}})
    table = venues.resolve_venue_table(venue)
    assert table[2024] == "ICLR.cc/2024/Conference"
