"""六阶段 stage 执行器 + `Selector`/`StageContext`（接口冻结件 §2.7；design/05 §1）。

职责边界：本模块执行"一个已领取任务"的业务动作（discover/enumerate/resolve/
fetch/extract/ingest 六类；`pull` 的级联编排在 `runner.py`）。任务状态机操作
（complete/fail/block）与错误分类路由都不在这里——handler 只做事，失败一律抛
`CrawlerError`，由 runner 按 design/05 §4 统一路由。

关键语义（段号指 design/05）：
- 阶段间只通过持久化实体通信（§1 不变式）：handler 的输入全部从任务参数 + DB 行
  重建（`{"issue": <ulid>}` / `{"paper": <ulid>}` / `{"asset": <ulid>}`），不依赖
  进程内的上游对象——kill-9 后重跑（AC-1.3）与 resume（AC-1.5）都靠这一点成立。
- 限速接入：每次 adapter **网络型**调用（discover/enumerate/fetch，及需发请求的
  resolve）前 `limiter.acquire(domain)` → `sleeper(wait)`；discover/enumerate 记账在
  metadata_adapter.domains[0]，resolve/fetch 在 fulltext_adapter.domains[0]
  （与 `Route.rate_overrides` 的键一致）。fetch 的 wait 记入 FetchLog.rate_wait_ms。
  **例外（缺陷 C-C）**：adapter 声明 `resolve_offline=True`（`resolve_assets` 可证明
  零网络、纯 URL 构造）时 resolve 阶段跳过闸——大 venue（2260 篇量级）不再逐篇限速
  空转；豁免只给已证明零网络的路径，真实网络 resolve 策略（未声明）仍过闸。
- fetch 前 re-resolve（phase1-plan "T7c 追加设计裁决"）：fetch 子任务执行时现场
  调 `resolve_assets` 取最新 `AssetPlan` → `Repo.refresh_asset_plan` 同步 asset 行
  → 再用**新 plan**（而非 DB 旧 url）执行 fetch。mock 的故障注入编译在 url 查询串
  里，resume 修复场景必须以新 resolve 为准（AC-1.5 成立的前提）；真实 adapter 的
  signed url / entitlement 同样有时效，语义同构。裁决给出的顺序是单次
  `acquire`：re-resolve → refresh → acquire → sleeper → fetch。
- 幂等跳过（§5.3）：asset 已 fetched 且文件存在且 sha256 相符 → handler 返回
  `"skipped"`（runner 计入 RunReport.skipped）并 `log_event(msg="skipped")`，
  **不产生新的成功 fetch_log 行**（AC-1.3 判据）。
- extract（Phase 1 语义，计划 Task 7 前置讨论）：对 fetched pdf 资产写 fulltext 行
  （extractor="noop", extractor_ver="1", text_path=None, char_count=0）并把
  paper.ingest_state 推进到 extracted；幂等键 (asset, extractor_ver)——fulltext 表
  paper 1-1，重跑不重插。本地零网络。
- ingest（Phase 1 语义）：把"有 fetched 资产"的 paper 的 ingest_state 推进到
  fetched（只前进不回退；identifier 锚点强合并已由 `Repo.upsert_paper` 在
  enumerate 时天然处理），并向 RunReport.notes 追加人读摘要。本地零网络。

实现期注记（T10 收尾回填设计文档）：接口冻结件 §2.4 的 `Repo` 未提供 identifier /
fulltext 查询写入面，本模块对这两张表经 `StageContext.db` 直接读写（identifier 只读、
fulltext 幂等插入），不越权改 `Repo` 签名。
"""

from __future__ import annotations

import hashlib
import json
import random
import sqlite3
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal
from urllib.parse import urlsplit

from paper_crawler.auth.store import CredentialStore
from paper_crawler.browserfetch import (
    BudgetGate,
    challenge_cooldown_active,
    fetch_one,
    host_of,
    playwright_launcher,
)
from paper_crawler.config import Config
from paper_crawler.errors import CrawlerError, ErrorClass
from paper_crawler.obslog import log_event
from paper_crawler.pipeline.fetchio import PartFileIO, validate_pdf_magic
from paper_crawler.pipeline.report import RunReport
from paper_crawler.ratelimit import RateLimiter
from paper_crawler.registry import Route, VenueRegistry
from paper_crawler.storage.db import Database
from paper_crawler.storage.repo import FetchLogRow, Repo
from paper_crawler.tasks import TaskQueue
from paper_crawler.types import (
    AssetKind,
    AssetPlan,
    IssueRef,
    PaperStub,
    RatePolicy,
    SessionBackend,
    SessionHandle,
    UrlStrategy,
    utcnow_iso,
)
from paper_crawler.useragent import build_user_agent

if TYPE_CHECKING:
    # 冻结面类型精度（spec §8）——`from __future__ import annotations` 使注解惰性，仅供
    # mypy 解析，运行时不 import（避免 pipeline→adapter/http 的运行时依赖）。
    from paper_crawler.adapters.unpaywall.adapter import UnpaywallAdapter
    from paper_crawler.http import HttpClient

# ---------------------------------------------------------------------------
# 接口冻结件 §2.7：Selector / StageContext
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Selector:
    """pull/list 的圈定条件（接口冻结件 §2.7）。

    - `volume`/`issue`/`year` 圈定 issues（`issue` 对应 IssueRef.number）；
    - `dois` 圈定 papers（按 identifier，DOI 比较大小写不敏感）；
    - `filter_expr` = 标题大小写不敏感子串（FR-05 关键词过滤；DSL 属 Phase 6）；
    - `limit` = fetch 的 asset 数上限。**前置到 resolve 圈选**（缺陷 C-C）：确定性顺序
      下只对前 N 篇 paper 做 resolve（而非全量 resolve 后才截断），再对其候选做 asset
      级截断——语义仍是"最多 N 个 asset"，但大 venue 不再对将丢弃的绝大多数做无谓 resolve。
    """

    volume: str | None = None
    issue: str | None = None
    year: int | None = None
    dois: tuple[str, ...] = ()
    filter_expr: str | None = None
    limit: int | None = None


