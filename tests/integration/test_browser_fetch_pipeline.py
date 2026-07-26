"""browser-fetch 通道的 pipeline 集成（design/11 §8 T-5/T-10 + §9 integration 行）。

**真 sqlite + 真落盘 + 假 launcher**，零真实浏览器、零网络：

- 三级门（§7.1 L1）：config/ctx 任一关 → `skipped`（不派生失败、不落 fetch_log）；
- OK 路径全链：`PartFileIO` → 魔数 → 原子落位 → `finalize_fetch` 组合事务（asset fetched +
  成功 fetch_log 行，DB↔文件 sha256 对账一致）；
- T-5 预算护栏三判定走**真库真文件**：配额边界（cap−1 放行 / cap 熔断）、冷却 JSON 优先于
  配额、当日连续失败 ≥3 熔断；配额/冷却拒绝**不落 fetch_log**（非尝试）；
- 四态：CHALLENGE→`Challenged`、LOGIN_REDIRECT→`AuthRequired`、NO_ENTITLEMENT→
  `CrawlerError(NO_ENTITLEMENT)`（接既有 OA-fallback 链）——三者各落一条失败 fetch_log；
- T-10 obslog：`channel="browser"` + `verdict` + `quota_used`/`quota_cap` 落 jsonl，URL 脱敏。
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Callable, Iterator
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import yaml

import paper_crawler.pipeline.stages as stages_mod
from paper_crawler.adapter import AdapterBase, AdapterFamily, load_adapters
from paper_crawler.browserfetch import BrowserFetchHandle, PageResponse
from paper_crawler.config import Config
from paper_crawler.errors import AuthRequired, Challenged, CrawlerError, ErrorClass
from paper_crawler.obslog import setup_logging
from paper_crawler.pipeline import StageContext
from paper_crawler.pipeline.report import RunReport
from paper_crawler.pipeline.stages import execute_stage
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
    IssueRef,
    PaperStub,
    RatePolicy,
    SessionBackend,
    SessionHandle,
    UrlStrategy,
    VenueSpec,
    utcnow_iso,
)

VENUE = "render_journal"
DOMAIN = "papers.render.test"
LANDING = f"https://{DOMAIN}/sol3/papers.cfm?abstract_id=42"
PDF_BYTES = b"%PDF-1.4\n" + b"0" * 1024 + b"\n%%EOF\n"


class RenderPageAdapter(AdapterBase):
    """只产 `RENDER_PAGE` 计划的 fixture adapter（三消费方接入归 T11，此处只驱动接缝）。"""

    adapter_id = "render_mock"
    family: AdapterFamily = "open_access"  # E-1 前的冷却盲区面，恰是本通道主消费方形态
    capabilities = (
        Capability.DISCOVER | Capability.ENUMERATE | Capability.RESOLVE | Capability.FETCH
    )
    default_rate = RatePolicy(600, source_note="fixture adapter，无真实站点")
    auth_requirement = AuthLevel.NONE
    domains: tuple[str, ...] = (DOMAIN,)
    resolve_offline = True

    def resolve_assets(
        self, venue: VenueSpec, paper: PaperStub, session: SessionHandle | None = None
    ) -> list[AssetPlan]:
        return [AssetPlan(kind=AssetKind.PDF, url=LANDING, url_strategy=UrlStrategy.RENDER_PAGE)]


class FakeHandle:
    """假 `BrowserFetchHandle`（同 tests/unit 的形状，此处驱动全 stage 链）。"""

    def __init__(self, response: PageResponse, payload: bytes = PDF_BYTES) -> None:
        self.response = response
        self.payload = payload
        self.calls: list[str] = []
        self.launched: list[tuple[str, bytes | None]] = []  # (user_data_dir, storage_state)
        self.identity_headers: list[str | None] = []

    def goto(self, url: str) -> PageResponse:
        self.calls.append(f"goto:{url}")
        return self.response

    def download_via(self, trigger: Callable[[], None], dest: Path) -> int:
        self.calls.append("download_via")
        trigger()
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(self.payload)
        return len(self.payload)

    def close(self) -> None:
        self.calls.append("close")


def ok_page() -> PageResponse:
    return PageResponse(
        status=200,
        headers={"content-type": "text/html"},
        final_url=LANDING,
        body=b"<html>signed in as prof; citation_pdf_url</html>",
    )


def challenge_page() -> PageResponse:
    return PageResponse(
        status=403, headers={"cf-mitigated": "challenge"}, final_url=LANDING, body=b"403"
    )


def login_page() -> PageResponse:
    return PageResponse(
        status=302, headers={}, final_url=f"https://{DOMAIN}/signin", body=b"sign in"
    )


def no_entitlement_page() -> PageResponse:
    return PageResponse(
        status=200,
        headers={},
        final_url=f"https://{DOMAIN}/doi/article-abstract/42",
        body=b"<html>Get access</html>",
    )


@dataclass
class Env:
    config: Config
    db: Database
    repo: Repo
    queue: TaskQueue
    ctx: StageContext
    sleeps: list[float]
    asset_id: str
    task: sqlite3.Row

    def close(self) -> None:
        self.db.close()

    def fetch_logs(self) -> list[sqlite3.Row]:
        return self.repo.fetch_logs()

    def asset_row(self) -> sqlite3.Row:
        row = self.repo.get_asset(self.asset_id)
        assert row is not None
        return row

    def log_lines(self) -> list[dict[str, object]]:
        lines: list[dict[str, object]] = []
        for path in self.config.log_dir.glob("*.jsonl"):
            for raw in path.read_text(encoding="utf-8").splitlines():
                if raw.strip():
                    lines.append(json.loads(raw))
        return lines


def _write_venue(venues_dir: Path) -> None:
    venues_dir.mkdir(parents=True, exist_ok=True)
    (venues_dir / f"{VENUE}.yaml").write_text(
        yaml.safe_dump(
            {
                "id": VENUE,
                "kind": "journal",
                "names": {"full": "Render Journal"},
                "field": ["econ"],
                "identifiers": {"issn": ["0000-0002"]},
                "metadata_source": "render_mock",
                "fulltext_source": "render_mock",
                "auth": {"level": "none"},
                "status": "active",
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )


@pytest.fixture
def env(tmp_path: Path) -> Iterator[Env]:
    home = tmp_path / "home"
    venues_dir = tmp_path / "venues"
    _write_venue(venues_dir)
    config = Config(
        home=home,
        data_dir=home / "data",
        db_path=home / "catalog.sqlite",
        log_dir=home / "logs",
        reports_dir=home / "reports",
        venues_dirs=(venues_dir,),
        browser_fetch_enabled=True,
        browser_daily_cap=50,
        browser_jitter_s=(0.0, 0.0),  # 假时钟纪律：抖动关掉才能精确断言等待序列
    )
    setup_logging(config.log_dir, console_level="CRITICAL")
    db = Database(config.db_path)
    db.migrate()
    repo = Repo(db)
    queue = TaskQueue(db)

    adapters = load_adapters()
    adapters["render_mock"] = RenderPageAdapter()
    registry = VenueRegistry(adapters)
    assert registry.load_dirs([venues_dir]) == []
    repo.upsert_venue(registry.get(VENUE))

    issue_id = repo.upsert_issue(IssueRef(venue_id=VENUE, volume="1", number="1"), source="fixture")
    paper_id = repo.upsert_paper(
        VENUE,
        issue_id,
        PaperStub(title="A Render Paper", identifiers=(("doi", "10.9999/render.1"),), year=2026),
    )
    asset_id = repo.plan_asset(
        paper_id,
        AssetPlan(kind=AssetKind.PDF, url=LANDING, url_strategy=UrlStrategy.RENDER_PAGE),
        "render_mock",
    )
    sleeps: list[float] = []
    ctx = StageContext(
        config=config,
        db=db,
        repo=repo,
        registry=registry,
        queue=queue,
        limiter=RateLimiter(),
        sleeper=sleeps.append,
        browser_fetch=True,
    )
    result = queue.enqueue("fetch", VENUE, {"asset": asset_id})
    task = queue.get(result.task_id)
    assert task is not None
    e = Env(
        config=config,
        db=db,
        repo=repo,
        queue=queue,
        ctx=ctx,
        sleeps=sleeps,
        asset_id=asset_id,
        task=task,
    )
    yield e
    e.close()


def run_stage(env: Env, handle: FakeHandle, monkeypatch: pytest.MonkeyPatch) -> str:
    """注入假 launcher（替换 stages 消费的工厂），执行 fetch stage。"""

    def fake_factory(*, identity_header: str | None = None) -> object:
        handle.identity_headers.append(identity_header)

        def _launch(user_data_dir: str, storage_state: bytes | None) -> BrowserFetchHandle:
            handle.launched.append((user_data_dir, storage_state))
            return handle  # type: ignore[return-value]

        return _launch

    monkeypatch.setattr(stages_mod, "playwright_launcher", fake_factory)
    report = RunReport(command="grab", venue_id=VENUE, started_at=utcnow_iso())
    return execute_stage(env.ctx, env.task, report)


def seed_fetch_log(env: Env, *, count: int, error_class: str | None = None) -> None:
    """预置当日 fetch_log 行（带 task_id → 计入 venue×域维度派生查询）。"""
    for _ in range(count):
        env.repo.add_fetch_log(
            asset_id=env.asset_id,
            task_id=str(env.task["id"]),
            domain=DOMAIN,
            url=LANDING,
            http_status=None,
            bytes_=0,
            elapsed_ms=1,
            rate_wait_ms=0,
            error_class=error_class,
        )


def seed_cooldown(env: Env, key: str, *, hours: float = 12.0) -> None:
    path = env.config.home / "state" / "cooldown" / f"{key}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    until = (datetime.now(UTC) + timedelta(hours=hours)).isoformat()
    path.write_text(json.dumps({"until": until}), encoding="utf-8")


# ---------------------------------------------------------------------------
# 三级门（§7.1 L1）
# ---------------------------------------------------------------------------


def test_disabled_by_ctx_slot_is_skipped_not_failed(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CLI 未给 --browser（ctx 槽关）→ skipped；不派生失败、不落 fetch_log（§4.6 裁决）。"""
    env.ctx.browser_fetch = False
    handle = FakeHandle(ok_page())
    assert run_stage(env, handle, monkeypatch) == "skipped"
    assert handle.calls == []  # 浏览器根本没起
    assert env.fetch_logs() == []
    assert str(env.asset_row()["state"]) == "planned"


