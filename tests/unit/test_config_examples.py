"""config/ 规范文件夹守卫（D-025 / 10-config-layout §2）：样例文件存在、可解析、
**无真实凭证形态**（AC-0.3/AC-0.4：CI 断言 config/** 无凭证），且模板可被 Config.load 消费。
"""

from __future__ import annotations

import re
import shutil
import tomllib
from pathlib import Path

import pytest

from paper_crawler.config import Config

_CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"

# 凭证形态 tripwire（AC-0.4）：一个**整体**为 ≥16 位纯字母数字的引号包裹值——真实
# API key/hex token 的典型形态。占位（空串/含 @._-/空格的 email·URL·ref 名）均不命中。
_SECRET_SHAPE_RE = re.compile(r"""['"][A-Za-z0-9]{16,}['"]""")


def test_config_dir_has_required_files() -> None:
    for name in ("README.md", "config.example.toml", "profiles.example.toml"):
        assert (_CONFIG_DIR / name).is_file(), f"config/{name} 缺失"


@pytest.mark.parametrize("name", ["config.example.toml", "profiles.example.toml"])
def test_example_toml_parses(name: str) -> None:
    with (_CONFIG_DIR / name).open("rb") as handle:
        tomllib.load(handle)


@pytest.mark.parametrize("name", ["config.example.toml", "profiles.example.toml", "README.md"])
def test_config_examples_have_no_credential_shape(name: str) -> None:
    """AC-0.4：config/** 无 ≥16 位纯字母数字引号值（真实凭证形态）——样例只放占位。"""
    text = (_CONFIG_DIR / name).read_text(encoding="utf-8")
    hits = _SECRET_SHAPE_RE.findall(text)
    assert hits == [], f"config/{name} 疑似含凭证形态值: {hits}"


def test_config_example_credential_slots_are_empty() -> None:
    """config.example.toml 全部 [auth.*] 简单密钥槽为空串（占位；用户填真实值前 = 未配置）。"""
    with (_CONFIG_DIR / "config.example.toml").open("rb") as handle:
        doc = tomllib.load(handle)
    auth = doc.get("auth", {})
    assert auth.get("openreview", {}).get("token", "") == ""
    assert auth.get("openalex", {}).get("api_key", "") == ""
    assert auth.get("s2", {}).get("api_key", "") == ""
    assert auth.get("elsevier", {}).get("api_key", "") == ""
    assert auth.get("elsevier", {}).get("insttoken", "") == ""
    assert auth.get("wiley", {}).get("token", "") == ""


def test_config_example_loads_as_home_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """模板复制到 config-home 后可被 Config.load 消费：空凭证槽归一 None，非凭证键生效。"""
    for var in (
        "PAPER_CRAWLER_HOME",
        "PAPER_CRAWLER_OPENREVIEW_TOKEN",
        "PAPER_CRAWLER_ELSEVIER_API_KEY",
        "PAPER_CRAWLER_ELSEVIER_INSTTOKEN",
        "PAPER_CRAWLER_WILEY_TDM_TOKEN",
        "PAPER_CRAWLER_S2_API_KEY",
        "PAPER_CRAWLER_OPENALEX_API_KEY",
    ):
        monkeypatch.delenv(var, raising=False)
    workdir = tmp_path / "work"  # 隔离 cwd（无项目级 paper-crawler.toml）
    workdir.mkdir()
    monkeypatch.chdir(workdir)
    home = tmp_path / "home"
    home.mkdir()
    shutil.copy(_CONFIG_DIR / "config.example.toml", home / "config.toml")

    cfg = Config.load(home=home)
    assert cfg.identity_email == "you@example.edu"  # 非凭证键生效
    assert cfg.rate_scale == 1.0
    assert cfg.openalex_daily_budget_usd == 0.50
    # 空凭证槽 → None（未配置）
    assert cfg.openreview_token is None
    assert cfg.elsevier_api_key is None
    assert cfg.elsevier_insttoken is None
    assert cfg.wiley_tdm_token is None
    assert cfg.s2_api_key is None
    assert cfg.openalex_api_key is None
