"""oup_silverchair 落地页解析器单测（design/adapters/oup-silverchair.md §3.1）。

覆盖 PDF 链接抽取多形态（citation_pdf_url meta 首选 / article-pdf href 回退 / 相对
绝对化 / 0 命中 / 防御性形态校验 / meta 优先于 href）+ Supplementary 抽取（含
「SI 也走 article-pdf 路径」的桶归属）。零网络（纯字符串输入）。
"""

from __future__ import annotations

from helpers.oup_silverchair_fixtures import oup_fixture
from paper_crawler.adapters.oup_silverchair import parse

_ARTICLE_URL = "https://academic.oup.com/qje/article/141/3/2205/8662148"


def _fulltext_body() -> str:
    return oup_fixture("04_fulltext_logged_in")[3].decode("utf-8")


# --- extract_pdf_url ---------------------------------------------------------------


def test_citation_pdf_url_meta_is_preferred() -> None:
    pdf = parse.extract_pdf_url(_fulltext_body(), base_url=_ARTICLE_URL)
    assert pdf == "https://academic.oup.com/qje/article-pdf/141/3/2205/61701561/qjae044.pdf"


def test_citation_meta_wins_over_anchor_when_both_present() -> None:
    # meta 与锚点指向不同 file_id 时，meta 首选（design §3.1②）。
    html = (
        '<head><meta name="citation_pdf_url" '
        'content="https://academic.oup.com/qje/article-pdf/1/1/1/META999/a.pdf"/></head>'
        '<body><a href="/qje/article-pdf/1/1/1/ANCHOR111/a.pdf">PDF</a></body>'
    )
    pdf = parse.extract_pdf_url(html, base_url=_ARTICLE_URL)
    assert pdf == "https://academic.oup.com/qje/article-pdf/1/1/1/META999/a.pdf"


def test_anchor_fallback_when_no_meta() -> None:
    html = '<body><a href="/qje/article-pdf/140/2/889/61701561/qjae044.pdf">PDF</a></body>'
    pdf = parse.extract_pdf_url(html, base_url=_ARTICLE_URL)
    assert pdf == "https://academic.oup.com/qje/article-pdf/140/2/889/61701561/qjae044.pdf"


def test_root_relative_anchor_href_is_absolutized() -> None:
    # OUP 下载锚点为根相对路径（`/qje/article-pdf/…`）——urljoin 归一为绝对。
    html = '<a href="/qje/article-pdf/140/2/889/61701561/x.pdf">PDF</a>'
    pdf = parse.extract_pdf_url(html, base_url="https://academic.oup.com/qje/article/140/2/889/id")
    assert pdf == "https://academic.oup.com/qje/article-pdf/140/2/889/61701561/x.pdf"


def test_no_pdf_link_returns_none_on_abstract_page() -> None:
    body = oup_fixture("03_no_entitlement_abstract")[3].decode("utf-8")
    assert parse.extract_pdf_url(body, base_url=_ARTICLE_URL) is None


def test_no_pdf_link_returns_none_on_plain_page() -> None:
    html = "<html><body><p>Editorial board. Volume 141.</p></body></html>"
    assert parse.extract_pdf_url(html, base_url=_ARTICLE_URL) is None


def test_meta_pointing_to_non_article_pdf_is_rejected() -> None:
    # 防御性形态校验：citation_pdf_url 指向非 article-pdf 资源 → 视为未命中（返回 None）。
    html = (
        '<meta name="citation_pdf_url" '
        'content="https://academic.oup.com/qje/fulltext-html/141/3/2205"/>'
    )
    assert parse.extract_pdf_url(html, base_url=_ARTICLE_URL) is None


def test_empty_body_returns_none() -> None:
    assert parse.extract_pdf_url("", base_url=_ARTICLE_URL) is None


def test_anchor_without_href_is_skipped_gracefully() -> None:
    # 防御性：无 href 的锚点被跳过，不影响后续合法 article-pdf 锚点的抽取。
    html = '<a name="top">jump</a><a href="/qje/article-pdf/1/1/1/F9/x.pdf">PDF</a>'
    assert parse.extract_pdf_url(html, base_url=_ARTICLE_URL) == (
        "https://academic.oup.com/qje/article-pdf/1/1/1/F9/x.pdf"
    )


# --- extract_supplementary_urls ----------------------------------------------------


def test_supplementary_extracted_even_though_it_lives_on_article_pdf_path() -> None:
    # SI 附件也走 article-pdf 路径；supplementary 片段优先归 SI 桶，不污染正文 PDF。
    si = parse.extract_supplementary_urls(_fulltext_body(), base_url=_ARTICLE_URL)
    assert si == [
        "https://academic.oup.com/qje/article-pdf/141/3/2205/61701561/"
        "qjae044_supplementary_appendix.pdf"
    ]
    # 且正文 PDF 不是 SI（citation_pdf_url 首选，SI 路径含 supplementary 不会被当正文）。
    pdf = parse.extract_pdf_url(_fulltext_body(), base_url=_ARTICLE_URL)
    assert pdf is not None and "supplementary" not in pdf.lower()


def test_no_supplementary_returns_empty_list() -> None:
    html = '<a href="/qje/article-pdf/1/1/1/F/x.pdf">PDF</a>'
    assert parse.extract_supplementary_urls(html, base_url=_ARTICLE_URL) == []


def test_supplementary_dedup_preserves_order() -> None:
    html = (
        '<a href="/s/supplementary_a.pdf">a</a>'
        '<a href="/s/supplementary_b.pdf">b</a>'
        '<a href="/s/supplementary_a.pdf">a-dup</a>'
    )
    si = parse.extract_supplementary_urls(html, base_url=_ARTICLE_URL)
    assert si == [
        "https://academic.oup.com/s/supplementary_a.pdf",
        "https://academic.oup.com/s/supplementary_b.pdf",
    ]
