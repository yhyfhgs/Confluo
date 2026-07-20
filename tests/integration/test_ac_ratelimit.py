"""AC-1.4 · 限速合规 —— 真实时钟压力场景验收（Task 9）。

判据（acceptance-criteria.md AC-1.4）：压力场景下某 domain 的 FetchLog 时间戳间隔
统计：实际速率 ≤ 配置值 × 1.05。

场景：venue `rate_limit.requests_per_minute=600`、30 个资产（volumes=1 ×
issues_per_volume=2 × papers_per_issue=15 → year 2024 全量 30 篇），经 `crawler pull`
真实时钟跑（`typer.testing.CliRunner` 进程内，用真实 `time.sleep` sleeper——本 AC
必须真实等待，故**不**叠加 `[rate] scale` 快进）。

口径（Task 9 节"滑动窗口=60s 缩放后等效——直接验证相邻间隔均值与总时长"）：
mock.local 的 30 条 fetch_log 按 ts 升序，
- 实际速率 = 60 / 相邻间隔均值（= 60 × (n-1) / 总时长）；断言 ≤ 600 × 1.05；
- 总时长下界断言（≥ 2.9s × 0.95）证明限速真实生效（无限速则 30 次 fetch 近乎瞬时，
  速率将远超上限——两条断言互补）。

token bucket burst=10 在 fetch 阶段前已被 discover/enumerate/resolve 的取 token
消耗殆尽（1+2+30 = 33 次取 token 先于 30 次 fetch），故 fetch 阶段是纯稳态 0.1s/次
的节流，间隔均值 ≈ 0.1s、速率 ≈ 600rpm（实测跨多次运行稳定在 600–601rpm、
总时长 2.89–2.90s）。sleep 只会 overshoot 不会 undershoot，故慢机器上间隔更长
（速率更低、总时长更大），两条断言同向更安全，跨机器不 flaky。
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


@pytest.mark.slow
def test_pull_respects_configured_rate_limit(make_home: Callable[..., Path]) -> None:
    """Closes: AC-1.4（真实时钟 30 次 fetch，mock.local 实际速率 ≤ 配置值 × 1.05）。"""
    home = make_home(_RATE_QUIRKS, rate_limit_rpm=_CONFIGURED_RPM)

    result = runner.invoke(app, ["pull", VENUE, "--year", "2024", "--home", str(home)])
    assert result.exit_code == 0, result.output
    assert "| 成功 | 30 |" in result.output

    ts = _fetch_log_timestamps(home, "mock.local")
    assert len(ts) == 30  # 压力场景：30 次成功 fetch 全部记 FetchLog（审计证据源）

    total_span = (ts[-1] - ts[0]).total_seconds()
    mean_interval = total_span / (len(ts) - 1)
    actual_rpm = 60.0 / mean_interval

    # AC-1.4 判据：实际速率 ≤ 配置值 × 1.05
    assert actual_rpm <= _CONFIGURED_RPM * 1.05, (
        f"actual_rpm={actual_rpm:.1f} exceeds {_CONFIGURED_RPM * 1.05:.1f} "
        f"(total_span={total_span:.3f}s, mean_interval={mean_interval:.4f}s)"
    )
    # 限速真实生效的下界：30 篇 @600rpm(0.1s/篇) 稳态总时长 ≥ 2.9s × 0.95
    assert total_span >= 2.9 * 0.95, (
        f"total_span={total_span:.3f}s too short — rate limiting may not be active"
    )
