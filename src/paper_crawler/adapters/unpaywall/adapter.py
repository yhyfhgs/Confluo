"""Unpaywall `SourceAdapter` 主体（design/adapters/aggregators.md §5.5）。

**RESOLVE only**：capabilities 仅 ``Capability.RESOLVE``（无 DISCOVER/ENUMERATE/SEARCH/
FETCH——Unpaywall 无搜索端点，必须先有 DOI 清单来自 crossref/dblp 等枚举源；本 adapter
只按已知 DOI 定位 OA 副本，不下载全文）。

阶段分工（§5.5）：

- `resolve_assets`：`paper.identifiers` 取 `doi` → `lookup(doi)` → `best_oa_location.
  url_for_pdf` 非空则产 `AssetPlan(url_strategy=direct, auth_needed=none)`；为空时遍历
  `oa_locations[]` 回退（`parse.select_pdf_location`）；两处都没有 → **不产 AssetPlan**，
  仅当 `url_for_landing_page` 有值时落一条 DEBUG 观测（★裁决 J4：无 PDF 直链不下载
  landing 页，只记录其存在）。`version` 精确串（`submittedVersion`/`acceptedVersion`/
  `publishedVersion`）原样写入 `AssetPlan.version`；submitted/accepted（非正式版）
  额外落一条 DEBUG 观测（`Asset.version`/`AssetPlan` 无独立字段承载"是否正式版"这一
  维度，故经 obslog 而非新数据字段标注——见 `parse.INFORMAL_VERSIONS`）。
- `lookup`：`resolve_assets`/OA 报告（`report.py`）共用的底层原语——`GET /v2/{doi}
  ?email=<addr>` → 解析。**404（DOI 未收录）在此归一为 `None`**（正常空结果，非
  异常——§5.5「错误映射」表），其余错误状态（422 缺 email→config、429→rate_limited、
  5xx→transient、畸形 JSON→parse）由 `HttpClient`/`parse.parse_response` 原样 raise。
- `healthcheck`：固定金 OA DOI（D-019 锚点，§7）比对 `is_oa`+`oa_status`。

**触发条件语义**（设计意图，§5.5；**接线现状**：Phase 4 已实现并被集成测试覆盖，见
auth-framework.md §8.1——本节此前称"两条触发路径均不在本次改动范围内"的表述已过期，
2026-07-26 审计文档滞后修正）：本 adapter 在两种场景下被调用——①主源 resolve/fetch 因
`no_entitlement` 失败后的 OA 兜底（`runner._route_error` 的 NO_ENTITLEMENT 分支经
`_enqueue_oa_fallback` 派生 `oa_fallback` 子任务）；② `StageContext.oa_fallback` 门控
开启时（auth_gated venue 装配期默认置 True，见 `cli.py::_assemble_auth_seam`）。接线
路径：pipeline 第七 handler `_stage_oa_fallback`（`pipeline/stages.py`）把本类
`lookup()` 的记录规格化为 `AssetPlan` 并入队 `fetch` 任务 → `_fetch_oa_direct` 通用
direct 取回落盘（复用 `PartFileIO`/`validate_pdf_magic`/`finalize_fetch` 三件不绕过）。
本文件自身只负责 `resolve_assets`/`lookup` 的正确性（pipeline 编排/入队/落盘属
`stages.py`/`runner.py` 职责，不在本文件范围）；接线集成测试见
`tests/integration/test_auth_pipeline.py`（如
`test_no_entitlement_triggers_oa_fallback_direct_fetch`）。

**邮箱注入**（`?email=` 查询参数；aggregators.md §3）：优先级"显式注入 > env 兜底"
（同 arxiv/openreview 的 UA email 注入先例，见 `set_email`/`_resolve_email`）——CLI
装配期经 `EmailConsumer` 协议注入 `Config.identity_email`；未注入时惰性回退环境变量
`PAPER_CRAWLER_CONTACT_EMAIL`，再退 `.invalid` 占位（RFC 2606 保留域，不可能是真实
地址）。**日志脱敏前置义务**：本包引入前 `obslog._SENSITIVE_KEYS` 已并入 `email`
（T5 先决步骤），故请求 URL 经 `HttpClient`/`obslog.log_event` 落盘前邮箱已脱敏。
"""

from __future__ import annotations

import os
from urllib.parse import quote, urlencode

from paper_crawler.adapter import AdapterBase, AdapterFamily
from paper_crawler.adapters.unpaywall import parse
from paper_crawler.errors import CrawlerError, ErrorClass
from paper_crawler.http import HttpClient
from paper_crawler.obslog import log_event
from paper_crawler.types import (
    AssetKind,
    AssetPlan,
    AuthLevel,
    Capability,
    HealthReport,
    PaperStub,
    RatePolicy,
    SessionHandle,
    UrlStrategy,
    VenueSpec,
)
from paper_crawler.useragent import build_user_agent

