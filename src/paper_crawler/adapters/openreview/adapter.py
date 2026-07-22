"""OpenReview `SourceAdapter` 主体（design/adapters/openreview.md §1/§3-§6）。

**AC-2.1 / AC-2.2 的验收载体。** family=`open_access`（free_account 级——内容开放但
notes/PDF 需自有账号 token，§3）。能力 ``DISCOVER | ENUMERATE | RESOLVE | FETCH``
（无 SEARCH——冻结协议无 search()，arxiv.md §1 先例）。

阶段分工（§4）：

- `discover_timeline`：**零网络**。届表来自内置常量（`venues._ICLR_TABLE`，勘察 §2 逐年
  编码）+ venue `quirks.openreview_group_overrides` 覆盖通道。2015/2016 内置 None → 不产
  Issue（timeline「缺届」与 AC-2.1 anchor 表同口径）。字段分解定死：volume/number=None、
  year=YYYY(int，`--year` selector 生效字段)、label='YYYY'、paper_count_claimed=None。
- `enumerate_issue`：①issue.year 查届表得 venueid（精确大小写）；②`groups?id=<venueid>`
  依 `domain` 字段定 v1/v2 base URL（每届一次、进程内缓存）；③`<base>/notes?content.venueid=
  <venueid>&limit=1000&offset=…` 循环翻页至累计 `count`；④accepted 过滤 venueid==主会 id；
  ⑤空态 200 `{"notes":[],"count":0}` 合法空正常完成；⑥identifier=('openreview', forum)。
- `resolve_assets`：**纯构造零网络**。`meta['openreview_pdf']`（enumerate 携带的相对路径）→
  `https://openreview.net<path>`；无该键 → 0 plan（note 无 pdf 字段，正常非错误——2013/2014
  正文在 arXiv）。SI 同理。
- `fetch_asset`：`HttpClient.stream`（client 级 token cookie 由注入的 client 承载）→
  `io.write_stream`；HTML 回应（删除页/token 失效兜底）→ `GONE`。
- `healthcheck`：**匿名**（不依赖 token），v2/v1 双端各查一 group（断言存活 + domain）。

**认证边界（§3）**：token 经**注入的 client 的 client 级附加头** `Cookie:
openreview.accessToken=<token>` 承载（CLI 装配期从 config/env 组装，本 adapter 不读 token、
不碰明文）。**403 上下文重分类**：冻结 HttpClient 默认 403→`no_entitlement`；本 adapter 对
api/pdf 端点的 403 重分类为 `auth_expired`（该平台公开 venue 的 403 语义唯一＝挑战门/token
缺失）→ 走 Phase 1 auth_expired→整批 BLOCKED(auth) 路由（AC-1.5 同款）。
"""

from __future__ import annotations

import os
from collections.abc import Iterable, Iterator
from urllib.parse import urlencode

from paper_crawler.adapter import AdapterBase, AdapterFamily
from paper_crawler.adapters.openreview import parse, venues
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

# --- 端点与常量（§4/§5）----------------------------------------------------------------------

_GROUPS_ENDPOINT = "https://api2.openreview.net/groups"  # 匿名可读；判 domain / healthcheck
_PDF_SITE = "https://openreview.net"  # PDF/forum 页主站（非 api2）
_PAGE_LIMIT = 1000  # 勘察 §5：limit≤1000，offset 翻页至 count
_HTML_SNIFF = 512  # fetch HTML 嗅探读取的首字节数

_CONTACT_EMAIL_ENV = "PAPER_CRAWLER_CONTACT_EMAIL"
# RFC 2606 保留 .invalid：惰性自建（无注入 client、无 token）时的占位联系人。真实带 token
# 抓取走 CLI 注入的配置化 client（UA 携 config email + token cookie）。
_PLACEHOLDER_EMAIL = "anonymous@paper-crawler.invalid"

# healthcheck 匿名双端锚点（§4）：v2 端 2024 主会 + v1 端 2014 主会（2013-2017 数据路径依赖
# v1 端点存活）。断言 group 存在，v2 端额外断言含 domain（版本判定法的活体基线）。
_HEALTH_V2_GROUP = "ICLR.cc/2024/Conference"
_HEALTH_V1_GROUP = "ICLR.cc/2014/conference"
_HEALTH_V1_GROUPS_ENDPOINT = "https://api.openreview.net/groups"


def _default_user_agent() -> str:
    email = os.environ.get(_CONTACT_EMAIL_ENV, "").strip() or _PLACEHOLDER_EMAIL
    return build_user_agent(email)


