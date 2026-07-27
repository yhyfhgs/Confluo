"""任务队列语义测试（phase1-plan Task 5；Refs: FR-10, AC-1.3, AC-1.5）。

覆盖 design/05 §2/§4：canonical 幂等键、入队去重（duplicate/fresh_skip/force）、新鲜度
TTL 边界（注入时钟）、fail 的 RETRY_TABLE 处置（RATE_LIMITED 不计失败）、block/resume/
retry_failed 的计数与状态语义。
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from paper_crawler.errors import ErrorClass
from paper_crawler.storage.db import Database
from paper_crawler.tasks import TaskQueue


class FakeClock:
    """可拨动的假时钟（注入 TaskQueue 以控时序与新鲜度窗口）。"""

    def __init__(self, start: datetime) -> None:
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def advance(self, delta: timedelta) -> None:
        self.now += delta


@pytest.fixture
def database(tmp_path: Path) -> Iterator[Database]:
    db = Database(tmp_path / "tasks.sqlite")
    db.migrate()
    yield db
    db.close()


@pytest.fixture
def queue(database: Database) -> TaskQueue:
    return TaskQueue(database)


# ---------------------------------------------------------------------------
# canonical_params
# ---------------------------------------------------------------------------


def test_canonical_params_sorted_and_compact(queue: TaskQueue) -> None:
    """键排序 + 紧凑分隔符（无空格）。"""
    assert queue.canonical_params({"b": 1, "a": 2}) == '{"a":2,"b":1}'


def test_canonical_params_key_order_independent(queue: TaskQueue) -> None:
    """入参键序不影响规范化结果（幂等键稳定）。"""
    assert queue.canonical_params({"a": 1, "b": 2}) == queue.canonical_params({"b": 2, "a": 1})


def test_canonical_params_non_ascii_preserved(queue: TaskQueue) -> None:
    """ensure_ascii=False：非 ASCII 原样保留（与仓储层 JSON 约定一致）。"""
    assert queue.canonical_params({"q": "金融"}) == '{"q":"金融"}'


def test_canonical_params_empty_dict(queue: TaskQueue) -> None:
    """空参数 dict（如 discover 全量时间轴的 `{}`）规范化为 `{}`——幂等键稳定不崩。"""
    assert queue.canonical_params({}) == "{}"


def test_canonical_params_nested_dict_keys_sorted_recursively(queue: TaskQueue) -> None:
    """嵌套 dict 的内层键也被 sort_keys 递归排序 → 入参内外层键序均不影响幂等键。"""
    nested = queue.canonical_params({"outer": {"b": 2, "a": 1}, "k": 3})
    assert nested == '{"k":3,"outer":{"a":1,"b":2}}'
    assert queue.canonical_params({"outer": {"b": 2, "a": 1}}) == queue.canonical_params(
        {"outer": {"a": 1, "b": 2}}
    )


# ---------------------------------------------------------------------------
# enqueue：enqueued / duplicate / fresh_skip / force
# ---------------------------------------------------------------------------


def test_enqueue_new_is_enqueued(queue: TaskQueue) -> None:
    result = queue.enqueue("discover", "jfe", {"since": "2024"})
    assert result.status == "enqueued"
    assert result.task_id is not None
    row = queue.get(result.task_id)
    assert row is not None
    assert row["state"] == "PENDING"
    assert row["kind"] == "discover"
    assert row["params_json"] == '{"since":"2024"}'


def test_enqueue_duplicate_active_returns_existing_id(queue: TaskQueue) -> None:
    """同键 PENDING 已在 → duplicate，且返回既有 id（靠部分唯一索引捕获 IntegrityError）。"""
    first = queue.enqueue("enumerate", "jfe", {"volume": "160"})
    second = queue.enqueue("enumerate", "jfe", {"volume": "160"})
    assert second.status == "duplicate"
    assert second.task_id == first.task_id


def test_enqueue_duplicate_when_running(queue: TaskQueue) -> None:
    """RUNNING 也算活跃：claim 后再入队同键 → duplicate。"""
    first = queue.enqueue("enumerate", "jfe", {"volume": "161"})
    queue.claim_next()  # → RUNNING
    second = queue.enqueue("enumerate", "jfe", {"volume": "161"})
    assert second.status == "duplicate"
    assert second.task_id == first.task_id


def test_enqueue_param_order_dedupes(queue: TaskQueue) -> None:
    """不同键序但 canonical 相同 → 视为同键 → duplicate。"""
    queue.enqueue("enumerate", "jfe", {"volume": "9", "issue": "1"})
    second = queue.enqueue("enumerate", "jfe", {"issue": "1", "volume": "9"})
    assert second.status == "duplicate"


def test_enqueue_different_venue_not_duplicate(queue: TaskQueue) -> None:
    """venue 不同 → 不同键 → 各自入队。"""
    a = queue.enqueue("enumerate", "jfe", {"volume": "1"})
    b = queue.enqueue("enumerate", "rfs", {"volume": "1"})
    assert a.status == "enqueued"
    assert b.status == "enqueued"
    assert a.task_id != b.task_id


def _drain_to_done(queue: TaskQueue) -> str:
    """claim 最老 PENDING 并 complete，返回其 task_id。"""
    claimed = queue.claim_next()
    assert claimed is not None
    queue.complete(str(claimed["id"]))
    return str(claimed["id"])


def test_fresh_skip_within_ttl(database: Database) -> None:
    """discover DONE 后 23h（< 24h TTL）再入队 → fresh_skip，返回既有 DONE id。"""
    clock = FakeClock(datetime(2026, 1, 1, tzinfo=UTC))
    queue = TaskQueue(database, clock=clock)
    queue.enqueue("discover", "jfe", {"since": "2024"})
    done_id = _drain_to_done(queue)
    clock.advance(timedelta(hours=23))
    result = queue.enqueue("discover", "jfe", {"since": "2024"})
    assert result.status == "fresh_skip"
    assert result.task_id == done_id


def test_stale_after_ttl_reenqueues(database: Database) -> None:
    """discover DONE 后 25h（> 24h TTL）再入队 → enqueued（重新抓取）。"""
    clock = FakeClock(datetime(2026, 1, 1, tzinfo=UTC))
    queue = TaskQueue(database, clock=clock)
    queue.enqueue("discover", "jfe", {"since": "2024"})
    _drain_to_done(queue)
    clock.advance(timedelta(hours=25))
    result = queue.enqueue("discover", "jfe", {"since": "2024"})
    assert result.status == "enqueued"


def test_enumerate_seven_day_ttl_boundary(database: Database) -> None:
    """enumerate TTL=7d：6d 内 fresh_skip，8d 后 enqueued。"""
    clock = FakeClock(datetime(2026, 1, 1, tzinfo=UTC))
    queue = TaskQueue(database, clock=clock)
    queue.enqueue("enumerate", "jfe", {"volume": "160"})
    _drain_to_done(queue)
    clock.advance(timedelta(days=6))
    assert queue.enqueue("enumerate", "jfe", {"volume": "160"}).status == "fresh_skip"
    clock.advance(timedelta(days=2))  # 累计 8d
    assert queue.enqueue("enumerate", "jfe", {"volume": "160"}).status == "enqueued"


def test_ttl_none_is_permanently_fresh(database: Database) -> None:
    """resolve TTL=None：曾 DONE 即永远 fresh_skip（拨钟 100d 仍跳过）。"""
    clock = FakeClock(datetime(2026, 1, 1, tzinfo=UTC))
    queue = TaskQueue(database, clock=clock)
    queue.enqueue("resolve", "jfe", {"paper": "p1"})
    _drain_to_done(queue)
    clock.advance(timedelta(days=100))
    assert queue.enqueue("resolve", "jfe", {"paper": "p1"}).status == "fresh_skip"


def test_ttl_zero_never_fresh(database: Database) -> None:
    """ingest TTL=timedelta(0)：即便刚 DONE 也不 fresh_skip（每次重跑）。"""
    clock = FakeClock(datetime(2026, 1, 1, tzinfo=UTC))
    queue = TaskQueue(database, clock=clock)
    queue.enqueue("ingest", None, {"batch": "b1"})
    _drain_to_done(queue)
    assert queue.enqueue("ingest", None, {"batch": "b1"}).status == "enqueued"


def test_null_venue_freshness_path(database: Database) -> None:
    """venue_id=None 不影响新鲜度判定：DONE 后 23h→fresh_skip、25h→enqueued。

    _fresh_skip 用 NULL-安全查询（`venue_id IS NULL`），与 COALESCE 去重索引各司其职——
    新鲜度判定从不依赖唯一索引，故 venue-less 的 fresh_skip/enqueued 分支同样正确。
    """
    clock = FakeClock(datetime(2026, 1, 1, tzinfo=UTC))
    queue = TaskQueue(database, clock=clock)
    queue.enqueue("discover", None, {"since": "2024"})
    done_id = _drain_to_done(queue)
    clock.advance(timedelta(hours=23))
    fresh = queue.enqueue("discover", None, {"since": "2024"})
    assert fresh.status == "fresh_skip"
    assert fresh.task_id == done_id
    clock.advance(timedelta(hours=2))  # 累计 25h，越过 discover 24h 窗口
    assert queue.enqueue("discover", None, {"since": "2024"}).status == "enqueued"


def test_force_bypasses_fresh_skip(database: Database) -> None:
    """force=True 绕过 fresh_skip：新鲜 DONE 存在仍新建 PENDING。"""
    clock = FakeClock(datetime(2026, 1, 1, tzinfo=UTC))
    queue = TaskQueue(database, clock=clock)
    queue.enqueue("discover", "jfe", {"since": "2024"})
    done_id = _drain_to_done(queue)
    clock.advance(timedelta(hours=1))
    result = queue.enqueue("discover", "jfe", {"since": "2024"}, force=True)
    assert result.status == "enqueued"
    assert result.task_id != done_id


def test_force_does_not_bypass_duplicate(queue: TaskQueue) -> None:
    """force=True 不绕过 duplicate：同键活跃任务仍在 → duplicate。"""
    first = queue.enqueue("enumerate", "jfe", {"volume": "160"})
    result = queue.enqueue("enumerate", "jfe", {"volume": "160"}, force=True)
    assert result.status == "duplicate"
    assert result.task_id == first.task_id


def test_enqueue_null_venue_active_duplicate(queue: TaskQueue) -> None:
    """venue_id=None 同键活跃任务判 duplicate（COALESCE 索引归一 NULL；C1 仲裁方案 a）。"""
    first = queue.enqueue("ingest", None, {"batch": "b1"})
    second = queue.enqueue("ingest", None, {"batch": "b1"})
    assert second.status == "duplicate"
    assert second.task_id == first.task_id


def test_enqueue_bad_parent_id_raises_not_masked_as_duplicate(queue: TaskQueue) -> None:
    """不存在的 parent_id → 外键 IntegrityError 不被吞成 duplicate（原样抛出）。"""
    import sqlite3

    with pytest.raises(sqlite3.IntegrityError):
        queue.enqueue("fetch", "jfe", {"asset": 1}, parent_id="01NONEXISTENTPARENT000000")


def test_enqueue_records_parent_id(queue: TaskQueue) -> None:
    """合法 parent_id 落库（级联展开溯源）。"""
    parent = queue.enqueue("pull", "jfe", {"volume": "1"})
    assert parent.task_id is not None
    child = queue.enqueue("fetch", "jfe", {"asset": 1}, parent_id=parent.task_id)
    assert child.task_id is not None
    row = queue.get(child.task_id)
    assert row is not None
    assert row["parent_id"] == parent.task_id


# ---------------------------------------------------------------------------
# claim_next
# ---------------------------------------------------------------------------


def test_claim_next_empty_returns_none(queue: TaskQueue) -> None:
    assert queue.claim_next() is None


def test_claim_next_fifo_oldest_first(database: Database) -> None:
    """FIFO：按 created_at 领取最老 PENDING。"""
    clock = FakeClock(datetime(2026, 1, 1, tzinfo=UTC))
    queue = TaskQueue(database, clock=clock)
    a = queue.enqueue("fetch", "jfe", {"n": 1})
    clock.advance(timedelta(seconds=1))
    b = queue.enqueue("fetch", "jfe", {"n": 2})
    clock.advance(timedelta(seconds=1))
    c = queue.enqueue("fetch", "jfe", {"n": 3})
    claimed_ids = [str(queue.claim_next()["id"]) for _ in range(3)]  # type: ignore[index]
    assert claimed_ids == [a.task_id, b.task_id, c.task_id]


def test_claim_next_transitions_to_running(queue: TaskQueue) -> None:
    queue.enqueue("fetch", "jfe", {"n": 1})
    claimed = queue.claim_next()
    assert claimed is not None
    assert claimed["state"] == "RUNNING"
    # 已领取的不再是 PENDING → 队列空
    assert queue.claim_next() is None


# ---------------------------------------------------------------------------
# fail：RETRY_TABLE 处置
# ---------------------------------------------------------------------------


def _claim(queue: TaskQueue) -> str:
    claimed = queue.claim_next()
    assert claimed is not None
    return str(claimed["id"])


def test_fail_transient_retries_three_then_failed(queue: TaskQueue) -> None:
    """TRANSIENT RetrySpec(4)：3 次回 PENDING，第 4 次落 FAILED（含首次共 4 次尝试）。"""
    queue.enqueue("fetch", "jfe", {"n": 1})
    outcomes: list[str] = []
    for _ in range(4):
        task_id = _claim(queue)
        outcomes.append(queue.fail(task_id, ErrorClass.TRANSIENT, "5xx"))
    assert outcomes == ["PENDING", "PENDING", "PENDING", "FAILED"]
    row = queue.get(task_id)
    assert row is not None
    assert row["state"] == "FAILED"
    assert row["attempts"] == 4
    assert row["error_class"] == "transient"
    assert row["last_error"] == "5xx"


def test_fail_redacts_credentials_before_persisting(queue: TaskQueue) -> None:
    """`last_error` 是**持久化 + 直印**面（`crawler status --failed`）：凭证形态先脱敏。

    R1 审查 P2-2（第四 sink）：异常串会内联 URL（如浏览器导航失败），F-1 接线后那条
    URL 可能带一次性签名 token；`runner._route_error(str(exc))` → 本方法 → `task.last_error`
    → CLI 明文直印。脱敏落在**持久化边界**（同 `repo.add_fetch_log` 款式）。
    """
    queue.enqueue("fetch", "jfe", {"n": 1})
    task_id = _claim(queue)
    queue.fail(
        task_id,
        ErrorClass.TRANSIENT,
        "浏览器导航无响应: https://h.test/Delivery.cfm/x.pdf?abstractid=1&signature=SEKRET123456",
    )
    row = queue.get(task_id)
    assert row is not None
    last_error = str(row["last_error"])
    assert "SEKRET123456" not in last_error
    assert "signature=***" in last_error
    assert "abstractid=1" in last_error  # 非凭证段保留（脱敏不毁可诊断性）


def test_block_redacts_credentials_before_persisting(queue: TaskQueue) -> None:
    """`blocked_reason` 同为持久化 + 直印面（`crawler status --blocked`）。"""
    queue.enqueue("fetch", "jfe", {"n": 1})
    task_id = _claim(queue)
    queue.block(task_id, "browser-fetch 停手: 导航 https://h.test/x.pdf?access_token=SEKRET123456")
    row = queue.get(task_id)
    assert row is not None
    reason = str(row["blocked_reason"])
    assert "SEKRET123456" not in reason
    assert "access_token=***" in reason


def test_fail_rate_limited_never_counts_attempts(queue: TaskQueue) -> None:
    """RATE_LIMITED 不计 attempts：多次失败仍 PENDING，attempts 恒为 0。"""
    queue.enqueue("fetch", "jfe", {"n": 1})
    for _ in range(5):
        task_id = _claim(queue)
        assert queue.fail(task_id, ErrorClass.RATE_LIMITED, "429") == "PENDING"
    row = queue.get(task_id)
    assert row is not None
    assert row["state"] == "PENDING"
    assert row["attempts"] == 0


def test_fail_rate_limited_does_not_consume_transient_budget(queue: TaskQueue) -> None:
    """混合：RATE_LIMITED 夹在 TRANSIENT 之间不消耗预算，attempts 只随 TRANSIENT 增长。"""
    queue.enqueue("fetch", "jfe", {"n": 1})
    seq = [
        (ErrorClass.TRANSIENT, "PENDING"),
        (ErrorClass.RATE_LIMITED, "PENDING"),
        (ErrorClass.TRANSIENT, "PENDING"),
        (ErrorClass.RATE_LIMITED, "PENDING"),
        (ErrorClass.TRANSIENT, "PENDING"),
        (ErrorClass.TRANSIENT, "FAILED"),  # 第 4 次 TRANSIENT → attempts=4 → FAILED
    ]
    for error_class, expected in seq:
        task_id = _claim(queue)
        assert queue.fail(task_id, error_class, "x") == expected
    row = queue.get(task_id)
    assert row is not None
    assert row["attempts"] == 4


def test_fail_unlisted_class_fails_immediately(queue: TaskQueue) -> None:
    """未列入 RETRY_TABLE 的类默认 RetrySpec(1)：首次失败即 FAILED。"""
    queue.enqueue("enumerate", "jfe", {"v": 1})
    task_id = _claim(queue)
    assert queue.fail(task_id, ErrorClass.PARSE, "0 hits") == "FAILED"
    row = queue.get(task_id)
    assert row is not None
    assert row["attempts"] == 1
    assert row["error_class"] == "parse"


def test_fail_integrity_retries_once(queue: TaskQueue) -> None:
    """INTEGRITY RetrySpec(2)：1 次回 PENDING，第 2 次 FAILED。"""
    queue.enqueue("fetch", "jfe", {"n": 1})
    assert queue.fail(_claim(queue), ErrorClass.INTEGRITY, "bad magic") == "PENDING"
    assert queue.fail(_claim(queue), ErrorClass.INTEGRITY, "bad magic") == "FAILED"


# ---------------------------------------------------------------------------
# block / resume
# ---------------------------------------------------------------------------


def test_block_does_not_touch_attempts(queue: TaskQueue) -> None:
    """block 不动 attempts（design/05 §2：BLOCKED 不占重试次数）。"""
    queue.enqueue("fetch", "jfe", {"n": 1})
    task_id = _claim(queue)
    queue.fail(task_id, ErrorClass.TRANSIENT, "5xx")  # attempts=1 → PENDING
    task_id = _claim(queue)  # 再领取 → RUNNING
    queue.block(task_id, "auth login elsevier")
    row = queue.get(task_id)
    assert row is not None
    assert row["state"] == "BLOCKED"
    assert row["attempts"] == 1  # 未变
    assert row["blocked_reason"] == "auth login elsevier"


def test_resume_single(queue: TaskQueue) -> None:
    queue.enqueue("fetch", "jfe", {"n": 1})
    task_id = _claim(queue)
    queue.block(task_id, "why")
    assert queue.resume(task_id) == 1
    row = queue.get(task_id)
    assert row is not None
    assert row["state"] == "PENDING"
    assert row["blocked_reason"] is None  # resume 清空阻塞原因


def test_resume_all_blocked(queue: TaskQueue) -> None:
    """resume(all_blocked=True) 恢复全部 BLOCKED，返回恢复数。"""
    ids: list[str] = []
    for n in range(3):
        queue.enqueue("fetch", "jfe", {"n": n})
    for _ in range(3):
        task_id = _claim(queue)
        queue.block(task_id, "why")
        ids.append(task_id)
    assert queue.resume(all_blocked=True) == 3
    for task_id in ids:
        row = queue.get(task_id)
        assert row is not None
        assert row["state"] == "PENDING"


def test_resume_all_blocked_only_counts_blocked(queue: TaskQueue) -> None:
    """all_blocked 只影响 BLOCKED：另有 PENDING/DONE 不受牵连，计数仅含 BLOCKED。"""
    queue.enqueue("fetch", "jfe", {"n": 0})  # 留在 PENDING
    queue.enqueue("fetch", "jfe", {"n": 1})
    blocked_id = _claim(queue)
    queue.block(blocked_id, "why")
    assert queue.resume(all_blocked=True) == 1


def test_resume_requires_target(queue: TaskQueue) -> None:
    """既未给 task_id 也未 all_blocked → ValueError。"""
    with pytest.raises(ValueError, match="task_id"):
        queue.resume()


# ---------------------------------------------------------------------------
# retry_failed
# ---------------------------------------------------------------------------


def _fail_to_terminal(queue: TaskQueue, error_class: ErrorClass) -> str:
    """把一个任务打到 FAILED 终态，返回其 id。"""
    task_id = _claim(queue)
    state = queue.fail(task_id, error_class, "x")
    while state == "PENDING":
        task_id = _claim(queue)
        state = queue.fail(task_id, error_class, "x")
    return task_id


def test_retry_failed_all(queue: TaskQueue) -> None:
    """retry_failed() 无过滤：全部 FAILED → PENDING，返回重试数。"""
    queue.enqueue("enumerate", "jfe", {"v": 1})
    queue.enqueue("enumerate", "jfe", {"v": 2})
    a = _fail_to_terminal(queue, ErrorClass.PARSE)
    b = _fail_to_terminal(queue, ErrorClass.PARSE)
    assert queue.retry_failed() == 2
    for task_id in (a, b):
        row = queue.get(task_id)
        assert row is not None
        assert row["state"] == "PENDING"


def test_retry_failed_filters_by_class(queue: TaskQueue) -> None:
    """retry_failed(error_class=X) 只重试该类，其余保持 FAILED。"""
    queue.enqueue("enumerate", "jfe", {"v": 1})
    queue.enqueue("fetch", "jfe", {"n": 1})
    parse_id = _fail_to_terminal(queue, ErrorClass.PARSE)
    transient_id = _fail_to_terminal(queue, ErrorClass.TRANSIENT)
    assert queue.retry_failed(error_class=ErrorClass.TRANSIENT) == 1
    transient_row = queue.get(transient_id)
    parse_row = queue.get(parse_id)
    assert transient_row is not None and transient_row["state"] == "PENDING"
    assert parse_row is not None and parse_row["state"] == "FAILED"


def test_retry_failed_resets_attempts(queue: TaskQueue) -> None:
    """retry_failed 重置 attempts=0，使重试后拿到完整重试预算。"""
    queue.enqueue("fetch", "jfe", {"n": 1})
    task_id = _fail_to_terminal(queue, ErrorClass.TRANSIENT)  # attempts=4
    queue.retry_failed()
    row = queue.get(task_id)
    assert row is not None
    assert row["attempts"] == 0


def test_retry_failed_none_matched_returns_zero(queue: TaskQueue) -> None:
    queue.enqueue("enumerate", "jfe", {"v": 1})
    _fail_to_terminal(queue, ErrorClass.PARSE)
    assert queue.retry_failed(error_class=ErrorClass.TRANSIENT) == 0


# ---------------------------------------------------------------------------
# get / by_state
# ---------------------------------------------------------------------------


def test_get_missing_returns_none(queue: TaskQueue) -> None:
    assert queue.get("01NOPENOPENOPENOPENOPE0000") is None


def test_by_state_lists_and_orders(database: Database) -> None:
    """by_state 列出目标状态任务，按 created_at 稳定排序。"""
    clock = FakeClock(datetime(2026, 1, 1, tzinfo=UTC))
    queue = TaskQueue(database, clock=clock)
    order: list[str] = []
    for n in range(3):
        order.append(str(queue.enqueue("fetch", "jfe", {"n": n}).task_id))
        clock.advance(timedelta(seconds=1))
    pending = queue.by_state("PENDING")
    assert [str(r["id"]) for r in pending] == order
    # claim 一个后，PENDING 少一，RUNNING 多一
    queue.claim_next()
    assert len(queue.by_state("PENDING")) == 2
    assert len(queue.by_state("RUNNING")) == 1


# ---------------------------------------------------------------------------
# recover_running（崩溃恢复；2026-07-21 T7c 仲裁增补的冻结件 §2.5 扩充）
# ---------------------------------------------------------------------------


def test_recover_running_returns_zero_when_no_running(queue: TaskQueue) -> None:
    queue.enqueue("discover", "jfe", {})  # PENDING，不受影响
    assert queue.recover_running() == 0


def test_recover_running_requeues_without_touching_attempts(queue: TaskQueue) -> None:
    """RUNNING→PENDING；attempts 与 error_class 均不动（崩溃不是失败，不耗重试预算）。"""
    task_id = str(queue.enqueue("fetch", "jfe", {"asset": "a1"}).task_id)
    assert queue.claim_next() is not None
    # 先经历一次退避（attempts=1 回 PENDING）再领取——模拟带预算痕迹的崩溃现场
    assert queue.fail(task_id, ErrorClass.TRANSIENT, "boom") == "PENDING"
    claimed = queue.claim_next()
    assert claimed is not None and str(claimed["state"]) == "RUNNING"

    assert queue.recover_running() == 1

    row = queue.get(task_id)
    assert row is not None
    assert row["state"] == "PENDING"
    assert row["attempts"] == 1  # 不动 attempts
    assert row["error_class"] == "transient"  # 不动 error_class（保留崩溃前诊断）


def test_recover_running_leaves_other_states_untouched(queue: TaskQueue) -> None:
    """只动 RUNNING：DONE/BLOCKED/PENDING 原样保持。"""
    done_id = str(queue.enqueue("discover", "jfe", {}).task_id)
    assert queue.claim_next() is not None
    queue.complete(done_id)

    blocked_id = str(queue.enqueue("fetch", "jfe", {"asset": "b"}).task_id)
    assert queue.claim_next() is not None
    queue.block(blocked_id, "auth")

    running_id = str(queue.enqueue("fetch", "jfe", {"asset": "d"}).task_id)
    assert queue.claim_next() is not None  # 领取的是当下唯一 PENDING（"d"）

    pending_id = str(queue.enqueue("fetch", "jfe", {"asset": "c"}).task_id)

    assert queue.recover_running() == 1

    states = {
        task_id: str(row["state"])
        for task_id in (done_id, blocked_id, running_id, pending_id)
        if (row := queue.get(task_id)) is not None
    }
    assert states == {
        done_id: "DONE",
        blocked_id: "BLOCKED",
        running_id: "PENDING",
        pending_id: "PENDING",
    }
