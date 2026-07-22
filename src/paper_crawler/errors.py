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
    # 原始 HTTP 状态码（auth-framework §6，检查单 #4 闭合）：**纯附加**，缺省 None =
    # 非 HTTP 来源（超时/连接/解析/配置等）。`http.py` 的状态映射额外携带它，供上层
    # 精确重分类（如 openalex 402 credit 耗尽经 `exc.status_code == 402` 判定，不再靠
    # 解析异常消息里 `"HTTP {status} for …"` 文本）。映射表本身不因此改变——只是**额外
    # 携带**原始 status。既有全部构造点不传该 kwarg → None，读 `.status_code` 的新代码
    # 用 `== <int>` 判定，非 HTTP 来源天然 None 不会误命中。
    status_code: int | None

    def __init__(
        self,
        error_class: ErrorClass,
        msg: str,
        *,
        detail: str = "",
        status_code: int | None = None,
    ) -> None:
        super().__init__(msg)
        self.error_class = error_class
        self.detail = detail
        self.status_code = status_code


class IllegalTransition(Exception):
    """task 状态机非法转移（design/05 §8）；不属于 ErrorClass 语义。"""


class CapabilityNotSupported(CrawlerError):
    """adapter 未声明的能力被调用；error_class 恒为 CONFIG。"""

    def __init__(self, msg: str = "capability not supported", *, detail: str = "") -> None:
        super().__init__(ErrorClass.CONFIG, msg, detail=detail)


class AuthRequired(CrawlerError):
    """无可用 session 且未交互（首登缺失/session 已 invalidate）；`error_class` 恒
    `AUTH_EXPIRED`（auth-framework §2.4，沿 `CapabilityNotSupported` 固定 error_class 先例）。

    → runner 路由为整批 BLOCKED(auth)，提示 `crawler auth login <provider>`。**canary
    healthcheck 路径不抛本异常**（无 session 的 healthcheck 语义 = adapter 抛
    `NotImplementedError` → SKIP，二义分离；auth-framework §7 B-M4）。
    """

    def __init__(self, msg: str = "auth session required", *, detail: str = "") -> None:
        super().__init__(ErrorClass.AUTH_EXPIRED, msg, detail=detail)


class Challenged(CrawlerError):
    """风控/CAPTCHA/异常验证页命中特征库；`error_class` 恒 `CHALLENGE`（auth-framework
    §2.4）。→ runner 路由为 BLOCKED(challenge) + 平台冷却。**绝不尝试破解**（AC-0.2）。"""

    def __init__(self, msg: str = "anti-abuse challenge detected", *, detail: str = "") -> None:
        super().__init__(ErrorClass.CHALLENGE, msg, detail=detail)


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
