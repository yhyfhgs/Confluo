"""neurips_proceedings 十一件套 fixture 保真/落点测试 + D-019 锚点表
（design/adapters/neurips-proceedings.md §6；T3）。

每件 fixture → 预期解析形态或 error_class 落点：§5 全部 error_class（parse/gone/
rate_limited/transient/config）各有落点，均离线经 `HttpClient(MockTransport)` 或
纯解析函数验证。零真实网络。

真实性核对：fixture ②③（年页 legacy/modern golden）内嵌的 3 个 canary（hash/title/
track）必须与 `adapter._CANARIES` 逐字一致——design §6 "样本 hash/title 取自 fixture
②③" 的字面要求，本文件用交叉断言防止两处独立漂移。
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from helpers.neurips_proceedings_fixtures import fixture_bytes, http_fixture
from paper_crawler.adapters.neurips_proceedings import parse
from paper_crawler.adapters.neurips_proceedings.adapter import (
    _CANARIES,
    NeuripsProceedingsAdapter,
    _gone_guarded_stream,
)
from paper_crawler.errors import CrawlerError, ErrorClass
from paper_crawler.http import HttpClient
from paper_crawler.types import VenueSpec

_UA = "PaperCrawler/test (personal research; mailto:test@example.com)"
_FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "neurips_proceedings"
_ANCHOR_PATH = _FIXTURES_DIR / "dblp-nips-anchor.json"


def _client_for(name: str) -> HttpClient:
    status, headers, body = http_fixture(name)

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, headers=headers, content=body)

    return HttpClient(user_agent=_UA, transport=httpx.MockTransport(handler))


# --- ① 首页 ul.proceedings-list（discover 一致性回归，不进产线 discover_timeline）--------------


def test_fixture_01_homepage_has_39_continuous_years() -> None:
    years = parse.parse_proceedings_list(fixture_bytes("01_proceedings_list_homepage.html"))
    assert len(years) == 39
    assert sorted(years) == list(range(1987, 2026))  # 连续无缺口


def test_fixture_01_volume_invariant_holds_for_every_year() -> None:
    years = parse.parse_proceedings_list(fixture_bytes("01_proceedings_list_homepage.html"))
    for year in years:
        assert parse.volume_for_year(year) == year - 1987


def test_fixture_01_matches_programmatic_discover_for_same_range() -> None:
    """一致性回归核心断言（design §3.1 论证）：程序生成 discover_timeline 的年份集合
    与解析首页得到的年份集合，对历史区间完全相等——这是"discover 可以零网络程序生成
    而不必解析首页"这一裁决（§8-★2）的离线可复核证据。
    """
    homepage_bytes = fixture_bytes("01_proceedings_list_homepage.html")
    homepage_years = set(parse.parse_proceedings_list(homepage_bytes))
    venue = VenueSpec(
        id="neurips",
        kind="conference",
        names={"full": "NeurIPS"},
        field=["cs_ai"],
        metadata_source="neurips_proceedings",
        fulltext_source="neurips_proceedings",
        quirks={"first_year": 1987, "known_through_year": 2025},
    )
    discovered_years = {i.year for i in NeuripsProceedingsAdapter().discover_timeline(venue)}
    assert discovered_years == homepage_years


# --- ②③ 年页 legacy/modern（enumerate golden，含 canary）---------------------------------------


def test_fixture_02_legacy_2021_has_three_papers_all_track_none() -> None:
    papers = parse.parse_year_page(fixture_bytes("02_year_page_2021_legacy.html"))
    assert len(papers) == 3
    assert {p.track for p in papers} == {"none"}
    assert {p.asset_suffix for p in papers} == {""}


def test_fixture_03_modern_2022_has_four_papers_mixed_tracks() -> None:
    papers = parse.parse_year_page(fixture_bytes("03_year_page_2022_modern.html"))
    assert len(papers) == 4
    assert {p.track for p in papers} == {"conference", "datasets_and_benchmarks"}
    # 混排断言（design §4"两条 track 共享同一年份索引页"）：非按 track 分组排列。
    tracks_in_order = [p.track for p in papers]
    assert tracks_in_order != sorted(tracks_in_order)


def test_fixtures_02_03_embed_exactly_the_three_adapter_canaries() -> None:
    """design §6"样本 hash/title 取自 fixture ②③"的字面校验：交叉比对 fixture 内容
    与 `adapter._CANARIES`，防止两处（fixture 文件 vs 硬编码 canary 元组）各自漂移。
    """
    by_hash = {
        p.hash: p
        for p in (
            *parse.parse_year_page(fixture_bytes("02_year_page_2021_legacy.html")),
            *parse.parse_year_page(fixture_bytes("03_year_page_2022_modern.html")),
        )
    }
    assert len(_CANARIES) == 3
    for canary in _CANARIES:
        paper = by_hash.get(canary.hash)
        assert paper is not None, f"canary {canary.hash} not found in fixtures 02/03"
        assert paper.title == canary.title
        assert paper.track == canary.track


def test_fixture_02_healthcheck_min_paper_floor_is_satisfied() -> None:
    # design §3.5"篇数不低于下限"——fixture 本身必须满足 adapter 的健康检查地板，
    # 否则 healthcheck() 会在到达 canary 比对前就先报"篇数过低"。
    from paper_crawler.adapters.neurips_proceedings.adapter import _HEALTHCHECK_MIN_PAPERS

    papers_2021 = parse.parse_year_page(fixture_bytes("02_year_page_2021_legacy.html"))
    papers_2022 = parse.parse_year_page(fixture_bytes("03_year_page_2022_modern.html"))
    assert len(papers_2021) >= _HEALTHCHECK_MIN_PAPERS[2021]
    assert len(papers_2022) >= _HEALTHCHECK_MIN_PAPERS[2022]


def test_healthcheck_end_to_end_via_fixtures_02_03_is_healthy() -> None:
    """全链路：把 fixture ②③原样喂给 healthcheck()，应判定 healthy（生产 canary 比对
    真正吃到的是这两个文件，而不只是单测里手写的内联 HTML）。
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/2021"):
            return httpx.Response(200, content=fixture_bytes("02_year_page_2021_legacy.html"))
        if request.url.path.endswith("/2022"):
            return httpx.Response(200, content=fixture_bytes("03_year_page_2022_modern.html"))
        raise AssertionError(f"unexpected request: {request.url}")

    client = HttpClient(user_agent=_UA, transport=httpx.MockTransport(handler))
    report = NeuripsProceedingsAdapter(http=client).healthcheck()
    assert report.healthy is True


