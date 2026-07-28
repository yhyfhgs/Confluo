"""OUP cookie 供给 seam 生产装配集成（auth-framework §8.2；MAJOR-1 修复的离线载体）。

背景（fable 全分支终审 MAJOR-1）：`_assemble_auth_seam` 曾留"OUP 合入后补一行注入"的
TODO 却从未执行——`oup_silverchair` 的 `set_cookie_supplier` 零生产调用点，真实 OUP 取回
会在 `_cookies_for` 抛 `CONFIG "oup cookie 供给 seam 未装配"`。本文件证明修复后：

  ① `_assemble_auth_seam` 后 oup adapter 的 cookie supplier 已注入（非 None）——DoD ①；
  ② supplier 被调用时经 `AuthManager.resolve`→`load_cookies` 解密 storage_state 返 cookie
     dict（真实 CookieSessionProvider + 假加密 state）——DoD ②；
  ③ 装配期无凭证配置不抛 CONFIG（懒解析：闭包装配期不解析，仅真实 fetch 触达才解析）——DoD ③；
  ④ 端到端（离线）：装配出的同一 `_cookie_supplier_for` 闭包把 AES-GCM 解密的 cookie 喂进真实
     OUP adapter 的专属 client，resolve 产出 PDF plan（不抛 CONFIG）且域限定穿过装配链保持
     （doi.org 首跳不带 cookie）。真实 SSO 端到端（首登/风控）仍归 T7b。

零真实网络（httpx.MockTransport + tests/conftest.py 全局 socket 护栏）、零真实 keyring
（`_isolated` autouse → filekey 降级，沿 tests/unit/test_auth_manager.py 先例）。
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

import paper_crawler.auth.store as store_mod
from helpers import FakeFetchIO, make_oup_venue
from helpers.auth import make_config
from integration.conftest import AUTH_T0, AuthClock, storage_state_bytes
from paper_crawler.adapter import load_adapters
from paper_crawler.adapters.oup_silverchair.adapter import OupSilverchairAdapter
from paper_crawler.auth.manager import AuthManager
from paper_crawler.cli import (
    _assemble_auth_seam,
    _cookie_supplier_for,
    _host_matches_cookie_domain,
    _url_rewriter_for,
)
from paper_crawler.errors import AuthRequired, CrawlerError, ErrorClass
from paper_crawler.http import HttpClient
from paper_crawler.pipeline import StageContext
from paper_crawler.ratelimit import RateLimiter
from paper_crawler.registry import VenueRegistry
from paper_crawler.storage.db import Database
from paper_crawler.storage.repo import Repo
from paper_crawler.tasks import TaskQueue
from paper_crawler.types import AssetKind, AssetPlan, PaperStub, SessionBackend, SessionHandle

_STATE_REF = "oup_campus_state"
_COOKIE_NAME = "SILVERCHAIR_SESSION"
_COOKIE_VALUE = "sess-cookie-xyz"

OUP_COOKIE_PROFILE = """\
schema_version = 1

[providers."oup@campus"]
kind = "cookie_session"
platform = "oup_silverchair"
login_url = "https://mock.test/login"
probe_url = "https://academic.oup.com/my-account"
state_ref = "oup_campus_state"
est_ttl_hours = 24
"""

# api_key profile（无 load_cookies）——供"非 cookie provider → CONFIG"的负向分支。
APIKEY_PROFILE = """\
schema_version = 1

[providers.elsevier]
kind = "api_key"
platform = "elsevier_sd"
key_ref = "elsevier_apikey"
"""

# ezproxy profile（R3e）：同一 oup 平台改走校外代理——rewrite_suffix 与 proxy cookie 的
# 代理父域对齐（EZProxy 真实形态，见 tests/unit/test_auth_providers.py 的同名常量）。
EZPROXY_PROFILE = """\
schema_version = 1

