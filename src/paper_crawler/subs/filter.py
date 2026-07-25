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

## 谓词注册（源专属本地补偿）

`title_regex_any`/`exclude_regex`/`min_year` 是**订阅级**、跨源统一的条件；某些源还带
**源专属**的固定补偿谓词——例如 ssrn `quirks.topic_filter`（`venues/econ/ssrn.yaml`，
econ/fin 主题近似过滤，design/adapters/ssrn.md §3）尚未有 DSL 字段承载，是源自身固定
策略，不属于用户在订阅文件里声明的 `filters:`。这类谓词用 `"<source>.<name>"` 命名
（`subs.types` 模块 docstring 约定），登记进 `PREDICATE_REGISTRY`，T2 编译产出的
`PlanStep.local_predicates` 若含这类标记，调用方（T5）经 `extra_predicates=` 传入本模块
一并执行。**未登记的名字响亮报错**（`ValueError`，同 `merge.py` 未知 `source` 先例：
`raise ValueError(f"unknown source {source!r}; must be one of ...")`）——一个拼错的
谓词名绝不能被静默跳过；校验在遍历 `stubs` **之前**完成，因此空输入流也会触发报错
（fail-loud 不依赖"恰好有数据流过"）。

当前唯一登记项 `SSRN_TOPIC_FILTER`（`"ssrn.topic_filter"`）直接复用
`adapters.ssrn.parse.topic_field_matches`/`stub_topic_field`（Phase 5 既有纯函数，
`stub.meta` 读 `TOPIC_FIELD_META_KEY`）——不复制这套近似过滤逻辑第二份。

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

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from re import IGNORECASE, Pattern
from re import compile as re_compile

from paper_crawler.adapters.ssrn.parse import stub_topic_field, topic_field_matches
from paper_crawler.obslog import log_event
from paper_crawler.subs.model import LocalFilter
from paper_crawler.subs.types import LOCAL_PREDICATE_MIN_YEAR, LOCAL_PREDICATE_TITLE_REGEX_ANY
from paper_crawler.types import PaperStub

# 一个源专属补偿谓词：`PaperStub` → 是否通过（True=保留，语义同 `topic_field_matches`）。
PredicateFn = Callable[[PaperStub], bool]

# ssrn econ/fin 主题近似过滤（design/adapters/ssrn.md §3；`venues/econ/ssrn.yaml`
# `quirks.topic_filter: econ_fin` 的运行期落点）。`"<source>.<name>"` 命名约定。
SSRN_TOPIC_FILTER = "ssrn.topic_filter"

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


# 谓词注册表（任务卡要求的"简单 dict 映射"）：名字 → 可调用。新增源专属谓词只需在此
# 添加一项，无需改动 `filter_papers` 的控制流。
PREDICATE_REGISTRY: dict[str, PredicateFn] = {
    SSRN_TOPIC_FILTER: _ssrn_topic_filter,
}


@dataclass(frozen=True)
class FilteredPaper:
    """通过本地过滤的一条 `PaperStub` + 命中的规则标记（喂 `ReportEntry.matched_rules`）。"""

    stub: PaperStub
    matched_rules: tuple[str, ...] = ()


def apply_predicate(name: str, stub: PaperStub) -> bool:
    """按名字从 `PREDICATE_REGISTRY` 取谓词并对 `stub` 求值。

    未登记的名字响亮报错（`ValueError`，同 `merge.SOURCE_PRIORITY` 未知 source 先例）
    ——不静默视为"不通过"或"通过"，两种默认都可能悄悄吞掉一个真实的接线错误。
    """
    try:
        predicate = PREDICATE_REGISTRY[name]
    except KeyError:
        raise ValueError(
            f"未登记的本地补偿谓词 {name!r}（已登记: {sorted(PREDICATE_REGISTRY)}）"
        ) from None
    return predicate(stub)


def _compile_case_insensitive(pattern: str) -> Pattern[str]:
    """大小写不敏感重编译（`LocalFilter` 校验期只保证可编译，未固定 flags）。"""
    return re_compile(pattern, IGNORECASE)


def filter_papers(
    stubs: Iterable[PaperStub],
    filters: LocalFilter,
    *,
    extra_predicates: Sequence[str] = (),
) -> list[FilteredPaper]:
    """对 `stubs` 流应用 `filters`（+ 可选源专属 `extra_predicates`），返回通过项。

    `extra_predicates` 里的每个名字须已在 `PREDICATE_REGISTRY` 登记，且在遍历 `stubs`
    **之前**一次性校验完毕——即使 `stubs` 为空，未登记的名字也会立即报错（不依赖
    "恰好有数据流过"才暴露接线错误）。

    通过条件（全部满足）：`exclude_regex` 无一命中 AND（`title_regex_any` 为空 OR 命中
    其一）AND（`min_year` 为空 OR `year` 达标）AND 全部 `extra_predicates` 都返回 True。
    返回顺序 = 输入顺序（不重排、不去重——去重是 `guard.dedupe_against_library` 的职责）。
    """
    unknown = sorted({name for name in extra_predicates if name not in PREDICATE_REGISTRY})
    if unknown:
        raise ValueError(f"未登记的本地补偿谓词 {unknown}（已登记: {sorted(PREDICATE_REGISTRY)}）")

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

        if extra_predicates:
            failed = False
            for name in extra_predicates:
                if apply_predicate(name, stub):
                    rules.append(name)
                else:
                    failed = True
                    break
            if failed:
                continue

        kept.append(FilteredPaper(stub=stub, matched_rules=tuple(rules)))

    return kept


__all__ = [
    "PREDICATE_REGISTRY",
    "SSRN_TOPIC_FILTER",
    "FilteredPaper",
    "PredicateFn",
    "apply_predicate",
    "filter_papers",
    "reset_predicate_warnings",
]
