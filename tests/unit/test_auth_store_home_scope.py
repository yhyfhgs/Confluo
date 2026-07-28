"""主密钥 keyring 条目的 config-home 维度隔离（修复批 R1a / P0-5）。

**缺陷（修复前）**：`master-key` 条目在 keyring 里**全局唯一**，无 config-home 维度；
`clear_master_key_if_unused()`（`AuthManager.logout` 有状态类收尾 ⑤，manager.py:179-180）
的"是否还有人在用"判据只看**本 home** 的 `state/*.enc`——于是任一 home（哪怕是一份凭证
都没有的测试/隔离 home）执行 logout，都会删掉所有 home 共用的那一条主密钥，B home 的
`state/*.enc` 就此**永久不可解**（文件还在，`read_state` 抛 `AuthRequired`）。

**修复后不变式**（本文件逐条锁定）：

1. 条目名带 home 指纹 `master-key@<sha256(resolve(home))[:12]>`——A home 的 clear 只
   删自己那条，B home 的主密钥与密文不受影响；
2. **向后兼容迁移**：旧名裸条目 `master-key`（修复前版本写入）只读不删——命中即**复制**
   到本 home 新名，既有密文继续可解；此后本 home 一律走新名；
3. `clear_master_key_if_unused` 只删本 home 指纹的新名条目，**永不触碰旧名裸条目**
   （其它 home 可能仍依赖它——跨 home 安全 > 彻底清理）。

零真实 keyring（`_import_keyring` 恒被替换，绝不触宿主 Keychain）、零网络。
"""

import base64
import hashlib
import os
from pathlib import Path

import pytest

import paper_crawler.auth.store as store_mod
from helpers.auth import FakeKeyring, install_fake_keyring
from paper_crawler.auth.store import CredentialStore
from paper_crawler.errors import CrawlerError, ErrorClass

_SERVICE = "paper-crawler"
_LEGACY_ENTRY = "master-key"  # 修复前的全局唯一裸条目名


@pytest.fixture(autouse=True)
def _isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """keyring 绝缘（默认无后端）+ 一次性降级警告旗标复位 + cwd 隔离。"""
    monkeypatch.setattr(store_mod, "_import_keyring", lambda: None)
    monkeypatch.setattr(store_mod, "_filekey_warned", True)  # 本文件不断言降级文案
    monkeypatch.delenv("PAPER_CRAWLER_HOME", raising=False)
    workdir = tmp_path / "cwd"
    workdir.mkdir(exist_ok=True)
    monkeypatch.chdir(workdir)


def _b64_key() -> str:
    return base64.b64encode(os.urandom(32)).decode("ascii")


# ---------------------------------------------------------------------------
# ①条目按 home 指纹分名（P0-5 主回归）
# ---------------------------------------------------------------------------


