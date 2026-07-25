"""订阅域冻结件（`subs/types.py`）的结构与语义（Phase 6 T1；plan §2）。

这些类型是 T2-T6 的共同契约，测试的重点是**契约性质**而非实现细节：不可变、
`truncated` 由 `outcome` 单一决定、补偿谓词标记与 `LocalFilter` 字段名同源、
`pushdown` 的重复键语义。
"""

from __future__ import annotations

import dataclasses

import pytest

from paper_crawler.subs.model import LocalFilter
from paper_crawler.subs.types import (
    LOCAL_PREDICATE_EXCLUDE_REGEX,
    LOCAL_PREDICATE_MIN_YEAR,
    LOCAL_PREDICATE_TITLE_REGEX_ANY,
    CompiledPlan,
    FailureEvent,
    PlanStep,
    ReportEntry,
    RunSummary,
    WatchOutcome,
)


def test_local_predicate_constants_track_local_filter_fields() -> None:
    """谓词标记 == `LocalFilter` 字段名（集合等值自断言，防两处清单漂移）。"""
    constants = {
        LOCAL_PREDICATE_TITLE_REGEX_ANY,
        LOCAL_PREDICATE_EXCLUDE_REGEX,
        LOCAL_PREDICATE_MIN_YEAR,
    }
    assert constants == {f.name for f in dataclasses.fields(LocalFilter)}


def test_plan_step_defaults_and_params_view() -> None:
    step = PlanStep(source="arxiv")
    assert step.pushdown == () and step.local_predicates == () and step.note == ""
    assert step.as_params() == {}


def test_plan_step_pushdown_allows_repeated_keys() -> None:
    """URL 查询串允许重复键（OpenAlex 多个 `filter=`）——`pushdown` 保序保重复。"""
    step = PlanStep(
        source="openalex",
        pushdown=(("filter", "concepts.id:C1"), ("filter", "type:preprint")),
    )
    assert len(step.pushdown) == 2
    assert step.as_params() == {"filter": "type:preprint"}  # dict 视图取最后一个


def test_plan_step_is_frozen_and_hashable() -> None:
    step = PlanStep(source="nber", pushdown=(("program", "AP"),))
    assert {step, dataclasses.replace(step, source="nber")} == {step}  # hashable + 值语义
    with pytest.raises(dataclasses.FrozenInstanceError):
        step.source = "arxiv"  # type: ignore[misc]


def test_compiled_plan_lookup_and_predicate_union() -> None:
    plan = CompiledPlan(
        subscription="llm-agents",
        steps=(
            PlanStep(source="arxiv", local_predicates=(LOCAL_PREDICATE_MIN_YEAR,)),
            PlanStep(
                source="ssrn",
                local_predicates=(
                    LOCAL_PREDICATE_TITLE_REGEX_ANY,
                    LOCAL_PREDICATE_MIN_YEAR,  # 与 arxiv 重复 → 并集去重
                    "ssrn.topic_filter",  # 源专属补偿谓词
                ),
                note="ssrn 无关键词下推能力",
            ),
        ),
    )
    assert plan.step_for("ssrn") is plan.steps[1]
    assert plan.step_for("crossref") is None
    # 保序去重：首次出现序
    assert plan.all_local_predicates() == (
        LOCAL_PREDICATE_MIN_YEAR,
        LOCAL_PREDICATE_TITLE_REGEX_ANY,
        "ssrn.topic_filter",
    )


def test_empty_plan_has_no_predicates() -> None:
    assert CompiledPlan(subscription="empty").all_local_predicates() == ()


@pytest.mark.parametrize(
    ("outcome", "expected"),
    [
        (WatchOutcome.OK, False),
        (WatchOutcome.TRUNCATED, True),
        (WatchOutcome.FAILED, False),
    ],
)
def test_truncated_is_derived_from_outcome(outcome: WatchOutcome, expected: bool) -> None:
    """熔断标记无独立字段——单一真相源，杜绝 `outcome`/`truncated` 各说各话。"""
    summary = RunSummary(subscription="s", started_at="2026-07-26T00:00:00+00:00", outcome=outcome)
    assert summary.truncated is expected


def test_watch_outcome_values_are_stable_strings() -> None:
    """落库/落报告的字面量——改动即破坏历史记录可读性。"""
    assert [o.value for o in WatchOutcome] == ["ok", "truncated", "failed"]


def test_dry_run_is_orthogonal_to_outcome() -> None:
    """dry-run 也可能"本会熔断"：两者正交，过载报告照出、入库恒 0。"""
    summary = RunSummary(
        subscription="s",
        started_at="2026-07-26T00:00:00+00:00",
        outcome=WatchOutcome.TRUNCATED,
        dry_run=True,
        new_count=500,
        guard_limit=200,
    )
    assert summary.truncated and summary.dry_run and summary.ingested_count == 0


def test_run_summary_defaults_are_zeroed() -> None:
    summary = RunSummary(subscription="s", started_at="t")
    assert summary.outcome is WatchOutcome.OK
    assert summary.entries == () and summary.failures == ()
    assert (summary.seen_count, summary.new_count, summary.ingested_count) == (0, 0, 0)
    assert (summary.fetched_count, summary.library_total, summary.guard_limit) == (0, 0, 0)
    assert summary.report_path is None and summary.finished_at == ""


def test_report_entry_carries_daily_report_columns() -> None:
    """design/09 §6.3：标题/作者/链接/命中规则；§6.1 过载报告按分类分布。"""
    entry = ReportEntry(
        title="Agentic Tool Use",
        authors=("A. Author", "B. Author"),
        url="https://arxiv.org/abs/2401.00001",
        matched_rules=("title_regex_any[0]",),
        source="arxiv",
        categories=("cs.AI",),
        paper_id="01J0000000000000000000000",
    )
    assert entry.matched_rules == ("title_regex_any[0]",)
    with pytest.raises(dataclasses.FrozenInstanceError):
        entry.title = "改不了"  # type: ignore[misc]


def test_failure_event_shape() -> None:
    event = FailureEvent(source="ssrn", error_class="transient", message="连接超时")
    assert (event.source, event.error_class, event.message) == ("ssrn", "transient", "连接超时")
