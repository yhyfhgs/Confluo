"""browser-fetch 横切件（[design/11](../../docs/design/11-browser-fetch.md) §3.2 **案 A 薄接缝
最小件**；D-030 裁决①⑤⑥⑧）。

三消费方（ssrn 模式 B / aea pubs 全文 / wiley 页面兜底）统一的"浏览器上下文取回单篇"通道：
一次调用起一个**一次性上下文、用完即毁**，不建池、不建账本、不做批量。

**AC-0.2 红线（§2，不可协商）**——本模块只做五件事，其余明令出列：

1. 在用户**已合法登录/无需登录**的上下文内打开目标 URL、取回单个 PDF 资产；
2. 对响应做四态判定——**全权委托 `ChallengeDetector`**（特征库单一权威源，本模块零特征串）；
3. 判 CHALLENGE → 立即停手抛 `Challenged`（→ BLOCKED + 域冷却 24h），**零后续动作**：
   不等待质询自动通过、不点击"我不是机器人"、不注入/执行质询脚本、不调打码服务、
   不轮换 UA/指纹/代理重试、不降级 stealth；`fetch_one` 全函数**无 except 重试块**
   （任何失败一次性上抛，交 pipeline 错误分类学处置，design/05 §4）；
4. 预算护栏（§7）：域级限速+抖动、每 venue×域 日配额、挑战冷却、连续失败熔断——
   **全部离线判定**（sqlite + 冷却 JSON），零网络、零新表（唯一事实源 = FetchLog）；
5. 只把字节落到调用方给的 `dest`（`.part` 路径）——`PartFileIO`/魔数/`finalize_fetch`
   三原语归 `pipeline/stages.py::_fetch_via_browser`，本模块不另起落盘路径（§4.5）。

**不做**：discover/enumerate/search；登录（首登仍归 `auth/browser.py::run_headed_login`，
D-006 人在回路）；批量/并发（并发恒 1）；挑战求解/重试/UA 轮换/代理切换/指纹伪装；
常驻浏览器进程或上下文池（§3.5 选案理由：能力面应当**恰好等于**合规面）。

**依赖分层**：playwright 是可选 extra（`[auth-browser]`），**模块顶层零 import**——
`playwright_launcher()` 返回的默认 launcher 在真实取回时才惰性 import；未装 →
`AuthRequired` + 安装指引（复用 `auth/browser.py` 的**同一条**指引常量，不复制字面）。
测试全走假 `LaunchFetchFn` + stub `BrowserFetchHandle`（零浏览器零网络）。

**演进缝（§3.6，当前不做）**：若实测证实"每篇冷启抬高质询频次"，最小升级 = 在
`fetch_one` 之上加**调用方作用域**的 context 复用器（追加一个 keyword-only 形参即可，
对本签名纯附加、零破坏）——不引入常驻进程/账本表/批量 CLI。

## 已知边界（清账指针；T6 审查登记，#1/#2 已由 T11 controller 裁决闭合，全部**不改行为**）

1. **【已闭合，T11 controller 前置裁决】open_access 消费方干净上下文 by design**：
   `storage_state` 只来自 runner 的 auth 健康门，而该门对 `family != "auth_gated"` 早
   返回 ⇒ ssrn/aea（本通道两个主消费方，均 `open_access` family）**恒以干净上下文
   启动**——这是这两个消费方的**应有姿态，不是凭证注入缺口**：browser-fetch 对它们的
   语义是公开内容的浏览器渲染取回（解决"需要 JS 渲染"，非"需要登录"），Cloudflare 拦截
   由既有 S-c 头级判定（403+`cf-mitigated`→CHALLENGE）+ 域级冷却处置。wiley 页面兜底
   属 `auth_gated`，消费 runner 已为其建立的真实 session（既有路径覆盖，零改动）。
   同一裁决同步 `pipeline/stages.py::_browser_storage_state` docstring 与
   `tests/manual/browser_fetch_runbook.md` §5 清账表第 1 行。
2. **【已闭合，T11 controller 裁决：本 Phase 不动】下载触发的第二次导航不再过判定器**：
   `goto` 判定 OK 后，`download_via(trigger=…)` 内的导航结果不重新分类（与 §4.2 设计伪码
   同形）。若站点在第二跳才发质询，本次表现为**下载未发生 → 归 `TRANSIENT`**（非
   CrawlerError 的下载异常统一映射 TRANSIENT）——**不是绕过**，但会**进重试表**（4 次
   尝试 / 2·8·30s 退避），即对刚发过质询的域再敲三次。T11 提案：改判 `CHALLENGE`（→ 域
   冷却，零重试）更贴合"检测到风控即停手"精神，但需 `BrowserFetchHandle.download_via`
   在失败路径暴露响应快照才可行，属接口面扩张。**裁决**：现状"过度重试"方向安全、
   与 §4.2 设计伪码同形属设计既定——本 Phase 不改冻结接口，提案原文登记
   `tests/manual/browser_fetch_runbook.md` §5 清账表，标 P8/T18（AC-BF 转正时评估）。
3. **AC-BF.4② 时序载体不足** → 归 T18（AC-BF 转正时定审计载体）：obslog 每次调用只记
   `rate_wait_ms` 汇总，无请求发起时刻序列，"相邻两次请求间隔 ≥ 域声明下限"只能间接推算；
   限速的真实约束在 `RateLimiter` 桶上，不在日志上。
4. **直调 `fetch_one` 时冷却读侧只认域键**：`challenge_cooldown_active` 已委派
   `pipeline/cooldown.read_until`（T3），但仍只查**单个域键**，不遍历 `resolve_keys` 给出的
   `<adapter_id>` 旧兼容键——本通道手上只有 URL（无 venue→adapter 路由），域键是它能如实
   主张的全部。经 pipeline 走时由 runner 的 pre-stage 冷却门（读全键集）先拦，不受影响。
5. **【已登记，T11 controller 裁决：已知缺口，不改行为】aea browser-fetch 通道可达性**：
   `AeaAdapter.family` 仍 `auth_gated`（未改）；本通道激活前提是配置 aea profile（机构
   订阅用户，首登人工，D-006 语义）——无 profile 时 runner 的 auth 健康门
   （`_auth_gate_fetch`）在到达 `pipeline/stages.py` 的 RENDER_PAGE 分支**之前**即
   `CONFIG`-BLOCK，与本模块/`ctx.browser_fetch` 开关无关。OA 刊（jel/jep）全文由既有
   unpaywall OA-fallback（D-024）承载；订阅刊（aer/aeri/aej_*）在未配置 profile 前如实
   BLOCKED——非本模块缺陷，是 D-006 aea 认证未落地的已知外部依赖（同构 elsevier T7b
   dormant 语义）。详见 `tests/manual/browser_fetch_runbook.md` §5 清账表第 5 行 +
   `docs/design/adapters/aea.md` §10。
"""

