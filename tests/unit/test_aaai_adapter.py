"""AaaiOjsAdapter 主体单测（design/adapters/aaai-ojs.md §3-§6；T5）。

零真实网络：网络型方法（enumerate/fetch/healthcheck）经 `HttpClient(transport=
httpx.MockTransport(...))` 注入受控响应；纯逻辑方法（discover/resolve）无 http 依赖。
十一件套真实结构由 fixtures 加载（tests/fixtures/aaai/raw/）；adapter 主体逻辑
（volume_map 路由 / 全库回填 vs 当前届回看窗 / DOI-卷号 partition / view→download /
登录页嗅探）用 fixtures + 内联片段覆盖。
"""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from helpers import FakeFetchIO, make_aaai_venue
from helpers.aaai_fixtures import build_oai_page, fixture_bytes
from paper_crawler.adapters.aaai_ojs.adapter import AaaiOjsAdapter
from paper_crawler.errors import CrawlerError, ErrorClass
from paper_crawler.http import HttpClient
from paper_crawler.types import (
    AssetKind,
    AuthLevel,
    Capability,
    IssueRef,
    PaperStub,
    UrlStrategy,
    VenueSpec,
)

_UA = "PaperCrawler/test (personal research; mailto:test@example.com)"

Handler = Callable[[httpx.Request], httpx.Response]


def _adapter(handler: Handler) -> AaaiOjsAdapter:
    client = HttpClient(user_agent=_UA, transport=httpx.MockTransport(handler))
    return AaaiOjsAdapter(http=client)


def _issue(*, volume: str, year: int) -> IssueRef:
    return IssueRef(
        venue_id="aaai", volume=volume, number=None, year=year, label=f"AAAI-{year % 100:02d}"
    )


def _two_page_handler(request: httpx.Request) -> httpx.Response:
    """全库 2 页收割：resumptionToken 决定首页/续页（内容含 v40+v33 混合，供 partition）。"""
    if "resumptionToken" in request.url.params:
        return httpx.Response(200, content=fixture_bytes("02_oai_listrecords_page2.xml"))
    return httpx.Response(200, content=fixture_bytes("01_oai_listrecords_page1.xml"))


# --- 元数据 ------------------------------------------------------------------------------------


def test_adapter_metadata_matches_design_verdicts() -> None:
    a = AaaiOjsAdapter()
    assert a.adapter_id == "aaai_ojs"
    assert a.family == "open_access"
    assert a.capabilities == (
        Capability.DISCOVER | Capability.ENUMERATE | Capability.RESOLVE | Capability.FETCH
    )
    assert Capability.SEARCH not in a.capabilities
    assert a.auth_requirement == AuthLevel.NONE
    assert a.domains == ("ojs.aaai.org",)
    assert a.default_rate.requests_per_minute == 30.0
    assert a.default_rate.source_note != ""


def test_set_http_client_injection_overrides_lazy_env_build() -> None:
    adapter = AaaiOjsAdapter()
    injected = HttpClient(user_agent=_UA)
    adapter.set_http_client(injected)
    assert adapter._client() is injected


def test_lazy_client_builds_and_caches_when_http_none() -> None:
    a = AaaiOjsAdapter()
    client = a._client()
    assert isinstance(client, HttpClient)
    assert a._client() is client
    client.close()


# --- discover（零网络，届/年聚合）------------------------------------------------------------


def test_discover_yields_year_aggregated_issues_sorted() -> None:
    issues = list(AaaiOjsAdapter().discover_timeline(make_aaai_venue()))
    assert [(i.year, i.volume, i.label) for i in issues] == [
        (2019, "33", "AAAI-19"),
        (2026, "40", "AAAI-26"),
    ]
    first = issues[0]
    assert first.venue_id == "aaai"
    assert first.number is None  # OJS "No.M" 不建模为 IssueRef 维度（方案 B）
    assert first.pub_date is None
    assert first.paper_count_claimed is None


def test_discover_label_is_two_digit_year_brand_not_session_ordinal() -> None:
    # 站点品牌名 AAAI-YY（=2 位年份），刻意区别于"第 N 届"序号（survey §2.4）。
    issues = {i.year: i for i in AaaiOjsAdapter().discover_timeline(make_aaai_venue())}
    assert issues[2026].label == "AAAI-26"
    assert issues[2019].label == "AAAI-19"


def test_discover_since_filters_year_lower_bound() -> None:
    issues = list(AaaiOjsAdapter().discover_timeline(make_aaai_venue(), since="2026"))
    assert [i.year for i in issues] == [2026]


