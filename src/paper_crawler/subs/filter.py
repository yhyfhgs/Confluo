"""本地二次过滤（Phase 6 T3；design/09 §2 `filters:` 段 + §3 本地补偿原则）。

`LocalFilter`（`subs.model` 冻结件）三字段对 `PaperStub` 流**统一执行**（design/09 §2：
"对所有源结果统一执行的本地二次过滤"——不论该源是否已把等价条件下推，本地过滤仍会
再跑一遍，正确性以本地过滤为准，design/09 §3 末原则句）：

- `title_regex_any`：非空时标题须命中其中**任一**条才通过（大小写不敏感）；命中的每个
  索引记一条 `"title_regex_any[i]"`（`LOCAL_PREDICATE_TITLE_REGEX_ANY` 前缀）进
  `matched_rules`，供 `ReportEntry.matched_rules` 消费（design/09 §6.3"命中的过滤规则"）。
  为空 = 不设限，全部通过、不产该前缀的标记。
- `exclude_regex`：非空时标题命中**任一**条即整条剔除（大小写不敏感）。被剔除的条目不
  出现在返回值里，因此 `LOCAL_PREDICATE_EXCLUDE_REGEX` **永远不会**出现在 `matched_rules`
  中——"命中排除规则"和"留在清单里"互斥，这是设计使然而非遗漏。
- `min_year`：非空时 `stub.year` 须 **≥** 阈值才通过；`year is None`（年份未知）在
  **已声明** `min_year` 时视为不通过——呼应 `adapters.ssrn.parse.topic_field_matches` 的
  先例（无法确认时诚实剔除，opt-in 收窄语义下宁可漏收不可误纳噪声，该函数 docstring
  原话）。通过时记一条 `"min_year"`（`LOCAL_PREDICATE_MIN_YEAR`）。

三者皆空（`filters.is_empty()`）→ 全部通过，`matched_rules` 恒为空元组。

## 谓词注册（源专属本地补偿；Phase 7 T9 改造为**构造器形态**）

`title_regex_any`/`exclude_regex`/`min_year` 是**订阅级**、跨源统一的条件；某些源还带
**源专属**的固定补偿谓词——例如 ssrn `quirks.topic_filter`（`venues/econ/ssrn.yaml`，
econ/fin 主题近似过滤，design/adapters/ssrn.md §3）尚未有 DSL 字段承载，是源自身固定
策略，不属于用户在订阅文件里声明的 `filters:`。这类谓词用 `"<source>.<name>"` 命名
（`subs.types` 模块 docstring 约定），登记进 `PREDICATE_REGISTRY`。

`PREDICATE_REGISTRY` 的值不再是裸的 `PaperStub -> bool`（`PredicateFn`），而是
**构造器** `PredicateConstructor = Callable[[str], PredicateFn]`——接一个**订阅级
参数**（字符串；免参数的谓词忽略它即可），返回真正求值用的 `PredicateFn` 闭包。这是
Phase 7 T9"参数化谓词签名"冻结件的落点：此前签名不带参数，无法承载订阅级表达式
（如 arxiv 的 `query` 布尔式）；`build_predicate(name, param)` 是新的构造入口，
`apply_predicate(name, stub, param=...)` 与 `filter_papers(..., predicate_params=...)`
在其上薄封装。**唯一存量谓词 `ssrn.topic_filter` 已迁移到新签名，不做兼容层**——登记
面全量切换，未登记的名字依旧响亮报错（`ValueError`，同 `merge.py` 未知 `source` 先例：
`raise ValueError(f"unknown source {source!r}; must be one of ...")`）——一个拼错的
谓词名绝不能被静默跳过；校验在遍历 `stubs` **之前**完成，因此空输入流也会触发报错
（fail-loud 不依赖"恰好有数据流过"）。

当前登记两项：

- `SSRN_TOPIC_FILTER`（`"ssrn.topic_filter"`）：构造器忽略参数（该谓词的判定
  完全来自 `stub.meta`，不需要订阅级参数），直接复用
  `adapters.ssrn.parse.topic_field_matches`/`stub_topic_field`（Phase 5 既有纯函数，
  `stub.meta` 读 `TOPIC_FIELD_META_KEY`）——不复制这套近似过滤逻辑第二份。
- `ARXIV_QUERY_BOOL`（`"arxiv.query_bool"`，Phase 7 T9 新增）：构造器接
  `compile._compile_arxiv` 归一后的 arXiv 查询布尔式（`subs.types.parse_arxiv_query`
  解析出的语法树，范围=ti/abs 字段 + AND/OR/ANDNOT + 引号短语，决策⑤ YAGNI），返回
  按标题/摘要文本求值的闭包。**该标记不进 `PlanStep.local_predicates`**——
  `subs/watch.py` 现有的 `extra_predicates=` 调用点只传裸名字、不传参数，见
  `compile.py::_compile_arxiv` docstring 的接缝说明；本模块提供的是完整、可独立
  测试的机制，实际接入 watch.py 运行时留给后续卡。

### 信号缺失时的兜底：pass-through 放行（T5 随卡小修，controller 裁决 2026-07-26）

`topic_field_matches(None)` 在**原语层**是 `False`（"无法确认 econ/fin 归属时诚实
排除"，见其 docstring）——那是 Phase 5 的 `filter_stubs_by_topic` 语义：那条路径上
信号**本该有**（openalex enrich 已跑过），缺失即真实的"不属于"。

订阅域的处境相反：`stub.meta['openalex_field']` 这个 enrich 信号**当前生产路径根本
不产**（ssrn 走 crossref 前缀枚举，无此键；openalex `_meta_of` 亦未接线——见
`compile.py::_compile_ssrn` docstring 的"执行前提"段）。若直接沿用原语语义，整条
ssrn 订阅会被这个谓词**清零**：用户看到的是一份永远空白的日报，而不是一条"这层
过滤没生效"的提示。故本层包一道兜底——

- `stub_topic_field(stub) is None` → **放行**（pass-through），并经 obslog 记一条
  一次性 WARNING（**每次 watch 运行每个谓词一条**——记账是谓词名粒度，由
  `reset_predicate_warnings()` 在 run 起点复位一次；同一谓词只可能挂在一个源上，
  故实际效果等同"每 run 每源一条"）；
- 非 None → 照走 `topic_field_matches`（信号一旦接线，语义立刻回到精确判定，本层
  自动退场，无需再改一次代码）。

方向性取舍与 `filter_papers` 的 `min_year` 那条**刻意相反**：`min_year` 缺 year 时
排除，因为 year 是普遍可得的字段，缺失是数据个例；此处缺的是**整条通道都还没接的
信号**，"全都排除"表达的不是数据事实而是接线状态。宁可多收噪声（用户看得见、可
用 `exclude_regex` 收窄），不可静默清零（用户看不见、无从自证）。
"""

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from re import IGNORECASE, Pattern
from re import compile as re_compile

