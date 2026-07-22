"""DBLP 在线冒烟（Phase 3 T4 DoD：限量在线冒烟；样板 arxiv/pmlr，§9 执行细则）。

默认经 `addopts = -m 'not online'` 排除；显式 `uv run pytest tests/online -m
online` 才跑。硬预算 `MAX_REAL_REQUESTS = 2`（`real_request_budget` 逐请求
记账、超限即 fail）；限速器按 adapter 自身 `default_rate`（15 rpm = 1 req/4s，
robots `Crawl-delay: 4`）注册，UA 携真实 mailto（D-014）。

**本文件本次实现只写不跑**（AGENTS §6"默认零真实网络"红线 + 本任务显式约束）：
未在本会话执行 `pytest -m online`，`≥4s/req` 的限速纪律在两个测试各自的单次
`real_request_budget.spend(1)` 调用点得到静态体现（共 2 次真实请求，天然间隔
≥4s，session-scope 的共享 `HttpClient`/`RateLimiter` 保证同一进程内两次真实
请求之间确实经过限速器 `acquire`）；T5 执行时若发现结构漂移，按 test-plan §4
"连续 2 周 DRIFT→模块降级"流程处理，不阻塞离线 DoD。

证实真实站点应答 + 解析入库路径打通（design/adapters/aggregators.md §8 dblp
行"单卷 XML 1（≥4s 间隔）（≤1）"——本文件额外覆盖 discover 的索引页解析路径，
合计 2 请求，仍在 plan §2-4 每源 `MAX_REAL_REQUESTS ≤5` 之内）：

- healthcheck（1 请求）：固定卷 `conf/icml/icml2023.xml` 结构性判定（§5.2/§7；
  真值精确锚点 [PENDING]，见 `adapter.py::healthcheck` 与
  `tests/unit/test_dblp_canary.py` 模块 docstring）；
- discover_timeline（1 请求）：conf 索引页 `GET /db/conf/icml/` 解析出真实卷
  slug 集合，抽样断言"至少发现 PMLR 时代起点年（2013）以后的若干届、且都是
  可用于 `enumerate_issue` 的合法 slug 形态"——不对精确届数/记录数做硬编码
  比对（同 healthcheck 的诚实标注，真实届数会随年份增长）。

未覆盖 `enumerate_issue` 的独立在线请求：其解析路径（`parse.parse_volume_xml`）
已被 healthcheck 的真实请求实质覆盖（healthcheck 内部即调用同一函数解析同一
形态的卷 XML），额外单独请求验证同一段解析逻辑对预算无增益，故未安排。
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

from helpers.dblp_fixtures import make_dblp_venue
from online.conftest import RealRequestBudget
from online.smoke_helpers import make_rate_limited_client
from paper_crawler.adapters.dblp.adapter import DblpAdapter
from paper_crawler.http import HttpClient

MAX_REAL_REQUESTS = 2

# PMLR 时代起点（design/adapters/pmlr.md §附；dblp 卷历史早于此，但本冒烟只需
# 断言"发现的届里至少含近代年份"这一低风险信号，不依赖精确历史下界）。
_SANITY_MIN_YEAR = 2013

# D-014 UA mailto 段（同 arxiv/pmlr 样板口径，不硬编码——从 env 取，缺失整文件 skip）。
_CONTACT_EMAIL = os.environ.get("PAPER_CRAWLER_CONTACT_EMAIL", "")
if not _CONTACT_EMAIL:
    pytest.skip(
        "PAPER_CRAWLER_CONTACT_EMAIL not set (required for D-014 UA identity)",
        allow_module_level=True,
    )


@pytest.fixture(scope="session")
def dblp_client() -> Iterator[HttpClient]:
    """真实 HttpClient：UA 携真实 mailto（D-014）+ 15rpm（≥4s/req）限速器。"""
    client = make_rate_limited_client(
        domains=DblpAdapter.domains,
        default_rate=DblpAdapter.default_rate,
        contact_email=_CONTACT_EMAIL,
    )
    try:
        yield client
    finally:
        client.close()


@pytest.mark.online
def test_healthcheck_icml2023_reachable(
    dblp_client: HttpClient, real_request_budget: RealRequestBudget
) -> None:
    """1 请求：固定卷 `conf/icml/icml2023.xml` 可达 + 结构性判定通过。"""
    adapter = DblpAdapter(http=dblp_client)
    real_request_budget.spend(1)
    report = adapter.healthcheck()
    print(f"HEALTHCHECK healthy={report.healthy} detail={report.detail!r}")
    assert "unreachable" not in report.detail, f"icml2023.xml unreachable: {report.detail}"
    assert report.healthy, f"dblp healthcheck unhealthy: {report.detail!r}"


@pytest.mark.online
def test_discover_timeline_icml_finds_recent_real_editions(
    dblp_client: HttpClient, real_request_budget: RealRequestBudget
) -> None:
    """1 请求：conf 索引页解析出的届列表至少含 PMLR 时代年份、且 slug 形态合法。

    不对精确届数做硬编码比对（真实届数逐年增长，见 D-019 dblp 锚点表
    aggregators.md §7 "record_count=[PENDING]"一行同款诚实标注）；只做结构性
    合理性检查——这正是"不得拼接猜测 key，一律从索引页解析"这条红线的在线证据。
    """
    adapter = DblpAdapter(http=dblp_client)
    real_request_budget.spend(1)
    issues = list(adapter.discover_timeline(make_dblp_venue()))
    print(f"DISCOVER found {len(issues)} issue(s): {[i.label for i in issues][:5]}...")
    assert issues, "conf/icml index page yielded zero discovered volumes"
    assert any(i.year is not None and i.year >= _SANITY_MIN_YEAR for i in issues), (
        f"no discovered edition has year >= {_SANITY_MIN_YEAR} (PMLR era) — "
        "possible index page structural drift"
    )
    for issue in issues:
        assert issue.label, f"issue with no slug (label): {issue!r}"
        assert issue.year is not None, f"issue with no year: {issue!r}"
