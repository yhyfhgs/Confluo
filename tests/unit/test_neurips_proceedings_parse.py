"""neurips_proceedings 零网络解析层单测（design/adapters/neurips-proceedings.md §3；T1）。

真实条目样本（1987 legacy / 2023 conference+D&B）逐字复用
docs/research/site-survey/neurips-proceedings.md §3 的 [LIVE] 实测 markup——不是本次
实现臆造的合成 HTML。2023 D&B 条目的作者列表在勘察原文里以 "lianhao yin, ..." 省略号
结尾（勘察自身的截断记号，不是真实站点内容），本文件只取勘察明确给出的两个真实姓名，
不杜撰省略号背后的第三作者。
"""

from __future__ import annotations

import pytest

from paper_crawler.adapters.neurips_proceedings import parse
from paper_crawler.errors import CrawlerError, ErrorClass

# --- 真实 markup 样本（[LIVE] site-survey §3，字段值逐字复用）-----------------------------------
#
# 用构造函数拼装而非整段粘贴大段原文字符串——单纯是为了在 100 列行宽内换行；href/title/
# authors 的**值**均逐字取自勘察原文，未做任何内容改写（长字符串用相邻字面量隐式拼接
# 换行，Python 不会在拼接点插入任何字符，故换行本身不改变被测字符串的内容）。


def _li(*, li_class: str, track: str, href: str, title: str, authors: str, badge: str = "") -> str:
    badge_html = f'<span class="paper-track-badge">{badge}</span>' if badge else ""
    return (
        f'<li class="{li_class}" data-track="{track}">'
        '<div class="paper-content">'
        f'<a title="paper title" href="{href}">{title}</a>'
        f'<span class="paper-authors">{authors}</span>'
        f"</div>{badge_html}</li>"
    )


_LEGACY_1987_LI = _li(
    li_class="",
    track="none",
    href="/paper_files/paper/1987/hash/03004620ea802b9118dd44d69f07af56-Abstract.html",
    title="Synchronization in Neural Nets",
    authors="Jacques J. Vidal, John Haggerty",
)

_MODERN_2023_CONFERENCE_LI = _li(
    li_class="conference",
    track="conference",
    href=("/paper_files/paper/2023/hash/0001ca33ba34ce0351e4612b744b3936-Abstract-Conference.html"),
    title=(
        "Modelling Cellular Perturbations with the Sparse Additive Mechanism Shift "
        "Variational Autoencoder"
    ),
    authors="Michael Bereket, Theofanis Karaletsos",
    badge="Main Conference Track",
)

_MODERN_2023_DB_LI = _li(
    li_class="datasets_and_benchmarks",
    track="datasets_and_benchmarks",
    href=(
        "/paper_files/paper/2023/hash/00ba06ba5c324efdfb068865ca44cf0b-"
        "Abstract-Datasets_and_Benchmarks.html"
    ),
    title=("Gigastep - One Billion Steps per Second Multi-agent Reinforcement Learning"),
    authors="Mathias Lechner, lianhao yin",
    badge="Datasets and Benchmarks Track",
)


def _page(*lis: str) -> bytes:
    body = "\n".join(lis)
    return f"<html><body><ul class='paper-list'>{body}</ul></body></html>".encode()


# --- era_for_year / volume_for_year（[LIVE] §2/§5 边界与不变式）--------------------------------


@pytest.mark.parametrize(
    ("year", "expected"),
    [(1987, "legacy"), (2019, "legacy"), (2021, "legacy"), (2022, "modern"), (2025, "modern")],
)
def test_era_for_year_boundary(year: int, expected: str) -> None:
    assert parse.era_for_year(year) == expected


@pytest.mark.parametrize(
    ("year", "expected_volume"), [(1987, 0), (1988, 1), (2023, 36), (2025, 38)]
)
def test_volume_for_year_matches_live_verified_invariant(year: int, expected_volume: int) -> None:
    # [LIVE] §2：vol = year - 1987（2025→38, 1988→1, 1987→0 均实测核对）。
    assert parse.volume_for_year(year) == expected_volume


# --- infix_for_era_track（(era,track)→infix 闭表，T1 矩阵）-------------------------------------


