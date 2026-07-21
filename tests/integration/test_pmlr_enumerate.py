"""pmlr discover→enumerate→resolve→fetch→upsert 全链路集成（Phase 2，design/adapters/
pmlr.md §6.3 T4 集成）。

用 `httpx.MockTransport` 喂合成 fixture 走全链路，断言：字段落库（identifier/meta/
year）、双域 resolve+fetch 端到端（AssetPlan.url 域集合覆盖两种托管形态）、重叠
窗口去重（identifier 锚点）、0-div 两个消歧分支（合法空 vs parse）经完整
enumerate→upsert 路径的行为、错误路由（404/503 → 各自 ErrorClass）。零真实网络。
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

from helpers import FakeFetchIO, make_pmlr_venue
from helpers.pmlr_fixtures import fixture_bytes
from paper_crawler.adapters.pmlr.adapter import PmlrAdapter
from paper_crawler.errors import CrawlerError, ErrorClass
from paper_crawler.http import HttpClient
from paper_crawler.storage.db import Database
from paper_crawler.storage.repo import Repo
from paper_crawler.types import AssetKind, IssueRef

_UA = "PaperCrawler/test (personal research; mailto:test@example.com)"
_VENUE_ID = "icml"


def _issue_v235() -> IssueRef:
    return IssueRef(venue_id=_VENUE_ID, volume="235", number=None, year=2024, label="v235")


def _issue_v202() -> IssueRef:
    return IssueRef(venue_id=_VENUE_ID, volume="202", number=None, year=2023, label="v202")


def _adapter(handler: object) -> PmlrAdapter:
    client = HttpClient(user_agent=_UA, transport=httpx.MockTransport(handler))  # type: ignore[arg-type]
    return PmlrAdapter(http=client)


def _normal_volume_handler(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, content=fixture_bytes("01_volume_index_normal.html"))


@pytest.fixture
def repo(tmp_path: Path) -> Iterator[Repo]:
    db = Database(tmp_path / "pmlr.sqlite")
    db.migrate()
    r = Repo(db)
    r.upsert_venue(make_pmlr_venue())  # paper/issue.venue_id 外键前置
    yield r
    db.close()


def _harvest(repo: Repo, adapter: PmlrAdapter, issue: IssueRef, issue_id: str) -> int:
    venue = make_pmlr_venue()
    count = 0
    for stub in adapter.enumerate_issue(venue, issue):
        repo.upsert_paper(_VENUE_ID, issue_id, stub)
        count += 1
    return count


def _identifiers(repo: Repo) -> set[tuple[str, str]]:
    rows = repo.db.query("SELECT scheme, value FROM identifier")
    return {(str(r["scheme"]), str(r["value"])) for r in rows}


# --- enumerate→upsert 字段落库 -------------------------------------------------------------------


def test_enumerate_upserts_all_three_papers_with_fields(repo: Repo) -> None:
    issue = _issue_v235()
    issue_id = repo.upsert_issue(issue, source="pmlr")
    harvested = _harvest(repo, _adapter(_normal_volume_handler), issue, issue_id)

    assert harvested == 3
    assert _identifiers(repo) == {
        ("pmlr", "pmlr-v235-abad-rocamora24a"),
        ("pmlr", "pmlr-v235-example-selfhosted24b"),
        ("pmlr", "pmlr-v235-another-example24c"),
    }

    papers = {str(p["title"]): p for p in repo.list_papers(_VENUE_ID)}
    lead = papers["Revisiting Character-level Adversarial Attacks for Language Models"]
    assert lead["year"] == 2024
    meta = json.loads(str(lead["meta_json"]))
    assert meta["openreview"] == "AZWqXfM6z9"
    assert meta["pdf_url"].startswith("https://raw.githubusercontent.com/")
    assert meta["landing_url"] == "https://proceedings.mlr.press/v235/abad-rocamora24a.html"

    # 无 OpenReview 链接的那篇：meta 不含 'openreview' 键（design §3.2 可选字段）。
    no_or = papers["A Synthetic Self-Hosted Example Paper for PMLR Fixture Coverage"]
    assert "openreview" not in json.loads(str(no_or["meta_json"]))


def test_paper_issue_link_created_for_volume(repo: Repo) -> None:
    issue = _issue_v235()
    issue_id = repo.upsert_issue(issue, source="pmlr")
    _harvest(repo, _adapter(_normal_volume_handler), issue, issue_id)
    linked = repo.list_papers(_VENUE_ID, issue_id=issue_id)
    assert len(linked) == 3


# --- 重叠重收去重（identifier 锚点）---------------------------------------------------------------


def test_overlapping_reharvest_does_not_duplicate(repo: Repo) -> None:
    issue = _issue_v235()
    issue_id = repo.upsert_issue(issue, source="pmlr")
    first = _harvest(repo, _adapter(_normal_volume_handler), issue, issue_id)
    second = _harvest(repo, _adapter(_normal_volume_handler), issue, issue_id)
    assert first == second == 3
    assert len(repo.list_papers(_VENUE_ID)) == 3
    assert len(_identifiers(repo)) == 3


# --- 全链路：discover→enumerate→resolve→fetch，双域端到端 -----------------------------------------


def test_full_chain_discover_enumerate_resolve_fetch_dual_hosted(repo: Repo) -> None:
    pdf_bytes = b"%PDF-1.4\nsynthetic contract pdf\n%%EOF\n"

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url).endswith(".pdf"):
            return httpx.Response(200, content=pdf_bytes)
        return httpx.Response(200, content=fixture_bytes("01_volume_index_normal.html"))

    adapter = _adapter(handler)
    venue = make_pmlr_venue()

    issues = list(adapter.discover_timeline(venue))
    assert {i.volume for i in issues} == {"202", "235"}
    target = next(i for i in issues if i.volume == "235")

    papers = list(adapter.enumerate_issue(venue, target))
    assert len(papers) == 3

    hosts_seen: set[str] = set()
    for paper in papers:
        plans = adapter.resolve_assets(venue, paper)
        assert len(plans) == 1
        plan = plans[0]
        assert plan.kind is AssetKind.PDF
        hosts_seen.add(httpx.URL(plan.url).host or "")

        io = FakeFetchIO()
        result = adapter.fetch_asset(plan, io)
        assert result.ok is True
        assert io.data == pdf_bytes
        assert io.data.startswith(b"%PDF")

    # 双域端到端（design §6.3 明确要求）：resolve 产出的 AssetPlan.url 覆盖两种
    # 托管形态，且完全来自带内 pdf_url（resolve 阶段零网络、未按卷号推断域）。
    assert hosts_seen == {"raw.githubusercontent.com", "proceedings.mlr.press"}


# --- 0-div 消歧：合法空卷 vs parse 漂移，经完整 enumerate→upsert 路径 -----------------------------


def test_legal_empty_volume_completes_with_zero_papers(repo: Repo) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "bibliography.bib" in str(request.url):
            return httpx.Response(200, content=fixture_bytes("07_bibliography_empty.bib"))
        return httpx.Response(200, content=fixture_bytes("06_volume_index_empty.html"))

    issue = _issue_v202()
    issue_id = repo.upsert_issue(issue, source="pmlr")
    harvested = _harvest(repo, _adapter(handler), issue, issue_id)
    assert harvested == 0  # 合法空卷：正常完成，非错误
    assert repo.list_papers(_VENUE_ID) == []


def test_parse_drift_error_propagates_through_full_chain(repo: Repo) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "bibliography.bib" in str(request.url):
            return httpx.Response(200, content=fixture_bytes("02_bibliography_normal.bib"))
        return httpx.Response(200, content=fixture_bytes("04_volume_index_parse_fault.html"))

    issue = _issue_v235()
    issue_id = repo.upsert_issue(issue, source="pmlr")
    with pytest.raises(CrawlerError) as exc:
        _harvest(repo, _adapter(handler), issue, issue_id)
    assert exc.value.error_class is ErrorClass.PARSE
    # 未提交部分数据（parse 在生成 stub 前于 enumerate 内部抛出）。
    assert repo.list_papers(_VENUE_ID) == []


# --- 错误路由（adapter 边界的 ErrorClass 契约）------------------------------------------------


def test_error_routing_volume_page_404_is_gone(repo: Repo) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, content=fixture_bytes("05_volume_404.html"))

    issue = _issue_v235()
    issue_id = repo.upsert_issue(issue, source="pmlr")
    with pytest.raises(CrawlerError) as exc:
        _harvest(repo, _adapter(handler), issue, issue_id)
    assert exc.value.error_class is ErrorClass.GONE


def test_error_routing_volume_page_503_is_transient(repo: Repo) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, content=b"down")

    issue = _issue_v235()
    issue_id = repo.upsert_issue(issue, source="pmlr")
    with pytest.raises(CrawlerError) as exc:
        _harvest(repo, _adapter(handler), issue, issue_id)
    assert exc.value.error_class is ErrorClass.TRANSIENT
