"""Wiley Online Library `SourceAdapter` 主体（design/adapters/wiley.md，实现级；D-024）。

**family=`auth_gated`，capabilities=`RESOLVE | FETCH`**（enumerate 走 crossref，DOI 前缀
`10.1111`/`10.1002`/`10.3982` 由 `parse.is_wiley_doi` 甄别）。推荐档 = **TDM API 优先**
（`GET api.wiley.com/onlinelibrary/tdm/v1/articles/{DOI}` + `Wiley-TDM-Client-Token` 头
→ 全文 PDF，wiley.md §2 [LIVE 2026-07-23]）。

**token 门控 skip（D-024，s2 先例）**：Wiley TDM token 自助可得但 entitlement 受机构订阅
约束；现状 config/env **无 token**。故：
- `resolve_assets`/`fetch_asset` 无 token → `raise AuthRequired`（detail 含配置指引
  `[auth.wiley] token`）→ runner 路由 BLOCKED(auth)，**不发任何真实请求**（离线 fixture 覆盖）。
- `healthcheck` 无 token → `raise NotImplementedError` → canary SKIP（与 fetch 的
  `AuthRequired`→BLOCKED 二义分离，auth-framework §7 B-M4；复用 s2/canary 既有 SKIP 分支）。

**凭证隔离红线（wiley.md §3.2）**：`Wiley-TDM-Client-Token` 头必须随**专属** `HttpClient`
的构造一次性注入（`extra_headers={"Wiley-TDM-Client-Token": <token>}`），**绝不复用跨
adapter 共享的 client**——否则该 token 头会随其它域（crossref/dblp/...）的请求外泄
（沿 openreview cookie / s2 `x-api-key` 专属 client 先例）。**隔离义务在调用方**（CLI 装配
期的 `_bind_wiley_token_client` 类比 `_bind_openreview_token_client`——本 T-wiley 交付面
不含该 CLI 接线，属"token 到位后"的已知 union 点）：`set_http_client` 只接收组装好的专属
client，`set_token` 只记录 token 值本身（供门控判定"是否已配置"），**不**据此改动
`self._http` 的请求头。单测/在线冒烟各自构造携头专属 client 注入，验证行为正确。

**错误映射（wiley.md §5）经 `HttpClient` 冻结映射**：TDM host 返回结构化错误（非挑战页，
R0 印证），故 401→`auth_expired`、403→`no_entitlement`（订阅域约束语义）、429→`rate_limited`
（`HttpClient` 已解析 `Retry-After` 入 detail）均由 `HttpClient._error_for_status` 原样
产出，本层透传不重分类。Cloudflare 质询（`cf-mitigated: challenge`）是**页面兜底路径**
（`onlinelibrary.wiley.com` + BrowserFetcher）现象——TDM httpx 路径不暴露响应头故无从
在此判头级质询；healthcheck 探针对**质询页 body** 特征（"just a moment"/`challenge-platform`）
经 `ChallengeDetector` 判定，页面兜底的头级质询检测随 BrowserFetcher 落地（deferred，§3.2）。

**双窗口限速（wiley.md §4 接缝结论）**：3 req/s 瞬时 + 60/10min 滑动 → 现有单 token bucket
可表达，无需扩展冻结 `ratelimit.py`。起步保守 `RatePolicy(rpm=5, burst=3)`——60/10min≈6rpm
是绝对主导约束（3req/s 跑满则 20s 耗尽 10min 预算），取 rpm=5 令长程速率 ≤ 滑动窗均值并留
1/min 头寸，burst=3 令任意瞬时至多 3 连发（第 4 请求需等 60/5=12s）。实测真实 429 后按
wiley.md 既有"起步保守、观测后调"纪律放宽。
"""

from __future__ import annotations

from paper_crawler.adapter import AdapterBase, AdapterFamily
from paper_crawler.adapters.wiley import parse
from paper_crawler.auth.challenge import ChallengeDetector, ClassifyResult
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

# TDM token 请求头名（wiley.md §2；搜索索引原文 "passing your Clickthrough Client token as
# the value of the `Wiley-TDM-Client-Token` header"，R0 [LIVE 2026-07-23] 复核一致）。
TDM_TOKEN_HEADER = "Wiley-TDM-Client-Token"

# 无 token 门控的配置指引（AuthRequired detail；wiley.md §3.1）。
_AUTH_HINT = "[auth.wiley] token"

# healthcheck 探针锚点 DOI（⚠[PENDING token-verify]）：无 token 时 healthcheck 早退
# NotImplementedError → 本常量在有 token 前**从不被使用**。有 token 后须由操作者按
# tests/manual/wiley_runbook.md「首取步骤」核准为一个已知可取回（理想：开放获取，
# 只需 token 连通、不依赖机构订阅）的 Wiley DOI 后落定；当前取 Journal of Finance
# 形态占位，标注 [PENDING]，绝不宣称已活验。
_HEALTHCHECK_DOI = "10.1111/jofi.13123"