from __future__ import annotations

import importlib
import json
import shutil
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol, runtime_checkable
from urllib.parse import urlsplit

# 安装指引常量单一源：design/11 §4.1 明令 `auth/browser.py` **零改动**，故消费其模块私有
# 常量而非复制字面（复制=两处漂移面；§6.1"复用 auth/browser.py 逐字提示"）。
from paper_crawler.auth.browser import _BROWSER_INSTALL_HINT
from paper_crawler.auth.challenge import ChallengeDetector, ClassifyResult
from paper_crawler.errors import AuthRequired, Challenged, CrawlerError, ErrorClass
from paper_crawler.types import AssetPlan, UrlStrategy

_PROFILE_PREFIX = "pc-bfetch-"
# 连续非挑战失败熔断阈值（§7.1 L4；CHALLENGE 的阈值恒为 1——即刻停手，不在此列）。
_BREAKER_THRESHOLD = 3


# ---------------------------------------------------------------------------
# 冻结件：Protocol / 值对象（Phase 7 §2 冻结件表 `browserfetch.BrowserFetchHandle`）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PageResponse:
    """`goto` 返回的最小四元组——**恰好**是 `ChallengeDetector.classify` 的入参形态
    （§5.1：判定器与传输无关，浏览器路径天然完整），不多不少。"""

    status: int
    headers: Mapping[str, str]
    final_url: str
    body: bytes


class BrowserFetchHandle(Protocol):
    """一次浏览器上下文的最小把手（鸭型；假 seam 可测，沿 `BrowserContextHandle` 先例）。"""

    def goto(self, url: str) -> PageResponse:
        """导航到 `url`，返回判定四元组。"""
        ...

    def download_via(self, trigger: Callable[[], None], dest: Path) -> int:
        """Playwright `expect_download` 的抽象：执行 `trigger`（点击/导航）→ 落盘 → 返字节数。"""
        ...

    def close(self) -> None:
        """关闭上下文（一次性上下文用完即毁）。"""
        ...