[providers."oup@ezproxy"]
kind = "ezproxy"
platform = "oup_silverchair"
proxy_base = "https://login.myuniv.edu/login?url="
rewrite_suffix = ".login-myuniv-edu.ezproxy"
state_ref = "oup_ezproxy_state"
est_ttl_hours = 12
"""

_EZPROXY_STATE_REF = "oup_ezproxy_state"
_PROXY_COOKIE_NAME = "ezproxy"
_PROXY_COOKIE_VALUE = "proxy-sess-abc"
_PROXY_PARENT_DOMAIN = "login-myuniv-edu.ezproxy"
_PLATFORM_PDF_URL = "https://academic.oup.com/qje/article-pdf/141/3/2205/6170/qjae044.pdf"


@pytest.fixture(autouse=True)
def _isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(store_mod, "_import_keyring", lambda: None)
    monkeypatch.setattr(store_mod, "_filekey_warned", True)
    monkeypatch.chdir(tmp_path)


def _home(tmp_path: Path, profile_toml: str | None) -> Path:
    """隔离 HOME；`profile_toml=None` = 不写 profiles.toml（无凭证配置形态）。"""
    home = tmp_path / "home"
    (home / "auth").mkdir(mode=0o700, parents=True)
    if profile_toml is not None:
        (home / "auth" / "profiles.toml").write_text(profile_toml, encoding="utf-8")
    return home


def _assemble(config: object, adapters: dict[str, object]) -> AuthManager:
    """跑真实 `_assemble_auth_seam`（离线 http），装配后即释放 db/http；manager 独立存续。

    `adapters` 原地被注入 supplier——调用方经 `adapters["oup_silverchair"]` 断言。
    """
    db = Database(config.db_path)  # type: ignore[attr-defined]
    db.migrate()
    try:
        limiter = RateLimiter(scale=config.rate_scale)  # type: ignore[attr-defined]
        ctx = StageContext(
            config=config,  # type: ignore[arg-type]
            db=db,
            repo=Repo(db),
            registry=VenueRegistry(adapters),  # type: ignore[arg-type]
            queue=TaskQueue(db),
            limiter=limiter,
        )
        http = HttpClient(
            user_agent="pc-test",
            transport=httpx.MockTransport(lambda _r: httpx.Response(200, content=b"%PDF-1.4")),
        )
        try:
            return _assemble_auth_seam(config, adapters, ctx, http, limiter)  # type: ignore[arg-type]
        finally:
            http.close()
    finally:
        db.close()


def _session(provider_id: str = "oup@campus", ref: str = _STATE_REF) -> SessionHandle:
    return SessionHandle(
        provider_id=provider_id,
        backend=SessionBackend.HTTPX_COOKIES,
        payload_ref=ref,
        established_at=AUTH_T0,
    )


def _paper(doi: str = "10.1093/qje/qjae044") -> PaperStub:
    return PaperStub(title="A Synthetic Placeholder Article", identifiers=(("doi", doi),))


def _mixed_domain_state() -> bytes:
    """一份同时含**代理父域** cookie 与**平台主域** cookie 的 storage_state（R3e 隔离判据）。

    真实校外形态里 storage_state 是一次浏览器首登的全量快照，可能同时含多域条目——seam
    必须按请求 host 交付，而不是把整表倒给消费方再由消费方硬钉一个域。
    """
    return json.dumps(
        {
            "cookies": [
                {
                    "name": _PROXY_COOKIE_NAME,
                    "value": _PROXY_COOKIE_VALUE,
                    "domain": _PROXY_PARENT_DOMAIN,
                    "path": "/",
                    "secure": True,
                },
                {
                    "name": _COOKIE_NAME,
                    "value": _COOKIE_VALUE,
                    "domain": "academic.oup.com",
                    "path": "/",
                    "secure": True,
                },
            ],
            "origins": [],
        },
        ensure_ascii=False,
    ).encode("utf-8")


# ---------------------------------------------------------------------------
# ① 装配后 supplier 已注入（非 None） / ③ 无凭证配置装配不抛
# ---------------------------------------------------------------------------


def test_assemble_wires_cookie_supplier_into_oup_adapter(tmp_path: Path) -> None:
    """DoD ①：`_assemble_auth_seam`（真实 load_adapters）后 oup adapter 的 supplier 非 None。"""
    config = make_config(_home(tmp_path, OUP_COOKIE_PROFILE))
    adapters = load_adapters()
    assert isinstance(adapters["oup_silverchair"], OupSilverchairAdapter)
    assert adapters["oup_silverchair"]._cookie_supplier is None  # 装配前：无参构造 → None

    _assemble(config, adapters)

    assert adapters["oup_silverchair"]._cookie_supplier is not None  # 装配后：已注入


def test_assemble_no_credentials_does_not_raise(tmp_path: Path) -> None:
    """DoD ③：无 profiles.toml（无凭证配置）时装配不抛——supplier 仍注入但装配期零 provider 解析。"""
    config = make_config(_home(tmp_path, None))
    adapters = load_adapters()

    manager = _assemble(config, adapters)  # 不抛（懒解析：闭包装配期不解析）

    assert adapters["oup_silverchair"]._cookie_supplier is not None
    assert manager.providers() == {}  # 无凭证配置：注册表空，装配期未触碰 provider


# ---------------------------------------------------------------------------
# ② supplier 经 AuthManager.resolve→load_cookies 返回 cookie dict
# ---------------------------------------------------------------------------


def test_supplier_resolves_via_authmanager_load_cookies(tmp_path: Path) -> None:
    """DoD ②：supplier(session, host) → resolve(oup@campus) → load_cookies 解密假 state → dict。"""
    config = make_config(_home(tmp_path, OUP_COOKIE_PROFILE))
    manager = AuthManager(config, clock=AuthClock())
    # 真实 AES-GCM 加密落盘（keyring 已绝缘 → filekey）：假 storage_state。
    manager.store.write_state(
        _STATE_REF,
        storage_state_bytes(_COOKIE_VALUE, domain="academic.oup.com", name=_COOKIE_NAME),
    )
    supplier = _cookie_supplier_for(manager)

    cookies = supplier(_session(), "academic.oup.com")

    assert cookies == {_COOKIE_NAME: _COOKIE_VALUE}  # 解密 → name→value dict


def test_supplier_is_lazy_resolves_only_on_call(tmp_path: Path) -> None:
    """DoD ③（懒解析时机）：闭包构造不解析；仅被调用时才 resolve→load_cookies→read_state。

    无 state 落盘 → 调用时 read_state 缺 `.enc` → AuthRequired（证明解析发生在调用时，非构造时）。
    """
    config = make_config(_home(tmp_path, OUP_COOKIE_PROFILE))
    manager = AuthManager(config, clock=AuthClock())
    supplier = _cookie_supplier_for(manager)  # 构造：不触 provider/加密面

    with pytest.raises(AuthRequired):  # 调用时才解析并读 state（缺 → AuthRequired）
        supplier(_session(), "academic.oup.com")


def test_supplier_non_cookie_provider_is_config_error(tmp_path: Path) -> None:
    """cookie 档 venue 却映射到非 cookie provider（api_key，无 load_cookies）→ 响亮 CONFIG。"""
    config = make_config(_home(tmp_path, APIKEY_PROFILE))
    manager = AuthManager(config, clock=AuthClock())
    supplier = _cookie_supplier_for(manager)

    with pytest.raises(CrawlerError) as exc:
        supplier(_session(provider_id="elsevier", ref="elsevier_apikey"), "academic.oup.com")
    assert exc.value.error_class is ErrorClass.CONFIG
    assert "load_cookies" in str(exc.value)


# ---------------------------------------------------------------------------
# ④ 端到端（离线）：装配闭包 → 真实 OUP adapter 专属 client → PDF plan，无 CONFIG，域限定保持
# ---------------------------------------------------------------------------


def test_assembled_supplier_feeds_oup_adapter_resolve_offline(tmp_path: Path) -> None:
    """端到端离线证据：`_cookie_supplier_for(manager)` 闭包（= 装配注入的同一函数）把 AES-GCM
    解密的 cookie 喂进真实 OUP adapter 专属 client → resolve 产 PDF plan（**不抛 CONFIG**）；
    且 cookie 域限定穿过装配链保持——doi.org 首跳不带 cookie，academic.oup.com 才带。"""
    config = make_config(_home(tmp_path, OUP_COOKIE_PROFILE))
    manager = AuthManager(config, clock=AuthClock())
    manager.store.write_state(
        _STATE_REF,
        storage_state_bytes(_COOKIE_VALUE, domain="academic.oup.com", name=_COOKIE_NAME),
    )
    supplier = _cookie_supplier_for(manager)

    seen: dict[str, str | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen[request.url.host] = request.headers.get("cookie")
        if request.url.host == "doi.org":
            return httpx.Response(
                302, headers={"Location": "https://academic.oup.com/qje/article/1/1/1/1"}
            )
        body = (
            b'<html><head><meta name="citation_pdf_url" '
            b'content="https://academic.oup.com/qje/article-pdf/1/1/1/F/x.pdf"/></head>'
            b"<body><a href='/user/logout'>Sign out</a></body></html>"
        )
        return httpx.Response(200, content=body)

    adapter = OupSilverchairAdapter(transport=httpx.MockTransport(handler))
    adapter.set_cookie_supplier(supplier)  # = bind_cookie_supplier 注入的同一闭包
    plans = adapter.resolve_assets(make_oup_venue(), _paper(), session=_session())

    assert plans and plans[0].kind is AssetKind.PDF  # 装配完整、无 CONFIG 抛出
    assert seen["doi.org"] is None  # 凭证不泄漏 DOI 解析器（域限定穿过装配链保持）
    assert f"{_COOKIE_NAME}={_COOKIE_VALUE}" in (seen["academic.oup.com"] or "")


# ---------------------------------------------------------------------------
# R3e：seam 携域信息——ezproxy 形态下改写后的 host 拿到 proxy cookie（R2d 顾虑①收口）
# ---------------------------------------------------------------------------


def _ezproxy_manager(tmp_path: Path) -> AuthManager:
    """装好 ezproxy profile + 混域 storage_state（真实 AES-GCM 落盘）的 manager。"""
    config = make_config(_home(tmp_path, EZPROXY_PROFILE))
    manager = AuthManager(config, clock=AuthClock())
    manager.store.write_state(_EZPROXY_STATE_REF, _mixed_domain_state())
    return manager


def _ezproxy_session() -> SessionHandle:
    return _session(provider_id="oup@ezproxy", ref=_EZPROXY_STATE_REF)


@pytest.mark.parametrize(
    ("host", "domain", "expected"),
    [
        ("academic.oup.com", "academic.oup.com", True),  # 精确相等
        ("academic-oup-com.login-myuniv-edu.ezproxy", "login-myuniv-edu.ezproxy", True),  # 子域
        ("ACADEMIC.OUP.COM.", ".academic.oup.com", True),  # 大小写/前导点/尾点归一
        ("doi.org", "academic.oup.com", False),  # 无关域
        ("evil-academic.oup.com.attacker.test", "academic.oup.com", False),  # 后缀不等于子域
        ("academic.oup.com", "", False),  # 畸形条目（缺 domain）→ 不外发
        ("", "academic.oup.com", False),  # 无 host → 不外发
    ],
)
def test_host_matches_cookie_domain_rules(host: str, domain: str, expected: bool) -> None:
    """简化版 RFC 6265 域匹配的逐条判据（`_cookie_supplier_for` 过滤所依赖的唯一规则）。"""
    assert _host_matches_cookie_domain(host, domain) is expected


def test_supplier_filters_cookies_by_request_host(tmp_path: Path) -> None:
    """seam 的域信息不再在类型面被丢弃：`supplier(session, host)` 按 host 过滤 provider jar。

    修复前签名是 `supplier(session)` → 整张表（跨域混装）交给消费方，消费方只能硬钉一个域。
    """
    supplier = _cookie_supplier_for(_ezproxy_manager(tmp_path))
    proxy_host = "academic-oup-com.login-myuniv-edu.ezproxy"

    assert supplier(_ezproxy_session(), proxy_host) == {_PROXY_COOKIE_NAME: _PROXY_COOKIE_VALUE}
    assert supplier(_ezproxy_session(), "academic.oup.com") == {_COOKIE_NAME: _COOKIE_VALUE}
    assert supplier(_ezproxy_session(), "doi.org") == {}  # 无关域零凭证（防泄漏）


def test_assembled_supplier_feeds_proxy_cookie_on_rewritten_host(tmp_path: Path) -> None:
    """端到端（离线）：ezproxy 形态下 fetch 的实发请求带 **proxy cookie**——R2d 接线的
    `rewrite_url` 与本卡的域感知 cookie 供给在**同一个 host 上闭合**。

    链路与生产一致：`AuthManager.resolve(provider).rewrite_url`（= pipeline
    `_url_rewriter_of`→`_proxy_rewritten` 施加于 plan.url 的同一函数）→ 真实 OUP adapter
    专属 client。修复前：adapter 把 supplier 交出的 cookie 硬钉 `academic.oup.com`，代理域
    请求域匹配失败 → `Cookie` 头为空（凭证被丢、裸发 → 落代理登录页）。
    """
    manager = _ezproxy_manager(tmp_path)
    supplier = _cookie_supplier_for(manager)
    provider = manager.resolve("oup@ezproxy")
    proxied_url = provider.rewrite_url(_PLATFORM_PDF_URL)  # 生产同一改写函数
    assert proxied_url != _PLATFORM_PDF_URL  # 前提自检：确已改写到代理域

    seen: dict[str, str | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen[request.url.host] = request.headers.get("cookie")
        return httpx.Response(
            200, content=b"%PDF-1.7\ncontent\n%%EOF\n", headers={"content-type": "application/pdf"}
        )

    adapter = OupSilverchairAdapter(transport=httpx.MockTransport(handler))
    adapter.set_cookie_supplier(supplier)  # = bind_cookie_supplier 注入的同一闭包

    result = adapter.fetch_asset(
        AssetPlan(kind=AssetKind.PDF, url=proxied_url), FakeFetchIO(), session=_ezproxy_session()
    )

    proxy_host = httpx.URL(proxied_url).host
    assert result.ok is True
    assert f"{_PROXY_COOKIE_NAME}={_PROXY_COOKIE_VALUE}" in (seen[proxy_host] or "")
    # 隔离：同一份 state 里的平台主域 cookie 不外发到代理域
    assert _COOKIE_VALUE not in (seen[proxy_host] or "")


# ---------------------------------------------------------------------------
# R2c：`_assemble_auth_seam` 同一装配也须注入联系邮箱（`EmailConsumer`，UA `mailto:` 段）
# ---------------------------------------------------------------------------


def test_assemble_wires_email_into_oup_adapter(tmp_path: Path) -> None:
    """`_assemble_auth_seam` 后 oup adapter 的 `_email` = `Config.identity_email`（非 None）。

    修复前：`_assemble_auth_seam` 只对 unpaywall 做 `EmailConsumer` 注入，oup 完全没有
    对应分支——即便用户配了 `[identity].email`，oup 的 UA 也恒是匿名占位（P1-17 根因）。
    本用例证明修复后 oup 也被同一次装配覆盖到（经通用 `_bind_email`，非逐 adapter 硬编码）。
    """
    config = make_config(
        _home(tmp_path, OUP_COOKIE_PROFILE), identity_email="researcher@example.edu"
    )
    adapters = load_adapters()
    assert isinstance(adapters["oup_silverchair"], OupSilverchairAdapter)
    assert adapters["oup_silverchair"]._email is None  # 装配前：无参构造 → None

    _assemble(config, adapters)

    assert adapters["oup_silverchair"]._email == "researcher@example.edu"


def test_assemble_with_no_identity_email_leaves_oup_email_none(tmp_path: Path) -> None:
    """未配置 `[identity].email` → 装配仍调用 `set_email(None)`（不注入亦不报错），oup
    随后在真实请求时按既有回退链（env→占位）自行兜底——`_resolve_email` 的职责，不在此断言。
    """
    config = make_config(_home(tmp_path, OUP_COOKIE_PROFILE))
    assert config.identity_email is None
    adapters = load_adapters()

    _assemble(config, adapters)

    assert adapters["oup_silverchair"]._email is None


# ---------------------------------------------------------------------------
# R3f：resolve 侧 URL 改写 seam 生产装配（R3e 顾虑④裁决"接通"，完成 ezproxy 端到端闭环）
# ---------------------------------------------------------------------------


def test_assemble_wires_url_rewriter_when_ezproxy_profile_configured(tmp_path: Path) -> None:
    """DoD：ezproxy profile 配置时，`_assemble_auth_seam` 后 oup adapter 的 `_url_rewriter`
    非 None（修复前该属性/seam 都不存在，resolve 恒裸发平台真实域）。"""
    config = make_config(_home(tmp_path, EZPROXY_PROFILE))
    adapters = load_adapters()
    assert isinstance(adapters["oup_silverchair"], OupSilverchairAdapter)
    assert adapters["oup_silverchair"]._url_rewriter is None  # 装配前：无参构造 → None

    _assemble(config, adapters)

    assert adapters["oup_silverchair"]._url_rewriter is not None  # 装配后：已注入


def test_assemble_wires_url_rewriter_unconditionally_without_ezproxy_profile(
    tmp_path: Path,
) -> None:
    """controller 复审裁决"改懒"后的新契约：`_bind_url_rewriter` **无条件**装配（同
    `bind_cookie_supplier` 风格），即便只配置了 cookie_session（无 ezproxy）——`_url_rewriter`
    装配后仍非 None。是否真的存在 ezproxy provider 这一问被推迟到闭包真正被调用时才按
    `session.provider_id` 判定（见 `test_assemble_does_not_eagerly_read_profiles_toml_...`：
    这次装配本身不读 `profiles.toml`）；对非 ezproxy session，`AuthProviderBase.rewrite_url`
    恒等，闭包空操作，行为不受影响（见
    `test_cookie_session_resolve_unaffected_by_unconditionally_bound_rewriter` 的端到端证据）。
    """
    config = make_config(_home(tmp_path, OUP_COOKIE_PROFILE))
    adapters = load_adapters()

    _assemble(config, adapters)

    assert adapters["oup_silverchair"]._url_rewriter is not None


def test_assemble_wires_url_rewriter_without_any_credentials(tmp_path: Path) -> None:
    """无 profiles.toml（无凭证配置）→ 仍无条件装配、不抛（同 DoD③"无凭证配置装配不抛"的
    同一精神，扩到本 seam：闭包捕获的是 `manager`，构造闭包本身不触碰 `profiles.toml`）。"""
    config = make_config(_home(tmp_path, None))
    adapters = load_adapters()

    _assemble(config, adapters)  # 不抛

    assert adapters["oup_silverchair"]._url_rewriter is not None


def test_assemble_does_not_eagerly_read_profiles_toml_for_url_rewriter(tmp_path: Path) -> None:
    """核心裁决点的直接证据：装配期本身**不读** `profiles.toml`——用一份语法损坏的
    `profiles.toml` 证明。若装配期仍先扫一遍 `manager.profiles()` 判断"要不要装配"（R3f
    初版的写法），`CredentialStore.load_profiles()` 会在此刻就因 TOML 语法错误
    `CrawlerError(CONFIG)`，导致**与本次 pull 完全无关**的装配步骤连带失败；改懒后装配
    压根不碰这份文件的解析，不抛（`AuthManager.__init__` 本就不预读 profiles，构造闭包
    `_url_rewriter_for(manager)` 与 `bind_cookie_supplier` 也都只捕获引用、不解析）。"""
    home = _home(tmp_path, "not valid toml [[[\n")  # 语法损坏：真实解析会 TOMLDecodeError
    config = make_config(home)
    adapters = load_adapters()

    _assemble(config, adapters)  # 不抛：装配期从未触碰这份损坏文件的解析

    assert adapters["oup_silverchair"]._url_rewriter is not None  # 但闭包仍（无条件）已注入


def test_cookie_session_resolve_unaffected_by_unconditionally_bound_rewriter(
    tmp_path: Path,
) -> None:
    """安全网（改懒→无条件装配后必须补的证据）：`_url_rewriter` 现在对**任何**已装配 session
    都非 None（含纯 cookie_session、无 ezproxy），但 `AuthProviderBase.rewrite_url` 恒等——
    resolve 全链（含 R3f 新增的 doi.org 手工两段式探路，见 adapter 模块 docstring）产出与
    "完全不装配 rewriter"逐字一致的结果：落地请求仍打 `academic.oup.com` 本尊（不是某个被
    误改写的怪异域），cookie 仍正确命中平台域，从未出现第三个未预期的 host。"""
    config = make_config(_home(tmp_path, OUP_COOKIE_PROFILE))
    manager = AuthManager(config, clock=AuthClock())
    manager.store.write_state(
        _STATE_REF,
        storage_state_bytes(_COOKIE_VALUE, domain="academic.oup.com", name=_COOKIE_NAME),
    )
    cookie_supplier = _cookie_supplier_for(manager)
    url_rewriter = _url_rewriter_for(manager)  # = `_bind_url_rewriter` 现在无条件注入的同一闭包

    seen: dict[str, str | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen[request.url.host] = request.headers.get("cookie")
        if request.url.host == "doi.org":
            return httpx.Response(
                302, headers={"Location": "https://academic.oup.com/qje/article/1/1/1/1"}
            )
        body = (
            b'<html><head><meta name="citation_pdf_url" '
            b'content="https://academic.oup.com/qje/article-pdf/1/1/1/F9/x.pdf"/></head>'
            b"<body><a href='/user/logout'>Sign out</a></body></html>"
        )
        return httpx.Response(200, content=body)

    adapter = OupSilverchairAdapter(transport=httpx.MockTransport(handler))
    adapter.set_cookie_supplier(cookie_supplier)
    adapter.set_url_rewriter(url_rewriter)  # 无条件装配后，非 ezproxy session 也会收到此注入

    plans = adapter.resolve_assets(make_oup_venue(), _paper(), session=_session())

    assert plans and plans[0].kind is AssetKind.PDF
    assert seen["doi.org"] is None
    assert f"{_COOKIE_NAME}={_COOKIE_VALUE}" in (seen["academic.oup.com"] or "")
    assert set(seen) == {"doi.org", "academic.oup.com"}  # 从未落到任何被误改写的域


def test_url_rewriter_closure_delegates_to_resolved_provider_rewrite_url(tmp_path: Path) -> None:
    """闭包 `(session, url)` → `manager.resolve(session.provider_id).rewrite_url(url)`——
    与 pipeline `_url_rewriter_of`→`_proxy_rewritten` 施加于 `plan.url` 的同一条真实规则
    （同一 provider 实例、同一方法），只是触发时机换成 CLI 装配的懒解析闭包（风格照抄
    `_cookie_supplier_for`）。"""
    manager = _ezproxy_manager(tmp_path)
    rewriter = _url_rewriter_for(manager)
    provider = manager.resolve("oup@ezproxy")

    rewritten = rewriter(_ezproxy_session(), _PLATFORM_PDF_URL)

    assert rewritten == provider.rewrite_url(_PLATFORM_PDF_URL)
    assert rewritten != _PLATFORM_PDF_URL  # 前提自检：确已改写到代理域


def test_assembled_rewriter_and_cookie_supplier_close_ezproxy_resolve_loop(tmp_path: Path) -> None:
    """端到端（离线）：oup resolve 的 doi.org 首跳落地请求经 R3f 装配的 rewriter 改写到代理域，
    R3e 装配的域感知 cookie supplier 在该改写后的 host 上命中 **proxy cookie**——两条 R3
    系列 seam 在同一个 host 上闭合，ezproxy 场景的 resolve 全链不再裸打出版社真实域。

    修复前：`_assemble_auth_seam` 没有本卡新增的 rewriter 装配分支，resolve 的落地请求会
    径直落 `academic.oup.com`（真实域，校外网络多半连不通/撞验证墙），也就永远问不到代理域
    这个 cookie 归属 host——本用例在修复前会因 `seen` 缺失 `proxy_host` 这个 key（mock
    对未预期 host 返 404，落地解析随之失败）而失败。
    """
    manager = _ezproxy_manager(tmp_path)
    cookie_supplier = _cookie_supplier_for(manager)
    url_rewriter = _url_rewriter_for(manager)
    proxy_host = httpx.URL(manager.resolve("oup@ezproxy").rewrite_url(_PLATFORM_PDF_URL)).host

    seen: dict[str, str | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen[request.url.host] = request.headers.get("cookie")
        if request.url.host == "doi.org":
            return httpx.Response(
                302, headers={"Location": "https://academic.oup.com/qje/article/1/1/1/1"}
            )
        if request.url.host == proxy_host:
            body = (
                b'<html><head><meta name="citation_pdf_url" '
                b'content="https://academic.oup.com/qje/article-pdf/1/1/1/F9/x.pdf"/></head>'
                b"<body><a href='/user/logout'>Sign out</a></body></html>"
            )
            return httpx.Response(200, content=body)
        return httpx.Response(404, content=b"unexpected host: rewriter seam not wired")

    adapter = OupSilverchairAdapter(transport=httpx.MockTransport(handler))
    adapter.set_cookie_supplier(cookie_supplier)  # = bind_cookie_supplier 注入的同一闭包
    adapter.set_url_rewriter(url_rewriter)  # = _bind_url_rewriter 注入的同一闭包

    plans = adapter.resolve_assets(make_oup_venue(), _paper(), session=_ezproxy_session())

    assert plans and plans[0].kind is AssetKind.PDF
    assert seen["doi.org"] is None  # 首跳零 cookie：凭证防泄漏红线在 rewriter 在场时仍成立
    assert f"{_PROXY_COOKIE_NAME}={_PROXY_COOKIE_VALUE}" in (seen[proxy_host] or "")
    assert _COOKIE_VALUE not in (seen[proxy_host] or "")  # 平台主域 cookie 不外发到代理域
    assert "academic.oup.com" not in seen  # 落地请求确已改写，从未裸打真实平台域
