"""任务队列与状态机（接口冻结件 §2.5 `tasks.py`）。

设计依据：
- design/05 §2：任务模型、状态机、入队去重、BLOCKED/FAILED 语义、新鲜度策略。
- design/05 §4：错误分类学与重试表（经 `errors.RETRY_TABLE` 消费，队列不复制策略）。
- design/05 §8：状态机转移全覆盖（含非法转移拒绝）。

事务纪律（T2 review 知会）：`TaskQueue` 直接经 `Database.execute/query/tx` 操作 task 表
（不经 `Repo`——`Repo` 方法自带 BEGIN IMMEDIATE，不可被外层 `tx()` 嵌套）；本模块自身的
`tx()` 仅用于 `claim_next` 的 SELECT+UPDATE 原子性，绝不嵌套。Phase 1 串行单写者，其余
读改写以 autocommit 单语句落库即安全。
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from paper_crawler.errors import RETRY_TABLE, ErrorClass, IllegalTransition, RetrySpec
from paper_crawler.storage.db import Database
from paper_crawler.types import new_ulid

# `oa_fallback` = auth-framework §8.1 的第七 handler（no_entitlement 的 unpaywall OA 兜底
# 派生任务；纯附加，默认关闭——仅当 `StageContext.oa_fallback` 开启且 paper 有 doi 时由
# `runner._route_error` 的 NO_ENTITLEMENT 分支派生。既有六阶段语义零改动）。
TaskKind = Literal[
    "pull", "discover", "enumerate", "resolve", "fetch", "extract", "ingest", "oa_fallback"
]
TaskState = Literal["PENDING", "RUNNING", "DONE", "FAILED", "BLOCKED"]

# 全部合法状态（供 5×5 转移矩阵测试枚举）。
TASK_STATES: tuple[TaskState, ...] = ("PENDING", "RUNNING", "DONE", "FAILED", "BLOCKED")

# 状态机合法转移全集（design/05 §8；接口冻结件 §2.5 逐条枚举的七条边）：
#   PENDING→RUNNING（claim）
#   RUNNING→DONE（complete）| FAILED（fail 到顶）| BLOCKED（block）| PENDING（fail 退避重试）
#   FAILED→PENDING（retry）
#   BLOCKED→PENDING（resume）
# 其余 (源, 目标) 组合一律非法。
LEGAL_TRANSITIONS: frozenset[tuple[TaskState, TaskState]] = frozenset(
    {
        ("PENDING", "RUNNING"),
        ("RUNNING", "DONE"),
        ("RUNNING", "FAILED"),
        ("RUNNING", "BLOCKED"),
        ("RUNNING", "PENDING"),
        ("FAILED", "PENDING"),
        ("BLOCKED", "PENDING"),
    }
)


def validate_transition(current: str, target: str) -> None:
    """状态机单步校验：非 `LEGAL_TRANSITIONS` 之列即 raise `IllegalTransition`。"""
    if (current, target) not in LEGAL_TRANSITIONS:
        raise IllegalTransition(f"illegal task transition: {current} -> {target}")


# 新鲜度 TTL（design/05 §2）。语义精确：
#   None          → 只要曾 DONE 即永远 fresh_skip（resolve/fetch/extract：产物永久有效）；
#   timedelta(0)  → 永不 fresh_skip（ingest/pull：每次重跑）；
#   正 timedelta  → DONE 距今在窗口内则 fresh_skip（discover 24h、enumerate 7d）。
FRESHNESS_TTL: dict[str, timedelta | None] = {
    "discover": timedelta(hours=24),
    "enumerate": timedelta(days=7),
    "resolve": None,
    "fetch": None,
    "extract": None,
    "ingest": timedelta(0),
    "pull": timedelta(0),
    # oa_fallback 产物（planned OA asset）永久有效——曾 DONE 即 fresh_skip（同 resolve 语义）。
    "oa_fallback": None,
}


@dataclass(frozen=True)
class EnqueueResult:
    """入队结果；`fresh_skip`/`duplicate` 时 `task_id` 指向既有任务，`enqueued` 时为新 id。"""

    task_id: str | None
    status: Literal["enqueued", "duplicate", "fresh_skip"]


def _venue_clause(venue_id: str | None, params: list[object]) -> str:
    """方言中性的 NULL-安全 venue 等值子句（避免 SQLite 专有 `IS ?`）。"""
    if venue_id is None:
        return "venue_id IS NULL"
    params.append(venue_id)
    return "venue_id = ?"


class TaskQueue:
    """task 表之上的入队/领取/状态机操作；错误重试策略取自 `RETRY_TABLE`。"""

    def __init__(self, db: Database, clock: Callable[[], datetime] | None = None) -> None:
        self.db = db
        # 时钟注入：默认 UTC now；测试可拨动假时钟验证新鲜度窗口边界。
        self._clock: Callable[[], datetime] = clock or (lambda: datetime.now(UTC))

    # -- 时钟 ---------------------------------------------------------------

    def _now(self) -> datetime:
        return self._clock()

    def _now_iso(self) -> str:
        return self._clock().isoformat()

    # -- 幂等键 -------------------------------------------------------------

    def canonical_params(self, params: Mapping[str, object]) -> str:
        """params 的规范化 JSON（sorted-keys 紧凑）——入队幂等键的构成部分。"""
        return json.dumps(dict(params), sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    # -- 入队 ---------------------------------------------------------------

    def enqueue(
        self,
        kind: TaskKind,
        venue_id: str | None,
        params: Mapping[str, object],
        *,
        parent_id: str | None = None,
        force: bool = False,
    ) -> EnqueueResult:
        """入队一个任务，返回处置结果。

        - `fresh_skip`：同键存在 DONE 且未过 `FRESHNESS_TTL`（`force=True` 绕过本判定）。
        - `duplicate`：同键已有 PENDING/RUNNING——直接 INSERT，靠 T2 的部分唯一索引
          `idx_task_active_idem` 捕获 `IntegrityError` 转 duplicate（竞态安全，不做
          SELECT-then-INSERT）。`force` 不绕过 duplicate。
        - `enqueued`：新建 PENDING 任务。
        """
        canonical = self.canonical_params(params)
        if not force:
            fresh_id = self._fresh_skip(kind, venue_id, canonical)
            if fresh_id is not None:
                return EnqueueResult(task_id=fresh_id, status="fresh_skip")
        task_id = new_ulid()
        now = self._now_iso()
        try:
            self.db.execute(
                "INSERT INTO task "
                "(id, kind, venue_id, params_json, state, attempts, parent_id, "
                " created_at, updated_at) "
                "VALUES (?, ?, ?, ?, 'PENDING', 0, ?, ?, ?)",
                (task_id, kind, venue_id, canonical, parent_id, now, now),
            )
        except sqlite3.IntegrityError:
            # 活跃幂等冲突 → duplicate；若非此因（如 parent_id 外键失败）则不吞、原样抛出。
            existing = self._find_active(kind, venue_id, canonical)
            if existing is None:
                raise
            return EnqueueResult(task_id=existing, status="duplicate")
        return EnqueueResult(task_id=task_id, status="enqueued")

    def _fresh_skip(self, kind: TaskKind, venue_id: str | None, canonical: str) -> str | None:
        """按 `FRESHNESS_TTL` 判定同键最近一次 DONE 是否仍新鲜；是则返回其 id，否则 None。"""
        ttl = FRESHNESS_TTL.get(kind)
        params: list[object] = [kind]
        clause = _venue_clause(venue_id, params)
        params.append(canonical)
        rows = self.db.query(
            "SELECT id, updated_at FROM task "
            f"WHERE kind = ? AND {clause} AND params_json = ? AND state = 'DONE' "
            "ORDER BY updated_at DESC, id DESC LIMIT 1",
            params,
        )
        if not rows:
            return None
        row = rows[0]
        if ttl is None:
            return str(row["id"])  # 永久新鲜：曾 DONE 即跳过
        if ttl == timedelta(0):
            return None  # 永不新鲜：每次重跑
        updated = datetime.fromisoformat(row["updated_at"])
        if self._now() - updated < ttl:
            return str(row["id"])
        return None

    def _find_active(self, kind: TaskKind, venue_id: str | None, canonical: str) -> str | None:
        """查同键最老的活跃（PENDING/RUNNING）任务 id；无则 None。"""
        params: list[object] = [kind]
        clause = _venue_clause(venue_id, params)
        params.append(canonical)
        rows = self.db.query(
            "SELECT id FROM task "
            f"WHERE kind = ? AND {clause} AND params_json = ? "
            "AND state IN ('PENDING', 'RUNNING') "
            "ORDER BY created_at, id LIMIT 1",
            params,
        )
        return str(rows[0]["id"]) if rows else None

    # -- 领取与状态机 -------------------------------------------------------

    def claim_next(self) -> sqlite3.Row | None:
        """领取最老 PENDING → RUNNING（在 `tx()` 事务内 SELECT+UPDATE 原子）；空则 None。"""
        with self.db.tx() as conn:
            pending = conn.execute(
                "SELECT id FROM task WHERE state = 'PENDING' ORDER BY created_at, id LIMIT 1"
            ).fetchone()
            if pending is None:
                return None
            task_id = str(pending["id"])
            conn.execute(
                "UPDATE task SET state = 'RUNNING', updated_at = ? WHERE id = ?",
                (self._now_iso(), task_id),
            )
        return self.get(task_id)

    def complete(self, task_id: str) -> None:
        """RUNNING → DONE（唯一合法源 RUNNING，否则 `IllegalTransition`）。"""
        row = self._require(task_id)
        validate_transition(str(row["state"]), "DONE")
        self.db.execute(
            "UPDATE task SET state = 'DONE', updated_at = ? WHERE id = ?",
            (self._now_iso(), task_id),
        )

    def fail(self, task_id: str, error_class: ErrorClass, msg: str) -> TaskState:
        """按 `RETRY_TABLE` 处置一次失败，返回落定状态（"PENDING" 退避重试 / "FAILED"）。

        `RATE_LIMITED` 不计入 attempts（design/05 §4"不计失败"）；attempts+1 后仍 <
        max_attempts → 回 PENDING，否则 FAILED 并落 error_class/last_error。退避 sleep 属
        runner 层职责，不在队列层。仅 RUNNING 任务可 fail。
        """
        row = self._require(task_id)
        current = str(row["state"])
        if current != "RUNNING":
            raise IllegalTransition(f"illegal task transition: {current} -> PENDING/FAILED (fail)")
        spec: RetrySpec = RETRY_TABLE.get(error_class, RetrySpec(1))
        increment = 0 if error_class is ErrorClass.RATE_LIMITED else 1
        attempts = int(row["attempts"]) + increment
        target: TaskState = "PENDING" if attempts < spec.max_attempts else "FAILED"
        self.db.execute(
            "UPDATE task SET state = ?, attempts = ?, error_class = ?, last_error = ?, "
            "updated_at = ? WHERE id = ?",
            (target, attempts, error_class.value, msg, self._now_iso(), task_id),
        )
        return target

    def block(self, task_id: str, reason: str) -> None:
        """RUNNING → BLOCKED（唯一合法源 RUNNING）；不动 attempts（design/05 §2）。"""
        row = self._require(task_id)
        validate_transition(str(row["state"]), "BLOCKED")
        self.db.execute(
            "UPDATE task SET state = 'BLOCKED', blocked_reason = ?, updated_at = ? WHERE id = ?",
            (reason, self._now_iso(), task_id),
        )

    def resume(self, task_id: str | None = None, *, all_blocked: bool = False) -> int:
        """BLOCKED → PENDING，返回恢复数。`all_blocked=True` 恢复全部 BLOCKED（忽略 task_id）。"""
        if all_blocked:
            rows = self.db.query("SELECT id FROM task WHERE state = 'BLOCKED'")
            for r in rows:
                self._blocked_to_pending(str(r["id"]))
            return len(rows)
        if task_id is None:
            raise ValueError("resume 需要 task_id 或 all_blocked=True")
        row = self._require(task_id)
        current = str(row["state"])
        if current != "BLOCKED":
            raise IllegalTransition(f"illegal task transition: {current} -> PENDING (resume)")
        self._blocked_to_pending(task_id)
        return 1

    def _blocked_to_pending(self, task_id: str) -> None:
        self.db.execute(
            "UPDATE task SET state = 'PENDING', blocked_reason = NULL, updated_at = ? WHERE id = ?",
            (self._now_iso(), task_id),
        )

    def retry_failed(self, error_class: ErrorClass | None = None) -> int:
        """FAILED → PENDING 批量重试，返回重试数；`error_class` 给定则仅重试该类。

        重置 attempts 归 0，使人工 retry 拿到完整的重试预算（design/05 §2/§4"可批量 retry"）。
        """
        if error_class is None:
            rows = self.db.query("SELECT id FROM task WHERE state = 'FAILED'")
        else:
            rows = self.db.query(
                "SELECT id FROM task WHERE state = 'FAILED' AND error_class = ?",
                (error_class.value,),
            )
        now = self._now_iso()
        for r in rows:
            self.db.execute(
                "UPDATE task SET state = 'PENDING', attempts = 0, updated_at = ? WHERE id = ?",
                (now, str(r["id"])),
            )
        return len(rows)

    def recover_running(self) -> int:
        """进程启动时对孤儿 RUNNING 任务的崩溃恢复（design/05 §5 断点续爬）：
        全部 RUNNING → PENDING，返回恢复数。

        Phase 1 单进程串行下，启动时刻存在的 RUNNING 必为上次进程崩溃（kill-9 等）
        的遗留——正常退出不会留下 RUNNING 行。RUNNING→PENDING 是状态机合法边
        （`LEGAL_TRANSITIONS` 中与"退避重试"同边；WHERE 子句保证源状态合法，同
        `resume(all_blocked=True)` 的批量先例）。**不动 attempts**（崩溃不是失败，
        不消耗重试预算）、不动 error_class（保留崩溃前的最后诊断信息）。

        2026-07-21 T7c 仲裁增补（冻结件 §2.5 扩充）：恢复语义属队列状态机职责，
        runner 启动路径经本 API 调用而非直写 task 表。
        """
        rows = self.db.query("SELECT id FROM task WHERE state = 'RUNNING'")
        now = self._now_iso()
        for r in rows:
            self.db.execute(
                "UPDATE task SET state = 'PENDING', updated_at = ? WHERE id = ?",
                (now, str(r["id"])),
            )
        return len(rows)

    # -- 查询 ---------------------------------------------------------------

    def get(self, task_id: str) -> sqlite3.Row | None:
        """按 id 取单个任务；不存在返回 None。"""
        rows = self.db.query("SELECT * FROM task WHERE id = ?", (task_id,))
        return rows[0] if rows else None

    def by_state(self, state: TaskState) -> list[sqlite3.Row]:
        """列出某状态的全部任务，按 created_at 稳定排序。"""
        return self.db.query("SELECT * FROM task WHERE state = ? ORDER BY created_at, id", (state,))

    def _require(self, task_id: str) -> sqlite3.Row:
        row = self.get(task_id)
        if row is None:
            raise KeyError(f"no such task: {task_id}")
        return row


__all__ = [
    "FRESHNESS_TTL",
    "LEGAL_TRANSITIONS",
    "TASK_STATES",
    "EnqueueResult",
    "TaskKind",
    "TaskQueue",
    "TaskState",
    "validate_transition",
]
