"""NeurIPS proceedings 在线冒烟（Phase 2 DoD：每 adapter 一个限量在线冒烟；样板 arxiv）。

默认经 `addopts = -m 'not online'` 排除。硬预算 `MAX_REAL_REQUESTS = 5`；请求共用一个
30rpm 限速器（`neurips_client`，`proceedings.neurips.cc` 主域 + 两镜像 alias），UA 携
真实 mailto（D-014）。

证实真实站点应答 + 解析入库路径打通（design/adapters/neurips-proceedings.md §3 在线证据层）：
- 2023 年页枚举（1 请求，现代形态）：解析出的 stub 数 == D-019 锚点 **3540**（3218
  conference + 322 D&B 同页混排，site-survey §3 两法计数一致）；
- 2021 年页枚举（1 请求，legacy 形态）：解出非空 + 首条 `meta['asset_suffix']==''`
  （legacy 后缀边界左侧空串，验双 era 解析器不退化）；顺带打印 real 2021 canary
  （hash 000c076c… 的真实 title+track，供 adapter `_CANARIES` 占位替换，非强制）；
- 单篇 PDF 首 chunk（1 请求，现代 `-Paper{infix}.pdf`）：`%PDF` 魔数（捕获自 2023）；
- healthcheck（2 请求，2021 legacy + 2022 modern 两页）：断言两届年页可达且解析过下限
  （**canary 仍为合成占位** deadbeef/facefeed → `healthy=False` 属既有债，冒烟不据此
  判失败，见 adapter `_CANARIES` 注记）。

≈ 共 5 请求 ≤ 5。真实执行结果归档 scratchpad/online-smoke-batch-run.txt。
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

from helpers import make_neurips_venue
from online.conftest import RealRequestBudget
from online.smoke_helpers import make_rate_limited_client, stream_first_chunk
from paper_crawler.adapters.neurips_proceedings.adapter import NeuripsProceedingsAdapter
from paper_crawler.http import HttpClient
from paper_crawler.types import IssueRef, PaperStub

MAX_REAL_REQUESTS = 5

# D-019 锚点：NeurIPS 2023 = 3540 篇（conference 3218 + D&B 322，同页混排）。
_NEURIPS2023_ANCHOR = 3540
# 真实 2021 canary hash（adapter `_CANARIES` 逐字复用，[LIVE] 实测 32-hex）。
_CANARY_2021_HASH = "000c076c390a4c357313fca29e390ece"

_CONTACT_EMAIL = os.environ.get("PAPER_CRAWLER_CONTACT_EMAIL", "")
if not _CONTACT_EMAIL:
    pytest.skip(
        "PAPER_CRAWLER_CONTACT_EMAIL not set (required for D-014 UA identity)",
        allow_module_level=True,
    )

_CAPTURED: list[PaperStub] = []


@pytest.fixture(scope="session")
def neurips_client() -> Iterator[HttpClient]:
    """真实 HttpClient：UA 携真实 mailto（D-014）+ 30rpm 限速器（三镜像域共享一桶）。"""
    client = make_rate_limited_client(
        domains=NeuripsProceedingsAdapter.domains,
        default_rate=NeuripsProceedingsAdapter.default_rate,
        contact_email=_CONTACT_EMAIL,
    )
    try:
        yield client
    finally:
        client.close()


@pytest.mark.online
def test_enumerate_2023_count_matches_anchor(
    neurips_client: HttpClient, real_request_budget: RealRequestBudget
) -> None:
    """1 请求：2023 年页解析出的 stub 数 == D-019 锚点 3540（现代形态，两 track 混排）。"""
    adapter = NeuripsProceedingsAdapter(http=neurips_client)
    venue = make_neurips_venue()
    issue = IssueRef(venue_id="neurips", year=2023, label="2023")
    real_request_budget.spend(1)
    stubs = list(adapter.enumerate_issue(venue, issue))
    print(f"ENUMERATE 2023 parsed={len(stubs)} anchor={_NEURIPS2023_ANCHOR}")
    assert len(stubs) == _NEURIPS2023_ANCHOR, (
        f"NeurIPS 2023 解析出 {len(stubs)} 篇，与 D-019 锚点 {_NEURIPS2023_ANCHOR} 不符"
    )
    _CAPTURED.append(stubs[0])
    print(f"CAPTURED id={stubs[0].identifiers!r} meta={stubs[0].meta!r}")


@pytest.mark.online
def test_enumerate_2021_legacy_form_parses(
    neurips_client: HttpClient, real_request_budget: RealRequestBudget
) -> None:
    """1 请求：2021 legacy 年页解出非空 + 首条 `asset_suffix==''`（legacy 后缀边界左侧）。

    顺带打印 real 2021 canary（hash 000c076c…）的真实 title+track，供 adapter
    `_CANARIES` 的合成占位替换（非强制——2022 两条 canary hash 亦为合成，仅替换 2021
    不足以让 healthcheck 转 healthy）。
    """
    adapter = NeuripsProceedingsAdapter(http=neurips_client)
    venue = make_neurips_venue()
    issue = IssueRef(venue_id="neurips", year=2021, label="2021")
    real_request_budget.spend(1)
    stubs = list(adapter.enumerate_issue(venue, issue))
    assert stubs, "NeurIPS 2021 年页解析出 0 条目"
    first_suffix = dict(stubs[0].meta).get("asset_suffix")
    print(f"ENUMERATE 2021 parsed={len(stubs)} first_asset_suffix={first_suffix!r}")
    assert first_suffix == "", (
        f"2021 legacy 首条 asset_suffix 应为空串（legacy 后缀边界左侧），实得 {first_suffix!r}"
    )
    canary = next(
        (s for s in stubs if dict(s.identifiers).get("neurips") == _CANARY_2021_HASH), None
    )
    if canary is not None:
        print(
            f"CANARY_CAPTURE 2021 hash={_CANARY_2021_HASH} "
            f"title={canary.title!r} track={dict(canary.meta).get('track')!r}"
        )
    else:
        print(f"CANARY_CAPTURE 2021 hash={_CANARY_2021_HASH} NOT FOUND on 2021 page")


@pytest.mark.online
def test_fetch_single_pdf_first_chunk_is_pdf(
    neurips_client: HttpClient, real_request_budget: RealRequestBudget
) -> None:
    """1 请求：resolve 真实 2023 stub → stream 首 chunk 断 `%PDF` 魔数后关流。"""
    if not _CAPTURED:
        pytest.skip("需先跑 test_enumerate_2023_count_matches_anchor 捕获真实 stub")
    adapter = NeuripsProceedingsAdapter(http=neurips_client)
    plan = adapter.resolve_assets(make_neurips_venue(), _CAPTURED[0])[0]
    real_request_budget.spend(1)
    head = stream_first_chunk(neurips_client, plan.url)
    print(f"FETCH_FIRST_CHUNK url={plan.url} head={head[:8]!r}")
    assert head.startswith(b"%PDF"), f"下载体非 PDF（前 8 字节 {head[:8]!r}）"


@pytest.mark.online
def test_healthcheck_both_year_pages_reachable(
    neurips_client: HttpClient, real_request_budget: RealRequestBudget
) -> None:
    """2 请求：healthcheck GET 2021 legacy + 2022 modern 两页，断言可达且解析过下限。

    canary 仍为合成占位（`_CANARIES` 的 deadbeef/facefeed）→ `healthy=False` 属既有债，
    非站点/解析问题；冒烟只验两届年页可达并解析过下限（healthcheck 先过 fetch+floor
    才进入 canary 比对），不据 `healthy` 判失败。
    """
    adapter = NeuripsProceedingsAdapter(http=neurips_client)
    real_request_budget.spend(2)  # healthcheck 内部固定 GET 2021 + 2022 两页
    report = adapter.healthcheck()
    print(f"HEALTHCHECK healthy={report.healthy} detail={report.detail!r}")
    assert "fetch/parse failed" not in report.detail, (
        f"neurips 年页不可达/解析失败: {report.detail!r}"
    )
    assert "floor" not in report.detail, f"neurips 年页解析低于下限: {report.detail!r}"
    # 走到 canary 比对（或直接 healthy）即证明两页 fetch+floor 均过 → 站点解析路径通。
    assert report.healthy or "canary" in report.detail, (
        f"healthcheck 未进入 canary 比对阶段（疑似 fetch/floor 早退）: {report.detail!r}"
    )
