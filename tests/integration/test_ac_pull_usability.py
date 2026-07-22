"""缺陷 C-C · 大 venue pull 可用性 —— resolve 零网络豁免限速 + --limit 前置到 resolve 圈选。

缺陷（Phase 2 终检置顶）：pull 的 resolve 阶段对**每篇** paper 逐个过 per-domain
限速闸，但 `url_strategy=direct` 的 resolve 是零网络纯 URL 构造（不发任何 HTTP
请求）；且 `--limit` 在全量 resolve 完成后才截断候选。后果：ICLR 2024（2260 篇）
量级 pull 的 resolve 阶段数十分钟纯空转（见 tests/online/test_openreview_smoke.py
的口径注记）。

裁决修法（两点都验，见 design/05 §3 per-domain 限速 / §6 --limit）：
1. **零网络 resolve 豁免限速闸**：adapter 声明 `resolve_offline=True`（本仓全部
   adapter 的 `resolve_assets` 都是纯 URL 构造，已逐个证明零网络）→ resolve 阶段
   不取 token。反向保证：未声明的 adapter（真实网络 resolve 策略）限速闸必须保留。
2. **--limit N 前置到 resolve 圈选**：只对确定性顺序（`_select_papers` 稳定序）的
   前 N 篇建 resolve 任务，而非全量 resolve 后才截断——resolve 任务数 == N；且
   dry-run 的"将下载 N"与实跑下载数一致（AC-1.2 口径在 --limit 下同样成立）；两次
   重跑圈选同一子集（断点续爬 resume 不会选中不同子集）。

进程内经 `PipelineRunner`（不经 CLI），复用 `test_pipeline_e2e` 的 `make_env`/
`PipelineEnv`。全程零真实网络（mock adapter）。
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from integration.conftest import VENUE
from integration.test_pipeline_e2e import PipelineEnv, make_env
from paper_crawler.adapter import load_adapters
from paper_crawler.adapters.mock_platform import MockPlatformAdapter
from paper_crawler.pipeline import PipelineRunner, Selector, StageContext
from paper_crawler.ratelimit import RateLimiter
from paper_crawler.registry import VenueRegistry

# year 2024 = volume 1；30 篇（2 期 × 15）> limit 才能验证"只 resolve 前 N 篇"而非全量。
_LIMIT_QUIRKS: dict[str, object] = {
    "volumes": 1,
    "issues_per_volume": 2,
    "papers_per_issue": 15,
    "seed": 42,
}
# 规模场景：单卷单期 2200 篇（>2000），验证 resolve 零 token / 壁钟不随篇数线性膨胀。
_SCALE_QUIRKS: dict[str, object] = {
    "volumes": 1,
    "issues_per_volume": 1,
    "papers_per_issue": 2200,
    "seed": 42,
}


class _CountingLimiter(RateLimiter):
    """`RateLimiter` 计数壳：记录 `acquire` 次数，限速语义与父类完全一致。"""

    def __init__(self, *, scale: float = 1.0) -> None:
        super().__init__(scale=scale)
        self.acquire_calls = 0

    def acquire(self, domain: str) -> float:
        self.acquire_calls += 1
        return super().acquire(domain)


def _runner(
    env: PipelineEnv,
    *,
    limiter: RateLimiter | None = None,
    real_sleeper: bool = False,
    dry_run: bool = False,
) -> PipelineRunner:
    """按 `make_runner` 同形装配 runner，但可注入自定义 limiter / 真实 sleeper。"""
    registry = VenueRegistry(load_adapters())
    assert registry.load_dirs(list(env.config.venues_dirs)) == []
    ctx = StageContext(
        config=env.config,
        db=env.db,
        repo=env.repo,
        registry=registry,
        queue=env.queue,
        limiter=limiter if limiter is not None else RateLimiter(scale=env.config.rate_scale),
        sleeper=time.sleep if real_sleeper else env.sleeps.append,
        dry_run=dry_run,
    )
    return PipelineRunner(ctx)


def _fetched_dois(env: PipelineEnv) -> list[str]:
    """已 fetched 资产所属 paper 的 doi（升序）——圈选子集身份的可比较投影。"""
    rows = env.db.query(
        "SELECT DISTINCT i.value FROM identifier i "
        "JOIN asset a ON a.paper_id = i.paper_id "
        "WHERE a.state = 'fetched' AND i.scheme = 'doi' ORDER BY i.value"
    )
    return [str(r["value"]) for r in rows]


# -- 修法 1：零网络 resolve 豁免限速闸 -----------------------------------------


def test_direct_resolve_consumes_zero_ratelimit_tokens_at_scale(tmp_path: Path) -> None:
    """2200 篇零网络 resolve 全程不取限速 token，且壁钟 <5s（未修复时逐篇闸 ≈ 数分钟）。"""
    env = make_env(tmp_path, quirks=_SCALE_QUIRKS)
    try:
        limiter = _CountingLimiter(scale=env.config.rate_scale)
        runner = _runner(env, limiter=limiter, real_sleeper=True, dry_run=True)

        start = time.monotonic()
        runner.pull(VENUE, Selector(volume="1"))  # dry-run 止于 resolve
        elapsed = time.monotonic() - start

        # discover(1) + enumerate(1 期) = 2；resolve 2200 篇零网络 → 0 token。
        # 未修复时应为 2 + 2200 = 2202（每篇逐个 acquire_and_wait）。
        assert limiter.acquire_calls == 2, (
            f"resolve 消耗了限速 token（期望仅 discover+enumerate=2，实测 "
            f"{limiter.acquire_calls}）——2200 篇被逐个限速空转正是 C-C 缺陷本身"
        )
        # 壁钟护栏：真实 sleeper 下 2200 篇 resolve <5s（未修复时逐篇 0.1s 闸 ≈ 数分钟）。
        assert elapsed < 5.0, f"resolve 阶段壁钟 {elapsed:.2f}s ≥ 5s（限速空转征兆）"
        # dry-run 止于 resolve：全部 planned（证明确实 resolve 了 2200 篇，非"没跑所以零 token"）。
        assert env.repo.counts(VENUE)["assets_planned"] == 2200
    finally:
        env.close()


def test_ratelimit_gate_retained_for_non_offline_resolve(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """反向保证：未声明 `resolve_offline` 的 adapter（真实网络 resolve 策略）限速闸必须保留。"""
    env = make_env(
        tmp_path,
        quirks={"volumes": 1, "issues_per_volume": 1, "papers_per_issue": 3, "seed": 42},
    )
    try:
        # 模拟"需发请求的 resolve 策略"：把 mock 的零网络声明临时置 False。
        monkeypatch.setattr(MockPlatformAdapter, "resolve_offline", False)
        limiter = _CountingLimiter(scale=env.config.rate_scale)
        _runner(env, limiter=limiter, dry_run=True).pull(VENUE, Selector(volume="1"))

        # discover(1) + enumerate(1) + resolve(3 篇各 1 次) = 5：闸对真实网络 resolve 保留。
        assert limiter.acquire_calls == 5, (
            f"非零网络 resolve 的限速闸被误豁免（期望 5，实测 {limiter.acquire_calls}）"
        )
    finally:
        env.close()


# -- 修法 2：--limit 前置到 resolve 圈选 ---------------------------------------


def test_limit_is_forward_to_resolve_selection(tmp_path: Path) -> None:
    """limit=10（30 篇中）：只对前 10 篇建 resolve 任务（而非全量 30 后才截断）。"""
    env = make_env(tmp_path, quirks=_LIMIT_QUIRKS)
    try:
        report = _runner(env).pull(VENUE, Selector(year=2024, limit=10))

        resolve_tasks = env.db.query("SELECT id FROM task WHERE kind = 'resolve'")
        assert len(resolve_tasks) == 10, "resolve 未前置——仍对全量 30 篇建了任务"

        counts = env.repo.counts(VENUE)
        assert counts["papers"] == 30  # enumerate 仍全量落库（清单不受 limit 影响）
        assert counts["assets_planned"] == 10  # 仅前 10 篇 resolve → 10 plan
        assert counts["assets_fetched"] == 10
        assert report.succeeded == 10
    finally:
        env.close()


def test_limit_dry_run_count_matches_real_run(tmp_path: Path) -> None:
    """AC-1.2 口径在 --limit 下成立：dry-run 的"将下载 N" == 实跑实际下载数。"""
    env = make_env(tmp_path, quirks=_LIMIT_QUIRKS)
    try:
        dry = _runner(env, dry_run=True).pull(VENUE, Selector(year=2024, limit=10))
        assert dry.planned_downloads == 10
        assert env.repo.counts(VENUE)["assets_fetched"] == 0  # dry-run 零下载副作用

        real = _runner(env).pull(VENUE, Selector(year=2024, limit=10))
        assert real.succeeded == dry.planned_downloads == 10  # 逐字一致
    finally:
        env.close()


def test_limit_selection_is_deterministic_across_reruns(tmp_path: Path) -> None:
    """两次独立 limit=10 跑圈选**同一** 10 篇子集（稳定排序 → 断点续爬 resume 不漂移）。"""
    env1 = make_env(tmp_path / "run1", quirks=_LIMIT_QUIRKS)
    env2 = make_env(tmp_path / "run2", quirks=_LIMIT_QUIRKS)
    try:
        _runner(env1).pull(VENUE, Selector(year=2024, limit=10))
        _runner(env2).pull(VENUE, Selector(year=2024, limit=10))

        dois1 = _fetched_dois(env1)
        dois2 = _fetched_dois(env2)
        assert len(dois1) == 10
        assert dois1 == dois2, "同语料两次 limit=10 圈选了不同子集（非确定性圈选）"
    finally:
        env1.close()
        env2.close()
