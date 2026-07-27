"""ssrn 模式 B 同批约束的**生产端**接线（design/11 §4.4；T20 审计 R1 F-1 回归载体）。

design/11 §4.4 的同批语义由**一对**接缝构成：

- **消费端**（T6 落地）：`browserfetch.fetch_one(resolve_in_context=…)` —— 非 None 时在
  同一浏览器上下文内先解析出 volatile 计划，再判定/下载；
- **生产端**（本文件锁定）：ssrn adapter 提供 `resolve_in_browser_context(plan, handle)`，
  `pipeline/stages.py::_fetch_via_browser` 把它包成闭包传进 `fetch_one`。

生产端缺失时链路**结构性取不到全文**：`Delivery.cfm` 的一次性 token 从未被解析，浏览器拿
landing 引用当资产 URL 去 `download_via`——本文件的用例即以此为红判据（修前必失败）。

**真 sqlite + 真落盘 + 假 handle**，零真实浏览器、零网络（沿 `test_browser_fetch_pipeline.py`
的假 launcher 形态；本文件用**真 `SsrnAdapter`**，不用 fixture adapter——被审的正是 ssrn 侧）。
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
import yaml

import paper_crawler.pipeline.stages as stages_mod
from paper_crawler.adapter import load_adapters
from paper_crawler.browserfetch import BrowserFetchHandle, PageResponse
from paper_crawler.config import Config
from paper_crawler.errors import Challenged, CrawlerError, ErrorClass
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
    IssueRef,
    PaperStub,
    UrlStrategy,
    utcnow_iso,
)

VENUE = "ssrn"
ABSTRACT_ID = "4056799"
DOMAIN = "papers.ssrn.com"
LANDING = f"https://{DOMAIN}/sol3/papers.cfm?abstract_id={ABSTRACT_ID}"
# volatile（同批产出、一次性）——签名参数是 F-2 的脱敏判据载体。
VOLATILE_PATH = f"Delivery.cfm/SSRN_ID{ABSTRACT_ID}_code42.pdf?abstractid={ABSTRACT_ID}&mirid=1"
VOLATILE = f"https://{DOMAIN}/sol3/{VOLATILE_PATH}&signature=SEKRET-SIGNATURE-123"
PDF_BYTES = b"%PDF-1.4\n" + b"0" * 1024 + b"\n%%EOF\n"

LANDING_HTML = (
    "<html><body><h1>A Working Paper</h1>"
    f"<a class='btn' href='{VOLATILE_PATH}&signature=SEKRET-SIGNATURE-123'>Download This Paper</a>"
    "</body></html>"
).encode()


class FakeHandle:
    """假 `BrowserFetchHandle`：按 URL 返回预置响应，记录调用序列（同批判据载体）。"""

    def __init__(
        self,
        pages: dict[str, PageResponse] | None = None,
        *,
        payload: bytes = PDF_BYTES,
    ) -> None:
        self.pages = pages if pages is not None else default_pages()
        self.payload = payload
        self.calls: list[str] = []

    def goto(self, url: str) -> PageResponse:
        self.calls.append(f"goto:{url}")
        response = self.pages.get(url)
        if response is None:  # 未预置的 URL = 用例没想到的导航，响亮失败胜过静默 200
            raise AssertionError(f"unexpected navigation: {url}")
        return response

    def download_via(self, trigger: Callable[[], None], dest: Path) -> int:
        self.calls.append("download_via")
        trigger()
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(self.payload)
        return len(self.payload)

    def close(self) -> None:
        self.calls.append("close")

    @property
    def gotos(self) -> list[str]:
        return [c.removeprefix("goto:") for c in self.calls if c.startswith("goto:")]


def landing_page(body: bytes = LANDING_HTML, *, status: int = 200) -> PageResponse:
    return PageResponse(
        status=status, headers={"content-type": "text/html"}, final_url=LANDING, body=body
    )


def volatile_page() -> PageResponse:
    return PageResponse(
        status=200,
        headers={"content-type": "application/pdf"},
        final_url=VOLATILE,
        body=b"%PDF-1.4 stream",
    )


def default_pages() -> dict[str, PageResponse]:
    return {LANDING: landing_page(), VOLATILE: volatile_page()}


@dataclass
class Env:
    config: Config
    db: Database
    repo: Repo
    queue: TaskQueue
    ctx: StageContext
    asset_id: str
    task: sqlite3.Row

    def close(self) -> None:
        self.db.close()

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
    """最小 ssrn venue（形态取自 `venues/econ/ssrn.yaml`，只留本用例需要的字段）。"""
    venues_dir.mkdir(parents=True, exist_ok=True)
    (venues_dir / f"{VENUE}.yaml").write_text(
        yaml.safe_dump(
            {
                "id": VENUE,
                "kind": "preprint_channel",
                "names": {"full": "Social Science Research Network"},
                "field": ["econ"],
                "identifiers": {"crossref_prefix": "10.2139"},
                "metadata_source": "ssrn",
                "fulltext_source": "ssrn",
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
        browser_jitter_s=(0.0, 0.0),  # 假时钟纪律：抖动关掉才能精确断言等待序列
    )
    setup_logging(config.log_dir, console_level="CRITICAL")
    db = Database(config.db_path)
    db.migrate()
    repo = Repo(db)
    queue = TaskQueue(db)

    registry = VenueRegistry(load_adapters())  # 真 SsrnAdapter（entry point 注册）
    assert registry.load_dirs([venues_dir]) == []
    repo.upsert_venue(registry.get(VENUE))

    issue_id = repo.upsert_issue(IssueRef(venue_id=VENUE, year=2026), source="fixture")
    paper_id = repo.upsert_paper(
        VENUE,
        issue_id,
        PaperStub(
            title="Allocating Scarce Information",
            identifiers=(("doi", f"10.2139/ssrn.{ABSTRACT_ID}"), ("ssrn", ABSTRACT_ID)),
            year=2026,
        ),
    )
    asset_id = repo.plan_asset(
        paper_id,
        AssetPlan(kind=AssetKind.PDF, url=LANDING, url_strategy=UrlStrategy.RENDER_PAGE),
        "ssrn",
    )
    ctx = StageContext(
        config=config,
        db=db,
        repo=repo,
        registry=registry,
        queue=queue,
        limiter=RateLimiter(),
        sleeper=lambda _s: None,
        browser_fetch=True,
    )
    result = queue.enqueue("fetch", VENUE, {"asset": asset_id})
    task = queue.get(result.task_id)
    assert task is not None
    e = Env(config=config, db=db, repo=repo, queue=queue, ctx=ctx, asset_id=asset_id, task=task)
    yield e
    e.close()


def run_stage(env: Env, handle: FakeHandle, monkeypatch: pytest.MonkeyPatch) -> str:
    def fake_factory(*, identity_header: str | None = None) -> object:
        def _launch(user_data_dir: str, storage_state: bytes | None) -> BrowserFetchHandle:
            return handle  # type: ignore[return-value]

        return _launch

    monkeypatch.setattr(stages_mod, "playwright_launcher", fake_factory)
    report = RunReport(command="grab", venue_id=VENUE, started_at=utcnow_iso())
    return execute_stage(env.ctx, env.task, report)


# ---------------------------------------------------------------------------
# F-1：同批闭包的生产端接线（修前红）
# ---------------------------------------------------------------------------


def test_volatile_url_is_resolved_in_the_same_context(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    """landing → 同 context 解析出 `Delivery.cfm` → **用 volatile URL** 判定并下载。

    修前：生产端未接线 ⇒ `fetch_one` 收到 `resolve_in_context=None` ⇒ 全程只碰 landing，
    volatile URL 从未被请求（`goto` 序列里没有它）——本断言即 F-1 的红判据。
    """
    handle = FakeHandle()
    assert run_stage(env, handle, monkeypatch) == "done"

    assert handle.gotos[0] == LANDING  # 第一跳恒是 landing（同批解析在同一 handle 上）
    assert VOLATILE in handle.gotos  # 判定/下载走的是同批解析出的 volatile URL
    assert handle.gotos.count(LANDING) == 1  # landing 只解析一次（不重复导航）
    assert "download_via" in handle.calls


def test_asset_url_keeps_landing_reference_not_volatile(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§4.4 持久化纪律：volatile URL **不入 `asset.url`**（跨批复用即设计违规）。"""
    assert run_stage(env, FakeHandle(), monkeypatch) == "done"
    assert str(env.asset_row()["url"]) == LANDING


