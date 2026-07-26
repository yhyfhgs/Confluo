"""订阅域冻结件（`subs/types.py`）的结构与语义（Phase 6 T1 + Phase 7 T9；plan §2）。

这些类型是 T2-T6 的共同契约，测试的重点是**契约性质**而非实现细节：不可变、
`truncated` 由 `outcome` 单一决定、补偿谓词标记与 `LocalFilter` 字段名同源、
`pushdown` 的重复键语义。Phase 7 T9 增补：`PlanStep.predicate_params`（参数化谓词的
新接缝）+ arXiv 查询布尔式语法（`normalize_arxiv_query`/`wrap_arxiv_query`/
`parse_arxiv_query`，"参数化谓词签名"冻结件的语法层）。
"""

from __future__ import annotations

import dataclasses

import pytest

from paper_crawler.subs.model import SOURCE_FIELDS, LocalFilter
from paper_crawler.subs.types import (
    ARXIV_QUERY_FIELDS,
    DATE_WINDOW_PARAMS,
    LOCAL_PREDICATE_EXCLUDE_REGEX,
    LOCAL_PREDICATE_MIN_YEAR,
    LOCAL_PREDICATE_TITLE_REGEX_ANY,
    ArxivQueryAtom,
    ArxivQueryOp,
    CompiledPlan,
    FailureEvent,
    PlanStep,
    ReportEntry,
    RunSummary,
    WatchOutcome,
    is_source_scoped_predicate,
    normalize_arxiv_query,
    parse_arxiv_query,
    wrap_arxiv_query,
)


def test_local_predicate_constants_track_local_filter_fields() -> None:
    """谓词标记 == `LocalFilter` 字段名（集合等值自断言，防两处清单漂移）。"""
    constants = {
        LOCAL_PREDICATE_TITLE_REGEX_ANY,
        LOCAL_PREDICATE_EXCLUDE_REGEX,
        LOCAL_PREDICATE_MIN_YEAR,
    }
    assert constants == {f.name for f in dataclasses.fields(LocalFilter)}


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("ssrn.topic_filter", True),  # 唯一登记的源专属谓词（T2 产 / T3 收）
        ("arxiv.some_future_quirk", True),
        (LOCAL_PREDICATE_TITLE_REGEX_ANY, False),
        (LOCAL_PREDICATE_EXCLUDE_REGEX, False),
        (LOCAL_PREDICATE_MIN_YEAR, False),
        ("title_regex_any[0]", False),  # T3 的命中记录形态，不含点 → 不误判
        (".leading", False),  # 两侧必须非空，半截名不算
        ("trailing.", False),
        ("", False),
    ],
)
def test_is_source_scoped_predicate_discriminates_dotted_names(name: str, expected: bool) -> None:
    """分流契约的单一同源判别式（T2 产 / T3 收 / T5 分流，三方不各写一份 `"." in`）。"""
    assert is_source_scoped_predicate(name) is expected


def test_local_predicate_constants_are_never_source_scoped() -> None:
    """通用谓词与源专属谓词天然不重叠（判别式对全部通用标记恒 False）。"""
    for constant in (
        LOCAL_PREDICATE_TITLE_REGEX_ANY,
        LOCAL_PREDICATE_EXCLUDE_REGEX,
        LOCAL_PREDICATE_MIN_YEAR,
    ):
        assert not is_source_scoped_predicate(constant)


def test_date_window_params_cover_exactly_the_dsl_source_set() -> None:
    """槽位名表与 DSL 源词表同集——表住叶子模块，T2/T4/T5 三方消费同一份。"""
    assert set(DATE_WINDOW_PARAMS) == set(SOURCE_FIELDS)


def test_date_window_params_re_exported_from_compile_is_the_same_object() -> None:
    """compile.py 保留 re-export：既有 `from ...compile import DATE_WINDOW_PARAMS` 不变。"""
    from paper_crawler.subs import compile as compile_module

    assert compile_module.DATE_WINDOW_PARAMS is DATE_WINDOW_PARAMS
    assert "DATE_WINDOW_PARAMS" in compile_module.__all__


