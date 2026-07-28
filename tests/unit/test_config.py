"""config.py（§2.7 Config）单测：home 优先级、config.toml 读取、venues_dirs、ensure_dirs、
分层加载链（D-025：env > 项目级 > home > 默认）、敏感键护栏、describe_config 来源层追踪。"""

from pathlib import Path

import pytest

from paper_crawler.config import Config, _find_project_config, _to_int, describe_config
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
    "PAPER_CRAWLER_AUTH_DAILY_CAP",
    "PAPER_CRAWLER_AUTH_HEALTH_INTERVAL",
    "PAPER_CRAWLER_AUTH_HEALTH_MAX_AGE_S",
    "PAPER_CRAWLER_AUTH_WORK_HOURS",
    "PAPER_CRAWLER_OA_FALLBACK_RATE_RPM",
    "PAPER_CRAWLER_BROWSER_FETCH_ENABLED",
    "PAPER_CRAWLER_BROWSER_DAILY_CAP",
    "PAPER_CRAWLER_BROWSER_RATE_RPM",
    "PAPER_CRAWLER_BROWSER_JITTER_S",
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
    """项目级 ./paper-crawler.toml 敏感键形态 → CrawlerError(CONFIG) 拒启动（挪 config-home）。"""
    _write(isolated_cwd / "paper-crawler.toml", toml_body)
    with pytest.raises(CrawlerError) as exc:
        Config.load(home=tmp_path / "home")
    assert exc.value.error_class is ErrorClass.CONFIG
    assert "敏感键" in str(exc.value)
    assert "config-home" in str(exc.value)  # 指引文案（D-032 措辞）


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


# -- 畸形 TOML 语法错误 → CONFIG 类错误（2026-07-24 审计 P1 [O1]）----------------------------
# 家目录/项目级 config.toml 语法错误此前抛裸 `tomllib.TOMLDecodeError` 逃逸出 errors.py
# 「配置错误归 CONFIG 类」契约（与同函数的敏感键护栏处理不一致）；`_load_toml` 现统一包裹。


def test_home_config_malformed_toml_raises_config_error(tmp_path: Path) -> None:
    """家目录 config.toml 语法错误（缺右中括号）→ CrawlerError(CONFIG)，不逃逸裸异常。"""
    home = tmp_path / "home"
    home.mkdir()
    (home / "config.toml").write_text("[rate\nscale = 0.5\n", encoding="utf-8")
    with pytest.raises(CrawlerError) as exc:
        Config.load(home=home)
    assert exc.value.error_class is ErrorClass.CONFIG
    assert str(home / "config.toml") in str(exc.value)


def test_project_config_malformed_toml_raises_config_error(
    isolated_cwd: Path, tmp_path: Path
) -> None:
    """项目级 ./paper-crawler.toml 语法错误 → 同归 CrawlerError(CONFIG)（同一 `_load_toml`）。"""
    _write(isolated_cwd / "paper-crawler.toml", "key = = bad\n")
    with pytest.raises(CrawlerError) as exc:
        Config.load(home=tmp_path / "home")
    assert exc.value.error_class is ErrorClass.CONFIG
    assert str(isolated_cwd / "paper-crawler.toml") in str(exc.value)


def test_describe_config_malformed_home_toml_raises_config_error(tmp_path: Path) -> None:
    """`describe_config` 与 `Config.load` 共享 `_load_toml`——畸形 TOML 同样归 CONFIG。"""
    home = tmp_path / "home"
    home.mkdir()
    (home / "config.toml").write_text("not = [valid\n", encoding="utf-8")
    with pytest.raises(CrawlerError) as exc:
        describe_config(home=home)
    assert exc.value.error_class is ErrorClass.CONFIG


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


# -- rate.scale / retry.scale 边界护栏（R1b P1-1：scale≤0 → RateLimiter.acquire 返 inf ---------
# 挂死；scale>1 全局放宽且 effective_rpm() 观测面不反映真值）。合法域 rate.scale∈(0,1]，
# retry.scale 只需 >0（放大退避无合规问题，故无上界）。


