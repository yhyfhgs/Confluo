"""Query API Atom 与 OAI-PMH ListRecords 解析器（design/adapters/arxiv.md §3/§5）。

零网络：输入已取回的响应 `bytes`，输出中间记录 `ArxivRecord`（与网络/存储解耦，
供 T5 adapter 主体消费）。只用标准库 `xml.etree.ElementTree`——不引入第三方
XML 依赖。

两个数据源字段命名并不一致（历史遗留）：Atom 的 arXiv 扩展命名空间用下划线
（``journal_ref``），OAI-PMH 的 ``arXiv`` 元数据 schema 用连字符
（``journal-ref``）——本模块内部统一吸收这个差异，两个解析器产出同一套
`ArxivRecord` 字段名。

**OAI-PMH 信封层已上移共享核**（★C，design/adapters/aaai-ojs.md §9）：错误码表、
`noRecordsMatch` 空态、墓碑遍历+计数、`resumptionToken`、`OaiListPage` 页形状统一
由 `paper_crawler.adapters._oai` 提供（arxiv 与 aaai_ojs 共用，避免重复漂移）。本
模块只保留 arxiv 的**体层**：Atom feed 解析器 + ``arXiv`` 私有 schema 的元素解析器
（``_parse_oai_arxiv_element``），后者经 ``record_parser`` 回调注入共享核。

异常形态识别（arxiv.md §5 失败模式映射 + 2026-07-22 §5 勘误）。**措辞校准**：§5
表格给出站点现象→error_class 的映射，但 OAI 4xx→`CONFIG` 的细分归类（badArgument
等）是 §5 勘误行与 http.py "其余 4xx→CONFIG" 口径的平行落地、属 design/05 §4 的
外推，并非 §5 原表逐字——故此处按"§5 + 勘误 + §4 外推"执行，不再声称"逐字"：

- Atom feed 的 `opensearch:totalResults` > 0 但 `<entry>` 为空 → `ErrorClass.PARSE`
  （真实数据不应出现，出现即站点/查询异常）。
- OAI-PMH 顶层 `<error code="...">` 的逐类归并、墓碑跳过、`resumptionToken` 语义均由
  共享核 `_oai` 实现（见其模块 docstring）；本模块的 arxiv 体层只负责"``<metadata>``
  存在但缺 ``<arXiv>`` 子元素"这一真实解析失败 → `PARSE`（非墓碑）。
- 任何 XML 语法错误（截断响应等）→ `ErrorClass.PARSE`（`_oai.fromstring`）。
- 记录级必需字段（id/title）缺失 → `ErrorClass.PARSE`（单条记录级，非整页级）。

`to_paper_stub()` 是 arxiv.md §3 field mapping 的落地：``identifiers`` 恒为单
一 ``(('arxiv', base_id),)``；``journal_ref``/``doi`` 放 `PaperStub.meta`
（键名恰为 ``'journal_ref'``/``'doi'``），**绝不产出为 identifier**——防止
Phase 2 阶段就意外触发跨源强合并（该判定留给 Phase 3 ingest 按 D-007 决策）。
"""

import xml.etree.ElementTree as ET
from collections.abc import Iterator
from dataclasses import dataclass

from paper_crawler.adapters import _oai
from paper_crawler.adapters._oai import OaiListPage  # 再导出：信封页形状（体层记录=ArxivRecord）
from paper_crawler.adapters.arxiv import ids
from paper_crawler.errors import CrawlerError, ErrorClass
from paper_crawler.types import PaperStub

# --- 命名空间 --------------------------------------------------------------------------------

_ATOM_NS = "http://www.w3.org/2005/Atom"
_ARXIV_ATOM_NS = "http://arxiv.org/schemas/atom"
_OPENSEARCH_NS = "http://a9.com/-/spec/opensearch/1.1/"

_ARXIV_OAI_NS = "http://arxiv.org/OAI/arXiv/"


def _atom(name: str) -> str:
    return f"{{{_ATOM_NS}}}{name}"


def _arxiv_atom(name: str) -> str:
    return f"{{{_ARXIV_ATOM_NS}}}{name}"


