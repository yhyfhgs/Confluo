"""PMLR 在线冒烟（Phase 2 DoD：每 adapter 一个限量在线冒烟；样板 arxiv）。

默认经 `addopts = -m 'not online'` 排除；显式 `uv run pytest tests/online -m online`
才跑。硬预算 `MAX_REAL_REQUESTS = 5`（`real_request_budget` 逐请求记账、超限即
fail）；请求共用一个 30rpm 限速器（`pmlr_client`，两域共用一份预算——
`proceedings.mlr.press` 主域 + `raw.githubusercontent.com` alias），UA 携真实
mailto（D-014）。

证实真实站点应答 + 解析入库路径打通（AC-2.3 在线证据层同构）：
- healthcheck（1 请求）：站点根 200 + 标题文本 + 卷锚点（pmlr.md §3.5）；
- v235 卷页枚举（1 请求）：ICML 2024 卷页解析出 `PaperStub` 数对 D-019 锚点 **2610**
  （site-survey/pmlr.md：div/Download PDF/去重 slug 三重互证）；
- 单篇 PDF 首 chunk（1 请求）：`%PDF` 魔数（GitHub raw 托管、Content-Type 非 pdf
  也不影响流式；用捕获自 v235 的真实 stub `meta['pdf_url']` 走 resolve→stream）。

≈ 共 3 请求 ≤ 5。真实执行结果归档 scratchpad/online-smoke-batch-run.txt。
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

from helpers import make_pmlr_venue
from online.conftest import RealRequestBudget
from online.smoke_helpers import make_rate_limited_client, stream_first_chunk
from paper_crawler.adapters.pmlr.adapter import PmlrAdapter
from paper_crawler.http import HttpClient
from paper_crawler.types import PaperStub

MAX_REAL_REQUESTS = 5

# D-019 锚点：ICML 2024 = v235 = 2610 篇（site-survey/pmlr.md 三重互证）。
_V235_ANCHOR = 2610

# D-014 UA mailto 段（同 arxiv 样板口径，不硬编码——从 env 取，缺失整文件 skip）。
_CONTACT_EMAIL = os.environ.get("PAPER_CRAWLER_CONTACT_EMAIL", "")
if not _CONTACT_EMAIL:
    pytest.skip(
        "PAPER_CRAWLER_CONTACT_EMAIL not set (required for D-014 UA identity)",
        allow_module_level=True,
    )

# 跨测试传递的真实捕获 stub（enumerate 测试填入首篇，PDF 测试消费）——保持每测试
# 单一职责与逐请求记账清晰，同时让 PDF 走真实枚举出的 meta['pdf_url']（端到端）。
_CAPTURED: list[PaperStub] = []


@pytest.fixture(scope="session")
def pmlr_client() -> Iterator[HttpClient]:
    """真实 HttpClient：UA 携真实 mailto（D-014）+ 30rpm 限速器（两域共享一桶）。"""
    client = make_rate_limited_client(
        domains=PmlrAdapter.domains,
        default_rate=PmlrAdapter.default_rate,
        contact_email=_CONTACT_EMAIL,
    )
    try:
        yield client
    finally:
        client.close()


@pytest.mark.online
def test_healthcheck_site_root_reachable(
    pmlr_client: HttpClient, real_request_budget: RealRequestBudget
) -> None:
    """1 请求：站点根 200 + 标题文本 + 卷锚点（pmlr.md §3.5 匿名 ping）。"""
    adapter = PmlrAdapter(http=pmlr_client)
    real_request_budget.spend(1)
    report = adapter.healthcheck()
    print(f"HEALTHCHECK healthy={report.healthy} detail={report.detail!r}")
    assert "unreachable" not in report.detail, f"site root unreachable: {report.detail}"
    assert report.healthy, f"pmlr healthcheck unhealthy: {report.detail!r}"


@pytest.mark.online
def test_enumerate_v235_count_matches_anchor(
    pmlr_client: HttpClient, real_request_budget: RealRequestBudget
) -> None:
    """1 请求：v235（ICML 2024）卷页解析出的 stub 数 == D-019 锚点 2610。"""
    adapter = PmlrAdapter(http=pmlr_client)
    venue = make_pmlr_venue()  # 默认 volume_map={2023:202, 2024:235}
    # discover 零网络（读 volume_map），拿 v235 的 IssueRef，不手搓字段。
    issue = next(i for i in adapter.discover_timeline(venue) if i.volume == "235")
    real_request_budget.spend(1)
    stubs = list(adapter.enumerate_issue(venue, issue))
    print(f"ENUMERATE v235 parsed={len(stubs)} anchor={_V235_ANCHOR}")
    assert len(stubs) == _V235_ANCHOR, (
        f"v235 解析出 {len(stubs)} 篇，与 D-019 锚点 {_V235_ANCHOR} 不符"
    )
    # 捕获首篇（带 pdf_url）供 PDF 测试端到端复用真实 meta。
    first_with_pdf = next((s for s in stubs if dict(s.meta).get("pdf_url")), None)
    assert first_with_pdf is not None, "v235 无任何 stub 携带 pdf_url meta"
    _CAPTURED.append(first_with_pdf)
    pdf_url = dict(first_with_pdf.meta)["pdf_url"]
    print(f"CAPTURED id={first_with_pdf.identifiers!r} pdf_url={pdf_url!r}")


@pytest.mark.online
def test_fetch_single_pdf_first_chunk_is_pdf(
    pmlr_client: HttpClient, real_request_budget: RealRequestBudget
) -> None:
    """1 请求：resolve 真实 stub → stream 首 chunk 断 `%PDF` 魔数后关流（HEAD 语义）。"""
    if not _CAPTURED:
        pytest.skip("需先跑 test_enumerate_v235_count_matches_anchor 捕获真实 stub")
    adapter = PmlrAdapter(http=pmlr_client)
    plan = adapter.resolve_assets(make_pmlr_venue(), _CAPTURED[0])[0]
    real_request_budget.spend(1)
    head = stream_first_chunk(pmlr_client, plan.url)
    print(f"FETCH_FIRST_CHUNK url={plan.url} head={head[:8]!r}")
    assert head.startswith(b"%PDF"), f"下载体非 PDF（前 8 字节 {head[:8]!r}）"
