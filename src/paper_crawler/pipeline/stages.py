"""六阶段 stage 执行器 + `Selector`/`StageContext`（接口冻结件 §2.7；design/05 §1）。

职责边界：本模块执行"一个已领取任务"的业务动作（discover/enumerate/resolve/
fetch/extract/ingest 六类；`pull` 的级联编排在 `runner.py`）。任务状态机操作
（complete/fail/block）与错误分类路由都不在这里——handler 只做事，失败一律抛
`CrawlerError`，由 runner 按 design/05 §4 统一路由。

关键语义（段号指 design/05）：
- 阶段间只通过持久化实体通信（§1 不变式）：handler 的输入全部从任务参数 + DB 行
  重建（`{"issue": <ulid>}` / `{"paper": <ulid>}` / `{"asset": <ulid>}`），不依赖
  进程内的上游对象——kill-9 后重跑（AC-1.3）与 resume（AC-1.5）都靠这一点成立。
- 限速接入：每次 adapter 网络型调用（discover/enumerate/resolve/fetch）前
  `limiter.acquire(domain)` → `sleeper(wait)`；discover/enumerate 记账在
  metadata_adapter.domains[0]，resolve/fetch 在 fulltext_adapter.domains[0]
  （与 `Route.rate_overrides` 的键一致）。fetch 的 wait 记入 FetchLog.rate_wait_ms。
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
import sqlite3
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

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
from paper_crawler.types import AssetKind, AssetPlan, IssueRef, PaperStub, utcnow_iso

# ---------------------------------------------------------------------------
# 接口冻结件 §2.7：Selector / StageContext
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Selector:
    """pull/list 的圈定条件（接口冻结件 §2.7）。

    - `volume`/`issue`/`year` 圈定 issues（`issue` 对应 IssueRef.number）；
    - `dois` 圈定 papers（按 identifier，DOI 比较大小写不敏感）；
    - `filter_expr` = 标题大小写不敏感子串（FR-05 关键词过滤；DSL 属 Phase 6）；
    - `limit` = fetch 的 asset 数上限（resolve 全量完成后截断候选列表）。
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
    resolve 只依赖 doi identifier，不影响语义。
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
    )


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


def _asset_final_path(config: Config, venue_id: str, paper: sqlite3.Row, kind: str) -> Path:
    """fetch 落位路径（design/06 §4）：data/pdf/{venue_id}/{year}/{paper_ulid}.pdf。

    Phase 1 只有 pdf 资产会走到 fetch（mock resolve 只产 pdf 计划）；paper.year
    为 NULL 时落 "unknown" 子目录（布局键要求 year 段存在）。
    """
    if kind != AssetKind.PDF.value:
        raise CrawlerError(ErrorClass.CONFIG, f"Phase 1 only lands pdf assets, got kind={kind!r}")
    year_raw = paper["year"]
    year_part = str(int(year_raw)) if year_raw is not None else "unknown"
    return config.data_dir / "pdf" / venue_id / year_part / f"{paper['id']}.pdf"


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
    acquire_and_wait(ctx, domain)

    plans = adapter.resolve_assets(route.venue, _paper_stub(ctx, paper), session=None)
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
    PartFileIO 写 → 校验（bytes>0 + pdf 魔数）→ 原子 commit 到
    data/pdf/{venue_id}/{year}/{paper_ulid}.pdf → finalize_fetch（mark fetched +
    add_fetch_log 单事务，含 rate_wait_ms/elapsed_ms）。失败路径单独写 fetch_log
    （error_class 填充）后抛出，由 runner 路由。mock 无 HTTP 层，http_status 恒 NULL。
    """
    task_id = str(task["id"])
    asset_id = str(_params(task)["asset"])
    asset = ctx.repo.get_asset(asset_id)
    if asset is None:
        raise CrawlerError(ErrorClass.CONFIG, f"fetch references missing asset {asset_id!r}")
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

    # T7c 裁决：现场 re-resolve 取新 plan，同步 asset 行后按新 plan 执行（勿复用旧 url）。
    plans = adapter.resolve_assets(route.venue, _paper_stub(ctx, paper), session=None)
    plan = _match_plan(plans, asset)
    ctx.repo.refresh_asset_plan(asset_id, url=plan.url, auth_needed=plan.auth_needed.value)

    wait = acquire_and_wait(ctx, domain)
    rate_wait_ms = round(wait * 1000)
    io = PartFileIO(ctx.config.data_dir / "tmp", asset_id)
    started = time.monotonic()
    try:
        result = adapter.fetch_asset(plan, io, session=None)
        if not result.ok:
            raise CrawlerError(
                result.error_class or ErrorClass.TRANSIENT,
                result.detail or "adapter returned ok=False",
            )
        if result.bytes_written <= 0:
            raise CrawlerError(ErrorClass.INTEGRITY, "empty download (0 bytes)")
        if plan.expected_type == "application/pdf" and not validate_pdf_magic(io.part_path):
            raise CrawlerError(ErrorClass.INTEGRITY, "downloaded file lacks %PDF- magic")
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

    final_path = _asset_final_path(ctx.config, venue_id, paper, str(asset["kind"]))
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
