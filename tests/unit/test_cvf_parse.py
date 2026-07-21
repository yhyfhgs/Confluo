"""cvf 列表页解析器单测（design/adapters/cvf.md §2/§3.2；T1）。

零网络（输入 HTML 字面量）：单/多条目抽取、作者 `input[name=query_author]` 提取、
pdf/supp/arXiv 按锚文本分类（不被 bibtex-toggle/作者提交链接误判）、URL 绝对化
（相对→绝对，双 era 同一函数）、identifier 构造与大小写保留、缺 pdf href /
空标题 → PARSE、Unicode 作者名、day=all 链接判据、PDF 路径改写规则交叉校验
（T1 专属，非运行时来源，见 design §3.3）。

条目 1（GFPose）逐字转录自 [LIVE] 站点勘察（research/site-survey/cvf.md §2b）——
真实标题/作者/href/arXiv id，非合成值；其余条目按站点选择器规则合成。
"""

from __future__ import annotations

import pytest

from paper_crawler.adapters.cvf import parse
from paper_crawler.errors import CrawlerError, ErrorClass

_CVPR2023_URL = "https://openaccess.thecvf.com/CVPR2023?day=all"
_CVPR2013_URL = "https://openaccess.thecvf.com/CVPR2013"


def _entry_html(
    *,
    title: str,
    landing_href: str,
    authors: list[str],
    pdf_href: str,
    supp_href: str | None = None,
    arxiv_href: str | None = None,
) -> str:
    """按 [LIVE] §2b 选择器规则合成一条列表页条目的原始 HTML。"""
    author_forms = "".join(
        f'<form id="f{i}" action="/CVPR2023" method="post" class="authsearch">\n'
        f'<input type="hidden" name="query_author" value="{a}">\n'
        f'<a href="#" onclick="document.getElementById(\'f{i}\').submit();">{a}</a>,\n'
        "</form>\n"
        for i, a in enumerate(authors)
    )
    links = [f'[<a href="{pdf_href}">pdf</a>]\n']
    if supp_href:
        links.append(f'[<a href="{supp_href}">supp</a>]\n')
    if arxiv_href:
        links.append(f'[<a href="{arxiv_href}">arXiv</a>]\n')
    links.append(
        '<div class="link2">[<a class="fakelink" '
        "onclick=\"$(this).siblings('.bibref').slideToggle()\">bibtex</a>]\n"
        '<div class="bibref pre-white-space">@InProceedings{x_2023_CVPR,\n'
        f"    title = {{{title}}},\n"
        "}</div>\n</div>\n"
    )
    return (
        f'<dt class="ptitle"><br><a href="{landing_href}">{title}</a></dt>\n'
        f"<dd>\n{author_forms}</dd>\n"
        f"<dd>\n{''.join(links)}</dd>\n"
    )


def _page(*entries: str) -> str:
    body = "\n".join(entries)
    return f'<html><body><div id="content"><dl>\n{body}\n</dl></div></body></html>'


# --- GFPose：真实条目（[LIVE] research/site-survey/cvf.md §2b 逐字转录）----------------------

_GFPOSE_TITLE = "GFPose: Learning 3D Human Pose Prior With Gradient Fields"
_GFPOSE_LANDING = (
    "/content/CVPR2023/html/"
    "Ci_GFPose_Learning_3D_Human_Pose_Prior_With_Gradient_Fields_CVPR_2023_paper.html"
)
_GFPOSE_PDF = (
    "/content/CVPR2023/papers/"
    "Ci_GFPose_Learning_3D_Human_Pose_Prior_With_Gradient_Fields_CVPR_2023_paper.pdf"
)
_GFPOSE_SUPP = "/content/CVPR2023/supplemental/Ci_GFPose_Learning_3D_CVPR_2023_supplemental.pdf"
_GFPOSE_ARXIV = "http://arxiv.org/abs/2212.08641"
_GFPOSE_AUTHORS = [
    "Hai Ci",
    "Mingdong Wu",
    "Wentao Zhu",
    "Xiaoxuan Ma",
    "Hao Dong",
    "Fangwei Zhong",
    "Yizhou Wang",
]
_GFPOSE_STEM = "Ci_GFPose_Learning_3D_Human_Pose_Prior_With_Gradient_Fields_CVPR_2023_paper"


def _gfpose_html() -> str:
    return _entry_html(
        title=_GFPOSE_TITLE,
        landing_href=_GFPOSE_LANDING,
        authors=_GFPOSE_AUTHORS,
        pdf_href=_GFPOSE_PDF,
        supp_href=_GFPOSE_SUPP,
        arxiv_href=_GFPOSE_ARXIV,
    )


