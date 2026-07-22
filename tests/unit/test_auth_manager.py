"""`auth/manager.py` 单测（auth-framework §1/§4.2；T1b）。

锁定面：kind→实现类注册表（load_providers）；resolve 的 active_profile/--profile/
platform 解析序与歧义报错；ensure_session 进程内缓存；logout 按 kind 取证清理
（B-m6 + 主密钥按需清 ⑤）；status_rows 只读呈现（meta sidecar，不解密不探测）；
启动权限巡检 WARNING。零真实网络/浏览器/keyring。
"""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import paper_crawler.auth.store as store_mod
from helpers.auth import FakeKeyring, install_fake_keyring, make_config
from paper_crawler.auth.manager import AuthManager, ProviderStatus, load_providers
from paper_crawler.auth.providers.api_key import ApiKeyProvider
from paper_crawler.auth.providers.cookie_session import CookieSessionProvider
from paper_crawler.auth.providers.ezproxy import EZProxyProvider
from paper_crawler.auth.providers.sso_flow import SSOFlowProvider
from paper_crawler.auth.store import CredentialStore
from paper_crawler.errors import AuthRequired, CrawlerError, ErrorClass

T0 = datetime(2026, 7, 23, 12, 0, 0, tzinfo=UTC)
SECRET_KEY = "APIKEY-SECRET-xyz789"

PROFILES = """\
schema_version = 1

[providers.elsevier]
kind = "api_key"
platform = "elsevier_sd"
key_ref = "elsevier_apikey"
insttoken_ref = "elsevier_insttoken"

[providers."oup@campus"]
kind = "cookie_session"
platform = "oup_silverchair"
login_url = "https://mock.test/login"
state_ref = "oup_campus_state"
est_ttl_hours = 24

[providers."oup@shib"]
kind = "sso_flow"
platform = "oup_silverchair"
inst_login_url = "https://mock.test/InstitutionalLogin"
wayf_hint = "My University"
state_ref = "oup_shib_state"
est_ttl_hours = 8

[providers."elsevier@ezproxy"]
kind = "ezproxy"
platform = "elsevier_sd"
proxy_base = "https://login.myuniv.edu/login?url="
rewrite_suffix = ".login-myuniv-edu.ezproxy"
state_ref = "ezproxy_myuniv_state"
est_ttl_hours = 12
"""


@pytest.fixture(autouse=True)
def _isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(store_mod, "_import_keyring", lambda: None)
    monkeypatch.setattr(store_mod, "_filekey_warned", True)
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def home(tmp_path: Path) -> Path:
    home = tmp_path / "home"
    (home / "auth").mkdir(mode=0o700, parents=True)
    (home / "auth" / "profiles.toml").write_text(PROFILES, encoding="utf-8")
    return home


class FakeClock:
    def __init__(self, start: datetime = T0) -> None:
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kwargs: float) -> None:
        self.now = self.now + timedelta(**kwargs)


def make_manager(
    home: Path,
    clock: FakeClock | None = None,
    active_profiles: dict[str, str] | None = None,
    **config_overrides: object,
) -> AuthManager:
    config = make_config(home, **config_overrides)
    return AuthManager(config, clock=clock or FakeClock(), active_profiles=active_profiles)


# ---------------------------------------------------------------------------
# 注册表（load_providers）
# ---------------------------------------------------------------------------


def test_load_providers_maps_kind_to_implementation(home: Path) -> None:
    store = CredentialStore(home)
    store.bind_config(make_config(home))
    providers = load_providers(store)
    assert type(providers["elsevier"]) is ApiKeyProvider
    assert type(providers["oup@campus"]) is CookieSessionProvider
    assert type(providers["oup@shib"]) is SSOFlowProvider
    assert type(providers["elsevier@ezproxy"]) is EZProxyProvider
    assert providers["oup@shib"].provider_id == "oup@shib"


