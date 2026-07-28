"""四 AuthProvider 实现单测（auth-framework §2.2/§3.4/§4.1；T1b）。

覆盖面：APIKey（has_key 预检→AuthRequired 指引 / BEARER_TOKEN handle / B-m6 取证
invalidate）；CookieSession（storage_state 加密落盘→cookie jar 导出 / 探针四态判读 /
首登经 browser seam）；SSO（重放 InstitutionalLogin 续期三路：成功新 handle / 失败
None / 风控 Challenged）；EZProxy（rewrite_url 真实重写表含端口/子域/幂等边界）。

零真实网络（httpx.MockTransport）、零真实浏览器（假 login_flow）、零真实 keyring。
"""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest

import paper_crawler.auth.store as store_mod
from helpers.auth import FakeKeyring, install_fake_keyring, make_config
from paper_crawler.auth.protocol import AuthProvider
from paper_crawler.auth.providers.api_key import ApiKeyProvider
from paper_crawler.auth.providers.cookie_session import (
    CookieSessionProvider,
    cookies_to_storage_state,
    storage_state_to_cookies,
)
from paper_crawler.auth.providers.ezproxy import EZProxyProvider
from paper_crawler.auth.providers.sso_flow import SSOFlowProvider
from paper_crawler.auth.store import CredentialStore, ProviderProfile
from paper_crawler.errors import AuthRequired, Challenged, CrawlerError, ErrorClass
from paper_crawler.types import HealthStatus, SessionBackend, SessionHandle

T0 = datetime(2026, 7, 23, 12, 0, 0, tzinfo=UTC)

SECRET_COOKIE = "COOKIE-SECRET-abc123"
SECRET_KEY = "APIKEY-SECRET-xyz789"

STORAGE_STATE = json.dumps(
    {
        "cookies": [
            {
                "name": "sid",
                "value": SECRET_COOKIE,
                "domain": "mock.test",
                "path": "/",
                "secure": True,
            }
        ],
        "origins": [],
    }
).encode("utf-8")


@pytest.fixture(autouse=True)
def _isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(store_mod, "_import_keyring", lambda: None)
    monkeypatch.setattr(store_mod, "_filekey_warned", True)  # 警告已测于 store 层，此处静音
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def home(tmp_path: Path) -> Path:
    return tmp_path / "home"


@pytest.fixture
def store(home: Path) -> CredentialStore:
    built = CredentialStore(home)
    built.bind_config(make_config(home))
    return built


class FakeClock:
    def __init__(self, start: datetime = T0) -> None:
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kwargs: float) -> None:
        self.now = self.now + timedelta(**kwargs)


API_PROFILE = ProviderProfile(
    provider_id="elsevier",
    kind="api_key",
    platform="elsevier_sd",
    key_ref="elsevier_apikey",
    insttoken_ref="elsevier_insttoken",
)

COOKIE_PROFILE = ProviderProfile(
    provider_id="oup@campus",
    kind="cookie_session",
    platform="oup_silverchair",
    login_url="https://mock.test/login",
    probe_url="https://mock.test/my-account",
    state_ref="oup_campus_state",
    est_ttl_hours=24.0,
)

SSO_PROFILE = ProviderProfile(
    provider_id="oup@shib",
    kind="sso_flow",
    platform="oup_silverchair",
    inst_login_url="https://mock.test/InstitutionalLogin",
    wayf_hint="My University",
    probe_url="https://mock.test/my-account",
    state_ref="oup_shib_state",
    est_ttl_hours=8.0,
)

EZPROXY_PROFILE = ProviderProfile(
    provider_id="elsevier@ezproxy",
    kind="ezproxy",
    platform="elsevier_sd",
    proxy_base="https://login.myuniv.edu/login?url=",
    rewrite_suffix=".login-myuniv-edu.ezproxy",
    state_ref="ezproxy_myuniv_state",
    est_ttl_hours=12.0,
)


