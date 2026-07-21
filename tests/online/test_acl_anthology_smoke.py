"""ACL Anthology 在线冒烟（Phase 2 DoD：每 adapter 一个限量在线冒烟；样板 arxiv）。

默认经 `addopts = -m 'not online'` 排除。硬预算 `MAX_REAL_REQUESTS = 5`；请求共用一个
30rpm 限速器（`acl_client`，`raw.githubusercontent.com` 主域 + `aclanthology.org`
alias），UA 携真实 mailto（D-014）。**不触 api.github.com**（60 req/hr 匿名上限——冒烟
走 raw bulk + 站点 PDF 两域即可，避开 GitHub API 预算）。

证实真实站点应答 + 解析入库路径打通（AC-2.5 在线证据层）：
- schema.rnc（1 请求，raw bulk 路径）：含 `Collection`/`Paper` 元素定义（同时验证
  `master` 分支名正确，acl-anthology.md §4 healthcheck bulk 项）；
- 2023.emnlp.xml（1 请求，整拉≈2.27MB 可接受）：`parse_collection_xml` 解出 `main`
  卷论文数 == D-019 锚点 **1047**（site-survey/acl-anthology.md §7 anchor 表；main =
  long+short 合并单一 `<paper>` 序列）；
- 单篇 PDF 首 chunk（1 请求，站点 PDF 兜底路径）：`%PDF` 魔数（捕获自 main 卷首篇的
  真实 anthology id → resolve `aclanthology.org/{id}.pdf`）。

≈ 共 3 请求 ≤ 5。真实执行结果归档 scratchpad/online-smoke-batch-run.txt。
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

from helpers import make_acl_anthology_venue
from online.conftest import RealRequestBudget
from online.smoke_helpers import make_rate_limited_client, stream_first_chunk
from paper_crawler.adapters.acl_anthology import parse
from paper_crawler.adapters.acl_anthology.adapter import _RAW_BASE, _SCHEMA_URL, AclAnthologyAdapter
from paper_crawler.http import HttpClient
from paper_crawler.types import PaperStub

MAX_REAL_REQUESTS = 5

# D-019 锚点：2023.emnlp.xml 的 `main` 卷（long+short 合并）= 1047 篇（site-survey §7）。
_EMNLP2023_MAIN_ANCHOR = 1047
_EMNLP2023_XML_URL = f"{_RAW_BASE}2023.emnlp.xml"

_CONTACT_EMAIL = os.environ.get("PAPER_CRAWLER_CONTACT_EMAIL", "")
if not _CONTACT_EMAIL:
    pytest.skip(
        "PAPER_CRAWLER_CONTACT_EMAIL not set (required for D-014 UA identity)",
        allow_module_level=True,
    )

_CAPTURED: list[PaperStub] = []


@pytest.fixture(scope="session")
def acl_client() -> Iterator[HttpClient]:
    """真实 HttpClient：UA 携真实 mailto（D-014）+ 30rpm 限速器（raw 主域 + 站点 alias）。"""
    client = make_rate_limited_client(
        domains=AclAnthologyAdapter.domains,
        default_rate=AclAnthologyAdapter.default_rate,
        contact_email=_CONTACT_EMAIL,
    )
    try:
        yield client
    finally:
        client.close()


@pytest.mark.online
def test_schema_rnc_reachable_with_expected_elements(
    acl_client: HttpClient, real_request_budget: RealRequestBudget
) -> None:
    """1 请求：raw `schema.rnc` 含 `Collection`/`Paper` 元素定义（bulk 路径 + master 分支）。"""
    real_request_budget.spend(1)
    schema = acl_client.get_bytes(_SCHEMA_URL).decode("utf-8", errors="replace")
    print(f"SCHEMA_RNC bytes={len(schema)} url={_SCHEMA_URL}")
    assert "Collection = element collection" in schema, "schema.rnc 缺 Collection 元素定义"
    assert "Paper = element paper" in schema, "schema.rnc 缺 Paper 元素定义"


@pytest.mark.online
def test_emnlp2023_main_volume_count_matches_anchor(
    acl_client: HttpClient, real_request_budget: RealRequestBudget
) -> None:
    """1 请求：2023.emnlp.xml 的 `main` 卷解析论文数 == D-019 锚点 1047。"""
    real_request_budget.spend(1)
    data = acl_client.get_bytes(_EMNLP2023_XML_URL)
    collection = parse.parse_collection_xml(data)
    main = next((v for v in collection.volumes if v.id == "main"), None)
    assert main is not None, (
        f"2023.emnlp.xml 无 id=='main' 卷（实得 {[v.id for v in collection.volumes]!r}）"
    )
    print(
        f"ENUMERATE 2023.emnlp main parsed={len(main.papers)} anchor={_EMNLP2023_MAIN_ANCHOR} "
        f"volumes={[(v.id, len(v.papers)) for v in collection.volumes]!r}"
    )
    assert len(main.papers) == _EMNLP2023_MAIN_ANCHOR, (
        f"2023.emnlp main 解析出 {len(main.papers)} 篇，与 D-019 锚点 {_EMNLP2023_MAIN_ANCHOR} 不符"
    )
    # 捕获 main 卷首篇 → to_paper_stub（供 PDF 测试端到端复用真实 anthology id）。
    stub = parse.to_paper_stub(
        collection.id,
        main.id,
        main.papers[0],
        track=main.id,
        volume_year=main.year,
        volume_month=main.month,
    )
    _CAPTURED.append(stub)
    print(f"CAPTURED id={stub.identifiers!r}")


@pytest.mark.online
def test_fetch_single_pdf_first_chunk_is_pdf(
    acl_client: HttpClient, real_request_budget: RealRequestBudget
) -> None:
    """1 请求：resolve 真实 stub → `aclanthology.org/{id}.pdf` stream 首 chunk 断 `%PDF`。"""
    if not _CAPTURED:
        pytest.skip("需先跑 test_emnlp2023_main_volume_count_matches_anchor 捕获真实 stub")
    adapter = AclAnthologyAdapter(http=acl_client)
    plan = adapter.resolve_assets(make_acl_anthology_venue(), _CAPTURED[0])[0]
    real_request_budget.spend(1)
    head = stream_first_chunk(acl_client, plan.url)
    print(f"FETCH_FIRST_CHUNK url={plan.url} head={head[:8]!r}")
    assert head.startswith(b"%PDF"), f"下载体非 PDF（前 8 字节 {head[:8]!r}）"