from paper_crawler.adapters.ssrn.parse import stub_topic_field, topic_field_matches
from paper_crawler.obslog import log_event
from paper_crawler.subs.model import LocalFilter
from paper_crawler.subs.types import (
    LOCAL_PREDICATE_MIN_YEAR,
    LOCAL_PREDICATE_TITLE_REGEX_ANY,
    ArxivQueryAtom,
    ArxivQueryNode,
    parse_arxiv_query,
)
from paper_crawler.types import PaperStub

# 一个源专属补偿谓词：`PaperStub` → 是否通过（True=保留，语义同 `topic_field_matches`）。
PredicateFn = Callable[[PaperStub], bool]

# 谓词**构造器**：接一个订阅级参数（字符串；免参数的谓词忽略它），返回真正求值用的
# `PredicateFn`（Phase 7 T9"参数化谓词签名"冻结件——模块 docstring"谓词注册"段）。
PredicateConstructor = Callable[[str], PredicateFn]

# ssrn econ/fin 主题近似过滤（design/adapters/ssrn.md §3；`venues/econ/ssrn.yaml`
# `quirks.topic_filter: econ_fin` 的运行期落点）。`"<source>.<name>"` 命名约定。
SSRN_TOPIC_FILTER = "ssrn.topic_filter"

# arxiv `query` 布尔式的参数化补偿谓词（Phase 7 T9）。谓词名同
# `compile.PREDICATE_ARXIV_QUERY_BOOL`——两处各自独立定义同一字面量，沿用本模块
# `SSRN_TOPIC_FILTER`/`compile.PREDICATE_SSRN_TOPIC_FILTER` 的既有先例。
ARXIV_QUERY_BOOL = "arxiv.query_bool"

# 已提示过"enrich 信号未接线"的谓词名（模块级；`reset_predicate_warnings()` 复位）。
# 一次 watch 运行内每个谓词只提示一条——逐条目提示会把日志刷成噪声，而这条提示描述的
# 是**接线状态**（整条通道的属性），不是某一条目的属性。
_SIGNAL_WARNED: set[str] = set()


def reset_predicate_warnings() -> None:
    """复位"信号缺失"一次性提示的记账——**每次 watch 运行起点调用一次**（不是每源一次）。

    `subs/watch.py::run_watch` 在编译计划之前调用一次，此后整轮运行内每个谓词最多提示
    一条。不调用亦不影响过滤结果，只是提示退化为"进程内一条"（长驻进程里第二次 run
    就看不到提示了；watch 是 cron 单次运行，实际不受影响）。
    """
    _SIGNAL_WARNED.clear()


