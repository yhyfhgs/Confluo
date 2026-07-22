"""config.py（§2.7 Config）单测：home 优先级、config.toml 读取、venues_dirs、ensure_dirs、
分层加载链（D-025：env > 项目级 > home > 默认）、敏感键护栏、describe_config 来源层追踪。"""

from pathlib import Path

import pytest

from paper_crawler.config import Config, describe_config
from paper_crawler.errors import CrawlerError, ErrorClass

# 分层加载引入的全部 PAPER_CRAWLER_* env——每个用例前清空，防宿主环境/跨例泄漏干扰断言。
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
def _clear_pc_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """清空全部 PAPER_CRAWLER_* env（既有用例随后各自 setenv 需要的项，纯附加不破坏）。"""
    for var in _PC_ENV_VARS:
        monkeypatch.delenv(var, raising=False)


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


# -- OpenReview token 通道（openreview.md §3）--------------------------------------------


def test_openreview_token_read_from_config_toml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`[auth.openreview].token` 读入 Config.openreview_token（cookie 通道来源）。"""
    monkeypatch.delenv("PAPER_CRAWLER_HOME", raising=False)
    monkeypatch.delenv("PAPER_CRAWLER_OPENREVIEW_TOKEN", raising=False)
    home = tmp_path / "home"
    home.mkdir()
    (home / "config.toml").write_text('[auth.openreview]\ntoken = "tok-abc123"\n', encoding="utf-8")
    cfg = Config.load(home=home)
    assert cfg.openreview_token == "tok-abc123"


def test_openreview_token_absent_is_none(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """无 config.toml 且无 env → openreview_token 缺省 None（匿名）。"""
    monkeypatch.delenv("PAPER_CRAWLER_HOME", raising=False)
    monkeypatch.delenv("PAPER_CRAWLER_OPENREVIEW_TOKEN", raising=False)
    cfg = Config.load(home=tmp_path / "home")
    assert cfg.openreview_token is None


def test_openreview_token_blank_normalizes_to_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("PAPER_CRAWLER_HOME", raising=False)
    monkeypatch.delenv("PAPER_CRAWLER_OPENREVIEW_TOKEN", raising=False)
    home = tmp_path / "home"
    home.mkdir()
    (home / "config.toml").write_text('[auth.openreview]\ntoken = "   "\n', encoding="utf-8")
    cfg = Config.load(home=home)
    assert cfg.openreview_token is None


def test_openreview_token_env_var_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """环境变量 PAPER_CRAWLER_OPENREVIEW_TOKEN 提供 token（无 config.toml）。"""
    monkeypatch.delenv("PAPER_CRAWLER_HOME", raising=False)
    monkeypatch.setenv("PAPER_CRAWLER_OPENREVIEW_TOKEN", "env-tok-xyz")
    cfg = Config.load(home=tmp_path / "home")
    assert cfg.openreview_token == "env-tok-xyz"


def test_openreview_token_env_overrides_config_toml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """env 覆盖 config.toml（12-factor 惯例）。"""
    monkeypatch.delenv("PAPER_CRAWLER_HOME", raising=False)
    monkeypatch.setenv("PAPER_CRAWLER_OPENREVIEW_TOKEN", "env-wins")
    home = tmp_path / "home"
    home.mkdir()
    (home / "config.toml").write_text('[auth.openreview]\ntoken = "file-loses"\n', encoding="utf-8")
    cfg = Config.load(home=home)
    assert cfg.openreview_token == "env-wins"


def test_ensure_dirs_creates_tree(tmp_path: Path) -> None:
    cfg = Config.load(home=tmp_path)
    cfg.ensure_dirs()
    for sub in ("pdf", "si", "fulltext", "export", "tmp"):
        assert (cfg.data_dir / sub).is_dir()
    assert cfg.log_dir.is_dir()
    assert cfg.reports_dir.is_dir()


# -- Phase 4 新增凭证槽（elsevier/wiley）：Config-slot + env 覆盖（auth-framework §3.4）--------


def test_elsevier_wiley_slots_from_home_config(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    (home / "config.toml").write_text(
        "[auth.elsevier]\napi_key = 'els-k'\ninsttoken = 'inst-k'\n"
        "[auth.wiley]\ntoken = 'wy-tok'\n",
        encoding="utf-8",
    )
    cfg = Config.load(home=home)
    assert cfg.elsevier_api_key == "els-k"
    assert cfg.elsevier_insttoken == "inst-k"
    assert cfg.wiley_tdm_token == "wy-tok"


def test_elsevier_wiley_slots_default_none(tmp_path: Path) -> None:
    cfg = Config.load(home=tmp_path / "home")
    assert cfg.elsevier_api_key is None
    assert cfg.elsevier_insttoken is None
    assert cfg.wiley_tdm_token is None


def test_elsevier_wiley_slots_blank_normalizes_none(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    (home / "config.toml").write_text(
        "[auth.elsevier]\napi_key = '   '\n[auth.wiley]\ntoken = ''\n", encoding="utf-8"
    )
    cfg = Config.load(home=home)
    assert cfg.elsevier_api_key is None
    assert cfg.wiley_tdm_token is None


@pytest.mark.parametrize(
    ("env_var", "field"),
    [
        ("PAPER_CRAWLER_ELSEVIER_API_KEY", "elsevier_api_key"),
        ("PAPER_CRAWLER_ELSEVIER_INSTTOKEN", "elsevier_insttoken"),
        ("PAPER_CRAWLER_WILEY_TDM_TOKEN", "wiley_tdm_token"),
    ],
)
def test_new_slots_env_overrides_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, env_var: str, field: str
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    (home / "config.toml").write_text(
        "[auth.elsevier]\napi_key = 'file'\ninsttoken = 'file'\n[auth.wiley]\ntoken = 'file'\n",
        encoding="utf-8",
    )
    monkeypatch.setenv(env_var, "env-wins")
    cfg = Config.load(home=home)
    assert getattr(cfg, field) == "env-wins"


# -- 分层加载链（D-025 / 10-config-layout §3）：env > 项目级 > home > 默认 ---------------------


@pytest.fixture
def isolated_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """隔离 cwd 到一个无 paper-crawler.toml 的工作目录（项目级发现自 cwd 向上查）。"""
    workdir = tmp_path / "work"
    workdir.mkdir()
    monkeypatch.chdir(workdir)
    return workdir


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_project_layer_overrides_home_for_nonsensitive(isolated_cwd: Path, tmp_path: Path) -> None:
    """项目级非敏感键（路径/限速/email）覆盖 home（新增中间层，插在 env 与 home 之间）。"""
    home = tmp_path / "home"
    home.mkdir()
    _write(home / "config.toml", "[rate]\nscale = 0.5\n[identity]\nemail = 'home@x.edu'\n")
    _write(
        isolated_cwd / "paper-crawler.toml",
        "[rate]\nscale = 0.25\n[identity]\nemail = 'proj@x.edu'\n",
    )
    cfg = Config.load(home=home)
    assert cfg.rate_scale == 0.25  # project 覆盖 home
    assert cfg.identity_email == "proj@x.edu"


def test_env_overrides_project_and_home_for_credential(
    isolated_cwd: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """env 最高：openreview token（凭证只能来自 env/home，项目级放它会触护栏）——env 覆盖 home。"""
    home = tmp_path / "home"
    home.mkdir()
    _write(home / "config.toml", "[auth.openreview]\ntoken = 'home-tok'\n")
    monkeypatch.setenv("PAPER_CRAWLER_OPENREVIEW_TOKEN", "env-tok")
    cfg = Config.load(home=home)
    assert cfg.openreview_token == "env-tok"


def test_home_used_when_no_project_layer(isolated_cwd: Path, tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    _write(home / "config.toml", "[rate]\nscale = 0.5\n")
    cfg = Config.load(home=home)
    assert cfg.rate_scale == 0.5


def test_project_data_dir_and_venues_effective(isolated_cwd: Path, tmp_path: Path) -> None:
    """项目级路径键生效（data_dir 绝对原样、venues_dirs 相对挂 home）。"""
    ext = tmp_path / "ext" / "data"
    _write(
        isolated_cwd / "paper-crawler.toml",
        f"[paths]\ndata_dir = '{ext.as_posix()}'\nvenues_dirs = ['curated']\n",
    )
    cfg = Config.load(home=tmp_path / "home")
    assert cfg.data_dir == ext
    assert cfg.venues_dirs == (tmp_path / "home" / "curated",)


def test_project_layer_missing_silently_skipped(isolated_cwd: Path, tmp_path: Path) -> None:
    """无项目级文件 → 静默跳过（不报错，落 home/默认）。"""
    cfg = Config.load(home=tmp_path / "home")
    assert cfg.rate_scale == 1.0


# -- 敏感键防误提交护栏（§3.1）：项目级含敏感键 → CONFIG 拒启动 -------------------------------


@pytest.mark.parametrize(
    "toml_body",
    [
        "[auth.elsevier]\napi_key = 'sk-xxx'\n",
        "[auth.elsevier]\ninsttoken = 'x'\n",
        "[auth.wiley]\ntoken = 'uuid'\n",
        "[auth.openreview]\ntoken = 'x'\n",
        "password = 'hunter2'\n",
        "secret = 's'\n",
        "[svc]\napikey = 'x'\n",
        "[creds]\ncredential = 'x'\n",
        "authorization = 'Bearer x'\n",
        "session_id = 'abc'\n",
        "[db]\nprivate_key = 'x'\n",
    ],
)
def test_project_sensitive_key_rejects_startup(
    isolated_cwd: Path, tmp_path: Path, toml_body: str
) -> None:
    """项目级 ./paper-crawler.toml 敏感键形态 → CrawlerError(CONFIG) 拒启动（指引挪家目录/env）。"""
    _write(isolated_cwd / "paper-crawler.toml", toml_body)
    with pytest.raises(CrawlerError) as exc:
        Config.load(home=tmp_path / "home")
    assert exc.value.error_class is ErrorClass.CONFIG
    assert "敏感键" in str(exc.value)
    assert "家目录" in str(exc.value)  # 指引文案


def test_project_nonsensitive_keys_pass_including_email(isolated_cwd: Path, tmp_path: Path) -> None:
    """非敏感键放行——含 email（identity.email 属合法非凭证键，护栏刻意排除）与裸 key_ref。"""
    _write(
        isolated_cwd / "paper-crawler.toml",
        "[identity]\nemail = 'ok@x.edu'\n[rate]\nscale = 0.3\n[misc]\nkey_ref = 'entry-name'\n",
    )
    cfg = Config.load(home=tmp_path / "home")  # 不抛
    assert cfg.identity_email == "ok@x.edu"
    assert cfg.rate_scale == 0.3


def test_project_sensitive_key_reports_dotted_path(isolated_cwd: Path, tmp_path: Path) -> None:
    """护栏错误标出命中键的点号路径（嵌套表内）。"""
    _write(isolated_cwd / "paper-crawler.toml", "[auth.elsevier]\napi_key = 'x'\n")
    with pytest.raises(CrawlerError) as exc:
        Config.load(home=tmp_path / "home")
    assert "auth.elsevier.api_key" in str(exc.value)
    assert exc.value.detail == "auth.elsevier.api_key"


def test_home_config_credentials_not_guarded(isolated_cwd: Path, tmp_path: Path) -> None:
    """护栏仅约束项目级层——家目录 config.toml（仓库外）是凭证的设计归处，含 api_key 不拒启动。"""
    home = tmp_path / "home"
    home.mkdir()
    _write(home / "config.toml", "[auth.elsevier]\napi_key = 'els-key'\n")
    cfg = Config.load(home=home)  # 不抛
    assert cfg.elsevier_api_key == "els-key"


# -- 默认行为零变化自证（无项目级文件 + 无新 env → 与旧版逐字段一致）--------------------------


def test_default_behavior_unchanged_no_project_no_env(isolated_cwd: Path, tmp_path: Path) -> None:
    """纯附加自证：无项目级 ./paper-crawler.toml + 无新 env → 全字段与旧版默认逐字段一致。

    既有字段逐一钉死其默认值；新增三凭证字段默认 None（纯附加，旧版无此字段）。
    """
    home = tmp_path / "home"
    cfg = Config.load(home=home)
    # 既有字段（与旧版 load 逐字段一致）
    assert cfg.home == home
    assert cfg.data_dir == home / "data"
    assert cfg.db_path == home / "catalog.sqlite"
    assert cfg.log_dir == home / "logs"
    assert cfg.reports_dir == home / "reports"
    assert cfg.venues_dirs == ()  # isolated_cwd 无 venues/，home 无 venues/
    assert cfg.rate_scale == 1.0
    assert cfg.retry_scale == 1.0
    assert cfg.identity_email is None
    assert cfg.openreview_token is None
    assert cfg.openalex_api_key is None
    assert cfg.s2_api_key is None
    assert cfg.openalex_daily_budget_usd == 0.50
    # 新增字段：纯附加默认 None
    assert cfg.elsevier_api_key is None
    assert cfg.elsevier_insttoken is None
    assert cfg.wiley_tdm_token is None


# -- describe_config：分层解析中间态（每键 winning 来源层 + 敏感标记，供 config show）----------


def test_describe_config_tracks_winning_source_layers(
    isolated_cwd: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    _write(home / "config.toml", "[identity]\nemail = 'home@x.edu'\n[rate]\nscale = 0.5\n")
    _write(isolated_cwd / "paper-crawler.toml", "[rate]\nscale = 0.25\n")
    monkeypatch.setenv("PAPER_CRAWLER_ELSEVIER_API_KEY", "els")
    layers = {row.key: row for row in describe_config(home=home)}
    assert layers["home"].source == "explicit"
    assert layers["identity.email"].source == "home"
    assert layers["rate.scale"].source == "project"  # project 覆盖 home
    assert layers["auth.elsevier.api_key"].source == "env"
    assert layers["retry.scale"].source == "default"
    assert layers["auth.wiley.token"].value is None  # 未配置
    # 敏感标记
    assert layers["auth.elsevier.api_key"].sensitive is True
    assert layers["identity.email"].is_email is True
    assert layers["rate.scale"].sensitive is False


def test_describe_config_home_source_reflects_resolution(
    isolated_cwd: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PAPER_CRAWLER_HOME", str(tmp_path / "envhome"))
    rows = {row.key: row for row in describe_config()}
    assert rows["home"].source == "env"
    assert rows["home"].value == tmp_path / "envhome"


def test_describe_config_guardrail_propagates(isolated_cwd: Path, tmp_path: Path) -> None:
    """describe_config 与 Config.load 共享护栏——项目级敏感键同样拒启动。"""
    _write(isolated_cwd / "paper-crawler.toml", "[auth.wiley]\ntoken = 'x'\n")
    with pytest.raises(CrawlerError):
        describe_config(home=tmp_path / "home")


def test_guardrail_scans_array_of_tables(isolated_cwd: Path, tmp_path: Path) -> None:
    """护栏递归 TOML array-of-tables（`[[...]]` → list）——嵌套在数组元素里的敏感键也拦。"""
    _write(isolated_cwd / "paper-crawler.toml", "[[servers]]\ntoken = 'x'\n")
    with pytest.raises(CrawlerError) as exc:
        Config.load(home=tmp_path / "home")
    assert exc.value.error_class is ErrorClass.CONFIG
    assert "servers" in str(exc.value) and "token" in str(exc.value)


@pytest.mark.parametrize("bad_scale", ["true", "[1, 2]"])
def test_scale_non_number_raises_typeerror(
    isolated_cwd: Path, tmp_path: Path, bad_scale: str
) -> None:
    """畸形 scale（bool / 非数值）→ 响亮 TypeError（不静默当 1.0），守卫 _to_float。"""
    home = tmp_path / "home"
    home.mkdir()
    _write(home / "config.toml", f"[rate]\nscale = {bad_scale}\n")
    with pytest.raises(TypeError):
        Config.load(home=home)
