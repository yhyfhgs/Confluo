"""NeurIPS proceedings `SourceAdapter` 主体（design/adapters/neurips-proceedings.md §1/§3-§5）。

把零网络纯逻辑（`parse`）与 T2 共享 `HttpClient` 组装成 adapter。能力口径（design §1）：
``DISCOVER | ENUMERATE | RESOLVE | FETCH``——**不声明 SEARCH**（冻结 `SourceAdapter`
协议无 `search()`，arxiv/openreview/pmlr 同款先例）。

阶段分工（design §3）：

- `discover_timeline`：``[quirks.first_year(默认1987) .. quirks.known_through_year
  (默认 当前UTC年-1)]`` 逐年生成 `IssueRef`，**零网络**（程序生成，design §8-★2 已
  裁决；非"解析首页"——1987..今逐年连续、``vol=year-1987`` 纯函数，[LIVE] 勘察已
  证实，见 `parse.parse_proceedings_list` 模块docstring 的一致性回归说明）。新届
  追加归 `track` 子系统（design/08 §4），不在本 adapter 职责内。
- `enumerate_issue`：GET 年页（``{base}/paper_files/paper/{year}``，1 请求，唯一
  网络调用）→ `parse.parse_year_page` 解析。0 条目由 `parse` 层直接判 `PARSE`
  （neurips 无 pmlr 式空卷歧义——已发布年恒非空，design §5 失败模式表）。
- `resolve_assets`：纯 URL 构造、**零网络**（hash+year+后缀规则 → 单个 PDF
  `AssetPlan`；后缀优先取 enumerate 逐字捕获的 ``meta['asset_suffix']``，缺失时
  回退 `(era,track)` 闭表，未知组合响亮 `CONFIG`）。Supplemental **本期不产**
  （design §3.3：存在性须详情页判定，纯构造会误产不存在资产，留 Phase 3
  enrichment）。
- `fetch_asset`：`HttpClient.stream` → `FetchIO.write_stream`；PDF url 却回 HTML
  页判 `GONE`（`_gone_guarded_stream`，arxiv/openreview 同款先例）。
- `healthcheck`：GET 2021（legacy）+ 2022（modern）两个年页（2 请求，覆盖后缀边界
  两态与 conference/D&B 两 track）→ 断言 3 个固定 canary（1×2021 legacy、1×2022
  conference、1×2022 D&B）规整化 title + track 双字段命中，且两页解析篇数不低于
  下限（design §3.5）。

**限速/礼貌**：`default_rate` = 1 req/2s（=30 req/min）——站点无 robots.txt、无
`X-RateLimit-*`/ToS 限速条款（[LIVE] §7/§8），NFR-4「无声明站点默认」；三镜像域
共享同一预算（同 Apache 后端字节级相同，[LIVE] §1）。``domains[0]=
'proceedings.neurips.cc'``（`citation_pdf_url` 自称 canonical，[LIVE] §1）作限速/
日志账本键与 URL 构造 base；``papers.neurips.cc``/``papers.nips.cc`` 仅登记为兜底
镜像——本 adapter 实际请求恒走 `domains[0]`。

**HttpClient 注入**（同 arxiv/pmlr/openreview 先例）：`load_adapters()` 无参实例化
——``__init__(http=None)``，首次网络调用惰性自建（UA 走 D-014，email 从环境变量
`PAPER_CRAWLER_CONTACT_EMAIL` 取，缺失用占位 `.invalid` 地址）。**测试注入
`HttpClient(transport=MockTransport(...))` 达成零真实网络**；真实在线应注入配置化
client 使 UA 携真实联系方式。
"""

from __future__ import annotations

import os
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime

from paper_crawler.adapter import AdapterBase, AdapterFamily
from paper_crawler.adapters.neurips_proceedings import parse
from paper_crawler.errors import CrawlerError, ErrorClass
from paper_crawler.http import HttpClient
from paper_crawler.types import (
    AssetKind,
    AssetPlan,
    AuthLevel,
    Capability,
    FetchIO,
    FetchResult,
    HealthReport,
    IssueRef,
    PaperStub,
    RatePolicy,
    SessionHandle,
    UrlStrategy,
    VenueSpec,
)
from paper_crawler.useragent import build_user_agent