# --- 端点与常量（§5.5）------------------------------------------------------------------------

_API_BASE = "https://api.unpaywall.org/v2/"

_CONTACT_EMAIL_ENV = "PAPER_CRAWLER_CONTACT_EMAIL"  # 同 arxiv/openreview 的既有环境变量
# RFC 2606 保留 .invalid：惰性自建（无显式注入邮箱）时的占位联系人；诚实反映"未配置"，
# 不硬编码可能被误用的真实地址（同 arxiv/openreview `_PLACEHOLDER_EMAIL` 先例）。
_PLACEHOLDER_EMAIL = "anonymous@paper-crawler.invalid"

# healthcheck 固定金 OA DOI（D-019 锚点，aggregators.md §7；[LIVE] 2026-07-22 核验，
# 详见 tests/fixtures/unpaywall/01_normal_gold_fallback.json 的 `_grounded` 字段）。
# 若未来该 DOI 的 OA 状态真的漂移，人工核准新真值后按 UPDATE_GOLDEN 纪律更新本二常量。
_HEALTHCHECK_DOI = "10.1371/journal.pmed.0020124"
_HEALTHCHECK_EXPECT_IS_OA = True
_HEALTHCHECK_EXPECT_OA_STATUS = "gold"


def _default_email() -> str:
    return os.environ.get(_CONTACT_EMAIL_ENV, "").strip() or _PLACEHOLDER_EMAIL


def _resolve_url(doi: str, email: str) -> str:
    """`GET /v2/{doi}?email=<addr>` 的完整 URL（`doi` 内的 `/` 保留为路径分隔符）。"""
    encoded_doi = quote(doi, safe="/")
    return f"{_API_BASE}{encoded_doi}?{urlencode({'email': email})}"


def _doi_of(paper: PaperStub) -> str:
    """从 stub 取 DOI（scheme='doi'）；缺失 → CONFIG（路由缺陷——unpaywall 只按 DOI resolve）。"""
    for scheme, value in paper.identifiers:
        if scheme == "doi":
            return value
    raise CrawlerError(
        ErrorClass.CONFIG, f"unpaywall resolve_assets needs a doi identifier: {paper.identifiers!r}"
    )


