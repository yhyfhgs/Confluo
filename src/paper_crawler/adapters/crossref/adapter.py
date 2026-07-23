"""Crossref `SourceAdapter` 主体（期刊主干；design/adapters/aggregators.md §5.1；AC-3.5 载体）。

把零网络纯逻辑（`parse`）与 T2 共享 `HttpClient` 组装成 aggregator adapter。能力口径
（§1 表）：``DISCOVER | ENUMERATE``——**无 SEARCH/RESOLVE/FETCH**（五源均无 FETCH，
plan §2-3；SEARCH 冻结协议无 `search()`，订阅命中经 enumerate + 本地过滤达成，§1）。

**两轴参数化枚举扩展**（Phase 5 T1；规范出处 nber.md §3.1，★N-1 裁决=YES）：本 adapter
升为通用参数化枚举源，消费方 = nber（prefix+published）/ ssrn（prefix+created）+ 既有全部
by-ISSN 期刊（issn+published，**零回归**）：

- **轴① enum-key（issn XOR prefix）**：venue `identifiers.issn`（期刊）**XOR**
  `identifiers.crossref_prefix`（前缀系列，nber `10.3386` / ssrn `10.2139`）→ URL 基址
  `/journals/{issn}/works` **XOR** `/prefixes/{prefix}/works`；二者都缺/都在 → CONFIG 响亮。
- **轴② date-field（published | created）**：venue `quirks.crossref_date_field`（默认
  `published`）三处联动——发现 facet `{field}:*` / 枚举 filter `from/until-{pub|created}-date`
  / 解析键 `facets.{field}`（★注：`published` 轴 filter 前缀是 `pub` 缩写、facet/解析键用
  全名 `published`；`created` 轴三处同名）。
- **零改面**：`to_paper_stub`（仍产 `(doi,)`）、cursor 深翻契约、首页空判、限速、UA、
  polite pool 逐字复用（扩展纯加性，两轴之外零改）。

阶段分工（§5.1）：

- `discover_timeline`：`/journals/{issn}/works?rows=0&facet=published:*`（1 请求）→ 按
  出版年 facet 计数产逐年 `IssueRef`（`paper_count_claimed`=该年计数）；`since` 为可选
  年份下界。Crossref 无 volume/issue filter，故时间轴粒度=出版年（volume/issue 从 works
  记录字段读入 meta，不作枚举键）。
- `enumerate_issue`：`(issn, year)` → `filter=from-pub-date,until-pub-date` 日期窗
  拉 works → PaperStub 流。**cursor 深翻断点续拉**（§5.1 契约逐字）：首请求 `cursor=*`
  → 读 `message.next-cursor` → 续拉至 `items` 空。cursor 值**不持久化、不跨任务复用**；
  中断续拉按 `(issn, year)` 窗口**重建** `cursor=*` 从头（幂等由 `(doi)` identifier
  去重天然保证，无重复入库）。
- `healthcheck`：`GET /works/{固定DOI}` → 比对**空白规整化 title[0]**（非纯计数——
  total-results 随出版增长会漂）。真值 [PENDING]（留待在线冒烟 UPDATE_GOLDEN 捕获，
  §5.1/§7）：未捕获前作结构性探测（title 非空即健康，detail 附实测 title 供捕获）。

**限速（X-Rate-Limit，§4）**：polite pool 实测 `X-Rate-Limit-Limit:10`/`Interval:1s`；
`default_rate` 取**保守上限 5 req/s**（=300 req/min，远离 10/1s）。限速经 pipeline
`acquire_and_wait` + `HttpClient` 逐请求闸（`rate_limiter` 冻结扩展点）强制，adapter
内部 cursor 翻页每页一请求也走闸、不绕过（沿 arxiv C4 先例）。**动态读响应头调节**
在冻结 `HttpClient.get_bytes`（只回 body、不暴露 headers）下不可达——退化为静态保守
上限 + 429→`rate_limited`（HttpClient 读 Retry-After 入 detail）退避（见报告 concerns）。

**UA/polite pool**：UA 须携 `mailto:`（Crossref polite pool 硬要求 → 10/1s 而非匿名档）。
经 `HttpClientConsumer` 注入携 config `[identity].email` 的共享 client（`bind_http_client`）；
未注入时惰性自建（UA email 从 env `PAPER_CRAWLER_CONTACT_EMAIL` 取，缺省 `.invalid` 占位）。

**错误映射（§5.1 表）**：429/X-Rate-Limit 触顶→`rate_limited`（读 Retry-After，HttpClient）；
4xx（filter 语法/ISSN 非法）→`config`（HttpClient）；5xx→`transient`（HttpClient）；
`total-results>0` 但首页 items 空解析 0 条→`parse`（canary 标红，本层判）。cursor 过期/
scroll 失效→Crossref 返 400→`config`（HttpClient 状态映射治理，响亮停机后人工重跑；
窗口重建从头是本层续拉契约——★裁决④ 2026-07-22，无 cursor 专属重映射）。
"""

