"""NBER 在线冒烟（Phase 5 T3；nber.md §7/§8；AC-5.2 在线证据层）。

**只写不跑**：默认经 `-m 'not online'` 排除；显式 `uv run pytest tests/online -m online` 才跑
（缺 `PAPER_CRAWLER_CONTACT_EMAIL` 时整模块 skip，同 crossref/arxiv 样板）。硬预算
`MAX_REAL_REQUESTS = 5`（`real_request_budget` 逐请求记账，超限即 fail）；UA 携真实 mailto
（D-014，诚实非训练用途，`PaperCrawler/<ver> (personal research; mailto:…)`）。

台账（≤5，nber.md §7/§8；**全程不触 <18 月论文**——红线）：
1. crossref prefix works（nber 10.3386，1 请求，api.crossref.org）→ prefix 基址枚举可解析。
2. crossref prefix + published facet（nber，1 请求，api.crossref.org）→ 逐出版年 IssueRef 非空。
3. RSS new.xml（1 请求，**back.nber.org 独立桶 ≥10s** 遵 Crawl-delay:10）→ parse_rss_items 非空。
4. 已知 >18 月开放 w30000 PDF **首 chunk %PDF**（1 请求，www.nber.org，**不下正文**）。
5. www.nber.org robots.txt 复核（1 请求）→ 断言 /search Disallow（红线：不作枚举路径）。

**红线**：全程只触已知 >18 月开放 w30000（不触任何 <18 月论文/软门）；back.nber.org 若触
必 ≥10s 间隔（独立桶 rpm=6，实跑遵 Crawl-delay:10）。
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

from online.conftest import RealRequestBudget
from online.smoke_helpers import make_rate_limited_client, stream_first_chunk
from paper_crawler.adapters.crossref import parse as crossref_parse
from paper_crawler.adapters.crossref.adapter import CrossrefAdapter
from paper_crawler.adapters.nber import parse as nber_parse
from paper_crawler.adapters.nber.adapter import BACK_HOST, NberAdapter
from paper_crawler.http import HttpClient
from paper_crawler.ratelimit import RateLimiter
from paper_crawler.types import VenueSpec
from paper_crawler.useragent import build_user_agent

MAX_REAL_REQUESTS = 5

_NBER_PREFIX = "10.3386"
_HEALTHCHECK_PDF = "https://www.nber.org/system/files/working_papers/w30000/w30000.pdf"
_RSS_URL = "https://back.nber.org/rss/new.xml"
_ROBOTS_URL = "https://www.nber.org/robots.txt"

# D-014 UA mailto 段（同 crossref/arxiv 样板：env 缺失整文件 skip）。
_CONTACT_EMAIL = os.environ.get("PAPER_CRAWLER_CONTACT_EMAIL", "")
if not _CONTACT_EMAIL:
    pytest.skip(
        "PAPER_CRAWLER_CONTACT_EMAIL not set (required for D-014 UA + Crossref polite pool)",
        allow_module_level=True,
    )


def _nber_venue() -> VenueSpec:
    """nber prefix venue（默认 published；fulltext_source 未过 registry，仅元数据路径用）。"""
    return VenueSpec(
        id="nber",
        kind="preprint_channel",
        names={"full": "NBER Working Papers"},
        field=["econ"],
        identifiers={"crossref_prefix": _NBER_PREFIX},
        metadata_source="crossref",
        fulltext_source="nber",
    )


@pytest.fixture(scope="session")
def crossref_client() -> Iterator[HttpClient]:
    """真实 CrossrefAdapter client：UA 携 mailto（polite pool）+ 5 req/s（api.crossref.org）。"""
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
def nber_client() -> Iterator[HttpClient]:
    """真实 nber client：www.nber.org 1 req/5s（+ www2 别名）+ back.nber.org **独立桶** 1 req/10s。

    双域分桶亲装（nber.md §4）：register www（default_rate）+ alias www2；**独立** register
    back.nber.org（BACK_RATE_POLICY，1 req/10s 遵 Crawl-delay:10，不 alias www）。UA 诚实 mailto。
    """
    limiter = RateLimiter()
    limiter.register(NberAdapter.domains[0], NberAdapter.default_rate)
    for mirror in NberAdapter.domains[1:]:
        limiter.alias(mirror, NberAdapter.domains[0])
    limiter.register(BACK_HOST, NberAdapter.BACK_RATE_POLICY)  # 独立桶（on-demand，OA-host 先例）
    client = HttpClient(user_agent=build_user_agent(_CONTACT_EMAIL), rate_limiter=limiter)
    try:
        yield client
    finally:
        client.close()


@pytest.mark.online
def test_prefix_works_page_shape(
    crossref_client: HttpClient, real_request_budget: RealRequestBudget
) -> None:
    """1 请求：/prefixes/10.3386/works?rows=1 → parse_works_page 解析出 DOI 前缀 10.3386 记录。"""
    real_request_budget.spend(1)
    data = crossref_client.get_bytes(
        f"https://api.crossref.org/prefixes/{_NBER_PREFIX}/works?rows=1"
    )
    page = crossref_parse.parse_works_page(data)
    print(f"NBER-PREFIX-WORKS total={page.total_results} items={page.item_count}")
    assert page.records, "prefix works 首条应解析出有效记录（DOI + title）"
    assert page.records[0].doi.startswith(f"{_NBER_PREFIX}/"), page.records[0].doi


@pytest.mark.online
def test_prefix_published_facet_discover(
    crossref_client: HttpClient, real_request_budget: RealRequestBudget
) -> None:
    """1 请求：nber venue 键（prefix + published）→ discover 逐出版年 IssueRef 非空。"""
    real_request_budget.spend(1)
    issues = list(CrossrefAdapter(http=crossref_client).discover_timeline(_nber_venue()))
    years = sorted(i.year for i in issues if i.year is not None)
    print(f"NBER-PREFIX-FACET published years={len(years)} range={years[:1]}..{years[-1:]}")
    assert issues, "nber prefix + published facet 应产逐年 IssueRef（facets.published 非空）"


@pytest.mark.online
def test_rss_new_xml_parses(
    nber_client: HttpClient, real_request_budget: RealRequestBudget
) -> None:
    """1 请求（back.nber.org 独立桶 ≥10s）：new.xml → parse_rss_items 非空 + guid 反解 DOI。"""
    real_request_budget.spend(1)
    data = nber_client.get_bytes(_RSS_URL)
    items = nber_parse.parse_rss_items(data)
    print(f"NBER-RSS items={len(items)} first={items[:1]}")
    assert items, "new.xml 应解析出周新论文 item（guid→DOI）"
    assert all(it.doi.startswith(f"{_NBER_PREFIX}/") for it in items)


@pytest.mark.online
def test_open_pdf_first_chunk_is_pdf(
    nber_client: HttpClient, real_request_budget: RealRequestBudget
) -> None:
    """1 请求（www.nber.org，**不下正文**）：已知 >18 月开放 w30000 PDF 首 chunk → %PDF- 魔数。

    **红线**：只触已知 >18 月开放段（w30000）——绝不触 <18 月论文/软门。首 chunk 取回即关流
    （HEAD 式轻探测），断 `%PDF-` 魔数（真值 [PENDING UPDATE_GOLDEN]：捕获后可加 content-type）。
    """
    real_request_budget.spend(1)
    head = stream_first_chunk(nber_client, _HEALTHCHECK_PDF, min_bytes=8)
    print(f"NBER-PDF-HEAD w30000 head={head[:8]!r}")
    assert head.lstrip().startswith(b"%PDF-"), f"w30000 开放 PDF 首字节非 %PDF: {head[:16]!r}"


@pytest.mark.online
def test_www_robots_disallows_search(
    nber_client: HttpClient, real_request_budget: RealRequestBudget
) -> None:
    """1 请求：www.nber.org/robots.txt 复核——/search Disallow（红线：不作枚举路径，AC-0.5）。"""
    real_request_budget.spend(1)
    body = nber_client.get_bytes(_ROBOTS_URL)
    text = body.decode("utf-8", errors="replace")
    print(f"NBER-ROBOTS len={len(text)}")
    assert "/search" in text, "robots.txt 应含 /search 规则（[LIVE] Disallow）——变更须复核枚举红线"
