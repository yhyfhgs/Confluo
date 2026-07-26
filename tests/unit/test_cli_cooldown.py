"""`crawler cooldown status|clear` CLI 单测（E-2；检查单 #7 / D-030 裁决点④）。

薄接线层测试：纯逻辑已在 `tests/unit/test_pipeline_cooldown.py` 覆盖，本文件只测
CLI 参数解析/呈现/退出码（同 `test_auth_cli.py`/`test_cli_grab.py` 的 CliRunner
进程内驱动手法，零真实网络/DB/registry）。

`status`/`clear` 均为"轻装配"命令（同 `auth/cli.py` 的 `_build_manager` 先例）：
只 `Config.load(home)`，不构造 `PipelineRunner`/DB/`VenueRegistry`——`home` 目录
无需 `venues/`、无需 `config.toml`，纯 `state/cooldown/*.json` 文件读写。

**独立审查修复覆盖**：P0 路径穿越（`clear <KEY>` 的 KEY 来自用户输入，`../` 注入/
绝对路径/含 `/` 键三向量 + 端到端"home 外文件不被删"证据）；P1 `status` 对损坏
文件的响亮 WARNING（不得静默呈现成"无冷却记录"）。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner

from paper_crawler.cli import app
from paper_crawler.pipeline import cooldown

runner = CliRunner()

_PC_ENV_VARS = ("PAPER_CRAWLER_HOME",)


@pytest.fixture(autouse=True)
def _isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """cwd/env 绝缘（同 `test_auth_cli.py` 先例）——绝不触真实 config-home（D-032 红线）。"""
    for var in _PC_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    workdir = tmp_path / "cwd"
    workdir.mkdir()
    monkeypatch.chdir(workdir)


@pytest.fixture
def home(tmp_path: Path) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    return home


def all_output(result: object) -> str:
    output = str(getattr(result, "output", ""))
    try:
        stderr = str(getattr(result, "stderr", ""))
    except ValueError:
        stderr = ""
    return output + stderr


def _line_with(text: str, key: str) -> str:
    """输出中以 `key` 开头（表格首列）的那一行；找不到则断言失败，报出全文便于调试。"""
    for line in text.splitlines():
        if line.strip().startswith(key):
            return line
    raise AssertionError(f"未找到以 {key!r} 开头的行，全文：\n{text}")


# ---------------------------------------------------------------------------
# cooldown status
# ---------------------------------------------------------------------------


def test_status_no_records_shows_message_and_exit_zero(home: Path) -> None:
    result = runner.invoke(app, ["cooldown", "status", "--home", str(home)])
    assert result.exit_code == 0, all_output(result)
    assert "无冷却记录" in result.output
    assert str(home / "state" / "cooldown") in result.output


def test_status_lists_active_and_expired_entries(home: Path) -> None:
    now = datetime.now(UTC)
    cooldown.write(home, "pubs.mock.local", now + timedelta(hours=12))  # 域级新键，生效中
    cooldown.write(home, "mock_platform", now - timedelta(hours=1))  # adapter_id 旧键，已过期

    result = runner.invoke(app, ["cooldown", "status", "--home", str(home)])

    assert result.exit_code == 0, all_output(result)
    assert "key" in result.output and "until" in result.output  # 表头
    active_line = _line_with(result.output, "pubs.mock.local")
    assert "已过期" not in active_line
    expired_line = _line_with(result.output, "mock_platform")
    assert "已过期" in expired_line


def test_status_lists_both_domain_and_legacy_adapter_id_keys(home: Path) -> None:
    """E-1"两形态键"如实并列（本卡不做旧键迁移，已裁决歧义）。"""
    now = datetime.now(UTC)
    cooldown.write(home, "pubs.aeaweb.org", now + timedelta(hours=1))
    cooldown.write(home, "aea", now + timedelta(hours=1))

    result = runner.invoke(app, ["cooldown", "status", "--home", str(home)])

    assert result.exit_code == 0, all_output(result)
    assert "pubs.aeaweb.org" in result.output
    assert _line_with(result.output, "aea")  # 旧键单独一行存在


def test_status_does_not_require_venues_or_config(tmp_path: Path) -> None:
    """轻装配契约：`home` 目录空无一物（无 venues/、无 config.toml）也能跑（无 DB/registry）。"""
    bare_home = tmp_path / "bare"
    bare_home.mkdir()
    result = runner.invoke(app, ["cooldown", "status", "--home", str(bare_home)])
    assert result.exit_code == 0, all_output(result)


def test_status_reports_corrupt_files_as_warning_instead_of_silent_empty(home: Path) -> None:
    """独立审查 P1 复现：目录只含损坏文件时，`status` 此前静默呈现"（无冷却记录）"，
    跟真空目录一模一样——须逐个响亮 WARNING 列出文件名+原因，不得吞没。"""
    broken_one = cooldown.cooldown_path(home, "broken_one")
    broken_one.parent.mkdir(parents=True, exist_ok=True)
    broken_one.write_text("not json", encoding="utf-8")
    cooldown.cooldown_path(home, "broken_two").write_text("{}", encoding="utf-8")

    result = runner.invoke(app, ["cooldown", "status", "--home", str(home)])

    assert result.exit_code == 0, all_output(result)  # 诊断信息不是失败
    output = all_output(result)
    assert "警告" in output
    assert "broken_one.json" in output
    assert "broken_two.json" in output


# ---------------------------------------------------------------------------
# cooldown clear
# ---------------------------------------------------------------------------


def test_clear_specific_key_removes_file(home: Path) -> None:
    cooldown.write(home, "pubs.mock.local", datetime.now(UTC))
    cooldown.write(home, "keep_me", datetime.now(UTC))

    result = runner.invoke(app, ["cooldown", "clear", "pubs.mock.local", "--home", str(home)])

    assert result.exit_code == 0, all_output(result)
    assert "已清除 1 条冷却记录" in result.output
    assert not cooldown.cooldown_path(home, "pubs.mock.local").exists()
    assert cooldown.cooldown_path(home, "keep_me").is_file()


def test_clear_missing_key_is_idempotent_zero_count(home: Path) -> None:
    result = runner.invoke(app, ["cooldown", "clear", "no_such_key", "--home", str(home)])
    assert result.exit_code == 0, all_output(result)
    assert "已清除 0 条冷却记录" in result.output


def test_clear_all_removes_every_entry(home: Path) -> None:
    now = datetime.now(UTC)
    cooldown.write(home, "a", now)
    cooldown.write(home, "b", now)
    cooldown.write(home, "c", now)

    result = runner.invoke(app, ["cooldown", "clear", "--all", "--home", str(home)])

    assert result.exit_code == 0, all_output(result)
    assert "已清除 3 条冷却记录" in result.output
    assert cooldown.list_entries(home, now=now) == []


def test_clear_without_key_or_all_exits_2(home: Path) -> None:
    result = runner.invoke(app, ["cooldown", "clear", "--home", str(home)])
    assert result.exit_code == 2, all_output(result)
    assert "必须指定" in all_output(result)


def test_clear_with_key_and_all_together_exits_2(home: Path) -> None:
    result = runner.invoke(app, ["cooldown", "clear", "some_key", "--all", "--home", str(home)])
    assert result.exit_code == 2, all_output(result)
    assert "不可同时指定" in all_output(result)


# ---------------------------------------------------------------------------
# 路径穿越防护（独立审查 P0 修复）：`crawler cooldown clear <KEY>` 的 KEY 来自用户
# 输入，是本漏洞真正的攻击面（写侧键来自受控 URL hostname，见 pipeline/cooldown.py
# 模块 docstring）。曾实测 `clear "../../../victim/important"` 真删 home 外文件。
# ---------------------------------------------------------------------------


def test_clear_parent_traversal_key_does_not_delete_file_outside_home(
    home: Path, tmp_path: Path
) -> None:
    """端到端复现 + 验证已堵死：home 外的 victim 文件在攻击尝试后毫发无损。"""
    victim = tmp_path / "victim" / "important.json"
    victim.parent.mkdir(parents=True)
    victim.write_text('{"sentinel": "do-not-delete"}', encoding="utf-8")

    result = runner.invoke(
        app, ["cooldown", "clear", "../../../victim/important", "--home", str(home)]
    )

    assert result.exit_code == 2, all_output(result)
    assert "错误" in all_output(result)
    assert victim.is_file()
    assert victim.read_text(encoding="utf-8") == '{"sentinel": "do-not-delete"}'


def test_clear_absolute_path_key_rejected(home: Path) -> None:
    result = runner.invoke(app, ["cooldown", "clear", "/etc/passwd", "--home", str(home)])
    assert result.exit_code == 2, all_output(result)


def test_clear_key_containing_slash_rejected(home: Path) -> None:
    """含 `/` 即拒——不必配 `..` 也不许静默在 state/cooldown/ 下建子目录。"""
    result = runner.invoke(app, ["cooldown", "clear", "sub/dir", "--home", str(home)])
    assert result.exit_code == 2, all_output(result)
    assert not (cooldown.cooldown_dir(home) / "sub").exists()


# ---------------------------------------------------------------------------
# 子命令组注册（cli.py add_typer 接线）
# ---------------------------------------------------------------------------


def test_cooldown_group_registered_on_top_level_app() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0, all_output(result)
    assert "cooldown" in result.output
