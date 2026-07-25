"""NBER program RSS watch 增量通道（design/adapters/nber.md §3.4；Phase 6 T7 转主）。

**定位（不变）**：backfill/全量枚举**恒走** crossref 前缀枚举（`adapter.py`/`parse.py`
既有 `resolve_assets`/`fetch_asset` 主干，D-005，本模块零改动）——本模块只服务**watch
增量**：把 `back.nber.org/rss/new{code}.xml` 的 19 个官方 program 分 feed 之一拉取、
解析为可入库的条目流，供 Phase 6 `subs/watch.py`（T5，尚未落地）编排消费。

## program → feed 映射表：证据分级（**只收录有证据的 program**，不臆造缺口）

NBER 官方共有 **19 个 program**（[DOC]，[research/site-survey/nber.md](
../../../../docs/research/site-survey/nber.md) §2 转引旧稿 `econ-fin-preprints.md`，
未逐一复验）。本模块 `PROGRAM_FEEDS` 只收录**本项目文档给出确切代码 + 语义**、且已逐一
在线坐实的 5 个（`docs/catalog/preprint-platforms.md` §4 "本项目相关 program 代码
[VERIFIED]"）：

| 代码 | 名称 | feed URL 证据 |
|---|---|---|
| `AP` | Asset Pricing | **[LIVE] 2026-07-26** `newap.xml` 实测 200/4-item |
| `CF` | Corporate Finance | **[LIVE] 2026-07-24** `newcf.xml` 实测 200/3-item（原勘察） |
| `EFG` | Economic Fluctuations & Growth | **[LIVE] 2026-07-26** `newefg.xml` 实测 200/5-item |
| `IFM` | Intl Finance & Macroeconomics | **[LIVE] 2026-07-26** `newifm.xml` 实测 200/2-item |
| `ME` | Monetary Economics | **[LIVE] 2026-07-26** `newme.xml` 实测 200/2-item |

**5/5 全部 [LIVE] 实证**（2026-07-26 补测 `newap`/`newefg`/`newifm`/`newme` 四条，
`newcf` 沿用 2026-07-24 原勘察；controller 批准动用 phase6 计划 §3 机动预算余量
4 请求，`Crawl-delay:10` 逐条遵守）——四条补测额外证实：① 真实 `<item>` **无**
`<pubDate>` 子元素（与 site-survey §3 字段表"发表日期 RSS ❌"结论一致，非本模块
臆断，见下文 `pub_date` 段）；② `<guid>` 真实形态带 `#fromrss` 片段
（`https://www.nber.org/papers/w{n}#fromrss`），`parse.doi_from_guid` 的 `\\b`
词边界正则已正确处理该片段（解析 13/13 真实条目零失败，含作者名含连字符/变音符号
的边界情形）；③ 同一论文可被编入多个 program（如 `w35483`/`w35504` 同时现身
`newefg.xml` 与 `newme.xml`），印证下方"跨 program 重复"段的设计预期。

**明确排除**：官方 `PE` 代码因两义未核验（Public Economics / Political Economy，
catalog §4 "⚠ PE 缩写存两义...未核验，实现期以官网筛选器确认"）被排除——未获在线
核验该代码本身含义的预算，排除优于猜测；其余 ~14 个 program 本项目文档从未点名给出
代码，同样排除而非按"newXX"通用模式硬猜（猜错代码会静默产出 404/空 feed，看似"能跑"
实为悄悄失效，违反"响亮失败优于静默降级"的项目纪律）。**最终口径**：有据可查（含义
+ 代码双确认）的 program **全部**实证收录（5/5），其余 14 个官方 program 无码不猜。
如需扩展先补勘察证据（含 `PE` 语义核验），不改此表猜测。

## RSS → PaperStub 字段映射：尽力而为（RSS 字段本身单薄）

- `title`/`authors`：RSS `<title>` 惯例含 `<正题> -- by <作者串>` 尾巴（`parse.RssItem`
  原样保留整串；本模块**额外**拆出干净标题 + 结构化作者元组，供 daily-report
  "标题/作者" 分列渲染，design/09 §6 第 3 条）。拆分为启发式（**贪婪**匹配取**最后一个**
  `-- by` 为作者分隔——标题本身含该短语时不误切，如 "The Trade-off -- by Design ...
  -- by Alice Adams" 须切在末段；逗号为主 + 末段 "and"-连接兜底），非红线逻辑，
  不含尾巴时优雅退化（`authors=()`，标题原样）。
- `abstract`：`<description>`，同 `parse.RssItem`。
- `identifiers`：`(("doi", <反解 DOI>),)`——`parse.parse_rss_items`/`doi_from_guid` 已
  保证：guid 无法反解出 series 号的 item 在源头就被跳过，故本模块产出的每个条目恒有
  DOI，不存在"该造 wp 号 identifier"的分支（读 `parse.py` 现有逻辑核实：不可反解 →
  跳过而非产出 doi=None 的条目）。identifier scheme/形态与既有 `NberAdapter._doi_of`
  的读取口径（`scheme == "doi"`）完全对齐。
- `pub_date`：**尽力而为、非权威**——RSS `<pubDate>`（RFC 2822）在 [site-survey §3 字段
  可得性表](../../../../docs/research/site-survey/nber.md) 中"发表日期"一列标 ❌
  （未被判定为可靠 pub_date 源）；2026-07-26 在线补测的 4 个真实 feed **零个**
  `<item>` 带 `<pubDate>`，与该结论一致（旧 Phase 5 fixture 里出现的 `<pubDate>`
  只是合成样例，非真实字段常态）。本模块仍在**尽力而为**原则下解析该字段（存在即用、
  解析失败或缺失即 `None`，不 raise）。**18 月开放窗判定与本字段完全解耦**——
  `NberAdapter.resolve_assets` 恒读 crossref 枚举产出的 `pub_date`（见 `adapter.py`），
  本模块的 watch 条目从不进入 resolve 路径的红线判定。
- `year`：从 `pub_date` 派生（`_year_from_date`，逐字对齐
  `adapters/crossref/parse.py` 同名函数的先例：取前 4 位数字串）。**必须填**——
  `subs/filter.py` 的 `min_year` 判据对"已声明 `min_year` 但 `year is None`"判**不
  通过**（呼应 `ssrn.parse.topic_field_matches` 同一保守原则）；T8 仅有的两个带
  nber 的预设（`asset-pricing-wp` 的 `min_year: 2022`、`corporate-finance` 的
  `min_year: 2020`）一旦接线，若 `year` 恒 `None` 则 nber 恒零产出——表现为"本周
  没有新论文"这种不会主动报错的静默失效，比响亮失败更危险。**在线实测证实
  `pub_date` 本身常缺失**（RSS 无该字段的条目是**常态**而非例外，2026-07-26 补测
  13/13 真实条目零个带 `<pubDate>`）——若只靠 `pub_date` 派生，`year` 会在生产环境
  里近乎恒 `None`，`min_year` 预设系统性判不通过。

  **已缓解：controller 裁决方案 (c) watch 增量语境 proxy year**——`to_paper_stub`
  新增可选参数 `default_year: int | None = None`：`pub_date` 能派生年份时优先用
  该年份（**权威路径不变**）；派生不出时退回调用方传入的 `default_year`。
  `discover_incremental` 外壳按抓取时刻（UTC，`now` 参数可注入假时钟，同
  `subs/watermark.py` `now: date | None = None` 先例）算出 `fetch_year`，写在每条
  `NberWatchEntry.fetch_year` 上，供 T5 调用 `entry.to_paper_stub(default_year=
  entry.fetch_year)` 时取用。proxy 语义与边界（四条，controller 裁决原文）：

  1. **proxy 依据**：RSS watch 通道只吐"最近一批"条目（园区无翻页/无历史窗），
     抓取周即约等于该条目的发布周——proxy 误差只在**跨年周**（12 月末/1 月初的
     那一两周）才可能出现 ±1 年偏差，其余 50 周误差为 0。
  2. **proxy ≠ 编造**：这是**增量语境下的下界推断**（"这条本周从 watch 通道
     冒出来，年份大概率是今年"），目的是让 `min_year` 一类过滤器对"本周新条目"
     正确放行，不是替官方数据杜撰一个字段——`pub_date` 依旧诚实为 `None`，
     `year` 才是 proxy，且只在 `pub_date` 派生失败时才启用（显式、可关闭：调用方
     不传 `default_year` 即完全退回旧行为）。
  3. **入库后修正**：nber 的元数据主干仍是 crossref 前缀枚举（§3.1，本通道零
     改动）——同一篇论文一旦被 crossref/backfill 收录，其 `pub_date`/`year` 会按
     DOI 关联被权威值覆盖；watch 通道产的 proxy year 只是"先放行、后续被真实
     数据自然纠正"的临时值，不是永久性替代。
  4. **backfill 不受影响**：`NberAdapter.resolve_assets` 的 18 月开放窗判定
     （§3.2）与 crossref 枚举通道（§3.1）完全不经本模块，本 mitigate 只影响
     watch 增量路径产出的 `PaperStub.year`，不触碰 18 月窗红线判定或 backfill
     字段口径。
- `url`：RSS `<guid>` 在勘察中确认等价 landing 链（`www.nber.org/papers/w{n}`，
  2026-07-26 在线补测确认真实形态为 `.../papers/w{n}#fromrss`），本模块按既有
  `parse.pdf_url` 的"确定性构造"惯例直接拼干净 landing URL（免二次抓取/免依赖
  `<link>` 子元素是否存在、免保留 `#fromrss` 片段——落地页本身无该锚点语义）。

## watch-only 定位与 T4 接缝（本卡范围边界）

- 本模块**不做**任何限速/路由决策——`discover_incremental` 只管"给定已归一去重
  program 代码列表 + 调用方装配好的 `HttpClient` → 逐 feed 一次请求 → 解析条目流"。
  `back.nber.org` 桶的**注册**（`NberAdapter.BACK_RATE_POLICY`/`BACK_HOST`，
  ★接缝 N-3）与限速闸的实际生效（`HttpClient._rate_limiter.acquire`）由调用方装配
  （T5 watch runner，遵循 `stages.py` `_fetch_oa_direct` 的"域出现即 register 保守桶"
  先例）——本模块只需保证它请求的 URL host 恒为 `back.nber.org`，绝不触达
  `api.crossref.org`（路由专测断言点）。
- **id 集合差分现由 `subs/watermark.py`（T4，已落地 main）的 `IdSetDiff` 策略权威
  承接**——本模块不再自带占位差分逻辑，只留 `ids_of`：从 entries 提取**保序去重**
  的 id 序列（`entry.diff_id` = `series_id`），顺序即 feed 文档序（RSS 惯例
  新→旧）。`IdSetDiff.advance()`"截断只砍最旧"的前提正是"传入的 `seen` 是
  新→旧序"（`watermark.py` 类文档原话）——`ids_of` 的输出可直接喂给
  `IdSetDiff.new_ids(state, ids_of(entries))`（求本次真正新增的 id）与
  `IdSetDiff.advance(state, seen=ids_of(entries))`（求下一水位，注意 `advance`
  要的是**本次窗内全部**id 而非 `new_ids` 的差集——`watermark.py` 类文档已强调）。
  T5 按 `diff_id`∈`new_ids(...)` 结果过滤 entries 即可，不需要 rss.py 提供额外的
  过滤函数——避免与 T4 正式策略并存两套"什么算新"的判断面。
- **跨 program 重复**：同一篇论文确实会被 NBER 编入多个 program（2026-07-26 在线
  补测实证：`w35483`/`w35504` 同时出现在 `newefg.xml` 与 `newme.xml`）——
  `discover_incremental` 按 program 逐一拉取，重复条目由调用方的
  `dedupe_against_library`（T3）/`IdSetDiff` 差分在更上层收敛，本模块不做跨 feed
  去重（保持"一 feed 一请求"语义纯粹，去重是消费侧关注点）。
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
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

#: program 代码（大写）→ feed 完整 URL。**只收录有证据的 5 个**（模块 docstring 表，
#: 5/19 全 [LIVE] 实证），不按 NBER 官方声称的 19 个硬造满——键集与 `SUPPORTED_PROGRAMS`
#: 各自独立声明，由 contract 测试断言集合相等（防两处清单静默漂移，同 F5 canary 反模式
#: 治理口径）。
PROGRAM_FEEDS: dict[str, str] = {
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

# 标题 "-- by <作者串>" 尾巴：**贪婪** `.*`（非 `.*?`）使匹配落在**最后一个** "-- by"——
# 标题本身含该短语时（如 "... -- by Design ... -- by Alice Adams"）仍切对位置。
_AUTHOR_TAIL_RE = re_compile(r"^(?P<title>.*)\s*--\s*by\s+(?P<authors>.+)$", IGNORECASE)
# 拆分后单个作者段开头残留的 "and " （Oxford 逗号写法 "A, B, and C" 的收尾清理）。
_LEADING_AND_RE = re_compile(r"^and\s+", IGNORECASE)


def _today() -> date:
    """当前 UTC 日期（proxy year 的时钟入口）；`discover_incremental` 的 `now=` 可
    注入假时钟，同 `subs/watermark.py` 同名 `_today()` 先例，非本模块自创写法。"""
    return datetime.now(UTC).date()


def _dedupe(values: Iterable[str]) -> tuple[str, ...]:
    """保序去重（同 `subs/watermark.py` `_dedupe`/`types.CompiledPlan.all_local_predicates`
    的既有手法，非本模块自创）。"""
    seen: dict[str, None] = {}
    for value in values:
        seen.setdefault(value, None)
    return tuple(seen)


def normalize_program(code: str) -> str:
    """program 代码大小写/空白归一（T2 的 `PlanStep.pushdown` 逐字保留用户输入，
    归一职责在此——phase5-report §6 检查单 #3 接缝）。

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
    fetch_year: int  # 抓取时刻年份（UTC）——proxy year 的候选值，`discover_incremental` 注入

    @property
    def diff_id(self) -> str:
        """id 集合差分用稳定 id（喂给 `subs.watermark.IdSetDiff`，模块 docstring 末段）。"""
        return self.series_id

    def to_paper_stub(self, *, default_year: int | None = None) -> PaperStub:
        """→ `PaperStub`（T5 摄入所需形态；program/series_id/url 搭 `meta` 顺风车）。

        `year` 优先从 `pub_date` 派生（`_year_from_date`，**权威路径**）；派生不出时
        （RSS 常态缺 `<pubDate>`）退回调用方传入的 `default_year`——两者都缺才是
        `None`。`default_year` 缺省 `None`：不传参调用与旧行为完全一致（纯 `pub_date`
        派生），T5 的推荐用法是 `entry.to_paper_stub(default_year=entry.fetch_year)`
        （proxy year 语义/边界见模块 docstring "year" 段，controller 方案 (c) 裁决）。

        `meta` 弹性字段（`types.PaperStub` 既有设计意图：携带 adapter 私有定位符）——
        `program` 供日报 `ReportEntry.categories`（"NBER program"）取用，无需 T5 反查。
        """
        year = _year_from_date(self.pub_date)
        if year is None:
            year = default_year
        return PaperStub(
            title=self.title,
            identifiers=(("doi", self.doi),),
            year=year,
            pub_date=self.pub_date,
            abstract=self.abstract,
            authors=self.authors,
            meta=(
                ("program", self.program),
                ("series_id", self.series_id),
                ("url", self.url),
            ),
        )


