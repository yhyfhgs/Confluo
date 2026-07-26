"""订阅 DSL 模型与加载校验（Phase 6 T1 冻结件；design/09 §2 逐字段）。

一个 `Subscription` = 用户声明的"我关心什么"：`sources`（每源专属选择器，编译为
原生查询下推）+ `filters`（对所有源结果统一执行的本地二次过滤）+ `actions`（入库/
自动下载）+ `guard`（数量护栏，FR-16）+ `schedule_hint`（**仅存不调度**——cron 外置，
design/05 §2；plan §4 T1 已裁决歧义③）。

## 校验纪律：fail-loud（plan §4 T1 已裁决歧义②）

订阅文件是用户配置，任何结构/取值问题一律 `SubscriptionInvalid`（CONFIG 类）
**拒载**，绝不"忽略未知字段继续跑"——一个拼错的 `catgories:` 若被静默丢弃，用户
会收到一份"看起来正常但少了半个领域"的日报，这类静默降级正是审计 S1 的反模式。
与 `registry.load_dirs`（收集 `LintIssue` 不抛）的差异是刻意的：venue 目录是几十个
文件的批量面（一个坏文件不该拖垮全库），订阅是用户逐个显式指定运行的单元。

具体规则（每条都有专测，`tests/unit/test_subs_model.py`）：

- 顶层/各段的**未知字段**→ 报错（并在消息里列出该位置允许的字段）；
- **未知源**→ 报错（列出 `SOURCE_FIELDS` 支持的六源）；
- 声明了却**空值**的字段（`categories: []`、`query: ""`）→ 报错（意图不明）；
- `filters` 的正则**编译失败**→ 报错（把 `re.error` 归一到 CONFIG，不留到运行期炸）；
- 数值域：`guard.max_new_per_run ≥ 1`、`actions.auto_fetch_limit ≥ 0`、
  `filters.min_year ∈ [1000, 3000]`；`bool` 不被当作 int 接受（YAML `true` 误填
  数值位 → 报错）；
- 文件名 stem 必须等于 `name`（沿 registry 的"文件名与 id 一致"惯例，此处升为硬错）；
- YAML **同一映射内的重复键**（如两次 `sources:`、`sources:` 内两次同一源、选择器
  内两次同一字段）→ 报错（PyYAML 默认静默取后者覆盖前者，此处升级为拒载——
  Phase 6 深审 P1-2 热修，`_DuplicateKeySafeLoader`）。

## `guard` 缺省补全（design/09 §2 示例二只写 `max_new_per_run`）

`max_new_per_run=200`、`dedupe_against_library=True`——缺省即安全侧（有熔断、有去重）。

## 目录语义

- `load_subscriptions_dir(subscriptions/)` **只扫顶层** `*.yaml`：`subscriptions/presets/`
  （design/09 §4 的 9 个预置包，T8）是**模板**不是活订阅——用户复制一份到
  `subscriptions/` 顶层并改造后才生效。这样 `watch --all` 不会把 9 个 preset 当成
  用户的真实订阅跑掉，也天然免掉 preset 与用户文件的同名冲突。
- `name` 唯一性由"文件名 stem == name"约束天然保证（同目录 stem 不可能重复）。
"""

import json
import re
from collections.abc import Hashable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, NoReturn

import yaml

from paper_crawler.errors import SubscriptionInvalid
from paper_crawler.subs.types import parse_arxiv_query

# --- DSL 词表（T2 编译器的能力面契约）---------------------------------------

# 每源允许的选择器字段（design/09 §3 能力映射表的下推面；顺序即序列化/报错列出序）。
# **日期窗不在 DSL 里**——增量窗由 watermark 推进（design/09 §5，T4 owns），编译期
# 由 T2 注入，用户不手写。
SOURCE_FIELDS: dict[str, tuple[str, ...]] = {
    "arxiv": ("categories", "query"),  # 字段前缀 ti/abs/cat/au + 布尔式，完整下推
    "ssrn": ("networks", "ejournals"),  # 仅分类浏览；关键词全在本地过滤
    "openalex": ("concepts", "from_source_types"),  # filter=concepts/type
    "s2": ("venues", "fields_of_study", "query"),  # bulk search venue/fieldsOfStudy
    "nber": ("programs",),  # program 分类下推
    "crossref": ("issns",),  # ISSN + from-pub-date（期刊 watch 通道）
}

