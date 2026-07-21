"""CVF Open Access 在线冒烟（Phase 2 DoD：每 adapter 一个限量在线冒烟；样板 arxiv）。

默认经 `addopts = -m 'not online'` 排除。硬预算 `MAX_REAL_REQUESTS = 5`；请求共用一个
30rpm 限速器（`cvf_client`，单域 `openaccess.thecvf.com`），UA 携真实 mailto（D-014）。

证实真实站点应答 + 解析入库路径打通（AC-2.4 在线证据层）：
- healthcheck（1 请求）：`CVPR2024?day=all` 首条目解析成功（固定已发布年，确定性——
  默认 current_year=当前 UTC 年，本届可能未发布，冒烟注入 2024 保稳定）；
- CVPR2023 现代全集（1 请求，`list_mode=day_all` 强制直取 `?day=all` 免 bare 探测）：
  条目数 == D-019 锚点 **2353**（site-survey/cvf.md：dt.ptitle/papers.pdf/>pdf</a>
  三法互证）；
- CVPR2013 flat 早年（1 请求）：**验证 `query` 属性修复的真实性**——flat 页作者取自
  `input[name=query]`（非现代 `query_author`），断言首条 stub **authors 非空**（修复
  缺席则此断言必挂，见 cvf/parse.py `_AUTHOR_INPUT_NAMES` 与 fix commit）；
- 单篇 PDF 首 chunk（1 请求）：`%PDF` 魔数（捕获自 CVPR2023 的真实 stub）。

≈ 共 4 请求 ≤ 5。真实执行结果归档 scratchpad/online-smoke-batch-run.txt。
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

from helpers import make_cvf_venue
from online.conftest import RealRequestBudget
from online.smoke_helpers import make_rate_limited_client, stream_first_chunk
from paper_crawler.adapters.cvf.adapter import CVFAdapter
from paper_crawler.http import HttpClient
from paper_crawler.types import IssueRef, PaperStub

MAX_REAL_REQUESTS = 5

# D-019 锚点：CVPR2023 `?day=all` 全集 = 2353（site-survey/cvf.md 三法互证）。
_CVPR2023_ANCHOR = 2353
# healthcheck 用固定已发布年（避免当前届未发布导致的非确定性）。
_HEALTHCHECK_YEAR = 2024

_CONTACT_EMAIL = os.environ.get("PAPER_CRAWLER_CONTACT_EMAIL", "")
if not _CONTACT_EMAIL:
    pytest.skip(
        "PAPER_CRAWLER_CONTACT_EMAIL not set (required for D-014 UA identity)",
        allow_module_level=True,
    )

_CAPTURED: list[PaperStub] = []


@pytest.fixture(scope="session")
def cvf_client() -> Iterator[HttpClient]:
    """真实 HttpClient：UA 携真实 mailto（D-014）+ 30rpm 限速器（单域）。"""
    client = make_rate_limited_client(
        domains=CVFAdapter.domains,
        default_rate=CVFAdapter.default_rate,
        contact_email=_CONTACT_EMAIL,
    )
    try:
        yield client
    finally:
        client.close()


@pytest.mark.online
def test_healthcheck_recent_cvpr_reachable(
    cvf_client: HttpClient, real_request_budget: RealRequestBudget
) -> None:
    """1 请求：`CVPR2024?day=all` 首条目解析成功（cvf.md §3.5；固定已发布年）。"""
    adapter = CVFAdapter(http=cvf_client, current_year=_HEALTHCHECK_YEAR)
    real_request_budget.spend(1)
    report = adapter.healthcheck()
    print(f"HEALTHCHECK healthy={report.healthy} detail={report.detail!r}")
    assert report.healthy, f"cvf healthcheck unhealthy: {report.detail!r}"


@pytest.mark.online
def test_enumerate_cvpr2023_count_matches_anchor(
    cvf_client: HttpClient, real_request_budget: RealRequestBudget
) -> None:
    """1 请求：CVPR2023 `?day=all` 条目数 == D-019 锚点 2353（强制 day_all 免 bare 探测）。"""
    adapter = CVFAdapter(http=cvf_client)
    venue = make_cvf_venue("cvpr", list_mode="day_all")
    issue = IssueRef(venue_id="cvpr", year=2023, label="2023")
    real_request_budget.spend(1)
    stubs = list(adapter.enumerate_issue(venue, issue))
    print(f"ENUMERATE CVPR2023 parsed={len(stubs)} anchor={_CVPR2023_ANCHOR}")
    assert len(stubs) == _CVPR2023_ANCHOR, (
        f"CVPR2023 解析出 {len(stubs)} 篇，与 D-019 锚点 {_CVPR2023_ANCHOR} 不符"
    )
    first_with_pdf = next((s for s in stubs if dict(s.meta).get("pdf_url")), None)
    assert first_with_pdf is not None, "CVPR2023 无任何 stub 携带 pdf_url meta"
    _CAPTURED.append(first_with_pdf)
    pdf_url = dict(first_with_pdf.meta)["pdf_url"]
    print(f"CAPTURED id={first_with_pdf.identifiers!r} pdf_url={pdf_url!r}")


@pytest.mark.online
def test_enumerate_cvpr2013_flat_has_authors(
    cvf_client: HttpClient, real_request_budget: RealRequestBudget
) -> None:
    """1 请求：CVPR2013 flat 早年页首条 stub authors 非空——验证 `query` 属性修复真实性。

    flat 页作者取自 `input[name=query]`（现代 `?day=all` 页用 `query_author`）；若
    adapter 只认现代属性名（修复缺席），flat 页 authors 会全空、本断言挂——这正是
    在线证伪 `fix(adapter:cvf): flat-era author input is name="query"` 的载体。
    """
    adapter = CVFAdapter(http=cvf_client)
    venue = make_cvf_venue("cvpr")  # 自动探测（flat 页 bare URL 直含 dt.ptitle）
    issue = IssueRef(venue_id="cvpr", year=2013, label="2013")
    real_request_budget.spend(1)
    stubs = list(adapter.enumerate_issue(venue, issue))
    assert stubs, "CVPR2013 解析出 0 条目"
    with_authors = [s for s in stubs if s.authors]
    print(
        f"ENUMERATE CVPR2013 parsed={len(stubs)} with_authors={len(with_authors)} "
        f"sample_authors={stubs[0].authors!r}"
    )
    assert stubs[0].authors, "CVPR2013 flat 首条 stub authors 为空——query 属性修复疑似缺席/失效"


@pytest.mark.online
def test_fetch_single_pdf_first_chunk_is_pdf(
    cvf_client: HttpClient, real_request_budget: RealRequestBudget
) -> None:
    """1 请求：resolve 真实 CVPR2023 stub → stream 首 chunk 断 `%PDF` 魔数后关流。"""
    if not _CAPTURED:
        pytest.skip("需先跑 test_enumerate_cvpr2023_count_matches_anchor 捕获真实 stub")
    adapter = CVFAdapter(http=cvf_client)
    plan = adapter.resolve_assets(make_cvf_venue("cvpr"), _CAPTURED[0])[0]
    real_request_budget.spend(1)
    head = stream_first_chunk(cvf_client, plan.url)
    print(f"FETCH_FIRST_CHUNK url={plan.url} head={head[:8]!r}")
    assert head.startswith(b"%PDF"), f"下载体非 PDF（前 8 字节 {head[:8]!r}）"
