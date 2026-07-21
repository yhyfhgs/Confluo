"""AAAI OJS 的 OAI-PMH ``oai_dc`` **体层**解析器 + DOI 归一（design/adapters/aaai-ojs.md
§3/§4/§7）。

零网络：输入已取回的响应 `bytes`，输出中间记录 `AaaiRecord`（与网络/存储解耦，供
adapter 主体消费）。**信封层复用共享核** `paper_crawler.adapters._oai`（★C，§9）——
错误码表/墓碑/`resumptionToken`/`OaiListPage` 都在那里；本模块只写 AAAI 的 `oai_dc`
体层：从 ``<oai_dc:dc>`` 抽 title/creator*/description/date/双 identifier 择 DOI/
relation→pdf_url，并把 AAAI DOI 归一为唯一强合并锚点。

**DOI = 唯一强 identifier（★B，§3.3/§9）**：`identifiers = (('doi', <小写规范串>),)`。
AAAI DOI 是本源（AAAI proceedings）为本篇本版分配的官方规范 id（形如
``10.1609/aaai.v{V}i{I}.{articleId}``），**不是**指向他源版本的跨源指针——产
identifier 是 R3 底层原则的正确应用（本源 id 产 identifier、跨源线索入 meta），
Phase 3 Crossref 同 DOI 合并是强合并锚点的正用。归一规则：统一小写（DOI 大小写
不敏感，小写化保证 `PRIMARY KEY(scheme,value)` 稳定），**不剥前缀、不改分隔符**。

**HTML/citation 详情解析器**（`parse_issue_toc`/`parse_article_meta`）为**对账/兜底
路径的解析基础**：设计裁决主抓取走 OAI 单路径（HTML issue-TOC 兜底已否决，§9 ★A
附属），故这两者**不接入运行时 enumerate/resolve**——仅供 D-019 锚点生成的 OAI↔HTML
计数对账、以及 `citation_pdf_url` 的 fixture 对账参考（§4：不作运行时 resolve 兜底，
否则违反 resolve 零网络断言）。先例 pmlr `parse_citation_meta`（同为推迟路径的解析
基础）。
"""

from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass

from paper_crawler.adapters import _oai
from paper_crawler.adapters._oai import OaiListPage  # 再导出：信封页形状（体层记录=AaaiRecord）
from paper_crawler.errors import CrawlerError, ErrorClass
from paper_crawler.types import PaperStub

# --- 命名空间（oai_dc 体层）------------------------------------------------------------------

_OAI_DC_NS = "http://www.openarchives.org/OAI/2.0/oai_dc/"
_DC_NS = "http://purl.org/dc/elements/1.1/"


def _oai_dc(name: str) -> str:
    return f"{{{_OAI_DC_NS}}}{name}"


def _dc(name: str) -> str:
    return f"{{{_DC_NS}}}{name}"


# --- DOI 归一（design §3.3）------------------------------------------------------------------

# 裸 DOI 形态（前缀 10.NNNN/…）；用于从两个 dc:identifier 中择出 DOI（另一个是 landing URL）。
_DOI_RE = re.compile(r"10\.\d{4,9}/\S+")
# 从 AAAI DOI 抽卷号：aaai.v{V}i{I}.{articleId} 里的 v{V}（小写化后匹配）。
_AAAI_VOLUME_RE = re.compile(r"aaai\.v(\d+)i", re.IGNORECASE)
# 从 landing URL 抽 OJS article id：/article/view/{id}[/…]。
_ARTICLE_ID_RE = re.compile(r"/article/view/(\d+)")


def normalize_doi(doi: str) -> str:
    """DOI 归一：去首尾空白 + 统一小写（不剥前缀、不改分隔符，design §3.3）。"""
    return doi.strip().lower()


def volume_from_doi(doi: str) -> str | None:
    """从 AAAI DOI 抽卷号裸数字串（``aaai.v40i1.36958`` → ``'40'``）；非 AAAI 形态 → None。"""
    match = _AAAI_VOLUME_RE.search(doi)
    return match.group(1) if match else None


def _classify_identifiers(values: list[str]) -> tuple[str | None, str | None]:
    """把 dc:identifier 值序列分成 (DOI, landing URL)。

    DOI = 首个匹配裸 DOI 正则者；landing = 首个 http(s) URL（且非 DOI）。survey §5.2：
    oai_dc 恰有两个 dc:identifier——一个 landing view URL、一个裸 DOI。
    """
    doi: str | None = None
    landing: str | None = None
    for raw in values:
        value = raw.strip()
        if not value:
            continue
        if doi is None and _DOI_RE.fullmatch(value):
            doi = value
        elif landing is None and value.lower().startswith(("http://", "https://")):
            landing = value
    return doi, landing


