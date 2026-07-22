"""OpenAlex 每日 credit 预算状态（design/adapters/aggregators.md §4 伪代码落地）。

state 文件形如 ``{"date": "YYYY-MM-DD", "spent_usd": <float>}``（UTC 日期 key），落在
调用方指定的路径下（约定 ``<config-home>/state/openalex-budget.json``——家目录、仓库
外，AGENTS §6.4；本模块自身不认识 "config-home" 概念，只接受调用方传入的 `Path`）。

**原子性范围（如实标注，aggregators.md §4 "[PENDING·T6 确认]" 的落地取舍）**：`save_state`
用"同目录临时文件 + `os.replace`"保证**单次写入**原子（不会有读者看到半写文件、
kill -9 不会截断已存在的旧文件），但 `add_spend` 的"读→加→写"三步序列**不**跨进程加锁
——两个并发进程各自读到同一旧值、各自加、各自写，后写者会覆盖前写者的增量（lost
update）。design 文档已明确本 Phase 的最小实现基线是"run-scoped 累计 + 落 config-home
JSON"，`crawler enrich` 是单进程顺序驱动（同一命令内部不并发调用 `enrich_batch`），
故这一读–改–写窗口内只有极小概率与另一次*手动并发运行的* `crawler enrich` 撞车；
真出现也只是预算核销偏保守/偏宽松几美分，不影响正确性红线（不会因此绕过强制停机——
下一次 `load_state` 仍会读到两次写入中较新落盘的那个值，不会无限增长）。跨进程强一致
如需要，可在此加 `fcntl.flock`，留作后续加固项（见任务报告 concerns）。
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


def _today_utc() -> str:
    return datetime.now(UTC).date().isoformat()


@dataclass(frozen=True)
class BudgetState:
    """当日预算状态：UTC 日期 key + 累计花费（美元）。"""

    date: str
    spent_usd: float


def load_state(path: Path) -> BudgetState:
    """读取 `path` 处的状态；不存在/畸形/日期非今日（UTC）→ 视为今日新起点 `spent_usd=0`。

    "日期非今日 → 重置"即 §4 伪代码的"date 滚动即重置 spent_usd=0"——本函数把"滚动"
    表达为惰性读时判定，不需要额外的后台任务或写时机检测。
    """
    today = _today_utc()
    if not path.is_file():
        return BudgetState(date=today, spent_usd=0.0)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return BudgetState(date=today, spent_usd=0.0)
    if not isinstance(raw, dict) or raw.get("date") != today:
        return BudgetState(date=today, spent_usd=0.0)
    spent = raw.get("spent_usd")
    if isinstance(spent, bool) or not isinstance(spent, int | float):
        return BudgetState(date=today, spent_usd=0.0)
    return BudgetState(date=today, spent_usd=float(spent))


def save_state(path: Path, state: BudgetState) -> None:
    """原子写：同目录临时文件 + `os.replace`（模块 docstring 的原子性范围说明）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({"date": state.date, "spent_usd": state.spent_usd})
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=".openalex-budget-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
        os.replace(tmp_name, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp_name)
        raise


def add_spend(path: Path, amount_usd: float) -> BudgetState:
    """读→加→写（单进程原子性范围见模块 docstring）；`amount_usd` 为负/NaN 时钳到 0 计入。"""
    state = load_state(path)
    safe_amount = amount_usd if amount_usd > 0.0 else 0.0
    updated = BudgetState(date=state.date, spent_usd=state.spent_usd + safe_amount)
    save_state(path, updated)
    return updated


__all__ = ["BudgetState", "add_spend", "load_state", "save_state"]
