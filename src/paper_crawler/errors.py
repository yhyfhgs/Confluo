"""错误分类学与重试表（接口冻结件 §2.1）。

`ErrorClass` 是全系统唯一的错误语义枚举（design/05 §4）：任何异常路径都必须
映射到其中一类。`RETRY_TABLE` 给出各类的重试策略；未列出的类默认 `RetrySpec(1)`
（不重试），其中 AUTH_EXPIRED / CHALLENGE / CONFIG 由 pipeline 特判转 BLOCKED。
"""

from dataclasses import dataclass
from enum import StrEnum


class ErrorClass(StrEnum):
    """贯穿全系统的统一错误枚举（design/05 §4 的九类）。"""

    TRANSIENT = "transient"
    RATE_LIMITED = "rate_limited"
    AUTH_EXPIRED = "auth_expired"
    NO_ENTITLEMENT = "no_entitlement"
    CHALLENGE = "challenge"
    GONE = "gone"
    PARSE = "parse"
    INTEGRITY = "integrity"
    CONFIG = "config"


class CrawlerError(Exception):
    """系统内一切受控异常的基类；`error_class` 决定 pipeline 的处置路径。"""

    error_class: ErrorClass
    detail: str

    def __init__(self, error_class: ErrorClass, msg: str, *, detail: str = "") -> None:
        super().__init__(msg)
        self.error_class = error_class
        self.detail = detail


class IllegalTransition(Exception):
    """task 状态机非法转移（design/05 §8）；不属于 ErrorClass 语义。"""


class CapabilityNotSupported(CrawlerError):
    """adapter 未声明的能力被调用；error_class 恒为 CONFIG。"""

    def __init__(self, msg: str = "capability not supported", *, detail: str = "") -> None:
        super().__init__(ErrorClass.CONFIG, msg, detail=detail)


@dataclass(frozen=True)
class RetrySpec:
    """重试规格；`backoff_seconds` 秒值可被 `Config.retry_scale` 缩放。"""

    max_attempts: int  # 含首次；1 = 不重试
    backoff_seconds: tuple[float, ...] = ()


# design/05 §4 重试表。未列出的 ErrorClass 默认 RetrySpec(1)（消费方用 .get 兜底）。
RETRY_TABLE: dict[ErrorClass, RetrySpec] = {
    ErrorClass.TRANSIENT: RetrySpec(4, (2.0, 8.0, 30.0)),  # 3 次重试
    ErrorClass.RATE_LIMITED: RetrySpec(4, (2.0, 8.0, 30.0)),  # 不计 attempts（队列层特判）
    ErrorClass.INTEGRITY: RetrySpec(2, (0.0,)),  # 重下 1 次
    # 其余 → RetrySpec(1)；AUTH_EXPIRED/CHALLENGE/CONFIG → BLOCKED（pipeline 特判）
}
