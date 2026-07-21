"""cvf canary 三样本（design/adapters/cvf.md §6："3 个跨年+跨 era 固定样本"）。

三样本——CVPR2023（现代 day_all）、ICCV2021（奇数年，验双年制路由）、CVPR2013
（flat 早年，验双形态解析器不退化）——各自经 `CVFAdapter.enumerate_issue` 全链
（MockTransport 回放）驱动，比对**空白规整化 title + 第二稳定字段（identifier
stem）**，不做原串精确匹配（design §6："避免折行/微调误报 DRIFT"，先例
arxiv/openreview 双字段比对法）。CVPR2023 样本的标题/作者/href 逐字转录自 [LIVE]
站点勘察（真实 GFPose 论文），非合成——三样本中最具"锚点"意义的一条。

**范围说明**：本文件是 T1/T3 层的**离线**跨 era 回归哨兵（零真实网络，CI 化）。
design §6 提到的"另附 1 条计数锚点（CVPR2023?day=all 条目数 == 2353）"是对**真实
站点**的计数断言，只能在 T5 在线冒烟层验证（本任务禁真实网络，T5 canary 注册
留待后续在线阶段——D-019 锚点表 `dblp-cvf-anchor.json` 已记录 2353 作为待核对的
种子值）。
"""

from __future__ import annotations

import httpx

from helpers import make_cvf_venue
from paper_crawler.adapters.cvf.adapter import CVFAdapter
from paper_crawler.http import HttpClient
from paper_crawler.types import IssueRef

_UA = "PaperCrawler/test (personal research; mailto:test@example.com)"


def _normalize_ws(text: str) -> str:
    return " ".join(text.split())


# --- 样本 1：CVPR2023（现代 day_all，真实 GFPose 条目，[LIVE] 转录）---------------------------

_GFPOSE_TITLE = "GFPose: Learning 3D Human Pose Prior With Gradient Fields"
_GFPOSE_STEM = "Ci_GFPose_Learning_3D_Human_Pose_Prior_With_Gradient_Fields_CVPR_2023_paper"


def _cvpr2023_day_all_html() -> bytes:
    return (
        '<html><body><div id="content"><dl>\n'
        '<dt class="ptitle"><br><a href="/content/CVPR2023/html/'
        f'{_GFPOSE_STEM}.html">{_GFPOSE_TITLE}</a></dt>\n'
        '<dd><input type="hidden" name="query_author" value="Hai Ci"></dd>\n'
        f'<dd>[<a href="/content/CVPR2023/papers/{_GFPOSE_STEM}.pdf">pdf</a>]'
        f'[<a href="http://arxiv.org/abs/2212.08641">arXiv</a>]</dd>\n'
        "</dl></div></body></html>"
    ).encode()


def test_canary_cvpr2023_gfpose_title_and_stem_match_live_survey() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("day") == "all":
            return httpx.Response(200, content=_cvpr2023_day_all_html())
        # bare 探测先命中 day-landing（现代年份两请求真实行为）。
        return httpx.Response(
            200,
            content=(
                b'<div id="content"><dl><dd>[<a href="/CVPR2023?day=all">All</a>]</dd></dl></div>'
            ),
        )

    client = HttpClient(user_agent=_UA, transport=httpx.MockTransport(handler))
    adapter = CVFAdapter(http=client, current_year=2026)
    (stub,) = list(
        adapter.enumerate_issue(
            make_cvf_venue("cvpr"), IssueRef(venue_id="cvpr", year=2023, label="2023")
        )
    )
    assert _normalize_ws(stub.title) == _GFPOSE_TITLE
    _, value = stub.identifiers[0]
    assert value == f"CVPR2023/{_GFPOSE_STEM}"


# --- 样本 2：ICCV2021（奇数年，验双年制路由）----------------------------------------------------

_ICCV_STEM = "Reyes_Adaptive_Feature_Alignment_for_Cross_Domain_Retrieval_ICCV_2021_paper"
_ICCV_TITLE = "Adaptive Feature Alignment for Cross-Domain Retrieval"


