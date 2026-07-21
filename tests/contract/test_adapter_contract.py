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
    make_aaai_venue,
    make_acl_anthology_venue,
    make_arxiv_venue,
    make_cvf_venue,
    make_mock_venue,
    make_neurips_venue,
    make_openreview_venue,
    make_pmlr_venue,
)
from helpers.aaai_fixtures import fixture_bytes as aaai_fixture_bytes
from helpers.arxiv_fixtures import fixture_bytes
from helpers.pmlr_fixtures import fixture_bytes as pmlr_fixture_bytes
from paper_crawler.adapter import AdapterBase, AdapterFamily, SourceAdapter, load_adapters
from paper_crawler.adapters.aaai_ojs.adapter import AaaiOjsAdapter
from paper_crawler.adapters.acl_anthology.adapter import AclAnthologyAdapter
from paper_crawler.adapters.arxiv.adapter import ArxivAdapter
from paper_crawler.adapters.cvf.adapter import CVFAdapter
from paper_crawler.adapters.neurips_proceedings.adapter import NeuripsProceedingsAdapter
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


# acl_anthology 契约链的 MockTransport：git-tree 清单只含一年（2023.emnlp.xml）→
# discover 首个 issue 即该年；enumerate 读回一篇最小合法 paper（其余 raw 候选/findings
# 文件 404→legal-empty，正常空跳过）；resolve/fetch 走标准 pdf plan → %PDF。
_ACL_ANTHOLOGY_CONTRACT_TREE = (
    b'{"truncated": false, "tree": [{"path": "data/xml/2023.emnlp.xml", "type": "blob"}]}'
)
_ACL_ANTHOLOGY_CONTRACT_COLLECTION = (
    b"<collection id='2023.emnlp'><volume id='main' type='proceedings'>"
    b"<meta><year>2023</year><venue>emnlp</venue></meta>"
    b"<paper id='1'><title>Contract Test Paper</title><bibkey>contract-2023</bibkey>"
    b"<url hash='aaaaaaaa'>2023.emnlp-main.1</url></paper>"
    b"</volume></collection>"
)


def _acl_anthology_contract_handler(request: httpx.Request) -> httpx.Response:
    if request.url.host == "api.github.com":
        return httpx.Response(200, content=_ACL_ANTHOLOGY_CONTRACT_TREE)
    if request.url.host == "raw.githubusercontent.com":
        if request.url.path.endswith("2023.emnlp.xml"):
            return httpx.Response(200, content=_ACL_ANTHOLOGY_CONTRACT_COLLECTION)
        return httpx.Response(404, content=b"synthetic 404")  # legacy/findings candidates
    if request.url.path.endswith(".pdf"):
        return httpx.Response(200, content=_CONTRACT_PDF)
    return httpx.Response(404, content=b"synthetic 404")


def _acl_anthology_case() -> tuple[SourceAdapter, VenueSpec]:
    transport = httpx.MockTransport(_acl_anthology_contract_handler)
    client = HttpClient(user_agent=_CONTRACT_UA, transport=transport)
    return AclAnthologyAdapter(http=client), make_acl_anthology_venue()


def _cvf_contract_handler(request: httpx.Request) -> httpx.Response:
    """cvf 契约链的 MockTransport：任意年份 bare GET → 单条目 flat 页 → pdf 取回 %PDF。

    合成响应（零真实网络）：单条目自带 pdf href，使 discover→enumerate→resolve→fetch
    全链有产出，无需模拟双请求 day-landing 分支（该分支的单测覆盖见
    tests/unit/test_cvf_adapter.py）。`discover_timeline` 最早年为 2013，故本
    handler 实际模拟的是 flat era 响应——作者 hidden input 用真实的 `name="query"`
    （非 modern `?day=all` 专属的 `query_author`，2026-07-22 独立审查校正，见
    `parse._AUTHOR_INPUT_NAMES`）。
    """
    if request.url.path.endswith(".pdf"):
        return httpx.Response(200, content=_CONTRACT_PDF)
    html = (
        '<dt class="ptitle"><br><a href="/content/X/html/contract_paper.html">'
        "Contract Paper</a></dt>\n"
        '<dd><input type="hidden" name="query" value="Contract Author"></dd>\n'
        '<dd>[<a href="/content/X/papers/contract_paper.pdf">pdf</a>]</dd>\n'
    )
    return httpx.Response(200, content=f"<html><body><dl>{html}</dl></body></html>".encode())


