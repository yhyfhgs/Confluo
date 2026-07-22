"""AuthProvider 四实现（auth-framework §1 模块表；T1b）。

kind → 实现类的注册表消费方在 `auth/manager.py`（`load_providers`）；平台 adapter
（T3/T4/T-wiley）经 manager/session 注入消费，不直接构造 provider。
"""

from paper_crawler.auth.providers.api_key import ApiKeyProvider
from paper_crawler.auth.providers.cookie_session import CookieSessionProvider
from paper_crawler.auth.providers.ezproxy import EZProxyProvider
from paper_crawler.auth.providers.sso_flow import SSOFlowProvider

__all__ = [
    "ApiKeyProvider",
    "CookieSessionProvider",
    "EZProxyProvider",
    "SSOFlowProvider",
]
