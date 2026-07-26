"""aaai_ojs discover→enumerate→resolve→fetch→upsert 全链路集成（Phase 2，design/adapters/
aaai-ojs.md §7 T4）。

用 `httpx.MockTransport` 喂十一件套合成 fixture 走全链路，断言：全库收割按 DOI 卷号
partition 落盘正确（当前届 v40 / 历史届 v33 各自只落自己的记录）；**冷回填整条时间轴的
请求账**——全部历史届共享单趟全库收割、当前届单独走回看窗（审计 S1-P1 修复，请求数与
已注册历史届数解耦）；当前届固定回看窗重复 enumerate 无重复无遗漏（去重由
`identifier('doi')` 主键天然保证）；墓碑跳过计数经 obslog 暴露；view→download resolve +
PDF fetch 端到端；错误路由（404/503→各自 ErrorClass）。零真实网络。
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from contextlib import closing
from pathlib import Path

import httpx
import pytest

from helpers import FakeFetchIO, make_aaai_venue
from helpers.aaai_fixtures import build_oai_page, fixture_bytes
from paper_crawler.adapters.aaai_ojs.adapter import AaaiOjsAdapter
from paper_crawler.errors import CrawlerError, ErrorClass
from paper_crawler.http import HttpClient
from paper_crawler.storage.db import Database
from paper_crawler.storage.repo import Repo
from paper_crawler.types import AssetKind, IssueRef

_UA = "PaperCrawler/test (personal research; mailto:test@example.com)"
_VENUE_ID = "aaai"


def _issue(*, volume: str, year: int) -> IssueRef:
    return IssueRef(
        venue_id=_VENUE_ID, volume=volume, number=None, year=year, label=f"AAAI-{year % 100:02d}"
    )


def _adapter(handler: object) -> AaaiOjsAdapter:
    client = HttpClient(user_agent=_UA, transport=httpx.MockTransport(handler))  # type: ignore[arg-type]
    return AaaiOjsAdapter(http=client)


def _two_page_handler(request: httpx.Request) -> httpx.Response:
    if "resumptionToken" in request.url.params:
        return httpx.Response(200, content=fixture_bytes("02_oai_listrecords_page2.xml"))
    return httpx.Response(200, content=fixture_bytes("01_oai_listrecords_page1.xml"))


@pytest.fixture
def repo(tmp_path: Path) -> Iterator[Repo]:
    db = Database(tmp_path / "aaai.sqlite")
    db.migrate()
    r = Repo(db)
    r.upsert_venue(make_aaai_venue())  # paper/issue.venue_id 外键前置
    yield r
    db.close()


def _harvest(repo: Repo, adapter: AaaiOjsAdapter, issue: IssueRef, issue_id: str) -> int:
    venue = make_aaai_venue()
    count = 0
    for stub in adapter.enumerate_issue(venue, issue):
        repo.upsert_paper(_VENUE_ID, issue_id, stub)
        count += 1
    return count


def _identifiers(repo: Repo) -> set[tuple[str, str]]:
    rows = repo.db.query("SELECT scheme, value FROM identifier")
    return {(str(r["scheme"]), str(r["value"])) for r in rows}


# --- 全库收割按 DOI 卷号 partition 落盘 ----------------------------------------------------------


def test_current_edition_harvest_partitions_only_v40_papers(repo: Repo) -> None:
    issue = _issue(volume="40", year=2026)
    issue_id = repo.upsert_issue(issue, source="aaai_ojs")
    harvested = _harvest(repo, _adapter(_two_page_handler), issue, issue_id)

    assert harvested == 4  # A/C/E 页1 + F 页2（v40），过滤掉 v33 与墓碑
    assert _identifiers(repo) == {
        ("doi", "10.1609/aaai.v40i1.36958"),
        ("doi", "10.1609/aaai.v40i2.37001"),
        ("doi", "10.1609/aaai.v40i1.36959"),
        ("doi", "10.1609/aaai.v40i3.37050"),
    }

    papers = {str(p["title"]): p for p in repo.list_papers(_VENUE_ID)}
    lead = papers["Resource Efficient Sleep Staging via Multi-Level Masking and Prompt Learning"]
    assert lead["year"] == 2026
    meta = json.loads(str(lead["meta_json"]))
    assert meta["pdf_url"] == "https://ojs.aaai.org/index.php/AAAI/article/view/36958/40920"
    assert meta["ojs_article_id"] == "36958"
    assert "Vol. 40 No. 1" in meta["ojs_source"]


def test_historical_edition_harvest_partitions_only_v33_papers(repo: Repo) -> None:
    issue = _issue(volume="33", year=2019)
    issue_id = repo.upsert_issue(issue, source="aaai_ojs")
    harvested = _harvest(repo, _adapter(_two_page_handler), issue, issue_id)

    assert harvested == 2  # D 页1 + G 页2（v33）
    assert _identifiers(repo) == {
        ("doi", "10.1609/aaai.v33i01.3301695"),
        ("doi", "10.1609/aaai.v33i01.3301696"),
    }


def test_paper_issue_link_created_for_edition(repo: Repo) -> None:
    issue = _issue(volume="40", year=2026)
    issue_id = repo.upsert_issue(issue, source="aaai_ojs")
    _harvest(repo, _adapter(_two_page_handler), issue, issue_id)
    linked = repo.list_papers(_VENUE_ID, issue_id=issue_id)
    assert len(linked) == 4


# --- 冷回填全库：单趟收割喂满所有历史届（审计 S1-P1）-------------------------------------------

# 3 历史届（v24/v33/v34）+ 1 当前届（v40）；全库收割 3 页，回看窗单页。
_COLD_VOLUME_MAP = {2010: 24, 2019: 33, 2020: 34, 2026: 40}
_COLD_PAGES: tuple[tuple[tuple[str, str], ...], ...] = (
    (("24", "2401"), ("40", "4001"), ("33", "3301")),
    (("34", "3401"), ("24", "2402"), ("40", "4002")),
    (("33", "3302"), ("34", "3402")),
)
_COLD_WINDOW_PAGE: tuple[tuple[str, str], ...] = (("40", "4003"),)


def _cold_handler(counter: list[httpx.URL]) -> Callable[[httpx.Request], httpx.Response]:
    """全库 3 页（无 `from`）/ 回看窗 1 页（带 `from`，只回当前届新增），逐请求计数。"""

    def handler(request: httpx.Request) -> httpx.Response:
        counter.append(request.url)
        if "from" in request.url.params:
            return httpx.Response(200, content=build_oai_page(_COLD_WINDOW_PAGE))
        token = request.url.params.get("resumptionToken")
        index = int(token.rsplit("-", 1)[-1]) if token else 0
        is_last = index == len(_COLD_PAGES) - 1
        return httpx.Response(
            200,
            content=build_oai_page(
                _COLD_PAGES[index], resumption_token=None if is_last else f"COLD-{index + 1}"
            ),
        )

    return handler


def test_cold_backfill_whole_timeline_costs_one_full_pass(tmp_path: Path) -> None:
    """discover→enumerate 走完整条时间轴：全部历史届共享单趟全库收割，当前届单独走回看窗。

    修复前每个历史届各自重扫全库（审计 S1-P1，请求成本随已注册届数线性放大）；修复后
    请求数 = 全库页数 + 当前届窗口页数，与已注册历史届数**解耦**。
    """
    with closing(Database(tmp_path / "aaai-cold.sqlite")) as db:
        db.migrate()
        repo = Repo(db)
        venue = make_aaai_venue(volume_map=dict(_COLD_VOLUME_MAP))
        repo.upsert_venue(venue)

        seen: list[httpx.URL] = []
        adapter = _adapter(_cold_handler(seen))

        issues = list(adapter.discover_timeline(venue))
        assert [i.volume for i in issues] == ["24", "33", "34", "40"]  # 升序：历史届先于当前届

        per_issue: dict[str, set[str]] = {}
        for ref in issues:
            issue_id = repo.upsert_issue(ref, source="aaai_ojs")
            for stub in adapter.enumerate_issue(venue, ref):
                repo.upsert_paper(_VENUE_ID, issue_id, stub)
            rows = repo.list_papers(_VENUE_ID, issue_id=issue_id)
            per_issue[str(ref.volume)] = {str(r["title"]) for r in rows}

        # 请求账：3 页全库（v24 触发，v33/v34 零请求命中缓存）+ 1 页当前届回看窗 = 4。
        assert len(seen) == len(_COLD_PAGES) + 1 == 4
        assert sum(1 for u in seen if "from" in u.params) == 1  # 只有当前届带日期窗
        # 修复前同一条时间轴的基线：3 历史届 × 3 页 + 1 = 10（降幅 2.5×，随届数增长而放大）。
        assert len(seen) < 3 * len(_COLD_PAGES) + 1

        # 分区落盘正确：每届只装自己卷号的论文（缓存命中路径与真收割路径同一判据）。
        assert {v: len(t) for v, t in per_issue.items()} == {"24": 2, "33": 2, "34": 2, "40": 1}
        assert all(
            f"v{volume} " in title for volume, titles in per_issue.items() for title in titles
        )
        assert len(repo.list_papers(_VENUE_ID)) == 7


# --- 当前届固定回看窗重复 enumerate：无重复无遗漏（DOI 主键去重）--------------------------------


def test_current_edition_overlapping_reharvest_does_not_duplicate(repo: Repo) -> None:
    issue = _issue(volume="40", year=2026)
    issue_id = repo.upsert_issue(issue, source="aaai_ojs")
    first = _harvest(repo, _adapter(_two_page_handler), issue, issue_id)
    second = _harvest(repo, _adapter(_two_page_handler), issue, issue_id)
    # 重叠回看窗两趟各产 4；DOI 主键去重 → DB 内恒 4 篇/4 identifier（无重复行、无遗漏）。
    assert first == second == 4
    assert len(repo.list_papers(_VENUE_ID)) == 4
    assert len(_identifiers(repo)) == 4


# --- 墓碑跳过计数经 obslog 暴露 -----------------------------------------------------------------


def test_tombstone_skip_count_surfaced_via_obslog(
    repo: Repo, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[dict[str, object]] = []
    monkeypatch.setattr(
        "paper_crawler.adapters.aaai_ojs.adapter.log_event",
        lambda level, msg, **kw: events.append({"level": level, "msg": msg, **kw}),
    )
    issue = _issue(volume="40", year=2026)
    issue_id = repo.upsert_issue(issue, source="aaai_ojs")
    _harvest(repo, _adapter(_two_page_handler), issue, issue_id)

    tombstone = [e for e in events if e["msg"] == "oai tombstones skipped"]
    assert len(tombstone) == 1
    assert tombstone[0]["skipped_tombstones"] == 1
    assert tombstone[0]["bucket"] == "AAAI-26"


# --- 全链路：discover→enumerate→resolve→fetch（view→download 端到端）-----------------------------


def test_full_chain_discover_enumerate_resolve_fetch(repo: Repo) -> None:
    pdf_bytes = b"%PDF-1.7\nsynthetic aaai pdf\n%%EOF\n"

    def handler(request: httpx.Request) -> httpx.Response:
        if "/article/download/" in request.url.path:
            return httpx.Response(200, content=pdf_bytes)
        return _two_page_handler(request)

    adapter = _adapter(handler)
    venue = make_aaai_venue()

    issues = list(adapter.discover_timeline(venue))
    assert {i.volume for i in issues} == {"33", "40"}
    target = next(i for i in issues if i.volume == "40")

    papers = list(adapter.enumerate_issue(venue, target))
    assert len(papers) == 4

    downloaded = 0
    for paper in papers:
        plans = adapter.resolve_assets(venue, paper)
        assert len(plans) == 1
        plan = plans[0]
        assert plan.kind is AssetKind.PDF
        # resolve 零网络：view→download 预换，域始终 ojs.aaai.org 本域。
        assert "/article/download/" in plan.url
        assert httpx.URL(plan.url).host == "ojs.aaai.org"

        io = FakeFetchIO()
        result = adapter.fetch_asset(plan, io)
        assert result.ok is True
        assert io.data == pdf_bytes
        downloaded += 1
    assert downloaded == 4


def test_full_chain_login_gated_galley_is_no_entitlement(repo: Repo) -> None:
    # 罕见路径：陈旧/未发布 galley 的 download → 302→/login 落地 → no_entitlement（★D）。
    def handler(request: httpx.Request) -> httpx.Response:
        if "/login" in request.url.path:
            return httpx.Response(200, content=fixture_bytes("08_issue_login_redirect.html"))
        if "/article/download/" in request.url.path:
            return httpx.Response(
                302, headers={"location": "https://ojs.aaai.org/index.php/AAAI/login?source=%2Fx"}
            )
        return _two_page_handler(request)

    adapter = _adapter(handler)
    venue = make_aaai_venue()
    paper = next(iter(adapter.enumerate_issue(venue, _issue(volume="40", year=2026))))
    plan = adapter.resolve_assets(venue, paper)[0]
    with pytest.raises(CrawlerError) as exc:
        adapter.fetch_asset(plan, FakeFetchIO())
    assert exc.value.error_class is ErrorClass.NO_ENTITLEMENT


# --- 错误路由（adapter 边界的 ErrorClass 契约）------------------------------------------------


def test_error_routing_oai_page_503_is_transient(repo: Repo) -> None:
    handler = lambda request: httpx.Response(503, content=b"down")  # noqa: E731
    issue = _issue(volume="40", year=2026)
    issue_id = repo.upsert_issue(issue, source="aaai_ojs")
    with pytest.raises(CrawlerError) as exc:
        _harvest(repo, _adapter(handler), issue, issue_id)
    assert exc.value.error_class is ErrorClass.TRANSIENT


def test_error_routing_article_download_404_is_gone(repo: Repo) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "/article/download/" in request.url.path:
            return httpx.Response(404, content=fixture_bytes("07_article_404.html"))
        return _two_page_handler(request)

    adapter = _adapter(handler)
    venue = make_aaai_venue()
    paper = next(iter(adapter.enumerate_issue(venue, _issue(volume="40", year=2026))))
    plan = adapter.resolve_assets(venue, paper)[0]
    with pytest.raises(CrawlerError) as exc:
        adapter.fetch_asset(plan, FakeFetchIO())
    assert exc.value.error_class is ErrorClass.GONE
