"""openalex/adapter.py 单测（MockTransport 注入，零真实网络；aggregators.md §5.3）。

覆盖：capabilities 空集 + duck-typed 协议一致性、`enrich_batch`（去重/URL 批切分/
错误映射 429/400/500/402→rate_limited 重分类/预算熔断/预算累计持久化）、healthcheck
（无 key→NotImplementedError/有 key 结构性 PENDING/精确匹配/漂移/不可达）、批大小
URL 长度上限论证的直接验证、HttpClient 注入与惰性自建。
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import httpx
import pytest

from helpers.openalex_fixtures import fixture_bytes, http_fixture
from paper_crawler.adapter import ApiKeyConsumer, EnrichmentSource, HttpClientConsumer
from paper_crawler.adapters.openalex import budget
from paper_crawler.adapters.openalex.adapter import (
    _MAX_URL_CHARS,
    OpenAlexAdapter,
    _batch_dois,
    _default_user_agent,
)
from paper_crawler.errors import CrawlerError, ErrorClass
from paper_crawler.http import HttpClient
from paper_crawler.types import AuthLevel, Capability

_UA = "PaperCrawler/test (personal research; mailto:test@example.com)"
Handler = Callable[[httpx.Request], httpx.Response]


def _adapter(handler: Handler, *, api_key: str | None = None) -> OpenAlexAdapter:
    client = HttpClient(user_agent=_UA, transport=httpx.MockTransport(handler))
    adapter = OpenAlexAdapter(http=client)
    adapter.set_api_key(api_key)
    return adapter


def _resp(body: bytes, status: int = 200) -> httpx.Response:
    return httpx.Response(status, content=body)


def _never(_request: httpx.Request) -> httpx.Response:
    raise AssertionError("no network expected for this path")


# --- 元数据/能力面 ---------------------------------------------------------------------------


def test_adapter_attributes() -> None:
    adapter = OpenAlexAdapter()
    assert adapter.adapter_id == "openalex"
    assert adapter.family == "aggregator"
    assert adapter.capabilities == Capability(0)
    assert not adapter.capabilities  # 空集
    for cap in Capability:
        assert cap not in adapter.capabilities
    assert adapter.auth_requirement is AuthLevel.NONE
    assert adapter.domains == ("api.openalex.org",)
    assert adapter.default_rate.requests_per_minute > 0
    assert adapter.default_rate.source_note != ""


def test_adapter_is_enrich_source_and_api_key_consumer_and_http_client_consumer() -> None:
    adapter = OpenAlexAdapter()
    assert isinstance(adapter, EnrichmentSource)
    assert isinstance(adapter, ApiKeyConsumer)
    assert isinstance(adapter, HttpClientConsumer)


def test_undeclared_capabilities_raise_capability_not_supported() -> None:
    from helpers import make_mock_venue
    from paper_crawler.errors import CapabilityNotSupported
    from paper_crawler.types import IssueRef

    adapter = OpenAlexAdapter()
    venue = make_mock_venue()
    with pytest.raises(CapabilityNotSupported):
        list(adapter.discover_timeline(venue))
    with pytest.raises(CapabilityNotSupported):
        list(adapter.enumerate_issue(venue, IssueRef(venue_id=venue.id)))
    with pytest.raises(CapabilityNotSupported):
        from paper_crawler.types import PaperStub

        adapter.resolve_assets(venue, PaperStub(title="T", identifiers=(("doi", "10.1/x"),)))


# --- _batch_dois：URL 长度安全上限（批大小论证的直接验证）--------------------------------------


def test_batch_dois_single_small_list_is_one_batch() -> None:
    batches = _batch_dois(["10.1/a", "10.1/b", "10.1/c"])
    assert batches == [["10.1/a", "10.1/b", "10.1/c"]]


def test_batch_dois_empty_list_yields_no_batches() -> None:
    assert _batch_dois([]) == []


def test_batch_dois_never_exceeds_max_url_chars() -> None:
    """核心安全性质：任意批次编码后的完整 URL 前缀累计长度不超过 `_MAX_URL_CHARS`。"""
    from urllib.parse import quote_plus

    from paper_crawler.adapters.openalex.adapter import _FILTER_PREFIX, _OR_SEP_ENCODED_LEN

    dois = [f"10.{1000 + i}/synthetic.doi-with-some-length-{i}" for i in range(500)]
    batches = _batch_dois(dois)

    assert sum(len(b) for b in batches) == len(dois)  # 无丢失无重复
    for batch in batches:
        total = len(_FILTER_PREFIX) + sum(len(quote_plus(d)) for d in batch)
        total += _OR_SEP_ENCODED_LEN * (len(batch) - 1)
        assert total <= _MAX_URL_CHARS, f"batch exceeds safety margin: {total} chars"


def test_batch_dois_respects_secondary_item_cap() -> None:
    """极短 DOI 退化场景：即使长度远未触顶，批内项数也不超过次要上限。"""
    from paper_crawler.adapters.openalex.adapter import _MAX_BATCH_ITEMS

    dois = [f"10.1/{i}" for i in range(_MAX_BATCH_ITEMS * 3)]
    batches = _batch_dois(dois)
    assert all(len(b) <= _MAX_BATCH_ITEMS for b in batches)
    assert sum(len(b) for b in batches) == len(dois)


def test_batch_dois_preserves_order_across_batches() -> None:
    dois = [f"10.1/{i:04d}" for i in range(120)]
    batches = _batch_dois(dois)
    flattened = [d for batch in batches for d in batch]
    assert flattened == dois


def test_batch_dois_pathological_single_doi_longer_than_cap_gets_own_batch() -> None:
    """单个 DOI 自身编码后即超限的极端边界——不死循环，独占一批。"""
    huge = "10.1/" + "x" * 3000
    batches = _batch_dois(["10.1/a", huge, "10.1/b"])
    assert batches == [["10.1/a"], [huge], ["10.1/b"]]


# --- enrich_batch：正常/去重/多批 ---------------------------------------------------------------


def test_enrich_batch_empty_input_yields_empty_no_network() -> None:
    adapter = _adapter(_never, api_key="k")
    assert adapter.enrich_batch([]) == []


def test_enrich_batch_dedupes_and_skips_blank(tmp_path: Path) -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return _resp(fixture_bytes("02_works_empty.json"))

    adapter = _adapter(handler, api_key="k")
    adapter.configure_budget(daily_budget_usd=1.0, state_path=tmp_path / "budget.json")
    adapter.enrich_batch(["10.1/a", "10.1/a", "", "10.1/b"])

    assert len(calls) == 1
    assert "10.1%2Fa" in calls[0]
    assert calls[0].count("10.1%2Fa") == 1  # 去重——不重复出现


def test_enrich_batch_normal_response_produces_stubs(tmp_path: Path) -> None:
    adapter = _adapter(lambda r: _resp(fixture_bytes("01_works_normal.json")), api_key="k")
    adapter.configure_budget(daily_budget_usd=1.0, state_path=tmp_path / "budget.json")

    stubs = adapter.enrich_batch(["10.7717/peerj.4375", "10.9999/synthetic.minimal"])

    assert len(stubs) == 2
    assert stubs[0].title.startswith("The State of OA")


def test_enrich_batch_multiple_internal_batches_multiple_requests(tmp_path: Path) -> None:
    """DOI 数超过单批 URL 长度上限 → 内部触发多次真实请求。"""
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return _resp(fixture_bytes("02_works_empty.json"))

    adapter = _adapter(handler, api_key="k")
    adapter.configure_budget(daily_budget_usd=100.0, state_path=tmp_path / "budget.json")
    many = [f"10.1/{i:05d}-{'x' * 40}" for i in range(200)]  # 足够长，必然多批
    adapter.enrich_batch(many)

    assert len(calls) > 1


def test_enrich_batch_api_key_injected_into_url(tmp_path: Path) -> None:
    captured: list[httpx.URL] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request.url)
        return _resp(fixture_bytes("02_works_empty.json"))

    adapter = _adapter(handler, api_key="secret-key-123")
    adapter.configure_budget(daily_budget_usd=1.0, state_path=tmp_path / "budget.json")
    adapter.enrich_batch(["10.1/a"])

    assert captured[0].params.get("api_key") == "secret-key-123"


def test_enrich_batch_no_api_key_omits_param_but_still_requests(tmp_path: Path) -> None:
    """openalex key 可选——匿名请求正常发出（区别于 s2 的"无 key 不发请求"）。"""
    captured: list[httpx.URL] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request.url)
        return _resp(fixture_bytes("02_works_empty.json"))

    adapter = _adapter(handler, api_key=None)
    adapter.configure_budget(daily_budget_usd=1.0, state_path=tmp_path / "budget.json")
    adapter.enrich_batch(["10.1/a"])

    assert "api_key" not in captured[0].params
    assert len(captured) == 1


# --- 预算熔断（本地状态 + 402 重分类）------------------------------------------------------------


def test_enrich_batch_local_budget_exhausted_raises_rate_limited_without_request(
    tmp_path: Path,
) -> None:
    state_path = tmp_path / "budget.json"
    budget.save_state(state_path, budget.BudgetState(date=budget._today_utc(), spent_usd=0.5))
    adapter = _adapter(_never, api_key="k")
    adapter.configure_budget(daily_budget_usd=0.5, state_path=state_path)

    with pytest.raises(CrawlerError) as exc:
        adapter.enrich_batch(["10.1/a"])
    assert exc.value.error_class is ErrorClass.RATE_LIMITED
    assert "budget" in str(exc.value).lower()


def test_enrich_batch_accumulates_cost_across_calls(tmp_path: Path) -> None:
    state_path = tmp_path / "budget.json"
    adapter = _adapter(lambda r: _resp(fixture_bytes("01_works_normal.json")), api_key="k")
    adapter.configure_budget(daily_budget_usd=1.0, state_path=state_path)

    adapter.enrich_batch(["10.1/a"])
    state = budget.load_state(state_path)
    assert state.spent_usd == pytest.approx(0.0002)

    adapter.enrich_batch(["10.1/b"])
    state = budget.load_state(state_path)
    assert state.spent_usd == pytest.approx(0.0004)


def test_enrich_batch_second_batch_blocked_after_first_exhausts_budget(tmp_path: Path) -> None:
    """内部多批场景：前一批把预算刚好打满，后续批次在发请求前熔断。"""
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        # 每批花掉全部预算——模拟"这批恰好把预算打满"。
        return _resp(b'{"meta":{"cost_usd":1.0},"results":[]}')

    adapter = _adapter(handler, api_key="k")
    state_path = tmp_path / "budget.json"
    adapter.configure_budget(daily_budget_usd=1.0, state_path=state_path)
    many = [f"10.1/{i:05d}-{'x' * 40}" for i in range(200)]  # 保证内部切多批

    with pytest.raises(CrawlerError) as exc:
        adapter.enrich_batch(many)
    assert exc.value.error_class is ErrorClass.RATE_LIMITED
    assert len(calls) == 1  # 第一批发了请求并把预算打满；第二批被熔断，未发请求


def test_enrich_batch_server_402_reclassified_as_rate_limited(tmp_path: Path) -> None:
    status, headers, body = http_fixture("03_works_402_budget_exhausted.http")
    adapter = _adapter(lambda r: httpx.Response(status, headers=headers, content=body), api_key="k")
    adapter.configure_budget(daily_budget_usd=1.0, state_path=tmp_path / "budget.json")

    with pytest.raises(CrawlerError) as exc:
        adapter.enrich_batch(["10.1/a"])
    assert exc.value.error_class is ErrorClass.RATE_LIMITED
    assert "402" in str(exc.value)


def test_enrich_batch_402_reclassified_by_status_code_not_message(tmp_path: Path) -> None:
    """检查单 #4 迁移：402 重分类靠 `exc.status_code == 402`（结构化契约），非异常消息文本嗅探。

    构造一个 `status_code=402` 但消息里**不含** "HTTP 402" 前缀的 CONFIG 错——旧文本嗅探
    （`_looks_like_status` 解析 "HTTP {status}" 前缀）会漏判成普通 CONFIG，status_code 判据仍准确。
    """

    class _Fake402Client:
        def get_bytes(self, url: str, *, accept: str | None = None) -> bytes:
            raise CrawlerError(ErrorClass.CONFIG, "credit limit exceeded", status_code=402)

    adapter = OpenAlexAdapter(http=_Fake402Client())  # type: ignore[arg-type]
    adapter.set_api_key("k")
    adapter.configure_budget(daily_budget_usd=1.0, state_path=tmp_path / "budget.json")

    with pytest.raises(CrawlerError) as exc:
        adapter.enrich_batch(["10.1/a"])
    assert exc.value.error_class is ErrorClass.RATE_LIMITED
    assert "402" in str(exc.value)  # 本层构造的固定文案含 402


def test_enrich_batch_non_402_config_error_propagates(tmp_path: Path) -> None:
    """400（非 402）的 CONFIG 错不被误重分类——只有 status_code==402 才转 RATE_LIMITED。"""

    class _Fake400Client:
        def get_bytes(self, url: str, *, accept: str | None = None) -> bytes:
            raise CrawlerError(ErrorClass.CONFIG, "HTTP 400 for ...", status_code=400)

    adapter = OpenAlexAdapter(http=_Fake400Client())  # type: ignore[arg-type]
    adapter.set_api_key("k")
    adapter.configure_budget(daily_budget_usd=1.0, state_path=tmp_path / "budget.json")

    with pytest.raises(CrawlerError) as exc:
        adapter.enrich_batch(["10.1/a"])
    assert exc.value.error_class is ErrorClass.CONFIG


# --- 其余错误映射（经 HttpClient 冻结映射，未特化的原样透传）------------------------------------


def test_enrich_batch_429_maps_rate_limited(tmp_path: Path) -> None:
    status, headers, body = http_fixture("05_works_429.http")
    adapter = _adapter(lambda r: httpx.Response(status, headers=headers, content=body), api_key="k")
    adapter.configure_budget(daily_budget_usd=1.0, state_path=tmp_path / "budget.json")

    with pytest.raises(CrawlerError) as exc:
        adapter.enrich_batch(["10.1/a"])
    assert exc.value.error_class is ErrorClass.RATE_LIMITED
    assert "retry_after_s=3" in exc.value.detail


def test_enrich_batch_400_maps_config(tmp_path: Path) -> None:
    status, headers, body = http_fixture("06_works_400_bad_filter.http")
    adapter = _adapter(lambda r: httpx.Response(status, headers=headers, content=body), api_key="k")
    adapter.configure_budget(daily_budget_usd=1.0, state_path=tmp_path / "budget.json")

    with pytest.raises(CrawlerError) as exc:
        adapter.enrich_batch(["10.1/a"])
    assert exc.value.error_class is ErrorClass.CONFIG


def test_enrich_batch_500_maps_transient(tmp_path: Path) -> None:
    status, headers, body = http_fixture("07_works_500.http")
    adapter = _adapter(lambda r: httpx.Response(status, headers=headers, content=body), api_key="k")
    adapter.configure_budget(daily_budget_usd=1.0, state_path=tmp_path / "budget.json")

    with pytest.raises(CrawlerError) as exc:
        adapter.enrich_batch(["10.1/a"])
    assert exc.value.error_class is ErrorClass.TRANSIENT


def test_enrich_batch_skips_are_logged(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    events: list[dict[str, object]] = []

    def _capture(level: str, msg: str, **extra: object) -> None:
        events.append({"msg": msg, **extra})

    monkeypatch.setattr("paper_crawler.adapters.openalex.adapter.log_event", _capture)
    data = b'{"meta":{},"results":[{"id":"https://openalex.org/W1"}]}'  # 无 title→跳过
    adapter = _adapter(lambda r: _resp(data), api_key="k")
    adapter.configure_budget(daily_budget_usd=1.0, state_path=tmp_path / "budget.json")

    adapter.enrich_batch(["10.1/a"])

    skip_events = [e for e in events if e["msg"] == "openalex enrich_batch records skipped"]
    assert len(skip_events) == 1
    assert skip_events[0]["skipped_untitled"] == 1


# --- healthcheck -----------------------------------------------------------------------------


def test_healthcheck_no_key_raises_not_implemented() -> None:
    adapter = OpenAlexAdapter()
    with pytest.raises(NotImplementedError, match="openalex key 未配置"):
        adapter.healthcheck()


def test_healthcheck_pending_golden_structural_healthy() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "/works/W2741809807" in str(request.url)
        return _resp(fixture_bytes("08_single_work_healthcheck.json"))

    report = _adapter(handler, api_key="k").healthcheck()
    assert report.healthy is True
    assert "PENDING" in report.detail
    assert "The State of OA" in report.detail


def test_healthcheck_exact_match_when_golden_captured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "paper_crawler.adapters.openalex.adapter._HEALTHCHECK_TITLE",
        "The State of OA: A Large-Scale Analysis of the Prevalence and Impact "
        "of Open Access Articles",
    )
    report = _adapter(
        lambda r: _resp(fixture_bytes("08_single_work_healthcheck.json")), api_key="k"
    ).healthcheck()
    assert report.healthy is True
    assert "matched" in report.detail


def test_healthcheck_drift_when_title_differs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "paper_crawler.adapters.openalex.adapter._HEALTHCHECK_TITLE", "A Completely Different Title"
    )
    report = _adapter(
        lambda r: _resp(fixture_bytes("08_single_work_healthcheck.json")), api_key="k"
    ).healthcheck()
    assert report.healthy is False
    assert "drift" in report.detail


def test_healthcheck_empty_title_unhealthy_parse() -> None:
    adapter = _adapter(lambda r: _resp(b'{"id": "https://openalex.org/W1"}'), api_key="k")
    report = adapter.healthcheck()
    assert report.healthy is False
    assert "parse" in report.detail.lower()


def test_healthcheck_unreachable_unhealthy() -> None:
    report = _adapter(lambda r: httpx.Response(500, text="down"), api_key="k").healthcheck()
    assert report.healthy is False
    assert "unreachable" in report.detail


def test_healthcheck_api_key_injected_into_url() -> None:
    captured: list[httpx.URL] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request.url)
        return _resp(fixture_bytes("08_single_work_healthcheck.json"))

    _adapter(handler, api_key="secret-key-456").healthcheck()
    assert captured[0].params.get("api_key") == "secret-key-456"


# --- HttpClient 注入 / 惰性自建 / UA / state path 惰性默认 --------------------------------------


def test_set_http_client_injects() -> None:
    adapter = OpenAlexAdapter()
    client = HttpClient(user_agent=_UA)
    adapter.set_http_client(client)
    assert adapter._client() is client


def test_lazy_client_built_and_cached_without_injection() -> None:
    adapter = OpenAlexAdapter()
    client = adapter._client()
    assert isinstance(client, HttpClient)
    assert adapter._client() is client


def test_default_user_agent_uses_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PAPER_CRAWLER_CONTACT_EMAIL", "real@example.org")
    assert "mailto:real@example.org" in _default_user_agent()


def test_default_user_agent_placeholder_when_env_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PAPER_CRAWLER_CONTACT_EMAIL", raising=False)
    assert ".invalid" in _default_user_agent()


def test_resolve_state_path_defaults_under_home_when_not_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PAPER_CRAWLER_HOME", raising=False)  # 宿主 env 隔离（D-032 后常驻）
    adapter = OpenAlexAdapter()
    path = adapter._resolve_state_path()
    assert path == Path.home() / ".paper-crawler" / "state" / "openalex-budget.json"


def test_resolve_state_path_honors_env_home(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # D-032：config-home 迁入仓库后 env 是主指向机制——兜底路径必须尊重之，否则
    # 脱离 CLI 装配的调用方会静默回落、重建空的 ~/.paper-crawler。
    monkeypatch.setenv("PAPER_CRAWLER_HOME", str(tmp_path / "repo-home"))
    adapter = OpenAlexAdapter()
    path = adapter._resolve_state_path()
    assert path == tmp_path / "repo-home" / "state" / "openalex-budget.json"


def test_configure_budget_overrides_state_path_and_budget() -> None:
    adapter = OpenAlexAdapter()
    custom = Path("/tmp/custom/openalex-budget.json")
    adapter.configure_budget(daily_budget_usd=2.5, state_path=custom)
    assert adapter._resolve_state_path() == custom
    assert adapter._daily_budget_usd == 2.5