def transport_factory(handler: object) -> object:
    """探针 http_factory：MockTransport 专属 client（零真实网络）。"""

    def factory(cookies: httpx.Cookies) -> httpx.Client:
        return httpx.Client(
            cookies=cookies,
            follow_redirects=True,
            transport=httpx.MockTransport(handler),  # type: ignore[arg-type]
        )

    return factory


# ---------------------------------------------------------------------------
# 协议符合性（四实现 isinstance AuthProvider）
# ---------------------------------------------------------------------------


def test_all_four_providers_satisfy_protocol(store: CredentialStore) -> None:
    providers = [
        ApiKeyProvider(API_PROFILE, store),
        CookieSessionProvider(COOKIE_PROFILE, store),
        SSOFlowProvider(SSO_PROFILE, store),
        EZProxyProvider(EZPROXY_PROFILE, store),
    ]
    for provider in providers:
        assert isinstance(provider, AuthProvider)
    assert [p.kind for p in providers] == ["api_key", "cookie_session", "sso_flow", "ezproxy"]


@pytest.mark.parametrize(
    ("cls", "profile"),
    [
        (ApiKeyProvider, COOKIE_PROFILE),
        (CookieSessionProvider, API_PROFILE),
        (SSOFlowProvider, COOKIE_PROFILE),
        (EZProxyProvider, SSO_PROFILE),
    ],
)
def test_kind_mismatch_rejected(
    cls: type, profile: ProviderProfile, store: CredentialStore
) -> None:
    with pytest.raises(CrawlerError) as excinfo:
        cls(profile, store)
    assert excinfo.value.error_class is ErrorClass.CONFIG


# ---------------------------------------------------------------------------
# ApiKeyProvider
# ---------------------------------------------------------------------------


def test_api_key_missing_raises_auth_required_with_guidance(store: CredentialStore) -> None:
    provider = ApiKeyProvider(API_PROFILE, store, clock=FakeClock())
    with pytest.raises(AuthRequired) as excinfo:
        provider.ensure_session()
    assert "[auth.elsevier].api_key" in excinfo.value.detail
    assert "PAPER_CRAWLER_ELSEVIER_API_KEY" in excinfo.value.detail
    with pytest.raises(AuthRequired):
        provider.ensure_session(interactive=True)  # key 不经 CLI 输入：交互态同样只指引


def test_api_key_ensure_session_returns_bearer_handle(home: Path, store: CredentialStore) -> None:
    store.bind_config(make_config(home, elsevier_api_key=SECRET_KEY))
    clock = FakeClock()
    provider = ApiKeyProvider(API_PROFILE, store, clock=clock)
    handle = provider.ensure_session()
    assert handle == SessionHandle(
        provider_id="elsevier",
        backend=SessionBackend.BEARER_TOKEN,
        payload_ref="elsevier_apikey",
        established_at=T0,
    )
    assert handle.est_ttl is None


def test_api_key_interactive_login_writes_meta_without_key_value(
    home: Path, store: CredentialStore
) -> None:
    store.bind_config(make_config(home, elsevier_api_key=SECRET_KEY))
    provider = ApiKeyProvider(API_PROFILE, store, clock=FakeClock())
    provider.ensure_session(interactive=True)
    meta = store.read_meta("elsevier_apikey")
    assert meta is not None
    assert meta["backend"] == "bearer_token"
    assert SECRET_KEY not in json.dumps(meta)  # sidecar 非密（A-m2）
    raw = (store.state_dir / "elsevier_apikey.meta.json").read_text(encoding="utf-8")
    assert SECRET_KEY not in raw


def test_api_key_health_check_and_refresh(home: Path, store: CredentialStore) -> None:
    config_with_key = make_config(home, elsevier_api_key=SECRET_KEY)
    store.bind_config(config_with_key)
    clock = FakeClock()
    provider = ApiKeyProvider(API_PROFILE, store, clock=clock)
    handle = provider.ensure_session()
    assert provider.health_check(handle) is HealthStatus.OK
    clock.advance(hours=1)
    refreshed = provider.refresh(handle)
    assert refreshed is not None and refreshed.established_at == clock.now
    store.bind_config(make_config(home))  # key 被移除
    assert provider.health_check(handle) is HealthStatus.EXPIRED
    assert provider.refresh(handle) is None


