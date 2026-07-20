"""AC-1.5 · 状态机与 BLOCKED —— CLI 层完整链路验收（Task 9）。

判据（acceptance-criteria.md AC-1.5）：注入 auth_expired → 任务转 BLOCKED 不占重试；
`resume` 后回 PENDING 并完成。

CLI 完整链路：
  1. 注入 auth_expired（fail_fetch indexes [0,1]）→ `crawler pull` 退出 3；
  2. N 个 fetch 任务 BLOCKED（attempts==0，不占重试）；
  3. 改临时 venues YAML 移除注入（模拟人工修复凭证）；
  4. `crawler resume --all` → BLOCKED 回 PENDING；
  5. 重跑 `crawler pull` 退出 0，counts 齐全、文件全落。

批口径（T7c 审查确认，按实际行为断言）：整批连带下 BLOCKED 数 = 批内 fetch 任务数
（此处 volume 1 issue 1 = 5 篇 → 5 个 fetch 任务全 BLOCKED）。触发/连带的实际拆分是
**1 触发 + 4 连带**：即便毒化了 [0,1] 两个 index，FIFO 领取下只有最早的 fetch 任务
(index 0) 真正执行并触发 auth_expired（随即把 venue 标记为 auth_blocked），其余 4 个
（含 index 1）在领取时即被"同批连带"拦截、根本没执行到毒化 url——故 2 个毒化 index
不产生 2 个触发点。与 `test_pipeline_errors.test_auth_expired_blocks_batch_then_resume_refetches`
的 pipeline 级口径一致，本测试在 CLI 层复验。

重跑计数（按实际行为，见 cli.py 模块 docstring"全局 PENDING 回收"）：resume 后的
5 个 PENDING fetch 任务在重跑 pull 的首个 drain 即作为"残留任务"被回收执行 →
succeeded=5；随后 fetch 阶段再入队同键任务时它们已 DONE → fresh_skip，与
discover/enumerate/resolve 的 fresh_skip 叠加 → skipped=12（1+1+5+5）。
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from typer.testing import CliRunner

from integration.conftest import DEFAULT_QUIRKS, VENUE, write_mock_venue
from paper_crawler.cli import app
from paper_crawler.storage.db import Database

runner = CliRunner()


def _fail_fetch(error_class: str, indexes: list[int]) -> dict[str, object]:
    quirks = dict(DEFAULT_QUIRKS)
    quirks["fail_fetch"] = {"error_class": error_class, "paper_indexes": indexes}
    return quirks


def _blocked_fetch_tasks(home: Path) -> list[dict[str, object]]:
    db = Database(home / "catalog.sqlite")
    try:
        rows = db.query(
            "SELECT attempts, blocked_reason FROM task "
            "WHERE kind='fetch' AND state='BLOCKED' ORDER BY created_at, id"
        )
    finally:
        db.close()
    return [{"attempts": r["attempts"], "blocked_reason": r["blocked_reason"]} for r in rows]


def _assets_fetched(home: Path) -> int:
    db = Database(home / "catalog.sqlite")
    try:
        return int(db.query("SELECT COUNT(*) AS n FROM asset WHERE state='fetched'")[0]["n"])
    finally:
        db.close()


def _pdf_files(home: Path) -> list[Path]:
    pdf_root = home / "data" / "pdf"
    return sorted(pdf_root.rglob("*.pdf")) if pdf_root.is_dir() else []


def test_auth_expired_blocks_batch_then_resume_all_then_pull_completes(
    make_home: Callable[..., Path],
) -> None:
    """Closes: AC-1.5（auth_expired 整批 BLOCKED 不占重试 → resume --all → 重跑完成）。"""
    home = make_home(_fail_fetch("auth_expired", [0, 1]), rate_scale=100.0)

    # -- 1/2. 注入 auth_expired → pull 退出 3 + 5 个 fetch BLOCKED（attempts==0）------
    r1 = runner.invoke(app, ["pull", VENUE, "--volume", "1", "--issue", "1", "--home", str(home)])
    assert r1.exit_code == 3, r1.output
    assert "| 阻塞 | 5 |" in r1.output
    assert "resume --all" in r1.output  # 报告给出人工动作提示

    blocked = _blocked_fetch_tasks(home)
    assert len(blocked) == 5  # 批内 fetch 任务全部 BLOCKED（批口径）
    assert all(b["attempts"] == 0 for b in blocked)  # 不占重试次数（判据）
    cascade = sum("同批连带" in str(b["blocked_reason"]) for b in blocked)
    assert cascade == 4  # 1 触发 + 4 连带（毒化 [0,1] 仍只 1 触发，见模块 docstring）
    trigger_reasons = [
        str(b["blocked_reason"]) for b in blocked if "同批连带" not in str(b["blocked_reason"])
    ]
    assert len(trigger_reasons) == 1
    assert "auth_expired" in trigger_reasons[0]

    # status --blocked 也应呈现原因与 resume 指引（运维视图）
    status = runner.invoke(app, ["status", "--blocked", "--home", str(home)])
    assert status.exit_code == 0
    assert "auth_expired" in status.output
    assert "crawler resume --all" in status.output

    # 阻塞态：0 资产落地
    assert _assets_fetched(home) == 0
    assert _pdf_files(home) == []

    # -- 3/4. 人工修复（改 YAML 移除注入）→ resume --all --------------------------
    write_mock_venue(home / "venues", dict(DEFAULT_QUIRKS))
    resume = runner.invoke(app, ["resume", "--all", "--home", str(home)])
    assert resume.exit_code == 0, resume.output
    assert "已恢复 5 个任务" in resume.output

    # -- 5. 重跑 pull 退出 0；counts 齐全、文件全落 -----------------------------
    r2 = runner.invoke(app, ["pull", VENUE, "--volume", "1", "--issue", "1", "--home", str(home)])
    assert r2.exit_code == 0, r2.output
    assert "| 成功 | 5 |" in r2.output  # 残留 5 个 fetch 任务被回收执行
    assert "| 失败 | 0 |" in r2.output
    assert "| 阻塞 | 0 |" in r2.output
    assert "| 跳过 | 12 |" in r2.output  # fresh_skip 叠加（1+1+5+5，见模块 docstring）

    assert _assets_fetched(home) == 5
    assert len(_pdf_files(home)) == 5
    assert all(f.read_bytes().startswith(b"%PDF-") for f in _pdf_files(home))
