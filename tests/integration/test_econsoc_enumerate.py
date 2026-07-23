"""econsoc discover→enumerate→resolve→fetch→upsert 全链路 + ECMA 分段路由集成（Phase 5 T6，
design/adapters/econsoc.md §7 T4）。

用 `httpx.MockTransport` 喂合成 fixture 走全链路，断言：TE/QE OAI 收割按 DOI 后缀刊别
membership + dc:date 年 partition 落盘正确（当前年 2024 / 历史年 2006 各自只落自己的记录、
QE 记录被 TE 枚举丢弃）；当前年重复 enumerate 无重复无遗漏（identifier('doi') 去重）；墓碑
跳过计数经 obslog 暴露；landing→galley resolve + PDF fetch 端到端；ECMA 域名分段三分流
（current→galley / backfile→no_entitlement / pre-DOI→零资产）；错误路由。零真实网络。
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

from helpers import FakeFetchIO, make_econsoc_ecma_venue, make_econsoc_teqe_venue
from helpers.econsoc_fixtures import fixture_bytes
from paper_crawler.adapters.econsoc.adapter import EconsocAdapter
from paper_crawler.errors import Challenged, CrawlerError, ErrorClass
from paper_crawler.http import HttpClient
from paper_crawler.storage.db import Database
from paper_crawler.storage.repo import Repo
from paper_crawler.types import AssetKind, IssueRef, PaperStub

_UA = "PaperCrawler/test (personal research; mailto:test@example.com)"
_VENUE_ID = "te"
_PDF = b"%PDF-1.7\nsynthetic econsoc pdf\n%%EOF\n"


def _issue(*, volume: str, year: int) -> IssueRef:
    return IssueRef(venue_id=_VENUE_ID, volume=volume, number=None, year=year, label=f"te-{year}")


def _adapter(handler: object) -> EconsocAdapter:
    client = HttpClient(user_agent=_UA, transport=httpx.MockTransport(handler))  # type: ignore[arg-type]
    return EconsocAdapter(http=client)


def _oai_handler(request: httpx.Request) -> httpx.Response:
    if "resumptionToken" in request.url.params:
        return httpx.Response(200, content=fixture_bytes("02_oai_listrecords_page2.xml"))
    return httpx.Response(200, content=fixture_bytes("01_oai_listrecords_page1.xml"))


def _full_chain_handler(request: httpx.Request) -> httpx.Response:
    if request.url.host == "econtheory.org":
        return _oai_handler(request)
    if "/file/" in request.url.path:
        return httpx.Response(200, content=_PDF)
    return httpx.Response(200, content=fixture_bytes("03_landing_with_galley.html"))


@pytest.fixture
def repo(tmp_path: Path) -> Iterator[Repo]:
    db = Database(tmp_path / "econsoc.sqlite")
    db.migrate()
    r = Repo(db)
    r.upsert_venue(make_econsoc_teqe_venue("te"))  # paper/issue.venue_id 外键前置
    yield r
    db.close()


def _harvest(repo: Repo, adapter: EconsocAdapter, issue: IssueRef, issue_id: str) -> int:
    venue = make_econsoc_teqe_venue("te")
    count = 0
    for stub in adapter.enumerate_issue(venue, issue):
        repo.upsert_paper(_VENUE_ID, issue_id, stub)
        count += 1
    return count


def _identifiers(repo: Repo) -> set[tuple[str, str]]:
    rows = repo.db.query("SELECT scheme, value FROM identifier")
    return {(str(r["scheme"]), str(r["value"])) for r in rows}


# --- TE 收割：DOI 后缀刊别 membership + dc:date 年 partition ------------------------------------


def test_current_year_harvest_partitions_only_te_2024(repo: Repo) -> None:
    issue = _issue(volume="19", year=2024)
    issue_id = repo.upsert_issue(issue, source="econsoc")
    harvested = _harvest(repo, _adapter(_oai_handler), issue, issue_id)
    # te6021/te6022 页1 + te6023 页2（journal=te ∧ year=2024）；QE 丢、2006 丢、墓碑跳。
    assert harvested == 3
    assert _identifiers(repo) == {
        ("doi", "10.3982/te6021"),
        ("doi", "10.3982/te6022"),
        ("doi", "10.3982/te6023"),
    }
    papers = {str(p["title"]): p for p in repo.list_papers(_VENUE_ID)}
    lead = papers["Stability and Incentive Compatibility in Two-Sided Markets"]
    assert lead["year"] == 2024


def test_historical_year_harvest_partitions_only_te_2006(repo: Repo) -> None:
    issue = _issue(volume="1", year=2006)
    issue_id = repo.upsert_issue(issue, source="econsoc")
    harvested = _harvest(repo, _adapter(_oai_handler), issue, issue_id)
    assert harvested == 2  # te0001 页1 + te0002 页2（year=2006）
    assert _identifiers(repo) == {("doi", "10.3982/te0001"), ("doi", "10.3982/te0002")}


def test_qe_venue_membership_drops_te_records(repo: Repo) -> None:
    # QE venue（ojs_code=qe）对同一多刊 fixture 只保留 qe 后缀记录（DOI 后缀 membership）。
    qe_venue = make_econsoc_teqe_venue("qe")
    papers = list(
        _adapter(_oai_handler).enumerate_issue(
            qe_venue, IssueRef(venue_id="qe", volume="15", year=2024)
        )
    )
    assert {dict(p.identifiers)["doi"] for p in papers} == {"10.3982/qe2297"}


def test_overlapping_reharvest_does_not_duplicate(repo: Repo) -> None:
    issue = _issue(volume="19", year=2024)
    issue_id = repo.upsert_issue(issue, source="econsoc")
    first = _harvest(repo, _adapter(_oai_handler), issue, issue_id)
    second = _harvest(repo, _adapter(_oai_handler), issue, issue_id)
    # 重叠回看窗两趟各产 3；DOI 主键去重 → DB 内恒 3 篇/3 identifier（无重复无遗漏）。
    assert first == second == 3
    assert len(repo.list_papers(_VENUE_ID)) == 3
    assert len(_identifiers(repo)) == 3


def test_tombstone_skip_count_surfaced_via_obslog(
    repo: Repo, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[dict[str, object]] = []
    monkeypatch.setattr(
        "paper_crawler.adapters.econsoc.adapter.log_event",
        lambda level, msg, **kw: events.append({"level": level, "msg": msg, **kw}),
    )
    issue = _issue(volume="19", year=2024)
    issue_id = repo.upsert_issue(issue, source="econsoc")
    _harvest(repo, _adapter(_oai_handler), issue, issue_id)
    tombstone = [e for e in events if e["msg"] == "oai tombstones skipped"]
    assert len(tombstone) == 1
    assert tombstone[0]["skipped_tombstones"] == 1


# --- 全链路：TE discover→enumerate→resolve(landing→galley)→fetch --------------------------------


def test_full_chain_te_discover_enumerate_resolve_fetch(repo: Repo) -> None:
    adapter = _adapter(_full_chain_handler)
    venue = make_econsoc_teqe_venue("te")

    issues = list(adapter.discover_timeline(venue))
    assert {i.year for i in issues} == {2006, 2024}
    target = next(i for i in issues if i.year == 2024)

    papers = list(adapter.enumerate_issue(venue, target))
    assert len(papers) == 3

    downloaded = 0
    for paper in papers:
        plans = adapter.resolve_assets(venue, paper)
        assert len(plans) == 1
        plan = plans[0]
        assert plan.kind is AssetKind.PDF
        assert httpx.URL(plan.url).host == "www.econometricsociety.org"
        assert "/file/" in plan.url
        io = FakeFetchIO()
        result = adapter.fetch_asset(plan, io)
        assert result.ok is True
        assert io.data == _PDF
        downloaded += 1
    assert downloaded == 3


# --- ECMA 域名分段三分流（current / backfile→no_entitlement / pre-DOI→零资产）------------------


def test_ecma_segment_three_way_split() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, content=fixture_bytes("03_landing_with_galley.html"))

    adapter = _adapter(handler)
    ecma = make_econsoc_ecma_venue()

    # ① 当前段（econometricsociety.org 域名）→ galley AssetPlan（触网 GET 落地页）。
    current = adapter.resolve_assets(
        ecma,
        PaperStub(
            title="Current ECMA",
            identifiers=(("doi", "10.3982/ecta23709"),),
            meta=(("primary_url_domain", "www.econometricsociety.org"),),
        ),
    )
    assert len(current) == 1 and current[0].kind is AssetKind.PDF

    # ② 过刊段（doi.wiley.com 域名）→ NO_ENTITLEMENT（跨 adapter handoff defer，零网络）。
    with pytest.raises(CrawlerError) as backfile:
        adapter.resolve_assets(
            ecma,
            PaperStub(
                title="Backfile ECMA",
                identifiers=(("doi", "10.3982/ecta12058"),),
                meta=(("primary_url_domain", "doi.wiley.com"),),
            ),
        )
    assert backfile.value.error_class is ErrorClass.NO_ENTITLEMENT

    # ③ pre-DOI 段（10.2307/JSTOR）→ 界外零资产（非错误，零网络）。
    pre_doi = adapter.resolve_assets(
        ecma, PaperStub(title="Pre-DOI ECMA", identifiers=(("doi", "10.2307/1912227"),))
    )
    assert pre_doi == []

    # 分流计数：仅当前段触网（②③ 分段前置判定，未触落地页）。
    assert sum(1 for u in calls if "/doi/" in u) == 1


# --- 错误路由（adapter 边界的 ErrorClass 契约）------------------------------------------------


def test_error_routing_oai_page_503_is_transient(repo: Repo) -> None:
    handler = lambda request: httpx.Response(503, content=b"down")  # noqa: E731
    issue = _issue(volume="19", year=2024)
    issue_id = repo.upsert_issue(issue, source="econsoc")
    with pytest.raises(CrawlerError) as exc:
        _harvest(repo, _adapter(handler), issue, issue_id)
    assert exc.value.error_class is ErrorClass.TRANSIENT


def test_error_routing_galley_returns_html_is_gone() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "/file/" in request.url.path:
            return httpx.Response(200, content=fixture_bytes("05_galley_not_pdf.html"))
        return httpx.Response(200, content=fixture_bytes("03_landing_with_galley.html"))

    adapter = _adapter(handler)
    venue = make_econsoc_teqe_venue("te")
    plan = adapter.resolve_assets(
        venue, PaperStub(title="X", identifiers=(("doi", "10.3982/te6021"),))
    )[0]
    with pytest.raises(CrawlerError) as exc:
        adapter.fetch_asset(plan, FakeFetchIO())
    assert exc.value.error_class is ErrorClass.GONE


def test_error_routing_cf_challenge_landing_is_challenge() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=fixture_bytes("04_cf_challenge.html"))

    adapter = _adapter(handler)
    venue = make_econsoc_teqe_venue("te")
    with pytest.raises(Challenged) as exc:
        adapter.resolve_assets(
            venue, PaperStub(title="X", identifiers=(("doi", "10.3982/te6021"),))
        )
    assert exc.value.error_class is ErrorClass.CHALLENGE