@dataclass
class StageContext:
    """一次 pipeline 运行的全部依赖注入（接口冻结件 §2.7）。

    `sleeper` 承接一切等待（限速 wait 与重试退避），测试注入假 sleeper 即可零延时
    断言等待序列；`dry_run=True` 时 pull 级联止于 resolve（design/05 §6）。
    """

    config: Config
    db: Database
    repo: Repo
    registry: VenueRegistry
    queue: TaskQueue
    limiter: RateLimiter
    sleeper: Callable[[float], None] = time.sleep
    dry_run: bool = False
    # ---- Phase 4 auth 接缝（auth-framework §8；纯附加/默认关闭 → Phase 1-3 venue 零回归）----
    # OA-fallback 总开关（§8.1）：no_entitlement 兜底是否派生 oa_fallback 任务。默认 False =
    # 关闭；CLI 的 pull/grab 装配期置 True（连带注入下面三槽）。既有直建 StageContext 的测试
    # 与命令保持默认 False → 行为逐字不变（回归锁定安全网）。
    oa_fallback: bool = False
    # unpaywall adapter 实例（§8.1 接线点 B `_stage_oa_fallback` 消费）；None = 未装配 → 静默跳过。
    unpaywall_adapter: UnpaywallAdapter | None = None
    # 共享 HttpClient（§8.1 接线点 C `_fetch_oa_direct` 的通用 direct stream 复用；离线路径为
    # None → OA direct fetch 静默跳过）。
    http: HttpClient | None = None
    # auth_gated venue 的活跃 SessionHandle 注入通道（venue_id → session）：**runner 独占写**
    # （健康门建立/refresh 后落此表，§8.2），resolve/fetch 阶段只读消费——传给 adapter 冻结
    # 协议里自 Phase 1 即存在的 `session` 形参。默认空 → Phase 1-3 venue 恒读到 None（session=
    # None，与既有逐字一致）。
    auth_sessions: dict[str, SessionHandle] = field(default_factory=dict)
    # ---- Phase 7 browser-fetch 接缝（11-browser-fetch §3.2 案 A 的**唯一**新增槽）----------
    # 本次运行是否允许走浏览器上下文取回通道（§7.1 L1 三级门之一）：CLI `grab --browser` 置位。
    # 默认 False = 关闭（D-029"非默认"）；与 `Config.browser_fetch_enabled` **同时为真**才生效，
    # 二者皆关时 `RENDER_PAGE` 计划在 `_stage_fetch` 返回 `skipped`（不派生失败、不计 failures，
    # 语义等价 §4.6 裁决的 "deferred"，且零冻结件改动）。
    browser_fetch: bool = False


StageOutcome = Literal["done", "skipped"]

# ---------------------------------------------------------------------------
# 共用小件
# ---------------------------------------------------------------------------


def _params(task: sqlite3.Row) -> dict[str, Any]:
    """解析任务行的 params_json（enqueue 侧恒写 JSON object）。"""
    parsed: dict[str, Any] = json.loads(str(task["params_json"]))
    return parsed


def _task_venue(task: sqlite3.Row) -> str:
    venue_id = task["venue_id"]
    if venue_id is None:
        raise CrawlerError(
            ErrorClass.CONFIG, f"task {task['id']} ({task['kind']}) is missing venue_id"
        )
    return str(venue_id)


def route_for(ctx: StageContext, venue_id: str) -> Route:
    """解析 venue 路由并把两侧 adapter 的限速策略登记进 limiter（幂等，取最保守值）。

    注册与 override 都单调不放宽（ratelimit 语义），因此每次调用重复登记是安全的，
    不需要缓存；`rate_overrides` 的键 = fulltext_adapter.domains[0]（registry 语义）。

    多域 adapter（如 arxiv 的 export/oaipmh/arxiv.org）把 domains[1:] `alias` 到主域
    domains[0]，使三域共用一份 ToU 预算（并发 1）——HttpClient 逐请求在实际请求 host
    `acquire`（C4 红线修复）时，副域经别名落到主域同一桶，不会因未注册而 fail-fast，
    也不会各自独立放行绕过「三域共享 1req/3s」。
    """
    route = ctx.registry.route(venue_id)
    for adapter in (route.metadata_adapter, route.fulltext_adapter):
        primary = adapter.domains[0]
        ctx.limiter.register(primary, adapter.default_rate)
        for secondary in adapter.domains[1:]:
            ctx.limiter.alias(secondary, primary)
    for domain, rpm in route.rate_overrides.items():
        ctx.limiter.override(domain, rpm)
    return route


def acquire_and_wait(ctx: StageContext, domain: str) -> float:
    """消费一个限速 token；需要等待时经 `ctx.sleeper` 等待。返回等待秒数（0=立即）。"""
    wait = ctx.limiter.acquire(domain)
    if wait > 0:
        ctx.sleeper(wait)
    return wait


def _paper_row(ctx: StageContext, paper_id: str) -> sqlite3.Row:
    rows = ctx.db.query("SELECT * FROM paper WHERE id = ?", (paper_id,))
    if not rows:
        raise CrawlerError(ErrorClass.CONFIG, f"task references missing paper {paper_id!r}")
    return rows[0]


def _paper_stub(ctx: StageContext, paper: sqlite3.Row) -> PaperStub:
    """从持久化的 paper + identifier 行重建 `PaperStub`（resolve/re-resolve 输入）。

    authorship Phase 1 未落库（repo 无 author 写入面），authors 恒空——mock 的
    resolve 只依赖 doi identifier，不影响语义。`meta` 从 `paper.meta_json` 还原：
    resolve 依赖 enumerate 携带的 adapter 私有定位符（如 openreview 的 pdf 相对路径）
    重建 AssetPlan——meta 此前在重建时被丢弃，是需要 meta 的 adapter（openreview）成立
    的前提。arxiv/mock 的 resolve 不读 meta，还原它不改变其语义。
    """
    idents = ctx.db.query(
        "SELECT scheme, value FROM identifier WHERE paper_id = ? "
        "ORDER BY is_primary DESC, scheme, value",
        (str(paper["id"]),),
    )
    if not idents:
        raise CrawlerError(
            ErrorClass.CONFIG, f"paper {paper['id']!r} has no identifiers (cannot resolve)"
        )
    return PaperStub(
        title=str(paper["title"]),
        identifiers=tuple((str(r["scheme"]), str(r["value"])) for r in idents),
        year=paper["year"],
        pub_date=paper["pub_date"],
        abstract=paper["abstract"],
        meta=_meta_from_json(paper["meta_json"]),
    )


def _meta_from_json(raw: object) -> tuple[tuple[str, str], ...]:
    """`paper.meta_json`（`Repo._meta_to_json` 的产物）→ tuple-of-tuples；NULL/畸形 → 空。

    只还原字符串键值对（值经 `str()` 兜底），键序确定（sorted）——与序列化时的
    `sort_keys=True` 对齐，重建结果稳定。非 JSON-object 或解析失败静默降级为空 meta
    （resolve 侧对缺失 meta 键已按「无该资产」处理，不需响亮停机）。
    """
    if not raw:
        return ()
    try:
        parsed = json.loads(str(raw))
    except (json.JSONDecodeError, ValueError):
        return ()
    if not isinstance(parsed, dict):
        return ()
    return tuple((str(k), str(v)) for k, v in sorted(parsed.items()))


