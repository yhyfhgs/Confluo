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
- **`entries` 在熔断路径下的含义**：本渲染器假设 `entries` 在熔断时仍由 T5
  填充为本地过滤+去重后的全量候选（供"过载分布"按来源/分类聚合），只是
  **不**展示逐条"新增清单"表格——design/09 §6.1 熔断只产出"过载报告"，逐条
  列出成百条标题不是过载报告该做的事。若 T5 的实现选择熔断时不填充
  `entries`，过载分布退化为空表占位行（"-"/0），不报错、不崩溃。
- **过载分布的接缝**（plan §4 T6"接缝裁决"③）：本卡完成时 main 尚无
  `subs/guard.py`（T3 未合并），`OverloadReport` 类型不存在。本模块因此不
  导入 T3 任何东西——分布完全由本模块自行从 `RunSummary.entries` 的
  `source`/`categories` 字段聚合计算，并在渲染文本内注明这是过渡实现，供
  T5 集成 T3 后与正式 `OverloadReport` 口径对齐（若不一致）。
- **凭证脱敏纵深防御**（Global Constraints §6，同 `pipeline/report.py`/
  `unpaywall/report.py` 先例）：`FailureEvent.message` 是自由文本，可能透传
  上游异常消息——渲染前经 `obslog.redact()` 处理。
- **风格对齐**：不用 emoji/加粗/引用块——`pipeline/report.py`/
  `unpaywall/report.py` 两份既有报告渲染器都只用标题/列表/表格三种 markdown
  构造 + 朴素中文陈述句，本模块照此风格对齐（审查依据）。
"""

from __future__ import annotations

from collections.abc import Sequence

from paper_crawler.obslog import redact
from paper_crawler.subs.types import FailureEvent, ReportEntry, RunSummary

_OVERLOAD_SEAM_NOTE = (
    "注：过载分布基于本次运行 entries 的来源/分类聚合计算——main 当前无 "
    "`subs/guard.py`（T3 `OverloadReport` 未合并）；正式接入后如聚合口径不同，"
    "需在 T5 集成时对齐（phase6-implementation-plan.md §4 T6 接缝裁决）。"
)


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
# 过载分布（熔断专属；接缝见模块 docstring）
# ---------------------------------------------------------------------------


def _overload_section(summary: RunSummary) -> list[str]:
    source_counts = _count_sources(summary.entries)
    category_counts = _count_categories(summary.entries)

    lines = [
        f"熔断：本次新增 {summary.new_count} 篇超过阈值 {summary.guard_limit}"
        "（guard.max_new_per_run），已按护栏规则暂停入库；请收窄查询条件后重试。",
        "",
        "### 过载分布",
        "",
        _OVERLOAD_SEAM_NOTE,
        "",
        "按来源分布：",
        "",
        *_distribution_table("来源", source_counts),
        "",
        "按分类分布：",
        "",
        *_distribution_table("分类", category_counts),
        "",
        _narrowing_suggestion(source_counts, category_counts, len(summary.entries)),
    ]
    return lines


def _count_sources(entries: Sequence[ReportEntry]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for entry in entries:
        if entry.source:
            counts[entry.source] = counts.get(entry.source, 0) + 1
    return counts


def _count_categories(entries: Sequence[ReportEntry]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for entry in entries:
        for category in entry.categories:
            counts[category] = counts.get(category, 0) + 1
    return counts


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
    source_counts: dict[str, int], category_counts: dict[str, int], total: int
) -> str:
    if not source_counts and not category_counts:
        return "收窄建议：暂无可用于建议收窄的来源/分类分布数据。"

    parts: list[str] = []
    if source_counts:
        name, count = _sorted_counts(source_counts)[0]
        pct = count / total if total else 0.0
        parts.append(f"来源 `{name}`（{count} 篇，占 {pct:.1%}）")
    if category_counts:
        name, count = _sorted_counts(category_counts)[0]
        pct = count / total if total else 0.0
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
