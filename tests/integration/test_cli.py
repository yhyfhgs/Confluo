"""`crawler` CLI 集成测试（Task 8b：CLI 接线的行为验收）。

覆盖 phase1-implementation-plan.md Task 8 的退出码契约与命令面：
`venues lint`（合法/非法目录）、`pull`（成功落盘/`--dry-run`/`auth_expired` 整批
阻塞/`fail_enumerate` 失败）、`status`（`--blocked`/`--failed`/默认计数）、
`resume`（`--all` 后 re-resolve 生效、重新 pull 完成）、`retry`、`verify`（干净/
人为制造缺文件）、`report --last-run`、未知 venue、Selector 冲突（`--volume` 与
`--year` 同给、`--issue` 缺 `--volume`）。以 `typer.testing.CliRunner` 为主（进程内、
快），另附 2 条 subprocess 冒烟验证 `crawler` console-script entry point 真实可用。

环境隔离：每个 CliRunner 用例经 `_make_home` 建一个独立临时 HOME，写
`config.toml` 的 `[paths] venues_dirs = ["venues"]` 显式指向临时 venues 目录——
不依赖 `Config.load` 的 cwd 扫描回退（`Config.load` 默认候选目录含
`Path.cwd()/"venues"`，pytest 常见 cwd=仓库根目录，本身就带三份真实 venue；
显式钉住 venues_dirs 让每个用例的 venue 集合完全由自己控制，不与仓库内容
耦合）。venue 语料复用 `tests/integration/test_pipeline_e2e.py` 的
`DEFAULT_QUIRKS`/`VENUE` 常量（同一 mock 语料口径），故障注入手法照抄
`tests/integration/test_pipeline_errors.py` 的 `fail_fetch`/`fail_enumerate`
quirks 形状。
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from integration.test_pipeline_e2e import DEFAULT_QUIRKS, VENUE
from paper_crawler import cli as cli_module
from paper_crawler.cli import app
from paper_crawler.storage.db import Database
from paper_crawler.storage.repo import Repo
from paper_crawler.types import IssueRef, PaperStub, VenueSpec

REPO_ROOT = Path(__file__).resolve().parents[2]

runner = CliRunner()


# ---------------------------------------------------------------------------
# 环境构建 helper（CLI 测试独立于 test_pipeline_e2e.PipelineEnv：那套 dataclass
# 直接构造 Config，本套经真实 Config.load(home) + config.toml 落地，贴近实际
# CLI 使用路径）。
# ---------------------------------------------------------------------------


def _write_venue(
    venues_dir: Path, quirks: dict[str, object], *, rate_limit_rpm: float | None = None
) -> None:
    """写/改临时 mock venue YAML（形状同 PipelineEnv.write_venue，独立小实现）。"""
    doc: dict[str, object] = {
        "id": VENUE,
        "kind": "journal",
        "names": {"full": "Mock Journal", "aliases": ["MJ"]},
        "field": ["cs_ai"],
        "tier": "T1",
        "identifiers": {"issn": ["0000-0000"]},
        "metadata_source": "mock_platform",
        "fulltext_source": "mock_platform",
        "auth": {"level": "none"},
        "quirks": quirks,
        "status": "active",
    }
    if rate_limit_rpm is not None:
        doc["rate_limit"] = {"requests_per_minute": rate_limit_rpm}
    (venues_dir / "mock-journal.yaml").write_text(
        yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8"
    )


def _make_home(tmp_path: Path, quirks: dict[str, object] | None = None) -> Path:
    """建一个独立 HOME：config.toml 钉住 venues_dirs，写入一份 mock venue。"""
    home = tmp_path / "home"
    venues_dir = home / "venues"
    venues_dir.mkdir(parents=True)
    (home / "config.toml").write_text('[paths]\nvenues_dirs = ["venues"]\n', encoding="utf-8")
    _write_venue(venues_dir, dict(quirks if quirks is not None else DEFAULT_QUIRKS))
    return home


def _fail_fetch(error_class: str, indexes: list[int]) -> dict[str, object]:
    quirks = dict(DEFAULT_QUIRKS)
    quirks["fail_fetch"] = {"error_class": error_class, "paper_indexes": indexes}
    return quirks


def _fail_enumerate(volume: str, number: str) -> dict[str, object]:
    quirks = dict(DEFAULT_QUIRKS)
    quirks["fail_enumerate"] = {"volume": volume, "number": number}
    return quirks


def _pdf_files(home: Path) -> list[Path]:
    pdf_root = home / "data" / "pdf"
    return sorted(pdf_root.rglob("*.pdf")) if pdf_root.is_dir() else []


def _data_files(home: Path) -> list[Path]:
    data_dir = home / "data"
    return [p for p in data_dir.rglob("*") if p.is_file()] if data_dir.is_dir() else []


# ---------------------------------------------------------------------------
# venues lint / list
# ---------------------------------------------------------------------------


def test_venues_lint_valid_exits_0(tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    result = runner.invoke(app, ["venues", "lint", "--home", str(home)])
    assert result.exit_code == 0, result.output
    assert "OK" in result.output


def test_venues_lint_invalid_dir_exits_2_with_location(tmp_path: Path) -> None:
    """Closes: AC-1.6（非法 spec 被 `venues lint` 拒绝并给定位——CLI 层：退出 2 +
    file:venue_id:field 定位串。语义细分的七类非法见 test_venue_yaml_lint.py 单测）。"""
    home = tmp_path / "home"
    venues_dir = home / "venues"
    venues_dir.mkdir(parents=True)
    (home / "config.toml").write_text('[paths]\nvenues_dirs = ["venues"]\n', encoding="utf-8")
    (venues_dir / "broken.yaml").write_text(
        "\n".join(
            [
                "id: broken_venue",
                "kind: journal",
                "names: {full: Broken Venue}",
                "field: [cs_ai]",
                "identifiers: {issn: ['0000-0001']}",
                "metadata_source: totally_made_up_adapter",
                "fulltext_source: mock_platform",
            ]
        ),
        encoding="utf-8",
    )

    result = runner.invoke(app, ["venues", "lint", "--home", str(home)])

    assert result.exit_code == 2
    # LintIssue 逐条打印 file:venue_id:field: message —— 断言含定位信息。
    assert "broken.yaml" in result.output
    assert "broken_venue" in result.output
    assert "metadata_source" in result.output


def test_venues_list_filters_by_field(tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    result = runner.invoke(app, ["venues", "list", "--field", "cs_ai", "--home", str(home)])
    assert result.exit_code == 0
    assert VENUE in result.output


def test_venues_list_field_filter_excludes_non_matching(tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    result = runner.invoke(app, ["venues", "list", "--field", "finance", "--home", str(home)])
    assert result.exit_code == 0
    assert VENUE not in result.output


def test_venues_list_filters_by_tier(tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    result = runner.invoke(app, ["venues", "list", "--tier", "T2", "--home", str(home)])
    assert result.exit_code == 0
    assert VENUE not in result.output  # mock venue 固定 tier=T1


# ---------------------------------------------------------------------------
# pull：成功 / dry-run
# ---------------------------------------------------------------------------


def test_pull_success_exits_0_and_writes_files(tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    result = runner.invoke(app, ["pull", VENUE, "--year", "2024", "--home", str(home)])

    assert result.exit_code == 0, result.output
    assert "成功" in result.output
    files = _pdf_files(home)
    assert len(files) == 10
    assert all(f.read_bytes().startswith(b"%PDF-") for f in files)


def test_pull_year_end_to_end_report_shows_succeeded_n_failed_0(tmp_path: Path) -> None:
    """Closes: AC-1.1（mock venue 端到端 pull 的 CLI 层判据：DB 计数符合 mock 数据、
    data/ 文件数 = Asset(fetched) 数、报告"成功=N，失败=0"）。

    三项判据全部只从 CLI 产物断言（stdout 报告 + 落盘文件），不旁路进程内 API——
    补 `test_pipeline_e2e.test_pull_year_end_to_end`（pipeline 级 AC-1.1）缺的 CLI 端到端层。
    """
    home = _make_home(tmp_path)
    result = runner.invoke(app, ["pull", VENUE, "--year", "2024", "--home", str(home)])

    assert result.exit_code == 0, result.output
    # 报告"成功=N，失败=0"（year 2024 = 2 期 × 5 篇 = 10）
    assert "| 成功 | 10 |" in result.output
    assert "| 失败 | 0 |" in result.output
    # DB 中 Issue/Paper/Asset 计数符合 mock 数据（经报告 ingest 摘要断言，端到端可读）
    assert "issues=2 papers=10 assets_fetched=10/10" in result.output
    # data/ 下文件数 = Asset(fetched) 数（10）
    assert len(_pdf_files(home)) == 10


def test_pull_dry_run_exits_0_and_writes_no_files(tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    result = runner.invoke(app, ["pull", VENUE, "--year", "2024", "--dry-run", "--home", str(home)])

    assert result.exit_code == 0, result.output
    assert "将下载 10 篇" in result.output
    assert _data_files(home) == []


# ---------------------------------------------------------------------------
# pull：auth_expired 整批阻塞 / fail_enumerate 失败
# ---------------------------------------------------------------------------


def test_pull_auth_expired_exits_3(tmp_path: Path) -> None:
    home = _make_home(tmp_path, quirks=_fail_fetch("auth_expired", [0, 1]))
    result = runner.invoke(
        app, ["pull", VENUE, "--volume", "1", "--issue", "1", "--home", str(home)]
    )

    assert result.exit_code == 3, result.output
    assert "阻塞" in result.output


def test_pull_fail_enumerate_exits_1(tmp_path: Path) -> None:
    home = _make_home(tmp_path, quirks=_fail_enumerate("2", "1"))
    result = runner.invoke(app, ["pull", VENUE, "--volume", "2", "--home", str(home)])

    assert result.exit_code == 1, result.output
    assert "失败" in result.output


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------


def test_status_default_shows_state_counts(tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    result = runner.invoke(app, ["status", "--home", str(home)])

    assert result.exit_code == 0
    assert "PENDING: 0" in result.output
    assert "DONE: 0" in result.output


def test_status_blocked_shows_reason_and_resume_hint(tmp_path: Path) -> None:
    home = _make_home(tmp_path, quirks=_fail_fetch("auth_expired", [0, 1]))
    pull_result = runner.invoke(
        app, ["pull", VENUE, "--volume", "1", "--issue", "1", "--home", str(home)]
    )
    assert pull_result.exit_code == 3, pull_result.output

    result = runner.invoke(app, ["status", "--blocked", "--home", str(home)])

    assert result.exit_code == 0
    assert "auth_expired" in result.output
    assert "crawler resume" in result.output


def test_status_failed_shows_error_class_and_last_error(tmp_path: Path) -> None:
    home = _make_home(tmp_path, quirks=_fail_enumerate("2", "1"))
    pull_result = runner.invoke(app, ["pull", VENUE, "--volume", "2", "--home", str(home)])
    assert pull_result.exit_code == 1, pull_result.output

    result = runner.invoke(app, ["status", "--failed", "--home", str(home)])

    assert result.exit_code == 0
    assert "parse" in result.output


def test_status_blocked_empty_says_none(tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    result = runner.invoke(app, ["status", "--blocked", "--home", str(home)])
    assert result.exit_code == 0
    assert "无 BLOCKED 任务" in result.output


def test_status_failed_empty_says_none(tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    result = runner.invoke(app, ["status", "--failed", "--home", str(home)])
    assert result.exit_code == 0
    assert "无 FAILED 任务" in result.output


# ---------------------------------------------------------------------------
# resume --all 后重新 pull 完成（AC-1.5 的 CLI 层验证）
# ---------------------------------------------------------------------------


def test_resume_all_then_pull_completes(tmp_path: Path) -> None:
    home = _make_home(tmp_path, quirks=_fail_fetch("auth_expired", [0, 1]))
    blocked_result = runner.invoke(
        app, ["pull", VENUE, "--volume", "1", "--issue", "1", "--home", str(home)]
    )
    assert blocked_result.exit_code == 3, blocked_result.output

    # 人工修复：改临时 venue YAML 移除故障注入。
    _write_venue(home / "venues", dict(DEFAULT_QUIRKS))

    resume_result = runner.invoke(app, ["resume", "--all", "--home", str(home)])
    assert resume_result.exit_code == 0, resume_result.output
    assert "已恢复 5 个任务" in resume_result.output

    rerun_result = runner.invoke(
        app, ["pull", VENUE, "--volume", "1", "--issue", "1", "--home", str(home)]
    )
    assert rerun_result.exit_code == 0, rerun_result.output
    assert len(_pdf_files(home)) == 5


def test_resume_task_id_and_all_together_silently_prefers_all(tmp_path: Path) -> None:
    """TASK_ID 与 --all 同给：按现实现"静默走 --all"（M1，行为固化）。

    `resume` 命令体先判 `if all_:`，为真即整批恢复并直接返回，给出的 TASK_ID 被
    悄悄忽略（既不报用法错、也不单独校验该 id 是否存在）。这是已知 Minor（M1）：
    更严格的实现应在二者同给时报冲突退出 2。此处按当前行为固化，防止无意回归；
    若未来收紧为"冲突即退出 2"，改本测试并注销 M1。
    """
    home = _make_home(tmp_path, quirks=_fail_fetch("auth_expired", [0, 1]))
    pull_result = runner.invoke(
        app, ["pull", VENUE, "--volume", "1", "--issue", "1", "--home", str(home)]
    )
    assert pull_result.exit_code == 3, pull_result.output

    # 同给一个"不存在"的 TASK_ID 与 --all：若真按 TASK_ID 走会退出 2（KeyError），
    # 静默走 --all 则整批恢复、退出 0——以此区分两条实现路径。
    result = runner.invoke(
        app, ["resume", "definitely-not-a-real-task-id", "--all", "--home", str(home)]
    )
    assert result.exit_code == 0, result.output
    assert "已恢复 5 个任务" in result.output  # 走了 --all 整批分支，非 TASK_ID 分支


def test_resume_without_task_id_or_all_exits_2(tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    result = runner.invoke(app, ["resume", "--home", str(home)])
    assert result.exit_code == 2


def test_resume_unknown_task_id_exits_2(tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    result = runner.invoke(app, ["resume", "not-a-real-task-id", "--home", str(home)])
    assert result.exit_code == 2


def test_resume_single_task_id_succeeds(tmp_path: Path) -> None:
    home = _make_home(tmp_path, quirks=_fail_fetch("auth_expired", [0, 1]))
    pull_result = runner.invoke(
        app, ["pull", VENUE, "--volume", "1", "--issue", "1", "--home", str(home)]
    )
    assert pull_result.exit_code == 3, pull_result.output

    blocked_output = runner.invoke(app, ["status", "--blocked", "--home", str(home)]).output
    first_task_id = blocked_output.splitlines()[0].split()[0]

    _write_venue(home / "venues", dict(DEFAULT_QUIRKS))  # 人工修复，避免 fetch 再次触发注入
    result = runner.invoke(app, ["resume", first_task_id, "--home", str(home)])

    assert result.exit_code == 0, result.output
    assert "已恢复 1 个任务" in result.output


# ---------------------------------------------------------------------------
# retry
# ---------------------------------------------------------------------------


def test_retry_retries_failed_tasks(tmp_path: Path) -> None:
    home = _make_home(tmp_path, quirks=_fail_enumerate("2", "1"))
    pull_result = runner.invoke(app, ["pull", VENUE, "--volume", "2", "--home", str(home)])
    assert pull_result.exit_code == 1, pull_result.output

    result = runner.invoke(app, ["retry", "--home", str(home)])

    assert result.exit_code == 0
    assert "已重试 1 个任务" in result.output


def test_retry_unknown_error_class_exits_2(tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    result = runner.invoke(app, ["retry", "--class", "not_a_real_class", "--home", str(home)])
    assert result.exit_code == 2


# ---------------------------------------------------------------------------
# verify：干净 / 人为制造缺文件
# ---------------------------------------------------------------------------


def test_verify_clean_exits_0(tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    pull_result = runner.invoke(app, ["pull", VENUE, "--year", "2024", "--home", str(home)])
    assert pull_result.exit_code == 0, pull_result.output

    result = runner.invoke(app, ["verify", "--home", str(home)])

    assert result.exit_code == 0
    assert "一致" in result.output


def test_verify_detects_missing_file_exits_1(tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    pull_result = runner.invoke(app, ["pull", VENUE, "--year", "2024", "--home", str(home)])
    assert pull_result.exit_code == 0, pull_result.output
    victim = _pdf_files(home)[0]
    victim.unlink()  # 人为制造缺文件

    result = runner.invoke(app, ["verify", "--home", str(home)])

    assert result.exit_code == 1
    assert "missing_file" in result.output
    assert "re-fetch" in result.output


# ---------------------------------------------------------------------------
# report --last-run
# ---------------------------------------------------------------------------


def test_report_last_run_prints_saved_report(tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    pull_result = runner.invoke(app, ["pull", VENUE, "--year", "2024", "--home", str(home)])
    assert pull_result.exit_code == 0, pull_result.output

    result = runner.invoke(app, ["report", "--last-run", "--home", str(home)])

    assert result.exit_code == 0
    assert "Pipeline Report" in result.output
    assert "成功" in result.output


def test_report_without_history_prints_hint_and_exits_0(tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    result = runner.invoke(app, ["report", "--last-run", "--home", str(home)])

    assert result.exit_code == 0
    assert "尚无历史运行报告" in result.output


# ---------------------------------------------------------------------------
# 未知 venue / Selector 冲突
# ---------------------------------------------------------------------------


def test_pull_unknown_venue_exits_2(tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    result = runner.invoke(app, ["pull", "no_such_venue", "--year", "2024", "--home", str(home)])

    assert result.exit_code == 2
    assert "no_such_venue" in result.output


def test_pull_volume_and_year_together_exits_2(tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    result = runner.invoke(
        app, ["pull", VENUE, "--volume", "1", "--year", "2024", "--home", str(home)]
    )

    assert result.exit_code == 2
    assert "--volume" in result.output and "--year" in result.output


def test_pull_issue_without_volume_exits_2(tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    result = runner.invoke(app, ["pull", VENUE, "--issue", "1", "--home", str(home)])
    assert result.exit_code == 2


def test_pull_with_no_selector_exits_2(tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    result = runner.invoke(app, ["pull", VENUE, "--home", str(home)])
    assert result.exit_code == 2


def test_timeline_unknown_venue_exits_2(tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    result = runner.invoke(app, ["timeline", "no_such_venue", "--home", str(home)])
    assert result.exit_code == 2


def test_list_unknown_venue_exits_2(tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    result = runner.invoke(app, ["list", "no_such_venue", "--year", "2024", "--home", str(home)])
    assert result.exit_code == 2


def test_list_requires_volume_or_year_exits_2(tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    result = runner.invoke(app, ["list", VENUE, "--home", str(home)])
    assert result.exit_code == 2


def test_list_volume_and_year_together_exits_2(tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    result = runner.invoke(
        app, ["list", VENUE, "--volume", "1", "--year", "2024", "--home", str(home)]
    )
    assert result.exit_code == 2


def test_list_issue_without_volume_exits_2(tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    result = runner.invoke(
        app, ["list", VENUE, "--issue", "1", "--year", "2024", "--home", str(home)]
    )
    assert result.exit_code == 2


# ---------------------------------------------------------------------------
# timeline / list：正向路径轻量覆盖
# ---------------------------------------------------------------------------


def test_timeline_lists_discovered_issues(tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    result = runner.invoke(app, ["timeline", VENUE, "--home", str(home)])

    assert result.exit_code == 0, result.output
    assert "2024" in result.output  # volume "1" -> year 2024（DEFAULT_QUIRKS 派生）


def test_timeline_refresh_forces_rerun_within_freshness_window(tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    first = runner.invoke(app, ["timeline", VENUE, "--home", str(home)])
    assert first.exit_code == 0, first.output

    # 24h 新鲜度内不 --refresh：discover 应 fresh_skip（succeeded/failed 均 0）。
    again = runner.invoke(app, ["timeline", VENUE, "--home", str(home)])
    assert again.exit_code == 0, again.output

    refreshed = runner.invoke(app, ["timeline", VENUE, "--refresh", "--home", str(home)])
    assert refreshed.exit_code == 0, refreshed.output
    assert "2024" in refreshed.output


def test_list_previews_papers_without_downloading(tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    result = runner.invoke(app, ["list", VENUE, "--year", "2024", "--home", str(home)])

    assert result.exit_code == 0, result.output
    assert "Mock Paper" in result.output
    assert _pdf_files(home) == []  # 只 discover+enumerate，不下载


def test_list_with_volume_and_issue_scopes_to_single_issue(tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    result = runner.invoke(
        app, ["list", VENUE, "--volume", "1", "--issue", "1", "--home", str(home)]
    )

    assert result.exit_code == 0, result.output
    assert "Mock Paper 1.1" in result.output


def test_papers_in_scope_dedupes_paper_shared_across_issues(
    tmp_path: Path, venue: VenueSpec
) -> None:
    """`list` 的跨-issue 去重分支（cli._papers_in_scope 的 `if paper_id in seen: continue`）。

    mock 语料每期 DOI 唯一、不自然产生跨期 paper；此处直接经 Repo 用**同 DOI**两次
    `upsert_paper` 把一个 paper 链到两期（design/06 §3 强合并锚点，同 test_dbdump 手法），
    再喂给 `_papers_in_scope`——覆盖 `list` 跨期展示时"同一 paper 只列一次"的去重路径。
    """
    db = Database(tmp_path / "catalog.sqlite")
    db.migrate()
    try:
        repo = Repo(db)
        repo.upsert_venue(venue)
        i1 = repo.upsert_issue(
            IssueRef(venue_id=venue.id, volume="1", number="1", year=2024), source="mock"
        )
        i2 = repo.upsert_issue(
            IssueRef(venue_id=venue.id, volume="1", number="2", year=2024), source="mock"
        )
        shared = PaperStub(title="Shared Across Issues", identifiers=(("doi", "10.9999/shared"),))
        repo.upsert_paper(venue.id, i1, shared)
        repo.upsert_paper(venue.id, i2, shared)  # 同 DOI → 复用 paper、追加链到 i2
        # 对照：一篇只在 i1，确保不是"全量去重"而是"跨期同 paper 去重"
        repo.upsert_paper(
            venue.id, i1, PaperStub(title="Only In One", identifiers=(("doi", "10.9999/only"),))
        )

        issues = repo.list_issues(venue.id, volume="1")
        assert len(issues) == 2
        papers = cli_module._papers_in_scope(repo, venue.id, issues)

        titles = [str(p["title"]) for p in papers]
        assert titles.count("Shared Across Issues") == 1  # 跨期只列一次（去重分支命中）
        assert sorted(titles) == ["Only In One", "Shared Across Issues"]
    finally:
        db.close()


# ---------------------------------------------------------------------------
# subprocess 冒烟：验证 crawler console-script entry point 真实可用
# ---------------------------------------------------------------------------


def test_subprocess_venues_lint_against_repo_venues(tmp_path: Path) -> None:
    """`uv run crawler venues lint` 对仓库自带 venues/ 通过（Task 8 DoD）。"""
    isolated_home = tmp_path / "home"  # 避免污染真实 ~/.paper-crawler
    result = subprocess.run(
        ["uv", "run", "crawler", "venues", "lint"],
        cwd=REPO_ROOT,
        env={**os.environ, "PAPER_CRAWLER_HOME": str(isolated_home)},
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_subprocess_pull_dry_run_mock_journal(tmp_path: Path) -> None:
    """`uv run crawler pull mock_journal --year 2024 --dry-run --home <tmp>` 退出 0。"""
    home = tmp_path / "home"
    result = subprocess.run(
        [
            "uv",
            "run",
            "crawler",
            "pull",
            "mock_journal",
            "--year",
            "2024",
            "--dry-run",
            "--home",
            str(home),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr


# ---------------------------------------------------------------------------
# console-script 入口包装（`[project.scripts] crawler = "paper_crawler.cli:main"`
# 实际指向的可调用对象）：进程内直接调用，覆盖 subprocess 冒烟测不到的这一行
# （subprocess 起一个独立 Python 解释器，覆盖率统计不跨进程）。
# ---------------------------------------------------------------------------


def test_main_entry_point_wraps_app_and_exits_with_its_code(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home = _make_home(tmp_path)
    monkeypatch.setattr(sys, "argv", ["crawler", "venues", "lint", "--home", str(home)])

    with pytest.raises(SystemExit) as exc_info:
        cli_module.main()

    assert exc_info.value.code == 0