def test_discover_since_accepts_yyyy_prefix() -> None:
    issues = list(AaaiOjsAdapter().discover_timeline(make_aaai_venue(), since="2026-01"))
    assert [i.year for i in issues] == [2026]


def test_discover_missing_volume_map_is_config_error() -> None:
    venue = make_aaai_venue()
    venue.quirks.pop("volume_map")
    with pytest.raises(CrawlerError) as exc:
        list(AaaiOjsAdapter().discover_timeline(venue))
    assert exc.value.error_class is ErrorClass.CONFIG


def test_discover_illegal_volume_map_entry_is_config_error() -> None:
    with pytest.raises(CrawlerError) as exc:
        list(AaaiOjsAdapter().discover_timeline(make_aaai_venue(volume_map={"abc": "xyz"})))
    assert exc.value.error_class is ErrorClass.CONFIG


def test_discover_since_invalid_format_is_config_error() -> None:
    with pytest.raises(CrawlerError) as exc:
        list(AaaiOjsAdapter().discover_timeline(make_aaai_venue(), since="not-a-year"))
    assert exc.value.error_class is ErrorClass.CONFIG


# --- enumerate（OAI 收割 / DOI-卷号 partition / 回看窗）---------------------------------------


def test_enumerate_current_edition_partitions_to_its_volume_only() -> None:
    # v40（当前届）跨 2 页收割 → 只产 v40 记录（A/C/E 页1 + F 页2 = 4），过滤掉 v33。
    stubs = list(
        _adapter(_two_page_handler).enumerate_issue(
            make_aaai_venue(), _issue(volume="40", year=2026)
        )
    )
    dois = [dict(s.identifiers)["doi"] for s in stubs]
    assert dois == [
        "10.1609/aaai.v40i1.36958",
        "10.1609/aaai.v40i2.37001",
        "10.1609/aaai.v40i1.36959",
        "10.1609/aaai.v40i3.37050",
    ]
    assert all(d.startswith("10.1609/aaai.v40") for d in dois)


def test_enumerate_historical_edition_partitions_to_its_volume_only() -> None:
    # v33（历史届）从同一份全库收割里只产 v33 记录（D 页1 + G 页2 = 2）。
    stubs = list(
        _adapter(_two_page_handler).enumerate_issue(
            make_aaai_venue(), _issue(volume="33", year=2019)
        )
    )
    dois = [dict(s.identifiers)["doi"] for s in stubs]
    assert dois == ["10.1609/aaai.v33i01.3301695", "10.1609/aaai.v33i01.3301696"]


def test_enumerate_current_edition_uses_lookback_datestamp_window() -> None:
    seen: list[httpx.URL] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url)
        return _two_page_handler(request)

    list(_adapter(handler).enumerate_issue(make_aaai_venue(), _issue(volume="40", year=2026)))
    # 当前届（volume_map 最大年之卷）加固定回看窗 from=；OAI base 用 ojs_code=AAAI。
    assert str(seen[0]).startswith("https://ojs.aaai.org/index.php/AAAI/oai?")
    assert "from" in seen[0].params
    assert seen[0].params["metadataPrefix"] == "oai_dc"
    # 续页只带 verb + resumptionToken（OAI 规范互斥）。
    assert seen[1].params["resumptionToken"] == "AAAI-RESUME-PAGE2"
    assert "from" not in seen[1].params


def test_enumerate_historical_edition_has_no_datestamp_window() -> None:
    seen: list[httpx.URL] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url)
        return _two_page_handler(request)

    list(_adapter(handler).enumerate_issue(make_aaai_venue(), _issue(volume="33", year=2019)))
    # 历史届全库回填：无 from 日期窗（membership 判据是 DOI 卷号，非日期窗）。
    assert "from" not in seen[0].params


