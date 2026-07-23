"""Econometric Society（`econsoc`）的 OAI-PMH ``oai_dc`` **体层**解析器 + DOI 路由 +
ECMA 年代分段判定 + galley 链抽取（design/adapters/econsoc.md §3/§4）。

零网络纯逻辑：输入已取回的响应 `bytes`/HTML，输出中间记录 `EconsocRecord` 或路由判定
（与网络/存储解耦，供 adapter 主体消费）。只用标准库 + `ids.normalize_doi`。

**★C 复用边界（econsoc.md §4 "OAI 复用边界"）＝信封共享、体层各写**：OAI-PMH 信封层
（错误码表/`noRecordsMatch` 空态/墓碑遍历/`resumptionToken`/`OaiListPage` 页形状）复用
共享核 `paper_crawler.adapters._oai`（arxiv/aaai 之后第三个消费者，经 `record_parser`
回调注入）；``oai_dc`` **体层**在本模块**自写**（~50 行）——**严禁 import aaai_ojs 的
体层解析件**（跨 adapter import 会引入耦合，`_oai` 分层边界注释明示"体层由调用方注入"），
刻意接受 ~50 行与 aaai 的重复（★C 退路）。

**DOI = 唯一强 identifier（★B，econsoc.md §3.4）**：三刊 DOI 均为 Econometric Society
为本篇本版注册的本源官方 id（前缀 `10.3982` 学会自持、三刊共用、仅后缀 `ecta`/`te`/`qe`
区分刊，survey §1）。归一经 `ids.normalize_doi`（统一入口，小写化 + 剥前缀），不剥
`10.3982` 前缀、不改分隔符。

**ECMA 年代分段路由（方向 a，D-028/econsoc.md §3.3）**：ECMA(ECTA) DOI 跨三托管年代——
当前段自营 `econometricsociety.org`（OA）、过刊段 `doi.wiley.com`（Phase 5：`no_entitlement`
/skip，跨 adapter handoff defer）、pre-DOI 段 JSTOR（10.2307，界外）。判定以 DOI 实际落地
域名为权威信号（resolve 时的实时终点）；crossref `resource.primary.URL` 域名仅作 pre-filter
提示（**有陈旧风险**：QE crossref link 仍留遗留 Wiley link——权威取实时落地，见 §3.3 caveat）。
"""

from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import urljoin

from paper_crawler.adapters import _oai
from paper_crawler.adapters._oai import OaiListPage  # 再导出：信封页形状（体层记录=EconsocRecord）
from paper_crawler.errors import CrawlerError, ErrorClass
from paper_crawler.ids import normalize_doi
from paper_crawler.types import PaperStub

# --- 命名空间（oai_dc 体层）------------------------------------------------------------------

_OAI_DC_NS = "http://www.openarchives.org/OAI/2.0/oai_dc/"
_DC_NS = "http://purl.org/dc/elements/1.1/"


def _oai_dc(name: str) -> str:
    return f"{{{_OAI_DC_NS}}}{name}"


def _dc(name: str) -> str:
    return f"{{{_DC_NS}}}{name}"


# --- DOI 路由（design §3.1/§3.4；survey §1）---------------------------------------------------

# Econometric Society 自持前缀 `10.3982`，三刊共用、仅 DOI 后缀 ecta/te/qe 区分刊（survey §1）。
# 归一后小写，故此处匹配小写后缀；`\d` 锚定后缀确有编号（排除 `10.3982/foo` 之类非本源形态）。
_ECONSOC_DOI_RE = re.compile(r"^10\.3982/(ecta|te|qe)\d")
# JSTOR pre-DOI 时代前缀（ECMA <2010 过刊，survey §2 `10.2307/1912227`→jstor.org）。
_PRE_DOI_PREFIX = "10.2307/"
# DOI 后缀 token → venue 键：ecta 后缀属 Econometrica（venue id=ecma），te/qe 同名。
_TOKEN_TO_JOURNAL = {"ecta": "ecma", "te": "te", "qe": "qe"}

