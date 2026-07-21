"""pmlr canary：3 个跨会议/跨托管固定样本，规整化 title + pages 双字段比对
（design/adapters/pmlr.md §6.4）。

**分层说明**（呼应 `adapter.py` 模块 docstring）：design §3.5 的 `healthcheck()`
是运行期匿名站点根 ping（生产 canary 命令走它，见 canary.py/test_cli_canary.py）；
本文件的"3 样本已知答案比对"是**测试层**的解析回归断言（比照 test-plan §4"更细
粒度分类…后续 adapter 落地时才会叠加的更高层能力"一语，与 arxiv 把 3-canary 融
进 healthcheck() 的取向不同——pmlr.md §3.5 明确只要求站点根 ping，把已知答案比
对独立放在测试层，不增加 healthcheck() 的网络面）。

**数据来源诚实声明**：样本①为真实数据（[LIVE] 2026-07-22
docs/research/site-survey/pmlr.md 实测：v235/abad-rocamora24a，ICML 2024，
GitHub 托管）。样本②③的**卷号与托管形态**取自同一份 [LIVE] 勘察记录的真实事实
（v202=ICML 2023 自托管、v229=CoRL 2023 自托管），但**卷内具体论文内容是本次实
现标注合成**的占位数据——本次实现未做真实网络录制（`PAPER_CRAWLER_CONTACT_EMAIL`
未设，按 D-014 约定全走合成路径），不虚构任何真实论文的标题/页码。design §6.4
原文对样本②③注明"于实现期 UPDATE_GOLDEN 锁定"——此处锁定的是本文件自带的合成
fixture，而非真实站点响应。
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx
import pytest

from helpers import make_pmlr_venue
from paper_crawler.adapters.pmlr import parse
from paper_crawler.adapters.pmlr.adapter import PmlrAdapter
from paper_crawler.http import HttpClient
from paper_crawler.types import AssetKind, IssueRef

_UA = "PaperCrawler/test (personal research; mailto:test@example.com)"


@dataclass(frozen=True)
class _Canary:
    """一条 canary 锚点：卷/slug 定位 + 期望规整化 title/pages + 期望 pdf 托管域。"""

    label: str
    volume: str
    slug: str
    title: str
    firstpage: int
    lastpage: int
    pdf_host: str  # 期望的 [Download PDF] 域（跨托管覆盖的断言点）


_CANARIES: tuple[_Canary, ...] = (
    # ① ICML 2024，GitHub 托管——真实数据，[LIVE] 2026-07-22 site-survey/pmlr.md
    # item 2/3（title/pages/bibkey/pdf 域均实测）。
    _Canary(
        label="icml2024-github",
        volume="235",
        slug="abad-rocamora24a",
        title="Revisiting Character-level Adversarial Attacks for Language Models",
        firstpage=1,
        lastpage=30,
        pdf_host="raw.githubusercontent.com",
    ),
    # ② ICML 2023，自托管——卷号/托管形态真实（site-survey 项 3 表第一行：v202
    # 实测 200 application/pdf 自托管）；卷内论文为合成占位（无真实网络录制）。
    _Canary(
        label="icml2023-selfhosted",
        volume="202",
        slug="canary-selfhosted23a",
        title="A Synthetic Self-Hosted Canary Paper for Cross-Volume Coverage",
        firstpage=101,
        lastpage=115,
        pdf_host="proceedings.mlr.press",
    ),
    # ③ CoRL 2023，跨会议样本——卷号/托管形态真实（site-survey 请求 #19：v229
    # 实测"卷页全部自托管"，佐证"切分按上传时间非卷号"：同为 2023 年但 ICML
    # v202 与 CoRL v229 都在 v235(2024) 迁移前）；卷内论文为合成占位。
    _Canary(
        label="corl2023-crossvenue",
        volume="229",
        slug="canary-corl23a",
        title="A Synthetic Cross-Conference Canary Paper for CoRL-Style Volumes",
        firstpage=5,
        lastpage=20,
        pdf_host="proceedings.mlr.press",
    ),
)


def _pdf_url_for(canary: _Canary) -> str:
    if canary.pdf_host == "raw.githubusercontent.com":
        return (
            f"https://raw.githubusercontent.com/mlresearch/v{canary.volume}/main/assets/"
            f"{canary.slug}/{canary.slug}.pdf"
        )
    return f"https://proceedings.mlr.press/v{canary.volume}/{canary.slug}/{canary.slug}.pdf"


def _volume_page_bytes(canary: _Canary) -> bytes:
    div = (
        '<div class="paper">'
        f'<p class="title">{canary.title}</p>'
        f'<p class="details"><span class="authors">Canary Author</span><br>'
        f"PMLR {canary.volume}:{canary.firstpage}-{canary.lastpage}, 2024.</p>"
        f'<p class="links">[<a href="v{canary.volume}/{canary.slug}.html">abs</a>]'
        f'[<a href="{_pdf_url_for(canary)}">Download PDF</a>]</p>'
        "</div>"
    )
    return f"<html><body><div id='content'>{div}</div></body></html>".encode()


def _adapter_for(canary: _Canary) -> PmlrAdapter:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=_volume_page_bytes(canary))

    client = HttpClient(user_agent=_UA, transport=httpx.MockTransport(handler))
    return PmlrAdapter(http=client)


@pytest.mark.parametrize("canary", _CANARIES, ids=[c.label for c in _CANARIES])
def test_canary_parse_layer_title_and_pages_match_known_answer(canary: _Canary) -> None:
    """解析层直接比对：`PmlrPaper.title`（已规整化）+ (firstpage, lastpage) 双字段。"""
    papers = parse.parse_volume_index(_volume_page_bytes(canary))
    assert len(papers) == 1
    paper = papers[0]
    assert paper.title == canary.title  # 空白已在解析层规整化，直接等值比对
    assert (paper.firstpage, paper.lastpage) == (canary.firstpage, canary.lastpage)
    assert paper.slug == canary.slug


@pytest.mark.parametrize("canary", _CANARIES, ids=[c.label for c in _CANARIES])
def test_canary_end_to_end_through_enumerate_resolve_hits_expected_host(
    canary: _Canary,
) -> None:
    """adapter 层端到端：enumerate 产出正确 identifier，resolve 命中期望托管域。"""
    venue = make_pmlr_venue(volume_map={2024: int(canary.volume)})
    issue = IssueRef(
        venue_id="icml", volume=canary.volume, number=None, year=2024, label=f"v{canary.volume}"
    )
    papers = list(_adapter_for(canary).enumerate_issue(venue, issue))
    assert len(papers) == 1
    stub = papers[0]
    assert stub.identifiers == (("pmlr", f"pmlr-v{canary.volume}-{canary.slug}"),)
    assert stub.title == canary.title

    plans = PmlrAdapter().resolve_assets(venue, stub)
    assert len(plans) == 1
    plan = plans[0]
    assert plan.kind is AssetKind.PDF
    assert httpx.URL(plan.url).host == canary.pdf_host


def test_canary_set_covers_both_hosting_forms_and_multiple_volumes() -> None:
    """canary 集合自证覆盖面：>=1 GitHub 托管 + >=1 自托管，且跨 3 个不同卷号。"""
    hosts = {c.pdf_host for c in _CANARIES}
    assert hosts == {"raw.githubusercontent.com", "proceedings.mlr.press"}
    assert len({c.volume for c in _CANARIES}) == 3