def test_clear_in_one_home_never_breaks_another_home_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P0-5 回归：A home 的 logout 收尾绝不使 B home 的既有密文失效（修复前必失败）。"""
    fake = FakeKeyring()  # 单一"系统 keyring"，两 home 共用
    install_fake_keyring(monkeypatch, fake)
    home_a, home_b = tmp_path / "homeA", tmp_path / "homeB"

    store_b = CredentialStore(home_b)
    store_b.write_state("oup_campus_state", b"SECRET-STATE-B")

    # A home 一份凭证都没有（state_dir 尚未建）——logout 收尾照样调 clear（manager.py:180）
    store_a = CredentialStore(home_a)
    assert not store_a.state_dir.is_dir()
    assert store_a.clear_master_key_if_unused() is True

    # "新进程"口径：B home 重开仍可解密（修复前此处 AuthRequired——主密钥已被 A 删）
    assert CredentialStore(home_b).read_state("oup_campus_state") == b"SECRET-STATE-B"
    assert (store_b.state_dir / "oup_campus_state.enc").is_file()


def test_two_homes_hold_independent_master_key_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """两 home 各持一条主密钥条目（互不覆盖），各自密文各自可解。"""
    fake = FakeKeyring()
    install_fake_keyring(monkeypatch, fake)
    home_a, home_b = tmp_path / "homeA", tmp_path / "homeB"
    store_a, store_b = CredentialStore(home_a), CredentialStore(home_b)
    store_a.write_state("ref_a", b"payload-a")
    store_b.write_state("ref_b", b"payload-b")

    entry_a, entry_b = store_a._master_key_entry(), store_b._master_key_entry()
    assert entry_a != entry_b
    assert sorted(fake.entries) == sorted([(_SERVICE, entry_a), (_SERVICE, entry_b)])
    assert fake.entries[(_SERVICE, entry_a)] != fake.entries[(_SERVICE, entry_b)]
    assert CredentialStore(home_a).read_state("ref_a") == b"payload-a"
    assert CredentialStore(home_b).read_state("ref_b") == b"payload-b"


def test_master_key_entry_carries_resolved_home_fingerprint(tmp_path: Path) -> None:
    """条目名 = `master-key@<sha256(绝对 resolve 后路径)[:12]>`；等价路径写法指纹一致。"""
    home = tmp_path / "homeA"
    home.mkdir()
    expected = hashlib.sha256(str(home.resolve()).encode("utf-8")).hexdigest()[:12]
    entry = CredentialStore(home)._master_key_entry()
    assert entry == f"{_LEGACY_ENTRY}@{expected}"
    assert len(expected) == 12
    # 同一 home 的非规范写法（含 `..` 段）→ resolve 后同一指纹（方案 §1"绝对路径 resolve 后"）
    assert CredentialStore(tmp_path / "sub" / ".." / "homeA")._master_key_entry() == entry
    assert CredentialStore(tmp_path / "homeB")._master_key_entry() != entry
    # 条目名须过 ref 白名单（`delete_key` 内 `_checked_ref` 复用同一正则）
    assert store_mod._REF_RE.fullmatch(entry) is not None


# ---------------------------------------------------------------------------
# ②旧名裸条目迁移：复制不搬移，此后走新名
# ---------------------------------------------------------------------------


def test_legacy_bare_entry_is_copied_to_home_entry_never_deleted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeKeyring()
    legacy_value = _b64_key()
    fake.entries[(_SERVICE, _LEGACY_ENTRY)] = legacy_value
    install_fake_keyring(monkeypatch, fake)

    home = tmp_path / "home"
    store = CredentialStore(home)
    store.write_state("ref_a", b"payload")  # 新名 miss → 查旧名命中 → 复制到新名
    entry = store._master_key_entry()
    assert fake.entries[(_SERVICE, entry)] == legacy_value  # 值原样复制（既有密文可解）
    assert fake.entries[(_SERVICE, _LEGACY_ENTRY)] == legacy_value  # 旧名裸条目绝不删
    assert not (store.state_dir / ".filekey").exists()  # keyring 路径：不降级文件密钥

    # 新实例（"新进程"）可解密，且不再回读旧名——此后本 home 一律走新名
    fresh = CredentialStore(home)
    fake.get_password_calls.clear()
    assert fresh.read_state("ref_a") == b"payload"
    assert (_SERVICE, _LEGACY_ENTRY) not in fake.get_password_calls
    assert (_SERVICE, entry) in fake.get_password_calls


def test_legacy_migration_write_failure_still_serves_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """迁移复制写失败 → 仍用旧名密钥（值未丢：旧条目还在，下次再迁），不降级不失效。"""
    fake = FakeKeyring()
    legacy_value = _b64_key()
    fake.entries[(_SERVICE, _LEGACY_ENTRY)] = legacy_value

    def refuse(service: str, entry: str, value: str) -> None:
        raise RuntimeError("locked keychain")

    monkeypatch.setattr(fake, "set_password", refuse)
    install_fake_keyring(monkeypatch, fake)

    store = CredentialStore(tmp_path / "home")
    store.write_state("ref_a", b"payload")
    assert store.read_state("ref_a") == b"payload"
    assert not (store.state_dir / ".filekey").exists()  # 未降级：主密钥仍是旧名那把
    assert fake.entries[(_SERVICE, _LEGACY_ENTRY)] == legacy_value


def test_legacy_lookup_backend_failure_degrades_to_filekey(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """旧名回查触后端运行期故障 → 按 §3.3 降级文件密钥（不半途而废、不抛给调用方）。"""
    fake = FakeKeyring()

    def flaky(service: str, entry: str) -> str | None:
        if entry == _LEGACY_ENTRY:
            raise RuntimeError("keychain locked")
        return None

    monkeypatch.setattr(fake, "get_password", flaky)
    install_fake_keyring(monkeypatch, fake)

    store = CredentialStore(tmp_path / "home")
    store.write_state("ref_a", b"payload")
    assert (store.state_dir / ".filekey").is_file()
    assert fake.entries == {}  # 迁移未成 → 不写新名条目


def test_corrupt_legacy_entry_error_names_legacy_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """旧名条目损坏 → CONFIG 报错指名**旧名**（用户按提示清理的正是那一条）。"""
    fake = FakeKeyring()
    fake.entries[(_SERVICE, _LEGACY_ENTRY)] = "!!!not-base64!!!"
    install_fake_keyring(monkeypatch, fake)
    store = CredentialStore(tmp_path / "home")
    with pytest.raises(CrawlerError) as excinfo:
        store.write_state("ref_a", b"payload")
    assert excinfo.value.error_class is ErrorClass.CONFIG
    assert f"{_SERVICE}/{_LEGACY_ENTRY}" in str(excinfo.value)


def test_corrupt_home_entry_error_names_home_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """新名条目长度非法 → CONFIG 报错指名**本 home 新名条目**（旧名不背锅）。"""
    fake = FakeKeyring()
    home = tmp_path / "home"
    entry = CredentialStore(home)._master_key_entry()
    fake.entries[(_SERVICE, entry)] = base64.b64encode(b"short").decode("ascii")
    install_fake_keyring(monkeypatch, fake)
    with pytest.raises(CrawlerError) as excinfo:
        CredentialStore(home).write_state("ref_a", b"payload")
    assert excinfo.value.error_class is ErrorClass.CONFIG
    assert f"{_SERVICE}/{entry}" in str(excinfo.value)


# ---------------------------------------------------------------------------
# ③clear 语义：只删本 home 新名条目，旧名裸条目刻意保留
# ---------------------------------------------------------------------------


def test_clear_master_key_deletes_home_entry_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeKeyring()
    legacy_value = _b64_key()
    fake.entries[(_SERVICE, _LEGACY_ENTRY)] = legacy_value
    install_fake_keyring(monkeypatch, fake)

    home = tmp_path / "home"
    store = CredentialStore(home)
    store.write_state("ref_a", b"payload")
    entry = store._master_key_entry()
    assert (_SERVICE, entry) in fake.entries

    store.delete_state("ref_a")  # 本 home 最后一份 .enc 删除
    assert store.clear_master_key_if_unused() is True
    assert (_SERVICE, entry) not in fake.entries  # 本 home 新名条目：清
    assert fake.entries[(_SERVICE, _LEGACY_ENTRY)] == legacy_value  # 旧名裸条目：留


def test_clear_keeps_other_home_entry_intact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeKeyring()
    install_fake_keyring(monkeypatch, fake)
    home_a, home_b = tmp_path / "homeA", tmp_path / "homeB"
    store_a, store_b = CredentialStore(home_a), CredentialStore(home_b)
    store_a.write_state("ref_a", b"a")
    store_b.write_state("ref_b", b"b")

    store_a.delete_state("ref_a")
    assert store_a.clear_master_key_if_unused() is True
    assert (_SERVICE, store_a._master_key_entry()) not in fake.entries
    assert (_SERVICE, store_b._master_key_entry()) in fake.entries
    assert CredentialStore(home_b).read_state("ref_b") == b"b"
