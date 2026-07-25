"""errors.py（§2.1）单测：九类枚举、异常层级、重试表语义。"""

import pytest

from paper_crawler.errors import (
    RETRY_TABLE,
    AuthRequired,
    CapabilityNotSupported,
    Challenged,
    CrawlerError,
    ErrorClass,
    IllegalTransition,
    RetrySpec,
    SubscriptionInvalid,
    WatermarkInvalid,
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


# -- status_code（纯附加，auth-framework §6 / 检查单 #4）----------------------------------


def test_crawler_error_status_code_defaults_none() -> None:
    """既有全部构造点不传 status_code → None（非 HTTP 来源天然 None，不误命中 `== <int>`）。"""
    err = CrawlerError(ErrorClass.PARSE, "0 hits")
    assert err.status_code is None


def test_crawler_error_carries_status_code_when_given() -> None:
    err = CrawlerError(ErrorClass.NO_ENTITLEMENT, "HTTP 403", status_code=403)
    assert err.status_code == 403
    assert err.error_class is ErrorClass.NO_ENTITLEMENT


def test_crawler_error_status_code_is_keyword_only() -> None:
    # keyword-only：位置传参不落到 status_code（保护既有构造点签名）。
    err = CrawlerError(ErrorClass.CONFIG, "msg", detail="d")
    assert err.status_code is None
    assert err.detail == "d"


def test_capability_not_supported_status_code_none() -> None:
    """既有子类不传 status_code → None（纯附加不改子类构造）。"""
    assert CapabilityNotSupported().status_code is None


# -- AuthRequired / Challenged 子类（auth-framework §2.4，固定 error_class）-----------------


def test_auth_required_fixed_auth_expired_class() -> None:
    err = AuthRequired()
    assert isinstance(err, CrawlerError)
    assert err.error_class is ErrorClass.AUTH_EXPIRED
    assert err.status_code is None
    assert str(err)  # 非空默认文案


def test_auth_required_custom_msg_and_detail() -> None:
    err = AuthRequired("need login", detail="provider=elsevier")
    assert err.error_class is ErrorClass.AUTH_EXPIRED
    assert "need login" in str(err)
    assert err.detail == "provider=elsevier"


def test_challenged_fixed_challenge_class() -> None:
    err = Challenged()
    assert isinstance(err, CrawlerError)
    assert err.error_class is ErrorClass.CHALLENGE
    assert err.status_code is None
    assert str(err)


def test_challenged_custom_msg_and_detail() -> None:
    err = Challenged("captcha wall", detail="cloudflare")
    assert err.error_class is ErrorClass.CHALLENGE
    assert "captcha wall" in str(err)
    assert err.detail == "cloudflare"


# 子类矩阵（P2#4 热修）：`errors.py` 里*全部* CrawlerError 子类 × 其固定 error_class。
# 手工清单——配合下方 `test_error_class_matrix_covers_every_crawler_error_subclass`
# 的集合等值自断言（同 F5 canary 手法）：新增子类忘了登记这里会立刻红，根治
# "注册了却没验证"反模式。
_ERROR_CLASS_MATRIX: list[tuple[type[CrawlerError], ErrorClass]] = [
    (CapabilityNotSupported, ErrorClass.CONFIG),
    (AuthRequired, ErrorClass.AUTH_EXPIRED),
    (Challenged, ErrorClass.CHALLENGE),
    (SubscriptionInvalid, ErrorClass.CONFIG),
    # P6-T4：watermark 文档损坏 = 运行期状态问题，与 DSL 手写错误分立（处置动作不同：
    # 重置游标 vs 改 YAML），但同归 CONFIG——与 `read_watermark` 对畸形 JSON 的分类一致。
    (WatermarkInvalid, ErrorClass.CONFIG),
]


@pytest.mark.parametrize(
    ("subclass", "expected_class"),
    _ERROR_CLASS_MATRIX,
    ids=[cls.__name__ for cls, _ in _ERROR_CLASS_MATRIX],
)
def test_crawler_error_subclasses_route_via_fixed_error_class(
    subclass: type[CrawlerError], expected_class: ErrorClass
) -> None:
    # 不新增 ErrorClass 九类——子类只固定既有类别（沿 CapabilityNotSupported 先例）。
    assert subclass().error_class is expected_class
    assert expected_class in set(ErrorClass)


def _all_crawler_error_subclasses() -> set[type[CrawlerError]]:
    """递归收集 `CrawlerError` 的全部子类（`__subclasses__()` 只返回直接子类，
    这里做广度优先遍历以覆盖"子类的子类"）。"""
    collected: set[type[CrawlerError]] = set()
    frontier = [CrawlerError]
    while frontier:
        parent = frontier.pop()
        for child in parent.__subclasses__():
            if child not in collected:
                collected.add(child)
                frontier.append(child)
    return collected


def test_error_class_matrix_covers_every_crawler_error_subclass() -> None:
    """集合等值自断言：`_ERROR_CLASS_MATRIX` 覆盖集 == `errors.py` 里实际存在的
    全部 `CrawlerError` 子类（同 F5 canary 手法）。

    根治"注册了却没验证"——以后谁给 `errors.py` 加了新的 `CrawlerError` 子类却
    忘了登记到矩阵，这里立刻红，而不是悄悄漏掉一个从未被验证过 error_class 的类型。
    """
    covered = {subclass for subclass, _ in _ERROR_CLASS_MATRIX}
    assert _all_crawler_error_subclasses() == covered
