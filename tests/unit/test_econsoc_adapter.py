"""econsoc/adapter.py 单测（MockTransport 零真实网络；design/adapters/econsoc.md §4/§5/§7）。

覆盖：discover（volume_map→IssueRef + since + ECMA 无 volume_map→CONFIG）；enumerate
（DOI 后缀刊别 membership + dc:date 年 partition + 当前刊回看窗 from= + 墓碑跳过）；resolve
（TE/QE 落地页抽 galley；ECMA 分段三分流 current/backfile/pre_doi + 乐观默认；CF 质询→
Challenged；无 galley→0 资产）；fetch（%PDF 透传 / HTML CF 质询→CHALLENGE / HTML 撤稿→GONE）；
healthcheck（Identify repositoryName）；元数据（capabilities/family/rate/domains）。
"""

from __future__ import annotations

import httpx
import pytest

from helpers import FakeFetchIO, make_econsoc_ecma_venue, make_econsoc_teqe_venue
from helpers.econsoc_fixtures import build_oai_page, fixture_bytes
from paper_crawler.adapters.econsoc.adapter import EconsocAdapter
from paper_crawler.errors import Challenged, CrawlerError, ErrorClass
from paper_crawler.http import HttpClient
from paper_crawler.types import AssetKind, AuthLevel, Capability, IssueRef, PaperStub, VenueSpec

_UA = "PaperCrawler/test (personal research; mailto:test@example.com)"
_PDF = b"%PDF-1.7\nsynthetic econsoc pdf\n%%EOF\n"


def _adapter(handler: object) -> EconsocAdapter:
    client = HttpClient(user_agent=_UA, transport=httpx.MockTransport(handler))  # type: ignore[arg-type]
    return EconsocAdapter(http=client)


def _te_issue(year: int, volume: str) -> IssueRef:
    return IssueRef(venue_id="te", volume=volume, number=None, year=year, label=f"te-{year}")


def _dois(stubs: list[PaperStub]) -> list[str]:
    return [dict(s.identifiers)["doi"] for s in stubs]


def _stub(doi: str, meta: tuple[tuple[str, str], ...] = ()) -> PaperStub:
    return PaperStub(title="X", identifiers=(("doi", doi),), meta=meta)


# --- 元数据 -----------------------------------------------------------------------------------


def test_adapter_metadata() -> None:
    a = EconsocAdapter()
    assert a.adapter_id == "econsoc"
    assert a.family == "open_access"
    assert a.capabilities == (
        Capability.DISCOVER | Capability.ENUMERATE | Capability.RESOLVE | Capability.FETCH
    )
    assert a.auth_requirement is AuthLevel.NONE
    assert a.default_rate.source_note  # 非空出处（契约要求）
    assert a.default_rate.requests_per_minute <= 20.0  # ≥3s 硬下限（20rpm=3s）
    assert a.domains[0] == "www.econometricsociety.org"
    assert "econtheory.org" in a.domains  # OAI 域一并声明（route_for alias 到主域桶）
    assert a.resolve_offline is False  # resolve 网络绑定（GET 落地页抽 galley）


# --- discover -------------------------------------------------------------------------------


def test_discover_te_yields_per_year_issues() -> None:
    issues = list(EconsocAdapter().discover_timeline(make_econsoc_teqe_venue("te")))
    assert {(i.year, i.volume) for i in issues} == {(2006, "1"), (2024, "20")}
    for i in issues:
        assert i.venue_id == "te"
        assert i.label == f"te-{i.year}"


def test_discover_since_narrows_start() -> None:
    issues = list(EconsocAdapter().discover_timeline(make_econsoc_teqe_venue("te"), since="2020"))
    assert {i.year for i in issues} == {2024}


def test_discover_ecma_without_volume_map_is_config_error() -> None:
    # ECMA venue 无 volume_map（枚举委 crossref）→ 误调 discover 响亮停机（CONFIG）。
    with pytest.raises(CrawlerError) as exc:
        list(EconsocAdapter().discover_timeline(make_econsoc_ecma_venue()))
    assert exc.value.error_class is ErrorClass.CONFIG


# --- enumerate（DOI 后缀 membership + dc:date 年 partition + 回看窗）--------------------------


def _oai_handler(seen: list[str] | None = None) -> object:
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(str(request.url))
        if "resumptionToken" in request.url.params:
            return httpx.Response(200, content=fixture_bytes("02_oai_listrecords_page2.xml"))
        return httpx.Response(200, content=fixture_bytes("01_oai_listrecords_page1.xml"))

    return handler


