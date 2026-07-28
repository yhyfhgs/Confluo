"""订阅 DSL 解析与校验（Phase 6 T1；design/09 §2）。

三块：
1. **双示例逐字段**——`tests/fixtures/subs/{llm-agents,asset-pricing-wp}.yaml` 是
   design/09 §2 两个示例的逐字转录，此处逐字段断言解析结果（含 guard 缺省补全）；
2. **非法输入矩阵**（≥12 例）——未知源/未知字段/坏正则/负数 guard/空 sources/坏 YAML…
   全部必须响亮报错为 `SubscriptionInvalid`，且消息带字段定位；
3. **目录加载语义**——只扫顶层（presets 是模板不是活订阅）、重名拒载、缺目录拒载。
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from paper_crawler.adapter import AdapterBase, load_adapters
from paper_crawler.errors import CrawlerError, ErrorClass, SubscriptionInvalid
from paper_crawler.subs.model import (
    DEFAULT_DEDUPE_AGAINST_LIBRARY,
    DEFAULT_MAX_NEW_PER_RUN,
    ENRICH_ONLY_SOURCES,
    SOURCE_FIELDS,
    Actions,
    Guard,
    LocalFilter,
    SourceSelector,
    Subscription,
    load_subscription_file,
    load_subscriptions_dir,
    parse_subscription,
)
from paper_crawler.subs.types import DATE_WINDOW_PARAMS
from paper_crawler.types import Capability

_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "subs"

# 有专属 `SourceFetcher`、因而**不经** `AdapterFetcher` 的 DISCOVER/ENUMERATE 退化路径
# 的源（`watch.RoutingFetcher` 的路由表）。当前只有 nber——它的 watch 增量主通道是
# program RSS（`adapters/nber/rss.py::discover_incremental`，T7/nber.md §3.4），其
# adapter 的能力位是 `RESOLVE|FETCH`，按退化路径的门槛看"不够"，但它根本不走那条路。
_DEDICATED_WATCH_FETCHERS = frozenset({"nber"})


def _write(path: Path, body: str) -> Path:
    path.write_text(body, encoding="utf-8")
    return path


# --- 1. design/09 §2 双示例逐字段 ------------------------------------------


def test_llm_agents_example_parses_field_by_field() -> None:
    sub = load_subscription_file(_FIXTURES / "llm-agents.yaml")

    assert sub.name == "llm-agents"
    # R2b/P0-4：原 fixture 还有一个 `openalex` 源（design/09 §2 示例一逐字转录），随
    # `SOURCE_FIELDS` 收缩一并删除——enrich-only 源在 watch 侧结构性不可达，留着连解析
    # 都过不了。fixture 头注记录了这处与设计文档的已知偏离。
    assert sub.source_names() == ("arxiv",)

    arxiv = sub.selector_for("arxiv")
    assert arxiv is not None
    assert arxiv.categories == ("cs.AI", "cs.LG", "cs.CL", "cs.MA")
    # `query: >` 折叠标量：换行折成空格，尾随换行被 strip。
    assert arxiv.query == '(ti:"agent" OR abs:"agentic" OR abs:"tool use") AND NOT ti:"survey"'
    assert arxiv.concepts == ()  # 非本源字段保持空

    assert sub.selector_for("openalex") is None

    assert sub.filters == LocalFilter(
        title_regex_any=(r"\bagent(s|ic)?\b", "LLM"),
        exclude_regex=("quantum",),
        min_year=2024,
    )
    assert sub.actions == Actions(ingest="metadata", auto_fetch_limit=20)
    assert sub.guard == Guard(max_new_per_run=200, dedupe_against_library=True)
    assert sub.schedule_hint == "daily"  # 仅存不调度（已裁决歧义③）


def test_asset_pricing_example_parses_field_by_field_and_fills_guard_default() -> None:
    sub = load_subscription_file(_FIXTURES / "asset-pricing-wp.yaml")

    assert sub.name == "asset-pricing-wp"
    assert sub.source_names() == ("ssrn", "arxiv", "nber")

    ssrn = sub.selector_for("ssrn")
    assert ssrn is not None
    assert ssrn.networks == ("FEN",)
    assert ssrn.ejournals == ("Asset Pricing eJournal", "Capital Markets eJournal")

    arxiv = sub.selector_for("arxiv")
    assert arxiv is not None
    assert arxiv.categories == ("q-fin.PR", "q-fin.PM", "q-fin.ST")
    assert arxiv.query is None  # 本示例未声明

    nber = sub.selector_for("nber")
    assert nber is not None
    assert nber.programs == ("AP",)

    assert sub.filters == LocalFilter(
        title_regex_any=("asset pricing", "cross-section", "risk premi")
    )
    assert sub.actions == Actions(ingest="metadata", auto_fetch_limit=10)
    # 示例只写了 max_new_per_run → dedupe_against_library 按缺省补全（DoD 判据）。
    assert sub.guard == Guard(max_new_per_run=100, dedupe_against_library=True)
    assert sub.schedule_hint is None
    assert sub.selector_for("crossref") is None


@pytest.mark.parametrize("stem", ["llm-agents", "asset-pricing-wp"])
def test_examples_round_trip_through_query_dict(stem: str) -> None:
    """`to_query_dict()` + guard → `parse_subscription` 严格互逆（库内 JSON 的往返基础）。"""
    sub = load_subscription_file(_FIXTURES / f"{stem}.yaml")
    payload = json.loads(json.dumps(sub.to_query_dict()))
    payload["guard"] = json.loads(json.dumps(sub.guard.to_dict()))
    assert parse_subscription(payload) == sub


def test_minimal_document_takes_all_defaults() -> None:
    sub = parse_subscription({"name": "minimal", "sources": {"nber": {"programs": ["AP"]}}})
    assert sub.filters == LocalFilter() and sub.filters.is_empty()
    assert sub.actions == Actions(ingest="metadata", auto_fetch_limit=0)
    assert sub.guard.max_new_per_run == DEFAULT_MAX_NEW_PER_RUN
    assert sub.guard.dedupe_against_library is DEFAULT_DEDUPE_AGAINST_LIBRARY
    assert sub.schedule_hint is None


def test_all_dsl_sources_parse() -> None:
    """SOURCE_FIELDS 的每个源 × 每个字段都能被解析（能力面自断言，防清单漂移）。

    `query` 的合法样例按源区分：arxiv 自 Phase 7 T9 起校验布尔语法（范围=ti/abs
    字段，见 `_require_arxiv_query_syntax`），裸词 `"x"` 不再合法；其余源（当前无）
    的同名字段若为自由文本，裸词照旧合法。
    """
    sources: dict[str, object] = {}
    for source, fields in SOURCE_FIELDS.items():
        query_value = 'ti:"x"' if source == "arxiv" else "x"
        sources[source] = {name: (query_value if name == "query" else ["x"]) for name in fields}
    sub = parse_subscription({"name": "everything", "sources": sources})
    assert sub.source_names() == tuple(SOURCE_FIELDS)
    for selector in sub.sources:
        for name in SOURCE_FIELDS[selector.source]:
            assert getattr(selector, name)  # 非空 = 该字段真的被落进了 dataclass


# `SourceSelector` 上随 openalex/s2 退出 `SOURCE_FIELDS` 而失去来源的字段（R2b/P0-4）。
# 字段本身保留（冻结值对象 + R4 可能实装两源的时间轴，见该 dataclass docstring），
# 但清单必须显式列出来——否则下面那条等值自断言只能放宽成"包含"，就再也抓不住
# "新增了一个 DSL 里写得出、代码里永远读不到的字段"这类真漂移。
_PARKED_SELECTOR_FIELDS = frozenset({"concepts", "from_source_types", "venues", "fields_of_study"})


def test_source_fields_and_selector_dataclass_stay_in_sync() -> None:
    """`SOURCE_FIELDS` 的字段并集 ∪ 停放字段 == `SourceSelector` 的非 `source` 字段集合。

    集合等值自断言（沿审计 S4 的"注册了却没验证"根治手法）：任一侧新增字段而另一侧
    忘了跟进，这里立刻红——防止"DSL 里写了却永远读不到"的静默漏字段。停放字段列在
    `_PARKED_SELECTOR_FIELDS` 里，两侧仍是**等值**而非包含。
    """
    declared = {name for fields in SOURCE_FIELDS.values() for name in fields}
    on_class = {f.name for f in dataclasses.fields(SourceSelector)} - {"source"}
    assert declared | _PARKED_SELECTOR_FIELDS == on_class
    assert declared.isdisjoint(_PARKED_SELECTOR_FIELDS)  # 停放字段确实无源可声明


def test_selector_to_dict_only_emits_own_source_fields() -> None:
    selector = SourceSelector(source="nber", programs=("AP",), categories=("cs.AI",))
    assert selector.to_dict() == {"programs": ["AP"]}  # categories 不属于 nber，不外泄


def test_selector_to_dict_skips_unset_fields() -> None:
    """本源合法但未声明的字段（空列表 / query=None）不出现在回写里。"""
    selector = SourceSelector(source="arxiv", categories=("cs.AI",))
    assert selector.to_dict() == {"categories": ["cs.AI"]}  # query 未声明


def test_ingest_metadata_pdf_with_default_fetch_limit() -> None:
    sub = parse_subscription(
        {
            "name": "pdf-mode",
            "sources": {"nber": {"programs": ["AP"]}},
            "actions": {"ingest": "metadata+pdf"},
        }
    )
    assert sub.actions == Actions(ingest="metadata+pdf", auto_fetch_limit=0)


# --- 2. 非法输入矩阵（DoD ≥12 例）------------------------------------------

_BASE_SOURCES: dict[str, object] = {"arxiv": {"categories": ["cs.AI"]}}


def _doc(**overrides: object) -> dict[str, object]:
    document: dict[str, object] = {"name": "probe", "sources": dict(_BASE_SOURCES)}
    document.update(overrides)
    return document


_INVALID: list[tuple[str, dict[str, object], str]] = [
    # (用例名, 文档, 报错消息里必须出现的定位/关键词)
    ("未知顶层字段", _doc(schedule="daily"), "schedule"),
    ("未知源", {"name": "probe", "sources": {"biorxiv": {"categories": ["x"]}}}, "未知源"),
    (
        "未知源内字段",
        {"name": "probe", "sources": {"arxiv": {"catgories": ["cs.AI"]}}},
        "sources.arxiv.catgories",
    ),
    (
        "字段串到别的源",
        {"name": "probe", "sources": {"nber": {"categories": ["cs.AI"]}}},
        "sources.nber.categories",
    ),
    ("空 sources", {"name": "probe", "sources": {}}, "至少声明一个源"),
    ("缺 sources", {"name": "probe"}, "sources"),
    ("缺 name", {"sources": dict(_BASE_SOURCES)}, "name"),
    ("name 形态非法", _doc(name="LLM Agents"), "kebab-case"),
    ("空选择器", {"name": "probe", "sources": {"arxiv": {}}}, "选择器为空"),
    ("None 选择器", {"name": "probe", "sources": {"arxiv": None}}, "必须是映射"),
    (
        "标量当列表",
        {"name": "probe", "sources": {"arxiv": {"categories": "cs.AI"}}},
        "实际是单个字符串",
    ),
    ("空列表", {"name": "probe", "sources": {"arxiv": {"categories": []}}}, "列表不得为空"),
    (
        "数值当列表",
        {"name": "probe", "sources": {"arxiv": {"categories": 5}}},
        "必须是列表，实际是 int",
    ),
    ("空 query", {"name": "probe", "sources": {"arxiv": {"query": "  "}}}, "不得为空字符串"),
    (
        "列表元素非串",
        {"name": "probe", "sources": {"arxiv": {"categories": [1]}}},
        "sources.arxiv.categories[0]",
    ),
    ("坏 title 正则", _doc(filters={"title_regex_any": ["["]}), "正则非法"),
    ("坏 exclude 正则", _doc(filters={"exclude_regex": ["(unclosed"]}), "正则非法"),
    ("未知 filters 字段", _doc(filters={"max_year": 2024}), "filters.max_year"),
    ("min_year 非整数", _doc(filters={"min_year": "2024"}), "必须是整数"),
    ("min_year 负数", _doc(filters={"min_year": -1}), "年份越界"),
    ("min_year 越界", _doc(filters={"min_year": 20240}), "年份越界"),
    ("filters 非映射", _doc(filters=["title_regex_any"]), "必须是映射"),
    ("未知 actions 字段", _doc(actions={"ingest": "metadata", "fetch": 3}), "actions.fetch"),
    ("ingest 取值非法", _doc(actions={"ingest": "metadata+html"}), "actions.ingest"),
    ("auto_fetch_limit 负数", _doc(actions={"auto_fetch_limit": -1}), "不得为负"),
    ("未知 guard 字段", _doc(guard={"max_total": 10}), "guard.max_total"),
    ("guard 负数", _doc(guard={"max_new_per_run": -5}), "须 ≥ 1"),
    ("guard 零", _doc(guard={"max_new_per_run": 0}), "须 ≥ 1"),
    ("guard bool 落数值位", _doc(guard={"max_new_per_run": True}), "必须是整数"),
    ("dedupe 非布尔", _doc(guard={"dedupe_against_library": 1}), "必须是布尔"),
    ("schedule_hint 非串", _doc(schedule_hint=3), "必须是字符串"),
    # --- arxiv query 布尔式语法早验（Phase 7 T9；范围=ti/abs 字段，决策⑤ YAGNI）---
    (
        "arxiv query 缺字段前缀",
        {"name": "probe", "sources": {"arxiv": {"query": "agent"}}},
        "arXiv 查询式语法非法",
    ),
    (
        "arxiv query 不支持的字段前缀",
        {"name": "probe", "sources": {"arxiv": {"query": 'au:"Smith"'}}},
        "arXiv 查询式语法非法",
    ),
    (
        "arxiv query 括号不配对",
        {"name": "probe", "sources": {"arxiv": {"query": '(ti:"agent"'}}},
        "arXiv 查询式语法非法",
    ),
    (
        "arxiv query 悬空算子",
        {"name": "probe", "sources": {"arxiv": {"query": 'ti:"agent" OR'}}},
        "arXiv 查询式语法非法",
    ),
    # 独立审查 P1-1：未闭合引号（此前被词法层静默吞入，参数化谓词对任何 stub 恒
    # False，watch 运行时把整个 arxiv 源静默清零、零告警——见 test_subs_types.py
    # 的 parse_arxiv_query 专测；此处补订阅加载期的端到端拒载）。
    (
        "arxiv query 未闭合引号",
        {"name": "probe", "sources": {"arxiv": {"query": 'ti:"agent'}}},
        "未闭合或多余的引号",
    ),
    # 独立审查 P2③：手写日期窗须给出"日期窗不在 DSL 里"这条具体提示，不能被通用
    # 语法解析器的"不支持的字段前缀"抢先报出并遮蔽（`submittedDate` 词法上完全
    # 符合 field:phrase 原子形状）。
    (
        "arxiv query 手写日期窗",
        {
            "name": "probe",
            "sources": {
                "arxiv": {"query": 'ti:"agent" AND submittedDate:[202601010000 TO 202601310000]'}
            },
        },
        "不得手写日期窗",
    ),
]


@pytest.mark.parametrize(
    ("document", "needle"),
    [pytest.param(doc, needle, id=name) for name, doc, needle in _INVALID],
)
def test_invalid_documents_fail_loud(document: dict[str, object], needle: str) -> None:
    with pytest.raises(SubscriptionInvalid) as excinfo:
        parse_subscription(document, where="probe.yaml")
    message = str(excinfo.value)
    assert needle in message
    assert message.startswith("probe.yaml")  # 定位前缀恒在
    assert excinfo.value.error_class is ErrorClass.CONFIG
    assert isinstance(excinfo.value, CrawlerError)  # 归入既有 errors 层级


def test_invalid_matrix_covers_at_least_twelve_cases() -> None:
    """DoD 明文要求 ≥12 例；此断言防后人删测试时无声降标。"""
    assert len(_INVALID) >= 12


def test_sources_must_be_a_mapping() -> None:
    with pytest.raises(SubscriptionInvalid, match="必须是映射"):
        parse_subscription({"name": "probe", "sources": ["arxiv"]}, where="probe.yaml")


# --- 4. arxiv query 布尔式语法早验的正例 + 范围边界（Phase 7 T9）--------------


def test_arxiv_query_with_valid_boolean_syntax_parses_fine() -> None:
    """反例：语法合法的复合布尔式（OR 分组 + ANDNOT + 混合大小写 + 折叠空白）正常通过。

    与 9 个真实 preset 的实况同构（`tests/unit/test_subs_presets.py` 逐一验证真实
    文件），此处只需一条代表性用例证明校验没有过度收紧。
    """
    sub = parse_subscription(
        {
            "name": "probe",
            "sources": {
                "arxiv": {
                    "categories": ["cs.AI"],
                    "query": '(ti:"agent" OR abs:"agentic")\n      and not ti:"survey"',
                }
            },
        }
    )
    assert sub.selector_for("arxiv") is not None


def test_arxiv_query_date_window_names_give_the_specific_message() -> None:
    """独立审查 P2③ 回归锁：手写日期窗必须报"不得手写日期窗"这条具体提示，不能被
    通用语法解析器的"不支持的字段前缀"抢先报出（`DATE_WINDOW_PARAMS` 反向导出的
    全部 8 个名字逐一验证，同 `test_subs_compile.py::
    test_date_window_guard_names_are_derived_from_the_seam_table` 的口径，只是
    这里走**订阅加载期**——`model.py`——而非编译期）。
    """
    names = {name for names in DATE_WINDOW_PARAMS.values() for name in names}
    assert len(names) == 8
    for name in names:
        with pytest.raises(SubscriptionInvalid) as excinfo:
            parse_subscription(
                {"name": "probe", "sources": {"arxiv": {"query": f'ti:"agent" AND {name}:X'}}}
            )
        message = str(excinfo.value)
        assert "不得手写日期窗" in message, f"{name}: 被通用语法错误遮蔽 —— {message!r}"
        assert "不支持的字段前缀" not in message


def test_query_is_now_an_arxiv_only_field_and_other_sources_cannot_smuggle_it() -> None:
    """`query` 随 s2 退出 `SOURCE_FIELDS` 后成了 arxiv 独占字段（R2b/P0-4）。

    原测试（`test_s2_query_free_text_is_not_subject_to_arxiv_boolean_syntax`）用 s2 的
    自由文本 `query` 证明"arxiv 专属布尔语法校验只对 arxiv 生效"；s2 已不是合法源，那条
    证明面随之消失。改锁两件仍然为真、且属同一条纪律的事：

    ① `query` 现在只有 arxiv 一个宿主——`_parse_selector` 里 `source == "arxiv"` 那道
       条件因此暂时恒真，但**保留**（`SourceSelector.query` 是停放期共用的槽位，R4 若
       实装 s2 会立刻需要它）；
    ② 别的源写 `query` 一律按"未知字段"拒载——不会有哪个源绕过 arxiv 语法校验偷渡进来。
    """
    assert [source for source, fields in SOURCE_FIELDS.items() if "query" in fields] == ["arxiv"]

    with pytest.raises(SubscriptionInvalid) as excinfo:
        parse_subscription({"name": "probe", "sources": {"nber": {"query": "large language"}}})
    assert "未知字段" in str(excinfo.value)
    assert excinfo.value.detail is not None
    assert excinfo.value.detail.endswith("sources.nber.query")


# --- enrich-only 源：结构性不可达 → 加载期拒载（R2b/P0-4）--------------------
#
# 修复前的真实形态：`openalex`/`s2` 在 `SOURCE_FIELDS` 白名单里 → 订阅解析通过 →
# `compile.py` 有编译器、译得出漂亮的 `filter=`/`venue=` 参数 → `watch.AdapterFetcher`
# 调 `discover_timeline` → `AdapterBase` 兜底 `CapabilityNotSupported`，整轮 watch 炸。
# 9 个 preset 里 6 个声明了这两源，即"照文档抄一份 preset 就必炸"。


@pytest.mark.parametrize("source", sorted(ENRICH_ONLY_SOURCES))
def test_enrich_only_source_is_rejected_at_load_time_with_a_pointed_message(source: str) -> None:
    """三个 enrich-only 源一律在**加载期**拒载，且消息说清"为什么"与"改用什么"。

    判据不止"报错了"——通用的"未知源 'openalex'"会把用户引向检查拼写（而 openalex
    确实是本仓库注册在案的 adapter，拼写没错），故断言消息里同时出现 enrich-only 的
    判词、替代通道，以及仍然可用的四个源。
    """
    with pytest.raises(SubscriptionInvalid) as excinfo:
        parse_subscription({"name": "probe", "sources": {source: {"categories": ["x"]}}})

    message = str(excinfo.value)
    assert excinfo.value.error_class is ErrorClass.CONFIG
    assert excinfo.value.detail == f"<subscription>:sources.{source}"
    assert "enrich-only" in message
    assert "不支持 watch" in message
    assert "crawler enrich" in message
    assert "未知源" not in message  # 不是拼错，别把用户往那边引
    for available in SOURCE_FIELDS:
        assert available in message


def test_genuinely_unknown_source_still_gets_the_generic_message() -> None:
    """对照组：真拼错的源仍走通用文案（两档措辞不能塌成一档）。"""
    with pytest.raises(SubscriptionInvalid) as excinfo:
        parse_subscription({"name": "probe", "sources": {"arxvi": {"categories": ["cs.AI"]}}})
    message = str(excinfo.value)
    assert "未知源" in message
    assert "enrich-only" not in message


def test_enrich_only_source_set_matches_the_real_adapter_capability_bits() -> None:
    """`ENRICH_ONLY_SOURCES` **恰好** == 真实 adapter 表里 `capabilities` 为空集者。

    这是 P1-12（Capability 全枚举零消费）在订阅域的根治点：清单不再是一句注释里的
    断言，而是与 `load_adapters()` 的真实能力位对表。将来任何 adapter 退化/新增为
    enrich-only 却忘了同步词表，或反过来给 openalex 点亮了能力位却没把它加回
    `SOURCE_FIELDS`，这条都会当场红。
    """
    empty_capability_adapters = {
        adapter_id
        for adapter_id, adapter in load_adapters().items()
        if adapter.capabilities == Capability(0)
    }
    assert ENRICH_ONLY_SOURCES == empty_capability_adapters
    assert ENRICH_ONLY_SOURCES.isdisjoint(SOURCE_FIELDS)  # 白名单里一个都不许有


def test_every_dsl_source_is_structurally_reachable_by_a_watch_channel() -> None:
    """`SOURCE_FIELDS` 的每个源都得有一条**跑得动**的 watch 拉取通道。

    两条合法通道（`watch.RoutingFetcher` 的分派面）：
    - 专属 `SourceFetcher`（nber → `NberRssFetcher` 的 program RSS 通道，T7）；
    - 退化路径 `AdapterFetcher` → 该源同名 adapter 的 `discover_timeline` +
      `enumerate_issue`，故它必须同时具备 `DISCOVER` 与 `ENUMERATE`。

    能力位与"方法是否真被覆写"两条一起断言：位是声明、覆写是实现，`AdapterBase` 的
    兜底方法正是 `CapabilityNotSupported` 的出处——只查位会漏掉"声明了却没实现"，
    只查覆写会漏掉"实现了却没声明"（后者会让本卡新加的 registry lint 误判）。
    """
    adapters = load_adapters()
    for source in SOURCE_FIELDS:
        if source in _DEDICATED_WATCH_FETCHERS:
            continue
        adapter = adapters.get(source)
        assert adapter is not None, f"{source}: 无同名 adapter，且无专属 fetcher"
        assert Capability.DISCOVER in adapter.capabilities, f"{source} 缺 DISCOVER"
        assert Capability.ENUMERATE in adapter.capabilities, f"{source} 缺 ENUMERATE"
        assert type(adapter).discover_timeline is not AdapterBase.discover_timeline, (
            f"{source}: discover_timeline 未覆写，调用即 CapabilityNotSupported"
        )
        assert type(adapter).enumerate_issue is not AdapterBase.enumerate_issue, (
            f"{source}: enumerate_issue 未覆写，调用即 CapabilityNotSupported"
        )


# --- 文件层：坏 YAML / 空文件 / 编码 / 文件名 --------------------------------


def test_broken_yaml_fails_loud(tmp_path: Path) -> None:
    path = _write(tmp_path / "broken.yaml", "name: broken\nsources: {arxiv: [\n")
    with pytest.raises(SubscriptionInvalid, match="YAML 解析失败"):
        load_subscription_file(path)


def test_empty_file_fails_loud(tmp_path: Path) -> None:
    path = _write(tmp_path / "empty.yaml", "# 只有注释\n")
    with pytest.raises(SubscriptionInvalid, match="文件为空"):
        load_subscription_file(path)


def test_yaml_top_level_list_fails_loud(tmp_path: Path) -> None:
    path = _write(tmp_path / "listy.yaml", "- name: listy\n")
    with pytest.raises(SubscriptionInvalid, match="必须是映射"):
        load_subscription_file(path)


def test_unreadable_file_fails_loud(tmp_path: Path) -> None:
    (tmp_path / "gone.yaml").write_bytes(b"\xff\xfe\x00name")  # 非 UTF-8
    with pytest.raises(SubscriptionInvalid, match="文件读取失败"):
        load_subscription_file(tmp_path / "gone.yaml")


def test_missing_file_fails_loud(tmp_path: Path) -> None:
    with pytest.raises(SubscriptionInvalid, match="文件读取失败"):
        load_subscription_file(tmp_path / "nope.yaml")


def test_filename_must_match_name(tmp_path: Path) -> None:
    path = _write(tmp_path / "other-name.yaml", "name: probe\nsources: {nber: {programs: [AP]}}\n")
    with pytest.raises(SubscriptionInvalid, match="与 name"):
        load_subscription_file(path)


# --- YAML 重复键（P1-2 热修：PyYAML 默认静默取后者覆盖前者）------------------


def test_duplicate_source_key_fails_loud(tmp_path: Path) -> None:
    """`sources:` 内重复声明同一源（两次 `arxiv:`）→ 拒载，而非静默取后者覆盖前者。"""
    path = _write(
        tmp_path / "dup-source.yaml",
        "name: dup-source\n"
        "sources:\n"
        "  arxiv:\n"
        "    categories: [cs.AI]\n"
        "  arxiv:\n"
        "    categories: [cs.LG]\n",
    )
    with pytest.raises(SubscriptionInvalid) as excinfo:
        load_subscription_file(path)
    message = str(excinfo.value)
    assert "重复键" in message and "arxiv" in message
    assert message.startswith(str(path))  # 文件定位恒在（_fail 的 where 前缀）


def test_duplicate_field_within_selector_fails_loud(tmp_path: Path) -> None:
    """选择器内重复字段（两次 `categories:`）→ 拒载，而非静默取后者覆盖前者。"""
    path = _write(
        tmp_path / "dup-field.yaml",
        "name: dup-field\nsources:\n  arxiv:\n    categories: [cs.AI]\n    categories: [cs.LG]\n",
    )
    with pytest.raises(SubscriptionInvalid) as excinfo:
        load_subscription_file(path)
    message = str(excinfo.value)
    assert "重复键" in message and "categories" in message
    assert message.startswith(str(path))


def test_duplicate_top_level_field_fails_loud(tmp_path: Path) -> None:
    """顶层字段重复（两次 `sources:`）同样拒载——检测不分层级。"""
    path = _write(
        tmp_path / "dup-top.yaml",
        "name: dup-top\n"
        "sources:\n"
        "  arxiv:\n"
        "    categories: [cs.AI]\n"
        "sources:\n"
        "  nber:\n"
        "    programs: [AP]\n",
    )
    with pytest.raises(SubscriptionInvalid) as excinfo:
        load_subscription_file(path)
    message = str(excinfo.value)
    assert "重复键" in message and "sources" in message
    assert message.startswith(str(path))


# --- 3. 目录加载语义 --------------------------------------------------------


def _valid_body(name: str) -> str:
    return f"name: {name}\nsources:\n  nber:\n    programs: [AP]\n"


def test_load_dir_reads_top_level_only_and_sorts(tmp_path: Path) -> None:
    _write(tmp_path / "zulu.yaml", _valid_body("zulu"))
    _write(tmp_path / "alpha.yaml", _valid_body("alpha"))
    (tmp_path / "presets").mkdir()
    _write(tmp_path / "presets" / "preset-one.yaml", _valid_body("preset-one"))
    _write(tmp_path / "notes.txt", "不是 YAML")

    loaded = load_subscriptions_dir(tmp_path)
    # presets/ 是模板不是活订阅 → 不递归；非 .yaml 忽略；按文件名排序。
    assert [s.name for s in loaded] == ["alpha", "zulu"]


def test_load_dir_empty_is_ok(tmp_path: Path) -> None:
    assert load_subscriptions_dir(tmp_path) == []


def test_load_dir_missing_fails_loud(tmp_path: Path) -> None:
    with pytest.raises(SubscriptionInvalid, match="订阅目录不存在"):
        load_subscriptions_dir(tmp_path / "absent")


def test_load_dir_name_uniqueness_comes_from_filename_rule(tmp_path: Path) -> None:
    """同目录内不可能出现重名：stem 必须等于 name，而同扩展名的 stem 天然唯一。

    "另一个文件想叫同一个 name" 的唯一形态就是 stem 不符 → 被文件名校验拦下。
    """
    _write(tmp_path / "dup.yaml", _valid_body("dup"))
    _write(tmp_path / "dup-copy.yaml", _valid_body("dup"))  # name=dup 但 stem=dup-copy
    with pytest.raises(SubscriptionInvalid, match="与 name"):
        load_subscriptions_dir(tmp_path)


def test_load_dir_propagates_file_error(tmp_path: Path) -> None:
    _write(tmp_path / "ok.yaml", _valid_body("ok"))
    _write(tmp_path / "bad.yaml", "name: bad\nsources: {biorxiv: {categories: [x]}}\n")
    with pytest.raises(SubscriptionInvalid, match="未知源"):
        load_subscriptions_dir(tmp_path)


# --- from_stored（库行还原；repo 的解析路径）-------------------------------


def test_from_stored_round_trip() -> None:
    original = load_subscription_file(_FIXTURES / "llm-agents.yaml")
    restored = Subscription.from_stored(
        "llm-agents",
        json.dumps(original.to_query_dict(), ensure_ascii=False),
        json.dumps(original.guard.to_dict()),
    )
    assert restored == original


def test_from_stored_without_guard_json_takes_defaults() -> None:
    restored = Subscription.from_stored(
        "probe", json.dumps({"name": "probe", "sources": {"nber": {"programs": ["AP"]}}})
    )
    assert restored.guard == Guard()


@pytest.mark.parametrize(
    ("name", "query_json", "guard_json", "needle"),
    [
        ("probe", "{not json", None, "JSON 解析失败"),
        ("probe", '["probe"]', None, "必须是映射"),
        ("probe", '{"name": "other", "sources": {"nber": {"programs": ["AP"]}}}', None, "不一致"),
        (
            "probe",
            '{"name": "probe", "sources": {"nber": {"programs": ["AP"]}}}',
            "{bad",
            "JSON 解析失败",
        ),
    ],
)
def test_from_stored_corrupt_row_fails_loud(
    name: str, query_json: str, guard_json: str | None, needle: str
) -> None:
    with pytest.raises(SubscriptionInvalid, match=needle):
        Subscription.from_stored(name, query_json, guard_json)
