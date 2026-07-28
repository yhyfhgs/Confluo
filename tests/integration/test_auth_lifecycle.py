"""mock IdP 集成测试全生命周期（auth-framework §9；T6；AC-4.2/4.5/4.6 离线载体）。

范围边界（与 tests/unit/test_auth_*.py 的分工，勿重复单元断言）：单元测试逐方法
孤立验证签名/边界/单次响应判读；本文件是**集成层**——同一个持续存在的
`MockIdPState`（一个"进程内 mock IdP 后端"）跨多次 provider 方法调用、跨"新进程"
（新 provider/store 实例重读同一加密 state）串联出 07 §8 的登录全生命周期：

    ①首登（假 browser seam）→ storage_state 加密落盘
    ②headless 复用（新 provider 实例读 state → cookie jar 导出 → 探针 200）
    ③过期（mock 状态翻转 → 探针 302 → EXPIRED）
    ④refresh（SSO 重放：IdP session 尚存→新 handle；已失→None→BLOCKED 语义；
      风控挑战→Challenged，AC-4.6 交叉验证）
    ⑤logout 取证（AC-4.5：state/meta/keyring 全清 + 集成层全 home 树残留重扫）

选 `SSOFlowProvider` 作全周期主载体：它是唯一有实质 `refresh()` 语义的 provider
（`CookieSessionProvider`/`EZProxyProvider` 的 refresh 恒 None，`ApiKeyProvider`
无 storage_state），且继承 `CookieSessionProvider` 的全部 ensure_session/
health_check/invalidate 机制——覆盖它即覆盖 cookie_session 一系的核心路径。
EZProxy/ApiKey 的独立语义已由 tests/unit/test_auth_providers.py 充分单测，不在
本文件重复全周期。

AC-4.2 双源断言（B-m8）与 AC-4.6 载体见文件下半部分，各自的 docstring 说明其
在"T5 尚未合并入本 worktree"约束下的证明边界（批级 BLOCKED wiring 归 T7a）。

零真实网络（httpx.MockTransport，tests/conftest.py 全局 socket 护栏兜底）、
零真实浏览器（`login_flow=` 直接注入——browser.py 自身的 mkdtemp/rmtree/惰性
import 机制已由 tests/unit/test_auth_browser.py 全覆盖，本文件不重复）、零真实
keyring（`_isolated` autouse fixture，个别用例显式换装 `FakeKeyring` 覆盖另一
降级分支）。
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import httpx
import pytest

import paper_crawler.auth.store as store_mod
from helpers.auth import FakeKeyring, install_fake_keyring, make_config, master_key_entry
from integration.conftest import (
    AuthClock,
    MockIdPState,
    cookie_header,
    make_mock_idp_handler,
    storage_state_bytes,
)
from paper_crawler.auth.manager import AuthManager
from paper_crawler.auth.providers.sso_flow import SSOFlowProvider
from paper_crawler.auth.store import CredentialStore, ProviderProfile
from paper_crawler.config import Config
from paper_crawler.errors import Challenged, CrawlerError, ErrorClass
from paper_crawler.http import HttpClient
from paper_crawler.obslog import setup_logging
from paper_crawler.types import HealthStatus, SessionBackend, SessionHandle

# ---------------------------------------------------------------------------
# 隔离 + 装配（沿 tests/unit/test_auth_manager.py 的 `_isolated`/`FakeClock` 先例）
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(store_mod, "_import_keyring", lambda: None)
    monkeypatch.setattr(store_mod, "_filekey_warned", True)
    monkeypatch.chdir(tmp_path)


SSO_PROFILE_TOML = """\
schema_version = 1

