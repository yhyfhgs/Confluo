"""OpenAlex 每日 credit 预算状态（design/adapters/aggregators.md §4 伪代码落地）。

state 文件形如 ``{"date": "YYYY-MM-DD", "spent_usd": <float>}``（UTC 日期 key），落在
调用方指定的路径下（约定 ``<config-home>/state/openalex-budget.json``——家目录、仓库
外，AGENTS §6.4；本模块自身不认识 "config-home" 概念，只接受调用方传入的 `Path`）。

**原子性范围（Phase 4 M2b 检查单 #10 加固后，如实标注现状）**：`save_state` 用"同目录
临时文件 + `os.replace`"保证**单次写入**原子（不会有读者看到半写文件、kill -9 不会
截断已存在的旧文件）。`add_spend` 的"读→加→写"三步序列**在 Linux/macOS 上现已用
`fcntl.flock` 排他锁包住整个序列**（锁定义在 `<state 文件>.lock` 这个独立、从不改名的
文件上，而非 state 文件本身——`save_state` 的 `os.replace` 会让 state 路径指向新
inode，若直接对 state 文件本身 `flock` 则 rename 后旧 fd 持有的锁会与新 inode 脱钩、
起不到跨进程互斥的实际效果，故必须借一个稳定路径中转）；两个并发进程的 `add_spend`
调用现在会真正互斥执行，不再有"后写者覆盖前写者增量"的 lost update。**Windows
（无 `fcntl`）降级为原状**（不加锁，`_locked` 变为无操作上下文管理器）——`fcntl` 是
POSIX-only 标准库模块，Windows 无原生等价物且不在本仓库的部署目标范围（AGENTS.md 未
声明跨平台承诺、CI/开发环境均为 macOS/Linux），加一个自定义跨平台锁抽象超出本次
加固的必要范围，如实标注而非假装覆盖。

**仍然存在、本次未处理的更粗粒度竞态（如实标注，超出本次加固范围）**：`adapter.py::
enrich_batch` 对每个内部批次是"`load_state` 判是否超预算 → 发真实网络请求 →
`add_spend` 记账"三步，后两步之间隔着一次网络往返——即使 `add_spend` 本身现已跨进程
原子，两个*并发运行的* `crawler enrich` 进程仍可能都在网络请求飞行期间读到"未超预算"
的旧状态、都发出请求、之后才各自记账，使当日花费短暂超出预算上限（幅度上限=并发
进程数 × 单批次成本，通常几美分到几十美分量级）。修复需要在 adapter 层引入"预留-确认"
两阶段协议（请求前预留額度、请求后确认或回退），是比"让 add_spend 自身原子"更大的
改动，留作后续加固项——本次加固闭合的是 §模块 docstring 明确点名的那个具体缺陷
（`add_spend` 自身的读-加-写非原子），不是这个更粗粒度的检查-即-用竞态。
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows has no fcntl; exercised via _HAS_FLOCK=False path
    fcntl = None  # type: ignore[assignment]

_HAS_FLOCK = fcntl is not None


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


def _lock_path_for(path: Path) -> Path:
    """`add_spend` 排他锁的独立锁文件路径：`<state 文件名>.lock`，与 state 文件本身
    分开（原因见模块 docstring"原子性范围"段——`save_state` 会 `os.replace` state
    路径本身，锁必须落在一个从不被 replace 的稳定路径上才能跨调用持续互斥）。
    """
    return path.with_name(path.name + ".lock")


@contextlib.contextmanager
def _locked(path: Path) -> Iterator[None]:
    """跨进程排他锁：`fcntl.flock`（POSIX）包住调用方的临界区；Windows 降级为无操作。

    锁文件本身内容无意义（只作互斥柄用，不落业务数据）；`"a"` 模式确保不存在时
    创建、存在时不截断（截断本身对纯互斥用途无所谓，但 `"a"` 更朴素地表达"我们
    不关心内容"）。`flock` 随文件句柄 `close()`（`with` 退出）自动释放，无需显式
    `LOCK_UN`——但显式释放能让"锁已释放"这件事在代码里可读，且防止未来有人在
    `finally` 之外插入会意外延长句柄生命周期的逻辑。
    """
    if not _HAS_FLOCK:
        # Windows（无 fcntl）：降级为现状——不加锁，调用方自行承担模块 docstring
        # 描述的"更粗粒度竞态"段所述风险（比加锁前的风险面更小：至少 add_spend
        # 自身的读-加-写在 POSIX 上已是原子，Windows 上维持加固前的已知限制）。
        yield
        return
    assert fcntl is not None  # narrows type for mypy under _HAS_FLOCK guard
    lock_path = _lock_path_for(path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "a", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def add_spend(path: Path, amount_usd: float) -> BudgetState:
    """读→加→写，整段在跨进程排他锁下执行（POSIX；`_locked`/模块 docstring）；
    `amount_usd` 为负/NaN 时钳到 0 计入。"""
    with _locked(path):
        state = load_state(path)
        safe_amount = amount_usd if amount_usd > 0.0 else 0.0
        updated = BudgetState(date=state.date, spent_usd=state.spent_usd + safe_amount)
        save_state(path, updated)
        return updated


__all__ = ["BudgetState", "add_spend", "load_state", "save_state"]
