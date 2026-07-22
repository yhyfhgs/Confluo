"""AC-1.4 · 限速合规 —— 真实时钟压力场景验收（Task 9）。

判据（acceptance-criteria.md AC-1.4）：压力场景下某 domain 的 FetchLog 时间戳间隔
统计：实际速率 ≤ 配置值 × 1.05。

场景：venue `rate_limit.requests_per_minute=600`、30 个资产（volumes=1 ×
issues_per_volume=2 × papers_per_issue=15 → year 2024 全量 30 篇），经 `crawler pull`
真实时钟跑（`typer.testing.CliRunner` 进程内，用真实 `time.sleep` sleeper——本 AC
必须真实等待，故**不**叠加 `[rate] scale` 快进）。

口径（缺陷 C-C 修复后重校准——稳态尾段测量）：mock.local 的 30 条 fetch_log 按 ts 升序。
自 C-C 修复起 resolve 阶段豁免限速闸（mock 的 `resolve_assets` 零网络），token bucket 的
burst=10 不再被 resolve 预耗，故在 **fetch 起点仍可用**——前若干次 fetch near-instant
（消耗 burst），之后进入 token 补充节流的稳态（0.1s/次）。AC-1.4 的"实际速率 ≤ 配置×1.05"
针对**稳态**速率，故测量窗跳过 burst 段，取第 15 次（>burst=10，确保纯稳态）起的相邻间隔：
- 稳态实际速率 = 60 / 稳态相邻间隔均值；断言 ≤ 600 × 1.05；
- 稳态段时长下界（14 个间隔 @0.1s ≥ 1.4s × 0.95）证明限速真实生效（无限速则近乎瞬时，
  速率将远超上限——两条断言互补）。
sleep 只会 overshoot 不会 undershoot，故慢机器上稳态间隔更长（速率更低、段更长），两条
断言同向更安全，跨机器不 flaky。

历史：C-C 修复前，fetch 前的 discover/enumerate/resolve 共 1+2+30=33 次取 token 已把
burst 预耗殆尽，使全 30 次 fetch 均落稳态（旧口径按全 30 条测均值与总时长）；resolve
豁免限速闸后该前提失效（burst 复活），改为直接测量稳态尾段——判据（稳态速率 ≤ 配置×1.05）
不变，只是测量窗从"全 30 条"收窄到"跳过 burst 的尾段"。
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from integration.conftest import VENUE
from paper_crawler.cli import app
from paper_crawler.storage.db import Database

runner = CliRunner()

_RATE_QUIRKS: dict[str, object] = {
    "volumes": 1,
    "issues_per_volume": 2,
    "papers_per_issue": 15,
    "seed": 42,
}
_CONFIGURED_RPM = 600.0


def _fetch_log_timestamps(home: Path, domain: str) -> list[datetime]:
    db = Database(home / "catalog.sqlite")
    try:
        rows = db.query(
            "SELECT ts FROM fetch_log WHERE domain = ? AND error_class IS NULL ORDER BY ts, id",
            (domain,),
        )
    finally:
        db.close()
    return [datetime.fromisoformat(str(r["ts"])) for r in rows]


# burst 段测量起点：> token bucket burst（=10），确保稳态尾段完全落在补充节流区。
_STEADY_FROM = 15


@pytest.mark.slow
def test_pull_respects_configured_rate_limit(make_home: Callable[..., Path]) -> None:
    """Closes: AC-1.4（真实时钟 30 次 fetch，mock.local **稳态**速率 ≤ 配置值 × 1.05）。"""
    home = make_home(_RATE_QUIRKS, rate_limit_rpm=_CONFIGURED_RPM)

    result = runner.invoke(app, ["pull", VENUE, "--year", "2024", "--home", str(home)])
    assert result.exit_code == 0, result.output
    assert "| 成功 | 30 |" in result.output

    ts = _fetch_log_timestamps(home, "mock.local")
    assert len(ts) == 30  # 压力场景：30 次成功 fetch 全部记 FetchLog（审计证据源）

    # 跳过 burst 段（resolve 豁免限速闸后 burst 在 fetch 起点复活，C-C）：只测稳态尾段。
    steady = ts[_STEADY_FROM:]
    steady_span = (steady[-1] - steady[0]).total_seconds()
    steady_mean_interval = steady_span / (len(steady) - 1)
    actual_rpm = 60.0 / steady_mean_interval

    # AC-1.4 判据：稳态实际速率 ≤ 配置值 × 1.05
    assert actual_rpm <= _CONFIGURED_RPM * 1.05, (
        f"steady actual_rpm={actual_rpm:.1f} exceeds {_CONFIGURED_RPM * 1.05:.1f} "
        f"(steady_span={steady_span:.3f}s, steady_mean_interval={steady_mean_interval:.4f}s)"
    )
    # 限速真实生效的下界：稳态 (30-15-1)=14 个间隔 @600rpm(0.1s/篇) 段长 ≥ 1.4s × 0.95
    expected_intervals = len(ts) - _STEADY_FROM - 1
    assert steady_span >= expected_intervals * 0.1 * 0.95, (
        f"steady_span={steady_span:.3f}s too short — rate limiting may not be active"
    )