def _iccv2021_day_all_html() -> bytes:
    return (
        '<html><body><div id="content"><dl>\n'
        '<dt class="ptitle"><br><a href="/content/ICCV2021/html/'
        f'{_ICCV_STEM}.html">{_ICCV_TITLE}</a></dt>\n'
        '<dd><input type="hidden" name="query_author" value="Michael Reyes"></dd>\n'
        f'<dd>[<a href="/content/ICCV2021/papers/{_ICCV_STEM}.pdf">pdf</a>]</dd>\n'
        "</dl></div></body></html>"
    ).encode()


def test_canary_iccv2021_odd_year_routing_and_stem() -> None:
    requested_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_paths.append(request.url.path)
        return httpx.Response(200, content=_iccv2021_day_all_html())

    client = HttpClient(user_agent=_UA, transport=httpx.MockTransport(handler))
    adapter = CVFAdapter(http=client, current_year=2026)

    # 双年制路由：2021（奇数）在 cadence 届表内（discover 层已由
    # test_cvf_cadence.py::test_iccv_only_odd_years_from_2013 覆盖边界穷举；
    # 本样本额外证 enumerate 用会议代码 "ICCV" 而非 "CVPR" 构造 URL/identifier）。
    (stub,) = list(
        adapter.enumerate_issue(
            make_cvf_venue("iccv"), IssueRef(venue_id="iccv", year=2021, label="2021")
        )
    )
    assert requested_paths == ["/ICCV2021"]  # flat 响应（本样本无 day-landing 分支）
    assert _normalize_ws(stub.title) == _ICCV_TITLE
    _, value = stub.identifiers[0]
    assert value == f"ICCV2021/{_ICCV_STEM}"
    assert value.startswith("ICCV")  # 非 CVPR——路由未串台


# --- 样本 3：CVPR2013（flat 早年，验双形态解析器不退化，[LIVE] 词序/相对路径特征）--------------

_2013_STEM = "Kim_Deformable_Spatial_Pyramid_2013_CVPR_paper"  # 现代为 ..._CVPR_2013_paper 词序
_2013_TITLE = "Deformable Spatial Pyramid Matching for Fast Dense Correspondences"


def _cvpr2013_flat_html() -> bytes:
    return (
        '<html><body><div id="content"><dl>\n'
        '<dt class="ptitle"><br><a href="content_cvpr_2013/html/'
        f'{_2013_STEM}.html">{_2013_TITLE}</a></dt>\n'
        '<dd><input type="hidden" name="query_author" value="Jaechul Kim"></dd>\n'
        f'<dd>[<a href="content_cvpr_2013/papers/{_2013_STEM}.pdf">pdf</a>]</dd>\n'
        "</dl></div></body></html>"
    ).encode()


def test_canary_cvpr2013_flat_era_relative_href_and_word_order() -> None:
    request_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        assert request.url.path == "/CVPR2013"
        return httpx.Response(200, content=_cvpr2013_flat_html())

    client = HttpClient(user_agent=_UA, transport=httpx.MockTransport(handler))
    adapter = CVFAdapter(http=client, current_year=2026)
    (stub,) = list(
        adapter.enumerate_issue(
            make_cvf_venue("cvpr"), IssueRef(venue_id="cvpr", year=2013, label="2013")
        )
    )
    assert request_count == 1  # flat era：不退化为二次 ?day=all 探测
    assert _normalize_ws(stub.title) == _2013_TITLE
    _, value = stub.identifiers[0]
    assert value == f"CVPR2013/{_2013_STEM}"
    # 早年词序特征（[LIVE] §9）：`_2013_CVPR_paper`，与现代 `_CVPR_2023_paper` 不同。
    assert value.endswith("_2013_CVPR_paper")

    meta = dict(stub.meta)
    # 相对路径已被 to_paper_stub 绝对化——落 meta 的 URL 恒绝对，消除 era 分支
    # （design §3.3 "对两代同一段代码"）。
    assert meta["pdf_url"] == (
        f"https://openaccess.thecvf.com/content_cvpr_2013/papers/{_2013_STEM}.pdf"
    )
