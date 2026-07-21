"""pmlr 解析器单测（design/adapters/pmlr.md §3.2/§6.1；T1）。

零网络：内联 HTML/BibTeX 片段覆盖块解析矩阵、相对链接解析、identifier 构造、
BibTeX entry 计数（转义/Unicode/嵌套花括号）、空/parse 判别的解析器侧行为。
真实响应结构的七件套 fixture 由 `tests/unit/test_pmlr_fixtures.py` 单独覆盖。
"""

from __future__ import annotations

import pytest

from paper_crawler.adapters.pmlr import parse
from paper_crawler.errors import CrawlerError, ErrorClass

# --- 卷 index 块解析 ----------------------------------------------------------------------------


def _paper_div(
    *,
    title: str = "Example Paper Title",
    authors: str = "Jane Researcher, Alex Example",
    pages: str = "PMLR 235:1-30, 2024.",
    abs_href: str = "v235/example24a.html",
    pdf_href: str
    | None = "https://raw.githubusercontent.com/mlresearch/v235/main/assets/example24a/example24a.pdf",
    openreview_href: str | None = "https://openreview.net/forum?id=abc123XYZ",
) -> str:
    links = [f'[<a href="{abs_href}">abs</a>]']
    if pdf_href is not None:
        links.append(f'[<a href="{pdf_href}">Download PDF</a>]')
    if openreview_href is not None:
        links.append(f'[<a href="{openreview_href}">OpenReview</a>]')
    return (
        '<div class="paper">'
        f'<p class="title">{title}</p>'
        f'<p class="details"><span class="authors">{authors}</span><br>{pages}</p>'
        f'<p class="links">{"".join(links)}</p>'
        "</div>"
    )


def _page(*divs: str) -> bytes:
    body = "\n".join(divs)
    return f"<html><body><div id='content'>{body}</div></body></html>".encode()


def test_parse_volume_index_extracts_full_field_set() -> None:
    papers = parse.parse_volume_index(_page(_paper_div()))
    assert len(papers) == 1
    paper = papers[0]
    assert paper.title == "Example Paper Title"
    assert paper.authors == ("Jane Researcher", "Alex Example")
    assert paper.firstpage == 1
    assert paper.lastpage == 30
    assert paper.slug == "example24a"
    assert paper.landing_url == "https://proceedings.mlr.press/v235/example24a.html"
    assert (
        paper.pdf_url
        == "https://raw.githubusercontent.com/mlresearch/v235/main/assets/example24a/example24a.pdf"
    )
    assert paper.openreview_id == "abc123XYZ"


def test_parse_volume_index_multiple_divs_in_document_order() -> None:
    papers = parse.parse_volume_index(
        _page(
            _paper_div(title="First", abs_href="v235/first24a.html"),
            _paper_div(title="Second", abs_href="v235/second24b.html"),
        )
    )
    assert [p.title for p in papers] == ["First", "Second"]
    assert [p.slug for p in papers] == ["first24a", "second24b"]


def test_parse_volume_index_zero_divs_returns_empty_tuple_not_error() -> None:
    # 0-div 本身不是本函数的错误态——消歧责任在调用方（结合 bib 计数）。
    html_no_papers = b"<html><body><div id='content'><p>No papers yet.</p></div></body></html>"
    assert parse.parse_volume_index(html_no_papers) == ()


def test_parse_volume_index_ignores_non_paper_divs() -> None:
    page = (
        (b"<html><body><div id='content'><div class='nav'>Home</div>")
        + _paper_div().encode()
        + b"</div></body></html>"
    )
    papers = parse.parse_volume_index(page)
    assert len(papers) == 1


# --- 可选字段缺失容忍（pdf_url/openreview/pages 非必需）------------------------------------------


def test_parse_volume_index_missing_pdf_link_is_none_not_error() -> None:
    papers = parse.parse_volume_index(_page(_paper_div(pdf_href=None)))
    assert papers[0].pdf_url is None


def test_parse_volume_index_missing_openreview_link_is_none() -> None:
    papers = parse.parse_volume_index(_page(_paper_div(openreview_href=None)))
    assert papers[0].openreview_id is None


def test_parse_volume_index_missing_pages_pattern_is_none_tuple() -> None:
    papers = parse.parse_volume_index(_page(_paper_div(pages="No page info here.")))
    assert papers[0].firstpage is None
    assert papers[0].lastpage is None


def test_parse_volume_index_single_author_no_comma() -> None:
    papers = parse.parse_volume_index(_page(_paper_div(authors="Solo Author")))
    assert papers[0].authors == ("Solo Author",)


# --- 必需字段缺失 → PARSE ------------------------------------------------------------------------


def test_parse_volume_index_missing_title_is_parse_error() -> None:
    block = (
        '<div class="paper"><p class="details"><span class="authors">A</span></p>'
        '<p class="links">[<a href="v235/x24a.html">abs</a>]</p></div>'
    )
    with pytest.raises(CrawlerError) as exc:
        parse.parse_volume_index(_page(block))
    assert exc.value.error_class is ErrorClass.PARSE