def test_enumerate_logs_tombstone_skip_debug_event(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[dict[str, object]] = []
    monkeypatch.setattr(
        "paper_crawler.adapters.aaai_ojs.adapter.log_event",
        lambda level, msg, **kw: events.append({"level": level, "msg": msg, **kw}),
    )
    list(
        _adapter(_two_page_handler).enumerate_issue(
            make_aaai_venue(), _issue(volume="40", year=2026)
        )
    )
    tombstone_events = [e for e in events if e["msg"] == "oai tombstones skipped"]
    assert len(tombstone_events) == 1
    ev = tombstone_events[0]
    assert ev["level"] == "DEBUG"
    assert ev["venue"] == "aaai"
    assert ev["stage"] == "enumerate"
    assert ev["bucket"] == "AAAI-26"
    assert ev["skipped_tombstones"] == 1


def test_enumerate_current_edition_logs_skipped_other_volume_debug_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # F4 审查追加（S1 台账 (c) 项）：当前窗查询按 datestamp 取数，天然混入其它卷记录
    # （v33），此前静默丢弃、零日志——现汇总计数经 obslog DEBUG 可观测（路由噪声，
    # 非真丢失：这些记录仍会被 v33 自己的收割路径覆盖）。
    events: list[dict[str, object]] = []
    monkeypatch.setattr(
        "paper_crawler.adapters.aaai_ojs.adapter.log_event",
        lambda level, msg, **kw: events.append({"level": level, "msg": msg, **kw}),
    )
    list(
        _adapter(_two_page_handler).enumerate_issue(
            make_aaai_venue(), _issue(volume="40", year=2026)
        )
    )
    expected_msg = "aaai current-window records skipped for non-matching volume"
    skip_events = [e for e in events if e["msg"] == expected_msg]
    assert len(skip_events) == 1
    ev = skip_events[0]
    assert ev["level"] == "DEBUG"
    assert ev["venue"] == "aaai"
    assert ev["stage"] == "enumerate"
    assert ev["bucket"] == "AAAI-26"
    assert ev["volume"] == "40"
    assert ev["skipped_other_volume"] == 2  # v33 记录：页1 D + 页2 G


def test_enumerate_norecordsmatch_completes_empty() -> None:
    handler: Handler = lambda request: httpx.Response(  # noqa: E731
        200, content=fixture_bytes("03_oai_norecordsmatch.xml")
    )
    stubs = list(
        _adapter(handler).enumerate_issue(make_aaai_venue(), _issue(volume="40", year=2026))
    )
    assert stubs == []


def test_enumerate_bad_resumption_token_is_transient() -> None:
    handler: Handler = lambda request: httpx.Response(  # noqa: E731
        200, content=fixture_bytes("04_oai_bad_resumption_token.xml")
    )
    with pytest.raises(CrawlerError) as exc:
        list(_adapter(handler).enumerate_issue(make_aaai_venue(), _issue(volume="40", year=2026)))
    assert exc.value.error_class is ErrorClass.TRANSIENT


def test_enumerate_bad_argument_is_config() -> None:
    handler: Handler = lambda request: httpx.Response(  # noqa: E731
        200, content=fixture_bytes("05_oai_bad_argument.xml")
    )
    with pytest.raises(CrawlerError) as exc:
        list(_adapter(handler).enumerate_issue(make_aaai_venue(), _issue(volume="40", year=2026)))
    assert exc.value.error_class is ErrorClass.CONFIG


def test_enumerate_malformed_xml_is_parse() -> None:
    handler: Handler = lambda request: httpx.Response(  # noqa: E731
        200, content=fixture_bytes("09_oai_malformed.xml")
    )
    with pytest.raises(CrawlerError) as exc:
        list(_adapter(handler).enumerate_issue(make_aaai_venue(), _issue(volume="40", year=2026)))
    assert exc.value.error_class is ErrorClass.PARSE


def test_enumerate_volume_none_is_config_error() -> None:
    handler: Handler = lambda request: httpx.Response(200, content=b"")  # noqa: E731
    bad = IssueRef(venue_id="aaai", volume=None, year=2026)
    with pytest.raises(CrawlerError) as exc:
        list(_adapter(handler).enumerate_issue(make_aaai_venue(), bad))
    assert exc.value.error_class is ErrorClass.CONFIG


def test_enumerate_volume_non_digit_is_config_error() -> None:
    handler: Handler = lambda request: httpx.Response(200, content=b"")  # noqa: E731
    bad = IssueRef(venue_id="aaai", volume="v40", year=2026)  # 带前缀，非裸数字
    with pytest.raises(CrawlerError) as exc:
        list(_adapter(handler).enumerate_issue(make_aaai_venue(), bad))
    assert exc.value.error_class is ErrorClass.CONFIG


def test_enumerate_unregistered_volume_is_config_error() -> None:
    handler: Handler = lambda request: httpx.Response(200, content=b"")  # noqa: E731
    unregistered = IssueRef(venue_id="aaai", volume="9999", year=2099)
    with pytest.raises(CrawlerError) as exc:
        list(_adapter(handler).enumerate_issue(make_aaai_venue(), unregistered))
    assert exc.value.error_class is ErrorClass.CONFIG
    assert "9999" in str(exc.value)


def test_enumerate_uses_ojs_code_from_quirks() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, content=fixture_bytes("03_oai_norecordsmatch.xml"))

    venue = make_aaai_venue(ojs_code="ICWSM", volume_map={2026: 40})
    list(_adapter(handler).enumerate_issue(venue, _issue(volume="40", year=2026)))
    assert seen[0].startswith("https://ojs.aaai.org/index.php/ICWSM/oai?")