# 取值形态：文本字段 vs 字符串列表字段（其余皆列表）。
_TEXT_FIELDS = frozenset({"query"})

_TOP_LEVEL_FIELDS = ("name", "sources", "filters", "actions", "guard", "schedule_hint")
_FILTER_FIELDS = ("title_regex_any", "exclude_regex", "min_year")
_ACTION_FIELDS = ("ingest", "auto_fetch_limit")
_GUARD_FIELDS = ("max_new_per_run", "dedupe_against_library")

# 订阅名：kebab-case（design/09 §2 示例 `llm-agents` / `asset-pricing-wp`），同时是
# 文件名 stem 与 `subscription` 表主键。
_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9-]*$")

_INGEST_MODES = ("metadata", "metadata+pdf")
IngestMode = Literal["metadata", "metadata+pdf"]

# `guard` 缺省（design/09 §2；示例二只写 max_new_per_run，其余按此补全）。
DEFAULT_MAX_NEW_PER_RUN = 200
DEFAULT_DEDUPE_AGAINST_LIBRARY = True

# `filters.min_year` 的可信年份区间（挡住 -1 / 0 / 20240 一类明显笔误）。
_MIN_YEAR_FLOOR = 1000
_MIN_YEAR_CEIL = 3000


# --- 报错与取值原语 ---------------------------------------------------------


def _fail(where: str, path: str, message: str) -> NoReturn:
    """统一的拒载出口：消息带 `<文件>:<字段路径>` 定位，`detail` 存同一定位串。"""
    location = f"{where}:{path}" if path else where
    raise SubscriptionInvalid(f"{location} —— {message}", detail=location)


def _reject_unknown(
    raw: Mapping[str, object], allowed: Sequence[str], *, where: str, path: str
) -> None:
    """未知字段即拒载；消息列出该位置允许的全部字段（用户可直接照着改）。"""
    for key in raw:
        if key not in allowed:
            child = f"{path}.{key}" if path else str(key)
            _fail(where, child, f"未知字段（允许: {', '.join(allowed)}）")


def _require_mapping(value: object, *, where: str, path: str) -> dict[str, object]:
    """必须是映射（YAML object）；`None`（空段）与标量都拒。键一律归一为 str。"""
    if not isinstance(value, dict):
        kind = "空" if value is None else type(value).__name__
        _fail(where, path, f"必须是映射（object），实际是 {kind}")
    return {str(key): item for key, item in value.items()}


def _require_str(value: object, *, where: str, path: str) -> str:
    """必须是非空字符串（首尾空白剥除后判空）。"""
    if not isinstance(value, str):
        _fail(where, path, f"必须是字符串，实际是 {type(value).__name__}")
    text = value.strip()
    if not text:
        _fail(where, path, "不得为空字符串")
    return text


def _require_str_tuple(value: object, *, where: str, path: str) -> tuple[str, ...]:
    """必须是非空的字符串列表。裸标量（`categories: cs.AI`）给专门的提示。"""
    if isinstance(value, str):
        _fail(where, path, f"必须是列表，实际是单个字符串（写作 [{value.strip()}]）")
    if not isinstance(value, list):
        _fail(where, path, f"必须是列表，实际是 {type(value).__name__}")
    if not value:
        _fail(where, path, "列表不得为空（不声明该字段即可）")
    return tuple(
        _require_str(item, where=where, path=f"{path}[{index}]") for index, item in enumerate(value)
    )


def _require_int(value: object, *, where: str, path: str) -> int:
    """必须是整数；`bool` 显式拒绝（YAML `true` 落数值位是笔误，同 config._to_int 口径）。"""
    if isinstance(value, bool) or not isinstance(value, int):
        _fail(where, path, f"必须是整数，实际是 {type(value).__name__}")
    return value


