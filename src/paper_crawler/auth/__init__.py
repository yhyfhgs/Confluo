"""认证框架包（Phase 4；design/auth-framework.md）。

T1a 冻结件先行包：`AuthProvider` Protocol（§2.2，`protocol.py`）+
`ChallengeDetector` 判定器（§11，`challenge.py`）。

导出面对齐 auth-framework §1 模块表的 `auth/__init__.py` 行——本 T1a 先落其中
已存在的子集；`AuthRequired`/`Challenged`（T2 权威版 errors.py，§2.4）与
`load_providers`/`AuthManager`（T1b，§1）随各任务合并后补齐导出。
`ChallengeDetector`/`AuthProviderBase` 等不在 §1 导出清单内的件从各自模块
（`paper_crawler.auth.challenge`/`paper_crawler.auth.protocol`）直接 import。
"""

from paper_crawler.auth.protocol import AuthProvider
from paper_crawler.types import HealthStatus, SessionHandle

__all__ = ["AuthProvider", "HealthStatus", "SessionHandle"]
