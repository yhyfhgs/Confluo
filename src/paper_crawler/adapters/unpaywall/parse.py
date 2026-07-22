"""Unpaywall `/v2/{doi}` 响应解析（design/adapters/aggregators.md §5.5）。

纯函数层：JSON 字节 → 结构化 `UnpaywallRecord`，零网络、零 obslog（网络请求与
观测事件归 `adapter.py`）。字段目标见 aggregators.md §5.5 映射表：

- `is_oa`/`oa_status`：命中率报告与 resolve 判据的核心两个字段（`is_oa` 必需，
  缺失/非 bool → `PARSE`；`oa_status`(gold/green/hybrid/bronze/closed) 可空）。
- `best_oa_location`/`oa_locations[]`：仅取 `version`/`url_for_pdf`/
  `url_for_landing_page` 三个子字段（本系统不消费 `host_type`/`license`/`evidence`
  等其余字段）。Asset.version 精确串见 `KNOWN_VERSIONS`/`INFORMAL_VERSIONS`
  （D5 精度修订：全拼 `submittedVersion`/`acceptedVersion`/`publishedVersion`）。

回退链（`best_oa_location.url_for_pdf` 为 null 时，§5.5「回退链」行）：
`select_pdf_location` 遍历 `oa_locations[]` 找首个带 `url_for_pdf` 的项；两处都没有
则 `landing_url_of` 取 `best_oa_location.url_for_landing_page` 供 adapter 仅记
`meta.oa_landing_url`、不产 AssetPlan（★裁决 J4——无 PDF 直链不下载 landing 页）。
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from paper_crawler.errors import CrawlerError, ErrorClass

# aggregators.md §5.5：Asset.version 精确串（[LIVE] 全拼，D5 精度修订；research/
# site-survey/metadata-apis.md D5：实测全拼，非 submitted/accepted/published 简写）。
PUBLISHED_VERSION = "publishedVersion"
ACCEPTED_VERSION = "acceptedVersion"
SUBMITTED_VERSION = "submittedVersion"
KNOWN_VERSIONS = (SUBMITTED_VERSION, ACCEPTED_VERSION, PUBLISHED_VERSION)
# submitted/accepted 是「非正式版」（未定稿/未排版终稿）；published 是正式版。
INFORMAL_VERSIONS = frozenset({SUBMITTED_VERSION, ACCEPTED_VERSION})


@dataclass(frozen=True)
class OaLocation:
    """`best_oa_location`/`oa_locations[]` 单条项的三个消费字段。"""

    version: str | None
    url_for_pdf: str | None
    url_for_landing_page: str | None


@dataclass(frozen=True)
class UnpaywallRecord:
    """一次 `/v2/{doi}` 查询结果的结构化形态（RESOLVE only，不产 identifier，§6）。"""

    doi: str
    is_oa: bool
    oa_status: str | None
    best_oa_location: OaLocation | None
    oa_locations: tuple[OaLocation, ...]


def _load_json(data: bytes) -> object:
    try:
        return json.loads(data)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise CrawlerError(ErrorClass.PARSE, f"malformed unpaywall json: {exc}") from exc


def _str_or_none(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _location_of(raw: object) -> OaLocation | None:
    """把响应里的单个 location 对象（或 None/畸形）转成 `OaLocation`。

    Unpaywall 的 location 对象字段众多（`host_type`/`license`/`evidence`/...），本系统
    只消费三个；`raw` 非 dict（如 closed 记录里的 `null`）时返回 None——`best_oa_location`
    合法为 null，非解析错误。
    """
    if not isinstance(raw, dict):
        return None
    return OaLocation(
        version=_str_or_none(raw.get("version")),
        url_for_pdf=_str_or_none(raw.get("url_for_pdf")),
        url_for_landing_page=_str_or_none(raw.get("url_for_landing_page")),
    )


def _oa_locations_of(doc: dict[str, object]) -> tuple[OaLocation, ...]:
    raw_list = doc.get("oa_locations")
    if not isinstance(raw_list, list):
        return ()
    locations: list[OaLocation] = []
    for item in raw_list:
        location = _location_of(item)
        if location is not None:
            locations.append(location)
    return tuple(locations)


def parse_response(data: bytes, *, doi: str) -> UnpaywallRecord:
    """解析原始响应字节 → `UnpaywallRecord`；语法错误/必需字段缺失 → `CrawlerError(PARSE)`。

    `doi` 是调用方已知的请求 DOI——**不**从响应体的 `doi` 字段读回（unpaywall 不产
    identifier，「以输入 DOI 为键」，§6；避免响应体大小写/前缀差异污染下游比对）。
    唯一必需字段是 `is_oa`（bool）；`oa_status`/`best_oa_location`/`oa_locations`
    缺失或为 null 时分别按 None/None/() 兜底——Unpaywall 的 closed 记录这三者常缺，
    属正常形态，非解析错误。
    """
    doc = _load_json(data)
    if not isinstance(doc, dict):
        raise CrawlerError(
            ErrorClass.PARSE,
            f"unpaywall response top level must be a JSON object, got {type(doc).__name__}",
        )

    is_oa = doc.get("is_oa")
    if not isinstance(is_oa, bool):
        raise CrawlerError(
            ErrorClass.PARSE, f"unpaywall response missing/non-bool 'is_oa': {is_oa!r}"
        )

    return UnpaywallRecord(
        doi=doi,
        is_oa=is_oa,
        oa_status=_str_or_none(doc.get("oa_status")),
        best_oa_location=_location_of(doc.get("best_oa_location")),
        oa_locations=_oa_locations_of(doc),
    )


def select_pdf_location(record: UnpaywallRecord) -> OaLocation | None:
    """回退链：`best_oa_location` 有 `url_for_pdf` → 用它；否则遍历 `oa_locations[]`
    取首个带 `url_for_pdf` 的项；都没有 → None（调用方据此判定「仅 landing」或「无 OA」）。
    """
    best = record.best_oa_location
    if best is not None and best.url_for_pdf:
        return best
    for location in record.oa_locations:
        if location.url_for_pdf:
            return location
    return None


def landing_url_of(record: UnpaywallRecord) -> str | None:
    """`url_for_pdf` 全线为空时的 landing 兜底：`best_oa_location.url_for_landing_page`
    （★裁决 J4：仅供 adapter 记 `meta.oa_landing_url`，不产 AssetPlan）。
    `best_oa_location` 缺失（如 closed 记录）→ None。
    """
    best = record.best_oa_location
    return best.url_for_landing_page if best is not None else None


__all__ = [
    "ACCEPTED_VERSION",
    "INFORMAL_VERSIONS",
    "KNOWN_VERSIONS",
    "OaLocation",
    "PUBLISHED_VERSION",
    "SUBMITTED_VERSION",
    "UnpaywallRecord",
    "landing_url_of",
    "parse_response",
    "select_pdf_location",
]