LaunchFetchFn = Callable[[str, bytes | None], BrowserFetchHandle]
"""`(user_data_dir, storage_state_bytes | None) -> handle`；默认实现惰性 import playwright。"""

ResolveInContext = Callable[[BrowserFetchHandle], AssetPlan]
"""同批约束载体（§4.4）：在**同一上下文内**解析出 volatile 计划，立即用于本次下载。"""


@runtime_checkable
class BrowserContextResolver(Protocol):
    """同批约束的**生产端**可选协议（§4.4；沿 `adapter.HttpClientConsumer` 鸭型先例）。

    `ResolveInContext` 是消费端的形态（`fetch_one` 的形参）；产出该闭包的一侧是 adapter：
    实现本方法即声明"我的 `RENDER_PAGE` 计划带同批约束"，`pipeline/stages.py` 据此把
    `adapter.resolve_in_browser_context` 包成闭包传进 `fetch_one`。**按能力鸭型发现，
    不建 adapter 名单**（派发仍是策略驱动，contract 反模式护栏逐字不变）。

    实现约定（design/11 §4.4 + §2 红线 2）：
    - 入参 `plan` = adapter 自己 resolve 产的 landing 计划（`url` 是可入库的稳定引用）；
    - 在**同一 `handle`**（同 context）内完成站内解析，返回携 volatile URL 的新计划；
    - 解析过程中的**每一次导航都必须过判定器**（用 `classify_or_raise`）——否则风控页会
      退化成"解析不出链接"，把 CHALLENGE 静默降级；
    - 返回计划的 `url_strategy` 仍须是 `RENDER_PAGE`（`fetch_one` 会再校一次）。
    """

    def resolve_in_browser_context(
        self, plan: AssetPlan, handle: BrowserFetchHandle
    ) -> AssetPlan: ...


@dataclass(frozen=True)
class BrowserFetchOutcome:
    """单次取回结果。`url` = 本次**实际请求**的 URL（同批场景下即 volatile URL）——
    仅供调用方审计记账（fetch_log/obslog）；**绝不回写 `asset.url`**（§4.4 持久化纪律：
    asset.url 记 landing 引用，volatile URL 只活在单次调用的栈上）。"""

    verdict: ClassifyResult
    url: str
    ok: bool = False
    bytes_written: int = 0
    no_entitlement: bool = False


# ---------------------------------------------------------------------------
# §7 预算护栏（四层，全离线可判）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BudgetGate:
    """限速/配额/冷却/熔断的统一前置门（§7.3）——**只读本地状态，零网络**。

    四个依赖以可调用件注入（调用方装配，见 `pipeline/stages.py::_browser_budget_gate`）：
    数据源恒为既有事实源（FetchLog 派生 + runner 写的冷却 JSON + 既有 `RateLimiter` 桶），
    **不新建表、不新建状态目录**（§3.4 维度 4：预算事实源唯一性优于维度丰富度）。

    `daily_cap` 语义 = 每 venue×域 每日 fetch 尝试篇次上限（成败均计）。裁决⑥"与 VenueSpec
    取 min"：`Config.browser_daily_cap` 默认 50 已严于 ssrn.md §5 的 100/日，min 天然满足；
    `VenueSpec` 当前**无**日配额字段（冻结 schema，本卡不动），故未做 per-venue 收窄通道。
    """

    daily_cap: int
    count_today: Callable[[str, str], int]  # (venue_id, domain) -> 当日 fetch 尝试篇次
    cooldown_active: Callable[[str], bool]  # domain -> 是否在挑战冷却期（§5.6 域级键）
    consecutive_failures: Callable[[str], int]  # domain -> 当日连续失败数
    wait: Callable[[str], float]  # domain -> 已执行的限速+抖动等待秒数
    breaker_threshold: int = _BREAKER_THRESHOLD

    def check_or_raise(self, *, venue_id: str, domain: str) -> int:
        """冷却 → 配额 → 熔断三判定合一（顺序即优先级）；通过则返回**当日已用篇次**。

        冷却优先于配额（§7.3）：判罚期内继续敲门只会加重判罚，配额还剩多少无关紧要。
        """
        if self.cooldown_active(domain):
            raise Challenged(
                f"域 {domain} 处于挑战冷却期（24h）——browser-fetch 暂停对该域发起请求",
                detail="browser_cooldown",
            )
        used = self.count_today(venue_id, domain)
        if used >= self.daily_cap:
            raise CrawlerError(
                ErrorClass.CONFIG,
                f"browser-fetch 日配额已达上限（venue={venue_id} domain={domain} "
                f"used={used} cap={self.daily_cap}）",
                detail="browser_quota",
            )
        if self.consecutive_failures(domain) >= self.breaker_threshold:
            raise CrawlerError(
                ErrorClass.CONFIG,
                f"域 {domain} 连续失败 ≥{self.breaker_threshold} 次，当日停发（熔断）",
                detail="browser_breaker",
            )
        return used

    def wait_rate(self, *, domain: str) -> float:
        """域级限速闸 + 抖动（§7.1 L2；并发恒 1）。返回实际等待秒数。"""
        return self.wait(domain)


