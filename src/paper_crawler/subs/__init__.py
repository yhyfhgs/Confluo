"""订阅域（Phase 6；design/09 主题订阅与精确搜索）。

导出面 = plan §2 的两件冻结件：`model`（DSL 类型 + 加载校验入口）与 `types`
（编译计划 + 日报数据结构）。后续任务的实现件（T2 `compile.py`、T3 `filter.py`/
`guard.py`、T4 `watermark.py`、T5 `watch.py`、T6 `report.py`）从各自模块直接
import——**本 `__init__` 恒不导入它们**：`storage.repo.SubscriptionRepo` 反向依赖
`subs.model`（局部 import），若本文件再导入依赖 storage 的实现件就会成环。
"""

from paper_crawler.subs.model import (
    Actions,
    Guard,
    LocalFilter,
    SourceSelector,
    Subscription,
    load_subscription_file,
    load_subscriptions_dir,
    parse_subscription,
)
from paper_crawler.subs.types import (
    CompiledPlan,
    FailureEvent,
    PlanStep,
    ReportEntry,
    RunSummary,
    WatchOutcome,
)

__all__ = [
    "Actions",
    "CompiledPlan",
    "FailureEvent",
    "Guard",
    "LocalFilter",
    "PlanStep",
    "ReportEntry",
    "RunSummary",
    "SourceSelector",
    "Subscription",
    "WatchOutcome",
    "load_subscription_file",
    "load_subscriptions_dir",
    "parse_subscription",
]