def test_enumerate_current_year_keeps_only_te_2024_records() -> None:
    seen: list[str] = []
    papers = list(
        _adapter(_oai_handler(seen)).enumerate_issue(
            make_econsoc_teqe_venue("te"), _te_issue(2024, "20")
        )
    )
    # membership=te（QE 丢）+ partition=2024（2006 丢）+ 墓碑跳过 → te6021/te6022/te6023。
    assert {dict(p.identifiers)["doi"] for p in papers} == {
        "10.3982/te6021",
        "10.3982/te6022",
        "10.3982/te6023",
    }
    # 当前年首拉（新 adapter 实例、缓存无该年分区）→ 无窗全量收割（T15 修复，闭合"今年
    # 早发论文首拉漏收"缺口）；不再像旧行为那样带 from= 回看窗。
    assert all("from=" not in u for u in seen)


def test_enumerate_historical_year_keeps_only_te_2006_records() -> None:
    seen: list[str] = []
    papers = list(
        _adapter(_oai_handler(seen)).enumerate_issue(
            make_econsoc_teqe_venue("te"), _te_issue(2006, "1")
        )
    )
    assert {dict(p.identifiers)["doi"] for p in papers} == {"10.3982/te0001", "10.3982/te0002"}
    # 历史刊（非最大年）→ 无 from= 窗，全量收割。
    assert all("from=" not in u for u in seen)


# --- 当前年首拉完整性修复可观测性（T15/检查单#6，与 aaai_ojs F3 结构同构）----------------------
#
# 旧行为（本卡修复前）：当前年恒加 from=<今日-30d> 回看窗，首次收割该刊/年时窗口外
# （今年早些时候发表）的论文会被漏收，只经 obslog INFO 提示、不实际闭合缺口。新行为
# （本卡）：当前年首拉（缓存无该年分区）改走无窗全量收割——直接闭合缺口而非仅提示；
# 全量收割顺带把全部已注册年份（含当前年自身）partition 缓存，本 run 内再问到已缓存
# 年份（历史或当前）→ 零请求命中缓存（结构移植自 aaai_ojs `_cached_partition`/
# `_backfill_pages`，键改用年份）。级别仍为 INFO 非 WARNING（沿 F4 审查修正）：这是
# 首拉路径的常态表现，非偶发异常。