def test_parse_volume_index_missing_abs_link_is_parse_error() -> None:
    block = (
        '<div class="paper"><p class="title">T</p>'
        '<p class="links">[<a href="https://openreview.net/forum?id=x">OpenReview</a>]</p></div>'
    )
    with pytest.raises(CrawlerError) as exc:
        parse.parse_volume_index(_page(block))
    assert exc.value.error_class is ErrorClass.PARSE


# --- 相对链接解析（无前导斜杠，须以站点根解析）---------------------------------------------------


def test_abs_link_resolves_against_site_root_not_fetched_page_url() -> None:
    # href 自身已含 'v235/' 前缀；解析基准是站点根，不是"当前抓取页 URL"——
    # 否则会重复拼出 v235/v235/... （pmlr.md §3.2 明文警告的陷阱）。
    papers = parse.parse_volume_index(_page(_paper_div(abs_href="v235/example24a.html")))
    assert papers[0].landing_url == "https://proceedings.mlr.press/v235/example24a.html"
    assert "v235/v235" not in papers[0].landing_url


def test_slug_extraction_preserves_case_and_hyphens() -> None:
    papers = parse.parse_volume_index(_page(_paper_div(abs_href="v235/Abad-Rocamora24a.html")))
    assert papers[0].slug == "Abad-Rocamora24a"  # 原样保留，不做大小写归一


# --- 转义 / Unicode / 空白规整 -------------------------------------------------------------------


def test_title_html_entities_and_tags_are_unescaped_and_stripped() -> None:
    block = _paper_div(title="A &amp; B: <em>Emphasis</em> and Schr&ouml;dinger")
    papers = parse.parse_volume_index(_page(block))
    assert papers[0].title == "A & B: Emphasis and Schrödinger"


def test_title_whitespace_is_normalized() -> None:
    block = _paper_div(title="Multi   \n  line\ttitle")
    papers = parse.parse_volume_index(_page(block))
    assert papers[0].title == "Multi line title"


# --- identifier / PaperStub 转换 ------------------------------------------------------------------


def test_to_paper_stub_builds_verbatim_bibkey_identifier() -> None:
    paper = parse.parse_volume_index(_page(_paper_div(abs_href="v235/abad-rocamora24a.html")))[0]
    stub = parse.to_paper_stub(paper, volume="235", year=2024)
    assert stub.identifiers == (("pmlr", "pmlr-v235-abad-rocamora24a"),)
    assert stub.year == 2024


def test_to_paper_stub_meta_contains_only_documented_keys_in_order() -> None:
    paper = parse.parse_volume_index(_page(_paper_div()))[0]
    stub = parse.to_paper_stub(paper, volume="235", year=2024)
    assert [k for k, _ in stub.meta] == ["pdf_url", "landing_url", "openreview"]
    meta = dict(stub.meta)
    assert meta["pdf_url"] == paper.pdf_url
    assert meta["landing_url"] == paper.landing_url
    assert meta["openreview"] == paper.openreview_id


def test_to_paper_stub_omits_missing_optional_meta_keys() -> None:
    paper = parse.parse_volume_index(_page(_paper_div(pdf_href=None, openreview_href=None)))[0]
    stub = parse.to_paper_stub(paper, volume="235", year=2024)
    assert [k for k, _ in stub.meta] == ["landing_url"]


def test_to_paper_stub_abstract_and_pub_date_left_none() -> None:
    paper = parse.parse_volume_index(_page(_paper_div()))[0]
    stub = parse.to_paper_stub(paper, volume="235", year=2024)
    assert stub.abstract is None
    assert stub.pub_date is None


# --- bib entry 计数（转义 / Unicode / entry 计数）-------------------------------------------------


def test_count_bib_entries_basic() -> None:
    bib = b"""
@InProceedings{pmlr-v235-a24a,
  title = {Paper A},
  author = {Someone},
  pages = {1--10}
}
@InProceedings{pmlr-v235-b24b,
  title = {Paper B},
  pages = {11--20}
}
"""
    assert parse.count_bib_entries(bib) == 2


def test_count_bib_entries_nested_braces_do_not_confuse_counter() -> None:
    bib = b"""
@InProceedings{pmlr-v235-a24a,
  title = {{BERT}: Pre-training of Deep {{Bidirectional}} Transformers},
  author = {Someone}
}
"""
    assert parse.count_bib_entries(bib) == 1


def test_count_bib_entries_at_sign_inside_field_value_not_counted() -> None:
    bib = b"""
@InProceedings{pmlr-v235-a24a,
  title = {Paper A},
  note = {contact author@example.com for details}
}
"""
    assert parse.count_bib_entries(bib) == 1


def test_count_bib_entries_unicode_diacritics() -> None:
    bib = "@InProceedings{pmlr-v235-x24a,\n  author = {Schrödinger, Erwin}\n}\n".encode()
    assert parse.count_bib_entries(bib) == 1


