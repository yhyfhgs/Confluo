"""预印本虚拟月度桶生成单测（design/adapters/arxiv.md §3；T4 纯逻辑件）。

边界矩阵：inception 起点当月单桶、until 当月未满仍含、跨年、inception 晚于
until（空序列）；字段裁决逐字校验（volume=None/number 两位零填充/year/label/
pub_date=None/paper_count_claimed=None）；inception 格式非法 → CONFIG。
"""

from datetime import date

import pytest

from paper_crawler.adapters.arxiv.buckets import month_buckets
from paper_crawler.errors import CrawlerError, ErrorClass
from paper_crawler.types import IssueRef

VENUE_ID = "arxiv-cs-lg"


def test_inception_equals_until_month_yields_single_bucket() -> None:
    buckets = list(month_buckets(VENUE_ID, "2024-07", date(2024, 7, 15)))
    assert buckets == [
        IssueRef(
            venue_id=VENUE_ID,
            volume=None,
            number="07",
            year=2024,
            label="2024-07",
            pub_date=None,
            paper_count_claimed=None,
        )
    ]


def test_until_mid_month_still_includes_current_month_as_last_bucket() -> None:
    # until=2024-03-10（本月未满）——当月桶仍应生成，不因"未满月"而遗漏。
    buckets = list(month_buckets(VENUE_ID, "2024-01", date(2024, 3, 10)))
    labels = [b.label for b in buckets]
    assert labels == ["2024-01", "2024-02", "2024-03"]


def test_until_at_month_boundary_first_and_last_day_both_include_that_month() -> None:
    first_day = list(month_buckets(VENUE_ID, "2024-01", date(2024, 3, 1)))
    last_day = list(month_buckets(VENUE_ID, "2024-01", date(2024, 3, 31)))
    assert [b.label for b in first_day] == ["2024-01", "2024-02", "2024-03"]
    assert [b.label for b in last_day] == ["2024-01", "2024-02", "2024-03"]


def test_crosses_year_boundary() -> None:
    buckets = list(month_buckets(VENUE_ID, "2023-11", date(2024, 2, 5)))
    labels = [b.label for b in buckets]
    assert labels == ["2023-11", "2023-12", "2024-01", "2024-02"]
    years = [b.year for b in buckets]
    assert years == [2023, 2023, 2024, 2024]
    numbers = [b.number for b in buckets]
    assert numbers == ["11", "12", "01", "02"]


def test_inception_later_than_until_yields_empty_sequence() -> None:
    buckets = list(month_buckets(VENUE_ID, "2025-01", date(2024, 6, 15)))
    assert buckets == []


def test_inception_one_month_after_until_month_is_still_empty() -> None:
    # 边界：仅差一个月也应为空（不是"差一个月才算晚"的宽松判定）。
    buckets = list(month_buckets(VENUE_ID, "2024-08", date(2024, 7, 31)))
    assert buckets == []


def test_month_zero_padding_for_single_digit_months() -> None:
    buckets = list(month_buckets(VENUE_ID, "2024-01", date(2024, 1, 1)))
    assert buckets[0].number == "01"


def test_global_arxiv_inception_fallback_value() -> None:
    # arxiv.md §3：未声明 inception 时回退全局起点 1991-08（回退逻辑属调用方
    # T5，这里只验证函数本身能正确处理该真实起点值）。
    buckets = list(month_buckets(VENUE_ID, "1991-08", date(1991, 9, 30)))
    assert [b.label for b in buckets] == ["1991-08", "1991-09"]


def test_all_fields_match_arxiv_md_decision_for_every_bucket() -> None:
    for bucket in month_buckets(VENUE_ID, "2024-01", date(2024, 12, 31)):
        assert bucket.venue_id == VENUE_ID
        assert bucket.volume is None
        assert bucket.number is not None and len(bucket.number) == 2
        assert bucket.year is not None
        assert bucket.label == f"{bucket.year:04d}-{bucket.number}"
        assert bucket.pub_date is None
        assert bucket.paper_count_claimed is None


# --- 非法 inception 格式 ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "inception",
    [
        "",
        "not-a-date",
        "1991-8",  # 月份未零填充（长度 1）
        "1991/08",  # 分隔符错误
        "199108",  # 无分隔符
        "1991-13",  # 月份越界（13）
        "1991-00",  # 月份越界（0）
        "19910-8",  # 年份宽度错误
        "1991-8x",  # 月份含非数字字符
    ],
)
def test_invalid_inception_format_raises_config_error(inception: str) -> None:
    with pytest.raises(CrawlerError) as exc_info:
        list(month_buckets(VENUE_ID, inception, date(2024, 1, 1)))
    assert exc_info.value.error_class is ErrorClass.CONFIG
