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


def test_load_ledger_corrupt_json_returns_empty(bl: ModuleType, ledger_path: Path) -> None:
    ledger_path.parent.mkdir(parents=True)
    ledger_path.write_text("{not valid json", encoding="utf-8")
    assert bl.load_ledger(ledger_path) == {}


def test_load_ledger_non_dict_top_level_returns_empty(bl: ModuleType, ledger_path: Path) -> None:
    ledger_path.parent.mkdir(parents=True)
    ledger_path.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    assert bl.load_ledger(ledger_path) == {}


def test_load_ledger_skips_malformed_row_keeps_valid_ones(
    bl: ModuleType, ledger_path: Path
) -> None:
    ledger_path.parent.mkdir(parents=True)
    ledger_path.write_text(
        json.dumps(
            {
                "机动": {
                    "consumed": 3,
                    "entries": [{"ts": "t", "session": "s", "batch": "b", "count": 3}],
                },
                "broken-consumed": {"consumed": "not-an-int", "entries": []},
                "broken-shape": "not-a-dict",
            }
        ),
        encoding="utf-8",
    )
    ledger = bl.load_ledger(ledger_path)
    assert set(ledger) == {"机动"}
    assert ledger["机动"].consumed == 3
    assert ledger["机动"].entries[0].session == "s"


def test_load_ledger_skips_malformed_entry_keeps_valid_ones(
    bl: ModuleType, ledger_path: Path
) -> None:
    ledger_path.parent.mkdir(parents=True)
    ledger_path.write_text(
        json.dumps(
            {
                "机动": {
                    "consumed": 5,
                    "entries": [
                        {"ts": "t1", "session": "s1", "batch": "b1", "count": 5},
                        {"ts": "t2", "session": "s2", "batch": "b2", "count": "nope"},
                        "not-a-dict-entry",
                    ],
                }
            }
        ),
        encoding="utf-8",
    )
    row = bl.load_ledger(ledger_path)["机动"]
    assert len(row.entries) == 1
    assert row.entries[0].session == "s1"


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