# --- parse_list_page：抽取 ---------------------------------------------------------------------


def test_gfpose_full_combo_entry_extracted() -> None:
    (entry,) = parse.parse_list_page(_page(_gfpose_html()))
    assert entry.title == _GFPOSE_TITLE
    assert entry.landing_href == _GFPOSE_LANDING
    assert entry.authors == tuple(_GFPOSE_AUTHORS)
    assert entry.pdf_href == _GFPOSE_PDF
    assert entry.supp_href == _GFPOSE_SUPP
    assert entry.arxiv_href == _GFPOSE_ARXIV


def test_entry_with_pdf_and_arxiv_no_supp() -> None:
    html = _entry_html(
        title="Paper Without Supp",
        landing_href="/content/CVPR2023/html/a_paper.html",
        authors=["Ann Author"],
        pdf_href="/content/CVPR2023/papers/a_paper.pdf",
        arxiv_href="http://arxiv.org/abs/2301.00001",
    )
    (entry,) = parse.parse_list_page(_page(html))
    assert entry.pdf_href == "/content/CVPR2023/papers/a_paper.pdf"
    assert entry.supp_href is None
    assert entry.arxiv_href == "http://arxiv.org/abs/2301.00001"


def test_entry_with_pdf_and_supp_no_arxiv() -> None:
    html = _entry_html(
        title="Paper Without ArXiv",
        landing_href="/content/CVPR2023/html/b_paper.html",
        authors=["Bob Author"],
        pdf_href="/content/CVPR2023/papers/b_paper.pdf",
        supp_href="/content/CVPR2023/supplemental/b_supp.pdf",
    )
    (entry,) = parse.parse_list_page(_page(html))
    assert entry.supp_href == "/content/CVPR2023/supplemental/b_supp.pdf"
    assert entry.arxiv_href is None


def test_entry_with_pdf_only() -> None:
    html = _entry_html(
        title="Minimal Paper",
        landing_href="/content/CVPR2023/html/c_paper.html",
        authors=["Cy Author"],
        pdf_href="/content/CVPR2023/papers/c_paper.pdf",
    )
    (entry,) = parse.parse_list_page(_page(html))
    assert entry.pdf_href is not None
    assert entry.supp_href is None
    assert entry.arxiv_href is None


def test_multiple_entries_preserve_page_order() -> None:
    html = _page(
        _gfpose_html(),
        _entry_html(
            title="Second Paper",
            landing_href="/content/CVPR2023/html/second.html",
            authors=["Second Author"],
            pdf_href="/content/CVPR2023/papers/second.pdf",
        ),
        _entry_html(
            title="Third Paper",
            landing_href="/content/CVPR2023/html/third.html",
            authors=["Third Author"],
            pdf_href="/content/CVPR2023/papers/third.pdf",
        ),
    )
    entries = parse.parse_list_page(html)
    assert [e.title for e in entries] == [_GFPOSE_TITLE, "Second Paper", "Third Paper"]


def test_empty_page_yields_no_entries() -> None:
    assert parse.parse_list_page("<html><body>nothing here</body></html>") == []


def test_query_author_values_preserve_order() -> None:
    (entry,) = parse.parse_list_page(_page(_gfpose_html()))
    assert entry.authors == tuple(_GFPOSE_AUTHORS)


def test_query_author_input_with_empty_value_is_skipped() -> None:
    html = (
        '<dt class="ptitle"><br><a href="/x.html">Empty Author Value</a></dt>\n'
        '<dd><input type="hidden" name="query_author" value="">'
        '<input type="hidden" name="query_author" value="Real Author"></dd>\n'
        '<dd>[<a href="/x.pdf">pdf</a>]</dd>\n'
    )
    (entry,) = parse.parse_list_page(_page(html))
    assert entry.authors == ("Real Author",)  # 空 value 被跳过，不产生空字符串条目


def test_bibtex_toggle_link_text_not_misclassified() -> None:
    # bibtex 折叠开关的锚文本是 "bibtex"，不应污染 pdf/supp/arXiv 分类。
    (entry,) = parse.parse_list_page(_page(_gfpose_html()))
    assert entry.pdf_href == _GFPOSE_PDF  # 仍正确命中，未被 "bibtex" 链接覆盖


def test_unicode_author_name_captured_exactly() -> None:
    html = _entry_html(
        title="Unicode Author Paper",
        landing_href="/content/CVPR2023/html/unicode.html",
        authors=["Björn Ommer", "François Chollet", "Édouard Oyallon"],
        pdf_href="/content/CVPR2023/papers/unicode.pdf",
    )
    (entry,) = parse.parse_list_page(_page(html))
    assert entry.authors == ("Björn Ommer", "François Chollet", "Édouard Oyallon")


