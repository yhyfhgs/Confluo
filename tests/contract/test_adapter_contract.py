"""T2 契约测试（test-plan §1）：参数化遍历 `load_adapters()`，校验协议一致性。

全体 adapter 都要过的元数据完备性检查，以及——对声明了 contract case 的 adapter
（`mock_platform` 本地确定性；`arxiv`/`openreview` 经 `httpx.MockTransport` 注入合成
fixture，零真实网络）——DISCOVER→ENUMERATE→RESOLVE→FETCH 全链路产出合法性检查。剩余
真实站点 stub（crossref/elsevier_sd）在 Phase 3/4 前 `pytest.skip`（各 4 条，共 8 skip）。

契约的 enumerate 计数口径按能力分层：声明了权威计数（`IssueRef.paper_count_claimed`）
的 adapter（mock）严格等值；未声明的（arxiv 月度桶——预印本无权威"期"计数）只要求
"至少产出且每篇形态合法"。这不是放宽契约，而是契约对"有/无权威计数"两类源的正确表述。

未声明能力时的兜底行为（`CapabilityNotSupported`）用一个不声明任何能力的最小
`FakeAdapter` 独立验证——这是 `AdapterBase` 本身的契约，不依赖具体哪个 adapter
恰好缺哪个能力。
"""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from helpers import (
    FakeFetchIO,
    make_arxiv_venue,
    make_mock_venue,
    make_openreview_venue,
    make_pmlr_venue,
)
from helpers.arxiv_fixtures import fixture_bytes
from helpers.pmlr_fixtures import fixture_bytes as pmlr_fixture_bytes
from paper_crawler.adapter import AdapterBase, AdapterFamily, SourceAdapter, load_adapters
from paper_crawler.adapters.arxiv.adapter import ArxivAdapter
from paper_crawler.adapters.openreview.adapter import OpenReviewAdapter
from paper_crawler.adapters.pmlr.adapter import PmlrAdapter
from paper_crawler.errors import CapabilityNotSupported
from paper_crawler.http import HttpClient
from paper_crawler.types import (
    AssetKind,
    AssetPlan,
    AuthLevel,
    Capability,
    IssueRef,
    PaperStub,
    RatePolicy,
    VenueSpec,
)

_CONTRACT_UA = "PaperCrawler/test (personal research; mailto:test@example.com)"

# 一个最小的合成 PDF（首字节 %PDF- 魔数，供 fetch 契约的 %PDF 断言）。
_CONTRACT_PDF = b"%PDF-1.4\n% contract\n" + b"0" * 512 + b"\n%%EOF\n"


def _mock_case() -> tuple[SourceAdapter, VenueSpec]:
    return load_adapters()["mock_platform"], make_mock_venue()


def _arxiv_contract_handler(request: httpx.Request) -> httpx.Response:
    """arxiv 契约链的 MockTransport：pdf 取回 → %PDF；OAI 首页/续页 → 合成 fixture。"""
    if "/pdf/" in request.url.path:
        return httpx.Response(200, content=_CONTRACT_PDF)
    if "resumptionToken" in request.url.params:
        return httpx.Response(200, content=fixture_bytes("02_oai_listrecords_page2.xml"))
    return httpx.Response(200, content=fixture_bytes("02_oai_listrecords_page1.xml"))


def _arxiv_case() -> tuple[SourceAdapter, VenueSpec]:
    transport = httpx.MockTransport(_arxiv_contract_handler)
    client = HttpClient(user_agent=_CONTRACT_UA, transport=transport)
    return ArxivAdapter(http=client), make_arxiv_venue()


def _openreview_contract_handler(request: httpx.Request) -> httpx.Response:
    """openreview 契约链的 MockTransport：groups 判 v2 → notes（含 pdf）→ pdf 取回 %PDF。

    合成响应（零真实网络）：groups 带 domain→v2；notes 返回一条接收+含 pdf 字段的 note，
    使 discover→enumerate→resolve→fetch 全链有产出（无 pdf/0 plan 的分支由单测覆盖）。
    """
    if "/groups" in request.url.path:
        vid = request.url.params.get("id", "ICLR.cc/2024/Conference")
        body = f'{{"groups":[{{"id":"{vid}","domain":"{vid}"}}],"count":1}}'
        return httpx.Response(200, content=body.encode("utf-8"))
    if "/pdf" in request.url.path:
        return httpx.Response(200, content=_CONTRACT_PDF)
    # /notes：一条接收（venueid==主会 id）+ pdf 字段。
    vid = request.url.params.get("content.venueid", "ICLR.cc/2024/Conference")
    note = (
        '{"notes":[{"id":"contract1","forum":"contract1","content":{'
        '"title":{"value":"Contract Paper"},'
        f'"venueid":{{"value":"{vid}"}},'
        '"pdf":{"value":"/pdf/contract.pdf"}}}],"count":1}'
    )
    return httpx.Response(200, content=note.encode("utf-8"))