@pytest.mark.parametrize(
    ("era", "track", "expected"),
    [
        ("legacy", "none", ""),
        ("modern", "conference", "-Conference"),
        ("modern", "datasets_and_benchmarks", "-Datasets_and_Benchmarks"),
    ],
)
def test_infix_for_era_track_closed_table(era: str, track: str, expected: str) -> None:
    assert parse.infix_for_era_track(era, track) == expected


def test_infix_for_era_track_unknown_track_is_config() -> None:
    with pytest.raises(CrawlerError) as exc:
        parse.infix_for_era_track("modern", "position_papers")  # 假设的未来新 track
    assert exc.value.error_class is ErrorClass.CONFIG


def test_infix_for_era_track_missing_track_is_config() -> None:
    with pytest.raises(CrawlerError) as exc:
        parse.infix_for_era_track("modern", None)
    assert exc.value.error_class is ErrorClass.CONFIG


def test_infix_for_era_track_legacy_with_unexpected_track_is_config() -> None:
    # legacy 年 track 恒为 'none'（[LIVE] 实测）；表内无 (legacy, conference) 条目——
    # 遇到不该出现的组合同样响亮拒绝，而非静默返回 ''。
    with pytest.raises(CrawlerError) as exc:
        parse.infix_for_era_track("legacy", "conference")
    assert exc.value.error_class is ErrorClass.CONFIG


# --- pdf_url / supplemental_url（-Abstract→-Paper/-Supplemental、/hash/→/file/、.html→.pdf）----


@pytest.mark.parametrize(
    ("year", "infix", "expected"),
    [
        (
            2023,
            "-Conference",
            "https://proceedings.neurips.cc/paper_files/paper/2023/file/"
            "0001ca33ba34ce0351e4612b744b3936-Paper-Conference.pdf",
        ),
        (
            2023,
            "-Datasets_and_Benchmarks",
            "https://proceedings.neurips.cc/paper_files/paper/2023/file/"
            "00ba06ba5c324efdfb068865ca44cf0b-Paper-Datasets_and_Benchmarks.pdf",
        ),
        (
            1987,
            "",
            "https://proceedings.neurips.cc/paper_files/paper/1987/file/"
            "03004620ea802b9118dd44d69f07af56-Paper.pdf",
        ),
    ],
)
def test_pdf_url_matches_live_verified_samples(year: int, infix: str, expected: str) -> None:
    hash_ = expected.rsplit("/", 1)[-1].split("-Paper")[0]
    url = parse.pdf_url("https://proceedings.neurips.cc", year=year, hash_=hash_, infix=infix)
    assert url == expected
    # 三处替换的属性性断言（design §5）：产物里不应残留旧路径段/旧后缀/旧扩展名。
    assert "/hash/" not in url
    assert "-Abstract" not in url
    assert url.endswith(".pdf")
    assert "/file/" in url


def test_supplemental_url_uses_pdf_extension_not_zip() -> None:
    # [LIVE] §5 证伪旧稿的 .zip 假设：Supplemental 实测一律 .pdf。
    url = parse.supplemental_url(
        "https://proceedings.neurips.cc",
        year=2021,
        hash_="000c076c390a4c357313fca29e390ece",
        infix="",
    )
    assert url == (
        "https://proceedings.neurips.cc/paper_files/paper/2021/file/"
        "000c076c390a4c357313fca29e390ece-Supplemental.pdf"
    )
    assert url.endswith(".pdf")
    assert not url.endswith(".zip")


# --- validate_hash / HASH_RE（32-hex 形态断言，非法拒绝）----------------------------------------


@pytest.mark.parametrize(
    "value",
    [
        "0001ca33ba34ce0351e4612b744b3936",
        "000c076c390a4c357313fca29e390ece",
        "00000000000000000000000000000000"[:32],
    ],
)
def test_validate_hash_accepts_well_formed_lowercase_32_hex(value: str) -> None:
    assert parse.validate_hash(value) == value
    assert parse.HASH_RE.match(value)