# --- 端点与常量（design §2/§3/§4 表）-----------------------------------------------------------

_BASE_URL = "https://proceedings.neurips.cc"  # citation_pdf_url 自称 canonical（[LIVE] §1）
_YEAR_PAGE_TMPL = "/paper_files/paper/{year}"
_DEFAULT_FIRST_YEAR = 1987  # [LIVE] §2：/1986→404 下界；quirks.first_year 缺省值
_HTML_SNIFF = 512  # fetch HTML 嗅探读取的首字节数（arxiv/openreview 同款）

_CONTACT_EMAIL_ENV = "PAPER_CRAWLER_CONTACT_EMAIL"
# RFC 2606 保留 .invalid 顶级域——占位联系人不可能是真实地址（隐私安全），且明确
# 信号「该走配置化 client 注入真实 mailto」。仅在惰性自建且未设环境变量时使用
# （arxiv/pmlr/openreview 同款先例）。
_PLACEHOLDER_EMAIL = "anonymous@paper-crawler.invalid"


def _default_user_agent() -> str:
    """惰性自建 client 的 UA：email 从环境变量取（不硬编码），缺省用 `.invalid` 占位。"""
    email = os.environ.get(_CONTACT_EMAIL_ENV, "").strip() or _PLACEHOLDER_EMAIL
    return build_user_agent(email)


def _year_page_url(year: int) -> str:
    return f"{_BASE_URL}{_YEAR_PAGE_TMPL.format(year=year)}"


# --- healthcheck canary（design §3.5/§6：2021 legacy + 2022 conference/D&B 三样本）--------------


@dataclass(frozen=True)
class _HealthCanary:
    """一条 healthcheck 锚点：年份+hash 定位 + 期望规整化 title/track。"""

    year: int
    hash: str
    title: str
    track: str


# ⚠ 2021 hash 为真实值（docs/research/site-survey/neurips-proceedings.md §5/§9 [LIVE]
# 实测，32-hex 逐字复用）；title 未被勘察记录全文（预算内未抓取该样本的标题正文），
# 故为合成占位——**实现期义务**：T5 在线冒烟核验后须用实测标题替换（arxiv canary
# 「⚠ 合成占位需真实替换」同款纪律，见 arxiv/adapter.py `_CANARIES` 模块docstring）。
# 2022 两条 hash/title 因勘察预算耗尽（仅留 6 位截断 hash，无完整值可信复用）而
# **全部合成**，故意使用一望即知的占位十六进制模式（`deadbeef`/`facefeed` 重复）而
# 非貌似真实的随机哈希，避免未来维护者误把占位当真实数据长期沉淀。
_CANARIES: tuple[_HealthCanary, ...] = (
    _HealthCanary(
        year=2021,
        hash="000c076c390a4c357313fca29e390ece",
        title="SYNTHETIC placeholder canary title pending T5 real-value replacement (2021)",
        track="none",
    ),
    _HealthCanary(
        year=2022,
        hash="deadbeefdeadbeefdeadbeefdeadbeef",
        title=(
            "SYNTHETIC placeholder canary title pending T5 real-value replacement (2022 conference)"
        ),
        track="conference",
    ),
    _HealthCanary(
        year=2022,
        hash="facefeedfacefeedfacefeedfacefeed",
        title=(
            "SYNTHETIC placeholder canary title pending T5 real-value replacement "
            "(2022 datasets_and_benchmarks)"
        ),
        track="datasets_and_benchmarks",
    ),
)
_HEALTHCHECK_YEARS: tuple[int, ...] = (2021, 2022)
# 篇数下限（design §3.5"或任一页解析 < 篇数下限 → unhealthy"）——刻意低于本 adapter
# 自带的合成 fixture 实际条目数（2021=3、2022=4，见 tests/fixtures/neurips_proceedings/），
# 留一点余量防止 fixture 微调误报，同时仍能捕获"选择器漂移到只剩 0-1 条"的真实退化。
_HEALTHCHECK_MIN_PAPERS: dict[int, int] = {2021: 2, 2022: 2}


