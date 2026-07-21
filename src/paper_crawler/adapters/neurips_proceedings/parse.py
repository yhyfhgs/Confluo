"""NeurIPS proceedings 站点 HTML 解析器（design/adapters/neurips-proceedings.md §3）。

零网络：输入已取回的响应 `bytes`，输出中间记录（`NeuripsPaper`）或 `PaperStub`。只用
标准库 `re`/`html`，不引入 HTML 解析库（与 pmlr/openreview 既有 adapter 同款轻量正则派）。

覆盖两个解析目标（[LIVE] 勘察 §2/§3 对应表）：

- `parse_year_page`：单年列表页（`/paper_files/paper/{year}`）——**主源**，
  `enumerate_issue` 唯一网络调用的落点。选择器（[LIVE] §3）：``ul.paper-list >
  li[data-track]`` → ``div.paper-content > a[title="paper title"]``（**链接文字**=
  标题；``title`` 属性字面值恒为字符串 "paper title"，不是论文标题）+
  ``span.paper-authors``（逗号分隔全名）+ href 中的 32-hex hash 与 ``-Abstract``/
  ``.html`` 之间的逐字后缀（``asset_suffix``，legacy 年为空串）。0 条目（HTTP 200
  但解析出空结果）无合法态——`known_through_year` 已在 discover 阶段前置排除未发布
  当年（design §3.1），故 200 响应必然对应已发布届、恒 ≥1 篇（1987 都有 90 篇）；
  因此本函数把"0 条目"直接判 `PARSE`（不同于 pmlr 需要 bib 端点消歧空卷——neurips
  无此歧义态，design §5 失败模式表）。
- `parse_proceedings_list`：首页 ``ul.proceedings-list``（**discover 不消费**——
  `discover_timeline` 是零网络程序生成，design §8-★2 已裁决否决"解析首页"路径；
  本函数只服务 T3 一致性回归：证明"程序生成 vs 解析首页"对历史年产出同一年份
  集合，为 discover 的零网络捷径提供离线可复核的证据链）。

后缀改写规则（design §3.3）——resolve 阶段零网络 URL 构造依据，均定义于本模块：
`SUFFIX_BOUNDARY_YEAR`/`era_for_year`/`infix_for_era_track`/`pdf_url`/
`supplemental_url`（Supplemental 本期不产 `AssetPlan`，构造规则仍在此记档，供未来
enrichment 复用，亦满足 T1 "Paper/Supplemental 矩阵"覆盖要求）。
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass

from paper_crawler.errors import CrawlerError, ErrorClass
from paper_crawler.types import PaperStub

# --- 常量（design §1/§3.3；identifier scheme 见 docs/design/06-data-model.md 枚举清单）---------

SCHEME = "neurips"  # identifier scheme
HASH_RE = re.compile(r"^[0-9a-f]{32}$")  # 裸小写 32-hex（§8-★1；不做 lower()/归一变换，仅形态断言）

SUFFIX_BOUNDARY_YEAR = 2022  # 首个新格式年（[LIVE] §5：单一硬边界 2021→2022）
_FIRST_NEURIPS_YEAR = 1987  # vol=0 起点（[LIVE] §2）——不变式基准，非 discover 默认值来源

# (era, track) → PDF/Supplemental infix 闭表（[LIVE] §5；T1 矩阵）。未登记组合响亮拒绝猜测。
_INFIX_TABLE: dict[tuple[str, str], str] = {
    ("legacy", "none"): "",
    ("modern", "conference"): "-Conference",
    ("modern", "datasets_and_benchmarks"): "-Datasets_and_Benchmarks",
}


def era_for_year(year: int) -> str:
    """年份 → ``'legacy'``（≤2021）/``'modern'``（≥2022）（design §3.3 单一硬边界）。"""
    return "modern" if year >= SUFFIX_BOUNDARY_YEAR else "legacy"


def volume_for_year(year: int) -> int:
    """年份 → 站点卷号（``vol = year - 1987``，[LIVE] §2 纯函数不变式）。

    仅供校验/canary/D-019 锚点交叉核对使用——**不写入** `IssueRef.volume`（design
    §3.1 裁决：volume 字段恒 `None`，openreview 先例，`--year` selector 已足够圈定）。
    """
    return year - _FIRST_NEURIPS_YEAR


def infix_for_era_track(era: str, track: str | None) -> str:
    """(era, track) → PDF/Supplemental infix；未登记组合（含 track 缺失）→ `CONFIG`。

    响亮拒绝猜测（design §3.3："modern 遇未知 track 且无捕获后缀 → config，绝不静默
    猜"）——调用方应优先使用 enumerate 逐字捕获的 `asset_suffix`，仅在其缺失时才
    落到本函数的闭表回退。
    """
    if track is None:
        raise CrawlerError(
            ErrorClass.CONFIG,
            f"cannot derive a PDF suffix for era={era!r}: no track and no captured "
            "asset_suffix to fall back on",
        )
    infix = _INFIX_TABLE.get((era, track))
    if infix is None:
        raise CrawlerError(
            ErrorClass.CONFIG,
            f"no known PDF suffix for (era={era!r}, track={track!r}); refusing to guess "
            "— supply a captured asset_suffix or extend the closed table",
        )
    return infix


def pdf_url(base: str, *, year: int, hash_: str, infix: str) -> str:
    """``{base}/paper_files/paper/{year}/file/{hash}-Paper{infix}.pdf``（[LIVE] §5）。"""
    return f"{base}/paper_files/paper/{year}/file/{hash_}-Paper{infix}.pdf"


def supplemental_url(base: str, *, year: int, hash_: str, infix: str) -> str:
    """``{base}/paper_files/paper/{year}/file/{hash}-Supplemental{infix}.pdf``（[LIVE] §5）。

    **本期不产 AssetPlan**（design §3.3："存在与否须从 Abstract 页判定"，纯构造会
    误产不存在资产）——构造规则记档供 Phase 3 enrichment 复用，本函数仅供 T1
    Paper/Supplemental 矩阵测试与文档化，resolve_assets 不调用它。
    """
    return f"{base}/paper_files/paper/{year}/file/{hash_}-Supplemental{infix}.pdf"


def validate_hash(value: str) -> str:
    """校验 `value` 形似裸小写 32-hex hash 并原样返回；非法 → `CONFIG`。

    站点解析出的 hash 由 `parse_year_page` 的正则自身要求 ``[0-9a-f]{32}`` 形态，
    天然满足；本函数供 resolve 阶段读回 `PaperStub.identifiers` 时的防御性再校验
    —— identifier 是 adapter 自己写入的内部状态，若不合法即代码/装配缺陷，`CONFIG`
    而非 `PARSE`（`PARSE` 保留给"站点响应本身解析失败"）。
    """
    if not HASH_RE.match(value):
        raise CrawlerError(
            ErrorClass.CONFIG, f"neurips identifier value is not a bare 32-hex hash: {value!r}"
        )
    return value


# --- 中间记录 ----------------------------------------------------------------------------------


@dataclass(frozen=True)
class NeuripsPaper:
    """年页一个 ``<li data-track=...>`` 条目的解析产物。

    ``track`` 是 `data-track` 属性的逐字值（``'conference'``/``'datasets_and_benchmarks'``/
    ``'none'``）；``asset_suffix`` 是 href 中 `-Abstract` 与 `.html` 之间的逐字子串
    （``''``/``'-Conference'``/``'-Datasets_and_Benchmarks'``，抗未来新 track，
    design §3.2/§3.3）。``title``/``authors`` 已规整化（去标签、解转义实体、空白折叠）
    供 healthcheck 的"规整化 title"双字段比对直接等值使用（arxiv/pmlr 同款先例）。
    """

    hash: str
    title: str
    authors: tuple[str, ...]
    track: str
    asset_suffix: str


# --- 年页（主源）------------------------------------------------------------------------------

# `<li ...data-track="...">...</li>`：属性顺序不定（真实样本 class 在前、data-track 在后），
# 用 `[^>]*` 两侧宽容匹配；`.*?` 非贪婪到最近的 `</li>`（年页条目不嵌套 li，安全，pmlr
# 同款 div-block 正则先例）。
_LI_BLOCK_RE = re.compile(
    r"<li\b[^>]*\bdata-track=\"(?P<track>[^\"]*)\"[^>]*>(?P<body>.*?)</li>",
    re.DOTALL | re.IGNORECASE,
)
# 标题链接：`<a title="paper title" href="...">`——注意 `title` **属性**字面值恒为
# "paper title"（非论文实际标题），实际标题是链接文字（[LIVE] §3）。
_TITLE_LINK_RE = re.compile(
    r'<a\s+title="paper title"\s+href="(?P<href>[^"]*)"[^>]*>(?P<text>.*?)</a>',
    re.DOTALL | re.IGNORECASE,
)
_AUTHORS_RE = re.compile(
    r'<span\s+class="paper-authors"[^>]*>(?P<text>.*?)</span>', re.DOTALL | re.IGNORECASE
)
# hash + 逐字后缀：`/hash/{32-hex}-Abstract{suffix}.html`；suffix 组可为空串。
_HASH_ABSTRACT_RE = re.compile(r"/hash/(?P<hash>[0-9a-f]{32})-Abstract(?P<suffix>.*?)\.html")


def parse_year_page(data: bytes) -> tuple[NeuripsPaper, ...]:
    """解析单年列表页，逐 ``<li data-track=...>`` 产出 `NeuripsPaper`。

    0 条目（含"完全找不到任何 `<li data-track>`"与"找到但内部字段缺失/hash 形态
    非法"）统一判 `PARSE`——neurips 已发布年恒 ≥1 篇（[LIVE] §2：1987 都有 90 篇），
    不存在"200 但合法空"的年页（design §5 失败模式表；与 pmlr 需要 bib 端点消歧的
    空卷不同，本站点无此歧义态）。
    """
    text = data.decode("utf-8", errors="replace")
    papers = tuple(_parse_li_block(track, body) for track, body in _iter_li_blocks(text))
    if not papers:
        raise CrawlerError(
            ErrorClass.PARSE,
            "neurips year page parsed to 0 papers — either the page is genuinely empty "
            "(no legitimate empty year exists post-publication) or the "
            "`ul.paper-list > li[data-track]` selector has drifted",
        )
    return papers


def _iter_li_blocks(text: str) -> list[tuple[str, str]]:
    return [(m.group("track"), m.group("body")) for m in _LI_BLOCK_RE.finditer(text)]


def _parse_li_block(track: str, body: str) -> NeuripsPaper:
    title_match = _TITLE_LINK_RE.search(body)
    if title_match is None:
        raise CrawlerError(
            ErrorClass.PARSE,
            f"neurips year page li[data-track={track!r}] missing the "
            '`<a title="paper title" href=...>` link (cannot derive hash/identifier)',
        )
    title = _clean_text(title_match.group("text"))
    if not title:
        raise CrawlerError(
            ErrorClass.PARSE, f"neurips year page li[data-track={track!r}] has an empty title"
        )

    href = title_match.group("href")
    hash_match = _HASH_ABSTRACT_RE.search(href)
    if hash_match is None:
        raise CrawlerError(
            ErrorClass.PARSE,
            f"neurips year page entry {title!r} href {href!r} does not match the expected "
            "`/hash/{32-hex}-Abstract{suffix}.html` pattern",
        )

    return NeuripsPaper(
        hash=hash_match.group("hash"),
        title=title,
        authors=_extract_authors(body),
        track=html.unescape(track),
        asset_suffix=hash_match.group("suffix"),
    )


def _extract_authors(body: str) -> tuple[str, ...]:
    match = _AUTHORS_RE.search(body)
    if match is None:
        return ()
    raw = _clean_text(match.group("text"))
    if not raw:
        return ()
    return tuple(name for part in raw.split(",") if (name := part.strip()))


def to_paper_stub(paper: NeuripsPaper, *, year: int) -> PaperStub:
    """`NeuripsPaper` → `PaperStub`（design §3.2 字段映射裁决）。

    ``identifiers`` 恒为单一 ``(('neurips', <32-hex hash>),)``（裸小写、逐字原样，
    §8-★1）。``abstract``：年页无摘要，留 `None`（薄元数据，§8-★4；逐篇详情页摘要
    属 Phase 3 enrichment）。``meta`` 恒含 `track`/`asset_suffix` 两键（resolve 的
    构造线索，§3.2/§3.3）。
    """
    return PaperStub(
        title=paper.title,
        identifiers=((SCHEME, paper.hash),),
        year=year,
        authors=paper.authors,
        meta=(("track", paper.track), ("asset_suffix", paper.asset_suffix)),
    )


# --- 首页 `ul.proceedings-list`（discover 不消费；T3 一致性回归专用，见模块 docstring）---------


_HOMEPAGE_LI_RE = re.compile(
    r'<li>\s*<a\s+href="/paper_files/paper/(?P<year>\d{4})"[^>]*>', re.IGNORECASE
)


def parse_proceedings_list(data: bytes) -> tuple[int, ...]:
    """解析首页 ``ul.proceedings-list``，按页面出现顺序产出年份元组（[LIVE] §2）。

    **discover_timeline 不调用本函数**（design §8-★2 已裁决：discover 零网络程序
    生成，首页解析路径否决）——本函数只服务测试层的一致性回归：证明"程序生成 vs
    解析首页"对历史年产出同一年份集合，为 discover 的零网络捷径提供离线可复核的
    证据链。0 条目 → `PARSE`（首页权威源结构漂移，design §5 失败模式表）。
    """
    text = data.decode("utf-8", errors="replace")
    years = tuple(int(m.group("year")) for m in _HOMEPAGE_LI_RE.finditer(text))
    if not years:
        raise CrawlerError(
            ErrorClass.PARSE,
            "neurips homepage `ul.proceedings-list` parsed to 0 years — selector drift",
        )
    return years


# --- 共享小工具 --------------------------------------------------------------------------------


def _strip_tags(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text)


def _normalize_ws(text: str) -> str:
    return " ".join(text.split())


def _clean_text(text: str) -> str:
    return _normalize_ws(html.unescape(_strip_tags(text)))


__all__ = [
    "HASH_RE",
    "SCHEME",
    "SUFFIX_BOUNDARY_YEAR",
    "NeuripsPaper",
    "era_for_year",
    "infix_for_era_track",
    "parse_proceedings_list",
    "parse_year_page",
    "pdf_url",
    "supplemental_url",
    "to_paper_stub",
    "validate_hash",
    "volume_for_year",
]