# --- 2013 flat era：相对路径、旧目录名、stem 词序不同（[LIVE] §9）------------------------------


def test_2013_relative_href_and_old_stem_word_order_extracted_as_is() -> None:
    html = _entry_html(
        title="Deformable Spatial Pyramid Matching for Fast Dense Correspondences",
        landing_href="content_cvpr_2013/html/Kim_Deformable_Spatial_Pyramid_2013_CVPR_paper.html",
        authors=["Jaechul Kim"],
        pdf_href="content_cvpr_2013/papers/Kim_Deformable_Spatial_Pyramid_2013_CVPR_paper.pdf",
    )
    (entry,) = parse.parse_list_page(_page(html))
    # parse_list_page 只机械抽取，相对路径原样保留（绝对化是 to_paper_stub 的职责）。
    assert entry.pdf_href == (
        "content_cvpr_2013/papers/Kim_Deformable_Spatial_Pyramid_2013_CVPR_paper.pdf"
    )
    assert entry.pdf_href is not None
    assert not entry.pdf_href.startswith("http")


# --- has_day_all_link：day-landing 页判据（§3.2 分支②）----------------------------------------


def test_has_day_all_link_true_on_landing_page() -> None:
    landing_html = """
    <div id="content"><h3>Papers</h3><dl>
    <dd>[<a href="/CVPR2023?day=2023-06-20">Day 1: 2023-06-20</a>]</dd>
    <dd>[<a href="/CVPR2023?day=2023-06-21">Day 2: 2023-06-21</a>]</dd>
    <dd>[<a href="/CVPR2023?day=all">All Papers</a>]</dd>
    </dl></div>
    """
    assert parse.has_day_all_link(landing_html) is True
    assert parse.parse_list_page(landing_html) == []  # 无 dt.ptitle 条目


def test_has_day_all_link_true_with_ampersand_form() -> None:
    assert parse.has_day_all_link('<a href="/CVPR2023?foo=1&amp;day=all">All</a>') is False
    # &amp; 是 HTML 实体；原始查询串真实形态是裸 '&'，本函数按裸串判定。
    assert parse.has_day_all_link("/CVPR2023?foo=1&day=all") is True


def test_has_day_all_link_false_on_structural_drift_page() -> None:
    assert parse.has_day_all_link("<html><body>unexpected content</body></html>") is False


# --- to_paper_stub：identifier/meta/URL 绝对化/校验（§3.2）------------------------------------


def _gfpose_entry() -> parse.RawEntry:
    (entry,) = parse.parse_list_page(_page(_gfpose_html()))
    return entry


def test_to_paper_stub_modern_full_combo() -> None:
    stub = parse.to_paper_stub(
        _gfpose_entry(), base_url=_CVPR2023_URL, canonical_dir="CVPR2023", year=2023
    )
    assert stub.title == _GFPOSE_TITLE
    assert stub.identifiers == (("cvf", f"CVPR2023/{_GFPOSE_STEM}"),)
    assert stub.year == 2023
    assert stub.abstract is None  # list-only：列表页不含摘要（§3.2 裁决）
    assert stub.authors == tuple(_GFPOSE_AUTHORS)

    meta = dict(stub.meta)
    assert meta[parse.META_PDF_URL] == f"https://openaccess.thecvf.com{_GFPOSE_PDF}"
    assert meta[parse.META_SUPP_URL] == f"https://openaccess.thecvf.com{_GFPOSE_SUPP}"
    assert meta[parse.META_LANDING_URL] == f"https://openaccess.thecvf.com{_GFPOSE_LANDING}"
    assert meta[parse.META_ARXIV] == "2212.08641"  # 线索 id，非 identifier


def test_to_paper_stub_case_preserved_in_identifier() -> None:
    # canonical_dir 与 stem 大小写原样——不做 upper()/lower()（design §3.2 显式断言）。
    stub = parse.to_paper_stub(
        _gfpose_entry(), base_url=_CVPR2023_URL, canonical_dir="CVPR2023", year=2023
    )
    _, value = stub.identifiers[0]
    assert value == "CVPR2023/" + _GFPOSE_STEM
    assert "GFPose" in value  # 混合大小写原样保留


