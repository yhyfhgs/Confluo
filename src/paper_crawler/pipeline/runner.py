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
- PARSE / NO_ENTITLEMENT → fail 至 FAILED；NO_ENTITLEMENT 另标 asset
  state=no_entitlement；
- 非 CrawlerError 异常 → 按 TRANSIENT 处置并 log_event ERROR。

RunReport 计数口径：`succeeded` = 实际完成下载的 fetch 任务数（AC-1.1/AC-1.2 的
"成功=N"面向用户口径；discover/enumerate/resolve/extract/ingest 的完成经日志与
notes 汇总，不计入 succeeded）；`failed`/`blocked` 为全阶段任务口径；`skipped` =
入队新鲜度跳过（fresh_skip）+ handler 幂等跳过 + GONE 预期内跳过。
`planned_downloads`/`planned_bytes` 仅 dry-run 路径填充（T7b 渲染以 planned>0
判定 dry-run 行——契约）。

runner 启动（`__init__`）：`config.ensure_dirs()` + `cleanup_tmp(data/tmp)`
（§5.2 崩溃残留清理）+ 遗留 RUNNING 任务归还 PENDING（崩溃恢复，见
`_recover_running_tasks` docstring）。
"""

from __future__ import annotations

import json
import sqlite3
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
from paper_crawler.tasks import EnqueueResult, TaskKind, validate_transition
from paper_crawler.types import utcnow_iso

# AUTH_EXPIRED 连带 block 之外的两类"直接 BLOCKED"（design/05 §4）。
_BLOCK_CLASSES = frozenset({ErrorClass.CHALLENGE, ErrorClass.CONFIG})
# 一次运行内同一任务连续 rate_limited 的升级阈值（Phase 1 循环保护）。
_RATE_LIMITED_ESCALATION = 3


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

    def __init__(self, ctx: StageContext) -> None:
        self.ctx = ctx
        ctx.config.ensure_dirs()
        removed = cleanup_tmp(ctx.config.data_dir / "tmp")
        if removed:
            log_event("WARNING", f"startup: removed {removed} stale *.part file(s)")
        self._recover_running_tasks()
        # 单 venue 一旦 auth_expired，本次运行内其余 fetch 连带 block（整批 BLOCKED(auth)）。
        self._auth_blocked_venues: set[str] = set()
        # 一次运行内每任务的连续 rate_limited 计数（升级保护）。
        self._rate_limited_seen: dict[str, int] = {}

    # -- 启动 ---------------------------------------------------------------

    def _recover_running_tasks(self) -> None:
        """崩溃恢复：启动时把遗留 RUNNING 任务归还 PENDING（design/05 §5 断点续爬）。

        Phase 1 单进程串行：启动时刻存在 RUNNING 行只可能是上次进程被杀（kill-9）
        的残留。RUNNING→PENDING 是状态机合法边（`LEGAL_TRANSITIONS` 的"退避重试"
        边，逐行 `validate_transition` 守护）；`TaskQueue` 未提供公开恢复 API——
        `fail()` 会错误消耗 attempts 重试预算——故此处经 `Database` 直接执行同语义
        UPDATE。实现期注记，T10 收尾回填设计文档。
        """
        rows = self.ctx.db.query("SELECT id, state FROM task WHERE state = 'RUNNING'")
        for row in rows:
            validate_transition(str(row["state"]), "PENDING")
            self.ctx.db.execute(
                "UPDATE task SET state = 'PENDING', updated_at = ? WHERE id = ?",
                (utcnow_iso(), str(row["id"])),
            )
        if rows:
            log_event(
                "WARNING",
                f"startup: recovered {len(rows)} RUNNING task(s) to PENDING (crash leftovers)",
            )

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

    # -- 报告 ---------------------------------------------------------------

    def _new_report(self, command: str, venue_id: str | None) -> RunReport:
        self._auth_blocked_venues = set()
        self._rate_limited_seen = {}
        return RunReport(command=command, venue_id=venue_id, started_at=utcnow_iso())

    def _finalize(self, report: RunReport) -> RunReport:
        report.finished_at = utcnow_iso()
        report.save(self.ctx.config.reports_dir)
        log_event(
            "INFO",
            f"{report.command}: 成功 {report.succeeded} 失败 {report.failed} "
            f"阻塞 {report.blocked} 跳过 {report.skipped}",
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

        # 整批 BLOCKED(auth)：同 venue 剩余 fetch 子任务连带（attempts 不动）。
        if kind == "fetch" and venue is not None and venue in self._auth_blocked_venues:
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
                stage=kind,
                error_class=ErrorClass.AUTH_EXPIRED.value,
            )
            return

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

        # 其余走 RETRY_TABLE：TRANSIENT/RATE_LIMITED/INTEGRITY 可重试；
        # PARSE/NO_ENTITLEMENT 表内缺省 RetrySpec(1) → 立即 FAILED。
        if error_class is ErrorClass.NO_ENTITLEMENT and asset_id is not None:
            self.ctx.repo.mark_asset(asset_id, state="no_entitlement")

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
        enumerate → 每 paper resolve →（dry-run 止步并填 planned_*）→ 每候选
        asset fetch →（with_extract）extract → ingest 尾部必跑。

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
        for paper in papers:
            self._enqueue_child(
                report, "resolve", venue_id, {"paper": str(paper["id"])}, pull_id, force
            )
        self._drain_loop(report)

        # 候选资产（resolve 全量后按 limit 截断；gone/no_entitlement 不再进 fetch）
        candidates = self._candidate_assets(papers, sel.limit)

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