class OpenReviewAdapter(AdapterBase):
    """OpenReview adapter（`open_access`/free_account）；Phase 2 服务 venue 仅 iclr。"""

    adapter_id = "openreview"
    family: AdapterFamily = "open_access"
    # §1 裁决：无 SEARCH。
    capabilities = (
        Capability.DISCOVER | Capability.ENUMERATE | Capability.RESOLVE | Capability.FETCH
    )
    # §5：30 rpm、并发 1（实测 60/60s 窗取半保守）；source_note 出处强制（types.RatePolicy）。
    default_rate = RatePolicy(
        requests_per_minute=30.0,
        burst=1,
        source_note=(
            "OpenReview 60 req/60s sliding window (x-ratelimit-* headers), halved to "
            "30 rpm concurrency-1 conservative; ToS transmission-rate clause; "
            "research/site-survey/openreview.md [LIVE] 2026-07-22"
        ),
    )
    # §3：notes/PDF 需自有账号 token（cookieAuth）→ free_account 级。
    auth_requirement = AuthLevel.FREE_ACCOUNT
    # [0] 主域 = 限速/日志账本键；api/openreview.net 经 route_for 的 alias 落到同一桶
    # （三域共享一份 30rpm 预算，§5 口径统一）。
    domains: tuple[str, ...] = ("api2.openreview.net", "api.openreview.net", "openreview.net")
    # resolve_assets 只读 enumerate 携带的 meta（pdf/SI 相对路径）拼绝对 URL，零网络 →
    # 豁免 resolve 限速闸（fetch 仍走限速——2260 篇不再被逐篇 resolve 限速空转，缺陷 C-C）。
    resolve_offline = True

    def __init__(self, http: HttpClient | None = None) -> None:
        # http=None：首次网络调用惰性自建（匿名、无 token——仅 discover/healthcheck 可用，
        # notes/pdf 会 403→auth_expired）。真实带 token 抓取由 CLI 注入配置化 client。
        self._http = http
        # 版本判定进程内缓存（每 venueid 一次 groups 查询，§4 ②）。
        self._version_cache: dict[str, parse.ApiVersion] = {}

    def set_http_client(self, client: HttpClient) -> None:
        """注入组装好的 `HttpClient`（`adapter.HttpClientConsumer` 协议）。

        CLI 装配期注入：无 token 时注入共享匿名 client（groups 可读、notes/pdf 会 403）；
        有 token 时注入**专属 client**（client 级 `Cookie: openreview.accessToken=<token>`
        附加头，绝不复用共享 client——cookie 外泄他站属凭证红线，见 http.py extra_headers 注释）。
        """
        self._http = client

    def _client(self) -> HttpClient:
        if self._http is None:
            self._http = HttpClient(user_agent=_default_user_agent())
        return self._http

    # -- discover（零网络）-------------------------------------------------------------------

    def discover_timeline(self, venue: VenueSpec, since: str | None = None) -> Iterable[IssueRef]:
        """届表（内置常量 + overrides）→ 逐年 `IssueRef`（零网络）。

        `since`（可选下界，取前 4 字符为年）晚于某年时收窄。2015/2016（None）天然缺席。
        """
        since_year = _year_prefix(since)
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
            for year, _venueid in venues.issue_years(venue, since_year=since_year)
        ]

    # -- enumerate（groups 判版本 → notes 翻页 → accepted 过滤）------------------------------

    def enumerate_issue(self, venue: VenueSpec, issue: IssueRef) -> Iterable[PaperStub]:
        """一届 → 全部**接收**论文的 `PaperStub`（accepted 过滤 venueid==主会 id）。

        急切求值届表查询与版本判定（非法早失败为 CONFIG）；notes 翻页与解析在返回的
        生成器惰性执行。403（无/失效 token）在网络层经 `_reclassify_403` 重分类为
        auth_expired（整批 BLOCKED——AC-1.5 路由）。
        """
        venueid = _venueid_for_issue(venue, issue)
        version = self._api_version(venueid)
        base = parse.api_base_url(version)
        return self._enumerate_pages(venue, issue, venueid, version, base)

    def _api_version(self, venueid: str) -> parse.ApiVersion:
        """判定 venueid 的 note 归属版本（进程内缓存；每届一次 groups 查询，§4 ②）。"""
        cached = self._version_cache.get(venueid)
        if cached is not None:
            return cached
        url = f"{_GROUPS_ENDPOINT}?{urlencode({'id': venueid})}"
        data = self._get_bytes(url)
        version = parse.api_version_from_groups(data, venueid)
        self._version_cache[venueid] = version
        return version

    def _enumerate_pages(
        self,
        venue: VenueSpec,
        issue: IssueRef,
        venueid: str,
        version: parse.ApiVersion,
        base: str,
    ) -> Iterator[PaperStub]:
        offset = 0
        emitted = 0
        excluded = 0
        while True:
            url = _notes_url(base, venueid, offset)
            page = parse.parse_notes_page(self._get_bytes(url), version)
            for note in page.notes:
                if parse.is_accepted(note, venueid):
                    yield parse.to_paper_stub(note, year=issue.year)
                    emitted += 1
                else:
                    excluded += 1
            offset += len(page.notes)
            # 翻页终止：累计已覆盖 count，或本页空（防御 count 与实际不符的死循环）。
            if offset >= page.count or not page.notes:
                break
        log_event(
            "INFO",
            f"enumerate {issue.label}: {emitted} accepted ({excluded} excluded by venueid filter)",
            venue=venue.id,
            stage="enumerate",
            domain=self.domains[0],
        )

    # -- resolve（零网络纯构造）--------------------------------------------------------------

    def resolve_assets(
        self, venue: VenueSpec, paper: PaperStub, session: SessionHandle | None = None
    ) -> list[AssetPlan]:
        """meta 携带的 pdf/SI 相对路径 → 绝对 URL `AssetPlan`（零网络）。

        无 `openreview_pdf` 键 → 0 个 pdf plan（note 无 pdf 字段，正常非错误——2013/2014
        正文在 arXiv，跨源发现归 Phase 3）。SI（`openreview_si`）存在时追加 kind=si plan。
        """
        meta = dict(paper.meta)
        plans: list[AssetPlan] = []
        pdf_path = meta.get(parse.META_PDF_PATH)
        if pdf_path:
            plans.append(
                AssetPlan(
                    kind=AssetKind.PDF,
                    url=_absolute_asset_url(pdf_path),
                    expected_type="application/pdf",
                    url_strategy=UrlStrategy.DIRECT,
                    auth_needed=AuthLevel.FREE_ACCOUNT,
                    version=None,
                )
            )
        si_path = meta.get(parse.META_SI_PATH)
        if si_path:
            plans.append(
                AssetPlan(
                    kind=AssetKind.SI,
                    url=_absolute_asset_url(si_path),
                    expected_type="application/octet-stream",
                    url_strategy=UrlStrategy.DIRECT,
                    auth_needed=AuthLevel.FREE_ACCOUNT,
                    version=None,
                )
            )
        return plans

    # -- fetch（流式，携注入 client 的 token cookie）-----------------------------------------

    def fetch_asset(
        self, plan: AssetPlan, io: FetchIO, session: SessionHandle | None = None
    ) -> FetchResult:
        """`HttpClient.stream` → `io.write_stream`；HTML 回应（删除页/token 失效兜底）→ `GONE`。

        token 失效的**批量** HTML 由 enumerate 的 403→auth_expired 先行拦截（整批 BLOCKED）；
        此处 HTML 嗅探兜底个别删除页。403 亦经 `_reclassify_403` 重分类 auth_expired。
        `%PDF` 权威校验在 pipeline（冻结分工）。
        """
        try:
            stream = self._client().stream(plan.url)
            bytes_written, sha256 = io.write_stream(_gone_guarded_stream(stream))
        except CrawlerError as exc:
            raise _reclassify_403(exc) from exc
        return FetchResult(ok=True, bytes_written=bytes_written, sha256=sha256)

    # -- healthcheck（匿名双端 groups 查询）--------------------------------------------------

    def healthcheck(self, session: SessionHandle | None = None) -> HealthReport:
        """匿名双端各查一 group（§4）：v2 端 2024（断言含 domain）+ v1 端 2014（断言存活）。

        token 有效性**不属** healthcheck（平台健康与用户凭证分离；token 问题由 BLOCKED 反馈）。
        故用匿名 `_client()`（若注入了带 token 的 client 也无妨——groups 匿名可读）。
        """
        v2_url = f"{_GROUPS_ENDPOINT}?{urlencode({'id': _HEALTH_V2_GROUP})}"
        v1_url = f"{_HEALTH_V1_GROUPS_ENDPOINT}?{urlencode({'id': _HEALTH_V1_GROUP})}"
        try:
            v2_data = self._client().get_bytes(v2_url)
            v1_data = self._client().get_bytes(v1_url)
        except CrawlerError as exc:
            return HealthReport(
                healthy=False, detail=f"groups unreachable ({exc.error_class.value}): {exc}"
            )

        try:
            v2_version = parse.api_version_from_groups(v2_data, _HEALTH_V2_GROUP)
            v1_ids = parse.group_ids(v1_data)
        except CrawlerError as exc:
            return HealthReport(healthy=False, detail=f"groups parse failed: {exc}")

        if v2_version is not parse.ApiVersion.V2:
            return HealthReport(
                healthy=False,
                detail=f"{_HEALTH_V2_GROUP} lost its 'domain' field (v2 detection baseline broken)",
            )
        if _HEALTH_V1_GROUP not in v1_ids:
            return HealthReport(
                healthy=False,
                detail=f"v1 endpoint missing {_HEALTH_V1_GROUP} (2013-2017 path at risk)",
            )
        return HealthReport(
            healthy=True, detail="v2 (2024 domain) + v1 (2014) groups baseline reachable"
        )

    # -- 网络小工具（403 重分类统一入口）----------------------------------------------------

    def _get_bytes(self, url: str) -> bytes:
        """`get_bytes` 包装：把 api 端点的 403（no_entitlement）重分类为 auth_expired（§6）。"""
        try:
            return self._client().get_bytes(url)
        except CrawlerError as exc:
            raise _reclassify_403(exc) from exc


