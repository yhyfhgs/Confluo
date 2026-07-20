"""ratelimit.py（接口冻结件 §2.6）单测：token bucket 数学、register/override 保守取值、fail-fast。

覆盖点：连续 acquire 排队累加、burst 容量、scale 缩放、多 domain 独立、
未注册 domain fail-fast。
"""

import time

import pytest

from paper_crawler.errors import CrawlerError, ErrorClass
from paper_crawler.ratelimit import RateLimiter
from paper_crawler.types import RatePolicy


class FakeClock:
    """手动前进的假时钟（monotonic 风格，只在测试里显式 advance）。"""

    def __init__(self, start: float = 0.0) -> None:
        self._now = start

    def __call__(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds


def test_acquire_queues_and_accumulates_wait_with_frozen_clock() -> None:
    """rpm=60/burst=1，时钟不动：连续三次 acquire 返回 ≈0.0/1.0/2.0（预登记消费排队累加）。"""
    clock = FakeClock()
    limiter = RateLimiter(clock=clock)
    limiter.register("mock.local", RatePolicy(requests_per_minute=60, burst=1))

    waits = [limiter.acquire("mock.local") for _ in range(3)]

    assert waits[0] == pytest.approx(0.0, abs=1e-9)
    assert waits[1] == pytest.approx(1.0, abs=1e-9)
    assert waits[2] == pytest.approx(2.0, abs=1e-9)


def test_acquire_after_clock_advance_returns_zero_wait() -> None:
    """消费掉初始 burst token 后，时钟前进 1.5s（足够再生 1 个 token）：下次 acquire 立即可用。"""
    clock = FakeClock()
    limiter = RateLimiter(clock=clock)
    limiter.register("mock.local", RatePolicy(requests_per_minute=60, burst=1))

    first = limiter.acquire("mock.local")
    clock.advance(1.5)
    second = limiter.acquire("mock.local")

    assert first == pytest.approx(0.0, abs=1e-9)
    assert second == pytest.approx(0.0, abs=1e-9)


def test_acquire_partial_wait_when_time_advance_insufficient() -> None:
    """时钟只前进一部分：欠账应等比例减少，而不是直接清零或保持不变。"""
    clock = FakeClock()
    limiter = RateLimiter(clock=clock)
    limiter.register("mock.local", RatePolicy(requests_per_minute=60, burst=1))

    limiter.acquire("mock.local")  # 消费初始 token → 欠账 0
    limiter.acquire("mock.local")  # 立即再要 1 个 → 欠账 1.0s
    clock.advance(0.4)
    third = limiter.acquire("mock.local")

    # 两次欠账共 2.0s；已被 0.4s 时间抵消，第三次调用再欠 1.0s；总剩余 1.6s。
    assert third == pytest.approx(1.6, abs=1e-9)


def test_burst_allows_immediate_consumption_up_to_capacity() -> None:
    """burst=3：前 3 次立即可用，第 4 次才需要等待。"""
    clock = FakeClock()
    limiter = RateLimiter(clock=clock)
    limiter.register("mock.local", RatePolicy(requests_per_minute=60, burst=3))

    waits = [limiter.acquire("mock.local") for _ in range(3)]

    assert waits == [pytest.approx(0.0, abs=1e-9)] * 3
    assert limiter.acquire("mock.local") == pytest.approx(1.0, abs=1e-9)


def test_scale_slows_down_effective_rate() -> None:
    """scale=0.5 应使补充 1 个 token 所需时间加倍。"""
    clock = FakeClock()
    limiter = RateLimiter(scale=0.5, clock=clock)
    limiter.register("mock.local", RatePolicy(requests_per_minute=60, burst=1))

    limiter.acquire("mock.local")  # 消费初始 token
    second = limiter.acquire("mock.local")

    assert second == pytest.approx(2.0, abs=1e-9)


def test_domains_are_independent_buckets() -> None:
    clock = FakeClock()
    limiter = RateLimiter(clock=clock)
    limiter.register("a.example", RatePolicy(requests_per_minute=60, burst=1))
    limiter.register("b.example", RatePolicy(requests_per_minute=60, burst=1))

    limiter.acquire("a.example")  # 耗尽 a 的 token，不应影响 b

    assert limiter.acquire("b.example") == pytest.approx(0.0, abs=1e-9)


def test_register_repeated_takes_more_conservative_smaller_rpm() -> None:
    """design/05 §3"最保守值"：重复 register 同 domain 取更小 rpm，且单调不放宽。"""
    limiter = RateLimiter(clock=FakeClock())
    limiter.register("mock.local", RatePolicy(requests_per_minute=100, burst=1))
    limiter.register("mock.local", RatePolicy(requests_per_minute=30, burst=1))

    assert limiter.effective_rpm("mock.local") == 30

    limiter.register("mock.local", RatePolicy(requests_per_minute=200, burst=1))
    assert limiter.effective_rpm("mock.local") == 30


def test_register_repeated_takes_more_conservative_smaller_burst() -> None:
    """design/05 §3"最保守值"仲裁（2026-07-21）：burst 与 rpm 同理取更小值，且单调不放宽。"""
    clock = FakeClock()
    limiter = RateLimiter(clock=clock)
    limiter.register("mock.local", RatePolicy(requests_per_minute=60, burst=5))
    limiter.register("mock.local", RatePolicy(requests_per_minute=60, burst=2))

    # 有效容量应为较小者 2，而不是首次注册的 5：前 2 次立即可用，第 3 次需等待。
    waits = [limiter.acquire("mock.local") for _ in range(2)]
    assert waits == [pytest.approx(0.0, abs=1e-9)] * 2
    assert limiter.acquire("mock.local") == pytest.approx(1.0, abs=1e-9)

    # 之后再注册一个更大的 burst 不应放宽已生效的更保守容量（单调不增）。
    limiter.register("mock.local", RatePolicy(requests_per_minute=60, burst=10))
    clock.advance(10.0)  # 让 token 完全恢复
    waits_after = [limiter.acquire("mock.local") for _ in range(2)]
    assert waits_after == [pytest.approx(0.0, abs=1e-9)] * 2
    assert limiter.acquire("mock.local") == pytest.approx(1.0, abs=1e-9)


def test_override_takes_min_with_current_effective_rpm() -> None:
    limiter = RateLimiter(clock=FakeClock())
    limiter.register("mock.local", RatePolicy(requests_per_minute=60, burst=1))

    limiter.override("mock.local", 10)
    assert limiter.effective_rpm("mock.local") == 10

    limiter.override("mock.local", 500)
    assert limiter.effective_rpm("mock.local") == 10


def test_acquire_on_unregistered_domain_raises_config_error() -> None:
    """未注册 domain 的 acquire 必须 fail fast，防止绕过限速。"""
    limiter = RateLimiter(clock=FakeClock())

    with pytest.raises(CrawlerError) as exc_info:
        limiter.acquire("unknown.example")

    assert exc_info.value.error_class is ErrorClass.CONFIG


def test_effective_rpm_on_unregistered_domain_raises_config_error() -> None:
    limiter = RateLimiter(clock=FakeClock())

    with pytest.raises(CrawlerError) as exc_info:
        limiter.effective_rpm("unknown.example")

    assert exc_info.value.error_class is ErrorClass.CONFIG


def test_override_on_unregistered_domain_raises_config_error() -> None:
    limiter = RateLimiter(clock=FakeClock())

    with pytest.raises(CrawlerError) as exc_info:
        limiter.override("unknown.example", 10)

    assert exc_info.value.error_class is ErrorClass.CONFIG


def test_default_clock_is_time_monotonic() -> None:
    """未注入 clock 时应使用 time.monotonic（默认参数）；高速率高 burst 下首次 acquire 立即可用。"""
    limiter = RateLimiter()
    limiter.register("mock.local", RatePolicy(requests_per_minute=6000, burst=100))

    assert limiter.acquire("mock.local") == pytest.approx(0.0, abs=1e-6)
    assert callable(time.monotonic)


def test_acquire_with_zero_rate_returns_infinite_wait_instead_of_dividing_by_zero() -> None:
    """rpm=0（或 scale=0）时速率为 0：欠账无法被时间抵消，需返回 inf 而不是 ZeroDivisionError。"""
    clock = FakeClock()
    limiter = RateLimiter(clock=clock)
    limiter.register("mock.local", RatePolicy(requests_per_minute=0, burst=1))

    limiter.acquire("mock.local")  # 消费唯一的初始 token → 0.0
    second = limiter.acquire("mock.local")

    assert second == float("inf")