def challenge_cooldown_active(home: Path, key: str, *, now: datetime | None = None) -> bool:
    """读侧：`<config-home>/state/cooldown/<key>.json` 是否仍在冷却期内（§5.6/§8.4）。

    **委派 `pipeline/cooldown.py`**（T3 卡的公用模块；本函数原先自建的路径/格式知识已删除
    ——单一实现，杜绝两处漂移）。写侧权威仍是 `runner.py::_enter_challenge_cooldown`
    （E-1/D-030 裁决③），本函数**只读、不清理过期文件**（清理归 runner/`cooldown.clear`，
    避免两处并发删同一文件）——委派后该行为逐字不变（`read_until` 亦只读不删）。

    缺失/内容损坏/已过期一律 False：判定失败退回"未冷却"是安全的——真正的判罚会在下一次
    请求时由 `ChallengeDetector` 如实命中并重新写冷却。**键本身非法**（路径穿越等）由
    `cooldown.cooldown_path` 响亮抛 `CrawlerError(CONFIG)`（T3 的键白名单加固）——那是调用方
    给错键，与"磁盘数据坏了"是两类问题，不该被静默吞成"未冷却"。
    """
    # 函数内 import：`paper_crawler.pipeline.__init__` 会 eager-import `stages`，而 stages
    # 又 import 本模块——顶层 import 会成环。冷却判定每次取回只跑一次，代价可忽略。
    from paper_crawler.pipeline import cooldown

    until = cooldown.read_until(home, key)
    if until is None:
        return False
    return (now or datetime.now(UTC)) < until


# ---------------------------------------------------------------------------
# 真实 Playwright launcher（可选 extra；惰性 import，测试零触达）
# ---------------------------------------------------------------------------


def _import_playwright() -> Any:
    """惰性 import `playwright.sync_api`；未装 `[auth-browser]` → `AuthRequired`（§6.1）。"""
    try:
        return importlib.import_module("playwright.sync_api")
    except ImportError as exc:
        raise AuthRequired("browser-based fetch unavailable", detail=_BROWSER_INSTALL_HINT) from exc