# --- 模块级纯函数 -----------------------------------------------------------------------------


def _reclassify_403(exc: CrawlerError) -> CrawlerError:
    """403（冻结 HttpClient 默认 `no_entitlement`）→ `auth_expired`（§6 实现注记）。

    该平台公开 venue 的 403 语义唯一＝挑战门/token 缺失或失效（不存在「有 token 仍无权」
    场景），无需读响应体即可重分类。其余 error_class 原样透传。重分类后走 Phase 1 既有
    auth_expired→整批 BLOCKED(auth) 路由（AC-1.5 同款），status 给 token 配置指引（§3）。
    """
    if exc.error_class is ErrorClass.NO_ENTITLEMENT:
        return CrawlerError(
            ErrorClass.AUTH_EXPIRED,
            f"openreview 403 challenge/token required (reclassified): {exc}",
            detail="openreview_challenge",
        )
    return exc


def _year_prefix(since: str | None) -> int | None:
    """`since`（'YYYY...' 或 None）→ 年下界 int；前 4 字符非年份 → None（不设界）。"""
    if since is None or len(since) < 4 or not since[:4].isdigit():
        return None
    return int(since[:4])


def _venueid_for_issue(venue: VenueSpec, issue: IssueRef) -> str:
    """issue.year 查届表得主会 venueid（精确大小写）；缺 year/届表 None → CONFIG（路由缺陷）。"""
    if issue.year is None:
        raise CrawlerError(
            ErrorClass.CONFIG, f"openreview enumerate needs issue.year, got {issue!r}"
        )
    venueid = venues.resolve_venue_table(venue).get(issue.year)
    if venueid is None:
        raise CrawlerError(
            ErrorClass.CONFIG,
            f"venue {venue.id!r} year {issue.year} has no OpenReview main-conference group "
            "(missing year, or not in the built-in table / overrides)",
        )
    return venueid


