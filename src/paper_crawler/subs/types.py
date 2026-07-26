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

# 源专属补偿谓词的命名约定：`"<source>.<name>"`（如 `"ssrn.topic_filter"`）。
_SOURCE_SCOPED_SEPARATOR = "."


def is_source_scoped_predicate(name: str) -> bool:
    """该谓词标记是否**源专属**（点分名）而非全源通用（`LOCAL_PREDICATE_*`）。

    分流契约的**单一同源**判别式，三方消费（T2 产 / T3 收 / T5 分流），谁都不再
    自己写 `"." in name`：

    - **T2**（`compile.py`）按此约定**产**标记（`PREDICATE_SSRN_TOPIC_FILTER`）；
    - **T3**（`filter.py`）**收**——通用谓词走 `LocalFilter` 三件套，源专属的走
      各自的补偿实现（当前仅 `ssrn.topic_filter`）；
    - **T5**（`watch.py`）按此**分流**：把源专属谓词只喂给对应源的结果流，不误伤别源。

    判据是"含点分隔符且两侧非空"——`LOCAL_PREDICATE_*` 三个名字都不含点，故二者
    天然不重叠；`"title_regex_any[0]"` 这类 T3 产的**命中记录**同样不含点，不会被
    误判为源专属。
    """
    source, separator, predicate = name.partition(_SOURCE_SCOPED_SEPARATOR)
    return bool(separator) and bool(source) and bool(predicate)


# --- T2/T4/T5 接缝：各源日期窗参数名（单一同源，不必再翻文档）----------------
#
# **只声明槽位名**：值由 T4（`watermark.py`）按增量语义产出，T5 与 T2 的静态参数合成。
# 本表住在叶子模块 `types.py` 而非 `compile.py`——三方消费（T2 反查"用户不许手写日期
# 窗"的禁名单、T4 自断言产出键 ⊆ 本表、T5 合成），住在任一消费方里都会让另两方反向
# 依赖它。出处逐源：
#
# - arxiv：`submittedDate:[YYYYMMDDTTTT TO YYYYMMDDTTTT]`（GMT）——不是独立 URL 参数，
#   而是拼进**同一个 `search_query`** 的范围项（site-survey/arxiv.md 关键机制段）。
# - crossref：`filter=from-pub-date:…,until-pub-date:…`（published 轴的 filter 名是 `pub`
#   缩写；见 `adapters/crossref/adapter.py::_DATE_FIELD_FILTER`）。
# - openalex：`filter=from_publication_date:…,to_publication_date:…`（免费轴；
#   `from_created/updated_date` 是 Premium 门控，site-survey/metadata-apis.md）。
# - s2：bulk search 顶层参数 `publicationDateOrYear`（site-survey/metadata-apis.md 首列项；
#   `year=` 是同轴的年粒度替代，T4 取前者以保住日粒度——见 `watermark.py` s2 条）。
# - nber：**无日期参数**——RSS 通道按 id 集合差分推进（出处 = plan §4 的 T4/T7 两卡 +
#   nber.md §3.4「RSS 增量 watch 通道」/§7；design/09 §5 未列 nber，勿引）。
# - ssrn：内部 crossref 走 created 轴 → `from-created-date`/`until-created-date`
#   （ssrn.md §4.2 登记年轴）。**两端必须成对**：`CrossrefAdapter._works_url` 无条件
#   拼 `from-…,until-…`，缺 until 端就是半截 filter。design/09 §5 的 D-029 联动修订
#   （2026-07-26）已把 SSRN 行从"id 集合差分"改判为本游标。
DATE_WINDOW_PARAMS: dict[str, tuple[str, ...]] = {
    "arxiv": ("submittedDate",),
    "ssrn": ("from-created-date", "until-created-date"),
    "openalex": ("from_publication_date", "to_publication_date"),
    "s2": ("publicationDateOrYear",),
    "nber": (),
    "crossref": ("from-pub-date", "until-pub-date"),
}


