"""elsevier/wiley 凭证装配 seam 生产装配集成（R2a / P0-1；auth-framework §3.4 两级凭证模型）。

背景（双源审计 + 对抗复核）：`config.py` 解析 `[auth.elsevier].api_key`/`.insttoken` 与
`[auth.wiley].token` 三槽、`auth/store.py` 的 `_CONFIG_KEY_SLOTS` 建好了 keyring→config
委派表，但 **CLI 生产装配点从不消费它们**——`_build_env`/`_assemble_auth_seam` 无 elsevier/
wiley 注入分支（对照 openreview 有 `_bind_openreview_token_client`、oup 有
`bind_cookie_supplier`）。后果：用户配好 key 也恒 `adapter._api_key is None` →
elsevier resolve 必 `AuthRequired`、wiley TDM 主路径不可达（只剩页面兜底）。既有测试全部
手工 `set_api_key`/`set_token` 短路（如 `test_auth_pipeline.py` 的 elsevier NE 载体），
装配链零覆盖——本文件即补该缺口，断言**经真实 CLI 装配路径**（不手工 set）：

  ① config.toml 明文槽配 key → 装配后 elsevier/wiley 实例拿到 key，且携密头挂在**专属**
     `HttpClient` 上（`X-ELS-APIKey`(+`X-ELS-Insttoken`) / `Wiley-TDM-Client-Token`）；
  ② keyring 条目**优先于** config.toml 明文槽（走 `CredentialStore.read_key` 既有委派面，
     装配不绕过 store 直读 config）；
  ③ 凭证隔离红线：共享 `env.http` 绝不携任何携密头，两 adapter 的专属 client 互不串头；
  ④ 无凭证 → 行为不变（不注入、不报错，adapter 沿用共享 client，`auth_http` 为空）。

零真实网络（装配期不发请求 + tests/conftest.py 全局 socket 护栏）、零真实 keyring
（autouse `_isolated` → `_import_keyring` 绝缘，沿 tests/helpers/auth.py 红线）。
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

import paper_crawler.auth.store as store_mod
from helpers import make_elsevier_venue, make_wiley_venue
from helpers.auth import FakeKeyring, install_fake_keyring
from helpers.elsevier_fixtures import body_bytes
from paper_crawler import cli as cli_module
from paper_crawler.adapter import SourceAdapter
from paper_crawler.adapters.elsevier_sd.adapter import ElsevierScienceDirectAdapter
from paper_crawler.adapters.wiley.adapter import TDM_TOKEN_HEADER, WileyAdapter
from paper_crawler.config import Config
from paper_crawler.http import HttpClient
from paper_crawler.ratelimit import RateLimiter
from paper_crawler.types import AssetKind, PaperStub, UrlStrategy

# 携密头名（elsevier-sd.md §3.2 / wiley.md §3.2；wiley 侧复用 adapter 导出常量）。
_ELS_APIKEY_HEADER = "X-ELS-APIKey"
_ELS_INSTTOKEN_HEADER = "X-ELS-Insttoken"

_ELS_KEY = "els-key-abc"
_ELS_INSTTOKEN = "els-inst-xyz"
_WILEY_TOKEN = "wiley-tdm-123"

# `01_entitlement_true.http` 封套里的 DOI（JFE；parse 不校验 DOI 一致性，取同值只为自洽）。
_ELS_FIXTURE_DOI = "10.1016/j.jfineco.2011.03.021"

# keyring 委派表条目名（`auth/store.py::_CONFIG_KEY_SLOTS` 键；config/profiles.example.toml
# 的 key_ref 同名）——②优先级断言按这些条目名写入假 keyring。
_ELS_KEY_REF = "elsevier_apikey"
_WILEY_KEY_REF = "wiley_tdm_token"

_ENV_SLOTS = (
    "PAPER_CRAWLER_ELSEVIER_API_KEY",
    "PAPER_CRAWLER_ELSEVIER_INSTTOKEN",
    "PAPER_CRAWLER_WILEY_TDM_TOKEN",
)

_ELS_CONFIG = f'[auth.elsevier]\napi_key = "{_ELS_KEY}"\ninsttoken = "{_ELS_INSTTOKEN}"\n'
_WILEY_CONFIG = f'[auth.wiley]\ntoken = "{_WILEY_TOKEN}"\n'


@pytest.fixture(autouse=True)
def _isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """keyring 绝缘（默认无后端 → 走 config 槽委派）+ env 槽清空 + cwd 隔离（项目层不干扰）。"""
    monkeypatch.setattr(store_mod, "_import_keyring", lambda: None)
    monkeypatch.setattr(store_mod, "_filekey_warned", True)
    for name in _ENV_SLOTS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)


def _home(tmp_path: Path, config_toml: str = "") -> Path:
    """隔离 config-home；`config_toml` 为空 = 无任何凭证配置形态。"""
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    if config_toml:
        (home / "config.toml").write_text(config_toml, encoding="utf-8")
    return home


def _adapters(env: cli_module.CliEnv) -> dict[str, SourceAdapter]:
    return env.ctx.registry._adapters  # noqa: SLF001 (测试内省装配结果，同 openreview 先例)


def _headers(client: HttpClient) -> dict[str, str]:
    return dict(client._client.headers)  # noqa: SLF001 (同 test_cli_canary 的 s2 头断言先例)


def _paper(doi: str = "10.1111/jofi.13123") -> PaperStub:
    return PaperStub(title="A Synthetic Wiley Article", identifiers=(("doi", doi),))


# ---------------------------------------------------------------------------
# ① config.toml 明文槽 → 装配后 adapter 拿到 key + 携密专属 client
# ---------------------------------------------------------------------------


def test_elsevier_key_and_insttoken_reach_adapter_via_assembly(tmp_path: Path) -> None:
    """DoD ①（elsevier）：配了 key/insttoken → 装配后 `_api_key` 非 None，且专属 client 携两头。

    修复前失败点：装配链无注入分支 → `_api_key is None`（resolve 必 AuthRequired）。
    """
    with cli_module._env(_home(tmp_path, _ELS_CONFIG), False, auth=True) as env:
        els = _adapters(env)["elsevier_sd"]
        assert isinstance(els, ElsevierScienceDirectAdapter)

        assert els._api_key == _ELS_KEY  # 装配读到 config 槽（此前恒 None）
        client = els._client()
        assert client is not env.http  # 专属 client（凭证隔离红线）
        headers = _headers(client)
        assert headers[_ELS_APIKEY_HEADER.lower()] == _ELS_KEY
        assert headers[_ELS_INSTTOKEN_HEADER.lower()] == _ELS_INSTTOKEN


def test_elsevier_without_insttoken_omits_insttoken_header(tmp_path: Path) -> None:
    """insttoken 可选：只配 api_key → 专属 client 只带 `X-ELS-APIKey`，不带空 insttoken 头。"""
    config = f'[auth.elsevier]\napi_key = "{_ELS_KEY}"\n'
    with cli_module._env(_home(tmp_path, config), False, auth=True) as env:
        els = _adapters(env)["elsevier_sd"]
        assert isinstance(els, ElsevierScienceDirectAdapter)

        headers = _headers(els._client())
        assert headers[_ELS_APIKEY_HEADER.lower()] == _ELS_KEY
        assert _ELS_INSTTOKEN_HEADER.lower() not in headers


def test_wiley_token_reaches_adapter_and_unblocks_tdm_plan(tmp_path: Path) -> None:
    """DoD ①（wiley）：配了 token → `_token` 非 None + 专属 client 携 TDM 头 + resolve 出
    **TDM 主路径** `API_CALL` 计划（此前恒无 token → 只剩 `RENDER_PAGE` 页面兜底）。"""
    with cli_module._env(_home(tmp_path, _WILEY_CONFIG), False, auth=True) as env:
        wiley = _adapters(env)["wiley"]
        assert isinstance(wiley, WileyAdapter)

        assert wiley._token == _WILEY_TOKEN
        client = wiley._client()
        assert client is not env.http
        assert _headers(client)[TDM_TOKEN_HEADER.lower()] == _WILEY_TOKEN

        plans = wiley.resolve_assets(make_wiley_venue(), _paper())  # 零网络（纯 URL 构造）
        assert [plan.url_strategy for plan in plans] == [UrlStrategy.API_CALL]


def test_assembled_elsevier_client_sends_key_and_resolve_no_longer_blocks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P0 症状消解的端到端离线证据：装配后 elsevier `resolve_assets` **不再** `AuthRequired`
    ——entitlement 预检真实发出（MockTransport）且**请求携 `X-ELS-APIKey` 头** → 产 PDF 计划。

    经 `_elsevier_client_factory` 模块级 seam 换 `MockTransport`（零真实网络、不接 limiter），
    头组装逻辑与生产同形；断言落在**实际请求头**上，而非仅 client 对象内省。
    """
    seen: list[tuple[str, str | None, str | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(
            (
                request.url.host,
                request.headers.get(_ELS_APIKEY_HEADER),
                request.headers.get(_ELS_INSTTOKEN_HEADER),
            )
        )
        return httpx.Response(200, content=body_bytes("01_entitlement_true.http"))

    def factory(
        config: Config,
        api_key: str,
        insttoken: str | None,
        rate_limiter: RateLimiter | None = None,
    ) -> HttpClient:
        headers = {_ELS_APIKEY_HEADER: api_key}
        if insttoken:
            headers[_ELS_INSTTOKEN_HEADER] = insttoken
        return HttpClient(
            user_agent="pc-test",
            transport=httpx.MockTransport(handler),
            extra_headers=headers,
        )

    monkeypatch.setattr(cli_module, "_elsevier_client_factory", factory)

    with cli_module._env(_home(tmp_path, _ELS_CONFIG), False, auth=True) as env:
        els = _adapters(env)["elsevier_sd"]
        assert isinstance(els, ElsevierScienceDirectAdapter)
        # 修复前此调用恒 raise AuthRequired（key 恒 None，触网前拦截）。
        plans = els.resolve_assets(make_elsevier_venue(), _paper(_ELS_FIXTURE_DOI))

    assert [plan.kind for plan in plans] == [AssetKind.PDF]
    assert seen == [("api.elsevier.com", _ELS_KEY, _ELS_INSTTOKEN)]


# ---------------------------------------------------------------------------
# ② keyring 条目优先于 config.toml 明文槽（走 store.read_key 既有委派面）
# ---------------------------------------------------------------------------


def test_keyring_entry_wins_over_config_plaintext_slot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DoD ②：同时存在 keyring 条目与 config 明文槽 → 装配取 **keyring** 值（§3.4 优先级）。

    证明装配走 `CredentialStore.read_key` 委派面，而非绕过 store 直读 `Config` 字段。
    """
    fake = FakeKeyring()
    fake.entries[("paper-crawler", _ELS_KEY_REF)] = "keyring-els"
    fake.entries[("paper-crawler", _WILEY_KEY_REF)] = "keyring-wiley"
    install_fake_keyring(monkeypatch, fake)

    with cli_module._env(_home(tmp_path, _ELS_CONFIG + _WILEY_CONFIG), False, auth=True) as env:
        adapters = _adapters(env)
        els, wiley = adapters["elsevier_sd"], adapters["wiley"]
        assert isinstance(els, ElsevierScienceDirectAdapter)
        assert isinstance(wiley, WileyAdapter)

        assert els._api_key == "keyring-els"  # 非 config 槽的 _ELS_KEY
        assert _headers(els._client())[_ELS_APIKEY_HEADER.lower()] == "keyring-els"
        assert wiley._token == "keyring-wiley"
        assert _headers(wiley._client())[TDM_TOKEN_HEADER.lower()] == "keyring-wiley"


# ---------------------------------------------------------------------------
# ③ 凭证隔离红线：共享 client 不携密、两 adapter 专属 client 互不串头
# ---------------------------------------------------------------------------


def test_shared_client_never_carries_credential_headers(tmp_path: Path) -> None:
    """红线：共享 `env.http`（arxiv/crossref 等共用）绝不携任何携密头；两专属 client 不串头。"""
    with cli_module._env(_home(tmp_path, _ELS_CONFIG + _WILEY_CONFIG), False, auth=True) as env:
        adapters = _adapters(env)
        els, wiley = adapters["elsevier_sd"], adapters["wiley"]
        assert isinstance(els, ElsevierScienceDirectAdapter)
        assert isinstance(wiley, WileyAdapter)

        shared = _headers(env.http)
        for header in (_ELS_APIKEY_HEADER, _ELS_INSTTOKEN_HEADER, TDM_TOKEN_HEADER):
            assert header.lower() not in shared

        els_headers, wiley_headers = _headers(els._client()), _headers(wiley._client())
        assert TDM_TOKEN_HEADER.lower() not in els_headers  # elsevier client 不带 wiley token
        assert _ELS_APIKEY_HEADER.lower() not in wiley_headers  # 反向亦然
        assert els._client() is not wiley._client()


# ---------------------------------------------------------------------------
# ④ 无凭证 → 行为不变（不注入、不报错、沿用共享 client）
# ---------------------------------------------------------------------------


def test_no_credentials_keeps_previous_behaviour(tmp_path: Path) -> None:
    """DoD ④：无任何凭证配置 → 装配不抛、不建专属 client；两 adapter 沿用共享 http、key 仍 None
    （elsevier resolve 仍 AuthRequired、wiley 仍页面兜底——既有语义逐字不变）。"""
    with cli_module._env(_home(tmp_path), False, auth=True) as env:
        adapters = _adapters(env)
        els, wiley = adapters["elsevier_sd"], adapters["wiley"]
        assert isinstance(els, ElsevierScienceDirectAdapter)
        assert isinstance(wiley, WileyAdapter)

        assert els._api_key is None
        assert wiley._token is None
        assert els._client() is env.http  # bind_http_client 的共享注入，未被覆盖
        assert wiley._client() is env.http
        assert env.auth_http == ()  # 无专属 client 待关闭