def test_enumerate_ojs_code_defaults_to_venue_id_upper() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, content=fixture_bytes("03_oai_norecordsmatch.xml"))

    venue = make_aaai_venue(volume_map={2026: 40})
    venue.quirks.pop("ojs_code")  # 缺省 → venue.id.upper() = 'AAAI'
    list(_adapter(handler).enumerate_issue(venue, _issue(volume="40", year=2026)))
    assert seen[0].startswith("https://ojs.aaai.org/index.php/AAAI/oai?")


# --- 冷回填请求计数（审计 S1-P1：跨卷分区缓存，单趟全库 vs 逐卷重扫）--------------------------

# 3 历史届（v24/v33/v34）+ 1 当前届（v40）；每届 2 条记录，全库收割 3 页。
_COLD_VOLUME_MAP = {2010: 24, 2019: 33, 2020: 34, 2026: 40}
_COLD_HISTORICAL = ("24", "33", "34")
_COLD_PAGES: tuple[tuple[tuple[str, str], ...], ...] = (
    (("24", "2401"), ("40", "4001"), ("33", "3301")),
    (("34", "3401"), ("24", "2402"), ("40", "4002")),
    (("33", "3302"), ("34", "3402")),
)


def _cold_venue() -> VenueSpec:
    return make_aaai_venue(volume_map=dict(_COLD_VOLUME_MAP))


def _counting_backfill_handler(counter: list[httpx.URL]) -> Handler:
    """全库 3 页收割 handler，逐请求计数（`from=` 窗只有当前届才带，见断言）。"""

    def handler(request: httpx.Request) -> httpx.Response:
        counter.append(request.url)
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


def _dois(stubs: list[PaperStub]) -> list[str]:
    return [dict(s.identifiers)["doi"] for s in stubs]


def test_cold_backfill_single_pass_vs_per_volume_rescan_request_counts() -> None:
    """冷回填全部历史届的请求数：修复前 = 届数 × 全库页数；修复后 = 全库页数（单趟）。

    "修复前"基线用**每届一个新 adapter 实例**如实复现——无跨卷缓存可复用，正是审计
    S1-P1 描述的"其余历史卷各自触发全库无窗口重扫"路径。
    """
    venue = _cold_venue()
    pages = len(_COLD_PAGES)

    before: list[httpx.URL] = []
    before_dois = {}
    for volume in _COLD_HISTORICAL:
        adapter = _adapter(_counting_backfill_handler(before))  # 每届新实例 = 修复前语义
        issue = _issue(volume=volume, year=int(volume) + 1986)
        before_dois[volume] = _dois(list(adapter.enumerate_issue(venue, issue)))

    after: list[httpx.URL] = []
    shared = _adapter(_counting_backfill_handler(after))  # 同一实例跨卷复用单趟收割
    after_dois = {}
    for volume in _COLD_HISTORICAL:
        issue = _issue(volume=volume, year=int(volume) + 1986)
        after_dois[volume] = _dois(list(shared.enumerate_issue(venue, issue)))

    assert len(before) == pages * len(_COLD_HISTORICAL) == 9  # 逐卷重扫：3 届 × 3 页
    assert len(after) == pages == 3  # 单趟全库：3 页喂满 3 届
    assert len(before) == len(after) * len(_COLD_HISTORICAL)  # 降幅 = 历史届数（此处 3×）
    # 缓存保真：命中缓存产出的记录与真收割逐条相同（顺序含在内）。
    assert after_dois == before_dois
    assert after_dois["24"] == ["10.1609/aaai.v24i1.2401", "10.1609/aaai.v24i1.2402"]


def test_cold_backfill_cache_hit_issues_zero_requests() -> None:
    seen: list[httpx.URL] = []
    adapter = _adapter(_counting_backfill_handler(seen))
    venue = _cold_venue()

    list(adapter.enumerate_issue(venue, _issue(volume="24", year=2010)))
    after_first = len(seen)
    list(adapter.enumerate_issue(venue, _issue(volume="33", year=2019)))
    list(adapter.enumerate_issue(venue, _issue(volume="34", year=2020)))
    list(adapter.enumerate_issue(venue, _issue(volume="24", year=2010)))  # 同卷重取也走缓存
    assert after_first == len(_COLD_PAGES)
    assert len(seen) == after_first  # 后三次零请求


