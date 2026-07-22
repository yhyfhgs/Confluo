"""凭证库 `CredentialStore`（auth-framework §2.3 冻结签名 + §3 全节落地；T1b）。

两级凭证模型（D-023 / auth-framework §3.4）：

- **①简单字符串密钥**（elsevier api_key/insttoken、wiley TDM token）：`read_key(ref)`
  统一取——keyring 条目（可选加固层）首选，缺则**委派 Config 字段**（`[auth.<platform>]`
  Config-slot，家目录 config + env 覆盖）。该路径**不触加密依赖**（AC-4.1 轻路径）。
- **②有状态凭证**（storage_state / cookie jar）：`read_state`/`write_state` AES-256-GCM
  加解密落 `state/<ref>.enc`（0600），主密钥经 keyring→文件密钥降级链（§3.3）。

安全强制（§3.2/§3.3/§3.5，AC-0.3/AC-4.5）：

- **每次加密调用新随机 12B nonce**（A-m1；GCM nonce 复用即灾难性失密），nonce 前置于
  密文；AAD = 条目 ref（防跨条目重放——把 a.enc 拷成 b.enc 解密必败）。主密钥 32B。
- keyring 不可用（ImportError / NoKeyringError / fail·null 后端）→ 降级 `state/.filekey`
  （0600）+ **每进程仅一次**显式警告（obslog WARNING + stderr，§3.3 文案逐字）。
- `write_state`/`.filekey` 用 `os.open(..., O_WRONLY|O_CREAT|O_TRUNC, 0o600)` 原子创建
  （无 chmod 竞态窗）；`auth/`、`auth/state/` 目录 mkdir mode=0700。启动巡检
  （`audit_permissions`，AuthManager 调用）非 0600/0700 → WARNING **不自动改**。
- `delete_state`：随机字节覆写后 unlink（AC-4.5 取证式）；缺失静默 no-op。
- `state/<ref>.meta.json` 为**非密** sidecar（A-m2：backend/established_at/last_health/
  est_ttl_hours）——`auth status` 只读渲染，不含任何 cookie/token（写入前键名护栏拦截）。

惰性 import：`cryptography`/`keyring` 仅在加密/keyring 路径 import（未装 `[auth]` 时
纯 APIKey 全路径可用；需加密路径抛 `CrawlerError(CONFIG, "pip install paper-crawler[auth]")`）。

目录创建注记：§3.1 原文"目录随 `Config.ensure_dirs()` 扩展创建"——config.py 归 T2 独占
（T1b 零触碰），故本 store 在写路径自管 `mkdir(mode=0o700)`（等价结果，见终报偏离项）。
"""

import base64
import json
import os
import re
import stat
import sys
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, cast, get_args

from paper_crawler.auth.protocol import ProviderKind
from paper_crawler.config import Config
from paper_crawler.errors import AuthRequired, CrawlerError, ErrorClass
from paper_crawler.obslog import log_event
from paper_crawler.sensitive import REDACT_KEY_PATTERN

if TYPE_CHECKING:  # 惰性依赖仅作类型（运行时经 _import_aesgcm 按需加载）
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_PROFILES_NAME = "profiles.toml"
_FILEKEY_NAME = ".filekey"
_KEYRING_SERVICE = "paper-crawler"
_MASTER_KEY_ENTRY = "master-key"
_NONCE_LEN = 12  # AES-GCM 标准 96-bit nonce（§3.2 冻结参数）
_MASTER_KEY_LEN = 32  # AES-256（§3.2 冻结参数）

_INSTALL_AUTH_HINT = "pip install paper-crawler[auth]"

# §3.3 降级警告文案（逐字；测试断言原文）。
_FILEKEY_WARNING = (
    "⚠ 系统无可用 keyring 后端；认证主密钥降级为文件密钥 state/.filekey（0600）。"
    "该文件泄漏等价 session 泄漏——确保 config-home 目录访问受控（AGENTS §6.4）。"
)
_filekey_warned = False  # 每进程仅一次（§3.3"缓存标志"）

# ref → 文件名（state/<ref>.enc 等）：拒绝路径穿越/隐藏文件形态（防御纵深）。
_REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._@-]*$")

# meta sidecar 键名护栏：sidecar 是非密文件，凭证形态键一律拒写（A-m2/AC-0.4 纵深）。
_META_FORBIDDEN_KEY_RE = re.compile(rf"\b({REDACT_KEY_PATTERN})\b", re.IGNORECASE)

