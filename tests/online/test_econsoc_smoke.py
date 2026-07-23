"""Econometric Society（econsoc）在线冒烟（Phase 5 T6；design/adapters/econsoc.md §7 T5/§8）。

默认经 `addopts = -m 'not online'` 排除（不入 make check）。硬预算 `MAX_REAL_REQUESTS = 10`；
OAI/galley 请求共用一个限速 client（adapter 保守并集限速器），UA 携真实 mailto（D-014）；
doi.org 域名路由核对用独立 follow-redirects client（读实时重定向终点，HttpClient 无 HEAD/终点面）。

实测意图（≤10 请求）：
- healthcheck（1）：TE OAI `Identify` 200 + repositoryName 含 "Theoretical Economics"；
- TE OAI `ListRecords` 首页（1，不翻页）：`parse_oai_page` 结构断言 + 捕获首条 header identifier
  与一条带 galley 的记录；
- TE `GetRecord`（1）：以捕获 identifier 取单条（canary 活体锚）；
- TE 单篇 landing→galley→PDF 首 chunk（2）：resolve GET 落地页抽 galley + galley 首 chunk `%PDF`
  （闭 TE 匿名 OA）；
- ECMA 当前段 doi.org 域名核对（1）：ecta23709 → econometricsociety.org → classify=CURRENT；
- ECMA 过刊段 doi.org 域名核对（1）：ecta12058 → doi.wiley.com → classify=BACKFILE（闭
  [UNRESOLVED②] 抽样；权威取实时落地域名）。

环境注记：econsoc 域 R0c [LIVE] 实测可达；若遇 TLS reset/连接层阻断＝**环境障碍**（如实标注，
勿据此记站点 BLOCKED）。CF 前置域连续 challenge 即停（不对抗，AC-0.2）。qeconomics.org 证书过期
——绝不直连该域（QE 一切经 econtheory.org OAI + econometricsociety.org）。
"""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from collections.abc import Iterator

import httpx
import pytest

from online.conftest import RealRequestBudget
from online.smoke_helpers import make_rate_limited_client, stream_first_chunk
from paper_crawler.adapters.econsoc import parse
from paper_crawler.adapters.econsoc.adapter import (
    _DEFAULT_OAI_BASE,
    EconsocAdapter,
    _oai_endpoint_for_code,
    _oai_list_url,
)
from paper_crawler.adapters.econsoc.parse import EcmaSegment, EconsocRecord
from paper_crawler.http import HttpClient
from paper_crawler.useragent import build_user_agent

MAX_REAL_REQUESTS = 10

_CONTACT_EMAIL = os.environ.get("PAPER_CRAWLER_CONTACT_EMAIL", "")
if not _CONTACT_EMAIL:
    pytest.skip(
        "PAPER_CRAWLER_CONTACT_EMAIL not set (required for D-014 UA identity)",
        allow_module_level=True,
    )

# 实测锚（survey §1/§2 [LIVE] 2026-07-24 R0c）。
_TE_OAI = _oai_endpoint_for_code(_DEFAULT_OAI_BASE, "te")
_ECMA_CURRENT_DOI = "10.3982/ecta23709"  # 2026 当前段 → econometricsociety.org 自营
_ECMA_BACKFILE_DOI = "10.3982/ecta12058"  # 2015 过刊段 → doi.wiley.com（403 CF）
_OAI_NS = {"oai": "http://www.openarchives.org/OAI/2.0/"}

_CAPTURED: list[EconsocRecord] = []
_CAPTURED_OAI_ID: list[str] = []


@pytest.fixture(scope="session")
def econsoc_client() -> Iterator[HttpClient]:
    """真实限速 HttpClient：UA 携真实 mailto（D-014）+ adapter 保守并集限速器（多域同桶）。"""
    client = make_rate_limited_client(
        domains=EconsocAdapter.domains,
        default_rate=EconsocAdapter.default_rate,
        contact_email=_CONTACT_EMAIL,
    )
    try:
        yield client
    finally:
        client.close()


@pytest.fixture(scope="session")
def doi_client() -> Iterator[httpx.Client]:
    """doi.org 域名路由核对用 follow-redirects client（读实时重定向终点 host）。

    `HttpClient` 无 HEAD/不暴露终点 URL；域名路由权威信号=doi.org HEAD -L 实时终点（§3.3），
    故独立构造。UA 携真实 mailto（D-014），不伪装。
    """
    client = httpx.Client(
        headers={"User-Agent": build_user_agent(_CONTACT_EMAIL)},
        follow_redirects=True,
        timeout=30.0,
    )
    try:
        yield client
    finally:
        client.close()


@pytest.mark.online
def test_healthcheck_oai_identify(
    econsoc_client: HttpClient, real_request_budget: RealRequestBudget
) -> None:
    """1 请求：TE OAI `Identify` 200 + repositoryName 含 "Theoretical Economics"（存活基线）。"""
    adapter = EconsocAdapter(http=econsoc_client)
    real_request_budget.spend(1)
    report = adapter.healthcheck()
    print(f"HEALTHCHECK healthy={report.healthy} detail={report.detail!r}")
    assert report.healthy, f"econsoc TE OAI Identify healthcheck unhealthy: {report.detail!r}"