def test_cold_backfill_pass_carries_no_datestamp_window() -> None:
    seen: list[httpx.URL] = []
    adapter = _adapter(_counting_backfill_handler(seen))
    list(adapter.enumerate_issue(_cold_venue(), _issue(volume="24", year=2010)))
    # 历史届单趟全库：首页无 from 窗（datestamp≠发表日，窗口分区对历史届不可用）。
    assert "from" not in seen[0].params
    assert all("from" not in url.params for url in seen)


def test_current_edition_never_served_from_backfill_cache() -> None:
    """当前届恒走回看窗真请求——即便全库回填刚跑完（新鲜度优先，缓存只喂历史届）。"""
    seen: list[httpx.URL] = []
    adapter = _adapter(_counting_backfill_handler(seen))
    venue = _cold_venue()

    list(adapter.enumerate_issue(venue, _issue(volume="24", year=2010)))
    after_backfill = len(seen)
    stubs = list(adapter.enumerate_issue(venue, _issue(volume="40", year=2026)))

    assert len(seen) > after_backfill  # 真发了请求，没吃缓存
    assert "from" in seen[after_backfill].params  # 且带固定回看窗
    assert _dois(stubs) == ["10.1609/aaai.v40i1.4001", "10.1609/aaai.v40i1.4002"]


def test_backfill_cache_not_published_when_consumer_breaks_early() -> None:
    """调用方提前 break（未跑完收割）→ 不发布残缺分区，下次仍真收割。"""
    seen: list[httpx.URL] = []
    adapter = _adapter(_counting_backfill_handler(seen))
    venue = _cold_venue()

    next(iter(adapter.enumerate_issue(venue, _issue(volume="24", year=2010))))
    partial = len(seen)
    assert partial < len(_COLD_PAGES)  # 只翻到首页就撒手

    stubs = list(adapter.enumerate_issue(venue, _issue(volume="33", year=2019)))
    assert len(seen) == partial + len(_COLD_PAGES)  # 重新完整收割，而非用残缺缓存
    assert _dois(stubs) == ["10.1609/aaai.v33i1.3301", "10.1609/aaai.v33i1.3302"]


def test_backfill_cache_is_scoped_per_venue_and_oai_base() -> None:
    """缓存 key=(venue_id, oai_base)：换 `ojs_code`（姊妹刊）不复用上一实例的分区。"""
    seen: list[httpx.URL] = []
    adapter = _adapter(_counting_backfill_handler(seen))
    aaai = _cold_venue()
    icwsm = make_aaai_venue(volume_map=dict(_COLD_VOLUME_MAP), ojs_code="ICWSM")

    list(adapter.enumerate_issue(aaai, _issue(volume="24", year=2010)))
    first = len(seen)
    list(adapter.enumerate_issue(icwsm, _issue(volume="24", year=2010)))
    assert len(seen) == first + len(_COLD_PAGES)
    assert "/ICWSM/oai" in str(seen[-1])


def test_backfill_cache_miss_for_volume_registered_after_the_pass() -> None:
    """收割后才登记的历史卷不在旧分区表里 → 退回真收割，而非静默产空序列。"""
    seen: list[httpx.URL] = []
    adapter = _adapter(_counting_backfill_handler(seen))
    narrow = make_aaai_venue(volume_map={2019: 33, 2026: 40})
    widened = _cold_venue()

    list(adapter.enumerate_issue(narrow, _issue(volume="33", year=2019)))
    first = len(seen)
    stubs = list(adapter.enumerate_issue(widened, _issue(volume="24", year=2010)))
    assert len(seen) == first + len(_COLD_PAGES)
    assert _dois(stubs) == ["10.1609/aaai.v24i1.2401", "10.1609/aaai.v24i1.2402"]


def test_backfill_cache_disabled_loudly_when_record_cap_exceeded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """缓存记录数触顶 → WARN 事件 + 关缓存回退逐卷收割（响亮降级，不静默吃内存）。"""
    monkeypatch.setattr("paper_crawler.adapters.aaai_ojs.adapter._BACKFILL_CACHE_MAX_RECORDS", 1)
    events: list[dict[str, object]] = []
    monkeypatch.setattr(
        "paper_crawler.adapters.aaai_ojs.adapter.log_event",
        lambda level, msg, **kw: events.append({"level": level, "msg": msg, **kw}),
    )
    seen: list[httpx.URL] = []
    adapter = _adapter(_counting_backfill_handler(seen))
    venue = _cold_venue()

    stubs = list(adapter.enumerate_issue(venue, _issue(volume="24", year=2010)))
    assert _dois(stubs) == ["10.1609/aaai.v24i1.2401", "10.1609/aaai.v24i1.2402"]  # 产出不受损
    warns = [e for e in events if e["level"] == "WARN"]
    assert len(warns) == 1
    assert "cap exceeded" in str(warns[0]["msg"])

    first = len(seen)
    list(adapter.enumerate_issue(venue, _issue(volume="33", year=2019)))
    assert len(seen) == first + len(_COLD_PAGES)  # 缓存已关 → 回退重扫（只慢不错）


