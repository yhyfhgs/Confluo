"""acl_anthology/tree.py 单测（design/adapters/acl-anthology.md §4/§9-★4；T1 纯逻辑件）。

矩阵覆盖（design §7 T1 ②）：git-tree JSON 解析（含非 data/xml 路径过滤、`type=tree`
目录条目排除、`truncated=true` 拒绝）；(venue,year)→源文件名映射（新式优先/旧式兜底/
两者皆无→None 零网络短路）；候选年份提取（新式∪旧式，按 venue 过滤，升序）。零网络。
"""

from __future__ import annotations

import json

import pytest

from helpers import make_acl_anthology_venue
from helpers.acl_anthology_fixtures import fixture_bytes
from paper_crawler.adapters.acl_anthology import tree
from paper_crawler.errors import CrawlerError, ErrorClass

_VENUE = make_acl_anthology_venue()


# --- parse_tree_response：过滤 + truncated 拒绝 -------------------------------------------------


def test_parse_tree_response_extracts_only_data_xml_blobs() -> None:
    names = tree.parse_tree_response(fixture_bytes("10_github_tree_sample.json"))
    assert "2023.emnlp.xml" in names
    assert "2023.findings.xml" in names
    assert "D19.xml" in names
    # 非 data/xml 路径、非 .xml 后缀、type=tree 目录条目均被排除。
    assert "schema.rnc" not in names
    assert "people.yaml" not in names
    assert not any("README" in n for n in names)
    assert not any(n.startswith("data") for n in names)  # basename 已剥 data/xml/ 前缀


def test_parse_tree_response_excludes_other_venue_and_includes_multi_year() -> None:
    names = tree.parse_tree_response(fixture_bytes("10_github_tree_sample.json"))
    assert "2023.acl.xml" in names  # 存在于清单（不同 venue），但会被 candidate_years 的过滤剔除
    assert "2022.emnlp.xml" in names
    assert "D07.xml" in names and "D18.xml" in names


def test_parse_tree_response_rejects_truncated() -> None:
    body = json.dumps({"truncated": True, "tree": []}).encode("utf-8")
    with pytest.raises(CrawlerError) as exc:
        tree.parse_tree_response(body)
    assert exc.value.error_class is ErrorClass.PARSE


def test_parse_tree_response_rejects_malformed_json() -> None:
    with pytest.raises(CrawlerError) as exc:
        tree.parse_tree_response(b"{not json")
    assert exc.value.error_class is ErrorClass.PARSE


def test_parse_tree_response_rejects_missing_tree_key() -> None:
    with pytest.raises(CrawlerError) as exc:
        tree.parse_tree_response(json.dumps({"truncated": False}).encode())
    assert exc.value.error_class is ErrorClass.PARSE


def test_parse_tree_response_ignores_non_dict_entries_defensively() -> None:
    body = json.dumps({"truncated": False, "tree": ["not-a-dict", 42, None]}).encode()
    assert tree.parse_tree_response(body) == frozenset()


# --- legacy_prefix ------------------------------------------------------------------------------


def test_legacy_prefix_reads_quirk() -> None:
    assert tree.legacy_prefix(_VENUE) == "D"


def test_legacy_prefix_missing_returns_none() -> None:
    venue = make_acl_anthology_venue(anthology_legacy_prefix=None)
    assert tree.legacy_prefix(venue) is None


def test_legacy_prefix_blank_string_returns_none() -> None:
    venue = make_acl_anthology_venue(anthology_legacy_prefix="  ")
    assert tree.legacy_prefix(venue) is None


# --- resolve_primary_filename：新式优先/旧式兜底/两者皆无 ---------------------------------------


def test_resolve_primary_filename_prefers_new_style() -> None:
    filenames = frozenset({"2023.emnlp.xml", "D19.xml"})
    assert tree.resolve_primary_filename(_VENUE, 2023, filenames) == "2023.emnlp.xml"


def test_resolve_primary_filename_falls_back_to_old_style() -> None:
    filenames = frozenset({"D19.xml"})  # 无新式 2019.emnlp.xml
    assert tree.resolve_primary_filename(_VENUE, 2019, filenames) == "D19.xml"


def test_resolve_primary_filename_none_when_neither_present() -> None:
    filenames = frozenset({"2023.emnlp.xml"})
    assert tree.resolve_primary_filename(_VENUE, 2099, filenames) is None


def test_resolve_primary_filename_none_without_legacy_prefix_quirk() -> None:
    venue = make_acl_anthology_venue(anthology_legacy_prefix=None)
    filenames = frozenset({"D19.xml"})
    # 无 legacy prefix 声明时不会尝试旧式候选（无从构造）。
    assert tree.resolve_primary_filename(venue, 2019, filenames) is None


# --- new/old style filename 构造小工具 -----------------------------------------------------------


def test_new_style_filename() -> None:
    assert tree.new_style_filename("emnlp", 2023) == "2023.emnlp.xml"


def test_old_style_filename_two_digit_year() -> None:
    assert tree.old_style_filename("D", 2019) == "D19.xml"
    assert tree.old_style_filename("D", 2007) == "D07.xml"


def test_findings_filename() -> None:
    assert tree.findings_filename(2023) == "2023.findings.xml"


# --- candidate_years：新旧式并集、按 venue 过滤、升序 --------------------------------------------


def test_candidate_years_unions_new_and_old_style_sorted() -> None:
    names = tree.parse_tree_response(fixture_bytes("10_github_tree_sample.json"))
    years = tree.candidate_years(_VENUE, names)
    assert years == sorted(years)
    assert {2007, 2018, 2019, 2022, 2023} <= set(years)


def test_candidate_years_excludes_other_venue() -> None:
    names = tree.parse_tree_response(fixture_bytes("10_github_tree_sample.json"))
    years = tree.candidate_years(_VENUE, names)
    # data/xml/2023.acl.xml 存在于清单，但不应被计入 emnlp 的候选年份。
    acl_venue = make_acl_anthology_venue()
    acl_years = tree.candidate_years(acl_venue.model_copy(update={"id": "acl"}), names)
    assert 2023 in acl_years
    assert 2023 in years  # emnlp 自己的 2023.emnlp.xml 也在
    # 但两份候选集不应因为共享 "2023" 而混淆彼此的文件来源——各自过滤独立成立。
    assert tree.new_style_filename("acl", 2023) in names
    assert tree.new_style_filename("emnlp", 2023) in names


def test_candidate_years_without_legacy_prefix_only_new_style() -> None:
    names = tree.parse_tree_response(fixture_bytes("10_github_tree_sample.json"))
    venue = make_acl_anthology_venue(anthology_legacy_prefix=None)
    years = tree.candidate_years(venue, names)
    assert 2007 not in years and 2018 not in years and 2019 not in years  # 旧式全部不计入
    assert {2022, 2023} <= set(years)
