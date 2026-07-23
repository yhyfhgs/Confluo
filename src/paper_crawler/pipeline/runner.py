"""`PipelineRunner`：pull 级联编排、串行 drain 与错误分类路由（接口冻结件 §2.7）。

执行模型（design/05 §3；Phase 1 纯串行，接口可演进）：所有工作单元都是 task 行，
"enqueue 后同步 drain"——`claim_next` 循环逐个领取并执行，直到无 PENDING。pull 父
任务（kind=pull）也经队列领取执行，其 handler `_run_pull` 逐阶段
"enqueue 子任务（parent_id=pull）→ 嵌套 drain"，阶段边界一律从持久化实体（DB）
重新选定下一阶段输入——这既是 §1 的不变式，也是断点续爬（§5）的成立前提：残留
PENDING 任务参数自包含（issue/paper/asset ULID），任何时刻重跑都能自行完成。

错误分类路由（design/05 §4；本模块唯一出口）：
- AUTH_EXPIRED → `queue.block`（reason 含人工动作提示），且同 venue 同批剩余
  fetch 子任务连带 BLOCKED（"整批 BLOCKED(auth)"——经 drain 循环领取后立即
  block，PENDING→RUNNING→BLOCKED 全为合法转移，attempts 不动）；
- CHALLENGE / CONFIG → `queue.block`；
- TRANSIENT / RATE_LIMITED / INTEGRITY → `queue.fail`（回 PENDING 时按
  RETRY_TABLE backoff × config.retry_scale 经 sleeper 退避后继续 drain；
  RATE_LIMITED 不计 attempts，为防恒定注入导致无限循环，同一任务在一次运行内
  连续 rate_limited 超过 3 次后升级按 TRANSIENT 处置——Phase 1 循环保护，
  design/05 §4 的 "连续 3 次 → domain 冷却 1h" 属后续阶段）；
- GONE → asset 标 gone、任务 complete（预期内跳过，不重试）；
- NO_ENTITLEMENT → **独立终态**（auth-framework §8.5）：asset 标 no_entitlement、任务
  complete（**不计 failed**，`report.no_entitlement` 单列计数）；`StageContext.oa_fallback`
  开启且 paper 有 doi 时派生 unpaywall OA 兜底任务（§8.1）；
- PARSE → fail 至 FAILED（RetrySpec(1) 不重试）；
- 非 CrawlerError 异常 → 按 TRANSIENT 处置并 log_event ERROR。

Phase 4 auth 前置门（§8.2/8.3/8.4/8.6；默认关闭——未装配 `auth_manager` 时全旁路，Phase
1-3 逐字不变）：auth_gated venue 的 fetch 前经 `_auth_gate_fetch` 施加健康门（每 N 篇/老化
15min 主动 health_check，EXPIRED→refresh 失败即整批 BLOCKED(auth)，防 401 轰炸）、日配额
（当日 fetch 尝试篇次达 cap → BLOCKED(config)）、challenge 冷却（24h，跨运行持久化）、工作
时段窗（窗外延迟不失败）。OA-fallback direct asset（source_adapter=unpaywall）旁路一切 auth
门。假时钟经 `__init__(clock=)` 注入（健康门老化/工作时段窗/冷却判定，B-M1 可测性）。

RunReport 计数口径：`succeeded` = 实际完成下载的 fetch 任务数（AC-1.1/AC-1.2 的
"成功=N"面向用户口径；discover/enumerate/resolve/extract/ingest 的完成经日志与
notes 汇总，不计入 succeeded）；`failed`/`blocked` 为全阶段任务口径；`skipped` =
入队新鲜度跳过（fresh_skip）+ handler 幂等跳过 + GONE 预期内跳过。
`planned_downloads`/`planned_bytes` 仅 dry-run 路径填充（T7b 渲染以 planned>0
判定 dry-run 行——契约）。

runner 启动（`__init__`）：`config.ensure_dirs()` + `cleanup_tmp(data/tmp)`
（§5.2 崩溃残留清理）+ `queue.recover_running()`（遗留 RUNNING 归还 PENDING 的
崩溃恢复——语义见 `TaskQueue.recover_running` docstring；2026-07-21 T7c 仲裁
将其定为冻结件 §2.5 的公开 API）。
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from paper_crawler.errors import RETRY_TABLE, CrawlerError, ErrorClass, RetrySpec
from paper_crawler.obslog import log_event
from paper_crawler.pipeline.fetchio import cleanup_tmp
from paper_crawler.pipeline.report import RunReport
from paper_crawler.pipeline.stages import (
    Selector,
    StageContext,
    StageOutcome,
    execute_stage,
    fetched_file_ok,
)
from paper_crawler.tasks import EnqueueResult, TaskKind
from paper_crawler.types import HealthStatus, SessionHandle, utcnow_iso

# AUTH_EXPIRED 连带 block 之外的两类"直接 BLOCKED"（design/05 §4）。
_BLOCK_CLASSES = frozenset({ErrorClass.CHALLENGE, ErrorClass.CONFIG})
# 一次运行内同一任务连续 rate_limited 的升级阈值（Phase 1 循环保护）。
_RATE_LIMITED_ESCALATION = 3

# ---- Phase 4 auth 接缝默认值（auth-framework §8；Config 缺该键时的保守兜底）----
_DEFAULT_AUTH_WORK_HOURS = "8-23"  # §8.6 本地工作时段窗
_DEFAULT_AUTH_DAILY_CAP = 200  # §8.3 日配额（fetch 尝试篇次）
_DEFAULT_AUTH_HEALTH_INTERVAL = 20  # §8.2 每 N 篇强制 healthcheck
_DEFAULT_AUTH_HEALTH_MAX_AGE_S = 900.0  # §8.2 健康门老化（15 min）
_CHALLENGE_COOLDOWN = timedelta(hours=24)  # §8.4 平台冷却


@dataclass
class _BatchGate:
    """auth_gated venue 的批内健康门运行态（§8.2；每次 `_new_report` 重置）。

    `provider` 是 duck-typed AuthProvider（health_check/refresh）；`session` 由 runner
    独占维护（refresh 后就地替换），经 `StageContext.auth_sessions` 注入 fetch 阶段。
    """

    provider: Any
    session: SessionHandle
    last_check_at: datetime
    fetched_since_check: int = 0


def _work_hours_ok(window: str, now: datetime) -> bool:
    """本地时间是否落在工作时段窗内（§8.6）。

    `window` 形如 `"8-23"`（起始含、结束不含的本地小时区间）。`""`/无 `-`/`"0-24"` 或
    解析失败 → 恒 True（窗关闭/放行/fail-open——不因配置笔误把 auth_gated 批全拦）。now
    为 tz-aware 时转本地时区取小时；naive 时按其字面小时（测试注入 naive 假时钟即取该值）。
    """
    if not window:
        return True
    start_s, sep, end_s = window.partition("-")
    if not sep:
        return True
    try:
        start = int(start_s.strip())
        end = int(end_s.strip())
    except ValueError:
        return True
    if start <= 0 and end >= 24:
        return True
    hour = now.astimezone().hour if now.tzinfo is not None else now.hour
    return start <= hour < end


def _pull_params(sel: Selector, *, with_extract: bool, force: bool) -> dict[str, object]:
    """pull 任务的 params（幂等键成分；dry_run 是执行模式、不进身份）。"""
    return {
        "volume": sel.volume,
        "issue": sel.issue,
        "year": sel.year,
        "dois": sorted(sel.dois),
        "filter": sel.filter_expr,
        "limit": sel.limit,
        "with_extract": with_extract,
        "force": force,
    }


def _selector_from_params(params: dict[str, Any]) -> Selector:
    dois_raw = params.get("dois") or []
    return Selector(
        volume=params.get("volume"),
        issue=params.get("issue"),
        year=params.get("year"),
        dois=tuple(str(d) for d in dois_raw),
        filter_expr=params.get("filter"),
        limit=params.get("limit"),
    )


def _watch_target_months(today: date) -> list[tuple[int, int]]:
    """watch 的目标虚拟月桶列表（oldest-first），依 arxiv.md §3 watch 裁决：

    - 当月桶恒在列；
    - **跨月边界**：当日为月初（≤3 号）时追加上一月桶——announce 延迟可使上月末
      提交的记录延至本月初才出现在 OAI，含上月桶保证不漏（4 号起仅当月，边界已过）。

    纯函数（无 DB/网络），供 `PipelineRunner.watch` 与边界单测共用。年初（1 月 ≤3 号）
    上一月为上一年 12 月（跨年回绕）。
    """
    months: list[tuple[int, int]] = []
    if today.day <= 3:
        if today.month == 1:
            months.append((today.year - 1, 12))
        else:
            months.append((today.year, today.month - 1))
    months.append((today.year, today.month))
    return months


def _issue_scope_params(sel: Selector) -> dict[str, object]:
    """discover 子任务参数 = Selector 的 issue 范围；None 键省略（无范围键 ⇒ 全量
    时间轴，与 `run_single_stage("discover", ..., {})` 的幂等键互通）。"""
    scope: dict[str, object] = {}
    if sel.volume is not None:
        scope["volume"] = sel.volume
    if sel.issue is not None:
        scope["issue"] = sel.issue
    if sel.year is not None:
        scope["year"] = sel.year
    return scope


class PipelineRunner:
    """六阶段 pipeline 的串行执行器（接口冻结件 §2.7）。"""

    def __init__(
        self,
        ctx: StageContext,
        *,
        clock: Callable[[], datetime] | None = None,
        auth_manager: Any | None = None,
    ) -> None:
        self.ctx = ctx
        ctx.config.ensure_dirs()
        removed = cleanup_tmp(ctx.config.data_dir / "tmp")
        if removed:
            log_event("WARNING", f"startup: removed {removed} stale *.part file(s)")
        recovered = ctx.queue.recover_running()  # 崩溃恢复（TaskQueue 公开 API，§2.5 扩充）
        if recovered:
            log_event(
                "WARNING",
                f"startup: recovered {recovered} RUNNING task(s) to PENDING (crash leftovers)",
            )
        # 假时钟缝（B-M1，可测性硬要求）：健康门 15min 老化 / 工作时段窗 / challenge 冷却均经
        # 该注入时钟判定（先例 TaskQueue.__init__(clock=)）；默认 UTC now，有默认值→零回归。
        self._clock: Callable[[], datetime] = clock or (lambda: datetime.now(UTC))
        # auth_gated 平台的 provider 注册表 + session 解析入口（§8.2）；None = 未装配（Phase
        # 1-3 / 非 auth pull）→ 健康门/日配额/工作时段窗/冷却全部旁路，行为逐字不变。
        self._auth_manager = auth_manager
        # 单 venue 一旦 auth_expired，本次运行内其余 fetch 连带 block（整批 BLOCKED(auth)）。
        self._auth_blocked_venues: set[str] = set()
        # 一次运行内每任务的连续 rate_limited 计数（升级保护）。
        self._rate_limited_seen: dict[str, int] = {}
        # auth_gated 批内健康门计数器（venue→gate）+ 工作时段窗延迟集（venue）；每次运行重置。
        self._auth_batch: dict[str, _BatchGate] = {}
        self._work_hours_blocked: set[str] = set()
        # challenge 平台冷却（platform→until）：跨运行持久化在 config-home JSON（进程重启不丢，
        # §8.4），运行态字典加速。不在 `_new_report` 重置（冷却跨运行有效）。
        self._challenge_cooldown: dict[str, datetime] = {}

    # -- 公开入口（§2.7 冻结签名）-------------------------------------------

    def pull(
        self,
        venue_id: str,
        sel: Selector,
        *,
        with_extract: bool = False,
        force: bool = False,
    ) -> RunReport:
        """一次 pull 级联（1→4，`with_extract` 加 5，6 尾部必跑；dry-run 止于 3）。

        未知 venue 直接抛 `CrawlerError(CONFIG)`（不产生任何任务；CLI 以退出码 2
        呈现）。返回前报告落盘 reports_dir。
        """
        self.ctx.registry.get(venue_id)  # fail fast：未知 id → CrawlerError(CONFIG)
        report = self._new_report("pull", venue_id)
        result = self.ctx.queue.enqueue(
            "pull", venue_id, _pull_params(sel, with_extract=with_extract, force=force), force=force
        )
        log_event(
            "INFO",
            f"pull enqueued ({result.status})",
            task_id=result.task_id,
            venue=venue_id,
            stage="pull",
        )
        self._drain_loop(report)
        return self._finalize(report)

    def run_single_stage(
        self, kind: TaskKind, venue_id: str, params: dict[str, object]
    ) -> RunReport:
        """单阶段执行（design/05 §1"阶段可单独执行"）：enqueue 一个任务并 drain。"""
        report = self._new_report(f"run {kind}", venue_id)
        result = self.ctx.queue.enqueue(kind, venue_id, params)
        self._note_enqueue(result, kind, venue_id, report)
        self._drain_loop(report)
        return self._finalize(report)

    def drain(self) -> RunReport:
        """把队列里现存的 PENDING 全部执行完（claim_next 循环直到空）。"""
        report = self._new_report("drain", None)
        self._drain_loop(report)
        return self._finalize(report)

    def watch(self, venue_id: str, *, today: date | None = None) -> RunReport:
        """preprint venue 的当月桶元数据增量收割（arxiv.md §3 watch 裁决；零接口变更）。

        编排复用 pull 的 enqueue→drain 机制，不 fetch（watch 是元数据增量；`--fetch`
        选项留 Phase 6）：

        1. **discover（force=True）**：确保目标虚拟月桶行存在。跨月边界时上一月桶可能
           未在上次运行内建立（上次 discover 落在上月、24h 新鲜度内会 fresh_skip 而不
           补建本月桶），force 绕过新鲜度保证桶存在——arxiv discover 零网络，force 廉价。
        2. **enumerate 目标月桶（force=True）**：绕过 enumerate 的 7d 新鲜度 TTL 强制
           re-enumerate 整窗（watch 强制刷新语义）。去重由 `identifier(scheme='arxiv')`
           主键天然保证——重叠窗口/同日二跑零重复入库（幂等）。

        目标月由 `today`（缺省真实 UTC 今日）经 `_watch_target_months` 定：当月，且月初
        （≤3 号）含上一月桶。报告 notes 记本次净新增 paper 数（`repo.counts` 前后差）。
        未知 venue fail-fast 抛 `CrawlerError(CONFIG)`（CLI 以退出码 2 呈现）；venue 是否
        为 `preprint_channel` 由 CLI 层校验（用法约束，非 pipeline 语义）。
        """
        self.ctx.registry.get(venue_id)  # fail fast：未知 id → CrawlerError(CONFIG)
        day = today if today is not None else datetime.now(UTC).date()
        report = self._new_report("watch", venue_id)

        # 阶段 1 discover（force：保证当月/上月桶存在，绕过 24h 新鲜度）
        self._enqueue_child(report, "discover", venue_id, {}, None, force=True)
        self._drain_loop(report)

        papers_before = self.ctx.repo.counts(venue_id)["papers"]

        # 阶段 2 enumerate 目标月桶（force：绕过 7d 新鲜度，强制整窗重收）
        bucket_count = 0
        for year, month in _watch_target_months(day):
            for issue in self.ctx.repo.list_issues(venue_id, number=f"{month:02d}", year=year):
                self._enqueue_child(
                    report, "enumerate", venue_id, {"issue": str(issue["id"])}, None, force=True
                )
                bucket_count += 1
        self._drain_loop(report)

        new_papers = self.ctx.repo.counts(venue_id)["papers"] - papers_before
        report.notes.append(
            f"watch[{venue_id}]: +{new_papers} new paper(s) over {bucket_count} bucket(s)"
        )
        return self._finalize(report)

    def grab(self, venue_id: str, paper_id: str, *, force: bool = False) -> RunReport:
        """单篇全链取回（resolve → fetch，含 no_entitlement→OA 兜底）——`grab` 命令的编排。

        paper 已由 CLI 侧确定（库内 DOI 反查 或 crossref 单篇 lookup→`MergeEngine.ingest`
        新建并绑定 `venue_id`）。此处复用 pull 的 resolve/fetch 子任务机制与错误路由——auth
        健康门（§8.2）/日配额（§8.3）/工作时段窗（§8.6）/OA 兜底（§8.1）全生效。未知 venue
        fail-fast 抛 `CrawlerError(CONFIG)`（CLI 以退出码 2 呈现，不产生任何任务）。
        """
        spec = self.ctx.registry.get(venue_id)  # fail fast：未知 id → CrawlerError(CONFIG)
        self.ctx.repo.upsert_venue(spec)  # 确保 venue 行存在（FK + 路由；同 _run_pull）
        report = self._new_report("grab", venue_id)

        # 阶段 3 resolve（单篇）——planned asset 落库
        self._enqueue_child(report, "resolve", venue_id, {"paper": paper_id}, None, force)
        self._drain_loop(report)

        # 阶段 4 fetch（该 paper 的候选 asset；no_entitlement→OA 兜底任务在同一 drain 内派生消费）
        paper_rows = self.ctx.db.query("SELECT * FROM paper WHERE id = ?", (paper_id,))
        for asset in self._candidate_assets(list(paper_rows), None):
            self._enqueue_child(report, "fetch", venue_id, {"asset": str(asset["id"])}, None, force)
        self._drain_loop(report)
        return self._finalize(report)

    # -- 报告 ---------------------------------------------------------------

    def _new_report(self, command: str, venue_id: str | None) -> RunReport:
        self._auth_blocked_venues = set()
        self._rate_limited_seen = {}
        # auth 健康门批态与工作时段延迟集每次运行独立（§8.2/8.6）；challenge 冷却跨运行不重置。
        self._auth_batch = {}
        self._work_hours_blocked = set()
        self.ctx.auth_sessions.clear()
        return RunReport(command=command, venue_id=venue_id, started_at=utcnow_iso())

    def _finalize(self, report: RunReport) -> RunReport:
        report.finished_at = utcnow_iso()
        report.save(self.ctx.config.reports_dir)
        log_event(
            "INFO",
            f"{report.command}: 成功 {report.succeeded} 失败 {report.failed} "
            f"阻塞 {report.blocked} 跳过 {report.skipped} 无订阅 {report.no_entitlement}",
            venue=report.venue_id,
        )
        return report

    # -- drain 循环与任务执行 ------------------------------------------------

    def _drain_loop(self, report: RunReport) -> None:
        while True:
            row = self.ctx.queue.claim_next()
            if row is None:
                return
            self._execute_claimed(row, report)

    def _execute_claimed(self, row: sqlite3.Row, report: RunReport) -> None:
        task_id = str(row["id"])
        kind = str(row["kind"])
        venue = str(row["venue_id"]) if row["venue_id"] is not None else None

        # fetch 前置门（§8.2/8.3/8.4/8.6）：OA-fallback direct asset（source_adapter=unpaywall）
        # **旁路一切 auth 门**——第三方 OA 域，不占 auth 平台 session/配额，也不受整批连带块。
        # 其余 fetch 过 `_auth_gate_fetch`（含既有整批 BLOCKED(auth) 连带；非 auth venue 早放行）。
        gated_fetch = False
        if kind == "fetch":
            asset = self._fetch_asset_of(row)
            is_oa = asset is not None and str(asset["source_adapter"]) == "unpaywall"
            if not is_oa:
                if not self._auth_gate_fetch(row, venue, report):
                    return  # 门内已处置（连带 / 冷却 / 配额 / 工作时段 / 健康门 EXPIRED/CHALLENGE）
                gated_fetch = venue is not None and venue in self._auth_batch

        try:
            if kind == "pull":
                self._run_pull(row, report)
                outcome: StageOutcome = "done"
            else:
                outcome = execute_stage(self.ctx, row, report)
        except CrawlerError as exc:
            self._route_error(row, exc.error_class, str(exc), report)
            return
        except Exception as exc:  # design/05 §4：非 CrawlerError → TRANSIENT 处置
            msg = f"unexpected {type(exc).__name__}: {exc}"
            log_event(
                "ERROR",
                msg,
                task_id=task_id,
                venue=venue,
                stage=kind,
                error_class=ErrorClass.TRANSIENT.value,
            )
            self._route_error(row, ErrorClass.TRANSIENT, msg, report)
            return

        self.ctx.queue.complete(task_id)
        if outcome == "skipped":
            report.skipped += 1
        elif kind == "fetch":
            report.succeeded += 1  # succeeded 口径 = 完成下载的 fetch（模块 docstring）
            if gated_fetch and venue is not None:
                gate = self._auth_batch.get(venue)
                if gate is not None:
                    gate.fetched_since_check += 1  # 健康门篇次计数（§8.2）

    # -- auth 前置门（§8.2/8.3/8.4/8.6；未装配 AuthManager 时全旁路）--------------

    def _fetch_asset_of(self, row: sqlite3.Row) -> sqlite3.Row | None:
        """取 fetch 任务引用的 asset 行（供 OA-source 甄别）；无 asset 参数/不存在 → None。"""
        asset_id = _params_of(row).get("asset")
        return self.ctx.repo.get_asset(str(asset_id)) if asset_id is not None else None

    def _auth_gate_fetch(self, row: sqlite3.Row, venue: str | None, report: RunReport) -> bool:
        """auth_gated fetch 前置门。返回 True=放行；False=已处置（BLOCKED，调用方直接 return）。

        顺序：整批 BLOCKED(auth) 连带 → 工作时段窗延迟集 → [非 auth_gated / 未装配 → 放行] →
        challenge 冷却 → 批入口（工作时段窗一次性检查 + provider/session 建立）→ 日配额 →
        周期性健康门（N 篇 / 老化）→ 注入 session。健康门 EXPIRED→refresh 失败即整批 BLOCKED
        (auth)（首个 auth_expired 连带，无 401 轰炸，AC-4.2）。
        """
        task_id = str(row["id"])
        # 整批 BLOCKED(auth) 连带（既有机制；auth_expired 首发后同 venue 剩余 fetch 连带）。
        if venue is not None and venue in self._auth_blocked_venues:
            self.ctx.queue.block(
                task_id,
                f"auth_expired（同批连带）: venue {venue} 凭证已失效；"
                "修复后运行 `crawler resume --all` 恢复",
            )
            report.blocked += 1
            log_event(
                "WARNING",
                "blocked (auth batch)",
                task_id=task_id,
                venue=venue,
                stage="fetch",
                error_class=ErrorClass.AUTH_EXPIRED.value,
            )
            return False
        # 工作时段窗延迟集（批入口窗外后同 venue 剩余 fetch 连带延迟；§8.6）。
        if venue is not None and venue in self._work_hours_blocked:
            self._block_work_hours(task_id, venue, report)
            return False

        if venue is None or self._auth_manager is None:
            return True  # 非 auth 场景（Phase 1-3 / 未装配 AuthManager）：早放行
        try:
            route = self.ctx.registry.route(venue)
        except CrawlerError:
            return True  # 未知/畸形 venue：交由 stage 自身的 CONFIG 路由处理
        adapter = route.fulltext_adapter
        if getattr(adapter, "family", None) != "auth_gated":
            return True  # open_access / aggregator venue 不受 auth 门约束
        platform = adapter.adapter_id

        # challenge 平台冷却（§8.4）：冷却内该平台全队列 BLOCKED。
        if self._challenge_cooldown_active(platform):
            self.ctx.queue.block(
                task_id,
                f"challenge: 平台 {platform} 处于挑战冷却期（24h），venue {venue} 延后；"
                "冷却期满后 `crawler resume --all` 恢复",
            )
            report.blocked += 1
            log_event(
                "WARNING",
                "blocked (challenge cooldown)",
                task_id=task_id,
                venue=venue,
                stage="fetch",
                error_class=ErrorClass.CHALLENGE.value,
            )
            return False

        # 批入口（首个 auth_gated fetch）：工作时段窗检查一次 + provider/session 建立。
        if venue not in self._auth_batch:
            window = getattr(self.ctx.config, "auth_work_hours", _DEFAULT_AUTH_WORK_HOURS)
            if not _work_hours_ok(window, self._clock()):
                self._work_hours_blocked.add(venue)
                self._block_work_hours(task_id, venue, report)
                return False
            try:
                provider = self._auth_manager.resolve(route.auth_profile or platform)
                session = self._auth_manager.ensure_session(provider.provider_id)
            except CrawlerError as exc:
                # 无 session 且非交互 → AuthRequired(AUTH_EXPIRED) → 整批 BLOCKED(auth)。
                self._route_error(row, exc.error_class, str(exc), report)
                return False
            self._auth_batch[venue] = _BatchGate(
                provider=provider, session=session, last_check_at=self._clock()
            )
        gate = self._auth_batch[venue]

        # 日配额（§8.3）：auth 平台主域当日 fetch 尝试篇次达 cap → BLOCKED(config)。
        domain = adapter.domains[0]
        cap = int(getattr(self.ctx.config, "auth_daily_cap", _DEFAULT_AUTH_DAILY_CAP))
        if self.ctx.repo.count_fetch_today(domain) >= cap:
            self.ctx.queue.block(
                task_id,
                f"config: 日配额达上限（domain={domain} cap={cap}），venue {venue} 剩余 fetch "
                "延后；次日或 `crawler resume --all` 恢复",
            )
            report.blocked += 1
            log_event(
                "WARNING",
                "blocked (daily quota)",
                task_id=task_id,
                venue=venue,
                stage="fetch",
                error_class=ErrorClass.CONFIG.value,
                domain=domain,
            )
            return False

        # 周期性健康门（§8.2）：每 N 篇 或 老化超 max_age → health_check（防半批 401 轰炸）。
        interval = int(
            getattr(self.ctx.config, "auth_health_interval", _DEFAULT_AUTH_HEALTH_INTERVAL)
        )
        max_age_s = float(
            getattr(self.ctx.config, "auth_health_max_age_s", _DEFAULT_AUTH_HEALTH_MAX_AGE_S)
        )
        now = self._clock()
        if (
            gate.fetched_since_check >= interval
            or (now - gate.last_check_at).total_seconds() >= max_age_s
        ):
            status = gate.provider.health_check(gate.session)
            if status == HealthStatus.EXPIRED:
                new = gate.provider.refresh(gate.session)
                if new is not None:
                    gate.session = new
                    gate.fetched_since_check = 0
                    gate.last_check_at = now
                else:
                    self._route_error(
                        row,
                        ErrorClass.AUTH_EXPIRED,
                        "session expired；refresh 失败 → 整批 BLOCKED(auth)",
                        report,
                    )
                    return False
            elif status == HealthStatus.CHALLENGED:
                self._route_error(row, ErrorClass.CHALLENGE, "health_check 命中风控/挑战页", report)
                return False
            else:
                gate.fetched_since_check = 0
                gate.last_check_at = now

        # 注入 session 供 fetch 阶段（§8.2；resolve/fetch 经 ctx.auth_sessions 读取）。
        self.ctx.auth_sessions[venue] = gate.session
        return True

    def _block_work_hours(self, task_id: str, venue: str, report: RunReport) -> None:
        """工作时段窗外 → 延迟不失败（BLOCKED，可 resume；§8.6）。"""
        window = getattr(self.ctx.config, "auth_work_hours", _DEFAULT_AUTH_WORK_HOURS)
        self.ctx.queue.block(
            task_id,
            f"work_hours_window: 当前时刻在工作时段窗 {window!r} 外，venue {venue} 的 auth_gated "
            "fetch 延迟（非失败）；调整 [auth].work_hours 或窗内 `crawler resume --all` 恢复",
        )
        report.blocked += 1
        log_event(
            "INFO",
            f"blocked (work-hours window {window!r})",
            task_id=task_id,
            venue=venue,
            stage="fetch",
        )

    # -- challenge 平台冷却（§8.4；跨运行持久化在 config-home）---------------------

    def _cooldown_path(self, platform: str) -> Path:
        return self.ctx.config.home / "state" / "cooldown" / f"{platform}.json"

    def _platform_of(self, venue: str) -> str | None:
        try:
            return self.ctx.registry.route(venue).fulltext_adapter.adapter_id
        except CrawlerError:
            return None

    def _enter_challenge_cooldown(self, venue: str) -> None:
        """CHALLENGE → 写平台冷却（now+24h）到运行态字典 + config-home JSON（§8.4）。"""
        platform = self._platform_of(venue)
        if platform is None:
            return
        until = self._clock() + _CHALLENGE_COOLDOWN
        self._challenge_cooldown[platform] = until
        path = self._cooldown_path(platform)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"until": until.isoformat()}), encoding="utf-8")
        except OSError as exc:
            log_event("WARNING", f"challenge 冷却状态落盘失败（运行态仍生效）: {exc}", venue=venue)

    def _challenge_cooldown_active(self, platform: str) -> bool:
        """平台是否在冷却期内：运行态字典优先，缺失则从 config-home JSON 加载（进程重启不丢）。"""
        until = self._challenge_cooldown.get(platform)
        if until is None:
            path = self._cooldown_path(platform)
            if path.is_file():
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    until = datetime.fromisoformat(str(data["until"]))
                    self._challenge_cooldown[platform] = until
                except (OSError, ValueError, KeyError):
                    return False
        return until is not None and self._clock() < until

    def _enqueue_oa_fallback(self, row: sqlite3.Row, paper_id: str, report: RunReport) -> None:
        """no_entitlement（fetch 或 resolve 阶段）→ 派生 oa_fallback 任务（§8.1 接线点 A）。

        `paper_id` 由调用方按阶段解析（fetch: asset→paper；resolve: params["paper"]）。paper
        无 doi identifier / 任务无 venue → 不派生（AC-4.3：仅有 DOI 且可路由才尝试 OA 兜底）。
        """
        doi_rows = self.ctx.db.query(
            "SELECT value FROM identifier WHERE paper_id = ? AND scheme = 'doi' "
            "ORDER BY is_primary DESC, value LIMIT 1",
            (paper_id,),
        )
        if not doi_rows:
            return  # 无 doi → 无从 unpaywall 兜底
        if row["venue_id"] is None:
            return  # oa_fallback handler 需 venue（`_task_venue`/registry 路由）；无则不派生
        doi = str(doi_rows[0]["value"])
        venue = str(row["venue_id"])
        parent_id = str(row["parent_id"]) if row["parent_id"] is not None else None
        self._enqueue_child(
            report, "oa_fallback", venue, {"paper": paper_id, "doi": doi}, parent_id, force=False
        )

    # -- 错误分类路由（design/05 §4）----------------------------------------

    def _route_error(
        self, row: sqlite3.Row, error_class: ErrorClass, msg: str, report: RunReport
    ) -> None:
        task_id = str(row["id"])
        kind = str(row["kind"])
        venue = str(row["venue_id"]) if row["venue_id"] is not None else None
        params: dict[str, Any] = json.loads(str(row["params_json"]))
        asset_id = str(params["asset"]) if kind == "fetch" and "asset" in params else None

        if error_class is ErrorClass.AUTH_EXPIRED:
            self.ctx.queue.block(
                task_id,
                f"auth_expired: {msg}；修复凭证后运行 `crawler resume --all` 恢复",
            )
            report.blocked += 1
            if kind == "fetch" and venue is not None:
                self._auth_blocked_venues.add(venue)
            log_event(
                "WARNING",
                f"blocked: {msg}",
                task_id=task_id,
                venue=venue,
                stage=kind,
                error_class=error_class.value,
            )
            return

        if error_class in _BLOCK_CLASSES:
            # CHALLENGE → 额外写平台冷却 24h（§8.4）；冷却内该平台全队列 BLOCKED（健康门读该状态）。
            if error_class is ErrorClass.CHALLENGE and venue is not None:
                self._enter_challenge_cooldown(venue)
            self.ctx.queue.block(task_id, f"{error_class.value}: {msg}")
            report.blocked += 1
            log_event(
                "WARNING",
                f"blocked: {msg}",
                task_id=task_id,
                venue=venue,
                stage=kind,
                error_class=error_class.value,
            )
            return

        if error_class is ErrorClass.GONE:
            if asset_id is not None:
                self.ctx.repo.mark_asset(asset_id, state="gone")
            self.ctx.queue.complete(task_id)  # 预期内跳过：任务 DONE、不重试
            report.skipped += 1
            log_event(
                "WARNING",
                f"gone (预期内，不重试): {msg}",
                task_id=task_id,
                venue=venue,
                stage=kind,
                error_class=error_class.value,
            )
            return

        # NO_ENTITLEMENT 独立终态（§8.5）：预期内、**不计失败率**——任务 complete（非 FAILED）、
        # asset 标 no_entitlement、report.no_entitlement 单列计数；开启 oa_fallback 且有 doi 时
        # 派生 unpaywall OA 兜底任务（§8.1 接线点 A）。**与现状 diff**：此前 NO_ENTITLEMENT 走
        # RETRY_TABLE 缺省 RetrySpec(1)→FAILED（计 failed），现改为独立终态（回归锁定：
        # test_pipeline_errors 同步更新）。
        if error_class is ErrorClass.NO_ENTITLEMENT:
            # OA-fallback 派生的 paper 来源（§8.1 接线点 A 明文"fetch 失败 **或 resolve
            # entitlement 预检否**"）：fetch 阶段从 asset→paper（并标该 asset no_entitlement）；
            # resolve 阶段从 params["paper"]——elsevier_sd 等 auth_gated 平台在 resolve 预检
            # entitled:false 即抛 NE（无平台 asset 产出，AC-4.3 真实载体）。
            oa_paper_id: str | None = None
            if kind == "fetch" and asset_id is not None:
                self.ctx.repo.mark_asset(asset_id, state="no_entitlement")
                ne_asset = self.ctx.repo.get_asset(asset_id)
                oa_paper_id = str(ne_asset["paper_id"]) if ne_asset is not None else None
            elif kind == "resolve" and "paper" in params:
                oa_paper_id = str(params["paper"])
            self.ctx.queue.complete(task_id)
            report.no_entitlement += 1
            log_event(
                "WARNING",
                f"no_entitlement（不计失败率）: {msg}",
                task_id=task_id,
                venue=venue,
                stage=kind,
                error_class=error_class.value,
            )
            if self.ctx.oa_fallback and oa_paper_id is not None:
                self._enqueue_oa_fallback(row, oa_paper_id, report)
            return

        # §8.2 文件验证器联动：INTEGRITY 疑似 auth_leak（拦截页伪装 PDF）→ 强制下个 fetch 必探
        # 健康门（门龄归零：把 last_check_at 拨老，令下个 auth_gated fetch 的老化判定必触发
        # health_check），防伪装 PDF 连环命中。仅当该 venue 已有活跃健康门批。
        if error_class is ErrorClass.INTEGRITY and venue is not None:
            integrity_gate = self._auth_batch.get(venue)
            if integrity_gate is not None:
                integrity_gate.last_check_at = self._clock() - timedelta(days=1)

        # 其余走 RETRY_TABLE：TRANSIENT/RATE_LIMITED/INTEGRITY 可重试；PARSE 表内缺省
        # RetrySpec(1) → 立即 FAILED。
        effective = error_class
        if error_class is ErrorClass.RATE_LIMITED:
            seen = self._rate_limited_seen.get(task_id, 0) + 1
            self._rate_limited_seen[task_id] = seen
            if seen > _RATE_LIMITED_ESCALATION:
                effective = ErrorClass.TRANSIENT
                log_event(
                    "WARNING",
                    f"rate_limited x{seen} in this run; escalating to transient",
                    task_id=task_id,
                    venue=venue,
                    stage=kind,
                    error_class=error_class.value,
                )

        state = self.ctx.queue.fail(task_id, effective, msg)
        if state == "PENDING":
            self._sleep_backoff(task_id, effective)
            log_event(
                "INFO",
                f"retrying ({effective.value}): {msg}",
                task_id=task_id,
                venue=venue,
                stage=kind,
                error_class=effective.value,
            )
            return
        report.failed += 1
        report.failures.append(
            {"task_id": task_id, "stage": kind, "error_class": effective.value, "msg": msg}
        )
        log_event(
            "ERROR",
            f"failed: {msg}",
            task_id=task_id,
            venue=venue,
            stage=kind,
            error_class=effective.value,
        )

    def _sleep_backoff(self, task_id: str, error_class: ErrorClass) -> None:
        """按 RETRY_TABLE × retry_scale 退避（经 sleeper；RATE_LIMITED 以连续计数索引）。"""
        spec = RETRY_TABLE.get(error_class, RetrySpec(1))
        if not spec.backoff_seconds:
            return
        if error_class is ErrorClass.RATE_LIMITED:
            index = self._rate_limited_seen.get(task_id, 1) - 1
        else:
            row = self.ctx.queue.get(task_id)
            attempts = int(row["attempts"]) if row is not None else 1
            index = attempts - 1
        index = max(0, min(index, len(spec.backoff_seconds) - 1))
        wait = spec.backoff_seconds[index] * self.ctx.config.retry_scale
        if wait > 0:
            self.ctx.sleeper(wait)

    # -- pull 级联编排 -------------------------------------------------------

    def _run_pull(self, task: sqlite3.Row, report: RunReport) -> None:
        """pull 级联（design/05 §1）：discover → Selector 圈定 issues → 每期
        enumerate → resolve（--limit 时仅前 N 篇，缺陷 C-C）→（dry-run 止步并填
        planned_*）→ 每候选 asset fetch →（with_extract）extract → ingest 尾部必跑。

        每阶段 = "enqueue 子任务（parent_id=pull，fresh_skip 记 skipped）→ 嵌套
        drain"；阶段边界从 DB 重新选定输入（无论上一阶段是刚执行还是 fresh_skip，
        持久化实体都是唯一事实源）。
        """
        ctx = self.ctx
        pull_id = str(task["id"])
        venue_id = str(task["venue_id"])
        params = _params_of(task)
        sel = _selector_from_params(params)
        with_extract = bool(params.get("with_extract", False))
        force = bool(params.get("force", False))

        spec = ctx.registry.get(venue_id)  # venue 在级联期被移除 → CONFIG → BLOCKED
        ctx.repo.upsert_venue(spec)

        # 阶段 1 discover（Selector 的 issue 范围进任务参数——圈定即持久化范围）
        self._enqueue_child(report, "discover", venue_id, _issue_scope_params(sel), pull_id, force)
        self._drain_loop(report)

        # 阶段 2 enumerate（一期一个子任务）
        issues = ctx.repo.list_issues(venue_id, volume=sel.volume, number=sel.issue, year=sel.year)
        for issue in issues:
            self._enqueue_child(
                report, "enumerate", venue_id, {"issue": str(issue["id"])}, pull_id, force
            )
        self._drain_loop(report)

        # 阶段 3 resolve（dois/filter_expr 圈定 papers）
        papers = self._select_papers(venue_id, issues, sel)
        # 缺陷 C-C：--limit 前置到 resolve 圈选——只对确定性顺序（`_select_papers` 稳定序：
        # issue 有序 × 标题有序）的前 N 篇建 resolve 任务，而非全量 resolve 后才截断
        # （2260 篇量级 pull 不再对将被丢弃的绝大多数做无谓 resolve）。稳定序保证断点续爬
        # 重跑圈选同一子集。limit=None 时保持全量 resolve。
        resolve_papers = papers if sel.limit is None else papers[: sel.limit]
        for paper in resolve_papers:
            self._enqueue_child(
                report, "resolve", venue_id, {"paper": str(paper["id"])}, pull_id, force
            )
        self._drain_loop(report)

        # 候选资产：只来自已 resolve 的前 N 篇；再按 limit 做 **asset 级**截断——多资产/零
        # 资产 paper 下 asset 数≠paper 数，asset 级截断保持 --limit 的"asset 数上限"语义
        # 且与 dry-run 对账一致（前 N 篇的前 limit 个 asset == 旧全量 resolve 后前 limit 个
        # asset，故落盘子集与修复前逐字一致）。gone/no_entitlement 不进 fetch。
        candidates = self._candidate_assets(resolve_papers, sel.limit)

        if ctx.dry_run:
            # planned_* 仅 dry-run 填充（T7b 渲染契约）。planned_bytes：mock 的
            # resolve 不携带内容长度（AssetPlan 无 size 字段），无从估算 → 恒 0，
            # 真实 adapter 提供 Content-Length 后再填（如实注记）。
            report.planned_downloads = sum(
                1 for a in candidates if not (str(a["state"]) == "fetched" and fetched_file_ok(a))
            )
            report.planned_bytes = 0
            report.notes.append(
                f"dry-run：级联止于 resolve；将下载 {report.planned_downloads} 个资产"
                "（未创建 fetch 任务、data/ 零写入）"
            )
            return

        # 阶段 4 fetch（每候选 asset 一个子任务；已 DONE 的同键任务 fresh_skip）
        for asset in candidates:
            self._enqueue_child(
                report, "fetch", venue_id, {"asset": str(asset["id"])}, pull_id, force
            )
        self._drain_loop(report)

        # 阶段 5 extract（--extract 时；对 fetched pdf 资产）
        if with_extract:
            for asset in self._fetched_pdf_assets(papers):
                self._enqueue_child(
                    report, "extract", venue_id, {"asset": str(asset["id"])}, pull_id, force
                )
            self._drain_loop(report)

        # 阶段 6 ingest 尾部必跑（FRESHNESS_TTL=0 → 每次重跑）
        self._enqueue_child(report, "ingest", venue_id, {}, pull_id, force)
        self._drain_loop(report)

    # -- pull 的选定与入队小件 ----------------------------------------------

    def _enqueue_child(
        self,
        report: RunReport,
        kind: TaskKind,
        venue_id: str,
        params: dict[str, object],
        parent_id: str | None,
        force: bool,
    ) -> EnqueueResult:
        result = self.ctx.queue.enqueue(kind, venue_id, params, parent_id=parent_id, force=force)
        self._note_enqueue(result, kind, venue_id, report)
        return result

    def _note_enqueue(
        self, result: EnqueueResult, kind: str, venue_id: str | None, report: RunReport
    ) -> None:
        """fresh_skip 记 skipped 并落日志（§5.3 "日志记 skipped"）；duplicate 仅记日志
        不计数（既存活跃任务会被本次 drain 领取执行，按其结果计数，避免双计）。"""
        if result.status == "fresh_skip":
            report.skipped += 1
            log_event(
                "INFO",
                "skipped",
                task_id=result.task_id,
                venue=venue_id,
                stage=kind,
                reason="fresh",
            )
        elif result.status == "duplicate":
            log_event(
                "DEBUG",
                "duplicate task already active",
                task_id=result.task_id,
                venue=venue_id,
                stage=kind,
            )

    def _select_papers(
        self, venue_id: str, issues: list[sqlite3.Row], sel: Selector
    ) -> list[sqlite3.Row]:
        """选定 issues 内的 papers（去重），并应用 dois / filter_expr 圈定。"""
        seen: set[str] = set()
        out: list[sqlite3.Row] = []
        wanted_dois = {d.lower() for d in sel.dois}
        for issue in issues:
            for paper in self.ctx.repo.list_papers(venue_id, issue_id=str(issue["id"])):
                paper_id = str(paper["id"])
                if paper_id in seen:
                    continue
                seen.add(paper_id)
                if sel.filter_expr is not None:
                    if sel.filter_expr.lower() not in str(paper["title"]).lower():
                        continue
                if wanted_dois:
                    rows = self.ctx.db.query(
                        "SELECT value FROM identifier WHERE paper_id = ? AND scheme = 'doi'",
                        (paper_id,),
                    )
                    if not any(str(r["value"]).lower() in wanted_dois for r in rows):
                        continue
                out.append(paper)
        return out

    def _candidate_assets(self, papers: list[sqlite3.Row], limit: int | None) -> list[sqlite3.Row]:
        """papers 的可取回资产（排除 gone/no_entitlement），按稳定顺序，limit 截断。"""
        out: list[sqlite3.Row] = []
        for paper in papers:
            out.extend(
                self.ctx.db.query(
                    "SELECT * FROM asset WHERE paper_id = ? "
                    "AND state NOT IN ('gone', 'no_entitlement') "
                    "ORDER BY kind, version",
                    (str(paper["id"]),),
                )
            )
        if limit is not None:
            out = out[:limit]
        return out

    def _fetched_pdf_assets(self, papers: list[sqlite3.Row]) -> list[sqlite3.Row]:
        out: list[sqlite3.Row] = []
        for paper in papers:
            out.extend(
                self.ctx.db.query(
                    "SELECT * FROM asset WHERE paper_id = ? "
                    "AND state = 'fetched' AND kind = 'pdf' ORDER BY kind, version",
                    (str(paper["id"]),),
                )
            )
        return out


def _params_of(task: sqlite3.Row) -> dict[str, Any]:
    parsed: dict[str, Any] = json.loads(str(task["params_json"]))
    return parsed


__all__ = ["PipelineRunner"]
