"""NBER Working Papers `SourceAdapter` 主体（design/adapters/nber.md §1/§3/§4；AC-5.2 载体）。

family=`open_access`（无认证；获取阶梯第 0 档=匿名直取 + OA-fallback）。能力
``RESOLVE | FETCH``——**enumerate 一律走 crossref**（D-005；venue `identifiers.
crossref_prefix: 10.3386` 驱动 CrossrefAdapter 的 prefix 模式枚举，nber.md §3.1）。
RSS 增量 watch 以 `DISCOVER` 通道表达（`parse.parse_rss_items`，Phase 5 通道设计、
Phase 6 订阅转主，§3.4——本 Phase 不点亮 DISCOVER 能力）。

阶段分工（§3）：

- `resolve_assets`（RESOLVE，**零网络** `resolve_offline=True`）：DOI 后缀取 `w{n}`/`t{n}`
  + 18 月开放窗离线判定（`parse.is_open_after_window`）。>18 月开放 → 确定性构造
  `www.nber.org/system/files/…` DIRECT PDF 计划；<18 月软门 → `raise NO_ENTITLEMENT`
  (`recent_gated`)、**不产计划**（既有 OA-fallback 天然兜底，auth-framework §8.1）。
  **红线**：不利用 3 篇/年匿名配额、不构造软门 URL、不绕过（AC-5.2 调研伦理批注）。
  全文范围 Phase 5 先限 `w`（`t` 路径未勘察实证 → 不产全文计划、元数据照收，N-2）。
- `fetch_asset`（FETCH，`www.nber.org` 匿名直取）：共享 `HttpClient.stream` → `io.write_stream`
  + **`%PDF` 魔数双守卫**——`%PDF` 权威校验归 pipeline（冻结分工），本层补一刀软门嗅探：
  >18 月判定错边界、命中软门返**非 PDF**（HTML 登录/付费页）→ 归 `no_entitlement`
  （**非 integrity**——预期内门控、非伪装泄漏，§3.3）→ 交 OA-fallback；**绝不重试凑配额、
  不换 IP、不走软门**（红线）。
- `healthcheck`：已知 >18 月开放 `w30000` PDF 首 chunk `%PDF` 结构性探测（不下正文）。真值
  [PENDING online-smoke UPDATE_GOLDEN]（冻结 `HttpClient` 不暴露 HEAD/content-type，退化为
  首字节 `%PDF` 魔数探测——同 crossref/elsevier "冻结 client 不暴露 headers" 口径）。

**双域分桶**（§4，★接缝 N-3）：`domains=(www.nber.org, www2.nber.org)`——`route_for` 把
`www2`（低号老论文 301 目标）**别名共享** `www` 桶（1 req/5s）。`back.nber.org`（RSS/sitemap，
`Crawl-delay:10`）**必须独立桶**（`BACK_RATE_POLICY`=1 req/10s）、**不进 domains**——否则被
`route_for` 别名到 `www` 桶错享宽松预算，违反 Crawl-delay:10。watch 路径落地时经"域出现即
register 保守桶"（OA-host 先例 stages.py `_fetch_oa_direct`）注册，**不扩展冻结 ratelimit.py**
（wiley §4 同口径）。
"""

from __future__ import annotations

import os
from collections.abc import Iterable, Iterator
from datetime import date

from paper_crawler.adapter import AdapterBase, AdapterFamily
from paper_crawler.adapters.nber import parse
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
    PaperStub,
    RatePolicy,
    SessionHandle,
    UrlStrategy,
    VenueSpec,
)
from paper_crawler.useragent import build_user_agent

# --- 端点与常量（nber.md §3/§4）--------------------------------------------------------------

_WWW_HOST = "www.nber.org"  # 全文 host（domains[0]，限速账本键）
_WWW2_HOST = "www2.nber.org"  # 低号老论文 301 目标（domains[1]，别名共享 www 桶）
# ★接缝 N-3：RSS/sitemap host（Crawl-delay:10）——**独立桶、不进 domains**（§4 alias 陷阱）。
BACK_HOST = "back.nber.org"

# 18 月开放窗默认值（venue.quirks.fulltext_open_after_months 覆盖，§6）。
_QUIRK_OPEN_AFTER = "fulltext_open_after_months"
_DEFAULT_OPEN_AFTER_MONTHS = 18

# 全文范围 Phase 5 先限 `w`（`t` 全文路径未勘察实证——只 HEAD 过 w{n}，nber.md §9 N-2）。
_FULLTEXT_SERIES_LETTERS = frozenset({"w"})

