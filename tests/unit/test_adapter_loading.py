"""adapter.py（§2.3）单测：注册发现、元数据完备、能力路由（Capability/NotImplemented）。"""

import pytest

from paper_crawler.adapter import (
    HttpClientConsumer,
    SourceAdapter,
    bind_http_client,
    load_adapters,
)
from paper_crawler.errors import CapabilityNotSupported
from paper_crawler.http import HttpClient
from paper_crawler.types import (
    AssetKind,
    AssetPlan,
    AuthLevel,
    Capability,
    HealthReport,
    IssueRef,
    PaperStub,
    RatePolicy,
    VenueSpec,
)

EXPECTED_ADAPTER_IDS = {
    "mock_platform",
    "crossref",
    "openreview",
    "elsevier_sd",
    "arxiv",
    "pmlr",
    "acl_anthology",
    "cvf",
}
VALID_FAMILIES = {"open_access", "auth_gated", "aggregator"}


@pytest.fixture
def adapters() -> dict[str, SourceAdapter]:
    return load_adapters()


def test_load_adapters_discovers_all_registered(adapters: dict[str, SourceAdapter]) -> None:
    # 三个内置 stub + mock + 五个真实 adapter（arxiv/openreview/pmlr/acl_anthology/cvf）。
    assert set(adapters) == EXPECTED_ADAPTER_IDS


def test_every_adapter_has_complete_metadata(adapters: dict[str, SourceAdapter]) -> None:
    for adapter_id, adapter in adapters.items():
        assert adapter.adapter_id == adapter_id
        assert adapter.family in VALID_FAMILIES
        assert isinstance(adapter.capabilities, Capability)
        assert isinstance(adapter.default_rate, RatePolicy)
        assert adapter.default_rate.source_note != ""  # 出处必注（design/02）
        assert adapter.default_rate.requests_per_minute > 0
        assert isinstance(adapter.auth_requirement, AuthLevel)
        assert adapter.domains  # 非空
        assert all(isinstance(d, str) and d for d in adapter.domains)


def test_adapters_satisfy_runtime_checkable_protocol(
    adapters: dict[str, SourceAdapter],
) -> None:
    for adapter in adapters.values():
        assert isinstance(adapter, SourceAdapter)


def test_mock_platform_attributes(adapters: dict[str, SourceAdapter]) -> None:
    mock = adapters["mock_platform"]
    assert mock.family == "open_access"
    assert (
        mock.capabilities
        == Capability.DISCOVER | Capability.ENUMERATE | Capability.RESOLVE | Capability.FETCH
    )
    assert mock.default_rate.requests_per_minute == 600
    assert mock.default_rate.burst == 10
    assert mock.auth_requirement is AuthLevel.NONE
    assert mock.domains == ("mock.local",)


def test_crossref_stub_attributes(adapters: dict[str, SourceAdapter]) -> None:
    crossref = adapters["crossref"]
    assert crossref.family == "aggregator"
    assert crossref.capabilities == Capability.DISCOVER | Capability.ENUMERATE
    assert crossref.default_rate.requests_per_minute == 50
    assert crossref.domains == ("api.crossref.org",)
    assert "⚠" in crossref.default_rate.source_note


def test_openreview_attributes(adapters: dict[str, SourceAdapter]) -> None:
    # Phase 2 T-openreview：真实 adapter（entry point 注册），非 stub。
    openreview = adapters["openreview"]
    assert openreview.family == "open_access"
    assert (
        openreview.capabilities
        == Capability.DISCOVER | Capability.ENUMERATE | Capability.RESOLVE | Capability.FETCH
    )
    assert Capability.SEARCH not in openreview.capabilities
    assert openreview.default_rate.requests_per_minute == 30
    assert "OpenReview" in openreview.default_rate.source_note  # 出处（非占位 ⚠）
    assert openreview.auth_requirement is AuthLevel.FREE_ACCOUNT  # notes/PDF 需 token（§3）
    assert openreview.domains == (
        "api2.openreview.net",
        "api.openreview.net",
        "openreview.net",
    )


