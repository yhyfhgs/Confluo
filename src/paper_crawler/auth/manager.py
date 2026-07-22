"""`AuthManager`：provider 注册表 + active_profile 解析 + session 缓存（auth-framework §1）。

- **注册表**：`load_providers(store)` 把 `profiles.toml` 条目按 kind 实例化为四类
  provider（§1 导出件）。
- **active_profile 解析**（07 §6 / §4.1）：`resolve(name, profile=...)` —— 位置参数可为
  profiles 键（精确命中）或 platform id；`--profile` 临时覆盖（`campus` 后缀式或
  `oup@campus` 全键式）；platform 多 profile 且无 active 映射 → CONFIG（响亮要求指定）。
  active_profile 映射经构造参数注入（config `[auth].active_profile` 槽归 T2/T5 波次，
  config.py 本任务零触碰——见终报偏离项）。
- **session 缓存**：`ensure_session` 进程内按 provider 键缓存 handle；logout 清缓存
  （AC-4.5 ②）并按 kind 走取证清理（B-m6），有状态类联动主密钥按需清理（⑤）。
- **启动巡检**（§3.5）：构造时 `store.audit_permissions()`，非 0600/0700 → obslog
  WARNING（不自动改）。

`auth status` 呈现（§4.2）**只读**：meta sidecar + 本地 key 存在性——不触发真实探测、
不解密 state（避免 status 消耗配额/触发风控）。
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime

from paper_crawler.auth.protocol import AuthProvider, ProviderKind
from paper_crawler.auth.providers.api_key import ApiKeyProvider
from paper_crawler.auth.providers.cookie_session import CookieSessionProvider
from paper_crawler.auth.providers.ezproxy import EZProxyProvider
from paper_crawler.auth.providers.sso_flow import SSOFlowProvider
from paper_crawler.auth.store import CredentialStore, ProviderProfile, parse_meta_datetime
from paper_crawler.config import Config
from paper_crawler.errors import CrawlerError, ErrorClass
from paper_crawler.obslog import log_event
from paper_crawler.types import SessionBackend, SessionHandle

Clock = Callable[[], datetime]

_PROVIDER_CLASSES: dict[ProviderKind, Callable[..., AuthProvider]] = {
    "api_key": ApiKeyProvider,
    "cookie_session": CookieSessionProvider,
    "sso_flow": SSOFlowProvider,
    "ezproxy": EZProxyProvider,
}

_KIND_BACKENDS: dict[ProviderKind, SessionBackend] = {
    "api_key": SessionBackend.BEARER_TOKEN,
    "cookie_session": SessionBackend.HTTPX_COOKIES,
    "sso_flow": SessionBackend.PLAYWRIGHT_STATE,
    "ezproxy": SessionBackend.HTTPX_COOKIES,
}


def _default_clock() -> datetime:
    return datetime.now(UTC)


def load_providers(
    store: CredentialStore, *, clock: Clock | None = None
) -> dict[str, AuthProvider]:
    """`profiles.toml` → provider 实例注册表（§1 导出件；kind → 实现类映射）。"""
    return {
        provider_id: _PROVIDER_CLASSES[profile.kind](profile, store, clock=clock)
        for provider_id, profile in store.load_profiles().items()
    }


@dataclass(frozen=True)
class ProviderStatus:
    """`auth status` 一行（§4.2 列序；纯呈现字符串——凭证值绝不在内）。"""

    provider: str
    kind: str
    backend: str
    session: str
    last_health: str
    est_expiry: str
    state: str


class AuthManager:
    """provider 注册表 + active_profile 解析 + session 缓存 + 巡检入口。"""

    def __init__(
        self,
        config: Config,
        *,
        clock: Clock | None = None,
        store: CredentialStore | None = None,
        active_profiles: Mapping[str, str] | None = None,
    ) -> None:
        self._config = config
        self._clock: Clock = clock or _default_clock
        self._store = store if store is not None else CredentialStore(config.home)
        self._store.bind_config(config)
        self._active = dict(active_profiles or {})
        self._profiles: dict[str, ProviderProfile] | None = None
        self._providers: dict[str, AuthProvider] | None = None
        self._sessions: dict[str, SessionHandle] = {}
        for finding in self._store.audit_permissions():  # §3.5 启动巡检：告警不自动改
            log_event("WARNING", f"凭证库权限巡检：{finding}")

    @property
    def store(self) -> CredentialStore:
        return self._store

    # -- 注册表与解析 ----------------------------------------------------------

    def profiles(self) -> dict[str, ProviderProfile]:
        if self._profiles is None:
            self._profiles = self._store.load_profiles()
        return self._profiles

    def providers(self) -> dict[str, AuthProvider]:
        if self._providers is None:
            self._providers = {
                provider_id: _PROVIDER_CLASSES[profile.kind](
                    profile, self._store, clock=self._clock
                )
                for provider_id, profile in self.profiles().items()
            }
        return self._providers

    def get(self, provider_key: str) -> AuthProvider:
        providers = self.providers()
        if provider_key not in providers:
            known = ", ".join(sorted(providers)) or "（空）"
            raise CrawlerError(
                ErrorClass.CONFIG,
                f"未知 auth provider: {provider_key!r}（profiles.toml 已配置：{known}）",
            )
        return providers[provider_key]

    def resolve(self, name: str, *, profile: str | None = None) -> AuthProvider:
        """`<provider>`（profiles 键或 platform id）+ 可选 `--profile` → 具体 provider。

        解析序（§4.1 / 07 §6）：`--profile`（全键 `oup@campus` 或后缀 `campus`）>
        profiles 键精确命中 > platform 的 active_profile 映射 > platform 唯一候选；
        多候选无映射 → CONFIG（列出候选，要求 `--profile` 或 active_profile）。
        """
        if profile:
            key = profile if "@" in profile or profile in self.profiles() else f"{name}@{profile}"
            return self.get(key)
        providers = self.providers()
        if name in providers:
            return providers[name]
        if name in self._active:
            return self.get(self._active[name])
        candidates = sorted(key for key, prof in self.profiles().items() if prof.platform == name)
        if len(candidates) == 1:
            return providers[candidates[0]]
        if candidates:
            raise CrawlerError(
                ErrorClass.CONFIG,
                f"platform {name!r} 配置了多个 profile：{', '.join(candidates)}——"
                "用 --profile 指定或在 config [auth].active_profile 固定",
            )
        return self.get(name)  # 统一走未知键报错（列出已配置项）

    # -- session 缓存 ----------------------------------------------------------

    def ensure_session(self, provider_key: str, *, interactive: bool = False) -> SessionHandle:
        """进程内缓存的 `ensure_session`（07 §5-1：无 session 且非交互 → AuthRequired）。"""
        cached = self._sessions.get(provider_key)
        if cached is not None:
            return cached
        handle = self.get(provider_key).ensure_session(interactive=interactive)
        self._sessions[provider_key] = handle
        return handle

    def drop_session(self, provider_key: str) -> None:
        """仅清进程内缓存（健康门 EXPIRED→refresh 换 handle 时用；不动持久层）。"""
        self._sessions.pop(provider_key, None)

    def logout(self, provider_key: str) -> AuthProvider:
        """AC-4.5 取证式登出（B-m6 按 kind 分列）：provider.invalidate（api_key=keyring
        副本+meta；有状态=覆写删 .enc+meta）→ 清进程缓存 ② → 有状态类按需清主密钥 ⑤。"""
        provider = self.get(provider_key)
        profile = self.profiles()[provider_key]
        handle = self._sessions.pop(provider_key, None) or self._synthetic_handle(profile)
        provider.invalidate(handle)
        if profile.kind != "api_key":
            self._store.clear_master_key_if_unused()
        return provider

    def _synthetic_handle(self, profile: ProviderProfile) -> SessionHandle:
        """logout 无活跃缓存时的指针 handle（只携 ref 条目名，无任何凭证值）。"""
        ref = profile.state_ref or profile.key_ref or profile.provider_id
        return SessionHandle(
            provider_id=profile.provider_id,
            backend=_KIND_BACKENDS[profile.kind],
            payload_ref=ref,
            established_at=self._clock(),
        )

    # -- `auth status` 只读呈现（§4.2） ----------------------------------------

    def status_rows(self) -> list[ProviderStatus]:
        return [
            self._status_row(provider_id, profile)
            for provider_id, profile in sorted(self.profiles().items())
        ]

    def _status_row(self, provider_id: str, profile: ProviderProfile) -> ProviderStatus:
        now = self._clock()
        backend = str(_KIND_BACKENDS[profile.kind])
        ref = profile.state_ref or profile.key_ref
        meta = self._store.read_meta(ref) if ref is not None else None
        needs_login = f"needs `auth login {provider_id}`"

        if profile.kind == "api_key":
            configured = profile.key_ref is not None and self._store.has_key(profile.key_ref)
            return ProviderStatus(
                provider=provider_id,
                kind=str(profile.kind),
                backend=backend,
                session="configured" if configured else "absent",
                last_health=_render_last_health(meta),
                est_expiry="—",
                state="ready" if configured else needs_login,
            )

        present = ref is not None and self._store.has_state(ref)
        established = parse_meta_datetime((meta or {}).get("established_at"))
        session = _render_age(established, now) if present else "absent"
        est_expiry = "—"
        expired = False
        if present and established is not None and profile.est_ttl_hours is not None:
            remaining_h = profile.est_ttl_hours - (now - established).total_seconds() / 3600
            expired = remaining_h <= 0
            est_expiry = "expired" if expired else f"~{int(remaining_h)}h"
        last_health_value = (meta or {}).get("last_health")
        unhealthy = last_health_value in (
            "expired",
            "challenged",
        )  # HealthStatus 值（meta 落盘为 str）
        state = needs_login if (not present or expired or unhealthy) else "ready"
        return ProviderStatus(
            provider=provider_id,
            kind=str(profile.kind),
            backend=backend,
            session=session,
            last_health=_render_last_health(meta),
            est_expiry=est_expiry,
            state=state,
        )


def _render_age(established: datetime | None, now: datetime) -> str:
    """session 列 = `now - established_at`（§4.2；无 meta 时间戳则如实标注）。"""
    if established is None:
        return "present"  # state 在但 meta 缺失/损坏——只读呈现不猜测年龄
    seconds = max(0.0, (now - established).total_seconds())
    if seconds < 3600:
        return f"age {int(seconds // 60)}m"
    return f"age {int(seconds // 3600)}h"


def _render_last_health(meta: dict[str, object] | None) -> str:
    """last_health 列 = 最近一次 health_check 结果+时刻（meta 缓存；无则 `—`）。"""
    if not meta:
        return "—"
    value = meta.get("last_health")
    if not isinstance(value, str):
        return "—"
    checked_at = parse_meta_datetime(meta.get("last_health_at"))
    if checked_at is None:
        return value.upper()
    return f"{value.upper()} ({checked_at.strftime('%Y-%m-%d %H:%M')})"


__all__ = ["AuthManager", "ProviderStatus", "load_providers"]