# --- T2/T5 接缝：arxiv 分类 fan-out 的两个下推键（单一同源）-------------------
#
# 键名与 arxiv venue YAML 的 quirks 键**逐字相同**（`venues/preprint/arxiv-*.yaml`）：
# 经 `watch.AdapterFetcher.venue_for` 并进 `quirks` 后，正是
# `adapters/arxiv/adapter.py::_oai_target` 读的两个键——`arxiv_category` 决定客户端按
# `primary_category` 的子分类过滤，`arxiv_set` 决定 OAI-PMH 的 `set=`（archive 级）。
# adapter 侧因此零改动：下达通道是它**既有**的配置入口。
#
# **两键必须成对下推**：生产路径恒注入真实 venue（`cli._watch_source_venues` 按 id 序
# 取该源首个），其静态 `arxiv_set`（如 `arxiv_cs_ai` 的 `cs`）在 `venue_for` 的
# `{**existing.quirks, **params}` 合并中**存活**——只推 `arxiv_category=q-fin.PR` 会变成
# "在 `set=cs` 里按 q-fin.PR 客户端过滤"，恒空。`arxiv_set` 的派生式与 `_oai_target` 的
# 兜底派生**同式**（`category.split(".", 1)[0]`；`'q-fin.PR' → 'q-fin'` 可靠，带连字符的
# archive 亦然）。
#
# 表住在叶子模块（同 `DATE_WINDOW_PARAMS` 的守法）：T2（`compile.py` 产分类条目）与
# T5（`watch.py` 逐分类展开 + 派生 set）两侧共同消费，住在任一方都会让另一方反向依赖，
# 且两处各记一份键名迟早漂移。
ARXIV_CATEGORY_PARAM = "arxiv_category"
ARXIV_SET_PARAM = "arxiv_set"


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
    - `ingested_count`：真正入库数——dry-run 与熔断路径恒 0（`__post_init__` 强制，
      P2#3 热修；plan §4 T5 已裁决）；
    - `fetched_count`：本次派生的 fetch 任务数（`actions.auto_fetch_limit` 上限内）——
      同样受 dry-run 恒零约束；
    - `library_total`：累计库存（日报第二要素，§6.3）。

    `narrowing_hints`/`distribution`（Phase 6 深审热修追加，纯追加不改既有字段；
    T3/T6 接缝终裁二次调整）——AC-6.2（过载报告需给出可操作的收窄线索）的判据
    承载字段：
    - `distribution`：`(axis, label, count)` 有序三元组，`axis ∈ {"source", "category"}`
      （取值域仅 docstring 约定，非类型系统强制）。T5 从 `subs.guard.OverloadReport`
      的 `by_source`/`by_category` 两轴分布各自打上 axis 标签后拼接装配成一个扁平
      序列；T6 渲染日报时按 `axis` 过滤拆回两张表（来源分布表、类目分布表）。
    - `narrowing_hints`：当前 T5 恒留空（`()`）——收窄建议句改由 T6 直接从
      `distribution` 的计数现算（算法思路同 `subs.guard._suggest_narrowing`），不
      经 T5 预先算好传递。字段保留作未来面（如需要脱离 `distribution` 的独立提示）。
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
    # T3 guard 生成 → T5 装配 → T6 渲染（AC-6.2）；纯追加字段，既有构造点缺省即空。
    narrowing_hints: tuple[str, ...] = ()  # 当前 T5 恒留空；收窄句由 T6 从 distribution 现算
    distribution: tuple[tuple[str, str, int], ...] = ()  # (axis, label, count)，axis 见类 docstring

    def __post_init__(self) -> None:
        """dry-run 不变量（P2#3 热修）：`dry_run=True` 时绝不能真的入库或派生 fetch。

        违反即拒绝构造（`ValueError`）——不是运行期悄悄纠正，是构造期就响亮报错，
        逼上游（T5）在装配 `RunSummary` 前就把 dry-run 路径的计数清零，而不是"先
        算出真实计数再假装是演习"。
        """
        if self.dry_run and (self.ingested_count != 0 or self.fetched_count != 0):
            raise ValueError(
                "RunSummary: dry_run=True 时 ingested_count/fetched_count 必须为 0"
                f"（实际 ingested_count={self.ingested_count}, "
                f"fetched_count={self.fetched_count}）"
            )

    @property
    def truncated(self) -> bool:
        """熔断标记（`subscription_run.truncated` 的来源）——由 `outcome` 单一决定。"""
        return self.outcome is WatchOutcome.TRUNCATED


__all__ = [
    "ARXIV_CATEGORY_PARAM",
    "ARXIV_SET_PARAM",
    "DATE_WINDOW_PARAMS",
    "LOCAL_PREDICATE_EXCLUDE_REGEX",
    "LOCAL_PREDICATE_MIN_YEAR",
    "LOCAL_PREDICATE_TITLE_REGEX_ANY",
    "CompiledPlan",
    "FailureEvent",
    "PlanStep",
    "ReportEntry",
    "RunSummary",
    "WatchOutcome",
    "is_source_scoped_predicate",
]
