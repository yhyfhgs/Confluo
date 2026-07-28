"""查询编译器：`Subscription` → `CompiledPlan`（Phase 6 T2；design/09 §3 能力映射表）。

每个源一个编译器，把该源的 `SourceSelector` 翻译成**原生查询参数**（`PlanStep.pushdown`），
并把该源下推不了的条件标成**本地补偿谓词**（`PlanStep.local_predicates`）。原则句
（design/09 §3 末）："下推尽可能多以省流量，但正确性以本地过滤为准"——故凡是拿不准能否
精确下推的条件，一律落本地补偿，**绝不臆造源侧语法**去换取一次省流量的请求。

## 能力映射（design/09 §3 表 = 权威规格；语法出处见各编译器 docstring）

| 源 | 下推 | 本地补偿 |
|---|---|---|
| arxiv | `arxiv_category` 逐分类 fan-out；`query` 无下推面 | 仅 `filters` 三谓词 |
| crossref | 每 issn 一条（`/journals/{issn}/works`） | 仅 `filters` 三谓词（无关键词场景） |
| nber | 每 program 一条（feed 路由归 T7） | 仅 `filters` 三谓词 |
| ssrn | **无**（聚合源无 network/eJournal 维度） | `filters` 三谓词 + `ssrn.topic_filter` |

**openalex / s2 两行已删**（R2b/P0-4）：二者 `capabilities = Capability(0)`（enrich-only，
aggregators.md §1），watch 侧结构性不可达——编译器把它们译成一份漂亮的 `filter=` /
`venue=` 参数，`AdapterFetcher` 转头就在 `discover_timeline` 上吃
`CapabilityNotSupported`。留着编译器只会让"配置写得出、编译过得去、一跑必炸"这条路
继续存在，故连同 `_COMPILERS` 条目一并摘除；源白名单侧的收缩见
`model.SOURCE_FIELDS` / `model.ENRICH_ONLY_SOURCES`。要恢复得先真的实现两源的
DISCOVER/ENUMERATE 时间轴（功能扩展，归 R4 裁决），而不是把编译器搬回来。

arxiv 行两栏都要看细则（`_compile_arxiv` docstring）：分类条目由 T5 逐条展开成独立请求
并成对补上派生的 `arxiv_set`（经 venue quirks 进 OAI `set=`）；`query` 的关键词布尔式
**无下推通道**（OAI-PMH 无关键词能力），但自 Phase 7 T9 起有了参数化本地补偿谓词
`arxiv.query_bool`（挂 `PlanStep.predicate_params`，`filter.PREDICATE_REGISTRY` 新登记
的构造器）——该谓词标记不进 `local_predicates`（那是免参谓词的通道），而是经
`subs/watch.py` 的 `_scoped_predicates`/`filter_papers(..., predicate_params=...)`
接入，在真实 `subs watch` 运行中对标题/摘要真实求值（T9 同卡追加改动接通，不是
留给后续卡的空壳）。

## 三条不变量（下游可依赖）

1. **`pushdown` 条目顺序 = `model.SOURCE_FIELDS` 的字段声明序**——同一订阅恒得同一
   计划（确定性输出，快照可测）；重复键（多 issn / 多 program / 多 filter 轴）保序保重复，
   这正是 `PlanStep.pushdown` 用元组而非 dict 的原因。
2. **`LocalFilter` 的三谓词恒进全源** `local_predicates`（声明了哪几条就进哪几条，
   按 `LocalFilter` 字段序）：正则与 `min_year` 没有任何源被允许下推——`min_year` 尤其
   **不占日期参数槽位**（那是 T4 增量窗的位置，见下"接缝"），两者混用会让"过滤下界"与
   "增量上界"互相覆盖。
3. **源专属补偿谓词一律 `"<source>.<name>"`**（`subs/types.py` 约定），当前只有一条：
   `ssrn.topic_filter`。

## 只标记**有实现**的补偿谓词（controller 裁决 2026-07-26）

`local_predicates` 是 T3/T5 的执行契约，不是愿望清单：标一条 T3 registry 里没有的谓词，
T5 集成时会直接 `ValueError` 崩掉整轮 watch。当前唯一在列者——

- **`ssrn.topic_filter`：谓词有实现、只缺信号** → **保留标记**。执行层
  （`adapters/ssrn/parse.py::topic_field_matches`）在，缺的是 `stub.meta['openalex_field']`
  这个 enrich 信号；信号缺失时的兜底语义由 T3 定为 pass-through 放行 + obslog 一次性提示。

（同一裁决的另一半"openalex 名称型 concepts 连实现都没有 → 降级 note-only"已随
openalex 编译器一并删除，见上文能力映射表下方的说明。）

## 接缝：日期窗不在本模块（plan §4 T2 接缝裁决①）

本模块只产**静态参数**。运行时的增量窗口参数由 T4（watermark）独立产出、T5 合成——
二者结构同构（都是 `(key, value)` 元组），拼接即可。各源日期参数名见
`DATE_WINDOW_PARAMS`（单一同源，T4/T5 直接消费，不必再翻文档）。

`subs/__init__.py` 的导出面留待 T5 集成时统一补（本卡不动）。
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import replace
from typing import NoReturn

from paper_crawler.errors import CrawlerError, ErrorClass, SubscriptionInvalid
from paper_crawler.subs.model import (
    LocalFilter,
    SourceSelector,
    Subscription,
    unsupported_source_message,
)
from paper_crawler.subs.types import (
    ARXIV_CATEGORY_PARAM,
    DATE_WINDOW_PARAMS,
    LOCAL_PREDICATE_EXCLUDE_REGEX,
    LOCAL_PREDICATE_MIN_YEAR,
    LOCAL_PREDICATE_TITLE_REGEX_ANY,
    CompiledPlan,
    PlanStep,
    normalize_arxiv_query,
    wrap_arxiv_query,
)
from paper_crawler.types import VenueSpec

# --- T4/T5 接缝：各源日期窗参数名 -------------------------------------------

# 本模块不产日期值（接缝裁决①），也不再**持有**槽位名表：`DATE_WINDOW_PARAMS` 已迁至
# 叶子模块 `subs/types.py`（T2/T4/T5 三方消费，住在任一消费方都会让另两方反向依赖）。
# 此处保留 re-export，既有 `from paper_crawler.subs.compile import DATE_WINDOW_PARAMS`
# 的调用面逐字不变（`__all__` 亦不变）。表的逐源出处注释随表一并迁走，见 types.py。

# --- 取值域校验（DSL/venue 值进 URL 前的最后一道关）--------------------------

# 用户在 DSL 里手写日期窗 = 与 T4 的增量窗互相覆盖（`model.SOURCE_FIELDS` 注释明文
# "日期窗不在 DSL 里"）。名单从 `DATE_WINDOW_PARAMS` **反向导出**——与"编译产物不含
# 日期窗"的断言同源，加一个源就自动多守一个名字，两处不会各记一份。
_DATE_WINDOW_NAMES: frozenset[str] = frozenset(
    name.lower() for names in DATE_WINDOW_PARAMS.values() for name in names
)

# ISSN 形态：`NNNN-NNNC`（末位校验位可为 X）。ISSN 直接进 `/journals/{issn}/works` 的
# **URL path**，形态没关就是把用户的笔误原样拼进请求路径——这是最后一道关。
_ISSN_PATTERN = re.compile(r"^\d{4}-\d{3}[\dxX]$")

# --- 源专属补偿谓词与 venue 接线常量 -----------------------------------------

# ssrn econ/fin 主题**近似**过滤（venue YAML `quirks.topic_filter`，检查单 #10）。
# 谓词标记只记"这条要本地补偿"，取值（如 `econ_fin`）落 `note`——T3/T5 需要具体集合时
# 从 venue 读（`adapters/ssrn/parse.py::ECON_FIN_FIELDS` 是唯一权威集合）。
SSRN_TOPIC_FILTER_QUIRK = "topic_filter"
PREDICATE_SSRN_TOPIC_FILTER = "ssrn.topic_filter"

# arxiv `query` 布尔式的参数化补偿谓词（Phase 7 T9；plan §4 T9"参数化谓词签名"
# 冻结件）。谓词名同 `filter.ARXIV_QUERY_BOOL`——两处各自独立定义同一字面量，沿用
# 本文件 `PREDICATE_SSRN_TOPIC_FILTER`/`filter.SSRN_TOPIC_FILTER` 的既有先例（不
# 建一个跨模块 import 只为共享一个字符串常量）。
PREDICATE_ARXIV_QUERY_BOOL = "arxiv.query_bool"

# `quirks.topic_filter` 的合法取值域：目前**只有** `econ_fin` 有实现（= `ECON_FIN_FIELDS`
# 是全库唯一落地的主题集）。写了别的值（拼错的 `econ-fin`、臆造的集合名）→ CONFIG 响亮，
# 不静默当成"某个不存在的集合"跑出一份空清单。新增集合须同时落 parse.py 与本白名单。
SSRN_TOPIC_FILTER_VALUES: frozenset[str] = frozenset({"econ_fin"})

# --- 编译期备注（进 `PlanStep.note`，供日报/诊断呈现，不参与判定）-------------

_ARXIV_NOTE = (
    "arxiv categories → **逐分类 fan-out 下推**：每条请求带一个 arxiv_category + 派生的 "
    "arxiv_set，经 venue quirks 通道进 OAI-PMH 的 set= 与客户端 primary_category 过滤"
    "（T5 展开；请求量 = N 分类 × M 月桶，每个分类独立收割其 archive 的 set）；"
    "query → 编译为参数化本地补偿谓词 arxiv.query_bool（Phase 7 T9；挂 "
    "predicate_params，不进 pushdown——OAI-PMH 无关键词查询能力，下推通道不存在）："
    "范围=ti/abs 字段 + AND/OR/ANDNOT + 引号短语；经 subs/watch.py 的 "
    "_scoped_predicates/filter_papers(predicate_params=...) 接入，在真实 subs watch "
    "运行中真实生效（非仅编译产物）——9 个 preset 的 filters.title_regex_any 镜像"
    "继续叠加执行（防御纵深，决策④，非被取代）；"
    "增量窗由 T4 产出、T5 经 SourceRequest.since 下推为月桶起点"
)

_CROSSREF_NOTE = (
    "crossref 完整下推（无关键词场景）：每个 issn 一次 /journals/{issn}/works；"
    "增量窗由 T4 以 filter=from-pub-date/until-pub-date 注入"
)

_NBER_NOTE = (
    "nber programs 下推为参数形态（每 program 一条）；feed 路由归 T7"
    "（back.nber.org/rss/new{code}.xml，实证 feed 清单见 adapters/nber/rss.py，nber.md §3.4）；"
    "无日期参数——增量走 RSS id 集合差分（T4/T7 卡）"
)

_SSRN_NOTE_HEAD = "ssrn 聚合源无 network/eJournal 精确过滤维度（ssrn.md §3）→ 无下推参数"

_SSRN_NOTE_TAIL = (
    "；关键词类条件全量本地补偿；"
    "枚举窗由 T4 以 filter=from-created-date/until-created-date 注入（内部 crossref created 轴）"
)

# --- 报错出口（沿 `model._fail` 的"<定位> —— <消息>"格式，CLI 可直接指向出错的行）------


def _invalid(source: str, field: str, message: str, *, index: int | None = None) -> NoReturn:
    """编译期拒载：`SubscriptionInvalid`（CONFIG 类 / 退出码 2），`detail` 存字段定位串。"""
    path = f"sources.{source}.{field}" + ("" if index is None else f"[{index}]")
    raise SubscriptionInvalid(f"{path} —— {message}", detail=path)


def _reject_date_window(text: str, *, source: str, field: str) -> None:
    """文本里出现任一日期窗参数名 → 拒载（`_DATE_WINDOW_NAMES` 反向导出，全源可复用）。

    用户手写 `submittedDate:[…]` 会与 T4 注入的增量窗**同时**出现在一条 `search_query` 里：
    两个日期条件相与，实际收到的是二者交集——订阅看着在跑，却一直漏收。宁可拒载。
    """
    lowered = text.lower()
    for name in sorted(_DATE_WINDOW_NAMES):
        if name in lowered:
            _invalid(
                source,
                field,
                f"不得手写日期窗 {name!r}（日期窗不在 DSL 里：增量窗由 watermark 注入，"
                f"design/09 §5 / model.SOURCE_FIELDS 注释）",
            )


# arxiv `query` 布尔式的归一/包裹（`normalize_arxiv_query`/`wrap_arxiv_query`）与解析
# （`parse_arxiv_query`）自 Phase 7 T9 起迁至叶子模块 `subs/types.py`——`model.py`
# 早验语法 / 本模块产出 `predicate_params` 值 / `filter.py` 求值三方共同消费，住在
# 任一方都会让另两方反向依赖（同 `DATE_WINDOW_PARAMS` 的既有守法）。逻辑本身逐字
# 未变，只是搬家；本模块从 `subs.types` import 需要的两个公开函数。

# --- 通用：本地补偿谓词 -----------------------------------------------------


def local_predicates_of(filters: LocalFilter) -> tuple[str, ...]:
    """`filters` 里**已声明**的谓词标记（按 `LocalFilter` 字段序）——全源共有的补偿面。

    没有任何源能下推正则；`min_year` 亦刻意不下推（日期参数槽位归 T4 的增量窗，
    模块 docstring 不变量 2）。未声明的字段不进列表——`LocalFilter.is_empty()` 时返回空元组，
    此时"下推 == 全部条件"。
    """
    predicates: list[str] = []
    if filters.title_regex_any:
        predicates.append(LOCAL_PREDICATE_TITLE_REGEX_ANY)
    if filters.exclude_regex:
        predicates.append(LOCAL_PREDICATE_EXCLUDE_REGEX)
    if filters.min_year is not None:
        predicates.append(LOCAL_PREDICATE_MIN_YEAR)
    return tuple(predicates)


# --- per-source 编译器（duck-typed 注册表，plan §4 T2 已裁决歧义①）-----------


def _compile_arxiv(selector: SourceSelector, venue: VenueSpec | None) -> PlanStep:
    """arxiv：`categories` → 逐分类 `arxiv_category` 条目；`query` → 参数化本地补偿
    谓词（Phase 7 T9；plan §4 T9"参数化谓词签名"冻结件，替代此前"仅诊断呈现"的纯
    `search_query` pushdown 串——AC-6 验收记录 §4 第 6 条记录的缺口）。

    - **分类**：每个分类一条 `(ARXIV_CATEGORY_PARAM, category)` 重复键条目（保序保重复），
      由 T5 (`watch._compose_arxiv`) 逐条展开成独立请求并成对补上派生的 `arxiv_set`。
      这是它**真实的**下达通道：两个键经 `AdapterFetcher.venue_for` 并进 venue `quirks`
      后正是 `adapters/arxiv/adapter.py::_oai_target` 读的键（键名同源见 `subs/types.py`
      的 `ARXIV_CATEGORY_PARAM`/`ARXIV_SET_PARAM` 注释）。
    - **查询式**：用户的字段级布尔式，经 `types.normalize_arxiv_query`/`wrap_arxiv_query`
      归一后，作为**订阅级参数**挂到 `PlanStep.predicate_params`（键
      `PREDICATE_ARXIV_QUERY_BOOL = "arxiv.query_bool"`）。`filter.PREDICATE_REGISTRY`
      新登记的构造器据此参数构造一个真正会被求值的 `PaperStub -> bool` 本地补偿谓词
      （范围=ti/abs 字段 + AND/OR/ANDNOT + 引号短语，决策⑤ YAGNI；语法出处 =
      site-survey/arxiv.md「关键机制」段）。语法非法在**订阅加载期**已被 `model.py`
      的 `_require_arxiv_query_syntax` 挡下，故这里可以假定 `selector.query` 已是
      语法合法的表达式。

    **不再把 `query` 塞进 `pushdown`**（本次修复替代的旧形态）：`search_query` 参数
    从未被真实下达（OAI-PMH 无关键词能力，`watch.py`"下达不了的"参数表恒含它），旧
    实现把归一后的查询式塞进这个死胡同纯属诊断展示；现在同一段归一逻辑改喂一个真
    会被求值的谓词。

    新谓词标记连同其参数只挂在 `predicate_params`，不混入 `local_predicates`——
    两者是刻意分离的两条通道（免参 vs 带参），`watch._scoped_predicates` 把两侧的
    点分名合并后一并喂给 `filter_papers`，`predicate_params=` 再把参数原样转交
    （`watch.py` 模块 docstring"参数化谓词"段）；若误把需要参数的谓词名直接塞进
    `local_predicates`（跳过 `predicate_params`），构造器会在缺参数时报错——这正是
    两个字段要分开、不能合并成一个的理由。9 个 preset 现有的 `filters.title_regex_any`
    镜像继续保留（决策④，防御纵深，新机制叠加非替换）。

    归一后为空串的 `query`（如只写了空白）不产 `predicate_params` 条目——空查询串
    没有诊断价值。

    `query` 里手写日期窗（`submittedDate:[…]` 等）→ 拒载，见 `_reject_date_window`
    （不变）。
    """
    del venue  # arxiv 不消费 venue quirks（分类即 DSL 直给；venue 侧的静态 quirks 由 T5 覆盖）
    pushdown: list[tuple[str, str]] = [
        (ARXIV_CATEGORY_PARAM, category) for category in selector.categories
    ]
    predicate_params: list[tuple[str, str]] = []
    if selector.query is not None:
        _reject_date_window(selector.query, source="arxiv", field="query")
        expression = normalize_arxiv_query(selector.query)
        if expression:
            predicate_params.append((PREDICATE_ARXIV_QUERY_BOOL, wrap_arxiv_query(expression)))
    return PlanStep(
        source="arxiv",
        pushdown=tuple(pushdown),
        predicate_params=tuple(predicate_params),
        note=_ARXIV_NOTE,
    )


def _compile_crossref(selector: SourceSelector, venue: VenueSpec | None) -> PlanStep:
    """crossref：`issns` → 每刊一条 `issn` 下推（期刊 watch 通道，design/08 §5）。

    实测端点形态是 `/journals/{issn}/works?filter=from-pub-date:…`（site-survey/
    metadata-apis.md）——ISSN 在 **path** 里、一次一刊，故多 ISSN 编译成**重复键**条目，
    由 T5 展开为多次请求（既有 `CrossrefAdapter` 正是这个形状）。无关键词能力也无关键词
    需求（期刊订阅按刊+日期枚举），故除 `filters` 外无补偿缺口。

    ISSN 形态在此把关（`_ISSN_PATTERN`）：它进的是 **URL path** 而非查询值，笔误会变成一条
    形如 `/journals/0033–5533/works`（全角连字符）的请求，报回来的 404 看不出是谁的错。
    """
    del venue
    for index, issn in enumerate(selector.issns):
        if not _ISSN_PATTERN.match(issn):
            _invalid(
                "crossref",
                "issns",
                f"ISSN 形态非法: {issn!r}（须 NNNN-NNNC，末位可为 X；直接进 "
                f"/journals/{{issn}}/works 的 URL path）",
                index=index,
            )
    return PlanStep(
        source="crossref",
        pushdown=tuple(("issn", issn) for issn in selector.issns),
        note=_CROSSREF_NOTE,
    )


def _compile_nber(selector: SourceSelector, venue: VenueSpec | None) -> PlanStep:
    """nber：`programs` → 每 program 一条下推（**参数形态**；feed 路由归 T7）。

    program 码逐字保留（`AP`）：`back.nber.org/rss/new{code}.xml` 的大小写归一与 19 feed
    映射表都在 T7（nber.md **§3.4**「RSS 增量 watch 通道」），本卡只定参数形状，免得同一张
    映射表落两处漂移。无日期参数的出处同为 T7 卡 + nber.md §3.4/§7（**不是** design/09 §5
    ——那节没有 nber 这一行）。
    """
    del venue
    return PlanStep(
        source="nber",
        pushdown=tuple(("program", program) for program in selector.programs),
        note=_NBER_NOTE,
    )


def _ssrn_topic_filter(venue: VenueSpec | None) -> str | None:
    """读 venue YAML 的 `quirks.topic_filter`；**未声明**→ None，声明了但取值非法 → CONFIG。

    沿 `neurips_proceedings._coerce_year_quirk` 的先例：quirks 是用户可改的 venue 配置，
    写错要当场报错，不静默当成"没声明"（那会让整份订阅悄悄少一层过滤）。

    "未声明"用 **`in` 判定**而非 `.get() is None`：`topic_filter:`（YAML 空值 = `None`）
    是**写了**这个键、只是没给值，属于笔误而非"不要这层过滤"——它必须和 `""` 一样响亮，
    否则同一类错误一个静默一个报错，用户无从判断自己的配置到底生效没有。
    """
    if venue is None or SSRN_TOPIC_FILTER_QUIRK not in venue.quirks:
        return None
    raw = venue.quirks[SSRN_TOPIC_FILTER_QUIRK]
    if not isinstance(raw, str) or not raw.strip():
        raise CrawlerError(
            ErrorClass.CONFIG,
            f"venue {venue.id!r} quirks.{SSRN_TOPIC_FILTER_QUIRK} 须是非空字符串: {raw!r}",
        )
    value = raw.strip()
    if value not in SSRN_TOPIC_FILTER_VALUES:
        raise CrawlerError(
            ErrorClass.CONFIG,
            f"venue {venue.id!r} quirks.{SSRN_TOPIC_FILTER_QUIRK} 取值 {value!r} 无实现"
            f"（合法值: {', '.join(sorted(SSRN_TOPIC_FILTER_VALUES))}；"
            f"新增集合须同时落 adapters/ssrn/parse.py 与本白名单）",
        )
    return value


def _compile_ssrn(selector: SourceSelector, venue: VenueSpec | None) -> PlanStep:
    """ssrn：**零下推** + `quirks.topic_filter` 接线（检查单 #10；ssrn.md §1/§3 预留接缝）。

    元数据主路径是 crossref 前缀 `10.2139` 枚举（站点零接触，D-029），而**聚合源没有
    network/eJournal 过滤维度**（ssrn.md §3 论据 2）——所以 `networks`/`ejournals` 一个
    参数都下推不出去。既然本地也拿不到"真实 FEN/ERN 成员籍"信号，把它们记成本地补偿谓词
    只会造出一条没人能兑现的契约；故如实处理为：**声明意图入 `note`**，近似语义由 venue 的
    `quirks.topic_filter`（OpenAlex primary_topic.field ∈ econ/fin 集）承担。

    **`ssrn.topic_filter` 的执行前提（controller 裁决 2026-07-26）**：该谓词依赖
    `stub.meta['openalex_field']` 键；**当前生产路径不产该键**（openalex `_meta_of` 未接线、
    ssrn 走 crossref 枚举更无此键——见 `adapters/ssrn/parse.py::TOPIC_FIELD_META_KEY` 注释）。
    谓词在信号缺失时的兜底语义由 T3 执行层定义为 **pass-through 放行 + obslog 一次性提示**。
    故这里仍标记谓词（执行层实现是在的，缺的只是信号），但 `note` 必须把这个前提带出去，
    免得用户以为自己已经拿到了 econ/fin 收窄。

    design/09 §3 对 SSRN 的判词"关键词全在本地过滤"由 `filters` 三谓词落实（驱动层统一附加）。
    """
    note = _SSRN_NOTE_HEAD
    declared: list[str] = []
    if selector.networks:
        declared.append(f"networks=[{', '.join(selector.networks)}]")
    if selector.ejournals:
        declared.append(f"ejournals=[{', '.join(selector.ejournals)}]")
    if declared:
        note += f"；已声明 {'、'.join(declared)} 记为声明意图（近似，非真实子网成员籍）"

    predicates: tuple[str, ...] = ()
    topic_filter = _ssrn_topic_filter(venue)
    if topic_filter is None:
        note += "；venue 未声明 quirks.topic_filter → 无主题近似补偿"
    else:
        predicates = (PREDICATE_SSRN_TOPIC_FILTER,)
        note += (
            f"；econ/fin 主题近似过滤 quirks.topic_filter={topic_filter}"
            f" → 本地补偿 {PREDICATE_SSRN_TOPIC_FILTER}"
            "（依赖 enrich 信号接线 stub.meta['openalex_field']，未接线时该谓词退化为"
            " LocalFilter-only）"
        )
    return PlanStep(source="ssrn", local_predicates=predicates, note=note + _SSRN_NOTE_TAIL)


# duck-typed 注册表（不进 `AdapterBase` 协议——编译是订阅域的事，冻结件不因此改动；
# plan §4 T2 已裁决歧义①）。键集必须与 `model.SOURCE_FIELDS` 等值：
# `test_subs_compile.py` 有**集合等值自断言**（`SUPPORTED_SOURCES == set(SOURCE_FIELDS)`），
# 防"扩了 SOURCE_FIELDS 却没写编译器"这类清单漂移（审计 S4 教训的同款守法）。**反向也
# 由它守住**：给一个 watch 不可达的源写编译器（openalex/s2 的旧形态）同样会打红——
# 编译器的存在本身就是"这个源跑得动"的暗示，不该比白名单活得更久（R2b/P0-4）。
_COMPILERS: dict[str, Callable[[SourceSelector, VenueSpec | None], PlanStep]] = {
    "arxiv": _compile_arxiv,
    "ssrn": _compile_ssrn,
    "nber": _compile_nber,
    "crossref": _compile_crossref,
}

SUPPORTED_SOURCES: frozenset[str] = frozenset(_COMPILERS)


# --- 驱动 -------------------------------------------------------------------


def compile_subscription(
    subscription: Subscription, *, venues: Mapping[str, VenueSpec] | None = None
) -> CompiledPlan:
    """把一份订阅编译成执行计划：每个已声明的源一个 `PlanStep`（顺序 = DSL 声明序）。

    `venues` 按**源 id** 索引（`{"ssrn": <VenueSpec>}`）——当前只有 ssrn 消费 venue
    （`quirks.topic_filter`，检查单 #10）；缺该键或整个 `venues` 为 None 时按"未声明
    topic_filter"处理（可编译，`note` 里写明少了这层近似补偿）。

    未知源 / **watch 不可达源** → `SubscriptionInvalid`（CONFIG）：正常路径上
    `parse_subscription` 已挡住（`SOURCE_FIELDS` 白名单），此处兜住"绕过解析器直接构造
    `Subscription`"的调用方——包括从**旧库行**还原的历史订阅（`Subscription.from_stored`
    虽同走解析器，但库里躺着的 `query_json` 可能是白名单收缩之前写入的）。

    enrich-only 源（openalex/s2/repec）在此拿到的是与加载期**逐字相同**的那句话
    （`model.unsupported_source_message`）："该源不支持 watch，请走 crawler enrich"。
    修复前这条路径的终点是运行期的 `CapabilityNotSupported`——编译过、请求也合成了，
    直到 `AdapterFetcher` 调 `discover_timeline` 才炸（R2b/P0-4）。
    """
    venue_map = venues or {}
    universal = local_predicates_of(subscription.filters)

    steps: list[PlanStep] = []
    for selector in subscription.sources:
        compiler = _COMPILERS.get(selector.source)
        if compiler is None:
            detail = f"subscription[{subscription.name}]:sources.{selector.source}"
            raise SubscriptionInvalid(
                f"{detail} —— {unsupported_source_message(selector.source)}", detail=detail
            )
        step = compiler(selector, venue_map.get(selector.source))
        # 全源共有的补偿谓词在前、源专属在后——`all_local_predicates()` 的并集因此有稳定前缀。
        steps.append(replace(step, local_predicates=universal + step.local_predicates))

    return CompiledPlan(subscription=subscription.name, steps=tuple(steps))


__all__ = [
    "DATE_WINDOW_PARAMS",
    "PREDICATE_ARXIV_QUERY_BOOL",
    "PREDICATE_SSRN_TOPIC_FILTER",
    "SSRN_TOPIC_FILTER_QUIRK",
    "SSRN_TOPIC_FILTER_VALUES",
    "SUPPORTED_SOURCES",
    "compile_subscription",
    "local_predicates_of",
]
