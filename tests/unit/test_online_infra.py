"""在线测试基建的元测试（T3）：验证 pytest `online` marker 的默认排除机制真实
生效，以及 `real_request_budget` 预算护栏的超限 fail 路径。

全部离线：marker 元测试用子进程跑 `pytest --collect-only`/`-m online`（只收集
或跑 `tests/online/` 下的占位用例，占位用例本身零网络）；预算护栏测试直接
构造 `RealRequestBudget`（用假计数演练超限路径，不经真实 pytest fixture 机制、
不发任何请求）。这些测试属于"验证机制本身"的 T1 类单测，因此放在
`tests/unit/`（每次提交都跑），不是 T5 在线冒烟本身。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from online.conftest import RealRequestBudget

REPO_ROOT = Path(__file__).resolve().parents[2]
_PLACEHOLDER_NODE_ID = (
    "tests/online/test_infra_placeholder.py::test_placeholder_online_marker_usage"
)


def _run_pytest(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "pytest", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )


# --- marker 默认排除：collect-only 断言 ---------------------------------------


def test_online_marker_excluded_from_default_collection() -> None:
    """默认 addopts（`-m "not online"`，pyproject.toml）下，online 占位用例不在收集结果里。"""
    result = _run_pytest("--collect-only", "-q", "tests/online")
    output = result.stdout + result.stderr
    assert _PLACEHOLDER_NODE_ID not in output


def test_online_marker_included_when_explicitly_requested() -> None:
    """显式 `-m online` 能收集到——证明默认排除是 marker 过滤生效，不是用例本身收集失败。

    命令行追加的 `-m online` 覆盖 addopts 里的默认值 `-m "not online"`
    （pytest 标准语义：同名选项以最后一次出现为准）。
    """
    result = _run_pytest("--collect-only", "-q", "-m", "online", "tests/online")
    output = result.stdout + result.stderr
    assert _PLACEHOLDER_NODE_ID in output


def test_online_placeholder_actually_passes_under_explicit_flag() -> None:
    """不只是"被收集"——显式 `-m online` 时占位用例也能真正跑通（验证 fixture 装配无误：
    `real_request_budget` 正确读到模块的 `MAX_REAL_REQUESTS` 并构造出句柄）。
    """
    result = _run_pytest("-q", "-m", "online", "tests/online")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "1 passed" in result.stdout


# --- real_request_budget：超限 fail 路径（假计数演练） -------------------------


def test_spend_within_budget_does_not_fail() -> None:
    budget = RealRequestBudget("fake.module", max_requests=3, tracker={})
    budget.spend(1)
    budget.spend(2)
    assert budget.spent == 3
    assert budget.remaining == 0


def test_spend_exceeding_budget_raises_pytest_fail_with_hint_text() -> None:
    budget = RealRequestBudget("fake.module", max_requests=2, tracker={})
    budget.spend(2)

    with pytest.raises(pytest.fail.Exception) as exc_info:
        budget.spend(1)

    message = str(exc_info.value)
    assert "fake.module" in message
    assert "MAX_REAL_REQUESTS=2" in message
    assert "3" in message  # 已花费次数（2 已花 + 本次 1）


def test_spend_stops_incrementing_the_caller_visible_state_correctly_after_failure() -> None:
    """超限那一次 spend() 的记账仍然发生（`.spent` 反映真实已花费，不因失败回滚）——
    这样下次调用方查 `.remaining` 能看到负数，符合"已经超支"的语义，不会误报还有余量。
    """
    budget = RealRequestBudget("fake.module", max_requests=1, tracker={})
    budget.spend(1)
    with pytest.raises(pytest.fail.Exception):
        budget.spend(1)
    assert budget.spent == 2
    assert budget.remaining == -1


def test_single_spend_call_exceeding_budget_in_one_shot_also_fails() -> None:
    budget = RealRequestBudget("fake.module", max_requests=5, tracker={})
    with pytest.raises(pytest.fail.Exception):
        budget.spend(6)


def test_budget_shared_across_instances_pointing_at_the_same_tracker_and_module() -> None:
    """模拟同一在线测试文件内多个测试函数共享 session 级计数：两个各自构造的
    `RealRequestBudget`（同 module_name、同 tracker dict）会把花费累加到一起。
    """
    tracker: dict[str, int] = {}
    first = RealRequestBudget("fake.module", max_requests=3, tracker=tracker)
    second = RealRequestBudget("fake.module", max_requests=3, tracker=tracker)

    first.spend(2)
    assert second.spent == 2  # 第二个句柄能看到第一个句柄记的账

    with pytest.raises(pytest.fail.Exception):
        second.spend(2)  # 2 + 2 = 4 > 3，即使 second 自己只调用过一次 spend()


def test_budget_for_a_different_module_name_does_not_share_spend() -> None:
    tracker: dict[str, int] = {}
    RealRequestBudget("module.a", max_requests=1, tracker=tracker).spend(1)
    other = RealRequestBudget("module.b", max_requests=1, tracker=tracker)
    assert other.spent == 0  # 不同模块名各自记账，互不干扰
    other.spend(1)  # 不应超限
