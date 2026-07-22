"""CVF Open Access `SourceAdapter` 主体（design/adapters/cvf.md §1/§3-§6）。

**AC-2.4 的验收载体。** family=`open_access`（匿名可读、无认证——§2/§4）。能力
``DISCOVER | ENUMERATE | RESOLVE | FETCH``（无 SEARCH——冻结协议无 `search()`，
venue 内命中经 enumerate 全集 + 本地过滤达成，先例 arxiv/openreview）。Phase 2
服务 venue 仅 `cvpr`/`iccv`/`wacv`（主会卷；workshop/findings/demos 本期不注册，
§1）。

阶段分工（§3）：

- `discover_timeline`：**零网络**。届年来自内置 cadence 规则（`cadence.edition_years`）
  + venue `quirks.cvf_edition_overrides` 覆盖通道。`current_year` 由构造期可选注入
  （`current_year=` 关键字参数）或惰性取当前 UTC 年——测试注入固定值保证 cadence
  生成的确定性（§6 T4 裁决），生产实例化（`load_adapters()` 无参）用真实时钟。
- `enumerate_issue`：入口探测按**解析结果**分支（不按年份硬编 era，§3.2）：
  1. `GET {CONF}{year}`（bare）；
  2. 含 `dt.ptitle` 条目 → 早年 flat 列表，直接解析（1 请求）；
  3. 无条目但含 `?day=all` 链接 → day-landing 页，二次 `GET ...?day=all` 解析
     （2 请求）；
  4. 二者皆非（0 条目且无 day=all 链接）→ `PARSE`（结构漂移，CVF 无"200 空列表"
     合法态，§5）。
  venue `quirks.list_mode`（`'flat'`/`'day_all'`）可覆盖自动探测（逃生通道）。
- `resolve_assets`：**纯读 meta、零网络**（`meta['pdf_url']`/`meta['supp_url']`
  → `AssetPlan`；supp 不存在则不产 si plan，正常非错误——§3.3）。
- `fetch_asset`：`HttpClient.stream` 直取；无需 HTML 嗅探兜底（不同于 arxiv/
  openreview 的撤稿/挑战页场景——[LIVE] 勘察未见 CVF 单资产 200+HTML 软 404 形态，
  单资产 404 已由 `HttpClient` 统一映射 `GONE`，见 §5/§3.4）。
- `healthcheck`：最近一届 CVPR `?day=all` 首条目解析成功；不可达/解析失败时退化为
  `GET /menu` 断言含 `CVPR <当前年>` 锚点（§3.5）。

**限速**：`default_rate` = 1 req/2s（30 rpm）带出处（`RatePolicy.source_note`
强制）；`domains=("openaccess.thecvf.com",)` 单域（PDF/supp 同源直出，无 CDN，
§4）。实际限速由 pipeline `acquire_and_wait` 依 `default_rate` 强制，不在本 adapter。

**HttpClient 注入**（先例 arxiv/openreview brief）：`load_adapters()` 无参实例化，
`__init__(http=None)` 时首次网络调用惰性自建（UA 走 D-014，email 从环境变量
`PAPER_CRAWLER_CONTACT_EMAIL` 取、缺省占位 `.invalid`）。测试注入
`HttpClient(transport=MockTransport(...))` 达成零真实网络；CLI 经 `set_http_client`
注入配置化 client（`HttpClientConsumer` 协议）。
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from datetime import UTC, datetime

from paper_crawler.adapter import AdapterBase, AdapterFamily
from paper_crawler.adapters.cvf import cadence, parse
from paper_crawler.errors import CrawlerError, ErrorClass
from paper_crawler.http import HttpClient
from paper_crawler.obslog import log_event
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

# --- 端点与常量（§2/§4）------------------------------------------------------------------------

_BASE = "https://openaccess.thecvf.com"
_MENU_URL = f"{_BASE}/menu"

# venue id → 站点惯用大写会议代码（identifier canonical_dir 与 URL 路径共用）。
_CONF_CODE: dict[str, str] = {"cvpr": "CVPR", "iccv": "ICCV", "wacv": "WACV"}

_LIST_MODE_QUIRK = "list_mode"
_VALID_LIST_MODES = frozenset({"flat", "day_all"})

_CONTACT_EMAIL_ENV = "PAPER_CRAWLER_CONTACT_EMAIL"
# RFC 2606 保留 .invalid：惰性自建（无注入 client）时的占位联系人（先例 arxiv/openreview）。
_PLACEHOLDER_EMAIL = "anonymous@paper-crawler.invalid"


def _default_user_agent() -> str:
    email = os.environ.get(_CONTACT_EMAIL_ENV, "").strip() or _PLACEHOLDER_EMAIL
    return build_user_agent(email)


class CVFAdapter(AdapterBase):
    """CVF Open Access adapter（`open_access`）；Phase 2 服务 venue 仅 cvpr/iccv/wacv。"""

    adapter_id = "cvf"
    family: AdapterFamily = "open_access"
    # §1 裁决：无 SEARCH。
    capabilities = (
        Capability.DISCOVER | Capability.ENUMERATE | Capability.RESOLVE | Capability.FETCH
    )
    # §4：1 req/2s = 30 rpm、并发 1；source_note 出处强制（types.RatePolicy）。
    default_rate = RatePolicy(
        requests_per_minute=30.0,
        burst=1,
        source_note=(
            "openaccess.thecvf.com: /robots.txt -> 404 (no Disallow / Crawl-delay "
            "declared anywhere); no X-RateLimit-*/Retry-After observed in 22 [LIVE] "
            "requests; conservative default 1 req/2s (30 rpm) concurrency-1 per NFR-4 "
            "(community-hosted site, no site-declared budget to defer to); "
            "research/site-survey/cvf.md [LIVE] 2026-07-21"
        ),
    )
    # §2/§4：匿名可读、无认证、未见挑战门。
    auth_requirement = AuthLevel.NONE
    # [0] 主域 = 限速/日志账本键；PDF/supp 同源直出，单域（§4，对比 pmlr 双域教训）。
    domains: tuple[str, ...] = ("openaccess.thecvf.com",)
    # resolve_assets 纯读 meta 的 pdf/supp 绝对 URL，零网络 → 豁免 resolve 限速闸。
    resolve_offline = True

    def __init__(self, http: HttpClient | None = None, *, current_year: int | None = None) -> None:
        # http=None：首次网络调用惰性自建（仅 discover/cadence 零网络可用，其余方法需要
        # 真实/mock client）。current_year=None：惰性取当前 UTC 年——测试注入固定值。
        self._http = http
        self._current_year_override = current_year

    def set_http_client(self, client: HttpClient) -> None:
        """注入组装好的 `HttpClient`（`adapter.HttpClientConsumer` 协议）。"""
        self._http = client

    def _client(self) -> HttpClient:
        if self._http is None:
            self._http = HttpClient(user_agent=_default_user_agent())
        return self._http

    def _current_year(self) -> int:
        if self._current_year_override is not None:
            return self._current_year_override
        return datetime.now(UTC).year

    # -- discover（零网络，cadence 规则）------------------------------------------------------

    def discover_timeline(self, venue: VenueSpec, since: str | None = None) -> Iterable[IssueRef]:
        """cadence 届年（内置规则 + overrides）→ 逐年 `IssueRef`（零网络，§3.1）。

        字段分解定死（design §3.0）：volume/number/pub_date/paper_count_claimed
        恒 None；year=YYYY(int)；label='YYYY'。`since`（可选下界，取前 4 字符为年）
        只做下界裁剪，不触发任何探测（追新交给 track 子系统，§3.1）。
        """
        since_year = _year_prefix(since)
        years = cadence.edition_years(
            venue, current_year=self._current_year(), since_year=since_year
        )
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
            for year in years
        ]

    # -- enumerate（双形态列表页解析，§3.2）---------------------------------------------------

    def enumerate_issue(self, venue: VenueSpec, issue: IssueRef) -> Iterable[PaperStub]:
        """一届 → 该届全部论文的 `PaperStub`（列表页一次拿全，§3.2）。

        急切求值（非法 issue/venue 早失败为 CONFIG；列表页取回与解析在本方法内
        同步完成——CVF 无需像 arxiv/openreview 那样翻页，1-2 请求即拿到全集，
        故不做生成器惰性化，与 §3.2 "列表页一次拿全"的设计语言一致）。
        """
        if issue.year is None:
            raise CrawlerError(ErrorClass.CONFIG, f"cvf enumerate 需要 issue.year，实得 {issue!r}")
        canonical_dir = _canonical_dir(venue, issue.year)
        bare_url = f"{_BASE}/{canonical_dir}"
        forced_mode = _forced_list_mode(venue)

        list_url, entries = self._fetch_entries(canonical_dir, bare_url, forced_mode)
        stubs = [
            parse.to_paper_stub(
                entry, base_url=list_url, canonical_dir=canonical_dir, year=issue.year
            )
            for entry in entries
        ]
        log_event(
            "INFO",
            f"enumerate {canonical_dir}: {len(stubs)} paper(s) parsed",
            venue=venue.id,
            stage="enumerate",
            domain=self.domains[0],
        )
        return stubs

    def _fetch_entries(
        self, canonical_dir: str, bare_url: str, forced_mode: str | None
    ) -> tuple[str, list[parse.RawEntry]]:
        """入口探测：按解析结果分支（或 `quirks.list_mode` 覆盖），返回 (实际列表页 URL, 条目)。"""
        if forced_mode == "day_all":
            list_url = f"{bare_url}?day=all"
            return list_url, parse.parse_list_page(self._client().get_text(list_url))

        html = self._client().get_text(bare_url)
        entries = parse.parse_list_page(html)
        if entries:
            return bare_url, entries

        if forced_mode == "flat":
            raise CrawlerError(
                ErrorClass.PARSE,
                f"cvf {canonical_dir}: quirks.list_mode=flat 强制但解析出 0 条目（{bare_url}）",
            )
        if not parse.has_day_all_link(html):
            raise CrawlerError(
                ErrorClass.PARSE,
                f"cvf {canonical_dir}: 0 条目且无 '?day=all' 链接（结构漂移，{bare_url}）",
            )

        list_url = f"{bare_url}?day=all"
        entries = parse.parse_list_page(self._client().get_text(list_url))
        if not entries:
            raise CrawlerError(
                ErrorClass.PARSE, f"cvf {canonical_dir}?day=all: 解析出 0 条目（结构漂移）"
            )
        return list_url, entries

    # -- resolve（零网络，纯读 meta，§3.3）----------------------------------------------------

    def resolve_assets(
        self, venue: VenueSpec, paper: PaperStub, session: SessionHandle | None = None
    ) -> list[AssetPlan]:
        """meta 携带的 pdf/supp 绝对 URL → `AssetPlan`（零网络，§3.3）。

        **纯读 meta，不发请求、不做规则改写**——supp 文件名不可由 slug 规则推导
        （[LIVE] §2b/§4），PDF 虽可规则改写但优先与 supp 统一走采集 href（消除 era
        分支，见 parse.py 模块 docstring）。`meta['supp_url']` 缺失 → 不产 si plan
        （正常非错误，约 14% 条目无 supp）。
        """
        meta = dict(paper.meta)
        plans: list[AssetPlan] = []
        pdf_url = meta.get(parse.META_PDF_URL)
        if pdf_url:
            plans.append(
                AssetPlan(
                    kind=AssetKind.PDF,
                    url=pdf_url,
                    expected_type="application/pdf",
                    url_strategy=UrlStrategy.DIRECT,
                    auth_needed=AuthLevel.NONE,
                    version=None,
                )
            )
        supp_url = meta.get(parse.META_SUPP_URL)
        if supp_url:
            plans.append(
                AssetPlan(
                    kind=AssetKind.SI,
                    url=supp_url,
                    expected_type=_expected_type_for(supp_url),
                    url_strategy=UrlStrategy.DIRECT,
                    auth_needed=AuthLevel.NONE,
                    version=None,
                )
            )
        return plans

    # -- fetch（流式直取，§3.4）--------------------------------------------------------------

    def fetch_asset(
        self, plan: AssetPlan, io: FetchIO, session: SessionHandle | None = None
    ) -> FetchResult:
        """`HttpClient.stream` → `io.write_stream`（§3.4）。

        无需 HTML 嗅探兜底：单资产 404（个别 pdf/supp 下架）已由 `HttpClient` 统一
        映射 `GONE`（§5 表首二行区分整页 404 vs 单资产 404）；[LIVE] 勘察未见 CVF
        对存在的资产 URL 返回 200+HTML 软失败形态（不同于 arxiv/openreview 的撤稿/
        挑战页场景）。`%PDF` 权威校验归 pipeline（冻结分工）。
        """
        stream = self._client().stream(plan.url)
        bytes_written, sha256 = io.write_stream(stream)
        return FetchResult(ok=True, bytes_written=bytes_written, sha256=sha256)

    # -- healthcheck（最近一届 CVPR，退化 /menu，§3.5）----------------------------------------

    def healthcheck(self, session: SessionHandle | None = None) -> HealthReport:
        """`CVPR{当前年}?day=all` 首条目解析成功；不可达/解析失败退化为 `/menu` 锚点断言。"""
        year = self._current_year()
        url = f"{_BASE}/CVPR{year}?day=all"
        entries: list[parse.RawEntry] = []
        try:
            entries = parse.parse_list_page(self._client().get_text(url))
        except CrawlerError:
            entries = []
        if entries:
            return HealthReport(
                healthy=True, detail=f"CVPR{year}?day=all: 首条目解析成功（共 {len(entries)} 条）"
            )
        return self._healthcheck_menu_fallback(year)

    def _healthcheck_menu_fallback(self, year: int) -> HealthReport:
        try:
            html = self._client().get_text(_MENU_URL)
        except CrawlerError as exc:
            return HealthReport(
                healthy=False, detail=f"menu 不可达（{exc.error_class.value}）: {exc}"
            )
        anchor = f"CVPR {year}"
        if anchor not in html:
            return HealthReport(
                healthy=False,
                detail=f"CVPR{year} 不可达/解析失败，且 menu 缺 {anchor!r} 锚点",
            )
        return HealthReport(healthy=True, detail=f"退化检查：menu 含 {anchor!r} 锚点")


# --- 模块级纯函数 -----------------------------------------------------------------------------


def _year_prefix(since: str | None) -> int | None:
    """`since`（'YYYY...' 或 None）→ 年下界 int；前 4 字符非年份 → None（不设界）。"""
    if since is None or len(since) < 4 or not since[:4].isdigit():
        return None
    return int(since[:4])


def _canonical_dir(venue: VenueSpec, year: int) -> str:
    """venue+year → 规范目录名 `{CONF}{year}`（如 `CVPR2023`，§3.2）。

    `venue.id` 不在 `_CONF_CODE` 中（超出 Phase 2 范围）→ CONFIG（路由缺陷）。
    """
    code = _CONF_CODE.get(venue.id)
    if code is None:
        raise CrawlerError(
            ErrorClass.CONFIG,
            f"cvf adapter 无 venue {venue.id!r} 的会议代码映射（已登记: {sorted(_CONF_CODE)}）",
        )
    return f"{code}{year}"


def _forced_list_mode(venue: VenueSpec) -> str | None:
    """`quirks.list_mode`（'flat'|'day_all'，可选）——自动探测的逃生覆盖（§3.2）。"""
    raw = venue.quirks.get(_LIST_MODE_QUIRK)
    if raw is None:
        return None
    if raw not in _VALID_LIST_MODES:
        raise CrawlerError(
            ErrorClass.CONFIG,
            f"quirks.{_LIST_MODE_QUIRK} 必须是 {sorted(_VALID_LIST_MODES)} 之一，实得 {raw!r}",
        )
    return str(raw)


# supp 扩展名 → expected_type 推断（§3.3；未知扩展名 → application/octet-stream）。
_SUPP_EXPECTED_TYPES: dict[str, str] = {
    ".pdf": "application/pdf",
    ".zip": "application/zip",
    ".mp4": "video/mp4",
}


def _expected_type_for(url: str) -> str:
    """supp URL 的扩展名 → expected_type（[UNRESOLVED] ①：仅验 1 例 PDF supp，⚠ 实现期复核）。"""
    lower = url.lower()
    for ext, mime in _SUPP_EXPECTED_TYPES.items():
        if lower.endswith(ext):
            return mime
    return "application/octet-stream"


__all__ = ["CVFAdapter"]