def test_manager_providers_cached_single_construction(home: Path) -> None:
    manager = make_manager(home)
    assert manager.providers() is manager.providers()
    assert manager.get("elsevier") is manager.get("elsevier")


def test_manager_get_unknown_lists_known(home: Path) -> None:
    manager = make_manager(home)
    with pytest.raises(CrawlerError) as excinfo:
        manager.get("nonexistent")
    assert excinfo.value.error_class is ErrorClass.CONFIG
    assert "oup@campus" in str(excinfo.value)


def test_manager_empty_profiles(tmp_path: Path) -> None:
    home = tmp_path / "empty-home"
    manager = make_manager(home)
    assert manager.providers() == {}
    assert manager.status_rows() == []
    with pytest.raises(CrawlerError):
        manager.get("anything")


# ---------------------------------------------------------------------------
# resolve：--profile / active_profile / platform 唯一候选 / 歧义
# ---------------------------------------------------------------------------


def test_resolve_exact_profiles_key(home: Path) -> None:
    manager = make_manager(home)
    assert manager.resolve("oup@campus").provider_id == "oup@campus"
    assert manager.resolve("elsevier").provider_id == "elsevier"


def test_resolve_profile_option_suffix_and_full_key(home: Path) -> None:
    manager = make_manager(home)
    assert manager.resolve("oup", profile="campus").provider_id == "oup@campus"
    assert manager.resolve("whatever", profile="oup@shib").provider_id == "oup@shib"


def test_resolve_platform_via_active_profile_mapping(home: Path) -> None:
    manager = make_manager(home, active_profiles={"elsevier_sd": "elsevier@ezproxy"})
    assert manager.resolve("elsevier_sd").provider_id == "elsevier@ezproxy"


def test_resolve_platform_ambiguous_without_mapping(home: Path) -> None:
    manager = make_manager(home)
    with pytest.raises(CrawlerError) as excinfo:
        manager.resolve("oup_silverchair")  # oup@campus / oup@shib 双候选
    assert "--profile" in str(excinfo.value)
    assert "oup@campus" in str(excinfo.value)


def test_resolve_platform_single_candidate(tmp_path: Path) -> None:
    home = tmp_path / "single-home"
    (home / "auth").mkdir(mode=0o700, parents=True)
    (home / "auth" / "profiles.toml").write_text(
        '[providers."oup@campus"]\nkind = "cookie_session"\nplatform = "oup_silverchair"\n'
        'login_url = "https://mock.test/login"\nstate_ref = "s"\n',
        encoding="utf-8",
    )
    manager = make_manager(home)
    assert manager.resolve("oup_silverchair").provider_id == "oup@campus"


def test_resolve_unknown_name_raises(home: Path) -> None:
    with pytest.raises(CrawlerError):
        make_manager(home).resolve("mystery_platform")
    with pytest.raises(CrawlerError):
        make_manager(home).resolve("oup", profile="nonexistent")


# ---------------------------------------------------------------------------
# session 缓存 + logout 取证（B-m6 / ⑤）
# ---------------------------------------------------------------------------


def test_ensure_session_caches_per_provider(home: Path) -> None:
    clock = FakeClock()
    manager = make_manager(home, clock=clock, elsevier_api_key=SECRET_KEY)
    first = manager.ensure_session("elsevier")
    clock.advance(hours=2)
    second = manager.ensure_session("elsevier")
    assert second is first  # 进程内缓存：不重复 ensure（established 不漂移）
    manager.drop_session("elsevier")
    third = manager.ensure_session("elsevier")
    assert third.established_at == clock.now


def test_ensure_session_noninteractive_missing_raises(home: Path) -> None:
    manager = make_manager(home)
    with pytest.raises(AuthRequired):
        manager.ensure_session("oup@campus")


