"""elsevier_sd/parse.py 单测（零网络；elsevier-sd.md §3/§5）。

覆盖：entitlement 判定（true/false/字符串布尔/list 多条目/@status/字段缺失→PARSE/结构缺失
→PARSE/畸形 JSON→PARSE）、error 封套观测（error-response/service-error/缺失/非 JSON→空、
绝不 raise）。fixture 回放 01/02（entitlement true/false）+ 03/04（429 error 封套）。
"""

from __future__ import annotations

import pytest

from helpers.elsevier_fixtures import body_bytes
from paper_crawler.adapters.elsevier_sd import parse
from paper_crawler.errors import CrawlerError, ErrorClass

_DOI = "10.1016/j.jfineco.2011.03.021"


# --- parse_entitlement：有权 / 无权 ------------------------------------------------------------


def test_entitlement_true_fixture() -> None:
    decision = parse.parse_entitlement(body_bytes("01_entitlement_true.http"), doi=_DOI)
    assert decision.entitled is True
    assert decision.status == "found"


def test_entitlement_false_fixture() -> None:
    decision = parse.parse_entitlement(body_bytes("02_entitlement_false.http"), doi=_DOI)
    assert decision.entitled is False
    assert decision.status == "found"


def test_entitlement_bool_true_minimal() -> None:
    data = b'{"entitlement-response":{"document-entitlement":{"entitled":true}}}'
    assert parse.parse_entitlement(data, doi=_DOI).entitled is True


def test_entitlement_string_true_coerced() -> None:
    """`entitled` 为字符串 "true"（部分响应形态）→ 归一为布尔真。"""
    data = b'{"entitlement-response":{"document-entitlement":{"entitled":"true"}}}'
    assert parse.parse_entitlement(data, doi=_DOI).entitled is True


def test_entitlement_string_false_coerced() -> None:
    data = b'{"entitlement-response":{"document-entitlement":{"entitled":"false"}}}'
    assert parse.parse_entitlement(data, doi=_DOI).entitled is False


def test_entitlement_at_entitled_key_variant() -> None:
    """XML→JSON 转换可能落 `@entitled` 键（属性形态）——`_first` 容忍。"""
    data = b'{"entitlement-response":{"document-entitlement":{"@entitled":"true"}}}'
    assert parse.parse_entitlement(data, doi=_DOI).entitled is True


def test_entitlement_list_any_true() -> None:
    """document-entitlement 为 list（多文档查询）：任一条目有权 → 判有权。"""
    data = (
        b'{"entitlement-response":{"document-entitlement":[{"entitled":false},{"entitled":true}]}}'
    )
    assert parse.parse_entitlement(data, doi=_DOI).entitled is True


def test_entitlement_list_all_false() -> None:
    data = (
        b'{"entitlement-response":{"document-entitlement":[{"entitled":false},{"entitled":false}]}}'
    )
    assert parse.parse_entitlement(data, doi=_DOI).entitled is False


def test_entitlement_status_from_at_status() -> None:
    data = b'{"entitlement-response":{"document-entitlement":{"@status":"found","entitled":true}}}'
    assert parse.parse_entitlement(data, doi=_DOI).status == "found"


def test_entitlement_list_status_from_first_entry_only() -> None:
    """list 首条带 @status → status 定；次条 status 已非 None（不覆写，取首个非空）。"""
    data = (
        b'{"entitlement-response":{"document-entitlement":['
        b'{"@status":"found","entitled":false},{"@status":"ignored","entitled":true}]}}'
    )
    decision = parse.parse_entitlement(data, doi=_DOI)
    assert decision.entitled is True
    assert decision.status == "found"


def test_entitlement_unrecognized_string_value_raises_parse() -> None:
    """`entitled` 为不可判字符串（非 true/false 形态）→ 归一 None → 无有效字段 → PARSE。"""
    data = b'{"entitlement-response":{"document-entitlement":{"entitled":"maybe"}}}'
    with pytest.raises(CrawlerError) as exc:
        parse.parse_entitlement(data, doi=_DOI)
    assert exc.value.error_class is ErrorClass.PARSE


# --- parse_entitlement：结构/字段异常 → PARSE -------------------------------------------------


def test_entitlement_missing_entitled_field_raises_parse() -> None:
    """字段名假设失效（无 entitled 字段）→ 响亮 PARSE（不静默判 no_entitlement）。"""
    data = b'{"entitlement-response":{"document-entitlement":{"@status":"found"}}}'
    with pytest.raises(CrawlerError) as exc:
        parse.parse_entitlement(data, doi=_DOI)
    assert exc.value.error_class is ErrorClass.PARSE
    assert "entitled" in str(exc.value)


def test_entitlement_missing_response_wrapper_raises_parse() -> None:
    with pytest.raises(CrawlerError) as exc:
        parse.parse_entitlement(b'{"something-else":{}}', doi=_DOI)
    assert exc.value.error_class is ErrorClass.PARSE
    assert "entitlement-response" in str(exc.value)


def test_entitlement_missing_document_entitlement_raises_parse() -> None:
    with pytest.raises(CrawlerError) as exc:
        parse.parse_entitlement(b'{"entitlement-response":{}}', doi=_DOI)
    assert exc.value.error_class is ErrorClass.PARSE
    assert "document-entitlement" in str(exc.value)


def test_entitlement_top_level_not_object_raises_parse() -> None:
    with pytest.raises(CrawlerError) as exc:
        parse.parse_entitlement(b"[1,2,3]", doi=_DOI)
    assert exc.value.error_class is ErrorClass.PARSE


def test_entitlement_malformed_json_raises_parse() -> None:
    with pytest.raises(CrawlerError) as exc:
        parse.parse_entitlement(b"{not json", doi=_DOI)
    assert exc.value.error_class is ErrorClass.PARSE
    assert "malformed" in str(exc.value)


def test_entitlement_non_dict_list_entries_ignored() -> None:
    """list 内混入非对象条目（防御）→ 跳过；仅对象条目的 entitled 计入。"""
    data = b'{"entitlement-response":{"document-entitlement":["oops",{"entitled":true}]}}'
    assert parse.parse_entitlement(data, doi=_DOI).entitled is True


# --- parse_error_envelope：观测（绝不 raise）-------------------------------------------------


def test_error_envelope_keyless_429_fixture() -> None:
    env = parse.parse_error_envelope(body_bytes("03_keyless_429_rate_limit_exceeded.http"))
    assert env.code == "RATE_LIMIT_EXCEEDED"
    assert env.message and "Rate of requests" in env.message


def test_error_envelope_quota_429_fixture() -> None:
    env = parse.parse_error_envelope(body_bytes("04_quota_429_exceeded.http"))
    assert env.code == "QUOTA_EXCEEDED"


def test_error_envelope_service_error_shell() -> None:
    data = b'{"service-error":{"error-code":"AUTHENTICATION_ERROR","error-message":"bad key"}}'
    env = parse.parse_error_envelope(data)
    assert env.code == "AUTHENTICATION_ERROR"
    assert env.message == "bad key"


def test_error_envelope_malformed_returns_empty_never_raises() -> None:
    env = parse.parse_error_envelope(b"{not json")
    assert env.code is None
    assert env.message is None


def test_error_envelope_non_dict_returns_empty() -> None:
    assert parse.parse_error_envelope(b"[]").code is None


def test_error_envelope_unknown_shell_returns_empty() -> None:
    assert parse.parse_error_envelope(b'{"whatever":123}').code is None
