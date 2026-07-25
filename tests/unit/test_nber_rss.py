"""nber/rss.py 单测（MockTransport 注入，零真实网络；design/adapters/nber.md §3.4；
Phase 6 T7 检查单 #3，含两轮审查后修订回归：P1/P2 + controller 方案 (c) proxy year）。

覆盖：program 代码归一 + feed URL 映射（含未知代码 CONFIG）、映射表键集 == 已声明支持
集合的 contract 自断言（防清单漂移）、单 feed fixture 解析回归（正常/空/畸形三态）、
`discover_incremental`（一 feed 一请求、归一化去重、多 program 顺序、路由恒落
back.nber.org 不触 crossref、**调用即炸的非生成器外壳校验**、`now=` 时钟注入的
`fetch_year` 批内一致性）、`to_paper_stub` 字段映射（**year 派生优先级**：pub_date
派生 > `default_year` proxy 兜底 > 都缺 None，P1 红线 + controller 方案 (c) 裁决）、
id 序列桥接（`ids_of`，喂给 T4 `IdSetDiff`）、作者尾巴拆分（**贪婪匹配取最后一个
"-- by"**）与 pubDate 解析的边界启发式。
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

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


def test_supported_programs_is_five_of_nineteen_all_live_verified() -> None:
    """如实反映证据缺口：NBER 官方声称 19 个 program，本项目 5 个全部 [LIVE] 实证收录。"""
    assert rss.SUPPORTED_PROGRAMS == frozenset({"AP", "CF", "EFG", "IFM", "ME"})
    assert len(rss.SUPPORTED_PROGRAMS) == 5


# --- 单 feed fixture 解析回归（正常/空/畸形）------------------------------------------------


def test_parse_feed_entries_fixture() -> None:
    """[LIVE 结构对齐 newcf.xml] 3 item：逗号作者 / and-连接作者 / 无作者尾巴 + w/t 前缀。"""
    data = fixture_bytes("06_rss_program_cf_synth.xml")
    entries = rss._parse_feed_entries(data, program="CF", fetch_year=2026)
    assert len(entries) == 3
    assert all(e.fetch_year == 2026 for e in entries)

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
    assert rss._parse_feed_entries(data, program="AP", fetch_year=2026) == ()


def test_parse_feed_entries_malformed_xml_raises_parse() -> None:
    """畸形 XML → fail-loud PARSE（同 `parse.parse_rss_items` 红线口径）。"""
    data = fixture_bytes("08_rss_program_malformed.xml")
    with pytest.raises(CrawlerError) as exc:
        rss._parse_feed_entries(data, program="AP", fetch_year=2026)
    assert exc.value.error_class is ErrorClass.PARSE


def test_parse_feed_entries_skips_item_without_resolvable_guid() -> None:
    body = (
        b"<rss><channel><item><title>No stable id -- by Nobody</title>"
        b"<guid>https://www.nber.org/feed/entry/1</guid></item></channel></rss>"
    )
    assert rss._parse_feed_entries(body, program="AP", fetch_year=2026) == ()


def test_parse_feed_entries_missing_guid_is_skipped() -> None:
    body = b"<rss><channel><item><title>No guid at all</title></item></channel></rss>"
    assert rss._parse_feed_entries(body, program="AP", fetch_year=2026) == ()


def test_parse_feed_entries_handles_real_fromrss_guid_fragment() -> None:
    """2026-07-26 在线补测实证：真实 guid 带 `#fromrss` 片段，`doi_from_guid` 须正确反解。"""
    body = (
        b"<rss><channel><item><title>Real Shape -- by Real Author</title>"
        b'<guid isPermaLink="true">https://www.nber.org/papers/w35481#fromrss</guid>'
        b"</item></channel></rss>"
    )
    entries = rss._parse_feed_entries(body, program="AP", fetch_year=2026)
    assert len(entries) == 1
    assert entries[0].doi == "10.3386/w35481"
    assert entries[0].series_id == "w35481"
    assert entries[0].url == "https://www.nber.org/papers/w35481"  # 干净 landing，无片段


# --- discover_incremental：端到端 + 路由专测 + 归一化去重 -------------------------------------


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
    """严格一 feed 一请求；多 program 按传入顺序（去重后）逐一请求。"""
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


def test_discover_incremental_dedupes_normalized_duplicate_programs() -> None:
    """P2#1：归一后重复的 program（大小写/空白不同）只请求一次（省限速预算）。"""
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        return httpx.Response(200, content=fixture_bytes("07_rss_program_empty.xml"))

    list(rss.discover_incremental(["CF", "cf", "  Cf  "], _client_for(handler)))
    assert requested == ["https://back.nber.org/rss/newcf.xml"]


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