def test_logout_stateful_forensic_chain(home: Path) -> None:
    manager = make_manager(home)
    store = manager.store
    store.write_state("oup_campus_state", b'{"cookies": []}')
    store.write_meta("oup_campus_state", {"backend": "httpx_cookies"})
    assert (store.state_dir / ".filekey").is_file()
    manager.logout("oup@campus")
    assert not (store.state_dir / "oup_campus_state.enc").exists()  # ①
    assert not (store.state_dir / "oup_campus_state.meta.json").exists()  # ①
    assert not (store.state_dir / ".filekey").exists()  # ⑤ 最后一个 .enc 删除 → 主密钥清理
    assert not list(store.state_dir.glob("*.enc"))


def test_logout_stateful_keeps_master_key_while_others_remain(home: Path) -> None:
    manager = make_manager(home)
    store = manager.store
    store.write_state("oup_campus_state", b"a")
    store.write_state("oup_shib_state", b"b")
    manager.logout("oup@campus")
    assert (store.state_dir / ".filekey").is_file()  # oup@shib 仍在用主密钥
    assert store.read_state("oup_shib_state") == b"b"


def test_logout_clears_session_cache(home: Path) -> None:
    clock = FakeClock()
    manager = make_manager(home, clock=clock, elsevier_api_key=SECRET_KEY)
    manager.ensure_session("elsevier")
    manager.logout("elsevier")
    clock.advance(hours=5)
    fresh = manager.ensure_session("elsevier")  # 缓存已清（②）：重新 ensure
    assert fresh.established_at == clock.now