def test_enumerate_current_year_first_harvest_logs_full_harvest_info(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[dict[str, object]] = []
    monkeypatch.setattr(
        "paper_crawler.adapters.econsoc.adapter.log_event",
        lambda level, msg, **kw: events.append({"level": level, "msg": msg, **kw}),
    )
    list(
        _adapter(_oai_handler()).enumerate_issue(
            make_econsoc_teqe_venue("te"), _te_issue(2024, "20")
        )
    )
    infos = [e for e in events if "first harvest this run" in str(e["msg"])]
    assert len(infos) == 1
    assert infos[0]["level"] == "INFO"
    assert infos[0]["venue"] == "te"
    assert infos[0]["year"] == 2024


def test_enumerate_historical_year_does_not_log_first_harvest_info(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[dict[str, object]] = []
    monkeypatch.setattr(
        "paper_crawler.adapters.econsoc.adapter.log_event",
        lambda level, msg, **kw: events.append({"level": level, "msg": msg, **kw}),
    )
    list(
        _adapter(_oai_handler()).enumerate_issue(
            make_econsoc_teqe_venue("te"), _te_issue(2006, "1")
        )
    )
    # 历史年首拉一样触发全量收割（无窗，同结构），但**不**打"first harvest"提示——那条
    # 提示专指"当前年"分支（controller 裁决②的完整性叙事只对当前年有意义：历史年从
    # 来就是全量收割，没有"漏收窗口外论文"这个缺口可言）。
    assert [e for e in events if "first harvest this run" in str(e["msg"])] == []


def test_enumerate_current_year_cache_hit_returns_cached_without_new_request() -> None:
    # 结构核心：同实例内，任一年份的首趟全量收割已把当前年一并 partition 缓存——本 run
    # 内再问到当前年 → 零请求命中缓存（不再是"当前年恒发请求"的旧结构）。
    seen: list[str] = []
    adapter = _adapter(_oai_handler(seen))
    venue = make_econsoc_teqe_venue("te")
    list(adapter.enumerate_issue(venue, _te_issue(2006, "1")))  # 历史年首拉：全量收割
    after_first = len(seen)
    papers = list(adapter.enumerate_issue(venue, _te_issue(2024, "20")))  # 当前年：缓存命中
    assert len(seen) == after_first  # 零新请求
    assert {dict(p.identifiers)["doi"] for p in papers} == {
        "10.3982/te6021",
        "10.3982/te6022",
        "10.3982/te6023",
    }


def test_enumerate_paper_stub_carries_meta() -> None:
    papers = list(
        _adapter(_oai_handler()).enumerate_issue(
            make_econsoc_teqe_venue("te"), _te_issue(2024, "20")
        )
    )
    lead = next(p for p in papers if dict(p.identifiers)["doi"] == "10.3982/te6021")
    assert lead.year == 2024
    assert lead.authors == ("Alpha, Ann", "Beta, Bob")
    meta = dict(lead.meta)
    assert meta["pdf_url"].endswith("6021.PDF")
    assert "Vol 19, No 2" in meta["ojs_source"]


def test_enumerate_unregistered_year_is_config() -> None:
    with pytest.raises(CrawlerError) as exc:
        list(
            _adapter(_oai_handler()).enumerate_issue(
                make_econsoc_teqe_venue("te"), _te_issue(2099, "99")
            )
        )
    assert exc.value.error_class is ErrorClass.CONFIG


def test_enumerate_qe_endpoint_membership_filter() -> None:
    # QE venue（ojs_code=qe）对同一页 fixture 只保留 qe 后缀记录（其余 te 记录丢弃）。
    papers = list(
        _adapter(_oai_handler()).enumerate_issue(
            make_econsoc_teqe_venue("qe"), IssueRef(venue_id="qe", volume="15", year=2024)
        )
    )
    assert {dict(p.identifiers)["doi"] for p in papers} == {"10.3982/qe2297"}


# --- F2：dc:date 缺失/畸形记录的年 partition 可观测（审查修复）--------------------------------

_MISSING_DATE_PAGE = (
    b'<?xml version="1.0"?><OAI-PMH '
    b'xmlns="http://www.openarchives.org/OAI/2.0/" '
    b'xmlns:oai_dc="http://www.openarchives.org/OAI/2.0/oai_dc/" '
    b'xmlns:dc="http://purl.org/dc/elements/1.1/"><ListRecords>'
    # ① 有 dc:date（2024）的 TE 记录 → 归 2024。
    b"<record><header><identifier>oai:x:1</identifier></header><metadata><oai_dc:dc>"
    b"<dc:title>Dated TE Record</dc:title><dc:date>2024-05-02</dc:date>"
    b"<dc:identifier>https://econtheory.org/ojs/index.php/te/article/view/6021</dc:identifier>"
    b"<dc:identifier>10.3982/TE6021</dc:identifier></oai_dc:dc></metadata></record>"
    # ② 缺 dc:date 的 TE 记录 → 无法归年（skipped_missing_date），不误归 2024。
    b"<record><header><identifier>oai:x:2</identifier></header><metadata><oai_dc:dc>"
    b"<dc:title>Undated TE Record</dc:title>"
    b"<dc:identifier>https://econtheory.org/ojs/index.php/te/article/view/6099</dc:identifier>"
    b"<dc:identifier>10.3982/TE6099</dc:identifier></oai_dc:dc></metadata></record>"
    b"<resumptionToken/></ListRecords></OAI-PMH>"
)


def test_enumerate_missing_dc_date_counted_and_dropped(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[dict[str, object]] = []
    monkeypatch.setattr(
        "paper_crawler.adapters.econsoc.adapter.log_event",
        lambda level, msg, **kw: events.append({"msg": msg, **kw}),
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=_MISSING_DATE_PAGE)

    papers = list(
        _adapter(handler).enumerate_issue(make_econsoc_teqe_venue("te"), _te_issue(2024, "20"))
    )
    # 缺 date 记录不误归 2024（被丢弃）；有 date 的 2024 记录保留。
    assert {dict(p.identifiers)["doi"] for p in papers} == {"10.3982/te6021"}
    # 可观测：skipped_missing_date 计数经 obslog 暴露（对齐墓碑先例）。
    missing = [e for e in events if str(e["msg"]).startswith("oai records skipped for missing")]
    assert len(missing) == 1
    assert missing[0]["skipped_missing_date"] == 1


# --- 跨年分区缓存 + 当前年首拉全量修复（T15/检查单#6：结构移植自 aaai_ojs F3，键改年份）--------
#
# 3 历史年（2006/2010/2020）+ 1 当前年（2024=volume_map 最大年）；每年 2 条记录，全量
# 收割 3 页。与 aaai_ojs 的关键差异（controller 裁决②）：当前年**纳入**可缓存年份集合
# （aaai_ojs 排除当前届），使任一年份的首趟全量收割都顺带缓存当前年——见
# `test_current_year_served_from_backfill_cache_after_historical_pass`。

_COLD_VOLUME_MAP = {2006: 1, 2010: 5, 2020: 15, 2024: 20}
_COLD_HISTORICAL = (2006, 2010, 2020)
_COLD_PAGES: tuple[tuple[tuple[int, str], ...], ...] = (
    ((2006, "0601"), (2024, "2401"), (2010, "1001")),
    ((2020, "2001"), (2006, "0602"), (2024, "2402")),
    ((2010, "1002"), (2020, "2002")),
)


def _cold_venue() -> VenueSpec:
    return make_econsoc_teqe_venue("te", volume_map=dict(_COLD_VOLUME_MAP))


def _counting_backfill_handler(counter: list[httpx.URL]) -> object:
    """全量 3 页收割 handler，逐请求计数（冷回填全量收割不带 from= 回看窗）。"""

    def handler(request: httpx.Request) -> httpx.Response:
        counter.append(request.url)
        token = request.url.params.get("resumptionToken")
        index = int(token.rsplit("-", 1)[-1]) if token else 0
        is_last = index == len(_COLD_PAGES) - 1
        return httpx.Response(
            200,
            content=build_oai_page(
                _COLD_PAGES[index],
                journal="te",
                resumption_token=None if is_last else f"COLD-{index + 1}",
            ),
        )

    return handler


def test_cold_backfill_single_pass_vs_per_year_rescan_request_counts() -> None:
    """冷回填全部历史年的请求数：修复前 = 年数 × 全量页数；修复后 = 全量页数（单趟）。

    "修复前"基线用**每年一个新 adapter 实例**如实复现——无跨年缓存可复用，正是本卡
    结构移植所修的"其余历史年各自触发全量无窗口重扫"路径（结构移植自 aaai_ojs F3
    `_cached_partition`/`_backfill_pages`，分区键从 DOI 卷号改 dc:date 年）。
    """
    venue = _cold_venue()
    pages = len(_COLD_PAGES)

    before: list[httpx.URL] = []
    before_dois: dict[int, list[str]] = {}
    for year in _COLD_HISTORICAL:
        adapter = _adapter(_counting_backfill_handler(before))  # 每年新实例 = 修复前语义
        issue = _te_issue(year, str(year))
        before_dois[year] = _dois(list(adapter.enumerate_issue(venue, issue)))

    after: list[httpx.URL] = []
    shared = _adapter(_counting_backfill_handler(after))  # 同一实例跨年复用单趟收割
    after_dois: dict[int, list[str]] = {}
    for year in _COLD_HISTORICAL:
        issue = _te_issue(year, str(year))
        after_dois[year] = _dois(list(shared.enumerate_issue(venue, issue)))

    assert len(before) == pages * len(_COLD_HISTORICAL) == 9  # 逐年重扫：3 年 × 3 页
    assert len(after) == pages == 3  # 单趟全量：3 页喂满 3 年
    assert len(before) == len(after) * len(_COLD_HISTORICAL)  # 降幅 = 历史年数（此处 3×）
    assert after_dois == before_dois  # 缓存保真：命中缓存产出与真收割逐条相同
    assert after_dois[2006] == ["10.3982/te0601", "10.3982/te0602"]


def test_cold_backfill_cache_hit_issues_zero_requests() -> None:
    seen: list[httpx.URL] = []
    adapter = _adapter(_counting_backfill_handler(seen))
    venue = _cold_venue()

    list(adapter.enumerate_issue(venue, _te_issue(2006, "1")))
    after_first = len(seen)
    list(adapter.enumerate_issue(venue, _te_issue(2010, "5")))
    list(adapter.enumerate_issue(venue, _te_issue(2020, "15")))
    list(adapter.enumerate_issue(venue, _te_issue(2006, "1")))  # 同年重取也走缓存
    assert after_first == len(_COLD_PAGES)
    assert len(seen) == after_first  # 后三次零请求


def test_cold_backfill_pass_carries_no_datestamp_window() -> None:
    seen: list[httpx.URL] = []
    adapter = _adapter(_counting_backfill_handler(seen))
    list(adapter.enumerate_issue(_cold_venue(), _te_issue(2006, "1")))
    # 历史年首拉全量收割：首页无 from 窗（datestamp≠发表日，窗口分区对历史年不可用）。
    assert "from" not in seen[0].params
    assert all("from" not in url.params for url in seen)


def test_current_year_first_harvest_uses_full_windowless_harvest() -> None:
    """核心修复②：新实例直接问当前年(2024，缓存未预热)→ 无窗全量收割，非回看窗。"""
    seen: list[httpx.URL] = []
    adapter = _adapter(_counting_backfill_handler(seen))
    venue = _cold_venue()

    stubs = list(adapter.enumerate_issue(venue, _te_issue(2024, "20")))

    assert len(seen) == len(_COLD_PAGES)  # 全量收割：喂满全部页（非仅一页回看窗）
    assert all("from" not in url.params for url in seen)  # 无回看窗
    assert _dois(stubs) == ["10.3982/te2401", "10.3982/te2402"]


def test_current_year_served_from_backfill_cache_after_historical_pass() -> None:
    """结构核心①②合流：历史年首趟全量收割顺带缓存当前年——同 run 内当前年零请求命中。

    与 aaai_ojs 相反（design/adapters/aaai-ojs.md §4 护栏①"当前届永不读写缓存"）：
    econsoc 当前年**纳入**可缓存集合，令首趟全量收割即完整覆盖当前年，不必等它
    滚入历史才补全（闭合"当前年首拉漏收窗口外早发论文"缺口，controller 裁决②）。
    """
    seen: list[httpx.URL] = []
    adapter = _adapter(_counting_backfill_handler(seen))
    venue = _cold_venue()

    list(adapter.enumerate_issue(venue, _te_issue(2006, "1")))
    after_backfill = len(seen)
    stubs = list(adapter.enumerate_issue(venue, _te_issue(2024, "20")))

    assert len(seen) == after_backfill  # 零新请求——当前年缓存已由历史年首趟建立
    assert _dois(stubs) == ["10.3982/te2401", "10.3982/te2402"]


def test_backfill_cache_not_published_when_consumer_breaks_early() -> None:
    """调用方提前 break（未跑完收割）→ 不发布残缺分区，下次仍真收割。"""
    seen: list[httpx.URL] = []
    adapter = _adapter(_counting_backfill_handler(seen))
    venue = _cold_venue()

    next(iter(adapter.enumerate_issue(venue, _te_issue(2006, "1"))))
    partial = len(seen)
    assert partial < len(_COLD_PAGES)  # 只翻到首页就撒手

    stubs = list(adapter.enumerate_issue(venue, _te_issue(2010, "5")))
    assert len(seen) == partial + len(_COLD_PAGES)  # 重新完整收割，而非用残缺缓存
    assert _dois(stubs) == ["10.3982/te1001", "10.3982/te1002"]


def test_backfill_cache_is_scoped_per_venue_and_oai_base() -> None:
    """缓存 key=(venue_id, oai_base)：换 ojs_code（姊妹刊）不复用上一实例的分区。"""
    seen: list[httpx.URL] = []
    adapter = _adapter(_counting_backfill_handler(seen))
    te = _cold_venue()
    qe = make_econsoc_teqe_venue("qe", volume_map=dict(_COLD_VOLUME_MAP))

    list(adapter.enumerate_issue(te, _te_issue(2006, "1")))
    first = len(seen)
    list(adapter.enumerate_issue(qe, IssueRef(venue_id="qe", volume="1", year=2006)))
    assert len(seen) == first + len(_COLD_PAGES)
    assert "/qe/oai" in str(seen[-1])


def test_backfill_cache_miss_for_year_registered_after_the_pass() -> None:
    """收割后才登记的历史年不在旧分区表里 → 退回真收割，而非静默产空序列。"""
    seen: list[httpx.URL] = []
    adapter = _adapter(_counting_backfill_handler(seen))
    narrow = make_econsoc_teqe_venue("te", volume_map={2020: 15, 2024: 20})
    widened = _cold_venue()

    list(adapter.enumerate_issue(narrow, _te_issue(2020, "15")))
    first = len(seen)
    stubs = list(adapter.enumerate_issue(widened, _te_issue(2006, "1")))
    assert len(seen) == first + len(_COLD_PAGES)
    assert _dois(stubs) == ["10.3982/te0601", "10.3982/te0602"]


def test_backfill_cache_disabled_loudly_when_record_cap_exceeded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """缓存记录数触顶 → WARN 事件 + 关缓存回退逐年收割（响亮降级，不静默吃内存）。"""
    monkeypatch.setattr("paper_crawler.adapters.econsoc.adapter._BACKFILL_CACHE_MAX_RECORDS", 1)
    events: list[dict[str, object]] = []
    monkeypatch.setattr(
        "paper_crawler.adapters.econsoc.adapter.log_event",
        lambda level, msg, **kw: events.append({"level": level, "msg": msg, **kw}),
    )
    seen: list[httpx.URL] = []
    adapter = _adapter(_counting_backfill_handler(seen))
    venue = _cold_venue()

    stubs = list(adapter.enumerate_issue(venue, _te_issue(2006, "1")))
    assert _dois(stubs) == ["10.3982/te0601", "10.3982/te0602"]  # 产出不受损
    warns = [e for e in events if e["level"] == "WARN"]
    assert len(warns) == 1
    assert "cap exceeded" in str(warns[0]["msg"])

    first = len(seen)
    list(adapter.enumerate_issue(venue, _te_issue(2010, "5")))
    assert len(seen) == first + len(_COLD_PAGES)  # 缓存已关 → 回退重扫（只慢不错）


def test_backfill_records_outside_registered_years_are_dropped() -> None:
    """未注册年份不属任何年：既不产出也不进缓存（分区表只装已注册年份）。"""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=build_oai_page(((2006, "0601"), (2099, "9901")), journal="te")
        )

    adapter = _adapter(handler)
    venue = _cold_venue()
    assert _dois(list(adapter.enumerate_issue(venue, _te_issue(2006, "1")))) == ["10.3982/te0601"]
    assert adapter._backfill is not None
    assert set(adapter._backfill) == set(_COLD_VOLUME_MAP)  # 2099 未入缓存


_MIXED_DISCARD_PAGE = b"""<?xml version="1.0" encoding="UTF-8"?>
<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/"
         xmlns:oai_dc="http://www.openarchives.org/OAI/2.0/oai_dc/"
         xmlns:dc="http://purl.org/dc/elements/1.1/">
<ListRecords>
<record>
<header><identifier>oai:econtheory.org:article/601</identifier>
<datestamp>2006-03-17T09:00:00Z</datestamp></header>
<metadata><oai_dc:dc>
<dc:title>Target Year Paper</dc:title>
<dc:creator>Synthetic, Author</dc:creator>
<dc:date>2006-03-17</dc:date>
<dc:identifier>https://econtheory.org/ojs/index.php/te/article/view/601</dc:identifier>
<dc:identifier>10.3982/te0601</dc:identifier>
<dc:relation>https://www.econometricsociety.org/publications/te/2006/03/17/x/file/601.PDF\
</dc:relation>
</oai_dc:dc></metadata>
</record>
<record>
<header><identifier>oai:econtheory.org:article/9901</identifier>
<datestamp>2099-03-17T09:00:00Z</datestamp></header>
<metadata><oai_dc:dc>
<dc:title>Unregistered Year Paper</dc:title>
<dc:creator>Synthetic, Author</dc:creator>
<dc:date>2099-03-17</dc:date>
<dc:identifier>https://econtheory.org/ojs/index.php/te/article/view/9901</dc:identifier>
<dc:identifier>10.3982/te9901</dc:identifier>
<dc:relation>https://www.econometricsociety.org/publications/te/2099/03/17/x/file/9901.PDF\
</dc:relation>
</oai_dc:dc></metadata>
</record>
<record>
<header><identifier>oai:econtheory.org:article/5001</identifier>
<datestamp>2006-03-17T09:00:00Z</datestamp></header>
<metadata><oai_dc:dc>
<dc:title>Missing Date Paper</dc:title>
<dc:creator>Synthetic, Author</dc:creator>
<dc:identifier>https://econtheory.org/ojs/index.php/te/article/view/5001</dc:identifier>
<dc:identifier>10.3982/te5001</dc:identifier>
<dc:relation>https://www.econometricsociety.org/publications/te/2006/03/17/x/file/5001.PDF\
</dc:relation>
</oai_dc:dc></metadata>
</record>
<resumptionToken/>
</ListRecords>
</OAI-PMH>
"""


def test_backfill_logs_info_event_for_unregistered_and_unparseable_year_discards(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 未注册年份（2099）与 dc:date 缺失（5001）都是真丢弃，但走两条不同既有计数器：
    # 前者是本卡新引入的 discarded_unregistered_year（INFO，同构 aaai F4 审查）；后者
    # 沿用既有 skipped_missing_date（DEBUG，F2 审查修复，语义不变）。
    events: list[dict[str, object]] = []
    monkeypatch.setattr(
        "paper_crawler.adapters.econsoc.adapter.log_event",
        lambda level, msg, **kw: events.append({"level": level, "msg": msg, **kw}),
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=_MIXED_DISCARD_PAGE)

    adapter = _adapter(handler)
    venue = _cold_venue()
    stubs = list(adapter.enumerate_issue(venue, _te_issue(2006, "1")))
    assert _dois(stubs) == ["10.3982/te0601"]  # 只产目标年
    assert adapter._backfill is not None
    assert set(adapter._backfill) == set(_COLD_VOLUME_MAP)  # 2099/缺 date 均未入缓存

    discard_events = [
        e
        for e in events
        if e["msg"] == "econsoc backfill records discarded for unregistered/unparseable year"
    ]
    assert len(discard_events) == 1
    ev = discard_events[0]
    assert ev["level"] == "INFO"
    assert ev["venue"] == "te"
    assert ev["year"] == 2006
    assert ev["discarded_unregistered_year"] == 1  # 只有 2099；缺 date 的 5001 走另一计数器

    missing_events = [
        e for e in events if str(e["msg"]).startswith("oai records skipped for missing")
    ]
    assert len(missing_events) == 1
    assert missing_events[0]["skipped_missing_date"] == 1


def test_empty_registered_year_is_a_cache_hit_not_a_rescan() -> None:
    """全库里一条记录都没有的已注册历史年 = 空分区命中，**不得**因"空"而重扫全库。"""
    seen: list[httpx.URL] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url)
        return httpx.Response(200, content=build_oai_page(((2006, "0601"),), journal="te"))

    adapter = _adapter(handler)
    venue = _cold_venue()
    list(adapter.enumerate_issue(venue, _te_issue(2006, "1")))
    first = len(seen)
    assert list(adapter.enumerate_issue(venue, _te_issue(2010, "5"))) == []
    assert len(seen) == first  # 空年零请求


# --- resolve（TE/QE 落地页抽 galley）---------------------------------------------------------


def _landing_handler(landing_body: bytes) -> object:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=landing_body)

    return handler


def test_resolve_te_gets_landing_and_extracts_galley() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, content=fixture_bytes("03_landing_with_galley.html"))

    plans = _adapter(handler).resolve_assets(make_econsoc_teqe_venue("te"), _stub("10.3982/te6021"))
    assert len(plans) == 1
    assert plans[0].kind is AssetKind.PDF
    assert plans[0].auth_needed is AuthLevel.NONE
    assert plans[0].url.endswith("/file/6021.PDF")
    assert httpx.URL(plans[0].url).host == "www.econometricsociety.org"
    # resolve 网络绑定：GET 了 econometricsociety.org/doi/{DOI} 落地页。
    assert any("/doi/10.3982/te6021" in u for u in seen)


