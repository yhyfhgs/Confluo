"""arXiv 在线冒烟（T7）——本项目**首个授权的真实网络任务**（AGENTS §6 真实网络纪律）。

默认经 `addopts = -m 'not online'` 排除；显式 `uv run pytest tests/online -m online` 才跑。
硬预算 `MAX_REAL_REQUESTS = 10`（`real_request_budget` fixture 逐请求记账、超限即 fail）；
所有请求共用一个 1req/3s 限速器（`arxiv_client`，UA 携真实联系人 mailto，D-014）。

AC-2.3 在线证据层（D-018）：本冒烟证实真实站点应答 + 解析入库路径打通——
- canary 选样（3 请求）：跨域 cs.LG/econ/q-fin 各取 1 篇真实稳定论文（该 category
  提交最早者——年代久远者最稳定，不会被撤稿/改标题），规整化 title + primary_category
  经输出落 adapter `_CANARIES` 常量替换占位（见 test 输出 `CANARY_CAPTURE` 行）；
- healthcheck（1 请求）：Query API canary id_list 双字段比对（`_CANARIES` 更新后为 healthy）；
- enumerate 首页（1 请求）：cs.LG 当月桶 OAI-PMH 首页真实解析出 `PaperStub`；
- 单篇 PDF fetch（1 请求）：`%PDF` 魔数断言（adapter gone-guard 透传真实 PDF 流）；
- robots/ToU 复核（1 请求）：GET export.arxiv.org/robots.txt 对照 arxiv.md §4 ⚠ 义务。

≈ 共 7 请求 ≤ 10。真实执行结果归档 scratchpad/p2-t7-online-run.txt + 验收草稿。
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from urllib.parse import urlencode

import pytest

from helpers import FakeFetchIO, make_arxiv_venue
from online.conftest import RealRequestBudget
from paper_crawler.adapters.arxiv import parse
from paper_crawler.adapters.arxiv.adapter import _CANARIES, ArxivAdapter
from paper_crawler.http import HttpClient
from paper_crawler.ratelimit import RateLimiter
from paper_crawler.types import IssueRef, PaperStub
from paper_crawler.useragent import build_user_agent

MAX_REAL_REQUESTS = 10

# 用户真实邮箱（MEMORY / 任务卡）：D-014 UA `mailto:` 段的正当用途——真实网络请求
# 需以联系人表明爬取身份，便于站点在异常时联系。不作他用。
_CONTACT_EMAIL = "yhyfhgs@gmail.com"

_QUERY_ENDPOINT = "https://export.arxiv.org/api/query"
_ROBOTS_URL = "https://export.arxiv.org/robots.txt"

# canary 选样目标域（arxiv.md §6：跨域 cs.LG / econ.* / q-fin.* 各 1）。
# 每域给一个"该 archive 上线后若干年"的日期窗（该 category 已有原生论文、且年代够久
# 足够稳定），窗内升序筛主分类即目标者——避免最早期全是旧档交叉列（主分类为
# physics/math）导致 canary 主分类不落在目标域。
_CANARY_CATEGORIES: tuple[tuple[str, str], ...] = (
    ("cs.LG", "cat:cs.LG AND submittedDate:[199901010000 TO 199912312359]"),
    ("econ.EM", "cat:econ.EM AND submittedDate:[201801010000 TO 201812312359]"),
    ("q-fin.PR", "cat:q-fin.PR AND submittedDate:[201001010000 TO 201012312359]"),
)


@pytest.fixture(scope="session")
def arxiv_client() -> Iterator[HttpClient]:
    """真实 HttpClient：UA 携真实 mailto（D-014）+ 1req/3s 限速器（三域共享一桶）。

    session 级——整轮冒烟共用一个限速器，逐请求 acquire 使全程 ≤ 1req/3s（ToU「并发 1」），
    而非每个测试各自放行。与 C4 红线修复同一机制（HttpClient 逐请求限速闸）。
    """
    limiter = RateLimiter()
    limiter.register("export.arxiv.org", ArxivAdapter.default_rate)
    limiter.alias("oaipmh.arxiv.org", "export.arxiv.org")
    limiter.alias("arxiv.org", "export.arxiv.org")
    client = HttpClient(user_agent=build_user_agent(_CONTACT_EMAIL), rate_limiter=limiter)
    try:
        yield client
    finally:
        client.close()


def _search_native_url(search_query: str) -> str:
    """Query API：给定 search_query（含日期窗）升序取一批，供客户端筛主分类原生论文。

    `cat:X` 命中主分类或交叉列表；拉一批升序结果、客户端筛 `primary_category == X`
    取最早一条 = 该窗内该 category 的早期**原生**论文（主分类正确、年代久远 → 稳定，
    贴合 arxiv.md §6 跨域语义）。
    """
    params = {
        "search_query": search_query,
        "start": "0",
        "max_results": "100",
        "sortBy": "submittedDate",
        "sortOrder": "ascending",
    }
    return f"{_QUERY_ENDPOINT}?{urlencode(params)}"


@pytest.mark.online
def test_canary_selection_captures_real_samples(
    arxiv_client: HttpClient, real_request_budget: RealRequestBudget
) -> None:
    """3 请求：跨域各取最早 1 篇，捕获真实规整化 title + primary_category。

    输出 `CANARY_CAPTURE` 行供人工把 adapter `_CANARIES` 占位替换为真实值。
    断言：每个 category 恰返回 1 条可解析记录（title 非空、有 primary_category）。
    """
    captured: list[tuple[str, str, str, str]] = []
    for category, search_query in _CANARY_CATEGORIES:
        real_request_budget.spend(1)
        data = arxiv_client.get_bytes(_search_native_url(search_query))
        records = list(parse.parse_atom_feed(data))
        assert records, f"cat:{category} 窗内无结果"
        # 优先取主分类即目标 category 的最早原生论文；无则退回最早一条（交叉列）。
        native = next((r for r in records if r.primary_category == category), None)
        rec = native if native is not None else records[0]
        assert rec.title, f"cat:{category} record has empty title"
        assert rec.primary_category, f"cat:{category} record has no primary_category"
        query_id = rec.base_id if rec.version is None else f"{rec.base_id}v{rec.version}"
        captured.append((rec.base_id, query_id, rec.primary_category, rec.title))
        # copy-paste 就绪（_Canary(base_id, query_id, title, primary_category)）：
        print(
            f"CANARY_CAPTURE cat={category} native={native is not None} "
            f"base_id={rec.base_id!r} query_id={query_id!r} "
            f"primary_category={rec.primary_category!r} title={rec.title!r}"
        )
    assert len(captured) == len(_CANARY_CATEGORIES)


@pytest.mark.online
def test_healthcheck_live_canaries_match(
    arxiv_client: HttpClient, real_request_budget: RealRequestBudget
) -> None:
    """1 请求：Query API canary id_list 双字段比对（`_CANARIES` 已替换真实值后 healthy）。

    若仍为合成占位（未替换）则会 unhealthy——运行前须先跑
    `test_canary_selection_captures_real_samples` 并据输出替换 `_CANARIES`（见模块 docstring）。
    """
    adapter = ArxivAdapter(http=arxiv_client)
    real_request_budget.spend(1)
    report = adapter.healthcheck()
    print(f"HEALTHCHECK healthy={report.healthy} detail={report.detail!r}")
    assert "unreachable" not in report.detail, f"query api unreachable: {report.detail}"
    assert report.healthy, (
        f"canary healthcheck unhealthy — 是否已用 test_canary_selection 输出替换 _CANARIES？"
        f" detail={report.detail!r}"
    )


@pytest.mark.online
def test_enumerate_current_month_first_page_parses(
    arxiv_client: HttpClient, real_request_budget: RealRequestBudget
) -> None:
    """1 请求：cs.LG 当月桶 OAI-PMH 首页真实解析出至少 1 个 `PaperStub`（不翻页）。

    只取生成器首元素（首页请求），不 drain（drain 会翻页耗预算）。cs.LG 高产 →
    set=cs 首页必含 cs.LG 主分类论文，单请求即可拿到首个 stub。
    """
    adapter = ArxivAdapter(http=arxiv_client)
    today = datetime.now(UTC).date()
    bucket = IssueRef(
        venue_id="arxiv_cs_lg",
        volume=None,
        number=f"{today.month:02d}",
        year=today.year,
        label=f"{today.year:04d}-{today.month:02d}",
        paper_count_claimed=None,
    )
    real_request_budget.spend(1)
    first_stub = next(iter(adapter.enumerate_issue(make_arxiv_venue(), bucket)), None)
    assert first_stub is not None, "cs.LG 当月桶首页未解析出任何 stub"
    arxiv_id = dict(first_stub.identifiers).get("arxiv")
    print(f"ENUMERATE_FIRST_STUB id={arxiv_id!r} title={first_stub.title!r}")
    assert arxiv_id, "首个 stub 缺 arxiv identifier"
    assert first_stub.title, "首个 stub 缺 title"


@pytest.mark.online
def test_fetch_single_pdf_has_magic(
    arxiv_client: HttpClient, real_request_budget: RealRequestBudget
) -> None:
    """1 请求：真实取回单篇 PDF，断言 `%PDF` 魔数（adapter gone-guard 透传真实流）。"""
    adapter = ArxivAdapter(http=arxiv_client)
    # 用第一个 canary 的稳定 id 取 PDF（年代久远、必然存在且有 PDF）。
    paper = PaperStub(title="canary", identifiers=(("arxiv", _CANARIES[0].base_id),))
    plan = adapter.resolve_assets(make_arxiv_venue(), paper)[0]
    io = FakeFetchIO()
    real_request_budget.spend(1)
    result = adapter.fetch_asset(plan, io)
    print(f"FETCH ok={result.ok} bytes={result.bytes_written} url={plan.url}")
    assert result.ok is True
    assert result.bytes_written > 0
    assert io.data.startswith(b"%PDF"), f"下载体非 PDF（前 8 字节 {io.data[:8]!r}）"


@pytest.mark.online
def test_robots_txt_and_tou_review(
    arxiv_client: HttpClient, real_request_budget: RealRequestBudget
) -> None:
    """1 请求：GET export.arxiv.org/robots.txt，对照 arxiv.md §4 ⚠ ToU 复核义务。

    §4 推理：export.arxiv.org robots 对通用爬虫全禁，但本 adapter 对该域仅走官方
    文档化 Query API，其程序化访问依据是 API ToU 的明确邀请，robots 网页公约不适用于
    ToU 授权的 API 消费。本测试实测 robots.txt 全文（落报告），并检查是否存在与该推理
    **明确相悖**的条款（如点名禁止 API 消费者）——有则输出 ⚠ 警告，报告中升级仲裁。
    """
    real_request_budget.spend(1)
    robots = arxiv_client.get_text(_ROBOTS_URL)
    print("ROBOTS_TXT_BEGIN")
    print(robots)
    print("ROBOTS_TXT_END")
    # robots 禁 /api 之类是**预期且一致**的（robots 管网页爬虫，ToU 管 API）——不视为相悖。
    # 只有"点名禁止 API/程序化消费"这类**直接否定 ToU 邀请**的条款才需升级。
    lowered = robots.lower()
    contradiction = "terms of use" in lowered and "api" in lowered and "disallow" in lowered
    if contradiction:
        print(
            "⚠ ROBOTS_TOU_REVIEW: robots.txt 疑似含与『ToU 授权 API 访问』相悖条款——"
            "报告中升级 decision-log 仲裁（arxiv.md §4 / AC-0.5）"
        )
    # 结构性断言：能取到非空 robots 文本即证明该域可达且响应正常（复核已落输出）。
    assert robots.strip(), "robots.txt 为空"
