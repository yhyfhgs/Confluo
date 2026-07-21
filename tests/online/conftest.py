"""在线测试（T5）的真实请求预算护栏（T3 落地；design phase2-implementation-plan §2.3）。

**用法**（在具体在线测试文件顶部）：

```python
import pytest

MAX_REAL_REQUESTS = 3  # 本文件全部在线测试合计允许发起的真实请求数上限

@pytest.mark.online
def test_xxx(real_request_budget: RealRequestBudget) -> None:
    real_request_budget.spend(1)   # 每次真实网络请求前先记账
    response = http_client.get_text(url)
    ...
```

**机制**：`real_request_budget` fixture 读取当前测试模块顶层声明的
`MAX_REAL_REQUESTS`，返回一个绑定到该模块名的 `RealRequestBudget` 句柄。真正的
计数存储（`_real_request_spend_tracker`）是 **session 级** fixture——整个
pytest 会话共享同一份计数字典，因此：

- 同一文件内多个测试函数依次调用 `.spend()`，花费按模块名累加，不会因为
  `real_request_budget` 本身是 function-scope（每个测试函数各拿一个新句柄）
  而被重置；
- 超出该文件声明的 `MAX_REAL_REQUESTS` 时，`.spend()` 立即 `pytest.fail`
  （`pytrace=False`——这是护栏生效，不是被测代码本身的 bug，不需要贴一段无关的
  fixture 内部调用栈）。

本文件与其中的 `RealRequestBudget` 类只建机制、不写任何真实在线测试（那是
T7 起各 adapter 的 `tests/online/test_<adapter>_smoke.py` 的职责）；机制自身的
自测（超限 fail 路径、marker 默认排除）见 `tests/unit/test_online_infra.py`
（离线，`RealRequestBudget` 可脱离 pytest fixture 机制直接构造，用假计数演练）。
"""

from __future__ import annotations

import pytest


class RealRequestBudget:
    """单个测试模块视角下的真实请求预算句柄。

    `tracker` 是调用方注入的共享计数字典（`module_name -> 已花费次数`），
    使得多个 `RealRequestBudget` 实例（不同测试函数各自拿到的 fixture 值）在
    指向同一模块名时共享同一份计费——这就是模块 docstring 里"session 级共享
    计数"的具体实现：`tracker` 本身来自 session-scope fixture，`RealRequestBudget`
    实例才是每次 function-scope 重新构造的轻量视图。
    """

    def __init__(self, module_name: str, max_requests: int, tracker: dict[str, int]) -> None:
        self._module_name = module_name
        self._max_requests = max_requests
        self._tracker = tracker

    @property
    def max_requests(self) -> int:
        return self._max_requests

    @property
    def spent(self) -> int:
        return self._tracker.get(self._module_name, 0)

    @property
    def remaining(self) -> int:
        return self._max_requests - self.spent

    def spend(self, n: int = 1) -> None:
        """记账 n 次真实请求；超出本文件声明的 `MAX_REAL_REQUESTS` 立即 `pytest.fail`。"""
        spent = self._tracker.get(self._module_name, 0) + n
        self._tracker[self._module_name] = spent
        if spent > self._max_requests:
            pytest.fail(
                f"real_request_budget 超限：{self._module_name} 声明 "
                f"MAX_REAL_REQUESTS={self._max_requests}，已花费 {spent} 次真实请求"
                f"（本次 +{n}）。请检查该在线测试是否发起了多余的真实网络请求，"
                "或该预算声明是否需要上调。",
                pytrace=False,
            )


@pytest.fixture(scope="session")
def _real_request_spend_tracker() -> dict[str, int]:
    """整个 pytest 会话共享的花费计数存储（module_name -> 已花费次数）。"""
    return {}


@pytest.fixture
def real_request_budget(
    request: pytest.FixtureRequest, _real_request_spend_tracker: dict[str, int]
) -> RealRequestBudget:
    """当前测试模块的预算句柄；要求模块顶层已声明 `MAX_REAL_REQUESTS = N`。"""
    max_requests = getattr(request.module, "MAX_REAL_REQUESTS", None)
    if max_requests is None:
        pytest.fail(
            f"{request.module.__name__} 使用了 real_request_budget fixture，"
            "但未在文件顶部声明 `MAX_REAL_REQUESTS = N`。",
            pytrace=False,
        )
    return RealRequestBudget(
        module_name=request.module.__name__,
        max_requests=max_requests,
        tracker=_real_request_spend_tracker,
    )
