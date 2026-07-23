"""aea 在线冒烟（Phase 5 T5；design/adapters/aea.md §8）。

**只写不跑**：在线层由 controller 收尾统一实跑（T7/T8，沿 crossref/oup/wiley 等既有
在线冒烟先例）。默认经 `addopts = -m 'not online'` 排除；显式 `uv run pytest
tests/online -m online` 才跑。硬预算 `MAX_REAL_REQUESTS = 5`（aea.md §8 逐字："crossref
AER ISSN facet 1 + 单条 DOI 1 + landing 1 ≤3"，另留 2 请求余量）；**`pubs.aeaweb.org`
零请求**（CF challenge 站点判罚已实测，红线不对抗，见 aea.md §1/§10 与站点勘察
"环境障碍甄别"段——不得再触，即便只是 HEAD 探针）。

**注**：`aea` adapter 自身 `resolve_assets` 全离线（`resolve_offline=True`），本身不
发任何真实网络请求——本文件验证的是 aea **消费**的两个真实网络面：① Crossref
元数据主干（`metadata_source: crossref`，D-005）对 AEA 8 刊 ISSN 的真实响应；②
`www.aeaweb.org` 发现层 landing 页的 citation_* meta（供未来字段补全评估，非本
adapter 当前必需路径）。

预算分配（5 请求）：
1. Crossref AER（`0002-8282`）facet 逐年计数——比对 D-019 风格锚点（site-survey §3
   `total-results=5643`，出版单调增长 → 断言 `≥5643`）。
2. Crossref 单条 DOI `10.1257/aer.20230344` lookup——比对 site-survey §3 字段
   （volume/issue/abstract 非空），并与本 adapter 自身 `parse.parse_doi` 的路由结果
   交叉核对（`venue_id == "aer"`）。
3. `www.aeaweb.org` landing 页（`/articles?id=10.1257/aer.20230344`）——确认
   `citation_doi`/`citation_pdf_url` 等 meta 键存在（site-survey §3/§4）。
4–5. **6 刊 [DOC] ISSN 部分核实**（aea.md §7 出处分级"实现期在线冒烟负逐一核实
   义务"）：`aeri`（2640-205X，最新创刊、催生编目误差风险最高）+ `jel`
   （0022-0515，老牌刊作对照锚）经 Crossref facet 请求验证"该 ISSN 确实在 Crossref
   注册且可枚举"（非验证刊名文本，只验证 ISSN 本身有效）。**范围声明**：本文件
   ≤5 预算下只能覆盖 6 刊中的 2 刊；`aej_macro`/`aej_micro`/`aej_applied`/
   `aej_policy` 仍为 [DOC] 未核实，留待后续在线预算批次（如 phase5-implementation-plan
   §3 汇总表给出的 ≤10 分配额度，超出本文件独立声明的 ≤5）——UPDATE_GOLDEN 纪律下
   此处如实标注缺口，不假装已完成全 6 刊核实。
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

from online.conftest import RealRequestBudget
from online.smoke_helpers import make_rate_limited_client
from paper_crawler.adapters.aea.adapter import AeaAdapter
from paper_crawler.adapters.aea.parse import parse_doi
from paper_crawler.adapters.crossref.adapter import CrossrefAdapter
from paper_crawler.http import HttpClient
from paper_crawler.types import VenueSpec

MAX_REAL_REQUESTS = 5

# site-survey §3（[LIVE] 2026-07-24）：AER total-results=5643（出版持续增长，故用下限）。
_AER_ISSN = "0002-8282"
_AER_TOTAL_FLOOR = 5643

# site-survey §3 单条字段实测（[LIVE]）：DOI/volume/issue 字段。abstract 存在性
# （has_abstract=True）比精确长度更稳（长度会随 Crossref 记录后续修订微调）。
_AER_SAMPLE_DOI = "10.1257/aer.20230344"
_AER_SAMPLE_VOLUME = "116"
_AER_SAMPLE_ISSUE = "7"

# aea.md §7"仅 catalog [DOC] 来源"6 刊中本文件预算内可核实的 2 刊（见模块 docstring
# 的范围声明）。
_PARTIAL_DOC_ISSN_CHECKS = {
    "aeri": "2640-205X",
    "jel": "0022-0515",
}

# `www.aeaweb.org` 发现层 landing 页（site-survey §2/§3 URL 形态："/articles?id={DOI}"）。
_LANDING_URL = f"https://www.aeaweb.org/articles?id={_AER_SAMPLE_DOI}"

# D-014 UA mailto 段（同 crossref/pmlr 等既有在线冒烟样板：从 env 取，缺失整文件
# skip——crossref polite pool 硬要求，且诚实标识本系统的联系方式）。
_CONTACT_EMAIL = os.environ.get("PAPER_CRAWLER_CONTACT_EMAIL", "")
if not _CONTACT_EMAIL:
    pytest.skip(
        "PAPER_CRAWLER_CONTACT_EMAIL not set (required for D-014 UA + Crossref polite pool)",
        allow_module_level=True,
    )


def _aer_venue(issn: str = _AER_ISSN) -> VenueSpec:
    return VenueSpec(
        id="aer",
        kind="journal",
        names={"full": "American Economic Review", "aliases": ["AER"]},
        field=["econ"],
        identifiers={"issn": [issn]},
        metadata_source="crossref",
        fulltext_source="aea",
        auth={"level": "institutional", "provider_hint": "aea"},
    )


@pytest.fixture(scope="session")
def crossref_client() -> Iterator[HttpClient]:
    """真实 HttpClient：UA 携真实 mailto（D-014，polite pool）+ crossref 自有限速器。"""
    client = make_rate_limited_client(
        domains=CrossrefAdapter.domains,
        default_rate=CrossrefAdapter.default_rate,
        contact_email=_CONTACT_EMAIL,
    )
    try:
        yield client
    finally:
        client.close()


@pytest.fixture(scope="session")
def aeaweb_client() -> Iterator[HttpClient]:
    """真实 HttpClient：`www.aeaweb.org` 发现层专用（aea adapter 自有限速桶，§5；
    **绝不用于 `pubs.aeaweb.org`**——该域零请求，见模块 docstring 红线）。
    """
    client = make_rate_limited_client(
        domains=AeaAdapter.domains,
        default_rate=AeaAdapter.default_rate,
        contact_email=_CONTACT_EMAIL,
    )
    try:
        yield client
    finally:
        client.close()


@pytest.mark.online
def test_crossref_aer_facet_meets_live_anchor_floor(
    crossref_client: HttpClient, real_request_budget: RealRequestBudget
) -> None:
    """1 请求：AER facet 逐年计数之和 ≥ site-survey [LIVE] 锚点 5643（出版单调增长）。"""
    adapter = CrossrefAdapter(http=crossref_client)
    real_request_budget.spend(1)
    issues = list(adapter.discover_timeline(_aer_venue()))
    total = sum(i.paper_count_claimed or 0 for i in issues)
    print(f"DISCOVER AER years={len(issues)} sum={total} floor={_AER_TOTAL_FLOOR}")
    assert total >= _AER_TOTAL_FLOOR, (
        f"AER facet 逐年计数之和 {total} < site-survey 锚点 {_AER_TOTAL_FLOOR}"
    )


@pytest.mark.online
def test_crossref_single_doi_matches_site_survey_fields_and_own_parser(
    crossref_client: HttpClient, real_request_budget: RealRequestBudget
) -> None:
    """1 请求：单条 DOI lookup——比对 site-survey 字段 + 本 adapter 自身 DOI 解析路由。"""
    adapter = CrossrefAdapter(http=crossref_client)
    real_request_budget.spend(1)
    stub = adapter.lookup(_AER_SAMPLE_DOI)
    assert stub is not None, f"{_AER_SAMPLE_DOI} 未在 Crossref 收录（与 site-survey 矛盾）"
    abstract_len = len(stub.abstract or "")
    print(f"LOOKUP {_AER_SAMPLE_DOI} title={stub.title[:60]!r} abstract_len={abstract_len}")
    assert stub.abstract, "site-survey 记录 has_abstract=True，实测应非空"
    meta = dict(stub.meta)
    if "volume" in meta:
        assert meta["volume"] == _AER_SAMPLE_VOLUME
    if "issue" in meta:
        assert meta["issue"] == _AER_SAMPLE_ISSUE

    # 与本 adapter 自身（零网络）DOI 解析器交叉核对——路由须落 "aer"（§3.2）。
    parsed = parse_doi(_AER_SAMPLE_DOI)
    assert parsed is not None
    assert parsed.venue_id == "aer"
    assert parsed.doi_form == "submission"


@pytest.mark.online
def test_landing_page_carries_citation_meta(
    aeaweb_client: HttpClient, real_request_budget: RealRequestBudget
) -> None:
    """1 请求：`www.aeaweb.org` landing 页——确认 citation_doi/citation_pdf_url 等
    meta 键存在（site-survey §3/§4；不触 `pubs.aeaweb.org`）。
    """
    real_request_budget.spend(1)
    html = aeaweb_client.get_bytes(_LANDING_URL).decode("utf-8", errors="replace")
    print(f"LANDING {_LANDING_URL} bytes={len(html)}")
    assert 'name="citation_doi"' in html
    assert _AER_SAMPLE_DOI in html


@pytest.mark.online
def test_partial_doc_sourced_issns_are_registered_in_crossref(
    crossref_client: HttpClient, real_request_budget: RealRequestBudget
) -> None:
    """2 请求：`aeri`/`jel` 两刊 [DOC] ISSN 的存在性核实（facet 请求返回非负计数即
    表明该 ISSN 在 Crossref 确有注册；不验证刊名文本，见模块 docstring 范围声明）。
    """
    for venue_id, issn in _PARTIAL_DOC_ISSN_CHECKS.items():
        adapter = CrossrefAdapter(http=crossref_client)
        real_request_budget.spend(1)
        issues = list(adapter.discover_timeline(_aer_venue(issn=issn)))
        total = sum(i.paper_count_claimed or 0 for i in issues)
        print(f"DISCOVER {venue_id} issn={issn} years={len(issues)} sum={total}")
        assert total > 0, f"{venue_id} (issn={issn}) 在 Crossref 无任何记录——catalog ISSN 可能有误"
