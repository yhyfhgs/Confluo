"""OpenAlex 在线冒烟（T6；design/adapters/aggregators.md §5.3/§8）。

默认经 `addopts = -m 'not online'` 排除；显式 `uv run pytest tests/online -m online`
才跑。硬预算 `MAX_REAL_REQUESTS = 1`（aggregators.md §8 T6 在线冒烟表："openalex：
单 filter 查 1（读 cost_usd）（≤1）"——本源在 Phase 3 总预算 ≤100 请求里占 1 条）。

**本文件按任务契约"只写不跑"**：随本次改动一并落盘，但未在本次任务里实际执行
（需要真实网络请求，超出"零真实网络"实现门禁的范围）。首次执行前的操作者检查单：

1.（可选）设置 `PAPER_CRAWLER_OPENALEX_API_KEY` 提升每日额度——本文件**无 key 也应
   可跑**（openalex 匿名请求现状 [LIVE] 200，见 adapter.py 模块 docstring"key 可选"；
   与 s2 的强制 key 门控不同，本文件不因缺 key 而 `skip`）。
2. `uv run pytest tests/online/test_openalex_smoke.py -m online -v`。
3. 核对输出 `ENRICH_CAPTURE` 行：`cost_usd` 应为一个小额正浮点数（真实计费信号）；
   本用例使用的 DOI 是 D-019 **负锚点**（`10.1257/aer.20221079`，aggregators.md §7：
   "该 DOI 三源证实不存在"）——预期 `results=[]`（count:0），若某天该 DOI 意外出现
   结果，属站点数据变化（如撤稿元数据回填），按 UPDATE_GOLDEN 纪律核实后调整锚点，
   不代表本层代码有缺陷。
4. 执行结果归档 `docs/testing/records/`（沿 D-019 惯例）。

单请求覆盖面：`enrich_batch([doi])` 内部即 `GET /works?filter=doi:...` 一次请求，
同时验证「真实站点可达」+「空结果正确解析」+「`meta.cost_usd` 真实读取并落盘预算
状态文件」三件事。
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from online.conftest import RealRequestBudget
from paper_crawler.adapters.openalex import budget
from paper_crawler.adapters.openalex.adapter import OpenAlexAdapter
from paper_crawler.http import HttpClient
from paper_crawler.useragent import build_user_agent

MAX_REAL_REQUESTS = 1

# D-019 负锚点（aggregators.md §7）：该 DOI 经三源核实不存在，count 恒为 0——用作
# "零真实数据泄露风险 + 有把握的确定性断言"的探测目标（不依赖任何论文的具体元数据
# 措辞，不会因出版社修订标题/摘要而漂移）。
_NEGATIVE_ANCHOR_DOI = "10.1257/aer.20221079"


@pytest.fixture
def openalex_client() -> Iterator[HttpClient]:
    """真实 HttpClient：D-014 UA（email 可选，openalex 不强制 mailto）。单请求场景
    不需要共享限速器（同 unpaywall 冒烟先例）。
    """
    contact_email = os.environ.get("PAPER_CRAWLER_CONTACT_EMAIL")
    client = HttpClient(user_agent=build_user_agent(contact_email))
    try:
        yield client
    finally:
        client.close()


@pytest.mark.online
def test_enrich_batch_negative_anchor_returns_empty_and_records_cost(
    openalex_client: HttpClient, real_request_budget: RealRequestBudget, tmp_path: Path
) -> None:
    """1 请求：D-019 负锚点 DOI → 空结果列表 + 预算状态文件正确记账真实 `cost_usd`。"""
    adapter = OpenAlexAdapter(http=openalex_client)
    adapter.set_api_key(os.environ.get("PAPER_CRAWLER_OPENALEX_API_KEY"))
    state_path = tmp_path / "openalex-budget.json"
    adapter.configure_budget(daily_budget_usd=0.50, state_path=state_path)
    real_request_budget.spend(1)

    stubs = adapter.enrich_batch([_NEGATIVE_ANCHOR_DOI])
    state = budget.load_state(state_path)

    print(
        f"ENRICH_CAPTURE doi={_NEGATIVE_ANCHOR_DOI!r} stub_count={len(stubs)} "
        f"cost_usd_spent={state.spent_usd!r}"
    )
    assert stubs == [], (
        f"expected empty result for negative-anchor DOI {_NEGATIVE_ANCHOR_DOI!r} "
        f"(D-019 §7: confirmed absent across three sources), got {len(stubs)} stub(s) — "
        "if this is a genuine new indexing, update the D-019 anchor per UPDATE_GOLDEN, "
        "don't assume a code bug"
    )
    assert state.spent_usd > 0.0, "meta.cost_usd should have been read and persisted as > 0"