from __future__ import annotations

import os
from collections.abc import Iterable, Iterator
from urllib.parse import urlencode

from paper_crawler.adapter import AdapterBase, AdapterFamily
from paper_crawler.adapters.crossref import parse
from paper_crawler.errors import CrawlerError, ErrorClass
from paper_crawler.http import HttpClient
from paper_crawler.obslog import log_event
from paper_crawler.types import (
    AuthLevel,
    Capability,
    HealthReport,
    IssueRef,
    PaperStub,
    RatePolicy,
    SessionHandle,
    VenueSpec,
)
from paper_crawler.useragent import build_user_agent

# --- 端点与常量（§5.1 表）---------------------------------------------------------------------

_API_ROOT = "https://api.crossref.org"
# 深翻页大小：rows≤1000（offset≤10000 浅翻不用，深翻一律 cursor）。cursor 模式下
# 每页取 rows 条 + next-cursor 续页，直至 items 空。
_ROWS = 1000

# --- date-field 轴常量（nber.md §3.1）---------------------------------------------------------
# venue.quirks.crossref_date_field 择一，默认 published。映射值 = date-field → Crossref filter
# 日期名——★published 轴 filter 前缀是 `pub` 缩写（from-pub-date），而 facet 参数 / 解析键用全名
# `published`；created 轴三处同名（from-created-date / created:* / facets.created）。
_DATE_FIELD_QUIRK = "crossref_date_field"
_DATE_FIELD_FILTER: dict[str, str] = {"published": "pub", "created": "created"}
_VALID_DATE_FIELDS = frozenset(_DATE_FIELD_FILTER)  # {"published", "created"}
_DEFAULT_DATE_FIELD = "published"

_CONTACT_EMAIL_ENV = "PAPER_CRAWLER_CONTACT_EMAIL"
# RFC 2606 保留 .invalid 顶级域——占位联系人不可能是真实地址（隐私安全），且明确信号
# 「该走配置化 client 注入真实 mailto」。仅在惰性自建且未设环境变量时使用（同 arxiv/pmlr 先例）。
# 注意：mailto 缺失会掉出 polite pool（限速更严），故真实在线务必注入配置化 client。
_PLACEHOLDER_EMAIL = "anonymous@paper-crawler.invalid"

# healthcheck 固定 DOI（稳定经典论文；LeCun/Bengio/Hinton "Deep learning", Nature 2015）。
# **[PENDING online-smoke UPDATE_GOLDEN]**：真值（规整化 title[0]）留待在线冒烟捕获后
# 替换 `_HEALTHCHECK_TITLE`（§5.1/§7 同批未决项）；捕获前 healthcheck 作结构性探测。
_HEALTHCHECK_DOI = "10.1038/nature14539"
_HEALTHCHECK_TITLE: str | None = (
    "Deep learning"  # [LIVE] 2026-07-23 双源捕获（T3 审查+T7 冒烟实跑），UPDATE_GOLDEN 纪律转正
)


def _default_user_agent() -> str:
    """惰性自建 client 的 UA：email 从环境变量取（不硬编码），缺省用 `.invalid` 占位。"""
    email = os.environ.get(_CONTACT_EMAIL_ENV, "").strip() or _PLACEHOLDER_EMAIL
    return build_user_agent(email)


# --- adapter 主体 ----------------------------------------------------------------------------


