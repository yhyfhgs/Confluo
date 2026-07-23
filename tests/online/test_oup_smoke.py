"""OUP（Silverchair）在线冒烟 —— **仅匿名面**（oup-silverchair.md §7）。

默认经 `addopts = -m 'not online'` 排除；显式 `uv run pytest tests/online -m online` 才跑。
硬预算 `MAX_REAL_REQUESTS = 2`（robots 复核 + 1 篇 QJE 文章页 URL 模式确认）。

**红线严格遵守**（AGENTS §6 / AC-0.2 / AC-4.6）：OUP 需 SSO session，**匿名必撞 403
Cloudflare challenge** —— 本冒烟**只**做匿名探测（robots 一致性 + 断言文章页 challenge
特征即停），**绝不触登录态、绝不重试绕过、绝无破解**。真实全文取回归 runbook（用户参与层，
`tests/manual/oup_runbook.md`）。

**本文件本次实现只写不跑**（无 OUP 凭证 + 本任务"零在线请求"硬约束 + AGENTS §6"默认零
真实网络"）：未在本会话执行 `pytest -m online`（同 dblp 冒烟"只写不跑"先例）。执行前置：
`PAPER_CRAWLER_CONTACT_EMAIL` 已设（D-014 UA mailto，缺失整文件 skip）。

**为何用裸 httpx 而非共享 `HttpClient`**：challenge 是 `403`，共享 `HttpClient` 的冻结错误
映射在 ≥400 处即 raise（403→NO_ENTITLEMENT）会吞掉挑战页 headers/body，无从用
`ChallengeDetector` 判读——同 adapter.py 专属 client 的取舍（见其模块 docstring）。
"""

from __future__ import annotations

import os
import urllib.robotparser
from collections.abc import Iterator

import httpx
import pytest

from online.conftest import RealRequestBudget
from paper_crawler.auth.challenge import ChallengeDetector, ClassifyResult
from paper_crawler.useragent import build_user_agent

MAX_REAL_REQUESTS = 2

_ROBOTS_URL = "https://academic.oup.com/robots.txt"
# US-9 样例前缀 10.1093/qje/…（oup-silverchair.md §7 / R0 O2 实测过的 QJE 文章路径模式）。
_QJE_ARTICLE_URL = "https://academic.oup.com/qje/article/141/3/2205/8662148"
_QJE_ARTICLE_PDF_PATH = "/qje/article-pdf/141/3/2205/61701561/qjae044.pdf"

_CONTACT_EMAIL = os.environ.get("PAPER_CRAWLER_CONTACT_EMAIL", "")
if not _CONTACT_EMAIL:
    pytest.skip(
        "PAPER_CRAWLER_CONTACT_EMAIL not set (required for D-014 UA identity)",
        allow_module_level=True,
    )

_UA = build_user_agent(_CONTACT_EMAIL)
_DETECTOR = ChallengeDetector()


@pytest.fixture(scope="session")
def anon_client() -> Iterator[httpx.Client]:
    """裸匿名 httpx client（UA 携真实 mailto，D-014；**无 cookie，不触登录态**）。

    专属裸 client（非共享 HttpClient）以保留 403 挑战页的 headers/body 供判读（见模块
    docstring）；follow_redirects 保留以观察真实落点 URL 模式。
    """
    client = httpx.Client(headers={"User-Agent": _UA}, follow_redirects=True, timeout=30.0)
    try:
        yield client
    finally:
        client.close()


@pytest.mark.online
def test_robots_allows_qje_article_paths(
    anon_client: httpx.Client, real_request_budget: RealRequestBudget
) -> None:
    """1 请求：robots 复核——QJE `article`/`article-pdf` 路径对我方 UA 放行（design §2）。

    R0 [LIVE 2026-07-23]：OUP robots 无 AI-bot 条目、无 Crawl-delay，目标刊 article/
    article-pdf 未禁。此测在线复核该结论仍成立（漂移=结构信号，按 test-plan §4 处置）。
    """
    real_request_budget.spend(1)
    resp = anon_client.get(_ROBOTS_URL)
    assert resp.status_code == 200, f"robots.txt 不可达：{resp.status_code}"

    rp = urllib.robotparser.RobotFileParser()
    rp.parse(resp.text.splitlines())
    assert rp.can_fetch(_UA, _QJE_ARTICLE_URL), "robots 禁了 QJE article 路径（与 R0 结论相悖）"
    assert rp.can_fetch(_UA, f"https://academic.oup.com{_QJE_ARTICLE_PDF_PATH}"), (
        "robots 禁了 QJE article-pdf 路径（与 R0 结论相悖）"
    )
    print(f"ROBOTS ok: article + article-pdf allowed for UA={_UA!r}")


@pytest.mark.online
def test_anonymous_qje_article_is_challenge_and_stop(
    anon_client: httpx.Client, real_request_budget: RealRequestBudget
) -> None:
    """1 请求：匿名 GET QJE 文章页 → 断言 `ChallengeDetector` 判 CHALLENGE 即停（红线）。

    证实 adapter 设计前提"匿名程序化访问不可行、登录 session 态为工作前提"（design §2）；
    命中挑战即**停**——不重试、不绕过、不破解（AC-0.2/4.6）。R0 [LIVE] 观测为 403
    `cf-mitigated: challenge`；此处按判定器结果断言（对 header/body 特征稳健，不硬编状态码）。
    """
    real_request_budget.spend(1)
    resp = anon_client.get(_QJE_ARTICLE_URL)
    result = _DETECTOR.classify(
        status=resp.status_code,
        headers=dict(resp.headers),
        final_url=str(resp.url),
        body=resp.content,
    )
    print(
        f"ANON_ARTICLE status={resp.status_code} "
        f"cf-mitigated={resp.headers.get('cf-mitigated')!r} classify={result.value}"
    )
    assert result is ClassifyResult.CHALLENGE, (
        f"匿名 QJE 文章页未判为 CHALLENGE（实得 {result.value}，status={resp.status_code}）——"
        "R0 挑战前提疑似漂移，按 test-plan §4 处置；**不得**据此尝试任何绕过"
    )
    # 命中挑战即停：不发起任何后续请求（无 fetch、无 signin、无重试）。