# ①类简单串密钥的 Config 委派表（auth-framework §3.4 两级凭证模型）：
# key_ref → (Config 字段名, config.toml 槽位, 环境变量)。
_CONFIG_KEY_SLOTS: dict[str, tuple[str, str, str]] = {
    "elsevier_apikey": (
        "elsevier_api_key",
        "[auth.elsevier].api_key",
        "PAPER_CRAWLER_ELSEVIER_API_KEY",
    ),
    "elsevier_insttoken": (
        "elsevier_insttoken",
        "[auth.elsevier].insttoken",
        "PAPER_CRAWLER_ELSEVIER_INSTTOKEN",
    ),
    "wiley_tdm_token": (
        "wiley_tdm_token",
        "[auth.wiley].token",
        "PAPER_CRAWLER_WILEY_TDM_TOKEN",
    ),
}


def _import_aesgcm() -> "type[AESGCM]":
    """惰性取 `cryptography.AESGCM`；未装 `[auth]` → CrawlerError(CONFIG)（§3.2）。"""
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError as exc:
        raise CrawlerError(
            ErrorClass.CONFIG,
            f"凭证库加密路径需要可选依赖：{_INSTALL_AUTH_HINT}",
            detail="cookie/SSO 类 storage_state 走 AES-GCM；纯 APIKey 路径不需要本依赖",
        ) from exc
    return AESGCM


def _import_keyring() -> ModuleType | None:
    """惰性取 keyring 模块；未装 → None（进入 §3.3 降级链，不抛错）。"""
    try:
        import keyring
    except ImportError:
        return None
    return keyring


def _is_usable_backend(backend: object) -> bool:
    """`keyring.get_keyring()` 的 fail/null 后端 = 无可用后端（§3.3 降级判定点）。"""
    module = type(backend).__module__
    return not module.startswith(("keyring.backends.fail", "keyring.backends.null"))


def _warn_filekey_downgrade_once() -> None:
    """降级警告：obslog WARNING + stderr，每进程仅一次（§3.3）。"""
    global _filekey_warned
    if _filekey_warned:
        return
    _filekey_warned = True
    log_event("WARNING", _FILEKEY_WARNING)
    print(_FILEKEY_WARNING, file=sys.stderr)


def _write_private_file(path: Path, data: bytes) -> None:
    """0600 原子创建写（§3.5：O_CREAT 即带权限，无"先建后 chmod"竞态窗）。"""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, data)
    finally:
        os.close(fd)


def _forensic_unlink(path: Path) -> None:
    """取证式删除（AC-4.5）：等长随机字节覆写 + fsync 后 unlink；缺失静默 no-op。"""
    if not path.is_file():
        return
    size = path.stat().st_size
    fd = os.open(path, os.O_WRONLY)
    try:
        if size:
            os.write(fd, os.urandom(size))
        os.fsync(fd)
    finally:
        os.close(fd)
    path.unlink()


def parse_meta_datetime(value: object) -> datetime | None:
    """meta sidecar 的 ISO 时间戳 → aware datetime；非法/缺失 → None（只读渲染容错）。"""
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


# ---------------------------------------------------------------------------
# profiles.toml schema（auth-framework §3.4；严格拒未知键 + kind×必填组合校验）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProviderProfile:
    """`profiles.toml` 一个 provider 条目的解析产物（无任何密钥明文——只存引用名）。"""

    provider_id: str
    kind: ProviderKind
    platform: str
    key_ref: str | None = None
    insttoken_ref: str | None = None
    quota_probe: str | None = None
    login_url: str | None = None
    inst_login_url: str | None = None
    wayf_hint: str | None = None
    probe_url: str | None = None
    state_ref: str | None = None
    proxy_base: str | None = None
    rewrite_suffix: str | None = None
    est_ttl_hours: float | None = None


# 每 kind 的字段表：{键: 是否必填}（§3.4 schema 全键；kind/platform 为公共必填）。
_KIND_FIELDS: dict[str, dict[str, bool]] = {
    "api_key": {"key_ref": True, "insttoken_ref": False, "quota_probe": False},
    "cookie_session": {
        "login_url": True,
        "probe_url": False,
        "state_ref": True,
        "est_ttl_hours": False,
    },
    "sso_flow": {
        "inst_login_url": True,
        "wayf_hint": False,
        "probe_url": False,
        "state_ref": True,
        "est_ttl_hours": False,
    },
    "ezproxy": {
        "proxy_base": True,
        "rewrite_suffix": True,
        "state_ref": True,
        "est_ttl_hours": False,
    },
}
_PROVIDER_KINDS: tuple[str, ...] = get_args(ProviderKind)


