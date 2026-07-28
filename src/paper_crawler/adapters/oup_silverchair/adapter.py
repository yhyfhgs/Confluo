"""OUP（Silverchair 平台）`SourceAdapter` 主体（design/adapters/oup-silverchair.md）。

family=`auth_gated`（推荐档 **HTTP + session cookie**，design/04 §3 第 2 档）。能力
``RESOLVE | FETCH``——enumerate/discover 走 crossref（DOI 前缀 10.1093，metadata_source
分离）。服务 QJE/REStud/RFS/Review of Finance/EJ 等 OUP 顶刊（一 adapter 覆盖 5+，
经济金融密度最高平台）。

**登录 session 态为工作前提**（design §2 红线）：匿名 GET OUP 文章页恒撞 Cloudflare
`403 cf-mitigated: challenge`（R0 [LIVE 2026-07-23]）——挑战即 BLOCKED、**绝不对抗**
（AGENTS §6 / AC-0.2 / AC-4.6）。故 `resolve`/`fetch` 无 session → `AuthRequired`。

--- cookie 供给 seam（T1b 合并前的最小 duck-typed 接缝）--------------------------------

**一句话**：`fetch`/`resolve` 经**可注入的 cookie 供给函数** `CookieSupplier` 把
`SessionHandle` 换成 cookie jar（name→value），adapter 用该 jar 构造**专属** httpx
client 直取；真实供给（读 `CredentialStore` 解密 storage_state）由 T1b 落地、pipeline
装配期经 `set_cookie_supplier` 注入。本 Phase 未合并 T1b，故：

- 生产装配：`load_adapters()` 无参实例化 → supplier=None；pipeline（T1b 后）
  `set_cookie_supplier(real)` 注入（duck-typed，仿 `HttpClientConsumer`/`EmailConsumer`
  先例，不进 `SourceAdapter` 冻结协议）。
- 离线测试：构造期直接注入 `cookie_supplier=` + `transport=`（httpx.MockTransport），
  零真实网络（同 HttpClient 的 transport 注入通道先例）。

**为何不复用共享 `HttpClient`**：①凭证隔离红线——cookie 必须挂在**携密专属 client**，
绝不复用共享 client（否则外泄他站，plan §7-4）；②`ChallengeDetector` 需读 **403 落地页
的 headers+body** 才能四态分类，而共享 `HttpClient` 在 ≥400 处即 `raise` 会吞掉 body
（S-c/D-030 后它已能凭 `cf-mitigated` 头独立判出 CHALLENGE，但 LOGIN_REDIRECT /
NO_ENTITLEMENT / OK 三态仍须 body，理由不变）。故本 adapter 用专属 `httpx.Client`（UA+
domain 限定 cookie jar + follow_redirects），GET 后返回**原始响应视图**（不在 4xx 处
raise），交 `ChallengeDetector` 事后判读（design §5）。详设 §3.2 措辞"专属 HttpClient"
即此专属 client（同构：UA+Cookie+跟随重定向），实现上因上述②改用裸 httpx。

**联系邮箱 seam**（R2c 修复；同 unpaywall 先例）：`_authed_get` 的 UA 经
`useragent.build_user_agent` 统一组装，邮箱取 `_resolve_email()`——显式 `set_email`（CLI
装配期注入 `Config.identity_email`，`adapter.EmailConsumer` 协议）> 环境变量
`PAPER_CRAWLER_CONTACT_EMAIL` > `.invalid` 占位。修复前本模块恒读 env、CLI 无 seam 可挂，
oup（唯一订阅站 UA）因此恒匿名占位，违反 useragent.py 的礼貌联系人政策；现与
arxiv/openreview/unpaywall 等其余真实 adapter 同一套注入纪律。`_authed_get` 同时补一条
per-request obslog DEBUG 事件（`stage`/`domain`/`url`/`status`，见其 docstring）——
resolve/fetch/healthcheck 三调用点经此方法唯一收口，一处埋点全覆盖。

**限速**：resolve/fetch 每方法恰 1 个逻辑请求（doi.org→落地页跟随重定向 = 单请求；
article-pdf 直取 = 单请求），由 pipeline 的 per-stage `acquire_and_wait` 依 `default_rate`
（1 req/6s，design §4）逐阶段限速——同 cvf 先例（"实际限速由 pipeline，不在本 adapter"）。
日配额 200 按 fetch 尝试篇次计（resolve 页请求不计，design §4 A-M5）——落库口径归 pipeline。

**cookie 域限定**（凭证红线 + 防 doi.org 泄漏）：供给的 cookie 一律 `domain=academic.oup.com`
主域限定 → resolve 的 `GET doi.org/{doi}` 首跳**不带** cookie（不泄漏给 DOI 解析器），
仅重定向落到 academic.oup.com 后才随请求发出。
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping

import httpx

from paper_crawler.adapter import AdapterBase, AdapterFamily
from paper_crawler.adapters.oup_silverchair import parse
from paper_crawler.auth.challenge import ChallengeDetector, ClassifyResult
from paper_crawler.errors import AuthRequired, Challenged, CrawlerError, ErrorClass
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

# --- 端点与常量（design §2/§3）----------------------------------------------------------------

_PRIMARY_DOMAIN = "academic.oup.com"
_DOI_RESOLVER = "https://doi.org"
# 探针页（design §3.3；⚠ controller 亲读②：R0 无凭证未实测该路径——真实 URL 待 runbook
# 首登核验，profiles `probe_url` 可覆盖。healthcheck 无 venue 形参，故此为类级默认）。
_PROBE_URL = f"https://{_PRIMARY_DOMAIN}/my-account"

# DOI identifier scheme（ids.DOI_SCHEME；crossref 产出的 (scheme,value) 键名）。
_DOI_SCHEME = "doi"
# OUP DOI 前缀（design §1；仅用于诊断消息，不做硬门控——crossref 已按 venue 路由）。
_OUP_DOI_PREFIX = "10.1093/"

_CONTACT_EMAIL_ENV = "PAPER_CRAWLER_CONTACT_EMAIL"
# RFC 2606 保留 .invalid：显式注入（`set_email`）与 env 皆缺时的占位联系人（先例
# cvf/arxiv/unpaywall）。R2c 修复前本模块恒读 env、CLI 无 seam 可挂 `Config.identity_email`
# ——oup（唯一订阅站 UA）因此恒匿名占位；现比照 unpaywall 补 `set_email`/`_resolve_email`。
_PLACEHOLDER_EMAIL = "anonymous@paper-crawler.invalid"

# cookie 供给 seam：SessionHandle → cookie name→value 映射（见模块 docstring）。
CookieSupplier = Callable[[SessionHandle], Mapping[str, str]]


def _default_email() -> str:
    """env 兜底邮箱：`PAPER_CRAWLER_CONTACT_EMAIL` 非空则用之，否则 `.invalid` 占位
    （同 unpaywall `_default_email` 先例）。"""
    return os.environ.get(_CONTACT_EMAIL_ENV, "").strip() or _PLACEHOLDER_EMAIL


class _RawResponse:
    """专属 client GET 的原始响应视图（**不在 4xx 处 raise**，供 ChallengeDetector 判读）。

    只承载 `ChallengeDetector.classify` 的四入参 + fetch 的魔数校验所需字节——刻意不
    暴露 httpx.Response（避免连接/流未释放的隐患，字节已在 `_authed_get` 内读全）。
    """

    __slots__ = ("status", "headers", "final_url", "body")

    def __init__(self, *, status: int, headers: Mapping[str, str], final_url: str, body: bytes):
        self.status = status
        self.headers = dict(headers)
        self.final_url = final_url
        self.body = body


class OupSilverchairAdapter(AdapterBase):
    """OUP Silverchair adapter（`auth_gated`，RESOLVE|FETCH）。"""

    adapter_id = "oup_silverchair"
    family: AdapterFamily = "auth_gated"
    capabilities = Capability.RESOLVE | Capability.FETCH
    # design §4：串行 1 req/6s = 10 rpm、并发 1；source_note 出处强制（types.RatePolicy）。
    default_rate = RatePolicy(
        requests_per_minute=10.0,
        burst=1,
        source_note=(
            "academic.oup.com: robots.txt (200) has no Crawl-delay and no AI-bot rule; "
            "OUP publishes no TDM rate figure; article/article-pdf paths not disallowed. "
            "Conservative global default 1 req/6s (10 rpm) concurrency-1 per design/04 §4/§5; "
            "anonymous article GET -> 403 cf-mitigated:challenge (login session required). "
            "research/site-survey/publisher-platforms-p4-recheck.md O1/O2 [LIVE] 2026-07-23"
        ),
    )
    # design §2/§4：机构订阅刊，登录 session 态为工作前提。
    auth_requirement = AuthLevel.INSTITUTIONAL
    # 主域 = 限速/日志账本键 + cookie 域限定键（PDF 与落地页同源，单域）。
    domains: tuple[str, ...] = (_PRIMARY_DOMAIN,)

    def __init__(
        self,
        *,
        cookie_supplier: CookieSupplier | None = None,
        transport: httpx.BaseTransport | None = None,
        email: str | None = None,
    ) -> None:
        # cookie_supplier=None：pipeline（T1b 后）经 set_cookie_supplier 注入真实供给；
        # transport=None：生产用 httpx 默认传输，测试注入 MockTransport 达成零真实网络；
        # email=None：CLI 装配期经 set_email 注入 Config.identity_email（`adapter.EmailConsumer`
        # 协议，同 unpaywall 先例，R2c）——未注入时 `_resolve_email` 回退 env
        # `PAPER_CRAWLER_CONTACT_EMAIL` 再退 `.invalid` 占位（修复前恒读 env、无从被 CLI 覆盖）。
        self._cookie_supplier = cookie_supplier
        self._transport = transport
        self._email = email
        self._detector = ChallengeDetector()

    def set_cookie_supplier(self, supplier: CookieSupplier) -> None:
        """注入 cookie 供给函数（duck-typed seam；T1b 后由 pipeline 装配期调用）。"""
        self._cookie_supplier = supplier

    def set_email(self, email: str | None) -> None:
        """注入联系邮箱（`adapter.EmailConsumer` 协议；CLI 装配期传入 `Config.identity_email`，
        同 unpaywall `set_email` 先例，R2c）。"""
        self._email = email

    def _resolve_email(self) -> str:
        """当前生效邮箱：显式注入 > 环境变量 `PAPER_CRAWLER_CONTACT_EMAIL` > `.invalid` 占位
        （同 unpaywall `_resolve_email` 先例）。"""
        return self._email if self._email else _default_email()

    # -- resolve（doi.org→落地页 → ChallengeDetector 分类 → 解析 PDF 链接，design §3.1）-------

    def resolve_assets(
        self, venue: VenueSpec, paper: PaperStub, session: SessionHandle | None = None
    ) -> list[AssetPlan]:
        """DOI → 落地页解析出完整 `article-pdf` URL → `AssetPlan`（design §3.1）。

        流程：① session cookie jar 携带 GET `doi.org/{doi}` 跟随重定向到落地页；
        ② `ChallengeDetector.classify` 先分类（OK 态才解析）；③ 按四态分支：

        - CHALLENGE → `Challenged`（BLOCKED(challenge)+冷却，绝不对抗，AC-0.2/4.6）；
        - LOGIN_REDIRECT（302→signin，无账号标识）→ `AuthRequired`（整批 BLOCKED(auth)）；
        - NO_ENTITLEMENT（article-abstract 路由 / Get access 面板且无全文节点）→
          `CrawlerError(NO_ENTITLEMENT)`（转 unpaywall OA-fallback，design §5/§8.1）；
        - OK → 解析 PDF 链接（citation_pdf_url meta 首选 / article-pdf href 回退）：命中
          → `AssetPlan(PDF, DIRECT, INSTITUTIONAL)`（+ 存在时的 SI plan）；**0 命中 →
          `CrawlerError(PARSE)`**（OK 全文页却解析不出链接 = 站点改版腐化信号，canary
          标红，design §5——与 NO_ENTITLEMENT 由 classify 结果区分，非文本二次嗅探）。

        无 session → `AuthRequired`（提示 `crawler auth login oup@campus`）；离线测试经
        四类 fixture 覆盖，不发真实请求。
        """
        if session is None:
            raise AuthRequired("oup session 未配置", detail="crawler auth login oup@campus")
        doi = self._doi_of(paper)
        landing = self._authed_get(f"{_DOI_RESOLVER}/{doi}", session, stage="resolve")
        result = self._classify(landing)

        if result is ClassifyResult.CHALLENGE:
            raise Challenged("oup 落地页命中风控挑战", detail=_redacted_where(landing.final_url))
        if result is ClassifyResult.LOGIN_REDIRECT:
            raise AuthRequired(
                "oup 落地页 302→signin（session 过期/未登录）",
                detail="crawler auth login oup@campus",
            )
        if result is ClassifyResult.NO_ENTITLEMENT:
            raise CrawlerError(
                ErrorClass.NO_ENTITLEMENT,
                f"oup 无全文订阅权限（doi {doi}）→ 转 OA-fallback",
                detail=_redacted_where(landing.final_url),
            )

        # OK：解析全文页 PDF 链接（0 命中 = 改版腐化 → PARSE）。
        body_text = landing.body.decode("utf-8", errors="replace")
        pdf_url = parse.extract_pdf_url(body_text, base_url=landing.final_url)
        if pdf_url is None:
            raise CrawlerError(
                ErrorClass.PARSE,
                f"oup OK 全文页解析出 0 个 article-pdf 链接（改版信号；doi {doi}）",
                detail=_redacted_where(landing.final_url),
            )
        plans = [
            AssetPlan(
                kind=AssetKind.PDF,
                url=pdf_url,
                expected_type="application/pdf",
                url_strategy=UrlStrategy.DIRECT,
                auth_needed=AuthLevel.INSTITUTIONAL,
                version=None,
            )
        ]
        for si_url in parse.extract_supplementary_urls(body_text, base_url=landing.final_url):
            plans.append(
                AssetPlan(
                    kind=AssetKind.SI,
                    # MINOR-1：按扩展名推断（参照 cvf `_expected_type_for`）——SI 附录多为
                    # zip/xlsx/pdf，硬编 octet-stream 会令 fetch 对非 PDF 附录误做 %PDF 魔数断言。
                    expected_type=_expected_type_for(si_url),
                    url=si_url,
                    url_strategy=UrlStrategy.DIRECT,
                    auth_needed=AuthLevel.INSTITUTIONAL,
                    version=None,
                )
            )
        return plans

    # -- fetch（专属 client 直取 PDF + 魔数/auth_leak 校验，design §3.2）-----------------------

    def fetch_asset(
        self, plan: AssetPlan, io: FetchIO, session: SessionHandle | None = None
    ) -> FetchResult:
        """session cookie jar 注入专属 client → GET `article-pdf` 直取 → `io.write_stream`。

        成功判据按 `plan.expected_type` 分层（MINOR-1）：**PDF 主路**（`application/pdf`）
        要求 `200` + body 起始 `%PDF` 魔数；**非 PDF 资产**（SI zip/xlsx…）只要求 `200`
        （不做 `%PDF` 魔数断言——附录起始字节非 %PDF 属正常）。否则经 `ChallengeDetector`
        判读**被拒/伪装**（design §5，**不做 BrowserFetcher 兜底**——`[auth-browser]` 留
        T7b/runbook）：

        - CHALLENGE → `Challenged`；LOGIN_REDIRECT → `AuthRequired`（对所有 kind 一致）；
        - NO_ENTITLEMENT → `CrawlerError(NO_ENTITLEMENT)`；
        - **仅 PDF 主路** OK 却非 `%PDF`（下载物为 HTML 伪装 PDF）→ `CrawlerError(INTEGRITY,
          detail="auth_leak")`（魔数校验失败 → 触发 healthcheck 判拦截页伪装，design §3.2/§5）；
          非 PDF 资产不做此断言（MINOR-1：zip/xlsx 附录不误报 auth_leak）。

        **流式化 seam 备注**：本 Phase 为覆盖魔数 + auth_leak + 挑战判读，`_authed_get` 一次
        读全 body 再经 `io.write_stream(iter([body]))` 单块写入（低频个人科研量级可接受）；
        真流式（首 chunk 窥魔数后续写）留 T1b/pipeline 装配期按需精化，contract 不变。
        """
        if session is None:
            raise AuthRequired("oup session 未配置", detail="crawler auth login oup@campus")
        resp = self._authed_get(plan.url, session, stage="fetch")
        pdf_expected = plan.expected_type == "application/pdf"

        # PDF 主路快路：200 + %PDF 魔数 → 直接写（登录态泄漏防护的正锚，门控 pdf_expected）。
        if pdf_expected and resp.status == 200 and resp.body.startswith(b"%PDF"):
            bytes_written, sha256 = io.write_stream(iter([resp.body]))
            return FetchResult(ok=True, bytes_written=bytes_written, sha256=sha256)

        # 其余先经 ChallengeDetector 判读被拒/伪装（challenge/login/entitlement 对所有 kind 一致）。
        result = self._classify(resp)
        if result is ClassifyResult.CHALLENGE:
            raise Challenged("oup 取回命中风控挑战", detail=_redacted_where(resp.final_url))
        if result is ClassifyResult.LOGIN_REDIRECT:
            raise AuthRequired(
                "oup 取回 302→signin（session 过期）",
                detail="crawler auth login oup@campus",
            )
        if result is ClassifyResult.NO_ENTITLEMENT:
            raise CrawlerError(
                ErrorClass.NO_ENTITLEMENT,
                "oup 取回落 no_entitlement（无全文权限）",
                detail=_redacted_where(resp.final_url),
            )

        # 到此 classify=OK。分两支：
        if pdf_expected:
            # PDF 主路 OK 却非 %PDF（或非 200）：登录态泄漏/拦截页伪装成 PDF 响应 → auth_leak。
            raise CrawlerError(
                ErrorClass.INTEGRITY,
                f"oup 下载物非 PDF（HTML 伪装，status={resp.status}）",
                detail="auth_leak",
            )
        # 非 PDF 资产（SI）：200+OK → 正常写（不做 %PDF 魔数断言，MINOR-1）；非 200 → integrity。
        if resp.status == 200:
            bytes_written, sha256 = io.write_stream(iter([resp.body]))
            return FetchResult(ok=True, bytes_written=bytes_written, sha256=sha256)
        raise CrawlerError(
            ErrorClass.INTEGRITY,
            f"oup 非 PDF 资产取回非 200（status={resp.status}，type={plan.expected_type}）",
        )

    # -- healthcheck（探针账号页，design §3.3）------------------------------------------------

    def healthcheck(self, session: SessionHandle | None = None) -> HealthReport:
        """无 session → `raise NotImplementedError`（canary SKIP，复用先例 auth-framework §7）。

        有 session → 探针账号页 `ChallengeDetector.classify`：OK（含账号标识）→ healthy；
        302→signin → EXPIRED（unhealthy）；challenge 特征 → CHALLENGED（unhealthy）。
        探针 URL 为类级默认 `/my-account`（⚠ design §3.3 controller 亲读②：R0 未实测，
        待 runbook 核验）。
        """
        if session is None:
            raise NotImplementedError("oup session 未配置")
        resp = self._authed_get(_PROBE_URL, session, stage="healthcheck")
        result = self._classify(resp)
        if result is ClassifyResult.OK:
            return HealthReport(healthy=True, detail="oup 探针账号页 OK（含账号标识）")
        if result is ClassifyResult.LOGIN_REDIRECT:
            return HealthReport(healthy=False, detail="oup session 已过期（302→signin）")
        if result is ClassifyResult.CHALLENGE:
            return HealthReport(healthy=False, detail="oup 探针命中风控挑战（CHALLENGED）")
        return HealthReport(healthy=False, detail=f"oup 探针页非预期分类：{result.value}")

    # -- 内部：分类 / DOI / 专属 client GET --------------------------------------------------

    def _classify(self, resp: _RawResponse) -> ClassifyResult:
        return self._detector.classify(
            status=resp.status,
            headers=resp.headers,
            final_url=resp.final_url,
            body=resp.body,
        )

    def _doi_of(self, paper: PaperStub) -> str:
        """从 paper.identifiers 取 DOI（scheme `doi`，crossref 已归一为裸小写）。

        缺 DOI → `CONFIG`（路由/装配缺陷：oup 只按 DOI resolve，无 DOI 无从定位落地页）。
        非 10.1093 前缀不硬拒（crossref 已按 venue 路由至本 adapter；跨前缀留诊断宽容）。
        """
        for scheme, value in paper.identifiers:
            if scheme == _DOI_SCHEME and value:
                return value
        raise CrawlerError(
            ErrorClass.CONFIG,
            f"oup resolve 需要 paper 携带 {_DOI_SCHEME!r} identifier（前缀应为 {_OUP_DOI_PREFIX}）",
        )

    def _cookies_for(self, session: SessionHandle) -> httpx.Cookies:
        """经 seam 把 session 换成**主域限定**的 httpx cookie jar（凭证红线 + 防泄漏）。

        supplier 未装配（session 在但 seam 未接线）→ `CONFIG`（装配缺陷，响亮暴露：T1b
        store 合并后由 pipeline 注入，不该在生产缺席）。全部 cookie 限定 `domain=主域`
        → 首跳 doi.org 不携带（见模块 docstring）。
        """
        if self._cookie_supplier is None:
            raise CrawlerError(
                ErrorClass.CONFIG,
                "oup cookie 供给 seam 未装配（T1b store 合并后由 pipeline 注入）",
            )
        jar = httpx.Cookies()
        for name, value in self._cookie_supplier(session).items():
            jar.set(name, value, domain=_PRIMARY_DOMAIN)
        return jar

    def _authed_get(self, url: str, session: SessionHandle, *, stage: str) -> _RawResponse:
        """专属 client（UA+主域 cookie+跟随重定向）GET → 原始响应视图（**4xx 不 raise**）。

        网络层异常（超时/连接错）→ `CrawlerError(TRANSIENT)`（对齐 HttpClient 冻结映射
        口径，design §6）；HTTP 状态码**不**在此 raise——4xx（含 403 挑战）原样带回交
        `ChallengeDetector` 判读（见模块 docstring 为何不复用共享 HttpClient）。

        **R2c 观测补丁**：`client.get(url)` 内部已 `follow_redirects=True` 跟完全部重定向——
        成功后落**恰一条** obslog DEBUG 事件，字段（`stage`/`domain`/`url`/`status`）取自
        **终响应**（`response.url`/`response.status_code`，即跟随重定向后的最终落点；`url`
        经 `obslog.log_event` 内部 `redact()`）。字段名对齐 `http.py::_emit_event` 的形态，
        但**不**是 `http.py::_log_exchange` 那种逐重定向跳各记一条的行为——本 adapter 只记
        终点这一条（独立审查 Minor #5 订正措辞：此前"复用 `_emit_event` 既有事件形态"一句
        易被读成连跳数也复用，如实澄清为"字段形态对齐、覆盖范围不同"）。这是有意为之而非
        疏漏：`ChallengeDetector` 判读只关心落点本身（headers/body/final_url），中间跳转
        对四态分类无独立意义，简报"补一条事件"字面量已满足，不需要额外的首跳/中间跳事件。
        `resolve_assets`/`fetch_asset`/`healthcheck` 三调用点经本方法唯一收口，一处
        埋点即全覆盖（V2 订正口径：stage 级 INFO 与 fetch 侧 FetchLog 已有，本卡只补这条
        缺失的 per-request 事件，FetchLog 落库口径不动）。网络层异常分支不落此事件——同
        http.py 现状，异常本身已携带足够诊断信息（`CrawlerError.detail`）。
        """
        cookies = self._cookies_for(session)
        client = httpx.Client(
            headers={"User-Agent": build_user_agent(self._resolve_email())},
            cookies=cookies,
            transport=self._transport,
            follow_redirects=True,
            timeout=30.0,
        )
        try:
            response = client.get(url)
        except httpx.TimeoutException as exc:
            raise CrawlerError(ErrorClass.TRANSIENT, "oup 请求超时", detail="timeout") from exc
        except httpx.HTTPError as exc:
            raise CrawlerError(
                ErrorClass.TRANSIENT, "oup 连接错误", detail=type(exc).__name__
            ) from exc
        else:
            log_event(
                "DEBUG",
                "oup http exchange",
                stage=stage,
                domain=response.url.host or None,
                url=str(response.url),
                status=response.status_code,
            )
            return _RawResponse(
                status=response.status_code,
                headers=response.headers,
                final_url=str(response.url),
                body=response.content,
            )
        finally:
            client.close()


# SI 附件扩展名 → expected_type 推断（参照 cvf `_expected_type_for` 先例，MINOR-1）。
# 未知扩展名回落 `application/octet-stream`——fetch 对非 `application/pdf` 资产不做 %PDF
# 魔数断言（zip/xlsx 等附录起始字节非 %PDF 属正常，不误报 auth_leak）。`.pdf` 附录仍归
# `application/pdf` → 走 PDF 主路魔数 + auth_leak 防护（附录若是真 PDF，%PDF 校验正确）。
_SI_EXPECTED_TYPES: dict[str, str] = {
    ".pdf": "application/pdf",
    ".zip": "application/zip",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".csv": "text/csv",
    ".txt": "text/plain",
}


def _expected_type_for(url: str) -> str:
    """SI URL 扩展名 → expected_type；未知扩展名回落 `application/octet-stream`（参照 cvf）。"""
    lower = url.lower()
    for ext, mime in _SI_EXPECTED_TYPES.items():
        if lower.endswith(ext):
            return mime
    return "application/octet-stream"


def _redacted_where(final_url: str) -> str:
    """诊断 detail 里的落点定位：只保留 path（去 query，避免 returnUrl 等参数噪声/泄漏）。"""
    return final_url.split("?", 1)[0]


__all__ = ["CookieSupplier", "OupSilverchairAdapter"]
