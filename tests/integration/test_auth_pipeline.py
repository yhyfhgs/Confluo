"""auth pipeline 接缝集成（auth-framework §8；进程内经 `PipelineRunner`，全部 mock 驱动）。

覆盖（离线，零真实网络——文件内 mock adapter/provider + `httpx.MockTransport` OA 取回 +
注入假时钟）：
- §8.1/8.5 no_entitlement 独立终态（不计 failed）→ unpaywall OA-fallback direct 取回落盘 OA asset；
- §8.2 健康门：批内周期性 health_check 检出 EXPIRED→整批 BLOCKED，无 401 轰炸（handler 计数 ≤1）；
  refresh 成功续期 → 继续；
- §8.3 日配额：auth 平台域当日 fetch 尝试篇次达 cap → BLOCKED(config)；
- §8.4 challenge → BLOCKED(challenge) + 平台冷却 24h（落盘 + 同批后续连带 BLOCKED）；
- §8.6 工作时段窗：窗外 auth_gated 批延迟不失败（BLOCKED，可 resume）；窗内放行；
- 07 §3.2 EZProxy 接线（P1-11）：fetch 前统一 `rewrite_url`——adapter 收到代理形态 URL、
  FetchLog 记实发 URL 而归属域/asset.url 保持规范形态；非 ezproxy provider 与 OA 兜底零变化。

本文件自带 mock（不依赖 T6 conftest）：`_AuthGatedMock`（family=auth_gated）、`_FakeProvider`/
`_FakeAuthManager`（health/refresh/ensure_session）、`_MutableClock`（假时钟）。
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
import yaml

from paper_crawler.adapter import AdapterBase, AdapterFamily
from paper_crawler.adapters.elsevier_sd.adapter import ElsevierScienceDirectAdapter
from paper_crawler.auth.providers.ezproxy import EZProxyProvider
from paper_crawler.auth.store import CredentialStore, ProviderProfile
from paper_crawler.config import Config
from paper_crawler.errors import CrawlerError, ErrorClass
from paper_crawler.http import HttpClient
from paper_crawler.obslog import setup_logging
from paper_crawler.pipeline import PipelineRunner, StageContext
from paper_crawler.pipeline.runner import _DEFAULT_AUTH_DAILY_CAP, _work_hours_ok
from paper_crawler.ratelimit import RateLimiter
from paper_crawler.registry import VenueRegistry
from paper_crawler.storage.db import Database
from paper_crawler.storage.repo import Repo
from paper_crawler.tasks import TaskQueue
from paper_crawler.types import (
    AssetKind,
    AssetPlan,
    AuthLevel,
    Capability,
    FetchResult,
    HealthStatus,
    PaperStub,
    RatePolicy,
    SessionBackend,
    SessionHandle,
    UrlStrategy,
)

_VENUE = "auth_venue"
_PLATFORM = "auth_mock"
_DOMAIN = "auth.mock.local"  # 冷却键（E-1 后 = 域；`_AuthGatedMock.domains[0]` 与 asset host）
_PDF = b"%PDF-1.4\n" + b"0" * 1024 + b"\n%%EOF\n"


# --- mock auth_gated adapter --------------------------------------------------


class _AuthGatedMock(AdapterBase):
    """family=auth_gated 的本地 mock；fetch 行为由 `fetch_mode` 控制，记录调用计数。"""

    adapter_id = _PLATFORM
    family: AdapterFamily = "auth_gated"
    capabilities = (
        Capability.DISCOVER | Capability.ENUMERATE | Capability.RESOLVE | Capability.FETCH
    )
    default_rate = RatePolicy(6000, burst=1000, source_note="mock")
    auth_requirement = AuthLevel.NONE  # 门键于 family=auth_gated，非 auth_requirement
    domains: tuple[str, ...] = ("auth.mock.local",)
    resolve_offline = True

    def __init__(self, *, fetch_mode: str = "ok", plan_host: str = "auth.mock.local") -> None:
        self.fetch_mode = fetch_mode  # "ok" | "no_entitlement" | "auth_expired" | "challenge"
        self.fetch_calls = 0
        self.auth_fail_calls = 0  # 命中 auth_expired（401 形态）的 fetch 次数
        # resolve 产计划的 host（默认 = domains[0]；ezproxy 幂等用例注入已代理形态 host）。
        self.plan_host = plan_host
        # 真正交到 `fetch_asset` 的 plan.url 序列——EZProxy 接线（07 §3.2）断言口径：
        # "实际发出的请求 URL"，adapter 侧只看得到 pipeline 给它的那一个。
        self.fetch_urls: list[str] = []

    def resolve_assets(
        self, venue: object, paper: PaperStub, session: SessionHandle | None = None
    ) -> list[AssetPlan]:
        doi = next((v for s, v in paper.identifiers if s == "doi"), "x")
        return [
            AssetPlan(
                kind=AssetKind.PDF,
                url=f"https://{self.plan_host}/pdf/{doi}",
                expected_type="application/pdf",
            )
        ]

    def fetch_asset(
        self, plan: AssetPlan, io: object, session: SessionHandle | None = None
    ) -> FetchResult:
        self.fetch_calls += 1
        self.fetch_urls.append(plan.url)
        if self.fetch_mode == "auth_expired":
            self.auth_fail_calls += 1
            raise CrawlerError(ErrorClass.AUTH_EXPIRED, "401 unauthorized (mock)")
        if self.fetch_mode == "no_entitlement":
            raise CrawlerError(ErrorClass.NO_ENTITLEMENT, "403 no entitlement (mock)")
        if self.fetch_mode == "challenge":
            raise CrawlerError(ErrorClass.CHALLENGE, "cf-mitigated challenge (mock)")
        if self.fetch_mode == "bad_pdf":  # 非 %PDF（拦截页伪装）→ pipeline 判 INTEGRITY
            n, sha = io.write_stream([b"<html>not a pdf</html>"])  # type: ignore[attr-defined]
            return FetchResult(ok=True, bytes_written=n, sha256=sha)
        n, sha = io.write_stream([_PDF])  # type: ignore[attr-defined]
        return FetchResult(ok=True, bytes_written=n, sha256=sha)


# --- fake AuthManager / provider ---------------------------------------------


class _FakeProvider:
    """duck-typed AuthProvider：health_check 按注入序列返回；refresh 返回预置 handle。"""

    def __init__(
        self, *, health_seq: list[HealthStatus] | None = None, refresh_returns: object = None
    ) -> None:
        self.provider_id = _PLATFORM
        self._health_seq = list(health_seq or [])
        self._refresh_returns = refresh_returns
        self.health_calls = 0
        self.refresh_calls = 0

    def _handle(self) -> SessionHandle:
        return SessionHandle(
            provider_id=self.provider_id,
            backend=SessionBackend.BEARER_TOKEN,
            payload_ref="mock_ref",
            established_at=datetime(2026, 7, 23, 10, 0, 0),
        )

    def ensure_session(self, *, interactive: bool = False) -> SessionHandle:
        return self._handle()

    def health_check(self, session: SessionHandle) -> HealthStatus:
        self.health_calls += 1
        return self._health_seq.pop(0) if self._health_seq else HealthStatus.OK

    def refresh(self, session: SessionHandle) -> object:
        self.refresh_calls += 1
        return self._refresh_returns


# ezproxy 形态 provider（07 §3.2 / auth-framework §3.4）：重写规则**不在测试里复刻**，
# 直接委托真实 `EZProxyProvider.rewrite_url`——被接线的是生产实现，而非同名替身。
_EZ_SUFFIX = ".ezproxy.myuniv.edu"
_EZ_PROXIED_HOST = f"auth-mock-local{_EZ_SUFFIX}"  # `_DOMAIN` 经 §3.4 泛化规则改写后的形态

_EZ_PROFILE = ProviderProfile(
    provider_id=_PLATFORM,
    kind="ezproxy",
    platform=_PLATFORM,
    proxy_base="https://login.myuniv.edu/login?url=",
    rewrite_suffix=_EZ_SUFFIX,
    state_ref="ez_state",
)


class _EZProxyFakeProvider(_FakeProvider):
    """ensure_session/health/refresh 沿用 fake 装置；`rewrite_url` 委托真实 EZProxyProvider。"""

    def __init__(self, home: Path) -> None:
        super().__init__()
        # `rewrite_url` 是纯字符串变换（只读 profile 的 rewrite_suffix），不触达 store。
        self._ez = EZProxyProvider(_EZ_PROFILE, CredentialStore(home))

    def rewrite_url(self, url: str) -> str:
        return self._ez.rewrite_url(url)


class _FakeAuthManager:
    def __init__(self, provider: _FakeProvider, *, raise_ensure: bool = False) -> None:
        self._provider = provider
        self._session: SessionHandle | None = None
        self._raise_ensure = raise_ensure

    def resolve(self, name: str, *, profile: str | None = None) -> _FakeProvider:
        return self._provider

    def ensure_session(self, provider_key: str, *, interactive: bool = False) -> SessionHandle:
        if self._raise_ensure:  # 无 session 且非交互 → AuthRequired（07 §5-1）
            raise CrawlerError(ErrorClass.AUTH_EXPIRED, "auth session required (mock)")
        if self._session is None:
            self._session = self._provider.ensure_session()
        return self._session


class _MutableClock:
    """可拨动的假时钟（naive datetime；工作时段窗按其字面小时）。"""

    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


# --- fake unpaywall adapter（OA-fallback resolve → OA pdf plan）---------------


class _FakeUnpaywall:
    domains: tuple[str, ...] = ("api.unpaywall.org",)
    default_rate = RatePolicy(300, burst=5, source_note="mock")

    def __init__(self, plans: list[AssetPlan]) -> None:
        self._plans = plans
        self.calls = 0

    def resolve_assets(
        self, venue: object, paper: PaperStub, session: SessionHandle | None = None
    ) -> list[AssetPlan]:
        self.calls += 1
        return list(self._plans)


# --- harness ------------------------------------------------------------------


def _oa_http() -> HttpClient:
    """MockTransport HttpClient：任何请求返 200 %PDF（OA direct 取回；无 limiter）。"""
    return HttpClient(
        user_agent="pc-test",
        transport=httpx.MockTransport(lambda req: httpx.Response(200, content=_PDF)),
    )


def _setup(
    tmp_path: Path,
    *,
    request: pytest.FixtureRequest,
    auth_mock: _AuthGatedMock,
    unpaywall: object | None = None,
    http: HttpClient | None = None,
    n_papers: int = 1,
    seed_fetch_logs: int = 0,
    id_scheme: str = "doi",
    config_extra: str = "",
    overrides: dict[str, object] | None = None,
) -> SimpleNamespace:
    home = tmp_path / "home"
    venues = home / "venues"
    venues.mkdir(parents=True)
    (home / "config.toml").write_text(
        '[paths]\nvenues_dirs = ["venues"]\n' + config_extra, encoding="utf-8"
    )
    (venues / f"{_VENUE}.yaml").write_text(
        yaml.safe_dump(
            {
                "id": _VENUE,
                "kind": "journal",
                "names": {"full": "Auth Venue", "aliases": []},
                "field": ["cs_ai"],
                "identifiers": {"issn": ["0000-0000"]},
                "metadata_source": _PLATFORM,
                "fulltext_source": _PLATFORM,
            }
        ),
        encoding="utf-8",
    )
    config = Config.load(home)
    for key, value in (overrides or {}).items():
        object.__setattr__(config, key, value)  # frozen dataclass 测试注入（Config 无该键时）
    setup_logging(config.log_dir, console_level="CRITICAL")
    db = Database(config.db_path)
    request.addfinalizer(db.close)  # 资源纪律（post-phase5-audit §3[S4]）：测试结束必关连接
    db.migrate()
    repo = Repo(db)
    queue = TaskQueue(db)
    registry = VenueRegistry({_PLATFORM: auth_mock, "unpaywall": unpaywall})
    registry.load_dirs([venues])
    repo.upsert_venue(registry.get(_VENUE))

    asset_ids: list[str] = []
    for i in range(n_papers):
        value = f"10.1/auth.{i}" if id_scheme == "doi" else f"auth.{i}"
        pid = repo.upsert_paper(
            _VENUE, None, PaperStub(title=f"p{i}", identifiers=((id_scheme, value),))
        )
        aid = repo.plan_asset(
            pid,
            AssetPlan(
                kind=AssetKind.PDF,
                url=f"https://auth.mock.local/pdf/{value}",
                expected_type="application/pdf",
            ),
            _PLATFORM,
        )
        asset_ids.append(aid)
    for _ in range(seed_fetch_logs):
        repo.add_fetch_log(
            asset_id=None,
            task_id=None,
            domain="auth.mock.local",
            url="seed",
            http_status=None,
            bytes_=0,
            elapsed_ms=0,
            rate_wait_ms=0,
            error_class=None,
        )

    sleeps: list[float] = []
    ctx = StageContext(
        config=config,
        db=db,
        repo=repo,
        registry=registry,
        queue=queue,
        limiter=RateLimiter(scale=config.rate_scale),
        sleeper=sleeps.append,
        oa_fallback=True,
        unpaywall_adapter=unpaywall,
        http=http,
    )
    return SimpleNamespace(
        config=config,
        db=db,
        repo=repo,
        queue=queue,
        registry=registry,
        ctx=ctx,
        asset_ids=asset_ids,
        sleeps=sleeps,
    )


def _runner(
    env: SimpleNamespace, *, provider: _FakeProvider, clock: _MutableClock
) -> PipelineRunner:
    return PipelineRunner(env.ctx, clock=clock, auth_manager=_FakeAuthManager(provider))


def _enqueue_fetches(env: SimpleNamespace) -> None:
    for aid in env.asset_ids:
        env.queue.enqueue("fetch", _VENUE, {"asset": aid})


_OK_CLOCK = lambda: _MutableClock(datetime(2026, 7, 23, 10, 0, 0))  # noqa: E731 (10:00 窗内)


def _ok_provider() -> _FakeProvider:
    return _FakeProvider(health_seq=[])  # 恒 OK


# -- §8.1/8.5 no_entitlement 独立终态 → OA-fallback direct 取回落盘 --------------


def test_no_entitlement_triggers_oa_fallback_direct_fetch(
    tmp_path: Path, request: pytest.FixtureRequest
) -> None:
    """no_entitlement（不计 failed）→ 派生 oa_fallback → unpaywall 规格化 OA pdf plan →
    `_fetch_oa_direct` 无凭证取回落盘 OA asset（AC-4.3 主方向 / 检查单 #12）。"""
    auth_mock = _AuthGatedMock(fetch_mode="no_entitlement")
    ua = _FakeUnpaywall(
        [
            AssetPlan(
                kind=AssetKind.PDF,
                url="https://oa.example.org/copy.pdf",
                url_strategy=UrlStrategy.DIRECT,
                auth_needed=AuthLevel.NONE,
                version="publishedVersion",
            )
        ]
    )
    env = _setup(
        tmp_path, request=request, auth_mock=auth_mock, unpaywall=ua, http=_oa_http(), n_papers=1
    )
    _enqueue_fetches(env)
    report = _runner(env, provider=_ok_provider(), clock=_OK_CLOCK()).drain()

    # no_entitlement 独立终态：不计 failed，单列计数
    assert report.failed == 0 and report.no_entitlement == 1
    # OA-fallback 实际取回：unpaywall 被查、OA asset 落盘（%PDF）
    assert ua.calls == 1
    fetched = env.repo.list_assets(venue_id=_VENUE, state="fetched")
    assert len(fetched) == 1
    oa_asset = fetched[0]
    assert oa_asset["source_adapter"] == "unpaywall" and oa_asset["version"] == "publishedVersion"
    assert Path(str(oa_asset["file_path"])).is_file()
    # 原平台 asset 停在 no_entitlement，不覆盖 OA 副本（身份并存）
    assert len(env.repo.list_assets(venue_id=_VENUE, state="no_entitlement")) == 1


