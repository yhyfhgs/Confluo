"""adapter.py（§2.3）单测：注册发现、元数据完备、能力路由（Capability/NotImplemented）。"""

import pytest

from paper_crawler.adapter import SourceAdapter, load_adapters
from paper_crawler.errors import CapabilityNotSupported
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

EXPECTED_ADAPTER_IDS = {"mock_platform", "crossref", "openreview", "elsevier_sd"}
VALID_FAMILIES = {"open_access", "auth_gated", "aggregator"}


@pytest.fixture
def adapters() -> dict[str, SourceAdapter]:
    return load_adapters()


def test_load_adapters_discovers_four(adapters: dict[str, SourceAdapter]) -> None:
    # 三个内置 stub + mock（mock 亦经 entry point，覆盖同 id 不新增）。
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


def test_openreview_stub_attributes(adapters: dict[str, SourceAdapter]) -> None:
    openreview = adapters["openreview"]
    assert openreview.family == "open_access"
    assert openreview.default_rate.requests_per_minute == 30
    assert openreview.domains == ("api2.openreview.net",)


def test_elsevier_stub_attributes(adapters: dict[str, SourceAdapter]) -> None:
    elsevier = adapters["elsevier_sd"]
    assert elsevier.family == "auth_gated"
    assert elsevier.capabilities == Capability.RESOLVE | Capability.FETCH
    assert elsevier.auth_requirement is AuthLevel.INSTITUTIONAL
    assert elsevier.default_rate.requests_per_minute == 10
    assert elsevier.domains == ("www.sciencedirect.com",)


def test_healthcheck_defaults_healthy(adapters: dict[str, SourceAdapter]) -> None:
    report = adapters["crossref"].healthcheck()
    assert isinstance(report, HealthReport)
    assert report.healthy is True


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
    with pytest.raises(NotImplementedError):
        adapters["crossref"].discover_timeline(venue)
    with pytest.raises(NotImplementedError):
        adapters["openreview"].enumerate_issue(venue, IssueRef(venue_id=venue.id))


def test_mock_platform_methods_not_implemented_until_t6(
    adapters: dict[str, SourceAdapter], venue: VenueSpec
) -> None:
    with pytest.raises(NotImplementedError):
        adapters["mock_platform"].discover_timeline(venue)


class _NullIO:
    def write_stream(self, chunks: object) -> tuple[int, str]:
        return (0, "")


def _null_io() -> _NullIO:
    return _NullIO()
