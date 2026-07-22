"""Crossref `SourceAdapter` 主体（期刊主干；design/adapters/aggregators.md §5.1；AC-3.5 载体）。

把零网络纯逻辑（`parse`）与 T2 共享 `HttpClient` 组装成 aggregator adapter。能力口径
（§1 表）：``DISCOVER | ENUMERATE``——**无 SEARCH/RESOLVE/FETCH**（五源均无 FETCH，
plan §2-3；SEARCH 冻结协议无 `search()`，订阅命中经 enumerate + 本地过滤达成，§1）。

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
        """`rows=0&facet=published:*` → 逐出版年 `IssueRef`（§5.1）。

        `issn` 从 `venue.identifiers.issn[0]` 取（D-015：期刊+crossref 必填，lint 保证；
        本层缺省仍 CONFIG 早失败）。`since`（可选年份下界，取前 4 位）收窄起点。目标/边界
        急切求值（非法早失败 CONFIG）；网络在返回生成器惰性执行。
        """
        issn = _issn_of(venue)
        since_year = _since_year(since)
        return self._discover_years(venue, issn, since_year)

    def _discover_years(
        self, venue: VenueSpec, issn: str, since_year: int | None
    ) -> Iterator[IssueRef]:
        data = self._client().get_bytes(self._facet_url(issn))
        year_counts, _total = parse.parse_facet_years(data)
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
        """`(issn, year)` 日期窗 → works cursor 深翻 → PaperStub 流（§5.1 cursor 契约）。

        目标/窗口急切求值（缺 issn/year 早失败 CONFIG）；cursor 翻页与网络在返回生成器
        惰性执行。去重由 `(doi)` identifier 主键天然保证（窗口重建/重叠不产重复入库）。
        """
        issn = _issn_of(venue)
        year = issue.year
        if year is None:
            raise CrawlerError(
                ErrorClass.CONFIG,
                f"crossref enumerate needs IssueRef.year (per-year window), got {issue!r}",
            )
        return self._enumerate_window(venue, issn, year)

    def _enumerate_window(self, venue: VenueSpec, issn: str, year: int) -> Iterator[PaperStub]:
        frm = f"{year:04d}-01-01"
        until = f"{year:04d}-12-31"
        cursor = "*"  # 深翻起点；不持久化、不跨任务复用（中断按窗口重建从头，§5.1）
        first_page = True
        while True:
            data = self._client().get_bytes(self._works_url(issn, frm, until, cursor))
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
                    f"crossref {issn} {year}: total-results={page.total_results} but first page "
                    "items empty — parse anomaly",
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

    def _facet_url(self, issn: str) -> str:
        params = {"rows": "0", "facet": "published:*"}
        return f"{_API_ROOT}/journals/{issn}/works?{urlencode(params)}"

    def _works_url(self, issn: str, frm: str, until: str, cursor: str) -> str:
        params = {
            "filter": f"from-pub-date:{frm},until-pub-date:{until}",
            "rows": str(_ROWS),
            "cursor": cursor,
        }
        return f"{_API_ROOT}/journals/{issn}/works?{urlencode(params)}"

    def _work_url(self, doi: str) -> str:
        # DOI 原样入 path（Crossref /works/{doi} 标准端点，DOI 内含 '/' 是 path 组成部分）。
        return f"{_API_ROOT}/works/{doi}"


# --- 模块级纯函数 -----------------------------------------------------------------------------


def _issn_of(venue: VenueSpec) -> str:
    """从 `venue.identifiers.issn[0]` 取 ISSN；缺失/畸形 → CONFIG（D-015 lint 已保证期刊必填）。"""
    raw = venue.identifiers.get("issn")
    if isinstance(raw, list) and raw and isinstance(raw[0], str) and raw[0].strip():
        return raw[0].strip()
    raise CrawlerError(
        ErrorClass.CONFIG,
        f"crossref venue {venue.id!r} needs identifiers.issn[0] (D-015)",
    )


def _since_year(since: str | None) -> int | None:
    """`since`（可选年份下界，取前 4 位数字）→ int；非法格式 → CONFIG。"""
    if since is None:
        return None
    head = since[:4]
    if len(head) == 4 and head.isdigit():
        return int(head)
    raise CrawlerError(ErrorClass.CONFIG, f"invalid crossref since (need YYYY prefix): {since!r}")


__all__ = ["CrossrefAdapter"]