def _warn_signal_missing_once(predicate: str, detail: str) -> None:
    """同一谓词在本次运行内只提示一次（模块 docstring "信号缺失时的兜底"段）。"""
    if predicate in _SIGNAL_WARNED:
        return
    _SIGNAL_WARNED.add(predicate)
    log_event("WARNING", f"{predicate}: {detail}", stage="watch")


def _ssrn_topic_filter(stub: PaperStub) -> bool:
    """`ssrn.topic_filter` 的执行体：信号缺失 → 放行 + 一次性提示；有信号 → 照判。"""
    field_value = stub_topic_field(stub)
    if field_value is None:
        _warn_signal_missing_once(
            SSRN_TOPIC_FILTER,
            "enrich 信号未接线（stub.meta['openalex_field'] 缺失），"
            "topic_filter 退化为 LocalFilter-only（本次全部放行）",
        )
        return True
    return topic_field_matches(field_value)


def _construct_ssrn_topic_filter(_param: str) -> PredicateFn:
    """`ssrn.topic_filter` 的构造器：判定信号完全来自 `stub.meta`，不需要订阅级
    参数——`_param` 恒被忽略（保留形参只为满足 `PredicateConstructor` 的统一签名）。
    """
    return _ssrn_topic_filter


def _arxiv_field_text(field: str, stub: PaperStub) -> str | None:
    """把语法树的字段名映射到 `PaperStub` 的对应文本（范围=`ARXIV_QUERY_FIELDS`）。"""
    if field == "ti":
        return stub.title
    if field == "abs":
        return stub.abstract
    raise AssertionError(f"unreachable: field {field!r} not in ARXIV_QUERY_FIELDS")


def _evaluate_arxiv_query(node: ArxivQueryNode, stub: PaperStub) -> bool:
    """对语法树递归求值（大小写不敏感的子串匹配——近似过滤，非精确复刻 arXiv 检索
    相关性语义；范围与匹配方式的取舍见 `subs.types.ArxivQueryAtom`/模块级说明）。

    字段缺失（如 `stub.abstract is None`）→ 该原子判 `False`（无法确认时诚实剔除，
    呼应 `filter_papers` 的 `min_year`/`ssrn.topic_filter` 同款取舍）。
    """
    if isinstance(node, ArxivQueryAtom):
        text = _arxiv_field_text(node.field, stub)
        return text is not None and node.phrase.lower() in text.lower()
    left = _evaluate_arxiv_query(node.left, stub)
    if node.op == "OR":
        return left or _evaluate_arxiv_query(node.right, stub)
    if node.op == "ANDNOT":
        return left and not _evaluate_arxiv_query(node.right, stub)
    return left and _evaluate_arxiv_query(node.right, stub)  # op == "AND"


def _construct_arxiv_query_bool(param: str) -> PredicateFn:
    """`arxiv.query_bool` 的构造器：`param` 是 `compile._compile_arxiv` 已归一的
    查询布尔式（Phase 7 T9；plan §4 T9 冻结件"参数化谓词签名"）。解析在**构造时
    一次性**完成（非逐 paper 重复解析），返回的闭包只做树求值。

    `param` 为空/纯空白 → 响亮报错：`_compile_arxiv` 只在 `selector.query` 归一后
    非空时才会挂上这条谓词标记，正常接线路径不会传空参数——这里报错的是"调用方没
    传参数"这类接线错误，不是用户配置错误（那一层已被 `model.py` 的
    `_require_arxiv_query_syntax` 挡在订阅加载期）。
    """
    if not param.strip():
        raise ValueError(f"{ARXIV_QUERY_BOOL} 构造器需要非空查询式参数（接线错误：未传 param）")
    tree = parse_arxiv_query(param)

    def _predicate(stub: PaperStub) -> bool:
        return _evaluate_arxiv_query(tree, stub)

    return _predicate


# 谓词注册表：名字 → **构造器**（Phase 7 T9 改造，见模块 docstring"谓词注册"段）。
# 新增源专属谓词只需在此添加一项，无需改动 `filter_papers` 的控制流。
PREDICATE_REGISTRY: dict[str, PredicateConstructor] = {
    SSRN_TOPIC_FILTER: _construct_ssrn_topic_filter,
    ARXIV_QUERY_BOOL: _construct_arxiv_query_bool,
}


@dataclass(frozen=True)
class FilteredPaper:
    """通过本地过滤的一条 `PaperStub` + 命中的规则标记（喂 `ReportEntry.matched_rules`）。"""

    stub: PaperStub
    matched_rules: tuple[str, ...] = ()