def fetched_file_ok(asset: sqlite3.Row) -> bool:
    """§5.3 幂等跳过判据：file_path 存在且内容 sha256 与 asset 行一致。

    Phase 1 资产为 KB 级 mock 文件，整读哈希即可；大文件流式化留待真实 adapter 阶段。
    """
    path_raw = asset["file_path"]
    sha_raw = asset["sha256"]
    if not path_raw or not sha_raw:
        return False
    path = Path(str(path_raw))
    if not path.is_file():
        return False
    return hashlib.sha256(path.read_bytes()).hexdigest() == str(sha_raw)


def _asset_final_path(config: Config, venue_id: str, paper: sqlite3.Row, plan: AssetPlan) -> Path:
    """fetch 落位路径（design/06 §4 文件存储布局）。

    - pdf → `data/pdf/{venue_id}/{year}/{paper_ulid}.pdf`（主全文，固定命名）。
    - si  → `data/si/{venue_id}/{year}/{paper_ulid}/{原名}`（按 paper 分子目录、
      保持原文件名；原名取 `plan.url` 的 basename，见 `_asset_url_basename`）。
    - 其余 kind（html/bibtex/source）：§4 未给出落位布局，本阶段不支持——响亮抛
      CONFIG（经 pipeline 特判转 BLOCKED；人工可读的报错优于静默落到一个未经
      设计审的路径，或放任资产永久卡在 planned/BLOCKED 却无从得知原因）。

    paper.year 为 NULL 时落 "unknown" 子目录（布局键要求 year 段存在）。
    """
    year_raw = paper["year"]
    year_part = str(int(year_raw)) if year_raw is not None else "unknown"
    paper_id = str(paper["id"])
    if plan.kind is AssetKind.PDF:
        return config.data_dir / "pdf" / venue_id / year_part / f"{paper_id}.pdf"
    if plan.kind is AssetKind.SI:
        filename = _asset_url_basename(plan.url)
        return config.data_dir / "si" / venue_id / year_part / paper_id / filename
    raise CrawlerError(
        ErrorClass.CONFIG, f"unsupported asset kind for fetch landing: {plan.kind.value!r}"
    )


def _asset_url_basename(url: str) -> str:
    """从资产 URL 取原始文件名（design/06 §4 si 资产"保持原名"的取名规则）。

    剥离 query string / fragment 后取 path 最后一段；取不到文件名（path 为空、
    或以 "/" 结尾）时兜底为 "si.bin"——避免把落位路径退化成目录本身或空文件名。
    """
    name = urlsplit(url).path.rsplit("/", 1)[-1]
    return name if name else "si.bin"


def _match_plan(plans: list[AssetPlan], asset: sqlite3.Row) -> AssetPlan:
    """在 re-resolve 结果里找回本 asset 的身份 (kind, version)；找不到视为 GONE。

    asset 幂等身份 = (paper, kind, version)（T7c 裁决：url 只是执行细节）；上游
    不再提供同身份计划说明该资产已下架。
    """
    for plan in plans:
        if plan.kind.value == str(asset["kind"]) and plan.version == asset["version"]:
            return plan
    raise CrawlerError(
        ErrorClass.GONE,
        f"re-resolve no longer offers asset kind={asset['kind']!r} version={asset['version']!r}",
    )


# ---------------------------------------------------------------------------
# 六阶段 handler（§1 表；"pull" 编排在 runner）
# ---------------------------------------------------------------------------


def _stage_discover(ctx: StageContext, task: sqlite3.Row, report: RunReport) -> StageOutcome:
    """阶段 1 discover：VenueSpec(+范围) → Issue 行（§1）。

    任务参数携带 Selector 的 issue 范围（volume/issue/year，None 键省略）：pull 的
    "按 Selector 圈定 issues" 在持久化边界生效——只 upsert 命中范围的期（集成测试
    的 counts 口径：`pull --year 2024` 后 DB 仅有该年 2 期）。无范围键（如
    `crawler timeline`）则落全量时间轴。
    """
    venue_id = _task_venue(task)
    params = _params(task)
    route = route_for(ctx, venue_id)
    # 阶段可单独执行（§1）：discover 是建立 venue 引用行的入口阶段，须自足确保
    # venue 行存在（幂等 upsert；pull 编排在其外也 upsert，二者互不冲突）。
    ctx.repo.upsert_venue(route.venue)
    domain = route.metadata_adapter.domains[0]
    acquire_and_wait(ctx, domain)

    volume = params.get("volume")
    number = params.get("issue")
    year = params.get("year")
    count = 0
    for ref in route.metadata_adapter.discover_timeline(route.venue, since=None):
        if volume is not None and ref.volume != volume:
            continue
        if number is not None and ref.number != number:
            continue
        if year is not None and ref.year != year:
            continue
        ctx.repo.upsert_issue(ref, source=route.metadata_adapter.adapter_id)
        count += 1
    log_event(
        "INFO",
        f"discover: {count} issue(s) persisted",
        task_id=str(task["id"]),
        venue=venue_id,
        stage="discover",
        domain=domain,
    )
    return "done"


def _stage_enumerate(ctx: StageContext, task: sqlite3.Row, report: RunReport) -> StageOutcome:
    """阶段 2 enumerate：一期 → Paper+Identifier 行（§1；任务粒度=一期）。

    "事务粒度=一期"按计划澄清指任务粒度：一期一个 enumerate 子任务；期内每篇的
    upsert 由 `Repo.upsert_paper` 自带事务完成（不可外层再包 tx 嵌套）。
    """
    venue_id = _task_venue(task)
    issue_id = str(_params(task)["issue"])
    rows = ctx.db.query("SELECT * FROM issue WHERE id = ?", (issue_id,))
    if not rows:
        raise CrawlerError(ErrorClass.CONFIG, f"enumerate references missing issue {issue_id!r}")
    issue = rows[0]
    route = route_for(ctx, venue_id)
    domain = route.metadata_adapter.domains[0]
    acquire_and_wait(ctx, domain)

    ref = IssueRef(
        venue_id=venue_id,
        volume=issue["volume"],
        number=issue["number"],
        year=issue["year"],
        label=issue["label"],
        pub_date=issue["pub_date"],
        paper_count_claimed=issue["paper_count_claimed"],
    )
    count = 0
    for stub in route.metadata_adapter.enumerate_issue(route.venue, ref):
        ctx.repo.upsert_paper(venue_id, issue_id, stub)
        count += 1
    log_event(
        "INFO",
        f"enumerate v{ref.volume}n{ref.number}: {count} paper(s) upserted",
        task_id=str(task["id"]),
        venue=venue_id,
        stage="enumerate",
        domain=domain,
    )
    return "done"