def test_to_paper_stub_relative_2013_href_absolutized_via_urljoin() -> None:
    html = _entry_html(
        title="Deformable Spatial Pyramid Matching for Fast Dense Correspondences",
        landing_href="content_cvpr_2013/html/Kim_Deformable_Spatial_Pyramid_2013_CVPR_paper.html",
        authors=["Jaechul Kim"],
        pdf_href="content_cvpr_2013/papers/Kim_Deformable_Spatial_Pyramid_2013_CVPR_paper.pdf",
    )
    (entry,) = parse.parse_list_page(_page(html))
    stub = parse.to_paper_stub(entry, base_url=_CVPR2013_URL, canonical_dir="CVPR2013", year=2013)
    meta = dict(stub.meta)
    assert meta[parse.META_PDF_URL] == (
        "https://openaccess.thecvf.com/content_cvpr_2013/papers/"
        "Kim_Deformable_Spatial_Pyramid_2013_CVPR_paper.pdf"
    )
    _, value = stub.identifiers[0]
    # 早年 stem 词序 `_2013_CVPR_paper`（现代为 `_CVPR_2023_paper`）——原样保留，不改写。
    assert value == "CVPR2013/Kim_Deformable_Spatial_Pyramid_2013_CVPR_paper"


def test_to_paper_stub_no_supp_omits_supp_meta_key() -> None:
    html = _entry_html(
        title="No Supp Paper",
        landing_href="/content/CVPR2023/html/nosupp.html",
        authors=["Ann Author"],
        pdf_href="/content/CVPR2023/papers/nosupp.pdf",
        arxiv_href="http://arxiv.org/abs/2301.00002",
    )
    (entry,) = parse.parse_list_page(_page(html))
    stub = parse.to_paper_stub(entry, base_url=_CVPR2023_URL, canonical_dir="CVPR2023", year=2023)
    meta = dict(stub.meta)
    assert parse.META_SUPP_URL not in meta
    assert parse.META_ARXIV in meta


def test_to_paper_stub_no_arxiv_omits_arxiv_meta_key() -> None:
    html = _entry_html(
        title="No ArXiv Paper",
        landing_href="/content/CVPR2023/html/noarxiv.html",
        authors=["Bob Author"],
        pdf_href="/content/CVPR2023/papers/noarxiv.pdf",
        supp_href="/content/CVPR2023/supplemental/noarxiv_supp.pdf",
    )
    (entry,) = parse.parse_list_page(_page(html))
    stub = parse.to_paper_stub(entry, base_url=_CVPR2023_URL, canonical_dir="CVPR2023", year=2023)
    meta = dict(stub.meta)
    assert parse.META_ARXIV not in meta
    assert parse.META_SUPP_URL in meta


def test_to_paper_stub_missing_pdf_href_raises_parse() -> None:
    entry = parse.RawEntry(
        title="No Pdf Paper",
        landing_href="/content/CVPR2023/html/nopdf.html",
        authors=("Ann Author",),
        pdf_href=None,
        supp_href=None,
        arxiv_href=None,
    )
    with pytest.raises(CrawlerError) as exc:
        parse.to_paper_stub(entry, base_url=_CVPR2023_URL, canonical_dir="CVPR2023", year=2023)
    assert exc.value.error_class is ErrorClass.PARSE


def test_to_paper_stub_empty_title_raises_parse() -> None:
    entry = parse.RawEntry(
        title="",
        landing_href=None,
        authors=(),
        pdf_href="/content/CVPR2023/papers/x.pdf",
        supp_href=None,
        arxiv_href=None,
    )
    with pytest.raises(CrawlerError) as exc:
        parse.to_paper_stub(entry, base_url=_CVPR2023_URL, canonical_dir="CVPR2023", year=2023)
    assert exc.value.error_class is ErrorClass.PARSE


def test_to_paper_stub_pdf_href_not_ending_in_pdf_raises_parse() -> None:
    entry = parse.RawEntry(
        title="Weird Href Paper",
        landing_href=None,
        authors=(),
        pdf_href="/content/CVPR2023/papers/x.html",  # 非法：不以 .pdf 结尾
        supp_href=None,
        arxiv_href=None,
    )
    with pytest.raises(CrawlerError) as exc:
        parse.to_paper_stub(entry, base_url=_CVPR2023_URL, canonical_dir="CVPR2023", year=2023)
    assert exc.value.error_class is ErrorClass.PARSE


def test_to_paper_stub_missing_landing_href_omits_landing_meta_key() -> None:
    # landing_href 缺失（选择器未命中标题锚点的 href，但 pdf/title 仍在——防御性场景）
    # 不应致命，只是 meta 里没有 landing_url 键。
    entry = parse.RawEntry(
        title="No Landing Href Paper",
        landing_href=None,
        authors=("Ann Author",),
        pdf_href="/content/CVPR2023/papers/nolanding.pdf",
        supp_href=None,
        arxiv_href=None,
    )
    stub = parse.to_paper_stub(entry, base_url=_CVPR2023_URL, canonical_dir="CVPR2023", year=2023)
    meta = dict(stub.meta)
    assert parse.META_LANDING_URL not in meta
    assert parse.META_PDF_URL in meta


