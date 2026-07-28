"""`EZProxyProvider`（auth-framework §1/§3.4；07 §3.2；T1b）。

- **`rewrite_url` 真实重写**（§3.4 泛化规则）：host 的 `.` → `-` + `rewrite_suffix`
  （如 `www.sciencedirect.com` → `www-sciencedirect-com.login-myuniv-edu.ezproxy`）；
  端口保留；已重写幂等；无 host（相对路径/mailto:）恒等。fetch 前由 pipeline 统一
  调用——**adapter 不感知代理存在**（07 §3.2：代理是 L2 关注点）。
- **proxy cookie 维持**：有状态凭证走 `state_ref`（AES-GCM store），首登 headed 打开
  `proxy_base`（人工完成校方认证，D-006）→ storage_state 加密落盘；`load_cookies` 是
  `HTTPX_COOKIES` 后端的导出面（CookieSupplier seam 鸭型消费，与 cookie_session 同签名）。
- 健康判定轻量（state 存在性）：ezproxy profile 无探针端点（§3.4 schema），真实
  探测归 mock IdP 集成层（§9"mock proxy 302"）与 runbook。`refresh` 恒 None。

依赖面（§1 模块表）：store + 标准库 URL 处理；browser 仅在首登路径**惰性**触达。
"""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from urllib.parse import urlsplit, urlunsplit

from paper_crawler.auth.protocol import AuthProviderBase, ProviderKind
from paper_crawler.auth.store import CredentialStore, ProviderProfile, parse_meta_datetime
from paper_crawler.errors import AuthRequired, CrawlerError, ErrorClass
from paper_crawler.types import HealthStatus, SessionBackend, SessionHandle

if TYPE_CHECKING:  # httpx 只在 `load_cookies` 惰性触达（依赖面见模块 docstring）
    import httpx

Clock = Callable[[], datetime]
LoginFlow = Callable[..., bytes]
WaitFn = Callable[[], None]


def _default_clock() -> datetime:
    return datetime.now(UTC)


def _default_wait_for_user() -> None:  # pragma: no cover - 真实交互路径（CLI/测试注入替身）
    input("完成校方认证后回车继续…")