class UnpaywallAdapter(AdapterBase):
    """Unpaywall adapter（`aggregator` family；RESOLVE only）。"""

    adapter_id = "unpaywall"
    family: AdapterFamily = "aggregator"
    capabilities = Capability.RESOLVE
    # §4：5 req/s（=300 req/min）且日总量 <100k；burst=5 对齐"每秒 5 个"的自然突发上限。
    # 日总量护栏本身未在本 adapter 内实现持久化熔断（OA 报告典型规模 ~100 DOI 远低于
    # 100k/天，非本期风险；若未来需要跨进程日配额，可仿 openalex `meta.cost_usd` 熔断
    # 先例另行引入，见任务报告 concerns）。
    default_rate = RatePolicy(
        requests_per_minute=300.0,
        burst=5,
        source_note=(
            "Unpaywall API: 5 req/s and <100k requests/day (no key, email required "
            "via ?email= query param); docs/design/adapters/aggregators.md §4 [DOCS]"
        ),
    )
    auth_requirement = AuthLevel.NONE
    domains: tuple[str, ...] = ("api.unpaywall.org",)
    # `resolve_assets` 需要真实网络请求（GET /v2/{doi} 判定 is_oa/url_for_pdf）才能产出
    # AssetPlan，不满足 `AdapterBase.resolve_offline` "可证明零网络"的契约——保留继承的
    # 默认 False（安全侧，不豁免 resolve 阶段限速闸），区别于 arxiv/openreview 纯 URL
    # 构造式 resolve（那些已证明零网络，显式置 True）。

    def __init__(self, http: HttpClient | None = None, *, email: str | None = None) -> None:
        # http=None：首次网络调用时惰性自建（见模块 docstring 的邮箱注入优先级）。
        self._http = http
        self._email = email

    def set_http_client(self, client: HttpClient) -> None:
        """注入组装好的 `HttpClient`（`adapter.HttpClientConsumer` 协议）。"""
        self._http = client

    def set_email(self, email: str | None) -> None:
        """注入联系邮箱（`adapter.EmailConsumer` 协议；CLI 装配期传入 `Config.identity_email`）。"""
        self._email = email

    def _resolve_email(self) -> str:
        """当前生效邮箱：显式注入 > 环境变量 `PAPER_CRAWLER_CONTACT_EMAIL` > `.invalid` 占位。"""
        return self._email if self._email else _default_email()

    def _client(self) -> HttpClient:
        if self._http is None:
            self._http = HttpClient(user_agent=build_user_agent(self._resolve_email()))
        return self._http

    # -- lookup（resolve_assets 与 OA 报告共用的底层原语）------------------------------------

    def lookup(self, doi: str) -> parse.UnpaywallRecord | None:
        """`GET /v2/{doi}?email=<addr>` → 结构化记录；404（DOI 未收录）→ `None`。

        `None` 是**正常空结果**（该 DOI 无 unpaywall 记录），非异常——调用方（本类的
        `resolve_assets`、`report.build_oa_report`）据此各自判定"无 OA 副本"/"未收录"。
        其余错误状态经 `HttpClient` 冻结映射原样 `raise`（422→config、429→rate_limited、
        5xx→transient）；响应体畸形经 `parse.parse_response` 原样 `raise`（→parse）。
        """
        url = _resolve_url(doi, self._resolve_email())
        try:
            data = self._client().get_bytes(url)
        except CrawlerError as exc:
            if exc.error_class is ErrorClass.GONE:
                return None
            raise
        return parse.parse_response(data, doi=doi)

    # -- resolve（真实网络：GET /v2/{doi}）----------------------------------------------------

    def resolve_assets(
        self, venue: VenueSpec, paper: PaperStub, session: SessionHandle | None = None
    ) -> list[AssetPlan]:
        """`paper` 的 DOI → 0 或 1 个 pdf `AssetPlan`（§5.5 映射表）。

        `venue` 未被使用（unpaywall 是跨 venue 的 OA 兜底源，不读 venue 层配置）——
        与 arxiv `resolve_assets` 对 `venue` 参数的既有处理方式一致（冻结协议签名要求）。
        """
        doi = _doi_of(paper)
        record = self.lookup(doi)
        if record is None:
            return []  # 该 DOI 未被 unpaywall 收录，正常空结果（非错误）

        location = parse.select_pdf_location(record)
        if location is None or not location.url_for_pdf:
            landing = parse.landing_url_of(record)
            if landing:
                # ★裁决 J4：仅 landing 有值时记一条观测（不下载 landing 页，不产 AssetPlan）。
                log_event(
                    "DEBUG",
                    "unpaywall oa landing only (no pdf link found)",
                    stage="resolve",
                    domain=self.domains[0],
                    oa_landing_url=landing,
                    oa_status=record.oa_status,
                    doi=doi,
                )
            return []

        if location.version in parse.INFORMAL_VERSIONS:
            # Asset.version 精确串已如实写入下方 AssetPlan；此处额外记一条"非正式版"
            # 观测（AssetPlan/Asset 无独立字段承载该维度，见模块 docstring）。
            log_event(
                "DEBUG",
                "unpaywall resolved an informal (non-final) OA version",
                stage="resolve",
                domain=self.domains[0],
                version=location.version,
                doi=doi,
            )

        return [
            AssetPlan(
                kind=AssetKind.PDF,
                url=location.url_for_pdf,
                expected_type="application/pdf",
                url_strategy=UrlStrategy.DIRECT,
                auth_needed=AuthLevel.NONE,
                version=location.version,
            )
        ]

    # `fetch_asset`/`discover_timeline`/`enumerate_issue` 未声明能力（capabilities 仅
    # RESOLVE）——不覆写，沿用 `AdapterBase` 默认的 `CapabilityNotSupported`（crossref/
    # elsevier_sd stub 先例，见 `test_undeclared_capability_raises_capability_not_supported`）。

    # -- healthcheck（固定金 OA DOI，D-019 锚点）-----------------------------------------------

    def healthcheck(self, session: SessionHandle | None = None) -> HealthReport:
        """`GET /v2/{固定金 OA DOI}` → 比对 `is_oa`+`oa_status`（§5.5/§7 D-019 锚点）。"""
        try:
            record = self.lookup(_HEALTHCHECK_DOI)
        except CrawlerError as exc:
            return HealthReport(
                healthy=False, detail=f"unpaywall unreachable ({exc.error_class.value}): {exc}"
            )
        if record is None:
            return HealthReport(
                healthy=False,
                detail=f"anchor DOI {_HEALTHCHECK_DOI} not found in unpaywall (expected present)",
            )
        if (
            record.is_oa is not _HEALTHCHECK_EXPECT_IS_OA
            or record.oa_status != _HEALTHCHECK_EXPECT_OA_STATUS
        ):
            return HealthReport(
                healthy=False,
                detail=(
                    f"canary drift on {_HEALTHCHECK_DOI}: is_oa={record.is_oa!r} "
                    f"oa_status={record.oa_status!r} (expected is_oa="
                    f"{_HEALTHCHECK_EXPECT_IS_OA!r} oa_status={_HEALTHCHECK_EXPECT_OA_STATUS!r})"
                ),
            )
        return HealthReport(
            healthy=True,
            detail=(
                f"{_HEALTHCHECK_DOI} matches is_oa={record.is_oa!r} oa_status={record.oa_status!r}"
            ),
        )


__all__ = ["UnpaywallAdapter"]