def test_api_key_invalidate_forensics_by_kind(
    home: Path, store: CredentialStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """B-m6：清 keyring 副本 + meta；不删用户 config 槽/env。"""
    fake = FakeKeyring()
    fake.entries[("paper-crawler", "elsevier_apikey")] = SECRET_KEY
    fake.entries[("paper-crawler", "elsevier_insttoken")] = "INST-SECRET"
    install_fake_keyring(monkeypatch, fake)
    config = make_config(home, elsevier_api_key="config-copy")
    store.bind_config(config)
    provider = ApiKeyProvider(API_PROFILE, store, clock=FakeClock())
    handle = provider.ensure_session(interactive=True)
    provider.invalidate(handle)
    assert ("paper-crawler", "elsevier_apikey") not in fake.entries  # keyring 副本清除
    assert ("paper-crawler", "elsevier_insttoken") not in fake.entries
    assert store.read_meta("elsevier_apikey") is None  # 工具管理的 sidecar 清除
    assert config.elsevier_api_key == "config-copy"  # 用户 config 槽不动
    assert not list(store.state_dir.glob("*.enc"))  # api_key 类本就无 storage_state


def test_api_key_no_secret_in_repr_or_errors(home: Path, store: CredentialStore) -> None:
    store.bind_config(make_config(home, elsevier_api_key=SECRET_KEY))
    provider = ApiKeyProvider(API_PROFILE, store, clock=FakeClock())
    handle = provider.ensure_session()
    for rendered in (repr(provider), str(provider), repr(handle), repr(provider._profile)):
        assert SECRET_KEY not in rendered  # 密钥值绝不入 repr（安全断言 #7）


# ---------------------------------------------------------------------------
# CookieSessionProvider
# ---------------------------------------------------------------------------


def make_cookie_provider(
    store: CredentialStore,
    *,
    clock: FakeClock | None = None,
    handler: object = None,
    login_state: bytes = STORAGE_STATE,
    profile: ProviderProfile = COOKIE_PROFILE,
) -> tuple[CookieSessionProvider, list[str]]:
    login_calls: list[str] = []

    def login_flow(*, login_url: str, wait_for_user: object) -> bytes:
        login_calls.append(login_url)
        return login_state

    provider = CookieSessionProvider(
        profile,
        store,
        clock=clock or FakeClock(),
        login_flow=login_flow,
        http_factory=transport_factory(handler) if handler else None,  # type: ignore[arg-type]
    )
    return provider, login_calls


def test_cookie_ensure_session_missing_noninteractive_raises(store: CredentialStore) -> None:
    provider, _ = make_cookie_provider(store)
    with pytest.raises(AuthRequired) as excinfo:
        provider.ensure_session()
    assert "crawler auth login oup@campus" in excinfo.value.detail


def test_cookie_interactive_first_login_encrypts_state_and_meta(store: CredentialStore) -> None:
    clock = FakeClock()
    provider, login_calls = make_cookie_provider(store, clock=clock)
    handle = provider.ensure_session(interactive=True)
    assert login_calls == ["https://mock.test/login"]  # browser seam 收到 login_url
    assert handle.backend is SessionBackend.HTTPX_COOKIES
    assert handle.payload_ref == "oup_campus_state"
    assert handle.established_at == T0
    assert handle.est_ttl == timedelta(hours=24)
    enc = store.state_dir / "oup_campus_state.enc"
    assert enc.is_file()
    assert SECRET_COOKIE.encode() not in enc.read_bytes()  # 落盘即密文（AC-0.3）
    meta = store.read_meta("oup_campus_state")
    assert meta is not None and meta["backend"] == "httpx_cookies"
    assert SECRET_COOKIE not in json.dumps(meta)


def test_cookie_ensure_session_reuses_persisted_state(store: CredentialStore) -> None:
    clock = FakeClock()
    provider, login_calls = make_cookie_provider(store, clock=clock)
    first = provider.ensure_session(interactive=True)
    clock.advance(hours=3)
    again = provider.ensure_session()  # headless 复用：不再触发首登
    assert login_calls == ["https://mock.test/login"]
    assert again.established_at == first.established_at  # established 取 meta，非 now


def test_cookie_load_cookies_roundtrip(store: CredentialStore) -> None:
    provider, _ = make_cookie_provider(store)
    handle = provider.ensure_session(interactive=True)
    jar = provider.load_cookies(handle)
    assert jar.get("sid", domain="mock.test") == SECRET_COOKIE


def test_cookie_health_check_probe_ok(store: CredentialStore) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/my-account"
        assert f"sid={SECRET_COOKIE}" in request.headers.get("cookie", "")  # jar 复用
        return httpx.Response(200, text="<html>Signed in as prof@myuniv.edu</html>")

    provider, _ = make_cookie_provider(store, handler=handler)
    handle = provider.ensure_session(interactive=True)
    assert provider.health_check(handle) is HealthStatus.OK
    meta = store.read_meta("oup_campus_state")
    assert meta is not None and meta["last_health"] == "ok"


def test_cookie_health_check_login_redirect_expired(store: CredentialStore) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/my-account":
            return httpx.Response(302, headers={"location": "https://mock.test/signin"})
        return httpx.Response(200, text="<html>please sign in</html>")

    provider, _ = make_cookie_provider(store, handler=handler)
    handle = provider.ensure_session(interactive=True)
    assert provider.health_check(handle) is HealthStatus.EXPIRED
    meta = store.read_meta("oup_campus_state")
    assert meta is not None and meta["last_health"] == "expired"


def test_cookie_health_check_challenge(store: CredentialStore) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, headers={"cf-mitigated": "challenge"}, text="Just a moment...")

    provider, _ = make_cookie_provider(store, handler=handler)
    handle = provider.ensure_session(interactive=True)
    assert provider.health_check(handle) is HealthStatus.CHALLENGED  # 如实上报，不对抗


