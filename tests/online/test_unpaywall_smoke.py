"""Unpaywall 在线冒烟（T5；design/adapters/aggregators.md §5.5/§8）。

默认经 `addopts = -m 'not online'` 排除；显式 `uv run pytest tests/online -m online`
才跑。硬预算 `MAX_REAL_REQUESTS = 1`（design/adapters/aggregators.md §8 T5 在线冒烟表：
"unpaywall：单已知金色 DOI 1（≤1）"——本源在 Phase 3 总预算 ≤100 请求里占 1 条）。

**本文件按任务契约"只写不跑"**：随本次改动一并落盘，但未在本次任务里实际执行
（需要真实 `PAPER_CRAWLER_CONTACT_EMAIL` 且发起真实网络请求，超出"零真实网络"
实现门禁的范围）。首次执行前的操作者检查单：

1. 设置 `PAPER_CRAWLER_CONTACT_EMAIL` 为真实可联系邮箱（否则整文件 `skip`，见下）。
2. `uv run pytest tests/online/test_unpaywall_smoke.py -m online -v`。
3. 核对输出 `HEALTHCHECK_CAPTURE` 行：若 D-019 锚点 DOI
   （`10.1371/journal.pmed.0020124`）的真实 `is_oa`/`oa_status` 与
   `adapter._HEALTHCHECK_EXPECT_IS_OA`/`_HEALTHCHECK_EXPECT_OA_STATUS` 不一致
   （罕见——OA 状态理论上不回退，但站点数据可能修订），按 UPDATE_GOLDEN 纪律人工
   核准后更新 `adapter.py` 的两个常量 + `tests/fixtures/unpaywall/
   01_normal_gold_fallback.json` 的 `_grounded` 字段说明。
4. 执行结果（通过/漂移）归档 `docs/testing/records/`（沿 D-019 惯例）。

单请求覆盖面：`adapter.healthcheck()` 内部即 `GET /v2/{固定金 OA DOI}?email=<addr>`
一次请求，同时验证「真实站点可达」+「is_oa/oa_status 双字段比对」两件事——D-019
锚点表本身就是 healthcheck 的复用对象，无需额外请求。
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

from online.conftest import RealRequestBudget
from paper_crawler.adapters.unpaywall.adapter import (
    _HEALTHCHECK_DOI,
    _HEALTHCHECK_EXPECT_IS_OA,
    _HEALTHCHECK_EXPECT_OA_STATUS,
    UnpaywallAdapter,
)
from paper_crawler.http import HttpClient
from paper_crawler.useragent import build_user_agent

MAX_REAL_REQUESTS = 1

# D-014 UA `mailto:` 段 + unpaywall `?email=` 查询参数：真实网络请求需以联系人表明
# 爬取身份（同 arxiv/openreview T7 先例，不硬编码——操作者负责提供联络身份）。
_CONTACT_EMAIL = os.environ.get("PAPER_CRAWLER_CONTACT_EMAIL", "")
if not _CONTACT_EMAIL:
    pytest.skip(
        "PAPER_CRAWLER_CONTACT_EMAIL not set (required for D-014 UA + unpaywall ?email=)",
        allow_module_level=True,
    )


@pytest.fixture
def unpaywall_client() -> Iterator[HttpClient]:
    """真实 HttpClient：UA 携真实 mailto（D-014）。单请求场景不需要共享限速器
    （5 req/s 对 1 次请求恒不触顶），故不额外挂 `RateLimiter`（与 arxiv/openreview
    的 session 级限速 fixture不同——那些覆盖多请求场景）。
    """
    client = HttpClient(user_agent=build_user_agent(_CONTACT_EMAIL))
    try:
        yield client
    finally:
        client.close()


@pytest.mark.online
def test_healthcheck_matches_gold_anchor_doi(
    unpaywall_client: HttpClient, real_request_budget: RealRequestBudget
) -> None:
    """1 请求：D-019 金 OA DOI 锚点 `healthcheck()` 比对 `is_oa`+`oa_status`。

    锚点 `10.1371/journal.pmed.0020124`（Ioannidis 2005，aggregators.md §7）
    [LIVE] 2026-07-22 核验值：`is_oa=True`、`oa_status="gold"`——不太可能随时间推移
    回退（已发表金色 OA 论文极少被撤销开放状态），若漂移属真实站点数据变化信号，
    按模块 docstring 的 UPDATE_GOLDEN 纪律处理，而非测试本身的缺陷。
    """
    adapter = UnpaywallAdapter(http=unpaywall_client, email=_CONTACT_EMAIL)
    real_request_budget.spend(1)

    report = adapter.healthcheck()

    print(
        f"HEALTHCHECK_CAPTURE doi={_HEALTHCHECK_DOI!r} healthy={report.healthy} "
        f"detail={report.detail!r} expected_is_oa={_HEALTHCHECK_EXPECT_IS_OA!r} "
        f"expected_oa_status={_HEALTHCHECK_EXPECT_OA_STATUS!r}"
    )
    assert "unreachable" not in report.detail, f"unpaywall unreachable: {report.detail}"
    assert report.healthy, (
        f"healthcheck unhealthy against gold anchor DOI {_HEALTHCHECK_DOI!r} — "
        f"see module docstring UPDATE_GOLDEN steps before assuming a test bug: "
        f"detail={report.detail!r}"
    )