def _stage_resolve(ctx: StageContext, task: sqlite3.Row, report: RunReport) -> StageOutcome:
    """阶段 3 resolve：一篇 paper → planned Asset 行（§1；幂等键 (paper,kind,version)）。

    ingest_state 只前进：仅 metadata_only → resolved（force 重跑不把 fetched/
    extracted 拉回去）。
    """
    venue_id = _task_venue(task)
    paper_id = str(_params(task)["paper"])
    paper = _paper_row(ctx, paper_id)
    route = route_for(ctx, venue_id)
    adapter = route.fulltext_adapter
    domain = adapter.domains[0]
    # 缺陷 C-C：可证明零网络的 resolve（`resolve_offline=True`——纯 URL 构造、不发请求）
    # 豁免 per-domain 限速闸，大 venue（如 ICLR 2024 的 2260 篇）不再被逐篇限速空转。安全侧
    # 默认 False（getattr 兜底），真实网络 resolve 策略仍过闸——豁免只给已证明零网络的路径。
    if not getattr(adapter, "resolve_offline", False):
        acquire_and_wait(ctx, domain)

    # auth_gated venue：runner 健康门建立的 session 经 ctx.auth_sessions 注入（§8.2）；
    # 非 auth_gated / 未装配 auth 时恒 None（Phase 1-3 逐字不变）。
    session = ctx.auth_sessions.get(venue_id)
    plans = adapter.resolve_assets(route.venue, _paper_stub(ctx, paper), session=session)
    for plan in plans:
        ctx.repo.plan_asset(paper_id, plan, adapter.adapter_id)
    if str(paper["ingest_state"]) == "metadata_only":
        ctx.repo.set_paper_state(paper_id, "resolved")
    log_event(
        "INFO",
        f"resolve: {len(plans)} asset plan(s)",
        task_id=str(task["id"]),
        venue=venue_id,
        stage="resolve",
        domain=domain,
    )
    return "done"


def _stage_fetch(ctx: StageContext, task: sqlite3.Row, report: RunReport) -> StageOutcome:
    """阶段 4 fetch：单 asset 原子下载（§5.2 + T7c re-resolve 裁决）。

    顺序：幂等跳过判定 → re-resolve → refresh_asset_plan → acquire → sleeper →
    PartFileIO 写 → 校验（bytes>0 + pdf 魔数）→ 按 kind 解析落位路径（design/06 §4：
    pdf/si 有布局，其余 kind 响亮 CONFIG，见 `_asset_final_path`）→ 原子 commit →
    finalize_fetch（mark fetched + add_fetch_log 单事务，含 rate_wait_ms/elapsed_ms）。
    失败路径（含"落位路径解析失败"——如不支持的 kind）统一单独写 fetch_log
    （error_class 填充）后抛出，由 runner 路由。mock 无 HTTP 层，http_status 恒 NULL。
    """
    task_id = str(task["id"])
    asset_id = str(_params(task)["asset"])
    asset = ctx.repo.get_asset(asset_id)
    if asset is None:
        raise CrawlerError(ErrorClass.CONFIG, f"fetch references missing asset {asset_id!r}")
    # OA-fallback direct 分支（§8.1 接线点 C）：unpaywall 兜底 asset 走通用 direct 取回，
    # **不 re-resolve、不派发 route.fulltext_adapter**（auth 平台）——OA 公共库无凭证直取。
    # 提前于 route 解析，OA host（第三方域）与 auth 平台域天然隔离（限速/日配额互不占用）。
    if str(asset["source_adapter"]) == "unpaywall":
        return _fetch_oa_direct(ctx, task, asset)
    paper = _paper_row(ctx, str(asset["paper_id"]))
    venue_id = str(paper["venue_id"])

    if str(asset["state"]) == "fetched" and fetched_file_ok(asset):
        log_event(
            "INFO",
            "skipped",
            task_id=task_id,
            venue=venue_id,
            stage="fetch",
            asset_id=asset_id,
        )
        return "skipped"

    route = route_for(ctx, venue_id)
    adapter = route.fulltext_adapter
    domain = adapter.domains[0]

    # auth_gated venue：runner 健康门建立/refresh 的 session 经 ctx.auth_sessions 注入
    # （§8.2；re-resolve 与 fetch 同用一个 session）；非 auth_gated 恒 None（逐字不变）。
    session = ctx.auth_sessions.get(venue_id)
    # T7c 裁决：现场 re-resolve 取新 plan，同步 asset 行后按新 plan 执行（勿复用旧 url）。
    plans = adapter.resolve_assets(route.venue, _paper_stub(ctx, paper), session=session)
    plan = _match_plan(plans, asset)
    ctx.repo.refresh_asset_plan(asset_id, url=plan.url, auth_needed=plan.auth_needed.value)

    # browser-fetch 分支（11-browser-fetch §1.3/§3.2 案 A：**一个分支 + 一个函数**）：
    # 计划声明 RENDER_PAGE（需渲染页面才能取回）→ 走浏览器上下文通道；其余 direct/api_call
    # 计划逐字走下方既有路径（零改动）。放在 refresh 之后：asset.url 落的是 adapter 给的
    # landing/稳定引用，同批 volatile URL 只活在 `fetch_one` 的栈上（§4.4 持久化纪律）。
    if plan.url_strategy is UrlStrategy.RENDER_PAGE:
        return _fetch_via_browser(ctx, task, asset, paper, venue_id, plan)

    wait = acquire_and_wait(ctx, domain)
    rate_wait_ms = round(wait * 1000)
    io = PartFileIO(ctx.config.data_dir / "tmp", asset_id)
    started = time.monotonic()
    try:
        result = adapter.fetch_asset(plan, io, session=session)
        if not result.ok:
            raise CrawlerError(
                result.error_class or ErrorClass.TRANSIENT,
                result.detail or "adapter returned ok=False",
            )
        if result.bytes_written <= 0:
            raise CrawlerError(ErrorClass.INTEGRITY, "empty download (0 bytes)")
        if plan.expected_type == "application/pdf" and not validate_pdf_magic(io.part_path):
            raise CrawlerError(ErrorClass.INTEGRITY, "downloaded file lacks %PDF- magic")
        # 落位路径解析纳入同一 try：不支持的 kind（design/06 §4 未给出布局）与
        # 下载/校验失败共用一套失败处置（fetch_log 审计 + .part 清理），不留特例缝隙。
        final_path = _asset_final_path(ctx.config, venue_id, paper, plan)
    except Exception as exc:
        elapsed_ms = round((time.monotonic() - started) * 1000)
        io.abort()
        error_class = exc.error_class if isinstance(exc, CrawlerError) else ErrorClass.TRANSIENT
        ctx.repo.add_fetch_log(
            asset_id=asset_id,
            task_id=task_id,
            domain=domain,
            url=plan.url,
            http_status=None,
            bytes_=0,
            elapsed_ms=elapsed_ms,
            rate_wait_ms=rate_wait_ms,
            error_class=error_class.value,
        )
        raise
    elapsed_ms = round((time.monotonic() - started) * 1000)

    io.commit(final_path)
    # 收尾单事务（Phase 2 T1）：mark_asset(fetched) + add_fetch_log 原子提交，消除
    # 二者独立提交之间的 SIGKILL 缝隙（AC-1.3）。旧的两步调用路径已删除。
    ctx.repo.finalize_fetch(
        asset_id,
        file_path=str(final_path),
        bytes_=result.bytes_written,
        sha256=result.sha256,
        fetch_log_row=FetchLogRow(
            task_id=task_id,
            domain=domain,
            url=plan.url,
            http_status=None,
            bytes_=result.bytes_written,
            elapsed_ms=elapsed_ms,
            rate_wait_ms=rate_wait_ms,
            error_class=None,
        ),
    )
    log_event(
        "INFO",
        f"fetched {result.bytes_written} bytes",
        task_id=task_id,
        venue=venue_id,
        stage="fetch",
        domain=domain,
        url=plan.url,
    )
    return "done"