def _profile_error(provider_id: str, message: str) -> CrawlerError:
    return CrawlerError(
        ErrorClass.CONFIG,
        f"profiles.toml provider {provider_id!r} 非法：{message}",
        detail=provider_id,
    )


def _parse_ttl_hours(provider_id: str, raw: object) -> float:
    """est_ttl_hours：数值（int/float）；bool 显式拒绝（True→1.0 意外，同 config 口径）。"""
    if isinstance(raw, bool) or not isinstance(raw, int | float):
        raise _profile_error(provider_id, f"est_ttl_hours 须为数值，得到 {type(raw).__name__}")
    value = float(raw)
    if value <= 0:
        raise _profile_error(provider_id, "est_ttl_hours 须为正数")
    return value


def _parse_profile(provider_id: str, entry: object) -> ProviderProfile:
    if not isinstance(entry, dict):
        raise _profile_error(provider_id, "须为 TOML 表（[providers.<id>]）")
    kind_raw = entry.get("kind")
    if kind_raw not in _PROVIDER_KINDS:
        raise _profile_error(
            provider_id, f"kind 须为 {'/'.join(_PROVIDER_KINDS)} 之一，得到 {kind_raw!r}"
        )
    fields = _KIND_FIELDS[str(kind_raw)]
    allowed = {"kind", "platform", *fields}
    unknown = sorted(set(map(str, entry)) - allowed)
    if unknown:
        # 严格拒未知键（§3.4，仿 VenueSpec extra="forbid"）——含"他 kind 的合法键"
        # （如 api_key 带 state_ref）：kind×字段组合同样在此拦截。
        raise _profile_error(provider_id, f"未知键 {', '.join(unknown)}（kind={kind_raw}）")
    values: dict[str, object] = {}
    for field, required in fields.items():
        raw = entry.get(field)
        if raw is None:
            if required:
                raise _profile_error(provider_id, f"kind={kind_raw} 缺必填键 {field}")
            continue
        if field == "est_ttl_hours":
            values[field] = _parse_ttl_hours(provider_id, raw)
        elif not isinstance(raw, str) or not raw.strip():
            raise _profile_error(provider_id, f"{field} 须为非空字符串")
        else:
            values[field] = raw.strip()
    platform = entry.get("platform")
    if not isinstance(platform, str) or not platform.strip():
        raise _profile_error(provider_id, "缺必填键 platform（须为非空字符串）")

    def _s(field: str) -> str | None:
        value = values.get(field)
        return value if isinstance(value, str) else None

    ttl_raw = values.get("est_ttl_hours")
    return ProviderProfile(
        provider_id=provider_id,
        kind=cast(ProviderKind, kind_raw),  # 上方成员校验已收窄
        platform=platform.strip(),
        key_ref=_s("key_ref"),
        insttoken_ref=_s("insttoken_ref"),
        quota_probe=_s("quota_probe"),
        login_url=_s("login_url"),
        inst_login_url=_s("inst_login_url"),
        wayf_hint=_s("wayf_hint"),
        probe_url=_s("probe_url"),
        state_ref=_s("state_ref"),
        proxy_base=_s("proxy_base"),
        rewrite_suffix=_s("rewrite_suffix"),
        est_ttl_hours=ttl_raw if isinstance(ttl_raw, float) else None,
    )


# ---------------------------------------------------------------------------
# CredentialStore（§2.3 冻结签名 + 纯附加辅助面）
# ---------------------------------------------------------------------------