# 裸 DOI 形态（前缀 10.NNNN/…）；从多个 dc:identifier 中择出 DOI（另一个是 landing URL）。
_DOI_RE = re.compile(r"10\.\d{4,9}/\S+")
# 从 OJS landing URL 抽 article id：/article/view/{id}[/…]（TE/QE OJS 端点形态，survey §4）。
_ARTICLE_ID_RE = re.compile(r"/article/view/(\d+)")


def journal_of_doi(doi: str) -> str | None:
    """从归一 DOI 抽刊别：`ecta`→``'ecma'`` / `te`→``'te'`` / `qe`→``'qe'``；非本源形态 → None。

    membership 判据（TE/QE OAI enumerate 客户端过滤，design §4）与 ECMA 识别共用此单点
    （前缀 `10.3982` 三刊共用，仅后缀区分刊——裸前缀不可判刊，见 D-028）。
    """
    match = _ECONSOC_DOI_RE.match(normalize_doi(doi))
    return _TOKEN_TO_JOURNAL[match.group(1)] if match else None


def is_pre_doi(doi: str) -> bool:
    """本 DOI 是否为 ECMA pre-DOI 时代（JSTOR 旧前缀 `10.2307`，survey §2）。

    ECMA 分段路由面 = modern `10.3982/ecta`（`journal_of_doi=='ecma'`）∪ pre-DOI `10.2307`
    （journal_of_doi 判 None，但仍属 ECMA 界外过刊面）；TE/QE 自 2006 born-DOI（10.3982），
    无 pre-DOI 时代，不涉此面（resolve 据此把 pre-DOI 归 PRE_DOI 界外零资产，而非误 GET
    econsoc 当前段落地页）。
    """
    return normalize_doi(doi).startswith(_PRE_DOI_PREFIX)


# --- ECMA 年代分段路由（design §3.3 方向 a；D-028）---------------------------------------------


class EcmaSegment(StrEnum):
    """ECMA(ECTA) DOI 的托管年代分段（design §3.3）——决定 fulltext 归属 adapter。"""

    CURRENT = "current"  # 当前段：econometricsociety.org 自营 OA → 本 adapter 取回
    BACKFILE = "backfile"  # 过刊段：doi.wiley.com → Phase 5 `no_entitlement`/skip（handoff defer）
    PRE_DOI = "pre_doi"  # pre-DOI 段：JSTOR（10.2307）→ 界外零资产（tier T3 暂缓）


def classify_ecma_segment(doi: str, *, landing_domain: str | None) -> EcmaSegment:
    """按 DOI + 落地域名判 ECMA 分段归属（design §3.3 方向 a）。

    - `10.2307/…`（JSTOR pre-DOI 旧前缀）→ ``PRE_DOI``（无需域名，前缀即判据，survey §2）。
    - `10.3982/ecta…`：以落地域名为准——``doi.wiley.com``/含 ``wiley`` → ``BACKFILE``；
      含 ``jstor`` → ``PRE_DOI``；``econometricsociety.org`` 或**未知/缺域名** → ``CURRENT``
      （乐观默认：当前段是主路径、过刊段是例外；误路由的过刊 DOI 会在 resolve 落地 GET 时
      自然暴露为 GONE/no_entitlement，不阻塞主路径，design §3.3/§6）。

    **caveat（design §3.3）**：`landing_domain` 若取自 crossref `resource.primary.URL` 有陈旧
    风险（当前 ECMA 的 crossref link 可能仍留遗留 Wiley link → 误判 BACKFILE）——故本函数只
    是"给定域名的纯判定"，**权威信号应是 resolve 时的实时落地域名**（doi.org HEAD `-L` 终点），
    crossref 登记域名仅作 pre-filter 提示，见 adapter `resolve_assets` 与在线冒烟。
    """
    norm = normalize_doi(doi)
    if norm.startswith(_PRE_DOI_PREFIX):
        return EcmaSegment.PRE_DOI
    if landing_domain:
        host = landing_domain.lower()
        if "wiley" in host:
            return EcmaSegment.BACKFILE
        if "jstor" in host:
            return EcmaSegment.PRE_DOI
    return EcmaSegment.CURRENT