def test_no_entitlement_no_oa_link_no_download(
    tmp_path: Path, request: pytest.FixtureRequest
) -> None:
    """unpaywall 无 PDF 直链（resolve 空）→ oa_fallback done、无副本落盘（landing-only 不下载）。"""
    auth_mock = _AuthGatedMock(fetch_mode="no_entitlement")
    ua = _FakeUnpaywall([])  # 无 OA 直链
    env = _setup(
        tmp_path, request=request, auth_mock=auth_mock, unpaywall=ua, http=_oa_http(), n_papers=1
    )
    _enqueue_fetches(env)
    report = _runner(env, provider=_ok_provider(), clock=_OK_CLOCK()).drain()

    assert report.no_entitlement == 1 and report.failed == 0
    assert ua.calls == 1
    assert env.repo.list_assets(venue_id=_VENUE, state="fetched") == []


# -- §8.2 健康门：EXPIRED 检出 → 整批 BLOCKED，无 401 轰炸 ---------------------


def test_first_fetch_auth_expired_blocks_batch_no_bombardment(
    tmp_path: Path, request: pytest.FixtureRequest
) -> None:
    """auth_mock fetch 首发 401 → 整批 BLOCKED(auth) 连带；handler 恰 1 次 401（AC-4.2 双源）。"""
    auth_mock = _AuthGatedMock(fetch_mode="auth_expired")
    env = _setup(tmp_path, request=request, auth_mock=auth_mock, n_papers=8)
    _enqueue_fetches(env)
    report = _runner(env, provider=_ok_provider(), clock=_OK_CLOCK()).drain()

    assert report.succeeded == 0
    assert report.blocked == 8  # 1 触发 + 7 连带
    assert auth_mock.fetch_calls == 1  # 只有触发者真正 fetch（B-m8 handler 请求计数为主）
    assert auth_mock.auth_fail_calls == 1  # ≤1，无 401 轰炸


