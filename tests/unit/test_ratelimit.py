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


# --- alias：多域共享一份预算（C4 红线修复的桶归并语义）------------------------


def test_alias_shares_one_bucket_across_domains() -> None:
    """arxiv 三域共用 1req/3s：对主域与别名域交替 acquire，欠账累加到同一份预算。"""
    clock = FakeClock()
    limiter = RateLimiter(clock=clock)
    limiter.register("export.arxiv.org", RatePolicy(requests_per_minute=60, burst=1))
    limiter.alias("oaipmh.arxiv.org", "export.arxiv.org")
    limiter.alias("arxiv.org", "export.arxiv.org")

    # 时钟不动：主域消费初始 token（0.0），两个别名域各再消费（排队累加 1.0/2.0）——
    # 若三域各自独立成桶则每次都会返回 0.0。
    assert limiter.acquire("export.arxiv.org") == pytest.approx(0.0, abs=1e-9)
    assert limiter.acquire("oaipmh.arxiv.org") == pytest.approx(1.0, abs=1e-9)
    assert limiter.acquire("arxiv.org") == pytest.approx(2.0, abs=1e-9)


def test_alias_reflects_later_tightening_of_canonical_bucket() -> None:
    """别名建立后再 override 主域（收紧），别名域 acquire 也按收紧后的速率排队（同一对象）。"""
    clock = FakeClock()
    limiter = RateLimiter(clock=clock)
    limiter.register("export.arxiv.org", RatePolicy(requests_per_minute=60, burst=1))
    limiter.alias("oaipmh.arxiv.org", "export.arxiv.org")
    limiter.override("export.arxiv.org", 30)  # 收紧到 30rpm=0.5/s

    assert limiter.effective_rpm("oaipmh.arxiv.org") == 30.0
    limiter.acquire("oaipmh.arxiv.org")  # 初始 token → 0.0
    # 30rpm → 0.5 token/s，欠 1 个 token 需 2s。
    assert limiter.acquire("oaipmh.arxiv.org") == pytest.approx(2.0, abs=1e-9)


def test_alias_to_unregistered_canonical_fails_fast() -> None:
    """canonical 未注册即无桶可共享——fail-fast（同 override/acquire 的 CONFIG 口径）。"""
    limiter = RateLimiter(clock=FakeClock())
    with pytest.raises(CrawlerError) as exc_info:
        limiter.alias("oaipmh.arxiv.org", "export.arxiv.org")
    assert exc_info.value.error_class is ErrorClass.CONFIG


# --- effective_rpm 计入 scale（R1b P1-1：观测面此前不反映 scale 缩放后的真实速率）------------


def test_effective_rpm_reflects_scale() -> None:
    """scale=0.5 时 effective_rpm 必须反映真实生效速率（30），而不是裸 rpm（60）。"""
    limiter = RateLimiter(scale=0.5, clock=FakeClock())
    limiter.register("mock.local", RatePolicy(requests_per_minute=60, burst=1))

    assert limiter.effective_rpm("mock.local") == pytest.approx(30.0, abs=1e-9)


def test_effective_rpm_reflects_scale_after_alias_and_override() -> None:
    """register+override+alias 合并后的 rpm 同样按 scale 折算（观测面与实际耗 token 速率一致）。"""
    limiter = RateLimiter(scale=0.5, clock=FakeClock())
    limiter.register("export.arxiv.org", RatePolicy(requests_per_minute=60, burst=1))
    limiter.alias("oaipmh.arxiv.org", "export.arxiv.org")
    limiter.override("export.arxiv.org", 20)

    assert limiter.effective_rpm("oaipmh.arxiv.org") == pytest.approx(10.0, abs=1e-9)


# --- alias 遇 alias_domain 已有独立桶：不覆盖，取更保守值（R1b P1-4；f2_repro.py 场景）--------
#
# 修复前：`self._buckets[alias_domain] = bucket` 无条件覆盖——alias_domain 若已直接
# register/override 过（更严的 rpm）或已积累欠账（更负的 level），会被静默丢弃/清零。
# 与 register()"只会更保守"docstring 对齐：rpm/capacity 取 min，level 取二者中更负值。