# OA 第三方 host 保守默认限速（=1 req/2s）；`Config.oa_fallback_rate_rpm` 可覆盖（§8.1）。
_OA_FALLBACK_DEFAULT_RPM = 30

# browser-fetch 通道的 Config 兜底（与 `Config` 字段默认逐一相同；11-browser-fetch §7.5）。
_BROWSER_DEFAULT_DAILY_CAP = 50
_BROWSER_DEFAULT_RATE_RPM = 10
_BROWSER_DEFAULT_JITTER_S = (2.0, 5.0)
# 失败态 → obslog `verdict` 词表（§7.4；四值 ok|challenge|login_redirect|no_entitlement）。
_BROWSER_VERDICTS: dict[ErrorClass, str] = {
    ErrorClass.CHALLENGE: "challenge",
    ErrorClass.AUTH_EXPIRED: "login_redirect",
    ErrorClass.NO_ENTITLEMENT: "no_entitlement",
}


def _browser_wait(ctx: StageContext, domain: str) -> float:
    """browser 通道的域级限速闸 + 抖动（§7.1 L2）；返回实际等待秒数（经 `ctx.sleeper`）。

    抖动叠加在既有 token bucket 之上——ssrn robots `crawl-delay:5` + 2–5s 抖动 ⇒ 有效
    5–10s（ssrn.md §5 逐字）。测试注入假 sleeper + `jitter_s=[0,0]` 即可零延时精确断言。
    """
    low, high = getattr(ctx.config, "browser_jitter_s", _BROWSER_DEFAULT_JITTER_S)
    jitter = random.uniform(float(low), float(high)) if high > 0 else 0.0
    wait = ctx.limiter.acquire(domain) + jitter
    if wait > 0:
        ctx.sleeper(wait)
    return wait


def _browser_budget_gate(ctx: StageContext, waits: list[float]) -> BudgetGate:
    """装配 §7 预算门：数据源全部是既有事实源（FetchLog 派生 + runner 写的冷却 JSON）。"""

    def wait(domain: str) -> float:
        elapsed = _browser_wait(ctx, domain)
        waits.append(elapsed)
        return elapsed

    return BudgetGate(
        daily_cap=int(getattr(ctx.config, "browser_daily_cap", _BROWSER_DEFAULT_DAILY_CAP)),
        count_today=ctx.repo.count_browser_fetch_today,
        cooldown_active=lambda domain: challenge_cooldown_active(ctx.config.home, domain),
        consecutive_failures=ctx.repo.count_recent_fetch_failures,
        wait=wait,
    )


def _browser_storage_state(ctx: StageContext, venue_id: str) -> bytes | None:
    """取本 venue 的 `storage_state` 明文字节（§4.3 复用链；**只在内存**，不落明文临时文件）。

    只消费 runner 健康门已建立的 session（`ctx.auth_sessions`，§8.2）——本通道**不自行管理
    provider**。无 session / 非 `playwright_state` 后端 → None = **合法路径**（gold OA 或
    未 opt-in 账号以干净上下文启动，遇挑战即 BLOCKED，符合红线）。条目缺失/密文损坏由
    `CredentialStore.read_state` 抛 `AuthRequired`（→ BLOCKED(auth) + 重登指引）。

    ⚠ **已知边界（T11 前置设计项，审查 P1 登记）**：`ctx.auth_sessions` **只被 runner 的
    auth 健康门写入，而该门对 `family != "auth_gated"` 早返回**（`runner.py` 的
    `_auth_gate_fetch`）——本通道的两个主消费方 ssrn / aea 恰是 `open_access` family，因此
    在当前实现下**恒拿不到 storage_state、恒以干净上下文启动**。方向 fail-safe（无凭证
    最多是遇挑战即 BLOCKED，绝不会误用他人凭证），但 **T11 接入前必须先裁决 open_access
    消费方的凭证注入通道**（扩健康门 family 面 / 给 `RENDER_PAGE` 计划单独的 provider 解析
    /其他），否则 ssrn 模式 B 与 aea 订阅刊接入即恒 BLOCKED。同一条登记在
    `browserfetch.py` 模块 docstring 与 `tests/manual/browser_fetch_runbook.md` 清账节。
    """
    session = ctx.auth_sessions.get(venue_id)
    if session is None or session.backend is not SessionBackend.PLAYWRIGHT_STATE:
        return None
    return CredentialStore(ctx.config.home).read_state(session.payload_ref)


