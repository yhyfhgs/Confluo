"""`schema.rnc` 描述的 Collection→Volume→Paper XML 解析器（design §4 enumerate_issue）。

**零网络**：输入已取回的响应 `bytes`，输出中间记录 `RawCollection`/`RawVolume`/
`RawPaper`，再由 `to_paper_stub` 落地字段映射裁决。只用标准库
`xml.etree.ElementTree`（同 arxiv `parse.py` 先例）。

结构（`data/xml/schema.rnc` 权威定义，勘察 §1 全文抓取）：``Collection(id) →
Volume(id,type)* → Paper(id)*``；`Volume` 恒含 `Meta`（`year` 必填、`month` 可选），
`Paper` 除 `title`/`bibkey` 外多数字段可选。`title`/`abstract` 属
`InlineMarkupText`/`MarkupText`（可含 `<fixed-case>`/`<i>` 等内联标记）——用
`itertext()` 拼接取纯文本，天然剥掉标记外壳。

Findings 跨文件 join（结构性核心，§4）：findings 文件的 volume id **就是**目标 venue
的 slug（如 `emnlp`），但 volume 内 `<meta><venue>` 恒为字面 `"findings"`（非目标
venue 名）——过滤键是 **volume id**，不是 meta/venue 文本。`to_paper_stub` 因此把
`track` 作为独立参数传入而非从 volume id 派生：主文件路径传原始 volume id
（main/tutorial/demo/industry…），findings 路径的调用方（`adapter.py`）**固定传字面值
`"findings"`**——否则该论文的 `meta['track']` 会变成语义重复的 volume id（如
"emnlp"，与 venue 自身同名，掩盖"这是 Findings track"这一事实）。
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass

from paper_crawler.adapters.acl_anthology import ids
from paper_crawler.errors import CrawlerError, ErrorClass
from paper_crawler.types import PaperStub

# --- PaperStub.meta 键（adapter 私有命名空间，同 openreview META_* 先例）------------------------

META_TRACK = "track"
META_BIBKEY = "bibkey"
META_LICENSE = "license"
META_PAGES = "pages"
META_COLLECTION = "anthology_collection"
# 附件本地文件名；一篇可有多个，故同键可在 meta 元组内重复出现（tuple-of-tuples 天然
# 允许重复键，resolve_assets 据此逐个产 SI AssetPlan——见 adapter.py，design §4 [UNRESOLVED]）。
META_ATTACHMENT = "acl_anthology_attachment"

_ANTHOLOGY_SCHEME = "anthology"
_DOI_SCHEME = "doi"

_MONTH_NAMES: dict[str, int] = {
    name: index
    for index, name in enumerate(
        [
            "january",
            "february",
            "march",
            "april",
            "may",
            "june",
            "july",
            "august",
            "september",
            "october",
            "november",
            "december",
        ],
        start=1,
    )
}


# --- 中间记录 --------------------------------------------------------------------------------


@dataclass(frozen=True)
class RawPaper:
    """一篇 `<paper>` 的解析后原始字段（未经 identifier/meta 映射）。"""

    id_attr: str
    title: str
    authors: tuple[str, ...]
    pages: str | None
    abstract: str | None
    url_text: str | None
    doi: str | None
    bibkey: str | None
    attachments: tuple[str, ...]
    year: int | None
    month: str | None


@dataclass(frozen=True)
class RawVolume:
    """一个 `<volume>`：id + volume 级 `<meta>` 的 year/month 兜底 + 其下全部 paper。"""

    id: str
    year: int | None
    month: str | None
    papers: tuple[RawPaper, ...]


@dataclass(frozen=True)
class RawCollection:
    """一份 XML 文件的顶层 `<collection>`：id + 全部 volume。"""

    id: str
    volumes: tuple[RawVolume, ...]


# --- XML 解析（xml.etree，零网络）---------------------------------------------------------------


def parse_collection_xml(data: bytes) -> RawCollection:
    """解析一份 bulk XML 文件（`<collection>` 根）为 `RawCollection`。

    XML 语法错误（截断响应等）→ `PARSE`；根元素非 `<collection>` 或缺 `id` 属性同样
    → `PARSE`（结构与权威 schema 不符，§6 失败模式映射）。
    """
    root = _fromstring(data)
    if root.tag != "collection":
        raise CrawlerError(
            ErrorClass.PARSE, f"expected <collection> root element, got <{root.tag}>"
        )
    collection_id = root.get("id")
    if not collection_id:
        raise CrawlerError(ErrorClass.PARSE, "<collection> is missing required 'id' attribute")
    volumes = tuple(_parse_volume(volume_el) for volume_el in root.findall("volume"))
    return RawCollection(id=collection_id, volumes=volumes)


def _parse_volume(volume_el: ET.Element) -> RawVolume:
    volume_id = volume_el.get("id")
    if not volume_id:
        raise CrawlerError(ErrorClass.PARSE, "<volume> is missing required 'id' attribute")
    meta_el = volume_el.find("meta")
    year = _optional_int(meta_el.findtext("year")) if meta_el is not None else None
    month = _optional_text(meta_el, "month") if meta_el is not None else None
    papers = tuple(_parse_paper(paper_el) for paper_el in volume_el.findall("paper"))
    return RawVolume(id=volume_id, year=year, month=month, papers=papers)


def _parse_paper(paper_el: ET.Element) -> RawPaper:
    id_attr = paper_el.get("id")
    if not id_attr:
        raise CrawlerError(ErrorClass.PARSE, "<paper> is missing required 'id' attribute")
    context = f"paper id={id_attr!r}"

    title = _required_itertext(paper_el, "title", context=context)
    authors = tuple(_person_name(author_el) for author_el in paper_el.findall("author"))
    authors = tuple(name for name in authors if name)
    pages = _optional_text(paper_el, "pages")
    abstract = _optional_itertext(paper_el, "abstract")

    url_el = paper_el.find("url")
    url_text = None
    if url_el is not None and url_el.text and url_el.text.strip():
        url_text = url_el.text.strip()

    doi = _optional_text(paper_el, "doi")
    bibkey = _optional_text(paper_el, "bibkey")
    attachments = tuple(
        stripped
        for attachment_el in paper_el.findall("attachment")
        if attachment_el.text and (stripped := attachment_el.text.strip())
    )
    year = _optional_int(paper_el.findtext("year"))
    month = _optional_text(paper_el, "month")

    return RawPaper(
        id_attr=id_attr,
        title=title,
        authors=authors,
        pages=pages,
        abstract=abstract,
        url_text=url_text,
        doi=doi,
        bibkey=bibkey,
        attachments=attachments,
        year=year,
        month=month,
    )


def _person_name(person_el: ET.Element) -> str:
    first = person_el.findtext("first")
    last = person_el.findtext("last")
    parts = [p.strip() for p in (first, last) if p and p.strip()]
    return " ".join(parts)


# --- PaperStub 映射（design §4 字段映射裁决逐字执行）---------------------------------------------


def to_paper_stub(
    collection_id: str,
    volume_id: str,
    paper: RawPaper,
    *,
    track: str,
    volume_year: int | None,
    volume_month: str | None,
) -> PaperStub:
    """`RawPaper` → `PaperStub`（§4 字段映射裁决）。

    - `identifiers`：`('anthology', 原样 id)` 恒产（主 identifier，index 0）；
      `<doi>` 存在时追加 `('doi', 归一化裸 DOI)`（§9-★3：本源自持前缀，产第二 identifier）。
      anthology_id **优先读 `<url>`**（`ids.normalize_from_url_element`）；缺失时按
      `collection_id` 的形态（新式以 4 位年开头）选构造规则兜底。
    - `year`/`pub_date`：paper 级 `<year>`/`<month>` 存在则用之，否则回退 volume 级
      `<meta>` 的 year/month（真实数据几乎恒在 volume 级，勘察 §1）。`pub_date` 仅在
      月份文本可解析为英文月名时产出（`YYYY-MM`，无日粒度）。
    - `meta`：`track`（调用方传入——findings join 路径固定传 `"findings"`，见模块
      docstring）、`anthology_collection`（collection id）、`bibkey`、`pages`、
      `license`（按有效年份二分，§3/§9-★5）、每个 attachment 一条 `acl_anthology_attachment`。
    """
    anthology_id = _anthology_id(collection_id, volume_id, paper)
    identifiers: list[tuple[str, str]] = [(_ANTHOLOGY_SCHEME, anthology_id)]
    if paper.doi:
        identifiers.append((_DOI_SCHEME, ids.normalize_doi(paper.doi)))

    year = paper.year if paper.year is not None else volume_year
    month = paper.month if paper.month is not None else volume_month
    pub_date = _pub_date(year, month)

    meta: list[tuple[str, str]] = [(META_TRACK, track), (META_COLLECTION, collection_id)]
    if paper.bibkey:
        meta.append((META_BIBKEY, paper.bibkey))
    if paper.pages:
        meta.append((META_PAGES, paper.pages))
    if year is not None:
        meta.append((META_LICENSE, ids.license_for_year(year)))
    meta.extend((META_ATTACHMENT, attachment) for attachment in paper.attachments)

    return PaperStub(
        title=paper.title,
        identifiers=tuple(identifiers),
        year=year,
        pub_date=pub_date,
        abstract=paper.abstract,
        authors=paper.authors,
        meta=tuple(meta),
    )


def _anthology_id(collection_id: str, volume_id: str, paper: RawPaper) -> str:
    if paper.url_text:
        return ids.normalize_from_url_element(paper.url_text)
    if collection_id[:4].isdigit():  # 新式：collection_id 以 4 位年份开头（如 "2023.emnlp"）
        return ids.construct_new(collection_id, volume_id, paper.id_attr)
    return ids.construct_old(collection_id, volume_id, paper.id_attr)  # 旧式：如 "D19"


def _pub_date(year: int | None, month_text: str | None) -> str | None:
    if year is None or not month_text:
        return None
    month_num = _MONTH_NAMES.get(month_text.strip().lower())
    if month_num is None:
        return None
    return f"{year:04d}-{month_num:02d}"


# --- 共享小工具（同 arxiv parse.py 先例）--------------------------------------------------------


def _fromstring(data: bytes) -> ET.Element:
    try:
        return ET.fromstring(data)
    except ET.ParseError as exc:
        raise CrawlerError(ErrorClass.PARSE, f"malformed acl anthology xml: {exc}") from exc


def _normalize_ws(text: str) -> str:
    return " ".join(text.split())


def _itertext_normalized(el: ET.Element) -> str:
    return _normalize_ws("".join(el.itertext()))


def _required_itertext(parent: ET.Element, tag: str, *, context: str) -> str:
    el = parent.find(tag)
    if el is None:
        raise CrawlerError(ErrorClass.PARSE, f"{context}: missing required element <{tag}>")
    text = _itertext_normalized(el)
    if not text:
        raise CrawlerError(ErrorClass.PARSE, f"{context}: <{tag}> is empty")
    return text


def _optional_itertext(parent: ET.Element, tag: str) -> str | None:
    el = parent.find(tag)
    if el is None:
        return None
    text = _itertext_normalized(el)
    return text or None


def _optional_text(parent: ET.Element, tag: str) -> str | None:
    raw = parent.findtext(tag)
    if raw is None:
        return None
    cleaned = _normalize_ws(raw)
    return cleaned or None


def _optional_int(raw: str | None) -> int | None:
    if raw is None:
        return None
    try:
        return int(raw.strip())
    except ValueError:
        return None


__all__ = [
    "META_ATTACHMENT",
    "META_BIBKEY",
    "META_COLLECTION",
    "META_LICENSE",
    "META_PAGES",
    "META_TRACK",
    "RawCollection",
    "RawPaper",
    "RawVolume",
    "parse_collection_xml",
    "to_paper_stub",
]
