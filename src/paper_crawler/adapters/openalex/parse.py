"""OpenAlex `works` 响应解析与字段映射（design/adapters/aggregators.md §5.3 逐行）。

零网络、零 obslog（沿 unpaywall/crossref parse.py 先例：网络请求与观测事件归
`adapter.py`）。只用标准库 `json`。

字段映射（§5.3 表逐行）：
- identifier(openalex) = `id`（`https://openalex.org/W...` 剥 URL 前缀取裸 `W...`）；
  **恒有**——响应条目缺失/畸形时该条目跳过（不产半条 stub）。
- identifier(doi) = `doi`（裸或 `https://doi.org/...`）→ `ids.normalize_doi()`；缺失则
  不产该 identifier（stub 仍可仅凭 openalex id 成立）。
- title = `title`；**缺失/空白 → 跳过该记录 + 计 `skipped_untitled`**（★同 crossref
  裁决：title 是 `paper.title NOT NULL`，占位符会污染 `title_norm` 弱信号匹配面，
  宁缺勿污）。
- abstract = `abstract_inverted_index`（`{词: [位置,...]}` 倒排索引）→ 按位置重排拼回
  纯文本；空字典 `{}` 视为"该记录确无摘要"（非畸形）→ `None`；非字典/值非法（非
  list[int] 位置）→ `CrawlerError(PARSE)`（§5.3 错误映射表"倒排索引畸形→parse"）。
- authors = `authorships[].author.display_name`；缺失/畸形条目静默跳过（防御，非阻塞）。
- year/pub_date = `publication_year` / `publication_date`。
- OA（meta） = `open_access.{is_oa,oa_status,oa_url}`、`best_oa_location.pdf_url`——
  `PaperStub.meta` 值类型冻结为 `str`（aggregators.md §6 A-C1）：`is_oa`（bool）经
  `str().lower()` 存 `"true"/"false"`，其余标量原样字符串。
- `meta.cost_usd`（响应顶层 `meta.cost_usd`）供预算核销（§4），**不**进 `PaperStub.meta`
  ——它是本次请求的开销记账，不是某篇论文的属性，随 `WorksPage.cost_usd` 单独返回。
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from paper_crawler.errors import CrawlerError, ErrorClass
from paper_crawler.ids import normalize_doi
from paper_crawler.types import PaperStub

_OPENALEX_ID_PREFIX = "https://openalex.org/"
_DOI_URL_PREFIXES = ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/")


# --- 中间/输出类型 -----------------------------------------------------------------------------


@dataclass(frozen=True)
class WorksPage:
    """一次 `works?filter=doi:...` 批查响应：产出 stub 流 + 请求开销 + 跳过统计。"""

    stubs: tuple[PaperStub, ...]
    cost_usd: float
    skipped_untitled: int
    skipped_no_identifier: int


# --- 公开 API：批查响应 ------------------------------------------------------------------------


def parse_works_batch(data: bytes) -> WorksPage:
    """解析 `GET /works?filter=doi:...` 响应为 `WorksPage`（§5.3）。

    顶层须为 JSON 对象且含 `results` 数组；`meta.cost_usd` 缺失/非数值 → 记 0（"或 0"
    兜底，同 §4 伪代码 `spent += float(resp.meta.cost_usd or 0)`）。逐条 `results[]`
    经 `_stub_of` 转换；返回 `None`（缺标题/缺全部 identifier）计入相应跳过计数、不
    产出 stub（不中断整页——单条数据缺陷不应拖垮同批其余条目）。
    """
    doc = _load_json(data)
    if not isinstance(doc, dict):
        raise CrawlerError(
            ErrorClass.PARSE,
            f"openalex works response top level must be a JSON object, got {type(doc).__name__}",
        )
    meta = doc.get("meta")
    cost_usd = _parse_cost_usd(meta.get("cost_usd")) if isinstance(meta, dict) else 0.0

    results = doc.get("results")
    if not isinstance(results, list):
        raise CrawlerError(ErrorClass.PARSE, "openalex works response missing 'results' list")

    stubs: list[PaperStub] = []
    skipped_untitled = 0
    skipped_no_identifier = 0
    for item in results:
        if not isinstance(item, dict):
            skipped_untitled += 1
            continue
        outcome = _stub_of(item)
        if outcome is None:
            skipped_untitled += 1
            continue
        stub, has_identifier = outcome
        if not has_identifier:
            skipped_no_identifier += 1
            continue
        stubs.append(stub)

    return WorksPage(
        stubs=tuple(stubs),
        cost_usd=cost_usd,
        skipped_untitled=skipped_untitled,
        skipped_no_identifier=skipped_no_identifier,
    )


# --- 公开 API：单条 work（healthcheck）----------------------------------------------------------


def parse_single_work_title(data: bytes) -> str:
    """解析 `GET /works/W{id}` 单条响应，返回空白规整化的 `title`；缺 title → `PARSE`。"""
    doc = _load_json(data)
    if not isinstance(doc, dict):
        raise CrawlerError(
            ErrorClass.PARSE,
            f"openalex single work response top level must be a JSON object, "
            f"got {type(doc).__name__}",
        )
    title = _clean_title(doc.get("title"))
    if title is None:
        raise CrawlerError(ErrorClass.PARSE, "openalex single work has empty/missing title")
    return title


# --- 模块级纯函数 ------------------------------------------------------------------------------


def _load_json(data: bytes) -> object:
    try:
        return json.loads(data)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise CrawlerError(ErrorClass.PARSE, f"malformed openalex json: {exc}") from exc


def _clean_title(raw: object) -> str | None:
    if not isinstance(raw, str):
        return None
    collapsed = " ".join(raw.split())
    return collapsed or None


def _bare_openalex_id(raw: str) -> str:
    """`https://openalex.org/W...` → 裸 `W...`；已是裸值时原样返回。"""
    if raw.startswith(_OPENALEX_ID_PREFIX):
        return raw[len(_OPENALEX_ID_PREFIX) :]
    return raw


def _clean_doi(raw: object) -> str | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    return normalize_doi(raw)


def _identifiers_of(item: dict[str, object]) -> tuple[tuple[str, str], ...]:
    ids: list[tuple[str, str]] = []
    raw_id = item.get("id")
    if isinstance(raw_id, str) and raw_id.strip():
        ids.append(("openalex", _bare_openalex_id(raw_id.strip())))
    doi = _clean_doi(item.get("doi"))
    if doi:
        ids.append(("doi", doi))
    return tuple(ids)


def _reconstruct_abstract(inverted: dict[object, object]) -> str:
    """`abstract_inverted_index`（非空）→ 按位置重排拼回纯文本；畸形 → `CrawlerError(PARSE)`。"""
    positions: list[tuple[int, str]] = []
    max_pos = -1
    for word, pos_list in inverted.items():
        if not isinstance(word, str) or not isinstance(pos_list, list):
            raise CrawlerError(
                ErrorClass.PARSE,
                f"openalex abstract_inverted_index malformed entry for {word!r}: {pos_list!r}",
            )
        for pos in pos_list:
            if not isinstance(pos, int) or isinstance(pos, bool) or pos < 0:
                raise CrawlerError(
                    ErrorClass.PARSE,
                    f"openalex abstract_inverted_index malformed position {pos!r} "
                    f"for word {word!r}",
                )
            positions.append((pos, word))
            max_pos = max(max_pos, pos)
    if not positions:
        return ""
    slots: list[str | None] = [None] * (max_pos + 1)
    for pos, word in positions:
        slots[pos] = word
    return " ".join(word for word in slots if word is not None)


def _abstract_of(item: dict[str, object]) -> str | None:
    raw = item.get("abstract_inverted_index")
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise CrawlerError(
            ErrorClass.PARSE,
            f"openalex abstract_inverted_index must be an object, got {type(raw).__name__}",
        )
    if not raw:
        return None  # 空字典＝该记录确无摘要，非畸形
    text = _reconstruct_abstract(raw)
    return text or None


def _authors_of(item: dict[str, object]) -> tuple[str, ...]:
    raw = item.get("authorships")
    if not isinstance(raw, list):
        return ()
    names: list[str] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        author = entry.get("author")
        if not isinstance(author, dict):
            continue
        name = author.get("display_name")
        if isinstance(name, str) and name.strip():
            names.append(name.strip())
    return tuple(names)


def _meta_of(item: dict[str, object]) -> tuple[tuple[str, str], ...]:
    meta: list[tuple[str, str]] = []
    oa = item.get("open_access")
    if isinstance(oa, dict):
        is_oa = oa.get("is_oa")
        if isinstance(is_oa, bool):
            meta.append(("is_oa", "true" if is_oa else "false"))
        oa_status = oa.get("oa_status")
        if isinstance(oa_status, str) and oa_status:
            meta.append(("oa_status", oa_status))
        oa_url = oa.get("oa_url")
        if isinstance(oa_url, str) and oa_url:
            meta.append(("oa_url", oa_url))
    best_location = item.get("best_oa_location")
    if isinstance(best_location, dict):
        pdf_url = best_location.get("pdf_url")
        if isinstance(pdf_url, str) and pdf_url:
            meta.append(("pdf_url", pdf_url))
    return tuple(meta)


def _int_or_none(raw: object) -> int | None:
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return raw
    return None


def _str_or_none(raw: object) -> str | None:
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return None


def _stub_of(item: dict[str, object]) -> tuple[PaperStub, bool] | None:
    """单条 `results[]` 条目 → `(PaperStub, has_identifier)`；缺标题 → `None`（调用方跳过计）。

    `has_identifier` 恒应为真（`id` 字段"恒有"，§5.3）；仍显式返回该标志防御性覆盖
    "响应条目本身就残缺到连 `id` 都没有"的边界——调用方据此计入 `skipped_no_identifier`
    而非产出一个违反"identifiers 至少 1 个"约定的空锚点 stub。
    """
    title = _clean_title(item.get("title"))
    if title is None:
        return None
    identifiers = _identifiers_of(item)
    stub = PaperStub(
        title=title,
        identifiers=identifiers,
        year=_int_or_none(item.get("publication_year")),
        pub_date=_str_or_none(item.get("publication_date")),
        abstract=_abstract_of(item),
        authors=_authors_of(item),
        meta=_meta_of(item),
    )
    return stub, bool(identifiers)


def _parse_cost_usd(value: object) -> float:
    """`meta.cost_usd` 宽容转 float；缺失/非数值/非法字符串 → 0.0（"或 0"兜底，§4）。"""
    if isinstance(value, bool):
        return 0.0
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return 0.0
    return 0.0


__all__ = ["WorksPage", "parse_single_work_title", "parse_works_batch"]
