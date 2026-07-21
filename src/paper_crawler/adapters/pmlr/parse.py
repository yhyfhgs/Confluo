"""卷 index HTML / `bibliography.bib` / 单篇 `citation_*` 详情页解析器（pmlr.md §3.2/§6.1）。

零网络：输入已取回的响应 `bytes`，输出中间记录（`PmlrPaper`/`CitationMeta`），供
T5 adapter 主体消费。三个解析目标对应 pmlr.md §2 勘察的三条结构化元数据源：

- `parse_volume_index`：卷 index 页（`v{N}/`）逐 ``<div class="paper">`` 提取——
  **主源**，常态单请求即含全部字段（title/authors/pages/slug/pdf_url/openreview）。
- `count_bib_entries`：卷 `bibliography.bib` 的 entry 计数——**仅供 0-div 歧义态
  消歧**（§3.2 判据表：HTML 0 条时靠 bib 条目数区分"合法空卷"与"解析器失效"），
  不做全字段解析（bibkey 可由 `N+slug` 直接构造，无需抓 bib）。
- `parse_citation_meta`：单篇 abs 详情页的 Google Scholar ``citation_*`` meta +
  内嵌 BibTeX key——本期**不接入**主 enumerate 路径（abstract 回填是推迟路径，
  pmlr.md §3.2"abstract：卷 index 不含…本期留 None"），仅供 bibkey 反查回归与
  未来回填路径的解析基础（test-plan §2"三件套"详情页覆盖）。

链接解析约定：卷 index 页内的 ``[abs]``/``[Download PDF]``/``[OpenReview]`` 三链
一律用 ``urljoin(SITE_ROOT, href)`` 相对**站点根**（`https://proceedings.mlr.press/`）
解析，而非相对"当前抓取页自身 URL"——站点顶层卷列表锚点确实是
`href="v235"`（无前导斜杠、相对站点根，[LIVE] 勘察与独立审查 2026-07-22 真实
抓取均证实）；若改用严格 RFC3986"相对当前页"解析会把卷内链接误拼成
`v235/v235/…`（重复段）。**测辞校准**（独立审查 2026-07-22 真实交叉验证）：
design pmlr.md §3.2 的简化示例给出的是卷内 `[abs]` href 形如
`v235/{slug}.html` 的"相对无前导斜杠"形态，但审查对真实 v235/v202/v9 三卷
页面的抓取显示，卷内 `[abs]`/`[Download PDF]`/`[OpenReview]` 三链的 href
**通常已是绝对 URL**（而非相对形态）——即卷内链接与顶层卷列表锚点的相对/
绝对形态并不一致。这不影响本模块的正确性：`urljoin(SITE_ROOT, href)` 对
绝对 href 直接原样返回、对相对 href 按站点根解析，两种输入形态殊途同归；
选用"相对站点根"而非"相对当前页"解析仍是唯一正确选择（覆盖顶层锚点场景，
且对卷内的绝对 href 无副作用）。
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urljoin, urlsplit

from paper_crawler.errors import CrawlerError, ErrorClass
from paper_crawler.types import PaperStub

# 站点根（pmlr.md §3.2 的"卷 base URL"——所有站内相对链接的解析基准，见模块 docstring）。
SITE_ROOT = "https://proceedings.mlr.press/"

# --- 中间记录 ----------------------------------------------------------------------------------


@dataclass(frozen=True)
class PmlrPaper:
    """卷 index 页一个 ``<div class="paper">`` 的解析产物。

    ``pdf_url``/``openreview_id`` 为 None 属正常态（pmlr.md §3.3："PMLR 每篇必有
    PDF；若 meta 缺 pdf_url（不应发生）→产 0 个 pdf plan（非错误）"；OpenReview
    链接并非每篇都有）。``firstpage``/``lastpage`` 解析失败同样容忍为 None——页码
    仅用于 canary 比对（§6.4），不是 identifier 构造的必需字段。
    """

    slug: str
    title: str
    authors: tuple[str, ...]
    firstpage: int | None
    lastpage: int | None
    pdf_url: str | None
    landing_url: str
    openreview_id: str | None


@dataclass(frozen=True)
class CitationMeta:
    """单篇 abs 详情页的 ``citation_*`` meta + 内嵌 BibTeX key（`parse_citation_meta` 产物）。"""

    title: str | None
    authors: tuple[str, ...]
    pdf_url: str | None
    abstract_html_url: str | None
    firstpage: int | None
    lastpage: int | None
    publication_date: str | None
    conference_title: str | None
    issn: str | None
    bibkey: str | None


# --- 卷 index HTML（主源）-----------------------------------------------------------------------

_PAPER_BLOCK_RE = re.compile(r'<div\s+class="paper"[^>]*>(.*?)</div>', re.DOTALL | re.IGNORECASE)
_TITLE_RE = re.compile(r'<p\s+class="title"[^>]*>(.*?)</p>', re.DOTALL | re.IGNORECASE)
_AUTHORS_RE = re.compile(r'<span\s+class="authors"[^>]*>(.*?)</span>', re.DOTALL | re.IGNORECASE)
_PAGES_RE = re.compile(r"PMLR\s+\d+:(\d+)-(\d+)")
_LINK_RE = re.compile(r'<a\s+href="([^"]*)"[^>]*>(.*?)</a>', re.DOTALL | re.IGNORECASE)


def parse_volume_index(data: bytes) -> tuple[PmlrPaper, ...]:
    """解析卷 index 页，逐 ``<div class="paper">`` 产出 `PmlrPaper`。

    返回空 tuple（0 条 ``<div class="paper">``）**不是**本函数抛出的错误态——
    这是唯一的歧义态（合法空卷 vs HTML 解析器失效），消歧责任在调用方（须结合
    `count_bib_entries`，pmlr.md §3.2 判据表）。找到 div 但块内缺失必需字段
    （title / ``[abs]`` 链接→slug）才是本函数判定的 `PARSE`——这类"非空却读不出
    字段"的情形本身就是解析器/结构漂移信号，不该被静默吞掉。
    """
    text = data.decode("utf-8", errors="replace")
    return tuple(_parse_paper_block(block) for block in _PAPER_BLOCK_RE.findall(text))


def _parse_paper_block(block: str) -> PmlrPaper:
    title = _first_group_text(_TITLE_RE, block)
    if not title:
        raise CrawlerError(ErrorClass.PARSE, 'pmlr paper block missing <p class="title">')

    slug, landing_url = _extract_abs(block)
    if slug is None:
        raise CrawlerError(
            ErrorClass.PARSE,
            f"pmlr paper block {title!r} missing [abs] link (cannot derive slug/identifier)",
        )

    authors = _extract_authors(block)
    firstpage, lastpage = _extract_pages(block)
    pdf_url = _extract_link_url(block, "Download PDF")
    openreview_id = _extract_openreview(block)

    return PmlrPaper(
        slug=slug,
        title=title,
        authors=authors,
        firstpage=firstpage,
        lastpage=lastpage,
        pdf_url=pdf_url,
        landing_url=landing_url,
        openreview_id=openreview_id,
    )


def _extract_abs(block: str) -> tuple[str | None, str]:
    """从 ``[abs]`` 链接取 (slug, 已解析绝对 landing_url)；找不到时 slug=None。"""
    href = _extract_link_href(block, "abs")
    if href is None:
        return None, ""
    tail = href.rsplit("/", 1)[-1]
    if not tail.endswith(".html"):
        return None, ""
    slug = tail[: -len(".html")]
    if not slug:
        return None, ""
    return slug, urljoin(SITE_ROOT, href)


def _extract_authors(block: str) -> tuple[str, ...]:
    raw = _first_group_text(_AUTHORS_RE, block)
    if not raw:
        return ()
    return tuple(name for part in raw.split(",") if (name := part.strip()))


def _extract_pages(block: str) -> tuple[int | None, int | None]:
    match = _PAGES_RE.search(block)
    if match is None:
        return None, None
    return int(match.group(1)), int(match.group(2))


def _extract_link_href(block: str, link_text: str) -> str | None:
    matches: list[tuple[str, str]] = _LINK_RE.findall(block)
    for href, text in matches:
        if _clean_text(text) == link_text:
            return href
    return None


def _extract_link_url(block: str, link_text: str) -> str | None:
    href = _extract_link_href(block, link_text)
    return urljoin(SITE_ROOT, href) if href is not None else None


def _extract_openreview(block: str) -> str | None:
    href = _extract_link_href(block, "OpenReview")
    if href is None:
        return None
    values = parse_qs(urlsplit(href).query).get("id")
    return values[0] if values else None


# --- bibliography.bib（0-div 歧义态消歧辅源）----------------------------------------------------

# 真实 PMLR `bibliography.bib` 恒以一条卷级元数据 entry 起手（独立审查 2026-07-22
# 对三份不同年代/会议的真实 bib 文件核实一致：v202/ICML2023、v238/AISTATS2024、
# v9/AISTATS2010），形如 ``@Proceedings{ICML2023, title=…, volume=202, …}``——
# 与逐篇论文的 ``@InProceedings{…}`` 用完全相同的 ``@Type{key, ...}`` 语法，
# 但不是一篇论文。计数必须只认 `@InProceedings`（大小写不敏感，BibTeX 惯例），
# 否则会把这条卷级前导 entry 也计入，使返回值恒为"论文数 + 1"而非论文数
# 本身——直接影响 §3.2 的 0-div 消歧判据（"bib==0 → 合法空卷"）。
_PAPER_ENTRY_TYPE = "inproceedings"


def count_bib_entries(data: bytes) -> int:
    """计算 ``bibliography.bib`` 中顶层 ``@InProceedings{...}``（论文）entry 的个数。

    仅供 pmlr.md §3.2 的 0-div 消歧使用（区分"合法空卷"与"HTML 解析器失效"），
    不解析条目内字段——bibkey 由 ``pmlr-v{N}-{slug}`` 直接构造，无需抓 bib
    （§3.2："bibkey 可由 N + slug 直接构造，不依赖抓 bib 文件"）。**只统计论文
    entry**（`@InProceedings`，大小写不敏感）——真实 bib 文件恒有的卷级
    ``@Proceedings{...}`` 元数据前导 entry（以及理论上可能出现的
    ``@Comment{...}``/``@String{...}`` 等非论文类型）一律不计入，见上方模块级
    常量注释。

    用括号深度扫描而非整行/整段正则：只在**深度为 0**时把 ``@word{`` 识别为新
    entry 起点——**无论 entry 类型是否被计数，都照常推进深度**（否则
    ``@Proceedings{}`` 内部的花括号会与后续真实论文 entry 的花括号错位配对），
    只是计数器只在类型匹配 `@InProceedings` 时才 +1。entry 内部任意深度的嵌套
    花括号（如 ``title = {{BERT}: ...}``）与字段值里的 ``@``（如邮箱
    ``foo@bar.com``）都不会被误判为新 entry；顶层 ``%`` 注释行（BibTeX 惯例）
    整行跳过，避免注释文本里偶然出现的 ``@`` 误计数。
    """
    text = data.decode("utf-8", errors="replace")
    count = 0
    depth = 0
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if depth == 0 and ch == "%":
            newline = text.find("\n", i)
            i = n if newline == -1 else newline + 1
            continue
        if depth == 0 and ch == "@":
            j = i + 1
            while j < n and (text[j].isalnum() or text[j] == "_"):
                j += 1
            entry_type = text[i + 1 : j]
            k = j
            while k < n and text[k].isspace():
                k += 1
            if k < n and text[k] == "{":
                if entry_type.lower() == _PAPER_ENTRY_TYPE:
                    count += 1
                depth = 1  # 无论是否计数，都要推进深度以正确跳过该 entry 的内容。
                i = k + 1
                continue
        elif ch == "{":
            if depth > 0:
                depth += 1
        elif ch == "}":
            if depth > 0:
                depth -= 1
        i += 1
    return count


# --- 单篇 abs 详情页（citation_* meta，推迟路径的解析基础）---------------------------------------

_META_RE = re.compile(
    r'<meta\s+name="(?P<name>[^"]+)"\s+content="(?P<content>[^"]*)"', re.IGNORECASE
)
_BIBKEY_RE = re.compile(r"@\w+\{\s*([^,\s}]+)\s*,")


def parse_citation_meta(data: bytes) -> CitationMeta:
    """解析单篇 abs 详情页的 Google Scholar ``citation_*`` meta + 内嵌 BibTeX key。

    本期不接入主 enumerate 路径（见模块 docstring）；供 bibkey 反查回归测试与
    未来 abstract 回填路径复用。字段全部宽松处理（缺失即 None/空 tuple），因为
    本函数不在任何 error_class 判定路径上。
    """
    text = data.decode("utf-8", errors="replace")
    tags: dict[str, list[str]] = {}
    for match in _META_RE.finditer(text):
        tags.setdefault(match.group("name"), []).append(html.unescape(match.group("content")))

    def first(name: str) -> str | None:
        values = tags.get(name)
        return values[0] if values else None

    bibkey_match = _BIBKEY_RE.search(text)
    return CitationMeta(
        title=first("citation_title"),
        authors=tuple(tags.get("citation_author", ())),
        pdf_url=first("citation_pdf_url"),
        abstract_html_url=first("citation_abstract_html_url"),
        firstpage=_int_or_none(first("citation_firstpage")),
        lastpage=_int_or_none(first("citation_lastpage")),
        publication_date=first("citation_publication_date"),
        conference_title=first("citation_conference_title"),
        issn=first("citation_issn"),
        bibkey=bibkey_match.group(1) if bibkey_match else None,
    )


# --- PaperStub 转换 ----------------------------------------------------------------------------


def to_paper_stub(paper: PmlrPaper, *, volume: str, year: int | None) -> PaperStub:
    """把 `PmlrPaper` 转成 `PaperStub`（pmlr.md §3.2 字段映射裁决逐字执行）。

    ``identifiers`` 恒为单一 ``(('pmlr', f'pmlr-v{volume}-{slug}'),)``——官方
    BibTeX entry key 全串，大小写原样保留（不做 lower()/upper() 归一）。``meta``
    仅含 pmlr.md §3.2 定死的三键（``pdf_url``/``landing_url``/``openreview``，
    前两者外加可选的第三者），**不含** pages——pages 只是 canary 比对用的中间态
    字段，留在 `PmlrPaper`，不进最小元数据锚点。``abstract`` 卷 index 不含，
    留 None（推迟路径）。
    """
    meta: list[tuple[str, str]] = []
    if paper.pdf_url:
        meta.append(("pdf_url", paper.pdf_url))
    meta.append(("landing_url", paper.landing_url))
    if paper.openreview_id:
        meta.append(("openreview", paper.openreview_id))

    return PaperStub(
        title=paper.title,
        identifiers=(("pmlr", f"pmlr-v{volume}-{paper.slug}"),),
        year=year,
        authors=paper.authors,
        meta=tuple(meta),
    )


# --- 共享小工具 --------------------------------------------------------------------------------


def _strip_tags(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text)


def _normalize_ws(text: str) -> str:
    return " ".join(text.split())


def _clean_text(text: str) -> str:
    return _normalize_ws(html.unescape(_strip_tags(text)))


def clean_text(text: str) -> str:
    """把带标签的 HTML 片段/整页转成"可见文本"：去标签 + 解转义实体 + 空白规整化。

    公开导出供 `adapter.py` 的 `healthcheck` 复用（独立审查 2026-07-22 发现：真实
    站点根页的卷锚点markup 是 ``<a href="v235"><b>Volume 235</b></a> Proceedings
    of ICML 2024``——"Volume N" 被 ``<b>`` 包裹、锚点在此提前闭合，"Proceedings
    of…" 落在锚点外的纯文本，二者之间隔着 ``</b></a> `` 标签边界而非纯空白，对
    带标签原始 HTML 直接做 ``\\s+`` 正则必然不匹配。修法是先转成可见文本（与本
    模块解析卷 index 页 title/authors 字段的既有处理方式一致）再匹配，而不是让
    正则去容忍标签插入。"""
    return _clean_text(text)


def _first_group_text(pattern: re.Pattern[str], block: str) -> str | None:
    match = pattern.search(block)
    if match is None:
        return None
    cleaned = _clean_text(match.group(1))
    return cleaned or None


def _int_or_none(text: str | None) -> int | None:
    if text is None:
        return None
    try:
        return int(text.strip())
    except ValueError:
        return None


__all__ = [
    "SITE_ROOT",
    "CitationMeta",
    "PmlrPaper",
    "clean_text",
    "count_bib_entries",
    "parse_citation_meta",
    "parse_volume_index",
    "to_paper_stub",
]