def _fetch_via_browser(
    ctx: StageContext,
    task: sqlite3.Row,
    asset: sqlite3.Row,
    paper: sqlite3.Row,
    venue_id: str,
    plan: AssetPlan,
) -> StageOutcome:
    """`RENDER_PAGE` 计划的浏览器上下文取回（11-browser-fetch §1.3 接线点 + §4.5 落盘纪律）。

    三级门（§7.1 L1）全开才走：`Config.browser_fetch_enabled` + `StageContext.browser_fetch`
    （CLI `--browser`）；任一关闭 → `skipped`（detail=`browser_fetch_disabled`，**不派生失败、
    不计 failures**，§4.6 裁决）。

    落盘复用主路径三原语一件不绕过：`PartFileIO` 原子写 → `validate_pdf_magic` 魔数校验
    （失败判 `INTEGRITY(auth_leak)`，04 §4）→ `io.commit` → `finalize_fetch` 组合事务
    （成功行）；失败路径同样落一条 `add_fetch_log`（error_class 填充）——两条路径都落行，
    正是 §7.2"每次 fetch_one 调用 = 一次 fetch 尝试 = 一行 fetch_log"的兑现。

    `no_entitlement` 判定**转 `CrawlerError(NO_ENTITLEMENT)` 上抛**，接既有 runner 链
    （asset 标 no_entitlement、不计 failures、派生 OA-fallback；AC-BF.5 = AC-4.3 既有形态）。
    """
    task_id = str(task["id"])
    asset_id = str(asset["id"])
    if not (ctx.browser_fetch and getattr(ctx.config, "browser_fetch_enabled", False)):
        log_event(
            "INFO",
            "skipped (browser-fetch 通道未开启)",
            task_id=task_id,
            venue=venue_id,
            stage="fetch",
            asset_id=asset_id,
            channel="browser",
            detail="browser_fetch_disabled",
        )
        return "skipped"

    domain = host_of(plan.url)
    rpm = float(getattr(ctx.config, "browser_rate_rpm", _BROWSER_DEFAULT_RATE_RPM))
    # 桶登记幂等且单调不放宽（ratelimit 语义）：与 adapter 既有 default_rate 取更保守者。
    ctx.limiter.register(
        domain,
        RatePolicy(
            requests_per_minute=rpm,
            burst=1,  # 并发恒 1（§7.1）
            source_note="browser-fetch 保守默认 [Config.browser_rate_rpm]",
        ),
    )
    waits: list[float] = []
    gate = _browser_budget_gate(ctx, waits)
    # 预算前置判定放在记账 try 之外：配额/熔断/冷却拒绝**不是一次 fetch 尝试**（零请求），
    # 故不落 fetch_log（落了会自我抬高计数）。`fetch_one` 内部会再判一次（幂等只读，
    # 为直调本模块的消费方兜底）。
    quota_used = gate.check_or_raise(venue_id=venue_id, domain=domain)
    storage_state = _browser_storage_state(ctx, venue_id)

    io = PartFileIO(ctx.config.data_dir / "tmp", asset_id)
    io.part_path.parent.mkdir(parents=True, exist_ok=True)  # 浏览器直接写 dest，先备好目录
    started = time.monotonic()
    try:
        outcome = fetch_one(
            plan=plan,
            venue_id=venue_id,
            dest=io.part_path,
            storage_state=storage_state,
            budget=gate,
            launch=playwright_launcher(identity_header=build_user_agent(ctx.config.identity_email)),
        )
        if outcome.no_entitlement:
            raise CrawlerError(
                ErrorClass.NO_ENTITLEMENT,
                "浏览器上下文判定无订阅权限（→ OA-fallback 既有链）",
                detail="browser_no_entitlement",
            )
        if outcome.bytes_written <= 0:
            raise CrawlerError(ErrorClass.INTEGRITY, "empty browser download (0 bytes)")
        if plan.expected_type == "application/pdf" and not validate_pdf_magic(io.part_path):
            raise CrawlerError(
                ErrorClass.INTEGRITY,
                "browser download lacks %PDF- magic",
                detail="auth_leak",
            )
        final_path = _asset_final_path(ctx.config, venue_id, paper, plan)
        # 浏览器把字节直接写进 dest（非经 `write_stream`），故哈希在此现算——口径与
        # `fetched_file_ok` 的整读 sha256 一致（DB↔文件对账因此成立）。
        sha256_hex = hashlib.sha256(io.part_path.read_bytes()).hexdigest()
    except Exception as exc:
        elapsed_ms = round((time.monotonic() - started) * 1000)
        io.abort()
        error_class = exc.error_class if isinstance(exc, CrawlerError) else ErrorClass.TRANSIENT
        ctx.repo.add_fetch_log(
            asset_id=asset_id,
            task_id=task_id,
            domain=domain,
            url=plan.url,  # 失败时 volatile URL 未知/无意义，记 landing 引用（如实）
            http_status=None,
            bytes_=0,
            elapsed_ms=elapsed_ms,
            rate_wait_ms=round(sum(waits) * 1000),
            error_class=error_class.value,
        )
        _log_browser_event(
            level="WARNING",
            task_id=task_id,
            venue_id=venue_id,
            asset_id=asset_id,
            domain=domain,
            url=plan.url,
            verdict=_BROWSER_VERDICTS.get(error_class, error_class.value),
            quota_used=quota_used,
            quota_cap=gate.daily_cap,
            rate_wait_ms=round(sum(waits) * 1000),
            elapsed_ms=elapsed_ms,
            msg=f"browser-fetch 停手: {exc}",
        )
        raise
    elapsed_ms = round((time.monotonic() - started) * 1000)
    rate_wait_ms = round(sum(waits) * 1000)

    io.commit(final_path)
    ctx.repo.finalize_fetch(
        asset_id,
        file_path=str(final_path),
        bytes_=outcome.bytes_written,
        sha256=sha256_hex,
        fetch_log_row=FetchLogRow(
            task_id=task_id,
            domain=domain,
            url=outcome.url,  # 实际请求的 URL（同批场景=volatile）；repo 落库前经 redact
            http_status=None,
            bytes_=outcome.bytes_written,
            elapsed_ms=elapsed_ms,
            rate_wait_ms=rate_wait_ms,
            error_class=None,
        ),
    )
    _log_browser_event(
        level="INFO",
        task_id=task_id,
        venue_id=venue_id,
        asset_id=asset_id,
        domain=domain,
        url=outcome.url,
        verdict="ok",
        quota_used=quota_used,
        quota_cap=gate.daily_cap,
        rate_wait_ms=rate_wait_ms,
        elapsed_ms=elapsed_ms,
        msg=f"browser-fetch fetched {outcome.bytes_written} bytes",
    )
    return "done"


