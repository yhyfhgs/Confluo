"""nber/rss.py 单测（MockTransport 注入，零真实网络；design/adapters/nber.md §3.4；
Phase 6 T7 检查单 #3）。

覆盖：program 代码归一 + feed URL 映射（含未知代码 CONFIG）、映射表键集 == 已声明支持
集合的 contract 自断言（防清单漂移）、单 feed fixture 解析回归（正常/空/畸形三态）、
`discover_incremental` 端到端（一 feed 一请求、多 program 顺序、路由恒落 back.nber.org
不触 crossref、未知 program 零部分请求副作用）、`to_paper_stub` 字段映射、id 集合差分
桥接（`ids_of`/`new_entries`）、作者尾巴拆分与 pubDate 解析的边界启发式。
"""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from helpers.nber_fixtures import fixture_bytes
from paper_crawler.adapters.nber import rss
from paper_crawler.errors import CrawlerError, ErrorClass
from paper_crawler.http import HttpClient

_UA = "PaperCrawler/test (personal research; mailto:test@example.com)"

Handler = Callable[[httpx.Request], httpx.Response]


def _never(_request: httpx.Request) -> httpx.Response:
    raise AssertionError("no network expected for this path")


def _client_for(handler: Handler) -> HttpClient:
    return HttpClient(user_agent=_UA, transport=httpx.MockTransport(handler))


# --- program 代码归一 + feed URL 映射 -----------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("AP", "AP"),
        ("ap", "AP"),
        ("  Cf  ", "CF"),
        ("efg", "EFG"),
        ("Ifm", "IFM"),
        ("me", "ME"),
    ],
)
def test_normalize_program(raw: str, expected: str) -> None:
    assert rss.normalize_program(raw) == expected


def test_normalize_program_unknown_raises_config() -> None:
    with pytest.raises(CrawlerError) as exc:
        rss.normalize_program("PE")  # 明确排除（两义未核验，模块 docstring）
    assert exc.value.error_class is ErrorClass.CONFIG
    assert "PE" in str(exc.value)


def test_normalize_program_unlisted_code_raises_config() -> None:
    """官方声称 19 个 program 里未获本项目证据的代码（如 "LS"）同样拒载，不臆造 URL。"""
    with pytest.raises(CrawlerError) as exc:
        rss.normalize_program("LS")
    assert exc.value.error_class is ErrorClass.CONFIG


@pytest.mark.parametrize(
    ("program", "expected_url"),
    [
        ("AP", "https://back.nber.org/rss/newap.xml"),
        ("CF", "https://back.nber.org/rss/newcf.xml"),
        ("EFG", "https://back.nber.org/rss/newefg.xml"),
        ("IFM", "https://back.nber.org/rss/newifm.xml"),
        ("ME", "https://back.nber.org/rss/newme.xml"),
    ],
)
def test_feed_url_matches_naming_pattern(program: str, expected_url: str) -> None:
    assert rss.feed_url(program) == expected_url


def test_feed_url_case_insensitive() -> None:
    assert rss.feed_url("cf") == rss.feed_url("CF")


def test_feed_url_unknown_program_raises_config() -> None:
    with pytest.raises(CrawlerError) as exc:
        rss.feed_url("ZZ")
    assert exc.value.error_class is ErrorClass.CONFIG


def test_program_feed_mapping_matches_supported_programs() -> None:
    """映射表键集 == 已声明支持集合（集合等值自断言，防 canary 式清单漂移反模式，F5 口径）。"""
    assert set(rss.PROGRAM_FEEDS) == rss.SUPPORTED_PROGRAMS


def test_supported_programs_is_five_of_nineteen() -> None:
    """如实反映证据缺口：NBER 官方声称 19 个 program，本项目只对 5 个有 [VERIFIED] 代码。"""
    assert rss.SUPPORTED_PROGRAMS == frozenset({"AP", "CF", "EFG", "IFM", "ME"})
    assert len(rss.SUPPORTED_PROGRAMS) == 5


# --- 单 feed fixture 解析回归（正常/空/畸形）------------------------------------------------