# --- 中间记录 --------------------------------------------------------------------------------


@dataclass(frozen=True)
class EconsocRecord:
    """一条 `oai_dc` 记录的解析产物（design §4 字段映射）。

    ``doi``：已归一（小写规范）的本源 DOI——唯一强 identifier 锚点（★B）。``journal``：从
    DOI 后缀抽出的刊别（``'ecma'``/``'te'``/``'qe'``；TE/QE enumerate 客户端过滤维度）。
    ``pdf_view_url``：首个 ``dc:relation``（galley/article view URL，resolve 输入线索）。
    ``article_id``：从 landing URL 抽出的 OJS 内部 id（供 meta/对账）。``rights``：
    ``dc:rights``（CC 许可串，OA 佐证/canary 观测，不入 stub）。
    """

    doi: str
    journal: str | None
    title: str
    abstract: str | None
    authors: tuple[str, ...]
    date: str | None
    landing_url: str | None
    pdf_view_url: str | None
    article_id: str | None
    source: str | None
    rights: str | None


# --- 公开 API：OAI-PMH ListRecords / GetRecord（信封复用共享核，体层为 oai_dc）------------------


def parse_oai_page(data: bytes) -> OaiListPage[EconsocRecord]:
    """解析一页 OAI-PMH `ListRecords`：记录 + 续爬令牌 + 墓碑跳过数（信封走共享核 `_oai`）。

    本函数仅注入 econsoc 体层回调 `_parse_oai_dc_metadata`（``<metadata>`` → `EconsocRecord`）。
    记录**未做 DOI 后缀过滤**（adapter 职责——解析层只认 OAI 协议形态）。
    """
    return _oai.parse_oai_page(data, record_parser=_parse_oai_dc_metadata)


def parse_get_record(data: bytes) -> EconsocRecord:
    """解析 OAI-PMH `GetRecord` 响应为单条 `EconsocRecord`（canary 用，design §4/§7）。

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


# --- oai_dc 体层薄解析器（★C：自写，严禁复用 aaai 体层）------------------------------------------


def _parse_oai_dc_metadata(metadata: ET.Element) -> EconsocRecord:
    """econsoc 体层回调：从 `<metadata>` 定位 ``<oai_dc:dc>`` 并解析为 `EconsocRecord`。

    ``<metadata>`` 存在但缺 ``<oai_dc:dc>``（如误配 schema）是真实解析失败 → `PARSE`
    （非墓碑——墓碑是"整条缺 metadata"，此处是"metadata 在但 schema 错"，见 `_oai` 分层边界）。
    """
    dc_el = metadata.find(_oai_dc("dc"))
    if dc_el is None:
        raise CrawlerError(ErrorClass.PARSE, "OAI record <metadata> missing <oai_dc:dc> element")

    title = _oai.required_text(dc_el, _dc("title"), context="econsoc oai_dc record")

    identifier_values = [text for el in dc_el.findall(_dc("identifier")) if (text := el.text)]
    raw_doi, landing_url = _classify_identifiers(identifier_values)
    if raw_doi is None:
        raise CrawlerError(
            ErrorClass.PARSE,
            f"econsoc oai_dc record {title!r} has no DOI among dc:identifier {identifier_values!r}",
        )
    doi = normalize_doi(raw_doi)

    authors = tuple(
        name
        for el in dc_el.findall(_dc("creator"))
        if el.text and (name := _oai.normalize_ws(el.text))
    )
    return EconsocRecord(
        doi=doi,
        journal=journal_of_doi(doi),
        title=title,
        abstract=_oai.optional_text(dc_el, _dc("description")),
        authors=authors,
        date=_oai.optional_text(dc_el, _dc("date")),
        landing_url=landing_url,
        pdf_view_url=_oai.optional_text(dc_el, _dc("relation")),
        article_id=_article_id_from_landing(landing_url),
        source=_oai.optional_text(dc_el, _dc("source")),
        rights=_oai.optional_text(dc_el, _dc("rights")),
    )


def _classify_identifiers(values: list[str]) -> tuple[str | None, str | None]:
    """把 dc:identifier 值序列分成 (DOI, landing URL)。

    DOI = 首个匹配裸 DOI 正则者；landing = 首个 http(s) URL（且非 DOI）。TE/QE oai_dc 恰有
    两个 dc:identifier——一个 landing 文章页 URL、一个裸 DOI（survey §4）。
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


