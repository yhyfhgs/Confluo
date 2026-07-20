"""per-domain token bucket 限速器（接口冻结件 §2.6）。

设计要点（design/05 §3"最保守值"语义）：
- 容量 = burst；速率 = requests_per_minute / 60 * scale token/s。
- `acquire` 本身不 sleep——无 token 可用时"预登记消费"（level 可为负，代表
  欠账），返回调用方应 sleep 的秒数；由调用方自行 sleep，保持限速器纯函数式、
  可用假时钟精确断言（连续 acquire 排队累加）。
- `register`/`override` 对同一 domain 反复调用时，有效 rpm 单调不增——只会
  更保守，即使后续调用传入更大的 rpm 也不放宽（防止后注册覆盖掉更严格的限制）。
- 容量（burst）只在 domain 首次 `register` 时确定：接口冻结件只对 rpm 定义了
  "重复注册取更保守"合并语义，未提及 burst 的合并规则，故本实现保留首次注册的
  burst 不变。
- 未注册 domain 的 `acquire`/`override`/`effective_rpm` 一律 fail fast，抛
  `CrawlerError(CONFIG)`——未注册即未声明限速策略，静默放行等于绕过限速。
"""

import time
from collections.abc import Callable
from dataclasses import dataclass

from paper_crawler.errors import CrawlerError, ErrorClass
from paper_crawler.types import RatePolicy


@dataclass
class _Bucket:
    """单个 domain 的 token bucket 状态。"""

    rpm: float
    capacity: int
    level: float
    last_update: float


class RateLimiter:
    """per-domain token bucket；速率取 register/override 中的最保守值。"""

    def __init__(self, *, scale: float = 1.0, clock: Callable[[], float] = time.monotonic) -> None:
        self._scale = scale
        self._clock = clock
        self._buckets: dict[str, _Bucket] = {}

    def register(self, domain: str, policy: RatePolicy) -> None:
        """注册（或加固）一个 domain 的限速策略；重复注册取更保守（更小）的 rpm。"""
        existing = self._buckets.get(domain)
        if existing is None:
            now = self._clock()
            self._buckets[domain] = _Bucket(
                rpm=policy.requests_per_minute,
                capacity=policy.burst,
                level=float(policy.burst),
                last_update=now,
            )
            return
        existing.rpm = min(existing.rpm, policy.requests_per_minute)

    def override(self, domain: str, requests_per_minute: float) -> None:
        """VenueSpec/CLI 临时覆盖；与当前有效值取 min（只会更保守，不会放宽）。"""
        bucket = self._require_bucket(domain)
        bucket.rpm = min(bucket.rpm, requests_per_minute)

    def acquire(self, domain: str) -> float:
        """消费一个 token；返回调用方应 sleep 的秒数（0=立即可用）。本方法不 sleep。"""
        bucket = self._require_bucket(domain)
        rate = self._rate_per_sec(bucket)

        now = self._clock()
        elapsed = max(0.0, now - bucket.last_update)
        level = bucket.level + elapsed * rate
        if level > bucket.capacity:
            level = float(bucket.capacity)
        bucket.last_update = now

        level -= 1.0  # 预登记本次消费，即使不足也记账（形成"欠账"，供下次排队累加）
        bucket.level = level

        if level >= 0.0:
            return 0.0
        if rate <= 0.0:
            return float("inf")
        return -level / rate

    def effective_rpm(self, domain: str) -> float:
        """当前生效的 requests_per_minute（register/override 合并后的最保守值）。"""
        return self._require_bucket(domain).rpm

    def _rate_per_sec(self, bucket: _Bucket) -> float:
        return bucket.rpm / 60.0 * self._scale

    def _require_bucket(self, domain: str) -> _Bucket:
        bucket = self._buckets.get(domain)
        if bucket is None:
            raise CrawlerError(
                ErrorClass.CONFIG,
                f"rate limiter: domain not registered: {domain}",
                detail=domain,
            )
        return bucket


__all__ = ["RateLimiter"]