def test_cookie_health_check_without_probe_url_is_presence_based(store: CredentialStore) -> None:
    profile = ProviderProfile(
        provider_id="oup@campus",
        kind="cookie_session",
        platform="oup_silverchair",
        login_url="https://mock.test/login",
        state_ref="oup_campus_state",
    )
    provider, _ = make_cookie_provider(store, profile=profile)
    handle = provider.ensure_session(interactive=True)
    assert provider.health_check(handle) is HealthStatus.OK  # 轻量：state 在即 OK
    store.delete_state("oup_campus_state")
    assert provider.health_check(handle) is HealthStatus.EXPIRED


def test_cookie_probe_network_error_maps_transient(store: CredentialStore) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    provider, _ = make_cookie_provider(store, handler=handler)
    handle = provider.ensure_session(interactive=True)
    with pytest.raises(CrawlerError) as excinfo:
        provider.health_check(handle)
    assert excinfo.value.error_class is ErrorClass.TRANSIENT
    assert SECRET_COOKIE not in str(excinfo.value)  # 异常消息无凭证（安全断言 #7）
    assert SECRET_COOKIE not in excinfo.value.detail


def test_cookie_refresh_always_none(store: CredentialStore) -> None:
    provider, _ = make_cookie_provider(store)
    handle = provider.ensure_session(interactive=True)
    assert provider.refresh(handle) is None  # 07 §3.1：cookie 类无静默续期通道


def test_cookie_invalidate_deletes_state_and_meta(store: CredentialStore) -> None:
    provider, _ = make_cookie_provider(store)
    handle = provider.ensure_session(interactive=True)
    provider.invalidate(handle)
    assert not (store.state_dir / "oup_campus_state.enc").exists()
    assert not (store.state_dir / "oup_campus_state.meta.json").exists()
    with pytest.raises(AuthRequired):
        provider.ensure_session()  # 取证删除后回到"需首登"态