class CredentialStore:
    """凭证库（冻结六方法 `read_state/write_state/delete_state/read_key/has_key/
    load_profiles` + 纯附加辅助面：meta sidecar、keyring 条目删除、权限巡检等）。"""

    def __init__(self, home: Path) -> None:
        self._home = home
        self.auth_dir = home / "auth"
        self.state_dir = self.auth_dir / "state"
        self._config: Config | None = None
        self._master_key: bytes | None = None

    # -- 装配 -----------------------------------------------------------------

    def bind_config(self, config: Config) -> None:
        """注入已加载 `Config`（`read_key` ①类简单串的委派源；避免重复 `Config.load`）。"""
        self._config = config

    @property
    def profiles_path(self) -> Path:
        return self.auth_dir / _PROFILES_NAME

    def _config_lazy(self) -> Config:
        if self._config is None:
            self._config = Config.load(self._home)
        return self._config

    def _ensure_dirs(self) -> None:
        """`auth/`、`auth/state/` mkdir mode=0700（§3.5；仅写路径调用，读路径不建目录）。"""
        self.auth_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.state_dir.mkdir(mode=0o700, exist_ok=True)

    def _checked_ref(self, ref: str) -> str:
        if not _REF_RE.fullmatch(ref):
            raise CrawlerError(
                ErrorClass.CONFIG,
                f"非法凭证条目 ref: {ref!r}（仅限字母数字与 ._@-，不得以点号开头）",
            )
        return ref

    def _state_path(self, ref: str) -> Path:
        return self.state_dir / f"{self._checked_ref(ref)}.enc"

    def _meta_path(self, ref: str) -> Path:
        return self.state_dir / f"{self._checked_ref(ref)}.meta.json"

    # -- 主密钥（§3.3 降级链） -------------------------------------------------

    def _master_key_from_keyring(self) -> bytes | None:
        """keyring 主密钥：取/首次生成存入；后端不可用/读写失败 → None（降级）。"""
        keyring = _import_keyring()
        if keyring is None:
            return None
        try:
            backend = keyring.get_keyring()
        except Exception:  # NoKeyringError 及后端探测异常一律按无后端降级（§3.3）
            return None
        if not _is_usable_backend(backend):
            return None
        try:
            raw = keyring.get_password(_KEYRING_SERVICE, _MASTER_KEY_ENTRY)
        except Exception:  # 后端运行期故障（锁定/拒权）→ 降级，不半途而废
            return None
        if raw is None:
            key = os.urandom(_MASTER_KEY_LEN)
            encoded = base64.b64encode(key).decode("ascii")
            try:
                keyring.set_password(_KEYRING_SERVICE, _MASTER_KEY_ENTRY, encoded)
            except Exception:  # 存不进 keyring → 弃用该密钥并降级（不留半程状态）
                return None
            return key
        try:
            key = base64.b64decode(raw.encode("ascii"), validate=True)
        except ValueError as exc:
            raise CrawlerError(
                ErrorClass.CONFIG,
                "keyring 主密钥条目损坏（非 base64）——清理 keyring 条目 "
                f"'{_KEYRING_SERVICE}/{_MASTER_KEY_ENTRY}' 后重新 auth login",
            ) from exc
        if len(key) != _MASTER_KEY_LEN:
            raise CrawlerError(
                ErrorClass.CONFIG,
                f"keyring 主密钥长度非 {_MASTER_KEY_LEN}B——清理 keyring 条目 "
                f"'{_KEYRING_SERVICE}/{_MASTER_KEY_ENTRY}' 后重新 auth login",
            )
        return key

    def _filekey(self) -> bytes:
        """降级路径文件主密钥：`state/.filekey`（0600；已有则复用，保持既有密文可解）。"""
        path = self.state_dir / _FILEKEY_NAME
        if path.is_file():
            key = path.read_bytes()
            if len(key) != _MASTER_KEY_LEN:
                raise CrawlerError(
                    ErrorClass.CONFIG,
                    f"state/.filekey 主密钥长度非 {_MASTER_KEY_LEN}B（文件损坏）——"
                    "删除后重新 auth login（既有加密 state 将不可解）",
                )
            return key
        self._ensure_dirs()
        key = os.urandom(_MASTER_KEY_LEN)
        _write_private_file(path, key)
        return key

    def _resolve_master_key(self) -> bytes:
        """keyring 首选 → 文件密钥降级 + 一次性显式警告（§3.3）；进程内缓存。"""
        if self._master_key is None:
            key = self._master_key_from_keyring()
            if key is None:
                key = self._filekey()
                _warn_filekey_downgrade_once()
            self._master_key = key
        return self._master_key

    # -- 加密状态（②有状态凭证；§2.3 冻结签名） --------------------------------

    def read_state(self, ref: str) -> bytes:
        """解密取 `state/<ref>.enc`；缺失 → `AuthRequired`（§2.3）。"""
        path = self._state_path(ref)
        if not path.is_file():
            raise AuthRequired(
                f"no stored auth state for {ref!r}",
                detail=f"缺 state/{ref}.enc——先执行 crawler auth login",
            )
        blob = path.read_bytes()
        if len(blob) <= _NONCE_LEN:
            raise AuthRequired(
                f"auth state for {ref!r} is corrupt",
                detail="state 文件过短（非 nonce+密文布局）——crawler auth login 重登",
            )
        aesgcm_cls = _import_aesgcm()
        key = self._resolve_master_key()
        nonce, ciphertext = blob[:_NONCE_LEN], blob[_NONCE_LEN:]
        try:
            return aesgcm_cls(key).decrypt(nonce, ciphertext, ref.encode("utf-8"))
        except Exception as exc:  # InvalidTag：篡改/跨条目重放（AAD 不符）/主密钥更换
            raise AuthRequired(
                f"auth state for {ref!r} cannot be decrypted",
                detail="密文校验失败（篡改/跨条目拷贝/密钥更换）——crawler auth login 重登",
            ) from exc

    def write_state(self, ref: str, data: bytes) -> None:
        """AES-256-GCM 加密落盘 `state/<ref>.enc`（0600 原子创建；每次新随机 nonce）。"""
        path = self._state_path(ref)  # ref 校验先行（非法 ref 不触加密依赖）
        aesgcm_cls = _import_aesgcm()  # 未装 [auth] → 此处即抛，不留半程文件
        key = self._resolve_master_key()
        nonce = os.urandom(_NONCE_LEN)  # A-m1：每次加密调用新随机 nonce，绝不复用
        blob = nonce + aesgcm_cls(key).encrypt(nonce, data, ref.encode("utf-8"))
        self._ensure_dirs()
        _write_private_file(path, blob)

    def delete_state(self, ref: str) -> None:
        """覆写后 unlink（AC-4.5 取证式）；连带非密 meta sidecar；缺失静默 no-op。"""
        _forensic_unlink(self._state_path(ref))
        meta = self._meta_path(ref)
        if meta.is_file():
            meta.unlink()

    def has_state(self, ref: str) -> bool:
        """state 存在性预检（不解密不取值；provider ensure_session 用）。"""
        return self._state_path(ref).is_file()

    # -- meta sidecar（A-m2：非密，`auth status` 只读渲染源） -------------------

    def read_meta(self, ref: str) -> dict[str, object] | None:
        path = self._meta_path(ref)
        if not path.is_file():
            return None
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return loaded if isinstance(loaded, dict) else None

    def write_meta(self, ref: str, updates: Mapping[str, object]) -> None:
        """合并写 sidecar。键名护栏：凭证形态键（cookie/token/…）一律拒写（非密不变式）。"""
        for key in updates:
            if _META_FORBIDDEN_KEY_RE.search(key):
                raise CrawlerError(
                    ErrorClass.CONFIG,
                    f"meta sidecar 禁写凭证形态键 {key!r}（sidecar 为非密文件，A-m2）",
                )
        merged = self.read_meta(ref) or {}
        merged.update(updates)
        self._ensure_dirs()
        self._meta_path(ref).write_text(
            json.dumps(merged, ensure_ascii=False, sort_keys=True), encoding="utf-8"
        )

    def delete_meta(self, ref: str) -> None:
        """删除 sidecar（api_key 类 logout 用——无 state 但可能有工具管理的 meta）。"""
        path = self._meta_path(ref)
        if path.is_file():
            path.unlink()

    # -- 密钥类凭证（①简单字符串；§2.3 冻结签名） ------------------------------

    def _keyring_entry(self, entry: str) -> str | None:
        keyring = _import_keyring()
        if keyring is None:
            return None
        try:
            backend = keyring.get_keyring()
            if not _is_usable_backend(backend):
                return None
            value = keyring.get_password(_KEYRING_SERVICE, entry)
        except Exception:  # 后端不可用/运行期故障 → 视为无条目（降级到 config）
            return None
        return value if isinstance(value, str) and value.strip() else None

    def read_key(self, ref: str) -> str | None:
        """keyring 条目（首选，可选加固层）→ Config 字段委派（①类简单串）；缺 → None。"""
        value = self._keyring_entry(self._checked_ref(ref))
        if value is not None:
            return value
        slot = _CONFIG_KEY_SLOTS.get(ref)
        if slot is None:
            return None
        config_value = getattr(self._config_lazy(), slot[0])
        return config_value if isinstance(config_value, str) and config_value else None

    def has_key(self, ref: str) -> bool:
        """ensure_session 的存在性预检（§2.3：布尔判定，不向调用方暴露值）。"""
        return self.read_key(ref) is not None

    def delete_key(self, ref: str) -> None:
        """删除 keyring 中的密钥条目副本（B-m6 api_key 类 logout：**不删**用户
        config.toml `[auth.*]` 明文槽与 env——那是用户手管配置，非本工具职责）。"""
        keyring = _import_keyring()
        if keyring is None:
            return
        try:
            backend = keyring.get_keyring()
            if not _is_usable_backend(backend):
                return
            keyring.delete_password(_KEYRING_SERVICE, self._checked_ref(ref))
        except Exception:  # 条目不存在（PasswordDeleteError）/后端故障 → 静默 no-op
            return

    def key_hint(self, ref: str) -> str:
        """key 缺失时的配置指引（AuthRequired.detail 用；绝不含任何密钥值）。"""
        slot = _CONFIG_KEY_SLOTS.get(ref)
        if slot is None:
            return f"配置 keyring 条目 '{ref}'（service='{_KEYRING_SERVICE}'）"
        _, toml_slot, env_name = slot
        return (
            f"家目录 config.toml {toml_slot} 或环境变量 {env_name}；"
            f"或 keyring 条目 '{ref}'（service='{_KEYRING_SERVICE}'）"
        )

    # -- profiles 装载（§2.3 冻结签名 + §3.4 schema） ---------------------------

    def load_profiles(self) -> dict[str, ProviderProfile]:
        """解析 `auth/profiles.toml`（严格 schema；文件缺失 → 空表=未配置任何 provider）。"""
        path = self.profiles_path
        if not path.is_file():
            return {}
        with path.open("rb") as handle:
            doc = tomllib.load(handle)
        unknown_top = sorted(set(doc) - {"schema_version", "providers"})
        if unknown_top:
            raise CrawlerError(
                ErrorClass.CONFIG,
                f"profiles.toml 未知顶层键：{', '.join(unknown_top)}"
                "（仅允许 schema_version / [providers.*]）",
            )
        version = doc.get("schema_version", 1)
        if version != 1:
            raise CrawlerError(
                ErrorClass.CONFIG, f"profiles.toml schema_version 不支持：{version!r}（当前=1）"
            )
        providers_raw = doc.get("providers", {})
        if not isinstance(providers_raw, dict):
            raise CrawlerError(ErrorClass.CONFIG, "profiles.toml providers 须为表")
        return {
            str(provider_id): _parse_profile(str(provider_id), entry)
            for provider_id, entry in providers_raw.items()
        }

    # -- 巡检与收尾（§3.5 / AC-4.5 ⑤） -----------------------------------------

    def audit_permissions(self) -> list[str]:
        """巡检既有目录/文件权限；非 0700/0600 → 告警文本（**不自动改**，§3.5）。"""
        findings: list[str] = []
        for directory in (self.auth_dir, self.state_dir):
            if directory.is_dir():
                mode = stat.S_IMODE(directory.stat().st_mode)
                if mode != 0o700:
                    findings.append(f"{directory} 权限 {mode:03o}（应 0700）")
        if self.state_dir.is_dir():
            for path in sorted(self.state_dir.iterdir()):
                if path.name == _FILEKEY_NAME or path.suffix == ".enc":
                    mode = stat.S_IMODE(path.stat().st_mode)
                    if mode != 0o600:
                        findings.append(f"{path} 权限 {mode:03o}（应 0600）")
        return findings

    def clear_master_key_if_unused(self) -> bool:
        """无任何 `state/*.enc` 残留时清理主密钥（AC-4.5 ⑤：保护对象已不存在）。

        文件密钥同样取证式覆写删除；keyring 条目删除；进程内缓存清空。
        仍有 .enc（他 provider 在用）→ 不动，返回 False。
        """
        if self.state_dir.is_dir() and any(self.state_dir.glob("*.enc")):
            return False
        if self.state_dir.is_dir():
            _forensic_unlink(self.state_dir / _FILEKEY_NAME)
        self.delete_key(_MASTER_KEY_ENTRY)
        self._master_key = None
        return True


__all__ = ["CredentialStore", "ProviderProfile", "parse_meta_datetime"]