def _cvf_case() -> tuple[SourceAdapter, VenueSpec]:
    transport = httpx.MockTransport(_cvf_contract_handler)
    client = HttpClient(user_agent=_CONTRACT_UA, transport=transport)
    return CVFAdapter(http=client, current_year=2026), make_cvf_venue()


def _aaai_contract_handler(request: httpx.Request) -> httpx.Response:
    """aaai_ojs 契约链的 MockTransport：OAI 首页/续页 → 合成 fixture；PDF download → %PDF。

    第一个 issue（discover 升序首个=2019/v33 历史届）走全库 2 页收割，enumerate 产出 v33
    记录，resolve 经 view→download 命中 /article/download/，fetch 取回 %PDF。
    """
    if "/article/download/" in request.url.path:
        return httpx.Response(200, content=_CONTRACT_PDF)
    if "resumptionToken" in request.url.params:
        return httpx.Response(200, content=aaai_fixture_bytes("02_oai_listrecords_page2.xml"))
    return httpx.Response(200, content=aaai_fixture_bytes("01_oai_listrecords_page1.xml"))


def _aaai_case() -> tuple[SourceAdapter, VenueSpec]:
    transport = httpx.MockTransport(_aaai_contract_handler)
    client = HttpClient(user_agent=_CONTRACT_UA, transport=transport)
    return AaaiOjsAdapter(http=client), make_aaai_venue()


_NEURIPS_YEAR_PAGE = (
    b'<html><body><ul class="paper-list">'
    b'<li class="" data-track="none"><div class="paper-content">'
    b'<a title="paper title" href="/paper_files/paper/2021/hash/'
    b'000c076c390a4c357313fca29e390ece-Abstract.html">Contract Test Paper</a>'
    b'<span class="paper-authors">Contract Author</span>'
    b"</div></li></ul></body></html>"
)


def _neurips_proceedings_contract_handler(request: httpx.Request) -> httpx.Response:
    """neurips_proceedings 契约链的 MockTransport：年页 → 合成单条目页；PDF 取回 → %PDF。

    不区分请求的具体年份（2021/2022 等）——contract 只关心链路机制是否走通，年页
    内容与被请求年份是否语义一致由 T5 adapter 单测/T4 集成测试覆盖（同 pmlr 先例）。
    """
    if str(request.url).endswith(".pdf"):
        return httpx.Response(200, content=_CONTRACT_PDF)
    return httpx.Response(200, content=_NEURIPS_YEAR_PAGE)


def _neurips_proceedings_case() -> tuple[SourceAdapter, VenueSpec]:
    transport = httpx.MockTransport(_neurips_proceedings_contract_handler)
    client = HttpClient(user_agent=_CONTRACT_UA, transport=transport)
    return NeuripsProceedingsAdapter(http=client), make_neurips_venue()


# adapter_id -> (adapter, venue) 工厂。只有此处登记的 adapter 会跑完整能力链路检查；
# 其余（stub）adapter 一律 pytest.skip（stub until Phase 3/4）。pmlr 无 stub 阶段
# （不同于 arxiv 曾有 T1-T4 的 stub 过渡期）——直接新增一行即完整接入契约套件。
_CONTRACT_CASES: dict[str, Callable[[], tuple[SourceAdapter, VenueSpec]]] = {
    "mock_platform": _mock_case,
    "arxiv": _arxiv_case,
    "openreview": _openreview_case,
    "pmlr": _pmlr_case,
    "acl_anthology": _acl_anthology_case,
    "cvf": _cvf_case,
    "aaai_ojs": _aaai_case,
    "neurips_proceedings": _neurips_proceedings_case,
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