def test_storage_state_helpers_roundtrip() -> None:
    jar = storage_state_to_cookies(STORAGE_STATE)
    assert jar.get("sid", domain="mock.test") == SECRET_COOKIE
    rebuilt = storage_state_to_cookies(cookies_to_storage_state(jar))
    assert rebuilt.get("sid", domain="mock.test") == SECRET_COOKIE


def test_storage_state_malformed_raises_auth_required() -> None:
    with pytest.raises(AuthRequired):
        storage_state_to_cookies(b"\xff\xfenot-json")
    assert len(storage_state_to_cookies(b'{"no_cookies": 1}')) == 0  # 容错：无 cookies 键


# ---------------------------------------------------------------------------
# SSOFlowProvider（refresh 三路：成功 / 失败 None / 风控 Challenged）
# ---------------------------------------------------------------------------


def make_sso_provider(
    store: CredentialStore, handler: object, clock: FakeClock | None = None
) -> SSOFlowProvider:
    def login_flow(*, login_url: str, wait_for_user: object) -> bytes:
        return STORAGE_STATE

    return SSOFlowProvider(
        SSO_PROFILE,
        store,
        clock=clock or FakeClock(),
        login_flow=login_flow,
        http_factory=transport_factory(handler),  # type: ignore[arg-type]
    )


def test_sso_backend_is_playwright_state_and_login_opens_inst_url(
    store: CredentialStore,
) -> None:
    calls: list[str] = []

    def login_flow(*, login_url: str, wait_for_user: object) -> bytes:
        calls.append(login_url)
        return STORAGE_STATE

    provider = SSOFlowProvider(SSO_PROFILE, store, clock=FakeClock(), login_flow=login_flow)
    handle = provider.ensure_session(interactive=True)
    assert calls == ["https://mock.test/InstitutionalLogin"]
    assert handle.backend is SessionBackend.PLAYWRIGHT_STATE
    assert handle.est_ttl == timedelta(hours=8)


def test_sso_refresh_success_returns_new_handle_and_rewrites_state(
    store: CredentialStore,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/InstitutionalLogin":
            # IdP session 尚存：302 回跳 + 种新 cookie（纯重定向链，无 JS，§9）
            return httpx.Response(
                302,
                headers={
                    "location": "https://mock.test/landing",
                    "set-cookie": "sid=REFRESHED-cookie; Domain=mock.test; Path=/",
                },
            )
        return httpx.Response(200, text="<html>Signed in as prof — my account</html>")

    clock = FakeClock()
    provider = make_sso_provider(store, handler, clock=clock)
    handle = provider.ensure_session(interactive=True)
    clock.advance(hours=9)
    refreshed = provider.refresh(handle)
    assert refreshed is not None
    assert refreshed.established_at == clock.now  # 新 handle（时钟注入可测，B-M1）
    jar = provider.load_cookies(refreshed)
    assert jar.get("sid", domain="mock.test") == "REFRESHED-cookie"  # 新 cookie 已回写加密 state
    meta = store.read_meta("oup_shib_state")
    assert meta is not None and meta["last_health"] == "ok"


def test_sso_refresh_idp_expired_returns_none(store: CredentialStore) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/InstitutionalLogin":
            return httpx.Response(302, headers={"location": "https://mock.test/idp/login"})
        return httpx.Response(200, text="<html>IdP login required</html>")

    provider = make_sso_provider(store, handler)
    handle = provider.ensure_session(interactive=True)
    assert provider.refresh(handle) is None  # IdP 亦过期 → 人工重登（BLOCKED 路径）


def test_sso_refresh_challenge_raises_challenged(store: CredentialStore) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, headers={"cf-mitigated": "challenge"}, text="Just a moment...")

    provider = make_sso_provider(store, handler)
    handle = provider.ensure_session(interactive=True)
    with pytest.raises(Challenged):
        provider.refresh(handle)  # 风控：如实上报，绝不重试/对抗（AC-0.2/AC-4.6）


