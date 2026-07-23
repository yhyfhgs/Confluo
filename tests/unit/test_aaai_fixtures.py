"""十一件套合成 fixture 的有效性验证 + D-019 锚点内部一致性（Phase 2，aaai_ojs adapter）。

目的：证明 `tests/fixtures/aaai/raw/` 的合成 fixture 结构合法、经解析器/共享核状态映射
后落到各自声明的 error_class / 形态——既给 fixture 文件本身上覆盖网，又在未来若做真实
响应重录时充当回归基线。真实网络零依赖（④/⑤/⑧ 的运行时状态码经 MockTransport 在
test_aaai_adapter.py 复现；本文件覆盖"fixture 内容本身能否被解析器/嗅探器正确消费")。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from helpers.aaai_fixtures import fixture_bytes
from paper_crawler.adapters.aaai_ojs import parse
from paper_crawler.adapters.aaai_ojs.adapter import _looks_like_html, _looks_like_login
from paper_crawler.errors import CrawlerError, ErrorClass

_ANCHOR_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "aaai" / "dblp-aaai-anchor.json"


# --- ①/② OAI ListRecords 正常页 + 续页 --------------------------------------------------------


def test_fixture_01_page1_records_tombstone_and_token() -> None:
    page = parse.parse_oai_page(fixture_bytes("01_oai_listrecords_page1.xml"))
    assert page.skipped_tombstones == 1  # 1 条 deleted 墓碑
    assert page.resumption_token == "AAAI-RESUME-PAGE2"
    # 4 条非墓碑记录，混合卷号（v40 当前届 + v33 历史届），供 partition。
    assert [r.volume for r in page.records] == ["40", "40", "33", "40"]


def test_fixture_01_first_record_reuses_real_survey_values() -> None:
    # 记录 D（article/3745，Vol.33/AAAI-19）复用 survey §5.2 [LIVE] 实测字段值。
    records = parse.parse_oai_page(fixture_bytes("01_oai_listrecords_page1.xml")).records
    real = next(r for r in records if r.article_id == "3745")
    assert real.title == "Emergency Department Online Patient-Caregiver Scheduling"
    assert real.doi == "10.1609/aaai.v33i01.3301695"
    assert real.authors == ("Rosemarin, Hanan",)
    assert real.pdf_view_url == "https://ojs.aaai.org/index.php/AAAI/article/view/3745/3623"
    assert real.date == "2019-07-21"


def test_fixture_01_has_multi_creator_and_secondary_galley_records() -> None:
    records = parse.parse_oai_page(fixture_bytes("01_oai_listrecords_page1.xml")).records
    # ≥1 条多 dc:creator（design §7 ①要求）。
    assert any(len(r.authors) >= 2 for r in records)
    # ≥1 条带次 galley relation：36959 有两个 dc:relation，取首个（PDF galley 40921）。
    secondary = next(r for r in records if r.article_id == "36959")
    assert secondary.pdf_view_url == "https://ojs.aaai.org/index.php/AAAI/article/view/36959/40921"


def test_fixture_02_page2_records_and_end_of_harvest() -> None:
    page = parse.parse_oai_page(fixture_bytes("02_oai_listrecords_page2.xml"))
    assert page.resumption_token is None  # 空 token 文本 = 收割结束
    assert [r.volume for r in page.records] == ["40", "33"]


def test_fixtures_01_02_full_harvest_partitions_4_v40_and_2_v33() -> None:
    p1 = parse.parse_oai_page(fixture_bytes("01_oai_listrecords_page1.xml")).records
    p2 = parse.parse_oai_page(fixture_bytes("02_oai_listrecords_page2.xml")).records
    volumes = [r.volume for r in (*p1, *p2)]
    assert volumes.count("40") == 4
    assert volumes.count("33") == 2


# --- ③④⑤⑥⑨ OAI 错误/空态 --------------------------------------------------------------------


def test_fixture_03_norecordsmatch_is_legal_empty_page() -> None:
    page = parse.parse_oai_page(fixture_bytes("03_oai_norecordsmatch.xml"))
    assert page.records == ()
    assert page.resumption_token is None


def test_fixture_04_bad_resumption_token_is_transient() -> None:
    with pytest.raises(CrawlerError) as exc:
        parse.parse_oai_page(fixture_bytes("04_oai_bad_resumption_token.xml"))
    assert exc.value.error_class is ErrorClass.TRANSIENT


def test_fixture_05_bad_argument_is_config() -> None:
    with pytest.raises(CrawlerError) as exc:
        parse.parse_oai_page(fixture_bytes("05_oai_bad_argument.xml"))
    assert exc.value.error_class is ErrorClass.CONFIG


def test_fixture_06_getrecord_iddoesnotexist_is_gone() -> None:
    with pytest.raises(CrawlerError) as exc:
        parse.parse_get_record(fixture_bytes("06_oai_getrecord_iddoesnotexist.xml"))
    assert exc.value.error_class is ErrorClass.GONE


def test_fixture_09_malformed_xml_is_parse() -> None:
    with pytest.raises(CrawlerError) as exc:
        parse.parse_oai_page(fixture_bytes("09_oai_malformed.xml"))
    assert exc.value.error_class is ErrorClass.PARSE


# --- ⑦⑧ HTML 失败页（fetch 嗅探基线）---------------------------------------------------------


def test_fixture_07_article_404_is_html_but_not_login() -> None:
    # 撤稿/404 页：形似 HTML 但无登录标记 → 嗅探归 GONE（区别于 08）。
    body = fixture_bytes("07_article_404.html")
    assert _looks_like_html(body)
    assert not _looks_like_login(body)
    assert b"404 Not Found" in body


def test_fixture_08_login_page_is_html_and_login() -> None:
    # 登录页：形似 HTML 且有登录标记 → 嗅探归 NO_ENTITLEMENT（★D，login-gated）。
    body = fixture_bytes("08_issue_login_redirect.html")
    assert _looks_like_html(body)
    assert _looks_like_login(body)
    assert b"/login" in body


# --- ⑩⑪ 对账/兜底路径解析器 -------------------------------------------------------------------


def test_fixture_10_issue_toc_two_summaries_pdf_class_filtered() -> None:
    entries = parse.parse_issue_toc(fixture_bytes("10_issue_toc.html"))
    assert [e.article_id for e in entries] == ["36958", "36959"]
    first = entries[0]
    assert (
        first.title
        == "Resource Efficient Sleep Staging via Multi-Level Masking and Prompt Learning"
    )
    assert first.pages == "3-11"
    # 36958 挂两个 galley（pdf + file/Video）；按 class 过滤只取 pdf galley。
    assert first.pdf_url == "https://ojs.aaai.org/index.php/AAAI/article/view/36958/40920"
    assert first.authors == ("Lejun Ai", "Yulong Li", "Haodong Yi")


def test_fixture_11_article_detail_citation_meta_matches_real_values() -> None:
    meta = parse.parse_article_meta(fixture_bytes("11_article_detail.html"))
    assert meta.doi == "10.1609/aaai.v40i1.36958"
    assert (
        meta.title == "Resource Efficient Sleep Staging via Multi-Level Masking and Prompt Learning"
    )
    assert meta.pdf_url == "https://ojs.aaai.org/index.php/AAAI/article/download/36958/40920"
    assert (meta.volume, meta.issue, meta.firstpage, meta.lastpage) == ("40", "1", "3", "11")
    assert meta.authors == ("Lejun Ai", "Yulong Li")


def test_fixture_11_citation_pdf_url_matches_view_to_download_of_relation() -> None:
    # 对账钉死：详情页 citation_pdf_url（download 终态）== OAI dc:relation（view）经
    # adapter view→download 预换的结果——证明 resolve 零网络构造与站点终态一致，
    # 无需运行时读 citation_pdf_url（§4：不作运行时 resolve 兜底）。
    from paper_crawler.adapters.aaai_ojs.adapter import _view_to_download

    records = parse.parse_oai_page(fixture_bytes("01_oai_listrecords_page1.xml")).records
    rec_36958 = next(r for r in records if r.article_id == "36958")
    meta = parse.parse_article_meta(fixture_bytes("11_article_detail.html"))
    assert rec_36958.pdf_view_url is not None
    assert _view_to_download(rec_36958.pdf_view_url) == meta.pdf_url


# --- D-019 锚点表（内部一致性：与 venues/cs_ai/aaai.yaml 的 volume_map 不漂移）------------------


def test_dblp_aaai_anchor_years_match_venue_yaml_volume_map() -> None:
    import yaml

    venues_dir = Path(__file__).resolve().parents[2] / "venues"
    aaai_yaml = yaml.safe_load((venues_dir / "cs_ai" / "aaai.yaml").read_text(encoding="utf-8"))
    venue_volume_map: dict[int, int] = aaai_yaml["quirks"]["volume_map"]

    anchor = json.loads(_ANCHOR_PATH.read_text(encoding="utf-8"))
    anchor_years = {row["year"]: row["volume"] for row in anchor["rows"]}
    # 锚点年份/卷号与 venue yaml 逐条相等（双向：无遗漏、无多余）。
    assert anchor_years == venue_volume_map


def test_dblp_aaai_anchor_oai_count_filled_but_dblp_cross_check_still_pending() -> None:
    # D-019：2026-07-23 全库 OAI 收割（Phase 2 检查单 #3 → Phase 3 报告 §6 检查单 #8）已
    # 回填 oai_count 为真实整数（research/site-survey/aaai-ojs.md §11）；DBLP TOC 人工
    # 交叉核对未做——dblp_cross_check 仍必须 pending（诚实标注，不悄悄标为已核准）。
    anchor = json.loads(_ANCHOR_PATH.read_text(encoding="utf-8"))
    assert anchor["dblp_venue"] == "conf/aaai"
    assert all(isinstance(row["oai_count"], int) and row["oai_count"] > 0 for row in anchor["rows"])
    assert all(row["dblp_cross_check"] == "pending" for row in anchor["rows"])


def test_dblp_aaai_anchor_lower_bound_is_2010() -> None:
    # 覆盖下界 2010（Vol.24）：controller 2026-07-24 裁决扩容纳入 2010-2018（design/
    # adapters/aaai-ojs.md §10 ★F，依据 §11 全库收割实测）；更早届（<2010）仍为界外
    # （survey §11.3/§11.5），锚点不含 <2010 行。
    anchor = json.loads(_ANCHOR_PATH.read_text(encoding="utf-8"))
    years = [row["year"] for row in anchor["rows"]]
    assert min(years) == 2010
    assert "界外" in anchor["coverage_note"]
