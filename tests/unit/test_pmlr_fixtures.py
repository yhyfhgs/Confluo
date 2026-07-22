"""七件套 + 独立审查追加件（+ D-019 锚点表）合成 fixture 的有效性验证（Phase 2，
pmlr adapter）。

目的：证明 `tests/fixtures/pmlr/raw/` 的合成 fixture 结构合法、且经解析器/
HttpClient 状态映射后落到各自声明的 error_class / 形态——既给 fixture 文件本身
上覆盖网，又在未来若做真实响应重录时充当"回归基线"。真实网络零依赖：④/⑤ 的
状态码经 `httpx.MockTransport` 复现（见 test_pmlr_adapter.py 的 enumerate/fetch
测试；本文件只覆盖"fixture 内容本身能否被解析器正确消费"这一层）。

独立审查 2026-07-22 追加件（原七件套之外）：⑨ 站点根页（真实 DOM 锚点markup，
`healthcheck()` HIGH 缺陷修复的回归基线）、⑩ bib 卷级前导 entry-only 文件
（`count_bib_entries` MEDIUM 缺陷修复的回归基线）；⑦ 的配套 bib 也补了一份
含真实前导 entry 的变体（见 fixture ②/⑥ 小节）。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from helpers.golden import assert_matches_golden
from helpers.pmlr_fixtures import fixture_bytes
from paper_crawler.adapters.pmlr import parse
from paper_crawler.adapters.pmlr.adapter import _HEALTHCHECK_TITLE_TEXT, _VOLUME_ANCHOR_RE
from paper_crawler.errors import CrawlerError

_GOLDEN_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "pmlr" / "golden"
_ANCHOR_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "pmlr" / "dblp-icml-anchor.json"


def _bib_body_without_percent_comments(text: str) -> str:
    """去掉 ``%`` 开头的整行注释后的正文——供本文件里"直接文本计数交叉核对"的
    测试使用。**不要用裸 `str.count()` 扫全文件**：本文件自己的 fixture 头注释
    出于说明目的会写出 `@Proceedings{...}` 这样的示例语法（正是本轮修复的
    `count_bib_entries` 曾经踩过的同一类坑的测试层镜像——先前是 HTML 注释里
    写出 `class="paper"` 骗过 HTML 正则，这次是 bib 注释里写出 `@Proceedings{`
    骗过 naive 计数）；必须先剥掉 `%` 注释行再数，才是与源码算法同口径的验证。
    """
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("%"))


# --- ① 卷 index 正常页 ---------------------------------------------------------------------------


def test_fixture_01_volume_index_normal_has_three_papers_mixed_hosts() -> None:
    papers = parse.parse_volume_index(fixture_bytes("01_volume_index_normal.html"))
    assert len(papers) == 3
    slugs = [p.slug for p in papers]
    assert slugs == ["abad-rocamora24a", "example-selfhosted24b", "another-example24c"]
    # 双域端到端覆盖（design §6.2 item 1）：>=1 GitHub + >=1 自托管。
    hosts = {p.pdf_url.split("/")[2] for p in papers if p.pdf_url}
    assert hosts == {"raw.githubusercontent.com", "proceedings.mlr.press"}


def test_fixture_01_first_entry_matches_live_verified_real_values() -> None:
    # 真实条目（v235/abad-rocamora24a）：docs/research/site-survey/pmlr.md item 2/3。
    paper = parse.parse_volume_index(fixture_bytes("01_volume_index_normal.html"))[0]
    assert paper.title == "Revisiting Character-level Adversarial Attacks for Language Models"
    assert paper.firstpage == 1
    assert paper.lastpage == 30
    assert paper.openreview_id == "AZWqXfM6z9"
    assert paper.pdf_url == (
        "https://raw.githubusercontent.com/mlresearch/v235/main/assets/"
        "abad-rocamora24a/abad-rocamora24a.pdf"
    )


def test_fixture_01_golden_paper_stubs() -> None:
    papers = parse.parse_volume_index(fixture_bytes("01_volume_index_normal.html"))
    stubs = [parse.to_paper_stub(p, volume="235", year=2024) for p in papers]
    assert_matches_golden(stubs, _GOLDEN_DIR / "01_volume_index_normal.json")


# --- ② bibliography.bib 正常文件 ------------------------------------------------------------------


def test_fixture_02_bibliography_normal_has_three_entries_matching_fixture_01() -> None:
    # 与 fixture ① 的三篇一一对应——供 0-div 消歧"bib>0"分支复用（fixture ④）。
    # 本文件现含真实形态的卷级前导 @Proceedings{} entry（独立审查 2026-07-22
    # MEDIUM 发现）；断言仍为 3（只数论文），证明该前导 entry 被正确排除在外。
    assert parse.count_bib_entries(fixture_bytes("02_bibliography_normal.bib")) == 3


def test_fixture_02_leading_proceedings_entry_is_present_but_excluded() -> None:
    """直接钉死"文件确实含 4 个顶层 @ 块，但只有 3 个被计入"——防止未来有人
    误删前导 entry 而让 test_..._has_three_entries... 退化成"巧合对"的假阳性。
    """
    body = _bib_body_without_percent_comments(
        fixture_bytes("02_bibliography_normal.bib").decode("utf-8")
    )
    assert body.count("@Proceedings{") == 1
    assert body.count("@InProceedings{") == 3
    assert parse.count_bib_entries(fixture_bytes("02_bibliography_normal.bib")) == 3


# --- ④ parse 故障页（0-div，配套 bib>0）-----------------------------------------------------------


def test_fixture_04_parse_fault_page_has_zero_divs() -> None:
    assert parse.parse_volume_index(fixture_bytes("04_volume_index_parse_fault.html")) == ()


def test_fixture_04_paired_with_fixture_02_triggers_parse_disambiguation() -> None:
    # 消歧本身在 adapter 层（见 test_pmlr_adapter.py），此处只验证 fixture 数据形状：
    # 0-div + 配套 bib>0 才是"parse"判据（design §3.2 表）。
    html_divs = parse.parse_volume_index(fixture_bytes("04_volume_index_parse_fault.html"))
    bib_count = parse.count_bib_entries(fixture_bytes("02_bibliography_normal.bib"))
    assert len(html_divs) == 0
    assert bib_count > 0


# --- ⑤ 404 卷页 -----------------------------------------------------------------------------------


def test_fixture_05_volume_404_body_is_generic_not_parsed() -> None:
    # 判据靠 HTTP status，不靠 body（design §2）——本 fixture 只需能被读取；
    # 若误喂进 parse_volume_index 也应得到 0 papers（无 <div class="paper">）。
    body = fixture_bytes("05_volume_404.html")
    assert b"Page not found" in body
    assert parse.parse_volume_index(body) == ()


# --- ⑥/⑦/⑩ 合法空卷（0-div + bib==0，两种 bib 形态）--------------------------------------------


def test_fixture_06_volume_index_empty_has_zero_divs() -> None:
    assert parse.parse_volume_index(fixture_bytes("06_volume_index_empty.html")) == ()


def test_fixture_07_bibliography_empty_has_zero_entries() -> None:
    assert parse.count_bib_entries(fixture_bytes("07_bibliography_empty.bib")) == 0


def test_fixture_06_and_07_paired_form_legal_empty_state() -> None:
    html_divs = parse.parse_volume_index(fixture_bytes("06_volume_index_empty.html"))
    bib_count = parse.count_bib_entries(fixture_bytes("07_bibliography_empty.bib"))
    assert len(html_divs) == 0
    assert bib_count == 0  # design §3.2 表："0 + 0" = 合法空卷，非错误


def test_fixture_10_header_only_bib_has_zero_paper_entries_despite_one_raw_block() -> None:
    """独立审查 2026-07-22 MEDIUM 发现的具体风险场景（Cannot-verify #1：真实是否
    存在该形态未经实测，但函数必须在该形态下仍正确）：bib 文件含 1 个顶层
    @ 块（卷级 @Proceedings{}），但 0 个论文 entry——`count_bib_entries` 必须
    返回 0（而非旧实现会返回的 1），B5"合法空卷"分支才不会被误判 `parse`。
    """
    data = fixture_bytes("10_bibliography_header_only.bib")
    body = _bib_body_without_percent_comments(data.decode("utf-8"))
    assert body.count("@Proceedings{") == 1
    assert "@InProceedings{" not in body
    assert parse.count_bib_entries(data) == 0


def test_fixture_06_and_10_paired_also_form_legal_empty_state() -> None:
    # 与 07 并列的另一种"合法空卷"配套 bib 形态（有卷级前导 entry）。
    html_divs = parse.parse_volume_index(fixture_bytes("06_volume_index_empty.html"))
    bib_count = parse.count_bib_entries(fixture_bytes("10_bibliography_header_only.bib"))
    assert len(html_divs) == 0
    assert bib_count == 0


# --- ⑧ 单篇 abs 详情页（citation_* meta）----------------------------------------------------------


def test_fixture_08_paper_landing_page_citation_meta_matches_live_verified_values() -> None:
    meta = parse.parse_citation_meta(fixture_bytes("08_paper_landing_page.html"))
    assert meta.title == "Revisiting Character-level Adversarial Attacks for Language Models"
    assert meta.authors == ("Elias Abad Rocamora",)
    assert meta.firstpage == 1
    assert meta.lastpage == 30
    assert meta.issn == "2640-3498"
    assert meta.conference_title == "International Conference on Machine Learning"
    assert meta.publication_date == "2024/07/08"


def test_fixture_08_bibkey_cross_references_fixture_01_identifier() -> None:
    # bibkey 反查端到端：详情页内嵌 key 必须与卷 index 页构造出的 identifier 一致。
    meta = parse.parse_citation_meta(fixture_bytes("08_paper_landing_page.html"))
    paper = parse.parse_volume_index(fixture_bytes("01_volume_index_normal.html"))[0]
    stub = parse.to_paper_stub(paper, volume="235", year=2024)
    assert meta.bibkey == dict(stub.identifiers)["pmlr"]


# --- ⑨ 站点根页（真实 DOM 锚点markup；独立审查 2026-07-22 追加）-----------------------------------


def test_fixture_09_site_root_normal_has_real_bold_wrapped_anchors() -> None:
    """确认本 fixture 确实复刻了审查报告引述的真实 markup 形态（否则这份"回归
    基线"本身就会退化成又一份想当然的合成片段，重蹈 HIGH 缺陷的覆辙）。
    """
    body = fixture_bytes("09_site_root_normal.html")
    assert b'<a href="v235"><b>Volume 235</b></a> Proceedings of ICML 2024' in body
    # 锚点在 </b> 处提前闭合——锚点标签本身不含 "Proceedings of"。
    assert b'<a href="v235"><b>Volume 235</b></a> Proceedings' not in body.replace(b" ", b"")


def test_fixture_09_site_root_normal_passes_healthcheck_assertions_via_clean_text() -> None:
    text = fixture_bytes("09_site_root_normal.html").decode("utf-8")
    visible = parse.clean_text(text)
    assert _HEALTHCHECK_TITLE_TEXT in visible
    assert _VOLUME_ANCHOR_RE.search(visible) is not None


def test_fixture_09_site_root_normal_would_fail_naive_raw_html_regex() -> None:
    """反证：证明修复前的"对原始带标签 HTML 直接正则"做法在这份真实形态 fixture
    上必然不匹配——独立佐证 HIGH 缺陷的真实性与修复的必要性，而不只是空口白说。
    """
    text = fixture_bytes("09_site_root_normal.html").decode("utf-8")
    assert _VOLUME_ANCHOR_RE.search(text) is None  # 未清洗的原始 HTML 上必然落空


# --- D-019 锚点表（内部一致性：与 venues/cs_ai/icml.yaml 的 volume_map 不漂移）--------------------


def test_dblp_icml_anchor_seed_row_matches_live_verified_count() -> None:
    anchor = json.loads(_ANCHOR_PATH.read_text(encoding="utf-8"))
    rows = {row["year"]: row for row in anchor["rows"]}
    seed = rows[2024]
    assert seed["volume"] == 235
    assert seed["paper_count_claimed"] == 2610
    assert seed["dblp_slug"] == "conf/icml/icml2024"
    # D-019：2026-07-23 M2a 在线债务清理完成人工 DBLP 交叉核对（dblp.org/db/conf/icml/
    # icml2024.html，2610 条 inproceedings，与种子值精确匹配）——种子行状态由 pending
    # 转正为 LIVE 核准值，见 tests/fixtures/pmlr/dblp-icml-anchor.json 行内 note。
    assert seed["dblp_cross_check"] == "LIVE_2026-07-23_MATCH"
    assert seed["dblp_toc_count"] == 2610


def test_dblp_icml_anchor_years_are_subset_of_venue_yaml_volume_map() -> None:
    venues_dir = Path(__file__).resolve().parents[2] / "venues"
    import yaml

    icml_yaml = yaml.safe_load((venues_dir / "cs_ai" / "icml.yaml").read_text(encoding="utf-8"))
    venue_volume_map: dict[int, int] = icml_yaml["quirks"]["volume_map"]

    anchor = json.loads(_ANCHOR_PATH.read_text(encoding="utf-8"))
    for row in anchor["rows"]:
        assert row["year"] in venue_volume_map
        assert row["volume"] == venue_volume_map[row["year"]]


def test_dblp_icml_anchor_non_seed_rows_still_pending_human_confirmation() -> None:
    # D-019：2026-07-23 M2a 在线债务清理仅对种子行（2024）做了真实 DBLP 交叉核对
    # （见 test_dblp_icml_anchor_seed_row_matches_live_verified_count）；其余年份未
    # 触碰，必须继续诚实标 pending（不得悄悄标记为已核准）。
    anchor = json.loads(_ANCHOR_PATH.read_text(encoding="utf-8"))
    non_seed_rows = [row for row in anchor["rows"] if row["year"] != 2024]
    assert len(non_seed_rows) == len(anchor["rows"]) - 1
    assert all(row["dblp_cross_check"] == "pending" for row in non_seed_rows)


# --- 反例：非 pmlr 结构的输入不应被误判为"有效卷页" -----------------------------------------------


def test_unrelated_html_without_paper_divs_raises_nothing_just_empty() -> None:
    with pytest.raises(CrawlerError):
        parse.parse_volume_index(b'<div class="paper"><p class="details">no title here</p></div>')