# --- 中间记录 --------------------------------------------------------------------------------


@dataclass(frozen=True)
class AaaiRecord:
    """一条 `oai_dc` 记录的解析产物。

    ``doi``：已归一（小写规范）的本源 DOI——唯一强 identifier 锚点（★B）。``volume``：
    从 DOI 抽出的卷号裸数字串（enumerate 的客户端过滤维度，design §4）。``pdf_view_url``：
    取自首个 ``dc:relation``（galley view URL；resolve 阶段 view→download 预换）。
    ``article_id``：从 landing URL 抽出的 OJS 内部 id（供 meta/URL 构造）。
    """

    doi: str
    volume: str | None
    title: str
    abstract: str | None
    authors: tuple[str, ...]
    date: str | None
    landing_url: str | None
    pdf_view_url: str | None
    article_id: str | None
    source: str | None


# --- 公开 API：OAI-PMH ListRecords（信封复用共享核，体层为 oai_dc）------------------------------


def parse_oai_page(data: bytes) -> OaiListPage[AaaiRecord]:
    """解析一页 OAI-PMH `ListRecords`：记录 + 续爬令牌 + 墓碑跳过数（信封走共享核 `_oai`）。

    本函数仅注入 AAAI 体层回调 `_parse_oai_dc_metadata`（``<metadata>`` → `AaaiRecord`）。
    记录**未做卷号过滤**（adapter 职责——解析层只认 OAI 协议形态）。
    """
    return _oai.parse_oai_page(data, record_parser=_parse_oai_dc_metadata)


def parse_get_record(data: bytes) -> AaaiRecord:
    """解析 OAI-PMH `GetRecord` 响应为单条 `AaaiRecord`（canary 用，design §7）。

    顶层 `<error>` 复用共享核 `_oai.raise_if_oai_error`——``idDoesNotExist`` → `GONE`
    （单 id 未命中，design §6）。其余结构缺失 → `PARSE`。
    """
    root = _oai.fromstring(data)
    _oai.raise_if_oai_error(root)
    get_record = root.find(_oai.oai("GetRecord"))
    if get_record is None:
        raise CrawlerError(ErrorClass.PARSE, "OAI GetRecord response missing <GetRecord>")
    record = get_record.find(_oai.oai("record"))
    if record is None:
        raise CrawlerError(ErrorClass.PARSE, "OAI GetRecord missing <record>")
    metadata = record.find(_oai.oai("metadata"))
    if metadata is None:
        raise CrawlerError(ErrorClass.PARSE, "OAI GetRecord <record> missing <metadata>")
    return _parse_oai_dc_metadata(metadata)


def _parse_oai_dc_metadata(metadata: ET.Element) -> AaaiRecord:
    """AAAI 体层回调：从 `<metadata>` 定位 ``<oai_dc:dc>`` 并解析为 `AaaiRecord`。

    ``<metadata>`` 存在但缺 ``<oai_dc:dc>``（如误配 arXiv schema）是真实解析失败 →
    `PARSE`（非墓碑——墓碑是"整条缺 metadata"，此处是"metadata 在但 schema 错"）。
    """
    dc_el = metadata.find(_oai_dc("dc"))
    if dc_el is None:
        raise CrawlerError(ErrorClass.PARSE, "OAI record <metadata> missing <oai_dc:dc> element")
    return _parse_oai_dc_element(dc_el)


