"""`paper_crawler.ids` 纯函数单测（Phase 3 T1；plan §2-1）。

穷举边界：大小写混合 DOI / 带 URL 前缀 / `doi:` scheme / Unicode 标题 / LaTeX `\'{e}`
类宏 / 连字符标点 / 空白折叠 / 空串。
"""

from __future__ import annotations

import pytest

from paper_crawler.ids import normalize_doi, normalize_title

# -- normalize_doi -----------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # 大小写混合 → 小写化
        ("10.1016/J.JFINECO.2020.01.001", "10.1016/j.jfineco.2020.01.001"),
        ("10.1257/AER.20191823", "10.1257/aer.20191823"),
        # https://doi.org/ 前缀（含大小写协议）
        ("https://doi.org/10.1016/j.X", "10.1016/j.x"),
        ("HTTPS://DOI.ORG/10.1/A", "10.1/a"),
        # dx.doi.org 变体 + http
        ("http://dx.doi.org/10.1/A", "10.1/a"),
        ("https://dx.doi.org/10.1/B", "10.1/b"),
        # doi: scheme 前缀（大小写）
        ("doi:10.1/B", "10.1/b"),
        ("DOI:10.1/C", "10.1/c"),
        # 首尾空白清理
        ("  10.1/D  ", "10.1/d"),
        ("\t10.1/E\n", "10.1/e"),
        # 前缀 + 空白组合
        ("  https://doi.org/10.1/F  ", "10.1/f"),
        # 空串 → 空串（归一而非校验）
        ("", ""),
    ],
)
def test_normalize_doi(raw: str, expected: str) -> None:
    assert normalize_doi(raw) == expected


def test_normalize_doi_is_idempotent() -> None:
    once = normalize_doi("HTTPS://DOI.ORG/10.1016/J.X")
    assert normalize_doi(once) == once


def test_normalize_doi_non_doi_returned_normalized_not_raised() -> None:
    """非 DOI 形态：原样归一返回（小写/剥前缀/trim），不抛异常（设计权衡）。"""
    assert normalize_doi("  Not-A-DOI  ") == "not-a-doi"
    assert normalize_doi("arXiv:2401.12345") == "arxiv:2401.12345"


def test_normalize_doi_only_strips_leading_prefix() -> None:
    """前缀只在开头剥；DOI 体内偶含 'doi.org' 子串不受影响。"""
    assert normalize_doi("10.1/contains/doi.org/inside") == "10.1/contains/doi.org/inside"


# -- normalize_title ---------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # 大小写折叠 + 去标点 + 空白折叠
        ("The Q-Theory: A Review!", "the q theory a review"),
        ("  Multiple   Spaces  Here ", "multiple spaces here"),
        # 连字符视作分隔 → 空格
        ("State-of-the-Art Methods", "state of the art methods"),
        # 空串 / 纯标点
        ("", ""),
        ("!!! ??? ...", ""),
        # 数字保留
        ("GPT-4 Technical Report", "gpt 4 technical report"),
    ],
)
def test_normalize_title_basic(raw: str, expected: str) -> None:
    assert normalize_title(raw) == expected


def test_normalize_title_unicode_accents_fold() -> None:
    """Unicode 重音（NFKD 可分解）折叠到基字母。"""
    assert normalize_title("Café Société") == "cafe societe"
    assert normalize_title("Erdős number") == "erdos number"
    assert normalize_title("Señor") == "senor"


def test_normalize_title_latex_accent_macros() -> None:
    """LaTeX 重音宏剥离——各形折叠到同一键。"""
    assert normalize_title(r"\'{E}tude") == "etude"
    assert normalize_title(r"\'Etude") == "etude"
    assert normalize_title(r"Erd\H{o}s number") == "erdos number"
    assert normalize_title(r"Fran\c{c}ois") == "francois"
    assert normalize_title(r"\~namES") == "names"


def test_normalize_title_latex_and_unicode_and_plain_collapse_equal() -> None:
    """同一标题的 LaTeX 形、Unicode 形、去重音形归一后相等（弱信号匹配的核心目的）。"""
    latex = normalize_title(r"Erd\H{o}s--R\'enyi Random Graphs")
    unicode_form = normalize_title("Erdős–Rényi Random Graphs")
    plain = normalize_title("Erdos-Renyi Random Graphs")
    assert latex == unicode_form == plain == "erdos renyi random graphs"


def test_normalize_title_generic_latex_command_stripped_keeps_argument() -> None:
    """通用 LaTeX 命令（\\emph 等）剥命令保留花括号内容。"""
    assert normalize_title(r"An \emph{Important} Result") == "an important result"
    assert normalize_title(r"\textbf{Bold} Claim") == "bold claim"


def test_normalize_title_standalone_letter_macro() -> None:
    """独立字母宏 \\o→o、\\ss→ss；\\lambda 不被误切成 \\l。"""
    assert normalize_title(r"K\o benhavn") == "ko benhavn"
    assert normalize_title(r"Wei\ss ") == "weiss"
    assert normalize_title(r"The \lambda Calculus") == "the calculus"


def test_normalize_title_cjk_preserved() -> None:
    """CJK 标题：去标点/空白折叠但保留表意字符（Unicode \\w）。"""
    assert normalize_title("深度学习：综述") == "深度学习 综述"


def test_normalize_title_is_idempotent() -> None:
    once = normalize_title(r"Café \emph{Q}-Theory!")
    assert normalize_title(once) == once
