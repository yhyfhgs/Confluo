"""Elsevier ScienceDirect `SourceAdapter` 主体（elsevier-sd.md §3/§5；AC-4.1 载体）。

family=`auth_gated`（官方 API 档——auth_gated 三档阶梯第 1 档，design/04 §3）。能力
``RESOLVE | FETCH``——**enumerate 一律 crossref**（D-005；elsevier robots 全禁 + 全站
TDMRep → 页面路线双重不可行 → API 唯一正道，AGENTS §6 / elsevier-sd.md §2）。域
`api.elsevier.com`（**非** `www.sciencedirect.com`；页面路线不走）。

阶段分工（§3）：

- `resolve_assets`（RESOLVE，**真实网络**）：无 key → `AuthRequired`（BLOCKER-1 离线分支，
  §3.1）；有 key → entitlement 预检（`GET /content/article/entitlement/doi/{doi}`）→ 有权产
  `AssetPlan(kind=PDF, url_strategy=API_CALL, httpAccept=application/pdf)`（XML SOURCE 备选经
  venue quirk `elsevier_want_xml_source` 可选同存，§3.1）/ 无权 → `raise NO_ENTITLEMENT`
  （AC-4.3：转 unpaywall OA-fallback，auth-framework §8.1；不计 failures §8.5——pipeline 侧接线
  归 auth-framework §8 后续，见任务报告 concerns）。
- `fetch_asset`（FETCH）：`HttpClient.stream` Article Retrieval API（`httpAccept` query 定
  PDF/XML——冻结 `stream()` 不暴露 `Accept` 头，故格式经 query 参数，[DOCS]）→ `io.write_stream`；
  `%PDF` 魔数 + bytes>0 校验归 pipeline（XML source expected_type=text/xml 跳魔数）。
- `healthcheck`：**无 key → `NotImplementedError`**（→canary SKIP，B-M4 钉死，复用 s2/openalex
  先例，零 canary 改动）；有 key → 已知 JFE DOI 的 entitlement 探测（真值 [PENDING]，BLOCKER-1
  待 T7b 捕获）。

**凭证隔离红线**（§3.2）：`X-ELS-APIKey`(+`X-ELS-Insttoken`) 经**专属** `HttpClient`
（client 级附加头）由装配期注入——**绝不复用跨 adapter 共享 client**（携密头随他域外泄属
凭证红线，沿 openreview/s2 先例，见 `set_http_client` docstring）。本 adapter 自身不做头注入、
不读明文 key（只经 `set_api_key` 记录"是否已配置"用于 AuthRequired/SKIP 判定分支）。

**429 保守化**（B-M2，§5）：**任意认证态 429**（keyless `RATE_LIMIT_EXCEEDED` / 认证态
`QUOTA_EXCEEDED`）→ `RATE_LIMITED` + **当日熔断**（`_circuit`——本进程内同日后续请求短路，
不再触网）。**不靠 `X-ELS-Status` 真值分流行为**（认证态真值不可活验，只入 detail 作观测）。
`403` 重分类 `AUTH_EXPIRED`（elsevier API 403 = key/insttoken 失效，非"有权探否"——后者经
entitlement 端点 200+entitled:false 判定，§5；沿 openreview 403→auth_expired 重分类先例）。
"""

from __future__ import annotations

import os
from datetime import date
from urllib.parse import quote, urlencode

from paper_crawler.adapter import AdapterBase, AdapterFamily
from paper_crawler.adapters.elsevier_sd import parse
from paper_crawler.errors import AuthRequired, CrawlerError, ErrorClass
from paper_crawler.http import HttpClient
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

# --- 端点与常量（elsevier-sd.md §3/§4）--------------------------------------------------------

_API_ROOT = "https://api.elsevier.com/content"

_CONTACT_EMAIL_ENV = "PAPER_CRAWLER_CONTACT_EMAIL"
# RFC 2606 保留 .invalid：惰性自建（无注入专属 client）时的占位 UA 联系人。真实带 key 抓取
# 走装配期注入的携 `X-ELS-APIKey` 头专属 client（沿 s2/openreview 先例）。
_PLACEHOLDER_EMAIL = "anonymous@paper-crawler.invalid"

# venue quirk 键：置真时 resolve 额外产 XML 全文标记版 SOURCE AssetPlan（§3.1"可选同存"；
# extract 阶段免 OCR 之利）。**默认关**——PDF 优先，避免每篇双取空转；PDF vs XML 逐刊
# 可得性 ⚠[DOCS] 待 T7b 真实 key 核验（elsevier-sd.md §2 待核验项）。
_QUIRK_WANT_XML = "elsevier_want_xml_source"

