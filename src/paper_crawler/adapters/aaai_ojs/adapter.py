"""AAAI OJS `SourceAdapter` 主体（design/adapters/aaai-ojs.md §1/§3-§6）。

把零网络纯逻辑（`parse`）与 T2 共享 `HttpClient` 组装成 adapter。能力口径（§2）：
``DISCOVER | ENUMERATE | RESOLVE | FETCH``——**不声明 SEARCH**（冻结 `SourceAdapter`
协议无 `search()`，订阅命中经 enumerate 增量 + 本地过滤达成，先例 arxiv/openreview/
pmlr §1）。

阶段分工（§4）：

- `discover_timeline`（零网络）：`quirks.volume_map`（year→volume）逐条产**届/年聚合**
  IssueRef（★A 方案 B，§9）——一届一 IssueRef、幂等键 ``(venue, year)``；48 个 OJS
  issue 是站点实现细节非领域概念，"No.M" 降为 per-paper meta。
- `enumerate_issue`（OAI-PMH 收割）：`ListRecords` + `resumptionToken` 翻页 +
  **DOI-卷号客户端过滤**（membership 判据是 DOI 卷号，非 OAI set/日期窗——datestamp≠
  发表日，§4 ⚠）。**先全库回填、后当前届固定回看窗增量**（★A 附属，零接口变更、arxiv
  同构）：历史届无日期窗全库收割按卷 partition；当前届（volume_map 最大年之卷）加
  ``from=<今日−回看天数>`` datestamp 窗做增量。去重由 `identifier('doi')` 主键天然保证。
  历史届的那"一趟"全库收割由**跨卷分区缓存**兑现（见 `_backfill_pages`）：首个历史届
  触发单趟收割并把所有已注册历史卷就地 partition 缓存，其余历史届零请求命中缓存——
  否则每届各自重扫全库，请求成本随已注册届数线性放大（审计 S1-P1）。
- `resolve_assets`（零网络）：读 `meta['pdf_url']`（dc:relation 的 galley view URL）→
  ``/view/``→``/download/`` 预换终态 URL（survey §4，省一跳）→ 单个 PDF `AssetPlan`。
- `fetch_asset`（流式）：`HttpClient.stream` → `io.write_stream`；首字节嗅探——PDF url
  回登录页（302→/login 未发布/占位 galley）→ `no_entitlement`（★D，§9）；回其它 HTML
  （撤稿/合并）→ `gone`。`%PDF` 权威校验归 pipeline。
- `healthcheck`：OAI `Identify` 200 + `repositoryName` 含 "AAAI"（存活基线，匿名零
  token；REST API 匿名 403 非健康信号，不参与）。3 样本 GetRecord canary 的"已知答案"
  回归比对是**测试层**职责（tests/unit/test_aaai_canary.py，先例 pmlr §6.4 分层——不
  给运行期 healthcheck 增网络面）。

**限速/礼貌**（§5）：`default_rate` = 1 req/2s（30 rpm），并发 1——NFR-4 无站点声明
保守默认（robots 无 Crawl-delay、无 Retry-After/无反爬，[LIVE] 2026-07-21）；单 nginx
本域承载力有限，克制并发。批量走 OAI 收割（100/页 + resumptionToken）非逐篇 HTML。

**HttpClient 注入**（同 arxiv/pmlr 先例）：`load_adapters()` 无参实例化——`__init__
(http=None)`，首次网络调用惰性自建（UA 走 D-014，email 从环境变量取，缺失用占位
`.invalid` 地址）。测试注入 `HttpClient(transport=MockTransport(...))` 达成零真实网络。
"""

from __future__ import annotations

import os
from collections.abc import Iterable, Iterator
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

from paper_crawler.adapter import AdapterBase, AdapterFamily
from paper_crawler.adapters import _oai
from paper_crawler.adapters.aaai_ojs import parse
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

# --- 端点与常量（§2 表 / §4）------------------------------------------------------------------