def test_resolve_no_galley_returns_zero_assets() -> None:
    body = b"<html><body><p>Subscription required. No galley link here.</p></body></html>"
    plans = _adapter(_landing_handler(body)).resolve_assets(
        make_econsoc_teqe_venue("te"), _stub("10.3982/te6021")
    )
    assert plans == []


def test_resolve_cf_challenge_landing_raises_challenged() -> None:
    handler = _landing_handler(fixture_bytes("04_cf_challenge.html"))
    with pytest.raises(Challenged) as exc:
        _adapter(handler).resolve_assets(make_econsoc_teqe_venue("te"), _stub("10.3982/te6021"))
    assert exc.value.error_class is ErrorClass.CHALLENGE


def test_resolve_missing_doi_is_config() -> None:
    paper = PaperStub(title="X", identifiers=(("arxiv", "2401.00001"),))
    with pytest.raises(CrawlerError) as exc:
        _adapter(_landing_handler(b"")).resolve_assets(make_econsoc_teqe_venue("te"), paper)
    assert exc.value.error_class is ErrorClass.CONFIG


# --- resolve ECMA 分段路由（三分流 + 乐观默认）----------------------------------------------


def test_resolve_ecma_current_domain_fetches_galley() -> None:
    handler = _landing_handler(fixture_bytes("03_landing_with_galley.html"))
    plans = _adapter(handler).resolve_assets(
        make_econsoc_ecma_venue(),
        _stub("10.3982/ecta23709", meta=(("primary_url_domain", "www.econometricsociety.org"),)),
    )
    assert len(plans) == 1 and plans[0].kind is AssetKind.PDF


