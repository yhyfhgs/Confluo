"""AC-1.3 · 断点续爬幂等 —— kill -9 压力验收（Task 9，最重）。

判据（acceptance-criteria.md AC-1.3）：在 fetch 阶段随机 kill 进程后重跑 `pull`；
最终 DB dump 与"不中断一次跑完"逐行一致；日志含 skipped 记录且无重复 FetchLog。

手法（phase1-implementation-plan Task 9 节）：
- `home_a`：`subprocess.Popen(python -m paper_crawler.cli pull mock_journal --year 2024
  --home <home_a>)`，venue YAML 设 `fetch_delay_ms=150`（拉长 fetch 阶段，让随机 kill
  稳定命中执行中的下载）；随机 0.3–1.2s 后 `SIGKILL`；循环 4 次（≥3）后完整跑到退出 0。
- `home_b`：同一 venue 语料一次跑完（对照）。

三条断言（canonical dump 口径的可执行定义见 `tests/helpers/dbdump.py` docstring）：
1. `canonical_dump(home_a) == canonical_dump(home_b)`：业务数据逐行一致（剔除 ULID/
   时钟/file_path 等不可复现列；task/fetch_log 历史轨迹合法地不同，不参与）；
2. 每 asset 成功 fetch_log **恰 1、无重复**（home_a 的 fetch_log 按 asset 聚合
   `error_class IS NULL` 行数，全部 == 1）——这正是 AC-1.3"无重复 FetchLog"判据本身。
   Phase 2 T1 把 fetch 收尾的 mark_asset(fetched) 与 add_fetch_log 并入
   `repo.finalize_fetch` 单事务（BEGIN IMMEDIATE），二者同进同退：SIGKILL 要么落在
   收尾提交前（asset 未 fetched，resume 重下并写 1 条），要么落在提交后（asset 已
   fetched 且已有 1 条日志，resume 因幂等跳过 `state=='fetched' and fetched_file_ok`
   不再补写）——`mark_asset` 与 `add_fetch_log` 之间的中途缝隙已消除。故每个最终
   fetched 的 asset 恒有且仅有 1 条成功日志，断言收紧为"全部 16 个 asset 各恰 1 条"
   （此前三步独立提交的已知 kill 窗口会让某 asset 成功日志为 0，只能断言 max ≤ 1；
   该窗口已随 finalize_fetch 消除）；
3. 重跑日志含 skipped（断点续爬跳过已完成工作；一次干净跑无 skipped，故 skipped 的
   出现本身即证明发生了续爬）。

语料：`papers_per_issue=8` → year 2024（volume 1）= 2 期 × 8 = 16 篇/资产。选 16 而非
默认 10，是为让"fresh 一跑 ~5s > 最大 kill 窗 1.2s"在 4 个循环里稳定各命中一次真实
kill（实测 8 个种子均 4/4 真实 kill、canonical 恒一致、总时长 ~7.5s < 60s 门禁）。
kill 时点随机（固定 seed 保证调度可复现），但三条断言与 kill 落点无关——这正是幂等
验收的要义。标 `@pytest.mark.slow`；`make test` 不加 marker 过滤，仍纳入 80% 门禁统计。
"""

from __future__ import annotations

import random
import signal
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

from helpers.dbdump import canonical_dump
from integration.conftest import VENUE
from paper_crawler.storage.db import Database

# year 2024 = volume 1；papers_per_issue=8 → 2 期 × 8 = 16 资产。两个 home 必须完全同
# 语料（含 fetch_delay_ms=150——delay 编码进 asset.url 查询串，是 canonical_dump 比较
# 列之一，两 home 必须一致否则 url 不等）。
_KILL_QUIRKS: dict[str, object] = {
    "volumes": 3,
    "issues_per_volume": 2,
    "papers_per_issue": 8,
    "seed": 42,
    "fetch_delay_ms": 150,
}
_EXPECTED_ASSETS = 16
_KILL_CYCLES = 4  # ≥3（判据）
_RNG_SEED = 20260721  # 固定 → kill 调度可复现；断言与落点无关


def _pull_cmd(home: Path) -> list[str]:
    # console-script 等价入口（`python -m paper_crawler.cli` 命中 __main__ 守卫），
    # 免 `uv run` 每次解析依赖的启动开销——kill 循环要快而稳。
    return [
        sys.executable,
        "-m",
        "paper_crawler.cli",
        "pull",
        VENUE,
        "--year",
        "2024",
        "--home",
        str(home),
    ]