# healthcheck 锚点：真实 JFE DOI（Journal of Financial Economics；已见 tests/unit/
# test_auth_protocol.py 作 elsevier 端点范例，全库一致识别号）。**entitled 真值 [PENDING]**
# ——BLOCKER-1：无 key 无法活验本 DOI 的 entitlement，捕获前作结构性探测（entitlement 端点
# 可达且封套可解析即健康，detail 附实测 entitled 供 T7b UPDATE_GOLDEN 捕获）。
_HEALTHCHECK_DOI = "10.1016/j.jfineco.2011.03.021"
_HEALTHCHECK_EXPECT_ENTITLED: bool | None = None


def _default_user_agent() -> str:
    email = os.environ.get(_CONTACT_EMAIL_ENV, "").strip() or _PLACEHOLDER_EMAIL
    return build_user_agent(email)


def _entitlement_url(doi: str) -> str:
    """entitlement 预检端点：`/content/article/entitlement/doi/{doi}`（get_bytes accept=JSON）。"""
    return f"{_API_ROOT}/article/entitlement/doi/{quote(doi, safe='/')}"


def _article_url(doi: str, http_accept: str) -> str:
    """Article Retrieval 全文端点：`/content/article/doi/{doi}?httpAccept=<fmt>`。

    格式（pdf/xml）经 `httpAccept` query 参数指定——冻结 `HttpClient.stream()` 不暴露单请求
    `Accept` 头覆盖，Elsevier API 支持等效的 `httpAccept` query（[DOCS]）。key 绝不入 query
    （随专属 client 的 `X-ELS-APIKey` 头承载，凭证不入 URL/日志，红线）。
    """
    return (
        f"{_API_ROOT}/article/doi/{quote(doi, safe='/')}?{urlencode({'httpAccept': http_accept})}"
    )


def _doi_of(paper: PaperStub) -> str:
    """从 stub 取 DOI（scheme='doi'）；缺失 → CONFIG（路由缺陷——elsevier 只按 DOI resolve）。"""
    for scheme, value in paper.identifiers:
        if scheme == "doi":
            return value
    raise CrawlerError(
        ErrorClass.CONFIG,
        f"elsevier_sd resolve_assets needs a doi identifier: {paper.identifiers!r}",
    )


def _wants_xml_source(venue: VenueSpec) -> bool:
    return bool(venue.quirks.get(_QUIRK_WANT_XML))