def test_to_paper_stub_year_none_passthrough() -> None:
    stub = parse.to_paper_stub(
        _gfpose_entry(), base_url=_CVPR2023_URL, canonical_dir="CVPR2023", year=None
    )
    assert stub.year is None


# --- stem 提取：naming-convention-agnostic（含 workshop 命名空间形态，design §3 workshop-ready）--


def test_stem_extraction_empty_stem_raises_parse() -> None:
    with pytest.raises(CrawlerError) as exc:
        parse._stem_from_pdf_url("https://openaccess.thecvf.com/content/CVPR2023/papers/.pdf")
    assert exc.value.error_class is ErrorClass.PARSE


def test_stem_extraction_workshop_shaped_href_naming_agnostic() -> None:
    # 本 adapter 不发现 workshop（design §1），但 stem 提取函数对任意 basename 中性——
    # 验证一个 workshop 形态 href（[LIVE] §5：CVPRW 标记、W 目录）同样能正确抽出 stem。
    workshop_pdf_url = (
        "https://openaccess.thecvf.com/content/CVPR2023W/WAD/papers/"
        "Singh_Something_CVPRW_2023_paper.pdf"
    )
    # 直接调用私有函数（T1 交叉校验，非运行时依赖——生产路径见 to_paper_stub 测试）。
    stem = parse._stem_from_pdf_url(workshop_pdf_url)
    assert stem == "Singh_Something_CVPRW_2023_paper"


# --- arXiv id 提取（meta 线索，非 identifier）--------------------------------------------------


@pytest.mark.parametrize(
    ("href", "expected"),
    [
        ("http://arxiv.org/abs/2212.08641", "2212.08641"),
        ("https://arxiv.org/abs/2212.08641v2", "2212.08641v2"),
        ("http://arxiv.org/abs/2212.08641/", "2212.08641"),
        ("not-an-arxiv-url", "not-an-arxiv-url"),  # 防御性：不匹配形状则原样返回
    ],
)
def test_arxiv_id_from_href(href: str, expected: str) -> None:
    assert parse._arxiv_id_from_href(href) == expected


# --- PDF 路径改写规则交叉校验（T1 专属；design §3.3："非运行时来源"，仅测试内验证一致）--------


def _rewrite_landing_to_pdf(landing_url: str) -> str:
    """独立重实现 html→pdf 路径改写规则（`/html/`→`/papers/`，`.html`→`.pdf`）。

    **仅供本测试交叉校验**：生产 `resolve_assets` 只读采集的 `[pdf]` href（design
    §3.3 裁决——supp 文件名不可推导，PDF 虽可改写但优先统一走采集 href 消除 era
    分支）。此函数独立于 `parse.py` 实现，避免"用同一段代码验证自己"的循环论证。
    """
    return landing_url.replace("/html/", "/papers/").removesuffix(".html") + ".pdf"


def test_pdf_rewrite_rule_matches_collected_href_for_gfpose() -> None:
    stub = parse.to_paper_stub(
        _gfpose_entry(), base_url=_CVPR2023_URL, canonical_dir="CVPR2023", year=2023
    )
    meta = dict(stub.meta)
    landing_url = meta[parse.META_LANDING_URL]
    rewritten = _rewrite_landing_to_pdf(landing_url)
    assert rewritten == meta[parse.META_PDF_URL]


def test_pdf_rewrite_rule_matches_collected_href_for_2013_relative_entry() -> None:
    html = _entry_html(
        title="Deformable Spatial Pyramid Matching for Fast Dense Correspondences",
        landing_href="content_cvpr_2013/html/Kim_Deformable_Spatial_Pyramid_2013_CVPR_paper.html",
        authors=["Jaechul Kim"],
        pdf_href="content_cvpr_2013/papers/Kim_Deformable_Spatial_Pyramid_2013_CVPR_paper.pdf",
    )
    (entry,) = parse.parse_list_page(_page(html))
    stub = parse.to_paper_stub(entry, base_url=_CVPR2013_URL, canonical_dir="CVPR2013", year=2013)
    meta = dict(stub.meta)
    landing_url = meta[parse.META_LANDING_URL]
    rewritten = _rewrite_landing_to_pdf(landing_url)
    assert rewritten == meta[parse.META_PDF_URL]
