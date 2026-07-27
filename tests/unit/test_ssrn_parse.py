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


# --- landing → Delivery.cfm 抽取（模式 B 同批解析核；design/11 §4.4）------------------------

_LANDING = "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4056799"


def test_delivery_url_relative_href_is_absolutized() -> None:
    """相对 href 经 landing 的 `final_url` 绝对化（站点实际给的就是相对形态）。"""
    body = b"<a href='Delivery.cfm/SSRN_ID4056799_code1.pdf?abstractid=4056799&mirid=1'>PDF</a>"
    assert parse.delivery_url_from_landing(body, base_url=_LANDING) == (
        "https://papers.ssrn.com/sol3/Delivery.cfm/SSRN_ID4056799_code1.pdf"
        "?abstractid=4056799&mirid=1"
    )


def test_delivery_url_absolute_href_and_entity_unescaped() -> None:
    """绝对 href 原样采用；HTML 实体（`&amp;`）还原——否则 query 会被站点看成一个参数。"""
    body = (
        b'<a href="https://papers.ssrn.com/sol3/Delivery.cfm/x.pdf?abstractid=1&amp;mirid=1">x</a>'
    )
    assert parse.delivery_url_from_landing(body, base_url=_LANDING) == (
        "https://papers.ssrn.com/sol3/Delivery.cfm/x.pdf?abstractid=1&mirid=1"
    )


def test_delivery_url_is_case_insensitive_on_the_marker() -> None:
    body = b'<A HREF="delivery.CFM/x.pdf?abstractid=1">x</A>'
    result = parse.delivery_url_from_landing(body, base_url=_LANDING)
    assert result == "https://papers.ssrn.com/sol3/delivery.CFM/x.pdf?abstractid=1"


def test_delivery_url_absent_returns_none() -> None:
    """无下载链接 → None（调用方映射 `no_entitlement`；**不猜、不拼** URL，红线 4）。"""
    body = b"<html><h1>WP</h1><a href='/sol3/cf_dev/AbsByAuth.cfm?per_id=1'>author</a></html>"
    assert parse.delivery_url_from_landing(body, base_url=_LANDING) is None


def test_delivery_url_cross_host_href_is_rejected() -> None:
    """同源护栏：跨站 `Delivery.cfm` 链接一律不采（页面被改写/注入时不外送导航）。"""
    body = b"<a href='https://evil.example.test/Delivery.cfm/x.pdf?abstractid=1'>x</a>"
    assert parse.delivery_url_from_landing(body, base_url=_LANDING) is None


def test_delivery_url_scheme_downgrade_is_rejected() -> None:
    """**真同源**（R1 审查 P2-3）：scheme 降级 http 不采——明文跳转会外泄 cookie/token。"""
    body = b"<a href='http://papers.ssrn.com/sol3/Delivery.cfm/x.pdf?abstractid=1'>x</a>"
    assert parse.delivery_url_from_landing(body, base_url=_LANDING) is None


def test_delivery_url_odd_port_is_rejected() -> None:
    """同 host 异端口不是同源（`https://h:8443` ≠ `https://h`）。"""
    body = b"<a href='https://papers.ssrn.com:8443/sol3/Delivery.cfm/x.pdf?abstractid=1'>x</a>"
    assert parse.delivery_url_from_landing(body, base_url=_LANDING) is None


def test_delivery_url_with_userinfo_is_rejected() -> None:
    """带 userinfo 的 URL 一律不采：`https://evil:pass@papers.ssrn.com/…` 既是凭证形态，
    也是经典的 host 误读诱饵（不同解析器对 `@` 前后的归属不一致）。"""
    body = b"<a href='https://evil:pass@papers.ssrn.com/sol3/Delivery.cfm/x.pdf?abstractid=1'>x</a>"
    assert parse.delivery_url_from_landing(body, base_url=_LANDING) is None


def test_delivery_url_explicit_default_port_is_accepted() -> None:
    """显式 `:443` 与缺省等价（同源，采）。"""
    body = b"<a href='https://papers.ssrn.com:443/sol3/Delivery.cfm/x.pdf?abstractid=1'>x</a>"
    result = parse.delivery_url_from_landing(body, base_url=_LANDING)
    assert result == "https://papers.ssrn.com:443/sol3/Delivery.cfm/x.pdf?abstractid=1"


def test_delivery_url_ignores_non_href_attributes() -> None:
    """左边界（R1 审查 P2-4）：`data-href=`/`xlink:href=` 等以 href 收尾的属性名不当 href。"""
    body = (
        b"<div data-href='Delivery.cfm/decoy.pdf?abstractid=1'></div>"
        b"<use xlink:href='Delivery.cfm/decoy2.pdf?abstractid=1'/>"
    )
    assert parse.delivery_url_from_landing(body, base_url=_LANDING) is None


def test_delivery_url_still_matches_real_href_after_decoys() -> None:
    """诱饵属性不遮蔽其后的真 `href`（左边界护栏不得误杀正例）。"""
    body = (
        b"<div data-href='Delivery.cfm/decoy.pdf?abstractid=1'></div>"
        b"<a href='Delivery.cfm/real.pdf?abstractid=1'>PDF</a>"
    )
    result = parse.delivery_url_from_landing(body, base_url=_LANDING)
    assert result is not None and result.endswith("real.pdf?abstractid=1")


def test_delivery_url_takes_the_first_match() -> None:
    body = (
        b"<a href='Delivery.cfm/first.pdf?abstractid=1'>a</a>"
        b"<a href='Delivery.cfm/second.pdf?abstractid=1'>b</a>"
    )
    result = parse.delivery_url_from_landing(body, base_url=_LANDING)
    assert result is not None and result.endswith("first.pdf?abstractid=1")


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
