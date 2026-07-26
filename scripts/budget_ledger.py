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


class LedgerCorruptError(RuntimeError):
    """账本文件存在但内容无法安全、完整解析（独立审查 P0-1/P0-2 坐实）。

    **绝不**在此情形下静默退回空账本——`record_entry` 的读→加→写会紧接着对
    `load_ledger` 的返回值做无条件整体覆写；若把"解析失败"悄悄当成"空账本"，
    那次覆写就会把文件里原本存在、只是暂时解析不出来的数据**永久抹除**。调用方
    （库层直调者或 `main()`）应人工检查/修复该文件的内容，或显式移走/重命名，
    让工具从一份新的空账本重新开始——都不该由本工具自作主张替你决定。
    """


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


def _parse_entry(value: object) -> LedgerEntry:
    """把一条已解析的 JSON 值转成 `LedgerEntry`；任何畸形（含 `count` 非 bool 的
    正整数——独立审查 P0-2）**响亮抛 `LedgerCorruptError`**，不再静默丢弃该条目
    （旧行为：返回 `None` 由调用方过滤——那正是 P0-2 坐实的丢数据路径：`count`
    传 float 落盘后，下次解析判畸形丢弃，再一次 `record_entry` 就把它永久覆写掉）。
    """
    if not isinstance(value, dict):
        raise LedgerCorruptError(f"entry is not a JSON object: {value!r}")
    ts, session, batch, count = (
        value.get("ts"),
        value.get("session"),
        value.get("batch"),
        value.get("count"),
    )
    if not isinstance(ts, str) or not isinstance(session, str) or not isinstance(batch, str):
        raise LedgerCorruptError(f"entry has non-string ts/session/batch: {value!r}")
    if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
        raise LedgerCorruptError(
            f"entry.count must be a positive int (non-bool); got {count!r} in {value!r}"
        )
    return LedgerEntry(ts=ts, session=session, batch=batch, count=count)


def _parse_row(value: object) -> LedgerRow:
    """把一条已解析的 JSON 值转成 `LedgerRow`；任何畸形**响亮抛 `LedgerCorruptError`**
    （不再静默丢弃整行——理由同 `_parse_entry`）。"""
    if not isinstance(value, dict):
        raise LedgerCorruptError(f"row is not a JSON object: {value!r}")
    consumed = value.get("consumed")
    if isinstance(consumed, bool) or not isinstance(consumed, int):
        raise LedgerCorruptError(f"row.consumed must be an int (non-bool); got {consumed!r}")
    raw_entries = value.get("entries")
    if not isinstance(raw_entries, list):
        raise LedgerCorruptError(f"row.entries must be a list; got {raw_entries!r}")
    entries = tuple(_parse_entry(item) for item in raw_entries)
    return LedgerRow(consumed=consumed, entries=entries)


def load_ledger(path: Path) -> Ledger:
    """读取账本。文件**不存在** → 空账本（合法的"首次运行"起点）。文件**存在但
    无法安全、完整解析**（JSON 语法错误/读取失败/顶层非对象/任意一行或一条记录
    畸形）→ **fail-loud：抛 `LedgerCorruptError`，绝不静默退回空账本**——静默会让
    `record_entry` 紧接着对着这份"看起来空"的账本做无条件整体覆写，把解析失败的
    那部分数据永久抹除（独立审查 P0-1 实测坐实：预置两行→截断 JSON→`record` 后
    两行全部消失）。`status` 读路径同样直接传播本异常，不得静默报 `consumed: 0`。
    """
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as exc:
        raise LedgerCorruptError(f"{path}: cannot read ledger file ({exc})") from exc
    except json.JSONDecodeError as exc:
        raise LedgerCorruptError(f"{path}: invalid JSON ({exc})") from exc
    if not isinstance(raw, dict):
        raise LedgerCorruptError(
            f"{path}: top-level JSON must be an object; got {type(raw).__name__}"
        )
    ledger: Ledger = {}
    for name, value in raw.items():
        try:
            ledger[str(name)] = _parse_row(value)
        except LedgerCorruptError as exc:
            raise LedgerCorruptError(f"{path}: row {name!r} is malformed ({exc})") from exc
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
    """记一笔消费：读→加→写整段在跨进程排他锁下执行，返回该行更新后的状态。

    `count` 必须是非 bool 的正整数——**库层运行时守卫**（独立审查 P0-2/P1）：CLI
    的 `main()` 已有一层 `--count` 校验，但那只挡得住经 argparse 的调用；绕过 CLI
    直调本函数（如脚本内部调用、未来的库消费方）仍可能传 `2.7`/`0`/`-50` 等坏值——
    一旦放行落盘，`existing.consumed + count` 会污染该行的 `consumed`（变 float 或
    负数），下次 `load_ledger`→`_parse_row` 判其畸形并 `raise`，此前"静默丢弃"的
    旧版本更会在下一次 `record_entry` 时被无条件整体覆写永久抹除——在此处直接拒绝，
    防止坏数据第一步就写入文件，与 CLI 层校验构成两层防御。
    """
    if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
        raise ValueError(f"count must be a positive int (non-bool); got {count!r}")
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
        try:
            row = record_entry(path, args.row, args.session, args.batch, args.count)
        except (ValueError, LedgerCorruptError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(f"ledger: {path}")
        print(
            f"recorded: row={args.row!r} count={args.count} session={args.session!r} "
            f"batch={args.batch!r} -> consumed={row.consumed} ({len(row.entries)} entries)"
        )
        return 0

    if args.action == "status":
        try:
            ledger = load_ledger(path)
        except LedgerCorruptError as exc:
            # fail-loud（P0-1）：只读路径也不得静默把损坏文件当空账本报 consumed: 0。
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(f"ledger: {path}")
        if args.row:
            print(render_detail(args.row, ledger.get(args.row, _EMPTY_ROW)))
        else:
            print(render_summary(ledger) if ledger else "(empty ledger)")
        return 0

    return 1  # pragma: no cover - argparse required=True on subparsers 使此分支不可达


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
