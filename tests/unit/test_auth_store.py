"""`auth/store.py` 单测（auth-framework §2.3 冻结签名 + §3 全节；T1b）。

安全断言锁定面（终报清单对应）：AES-256-GCM 每次新 nonce + AAD=ref（#1）、keyring
降级链 + 每进程一次警告（#2）、0600/0700 原子创建与巡检不自动改（#3）、delete_state
覆写后 unlink（#4）、密钥值不外泄（#7）、read_key 统一取/has_key 布尔（#8）、惰性
import 与未装 [auth] 报错文案（#9）、meta sidecar 非密（#10）、profiles schema 严格
拒未知键 + kind×必填组合（#12）。

全部测试**零真实 keyring**（`_import_keyring` 恒被替换——绝不触宿主 Keychain）、
零真实网络、零真实浏览器。
"""

import json
import stat
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

import paper_crawler.auth.store as store_mod
from helpers.auth import FakeKeyring, install_fake_keyring, make_config
from paper_crawler.auth.store import CredentialStore, ProviderProfile, parse_meta_datetime
from paper_crawler.errors import AuthRequired, CrawlerError, ErrorClass

# ---------------------------------------------------------------------------
# fixtures：keyring 绝缘（默认无后端→filekey 路径）+ 警告旗标复位 + env 清理
# ---------------------------------------------------------------------------

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
    """keyring 绝缘（防触宿主 Keychain）+ 一次性警告旗标复位 + env/cwd 隔离。"""
    monkeypatch.setattr(store_mod, "_import_keyring", lambda: None)
    monkeypatch.setattr(store_mod, "_filekey_warned", False)
    for var in _PC_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    workdir = tmp_path / "cwd"
    workdir.mkdir(exist_ok=True)
    monkeypatch.chdir(workdir)


@pytest.fixture
def home(tmp_path: Path) -> Path:
    return tmp_path / "home"


@pytest.fixture
def store(home: Path) -> CredentialStore:
    return CredentialStore(home)


# ---------------------------------------------------------------------------
# AES-GCM round-trip / nonce / AAD（安全断言 #1）
# ---------------------------------------------------------------------------


def test_write_read_state_roundtrip_filekey_mode(store: CredentialStore) -> None:
    plaintext = b'{"cookies": [{"name": "sid", "value": "SECRET-COOKIE"}]}'
    store.write_state("oup_campus_state", plaintext)
    assert store.read_state("oup_campus_state") == plaintext
    blob = (store.state_dir / "oup_campus_state.enc").read_bytes()
    assert b"SECRET-COOKIE" not in blob  # 密文不含明文形态
    assert len(blob) > len(plaintext)  # nonce(12) + ciphertext + tag(16)


def test_write_state_fresh_random_nonce_every_call(store: CredentialStore) -> None:
    """A-m1：每次加密调用新随机 12B nonce（前置于密文）——同 ref 同明文两次落盘不同。"""
    path = store.state_dir / "ref_a.enc"
    store.write_state("ref_a", b"same-plaintext")
    first = path.read_bytes()
    store.write_state("ref_a", b"same-plaintext")
    second = path.read_bytes()
    assert first[:12] != second[:12]  # nonce 逐次全新
    assert first != second


def test_read_state_aad_binds_entry_ref_rejects_cross_ref_replay(store: CredentialStore) -> None:
    """AAD=条目 ref：把 a.enc 拷成 b.enc（跨条目重放）必然解密失败。"""
    store.write_state("ref_a", b"payload-a")
    (store.state_dir / "ref_b.enc").write_bytes((store.state_dir / "ref_a.enc").read_bytes())
    with pytest.raises(AuthRequired):
        store.read_state("ref_b")
    assert store.read_state("ref_a") == b"payload-a"  # 原条目不受影响


def test_read_state_missing_raises_auth_required(store: CredentialStore) -> None:
    with pytest.raises(AuthRequired) as excinfo:
        store.read_state("absent_ref")
    assert "auth login" in excinfo.value.detail


