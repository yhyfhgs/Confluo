"""Crossref cursor 中断 -> 窗口重建 -> DOI 去重端到端（phase3-report.md §6 检查单 #15a）。

补强动机（如实标注）：`test_crossref_adapter.py::test_enumerate_cursor_two_page_continuation`
只证明了单次不中断的完整游标翻页机制（adapter 层，MockTransport 直接断言 stub 列表）；
adapter/parse.py 模块 docstring 承诺的更强性质——"中断续拉按 (issn, year) 窗口**重建**
`cursor=*` 从头（幂等由 `(doi)` identifier 去重天然保证，无重复入库）"——此前没有任何测试
真正驱动到 **存储/合并层**验证"重复重放不重复入库"。本文件补这一端到端用例：adapter
cursor 翻页 + `MergeEngine.ingest` + 真实 sqlite `Repo` 全链路。

手法：
1. 三页 fixture 序列（10/11/12，姊妹夹具于 04a/04b）：page1（2 条 A/B + next-cursor）→
   page2（2 条 C/D + next-cursor）→ page3（空，终止）。
2. **"中断"**：对 `enumerate_issue` 返回的生成器只 `next()` 两次（消费完 page1 的 2 条
   stub），随后**弃置该生成器、不再迭代**——模拟调用方（pipeline/task）在拉完 page1、
   尚未请求 page2 时被杀死；已消费的 2 条经 `MergeEngine.ingest` 入库。
3. **"窗口重建"**：对同一 `(venue, issue)` 发起全新 `enumerate_issue` 调用（cursor 从
   `*` 重新开始，不复用/不接续被弃置的生成器状态——契约就是"不持久化、不跨任务复用"）。
   本次完整走完 3 页，产出 4 条 stub（A/B 重复出现 + 新的 C/D），逐条 ingest。
4. 断言：中断前只发生 1 次 HTTP 请求（page1）；重建后发生 3 次（page1 重新拉取一次 +
   page2 + page3）；重建阶段 A/B 的 `IngestResult.action == "merged"`（DOI 命中既有
   paper，不新建）、C/D 为 `"created"`；终态库内**恰好 4 篇论文**（不是 6 篇）、每篇
   恰 1 个 doi identifier——不重不漏。
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from helpers.crossref_fixtures import fixture_bytes
from paper_crawler.adapters.crossref.adapter import CrossrefAdapter
from paper_crawler.http import HttpClient
from paper_crawler.merge import MergeEngine
from paper_crawler.storage.db import Database
from paper_crawler.storage.repo import Repo
from paper_crawler.types import IssueRef, VenueSpec

_UA = "PaperCrawler/test (personal research; mailto:test@example.com)"

# page1 的 next-cursor 指向 page2；page2 的 next-cursor 指向 page3（空，终止）。
_PAGE1_CURSOR = "*"
_PAGE2_CURSOR = "AoJ4resume4cursor4page2"
_PAGE3_CURSOR = "AoJ4resume4cursor4page3"


def _venue() -> VenueSpec:
    return VenueSpec(
        id="qje",
        kind="journal",
        names={"full": "Quarterly Journal of Economics", "aliases": ["QJE"]},
        field=["econ"],
        identifiers={"issn": ["0033-5533"]},
        metadata_source="crossref",
        fulltext_source="mock_platform",
    )


def _paper_count(repo: Repo) -> int:
    return int(repo.db.query("SELECT COUNT(*) AS n FROM paper")[0]["n"])


def _doi_identifiers(repo: Repo) -> list[str]:
    rows = repo.db.query("SELECT value FROM identifier WHERE scheme = 'doi' ORDER BY value")
    return [str(r["value"]) for r in rows]


def test_cursor_interrupt_then_window_rebuild_dedups_by_doi(tmp_path: Path) -> None:
    database = Database(tmp_path / "crossref-resume.sqlite")
    database.migrate()
    repo = Repo(database)
    engine = MergeEngine(repo)

    request_cursors: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        cursor = request.url.params.get("cursor")
        request_cursors.append(cursor)
        if cursor == _PAGE1_CURSOR:
            return httpx.Response(200, content=fixture_bytes("10_works_cursor_resume_page1.json"))
        if cursor == _PAGE2_CURSOR:
            return httpx.Response(200, content=fixture_bytes("11_works_cursor_resume_page2.json"))
        assert cursor == _PAGE3_CURSOR
        return httpx.Response(200, content=fixture_bytes("12_works_cursor_resume_page3.json"))

    adapter = CrossrefAdapter(
        http=HttpClient(user_agent=_UA, transport=httpx.MockTransport(handler))
    )
    venue = _venue()
    issue = IssueRef(venue_id="qje", year=2024)

    # -- 1) 第一次尝试：只驱动 page1，随后"中断"（生成器被弃置，不再 next()）--------------
    first_attempt = iter(adapter.enumerate_issue(venue, issue))
    interrupted_stubs = [next(first_attempt), next(first_attempt)]
    del first_attempt  # 显式弃置：调用方永远不会再拉 page2（模拟进程被杀）

    assert [s.identifiers[0][1] for s in interrupted_stubs] == [
        "10.1093/qje/qjae020",
        "10.1093/qje/qjae021",
    ]
    for stub in interrupted_stubs:
        result = engine.ingest(stub, source="crossref")
        assert result.action == "created"

    assert request_cursors == [_PAGE1_CURSOR]  # 中断前恰 1 次请求
    assert _paper_count(repo) == 2

    # -- 2) 窗口重建：全新调用，cursor 从 * 重新开始，完整走完 3 页 ------------------------
    rebuilt_stubs = list(adapter.enumerate_issue(venue, issue))
    assert [s.identifiers[0][1] for s in rebuilt_stubs] == [
        "10.1093/qje/qjae020",  # 与中断前重复（窗口重建的必然代价——cursor 不持久化）
        "10.1093/qje/qjae021",
        "10.1093/qje/qjae022",  # 中断前从未到达的新记录
        "10.1093/qje/qjae023",
    ]
    # 重建请求序列：page1 重新拉取 + page2 + page3（终止）——不接续被弃置的旧游标状态。
    assert request_cursors == [_PAGE1_CURSOR, _PAGE1_CURSOR, _PAGE2_CURSOR, _PAGE3_CURSOR]

    rebuilt_actions = [engine.ingest(stub, source="crossref").action for stub in rebuilt_stubs]
    assert rebuilt_actions == ["merged", "merged", "created", "created"]

    # -- 3) 终态：不重不漏 ----------------------------------------------------------------
    assert _paper_count(repo) == 4
    assert _doi_identifiers(repo) == [
        "10.1093/qje/qjae020",
        "10.1093/qje/qjae021",
        "10.1093/qje/qjae022",
        "10.1093/qje/qjae023",
    ]


def test_cursor_interrupt_before_any_page_then_rebuild_is_pure_replay(tmp_path: Path) -> None:
    """边界：中断发生在**第一条记录都还没消费**时（生成器创建但从未 next()）。

    窗口重建等价于该窗口一次干净的完整拉取——本用例把它当"重复重放"的下界样例：
    重建结果与 fixture 全量一致、不发生任何请求泄漏（未消费的生成器不产生副作用）。
    """
    database = Database(tmp_path / "crossref-resume-empty.sqlite")
    database.migrate()
    repo = Repo(database)
    engine = MergeEngine(repo)

    request_cursors: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        cursor = request.url.params.get("cursor")
        request_cursors.append(cursor)
        if cursor == _PAGE1_CURSOR:
            return httpx.Response(200, content=fixture_bytes("10_works_cursor_resume_page1.json"))
        if cursor == _PAGE2_CURSOR:
            return httpx.Response(200, content=fixture_bytes("11_works_cursor_resume_page2.json"))
        assert cursor == _PAGE3_CURSOR
        return httpx.Response(200, content=fixture_bytes("12_works_cursor_resume_page3.json"))

    adapter = CrossrefAdapter(
        http=HttpClient(user_agent=_UA, transport=httpx.MockTransport(handler))
    )
    venue = _venue()
    issue = IssueRef(venue_id="qje", year=2024)

    never_consumed = adapter.enumerate_issue(venue, issue)
    del never_consumed  # 生成器从未 next() 过：零请求（惰性求值，"中断"发生在拉取之前）
    assert request_cursors == []

    rebuilt_stubs = list(adapter.enumerate_issue(venue, issue))
    assert len(rebuilt_stubs) == 4
    for stub in rebuilt_stubs:
        engine.ingest(stub, source="crossref")

    assert _paper_count(repo) == 4
    assert len(_doi_identifiers(repo)) == 4


@pytest.mark.parametrize("n_consumed", [1, 2, 3, 4])
def test_cursor_interrupt_at_various_points_always_dedups_to_four_papers(
    tmp_path: Path, n_consumed: int
) -> None:
    """中断点在 1~4 条（跨 page1/page2 边界）任意位置，重建后终态恒为 4 篇不重复。

    覆盖 `n_consumed in {1,2,3,4}`：1/2 落在 page1 内、3 落在刚跨入 page2 的第 1 条、
    4 落在 page2 的第 2 条（即 page2 也被"中断前"完整消费，只差 page3 的终止探测请求
    未发生）——四个取值把中断点分布在窗口内和窗口尾部，验证 dedup 不因中断点位置而失效。
    """
    database = Database(tmp_path / f"crossref-resume-{n_consumed}.sqlite")
    database.migrate()
    repo = Repo(database)
    engine = MergeEngine(repo)

    def handler(request: httpx.Request) -> httpx.Response:
        cursor = request.url.params.get("cursor")
        if cursor == _PAGE1_CURSOR:
            return httpx.Response(200, content=fixture_bytes("10_works_cursor_resume_page1.json"))
        if cursor == _PAGE2_CURSOR:
            return httpx.Response(200, content=fixture_bytes("11_works_cursor_resume_page2.json"))
        return httpx.Response(200, content=fixture_bytes("12_works_cursor_resume_page3.json"))

    adapter = CrossrefAdapter(
        http=HttpClient(user_agent=_UA, transport=httpx.MockTransport(handler))
    )
    venue = _venue()
    issue = IssueRef(venue_id="qje", year=2024)

    first_attempt = iter(adapter.enumerate_issue(venue, issue))
    for _ in range(n_consumed):
        engine.ingest(next(first_attempt), source="crossref")
    del first_attempt

    assert _paper_count(repo) == n_consumed  # 中断前入库数恰等于消费数（无重复无遗漏）

    for stub in adapter.enumerate_issue(venue, issue):
        engine.ingest(stub, source="crossref")

    assert _paper_count(repo) == 4  # 无论中断点在哪，重建后终态恒为窗口全量、不多不少
    assert len(_doi_identifiers(repo)) == 4
