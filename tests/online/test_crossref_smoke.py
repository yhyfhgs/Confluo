"""Crossref 在线冒烟（Phase 3 T3；aggregators.md §8 在线层）。

**只写不跑**：在线层由 controller 收尾统一实跑（T7/T8）。默认经 `addopts = -m 'not
online'` 排除；显式 `uv run pytest tests/online -m online` 才跑。硬预算
`MAX_REAL_REQUESTS = 5`（`real_request_budget` 逐请求记账、超限即 fail）；请求共用
一个 5 req/s（300rpm）限速 client（`crossref_client`），UA 携真实 mailto（D-014，
Crossref polite pool 硬要求）。

证实真实站点应答 + 解析入库路径打通（AC-3.5 在线证据层）：
- healthcheck（1 请求）：真实 `/works/{固定DOI}` 可达 + title[0] 非空（[PENDING] 结构态）；
  **附打印实测 title 供 UPDATE_GOLDEN 捕获**（捕获后替换 adapter `_HEALTHCHECK_TITLE`）。
- discover QJE facet（1 请求）：逐年 `paper_count_claimed` 之和（=total-results）对
  D-019 锚点 **6655**（出版单调增长 → 断言 `≥6655`，§7 note）。
- enumerate QJE 2024 抽查（1–2 请求 cursor）：闭合年计数 ≈46（§7 稳定锚，±漂移容差）+
  抽 1 篇断字段映射（doi identifier / title 非空 / year==2024）。

≈ 共 3–4 请求 ≤ 5。真实执行结果由 controller 归档在线层记录。
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

from online.conftest import RealRequestBudget
from online.smoke_helpers import make_rate_limited_client
from paper_crawler.adapters.crossref.adapter import CrossrefAdapter
from paper_crawler.http import HttpClient
from paper_crawler.types import IssueRef, PaperStub, VenueSpec

MAX_REAL_REQUESTS = 5

# D-019 锚点（aggregators.md §7）：QJE ISSN 0033-5533、total_all≥6655（增长）、2024=46（闭合年）。
_QJE_ISSN = "0033-5533"
_QJE_TOTAL_FLOOR = 6655
_QJE_2024_COUNT = 46
_QJE_2024_TOLERANCE = 6  # 闭合年，允许少量后补/撤回漂移

# D-014 UA mailto 段（同 arxiv/pmlr 样板：从 env 取，缺失整文件 skip——polite pool 硬要求）。
_CONTACT_EMAIL = os.environ.get("PAPER_CRAWLER_CONTACT_EMAIL", "")
if not _CONTACT_EMAIL:
    pytest.skip(
        "PAPER_CRAWLER_CONTACT_EMAIL not set (required for D-014 UA + Crossref polite pool)",
        allow_module_level=True,
    )


def _qje_venue() -> VenueSpec:
    return VenueSpec(
        id="qje",
        kind="journal",
        names={"full": "The Quarterly Journal of Economics", "aliases": ["QJE"]},
        field=["econ"],
        identifiers={"issn": [_QJE_ISSN]},
        metadata_source="crossref",
        fulltext_source="elsevier_sd",
        auth={"level": "institutional"},
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
def test_healthcheck_reachable_and_capture_title(
    crossref_client: HttpClient, real_request_budget: RealRequestBudget
) -> None:
    """1 请求：真实 /works/{固定DOI} 可达 + title[0] 非空；打印实测 title 供 UPDATE_GOLDEN。"""
    adapter = CrossrefAdapter(http=crossref_client)
    real_request_budget.spend(1)
    report = adapter.healthcheck()
    print(f"HEALTHCHECK healthy={report.healthy} detail={report.detail!r}")
    assert "unreachable" not in report.detail, f"works api unreachable: {report.detail}"
    assert report.healthy, f"crossref healthcheck unhealthy: {report.detail!r}"


@pytest.mark.online
def test_discover_qje_total_matches_anchor(
    crossref_client: HttpClient, real_request_budget: RealRequestBudget
) -> None:
    """1 请求：QJE facet 逐年计数之和（=total-results）≥ D-019 锚点 6655（出版增长）。"""
    adapter = CrossrefAdapter(http=crossref_client)
    real_request_budget.spend(1)
    issues = list(adapter.discover_timeline(_qje_venue()))
    total = sum(i.paper_count_claimed or 0 for i in issues)
    print(f"DISCOVER QJE years={len(issues)} sum={total} floor={_QJE_TOTAL_FLOOR}")
    assert total >= _QJE_TOTAL_FLOOR, (
        f"QJE facet 逐年计数之和 {total} < 锚点下限 {_QJE_TOTAL_FLOOR}（出版单调增长应 ≥）"
    )
    # 2024 闭合年计数抽查（§7 稳定锚，±容差）。
    y2024 = next((i for i in issues if i.year == 2024), None)
    assert y2024 is not None and y2024.paper_count_claimed is not None
    assert abs(y2024.paper_count_claimed - _QJE_2024_COUNT) <= _QJE_2024_TOLERANCE, (
        f"QJE 2024 计数 {y2024.paper_count_claimed} 偏离锚点 {_QJE_2024_COUNT} 超容差"
    )


@pytest.mark.online
def test_enumerate_qje_2024_sample_field_mapping(
    crossref_client: HttpClient, real_request_budget: RealRequestBudget
) -> None:
    """1–2 请求（cursor）：枚举 QJE 2024 → 计数 ≈46 + 抽 1 篇断字段映射。"""
    adapter = CrossrefAdapter(http=crossref_client)
    issue = IssueRef(venue_id="qje", year=2024)
    real_request_budget.spend(2)  # 首页 + 可能 1 续页（≤rows=1000，2024 单页即可，续页取空终止）
    stubs = list(adapter.enumerate_issue(_qje_venue(), issue))
    print(f"ENUMERATE QJE 2024 parsed={len(stubs)} anchor≈{_QJE_2024_COUNT}")
    assert abs(len(stubs) - _QJE_2024_COUNT) <= _QJE_2024_TOLERANCE, (
        f"QJE 2024 枚举 {len(stubs)} 篇，偏离锚点 {_QJE_2024_COUNT} 超容差"
    )
    sample: PaperStub = stubs[0]
    print(f"SAMPLE id={sample.identifiers!r} title={sample.title[:60]!r} year={sample.year}")
    schemes = {scheme for scheme, _ in sample.identifiers}
    assert "doi" in schemes, f"sample stub 无 doi identifier: {sample.identifiers!r}"
    assert sample.title.strip(), "sample stub title 为空"
    # QJE online-first 语义（AC-3.5 实跑实证）：2024 出版窗口内条目的 print year 可为
    # 2025（published-print 后置）——按日期窗口过滤正确，year 断言容两值。
    assert sample.year in (2024, 2025), f"sample stub year {sample.year} not in 2024/2025"
