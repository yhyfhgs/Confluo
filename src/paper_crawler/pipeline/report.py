"""运行报告：`RunReport`（接口冻结件 §2.7；design/05 §7 观测性）。

每次 pipeline 命令结束产出一份 markdown 摘要（成功/失败/阻塞/跳过计数、失败清单
top、下一步提示），并可落盘供 `crawler report [--last-run]` 重打印（design/05 §6/§7）。

设计决策（冻结件字段本身未显式携带 `dry_run: bool`，本模块据此推断，供 T7c/T8
runner/CLI 消费时对齐）：

- **dry-run 预览行**："将下载 N 篇 / 估 M MB" 行的显示条件是
  ``planned_downloads > 0 or planned_bytes > 0``。design/05 §6 只在 dry-run 路径
  产出这两个字段（实跑报告不设置），因此该条件天然等价于"这是一份 dry-run 报告"，
  无需额外字段即可复现两种渲染形态。
- **MB 换算**：按 1024*1024 字节（MiB，通俗标注为 MB，与常见文件管理器口径一致）
  为基数，保留 1 位小数。
- **凭证脱敏纵深防御**：Global Constraints §6（"日志/异常文本不得含凭证形态内容"）
  未把 RunReport 显式列为例外——`failures[].msg` 与 `notes` 都是自由文本，可能
  透传上游异常消息。渲染 markdown 与落盘 history.jsonl 前一律经
  `obslog.redact()` 处理，口径与 `log_event()` 一致（不信任调用方已脱敏）。
"""

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from paper_crawler.obslog import redact

_MAX_FAILURES_SHOWN = 10
_BYTES_PER_MB = 1024 * 1024


@dataclass
class RunReport:
    """一次 pipeline 命令运行的摘要（可变——runner 在执行过程中累积计数）。"""

    command: str
    venue_id: str | None
    started_at: str
    finished_at: str = ""
    succeeded: int = 0
    failed: int = 0
    blocked: int = 0
    skipped: int = 0
    # 无订阅权限的独立终态（auth-framework §8.5）：预期内、**不计失败率**——单列一行，
    # 与 failed/blocked/skipped 并列（AC-4.3；OA-fallback 另行呈现落盘的 OA 副本）。
    no_entitlement: int = 0
    planned_downloads: int = 0
    planned_bytes: int = 0
    # 每项形如 {"task_id": ..., "stage": ..., "error_class": ..., "msg": ...}。
    failures: list[dict[str, object]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def render_markdown(self) -> str:
        """渲染 markdown 摘要：标题 → 计数表 → [dry-run 预览] → [失败清单]
        → [下一步提示] → [Notes]。空的可选小节整体省略，不留空标题。
        """
        venue_label = self.venue_id if self.venue_id is not None else "(all venues)"
        finished_label = self.finished_at if self.finished_at else "(running)"

        lines: list[str] = [
            f"# Pipeline Report — {self.command} {venue_label}",
            "",
            f"- Venue: {venue_label}",
            f"- 时间窗: {self.started_at} → {finished_label}",
            "",
            "## 计数",
            "",
            "| 指标 | 数量 |",
            "| --- | --- |",
            f"| 成功 | {self.succeeded} |",
            f"| 失败 | {self.failed} |",
            f"| 阻塞 | {self.blocked} |",
            f"| 跳过 | {self.skipped} |",
        ]
        # no_entitlement 独立呈现（§8.5）：仅在发生时加一行，不污染既有零值报告的渲染。
        if self.no_entitlement > 0:
            lines.append(f"| 无订阅权限 | {self.no_entitlement} |")

        if self.planned_downloads > 0 or self.planned_bytes > 0:
            mb = self.planned_bytes / _BYTES_PER_MB
            lines += ["", f"将下载 {self.planned_downloads} 篇 / 估 {mb:.1f} MB"]

        if self.failures:
            lines += ["", "## 失败清单（Top 10）", ""]
            shown = self.failures[:_MAX_FAILURES_SHOWN]
            for item in shown:
                task_id = item.get("task_id", "?")
                stage = item.get("stage", "?")
                error_class = item.get("error_class", "?")
                msg = redact(str(item.get("msg", "")))
                lines.append(f"- [{stage}] {task_id}: {error_class} — {msg}")
            remaining = len(self.failures) - len(shown)
            if remaining > 0:
                lines.append(f"（及另 {remaining} 项）")

        if self.blocked > 0:
            lines += [
                "",
                f"下一步：{self.blocked} 个任务被阻塞，运行 `crawler status --blocked` "
                "查看详情，处理后执行 `crawler resume --all`（或指定单个任务 id）恢复。",
            ]

        if self.notes:
            lines += ["", "## Notes", ""]
            lines += [f"- {redact(note)}" for note in self.notes]

        lines.append("")  # 文件以换行结尾
        return "\n".join(lines)

    def save(self, reports_dir: Path) -> Path:
        """写 `reports_dir/last-run.md`（覆盖）+ 追加 `reports_dir/history.jsonl`。

        目录不存在则自动创建；返回 last-run.md 的路径。history.jsonl 每行是本
        报告转 dict 后的一条 JSON（`failures[].msg`/`notes` 已按上述纵深防御脱敏）。
        """
        reports_dir.mkdir(parents=True, exist_ok=True)

        last_run_path = reports_dir / "last-run.md"
        last_run_path.write_text(self.render_markdown(), encoding="utf-8")

        record = asdict(self)
        record["failures"] = [
            {**item, "msg": redact(str(item.get("msg", "")))} for item in record["failures"]
        ]
        record["notes"] = [redact(str(note)) for note in record["notes"]]

        history_path = reports_dir / "history.jsonl"
        with history_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

        return last_run_path


__all__ = ["RunReport"]