def test_health_gate_detects_expired_within_interval(
    tmp_path: Path, request: pytest.FixtureRequest
) -> None:
    """周期性健康门（每 N 篇）检出 EXPIRED（refresh→None）→ 整批 BLOCKED，fetch 未撞 401。"""
    auth_mock = _AuthGatedMock(fetch_mode="ok")
    provider = _FakeProvider(health_seq=[HealthStatus.EXPIRED], refresh_returns=None)
    env = _setup(
        tmp_path,
        request=request,
        auth_mock=auth_mock,
        n_papers=10,
        overrides={"auth_health_interval": 2},
    )
    _enqueue_fetches(env)
    report = _runner(env, provider=provider, clock=_OK_CLOCK()).drain()

    # 前 2 篇成功；第 3 篇门触发（fetched_since_check>=2）→ health_check EXPIRED → BLOCKED
    assert report.succeeded == 2
    assert report.blocked == 8
    assert provider.health_calls == 1  # 门恰触发一次
    assert auth_mock.fetch_calls == 2  # 门前置拦截，fetch 未在 EXPIRED 后被调用（0 轰炸）
    assert auth_mock.auth_fail_calls == 0


def test_health_gate_aging_triggers_check_and_refresh_continues(
    tmp_path: Path, request: pytest.FixtureRequest
) -> None:
    """老化门（max_age=0 → 每篇 health_check）：EXPIRED→refresh 成功续期 → 继续取回。"""
    auth_mock = _AuthGatedMock(fetch_mode="ok")
    new_session = SessionHandle(
        provider_id=_PLATFORM,
        backend=SessionBackend.BEARER_TOKEN,
        payload_ref="refreshed",
        established_at=datetime(2026, 7, 23, 11, 0, 0),
    )
    provider = _FakeProvider(
        health_seq=[HealthStatus.EXPIRED, HealthStatus.OK], refresh_returns=new_session
    )
    env = _setup(
        tmp_path,
        request=request,
        auth_mock=auth_mock,
        n_papers=2,
        overrides={"auth_health_max_age_s": 0.0, "auth_health_interval": 999},
    )
    _enqueue_fetches(env)
    report = _runner(env, provider=provider, clock=_OK_CLOCK()).drain()

    # 每篇都过老化门；首篇 EXPIRED→refresh 成功→续期→继续；两篇均取回
    assert report.succeeded == 2 and report.blocked == 0
    assert provider.refresh_calls == 1
    assert env.ctx.auth_sessions[_VENUE].payload_ref == "refreshed"  # session 已换新