@pytest.mark.parametrize("bad_scale", ["0", "0.0", "-1", "-0.01"])
def test_rate_scale_non_positive_rejected(tmp_path: Path, bad_scale: str) -> None:
    home = tmp_path / "home"
    home.mkdir()
    (home / "config.toml").write_text(f"[rate]\nscale = {bad_scale}\n", encoding="utf-8")
    with pytest.raises(CrawlerError) as excinfo:
        Config.load(home=home)
    assert excinfo.value.error_class is ErrorClass.CONFIG
    assert excinfo.value.detail == "rate.scale"


@pytest.mark.parametrize("bad_scale", ["1.01", "1.5", "2", "100"])
def test_rate_scale_above_one_rejected(tmp_path: Path, bad_scale: str) -> None:
    """scale 只用于收紧：>1 会让实际 rpm 超过 venue/adapter 声明的上限，响亮拒绝。"""
    home = tmp_path / "home"
    home.mkdir()
    (home / "config.toml").write_text(f"[rate]\nscale = {bad_scale}\n", encoding="utf-8")
    with pytest.raises(CrawlerError) as excinfo:
        Config.load(home=home)
    assert excinfo.value.error_class is ErrorClass.CONFIG
    assert excinfo.value.detail == "rate.scale"
    assert "仅用于收紧" in str(excinfo.value)