def test_elsevier_stub_attributes(adapters: dict[str, SourceAdapter]) -> None:
    elsevier = adapters["elsevier_sd"]
    assert elsevier.family == "auth_gated"
    assert elsevier.capabilities == Capability.RESOLVE | Capability.FETCH
    assert elsevier.auth_requirement is AuthLevel.INSTITUTIONAL
    assert elsevier.default_rate.requests_per_minute == 10
    assert elsevier.domains == ("www.sciencedirect.com",)


def test_arxiv_attributes(adapters: dict[str, SourceAdapter]) -> None:
    arxiv = adapters["arxiv"]
    assert arxiv.family == "open_access"
    # arxiv.md §1 裁决：DISCOVER|ENUMERATE|RESOLVE|FETCH，无 SEARCH。
    assert (
        arxiv.capabilities
        == Capability.DISCOVER | Capability.ENUMERATE | Capability.RESOLVE | Capability.FETCH
    )
    assert Capability.SEARCH not in arxiv.capabilities
    assert arxiv.default_rate.requests_per_minute == 20.0  # 1 req/3s
    assert "Terms of Use" in arxiv.default_rate.source_note  # ToU 出处
    assert arxiv.auth_requirement is AuthLevel.NONE
    assert arxiv.domains == ("export.arxiv.org", "oaipmh.arxiv.org", "arxiv.org")


def test_pmlr_attributes(adapters: dict[str, SourceAdapter]) -> None:
    pmlr = adapters["pmlr"]
    assert pmlr.family == "open_access"
    # pmlr.md §1 裁决：DISCOVER|ENUMERATE|RESOLVE|FETCH，无 SEARCH。
    assert (
        pmlr.capabilities
        == Capability.DISCOVER | Capability.ENUMERATE | Capability.RESOLVE | Capability.FETCH
    )
    assert Capability.SEARCH not in pmlr.capabilities
    assert pmlr.default_rate.requests_per_minute == 30.0  # 1 req/2s
    assert pmlr.auth_requirement is AuthLevel.NONE
    assert pmlr.domains == ("proceedings.mlr.press", "raw.githubusercontent.com")


def test_cvf_attributes(adapters: dict[str, SourceAdapter]) -> None:
    cvf = adapters["cvf"]
    assert cvf.family == "open_access"
    # design/adapters/cvf.md §1 裁决：DISCOVER|ENUMERATE|RESOLVE|FETCH，无 SEARCH。
    assert (
        cvf.capabilities
        == Capability.DISCOVER | Capability.ENUMERATE | Capability.RESOLVE | Capability.FETCH
    )
    assert Capability.SEARCH not in cvf.capabilities
    assert cvf.default_rate.requests_per_minute == 30.0  # 1 req/2s
    assert "site-survey/cvf.md" in cvf.default_rate.source_note  # 出处（非占位 ⚠）
    assert cvf.auth_requirement is AuthLevel.NONE  # 匿名可读、无认证（§2/§4）
    assert cvf.domains == ("openaccess.thecvf.com",)


def test_healthcheck_defaults_healthy(adapters: dict[str, SourceAdapter]) -> None:
    # mock_platform 不覆写 healthcheck → 继承 AdapterBase 默认恒 healthy。
    # （stub adapter 现已覆写为抛 NotImplementedError，见下一个测试。）
    report = adapters["mock_platform"].healthcheck()
    assert isinstance(report, HealthReport)
    assert report.healthy is True


@pytest.mark.parametrize("adapter_id", ["crossref", "elsevier_sd"])
def test_stub_healthcheck_raises_not_implemented_for_canary_skip(
    adapters: dict[str, SourceAdapter], adapter_id: str
) -> None:
    """canary SKIP 语义修正：剩余 stub 的 healthcheck 抛 NotImplementedError。

    此前继承 AdapterBase 默认恒 healthy，会让未实现的 stub 在 canary 假报"健康"；
    改为抛 NotImplementedError 后 `run_canary` 归为 SKIP（不影响退出码，见 canary.py）。
    （openreview 已 Phase 2 落地真实 healthcheck——匿名双端 groups 探测，不再 stub。）
    """
    with pytest.raises(NotImplementedError):
        adapters[adapter_id].healthcheck()


