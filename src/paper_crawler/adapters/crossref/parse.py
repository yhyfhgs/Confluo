"""Crossref REST `works` 响应解析与字段映射（design/adapters/aggregators.md §5.1 逐行）。

零网络：输入已取回的响应 `bytes`（JSON），输出中间记录 `CrossrefRecord` 与页信息
`CrossrefWorksPage`（与网络/存储解耦，供 adapter 主体消费）。只用标准库 `json`——
不引入第三方依赖（沿 arxiv/_oai「XML 走 stdlib」先例）。

字段映射（§5.1 表逐行）：
- title = `items[].title[0]`（数组取 [0]，空白规整化）；**空数组/缺失 → 跳过该记录 +
  计 `skipped_untitled`**（★裁决 2026-07-22：title 是 06 `paper.title NOT NULL`；占位符
  标题会污染 `title_norm` 弱信号匹配面——宁缺勿污，不占位）。
- doi = `items[].DOI` → `ids.normalize_doi()`；**缺 DOI → 跳过 + 计 `skipped_doiless`**
  （期刊 works 恒有 DOI；无 DOI 者既无强合并锚点、又无稳定身份，PaperStub 须 ≥1
  identifier，故跳过而非造无锚点 stub。罕见于期刊，§5.1）。
- pub_date = `published-print`→`published-online`→`issued` 的 `date-parts` 首个非空族
  （partial 日期容 'YYYY'/'YYYY-MM'）。
- volume/issue = `items[].volume` / `items[].issue`（文本，容 'S1' 特刊）→ 入 `meta`。
- abstract = `items[].abstract`（JATS，常缺 ~70%）→ None，不阻塞（06 §5 约定）。
- authors = `items[].author[]`（`given`/`family`，机构作者退化到 `name`）。
- paper_count_claimed = `message.total-results`（窗口/facet 计数）。

错误：JSON 语法错误 / 顶层缺 `message` → `PARSE`。「total-results>0 但 items 空解析
0 条」的 canary 标红判定在 adapter 层（须知是否首页/续页，§5.1 错误表）——本层只如实
报出 `item_count`（items 数组长度）供其判定。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from paper_crawler.errors import CrawlerError, ErrorClass
from paper_crawler.ids import normalize_doi
from paper_crawler.types import PaperStub

# pub_date 日期族选择优先级（§5.1）：印刷版 → 在线版 → issued。
_DATE_FIELDS = ("published-print", "published-online", "issued")
_WS_RE = re.compile(r"\s+")


# --- 中间记录 --------------------------------------------------------------------------------


@dataclass(frozen=True)
class CrossrefRecord:
    """一条 works 记录解析后的统一中间形状（title/doi 已规整）。"""

    doi: str  # 已 normalize_doi（parse_works_page 产出者恒非空；单条 healthcheck 可空）
    title: str  # title[0]，空白规整化
    pub_date: str | None
    volume: str | None
    issue: str | None
    abstract: str | None
    authors: tuple[str, ...]


@dataclass(frozen=True)
class CrossrefWorksPage:
    """一页 `works` 响应：记录 + 窗口计数 + 深翻游标 + 跳过统计 + 原始 items 数。"""

    records: tuple[CrossrefRecord, ...]
    total_results: int | None  # message.total-results（paper_count_claimed 源）
    next_cursor: str | None  # message.next-cursor（深翻续页；末页仍可能带值，终止靠 item_count==0）
    item_count: int  # items 数组长度（未过滤）——termination/anomaly 判定用（§5.1）
    skipped_untitled: int  # title 空数组/缺失被跳过数
    skipped_doiless: int  # 缺 DOI 被跳过数


# --- 公开 API：works 列表页 -------------------------------------------------------------------


def parse_works_page(data: bytes) -> CrossrefWorksPage:
    """解析一页 `/journals/{issn}/works`（或带 cursor 的续页）为 `CrossrefWorksPage`。

    逐 item 映射；title 空 → 跳过并计 `skipped_untitled`；DOI 缺 → 跳过并计
    `skipped_doiless`。不在此判「total>0 items 空」anomaly（adapter 层按首/续页判）。
    """
    message = _message(data)
    total = _int_or_none(message.get("total-results"))
    next_cursor = _nonempty_str(message.get("next-cursor"))
    items = message.get("items")
    item_list = items if isinstance(items, list) else []

    records: list[CrossrefRecord] = []
    skipped_untitled = 0
    skipped_doiless = 0
    for item in item_list:
        if not isinstance(item, dict):
            skipped_untitled += 1  # 非对象 item：无 title，按无标题跳过计
            continue
        title = _first_title(item.get("title"))
        if title is None:
            skipped_untitled += 1
            continue
        doi = _extract_doi(item.get("DOI"))
        if not doi:
            skipped_doiless += 1
            continue
        records.append(_to_record(item, title=title, doi=doi))

    return CrossrefWorksPage(
        records=tuple(records),
        total_results=total,
        next_cursor=next_cursor,
        item_count=len(item_list),
        skipped_untitled=skipped_untitled,
        skipped_doiless=skipped_doiless,
    )


# --- 公开 API：facet 年计数（discover 时间轴）------------------------------------------------


def parse_facet_years(data: bytes) -> tuple[dict[int, int], int | None]:
    """解析 `rows=0&facet=published:*` 响应 → (year→count, total-results)。

    `message.facets.published.values` = {year_str: count}。非整数年/计数键静默跳过
    （防御畸形）。total-results 为整刊全史计数（paper_count_claimed 兜底）。
    """
    message = _message(data)
    total = _int_or_none(message.get("total-results"))
    year_counts: dict[int, int] = {}

    facets = message.get("facets")
    published = facets.get("published") if isinstance(facets, dict) else None
    values = published.get("values") if isinstance(published, dict) else None
    if isinstance(values, dict):
        for raw_year, raw_count in values.items():
            year = _int_or_none(raw_year)
            count = _int_or_none(raw_count)
            if year is not None and count is not None:
                year_counts[year] = count
    return year_counts, total


# --- 公开 API：单条 work（healthcheck）-------------------------------------------------------


def parse_single_work_title(data: bytes) -> str:
    """解析 `/works/{doi}` 单条响应，返回空白规整化的 `title[0]`；缺 title → `PARSE`。

    healthcheck 只需比对 title[0]（非纯计数——total-results 随出版增长会漂，§5.1）。
    """
    message = _message(data)
    title = _first_title(message.get("title"))
    if title is None:
        raise CrawlerError(ErrorClass.PARSE, "crossref single work has empty/missing title[0]")
    return title


# --- PaperStub 转换 --------------------------------------------------------------------------


def to_paper_stub(record: CrossrefRecord) -> PaperStub:
    """把中间记录转成 `PaperStub`（§5.1 映射；identifiers 恒含 (doi, 归一值)）。

    volume/issue 入 `meta`（PaperStub 无这两个专属字段，卷期落库聚合在 ingest/issue
    层，06 §5）。source provenance tag='crossref' 由 adapter 传给 MergeEngine.ingest。
    """
    meta: list[tuple[str, str]] = []
    if record.volume:
        meta.append(("volume", record.volume))
    if record.issue:
        meta.append(("issue", record.issue))
    return PaperStub(
        title=record.title,
        identifiers=(("doi", record.doi),),
        year=_year_from_date(record.pub_date),
        pub_date=record.pub_date,
        abstract=record.abstract,
        authors=record.authors,
        meta=tuple(meta),
    )


# --- 模块级纯函数 -----------------------------------------------------------------------------


def _message(data: bytes) -> dict[str, object]:
    """取 JSON 顶层 `message` 对象；JSON 语法错误或缺 `message` → `PARSE`。"""
    try:
        root = json.loads(data)
    except (json.JSONDecodeError, ValueError) as exc:
        raise CrawlerError(ErrorClass.PARSE, f"crossref response is not valid JSON: {exc}") from exc
    if not isinstance(root, dict):
        raise CrawlerError(ErrorClass.PARSE, "crossref response top-level is not an object")
    message = root.get("message")
    if not isinstance(message, dict):
        raise CrawlerError(ErrorClass.PARSE, "crossref response missing 'message' object")
    return message


def _to_record(item: dict[str, object], *, title: str, doi: str) -> CrossrefRecord:
    return CrossrefRecord(
        doi=doi,
        title=title,
        pub_date=_pub_date(item),
        volume=_nonempty_str(item.get("volume")),
        issue=_nonempty_str(item.get("issue")),
        abstract=_nonempty_str(item.get("abstract")),
        authors=_authors(item.get("author")),
    )


def _first_title(raw: object) -> str | None:
    """`title` 数组取 [0] 并空白规整化；空数组/缺失/首元素空白 → None（跳过信号）。"""
    if not isinstance(raw, list) or not raw:
        return None
    first = raw[0]
    if not isinstance(first, str):
        return None
    collapsed = _WS_RE.sub(" ", first).strip()
    return collapsed or None


def _extract_doi(raw: object) -> str:
    """`DOI` → `normalize_doi`；非字符串/空 → 空串（调用方按"无 DOI"跳过）。"""
    if not isinstance(raw, str):
        return ""
    return normalize_doi(raw)


def _pub_date(item: dict[str, object]) -> str | None:
    """published-print → published-online → issued 的 date-parts 首个非空族（§5.1）。"""
    for field in _DATE_FIELDS:
        formatted = _format_date_parts(item.get(field))
        if formatted is not None:
            return formatted
    return None


def _format_date_parts(raw: object) -> str | None:
    """Crossref `{"date-parts": [[Y,M,D]]}` → 'YYYY-MM-DD'（partial 容 'YYYY'/'YYYY-MM'）。

    `date-parts` 常见形态 `[[2024, 3, 15]]`；未知日期为 `[[]]`（空内层）→ None。
    """
    if not isinstance(raw, dict):
        return None
    parts = raw.get("date-parts")
    if not isinstance(parts, list) or not parts:
        return None
    first = parts[0]
    if not isinstance(first, list):
        return None
    nums = [p for p in first if isinstance(p, int)]
    if not nums:
        return None
    if len(nums) >= 3:
        return f"{nums[0]:04d}-{nums[1]:02d}-{nums[2]:02d}"
    if len(nums) == 2:
        return f"{nums[0]:04d}-{nums[1]:02d}"
    return f"{nums[0]:04d}"


def _authors(raw: object) -> tuple[str, ...]:
    """`author[]` → ('Given Family', ...)；机构作者退化到 `name`；空/畸形跳过。"""
    if not isinstance(raw, list):
        return ()
    names: list[str] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        given = entry.get("given")
        family = entry.get("family")
        parts = [p.strip() for p in (given, family) if isinstance(p, str) and p.strip()]
        if parts:
            names.append(" ".join(parts))
            continue
        org = entry.get("name")  # 机构/团体作者只有 name
        if isinstance(org, str) and org.strip():
            names.append(org.strip())
    return tuple(names)


def _year_from_date(pub_date: str | None) -> int | None:
    if pub_date is None or len(pub_date) < 4 or not pub_date[:4].isdigit():
        return None
    return int(pub_date[:4])


def _nonempty_str(raw: object) -> str | None:
    """文本值取非空白串；非字符串/空白 → None。"""
    if isinstance(raw, str):
        stripped = raw.strip()
        return stripped or None
    return None


def _int_or_none(raw: object) -> int | None:
    """宽容转 int（Crossref facet 键为字符串年、计数为 int；total-results 为 int）。"""
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            return int(raw.strip())
        except ValueError:
            return None
    return None


__all__ = [
    "CrossrefRecord",
    "CrossrefWorksPage",
    "parse_facet_years",
    "parse_single_work_title",
    "parse_works_page",
    "to_paper_stub",
]
