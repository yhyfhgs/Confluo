"""`crawler auth login/status/logout` CLI 单测（auth-framework §4；T1b）。

退出码契约（§4/design/05 Task 8）与安全断言：login 0/2/1 三态；status 恒 0 只读
（空配置正确呈现 + 不解密）；logout 取证式按 kind 分列（AC-4.5：config 明文槽不动、
state 无残留）；日志 jsonl 无凭证形态残留（AC-0.4）。

CliRunner 进程内驱动，零真实网络/浏览器/keyring。
"""

import json
import sys
from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

import paper_crawler.auth.browser as browser_mod
import paper_crawler.auth.providers.cookie_session as cookie_mod
import paper_crawler.auth.store as store_mod
from helpers.auth import FakeKeyring, install_fake_keyring
from paper_crawler.auth.store import CredentialStore
from paper_crawler.cli import app

runner = CliRunner()

SECRET_COOKIE = "COOKIE-SECRET-abc123"
STORAGE_STATE = json.dumps(
    {
        "cookies": [{"name": "sid", "value": SECRET_COOKIE, "domain": "mock.test", "path": "/"}],
        "origins": [],
    }
).encode("utf-8")

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
def _isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(store_mod, "_import_keyring", lambda: None)
    monkeypatch.setattr(store_mod, "_filekey_warned", True)
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


def write_profiles(home: Path, content: str) -> None:
    (home / "auth").mkdir(mode=0o700, exist_ok=True)
    (home / "auth" / "profiles.toml").write_text(content, encoding="utf-8")


API_PROFILE_TOML = """\
[providers.elsevier]
kind = "api_key"
platform = "elsevier_sd"
key_ref = "elsevier_apikey"
"""

COOKIE_PROFILE_TOML = """\
[providers."oup@campus"]
kind = "cookie_session"
platform = "oup_silverchair"
login_url = "https://mock.test/login"
state_ref = "oup_campus_state"
est_ttl_hours = 24
"""

COOKIE_PROFILE_WITH_PROBE_TOML = """\
[providers."oup@campus"]
kind = "cookie_session"
platform = "oup_silverchair"
login_url = "https://mock.test/login"
probe_url = "https://mock.test/my-account"
state_ref = "oup_campus_state"
"""

SSO_PROFILE_TOML = """\
[providers."oup@shib"]
kind = "sso_flow"
platform = "oup_silverchair"
inst_login_url = "https://mock.test/InstitutionalLogin"
wayf_hint = "My University"
state_ref = "oup_shib_state"
"""


def all_output(result: object) -> str:
    """stdout（+可分离的 stderr）合并文本——兼容 click 混流/分流两种版本。"""
    output = str(getattr(result, "output", ""))
    try:
        stderr = str(getattr(result, "stderr", ""))
    except ValueError:  # click 未单独捕获 stderr 的版本
        stderr = ""
    return output + stderr


def fake_login_flow(monkeypatch: pytest.MonkeyPatch, state: bytes = STORAGE_STATE) -> list[str]:
    """替换 browser.run_headed_login（cookie/sso/ezproxy 默认首登流的惰性入口）。"""
    calls: list[str] = []

    def fake(*, login_url: str, wait_for_user: object, launch: object = None) -> bytes:
        calls.append(login_url)
        return state

    monkeypatch.setattr(browser_mod, "run_headed_login", fake)
    return calls


# ---------------------------------------------------------------------------
# auth status
# ---------------------------------------------------------------------------


def test_status_empty_config_exits_zero(home: Path) -> None:
    result = runner.invoke(app, ["auth", "status", "--home", str(home)])
    assert result.exit_code == 0, all_output(result)
    assert "无 provider 配置" in result.output
    assert "profiles.toml" in result.output


def test_status_renders_rows_and_exit_zero(home: Path) -> None:
    write_profiles(home, API_PROFILE_TOML + "\n" + COOKIE_PROFILE_TOML)
    result = runner.invoke(app, ["auth", "status", "--home", str(home)])
    assert result.exit_code == 0, all_output(result)
    assert "provider" in result.output and "last_health" in result.output  # §4.2 列头
    assert "elsevier" in result.output
    assert "oup@campus" in result.output
    assert "needs `auth login" in result.output  # 未配置/未登录行