def _require_bool(value: object, *, where: str, path: str) -> bool:
    """必须是布尔（`1`/`"yes"` 一律拒——YAML 有真正的 `true`/`false`）。"""
    if not isinstance(value, bool):
        _fail(where, path, f"必须是布尔（true/false），实际是 {type(value).__name__}")
    return value


def _require_regex(pattern: str, *, where: str, path: str) -> str:
    """正则必须可编译；`re.error` 归一为 CONFIG 类拒载（不留到运行期）。"""
    try:
        re.compile(pattern)
    except re.error as exc:
        _fail(where, path, f"正则非法: {exc}")
    return pattern


def _require_arxiv_query_syntax(text: str, *, where: str, path: str) -> None:
    """arxiv `query` 布尔式的语法早验（Phase 7 T9；plan §4 T9"参数化谓词签名"冻结件，
    范围=ti/abs 字段 + AND/OR/ANDNOT + 引号短语，决策⑤ YAGNI）。

    订阅**加载期**就响亮拒载语法错误（本模块开篇 fail-loud 纪律的同款适用），而
    非留到 `compile.py` 编译 / `filter.py` 求值期才炸——同 `_require_regex` 的
    先例（正则合法性同样在此层把关）。只验语法能否解析成树，不在此处构造真正的
    求值闭包——那是 `filter.PREDICATE_REGISTRY` 的 `arxiv.query_bool` 构造器在
    编译产物被消费时才做的事，两处各自独立解析一次，不跨模块传递解析结果（同
    `_require_regex` 校验后仍把原始字符串交回、`filter._compile_case_insensitive`
    照样重新编译一遍的先例，非新增的重复劳动）。

    只对 `arxiv` 源的 `query` 字段生效——`s2` 同名字段是自由文本，交给 S2 的
    bulk search 端点，没有本地布尔语法。
    """
    try:
        parse_arxiv_query(text)
    except ValueError as exc:
        _fail(where, path, f"arXiv 查询式语法非法: {exc}")


# --- 值对象（冻结件）-------------------------------------------------------


@dataclass(frozen=True)
class SourceSelector:
    """一个源的选择器（design/09 §2 `sources:` 下的一段）。

    单一类型承载六源的字段并集（而非每源一个子类）：T2 的编译器按 `source` 分派，
    读到的字段名与 DSL 逐字一致；哪些字段对哪个源合法由 `SOURCE_FIELDS` 单点定义，
    解析期即已强制——编译器可以放心假设"出现在这里的字段对该源合法"。
    """

    source: str
    # arxiv
    categories: tuple[str, ...] = ()
    query: str | None = None  # arxiv 字段级布尔式 / s2 bulk query
    # ssrn
    networks: tuple[str, ...] = ()
    ejournals: tuple[str, ...] = ()
    # openalex
    concepts: tuple[str, ...] = ()
    from_source_types: tuple[str, ...] = ()
    # s2
    venues: tuple[str, ...] = ()
    fields_of_study: tuple[str, ...] = ()
    # nber
    programs: tuple[str, ...] = ()
    # crossref
    issns: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        """回写为 DSL 片段（只含本源已声明的非空字段，顺序同 `SOURCE_FIELDS`）。"""
        out: dict[str, object] = {}
        for name in SOURCE_FIELDS[self.source]:
            value = getattr(self, name)
            if name in _TEXT_FIELDS:
                if value is not None:
                    out[name] = value
            elif value:
                out[name] = list(value)
        return out


@dataclass(frozen=True)
class LocalFilter:
    """本地二次过滤（design/09 §2 `filters:`；对所有源结果统一执行）。

    语义归 T3（`subs/filter.py`）：`title_regex_any` 任一命中即通过、`exclude_regex`
    任一命中即排除、`min_year` 下界（含）。本类只保证**语法合法**（正则可编译）。
    """

    title_regex_any: tuple[str, ...] = ()
    exclude_regex: tuple[str, ...] = ()
    min_year: int | None = None

    def is_empty(self) -> bool:
        """无任何过滤条件（编译期据此判断有无需要本地补偿的谓词）。"""
        return not self.title_regex_any and not self.exclude_regex and self.min_year is None

    def to_dict(self) -> dict[str, object]:
        out: dict[str, object] = {}
        if self.title_regex_any:
            out["title_regex_any"] = list(self.title_regex_any)
        if self.exclude_regex:
            out["exclude_regex"] = list(self.exclude_regex)
        if self.min_year is not None:
            out["min_year"] = self.min_year
        return out


