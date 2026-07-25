"""订阅域接口冻结件：编译计划与日报数据结构（Phase 6 T1；plan §2 冻结表第二行）。

本模块是**叶子**：只依赖标准库，不导入 `subs.model`／`storage`／`adapter`——下游
T2（编译器）、T3（过滤+护栏）、T5（watch runner）、T6（日报渲染）共同消费这些结构，
任何一方都不应为了拿到类型而反向依赖另一方。

三组结构：

1. `PlanStep`/`CompiledPlan`——查询编译产物（design/09 §3）。每步 = 一个源的
   **下推参数** + 该源**下推不了、必须本地补偿**的谓词标记。原则句（§3 末）：
   "下推尽可能多以省流量，但正确性以本地过滤为准"——故 `local_predicates` 是
   T3 与 T5 的正确性契约，不是提示信息。
2. `WatchOutcome`/`FailureEvent`/`ReportEntry`/`RunSummary`——一次 watch 运行的
   结果（design/09 §6 日报三要素：每订阅新增清单、累计库存、失败与熔断事件）。
   `RunSummary` 由 T5 产出、T6 渲染、`SubscriptionRepo.record_run` 落库。
3. 谓词标记常量——`LOCAL_PREDICATE_*` 与 `model.LocalFilter` 字段名单一同源
   （防两处清单漂移）；源专属补偿谓词用 `"<source>.<name>"` 形式（如
   `"ssrn.topic_filter"`，plan §4 T2 检查单 #10）。

约定（同 `paper_crawler.types` 模块 docstring）：全部 dataclass `frozen`、需
hashable，故弹性字段一律 tuple-of-tuples 而非 dict；时间戳 UTC ISO8601 字符串。
"""

from dataclasses import dataclass
from enum import StrEnum

# 本地补偿谓词的标准标记（= `model.LocalFilter` 的字段名，单一同源）。
LOCAL_PREDICATE_TITLE_REGEX_ANY = "title_regex_any"
LOCAL_PREDICATE_EXCLUDE_REGEX = "exclude_regex"
LOCAL_PREDICATE_MIN_YEAR = "min_year"


# ---------------------------------------------------------------------------
# 编译计划（T2 产出 → T5 执行）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PlanStep:
    """一个源的一步执行计划：下推参数 + 本地补偿谓词标记。

    - `pushdown` 是**有序 k-v 序列**而非 dict：URL 查询串允许重复键（如 OpenAlex
      多个 `filter=`），且 frozen dataclass 需 hashable（模块 docstring 约定）。
      值一律字符串——编译产物直接就是查询参数形态；需要 dict 视图时用 `as_params()`。
    - `local_predicates` 列出该源**下推不了**、必须在本地过滤器（T3）补偿的谓词
      标记。空元组 = 该源已完整下推。
    - `note` 是编译期备注（如 "ssrn 无关键词下推能力，关键词全量本地补偿"），
      供日报/诊断呈现，不参与判定。
    """

    source: str
    pushdown: tuple[tuple[str, str], ...] = ()
    local_predicates: tuple[str, ...] = ()
    note: str = ""

    def as_params(self) -> dict[str, str]:
        """`pushdown` 的 dict 视图（重复键取**最后**一个，同 URL 解析惯例）。

        仅供只关心单值参数的消费方；构造真实请求时用 `pushdown` 本身以保留重复键。
        """
        return dict(self.pushdown)


@dataclass(frozen=True)
class CompiledPlan:
    """一个订阅编译后的全部执行步骤（每源一步，顺序即 DSL `sources:` 声明序）。"""

    subscription: str
    steps: tuple[PlanStep, ...] = ()

    def step_for(self, source: str) -> PlanStep | None:
        """取某源的步骤；该源不在计划内时 None。"""
        return next((step for step in self.steps if step.source == source), None)

    def all_local_predicates(self) -> tuple[str, ...]:
        """全部步骤的补偿谓词并集（保序去重）——AC-6.4 "下推+补偿 == 全本地" 的判据面。"""
        seen: dict[str, None] = {}
        for step in self.steps:
            for predicate in step.local_predicates:
                seen.setdefault(predicate, None)
        return tuple(seen)