def test_resolve_ecma_optimistic_current_without_domain() -> None:
    # 无 primary_url_domain（crossref 未登记）→ 乐观归当前段 → 走落地页抽 galley。
    handler = _landing_handler(fixture_bytes("03_landing_with_galley.html"))
    plans = _adapter(handler).resolve_assets(make_econsoc_ecma_venue(), _stub("10.3982/ecta23709"))
    assert len(plans) == 1


def test_resolve_ecma_backfile_wiley_domain_is_no_entitlement() -> None:
    # 过刊段（doi.wiley.com）→ NO_ENTITLEMENT（跨 adapter handoff defer，D-028）；零网络。
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, content=b"should-not-be-called")

    with pytest.raises(CrawlerError) as exc:
        _adapter(handler).resolve_assets(
            make_econsoc_ecma_venue(),
            _stub("10.3982/ecta12058", meta=(("primary_url_domain", "doi.wiley.com"),)),
        )
    assert exc.value.error_class is ErrorClass.NO_ENTITLEMENT
    assert calls == []  # 分段前置判定，未触网


def test_resolve_ecma_pre_doi_jstor_is_zero_assets() -> None:
    # pre-DOI 段（10.2307/JSTOR）→ 界外零资产 skip（非错误）；零网络。
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, content=b"should-not-be-called")

    plans = _adapter(handler).resolve_assets(make_econsoc_ecma_venue(), _stub("10.2307/1912227"))
    assert plans == []
    assert calls == []