def _log_browser_event(
    *,
    level: str,
    task_id: str,
    venue_id: str,
    asset_id: str,
    domain: str,
    url: str,
    verdict: str,
    quota_used: int,
    quota_cap: int,
    rate_wait_ms: int,
    elapsed_ms: int,
    msg: str,
) -> None:
    """§7.4 obslog 记账：`channel="browser"` 是**新字段值**（非新字段——`log_event` 自由
    kwargs），用于把浏览器通道请求从 obslog 一键筛出，服务 AC-BF.4 的限速/配额审计。
    `url` 由 `log_event` 统一经 `redact` 脱敏（既有单一权威脱敏源）。"""
    log_event(
        level,
        msg,
        task_id=task_id,
        venue=venue_id,
        stage="fetch",
        domain=domain,
        url=url,
        asset_id=asset_id,
        channel="browser",
        verdict=verdict,
        quota_used=quota_used,
        quota_cap=quota_cap,
        rate_wait_ms=rate_wait_ms,
        elapsed_ms=elapsed_ms,
    )


def _fetch_oa_direct(ctx: StageContext, task: sqlite3.Row, asset: sqlite3.Row) -> StageOutcome:
    """OA-fallback 兜底 asset 的**通用 direct 取回**（§8.1 接线点 C）。

    **不经 route.fulltext_adapter**（auth 平台无 session 即 AuthRequired）：unpaywall 的 OA
    副本是第三方公共库 PDF 直链，用共享 `HttpClient` 无凭证流式取回。复用 fetch 主路径的三件
    强制原语——`PartFileIO` 原子写 / `validate_pdf_magic` 魔数校验 / `finalize_fetch` 组合
    事务记账（一个不绕过）。OA host 保守限速桶自动注册（`Config.oa_fallback_rate_rpm` 默认
    30 rpm；`register` 幂等取最保守），与 auth 平台域天然隔离（日配额只数 auth 平台域，§8.3）。
    """
    asset_id = str(asset["id"])
    # §5.3 幂等跳过（与 `_stage_fetch` 主路径一致）：OA 副本已 fetched 且文件校验合格 → 跳过，
    # 不因 --force/再入队真实重下（OA 分支先于主路径的 fetched 判定，故此处独立复制该检查）。
    if str(asset["state"]) == "fetched" and fetched_file_ok(asset):
        log_event("INFO", "skipped", stage="fetch", asset_id=asset_id)
        return "skipped"
    http = ctx.http
    if http is None:
        # 未注入共享 client（离线路径/未装配）→ 静默跳过，不误报失败。
        log_event(
            "INFO", "oa direct fetch skipped (no http client)", stage="fetch", asset_id=asset_id
        )
        return "skipped"
    task_id = str(task["id"])
    url = str(asset["url"])
    host = urlsplit(url).hostname or urlsplit(url).netloc or url
    paper = _paper_row(ctx, str(asset["paper_id"]))
    venue_id = str(paper["venue_id"])

    rpm = float(getattr(ctx.config, "oa_fallback_rate_rpm", _OA_FALLBACK_DEFAULT_RPM))
    ctx.limiter.register(
        host,
        RatePolicy(
            requests_per_minute=rpm,
            burst=1,
            source_note="OA-fallback direct fetch 保守默认 [Config.oa_fallback_rate_rpm]",
        ),
    )
    wait = acquire_and_wait(ctx, host)
    rate_wait_ms = round(wait * 1000)

    io = PartFileIO(ctx.config.data_dir / "tmp", asset_id)
    started = time.monotonic()
    try:
        bytes_written, sha256_hex = io.write_stream(http.stream(url))
        if bytes_written <= 0:
            raise CrawlerError(ErrorClass.INTEGRITY, "empty OA download (0 bytes)")
        if not validate_pdf_magic(io.part_path):
            raise CrawlerError(ErrorClass.INTEGRITY, "OA copy lacks %PDF- magic")
        # OA 副本恒 pdf（身份 (paper,pdf,<oa版>)）；落位复用主路径 `_asset_final_path`。
        # ★已知限制（Phase 4 债务，MINOR-2）：`_asset_final_path` 的 pdf 落位路径
        # `data/pdf/{venue}/{year}/{paper}.pdf` **不含 version**（design/06 §4 布局）——故本 OA
        # 副本（version=oa 串）与日后同 paper 的平台 pdf（version=None）**共享同一文件路径**，
        # 后取回者覆盖前者、且 asset 行 sha 与磁盘可不一致（verify 潜在冲突）。当前 OA 兜底仅在
        # 平台无权（no_entitlement，无平台 pdf 落盘）时触发，路径实际空闲、无冲突；design/06
        # 层的 version 化落位缺口记入 Phase 4 债务档（T8 报告）。
        final_path = _asset_final_path(
            ctx.config, venue_id, paper, AssetPlan(kind=AssetKind.PDF, url=url)
        )
    except Exception as exc:
        elapsed_ms = round((time.monotonic() - started) * 1000)
        io.abort()
        error_class = exc.error_class if isinstance(exc, CrawlerError) else ErrorClass.TRANSIENT
        ctx.repo.add_fetch_log(
            asset_id=asset_id,
            task_id=task_id,
            domain=host,
            url=url,
            http_status=None,
            bytes_=0,
            elapsed_ms=elapsed_ms,
            rate_wait_ms=rate_wait_ms,
            error_class=error_class.value,
        )
        raise
    elapsed_ms = round((time.monotonic() - started) * 1000)

    io.commit(final_path)
    ctx.repo.finalize_fetch(
        asset_id,
        file_path=str(final_path),
        bytes_=bytes_written,
        sha256=sha256_hex,
        fetch_log_row=FetchLogRow(
            task_id=task_id,
            domain=host,
            url=url,
            http_status=None,
            bytes_=bytes_written,
            elapsed_ms=elapsed_ms,
            rate_wait_ms=rate_wait_ms,
            error_class=None,
        ),
    )
    log_event(
        "INFO",
        f"oa direct fetched {bytes_written} bytes",
        task_id=task_id,
        venue=venue_id,
        stage="fetch",
        domain=host,
        url=url,
    )
    return "done"