def _parse_oai_dc_element(dc_el: ET.Element) -> AaaiRecord:
    """从 ``<oai_dc:dc>`` 抽字段（design §4 字段映射）。

    必需字段缺失 → `PARSE`：``dc:title`` 缺、或两个 ``dc:identifier`` 都不含 DOI
    （design §6："记录缺 dc:title / dc:identifier 无 DOI → parse"）。
    """
    title = _oai.required_text(dc_el, _dc("title"), context="aaai oai_dc record")

    identifier_values = [text for el in dc_el.findall(_dc("identifier")) if (text := el.text)]
    raw_doi, landing_url = _classify_identifiers(identifier_values)
    if raw_doi is None:
        raise CrawlerError(
            ErrorClass.PARSE,
            f"aaai oai_dc record {title!r} has no DOI among dc:identifier {identifier_values!r}",
        )
    doi = normalize_doi(raw_doi)

    authors = tuple(
        name
        for el in dc_el.findall(_dc("creator"))
        if el.text and (name := _oai.normalize_ws(el.text))
    )
    abstract = _oai.optional_text(dc_el, _dc("description"))
    date = _oai.optional_text(dc_el, _dc("date"))
    source = _oai.optional_text(dc_el, _dc("source"))

    # 首个 dc:relation = galley view URL（design §4：多 galley 取首个 + 记录级 dc:format
    # 佐证，消歧失败由 pipeline %PDF 魔数拦截）。
    pdf_view_url = _oai.optional_text(dc_el, _dc("relation"))

    article_id = _article_id_from_landing(landing_url)

    return AaaiRecord(
        doi=doi,
        volume=volume_from_doi(doi),
        title=title,
        abstract=abstract,
        authors=authors,
        date=date,
        landing_url=landing_url,
        pdf_view_url=pdf_view_url,
        article_id=article_id,
        source=source,
    )


def _article_id_from_landing(landing_url: str | None) -> str | None:
    if landing_url is None:
        return None
    match = _ARTICLE_ID_RE.search(landing_url)
    return match.group(1) if match else None


# --- PaperStub 转换（design §3.3 meta 键名定死）------------------------------------------------


def to_paper_stub(record: AaaiRecord) -> PaperStub:
    """把 `AaaiRecord` 转成 `PaperStub`（design §3.3/§4 字段映射逐字执行）。

    ``identifiers`` 恒为单一 ``(('doi', <小写规范串>),)``（★B 本源强锚点）。``meta``
    键名定死：``pdf_url``（dc:relation 的 galley view URL，供 resolve 零网络构造）、
    ``ojs_article_id``、可选 ``ojs_source``（dc:source 期号串，供对账）。摘要/作者走
    `PaperStub` 一级字段，**不入 meta**。
    """
    meta: list[tuple[str, str]] = []
    if record.pdf_view_url:
        meta.append(("pdf_url", record.pdf_view_url))
    if record.article_id:
        meta.append(("ojs_article_id", record.article_id))
    if record.source:
        meta.append(("ojs_source", record.source))

    return PaperStub(
        title=record.title,
        identifiers=(("doi", record.doi),),
        year=_year_from_date(record.date),
        pub_date=record.date,
        abstract=record.abstract,
        authors=record.authors,
        meta=tuple(meta),
    )


def _year_from_date(date: str | None) -> int | None:
    if date is None or len(date) < 4 or not date[:4].isdigit():
        return None
    return int(date[:4])


# --- 对账/兜底路径解析器（不接入运行时；见模块 docstring）--------------------------------------


@dataclass(frozen=True)
class AaaiTocEntry:
    """HTML issue TOC 一条 ``.obj_article_summary`` 的解析产物（对账用，design §7 ⑩）。"""

    article_id: str
    title: str
    authors: tuple[str, ...]
    pages: str | None
    pdf_url: str | None


# 按 `.obj_article_summary` 起始标签切段——AAAI 条目内含嵌套 <div>（.meta/.authors/.pages），
# 不能用 pmlr 式"惰性到首个 </div>"（会被内层 </div> 提前截断）；改用"下一个条目起点"切界。
_SUMMARY_SPLIT_RE = re.compile(r'<div\s+class="obj_article_summary"[^>]*>', re.IGNORECASE)
_TITLE_LINK_RE = re.compile(
    r'<h3\s+class="title">\s*<a\b[^>]*href="([^"]*)"[^>]*>(.*?)</a>', re.DOTALL | re.IGNORECASE
)
_AUTHORS_DIV_RE = re.compile(r'<div\s+class="authors">(.*?)</div>', re.DOTALL | re.IGNORECASE)
_PAGES_DIV_RE = re.compile(r'<div\s+class="pages">(.*?)</div>', re.DOTALL | re.IGNORECASE)
# PDF galley：class 必须含 pdf（同文章可能挂 obj_galley_link file 的 Video/Poster，survey §2.2）。
_PDF_GALLEY_RE = re.compile(
    r'<a\s+class="obj_galley_link pdf"[^>]*href="([^"]*)"', re.DOTALL | re.IGNORECASE
)