# --- F1：ECMA 当前段落地 404/410 终态诚实化（GONE→no_entitlement，审查修复）--------------------


def test_resolve_ecma_current_404_remapped_to_no_entitlement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # crossref 无 primary_url_domain → ecma 过刊 DOI 恒乐观归 CURRENT → GET 自营域 404（过刊实存
    # Wiley、econsoc 不托管）→ 现行 GONE=误终态；仅 ecma 改归 no_entitlement（触发 OA-fallback）。
    events: list[dict[str, object]] = []
    monkeypatch.setattr(
        "paper_crawler.adapters.econsoc.adapter.log_event",
        lambda level, msg, **kw: events.append({"msg": msg, **kw}),
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, content=b"not found on self-hosted current segment")

    with pytest.raises(CrawlerError) as exc:
        _adapter(handler).resolve_assets(make_econsoc_ecma_venue(), _stub("10.3982/ecta12058"))
    assert exc.value.error_class is ErrorClass.NO_ENTITLEMENT
    assert exc.value.detail == "ecma-current-not-hosted"
    # 可观测：ecma_current_404_as_ne 计数经 obslog 暴露。
    remaps = [e for e in events if "remapped GONE->no_entitlement" in str(e["msg"])]
    assert len(remaps) == 1
    assert remaps[0]["ecma_current_404_as_ne"] == 1