# -- §8.3 日配额：达 cap → BLOCKED(config) ------------------------------------


def test_daily_quota_reached_blocks(tmp_path: Path, request: pytest.FixtureRequest) -> None:
    """auth 平台域当日 fetch 尝试篇次达 cap → BLOCKED(config)，fetch handler 不被调用（AC-4.4）。"""
    auth_mock = _AuthGatedMock(fetch_mode="ok")
    # cap 覆盖为 3（机制等价默认 200，测试快）；预置 3 行 fetch_log 占满当日配额
    env = _setup(
        tmp_path,
        request=request,
        auth_mock=auth_mock,
        n_papers=2,
        seed_fetch_logs=3,
        overrides={"auth_daily_cap": 3},
    )
    _enqueue_fetches(env)
    report = _runner(env, provider=_ok_provider(), clock=_OK_CLOCK()).drain()

    assert report.succeeded == 0
    assert report.blocked == 2  # 两篇 fetch 皆因配额 BLOCKED
    assert auth_mock.fetch_calls == 0  # 门前置拦截，未发起取回
    blocked = env.db.query("SELECT blocked_reason FROM task WHERE state = 'BLOCKED'")
    assert all("日配额" in str(r["blocked_reason"]) for r in blocked)


def test_default_daily_cap_is_200() -> None:
    """默认日配额 = 200（auth-framework §8.3 / 04 §4；= runner getattr 兜底常量）。"""
    assert _DEFAULT_AUTH_DAILY_CAP == 200


def test_runner_reads_real_config_field_not_getattr_default(
    tmp_path: Path, request: pytest.FixtureRequest
) -> None:
    """对照测试（controller 令）：Config 有真实字段（config.toml [auth].daily_cap=3）时，runner
    读到真实值 3 而非 getattr 兜底默认 200——达 3 即 BLOCKED（若走默认 200 则不会阻塞）。"""
    auth_mock = _AuthGatedMock(fetch_mode="ok")
    env = _setup(
        tmp_path,
        request=request,
        auth_mock=auth_mock,
        n_papers=1,
        seed_fetch_logs=3,
        config_extra="[auth]\ndaily_cap = 3\n",  # 经 Config.load 落真实字段，非 object.__setattr__
    )
    assert env.config.auth_daily_cap == 3  # 真实字段（非 getattr 默认 200）
    _enqueue_fetches(env)
    report = _runner(env, provider=_ok_provider(), clock=_OK_CLOCK()).drain()

    assert report.blocked == 1 and report.succeeded == 0  # 达真实 cap=3 → BLOCKED
    assert auth_mock.fetch_calls == 0


# -- §8.4 challenge → BLOCKED(challenge) + 平台冷却 24h ------------------------


def test_challenge_blocks_and_writes_cooldown(
    tmp_path: Path, request: pytest.FixtureRequest
) -> None:
    """fetch 命中挑战 → BLOCKED(challenge) + 域冷却落盘；同批后续经冷却门连带 BLOCKED。

    **键粒度回归锁定（E-1，D-030 裁决③）**：落盘文件名此前是 `<adapter_id>.json`，
    现为 `<域>.json`（域取自 asset URL host）——修 aea 一 adapter 双域异质的连坐。
    旧键仍被**读**到（向前兼容），见 `test_challenge_cooldown_persists_across_runs`。
    """
    auth_mock = _AuthGatedMock(fetch_mode="challenge")
    env = _setup(tmp_path, request=request, auth_mock=auth_mock, n_papers=3)
    _enqueue_fetches(env)
    report = _runner(env, provider=_ok_provider(), clock=_OK_CLOCK()).drain()

    assert report.blocked == 3 and report.succeeded == 0
    assert auth_mock.fetch_calls == 1  # 首篇命中 challenge；其余经冷却门拦截，未 fetch
    cooldown_file = env.config.home / "state" / "cooldown" / f"{_DOMAIN}.json"
    assert cooldown_file.is_file()  # 冷却状态落盘（跨运行持久化）
    reasons = env.db.query("SELECT blocked_reason FROM task WHERE state = 'BLOCKED'")
    assert any("challenge" in str(r["blocked_reason"]) for r in reasons)