@pytest.mark.online
def test_te_listrecords_first_page_structure(
    econsoc_client: HttpClient, real_request_budget: RealRequestBudget
) -> None:
    """1 请求：TE OAI `ListRecords` 首页 oai_dc 结构断言 + 捕获 identifier / galley 记录。"""
    url = _oai_list_url(_TE_OAI, None)  # 首页无 from 窗；不消费 resumptionToken（不翻页）
    real_request_budget.spend(1)
    raw = econsoc_client.get_bytes(url)
    page = parse.parse_oai_page(raw)
    print(
        f"LISTRECORDS records={len(page.records)} "
        f"skipped_tombstones={page.skipped_tombstones} "
        f"has_resumption_token={page.resumption_token is not None}"
    )
    assert page.records, "TE OAI ListRecords 首页解析出 0 条记录"
    first = page.records[0]
    print(f"FIRST_RECORD doi={first.doi!r} journal={first.journal!r} title={first.title!r}")
    assert first.doi.startswith("10.3982/"), f"首条 DOI 形态异常: {first.doi!r}"
    assert first.journal == "te", f"TE 端点首条刊别应为 te，实为 {first.journal!r}"
    # 捕获首条 OAI header identifier（GetRecord 用）+ 一条带 galley 的记录（resolve 用）。
    header_id = ET.fromstring(raw).find(".//oai:record/oai:header/oai:identifier", _OAI_NS)
    if header_id is not None and header_id.text:
        _CAPTURED_OAI_ID.append(header_id.text)
    _CAPTURED.append(first)


@pytest.mark.online
def test_te_getrecord_single(
    econsoc_client: HttpClient, real_request_budget: RealRequestBudget
) -> None:
    """1 请求：以捕获的 OAI identifier 取单条 `GetRecord`（canary 活体锚）。"""
    if not _CAPTURED_OAI_ID:
        pytest.skip("需先跑 test_te_listrecords_first_page_structure 捕获 OAI identifier")
    from urllib.parse import urlencode

    params = {
        "verb": "GetRecord",
        "identifier": _CAPTURED_OAI_ID[0],
        "metadataPrefix": "oai_dc",
    }
    real_request_budget.spend(1)
    record = parse.parse_get_record(econsoc_client.get_bytes(f"{_TE_OAI}?{urlencode(params)}"))
    print(f"GETRECORD doi={record.doi!r} journal={record.journal!r} title={record.title!r}")
    assert record.journal == "te"
    assert record.doi.startswith("10.3982/te")


@pytest.mark.online
def test_te_resolve_landing_to_galley_pdf(
    econsoc_client: HttpClient, real_request_budget: RealRequestBudget
) -> None:
    """2 请求：resolve（GET 落地页抽 galley）+ galley 首 chunk 断 `%PDF`（TE 匿名 OA）。"""
    if not _CAPTURED:
        pytest.skip("需先跑 test_te_listrecords_first_page_structure 捕获真实记录")
    adapter = EconsocAdapter(http=econsoc_client)
    stub = parse.to_paper_stub(_CAPTURED[0])
    real_request_budget.spend(1)  # resolve GET 落地页
    plans = adapter.resolve_assets(_te_venue(), stub)
    if not plans:
        pytest.skip(f"落地页未抽到 galley 链（撤稿/合并/schema 漂移）: {stub.identifiers}")
    plan = plans[0]
    print(f"RESOLVE galley url={plan.url}")
    real_request_budget.spend(1)  # galley 首 chunk
    head = stream_first_chunk(econsoc_client, plan.url)
    print(f"FETCH_FIRST_CHUNK head={head[:8]!r}")
    assert head.startswith(b"%PDF"), f"galley 下载体非 PDF（前 8 字节 {head[:8]!r}）——见报告"


@pytest.mark.online
def test_ecma_current_doi_domain_route_is_econsoc(
    doi_client: httpx.Client, real_request_budget: RealRequestBudget
) -> None:
    """1 请求：当前段 ECMA DOI doi.org HEAD -L → econometricsociety.org → classify=CURRENT。"""
    real_request_budget.spend(1)
    resp = doi_client.head(f"https://doi.org/{_ECMA_CURRENT_DOI}")
    host = resp.url.host
    print(f"ECMA_CURRENT doi.org terminus host={host!r} status={resp.status_code}")
    assert "econometricsociety.org" in host, f"当前段 ECMA 未落自营域: {host!r}"
    assert (
        parse.classify_ecma_segment(_ECMA_CURRENT_DOI, landing_domain=host) is EcmaSegment.CURRENT
    )


@pytest.mark.online
def test_ecma_backfile_doi_domain_route_is_wiley(
    doi_client: httpx.Client, real_request_budget: RealRequestBudget
) -> None:
    """1 请求：过刊段 ECMA DOI doi.org HEAD -L → doi.wiley.com → classify=BACKFILE。

    闭 [UNRESOLVED②] 抽样（权威取实时落地域名）。仅读 doi.org 重定向终点域名，**不续访**
    doi.wiley.com（其 stateless 403 CF 即 BLOCKED、停手，
    §5 红线；域名核对不需要真正取 Wiley 全文）。
    """
    real_request_budget.spend(1)
    resp = doi_client.head(f"https://doi.org/{_ECMA_BACKFILE_DOI}")
    host = resp.url.host
    print(f"ECMA_BACKFILE doi.org terminus host={host!r} status={resp.status_code}")
    assert "wiley" in host, f"过刊段 ECMA 未落 Wiley 域: {host!r}"
    assert (
        parse.classify_ecma_segment(_ECMA_BACKFILE_DOI, landing_domain=host) is EcmaSegment.BACKFILE
    )


def _te_venue():  # type: ignore[no-untyped-def]
    from helpers import make_econsoc_teqe_venue

    return make_econsoc_teqe_venue("te")