_OAI_BASE_TMPL = "https://ojs.aaai.org/index.php/{code}/oai"
_METADATA_PREFIX = "oai_dc"
# 当前届增量的固定回看天数（§4 ★A 附属：非持久化 watermark 的 adapter 常量）。窗口越长越
# 抗 datestamp 滞后（survey §6：2019 论文 datestamp=2021 的 2 年滞后），但当前届的初始
# 完整基线由"历史全库回填"建立，本窗口只负责捕获增量新增（去重由 DOI 主键保证）。
_LOOKBACK_DAYS = 30
# 跨卷分区缓存的记录数硬顶（审计 S1-P1 修复）。全库活记录实测 ~22.4k（survey §11.1，
# completeListSize=26185 含 4.26% 墓碑），本常量取其 ~2× 余量：正常运行永不触顶；真触顶
# 说明站点规模已远超勘察量级，此时**响亮降级**（WARN 事件 + 关缓存回退逐卷收割）而非
# 静默吃内存——缓存是纯性能设施，关掉只慢不错。
_BACKFILL_CACHE_MAX_RECORDS = 50_000
_HEALTHCHECK_CODE = "AAAI"  # 主会 context（healthcheck Identify 用）
_PDF_MAGIC = b"%PDF-"
_SNIFF_BYTES = 4096  # 首字节嗅探缓冲：足以覆盖 OJS 登录页顶部的 login 表单标记

_CONTACT_EMAIL_ENV = "PAPER_CRAWLER_CONTACT_EMAIL"
# RFC 2606 保留 .invalid 顶级域——占位联系人不可能是真实地址，且明确信号「该走配置化
# client 注入真实 mailto」。仅在惰性自建且未设环境变量时使用（同 arxiv/pmlr 先例）。
_PLACEHOLDER_EMAIL = "anonymous@paper-crawler.invalid"


def _default_user_agent() -> str:
    """惰性自建 client 的 UA：email 从环境变量取（不硬编码），缺省用 `.invalid` 占位。"""
    email = os.environ.get(_CONTACT_EMAIL_ENV, "").strip() or _PLACEHOLDER_EMAIL
    return build_user_agent(email)


# --- adapter 主体 ----------------------------------------------------------------------------


