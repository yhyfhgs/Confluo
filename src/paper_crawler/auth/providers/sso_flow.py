"""`SSOFlowProvider`（auth-framework §1/§4.1；07 §3.3；T1b）。

复用 cookie_session 的 storage_state 机制（继承 `CookieSessionProvider`）；差异面：

- 首登打开 `inst_login_url`（WAYF 选机构由用户人工完成，`wayf_hint` 仅作提示——
  不自动化 MFA，D-006）；backend = `playwright_state`（浏览器上下文复用形态）。
- **`refresh` = headless 重放 InstitutionalLogin**（07 §3.3：IdP session 尚存时常见
  可静默续期）：携既有 cookie jar GET `inst_login_url`（纯 302 链 + Set-Cookie，
  mock 层可测，§9）——回跳落在已登录态 → 合并新 cookie 回写 state → 新 handle；
  落回 login 页（IdP 亦过期）→ None；命中风控 → `Challenged`（不重试不对抗）。
"""

import httpx

from paper_crawler.auth.challenge import ClassifyResult
from paper_crawler.auth.protocol import ProviderKind
from paper_crawler.auth.providers.cookie_session import (
    CookieSessionProvider,
    _required,
    cookies_to_storage_state,
    storage_state_to_cookies,
)
from paper_crawler.errors import Challenged
from paper_crawler.types import HealthStatus, SessionBackend, SessionHandle


class SSOFlowProvider(CookieSessionProvider):
    """Shibboleth / OpenAthens 机构 SSO（07 §3.3）。"""

    kind: ProviderKind = "sso_flow"
    _backend = SessionBackend.PLAYWRIGHT_STATE

    def _login_url(self) -> str:
        return _required(self._profile.inst_login_url, "inst_login_url", self.provider_id)

    def refresh(self, session: SessionHandle) -> SessionHandle | None:
        """静默续期：重放 InstitutionalLogin；成功 → 新 handle / 不可续 → None（§2.2）。"""
        ref = session.payload_ref
        if not self._store.has_state(ref):
            return None  # 无可续之物（已 invalidate/未登录）
        inst_url = self._login_url()
        cookies = storage_state_to_cookies(self._store.read_state(ref))
        client = self._http_factory(cookies)
        try:
            try:
                response = client.get(inst_url)
            except httpx.HTTPError:
                return None  # 网络失败 → 不可静默续期（不半途重试，07 §5-1）
            result = self._detector.classify(
                status=response.status_code,
                headers=response.headers,
                final_url=str(response.url),
                body=response.content,
            )
            if result is ClassifyResult.CHALLENGE:
                # 续期探测命中风控：如实上报，绝不重试/对抗（AC-0.2/AC-4.6）。
                raise Challenged(detail=f"refresh({self.provider_id}) 命中风控挑战页")
            if result is not ClassifyResult.OK:
                return None  # 落回 login/异常路由：IdP session 亦过期 → 人工重登
            # 302 链的 Set-Cookie 已并入 client.cookies——合并态回写加密 state。
            new_state = cookies_to_storage_state(client.cookies)
        finally:
            client.close()
        now = self._clock()
        self._store.write_state(ref, new_state)
        self._store.write_meta(
            ref,
            {
                "backend": str(self._backend),
                "established_at": now.isoformat(),
                "last_health": str(HealthStatus.OK),
                "last_health_at": now.isoformat(),
            },
        )
        return self._handle(now)


__all__ = ["SSOFlowProvider"]
