"""数量护栏引擎（Phase 6 T3；design/09 §6）——`is_truncated` 熔断边界 + `OverloadReport`。

`dedupe_against_library` 走真 sqlite，见 `tests/integration/test_subs_guard_db.py`。
"""

from __future__ import annotations

import dataclasses

import pytest

from paper_crawler.subs.guard import OverloadReport, build_overload_report, is_truncated
from paper_crawler.subs.types import ReportEntry


def _entry(source: str = "arxiv", categories: tuple[str, ...] = ()) -> ReportEntry:
    return ReportEntry(
        title=f"paper via {source or 'unknown'}", source=source, categories=categories
    )


# --- 熔断边界（design/09 §6.1：等于阈值不熔断，大于才熔断）--------------------


@pytest.mark.parametrize(
    ("new_count", "max_new_per_run", "expected"),
    [
        (200, 200, False),  # 恰好等于阈值 → 不熔断
        (201, 200, True),  # 严格大于 → 熔断
        (199, 200, False),
        (0, 200, False),
        (1, 1, False),  # 阈值下界 1（model.py 校验的最小值）
        (2, 1, True),
    ],
)
def test_is_truncated_boundary(new_count: int, max_new_per_run: int, expected: bool) -> None:
    assert is_truncated(new_count, max_new_per_run) is expected


# --- OverloadReport 数据结构 --------------------------------------------------


def test_overload_report_is_frozen() -> None:
    report = OverloadReport(subscription="s", new_count=1, guard_limit=1)
    with pytest.raises(dataclasses.FrozenInstanceError):
        report.new_count = 2  # type: ignore[misc]


def test_build_overload_report_counts_and_source_dominant_suggestion() -> None:
    entries = [
        _entry("arxiv", ("cs.AI",)),
        _entry("arxiv", ("cs.AI",)),
        _entry("arxiv", ("cs.AI",)),
        _entry("arxiv", ("cs.LG",)),
        _entry("ssrn"),  # 无分类 → 不进 by_category，但仍计入 by_source
    ]
    report = build_overload_report("llm-agents", entries, guard_limit=3)

    assert report.subscription == "llm-agents"
    assert report.new_count == 5
    assert report.guard_limit == 3
    assert report.by_source == (("arxiv", 4), ("ssrn", 1))
    assert report.by_category == (("cs.AI", 3), ("cs.LG", 1))
    assert "来源" in report.suggestion
    assert "arxiv" in report.suggestion
    assert "4/5" in report.suggestion


def test_build_overload_report_category_dominant_when_higher_share() -> None:
    """来源高度分散、类目高度集中时——收窄建议应指向类目而非来源。"""
    entries = [
        _entry("arxiv", ("shared",)),
        _entry("ssrn", ("shared",)),
        _entry("nber", ("shared",)),
        _entry("crossref"),
        _entry("openalex"),
    ]
    report = build_overload_report("s", entries, guard_limit=1)

    assert report.by_source[0] == ("arxiv", 1)  # 5 源各 1，字典序打平
    assert report.by_category == (("shared", 3),)
    assert "类目" in report.suggestion
    assert "shared" in report.suggestion
    assert "3/5" in report.suggestion


def test_build_overload_report_tie_prefers_source_axis() -> None:
    """来源与类目占比相同（并列）时，`max` 稳定取先入列表者——即"来源"。"""
    entries = [
        _entry("arxiv", ("cs.AI",)),
        _entry("arxiv", ("cs.AI",)),
        _entry("ssrn", ("cs.LG",)),
        _entry("nber", ("cs.CL",)),
    ]
    report = build_overload_report("s", entries, guard_limit=2)

    assert report.by_source[0] == ("arxiv", 2)
    assert report.by_category[0] == ("cs.AI", 2)
    assert "来源" in report.suggestion
    assert "类目" not in report.suggestion.split("；建议")[0]  # 未被判为主建议轴


def test_build_overload_report_multi_label_category_counts_each_bucket() -> None:
    """一条目多个类目——design 语义"分布"，各类目桶各计一次（非论文数之和）。"""
    entries = [_entry("arxiv", ("cs.AI", "cs.LG")), _entry("arxiv", ("cs.AI",))]
    report = build_overload_report("s", entries, guard_limit=1)
    assert dict(report.by_category) == {"cs.AI": 2, "cs.LG": 1}


def test_build_overload_report_dedupes_repeated_category_within_one_entry() -> None:
    """P2#4 回归：单条目内重复标签只计一次，不应让份额超过 100%。

    `ReportEntry.categories` 无去重契约（源侧原始元组，如 arXiv 主分类与
    cross-list 可能同值）——条目内去重是 `_counts_by` 自身的职责，不是上游契约；
    跨条目的正常累计不受影响（见上一测试）。source 留空使 by_source 为空，
    让类目轴成为唯一候选，从而对份额文案做精确断言。
    """
    entries = [_entry("", ("cs.AI", "cs.AI"))]
    report = build_overload_report("s", entries, guard_limit=1)

    assert report.by_category == (("cs.AI", 1),)  # 而非 ("cs.AI", 2)
    assert report.new_count == 1
    assert "200%" not in report.suggestion
    assert "1/1 ≈ 100%" in report.suggestion


def test_build_overload_report_repeated_category_with_source_still_caps_at_total() -> None:
    """复现审查报告里的具体例子：单条目 categories=('cs.AI','cs.AI') + 正常来源。"""
    entries = [_entry("arxiv", ("cs.AI", "cs.AI"))]
    report = build_overload_report("s", entries, guard_limit=1)

    assert report.by_category == (("cs.AI", 1),)
    assert report.by_source == (("arxiv", 1),)
    assert "200%" not in report.suggestion


def test_build_overload_report_empty_source_skips_by_source_bucket() -> None:
    entries = [_entry("", ("cs.AI",))]
    report = build_overload_report("s", entries, guard_limit=0)
    assert report.by_source == ()
    assert report.by_category == (("cs.AI", 1),)
    assert "类目" in report.suggestion  # 唯一可用分布轴


def test_build_overload_report_no_distribution_falls_back_to_generic_advice() -> None:
    entries = [_entry("", ())]  # 无来源、无类目
    report = build_overload_report("s", entries, guard_limit=0)
    assert report.by_source == () and report.by_category == ()
    assert "调低 guard.max_new_per_run" in report.suggestion


def test_build_overload_report_empty_entries_has_zero_new_count_and_no_crash() -> None:
    report = build_overload_report("s", [], guard_limit=5)
    assert (report.new_count, report.by_source, report.by_category) == (0, (), ())
    assert report.suggestion  # 仍产出一句头部说明，不因除零崩溃
