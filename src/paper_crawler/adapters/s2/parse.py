"""S2 `POST /paper/batch` 响应解析与字段映射（design/adapters/aggregators.md §5.4 逐行）。

零网络、零 obslog（沿 crossref/unpaywall/openalex parse.py 先例）。只用标准库 `json`。

响应形态：JSON 数组，**与请求体 `ids` 同序对齐**，未命中的位置为 `null`（S2 batch
端点契约；官方 [DOCS]，非本次实现在线核验）——`null` 是正常"该 id 未命中"结果，非
异常。

字段映射（§5.4 表逐行 + title 的隐含必要性）：
- title：设计表未列（S2 稀疏返回须显式 `fields=`，实现层已在请求侧把 `title` 并入
  `fields`——见 `adapter.py` 的 `_FIELDS`）；**缺失/空白 → 跳过该记录**（同 crossref/
  openalex 裁决：`paper.title NOT NULL`，宁缺勿污 title_norm 弱信号匹配面）。
- identifier(s2) = `paperId`（"恒有（命中时）"）。
- identifier(doi) = `externalIds.DOI` → `ids.normalize_doi()`；缺失则不产该 identifier。
- citations(meta) = `citationCount` → `meta["citation_count"]`（int 经 `str()`，
  `PaperStub.meta` 值类型冻结为 str，aggregators.md §6 A-C1）。
- tldr(meta) = `tldr.text` → `meta["tldr"]`。
- fieldsOfStudy(meta) = `fieldsOfStudy` → `meta["fields_of_study"]`（list 经
  `json.dumps`，非标量结构必须序列化）。
- OA(meta) = `openAccessPdf.{url,status,license}` → `meta["pdf_url"]`（与 openalex
  `pdf_url` 同名——同一概念"该论文的 OA PDF 直链"，字段级来源优先级收敛据此正确竞合，
  见 `merge.py` `SOURCE_PRIORITY`）/ `meta["oa_status"]` / `meta["oa_license"]`。
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from paper_crawler.errors import CrawlerError, ErrorClass
from paper_crawler.ids import normalize_doi
from paper_crawler.types import PaperStub


@dataclass(frozen=True)
class BatchResult:
    """一次 `POST /paper/batch` 响应：产出 stub 流 + 跳过/未命中统计。"""

    stubs: tuple[PaperStub, ...]
    not_found: int  # 数组中为 null 的位置数（该 id 未命中，正常结果非错误）
    skipped_untitled: int  # 命中但 title 缺失/空白（宁缺勿污，跳过不入 stub）


def parse_batch_response(data: bytes) -> BatchResult:
    """解析 `POST /paper/batch` 响应为 `BatchResult`（§5.4）。

    顶层须为 JSON 数组；逐元素：`null` → 计 `not_found`；非对象/缺 title → 计
    `skipped_untitled`；否则经 `_stub_of` 转换入 `stubs`。单条数据缺陷不中断整批
    （同 openalex/crossref 的"跳过不炸整页"先例）。
    """
    doc = _load_json(data)
    if not isinstance(doc, list):
        raise CrawlerError(
            ErrorClass.PARSE,
            f"s2 batch response top level must be a JSON array, got {type(doc).__name__}",
        )

    stubs: list[PaperStub] = []
    not_found = 0
    skipped_untitled = 0
    for entry in doc:
        if entry is None:
            not_found += 1
            continue
        if not isinstance(entry, dict):
            skipped_untitled += 1
            continue
        stub = _stub_of(entry)
        if stub is None:
            skipped_untitled += 1
            continue
        stubs.append(stub)

    return BatchResult(stubs=tuple(stubs), not_found=not_found, skipped_untitled=skipped_untitled)


def parse_single_paper_title(data: bytes) -> str:
    """解析 `GET /paper/DOI:{doi}?fields=title` 单条响应，返回空白规整化 `title`。

    healthcheck 专用（§5.4："有 key → GET /paper/DOI:{固定DOI}?fields=title 比对规整化
    title"）。缺 title → `PARSE`。
    """
    doc = _load_json(data)
    if not isinstance(doc, dict):
        raise CrawlerError(
            ErrorClass.PARSE,
            f"s2 single paper response top level must be a JSON object, got {type(doc).__name__}",
        )
    title = _clean_title(doc.get("title"))
    if title is None:
        raise CrawlerError(ErrorClass.PARSE, "s2 single paper has empty/missing title")
    return title


# --- 模块级纯函数 ------------------------------------------------------------------------------


def _load_json(data: bytes) -> object:
    try:
        return json.loads(data)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise CrawlerError(ErrorClass.PARSE, f"malformed s2 json: {exc}") from exc


def _clean_title(raw: object) -> str | None:
    if not isinstance(raw, str):
        return None
    collapsed = " ".join(raw.split())
    return collapsed or None


def _identifiers_of(entry: dict[str, object]) -> tuple[tuple[str, str], ...]:
    ids: list[tuple[str, str]] = []
    paper_id = entry.get("paperId")
    if isinstance(paper_id, str) and paper_id.strip():
        ids.append(("s2", paper_id.strip()))
    external = entry.get("externalIds")
    if isinstance(external, dict):
        doi = external.get("DOI")
        if isinstance(doi, str) and doi.strip():
            ids.append(("doi", normalize_doi(doi)))
    return tuple(ids)


def _meta_of(entry: dict[str, object]) -> tuple[tuple[str, str], ...]:
    meta: list[tuple[str, str]] = []
    citation_count = entry.get("citationCount")
    if isinstance(citation_count, int) and not isinstance(citation_count, bool):
        meta.append(("citation_count", str(citation_count)))
    tldr = entry.get("tldr")
    if isinstance(tldr, dict):
        text = tldr.get("text")
        if isinstance(text, str) and text.strip():
            meta.append(("tldr", text.strip()))
    fields_of_study = entry.get("fieldsOfStudy")
    if isinstance(fields_of_study, list) and fields_of_study:
        cleaned = [f for f in fields_of_study if isinstance(f, str) and f]
        if cleaned:
            meta.append(("fields_of_study", json.dumps(cleaned)))
    oa_pdf = entry.get("openAccessPdf")
    if isinstance(oa_pdf, dict):
        url = oa_pdf.get("url")
        if isinstance(url, str) and url:
            meta.append(("pdf_url", url))
        status = oa_pdf.get("status")
        if isinstance(status, str) and status:
            meta.append(("oa_status", status))
        license_ = oa_pdf.get("license")
        if isinstance(license_, str) and license_:
            meta.append(("oa_license", license_))
    return tuple(meta)


def _stub_of(entry: dict[str, object]) -> PaperStub | None:
    title = _clean_title(entry.get("title"))
    if title is None:
        return None
    identifiers = _identifiers_of(entry)
    if not identifiers:
        return None  # 防御边界：连 paperId 都缺失的残缺条目，不产违反"至少 1 个 identifier"的 stub
    return PaperStub(
        title=title,
        identifiers=identifiers,
        abstract=None,  # S2 abstract 未列入 §5.4 映射表/请求 fields，恒 None（不越权抓取范围）
        authors=(),  # 同上：§5.4 表未列 authors
        meta=_meta_of(entry),
    )


__all__ = ["BatchResult", "parse_batch_response", "parse_single_paper_title"]
