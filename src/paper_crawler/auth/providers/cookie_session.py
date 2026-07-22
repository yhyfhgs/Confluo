"""`CookieSessionProvider`（auth-framework §1/§4.1；07 §3.1；T1b）。

- **首登**（interactive=True，人在回路 D-006）：经 browser seam（惰性）headed 登录 →
  storage_state 加密落盘（`CredentialStore.write_state`）+ 非密 meta sidecar（A-m2）。
- **headless 复用**：`load_cookies(session)` 解密 storage_state → httpx cookie jar
  （Silverchair 系直取通道；T4 adapter 消费）。
- **健康探针**：`probe_url`（profiles.toml 声明）+ 专属 httpx client（凭证隔离红线：
  cookie 绝不进共享 client）→ `ChallengeDetector` 四态判读 → `HealthStatus`。
  探针不触发风控对抗——CHALLENGED 即如实上报（§2.2）。
- cookie_session 无静默续期通道（07 §3.1 重登人在回路）→ `refresh` 恒 None。
"""

import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import httpx

from paper_crawler.auth.challenge import ChallengeDetector, ClassifyResult
from paper_crawler.auth.protocol import AuthProviderBase, ProviderKind
from paper_crawler.auth.store import CredentialStore, ProviderProfile, parse_meta_datetime
from paper_crawler.errors import AuthRequired, CrawlerError, ErrorClass
from paper_crawler.types import HealthStatus, SessionBackend, SessionHandle
from paper_crawler.useragent import build_user_agent

Clock = Callable[[], datetime]
HttpFactory = Callable[[httpx.Cookies], httpx.Client]
# (login_url=..., wait_for_user=...) -> storage_state bytes（browser.run_headed_login 形状）
LoginFlow = Callable[..., bytes]
WaitFn = Callable[[], None]

# ChallengeDetector 四态 → HealthStatus（§11：探针页判读；NO_ENTITLEMENT ≠ session
# 失效——entitlement 按篇判定归 adapter/resolve，探针只回答"登录态是否还在"）。
_CLASSIFY_TO_HEALTH: dict[ClassifyResult, HealthStatus] = {
    ClassifyResult.OK: HealthStatus.OK,
    ClassifyResult.LOGIN_REDIRECT: HealthStatus.EXPIRED,
    ClassifyResult.CHALLENGE: HealthStatus.CHALLENGED,
    ClassifyResult.NO_ENTITLEMENT: HealthStatus.OK,
}


def _default_clock() -> datetime:
    return datetime.now(UTC)


def _default_wait_for_user() -> None:  # pragma: no cover - 真实交互路径（CLI/测试注入替身）
    input("完成登录（含 MFA）后回车继续…")


def _default_http_factory(cookies: httpx.Cookies) -> httpx.Client:
    """探针专属 client（凭证隔离红线：携 cookie 的 client 绝不与共享 client 复用）。"""
    return httpx.Client(
        cookies=cookies,
        follow_redirects=True,
        headers={"User-Agent": build_user_agent(None)},
    )


def _required(value: str | None, field: str, provider_id: str) -> str:
    if value is None:  # pragma: no cover - load_profiles schema 已强制必填（防御纵深）
        raise CrawlerError(
            ErrorClass.CONFIG, f"provider {provider_id!r} 缺 {field}（profiles schema 缺口）"
        )
    return value


