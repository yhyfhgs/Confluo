"""Query API Atom 与 OAI-PMH ListRecords 解析器（design/adapters/arxiv.md §3/§5）。

零网络：输入已取回的响应 `bytes`，输出中间记录 `ArxivRecord`（与网络/存储解耦，
供 T5 adapter 主体消费）。只用标准库 `xml.etree.ElementTree`——不引入第三方
XML 依赖。

两个数据源字段命名并不一致（历史遗留）：Atom 的 arXiv 扩展命名空间用下划线
（``journal_ref``），OAI-PMH 的 ``arXiv`` 元数据 schema 用连字符
（``journal-ref``）——本模块内部统一吸收这个差异，两个解析器产出同一套
`ArxivRecord` 字段名。

异常形态识别（arxiv.md §5 失败模式映射 + 2026-07-22 §5 勘误）。**措辞校准**：§5
表格给出站点现象→error_class 的映射，但 OAI 4xx→`CONFIG` 的细分归类（badArgument
等）是 §5 勘误行与 http.py "其余 4xx→CONFIG" 口径的平行落地、属 design/05 §4 的
外推，并非 §5 原表逐字——故此处按"§5 + 勘误 + §4 外推"执行，不再声称"逐字"：

- Atom feed 的 `opensearch:totalResults` > 0 但 `<entry>` 为空 → `ErrorClass.PARSE`
  （真实数据不应出现，出现即站点/查询异常）。
- OAI-PMH 顶层 `<error code="...">`（arxiv.md §5 + 2026-07-22 勘误逐类归并）：
  - `noRecordsMatch` → **非错误**：解析为空记录序列正常完成（空窗口/空桶的 OAI
    合法响应；watch 空日、新 category 月初的常态——误归 PARSE 会使空日 watch 假故障）；
  - `badResumptionToken` → `TRANSIENT`（token 每日过期，重跑天然恢复）；
  - `badArgument` / `badVerb` / `cannotDisseminateFormat` → `CONFIG`（我方请求构造
    缺陷，响亮停机，与 http.py 4xx→CONFIG 口径平行）；
  - `idDoesNotExist` → `GONE`（单 id 查询场景，--all-versions deferred 本期低频）；
  - 其余未知 code → `PARSE`（保守兜底）。
- 任何 XML 语法错误（截断响应等）→ `ErrorClass.PARSE`。
- 记录级必需字段（id/title）缺失 → `ErrorClass.PARSE`（单条记录级，非整页级）。
- 墓碑记录（`<header status="deleted">` 或整条缺 `<metadata>`）静默跳过，但跳过
  计数经 `parse_oai_page().skipped_tombstones` 暴露给 adapter（T5 在 enumerate 时经
  obslog 记 debug 事件——墓碑不再是静默黑洞，可观测）。

`to_paper_stub()` 是 arxiv.md §3 field mapping 的落地：``identifiers`` 恒为单
一 ``(('arxiv', base_id),)``；``journal_ref``/``doi`` 放 `PaperStub.meta`
（键名恰为 ``'journal_ref'``/``'doi'``），**绝不产出为 identifier**——防止
Phase 2 阶段就意外触发跨源强合并（该判定留给 Phase 3 ingest 按 D-007 决策）。
"""

import xml.etree.ElementTree as ET
from collections.abc import Iterator
from dataclasses import dataclass

from paper_crawler.adapters.arxiv import ids
from paper_crawler.errors import CrawlerError, ErrorClass
from paper_crawler.types import PaperStub

# --- 命名空间 --------------------------------------------------------------------------------

_ATOM_NS = "http://www.w3.org/2005/Atom"
_ARXIV_ATOM_NS = "http://arxiv.org/schemas/atom"
_OPENSEARCH_NS = "http://a9.com/-/spec/opensearch/1.1/"

_OAI_NS = "http://www.openarchives.org/OAI/2.0/"
_ARXIV_OAI_NS = "http://arxiv.org/OAI/arXiv/"


def _atom(name: str) -> str:
    return f"{{{_ATOM_NS}}}{name}"


def _arxiv_atom(name: str) -> str:
    return f"{{{_ARXIV_ATOM_NS}}}{name}"


def _opensearch(name: str) -> str:
    return f"{{{_OPENSEARCH_NS}}}{name}"


def _oai(name: str) -> str:
    return f"{{{_OAI_NS}}}{name}"