def _year_from_date(pub_date: str | None) -> int | None:
    """`pub_date`（ISO `YYYY-...` 或 `None`）→ 年份；逐字对齐
    `adapters/crossref/parse.py` 的 `_year_from_date` 先例（取前 4 位数字串）。"""
    if pub_date is None or len(pub_date) < 4 or not pub_date[:4].isdigit():
        return None
    return int(pub_date[:4])


def _split_title_authors(raw_title: str) -> tuple[str, tuple[str, ...]]:
    """`<title>` → (干净标题, 作者元组)；无 "-- by" 尾巴 → (原标题, ())。"""
    match = _AUTHOR_TAIL_RE.match(raw_title)
    if match is None:
        return raw_title.strip(), ()
    return match.group("title").strip(), _split_authors(match.group("authors").strip())


def _split_authors(blob: str) -> tuple[str, ...]:
    """作者串拆分（逗号为主；末段无逗号的 "X and Y" 收尾 + Oxford 逗号 "and " 前缀清理）。

    启发式、非红线逻辑——覆盖 fixture 与在线补测观测到的写法（"A, B" / "A and B" /
    "A, B, and C"），不追求穷尽所有可能的自然语言列表书写。
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


def _parse_feed_entries(
    data: bytes, *, program: str, fetch_year: int
) -> tuple[NberWatchEntry, ...]:
    """单 feed 原始字节 → `NberWatchEntry` 元组（program 已归一，由调用方传入）。

    **独立于** `parse.parse_rss_items`（而非直接调用）：本函数需要在同一遍解析里
    额外取 `pubDate` + 拆作者尾巴，两者都不在 `parse.RssItem` 的既有字段面里；guid→DOI
    反解复用 `parse.doi_from_guid`（红线核心正则单一出处，不复制；2026-07-26 在线
    补测确认其 `\\b` 词边界写法对真实 `#fromrss` guid 片段解析零失败），跳过语义
    （无 guid / guid 无 series 段 → 跳过该 item，无稳定身份不产条目）与畸形 XML→
    `PARSE` 的红线口径与 `parse.parse_rss_items` 完全一致。

    `fetch_year`：调用方（`discover_incremental`）算好的抓取时刻年份，逐字写进
    每条产出的 `NberWatchEntry.fetch_year`（proxy year 候选值，模块 docstring
    "year" 段）——本函数不读时钟，纯参数传递，保持零网络/零副作用可测性。
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
                fetch_year=fetch_year,
            )
        )
    return tuple(entries)