def test_parse_feed_entries_fixture() -> None:
    """[LIVE 结构对齐 newcf.xml] 3 item：逗号作者 / and-连接作者 / 无作者尾巴 + w/t 前缀。"""
    data = fixture_bytes("06_rss_program_cf_synth.xml")
    entries = rss._parse_feed_entries(data, program="CF")
    assert len(entries) == 3

    first, second, third = entries

    assert first.program == "CF"
    assert first.doi == "10.3386/w40001"
    assert first.series_id == "w40001"
    assert first.title == "Synthetic Capital Structure Adjustment Speeds"
    assert first.authors == ("Alice Adams", "Bob Brown")
    assert first.abstract is not None and "capital structure" in first.abstract
    assert first.url == "https://www.nber.org/papers/w40001"
    assert first.pub_date == "2026-07-20"  # RFC 2822 -> ISO

    assert second.series_id == "t0150"  # t-series 前缀覆盖
    assert second.authors == ("Carol Cooper", "Dave Diaz")  # 无逗号的 "and" 连接
    assert second.pub_date is None  # 缺 <pubDate> 标签

    assert third.title == "Synthetic Note Without An Author Tail"
    assert third.authors == ()  # 无 "-- by" 尾巴
    assert third.pub_date is None  # <pubDate> 畸形文本，尽力而为不 raise


def test_parse_feed_entries_empty_feed_is_not_an_error() -> None:
    """零 <item> 是合法结果（某周无新增），不是异常——返回空元组。"""
    data = fixture_bytes("07_rss_program_empty.xml")
    assert rss._parse_feed_entries(data, program="AP") == ()


def test_parse_feed_entries_malformed_xml_raises_parse() -> None:
    """畸形 XML → fail-loud PARSE（同 `parse.parse_rss_items` 红线口径）。"""
    data = fixture_bytes("08_rss_program_malformed.xml")
    with pytest.raises(CrawlerError) as exc:
        rss._parse_feed_entries(data, program="AP")
    assert exc.value.error_class is ErrorClass.PARSE


def test_parse_feed_entries_skips_item_without_resolvable_guid() -> None:
    body = (
        b"<rss><channel><item><title>No stable id -- by Nobody</title>"
        b"<guid>https://www.nber.org/feed/entry/1</guid></item></channel></rss>"
    )
    assert rss._parse_feed_entries(body, program="AP") == ()


def test_parse_feed_entries_missing_guid_is_skipped() -> None:
    body = b"<rss><channel><item><title>No guid at all</title></item></channel></rss>"
    assert rss._parse_feed_entries(body, program="AP") == ()


# --- discover_incremental：端到端 + 路由专测 -------------------------------------------------


def test_discover_incremental_single_program_yields_parsed_entries() -> None:
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        return httpx.Response(200, content=fixture_bytes("06_rss_program_cf_synth.xml"))

    entries = list(rss.discover_incremental(["cf"], _client_for(handler)))
    assert len(entries) == 3
    assert all(e.program == "CF" for e in entries)
    assert requested == ["https://back.nber.org/rss/newcf.xml"]


def test_discover_incremental_one_request_per_program_in_order() -> None:
    """严格一 feed 一请求；多 program 按传入顺序逐一请求（DoD "每 feed 一次请求语义"）。"""
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        return httpx.Response(200, content=fixture_bytes("07_rss_program_empty.xml"))

    list(rss.discover_incremental(["ap", "CF", "me"], _client_for(handler)))
    assert requested == [
        "https://back.nber.org/rss/newap.xml",
        "https://back.nber.org/rss/newcf.xml",
        "https://back.nber.org/rss/newme.xml",
    ]


def test_discover_incremental_watch_routes_to_back_host_never_crossref() -> None:
    """watch 场景 nber 走 RSS 不走 crossref 枚举的路由专测：请求域恒 back.nber.org。

    mock transport 对任何非 back.nber.org 的请求直接断言失败（而不仅是事后检查捕获
    列表）——确保即便实现改动，一旦意外发往 api.crossref.org 之类的枚举域，测试立刻
    在请求发出的瞬间炸掉，而非仅凭"事后 host 集合比对"这种可能被绕过的弱检查。
    """

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "back.nber.org", f"unexpected host: {request.url.host}"
        assert request.url.host != "api.crossref.org"
        return httpx.Response(200, content=fixture_bytes("07_rss_program_empty.xml"))

    list(rss.discover_incremental(["AP", "EFG", "IFM"], _client_for(handler)))


def test_discover_incremental_unknown_program_raises_before_any_request() -> None:
    """全量校验先行：未知 program 在**任何**请求发出前拒载（零部分请求副作用）。"""
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, content=fixture_bytes("07_rss_program_empty.xml"))

    with pytest.raises(CrawlerError) as exc:
        list(rss.discover_incremental(["AP", "NOTREAL"], _client_for(handler)))
    assert exc.value.error_class is ErrorClass.CONFIG
    assert calls == []  # 连合法的 "AP" 也没被请求——校验发生在循环之前


