"""`ApiKeyProvider`（auth-framework §1/§4.1；07 §3.4；T1b）。

①类简单字符串密钥（Elsevier `X-ELS-APIKey`(+`X-ELS-Insttoken`) / Wiley TDM token）：

- `ensure_session`：`store.has_key(key_ref)` 存在性预检（**不取值**——密钥值绝不
  流经 provider/handle/日志）→ 缺 → `AuthRequired`（detail=配置指引，含 config 槽/
  env/keyring 三源路径）；在 → `SessionHandle(BEARER_TOKEN)`（无状态凭证，指针语义）。
- `health_check` 轻量（key 存在性）；`quota_probe` 连通/entitlement 探测归 T3 在线层
  （任务卡钉死；BLOCKER-1：真实 key 到位后 T7b runbook 补真实验证）。
- `invalidate`（B-m6 api_key 取证口径）：只撤销本工具管理的副本——keyring 中的
  `key_ref`/`insttoken_ref` 条目 + meta sidecar；**不删**用户 config.toml `[auth.*]`
  明文槽与 env（用户手管配置非本命令职责）。无 storage_state/user-data-dir，①⑥不适用。

本 provider 全路径不触 `cryptography`/`keyring` 之外的加密面（AC-4.1 轻路径：未装
`[auth]` extra 时 APIKey 全链可用）。
"""

from collections.abc import Callable
from datetime import UTC, datetime

from paper_crawler.auth.protocol import AuthProviderBase, ProviderKind
from paper_crawler.auth.store import CredentialStore, ProviderProfile
from paper_crawler.errors import AuthRequired, CrawlerError, ErrorClass
from paper_crawler.types import HealthStatus, SessionBackend, SessionHandle

Clock = Callable[[], datetime]


def _default_clock() -> datetime:
    return datetime.now(UTC)


class ApiKeyProvider(AuthProviderBase):
    """官方 API key / TDM token（07 §3.4；elsevier AC-4.1 载体）。"""

    kind: ProviderKind = "api_key"

    def __init__(
        self,
        profile: ProviderProfile,
        store: CredentialStore,
        *,
        clock: Clock | None = None,
    ) -> None:
        if profile.kind != self.kind:
            raise CrawlerError(
                ErrorClass.CONFIG,
                f"profile {profile.provider_id!r} kind={profile.kind} 与 {self.kind} 不符",
            )
        self.provider_id = profile.provider_id
        self._profile = profile
        self._store = store
        self._clock = clock or _default_clock

    def _key_ref(self) -> str:
        ref = self._profile.key_ref
        if ref is None:  # pragma: no cover - load_profiles schema 已强制（防御纵深）
            raise CrawlerError(
                ErrorClass.CONFIG, f"provider {self.provider_id!r} 缺 key_ref（schema 缺口）"
            )
        return ref

    def _handle(self) -> SessionHandle:
        return SessionHandle(
            provider_id=self.provider_id,
            backend=SessionBackend.BEARER_TOKEN,
            payload_ref=self._key_ref(),
            established_at=self._clock(),
        )

    def ensure_session(self, *, interactive: bool = False) -> SessionHandle:
        """has_key 预检 → 缺 `AuthRequired`（含配置指引 detail）；在 → BEARER_TOKEN handle。

        interactive=True（`auth login`）额外落 meta sidecar（established_at 供 status
        呈现）——本 provider 不做任何交互式密钥输入（密钥经 config/env/keyring 配置，
        CLI 绝不经手明文值）。`quota_probe` 连通探测归 T3 在线层（任务卡口径）。
        """
        ref = self._key_ref()
        if not self._store.has_key(ref):
            raise AuthRequired(
                f"API key missing for {self.provider_id!r}",
                detail=self._store.key_hint(ref),
            )
        if interactive:
            self._store.write_meta(
                ref,
                {
                    "backend": str(SessionBackend.BEARER_TOKEN),
                    "established_at": self._clock().isoformat(),
                },
            )
        return self._handle()

    def health_check(self, session: SessionHandle) -> HealthStatus:
        """轻量：key 存在性（quota_probe 连通留 T3 在线层）。缺 key → EXPIRED。"""
        ok = self._store.has_key(session.payload_ref)
        status = HealthStatus.OK if ok else HealthStatus.EXPIRED
        if self._store.read_meta(session.payload_ref) is not None:
            # 仅在 login 已建 sidecar 时刷新（status 呈现）；不无端创建 state 目录。
            self._store.write_meta(
                session.payload_ref,
                {"last_health": str(status), "last_health_at": self._clock().isoformat()},
            )
        return status

    def refresh(self, session: SessionHandle) -> SessionHandle | None:
        """key 类"续期"= key 仍在 → 新 handle；已被移除 → None（§2.2 语义映射）。"""
        if self._store.has_key(session.payload_ref):
            return self._handle()
        return None

    def invalidate(self, session: SessionHandle) -> None:
        """B-m6 api_key 取证口径：删 keyring 条目副本 + meta sidecar；不动 config/env。"""
        ref = self._key_ref()
        self._store.delete_key(ref)
        if self._profile.insttoken_ref is not None:
            self._store.delete_key(self._profile.insttoken_ref)
        self._store.delete_meta(ref)


__all__ = ["ApiKeyProvider"]
