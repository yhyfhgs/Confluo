"""aea DOI 双形态容错解析器 + code→venue 路由表单测（design/adapters/aea.md §3.2/§8）。

零网络纯函数层，密集覆盖（DoD"解析器 ≥90%"）：① 双形态解析（submission/
vol_issue_page/pnp）；② code→venue 全 8 刊路由断言；③ 未知 code 容错（不路由、
不崩，WARN 由 adapter.py 上层负责——本文件只断言 `venue_id is None`，WARN 观测的
断言见 `test_aea_adapter.py`）；④ 畸形/边界输入零崩溃。四组真实 DOI 取自
`docs/research/site-survey/aea.md` [LIVE] 2026-07-24 实测记录（附录请求清单）。
"""

from __future__ import annotations

import pytest

from paper_crawler.adapters.aea.parse import CODE_TO_VENUE, ParsedAeaDoi, parse_doi

# --- 真实站点勘察实证的 DOI 样本（site-survey §2/§4/§5，[LIVE] 2026-07-24）------------------


def test_real_aer_submission_doi_is_submission_form() -> None:
    """`10.1257/aer.20230344`：近期研究文，site-survey §3 单条字段实测样本。"""
    parsed = parse_doi("10.1257/aer.20230344")
    assert parsed == ParsedAeaDoi(
        code="aer",
        suffix="20230344",
        doi_form="submission",
        venue_id="aer",
        raw="10.1257/aer.20230344",
    )


def test_real_aer_vol_issue_page_doi_is_vol_issue_page_form() -> None:
    """`10.1257/aer.106.6.i`：AER front matter，页为罗马数字 "i"（site-survey §5）。"""
    parsed = parse_doi("10.1257/aer.106.6.i")
    assert parsed is not None
    assert parsed.code == "aer"
    assert parsed.suffix == "106.6.i"
    assert parsed.doi_form == "vol_issue_page"
    assert parsed.venue_id == "aer"


def test_real_aer_pnp_doi_is_pnp_form_and_unrouted() -> None:
    """`10.1257/aer.p20151048`：AER P&P 短文（site-survey §5）——venue 暂缓（A-3）。"""
    parsed = parse_doi("10.1257/aer.p20151048")
    assert parsed is not None
    assert parsed.code == "aer"
    assert parsed.suffix == "p20151048"
    assert parsed.doi_form == "pnp"
    assert parsed.venue_id is None


def test_real_jep_submission_doi_routes_to_jep() -> None:
    """`10.1257/jep.20251473`：JEP gold OA 样本（site-survey §4/§5）。"""
    parsed = parse_doi("10.1257/jep.20251473")
    assert parsed is not None
    assert parsed.code == "jep"
    assert parsed.doi_form == "submission"
    assert parsed.venue_id == "jep"


# --- 三种 doi_form 的合成边界样本（补 site-survey 未逐一覆盖的子刊/独立 pandp 形态）------


def test_subvenue_mac_submission_form_routes_to_aej_macro() -> None:
    """`mac.20180329`（site-survey §2 journals 表点名的子刊 code→示例 DOI）。"""
    parsed = parse_doi("10.1257/mac.20180329")
    assert parsed is not None
    assert parsed.code == "mac"
    assert parsed.suffix == "20180329"
    assert parsed.doi_form == "submission"
    assert parsed.venue_id == "aej_macro"


def test_independent_pandp_code_is_pnp_form_and_unrouted() -> None:
    """`pandp.116.742`（site-survey §2 附注的独立 P&P code，非 aer.p* 形态）。"""
    parsed = parse_doi("10.1257/pandp.116.742")
    assert parsed is not None
    assert parsed.code == "pandp"
    assert parsed.suffix == "116.742"
    assert parsed.doi_form == "pnp"
    assert parsed.venue_id is None


# --- code→venue 8 刊路由全断言（DoD"8 刊路由...断言全绿"）--------------------------------


@pytest.mark.parametrize(
    ("code", "expected_venue_id"),
    [
        ("aer", "aer"),
        ("aeri", "aeri"),
        ("mac", "aej_macro"),
        ("app", "aej_applied"),
        ("mic", "aej_micro"),
        ("pol", "aej_policy"),
        ("jel", "jel"),
        ("jep", "jep"),
    ],
)
def test_all_8_venues_route_correctly_from_submission_form_doi(
    code: str, expected_venue_id: str
) -> None:
    doi = f"10.1257/{code}.20200001"  # 统一用合法 8 位投稿号后缀，只变 code
    parsed = parse_doi(doi)
    assert parsed is not None
    assert parsed.doi_form == "submission"
    assert parsed.venue_id == expected_venue_id


def test_code_to_venue_table_has_exactly_8_entries() -> None:
    """路由表条目数 = 8 刊（不含故意排除的 pandp）——防静默漏收/多收子刊。"""
    assert len(CODE_TO_VENUE) == 8
    assert "pandp" not in CODE_TO_VENUE


def test_code_differs_from_venue_id_for_all_subvenue_codes() -> None:
    """§3.2 核心裁决"DOI 子前缀 code ≠ venue id"——AEJ 四系子刊逐一验证不等。"""
    for code in ("mac", "app", "mic", "pol"):
        assert CODE_TO_VENUE[code] != code


# --- 未知 code 容错（不路由、不崩，§3.2"防新子刊上线"）------------------------------------


