"""openreview 十一件套 fixture 保真/落点测试（design/adapters/openreview.md §7 T3）。

每件 fixture → 预期解析形态或 error_class 落点：§6 全部 error_class（含 transient/config）
各有落点。JSON 形态件走 parse.*；错误状态码件经 `HttpClient(MockTransport)` 走真实
状态→ErrorClass 映射（403 额外经 adapter `_get_bytes` 重分类 auth_expired）。零真实网络。
"""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from helpers import make_openreview_venue
from helpers.openreview_fixtures import fixture_bytes, http_fixture
from paper_crawler.adapters.openreview import parse
from paper_crawler.adapters.openreview.adapter import OpenReviewAdapter
from paper_crawler.adapters.openreview.parse import ApiVersion
from paper_crawler.errors import CrawlerError, ErrorClass
from paper_crawler.http import HttpClient
from paper_crawler.types import IssueRef

_UA = "PaperCrawler/test (personal research; mailto:test@example.com)"


# --- 形态件（JSON body）--------------------------------------------------------------------


def test_01_v2_notes_normal_accepted_filter_and_pdf() -> None:
    page = parse.parse_notes_page(fixture_bytes("01_v2_notes_normal.json"), ApiVersion.V2)
    assert page.count == 3
    venueid = "ICLR.cc/2024/Conference"
    accepted = [n for n in page.notes if parse.is_accepted(n, venueid)]
    assert [n.forum for n in accepted] == ["acc0001pdf", "acc0002nopdf"]  # rej 被排除
    # ①含 pdf ②≥1 条无 pdf（设计 §7 要求）
    assert accepted[0].pdf is not None
    assert accepted[1].pdf is None


def test_02_paged_pages_cover_count() -> None:
    p1 = parse.parse_notes_page(fixture_bytes("02_v2_notes_paged_page1.json"), ApiVersion.V2)
    p2 = parse.parse_notes_page(fixture_bytes("02_v2_notes_paged_page2.json"), ApiVersion.V2)
    assert p1.count == p2.count == 3  # count>页内条数（分页）
    assert len(p1.notes) == 2 and len(p2.notes) == 1  # 累计 3 == count


def test_03_empty_is_legal_empty() -> None:
    page = parse.parse_notes_page(fixture_bytes("03_notes_empty.json"), ApiVersion.V2)
    assert page.notes == () and page.count == 0


def test_04_groups_venues_cross_validates_builtin_table() -> None:
    # 届表交叉验证：venues 主表的 ICLR.cc/* 与内置届表非空年逐一吻合（大小写精确）。
    from paper_crawler.adapters.openreview import venues

    ids = set(parse.group_ids(fixture_bytes("04_groups_venues.json")))  # 含 "venues" 自身
    members = _venues_members(fixture_bytes("04_groups_venues.json"))
    table = venues.resolve_venue_table(make_openreview_venue())
    for year, venueid in table.items():
        if venueid is not None:
            assert venueid in members, f"{year}: {venueid} not in venues main table"
    assert "venues" in ids


def test_04_group_2024_detected_as_v2() -> None:
    v = parse.api_version_from_groups(
        fixture_bytes("04_group_2024_v2.json"), "ICLR.cc/2024/Conference"
    )
    assert v is ApiVersion.V2


def test_04_group_2014_detected_as_v1() -> None:
    v = parse.api_version_from_groups(
        fixture_bytes("04_group_2014_v1.json"), "ICLR.cc/2014/conference"
    )
    assert v is ApiVersion.V1


def test_05_v1_notes_direct_take_and_arxiv_meta() -> None:
    page = parse.parse_notes_page(fixture_bytes("05_v1_notes_page.json"), ApiVersion.V1)
    (note,) = page.notes
    assert note.title == "An Early ICLR Paper With arXiv Body"
    assert note.venueid == "ICLR.cc/2014/conference"
    assert note.arxiv == "1312.6173"  # 线索入 meta（非 identifier）
    assert note.pdf is None  # 2014 正文在 arXiv


def test_09_malformed_raises_parse() -> None:
    with pytest.raises(CrawlerError) as exc:
        parse.parse_notes_page(fixture_bytes("09_malformed.json"), ApiVersion.V2)
    assert exc.value.error_class is ErrorClass.PARSE


# --- 错误状态码件（.http）：真实状态→ErrorClass 映射落点 -----------------------------------


def _client_for(name: str) -> HttpClient:
    status, headers, body = http_fixture(name)

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, headers=headers, content=body)

    return HttpClient(user_agent=_UA, transport=httpx.MockTransport(handler))


def _enumerate(client: HttpClient) -> Callable[[], list[object]]:
    adapter = OpenReviewAdapter(http=client)
    issue = IssueRef(venue_id="iclr", year=2024, label="2024")
    return lambda: list(adapter.enumerate_issue(make_openreview_venue(), issue))


def test_06_challenge_403_reclassified_to_auth_expired() -> None:
    # 冻结 HttpClient：403→no_entitlement；adapter enumerate 重分类→auth_expired（§6）。
    with pytest.raises(CrawlerError) as exc:
        _enumerate(_client_for("06_challenge_403.http"))()
    assert exc.value.error_class is ErrorClass.AUTH_EXPIRED


def test_06_challenge_403_raw_http_is_no_entitlement() -> None:
    # 未经 adapter 重分类的裸 HttpClient 层：403 仍是冻结默认 no_entitlement。
    with pytest.raises(CrawlerError) as exc:
        _client_for("06_challenge_403.http").get_bytes("https://api2.openreview.net/notes")
    assert exc.value.error_class is ErrorClass.NO_ENTITLEMENT


def test_07_notfound_404_maps_to_gone() -> None:
    with pytest.raises(CrawlerError) as exc:
        _client_for("07_notfound_404.http").get_bytes("https://api2.openreview.net/groups?id=x")
    assert exc.value.error_class is ErrorClass.GONE


def test_08_ratelimit_429_maps_to_rate_limited_with_retry_after() -> None:
    with pytest.raises(CrawlerError) as exc:
        _client_for("08_ratelimit_429.http").get_bytes("https://api2.openreview.net/notes")
    assert exc.value.error_class is ErrorClass.RATE_LIMITED
    assert "retry_after_s=30" in exc.value.detail


def test_10_server_error_500_maps_to_transient() -> None:
    with pytest.raises(CrawlerError) as exc:
        _client_for("10_server_error_500.http").get_bytes("https://api2.openreview.net/notes")
    assert exc.value.error_class is ErrorClass.TRANSIENT


def test_11_bad_request_400_maps_to_config() -> None:
    with pytest.raises(CrawlerError) as exc:
        _client_for("11_bad_request_400.http").get_bytes("https://api2.openreview.net/notes")
    assert exc.value.error_class is ErrorClass.CONFIG


# --- 辅助 ------------------------------------------------------------------------------------


def _venues_members(data: bytes) -> set[str]:
    import json

    doc = json.loads(data)
    members: set[str] = set()
    for group in doc["groups"]:
        for member in group.get("members", []):
            members.add(member)
    return members