def _arxiv_oai(name: str) -> str:
    return f"{{{_ARXIV_OAI_NS}}}{name}"


# --- 中间记录 --------------------------------------------------------------------------------


@dataclass(frozen=True)
class ArxivRecord:
    """Atom/OAI 解析后的统一中间记录（两个解析器共用同一形状）。

    ``base_id``：已去版本号、归一化的 arXiv id（`ids.normalize` 的产物）。
    ``version``：Atom 来源为条目实际版本号（`vN`，无后缀时 None）；OAI 来源恒
    为 None（``arXiv`` 元数据 schema 不携带版本信息，只有 ``arXivRaw`` 才有，
    本期不使用该 schema——见 arxiv.md §3 `--all-versions` deferred 说明）。
    """

    base_id: str
    version: int | None
    title: str
    abstract: str | None
    authors: tuple[str, ...]
    categories: tuple[str, ...]
    primary_category: str | None
    journal_ref: str | None
    doi: str | None
    submitted: str | None


@dataclass(frozen=True)
class OaiListPage:
    """一页 OAI-PMH `ListRecords` 的完整解析产物（供 T5 adapter 单遍消费）。

    把"记录序列 + 续爬令牌 + 墓碑跳过数"三者在一次 XML 解析里一并给出，避免
    adapter 对同一份响应体重复 `ET.fromstring`，并让墓碑跳过数可观测（T4 审查
    Important 项：墓碑此前被静默跳过，无计数）。

    - ``records``：已解析、**未过滤**的记录（子分类客户端过滤是 adapter 的职责，
      不在解析层做——解析层只认 OAI 协议形态）。
    - ``resumption_token``：下一页令牌；收割结束（无 token 或空 token 文本）为 None。
    - ``skipped_tombstones``：本页被跳过的墓碑记录数（`status="deleted"` 或整条缺
      `<metadata>` 二者合计）。
    """

    records: tuple[ArxivRecord, ...]
    resumption_token: str | None
    skipped_tombstones: int


# --- 公开 API：Query API Atom -----------------------------------------------------------------


def parse_atom_feed(data: bytes) -> Iterator[ArxivRecord]:
    """解析 Query API 返回的 Atom feed，逐条产出 `ArxivRecord`。

    `opensearch:totalResults` 非零但 `<entry>` 为空时抛 `PARSE`（arxiv.md §5）；
    `totalResults` 为 0（正常空结果页）不抛错，直接产出空序列。
    """
    root = _fromstring(data)
    total = _total_results(root)
    entries = root.findall(_atom("entry"))
    if total is not None and total > 0 and not entries:
        raise CrawlerError(
            ErrorClass.PARSE,
            f"atom feed reports opensearch:totalResults={total} but has no <entry>",
        )
    for entry in entries:
        yield _parse_atom_entry(entry)


def _total_results(root: ET.Element) -> int | None:
    text = root.findtext(_opensearch("totalResults"))
    if text is None:
        return None
    try:
        return int(text.strip())
    except ValueError:
        return None


def _parse_atom_entry(entry: ET.Element) -> ArxivRecord:
    raw_id_url = _required_text(entry, _atom("id"), context="atom entry")
    _, sep, raw_id = raw_id_url.partition("/abs/")
    if not sep:
        raise CrawlerError(
            ErrorClass.PARSE, f"atom entry <id> is not an arxiv abs url: {raw_id_url!r}"
        )
    base_id, version = ids.split_version(raw_id)

    title = _required_text(entry, _atom("title"), context="atom entry")
    abstract = _optional_text(entry, _atom("summary"))
    submitted = _optional_text(entry, _atom("published"))

    authors = tuple(
        name.strip()
        for author_el in entry.findall(_atom("author"))
        if (name := author_el.findtext(_atom("name"))) and name.strip()
    )

    categories = tuple(
        term for cat_el in entry.findall(_atom("category")) if (term := cat_el.get("term"))
    )

    primary_el = entry.find(_arxiv_atom("primary_category"))
    primary_category = primary_el.get("term") if primary_el is not None else None

    journal_ref = _optional_text(entry, _arxiv_atom("journal_ref"))
    doi = _optional_text(entry, _arxiv_atom("doi"))

    return ArxivRecord(
        base_id=base_id,
        version=version,
        title=title,
        abstract=abstract,
        authors=authors,
        categories=categories,
        primary_category=primary_category,
        journal_ref=journal_ref,
        doi=doi,
        submitted=submitted,
    )