def test_unknown_code_with_submission_suffix_does_not_route_but_does_not_crash() -> None:
    parsed = parse_doi("10.1257/xyz.20230344")
    assert parsed is not None
    assert parsed.code == "xyz"
    assert parsed.doi_form == "submission"
    assert parsed.venue_id is None


def test_unknown_code_with_vol_issue_page_suffix_does_not_route() -> None:
    parsed = parse_doi("10.1257/newjournal.50.2.100")
    assert parsed is not None
    assert parsed.doi_form == "vol_issue_page"
    assert parsed.venue_id is None


# --- 畸形/边界输入：任一形态不得抛错（§3.2 容错契约）---------------------------------------


def test_non_aea_prefix_returns_none() -> None:
    """非 `10.1257/` 前缀（如 elsevier 前缀 10.1016）→ None，非本 adapter 的 DOI。"""
    assert parse_doi("10.1016/j.jfineco.2011.03.021") is None


def test_completely_unrelated_string_returns_none() -> None:
    assert parse_doi("not-a-doi-at-all") is None


def test_empty_string_returns_none() -> None:
    assert parse_doi("") is None


def test_bare_code_without_suffix_does_not_crash() -> None:
    """`10.1257/aer`（无 code.suffix 分隔）——畸形但容错：整串作 code，suffix 空。"""
    parsed = parse_doi("10.1257/aer")
    assert parsed is not None
    assert parsed.code == "aer"
    assert parsed.suffix == ""
    assert parsed.doi_form == "unknown"
    assert parsed.venue_id == "aer"  # code 本身可识别，宽容路由


def test_prefix_only_with_nothing_after_does_not_crash() -> None:
    """`10.1257/`（前缀后空）——最极端畸形输入，仍不崩。"""
    parsed = parse_doi("10.1257/")
    assert parsed is not None
    assert parsed.code == ""
    assert parsed.suffix == ""
    assert parsed.doi_form == "unknown"
    assert parsed.venue_id is None


def test_suffix_with_no_digits_and_no_dot_is_unknown_form_but_still_routes() -> None:
    """suffix 非 8 位数字、不含点——`doi_form="unknown"`，但 code 路由仍照常进行
    （doi_form 与 venue_id 路由是两个独立维度，见模块 docstring）。
    """
    parsed = parse_doi("10.1257/aer.frontmatter")
    assert parsed is not None
    assert parsed.doi_form == "unknown"
    assert parsed.venue_id == "aer"


# --- 大小写与空白容错 ----------------------------------------------------------------------


def test_uppercase_code_is_normalized_to_lowercase_for_routing() -> None:
    parsed = parse_doi("10.1257/AER.20230344")
    assert parsed is not None
    assert parsed.code == "aer"  # 归一小写
    assert parsed.venue_id == "aer"
    assert parsed.raw == "10.1257/AER.20230344"  # raw 原样保留大小写


def test_surrounding_whitespace_is_stripped() -> None:
    parsed = parse_doi("  10.1257/aer.20230344  ")
    assert parsed is not None
    assert parsed.raw == "10.1257/aer.20230344"


def test_prefix_case_insensitive_match() -> None:
    """DOI 前缀比对本身也不区分大小写（防御性——Crossref 惯例全小写，此为容错扩展）。"""
    parsed = parse_doi("10.1257/aer.20230344".upper())
    assert parsed is not None
    assert parsed.venue_id == "aer"


# --- P&P 特判优先于普通 code 路由（核心裁决单测，§3.2/§7 A-3）----------------------------


def test_pnp_suffix_overrides_known_code_routing_even_though_code_is_in_table() -> None:
    """`aer.p20151048` 的 code=`aer` 本身在 `CODE_TO_VENUE` 表中，但 pnp 后缀形态
    优先判定为暂缓——不路由到 `aer`（区别于普通 `aer.{8位}` 会路由到 `aer`）。
    """
    submission = parse_doi("10.1257/aer.20230344")
    pnp = parse_doi("10.1257/aer.p20151048")
    assert submission is not None and submission.venue_id == "aer"
    assert pnp is not None and pnp.venue_id is None
    assert pnp.code == submission.code == "aer"  # 同一 code，路由结果因形态不同而不同


def test_pnp_suffix_pattern_requires_exactly_8_digits_after_p() -> None:
    """`p{8 位}` 精确匹配——非 8 位数字的 "p" 前缀后缀不误判为 pnp（回退按普通形态
    判定），防止过度宽泛匹配吞掉真实的 vol_issue_page 形态（如某卷号恰以 p 开头
    的假想边界，形态判定应保守）。
    """
    too_short = parse_doi("10.1257/aer.p123")
    assert too_short is not None
    assert too_short.doi_form != "pnp"  # 3 位数字，不匹配 p\d{8}
    assert too_short.venue_id == "aer"  # 未落 pnp 特判，按普通 code 路由


def test_pnp_form_applies_uniformly_to_any_code_not_only_aer() -> None:
    """pnp 形态判定不限定 code=='aer'——任何 code 命中 `p\\d{8}` 后缀均视为 pnp（解析
    器容错设计的一般化，见 parse.py 模块 docstring）。此为防御性健壮性，非已知真实
    数据模式。
    """
    parsed = parse_doi("10.1257/mac.p12345678")
    assert parsed is not None
    assert parsed.doi_form == "pnp"
    assert parsed.venue_id is None