def test_discover_incremental_validates_eagerly_without_consuming() -> None:
    """P2#5：非生成器外壳——调用本身（不迭代/不消费返回值）即触发校验并抛错。

    用 `_never` transport：若校验被推迟到迭代时才跑（旧生成器函数语义），本测试
    因为从不迭代返回值，将**观察不到任何异常**（静默通过，掩盖 T5 dry-run 场景下
    "构造了流却不消费"时拼错 program 会被漏检的风险）。断言点是"调用这一行本身"
    必须抛错，而不是包一层 `list()`/`next()` 才抛。
    """
    with pytest.raises(CrawlerError) as exc:
        rss.discover_incremental(["NOTREAL"], _client_for(_never))  # 注意：未迭代、未赋值消费
    assert exc.value.error_class is ErrorClass.CONFIG


def test_discover_incremental_empty_programs_yields_nothing() -> None:
    assert list(rss.discover_incremental([], _client_for(_never))) == []


def test_discover_incremental_injects_fetch_year_from_now() -> None:
    """proxy year 接线：`now=` 注入假时钟（同 `subs/watermark.py` 先例）→ 批内每条
    entry 的 `fetch_year` 都等于该时钟的年份，不逐条重新读真实时钟。
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=fixture_bytes("06_rss_program_cf_synth.xml"))

    entries = list(rss.discover_incremental(["cf"], _client_for(handler), now=date(2025, 12, 30)))
    assert len(entries) == 3
    assert all(e.fetch_year == 2025 for e in entries)


def test_discover_incremental_defaults_fetch_year_to_real_today() -> None:
    """未注入 `now` 时退回真实 UTC 当前年份（非本次断言精确值，只断言"不是随便的数"）。"""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=fixture_bytes("06_rss_program_cf_synth.xml"))

    entries = list(rss.discover_incremental(["cf"], _client_for(handler)))
    assert all(e.fetch_year == rss._today().year for e in entries)


# --- to_paper_stub 字段映射（含 year 派生 + proxy year 兜底，P1 红线）---------------------------


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
        fetch_year=2026,
    )
    stub = entry.to_paper_stub()
    assert stub.title == entry.title
    assert stub.identifiers == (("doi", "10.3386/w40001"),)
    assert stub.authors == ("Alice Adams", "Bob Brown")
    assert stub.abstract == "A synthetic abstract."
    assert stub.pub_date == "2026-07-20"
    assert stub.year == 2026
    assert ("program", "AP") in stub.meta
    assert ("series_id", "w40001") in stub.meta
    assert ("url", "https://www.nber.org/papers/w40001") in stub.meta


# controller 裁决方案 (c)：watch 增量语境 proxy year——3 例测试锁住优先级（pub_date 派生
# 优先 > default_year 兜底 > 都缺才 None）。


def _bare_entry(*, pub_date: str | None) -> rss.NberWatchEntry:
    return rss.NberWatchEntry(
        program="AP",
        doi="10.3386/w1",
        series_id="w1",
        title="t",
        authors=(),
        abstract=None,
        url="https://www.nber.org/papers/w1",
        pub_date=pub_date,
        fetch_year=2026,
    )


def test_to_paper_stub_pub_date_year_takes_priority_over_default_year() -> None:
    """有 pub_date 时，派生年份优先——即便传了 default_year 也不覆盖权威值。"""
    entry = _bare_entry(pub_date="2020-03-01")
    assert entry.to_paper_stub(default_year=2026).year == 2020


def test_to_paper_stub_uses_default_year_when_pub_date_missing() -> None:
    """无 pub_date（RSS 常态）时退回 default_year——proxy year 兜底生效。"""
    entry = _bare_entry(pub_date=None)
    assert entry.to_paper_stub(default_year=2026).year == 2026


def test_to_paper_stub_year_none_when_pub_date_and_default_year_both_missing() -> None:
    """两者都缺 → 如实 None（不编造）；不传 default_year 的旧调用方式行为不变。"""
    entry = _bare_entry(pub_date=None)
    assert entry.to_paper_stub().year is None
    assert entry.to_paper_stub(default_year=None).year is None


@pytest.mark.parametrize(
    ("pub_date", "expected_year"),
    [
        ("2026-07-20", 2026),
        ("2020", 2020),
        (None, None),
        ("", None),
        ("garbage", None),
        ("20", None),  # 不足 4 位数字
    ],
)
def test_year_from_date(pub_date: str | None, expected_year: int | None) -> None:
    assert rss._year_from_date(pub_date) == expected_year


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
        fetch_year=2026,
    )
    assert entry.diff_id == "w1"


# --- ids_of：喂给 T4 subs.watermark.IdSetDiff 的保序去重 id 序列 -------------------------------


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
        fetch_year=2026,
    )


def test_ids_of_preserves_feed_order() -> None:
    """P1#2：`ids_of` 保序（feed 序即新→旧）——`IdSetDiff.advance()` 的截断前提。"""
    entries = (_entry("w3"), _entry("w2"), _entry("w1"))
    assert rss.ids_of(entries) == ("w3", "w2", "w1")