def _notes_url(base: str, venueid: str, offset: int) -> str:
    """构造 notes 翻页 URL（禁携 email 参数——robots `/*?*email=` 唯一禁则 + 隐私红线）。"""
    params = {
        "content.venueid": venueid,
        "limit": str(_PAGE_LIMIT),
        "offset": str(offset),
    }
    return f"{base}/notes?{urlencode(params)}"


def _absolute_asset_url(relative_path: str) -> str:
    """`content.pdf.value` 相对路径 → 绝对 URL（同域 openreview.net）。"""
    if relative_path.startswith(("http://", "https://")):
        return relative_path  # 已是绝对（防御性——正常态为 `/pdf/<hex>.pdf`）
    return f"{_PDF_SITE}{relative_path if relative_path.startswith('/') else '/' + relative_path}"


def _gone_guarded_stream(chunks: Iterable[bytes]) -> Iterator[bytes]:
    """透传字节流但先嗅探首字节：PDF 魔数放行；HTML 页（删除/挑战页）→ `GONE`。

    `Content-Type: text/html` 的响应（删除页、token 失效的 403 HTML）在正文形态上表现为
    HTML——归 `GONE`（资源终态、不重试），避免 pipeline 的 `%PDF` 校验误判为 INTEGRITY 重下。
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
            "openreview returned an HTML page (deleted/challenge), not a PDF/asset",
        )
    if head:
        yield bytes(head)
    yield from iterator


def _looks_like_html(head: bytes) -> bool:
    low = head[:64].lower()
    return low.startswith(b"<!doctype html") or low.startswith(b"<html") or b"<html" in low


__all__ = ["OpenReviewAdapter"]