def discover_incremental(
    programs: Iterable[str], client: HttpClient, *, now: date | None = None
) -> Iterator[NberWatchEntry]:
    """按 program 逐 feed 拉取（严格一 feed 一请求，重复代码只请求一次）→
    `NberWatchEntry` 流（watch 增量主通道）。

    duck-typed，供 T5 watch runner 消费（phase5-report §6 检查单 #3；本卡不实现 runner 本身）。

    - **本函数不是生成器**——全量归一/去重校验在**调用瞬间**同步执行完（未知 program
      立即 `raise`），返回值才是内部生成器 `_discover_incremental` 产出的惰性流。
      这与"函数体含 `yield` 即生成器、调用不执行任何代码、只在首次 `next()` 时才跑到
      第一个 `yield`"的 Python 语义特意分层：若本函数自身是生成器，T5 若走 dry-run
      之类路径**构造了返回值却从未迭代**，校验代码就永远不会执行——一个拼错的
      program 代码会在"看起来调用成功"的假象下被悄悄漏掉，直到某次真正消费时才炸，
      定位困难。拆成"立即执行的校验外壳 + 内部生成器"后，`discover_incremental(...)`
      这一行调用本身就是校验点，不依赖调用方是否消费返回值。
    - **归一化去重**：`programs` 先 `normalize_program` 逐个归一，再保序去重——
      `["CF", "cf"]` 只产生 1 次请求（同一 feed 重复拉两遍纯属浪费限速预算，
      对 `back.nber.org` 的 `Crawl-delay:10` 尤其不友好）。
    - **每 feed 一次请求语义**：不分页、不重试凑数据——RSS 天然是单次快照，多请求
      同一 feed 是调用方（T5）的重复调度决定，去重后的这份唯一 codes 列表本身
      不在本函数职责内再重复。
    - **域路由**：请求 URL 恒以 `PROGRAM_FEEDS` 的 `back.nber.org` 基址构造，从不触达
      `api.crossref.org`（enumerate/backfill 主干专属域，本函数完全不涉及）——路由
      专测断言点。限速闸生效与否取决于 `client` 装配时是否注入了已注册 `back.nber.org`
      桶的 `RateLimiter`（模块 docstring "watch-only 定位"段）；未注入时 `HttpClient`
      对无 limiter 的请求是无操作直通（`http.py` 既有语义），单测无需装配限速器。
    - **`now`：proxy year 的时钟入口**（UTC，缺省真实 `_today()`；测试可注入假时钟，
      同 `subs/watermark.py` 各策略 `now: date | None = None` 参数先例）。本次调用
      算出的 `now.year`（或 `_today().year`）写进本批**每一条**产出 entry 的
      `fetch_year`——同一次 `discover_incremental` 调用内所有条目共享同一个抓取年份
      （不逐条重新读时钟），供 T5 在 `entry.to_paper_stub(default_year=
      entry.fetch_year)` 时取用（模块 docstring "year" 段 controller 方案 (c)）。
    """
    codes = _dedupe(normalize_program(code) for code in programs)
    fetch_year = (now if now is not None else _today()).year
    return _discover_incremental(codes, client, fetch_year=fetch_year)


