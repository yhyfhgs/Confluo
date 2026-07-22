"""top-level `paper_crawler.ids.normalize_doi` 单测（plan §2-1 冻结语义）。

本分支自建的最小 DOI 归一版（T1 merge-engine 分支为权威版）——覆盖：小写化、
`https?://(dx.)doi.org/` 与 `doi:` 前缀剥离、首尾空白清理、边界（空串/无前缀）。
"""

import pytest

from paper_crawler.ids import normalize_doi


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # 大小写归一（DOI 大小写不敏感，统一小写作强合并锚点）
        ("10.1257/AER.20221079", "10.1257/aer.20221079"),
        # https://doi.org/ 前缀剥离 + 小写
        ("https://doi.org/10.1093/QJE/QJAE001", "10.1093/qje/qjae001"),
        # http:// 变体
        ("http://doi.org/10.1038/NATURE14539", "10.1038/nature14539"),
        # dx.doi.org 变体
        ("https://dx.doi.org/10.1016/J.JFINECO.2023.01.001", "10.1016/j.jfineco.2023.01.001"),
        # doi: scheme 前缀
        ("doi:10.1234/ABC", "10.1234/abc"),
        ("DOI:10.1234/ABC", "10.1234/abc"),
        # 首尾空白清理
        ("  10.1234/xyz  ", "10.1234/xyz"),
        ("\thttps://doi.org/10.1234/XyZ\n", "10.1234/xyz"),
        # 无前缀裸 DOI 原样（仅小写）
        ("10.1234/plain", "10.1234/plain"),
        # 空串边界（调用方判"无 DOI"，本函数不抛）
        ("", ""),
        ("   ", ""),
    ],
)
def test_normalize_doi(raw: str, expected: str) -> None:
    assert normalize_doi(raw) == expected


def test_normalize_doi_only_strips_leading_prefix_not_embedded() -> None:
    # 前缀锚定行首（^）——串中间出现的 'doi:' 文本不被误剥。
    assert normalize_doi("10.1234/contains-doi:-inside") == "10.1234/contains-doi:-inside"
