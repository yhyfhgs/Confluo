"""AC-1 集成测试的共享装配（Task 9）。

四份 AC 测试（kill-resume/dry-run/ratelimit/blocked-resume）都要建一个"真实
`Config.load(home)` 路径"的隔离 HOME：`config.toml` 钉住 `venues_dirs`、写一份
mock venue YAML、可选叠加 `rate_limit`（venue 级覆盖）与 `[rate] scale`（把限速
sleep 快进——不测限速的 AC 借此免去真实等待）。这套装配与 `test_cli.py` 的
`_make_home`/`_write_venue` 同形，此处抽成可复用件供四份新测试共享；venue 语料
口径（`VENUE`/`DEFAULT_QUIRKS`）继续复用 `test_pipeline_e2e`，全仓一致。

`build_home`/`write_mock_venue` 是模块级函数（供 kill-resume 建两个 home、
blocked-resume 中途改写 YAML 模拟人工修复时按 `from integration.conftest import ...`
取用）；`make_home` 是便捷 fixture（单 home 的常见情形，免 import）。
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
import yaml

from integration.test_pipeline_e2e import DEFAULT_QUIRKS, VENUE

__all__ = [
    "DEFAULT_QUIRKS",
    "VENUE",
    "AUTH_T0",
    "MOCK_IDP_COOKIE_NAME",
    "AuthClock",
    "MockIdPState",
    "build_home",
    "cookie_header",
    "make_home",
    "make_mock_idp_handler",
    "storage_state_bytes",
    "write_mock_venue",
]


def write_mock_venue(
    venues_dir: Path, quirks: dict[str, object], *, rate_limit_rpm: float | None = None
) -> None:
    """写/覆盖一份 mock venue YAML（形状同 test_cli._write_venue，lint 可过、路由 mock）。"""
    doc: dict[str, object] = {
        "id": VENUE,
        "kind": "journal",
        "names": {"full": "Mock Journal", "aliases": ["MJ"]},
        "field": ["cs_ai"],
        "tier": "T1",
        "identifiers": {"issn": ["0000-0000"]},
        "metadata_source": "mock_platform",
        "fulltext_source": "mock_platform",
        "auth": {"level": "none"},
        "quirks": quirks,
        "status": "active",
    }
    if rate_limit_rpm is not None:
        doc["rate_limit"] = {"requests_per_minute": rate_limit_rpm}
    (venues_dir / "mock-journal.yaml").write_text(
        yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8"
    )


def build_home(
    base: Path,
    quirks: dict[str, object],
    *,
    name: str = "home",
    rate_limit_rpm: float | None = None,
    rate_scale: float | None = None,
) -> Path:
    """在 `base/name` 下装配一个隔离 HOME（config.toml + 一份 mock venue）。"""
    home = base / name
    venues_dir = home / "venues"
    venues_dir.mkdir(parents=True)
    config_lines = ["[paths]", 'venues_dirs = ["venues"]']
    if rate_scale is not None:
        config_lines += ["", "[rate]", f"scale = {rate_scale}"]
    (home / "config.toml").write_text("\n".join(config_lines) + "\n", encoding="utf-8")
    write_mock_venue(venues_dir, dict(quirks), rate_limit_rpm=rate_limit_rpm)
    return home


@pytest.fixture
def make_home(tmp_path: Path) -> Callable[..., Path]:
    """便捷 home 工厂：`make_home(quirks, name=..., rate_limit_rpm=..., rate_scale=...)`。"""

    def _make(
        quirks: dict[str, object],
        *,
        name: str = "home",
        rate_limit_rpm: float | None = None,
        rate_scale: float | None = None,
    ) -> Path:
        return build_home(
            tmp_path, quirks, name=name, rate_limit_rpm=rate_limit_rpm, rate_scale=rate_scale
        )

    return _make


# ---------------------------------------------------------------------------
# Mock IdP（auth-framework §9；T6 交付——mock IdP fixtures，命名清晰稳定，供
# `tests/integration/test_auth_lifecycle.py` 消费，亦供 T7a 批级端到端复用）。
#
# 机制：`httpx.MockTransport` 处理函数 + 进程内状态字典（`MockIdPState`）模拟
# IdP session/cookie 有效性——纯 httpx，零真实网络/浏览器（keyring 绝缘由各消费
# 测试文件自身的 `_isolated` autouse fixture 负责，见 tests/helpers/auth.py；
# 零真实 socket 由 tests/conftest.py 的全局护栏兜底）。过期语义纯状态驱动
# （B-M1：不依赖 httpx cookiejar 真实 TTL）——测试直接调用
# `expire_cookie`/`expire_idp_session`/`trigger_challenge` 翻转，零 sleep。
#
# 路由表（auth-framework §9 原表 + article-pdf 直取扩展）：
#   /login              → 200（首登探测锚点，本身不参与假 login_flow 首登——首登
#                          走 provider 的 `login_flow=` 注入点直接返回 storage_state，
#                          不经此路由；保留供 T7a 需要"真打一次首登页"场景复用）
#   /my-account         → cookie 有效 200+账号标识；否则 302→/login
#   /InstitutionalLogin → IdP session 存：302+Set-Cookie 新 cookie →/my-account；
#                         否则：302→/idp/login（终点无账号标识，refresh→None）
#   /idp/login          → 200 IdP 登录页（无账号标识，终止 refresh 重定向链）
#   /article-pdf/<id>   → cookie 有效 200 %PDF；无效/缺失 401（直取端点的
#                         AUTH_EXPIRED 信号——errors.py `401→AUTH_EXPIRED` 与
#                         auth-framework §8.4"401/302→login 同归 AUTH_EXPIRED"
#                         一致，direct-download 端点对纯过期 session 常见 401
#                         而非重定向）；`no_entitlement_ids` 命中 → 302→
#                         /article-abstract（供 AC-4.3 形态复用，未来 T7a 可能用到）
#   /article-abstract   → 200 无权限面板（呼应上条）
#   任意路由：`state.challenge_active` 时一律 403 + `cf-mitigated: challenge` +
#   "Just a moment..."（T1a challenge.py 特征库，判定优先级最高，auth-framework §11）
# ---------------------------------------------------------------------------

AUTH_T0 = datetime(2026, 7, 23, 12, 0, 0, tzinfo=UTC)
MOCK_IDP_COOKIE_NAME = "sid"


class AuthClock:
    """可拨动假时钟（B-M1 注入缝）；`__call__` 供 provider/manager `clock=` 消费。

    与 tests/unit/test_auth_{manager,providers}.py 的 `FakeClock` 同形——独立
    定义避免 tests/integration 反向依赖 tests/unit 内部件；字段/行为逐一对齐。
    """

    def __init__(self, start: datetime = AUTH_T0) -> None:
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kwargs: float) -> None:
        self.now = self.now + timedelta(**kwargs)


@dataclass
class MockIdPState:
    """mock IdP 进程内状态（auth-framework §9）：cookie 有效性 + IdP session 存续
    + 挑战页开关 + 请求/状态码计数（AC-4.2 B-m8 主证数据源）。

    一个实例代表"一个持续存在的 IdP 后端"——同一 `MockIdPState` 可被多次
    `make_mock_idp_handler` 调用包装出的多个 handler/transport/client/provider
    实例共享（各自的 client 是"新连接"，但后端状态是同一个，如实模拟"进程重启
    但 IdP 侧状态不受影响"，auth-framework §9 storage_state 复用跨进程重启注记）。
    """

    valid_cookies: set[str] = field(default_factory=set)
    idp_session_alive: bool = True
    challenge_active: bool = False
    no_entitlement_ids: set[str] = field(default_factory=set)
    request_log: list[tuple[str, str]] = field(default_factory=list)  # (method, path)
    status_counts: Counter[int] = field(default_factory=Counter)
    refresh_seq: int = 0

    def issue_cookie(self, value: str) -> None:
        self.valid_cookies.add(value)

    def expire_cookie(self, value: str) -> None:
        self.valid_cookies.discard(value)

    def expire_idp_session(self) -> None:
        self.idp_session_alive = False

    def trigger_challenge(self, active: bool = True) -> None:
        self.challenge_active = active

    def is_valid(self, cookie: str | None) -> bool:
        return cookie is not None and cookie in self.valid_cookies

    def status_count(self, status: int) -> int:
        """给定 HTTP 状态码的 mock 响应次数（AC-4.2 B-m8 主证：handler 计数）。"""
        return self.status_counts[status]

    def route_hits(self, path_prefix: str) -> int:
        """给定路径前缀的请求次数（用于断言"探针/续期恰好一次，不重试不轰炸"）。"""
        return sum(1 for _, path in self.request_log if path.startswith(path_prefix))

    def next_refreshed_cookie(self) -> str:
        """`/InstitutionalLogin` 续期成功时签发的新 cookie 值（确定性可断言，非 uuid）。"""
        self.refresh_seq += 1
        cookie = f"idp-refreshed-{self.refresh_seq}"
        self.issue_cookie(cookie)
        return cookie


def _resolve_mock_cookie(
    request: httpx.Request, state: MockIdPState, *, name: str = MOCK_IDP_COOKIE_NAME
) -> str | None:
    """从请求头解析当前会话 cookie 值——**优先取当前有效的那个**，非单纯取首个。

    同名 cookie 可能在同一次 redirect 链内重复出现在一个 `Cookie` 头中：
    httpx 的 cookiejar 把"host-only"（无 `Domain=` 属性，如首登写入的 storage_state
    原样态）与"domain-scoped"（`Set-Cookie: ...; Domain=<host>` 续期新种的那种）
    视为两条不同记录，即便两者最终都命中同一 host——续期 302 的第二跳会同时带上
    旧的 host-only 值与刚种下的新 domain-scoped 值（`sid=OLD; sid=NEW`）。若只取
    首个会误判为旧值仍在用；改为"多值时优先取当前仍有效的那个"，再退化为最后一个
    （供"确实没有一个有效"的负向路径判定用），与是否只有单值无关，恒定成立。
    """
    values: list[str] = []
    raw = request.headers.get("cookie", "")
    for part in raw.split(";"):
        key, _, value = part.strip().partition("=")
        if key == name and value:
            values.append(value)
    for value in values:
        if state.is_valid(value):
            return value
    return values[-1] if values else None


def make_mock_idp_handler(state: MockIdPState) -> Callable[[httpx.Request], httpx.Response]:
    """构造 mock IdP 的 `httpx.MockTransport` 处理函数（本段顶部路由表）。"""

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        state.request_log.append((request.method, path))
        cookie = _resolve_mock_cookie(request, state)

        if state.challenge_active:
            response = httpx.Response(
                403, headers={"cf-mitigated": "challenge"}, text="Just a moment..."
            )
        elif path == "/login":
            response = httpx.Response(200, text="<html>mock IdP login page</html>")
        elif path == "/my-account":
            if state.is_valid(cookie):
                response = httpx.Response(200, text="<html>Signed in as prof — my account</html>")
            else:
                response = httpx.Response(302, headers={"location": "https://mock.test/login"})
        elif path == "/InstitutionalLogin":
            if state.idp_session_alive:
                new_cookie = state.next_refreshed_cookie()
                response = httpx.Response(
                    302,
                    headers={
                        "location": "https://mock.test/my-account",
                        "set-cookie": f"{MOCK_IDP_COOKIE_NAME}={new_cookie}; "
                        "Domain=mock.test; Path=/",
                    },
                )
            else:
                response = httpx.Response(302, headers={"location": "https://mock.test/idp/login"})
        elif path == "/idp/login":
            response = httpx.Response(200, text="<html>institutional login required</html>")
        elif path.startswith("/article-pdf/"):
            article_id = path.rsplit("/", 1)[-1]
            if article_id in state.no_entitlement_ids:
                response = httpx.Response(
                    302, headers={"location": "https://mock.test/article-abstract"}
                )
            elif state.is_valid(cookie):
                response = httpx.Response(200, content=b"%PDF-1.4 mock fulltext bytes")
            else:
                response = httpx.Response(401, text="unauthorized")
        elif path == "/article-abstract":
            response = httpx.Response(200, text="<html>Get access / Purchase this article</html>")
        else:
            response = httpx.Response(404, text="mock IdP: unknown route")

        state.status_counts[response.status_code] += 1
        return response

    return handler


def storage_state_bytes(
    cookie_value: str, *, domain: str = "mock.test", name: str = MOCK_IDP_COOKIE_NAME
) -> bytes:
    """构造 Playwright storage_state JSON 字节（假首登 seam 的返回值形状）。"""
    return json.dumps(
        {
            "cookies": [
                {"name": name, "value": cookie_value, "domain": domain, "path": "/", "secure": True}
            ],
            "origins": [],
        },
        ensure_ascii=False,
    ).encode("utf-8")


def cookie_header(value: str, *, name: str = MOCK_IDP_COOKIE_NAME) -> dict[str, str]:
    """静态 `Cookie:` 头（供 `HttpClient(extra_headers=...)` 直取路径注入 session cookie；
    http.py 模块 docstring 明示的既有用法——`extra_headers` 是 client 实例私有附加头，
    绝不跨 client 复用，见 openreview `Cookie: openreview.accessToken=` 先例）。
    """
    return {"Cookie": f"{name}={value}"}


@pytest.fixture
def mock_idp_state() -> MockIdPState:
    """每测试独立的 mock IdP 状态（零跨测试残留）。"""
    return MockIdPState()
