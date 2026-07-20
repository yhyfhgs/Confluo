"""errors.py（§2.1）单测：九类枚举、异常层级、重试表语义。"""

import pytest

from paper_crawler.errors import (
    RETRY_TABLE,
    CapabilityNotSupported,
    CrawlerError,
    ErrorClass,
    IllegalTransition,
    RetrySpec,
)

EXPECTED_ERROR_VALUES = {
    "transient",
    "rate_limited",
    "auth_expired",
    "no_entitlement",
    "challenge",
    "gone",
    "parse",
    "integrity",
    "config",
}


def test_error_class_has_exactly_nine_documented_values() -> None:
    assert {ec.value for ec in ErrorClass} == EXPECTED_ERROR_VALUES
    assert len(list(ErrorClass)) == 9


def test_error_class_is_str_enum() -> None:
    # StrEnum：成员与其字符串值相等，可直接作为文本使用（写入 DB error_class 列）。
    assert ErrorClass.TRANSIENT == "transient"
    assert f"{ErrorClass.PARSE}" == "parse"


def test_crawler_error_carries_class_and_detail() -> None:
    err = CrawlerError(ErrorClass.PARSE, "0 hits", detail="selector foo")
    assert err.error_class is ErrorClass.PARSE
    assert err.detail == "selector foo"
    assert "0 hits" in str(err)


def test_crawler_error_detail_defaults_empty() -> None:
    err = CrawlerError(ErrorClass.GONE, "404")
    assert err.detail == ""


def test_capability_not_supported_is_config_class() -> None:
    err = CapabilityNotSupported("adapter x lacks DISCOVER")
    assert isinstance(err, CrawlerError)
    assert err.error_class is ErrorClass.CONFIG
    assert "DISCOVER" in str(err)


def test_capability_not_supported_has_default_message() -> None:
    err = CapabilityNotSupported()
    assert err.error_class is ErrorClass.CONFIG
    assert str(err)  # 非空默认文案


def test_illegal_transition_is_plain_exception_not_crawler_error() -> None:
    assert issubclass(IllegalTransition, Exception)
    assert not issubclass(IllegalTransition, CrawlerError)
    with pytest.raises(IllegalTransition):
        raise IllegalTransition("DONE->RUNNING")


def test_retry_table_transient_and_rate_limited() -> None:
    assert RETRY_TABLE[ErrorClass.TRANSIENT] == RetrySpec(4, (2.0, 8.0, 30.0))
    assert RETRY_TABLE[ErrorClass.RATE_LIMITED] == RetrySpec(4, (2.0, 8.0, 30.0))


def test_retry_table_integrity_redownloads_once() -> None:
    spec = RETRY_TABLE[ErrorClass.INTEGRITY]
    assert spec.max_attempts == 2
    assert spec.backoff_seconds == (0.0,)


@pytest.mark.parametrize(
    "error_class",
    [
        ErrorClass.AUTH_EXPIRED,
        ErrorClass.NO_ENTITLEMENT,
        ErrorClass.CHALLENGE,
        ErrorClass.GONE,
        ErrorClass.PARSE,
        ErrorClass.CONFIG,
    ],
)
def test_retry_table_omits_non_retryable_classes(error_class: ErrorClass) -> None:
    # 未列出 → 消费方用 .get 兜底为 RetrySpec(1)（不重试）。
    assert error_class not in RETRY_TABLE
    assert RETRY_TABLE.get(error_class, RetrySpec(1)).max_attempts == 1


def test_retry_spec_default_backoff_is_empty() -> None:
    assert RetrySpec(1).backoff_seconds == ()


def test_retry_spec_is_frozen() -> None:
    spec = RetrySpec(4, (2.0,))
    with pytest.raises(AttributeError):
        spec.max_attempts = 9  # type: ignore[misc]