def storage_state_to_cookies(state: bytes) -> httpx.Cookies:
    """Playwright storage_state JSON → httpx cookie jar（headless 复用通道）。"""
    try:
        doc = json.loads(state.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AuthRequired(
            "stored auth state is not a storage_state document",
            detail="state 内容非 JSON——crawler auth login 重登",
        ) from exc
    cookies = httpx.Cookies()
    raw = doc.get("cookies") if isinstance(doc, dict) else None
    if not isinstance(raw, list):
        return cookies
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        name, value = entry.get("name"), entry.get("value")
        if not isinstance(name, str) or not isinstance(value, str):
            continue
        domain = str(entry.get("domain") or "").lstrip(".")
        path = str(entry.get("path") or "/")
        cookies.set(name, value, domain=domain, path=path)
    return cookies


def cookies_to_storage_state(cookies: httpx.Cookies) -> bytes:
    """httpx cookie jar → storage_state JSON（SSO 静默续期回写；§9 生命周期）。"""
    entries: list[dict[str, object]] = []
    for cookie in cookies.jar:
        entry: dict[str, object] = {
            "name": cookie.name,
            "value": cookie.value or "",
            "domain": cookie.domain,
            "path": cookie.path or "/",
            "secure": bool(cookie.secure),
        }
        if cookie.expires is not None:
            entry["expires"] = cookie.expires
        entries.append(entry)
    return json.dumps({"cookies": entries, "origins": []}, ensure_ascii=False).encode("utf-8")


class CookieSessionProvider(AuthProviderBase):
    """出版社直接账号 / 校内已认证态（07 §3.1）。"""

    kind: ProviderKind = "cookie_session"
    _backend = SessionBackend.HTTPX_COOKIES

    def __init__(
        self,
        profile: ProviderProfile,
        store: CredentialStore,
        *,
        clock: Clock | None = None,
        http_factory: HttpFactory | None = None,
        login_flow: LoginFlow | None = None,
        wait_for_user: WaitFn | None = None,
        detector: ChallengeDetector | None = None,
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
        self._http_factory = http_factory or _default_http_factory
        self._login_flow = login_flow
        self._wait_for_user = wait_for_user or _default_wait_for_user
        self._detector = detector or ChallengeDetector()

    # -- 内部 -----------------------------------------------------------------

    def _state_ref(self) -> str:
        return _required(self._profile.state_ref, "state_ref", self.provider_id)

    def _login_url(self) -> str:
        return _required(self._profile.login_url, "login_url", self.provider_id)

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

    def _first_login(self) -> bytes:
        flow = self._login_flow
        if flow is None:
            # 惰性（§1 依赖表"browser（惰性）"）：仅真实首登路径触达 browser 模块。
            from paper_crawler.auth import browser

            flow = browser.run_headed_login
        return flow(login_url=self._login_url(), wait_for_user=self._wait_for_user)

    # -- AuthProvider 五方法 ---------------------------------------------------

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

    def health_check(self, session: SessionHandle) -> HealthStatus:
        ref = session.payload_ref
        if not self._store.has_state(ref):
            return HealthStatus.EXPIRED
        probe_url = self._profile.probe_url
        if probe_url is None:
            status = HealthStatus.OK  # 无探针端点：state 在即视 OK（轻量判定）
        else:
            status = self._probe(ref, probe_url)
        self._store.write_meta(
            ref, {"last_health": str(status), "last_health_at": self._clock().isoformat()}
        )
        return status

    def _probe(self, ref: str, probe_url: str) -> HealthStatus:
        cookies = storage_state_to_cookies(self._store.read_state(ref))
        client = self._http_factory(cookies)
        try:
            try:
                response = client.get(probe_url)
            except httpx.HTTPError as exc:  # 网络层异常：沿 HttpClient 映射口径 → TRANSIENT
                raise CrawlerError(
                    ErrorClass.TRANSIENT,
                    f"auth probe failed for {self.provider_id!r}",
                    detail=type(exc).__name__,
                ) from exc
        finally:
            client.close()
        result = self._detector.classify(
            status=response.status_code,
            headers=response.headers,
            final_url=str(response.url),
            body=response.content,
        )
        return _CLASSIFY_TO_HEALTH[result]

    def refresh(self, session: SessionHandle) -> SessionHandle | None:
        """cookie_session 无静默续期通道（07 §3.1：重登人在回路）→ 恒 None。"""
        return None

    def load_cookies(self, session: SessionHandle) -> httpx.Cookies:
        """解密 storage_state → httpx cookie jar（headless 复用；T4 adapter 消费）。"""
        return storage_state_to_cookies(self._store.read_state(session.payload_ref))

    def _delete_payload(self, payload_ref: str) -> None:
        """invalidate 样板的 store 委托（AC-4.5：`.enc` 覆写删除 + meta sidecar 连带）。"""
        self._store.delete_state(payload_ref)


__all__ = [
    "CookieSessionProvider",
    "cookies_to_storage_state",
    "storage_state_to_cookies",
]