def build_predicate(name: str, param: str = "") -> PredicateFn:
    """按名字从 `PREDICATE_REGISTRY` 取构造器并绑定 `param`，返回可反复调用的
    `PaperStub -> bool` 闭包（Phase 7 T9）。

    未登记的名字响亮报错（`ValueError`，同 `merge.SOURCE_PRIORITY` 未知 source 先例）
    ——不静默视为"不通过"或"通过"，两种默认都可能悄悄吞掉一个真实的接线错误。
    `param` 留空串给不需要订阅级参数的谓词（如 `ssrn.topic_filter`）。
    """
    try:
        constructor = PREDICATE_REGISTRY[name]
    except KeyError:
        raise ValueError(
            f"未登记的本地补偿谓词 {name!r}（已登记: {sorted(PREDICATE_REGISTRY)}）"
        ) from None
    return constructor(param)


def apply_predicate(name: str, stub: PaperStub, *, param: str = "") -> bool:
    """按名字取谓词（可选带订阅级 `param`）并对单个 `stub` 求值。

    便于测试/一次性直调；批量过滤场景见 `filter_papers`——它对同一谓词只构造一次
    （尤其 `arxiv.query_bool` 的语法树解析只做一次），不会像本函数这样每次都重新
    构造。
    """
    return build_predicate(name, param)(stub)


def _compile_case_insensitive(pattern: str) -> Pattern[str]:
    """大小写不敏感重编译（`LocalFilter` 校验期只保证可编译，未固定 flags）。"""
    return re_compile(pattern, IGNORECASE)


def filter_papers(
    stubs: Iterable[PaperStub],
    filters: LocalFilter,
    *,
    extra_predicates: Sequence[str] = (),
    predicate_params: Mapping[str, str] | None = None,
) -> list[FilteredPaper]:
    """对 `stubs` 流应用 `filters`（+ 可选源专属 `extra_predicates`），返回通过项。

    `extra_predicates` 里的每个名字须已在 `PREDICATE_REGISTRY` 登记，且在遍历 `stubs`
    **之前**一次性校验完毕——即使 `stubs` 为空，未登记的名字也会立即报错（不依赖
    "恰好有数据流过"才暴露接线错误）。`predicate_params`（Phase 7 T9 新增）按名字
    给需要订阅级参数的谓词（如 `arxiv.query_bool`）供参——每个谓词只在遍历 `stubs`
    **之前**构造一次（`PREDICATE_REGISTRY` 的构造器只调一次，非逐 paper 重复解析），
    未在 `predicate_params` 里出现的名字取空参数（免参谓词如 `ssrn.topic_filter`
    的正常形态）。

    通过条件（全部满足）：`exclude_regex` 无一命中 AND（`title_regex_any` 为空 OR 命中
    其一）AND（`min_year` 为空 OR `year` 达标）AND 全部 `extra_predicates` 都返回 True。
    返回顺序 = 输入顺序（不重排、不去重——去重是 `guard.dedupe_against_library` 的职责）。
    """
    unknown = sorted({name for name in extra_predicates if name not in PREDICATE_REGISTRY})
    if unknown:
        raise ValueError(f"未登记的本地补偿谓词 {unknown}（已登记: {sorted(PREDICATE_REGISTRY)}）")

    params = predicate_params or {}
    bound_predicates = [
        (name, build_predicate(name, params.get(name, ""))) for name in extra_predicates
    ]

    title_patterns = [_compile_case_insensitive(p) for p in filters.title_regex_any]
    exclude_patterns = [_compile_case_insensitive(p) for p in filters.exclude_regex]

    kept: list[FilteredPaper] = []
    for stub in stubs:
        title = stub.title

        if exclude_patterns and any(pattern.search(title) for pattern in exclude_patterns):
            continue

        rules: list[str] = []

        if title_patterns:
            hits = [index for index, pattern in enumerate(title_patterns) if pattern.search(title)]
            if not hits:
                continue
            rules.extend(f"{LOCAL_PREDICATE_TITLE_REGEX_ANY}[{index}]" for index in hits)

        if filters.min_year is not None:
            if stub.year is None or stub.year < filters.min_year:
                continue
            rules.append(LOCAL_PREDICATE_MIN_YEAR)

        if bound_predicates:
            failed = False
            for name, predicate in bound_predicates:
                if predicate(stub):
                    rules.append(name)
                else:
                    failed = True
                    break
            if failed:
                continue

        kept.append(FilteredPaper(stub=stub, matched_rules=tuple(rules)))

    return kept


__all__ = [
    "ARXIV_QUERY_BOOL",
    "PREDICATE_REGISTRY",
    "SSRN_TOPIC_FILTER",
    "FilteredPaper",
    "PredicateConstructor",
    "PredicateFn",
    "apply_predicate",
    "build_predicate",
    "filter_papers",
    "reset_predicate_warnings",
]
