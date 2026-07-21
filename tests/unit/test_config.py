"""config.py（§2.7 Config）单测：home 优先级、config.toml 读取、venues_dirs、ensure_dirs。"""

from pathlib import Path

import pytest

from paper_crawler.config import Config


def test_load_prefers_explicit_home_over_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PAPER_CRAWLER_HOME", str(tmp_path / "from_env"))
    explicit = tmp_path / "explicit"
    cfg = Config.load(home=explicit)
    assert cfg.home == explicit


def test_load_uses_env_when_no_explicit_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_home = tmp_path / "env_home"
    monkeypatch.setenv("PAPER_CRAWLER_HOME", str(env_home))
    cfg = Config.load()
    assert cfg.home == env_home


def test_load_defaults_to_dot_paper_crawler(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PAPER_CRAWLER_HOME", raising=False)
    cfg = Config.load()
    assert cfg.home == Path.home() / ".paper-crawler"


def test_derived_paths_hang_off_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PAPER_CRAWLER_HOME", raising=False)
    cfg = Config.load(home=tmp_path)
    assert cfg.data_dir == tmp_path / "data"
    assert cfg.db_path == tmp_path / "catalog.sqlite"
    assert cfg.log_dir == tmp_path / "logs"
    assert cfg.reports_dir == tmp_path / "reports"
    assert cfg.rate_scale == 1.0
    assert cfg.retry_scale == 1.0


def test_config_toml_overrides(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PAPER_CRAWLER_HOME", raising=False)
    home = tmp_path / "home"
    home.mkdir()
    external_data = tmp_path / "bigdisk" / "data"
    (home / "config.toml").write_text(
        "\n".join(
            [
                "[paths]",
                f'data_dir = "{external_data.as_posix()}"',
                'venues_dirs = ["curated", "extra"]',
                "[rate]",
                "scale = 0.25",
                "[retry]",
                "scale = 3.0",
            ]
        ),
        encoding="utf-8",
    )
    cfg = Config.load(home=home)
    assert cfg.data_dir == external_data  # 绝对路径原样
    # 相对 venues_dirs 挂在 home 下，保序。
    assert cfg.venues_dirs == (home / "curated", home / "extra")
    assert cfg.rate_scale == 0.25
    assert cfg.retry_scale == 3.0


def test_config_toml_present_but_partial(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # config.toml 存在但只给 [rate]，[paths] 缺省 → data_dir/venues_dirs 走默认。
    monkeypatch.delenv("PAPER_CRAWLER_HOME", raising=False)
    home = tmp_path / "home"
    home.mkdir()
    (home / "config.toml").write_text("[rate]\nscale = 0.5\n", encoding="utf-8")
    workdir = tmp_path / "work"
    workdir.mkdir()
    monkeypatch.chdir(workdir)

    cfg = Config.load(home=home)
    assert cfg.data_dir == home / "data"  # 未被 toml 覆盖
    assert cfg.venues_dirs == ()  # [paths].venues_dirs 缺省且无目录存在
    assert cfg.rate_scale == 0.5
    assert cfg.retry_scale == 1.0  # [retry] 缺省


def test_venues_dirs_default_detects_home_and_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("PAPER_CRAWLER_HOME", raising=False)
    home = tmp_path / "home"
    (home / "venues").mkdir(parents=True)
    workdir = tmp_path / "work"
    (workdir / "venues").mkdir(parents=True)
    monkeypatch.chdir(workdir)

    cfg = Config.load(home=home)
    # cwd/venues 在前，home/venues 在后（后者覆盖前者同 id）。
    assert cfg.venues_dirs == (workdir / "venues", home / "venues")


def test_venues_dirs_empty_when_none_exist(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PAPER_CRAWLER_HOME", raising=False)
    workdir = tmp_path / "work"
    workdir.mkdir()
    monkeypatch.chdir(workdir)
    cfg = Config.load(home=tmp_path / "home")
    assert cfg.venues_dirs == ()


def test_identity_email_read_from_config_toml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`[identity].email` 读入 Config.identity_email（D-014 UA mailto 来源）。"""
    monkeypatch.delenv("PAPER_CRAWLER_HOME", raising=False)
    home = tmp_path / "home"
    home.mkdir()
    (home / "config.toml").write_text(
        '[identity]\nemail = "researcher@example.edu"\n', encoding="utf-8"
    )
    cfg = Config.load(home=home)
    assert cfg.identity_email == "researcher@example.edu"


def test_identity_email_absent_is_none(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """无 config.toml → identity_email 缺省 None（UA 省略 mailto 段）。"""
    monkeypatch.delenv("PAPER_CRAWLER_HOME", raising=False)
    cfg = Config.load(home=tmp_path / "home")
    assert cfg.identity_email is None


def test_identity_email_blank_normalizes_to_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """空白 email 串归一为 None（等价未配置——不产生 `mailto:` 空值）。"""
    monkeypatch.delenv("PAPER_CRAWLER_HOME", raising=False)
    home = tmp_path / "home"
    home.mkdir()
    (home / "config.toml").write_text('[identity]\nemail = "   "\n', encoding="utf-8")
    cfg = Config.load(home=home)
    assert cfg.identity_email is None


def test_ensure_dirs_creates_tree(tmp_path: Path) -> None:
    cfg = Config.load(home=tmp_path)
    cfg.ensure_dirs()
    for sub in ("pdf", "si", "fulltext", "export", "tmp"):
        assert (cfg.data_dir / sub).is_dir()
    assert cfg.log_dir.is_dir()
    assert cfg.reports_dir.is_dir()