def test_discover_incremental_empty_programs_yields_nothing() -> None:
    assert list(rss.discover_incremental([], _client_for(_never))) == []


# --- to_paper_stub 字段映射 -------------------------------------------------------------------


def test_to_paper_stub_maps_fields_and_carries_program_in_meta() -> None:
    entry = rss.NberWatchEntry(
        program="AP",
        doi="10.3386/w40001",
        series_id="w40001",
        title="Synthetic Capital Structure Adjustment Speeds",
        authors=("Alice Adams", "Bob Brown"),
        abstract="A synthetic abstract.",
        url="https://www.nber.org/papers/w40001",
        pub_date="2026-07-20",
    )
    stub = entry.to_paper_stub()
    assert stub.title == entry.title
    assert stub.identifiers == (("doi", "10.3386/w40001"),)
    assert stub.authors == ("Alice Adams", "Bob Brown")
    assert stub.abstract == "A synthetic abstract."
    assert stub.pub_date == "2026-07-20"
    assert ("program", "AP") in stub.meta
    assert ("series_id", "w40001") in stub.meta
    assert ("url", "https://www.nber.org/papers/w40001") in stub.meta


def test_diff_id_is_series_id() -> None:
    entry = rss.NberWatchEntry(
        program="AP",
        doi="10.3386/w1",
        series_id="w1",
        title="t",
        authors=(),
        abstract=None,
        url="https://www.nber.org/papers/w1",
        pub_date=None,
    )
    assert entry.diff_id == "w1"


# --- id 集合差分桥接（T4/T5 接缝占位）----------------------------------------------------------


def _entry(series_id: str) -> rss.NberWatchEntry:
    return rss.NberWatchEntry(
        program="AP",
        doi=f"10.3386/{series_id}",
        series_id=series_id,
        title=series_id,
        authors=(),
        abstract=None,
        url=f"https://www.nber.org/papers/{series_id}",
        pub_date=None,
    )


def test_ids_of_collects_diff_ids() -> None:
    entries = (_entry("w1"), _entry("w2"))
    assert rss.ids_of(entries) == frozenset({"w1", "w2"})


def test_new_entries_filters_already_seen() -> None:
    entries = (_entry("w1"), _entry("w2"), _entry("w3"))
    fresh = rss.new_entries(entries, seen_ids={"w1"})
    assert [e.series_id for e in fresh] == ["w2", "w3"]


def test_new_entries_empty_seen_returns_all() -> None:
    entries = (_entry("w1"), _entry("w2"))
    assert rss.new_entries(entries, seen_ids=()) == entries


# --- 作者尾巴拆分启发式（边界个案，超出 fixture 覆盖的额外用例）--------------------------------


@pytest.mark.parametrize(
    ("blob", "expected"),
    [
        ("Alice Adams", ("Alice Adams",)),  # 单作者
        ("Alice Adams, Bob Brown", ("Alice Adams", "Bob Brown")),  # 逗号
        ("Alice Adams and Bob Brown", ("Alice Adams", "Bob Brown")),  # 无逗号 and-连接
        (
            "Alice Adams, Bob Brown, and Carol Cooper",
            ("Alice Adams", "Bob Brown", "Carol Cooper"),
        ),  # Oxford 逗号
        (
            "Alice Adams, Bob Brown, Carol Cooper",
            ("Alice Adams", "Bob Brown", "Carol Cooper"),
        ),  # 三作者纯逗号（无 and）
    ],
)
def test_split_authors_heuristic(blob: str, expected: tuple[str, ...]) -> None:
    assert rss._split_authors(blob) == expected


def test_split_title_authors_no_tail_returns_title_unchanged() -> None:
    title, authors = rss._split_title_authors("A Title With No Author Tail")
    assert title == "A Title With No Author Tail"
    assert authors == ()


def test_split_title_authors_strips_tail() -> None:
    title, authors = rss._split_title_authors("Some Paper -- by Alice Adams")
    assert title == "Some Paper"
    assert authors == ("Alice Adams",)


# --- pubDate 尽力而为解析 ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Mon, 20 Jul 2026 00:00:00 GMT", "2026-07-20"),
        (None, None),
        ("", None),
        ("not-a-valid-date", None),
    ],
)
def test_parse_pub_date(raw: str | None, expected: str | None) -> None:
    assert rss._parse_pub_date(raw) == expected