@pytest.mark.parametrize(
    "value",
    [
        "",
        "0001CA33BA34CE0351E4612B744B3936",  # 大写——站点恒小写，不做归一，拒绝
        "0001ca33ba34ce0351e4612b744b393",  # 31 位，短一位
        "0001ca33ba34ce0351e4612b744b39366",  # 33 位，长一位
        "0001ca33ba34ce0351e4612b744b393g",  # 非法字符 g（且仍是 32 位长度）
        "not-a-hash-at-all",
    ],
)
def test_validate_hash_rejects_malformed_values(value: str) -> None:
    with pytest.raises(CrawlerError) as exc:
        parse.validate_hash(value)
    assert exc.value.error_class is ErrorClass.CONFIG


# --- parse_year_page：真实 legacy/modern 样本 ---------------------------------------------------


def test_parse_year_page_legacy_1987_real_sample() -> None:
    papers = parse.parse_year_page(_page(_LEGACY_1987_LI))
    assert len(papers) == 1
    paper = papers[0]
    assert paper.hash == "03004620ea802b9118dd44d69f07af56"
    assert paper.title == "Synchronization in Neural Nets"
    assert paper.authors == ("Jacques J. Vidal", "John Haggerty")
    assert paper.track == "none"
    assert paper.asset_suffix == ""


def test_parse_year_page_modern_2023_mixed_tracks_real_samples() -> None:
    papers = parse.parse_year_page(_page(_MODERN_2023_CONFERENCE_LI, _MODERN_2023_DB_LI))
    assert len(papers) == 2

    conference = papers[0]
    assert conference.hash == "0001ca33ba34ce0351e4612b744b3936"
    assert conference.title == (
        "Modelling Cellular Perturbations with the Sparse Additive Mechanism Shift "
        "Variational Autoencoder"
    )
    assert conference.authors == ("Michael Bereket", "Theofanis Karaletsos")
    assert conference.track == "conference"
    assert conference.asset_suffix == "-Conference"

    db = papers[1]
    assert db.hash == "00ba06ba5c324efdfb068865ca44cf0b"
    assert db.title == "Gigastep - One Billion Steps per Second Multi-agent Reinforcement Learning"
    assert db.authors == ("Mathias Lechner", "lianhao yin")
    assert db.track == "datasets_and_benchmarks"
    assert db.asset_suffix == "-Datasets_and_Benchmarks"


def test_parse_year_page_mixed_legacy_and_modern_in_one_call_still_extracts_both() -> None:
    # 纯解析层不关心跨年一致性（那是 adapter/健康检查层的事）；用来断言两种 li 形态
    # 可在同一次调用里被正确逐条解析，互不干扰。
    papers = parse.parse_year_page(_page(_LEGACY_1987_LI, _MODERN_2023_CONFERENCE_LI))
    assert [p.track for p in papers] == ["none", "conference"]
    assert [p.asset_suffix for p in papers] == ["", "-Conference"]


# --- parse_year_page：错误路径 -------------------------------------------------------------------


def test_parse_year_page_zero_entries_is_parse_error() -> None:
    with pytest.raises(CrawlerError) as exc:
        parse.parse_year_page(b"<html><body><div>totally different layout</div></body></html>")
    assert exc.value.error_class is ErrorClass.PARSE


def test_parse_year_page_li_without_title_link_is_parse_error() -> None:
    broken = (
        '<li class="" data-track="none"><div class="paper-content">'
        '<span class="paper-authors">Nobody</span></div></li>'
    )
    with pytest.raises(CrawlerError) as exc:
        parse.parse_year_page(_page(broken))
    assert exc.value.error_class is ErrorClass.PARSE


def test_parse_year_page_href_with_malformed_hash_is_parse_error() -> None:
    broken = (
        '<li class="" data-track="none"><div class="paper-content">'
        '<a title="paper title" href="/paper_files/paper/1987/hash/'
        'NOT-A-VALID-HASH-Abstract.html">Some Title</a>'
        '<span class="paper-authors">A. Author</span></div></li>'
    )
    with pytest.raises(CrawlerError) as exc:
        parse.parse_year_page(_page(broken))
    assert exc.value.error_class is ErrorClass.PARSE