# --- adapter 主体 ----------------------------------------------------------------------------


class NeuripsProceedingsAdapter(AdapterBase):
    """NeurIPS 正式 proceedings adapter（`open_access` family）；Phase 2 服务 venue 仅 `neurips`。

    评审版（OpenReview `neurips_openreview` channel）本期推迟，不在本 adapter 范围
    （design §1；与 openreview.md §1 口径一致）。
    """

    adapter_id = "neurips_proceedings"
    family: AdapterFamily = "open_access"
    # design §1 裁决：无 SEARCH。
    capabilities = (
        Capability.DISCOVER | Capability.ENUMERATE | Capability.RESOLVE | Capability.FETCH
    )
    # 1 req/2s = 30 req/min；三镜像域共享同一预算（同 Apache 后端字节级相同，[LIVE] §1）。
    default_rate = RatePolicy(
        requests_per_minute=30.0,
        burst=1,
        source_note=(
            "proceedings.neurips.cc / papers.neurips.cc / papers.nips.cc 均无 robots.txt"
            "（两域 404）、无 X-RateLimit-*/Retry-After/ToS 限速条款 → NFR-4 保守默认"
            "1 req/2s/domain；research/site-survey/neurips-proceedings.md [LIVE] 2026-07-21"
        ),
    )
    auth_requirement = AuthLevel.NONE
    # [0] 主域（citation_pdf_url 自称 canonical，实际请求 base，见 `_BASE_URL`）；
    # [1][2] 内容等价镜像（字节级相同，同 Apache 后端）——本 adapter 恒用 [0] 构造 URL，
    # [1][2] 仅登记备查（换镜像不翻倍限速预算——design §4）。
    domains: tuple[str, ...] = (
        "proceedings.neurips.cc",
        "papers.neurips.cc",
        "papers.nips.cc",
    )

    def __init__(self, http: HttpClient | None = None) -> None:
        # http=None：首次网络调用时惰性自建（见模块 docstring 的注入说明）。
        self._http = http

    def set_http_client(self, client: HttpClient) -> None:
        """注入组装好的 `HttpClient`（`adapter.HttpClientConsumer` 协议，同前例）。"""
        self._http = client

    def _client(self) -> HttpClient:
        if self._http is None:
            self._http = HttpClient(user_agent=_default_user_agent())
        return self._http

    # -- discover（零网络）-------------------------------------------------------------------

    def discover_timeline(self, venue: VenueSpec, since: str | None = None) -> Iterable[IssueRef]:
        """``[first_year..known_through_year]`` 逐年生成 `IssueRef`（零网络，design §3.1）。

        字段分解定死（openreview 先例）：``volume``=None、``number``=None、
        ``year``=int、``label``='YYYY'、``pub_date``=None、``paper_count_claimed``=None
        （discover 无权威计数，enumerate 回填）。`since` 晚于 `first_year` 时收窄起点。
        """
        first_year = _first_year(venue)
        known_through_year = _known_through_year(venue)
        since_year = _parse_since_year(since)
        start = first_year if since_year is None else max(first_year, since_year)
        return [
            IssueRef(
                venue_id=venue.id,
                volume=None,
                number=None,
                year=year,
                label=f"{year:04d}",
                pub_date=None,
                paper_count_claimed=None,
            )
            for year in range(start, known_through_year + 1)
        ]

    # -- enumerate（1 请求/届，唯一网络调用）--------------------------------------------------

    def enumerate_issue(self, venue: VenueSpec, issue: IssueRef) -> Iterable[PaperStub]:
        """GET 年页 → `parse.parse_year_page`（design §3.2）。0 条目由 parse 层判 `PARSE`。"""
        year = _issue_year(issue)
        data = self._client().get_bytes(_year_page_url(year))
        papers = parse.parse_year_page(data)
        return [parse.to_paper_stub(p, year=year) for p in papers]

    # -- resolve（零网络，纯构造）-------------------------------------------------------------

    def resolve_assets(
        self, venue: VenueSpec, paper: PaperStub, session: SessionHandle | None = None
    ) -> list[AssetPlan]:
        """hash+year+后缀规则 → 单个 PDF `AssetPlan`（design §3.3；仅 PDF，不产 Supplemental）。"""
        hash_ = _hash_of(paper)
        year = _paper_year(paper)
        infix = _infix_for(paper, year)
        url = parse.pdf_url(_BASE_URL, year=year, hash_=hash_, infix=infix)
        return [
            AssetPlan(
                kind=AssetKind.PDF,
                url=url,
                expected_type="application/pdf",
                url_strategy=UrlStrategy.DIRECT,
                auth_needed=AuthLevel.NONE,
                version=None,
            )
        ]

    # -- fetch（流式）------------------------------------------------------------------------

    def fetch_asset(
        self, plan: AssetPlan, io: FetchIO, session: SessionHandle | None = None
    ) -> FetchResult:
        """`HttpClient.stream` → `io.write_stream`；PDF url 却回 HTML 页判 `GONE`（design §3.4）。

        `%PDF` 权威校验归 pipeline（冻结分工）；HTTP 404/410 已由 `HttpClient` 直接映射
        `GONE`，本层只补一刀"200 但回了 HTML 正文"的嗅探。
        """
        stream = self._client().stream(plan.url)
        bytes_written, sha256 = io.write_stream(_gone_guarded_stream(stream))
        return FetchResult(ok=True, bytes_written=bytes_written, sha256=sha256)

    # -- healthcheck（2 请求，跨边界 canary）--------------------------------------------------

    def healthcheck(self, session: SessionHandle | None = None) -> HealthReport:
        """GET 2021+2022 年页 → 3 canary 规整化 title+track 双字段比对（design §3.5）。

        任一年页取回/解析失败、任一年页篇数低于下限、或任一 canary 缺失/字段漂移 →
        `unhealthy`（不 raise——匹配 arxiv/openreview/pmlr 既有 healthcheck 契约）。
        """
        try:
            pages = {year: self._fetch_and_parse_year(year) for year in _HEALTHCHECK_YEARS}
        except CrawlerError as exc:
            return HealthReport(
                healthy=False,
                detail=f"year page fetch/parse failed ({exc.error_class.value}): {exc}",
            )

        for year, minimum in _HEALTHCHECK_MIN_PAPERS.items():
            count = len(pages[year])
            if count < minimum:
                return HealthReport(
                    healthy=False,
                    detail=f"{year} year page parsed only {count} papers (< {minimum} floor)",
                )

        by_hash = {p.hash: p for papers in pages.values() for p in papers}
        drifts = [msg for c in _CANARIES if (msg := _canary_drift(c, by_hash.get(c.hash)))]
        if drifts:
            return HealthReport(healthy=False, detail="canary drift — " + "; ".join(drifts))
        return HealthReport(
            healthy=True,
            detail=f"{len(_CANARIES)} canaries matched across {_HEALTHCHECK_YEARS} (title + track)",
        )

    def _fetch_and_parse_year(self, year: int) -> tuple[parse.NeuripsPaper, ...]:
        data = self._client().get_bytes(_year_page_url(year))
        return parse.parse_year_page(data)