class AaaiOjsAdapter(AdapterBase):
    """AAAI OJS（`ojs.aaai.org`）adapter（`open_access` family）。

    服务 venue：AAAI 学会 OJS 实例上的出版物（Phase 范围先 `aaai` 主会）。同实例托管多刊
    （AIES/ICWSM/ICAPS…），同一套 URL 模板仅替换 `quirks.ojs_code`——姊妹 venue 复用本
    adapter、各自 volume_map，作为独立 venue 后续注册（先例 arxiv 按 category 切多 venue）。
    版权定位：免费只读镜像、个人科研用途、不再分发（§1 红线，非 CC-BY 开放许可）。
    """

    adapter_id = "aaai_ojs"
    family: AdapterFamily = "open_access"
    # §2 裁决：无 SEARCH。
    capabilities = (
        Capability.DISCOVER | Capability.ENUMERATE | Capability.RESOLVE | Capability.FETCH
    )
    # 1 req/2s = 30 req/min，并发 1（§5 表）。
    default_rate = RatePolicy(
        requests_per_minute=30.0,
        burst=1,
        source_note=(
            "ojs.aaai.org 无官方文档化速率数字（robots.txt 仅 Disallow /cache/，无 "
            "Crawl-delay；无 429/Retry-After/反爬）→ NFR-4 保守默认 1 req/2s、并发 1；"
            "research/site-survey/aaai-ojs.md [LIVE] 2026-07-21"
        ),
    )
    auth_requirement = AuthLevel.NONE
    domains: tuple[str, ...] = ("ojs.aaai.org",)
    # resolve_assets 纯读 meta['pdf_url'] 做 view→download 换写，零网络 → 豁免限速闸。
    resolve_offline = True

    def __init__(self, http: HttpClient | None = None) -> None:
        # http=None：首次网络调用时惰性自建（见模块 docstring 的注入说明）。
        self._http = http
        # 跨卷分区缓存（审计 S1-P1）：单趟全库收割的产物，key=(venue_id, oai_base)，
        # value=已注册历史卷→该卷 PaperStub 序列。**实例内存态、非持久化**：随 adapter
        # 实例（= 一次 CLI 进程内的 registry 实例）生灭，跨进程不复用、不落盘。
        self._backfill_key: tuple[str, str] | None = None
        self._backfill: dict[str, tuple[PaperStub, ...]] | None = None

    def set_http_client(self, client: HttpClient) -> None:
        """注入组装好的 `HttpClient`（`adapter.HttpClientConsumer` 协议，同 arxiv 先例）。"""
        self._http = client

    def _client(self) -> HttpClient:
        if self._http is None:
            self._http = HttpClient(user_agent=_default_user_agent())
        return self._http

    # -- discover（零网络）-------------------------------------------------------------------

    def discover_timeline(self, venue: VenueSpec, since: str | None = None) -> Iterable[IssueRef]:
        """`quirks.volume_map`（year→volume）逐条产**届/年聚合** IssueRef（零网络，§4/§3.2）。

        字段分解定死（★A 方案 B）：``volume``=裸数字串（一届=一卷）、``number``=None
        （OJS "No.M" 子 issue 不建模为 IssueRef 维度）、``year``=int（--year/--volume
        selector 的生效字段）、``label``=f'AAAI-{year%100:02d}'（站点品牌名，与"第 N 届"
        序号刻意区分）、``pub_date``=None、``paper_count_claimed``=None（enumerate 回填）。
        `since`（可选下界，'YYYY' 前缀）晚于 volume_map 最小年时收窄起点（增量发现）。
        """
        volume_map = _volume_map(venue)
        since_year = _parse_since_year(since)
        for year in sorted(volume_map):
            if since_year is not None and year < since_year:
                continue
            volume = volume_map[year]
            yield IssueRef(
                venue_id=venue.id,
                volume=str(volume),
                number=None,
                year=year,
                label=f"AAAI-{year % 100:02d}",
                pub_date=None,
                paper_count_claimed=None,
            )

    # -- enumerate（OAI-PMH 收割）-----------------------------------------------------------

    def enumerate_issue(self, venue: VenueSpec, issue: IssueRef) -> Iterable[PaperStub]:
        """届 IssueRef → OAI-PMH `ListRecords` 收割（DOI-卷号客户端过滤 + resumptionToken）。

        目标/窗口构造在此**急切**求值（非法 issue 早失败为 CONFIG）；翻页与网络在返回的
        生成器惰性执行。**先全库回填、后当前届固定回看窗增量**（★A 附属，§4/§9）：

        - **当前届**（volume_map 最大年之卷）：加 ``from=<今日−回看天数>`` datestamp 窗，
          **永不读写跨卷缓存**——新鲜度优先，每次都要真去看站点有没有新增。
        - **历史届**：无日期窗全库收割，但**一趟喂所有历史届**（跨卷分区缓存）——首个历史
          届触发收割并 partition 缓存全部已注册历史卷，其余历史届零请求命中缓存。

        去重由下游 `identifier('doi')` 主键天然保证（重叠窗口不产重复行）。
        """
        volume = _issue_volume(issue, venue)
        oai_base = _oai_base(_ojs_code(venue))
        if volume == _latest_volume(venue):
            url = _oai_list_url(oai_base, _lookback_from())
            return self._enumerate_pages(venue, issue, volume, oai_base, url)
        cached = self._cached_partition(venue, oai_base, volume)
        if cached is not None:
            log_event(
                "DEBUG",
                "aaai backfill partition cache hit",
                venue=venue.id,
                stage="enumerate",
                bucket=issue.label,
                volume=volume,
                papers=len(cached),
            )
            return iter(cached)
        return self._backfill_pages(venue, issue, volume, oai_base, _oai_list_url(oai_base, None))

    def _enumerate_pages(
        self, venue: VenueSpec, issue: IssueRef, volume: str, oai_base: str, url: str
    ) -> Iterator[PaperStub]:
        """单卷收割：翻页 + DOI-卷号过滤，只产本卷（当前届回看窗增量路径）。"""
        for page in self._iter_pages(venue, issue, oai_base, url):
            for record in page.records:
                # DOI-卷号客户端过滤（§4）：只保留 DOI 解析出的卷号 == 本届卷号者。
                if record.volume != volume:
                    continue
                yield parse.to_paper_stub(record)

    # -- 跨卷分区缓存（审计 S1-P1：历史卷冷回填单趟化）----------------------------------------

    def _backfill_pages(
        self, venue: VenueSpec, issue: IssueRef, volume: str, oai_base: str, url: str
    ) -> Iterator[PaperStub]:
        """历史届全库回填：单趟收割 → 目标卷即时产出 + 其余已注册历史卷就地 partition 缓存。

        为什么不用日期窗替代（**已否决**，理由入档以免后人重蹈）：OAI `from/until` 过滤的
        是 `datestamp`（入库/修改时间）而非发表日，survey §11.2 实测 Vol.26 的 383 条里
        362 条 `dc:date` 因批量勘误落在 2021——按发表年切窗必然漏收；且 `datestamp` 会被
        站点侧再编辑改写，"今天正确的窗"明天就静默少收。故窗口分区对历史届不可用，
        单趟全库 + 跨卷 partition 才是 design §4 ★A "一次全库收割按卷 partition" 的原意。

        缓存只在收割**自然跑完**（resumptionToken 耗尽）时发布：调用方提前 break 而中断
        生成器，则本趟不发布任何缓存（宁可下次重扫，不要发布残缺分区）。
        """
        cacheable = self._cacheable_volumes(venue)
        partitions: dict[str, list[PaperStub]] | None = {v: [] for v in cacheable}
        buffered = 0
        for page in self._iter_pages(venue, issue, oai_base, url):
            for record in page.records:
                vol = record.volume
                # DOI-卷号 partition（§4）：目标卷即时产出；其余已注册历史卷进缓存；
                # 未注册卷号/非 AAAI 形态（volume=None）不属任何届，丢弃。
                if vol is None or (vol != volume and vol not in cacheable):
                    continue
                stub = parse.to_paper_stub(record)
                if vol == volume:
                    yield stub
                if partitions is not None and vol in partitions:
                    partitions[vol].append(stub)
                    buffered += 1
                    if buffered > _BACKFILL_CACHE_MAX_RECORDS:
                        partitions = None
                        log_event(
                            "WARN",
                            "aaai backfill partition cache disabled (record cap exceeded)",
                            venue=venue.id,
                            stage="enumerate",
                            bucket=issue.label,
                            cap=_BACKFILL_CACHE_MAX_RECORDS,
                        )
        if partitions is not None:
            self._publish_backfill(venue, oai_base, partitions)

    def _iter_pages(
        self, venue: VenueSpec, issue: IssueRef, oai_base: str, url: str
    ) -> Iterator[parse.OaiListPage[parse.AaaiRecord]]:
        """`ListRecords` 翻页循环（resumptionToken 直到耗尽）+ 墓碑跳过数可观测。"""
        client = self._client()
        while True:
            page = parse.parse_oai_page(client.get_bytes(url))
            if page.skipped_tombstones:
                # 墓碑可观测（design §4）：venue/届/跳过数落 obslog debug 事件。
                log_event(
                    "DEBUG",
                    "oai tombstones skipped",
                    venue=venue.id,
                    stage="enumerate",
                    bucket=issue.label,
                    skipped_tombstones=page.skipped_tombstones,
                )
            yield page
            if page.resumption_token is None:
                return
            url = _oai_resume_url(oai_base, page.resumption_token)

    def _cacheable_volumes(self, venue: VenueSpec) -> frozenset[str]:
        """可进缓存的卷集合 = 已注册卷 − 当前届卷（当前届恒走回看窗，不吃缓存）。"""
        registered = {str(v) for v in _volume_map(venue).values()}
        return frozenset(registered - {_latest_volume(venue)})

    def _cached_partition(
        self, venue: VenueSpec, oai_base: str, volume: str
    ) -> tuple[PaperStub, ...] | None:
        """命中则返回该卷分区（**空届返回空元组也算命中**，不触发重扫）；未命中 None。

        命中判据三合一：缓存已发布、`(venue_id, oai_base)` 同源、且该卷在上趟收割的
        `cacheable` 集合内。第三条挡住"收割后 volume_map 才新增的卷"——那种卷在旧分区表
        里查无此键，退回真收割而非静默产空序列。
        """
        if self._backfill is None or self._backfill_key != (venue.id, oai_base):
            return None
        return self._backfill.get(volume)

    def _publish_backfill(
        self, venue: VenueSpec, oai_base: str, partitions: dict[str, list[PaperStub]]
    ) -> None:
        self._backfill_key = (venue.id, oai_base)
        self._backfill = {vol: tuple(stubs) for vol, stubs in partitions.items()}
        log_event(
            "DEBUG",
            "aaai backfill partition cache published",
            venue=venue.id,
            stage="enumerate",
            volumes=len(self._backfill),
            papers=sum(len(stubs) for stubs in self._backfill.values()),
        )

    # -- resolve（零网络，view→download 预换）-----------------------------------------------

    def resolve_assets(
        self, venue: VenueSpec, paper: PaperStub, session: SessionHandle | None = None
    ) -> list[AssetPlan]:
        """纯读 `meta['pdf_url']`（galley view URL）→ ``/view/``→``/download/`` 终态 URL（§4）。

        survey §4：view 302→download，预换省一跳。meta 缺 `pdf_url`（无 galley relation，
        罕见）→产 0 个 pdf plan（非错误，pmlr/openreview 先例）。landing 不物化为 asset
        （与 arxiv/pmlr 一致）。多 galley 消歧失败的偶发非 PDF 由 pipeline `%PDF` 魔数拦截。
        """
        pdf_view_url = dict(paper.meta).get("pdf_url")
        if not pdf_view_url:
            return []
        return [
            AssetPlan(
                kind=AssetKind.PDF,
                url=_view_to_download(pdf_view_url),
                expected_type="application/pdf",
                url_strategy=UrlStrategy.DIRECT,
                auth_needed=AuthLevel.NONE,
                version=None,
            )
        ]

    # -- fetch（流式，登录页/撤稿页首字节嗅探）-----------------------------------------------

    def fetch_asset(
        self, plan: AssetPlan, io: FetchIO, session: SessionHandle | None = None
    ) -> FetchResult:
        """`HttpClient.stream` → `io.write_stream`；首字节嗅探区分登录页/撤稿页（§4/§6）。

        `%PDF` 权威校验归 pipeline（冻结分工）；本层把两类"PDF url 却回 HTML"归类：登录页
        （302→/login，未发布/占位 galley）→ `no_entitlement`（★D，存在但不可匿名取）；其它
        HTML（撤稿/合并/不存在）→ `gone`。HTTP 4xx（404/410）由 `HttpClient` 直接映射。
        """
        stream = self._client().stream(plan.url)
        bytes_written, sha256 = io.write_stream(_entitlement_guarded_stream(stream))
        return FetchResult(ok=True, bytes_written=bytes_written, sha256=sha256)

    # -- healthcheck（OAI Identify）---------------------------------------------------------

    def healthcheck(self, session: SessionHandle | None = None) -> HealthReport:
        """OAI `Identify` 200 + `repositoryName` 含 "AAAI"（存活基线，§4；匿名零 token）。

        REST API 匿名 403 非健康信号，不参与。3 样本 GetRecord canary 的已知答案回归比对
        是测试层职责（test_aaai_canary.py，先例 pmlr §6.4——不给运行期 healthcheck 增网络面）。
        """
        url = _oai_identify_url(_oai_base(_HEALTHCHECK_CODE))
        try:
            data = self._client().get_bytes(url)
        except CrawlerError as exc:
            return HealthReport(
                healthy=False,
                detail=f"oai identify unreachable ({exc.error_class.value}): {exc}",
            )
        try:
            name = _identify_repository_name(data)
        except CrawlerError as exc:
            return HealthReport(healthy=False, detail=f"identify parse failed: {exc}")
        if name is None or "AAAI" not in name.upper():
            return HealthReport(
                healthy=False, detail=f"identify repositoryName missing 'AAAI': {name!r}"
            )
        return HealthReport(healthy=True, detail=f"oai identify ok (repositoryName={name!r})")


