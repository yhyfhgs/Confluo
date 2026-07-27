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

import hashlib
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from helpers.fulltext_schema import write_fulltext_row
from integration.test_pipeline_e2e import DEFAULT_QUIRKS, VENUE
from paper_crawler import cli as cli_module
from paper_crawler.cli import app
from paper_crawler.errors import ErrorClass
from paper_crawler.storage.db import Database
from paper_crawler.storage.repo import Repo
from paper_crawler.tasks import TaskQueue
from paper_crawler.types import IssueRef, PaperStub, VenueSpec
from paper_crawler.verify import VerifyIssue

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


def test_status_never_prints_credentials_from_task_error_columns(tmp_path: Path) -> None:
    """`status --blocked/--failed` 是 `blocked_reason`/`last_error` 的**直印面**。

    R1 审查 P2-2（第四 sink）：browser-fetch 的异常串会内联 URL，而同批 volatile URL
    带一次性签名 token ⇒ `runner._route_error(str(exc))` → `queue.fail/block` → 本命令
    明文直印。脱敏落在队列的持久化边界，故本测从**用户看得见的那一面**验收。
    """
    home = _make_home(tmp_path)
    db = Database(home / "catalog.sqlite")
    db.migrate()
    queue = TaskQueue(db)
    signed = "https://h.test/Delivery.cfm/x.pdf?abstractid=7&signature=SEKRET123456"

    blocked_id = str(queue.enqueue("fetch", VENUE, {"asset": "a"}).task_id)
    assert queue.claim_next() is not None
    queue.block(blocked_id, f"browser-fetch 停手: 命中风控 {signed}")

    failed_id = str(queue.enqueue("fetch", VENUE, {"asset": "b"}).task_id)
    assert queue.claim_next() is not None
    for _ in range(4):  # TRANSIENT RetrySpec(4)：跑满预算落 FAILED
        queue.fail(failed_id, ErrorClass.TRANSIENT, f"浏览器导航无响应: {signed}")
        if queue.claim_next() is None:
            break
    db.close()

    blocked_out = runner.invoke(app, ["status", "--blocked", "--home", str(home)]).output
    failed_out = runner.invoke(app, ["status", "--failed", "--home", str(home)]).output

    assert "SEKRET123456" not in blocked_out
    assert "SEKRET123456" not in failed_out
    assert "signature=***" in blocked_out
    assert "signature=***" in failed_out
    assert "abstractid=7" in blocked_out  # 可诊断性保留


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
# verify：干净 / 人为制造三类不一致（AC-3.3；phase3-implementation-plan §4 T2）
#
# 三类各自独立用例 + 组合场景 + 干净库 0 误报（deliverable #4）。missing_file/
# hash_mismatch 各附一条"照建议命令实际执行 → 复检转清洁"的用例，不止断言建议
# 文本包含正确的命令形态，还证明其真实有效（deliverable #2"正确修复建议"的
# 最强验证）。orphan_file 没有对应的自动纳管命令（现有 CLI 命令面核实结论，见
# cli.py `_verify_fix_hint`），故只断言建议文本如实说明、不臆造命令。
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
    # 正确修复建议（AC-3.3）：真实存在的恢复命令，不是 `resume`/`retry`（那两个只管
    # BLOCKED/FAILED 任务，对"已 DONE 但文件被删"的本情形无效——见现状盘点结论）。
    assert "--force" in result.output
    assert "crawler pull" in result.output


