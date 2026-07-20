"""任务状态机转移测试（phase1-plan Task 5；Refs: FR-10, AC-1.3, AC-1.5）。

覆盖 design/05 §8"状态机转移全覆盖（含非法转移拒绝）"：
- `validate_transition` 的 5×5 全枚举矩阵（25 组），合法边通过、其余 raise IllegalTransition；
- 经 TaskQueue 的端到端转移：合法生命周期贯通，非法源状态被各变更方法拒绝。
"""

from __future__ import annotations

import itertools
from collections.abc import Iterator
from pathlib import Path

import pytest

from paper_crawler.errors import ErrorClass, IllegalTransition
from paper_crawler.storage.db import Database
from paper_crawler.tasks import (
    LEGAL_TRANSITIONS,
    TASK_STATES,
    TaskQueue,
    validate_transition,
)

# 接口冻结件 §2.5 逐条枚举的合法边共 7 条（PENDING→RUNNING; RUNNING→DONE|FAILED|BLOCKED|
# PENDING; FAILED→PENDING; BLOCKED→PENDING）。此常量把"全集"钉死，任何增删都会被本测试捕获。
EXPECTED_LEGAL: frozenset[tuple[str, str]] = frozenset(
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


@pytest.fixture
def queue(tmp_path: Path) -> Iterator[TaskQueue]:
    database = Database(tmp_path / "tasks.sqlite")
    database.migrate()
    yield TaskQueue(database)
    database.close()


# ---------------------------------------------------------------------------
# 纯函数：5×5 全枚举矩阵
# ---------------------------------------------------------------------------


def test_legal_transition_set_is_frozen_at_seven_edges() -> None:
    """合法转移全集恰为接口冻结件枚举的 7 条边（钉死"全集"，防漂移）。"""
    assert LEGAL_TRANSITIONS == EXPECTED_LEGAL
    assert len(LEGAL_TRANSITIONS) == 7


@pytest.mark.parametrize("current,target", list(itertools.product(TASK_STATES, TASK_STATES)))
def test_transition_matrix_full_enumeration(current: str, target: str) -> None:
    """5 状态 × 5 目标全枚举：合法边不抛，其余 18 组一律 IllegalTransition。"""
    if (current, target) in EXPECTED_LEGAL:
        validate_transition(current, target)  # 不抛即通过
    else:
        with pytest.raises(IllegalTransition):
            validate_transition(current, target)


def test_matrix_partition_counts() -> None:
    """矩阵划分口径：25 = 7 合法 + 18 非法。"""
    all_pairs = list(itertools.product(TASK_STATES, TASK_STATES))
    legal = [p for p in all_pairs if p in EXPECTED_LEGAL]
    illegal = [p for p in all_pairs if p not in EXPECTED_LEGAL]
    assert len(all_pairs) == 25
    assert len(legal) == 7
    assert len(illegal) == 18


# ---------------------------------------------------------------------------
# 经队列的端到端：合法生命周期
# ---------------------------------------------------------------------------


def test_lifecycle_pending_running_done(queue: TaskQueue) -> None:
    """PENDING→RUNNING（claim）→DONE（complete）合法贯通。"""
    result = queue.enqueue("discover", "jfe", {"since": "2024"})
    assert result.status == "enqueued"
    claimed = queue.claim_next()
    assert claimed is not None
    assert claimed["state"] == "RUNNING"
    queue.complete(str(claimed["id"]))
    done = queue.get(str(claimed["id"]))
    assert done is not None
    assert done["state"] == "DONE"


def test_lifecycle_running_pending_retry_then_running(queue: TaskQueue) -> None:
    """RUNNING→PENDING（退避重试）后可再次被 claim。"""
    queue.enqueue("fetch", "jfe", {"asset": 1})
    first = queue.claim_next()
    assert first is not None
    assert queue.fail(str(first["id"]), ErrorClass.TRANSIENT, "5xx") == "PENDING"
    again = queue.claim_next()
    assert again is not None
    assert again["id"] == first["id"]
    assert again["state"] == "RUNNING"


def test_lifecycle_blocked_resume(queue: TaskQueue) -> None:
    """RUNNING→BLOCKED（block）→PENDING（resume）合法贯通。"""
    queue.enqueue("fetch", "jfe", {"asset": 2})
    claimed = queue.claim_next()
    assert claimed is not None
    queue.block(str(claimed["id"]), "auth login elsevier")
    blocked = queue.get(str(claimed["id"]))
    assert blocked is not None
    assert blocked["state"] == "BLOCKED"
    assert queue.resume(str(claimed["id"])) == 1
    resumed = queue.get(str(claimed["id"]))
    assert resumed is not None
    assert resumed["state"] == "PENDING"


# ---------------------------------------------------------------------------
# 经队列的端到端：非法源状态被各变更方法拒绝
# ---------------------------------------------------------------------------


def test_complete_rejects_non_running(queue: TaskQueue) -> None:
    """complete 只接受 RUNNING 源；PENDING 上调用即 IllegalTransition。"""
    result = queue.enqueue("discover", "jfe", {"x": 1})
    with pytest.raises(IllegalTransition):
        queue.complete(str(result.task_id))


def test_block_rejects_non_running(queue: TaskQueue) -> None:
    """block 只接受 RUNNING 源；PENDING 上调用即 IllegalTransition。"""
    result = queue.enqueue("discover", "jfe", {"x": 2})
    with pytest.raises(IllegalTransition):
        queue.block(str(result.task_id), "why")


def test_fail_rejects_non_running(queue: TaskQueue) -> None:
    """fail 只接受 RUNNING 源；PENDING 上调用即 IllegalTransition。"""
    result = queue.enqueue("discover", "jfe", {"x": 3})
    with pytest.raises(IllegalTransition):
        queue.fail(str(result.task_id), ErrorClass.TRANSIENT, "boom")


def test_resume_rejects_non_blocked(queue: TaskQueue) -> None:
    """resume 只接受 BLOCKED 源；DONE 任务上调用即 IllegalTransition（DONE→PENDING 非法）。"""
    result = queue.enqueue("discover", "jfe", {"x": 4})
    claimed = queue.claim_next()
    assert claimed is not None
    queue.complete(str(claimed["id"]))
    with pytest.raises(IllegalTransition):
        queue.resume(str(result.task_id))


def test_complete_on_done_rejected(queue: TaskQueue) -> None:
    """DONE→DONE 非法：complete 幂等重放被状态机拒绝。"""
    queue.enqueue("discover", "jfe", {"x": 5})
    claimed = queue.claim_next()
    assert claimed is not None
    queue.complete(str(claimed["id"]))
    with pytest.raises(IllegalTransition):
        queue.complete(str(claimed["id"]))


def test_mutators_raise_on_missing_task(queue: TaskQueue) -> None:
    """对不存在的 task 调用变更方法 → KeyError（先于状态机校验）。"""
    with pytest.raises(KeyError):
        queue.complete("01JUNKULIDDOESNOTEXIST0000")