class CrossrefAdapter(AdapterBase):
    """Crossref 元数据主干 adapter（`aggregator` family；期刊 ISSN 枚举）。"""

    adapter_id = "crossref"
    family: AdapterFamily = "aggregator"
    # §1：无 SEARCH/RESOLVE/FETCH——仅 discover/enumerate（五源均无 FETCH，plan §2-3）。
    capabilities = Capability.DISCOVER | Capability.ENUMERATE
    # X-Rate-Limit 实测 10/1s（polite pool）→ 保守取上限 5 req/s = 300 req/min，burst=1。
    default_rate = RatePolicy(
        requests_per_minute=300.0,
        burst=1,
        source_note=(
            "api.crossref.org polite pool (UA mailto)：实测 X-Rate-Limit-Limit:10 / "
            "Interval:1s；保守取上限 5 req/s（远离 10/1s）；动态读响应头调节受冻结 "
            "HttpClient.get_bytes 不暴露 headers 所限、退化为静态上限 + 429 退避；"
            "research/site-survey/metadata-apis.md + aggregators.md §4 [LIVE] 2026-07-22"
        ),
    )
    auth_requirement = AuthLevel.NONE
    domains: tuple[str, ...] = ("api.crossref.org",)

    def __init__(self, http: HttpClient | None = None) -> None:
        # http=None：首次网络调用时惰性自建（见模块 docstring 的注入说明）。
        self._http = http

    def set_http_client(self, client: HttpClient) -> None:
        """注入组装好的 `HttpClient`（`adapter.HttpClientConsumer` 协议，同 arxiv 先例）。

        CLI 经 `bind_http_client` 在 `load_adapters()` 后注入携 config `[identity].email`
        （UA `mailto:`，polite pool 硬要求）的共享 client——crossref 尤其依赖此注入接通
        真实 mailto，否则掉出 polite pool（限速更严）。
        """
        self._http = client

    def _client(self) -> HttpClient:
        if self._http is None:
            self._http = HttpClient(user_agent=_default_user_agent())
        return self._http

    # -- discover（facet 逐年计数，1 请求）---------------------------------------------------

    def discover_timeline(self, venue: VenueSpec, since: str | None = None) -> Iterable[IssueRef]:
        """`rows=0&facet={field}:*` → 逐年 `IssueRef`（§5.1；两轴见模块 docstring）。

        enum-key（issn XOR prefix）+ date-field（published|created）从 venue 急切解析
        （非法早失败 CONFIG：issn·prefix 都缺/都在、未知 date-field）。`since`（可选年份
        下界，取前 4 位）收窄起点；网络在返回生成器惰性执行。
        """
        mode, key = _enum_key_of(venue)
        field = _date_field_of(venue)
        since_year = _since_year(since)
        return self._discover_years(venue, mode, key, field, since_year)

    def _discover_years(
        self, venue: VenueSpec, mode: str, key: str, field: str, since_year: int | None
    ) -> Iterator[IssueRef]:
        data = self._client().get_bytes(self._facet_url(mode, key, field))
        year_counts, _total = parse.parse_facet_years(data, field)
        for year in sorted(year_counts):
            if since_year is not None and year < since_year:
                continue
            yield IssueRef(
                venue_id=venue.id,
                volume=None,
                number=None,
                year=year,
                label=str(year),
                pub_date=None,
                paper_count_claimed=year_counts[year],
            )

    # -- enumerate（日期窗 + cursor 深翻断点续拉）-------------------------------------------

    def enumerate_issue(self, venue: VenueSpec, issue: IssueRef) -> Iterable[PaperStub]:
        """`(key, year)` 日期窗 → works cursor 深翻 → PaperStub 流（§5.1 cursor 契约）。

        enum-key（issn XOR prefix）+ date-field + year 急切求值（缺/冲突 → CONFIG）；cursor
        翻页与网络在返回生成器惰性执行。去重由 `(doi)` identifier 主键天然保证（窗口重建/
        重叠不产重复入库）。
        """
        mode, key = _enum_key_of(venue)
        field = _date_field_of(venue)
        year = issue.year
        if year is None:
            raise CrawlerError(
                ErrorClass.CONFIG,
                f"crossref enumerate needs IssueRef.year (per-year window), got {issue!r}",
            )
        return self._enumerate_window(venue, mode, key, field, year)

    def _enumerate_window(
        self, venue: VenueSpec, mode: str, key: str, field: str, year: int
    ) -> Iterator[PaperStub]:
        frm = f"{year:04d}-01-01"
        until = f"{year:04d}-12-31"
        cursor = "*"  # 深翻起点；不持久化、不跨任务复用（中断按窗口重建从头，§5.1）
        first_page = True
        while True:
            data = self._client().get_bytes(self._works_url(mode, key, field, frm, until, cursor))
            page = parse.parse_works_page(data)

            # total-results>0 但**首页** items 空解析 0 条 → parse（canary 标红，§5.1）。
            # 续页 items 空是深翻正常终止信号，不判 parse。
            if (
                first_page
                and page.total_results is not None
                and page.total_results > 0
                and page.item_count == 0
            ):
                raise CrawlerError(
                    ErrorClass.PARSE,
                    f"crossref {mode}:{key} {year}: total-results={page.total_results} but first "
                    "page items empty — parse anomaly",
                )
            first_page = False

            if page.skipped_untitled or page.skipped_doiless:
                # 跳过可观测（§5.1 title/doi 空跳过裁决）：venue/窗口/跳过数落 obslog。
                log_event(
                    "DEBUG",
                    "crossref records skipped",
                    venue=venue.id,
                    stage="enumerate",
                    year=year,
                    skipped_untitled=page.skipped_untitled,
                    skipped_doiless=page.skipped_doiless,
                )

            for record in page.records:
                yield parse.to_paper_stub(record)

            if page.item_count == 0 or page.next_cursor is None:
                return  # 终止：items 空（深翻到底）或无续页游标
            cursor = page.next_cursor

    # -- lookup（单篇 DOI → PaperStub；grab 命令用）----------------------------------------

    def lookup(self, doi: str) -> PaperStub | None:
        """`GET /works/{doi}` → `PaperStub`（`grab` 命令的单篇元数据 lookup）。

        404（DOI 未收录）归一为 `None`（正常空结果，非异常——同 unpaywall `lookup` 的
        GONE→None 口径）；缺 title/DOI 亦 `None`（无强合并锚点/无稳定身份不造 stub）。其余
        错误状态（4xx→config / 5xx→transient / 畸形 JSON→parse）经 `HttpClient`/`parse`
        原样 raise。返回的 stub 交 `MergeEngine.ingest(source='crossref')` 建最小 paper 行。
        """
        try:
            data = self._client().get_bytes(self._work_url(doi))
        except CrawlerError as exc:
            if exc.error_class is ErrorClass.GONE:
                return None
            raise
        record = parse.parse_single_work(data)
        return parse.to_paper_stub(record) if record is not None else None

    # -- healthcheck（固定 DOI title 比对）--------------------------------------------------

    def healthcheck(self, session: SessionHandle | None = None) -> HealthReport:
        """`GET /works/{固定DOI}` → 比对空白规整化 title[0]（§5.1）。

        真值 [PENDING]（未经在线捕获，`_HEALTHCHECK_TITLE=None`）：结构性探测——API 可达
        且 title[0] 非空即健康，detail 附实测 title 供在线冒烟 UPDATE_GOLDEN 捕获。捕获后
        （`_HEALTHCHECK_TITLE` 置真值）转精确 drift 比对（title 漂移 → unhealthy）。
        """
        try:
            data = self._client().get_bytes(self._work_url(_HEALTHCHECK_DOI))
        except CrawlerError as exc:
            return HealthReport(
                healthy=False, detail=f"works api unreachable ({exc.error_class.value}): {exc}"
            )
        try:
            title = parse.parse_single_work_title(data)
        except CrawlerError as exc:
            return HealthReport(healthy=False, detail=f"canary parse failed: {exc}")

        if _HEALTHCHECK_TITLE is None:
            # [PENDING] 真值未捕获：结构性健康（title 非空）+ 附实测值供捕获。
            return HealthReport(
                healthy=True, detail=f"[PENDING golden] observed title[0]={title!r}"
            )
        if title != _HEALTHCHECK_TITLE:
            return HealthReport(
                healthy=False,
                detail=f"canary drift — title {title!r} != expected {_HEALTHCHECK_TITLE!r}",
            )
        return HealthReport(healthy=True, detail="canary matched (title[0])")

    # -- URL 构造 ---------------------------------------------------------------------------

    def _facet_url(self, mode: str, key: str, field: str) -> str:
        params = {"rows": "0", "facet": f"{field}:*"}
        return f"{_API_ROOT}/{_base_path(mode, key)}/works?{urlencode(params)}"

    def _works_url(self, mode: str, key: str, field: str, frm: str, until: str, cursor: str) -> str:
        date_name = _DATE_FIELD_FILTER[field]
        params = {
            "filter": f"from-{date_name}-date:{frm},until-{date_name}-date:{until}",
            "rows": str(_ROWS),
            "cursor": cursor,
        }
        return f"{_API_ROOT}/{_base_path(mode, key)}/works?{urlencode(params)}"

    def _work_url(self, doi: str) -> str:
        # DOI 原样入 path（Crossref /works/{doi} 标准端点，DOI 内含 '/' 是 path 组成部分）。
        return f"{_API_ROOT}/works/{doi}"