def test_read_state_corrupt_blob_raises_auth_required(store: CredentialStore) -> None:
    store.write_state("ref_a", b"payload")
    path = store.state_dir / "ref_a.enc"
    blob = bytearray(path.read_bytes())
    blob[-1] ^= 0xFF  # 篡改密文尾字节（认证 tag 校验必败）
    path.write_bytes(bytes(blob))
    with pytest.raises(AuthRequired):
        store.read_state("ref_a")
    path.write_bytes(b"short")  # 短于 nonce 布局
    with pytest.raises(AuthRequired):
        store.read_state("ref_a")


def test_master_key_is_32_bytes(store: CredentialStore) -> None:
    store.write_state("ref_a", b"x")
    assert len((store.state_dir / ".filekey").read_bytes()) == 32  # AES-256 主密钥


# ---------------------------------------------------------------------------
# 0600/0700 权限（安全断言 #3）+ 巡检不自动改
# ---------------------------------------------------------------------------


def test_state_file_dirs_and_filekey_modes(store: CredentialStore) -> None:
    store.write_state("ref_a", b"payload")
    assert stat.S_IMODE((store.state_dir / "ref_a.enc").stat().st_mode) == 0o600
    assert stat.S_IMODE((store.state_dir / ".filekey").stat().st_mode) == 0o600
    assert stat.S_IMODE(store.auth_dir.stat().st_mode) == 0o700
    assert stat.S_IMODE(store.state_dir.stat().st_mode) == 0o700


def test_audit_permissions_warns_but_never_chmods(store: CredentialStore) -> None:
    store.write_state("ref_a", b"payload")
    store.write_meta("ref_a", {"backend": "httpx_cookies"})  # 非密 sidecar：巡检跳过不告警
    (store.state_dir / "ref_a.enc").chmod(0o644)
    store.state_dir.chmod(0o755)
    findings = store.audit_permissions()
    assert any("ref_a.enc" in f and "0600" in f for f in findings)
    assert any("state" in f and "0700" in f for f in findings)
    # 不自动改（§3.5：告警不掩盖问题）
    assert stat.S_IMODE((store.state_dir / "ref_a.enc").stat().st_mode) == 0o644
    assert stat.S_IMODE(store.state_dir.stat().st_mode) == 0o755


def test_audit_permissions_clean_store_no_findings(store: CredentialStore) -> None:
    store.write_state("ref_a", b"payload")
    assert store.audit_permissions() == []


def test_audit_permissions_empty_home_no_findings(store: CredentialStore) -> None:
    assert store.audit_permissions() == []  # 目录未建（空配置）→ 零告警零建目录
    assert not store.auth_dir.exists()


# ---------------------------------------------------------------------------
# delete_state：覆写后 unlink（安全断言 #4，AC-4.5）
# ---------------------------------------------------------------------------


