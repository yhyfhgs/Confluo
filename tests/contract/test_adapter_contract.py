"""T2 契约测试（test-plan §1）：参数化遍历 `load_adapters()`，校验协议一致性。

全体 adapter 都要过的元数据完备性检查，以及——对声明了 contract case 的 adapter
（`mock_platform` 本地确定性；`arxiv`/`openreview`/`crossref`/`dblp`/`unpaywall`/
`elsevier_sd`/`wiley`/`oup_silverchair` 经 `httpx.MockTransport` 注入合成 fixture，
零真实网络）——DISCOVER→ENUMERATE→RESOLVE→FETCH 全链路产出合法性检查。
**Phase 4 T3 补强**：elsevier_sd 落地为真实 auth_gated adapter（RESOLVE|FETCH，
enumerate 走 crossref D-005）补 factory——resolve（entitlement 预检）+ fetch（%PDF）
转真实通过，仅 discover/enumerate 因无能力 skip（收窄 2）。
**Phase 4 T4**：oup_silverchair 是**首个 cookie 档 auth_gated 契约 case**（RESOLVE|FETCH）——
resolve/fetch 契约用 `_RESOLVE_ONLY_SAMPLE_PAPERS` 登记的 QJE DOI 样本 +
`_CONTRACT_SESSIONS`/`_session_for` 注入的假 session（其余源 session=None，行为逐字
不变）走通全链（注入 cookie supplier + landing_transport 零真实网络）；discover/enumerate
两测因缺能力 skip（+2）。**Phase 5 T5**：`aea` 是 RESOLVE-only offline adapter，但
`resolve_assets` 按设计**从不返回非空 `AssetPlan` 列表**（订阅刊 raise
`NO_ENTITLEMENT`、OA 刊返回空列表，两分支均不产平台资产计划——见
`adapters/aea/adapter.py` 模块 docstring 的"结构性诚实边界"论证），与本文件
`test_resolve_yields_nonempty_asset_plans` 的通用假设（"declared RESOLVE ⟹
resolve(sample) 产 ≥1 个 AssetPlan"）**结构性不相容**——不为它伪造一个能通过
断言但实际上不代表真实可执行取回路径的样本，故不登记 factory（不同于 openalex/s2
"无能力可契"的空集合 case；aea 是"有能力但契约形状不适用"，两者殊途同归都落
`_contract_case` 的兜底 skip 分支）。aea 自身 resolve_assets 两分支（raise
no_entitlement / 返回空列表）由 `tests/unit/test_aea_adapter.py` 直接覆盖。**Phase 5
T6**：`econsoc` 全四位 case 走 TE 全链（open_access，无 auth 门控样本注入），不新增
skip。当前契约 skip 合计 **25**：openalex/s2/aea 各 4（无契可契，原因分述如上）+
crossref/dblp 各 2（无 RESOLVE/FETCH）+ unpaywall 3（仅 RESOLVE）+ elsevier_sd 2 +
oup_silverchair 2（各自无 DISCOVER/ENUMERATE）+ wiley 2 = 25（实跑 120 passed / 25
skipped——Phase 5 T6 econsoc 全四位 case 走 TE 全链，+8 passed 无新增 skip）。

契约的 enumerate 计数口径按能力分层：声明了权威计数（`IssueRef.paper_count_claimed`）
的 adapter（mock）严格等值；未声明的（arxiv 月度桶、dblp 会议届——预印本/会议无权威
"期"计数）只要求"至少产出且每篇形态合法"。这不是放宽契约，而是契约对"有/无权威计数"
两类源的正确表述。crossref 声明了权威计数（facet 逐年计数），contract fixture 为此
自建一组数值自洽的最小合成响应（1 年/1 篇），不复用 `tests/fixtures/crossref/` 下
adapter 自身单测的既有 fixture——那些文件的 `paper_count_claimed`（如 46）与其
enumerate 页面的有效记录数（如 3，因单测刻意混入跳过样例）并不相等，直接挪用会在
本契约的严格等值断言上装配性失败，同 acl_anthology/cvf/neurips 已有先例（那三个
contract case 同样是自建最小合成响应，不复用各自 adapter 单测 fixture）。

resolve/fetch 契约测试取"样本 paper"的口径按 adapter 形状分层（`_sample_paper_for`）：
多数 adapter 是 DISCOVER→ENUMERATE→RESOLVE→FETCH 全链路（样本 paper 从真实
discover→enumerate 产出取得）；unpaywall 这类 RESOLVE-only 聚合源（按外部已知 DOI
定位 OA 副本，不产出自己的论文列表——`_RESOLVE_ONLY_SAMPLE_PAPERS` 登记）改用直接
登记的样本 paper，不强行伪造它并不具备的 DISCOVER/ENUMERATE。

未声明能力时的兜底行为（`CapabilityNotSupported`）用一个不声明任何能力的最小
`FakeAdapter` 独立验证——这是 `AdapterBase` 本身的契约，不依赖具体哪个 adapter
恰好缺哪个能力。
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

import httpx
import pytest

from helpers import (
    FakeFetchIO,
    make_aaai_venue,
    make_acl_anthology_venue,
    make_arxiv_venue,
    make_crossref_venue,
    make_cvf_venue,
    make_econsoc_teqe_venue,
    make_elsevier_venue,
    make_mock_venue,
    make_neurips_venue,
    make_openreview_venue,
    make_oup_venue,
    make_pmlr_venue,
    make_wiley_venue,
)
from helpers.aaai_fixtures import fixture_bytes as aaai_fixture_bytes
from helpers.arxiv_fixtures import fixture_bytes
from helpers.dblp_fixtures import fixture_bytes as dblp_fixture_bytes
from helpers.dblp_fixtures import make_dblp_venue
from helpers.econsoc_fixtures import fixture_bytes as econsoc_fixture_bytes
from helpers.oup_silverchair_fixtures import landing_transport, oup_fixture, static_cookie_supplier
from helpers.pmlr_fixtures import fixture_bytes as pmlr_fixture_bytes
from helpers.unpaywall_fixtures import fixture_bytes as unpaywall_fixture_bytes
from paper_crawler.adapter import AdapterBase, AdapterFamily, SourceAdapter, load_adapters
from paper_crawler.adapters.aaai_ojs.adapter import AaaiOjsAdapter
from paper_crawler.adapters.acl_anthology.adapter import AclAnthologyAdapter
from paper_crawler.adapters.arxiv.adapter import ArxivAdapter
from paper_crawler.adapters.crossref.adapter import CrossrefAdapter
from paper_crawler.adapters.cvf.adapter import CVFAdapter
from paper_crawler.adapters.dblp.adapter import DblpAdapter
from paper_crawler.adapters.econsoc.adapter import EconsocAdapter
from paper_crawler.adapters.elsevier_sd.adapter import ElsevierScienceDirectAdapter
from paper_crawler.adapters.neurips_proceedings.adapter import NeuripsProceedingsAdapter
from paper_crawler.adapters.openreview.adapter import OpenReviewAdapter
from paper_crawler.adapters.oup_silverchair.adapter import OupSilverchairAdapter
from paper_crawler.adapters.pmlr.adapter import PmlrAdapter
from paper_crawler.adapters.unpaywall.adapter import UnpaywallAdapter
from paper_crawler.adapters.wiley.adapter import TDM_TOKEN_HEADER, WileyAdapter
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
    SessionBackend,
    SessionHandle,
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


def _econsoc_contract_handler(request: httpx.Request) -> httpx.Response:
    """econsoc（TE）契约链的 MockTransport：OJS OAI 首页/续页（econtheory.org）→ 合成 fixture；
    econometricsociety.org 落地页 → galley 链 fixture；galley `/file/*.PDF` → %PDF。

    全链路 discover（volume_map 首个=2006）→ enumerate(OAI, DOI 后缀+dc:date 年过滤)→
    resolve(GET 落地页抽 galley)→ fetch(%PDF)。TE 是 econsoc 全四位面（ECMA 走 crossref、
    只 RESOLVE|FETCH，非契约全链 case——用 TE 覆盖 econsoc 契约链）。
    """
    if request.url.host == "econtheory.org":  # OJS OAI-PMH
        if "resumptionToken" in request.url.params:
            return httpx.Response(
                200, content=econsoc_fixture_bytes("02_oai_listrecords_page2.xml")
            )
        return httpx.Response(200, content=econsoc_fixture_bytes("01_oai_listrecords_page1.xml"))
    if "/file/" in request.url.path:  # galley PDF（econometricsociety.org/.../file/{file}.PDF）
        return httpx.Response(200, content=_CONTRACT_PDF)
    # econometricsociety.org/doi/{DOI} 落地页 → galley 链 fixture。
    return httpx.Response(200, content=econsoc_fixture_bytes("03_landing_with_galley.html"))


def _econsoc_case() -> tuple[SourceAdapter, VenueSpec]:
    transport = httpx.MockTransport(_econsoc_contract_handler)
    client = HttpClient(user_agent=_CONTRACT_UA, transport=transport)
    return EconsocAdapter(http=client), make_econsoc_teqe_venue("te")


# crossref 契约链的 MockTransport：facet 年计数（discover） → cursor works 页
# （enumerate）。**自建最小合成响应**（不复用 `tests/fixtures/crossref/` 下 adapter
# 自身单测的既有 fixture）——crossref 声明权威计数（`paper_count_claimed`），本契约
# 套件对声明权威计数的 adapter 做严格等值断言（`len(papers) == first_issue.
# paper_count_claimed`），既有单测 fixture 的计数值（如 46）与其页面有效记录数
# （如 3，单测刻意混入跳过样例）并不相等，直接挪用会在该断言上装配性失败——见模块
# 顶部 docstring。1 年/1 篇是满足严格等值的最小自洽取值；`next-cursor: null` 使
# enumerate 恰 1 请求即终止（不需要额外一页空结果）。
_CROSSREF_CONTRACT_FACET = (
    b'{"status":"ok","message-type":"work-list","message":{'
    b'"total-results":1,"facets":{"published":{"values":{"2024":1}}}}}'
)
_CROSSREF_CONTRACT_WORKS_PAGE = (
    b'{"status":"ok","message-type":"work-list","message":{'
    b'"total-results":1,"next-cursor":null,"items-per-page":1,"items":[{'
    b'"DOI":"10.1234/contract.paper","title":["Contract Test Paper"],'
    b'"author":[{"given":"Contract","family":"Author","sequence":"first"}],'
    b'"published-print":{"date-parts":[[2024,1]]}}]}}'
)


def _crossref_contract_handler(request: httpx.Request) -> httpx.Response:
    if request.url.params.get("facet"):
        return httpx.Response(200, content=_CROSSREF_CONTRACT_FACET)
    return httpx.Response(200, content=_CROSSREF_CONTRACT_WORKS_PAGE)


def _crossref_case() -> tuple[SourceAdapter, VenueSpec]:
    transport = httpx.MockTransport(_crossref_contract_handler)
    client = HttpClient(user_agent=_CONTRACT_UA, transport=transport)
    return CrossrefAdapter(http=client), make_crossref_venue()


def _dblp_contract_handler(request: httpx.Request) -> httpx.Response:
    """dblp 契约链的 MockTransport：conf 索引页（discover） → 卷 XML（enumerate）。

    复用 adapter 自身单测的既有 fixture（`10_volume_xml_bht_schema_normal.xml`，非
    1828 条真实全量的 `11_..._full_real_icml2023.xml`——契约只需"链路走通+形态合法"，
    无需大体量）：dblp **不**声明权威计数（`IssueRef.paper_count_claimed` 恒 None），
    不受 crossref 那种严格等值断言约束，故可以像 pmlr/neurips 先例一样不区分请求的
    具体年份/卷号，任何 `.xml` 请求都回同一份卷内容。
    """
    if request.url.path.endswith(".xml"):
        body = dblp_fixture_bytes("10_volume_xml_bht_schema_normal.xml")
        return httpx.Response(200, content=body)
    return httpx.Response(200, content=dblp_fixture_bytes("01_conf_index_normal.html"))


def _dblp_case() -> tuple[SourceAdapter, VenueSpec]:
    transport = httpx.MockTransport(_dblp_contract_handler)
    client = HttpClient(user_agent=_CONTRACT_UA, transport=transport)
    return DblpAdapter(http=client), make_dblp_venue()


def _elsevier_contract_handler(request: httpx.Request) -> httpx.Response:
    """elsevier_sd 契约链的 MockTransport：entitlement 端点 → entitled:true；article → %PDF。

    合成响应（零网络）：entitlement 预检返有权 → resolve 产 1 个 PDF AssetPlan（url_strategy=
    api_call）；article 取回（httpAccept=application/pdf）→ %PDF，使 resolve→fetch 链有产出。
    elsevier_sd 无 DISCOVER/ENUMERATE（走 crossref，D-005）——样本 paper 经
    `_RESOLVE_ONLY_SAMPLE_PAPERS` 直接登记（同 unpaywall 先例）。
    """
    if "/entitlement/" in request.url.path:
        body = (
            b'{"entitlement-response":{"document-entitlement":{"@status":"found","entitled":true}}}'
        )
        return httpx.Response(200, content=body)
    return httpx.Response(200, content=_CONTRACT_PDF)


def _elsevier_case() -> tuple[SourceAdapter, VenueSpec]:
    transport = httpx.MockTransport(_elsevier_contract_handler)
    client = HttpClient(user_agent=_CONTRACT_UA, transport=transport)
    adapter = ElsevierScienceDirectAdapter(http=client)
    adapter.set_api_key(
        "contract-key"
    )  # 装配期专属 client + key 门控（凭证隔离，见 adapter docstring）
    return adapter, make_elsevier_venue()


def _oup_silverchair_case() -> tuple[SourceAdapter, VenueSpec]:
    """oup_silverchair 契约链：**首个 auth_gated 契约 case**（RESOLVE|FETCH，无 DISCOVER/
    ENUMERATE——resolve/fetch 契约用 `_RESOLVE_ONLY_SAMPLE_PAPERS` 登记的 QJE DOI 样本 +
    `_CONTRACT_SESSIONS` 注入的假 session）。

    专属 client 经注入的 `static_cookie_supplier` + `landing_transport`（doi.org→302→全文页
    fixture；article-pdf→%PDF）达成零真实网络：resolve 解析 citation_pdf_url→AssetPlan(PDF)，
    fetch 直取 %PDF。session 由通用 resolve/fetch 契约测试经 `_session_for` 线程注入。
    """
    _, _, final_url, body = oup_fixture("04_fulltext_logged_in")
    transport = landing_transport(final_url, 200, {}, body)
    adapter = OupSilverchairAdapter(cookie_supplier=static_cookie_supplier(), transport=transport)
    return adapter, make_oup_venue()


def _unpaywall_contract_handler(request: httpx.Request) -> httpx.Response:
    """unpaywall 契约链的 MockTransport：唯一端点 `GET /v2/{doi}` → 复用 adapter 自身
    单测的既有 fixture（`02_direct_pdf_hit_hybrid.json`：`is_oa=true` 且
    `best_oa_location.url_for_pdf` 非空，产出恰 1 个 `AssetPlan`）。unpaywall
    `parse_response` 以调用方传入的 DOI 为键、不读响应体自带的 `doi` 字段（§5.5），
    故复用哪个 DOI 的 fixture 与契约测试实际查询的样本 DOI 是否一致无关紧要。
    """
    return httpx.Response(200, content=unpaywall_fixture_bytes("02_direct_pdf_hit_hybrid.json"))


def _unpaywall_case() -> tuple[SourceAdapter, VenueSpec]:
    transport = httpx.MockTransport(_unpaywall_contract_handler)
    client = HttpClient(user_agent=_CONTRACT_UA, transport=transport)
    # unpaywall `resolve_assets` 不读 `venue` 参数（跨 venue 的 OA 兜底源，adapter
    # 模块 docstring）——复用泛用 mock venue 即可，同 `test_unpaywall_adapter.py`
    # 既有先例（该文件的 resolve 测试同样直接 `from helpers import make_mock_venue`）。
    return UnpaywallAdapter(http=client), make_mock_venue()


def _wiley_contract_handler(request: httpx.Request) -> httpx.Response:
    """wiley 契约链的 MockTransport：TDM 端点 → %PDF（`Wiley-TDM-Client-Token` 头随专属
    client 发出，凭证隔离——同 s2 契约不校验头值，只需链路走通 + 形态合法）。"""
    return httpx.Response(200, content=_CONTRACT_PDF)


def _wiley_case() -> tuple[SourceAdapter, VenueSpec]:
    # wiley 是 token 门控 adapter（无 token → resolve/fetch AuthRequired）——契约链需注入
    # 携 `Wiley-TDM-Client-Token` 头的**专属** client + set_token，模拟 CLI 装配期的凭证
    # 隔离结果（同 s2 `test_enrich_batch_x_api_key_header_present_on_request` 先例）。
    transport = httpx.MockTransport(_wiley_contract_handler)
    client = HttpClient(
        user_agent=_CONTRACT_UA,
        transport=transport,
        extra_headers={TDM_TOKEN_HEADER: "contract-token"},
    )
    return WileyAdapter(http=client, token="contract-token"), make_wiley_venue()


# 无 DISCOVER/ENUMERATE 的 adapter（unpaywall=RESOLVE-only；wiley/elsevier_sd=RESOLVE|FETCH，
# enumerate 走 crossref D-005）：resolve/fetch 契约测试不能像全链路 adapter 那样从
# discover→enumerate 派生样本 paper（那两个能力它们没有），改直接登记现成样本——见
# `_sample_paper_for`。elsevier_sd 样本用真实 JFE DOI（其 resolve 只读 paper.doi）。
_RESOLVE_ONLY_SAMPLE_PAPERS: dict[str, PaperStub] = {
    "unpaywall": PaperStub(
        title="Contract Test Paper (Resolve-Only Adapter)",
        identifiers=(("doi", "10.9999/contract.unpaywall"),),
    ),
    # wiley DOI 前缀（10.1111，Journal of Finance 形态）——TDM URL 由 resolve 从此 DOI 构造。
    "wiley": PaperStub(
        title="Contract Test Paper (Wiley TDM Adapter)",
        identifiers=(("doi", "10.1111/contract.wiley"),),
    ),
    "elsevier_sd": PaperStub(
        title="Contract Test Paper (Elsevier)",
        identifiers=(("doi", "10.1016/j.jfineco.2011.03.021"),),
    ),
    # oup_silverchair 是 auth_gated（RESOLVE|FETCH），无 DISCOVER/ENUMERATE——按 QJE DOI
    # 定位落地页（US-9 样例前缀 10.1093/qje/…），同 unpaywall 直接登记样本。
    "oup_silverchair": PaperStub(
        title="A Synthetic Placeholder Article",
        identifiers=(("doi", "10.1093/qje/qjae044"),),
    ),
}

# auth_gated adapter 的 resolve/fetch 契约需要 session（其余源 session=None，行为不变）。
# 首个 auth_gated 契约 case=oup_silverchair；假 session 配合注入的 cookie supplier 走通全链。
_CONTRACT_SESSIONS: dict[str, SessionHandle] = {
    "oup_silverchair": SessionHandle(
        provider_id="oup@campus",
        backend=SessionBackend.HTTPX_COOKIES,
        payload_ref="oup-contract-state",
        established_at=datetime(2026, 7, 23, tzinfo=UTC),
    ),
}


def _session_for(adapter_id: str) -> SessionHandle | None:
    """契约 resolve/fetch 的 session 入参：仅 auth_gated case 有值，其余 None（默认，不变）。"""
    return _CONTRACT_SESSIONS.get(adapter_id)


def _sample_paper_for(adapter_id: str, adapter: SourceAdapter, venue: VenueSpec) -> PaperStub:
    """resolve/fetch 契约测试的样本 paper：`_RESOLVE_ONLY_SAMPLE_PAPERS` 登记的
    adapter（无 DISCOVER/ENUMERATE）直接用登记样本；其余（有 DISCOVER+ENUMERATE 的
    全链路 adapter）沿用既有口径——从真实 discover→enumerate 产出取第一条。"""
    sample = _RESOLVE_ONLY_SAMPLE_PAPERS.get(adapter_id)
    if sample is not None:
        return sample
    first_issue = next(iter(adapter.discover_timeline(venue)))
    return next(iter(adapter.enumerate_issue(venue, first_issue)))


# adapter_id -> (adapter, venue) 工厂。只有此处登记的 adapter 会跑完整能力链路检查；
# 其余一律 pytest.skip——见模块顶部 docstring 的 skip 分解。pmlr 无 stub 阶段（不同于
# arxiv 曾有 T1-T4 的 stub 过渡期）——直接新增一行即完整接入契约套件。
# **`aea` 刻意不登记**（Phase 5 T5）：不是"缺能力"（它声明了 RESOLVE），而是
# `resolve_assets` 按设计从不产出非空 `AssetPlan`（模块 docstring 展开）——本契约的
# `test_resolve_yields_nonempty_asset_plans` 断言对它结构性不适用，登记一个会强行
# 通过但不代表真实取回路径的 factory 违背"契约反映真实行为"的初衷。
_CONTRACT_CASES: dict[str, Callable[[], tuple[SourceAdapter, VenueSpec]]] = {
    "mock_platform": _mock_case,
    "arxiv": _arxiv_case,
    "openreview": _openreview_case,
    "pmlr": _pmlr_case,
    "acl_anthology": _acl_anthology_case,
    "cvf": _cvf_case,
    "aaai_ojs": _aaai_case,
    "neurips_proceedings": _neurips_proceedings_case,
    "econsoc": _econsoc_case,
    "crossref": _crossref_case,
    "dblp": _dblp_case,
    "unpaywall": _unpaywall_case,
    "wiley": _wiley_case,
    "elsevier_sd": _elsevier_case,
    "oup_silverchair": _oup_silverchair_case,
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
        pytest.skip(
            reason=(
                f"no contract case registered for {adapter_id!r}: either duck-typed "
                "enrich-only with an empty capability set (openalex/s2, capabilities="
                "Capability(0), T6 — do not participate in this protocol by design) or "
                "a declared RESOLVE that structurally never returns a nonempty AssetPlan "
                "(aea, T5 — see _CONTRACT_CASES module comment); see module docstring for "
                "the full skip breakdown"
            )
        )
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
        # 声明权威计数者（mock、crossref facet 逐年计数）：严格等值。
        assert len(papers) == first_issue.paper_count_claimed
    else:
        # 无权威计数者（arxiv 月度桶、dblp 会议届）：至少产出（形态合法性由下方逐篇断言）。
        assert papers
    for paper in papers:
        assert isinstance(paper, PaperStub)
        assert len(paper.identifiers) >= 1


def test_resolve_yields_nonempty_asset_plans(adapter_id: str) -> None:
    adapter, venue = _contract_case(adapter_id)
    if Capability.RESOLVE not in adapter.capabilities:
        pytest.skip(reason=f"{adapter_id} lacks RESOLVE")

    paper = _sample_paper_for(adapter_id, adapter, venue)
    plans = adapter.resolve_assets(venue, paper, session=_session_for(adapter_id))

    assert plans
    assert all(isinstance(plan, AssetPlan) for plan in plans)


def test_fetch_via_fake_io_succeeds_and_writes_pdf_magic_bytes(adapter_id: str) -> None:
    adapter, venue = _contract_case(adapter_id)
    if Capability.FETCH not in adapter.capabilities:
        pytest.skip(reason=f"{adapter_id} lacks FETCH")

    paper = _sample_paper_for(adapter_id, adapter, venue)
    session = _session_for(adapter_id)
    plan = adapter.resolve_assets(venue, paper, session=session)[0]

    io = FakeFetchIO()
    result = adapter.fetch_asset(plan, io, session=session)

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