def test_status_read_only_never_decrypts(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """安全断言 #10：status 只读 meta sidecar——加密依赖被毒化仍照常工作。"""
    write_profiles(home, COOKIE_PROFILE_TOML)
    store = CredentialStore(home)
    store.write_state("oup_campus_state", STORAGE_STATE)
    store.write_meta(
        "oup_campus_state",
        {"backend": "httpx_cookies", "established_at": "2026-07-23T00:00:00+00:00"},
    )

    def poisoned() -> object:
        raise AssertionError("status must not decrypt")

    monkeypatch.setattr(store_mod, "_import_aesgcm", poisoned)
    result = runner.invoke(app, ["auth", "status", "--home", str(home)])
    assert result.exit_code == 0, all_output(result)
    assert "age" in result.output  # session 年龄来自 sidecar，非解密


# ---------------------------------------------------------------------------
# auth login：api_key 档（§4.1 行 1）
# ---------------------------------------------------------------------------


def test_login_unknown_provider_exit_2(home: Path) -> None:
    write_profiles(home, API_PROFILE_TOML)
    result = runner.invoke(app, ["auth", "login", "mystery", "--home", str(home)])
    assert result.exit_code == 2, all_output(result)
    assert "未知 auth provider" in all_output(result)


def test_login_api_key_missing_exit_2_with_guidance(home: Path) -> None:
    write_profiles(home, API_PROFILE_TOML)
    result = runner.invoke(app, ["auth", "login", "elsevier", "--home", str(home)])
    assert result.exit_code == 2, all_output(result)
    assert "[auth.elsevier].api_key" in all_output(result)  # 配置路径指引（§4.1 退出码 2）


def test_login_api_key_configured_exit_0(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_profiles(home, API_PROFILE_TOML)
    monkeypatch.setenv("PAPER_CRAWLER_ELSEVIER_API_KEY", "ENV-KEY-123")
    result = runner.invoke(app, ["auth", "login", "elsevier", "--home", str(home)])
    assert result.exit_code == 0, all_output(result)
    assert "elsevier: ready" in result.output
    # login 落 meta sidecar（status 呈现源），且不含密钥值
    meta_path = home / "auth" / "state" / "elsevier_apikey.meta.json"
    assert meta_path.is_file()
    assert "ENV-KEY-123" not in meta_path.read_text(encoding="utf-8")
    status = runner.invoke(app, ["auth", "status", "--home", str(home)])
    assert "configured" in status.output
    assert "ENV-KEY-123" not in status.output


# ---------------------------------------------------------------------------
# auth login：cookie/sso 档（§4.1 行 2/3；browser seam）
# ---------------------------------------------------------------------------


def test_login_cookie_without_auth_browser_extra_exit_2(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """未装 [auth-browser]：exit 2 + `pip install paper-crawler[auth-browser]` 提示。"""
    write_profiles(home, COOKIE_PROFILE_TOML)
    monkeypatch.setitem(sys.modules, "playwright", None)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", None)
    result = runner.invoke(app, ["auth", "login", "oup@campus", "--home", str(home)])
    assert result.exit_code == 2, all_output(result)
    assert "pip install paper-crawler[auth-browser]" in all_output(result)


def test_login_cookie_first_login_persists_encrypted_state(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_profiles(home, COOKIE_PROFILE_TOML)
    calls = fake_login_flow(monkeypatch)
    result = runner.invoke(app, ["auth", "login", "oup@campus", "--home", str(home)])
    assert result.exit_code == 0, all_output(result)
    assert calls == ["https://mock.test/login"]
    enc = home / "auth" / "state" / "oup_campus_state.enc"
    assert enc.is_file()
    assert SECRET_COOKIE.encode() not in enc.read_bytes()  # 加密落盘（AC-0.3）
    # AC-0.4：全部 jsonl 日志无 cookie 值残留
    jsonl_text = "".join(p.read_text(encoding="utf-8") for p in (home / "logs").glob("*.jsonl"))
    assert SECRET_COOKIE not in jsonl_text
    # 全 home 树唯一持有 cookie 值的文件 = 加密 .enc（无任何明文副本）
    for path in home.rglob("*"):
        if path.is_file():
            assert SECRET_COOKIE.encode() not in path.read_bytes(), path


def test_login_cookie_probe_ok_exit_0(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_profiles(home, COOKIE_PROFILE_WITH_PROBE_TOML)
    fake_login_flow(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>Signed in as prof</html>")

    def factory(cookies: httpx.Cookies) -> httpx.Client:
        return httpx.Client(
            cookies=cookies, follow_redirects=True, transport=httpx.MockTransport(handler)
        )

    monkeypatch.setattr(cookie_mod, "_default_http_factory", factory)
    result = runner.invoke(app, ["auth", "login", "oup@campus", "--home", str(home)])
    assert result.exit_code == 0, all_output(result)


def test_login_cookie_probe_login_redirect_exit_1(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """探针不 OK（302→signin）→ 退出码 1（§4.1"1 探针失败"）。"""
    write_profiles(home, COOKIE_PROFILE_WITH_PROBE_TOML)
    fake_login_flow(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/my-account":
            return httpx.Response(302, headers={"location": "https://mock.test/signin"})
        return httpx.Response(200, text="<html>please sign in</html>")

    def factory(cookies: httpx.Cookies) -> httpx.Client:
        return httpx.Client(
            cookies=cookies, follow_redirects=True, transport=httpx.MockTransport(handler)
        )

    monkeypatch.setattr(cookie_mod, "_default_http_factory", factory)
    result = runner.invoke(app, ["auth", "login", "oup@campus", "--home", str(home)])
    assert result.exit_code == 1, all_output(result)
    assert "探针未通过" in all_output(result)


def test_login_sso_shows_wayf_hint(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_profiles(home, SSO_PROFILE_TOML)
    calls = fake_login_flow(monkeypatch)
    result = runner.invoke(app, ["auth", "login", "oup@shib", "--home", str(home)])
    assert result.exit_code == 0, all_output(result)
    assert "WAYF 机构选择提示：My University" in result.output  # §4.1 wayf_hint 辅助
    assert calls == ["https://mock.test/InstitutionalLogin"]


def test_login_profile_option_resolves_named_profile(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_profiles(home, COOKIE_PROFILE_TOML)
    fake_login_flow(monkeypatch)
    result = runner.invoke(
        app, ["auth", "login", "oup", "--profile", "campus", "--home", str(home)]
    )
    assert result.exit_code == 0, all_output(result)
    assert "oup@campus: ready" in result.output


# ---------------------------------------------------------------------------
# auth logout（§4.3 / AC-4.5 取证式；B-m6 按 kind 分列）
# ---------------------------------------------------------------------------


def test_logout_cookie_forensic_no_residue(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_profiles(home, COOKIE_PROFILE_TOML)
    fake_login_flow(monkeypatch)
    assert runner.invoke(app, ["auth", "login", "oup@campus", "--home", str(home)]).exit_code == 0
    state_dir = home / "auth" / "state"
    assert list(state_dir.glob("*.enc"))
    result = runner.invoke(app, ["auth", "logout", "oup@campus", "--home", str(home)])
    assert result.exit_code == 0, all_output(result)
    # AC-4.5 取证清单（cookie 类）：.enc / meta / .filekey 全无残留
    assert not list(state_dir.glob("*.enc"))
    assert not list(state_dir.glob("*.meta.json"))
    assert not (state_dir / ".filekey").exists()
    leftovers = list(state_dir.iterdir()) if state_dir.is_dir() else []
    assert leftovers == []  # state 目录彻底干净
    # 幂等：再次 logout 仍 0
    again = runner.invoke(app, ["auth", "logout", "oup@campus", "--home", str(home)])
    assert again.exit_code == 0


def test_logout_api_key_keeps_user_config_slot(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """B-m6：api_key logout 清 keyring 副本，不删用户 config.toml 明文槽。"""
    write_profiles(home, API_PROFILE_TOML)
    config_text = '[auth.elsevier]\napi_key = "user-managed-key"\n'
    (home / "config.toml").write_text(config_text, encoding="utf-8")
    fake = FakeKeyring()
    fake.entries[("paper-crawler", "elsevier_apikey")] = "keyring-copy"
    install_fake_keyring(monkeypatch, fake)
    result = runner.invoke(app, ["auth", "logout", "elsevier", "--home", str(home)])
    assert result.exit_code == 0, all_output(result)
    assert ("paper-crawler", "elsevier_apikey") not in fake.entries  # 工具管理副本清除
    assert (home / "config.toml").read_text(encoding="utf-8") == config_text  # 用户槽不动
    status = runner.invoke(app, ["auth", "status", "--home", str(home)])
    assert "configured" in status.output  # config 槽仍生效（logout 只撤销工具副本）


def test_logout_unknown_provider_exit_2(home: Path) -> None:
    write_profiles(home, API_PROFILE_TOML)
    result = runner.invoke(app, ["auth", "logout", "mystery", "--home", str(home)])
    assert result.exit_code == 2, all_output(result)


# ---------------------------------------------------------------------------
# profiles 配置错（schema 严格性经 CLI 面）
# ---------------------------------------------------------------------------


def test_login_with_invalid_profiles_schema_exit_2(home: Path) -> None:
    write_profiles(home, '[providers.x]\nkind = "api_key"\nplatform = "p"\n')  # 缺 key_ref
    result = runner.invoke(app, ["auth", "login", "x", "--home", str(home)])
    assert result.exit_code == 2, all_output(result)
    assert "key_ref" in all_output(result)


def test_login_cookie_probe_network_error_exit_1(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """探针网络失败（CrawlerError 非 AuthRequired）→ 退出码 1（§4.1）。"""
    write_profiles(home, COOKIE_PROFILE_WITH_PROBE_TOML)
    fake_login_flow(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route", request=request)

    def factory(cookies: httpx.Cookies) -> httpx.Client:
        return httpx.Client(
            cookies=cookies, follow_redirects=True, transport=httpx.MockTransport(handler)
        )

    monkeypatch.setattr(cookie_mod, "_default_http_factory", factory)
    result = runner.invoke(app, ["auth", "login", "oup@campus", "--home", str(home)])
    assert result.exit_code == 1, all_output(result)
    assert "probe failed" in all_output(result)


# ---------------------------------------------------------------------------
# 审查 MINOR-1：status 对损坏 profiles.toml 走 clean-error（exit 2，无裸 traceback）
# ---------------------------------------------------------------------------


def test_status_corrupt_profiles_toml_syntax_exit_2_clean_error(home: Path) -> None:
    """TOML 语法损坏 → exit 2 + 无 traceback + 错误信息含完整文件路径指引。"""
    write_profiles(home, "[providers.broken\nkind = ???")  # 非法 TOML
    result = runner.invoke(app, ["auth", "status", "--home", str(home)])
    assert result.exit_code == 2, all_output(result)
    output = all_output(result)
    assert "Traceback" not in output  # clean-error 惯例（无 Rich 裸栈）
    assert result.exception is None or isinstance(result.exception, SystemExit)
    assert str(home / "auth" / "profiles.toml") in output  # 完整路径指引
    assert "错误" in output


def test_status_invalid_profiles_schema_exit_2_clean_error(home: Path) -> None:
    """schema 非法（未知键）→ exit 2 + 无 traceback + 指引含 profiles.toml。"""
    write_profiles(
        home, '[providers.x]\nkind = "api_key"\nplatform = "p"\nkey_ref = "k"\nmystery = 1\n'
    )
    result = runner.invoke(app, ["auth", "status", "--home", str(home)])
    assert result.exit_code == 2, all_output(result)
    output = all_output(result)
    assert "Traceback" not in output
    assert "profiles.toml" in output
    assert "mystery" in output  # 指向具体非法键
