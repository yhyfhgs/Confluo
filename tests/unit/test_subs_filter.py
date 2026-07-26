"""本地过滤器（Phase 6 T3 + Phase 7 T9；design/09 §2 `filters:` + §3 本地补偿）。

覆盖：`title_regex_any`/`exclude_regex`/`min_year` 正则命中矩阵（含 Unicode 标题、
无 title 的 meta、坏输入）；`exclude_regex` 永不出现在 `matched_rules`；源专属谓词
注册表（ssrn `topic_filter` + arxiv `query_bool`，构造器形态）+ 未登记谓词 fail-loud
（含空输入流也报错）。
"""

from __future__ import annotations

import dataclasses
import logging

import pytest

from paper_crawler.subs.filter import (
    ARXIV_QUERY_BOOL,
    PREDICATE_REGISTRY,
    SSRN_TOPIC_FILTER,
    FilteredPaper,
    apply_predicate,
    build_predicate,
    filter_papers,
    reset_predicate_warnings,
)
from paper_crawler.subs.model import LocalFilter
from paper_crawler.types import PaperStub


def _stub(
    title: str,
    *,
    year: int | None = 2024,
    meta: tuple[tuple[str, str], ...] = (),
    abstract: str | None = None,
) -> PaperStub:
    return PaperStub(
        title=title, identifiers=(("doi", "10.1/x"),), year=year, meta=meta, abstract=abstract
    )


# --- 正则命中矩阵（≥10 例，含 Unicode/无 title/坏输入）------------------------


@pytest.mark.parametrize(
    ("title", "year", "filters", "expect_kept", "expect_rules"),
    [
        # 1. title_regex_any 单模式命中，大小写不敏感（模式小写，标题含大写 "Agentic"）。
        (
            "Agentic Tool Use in LLMs",
            2024,
            LocalFilter(title_regex_any=("agent",)),
            True,
            ("title_regex_any[0]",),
        ),
        # 2. title_regex_any 多模式，仅第二个命中。
        (
            "A Survey of Diffusion Models",
            2024,
            LocalFilter(title_regex_any=("agent", "diffusion")),
            True,
            ("title_regex_any[1]",),
        ),
        # 3. title_regex_any 多模式，两个都命中 → matched_rules 列出全部索引（升序）。
        (
            "Agentic Diffusion Agents",
            2024,
            LocalFilter(title_regex_any=("agent", "diffusion")),
            True,
            ("title_regex_any[0]", "title_regex_any[1]"),
        ),
        # 4. title_regex_any 声明但无一命中 → 剔除。
        (
            "Quantum Computing Basics",
            2024,
            LocalFilter(title_regex_any=("agent",)),
            False,
            None,
        ),
        # 5. title_regex_any 未声明（空）→ 无条件通过，不产标记。
        ("Anything Goes", 2024, LocalFilter(), True, ()),
        # 6. exclude_regex 命中 → 剔除，即使同时命中 title_regex_any。
        (
            "Agentic Quantum Survey",
            2024,
            LocalFilter(title_regex_any=("agent",), exclude_regex=("quantum",)),
            False,
            None,
        ),
        # 7. exclude_regex 声明但未命中 → 放行；exclude_regex 本身永不进 matched_rules。
        (
            "Agentic Tool Use",
            2024,
            LocalFilter(title_regex_any=("agent",), exclude_regex=("quantum",)),
            True,
            ("title_regex_any[0]",),
        ),
        # 8. min_year 边界：恰好等于阈值 → 通过（design/09 §6.1 语义：不熔断同类"含边界"）。
        ("Old But Eligible Paper", 2024, LocalFilter(min_year=2024), True, ("min_year",)),
        # 9. min_year 边界：低于阈值一年 → 剔除。
        ("Too Old Paper", 2023, LocalFilter(min_year=2024), False, None),
        # 10. min_year 声明但年份未知（None）→ 剔除（不可确认者不纳，同 ssrn topic_field 先例）。
        ("Year Unknown Paper", None, LocalFilter(min_year=2024), False, None),
        # 11. min_year 未声明 + 年份未知 → 无约束，通过。
        ("No Year No Constraint", None, LocalFilter(), True, ()),
        # 12. Unicode 标题：重音字符大小写不敏感（É ↔ é）。
        (
            "ÉCONOMIE et Finance Recherche",
            2024,
            LocalFilter(title_regex_any=("économie",)),
            True,
            ("title_regex_any[0]",),
        ),
        # 13. Unicode 标题：CJK 子串精确匹配（非拉丁文字，验证不因编码问题崩溃/漏判）。
        (
            "深度学习中的智能体研究",
            2024,
            LocalFilter(title_regex_any=("智能体",)),
            True,
            ("title_regex_any[0]",),
        ),
        # 14. 无 title 的 meta（空字符串）+ title_regex_any 声明 → 空标题不可能命中，剔除。
        ("", 2024, LocalFilter(title_regex_any=("agent",)), False, None),
        # 15. 无 title 的 meta（空字符串）+ 无过滤条件 → 通过，不崩溃。
        ("", 2024, LocalFilter(), True, ()),
        # 16. 坏输入：year 越界（0，非正常论文年份）仍按普通整数比较，不崩溃。
        ("Weird Year Paper", 0, LocalFilter(min_year=2024), False, None),
    ],
)
def test_regex_and_year_matrix(
    title: str,
    year: int | None,
    filters: LocalFilter,
    expect_kept: bool,
    expect_rules: tuple[str, ...] | None,
) -> None:
    stub = _stub(title, year=year)
    result = filter_papers([stub], filters)
    if expect_kept:
        assert len(result) == 1
        assert result[0].stub is stub  # 原对象直接透传，不复制/不修改
        assert result[0].matched_rules == expect_rules
    else:
        assert result == []