def test_verify_detects_orphan_file_exits_1(tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    pull_result = runner.invoke(app, ["pull", VENUE, "--year", "2024", "--home", str(home)])
    assert pull_result.exit_code == 0, pull_result.output
    orphan_path = home / "data" / "pdf" / "stray-orphan.pdf"
    orphan_path.write_bytes(b"%PDF-1.4\n% orphan\n%%EOF\n")  # 人为制造孤儿文件

    result = runner.invoke(app, ["verify", "--home", str(home)])

    assert result.exit_code == 1
    assert "orphan_file" in result.output
    assert "adopt" in result.output
    assert str(orphan_path) in result.output
    # 正确修复建议（AC-3.3"纳管或清理提示"）：CLI 命令面核实结论是当前无自动纳管
    # 命令，如实说明而非编造一个不存在的 `crawler adopt`。
    assert "纳管" in result.output


def test_verify_detects_hash_mismatch_exits_1(tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    pull_result = runner.invoke(app, ["pull", VENUE, "--year", "2024", "--home", str(home)])
    assert pull_result.exit_code == 0, pull_result.output
    victim = _pdf_files(home)[0]
    victim.write_bytes(b"%PDF-1.4\n% corrupted-in-place\n%%EOF\n")  # 人为制造哈希不符

    result = runner.invoke(app, ["verify", "--home", str(home)])

    assert result.exit_code == 1
    assert "hash_mismatch" in result.output
    assert "quarantine" in result.output
    # 正确修复建议（AC-3.3"标记 corrupt+re-fetch"）：两个动作都要出现。
    assert "corrupt" in result.output
    assert "--force" in result.output


def test_verify_detects_all_three_kinds_combined_exits_1(tmp_path: Path) -> None:
    """组合场景：三类不一致同时存在，`verify` 一次跑全部检出（deliverable #4）。"""
    home = _make_home(tmp_path)
    pull_result = runner.invoke(app, ["pull", VENUE, "--year", "2024", "--home", str(home)])
    assert pull_result.exit_code == 0, pull_result.output
    files = _pdf_files(home)
    assert len(files) >= 3  # 需要至少 3 个互不相同的受害文件

    missing_victim, hash_victim = files[0], files[1]
    missing_victim.unlink()
    hash_victim.write_bytes(b"%PDF-1.4\n% corrupted-in-place\n%%EOF\n")
    orphan_path = home / "data" / "pdf" / "stray-orphan.pdf"
    orphan_path.write_bytes(b"%PDF-1.4\n% orphan\n%%EOF\n")

    result = runner.invoke(app, ["verify", "--home", str(home)])

    assert result.exit_code == 1
    assert "missing_file" in result.output
    assert "hash_mismatch" in result.output
    assert "orphan_file" in result.output
    assert "发现 3 处不一致。" in result.output


def test_verify_missing_file_fix_command_actually_repairs_it(tmp_path: Path) -> None:
    """锁定"正确修复建议"而不止是文本包含：照建议的命令形态真的执行一遍，
    verify 复检必须转清洁——证明建议不是空话（AC-3.3 最强验证形态）。
    """
    home = _make_home(tmp_path)
    pull_result = runner.invoke(app, ["pull", VENUE, "--year", "2024", "--home", str(home)])
    assert pull_result.exit_code == 0, pull_result.output
    victim = _pdf_files(home)[0]
    original = victim.read_bytes()
    victim.unlink()

    broken = runner.invoke(app, ["verify", "--home", str(home)])
    assert broken.exit_code == 1

    # 建议命令形态：`crawler pull <venue> --year <year> --force`（真实 CLI 能力：
    # fetch 任务一旦 DONE 永久新鲜，须 --force 绕过——见 tasks.py FRESHNESS_TTL）。
    repair = runner.invoke(app, ["pull", VENUE, "--year", "2024", "--force", "--home", str(home)])
    assert repair.exit_code == 0, repair.output

    healed = runner.invoke(app, ["verify", "--home", str(home)])
    assert healed.exit_code == 0
    assert "一致" in healed.output
    assert victim.is_file()
    assert victim.read_bytes() == original  # mock fetch 内容确定性（同 doi 同字节）


def test_verify_hash_mismatch_fix_command_actually_repairs_it(tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    pull_result = runner.invoke(app, ["pull", VENUE, "--year", "2024", "--home", str(home)])
    assert pull_result.exit_code == 0, pull_result.output
    victim = _pdf_files(home)[0]
    original = victim.read_bytes()
    victim.write_bytes(b"%PDF-1.4\n% corrupted-in-place\n%%EOF\n")

    broken = runner.invoke(app, ["verify", "--home", str(home)])
    assert broken.exit_code == 1

    repair = runner.invoke(app, ["pull", VENUE, "--year", "2024", "--force", "--home", str(home)])
    assert repair.exit_code == 0, repair.output

    healed = runner.invoke(app, ["verify", "--home", str(home)])
    assert healed.exit_code == 0
    assert victim.read_bytes() == original


# ---------------------------------------------------------------------------
# verify：T14 扩展（design/12 §9.2）—— si/fulltext 两个表面 + 信息级 stale_fulltext
# ---------------------------------------------------------------------------


def test_verify_detects_si_orphan_file_exits_1(tmp_path: Path) -> None:
    """si 与 pdf 同构地纳入孤儿扫描范围（T14；design/12 §9.2 扫描范围扩展）——
    `emit_si=True` quirk 驱动 mock adapter 真实落一份 si 资产，额外放一份未登记的
    孤儿文件在同一 si/ 子树下，锁定"si 确实被端到端扫描到"（`tests/unit/test_verify.py`
    已单测锁定文件级判定，本用例只补 CLI 端到端一次直路径回归）。
    """
    quirks = dict(DEFAULT_QUIRKS)
    quirks["emit_si"] = True
    home = _make_home(tmp_path, quirks)
    pull_result = runner.invoke(app, ["pull", VENUE, "--year", "2024", "--home", str(home)])
    assert pull_result.exit_code == 0, pull_result.output
    orphan_path = home / "data" / "si" / "stray-orphan.zip"
    orphan_path.parent.mkdir(parents=True, exist_ok=True)
    orphan_path.write_bytes(b"PK\x03\x04stray-si-bytes")

    result = runner.invoke(app, ["verify", "--home", str(home)])

    assert result.exit_code == 1
    assert "orphan_file" in result.output
    assert "adopt" in result.output
    assert str(orphan_path) in result.output


def test_verify_detects_fulltext_orphan_file_exits_1(tmp_path: Path) -> None:
    """fulltext/ 纳入孤儿扫描范围（T14；design/12 §9.2），suggestion 为 `prune`
    （区别于 asset 侧的 `adopt`——全文产物可从源 PDF 重新派生，直接删除即可）。
    """
    home = _make_home(tmp_path)
    pull_result = runner.invoke(app, ["pull", VENUE, "--year", "2024", "--home", str(home)])
    assert pull_result.exit_code == 0, pull_result.output
    orphan_path = home / "data" / "fulltext" / "stray-orphan.txt"
    orphan_path.parent.mkdir(parents=True, exist_ok=True)
    orphan_path.write_text("nobody points at me", encoding="utf-8")

    result = runner.invoke(app, ["verify", "--home", str(home)])

    assert result.exit_code == 1
    assert "orphan_file" in result.output
    assert "prune" in result.output
    assert str(orphan_path) in result.output


def test_verify_reports_pending_extraction_count_without_failing(tmp_path: Path) -> None:
    """`count_pending_extraction`（`state='noop'` 占位行，design/12 §9.2 附注）经
    `verify` 输出为一行提示，不影响退出码——覆盖 `verify()` 命令里 `pending` 分支。
    """
    home = _make_home(tmp_path)
    pull_result = runner.invoke(app, ["pull", VENUE, "--year", "2024", "--home", str(home)])
    assert pull_result.exit_code == 0, pull_result.output

    db = Database(home / "catalog.sqlite")
    try:
        repo = Repo(db)
        paper_id = str(repo.list_assets()[0]["paper_id"])
        write_fulltext_row(repo, paper_id, text_path=None, state="noop")
    finally:
        db.close()

    result = runner.invoke(app, ["verify", "--home", str(home)])

    assert result.exit_code == 0, result.output
    assert "另有 1 篇论文的全文仍是占位" in result.output


def test_verify_stale_fulltext_alone_does_not_fail_exit_code(tmp_path: Path) -> None:
    """T14 关键行为契约（design/12 §9.2）：`stale_fulltext` 是信息级，单独出现时
    **不应**使 `verify` 非零退出——它是可自愈的静默错配提示（下次 extract 自动重抽
    取代），不是需要人工立即处理的缺陷。若这条回归，AC-7.4"全库 verify 通过"就会
    被一个本不该算数的信号误判为不通过。

    T7（真实 extract 落地）尚未合并，直接经 `Database`/`Repo` 打开 CLI 用的同一份
    `catalog.sqlite`，用 `write_fulltext_row`（T7 增量列契约）造一行"asset 已
    re-fetch、fulltext 仍指向旧内容"的陈旧行——同 `tests/unit/test_verify.py::
    test_verify_store_detects_stale_fulltext_as_info_severity` 的构造手法。
    """
    home = _make_home(tmp_path)
    pull_result = runner.invoke(app, ["pull", VENUE, "--year", "2024", "--home", str(home)])
    assert pull_result.exit_code == 0, pull_result.output

    db = Database(home / "catalog.sqlite")
    try:
        repo = Repo(db)
        asset = repo.list_assets()[0]
        asset_id = str(asset["id"])
        paper_id = str(asset["paper_id"])
        old_sha = str(asset["sha256"])
        pdf_path = Path(str(asset["file_path"]))

        # 模拟"asset 被 re-fetch"：磁盘内容与 DB sha256 都变成新内容。
        new_content = b"%PDF-1.4\n% re-fetched with new content\n%%EOF\n"
        pdf_path.write_bytes(new_content)
        new_sha = hashlib.sha256(new_content).hexdigest()
        repo.mark_asset(
            asset_id,
            state="fetched",
            file_path=str(pdf_path),
            bytes_=len(new_content),
            sha256=new_sha,
        )

        # fulltext 行自身完全自洽（文件在、哈希对、路径对）——只是内容出自旧版 PDF。
        text_path = home / "data" / "fulltext" / VENUE / "2024" / f"{paper_id}.txt"
        text_content = b"text extracted from the pre-refetch pdf content"
        text_path.parent.mkdir(parents=True, exist_ok=True)
        text_path.write_bytes(text_content)
        text_sha = hashlib.sha256(text_content).hexdigest()
        write_fulltext_row(
            repo,
            paper_id,
            text_path=str(text_path),
            text_sha256=text_sha,
            asset_id=asset_id,
            source_sha256=old_sha,
            state="extracted",
        )
    finally:
        db.close()

    result = runner.invoke(app, ["verify", "--home", str(home)])

    assert result.exit_code == 0, result.output
    assert "stale_fulltext" in result.output
    assert "re-extract" in result.output
    assert "信息" in result.output


# ---------------------------------------------------------------------------
# verify 修复建议 helper：`_pdf_layout_scope`/`_pull_force_cmd` 边界分支直测
#
# 正向路径（venue_id+year 均能从真实 pull 产出的路径解析）已被上面的集成用例
# 覆盖；这里直调私有函数补 CLI 端到端难以自然触达的边界——空 file_path、相对
# 路径、pdf/ 树外路径、year 段非数字、venue 已知但 scope 缺失、两者皆缺——同
# `_papers_in_scope` 直调私有函数的既有先例（见上方
# test_papers_in_scope_dedupes_paper_shared_across_issues）。
# ---------------------------------------------------------------------------


def test_pdf_layout_scope_empty_file_path_returns_none_none(tmp_path: Path) -> None:
    """`missing_file` 且 `file_path` 本身为空的异常路径（见
    tests/unit/test_verify.py::test_verify_store_detects_missing_file_when_file_path_empty）。
    """
    assert cli_module._pdf_layout_scope(tmp_path, "") == (None, None)


def test_pdf_layout_scope_resolves_relative_path_under_data_dir(tmp_path: Path) -> None:
    """相对 file_path 按 data_dir 展开（与 verify.py `_resolve` 的兼容语义对齐）。"""
    relative = "pdf/mock_journal/2024/paper123.pdf"
    assert cli_module._pdf_layout_scope(tmp_path, relative) == ("mock_journal", "2024")


def test_pdf_layout_scope_path_outside_pdf_tree_returns_none_none(tmp_path: Path) -> None:
    outside = str(tmp_path / "si" / "mock_journal" / "2024" / "extra.zip")
    assert cli_module._pdf_layout_scope(tmp_path, outside) == (None, None)


def test_pdf_layout_scope_non_digit_year_segment_returns_none_year(tmp_path: Path) -> None:
    """`_asset_final_path`（pipeline/stages.py）对缺失 year 落目录名 "unknown"；
    不是合法 `--year` 输入，`_pdf_layout_scope` 须识别为不可用而非当真年份返回。
    """
    unknown_year_path = str(tmp_path / "pdf" / "mock_journal" / "unknown" / "paper123.pdf")
    assert cli_module._pdf_layout_scope(tmp_path, unknown_year_path) == ("mock_journal", None)


def test_pull_force_cmd_venue_only_prompts_for_scope_flag() -> None:
    cmd = cli_module._pull_force_cmd("mock_journal", None, "asset-1")
    assert "crawler pull mock_journal --force" in cmd
    assert "--volume" in cmd and "--year" in cmd and "--doi" in cmd


def test_pull_force_cmd_neither_known_includes_asset_id() -> None:
    cmd = cli_module._pull_force_cmd(None, None, "asset-42")
    assert "<venue_id>" in cmd
    assert "asset-42" in cmd


def test_pull_force_cmd_neither_known_without_asset_id_omits_asset_marker() -> None:
    cmd = cli_module._pull_force_cmd(None, None, None)
    assert "<venue_id>" in cmd
    assert "asset=" not in cmd  # 无 asset_id 时不留残缺占位


# ---------------------------------------------------------------------------
# verify 修复建议 helper（T14 扩展）：`_si_layout_scope`/`_fulltext_layout_scope`/
# `_asset_layout_scope`/`_pull_extract_cmd`/`_verify_fix_hint` 新分支边界直测
#
# 与上方 `_pdf_layout_scope`/`_pull_force_cmd` 同一先例：正向路径已被 CLI 端到端用例
# 覆盖，这里直调私有函数补边界（si 多一层 paper 子目录、fulltext 域、prune/re-extract
# 两条新 suggestion、stale_fulltext 的 info 措辞）。
# ---------------------------------------------------------------------------


def test_si_layout_scope_resolves_relative_path_with_paper_subdir(tmp_path: Path) -> None:
    """si 比 pdf 多一层 paper ulid 子目录（design/06 §4），venue/year 段位次不变。"""
    relative = "si/mock_journal/2024/paper123/supplement.zip"
    assert cli_module._si_layout_scope(tmp_path, relative) == ("mock_journal", "2024")


def test_si_layout_scope_path_outside_si_tree_returns_none_none(tmp_path: Path) -> None:
    outside = str(tmp_path / "pdf" / "mock_journal" / "2024" / "extra.pdf")
    assert cli_module._si_layout_scope(tmp_path, outside) == (None, None)


def test_si_layout_scope_empty_file_path_returns_none_none(tmp_path: Path) -> None:
    assert cli_module._si_layout_scope(tmp_path, "") == (None, None)


def test_fulltext_layout_scope_resolves_relative_path_under_data_dir(tmp_path: Path) -> None:
    """`fulltext.text_path` 相对形态（design/12 §5.4，不含 `data/` 前缀）能正确解析。"""
    relative = "fulltext/mock_journal/2024/paper123.txt"
    assert cli_module._fulltext_layout_scope(tmp_path, relative) == ("mock_journal", "2024")


def test_fulltext_layout_scope_path_outside_fulltext_tree_returns_none_none(
    tmp_path: Path,
) -> None:
    outside = str(tmp_path / "pdf" / "mock_journal" / "2024" / "extra.pdf")
    assert cli_module._fulltext_layout_scope(tmp_path, outside) == (None, None)


def test_fulltext_layout_scope_empty_file_path_returns_none_none(tmp_path: Path) -> None:
    assert cli_module._fulltext_layout_scope(tmp_path, "") == (None, None)


def test_asset_layout_scope_falls_back_to_si_when_not_pdf(tmp_path: Path) -> None:
    """`_asset_layout_scope` 先试 pdf 布局，未命中再试 si——两域路径互斥，依次尝试
    即可正确覆盖 missing_file/hash_mismatch 在 asset 域同时含 pdf/si 两种 kind 的场景。
    """
    si_path = "si/mock_journal/2024/paper123/supplement.zip"
    assert cli_module._asset_layout_scope(tmp_path, si_path) == ("mock_journal", "2024")


def test_asset_layout_scope_prefers_pdf_when_both_would_match_structurally(
    tmp_path: Path,
) -> None:
    pdf_path = "pdf/mock_journal/2024/paper123.pdf"
    assert cli_module._asset_layout_scope(tmp_path, pdf_path) == ("mock_journal", "2024")


def test_asset_layout_scope_outside_both_trees_returns_none_none(tmp_path: Path) -> None:
    outside = str(tmp_path / "fulltext" / "mock_journal" / "2024" / "paper123.txt")
    assert cli_module._asset_layout_scope(tmp_path, outside) == (None, None)


def test_pull_extract_cmd_venue_and_year_known_includes_extract_and_force() -> None:
    cmd = cli_module._pull_extract_cmd("mock_journal", "2024", "asset-1")
    assert "crawler pull mock_journal --year 2024 --extract --force" in cmd


def test_pull_extract_cmd_venue_only_prompts_for_scope_flag() -> None:
    cmd = cli_module._pull_extract_cmd("mock_journal", None, "asset-1")
    assert "crawler pull mock_journal --extract --force" in cmd
    assert "--volume" in cmd and "--year" in cmd and "--doi" in cmd


def test_pull_extract_cmd_neither_known_includes_asset_id() -> None:
    cmd = cli_module._pull_extract_cmd(None, None, "asset-42")
    assert "<venue_id>" in cmd
    assert "--extract --force" in cmd
    assert "asset-42" in cmd


def test_verify_fix_hint_prune_does_not_invent_command(tmp_path: Path) -> None:
    """fulltext 域 orphan_file（suggestion=`prune`）：不像 asset 域 `adopt` 那样谨慎——
    孤儿全文产物可安全直接删除（可从源 PDF 重新派生），措辞应体现这一点。
    """
    issue = VerifyIssue(
        kind="orphan_file",
        asset_id=None,
        file_path=str(tmp_path / "data" / "fulltext" / "orphan.txt"),
        suggestion="prune",
    )
    hint = cli_module._verify_fix_hint(issue, tmp_path / "data")
    assert "删除" in hint


def test_verify_fix_hint_re_extract_defect_suggests_pull_extract_force(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    text_path = data_dir / "fulltext" / "mock_journal" / "2024" / "paper123.txt"
    issue = VerifyIssue(
        kind="missing_file",
        asset_id="asset-1",
        file_path=str(text_path),
        suggestion="re-extract",
    )
    hint = cli_module._verify_fix_hint(issue, data_dir)
    assert "crawler pull mock_journal --year 2024 --extract --force" in hint


def test_verify_fix_hint_stale_fulltext_is_labeled_info_not_fix(tmp_path: Path) -> None:
    """`stale_fulltext` 的提示措辞须与"缺陷"区分开（design/12 §9.2：信息级，不计入
    退出码）——本用例锁定文案本身带有 info 标签而非 fix 标签。
    """
    data_dir = tmp_path / "data"
    text_path = data_dir / "fulltext" / "mock_journal" / "2024" / "paper123.txt"
    issue = VerifyIssue(
        kind="stale_fulltext",
        asset_id="asset-1",
        file_path=str(text_path),
        suggestion="re-extract",
        severity="info",
    )
    hint = cli_module._verify_fix_hint(issue, data_dir)
    assert "info:" in hint
    assert "fix:" not in hint
    assert "crawler pull mock_journal --year 2024 --extract --force" in hint


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


def test_list_folds_merged_duplicates_and_no_aggregate_expands(tmp_path: Path) -> None:
    """T13/AC-7.3 查询层聚合：人工 `dedupe decide … merge` 后 `list` 折叠重复行显示，
    `--no-aggregate` 原样展开；两种模式下 paper 行都还在库里（物理不删行）。"""
    home = _make_home(tmp_path)
    assert runner.invoke(app, ["list", VENUE, "--year", "2024", "--home", str(home)]).exit_code == 0

    db = Database(home / "catalog.sqlite")
    try:
        repo = Repo(db)
        issue_id = str(repo.list_issues(VENUE, year=2024)[0]["id"])
        papers = repo.list_papers(VENUE, issue_id=issue_id)
        a, b = str(papers[0]["id"]), str(papers[1]["id"])
        db.execute(
            "INSERT INTO paper_relation "
            "(from_paper, to_paper, kind, confidence, evidence_json, decided) "
            "VALUES (?,?,?,?,?,?)",
            (a, b, "candidate_duplicate", 0.5, '{"reason": "weak-signal-title-author"}', None),
        )
        repo.decide_candidate(a, b, "merge")
        total_rows = db.query("SELECT COUNT(*) AS n FROM paper")[0]["n"]
    finally:
        db.close()

    folded = runner.invoke(app, ["list", VENUE, "--year", "2024", "--home", str(home)])
    expanded = runner.invoke(
        app, ["list", VENUE, "--year", "2024", "--no-aggregate", "--home", str(home)]
    )

    assert folded.exit_code == 0, folded.output
    assert expanded.exit_code == 0, expanded.output
    assert "折叠 1 行" in folded.output
    assert "折叠" not in expanded.output
    assert folded.output.count("Mock Paper") == expanded.output.count("Mock Paper") - 1

    db = Database(home / "catalog.sqlite")
    try:
        assert db.query("SELECT COUNT(*) AS n FROM paper")[0]["n"] == total_rows  # 零删行
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
