"""日报渲染：`render_daily`（Phase 6 T6；design/09 §6 第 3 条 + plan §4 T6）。

纯函数渲染器——零 IO、零网络、零全局状态：只消费 `subs.types.RunSummary`
（T1 冻结件，本模块**只读**不改），把一天内一个或多个订阅的运行结果合并渲染成
一份 markdown 日报。文件名 `daily-YYYY-MM-DD.md` 的落盘由调用方（T5
`subs/watch.py`）负责——本模块不碰文件系统，`date` 只作为标题文本传入。

## 日报结构（design/09 §6 三要素 + plan §4 T6 补充；标题层级见下）

```
# 日报 — {date}
## 总览                —— 订阅/状态/新增/入库/熔断 一览表
## {subscription}      —— 每订阅一节，按传入顺序重复
### 新增清单            —— 非熔断且有新增时：标题/作者/链接/命中规则
### 过载分布            —— 仅熔断时：按来源/按分类分布 + 收窄建议
### 失败事件            —— 有失败事件时：来源/错误类型/消息（与熔断/新增清单正交）
## 累计库存             —— 尾部：全部订阅的库存汇总表
```

零订阅、或有订阅但零新增（"空日"）也产出合法文档：零订阅时整份文档只有标题 +
一句明确的"无新增"陈述；有订阅但某订阅零新增（且未熔断）时，该订阅节内直接
一句"无新增论文。"——两种情形都不留半截结构或空标题。

## 设计决策（冻结件字段未显式规定的推断，供审查核对）

- **dry-run 标记**：`RunSummary.dry_run=True` 的订阅在"状态"处追加
  "（预览，未入库）"（总览表与每订阅节的状态行都追加）。`dry_run` 与
  `outcome`/`truncated` 正交（`subs/types.py` 模块 docstring已述）——故熔断
  提示文案不因 dry-run 而改变措辞："未入库"陈述在两种情形下都成立（真实熔断=
  护栏拦截；dry-run=预览本就不入库），状态行的标记已足够区分原因。
- **过载分布的数据源（双路径，T5 卡已裁决歧义③+T6 设计决策）**：T1b 接缝终裁
  后 `RunSummary.distribution` 是 `(axis, label, count)` 三元组序列
  （`axis ∈ {"source", "category"}`，T5 从 `subs.guard.OverloadReport` 的
  `by_source`/`by_category` 两轴分布打标签拼装）——本模块**优先**消费它：非空时
  按 `axis` 过滤拆回"按来源分布"/"按分类分布"两张表，不再自行从 `entries`
  聚合。`distribution` 为空（T5 该路径未装配，或熔断时确实只带 distribution
  不带全量 `entries` 的场景）时，退化为旧路径——本模块自行从 `entries` 的
  `source`/`categories` 字段聚合（`_count_sources`/`_count_categories`，同
  `subs.guard._counts_by` 的条目内标签去重修法对齐）；两条路径共享同一张表格
  渲染与收窄建议逻辑，只是计数字典的来源不同。收窄建议句始终由本模块（而非
  `narrowing_hints`——该字段 T5 现阶段恒留空，`subs/types.py` `RunSummary`
  docstring 已述）从（无论哪条路径产出的）计数现算，分母统一用
  `RunSummary.new_count`（而非 `len(entries)`——熔断时 `entries` 可能不完整
  或为空，`new_count` 才是护栏比对时的权威净新增数）。
- **`entries` 在熔断路径下的含义（entries-派生兜底路径专属）**：仅当
  `distribution` 为空、退化到 entries 兜底聚合时才涉及——本渲染器假设此时
  `entries` 仍由 T5 填充为本地过滤+去重后的全量候选。无论走哪条数据源路径，
  熔断时都**不**展示逐条"新增清单"表格——design/09 §6.1 熔断只产出"过载报告"，
  逐条列出成百条标题不是过载报告该做的事。两条路径下若聚合结果仍为空，过载
  分布退化为空表占位行（"-"/0），不报错、不崩溃。
- **凭证脱敏纵深防御**（Global Constraints §6，同 `pipeline/report.py`/
  `unpaywall/report.py` 先例）：`FailureEvent.message` 是自由文本，可能透传
  上游异常消息——渲染前经 `obslog.redact()` 处理。
- **风格对齐**：不用 emoji/加粗/引用块——`pipeline/report.py`/
  `unpaywall/report.py` 两份既有报告渲染器都只用标题/列表/表格三种 markdown
  构造 + 朴素中文陈述句，本模块照此风格对齐（审查依据）。
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence

from paper_crawler.obslog import redact
from paper_crawler.subs.types import FailureEvent, ReportEntry, RunSummary

_AXIS_SOURCE = "source"
_AXIS_CATEGORY = "category"


def render_daily(summaries: Sequence[RunSummary], *, date: str) -> str:
    """把一天内一个或多个订阅的 `RunSummary` 合并渲染为一份日报 markdown。

    多订阅合并一份文档（design/09 §6 第 3 条："多订阅合并一份
    `daily-YYYY-MM-DD.md`"）；零订阅/零新增亦产合法文档（见模块 docstring）。
    纯函数：不做任何 IO，`date` 仅用于标题文本，落盘路径与文件名由调用方决定。
    """
    lines: list[str] = [f"# 日报 — {date}", ""]

    if not summaries:
        lines.append("今日无订阅运行记录，无新增论文。")
        lines.append("")
        return "\n".join(lines)

    lines.extend(_overview_section(summaries))

    for summary in summaries:
        lines.append("")
        lines.extend(_subscription_section(summary))

    lines.append("")
    lines.extend(_inventory_section(summaries))
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 总览（头部）
# ---------------------------------------------------------------------------


def _overview_section(summaries: Sequence[RunSummary]) -> list[str]:
    lines = [
        "## 总览",
        "",
        "| 订阅 | 状态 | 新增 | 入库 | 熔断 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for summary in summaries:
        lines.append(
            "| "
            + " | ".join(
                _escape_cell(cell)
                for cell in (
                    summary.subscription,
                    _status_label(summary),
                    str(summary.new_count),
                    str(summary.ingested_count),
                    "熔断" if summary.truncated else "",
                )
            )
            + " |"
        )
    return lines


def _status_label(summary: RunSummary) -> str:
    """`outcome` 字面值 + dry-run 标记（正交拼接，见模块 docstring "设计决策"）。"""
    suffix = "（预览，未入库）" if summary.dry_run else ""
    return f"{summary.outcome.value}{suffix}"


# ---------------------------------------------------------------------------
# 每订阅一节
# ---------------------------------------------------------------------------


def _subscription_section(summary: RunSummary) -> list[str]:
    lines = [
        f"## {summary.subscription}",
        "",
        f"- 状态: {_status_label(summary)}",
        f"- 新增: {summary.new_count}",
        f"- 入库: {summary.ingested_count}",
        f"- 累计库存: {summary.library_total}",
    ]

    if summary.truncated:
        lines.append("")
        lines.extend(_overload_section(summary))
    elif summary.entries:
        lines.append("")
        lines.extend(_entries_section(summary.entries))
    else:
        lines.append("")
        lines.append("无新增论文。")

    if summary.failures:
        lines.append("")
        lines.extend(_failures_section(summary.failures))

    return lines


def _entries_section(entries: Sequence[ReportEntry]) -> list[str]:
    """ "新增清单"（design/09 §6.3）：标题/作者/链接/命中的过滤规则。"""
    lines = [
        "### 新增清单",
        "",
        "| 标题 | 作者 | 链接 | 命中规则 |",
        "| --- | --- | --- | --- |",
    ]
    for entry in entries:
        lines.append(
            "| "
            + " | ".join(
                _escape_cell(cell)
                for cell in (
                    entry.title,
                    _join_or_dash(entry.authors),
                    entry.url,
                    _join_or_dash(entry.matched_rules),
                )
            )
            + " |"
        )
    return lines


def _failures_section(failures: Sequence[FailureEvent]) -> list[str]:
    """ "失败与熔断事件"段的失败部分（design/09 §6.3）；message 经 redact() 纵深防御。"""
    lines = [
        "### 失败事件",
        "",
        "| 来源 | 错误类型 | 消息 |",
        "| --- | --- | --- |",
    ]
    for failure in failures:
        lines.append(
            "| "
            + " | ".join(
                _escape_cell(cell)
                for cell in (failure.source, failure.error_class, redact(failure.message))
            )
            + " |"
        )
    return lines


# ---------------------------------------------------------------------------
# 过载分布（熔断专属；数据源优先级见模块 docstring "过载分布的数据源"）
# ---------------------------------------------------------------------------


def _overload_section(summary: RunSummary) -> list[str]:
    source_counts, category_counts = _resolve_distribution(summary)

    lines = [
        f"熔断：本次新增 {summary.new_count} 篇超过阈值 {summary.guard_limit}"
        "（guard.max_new_per_run），已按护栏规则暂停入库；请收窄查询条件后重试。",
        "",
        "### 过载分布",
        "",
        "按来源分布：",
        "",
        *_distribution_table("来源", source_counts),
        "",
        "按分类分布：",
        "",
        *_distribution_table("分类", category_counts),
        "",
        _narrowing_suggestion(source_counts, category_counts, summary.new_count),
    ]
    return lines


def _resolve_distribution(summary: RunSummary) -> tuple[dict[str, int], dict[str, int]]:
    """按 axis 拆 `RunSummary.distribution` 为（来源计数, 分类计数）——优先路径。

    `distribution` 非空时以它为准（T5 从 `subs.guard.OverloadReport` 装配，权威
    数据源）；为空时退化为从 `entries` 自行聚合（旧路径，兜底不报错——熔断时
    `entries` 可能不完整或本就为空，见模块 docstring）。
    """
    if summary.distribution:
        source_counts = _counts_from_distribution(summary.distribution, _AXIS_SOURCE)
        category_counts = _counts_from_distribution(summary.distribution, _AXIS_CATEGORY)
        return source_counts, category_counts
    return _count_sources(summary.entries), _count_categories(summary.entries)


def _counts_from_distribution(
    distribution: Sequence[tuple[str, str, int]], axis: str
) -> dict[str, int]:
    """`distribution` 里 `axis` 匹配的 `(label, count)` 项 → 计数字典（同 label 累加，防御性）。"""
    counts: dict[str, int] = {}
    for item_axis, label, count in distribution:
        if item_axis == axis:
            counts[label] = counts.get(label, 0) + count
    return counts


def _counts_by(
    entries: Sequence[ReportEntry], labels_of: Callable[[ReportEntry], Iterable[str]]
) -> dict[str, int]:
    """entries 兜底路径的通用计数：按 `labels_of` 抽取的标签计数。

    **条目内去重、跨条目正常累计**——与 `subs.guard._counts_by` 同款修法对齐
    （审查 P2#4）：`labels_of(entry)` 在同一条目内重复的标签（如
    `ReportEntry.categories` 内 arXiv 主分类与 cross-list 同值）只计一次
    （`dict.fromkeys` 保序去重），否则单条目内的重复会让某个桶的计数超过实际
    拥有该标签的条目数，收窄建议算出的份额可能溢出 100%。
    """
    counts: dict[str, int] = {}
    for entry in entries:
        for label in dict.fromkeys(labels_of(entry)):
            counts[label] = counts.get(label, 0) + 1
    return counts


def _count_sources(entries: Sequence[ReportEntry]) -> dict[str, int]:
    return _counts_by(entries, lambda entry: (entry.source,) if entry.source else ())


def _count_categories(entries: Sequence[ReportEntry]) -> dict[str, int]:
    return _counts_by(entries, lambda entry: entry.categories)


def _sorted_counts(counts: dict[str, int]) -> list[tuple[str, int]]:
    """按计数降序、同计数按名称升序——聚合口径与输入序无关，保证渲染确定性。"""
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))


def _distribution_table(header: str, counts: dict[str, int]) -> list[str]:
    lines = [f"| {header} | 数量 |", "| --- | --- |"]
    rows = _sorted_counts(counts)
    if rows:
        lines += [f"| {_escape_cell(name)} | {count} |" for name, count in rows]
    else:
        lines.append("| - | 0 |")
    return lines


def _narrowing_suggestion(
    source_counts: dict[str, int], category_counts: dict[str, int], new_count: int
) -> str:
    """双轴收窄建议句（本模块生成，不消费 `RunSummary.narrowing_hints`——该字段
    T5 现阶段恒留空）。分母用 `new_count`（`RunSummary.new_count`，护栏比对的权威
    净新增数），不用 `len(entries)`——熔断时 `entries` 可能不完整或为空。
    """
    if not source_counts and not category_counts:
        return "收窄建议：暂无可用于建议收窄的来源/分类分布数据。"

    parts: list[str] = []
    if source_counts:
        name, count = _sorted_counts(source_counts)[0]
        pct = count / new_count if new_count else 0.0
        parts.append(f"来源 `{name}`（{count} 篇，占 {pct:.1%}）")
    if category_counts:
        name, count = _sorted_counts(category_counts)[0]
        pct = count / new_count if new_count else 0.0
        parts.append(f"分类 `{name}`（{count} 篇，占 {pct:.1%}）")
    return "收窄建议：优先考虑收窄 " + " 或 ".join(parts) + "。"


# ---------------------------------------------------------------------------
# 尾部：累计库存
# ---------------------------------------------------------------------------


def _inventory_section(summaries: Sequence[RunSummary]) -> list[str]:
    lines = [
        "## 累计库存",
        "",
        "| 订阅 | 累计库存 |",
        "| --- | --- |",
    ]
    for summary in summaries:
        lines.append(f"| {_escape_cell(summary.subscription)} | {summary.library_total} |")
    return lines


# ---------------------------------------------------------------------------
# 共享小工具
# ---------------------------------------------------------------------------


def _escape_cell(text: str) -> str:
    """表格单元格转义（同 `unpaywall/report.py` 先例）：`|` 转义、空值兜底 "-"。"""
    return text.replace("|", "\\|") if text else "-"


def _join_or_dash(items: Sequence[str]) -> str:
    return ", ".join(items) if items else "-"


__all__ = ["render_daily"]