class _PlaywrightFetchContext:  # pragma: no cover - 真实浏览器路径（§8 T-11 runbook 手动门）
    """真实 headless persistent context 把手（storage_state 注入 + 下载落盘）。

    - **headless 恒真**：headed 只属首登（既有通道）；本通道**不**开 headed 让用户"手动过
      挑战"——那属 §6.2 人工介入流（用户在**自己的**浏览器里处理，系统只等 `crawler resume`）。
    - **诚实身份**（D-014 / 红线 §2-3）：以附加头 `X-Paper-Crawler: <UA 串>` 标识本系统，
      **绝不改写 UA 伪装成纯浏览器**（§11 开放问题③：UA 形态待真实站点验收，附加头是当前
      不伪装的最小实现）。
    """

    def __init__(
        self,
        sync_api: Any,
        user_data_dir: str,
        storage_state: bytes | None,
        extra_headers: Mapping[str, str],
    ) -> None:
        self._playwright = sync_api.sync_playwright().start()
        try:
            self._context = self._playwright.chromium.launch_persistent_context(
                user_data_dir, headless=True
            )
            if storage_state is not None:
                cookies = json.loads(storage_state.decode("utf-8")).get("cookies", [])
                if cookies:
                    self._context.add_cookies(cookies)
            if extra_headers:
                self._context.set_extra_http_headers(dict(extra_headers))
            self._page = self._context.new_page()
        except Exception:
            self._playwright.stop()
            raise

    def goto(self, url: str) -> PageResponse:
        response = self._page.goto(url)
        if response is None:
            raise CrawlerError(ErrorClass.TRANSIENT, f"浏览器导航无响应: {url}")
        return PageResponse(
            status=int(response.status),
            headers=dict(response.headers),
            final_url=str(response.url),
            body=bytes(response.body()),
        )

    def download_via(self, trigger: Callable[[], None], dest: Path) -> int:
        with self._page.expect_download() as info:
            trigger()
        dest.parent.mkdir(parents=True, exist_ok=True)
        info.value.save_as(str(dest))
        return dest.stat().st_size

    def close(self) -> None:
        try:
            self._context.close()
        finally:
            self._playwright.stop()


def playwright_launcher(*, identity_header: str | None = None) -> LaunchFetchFn:
    """默认 launcher 工厂：惰性 import + 一次性 persistent context。

    `identity_header` = D-014 身份串（`build_user_agent` 产物），以 `X-Paper-Crawler` 附加头
    发出；None 时不发该头。工厂形态是为了把 config 依赖留在装配层——本模块不读 config。
    """

    def _launch(user_data_dir: str, storage_state: bytes | None) -> BrowserFetchHandle:
        sync_api = _import_playwright()  # 未装 [auth-browser] → AuthRequired（此处即抛）
        headers = {"X-Paper-Crawler": identity_header} if identity_header else {}
        return _PlaywrightFetchContext(sync_api, user_data_dir, storage_state, headers)

    return _launch


# ---------------------------------------------------------------------------
# 主入口：fetch_one（纯函数；不重试、不对抗、并发恒 1）
# ---------------------------------------------------------------------------


def host_of(url: str) -> str:
    """取 URL 的 host（限速/配额/冷却三处共用的域键；与 runner 冷却键口径一致）。"""
    parts = urlsplit(url)
    return parts.hostname or parts.netloc or url


def _require_render_page(plan: AssetPlan, *, origin: str) -> None:
    """本通道只服务 `RENDER_PAGE` 计划；其余响亮 CONFIG（§4.2/§4.6 裁决⑤）。"""
    if plan.url_strategy is not UrlStrategy.RENDER_PAGE:
        raise CrawlerError(
            ErrorClass.CONFIG,
            f"browser-fetch 只接受 url_strategy=render_page 的计划，{origin} 给的是 "
            f"{plan.url_strategy.value!r}",
            detail="browser_strategy",
        )


def classify_or_raise(
    response: PageResponse, *, domain: str, detector: ChallengeDetector | None = None
) -> ClassifyResult:
    """四态判定 + 两个停手态的统一抛法（§5.1；本模块**唯一**的判定出口）。

    抽出为模块级函数是为了让**同批解析闭包**（§4.4 生产端，见 `BrowserContextResolver`）
    与 `fetch_one` 主路径共用**同一份**语义：浏览器通道里的每一次导航都必须过判定器，
    任何"少判一跳"都是把风控页静默降级成别的终态（正是 S-c 收口的那类缺口）。

    - CHALLENGE → `Challenged`（红线：唯一合法动作是分类并停手，零重试零绕过零求解）；
    - LOGIN_REDIRECT → `AuthRequired`（storage_state 失效，提示重登）；
    - NO_ENTITLEMENT / OK → **原样返回**，由调用方按自己的语境处置（`fetch_one` 返
      `Outcome(no_entitlement=True)`；解析闭包无法返回"无权限计划"，故转 CrawlerError）。
    """
    verdict = (detector if detector is not None else ChallengeDetector()).classify(
        status=response.status,
        headers=response.headers,
        final_url=response.final_url,
        body=response.body,
    )
    if verdict is ClassifyResult.CHALLENGE:
        # 红线：**唯一合法动作**是分类为 CHALLENGE 并停手（零重试、零绕过、零求解）。
        raise Challenged(
            f"浏览器上下文命中风控/挑战页（domain={domain}）——已停手，"
            "请在**你自己的浏览器**中正常访问并完成站点验证后 `crawler resume --all`",
            detail="browser_challenge",
        )
    if verdict is ClassifyResult.LOGIN_REDIRECT:
        raise AuthRequired(
            f"浏览器上下文被导向登录页（domain={domain}）",
            detail="storage_state 已失效——重登：crawler auth login <provider>",
        )
    return verdict


