"""`AuthProvider` Protocol 接口冻结件（auth-framework §2.2；T1a 落盘后冻结，改动须仲裁）。

五方法签名逐字对齐 design/auth-framework.md §2.2（07 §2 伪代码的实现级落地）：
`ensure_session` / `health_check` / `refresh` / `invalidate` / `rewrite_url`。
`@runtime_checkable`（沿 `SourceAdapter` 先例，供装配期 duck-typed 甄别）。

异常契约（§2.2）：`ensure_session(interactive=False)` 无 session → `AuthRequired`；
探针命中风控 → `Challenged`（两异常子类归 **T2 权威版 errors.py**，auth-framework §2.4）；
其余网络异常沿用 `HttpClient` 冻结错误映射（§6）。

红线（AGENTS §6 / D-006）：只用用户自有合法凭证；探针/续期不触发风控对抗——
CHALLENGED 即如实上报，绝无破解/绕过路径（AC-0.2）。
"""

from typing import Literal, Protocol, runtime_checkable

from paper_crawler.types import HealthStatus, SessionHandle

ProviderKind = Literal["cookie_session", "ezproxy", "sso_flow", "api_key"]


@runtime_checkable
class AuthProvider(Protocol):
    """认证 provider 冻结协议（auth-framework §2.2 五方法）。"""

    provider_id: str  # profiles.toml 的 provider 键（含 profile 后缀，如 'elsevier@ezproxy'）
    kind: ProviderKind

    def ensure_session(self, *, interactive: bool = False) -> SessionHandle:
        """返回可用会话。不可用且 interactive=False → raise AuthRequired（不半途而废，07 §5-1）。
        interactive=True 时可走首登（headed 浏览器 / 交互式 key 配置校验）。"""

    def health_check(self, session: SessionHandle) -> HealthStatus:
        """OK | EXPIRED | CHALLENGED（07 §2）。探针不触发风控对抗——CHALLENGED 即如实上报。"""

    def refresh(self, session: SessionHandle) -> SessionHandle | None:
        """静默续期成功→新 handle；
        不可静默续期→None（07 §2；SSO 侧 IdP session 尚存时常见可续）。"""

    def invalidate(self, session: SessionHandle) -> None:
        """使 session 失效并从 CredentialStore 删除其 payload（AC-4.5 取证式彻底删除）。"""

    def rewrite_url(self, url: str) -> str:
        """默认恒等（AdapterProviderBase 提供）；
        仅 EZProxyProvider 覆盖为真实重写（07 §2/§3.2）。"""


class AuthProviderBase:
    """便利基类（**非冻结**，仿 `AdapterBase`；auth-framework §2.2）。

    提供 `rewrite_url` 恒等默认 + `invalidate` 的 store 删除样板；四 provider
    （T1b）各覆盖 `ensure_session`/`health_check`/`refresh` 并设类属性
    `provider_id`/`kind`。`invalidate` 依赖 `CredentialStore`（T1b 交付，
    auth-framework §2.3）——本基类只定义抽象委托点 `_delete_payload`，不落
    store 逻辑；T1b 在 provider/基类接线处委派 `store.delete_state(ref)`。
    """

    provider_id: str
    kind: ProviderKind

    def rewrite_url(self, url: str) -> str:
        """默认恒等（auth-framework §2.2）；仅 EZProxyProvider 覆盖为真实重写（07 §2/§3.2）。"""
        return url

    def invalidate(self, session: SessionHandle) -> None:
        """invalidate 样板：删除 `session.payload_ref` 指向的加密 payload
        （AC-4.5 取证式彻底删除）；store 细节经 `_delete_payload` 委托。"""
        self._delete_payload(session.payload_ref)

    def _delete_payload(self, payload_ref: str) -> None:
        """抽象委托点：从 CredentialStore 删除 payload 条目（T1b 实现——
        `store.delete_state(ref)`，auth-framework §2.3；本 T1a 基类不落 store 逻辑）。"""
        raise NotImplementedError("CredentialStore 删除样板归 T1b（auth-framework §2.3/§3）")


__all__ = ["AuthProvider", "AuthProviderBase", "ProviderKind"]