def test_logout_api_key_keyring_copy_only(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeKeyring()
    fake.entries[("paper-crawler", "elsevier_apikey")] = "keyring-copy"
    fake.entries[("paper-crawler", "elsevier_insttoken")] = "inst-copy"
    install_fake_keyring(monkeypatch, fake)
    manager = make_manager(home, elsevier_api_key="config-value")
    manager.logout("elsevier")
    assert ("paper-crawler", "elsevier_apikey") not in fake.entries
    assert ("paper-crawler", "elsevier_insttoken") not in fake.entries
    assert ("paper-crawler", "master-key") not in fake.entries  # api_key 路径不触主密钥
    assert manager.store.read_key("elsevier_apikey") == "config-value"  # config 槽不动


def test_logout_unknown_provider_raises(home: Path) -> None:
    with pytest.raises(CrawlerError):
        make_manager(home).logout("nonexistent")


def test_logout_idempotent_when_nothing_stored(home: Path) -> None:
    manager = make_manager(home)
    manager.logout("oup@campus")  # 本就无残留：静默成功（幂等）
    manager.logout("oup@campus")


# ---------------------------------------------------------------------------
# status_rows（§4.2 只读呈现：meta sidecar；不解密不探测）
# ---------------------------------------------------------------------------


def rows_by_provider(manager: AuthManager) -> dict[str, ProviderStatus]:
    return {row.provider: row for row in manager.status_rows()}


def test_status_api_key_configured_and_absent(home: Path) -> None:
    rows = rows_by_provider(make_manager(home, elsevier_api_key=SECRET_KEY))
    assert rows["elsevier"].session == "configured"
    assert rows["elsevier"].backend == "bearer_token"
    assert rows["elsevier"].state == "ready"
    assert rows["elsevier"].est_expiry == "—"
    rows_nokey = rows_by_provider(make_manager(home))
    assert rows_nokey["elsevier"].session == "absent"
    assert rows_nokey["elsevier"].state == "needs `auth login elsevier`"


def test_status_stateful_fresh_session_row(home: Path) -> None:
    clock = FakeClock()
    manager = make_manager(home, clock=clock)
    store = manager.store
    store.write_state("oup_campus_state", b"state")
    store.write_meta(
        "oup_campus_state",
        {
            "backend": "httpx_cookies",
            "established_at": T0.isoformat(),
            "last_health": "ok",
            "last_health_at": T0.isoformat(),
        },
    )
    clock.advance(hours=3)
    row = rows_by_provider(manager)["oup@campus"]
    assert row.kind == "cookie_session"
    assert row.backend == "httpx_cookies"
    assert row.session == "age 3h"
    assert row.last_health == "OK (2026-07-23 12:00)"
    assert row.est_expiry == "~21h"  # 24h TTL - 3h age（§4.2 样例行）
    assert row.state == "ready"


def test_status_stateful_expired_ttl_needs_login(home: Path) -> None:
    clock = FakeClock()
    manager = make_manager(home, clock=clock)
    store = manager.store
    store.write_state("oup_shib_state", b"state")
    store.write_meta("oup_shib_state", {"established_at": T0.isoformat(), "last_health": "expired"})
    clock.advance(hours=9)  # est_ttl 8h → 已过期
    row = rows_by_provider(manager)["oup@shib"]
    assert row.session == "age 9h"
    assert row.est_expiry == "expired"
    assert row.state == "needs `auth login oup@shib`"
    assert row.last_health == "EXPIRED"  # 无 last_health_at → 只呈现结果


def test_status_stateful_absent_row(home: Path) -> None:
    row = rows_by_provider(make_manager(home))["elsevier@ezproxy"]
    assert row.session == "absent"
    assert row.last_health == "—"
    assert row.est_expiry == "—"
    assert row.state == "needs `auth login elsevier@ezproxy`"


def test_status_challenged_last_health_needs_login(home: Path) -> None:
    manager = make_manager(home)
    store = manager.store
    store.write_state("oup_campus_state", b"state")
    store.write_meta(
        "oup_campus_state", {"established_at": T0.isoformat(), "last_health": "challenged"}
    )
    row = rows_by_provider(manager)["oup@campus"]
    assert row.state == "needs `auth login oup@campus`"


def test_status_is_read_only_no_decrypt_no_probe(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§4.2：status 只读 meta sidecar——加密面被毒化也照常呈现（绝不解密/探测）。"""
    manager = make_manager(home)
    store = manager.store
    store.write_state("oup_campus_state", b"state")

    def poisoned() -> object:
        raise AssertionError("status must not touch cryptography")

    monkeypatch.setattr(store_mod, "_import_aesgcm", poisoned)
    rows = rows_by_provider(manager)
    assert rows["oup@campus"].session == "present"  # state 在但无 meta 时间戳：如实呈现


def test_status_rows_never_contain_secret_values(home: Path) -> None:
    manager = make_manager(home, elsevier_api_key=SECRET_KEY)
    for row in manager.status_rows():
        for cell in (
            row.provider,
            row.kind,
            row.backend,
            row.session,
            row.last_health,
            row.est_expiry,
            row.state,
        ):
            assert SECRET_KEY not in cell  # 呈现层零凭证值（安全断言 #7）


# ---------------------------------------------------------------------------
# 启动巡检（§3.5）
# ---------------------------------------------------------------------------


def test_manager_init_audit_logs_permission_warnings(home: Path, tmp_path: Path) -> None:
    from paper_crawler.obslog import setup_logging

    store = CredentialStore(home)
    store.bind_config(make_config(home))
    store.write_state("oup_campus_state", b"state")
    (store.state_dir / "oup_campus_state.enc").chmod(0o644)
    log_dir = tmp_path / "logs"
    setup_logging(log_dir)
    make_manager(home)  # 构造即巡检
    lines = [
        json.loads(line)
        for jsonl in log_dir.glob("*.jsonl")
        for line in jsonl.read_text(encoding="utf-8").splitlines()
    ]
    warnings = [ln for ln in lines if ln["level"] == "WARNING" and "权限巡检" in ln["msg"]]
    assert warnings, "非 0600 state 文件必须产生启动巡检 WARNING"
    # 不自动改（§3.5）
    import stat as stat_mod

    assert stat_mod.S_IMODE((store.state_dir / "oup_campus_state.enc").stat().st_mode) == 0o644