def _discover_incremental(
    codes: Sequence[str], client: HttpClient, *, fetch_year: int
) -> Iterator[NberWatchEntry]:
    """`discover_incremental` 的内部生成器实现；`codes` 已归一去重校验完毕。"""
    for code in codes:
        data = client.get_bytes(PROGRAM_FEEDS[code])
        yield from _parse_feed_entries(data, program=code, fetch_year=fetch_year)


def ids_of(entries: Iterable[NberWatchEntry]) -> tuple[str, ...]:
    """本批 entries 的 id 序列（保序去重，feed 文档序即新→旧）。

    供调用方喂给 `subs.watermark.IdSetDiff`（T4，已落地 main）：`new_ids(state,
    ids_of(entries))` 求本次真正新增、`advance(state, seen=ids_of(entries))` 推进
    水位——`advance()` 的"截断只砍最旧"前提正是"传入的 `seen` 是新→旧序"
    （`IdSetDiff`/`IdSetState` 类文档原话），故此处顺序不是随意的，直接对应 RSS
    feed 的文档序（新条目在前，NBER 惯例）。
    """
    return _dedupe(entry.diff_id for entry in entries)


__all__ = [
    "PROGRAM_FEEDS",
    "SUPPORTED_PROGRAMS",
    "NberWatchEntry",
    "discover_incremental",
    "feed_url",
    "ids_of",
    "normalize_program",
]
