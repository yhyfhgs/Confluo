"""arxiv enumerate→upsert 回放集成（Phase 2 T5；arxiv.md §6 T4 集成、AC-2.3 离线证据层）。

用 `httpx.MockTransport` 喂合成 fixture 走 enumerate→`Repo.upsert_paper` 全链路，断言：
字段落库（两代 id、meta 的 journal_ref/doi、子分类过滤）、重叠窗口去重（identifier 锚点）、
空桶（noRecordsMatch）正常完成、错误路由（503/badToken/400 → 各自 ErrorClass）。零真实网络。

注：完整 watch 编排（当月桶级联 + 七收割日 announce-延迟回放，AC-2.3 ③ / D-018）属 T6/T7
runbook；本文件覆盖 enumerate→upsert 这一「全链路」段与去重/空桶/错误路由的机制正确性。
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

from helpers import make_arxiv_venue
from helpers.arxiv_fixtures import fixture_bytes, http_fixture
from paper_crawler.adapters.arxiv.adapter import ArxivAdapter
from paper_crawler.errors import CrawlerError, ErrorClass
from paper_crawler.http import HttpClient
from paper_crawler.storage.db import Database
from paper_crawler.storage.repo import Repo
from paper_crawler.types import IssueRef

_UA = "PaperCrawler/test (personal research; mailto:test@example.com)"
_VENUE_ID = "arxiv_cs_lg"


def _bucket() -> IssueRef:
    return IssueRef(venue_id=_VENUE_ID, volume=None, number="01", year=2024, label="2024-01")


def _adapter(handler: object) -> ArxivAdapter:
    client = HttpClient(user_agent=_UA, transport=httpx.MockTransport(handler))  # type: ignore[arg-type]
    return ArxivAdapter(http=client)


def _paging_handler(request: httpx.Request) -> httpx.Response:
    """OAI ListRecords 首页/续页分发（resumptionToken 命中 → 第二页）。"""
    if "resumptionToken" in request.url.params:
        return httpx.Response(200, content=fixture_bytes("02_oai_listrecords_page2.xml"))
    return httpx.Response(200, content=fixture_bytes("02_oai_listrecords_page1.xml"))


@pytest.fixture
def repo(tmp_path: Path) -> Iterator[Repo]:
    db = Database(tmp_path / "arxiv.sqlite")
    db.migrate()
    r = Repo(db)
    r.upsert_venue(make_arxiv_venue())  # paper/issue.venue_id 外键前置
    yield r
    db.close()


def _harvest(repo: Repo, adapter: ArxivAdapter, issue_id: str) -> int:
    venue = make_arxiv_venue()
    count = 0
    for stub in adapter.enumerate_issue(venue, _bucket()):
        repo.upsert_paper(_VENUE_ID, issue_id, stub)
        count += 1
    return count


def _identifiers(repo: Repo) -> set[tuple[str, str]]:
    rows = repo.db.query("SELECT scheme, value FROM identifier")
    return {(str(r["scheme"]), str(r["value"])) for r in rows}


# --- enumerate→upsert 字段落库 ---------------------------------------------------------------


def test_paging_upserts_both_id_generations_with_fields(repo: Repo) -> None:
    issue_id = repo.upsert_issue(_bucket(), source="arxiv")
    harvested = _harvest(repo, _adapter(_paging_handler), issue_id)

    # cs.LG 命中 3 条（新+老+新）；cs.CL 被子分类过滤、deleted 墓碑被跳过。
    assert harvested == 3
    assert _identifiers(repo) == {
        ("arxiv", "2401.10001"),
        ("arxiv", "cs.lg/0401001"),  # 老代小写归一
        ("arxiv", "2401.10003"),
    }

    papers = {str(p["title"]): p for p in repo.list_papers(_VENUE_ID)}
    lead = papers["A Robust Framework for Scalable Representation Learning"]
    assert lead["year"] == 2024  # 从 created 2024-01-10 派生
    assert json.loads(str(lead["meta_json"])) == {
        "doi": "10.1000/ex.2024.10001",
        "journal_ref": "Proc. Example ML Conf. 2024, pp. 1-12",
        # R3b（审计 P1-9）：pull 路径与 aggregator 路径同口径落首作者姓氏——弱信号比对锚，
        # 键名/推导与 `Repo._create_paper` 逐字同源（`merge._first_author_surname`）。
        "_first_author": "lovelace",
    }
    # cs.CL 论文（2401.10002）不入库。
    assert ("arxiv", "2401.10002") not in _identifiers(repo)


def test_paper_issue_link_created_for_bucket(repo: Repo) -> None:
    issue_id = repo.upsert_issue(_bucket(), source="arxiv")
    _harvest(repo, _adapter(_paging_handler), issue_id)
    linked = repo.list_papers(_VENUE_ID, issue_id=issue_id)
    assert len(linked) == 3  # 三篇都建了 paper_issue_link


# --- 重叠窗口去重（identifier 锚点）----------------------------------------------------------


def test_overlapping_reharvest_does_not_duplicate(repo: Repo) -> None:
    issue_id = repo.upsert_issue(_bucket(), source="arxiv")
    first = _harvest(repo, _adapter(_paging_handler), issue_id)
    second = _harvest(repo, _adapter(_paging_handler), issue_id)  # 重叠整窗重收
    assert first == second == 3
    # 两轮各产出 3 条，但 identifier 主键天然去重 → 仍是 3 篇 paper。
    assert len(repo.list_papers(_VENUE_ID)) == 3
    assert len(_identifiers(repo)) == 3


# --- 空桶（noRecordsMatch）正常完成 ----------------------------------------------------------


def test_empty_bucket_norecordsmatch_completes_clean(repo: Repo) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=fixture_bytes("10_oai_norecordsmatch.xml"))

    issue_id = repo.upsert_issue(_bucket(), source="arxiv")
    assert _harvest(repo, _adapter(handler), issue_id) == 0  # 空日 watch 常态：零记录、无异常
    assert repo.list_papers(_VENUE_ID) == []


# --- 错误路由（adapter 边界的 ErrorClass 契约）-----------------------------------------------


def test_error_routing_bad_resumption_token_is_transient(repo: Repo) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=fixture_bytes("07_oai_bad_resumption_token.xml"))

    with pytest.raises(CrawlerError) as exc:
        _harvest(repo, _adapter(handler), repo.upsert_issue(_bucket(), source="arxiv"))
    assert exc.value.error_class is ErrorClass.TRANSIENT


def test_error_routing_503_retry_after_is_rate_limited(repo: Repo) -> None:
    status, headers, body = http_fixture("06_oai_503_retry_after.http")

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, headers=headers, content=body)

    with pytest.raises(CrawlerError) as exc:
        _harvest(repo, _adapter(handler), repo.upsert_issue(_bucket(), source="arxiv"))
    assert exc.value.error_class is ErrorClass.RATE_LIMITED
    assert "retry_after_s=120" in exc.value.detail


def test_error_routing_400_offset_is_config(repo: Repo) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, content=fixture_bytes("08_query_400_offset.xml"))

    with pytest.raises(CrawlerError) as exc:
        _harvest(repo, _adapter(handler), repo.upsert_issue(_bucket(), source="arxiv"))
    assert exc.value.error_class is ErrorClass.CONFIG