def test_challenge_on_landing_stops_before_resolving(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    """同批解析导航同样过 `ChallengeDetector`：landing 命中风控 → 立即停手（零后续导航）。

    生产端若不判定，CF 挑战页会退化成"解析不出下载链接"，把 challenge 静默降级——正是
    项目刚以 S-c 收口的那类缺口，不得在本接缝重演。
    """
    challenge = PageResponse(
        status=403, headers={"cf-mitigated": "challenge"}, final_url=LANDING, body=b"403"
    )
    handle = FakeHandle({LANDING: challenge})
    with pytest.raises(Challenged):
        run_stage(env, handle, monkeypatch)
    assert handle.gotos == [LANDING]
    assert "download_via" not in handle.calls


def test_landing_without_download_link_is_no_entitlement(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    """landing 无 `Delivery.cfm` 链接（付费/无免费副本）→ `no_entitlement` 接既有 OA 链。

    body 刻意**不带** access-wall 特征串（"get access"/"purchase"）——否则判定器自己就返
    NO_ENTITLEMENT，测不到"解析不出下载链接"这条独立分支。
    """
    handle = FakeHandle({LANDING: landing_page(b"<html><h1>WP</h1><p>abstract only</p></html>")})
    with pytest.raises(CrawlerError) as excinfo:
        run_stage(env, handle, monkeypatch)
    assert excinfo.value.error_class is ErrorClass.NO_ENTITLEMENT
    assert "download_via" not in handle.calls
