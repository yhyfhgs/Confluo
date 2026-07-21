"""AAAI OJS 在线冒烟（Phase 2 DoD：每 adapter 一个限量在线冒烟；样板 arxiv）。

默认经 `addopts = -m 'not online'` 排除。硬预算 `MAX_REAL_REQUESTS = 5`；请求共用一个
30rpm 限速器（`aaai_client`，单域 `ojs.aaai.org`），UA 携真实 mailto（D-014）。

证实真实站点应答 + 解析入库路径打通（design/adapters/aaai-ojs.md §4 在线证据层）：
- healthcheck（1 请求）：OAI `Identify` 200 + `repositoryName` 含 "AAAI"（存活基线，
  匿名零 token，§3.5）；
- OAI `ListRecords` 首页（1 请求，**不翻页**）：`parse_oai_page` 结构断言（记录非空、
  首条含本源 DOI + 标题、可从 DOI 抽卷号）+ 墓碑跳过数可观测（`skipped_tombstones`）；
- 单篇 PDF 首 chunk（1 请求）：`view→download` 预换（resolve）+ 302 跟随（HttpClient
  `follow_redirects`）→ `%PDF` 魔数（捕获自首页首个带 galley 的真实记录）。

≈ 共 3 请求 ≤ 5。openreview 因无用户 token（free_account 级）本批跳过，不在此列。
真实执行结果归档 scratchpad/online-smoke-batch-run.txt。
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

from helpers import make_aaai_venue
from online.conftest import RealRequestBudget
from online.smoke_helpers import make_rate_limited_client, stream_first_chunk
from paper_crawler.adapters.aaai_ojs import parse
from paper_crawler.adapters.aaai_ojs.adapter import (
    AaaiOjsAdapter,
    _oai_base,
    _oai_list_url,
    _ojs_code,
)
from paper_crawler.adapters.aaai_ojs.parse import AaaiRecord
from paper_crawler.http import HttpClient

MAX_REAL_REQUESTS = 5

_CONTACT_EMAIL = os.environ.get("PAPER_CRAWLER_CONTACT_EMAIL", "")
if not _CONTACT_EMAIL:
    pytest.skip(
        "PAPER_CRAWLER_CONTACT_EMAIL not set (required for D-014 UA identity)",
        allow_module_level=True,
    )

_CAPTURED: list[AaaiRecord] = []


@pytest.fixture(scope="session")
def aaai_client() -> Iterator[HttpClient]:
    """真实 HttpClient：UA 携真实 mailto（D-014）+ 30rpm 限速器（单域）。"""
    client = make_rate_limited_client(
        domains=AaaiOjsAdapter.domains,
        default_rate=AaaiOjsAdapter.default_rate,
        contact_email=_CONTACT_EMAIL,
    )
    try:
        yield client
    finally:
        client.close()


@pytest.mark.online
def test_healthcheck_oai_identify(
    aaai_client: HttpClient, real_request_budget: RealRequestBudget
) -> None:
    """1 请求：OAI `Identify` 200 + `repositoryName` 含 "AAAI"（存活基线，§3.5）。"""
    adapter = AaaiOjsAdapter(http=aaai_client)
    real_request_budget.spend(1)
    report = adapter.healthcheck()
    print(f"HEALTHCHECK healthy={report.healthy} detail={report.detail!r}")
    assert report.healthy, f"aaai OAI Identify healthcheck unhealthy: {report.detail!r}"


@pytest.mark.online
def test_listrecords_first_page_structure(
    aaai_client: HttpClient, real_request_budget: RealRequestBudget
) -> None:
    """1 请求：OAI `ListRecords` 首页 oai_dc 结构断言 + 墓碑计数（不翻页）。"""
    venue = make_aaai_venue()
    oai_base = _oai_base(_ojs_code(venue))
    url = _oai_list_url(oai_base, None)  # 首页无 from 窗；不消费 resumptionToken（不翻页）
    real_request_budget.spend(1)
    page = parse.parse_oai_page(aaai_client.get_bytes(url))
    print(
        f"LISTRECORDS records={len(page.records)} "
        f"skipped_tombstones={page.skipped_tombstones} "
        f"has_resumption_token={page.resumption_token is not None}"
    )
    assert page.records, "OAI ListRecords 首页解析出 0 条记录"
    assert isinstance(page.skipped_tombstones, int) and page.skipped_tombstones >= 0
    first = page.records[0]
    print(f"FIRST_RECORD doi={first.doi!r} volume={first.volume!r} title={first.title!r}")
    assert first.doi.startswith("10."), f"首条记录 DOI 形态异常: {first.doi!r}"
    assert first.title, "首条记录标题为空"
    # oai_dc 结构完整性：至少一条能从 AAAI DOI 抽出卷号（enumerate 客户端过滤维度）。
    assert any(r.volume is not None for r in page.records), (
        "首页无任何记录能从 DOI 抽出 AAAI 卷号（volume_from_doi 全 None，疑似 schema 漂移）"
    )
    galley = next((r for r in page.records if r.pdf_view_url), None)
    assert galley is not None, "首页无任何记录携带 dc:relation galley view URL"
    _CAPTURED.append(galley)
    print(f"CAPTURED doi={galley.doi!r} pdf_view_url={galley.pdf_view_url!r}")


@pytest.mark.online
def test_fetch_single_pdf_first_chunk_is_pdf(
    aaai_client: HttpClient, real_request_budget: RealRequestBudget
) -> None:
    """1 请求：resolve（view→download 预换）→ 302 跟随 → stream 首 chunk 断 `%PDF`。"""
    if not _CAPTURED:
        pytest.skip("需先跑 test_listrecords_first_page_structure 捕获真实记录")
    adapter = AaaiOjsAdapter(http=aaai_client)
    stub = parse.to_paper_stub(_CAPTURED[0])
    plan = adapter.resolve_assets(make_aaai_venue(), stub)[0]
    print(f"RESOLVE view->download url={plan.url}")
    real_request_budget.spend(1)
    head = stream_first_chunk(aaai_client, plan.url)
    print(f"FETCH_FIRST_CHUNK head={head[:8]!r}")
    assert head.startswith(b"%PDF"), (
        f"下载体非 PDF（前 8 字节 {head[:8]!r}）——疑似登录门（★D）/撤稿页，见报告"
    )