def fetch_one(
    *,
    plan: AssetPlan,
    venue_id: str,
    dest: Path,
    storage_state: bytes | None,
    budget: BudgetGate,
    detector: ChallengeDetector | None = None,
    resolve_in_context: ResolveInContext | None = None,
    launch: LaunchFetchFn | None = None,
) -> BrowserFetchOutcome:
    """单篇浏览器上下文取回（§4.2）。**不重试、不对抗、并发恒 1**（§2 红线）。

    参数：
    - `plan`：`url_strategy` 必须为 `RENDER_PAGE`（否则响亮 CONFIG）；
    - `dest`：`.part` 路径（落盘归 pipeline，本函数只把字节交到这里）；
    - `storage_state`：`CredentialStore` 解密后的字节；**None 是合法路径**（gold OA /
      未 opt-in 账号 → 干净上下文，遇挑战即 BLOCKED，符合红线）；
    - `budget`：§7 三判定前置门（离线）；
    - `resolve_in_context`：ssrn 同批约束载体（§4.4），非 None 时先在**同一上下文内**
      解析出 volatile 计划；
    - `launch`：测试 seam（假 launcher 注入 → 零真实浏览器）。

    失败语义：CHALLENGE→`Challenged`；LOGIN_REDIRECT→`AuthRequired`；NO_ENTITLEMENT→
    正常返回（`no_entitlement=True`，交调用方走 OA-fallback 既有链）；预算门→
    `Challenged`/`CrawlerError(CONFIG)`。**全函数无 except 重试块**。
    """
    _require_render_page(plan, origin="调用方")
    domain = host_of(plan.url)
    # 预算三判定（离线，零请求）——失败即抛，浏览器根本不起。
    budget.check_or_raise(venue_id=venue_id, domain=domain)

    verdict_detector = detector if detector is not None else ChallengeDetector()
    launch_fn = launch if launch is not None else playwright_launcher()
    # A-M7 一次性 profile 目录纪律：浏览器 profile 内含明文 cookie/缓存，残留等价 session 泄漏。
    profile_dir = tempfile.mkdtemp(prefix=_PROFILE_PREFIX)
    try:
        handle = launch_fn(profile_dir, storage_state)
        try:
            budget.wait_rate(domain=domain)  # 判定导航前过域级闸（含抖动）
            effective = plan if resolve_in_context is None else resolve_in_context(handle)
            _require_render_page(effective, origin="resolve_in_context")
            response = handle.goto(effective.url)
            verdict = classify_or_raise(response, domain=domain, detector=verdict_detector)
            if verdict is ClassifyResult.NO_ENTITLEMENT:
                return BrowserFetchOutcome(verdict=verdict, url=effective.url, no_entitlement=True)
            # OK：下载触发是**第二次真实请求**，故再过一次域级闸（宁可更慢，不少记一次请求）。
            budget.wait_rate(domain=domain)
            written = handle.download_via(
                trigger=lambda: _trigger_download(handle, effective.url), dest=dest
            )
            return BrowserFetchOutcome(
                verdict=verdict, url=effective.url, ok=True, bytes_written=written
            )
        finally:
            handle.close()
    finally:
        shutil.rmtree(profile_dir, ignore_errors=True)  # 异常路径亦清理（凭证残留红线）


def _trigger_download(handle: BrowserFetchHandle, url: str) -> None:
    """下载触发动作：在 `expect_download` 上下文内导航到资产 URL（响应丢弃——
    判定已在上一步完成；此处只为触发下载事件）。"""
    handle.goto(url)


__all__ = [
    "BrowserContextResolver",
    "BrowserFetchHandle",
    "BrowserFetchOutcome",
    "BudgetGate",
    "LaunchFetchFn",
    "PageResponse",
    "ResolveInContext",
    "challenge_cooldown_active",
    "classify_or_raise",
    "fetch_one",
    "host_of",
    "playwright_launcher",
]
