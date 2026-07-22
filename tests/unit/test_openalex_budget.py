"""openalex/budget.py 单测（design/adapters/aggregators.md §4 伪代码落地）：状态读写、
日期滚动重置、原子写、`add_spend` 累计、跨进程 `flock` 加固（Phase 4 M2b 检查单 #10）。
零真实网络、零 `HttpClient` 依赖。
"""

from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from paper_crawler.adapters.openalex import budget


def _today() -> str:
    return datetime.now(UTC).date().isoformat()


# --- load_state ----------------------------------------------------------------------------


def test_load_state_missing_file_returns_zero_spend_today(tmp_path: Path) -> None:
    state = budget.load_state(tmp_path / "does-not-exist.json")
    assert state.date == _today()
    assert state.spent_usd == 0.0


def test_load_state_reads_existing_same_day_value(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    path.write_text(json.dumps({"date": _today(), "spent_usd": 0.1234}), encoding="utf-8")

    state = budget.load_state(path)

    assert state.date == _today()
    assert state.spent_usd == 0.1234


def test_load_state_rolls_over_on_stale_date(tmp_path: Path) -> None:
    """date 滚动即重置 spent_usd=0（§4 伪代码"date 滚动即重置"）。"""
    path = tmp_path / "state.json"
    yesterday = (datetime.now(UTC).date() - timedelta(days=1)).isoformat()
    path.write_text(json.dumps({"date": yesterday, "spent_usd": 0.49}), encoding="utf-8")

    state = budget.load_state(path)

    assert state.date == _today()
    assert state.spent_usd == 0.0


def test_load_state_malformed_json_resets_to_zero(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    path.write_text("{not valid json", encoding="utf-8")

    state = budget.load_state(path)

    assert state.date == _today()
    assert state.spent_usd == 0.0


def test_load_state_non_object_top_level_resets_to_zero(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    path.write_text(json.dumps([1, 2, 3]), encoding="utf-8")

    state = budget.load_state(path)

    assert state.spent_usd == 0.0


def test_load_state_non_numeric_spent_usd_resets_to_zero(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    path.write_text(json.dumps({"date": _today(), "spent_usd": "not-a-number"}), encoding="utf-8")

    state = budget.load_state(path)

    assert state.spent_usd == 0.0


def test_load_state_bool_spent_usd_resets_to_zero(tmp_path: Path) -> None:
    """`bool` 是 `int` 子类——显式排除，防止 `True`（=1）被误当 1.0 美元。"""
    path = tmp_path / "state.json"
    path.write_text(json.dumps({"date": _today(), "spent_usd": True}), encoding="utf-8")

    state = budget.load_state(path)

    assert state.spent_usd == 0.0


# --- save_state / add_spend -----------------------------------------------------------------


def test_save_state_then_load_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "state.json"
    budget.save_state(path, budget.BudgetState(date=_today(), spent_usd=0.25))

    state = budget.load_state(path)

    assert state.spent_usd == 0.25


def test_save_state_creates_parent_directories(tmp_path: Path) -> None:
    path = tmp_path / "a" / "b" / "c" / "openalex-budget.json"
    budget.save_state(path, budget.BudgetState(date=_today(), spent_usd=0.0))
    assert path.is_file()


def test_save_state_does_not_leave_temp_files_behind(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    budget.save_state(path, budget.BudgetState(date=_today(), spent_usd=0.01))
    leftovers = list(tmp_path.glob(".openalex-budget-*.tmp"))
    assert leftovers == []


def test_save_state_cleans_up_temp_file_and_reraises_on_replace_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`os.replace` 失败（如磁盘只读/权限问题）时：温度文件被清理、异常原样上抛
    （不吞异常、不留下半成品临时文件）。"""

    def _boom(_src: str, _dst: str) -> None:
        raise OSError("simulated replace failure")

    monkeypatch.setattr(budget.os, "replace", _boom)
    path = tmp_path / "state.json"

    with pytest.raises(OSError, match="simulated replace failure"):
        budget.save_state(path, budget.BudgetState(date=_today(), spent_usd=0.02))

    assert not path.exists()
    assert list(tmp_path.glob(".openalex-budget-*.tmp")) == []


def test_add_spend_accumulates_across_calls(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    budget.add_spend(path, 0.1)
    second = budget.add_spend(path, 0.05)

    assert second.spent_usd == 0.15000000000000002 or abs(second.spent_usd - 0.15) < 1e-9


def test_add_spend_negative_amount_clamped_to_zero(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    budget.add_spend(path, 0.2)
    state = budget.add_spend(path, -5.0)

    assert state.spent_usd == 0.2  # 负值钳到 0，不倒扣预算


def test_add_spend_persists_to_disk(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    budget.add_spend(path, 0.3)

    on_disk = json.loads(path.read_text(encoding="utf-8"))
    assert on_disk["date"] == _today()
    assert on_disk["spent_usd"] == 0.3


# --- 跨进程加固：fcntl.flock（Phase 4 M2b 检查单 #10）------------------------------------------
#
# 真两进程验证需要真的起两个 OS 进程；本文件按任务边界注明的"单进程双句柄"手法模拟：
# `flock` 的互斥语义作用于*打开的文件描述*而非调用方所在的进程，同一进程内两次独立
# `open()` 产生的两个文件描述在 POSIX 上会像来自两个不同进程一样互斥——线程（而非
# 同步顺序调用）足以制造真实的并发访问窗口（`fcntl.flock` 是阻塞系统调用，等待期间
# 会释放 GIL，不会把并发悄悄压扁成顺序执行）。


def test_locked_second_handle_blocks_until_first_releases(tmp_path: Path) -> None:
    """两个独立句柄（线程模拟两个"进程"）：第二个必须等第一个释放锁才能进临界区。"""
    path = tmp_path / "state.json"
    first_in_critical_section = threading.Event()
    release_first = threading.Event()
    order: list[str] = []

    def _hold_first() -> None:
        with budget._locked(path):
            first_in_critical_section.set()
            release_first.wait(timeout=5.0)
            order.append("first-released")

    first_thread = threading.Thread(target=_hold_first)
    first_thread.start()
    assert first_in_critical_section.wait(timeout=5.0), "first handle never acquired the lock"

    def _try_second() -> None:
        with budget._locked(path):
            order.append("second-acquired")

    second_thread = threading.Thread(target=_try_second)
    second_thread.start()
    # 给第二个线程一个宽裕的窗口：若 flock 没有真的挡住它，它会在这段时间内抢先记录
    # （只断言"尚未发生"，不依赖精确计时——慢机器只会让这个窗口更安全，不会更 flaky）。
    time.sleep(0.3)
    assert order == [], "second handle acquired the lock while the first still held it"

    release_first.set()
    first_thread.join(timeout=5.0)
    second_thread.join(timeout=5.0)
    assert order == ["first-released", "second-acquired"]  # 严格先后，无交叉


def test_concurrent_add_spend_no_lost_updates_under_thread_contention(tmp_path: Path) -> None:
    """真实并发（8 线程 × 25 次 `add_spend`）下终态精确等于全部增量之和——无 lost update。

    这是对模块 docstring 加固前描述的具体缺陷（"两个并发进程各自读到同一旧值、各自
    加、各自写，后写者覆盖前写者增量"）的直接回归锁：无论线程调度如何交错，flock
    都会把每次 `add_spend` 的读→加→写整体串行化，终态必然精确等于 200 次 0.01 美元
    增量之和，不多不少。"""
    path = tmp_path / "state.json"
    workers = 8
    calls_per_worker = 25
    increment = 0.01
    expected_total = workers * calls_per_worker * increment

    def _spend_many() -> None:
        for _ in range(calls_per_worker):
            budget.add_spend(path, increment)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_spend_many) for _ in range(workers)]
        for future in futures:
            future.result(timeout=30.0)

    final = budget.load_state(path)
    assert final.spent_usd == pytest.approx(expected_total, abs=1e-9)


def test_locked_is_noop_when_flock_unavailable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Windows（无 `fcntl`）降级路径：`_locked` 变为无操作上下文管理器，不建锁文件。"""
    monkeypatch.setattr(budget, "_HAS_FLOCK", False)
    path = tmp_path / "state.json"

    with budget._locked(path):
        pass

    assert not budget._lock_path_for(path).exists()


def test_lock_path_for_is_state_path_with_lock_suffix(tmp_path: Path) -> None:
    path = tmp_path / "openalex-budget.json"
    assert budget._lock_path_for(path) == tmp_path / "openalex-budget.json.lock"


def test_add_spend_creates_lock_file_alongside_state(tmp_path: Path) -> None:
    """flock 目标是独立锁文件、不是 state 文件本身（见模块 docstring 的 rename/inode
    说明——`save_state` 会 replace state 路径，锁必须落在一个从不被 replace 的稳定
    路径上）。"""
    path = tmp_path / "state.json"
    budget.add_spend(path, 0.1)

    assert path.is_file()
    assert budget._lock_path_for(path).is_file()