def test_sso_refresh_without_state_returns_none(store: CredentialStore) -> None:
    provider = make_sso_provider(store, lambda request: httpx.Response(200))
    handle = SessionHandle(
        provider_id="oup@shib",
        backend=SessionBackend.PLAYWRIGHT_STATE,
        payload_ref="oup_shib_state",
        established_at=T0,
    )
    assert provider.refresh(handle) is None


def test_sso_refresh_network_error_returns_none(store: CredentialStore) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timeout", request=request)

    provider = make_sso_provider(store, handler)
    handle = provider.ensure_session(interactive=True)
    assert provider.refresh(handle) is None  # 网络失败 → 不可静默续期（不重试）


# ---------------------------------------------------------------------------
# EZProxyProvider（rewrite_url 真实重写表 + 边界）
# ---------------------------------------------------------------------------


@pytest.fixture
def ezproxy(store: CredentialStore) -> EZProxyProvider:
    def login_flow(*, login_url: str, wait_for_user: object) -> bytes:
        return STORAGE_STATE

    return EZProxyProvider(EZPROXY_PROFILE, store, clock=FakeClock(), login_flow=login_flow)


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        (  # 基本重写（§3.4 泛化规则：host '.'→'-' + 后缀；路径/查询/片段保留）
            "https://www.sciencedirect.com/science/article/pii/S0304?via=ihub#sec1",
            "https://www-sciencedirect-com.login-myuniv-edu.ezproxy"
            "/science/article/pii/S0304?via=ihub#sec1",
        ),
        (  # 子域
            "https://api.elsevier.com/content/article/doi/10.1016/j.jfineco.2011.03.021",
            "https://api-elsevier-com.login-myuniv-edu.ezproxy"
            "/content/article/doi/10.1016/j.jfineco.2011.03.021",
        ),
        (  # 端口保留
            "https://example.com:8443/paper.pdf",
            "https://example-com.login-myuniv-edu.ezproxy:8443/paper.pdf",
        ),
        ("http://x.y.z.example.org/", "http://x-y-z-example-org.login-myuniv-edu.ezproxy/"),
    ],
)
def test_ezproxy_rewrite_url_table(ezproxy: EZProxyProvider, url: str, expected: str) -> None:
    assert ezproxy.rewrite_url(url) == expected


def test_ezproxy_rewrite_idempotent(ezproxy: EZProxyProvider) -> None:
    once = ezproxy.rewrite_url("https://www.sciencedirect.com/science/article/pii/X")
    assert ezproxy.rewrite_url(once) == once  # 已重写幂等（重复套代理会毁 URL）


@pytest.mark.parametrize("url", ["mailto:me@example.org", "/relative/path", "not a url", ""])
def test_ezproxy_rewrite_no_host_identity(ezproxy: EZProxyProvider, url: str) -> None:
    assert ezproxy.rewrite_url(url) == url


def test_ezproxy_rewrite_suffix_without_leading_dot_normalized(store: CredentialStore) -> None:
    profile = ProviderProfile(
        provider_id="p@ez",
        kind="ezproxy",
        platform="x",
        proxy_base="https://login.myuniv.edu/login?url=",
        rewrite_suffix="ezproxy.myuniv.edu",
        state_ref="ez_state",
    )
    provider = EZProxyProvider(profile, store)
    assert (
        provider.rewrite_url("https://example.com/a") == "https://example-com.ezproxy.myuniv.edu/a"
    )


def test_ezproxy_first_login_opens_proxy_base_and_persists(store: CredentialStore) -> None:
    calls: list[str] = []

    def login_flow(*, login_url: str, wait_for_user: object) -> bytes:
        calls.append(login_url)
        return STORAGE_STATE

    provider = EZProxyProvider(EZPROXY_PROFILE, store, clock=FakeClock(), login_flow=login_flow)
    with pytest.raises(AuthRequired):
        provider.ensure_session()
    handle = provider.ensure_session(interactive=True)
    assert calls == ["https://login.myuniv.edu/login?url="]  # §4.1：打开 proxy_base
    assert handle.backend is SessionBackend.HTTPX_COOKIES
    assert (store.state_dir / "ezproxy_myuniv_state.enc").is_file()


