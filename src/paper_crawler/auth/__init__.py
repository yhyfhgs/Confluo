"""认证框架包（Phase 4；design/auth-framework.md）。

导出面 = auth-framework §1 模块表的 `auth/__init__.py` 行：`AuthProvider`/
`SessionHandle`/`HealthStatus`/`AuthRequired`/`Challenged`/`load_providers`/
`AuthManager`（T1a 冻结件 + T2 权威版异常 + T1b 本体，全部到位）。

不在 §1 导出清单内的件从各自模块直接 import：`ChallengeDetector`/`AuthProviderBase`
（`auth.challenge`/`auth.protocol`）、`CredentialStore`/`ProviderProfile`
（`auth.store`）、四 provider 实现（`auth.providers`）、browser seam（`auth.browser`，
惰性——本 `__init__` 不触达，import auth 包不加载任何可选依赖路径）。
"""

from paper_crawler.auth.manager import AuthManager, load_providers
from paper_crawler.auth.protocol import AuthProvider
from paper_crawler.errors import AuthRequired, Challenged
from paper_crawler.types import HealthStatus, SessionHandle

__all__ = [
    "AuthManager",
    "AuthProvider",
    "AuthRequired",
    "Challenged",
    "HealthStatus",
    "SessionHandle",
    "load_providers",
]