def _run_to_completion(home: Path) -> int:
    proc = subprocess.Popen(_pull_cmd(home), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return proc.wait(timeout=90)


def _kill_cycle(home: Path, rng: random.Random) -> bool:
    """启动一次 pull，随机 0.3–1.2s 后 SIGKILL（若仍在跑）。返回是否真的 kill 了。"""
    proc = subprocess.Popen(_pull_cmd(home), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        proc.wait(timeout=rng.uniform(0.3, 1.2))
    except subprocess.TimeoutExpired:
        proc.send_signal(signal.SIGKILL)
        proc.wait(timeout=10)
        return True
    return False  # 进程在 kill 窗口内已自行跑完（续爬完成得太快）


def _success_logs_per_asset(home: Path) -> dict[str, int]:
    db = Database(home / "catalog.sqlite")
    try:
        rows = db.query(
            "SELECT asset_id, COUNT(*) AS n FROM fetch_log "
            "WHERE error_class IS NULL AND asset_id IS NOT NULL GROUP BY asset_id"
        )
    finally:
        db.close()
    return {str(r["asset_id"]): int(r["n"]) for r in rows}


def _assets_fetched(home: Path) -> int:
    db = Database(home / "catalog.sqlite")
    try:
        return int(db.query("SELECT COUNT(*) AS n FROM asset WHERE state='fetched'")[0]["n"])
    finally:
        db.close()


def _log_text(home: Path) -> str:
    log_dir = home / "logs"
    if not log_dir.is_dir():
        return ""
    return "".join(p.read_text(encoding="utf-8") for p in sorted(log_dir.glob("*.jsonl")))


def _pdf_files(home: Path) -> list[Path]:
    pdf_root = home / "data" / "pdf"
    return sorted(pdf_root.rglob("*.pdf")) if pdf_root.is_dir() else []


@pytest.mark.slow
def test_kill9_resume_is_idempotent_and_matches_clean_run(
    make_home: Callable[..., Path],
) -> None:
    """Closes: AC-1.3（kill -9 续爬幂等：与一次跑完逐行一致 + ≤1 成功 FetchLog + 含 skipped）。"""
    home_a = make_home(_KILL_QUIRKS, name="home_a")
    home_b = make_home(_KILL_QUIRKS, name="home_b")

    # -- home_a：随机 kill -9 循环 ≥3 次 → 完整跑到退出 0 ------------------------
    rng = random.Random(_RNG_SEED)
    real_kills = sum(_kill_cycle(home_a, rng) for _ in range(_KILL_CYCLES))
    assert real_kills >= 3, f"only {real_kills} real SIGKILLs landed (expected ≥3)"

    assert _run_to_completion(home_a) == 0  # 崩溃恢复后完整跑到成功退出

    # -- home_b：一次性连续跑完（对照）----------------------------------------
    assert _run_to_completion(home_b) == 0

    # 前提：两条路径都真正完成了全部 16 个资产（否则 dump 一致会退化为"都没跑完"的假绿）
    assert _assets_fetched(home_a) == _EXPECTED_ASSETS
    assert _assets_fetched(home_b) == _EXPECTED_ASSETS
    assert len(_pdf_files(home_a)) == _EXPECTED_ASSETS
    assert len(_pdf_files(home_b)) == _EXPECTED_ASSETS

    # 断言 1：canonical dump 逐行一致（ULID/时钟/file_path 剔除，task/fetch_log 不参与）
    assert canonical_dump(home_a / "catalog.sqlite") == canonical_dump(home_b / "catalog.sqlite")

    # 断言 2：每 asset 成功 fetch_log 恰 1——AC-1.3"无重复 FetchLog"判据本身。
    # Phase 2 T1 的 finalize_fetch 单事务消除了 mark_asset↔add_fetch_log 缝隙（见模块
    # docstring 断言 2），故每个最终 fetched 的 asset 恒有且仅有 1 条成功日志：收紧为
    # "全部 16 个 asset 各恰 1 条"（此前该窗口只能断言 max ≤ 1）。
    per_asset = _success_logs_per_asset(home_a)
    assert len(per_asset) == _EXPECTED_ASSETS, f"expected {_EXPECTED_ASSETS} logged: {per_asset}"
    assert all(n == 1 for n in per_asset.values()), f"non-unique success FetchLog: {per_asset}"

    # 断言 3：重跑日志含 skipped（续爬跳过已完成工作；干净一跑无 skipped）
    assert '"msg": "skipped"' in _log_text(home_a)
    assert '"msg": "skipped"' not in _log_text(home_b)  # 对照：一次跑完不产生 skipped