# --- 模块级纯函数 -----------------------------------------------------------------------------


def _coerce_year_quirk(raw: object, *, field: str, venue_id: str) -> int:
    """把 quirks 年份值归一为 int（YAML 未加引号得 int，加引号得 str）；非法 → `CONFIG`。

    显式挡布尔（bool 是 int 子类，`True`/`False` 当年份是荒谬值）——openreview
    `venues._coerce_year` 同款纪律。
    """
    if isinstance(raw, bool):
        raise CrawlerError(
            ErrorClass.CONFIG, f"venue {venue_id!r} quirks.{field} must not be a bool: {raw!r}"
        )
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str):
        try:
            return int(raw.strip())
        except ValueError:
            raise CrawlerError(
                ErrorClass.CONFIG,
                f"venue {venue_id!r} quirks.{field} is not a valid year: {raw!r}",
            ) from None
    raise CrawlerError(
        ErrorClass.CONFIG, f"venue {venue_id!r} quirks.{field} has an illegal type: {raw!r}"
    )


def _first_year(venue: VenueSpec) -> int:
    """`quirks.first_year`（默认 1987，[LIVE] §2 下界）；非法 → `CONFIG`。"""
    raw = venue.quirks.get("first_year", _DEFAULT_FIRST_YEAR)
    return _coerce_year_quirk(raw, field="first_year", venue_id=venue.id)


