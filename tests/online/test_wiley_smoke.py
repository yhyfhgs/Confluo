"""Wiley TDM 在线冒烟（Phase 4 T-wiley；design/adapters/wiley.md §6）。

默认经 `addopts = -m 'not online'` 排除；显式 `uv run pytest tests/online -m online` 才跑。
硬预算 `MAX_REAL_REQUESTS = 1`（wiley.md §6：token 到位后已知有权 DOI 单篇 1，≤1）。

**token 门控 skip（诚实 skip，不伪通过；D-024，s2 先例）**：Wiley TDM token 未配置——
`pytest.mark.skipif` 而非模块级无条件 `skip`：无 token 时**收集但标记 skip**，供 CI/本地一眼
看出"存在但未跑"，而非整文件消失。token 自助可得但 entitlement 受机构订阅约束（R0
[LIVE 2026-07-23]），故本文件"只写不跑"随本次改动落盘，token 到位即活。

**token 到手后的操作者检查单**（详见 tests/manual/wiley_runbook.md）：

1. 按 runbook 自助获取 TDM token（WOL 个人账号 → click-through TDM license → UUID）。
2. 设 `PAPER_CRAWLER_WILEY_TDM_TOKEN` 为真实 token（否则本文件 skip，不算失败）。
3. 把 `_SMOKE_DOI` 核准为一个已知可取回（理想：开放获取，只需 token 连通、不依赖机构
   订阅）的 Wiley DOI——当前为 [PENDING token-verify] 占位（与 adapter `_HEALTHCHECK_DOI`
   同源）。若该 DOI 无权 → 403 no_entitlement，是订阅域约束的预期信号，换一个有权/OA DOI。
4. `uv run pytest tests/online/test_wiley_smoke.py -m online -v`；核对 `SMOKE_CAPTURE` 行
   （`%PDF` 魔数 + 字节数）。
5. **首次真实 token 冒烟须审计实际 429 触发行为**（wiley.md §7），据以校准双窗口稳态限速值。
6. 执行结果归档 `docs/testing/records/`（沿既有惯例）。

单请求覆盖面：`resolve_assets` → `fetch_asset` 一次真实 TDM 取回，验证「端点可达」+「token
头连通」+「返回 PDF 魔数」——这也是"token 是否真的生效 + 有该刊 entitlement"的最直接证据。
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

from helpers import FakeFetchIO, make_wiley_venue
from online.conftest import RealRequestBudget
from paper_crawler.adapters.wiley.adapter import _HEALTHCHECK_DOI, TDM_TOKEN_HEADER, WileyAdapter
from paper_crawler.http import HttpClient
from paper_crawler.types import PaperStub
from paper_crawler.useragent import build_user_agent

MAX_REAL_REQUESTS = 1

_WILEY_TOKEN = os.environ.get("PAPER_CRAWLER_WILEY_TDM_TOKEN", "").strip()

# ⚠ [PENDING token-verify]：与 adapter `_HEALTHCHECK_DOI` 同源占位——token 到手后按模块
# docstring 检查单第 3 步核准为已知可取回 DOI。
_SMOKE_DOI = _HEALTHCHECK_DOI


@pytest.fixture
def wiley_client() -> Iterator[HttpClient]:
    """真实 HttpClient：`Wiley-TDM-Client-Token` 头携真实 token（凭证隔离——本 client 只在
    本文件的独立测试进程内构造，不与其它 adapter 共享，同 CLI 装配期的隔离原则）。"""
    client = HttpClient(
        user_agent=build_user_agent(os.environ.get("PAPER_CRAWLER_CONTACT_EMAIL")),
        extra_headers={TDM_TOKEN_HEADER: _WILEY_TOKEN},
    )
    try:
        yield client
    finally:
        client.close()


@pytest.mark.online
@pytest.mark.skipif(
    not _WILEY_TOKEN,
    reason="PAPER_CRAWLER_WILEY_TDM_TOKEN 未设——token 未配置，诚实 skip 不伪通过（D-024）",
)
def test_tdm_fetch_single_article_when_token_configured(
    wiley_client: HttpClient, real_request_budget: RealRequestBudget
) -> None:
    """1 请求：有 token 时对已知 DOI resolve→fetch，断言落盘 `%PDF` 魔数（wiley.md §3/§6）。"""
    adapter = WileyAdapter(http=wiley_client, token=_WILEY_TOKEN)
    paper = PaperStub(title="Wiley smoke", identifiers=(("doi", _SMOKE_DOI),))
    plan = adapter.resolve_assets(make_wiley_venue(), paper)[0]

    io = FakeFetchIO()
    real_request_budget.spend(1)
    result = adapter.fetch_asset(plan, io)

    print(
        f"SMOKE_CAPTURE doi={_SMOKE_DOI!r} ok={result.ok} bytes={result.bytes_written} "
        f"is_pdf={io.data[:5]!r}"
    )
    assert result.ok is True
    assert io.data.startswith(b"%PDF"), (
        f"TDM fetch did not return a PDF for {_SMOKE_DOI!r} — token invalid, no entitlement "
        f"(403), or wrong DOI; see module docstring operator checklist. head={io.data[:32]!r}"
    )