def test_exclude_regex_constant_never_appears_in_matched_rules() -> None:
    """`exclude_regex` 命中即剔除、不可能留在返回值里——故常量永不出现在 matched_rules。"""
    stub = _stub("Agentic but Quantum Survey")
    result = filter_papers(
        [stub], LocalFilter(title_regex_any=("agent",), exclude_regex=("survey",))
    )
    assert result == []  # 命中 exclude 被剔除
    # 换一个不命中 exclude 的近似标题，确认 matched_rules 里绝不会出现 exclude_regex 字样。
    kept = filter_papers(
        [_stub("Agentic Tool Use")],
        LocalFilter(title_regex_any=("agent",), exclude_regex=("survey",)),
    )
    assert all("exclude_regex" not in rule for rule in kept[0].matched_rules)


def test_preserves_input_order_across_multiple_stubs() -> None:
    stubs = [_stub("Agent One"), _stub("Unrelated"), _stub("Agent Two")]
    result = filter_papers(stubs, LocalFilter(title_regex_any=("agent",)))
    assert [f.stub.title for f in result] == ["Agent One", "Agent Two"]


def test_empty_filters_pass_everything_with_empty_matched_rules() -> None:
    stubs = [_stub("Paper A"), _stub("Paper B", year=None)]
    result = filter_papers(stubs, LocalFilter())
    assert [f.matched_rules for f in result] == [(), ()]
    assert len(result) == 2


# --- 谓词注册表（源专属本地补偿）--------------------------------------------


def test_registry_contains_exactly_ssrn_and_arxiv_predicates() -> None:
    """集合等值自断言：登记表内容与预期完全一致（防悄悄新增/漏登记漂移）。

    Phase 7 T9 新增 `ARXIV_QUERY_BOOL`——此前本断言只含 `SSRN_TOPIC_FILTER`。
    """
    assert set(PREDICATE_REGISTRY) == {SSRN_TOPIC_FILTER, ARXIV_QUERY_BOOL}


def test_apply_predicate_ssrn_topic_filter_true_for_econ_fin_field() -> None:
    stub = _stub(
        "Asset Pricing Paper", meta=(("openalex_field", "Economics, Econometrics and Finance"),)
    )
    assert apply_predicate(SSRN_TOPIC_FILTER, stub) is True