# --- ④a/④b 详情页 Abstract 快照（enrichment golden，本期不解析）--------------------------------


def test_fixture_04a_modern_2023_detail_has_real_citation_meta_and_double_p_abstract() -> None:
    body = fixture_bytes("04a_abstract_detail_modern_2023.html")
    assert b'<meta name="citation_title" content="Modelling Cellular Perturbations' in body
    assert b'<meta name="citation_volume" content="36">' in body
    # 双 <p> 包裹瑕疵（design §3.3/§4，[LIVE] 实测站点模板缺陷）。
    assert b'<p class="paper-abstract"><p>' in body


def test_fixture_04b_legacy_1987_detail_has_sparser_citation_meta() -> None:
    body = fixture_bytes("04b_abstract_detail_legacy_1987.html")
    assert b'<meta name="citation_title" content="Synchronization in Neural Nets">' in body
    assert b'<meta name="citation_volume" content="0">' in body
    # 1987 年代稀疏性（[LIVE] §4）：journal_title 无 "Advances in" 前缀、无 first/lastpage、
    # 年份粒度日期。只掐 citation_journal_title 这一条 meta 标签的内容判断——不对整份
    # 文件字节做全文子串搜索（文件头的说明性注释本身就会提到"Advances in"这个词组，
    # 全文搜索会把注释误判为反例，见本次实现踩过的坑）。
    journal_meta = b'<meta name="citation_journal_title" content="Neural Information Processing'
    assert journal_meta in body
    assert b"Advances in Neural Information Processing Systems" not in body
    assert b"citation_firstpage" not in body
    assert b'<meta name="citation_publication_date" content="1987">' in body


