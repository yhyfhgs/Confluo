"""ssrn/parse.py 单测（纯逻辑零网络；ssrn.md §4.2/§4.4/§7）。

覆盖：DOI→abstract_id 抽取正则矩阵（合法 / 非-ssrn 中缀护栏 / 大小写+doi.org 前缀归一）、
identifier 取值（doi/ssrn）、增补 (ssrn) id（幂等）、landing URL 构造、econ/fin 主题
近似过滤谓词（AC-5.1a② 确定性：固定输入→期望输出）。
"""

from __future__ import annotations

from paper_crawler.adapters.ssrn import parse
from paper_crawler.types import PaperStub


def _stub(*identifiers: tuple[str, str], meta: tuple[tuple[str, str], ...] = ()) -> PaperStub:
    return PaperStub(title="T", identifiers=identifiers or (("doi", "10.2139/ssrn.1"),), meta=meta)


# --- DOI→abstract_id 抽取正则矩阵（§7 T1①）------------------------------------------------


def test_abstract_id_valid_ssrn_doi() -> None:
    assert parse.abstract_id_from_doi("10.2139/ssrn.4056799") == "4056799"


def test_abstract_id_uppercase_and_doiorg_prefix_normalized() -> None:
    """大小写 + doi.org 前缀经 normalize_doi 归一后匹配（§7 大小写/前缀矩阵）。"""
    assert parse.abstract_id_from_doi("https://doi.org/10.2139/SSRN.4056799") == "4056799"
    assert parse.abstract_id_from_doi("10.2139/SSRN.7654321") == "7654321"


def test_abstract_id_non_ssrn_infix_under_prefix_returns_none() -> None:
    """前缀 10.2139 下**非 `ssrn.` 中缀** DOI（潜在非-SSRN）→ None（护栏信号，§4.2）。"""
    assert parse.abstract_id_from_doi("10.2139/dpr.v3.2019.0042") is None


def test_abstract_id_wrong_prefix_returns_none() -> None:
    """非 10.2139 前缀（如 nber 10.3386）→ None（不误纳）。"""
    assert parse.abstract_id_from_doi("10.3386/w30000") is None


def test_abstract_id_non_numeric_suffix_returns_none() -> None:
    """`ssrn.` 后非纯数字 → None（下载主键须十进制 abstract_id）。"""
    assert parse.abstract_id_from_doi("10.2139/ssrn.abc") is None


def test_abstract_id_empty_string_returns_none() -> None:
    assert parse.abstract_id_from_doi("") is None


# --- identifier 取值 -------------------------------------------------------------------------


def test_doi_of_stub_present_and_absent() -> None:
    assert parse.doi_of_stub(_stub(("doi", "10.2139/ssrn.1"))) == "10.2139/ssrn.1"
    assert parse.doi_of_stub(_stub(("ssrn", "1"))) is None


def test_ssrn_id_of_stub_present_and_absent() -> None:
    assert parse.ssrn_id_of_stub(_stub(("doi", "10.2139/ssrn.1"), ("ssrn", "1"))) == "1"
    assert parse.ssrn_id_of_stub(_stub(("doi", "10.2139/ssrn.1"))) is None


# --- 增补 (ssrn) identifier（DOI 锚点保留 + 幂等）------------------------------------------


def test_augment_adds_ssrn_id_preserving_doi_anchor() -> None:
    stub = _stub(("doi", "10.2139/ssrn.4056799"))
    out = parse.augment_with_ssrn_id(stub, "4056799")
    assert out.identifiers == (("doi", "10.2139/ssrn.4056799"), ("ssrn", "4056799"))


def test_augment_is_idempotent() -> None:
    stub = _stub(("doi", "10.2139/ssrn.1"), ("ssrn", "1"))
    assert parse.augment_with_ssrn_id(stub, "1") is stub  # 已含 → 原样返回


# --- landing URL 构造（纯串，零网络）--------------------------------------------------------


def test_landing_url_shape() -> None:
    assert (
        parse.landing_url("4056799")
        == "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4056799"
    )


# --- econ/fin 主题近似过滤谓词（AC-5.1a② 确定性）-------------------------------------------


def test_topic_field_matches_in_allowed() -> None:
    assert parse.topic_field_matches("Economics, Econometrics and Finance") is True
    assert parse.topic_field_matches("Business, Management and Accounting") is True


def test_topic_field_matches_not_in_allowed() -> None:
    assert parse.topic_field_matches("Medicine") is False
    assert parse.topic_field_matches("Engineering") is False


def test_topic_field_matches_none_excluded() -> None:
    """None（未 enrich）→ False：近似过滤诚实排除不可确认者（opt-in 收窄语义）。"""
    assert parse.topic_field_matches(None) is False


def test_topic_field_matches_custom_allowed_set() -> None:
    assert parse.topic_field_matches("Law", allowed=frozenset({"Law"})) is True


def test_stub_topic_field_present_and_absent() -> None:
    with_field = _stub(("ssrn", "1"), meta=(("openalex_field", "Medicine"),))
    assert parse.stub_topic_field(with_field) == "Medicine"
    assert parse.stub_topic_field(_stub(("ssrn", "1"))) is None


def test_filter_stubs_by_topic_deterministic() -> None:
    """AC-5.1a② 判据：固定输入集 → 期望过滤输出精确断言（保序，近似过滤如实排除非-econ/fin）。"""
    econ = _stub(("ssrn", "1"), meta=(("openalex_field", "Economics, Econometrics and Finance"),))
    biz = _stub(("ssrn", "2"), meta=(("openalex_field", "Business, Management and Accounting"),))
    med = _stub(("ssrn", "3"), meta=(("openalex_field", "Medicine"),))
    eng = _stub(("ssrn", "4"), meta=(("openalex_field", "Engineering"),))
    unenriched = _stub(("ssrn", "5"))  # 无 openalex_field → 排除

    kept = parse.filter_stubs_by_topic([econ, biz, med, eng, unenriched])

    assert [parse.ssrn_id_of_stub(s) for s in kept] == ["1", "2"]  # 仅 econ/fin，保序