def _known_through_year(venue: VenueSpec) -> int:
    """`quirks.known_through_year`（默认 当前 UTC 年−1，安全已发布界，design §3.1）。"""
    raw = venue.quirks.get("known_through_year")
    if raw is None:
        return datetime.now(UTC).year - 1
    return _coerce_year_quirk(raw, field="known_through_year", venue_id=venue.id)


def _parse_since_year(since: str | None) -> int | None:
    """`since`（可选年份下界字符串）→ int；非法格式 → `CONFIG`。"""
    if since is None:
        return None
    try:
        return int(since)
    except ValueError as exc:
        raise CrawlerError(ErrorClass.CONFIG, f"invalid since year: {since!r}") from exc


def _issue_year(issue: IssueRef) -> int:
    if issue.year is None:
        raise CrawlerError(
            ErrorClass.CONFIG, f"neurips_proceedings enumerate needs issue.year, got {issue!r}"
        )
    return issue.year


def _paper_year(paper: PaperStub) -> int:
    if paper.year is None:
        raise CrawlerError(
            ErrorClass.CONFIG, f"neurips_proceedings resolve needs paper.year, got {paper!r}"
        )
    return paper.year


def _hash_of(paper: PaperStub) -> str:
    """从 stub 取 hash（scheme='neurips'）并校验形态；缺失/非法 → `CONFIG`（路由缺陷）。"""
    for scheme, value in paper.identifiers:
        if scheme == parse.SCHEME:
            return parse.validate_hash(value)
    raise CrawlerError(ErrorClass.CONFIG, f"paper has no neurips identifier: {paper.identifiers!r}")


def _infix_for(paper: PaperStub, year: int) -> str:
    """优先取 `meta['asset_suffix']` 逐字值；缺失（键不存在）时回退 `(era,track)` 闭表。"""
    meta = dict(paper.meta)
    if "asset_suffix" in meta:
        return meta["asset_suffix"]
    era = parse.era_for_year(year)
    return parse.infix_for_era_track(era, meta.get("track"))


def _canary_drift(canary: _HealthCanary, paper: parse.NeuripsPaper | None) -> str | None:
    """单条 canary 的漂移诊断；无漂移返回 None。"""
    if paper is None:
        return f"{canary.year}/{canary.hash}: missing from response"
    if paper.title != canary.title:  # NeuripsPaper.title 已规整化，直接等值
        return f"{canary.year}/{canary.hash}: title drift"
    if paper.track != canary.track:
        return f"{canary.year}/{canary.hash}: track drift ({paper.track!r} != {canary.track!r})"
    return None


def _gone_guarded_stream(chunks: Iterable[bytes]) -> Iterator[bytes]:
    """透传字节流但先嗅探首字节：PDF 魔数放行；HTML 页 → `GONE`（arxiv/openreview 同款）。

    首个非 PDF 且形似 HTML 的响应体归 `GONE`（资源终态、不重试），避免 pipeline 的
    `%PDF` 权威校验把它误判为 `INTEGRITY`（重下）。
    """
    iterator = iter(chunks)
    head = bytearray()
    for chunk in iterator:
        head.extend(chunk)
        if len(head) >= _HTML_SNIFF:
            break
    stripped = bytes(head).lstrip()
    if not stripped.startswith(b"%PDF-") and _looks_like_html(stripped):
        raise CrawlerError(
            ErrorClass.GONE,
            "neurips_proceedings returned an HTML page instead of a PDF (not-found/removed)",
        )
    if head:
        yield bytes(head)
    yield from iterator


def _looks_like_html(head: bytes) -> bool:
    low = head[:64].lower()
    return low.startswith(b"<!doctype html") or low.startswith(b"<html") or b"<html" in low


__all__ = ["NeuripsProceedingsAdapter"]