def test_resolve_te_landing_404_stays_gone() -> None:
    # te/qe 的 404 保持 GONE（econtheory 自持 OJS 对自己记录有权威性）——F1 仅作用于 ecma。
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, content=b"withdrawn")

    with pytest.raises(CrawlerError) as exc:
        _adapter(handler).resolve_assets(make_econsoc_teqe_venue("te"), _stub("10.3982/te6021"))
    assert exc.value.error_class is ErrorClass.GONE


# --- fetch（%PDF 透传 / HTML CF 质询→CHALLENGE / HTML 撤稿→GONE）------------------------------


def _stream_handler(body: bytes) -> object:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body)

    return handler


def test_fetch_pdf_passthrough() -> None:
    from paper_crawler.types import AssetPlan

    plan = AssetPlan(kind=AssetKind.PDF, url="https://www.econometricsociety.org/x/file/y.PDF")
    io = FakeFetchIO()
    result = _adapter(_stream_handler(_PDF)).fetch_asset(plan, io)
    assert result.ok is True
    assert io.data == _PDF


def test_fetch_cf_challenge_html_is_challenge() -> None:
    from paper_crawler.types import AssetPlan

    plan = AssetPlan(kind=AssetKind.PDF, url="https://www.econometricsociety.org/x/file/y.PDF")
    handler = _stream_handler(fixture_bytes("04_cf_challenge.html"))
    with pytest.raises(Challenged) as exc:
        _adapter(handler).fetch_asset(plan, FakeFetchIO())
    assert exc.value.error_class is ErrorClass.CHALLENGE


