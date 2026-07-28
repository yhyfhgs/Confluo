"""fetch 前置门的异常路由 + `_finalize` 保证执行（R1d / 独立审查 P1-5）。

缺陷（修复前）：`_execute_claimed` 的两道 fetch 前置门（challenge 域冷却门、auth 门）
位于 per-task `try` **之外**——门内任何异常都不经 `_route_error` 分类，而是：

- 顶层路径（`drain()`/`grab()`/`timeline --refresh`）：逃出 `_drain_loop` → 整轮中止，
  `_finalize` 不执行（`last-run.md` 不落盘、GROBID 连接池不关），领取中的任务停在
  RUNNING（要靠下个进程的 `recover_running` 才归还 PENDING）；
- 嵌套路径（`pull` 级联内的 `_drain_loop`）：被**外层 pull 任务**的 `except CrawlerError`
  接住 → 错误记在 pull 父任务上（归因错位），真正出问题的 fetch 子任务反而无痕。

真实触发面（本文件三个场景与之同构）：
1. `auth/providers/cookie_session.py` 的探针网络故障恒抛 `CrawlerError(TRANSIENT)`，
   而 `_auth_gate_fetch` 的 `health_check`/`refresh` 调用无 try（对照 ensure_session 有）；
2. 冷却键读侧：`cooldown.read_until` 经 `cooldown_path` 白名单校验，非法键（如带根点的
   FQDN host `pubs.example.org.`、IPv6 字面量 `2001:db8::1`、IDN 未 punycode 化的 host）
   抛 `CrawlerError(CONFIG)`——该调用同样在 try 外；
3. 非 `CrawlerError` 的意外异常（门内任意 bug）同样直接逃逸。

修复后的口径（本文件即其回归锁定）：门内异常一律按**当前 fetch 任务**经 `_route_error`
分类处置（TRANSIENT→退避重试至 FAILED、CONFIG→BLOCKED、非 CrawlerError→TRANSIENT），
整轮继续处理后续任务；且无论 drain 如何逃逸（含 `BaseException`：Ctrl-C），`_finalize`
必在 `finally` 中执行——报告落盘、GROBID 连接池关闭。

装配复用 `integration.test_auth_pipeline` 的 mock 家族（auth_gated adapter / 假 provider /
假时钟），沿 `integration.conftest` 直接 import 姊妹测试模块件的既有先例。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from integration.test_auth_pipeline import (
    _VENUE,
    _AuthGatedMock,
    _enqueue_fetches,
    _FakeAuthManager,
    _FakeProvider,
    _MutableClock,
    _ok_provider,
    _setup,
)
from paper_crawler.errors import CrawlerError, ErrorClass
from paper_crawler.pipeline import PipelineRunner
from paper_crawler.types import AssetPlan, FetchResult, HealthStatus, SessionHandle

_OK_CLOCK = datetime(2026, 7, 23, 10, 0, 0)  # 工作时段窗（8-23）内


class _ProbeExplodesProvider(_FakeProvider):
    """`cookie_session._probe` 网络故障的同构 mock：health_check 恒抛 TRANSIENT。"""

    def health_check(self, session: SessionHandle) -> HealthStatus:
        self.health_calls += 1
        raise CrawlerError(
            ErrorClass.TRANSIENT, "auth probe failed for 'auth_mock'", detail="ConnectError"
        )


def _states(env: SimpleNamespace) -> dict[str, int]:
    rows = env.db.query("SELECT state, COUNT(*) AS c FROM task GROUP BY state")
    return {str(r["state"]): int(r["c"]) for r in rows}


# -- ① 健康门探针抛 TRANSIENT：归因到当前 fetch 任务，整轮不中止 -------------------


def test_health_gate_probe_transient_routes_to_task_and_drain_returns(
    tmp_path: Path, request: pytest.FixtureRequest
) -> None:
    """health_check 抛 TRANSIENT → 该 fetch 任务按 TRANSIENT 重试语义（退避后重试至 FAILED），
    其余任务照常领取执行，`drain()` 正常返回，`last-run.md` 已落盘。"""
    auth_mock = _AuthGatedMock(fetch_mode="ok")
    provider = _ProbeExplodesProvider()
    env = _setup(
        tmp_path,
        request=request,
        auth_mock=auth_mock,
        n_papers=10,
        overrides={"auth_health_interval": 2},
    )
    _enqueue_fetches(env)
    runner = PipelineRunner(
        env.ctx, clock=_MutableClock(_OK_CLOCK), auth_manager=_FakeAuthManager(provider)
    )

    report = runner.drain()  # 修复前：CrawlerError(TRANSIENT) 逃逸，整轮中止

    assert provider.health_calls >= 1  # 门确实触发了探针
    assert report.succeeded == 2  # 门触发前的两篇照常取回
    assert report.failed == 8  # 其余八篇各自按 TRANSIENT 重试至 FAILED（RetrySpec(4)）
    assert report.blocked == 0
    assert all(f["stage"] == "fetch" for f in report.failures)  # 归因在 fetch 任务上
    assert all(f["error_class"] == ErrorClass.TRANSIENT.value for f in report.failures)
    # 整轮走完：无任务停在 RUNNING/PENDING（修复前领取中的那个会永久停在 RUNNING）
    assert _states(env) == {"DONE": 2, "FAILED": 8}
    assert (env.config.reports_dir / "last-run.md").is_file()  # `_finalize` 已执行


# -- ② 冷却读侧非法键抛 CONFIG：BLOCKED（按路由），整轮不中止 ---------------------


def test_cooldown_read_illegal_key_blocks_task_and_run_continues(
    tmp_path: Path, request: pytest.FixtureRequest
) -> None:
    """冷却门读侧抛 `CrawlerError(CONFIG)`（非法冷却键）→ 当前任务 BLOCKED（CONFIG 的既有
    路由），后续任务照常取回，`drain()` 正常返回、报告落盘。

    非法键来自 asset URL 的 host——此处用**带根点的 FQDN**（`auth.mock.local.`，合法 URL
    形态），其 host 以 `.` 结尾即不满足 `cooldown._KEY_RE`（首尾须字母数字）；IPv6 字面量
    与未 punycode 化的 IDN host 是同一缺陷面的姊妹形态。
    """
    auth_mock = _AuthGatedMock(fetch_mode="ok")
    env = _setup(tmp_path, request=request, auth_mock=auth_mock, n_papers=2)
    # 首个 asset 的 URL 换成根点 FQDN：其冷却键非法 → 冷却门读侧抛 CONFIG
    env.db.execute(
        "UPDATE asset SET url = ? WHERE id = ?",
        ("https://auth.mock.local./pdf/10.1/auth.0", env.asset_ids[0]),
    )
    _enqueue_fetches(env)
    runner = PipelineRunner(
        env.ctx, clock=_MutableClock(_OK_CLOCK), auth_manager=_FakeAuthManager(_ok_provider())
    )

    report = runner.drain()  # 修复前：CrawlerError(CONFIG) 逃逸，整轮中止

    assert report.blocked == 1 and report.succeeded == 1  # 一个 BLOCKED、另一个照常取回
    assert report.failed == 0
    assert _states(env) == {"BLOCKED": 1, "DONE": 1}
    blocked = env.db.query("SELECT blocked_reason FROM task WHERE state = 'BLOCKED'")
    assert "config" in str(blocked[0]["blocked_reason"])  # CONFIG → BLOCKED（既有路由）
    assert "非法冷却键" in str(blocked[0]["blocked_reason"])  # 原因如实透传给用户
    assert (env.config.reports_dir / "last-run.md").is_file()


# -- ③ pull 嵌套：门异常归因到 fetch 子任务而非 pull 父任务 -----------------------


def test_gate_error_attributed_to_fetch_child_not_pull_parent(
    tmp_path: Path, request: pytest.FixtureRequest
) -> None:
    """pull 级联内的嵌套 drain：fetch 前置门异常记在**该 fetch 子任务**上，pull 父任务不背锅。

    修复前该异常逃出嵌套 `_drain_loop` → 被外层 `_execute_claimed`（pull 行）的
    `except CrawlerError` 接住 → `queue.fail(pull_id, TRANSIENT)`：pull 反复重试至 FAILED，
    而真正出问题的 fetch 子任务停在 RUNNING、无 error_class（归因错位）。
    """
    auth_mock = _AuthGatedMock(fetch_mode="ok")
    provider = _ProbeExplodesProvider()
    env = _setup(
        tmp_path,
        request=request,
        auth_mock=auth_mock,
        n_papers=10,
        overrides={"auth_health_interval": 2},
    )
    # asset 行已就位 → 直接把 fetch 子任务挂在一个 pull 任务下（模拟 pull 级联第 4 阶段：
    # 子任务先于 pull 内部 enqueue 的 discover 建立，故必在 pull 的嵌套 drain 内被领取）
    pull_task = env.queue.enqueue("pull", _VENUE, {})
    for asset_id in env.asset_ids:
        env.queue.enqueue("fetch", _VENUE, {"asset": asset_id}, parent_id=pull_task.task_id)
    runner = PipelineRunner(
        env.ctx, clock=_MutableClock(_OK_CLOCK), auth_manager=_FakeAuthManager(provider)
    )

    report = runner.drain()  # 修复前：pull 重试耗尽后异常仍从顶层逃逸

    pull_row = env.queue.get(pull_task.task_id)
    assert str(pull_row["state"]) == "DONE"  # 父任务未被错记失败
    assert pull_row["error_class"] is None
    assert int(pull_row["attempts"]) == 0  # 也未被错误地消耗重试预算
    failed = env.db.query("SELECT kind, error_class FROM task WHERE state = 'FAILED'")
    assert failed and all(str(r["kind"]) == "fetch" for r in failed)  # 失败全部记在 fetch 子任务
    assert all(str(r["error_class"]) == ErrorClass.TRANSIENT.value for r in failed)
    assert all(f["stage"] == "fetch" for f in report.failures)
    assert (env.config.reports_dir / "last-run.md").is_file()


# -- ④ `_finalize` 保证执行（drain 无论如何逃逸）--------------------------------


class _CtrlCMock(_AuthGatedMock):
    """fetch 中途 Ctrl-C：`BaseException` 不被 `_execute_claimed` 的 `except Exception` 接住，
    是"drain 仍可能逃逸"的**真实**残余面——`_finalize` 的 finally 兜的正是它。"""

    def fetch_asset(
        self, plan: AssetPlan, io: object, session: SessionHandle | None = None
    ) -> FetchResult:
        self.fetch_calls += 1
        raise KeyboardInterrupt


class _FakeGrobid:
    """`StageContext.grobid` 的最小替身：只记 close 是否被调用（`_finalize` 的资源侧职责）。"""

    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


def test_finalize_runs_even_when_drain_escapes(
    tmp_path: Path, request: pytest.FixtureRequest
) -> None:
    """drain 主循环逃逸（Ctrl-C）时报告仍落盘、GROBID 连接池仍关闭，且异常照常向上抛。"""
    env = _setup(tmp_path, request=request, auth_mock=_CtrlCMock(fetch_mode="ok"), n_papers=1)
    grobid = _FakeGrobid()
    env.ctx.grobid = grobid
    _enqueue_fetches(env)
    runner = PipelineRunner(
        env.ctx, clock=_MutableClock(_OK_CLOCK), auth_manager=_FakeAuthManager(_ok_provider())
    )

    with pytest.raises(KeyboardInterrupt):
        runner.drain()

    assert (env.config.reports_dir / "last-run.md").is_file()  # 报告落盘
    assert grobid.closed and env.ctx.grobid is None  # 连接池关闭并置回 None


# -- ⑤ 冷却**写**侧非法键：就地收敛，不从 `_route_error` 内部逃逸 -------------------


def test_enter_cooldown_with_illegal_key_does_not_raise_from_error_route(
    tmp_path: Path, request: pytest.FixtureRequest
) -> None:
    """`_enter_challenge_cooldown` 由 `_route_error` 调用——已在 per-task 错误处置之内，
    非法键在此再抛会从 except 块逃出并中止整轮。故就地收敛为 ERROR 日志：不抛、不落盘、
    运行态字典仍生效（该任务照常由调用方按 CHALLENGE 转 BLOCKED）。

    读侧同类异常（`_block_if_cooling_down`）则相反——经 `_route_error` 正常分类为
    BLOCKED(config)，见 `test_cooldown_read_illegal_key_blocks_task_and_run_continues`。
    """
    env = _setup(tmp_path, request=request, auth_mock=_AuthGatedMock(fetch_mode="ok"), n_papers=1)
    env.db.execute(
        "UPDATE asset SET url = ? WHERE id = ?",
        ("https://auth.mock.local./pdf/x", env.asset_ids[0]),
    )
    asset = env.repo.get_asset(env.asset_ids[0])
    runner = PipelineRunner(
        env.ctx, clock=_MutableClock(_OK_CLOCK), auth_manager=_FakeAuthManager(_ok_provider())
    )

    runner._enter_challenge_cooldown(_VENUE, asset)  # 不抛

    assert runner._challenge_cooldown["auth.mock.local."] > _OK_CLOCK  # 运行态仍生效
    cooldown_dir = env.config.home / "state" / "cooldown"
    assert not cooldown_dir.is_dir() or list(cooldown_dir.glob("*.json")) == []  # 未落盘
