"""preprint↔published 关联报告（T16；AC-7.4 后半，design/06 §3 preprint_of 语义）。

纯函数渲染层（同 `adapters/unpaywall/report.py`/`subs/report.py`/`pipeline/report.py`
既有三处先例的分工：不做 DB 查询、不做 CLI 接线、零 IO）：`build_preprint_report` 只
消费 `storage.repo.Repo.list_preprint_relations()` 返回的只读行序列（`sqlite3.Row`），
`render_preprint_report_markdown` 将聚合结果渲染为 markdown。CLI 侧（`cli.py` 的
`preprint-report` 命令）负责装配 `Repo` 与 `typer.echo` 输出。

design/06 §3 preprint_of 语义锚点：**双条 paper 双份全文、不合并**——本报告只做只读
关联展示，不做任何写操作、不改变 `decided`/`paper_relation` 任何字段（T13
`dedupe review` 才是写入 `decided` 的唯一入口，preprint_of 尚无对应审核命令）。

## 报告结构
- 总览：边总数 + decided 分布（待复核/merged/rejected）。
- 逐边清单：按 published venue 分组（未挂靠 venue 的边归入统一的"（未挂靠 venue）"
  分组）——分组只是切段展示，组内顺序与分组出现顺序完全沿用输入行序，不重排；
  `Repo.list_preprint_relations()` 已产出"named venue 优先、NULL venue 殿后，组内
  按 year/标题"的确定性序（该方法 docstring），本模块的分组切段与之天然对齐。
- 空库/零边：响亮的一句陈述（"库内暂无 preprint_of 关联边（total=0）。"），不是
  静默空文档——同 `subs/report.py::render_daily` 零订阅路径先例。

## 设计决策（供审查核对）
- **表格列**：每边一行，preprint/published 各自"标题"列 + "venue/year"合并列
  （如 `ArXiv Mock (2024)`），另加"证据"列（`clue_key=clue_value`，folded 进
  provenance 标签）与"decided"列——六列。字段选择为本卡设计裁量（标题/venue/
  year/证据来源/decided），AC-7.4 原文仅要求"关联报告生成"、未列字段；venue 与
  year 合并展示同样是本卡设计裁量：分组取 venue 优先、组内按年升序，venue 缺失
  归尾组（"报告结构"节已述），列布局延伸同一裁量取舍，与表格宽度可读性权衡。
- **证据来源字段**（`evidence_source`）：解析自 `paper_relation.evidence_json` 的
  `source`（aggregator/`merge_ingest` 路径）或 `venue_id`（pull/`upsert_paper` 路径）
  ——`_apply_preprint_clues` docstring "二者互斥"，本模块按此优先取 `source`、
  其次 `venue_id`。畸形/缺失 evidence_json 不炸报告：证据字段全部降级为 `None`
  （防御性，同 `oa_report.build_oa_report` "单行故障不中断整体报告"的精神）。
- **decided 展示**：`None` 渲染为"待复核"（人类可读，非裸 `None`/空串）；非空值
  （`merged`/`rejected`）原样透出，不归一化措辞——报告是审计工具，如实展示比统一
  措辞更重要。
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass

_UNLINKED_VENUE_LABEL = "（未挂靠 venue）"
_PENDING_LABEL = "待复核"


@dataclass(frozen=True)
class PreprintRelationRow:
    """单条 preprint_of 边的展示行（`Repo.list_preprint_relations()` 一行的类型化包装）。"""

    preprint_id: str
    preprint_title: str
    preprint_venue: str | None
    preprint_year: int | None
    published_id: str
    published_title: str
    published_venue: str | None
    published_year: int | None
    clue_key: str | None
    clue_value: str | None
    evidence_source: str | None
    decided: str | None


@dataclass(frozen=True)
class PreprintReport:
    """一次 preprint_of 关联报告的聚合结果。"""

    total: int
    rows: tuple[PreprintRelationRow, ...]

    @property
    def pending_count(self) -> int:
        """`decided IS NULL`（待复核，design/06 §3"NULL=有效待复核"）的边数。"""
        return sum(1 for row in self.rows if row.decided is None)

    def decided_counts(self) -> dict[str, int]:
        """已人工裁决的边按 `decided` 值计数（`merged`/`rejected` 等，出现值才有键）。"""
        counts: dict[str, int] = {}
        for row in self.rows:
            if row.decided is not None:
                counts[row.decided] = counts.get(row.decided, 0) + 1
        return counts


def _evidence_fields(evidence_json: object) -> tuple[str | None, str | None, str | None]:
    """`paper_relation.evidence_json` → `(clue_key, clue_value, evidence_source)`。

    畸形 JSON / 非对象 / 缺失 → 三者全 `None`（防御性，见模块 docstring）。
    `evidence_source` 取 `source`（aggregator 路径）或 `venue_id`（pull 路径）——二者
    互斥（`_apply_preprint_clues` docstring），优先 `source`。
    """
    if not isinstance(evidence_json, str) or not evidence_json:
        return None, None, None
    try:
        parsed = json.loads(evidence_json)
    except json.JSONDecodeError:
        return None, None, None
    if not isinstance(parsed, dict):
        return None, None, None
    clue_key = parsed.get("clue_key")
    clue_value = parsed.get("clue_value")
    source_label = parsed.get("source")
    if source_label is None:
        source_label = parsed.get("venue_id")
    return (
        str(clue_key) if clue_key is not None else None,
        str(clue_value) if clue_value is not None else None,
        str(source_label) if source_label is not None else None,
    )


def build_preprint_report(rows: Sequence[sqlite3.Row]) -> PreprintReport:
    """`Repo.list_preprint_relations()` 行序列 → `PreprintReport`（纯聚合，零 IO）。"""
    report_rows: list[PreprintRelationRow] = []
    for row in rows:
        clue_key, clue_value, evidence_source = _evidence_fields(row["evidence_json"])
        report_rows.append(
            PreprintRelationRow(
                preprint_id=str(row["preprint_id"]),
                preprint_title=str(row["preprint_title"]),
                preprint_venue=row["preprint_venue"],
                preprint_year=row["preprint_year"],
                published_id=str(row["published_id"]),
                published_title=str(row["published_title"]),
                published_venue=row["published_venue"],
                published_year=row["published_year"],
                clue_key=clue_key,
                clue_value=clue_value,
                evidence_source=evidence_source,
                decided=row["decided"],
            )
        )
    return PreprintReport(total=len(report_rows), rows=tuple(report_rows))


def _escape_cell(text: str) -> str:
    return text.replace("|", "\\|") if text else "-"


def _venue_year_cell(venue: str | None, year: int | None) -> str:
    venue_label = venue or "-"
    year_label = str(year) if year is not None else "-"
    return f"{venue_label} ({year_label})"


def _evidence_cell(row: PreprintRelationRow) -> str:
    clue = f"{row.clue_key}={row.clue_value}" if row.clue_key and row.clue_value else None
    if clue and row.evidence_source:
        return f"{clue}（来源: {row.evidence_source}）"
    if clue:
        return clue
    if row.evidence_source:
        return f"来源: {row.evidence_source}"
    return "-"


def _decided_cell(decided: str | None) -> str:
    return decided if decided is not None else _PENDING_LABEL


def _group_label(published_venue: str | None) -> str:
    return published_venue if published_venue else _UNLINKED_VENUE_LABEL


def _edge_table(rows: Sequence[PreprintRelationRow]) -> list[str]:
    lines = [
        "| preprint 标题 | preprint venue/year | published 标题 | published venue/year "
        "| 证据来源 | decided |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                _escape_cell(cell)
                for cell in (
                    row.preprint_title,
                    _venue_year_cell(row.preprint_venue, row.preprint_year),
                    row.published_title,
                    _venue_year_cell(row.published_venue, row.published_year),
                    _evidence_cell(row),
                    _decided_cell(row.decided),
                )
            )
            + " |"
        )
    return lines


def render_preprint_report_markdown(report: PreprintReport) -> str:
    """聚合结果 → markdown（总览 + 按 published venue 分组的逐边清单）。"""
    lines = ["# preprint↔published 关联报告", ""]
    if report.total == 0:
        lines.append("库内暂无 preprint_of 关联边（total=0）。")
        lines.append("")
        return "\n".join(lines)

    decided_counts = report.decided_counts()
    lines += [
        f"- 边总数: {report.total}",
        f"- 待复核（decided 为空）: {report.pending_count}",
    ]
    for state in sorted(decided_counts):
        lines.append(f"- {state}: {decided_counts[state]}")
    lines += ["", "## 逐边清单", ""]

    groups: dict[str, list[PreprintRelationRow]] = {}
    order: list[str] = []
    for row in report.rows:
        label = _group_label(row.published_venue)
        if label not in groups:
            groups[label] = []
            order.append(label)
        groups[label].append(row)

    for label in order:
        lines.append(f"### {label}")
        lines.append("")
        lines.extend(_edge_table(groups[label]))
        lines.append("")

    return "\n".join(lines)


__all__ = [
    "PreprintReport",
    "PreprintRelationRow",
    "build_preprint_report",
    "render_preprint_report_markdown",
]
