"""openalex/budget.py 单测（design/adapters/aggregators.md §4 伪代码落地）：状态读写、
日期滚动重置、原子写、`add_spend` 累计。零真实网络、零 `HttpClient` 依赖。
"""

from __future__ import annotations

import json
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