def test_fetch_withdrawn_html_is_gone() -> None:
    from paper_crawler.types import AssetPlan

    plan = AssetPlan(kind=AssetKind.PDF, url="https://www.econometricsociety.org/x/file/y.PDF")
    handler = _stream_handler(fixture_bytes("05_galley_not_pdf.html"))
    with pytest.raises(CrawlerError) as exc:
        _adapter(handler).fetch_asset(plan, FakeFetchIO())
    assert exc.value.error_class is ErrorClass.GONE


# --- healthcheck（TE OAI Identify repositoryName）-------------------------------------------


def _identify_body(repo_name: str) -> bytes:
    return (
        '<?xml version="1.0"?><OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">'
        f"<Identify><repositoryName>{repo_name}</repositoryName>"
        "<protocolVersion>2.0</protocolVersion></Identify></OAI-PMH>"
    ).encode()


def test_healthcheck_ok_when_repository_name_matches() -> None:
    handler = _stream_handler(_identify_body("Theoretical Economics"))
    report = _adapter(handler).healthcheck()
    assert report.healthy is True


def test_healthcheck_unhealthy_on_wrong_repository_name() -> None:
    handler = _stream_handler(_identify_body("Some Other Repository"))
    report = _adapter(handler).healthcheck()
    assert report.healthy is False


def test_healthcheck_unhealthy_when_unreachable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, content=b"down")

    report = _adapter(handler).healthcheck()
    assert report.healthy is False