# healthcheck 锚点：已知 >18 月开放 w30000（[LIVE] 2026-07-24 HEAD 200，nber.md §3.5）。
_HEALTHCHECK_SERIES = "w30000"
# 软门嗅探读取的首字节数（同 arxiv/neurips `_HTML_SNIFF`）。
_HTML_SNIFF = 512

_CONTACT_EMAIL_ENV = "PAPER_CRAWLER_CONTACT_EMAIL"
# RFC 2606 保留 .invalid：惰性自建（无注入 client）时的占位 UA 联系人（同 crossref 先例）。
_PLACEHOLDER_EMAIL = "anonymous@paper-crawler.invalid"


def _default_user_agent() -> str:
    email = os.environ.get(_CONTACT_EMAIL_ENV, "").strip() or _PLACEHOLDER_EMAIL
    return build_user_agent(email)


def _today() -> date:
    """当前 UTC 日期（18 月窗判定基准）；单测经 monkeypatch 注入假时钟。"""
    return date.today()


class NberAdapter(AdapterBase):
    """NBER Working Papers adapter（`open_access`；prefix 10.3386 消费 + >18 月离线全文窗）。"""

    adapter_id = "nber"
    family: AdapterFamily = "open_access"
    # §1：RESOLVE|FETCH——enumerate 走 crossref（D-005）；RSS watch 的 DISCOVER
    # Phase 6 转主，本 Phase 不点亮。
    capabilities = Capability.RESOLVE | Capability.FETCH
    # §4：www.nber.org 全文匿名直取——robots 无 Crawl-delay [LIVE 07-24]，保守 1 req/5s。
    default_rate = RatePolicy(
        requests_per_minute=12.0,
        burst=1,
        source_note=(
            "www.nber.org 全文匿名直取；robots 无 Crawl-delay，保守 1 req/5s（=12 rpm）；"
            "back.nber.org(RSS) 独立桶 1 req/10s 遵 Crawl-delay:10（见 NberAdapter."
            "BACK_RATE_POLICY，不进 domains 避 alias 陷阱）；nber.md §4 [LIVE 2026-07-24]"
        ),
    )
    auth_requirement = AuthLevel.NONE
    # www2（低号老论文 301 目标）经 domains[1] 别名共享 www 桶（route_for）。back.nber.org
    # **不在此 tuple**（独立桶，§4）。apex nber.org 301→www、不单列。
    domains: tuple[str, ...] = (_WWW_HOST, _WWW2_HOST)
    # resolve 纯日期判定 + URL 构造（零网络，D-022 免限速闸）——非 elsevier 网络 entitlement 预检。
    resolve_offline = True

    # ★接缝 N-3：back.nber.org 独立限速桶（RSS/sitemap watch 路径 on-demand register 用；1 req/10s
    # 遵 Crawl-delay:10）。**不进 domains**（避 route_for alias 到 www 桶错享宽松预算，§4）——watch
    # 落地时经"域出现即 register 保守桶"（OA-host 先例）注册，与冻结 ratelimit.py 解耦。
    BACK_RATE_POLICY = RatePolicy(
        requests_per_minute=6.0,
        burst=1,
        source_note=(
            "back.nber.org（RSS/sitemap）独立桶 1 req/10s（=6 rpm）遵 robots Crawl-delay:10 "
            "[LIVE 2026-07-24]；on-demand register（OA-host 先例），不进 domains 避 alias（§4）"
        ),
    )

    def __init__(self, http: HttpClient | None = None) -> None:
        # http=None：首次网络调用（fetch/healthcheck）惰性自建；resolve 零网络不触 client。
        self._http = http

    def set_http_client(self, client: HttpClient) -> None:
        """注入组装好的共享 `HttpClient`（`adapter.HttpClientConsumer` 协议，同 neurips 先例）。

        NBER 无凭证（open_access）——共享 client 即可（无携密头隔离顾虑）。CLI 经 `bind_http_client`
        在装配期注入携 config `[identity].email`（诚实 UA，D-014）+ 共享 limiter 的 client。
        """
        self._http = client

    def _client(self) -> HttpClient:
        if self._http is None:
            self._http = HttpClient(user_agent=_default_user_agent())
        return self._http

    # -- resolve（零网络，18 月开放窗离线判定）-----------------------------------------------

    def resolve_assets(
        self, venue: VenueSpec, paper: PaperStub, session: SessionHandle | None = None
    ) -> list[AssetPlan]:
        """DOI→series + 18 月窗离线判定 → 开放 PDF 计划 / <窗 `raise NO_ENTITLEMENT`（§3.2）。

        纯离线（`resolve_offline=True`，无网络）：>18 月开放 → 确定性 DIRECT PDF 计划；<18 月
        软门 → `NO_ENTITLEMENT(recent_gated)`（不产计划 → OA-fallback，auth-framework §8.1；
        **不利用配额、不构造软门 URL、不绕过**——红线）。`session` 未使用（open_access 无认证，
        冻结协议签名要求）。非 w/t series（book chapter）或非 nber DOI → 空计划 + DEBUG 观测。
        全文先限 `w`（`t` 路径未证实 → 空计划、元数据照收，N-2）。
        """
        doi = _doi_of(paper)
        series_id = parse.series_id_from_doi(doi)
        if series_id is None:
            # 非 w/t series（book chapter）/ 非 nber 前缀 → 不产全文计划（非异常，§3.2）。
            log_event(
                "DEBUG",
                "nber resolve: non-series DOI, no fulltext plan",
                venue=venue.id,
                stage="resolve",
                doi=doi,
            )
            return []
        if parse.series_letter(series_id) not in _FULLTEXT_SERIES_LETTERS:
            # `t{n}` 技术工作论文：全文路径未勘察实证 → Phase 5 不产全文计划（元数据照收，N-2/§9）。
            log_event(
                "DEBUG",
                "nber resolve: t-series fulltext deferred (N-2), no plan",
                venue=venue.id,
                stage="resolve",
                doi=doi,
                series=series_id,
            )
            return []

        open_after = _open_after_months(venue)
        is_open = parse.is_open_after_window(
            paper.pub_date, window_months=open_after, today=_today()
        )
        if not is_open:
            # <18 月软门（recent_gated）：预期内门控、不产平台计划 → OA-fallback 天然兜底（§8.1）。
            # status_code=None（离线日期判定，非 HTTP 响应体语义——区别于 elsevier 的 200）。
            raise CrawlerError(
                ErrorClass.NO_ENTITLEMENT,
                f"nber: {series_id} within {open_after}-month gate (pub_date={paper.pub_date!r})",
                detail="recent_gated",
            )
        return [
            AssetPlan(
                kind=AssetKind.PDF,
                url=parse.pdf_url(series_id),
                expected_type="application/pdf",
                url_strategy=UrlStrategy.DIRECT,
                auth_needed=AuthLevel.NONE,
                version=None,
            )
        ]

    # -- fetch（www.nber.org 匿名直取 + %PDF 魔数双守卫）-------------------------------------

    def fetch_asset(
        self, plan: AssetPlan, io: FetchIO, session: SessionHandle | None = None
    ) -> FetchResult:
        """`HttpClient.stream` → `io.write_stream`；软门返非 PDF → `NO_ENTITLEMENT`（§3.3）。

        `%PDF` **权威**校验归 pipeline（冻结分工）；本层补软门守卫——首字节非 `%PDF` 且形似
        HTML（软门登录/付费页）→ `NO_ENTITLEMENT`（**非 integrity**：预期内门控、非伪装泄漏；
        交 OA-fallback，**绝不重试凑配额/换 IP/走软门**，红线）。404/410 由 `HttpClient` 直接
        映射 `GONE`（延迟重试队列，§5）——本层不干预。`session` 未使用（open_access 无认证）。
        """
        stream = self._client().stream(plan.url)
        bytes_written, sha256 = io.write_stream(_soft_gate_guarded_stream(stream))
        return FetchResult(ok=True, bytes_written=bytes_written, sha256=sha256)

    # -- healthcheck（已知开放 w30000 PDF 首 chunk %PDF 结构性探测）---------------------------

    def healthcheck(self, session: SessionHandle | None = None) -> HealthReport:
        """已知 >18 月开放 `w30000` PDF 首 chunk `%PDF` 魔数结构性探测（不下正文，§3.5）。

        真值 [PENDING online-smoke UPDATE_GOLDEN]：冻结 `HttpClient` 无 HEAD/不暴露 content-type
        （同 crossref/elsevier 口径），退化为"取首 chunk 断 `%PDF` 魔数"的 HEAD 式轻探测——首字节
        `%PDF` 即健康。canary 须注册 `www.nber.org` 限速域（A-M1 `_register_rate_domains` 自动登记
        domains[0]，§4）。取回失败（不可达）→ unhealthy（不 raise，匹配既有 healthcheck 契约）。
        """
        url = parse.pdf_url(_HEALTHCHECK_SERIES)
        try:
            head = _read_head(self._client().stream(url), _HTML_SNIFF)
        except CrawlerError as exc:
            return HealthReport(
                healthy=False, detail=f"nber fulltext unreachable ({exc.error_class.value}): {exc}"
            )
        if head.lstrip().startswith(b"%PDF-"):
            return HealthReport(
                healthy=True, detail=f"[PENDING golden] {_HEALTHCHECK_SERIES} PDF %PDF- magic ok"
            )
        return HealthReport(
            healthy=False,
            detail=f"{_HEALTHCHECK_SERIES} fulltext lacks %PDF- magic (head={head[:16]!r})",
        )

    # `discover_timeline`/`enumerate_issue` 未声明能力（capabilities 仅 RESOLVE|FETCH——enumerate
    # 走 crossref prefix 模式，D-005；RSS watch DISCOVER Phase 6 转主）——沿 AdapterBase 默认
    # `CapabilityNotSupported`。RSS `<item>` 解析逻辑见 `parse.parse_rss_items`（通道设计，§3.4）。