def test_challenge_cooldown_persists_across_runs(
    tmp_path: Path, request: pytest.FixtureRequest
) -> None:
    """冷却期内新一次运行（新 runner 进程语义）：从 config-home JSON 加载冷却 → 该平台 BLOCKED。

    预置的是**旧格式** `<adapter_id>.json` 键——E-1 后读时两键都查，故上一版本落盘的
    冷却文件仍然生效（向前兼容，无迁移脚本）。
    """
    auth_mock = _AuthGatedMock(fetch_mode="ok")  # 若门放行本会成功——但冷却应拦截
    env = _setup(tmp_path, request=request, auth_mock=auth_mock, n_papers=1)
    # 预置冷却文件（未来 12h）——模拟前次运行已进入冷却
    cooldown_dir = env.config.home / "state" / "cooldown"
    cooldown_dir.mkdir(parents=True, exist_ok=True)
    until = (datetime(2026, 7, 23, 10, 0, 0) + timedelta(hours=12)).isoformat()
    (cooldown_dir / f"{_PLATFORM}.json").write_text(f'{{"until": "{until}"}}', encoding="utf-8")

    _enqueue_fetches(env)
    report = _runner(env, provider=_ok_provider(), clock=_OK_CLOCK()).drain()

    assert report.blocked == 1 and report.succeeded == 0
    assert auth_mock.fetch_calls == 0  # 冷却门拦截，未 fetch


# -- §8.6 工作时段窗：窗外延迟不失败 / 窗内放行 --------------------------------


def test_work_hours_window_outside_blocks_batch(
    tmp_path: Path, request: pytest.FixtureRequest
) -> None:
    """本地 02:00 在窗（8-23）外 → auth_gated 批延迟（BLOCKED，非失败），fetch 不被调用。"""
    auth_mock = _AuthGatedMock(fetch_mode="ok")
    env = _setup(tmp_path, request=request, auth_mock=auth_mock, n_papers=3)
    _enqueue_fetches(env)
    clock = _MutableClock(datetime(2026, 7, 23, 2, 0, 0))  # 02:00 窗外
    report = _runner(env, provider=_ok_provider(), clock=clock).drain()

    assert report.blocked == 3 and report.succeeded == 0 and report.failed == 0
    assert auth_mock.fetch_calls == 0
    reasons = env.db.query("SELECT blocked_reason FROM task WHERE state = 'BLOCKED'")
    assert all("work_hours_window" in str(r["blocked_reason"]) for r in reasons)
    # 延迟不失败 = 可 resume（BLOCKED→PENDING）
    assert env.queue.resume(all_blocked=True) == 3


def test_work_hours_window_inside_proceeds(tmp_path: Path, request: pytest.FixtureRequest) -> None:
    """本地 10:00 在窗内 → 正常放行取回（窗仅约束 auth_gated，不误拦窗内批）。"""
    auth_mock = _AuthGatedMock(fetch_mode="ok")
    env = _setup(tmp_path, request=request, auth_mock=auth_mock, n_papers=2)
    _enqueue_fetches(env)
    report = _runner(
        env, provider=_ok_provider(), clock=_MutableClock(datetime(2026, 7, 23, 10, 0, 0))
    ).drain()

    assert report.succeeded == 2 and report.blocked == 0


def test_work_hours_window_disabled_all_day(tmp_path: Path, request: pytest.FixtureRequest) -> None:
    """窗配置为空串 = 关闭 → 全天放行（即便时刻在旧窗外）。"""
    auth_mock = _AuthGatedMock(fetch_mode="ok")
    env = _setup(
        tmp_path,
        request=request,
        auth_mock=auth_mock,
        n_papers=1,
        overrides={"auth_work_hours": ""},
    )
    _enqueue_fetches(env)
    report = _runner(
        env, provider=_ok_provider(), clock=_MutableClock(datetime(2026, 7, 23, 3, 0, 0))
    ).drain()

    assert report.succeeded == 1 and report.blocked == 0


# -- 回归：oa_fallback 默认关（直建 StageContext）时 no_entitlement 无兜底任务 ----


def test_oa_fallback_disabled_no_derivation(tmp_path: Path, request: pytest.FixtureRequest) -> None:
    """StageContext.oa_fallback=False（默认）→ no_entitlement 独立终态但**不派生** oa_fallback。"""
    auth_mock = _AuthGatedMock(fetch_mode="no_entitlement")
    env = _setup(
        tmp_path,
        request=request,
        auth_mock=auth_mock,
        unpaywall=_FakeUnpaywall([]),
        http=_oa_http(),
    )
    object.__setattr__(env.ctx, "oa_fallback", False)  # 关闭兜底
    _enqueue_fetches(env)
    report = _runner(env, provider=_ok_provider(), clock=_OK_CLOCK()).drain()

    assert report.no_entitlement == 1 and report.failed == 0
    # 无 oa_fallback 任务派生
    assert env.db.query("SELECT id FROM task WHERE kind = 'oa_fallback'") == []


# -- 边界/降级路径覆盖 ---------------------------------------------------------


def test_ensure_session_unavailable_blocks_batch(
    tmp_path: Path, request: pytest.FixtureRequest
) -> None:
    """批入口 ensure_session 抛 AuthRequired（无 session 非交互）→ 整批 BLOCKED(auth)，未 fetch。"""
    auth_mock = _AuthGatedMock(fetch_mode="ok")
    env = _setup(tmp_path, request=request, auth_mock=auth_mock, n_papers=3)
    _enqueue_fetches(env)
    runner = PipelineRunner(
        env.ctx,
        clock=_OK_CLOCK(),
        auth_manager=_FakeAuthManager(_ok_provider(), raise_ensure=True),
    )
    report = runner.drain()

    assert report.blocked == 3 and report.succeeded == 0
    assert auth_mock.fetch_calls == 0


