"""wiley/parse.py 单测（零网络纯函数；design/adapters/wiley.md §3/§6）。

覆盖：DOI 前缀路由（三前缀命中 + 归一鲁棒性 + 非 Wiley 拒绝）、TDM URL 构造（DOI 斜杠保留 +
不安全字符转义 + 归一）、`%PDF` 魔数轻校验。
"""

from __future__ import annotations

import pytest

from paper_crawler.adapters.wiley import parse

# --- is_wiley_doi -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "doi",
    [
        "10.1111/jofi.13123",  # Journal of Finance（学会刊 10.1111）
        "10.1002/anie.201915678",  # 商业刊 10.1002
        "10.3982/ECTA12345",  # Econometrica(ECMA) 10.3982
    ],
)
def test_is_wiley_doi_true_for_known_prefixes(doi: str) -> None:
    assert parse.is_wiley_doi(doi) is True


def test_is_wiley_doi_normalizes_url_and_case() -> None:
    """带 https://doi.org/ 前缀与大小写混写经 normalize_doi 归一后仍正确判定。"""
    assert parse.is_wiley_doi("https://doi.org/10.1111/JOFI.13123") is True
    assert parse.is_wiley_doi("doi:10.1002/Anie.201915678") is True
    assert parse.is_wiley_doi("  10.3982/ECTA12345  ") is True


@pytest.mark.parametrize(
    "doi",
    [
        "10.1016/j.jfineco.2020.01.001",  # Elsevier（JFE）——非 Wiley
        "10.1257/aer.20191823",  # AEA
        "10.1234/other",
        "",
        "not-a-doi",
    ],
)
def test_is_wiley_doi_false_for_non_wiley(doi: str) -> None:
    assert parse.is_wiley_doi(doi) is False


# --- tdm_article_url --------------------------------------------------------------------------


def test_tdm_article_url_builds_endpoint_and_keeps_doi_slash() -> None:
    url = parse.tdm_article_url("10.1111/jofi.13123")
    assert url == "https://api.wiley.com/onlinelibrary/tdm/v1/articles/10.1111/jofi.13123"


def test_tdm_article_url_normalizes_before_building() -> None:
    """带 doi.org 前缀/大小写的输入先归一（小写、剥前缀）再拼 URL。"""
    url = parse.tdm_article_url("https://doi.org/10.1002/ANIE.201915678")
    assert url == "https://api.wiley.com/onlinelibrary/tdm/v1/articles/10.1002/anie.201915678"


def test_tdm_article_url_escapes_unsafe_chars_but_not_slash() -> None:
    """DOI 内空格等不安全字符转义（%20），路径分隔 `/` 保留。"""
    url = parse.tdm_article_url("10.1111/x y")
    assert url == "https://api.wiley.com/onlinelibrary/tdm/v1/articles/10.1111/x%20y"


# --- looks_like_pdf ---------------------------------------------------------------------------


def test_looks_like_pdf_true_for_magic() -> None:
    assert parse.looks_like_pdf(b"%PDF-1.7\n...") is True


@pytest.mark.parametrize("data", [b"", b"<html>", b"not a pdf", b"PDF-1.7", b"\x89PNG"])
def test_looks_like_pdf_false_for_non_pdf(data: bytes) -> None:
    assert parse.looks_like_pdf(data) is False
