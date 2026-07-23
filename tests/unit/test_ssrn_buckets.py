"""ssrn/buckets.py 单测（纯生成零网络年桶；ssrn.md §4.3 + controller 发现①仲裁令）。

覆盖：逐年桶字段分解（§4.3 裁决）、闭区间 [start, end]、下界=上界单桶、
下界晚于上界空序列（不抛错）、上界截断天然排除脏未来年。
"""

from __future__ import annotations

from paper_crawler.adapters.ssrn import buckets


def test_year_buckets_field_decomposition() -> None:
    """§4.3 字段裁决：volume=None、number=None、year=YYYY、label='YYYY'、count_claimed=None。"""
    issues = list(buckets.year_buckets("ssrn", 2020, 2020))
    assert len(issues) == 1
    issue = issues[0]
    assert issue.venue_id == "ssrn"
    assert issue.volume is None
    assert issue.number is None
    assert issue.year == 2020
    assert issue.label == "2020"
    assert issue.pub_date is None
    assert issue.paper_count_claimed is None  # 规模锚移交 M1 census（纯生成无权威计数）


def test_year_buckets_inclusive_range() -> None:
    years = [i.year for i in buckets.year_buckets("ssrn", 1990, 1993)]
    assert years == [1990, 1991, 1992, 1993]  # 闭区间含上界


def test_year_buckets_single_year_when_start_equals_end() -> None:
    assert [i.year for i in buckets.year_buckets("ssrn", 2026, 2026)] == [2026]


def test_year_buckets_empty_when_start_after_end() -> None:
    """下界晚于上界（如 since 越界）→ 空序列（不抛错，正常态；同 arxiv month_buckets）。"""
    assert list(buckets.year_buckets("ssrn", 2030, 2026)) == []


def test_year_buckets_upper_bound_excludes_dirty_future_years() -> None:
    """上界=今年截断 → 脏未来年（2077/2103/2104）天然不产（纯生成无 facet 数据可污染，§4.3）。"""
    years = {i.year for i in buckets.year_buckets("ssrn", 1990, 2026)}
    assert years == set(range(1990, 2027))
    assert 2077 not in years
    assert 2103 not in years
    assert 2104 not in years
