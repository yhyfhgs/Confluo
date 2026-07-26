#!/usr/bin/env python3
"""在线预算共享行运行时账本（Phase 7 T4；phase6-report §4 事件⑤处置，检查单 #16）。

**动机**（phase6-report §4 事件⑤如实记录的缺口）：多个独立会话/agent 各自静态推算
共享预算行（如 phase7-implementation-plan.md §3"机动 ≤10"）的剩余额度时，缺一份
中心化运行时账本——三次独立在线活动（6+1+4）各自记"占用 X"/"余 Y"，没有一份文档
在写下"余额"时核对过另外两次已消耗的部分，合计 11 较名义上限超出 1。本工具把该
共享行的累计消耗与逐次消费记录落一份单一 JSON 文件，供"消费前读账本、消费后记账本"
两条纪律（`docs/process/online-budget.md`）落地。

**定位**（已裁决，不入 `src/paper_crawler` 包）：编排/记账流程工具，非爬虫功能——
不占门禁覆盖率（`pyproject.toml` `[tool.coverage.run] source = ["paper_crawler"]`
不含 `scripts/`）、不入 mypy 扫描面（`[tool.mypy] files = ["src"]`）；仍需过
`ruff check .`/`ruff format --check .`（两者扫全仓库，无 `scripts/` 排除项）。

**落盘位置**：`<config-home>/state/budget.json`——config-home 解析**复用**
`paper_crawler.config.resolve_home()`（D-032 红线：禁 `Path.home()` 硬编码兜底；
解析顺序=显式 `--home` > `$PAPER_CRAWLER_HOME` > `~/.paper-crawler`，与 CLI 主程序
逐字段同源）。

**JSON 账本格式**（共享预算行 → 累计消耗 + 消费记录数组）::

    {
      "机动": {
        "consumed": 11,
        "entries": [
          {"ts": "2026-07-26T08:00Z", "session": "repec-probe", "batch": "探针遗留", "count": 6},
          {"ts": "2026-07-26T09:30Z", "session": "acl-anthology", "batch": "补拉", "count": 1},
          {"ts": "2026-07-26T11:00Z", "session": "T7-nber", "batch": "坐实", "count": 4}
        ]
      },
      "T8-robots": {"consumed": 2, "entries": [...]}
    }

行名自由文本（对齐当期 `phase<N>-implementation-plan.md` §3 表的行名，如"机动"/
"T8-robots"）；账本本身**不记录预算上限**——上限随 Phase 计划表变化，账本只管
"这一行迄今被消耗了多少"这一件事，人/agent 在 `status` 输出旁核对当期计划表的
`≤N` 上限。

**并发安全**：读→加→写整段包在 `fcntl.flock`（POSIX）排他锁下（锁文件与账本文件
分离，做法与写法均照搬 `paper_crawler.adapters.openalex.budget` 的既有加固模式——
`save_ledger` 的 `os.replace` 会让账本路径指向新 inode，锁必须落在一个从不被
replace 的稳定路径上）；Windows（无 `fcntl`）降级为不加锁。

用法::

    # 消费前：核对账本（默认列全部行；--row 只看一行明细）
    uv run python scripts/budget_ledger.py status
    uv run python scripts/budget_ledger.py status --row 机动

    # 消费后：记一笔（--session 建议填会话/任务标识，便于事后追溯"谁在何时用了多少"）
    uv run python scripts/budget_ledger.py record --row 机动 --session T19-nber \\
        --batch "nber 坐实" --count 4

    # 显式覆盖 config-home（测试/隔离场景；生产用途省略，走默认解析链）
    uv run python scripts/budget_ledger.py --home /tmp/scratch-home status
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
import tempfile
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from paper_crawler.config import resolve_home

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows has no fcntl; exercised via _HAS_FLOCK=False path
    fcntl = None  # type: ignore[assignment]

_HAS_FLOCK = fcntl is not None


@dataclass(frozen=True)
class LedgerEntry:
    """一条消费记录：时间戳 + 会话戳 + 批次 + 数量。"""

    ts: str
    session: str
    batch: str
    count: int

    def to_json(self) -> dict[str, object]:
        return {"ts": self.ts, "session": self.session, "batch": self.batch, "count": self.count}


@dataclass(frozen=True)
class LedgerRow:
    """一条共享预算行：累计消耗 + 消费记录数组（时间顺序，追加写）。"""

    consumed: int
    entries: tuple[LedgerEntry, ...] = ()

    def to_json(self) -> dict[str, object]:
        return {"consumed": self.consumed, "entries": [e.to_json() for e in self.entries]}


Ledger = dict[str, LedgerRow]

_EMPTY_ROW = LedgerRow(consumed=0, entries=())


def _parse_entry(value: object) -> LedgerEntry | None:
    if not isinstance(value, dict):
        return None
    ts, session, batch, count = (
        value.get("ts"),
        value.get("session"),
        value.get("batch"),
        value.get("count"),
    )
    if not isinstance(ts, str) or not isinstance(session, str) or not isinstance(batch, str):
        return None
    if isinstance(count, bool) or not isinstance(count, int):
        return None
    return LedgerEntry(ts=ts, session=session, batch=batch, count=count)


def _parse_row(value: object) -> LedgerRow | None:
    if not isinstance(value, dict):
        return None
    consumed = value.get("consumed")
    if isinstance(consumed, bool) or not isinstance(consumed, int):
        return None
    raw_entries = value.get("entries")
    if not isinstance(raw_entries, list):
        return None
    entries = [parsed for item in raw_entries if (parsed := _parse_entry(item)) is not None]
    return LedgerRow(consumed=consumed, entries=tuple(entries))


def load_ledger(path: Path) -> Ledger:
    """读取账本；不存在/畸形整体 → 空账本。单行畸形只丢该行，不连累其余行。"""
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    if not isinstance(raw, dict):
        return {}
    ledger: Ledger = {}
    for name, value in raw.items():
        row = _parse_row(value)
        if row is not None:
            ledger[str(name)] = row
    return ledger


def save_ledger(path: Path, ledger: Ledger) -> None:
    """原子写：同目录临时文件 + `os.replace`（照搬 openalex/budget.py 的既有模式）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        {name: row.to_json() for name, row in ledger.items()}, ensure_ascii=False, indent=2
    )
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=".budget-ledger-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
        os.replace(tmp_name, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp_name)
        raise