# --- 模块级纯函数 -----------------------------------------------------------------------------


def _volume_map(venue: VenueSpec) -> dict[int, int]:
    """从 `venue.quirks['volume_map']` 取 year→volume 映射；结构非法 → `CONFIG`（pmlr 先例）。

    键值宽容强转 `int()`（PyYAML 对无引号整数键给 int，有引号则给 str；两种形态都接受）。
    """
    raw = venue.quirks.get("volume_map")
    if not isinstance(raw, dict) or not raw:
        raise CrawlerError(
            ErrorClass.CONFIG,
            f"venue {venue.id!r} 缺少非空的 quirks.volume_map（year→volume，aaai-ojs.md §4）",
        )
    result: dict[int, int] = {}
    for key, value in raw.items():
        try:
            year = int(key)
            volume = int(value)
        except (TypeError, ValueError) as exc:
            raise CrawlerError(
                ErrorClass.CONFIG,
                f"venue {venue.id!r} quirks.volume_map 含非法条目: {key!r}: {value!r}",
            ) from exc
        result[year] = volume
    return result


def _latest_volume(venue: VenueSpec) -> str:
    """volume_map 最大年对应的卷号（裸数字串）——"当前届"判据（触发 enumerate 回看窗）。"""
    volume_map = _volume_map(venue)
    latest_year = max(volume_map)
    return str(volume_map[latest_year])