def test_parse_year_page_whitespace_only_title_text_is_parse_error() -> None:
    # 链接存在，但文字内容全是空白——规整化后为空串，与"整个链接缺失"是不同的漂移
    # 信号，但同样判 parse（标题是核心身份字段，不能容忍空）。
    blank_title = (
        '<li class="" data-track="none"><div class="paper-content">'
        '<a title="paper title" href="/paper_files/paper/1987/hash/'
        '03004620ea802b9118dd44d69f07af56-Abstract.html">   </a>'
        '<span class="paper-authors">A. Author</span></div></li>'
    )
    with pytest.raises(CrawlerError) as exc:
        parse.parse_year_page(_page(blank_title))
    assert exc.value.error_class is ErrorClass.PARSE


def test_parse_year_page_missing_authors_span_is_tolerated_as_empty_tuple() -> None:
    # 作者字段比标题/hash 更"软"——缺失时容忍为空 tuple（pmlr 同款先例），不是错误。
    no_authors = (
        '<li class="" data-track="none"><div class="paper-content">'
        '<a title="paper title" href="/paper_files/paper/1987/hash/'
        '03004620ea802b9118dd44d69f07af56-Abstract.html">Some Title</a>'
        "</div></li>"
    )
    papers = parse.parse_year_page(_page(no_authors))
    assert papers[0].authors == ()


def test_parse_year_page_whitespace_only_authors_span_is_tolerated_as_empty_tuple() -> None:
    # span 存在但内容全是空白（不同于"span 缺失"，规整化路径不同）——同样容忍为空 tuple。
    blank_authors = (
        '<li class="" data-track="none"><div class="paper-content">'
        '<a title="paper title" href="/paper_files/paper/1987/hash/'
        '03004620ea802b9118dd44d69f07af56-Abstract.html">Some Title</a>'
        '<span class="paper-authors">   </span></div></li>'
    )
    papers = parse.parse_year_page(_page(blank_authors))
    assert papers[0].authors == ()


# --- to_paper_stub：字段映射（design §3.2）-------------------------------------------------------


def test_to_paper_stub_field_mapping() -> None:
    paper = parse.parse_year_page(_page(_MODERN_2023_CONFERENCE_LI))[0]
    stub = parse.to_paper_stub(paper, year=2023)
    assert stub.identifiers == (("neurips", "0001ca33ba34ce0351e4612b744b3936"),)
    assert stub.year == 2023
    assert stub.abstract is None  # 年页无摘要，薄元数据（§8-★4）
    assert dict(stub.meta) == {"track": "conference", "asset_suffix": "-Conference"}


def test_to_paper_stub_legacy_asset_suffix_is_empty_string_not_missing_key() -> None:
    paper = parse.parse_year_page(_page(_LEGACY_1987_LI))[0]
    stub = parse.to_paper_stub(paper, year=1987)
    meta = dict(stub.meta)
    assert "asset_suffix" in meta
    assert meta["asset_suffix"] == ""
    assert meta["track"] == "none"


# --- parse_proceedings_list（首页届表；discover 不消费，T3 一致性回归用）-----------------------


def _homepage_li(*, year: int, label: str, brand: str) -> str:
    return (
        f'<li><a href="/paper_files/paper/{year}">{label}</a>'
        f'<span class="proceedings-meta">{brand} {year}</span></li>'
    )


_HOMEPAGE_SAMPLE = (
    "<ul class='proceedings-list'>"
    + _homepage_li(
        year=2025, label="Advances in Neural Information Processing Systems 38 ", brand="NeurIPS"
    )
    + _homepage_li(
        year=1988, label="Advances in Neural Information Processing Systems 1 ", brand="NIPS"
    )
    + _homepage_li(year=1987, label="Neural Information Processing Systems 0 ", brand="NIPS")
    + "</ul>"
)


def test_parse_proceedings_list_real_boundary_samples() -> None:
    # 三条边界样本逐字取自 [LIVE] site-survey §2（顺序即页面出现顺序：新→旧）。
    years = parse.parse_proceedings_list(_HOMEPAGE_SAMPLE.encode())
    assert years == (2025, 1988, 1987)


def test_parse_proceedings_list_zero_entries_is_parse_error() -> None:
    with pytest.raises(CrawlerError) as exc:
        parse.parse_proceedings_list(b"<html><body>no listing here</body></html>")
    assert exc.value.error_class is ErrorClass.PARSE