def test_count_bib_entries_top_level_percent_comment_with_at_sign_ignored() -> None:
    bib = b"""% see also @SomethingElse{not-an-entry}
@InProceedings{pmlr-v235-a24a,
  title = {Paper A}
}
"""
    assert parse.count_bib_entries(bib) == 1


def test_count_bib_entries_empty_file_is_zero() -> None:
    assert parse.count_bib_entries(b"% empty bibliography\n") == 0
    assert parse.count_bib_entries(b"") == 0


def test_count_bib_entries_space_between_type_and_brace() -> None:
    # 少数 bib 生成器在 entry type 与开花括号间留空格：`@InProceedings {key, ...}`。
    bib = b"@InProceedings {pmlr-v235-a24a,\n  title = {Paper A}\n}\n"
    assert parse.count_bib_entries(bib) == 1


def test_count_bib_entries_stray_at_sign_not_followed_by_brace_is_not_counted() -> None:
    # 顶层裸 '@' 后接的不是 `word{`（如邮件署名残片）——不应被计为新 entry，
    # 也不应打乱后续真实 entry 的扫描。
    bib = b"contact @ conference for details\n@InProceedings{pmlr-v235-a24a,\n  title={T}\n}\n"
    assert parse.count_bib_entries(bib) == 1


def test_count_bib_entries_stray_braces_before_first_entry_do_not_affect_depth() -> None:
    # entry 之外（顶层）的孤立花括号不应影响后续深度追踪。
    bib = b"{stray} } another stray brace {\n@InProceedings{pmlr-v235-a24a,\n  title={T}\n}\n"
    assert parse.count_bib_entries(bib) == 1


# --- 相对链接/作者提取的边界形态 -----------------------------------------------------------------


def test_abs_link_href_not_ending_in_html_yields_no_slug() -> None:
    block = _paper_div(abs_href="v235/example24a")  # 缺 .html 后缀，形态非法
    with pytest.raises(CrawlerError) as exc:
        parse.parse_volume_index(_page(block))
    assert exc.value.error_class is ErrorClass.PARSE


def test_abs_link_href_empty_slug_after_stripping_yields_no_slug() -> None:
    block = _paper_div(abs_href="v235/.html")  # 剥离后缀后 slug 为空串
    with pytest.raises(CrawlerError) as exc:
        parse.parse_volume_index(_page(block))
    assert exc.value.error_class is ErrorClass.PARSE


def test_authors_span_present_but_blank_yields_empty_tuple() -> None:
    papers = parse.parse_volume_index(_page(_paper_div(authors="   ")))
    assert papers[0].authors == ()


# --- citation_* meta（推迟路径的解析基础）-------------------------------------------------------


def test_parse_citation_meta_extracts_full_field_set() -> None:
    page = b"""<html><head>
<meta name="citation_title" content="Revisiting Character-level Adversarial Attacks">
<meta name="citation_author" content="Elias Abad Rocamora">
<meta name="citation_pdf_url" content="https://raw.githubusercontent.com/mlresearch/v235/main/assets/abad-rocamora24a/abad-rocamora24a.pdf">
<meta name="citation_abstract_html_url" content="https://proceedings.mlr.press/v235/abad-rocamora24a.html">
<meta name="citation_firstpage" content="1">
<meta name="citation_lastpage" content="30">
<meta name="citation_publication_date" content="2024/07/08">
<meta name="citation_conference_title" content="International Conference on Machine Learning">
<meta name="citation_issn" content="2640-3498">
</head><body>
@InProceedings{pmlr-v235-abad-rocamora24a,
  title = {Revisiting Character-level Adversarial Attacks}
}
</body></html>"""
    meta = parse.parse_citation_meta(page)
    assert meta.title == "Revisiting Character-level Adversarial Attacks"
    assert meta.authors == ("Elias Abad Rocamora",)
    assert meta.firstpage == 1
    assert meta.lastpage == 30
    assert meta.issn == "2640-3498"
    assert meta.bibkey == "pmlr-v235-abad-rocamora24a"


def test_parse_citation_meta_multiple_authors_each_own_tag() -> None:
    page = b"""<html><head>
<meta name="citation_author" content="First Author">
<meta name="citation_author" content="Second Author">
</head><body></body></html>"""
    meta = parse.parse_citation_meta(page)
    assert meta.authors == ("First Author", "Second Author")


def test_parse_citation_meta_missing_fields_are_none() -> None:
    meta = parse.parse_citation_meta(b"<html><head></head><body>no meta here</body></html>")
    assert meta.title is None
    assert meta.authors == ()
    assert meta.bibkey is None


def test_parse_citation_meta_non_numeric_page_is_none_not_error() -> None:
    page = (
        b'<html><head><meta name="citation_firstpage" content="n/a">'
        b'<meta name="citation_lastpage" content="also-not-a-number"></head><body></body></html>'
    )
    meta = parse.parse_citation_meta(page)
    assert meta.firstpage is None
    assert meta.lastpage is None