@dataclass(frozen=True)
class Actions:
    """入库与自动下载（design/09 §2 `actions:`）。

    `auto_fetch_limit` 只在 `ingest="metadata+pdf"` 时有执行意义，但 design/09 §2
    示例一正是 `ingest: metadata` + `auto_fetch_limit: 20` 的写法——故**不做**跨字段
    否决，二者独立校验（限额是上界声明，不是开关）。
    """

    ingest: IngestMode = "metadata"
    auto_fetch_limit: int = 0  # 缺省 0 = 不自动下载（保守侧；示例均显式给值）

    def to_dict(self) -> dict[str, object]:
        return {"ingest": self.ingest, "auto_fetch_limit": self.auto_fetch_limit}


@dataclass(frozen=True)
class Guard:
    """数量护栏（design/09 §2 `guard:`，FR-16）。

    `max_new_per_run`：净新增超过即熔断——本次不入库，只出过载报告（§6.1，T3/T5）。
    `dedupe_against_library`：与既有库按 identifier (scheme,value) 去重（§5 末）。
    """

    max_new_per_run: int = DEFAULT_MAX_NEW_PER_RUN
    dedupe_against_library: bool = DEFAULT_DEDUPE_AGAINST_LIBRARY

    def to_dict(self) -> dict[str, object]:
        return {
            "max_new_per_run": self.max_new_per_run,
            "dedupe_against_library": self.dedupe_against_library,
        }


@dataclass(frozen=True)
class Subscription:
    """一份订阅声明（design/09 §2 的一个 YAML 文件）。

    `sources` 是**有序**元组（顺序 = YAML 声明序 = 编译计划步骤序，确定性输出）。
    序列化拆两半以对齐 `subscription` 表（design/06 §2）：`to_query_dict()` →
    `query_json`（DSL 主体），`guard.to_dict()` → `guard_json`（护栏配置）。
    """

    name: str
    sources: tuple[SourceSelector, ...]
    filters: LocalFilter = field(default_factory=LocalFilter)
    actions: Actions = field(default_factory=Actions)
    guard: Guard = field(default_factory=Guard)
    schedule_hint: str | None = None  # 仅存不调度（cron 外置，design/05 §2）

    def source_names(self) -> tuple[str, ...]:
        """本订阅涉及的源 id（声明序）。"""
        return tuple(selector.source for selector in self.sources)

    def selector_for(self, source: str) -> SourceSelector | None:
        """取某源的选择器；未声明该源时 None。"""
        return next((s for s in self.sources if s.source == source), None)

    def to_query_dict(self) -> dict[str, object]:
        """DSL 主体（不含 guard）→ `subscription.query_json` 的载荷。

        与 `parse_subscription` 严格互逆：`parse(to_query_dict() + guard) == self`
        （`tests/unit/test_subs_model.py` 有 round-trip 专测）。
        """
        out: dict[str, object] = {
            "name": self.name,
            "sources": {s.source: s.to_dict() for s in self.sources},
        }
        filters = self.filters.to_dict()
        if filters:
            out["filters"] = filters
        out["actions"] = self.actions.to_dict()
        if self.schedule_hint is not None:
            out["schedule_hint"] = self.schedule_hint
        return out

    @classmethod
    def from_stored(
        cls, name: str, query_json: str, guard_json: str | None = None
    ) -> "Subscription":
        """从库行（`query_json` + `guard_json`）还原——走与文件加载**同一个**校验器。

        单一解析路径 = 库内存量与文件新写的口径不会漂移；库行损坏（非 JSON、
        `name` 与主键不符）同样响亮报错，不返回半截对象。
        """
        where = f"subscription[{name}]"
        raw = _loads_object(query_json, where=where, path="query_json")
        if guard_json is not None:
            raw["guard"] = _loads_object(guard_json, where=where, path="guard_json")
        parsed = parse_subscription(raw, where=where)
        if parsed.name != name:
            _fail(where, "name", f"库行主键 {name!r} 与 query_json.name {parsed.name!r} 不一致")
        return parsed