def test_plan_step_defaults_and_params_view() -> None:
    step = PlanStep(source="arxiv")
    assert step.pushdown == () and step.local_predicates == () and step.note == ""
    assert step.predicate_params == ()  # Phase 7 T9 新增字段，缺省同样空元组
    assert step.as_params() == {}


def test_plan_step_predicate_params_is_independent_of_local_predicates() -> None:
    """`predicate_params`（Phase 7 T9）与 `local_predicates` 是两个独立字段——可以
    只设其一，互不干扰（`compile._compile_arxiv` 正是只设 `predicate_params` 那侧，
    刻意不让 `arxiv.query_bool` 混入 `local_predicates`，见其 docstring）。
    """
    step = PlanStep(
        source="arxiv",
        local_predicates=(LOCAL_PREDICATE_MIN_YEAR,),
        predicate_params=(("arxiv.query_bool", 'ti:"agent"'),),
    )
    assert step.local_predicates == (LOCAL_PREDICATE_MIN_YEAR,)
    assert step.predicate_params == (("arxiv.query_bool", 'ti:"agent"'),)


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


def test_plan_step_with_predicate_params_stays_hashable() -> None:
    """新字段同样是 tuple-of-tuples（frozen dataclass 需 hashable 的既有守法）。"""
    step = PlanStep(source="arxiv", predicate_params=(("arxiv.query_bool", 'ti:"agent"'),))
    assert hash(step) == hash(dataclasses.replace(step))  # 不炸即通过（值相等 → hash 相等）


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
    """dry-run 也可能"本会熔断"：两者正交，过载报告（`new_count`/`guard_limit`）照出。"""
    summary = RunSummary(
        subscription="s",
        started_at="2026-07-26T00:00:00+00:00",
        outcome=WatchOutcome.TRUNCATED,
        dry_run=True,
        new_count=500,
        guard_limit=200,
    )
    assert summary.truncated and summary.dry_run
    assert summary.new_count == 500 and summary.guard_limit == 200


@pytest.mark.parametrize(
    "kwargs",
    [
        {"ingested_count": 1},
        {"fetched_count": 1},
        {"ingested_count": 3, "fetched_count": 2},
    ],
    ids=["ingested_count", "fetched_count", "both"],
)
def test_dry_run_invariant_rejects_nonzero_ingest_or_fetch(kwargs: dict[str, int]) -> None:
    """P2#3：`dry_run=True` 时 `ingested_count`/`fetched_count` 必须为 0——违反即拒绝构造。

    此前 `test_dry_run_is_orthogonal_to_outcome` 断言 `ingested_count == 0` 是恒真式
    （从未尝试传非零值，无论不变量是否真的被强制都会通过）；这里直接构造违例并
    断言拒绝构造，才是对不变量本身的验证。
    """
    with pytest.raises(ValueError, match="dry_run"):
        RunSummary(subscription="s", started_at="t", dry_run=True, **kwargs)


def test_dry_run_false_allows_nonzero_ingest_and_fetch() -> None:
    """不变量只在 `dry_run=True` 时生效——正常运行路径的真实计数不受影响。"""
    summary = RunSummary(
        subscription="s", started_at="t", dry_run=False, ingested_count=5, fetched_count=2
    )
    assert summary.ingested_count == 5 and summary.fetched_count == 2


def test_run_summary_defaults_are_zeroed() -> None:
    summary = RunSummary(subscription="s", started_at="t")
    assert summary.outcome is WatchOutcome.OK
    assert summary.entries == () and summary.failures == ()
    assert (summary.seen_count, summary.new_count, summary.ingested_count) == (0, 0, 0)
    assert (summary.fetched_count, summary.library_total, summary.guard_limit) == (0, 0, 0)
    assert summary.report_path is None and summary.finished_at == ""
    assert summary.narrowing_hints == () and summary.distribution == ()