def test_alias_keeps_stricter_rpm_when_alias_domain_already_registered() -> None:
    """①先 register(shared,6rpm) 再 alias 到 30rpm 主域 → effective 仍 6（不被放宽到 30）。"""
    clock = FakeClock()
    limiter = RateLimiter(clock=clock)
    limiter.register("shared.example", RatePolicy(requests_per_minute=6, burst=1))
    limiter.register("main.example", RatePolicy(requests_per_minute=30, burst=1))

    limiter.alias("shared.example", "main.example")

    assert limiter.effective_rpm("shared.example") == 6
    # 合并是双向的：main 侧后续 acquire 也应遵守合并后更严的共享桶。
    assert limiter.effective_rpm("main.example") == 6


def test_alias_preserves_debt_when_alias_domain_already_has_bucket() -> None:
    """②欠账 -2.0 后 alias → 下次 acquire 仍需等待（f2_repro.py 场景 A：修复前欠账被清零，
    alias 后立即可用）。全程黑盒——只走公开 API（acquire 返回值间接证明欠账，不碰 _buckets）。
    """
    clock = FakeClock()
    limiter = RateLimiter(clock=clock)
    raw = "raw.githubusercontent.com"
    limiter.register(raw, RatePolicy(requests_per_minute=30, burst=1))
    limiter.alias("aclanthology.org", raw)
    limiter.alias("api.github.com", raw)

    # 时钟不动，30rpm=0.5 token/s，burst=1：连续 3 次 acquire 排队累加 0.0/2.0/4.0（欠账 -2.0）。
    waits = [limiter.acquire(raw) for _ in range(3)]
    assert waits == [pytest.approx(v, abs=1e-9) for v in (0.0, 2.0, 4.0)]

    # 新 venue 的 canonical 域注册后把 raw 别名过去——raw 是 alias_domain 一侧（已有独立桶+欠账）。
    limiter.register("proceedings.mlr.press", RatePolicy(requests_per_minute=30, burst=1))
    limiter.alias(raw, "proceedings.mlr.press")

    # 欠账必须保留（更保守）并继续累加，不能因合并被清零成新桶的满容量（修复前会变回 0.0）。
    assert limiter.acquire(raw) == pytest.approx(6.0, abs=1e-9)
    # 此前已建立的其它别名（aclanthology.org）与 raw 就地合并同一对象，应同步观测到保留
    # 下来的欠账并继续累加，而不是仍停在被丢弃的旧状态。
    assert limiter.acquire("aclanthology.org") == pytest.approx(8.0, abs=1e-9)


def test_alias_repeated_same_pair_is_idempotent() -> None:
    """③重复 alias 同一对不劣化——stages.py route_for 每次调用都会重建 alias（幂等要求）。"""
    clock = FakeClock()
    limiter = RateLimiter(clock=clock)
    limiter.register("export.arxiv.org", RatePolicy(requests_per_minute=60, burst=1))
    limiter.alias("oaipmh.arxiv.org", "export.arxiv.org")

    first_wait = limiter.acquire("oaipmh.arxiv.org")  # 消费初始 token → 0.0

    # 重复调用（如同 route_for 被多次触发）不应进一步收紧或改变已生效状态。
    limiter.alias("oaipmh.arxiv.org", "export.arxiv.org")
    limiter.alias("oaipmh.arxiv.org", "export.arxiv.org")

    assert limiter.effective_rpm("oaipmh.arxiv.org") == 60
    assert first_wait == pytest.approx(0.0, abs=1e-9)
    # 幂等：再次 acquire 的排队值与"只 alias 一次"时应有的走向一致（欠 1 个 token → 1.0s），
    # 而不是因重复合并被进一步拉长。
    assert limiter.acquire("oaipmh.arxiv.org") == pytest.approx(1.0, abs=1e-9)


def test_alias_merge_takes_more_conservative_capacity_and_clamps_level() -> None:
    """burst 同 rpm 同理取 min；合并后 level 不得超过收紧后的新 capacity（不变式）。"""
    clock = FakeClock()
    limiter = RateLimiter(clock=clock)
    limiter.register("a.example", RatePolicy(requests_per_minute=60, burst=5))
    limiter.register("b.example", RatePolicy(requests_per_minute=60, burst=1))

    limiter.alias("a.example", "b.example")

    # 容量取更小者（1），且此刻两域共享同一桶。
    clock.advance(100.0)  # 时间充分推进，若容量未收紧则可能误判
    waits = [limiter.acquire("a.example") for _ in range(1)]
    assert waits == [pytest.approx(0.0, abs=1e-9)]
    assert limiter.acquire("b.example") == pytest.approx(1.0, abs=1e-9)