class ElsevierScienceDirectAdapter(AdapterBase):
    """Elsevier ScienceDirect adapter（`auth_gated`/官方 API；JFE 等 15+ 刊，NFR-1 杠杆）。"""

    adapter_id = "elsevier_sd"
    family: AdapterFamily = "auth_gated"
    capabilities = Capability.RESOLVE | Capability.FETCH
    # §4：自限 2 req/s（=120 req/min，远离官方 10 req/s，留余量给交互式使用）；动态读
    # `X-RateLimit-*` 头在冻结 `HttpClient.get_bytes`（不暴露响应头）下不可达——退化为静态
    # 保守上限 + 429→rate_limited 当日熔断（沿 crossref/openalex 同款裁决）。
    default_rate = RatePolicy(
        requests_per_minute=120.0,
        burst=1,
        source_note=(
            "Elsevier Article API 自限 2 req/s（官方 10 req/s / 50k 周，留余量）；"
            "动态读 X-RateLimit-* 受冻结 HttpClient.get_bytes 不暴露 headers 所限、"
            "退化为静态上限 + 429 当日熔断；elsevier-sd.md §4 [LIVE 2026-07-20]"
        ),
    )
    auth_requirement = AuthLevel.INSTITUTIONAL
    domains: tuple[str, ...] = ("api.elsevier.com",)
    # resolve_assets 发真实网络请求（entitlement 预检）→ 不满足 `resolve_offline` 零网络契约，
    # 保留继承默认 False（resolve 阶段仍过限速闸，同 unpaywall 网络 resolve 先例）。

    def __init__(self, http: HttpClient | None = None) -> None:
        # http=None：首次网络调用惰性自建（匿名——但 resolve/fetch 先经 `_require_api_key`
        # 拦截，healthcheck 先判 key；无 key 分支绝不触网）。带 key 抓取走装配期注入的专属 client。
        self._http = http
        self._api_key: str | None = None
        # 当日熔断状态（B-M2）：置为某日后，同日后续 resolve/fetch 短路为 RATE_LIMITED、不触网。
        # 进程内状态——一次 pull run 即一个进程，覆盖单次运行的保守熔断；跨进程持久化（openalex
        # state-file 口径）为文档化扩展点，BLOCKER-1 下配额真值不可活验、暂不引入。
        self._circuit_open_date: date | None = None

    def set_http_client(self, client: HttpClient) -> None:
        """注入组装好的 `HttpClient`（`adapter.HttpClientConsumer` 协议）。

        **凭证隔离义务在调用方**（装配期）：有 key 时必须注入携 `X-ELS-APIKey`
        (+ 可选 `X-ELS-Insttoken`) 头的**专属** client，绝不把跨 adapter 共享的匿名 client
        传入——否则携密头随其它域（crossref/dblp/...）请求外泄（凭证红线，沿 openreview/s2
        先例）。本方法不校验传入 client 是否携正确头（无法从 `HttpClient` 反读其内部头），
        信任调用方遵守隔离约定。
        """
        self._http = client

    def set_api_key(self, key: str | None) -> None:
        """注入可选 API key（`adapter.ApiKeyConsumer` 协议）。

        只记录 key 值本身（供 `resolve_assets` 的 `AuthRequired` 分支、`healthcheck` 的
        `NotImplementedError`→SKIP 分支判定"是否已配置"），**不**据此改动 `self._http` 的
        请求头——`X-ELS-APIKey` 头必须随专属 client 的构造一次性注入（见 `set_http_client`），
        与本方法的调用顺序由装配方保证（先构造携正确头的专属 client 再注入）。
        """
        self._api_key = key

    def _client(self) -> HttpClient:
        if self._http is None:
            self._http = HttpClient(user_agent=_default_user_agent())
        return self._http

    def _require_api_key(self) -> None:
        """无 key → `AuthRequired`（BLOCKER-1 离线分支，§3.1）：整批 BLOCKED(auth)，提示配 key。"""
        if not self._api_key:
            raise AuthRequired(
                "elsevier api_key 未配置",
                detail="配置 [auth.elsevier].api_key 或 env PAPER_CRAWLER_ELSEVIER_API_KEY；"
                "随后 `crawler auth login elsevier`",
            )

    def _guard_circuit(self) -> None:
        """当日熔断已开（同日曾见 429）→ 直接 `RATE_LIMITED`、不触网（B-M2 保守化）。"""
        if self._circuit_open_date == date.today():
            raise CrawlerError(
                ErrorClass.RATE_LIMITED,
                "elsevier 当日 429 熔断已开（B-M2 保守化）：同日不再请求，明日或配额重置后恢复",
                detail="circuit_open",
            )

    def _handle_network_error(self, exc: CrawlerError) -> CrawlerError:
        """网络错误统一后处理（§5 失败模式映射）：429 当日熔断 + 403 重分类 auth_expired。

        - **任意 429**（HttpClient 已映射 RATE_LIMITED + 携 Retry-After 入 detail）→ 置当日熔断
          （B-M2）；**不靠 `X-ELS-Status` 真值分流**（认证态真值不可活验），error 封套 error-code
          仅可入 detail 作观测、不改处置。原样透传 RATE_LIMITED（class/detail 已正确）。
        - **403** → 重分类 `AUTH_EXPIRED`（elsevier API 403 = key/insttoken 失效；"有权探否"
          走 entitlement 端点 200+entitled:false，§5）→ 整批 BLOCKED(auth)。沿 openreview 先例。
        - 其余（401→auth_expired / 404,410→gone / 5xx→transient / 400→config）原样透传
          （HttpClient 冻结映射已正确）。
        """
        if exc.status_code == 429 or exc.error_class is ErrorClass.RATE_LIMITED:
            self._circuit_open_date = date.today()
            return exc
        if exc.status_code == 403:
            return CrawlerError(
                ErrorClass.AUTH_EXPIRED,
                f"elsevier 403 (invalid api_key/insttoken; reclassified): {exc}",
                detail="elsevier_auth",
                status_code=exc.status_code,
            )
        return exc

    # -- resolve（真实网络：entitlement 预检 → AssetPlan / no_entitlement）---------------------

    def resolve_assets(
        self, venue: VenueSpec, paper: PaperStub, session: SessionHandle | None = None
    ) -> list[AssetPlan]:
        """entitlement 预检 → 有权产 PDF(+可选 XML) plan / 无权 `raise NO_ENTITLEMENT`（§3.1）。

        无 key → `AuthRequired`（触网前拦截，离线单测断言此分支）。`session` 未使用（凭证经注入
        专属 client 承载，非 session 参数——冻结协议签名要求；AuthProvider session 装配归 T5）。
        """
        self._require_api_key()
        self._guard_circuit()
        doi = _doi_of(paper)
        try:
            data = self._client().get_bytes(_entitlement_url(doi), accept="application/json")
        except CrawlerError as exc:
            raise self._handle_network_error(exc) from exc
        decision = parse.parse_entitlement(data, doi=doi)
        if not decision.entitled:
            # AC-4.3：无权不产平台 AssetPlan、标 no_entitlement（status_code=200——判定源于
            # 200 响应体语义，非 HTTP 状态；转 unpaywall OA-fallback 归 auth-framework §8）。
            raise CrawlerError(
                ErrorClass.NO_ENTITLEMENT,
                f"elsevier: no entitlement for {doi} (status={decision.status!r})",
                detail="no_entitlement",
                status_code=200,
            )
        plans = [
            AssetPlan(
                kind=AssetKind.PDF,
                url=_article_url(doi, "application/pdf"),
                expected_type="application/pdf",
                url_strategy=UrlStrategy.API_CALL,
                auth_needed=AuthLevel.INSTITUTIONAL,
                version=None,
            )
        ]
        if _wants_xml_source(venue):
            plans.append(
                AssetPlan(
                    kind=AssetKind.SOURCE,
                    url=_article_url(doi, "text/xml"),
                    expected_type="text/xml",
                    url_strategy=UrlStrategy.API_CALL,
                    auth_needed=AuthLevel.INSTITUTIONAL,
                    version=None,
                )
            )
        return plans

    # -- fetch（流式，携注入专属 client 的 X-ELS-APIKey 头）------------------------------------

    def fetch_asset(
        self, plan: AssetPlan, io: FetchIO, session: SessionHandle | None = None
    ) -> FetchResult:
        """`stream` Article API（httpAccept query 定 PDF/XML）→ `io.write_stream`（§3.2）。

        无 key → `AuthRequired`（防御，正常态 resolve 先拦）；当日熔断开 → RATE_LIMITED 短路。
        429→当日熔断、403→auth_expired 经 `_handle_network_error`。`%PDF` 魔数 + bytes>0 权威
        校验在 pipeline（冻结分工）——空壳（魔数/大小失败）→ pipeline 标 INTEGRITY（§5）。
        """
        self._require_api_key()
        self._guard_circuit()
        try:
            stream = self._client().stream(plan.url)
            bytes_written, sha256 = io.write_stream(stream)
        except CrawlerError as exc:
            raise self._handle_network_error(exc) from exc
        return FetchResult(ok=True, bytes_written=bytes_written, sha256=sha256)

    # -- healthcheck（key 门控；有 key → entitlement 探测）------------------------------------

    def healthcheck(self, session: SessionHandle | None = None) -> HealthReport:
        """无 key → `NotImplementedError`（→canary SKIP，B-M4）；有 key → JFE DOI entitlement 探测。

        真值 [PENDING]（`_HEALTHCHECK_EXPECT_ENTITLED=None`，BLOCKER-1 待 T7b 捕获）：结构性探测
        ——entitlement 端点可达且封套可解析即健康，detail 附实测 entitled 供 UPDATE_GOLDEN 捕获。
        捕获后（置真值）转精确 drift 比对。**不**豁免熔断/不预判 429——探测意在活体触达。
        """
        if not self._api_key:
            raise NotImplementedError("elsevier api_key 未配置")
        try:
            data = self._client().get_bytes(
                _entitlement_url(_HEALTHCHECK_DOI), accept="application/json"
            )
        except CrawlerError as exc:
            return HealthReport(
                healthy=False, detail=f"elsevier unreachable ({exc.error_class.value}): {exc}"
            )
        try:
            decision = parse.parse_entitlement(data, doi=_HEALTHCHECK_DOI)
        except CrawlerError as exc:
            return HealthReport(healthy=False, detail=f"entitlement parse failed: {exc}")

        if _HEALTHCHECK_EXPECT_ENTITLED is None:
            return HealthReport(
                healthy=True,
                detail=(
                    f"[PENDING golden] observed entitled={decision.entitled} "
                    f"status={decision.status!r} (doi={_HEALTHCHECK_DOI})"
                ),
            )
        if decision.entitled is not _HEALTHCHECK_EXPECT_ENTITLED:
            return HealthReport(
                healthy=False,
                detail=(
                    f"canary drift — entitled={decision.entitled} != "
                    f"expected {_HEALTHCHECK_EXPECT_ENTITLED} (doi={_HEALTHCHECK_DOI})"
                ),
            )
        return HealthReport(
            healthy=True, detail=f"entitlement canary matched (entitled={decision.entitled})"
        )

    # `discover_timeline`/`enumerate_issue` 未声明能力（capabilities 仅 RESOLVE|FETCH——enumerate
    # 走 crossref，D-005）——不覆写，沿用 `AdapterBase` 默认 `CapabilityNotSupported`。


__all__ = ["ElsevierScienceDirectAdapter"]
