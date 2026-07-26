"""`scripts/budget_ledger.py` 单测（Phase 7 T4；检查单 #16；phase6-report §4 事件⑤回归锁）。

`scripts/` 非 Python 包（无 `__init__.py`）——经 `importlib.util` 按文件路径动态加载
模块，不用 `sys.path` 注入（避免污染其余测试的导入解析）。全部测试固定走 `tmp_path`
（T4 卡纪律：工具测试一律 tmp_path，绝不触碰仓库根真实 `.paper-crawler/`）；CLI 分支
的用例一律显式传 `--home`，即便设了 `PAPER_CRAWLER_HOME` 也不应落到该路径
（`test_cli_explicit_home_overrides_env_var` 回归锁）。
"""

from __future__ import annotations

import importlib.util
import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType

import pytest

_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "budget_ledger.py"


def _load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("budget_ledger", _SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # dataclasses（`from __future__ import annotations` 令注解全为字符串）在类定义期
    # 需要通过 `sys.modules[cls.__module__]` 反查所属模块解析类型——先注册进
    # `sys.modules` 再 `exec_module`，否则 `@dataclass` 处理 `LedgerEntry`/`LedgerRow`
    # 时会因 `sys.modules.get("budget_ledger")` 返回 None 而 AttributeError。
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def bl() -> ModuleType:
    return _load_module()


@pytest.fixture
def ledger_path(tmp_path: Path) -> Path:
    return tmp_path / "state" / "budget.json"


# -- load_ledger -----------------------------------------------------------------


def test_load_ledger_missing_file_returns_empty(bl: ModuleType, ledger_path: Path) -> None:
    assert bl.load_ledger(ledger_path) == {}


## 独立审查 P0-1 回归锁：文件存在但不可解析——曾经"静默返回 {}"，会让 `record_entry`
## 紧接着对空账本做无条件整体覆写、永久抹除其余行历史（实测：预置两行→截断→record 后
## 全部消失）。修复为 fail-loud：一律 `raise LedgerCorruptError`，不再返回 `{}`。


def test_load_ledger_corrupt_json_raises_loud(bl: ModuleType, ledger_path: Path) -> None:
    ledger_path.parent.mkdir(parents=True)
    ledger_path.write_text("{not valid json", encoding="utf-8")
    with pytest.raises(bl.LedgerCorruptError, match="invalid JSON"):
        bl.load_ledger(ledger_path)


def test_load_ledger_non_dict_top_level_raises_loud(bl: ModuleType, ledger_path: Path) -> None:
    ledger_path.parent.mkdir(parents=True)
    ledger_path.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    with pytest.raises(bl.LedgerCorruptError, match="top-level JSON must be an object"):
        bl.load_ledger(ledger_path)


def test_load_ledger_unreadable_file_raises_loud(
    bl: ModuleType, ledger_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`OSError`（权限/损坏等）路径同样 fail-loud，不静默当空账本。"""
    ledger_path.parent.mkdir(parents=True)
    ledger_path.write_text("{}", encoding="utf-8")

    def _boom(*_args: object, **_kwargs: object) -> str:
        raise OSError("simulated read failure")

    monkeypatch.setattr(Path, "read_text", _boom)
    with pytest.raises(bl.LedgerCorruptError, match="cannot read ledger file"):
        bl.load_ledger(ledger_path)


def test_load_ledger_row_that_is_not_a_dict_raises_loud(bl: ModuleType, ledger_path: Path) -> None:
    """曾经：整行静默丢弃、其余行保留；现在：任何一行畸形都 fail-loud，绝不悄悄
    丢弃部分数据后放行调用方继续做无条件整体覆写。"""
    ledger_path.parent.mkdir(parents=True)
    ledger_path.write_text(
        json.dumps({"机动": {"consumed": 3, "entries": []}, "broken-shape": "not-a-dict"}),
        encoding="utf-8",
    )
    with pytest.raises(bl.LedgerCorruptError, match="broken-shape"):
        bl.load_ledger(ledger_path)


def test_load_ledger_row_with_bad_consumed_type_raises_loud(
    bl: ModuleType, ledger_path: Path
) -> None:
    """独立审查 P0-2 的确切复现路径：`consumed` 一旦不是 int（如被 float count 污染）
    ——曾经整行静默丢弃，现在 fail-loud 并点名该行。"""
    ledger_path.parent.mkdir(parents=True)
    ledger_path.write_text(
        json.dumps({"broken-consumed": {"consumed": 2.7, "entries": []}}), encoding="utf-8"
    )
    with pytest.raises(bl.LedgerCorruptError, match="broken-consumed"):
        bl.load_ledger(ledger_path)


def test_load_ledger_entries_not_a_list_raises_loud(bl: ModuleType, ledger_path: Path) -> None:
    ledger_path.parent.mkdir(parents=True)
    ledger_path.write_text(
        json.dumps({"机动": {"consumed": 3, "entries": "not-a-list"}}), encoding="utf-8"
    )
    with pytest.raises(bl.LedgerCorruptError, match="机动"):
        bl.load_ledger(ledger_path)


def test_load_ledger_entry_with_bad_count_type_raises_loud(
    bl: ModuleType, ledger_path: Path
) -> None:
    """曾经：畸形 entry 静默丢弃、同行其余合法 entry 保留；现在：一条畸形足以让
    整个账本读取 fail-loud（不再悄悄丢弃部分历史）。"""
    ledger_path.parent.mkdir(parents=True)
    ledger_path.write_text(
        json.dumps(
            {
                "机动": {
                    "consumed": 5,
                    "entries": [
                        {"ts": "t1", "session": "s1", "batch": "b1", "count": 5},
                        {"ts": "t2", "session": "s2", "batch": "b2", "count": "nope"},
                    ],
                }
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(bl.LedgerCorruptError, match="count must be a positive int"):
        bl.load_ledger(ledger_path)


def test_load_ledger_entry_that_is_not_a_dict_raises_loud(
    bl: ModuleType, ledger_path: Path
) -> None:
    ledger_path.parent.mkdir(parents=True)
    ledger_path.write_text(
        json.dumps({"机动": {"consumed": 5, "entries": ["not-a-dict-entry"]}}), encoding="utf-8"
    )
    with pytest.raises(bl.LedgerCorruptError):
        bl.load_ledger(ledger_path)


# -- _parse_entry/_parse_row 单元级守卫（与上面经 load_ledger 的集成路径互补）--------


def test_parse_entry_rejects_zero_count(bl: ModuleType) -> None:
    with pytest.raises(bl.LedgerCorruptError, match="positive int"):
        bl._parse_entry({"ts": "t", "session": "s", "batch": "b", "count": 0})


def test_parse_entry_rejects_negative_count(bl: ModuleType) -> None:
    with pytest.raises(bl.LedgerCorruptError, match="positive int"):
        bl._parse_entry({"ts": "t", "session": "s", "batch": "b", "count": -50})


def test_parse_entry_rejects_bool_count(bl: ModuleType) -> None:
    """`bool` 是 `int` 子类——必须显式排除，`True`/`False` 不是合法 count。"""
    with pytest.raises(bl.LedgerCorruptError, match="positive int"):
        bl._parse_entry({"ts": "t", "session": "s", "batch": "b", "count": True})


# -- save_ledger / round trip -----------------------------------------------------


def test_save_then_load_round_trips(bl: ModuleType, ledger_path: Path) -> None:
    entry = bl.LedgerEntry(ts="2026-07-27T00:00:00+00:00", session="s", batch="b", count=2)
    row = bl.LedgerRow(consumed=2, entries=(entry,))
    bl.save_ledger(ledger_path, {"机动": row})

    reloaded = bl.load_ledger(ledger_path)
    assert reloaded["机动"].consumed == 2
    assert reloaded["机动"].entries[0].batch == "b"


def test_save_ledger_creates_parent_directories(bl: ModuleType, tmp_path: Path) -> None:
    path = tmp_path / "a" / "b" / "budget.json"
    bl.save_ledger(path, {})
    assert path.is_file()


def test_save_ledger_does_not_leave_temp_files_behind(bl: ModuleType, ledger_path: Path) -> None:
    bl.save_ledger(ledger_path, {})
    leftovers = list(ledger_path.parent.glob(".budget-ledger-*.tmp"))
    assert leftovers == []


def test_save_ledger_cleans_up_temp_file_and_reraises_on_replace_failure(
    bl: ModuleType, ledger_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _boom(_src: str, _dst: str) -> None:
        raise OSError("simulated replace failure")

    monkeypatch.setattr(bl.os, "replace", _boom)

    with pytest.raises(OSError, match="simulated replace failure"):
        bl.save_ledger(ledger_path, {})

    assert not ledger_path.exists()
    assert list(ledger_path.parent.glob(".budget-ledger-*.tmp")) == []


def test_persisted_file_stores_utf8_row_names_literally(bl: ModuleType, ledger_path: Path) -> None:
    bl.record_entry(ledger_path, "机动", "s", "b", 1)
    raw = ledger_path.read_text(encoding="utf-8")
    assert "机动" in raw
    assert "\\u" not in raw  # ensure_ascii=False：不应出现转义 unicode 逃逸序列


# -- record_entry ------------------------------------------------------------------


def test_record_entry_creates_row_and_persists(bl: ModuleType, ledger_path: Path) -> None:
    fixed_now = datetime(2026, 7, 27, 9, 0, 0, tzinfo=UTC)
    row = bl.record_entry(ledger_path, "机动", "session-a", "batch-a", 6, now=lambda: fixed_now)
    assert row.consumed == 6
    assert len(row.entries) == 1
    assert row.entries[0].ts == "2026-07-27T09:00:00+00:00"

    reloaded = bl.load_ledger(ledger_path)
    assert reloaded["机动"].consumed == 6


def test_record_entry_accumulates_across_calls(bl: ModuleType, ledger_path: Path) -> None:
    """回归锁：phase6-report §4 事件⑤的 6+1+4=11 三次独立记账场景。"""
    bl.record_entry(ledger_path, "机动", "repec-probe", "探针遗留", 6)
    bl.record_entry(ledger_path, "机动", "acl-anthology", "补拉", 1)
    row = bl.record_entry(ledger_path, "机动", "T7-nber", "坐实", 4)
    assert row.consumed == 11
    assert [e.count for e in row.entries] == [6, 1, 4]


def test_record_entry_keeps_other_rows_untouched(bl: ModuleType, ledger_path: Path) -> None:
    bl.record_entry(ledger_path, "机动", "s1", "b1", 6)
    bl.record_entry(ledger_path, "T8-robots", "s2", "b2", 2)
    ledger = bl.load_ledger(ledger_path)
    assert ledger["机动"].consumed == 6
    assert ledger["T8-robots"].consumed == 2


# -- 独立审查 P0-2/P1 回归锁：库层直调（绕过 CLI）传坏 count -------------------------
#
# CLI 的 `--count` 经 argparse `type=int` 天然挡不出 float；下面几例模拟"绕过 CLI
# 直调 record_entry"的调用方（测试/未来脚本），坐实修复前会静默落盘、事后永久抹除
# 该行历史的三种坏值：float（P0-2 确切复现）、0、负数（P1 复现值 -50）、bool。


def test_record_entry_rejects_float_count(bl: ModuleType, ledger_path: Path) -> None:
    """独立审查 P0-2 确切复现：`count=2.7` 直调必须在落盘前被拒绝——不再放行写入
    后让 `existing.consumed + count` 把该行 `consumed` 污染成 float。"""
    with pytest.raises(ValueError, match="positive int"):
        bl.record_entry(ledger_path, "机动", "s", "b", 2.7)  # type: ignore[arg-type]
    assert not ledger_path.exists()  # 校验先于任何文件 IO，零副作用


def test_record_entry_rejects_zero_count(bl: ModuleType, ledger_path: Path) -> None:
    with pytest.raises(ValueError, match="positive int"):
        bl.record_entry(ledger_path, "机动", "s", "b", 0)
    assert not ledger_path.exists()


def test_record_entry_rejects_negative_count(bl: ModuleType, ledger_path: Path) -> None:
    """独立审查 P1 确切复现值：`count=-50` 直调必须拒绝（CLI 层的 `< 1` 校验挡不住
    绕过 CLI 的直调）。"""
    with pytest.raises(ValueError, match="positive int"):
        bl.record_entry(ledger_path, "机动", "s", "b", -50)
    assert not ledger_path.exists()


def test_record_entry_rejects_bool_count(bl: ModuleType, ledger_path: Path) -> None:
    with pytest.raises(ValueError, match="positive int"):
        bl.record_entry(ledger_path, "机动", "s", "b", True)  # type: ignore[arg-type]
    assert not ledger_path.exists()


def test_record_entry_does_not_overwrite_history_when_ledger_file_is_corrupt(
    bl: ModuleType, ledger_path: Path
) -> None:
    """独立审查 P0-1 确切复现场景的镜像验证：预置两行 → 外部截断 JSON（模拟磁盘
    损坏/误手动编辑）→ 再次 `record_entry`。修复前：静默当空账本、覆写后两行全部
    消失。修复后：`record_entry` 必须在**任何写入之前** `raise`，账本文件在磁盘上
    原样保留（连一个字节都不应该变——证明"无条件整体覆写"这一步没有发生）。
    """
    bl.record_entry(ledger_path, "机动", "s1", "b1", 6)
    bl.record_entry(ledger_path, "T8-robots", "s2", "b2", 2)
    ledger_path.write_text("{not valid json at all after truncation", encoding="utf-8")
    before = ledger_path.read_bytes()

    with pytest.raises(bl.LedgerCorruptError):
        bl.record_entry(ledger_path, "机动", "s3", "b3", 4)

    after = ledger_path.read_bytes()
    assert after == before, "record_entry 不得在 load 失败后仍以覆写方式落盘"


# -- 跨进程加固：fcntl.flock（照搬 openalex/budget.py 的既有验证手法）--------------------


def test_locked_second_handle_blocks_until_first_releases(
    bl: ModuleType, ledger_path: Path
) -> None:
    first_in_critical_section = threading.Event()
    release_first = threading.Event()
    order: list[str] = []

    def _hold_first() -> None:
        with bl._locked(ledger_path):
            first_in_critical_section.set()
            release_first.wait(timeout=5.0)
            order.append("first-released")

    first_thread = threading.Thread(target=_hold_first)
    first_thread.start()
    assert first_in_critical_section.wait(timeout=5.0), "first handle never acquired the lock"

    def _try_second() -> None:
        with bl._locked(ledger_path):
            order.append("second-acquired")

    second_thread = threading.Thread(target=_try_second)
    second_thread.start()
    time.sleep(0.3)
    assert order == [], "second handle acquired the lock while the first still held it"

    release_first.set()
    first_thread.join(timeout=5.0)
    second_thread.join(timeout=5.0)
    assert order == ["first-released", "second-acquired"]


def test_concurrent_record_entry_no_lost_updates_under_thread_contention(
    bl: ModuleType, ledger_path: Path
) -> None:
    """8 线程 × 25 次 `record_entry(count=1)`：终态精确等于 200，逐记录条数亦为 200——
    这正是 T4 卡要修复的问题本身（多会话并发消费同一共享行）的直接回归锁。
    """
    workers = 8
    calls_per_worker = 25

    def _record_many(worker_id: int) -> None:
        for i in range(calls_per_worker):
            bl.record_entry(ledger_path, "机动", f"worker-{worker_id}", f"batch-{i}", 1)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_record_many, w) for w in range(workers)]
        for future in futures:
            future.result(timeout=30.0)

    final = bl.load_ledger(ledger_path)["机动"]
    assert final.consumed == workers * calls_per_worker
    assert len(final.entries) == workers * calls_per_worker


def test_locked_is_noop_when_flock_unavailable(
    bl: ModuleType, ledger_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(bl, "_HAS_FLOCK", False)
    with bl._locked(ledger_path):
        pass
    assert not bl._lock_path_for(ledger_path).exists()


def test_lock_path_for_is_ledger_path_with_lock_suffix(bl: ModuleType, tmp_path: Path) -> None:
    path = tmp_path / "budget.json"
    assert bl._lock_path_for(path) == tmp_path / "budget.json.lock"


# -- CLI: main() ---------------------------------------------------------------------


def test_cli_record_then_status_round_trip(
    bl: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    home = tmp_path / "home"
    argv = [
        "budget_ledger.py",
        "--home",
        str(home),
        "record",
        "--row",
        "机动",
        "--session",
        "T19a",
        "--batch",
        "repec-probe",
        "--count",
        "6",
    ]
    assert bl.main(argv) == 0
    out = capsys.readouterr().out
    assert "consumed=6" in out
    assert str(home) in out

    status_argv = ["budget_ledger.py", "--home", str(home), "status", "--row", "机动"]
    assert bl.main(status_argv) == 0
    out2 = capsys.readouterr().out
    assert "consumed: 6" in out2
    assert "repec-probe" in out2


def test_cli_status_with_no_row_filter_lists_all_rows(
    bl: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    home = tmp_path / "home"
    bl.main(
        [
            "budget_ledger.py",
            "--home",
            str(home),
            "record",
            "--row",
            "机动",
            "--session",
            "s",
            "--batch",
            "b",
            "--count",
            "1",
        ]
    )
    capsys.readouterr()  # 丢弃 record 的输出
    bl.main(
        [
            "budget_ledger.py",
            "--home",
            str(home),
            "record",
            "--row",
            "T8-robots",
            "--session",
            "s",
            "--batch",
            "b",
            "--count",
            "2",
        ]
    )
    capsys.readouterr()

    assert bl.main(["budget_ledger.py", "--home", str(home), "status"]) == 0
    out = capsys.readouterr().out
    assert "机动" in out
    assert "T8-robots" in out


def test_cli_status_empty_ledger_says_so(
    bl: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    home = tmp_path / "home"
    assert bl.main(["budget_ledger.py", "--home", str(home), "status"]) == 0
    out = capsys.readouterr().out
    assert "(empty ledger)" in out


def test_cli_status_unknown_row_reads_as_zero(
    bl: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    home = tmp_path / "home"
    argv = ["budget_ledger.py", "--home", str(home), "status", "--row", "never-touched"]
    assert bl.main(argv) == 0
    out = capsys.readouterr().out
    assert "consumed: 0" in out
    assert "(none)" in out


def test_cli_record_rejects_non_positive_count(
    bl: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    home = tmp_path / "home"
    argv = [
        "budget_ledger.py",
        "--home",
        str(home),
        "record",
        "--row",
        "机动",
        "--session",
        "s",
        "--batch",
        "b",
        "--count",
        "0",
    ]
    assert bl.main(argv) == 1
    err = capsys.readouterr().err
    assert "count" in err
    assert not (home / "state" / "budget.json").exists()


def test_cli_record_rejects_negative_count(
    bl: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """独立审查 P1 复现值 -50，经 CLI 而非直调（argparse 正确地把 `-50` 当作
    `--count` 的值，而非误判成另一个选项）。"""
    home = tmp_path / "home"
    argv = [
        "budget_ledger.py",
        "--home",
        str(home),
        "record",
        "--row",
        "机动",
        "--session",
        "s",
        "--batch",
        "b",
        "--count",
        "-50",
    ]
    assert bl.main(argv) == 1
    err = capsys.readouterr().err
    assert "count" in err
    assert not (home / "state" / "budget.json").exists()


def test_cli_record_on_corrupt_ledger_fails_loud_and_leaves_file_untouched(
    bl: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """P0-1 的 CLI 端到端回归锁：`record` 遇到不可解析的既有账本必须非零退出 +
    stderr 指引，绝不静默覆写抹除。"""
    home = tmp_path / "home"
    ledger_file = home / "state" / "budget.json"
    ledger_file.parent.mkdir(parents=True)
    ledger_file.write_text("{not valid json", encoding="utf-8")
    before = ledger_file.read_bytes()

    argv = [
        "budget_ledger.py",
        "--home",
        str(home),
        "record",
        "--row",
        "机动",
        "--session",
        "s",
        "--batch",
        "b",
        "--count",
        "1",
    ]
    assert bl.main(argv) == 1
    err = capsys.readouterr().err
    assert "invalid JSON" in err
    assert ledger_file.read_bytes() == before


def test_cli_status_on_corrupt_ledger_fails_loud_not_zero(
    bl: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """P0-1 的只读路径回归锁：`status` 不得把损坏文件静默报成 `consumed: 0`。"""
    home = tmp_path / "home"
    ledger_file = home / "state" / "budget.json"
    ledger_file.parent.mkdir(parents=True)
    ledger_file.write_text("{not valid json", encoding="utf-8")

    argv = ["budget_ledger.py", "--home", str(home), "status", "--row", "机动"]
    assert bl.main(argv) == 1
    out, err = capsys.readouterr()
    assert "consumed: 0" not in out
    assert "invalid JSON" in err


def test_cli_record_rejects_blank_row(
    bl: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    home = tmp_path / "home"
    argv = [
        "budget_ledger.py",
        "--home",
        str(home),
        "record",
        "--row",
        "   ",
        "--session",
        "s",
        "--batch",
        "b",
        "--count",
        "1",
    ]
    assert bl.main(argv) == 1
    assert "must be non-empty" in capsys.readouterr().err


def test_cli_explicit_home_overrides_env_var(
    bl: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """显式 `--home` 优先于 `$PAPER_CRAWLER_HOME`——防止测试/隔离调用意外写穿到
    环境变量指向的真实 config-home（D-032 红线）。"""
    monkeypatch.setenv("PAPER_CRAWLER_HOME", str(tmp_path / "should-not-be-used"))
    home = tmp_path / "isolated-home"
    argv = [
        "budget_ledger.py",
        "--home",
        str(home),
        "record",
        "--row",
        "机动",
        "--session",
        "s",
        "--batch",
        "b",
        "--count",
        "1",
    ]
    assert bl.main(argv) == 0
    assert (home / "state" / "budget.json").is_file()
    assert not (tmp_path / "should-not-be-used").exists()