class WileyAdapter(AdapterBase):
    """Wiley Online Library adapter（`auth_gated` family；RESOLVE | FETCH，TDM API 优先）。"""

    adapter_id = "wiley"
    family: AdapterFamily = "auth_gated"
    capabilities = Capability.RESOLVE | Capability.FETCH
    # 双窗口限速映射（wiley.md §4 接缝结论——单桶可表达，起步保守）。
    default_rate = RatePolicy(
        requests_per_minute=5.0,
        burst=3,
        source_note=(
            "Wiley TDM: 3 req/s(瞬时→burst=3) + 60/10min(滑动均值→≈6rpm, 绝对主导约束)；"
            "起步保守 rpm=5/burst=3（≤滑动窗均值 + 留 1/min 头寸；第 4 连发等 60/5=12s），"
            "实测真实 429 后按 wiley.md 纪律放宽；docs/design/adapters/wiley.md §4 "
            "[LIVE 2026-07-23]（R0 端点/头/速率活验）"
        ),
    )
    # TDM token + 机构订阅域 → institutional（AssetPlan.auth_needed 同级，wiley.md §1/§3.1）。
    auth_requirement = AuthLevel.INSTITUTIONAL
    # 主干 = TDM API host（wiley.md §1）。页面兜底域 `onlinelibrary.wiley.com`（独立桶
    # 1req/6s + 日配额 200，§4）随 BrowserFetcher 落地（deferred，§3.2）——本交付只声明
    # 已实现的 TDM 主干域，不挂一个当前无取回代码的死域（避免其被 alias 归并进 TDM 桶）。
    domains: tuple[str, ...] = ("api.wiley.com",)
    # resolve_assets 是**可证明零网络**的纯 URL 构造（有 token → 拼 TDM URL；无 token →
    # raise AuthRequired），故豁免 resolve 阶段 per-domain 限速闸（同 arxiv/openreview 纯
    # 构造式 resolve 先例）。真实网络只发生在 fetch_asset/healthcheck（非 offline，仍走闸）。
    resolve_offline: bool = True

    def __init__(self, http: HttpClient | None = None, *, token: str | None = None) -> None:
        # http=None：首次网络调用时惰性自建（无 token 时 resolve/fetch/healthcheck 均在触网
        # 前门控早退，不会走到惰性自建）。token 经 set_token 或构造注入，仅供门控判定。
        self._http = http
        self._token = token

    # -- 依赖注入协议（HttpClientConsumer + wiley 专属 token setter）--------------------------

    def set_http_client(self, client: HttpClient) -> None:
        """注入组装好的 `HttpClient`（`adapter.HttpClientConsumer` 协议）。

        **凭证隔离义务在调用方**（CLI 装配期）：有 token 时必须注入携 `Wiley-TDM-Client-Token`
        头的**专属** client，不得把跨 adapter 共享的匿名 client 传入——本方法自身不校验传入
        client 是否携带正确的头（无法从 `HttpClient` 反读其内部头，同 s2/openreview 既有限制），
        信任调用方遵守模块 docstring 的隔离约定。
        """
        self._http = client

    def set_token(self, token: str | None) -> None:
        """注入 TDM client token（供 `resolve_assets`/`fetch_asset`/`healthcheck` 门控判定）。

        本方法**只记录 token 值本身**（判定"是否已配置"），**不**据此改动 `self._http` 的请求头
        ——`Wiley-TDM-Client-Token` 头必须随专属 client 的构造一次性注入（见 `set_http_client`
        docstring），本方法与 `set_http_client` 的调用顺序在装配侧由调用方保证一致（先构造好
        携正确头的专属 client 再注入）。空白串归一为"未配置"（等价未提供，同全库 token 口径）。
        """
        self._token = token.strip() if isinstance(token, str) else token

    def _client(self) -> HttpClient:
        if self._http is None:
            self._http = HttpClient(user_agent=build_user_agent(None))
        return self._http

    def _has_token(self) -> bool:
        return bool(self._token and self._token.strip())

    def _require_token(self, action: str) -> None:
        """无 token → `AuthRequired`（detail 含 `[auth.wiley] token` 配置指引，wiley.md §3.1）。"""
        if not self._has_token():
            raise AuthRequired(
                f"wiley {action} 需要 TDM token（未配置）；请配 {_AUTH_HINT} "
                "或 `crawler auth login wiley`（token 自助获取见 tests/manual/wiley_runbook.md）",
                detail=_AUTH_HINT,
            )

    # -- RESOLVE（零网络：门控 + 纯 URL 构造）-------------------------------------------------

    def resolve_assets(
        self, venue: VenueSpec, paper: PaperStub, session: SessionHandle | None = None
    ) -> list[AssetPlan]:
        """`paper` 的 DOI → 1 个 TDM `AssetPlan`（wiley.md §3.1）。无 token → `AuthRequired`。

        `venue` 未被使用（TDM 按 DOI 取回，不读 venue 层配置——同 unpaywall 跨 venue 先例，
        冻结协议签名要求保留形参）。首选 TDM 主干（`url_strategy=API_CALL`,
        `auth_needed=INSTITUTIONAL`）；页面兜底档（onlinelibrary 直链 + cookie）随
        BrowserFetcher 落地（deferred，§3.2），本层不产不可取回的兜底 plan（诚实：不承诺
        当前无 FETCH 支撑的路径）。
        """
        self._require_token("resolve_assets")
        doi = _doi_of(paper)
        return [
            AssetPlan(
                kind=AssetKind.PDF,
                url=parse.tdm_article_url(doi),
                expected_type="application/pdf",
                url_strategy=UrlStrategy.API_CALL,
                auth_needed=AuthLevel.INSTITUTIONAL,
            )
        ]

    # -- FETCH（真实网络：专属 client stream → io.write_stream）-------------------------------

    def fetch_asset(
        self, plan: AssetPlan, io: FetchIO, session: SessionHandle | None = None
    ) -> FetchResult:
        """TDM 端点流式取回 → `io.write_stream`（wiley.md §3.2）。无 token → `AuthRequired`。

        `self._client()` 须为携 `Wiley-TDM-Client-Token` 头的**专属** client（隔离义务在装配
        方，见模块/`set_http_client` docstring）。`%PDF` **权威**校验归 pipeline（冻结分工，
        arxiv 先例）——本层只把流交 `io.write_stream`。错误状态经 `HttpClient` 冻结映射
        （401→auth_expired / 403→no_entitlement / 429→rate_limited(读 Retry-After)）原样
        `raise`，不重分类（wiley.md §5）。
        """
        self._require_token("fetch_asset")
        stream = self._client().stream(plan.url)
        bytes_written, sha256 = io.write_stream(stream)
        return FetchResult(ok=True, bytes_written=bytes_written, sha256=sha256)

    # -- healthcheck（token 门控 + TDM 连通探针）----------------------------------------------

    def healthcheck(self, session: SessionHandle | None = None) -> HealthReport:
        """无 token → `NotImplementedError`（→canary SKIP）；有 token → TDM 探针判 PDF/质询。

        有 token：对锚点 DOI 的 TDM 端点取**首个数据块**（不整篇下载）——`%PDF` 魔数 → healthy；
        非 PDF 且 body 命中 Cloudflare 质询特征（`ChallengeDetector`）→ unhealthy(challenge)；
        其余非 PDF → unhealthy；网络/状态错误经 `HttpClient` 映射 → unhealthy（携 error_class）。
        锚点 DOI 为 [PENDING token-verify] 占位，须按 runbook 首取时核准（模块常量注释）。
        """
        if not self._has_token():
            raise NotImplementedError("wiley token 未配置")
        url = parse.tdm_article_url(_HEALTHCHECK_DOI)
        try:
            first = self._probe_first_bytes(url)
        except CrawlerError as exc:
            return HealthReport(
                healthy=False,
                detail=f"wiley TDM unreachable ({exc.error_class.value}): {exc}",
            )
        if parse.looks_like_pdf(first):
            return HealthReport(
                healthy=True,
                detail=f"[PENDING token-verify] TDM returned PDF for {_HEALTHCHECK_DOI}",
            )
        # 非 PDF：区分质询页（body 特征）与其它非预期内容（伪装页 → pipeline integrity 语义）。
        verdict = ChallengeDetector().classify(status=200, headers={}, final_url=url, body=first)
        if verdict is ClassifyResult.CHALLENGE:
            return HealthReport(
                healthy=False,
                detail=f"wiley TDM probe hit a challenge page (not PDF) for {_HEALTHCHECK_DOI}",
            )
        return HealthReport(
            healthy=False,
            detail=f"wiley TDM probe returned non-PDF content for {_HEALTHCHECK_DOI}",
        )

    def _probe_first_bytes(self, url: str) -> bytes:
        """流式取首个数据块即停（healthcheck 探针：验连通/PDF，不整篇下载）。

        首个数据块触发请求 + `HttpClient` 状态判定（≥400 → `CrawlerError`）；取到即 `return`，
        未消费尽的生成器由 CPython 引用计数在函数帧销毁时即时 `close`（触发底层 `httpx.stream`
        上下文清理，同 arxiv `_gone_guarded_stream` 之外的轻探针取舍）。空响应 → `b""`
        （下游 `looks_like_pdf` 判 False）。
        """
        for chunk in self._client().stream(url):
            return chunk
        return b""


def _doi_of(paper: PaperStub) -> str:
    """从 stub 取 DOI（scheme='doi'）；缺失 → CONFIG（路由缺陷——wiley 只按 DOI resolve，
    同 unpaywall `_doi_of` 先例）。"""
    for scheme, value in paper.identifiers:
        if scheme == "doi":
            return value
    raise CrawlerError(
        ErrorClass.CONFIG,
        f"wiley resolve_assets needs a doi identifier: {paper.identifiers!r}",
    )


__all__ = ["TDM_TOKEN_HEADER", "WileyAdapter"]