# --- 模块级纯函数 -----------------------------------------------------------------------------


def _enum_key_of(venue: VenueSpec) -> tuple[str, str]:
    """enum-key 轴（issn XOR prefix，nber.md §3.1）→ `(mode, key)`，mode ∈ {"issn","prefix"}。

    - `identifiers.issn`（期刊，`list[str]` 取 [0]）→ `("issn", issn)` → 基址 /journals/{issn}
    - `identifiers.crossref_prefix`（前缀系列，`str`，如 nber `10.3386` / ssrn `10.2139`）→
      `("prefix", prefix)` → 基址 /prefixes/{prefix}
    二者**都在**（歧义）或**都缺**（无枚举键）→ CONFIG 响亮报错（XOR 校验）。期刊 issn 必填由
    D-015 lint 保证；前缀系列（preprint_channel）经 lint 豁免（registry `_lint_issn`，nber.md §6）。
    """
    issn = _issn_value(venue)
    prefix = _prefix_value(venue)
    if issn is not None and prefix is not None:
        raise CrawlerError(
            ErrorClass.CONFIG,
            f"crossref venue {venue.id!r} has both identifiers.issn and identifiers."
            "crossref_prefix — enum-key must be issn XOR prefix (exactly one)",
        )
    if issn is not None:
        return ("issn", issn)
    if prefix is not None:
        return ("prefix", prefix)
    raise CrawlerError(
        ErrorClass.CONFIG,
        f"crossref venue {venue.id!r} needs identifiers.issn[0] XOR "
        "identifiers.crossref_prefix (enum-key)",
    )