# --- 公开 API：OAI-PMH ListRecords -------------------------------------------------------------


def parse_oai_page(data: bytes) -> OaiListPage:
    """解析一页 OAI-PMH `ListRecords`：一次解析给出记录 + 续爬令牌 + 墓碑跳过数。

    顶层 `<error>` 先于任何记录被识别：`noRecordsMatch` 视为空页正常返回
    （records 空、token None、skipped 0）；其余错误码按模块 docstring 归类抛出。
    记录**未做子分类过滤**（adapter 职责——解析层只认 OAI 协议形态）。
    """
    root = _fromstring(data)
    _raise_if_oai_error(root)  # noRecordsMatch 在此被吸收为"不抛"，落到下方空页
    records, skipped = _iter_oai_records(root)
    return OaiListPage(
        records=tuple(records),
        resumption_token=_resumption_token_from(root),
        skipped_tombstones=skipped,
    )


def parse_oai_list_records(data: bytes) -> Iterator[ArxivRecord]:
    """解析 OAI-PMH `ListRecords` 响应，逐条产出 `ArxivRecord`（墓碑记录静默跳过）。

    薄封装 `parse_oai_page`（丢弃续爬令牌与墓碑跳过数）；需要令牌/跳过数的调用方
    （T5 adapter）改用 `parse_oai_page`。错误识别与 `parse_oai_page` 完全一致。
    """
    return iter(parse_oai_page(data).records)


def oai_resumption_token(data: bytes) -> str | None:
    """从同一份 OAI-PMH 响应体中取出 `resumptionToken`（薄封装 `parse_oai_page`）。

    响应体是错误页时同样抛出（与 `parse_oai_page` 一致）；`resumptionToken` 缺失或
    为空文本（收割结束的标准写法）均返回 None。
    """
    return parse_oai_page(data).resumption_token


def _iter_oai_records(root: ET.Element) -> tuple[list[ArxivRecord], int]:
    """遍历 `<ListRecords>` 下的 `<record>`，返回 (记录列表, 墓碑跳过数)。

    墓碑（`status="deleted"` 或整条缺 `<metadata>`）计入跳过数而非静默丢弃；
    `<metadata>` 存在但缺 `<arXiv>` 子元素属真实解析失败 → `PARSE`（非墓碑）。
    调用前须已过 `_raise_if_oai_error`。
    """
    list_records = root.find(_oai("ListRecords"))
    if list_records is None:
        return [], 0
    records: list[ArxivRecord] = []
    skipped = 0
    for record in list_records.findall(_oai("record")):
        header = record.find(_oai("header"))
        if header is not None and header.get("status") == "deleted":
            skipped += 1
            continue
        metadata = record.find(_oai("metadata"))
        if metadata is None:
            skipped += 1
            continue
        arxiv_el = metadata.find(_arxiv_oai("arXiv"))
        if arxiv_el is None:
            raise CrawlerError(ErrorClass.PARSE, "OAI record <metadata> missing <arXiv> element")
        records.append(_parse_oai_arxiv_element(arxiv_el))
    return records, skipped


def _resumption_token_from(root: ET.Element) -> str | None:
    list_records = root.find(_oai("ListRecords"))
    if list_records is None:
        return None
    token_el = list_records.find(_oai("resumptionToken"))
    if token_el is None or token_el.text is None:
        return None
    token = token_el.text.strip()
    return token or None


# OAI-PMH 顶层错误码 → ErrorClass（arxiv.md §5 + 2026-07-22 勘误；见模块 docstring）。
# noRecordsMatch 不在表内——它是合法空态，由 _raise_if_oai_error 直接 return 吸收。
_OAI_ERROR_CLASS: dict[str, ErrorClass] = {
    "badResumptionToken": ErrorClass.TRANSIENT,
    "badArgument": ErrorClass.CONFIG,
    "badVerb": ErrorClass.CONFIG,
    "cannotDisseminateFormat": ErrorClass.CONFIG,
    "idDoesNotExist": ErrorClass.GONE,
}