def _parse_since_year(since: str | None) -> int | None:
    """`since`（可选年份下界，'YYYY' 前缀）→ int；非法格式 → `CONFIG`。"""
    if since is None:
        return None
    try:
        return int(since[:4])
    except ValueError as exc:
        raise CrawlerError(ErrorClass.CONFIG, f"invalid since year: {since!r}") from exc


def _issue_volume(issue: IssueRef, venue: VenueSpec) -> str:
    """校验并取出 `issue.volume`（裸数字串，须在 venue 的 volume_map 中注册）。

    两类 `config`：形态非法（非 None 且非纯数字串——foreign/畸形 IssueRef，如误传 arxiv
    月度桶）、以及卷号未在 `volume_map` 注册（新一届未登记，提示走 track 流程 D-012；
    pmlr 先例）。
    """
    if issue.volume is None or not issue.volume.isdigit():
        raise CrawlerError(
            ErrorClass.CONFIG,
            f"aaai enumerate needs IssueRef.volume as a bare digit string, got {issue.volume!r}",
        )
    volume_map = _volume_map(venue)
    if int(issue.volume) not in volume_map.values():
        raise CrawlerError(
            ErrorClass.CONFIG,
            f"volume {issue.volume!r} not registered in venue {venue.id!r} "
            "quirks.volume_map (unregistered edition — use `crawler track`, D-012)",
        )
    return issue.volume