def test_disabled_by_config_is_skipped(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    """config 关（即便 ctx 槽开）→ 同样 skipped：三级门任一关都不走通道。"""
    env.ctx.config = replace(env.config, browser_fetch_enabled=False)
    handle = FakeHandle(ok_page())
    assert run_stage(env, handle, monkeypatch) == "skipped"
    assert env.fetch_logs() == []


# ---------------------------------------------------------------------------
# OK 路径全链（落盘三原语 + 组合事务 + T-10 obslog）
# ---------------------------------------------------------------------------


def test_ok_path_lands_file_and_finalizes(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    handle = FakeHandle(ok_page())
    assert run_stage(env, handle, monkeypatch) == "done"

    asset = env.asset_row()
    assert str(asset["state"]) == "fetched"
    landed = Path(str(asset["file_path"]))
    assert landed.read_bytes() == PDF_BYTES
    # design/06 §4 落位布局：data/pdf/<venue>/<year>/<paper_ulid>.pdf
    assert landed.relative_to(env.config.data_dir).parts[:3] == ("pdf", VENUE, "2026")
    assert landed.name == f"{asset['paper_id']}.pdf"
    assert int(asset["bytes"]) == len(PDF_BYTES)
    # DB↔文件 sha256 对账（verify.py 口径）
    assert str(asset["sha256"]) == hashlib.sha256(PDF_BYTES).hexdigest()
    # .part 不残留
    assert list((env.config.data_dir / "tmp").glob("*.part")) == []

    logs = env.fetch_logs()
    assert len(logs) == 1  # 一次尝试恰好一行（§7.2 口径）
    assert str(logs[0]["domain"]) == DOMAIN
    assert logs[0]["error_class"] is None
    assert str(logs[0]["task_id"]) == str(env.task["id"])


def test_t10_obslog_records_browser_channel(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    run_stage(env, FakeHandle(ok_page()), monkeypatch)
    events = [line for line in env.log_lines() if line.get("channel") == "browser"]
    assert len(events) == 1
    event = events[0]
    assert event["verdict"] == "ok"
    assert event["stage"] == "fetch"
    assert event["domain"] == DOMAIN
    assert event["quota_used"] == 0 and event["quota_cap"] == 50
    assert "rate_wait_ms" in event and "elapsed_ms" in event
    assert "cookie" not in json.dumps(event).lower()  # 脱敏面：无凭证形态残留


def test_t10_obslog_records_challenge_verdict(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(Challenged):
        run_stage(env, FakeHandle(challenge_page()), monkeypatch)
    events = [line for line in env.log_lines() if line.get("channel") == "browser"]
    assert [e["verdict"] for e in events] == ["challenge"]
    assert events[0]["level"] == "WARNING"


# ---------------------------------------------------------------------------
# 四态在 stage 层的处置
# ---------------------------------------------------------------------------


def test_challenge_raises_and_logs_failure_row(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    handle = FakeHandle(challenge_page())
    with pytest.raises(Challenged):
        run_stage(env, handle, monkeypatch)
    assert "download_via" not in handle.calls  # 红线：检测即停
    logs = env.fetch_logs()
    assert [str(r["error_class"]) for r in logs] == [ErrorClass.CHALLENGE.value]
    assert str(env.asset_row()["state"]) == "planned"  # 未落盘，状态不前进
    assert list((env.config.data_dir / "tmp").glob("*.part")) == []


def test_login_redirect_raises_auth_required(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(AuthRequired):
        run_stage(env, FakeHandle(login_page()), monkeypatch)
    assert [str(r["error_class"]) for r in env.fetch_logs()] == [ErrorClass.AUTH_EXPIRED.value]


def test_no_entitlement_raises_for_existing_oa_chain(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    """无权限 → `CrawlerError(NO_ENTITLEMENT)`：接既有 runner 链（不计 failures + OA 兜底）。"""
    with pytest.raises(CrawlerError) as excinfo:
        run_stage(env, FakeHandle(no_entitlement_page()), monkeypatch)
    assert excinfo.value.error_class is ErrorClass.NO_ENTITLEMENT
    assert [str(r["error_class"]) for r in env.fetch_logs()] == [ErrorClass.NO_ENTITLEMENT.value]


def test_non_pdf_payload_is_integrity_auth_leak(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    """魔数校验不绕过：拦截页伪装成 PDF → `INTEGRITY(auth_leak)`。"""
    handle = FakeHandle(ok_page(), payload=b"<html>login wall</html>")
    with pytest.raises(CrawlerError) as excinfo:
        run_stage(env, handle, monkeypatch)
    assert excinfo.value.error_class is ErrorClass.INTEGRITY
    assert excinfo.value.detail == "auth_leak"


# ---------------------------------------------------------------------------
# T-5 预算护栏（真库 + 真冷却文件）
# ---------------------------------------------------------------------------


def test_t5_quota_boundary_allows_cap_minus_one(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    env.ctx.config = replace(env.config, browser_daily_cap=3)
    seed_fetch_log(env, count=2)
    assert run_stage(env, FakeHandle(ok_page()), monkeypatch) == "done"


def test_t5_quota_blocks_at_cap_without_extra_fetch_log(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    env.ctx.config = replace(env.config, browser_daily_cap=3)
    seed_fetch_log(env, count=3)
    handle = FakeHandle(ok_page())
    with pytest.raises(CrawlerError) as excinfo:
        run_stage(env, handle, monkeypatch)
    assert excinfo.value.error_class is ErrorClass.CONFIG
    assert excinfo.value.detail == "browser_quota"
    assert handle.calls == []
    assert len(env.fetch_logs()) == 3  # 配额拒绝不是"一次尝试"，不落新行


def test_t5_quota_is_scoped_to_venue_and_domain(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    """venue×域维度经 `fetch_log ⋈ task` 派生：他域的行不占本域配额。"""
    env.ctx.config = replace(env.config, browser_daily_cap=1)
    env.repo.add_fetch_log(
        asset_id=env.asset_id,
        task_id=str(env.task["id"]),
        domain="other.example.test",
        url="https://other.example.test/x.pdf",
        http_status=None,
        bytes_=1,
        elapsed_ms=1,
        rate_wait_ms=0,
    )
    assert run_stage(env, FakeHandle(ok_page()), monkeypatch) == "done"


def test_t5_cooldown_precedes_quota(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    """域冷却（runner 写的 JSON）优先于配额：抛 CHALLENGE 且零请求。"""
    env.ctx.config = replace(env.config, browser_daily_cap=1)
    seed_fetch_log(env, count=99)
    seed_cooldown(env, DOMAIN)
    handle = FakeHandle(ok_page())
    with pytest.raises(Challenged) as excinfo:
        run_stage(env, handle, monkeypatch)
    assert excinfo.value.detail == "browser_cooldown"
    assert handle.calls == []


def test_t5_breaker_after_three_consecutive_failures(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed_fetch_log(env, count=3, error_class=ErrorClass.TRANSIENT.value)
    handle = FakeHandle(ok_page())
    with pytest.raises(CrawlerError) as excinfo:
        run_stage(env, handle, monkeypatch)
    assert excinfo.value.detail == "browser_breaker"
    assert handle.calls == []


def test_t5_no_entitlement_rows_do_not_trip_the_breaker(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    """NE 是独立终态、**不是失败**（auth-framework §8.5 / §7.1 L4 字面"非挑战失败"）：
    连续三篇无订阅不得误熔断整个域（审查 P2-2 回归）。"""
    seed_fetch_log(env, count=3, error_class=ErrorClass.NO_ENTITLEMENT.value)
    assert run_stage(env, FakeHandle(ok_page()), monkeypatch) == "done"


def test_t5_no_entitlement_rows_are_transparent_to_the_streak(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    """NE 行对判据**完全透明**：既不累加、也不当成功打断——夹在失败之间的 NE 不掩盖熔断。"""
    seed_fetch_log(env, count=2, error_class=ErrorClass.TRANSIENT.value)
    seed_fetch_log(env, count=1, error_class=ErrorClass.NO_ENTITLEMENT.value)
    seed_fetch_log(env, count=1, error_class=ErrorClass.TRANSIENT.value)
    with pytest.raises(CrawlerError) as excinfo:
        run_stage(env, FakeHandle(ok_page()), monkeypatch)
    assert excinfo.value.detail == "browser_breaker"


def test_t5_breaker_resets_after_a_success(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    """当日出现一次成功即解除熔断（连续性判据自最新起、遇成功即止）。"""
    seed_fetch_log(env, count=3, error_class=ErrorClass.TRANSIENT.value)
    seed_fetch_log(env, count=1)  # 最新一条成功
    assert run_stage(env, FakeHandle(ok_page()), monkeypatch) == "done"


# ---------------------------------------------------------------------------
# storage_state 复用链（§4.3）+ 诚实身份（红线 §2-3）
# ---------------------------------------------------------------------------


def test_no_session_launches_clean_context(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    """无 session → `storage_state=None` 干净上下文（**合法路径**，非错误）。"""
    handle = FakeHandle(ok_page())
    run_stage(env, handle, monkeypatch)
    assert handle.launched[0][1] is None


def test_non_playwright_session_is_not_injected(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    """cookie/bearer 档 session 不误当 storage_state 注入浏览器（凭证面隔离）。"""
    env.ctx.auth_sessions[VENUE] = SessionHandle(
        provider_id="p",
        backend=SessionBackend.BEARER_TOKEN,
        payload_ref="ref",
        established_at=datetime.now(UTC),
    )
    handle = FakeHandle(ok_page())
    run_stage(env, handle, monkeypatch)
    assert handle.launched[0][1] is None


def test_playwright_session_state_is_decrypted_and_passed(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`playwright_state` 档：经 `CredentialStore.read_state(payload_ref)` 解密后**只入内存**。"""
    seen_refs: list[str] = []

    class StubStore:
        def __init__(self, home: Path) -> None:
            self.home = home

        def read_state(self, ref: str) -> bytes:
            seen_refs.append(ref)
            return b'{"cookies": [{"name": "sid", "value": "x"}]}'

    monkeypatch.setattr(stages_mod, "CredentialStore", StubStore)
    env.ctx.auth_sessions[VENUE] = SessionHandle(
        provider_id="p",
        backend=SessionBackend.PLAYWRIGHT_STATE,
        payload_ref="render@campus",
        established_at=datetime.now(UTC),
    )
    handle = FakeHandle(ok_page())
    run_stage(env, handle, monkeypatch)
    assert seen_refs == ["render@campus"]
    assert handle.launched[0][1] == b'{"cookies": [{"name": "sid", "value": "x"}]}'


def test_identity_header_is_honest_ua_string(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    """D-014 诚实身份：launcher 拿到本系统 UA 串（不伪装成纯浏览器）。"""
    env.ctx.config = replace(env.config, identity_email="you@example.edu")
    handle = FakeHandle(ok_page())
    run_stage(env, handle, monkeypatch)
    header = handle.identity_headers[0]
    assert header is not None
    assert header.startswith("PaperCrawler/")
    assert "mailto:you@example.edu" in header


# ---------------------------------------------------------------------------
# 限速闸（§7.1 L2）
# ---------------------------------------------------------------------------


def test_rate_gate_charges_每次导航(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    """判定导航 + 下载触发各过一次域级闸（两次真实请求，绝不合并计一次）。"""
    env.ctx.limiter = RateLimiter()
    run_stage(env, FakeHandle(ok_page()), monkeypatch)
    # rpm=10（1 req/6s）burst=1：首次即时，第二次欠账 → sleeper 收到一次 ~6s 等待。
    assert len(env.sleeps) == 1
    assert 5.5 < env.sleeps[0] <= 6.0
