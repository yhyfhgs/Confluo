"""nber/adapter.py 单测（MockTransport 注入，零真实网络；nber.md §3/§4）。

覆盖：能力/元数据面 + HttpClientConsumer、undeclared（discover/enumerate）→CapabilityNotSupported、
resolve（零网络：>18 月→PDF plan / <18 月→NO_ENTITLEMENT recent_gated / t→空 / chapter→空 /
缺 doi→CONFIG / 缺 pub_date→保守开放 / 自定义窗 / 畸形窗→CONFIG）、fetch（流式 PDF / **软门非 PDF→
no_entitlement 非 integrity** / 404→GONE）、healthcheck（%PDF 结构性 healthy / 非 PDF unhealthy /
不可达）、**双域分桶假时钟**（www 1req/5s + www2 别名共享 + back.nber.org 独立桶 1req/10s，
route_for alias 陷阱规避——nber.md §4 接缝 N-3）、fixture 回放（PDF head / 软门 SYNTH）。
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

import httpx
import pytest

from helpers import FakeFetchIO, make_nber_venue
from helpers.nber_fixtures import fixture_bytes
from paper_crawler.adapter import HttpClientConsumer
from paper_crawler.adapters.nber import adapter as nber_adapter
from paper_crawler.adapters.nber.adapter import BACK_HOST, NberAdapter, _default_user_agent
from paper_crawler.errors import CapabilityNotSupported, CrawlerError, ErrorClass
from paper_crawler.http import HttpClient
from paper_crawler.ratelimit import RateLimiter
from paper_crawler.types import (
    AssetKind,
    AssetPlan,
    AuthLevel,
    Capability,
    IssueRef,
    PaperStub,
    UrlStrategy,
)

_UA = "PaperCrawler/test (personal research; mailto:test@example.com)"
_TODAY = date(2026, 7, 24)  # 假时钟基准（nber.md [LIVE] 2026-07-24）
_PDF = b"%PDF-1.5\n% nber\n" + b"0" * 128 + b"\n%%EOF\n"

Handler = Callable[[httpx.Request], httpx.Response]


@pytest.fixture(autouse=True)
def _pin_today(monkeypatch: pytest.MonkeyPatch) -> None:
    """把 18 月窗判定的 today 钉在 2026-07-24（跨边界 open/gated 断言可精确）。"""
    monkeypatch.setattr(nber_adapter, "_today", lambda: _TODAY)


def _paper(doi: str = "10.3386/w20000", pub_date: str | None = "2015-01") -> PaperStub:
    return PaperStub(title="An NBER working paper", identifiers=(("doi", doi),), pub_date=pub_date)


def _adapter(handler: Handler) -> NberAdapter:
    client = HttpClient(user_agent=_UA, transport=httpx.MockTransport(handler))
    return NberAdapter(http=client)


def _never(_request: httpx.Request) -> httpx.Response:
    raise AssertionError("no network expected for this path (resolve is offline)")


# --- 元数据 / 能力面 --------------------------------------------------------------------------


def test_adapter_attributes() -> None:
    adapter = NberAdapter()
    assert adapter.adapter_id == "nber"
    assert adapter.family == "open_access"
    assert adapter.capabilities == Capability.RESOLVE | Capability.FETCH
    assert Capability.DISCOVER not in adapter.capabilities  # enumerate 走 crossref（D-005）
    assert Capability.ENUMERATE not in adapter.capabilities
    assert adapter.auth_requirement is AuthLevel.NONE
    assert adapter.domains == ("www.nber.org", "www2.nber.org")
    assert adapter.resolve_offline is True  # 零网络 resolve（D-022 免限速闸）
    assert adapter.default_rate.requests_per_minute == 12.0  # www 1 req/5s
    assert adapter.default_rate.source_note != ""


def test_back_host_not_in_domains() -> None:
    """★接缝 N-3：back.nber.org **不进 domains**（否则被 route_for 别名到 www 桶错享宽松预算）。"""
    assert BACK_HOST == "back.nber.org"
    assert BACK_HOST not in NberAdapter.domains
    assert NberAdapter.BACK_RATE_POLICY.requests_per_minute == 6.0  # 独立桶 1 req/10s


def test_adapter_is_http_client_consumer() -> None:
    assert isinstance(NberAdapter(), HttpClientConsumer)


def test_undeclared_capabilities_raise() -> None:
    adapter = NberAdapter()
    venue = make_nber_venue()
    with pytest.raises(CapabilityNotSupported):
        list(adapter.discover_timeline(venue))
    with pytest.raises(CapabilityNotSupported):
        list(adapter.enumerate_issue(venue, IssueRef(venue_id=venue.id)))


# --- resolve（零网络，18 月窗离线判定）-------------------------------------------------------


def test_resolve_open_yields_direct_pdf_plan() -> None:
    plans = _adapter(_never).resolve_assets(make_nber_venue(), _paper("10.3386/w20000", "2015-01"))
    assert len(plans) == 1
    plan = plans[0]
    assert plan.kind is AssetKind.PDF
    assert plan.url_strategy is UrlStrategy.DIRECT
    assert plan.auth_needed is AuthLevel.NONE
    assert plan.expected_type == "application/pdf"
    assert plan.url == "https://www.nber.org/system/files/working_papers/w20000/w20000.pdf"


def test_resolve_recent_raises_no_entitlement() -> None:
    """<18 月软门 → NO_ENTITLEMENT(recent_gated)、不产计划（→OA-fallback，不绕过）。"""
    with pytest.raises(CrawlerError) as exc:
        _adapter(_never).resolve_assets(make_nber_venue(), _paper("10.3386/w35000", "2026-06"))
    assert exc.value.error_class is ErrorClass.NO_ENTITLEMENT
    assert exc.value.detail == "recent_gated"
    assert exc.value.status_code is None  # 离线日期判定（非 HTTP 响应体语义）


def test_resolve_boundary_exactly_open() -> None:
    """恰满 18 月（2025-01-24 + 18mo == today）→ 开放（产计划，非 gated）。"""
    paper = _paper("10.3386/w25000", "2025-01-24")
    plans = _adapter(_never).resolve_assets(make_nber_venue(), paper)
    assert len(plans) == 1


def test_resolve_t_series_deferred_yields_no_plan() -> None:
    """t{n} 全文路径未证实（N-2）→ Phase 5 不产全文计划（空列表，元数据照收）。"""
    plans = _adapter(_never).resolve_assets(make_nber_venue(), _paper("10.3386/t0042", "2015-01"))
    assert plans == []


def test_resolve_book_chapter_yields_no_plan() -> None:
    """非 w/t series（book chapter）→ 空计划（DEBUG 观测，非异常）。"""
    plans = _adapter(_never).resolve_assets(make_nber_venue(), _paper("10.3386/c14009", "2015-01"))
    assert plans == []


def test_resolve_non_nber_doi_yields_no_plan() -> None:
    plans = _adapter(_never).resolve_assets(
        make_nber_venue(), _paper("10.1257/aer.20230001", "2015-01")
    )
    assert plans == []


def test_resolve_missing_doi_raises_config() -> None:
    paper = PaperStub(title="no doi", identifiers=(("openalex", "W123"),))
    with pytest.raises(CrawlerError) as exc:
        _adapter(_never).resolve_assets(make_nber_venue(), paper)
    assert exc.value.error_class is ErrorClass.CONFIG


def test_resolve_missing_pub_date_conservatively_open() -> None:
    """pub_date 缺失 → 保守尝试开放路径（§3.2 步 2，交 fetch %PDF 守卫兜底）。"""
    plans = _adapter(_never).resolve_assets(make_nber_venue(), _paper("10.3386/w20000", None))
    assert len(plans) == 1
    assert plans[0].kind is AssetKind.PDF


def test_resolve_custom_window_quirk() -> None:
    """venue quirks.fulltext_open_after_months=24：2015 仍开放；一篇 2025-06 在 24 月窗内→gated。"""
    venue = make_nber_venue(fulltext_open_after_months=24)
    assert _adapter(_never).resolve_assets(venue, _paper("10.3386/w1", "2015-01"))
    with pytest.raises(CrawlerError) as exc:
        _adapter(_never).resolve_assets(venue, _paper("10.3386/w35000", "2025-06"))
    assert exc.value.error_class is ErrorClass.NO_ENTITLEMENT


def test_resolve_string_window_quirk_coerced() -> None:
    """quirks 值为字符串（YAML 加引号）→ 容错转 int（'24' → 24 月窗，2025-06 仍 gated）。"""
    venue = make_nber_venue(fulltext_open_after_months="24")
    with pytest.raises(CrawlerError) as exc:
        _adapter(_never).resolve_assets(venue, _paper("10.3386/w35000", "2025-06"))
    assert exc.value.error_class is ErrorClass.NO_ENTITLEMENT


def test_resolve_bad_window_quirk_raises_config() -> None:
    for bad in (True, "eighteen", [18]):
        venue = make_nber_venue(fulltext_open_after_months=bad)
        with pytest.raises(CrawlerError) as exc:
            _adapter(_never).resolve_assets(venue, _paper())
        assert exc.value.error_class is ErrorClass.CONFIG


# --- fetch（匿名直取 + %PDF 魔数双守卫）------------------------------------------------------


def _pdf_plan(url: str = "https://www.nber.org/system/files/working_papers/w20000/w20000.pdf"):  # type: ignore[no-untyped-def]
    return AssetPlan(kind=AssetKind.PDF, url=url, url_strategy=UrlStrategy.DIRECT)


def test_fetch_streams_pdf() -> None:
    io = FakeFetchIO()
    result = _adapter(lambda r: httpx.Response(200, content=_PDF)).fetch_asset(_pdf_plan(), io)
    assert result.ok is True
    assert result.bytes_written == len(_PDF)
    assert io.data.startswith(b"%PDF-")


def test_fetch_soft_gate_html_maps_no_entitlement_not_integrity() -> None:
    """红线核心守卫：软门返非 PDF（HTML）→ no_entitlement（**非 integrity**）→ OA-fallback。"""
    html = b"<!DOCTYPE html><html><body>Please sign in or subscribe</body></html>"
    adapter = _adapter(lambda r: httpx.Response(200, content=html))
    with pytest.raises(CrawlerError) as exc:
        adapter.fetch_asset(_pdf_plan(), FakeFetchIO())
    assert exc.value.error_class is ErrorClass.NO_ENTITLEMENT
    assert exc.value.error_class is not ErrorClass.INTEGRITY
    assert exc.value.detail == "recent_gated"


def test_fetch_soft_gate_synth_fixture_maps_no_entitlement() -> None:
    """[SYNTH] 软门 fixture 回放（<18 月软门无真实抓取，§7）→ no_entitlement。"""
    body = fixture_bytes("03_softgate_synth.html")
    adapter = _adapter(lambda r: httpx.Response(200, content=body))
    with pytest.raises(CrawlerError) as exc:
        adapter.fetch_asset(_pdf_plan(), FakeFetchIO())
    assert exc.value.error_class is ErrorClass.NO_ENTITLEMENT


def test_fetch_pdf_head_fixture_replays() -> None:
    """[LIVE-shape] w30000 PDF head fixture 回放：%PDF- 魔数 → 正常落盘。"""
    body = fixture_bytes("02_pdf_head_w30000.bin")
    io = FakeFetchIO()
    result = _adapter(lambda r: httpx.Response(200, content=body)).fetch_asset(_pdf_plan(), io)
    assert result.ok is True
    assert io.data.startswith(b"%PDF-")


def test_fetch_404_maps_gone_via_httpclient() -> None:
    """PDF 404（DOI 太新/收录延迟）→ HttpClient 直接映射 GONE（本层不干预，§5）。"""
    with pytest.raises(CrawlerError) as exc:
        _adapter(lambda r: httpx.Response(404, content=b"not found")).fetch_asset(
            _pdf_plan(), FakeFetchIO()
        )
    assert exc.value.error_class is ErrorClass.GONE


def test_fetch_non_html_non_pdf_passes_through_to_pipeline() -> None:
    """非 HTML 非 PDF（如截断二进制）→ 不判软门、透传交 pipeline 的 %PDF 权威校验（INTEGRITY）。

    守卫只拦"形似 HTML 的软门"；其余非 PDF 由 pipeline 冻结 %PDF 校验处置（不越权改判）。
    """
    io = FakeFetchIO()
    result = _adapter(lambda r: httpx.Response(200, content=b"\x00\x01broken")).fetch_asset(
        _pdf_plan(), io
    )
    assert result.ok is True  # adapter 透传；pipeline 侧 validate_pdf_magic 会判 INTEGRITY
    assert not io.data.startswith(b"%PDF-")


# --- healthcheck（w30000 首 chunk %PDF 结构性探测）-------------------------------------------


def test_healthcheck_pdf_magic_healthy() -> None:
    report = _adapter(lambda r: httpx.Response(200, content=_PDF)).healthcheck()
    assert report.healthy is True
    assert "PENDING" in report.detail


def test_healthcheck_non_pdf_unhealthy() -> None:
    report = _adapter(lambda r: httpx.Response(200, content=b"<html>gate</html>")).healthcheck()
    assert report.healthy is False
    assert "%PDF" in report.detail


def test_healthcheck_unreachable_unhealthy() -> None:
    report = _adapter(lambda r: httpx.Response(503, content=b"down")).healthcheck()
    assert report.healthy is False
    assert "unreachable" in report.detail


def test_healthcheck_probes_known_open_w30000() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, content=_PDF)

    _adapter(handler).healthcheck()
    assert any("w30000/w30000.pdf" in u for u in seen)


# --- 双域分桶假时钟（nber.md §4，接缝 N-3）--------------------------------------------------


class _FakeClock:
    """固定假时钟（不推进）——连续 acquire 累加欠账，可精确断言 wait 序列。"""

    def __init__(self, t: float = 1000.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t


def _route_for_sim(limiter: RateLimiter) -> None:
    """模拟 pipeline `route_for` 对 nber 的登记：register domains[0] + alias domains[1:]。"""
    limiter.register(NberAdapter.domains[0], NberAdapter.default_rate)
    for secondary in NberAdapter.domains[1:]:
        limiter.alias(secondary, NberAdapter.domains[0])


def test_www_bucket_is_1_req_per_5s() -> None:
    """www.nber.org（domains[0]）1 req/5s：突发 1，第 2 次立即 acquire 需等 5s。"""
    limiter = RateLimiter(clock=_FakeClock())
    _route_for_sim(limiter)
    assert limiter.acquire("www.nber.org") == 0.0  # burst 首次
    assert limiter.acquire("www.nber.org") == pytest.approx(5.0)  # 60/12


def test_www2_aliases_share_www_bucket() -> None:
    """www2.nber.org（低号 301 目标）别名共享 www 桶——drain www 后 www2 同欠账。"""
    limiter = RateLimiter(clock=_FakeClock())
    _route_for_sim(limiter)
    assert limiter.acquire("www.nber.org") == 0.0  # drain www 首 token
    assert limiter.acquire("www2.nber.org") == pytest.approx(5.0)  # 共享同桶 → 欠账


def test_back_host_not_auto_registered_by_route_for() -> None:
    """route_for 只登记 domains——back.nber.org 未注册（须独立 on-demand register，§4）。

    未注册 domain 的 acquire fail-fast CONFIG（ratelimit 语义）——证 back **不**被 domains 覆盖，
    故不会被 alias 到 www 桶错享 5s 宽松预算（规避 route_for alias 陷阱）。
    """
    limiter = RateLimiter(clock=_FakeClock())
    _route_for_sim(limiter)
    with pytest.raises(CrawlerError) as exc:
        limiter.acquire("back.nber.org")
    assert exc.value.error_class is ErrorClass.CONFIG


def test_back_bucket_independent_1_req_per_10s() -> None:
    """back.nber.org 独立桶（BACK_RATE_POLICY，1 req/10s）与 www 桶互不影响（wait 序列断言）。

    on-demand register back 独立桶后：back 第 2 次需等 **10s**（遵 Crawl-delay:10）；且 www 桶
    被 drain 到欠账 **不影响** back 桶（独立预算）——这是"独立桶 vs 错误共享 www 宽松桶"的关键证据。
    """
    limiter = RateLimiter(clock=_FakeClock())
    _route_for_sim(limiter)
    # watch 路径 on-demand register（OA-host 先例，不 alias）。
    limiter.register(BACK_HOST, NberAdapter.BACK_RATE_POLICY)

    # 把 www 桶 drain 到欠账（模拟全文抓取占满 www 预算）。
    limiter.acquire("www.nber.org")
    limiter.acquire("www.nber.org")

    # back 桶独立、未被 www 欠账波及：首次 0，第 2 次需等 10s（而非 www 的 5s）。
    assert limiter.acquire(BACK_HOST) == 0.0
    assert limiter.acquire(BACK_HOST) == pytest.approx(10.0)  # 60/6，遵 Crawl-delay:10


# --- HttpClient 注入 / UA --------------------------------------------------------------------


def test_set_http_client_injects() -> None:
    adapter = NberAdapter()
    client = HttpClient(user_agent=_UA)
    adapter.set_http_client(client)
    assert adapter._client() is client


def test_lazy_client_built_and_cached() -> None:
    adapter = NberAdapter()
    client = adapter._client()
    assert isinstance(client, HttpClient)
    assert adapter._client() is client


def test_default_user_agent_uses_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PAPER_CRAWLER_CONTACT_EMAIL", "real@example.org")
    assert "mailto:real@example.org" in _default_user_agent()


def test_default_user_agent_placeholder_when_env_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PAPER_CRAWLER_CONTACT_EMAIL", raising=False)
    assert ".invalid" in _default_user_agent()