def _loads_object(payload: str, *, where: str, path: str) -> dict[str, object]:
    """JSON 文本 → 映射；解析失败或顶层非对象 → 拒载。"""
    try:
        loaded = json.loads(payload)
    except json.JSONDecodeError as exc:
        _fail(where, path, f"JSON 解析失败: {exc}")
    return _require_mapping(loaded, where=where, path=path)


# --- 解析与校验 -------------------------------------------------------------


def parse_subscription(raw: Mapping[str, object], *, where: str = "<subscription>") -> Subscription:
    """把一份已读入的映射校验并构造为 `Subscription`；任何问题 → `SubscriptionInvalid`。

    `where` 是定位前缀（文件路径 / `subscription[name]`），只用于报错消息。
    """
    document = _require_mapping(dict(raw), where=where, path="")
    _reject_unknown(document, _TOP_LEVEL_FIELDS, where=where, path="")

    if "name" not in document:
        _fail(where, "name", "必填字段缺失")
    name = _require_str(document["name"], where=where, path="name")
    if not _NAME_PATTERN.match(name):
        _fail(where, "name", f"订阅名 {name!r} 非法（须匹配 {_NAME_PATTERN.pattern}，kebab-case）")

    if "sources" not in document:
        _fail(where, "sources", "必填字段缺失（至少声明一个源）")
    sources = _parse_sources(document["sources"], where=where)

    filters = (
        _parse_filters(document["filters"], where=where) if "filters" in document else LocalFilter()
    )
    actions = (
        _parse_actions(document["actions"], where=where) if "actions" in document else Actions()
    )
    guard = _parse_guard(document["guard"], where=where) if "guard" in document else Guard()

    schedule_hint = (
        _require_str(document["schedule_hint"], where=where, path="schedule_hint")
        if "schedule_hint" in document
        else None
    )

    return Subscription(
        name=name,
        sources=sources,
        filters=filters,
        actions=actions,
        guard=guard,
        schedule_hint=schedule_hint,
    )


def _parse_sources(raw: object, *, where: str) -> tuple[SourceSelector, ...]:
    """`sources:` 段 → 选择器元组（保持 YAML 声明序）。空 sources 拒载。"""
    mapping = _require_mapping(raw, where=where, path="sources")
    if not mapping:
        _fail(where, "sources", "至少声明一个源（支持: " + ", ".join(sorted(SOURCE_FIELDS)) + "）")
    return tuple(_parse_selector(source, value, where=where) for source, value in mapping.items())


def _parse_selector(source: str, raw: object, *, where: str) -> SourceSelector:
    """一个源的选择器段；未知源 / 未知字段 / 空段一律拒载。"""
    path = f"sources.{source}"
    allowed = SOURCE_FIELDS.get(source)
    if allowed is None:
        _fail(
            where,
            path,
            f"未知源 {source!r}（支持: {', '.join(sorted(SOURCE_FIELDS))}；design/09 §3 能力表）",
        )
    mapping = _require_mapping(raw, where=where, path=path)
    if not mapping:
        _fail(where, path, f"选择器为空（该源可用字段: {', '.join(allowed)}）")
    _reject_unknown(mapping, allowed, where=where, path=path)

    lists: dict[str, tuple[str, ...]] = {}
    texts: dict[str, str] = {}
    for key, value in mapping.items():
        child = f"{path}.{key}"
        if key in _TEXT_FIELDS:
            text = _require_str(value, where=where, path=child)
            if source == "arxiv" and key == "query":
                _require_arxiv_query_syntax(text, where=where, path=child)
            texts[key] = text
        else:
            lists[key] = _require_str_tuple(value, where=where, path=child)

    return SourceSelector(
        source=source,
        categories=lists.get("categories", ()),
        query=texts.get("query"),
        networks=lists.get("networks", ()),
        ejournals=lists.get("ejournals", ()),
        concepts=lists.get("concepts", ()),
        from_source_types=lists.get("from_source_types", ()),
        venues=lists.get("venues", ()),
        fields_of_study=lists.get("fields_of_study", ()),
        programs=lists.get("programs", ()),
        issns=lists.get("issns", ()),
    )