def test_undeclared_capability_raises_capability_not_supported(
    adapters: dict[str, SourceAdapter], venue: VenueSpec
) -> None:
    paper = PaperStub(title="T", identifiers=(("doi", "10.9999/x"),))
    plan = AssetPlan(kind=AssetKind.PDF, url="https://x/y")

    # crossref 无 RESOLVE/FETCH（AdapterBase 兜底）。
    with pytest.raises(CapabilityNotSupported):
        adapters["crossref"].resolve_assets(venue, paper)
    with pytest.raises(CapabilityNotSupported):
        adapters["crossref"].fetch_asset(plan, io=_null_io())

    # elsevier_sd 无 DISCOVER/ENUMERATE（AdapterBase 兜底）。
    with pytest.raises(CapabilityNotSupported):
        adapters["elsevier_sd"].discover_timeline(venue)
    with pytest.raises(CapabilityNotSupported):
        adapters["elsevier_sd"].enumerate_issue(venue, IssueRef(venue_id=venue.id))


def test_declared_stub_methods_are_not_implemented(
    adapters: dict[str, SourceAdapter], venue: VenueSpec
) -> None:
    # 声明了能力但 T1 未实现 —— 区别于 CapabilityNotSupported。
    # （openreview 已 Phase 2 落地为真实 adapter；此处只剩 crossref stub。）
    with pytest.raises(NotImplementedError):
        adapters["crossref"].discover_timeline(venue)
    with pytest.raises(NotImplementedError):
        adapters["crossref"].enumerate_issue(venue, IssueRef(venue_id=venue.id))


def test_mock_platform_methods_are_implemented_after_t6(
    adapters: dict[str, SourceAdapter], venue: VenueSpec
) -> None:
    # T6 落地：mock_platform 不再 NotImplementedError（区别于仍是 stub 的
    # crossref/openreview，见 test_declared_stub_methods_are_not_implemented）。
    # 语料细节（quirks 派生、故障注入等）见 tests/unit/test_mock_platform.py；
    # 这里只验证经 load_adapters() 拿到的实例确实可用。
    issues = list(adapters["mock_platform"].discover_timeline(venue))
    assert issues


# --- HttpClient 注入（bind_http_client / HttpClientConsumer 协议）--------------------------


def test_arxiv_is_http_client_consumer(adapters: dict[str, SourceAdapter]) -> None:
    """arxiv/openreview/pmlr/acl_anthology/cvf 实现 `HttpClientConsumer`；stub/mock 不实现。"""
    assert isinstance(adapters["arxiv"], HttpClientConsumer)
    assert isinstance(adapters["openreview"], HttpClientConsumer)
    assert isinstance(adapters["pmlr"], HttpClientConsumer)
    assert isinstance(adapters["acl_anthology"], HttpClientConsumer)
    assert not isinstance(adapters["mock_platform"], HttpClientConsumer)
    assert not isinstance(adapters["crossref"], HttpClientConsumer)


def test_bind_http_client_injects_only_consumers(adapters: dict[str, SourceAdapter]) -> None:
    """`bind_http_client` 只注入实现协议的 adapter，返回被注入的 id 列表。"""
    client = HttpClient(user_agent="PaperCrawler/test (personal research)")
    injected = bind_http_client(adapters, client)
    # 五个真实 http adapter；注入生效——_client() 返回被注入实例，不再惰性自建。
    assert set(injected) == {"arxiv", "openreview", "pmlr", "acl_anthology", "cvf"}
    # 注入生效：arxiv 的 _client() 返回被注入的实例，不再惰性自建。
    arxiv = adapters["arxiv"]
    pmlr = adapters["pmlr"]
    assert isinstance(arxiv, HttpClientConsumer)
    assert isinstance(pmlr, HttpClientConsumer)
    assert arxiv._client() is client  # type: ignore[attr-defined]
    assert pmlr._client() is client  # type: ignore[attr-defined]


class _NullIO:
    def write_stream(self, chunks: object) -> tuple[int, str]:
        return (0, "")


def _null_io() -> _NullIO:
    return _NullIO()