class EZProxyProvider(AuthProviderBase):
    """校外经机构 EZProxy 访问（07 §3.2）。"""

    kind: ProviderKind = "ezproxy"
    _backend = SessionBackend.HTTPX_COOKIES

    def __init__(
        self,
        profile: ProviderProfile,
        store: CredentialStore,
        *,
        clock: Clock | None = None,
        login_flow: LoginFlow | None = None,
        wait_for_user: WaitFn | None = None,
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
        self._login_flow = login_flow
        self._wait_for_user = wait_for_user or _default_wait_for_user

    # -- 内部 -----------------------------------------------------------------

    def _required(self, value: str | None, field: str) -> str:
        if value is None:  # pragma: no cover - load_profiles schema 已强制（防御纵深）
            raise CrawlerError(
                ErrorClass.CONFIG, f"provider {self.provider_id!r} 缺 {field}（schema 缺口）"
            )
        return value

    def _state_ref(self) -> str:
        return self._required(self._profile.state_ref, "state_ref")

    def _suffix(self) -> str:
        raw = self._required(self._profile.rewrite_suffix, "rewrite_suffix")
        return raw if raw.startswith(".") else f".{raw}"

    def _est_ttl(self) -> timedelta | None:
        hours = self._profile.est_ttl_hours
        return timedelta(hours=hours) if hours is not None else None

    def _handle(self, established_at: datetime) -> SessionHandle:
        return SessionHandle(
            provider_id=self.provider_id,
            backend=self._backend,
            payload_ref=self._state_ref(),
            established_at=established_at,
            est_ttl=self._est_ttl(),
        )

    # -- AuthProvider 五方法 ---------------------------------------------------

    def rewrite_url(self, url: str) -> str:
        """§3.4 泛化规则：host `.`→`-` + 后缀；端口保留；已重写幂等；无 host 恒等。"""
        parts = urlsplit(url)
        host = parts.hostname
        if not host:
            return url
        suffix = self._suffix()
        if host.endswith(suffix):
            return url  # 已重写幂等（重复套代理会毁 URL）
        rewritten = host.replace(".", "-") + suffix
        netloc = rewritten if parts.port is None else f"{rewritten}:{parts.port}"
        return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))

    def ensure_session(self, *, interactive: bool = False) -> SessionHandle:
        ref = self._state_ref()
        if self._store.has_state(ref):
            meta = self._store.read_meta(ref) or {}
            established = parse_meta_datetime(meta.get("established_at")) or self._clock()
            return self._handle(established)
        if not interactive:
            raise AuthRequired(
                f"no auth session for {self.provider_id!r}",
                detail=f"先执行 crawler auth login {self.provider_id}",
            )
        state = self._first_login()
        now = self._clock()
        self._store.write_state(ref, state)
        self._store.write_meta(
            ref,
            {
                "backend": str(self._backend),
                "established_at": now.isoformat(),
                "est_ttl_hours": self._profile.est_ttl_hours,
            },
        )
        return self._handle(now)

    def _first_login(self) -> bytes:
        """首登：headed 打开 `proxy_base`（EZProxy 登录入口，§4.1）→ 人工校方认证。"""
        flow = self._login_flow
        if flow is None:
            from paper_crawler.auth import browser  # 惰性：仅真实首登路径触达

            flow = browser.run_headed_login
        proxy_base = self._required(self._profile.proxy_base, "proxy_base")
        return flow(login_url=proxy_base, wait_for_user=self._wait_for_user)

    def health_check(self, session: SessionHandle) -> HealthStatus:
        """轻量：proxy cookie state 存在性（profile 无探针端点；§3.4 schema）。"""
        ref = session.payload_ref
        if not self._store.has_state(ref):
            return HealthStatus.EXPIRED
        status = HealthStatus.OK
        self._store.write_meta(
            ref, {"last_health": str(status), "last_health_at": self._clock().isoformat()}
        )
        return status

    def refresh(self, session: SessionHandle) -> SessionHandle | None:
        """proxy cookie 无静默续期通道（校方认证人在回路）→ 恒 None。"""
        return None

    def load_cookies(self, session: SessionHandle) -> "httpx.Cookies":
        """解密 proxy storage_state → httpx cookie jar（`HTTPX_COOKIES` 后端的导出面）。

        与 `CookieSessionProvider.load_cookies` 同签名同语义——CLI 装配的 `CookieSupplier`
        闭包按 `session.provider_id` 解析 provider 后**鸭型调用本方法**，此前 ezproxy 缺它，
        cookie 档 venue 一旦映射到 ezproxy profile 就在真实 fetch 时响亮 CONFIG（seam 断在
        provider 侧）。首登存的就是 Playwright storage_state（`_first_login`），与 cookie_session
        同格式，故直接复用其转换器。

        **消费方注意**：proxy cookie 的域是**代理父域**，命中的是 `rewrite_url` 改写后的
        host（其子域）。把 cookie 重新钉到平台主域的消费方（如 `oup_silverchair._cookies_for`
        的 `domain=_PRIMARY_DOMAIN` 防泄漏收窄）会让它在代理请求上失配——那是消费方侧的
        待接线点，不是本方法的语义。
        """
        # 惰性 import：保持模块依赖面（store + 标准库 URL 处理），httpx 只在本路径触达。
        from paper_crawler.auth.providers.cookie_session import storage_state_to_cookies

        return storage_state_to_cookies(self._store.read_state(session.payload_ref))

    def _delete_payload(self, payload_ref: str) -> None:
        self._store.delete_state(payload_ref)


__all__ = ["EZProxyProvider"]
