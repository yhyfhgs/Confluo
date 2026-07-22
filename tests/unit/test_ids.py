"""`paper_crawler.ids.normalize_doi` 单测（plan §2-1 冻结语义边界矩阵）。

本模块是 T4（dblp adapter）先行落地的最小版（见 `ids.py` 模块 docstring：T1
merge-engine 分支为权威版）；测试只锁定 plan §2-1 明文的行为——小写化 + 剥
`https://doi.org/`（含 `dx.doi.org`、协议大小写）与 `doi:` 前缀。
"""

from paper_crawler.ids import normalize_doi


def test_bare_doi_is_only_lowercased() -> None:
    assert normalize_doi("10.1145/3442188.3445922") == "10.1145/3442188.3445922"


def test_uppercase_doi_is_lowercased() -> None:
    assert normalize_doi("10.1145/ABCDEF") == "10.1145/abcdef"


def test_strips_https_doi_org_prefix() -> None:
    assert normalize_doi("https://doi.org/10.1145/3442188.3445922") == "10.1145/3442188.3445922"


def test_strips_http_doi_org_prefix() -> None:
    assert normalize_doi("http://doi.org/10.1145/3442188.3445922") == "10.1145/3442188.3445922"


def test_strips_dx_doi_org_prefix() -> None:
    assert normalize_doi("https://dx.doi.org/10.1007/978-3-030-99999-9") == (
        "10.1007/978-3-030-99999-9"
    )


def test_url_prefix_is_case_insensitive() -> None:
    assert normalize_doi("HTTPS://DOI.ORG/10.1145/Mixed.Case") == "10.1145/mixed.case"


def test_strips_doi_scheme_prefix() -> None:
    assert normalize_doi("doi:10.1145/3442188.3445922") == "10.1145/3442188.3445922"


def test_doi_scheme_prefix_is_case_insensitive_and_tolerates_space() -> None:
    assert normalize_doi("DOI: 10.1145/3442188.3445922") == "10.1145/3442188.3445922"


def test_strips_surrounding_whitespace() -> None:
    assert normalize_doi("  10.1145/3442188.3445922  ") == "10.1145/3442188.3445922"


def test_combines_url_prefix_and_lowercasing() -> None:
    assert normalize_doi("https://doi.org/10.1007/978-3-030-99999-9_1") == (
        "10.1007/978-3-030-99999-9_1"
    )


def test_is_idempotent() -> None:
    once = normalize_doi("https://doi.org/10.1145/ABCDEF")
    assert normalize_doi(once) == once