def test_apply_predicate_ssrn_topic_filter_passes_through_when_signal_missing(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """信号未接线（无 `openalex_field`）→ **放行** + 一次性 WARNING（T5 随卡小修）。

    与 `adapters.ssrn.parse.topic_field_matches(None) is False` 的原语语义刻意相反：
    那条路径上信号本该有，缺失即"不属于"；订阅域这条通道**整条 enrich 都还没接**，
    照原语会把整份 ssrn 订阅静默清零（模块 docstring "信号缺失时的兜底"段）。
    """
    reset_predicate_warnings()
    stub = _stub("Unrelated Engineering Paper")  # 无 openalex_field meta

    with caplog.at_level(logging.WARNING, logger="paper_crawler"):
        assert apply_predicate(SSRN_TOPIC_FILTER, stub) is True
        # 第二条同样放行，但提示只出一次（"每 run 每源一条"，不逐条刷屏）。
        assert apply_predicate(SSRN_TOPIC_FILTER, _stub("Another")) is True

    warnings = [r for r in caplog.records if SSRN_TOPIC_FILTER in r.getMessage()]
    assert len(warnings) == 1
    assert "LocalFilter-only" in warnings[0].getMessage()


def test_apply_predicate_ssrn_topic_filter_still_judges_when_signal_present(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """有信号就照走 `topic_field_matches`——兜底只在"缺信号"这一格生效，不改判定语义。"""
    reset_predicate_warnings()
    econ = _stub("WP", meta=(("openalex_field", "Economics, Econometrics and Finance"),))
    engineering = _stub("WP", meta=(("openalex_field", "Engineering"),))

    with caplog.at_level(logging.WARNING, logger="paper_crawler"):
        assert apply_predicate(SSRN_TOPIC_FILTER, econ) is True
        assert apply_predicate(SSRN_TOPIC_FILTER, engineering) is False

    assert [r for r in caplog.records if SSRN_TOPIC_FILTER in r.getMessage()] == []


def test_apply_predicate_ssrn_topic_filter_false_for_other_field() -> None:
    stub = _stub("Engineering Paper", meta=(("openalex_field", "Engineering"),))
    assert apply_predicate(SSRN_TOPIC_FILTER, stub) is False


def test_build_predicate_ssrn_topic_filter_ignores_param() -> None:
    """`ssrn.topic_filter` 的构造器忽略 `param`——判定完全来自 `stub.meta`。"""
    econ = _stub("WP", meta=(("openalex_field", "Economics, Econometrics and Finance"),))
    predicate = build_predicate(SSRN_TOPIC_FILTER, "any-ignored-value")
    assert predicate(econ) is True


def test_build_predicate_unknown_name_fails_loud() -> None:
    with pytest.raises(ValueError, match="未登记的本地补偿谓词"):
        build_predicate("bogus.thing", "x")


# --- arxiv.query_bool（构造器形态谓词，Phase 7 T9）---------------------------


def test_construct_arxiv_query_bool_blank_param_fails_loud() -> None:
    """构造器需要非空查询式参数——空串/纯空白视为接线错误，响亮拒绝。"""
    with pytest.raises(ValueError, match=ARXIV_QUERY_BOOL):
        build_predicate(ARXIV_QUERY_BOOL, "")
    with pytest.raises(ValueError, match=ARXIV_QUERY_BOOL):
        build_predicate(ARXIV_QUERY_BOOL, "   ")


def test_construct_arxiv_query_bool_unsupported_field_fails_loud() -> None:
    """构造时即解析查询式——不支持的字段前缀（范围外，决策⑤ YAGNI）响亮报错。"""
    with pytest.raises(ValueError, match="不支持的字段前缀"):
        build_predicate(ARXIV_QUERY_BOOL, 'au:"Smith"')


def test_construct_arxiv_query_bool_matches_title_field() -> None:
    predicate = build_predicate(ARXIV_QUERY_BOOL, 'ti:"agent"')
    assert predicate(_stub("Agentic Tool Use")) is True
    assert predicate(_stub("Quantum Computing Basics")) is False


def test_construct_arxiv_query_bool_matches_abstract_field() -> None:
    predicate = build_predicate(ARXIV_QUERY_BOOL, 'abs:"tool use"')
    assert predicate(_stub("Some Title", abstract="A paper about tool use in agents.")) is True
    assert predicate(_stub("Some Title", abstract="Unrelated abstract.")) is False


def test_construct_arxiv_query_bool_missing_abstract_field_is_false() -> None:
    """`abs:` 原子遇 `stub.abstract is None` → 判 False（无法确认时诚实剔除，同
    `min_year`/`ssrn.topic_filter` 的既有取舍）。
    """
    predicate = build_predicate(ARXIV_QUERY_BOOL, 'abs:"agentic"')
    assert predicate(_stub("Agentic Title", abstract=None)) is False


def test_construct_arxiv_query_bool_or_semantics() -> None:
    predicate = build_predicate(ARXIV_QUERY_BOOL, '(ti:"agent" OR ti:"llm")')
    assert predicate(_stub("Agentic Systems")) is True
    assert predicate(_stub("LLM Reasoning")) is True
    assert predicate(_stub("Unrelated Paper")) is False


def test_construct_arxiv_query_bool_andnot_semantics() -> None:
    predicate = build_predicate(ARXIV_QUERY_BOOL, '(ti:"agent" ANDNOT ti:"survey")')
    assert predicate(_stub("Agentic Tool Use")) is True
    assert predicate(_stub("A Survey of Agentic Systems")) is False


def test_construct_arxiv_query_bool_and_semantics() -> None:
    """`AND`（非 `ANDNOT`）语义：语法支持但 9 个 preset 现状不用（决策⑤范围仍含它）。"""
    predicate = build_predicate(ARXIV_QUERY_BOOL, '(ti:"agent" AND abs:"tool")')
    assert predicate(_stub("Agentic Systems", abstract="uses a tool")) is True
    assert predicate(_stub("Agentic Systems", abstract="no such thing")) is False


def test_construct_arxiv_query_bool_case_insensitive_matching() -> None:
    """标题/短语大小写不敏感（同 `title_regex_any`/`exclude_regex` 的既有约定）。"""
    predicate = build_predicate(ARXIV_QUERY_BOOL, 'ti:"AGENT"')
    assert predicate(_stub("agentic tool use")) is True


def test_apply_predicate_arxiv_query_bool_with_param_kwarg() -> None:
    stub = _stub("Agentic Tool Use")
    assert apply_predicate(ARXIV_QUERY_BOOL, stub, param='ti:"agent"') is True
    assert apply_predicate(ARXIV_QUERY_BOOL, stub, param='ti:"quantum"') is False


def test_filter_papers_wires_predicate_params_to_arxiv_query_bool() -> None:
    """端到端：`filter_papers(extra_predicates=..., predicate_params=...)` 正确
    构造并应用 `arxiv.query_bool`——模拟未来 watch.py 集成会怎样驱动这条新接缝
    （本卡不改 watch.py，但机制本身在此完整验证）。
    """
    hit = _stub("Agentic Tool Use")
    miss = _stub("Quantum Computing Basics")
    result = filter_papers(
        [hit, miss],
        LocalFilter(),
        extra_predicates=(ARXIV_QUERY_BOOL,),
        predicate_params={ARXIV_QUERY_BOOL: '(ti:"agent" OR ti:"tool")'},
    )
    assert [f.stub.title for f in result] == ["Agentic Tool Use"]
    assert result[0].matched_rules == (ARXIV_QUERY_BOOL,)


def test_filter_papers_arxiv_query_bool_without_predicate_params_fails_loud() -> None:
    """未提供 `predicate_params` 时该谓词取空参数 → 构造器响亮报错（不静默放行/
    误判）——这正是 `compile._compile_arxiv` docstring 里"不能把这条标记混进
    `local_predicates`"的理由：现有 `watch.py` 调用点不传 `predicate_params`。
    """
    with pytest.raises(ValueError, match=ARXIV_QUERY_BOOL):
        filter_papers(
            [_stub("Agentic Tool Use")], LocalFilter(), extra_predicates=(ARXIV_QUERY_BOOL,)
        )


def test_filter_papers_constructs_each_predicate_only_once_per_call() -> None:
    """效率契约：谓词只在遍历 `stubs` **之前**构造一次（尤其 `arxiv.query_bool` 的
    语法树解析），不随 `stubs` 数量重复——多篇论文共用同一个已解析的树。
    """
    calls: list[str] = []
    original = PREDICATE_REGISTRY[ARXIV_QUERY_BOOL]

    def _counting_constructor(param: str) -> object:
        calls.append(param)
        return original(param)

    PREDICATE_REGISTRY[ARXIV_QUERY_BOOL] = _counting_constructor  # type: ignore[assignment]
    try:
        stubs = [_stub("Agentic A"), _stub("Agentic B"), _stub("Agentic C")]
        filter_papers(
            stubs,
            LocalFilter(),
            extra_predicates=(ARXIV_QUERY_BOOL,),
            predicate_params={ARXIV_QUERY_BOOL: 'ti:"agent"'},
        )
    finally:
        PREDICATE_REGISTRY[ARXIV_QUERY_BOOL] = original
    assert calls == ['ti:"agent"']  # 恰好一次，不是每 stub 一次


def test_apply_predicate_unknown_name_fails_loud() -> None:
    stub = _stub("Anything")
    with pytest.raises(ValueError, match="未登记的本地补偿谓词"):
        apply_predicate("bogus.thing", stub)


def test_filter_papers_unknown_extra_predicate_fails_loud_even_with_empty_stream() -> None:
    """fail-loud 校验在遍历 stubs 之前完成——空输入流也必须暴露接线错误。"""
    with pytest.raises(ValueError, match="bogus"):
        filter_papers([], LocalFilter(), extra_predicates=("bogus.thing",))


def test_filter_papers_applies_ssrn_topic_filter_extra_predicate() -> None:
    econ = _stub(
        "Asset Pricing WP", meta=(("openalex_field", "Economics, Econometrics and Finance"),)
    )
    engineering = _stub("Robotics WP", meta=(("openalex_field", "Engineering"),))
    result = filter_papers(
        [econ, engineering], LocalFilter(), extra_predicates=(SSRN_TOPIC_FILTER,)
    )
    assert [f.stub.title for f in result] == ["Asset Pricing WP"]
    assert result[0].matched_rules == (SSRN_TOPIC_FILTER,)


def test_filter_papers_combines_generic_filters_and_extra_predicate() -> None:
    """generic title_regex_any + 源专属谓词同时生效——两者的标记都进 matched_rules。"""
    hit = _stub(
        "Agentic Asset Pricing", meta=(("openalex_field", "Economics, Econometrics and Finance"),)
    )
    wrong_field = _stub("Agentic Robotics", meta=(("openalex_field", "Engineering"),))
    wrong_title = _stub(
        "Unrelated Survey", meta=(("openalex_field", "Economics, Econometrics and Finance"),)
    )
    result = filter_papers(
        [hit, wrong_field, wrong_title],
        LocalFilter(title_regex_any=("agent",)),
        extra_predicates=(SSRN_TOPIC_FILTER,),
    )
    assert [f.stub.title for f in result] == ["Agentic Asset Pricing"]
    assert result[0].matched_rules == ("title_regex_any[0]", SSRN_TOPIC_FILTER)


def test_filtered_paper_is_frozen() -> None:
    entry = FilteredPaper(stub=_stub("X"), matched_rules=("title_regex_any[0]",))
    with pytest.raises(dataclasses.FrozenInstanceError):
        entry.matched_rules = ()  # type: ignore[misc]