def test_ezproxy_health_presence_and_refresh_none(
    ezproxy: EZProxyProvider, store: CredentialStore
) -> None:
    handle = ezproxy.ensure_session(interactive=True)
    assert ezproxy.health_check(handle) is HealthStatus.OK
    assert ezproxy.refresh(handle) is None
    ezproxy.invalidate(handle)
    assert ezproxy.health_check(handle) is HealthStatus.EXPIRED
    assert not (store.state_dir / "ezproxy_myuniv_state.enc").exists()


# ---------------------------------------------------------------------------
# 覆盖补全：默认时钟/默认 http_factory/storage_state 边界/ezproxy 复用与惰性首登
# ---------------------------------------------------------------------------


def test_default_clock_used_when_not_injected(home: Path, store: CredentialStore) -> None:
    store.bind_config(make_config(home, elsevier_api_key=SECRET_KEY))
    api_handle = ApiKeyProvider(API_PROFILE, store).ensure_session()
    assert api_handle.established_at.tzinfo is not None  # aware UTC now

    def login_flow(*, login_url: str, wait_for_user: object) -> bytes:
        return STORAGE_STATE

    cookie = CookieSessionProvider(COOKIE_PROFILE, store, login_flow=login_flow)
    cookie_handle = cookie.ensure_session(interactive=True)
    assert cookie_handle.established_at.tzinfo is not None
    ez = EZProxyProvider(EZPROXY_PROFILE, store, login_flow=login_flow)
    ez_handle = ez.ensure_session(interactive=True)
    assert ez_handle.established_at.tzinfo is not None


def test_default_http_factory_dedicated_client_with_ua() -> None:
    """默认探针 client：专属实例（凭证隔离）+ D-014 UA；不发任何请求。"""
    from paper_crawler.auth.providers.cookie_session import _default_http_factory

    jar = httpx.Cookies()
    jar.set("sid", "v", domain="mock.test")
    client = _default_http_factory(jar)
    try:
        assert isinstance(client, httpx.Client)
        assert client.headers["User-Agent"].startswith("PaperCrawler/")
        assert client.cookies.get("sid", domain="mock.test") == "v"
    finally:
        client.close()


def test_storage_state_skips_malformed_entries() -> None:
    doc = {
        "cookies": [
            "not-a-dict",
            {"name": 123, "value": "x"},
            {"name": "ok", "value": "yes", "domain": ".mock.test"},
        ]
    }
    jar = storage_state_to_cookies(json.dumps(doc).encode())
    assert len(jar) == 1
    assert jar.get("ok", domain="mock.test") == "yes"  # 前导点归一


def test_cookies_to_storage_state_preserves_expires() -> None:
    from http.cookiejar import Cookie

    jar = httpx.Cookies()
    jar.jar.set_cookie(
        Cookie(
            version=0,
            name="sid",
            value="v",
            port=None,
            port_specified=False,
            domain="mock.test",
            domain_specified=True,
            domain_initial_dot=False,
            path="/",
            path_specified=True,
            secure=True,
            expires=1893456000,
            discard=False,
            comment=None,
            comment_url=None,
            rest={},
        )
    )
    state = json.loads(cookies_to_storage_state(jar).decode())
    assert state["cookies"][0]["expires"] == 1893456000
    assert state["cookies"][0]["secure"] is True


def test_ezproxy_ensure_session_reuses_persisted_state(store: CredentialStore) -> None:
    clock = FakeClock()

    def login_flow(*, login_url: str, wait_for_user: object) -> bytes:
        return STORAGE_STATE

    provider = EZProxyProvider(EZPROXY_PROFILE, store, clock=clock, login_flow=login_flow)
    first = provider.ensure_session(interactive=True)
    clock.advance(hours=2)
    again = provider.ensure_session()  # 复用：established 取 meta，非 now
    assert again.established_at == first.established_at
    assert again.est_ttl == timedelta(hours=12)