# --- ⑤ 年页 404 -----------------------------------------------------------------------------------


def test_fixture_05_body_is_exact_23_byte_generic_404() -> None:
    body = fixture_bytes("05_year_page_404.html")
    assert body == b"<h1>Page Not Found</h1>"
    assert len(body) == 23


def test_fixture_05_via_httpclient_404_maps_to_gone() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, content=fixture_bytes("05_year_page_404.html"))

    client = HttpClient(user_agent=_UA, transport=httpx.MockTransport(handler))
    with pytest.raises(CrawlerError) as exc:
        client.get_bytes("https://proceedings.neurips.cc/paper_files/paper/1986")
    assert exc.value.error_class is ErrorClass.GONE


# --- ⑥ 年页结构漂移（0 条目）→ parse -------------------------------------------------------------


def test_fixture_06_structural_drift_has_zero_entries() -> None:
    with pytest.raises(CrawlerError) as exc:
        parse.parse_year_page(fixture_bytes("06_year_page_structural_drift.html"))
    assert exc.value.error_class is ErrorClass.PARSE


# --- ⑦ PDF 正常字节头 → fetch happy path ------------------------------------------------------
#
# 不落物理 `.pdf` 文件：仓库 `.gitignore` 对 `*.pdf` 有全局排除规则（防误提交真实下载
# 产物），且 arxiv/openreview/pmlr 三份既有 fixture 套件同样一律用内联字节常量表示
# "PDF happy path"（如契约测试的 `_CONTRACT_PDF`），没有任何一份在 `tests/fixtures/`
# 下放过真实 `.pdf` 文件——遵循同一约定，内联而非物理文件。
_PDF_NORMAL_BYTES = (
    b"%PDF-1.4\n"
    b"% SYNTHETIC minimal PDF fixture (T3 fixture #7, design SS6 'PDF happy path').\n"
    b"1 0 obj<</Type/Catalog>>endobj\n"
    b"trailer<</Root 1 0 R>>\n"
    b"%%EOF\n"
)


def test_fixture_07_starts_with_pdf_magic_and_passes_gone_guard() -> None:
    assert _PDF_NORMAL_BYTES.startswith(b"%PDF-")
    out = b"".join(_gone_guarded_stream([_PDF_NORMAL_BYTES]))
    assert out == _PDF_NORMAL_BYTES  # 原样透传，不被误判 gone


# --- ⑧ PDF 回 HTML 页 → gone（_gone_guarded_stream）--------------------------------------------


def test_fixture_08_pdf_url_returning_html_is_sniffed_gone() -> None:
    body = fixture_bytes("08_pdf_returns_html_gone.html")
    with pytest.raises(CrawlerError) as exc:
        list(_gone_guarded_stream([body]))
    assert exc.value.error_class is ErrorClass.GONE


# --- ⑨ 503+Retry-After → rate_limited（响应头随体落盘）------------------------------------------


def test_fixture_09_503_retry_after_maps_to_rate_limited() -> None:
    status, headers, _body = http_fixture("09_year_page_503_retry_after.http")
    assert status == 503
    assert headers["Retry-After"] == "90"
    with pytest.raises(CrawlerError) as exc:
        _client_for("09_year_page_503_retry_after.http").get_bytes(
            "https://proceedings.neurips.cc/paper_files/paper/2021"
        )
    assert exc.value.error_class is ErrorClass.RATE_LIMITED
    assert "retry_after_s=90" in exc.value.detail


# --- ⑩ 5xx 无 Retry-After → transient ------------------------------------------------------------