def test_delete_state_overwrites_content_before_unlink(
    store: CredentialStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    store.write_state("ref_a", b"payload-to-forget")
    path = store.state_dir / "ref_a.enc"
    original = path.read_bytes()
    captured: dict[str, bytes] = {}
    real_unlink = Path.unlink

    def spy(self: Path, *, missing_ok: bool = False) -> None:
        if self.suffix == ".enc":
            captured["at_unlink"] = self.read_bytes()
        real_unlink(self, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", spy)
    store.delete_state("ref_a")
    assert not path.exists()
    assert captured["at_unlink"] != original  # unlink 时内容已被随机覆写
    assert len(captured["at_unlink"]) == len(original)  # 等长覆写（无截断残留窗）


def test_delete_state_missing_is_silent_noop(store: CredentialStore) -> None:
    store.delete_state("never_written")  # 不抛错（§2.3）


def test_delete_state_removes_meta_sidecar_too(store: CredentialStore) -> None:
    store.write_state("ref_a", b"payload")
    store.write_meta("ref_a", {"backend": "httpx_cookies"})
    store.delete_state("ref_a")
    assert not (store.state_dir / "ref_a.enc").exists()
    assert not (store.state_dir / "ref_a.meta.json").exists()


# ---------------------------------------------------------------------------
# keyring 降级链（安全断言 #2）：fail/Null/NoKeyringError → filekey + 一次警告
# ---------------------------------------------------------------------------


def test_filekey_downgrade_warns_exactly_once_per_process(
    store: CredentialStore, home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store.write_state("ref_a", b"one")
    CredentialStore(home).write_state("ref_b", b"two")  # 第二实例：同进程不再警告
    err = capsys.readouterr().err
    assert err.count("keyring") == 1
    assert "⚠ 系统无可用 keyring 后端；认证主密钥降级为文件密钥 state/.filekey（0600）。" in err
    assert "该文件泄漏等价 session 泄漏——确保 config-home 目录访问受控（AGENTS §6.4）。" in err


def test_filekey_downgrade_warning_reaches_obslog_jsonl(
    store: CredentialStore, tmp_path: Path
) -> None:
    from paper_crawler.obslog import setup_logging

    log_dir = tmp_path / "logs"
    setup_logging(log_dir)
    store.write_state("ref_a", b"payload")
    lines = [
        json.loads(line)
        for jsonl in log_dir.glob("*.jsonl")
        for line in jsonl.read_text(encoding="utf-8").splitlines()
    ]
    warnings = [ln for ln in lines if ln["level"] == "WARNING" and "keyring" in ln["msg"]]
    assert len(warnings) == 1


def test_filekey_reused_across_instances_keeps_state_decryptable(home: Path) -> None:
    CredentialStore(home).write_state("ref_a", b"payload")
    assert CredentialStore(home).read_state("ref_a") == b"payload"  # 同一 .filekey


@pytest.mark.parametrize(
    "backend_module",
    ["keyring.backends.fail", "keyring.backends.null"],
)
def test_fail_and_null_backends_degrade_to_filekey(
    store: CredentialStore, monkeypatch: pytest.MonkeyPatch, backend_module: str
) -> None:
    fake = FakeKeyring(backend_module=backend_module)
    install_fake_keyring(monkeypatch, fake)
    store.write_state("ref_a", b"payload")
    assert (store.state_dir / ".filekey").is_file()  # 降级为文件密钥
    assert fake.entries == {}  # 主密钥绝不存入死后端


def test_get_keyring_exception_degrades_to_filekey(
    store: CredentialStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom() -> object:
        raise RuntimeError("NoKeyringError: no usable backend")

    install_fake_keyring(monkeypatch, SimpleNamespace(get_keyring=boom))
    store.write_state("ref_a", b"payload")
    assert (store.state_dir / ".filekey").is_file()


def test_usable_keyring_backend_holds_master_key_no_filekey(
    store: CredentialStore, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = FakeKeyring()
    install_fake_keyring(monkeypatch, fake)
    store.write_state("ref_a", b"payload")
    assert not (store.state_dir / ".filekey").exists()  # keyring 可用：无文件密钥
    assert ("paper-crawler", "master-key") in fake.entries
    assert capsys.readouterr().err == ""  # 无降级警告
    # 新实例（同 keyring）可解密——主密钥持久于 keyring
    second = CredentialStore(store.auth_dir.parent)
    assert second.read_state("ref_a") == b"payload"


def test_keyring_master_key_corrupt_base64_raises_config(
    store: CredentialStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeKeyring()
    fake.entries[("paper-crawler", "master-key")] = "!!!not-base64!!!"
    install_fake_keyring(monkeypatch, fake)
    with pytest.raises(CrawlerError) as excinfo:
        store.write_state("ref_a", b"payload")
    assert excinfo.value.error_class is ErrorClass.CONFIG


def test_keyring_master_key_wrong_length_raises_config(
    store: CredentialStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    import base64

    fake = FakeKeyring()
    fake.entries[("paper-crawler", "master-key")] = base64.b64encode(b"short").decode()
    install_fake_keyring(monkeypatch, fake)
    with pytest.raises(CrawlerError) as excinfo:
        store.write_state("ref_a", b"payload")
    assert excinfo.value.error_class is ErrorClass.CONFIG
    assert "32" in str(excinfo.value)


def test_keyring_set_password_failure_degrades_without_half_state(
    store: CredentialStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeKeyring()

    def refuse(service: str, entry: str, value: str) -> None:
        raise RuntimeError("locked keychain")

    monkeypatch.setattr(fake, "set_password", refuse)
    install_fake_keyring(monkeypatch, fake)
    store.write_state("ref_a", b"payload")
    assert (store.state_dir / ".filekey").is_file()  # 存不进 keyring → 文件密钥兜底
    assert store.read_state("ref_a") == b"payload"


def test_filekey_corrupt_length_raises_config(store: CredentialStore) -> None:
    store._ensure_dirs()
    (store.state_dir / ".filekey").write_bytes(b"too-short")
    with pytest.raises(CrawlerError) as excinfo:
        store.write_state("ref_a", b"payload")
    assert excinfo.value.error_class is ErrorClass.CONFIG


# ---------------------------------------------------------------------------
# 惰性 import（安全断言 #9）：未装 [auth] 的报错文案；APIKey 路径零触碰加密
# ---------------------------------------------------------------------------


def test_missing_cryptography_raises_config_with_install_hint(
    store: CredentialStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(sys.modules, "cryptography", None)
    monkeypatch.setitem(sys.modules, "cryptography.hazmat.primitives.ciphers.aead", None)
    with pytest.raises(CrawlerError) as excinfo:
        store.write_state("ref_a", b"payload")
    assert excinfo.value.error_class is ErrorClass.CONFIG
    assert "pip install paper-crawler[auth]" in str(excinfo.value)
    # read 路径同样保护（文件在但依赖缺）
    store2 = CredentialStore(store.auth_dir.parent)
    store2._ensure_dirs()
    (store2.state_dir / "ref_b.enc").write_bytes(b"x" * 40)
    with pytest.raises(CrawlerError) as excinfo2:
        store2.read_state("ref_b")
    assert "pip install paper-crawler[auth]" in str(excinfo2.value)


def test_api_key_paths_never_touch_cryptography(
    store: CredentialStore, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """未装 [auth] 时 APIKey 全路径可用：key 读写/存在性/巡检/profiles 不触加密。"""

    def poisoned() -> object:
        raise AssertionError("cryptography must not be imported on api_key paths")

    monkeypatch.setattr(store_mod, "_import_aesgcm", poisoned)
    store.bind_config(make_config(home, elsevier_api_key="KEY-123"))
    assert store.has_key("elsevier_apikey") is True
    assert store.read_key("elsevier_apikey") == "KEY-123"
    store.delete_key("elsevier_apikey")
    store.write_meta("elsevier_apikey", {"backend": "bearer_token"})
    assert store.read_meta("elsevier_apikey") == {"backend": "bearer_token"}
    store.delete_meta("elsevier_apikey")
    assert store.load_profiles() == {}
    assert store.audit_permissions() == []


# ---------------------------------------------------------------------------
# read_key / has_key / delete_key / key_hint（安全断言 #8 + B-m6）
# ---------------------------------------------------------------------------


def test_read_key_prefers_keyring_then_config_slot(
    store: CredentialStore, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store.bind_config(make_config(home, elsevier_api_key="from-config"))
    assert store.read_key("elsevier_apikey") == "from-config"
    fake = FakeKeyring()
    fake.entries[("paper-crawler", "elsevier_apikey")] = "from-keyring"
    install_fake_keyring(monkeypatch, fake)
    assert store.read_key("elsevier_apikey") == "from-keyring"  # keyring 首选（可选加固层）


def test_read_key_all_config_slots_delegate(store: CredentialStore, home: Path) -> None:
    store.bind_config(
        make_config(
            home,
            elsevier_api_key="ek",
            elsevier_insttoken="it",
            wiley_tdm_token="wt",
        )
    )
    assert store.read_key("elsevier_apikey") == "ek"
    assert store.read_key("elsevier_insttoken") == "it"
    assert store.read_key("wiley_tdm_token") == "wt"


def test_read_key_unknown_ref_and_unset_slot_none(store: CredentialStore, home: Path) -> None:
    store.bind_config(make_config(home))
    assert store.read_key("elsevier_apikey") is None
    assert store.read_key("some_random_ref") is None
    assert store.has_key("elsevier_apikey") is False


def test_read_key_lazy_config_load_from_home(home: Path) -> None:
    """未 bind_config 时惰性 `Config.load(home)`（家目录 config.toml 槽委派）。"""
    home.mkdir(parents=True)
    (home / "config.toml").write_text('[auth.wiley]\ntoken = "tdm-uuid"\n', encoding="utf-8")
    assert CredentialStore(home).read_key("wiley_tdm_token") == "tdm-uuid"


def test_has_key_returns_strict_bool(store: CredentialStore, home: Path) -> None:
    store.bind_config(make_config(home, elsevier_api_key="value"))
    assert store.has_key("elsevier_apikey") is True  # 布尔判定，不向调用方暴露值


def test_delete_key_removes_keyring_copy_only(
    store: CredentialStore, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = make_config(home, elsevier_api_key="config-value")
    store.bind_config(config)
    fake = FakeKeyring()
    fake.entries[("paper-crawler", "elsevier_apikey")] = "keyring-copy"
    install_fake_keyring(monkeypatch, fake)
    store.delete_key("elsevier_apikey")
    assert ("paper-crawler", "elsevier_apikey") not in fake.entries
    assert store.read_key("elsevier_apikey") == "config-value"  # config 槽不动（B-m6）
    store.delete_key("elsevier_apikey")  # 再删：缺条目静默 no-op
    assert config.elsevier_api_key == "config-value"


def test_key_hint_names_slot_env_and_keyring(store: CredentialStore) -> None:
    hint = store.key_hint("elsevier_apikey")
    assert "[auth.elsevier].api_key" in hint
    assert "PAPER_CRAWLER_ELSEVIER_API_KEY" in hint
    assert "elsevier_apikey" in hint
    assert "keyring" in hint
    assert (
        store.key_hint("custom_ref") == "配置 keyring 条目 'custom_ref'（service='paper-crawler'）"
    )


# ---------------------------------------------------------------------------
# ref 防御：路径穿越/隐藏文件形态拒绝
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad_ref", ["../evil", "a/b", ".hidden", "", "a b", "..", "-lead"])
def test_illegal_refs_rejected(store: CredentialStore, bad_ref: str) -> None:
    with pytest.raises(CrawlerError) as excinfo:
        store.write_state(bad_ref, b"x")
    assert excinfo.value.error_class is ErrorClass.CONFIG
    with pytest.raises(CrawlerError):
        store.read_state(bad_ref)
    with pytest.raises(CrawlerError):
        store.read_key(bad_ref)


# ---------------------------------------------------------------------------
# meta sidecar（A-m2；安全断言 #10）：非密、合并写、凭证形态键拒写
# ---------------------------------------------------------------------------


def test_meta_roundtrip_merge_and_delete(store: CredentialStore) -> None:
    store.write_meta(
        "ref_a", {"backend": "httpx_cookies", "established_at": "2026-07-23T00:00:00+00:00"}
    )
    store.write_meta("ref_a", {"last_health": "ok"})
    assert store.read_meta("ref_a") == {
        "backend": "httpx_cookies",
        "established_at": "2026-07-23T00:00:00+00:00",
        "last_health": "ok",
    }
    store.delete_meta("ref_a")
    assert store.read_meta("ref_a") is None
    store.delete_meta("ref_a")  # 幂等


def test_meta_corrupt_json_reads_as_none(store: CredentialStore) -> None:
    store._ensure_dirs()
    (store.state_dir / "ref_a.meta.json").write_text("{not json", encoding="utf-8")
    assert store.read_meta("ref_a") is None
    (store.state_dir / "ref_a.meta.json").write_text('["list"]', encoding="utf-8")
    assert store.read_meta("ref_a") is None


@pytest.mark.parametrize("bad_key", ["cookie", "Set-Cookie", "api_key", "token", "insttoken"])
def test_meta_guard_rejects_credential_shaped_keys(store: CredentialStore, bad_key: str) -> None:
    with pytest.raises(CrawlerError) as excinfo:
        store.write_meta("ref_a", {bad_key: "anything"})
    assert excinfo.value.error_class is ErrorClass.CONFIG


def test_parse_meta_datetime_variants() -> None:
    aware = parse_meta_datetime("2026-07-23T10:00:00+00:00")
    assert aware == datetime(2026, 7, 23, 10, tzinfo=UTC)
    naive = parse_meta_datetime("2026-07-23T10:00:00")
    assert naive is not None and naive.tzinfo is UTC  # naive 归一 UTC
    assert parse_meta_datetime("not-a-date") is None
    assert parse_meta_datetime(None) is None
    assert parse_meta_datetime(123) is None


# ---------------------------------------------------------------------------
# clear_master_key_if_unused（AC-4.5 ⑤）
# ---------------------------------------------------------------------------


def test_clear_master_key_only_when_no_enc_left(
    store: CredentialStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    store.write_state("ref_a", b"a")
    store.write_state("ref_b", b"b")
    store.delete_state("ref_a")
    assert store.clear_master_key_if_unused() is False  # ref_b 仍在：不清
    assert (store.state_dir / ".filekey").is_file()
    store.delete_state("ref_b")
    assert store.clear_master_key_if_unused() is True
    assert not (store.state_dir / ".filekey").exists()


def test_clear_master_key_removes_keyring_entry(
    store: CredentialStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeKeyring()
    install_fake_keyring(monkeypatch, fake)
    store.write_state("ref_a", b"a")
    assert ("paper-crawler", "master-key") in fake.entries
    store.delete_state("ref_a")
    assert store.clear_master_key_if_unused() is True
    assert ("paper-crawler", "master-key") not in fake.entries


def test_clear_master_key_on_empty_store_is_true_noop(store: CredentialStore) -> None:
    assert store.clear_master_key_if_unused() is True  # 无目录/无 enc：幂等清理


# ---------------------------------------------------------------------------
# profiles.toml schema（安全断言 #12；§3.4）
# ---------------------------------------------------------------------------

VALID_PROFILES = """\
schema_version = 1

[providers.elsevier]
kind = "api_key"
platform = "elsevier_sd"
key_ref = "elsevier_apikey"
insttoken_ref = "elsevier_insttoken"
quota_probe = "https://api.elsevier.com/content/article/doi/10.1016/j.jfineco.2011.03.021"

[providers."oup@campus"]
kind = "cookie_session"
platform = "oup_silverchair"
login_url = "https://academic.oup.com/qje"
probe_url = "https://academic.oup.com/my-account"
state_ref = "oup_campus_state"
est_ttl_hours = 24

[providers."oup@shib"]
kind = "sso_flow"
platform = "oup_silverchair"
inst_login_url = "https://academic.oup.com/InstitutionalLogin"
wayf_hint = "My University"
probe_url = "https://academic.oup.com/my-account"
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


def write_profiles(store: CredentialStore, content: str) -> None:
    store.auth_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    store.profiles_path.write_text(content, encoding="utf-8")


def test_load_profiles_full_schema(store: CredentialStore) -> None:
    write_profiles(store, VALID_PROFILES)
    profiles = store.load_profiles()
    assert set(profiles) == {"elsevier", "oup@campus", "oup@shib", "elsevier@ezproxy"}
    elsevier = profiles["elsevier"]
    assert elsevier == ProviderProfile(
        provider_id="elsevier",
        kind="api_key",
        platform="elsevier_sd",
        key_ref="elsevier_apikey",
        insttoken_ref="elsevier_insttoken",
        quota_probe="https://api.elsevier.com/content/article/doi/10.1016/j.jfineco.2011.03.021",
    )
    campus = profiles["oup@campus"]
    assert campus.kind == "cookie_session"
    assert campus.login_url == "https://academic.oup.com/qje"
    assert campus.state_ref == "oup_campus_state"
    assert campus.est_ttl_hours == 24.0
    shib = profiles["oup@shib"]
    assert shib.kind == "sso_flow"
    assert shib.inst_login_url == "https://academic.oup.com/InstitutionalLogin"
    assert shib.wayf_hint == "My University"
    ezproxy = profiles["elsevier@ezproxy"]
    assert ezproxy.kind == "ezproxy"
    assert ezproxy.rewrite_suffix == ".login-myuniv-edu.ezproxy"
    assert ezproxy.proxy_base == "https://login.myuniv.edu/login?url="


def test_load_profiles_missing_file_empty(store: CredentialStore) -> None:
    assert store.load_profiles() == {}


def _expect_config_error(store: CredentialStore, content: str, needle: str) -> None:
    write_profiles(store, content)
    with pytest.raises(CrawlerError) as excinfo:
        store.load_profiles()
    assert excinfo.value.error_class is ErrorClass.CONFIG
    assert needle in str(excinfo.value)


def test_load_profiles_unknown_key_rejected(store: CredentialStore) -> None:
    _expect_config_error(
        store,
        '[providers.x]\nkind = "api_key"\nplatform = "p"\nkey_ref = "k"\nmystery = "v"\n',
        "mystery",
    )


def test_load_profiles_foreign_kind_key_rejected(store: CredentialStore) -> None:
    # kind×字段组合校验：api_key 带 cookie 类的 state_ref → 拒绝
    _expect_config_error(
        store,
        '[providers.x]\nkind = "api_key"\nplatform = "p"\nkey_ref = "k"\nstate_ref = "s"\n',
        "state_ref",
    )


@pytest.mark.parametrize(
    ("content", "needle"),
    [
        ('[providers.x]\nkind = "api_key"\nplatform = "p"\n', "key_ref"),
        ('[providers.x]\nkind = "cookie_session"\nplatform = "p"\nstate_ref = "s"\n', "login_url"),
        (
            '[providers.x]\nkind = "sso_flow"\nplatform = "p"\nstate_ref = "s"\n',
            "inst_login_url",
        ),
        (
            '[providers.x]\nkind = "ezproxy"\nplatform = "p"\nproxy_base = "b"\nstate_ref = "s"\n',
            "rewrite_suffix",
        ),
    ],
)
def test_load_profiles_kind_required_fields(
    store: CredentialStore, content: str, needle: str
) -> None:
    _expect_config_error(store, content, needle)


def test_load_profiles_bad_kind_rejected(store: CredentialStore) -> None:
    _expect_config_error(store, '[providers.x]\nkind = "magic"\nplatform = "p"\n', "kind")


def test_load_profiles_missing_platform_rejected(store: CredentialStore) -> None:
    _expect_config_error(store, '[providers.x]\nkind = "api_key"\nkey_ref = "k"\n', "platform")


def test_load_profiles_schema_version_guard(store: CredentialStore) -> None:
    _expect_config_error(store, "schema_version = 2\n", "schema_version")


def test_load_profiles_unknown_top_level_rejected(store: CredentialStore) -> None:
    _expect_config_error(
        store,
        'stray = 1\n[providers.x]\nkind = "api_key"\nplatform = "p"\nkey_ref = "k"\n',
        "stray",
    )


def test_load_profiles_non_table_provider_rejected(store: CredentialStore) -> None:
    _expect_config_error(store, "[providers]\nx = 1\n", "须为 TOML 表")


def test_load_profiles_non_table_providers_rejected(store: CredentialStore) -> None:
    _expect_config_error(store, "providers = 3\n", "providers 须为表")


@pytest.mark.parametrize(
    "ttl_line",
    ["est_ttl_hours = true", 'est_ttl_hours = "8"', "est_ttl_hours = -1", "est_ttl_hours = 0"],
)
def test_load_profiles_bad_ttl_rejected(store: CredentialStore, ttl_line: str) -> None:
    content = (
        '[providers.x]\nkind = "cookie_session"\nplatform = "p"\n'
        f'login_url = "u"\nstate_ref = "s"\n{ttl_line}\n'
    )
    _expect_config_error(store, content, "est_ttl_hours")


def test_load_profiles_empty_string_field_rejected(store: CredentialStore) -> None:
    _expect_config_error(
        store, '[providers.x]\nkind = "api_key"\nplatform = "p"\nkey_ref = "  "\n', "key_ref"
    )


# ---------------------------------------------------------------------------
# 覆盖补全：真实 `_import_keyring` 分支 / 零长覆写 / keyring 运行期故障分支
# ---------------------------------------------------------------------------

# 模块导入期捕获真实函数（autouse fixture 会替换 store_mod 上的引用；此处引用不受影响）。
_REAL_IMPORT_KEYRING = store_mod._import_keyring


def test_real_import_keyring_absent_returns_none(
    store: CredentialStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """真实 `_import_keyring`：import 失败 → None（降级链入口；#9 惰性）。"""
    monkeypatch.setattr(store_mod, "_import_keyring", _REAL_IMPORT_KEYRING)
    monkeypatch.setitem(sys.modules, "keyring", None)  # 毒化 → ImportError
    store.write_state("ref_a", b"payload")
    assert (store.state_dir / ".filekey").is_file()  # 走 filekey 降级


def test_real_import_keyring_present_returns_module(
    store: CredentialStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """真实 `_import_keyring`：import 成功 → 返回模块对象（fake 注入 sys.modules）。"""
    monkeypatch.setattr(store_mod, "_import_keyring", _REAL_IMPORT_KEYRING)
    fake = FakeKeyring()
    monkeypatch.setitem(sys.modules, "keyring", fake)  # type: ignore[arg-type]
    store.write_state("ref_a", b"payload")
    assert ("paper-crawler", "master-key") in fake.entries  # fake 被当作 keyring 模块使用
    assert not (store.state_dir / ".filekey").exists()


def test_forensic_unlink_zero_size_file(store: CredentialStore) -> None:
    store._ensure_dirs()
    empty = store.state_dir / "ref_a.enc"
    empty.touch()
    store.delete_state("ref_a")  # 零长文件：无覆写内容，直接 unlink，不抛错
    assert not empty.exists()


def test_keyring_get_password_raises_degrades(
    store: CredentialStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeKeyring()

    def broken(service: str, entry: str) -> str | None:
        raise RuntimeError("keychain locked")

    monkeypatch.setattr(fake, "get_password", broken)
    install_fake_keyring(monkeypatch, fake)
    store.write_state("ref_a", b"payload")
    assert (store.state_dir / ".filekey").is_file()  # get 故障 → 降级文件密钥


def test_keyring_entry_read_get_keyring_raises_falls_to_config(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = CredentialStore(home)
    store.bind_config(make_config(home, elsevier_api_key="cfg"))

    def boom() -> object:
        raise RuntimeError("no backend")

    install_fake_keyring(monkeypatch, SimpleNamespace(get_keyring=boom))
    assert store.read_key("elsevier_apikey") == "cfg"  # keyring 探测崩溃 → config 委派


def test_delete_key_dead_backend_is_noop(
    store: CredentialStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeKeyring(backend_module="keyring.backends.fail")
    fake.entries[("paper-crawler", "elsevier_apikey")] = "x"
    install_fake_keyring(monkeypatch, fake)
    store.delete_key("elsevier_apikey")  # 死后端：静默 no-op（不抛不删）
    assert ("paper-crawler", "elsevier_apikey") in fake.entries


def test_delete_key_get_keyring_raises_is_noop(
    store: CredentialStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom() -> object:
        raise RuntimeError("no backend")

    install_fake_keyring(monkeypatch, SimpleNamespace(get_keyring=boom))
    store.delete_key("elsevier_apikey")  # 探测崩溃：静默 no-op


def test_keyring_entry_dead_backend_falls_to_config(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = CredentialStore(home)
    store.bind_config(make_config(home, elsevier_api_key="cfg"))
    fake = FakeKeyring(backend_module="keyring.backends.null")
    fake.entries[("paper-crawler", "elsevier_apikey")] = "never-read"
    install_fake_keyring(monkeypatch, fake)
    assert store.read_key("elsevier_apikey") == "cfg"  # 死后端条目不读 → config 委派