def test_run_summary_carries_distribution_as_axis_label_count_triples() -> None:
    """`distribution` 是 `(axis, label, count)` 三元组（T3/T6 接缝终裁，AC-6.2 判据承载）：
    T5 从 `subs.guard.OverloadReport` 的 `by_source`/`by_category` 两轴分布各自打上
    axis 标签后拼装成一个扁平序列；T6 渲染日报时按 `axis` 过滤拆回两张表。
    """
    summary = RunSummary(
        subscription="s",
        started_at="t",
        distribution=(
            ("source", "arxiv", 120),
            ("source", "ssrn", 30),
            ("category", "cs.AI", 90),
        ),
    )
    assert summary.distribution == (
        ("source", "arxiv", 120),
        ("source", "ssrn", 30),
        ("category", "cs.AI", 90),
    )
    # axis 取值域仅 docstring 约定、非类型系统强制——冒烟一下字面量本身没有第三个轴。
    axes = {axis for axis, _label, _count in summary.distribution}
    assert axes <= {"source", "category"}


def test_run_summary_narrowing_hints_reserved_for_future_use() -> None:
    """`narrowing_hints` 现阶段 T5 恒留空——收窄句改由 T6 直接从 `distribution` 的
    计数现算（算法思路同 `subs.guard._suggest_narrowing`），不经 T5 预先算好传递。
    字段类型未变，仍可被显式赋值（保留作未来面，非被禁用）。
    """
    summary = RunSummary(subscription="s", started_at="t")
    assert summary.narrowing_hints == ()  # T5 现阶段的实际产出

    reserved = RunSummary(subscription="s", started_at="t", narrowing_hints=("未来面占位提示",))
    assert reserved.narrowing_hints == ("未来面占位提示",)


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


# --- arXiv 查询布尔式语法（Phase 7 T9；plan §4 T9"参数化谓词签名"冻结件）--------
#
# 范围=ti/abs 字段 + AND/OR/ANDNOT + 引号短语/裸词，括号任意嵌套（决策⑤ YAGNI）。
# `compile.py`（归一/包裹）与 `filter.py`（求值）两侧的用例见各自测试文件；这里只
# 测叶子模块本身：`ARXIV_QUERY_FIELDS`、归一/包裹的独立行为、解析出的语法树形状、
# 各类语法错误的响亮报错。


def test_arxiv_query_fields_scope_is_exactly_title_and_abstract() -> None:
    """集合等值自断言：范围=现有 9 个 preset 实测覆盖面（决策⑤），防悄悄扩大/缩小。"""
    assert ARXIV_QUERY_FIELDS == {"ti", "abs"}


def test_normalize_arxiv_query_folds_whitespace_and_uppercases_operators() -> None:
    assert normalize_arxiv_query('ti:"tool  use"   or\n  abs:"agentic"') == (
        'ti:"tool  use" OR abs:"agentic"'
    )


def test_normalize_arxiv_query_joins_and_not_into_andnot() -> None:
    assert normalize_arxiv_query('ti:"a" AND NOT ti:"b"') == 'ti:"a" ANDNOT ti:"b"'


def test_wrap_arxiv_query_wraps_compound_but_not_atoms() -> None:
    assert wrap_arxiv_query('ti:"a" OR ti:"b"') == '(ti:"a" OR ti:"b")'
    assert wrap_arxiv_query('ti:"already atomic"') == 'ti:"already atomic"'
    assert wrap_arxiv_query('(ti:"a" OR ti:"b")') == '(ti:"a" OR ti:"b")'  # 不重复包


def test_parse_arxiv_query_single_atom() -> None:
    assert parse_arxiv_query('ti:"agent"') == ArxivQueryAtom(field="ti", phrase="agent")


def test_parse_arxiv_query_accepts_unquoted_bareword_phrase() -> None:
    """语法允许裸词（无引号）——9 个 preset 现状不用，但语法本身支持（决策⑤范围含它）。"""
    assert parse_arxiv_query("ti:agent") == ArxivQueryAtom(field="ti", phrase="agent")


def test_parse_arxiv_query_or_chain_is_left_associative() -> None:
    tree = parse_arxiv_query('ti:"a" OR ti:"b" OR ti:"c"')
    assert tree == ArxivQueryOp(
        op="OR",
        left=ArxivQueryOp(
            op="OR",
            left=ArxivQueryAtom(field="ti", phrase="a"),
            right=ArxivQueryAtom(field="ti", phrase="b"),
        ),
        right=ArxivQueryAtom(field="ti", phrase="c"),
    )