def _opensearch(name: str) -> str:
    return f"{{{_OPENSEARCH_NS}}}{name}"


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


# --- 公开 API：Query API Atom -----------------------------------------------------------------


def parse_atom_feed(data: bytes) -> Iterator[ArxivRecord]:
    """解析 Query API 返回的 Atom feed，逐条产出 `ArxivRecord`。

    `opensearch:totalResults` 非零但 `<entry>` 为空时抛 `PARSE`（arxiv.md §5）；
    `totalResults` 为 0（正常空结果页）不抛错，直接产出空序列。
    """
    root = _oai.fromstring(data)
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
    raw_id_url = _oai.required_text(entry, _atom("id"), context="atom entry")
    _, sep, raw_id = raw_id_url.partition("/abs/")
    if not sep:
        raise CrawlerError(
            ErrorClass.PARSE, f"atom entry <id> is not an arxiv abs url: {raw_id_url!r}"
        )
    base_id, version = ids.split_version(raw_id)

    title = _oai.required_text(entry, _atom("title"), context="atom entry")
    abstract = _oai.optional_text(entry, _atom("summary"))
    submitted = _oai.optional_text(entry, _atom("published"))

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

    journal_ref = _oai.optional_text(entry, _arxiv_atom("journal_ref"))
    doi = _oai.optional_text(entry, _arxiv_atom("doi"))

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


# --- 公开 API：OAI-PMH ListRecords（信封层复用共享核，体层为 arxiv schema）---------------------


def parse_oai_page(data: bytes) -> OaiListPage[ArxivRecord]:
    """解析一页 OAI-PMH `ListRecords`：一次解析给出记录 + 续爬令牌 + 墓碑跳过数。

    信封遍历（错误码/墓碑/令牌）由共享核 `_oai.parse_oai_page` 承担；本函数仅注入
    arxiv 体层回调 `_parse_oai_metadata`（``<metadata>`` → `ArxivRecord`）。记录
    **未做子分类过滤**（adapter 职责——解析层只认 OAI 协议形态）。
    """
    return _oai.parse_oai_page(data, record_parser=_parse_oai_metadata)


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


def _parse_oai_metadata(metadata: ET.Element) -> ArxivRecord:
    """arxiv 体层回调：从 `<metadata>` 定位 ``<arXiv>`` 子元素并解析为 `ArxivRecord`。

    ``<metadata>`` 存在但缺 ``<arXiv>``（如误配 oai_dc）是真实解析失败 → `PARSE`
    （不能被共享核的墓碑计数吞掉——墓碑是"整条缺 metadata"，此处是"metadata 在但
    schema 错"）。
    """
    arxiv_el = metadata.find(_arxiv_oai("arXiv"))
    if arxiv_el is None:
        raise CrawlerError(ErrorClass.PARSE, "OAI record <metadata> missing <arXiv> element")
    return _parse_oai_arxiv_element(arxiv_el)


def _parse_oai_arxiv_element(el: ET.Element) -> ArxivRecord:
    raw_id = _oai.required_text(el, _arxiv_oai("id"), context="OAI arXiv record")
    base_id = ids.normalize(raw_id)

    title = _oai.required_text(el, _arxiv_oai("title"), context="OAI arXiv record")
    abstract = _oai.optional_text(el, _arxiv_oai("abstract"))
    submitted = _oai.optional_text(el, _arxiv_oai("created"))

    authors_el = el.find(_arxiv_oai("authors"))
    authors = _parse_oai_authors(authors_el) if authors_el is not None else ()

    categories_text = _oai.optional_text(el, _arxiv_oai("categories"))
    categories = tuple(categories_text.split()) if categories_text else ()
    primary_category = categories[0] if categories else None

    # OAI arXiv schema 用连字符命名（与 Atom 扩展命名空间的下划线命名不一致）。
    journal_ref = _oai.optional_text(el, _arxiv_oai("journal-ref"))
    doi = _oai.optional_text(el, _arxiv_oai("doi"))

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


__all__ = [
    "ArxivRecord",
    "OaiListPage",
    "oai_resumption_token",
    "parse_atom_feed",
    "parse_oai_list_records",
    "parse_oai_page",
    "to_paper_stub",
]
