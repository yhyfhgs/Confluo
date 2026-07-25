"""查询编译器：`Subscription` → `CompiledPlan`（Phase 6 T2；design/09 §3 能力映射表）。

每个源一个编译器，把该源的 `SourceSelector` 翻译成**原生查询参数**（`PlanStep.pushdown`），
并把该源下推不了的条件标成**本地补偿谓词**（`PlanStep.local_predicates`）。原则句
（design/09 §3 末）："下推尽可能多以省流量，但正确性以本地过滤为准"——故凡是拿不准能否
精确下推的条件，一律落本地补偿，**绝不臆造源侧语法**去换取一次省流量的请求。

## 能力映射（design/09 §3 表 = 权威规格；语法出处见各编译器 docstring）

| 源 | 下推 | 本地补偿 |
|---|---|---|
| arxiv | `search_query`（`cat:` 组 + 字段级布尔式，完整下推） | 仅 `filters` 三谓词 |
| crossref | 每 issn 一条（`/journals/{issn}/works`） | 仅 `filters` 三谓词（无关键词场景） |
| openalex | `filter=concepts.id:` + `filter=type:` | `filters` 三谓词 + 名称型 concepts |
| s2 | `venue` / `fieldsOfStudy` / `query`（bulk search） | 仅 `filters` 三谓词 |
| nber | 每 program 一条（feed 路由归 T7） | 仅 `filters` 三谓词 |
| ssrn | **无**（聚合源无 network/eJournal 维度） | `filters` 三谓词 + `ssrn.topic_filter` |

## 三条不变量（下游可依赖）

1. **`pushdown` 条目顺序 = `model.SOURCE_FIELDS` 的字段声明序**——同一订阅恒得同一
   计划（确定性输出，快照可测）；重复键（多 issn / 多 program / 多 filter 轴）保序保重复，
   这正是 `PlanStep.pushdown` 用元组而非 dict 的原因。
2. **`LocalFilter` 的三谓词恒进全源** `local_predicates`（声明了哪几条就进哪几条，
   按 `LocalFilter` 字段序）：正则与 `min_year` 没有任何源被允许下推——`min_year` 尤其
   **不占日期参数槽位**（那是 T4 增量窗的位置，见下"接缝"），两者混用会让"过滤下界"与
   "增量上界"互相覆盖。
3. **源专属补偿谓词一律 `"<source>.<name>"`**（`subs/types.py` 约定），当前两条：
   `ssrn.topic_filter`、`openalex.concepts`。

## 接缝：日期窗不在本模块（plan §4 T2 接缝裁决①）

本模块只产**静态参数**。运行时的增量窗口参数由 T4（watermark）独立产出、T5 合成——
二者结构同构（都是 `(key, value)` 元组），拼接即可。各源日期参数名见
`DATE_WINDOW_PARAMS`（单一同源，T4/T5 直接消费，不必再翻文档）。

`subs/__init__.py` 的导出面留待 T5 集成时统一补（本卡不动）。
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace

from paper_crawler.errors import CrawlerError, ErrorClass, SubscriptionInvalid
from paper_crawler.subs.model import LocalFilter, SourceSelector, Subscription
from paper_crawler.subs.types import (
    LOCAL_PREDICATE_EXCLUDE_REGEX,
    LOCAL_PREDICATE_MIN_YEAR,
    LOCAL_PREDICATE_TITLE_REGEX_ANY,
    CompiledPlan,
    PlanStep,
)
from paper_crawler.types import VenueSpec

# --- T4/T5 接缝：各源日期窗参数名 -------------------------------------------

# 本模块不产日期值（接缝裁决①）；这里只声明**槽位名**供 T4 产值、T5 合成。
# 出处逐源：
# - arxiv：`submittedDate:[YYYYMMDDTTTT TO YYYYMMDDTTTT]`（GMT）——不是独立 URL 参数，
#   而是拼进**同一个 `search_query`** 的范围项（site-survey/arxiv.md 关键机制段）。
# - crossref：`filter=from-pub-date:…,until-pub-date:…`（published 轴的 filter 名是 `pub`
#   缩写；见 `adapters/crossref/adapter.py::_DATE_FIELD_FILTER`）。
# - openalex：`filter=from_publication_date:…,to_publication_date:…`（免费轴；
#   `from_created/updated_date` 是 Premium 门控，site-survey/metadata-apis.md）。
# - s2：bulk search 顶层参数 `publicationDateOrYear`（亦可用 `year=2016-2020`）。
# - nber：**无日期参数**——RSS 通道按 id 集合差分推进（design/09 §5，T4+T7）。
# - ssrn：内部 crossref 走 created 轴 → `from-created-date`/`until-created-date`
#   （ssrn.md §4.2 登记年轴）。
DATE_WINDOW_PARAMS: dict[str, tuple[str, ...]] = {
    "arxiv": ("submittedDate",),
    "ssrn": ("from-created-date", "until-created-date"),
    "openalex": ("from_publication_date", "to_publication_date"),
    "s2": ("publicationDateOrYear",),
    "nber": (),
    "crossref": ("from-pub-date", "until-pub-date"),
}

# --- 源专属补偿谓词与 venue 接线常量 -----------------------------------------

# ssrn econ/fin 主题**近似**过滤（venue YAML `quirks.topic_filter`，检查单 #10）。
# 谓词标记只记"这条要本地补偿"，取值（如 `econ_fin`）落 `note`——T3/T5 需要具体集合时
# 从 venue 读（`adapters/ssrn/parse.py::ECON_FIN_FIELDS` 是唯一权威集合）。
SSRN_TOPIC_FILTER_QUIRK = "topic_filter"
PREDICATE_SSRN_TOPIC_FILTER = "ssrn.topic_filter"

# openalex 名称型 concepts（无离线 id 解析路径，见 `_compile_openalex`）。
PREDICATE_OPENALEX_CONCEPTS = "openalex.concepts"

# --- 编译期备注（进 `PlanStep.note`，供日报/诊断呈现，不参与判定）-------------

_ARXIV_NOTE = (
    "arxiv 完整下推：categories→cat: 组、query→字段级布尔式，合成单个 search_query"
    "（布尔操作符 AND/OR/ANDNOT 以 site-survey/arxiv.md 实测为准）；"
    "增量窗由 T4 以 submittedDate:[A TO B]（GMT）追加进同一 search_query"
)

_CROSSREF_NOTE = (
    "crossref 完整下推（无关键词场景）：每个 issn 一次 /journals/{issn}/works；"
    "增量窗由 T4 以 filter=from-pub-date/until-pub-date 注入"
)

_OPENALEX_NOTE = (
    "openalex 概念+类型下推；多条 filter 条目是 AND 关系（T5 以逗号拼进单个 filter= 参数），"
    "同一轴内多值用 | 表 OR；增量窗由 T4 以 filter=from_publication_date/to_publication_date 注入"
)

_S2_NOTE = (
    "s2 bulk search（/paper/search/bulk）下推 venue/fieldsOfStudy/query；"
    "venue 是模糊名/ISO4 缩写 OR 匹配（非 id 精确，site-survey/metadata-apis.md）→ 命中需本地复核；"
    "增量窗由 T4 以 publicationDateOrYear 注入；token 续页与 API key 归 T5"
)

_NBER_NOTE = (
    "nber programs 下推为参数形态（每 program 一条）；feed 路由归 T7"
    "（back.nber.org/rss/new{code}.xml，19 feed）；无日期参数——增量走 RSS id 集合差分（T4）"
)

_SSRN_NOTE_HEAD = "ssrn 聚合源无 network/eJournal 精确过滤维度（ssrn.md §3）→ 无下推参数"

_SSRN_NOTE_TAIL = (
    "；关键词类条件全量本地补偿；"
    "枚举窗由 T4 以 filter=from-created-date/until-created-date 注入（内部 crossref created 轴）"
)

# --- arXiv 查询式归一（语法以 site-survey/arxiv.md 实测为准）-----------------

# 引号短语：arXiv 用 `"…"` 表短语（`abs:"tool use"`）。归一只在引号**外**动手——
# 引号内是用户的检索词，动它就是改语义。
_QUOTED_PHRASE = re.compile(r'"[^"]*"')
_WHITESPACE_RUN = re.compile(r"\s+")
# `AND NOT` → `ANDNOT`：arXiv 实测的否定操作符是**单词 `ANDNOT`**（site-survey/arxiv.md
# "布尔 AND/OR/ANDNOT"），而 design/09 §2 示例写作 `AND NOT`——两者指同一语义，此处归一，
# 否则 `NOT` 会被 arXiv 当成检索词而静默改变结果集。
_AND_NOT = re.compile(r"\bAND\s+NOT\b", re.IGNORECASE)
# 裸布尔词大写化：arXiv 操作符须大写，小写 `and`/`or` 会被当作检索词。
_BARE_OPERATOR = re.compile(r"\b(and|or|andnot)\b", re.IGNORECASE)


def _outside_quotes(expr: str, transform: Callable[[str], str]) -> str:
    """只对引号外的片段施 `transform`，引号内原样保留（拼回原序）。"""
    chunks: list[str] = []
    cursor = 0
    for match in _QUOTED_PHRASE.finditer(expr):
        chunks.append(transform(expr[cursor : match.start()]))
        chunks.append(match.group(0))
        cursor = match.end()
    chunks.append(transform(expr[cursor:]))
    return "".join(chunks)


def _normalize_arxiv_query(raw: str) -> str:
    """归一用户写的 arXiv 布尔式：折行空白 + `AND NOT`→`ANDNOT` + 操作符大写。

    DSL 里的 `query` 常写成 YAML 折叠标量（design/09 §2 示例一的 `query: >`），折出来带
    换行与多余空格；且示例用 `AND NOT` 而实测操作符是 `ANDNOT`。归一**全部只在引号外**
    进行（`abs:"tool use"` 里的空格、`ti:"cats and dogs"` 里的 `and` 都不动）。

    不做的事：不校验字段前缀合法性、不补括号、不处理一元 `NOT`（arXiv 无此语义）——
    编译器不臆造语法，非法查询在运行期由 arXiv 明确报错，好过在此静默改写。
    """

    def normalize(chunk: str) -> str:
        chunk = _WHITESPACE_RUN.sub(" ", chunk)
        chunk = _AND_NOT.sub("ANDNOT", chunk)
        return _BARE_OPERATOR.sub(lambda m: m.group(1).upper(), chunk)

    return _outside_quotes(raw, normalize).strip()


def _is_atom(expr: str) -> bool:
    """表达式是否"原子"（引号外无空白）——原子无需加括号（`cat:cs.AI`、`ti:"tool use"`）。"""
    return not any(char.isspace() for char in _QUOTED_PHRASE.sub("", expr))


def _is_fully_wrapped(expr: str) -> bool:
    """整条表达式是否已被**一对**括号完整包住（`(a OR b)` 真，`(a) OR (b)` 假）。

    用于避免拼接时产生 `((…))` 这类无意义嵌套（不影响语义，只为可读与快照稳定）。
    """
    if not (expr.startswith("(") and expr.endswith(")")):
        return False
    depth = 0
    in_quote = False
    for index, char in enumerate(expr):
        if char == '"':
            in_quote = not in_quote
        elif in_quote:
            continue
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return index == len(expr) - 1
    return False  # 括号不配对（用户写错）——不加戏，原样交给 arXiv 报错


def _wrap(expr: str) -> str:
    """按需加括号：原子与"已整体括起"者原样返回，其余包一层。

    复合式**恒**带外层括号（哪怕它是 `search_query` 的唯一成分），因为 T4 的增量窗是
    `AND submittedDate:[A TO B]` **追加**在末尾的：少了这层括号，
    `cat:a OR cat:b AND <日期窗>` 会被读成 `cat:a OR (cat:b AND 日期窗)`——第一个分类
    悄悄逃出增量窗，是那种日报上看不出、对账才发现的漏收。
    """
    return expr if _is_atom(expr) or _is_fully_wrapped(expr) else f"({expr})"


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
    """arxiv：`categories` + `query` 合成单个 `search_query`（完整下推，design/09 §3）。

    - 分类组：`cat:cs.AI OR cat:cs.LG …`（多值时整体加括号）；
    - 查询式：用户的字段级布尔式，经 `_normalize_arxiv_query` 归一；
    - 两者都在时以 `AND` 连接（"这些分类里，且满足这个查询式"）。

    语法出处 = site-survey/arxiv.md「关键机制」段（字段前缀 `ti/au/abs/co/jr/cat/rn/all`、
    布尔 `AND/OR/ANDNOT`、短语用引号）。翻页上限与限速是 T5 的事，不在编译产物里。
    """
    del venue  # arxiv 不消费 venue quirks（分类即 DSL 直给）
    parts: list[str] = []
    if selector.categories:
        parts.append(_wrap(" OR ".join(f"cat:{category}" for category in selector.categories)))
    if selector.query is not None:
        parts.append(_wrap(_normalize_arxiv_query(selector.query)))
    expression = " AND ".join(parts)
    return PlanStep(
        source="arxiv",
        pushdown=(("search_query", expression),) if expression else (),
        note=_ARXIV_NOTE,
    )


def _compile_crossref(selector: SourceSelector, venue: VenueSpec | None) -> PlanStep:
    """crossref：`issns` → 每刊一条 `issn` 下推（期刊 watch 通道，design/08 §5）。

    实测端点形态是 `/journals/{issn}/works?filter=from-pub-date:…`（site-survey/
    metadata-apis.md）——ISSN 在 **path** 里、一次一刊，故多 ISSN 编译成**重复键**条目，
    由 T5 展开为多次请求（既有 `CrossrefAdapter` 正是这个形状）。无关键词能力也无关键词
    需求（期刊订阅按刊+日期枚举），故除 `filters` 外无补偿缺口。
    """
    del venue
    return PlanStep(
        source="crossref",
        pushdown=tuple(("issn", issn) for issn in selector.issns),
        note=_CROSSREF_NOTE,
    )


# OpenAlex 概念 id 形态：`C41008148` 或整条实体 URL。名称（"large language model"）无法在
# 离线编译期解析成 id——那需要一次 `/concepts` 查询（且该端点已弃用转 `/topics`，
# site-survey/metadata-apis.md ⚡）。故 id 形态下推、名称形态记本地补偿。
_OPENALEX_CONCEPT_ID = re.compile(r"^(?:https?://openalex\.org/)?(C\d+)$", re.IGNORECASE)


def _split_openalex_concepts(concepts: Sequence[str]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """把 `concepts` 分成（可下推的 id, 只能本地补偿的名称）两组，各自保序。"""
    ids: list[str] = []
    names: list[str] = []
    for concept in concepts:
        match = _OPENALEX_CONCEPT_ID.match(concept.strip())
        if match:
            ids.append("C" + match.group(1)[1:])
        else:
            names.append(concept)
    return tuple(ids), tuple(names)


def _compile_openalex(selector: SourceSelector, venue: VenueSpec | None) -> PlanStep:
    """openalex：`concepts`（id 形态）+ `from_source_types` → `filter=` 轴（design/09 §3）。

    - `concepts.id:C1|C2`——同轴多值用 `|` 表 OR；
    - `type:preprint|article`——`from_source_types` 映射到 works 的 `type` 轴
      （`model.SOURCE_FIELDS` 注释即写明 `filter=concepts/type`）。

    **名称型 concepts 不下推**：把 "large language model" 塞进 `concepts.id:` 只会得到
    空结果或报错——这类"看似省流量实则改结果"的下推正是 design/09 §3 原则句要挡的。
    它们改记 `openalex.concepts` 本地补偿，名称原样写进 `note` 供诊断/后续 id 解析。
    """
    del venue
    pushdown: list[tuple[str, str]] = []
    concept_ids, concept_names = _split_openalex_concepts(selector.concepts)
    if concept_ids:
        pushdown.append(("filter", "concepts.id:" + "|".join(concept_ids)))
    if selector.from_source_types:
        pushdown.append(("filter", "type:" + "|".join(selector.from_source_types)))

    note = _OPENALEX_NOTE
    predicates: tuple[str, ...] = ()
    if concept_names:
        predicates = (PREDICATE_OPENALEX_CONCEPTS,)
        note += (
            f"；concepts 名称 [{', '.join(concept_names)}] 无离线 id 解析路径"
            f"（/concepts 已弃用转 /topics）→ 记本地补偿 {PREDICATE_OPENALEX_CONCEPTS}"
        )
    return PlanStep(
        source="openalex",
        pushdown=tuple(pushdown),
        local_predicates=predicates,
        note=note,
    )


def _compile_s2(selector: SourceSelector, venue: VenueSpec | None) -> PlanStep:
    """s2：`venues`/`fields_of_study`/`query` → bulk search 参数（design/09 §3）。

    参数名取 site-survey/metadata-apis.md 实测面：`/paper/search/bulk` 的 `venue=`（逗号
    分隔 OR 匹配）、`fieldsOfStudy=`（逗号分隔）、`query=`。**venue 是模糊名匹配而非 id
    精确**（同上出处）——如实写进 `note`，不假装它是精确过滤。
    """
    del venue
    pushdown: list[tuple[str, str]] = []
    if selector.venues:
        pushdown.append(("venue", ",".join(selector.venues)))
    if selector.fields_of_study:
        pushdown.append(("fieldsOfStudy", ",".join(selector.fields_of_study)))
    if selector.query is not None:
        pushdown.append(("query", _WHITESPACE_RUN.sub(" ", selector.query).strip()))
    return PlanStep(source="s2", pushdown=tuple(pushdown), note=_S2_NOTE)


def _compile_nber(selector: SourceSelector, venue: VenueSpec | None) -> PlanStep:
    """nber：`programs` → 每 program 一条下推（**参数形态**；feed 路由归 T7）。

    program 码逐字保留（`AP`）：`back.nber.org/rss/new{code}.xml` 的大小写归一与 19 feed
    映射表都在 T7（nber.md §3.5），本卡只定参数形状，免得同一张映射表落两处漂移。
    """
    del venue
    return PlanStep(
        source="nber",
        pushdown=tuple(("program", program) for program in selector.programs),
        note=_NBER_NOTE,
    )


def _ssrn_topic_filter(venue: VenueSpec | None) -> str | None:
    """读 venue YAML 的 `quirks.topic_filter`（缺省 None）；取值非法 → CONFIG 响亮失败。

    沿 `neurips_proceedings._coerce_year_quirk` 的先例：quirks 是用户可改的 venue 配置，
    类型写错要当场报错，不静默当成"没声明"（那会让整份订阅悄悄少一层过滤）。
    """
    if venue is None:
        return None
    raw = venue.quirks.get(SSRN_TOPIC_FILTER_QUIRK)
    if raw is None:
        return None
    if not isinstance(raw, str) or not raw.strip():
        raise CrawlerError(
            ErrorClass.CONFIG,
            f"venue {venue.id!r} quirks.{SSRN_TOPIC_FILTER_QUIRK} 须是非空字符串: {raw!r}",
        )
    return raw.strip()


def _compile_ssrn(selector: SourceSelector, venue: VenueSpec | None) -> PlanStep:
    """ssrn：**零下推** + `quirks.topic_filter` 接线（检查单 #10；ssrn.md §1/§3 预留接缝）。

    元数据主路径是 crossref 前缀 `10.2139` 枚举（站点零接触，D-029），而**聚合源没有
    network/eJournal 过滤维度**（ssrn.md §3 论据 2）——所以 `networks`/`ejournals` 一个
    参数都下推不出去。既然本地也拿不到"真实 FEN/ERN 成员籍"信号，把它们记成本地补偿谓词
    只会造出一条没人能兑现的契约；故如实处理为：**声明意图入 `note`**，近似语义由 venue 的
    `quirks.topic_filter`（OpenAlex primary_topic.field ∈ econ/fin 集）承担，后者才是真能
    在本地兑现的谓词（`adapters/ssrn/parse.py::filter_stubs_by_topic`）。

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
        )
    return PlanStep(source="ssrn", local_predicates=predicates, note=note + _SSRN_NOTE_TAIL)


