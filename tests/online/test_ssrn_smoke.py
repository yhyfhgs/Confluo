"""SSRN 元数据层在线冒烟（Phase 5 T4；聚合元数据主路径，**零 SSRN 域**）。

**只写不跑**：默认经 `-m 'not online'` 排除；显式 `uv run pytest tests/online -m online`
才跑（缺 `PAPER_CRAWLER_CONTACT_EMAIL` 时整模块 skip，同 crossref/arxiv 样板）。硬预算
`MAX_REAL_REQUESTS = 5`（`real_request_budget` 逐请求记账，超限即 fail）；请求共用 5 req/s
限速 client（`make_rate_limited_client`），UA 携真实 mailto（D-014，polite pool，≥1s 间隔）。

**绝对红线：`*.ssrn.com` 零请求**——本冒烟唯一接触域 = `api.crossref.org`（元数据主路径）。
证实 SSRN 元数据层的**有效 online 路径**（是 T4 offline DoD 的活体地基）：

- **created-date FILTER 窗**（prefix 10.2139，1 请求）：`from/until-created-date` 窗 → 实测
  HTTP 200 + `parse_works_page` 解析出 `10.2139/ssrn.*` 记录 → `parse.abstract_id_from_doi`
  抽 abstract_id。**★spec-vs-reality 关键**：created **FILTER** 有效（区别于 created **FACET**
  ——后者返 HTTP 400，已由 T1 `test_crossref_prefix_smoke.py::test_prefix_created_facet_ssrn`
  XFAIL 哨兵覆盖，本处不重复；controller 发现①仲裁令据此改 DISCOVER 为纯生成）。
- **healthcheck 锚点**（固定 SSRN DOI，1 请求）：`SsrnAdapter.healthcheck` 经 crossref lookup
  打 `api.crossref.org/works/10.2139/ssrn.4056799` → title 精确 drift 比对。**非 SSRN 域**。
  golden 真值 [LIVE 2026-07-24] 已双源转正（本冒烟捕获 title="Allocating Scarce
  Information" + P5-M1 openalex 第二源确认一致，`_HEALTHCHECK_TITLE` 见 adapter 常量）。

≈ 共 2 请求 ≤ 5。DISCOVER 纯生成零网络、RESOLVE landing-only 零网络——无 online 面（offline
全覆盖）。
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from urllib.parse import urlencode

import pytest

from online.conftest import RealRequestBudget
from online.smoke_helpers import make_rate_limited_client
from paper_crawler.adapters.crossref import parse as crossref_parse
from paper_crawler.adapters.ssrn import parse as ssrn_parse
from paper_crawler.adapters.ssrn.adapter import SsrnAdapter
from paper_crawler.http import HttpClient

MAX_REAL_REQUESTS = 5

_SSRN_PREFIX = "10.2139"
# created-date FILTER 窗（固定过去区间，稳定且必populated——SSRN 日均数百投稿入 Crossref）。
_CREATED_FROM = "2026-06-01"
_CREATED_UNTIL = "2026-06-02"

# D-014 UA mailto 段（同 crossref/arxiv 样板：env 缺失整文件 skip——polite pool 硬要求）。
_CONTACT_EMAIL = os.environ.get("PAPER_CRAWLER_CONTACT_EMAIL", "")
if not _CONTACT_EMAIL:
    pytest.skip(
        "PAPER_CRAWLER_CONTACT_EMAIL not set (required for D-014 UA + Crossref polite pool)",
        allow_module_level=True,
    )


@pytest.fixture(scope="session")
def crossref_client() -> Iterator[HttpClient]:
    """真实 HttpClient：UA 携真实 mailto（D-014，polite pool）+ 5 req/s 限速器（单域）。

    限速域 = `SsrnAdapter.domains`（=`api.crossref.org`，元数据唯一网络出口）——`*.ssrn.com`
    **不在** domains，结构性保证零 SSRN 注册/请求。
    """
    client = make_rate_limited_client(
        domains=SsrnAdapter.domains,
        default_rate=SsrnAdapter.default_rate,
        contact_email=_CONTACT_EMAIL,
    )
    try:
        yield client
    finally:
        client.close()


@pytest.mark.online
def test_prefix_created_filter_window_returns_ssrn_records(
    crossref_client: HttpClient, real_request_budget: RealRequestBudget
) -> None:
    """1 请求：prefix 10.2139 + created **FILTER** 窗 → 200 + ssrn 记录 + abstract_id 抽取。

    ★spec-vs-reality：created **FILTER**（from/until-created-date）有效，区别于 created
    **FACET**（HTTP 400，T1 哨兵覆盖）——这是 ssrn ENUMERATE 委 crossref 的 created 轴地基。
    """
    real_request_budget.spend(1)
    params = {
        "filter": f"from-created-date:{_CREATED_FROM},until-created-date:{_CREATED_UNTIL}",
        "rows": "3",
    }
    url = f"https://api.crossref.org/prefixes/{_SSRN_PREFIX}/works?{urlencode(params)}"
    assert url.startswith("https://api.crossref.org/"), "唯一接触域必须是 api.crossref.org"
    data = crossref_client.get_bytes(url)  # created FILTER 有效 → 200（非 400 FACET）
    page = crossref_parse.parse_works_page(data)
    print(
        f"SSRN-CREATED-FILTER window {_CREATED_FROM}..{_CREATED_UNTIL} "
        f"total={page.total_results} items={page.item_count} recs={len(page.records)}"
    )
    assert page.records, "created FILTER 窗应解析出有效记录（DOI + title）"
    sample = page.records[0]
    print(f"  SAMPLE doi={sample.doi!r} title={sample.title[:60]!r}")
    assert sample.doi.startswith(f"{_SSRN_PREFIX}/"), f"DOI 前缀异常: {sample.doi!r}"
    # ssrn 后处理层 abstract_id 抽取（下载主键）——对至少一条真实记录成立。
    abstract_ids = [
        ssrn_parse.abstract_id_from_doi(rec.doi)
        for rec in page.records
        if ssrn_parse.abstract_id_from_doi(rec.doi) is not None
    ]
    print(f"  abstract_ids extracted: {abstract_ids}")
    assert abstract_ids, "created 窗内应至少一条 10.2139/ssrn.* DOI 可抽 abstract_id"


@pytest.mark.online
def test_healthcheck_anchor_via_crossref_non_ssrn_domain(
    crossref_client: HttpClient, real_request_budget: RealRequestBudget
) -> None:
    """1 请求：healthcheck 锚点固定 SSRN DOI 经 crossref lookup（**api.crossref.org，非 SSRN**）。

    golden 真值 [LIVE 2026-07-24] 已双源转正（`_HEALTHCHECK_TITLE="Allocating Scarce
    Information"`）——本次在线实跑走精确 drift 比对分支（非 PENDING 结构态）。
    """
    real_request_budget.spend(1)
    adapter = SsrnAdapter(http=crossref_client)
    report = adapter.healthcheck()
    print(f"SSRN-HEALTHCHECK healthy={report.healthy} detail={report.detail}")
    assert report.healthy is True, f"固定 SSRN DOI 锚点应经 crossref 解析健康: {report.detail}"