def test_backfill_records_outside_registered_volumes_are_dropped() -> None:
    """未注册卷号/非 AAAI DOI 不属任何届：既不产出也不进缓存（分区表只装已注册历史卷）。"""
    seen: list[httpx.URL] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url)
        return httpx.Response(200, content=build_oai_page((("24", "2401"), ("99", "9901"))))

    adapter = _adapter(handler)
    venue = _cold_venue()
    assert _dois(list(adapter.enumerate_issue(venue, _issue(volume="24", year=2010)))) == [
        "10.1609/aaai.v24i1.2401"
    ]
    assert adapter._backfill is not None
    assert set(adapter._backfill) == set(_COLD_HISTORICAL)  # v99 未入缓存


# 混合丢弃场景（F4 审查追加，S1 台账 (c) 项）：目标卷（24，产出）+ 未注册卷号（99，不在
# _cold_venue() 的 volume_map 里）+ 非 AAAI DOI 形态（volume=None，DOI 不含 "aaai.vNi"）。
# 后两类都命中 `_backfill_pages` 的真丢弃分支（非"进分区缓存"分支），也是本测试要钉死的。
_MIXED_DISCARD_PAGE = b"""<?xml version="1.0" encoding="UTF-8"?>
<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/"
         xmlns:oai_dc="http://www.openarchives.org/OAI/2.0/oai_dc/"
         xmlns:dc="http://purl.org/dc/elements/1.1/">
<ListRecords>
<record>
<header><identifier>oai:ojs.aaai.org:article/2401</identifier><datestamp>2010-03-17T09:00:00Z</datestamp></header>
<metadata><oai_dc:dc>
<dc:title>Target Volume Paper</dc:title>
<dc:creator>Synthetic, Author</dc:creator>
<dc:date>2010-03-17</dc:date>
<dc:identifier>https://ojs.aaai.org/index.php/AAAI/article/view/2401</dc:identifier>
<dc:identifier>10.1609/aaai.v24i1.2401</dc:identifier>
<dc:relation>https://ojs.aaai.org/index.php/AAAI/article/view/2401/1</dc:relation>
</oai_dc:dc></metadata>
</record>
<record>
<header><identifier>oai:ojs.aaai.org:article/9901</identifier><datestamp>2010-03-17T09:00:00Z</datestamp></header>
<metadata><oai_dc:dc>
<dc:title>Unregistered Volume Paper</dc:title>
<dc:creator>Synthetic, Author</dc:creator>
<dc:date>2010-03-17</dc:date>
<dc:identifier>https://ojs.aaai.org/index.php/AAAI/article/view/9901</dc:identifier>
<dc:identifier>10.1609/aaai.v99i1.9901</dc:identifier>
<dc:relation>https://ojs.aaai.org/index.php/AAAI/article/view/9901/1</dc:relation>
</oai_dc:dc></metadata>
</record>
<record>
<header><identifier>oai:ojs.aaai.org:article/5001</identifier><datestamp>2010-03-17T09:00:00Z</datestamp></header>
<metadata><oai_dc:dc>
<dc:title>Non-AAAI DOI Paper</dc:title>
<dc:creator>Synthetic, Author</dc:creator>
<dc:date>2010-03-17</dc:date>
<dc:identifier>https://ojs.aaai.org/index.php/AAAI/article/view/5001</dc:identifier>
<dc:identifier>10.9999/other-publisher.5001</dc:identifier>
<dc:relation>https://ojs.aaai.org/index.php/AAAI/article/view/5001/1</dc:relation>
</oai_dc:dc></metadata>
</record>
<resumptionToken/>
</ListRecords>
</OAI-PMH>
"""


