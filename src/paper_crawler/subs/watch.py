"""watch 编排：一次订阅增量运行的全链（Phase 6 T5；design/09 §5/§6 + design/05 §3 watch 模式）。

本模块是订阅域的**收口件**——T1（DSL/仓储）、T2（编译）、T3（过滤+护栏）、T4
（watermark）、T6（日报渲染）各自是纯件，谁都不知道彼此；把它们串成一次真实运行的
顺序、事务边界与"什么时候不该做什么"，全部在这里。

## 编排链（`run_watch` 的骨架，逐段对应 plan §4 T5 范围行）

```
加载订阅（subscriptions/ 目录 → upsert 入库；或直接读库）
  → T2 compile_subscription           每源一个 PlanStep（静态下推 + 补偿谓词标记）
  → T4 window_params                  每源本次的增量窗参数
  → build_requests                    静态参数 ⊕ 增量窗 → 逐条 SourceRequest
  → SourceFetcher.fetch               per-source 拉取（默认实现复用 adapter DISCOVER/ENUMERATE）
  → T4 IdSetDiff.new_ids              仅 id 差分类源：窗内先做增量差分
  → T3 filter_papers                  LocalFilter 三谓词 + 源专属补偿谓词（分流见下）
  → T3 dedupe_against_library         对库去重（guard.dedupe_against_library）
  → T3 is_truncated                   护栏熔断判定
  → 入库 / 派生取回链任务 / 推进 watermark / 落 subscription_run   ← 三条"不做"的分岔在此
  → RunSummary 装配 → T6 render_daily 落盘日报
```

## 五条"不做"的分岔（每条各自独立判，别用一个布尔糊过去）

| 情形 | 入库 | 派生任务 | 推 watermark | 落 run 记录 | 出日报 |
|---|---|---|---|---|---|
| 正常 | ✔ | ✔ | ✔ | ✔ | ✔ |
| 熔断（`TRUNCATED`） | ✘ | ✘ | ✘ | **✔**（`truncated=1`） | ✔（过载报告） |
| 整体失败（`FAILED`） | ✘ | ✘ | ✘ | ✔ | ✔（失败事件段） |
| `--dry-run` | ✘ | ✘ | ✘ | **✘** | ✔（**只回显 stdout，不落盘**） |
| 部分源失败 | ✔（成功源） | ✔ | ✔（成功源） | ✔ | ✔ |

熔断仍落 run 记录（plan §4 T5 已裁决歧义②）——"跑过但被护栏拦下"与"没跑"必须可
区分；dry-run 不落（design/09 §6.2"只报数不动库"，plan §4 T5 dry-run 语义），故
"熔断 + dry-run"同时成立时**以 dry-run 为准**：演习不留任何痕迹。

**dry-run 仍完整消费各源流**（AC-6.2 判据的前提）：拉取、`new_ids` 差分、本地过滤、
去重、熔断判定全程照跑，只是最后不落任何持久化。这是刻意的——生成器是惰性的，若
dry-run 走"早退"捷径，那些只在遍历时才触发的校验（解析异常、未登记谓词、坏日期）
一条都不会被触发，"上线前必跑 dry-run"这条操作规范就形同虚设（T7 教训）。

## 谓词分流（`types.is_source_scoped_predicate` 是单一判别式）

`PlanStep.local_predicates` 混着两类标记：全源通用的 `LocalFilter` 三谓词（T2 给每个
源都附上）与源专属的点分名（当前只有 `ssrn.topic_filter`）。前者由
`filter_papers(stubs, subscription.filters)` 天然执行——它读的是 `LocalFilter` 本身，
不看标记；后者必须经 `extra_predicates=` 显式传入，**且只喂给对应源**（否则 arxiv 的
结果会被 ssrn 的主题谓词误伤）。分流判据不在本模块自己写 `"." in name`，走冻结件的
`is_source_scoped_predicate`。

## 重复键逐条展开（`PlanStep.as_params()` 在本模块是禁用的）

`pushdown` 是**有序 k-v 序列**而非 dict，正是因为 crossref 多 ISSN / nber 多 program
会产生重复键——`as_params()` 的 dict 视图"重复键取最后一个"（其 docstring 明写），
在这里用一次就是静默丢掉 n-1 个刊/n-1 个 program：订阅照跑、日报照出、少了的那部分
无人察觉。故 `build_requests` 按源展开成**多条独立请求**（见 `_FANOUT_KEY`）。

## 源侧拉取接缝（`SourceFetcher`）

`SourceAdapter` 冻结协议是 venue/issue 轴的（`discover_timeline`/`enumerate_issue`），
没有"按查询参数搜索"的方法，Phase 6 也不动冻结件。故本模块定义一个**订阅域自己的**
拉取接缝 `SourceFetcher`（同 `EnrichmentSource` 的先例：立于冻结协议之外的 duck-typed
可选接口），并给出默认实现 `AdapterFetcher`——把一条 `SourceRequest` 映射为该源
adapter 的 DISCOVER→ENUMERATE 两步，`since=` 传增量窗下界，查询参数落合成 `VenueSpec`
的 `quirks`。真源的查询式枚举（arxiv `search_query`、s2 bulk search 等）随各自 adapter
的 watch 通道落地时经 `watch_incremental` 钩子接入，本模块不替 adapter 写 HTTP。

**nber 接线点（plan §4 T5 已裁决歧义⑪）**：本卡合并时 `adapters/nber/` 下**无**
`rss.py`——nber 源因此仍走 crossref 前缀枚举通道（`AdapterFetcher` 的
DISCOVER→ENUMERATE 默认路径），watermark 侧照旧是 `IdSetDiff`（T4 冻结的策略表）。
T7（`subs/nber-rss`）合并后，nber adapter 会带上 `discover_incremental`——届时
`AdapterFetcher._incremental_hook` 会自动优先走它（钩子名见 `_INCREMENTAL_HOOKS`），
本模块无需再改。

## 与既有 pipeline 队列的接缝（plan §7 风险②："T5 只派生任务不改 runner"）

`actions.ingest == "metadata+pdf"` 时按 `auto_fetch_limit` 派生取回链任务进既有
`task` 表，**不 drain**——下一次任意 pipeline 命令（`pull`/`timeline`/`list`）的
`drain()` 领取全局 PENDING 任务时顺带执行（`cli.py` 模块 docstring 的既有语义）。

派生的 kind 是 **`resolve` 而非 `fetch`**：`fetch` 任务的参数是 `asset` id，而元数据
刚入库时该 paper 一条 asset 行都还没有（asset 由 resolve 阶段产出）。`resolve` 是取回
链的入口阶段，派它才是"派生取回任务"的唯一可执行形态；`RunSummary.fetched_count`
计的就是这些派生数。resolve 需要 venue 路由（`_stage_resolve` 读 `paper.venue_id`），
故派生前把 paper 绑定到"该源担任 `fulltext_source` 的那个 venue"（registry 内 id 序
第一个）；找不到这样的 venue → 一条 WARNING + 不派生（响亮跳过，不静默产出永远
BLOCKED 的任务）。

## 退出码（design/05 §6 契约 0/1/2/3，CLI 层消费 `exit_code_for`）

`1（有失败）> 3（无失败但有熔断）> 0`——与 `cli._totals_exit_code` 同款优先级。熔断
落 3 而非 1：护栏拦截是**按用户配置正常工作**的结果，不是故障，但它需要人来收窄查询，
语义上与 pipeline 的 blocked（需人工介入）同档。用法/配置错（未知订阅名、坏 DSL）在
CLI 层归 2。
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Protocol, cast, runtime_checkable

from paper_crawler.adapter import SourceAdapter
from paper_crawler.errors import CrawlerError, ErrorClass
from paper_crawler.merge import MergeEngine
from paper_crawler.obslog import log_event
from paper_crawler.registry import VenueRegistry
from paper_crawler.storage.db import Database
from paper_crawler.storage.repo import Repo, SubscriptionRepo
from paper_crawler.subs.compile import compile_subscription
from paper_crawler.subs.filter import FilteredPaper, filter_papers, reset_predicate_warnings
from paper_crawler.subs.guard import build_overload_report, dedupe_against_library, is_truncated
from paper_crawler.subs.model import Subscription, load_subscriptions_dir
from paper_crawler.subs.report import render_daily
from paper_crawler.subs.types import (
    CompiledPlan,
    FailureEvent,
    PlanStep,
    ReportEntry,
    RunSummary,
    WatchOutcome,
    is_source_scoped_predicate,
)
from paper_crawler.subs.watermark import IdSetDiff, Watermark, advance, strategy_for, window_params
from paper_crawler.tasks import TaskQueue
from paper_crawler.types import PaperStub, VenueNames, VenueSpec, utcnow_iso

# 日报落盘根（design/05 §7"watch 模式报告落 `docs/reports/watch/`"；plan §4 T5 已裁决
# 歧义③——该子目录进 `.gitignore`，运行产物不入 git）。相对当前工作目录解析，同
# `canary.canary_record_path` 先例（预期在仓库根调用）。
DEFAULT_REPORT_ROOT = Path("docs") / "reports" / "watch"

# 每个订阅源在 `MergeEngine.ingest(source=…)` 里的来源身份。两套词表不同名是有原因的：
# `subs.model.SOURCE_FIELDS` 是**订阅 DSL 的源**（用户写什么），`merge.SOURCE_PRIORITY`
# 是**字段收敛的来源优先级**（谁的值更可信，D-021 冻结六枚举）。映射按"这批字节实际
# 来自哪儿"如实填，不按名字像不像：
#
# - arxiv → `official`：arXiv 就是其预印本的第一手记录（同 pull 路径 `upsert_paper`
#   对官方 proceedings 的最高优先处置）；
# - ssrn → `crossref`：D-029 后 ssrn 元数据主路径是 crossref 前缀 10.2139 枚举，站点
#   零接触——字节确实来自 crossref；
# - nber → `crossref`：本卡合并时 nber 仍走 crossref 前缀 10.3386 枚举（模块 docstring
#   "nber 接线点"）。T7 的 RSS 通道落地后，RSS 来的记录是 nber.org 官方一手，届时该
#   行应随 T7 一并改判 `official`——**不在本卡预先改**，否则会给当前真实走 crossref
#   的记录挂上一个更高的优先级，静默压过 crossref 自己的值。
MERGE_SOURCE: dict[str, str] = {
    "arxiv": "official",
    "ssrn": "crossref",
    "openalex": "openalex",
    "s2": "s2",
    "nber": "crossref",
    "crossref": "crossref",
}

# `stub.meta` 的读取约定（本模块是唯一消费点，故约定写在这里）：
# - `categories`：源侧分类，逗号分隔（arXiv cat / NBER program / SSRN 网络）——喂
#   `ReportEntry.categories` → 过载报告的"按分类分布"。不产该键的源分布只有来源轴，
#   如实为空，不臆造分类。
# - `url`：条目链接；缺失时退回 `https://doi.org/{doi}`，再缺则空串（日报渲染成 "-"）。
META_KEY_CATEGORIES = "categories"
META_KEY_URL = "url"

_DOI_RESOLVER = "https://doi.org/"


# ---------------------------------------------------------------------------
# 源侧拉取接缝
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SourceRequest:
    """一次源侧增量拉取请求 = 一个源的一条独立请求（重复键已展开）。

    - `params`：静态下推参数 ⊕ 增量窗参数，**有序 k-v**（同 `PlanStep.pushdown` 的
      约定，frozen dataclass 需 hashable）。展开后同一条请求内不再有语义上需要拆分的
      重复键；宿主形态特殊的窗（arxiv 并进 `search_query`、openalex 并进 `filter`）
      已由合成器就地拼好。
    - `since`：增量窗**下界**（ISO `YYYY-MM-DD`），与 `params` 里的窗**同源冗余**——
      因为并入宿主参数后它就不再是一个独立的 k-v 了，而 DISCOVER 的 `since=` 接缝
      需要它。无日期轴的源（nber）恒 None。
    - `note`：编译期备注透传（`PlanStep.note`），只供诊断呈现。
    """

    subscription: str
    source: str
    params: tuple[tuple[str, str], ...] = ()
    since: str | None = None
    note: str = ""


@runtime_checkable
class SourceFetcher(Protocol):
    """订阅域的源侧拉取接缝（duck-typed，立于 `SourceAdapter` 冻结协议之外）。

    实现者收一条 `SourceRequest`、给一串 `PaperStub`。抛 `CrawlerError` 表示该请求
    失败——编排层按源记 `FailureEvent` 并继续其他源，不让一个源的故障吞掉整轮 watch。
    """

    def fetch(self, request: SourceRequest) -> Iterable[PaperStub]: ...


# adapter 侧"增量拉取"钩子的候选名（duck-typed，按序探测；命中即优先于
# DISCOVER→ENUMERATE 默认路径）。`discover_incremental` 是 T7 nber RSS 的接线点
# （plan §4 T5 已裁决歧义⑪）；`watch_incremental` 留给后续源的查询式 watch 通道。
_INCREMENTAL_HOOKS: tuple[str, ...] = ("watch_incremental", "discover_incremental")

# 增量钩子的调用形态：参数 dict（合成后的请求参数）→ stub 流。
_IncrementalHook = Callable[[dict[str, str]], Iterable[PaperStub]]


class AdapterFetcher:
    """默认 `SourceFetcher`：把 `SourceRequest` 映射到该源 adapter 的既有能力。

    两条路径，按序：

    1. **增量钩子**（`_INCREMENTAL_HOOKS`）——adapter 若已实现订阅域的增量通道
       （T7 nber RSS 的 `discover_incremental`），直接交给它，参数以 `dict` 形态传入。
    2. **DISCOVER→ENUMERATE**（默认）——`discover_timeline(venue, since)` 圈出窗内的
       期/桶，逐个 `enumerate_issue(venue, ref)` 取 stub。这正是 plan §4 T5"复用各
       adapter 的 DISCOVER/ENUMERATE"的字面落地：不新写一套 HTTP/翻页/解析，限速与
       UA 由 CLI 装配期注入 adapter 的共享 `HttpClient` 承担（`cli._build_env` 既有
       装配，本模块不碰）。

    `venues` 按**源 id** 索引，给真实的 `VenueSpec`（如 ssrn 走 `venues/econ/ssrn.yaml`
    以带上 `quirks.topic_filter`）；缺该键时合成一份最小 spec，把请求参数塞进 `quirks`
    ——adapter 读配置的既有入口就是 quirks，这样测试用 `mock_platform` 也能被同一条
    路径驱动（`volumes`/`papers_per_issue`/`seed` 等直接从 venue 覆盖传入）。
    """

    def __init__(
        self,
        adapters: Mapping[str, SourceAdapter],
        *,
        venues: Mapping[str, VenueSpec] | None = None,
    ) -> None:
        self._adapters = dict(adapters)
        self._venues = dict(venues or {})

    def fetch(self, request: SourceRequest) -> Iterable[PaperStub]:
        adapter = self._adapters.get(request.source)
        if adapter is None:
            raise CrawlerError(
                ErrorClass.CONFIG,
                f"订阅源 {request.source!r} 无已注册 adapter"
                f"（已注册: {', '.join(sorted(self._adapters))}）",
            )
        hook = self._incremental_hook(adapter)
        if hook is not None:
            return list(hook(dict(request.params)))
        venue = self.venue_for(request)
        stubs: list[PaperStub] = []
        for ref in adapter.discover_timeline(venue, request.since):
            stubs.extend(adapter.enumerate_issue(venue, ref))
        return stubs

    @staticmethod
    def _incremental_hook(adapter: SourceAdapter) -> _IncrementalHook | None:
        """按 `_INCREMENTAL_HOOKS` 探测 adapter 的增量通道；无则 None（走默认路径）。"""
        for name in _INCREMENTAL_HOOKS:
            hook = getattr(adapter, name, None)
            if callable(hook):
                return cast("_IncrementalHook", hook)
        return None

    def venue_for(self, request: SourceRequest) -> VenueSpec:
        """该请求使用的 `VenueSpec`：注入的真实 spec 优先，否则按请求参数合成一份。

        合成 spec 的 `id` 取 `subs_<source>`（`^[a-z][a-z0-9_]*$` 合法），`quirks` =
        请求参数（值一律字符串，adapter 侧的 quirk 取值器自行转型）。它**不入库、不
        进 registry**，只是喂给 adapter 方法的一个值对象。
        """
        existing = self._venues.get(request.source)
        if existing is not None:
            return existing
        return VenueSpec(
            id=f"subs_{request.source}",
            kind="preprint_channel",
            names=VenueNames(full=f"subscription source {request.source}"),
            field=["cs_ai"],
            fulltext_source=request.source,
            quirks=dict(request.params),
        )


# ---------------------------------------------------------------------------
# 请求合成：静态下推参数 ⊕ 增量窗
# ---------------------------------------------------------------------------

# 需要**逐条展开成独立请求**的重复键（模块 docstring "重复键逐条展开"段）。
# 值进 URL path（crossref `/journals/{issn}/works`）或决定 feed 文件（nber
# `new{code}.xml`）的参数天然一次只能带一个。**openalex 的重复 `filter` 不在此列**
# ——那是 AND 关系、要合并进同一个 `filter=`（`compile._OPENALEX_NOTE` 明写），展开
# 反而会把"概念且类型"变成"概念或类型"两次请求。
_FANOUT_KEY: dict[str, str] = {"crossref": "issn", "nber": "program"}


def _params_without(params: Sequence[tuple[str, str]], key: str) -> tuple[tuple[str, str], ...]:
    return tuple((name, value) for name, value in params if name != key)


def _values_of(params: Sequence[tuple[str, str]], key: str) -> tuple[str, ...]:
    return tuple(value for name, value in params if name == key)


def _lower_bound_of(source: str, window: Sequence[tuple[str, str]]) -> str | None:
    """增量窗的下界日期（ISO `YYYY-MM-DD`）——`SourceRequest.since` 的取值来源。

    取窗里**第一个**参数的值并剥掉形态修饰：s2 的 `2026-07-19:`（单参数区间语法）剥
    尾冒号；arxiv 的 `[202607190000 TO 202607262359]` 不是 ISO 日期，故 arxiv 恒 None
    （其窗只以 `search_query` 内的范围项形态存在，adapter 从查询式自取）。无窗的源
    （nber）同样 None。
    """
    if source == "arxiv" or not window:
        return None
    raw = window[0][1].rstrip(":")
    return raw or None


def _compose_arxiv(
    step: PlanStep, window: Sequence[tuple[str, str]]
) -> tuple[tuple[tuple[str, str], ...], ...]:
    """arxiv：窗以 `submittedDate:[A TO B]` **AND 进同一个 `search_query`**。

    宿主形态出处 = `watermark.py` 模块 docstring 的"窗口参数的宿主形态"表：arxiv 的
    `submittedDate` 不是独立 URL 参数。`compile._wrap` 已保证复合查询式自带外层括号，
    故这里直接 ` AND ` 追加不会改变结合律（那条括号注释写的正是本行的前提）。
    """
    expression = next((value for name, value in step.pushdown if name == "search_query"), "")
    terms = [term for term in (expression, *(f"{name}:{value}" for name, value in window)) if term]
    if not terms:
        return ((),)
    return ((("search_query", " AND ".join(terms)),),)


def _compose_openalex(
    step: PlanStep, window: Sequence[tuple[str, str]]
) -> tuple[tuple[tuple[str, str], ...], ...]:
    """openalex：静态 `filter` 条目与窗的日期轴**逗号合并进单个 `filter=`**（AND 关系）。

    `compile._OPENALEX_NOTE` 明写"多条 filter 条目是 AND 关系（T5 以逗号拼进单个
    filter= 参数）"；`from_publication_date` 同样是 filter 轴的一项（`watermark.py`
    宿主形态表），故一并并入。非 filter 的静态参数（当前无）原样保留在前。
    """
    filters = [*_values_of(step.pushdown, "filter"), *(f"{n}:{v}" for n, v in window)]
    others = _params_without(step.pushdown, "filter")
    if not filters:
        return (others,)
    return ((*others, ("filter", ",".join(filters))),)


def _compose_flat(
    step: PlanStep, window: Sequence[tuple[str, str]]
) -> tuple[tuple[tuple[str, str], ...], ...]:
    """s2 / ssrn：窗是真参数或成对 filter 项，与静态参数平铺即可，无宿主合并。"""
    return ((*step.pushdown, *window),)


def _compose_fanout(
    step: PlanStep, window: Sequence[tuple[str, str]]
) -> tuple[tuple[tuple[str, str], ...], ...]:
    """crossref / nber：按 `_FANOUT_KEY` 的重复键**逐条**展开成独立请求。

    展开值为空（订阅未声明 issns/programs——正常解析路径不会出现，`SOURCE_FIELDS` 要求
    选择器非空）时退化为单条"只带窗"的请求，不返回空列表：返回零请求等于静默不拉这个源。
    """
    key = _FANOUT_KEY[step.source]
    rest = _params_without(step.pushdown, key)
    values = _values_of(step.pushdown, key)
    if not values:
        return ((*rest, *window),)
    return tuple(((key, value), *rest, *window) for value in values)


# 每源一个合成器（duck-typed 注册表，同 `compile._COMPILERS` 的形状与自断言纪律）。
_Composer = Callable[[PlanStep, Sequence[tuple[str, str]]], tuple[tuple[tuple[str, str], ...], ...]]

_COMPOSERS: dict[str, _Composer] = {
    "arxiv": _compose_arxiv,
    "openalex": _compose_openalex,
    "s2": _compose_flat,
    "ssrn": _compose_flat,
    "crossref": _compose_fanout,
    "nber": _compose_fanout,
}

SUPPORTED_SOURCES: frozenset[str] = frozenset(_COMPOSERS)


def build_requests(
    subscription: str, step: PlanStep, window: Sequence[tuple[str, str]] = ()
) -> tuple[SourceRequest, ...]:
    """把一个 `PlanStep` ⊕ 该源本次的增量窗合成为**逐条独立**的 `SourceRequest`。

    恒返回至少一条请求（零请求 = 静默不拉该源）；重复键的展开规则见 `_FANOUT_KEY`。
    未知源 → `CrawlerError(CONFIG)`（正常路径上 T1 解析器/T2 编译器已挡住，这里兜住
    绕过它们直接构造 `PlanStep` 的调用方，避免 KeyError 这种无信息量的崩法）。
    """
    composer = _COMPOSERS.get(step.source)
    if composer is None:
        raise CrawlerError(
            ErrorClass.CONFIG,
            f"订阅源 {step.source!r} 无请求合成器（支持: {', '.join(sorted(SUPPORTED_SOURCES))}）",
        )
    since = _lower_bound_of(step.source, window)
    return tuple(
        SourceRequest(
            subscription=subscription,
            source=step.source,
            params=params,
            since=since,
            note=step.note,
        )
        for params in composer(step, window)
    )


# ---------------------------------------------------------------------------
# 订阅加载
# ---------------------------------------------------------------------------


def load_subscriptions(directory: Path, repo: SubscriptionRepo) -> list[Subscription]:
    """加载 `directory` 顶层全部订阅并 upsert 入库，返回加载结果（按文件名序）。

    文件是**权威**、库是运行期状态：`SubscriptionRepo.upsert` 只更新 `query_json`/
    `guard_json`，watermark/last_run_at 原样保留（其 docstring 明示）——改订阅内容不会
    把增量游标清零。任一文件不合法 → `SubscriptionInvalid` 整体拒载（`load_subscriptions_dir`
    的 fail-loud 语义，plan §4 T5 已裁决歧义④"`--all` 遇任一坏订阅整体响亮拒载"，
    报错消息带出错文件路径）。
    """
    subscriptions = load_subscriptions_dir(directory)
    for subscription in subscriptions:
        repo.upsert(subscription)
    return subscriptions


def resolve_subscription(name: str, repo: SubscriptionRepo) -> Subscription:
    """按名字取订阅（库内），不存在 → `CrawlerError(CONFIG)`（CLI 归退出码 2）。"""
    subscription = repo.get(name)
    if subscription is None:
        known = repo.list_names()
        raise CrawlerError(
            ErrorClass.CONFIG,
            f"未知订阅 {name!r}"
            + (f"（已登记: {', '.join(known)}）" if known else "（当前一个订阅都没有登记）"),
        )
    return subscription


# ---------------------------------------------------------------------------
# 运行上下文
# ---------------------------------------------------------------------------


@dataclass
class WatchContext:
    """一次 watch 运行需要的全部依赖（显式注入，便于离线测试替换任一件）。

    `registry`/`queue` 只在派生取回链任务时才用到（`ingest: metadata+pdf`）；纯
    metadata 订阅传 None 亦可运行。`venues` 按**源 id** 索引，同时喂给 T2 编译器
    （ssrn 的 `quirks.topic_filter`）与 `AdapterFetcher`。
    """

    db: Database
    repo: Repo
    subs_repo: SubscriptionRepo
    fetcher: SourceFetcher
    registry: VenueRegistry | None = None
    queue: TaskQueue | None = None
    venues: Mapping[str, VenueSpec] = field(default_factory=dict)
    report_root: Path = DEFAULT_REPORT_ROOT


@dataclass
class _SourceOutcome:
    """一个源跑完后的中间产物（编排内部件，不外泄）。"""

    seen: int = 0
    kept: list[FilteredPaper] = field(default_factory=list)
    watermark_seen: list[str] = field(default_factory=list)
    failure: FailureEvent | None = None


# ---------------------------------------------------------------------------
# 编排主体
# ---------------------------------------------------------------------------


def _today(now: date | None) -> date:
    return now if now is not None else datetime.now(UTC).date()


def _watch_id(stub: PaperStub) -> str:
    """id 差分策略用的稳定条目 id：首个 identifier 的 `"<scheme>:<value>"`。

    `PaperStub.identifiers` 契约"至少 1 个"（`types.py`）；万一为空则退回标题——差分
    退化为按标题去重，比抛异常中断整轮 watch 保守。
    """
    if stub.identifiers:
        scheme, value = stub.identifiers[0]
        return f"{scheme}:{value}"
    return f"title:{stub.title}"


def _entry_url(stub: PaperStub) -> str:
    """条目链接：`meta['url']` 优先 → DOI resolver → 空串（日报渲染成 "-"）。"""
    for key, value in stub.meta:
        if key == META_KEY_URL and value:
            return value
    for scheme, value in stub.identifiers:
        if scheme == "doi" and value:
            return f"{_DOI_RESOLVER}{value}"
    return ""


def _entry_categories(stub: PaperStub) -> tuple[str, ...]:
    """源侧分类（`meta['categories']` 逗号分隔）；不产该键的源如实为空，不臆造分类。"""
    for key, value in stub.meta:
        if key == META_KEY_CATEGORIES:
            return tuple(part.strip() for part in value.split(",") if part.strip())
    return ()


def _to_entry(source: str, kept: FilteredPaper) -> ReportEntry:
    stub = kept.stub
    return ReportEntry(
        title=stub.title,
        authors=stub.authors,
        url=_entry_url(stub),
        matched_rules=kept.matched_rules,
        source=source,
        categories=_entry_categories(stub),
    )


def _scoped_predicates(step: PlanStep) -> tuple[str, ...]:
    """该源的**源专属**补偿谓词（点分名）——通用三谓词由 `LocalFilter` 路径承担。"""
    return tuple(name for name in step.local_predicates if is_source_scoped_predicate(name))


def _log_dropped_unknown_year(subscription: str, source: str, stubs: Sequence[PaperStub]) -> int:
    """声明 `min_year` 下 `year is None` 的条目计数 → obslog INFO（plan §4 T5 裁决⑩）。

    `filter_papers` 对"年份未知"是**排除**（其模块 docstring 的刻意取舍），而排除掉的
    条目不会出现在返回值里——用户在日报上只会看到"新增变少了"，看不到原因。故在此单独
    数一道并落 INFO。口径是**上界**：这些条目里可能有一部分本来也会被正则规则排除掉，
    此处不做归因拆分（那需要把 T3 的判定逻辑复制第二份，正是本模块要避免的）。

    不进 `RunSummary`——那是 T1 冻结件，本卡只可追加不可改结构，而可观测性用 obslog
    这条既有通道就已足够（Global Constraints §7 结构化日志）。
    """
    dropped = sum(1 for stub in stubs if stub.year is None)
    if dropped:
        log_event(
            "INFO",
            f"watch[{subscription}]: {source} 有 {dropped} 条因 year 缺失被 min_year 排除"
            "（计数为上界：其中可能有条目同时命中其他排除规则）",
            stage="watch",
            venue=source,
        )
    return dropped


def _run_source(
    context: WatchContext,
    subscription: Subscription,
    step: PlanStep,
    watermark: Watermark,
    *,
    day: date,
) -> _SourceOutcome:
    """跑一个源：合成请求 → 拉取 → id 差分 → 本地过滤。失败收进 `_SourceOutcome.failure`。

    **全程完整消费**（`list(...)` 物化）：`SourceFetcher.fetch` 允许返回生成器，而
    `watermark.advance` 明确要求 `Sequence`（多次遍历，其 docstring 的陷阱注记），
    dry-run 亦须走完整条链（模块 docstring）。两条理由指向同一件事——早早物化。
    """
    source = step.source
    outcome = _SourceOutcome()
    try:
        window = window_params(watermark, source, now=day)
        requests = build_requests(subscription.name, step, window)
        stubs: list[PaperStub] = []
        for request in requests:
            stubs.extend(context.fetcher.fetch(request))
    except CrawlerError as exc:
        log_event(
            "WARNING",
            f"watch[{subscription.name}]: 源 {source} 拉取失败: {exc}",
            stage="watch",
            venue=source,
            error_class=exc.error_class.value,
        )
        outcome.failure = FailureEvent(
            source=source, error_class=exc.error_class.value, message=str(exc)
        )
        return outcome

    outcome.seen = len(stubs)
    strategy = strategy_for(source)
    if isinstance(strategy, IdSetDiff):
        # id 差分类源（nber）：窗内先做增量差分——这就是它的增量机制本身，
        # 与后面的对库去重、identifier 主键是三道独立的网（`IdSetDiff` docstring）。
        seen_ids = [_watch_id(stub) for stub in stubs]
        fresh = frozenset(strategy.new_ids(watermark.state_for(source), seen_ids))
        stubs = [stub for stub in stubs if _watch_id(stub) in fresh]
        outcome.watermark_seen = seen_ids  # 传**全部** id（含重叠），非差分结果
    else:
        # 日期类源：只喂**确实带日期**的条目——把 None/空串塞给 `_parse_date` 会
        # `WatermarkInvalid` 炸掉整轮；缺日期时不推进（下次窗更宽）是保守侧。
        outcome.watermark_seen = [stub.pub_date for stub in stubs if stub.pub_date]

    if subscription.filters.min_year is not None:
        _log_dropped_unknown_year(subscription.name, source, stubs)
    outcome.kept = filter_papers(
        stubs, subscription.filters, extra_predicates=_scoped_predicates(step)
    )
    return outcome


def _dedupe_keeping_rules(kept: Sequence[FilteredPaper], db: Database) -> list[FilteredPaper]:
    """对库去重，但保住每条的 `matched_rules`（`guard` 只认 `PaperStub`）。

    `dedupe_against_library` 保持输入相对序且返回**同一批对象**（不复制），故按对象
    身份顺序对齐即可还原 `FilteredPaper`——同批内的重复 stub 也不会错配。
    """
    result = dedupe_against_library([item.stub for item in kept], db)
    survivors: list[FilteredPaper] = []
    cursor = 0
    for item in kept:
        if cursor < len(result.new) and item.stub is result.new[cursor]:
            survivors.append(item)
            cursor += 1
    return survivors


def _distribution_of(
    subscription_name: str, entries: Sequence[ReportEntry], *, guard_limit: int
) -> tuple[tuple[tuple[str, str, int], ...], str]:
    """熔断时的过载分布三元组 + 收窄建议句（plan §4 T5 已裁决歧义⑥）。

    `guard.build_overload_report` 的 `by_source`/`by_category` 两轴各自打上 axis 标记
    后拼成一个扁平序列喂 `RunSummary.distribution`（T6 按 axis 过滤拆回两张表）；
    `suggestion` 单独返回，供 CLI 打一行熔断简报。`narrowing_hints` 留空——收窄句由
    T6 自己从 distribution 现算（`RunSummary` docstring 已述该分工）。
    """
    report = build_overload_report(subscription_name, entries, guard_limit=guard_limit)
    distribution = (
        *(("source", label, count) for label, count in report.by_source),
        *(("category", label, count) for label, count in report.by_category),
    )
    return distribution, report.suggestion


def overload_brief(summary: RunSummary) -> str | None:
    """熔断简报一行（`OverloadReport.suggestion`）；未熔断 → None。

    只拿得到 `RunSummary` 的消费方（CLI stdout）用它——从 `entries` 现算，与 `run_watch`
    内部装配 `distribution` 时走的是**同一个** `guard.build_overload_report`，不另起一套
    建议算法（plan §4 T5 已裁决歧义⑥：suggestion 打 CLI stdout，日报里的收窄句归 T6）。
    """
    if not summary.truncated:
        return None
    report = build_overload_report(
        summary.subscription, summary.entries, guard_limit=summary.guard_limit
    )
    return report.suggestion


def _venue_for_source(registry: VenueRegistry, source: str) -> VenueSpec | None:
    """该源担任 `fulltext_source` 的 venue（id 序第一个）——派生取回链任务的路由落点。"""
    return next((spec for spec in registry.all() if spec.fulltext_source == source), None)


def _derive_fetch_tasks(
    context: WatchContext,
    subscription: Subscription,
    ingested: Sequence[tuple[str, str]],
) -> int:
    """按 `auto_fetch_limit` 派生取回链任务（`resolve` 入口），返回派生数。

    `ingested` = `[(source, paper_id), ...]`（入库序）。派生前把 paper 绑定到该源对应
    的 venue（`_stage_resolve` 读 `paper.venue_id` 路由）；找不到 venue 或未注入
    registry/queue → WARNING + 跳过该源（响亮，不静默产出永远 BLOCKED 的任务）。
    只计 `enqueued`：`duplicate`/`fresh_skip` 是既有任务，不是本次新派生的工作。
    """
    limit = subscription.actions.auto_fetch_limit
    if subscription.actions.ingest != "metadata+pdf" or limit <= 0:
        return 0
    if context.registry is None or context.queue is None:
        log_event(
            "WARNING",
            f"watch[{subscription.name}]: ingest=metadata+pdf 但未注入 registry/queue，"
            "本次不派生取回链任务",
            stage="watch",
        )
        return 0

    derived = 0
    warned: set[str] = set()
    venue_ids: dict[str, str | None] = {}
    for source, paper_id in ingested[:limit]:
        if source not in venue_ids:
            spec = _venue_for_source(context.registry, source)
            if spec is not None:
                context.repo.upsert_venue(spec)  # FK 前提：venue 行存在（同 grab 先例）
            venue_ids[source] = spec.id if spec is not None else None
        venue_id = venue_ids[source]
        if venue_id is None:
            if source not in warned:
                warned.add(source)
                log_event(
                    "WARNING",
                    f"watch[{subscription.name}]: 源 {source} 没有以它为 fulltext_source 的 "
                    "venue，无法路由取回链——本次不派生该源的任务",
                    stage="watch",
                    venue=source,
                )
            continue
        context.repo.bind_paper_venue(paper_id, venue_id)
        if context.queue.enqueue("resolve", venue_id, {"paper": paper_id}).status == "enqueued":
            derived += 1
    return derived


def run_watch(
    context: WatchContext,
    subscription: Subscription,
    *,
    dry_run: bool = False,
    now: date | None = None,
    report_path: str | None = None,
) -> RunSummary:
    """跑一次订阅 watch，返回 `RunSummary`（日报渲染与落盘由调用方做）。

    `report_path` 由调用方**先算好再传进来**（plan §4 T5 已裁决歧义③）：
    `SubscriptionRepo.record_run` 是 INSERT-only、没有回填接口，所以"先落记录再算日报
    路径"会永久留下一批 `report_path IS NULL` 的行。dry-run 下该值仍进 `RunSummary`
    （日报照渲染回显），只是不落库。

    `now` 是**唯一时钟入口**（测试/固定时间线注入）——转手传给 T4 的 `window_params`/
    `advance`，本模块不另外调 `datetime.now`。
    """
    started_at = utcnow_iso()
    day = _today(now)
    reset_predicate_warnings()  # "每 run 每源一条"提示的记账复位（T3 兜底提示）

    plan: CompiledPlan = compile_subscription(subscription, venues=dict(context.venues))
    watermark = Watermark.parse(context.subs_repo.read_watermark(subscription.name))

    seen_count = 0
    failures: list[FailureEvent] = []
    kept_by_source: list[tuple[str, FilteredPaper]] = []
    advanced = watermark
    succeeded_sources = 0

    for step in plan.steps:
        outcome = _run_source(context, subscription, step, watermark, day=day)
        if outcome.failure is not None:
            failures.append(outcome.failure)
            continue
        succeeded_sources += 1
        seen_count += outcome.seen
        kept_by_source.extend((step.source, item) for item in outcome.kept)
        advanced = advance(advanced, step.source, outcome.watermark_seen, now=day)

    # 对库去重（`guard.dedupe_against_library` 为假时整批直通——用户显式要重复看）。
    kept_items = [item for _, item in kept_by_source]
    if subscription.guard.dedupe_against_library:
        survivors = _dedupe_keeping_rules(kept_items, context.db)
        alive = {id(item) for item in survivors}
        kept_by_source = [pair for pair in kept_by_source if id(pair[1]) in alive]

    entries = tuple(_to_entry(source, item) for source, item in kept_by_source)
    new_count = len(entries)
    guard_limit = subscription.guard.max_new_per_run
    truncated = is_truncated(new_count, guard_limit)

    distribution: tuple[tuple[str, str, int], ...] = ()
    if truncated:
        distribution, suggestion = _distribution_of(
            subscription.name, entries, guard_limit=guard_limit
        )
        log_event("WARNING", f"watch[{subscription.name}]: {suggestion}", stage="watch")

    if truncated:
        outcome_kind = WatchOutcome.TRUNCATED
    elif failures and succeeded_sources == 0:
        outcome_kind = WatchOutcome.FAILED
    else:
        outcome_kind = WatchOutcome.OK

    ingested_count = 0
    fetched_count = 0
    if outcome_kind is WatchOutcome.OK and not dry_run:
        engine = MergeEngine(context.repo)
        ingested: list[tuple[str, str]] = []
        entries_with_ids: list[ReportEntry] = []
        for entry, (source, item) in zip(entries, kept_by_source, strict=True):
            result = engine.ingest(item.stub, source=MERGE_SOURCE[source])
            ingested.append((source, result.paper_id))
            entries_with_ids.append(
                ReportEntry(
                    title=entry.title,
                    authors=entry.authors,
                    url=entry.url,
                    matched_rules=entry.matched_rules,
                    source=entry.source,
                    categories=entry.categories,
                    paper_id=result.paper_id,
                )
            )
        entries = tuple(entries_with_ids)
        ingested_count = len(ingested)
        fetched_count = _derive_fetch_tasks(context, subscription, ingested)
        # watermark 只在真正入库的这条路径上提交（熔断/失败/dry-run 三条理由各自独立，
        # `watermark.advance` docstring 的"逐条判"纪律）；`restrict_to` 摘掉已退订的源。
        context.subs_repo.write_watermark(
            subscription.name, advanced.restrict_to(subscription.source_names()).to_dict()
        )
        context.subs_repo.touch_last_run(subscription.name, at=started_at)

    summary = RunSummary(
        subscription=subscription.name,
        started_at=started_at,
        finished_at=utcnow_iso(),
        outcome=outcome_kind,
        dry_run=dry_run,
        entries=entries,
        seen_count=seen_count,
        new_count=new_count,
        ingested_count=ingested_count,
        fetched_count=fetched_count,
        library_total=_library_total(context.db),
        guard_limit=guard_limit,
        failures=tuple(failures),
        report_path=report_path,
        distribution=distribution,
    )

    if not dry_run:
        context.subs_repo.record_run(
            name=subscription.name,
            started_at=started_at,
            new_count=new_count,
            fetched_count=fetched_count,
            truncated=summary.truncated,
            report_path=report_path,
        )
    return summary


def _library_total(db: Database) -> int:
    """累计库存（日报第二要素）= `paper` 表总行数。

    直查 `Database`（只读聚合，无跨表写语义）——同 `cli._doi_universe` 的既有分工：
    `repo.py` 是冻结件，不为一句 COUNT 新增仓储方法。口径是**全库**而非"本订阅入库
    的"：`paper` 行不带订阅归属（订阅不是聚合根之外的实体），且日报"累计库存"要回答
    的正是"我这个库现在有多少篇"。
    """
    return int(db.query("SELECT COUNT(*) AS n FROM paper")[0]["n"])


def run_watch_all(
    context: WatchContext,
    subscriptions: Sequence[Subscription],
    *,
    dry_run: bool = False,
    now: date | None = None,
) -> tuple[list[RunSummary], Path]:
    """串行跑多个订阅，返回 `(全部 RunSummary, 日报路径)`。

    日报路径**先算**（多订阅合并一份 `daily-YYYY-MM-DD.md`，design/09 §6 第 3 条）再
    逐个跑——每条 run 记录的 `report_path` 因此都能填上（`record_run` 是 INSERT-only，
    plan §4 T5 已裁决歧义③）。串行而非并发：护栏与 watermark 都是逐订阅的状态，串行
    让"第 n 个订阅熔断"不影响前 n-1 个已提交的水位，也让日报顺序确定可 golden。
    """
    day = _today(now)
    path = daily_report_path(day, root=context.report_root)
    summaries = [
        run_watch(context, subscription, dry_run=dry_run, now=now, report_path=str(path))
        for subscription in subscriptions
    ]
    return summaries, path


def daily_report_path(day: date, *, root: Path | None = None) -> Path:
    """日报落盘路径：`<root>/daily-YYYY-MM-DD.md`（root 缺省 `docs/reports/watch/`）。"""
    return (root if root is not None else DEFAULT_REPORT_ROOT) / f"daily-{day.isoformat()}.md"


def write_daily_report(summaries: Sequence[RunSummary], path: Path, *, day: date) -> str:
    """渲染日报并落盘（同日重跑覆盖——日报是当日快照，不是事件日志），返回 markdown 文本。

    渲染纯函数归 T6（`subs.report.render_daily`），本函数只负责建目录与写文件。
    **dry-run 不调用本函数**（`--dry-run` 只回显 stdout，plan §4 T5 dry-run 语义）。
    """
    text = render_daily(summaries, date=day.isoformat())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return text


def exit_code_for(summaries: Sequence[RunSummary]) -> int:
    """退出码判据（模块 docstring "退出码"段）：1（有失败）> 3（有熔断）> 0。

    "有失败"取 `FailureEvent` 的存在而非 `outcome is FAILED`：部分源失败时整轮仍
    `OK`（成功源照常入库），但用户需要一个非零信号知道"这次少收了一个源"——静默 0
    会让一个长期挂掉的源永远无人发现。
    """
    if any(summary.failures for summary in summaries):
        return 1
    if any(summary.truncated for summary in summaries):
        return 3
    return 0


__all__ = [
    "DEFAULT_REPORT_ROOT",
    "MERGE_SOURCE",
    "SUPPORTED_SOURCES",
    "AdapterFetcher",
    "SourceFetcher",
    "SourceRequest",
    "WatchContext",
    "build_requests",
    "daily_report_path",
    "exit_code_for",
    "load_subscriptions",
    "overload_brief",
    "resolve_subscription",
    "run_watch",
    "run_watch_all",
    "write_daily_report",
]
