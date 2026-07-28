"""per-domain token bucket 限速器（接口冻结件 §2.6）。

设计要点（design/05 §3"最保守值"语义）：
- 容量 = burst；速率 = requests_per_minute / 60 * scale token/s。
- `acquire` 本身不 sleep——无 token 可用时"预登记消费"（level 可为负，代表
  欠账），返回调用方应 sleep 的秒数；由调用方自行 sleep，保持限速器纯函数式、
  可用假时钟精确断言（连续 acquire 排队累加）。
- `register`/`override` 对同一 domain 反复调用时，有效 rpm 单调不增——只会
  更保守，即使后续调用传入更大的 rpm 也不放宽（防止后注册覆盖掉更严格的限制）。
- 容量（burst）与 rpm 同理单调不增：重复 `register` 同 domain 取更小的
  burst（2026-07-21 仲裁：突发容量越大越激进，"最保守值"精神下应与 rpm
  同样取 min，而非保留首次注册值——同 domain 多 adapter 声明不同 burst 时
  不应放宽）。若合并后当前 level 超过新容量会立即下调，保持"level ≤
  capacity"不变式随时成立。
- `alias` 同理单调不放宽（2026-07-27 R1b 修复 P1-4）：若 `alias_domain` 此刻已有
  独立桶（曾直接 `register`/`override` 过，或已积累欠账），**不覆盖丢弃**——与
  `canonical_domain` 的桶合并取更保守值（rpm/capacity 取 min，level 取二者中更负
  值），两个 key 之后都指向同一个（就地更新的）`_Bucket` 对象。同一对 `alias`
  反复调用是幂等的（`stages.route_for` 每次路由都会重建 alias，不能越调越严）。
- 未注册 domain 的 `acquire`/`override`/`effective_rpm` 一律 fail fast，抛
  `CrawlerError(CONFIG)`——未注册即未声明限速策略，静默放行等于绕过限速。
- `effective_rpm()` 返回的是**已计入 `scale`** 的真实生效速率（rpm × scale），
  不是注册时的裸 rpm——观测面必须与 `acquire()` 实际消费 token 的速率一致。
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
        """注册（或加固）一个 domain 的限速策略；重复注册取更保守（更小）的 rpm 与 burst。"""
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
        existing.capacity = min(existing.capacity, policy.burst)
        if existing.level > existing.capacity:
            existing.level = float(existing.capacity)

    def override(self, domain: str, requests_per_minute: float) -> None:
        """VenueSpec/CLI 临时覆盖；与当前有效值取 min（只会更保守，不会放宽）。"""
        bucket = self._require_bucket(domain)
        bucket.rpm = min(bucket.rpm, requests_per_minute)

    def alias(self, alias_domain: str, canonical_domain: str) -> None:
        """让 `alias_domain` 与 `canonical_domain` 共享同一 token bucket（多域共用一份预算）。

        `canonical_domain` 必须已 `register`——把 `alias_domain` 指向同一 `_Bucket`
        对象（引用别名），此后对任一 key 的 `acquire` 都记入同一份预算。用于同一
        adapter 声明的多个域共用一份 ToU 限速（如 arxiv 三域 export/oaipmh/arxiv.org
        共用 1req/3s、「并发 1」）：pipeline 在主域 acquire、HttpClient 在实际请求
        host acquire，二者落到同一桶，逐请求限速对整簇域生效而非各自独立放行。

        **`alias_domain` 已有独立桶时不覆盖**（2026-07-27 R1b P1-4 修复）：若它此前被
        直接 `register`/`override` 过（可能是更严的 rpm）或已积累欠账（level 为负），
        无条件 `self._buckets[alias_domain] = bucket` 会静默丢弃这些状态——`register`
        6rpm 后被 alias 到 30rpm 主域会被"放宽"，累积的欠账会被"清零"，两者都等价于
        绕过限速，与 `register`/`override`"只会更保守"的语义矛盾。故改为合并：rpm/
        capacity 取 min，level 取二者按当前时钟对齐补充后更负（更保守）的一侧，就地
        更新其中一个既有 `_Bucket` 对象，`alias_domain`/`canonical_domain` 两个 key
        合并后都指向它。

        `register` 首次建桶后从不替换该 `_Bucket` 对象（后续只就地收紧），故已经指向
        它的其它别名 key 会随合并自动同步（同一对象引用）。alias 到自身、或重复调用
        同一对 `(alias_domain, canonical_domain)`（两个 key 已共享同一对象）是幂等
        no-op——`stages.route_for` 每次路由都会重建 alias，不能因反复调用越调越严。
        """
        canonical_bucket = self._require_bucket(canonical_domain)
        existing = self._buckets.get(alias_domain)
        if existing is None:
            self._buckets[alias_domain] = canonical_bucket
            return
        if existing is canonical_bucket:
            return  # 已共享同一份桶（含 alias 到自身）——幂等 no-op

        # alias_domain 已有一份独立状态：合并前先把两侧都按当前时钟推进到"此刻"，避免
        # 两桶 last_update 不同步时直接比较 level 得出错误的"谁更保守"结论。
        self._refill(existing)
        self._refill(canonical_bucket)
        existing.rpm = min(existing.rpm, canonical_bucket.rpm)
        existing.capacity = min(existing.capacity, canonical_bucket.capacity)
        existing.level = min(existing.level, canonical_bucket.level)
        if existing.level > existing.capacity:
            existing.level = float(existing.capacity)
        self._buckets[alias_domain] = existing
        self._buckets[canonical_domain] = existing

    def acquire(self, domain: str) -> float:
        """消费一个 token；返回调用方应 sleep 的秒数（0=立即可用）。本方法不 sleep。"""
        bucket = self._require_bucket(domain)
        rate = self._refill(bucket)

        bucket.level -= 1.0  # 预登记本次消费，即使不足也记账（形成"欠账"，供下次排队累加）

        if bucket.level >= 0.0:
            return 0.0
        if rate <= 0.0:
            return float("inf")
        return -bucket.level / rate

    def effective_rpm(self, domain: str) -> float:
        """当前生效的 requests_per_minute（register/override/alias 合并后的最保守值），
        **已计入 `scale`**——反映 `acquire()` 实际消费 token 的真实速率（R1b P1-1：修复
        前只返回裸 `bucket.rpm`，scale≠1 时与真实吞吐不符的观测面缺陷）。
        """
        bucket = self._require_bucket(domain)
        return bucket.rpm * self._scale

    def _rate_per_sec(self, bucket: _Bucket) -> float:
        return bucket.rpm / 60.0 * self._scale

    def _refill(self, bucket: _Bucket) -> float:
        """把 `bucket.level` 按当前时钟推进到"此刻"（不消费 token，只补充+钳到容量上限并
        推进 `last_update`）；返回本次使用的速率（token/s），供调用方复用（`acquire` 消费
        token、`alias` 合并前对齐两桶时钟）而不必重复算 `_rate_per_sec`。
        """
        rate = self._rate_per_sec(bucket)
        now = self._clock()
        elapsed = max(0.0, now - bucket.last_update)
        level = bucket.level + elapsed * rate
        if level > bucket.capacity:
            level = float(bucket.capacity)
        bucket.level = level
        bucket.last_update = now
        return rate

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
