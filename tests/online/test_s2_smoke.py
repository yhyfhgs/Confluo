"""Semantic Scholar (S2) 在线冒烟（T6；design/adapters/aggregators.md §5.4/§8）。

默认经 `addopts = -m 'not online'` 排除；显式 `uv run pytest tests/online -m online`
才跑。硬预算 `MAX_REAL_REQUESTS = 1`（aggregators.md §8 T6 在线冒烟表："s2：按 key
存在性 skip（无 key → pytest skipif 不发请求...）（≤1）"）。

**按 key 存在性 skip 门控（诚实 skip，不伪通过）**：S2 key 用户申请中——`pytest.mark.
skipif` 而非模块级无条件 `pytest.skip`（区别于 crossref/unpaywall 的"缺 email 整
文件 skip"先例）：本文件在**无 key 时收集但标记 skip**，供 CI/本地一眼看出"存在
但未跑"，而非"整个文件消失不可见"。

**本文件按任务契约"只写不跑"**：随本次改动一并落盘，未在本次任务里实际执行（S2 key
尚未到手，也超出"零真实网络"实现门禁的范围）。key 到手后的操作者检查单：

1. 设置 `PAPER_CRAWLER_S2_API_KEY` 为真实 key（否则本文件测试 skip，不算失败）。
2. `uv run pytest tests/online/test_s2_smoke.py -m online -v`。
3. 核对输出 `HEALTHCHECK_CAPTURE` 行：真实 title 应与 `_HEALTHCHECK_DOI`
   （"Attention Is All You Need"）比对一致；若漂移/未命中，按 UPDATE_GOLDEN 纪律
   人工核准后更新 `adapter.py` 的 `_HEALTHCHECK_TITLE`。
4. 执行结果（通过/漂移/skip）归档 `docs/testing/records/`（沿 D-019 惯例）。

单请求覆盖面：`adapter.healthcheck()` 内部即 `GET /paper/DOI:{固定DOI}?fields=title`
一次请求，验证「真实站点可达」+「有 key 时不再是 404 not-found」+「title 字段解析」
三件事——这也是"key 是否真的生效"的最直接证据（无 key 症状 D2 是 404，与本用例的
预期成功响应形成对照）。
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

from online.conftest import RealRequestBudget
from paper_crawler.adapters.s2.adapter import _HEALTHCHECK_DOI, S2Adapter
from paper_crawler.http import HttpClient
from paper_crawler.useragent import build_user_agent

MAX_REAL_REQUESTS = 1

_S2_API_KEY = os.environ.get("PAPER_CRAWLER_S2_API_KEY", "").strip()


@pytest.fixture
def s2_client() -> Iterator[HttpClient]:
    """真实 HttpClient：`x-api-key` 头携真实 key（凭证隔离——本 client 只在本文件
    的独立测试进程内构造，不与其它 adapter 共享，同 CLI `enrich` 装配期的隔离原则，
    见 `cli.py::_prepare_enrich_source` docstring）。单请求场景不需要共享限速器。
    """
    client = HttpClient(
        user_agent=build_user_agent(os.environ.get("PAPER_CRAWLER_CONTACT_EMAIL")),
        extra_headers={"x-api-key": _S2_API_KEY},
    )
    try:
        yield client
    finally:
        client.close()


@pytest.mark.online
@pytest.mark.skipif(
    not _S2_API_KEY,
    reason="PAPER_CRAWLER_S2_API_KEY 未设——S2 key 用户申请中，诚实 skip 不伪通过（D2）",
)
def test_healthcheck_matches_anchor_when_key_configured(
    s2_client: HttpClient, real_request_budget: RealRequestBudget
) -> None:
    """1 请求：有 key 时固定 DOI 的 `healthcheck()` 比对规整化 title（§5.4）。"""
    adapter = S2Adapter(http=s2_client)
    adapter.set_api_key(_S2_API_KEY)
    real_request_budget.spend(1)

    report = adapter.healthcheck()

    print(
        f"HEALTHCHECK_CAPTURE doi={_HEALTHCHECK_DOI!r} healthy={report.healthy} "
        f"detail={report.detail!r}"
    )
    assert "unreachable" not in report.detail, f"s2 unreachable: {report.detail}"
    assert report.healthy, (
        f"healthcheck unhealthy against anchor DOI {_HEALTHCHECK_DOI!r} — "
        f"see module docstring UPDATE_GOLDEN steps before assuming a code bug: "
        f"detail={report.detail!r}"
    )