def test_parse_arxiv_query_andnot_binds_tighter_than_or_without_parens() -> None:
    """无括号消歧时 `AND`/`ANDNOT` 结合力强于 `OR`（标准约定，`ArxivQueryOp` docstring）。

    9 个 preset 现状恒显式加括号（不依赖此优先级），此处单独验证该规则本身。
    """
    tree = parse_arxiv_query('ti:"a" OR ti:"b" ANDNOT ti:"c"')
    assert tree == ArxivQueryOp(
        op="OR",
        left=ArxivQueryAtom(field="ti", phrase="a"),
        right=ArxivQueryOp(
            op="ANDNOT",
            left=ArxivQueryAtom(field="ti", phrase="b"),
            right=ArxivQueryAtom(field="ti", phrase="c"),
        ),
    )


def test_parse_arxiv_query_parenthesized_group_then_andnot() -> None:
    """9 个 preset 的实际形态：`(A OR B OR C) ANDNOT D`。"""
    tree = parse_arxiv_query('(ti:"a" OR abs:"b") ANDNOT ti:"c"')
    assert tree == ArxivQueryOp(
        op="ANDNOT",
        left=ArxivQueryOp(
            op="OR",
            left=ArxivQueryAtom(field="ti", phrase="a"),
            right=ArxivQueryAtom(field="abs", phrase="b"),
        ),
        right=ArxivQueryAtom(field="ti", phrase="c"),
    )


def test_parse_arxiv_query_is_robust_to_raw_unnormalized_text() -> None:
    """传入**原始**（未归一）文本同样安全——内部先调用 `normalize_arxiv_query`。"""
    tree = parse_arxiv_query('ti:"a"   and \n not  ti:"b"')
    assert tree == ArxivQueryOp(
        op="ANDNOT",
        left=ArxivQueryAtom(field="ti", phrase="a"),
        right=ArxivQueryAtom(field="ti", phrase="b"),
    )


def test_parse_arxiv_query_ignores_the_optional_outer_wrap() -> None:
    """有无 `wrap_arxiv_query` 包的外括号，解析出的树完全相同——包裹只为可读/快照。"""
    assert parse_arxiv_query('ti:"a" OR ti:"b"') == parse_arxiv_query('(ti:"a" OR ti:"b")')


@pytest.mark.parametrize(
    ("text", "needle"),
    [
        ("", "为空"),
        ("   ", "为空"),
        ('au:"Smith"', "不支持的字段前缀"),
        ('cat:"cs.AI"', "不支持的字段前缀"),
        ('(ti:"a" OR ti:"b"', "提前结束"),  # 结尾处缺右括号——连"期望的 token"都没了
        ('(ti:"a" ti:"b")', "括号不配对"),  # 两原子间缺算子，"关闭符"位置读到别的 token
        ('ti:"a" OR ti:"b")', "残留片段"),
        ('ti:"a" OR', "提前结束"),
        ("agent", "缺少字段前缀"),
        ('ti:"a" ti:"b"', "残留片段"),  # 两个原子之间缺算子（顶层，无外括号兜底）
        ('"stray quote"', "无法识别的查询片段"),  # 引号前没有 field: 前缀，词法层面就认不出
        ('ti:""', "短语为空"),  # 空引号短语（field: 后紧跟一对空引号）
        ('(ti:"a" OR)', "期望字段原子"),  # OR 之后紧跟右括号——原子位置读到了算子/括号
        # 独立审查 P1-1：未闭合引号（无内部空白）此前被词法层的裸词兜底分支静默吞入
        # （首尾不成对 → 不剥引号 → phrase 残留字面量 `"` → 谓词对任何 stub 恒 False，
        # 上游 filter_papers 因此把整个源静默清零、零告警）。两例对照独立审查报告原文：
        ('ti:"agent', "未闭合或多余的引号"),  # 单原子内直接缺收尾引号
        ('ti:"a" OR abs:"b', "未闭合或多余的引号"),  # 前一原子完整，后一原子缺收尾引号
    ],
)
def test_parse_arxiv_query_rejects_invalid_syntax(text: str, needle: str) -> None:
    with pytest.raises(ValueError, match=needle):
        parse_arxiv_query(text)