def _raise_if_oai_error(root: ET.Element) -> None:
    """顶层 `<error>` → 抛对应 `CrawlerError`；`noRecordsMatch` 是合法空态，直接返回。"""
    error_el = root.find(_oai("error"))
    if error_el is None:
        return
    code = error_el.get("code", "")
    if code == "noRecordsMatch":
        return  # arxiv.md §5 勘误：空窗口/空桶的合法响应，非错误
    message = (error_el.text or "").strip()
    error_class = _OAI_ERROR_CLASS.get(code, ErrorClass.PARSE)
    raise CrawlerError(error_class, f"OAI-PMH error code={code!r}: {message}", detail=code)


def _parse_oai_arxiv_element(el: ET.Element) -> ArxivRecord:
    raw_id = _required_text(el, _arxiv_oai("id"), context="OAI arXiv record")
    base_id = ids.normalize(raw_id)

    title = _required_text(el, _arxiv_oai("title"), context="OAI arXiv record")
    abstract = _optional_text(el, _arxiv_oai("abstract"))
    submitted = _optional_text(el, _arxiv_oai("created"))

    authors_el = el.find(_arxiv_oai("authors"))
    authors = _parse_oai_authors(authors_el) if authors_el is not None else ()

    categories_text = _optional_text(el, _arxiv_oai("categories"))
    categories = tuple(categories_text.split()) if categories_text else ()
    primary_category = categories[0] if categories else None

    # OAI arXiv schema 用连字符命名（与 Atom 扩展命名空间的下划线命名不一致）。
    journal_ref = _optional_text(el, _arxiv_oai("journal-ref"))
    doi = _optional_text(el, _arxiv_oai("doi"))

    return ArxivRecord(
        base_id=base_id,
        version=None,
        title=title,
        abstract=abstract,
        authors=authors,
        categories=categories,
        primary_category=primary_category,
        journal_ref=journal_ref,
        doi=doi,
        submitted=submitted,
    )


def _parse_oai_authors(authors_el: ET.Element) -> tuple[str, ...]:
    names: list[str] = []
    for author_el in authors_el.findall(_arxiv_oai("author")):
        forenames = author_el.findtext(_arxiv_oai("forenames"))
        keyname = author_el.findtext(_arxiv_oai("keyname"))
        parts = [p.strip() for p in (forenames, keyname) if p and p.strip()]
        if parts:
            names.append(" ".join(parts))
    return tuple(names)


# --- PaperStub 转换 ---------------------------------------------------------------------------


def to_paper_stub(record: ArxivRecord) -> PaperStub:
    """把中间记录转成 `PaperStub`（arxiv.md §3 字段映射裁决逐字执行）。

    ``identifiers`` 恒为单一 ``(('arxiv', base_id),)``；``journal_ref``/``doi``
    放 `meta`（键名恰为 ``'journal_ref'``/``'doi'``），绝不产出为 identifier。
    """
    meta: list[tuple[str, str]] = []
    if record.journal_ref:
        meta.append(("journal_ref", record.journal_ref))
    if record.doi:
        meta.append(("doi", record.doi))

    year = _year_from_submitted(record.submitted)

    return PaperStub(
        title=record.title,
        identifiers=(("arxiv", record.base_id),),
        year=year,
        pub_date=record.submitted,
        abstract=record.abstract,
        authors=record.authors,
        meta=tuple(meta),
    )


def _year_from_submitted(submitted: str | None) -> int | None:
    if submitted is None or len(submitted) < 4 or not submitted[:4].isdigit():
        return None
    return int(submitted[:4])


# --- 共享小工具 -------------------------------------------------------------------------------


def _fromstring(data: bytes) -> ET.Element:
    try:
        return ET.fromstring(data)
    except ET.ParseError as exc:
        raise CrawlerError(ErrorClass.PARSE, f"malformed xml: {exc}") from exc


def _normalize_ws(text: str) -> str:
    return " ".join(text.split())


def _optional_text(parent: ET.Element, tag: str) -> str | None:
    raw = parent.findtext(tag)
    if raw is None:
        return None
    cleaned = _normalize_ws(raw)
    return cleaned or None


def _required_text(parent: ET.Element, tag: str, *, context: str) -> str:
    value = _optional_text(parent, tag)
    if value is None:
        raise CrawlerError(ErrorClass.PARSE, f"{context}: missing required element {tag!r}")
    return value


__all__ = [
    "ArxivRecord",
    "OaiListPage",
    "oai_resumption_token",
    "parse_atom_feed",
    "parse_oai_list_records",
    "parse_oai_page",
    "to_paper_stub",
]
