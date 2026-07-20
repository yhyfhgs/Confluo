"""T2 契约测试（test-plan §1）：参数化遍历 `load_adapters()`，校验协议一致性。

全体 adapter 都要过的元数据完备性检查，以及——对声明了 contract fixture 的
adapter（目前只有 `mock_platform`；真实站点 stub 在 Phase 2/3/4 前 `pytest.skip`）——
DISCOVER→ENUMERATE→RESOLVE→FETCH 全链路产出合法性检查。

未声明能力时的兜底行为（`CapabilityNotSupported`）用一个不声明任何能力的最小
`FakeAdapter` 独立验证——这是 `AdapterBase` 本身的契约，不依赖具体哪个 adapter
恰好缺哪个能力。
"""

from __future__ import annotations

import pytest

from helpers import FakeFetchIO, make_mock_venue
from paper_crawler.adapter import AdapterBase, AdapterFamily, SourceAdapter, load_adapters
from paper_crawler.errors import CapabilityNotSupported
from paper_crawler.types import (
    AssetKind,
    AssetPlan,
    AuthLevel,
    Capability,
    IssueRef,
    PaperStub,
    RatePolicy,
)

# adapter_id -> venue 工厂。只有此处登记的 adapter 会跑完整能力链路检查；
# 其余（stub）adapter 一律 pytest.skip（stub until Phase 2/3/4）。
_CONTRACT_VENUE_FACTORIES = {"mock_platform": make_mock_venue}

ADAPTER_IDS = sorted(load_adapters())


@pytest.fixture
def adapters() -> dict[str, SourceAdapter]:
    return load_adapters()


@pytest.fixture(params=ADAPTER_IDS)
def adapter_id(request: pytest.FixtureRequest) -> str:
    return str(request.param)


def _require_contract_fixture(adapter_id: str) -> None:
    if adapter_id not in _CONTRACT_VENUE_FACTORIES:
        pytest.skip(reason="stub until Phase 2/3/4")


# --- 全体 adapter：元数据完备性 -------------------------------------------------------


def test_adapter_id_is_nonempty_and_matches_registry_key(
    adapter_id: str, adapters: dict[str, SourceAdapter]
) -> None:
    assert adapter_id
    assert adapters[adapter_id].adapter_id == adapter_id


def test_family_is_a_legal_value(adapter_id: str, adapters: dict[str, SourceAdapter]) -> None:
    assert adapters[adapter_id].family in {"open_access", "auth_gated", "aggregator"}


def test_default_rate_source_note_is_nonempty(
    adapter_id: str, adapters: dict[str, SourceAdapter]
) -> None:
    assert adapters[adapter_id].default_rate.source_note != ""


def test_domains_is_a_nonempty_tuple_of_strings(
    adapter_id: str, adapters: dict[str, SourceAdapter]
) -> None:
    domains = adapters[adapter_id].domains
    assert isinstance(domains, tuple)
    assert domains
    assert all(isinstance(d, str) and d for d in domains)


# --- contract-fixture adapter：能力全链路 ----------------------------------------------


def test_discover_yields_nonempty_legal_issue_refs(
    adapter_id: str, adapters: dict[str, SourceAdapter]
) -> None:
    _require_contract_fixture(adapter_id)
    adapter = adapters[adapter_id]
    if Capability.DISCOVER not in adapter.capabilities:
        pytest.skip(reason=f"{adapter_id} lacks DISCOVER")

    venue = _CONTRACT_VENUE_FACTORIES[adapter_id]()
    issues = list(adapter.discover_timeline(venue))
    assert issues
    for issue in issues:
        assert isinstance(issue, IssueRef)
        assert issue.venue_id == venue.id


def test_enumerate_first_issue_yields_declared_paper_count_with_identifiers(
    adapter_id: str, adapters: dict[str, SourceAdapter]
) -> None:
    _require_contract_fixture(adapter_id)
    adapter = adapters[adapter_id]
    if Capability.ENUMERATE not in adapter.capabilities:
        pytest.skip(reason=f"{adapter_id} lacks ENUMERATE")

    venue = _CONTRACT_VENUE_FACTORIES[adapter_id]()
    first_issue = next(iter(adapter.discover_timeline(venue)))
    papers = list(adapter.enumerate_issue(venue, first_issue))

    assert first_issue.paper_count_claimed is not None
    assert len(papers) == first_issue.paper_count_claimed
    for paper in papers:
        assert isinstance(paper, PaperStub)
        assert len(paper.identifiers) >= 1


def test_resolve_yields_nonempty_asset_plans(
    adapter_id: str, adapters: dict[str, SourceAdapter]
) -> None:
    _require_contract_fixture(adapter_id)
    adapter = adapters[adapter_id]
    if Capability.RESOLVE not in adapter.capabilities:
        pytest.skip(reason=f"{adapter_id} lacks RESOLVE")

    venue = _CONTRACT_VENUE_FACTORIES[adapter_id]()
    first_issue = next(iter(adapter.discover_timeline(venue)))
    paper = next(iter(adapter.enumerate_issue(venue, first_issue)))
    plans = adapter.resolve_assets(venue, paper)

    assert plans
    assert all(isinstance(plan, AssetPlan) for plan in plans)


def test_fetch_via_fake_io_succeeds_and_writes_pdf_magic_bytes(
    adapter_id: str, adapters: dict[str, SourceAdapter]
) -> None:
    _require_contract_fixture(adapter_id)
    adapter = adapters[adapter_id]
    if Capability.FETCH not in adapter.capabilities:
        pytest.skip(reason=f"{adapter_id} lacks FETCH")

    venue = _CONTRACT_VENUE_FACTORIES[adapter_id]()
    first_issue = next(iter(adapter.discover_timeline(venue)))
    paper = next(iter(adapter.enumerate_issue(venue, first_issue)))
    plan = adapter.resolve_assets(venue, paper)[0]

    io = FakeFetchIO()
    result = adapter.fetch_asset(plan, io)

    assert result.ok is True
    assert io.data.startswith(b"%PDF")


# --- AdapterBase 兜底：未声明能力 → CapabilityNotSupported ------------------------------


class _FakeAdapter(AdapterBase):
    """不声明任何能力的最小 adapter，只为验证 `AdapterBase` 的兜底契约。"""

    adapter_id = "fake_contract_adapter"
    family: AdapterFamily = "open_access"
    capabilities = Capability(0)
    default_rate = RatePolicy(1, source_note="contract test fixture")
    auth_requirement = AuthLevel.NONE
    domains: tuple[str, ...] = ("fake.local",)


def test_adapter_base_raises_capability_not_supported_for_undeclared_methods() -> None:
    adapter = _FakeAdapter()
    venue = make_mock_venue()
    paper = PaperStub(title="T", identifiers=(("doi", "10.9999/x"),))
    plan = AssetPlan(kind=AssetKind.PDF, url="https://fake.local/x")

    with pytest.raises(CapabilityNotSupported):
        list(adapter.discover_timeline(venue))
    with pytest.raises(CapabilityNotSupported):
        list(adapter.enumerate_issue(venue, IssueRef(venue_id=venue.id)))
    with pytest.raises(CapabilityNotSupported):
        adapter.resolve_assets(venue, paper)
    with pytest.raises(CapabilityNotSupported):
        adapter.fetch_asset(plan, io=FakeFetchIO())
