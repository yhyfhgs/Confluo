"""AC-1.2 · dry-run 不落盘 —— CLI 层端到端验收（Task 9）。

判据（acceptance-criteria.md AC-1.2）：`pull --dry-run` 后 `data/` 无新增文件、
DB 无 Asset(fetched)；输出的"将下载 N 篇"与随后实跑的实际下载数相等。

外加 T7b 协调项断言：**非 dry-run 的成功报告不得出现"将下载"预览行**
（report.py 渲染契约——预览行仅在 `planned_downloads>0 or planned_bytes>0` 即
dry-run 路径出现）。

以 `typer.testing.CliRunner`（进程内、真实 `Config.load` 路径）驱动；`no_rate_limit_wait`
中和 `RateLimiter.acquire` 把限速 wait 压到 0（本 AC 不测限速，免去真实等待——`rate.scale`
R1b 后拒绝 >1，不能再靠调大它快进，见 `integration/conftest.py`）。
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from typer.testing import CliRunner

from integration.conftest import DEFAULT_QUIRKS, VENUE
from paper_crawler.cli import app
from paper_crawler.storage.db import Database

runner = CliRunner()


@pytest.fixture(autouse=True)
def _fast_rate_limiter(no_rate_limit_wait: None) -> None:
    pass


def _data_files(home: Path) -> list[Path]:
    data_dir = home / "data"
    return [p for p in data_dir.rglob("*") if p.is_file()] if data_dir.is_dir() else []


def _asset_state_counts(home: Path) -> dict[str, int]:
    db = Database(home / "catalog.sqlite")
    try:
        rows = db.query("SELECT state, COUNT(*) AS n FROM asset GROUP BY state")
    finally:
        db.close()
    return {str(r["state"]): int(r["n"]) for r in rows}


def test_dry_run_no_side_effects_then_real_run_matches_and_has_no_preview(
    make_home: Callable[..., Path],
) -> None:
    """Closes: AC-1.2（dry-run 零落盘 + 预览数=实跑下载数 + 实跑报告无预览行）。"""
    home = make_home(DEFAULT_QUIRKS, rate_scale=1.0)

    # -- dry-run：止于 resolve，零下载副作用 ---------------------------------
    dry = runner.invoke(app, ["pull", VENUE, "--year", "2024", "--dry-run", "--home", str(home)])
    assert dry.exit_code == 0, dry.output

    # data/ 目录树快照：无任何新增文件（仅 ensure_dirs 建的空子目录，见判据"无新增文件"）
    assert _data_files(home) == []
    # DB 无 Asset(fetched)；但 resolve 已落库 → 10 个 planned（级联抵达 resolve）
    dry_states = _asset_state_counts(home)
    assert dry_states.get("fetched", 0) == 0
    assert dry_states.get("planned", 0) == 10
    # 输出的"将下载 N 篇"（planned_downloads=10）
    assert "将下载 10 篇" in dry.output

    # -- 实跑：succeeded == dry-run 预览数（AC-1.2 口径）---------------------
    real = runner.invoke(app, ["pull", VENUE, "--year", "2024", "--home", str(home)])
    assert real.exit_code == 0, real.output

    real_states = _asset_state_counts(home)
    assert real_states.get("fetched", 0) == 10  # 实跑把 10 个 planned 落成 fetched
    assert len(_data_files(home)) == 10  # 10 个 PDF 真实落盘
    # 报告计数表"成功 10"（== dry-run 的"将下载 10 篇"）
    assert "| 成功 | 10 |" in real.output
    # T7b 协调项：非 dry-run 成功报告**不得**出现 dry-run 预览行
    assert "将下载" not in real.output