def _stage_oa_fallback(ctx: StageContext, task: sqlite3.Row, report: RunReport) -> StageOutcome:
    """第七 handler oa_fallback：no_entitlement 的 unpaywall OA 兜底（§8.1 接线点 B）。

    UnpaywallRecord→AssetPlan 规格化经 unpaywall adapter 自身的 `resolve_assets`（复用其
    select_pdf_location + 精确版本串 + landing-only 观测的既有逻辑；A-M4：绝不直传 lookup()
    的 record 当 AssetPlan）。产 OA pdf 直链 → `plan_asset(source_adapter='unpaywall')`（独立
    身份 (paper,pdf,<oa版>)，与原平台 asset (paper,pdf,None) 并存不覆盖）→ enqueue 一个 fetch
    子任务（→ 接线点 C `_fetch_oa_direct`）。无 unpaywall 装配 / DOI 未收录 / 无 PDF 直链 →
    done（landing-only 不下载，AC-4.3"若存在"）。
    """
    params = _params(task)
    doi = str(params["doi"])
    paper_id = str(params["paper"])
    task_id = str(task["id"])
    ua = ctx.unpaywall_adapter
    if ua is None:
        log_event(
            "INFO",
            "oa_fallback skipped (no unpaywall adapter)",
            task_id=task_id,
            stage="oa_fallback",
        )
        return "skipped"

    venue_id = _task_venue(task)
    venue = ctx.registry.get(venue_id)
    paper = _paper_row(ctx, paper_id)
    stub = _paper_stub(ctx, paper)

    # unpaywall API 域独立桶（api.unpaywall.org，5 req/s）——与 auth 平台域/OA host 皆隔离。
    ctx.limiter.register(ua.domains[0], ua.default_rate)
    acquire_and_wait(ctx, ua.domains[0])
    plans = ua.resolve_assets(venue, stub)  # 规格化 AssetPlan 列表（DOI 未收录/无直链 → 空）
    oa_plan = next(
        (p for p in plans if p.kind is AssetKind.PDF and p.url_strategy is UrlStrategy.DIRECT),
        None,
    )
    if oa_plan is None:
        log_event(
            "INFO",
            "oa_fallback: no OA pdf direct link (landing-only or not indexed)",
            task_id=task_id,
            venue=venue_id,
            stage="oa_fallback",
            doi=doi,
        )
        return "done"

    new_asset_id = ctx.repo.plan_asset(paper_id, oa_plan, "unpaywall")
    parent_id = str(task["parent_id"]) if task["parent_id"] is not None else None
    ctx.queue.enqueue("fetch", venue_id, {"asset": new_asset_id}, parent_id=parent_id)
    log_event(
        "INFO",
        f"oa_fallback: OA asset planned + fetch enqueued (version={oa_plan.version})",
        task_id=task_id,
        venue=venue_id,
        stage="oa_fallback",
        doi=doi,
    )
    return "done"


def _stage_extract(ctx: StageContext, task: sqlite3.Row, report: RunReport) -> StageOutcome:
    """阶段 5 extract（Phase 1 noop 语义）：fetched pdf → fulltext 行 + ingest_state。

    幂等键 (asset, extractor_ver)：fulltext 表 paper 1-1，同 paper 已有行则不重插
    （Phase 1 extractor_ver 恒 "1"）。本地零网络，不走限速。
    """
    asset_id = str(_params(task)["asset"])
    asset = ctx.repo.get_asset(asset_id)
    if asset is None:
        raise CrawlerError(ErrorClass.CONFIG, f"extract references missing asset {asset_id!r}")
    if str(asset["state"]) != "fetched":
        raise CrawlerError(
            ErrorClass.CONFIG, f"extract requires a fetched asset, got {asset['state']!r}"
        )
    paper_id = str(asset["paper_id"])
    existing = ctx.db.query("SELECT paper_id FROM fulltext WHERE paper_id = ?", (paper_id,))
    if not existing:
        ctx.db.execute(
            "INSERT INTO fulltext "
            "(paper_id, extractor, extractor_ver, text_path, char_count, lang, extracted_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (paper_id, "noop", "1", None, 0, None, utcnow_iso()),
        )
    ctx.repo.set_paper_state(paper_id, "extracted")
    log_event(
        "INFO",
        "extract: fulltext row ensured (noop v1)",
        task_id=str(task["id"]),
        venue=_task_venue(task),
        stage="extract",
    )
    return "done"


def _stage_ingest(ctx: StageContext, task: sqlite3.Row, report: RunReport) -> StageOutcome:
    """阶段 6 ingest（Phase 1 语义）：推进 ingest_state + 报告 notes 摘要（§1）。

    - 有 fetched 资产的 paper：metadata_only/resolved → fetched（只前进，不把
      extracted 拉回）；
    - identifier 锚点强合并（design/06 §3）已由 enumerate 期的 `Repo.upsert_paper`
      天然处理，此处无需重放；
    - 摘要（含 counts 对账口径）进 RunReport.notes，供人读报告。本地零网络。
    """
    venue_id = _task_venue(task)
    rows = ctx.db.query(
        "SELECT DISTINCT p.id FROM paper p JOIN asset a ON a.paper_id = p.id "
        "WHERE p.venue_id = ? AND a.state = 'fetched' "
        "AND p.ingest_state IN ('metadata_only', 'resolved')",
        (venue_id,),
    )
    for row in rows:
        ctx.repo.set_paper_state(str(row["id"]), "fetched")
    counts = ctx.repo.counts(venue_id)
    note = (
        f"ingest[{venue_id}]: {len(rows)} paper(s) -> fetched; "
        f"issues={counts['issues']} papers={counts['papers']} "
        f"assets_fetched={counts['assets_fetched']}/{counts['assets_planned']}"
    )
    report.notes.append(note)
    log_event("INFO", note, task_id=str(task["id"]), venue=venue_id, stage="ingest")
    return "done"


_STAGE_HANDLERS: dict[str, Callable[[StageContext, sqlite3.Row, RunReport], StageOutcome]] = {
    "discover": _stage_discover,
    "enumerate": _stage_enumerate,
    "resolve": _stage_resolve,
    "fetch": _stage_fetch,
    "oa_fallback": _stage_oa_fallback,  # 第七 handler（§8.1；默认关闭，仅 oa_fallback 派生）
    "extract": _stage_extract,
    "ingest": _stage_ingest,
}


def execute_stage(ctx: StageContext, task: sqlite3.Row, report: RunReport) -> StageOutcome:
    """执行一个已领取（RUNNING）的六阶段任务；`pull` 由 runner 编排，不在此表。"""
    kind = str(task["kind"])
    handler = _STAGE_HANDLERS.get(kind)
    if handler is None:
        raise CrawlerError(ErrorClass.CONFIG, f"no stage handler for task kind {kind!r}")
    return handler(ctx, task, report)


__all__ = [
    "Selector",
    "StageContext",
    "StageOutcome",
    "acquire_and_wait",
    "execute_stage",
    "fetched_file_ok",
    "route_for",
]