def test_backfill_logs_info_event_for_unregistered_and_unparseable_volume_discards(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # F4 审查追加（S1 台账 (c) 项）：未注册卷号（99）与非 AAAI DOI（volume=None）都是
    # 真丢弃（此后不会被任何届的收割路径覆盖，区别于 _enumerate_pages 的路由噪声）；
    # 此前零日志、纯静默——现汇总计数经 obslog INFO 可观测。
    events: list[dict[str, object]] = []
    monkeypatch.setattr(
        "paper_crawler.adapters.aaai_ojs.adapter.log_event",
        lambda level, msg, **kw: events.append({"level": level, "msg": msg, **kw}),
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=_MIXED_DISCARD_PAGE)

    adapter = _adapter(handler)
    venue = _cold_venue()
    stubs = list(adapter.enumerate_issue(venue, _issue(volume="24", year=2010)))
    assert _dois(stubs) == ["10.1609/aaai.v24i1.2401"]  # 只产目标卷
    assert set(adapter._backfill) == set(_COLD_HISTORICAL)  # v99/None 均未入缓存

    discard_events = [
        e
        for e in events
        if e["msg"] == "aaai backfill records discarded for unregistered/unparseable volume"
    ]
    assert len(discard_events) == 1
    ev = discard_events[0]
    assert ev["level"] == "INFO"
    assert ev["venue"] == "aaai"
    assert ev["stage"] == "enumerate"
    assert ev["volume"] == "24"
    assert ev["discarded_unregistered_volume"] == 2  # v99 + 非 AAAI DOI(volume=None)


def test_empty_registered_edition_is_a_cache_hit_not_a_rescan() -> None:
    """全库里一条记录都没有的已注册历史届 = 空分区命中，**不得**因"空"而重扫全库。"""
    seen: list[httpx.URL] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url)
        return httpx.Response(200, content=build_oai_page((("24", "2401"),)))

    adapter = _adapter(handler)
    venue = _cold_venue()
    list(adapter.enumerate_issue(venue, _issue(volume="24", year=2010)))
    first = len(seen)
    assert list(adapter.enumerate_issue(venue, _issue(volume="33", year=2019))) == []
    assert len(seen) == first  # 空届零请求


# --- resolve（零网络，view→download 预换）----------------------------------------------------


def test_resolve_converts_view_to_download_url() -> None:
    paper = PaperStub(
        title="T",
        identifiers=(("doi", "10.1609/aaai.v40i1.36958"),),
        meta=(
            ("pdf_url", "https://ojs.aaai.org/index.php/AAAI/article/view/36958/40920"),
            ("ojs_article_id", "36958"),
        ),
    )
    plans = AaaiOjsAdapter().resolve_assets(make_aaai_venue(), paper)
    assert len(plans) == 1
    plan = plans[0]
    assert plan.kind is AssetKind.PDF
    assert plan.url == "https://ojs.aaai.org/index.php/AAAI/article/download/36958/40920"
    assert plan.url_strategy is UrlStrategy.DIRECT
    assert plan.auth_needed is AuthLevel.NONE
    assert plan.version is None


def test_resolve_without_pdf_url_meta_yields_zero_plans() -> None:
    paper = PaperStub(title="T", identifiers=(("doi", "10.1609/aaai.v40i1.1"),), meta=())
    assert AaaiOjsAdapter().resolve_assets(make_aaai_venue(), paper) == []


# --- fetch（流式，登录页/撤稿页首字节嗅探）---------------------------------------------------


def _pdf_plan_adapter(handler: Handler) -> tuple[AaaiOjsAdapter, object]:
    paper = PaperStub(
        title="T",
        identifiers=(("doi", "10.1609/aaai.v40i1.36958"),),
        meta=(("pdf_url", "https://ojs.aaai.org/index.php/AAAI/article/view/36958/40920"),),
    )
    plan = AaaiOjsAdapter().resolve_assets(make_aaai_venue(), paper)[0]
    return _adapter(handler), plan


def test_fetch_streams_pdf_bytes_ok() -> None:
    pdf = b"%PDF-1.7\n" + b"payload " * 64 + b"\n%%EOF\n"
    adapter, plan = _pdf_plan_adapter(lambda r: httpx.Response(200, content=pdf))
    io = FakeFetchIO()
    result = adapter.fetch_asset(plan, io)
    assert result.ok is True
    assert io.data == pdf


def test_fetch_http_404_is_gone_via_httpclient() -> None:
    adapter, plan = _pdf_plan_adapter(
        lambda r: httpx.Response(404, content=fixture_bytes("07_article_404.html"))
    )
    with pytest.raises(CrawlerError) as exc:
        adapter.fetch_asset(plan, FakeFetchIO())
    assert exc.value.error_class is ErrorClass.GONE


def test_fetch_login_page_html_is_no_entitlement() -> None:
    # 200 但回登录页（302→/login 落地，未发布/占位 galley）→ no_entitlement（★D）。
    adapter, plan = _pdf_plan_adapter(
        lambda r: httpx.Response(200, content=fixture_bytes("08_issue_login_redirect.html"))
    )
    with pytest.raises(CrawlerError) as exc:
        adapter.fetch_asset(plan, FakeFetchIO())
    assert exc.value.error_class is ErrorClass.NO_ENTITLEMENT
    assert exc.value.detail == "login-gated"


