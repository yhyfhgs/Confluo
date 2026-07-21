"""watch 纯逻辑单测：`_watch_target_months` 跨月边界 + OAI 回放生成器自洽。

runner.watch 的编排（force refresh / 去重 / 七日回放）属集成层，见
tests/integration/test_arxiv_watch.py。此处只测与 DB/网络解耦的两块纯逻辑：
跨月边界目标月计算（arxiv.md §3 watch 裁决）、合成 OAI 生成器能被真实解析器消费。
"""

from __future__ import annotations

from datetime import date

from helpers.arxiv_fixtures import OaiRecord, build_oai_listrecords
from paper_crawler.adapters.arxiv import parse
from paper_crawler.pipeline.runner import _watch_target_months

# --- 跨月边界（当月 + 月初 ≤3 号含上一月桶；4 号起仅当月）------------------------------------


def test_mid_month_targets_current_month_only() -> None:
    assert _watch_target_months(date(2024, 6, 15)) == [(2024, 6)]


def test_day4_is_current_month_only() -> None:
    """4 号起边界已过——仅当月桶（arxiv.md §3：4 号起仅当月）。"""
    assert _watch_target_months(date(2024, 6, 4)) == [(2024, 6)]


def test_day1_includes_previous_month() -> None:
    assert _watch_target_months(date(2024, 6, 1)) == [(2024, 5), (2024, 6)]


def test_day2_includes_previous_month() -> None:
    assert _watch_target_months(date(2024, 6, 2)) == [(2024, 5), (2024, 6)]


def test_day3_includes_previous_month() -> None:
    assert _watch_target_months(date(2024, 6, 3)) == [(2024, 5), (2024, 6)]


def test_year_boundary_wraps_to_december() -> None:
    """1 月月初（≤3 号）的上一月桶是上一年 12 月（跨年回绕）。"""
    assert _watch_target_months(date(2024, 1, 2)) == [(2023, 12), (2024, 1)]


def test_targets_are_oldest_first() -> None:
    """含上月桶时按时间序（oldest-first）——enumerate 先处理旧桶。"""
    months = _watch_target_months(date(2024, 3, 1))
    assert months == sorted(months)


# --- 合成 OAI 生成器 ↔ 真实解析器 round-trip ------------------------------------------------


def test_generator_output_parses_records_and_fields() -> None:
    """生成器产出经 `parse.parse_oai_page` 解析回等价记录（含 journal_ref/doi/墓碑跳过）。"""
    data = build_oai_listrecords(
        [
            OaiRecord("2406.00001", "First", doi="10.1/a", journal_ref="J 2024"),
            OaiRecord("2406.99999", "Tombstone", deleted=True),
            OaiRecord("2406.00002", "Second", categories="cs.CL cs.AI"),
        ]
    )
    page = parse.parse_oai_page(data)
    assert page.skipped_tombstones == 1  # 墓碑被计跳过
    by_id = {r.base_id: r for r in page.records}
    assert set(by_id) == {"2406.00001", "2406.00002"}
    assert by_id["2406.00001"].doi == "10.1/a"
    assert by_id["2406.00001"].journal_ref == "J 2024"
    assert by_id["2406.00002"].primary_category == "cs.CL"  # categories 首个为 primary
    assert page.resumption_token is None  # 缺省单页


def test_generator_resumption_token_round_trips() -> None:
    data = build_oai_listrecords(
        [OaiRecord("2406.00001", "Paged")], resumption_token="cs|2024-06|1"
    )
    assert parse.parse_oai_page(data).resumption_token == "cs|2024-06|1"


def test_generator_xml_escapes_special_chars() -> None:
    """标题含 XML 特殊字符（&/</>）不破坏文档——生成器转义、解析器还原。"""
    data = build_oai_listrecords([OaiRecord("2406.00001", "A & B <C> D")])
    (record,) = parse.parse_oai_page(data).records
    assert record.title == "A & B <C> D"