def _parse_filters(raw: object, *, where: str) -> LocalFilter:
    mapping = _require_mapping(raw, where=where, path="filters")
    _reject_unknown(mapping, _FILTER_FIELDS, where=where, path="filters")

    def regexes(key: str) -> tuple[str, ...]:
        if key not in mapping:
            return ()
        patterns = _require_str_tuple(mapping[key], where=where, path=f"filters.{key}")
        return tuple(
            _require_regex(pattern, where=where, path=f"filters.{key}[{index}]")
            for index, pattern in enumerate(patterns)
        )

    min_year: int | None = None
    if "min_year" in mapping:
        min_year = _require_int(mapping["min_year"], where=where, path="filters.min_year")
        if not _MIN_YEAR_FLOOR <= min_year <= _MIN_YEAR_CEIL:
            _fail(
                where,
                "filters.min_year",
                f"年份越界: {min_year}（须在 [{_MIN_YEAR_FLOOR}, {_MIN_YEAR_CEIL}]）",
            )

    return LocalFilter(
        title_regex_any=regexes("title_regex_any"),
        exclude_regex=regexes("exclude_regex"),
        min_year=min_year,
    )


def _parse_actions(raw: object, *, where: str) -> Actions:
    mapping = _require_mapping(raw, where=where, path="actions")
    _reject_unknown(mapping, _ACTION_FIELDS, where=where, path="actions")

    ingest: IngestMode = "metadata"
    if "ingest" in mapping:
        value = _require_str(mapping["ingest"], where=where, path="actions.ingest")
        if value not in _INGEST_MODES:
            _fail(where, "actions.ingest", f"取值须是 {' | '.join(_INGEST_MODES)}，实际 {value!r}")
        ingest = "metadata+pdf" if value == "metadata+pdf" else "metadata"

    auto_fetch_limit = 0
    if "auto_fetch_limit" in mapping:
        auto_fetch_limit = _require_int(
            mapping["auto_fetch_limit"], where=where, path="actions.auto_fetch_limit"
        )
        if auto_fetch_limit < 0:
            _fail(where, "actions.auto_fetch_limit", f"不得为负: {auto_fetch_limit}")

    return Actions(ingest=ingest, auto_fetch_limit=auto_fetch_limit)


def _parse_guard(raw: object, *, where: str) -> Guard:
    """`guard:` 段；缺省补全 `max_new_per_run=200` / `dedupe_against_library=True`。"""
    mapping = _require_mapping(raw, where=where, path="guard")
    _reject_unknown(mapping, _GUARD_FIELDS, where=where, path="guard")

    max_new_per_run = DEFAULT_MAX_NEW_PER_RUN
    if "max_new_per_run" in mapping:
        max_new_per_run = _require_int(
            mapping["max_new_per_run"], where=where, path="guard.max_new_per_run"
        )
        if max_new_per_run < 1:
            _fail(
                where,
                "guard.max_new_per_run",
                f"须 ≥ 1（熔断阈值；实际 {max_new_per_run}）——不设限请调大而非置 0",
            )

    dedupe = DEFAULT_DEDUPE_AGAINST_LIBRARY
    if "dedupe_against_library" in mapping:
        dedupe = _require_bool(
            mapping["dedupe_against_library"], where=where, path="guard.dedupe_against_library"
        )

    return Guard(max_new_per_run=max_new_per_run, dedupe_against_library=dedupe)


# --- 文件/目录加载 ----------------------------------------------------------