[providers."oup@shib"]
kind = "sso_flow"
platform = "oup_silverchair"
inst_login_url = "https://mock.test/InstitutionalLogin"
wayf_hint = "My University"
probe_url = "https://mock.test/my-account"
state_ref = "oup_shib_state"
est_ttl_hours = 8
"""


@dataclass
class LifecycleFixture:
    home: Path
    store: CredentialStore
    config: Config
    mock_idp: MockIdPState
    clock: AuthClock
    cookie: str


@pytest.fixture
def lifecycle(tmp_path: Path, mock_idp_state: MockIdPState) -> LifecycleFixture:
    """一个"新鲜 home"：已写 profiles.toml，尚未首登（①的起点）。"""
    home = tmp_path / "home"
    (home / "auth").mkdir(mode=0o700, parents=True)
    (home / "auth" / "profiles.toml").write_text(SSO_PROFILE_TOML, encoding="utf-8")
    config = make_config(home)
    store = CredentialStore(home)
    store.bind_config(config)
    return LifecycleFixture(
        home=home,
        store=store,
        config=config,
        mock_idp=mock_idp_state,
        clock=AuthClock(),
        cookie="initial-cookie-001",
    )


def _profile(fx: LifecycleFixture) -> ProviderProfile:
    return fx.store.load_profiles()["oup@shib"]


def _http_factory_for(state: MockIdPState) -> Callable[[httpx.Cookies], httpx.Client]:
    handler = make_mock_idp_handler(state)

    def factory(cookies: httpx.Cookies) -> httpx.Client:
        return httpx.Client(
            cookies=cookies, follow_redirects=True, transport=httpx.MockTransport(handler)
        )

    return factory


def _make_sso_provider(fx: LifecycleFixture, *, login_cookie: str | None = None) -> SSOFlowProvider:
    """构造一个**新** `SSOFlowProvider` 实例（每次调用都是新对象，读同一 `fx.store`）
    ——如实模拟"新进程重启后 headless 复用"（auth-framework §9 storage_state 复用
    跨进程重启注记）；`login_flow` 是假 browser seam：不触网，直接回放 storage_state
    并把该 cookie 登记进 mock IdP 后端（模拟"用户刚完成真实登录，IdP 侧已认得这个
    session"）。
    """

    def login_flow(*, login_url: str, wait_for_user: object) -> bytes:
        cookie = login_cookie if login_cookie is not None else fx.cookie
        fx.mock_idp.issue_cookie(cookie)
        return storage_state_bytes(cookie)

    return SSOFlowProvider(
        _profile(fx),
        fx.store,
        clock=fx.clock,
        login_flow=login_flow,
        http_factory=_http_factory_for(fx.mock_idp),
    )


def _first_login(fx: LifecycleFixture) -> SessionHandle:
    """①首登（假 browser seam）：只返回 handle，**丢弃 provider 实例**——强制后续
    阶段必须经 `_make_sso_provider` 重新构造，如实体现"新进程 headless 复用"。
    """
    provider = _make_sso_provider(fx, login_cookie=fx.cookie)
    return provider.ensure_session(interactive=True)


# ---------------------------------------------------------------------------
# ①首登 → storage_state 加密落盘
# ---------------------------------------------------------------------------


def test_lifecycle_01_first_login_encrypts_state_and_writes_meta(
    lifecycle: LifecycleFixture,
) -> None:
    handle = _first_login(lifecycle)

    assert handle.backend is SessionBackend.PLAYWRIGHT_STATE
    assert handle.payload_ref == "oup_shib_state"

    enc = lifecycle.store.state_dir / "oup_shib_state.enc"
    assert enc.is_file()
    assert lifecycle.cookie.encode() not in enc.read_bytes()  # 落盘即密文（AC-0.3）

    meta = lifecycle.store.read_meta("oup_shib_state")
    assert meta is not None
    assert meta["backend"] == "playwright_state"
    assert lifecycle.cookie not in json.dumps(meta)  # sidecar 非密（A-m2）

    # 假 seam：首登全程不触网（真实首登是"人在回路"的 headed 浏览器交互，非 HTTP 流程）。
    assert lifecycle.mock_idp.request_log == []


# ---------------------------------------------------------------------------
# ②headless 复用（新进程：新 provider 实例读 state → cookie jar 导出 → 探针 200）
# ---------------------------------------------------------------------------


def test_lifecycle_02_headless_reuse_new_process_probe_ok(lifecycle: LifecycleFixture) -> None:
    _first_login(lifecycle)

    fresh_provider = _make_sso_provider(lifecycle)  # "新进程"：不传 login_cookie，靠持久化 state
    handle = fresh_provider.ensure_session()  # 非交互：headless 复用，不触发首登
    assert fresh_provider.health_check(handle) is HealthStatus.OK
    assert lifecycle.mock_idp.route_hits("/my-account") == 1  # 单次探测，无轰炸

    jar = fresh_provider.load_cookies(handle)  # cookie jar 导出（②描述原句）
    assert jar.get("sid", domain="mock.test") == lifecycle.cookie

    meta = lifecycle.store.read_meta("oup_shib_state")
    assert meta is not None and meta["last_health"] == "ok"


# ---------------------------------------------------------------------------
# ③过期（mock 状态翻转 → 探针 302 → EXPIRED）
# ---------------------------------------------------------------------------


def test_lifecycle_03_expiry_detected_via_probe_redirect(lifecycle: LifecycleFixture) -> None:
    _first_login(lifecycle)
    lifecycle.mock_idp.expire_cookie(lifecycle.cookie)  # mock 状态驱动（B-M1，非真实 TTL）

    provider = _make_sso_provider(lifecycle)
    handle = provider.ensure_session()  # state 仍在盘（未 invalidate）→ 照常拿到 handle
    assert provider.health_check(handle) is HealthStatus.EXPIRED
    assert lifecycle.mock_idp.route_hits("/my-account") == 1

    meta = lifecycle.store.read_meta("oup_shib_state")
    assert meta is not None and meta["last_health"] == "expired"


# ---------------------------------------------------------------------------
# ④refresh：IdP session 尚存 → 新 handle
# ---------------------------------------------------------------------------


def test_lifecycle_04a_refresh_succeeds_while_idp_session_alive(
    lifecycle: LifecycleFixture,
) -> None:
    _first_login(lifecycle)
    lifecycle.mock_idp.expire_cookie(lifecycle.cookie)  # 本地 cookie 过期；IdP session 默认尚存

    provider = _make_sso_provider(lifecycle)
    handle = provider.ensure_session()
    assert provider.health_check(handle) is HealthStatus.EXPIRED

    refreshed = provider.refresh(handle)
    assert refreshed is not None
    assert refreshed.payload_ref == handle.payload_ref
    assert refreshed.established_at == lifecycle.clock.now  # B-M1：注入时钟精确断言

    assert provider.health_check(refreshed) is HealthStatus.OK  # 新 cookie 已回写加密 state
    new_cookie = provider.load_cookies(refreshed).get("sid", domain="mock.test")
    assert new_cookie is not None and new_cookie != lifecycle.cookie  # 确系新值，非旧值复活
    assert lifecycle.mock_idp.route_hits("/InstitutionalLogin") == 1  # 单次续期，不重试


# ---------------------------------------------------------------------------
# ④refresh：IdP session 已失 → None → BLOCKED 语义
# ---------------------------------------------------------------------------


def test_lifecycle_04b_refresh_none_when_idp_session_also_gone(lifecycle: LifecycleFixture) -> None:
    _first_login(lifecycle)
    lifecycle.mock_idp.expire_cookie(lifecycle.cookie)
    lifecycle.mock_idp.expire_idp_session()

    provider = _make_sso_provider(lifecycle)
    handle = provider.ensure_session()
    assert provider.health_check(handle) is HealthStatus.EXPIRED
    assert provider.refresh(handle) is None  # IdP 亦过期：不可静默续期（§2.2）

    # BLOCKED 语义（§8.2/§8.4；批级 runner wiring 归 T5/T7a，本层只证 provider 契约）：
    # refresh 失败不会"自动清空" state（那是 invalidate/logout 的职责）——上层唯一
    # 正确出路是路由为 AuthRequired/BLOCKED(auth)，提示人工 `crawler auth login` 重登
    # 后覆盖写入；本条断言证明这条路径在 provider 层是稳定、幂等、无副作用的：
    assert lifecycle.store.has_state("oup_shib_state")  # 仍需人工重登覆盖，而非自动清空
    assert provider.health_check(handle) is HealthStatus.EXPIRED  # 幂等复检：不会假性转好
    assert lifecycle.mock_idp.route_hits("/InstitutionalLogin") == 1  # 失败同样不重试


# ---------------------------------------------------------------------------
# ④refresh：风控挑战页 → Challenged（AC-4.6 的 refresh 子路径）
# ---------------------------------------------------------------------------


def test_lifecycle_04c_refresh_raises_challenged_on_challenge_page(
    lifecycle: LifecycleFixture,
) -> None:
    _first_login(lifecycle)
    lifecycle.mock_idp.expire_cookie(lifecycle.cookie)
    lifecycle.mock_idp.trigger_challenge()  # IdP 侧风控挑战页（T1a challenge.py 特征）

    provider = _make_sso_provider(lifecycle)
    handle = provider.ensure_session()
    with pytest.raises(Challenged) as excinfo:
        provider.refresh(handle)
    assert excinfo.value.error_class is ErrorClass.CHALLENGE
    assert lifecycle.mock_idp.route_hits("/InstitutionalLogin") == 1  # 命中即报，绝不重试（AC-0.2）


# ---------------------------------------------------------------------------
# ⑤logout 取证（AC-4.5）：state/meta/keyring 全清 + 集成层全 home 树残留重扫
# ---------------------------------------------------------------------------


def test_lifecycle_05_logout_forensic_wipe_full_home_tree(
    lifecycle: LifecycleFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """经 `AuthManager.logout()`（而非手搓 provider.invalidate）——`invalidate()` 不
    触网/不触 browser seam，manager 默认 provider 构造（无 mock http_factory 注入）
    在此完全安全，这是本文件唯一直接使用 `AuthManager` 驱动网络无关操作的用例。

    换装可用 `FakeKeyring`（覆盖本文件其余用例默认的 filekey 降级分支）：与
    tests/unit/test_auth_manager.py::test_logout_stateful_forensic_chain（filekey
    分支）互补，凑齐两条主密钥降级链的 logout 取证覆盖。
    """
    fake_keyring = FakeKeyring()
    install_fake_keyring(monkeypatch, fake_keyring)

    _first_login(lifecycle)
    assert (lifecycle.store.state_dir / "oup_shib_state.enc").is_file()
    assert master_key_entry(lifecycle.home) in fake_keyring.entries

    manager = AuthManager(lifecycle.config, clock=lifecycle.clock, store=lifecycle.store)
    manager.logout("oup@shib")

    # 取证清单（AC-4.5；B-m6 有状态类）：.enc / meta / keyring 主密钥条目全清。
    assert not list(lifecycle.store.state_dir.glob("*.enc"))
    assert not list(lifecycle.store.state_dir.glob("*.meta.json"))
    assert master_key_entry(lifecycle.home) not in fake_keyring.entries

    # 集成层重验（超出既有单测/CLI 测试逐一核对已知文件路径的范围）：对**全 home
    # 目录树**逐文件扫描字节内容，确认 cookie 明文不藏在任何角落（未知/意外文件亦覆盖）。
    cookie_bytes = lifecycle.cookie.encode("utf-8")
    scanned_files = 0
    for path in lifecycle.home.rglob("*"):
        if path.is_file():
            scanned_files += 1
            assert cookie_bytes not in path.read_bytes(), f"cookie 残留于 {path}"
    assert scanned_files > 0  # 反空扫描误判绿（profiles.toml 等文件至少恒在）

    # 幂等：再次 logout 静默成功（无残留可清，non-fatal no-op）。
    manager.logout("oup@shib")


# ---------------------------------------------------------------------------
# AC-4.2：health_check EXPIRED + refresh None 是批级 BLOCKED 判定的唯一决策输入
# （provider/manager 层能证的最深处——T5 pipeline 健康门未合并入本 worktree）。
# ---------------------------------------------------------------------------


def test_ac42_health_check_expired_and_unrefreshable_is_the_block_signal(
    lifecycle: LifecycleFixture,
) -> None:
    """批级 `_auth_batch`/`_auth_blocked_venues` wiring 归 T7a 收口（依 T5+T6，
    auth-framework §8.2/plan §4 T6 卡）——本 worktree 未合并 pipeline/runner.py。
    本用例证明该门控唯一需要的决策输入——`health_check` 返回 EXPIRED 且随后
    `refresh` 返回 None——在 provider 层精确、幂等、无副作用地成立，且不因反复
    探测而放大请求量（"无轰炸"纪律在 provider 单点层面同样成立）。
    """
    _first_login(lifecycle)
    lifecycle.mock_idp.expire_cookie(lifecycle.cookie)
    lifecycle.mock_idp.expire_idp_session()

    provider = _make_sso_provider(lifecycle)
    handle = provider.ensure_session()

    assert provider.health_check(handle) is HealthStatus.EXPIRED
    assert provider.refresh(handle) is None
    # 幂等复检：探测行为本身不会意外"治愈"或产生放大副作用。
    assert provider.health_check(handle) is HealthStatus.EXPIRED
    assert provider.refresh(handle) is None

    # 请求纪律：本测试主动调了两轮 health_check+refresh，handler 计数应精确等于
    # 调用次数（无隐藏重试/放大）。
    assert lifecycle.mock_idp.route_hits("/my-account") == 2
    assert lifecycle.mock_idp.route_hits("/InstitutionalLogin") == 2


def test_ac42_batch_fetch_stops_after_first_401_dual_source(
    lifecycle: LifecycleFixture, tmp_path: Path
) -> None:
    """AC-4.2 双源断言（B-m8）——批级健康门 wiring 本身归 T5/T7a（本 worktree 未
    合并 pipeline/runner.py，见 plan §4 T6 卡）。本用例在 provider 层之上叠一个
    **测试专用**的最小批循环（不代表 runner.py 真实实现、不改动任何 src 文件），
    复现"auth_gated 批中途 session 失效 → ≤20 篇内检出且不再轰炸"的可观测边界，
    为双源断言提供两个独立数据源：

      主证：`mock_idp.status_count(401)` —— MockTransport handler 实际吐出的
            401 响应次数（"401 响应计数"字面数据源）。
      辅证：obslog jsonl 中 `status == 401` 的事件行数——`HttpClient._log_exchange`
            对每次交换无条件落盘一条事件（http.py §2.1 冻结机制），与主证完全
            独立的第二条证据链（不同代码路径产生，非同一次计数的重复读取）。

    直取下载用 `HttpClient`（而非 provider 探针专属的 `_http_factory` client）——
    这正是唯一会产生 obslog `status=` 事件的路径，探针路径不途经 `HttpClient`，
    不产生该事件；两条路径分工明确，共同构成 B-m8 双源。
    """
    log_dir = tmp_path / "logs"
    setup_logging(log_dir)

    handle = _first_login(lifecycle)
    provider = _make_sso_provider(lifecycle)  # "新进程"：headless 复用同一 store

    client = HttpClient(
        user_agent="PaperCrawler/test (integration; mailto:test@example.org)",
        transport=httpx.MockTransport(make_mock_idp_handler(lifecycle.mock_idp)),
        extra_headers=cookie_header(lifecycle.cookie),
    )
    blocked_at: int | None = None
    try:
        for paper_index in range(1, 21):  # ≤20 篇批（AC-4.2 字面上限）
            if paper_index == 8:  # 批中途 session 失效：本地 cookie + IdP session 同时失效
                lifecycle.mock_idp.expire_cookie(lifecycle.cookie)
                lifecycle.mock_idp.expire_idp_session()
            if blocked_at is not None:  # 已判定整批 BLOCKED：不再发出任何后续请求
                break
            try:
                pdf = client.get_bytes(f"https://mock.test/article-pdf/p{paper_index:02d}")
                assert pdf.startswith(b"%PDF")
            except CrawlerError as exc:
                assert exc.error_class is ErrorClass.AUTH_EXPIRED  # 401 映射（http.py §2.1）
                # 健康门等价动作：探测确认 + 续期尝试（均失败）→ 判定整批 BLOCKED
                # （`_auth_blocked_venues` 连带语义的最小等价物）；记录触发点后收尾。
                assert provider.health_check(handle) is HealthStatus.EXPIRED
                assert provider.refresh(handle) is None
                blocked_at = paper_index
    finally:
        client.close()

    assert blocked_at == 8  # 第 8 篇触发（< 20，AC-4.2"≤20 篇内检出"）
    assert lifecycle.mock_idp.route_hits("/article-pdf/") == 8  # 7 次成功 + 1 次 401，之后零请求

    # 主证：MockTransport handler 实际吐出的 401 响应计数（B-m8 字面上限 ≤2）。
    assert lifecycle.mock_idp.status_count(401) <= 2
    assert lifecycle.mock_idp.status_count(401) == 1

    # 辅证：obslog jsonl 独立扫描 status=401 事件数（与主证不同代码路径产生的独立证据）。
    events = [
        json.loads(line)
        for jsonl in log_dir.glob("*.jsonl")
        for line in jsonl.read_text(encoding="utf-8").splitlines()
        if line
    ]
    events_401 = [row for row in events if row.get("status") == 401]
    assert len(events_401) <= 2
    assert len(events_401) == 1


# ---------------------------------------------------------------------------
# AC-4.6：mock 挑战页特征 → health_check 与 refresh 两条独立探测路径一致判定为
# CHALLENGED/Challenged；"冷却字段"断言止于 manager 层能确权的范围。
# ---------------------------------------------------------------------------


def test_ac46_challenge_cross_validated_and_platform_resolvable(
    lifecycle: LifecycleFixture,
) -> None:
    """mock 返挑战页特征（复用 T1a challenge.py 特征库：`cf-mitigated: challenge`
    头 + "Just a moment..." body，判定优先级最高，auth-framework §11）。两条独立
    探测路径（`health_check`/`refresh`）对**同一**挑战态一致判为 CHALLENGED/
    `Challenged`，且各自都只探测一次（不对抗、不重试，AC-0.2）。

    "冷却字段"断言止于 manager 层能确权的范围（真实冷却持久化 =
    `<config-home>/state/cooldown/<platform>.json`，runner.py 专属，
    auth-framework §8.4，T5/T7a 收口——本用例不模拟、不断言该文件）：本用例只证明
      (a) `Challenged.error_class` 稳定为 `ErrorClass.CHALLENGE`——未来冷却路由
          判据字段；
      (b) `AuthManager.profiles()[key].platform` 可从 profiles.toml 正确解析——
          未来冷却落盘键 `<platform>.json` 所需的键值，且此解析路径零网络
          （`load_profiles` 纯文件解析，不经 mock IdP，不受 `challenge_active`
          状态影响）。
    """
    handle = _first_login(lifecycle)
    lifecycle.mock_idp.trigger_challenge()

    provider = _make_sso_provider(lifecycle)
    assert provider.health_check(handle) is HealthStatus.CHALLENGED  # 探测路径①：如实上报，不抛错

    with pytest.raises(Challenged) as excinfo:
        provider.refresh(handle)  # 探测路径②：SSO 续期同样命中风控 → 显式抛出
    assert excinfo.value.error_class is ErrorClass.CHALLENGE

    assert lifecycle.mock_idp.route_hits("/my-account") == 1  # 不重试
    assert lifecycle.mock_idp.route_hits("/InstitutionalLogin") == 1  # 不重试

    manager = AuthManager(lifecycle.config, clock=lifecycle.clock, store=lifecycle.store)
    assert manager.profiles()["oup@shib"].platform == "oup_silverchair"  # 冷却键（零网络解析）


# ---------------------------------------------------------------------------
# 真实浏览器测试门控声明（deliverable #5）：本文件零 `import playwright`——全部
# 首登路径经 `login_flow=` 假 seam 注入，browser.py 自身的惰性 import/mkdtemp
# 清理机制已由 tests/unit/test_auth_browser.py 全覆盖，不在此重复。
# ---------------------------------------------------------------------------
