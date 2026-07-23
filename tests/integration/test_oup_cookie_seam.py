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

from pathlib import Path

import httpx
import pytest

import paper_crawler.auth.store as store_mod
from helpers import make_oup_venue
from helpers.auth import make_config
from integration.conftest import AUTH_T0, AuthClock, storage_state_bytes
from paper_crawler.adapter import load_adapters
from paper_crawler.adapters.oup_silverchair.adapter import OupSilverchairAdapter
from paper_crawler.auth.manager import AuthManager
from paper_crawler.cli import _assemble_auth_seam, _cookie_supplier_for
from paper_crawler.errors import AuthRequired, CrawlerError, ErrorClass
from paper_crawler.http import HttpClient
from paper_crawler.pipeline import StageContext
from paper_crawler.ratelimit import RateLimiter
from paper_crawler.registry import VenueRegistry
from paper_crawler.storage.db import Database
from paper_crawler.storage.repo import Repo
from paper_crawler.tasks import TaskQueue
from paper_crawler.types import AssetKind, PaperStub, SessionBackend, SessionHandle

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
    """DoD ②：supplier(session) → resolve(oup@campus) → load_cookies 解密假 state → cookie dict。"""
    config = make_config(_home(tmp_path, OUP_COOKIE_PROFILE))
    manager = AuthManager(config, clock=AuthClock())
    # 真实 AES-GCM 加密落盘（keyring 已绝缘 → filekey）：假 storage_state。
    manager.store.write_state(
        _STATE_REF,
        storage_state_bytes(_COOKIE_VALUE, domain="academic.oup.com", name=_COOKIE_NAME),
    )
    supplier = _cookie_supplier_for(manager)

    cookies = supplier(_session())

    assert cookies == {_COOKIE_NAME: _COOKIE_VALUE}  # 解密 → name→value dict


def test_supplier_is_lazy_resolves_only_on_call(tmp_path: Path) -> None:
    """DoD ③（懒解析时机）：闭包构造不解析；仅被调用时才 resolve→load_cookies→read_state。

    无 state 落盘 → 调用时 read_state 缺 `.enc` → AuthRequired（证明解析发生在调用时，非构造时）。
    """
    config = make_config(_home(tmp_path, OUP_COOKIE_PROFILE))
    manager = AuthManager(config, clock=AuthClock())
    supplier = _cookie_supplier_for(manager)  # 构造：不触 provider/加密面

    with pytest.raises(AuthRequired):  # 调用时才解析并读 state（缺 → AuthRequired）
        supplier(_session())


def test_supplier_non_cookie_provider_is_config_error(tmp_path: Path) -> None:
    """cookie 档 venue 却映射到非 cookie provider（api_key，无 load_cookies）→ 响亮 CONFIG。"""
    config = make_config(_home(tmp_path, APIKEY_PROFILE))
    manager = AuthManager(config, clock=AuthClock())
    supplier = _cookie_supplier_for(manager)

    with pytest.raises(CrawlerError) as exc:
        supplier(_session(provider_id="elsevier", ref="elsevier_apikey"))
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