def _article_id_from_landing(landing_url: str | None) -> str | None:
    if landing_url is None:
        return None
    match = _ARTICLE_ID_RE.search(landing_url)
    return match.group(1) if match else None


# --- PaperStub 转换（design §3.4 meta 键名定死）------------------------------------------------


def to_paper_stub(record: EconsocRecord) -> PaperStub:
    """把 `EconsocRecord` 转成 `PaperStub`（design §3.4/§4 字段映射逐字执行）。

    ``identifiers`` 恒为单一 ``(('doi', <小写规范串>),)``（★B 本源强锚点）。``meta`` 键名
    定死（design §3.4）：``pdf_url``（dc:relation galley/view URL，resolve 输入线索）、
    ``landing_url``（文章页 URL）、可选 ``ojs_article_id``（TE/QE）、可选 ``ojs_source``
    （dc:source 期号串，对账）。摘要/作者走 `PaperStub` 一级字段，**不入 meta**。
    """
    meta: list[tuple[str, str]] = []
    if record.pdf_view_url:
        meta.append(("pdf_url", record.pdf_view_url))
    if record.landing_url:
        meta.append(("landing_url", record.landing_url))
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


# --- 落地页 galley 链抽取（design §4：resolve 阶段 GET 落地页抽 galley）-------------------------

# 当前段自营前端的 galley PDF 链：`/publications/{journal}/{y}/{m}/{d}/{slug}/file/{file}.PDF`
# （survey §4 [LIVE]）。`{file}`/`{slug}` 非 DOI 可构造 → 必 GET 落地页正则抽取（HTML 依赖面，
# canary 监）。class 不含 pdf 佐证时以路径 `/file/*.pdf` 为准；`.PDF` 大写经 IGNORECASE 覆盖。
_GALLEY_HREF_RE = re.compile(r'href\s*=\s*["\']([^"\']*/file/[^"\']*?\.pdf)["\']', re.IGNORECASE)


def extract_galley_url(data: bytes, *, base_url: str) -> str | None:
    """从当前段落地页 HTML 抽首个 galley PDF 链（`/publications/.../file/{file}.PDF`）。

    相对链经 `urljoin(base_url, …)` 归一为绝对 URL（base = 落地页 URL，同源）。无 galley
    链（撤稿/合并/非 OA 页）→ None（adapter 据此产 0 资产，非错误）。HTML 依赖面，canary 监。
    """
    text = data.decode("utf-8", errors="replace")
    match = _GALLEY_HREF_RE.search(text)
    if match is None:
        return None
    return urljoin(base_url, html.unescape(match.group(1)))


# --- OAI Identify（healthcheck 存活基线）------------------------------------------------------


def identify_repository_name(data: bytes) -> str | None:
    """从 OAI `Identify` 响应取 `repositoryName`（缺 `<Identify>`/`<repositoryName>` → None）。

    healthcheck 存活基线：TE OAI Identify 的 repositoryName 含 "Theoretical Economics"
    （design §4）。信封小工具复用 `_oai`（`fromstring`/`oai`/`optional_text`）。
    """
    root = _oai.fromstring(data)
    identify = root.find(_oai.oai("Identify"))
    if identify is None:
        return None
    return _oai.optional_text(identify, _oai.oai("repositoryName"))


__all__ = [
    "EconsocRecord",
    "EcmaSegment",
    "OaiListPage",
    "classify_ecma_segment",
    "extract_galley_url",
    "identify_repository_name",
    "is_pre_doi",
    "journal_of_doi",
    "parse_get_record",
    "parse_oai_page",
    "to_paper_stub",
]