# duck-typed 注册表（不进 `AdapterBase` 协议——编译是订阅域的事，冻结件不因此改动；
# plan §4 T2 已裁决歧义①）。键集必须与 `model.SOURCE_FIELDS` 等值：
# `test_subs_compile.py` 有**集合等值自断言**（`SUPPORTED_SOURCES == set(SOURCE_FIELDS)`），
# 防"扩了 SOURCE_FIELDS 却没写编译器"这类清单漂移（审计 S4 教训的同款守法）。
_COMPILERS: dict[str, Callable[[SourceSelector, VenueSpec | None], PlanStep]] = {
    "arxiv": _compile_arxiv,
    "ssrn": _compile_ssrn,
    "openalex": _compile_openalex,
    "s2": _compile_s2,
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

    未知源 → `SubscriptionInvalid`（CONFIG）：正常路径上 `parse_subscription` 已挡住，
    此处兜住"绕过解析器直接构造 `Subscription`"的调用方，避免 KeyError 这种无信息量的崩法。
    """
    venue_map = venues or {}
    universal = local_predicates_of(subscription.filters)

    steps: list[PlanStep] = []
    for selector in subscription.sources:
        compiler = _COMPILERS.get(selector.source)
        if compiler is None:
            raise SubscriptionInvalid(
                f"subscription[{subscription.name}]:sources.{selector.source} —— "
                f"无该源的编译器（支持: {', '.join(sorted(SUPPORTED_SOURCES))}）",
                detail=f"subscription[{subscription.name}]:sources.{selector.source}",
            )
        step = compiler(selector, venue_map.get(selector.source))
        # 全源共有的补偿谓词在前、源专属在后——`all_local_predicates()` 的并集因此有稳定前缀。
        steps.append(replace(step, local_predicates=universal + step.local_predicates))

    return CompiledPlan(subscription=subscription.name, steps=tuple(steps))


__all__ = [
    "DATE_WINDOW_PARAMS",
    "PREDICATE_OPENALEX_CONCEPTS",
    "PREDICATE_SSRN_TOPIC_FILTER",
    "SSRN_TOPIC_FILTER_QUIRK",
    "SUPPORTED_SOURCES",
    "compile_subscription",
    "local_predicates_of",
]
