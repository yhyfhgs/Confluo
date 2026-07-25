"""查询编译器（Phase 6 T2；`subs/compile.py`，design/09 §3 能力映射表）。

四块：
1. **每源用例表 ≥6 例**——含边界：空 query / 多值（重复键）/ NOT / 该源未声明该字段；
2. **ssrn `topic_filter` 接线**（检查单 #10）——从**真实** `venues/econ/ssrn.yaml` 读入，
   落 `PlanStep.local_predicates`；venue 缺声明 / 取值非法两侧都有专测；
3. **接缝纪律**——编译产物**不含任何日期窗**（那是 T4 的槽位，plan §4 T2 接缝裁决①），
   注册表与 `SOURCE_FIELDS` 集合等值自断言；
4. **双示例快照**——design/09 §2 的 llm-agents / asset-pricing-wp 编译结果按
   `(source, pushdown, local_predicates)` 三元组逐字锁定（`note` 按冻结件定义"不参与判定"，
   故只做关键词 spot-check，不进快照——否则改一句措辞就要动快照，快照会退化成噪声）。
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from helpers import make_ssrn_venue
from paper_crawler.errors import CrawlerError, ErrorClass, SubscriptionInvalid
from paper_crawler.subs.compile import (
    DATE_WINDOW_PARAMS,
    PREDICATE_OPENALEX_CONCEPTS,
    PREDICATE_SSRN_TOPIC_FILTER,
    SUPPORTED_SOURCES,
    compile_subscription,
    local_predicates_of,
)
from paper_crawler.subs.model import (
    SOURCE_FIELDS,
    LocalFilter,
    SourceSelector,
    Subscription,
    load_subscription_file,
    parse_subscription,
)
from paper_crawler.subs.types import (
    LOCAL_PREDICATE_EXCLUDE_REGEX,
    LOCAL_PREDICATE_MIN_YEAR,
    LOCAL_PREDICATE_TITLE_REGEX_ANY,
    PlanStep,
)
from paper_crawler.types import VenueSpec

_TESTS_ROOT = Path(__file__).resolve().parents[1]
_FIXTURES = _TESTS_ROOT / "fixtures" / "subs"
_REPO_VENUES_DIR = _TESTS_ROOT.parent / "venues"


def _step(
    source: str, selector_fields: dict[str, object], *, filters: LocalFilter | None = None
) -> PlanStep:
    """编译单源选择器 → 该源的 `PlanStep`（不带 venue；ssrn 专用重载见 `_ssrn_step`）。"""
    subscription = Subscription(
        name="probe",
        sources=(SourceSelector(source=source, **selector_fields),),  # type: ignore[arg-type]
        filters=filters or LocalFilter(),
    )
    step = compile_subscription(subscription).step_for(source)
    assert step is not None
    return step


def _ssrn_step(selector_fields: dict[str, object], venue: VenueSpec | None) -> PlanStep:
    subscription = Subscription(
        name="probe",
        sources=(SourceSelector(source="ssrn", **selector_fields),),  # type: ignore[arg-type]
    )
    venues = {"ssrn": venue} if venue is not None else None
    step = compile_subscription(subscription, venues=venues).step_for("ssrn")
    assert step is not None
    return step


def _search_query(**selector_fields: object) -> str:
    step = _step("arxiv", dict(selector_fields))
    return step.as_params()["search_query"]


# --- arxiv：categories + query → 单个 search_query（完整下推）------------------


def test_arxiv_multi_categories_form_or_group() -> None:
    """多值分类 → `cat:` OR 组，整体加括号（后续与 query 用 AND 拼时优先级才正确）。"""
    assert _search_query(categories=("cs.AI", "cs.LG", "cs.CL")) == (
        "(cat:cs.AI OR cat:cs.LG OR cat:cs.CL)"
    )


def test_arxiv_single_category_needs_no_parentheses() -> None:
    """单值是"原子"——不加括号（噪声括号会让 search_query 难读且快照易漂）。"""
    assert _search_query(categories=("q-fin.PR",)) == "cat:q-fin.PR"


def test_arxiv_query_only_is_pushed_down_verbatim() -> None:
    """未声明 categories（边界：空分类）→ search_query 就是归一后的查询式本身。"""
    assert _search_query(query='ti:"agent"') == 'ti:"agent"'


def test_arxiv_categories_and_query_join_with_and() -> None:
    assert _search_query(categories=("cs.AI", "cs.MA"), query='abs:"tool use" OR ti:"agent"') == (
        '(cat:cs.AI OR cat:cs.MA) AND (abs:"tool use" OR ti:"agent")'
    )


def test_arxiv_and_not_is_normalized_to_andnot() -> None:
    """边界 NOT：design/09 §2 写 `AND NOT`，arXiv 实测操作符是 `ANDNOT`（site-survey）。

    不归一的话 `NOT` 会被当成检索词——结果集静默变样，正是编译器该挡住的失真。
    """
    assert _search_query(query='ti:"agent" AND NOT ti:"survey"') == (
        '(ti:"agent" ANDNOT ti:"survey")'
    )


def test_arxiv_folded_yaml_whitespace_is_collapsed() -> None:
    """YAML 折叠标量折出的换行/连续空格 → 单空格（引号内的空格不动）。"""
    assert _search_query(query='ti:"tool  use"   OR\n  abs:"agentic"') == (
        '(ti:"tool  use" OR abs:"agentic")'
    )


def test_arxiv_lowercase_operators_are_uppercased_outside_quotes() -> None:
    """裸 `and`/`or` 大写化（arXiv 操作符须大写）；引号内的同名词是检索词，绝不动。"""
    assert _search_query(query='ti:"cats and dogs" or abs:"agentic" and not ti:"survey"') == (
        '(ti:"cats and dogs" OR abs:"agentic" ANDNOT ti:"survey")'
    )


def test_arxiv_compound_expression_is_parenthesized_for_safe_appending() -> None:
    """复合式恒带外层括号——T4 的 `AND submittedDate:[…]` 是**追加**在末尾的。

    少了这层括号，`cat:a OR cat:b AND <日期窗>` 会被 arXiv 读成
    `cat:a OR (cat:b AND 日期窗)`：第一个分类悄悄逃出增量窗，正是"边界丢失"那类难查的错。
    """
    assert _search_query(categories=("cs.AI", "cs.LG")) == "(cat:cs.AI OR cat:cs.LG)"


def test_arxiv_already_wrapped_query_is_not_double_wrapped() -> None:
    assert _search_query(categories=("cs.AI",), query='(ti:"a" OR ti:"b")') == (
        'cat:cs.AI AND (ti:"a" OR ti:"b")'
    )


def test_arxiv_unbalanced_parentheses_are_left_alone() -> None:
    """括号不配对 = 用户写错：编译器不猜、不补（只按常规加自己的那层），交 arXiv 明确报错。"""
    assert _search_query(categories=("cs.AI",), query='((ti:"a" OR ti:"b")') == (
        'cat:cs.AI AND (((ti:"a" OR ti:"b"))'
    )


def test_arxiv_empty_selector_yields_no_pushdown() -> None:
    """兜底：绕过解析器直构的空选择器不产 `search_query=`（空查询串会拉回全站）。"""
    assert _step("arxiv", {}).pushdown == ()


# --- crossref：issns → 每刊一条（期刊 watch 通道）-----------------------------


def test_crossref_single_issn() -> None:
    assert _step("crossref", {"issns": ("0033-5533",)}).pushdown == (("issn", "0033-5533"),)


def test_crossref_multiple_issns_keep_repeated_keys_in_order() -> None:
    """多值边界：ISSN 在 `/journals/{issn}/works` 的 path 里，一次一刊 → 重复键条目。"""
    step = _step("crossref", {"issns": ("0033-5533", "0012-9682", "0004-3702")})
    assert step.pushdown == (
        ("issn", "0033-5533"),
        ("issn", "0012-9682"),
        ("issn", "0004-3702"),
    )


def test_crossref_dict_view_collapses_repeated_keys() -> None:
    """`as_params()` 是"最后一个胜出"的 dict 视图——多 ISSN 场景必须用 `pushdown` 本身。"""
    step = _step("crossref", {"issns": ("0033-5533", "0012-9682")})
    assert step.as_params() == {"issn": "0012-9682"}


def test_crossref_without_filters_has_no_local_compensation() -> None:
    """无关键词场景（design/09 §3 判词"完整下推"）：不声明 filters 即零补偿。"""
    assert _step("crossref", {"issns": ("0033-5533",)}).local_predicates == ()


def test_crossref_filters_still_compensate_locally() -> None:
    step = _step(
        "crossref",
        {"issns": ("0033-5533",)},
        filters=LocalFilter(exclude_regex=("erratum",), min_year=2024),
    )
    assert step.local_predicates == (LOCAL_PREDICATE_EXCLUDE_REGEX, LOCAL_PREDICATE_MIN_YEAR)


def test_crossref_empty_selector_yields_no_pushdown() -> None:
    assert _step("crossref", {}).pushdown == ()


def test_crossref_note_points_at_the_date_window_seam() -> None:
    assert "from-pub-date" in _step("crossref", {"issns": ("0033-5533",)}).note


# --- openalex：concepts + from_source_types → filter 轴 -----------------------


def test_openalex_concept_ids_are_pushed_down_as_or_group() -> None:
    step = _step("openalex", {"concepts": ("C41008148", "C154945302")})
    assert step.pushdown == (("filter", "concepts.id:C41008148|C154945302"),)
    assert step.local_predicates == ()


def test_openalex_concept_entity_url_is_normalized_to_short_id() -> None:
    step = _step("openalex", {"concepts": ("https://openalex.org/C41008148",)})
    assert step.pushdown == (("filter", "concepts.id:C41008148"),)


def test_openalex_concept_names_fall_back_to_local_compensation() -> None:
    """名称型概念无离线 id 解析路径 → 不臆造下推，记本地补偿并把名称写进 note。"""
    step = _step("openalex", {"concepts": ("large language model",)})
    assert step.pushdown == ()
    assert step.local_predicates == (PREDICATE_OPENALEX_CONCEPTS,)
    assert "large language model" in step.note


def test_openalex_mixed_ids_and_names_split_by_form() -> None:
    step = _step("openalex", {"concepts": ("C41008148", "large language model")})
    assert step.pushdown == (("filter", "concepts.id:C41008148"),)
    assert step.local_predicates == (PREDICATE_OPENALEX_CONCEPTS,)


def test_openalex_source_types_become_type_filter() -> None:
    """多值边界：同一 filter 轴内多值用 `|` 表 OR。"""
    step = _step("openalex", {"from_source_types": ("preprint", "article")})
    assert step.pushdown == (("filter", "type:preprint|article"),)


def test_openalex_two_axes_emit_two_filter_entries_in_field_order() -> None:
    """两轴同时声明 → 两条 `filter` 重复键条目，顺序 = `SOURCE_FIELDS` 字段序。"""
    step = _step("openalex", {"concepts": ("C41008148",), "from_source_types": ("preprint",)})
    assert step.pushdown == (
        ("filter", "concepts.id:C41008148"),
        ("filter", "type:preprint"),
    )
    assert [key for key, _ in step.pushdown] == ["filter", "filter"]


def test_openalex_empty_selector_yields_no_pushdown_and_no_concept_predicate() -> None:
    step = _step("openalex", {})
    assert step.pushdown == () and step.local_predicates == ()


# --- s2：venues / fields_of_study / query → bulk search 参数 ------------------


def test_s2_venues_are_comma_joined() -> None:
    step = _step("s2", {"venues": ("NeurIPS", "ICML")})
    assert step.pushdown == (("venue", "NeurIPS,ICML"),)


def test_s2_fields_of_study_are_comma_joined() -> None:
    step = _step("s2", {"fields_of_study": ("Economics", "Computer Science")})
    assert step.pushdown == (("fieldsOfStudy", "Economics,Computer Science"),)


def test_s2_query_whitespace_is_collapsed() -> None:
    step = _step("s2", {"query": "large  language\n  models"})
    assert step.pushdown == (("query", "large language models"),)


def test_s2_all_axes_follow_source_fields_order() -> None:
    step = _step(
        "s2",
        {"venues": ("NeurIPS",), "fields_of_study": ("Computer Science",), "query": "agents"},
    )
    assert step.pushdown == (
        ("venue", "NeurIPS"),
        ("fieldsOfStudy", "Computer Science"),
        ("query", "agents"),
    )


def test_s2_without_query_emits_no_query_param() -> None:
    """空 query 边界：bulk search 允许纯过滤检索，不该塞一个空 `query=`。"""
    step = _step("s2", {"venues": ("NeurIPS",)})
    assert "query" not in step.as_params()


def test_s2_empty_selector_yields_no_pushdown() -> None:
    assert _step("s2", {}).pushdown == ()


def test_s2_note_flags_fuzzy_venue_matching() -> None:
    """venue 是模糊名匹配而非 id 精确（site-survey）——如实标注，不假装精确。"""
    assert "模糊名" in _step("s2", {"venues": ("NeurIPS",)}).note


# --- nber：programs → 每 program 一条（feed 路由归 T7）------------------------


def test_nber_single_program() -> None:
    assert _step("nber", {"programs": ("AP",)}).pushdown == (("program", "AP"),)


def test_nber_multiple_programs_keep_repeated_keys_in_order() -> None:
    step = _step("nber", {"programs": ("AP", "CF", "ME")})
    assert step.pushdown == (("program", "AP"), ("program", "CF"), ("program", "ME"))


def test_nber_program_code_is_kept_verbatim() -> None:
    """大小写归一与 19 feed 映射表都在 T7——两处各存一份必然漂移。"""
    assert _step("nber", {"programs": ("cf",)}).pushdown == (("program", "cf"),)


def test_nber_empty_selector_yields_no_pushdown() -> None:
    assert _step("nber", {}).pushdown == ()


def test_nber_local_predicates_are_filters_only() -> None:
    step = _step(
        "nber", {"programs": ("AP",)}, filters=LocalFilter(title_regex_any=("asset pricing",))
    )
    assert step.local_predicates == (LOCAL_PREDICATE_TITLE_REGEX_ANY,)


def test_nber_note_hands_feed_routing_to_t7() -> None:
    assert "T7" in _step("nber", {"programs": ("AP",)}).note


def test_nber_has_no_date_window_slot() -> None:
    """NBER 增量走 RSS id 集合差分（design/09 §5）——没有日期参数可注入。"""
    assert DATE_WINDOW_PARAMS["nber"] == ()


# --- ssrn：零下推 + quirks.topic_filter 接线（检查单 #10）---------------------


def _load_repo_ssrn_venue() -> VenueSpec:
    """从**仓库真实** `venues/econ/ssrn.yaml` 读 VenueSpec（DoD："从 venue YAML 读入"）。"""
    raw = yaml.safe_load((_REPO_VENUES_DIR / "econ" / "ssrn.yaml").read_text(encoding="utf-8"))
    return VenueSpec.model_validate(raw)


def test_ssrn_topic_filter_from_shipped_venue_yaml_enters_local_predicates() -> None:
    """检查单 #10 的正主：真实 venue YAML 的 `quirks.topic_filter` → `ssrn.topic_filter`。

    读真文件而非构造 fixture：这条接线的价值就在"venue 里写了、编译时真被读到"，
    用合成 venue 自证等于没测（Phase 2「合成假设是盲区源」教训）。
    """
    venue = _load_repo_ssrn_venue()
    assert venue.quirks["topic_filter"] == "econ_fin"

    step = _ssrn_step({"networks": ("FEN",)}, venue)
    assert step.local_predicates == (PREDICATE_SSRN_TOPIC_FILTER,)
    assert "econ_fin" in step.note


def test_ssrn_topic_filter_absent_when_venue_not_supplied() -> None:
    step = _ssrn_step({"networks": ("FEN",)}, None)
    assert step.local_predicates == ()
    assert "未声明 quirks.topic_filter" in step.note


def test_ssrn_topic_filter_absent_when_venue_declares_none() -> None:
    venue = make_ssrn_venue()
    venue.quirks.pop("topic_filter")
    assert _ssrn_step({"networks": ("FEN",)}, venue).local_predicates == ()


@pytest.mark.parametrize("bad", [123, "", "   ", ["econ_fin"]])
def test_ssrn_topic_filter_illegal_value_fails_loud_as_config(bad: object) -> None:
    """quirks 类型写错当场 CONFIG 报错——静默当"没声明"会让订阅悄悄少一层过滤。"""
    venue = make_ssrn_venue(topic_filter=bad)
    with pytest.raises(CrawlerError) as excinfo:
        _ssrn_step({"networks": ("FEN",)}, venue)
    assert excinfo.value.error_class is ErrorClass.CONFIG
    assert "topic_filter" in str(excinfo.value)


def test_ssrn_never_pushes_down_networks_or_ejournals() -> None:
    """聚合源无 network/eJournal 过滤维度（ssrn.md §3）→ 恒零下推参数。"""
    step = _ssrn_step(
        {"networks": ("FEN", "ERN"), "ejournals": ("Asset Pricing eJournal",)},
        make_ssrn_venue(),
    )
    assert step.pushdown == ()


def test_ssrn_declared_networks_and_ejournals_are_recorded_in_note() -> None:
    """下推不了也不能吞：声明意图进 note，日报/诊断里用户看得见"这是近似"。"""
    note = _ssrn_step(
        {"networks": ("FEN",), "ejournals": ("Asset Pricing eJournal",)}, make_ssrn_venue()
    ).note
    assert "networks=[FEN]" in note
    assert "ejournals=[Asset Pricing eJournal]" in note
    assert "非真实子网成员籍" in note


def test_ssrn_ejournals_only_is_recorded_without_networks_clause() -> None:
    note = _ssrn_step({"ejournals": ("Capital Markets eJournal",)}, make_ssrn_venue()).note
    assert "ejournals=[Capital Markets eJournal]" in note
    assert "networks=" not in note


def test_ssrn_empty_selector_records_no_declared_intent() -> None:
    """边界"无该源字段"：什么都没声明就别在 note 里编出一句"已声明…"。"""
    note = _ssrn_step({}, make_ssrn_venue()).note
    assert "已声明" not in note


def test_ssrn_keyword_filters_are_all_local() -> None:
    """design/09 §3 SSRN 行判词："关键词全在本地过滤"。"""
    subscription = Subscription(
        name="probe",
        sources=(SourceSelector(source="ssrn", networks=("FEN",)),),
        filters=LocalFilter(title_regex_any=("risk premi",), exclude_regex=("erratum",)),
    )
    step = compile_subscription(subscription, venues={"ssrn": make_ssrn_venue()}).step_for("ssrn")
    assert step is not None
    assert step.local_predicates == (
        LOCAL_PREDICATE_TITLE_REGEX_ANY,
        LOCAL_PREDICATE_EXCLUDE_REGEX,
        PREDICATE_SSRN_TOPIC_FILTER,
    )


def test_ssrn_note_points_at_the_created_date_window_seam() -> None:
    assert "from-created-date" in _ssrn_step({"networks": ("FEN",)}, make_ssrn_venue()).note


# --- 通用补偿谓词与注册表纪律 -------------------------------------------------


def test_local_predicates_of_empty_filter_is_empty() -> None:
    assert local_predicates_of(LocalFilter()) == ()


def test_local_predicates_of_follows_local_filter_field_order() -> None:
    filters = LocalFilter(title_regex_any=("a",), exclude_regex=("b",), min_year=2024)
    assert local_predicates_of(filters) == (
        LOCAL_PREDICATE_TITLE_REGEX_ANY,
        LOCAL_PREDICATE_EXCLUDE_REGEX,
        LOCAL_PREDICATE_MIN_YEAR,
    )


def test_min_year_zero_is_not_treated_as_absent() -> None:
    """`min_year` 用 `is not None` 判在场——真值判断会把边界年份判丢（此处越界值仅测判据）。"""
    assert local_predicates_of(LocalFilter(min_year=0)) == (LOCAL_PREDICATE_MIN_YEAR,)


def test_compiler_registry_matches_source_fields_exactly() -> None:
    """集合等值自断言：扩了 `SOURCE_FIELDS` 却没写编译器 → 此处立刻红（防清单漂移）。"""
    assert SUPPORTED_SOURCES == frozenset(SOURCE_FIELDS)


def test_date_window_param_table_covers_every_source() -> None:
    """T4/T5 接缝表同样按源集合自断言——新增源必须显式回答"日期窗参数叫什么"。"""
    assert set(DATE_WINDOW_PARAMS) == set(SOURCE_FIELDS)


def test_unknown_source_fails_loud_instead_of_key_error() -> None:
    subscription = Subscription(name="probe", sources=(SourceSelector(source="scholar"),))
    with pytest.raises(SubscriptionInvalid) as excinfo:
        compile_subscription(subscription)
    assert excinfo.value.error_class is ErrorClass.CONFIG
    assert "scholar" in str(excinfo.value)


# --- 计划整体：顺序、缺源、日期窗纪律 ------------------------------------------


def _all_sources_subscription() -> Subscription:
    return parse_subscription(
        {
            "name": "all-sources",
            "sources": {
                "arxiv": {"categories": ["cs.AI"], "query": 'ti:"agent" AND NOT ti:"survey"'},
                "crossref": {"issns": ["0033-5533"]},
                "openalex": {"concepts": ["C41008148"], "from_source_types": ["preprint"]},
                "s2": {"venues": ["NeurIPS"], "fields_of_study": ["Computer Science"]},
                "nber": {"programs": ["AP"]},
                "ssrn": {"networks": ["FEN"]},
            },
            "filters": {"min_year": 2024},
        }
    )


def test_step_order_follows_dsl_declaration_order() -> None:
    plan = compile_subscription(_all_sources_subscription())
    assert [step.source for step in plan.steps] == [
        "arxiv",
        "crossref",
        "openalex",
        "s2",
        "nber",
        "ssrn",
    ]


def test_source_absent_from_dsl_gets_no_step() -> None:
    """边界"无该源段"：没声明就没有步骤（而非产一个空步骤去空跑一次请求）。"""
    plan = compile_subscription(
        Subscription(name="probe", sources=(SourceSelector(source="arxiv", categories=("cs.AI",)),))
    )
    assert plan.step_for("ssrn") is None
    assert len(plan.steps) == 1


def test_compiled_pushdown_never_carries_a_date_window() -> None:
    """接缝裁决①：编译产物是**静态**参数——日期窗归 T4，混进来会与增量窗互相覆盖。"""
    plan = compile_subscription(_all_sources_subscription(), venues={"ssrn": make_ssrn_venue()})
    date_names = {name for names in DATE_WINDOW_PARAMS.values() for name in names}
    for step in plan.steps:
        for key, value in step.pushdown:
            assert key not in date_names
            assert not any(name in value for name in date_names)


def test_min_year_is_compensated_locally_on_every_source() -> None:
    """`min_year` 不占日期参数槽位——它对每个源都是本地谓词（不变量 2）。"""
    plan = compile_subscription(_all_sources_subscription(), venues={"ssrn": make_ssrn_venue()})
    assert all(LOCAL_PREDICATE_MIN_YEAR in step.local_predicates for step in plan.steps)


def test_every_step_is_serializable_as_string_params() -> None:
    """契约稳定性：`pushdown` 值一律字符串（直接就是查询参数形态，冻结件约定）。"""
    plan = compile_subscription(_all_sources_subscription(), venues={"ssrn": make_ssrn_venue()})
    for step in plan.steps:
        assert step.source in SUPPORTED_SOURCES
        assert all(isinstance(key, str) and isinstance(value, str) for key, value in step.pushdown)
        assert step.note


# --- design/09 §2 双示例的编译快照 ---------------------------------------------


def _snapshot(name: str) -> tuple[tuple[str, tuple[tuple[str, str], ...], tuple[str, ...]], ...]:
    subscription = load_subscription_file(_FIXTURES / f"{name}.yaml")
    plan = compile_subscription(subscription, venues={"ssrn": _load_repo_ssrn_venue()})
    assert plan.subscription == name
    return tuple((s.source, s.pushdown, s.local_predicates) for s in plan.steps)


def test_llm_agents_example_compiles_to_expected_plan() -> None:
    assert _snapshot("llm-agents") == (
        (
            "arxiv",
            (
                (
                    "search_query",
                    "(cat:cs.AI OR cat:cs.LG OR cat:cs.CL OR cat:cs.MA) AND "
                    '((ti:"agent" OR abs:"agentic" OR abs:"tool use") ANDNOT ti:"survey")',
                ),
            ),
            (
                LOCAL_PREDICATE_TITLE_REGEX_ANY,
                LOCAL_PREDICATE_EXCLUDE_REGEX,
                LOCAL_PREDICATE_MIN_YEAR,
            ),
        ),
        (
            "openalex",
            (("filter", "type:preprint"),),
            (
                LOCAL_PREDICATE_TITLE_REGEX_ANY,
                LOCAL_PREDICATE_EXCLUDE_REGEX,
                LOCAL_PREDICATE_MIN_YEAR,
                PREDICATE_OPENALEX_CONCEPTS,
            ),
        ),
    )


def test_asset_pricing_wp_example_compiles_to_expected_plan() -> None:
    assert _snapshot("asset-pricing-wp") == (
        (
            "ssrn",
            (),
            (LOCAL_PREDICATE_TITLE_REGEX_ANY, PREDICATE_SSRN_TOPIC_FILTER),
        ),
        (
            "arxiv",
            (("search_query", "(cat:q-fin.PR OR cat:q-fin.PM OR cat:q-fin.ST)"),),
            (LOCAL_PREDICATE_TITLE_REGEX_ANY,),
        ),
        (
            "nber",
            (("program", "AP"),),
            (LOCAL_PREDICATE_TITLE_REGEX_ANY,),
        ),
    )


def test_examples_expose_their_local_compensation_union() -> None:
    """AC-6.4 的判据面：一份计划"下推之外还欠什么"必须可一眼枚举（保序去重并集）。"""
    subscription = load_subscription_file(_FIXTURES / "llm-agents.yaml")
    plan = compile_subscription(subscription)
    assert plan.all_local_predicates() == (
        LOCAL_PREDICATE_TITLE_REGEX_ANY,
        LOCAL_PREDICATE_EXCLUDE_REGEX,
        LOCAL_PREDICATE_MIN_YEAR,
        PREDICATE_OPENALEX_CONCEPTS,
    )
