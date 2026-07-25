"""`crawler config show` CLI 集成测试（10-config-layout §4：生效配置 + 来源层，脱敏自查）。

config show 不走 `_env`（无需 DB/日志）——直接 `describe_config(home)` 分层解析 + 渲染。
用 `monkeypatch.chdir` 隔离 cwd（项目级 `paper-crawler.toml` 自 cwd 向上查），并清空
PAPER_CRAWLER_* env 防宿主环境干扰。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from paper_crawler.cli import app

runner = CliRunner()

_PC_ENV_VARS = (
    "PAPER_CRAWLER_HOME",
    "PAPER_CRAWLER_OPENREVIEW_TOKEN",
    "PAPER_CRAWLER_OPENALEX_API_KEY",
    "PAPER_CRAWLER_S2_API_KEY",
    "PAPER_CRAWLER_ELSEVIER_API_KEY",
    "PAPER_CRAWLER_ELSEVIER_INSTTOKEN",
    "PAPER_CRAWLER_WILEY_TDM_TOKEN",
)


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in _PC_ENV_VARS:
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    workdir = tmp_path / "work"
    workdir.mkdir()
    monkeypatch.chdir(workdir)
    return workdir


def test_config_show_masks_credentials_and_email(cwd: Path, tmp_path: Path) -> None:
    """敏感槽整值 `***`，email 部分脱敏——绝不回显凭证/完整地址明文。"""
    home = tmp_path / "home"
    home.mkdir()
    (home / "config.toml").write_text(
        "[identity]\nemail = 'yhyfhgs@gmail.com'\n"
        "[auth.elsevier]\napi_key = 'sk-SUPERSECRET-123456'\n",
        encoding="utf-8",
    )
    result = runner.invoke(app, ["config", "show", "--home", str(home)])
    assert result.exit_code == 0, result.output
    assert "SUPERSECRET" not in result.output  # 凭证明文绝不回显
    assert "auth.elsevier.api_key" in result.output
    assert "***" in result.output
    assert "y***@gmail.com" in result.output  # email 部分脱敏（首字符 + *** + 域）
    assert "yhyfhgs@gmail.com" not in result.output


def test_config_show_reports_source_layers(cwd: Path, tmp_path: Path) -> None:
    """每键标注 winning 来源层（home/project/default）。"""
    home = tmp_path / "home"
    home.mkdir()
    (home / "config.toml").write_text("[rate]\nscale = 0.5\n", encoding="utf-8")
    (cwd / "paper-crawler.toml").write_text("[retry]\nscale = 0.9\n", encoding="utf-8")
    result = runner.invoke(app, ["config", "show", "--home", str(home)])
    assert result.exit_code == 0, result.output
    lines = result.output.splitlines()
    rate_line = next(ln for ln in lines if ln.startswith("rate.scale"))
    retry_line = next(ln for ln in lines if ln.startswith("retry.scale"))
    budget_line = next(ln for ln in lines if ln.startswith("openalex.daily_budget_usd"))
    assert "0.5" in rate_line and "home" in rate_line
    assert "0.9" in retry_line and "project" in retry_line  # 项目级层生效
    assert "default" in budget_line  # 未配置的数值键落默认


def test_config_show_env_source_masked(
    cwd: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PAPER_CRAWLER_ELSEVIER_API_KEY", "envsecretvalue123")
    result = runner.invoke(app, ["config", "show", "--home", str(tmp_path / "home")])
    assert result.exit_code == 0, result.output
    els_line = next(
        ln for ln in result.output.splitlines() if ln.startswith("auth.elsevier.api_key")
    )
    assert "***" in els_line
    assert "env" in els_line
    assert "envsecretvalue123" not in result.output  # env 凭证明文不回显


def test_config_show_unset_slots(cwd: Path, tmp_path: Path) -> None:
    """未配置的凭证槽显示 `(unset)`，来源列 `-`。"""
    result = runner.invoke(app, ["config", "show", "--home", str(tmp_path / "home")])
    assert result.exit_code == 0, result.output
    wiley_line = next(ln for ln in result.output.splitlines() if ln.startswith("auth.wiley.token"))
    assert "(unset)" in wiley_line
    # 未配置 → 来源列渲染为 "-"（非 default/home/env）
    assert wiley_line.rstrip().endswith("-")


def test_config_show_readonly_exit_zero(cwd: Path, tmp_path: Path) -> None:
    result = runner.invoke(app, ["config", "show", "--home", str(tmp_path / "home")])
    assert result.exit_code == 0
    assert "key" in result.output and "value" in result.output and "source" in result.output


def test_config_show_project_sensitive_key_rejects_exit_2(cwd: Path, tmp_path: Path) -> None:
    """项目级敏感键 → 分层护栏 CONFIG 拒启动，config show 报错退出 2。"""
    (cwd / "paper-crawler.toml").write_text("[auth.wiley]\ntoken = 'x'\n", encoding="utf-8")
    result = runner.invoke(app, ["config", "show", "--home", str(tmp_path / "home")])
    assert result.exit_code == 2
    assert "敏感键" in result.output


def test_config_show_malformed_home_toml_exit_2(cwd: Path, tmp_path: Path) -> None:
    """家目录 config.toml 语法损坏 → `CrawlerError(CONFIG)` → 退出码 2（无裸 traceback）。

    2026-07-24 审计 P1 [O1]：畸形 TOML 此前逃逸出 CONFIG 错误分类契约（裸
    `tomllib.TOMLDecodeError` 而非退出码 2）；`config.py::_load_toml` 归类修正后回归。
    """
    home = tmp_path / "home"
    home.mkdir()
    (home / "config.toml").write_text("[rate\nscale = 0.5\n", encoding="utf-8")  # 缺右中括号
    result = runner.invoke(app, ["config", "show", "--home", str(home)])
    assert result.exit_code == 2, result.output
    assert "Traceback" not in result.output
    assert str(home / "config.toml") in result.output


def test_config_show_home_row_present(cwd: Path, tmp_path: Path) -> None:
    """首行呈现 config-home 及其来源（explicit，因 --home 显式给出）。"""
    result = runner.invoke(app, ["config", "show", "--home", str(tmp_path / "home")])
    assert result.exit_code == 0
    home_line = next(ln for ln in result.output.splitlines() if ln.startswith("home"))
    assert "explicit" in home_line