def test_rate_scale_upper_bound_one_is_inclusive_and_allowed(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    (home / "config.toml").write_text("[rate]\nscale = 1.0\n", encoding="utf-8")
    assert Config.load(home=home).rate_scale == 1.0


@pytest.mark.parametrize("bad_scale", ["0", "-1", "-0.01"])
def test_retry_scale_non_positive_rejected(tmp_path: Path, bad_scale: str) -> None:
    home = tmp_path / "home"
    home.mkdir()
    (home / "config.toml").write_text(f"[retry]\nscale = {bad_scale}\n", encoding="utf-8")
    with pytest.raises(CrawlerError) as excinfo:
        Config.load(home=home)
    assert excinfo.value.error_class is ErrorClass.CONFIG
    assert excinfo.value.detail == "retry.scale"


def test_retry_scale_above_one_has_no_upper_bound(tmp_path: Path) -> None:
    """retry.scale 放大退避秒数无合规问题——刻意不设上界，同 test_config_toml_overrides
    里 scale=3.0 的既有覆盖互补（这里钉一个更大的值，证明"无上界"是有意为之而非漏校验）。"""
    home = tmp_path / "home"
    home.mkdir()
    (home / "config.toml").write_text("[retry]\nscale = 100.0\n", encoding="utf-8")
    assert Config.load(home=home).retry_scale == 100.0


# -- 项目级发现上界（NIT-1）：以 .git 仓库根为最后一层，不越界命中祖先 stray 文件 ------------


def test_find_project_config_stops_at_git_root(tmp_path: Path) -> None:
    """仓库根之上的祖先目录有 paper-crawler.toml → **不被命中**（.git 根即上界）。"""
    ancestor = tmp_path / "ancestor"
    repo = ancestor / "repo"
    sub = repo / "pkg" / "deep"
    sub.mkdir(parents=True)
    # 祖先目录（仓库根之上）的 stray 同名文件——修复前会被任意子目录调用命中。
    (ancestor / "paper-crawler.toml").write_text("[rate]\nscale = 0.1\n", encoding="utf-8")
    (repo / ".git").mkdir()  # 仓库根标记（目录形态）
    assert _find_project_config(sub) is None


def test_find_project_config_found_at_git_root_level_worktree(tmp_path: Path) -> None:
    """仓库根本层（`.git` 为**文件**，worktree 形态）的 paper-crawler.toml 仍被找到。"""
    repo = tmp_path / "repo"
    sub = repo / "pkg"
    sub.mkdir(parents=True)
    # worktree 形态：`.git` 是指针文件而非目录。
    (repo / ".git").write_text("gitdir: /elsewhere/worktrees/x\n", encoding="utf-8")
    proj = repo / "paper-crawler.toml"
    proj.write_text("[rate]\nscale = 0.2\n", encoding="utf-8")
    assert _find_project_config(sub) == proj


# ---------------------------------------------------------------------------
# auth-framework §8 pipeline knobs（daily_cap/health_interval/health_max_age_s/
# work_hours/oa_fallback_rate_rpm/active_profile）：默认 / home / env / describe。
# ---------------------------------------------------------------------------


def test_auth_knobs_default_when_unset(tmp_path: Path) -> None:
    """无 config.toml + 无 env → 默认值（与 runner/stages getattr 兜底逐一相同）。"""
    cfg = Config.load(home=tmp_path)
    assert cfg.auth_daily_cap == 200
    assert cfg.auth_health_interval == 20
    assert cfg.auth_health_max_age_s == 900
    assert cfg.auth_work_hours == "8-23"
    assert cfg.oa_fallback_rate_rpm == 30
    assert cfg.auth_active_profile is None


def test_auth_knobs_from_home_config_toml(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    (home / "config.toml").write_text(
        "[auth]\n"
        "daily_cap = 50\n"
        "health_interval = 5\n"
        "health_max_age_s = 120\n"
        'work_hours = "9-18"\n'
        "[oa_fallback]\n"
        "rate_rpm = 12\n",
        encoding="utf-8",
    )
    cfg = Config.load(home=home)
    assert cfg.auth_daily_cap == 50
    assert cfg.auth_health_interval == 5
    assert cfg.auth_health_max_age_s == 120
    assert cfg.auth_work_hours == "9-18"
    assert cfg.oa_fallback_rate_rpm == 12


def test_auth_knobs_env_overrides_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "home"
    home.mkdir()
    (home / "config.toml").write_text("[auth]\ndaily_cap = 50\n", encoding="utf-8")
    monkeypatch.setenv("PAPER_CRAWLER_AUTH_DAILY_CAP", "7")
    monkeypatch.setenv("PAPER_CRAWLER_OA_FALLBACK_RATE_RPM", "3")
    cfg = Config.load(home=home)
    assert cfg.auth_daily_cap == 7  # env > home
    assert cfg.oa_fallback_rate_rpm == 3


@pytest.mark.parametrize("bad_rpm", ["0", "-5"])
def test_oa_fallback_rate_rpm_must_be_positive(tmp_path: Path, bad_rpm: str) -> None:
    """rpm ≤ 0 → 拒启动：与 browserfetch.rate_rpm（config.py:398 min_value=1）同构——桶
    补充速率为 0 会让 `acquire` 返回 `inf`（无限等待），畸形配置不能静默变成死锁（R1b P1-2）。
    """
    home = tmp_path / "home"
    home.mkdir()
    (home / "config.toml").write_text(f"[oa_fallback]\nrate_rpm = {bad_rpm}\n", encoding="utf-8")
    with pytest.raises(CrawlerError) as excinfo:
        Config.load(home=home)
    assert excinfo.value.error_class is ErrorClass.CONFIG
    assert excinfo.value.detail == "oa_fallback.rate_rpm"


def test_oa_fallback_rate_rpm_env_is_validated_too(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PAPER_CRAWLER_OA_FALLBACK_RATE_RPM", "0")
    with pytest.raises(CrawlerError) as excinfo:
        Config.load(home=tmp_path)
    assert excinfo.value.error_class is ErrorClass.CONFIG


def test_active_profile_mapping_from_toml(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    (home / "config.toml").write_text(
        '[auth]\nactive_profile = { oup_silverchair = "oup@campus", elsevier_sd = "elsevier" }\n',
        encoding="utf-8",
    )
    cfg = Config.load(home=home)
    assert cfg.auth_active_profile == {"oup_silverchair": "oup@campus", "elsevier_sd": "elsevier"}


def test_auth_knobs_in_describe_config_with_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """config show 来源层追踪含这 6 项（env/home/default）。"""
    home = tmp_path / "home"
    home.mkdir()
    (home / "config.toml").write_text("[auth]\nhealth_interval = 9\n", encoding="utf-8")
    monkeypatch.setenv("PAPER_CRAWLER_AUTH_DAILY_CAP", "7")
    rows = {r.key: r for r in describe_config(home)}
    assert rows["auth.daily_cap"].value == 7 and rows["auth.daily_cap"].source == "env"
    assert rows["auth.health_interval"].value == 9
    assert rows["auth.health_interval"].source == "home"
    assert rows["auth.work_hours"].value == "8-23" and rows["auth.work_hours"].source == "default"
    assert rows["oa_fallback.rate_rpm"].value == 30
    assert "auth.active_profile" in rows  # 映射项也纳入追踪
    assert not rows["auth.daily_cap"].sensitive  # 均非敏感（config show 不脱敏，护栏不拦）
    assert not rows["auth.active_profile"].sensitive


def test_auth_knobs_not_flagged_sensitive_in_project_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """auth §8 knobs 非敏感——可入项目级 ./paper-crawler.toml，不触发敏感键护栏拒启动。"""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    (repo / "paper-crawler.toml").write_text(
        '[auth]\ndaily_cap = 42\nwork_hours = "10-20"\n', encoding="utf-8"
    )
    monkeypatch.chdir(repo)
    cfg = Config.load(home=tmp_path / "home")  # 不抛护栏 CONFIG
    assert cfg.auth_daily_cap == 42 and cfg.auth_work_hours == "10-20"


def test_to_int_accepts_numeric_forms_rejects_bool_and_type() -> None:
    """int knob 解析：int/float/数字串 → int；bool 与非数值类型 → TypeError（畸形 config 响亮）。"""
    assert _to_int(200) == 200
    assert _to_int(900.0) == 900
    assert _to_int("30") == 30
    with pytest.raises(TypeError):
        _to_int(True)  # bool 显式拒绝（避免 True→1）
    with pytest.raises(TypeError):
        _to_int([1])  # 非 int/float/str 类型


# ---------------------------------------------------------------------------
# Phase 7 T6：browser-fetch 四槽（11-browser-fetch §7.5）——默认 / home / env / 畸形拒启动。
# ---------------------------------------------------------------------------


def test_browserfetch_slots_default_when_unset(tmp_path: Path) -> None:
    """无 config.toml + 无 env → 保守默认（D-029：**默认关**）。"""
    cfg = Config.load(home=tmp_path)
    assert cfg.browser_fetch_enabled is False
    assert cfg.browser_daily_cap == 50  # 严于 auth_daily_cap=200（本通道最敏感）
    assert cfg.browser_rate_rpm == 10  # = 1 req/6s
    assert cfg.browser_jitter_s == (2.0, 5.0)


def test_browserfetch_slots_from_home_config_toml(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    (home / "config.toml").write_text(
        "[browserfetch]\nenabled = true\ndaily_cap = 3\nrate_rpm = 12\njitter_s = [1, 4]\n",
        encoding="utf-8",
    )
    cfg = Config.load(home=home)
    assert cfg.browser_fetch_enabled is True
    assert cfg.browser_daily_cap == 3
    assert cfg.browser_rate_rpm == 12
    assert cfg.browser_jitter_s == (1.0, 4.0)


def test_browserfetch_env_overrides_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "home"
    home.mkdir()
    (home / "config.toml").write_text("[browserfetch]\nenabled = true\n", encoding="utf-8")
    monkeypatch.setenv("PAPER_CRAWLER_BROWSER_FETCH_ENABLED", "false")
    monkeypatch.setenv("PAPER_CRAWLER_BROWSER_JITTER_S", "0,0")
    cfg = Config.load(home=home)
    assert cfg.browser_fetch_enabled is False  # env > home
    assert cfg.browser_jitter_s == (0.0, 0.0)


@pytest.mark.parametrize("literal", ["1", "TRUE", "yes", "on"])
def test_browserfetch_enabled_accepts_true_literals(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, literal: str
) -> None:
    monkeypatch.setenv("PAPER_CRAWLER_BROWSER_FETCH_ENABLED", literal)
    assert Config.load(home=tmp_path).browser_fetch_enabled is True


def test_browserfetch_enabled_rejects_ambiguous_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """非真假字面量 → 拒启动（绝不把 `maybe` 当"打开"这一敏感通道）。"""
    monkeypatch.setenv("PAPER_CRAWLER_BROWSER_FETCH_ENABLED", "maybe")
    with pytest.raises(CrawlerError) as excinfo:
        Config.load(home=tmp_path)
    assert excinfo.value.error_class is ErrorClass.CONFIG


@pytest.mark.parametrize("bad_rpm", ["0", "-5"])
def test_browserfetch_rate_rpm_must_be_positive(tmp_path: Path, bad_rpm: str) -> None:
    """rpm ≤ 0 → 拒启动：桶补充速率为 0 会让 `acquire` 返 `inf`（无限等待 / `round(inf)`
    溢出被归 TRANSIENT 无限重试），畸形配置绝不能静默变成对站点的行为异常（审查 P2-5）。"""
    home = tmp_path / "home"
    home.mkdir()
    (home / "config.toml").write_text(f"[browserfetch]\nrate_rpm = {bad_rpm}\n", encoding="utf-8")
    with pytest.raises(CrawlerError) as excinfo:
        Config.load(home=home)
    assert excinfo.value.error_class is ErrorClass.CONFIG
    assert excinfo.value.detail == "browserfetch.rate_rpm"


def test_browserfetch_rate_rpm_env_is_validated_too(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PAPER_CRAWLER_BROWSER_RATE_RPM", "0")
    with pytest.raises(CrawlerError) as excinfo:
        Config.load(home=tmp_path)
    assert excinfo.value.error_class is ErrorClass.CONFIG


def test_browserfetch_daily_cap_zero_is_allowed_as_hard_stop(tmp_path: Path) -> None:
    """cap=0 语义明确（当日封停该通道），方向 fail-safe——不拦（与 rpm 下界的区别）。"""
    home = tmp_path / "home"
    home.mkdir()
    (home / "config.toml").write_text("[browserfetch]\ndaily_cap = 0\n", encoding="utf-8")
    assert Config.load(home=home).browser_daily_cap == 0


@pytest.mark.parametrize("bad", ["jitter_s = [5, 2]", "jitter_s = [-1, 2]", "jitter_s = [2]"])
def test_browserfetch_jitter_malformed_is_loud(tmp_path: Path, bad: str) -> None:
    home = tmp_path / "home"
    home.mkdir()
    (home / "config.toml").write_text(f"[browserfetch]\n{bad}\n", encoding="utf-8")
    with pytest.raises(CrawlerError) as excinfo:
        Config.load(home=home)
    assert excinfo.value.error_class is ErrorClass.CONFIG


def test_browserfetch_slots_in_describe_config(tmp_path: Path) -> None:
    """config show 追踪四槽（非敏感——可入项目级，不触发护栏）。"""
    rows = {r.key: r for r in describe_config(tmp_path)}
    for key in (
        "browserfetch.enabled",
        "browserfetch.daily_cap",
        "browserfetch.rate_rpm",
        "browserfetch.jitter_s",
    ):
        assert rows[key].source == "default"
        assert not rows[key].sensitive