def test_health_check_challenged_blocks_and_cooldown(
    tmp_path: Path, request: pytest.FixtureRequest
) -> None:
    """健康门 health_check→CHALLENGED（非 fetch 抛）→ BLOCKED(challenge) + 平台冷却落盘。"""
    auth_mock = _AuthGatedMock(fetch_mode="ok")
    provider = _FakeProvider(health_seq=[HealthStatus.CHALLENGED])
    env = _setup(
        tmp_path,
        request=request,
        auth_mock=auth_mock,
        n_papers=3,
        overrides={"auth_health_max_age_s": 0.0},
    )
    _enqueue_fetches(env)
    report = _runner(env, provider=provider, clock=_OK_CLOCK()).drain()

    assert report.blocked == 3 and report.succeeded == 0
    assert provider.health_calls == 1 and auth_mock.fetch_calls == 0
    assert (env.config.home / "state" / "cooldown" / f"{_DOMAIN}.json").is_file()


def test_no_entitlement_paper_without_doi_no_oa_fallback(
    tmp_path: Path, request: pytest.FixtureRequest
) -> None:
    """no_entitlement 但 paper 无 doi → 不派生 oa_fallback（AC-4.3：仅有 DOI 才兜底）。"""
    auth_mock = _AuthGatedMock(fetch_mode="no_entitlement")
    env = _setup(
        tmp_path,
        request=request,
        auth_mock=auth_mock,
        unpaywall=_FakeUnpaywall([]),
        http=_oa_http(),
        id_scheme="arxiv",
    )
    _enqueue_fetches(env)
    report = _runner(env, provider=_ok_provider(), clock=_OK_CLOCK()).drain()

    assert report.no_entitlement == 1 and report.failed == 0
    assert env.db.query("SELECT id FROM task WHERE kind = 'oa_fallback'") == []


def test_oa_fallback_no_unpaywall_adapter_skips(
    tmp_path: Path, request: pytest.FixtureRequest
) -> None:
    """oa_fallback 开启但未装配 unpaywall adapter → `_stage_oa_fallback` skipped（不失败）。"""
    auth_mock = _AuthGatedMock(fetch_mode="no_entitlement")
    env = _setup(tmp_path, request=request, auth_mock=auth_mock, unpaywall=None, http=_oa_http())
    _enqueue_fetches(env)
    report = _runner(env, provider=_ok_provider(), clock=_OK_CLOCK()).drain()

    assert report.no_entitlement == 1 and report.failed == 0
    # oa_fallback 任务被派生但因无 adapter 而 skipped；无 OA asset 落盘
    assert env.repo.list_assets(venue_id=_VENUE, state="fetched") == []


def test_oa_direct_fetch_no_http_client_skips(
    tmp_path: Path, request: pytest.FixtureRequest
) -> None:
    """OA plan 已产但 StageContext.http 未注入 → `_fetch_oa_direct` skipped（asset 停 planned）。"""
    auth_mock = _AuthGatedMock(fetch_mode="no_entitlement")
    ua = _FakeUnpaywall(
        [
            AssetPlan(
                kind=AssetKind.PDF,
                url="https://oa.example.org/copy.pdf",
                url_strategy=UrlStrategy.DIRECT,
                version="publishedVersion",
            )
        ]
    )
    env = _setup(tmp_path, request=request, auth_mock=auth_mock, unpaywall=ua, http=None)  # 无 http
    _enqueue_fetches(env)
    report = _runner(env, provider=_ok_provider(), clock=_OK_CLOCK()).drain()

    assert report.no_entitlement == 1 and report.failed == 0
    assert env.repo.list_assets(venue_id=_VENUE, state="fetched") == []
    assert len(env.repo.list_assets(venue_id=_VENUE, state="planned")) == 1  # OA asset 停 planned


def test_oa_direct_fetch_non_pdf_fails_integrity(
    tmp_path: Path, request: pytest.FixtureRequest
) -> None:
    """OA host 返非 %PDF → INTEGRITY（fetch_log 记 error + .part 清理），OA asset 未 fetched。"""
    auth_mock = _AuthGatedMock(fetch_mode="no_entitlement")
    ua = _FakeUnpaywall(
        [
            AssetPlan(
                kind=AssetKind.PDF,
                url="https://oa.example.org/copy.pdf",
                url_strategy=UrlStrategy.DIRECT,
                version="publishedVersion",
            )
        ]
    )
    bad_http = HttpClient(
        user_agent="pc-test",
        transport=httpx.MockTransport(lambda req: httpx.Response(200, content=b"<html>x</html>")),
    )
    env = _setup(tmp_path, request=request, auth_mock=auth_mock, unpaywall=ua, http=bad_http)
    _enqueue_fetches(env)
    report = _runner(env, provider=_ok_provider(), clock=_OK_CLOCK()).drain()

    assert report.no_entitlement == 1
    assert env.repo.list_assets(venue_id=_VENUE, state="fetched") == []
    integrity_logs = [
        r for r in env.repo.fetch_logs(domain="oa.example.org") if r["error_class"] == "integrity"
    ]
    assert integrity_logs  # OA direct 失败路径写了 integrity fetch_log
    assert list((env.config.data_dir / "tmp").glob("*.part")) == []  # .part 已清理


# -- 工作时段窗解析纯函数（§8.6；含 fail-open 边界）---------------------------


@pytest.mark.parametrize(
    ("window", "hour", "expected"),
    [
        ("8-23", 10, True),  # 窗内
        ("8-23", 8, True),  # 起始含
        ("8-23", 23, False),  # 结束不含
        ("8-23", 2, False),  # 窗外
        ("", 3, True),  # 空 = 关闭窗（全天放行）
        ("0-24", 3, True),  # 全天窗
        ("nodashvalue", 3, True),  # 无 '-' → fail-open
        ("a-b", 3, True),  # 非数字 → fail-open（配置笔误不拦批）
    ],
)
def test_work_hours_ok_boundaries(window: str, hour: int, expected: bool) -> None:
    assert _work_hours_ok(window, datetime(2026, 7, 23, hour, 0, 0)) is expected


# -- MAJOR-1：elsevier_sd resolve 阶段 entitlement 预检否 → NE → OA-fallback（AC-4.3 真实载体）--


