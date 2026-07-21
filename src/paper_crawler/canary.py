"""adapter 健康矩阵组装（T3 落地；design phase2-implementation-plan §2.4，
test-plan.md §4/§9）。

纯函数层：遍历一组已注册 adapter，逐个调用 `healthcheck()`，把结果规整成健康
矩阵行（`CanaryRow`）与 markdown 渲染；不含 CLI 接线（那部分归 `cli.py` 的
`canary` 命令，负责 `load_adapters()`/`--adapter` 过滤/`_env` 环境装配）。

三种结果分类：

- **healthy**：`adapter.healthcheck()` 正常返回且 `HealthReport.healthy` 为真；
- **unhealthy**：正常返回但 `healthy=False`，或 `healthcheck()` 抛出除
  `NotImplementedError` 外的任意异常（真实站点探测失败、网络错误等）——两者
  都计入"存在不健康"，决定 CLI 退出码；
- **skip**：`healthcheck()` 抛 `NotImplementedError`——stub adapter（如
  Phase 2 前的 crossref/openreview/elsevier_sd）尚未实现健康检查，属于"未实现"
  而非"不健康"，不影响退出码（phase2-implementation-plan T3 任务卡明文）。

本模块只实现 test-plan.md §4 里最基础的一层——"adapter 能否正常应答"。
§4 描述的更细粒度分类（PASS/DRIFT/DEGRADED/BLOCKED，基于每个 adapter 注册的
"已知答案样本"比对）是后续 adapter 落地时才会叠加的更高层能力（如 arxiv 的
T7 canary 三样本注册），T3 阶段尚不实现，`§4` 既有语义不因本模块改动。

`detail` 文本一律先经 `obslog.redact()` 处理——健康检查异常消息可能透传上游
文本（未来真实 adapter 的 HTTP 错误信息等），与 `RunReport.render_markdown()`
同样的纵深防御口径（AC-0 红线："日志与报告无未脱敏敏感值"）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from paper_crawler.adapter import SourceAdapter
from paper_crawler.obslog import redact

CanaryStatus = Literal["healthy", "unhealthy", "skip"]

_STATUS_LABEL: dict[CanaryStatus, str] = {
    "healthy": "healthy",
    "unhealthy": "unhealthy",
    "skip": "SKIP",
}


@dataclass(frozen=True)
class CanaryRow:
    """健康矩阵的一行：一个 adapter 的探测结果。"""

    adapter_id: str
    status: CanaryStatus
    detail: str


def run_canary(adapters: dict[str, SourceAdapter]) -> list[CanaryRow]:
    """对每个 adapter 调用 `healthcheck()`，按 adapter_id 排序返回结果行。

    排序保证确定性输出（同一份 adapter 集合每次跑出的行序一致，与
    `VenueRegistry.all()` 按 id 排序的既有约定同口径）。任何单个 adapter 的
    异常都会被捕获归类，不会让整次 canary 因某个 adapter 报错而中断
    （canary 的存在意义就是探测"谁不健康"，探测过程本身必须健壮）。
    """
    rows: list[CanaryRow] = []
    for adapter_id in sorted(adapters):
        adapter = adapters[adapter_id]
        try:
            report = adapter.healthcheck()
        except NotImplementedError as exc:
            rows.append(CanaryRow(adapter_id, "skip", redact(str(exc) or "未实现")))
        except Exception as exc:  # 广捕：单个 adapter 异常不能拖垮整次 canary 探测
            rows.append(CanaryRow(adapter_id, "unhealthy", redact(f"{type(exc).__name__}: {exc}")))
        else:
            status: CanaryStatus = "healthy" if report.healthy else "unhealthy"
            rows.append(CanaryRow(adapter_id, status, redact(report.detail)))
    return rows


def canary_exit_code(rows: list[CanaryRow]) -> int:
    """canary 命令的退出码判据：0 = 无 unhealthy（SKIP 不影响）；1 = 至少一个 unhealthy。"""
    return 1 if any(row.status == "unhealthy" for row in rows) else 0


def render_canary_markdown(rows: list[CanaryRow]) -> str:
    """健康矩阵 markdown 表格：adapter / healthy / detail 三列（test-plan §4/§9）。"""
    lines = ["| adapter | healthy | detail |", "| --- | --- | --- |"]
    for row in rows:
        detail = row.detail.replace("|", "\\|") or "-"
        lines.append(f"| {row.adapter_id} | {_STATUS_LABEL[row.status]} | {detail} |")
    return "\n".join(lines)


__all__ = ["CanaryRow", "CanaryStatus", "canary_exit_code", "render_canary_markdown", "run_canary"]
