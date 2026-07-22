"""OpenReview JSON 解析器（design/adapters/openreview.md §2/§4/§6）。

**零网络**：输入已取回的响应 `bytes`，输出中间记录 `Note` / `NotesPage`。只用标准库
`json`。两代 API 的 note `content` 结构不同（历史遗留），本模块内部吸收差异：

- **v2**（`api2.openreview.net`）：``content.<field>.value`` 嵌套取值。
- **v1**（`api.openreview.net`）：``content.<field>`` 直接取值。

版本判定**不按年份**（官方明言不可靠），而按 group 的 `domain` 字段有无（有=v2、无=v1，
勘察 §1 [DOC]）——`api_version_from_groups`。解析器按版本双套；结构与版本预期不符
（如 v2 期望 `.value` 包裹却拿到裸值）→ `PARSE`（canary 标红的 v1/v2 错配信号，§6）。

`to_paper_stub` 落地 §4 字段映射裁决：``identifiers`` 恒为单一 ``(('openreview',
forum),)``（顶层论文帖 `id == forum`，原样保留大小写、无归一）；content 内 doi/arxiv
线索入 `meta`（键 'doi'/'arxiv'），**绝不产出为 identifier**（防跨源早合并，Phase 3
ingest 建边——arxiv R3 裁决先例）。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum

from paper_crawler.errors import CrawlerError, ErrorClass
from paper_crawler.types import PaperStub


class ApiVersion(StrEnum):
    """note 正文归属的 API 版本（决定 base URL 与 content 解析方式）。"""

    V1 = "v1"
    V2 = "v2"


# base URLs（勘察 §1 [DOC] OpenAPI）。
_API_BASE: dict[ApiVersion, str] = {
    ApiVersion.V1: "https://api.openreview.net",
    ApiVersion.V2: "https://api2.openreview.net",
}


def api_base_url(version: ApiVersion) -> str:
    """版本 → notes 端点 base URL。"""
    return _API_BASE[version]


# --- 中间记录 --------------------------------------------------------------------------------


@dataclass(frozen=True)
class Note:
    """一条 OpenReview note 的最小规格（v1/v2 解析后统一形状）。

    ``forum`` = 讨论主帖 id；顶层论文帖自身 ``id == forum``。``venueid`` = 该 note 的
    `content.venueid`（接收判定依据）；``pdf`` = `content.pdf` 相对路径（`/pdf/<hex>.pdf`）
    或 None（无 pdf 字段——2013/2014 届正文在 arXiv，正常态）。
    """

    id: str
    forum: str
    venueid: str | None
    title: str | None
    abstract: str | None
    pdf: str | None
    supplementary_material: str | None
    authors: tuple[str, ...]
    doi: str | None
    arxiv: str | None


@dataclass(frozen=True)
class NotesPage:
    """一页 `/notes` 响应的解析产物（供 adapter 翻页消费）。

    ``count`` = 匹配总数（**非页内条数**，勘察 §5）——adapter 据此判定是否续页。
    空态 200 ``{"notes":[],"count":0}`` 是合法空结果（`notes` 空、`count` 0），非错误。
    """

    notes: tuple[Note, ...]
    count: int


# --- 版本判定（groups 端点的 domain 字段）-----------------------------------------------------


def api_version_from_groups(data: bytes, venueid: str) -> ApiVersion:
    """从 `GET /groups?id=<venueid>` 响应判定 note 归属版本：有 `domain` → v2、无 → v1。

    envelope 形态 ``{"groups":[{...}],"count":N}``；取 id 匹配的 group（缺省首个）看
    `domain` 键有无。groups 为空（`count:0` 或空数组）→ `GONE`（该 venue group 不存在
    ——2015/2016 应由届表 None 前置拦截、不发此查询；走到这里即真异常）。畸形 JSON → `PARSE`。
    """
    doc = _load_json(data)
    groups = doc.get("groups") if isinstance(doc, dict) else None
    if not isinstance(groups, list) or not groups:
        raise CrawlerError(
            ErrorClass.GONE, f"openreview groups response has no group for {venueid!r}"
        )
    group = _match_group(groups, venueid)
    return ApiVersion.V2 if "domain" in group else ApiVersion.V1


def _match_group(groups: list[object], venueid: str) -> dict[str, object]:
    """在 groups 列表里找 id==venueid 的 group；找不到时退回首个 dict（envelope 保证匹配）。"""
    first_dict: dict[str, object] | None = None
    for entry in groups:
        if not isinstance(entry, dict):
            continue
        if first_dict is None:
            first_dict = entry
        if entry.get("id") == venueid:
            return entry
    if first_dict is None:
        raise CrawlerError(ErrorClass.PARSE, "openreview groups response has no object entries")
    return first_dict


def group_ids(data: bytes) -> list[str]:
    """从 groups envelope 抽出所有 group id（healthcheck 匿名基线断言用）。"""
    doc = _load_json(data)
    groups = doc.get("groups") if isinstance(doc, dict) else None
    if not isinstance(groups, list):
        return []
    return [
        gid
        for entry in groups
        if isinstance(entry, dict) and isinstance((gid := entry.get("id")), str)
    ]


# --- notes 解析（v1/v2 双套）------------------------------------------------------------------


def parse_notes_page(data: bytes, version: ApiVersion) -> NotesPage:
    """解析一页 `/notes` 响应为 `NotesPage`（`version` 决定 content 取值方式）。

    顶层 ``notes`` 缺失或非列表 → `PARSE`；``count`` 缺失回退为页内条数（保守）。
    单条 note 的 content 结构与版本预期不符（v2 缺 `.value` 包裹等）→ `PARSE`（错配信号）。
    """
    doc = _load_json(data)
    if not isinstance(doc, dict):
        raise CrawlerError(ErrorClass.PARSE, "openreview notes response is not a JSON object")
    raw_notes = doc.get("notes")
    if not isinstance(raw_notes, list):
        raise CrawlerError(ErrorClass.PARSE, "openreview notes response missing 'notes' array")
    notes = tuple(_parse_note(entry, version) for entry in raw_notes)
    raw_count = doc.get("count")
    # count 缺失/非整数（含 bool）回退为页内条数（保守）。
    if isinstance(raw_count, int) and not isinstance(raw_count, bool):
        count = raw_count
    else:
        count = len(notes)
    return NotesPage(notes=notes, count=count)


def _parse_note(entry: object, version: ApiVersion) -> Note:
    if not isinstance(entry, dict):
        raise CrawlerError(ErrorClass.PARSE, "openreview note entry is not a JSON object")
    note_id = entry.get("id")
    if not isinstance(note_id, str) or not note_id:
        raise CrawlerError(ErrorClass.PARSE, f"openreview note missing 'id': {entry!r}")
    # forum 缺省回退到 id（顶层论文帖 id==forum；防御性——正常响应恒带 forum）。
    forum_raw = entry.get("forum")
    forum = forum_raw if isinstance(forum_raw, str) and forum_raw else note_id

    content = entry.get("content")
    if not isinstance(content, dict):
        raise CrawlerError(
            ErrorClass.PARSE, f"openreview note {note_id!r} missing 'content' object"
        )

    return Note(
        id=note_id,
        forum=forum,
        venueid=_content_str(content, "venueid", version, note_id),
        title=_content_str(content, "title", version, note_id),
        abstract=_content_str(content, "abstract", version, note_id),
        pdf=_content_str(content, "pdf", version, note_id),
        supplementary_material=_content_str(content, "supplementary_material", version, note_id),
        authors=_content_authors(content, version, note_id),
        doi=_content_str(content, "doi", version, note_id),
        # arxiv 线索：2013/2014 常见的显式字段；键名可能是 'arxiv' 或 '_arxiv'（宽松探测）。
        arxiv=_content_str(content, "arxiv", version, note_id)
        or _content_str(content, "_arxiv", version, note_id),
    )


def _content_raw(
    content: dict[str, object], field: str, version: ApiVersion, note_id: str
) -> object:
    """取 content 字段的**原始值**并按版本解包：v2 拆 `.value`、v1 直取。

    结构与版本预期不符（v2 期望 `{"value": ...}` 却拿裸值、v1 却拿到 `.value` 包裹）
    → `PARSE`——这是 v1/v2 解析器错配的确定性信号（§6 canary 标红）。字段缺席返回 None。
    """
    raw = content.get(field)
    if raw is None:
        return None
    if version is ApiVersion.V2:
        if not isinstance(raw, dict) or "value" not in raw:
            raise CrawlerError(
                ErrorClass.PARSE,
                f"openreview v2 note {note_id!r} field {field!r} lacks .value wrapper "
                f"(v1/v2 parser mismatch?): {raw!r}",
            )
        return raw["value"]
    # v1：直取。裸值意外带 {"value": ...} 包裹 → 版本错配。
    if isinstance(raw, dict) and set(raw.keys()) == {"value"}:
        raise CrawlerError(
            ErrorClass.PARSE,
            f"openreview v1 note {note_id!r} field {field!r} has unexpected .value wrapper "
            f"(v1/v2 parser mismatch?): {raw!r}",
        )
    return raw


def _content_str(
    content: dict[str, object], field: str, version: ApiVersion, note_id: str
) -> str | None:
    """content 字段 → 规整化字符串或 None（非字符串标量原样 str 化被拒为 None）。"""
    value = _content_raw(content, field, version, note_id)
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return None


def _content_authors(
    content: dict[str, object], version: ApiVersion, note_id: str
) -> tuple[str, ...]:
    """content.authors → 作者名元组（列表值；非列表或空 → 空元组）。"""
    value = _content_raw(content, "authors", version, note_id)
    if not isinstance(value, list):
        return ()
    return tuple(stripped for item in value if isinstance(item, str) and (stripped := item.strip()))


# --- accepted 判定与 PaperStub 转换 -----------------------------------------------------------


def is_accepted(note: Note, venueid: str) -> bool:
    """接收判定（§4 ④）：``content.venueid == 主会 venue id`` 即接收。

    被拒/撤稿/desk-reject 的 venueid 落 `*_Submission/Withdrawn/Desk_Rejected` 类值
    （≠ 主会 id）→ 排除。venueid 缺失（None）→ 非接收（保守）。
    """
    return note.venueid == venueid


# 资产定位符的 meta 键（adapter 私有）：enumerate 把 note 的 pdf/SI 相对路径经 meta
# 携带到 resolve（pipeline 在 enumerate→DB→resolve 之间只经 meta_json round-trip 重建
# stub，content 不复存在——见 stages._paper_stub）。resolve 据此纯构造 URL；无 pdf 键
# 即「note 无 pdf 字段」→ 产 0 plan（§4）。**Phase 3 ingest 应只认 'doi'/'arxiv' 语义
# 线索键、忽略这些 adapter 私有键**（键名以 openreview_ 前缀显式隔离）。
META_PDF_PATH = "openreview_pdf"
META_SI_PATH = "openreview_si"

# `PaperStub.meta` 白名单（Phase 2 审查 concern，Phase 3 检查单 #6 收口）：`to_paper_stub`
# 目前实际写入 meta 的业务键只有下面 4 个（逐一对应关系见其下方 if 分支）——本常量把这个
# "现状"显式固化为结构性防线，而非仅靠 if 分支自然限定。OpenReview note.content 可能携带
# 任意站点字段（含潜在评审内部字段），本 adapter **绝不**做 `for k, v in content.items()`
# 式的整体透传；即便未来维护者不慎在 `to_paper_stub` 内加一行未经评审的新键，
# `_whitelist_meta` 也会在写入 `PaperStub` 前把它结构性丢弃，不会悄悄流入 meta_json：
#
# - ``doi`` / ``arxiv``：跨源关联线索（§4 ⑥ 裁决——只入 meta，绝不产出为 identifier，
#   防跨源早合并，Phase 3 ingest 建边前提）；
# - ``META_PDF_PATH`` / ``META_SI_PATH``：adapter 私有资产定位符（见上方常量注释），
#   `resolve_assets` 纯构造 URL 用，Phase 3 ingest 应忽略。
_META_KEY_WHITELIST: frozenset[str] = frozenset({"doi", "arxiv", META_PDF_PATH, META_SI_PATH})


def _whitelist_meta(pairs: list[tuple[str, str]]) -> tuple[tuple[str, str], ...]:
    """丢弃 `_META_KEY_WHITELIST` 之外的键（结构性防御，不依赖调用方自律）。

    保留原有相对顺序；白名单外键整条 (key, value) 一并丢弃，不做值脱敏——脱敏解的是
    "敏感值不落日志"，这里解的是"未评审的键不落库"，两者是不同红线（AC-0 对应 redact()）。
    """
    return tuple(pair for pair in pairs if pair[0] in _META_KEY_WHITELIST)


def to_paper_stub(note: Note, *, year: int | None) -> PaperStub:
    """`Note` → `PaperStub`（§4 ⑥ 字段映射裁决逐字执行）。

    ``identifiers`` 恒为单一 ``(('openreview', forum),)``（原样，无大小写归一）；
    doi/arxiv 线索入 `meta`（键 'doi'/'arxiv'），绝不产出为 identifier（防跨源早合并）。
    pdf/SI 相对路径亦入 `meta`（adapter 私有键，见常量注释）供 resolve 纯构造 URL。
    title 缺失（None）→ `PARSE`（论文帖必有标题；缺失即结构异常）。最终 `meta` 经
    `_whitelist_meta` 收口（见该函数与 `_META_KEY_WHITELIST` docstring）。
    """
    if note.title is None:
        raise CrawlerError(ErrorClass.PARSE, f"openreview note {note.forum!r} has no title")
    meta: list[tuple[str, str]] = []
    if note.doi:
        meta.append(("doi", note.doi))
    if note.arxiv:
        meta.append(("arxiv", note.arxiv))
    if note.pdf:
        meta.append((META_PDF_PATH, note.pdf))
    if note.supplementary_material:
        meta.append((META_SI_PATH, note.supplementary_material))
    return PaperStub(
        title=note.title,
        identifiers=(("openreview", note.forum),),
        year=year,
        abstract=note.abstract,
        authors=note.authors,
        meta=_whitelist_meta(meta),
    )


# --- 共享小工具 -------------------------------------------------------------------------------


def _load_json(data: bytes) -> object:
    try:
        return json.loads(data)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise CrawlerError(ErrorClass.PARSE, f"malformed openreview json: {exc}") from exc


__all__ = [
    "META_PDF_PATH",
    "META_SI_PATH",
    "ApiVersion",
    "Note",
    "NotesPage",
    "api_base_url",
    "api_version_from_groups",
    "group_ids",
    "is_accepted",
    "parse_notes_page",
    "to_paper_stub",
]
