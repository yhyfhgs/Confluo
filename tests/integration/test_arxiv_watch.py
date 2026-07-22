"""arxiv watch 编排集成（Phase 2 T6；arxiv.md §3 watch 裁决 + §6 七收割日回放）。

经 `PipelineRunner.watch` 走 discover(force)→enumerate(force) 全链路，`httpx.MockTransport`
按日序喂合成 OAI 页（`helpers.arxiv_fixtures.build_oai_listrecords`）。断言：当月桶强制
re-enumerate、重叠窗口/同日二跑零重复入库、跨月边界含上一月桶、七收割日累计无重复无遗漏
（含 announce 延迟：某记录第 N 日缺席、第 N+1 日出现）。零真实网络（MockTransport）。

M4 交接（T5 review）：确认 watch 高频 enumerate 路径的限速 domain keying——见
test_watch_rate_keying_uses_shared_export_domain。
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import httpx
import pytest
import yaml

from helpers.arxiv_fixtures import OaiRecord, build_oai_listrecords
from paper_crawler.adapter import bind_http_client, load_adapters
from paper_crawler.config import Config
from paper_crawler.http import HttpClient
from paper_crawler.obslog import setup_logging
from paper_crawler.pipeline import PipelineRunner, RunReport, StageContext
from paper_crawler.ratelimit import RateLimiter
from paper_crawler.registry import VenueRegistry
from paper_crawler.storage.db import Database
from paper_crawler.storage.repo import Repo
from paper_crawler.tasks import TaskQueue

_VENUE_ID = "arxiv_cs_lg"
_UA = "PaperCrawler/test (personal research; mailto:test@example.com)"
Handler = Callable[[httpx.Request], httpx.Response]


@dataclass
class WatchEnv:
    """一套隔离的 watch 运行环境：mock-注入的 arxiv adapter + 已加载 preprint venue。"""

    runner: PipelineRunner
    repo: Repo
    queue: TaskQueue
    limiter: RateLimiter
    registry: VenueRegistry
    sleeps: list[float]
    db: Database

    def watch(self, today: date) -> RunReport:
        return self.runner.watch(_VENUE_ID, today=today)

    def papers(self) -> int:
        return self.repo.counts(_VENUE_ID)["papers"]

    def identifiers(self) -> list[str]:
        rows = self.repo.db.query("SELECT value FROM identifier WHERE scheme = 'arxiv'")
        return [str(r["value"]) for r in rows]


def _write_venue(venues_dir: Path, *, inception: str = "2024-01") -> None:
    doc: dict[str, object] = {
        "id": _VENUE_ID,
        "kind": "preprint_channel",
        "names": {"full": "arXiv cs.LG", "aliases": ["arxiv-cs-lg"]},
        "field": ["cs_ai"],
        "metadata_source": "arxiv",
        "fulltext_source": "arxiv",
        "quirks": {"inception": inception, "arxiv_set": "cs", "arxiv_category": "cs.LG"},
        "status": "active",
    }
    (venues_dir / "arxiv-cs-lg.yaml").write_text(
        yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8"
    )


def _make_env(tmp_path: Path, handler: Handler, *, inception: str = "2024-01") -> WatchEnv:
    home = tmp_path / "home"
    venues_dir = tmp_path / "venues"
    venues_dir.mkdir(parents=True, exist_ok=True)
    home.mkdir(parents=True, exist_ok=True)
    _write_venue(venues_dir, inception=inception)
    config = Config(
        home=home,
        data_dir=home / "data",
        db_path=home / "catalog.sqlite",
        log_dir=home / "logs",
        reports_dir=home / "reports",
        venues_dirs=(venues_dir,),
    )
    setup_logging(config.log_dir, console_level="CRITICAL")
    db = Database(config.db_path)
    db.migrate()
    repo = Repo(db)

    adapters = load_adapters()
    client = HttpClient(user_agent=_UA, transport=httpx.MockTransport(handler))
    # 真实 http adapter 均为 HttpClientConsumer（watch 只跑 preprint venue，其余被注入但
    # 不参与——conference/journal 不入 watch）。
    # ★共享花名册（5 线并行 union 点）：crossref（T3）已加入注入集；T4/T5/T6 亦将扩集——
    # controller 合并取并集（另见 tests/unit/test_adapter_loading.py 同名断言）。
    # unpaywall（T5）亦为 HttpClientConsumer（RESOLVE-only，注入不参与 watch）。
    assert set(bind_http_client(adapters, client)) == {
        "arxiv",
        "openreview",
        "pmlr",
        "acl_anthology",
        "cvf",
        "aaai_ojs",
        "neurips_proceedings",
        "crossref",
        "unpaywall",
        "dblp",
    }
    registry = VenueRegistry(adapters)
    assert registry.load_dirs([venues_dir]) == []

    queue = TaskQueue(db)
    limiter = RateLimiter(scale=config.rate_scale)
    sleeps: list[float] = []
    ctx = StageContext(
        config=config,
        db=db,
        repo=repo,
        registry=registry,
        queue=queue,
        limiter=limiter,
        sleeper=sleeps.append,  # 假 sleeper：限速 wait 只记录不真睡
    )
    return WatchEnv(
        runner=PipelineRunner(ctx),
        repo=repo,
        queue=queue,
        limiter=limiter,
        registry=registry,
        sleeps=sleeps,
        db=db,
    )


EnvFactory = Callable[..., WatchEnv]


@pytest.fixture
def make_watch_env(tmp_path: Path) -> Iterator[EnvFactory]:
    """factory：每次调用建一套独立 WatchEnv（唯一子目录），teardown 统一关 DB 连接。"""
    envs: list[WatchEnv] = []
    counter = {"n": 0}

    def factory(handler: Handler, *, inception: str = "2024-01") -> WatchEnv:
        counter["n"] += 1
        env = _make_env(tmp_path / f"env{counter['n']}", handler, inception=inception)
        envs.append(env)
        return env

    yield factory
    for env in envs:
        env.db.close()


def _single_page(records: list[OaiRecord]) -> Handler:
    """恒返回同一页（单页，无 resumptionToken）——用于强制刷新/去重的定值场景。"""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=build_oai_listrecords(records))

    return handler


def _sequence_handler(pages: list[bytes]) -> Handler:
    """按 OAI 请求序返回 pages[i]（i=第 i 个 OAI 请求，0-based）——七日回放。"""
    state = {"i": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        i = state["i"]
        state["i"] += 1
        assert i < len(pages), f"unexpected OAI request #{i} (only {len(pages)} days scripted)"
        return httpx.Response(200, content=pages[i])

    return handler


# --- 当月桶强制刷新 + 同日二跑幂等零重复 -----------------------------------------------------


def test_watch_enumerates_current_month_and_persists(make_watch_env: EnvFactory) -> None:
    env = make_watch_env(
        _single_page([OaiRecord("2406.00001", "One"), OaiRecord("2406.00002", "Two")])
    )
    report = env.watch(date(2024, 6, 15))

    assert report.failed == 0 and report.blocked == 0
    assert env.papers() == 2
    assert sorted(env.identifiers()) == ["2406.00001", "2406.00002"]
    assert any("watch[arxiv_cs_lg]: +2 new paper(s)" in n for n in report.notes)


def test_watch_same_day_rerun_force_refreshes_and_stays_idempotent(
    make_watch_env: EnvFactory,
) -> None:
    """同日二跑：force 绕过 7d 新鲜度仍 re-enumerate，identifier 主键去重 → 零重复。"""
    handler = _single_page([OaiRecord("2406.00001", "One"), OaiRecord("2406.00002", "Two")])
    env = make_watch_env(handler)

    first = env.watch(date(2024, 6, 15))
    second = env.watch(date(2024, 6, 15))

    # 两跑都真正执行 enumerate（force → 不 fresh_skip）：第二跑 skipped 计数为 0。
    assert first.skipped == 0 and second.skipped == 0
    # 第二跑净新增 0（幂等），总量与 identifier 均不翻倍。
    assert env.papers() == 2
    assert len(env.identifiers()) == 2 == len(set(env.identifiers()))
    assert any("+0 new paper(s)" in n for n in second.notes)
    assert second.failed == 0


def test_watch_no_force_would_skip_but_watch_forces(make_watch_env: EnvFactory) -> None:
    """对照：证明 watch 确实强制刷新——二跑的 enumerate 未落 fresh_skip（skipped==0），
    区别于 `run_single_stage`（无 force）在 7d 窗口内会 fresh_skip。"""
    env = make_watch_env(_single_page([OaiRecord("2406.00001", "One")]))
    env.watch(date(2024, 6, 15))
    # 直接 run_single_stage enumerate 同一桶（无 force）→ 7d 新鲜度内 fresh_skip。
    issue = env.repo.list_issues(_VENUE_ID, number="06", year=2024)[0]
    skip_report = env.runner.run_single_stage("enumerate", _VENUE_ID, {"issue": str(issue["id"])})
    assert skip_report.skipped == 1  # 无 force → fresh_skip（与 watch 的 force 形成对照）


# --- 跨月边界（月初含上一月桶）--------------------------------------------------------------


def test_watch_month_boundary_includes_previous_month(make_watch_env: EnvFactory) -> None:
    """6/2（≤3 号）→ enumerate 2024-05 与 2024-06 两桶（各 1 OAI 请求）。"""
    env = make_watch_env(
        _sequence_handler(
            [
                build_oai_listrecords([OaiRecord("2405.00001", "May", created="2024-05-20")]),
                build_oai_listrecords([OaiRecord("2406.00001", "June", created="2024-06-01")]),
            ]
        ),
    )
    report = env.watch(date(2024, 6, 2))

    assert report.failed == 0
    assert sorted(env.identifiers()) == ["2405.00001", "2406.00001"]  # 两月桶都收
    assert any("over 2 bucket(s)" in n for n in report.notes)


def test_watch_mid_month_targets_single_bucket(make_watch_env: EnvFactory) -> None:
    """6/15（>3 号）→ 仅当月桶：单次 OAI 请求（上一月桶不入目标）。"""
    env = make_watch_env(_single_page([OaiRecord("2406.00001", "June")]))
    report = env.watch(date(2024, 6, 15))
    assert any("over 1 bucket(s)" in n for n in report.notes)


# --- 七收割日回放（AC-2.3 离线证据层，D-018）-------------------------------------------------


def test_seven_harvest_day_replay_dedups_and_handles_announce_delay(
    make_watch_env: EnvFactory,
) -> None:
    """Closes: AC-2.3 (offline layer, D-018).

    连续 7 次 watch，MockTransport 按日序喂逐日递增 + 重叠 + announce-延迟的 OAI 页：
    - 每日窗口重叠（A/B 反复返回）→ identifier 主键去重，零重复入库；
    - 第 4 日同页含 D 两次（intra-page 重复）→ 仍算 1 篇；
    - announce 延迟：E 第 5 日"应现却缺席"、第 6 日才出现 → 不漏、只计一次；
    - 持久墓碑 G（deleted）→ 永不入库。
    断言 7 日累计去重期望值、identifier 无重复、每日报告净新增序列、全程无 FAILED。
    """
    A = OaiRecord("2406.00001", "Paper A", created="2024-06-05")
    B = OaiRecord("2406.00002", "Paper B", created="2024-06-05")
    C = OaiRecord("2406.00003", "Paper C", created="2024-06-06")
    D = OaiRecord("2406.00004", "Paper D", created="2024-06-08")
    E = OaiRecord("2406.00005", "Paper E", created="2024-06-08")  # 第 5 日 announce 延迟
    F = OaiRecord("2406.00006", "Paper F", created="2024-06-11")
    G_TOMB = OaiRecord("2406.00099", "Withdrawn", deleted=True)  # 持久墓碑

    days: list[list[OaiRecord]] = [
        [A, B],  # day1: +A,+B
        [A, B, C],  # day2: +C（A/B 重叠）
        [A, B, C, G_TOMB],  # day3: +0（全重叠 + 墓碑）
        [A, B, C, D, D, G_TOMB],  # day4: +D（intra-page 重复 D 去重）
        [A, B, C, D, G_TOMB],  # day5: +0（E announce 延迟缺席）
        [A, B, C, D, E, G_TOMB],  # day6: +E（延迟记录到达）
        [A, B, C, D, E, F, G_TOMB],  # day7: +F
    ]
    pages = [build_oai_listrecords(recs) for recs in days]
    env = make_watch_env(_sequence_handler(pages))

    daily_new: list[int] = []
    for offset in range(7):
        report = env.watch(date(2024, 6, 10 + offset))  # 全 >3 号 → 恒当月桶 2024-06
        assert report.failed == 0, f"day{offset + 1} had FAILED tasks"
        # 从报告 notes 抽本日净新增计数（报告计数序列）。
        note = next(n for n in report.notes if n.startswith("watch[arxiv_cs_lg]:"))
        daily_new.append(int(note.split("+", 1)[1].split(" ", 1)[0]))

    # 每日净新增序列（报告计数）：[2,1,0,1,0,1,1]，和 = 6 篇去重期望值。
    assert daily_new == [2, 1, 0, 1, 0, 1, 1]
    assert env.papers() == 6
    ids = env.identifiers()
    assert len(ids) == 6 == len(set(ids))  # identifier 无重复
    assert set(ids) == {f"2406.0000{i}" for i in range(1, 7)}
    assert "2406.00099" not in ids  # 墓碑从不入库
    # 全程无 FAILED 任务（任务表口径，与逐日报告口径互证）。
    assert env.queue.by_state("FAILED") == []


# --- M4 交接：限速 domain keying 确认 --------------------------------------------------------


def test_watch_rate_keying_uses_shared_export_domain(make_watch_env: EnvFactory) -> None:
    """T5 review M4：watch 高频 enumerate 路径的限速账本键。

    arxiv 三端点（export/oaipmh/arxiv.org）按 ToU「并发 1」共用一份 1req/3s 预算——
    metadata（OAI enumerate）与 fulltext（PDF fetch）两侧 domains[0] 同为
    export.arxiv.org，故 enumerate 的 OAI 请求正确记在**共享** export.arxiv.org 桶
    （而非独立 oaipmh.arxiv.org 桶——独立记账会给两端各自 1req/3s、聚合 2req/3s 违反
    ToU）。M4 假设「应记 oaipmh 桶」按 ToU 反而错误，故不修正——见报告 M4 说明。
    """
    env = make_watch_env(_single_page([OaiRecord("2406.00001", "One")]))
    route = env.registry.route(_VENUE_ID)
    # 两侧限速主域一致 = 三端点共享单一预算键。
    assert route.metadata_adapter.domains[0] == "export.arxiv.org"
    assert route.fulltext_adapter.domains[0] == "export.arxiv.org"

    env.watch(date(2024, 6, 15))
    # watch 后 export.arxiv.org 桶已注册且被消费（enumerate 记账其上）。
    assert env.limiter.effective_rpm("export.arxiv.org") == 20.0
    # C4 红线修复：oaipmh/arxiv.org 经 route_for 的 alias 归并到 export **同一桶**——
    # HttpClient 逐请求在实际请求 host（oaipmh）acquire 时落到 export 预算，故二者
    # effective_rpm 一致（共享 20rpm=1req/3s，而非各自独立放行导致聚合 >1req/3s）。
    assert env.limiter.effective_rpm("oaipmh.arxiv.org") == 20.0
    assert env.limiter.effective_rpm("arxiv.org") == 20.0
    # 收紧主域即收紧全簇（同一 _Bucket 对象）——证明确为共享而非各自独立。
    env.limiter.override("export.arxiv.org", 10)
    assert env.limiter.effective_rpm("oaipmh.arxiv.org") == 10.0
