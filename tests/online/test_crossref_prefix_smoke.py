"""Crossref **prefix 模式** 在线冒烟（Phase 5 T1；nber.md §3.1 两轴扩展在线证据层）。

**只写不跑**：默认经 `-m 'not online'` 排除；显式 `uv run pytest tests/online
-m online` 才跑（缺 `PAPER_CRAWLER_CONTACT_EMAIL` 时整模块 skip，同 crossref/arxiv 样板）。
硬预算 `MAX_REAL_REQUESTS = 5`（`real_request_budget` 逐请求记账，超限即 fail）；请求
共用 5 req/s 限速 client（`make_rate_limited_client`），UA 携真实 mailto（D-014，polite pool）。

证实 T1 两轴扩展的**新面**在真实站点应答且形态与合成 fixture 一致（是 T3/T4 的上游地基）：
- prefix works 页形态（nber 10.3386，1 请求）：`/prefixes/10.3386/works?rows=1` →
  `parse.parse_works_page` 解析出 DOI 前缀 `10.3386/` 的有效记录（证 prefix 基址枚举可解析）。
- prefix + published facet（nber，1 请求）：discover 驱动 `_facet_url(prefix, published)` →
  逐出版年 `IssueRef` 非空（证 prefix 模式 published 轴闭合）。
- prefix + created facet（ssrn 10.2139，1 请求，★评审 MAJOR 联动点，**当前 XFAIL**）：
  `_facet_url(prefix, created)` → 实测 **HTTP 400**（Crossref 无 created facet）→ documented
  spec-vs-reality 冲突（见该用例 xfail reason + T1 终报仲裁项）；enumerate 的 from-created-date
  filter 不受影响（ssrn.md §2 [LIVE] 已证）。

≈ 共 3 请求 ≤ 5（[LIVE 2026-07-24] 实跑：works PASS / published-facet PASS / created-facet XFAIL）。
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

from online.conftest import RealRequestBudget
from online.smoke_helpers import make_rate_limited_client
from paper_crawler.adapters.crossref import parse
from paper_crawler.adapters.crossref.adapter import CrossrefAdapter
from paper_crawler.errors import CrawlerError
from paper_crawler.http import HttpClient
from paper_crawler.types import VenueSpec

MAX_REAL_REQUESTS = 5

# 消费方前缀（nber.md §2 / ssrn.md §2）：nber=10.3386（出版年轴）、ssrn=10.2139（登记年轴）。
_NBER_PREFIX = "10.3386"
_SSRN_PREFIX = "10.2139"

# D-014 UA mailto 段（同 crossref/arxiv 样板：env 缺失整文件 skip——polite pool 硬要求）。
_CONTACT_EMAIL = os.environ.get("PAPER_CRAWLER_CONTACT_EMAIL", "")
if not _CONTACT_EMAIL:
    pytest.skip(
        "PAPER_CRAWLER_CONTACT_EMAIL not set (required for D-014 UA + Crossref polite pool)",
        allow_module_level=True,
    )


def _prefix_venue(venue_id: str, prefix: str) -> VenueSpec:
    """前缀模式 venue（date-field 默认 published；created 轴由 URL builder 直测，不经此 venue）。"""
    return VenueSpec(
        id=venue_id,
        kind="preprint_channel",
        names={"full": venue_id.upper()},
        field=["econ"],
        identifiers={"crossref_prefix": prefix},
        metadata_source="crossref",
        fulltext_source=venue_id,  # 未注册（T3/T4 落地）——直接构造不过 registry，仅元数据路径用
    )


@pytest.fixture(scope="session")
def crossref_client() -> Iterator[HttpClient]:
    """真实 HttpClient：UA 携真实 mailto（D-014，polite pool）+ 5 req/s 限速器（单域）。"""
    client = make_rate_limited_client(
        domains=CrossrefAdapter.domains,
        default_rate=CrossrefAdapter.default_rate,
        contact_email=_CONTACT_EMAIL,
    )
    try:
        yield client
    finally:
        client.close()


@pytest.mark.online
def test_prefix_works_page_shape_nber(
    crossref_client: HttpClient, real_request_budget: RealRequestBudget
) -> None:
    """1 请求：/prefixes/10.3386/works?rows=1 → parse_works_page 解析出 DOI 前缀 10.3386 记录。"""
    real_request_budget.spend(1)
    data = crossref_client.get_bytes(
        f"https://api.crossref.org/prefixes/{_NBER_PREFIX}/works?rows=1"
    )
    page = parse.parse_works_page(data)
    print(
        f"PREFIX-WORKS nber total={page.total_results} items={page.item_count} "
        f"recs={len(page.records)}"
    )
    assert page.item_count >= 1, "prefix works 应至少返回 1 条 item"
    assert page.records, "prefix works 首条应解析出有效记录（DOI + title）"
    sample = page.records[0]
    print(f"  SAMPLE doi={sample.doi!r} title={sample.title[:60]!r}")
    assert sample.doi.startswith(f"{_NBER_PREFIX}/"), f"DOI 前缀异常: {sample.doi!r}"
    assert sample.title.strip(), "sample 记录 title 为空"


@pytest.mark.online
def test_prefix_published_facet_nber(
    crossref_client: HttpClient, real_request_budget: RealRequestBudget
) -> None:
    """1 请求：nber discover（prefix 10.3386 + published）→ 逐出版年 IssueRef 非空。"""
    real_request_budget.spend(1)
    venue = _prefix_venue("nber", _NBER_PREFIX)  # date-field 默认 published
    issues = list(CrossrefAdapter(http=crossref_client).discover_timeline(venue))
    years = sorted(i.year for i in issues if i.year is not None)
    print(f"PREFIX-FACET nber published years={len(years)} range={years[:1]}..{years[-1:]}")
    assert issues, "nber prefix + published facet 应产出逐年 IssueRef（facets.published 非空）"
    assert all(i.paper_count_claimed for i in issues), "每年应带 paper_count_claimed"


@pytest.mark.xfail(
    reason=(
        "SPEC-vs-REALITY 冲突（[LIVE 2026-07-24] T1 冒烟实证，见 T1 终报仲裁项）：真实 Crossref "
        "对 /prefixes/10.2139/works?facet=created:* 返 HTTP 400 validation-failure "
        "'facet-not-available'——created 非该路由合法 facet（合法含 published，不含 created）。"
        "nber.md §3.1 / ssrn.md §4.3 规定的 discover facet=created:* 因此不可实现 → ssrn DISCOVER "
        "机制需设计仲裁；enumerate 的 from-created-date filter 不受影响（ssrn.md §2 [LIVE] 已证）。"
        "本 xfail 为该冲突的活体哨兵：若 Crossref 日后新增 created facet 则 XPASS，提示复核。"
    ),
    strict=False,
    raises=CrawlerError,
)
@pytest.mark.online
def test_prefix_created_facet_ssrn(
    crossref_client: HttpClient, real_request_budget: RealRequestBudget
) -> None:
    """★评审 MAJOR 联动点在线证据（1 请求，当前 XFAIL）：prefix 10.2139 + created facet。

    断言 spec（ssrn.md §4.3）期望——真实 Crossref `facet=created:*` 返 `facets.created.values`
    使 `parse_facet_years(field='created')` 非空。**实测该请求返 HTTP 400**（created 非合法
    facet）→ `get_bytes` 抛 `CrawlerError(CONFIG)` → 本用例 xfail（documented 冲突，非静默）。
    该冲突不在 T1 擅改：T1 的两轴代码忠实实现 spec（facet={field}:* / parse facets.{field}），
    离线单测全绿；discover-by-created-facet 的机制取舍属 ssrn/T4 + spec owner 仲裁范畴（终报）。
    """
    real_request_budget.spend(1)
    adapter = CrossrefAdapter(http=crossref_client)
    url = adapter._facet_url("prefix", _SSRN_PREFIX, "created")
    data = crossref_client.get_bytes(url)  # 实测 HTTP 400 → CrawlerError（xfail 捕获）
    year_counts, total = parse.parse_facet_years(data, "created")
    print(f"PREFIX-FACET ssrn created total={total} created_years={len(year_counts)}")
    assert year_counts, "ssrn prefix + created facet 空：真实 Crossref 未返回 facets.created"