# --- 模块级纯函数 -----------------------------------------------------------------------------


def _doi_of(paper: PaperStub) -> str:
    """从 stub 取 DOI（scheme='doi'）；缺失 → CONFIG（路由缺陷——nber 只按 DOI resolve）。"""
    for scheme, value in paper.identifiers:
        if scheme == "doi":
            return value
    raise CrawlerError(
        ErrorClass.CONFIG,
        f"nber resolve_assets needs a doi identifier: {paper.identifiers!r}",
    )


def _open_after_months(venue: VenueSpec) -> int:
    """`quirks.fulltext_open_after_months`（默认 18，软门窗）；非法 → CONFIG（显式挡 bool）。"""
    raw = venue.quirks.get(_QUIRK_OPEN_AFTER, _DEFAULT_OPEN_AFTER_MONTHS)
    if isinstance(raw, bool):
        raise CrawlerError(
            ErrorClass.CONFIG,
            f"nber venue {venue.id!r} quirks.{_QUIRK_OPEN_AFTER} must not be a bool: {raw!r}",
        )
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str):
        try:
            return int(raw.strip())
        except ValueError:
            raise CrawlerError(
                ErrorClass.CONFIG,
                f"nber venue {venue.id!r} quirks.{_QUIRK_OPEN_AFTER} is not an int: {raw!r}",
            ) from None
    raise CrawlerError(
        ErrorClass.CONFIG,
        f"nber venue {venue.id!r} quirks.{_QUIRK_OPEN_AFTER} has illegal type: {raw!r}",
    )


