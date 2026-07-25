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
| openalex | `filter=concepts.id:` + `filter=type:` | 仅 `filters` 三谓词（名称型 concepts 见下） |
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
3. **源专属补偿谓词一律 `"<source>.<name>"`**（`subs/types.py` 约定），当前只有一条：
   `ssrn.topic_filter`。

## 只标记**有实现**的补偿谓词（controller 裁决 2026-07-26）

`local_predicates` 是 T3/T5 的执行契约，不是愿望清单：标一条 T3 registry 里没有的谓词，
T5 集成时会直接 `ValueError` 崩掉整轮 watch。两个近亲案例的处置因此不同——

- **`ssrn.topic_filter`：谓词有实现、只缺信号** → **保留标记**。执行层
  （`adapters/ssrn/parse.py::topic_field_matches`）在，缺的是 `stub.meta['openalex_field']`
  这个 enrich 信号；信号缺失时的兜底语义由 T3 定为 pass-through 放行 + obslog 一次性提示。
- **openalex 名称型 concepts：连实现都没有** → **出列，降级 note-only**。名称→id 要一次
  在线查询，属 T5 运行期；在谓词实现落地前，它既没下推也没本地补偿，如实写进 `note`
  （用户看得见"这条只是没生效"），而不是标一条没人兑现的契约。

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
from typing import NoReturn

from paper_crawler.errors import CrawlerError, ErrorClass, SubscriptionInvalid
from paper_crawler.subs.model import LocalFilter, SourceSelector, Subscription
from paper_crawler.subs.types import (
    DATE_WINDOW_PARAMS,
    LOCAL_PREDICATE_EXCLUDE_REGEX,
    LOCAL_PREDICATE_MIN_YEAR,
    LOCAL_PREDICATE_TITLE_REGEX_ANY,
    CompiledPlan,
    PlanStep,
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

# `quirks.topic_filter` 的合法取值域：目前**只有** `econ_fin` 有实现（= `ECON_FIN_FIELDS`
# 是全库唯一落地的主题集）。写了别的值（拼错的 `econ-fin`、臆造的集合名）→ CONFIG 响亮，
# 不静默当成"某个不存在的集合"跑出一份空清单。新增集合须同时落 parse.py 与本白名单。
SSRN_TOPIC_FILTER_VALUES: frozenset[str] = frozenset({"econ_fin"})

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
    "（back.nber.org/rss/new{code}.xml，实证 feed 清单见 adapters/nber/rss.py，nber.md §3.4）；"
    "无日期参数——增量走 RSS id 集合差分（T4/T7 卡）"
)

_SSRN_NOTE_HEAD = "ssrn 聚合源无 network/eJournal 精确过滤维度（ssrn.md §3）→ 无下推参数"

_SSRN_NOTE_TAIL = (
    "；关键词类条件全量本地补偿；"
    "枚举窗由 T4 以 filter=from-created-date/until-created-date 注入（内部 crossref created 轴）"
)

# 名称型 concepts 的现状说明（P1 出列裁决 2026-07-26）：既没下推、也**没有**本地补偿谓词
# 实现——如实说，别让用户以为它生效了。
_OPENALEX_CONCEPT_NAMES_NOTE = (
    "名称形态 concepts 未下推亦未本地补偿"
    "（谓词实现待 enrich 信号接线），当前退化为 LocalFilter-only"
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

    **已知行为（引号不配对）**：`"` 落单时 `_QUOTED_PHRASE` 匹配不到成对短语，那截文本
    按**引号外**处理——即照样折空白、照样大写化操作符。这是刻意不救的：引号配不上本就
    是写错了，猜"用户想在哪里闭合"只会把一个显式错误变成一个隐式错误。查询原样交给
    arXiv 报错，用户看到的是自己的引号问题，而不是编译器替他改过的某个陌生查询。
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

    `query` 里手写日期窗（`submittedDate:[…]` 等）→ 拒载，见 `_reject_date_window`。
    """
    del venue  # arxiv 不消费 venue quirks（分类即 DSL 直给）
    parts: list[str] = []
    if selector.categories:
        parts.append(_wrap(" OR ".join(f"cat:{category}" for category in selector.categories)))
    if selector.query is not None:
        _reject_date_window(selector.query, source="arxiv", field="query")
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

    它们**也不进 `local_predicates`**（P1 出列裁决 2026-07-26）：名称→id 要一次在线查询，
    谓词至今无任何实现，标上去只会让 T5 在组装执行链时对着一个不存在的谓词崩掉。故降级为
    note-only，如实告诉用户"这条既没下推也没补偿"。与 `ssrn.topic_filter` 的差别正在这里：
    那条**有**执行层实现、只缺 enrich 信号（故保留标记 + 由 T3 兜底），这条连实现都没有。
    """
    del venue
    pushdown: list[tuple[str, str]] = []
    concept_ids, concept_names = _split_openalex_concepts(selector.concepts)
    if concept_ids:
        pushdown.append(("filter", "concepts.id:" + "|".join(concept_ids)))
    if selector.from_source_types:
        for index, source_type in enumerate(selector.from_source_types):
            if "|" in source_type:
                _invalid(
                    "openalex",
                    "from_source_types",
                    f"取值不得含 '|': {source_type!r}（`|` 是 filter 轴内的 OR 分隔符，"
                    f"混入会被 OpenAlex 读成两个类型）",
                    index=index,
                )
        pushdown.append(("filter", "type:" + "|".join(selector.from_source_types)))

    note = _OPENALEX_NOTE
    if concept_names:
        note += (
            f"；concepts 名称 [{', '.join(concept_names)}] 无离线 id 解析路径"
            f"（/concepts 已弃用转 /topics）→ {_OPENALEX_CONCEPT_NAMES_NOTE}"
        )
    return PlanStep(source="openalex", pushdown=tuple(pushdown), note=note)


def _compile_s2(selector: SourceSelector, venue: VenueSpec | None) -> PlanStep:
    """s2：`venues`/`fields_of_study`/`query` → bulk search 参数（design/09 §3）。

    参数名取 site-survey/metadata-apis.md 实测面：`/paper/search/bulk` 的 `venue=`（逗号
    分隔 OR 匹配）、`fieldsOfStudy=`（逗号分隔）、`query=`。**venue 是模糊名匹配而非 id
    精确**（同上出处）——如实写进 `note`，不假装它是精确过滤。

    值里自带逗号 → 拒载：逗号是这两个参数的分隔符，`"Foo, Bar Journal"` 混进去会被 S2
    拆成两个 venue，多收一堆无关论文而毫无报错。
    """
    del venue
    pushdown: list[tuple[str, str]] = []
    for field, values in (
        ("venues", selector.venues),
        ("fields_of_study", selector.fields_of_study),
    ):
        for index, value in enumerate(values):
            if "," in value:
                _invalid(
                    "s2",
                    field,
                    f"取值不得含 ',': {value!r}（逗号是 venue/fieldsOfStudy 的 OR 分隔符，"
                    f"混入会被 S2 拆成多项）",
                    index=index,
                )
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
    "PREDICATE_SSRN_TOPIC_FILTER",
    "SSRN_TOPIC_FILTER_QUIRK",
    "SSRN_TOPIC_FILTER_VALUES",
    "SUPPORTED_SOURCES",
    "compile_subscription",
    "local_predicates_of",
]