def test_ezproxy_default_login_flow_is_lazy_browser_seam(
    store: CredentialStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    import paper_crawler.auth.browser as browser_mod

    calls: list[str] = []

    def fake(*, login_url: str, wait_for_user: object, launch: object = None) -> bytes:
        calls.append(login_url)
        return STORAGE_STATE

    monkeypatch.setattr(browser_mod, "run_headed_login", fake)
    provider = EZProxyProvider(EZPROXY_PROFILE, store, clock=FakeClock())  # login_flow 缺省
    provider.ensure_session(interactive=True)
    assert calls == ["https://login.myuniv.edu/login?url="]


def test_ezproxy_rewrite_uppercase_host_normalized(ezproxy: EZProxyProvider) -> None:
    """审查 NIT-1：大写 host 归一小写后重写（urlsplit.hostname 语义显式锁定）。"""
    rewritten = ezproxy.rewrite_url("HTTPS://WWW.ScienceDirect.COM/science/Article/pii/X")
    assert rewritten == (
        "https://www-sciencedirect-com.login-myuniv-edu.ezproxy/science/Article/pii/X"
    )  # host 归一小写；路径大小写保留
    assert ezproxy.rewrite_url(rewritten) == rewritten  # 归一后幂等仍成立


# proxy cookie 种在**代理父域**（EZProxy 真实形态）；重写后的 host 是它的子域。
PROXY_STORAGE_STATE = json.dumps(
    {
        "cookies": [
            {
                "name": "ezproxy",
                "value": SECRET_COOKIE,
                "domain": "login-myuniv-edu.ezproxy",
                "path": "/",
                "secure": True,
            }
        ],
        "origins": [],
    }
).encode("utf-8")


def test_ezproxy_load_cookies_exports_jar(store: CredentialStore) -> None:
    """P1-11 接线：`load_cookies` 把加密 proxy state 解成 httpx cookie jar（HTTPX_COOKIES
    后端的兑现——此前该后端声明无导出面，CookieSupplier seam 对 ezproxy 直接 CONFIG 报错）。"""
    provider = EZProxyProvider(
        EZPROXY_PROFILE,
        store,
        clock=FakeClock(),
        login_flow=lambda **_kwargs: PROXY_STORAGE_STATE,
    )
    handle = provider.ensure_session(interactive=True)
    jar = provider.load_cookies(handle)
    assert jar.get("ezproxy", domain="login-myuniv-edu.ezproxy") == SECRET_COOKIE


def test_ezproxy_proxy_cookie_matches_rewritten_host(store: CredentialStore) -> None:
    """cookie 域匹配（本卡关键判据）：代理父域的 cookie 会随**改写后**的请求发出。

    改写把 `www.sciencedirect.com` 变成代理父域的子域，故 jar 的 Netscape 域匹配成立——
    改写与 cookie 注入两条通路在同一个 host 上闭合，代理请求才真的是"已认证"的。
    """
    provider = EZProxyProvider(
        EZPROXY_PROFILE,
        store,
        clock=FakeClock(),
        login_flow=lambda **_kwargs: PROXY_STORAGE_STATE,
    )
    handle = provider.ensure_session(interactive=True)
    jar = provider.load_cookies(handle)

    proxied = provider.rewrite_url("https://www.sciencedirect.com/science/article/pii/X.pdf")
    request = httpx.Request("GET", proxied)
    jar.set_cookie_header(request)
    assert SECRET_COOKIE in request.headers.get("cookie", "")

    # 对照：未改写的原始 host 不匹配代理域 → 不携带（正是"接线前"的失效形态）
    direct = httpx.Request("GET", "https://www.sciencedirect.com/science/article/pii/X.pdf")
    jar.set_cookie_header(direct)
    assert "cookie" not in direct.headers
