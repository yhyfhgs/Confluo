"""在线测试基建占位用例（T3）。

真正会发真实请求的冒烟测试从 T7（arxiv）起陆续加入（如
`tests/online/test_arxiv_smoke.py`）。这个占位文件只用来：

1. 示范 `MAX_REAL_REQUESTS` + `real_request_budget` fixture 的标准写法；
2. 给 `tests/unit/test_online_infra.py` 的 marker 默认排除元测试一个真实存在、
   打了 `online` 标记的用例作为断言对象。

`MAX_REAL_REQUESTS = 0`——本用例不发起任何真实请求，因此从不调用
`real_request_budget.spend()`；默认 `-m "not online"` 下不会执行，显式
`-m online` 跑到时也只是一次不消耗预算的空操作。
"""

from __future__ import annotations

import pytest

from online.conftest import RealRequestBudget

MAX_REAL_REQUESTS = 0  # 占位：不发起任何真实请求


@pytest.mark.online
def test_placeholder_online_marker_usage(real_request_budget: RealRequestBudget) -> None:
    """占位：证明 online 标记 + 预算 fixture 的写法，不做真实网络调用。"""
    assert real_request_budget.max_requests == 0
    assert real_request_budget.spent == 0
    # 真正的在线测试会在这里调用 real_request_budget.spend(1) 再发请求；
    # 本占位测试预算为 0，从不调用 spend()。