# ---------------------------------------------------------------------------
# 运行结果与日报（T5 产出 → T6 渲染 / repo 落库）
# ---------------------------------------------------------------------------


class WatchOutcome(StrEnum):
    """一次订阅运行的终态。

    与 `RunSummary.dry_run` **正交**（dry-run 也可能"本会熔断"——此时
    `outcome=TRUNCATED` + `dry_run=True` + `ingested_count=0`，过载报告照出）。
    """

    OK = "ok"  # 正常完成（含零新增）
    TRUNCATED = "truncated"  # 护栏熔断（design/09 §6.1）：零入库，只出过载报告
    FAILED = "failed"  # 本订阅整体失败（全部源失败等）；watermark 不推进（T4 纪律）


@dataclass(frozen=True)
class FailureEvent:
    """一次运行中的失败事件（日报"失败与熔断事件"段，design/09 §6.3）。

    `error_class` 取 `errors.ErrorClass` 的字符串值（此处存字符串而非枚举，避免
    本叶子模块反向依赖上层；渲染与落库都只需要文本）。
    """

    source: str
    error_class: str
    message: str


@dataclass(frozen=True)
class ReportEntry:
    """日报"新增清单"的一条（design/09 §6.3：标题/作者/链接/命中的过滤规则）。

    - `matched_rules`：本条命中的**本地过滤规则**标记（T3 填，如
      `("title_regex_any[0]",)`）——日报据此让用户看清"为什么这条被收进来"，
      也是噪声反馈回路（§6.4，Phase 7）的输入。
    - `categories`：源侧分类（arXiv cat / SSRN 网络 / NBER program 等），供过载
      报告的"按分类分布"（§6.1）分组。
    - `paper_id`：入库后的内部 ULID；dry-run / 熔断路径无入库 → None。
    """

    title: str
    authors: tuple[str, ...] = ()
    url: str = ""
    matched_rules: tuple[str, ...] = ()
    source: str = ""
    categories: tuple[str, ...] = ()
    paper_id: str | None = None


@dataclass(frozen=True)
class RunSummary:
    """一次订阅运行的完整摘要——T6 渲染日报、repo 落 `subscription_run` 的唯一入参面。

    计数口径（避免下游各算各的）：
    - `seen_count`：本次从各源拉到的候选总数（本地过滤前）；
    - `new_count`：本地过滤 + 去重后的**净新增**数（= 护栏比对的量，design/09 §6.1）；
    - `ingested_count`：真正入库数——dry-run 与熔断路径恒 0（plan §4 T5 已裁决）；
    - `fetched_count`：本次派生的 fetch 任务数（`actions.auto_fetch_limit` 上限内）；
    - `library_total`：累计库存（日报第二要素，§6.3）。
    """

    subscription: str
    started_at: str
    finished_at: str = ""
    outcome: WatchOutcome = WatchOutcome.OK
    dry_run: bool = False
    entries: tuple[ReportEntry, ...] = ()
    seen_count: int = 0
    new_count: int = 0
    ingested_count: int = 0
    fetched_count: int = 0
    library_total: int = 0
    guard_limit: int = 0  # 本次生效的 `guard.max_new_per_run`（过载报告展示阈值）
    failures: tuple[FailureEvent, ...] = ()
    report_path: str | None = None

    @property
    def truncated(self) -> bool:
        """熔断标记（`subscription_run.truncated` 的来源）——由 `outcome` 单一决定。"""
        return self.outcome is WatchOutcome.TRUNCATED


__all__ = [
    "LOCAL_PREDICATE_EXCLUDE_REGEX",
    "LOCAL_PREDICATE_MIN_YEAR",
    "LOCAL_PREDICATE_TITLE_REGEX_ANY",
    "CompiledPlan",
    "FailureEvent",
    "PlanStep",
    "ReportEntry",
    "RunSummary",
    "WatchOutcome",
]
