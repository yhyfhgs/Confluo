"""NBER program RSS watch 增量通道（design/adapters/nber.md §3.4；Phase 6 T7 转主）。

**定位（不变）**：backfill/全量枚举**恒走** crossref 前缀枚举（`adapter.py`/`parse.py`
既有 `resolve_assets`/`fetch_asset` 主干，D-005，本模块零改动）——本模块只服务**watch
增量**：把 `back.nber.org/rss/new{code}.xml` 的 19 个官方 program 分 feed 之一拉取、
解析为可入库的条目流，供 Phase 6 `subs/watch.py`（T5，尚未落地）编排消费。

## program → feed 映射表：证据分级（**只收录有证据的 program**，不臆造缺口）

NBER 官方共有 **19 个 program**（[DOC]，[research/site-survey/nber.md](
../../../../docs/research/site-survey/nber.md) §2 转引旧稿 `econ-fin-preprints.md`，
本项目未逐一复验）。本模块 `PROGRAM_FEEDS` 只收录**本项目文档给出确切代码 + 语义**的
5 个（`docs/catalog/preprint-platforms.md` §4 "本项目相关 program 代码 [VERIFIED]"）：

| 代码 | 名称 | feed URL 证据 |
|---|---|---|
| `AP` | Asset Pricing | 命名模式外推（见下） |
| `CF` | Corporate Finance | **[LIVE] 2026-07-24** `newcf.xml` 实测 200/3-item |
| `EFG` | Economic Fluctuations & Growth | 命名模式外推 |
| `IFM` | International Finance & Macroeconomics | 命名模式外推 |
| `ME` | Monetary Economics | 命名模式外推 |

（`CF` 的 [LIVE] 证据出处：site-survey §2 / 请求清单 #13。）

"命名模式外推"指：`new{code_lower}.xml` 的 URL 构造规律本身已被 `newcf` 一例 [LIVE]
证实成立（site-survey §2：program 分 feed 与全量 feed 同构、"命名规律与主 feed 一致"），
故对已 [VERIFIED] 代码的其余 4 个套用同一模式是有依据的外推，而非无凭空臆造——但**未
对 newap/newefg/newifm/newme 逐一发过 HTTP 请求**，如需坐实须补一轮在线冒烟（不在本卡
预算内，[Phase 6 计划](../../../../docs/plan/phase6-implementation-plan.md) §3 未列该行）。

**明确排除**：官方 `PE` 代码因两义未核验（Public Economics / Political Economy，
catalog §4 "⚠ PE 缩写存两义...未核验，实现期以官网筛选器确认"）被排除——本卡未获在线
核验预算，排除优于猜测；其余 ~13 个 program 本项目文档从未点名给出代码，同样排除而非
按"newXX"通用模式硬猜（猜错代码会静默产出 404/空 feed，看似"能跑"实为悄悄失效，违反
"响亮失败优于静默降级"的项目纪律）。**故本表 5/19**——如需扩展，先补勘察证据，不改此表。

## RSS → PaperStub 字段映射：尽力而为（RSS 字段本身单薄）

- `title`/`authors`：RSS `<title>` 惯例含 `<正题> -- by <作者串>` 尾巴（`parse.RssItem`
  原样保留整串；本模块**额外**拆出干净标题 + 结构化作者元组，供 daily-report
  "标题/作者" 分列渲染，design/09 §6.3）。拆分为启发式（逗号 + 末段 "and"-连接兜底），
  非红线逻辑，不含尾巴时优雅退化（`authors=()`，标题原样）。
- `abstract`：`<description>`，同 `parse.RssItem`。
- `identifiers`：`(("doi", <反解 DOI>),)`——`parse.parse_rss_items`/`doi_from_guid` 已
  保证：guid 无法反解出 series 号的 item 在源头就被跳过，故本模块产出的每个条目恒有
  DOI，不存在"该造 wp 号 identifier"的分支（读 `parse.py` 现有逻辑核实：不可反解 →
  跳过而非产出 doi=None 的条目）。identifier scheme/形态与既有 `NberAdapter._doi_of`
  的读取口径（`scheme == "doi"`）完全对齐。
- `pub_date`：**尽力而为、非权威**——RSS `<pubDate>`（RFC 2822）在 [site-survey §3 字段
  可得性表](../../../../docs/research/site-survey/nber.md) 中"发表日期"一列标 ❌
  （未被判定为可靠 pub_date 源）。本模块仍在**尽力而为**原则下解析该字段（存在即用、
  解析失败或缺失即 `None`，不 raise），供日报展示用的粗粒度参考；**18 月开放窗判定
  与本字段完全解耦**——`NberAdapter.resolve_assets` 恒读 crossref 枚举产出的 `pub_date`
  （见 `adapter.py`），本模块的 watch 条目从不进入 resolve 路径的红线判定。
- `url`：RSS `<guid>` 在勘察中确认等价 landing 链（`www.nber.org/papers/w{n}`），本模块
  按既有 `parse.pdf_url` 的"确定性构造"惯例直接拼 landing URL（免二次抓取/免依赖
  item 是否带 `<link>` 子元素——既有 fixture `01_rss_new_truncated.xml` 即无该子元素）。

## watch-only 定位与 T4/T5 接缝（本卡范围边界）

- 本模块**不做**任何限速/路由决策——`discover_incremental` 只管"给定已归一 program
  代码列表 + 调用方装配好的 `HttpClient` → 逐 feed 一次请求 → 解析条目流"。`back.nber.org`
  桶的**注册**（`NberAdapter.BACK_RATE_POLICY`/`BACK_HOST`，★接缝 N-3）与限速闸的实际
  生效（`HttpClient._rate_limiter.acquire`）由调用方装配（T5 watch runner，遵循
  `stages.py` `_fetch_oa_direct` 的"域出现即 register 保守桶"先例）——本模块只需保证
  它请求的 URL host 恒为 `back.nber.org`，绝不触达 `api.crossref.org`（路由专测断言点）。
- **id 集合差分**（design/09 §5 nber 增量语义）：`subs/watermark.py`（T4 的 `IdSetDiff`
  策略）在 main 尚未落地（Phase 6 T4 卡待合并）——本模块自带独立、最小的 `ids_of`/
  `new_entries` 两个纯函数桥接同一语义（"给一组已见 id，滤出未见过的条目"），T5/T4
  落地后可整体替换为该模块的正式策略对象，接口形状保持一致（`NberWatchEntry.diff_id`
  取 `series_id`——同 program 内天然唯一、无需每次重新反解 DOI）。
- **跨 program 重复**：同一篇论文理论上可能被 NBER 编入多个 program（因而出现在多个
  订阅的 program 列表对应 feed 里）——`discover_incremental` 按 program 逐一拉取，
  重复条目由调用方的 `new_entries`/`dedupe_against_library`（T3）在更上层收敛，本模块
  不做跨 feed 去重（保持"一 feed 一请求"语义纯粹，去重是消费侧关注点）。
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from re import IGNORECASE
from re import compile as re_compile
from xml.etree import ElementTree as ET

from paper_crawler.adapters.nber import parse
from paper_crawler.adapters.nber.adapter import BACK_HOST
from paper_crawler.errors import CrawlerError, ErrorClass
from paper_crawler.http import HttpClient
from paper_crawler.types import PaperStub

# --- program → feed 映射表（模块 docstring "证据分级" 段为规范出处）--------------------------

_BACK_BASE = f"https://{BACK_HOST}"
_FEED_PATH_TMPL = "/rss/new{code}.xml"

#: program 代码（大写）→ feed 完整 URL。**只收录有证据的 5 个**（模块 docstring 表），
#: 不按 NBER 官方声称的 19 个硬造满——键集与 `SUPPORTED_PROGRAMS` 各自独立声明，
#: 由 contract 测试断言集合相等（防两处清单静默漂移，同 F5 canary 反模式治理口径）。
PROGRAM_FEEDS: Mapping[str, str] = {
    "AP": _BACK_BASE + _FEED_PATH_TMPL.format(code="ap"),
    "CF": _BACK_BASE + _FEED_PATH_TMPL.format(code="cf"),
    "EFG": _BACK_BASE + _FEED_PATH_TMPL.format(code="efg"),
    "IFM": _BACK_BASE + _FEED_PATH_TMPL.format(code="ifm"),
    "ME": _BACK_BASE + _FEED_PATH_TMPL.format(code="me"),
}

#: 已声明支持的 program 集合——独立字面量（**不是** `frozenset(PROGRAM_FEEDS)` 派生），
#: 故与 `PROGRAM_FEEDS` 的键集是两处独立维护的清单；contract 测试断言二者集合相等。
SUPPORTED_PROGRAMS: frozenset[str] = frozenset({"AP", "CF", "EFG", "IFM", "ME"})

# 论文 landing 页模板（确定性构造，同 `parse.pdf_url` 惯例；供"链接"字段与 meta 携带）。
_LANDING_TMPL = "https://www.nber.org/papers/{sid}"

# 标题 "-- by <作者串>" 尾巴（同 `parse.py` 观测到的 RSS 惯例；大小写不敏感容错）。
_AUTHOR_TAIL_RE = re_compile(r"^(?P<title>.*?)\s*--\s*by\s+(?P<authors>.+)$", IGNORECASE)
# 拆分后单个作者段开头残留的 "and " （Oxford 逗号写法 "A, B, and C" 的收尾清理）。
_LEADING_AND_RE = re_compile(r"^and\s+", IGNORECASE)


def normalize_program(code: str) -> str:
    """program 代码大小写/空白归一（T2 的 `PlanStep.pushdown` 逐字保留用户输入，
    归一职责在此——design/09 检查单 #3 接缝）。

    去首尾空白后转大写；不在 `PROGRAM_FEEDS` 内 → `CrawlerError(CONFIG)`（响亮拒载，
    同 `subs/model.py` "未知源即报错"纪律——不静默跳过一个拼错/未收录的 program 代码，
    否则用户会收到一份"看起来正常但少了一整个 program"的日报）。
    """
    normalized = code.strip().upper()
    if normalized not in PROGRAM_FEEDS:
        raise CrawlerError(
            ErrorClass.CONFIG,
            f"nber rss: unknown program code {code!r} (normalized {normalized!r}); "
            f"supported: {', '.join(sorted(PROGRAM_FEEDS))}",
        )
    return normalized


def feed_url(program: str) -> str:
    """program 代码（任意大小写/空白）→ feed URL；未知代码同 `normalize_program` 一样 CONFIG。"""
    return PROGRAM_FEEDS[normalize_program(program)]


@dataclass(frozen=True)
class NberWatchEntry:
    """一条 program RSS watch 增量条目（字段级映射产物，模块 docstring "字段映射"段）。"""

    program: str  # 归一后的大写代码（如 "AP"）——daily-report 分类展示来源
    doi: str
    series_id: str
    title: str  # 已剥离 "-- by ..." 尾巴的干净标题
    authors: tuple[str, ...]
    abstract: str | None
    url: str  # landing 页（确定性构造）
    pub_date: str | None  # 尽力而为、非权威（模块 docstring "pub_date" 段）

    @property
    def diff_id(self) -> str:
        """id 集合差分用稳定 id（T4/T5 接缝，模块 docstring 末段）。"""
        return self.series_id

    def to_paper_stub(self) -> PaperStub:
        """→ `PaperStub`（T5 摄入所需形态；program/series_id/url 搭 `meta` 顺风车）。

        `meta` 弹性字段（`types.PaperStub` 既有设计意图：携带 adapter 私有定位符）——
        `program` 供日报 `ReportEntry.categories`（"NBER program"）取用，无需 T5 反查。
        """
        return PaperStub(
            title=self.title,
            identifiers=(("doi", self.doi),),
            pub_date=self.pub_date,
            abstract=self.abstract,
            authors=self.authors,
            meta=(
                ("program", self.program),
                ("series_id", self.series_id),
                ("url", self.url),
            ),
        )


def _split_title_authors(raw_title: str) -> tuple[str, tuple[str, ...]]:
    """`<title>` → (干净标题, 作者元组)；无 "-- by" 尾巴 → (原标题, ())。"""
    match = _AUTHOR_TAIL_RE.match(raw_title)
    if match is None:
        return raw_title.strip(), ()
    return match.group("title").strip(), _split_authors(match.group("authors").strip())


def _split_authors(blob: str) -> tuple[str, ...]:
    """作者串拆分（逗号为主；末段无逗号的 "X and Y" 收尾 + Oxford 逗号 "and " 前缀清理）。

    启发式、非红线逻辑——覆盖 fixture 观测到的写法（"A, B" / "A and B" / "A, B, and C"），
    不追求穷尽所有可能的自然语言列表书写。
    """
    parts = [p.strip() for p in blob.split(",")]
    if parts and " and " in parts[-1].lower():
        tail = parts.pop()
        idx = tail.lower().rfind(" and ")
        parts.append(tail[:idx].strip())
        parts.append(tail[idx + len(" and ") :].strip())
    cleaned = (_LEADING_AND_RE.sub("", p).strip() for p in parts)
    return tuple(p for p in cleaned if p)


def _parse_pub_date(raw: str | None) -> str | None:
    """RSS `<pubDate>`（RFC 2822）→ ISO `YYYY-MM-DD`；缺失/不可解析 → `None`（不 raise）。

    尽力而为、非权威字段——模块 docstring "pub_date" 段；复用 `email.utils.
    parsedate_to_datetime`（`http.py` 解析 `Retry-After` HTTP-date 分支已用的同一
    标准库工具，行为一致，无需自定义 strptime 格式表）。
    """
    if raw is None:
        return None
    try:
        parsed = parsedate_to_datetime(raw.strip())
    except (TypeError, ValueError):
        return None
    return parsed.date().isoformat()


def _child_text(item: ET.Element, tag: str) -> str | None:
    """取 `<item>` 直属子元素文本（空白规整化）；缺失/空白 → `None`（同 `parse._child_text`）。"""
    child = item.find(tag)
    if child is None or child.text is None:
        return None
    text = child.text.strip()
    return text or None


def _parse_feed_entries(data: bytes, *, program: str) -> tuple[NberWatchEntry, ...]:
    """单 feed 原始字节 → `NberWatchEntry` 元组（program 已归一，由调用方传入）。

    **独立于** `parse.parse_rss_items`（而非直接调用）：本函数需要在同一遍解析里
    额外取 `pubDate` + 拆作者尾巴，两者都不在 `parse.RssItem` 的既有字段面里；guid→DOI
    反解复用 `parse.doi_from_guid`（红线核心正则单一出处，不复制），跳过语义（无 guid /
    guid 无 series 段 → 跳过该 item，无稳定身份不产条目）与畸形 XML→`PARSE` 的红线口径
    与 `parse.parse_rss_items` 完全一致。
    """
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise CrawlerError(ErrorClass.PARSE, f"nber program RSS is not valid XML: {exc}") from exc

    entries: list[NberWatchEntry] = []
    for item in root.iter("item"):
        guid = _child_text(item, "guid")
        if guid is None:
            continue
        doi = parse.doi_from_guid(guid)
        if doi is None:
            continue  # guid 无 /papers/w{n} 段 → 无稳定身份，跳过（同 parse.py 口径）
        series_id = doi.split("/", 1)[1]
        title, authors = _split_title_authors(_child_text(item, "title") or "")
        entries.append(
            NberWatchEntry(
                program=program,
                doi=doi,
                series_id=series_id,
                title=title,
                authors=authors,
                abstract=_child_text(item, "description"),
                url=_LANDING_TMPL.format(sid=series_id),
                pub_date=_parse_pub_date(_child_text(item, "pubDate")),
            )
        )
    return tuple(entries)


def discover_incremental(programs: Iterable[str], client: HttpClient) -> Iterator[NberWatchEntry]:
    """按 program 逐 feed 拉取（严格一 feed 一请求）→ `NberWatchEntry` 流（watch 增量主通道）。

    duck-typed，供 T5 watch runner 消费（design/09 检查单 #3；本卡不实现 runner 本身）。

    - **全量校验先行**：`programs` 在函数体最顶端一次性归一/校验完（列表推导先于任何
      HTTP 请求求值）——即便本函数是生成器，Python 生成器函数体在**首次** `next()` 时
      从头执行到第一个 `yield`，故校验语句会在任何请求发出前跑完；若某个 program 代码
      未知，调用方在开始消费前就会立即收到 `CrawlerError(CONFIG)`，**零部分请求副作用**
      （不会出现"前两个 program 已发请求、第三个才发现拼错"的半截状态）。
    - **每 feed 一次请求语义**：不分页、不重试凑数据——RSS 天然是单次快照，多请求同一
      feed 是调用方（T5）的重复调度决定，不在本函数职责内。
    - **域路由**：请求 URL 恒以 `PROGRAM_FEEDS` 的 `back.nber.org` 基址构造，从不触达
      `api.crossref.org`（enumerate/backfill 主干专属域，本函数完全不涉及）——路由
      专测断言点。限速闸生效与否取决于 `client` 装配时是否注入了已注册 `back.nber.org`
      桶的 `RateLimiter`（模块 docstring "watch-only 定位"段）；未注入时 `HttpClient`
      对无 limiter 的请求是无操作直通（`http.py` 既有语义），单测无需装配限速器。
    """
    codes = [normalize_program(code) for code in programs]
    for code in codes:
        data = client.get_bytes(PROGRAM_FEEDS[code])
        yield from _parse_feed_entries(data, program=code)


def ids_of(entries: Iterable[NberWatchEntry]) -> frozenset[str]:
    """本批 entries 的 id 集合（`diff_id`）——供调用方推进 watermark：`seen | ids_of(...)`。"""
    return frozenset(entry.diff_id for entry in entries)


def new_entries(
    entries: Iterable[NberWatchEntry], *, seen_ids: Iterable[str]
) -> tuple[NberWatchEntry, ...]:
    """id 集合差分：从 `entries` 中挑出 `diff_id` 不在 `seen_ids` 里的（增量新增）。

    独立轻量桥接——`subs/watermark.py`（T4 的 `IdSetDiff` 正式策略）在 main 尚未落地
    时的占位实现；接口形状（"一组已见 id → 过滤新增"）与该模块落地后的正式策略一致，
    T5 接线时可整体替换调用点，本函数签名不构成额外耦合面。
    """
    seen = frozenset(seen_ids)
    return tuple(entry for entry in entries if entry.diff_id not in seen)


__all__ = [
    "PROGRAM_FEEDS",
    "SUPPORTED_PROGRAMS",
    "NberWatchEntry",
    "discover_incremental",
    "feed_url",
    "ids_of",
    "new_entries",
    "normalize_program",
]
