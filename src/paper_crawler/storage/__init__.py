"""存储层：SQLite 连接/迁移器（`Database`）与仓储层（`Repo`）。

接口冻结件 §2.4。schema v1 见 `migrations/0001_init.sql`。
"""

from paper_crawler.storage.db import Database
from paper_crawler.storage.repo import Repo

__all__ = ["Database", "Repo"]