def test_fetch_login_page_reached_via_real_302_redirect_is_no_entitlement() -> None:
    # 忠实复现 302→/login：httpx follow_redirects 跟随，最终体是登录页 → no_entitlement。
    def handler(request: httpx.Request) -> httpx.Response:
        if "/login" in request.url.path:
            return httpx.Response(200, content=fixture_bytes("08_issue_login_redirect.html"))
        return httpx.Response(
            302, headers={"location": "https://ojs.aaai.org/index.php/AAAI/login?source=%2Fx"}
        )

    adapter, plan = _pdf_plan_adapter(handler)
    with pytest.raises(CrawlerError) as exc:
        adapter.fetch_asset(plan, FakeFetchIO())
    assert exc.value.error_class is ErrorClass.NO_ENTITLEMENT


def test_fetch_withdrawn_html_page_200_is_gone() -> None:
    # 200 但回非登录 HTML（撤稿/合并/不存在）→ gone（区别于登录页的 no_entitlement）。
    adapter, plan = _pdf_plan_adapter(
        lambda r: httpx.Response(200, content=fixture_bytes("07_article_404.html"))
    )
    with pytest.raises(CrawlerError) as exc:
        adapter.fetch_asset(plan, FakeFetchIO())
    assert exc.value.error_class is ErrorClass.GONE


def test_fetch_non_pdf_non_html_bytes_pass_through_to_pipeline() -> None:
    # 既非 PDF 又不形似 HTML（如截断二进制）→ 透传，交 pipeline %PDF 权威校验。
    blob = b"\x00\x01\x02 not a pdf not html " * 8
    adapter, plan = _pdf_plan_adapter(lambda r: httpx.Response(200, content=blob))
    io = FakeFetchIO()
    result = adapter.fetch_asset(plan, io)
    assert result.ok is True
    assert io.data == blob


# --- healthcheck（OAI Identify）--------------------------------------------------------------

_IDENTIFY_OK = (
    b'<?xml version="1.0"?><OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/"><Identify>'
    b"<repositoryName>Proceedings of the AAAI Conference on Artificial Intelligence</repositoryName>"  # noqa: E501
    b"<protocolVersion>2.0</protocolVersion></Identify></OAI-PMH>"
)


def test_healthcheck_ok_identify_repository_name_contains_aaai() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, content=_IDENTIFY_OK)

    report = _adapter(handler).healthcheck()
    assert report.healthy is True
    assert seen == ["https://ojs.aaai.org/index.php/AAAI/oai?verb=Identify"]


def test_healthcheck_repository_name_without_aaai_is_unhealthy() -> None:
    body = (
        b'<?xml version="1.0"?><OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/"><Identify>'
        b"<repositoryName>Some Other Repository</repositoryName></Identify></OAI-PMH>"
    )
    report = _adapter(lambda r: httpx.Response(200, content=body)).healthcheck()
    assert report.healthy is False
    assert "AAAI" in report.detail


def test_healthcheck_missing_identify_element_is_unhealthy() -> None:
    body = b'<?xml version="1.0"?><OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/"></OAI-PMH>'
    report = _adapter(lambda r: httpx.Response(200, content=body)).healthcheck()
    assert report.healthy is False


def test_healthcheck_malformed_identify_xml_is_unhealthy_not_raise() -> None:
    report = _adapter(lambda r: httpx.Response(200, content=b"<OAI-PMH><Identify>")).healthcheck()
    assert report.healthy is False
    assert "parse failed" in report.detail


def test_healthcheck_unreachable_returns_unhealthy_not_raise() -> None:
    report = _adapter(lambda r: httpx.Response(503, content=b"down")).healthcheck()
    assert report.healthy is False
    assert "unreachable" in report.detail


# --- UA 惰性自建 -------------------------------------------------------------------------------


def test_default_user_agent_uses_env_email(monkeypatch: pytest.MonkeyPatch) -> None:
    from paper_crawler.adapters.aaai_ojs import adapter as mod

    monkeypatch.setenv(mod._CONTACT_EMAIL_ENV, "real@lab.edu")
    ua = mod._default_user_agent()
    assert ua.startswith("PaperCrawler/")
    assert ua.endswith("(personal research; mailto:real@lab.edu)")


def test_default_user_agent_falls_back_to_placeholder(monkeypatch: pytest.MonkeyPatch) -> None:
    from paper_crawler.adapters.aaai_ojs import adapter as mod

    monkeypatch.delenv(mod._CONTACT_EMAIL_ENV, raising=False)
    ua = mod._default_user_agent()
    assert ua.endswith("(personal research; mailto:anonymous@paper-crawler.invalid)")