class _DuplicateKeySafeLoader(yaml.SafeLoader):
    """`SafeLoader` 子类：同一映射内的重复键 → 拒载（P1-2 热修）。

    PyYAML 的默认行为是"后声明的键静默覆盖前面的"，且不留任何痕迹——用户复制一段
    选择器改分类时手滑重复了 `sources:`、某个源、或某个字段，前一半声明会被悄悄
    丢弃，表现为"订阅文件看起来完整但少了半个领域却不报错"，正是本模块 docstring
    开篇要堵的"静默降级"反模式。

    覆盖点是 `construct_mapping`（保留 `SafeConstructor.flatten_mapping` 的 `<<`
    合并键语义，只是在原有"后者覆盖前者"的赋值前插入重复检测），对**全部**映射
    节点生效而不区分层级——顶层字段、`sources:` 内的源名、单个选择器内的字段，
    只要在同一 YAML 映射里重复出现，都会被抓住。
    """

    def construct_mapping(self, node: yaml.MappingNode, deep: bool = False) -> dict[Hashable, Any]:
        self.flatten_mapping(node)
        mapping: dict[Hashable, Any] = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if not isinstance(key, Hashable):
                raise yaml.constructor.ConstructorError(
                    "while constructing a mapping",
                    node.start_mark,
                    "found unhashable key",
                    key_node.start_mark,
                )
            if key in mapping:
                raise yaml.constructor.ConstructorError(
                    "while constructing a mapping",
                    node.start_mark,
                    f"发现重复键 {key!r}（PyYAML 默认会静默用后者覆盖前者）",
                    key_node.start_mark,
                )
            mapping[key] = self.construct_object(value_node, deep=deep)
        return mapping


def load_subscription_file(path: Path) -> Subscription:
    """加载单个订阅 YAML；读取/解析/校验任一环节失败 → `SubscriptionInvalid`。

    附加硬约束：文件名 stem 必须等于 `name`（`llm-agents.yaml` ↔ `name: llm-agents`）
    ——`crawler watch <name>` 靠 name 定位文件，两者不一致会让"改了文件却没生效"
    这类问题变得难以自证。
    """
    where = str(path)
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        _fail(where, "", f"文件读取失败（{type(exc).__name__}）: {exc}")

    try:
        raw = yaml.load(text, Loader=_DuplicateKeySafeLoader)  # 子类仍是 SafeLoader，非泛型 load
    except yaml.YAMLError as exc:
        _fail(where, "", f"YAML 解析失败: {exc}")

    if raw is None:
        _fail(where, "", "文件为空")
    document = _require_mapping(raw, where=where, path="")

    subscription = parse_subscription(document, where=where)
    if path.stem != subscription.name:
        _fail(
            where,
            "name",
            f"文件名 stem {path.stem!r} 与 name {subscription.name!r} 不一致",
        )
    return subscription


def load_subscriptions_dir(directory: Path) -> list[Subscription]:
    """加载 `directory` **顶层**的全部 `*.yaml`（按文件名排序，确定性输出）。

    - 不递归：`presets/` 子目录是模板不是活订阅（模块 docstring "目录语义"）；
    - 目录不存在/不是目录 → 拒载（不静默返回空——"订阅一个都没跑"必须有声音）；
      空目录合法（返回 `[]`，用户尚未建订阅）；
    - 任一文件失败即整体拒载（fail-loud）。

    `name` 唯一性无需在此再查：文件名 stem 必须等于 `name`（`load_subscription_file`），
    而同目录同扩展名的 stem 天然唯一——重名在文件系统层就不可能发生。
    """
    if not directory.is_dir():
        _fail(str(directory), "", "订阅目录不存在或不是目录")

    return [load_subscription_file(path) for path in sorted(directory.glob("*.yaml"))]


__all__ = [
    "DEFAULT_DEDUPE_AGAINST_LIBRARY",
    "DEFAULT_MAX_NEW_PER_RUN",
    "SOURCE_FIELDS",
    "Actions",
    "Guard",
    "IngestMode",
    "LocalFilter",
    "SourceSelector",
    "Subscription",
    "load_subscription_file",
    "load_subscriptions_dir",
    "parse_subscription",
]