def _openreview_case() -> tuple[SourceAdapter, VenueSpec]:
    transport = httpx.MockTransport(_openreview_contract_handler)
    client = HttpClient(user_agent=_CONTRACT_UA, transport=transport)
    return OpenReviewAdapter(http=client), make_openreview_venue()


def _pmlr_contract_handler(request: httpx.Request) -> httpx.Response:
    """pmlr 契约链的 MockTransport：卷 index 页 → 合成 fixture；PDF 取回 → %PDF。

    不区分请求的具体卷号（v202/v235 等）——contract 只关心链路机制是否走通，
    fixture 内容与被请求的卷号是否语义一致由 T5 adapter 单测/T4 集成测试覆盖。
    """
    if str(request.url).endswith(".pdf"):
        return httpx.Response(200, content=_CONTRACT_PDF)
    return httpx.Response(200, content=pmlr_fixture_bytes("01_volume_index_normal.html"))


def _pmlr_case() -> tuple[SourceAdapter, VenueSpec]:
    transport = httpx.MockTransport(_pmlr_contract_handler)
    client = HttpClient(user_agent=_CONTRACT_UA, transport=transport)
    return PmlrAdapter(http=client), make_pmlr_venue()


# adapter_id -> (adapter, venue) 工厂。只有此处登记的 adapter 会跑完整能力链路检查；
# 其余（stub）adapter 一律 pytest.skip（stub until Phase 3/4）。pmlr 无 stub 阶段
# （不同于 arxiv 曾有 T1-T4 的 stub 过渡期）——直接新增一行即完整接入契约套件。
_CONTRACT_CASES: dict[str, Callable[[], tuple[SourceAdapter, VenueSpec]]] = {
    "mock_platform": _mock_case,
    "arxiv": _arxiv_case,
    "openreview": _openreview_case,
    "pmlr": _pmlr_case,
}

ADAPTER_IDS = sorted(load_adapters())


@pytest.fixture
def adapters() -> dict[str, SourceAdapter]:
    return load_adapters()


@pytest.fixture(params=ADAPTER_IDS)
def adapter_id(request: pytest.FixtureRequest) -> str:
    return str(request.param)


def _contract_case(adapter_id: str) -> tuple[SourceAdapter, VenueSpec]:
    factory = _CONTRACT_CASES.get(adapter_id)
    if factory is None:
        pytest.skip(reason="no contract case (real-site stub deferred to Phase 3/4)")
    return factory()


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


# --- contract-case adapter：能力全链路 ------------------------------------------------


def test_discover_yields_nonempty_legal_issue_refs(adapter_id: str) -> None:
    adapter, venue = _contract_case(adapter_id)
    if Capability.DISCOVER not in adapter.capabilities:
        pytest.skip(reason=f"{adapter_id} lacks DISCOVER")

    issues = list(adapter.discover_timeline(venue))
    assert issues
    for issue in issues:
        assert isinstance(issue, IssueRef)
        assert issue.venue_id == venue.id


def test_enumerate_first_issue_yields_papers_with_identifiers(adapter_id: str) -> None:
    adapter, venue = _contract_case(adapter_id)
    if Capability.ENUMERATE not in adapter.capabilities:
        pytest.skip(reason=f"{adapter_id} lacks ENUMERATE")

    first_issue = next(iter(adapter.discover_timeline(venue)))
    papers = list(adapter.enumerate_issue(venue, first_issue))

    if first_issue.paper_count_claimed is not None:
        # 声明权威计数者（mock）：严格等值。
        assert len(papers) == first_issue.paper_count_claimed
    else:
        # 无权威计数者（arxiv 月度桶）：至少产出（形态合法性由下方逐篇断言）。
        assert papers
    for paper in papers:
        assert isinstance(paper, PaperStub)
        assert len(paper.identifiers) >= 1


def test_resolve_yields_nonempty_asset_plans(adapter_id: str) -> None:
    adapter, venue = _contract_case(adapter_id)
    if Capability.RESOLVE not in adapter.capabilities:
        pytest.skip(reason=f"{adapter_id} lacks RESOLVE")

    first_issue = next(iter(adapter.discover_timeline(venue)))
    paper = next(iter(adapter.enumerate_issue(venue, first_issue)))
    plans = adapter.resolve_assets(venue, paper)

    assert plans
    assert all(isinstance(plan, AssetPlan) for plan in plans)


def test_fetch_via_fake_io_succeeds_and_writes_pdf_magic_bytes(adapter_id: str) -> None:
    adapter, venue = _contract_case(adapter_id)
    if Capability.FETCH not in adapter.capabilities:
        pytest.skip(reason=f"{adapter_id} lacks FETCH")

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