def test_ids_of_dedupes_repeated_ids() -> None:
    entries = (_entry("w1"), _entry("w2"), _entry("w1"))
    assert rss.ids_of(entries) == ("w1", "w2")


def test_ids_of_empty() -> None:
    assert rss.ids_of(()) == ()


def test_ids_of_return_type_is_tuple_not_set() -> None:
    """回归锁：曾是 `frozenset`（无序），P1 审查后改为保序 tuple——类型不得退回集合。"""
    result = rss.ids_of((_entry("w1"),))
    assert isinstance(result, tuple)


# --- 作者尾巴拆分启发式（含 P2#2 贪婪匹配回归）--------------------------------------------------


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


def test_split_title_authors_last_by_wins_when_title_contains_by_phrase() -> None:
    """P2#2：标题本身含 "-- by" 短语时，真正的作者分隔是**最后一个**（贪婪匹配）。

    非贪婪（旧实现）会在第一个 "-- by" 处误切，把 "Design: Evidence from Firms"
    这类本属标题的文字错当成作者串去拆分逗号。
    """
    title, authors = rss._split_title_authors(
        "The Trade-off -- by Design: Evidence from Firms -- by Alice Adams, Bob Brown"
    )
    assert title == "The Trade-off -- by Design: Evidence from Firms"
    assert authors == ("Alice Adams", "Bob Brown")


def test_split_title_authors_single_by_still_works_with_greedy_regex() -> None:
    """贪婪化不应回归单个 "-- by" 场景的行为（回归锁）。"""
    title, authors = rss._split_title_authors(
        "Synthetic Study of Board Composition and Leverage -- by Carol Cooper and Dave Diaz"
    )
    assert title == "Synthetic Study of Board Composition and Leverage"
    assert authors == ("Carol Cooper", "Dave Diaz")


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