def _soft_gate_guarded_stream(chunks: Iterable[bytes]) -> Iterator[bytes]:
    """透传字节流但先嗅探首字节：`%PDF` 魔数放行；软门 HTML → `NO_ENTITLEMENT`（§3.3）。

    首个非 PDF 且形似 HTML 的响应体（>18 月判定错边界命中软门登录/付费页）归
    `no_entitlement`（**非 integrity**——预期内门控、非伪装泄漏；避免 pipeline 的 `%PDF`
    权威校验误判为 INTEGRITY 重下），交 OA-fallback，**绝不重试凑配额/换 IP/走软门**（红线）。
    结构同 neurips `_gone_guarded_stream`，唯错误类改判 `NO_ENTITLEMENT`（软门语义 vs 资源终态）。
    """
    iterator = iter(chunks)
    head = bytearray()
    for chunk in iterator:
        head.extend(chunk)
        if len(head) >= _HTML_SNIFF:
            break
    stripped = bytes(head).lstrip()
    if not stripped.startswith(b"%PDF-") and parse.looks_like_html(stripped):
        raise CrawlerError(
            ErrorClass.NO_ENTITLEMENT,
            "nber returned an HTML soft-gate (login/paywall) instead of a PDF; "
            "treated as no_entitlement (not integrity) → OA-fallback",
            detail="recent_gated",
        )
    if head:
        yield bytes(head)
    yield from iterator


def _read_head(chunks: Iterable[bytes], min_bytes: int) -> bytes:
    """流式读到 `>= min_bytes`（或流自然结束）即中止：HEAD 式轻探测（healthcheck 不下正文）。"""
    iterator = iter(chunks)
    head = bytearray()
    try:
        for chunk in iterator:
            head.extend(chunk)
            if len(head) >= min_bytes:
                break
    finally:
        close = getattr(iterator, "close", None)
        if callable(close):
            close()  # 提前关流释放连接（httpx 支持部分读后关闭，同 smoke_helpers）
    return bytes(head)


__all__ = ["NberAdapter"]