def test_fixture_10_5xx_no_retry_after_maps_to_transient() -> None:
    status, headers, _body = http_fixture("10_year_page_5xx_no_retry_after.http")
    assert status == 500
    assert "Retry-After" not in headers
    with pytest.raises(CrawlerError) as exc:
        _client_for("10_year_page_5xx_no_retry_after.http").get_bytes(
            "https://proceedings.neurips.cc/paper_files/paper/2021"
        )
    assert exc.value.error_class is ErrorClass.TRANSIENT


# --- ⑪ 400 → config -------------------------------------------------------------------------------


def test_fixture_11_400_maps_to_config() -> None:
    status, _headers, _body = http_fixture("11_year_page_400.http")
    assert status == 400
    with pytest.raises(CrawlerError) as exc:
        _client_for("11_year_page_400.http").get_bytes(
            "https://proceedings.neurips.cc/paper_files/paper/2021"
        )
    assert exc.value.error_class is ErrorClass.CONFIG


# --- D-019 锚点表（tests/fixtures/neurips_proceedings/dblp-nips-anchor.json）--------------------


def test_dblp_nips_anchor_seed_rows_match_live_verified_counts() -> None:
    anchor = json.loads(_ANCHOR_PATH.read_text(encoding="utf-8"))
    rows = {row["year"]: row for row in anchor["rows"]}
    # docs/research/site-survey/neurips-proceedings.md SS2 [LIVE] 表逐值核对。
    expected_seeds = {
        1987: 90,
        1993: 158,
        2019: 1428,
        2020: 1898,
        2021: 2334,
        2022: 2834,
        2023: 3540,
    }
    for year, count in expected_seeds.items():
        assert rows[year]["paper_count_claimed"] == count
        assert rows[year]["dblp_cross_check"] == "pending"


def test_dblp_nips_anchor_has_39_rows_spanning_1987_to_2025() -> None:
    anchor = json.loads(_ANCHOR_PATH.read_text(encoding="utf-8"))
    years = [row["year"] for row in anchor["rows"]]
    assert years == list(range(1987, 2026))


def test_dblp_nips_anchor_non_seed_rows_are_honestly_pending() -> None:
    # D-019：本次实现未做真实网络录制/DBLP 交叉核对，种子行之外一律 paper_count_claimed
    # =null（不得悄悄标记为已核准）。
    anchor = json.loads(_ANCHOR_PATH.read_text(encoding="utf-8"))
    seed_years = {1987, 1993, 2019, 2020, 2021, 2022, 2023}
    for row in anchor["rows"]:
        if row["year"] not in seed_years:
            assert row["paper_count_claimed"] is None
        assert row["dblp_cross_check"] == "pending"


def test_dblp_nips_anchor_matches_discover_timeline_when_known_through_year_pinned() -> None:
    """design §6"timeline 完整性判定＝timeline neurips 输出与锚点表全等——测试须固定
    known_through_year（如锚点最大年 2025）"的字面落地。
    """
    anchor = json.loads(_ANCHOR_PATH.read_text(encoding="utf-8"))
    anchor_years = {row["year"] for row in anchor["rows"]}
    max_year = max(anchor_years)
    min_year = min(anchor_years)

    venue = VenueSpec(
        id="neurips",
        kind="conference",
        names={"full": "NeurIPS"},
        field=["cs_ai"],
        metadata_source="neurips_proceedings",
        fulltext_source="neurips_proceedings",
        quirks={"first_year": min_year, "known_through_year": max_year},
    )
    discovered_years = {i.year for i in NeuripsProceedingsAdapter().discover_timeline(venue)}
    assert discovered_years == anchor_years


def test_dblp_nips_anchor_1987_1988_carry_the_vol_convention_caveat_note() -> None:
    # design §6"1987/1988＝vol 0/1（DBLP 年份约定须核，[UNRESOLVED] 归入 note）"。
    anchor = json.loads(_ANCHOR_PATH.read_text(encoding="utf-8"))
    rows = {row["year"]: row for row in anchor["rows"]}
    for year in (1987, 1988):
        assert "vol" in rows[year]["note"].lower() or "convention" in rows[year]["note"].lower()