def _ojs_code(venue: VenueSpec) -> str:
    """OJS journal context 代码：`quirks.ojs_code` > `venue.id.upper()`（§4 默认）。"""
    code = venue.quirks.get("ojs_code")
    if isinstance(code, str) and code.strip():
        return code.strip()
    return venue.id.upper()


def _oai_base(code: str) -> str:
    return _OAI_BASE_TMPL.format(code=code)


def _lookback_from() -> str:
    """当前届增量的 datestamp 窗下界 ``from``（今日 − 回看天数，UTC 日期，date 粒度）。"""
    return (datetime.now(UTC).date() - timedelta(days=_LOOKBACK_DAYS)).isoformat()


def _oai_list_url(oai_base: str, frm: str | None) -> str:
    params = {"verb": "ListRecords", "metadataPrefix": _METADATA_PREFIX}
    if frm is not None:
        params["from"] = frm
    return f"{oai_base}?{urlencode(params)}"


def _oai_resume_url(oai_base: str, token: str) -> str:
    # OAI-PMH 规范：resumptionToken 与其他实参互斥，续页只带 verb + resumptionToken。
    return f"{oai_base}?{urlencode({'verb': 'ListRecords', 'resumptionToken': token})}"


def _oai_identify_url(oai_base: str) -> str:
    return f"{oai_base}?{urlencode({'verb': 'Identify'})}"