def parse_issue_toc(data: bytes) -> tuple[AaaiTocEntry, ...]:
    """解析 HTML issue TOC 页（对账/兜底路径的解析基础，design §7 ⑩）。

    逐 ``.obj_article_summary`` 段产出 `AaaiTocEntry`（按 class 过滤 PDF galley）。段内
    缺 title 链接（→ 无 articleId）→ `PARSE`（结构漂移信号）。**不接入运行时 enumerate**
    （单路径原则，§9 ★A 附属）——供 D-019 锚点的 OAI↔HTML 计数对账。
    """
    text = data.decode("utf-8", errors="replace")
    segments = _SUMMARY_SPLIT_RE.split(text)[1:]  # 丢弃第一个条目前的页首
    return tuple(_parse_toc_segment(seg) for seg in segments)


def _parse_toc_segment(segment: str) -> AaaiTocEntry:
    title_match = _TITLE_LINK_RE.search(segment)
    if title_match is None:
        raise CrawlerError(
            ErrorClass.PARSE, "aaai issue TOC entry missing <h3 class=title> article link"
        )
    href, title_raw = title_match.group(1), _clean_text(title_match.group(2))
    article_id = _article_id_from_landing(href)
    if article_id is None or not title_raw:
        raise CrawlerError(
            ErrorClass.PARSE, f"aaai issue TOC entry missing articleId/title (href={href!r})"
        )

    authors_match = _AUTHORS_DIV_RE.search(segment)
    authors = _split_authors(authors_match.group(1)) if authors_match else ()
    pages_match = _PAGES_DIV_RE.search(segment)
    pages = _clean_text(pages_match.group(1)) if pages_match else None
    pdf_match = _PDF_GALLEY_RE.search(segment)
    pdf_url = pdf_match.group(1) if pdf_match else None

    return AaaiTocEntry(
        article_id=article_id,
        title=title_raw,
        authors=authors,
        pages=pages or None,
        pdf_url=pdf_url,
    )


@dataclass(frozen=True)
class AaaiArticleMeta:
    """单篇详情页的 ``DC.*`` + ``citation_*`` meta（对账用，design §7 ⑪）。

    ``pdf_url`` = ``citation_pdf_url``（download 终态 URL）——**仅 fixture 对账参考**，
    design §4 明令不作运行时 resolve 兜底（否则违反 resolve 零网络断言，pmlr-B3 教训）。
    """

    title: str | None
    authors: tuple[str, ...]
    doi: str | None
    pdf_url: str | None
    volume: str | None
    issue: str | None
    firstpage: str | None
    lastpage: str | None
    date: str | None


_META_RE = re.compile(
    r'<meta\s+name="(?P<name>[^"]+)"[^>]*\bcontent="(?P<content>[^"]*)"', re.IGNORECASE
)


def parse_article_meta(data: bytes) -> AaaiArticleMeta:
    """解析单篇详情页的 ``DC.*`` + ``citation_*`` meta（对账路径的解析基础，design §7 ⑪）。

    字段全部宽松（缺失即 None/空 tuple）——不在任何 error_class 判定路径上。DOI 优先取
    ``DC.Identifier.DOI``/``citation_doi``；作者取全部 ``citation_author``。
    """
    text = data.decode("utf-8", errors="replace")
    tags: dict[str, list[str]] = {}
    for match in _META_RE.finditer(text):
        tags.setdefault(match.group("name"), []).append(html.unescape(match.group("content")))

    def first(*names: str) -> str | None:
        for name in names:
            values = tags.get(name)
            if values:
                return values[0]
        return None

    return AaaiArticleMeta(
        title=first("citation_title", "DC.Title"),
        authors=tuple(tags.get("citation_author", ())),
        doi=first("DC.Identifier.DOI", "citation_doi"),
        pdf_url=first("citation_pdf_url"),
        volume=first("citation_volume", "DC.Source.Volume"),
        issue=first("citation_issue", "DC.Source.Issue"),
        firstpage=first("citation_firstpage"),
        lastpage=first("citation_lastpage"),
        date=first("citation_date", "DC.Date.issued"),
    )


# --- 共享小工具 ------------------------------------------------------------------------------


def _strip_tags(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text)


def _clean_text(text: str) -> str:
    return _oai.normalize_ws(html.unescape(_strip_tags(text)))


def _split_authors(raw: str) -> tuple[str, ...]:
    cleaned = _clean_text(raw)
    if not cleaned:
        return ()
    return tuple(name for part in cleaned.split(",") if (name := part.strip()))


__all__ = [
    "AaaiArticleMeta",
    "AaaiRecord",
    "AaaiTocEntry",
    "OaiListPage",
    "normalize_doi",
    "parse_article_meta",
    "parse_get_record",
    "parse_issue_toc",
    "parse_oai_page",
    "to_paper_stub",
    "volume_from_doi",
]
