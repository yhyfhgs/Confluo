"""SSRN `SourceAdapter` 主体（design/adapters/ssrn.md §4/§11；聚合元数据主路径 + 模式 B）。

把纯逻辑件（`buckets` 零网络年桶 / `parse` 后处理层）与**内部持有的 `CrossrefAdapter`**
组装成 adapter。能力口径（§4.1，随 D-030/design/11 §12 裁决①点亮）：
``DISCOVER | ENUMERATE | RESOLVE | FETCH``（RESOLVE 产 landing 观测 + 模式 B `RENDER_PAGE`
计划；FETCH 经 browser-fetch 横切件执行，本 adapter 自身不实现 `fetch_asset`）——
**无 SEARCH**（冻结 `SourceAdapter` 协议无 `search()`）。

**红线：元数据主路径零 `*.ssrn.com` 接触**（AC-5.1a③ / D-029）。本 adapter 的唯一网络
出口 = `api.crossref.org`（经内部 `CrossrefAdapter`）；`domains=("api.crossref.org",)`——
`*.ssrn.com` 域**永不注册、永不请求**（站点 Cloudflare + 环境 TLS 双阻断天然免疫）。
模式 B 的浏览器上下文取回（`papers.ssrn.com`）由 browser-fetch 横切件在 stages 层执行，
不占本 adapter 的 `domains`/限速声明——限速/配额/挑战冷却/robots 合规全部归横切件
统一护栏（design/11 §7），本 adapter 不写任何该类代码（D-029 案 B："能力面恰好等于
合规面"，无可误用富余）。

阶段分工（§4）：

- `discover_timeline`：**纯生成**零网络年桶（`buckets.year_buckets`，1990..今年）——
  controller 发现①仲裁令：真实 Crossref `facet=created:*` 返 HTTP 400，原 facet 方案
  不可实现 → 纯本地生成（零请求零 facet 依赖）。上界「今年」经**注入 clock** 取（沿
  `TaskQueue.__init__(clock=)` / `pipeline.runner` 先例，可测性——不硬调 `date.today()`）。
- `enumerate_issue`：**委内部 `CrossrefAdapter`**（prefix 10.2139 + created 日期轴，两类型
  全收不加 `type:` 过滤）产 `PaperStub` 流 → **后处理层**（`parse`）抽 abstract_id、增补
  `(ssrn)` identifier；**护栏**：非 `ssrn.` 中缀 DOI → 不增补 + 计 `skipped_non_ssrn` 观测。
- `resolve_assets`：**landing-only 零网络**（`resolve_offline=True`）——构造 landing 引用
  （既作观测，也是模式 B `RENDER_PAGE` 计划的 `url`，design/11 §4.4 持久化纪律：volatile
  `Delivery.cfm` URL 不入库、只活在浏览器上下文单次调用栈上，本 adapter 不构造它）；
  全文优先交 pipeline unpaywall OA-fallback（landing-only 净效果 PDF 命中≈0，§4.4），
  模式 B 计划作为**唯一全文路径**并行产出（T11，D-029 案 B），受 `[browserfetch].enabled`
  三级门控（stages 层，本 adapter 不判——门关时计划仍产出，由 stages 门拦为 `skipped`）。
- `healthcheck`：`GET api.crossref.org/works/{固定 SSRN DOI}` → title 精确 drift 比对（§9.2；
  真值 [LIVE 2026-07-24] 双源转正——crossref 冒烟 + openalex 第二源一致）——**非 SSRN 域**。

**限速/UA**：`default_rate` 沿 crossref 既有裁决（5 req/s polite pool，UA 携 mailto，§5）。
enumerate 的网络经内部 `CrossrefAdapter` 的共享 `HttpClient` 走 pipeline `acquire_and_wait`
闸（`api.crossref.org` 桶）。**HttpClient 注入**：`load_adapters()` 无参实例化 → CLI 经
`bind_http_client` 注入携 config `[identity].email` 的共享 client → 本 adapter 转发给内部
`CrossrefAdapter`（`HttpClientConsumer` 协议，同 arxiv 先例）。
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from dataclasses import replace
from datetime import UTC, datetime

from paper_crawler.adapter import AdapterBase, AdapterFamily
from paper_crawler.adapters.crossref.adapter import CrossrefAdapter
from paper_crawler.adapters.ssrn import buckets, parse
from paper_crawler.auth.challenge import ClassifyResult
from paper_crawler.browserfetch import BrowserFetchHandle, classify_or_raise, host_of
from paper_crawler.errors import CrawlerError, ErrorClass
from paper_crawler.http import HttpClient
from paper_crawler.obslog import log_event
from paper_crawler.types import (
    AssetKind,
    AssetPlan,
    AuthLevel,
    Capability,
    HealthReport,
    IssueRef,
    PaperStub,
    RatePolicy,
    SessionHandle,
    UrlStrategy,
    VenueSpec,
)

# --- 常量（ssrn.md §4.3/§9.2）----------------------------------------------------------------

# 纯生成年桶下界（§4.3「下界默认合理起点如 1990」）；SSRN 早期投稿 DOI 化边界前不产桶。
_DEFAULT_INCEPTION_YEAR = 1990

# healthcheck 固定 SSRN DOI（§9.2，[LIVE 2026-07-24] 200；abstract_id 4056799）。真值
# （规整化 title[0]）[LIVE 2026-07-24] 双源捕获（T4 crossref 冒烟 + P5-M1 openalex
# 第二源确认，title 规整化后逐字一致，UPDATE_GOLDEN 纪律转正，沿 crossref 先例同口径）。
# 经内部 crossref lookup 走 `api.crossref.org`（非 SSRN 域）。
_HEALTHCHECK_DOI = "10.2139/ssrn.4056799"
_HEALTHCHECK_TITLE: str | None = "Allocating Scarce Information"


class SsrnAdapter(AdapterBase):
    """SSRN 全库 adapter（`open_access` family；单一 ssrn venue + econ/fin 主题近似过滤）。"""

    adapter_id = "ssrn"
    family: AdapterFamily = "open_access"
    # §4.1：FETCH 随 D-030/design/11 §12 裁决①点亮（模式 B，经 browser-fetch 横切件执行）；
    # 无 SEARCH（冻结协议）。RESOLVE 产 landing 观测 + 模式 B RENDER_PAGE 计划。
    capabilities = (
        Capability.DISCOVER | Capability.ENUMERATE | Capability.RESOLVE | Capability.FETCH
    )
    # 元数据主干经 api.crossref.org（内部 CrossrefAdapter）——沿 crossref 既有裁决（polite
    # pool 实测 X-Rate-Limit-Limit:10/1s，保守取上限 5 req/s = 300 req/min，burst=1，§5）。
    default_rate = RatePolicy(
        requests_per_minute=300.0,
        burst=1,
        source_note=(
            "SSRN 元数据主路径经 api.crossref.org（prefix 10.2139 枚举主干，零 SSRN 接触）："
            "沿 crossref polite pool 裁决（X-Rate-Limit-Limit:10/1s，保守 5 req/s）；"
            "*.ssrn.com 仅模式 B（浏览器全文，browser-fetch 横切件，T11）触及、元数据层"
            "永不接触；design/adapters/ssrn.md §5 [LIVE] 2026-07-24"
        ),
    )
    auth_requirement = AuthLevel.NONE
    # 限速/日志账本键 = api.crossref.org（元数据唯一网络出口）。**`*.ssrn.com` 不在
    # domains**——结构性保证零 SSRN 域注册/请求（AC-5.1a③ 红线，§5）。
    domains: tuple[str, ...] = ("api.crossref.org",)
    # discover=纯生成、resolve=纯 landing URL 构造——均**可证明零网络** → 豁免 resolve 阶段
    # 限速闸（AdapterBase.resolve_offline 语义；同 arxiv/nber 纯 URL 构造 resolve 先例）。
    resolve_offline = True

    def __init__(
        self,
        http: HttpClient | None = None,
        *,
        crossref: CrossrefAdapter | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        # 内部 CrossrefAdapter：enumerate 委其走 prefix 10.2139 + created（venue quirks 驱动，
        # §4.2）；测试可注入预置 client 的 crossref（零真实网络）。http 透传给内部 crossref。
        self._crossref = crossref if crossref is not None else CrossrefAdapter(http=http)
        # 注入 clock（discover 上界「今年」的可测性缝，沿 TaskQueue/pipeline.runner 先例）；
        # 默认 UTC now——**不硬调 date.today()**（controller 仲裁令）。
        self._clock: Callable[[], datetime] = clock or (lambda: datetime.now(UTC))

    def set_http_client(self, client: HttpClient) -> None:
        """注入共享 `HttpClient`（`adapter.HttpClientConsumer` 协议）→ 转发给内部 crossref。

        CLI 经 `bind_http_client` 在 `load_adapters()` 后注入携 config `[identity].email`
        的共享 client（UA `mailto:`，crossref polite pool 硬要求）——本 adapter 无自持
        client，enumerate/healthcheck 的网络全经内部 `CrossrefAdapter`，故转发给它。
        """
        self._crossref.set_http_client(client)

    # -- discover（纯生成零网络年桶，controller 发现①仲裁令）--------------------------------

    def discover_timeline(self, venue: VenueSpec, since: str | None = None) -> Iterable[IssueRef]:
        """**纯生成**逐年虚拟桶 `IssueRef`（1990..今年，零网络；§4.3 + 发现①仲裁令）。

        起点 = ``1990``（§4.3 下界）或 `since`（可选年下界，取前 4 位、不早于 1990 起点）；
        终点 = **注入 clock 的今年**（`self._clock().year`，可测性——不硬调 `date.today()`）。
        **零请求、零 facet 依赖**（真实 Crossref `facet=created:*` 返 400，原方案不可实现）。
        """
        end_year = self._clock().year
        start_year = _resolve_start_year(since)
        return buckets.year_buckets(venue.id, start_year, end_year)

    # -- enumerate（委内部 crossref + abstract_id 后处理层）--------------------------------

    def enumerate_issue(self, venue: VenueSpec, issue: IssueRef) -> Iterable[PaperStub]:
        """委内部 `CrossrefAdapter`（prefix 10.2139 + created 窗）→ 后处理增补 `(ssrn)` id。

        crossref 侧走 `venue.identifiers.crossref_prefix` + `quirks.crossref_date_field=created`
        （venue YAML 声明，§4.2 消费侧契约）——两类型全收（不加 `type:` 过滤）。

        **日粒度增量窗（Phase 6 F7）**：venue `quirks` 若带 `from-created-date`/
        `until-created-date`（订阅 watch 由 `subs.watch.AdapterFetcher.venue_for` 并进），
        内部 crossref 的 `_window_bounds` 会与桶年取交集后下推——本层零改动即生效。没有这
        条通道时一个 7 天的 watch 窗会退化成整年枚举（实测 2026 全年 155,461 条）。本层的
        年桶（`discover_timeline(venue, since)`）负责下界裁剪，窗内的日粒度归内部 crossref。

        本层加工每个
        `PaperStub`：DOI 匹配 `10.2139/ssrn.{id}` → 增补 `(ssrn, abstract_id)`；**护栏**：非
        `ssrn.` 中缀（潜在非-SSRN）→ 不增补 + 跳过 + 计 `skipped_non_ssrn` 观测（§4.2）。
        cursor 深翻/限速/错误映射沿 crossref 既有（惰性生成器，去重由 identifier 主键保证）。
        """
        stubs = self._crossref.enumerate_issue(venue, issue)
        return self._augment_ssrn_ids(venue, issue, stubs)

    def _augment_ssrn_ids(
        self, venue: VenueSpec, issue: IssueRef, stubs: Iterable[PaperStub]
    ) -> Iterator[PaperStub]:
        skipped_non_ssrn = 0
        for stub in stubs:
            doi = parse.doi_of_stub(stub)
            abstract_id = parse.abstract_id_from_doi(doi) if doi is not None else None
            if abstract_id is None:
                # 护栏（§4.2 / §6.1）：前缀 10.2139 下非 `ssrn.` 中缀 DOI → 非错误，跳过 + 计观测
                # （防潜在非-SSRN DOI 误纳本 venue）。DOI 缺失（crossref 罕见跳过）亦落此支。
                skipped_non_ssrn += 1
                continue
            yield parse.augment_with_ssrn_id(stub, abstract_id)
        if skipped_non_ssrn:
            log_event(
                "DEBUG",
                "ssrn non-ssrn dois skipped (prefix 10.2139 guardrail)",
                venue=venue.id,
                stage="enumerate",
                year=issue.year,
                skipped_non_ssrn=skipped_non_ssrn,
            )

    # -- resolve（landing-only 零网络，§4.4）-------------------------------------------------

    def resolve_assets(
        self, venue: VenueSpec, paper: PaperStub, session: SessionHandle | None = None
    ) -> list[AssetPlan]:
        """**零网络**：landing 观测 + 模式 B `RENDER_PAGE` 计划（§4.4、D-029 案 B、design/11）。

        由 `(ssrn, abstract_id)` identifier（enumerate 增补）或 DOI 回退构造 landing URL
        `papers.ssrn.com/sol3/papers.cfm?abstract_id={id}` → 落一条 DEBUG 观测（**纯串、不
        请求**——`*.ssrn.com` 零接触，本函数本身零网络）。

        **模式 B（唯一全文路径）**：返回一个 `AssetPlan(url_strategy=RENDER_PAGE)`，`url`=
        landing 引用（**不是** volatile `Delivery.cfm` URL——design/11 §4.4 持久化纪律：
        同批产出的一次性 token 不入库，只活在浏览器上下文单次调用栈上；本 adapter 不构造
        该 URL，交 browser-fetch 横切件在浏览器上下文内解析）。`auth_needed=FREE_ACCOUNT`
        （免费账号 session，D-029 修订：opt-in、非元数据前提，无账号时以干净上下文尝试）。

        **AC-0 合规复述**：本方法**不**发起任何 `*.ssrn.com` 请求（红线 4，robots 面零风险
        ——真正的取回请求会先经浏览器上下文的 `papers.ssrn.com/robots.txt` 前置核验义务
        与既有 robots/软门禁纪律，§2 红线 4），**不绕过任何付费墙/验证码**——CF 挑战由
        `ChallengeDetector` 分类后立即停手（AC-0.2），遇挡板即 BLOCKED，绝不求解/重试/
        换 UA。限速节流（1 req/5s + 抖动）、每日配额、挑战冷却全部由 browser-fetch
        横切件统一护栏承担（design/11 §7），本 adapter 侧零限速/配额代码。`ctx.
        browser_fetch`/`Config.browser_fetch_enabled` 三级门在 stages 层（`_fetch_via_
        browser`）——本层不判，**门关时该计划仍照常产出**，由 stages 门拦截为 `skipped`
        （不计 failures，D-030 裁决⑤门控表达纪律）。

        `unpaywall` OA-fallback 仍并行可用（pipeline 既有链，净效果 PDF 命中≈0，§4.4）；
        二者不冲突——本方法只产模式 B 一个计划，OA-fallback 由 pipeline 在 fetch 失败/
        no_entitlement 时自行派生（既有机制，本层不重复实现）。`venue`/`session` 不读
        （下载主键来自 paper identifier，跨 venue 中性）。
        """
        abstract_id = _abstract_id_of(paper)
        landing_url = parse.landing_url(abstract_id)
        log_event(
            "DEBUG",
            "ssrn render_page plan (mode B, opt-in; landing url only, no volatile token persisted)",
            stage="resolve",
            abstract_id=abstract_id,
            ssrn_landing_url=landing_url,
        )
        return [
            AssetPlan(
                kind=AssetKind.PDF,
                url=landing_url,
                expected_type="application/pdf",
                url_strategy=UrlStrategy.RENDER_PAGE,
                auth_needed=AuthLevel.FREE_ACCOUNT,
            )
        ]

    # -- 模式 B 同批解析（design/11 §4.4 生产端；`BrowserContextResolver` 鸭型）-------------

    def resolve_in_browser_context(self, plan: AssetPlan, handle: BrowserFetchHandle) -> AssetPlan:
        """在**同一浏览器上下文内**把 landing 计划解析成 volatile `Delivery.cfm` 计划。

        design/11 §4.4 同批约束的生产端：`Delivery.cfm` 的下载 token 一次性、必须同一上下文
        即时使用，故解析不能发生在 `resolve_assets`（零网络、跨批持久化）里——只能由本方法
        在 browser-fetch 已建立的 `handle` 上完成，产物**只活在 `fetch_one` 的栈上**
        （`asset.url` 仍是 `resolve_assets` 落的 landing 引用，§4.4 持久化纪律）。

        两跳纪律：
        1. `handle.goto(landing)` → 响应过 `classify_or_raise`（**每一次导航都判定**，红线
           §2-1/§2-2：CHALLENGE→`Challenged` 停手、LOGIN_REDIRECT→`AuthRequired`；
           NO_ENTITLEMENT→ 本方法转 `CrawlerError(NO_ENTITLEMENT)`，接既有 OA-fallback 链
           ——闭包的返回类型是 `AssetPlan`，无法表达"无权限"，只能以错误类如实上报）；
        2. 从 HTML 读出下载 `href`（`parse.delivery_url_from_landing`，纯函数、同源护栏）
           → 无命中即 `no_entitlement`（ssrn.md §6.2"付费/无免费副本"行），**不重试、不猜
           URL**（红线 4：不得凭 abstract_id 拼 `Delivery.cfm` 绕开站点下载入口）。

        **AC-0 合规复述**：本方法只在用户显式发起（三级门全开）的单篇取回中被调用，零批量、
        零并发；限速/配额/冷却由横切件统一护栏承担（stages 的闭包外壳在解析导航前再过一次
        域级闸——本 adapter 侧仍**零限速/配额代码**）；遇挑战即停手，绝不求解/绕过/换 UA。
        """
        response = handle.goto(plan.url)
        # 判定器口径（R1 审查 P2-7）：此处恒新建 `ChallengeDetector()`（`classify_or_raise`
        # 的默认），与 `fetch_one` 主路径**不是同一个实例**。当前判定器无状态（`classify`
        # 是纯函数式分类，特征表为模块级常量）⇒ 行为等价，两实例无差别。但
        # `fetch_one(detector=…)` 的注入面**只覆盖主路径**、不穿到本闭包：一旦判定器变成
        # 有状态（如跨调用累计质询计数、动态特征表），同一次取回会出现"两跳两判定器"的
        # 割裂——届时须把 detector 穿进 resolve 接缝（`BrowserContextResolver` 加形参），
        # 而不是在此各自新建。本卡不动接缝签名，只登记该前提。
        verdict = classify_or_raise(response, domain=host_of(plan.url))
        if verdict is ClassifyResult.NO_ENTITLEMENT:
            raise CrawlerError(
                ErrorClass.NO_ENTITLEMENT,
                "ssrn landing 判定无免费全文权限（→ OA-fallback 既有链）",
                detail="ssrn_landing_no_entitlement",
            )
        delivery = parse.delivery_url_from_landing(response.body, base_url=response.final_url)
        if delivery is None:
            raise CrawlerError(
                ErrorClass.NO_ENTITLEMENT,
                "ssrn landing 页无 Delivery.cfm 下载链接（无免费副本，或站点标记形态已变）",
                detail="ssrn_no_delivery_link",
            )
        return replace(plan, url=delivery)

    # -- healthcheck（固定 SSRN DOI 经 crossref lookup；非 SSRN 域）--------------------------

    def healthcheck(self, session: SessionHandle | None = None) -> HealthReport:
        """`GET api.crossref.org/works/{固定 SSRN DOI}` → 比对规整化 title[0]（§9.2；非 SSRN 域）。

        经内部 crossref `lookup` 打 `api.crossref.org`（**非 `*.ssrn.com`**——元数据层健康
        探测同样零 SSRN 接触）。真值 [LIVE 2026-07-24]（`_HEALTHCHECK_TITLE` 已双源转正，
        见模块常量注释）：精确 drift 比对——title 与 golden 不等即 unhealthy（canary 腐化
        哨兵）。`_HEALTHCHECK_TITLE is None` 分支保留为防御性回退（未来若需重置 golden）。
        """
        try:
            stub = self._crossref.lookup(_HEALTHCHECK_DOI)
        except CrawlerError as exc:
            return HealthReport(
                healthy=False,
                detail=f"crossref works api unreachable ({exc.error_class.value}): {exc}",
            )
        if stub is None:
            return HealthReport(
                healthy=False,
                detail=f"anchor DOI {_HEALTHCHECK_DOI} not found in crossref (expected present)",
            )
        if _HEALTHCHECK_TITLE is None:
            # [PENDING] 真值未捕获：结构性健康（title 非空）+ 附实测值供在线冒烟捕获。
            return HealthReport(
                healthy=True, detail=f"[PENDING golden] observed title={stub.title!r}"
            )
        if stub.title != _HEALTHCHECK_TITLE:
            return HealthReport(
                healthy=False,
                detail=f"canary drift — title {stub.title!r} != expected {_HEALTHCHECK_TITLE!r}",
            )
        return HealthReport(healthy=True, detail="canary matched (title[0])")


# --- 模块级纯函数 -----------------------------------------------------------------------------


def _resolve_start_year(since: str | None) -> int:
    """discover 起点年：`since`（取前 4 位年，不早于 1990 起点）或默认 1990（§4.3）。"""
    if since is None:
        return _DEFAULT_INCEPTION_YEAR
    head = since[:4]
    if len(head) == 4 and head.isdigit():
        return max(_DEFAULT_INCEPTION_YEAR, int(head))
    raise CrawlerError(ErrorClass.CONFIG, f"invalid ssrn since (need YYYY prefix): {since!r}")


def _abstract_id_of(paper: PaperStub) -> str:
    """取下载主键 abstract_id：`(ssrn)` identifier 优先，回退 DOI 抽取；均无 → CONFIG。

    enumerate 产的 paper 恒带 `(ssrn, abstract_id)`；外部直接 resolve（grab --ssrn / --doi）
    可能只带 DOI → 由 DOI 抽取。两者皆缺（无 ssrn 身份、非 ssrn DOI）= 路由缺陷 → CONFIG。
    """
    ssrn_id = parse.ssrn_id_of_stub(paper)
    if ssrn_id is not None:
        return ssrn_id
    doi = parse.doi_of_stub(paper)
    if doi is not None:
        derived = parse.abstract_id_from_doi(doi)
        if derived is not None:
            return derived
    raise CrawlerError(
        ErrorClass.CONFIG,
        f"ssrn resolve needs a ssrn abstract_id or 10.2139/ssrn.* doi: {paper.identifiers!r}",
    )


__all__ = ["SsrnAdapter"]