def _identify_repository_name(data: bytes) -> str | None:
    """从 OAI `Identify` 响应取 `repositoryName`（缺 `<Identify>`/`<repositoryName>` → None）。"""
    root = _oai.fromstring(data)
    identify = root.find(_oai.oai("Identify"))
    if identify is None:
        return None
    return _oai.optional_text(identify, _oai.oai("repositoryName"))


def _view_to_download(view_url: str) -> str:
    """galley view URL → download 终态 URL：``/article/view/`` → ``/article/download/``（§4）。

    survey §4：view 302→download，预换省一跳。已是 download 形态（如取自 citation_pdf_url）
    时 replace 无操作（幂等）。
    """
    return view_url.replace("/article/view/", "/article/download/", 1)


def _entitlement_guarded_stream(chunks: Iterable[bytes]) -> Iterator[bytes]:
    """透传字节流，但先嗅探首字节：PDF 魔数放行；登录页→`NO_ENTITLEMENT`；其它 HTML→`GONE`。

    首个非 PDF 且形似 HTML 的响应体分两类（§6/★D）：OJS 登录页（302→/login 落地，未发布/
    占位 galley——"存在但不可匿名取"，权限门非消失）归 `NO_ENTITLEMENT`（detail=login-gated，
    保留 design/05 的 OA fallback 升级路径）；其它 HTML（撤稿/合并/不存在）归 `GONE`。既非
    PDF 又不形似 HTML 的体透传，交 pipeline 的 `%PDF` 权威校验处置。
    """
    iterator = iter(chunks)
    head = bytearray()
    for chunk in iterator:
        head.extend(chunk)
        if len(head) >= _SNIFF_BYTES:
            break
    stripped = bytes(head).lstrip()
    if not stripped.startswith(_PDF_MAGIC) and _looks_like_html(stripped):
        if _looks_like_login(head):
            raise CrawlerError(
                ErrorClass.NO_ENTITLEMENT,
                "aaai returned a login page (unpublished/gated galley), not a PDF",
                detail="login-gated",
            )
        raise CrawlerError(
            ErrorClass.GONE,
            "aaai returned an HTML page (withdrawn/merged/not-found), not a PDF",
        )
    if head:
        yield bytes(head)
    yield from iterator


def _looks_like_html(head: bytes) -> bool:
    # 子串扫描（非 startswith）覆盖前导注释/BOM/空白后才出现的 HTML 标记——OJS 落地页
    # 与撤稿页均以标准 HTML 文档标记起手；扫首字节缓冲整段，不被前导注释挤出窗口。
    low = head[:_SNIFF_BYTES].lower()
    return b"<!doctype html" in low or b"<html" in low


def _looks_like_login(head: bytes | bytearray) -> bool:
    """OJS 登录页特征（首字节缓冲内）：`/login` 路径回显 / password 字段 / signIn 表单。"""
    low = bytes(head).lower()
    return b"/login" in low or b'name="password"' in low or b"signin" in low


__all__ = ["AaaiOjsAdapter"]