def _issn_value(venue: VenueSpec) -> str | None:
    """`identifiers.issn[0]`（合法非空串）→ str；缺失/畸形 → None（非枚举键）。"""
    raw = venue.identifiers.get("issn")
    if isinstance(raw, list) and raw and isinstance(raw[0], str) and raw[0].strip():
        return raw[0].strip()
    return None


def _prefix_value(venue: VenueSpec) -> str | None:
    """`identifiers.crossref_prefix`（合法非空串，如 `10.3386`）→ str；缺失/畸形 → None。"""
    raw = venue.identifiers.get("crossref_prefix")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return None


def _date_field_of(venue: VenueSpec) -> str:
    """date-field 轴（published | created，默认 published，nber.md §3.1）。

    从 `venue.quirks.crossref_date_field` 读取；缺省 → `published`（既有 by-ISSN 期刊零改）；
    未知值 → CONFIG 响亮报错。ssrn 走 `created`（登记年轴），nber/期刊走 `published`（出版年轴）。
    """
    raw = venue.quirks.get(_DATE_FIELD_QUIRK)
    if raw is None:
        return _DEFAULT_DATE_FIELD
    if isinstance(raw, str) and raw in _VALID_DATE_FIELDS:
        return raw
    raise CrawlerError(
        ErrorClass.CONFIG,
        f"crossref venue {venue.id!r} has invalid quirks.{_DATE_FIELD_QUIRK}={raw!r} "
        f"(must be one of {sorted(_VALID_DATE_FIELDS)})",
    )


def _base_path(mode: str, key: str) -> str:
    """enum-key `(mode, key)` → Crossref URL 基址路径段（不含前导/后随斜杠）。"""
    if mode == "issn":
        return f"journals/{key}"
    return f"prefixes/{key}"  # mode == "prefix"（_enum_key_of 保证二值域）


def _since_year(since: str | None) -> int | None:
    """`since`（可选年份下界，取前 4 位数字）→ int；非法格式 → CONFIG。"""
    if since is None:
        return None
    head = since[:4]
    if len(head) == 4 and head.isdigit():
        return int(head)
    raise CrawlerError(ErrorClass.CONFIG, f"invalid crossref since (need YYYY prefix): {since!r}")


__all__ = ["CrossrefAdapter"]