def _lock_path_for(path: Path) -> Path:
    """独立锁文件路径（`<账本文件名>.lock`）——与账本文件本身分离，理由见模块 docstring
    "并发安全"段（`save_ledger` 的 `os.replace` 会让账本路径指向新 inode）。
    """
    return path.with_name(path.name + ".lock")


@contextlib.contextmanager
def _locked(path: Path) -> Iterator[None]:
    """跨进程排他锁：`fcntl.flock`（POSIX）；Windows（无 `fcntl`）降级为无操作。"""
    if not _HAS_FLOCK:
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


def record_entry(
    path: Path,
    row: str,
    session: str,
    batch: str,
    count: int,
    *,
    now: Callable[[], datetime] | None = None,
) -> LedgerRow:
    """记一笔消费：读→加→写整段在跨进程排他锁下执行，返回该行更新后的状态。"""
    clock = now or (lambda: datetime.now(UTC))
    with _locked(path):
        ledger = load_ledger(path)
        existing = ledger.get(row, _EMPTY_ROW)
        entry = LedgerEntry(ts=clock().isoformat(), session=session, batch=batch, count=count)
        updated = LedgerRow(consumed=existing.consumed + count, entries=(*existing.entries, entry))
        ledger[row] = updated
        save_ledger(path, ledger)
        return updated


def render_summary(ledger: Ledger) -> str:
    """全部行的一览表（行名/累计消耗/记录条数/最近一次时间戳）。"""
    lines = ["row\tconsumed\tentries\tlast_ts"]
    for name in sorted(ledger):
        row = ledger[name]
        last_ts = row.entries[-1].ts if row.entries else "-"
        lines.append(f"{name}\t{row.consumed}\t{len(row.entries)}\t{last_ts}")
    return "\n".join(lines)


def render_detail(name: str, row: LedgerRow) -> str:
    """单行明细：累计消耗 + 逐条消费记录。"""
    lines = [f"row: {name}", f"consumed: {row.consumed}"]
    if not row.entries:
        lines.append("entries: (none)")
        return "\n".join(lines)
    lines.append("entries:")
    for e in row.entries:
        lines.append(f"  {e.ts}  session={e.session}  batch={e.batch}  count={e.count}")
    return "\n".join(lines)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="budget_ledger.py",
        description="在线预算共享行运行时账本（消费前 status、消费后 record；见 "
        "docs/process/online-budget.md）。",
    )
    parser.add_argument(
        "--home",
        type=Path,
        default=None,
        help="显式 config-home（默认解析链：$PAPER_CRAWLER_HOME > ~/.paper-crawler；"
        "测试/隔离场景显式传入，绝不落到仓库根真实 .paper-crawler/）",
    )
    sub = parser.add_subparsers(dest="action", required=True)

    record = sub.add_parser("record", help="消费后记一笔")
    record.add_argument("--row", required=True, help="共享预算行名（如“机动”/T8-robots）")
    record.add_argument("--session", required=True, help="会话戳（建议填任务/会话标识）")
    record.add_argument("--batch", required=True, help="本次消费的批次描述")
    record.add_argument("--count", required=True, type=int, help="本次消费的请求数（>=1）")

    status = sub.add_parser("status", help="消费前核对账本")
    status.add_argument("--row", default=None, help="只看这一行明细；省略则列全部行一览")

    return parser


def main(argv: list[str]) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv[1:])
    home = resolve_home(args.home)
    path = home / "state" / "budget.json"

    if args.action == "record":
        if args.count < 1:
            print(f"error: --count must be >= 1 (got {args.count})", file=sys.stderr)
            return 1
        if not args.row.strip() or not args.session.strip() or not args.batch.strip():
            print("error: --row/--session/--batch must be non-empty", file=sys.stderr)
            return 1
        row = record_entry(path, args.row, args.session, args.batch, args.count)
        print(f"ledger: {path}")
        print(
            f"recorded: row={args.row!r} count={args.count} session={args.session!r} "
            f"batch={args.batch!r} -> consumed={row.consumed} ({len(row.entries)} entries)"
        )
        return 0

    if args.action == "status":
        ledger = load_ledger(path)
        print(f"ledger: {path}")
        if args.row:
            print(render_detail(args.row, ledger.get(args.row, _EMPTY_ROW)))
        else:
            print(render_summary(ledger) if ledger else "(empty ledger)")
        return 0

    return 1  # pragma: no cover - argparse required=True on subparsers 使此分支不可达


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
