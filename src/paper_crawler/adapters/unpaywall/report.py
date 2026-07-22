"""OA 命中率报告（T5 DoD 第二项；design/adapters/aggregators.md §5.5）。

对给定 DOI 集合做**单 DOI `GET /v2/{doi}` 循环**（无批量端点——`POST /v2/dois` 从勘察
到详设全程未 [LIVE] 验证响应结构，已裁决删除，见 aggregators.md 修订记录 #6/plan §4）→
聚合 `{总数, is_oa 数/命中率, 各 oa_status 计数, 有 pdf 直链数, 仅 landing 数, 未收录数,
查询出错数}` + 逐条清单，产出 markdown。

纯函数层（同 `verify.py`/`canary.py` 的既有分工：不做 CLI 接线、不做 DB 查询、不发
HTTP 请求本身）：`build_oa_report` 只消费调用方传入的 `lookup` 可调用对象（通常是
`UnpaywallAdapter.lookup` 的绑定方法），CLI 侧负责取 DOI 集合与装配 adapter/http
client（`cli.py` 的 `oa-report` 命令）。单个 DOI 查询失败（`CrawlerError`，如限速/
瞬时故障）不中断整份报告——记为 `outcome="error"` 一行并继续下一个 DOI，避免 100+
DOI 的报告因个别请求故障整体失败。
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Literal

from paper_crawler.adapters.unpaywall import parse
from paper_crawler.errors import CrawlerError
from paper_crawler.obslog import redact

Outcome = Literal["hit_pdf", "hit_landing_only", "hit_no_location", "not_oa", "not_found", "error"]

_OUTCOME_LABEL: dict[Outcome, str] = {
    "hit_pdf": "hit_pdf",
    "hit_landing_only": "hit_landing_only",
    "hit_no_location": "hit_no_location",
    "not_oa": "not_oa (closed)",
    "not_found": "not_found (404)",
    "error": "error",
}


@dataclass(frozen=True)
class OaReportRow:
    """单个 DOI 的查询结果一行（逐条清单）。"""

    doi: str
    outcome: Outcome
    is_oa: bool | None
    oa_status: str | None
    version: str | None
    pdf_url: str | None
    landing_url: str | None
    note: str


@dataclass(frozen=True)
class OaReport:
    """一次 OA 命中率报告的聚合结果。"""

    total: int
    rows: tuple[OaReportRow, ...]

    @property
    def is_oa_count(self) -> int:
        """`is_oa=true` 的数量——「OA 命中率」的分子（命中=unpaywall 认定其为 OA，
        不论我们能否实际取到 pdf 直链）。"""
        return sum(1 for row in self.rows if row.is_oa)

    @property
    def hit_rate(self) -> float:
        return self.is_oa_count / self.total if self.total else 0.0

    @property
    def pdf_count(self) -> int:
        return sum(1 for row in self.rows if row.outcome == "hit_pdf")

    @property
    def landing_only_count(self) -> int:
        return sum(1 for row in self.rows if row.outcome == "hit_landing_only")

    @property
    def not_found_count(self) -> int:
        return sum(1 for row in self.rows if row.outcome == "not_found")

    @property
    def error_count(self) -> int:
        return sum(1 for row in self.rows if row.outcome == "error")

    def oa_status_counts(self) -> dict[str, int]:
        """`oa_status` 分布（gold/green/hybrid/bronze/closed），按枚举值计数。"""
        counts: dict[str, int] = {}
        for row in self.rows:
            if row.oa_status is not None:
                counts[row.oa_status] = counts.get(row.oa_status, 0) + 1
        return counts


def _row_for_record(doi: str, record: parse.UnpaywallRecord | None) -> OaReportRow:
    if record is None:
        return OaReportRow(
            doi=doi,
            outcome="not_found",
            is_oa=None,
            oa_status=None,
            version=None,
            pdf_url=None,
            landing_url=None,
            note="not indexed by unpaywall (404)",
        )

    if not record.is_oa:
        return OaReportRow(
            doi=doi,
            outcome="not_oa",
            is_oa=False,
            oa_status=record.oa_status,
            version=None,
            pdf_url=None,
            landing_url=None,
            note="",
        )

    location = parse.select_pdf_location(record)
    if location is not None and location.url_for_pdf:
        note = "informal (non-final) version" if location.version in parse.INFORMAL_VERSIONS else ""
        return OaReportRow(
            doi=doi,
            outcome="hit_pdf",
            is_oa=True,
            oa_status=record.oa_status,
            version=location.version,
            pdf_url=location.url_for_pdf,
            landing_url=None,
            note=note,
        )

    landing = parse.landing_url_of(record)
    if landing:
        best_version = record.best_oa_location.version if record.best_oa_location else None
        return OaReportRow(
            doi=doi,
            outcome="hit_landing_only",
            is_oa=True,
            oa_status=record.oa_status,
            version=best_version,
            pdf_url=None,
            landing_url=landing,
            note="landing page only, no pdf link anywhere (J4 ruling: not downloaded)",
        )

    # 罕见边界：is_oa=true 但既无 pdf 也无 landing（响应字段异常稀疏）。
    return OaReportRow(
        doi=doi,
        outcome="hit_no_location",
        is_oa=True,
        oa_status=record.oa_status,
        version=None,
        pdf_url=None,
        landing_url=None,
        note="is_oa=true but no oa_location details in response",
    )


def build_oa_report(
    dois: Sequence[str], lookup: Callable[[str], parse.UnpaywallRecord | None]
) -> OaReport:
    """DOI 清单 → 逐个 `lookup(doi)` → 聚合 `OaReport`（单 DOI GET 循环，无批量端点）。

    `lookup` 通常是 `UnpaywallAdapter.lookup` 的绑定方法（`str -> UnpaywallRecord | None`，
    `None` = 404/未收录）；单次查询抛 `CrawlerError`（限速/瞬时故障/畸形响应等）不中断
    整份报告循环——记一行 `outcome="error"`（`note` 含 error_class，经 `redact()` 防御性
    脱敏）后继续下一个 DOI。
    """
    rows: list[OaReportRow] = []
    for doi in dois:
        try:
            record = lookup(doi)
        except CrawlerError as exc:
            rows.append(
                OaReportRow(
                    doi=doi,
                    outcome="error",
                    is_oa=None,
                    oa_status=None,
                    version=None,
                    pdf_url=None,
                    landing_url=None,
                    note=redact(f"{exc.error_class.value}: {exc}"),
                )
            )
            continue
        rows.append(_row_for_record(doi, record))
    return OaReport(total=len(dois), rows=tuple(rows))


def _escape_cell(text: str) -> str:
    return text.replace("|", "\\|") if text else "-"


def render_oa_report_markdown(report: OaReport) -> str:
    """聚合统计 + 逐条清单的 markdown（T5 DoD 第二项）。"""
    status_counts = report.oa_status_counts()
    lines = [
        "# Unpaywall OA 命中率报告",
        "",
        f"- 总数: {report.total}",
        f"- is_oa 命中数: {report.is_oa_count}（命中率 {report.hit_rate:.1%}）",
        f"- 有 pdf 直链: {report.pdf_count}",
        f"- 仅 landing（无 pdf 直链）: {report.landing_only_count}",
        f"- 未收录（404）: {report.not_found_count}",
        f"- 查询出错: {report.error_count}",
        "",
        "## oa_status 分布",
        "",
        "| oa_status | 数量 |",
        "| --- | --- |",
    ]
    if status_counts:
        lines.extend(f"| {status} | {count} |" for status, count in sorted(status_counts.items()))
    else:
        lines.append("| - | 0 |")
    lines.extend(
        [
            "",
            "## 逐条清单",
            "",
            "| doi | outcome | oa_status | version | note |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for row in report.rows:
        lines.append(
            "| "
            + " | ".join(
                _escape_cell(cell)
                for cell in (
                    row.doi,
                    _OUTCOME_LABEL[row.outcome],
                    row.oa_status or "",
                    row.version or "",
                    row.note,
                )
            )
            + " |"
        )
    return "\n".join(lines) + "\n"


__all__ = [
    "OaReport",
    "OaReportRow",
    "Outcome",
    "build_oa_report",
    "render_oa_report_markdown",
]