def test_elsevier_resolve_entitlement_false_derives_oa_fallback(
    tmp_path: Path, request: pytest.FixtureRequest
) -> None:
    """MAJOR-1 / AC-4.3 真实载体（fable 审查必修）：真实 `ElsevierScienceDirectAdapter` 在
    **resolve** 阶段 entitlement 预检 entitled:false → 抛 NE（非 fetch 阶段）→ runner 从
    params["paper"] 派生 oa_fallback → unpaywall OA 副本 direct 落盘。不计 failed（§8.5）。

    此前 NE 派生仅限 kind=="fetch"（asset_id 门控），resolve NE 不派生——elsevier 无权 DOI
    得不到 OA 兜底，AC-4.3 破。本测试是修复的端到端断言（真实 elsevier 场景，非泛 mock）。
    """
    doi = "10.1016/j.example.notsubscribed"
    # 真实 elsevier adapter：MockTransport 回 entitled:false 封套（fixture 02 结构）+ key
    ent_false = (
        b'{"entitlement-response":{"document-entitlement":'
        b'{"@status":"found","doi":"' + doi.encode() + b'","entitled":false}}}'
    )
    els = ElsevierScienceDirectAdapter(
        HttpClient(
            user_agent="pc-test",
            transport=httpx.MockTransport(lambda req: httpx.Response(200, content=ent_false)),
        )
    )
    els.set_api_key("test-key")

    home = tmp_path / "home"
    venues = home / "venues"
    venues.mkdir(parents=True)
    (home / "config.toml").write_text('[paths]\nvenues_dirs = ["venues"]\n', encoding="utf-8")
    (venues / "els_venue.yaml").write_text(
        yaml.safe_dump(
            {
                "id": "els_venue",
                "kind": "journal",
                "names": {"full": "Els Venue", "aliases": []},
                "field": ["finance"],
                "identifiers": {"issn": ["0000-0000"]},
                "fulltext_source": "elsevier_sd",
                "auth": {"level": "institutional"},
            }
        ),
        encoding="utf-8",
    )
    config = Config.load(home)
    setup_logging(config.log_dir, console_level="CRITICAL")
    db = Database(config.db_path)
    request.addfinalizer(db.close)  # 资源纪律（post-phase5-audit §3[S4]）：测试结束必关连接
    db.migrate()
    repo = Repo(db)
    queue = TaskQueue(db)
    ua = _FakeUnpaywall(
        [
            AssetPlan(
                kind=AssetKind.PDF,
                url="https://oa.example.org/copy.pdf",
                url_strategy=UrlStrategy.DIRECT,
                version="publishedVersion",
            )
        ]
    )
    registry = VenueRegistry({"elsevier_sd": els, "unpaywall": ua})
    registry.load_dirs([venues])
    repo.upsert_venue(registry.get("els_venue"))
    paper_id = repo.upsert_paper(
        "els_venue", None, PaperStub(title="unsubscribed", identifiers=(("doi", doi),))
    )
    ctx = StageContext(
        config=config,
        db=db,
        repo=repo,
        registry=registry,
        queue=queue,
        limiter=RateLimiter(scale=config.rate_scale),
        sleeper=[].append,
        oa_fallback=True,
        unpaywall_adapter=ua,
        http=_oa_http(),
    )
    queue.enqueue("resolve", "els_venue", {"paper": paper_id})  # resolve 任务（elsevier 预检）
    runner = PipelineRunner(ctx, clock=_OK_CLOCK(), auth_manager=_FakeAuthManager(_ok_provider()))
    report = runner.drain()

    # resolve 阶段 entitled:false → NE 独立终态（不计 failed）→ oa_fallback → OA 副本落盘
    assert report.no_entitlement == 1 and report.failed == 0
    assert ua.calls == 1  # unpaywall 被查（派生生效）
    fetched = repo.list_assets(venue_id="els_venue", state="fetched")
    assert len(fetched) == 1 and fetched[0]["source_adapter"] == "unpaywall"
    assert Path(str(fetched[0]["file_path"])).is_file()  # OA 副本 %PDF 落盘


# -- MAJOR-2：INTEGRITY（伪装 PDF）→ 强制下个 fetch 健康门（§8.2 文件验证器联动）--------------


def test_integrity_forces_health_check_on_next_fetch(
    tmp_path: Path, request: pytest.FixtureRequest
) -> None:
    """MAJOR-2（fable 审查必修）：auth_gated fetch 得非 %PDF（拦截页伪装）→ INTEGRITY → 门龄
    归零 → 下个 fetch（重试）**强制 health_check**（防伪装 PDF 连环命中）。此前未实现。"""
    auth_mock = _AuthGatedMock(fetch_mode="bad_pdf")
    provider = _ok_provider()  # health 恒 OK（验证"强制探测发生"，非探测结果）
    env = _setup(tmp_path, request=request, auth_mock=auth_mock, n_papers=1)
    _enqueue_fetches(env)
    report = _runner(env, provider=provider, clock=_OK_CLOCK()).drain()

    # INTEGRITY RetrySpec(2)：attempt1 INTEGRITY→门龄归零；attempt2 前老化门必触发 health_check
    # →仍 bad_pdf→INTEGRITY→FAILED。健康门被 INTEGRITY 强制探测恰 1 次（无本修复则为 0）。
    assert report.failed == 1
    assert auth_mock.fetch_calls == 2  # 两次尝试
    assert provider.health_calls == 1  # INTEGRITY 强制下个 fetch 必探（§8.2 联动）


# -- MINOR-1：OA-direct 幂等跳过（已 fetched 不因再入队/--force 重下）--------------------------


def test_oa_direct_fetch_idempotent_skip_when_already_fetched(
    tmp_path: Path, request: pytest.FixtureRequest
) -> None:
    """MINOR-1：OA 副本已 fetched 且文件校验合格 → `_fetch_oa_direct` 幂等跳过（不真实重下）。"""
    import hashlib

    env = _setup(
        tmp_path, request=request, auth_mock=_AuthGatedMock(fetch_mode="ok"), http=_oa_http()
    )
    paper_id = env.repo.upsert_paper(
        "auth_venue", None, PaperStub(title="oa", identifiers=(("doi", "10.9/oa"),))
    )
    oa_asset = env.repo.plan_asset(
        paper_id,
        AssetPlan(
            kind=AssetKind.PDF, url="https://oa.example.org/x.pdf", version="publishedVersion"
        ),
        "unpaywall",
    )
    # 落一个合格 %PDF + mark fetched（sha 对上 → fetched_file_ok 通过）
    pdf_path = env.config.data_dir / "oa_copy.pdf"
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pdf_path.write_bytes(_PDF)
    env.repo.mark_asset(
        oa_asset,
        state="fetched",
        file_path=str(pdf_path),
        bytes_=len(_PDF),
        sha256=hashlib.sha256(_PDF).hexdigest(),
    )
    env.queue.enqueue("fetch", "auth_venue", {"asset": oa_asset}, force=True)
    report = _runner(env, provider=_ok_provider(), clock=_OK_CLOCK()).drain()

    assert report.skipped == 1 and report.succeeded == 0  # OA 分支幂等跳过


