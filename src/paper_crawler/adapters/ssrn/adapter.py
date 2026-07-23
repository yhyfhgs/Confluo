"""SSRN `SourceAdapter` 主体（design/adapters/ssrn.md §4；聚合元数据主路径）。

把纯逻辑件（`buckets` 零网络年桶 / `parse` 后处理层）与**内部持有的 `CrossrefAdapter`**
组装成 adapter。能力口径（§4.1）：``DISCOVER | ENUMERATE | RESOLVE``（RESOLVE 为
landing-only 零网络）——**无 FETCH**（模式 B 浏览器全文 defer Phase 6，D-029 案 B）、
**无 SEARCH**（冻结 `SourceAdapter` 协议无 `search()`）。

**红线：元数据主路径零 `*.ssrn.com` 接触**（AC-5.1a③ / D-029）。本 adapter 的唯一网络
出口 = `api.crossref.org`（经内部 `CrossrefAdapter`）；`domains=("api.crossref.org",)`——
`*.ssrn.com` 域**永不注册、永不请求**（站点 Cloudflare + 环境 TLS 双阻断天然免疫）。

阶段分工（§4）：

- `discover_timeline`：**纯生成**零网络年桶（`buckets.year_buckets`，1990..今年）——
  controller 发现①仲裁令：真实 Crossref `facet=created:*` 返 HTTP 400，原 facet 方案
  不可实现 → 纯本地生成（零请求零 facet 依赖）。上界「今年」经**注入 clock** 取（沿
  `TaskQueue.__init__(clock=)` / `pipeline.runner` 先例，可测性——不硬调 `date.today()`）。
- `enumerate_issue`：**委内部 `CrossrefAdapter`**（prefix 10.2139 + created 日期轴，两类型
  全收不加 `type:` 过滤）产 `PaperStub` 流 → **后处理层**（`parse`）抽 abstract_id、增补
  `(ssrn)` identifier；**护栏**：非 `ssrn.` 中缀 DOI → 不增补 + 计 `skipped_non_ssrn` 观测。
- `resolve_assets`：**landing-only 零网络**（`resolve_offline=True`）——构造 landing 引用作
  观测、**不产 PDF asset**；全文交 pipeline unpaywall OA-fallback（landing-only 净效果 PDF
  命中≈0，§4.4）。
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
from datetime import UTC, datetime

from paper_crawler.adapter import AdapterBase, AdapterFamily
from paper_crawler.adapters.crossref.adapter import CrossrefAdapter
from paper_crawler.adapters.ssrn import buckets, parse
from paper_crawler.errors import CrawlerError, ErrorClass
from paper_crawler.http import HttpClient
from paper_crawler.obslog import log_event
from paper_crawler.types import (
    AssetPlan,
    AuthLevel,
    Capability,
    HealthReport,
    IssueRef,
    PaperStub,
    RatePolicy,
    SessionHandle,
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
    # §4.1：无 FETCH（模式 B defer Phase 6）/ 无 SEARCH（冻结协议）。RESOLVE=landing-only。
    capabilities = Capability.DISCOVER | Capability.ENUMERATE | Capability.RESOLVE
    # 元数据主干经 api.crossref.org（内部 CrossrefAdapter）——沿 crossref 既有裁决（polite
    # pool 实测 X-Rate-Limit-Limit:10/1s，保守取上限 5 req/s = 300 req/min，burst=1，§5）。
    default_rate = RatePolicy(
        requests_per_minute=300.0,
        burst=1,
        source_note=(
            "SSRN 元数据主路径经 api.crossref.org（prefix 10.2139 枚举主干，零 SSRN 接触）："
            "沿 crossref polite pool 裁决（X-Rate-Limit-Limit:10/1s，保守 5 req/s）；"
            "*.ssrn.com 仅模式 B（浏览器全文，defer Phase 6）触及、元数据层永不接触；"
            "design/adapters/ssrn.md §5 [LIVE] 2026-07-24"
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
        （venue YAML 声明，§4.2 消费侧契约）——两类型全收（不加 `type:` 过滤）。本层加工每个
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
        """**landing-only 零网络**：构造 landing 引用作观测、**不产可下载 asset**（§4.4）。

        由 `(ssrn, abstract_id)` identifier（enumerate 增补）或 DOI 回退构造 landing URL
        `papers.ssrn.com/sol3/papers.cfm?abstract_id={id}` → 落一条 DEBUG 观测（**纯串、不
        请求**——`*.ssrn.com` 零接触）。**返 `[]`**：SSRN 无第三方 PDF 旁路（勘察 §5 landing-only），
        全文交 pipeline unpaywall OA-fallback（净效果 PDF 命中≈0，§4.4；同 unpaywall landing-only
        先例返空）。`venue`/`session` 不读（下载主键来自 paper identifier，跨 venue 中性）。
        """
        abstract_id = _abstract_id_of(paper)
        log_event(
            "DEBUG",
            "ssrn landing-only (no platform pdf asset; pdf via unpaywall OA-fallback)",
            stage="resolve",
            abstract_id=abstract_id,
            ssrn_landing_url=parse.landing_url(abstract_id),
        )
        return []

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
