r"""NBER 零网络纯逻辑（design/adapters/nber.md §3.2/§3.4/§7）。

无网络、无副作用：DOI→series 号抽取、18 月开放窗离线谓词、全文 PDF URL 构造、
RSS `<item>` 反解（watch 通道设计）、软门 HTML 嗅探判据。只用标准库（`re`/
`datetime`/`xml.etree`）——不引第三方（沿 crossref/_oai「stdlib 解析」先例）。

**红线核心 = 18 月开放窗谓词**（`is_open_after_window`）：`open := (today − pub_date)
≥ window 月`。**离线判定**替代 elsevier 的网络 entitlement 预检——NBER 的"entitlement"
即 18 月窗，可由 `pub_date` 纯算（nber.md §3.2）。缺失/畸形 `pub_date` → **保守判开放**
（§3.2 步 2：交 fetch 阶段 `%PDF` 魔数守卫兜底，非"猜配额"——单次善意请求命中软门即
`no_entitlement` 退避，绝不重试/换 IP/走配额，红线不触）。

series 抽取（`series_id_from_doi`）：`^10\.3386/([wt]\d+)$`——`w` 工作论文 + `t` 技术
工作论文（均 type=report）；非此形态（少量 book chapter / 非 nber 中缀）→ None（调用方
不产全文计划，非异常）。全文路径 Phase 5 先限 `w`（`t` 路径未勘察实证，nber.md §9 N-2）。
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date
from xml.etree import ElementTree as ET

from paper_crawler.errors import CrawlerError, ErrorClass

# NBER DOI 前缀（Crossref 枚举键，nber.md §2）。series 后缀 = `w`(working) / `t`(technical)。
_DOI_PREFIX = "10.3386"
# 大小写不敏感匹配 `10.3386/w{n}` 或 `10.3386/t{n}`；捕获 series 号（归一小写）。
_SERIES_RE = re.compile(rf"^{re.escape(_DOI_PREFIX)}/([wt]\d+)$", re.IGNORECASE)
# RSS guid `…/papers/w{n}` 反解（nber.md §3.4）：路径尾段取 series 号。
_GUID_SERIES_RE = re.compile(r"/papers/([wt]\d+)\b", re.IGNORECASE)

# 全文 PDF 直链模板（nber.md §3.2；确定性构造，免抓 landing）。sid = w/t 号。
_FULLTEXT_BASE = "https://www.nber.org"
_PDF_PATH_TMPL = "/system/files/working_papers/{sid}/{sid}.pdf"

# 软门 HTML 嗅探：首字节形似 HTML → 命中软门（登录/付费页），非 PDF（nber.md §3.3）。
_HTML_HEAD = 64

# pub_date 精度：'YYYY' / 'YYYY-MM' / 'YYYY-MM-DD'（Crossref partial 日期，crossref/parse.py）。
_DATE_RE = re.compile(r"^(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?")


# --- series 号抽取 ----------------------------------------------------------------------------


def series_id_from_doi(doi: str) -> str | None:
    """`10.3386/w{n}` / `10.3386/t{n}` → 归一小写 series 号 `w{n}`/`t{n}`；非此形态 → None。

    非 nber 前缀、book chapter（无 w/t series 后缀）、畸形 DOI → None（调用方按"无全文
    计划"处置 + DEBUG 观测，非异常，nber.md §3.2 步 1）。
    """
    match = _SERIES_RE.match(doi.strip())
    return match.group(1).lower() if match else None


def series_letter(series_id: str) -> str:
    """series 号首字母（`w`/`t`）——resolve 侧全文范围判定用（Phase 5 先限 `w`，N-2）。"""
    return series_id[:1].lower()


def pdf_url(series_id: str) -> str:
    """全文 PDF 直链（确定性构造，nber.md §3.2）：`{base}/system/files/working_papers/{sid}/{sid}.pdf`。"""
    return f"{_FULLTEXT_BASE}{_PDF_PATH_TMPL.format(sid=series_id)}"


# --- 18 月开放窗谓词（红线核心，nber.md §3.2）------------------------------------------------


def parse_pub_date(pub_date: str) -> date | None:
    """Crossref partial 日期串 → `date`（取该精度**首日**：YYYY→01-01 / YYYY-MM→当月 1 日）。

    畸形/月日越界 → None（调用方按"缺失"保守处置）。首日口径使"已过月数"取上界——偏向
    判"开放"，命中软门由 fetch `%PDF` 守卫兜底（§3.2 步 2，红线不触）。
    """
    match = _DATE_RE.match(pub_date.strip())
    if match is None:
        return None
    year = int(match.group(1))
    month = int(match.group(2)) if match.group(2) else 1
    day = int(match.group(3)) if match.group(3) else 1
    try:
        return date(year, month, day)
    except ValueError:
        return None  # 月/日越界（如 2024-13 / 2024-02-30）


def _add_months(base: date, months: int) -> date:
    """`base` 加 `months` 个月（日超出目标月末则钳到月末，如 1-31 + 1 月 → 2-28/29）。"""
    total = (base.year * 12 + (base.month - 1)) + months
    year, month = divmod(total, 12)
    month += 1
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(base.day, last_day))


def is_open_after_window(pub_date: str | None, *, window_months: int, today: date) -> bool:
    """18 月开放窗离线谓词：`open := pub_date + window_months ≤ today`（nber.md §3.2 步 2）。

    - `pub_date` 缺失（None）或畸形不可解析 → **保守判开放** True（§3.2 步 2：交 fetch
      `%PDF` 魔数守卫兜底；单次善意请求命中软门即 no_entitlement 退避，红线不触）。
    - 否则按加月比较：满 `window_months` 月（含边界当日）→ 开放；未满 → 软门（<窗）。

    `today` 由调用方注入（adapter 传 `date.today()`；单测传假时钟精确断言跨边界 open/gated）。
    """
    if pub_date is None:
        return True
    parsed = parse_pub_date(pub_date)
    if parsed is None:
        return True  # 畸形日期按缺失保守处置（同 None 分支）
    return _add_months(parsed, window_months) <= today


# --- 软门 HTML 嗅探（nber.md §3.3）-----------------------------------------------------------


def looks_like_html(head: bytes) -> bool:
    """首字节形似 HTML（`<!doctype html` / `<html`）——软门登录/付费页判据（非 PDF）。

    与 neurips/arxiv `_looks_like_html` 同款轻嗅（首 64 字节小写比对）；调用方在 fetch
    守卫里用它把"200 却回 HTML 软门"归 `no_entitlement`（非 integrity，nber.md §3.3）。
    """
    low = head[:_HTML_HEAD].lstrip().lower()
    return low.startswith(b"<!doctype html") or low.startswith(b"<html") or b"<html" in low


# --- RSS 增量 watch 通道（nber.md §3.4；Phase 5 通道设计，Phase 6 订阅转主）-------------------


@dataclass(frozen=True)
class RssItem:
    """一条 `back.nber.org/rss/new.xml` `<item>` 解析结果（周更新论文 stub）。"""

    doi: str  # 由 guid 反解（`10.3386/w{n}`）
    series_id: str  # `w{n}`/`t{n}`
    title: str  # `<title>`（含 `-- by <作者>` 尾巴，原样保留）
    abstract: str | None  # `<description>`（完整摘要——OpenAlex 超预算时的降级源，§3.4）


def doi_from_guid(guid: str) -> str | None:
    """RSS `<guid>`（`…/papers/w{n}`）→ DOI `10.3386/w{n}`；无 series 段 → None。"""
    match = _GUID_SERIES_RE.search(guid.strip())
    if match is None:
        return None
    return f"{_DOI_PREFIX}/{match.group(1).lower()}"


def parse_rss_items(data: bytes) -> tuple[RssItem, ...]:
    """`new.xml`（或 program `new{code}.xml`）→ `RssItem` 元组（周新论文，nber.md §3.4）。

    逐 `<item>` 取 `title`/`description`/`guid`——guid 反解 DOI；无 guid series 段
    （反解失败）→ 跳过该 item（无稳定身份不产 stub，同 crossref「无 DOI 跳过」口径）。
    畸形 XML → `PARSE`（响亮停机）。**定位**：新鲜度/watch 通道，**非全量枚举**（全量恒走
    §3.1 crossref prefix）；须在 `back.nber.org` 独立桶下发（≥10s，§4，NberAdapter.BACK_RATE_POLICY）。
    """
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise CrawlerError(ErrorClass.PARSE, f"nber RSS is not valid XML: {exc}") from exc

    items: list[RssItem] = []
    for item in root.iter("item"):
        guid = _child_text(item, "guid")
        if guid is None:
            continue
        doi = doi_from_guid(guid)
        if doi is None:
            continue  # guid 无 /papers/w{n} 段 → 无稳定身份，跳过
        series_id = doi.split("/", 1)[1]
        title = _child_text(item, "title") or ""
        abstract = _child_text(item, "description")
        items.append(RssItem(doi=doi, series_id=series_id, title=title, abstract=abstract))
    return tuple(items)


def _child_text(item: ET.Element, tag: str) -> str | None:
    """取 `<item>` 直属子元素文本（空白规整化）；缺失/空白 → None。"""
    child = item.find(tag)
    if child is None or child.text is None:
        return None
    text = child.text.strip()
    return text or None


__all__ = [
    "RssItem",
    "doi_from_guid",
    "is_open_after_window",
    "looks_like_html",
    "parse_pub_date",
    "parse_rss_items",
    "pdf_url",
    "series_id_from_doi",
    "series_letter",
]