# -- P1-11：EZProxy `rewrite_url` 生产接线（07 §3.2「fetch 前统一调用」）---------------------


def test_ezproxy_provider_rewrites_url_before_fetch(
    tmp_path: Path, request: pytest.FixtureRequest
) -> None:
    """ezproxy provider 在场 → adapter 收到的 plan.url 已是代理形态（adapter 不感知代理）。

    同时锁死三条口径分离（07 §3.2 + 04 §5/§7）：
    - FetchLog.url = **实际发出**的代理形态 URL（合理使用自证材料记"我到底请求了什么"）；
    - FetchLog.domain 仍 = 平台主域（AC-4.4 日配额对账口径不被代理域打散）；
    - asset.url 落库仍是 adapter 给的规范引用（§4.4 落盘纪律；冷却键读侧同源）。
    """
    auth_mock = _AuthGatedMock(fetch_mode="ok")
    env = _setup(tmp_path, request=request, auth_mock=auth_mock, n_papers=1)
    _enqueue_fetches(env)
    report = _runner(
        env, provider=_EZProxyFakeProvider(tmp_path / "home"), clock=_OK_CLOCK()
    ).drain()

    proxied = f"https://{_EZ_PROXIED_HOST}/pdf/10.1/auth.0"
    assert report.succeeded == 1
    assert auth_mock.fetch_urls == [proxied]  # 实际发出的请求 URL = 代理形态
    logs = env.repo.fetch_logs(domain=_DOMAIN)
    assert [str(r["url"]) for r in logs] == [proxied]  # 审计记实发 URL
    assert all(str(r["domain"]) == _DOMAIN for r in logs)  # 归属域不变（配额对账不打散）
    asset = env.repo.get_asset(env.asset_ids[0])
    assert asset is not None
    assert str(asset["url"]) == f"https://{_DOMAIN}/pdf/10.1/auth.0"  # 落库仍规范 URL


def test_ezproxy_failure_path_fetch_log_records_proxied_url(
    tmp_path: Path, request: pytest.FixtureRequest
) -> None:
    """失败路径同口径：`_stage_fetch` 的失败 fetch_log 也记实发（代理形态）URL。"""
    auth_mock = _AuthGatedMock(fetch_mode="auth_expired")
    env = _setup(tmp_path, request=request, auth_mock=auth_mock, n_papers=1)
    _enqueue_fetches(env)
    report = _runner(
        env, provider=_EZProxyFakeProvider(tmp_path / "home"), clock=_OK_CLOCK()
    ).drain()

    assert report.blocked == 1
    logs = env.repo.fetch_logs(domain=_DOMAIN)
    assert [str(r["url"]) for r in logs] == [f"https://{_EZ_PROXIED_HOST}/pdf/10.1/auth.0"]
    assert str(logs[0]["error_class"]) == "auth_expired"


def test_ezproxy_rewrite_idempotent_in_fetch_path(
    tmp_path: Path, request: pytest.FixtureRequest
) -> None:
    """adapter 已给出代理形态 URL（用户自己配了代理直链）→ 不二次套代理（幂等，§3.4）。"""
    auth_mock = _AuthGatedMock(fetch_mode="ok", plan_host=_EZ_PROXIED_HOST)
    env = _setup(tmp_path, request=request, auth_mock=auth_mock, n_papers=1)
    _enqueue_fetches(env)
    report = _runner(
        env, provider=_EZProxyFakeProvider(tmp_path / "home"), clock=_OK_CLOCK()
    ).drain()

    assert report.succeeded == 1
    assert auth_mock.fetch_urls == [f"https://{_EZ_PROXIED_HOST}/pdf/10.1/auth.0"]


def test_non_ezproxy_provider_leaves_fetch_url_unchanged(
    tmp_path: Path, request: pytest.FixtureRequest
) -> None:
    """非 ezproxy provider（`AuthProviderBase.rewrite_url` 恒等 / duck-typed 无该方法）
    → URL 逐字不变（回归锁定：接线对既有三 provider 零影响）。"""
    auth_mock = _AuthGatedMock(fetch_mode="ok")
    env = _setup(tmp_path, request=request, auth_mock=auth_mock, n_papers=1)
    _enqueue_fetches(env)
    report = _runner(env, provider=_ok_provider(), clock=_OK_CLOCK()).drain()

    assert report.succeeded == 1
    assert auth_mock.fetch_urls == [f"https://{_DOMAIN}/pdf/10.1/auth.0"]


def test_oa_fallback_direct_fetch_not_proxied(
    tmp_path: Path, request: pytest.FixtureRequest
) -> None:
    """边界（不扩大）：OA-fallback 第三方 host 走无凭证 direct 通道，**不过机构代理**。"""
    seen: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(str(req.url))
        return httpx.Response(200, content=_PDF)

    auth_mock = _AuthGatedMock(fetch_mode="no_entitlement")
    ua = _FakeUnpaywall(
        [
            AssetPlan(
                kind=AssetKind.PDF,
                url="https://oa.example.org/copy.pdf",
                url_strategy=UrlStrategy.DIRECT,
                version="publishedVersion",
            )
        ]
    )
    env = _setup(
        tmp_path,
        request=request,
        auth_mock=auth_mock,
        unpaywall=ua,
        http=HttpClient(user_agent="pc-test", transport=httpx.MockTransport(handler)),
        n_papers=1,
    )
    _enqueue_fetches(env)
    report = _runner(
        env, provider=_EZProxyFakeProvider(tmp_path / "home"), clock=_OK_CLOCK()
    ).drain()

    assert report.no_entitlement == 1
    assert seen == ["https://oa.example.org/copy.pdf"]  # OA 域零改写
