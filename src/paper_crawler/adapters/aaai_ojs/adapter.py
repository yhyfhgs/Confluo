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
  发表日，§4 ⚠）。**冷启动全量收割建基线、基线已建后回看窗增量**（P0-3 修复，★A 附属
  结构延伸）：任一卷（历史或当前届）在本实例内首次被问到（跨卷分区缓存查无该卷）→
  单趟无日期窗全库收割，目标卷即时产出、**全部已注册卷（含当前届）**就地 partition
  缓存（见 `_backfill_pages`）——首个被问到的卷触发收割，其余已注册卷零请求命中缓存
  （历史届：直接命中即返回数据；否则每届各自重扫全库，请求成本随已注册届数线性放大，
  审计 S1-P1）。**当前届三态**（`_enumerate_current_edition`，基线完整 + 新鲜度优先）：
  ①**冷启动**（分区未建）→ 与历史届同款单趟无窗全库收割，就地建基线并即时交付；
  ②**首次交付**（分区已由某历史届的回填顺带建好、但当前届自己还没交付过）→
  ``chain(缓存分区内容, from=<今日−回看天数> 回看窗查询)`` 按 DOI 去重后一并产出
  （基线不能烂在缓存里，见 P0-3 回修）；③**稳态**（基线已交付过）→ 只走回看窗做真实
  增量查询（+1 请求/轮，不重复吐基线）。②③的窗口重叠不成问题：去重由
  `identifier('doi')` 主键天然保证（重叠窗口不产重复行）。**P0-3 根因（两层）**：其一，
  旧版注释曾称当前届基线由"历史全库回填"顺带建立，但该前提在旧实现里不成立——
  `_cacheable_volumes` 排除当前届、`_backfill_pages` 把当前卷记录判
  discarded_unregistered 丢弃，基线实际无处建立；当前届 enumerate 又无条件恒走
  回看窗，冷启动时 OJS datestamp 滞后发表（survey §6：可达近 2 年）导致窗口外早发
  论文被静默漏收，只能等其"滚入历史届"才被下次全库回填补齐。其二（回修）：前述两处
  改好、当前卷终于进了分区缓存之后，"缓存里有当前届分区"又被误当"基线已交付"信号而
  直接退回窄回看窗——已收割到的当前卷记录留在缓存里从未 yield 给消费方，缺口原样还在；
  故"分区已建"与"已交付"必须是两个标记（`_backfill` vs `_current_served`），首次交付
  走 chain（结构移植自 econsoc 同型 T15 修复，econsoc/adapter.py `_cacheable_years`；
  econsoc 缓存命中即返回、不再增量，aaai 在交付基线之余保留当前届每轮的回看窗真查以
  贴合"新鲜度优先"原设计，二者构造差异见 `_enumerate_current_edition`）。
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
# 当前届增量的固定回看天数（★D 附属：非持久化 watermark 的 adapter 常量）。窗口越长越
# 抗 datestamp 滞后（survey §6：2019 论文 datestamp=2021 的 2 年滞后）。**P0-3 修复**：当前
# 届的初始完整基线由单趟无窗全库收割建立（`_backfill_pages`）——它自己冷启动时触发，或由
# 某历史届的回填顺带建好、再经 `_enumerate_current_edition` 的首次交付 chain 吐给消费方；
# 旧注释曾称"历史全库回填顺带建立"即算数，该前提两层落空（`_cacheable_volumes` 排除当前届
# + 当前卷记录被判 discarded_unregistered 丢弃，基线无处建立；后来即便缓存住了也从不交付，
# 基线烂在缓存里）。本窗口只负责在基线之上捕获增量新增：首次交付时与基线 chain，此后每轮
# 单飞（去重由 DOI 主键保证）。
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
        # 跨卷分区缓存（审计 S1-P1；P0-3 起含当前届）：单趟全库收割的产物，
        # key=(venue_id, oai_base)，value=已注册卷（含当前届）→该卷 PaperStub 序列。
        # **实例内存态、非持久化**：随 adapter 实例（= 一次 CLI 进程内的 registry 实例）
        # 生灭，跨进程不复用、不落盘。
        self._backfill_key: tuple[str, str] | None = None
        self._backfill: dict[str, tuple[PaperStub, ...]] | None = None
        # 当前届「基线**已交付**」标记（P0-3 回修）——与上面的分区缓存（基线**已建**）
        # 刻意分成两件事：分区可能由某历史届的全库回填顺带建好，而那份内容还从未 yield
        # 给当前届的消费方；只有交付过，后续轮次才允许退化成纯回看窗（见
        # `_enumerate_current_edition`）。key=(venue_id, oai_base, volume)，仅在交付
        # 生成器**自然跑完**时落标（与 `_publish_backfill` 同哲学：残缺交付不算数，
        # 下一轮重来只多花一次窗口请求，且下游 DOI 主键幂等）。同为实例内存态。
        self._current_served: set[tuple[str, str, str]] = set()

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
        生成器惰性执行。**冷启动全量收割建基线、基线已建后回看窗增量**（P0-3 修复，
        §4/§9）：

        - **当前届**（volume_map 最大年之卷）：见 `_enumerate_current_edition` 的三态——
          ①分区未建 → 与历史届同款单趟全量收割建基线并即时交付；②分区已建（某历史届
          顺带建的）但本届还没交付过 → ``chain(缓存分区, 回看窗查询)`` 去重后一并产出；
          ③已交付过 → 只走 ``from=<今日−回看天数>`` datestamp 回看窗做真实增量查询
          （新鲜度优先，不重复吐基线）。
        - **历史届**：无日期窗全库收割，但**一趟喂所有已注册卷（含当前届）**（跨卷分区
          缓存）——首个被问到的卷触发收割并 partition 缓存全部已注册卷，其余历史届零
          请求命中缓存直接返回。

        去重由下游 `identifier('doi')` 主键天然保证（重叠窗口不产重复行）。
        """
        volume = _issue_volume(issue, venue)
        oai_base = _oai_base(_ojs_code(venue))
        if volume == _latest_volume(venue):
            return self._enumerate_current_edition(venue, issue, volume, oai_base)
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

    def _enumerate_current_edition(
        self, venue: VenueSpec, issue: IssueRef, volume: str, oai_base: str
    ) -> Iterable[PaperStub]:
        """当前届冷启动/首次交付/稳态三分支（P0-3 修复核心 + 回修，闭合"当前届无全量基线
        路径"与"基线烂在缓存里"两层缺口）。

        分支判据是**两个正交标记**：分区缓存有无该卷（基线**已建**）、`_current_served`
        有无该卷（基线**已交付**）。

        - **冷启动**（分区未建——本实例内还没有任何一趟全量收割覆盖过当前届，不论是它
          自己触发的还是某历史届顺带触发的）：与历史届同款单趟全量收割建基线
          （`_backfill_pages`，无 datestamp 窗、全部已注册卷含当前届一并 partition
          缓存）——取代旧版"当前届基线由历史全库回填顺带建立"的落空承诺（旧实现里
          `_cacheable_volumes` 排除当前届、`_backfill_pages` 把当前卷记录判
          discarded_unregistered 丢弃，基线实际无处建立，见模块 docstring）。
        - **首次交付**（分区已建但本届还没交付过——典型场景：`discover_timeline` 升序
          产 issue，v24 等历史届的全库回填顺带把当前届 partition 缓存了，随后才轮到当前
          届被 enumerate）：``chain(缓存分区内容, 回看窗查询)``，按 DOI 去重后一并产出。
          此前版本在这里把"分区已建"误当"已交付"、直接退回窄回看窗，致使已收割到的当前
          卷记录留在缓存里从未 yield、从未入库（P0-3 回修的靶心）。缓存分区那一段**零
          请求**，回看窗仍是一次真查——基线完整性与新鲜度两头都要。
        - **稳态**（已交付过）：只走 `from=` 回看窗做真实增量查询，不重复吐基线（当前届
          数据持续增长，快照很快过期；新鲜度优先，与历史届"缓存命中直接返回数据"不同；
          也与 econsoc"缓存命中即返回、不再增量"不同——econsoc 没有"同实例内重复
          enumerate 同一当前年"的场景假设，aaai 保留当前届每轮真查以贴合旧版设计意图）。

        缓存/标记的失效语义按 econsoc 既有口径：均为实例内存态、非持久化，跨进程/下次
        运行天然是空缓存空标记、天然重新冷启动全量收割，不自创 TTL/落盘机制。
        """
        cached = self._cached_partition(venue, oai_base, volume)
        if cached is None:
            log_event(
                "INFO",
                f"aaai {venue.id} {issue.label}: first harvest this run of current "
                f"edition volume {volume} (no partition cache yet) — running a full "
                "window-less harvest instead of a lookback datestamp query, closing "
                "the gap where papers whose OAI datestamp lags their publication date "
                "would otherwise be missed until they roll into a historical edition; "
                "later re-enumeration of this edition is served by a fresh lookback "
                "query alone (freshness first)",
                venue=venue.id,
                stage="enumerate",
                bucket=issue.label,
                volume=volume,
            )
            return self._serve_cold_baseline(venue, issue, volume, oai_base)
        if (venue.id, oai_base, volume) not in self._current_served:
            log_event(
                "INFO",
                f"aaai {venue.id} {issue.label}: first serve this run of current "
                f"edition volume {volume} — chaining the {len(cached)} cached baseline "
                "records (harvested by an earlier full window-less pass in this run, "
                "zero extra requests) with one fresh lookback datestamp query, so the "
                "baseline reaches the consumer instead of rotting in the cache; later "
                "re-enumeration of this edition is served by the lookback query alone",
                venue=venue.id,
                stage="enumerate",
                bucket=issue.label,
                volume=volume,
                baseline_papers=len(cached),
            )
            return self._serve_baseline_then_lookback(venue, issue, volume, oai_base, cached)
        url = _oai_list_url(oai_base, _lookback_from())
        return self._enumerate_pages(venue, issue, volume, oai_base, url)

    def _serve_cold_baseline(
        self, venue: VenueSpec, issue: IssueRef, volume: str, oai_base: str
    ) -> Iterator[PaperStub]:
        """当前届冷启动交付：单趟无窗全库收割即基线；跑完才落"已交付"标记。"""
        yield from self._backfill_pages(
            venue, issue, volume, oai_base, _oai_list_url(oai_base, None)
        )
        self._current_served.add((venue.id, oai_base, volume))

    def _serve_baseline_then_lookback(
        self,
        venue: VenueSpec,
        issue: IssueRef,
        volume: str,
        oai_base: str,
        baseline: tuple[PaperStub, ...],
    ) -> Iterator[PaperStub]:
        """当前届首次交付：`chain(缓存基线, 回看窗增量)`，同 DOI 只产一次。

        **去重口径**：先吐缓存基线（零请求）并记下其 DOI，回看窗里 DOI 已见者跳过——
        即"基线版本优先"。之所以不反过来"以回看窗新记录为准"：这份基线不是隔夜快照，
        而是**同一次运行内**几秒前那趟全库收割的产物，同一条记录在两处只可能字节相同
        （站点在同一趟运行中间改写该条的概率可忽略）；而"基线优先"能保持惰性——不必把
        整个窗口结果先物化再回头比对。真出现站点侧改写，下游 `identifier('doi')` 主键
        upsert 也会在下一轮回看窗把新版本盖回去。

        与 `_backfill_pages` 同哲学：标记只在生成器**自然跑完**时落——消费方提前 break
        则本届不算已交付，下一轮重走本分支（代价仅多一次窗口请求，产出幂等）。
        """
        served_dois: set[str] = set()
        for stub in baseline:
            doi = _stub_doi(stub)
            if doi is not None:
                served_dois.add(doi)
            yield stub
        url = _oai_list_url(oai_base, _lookback_from())
        for stub in self._enumerate_pages(venue, issue, volume, oai_base, url):
            doi = _stub_doi(stub)
            if doi is not None and doi in served_dois:
                continue
            yield stub
        self._current_served.add((venue.id, oai_base, volume))

    def _enumerate_pages(
        self, venue: VenueSpec, issue: IssueRef, volume: str, oai_base: str, url: str
    ) -> Iterator[PaperStub]:
        """单卷收割：翻页 + DOI-卷号过滤，只产本卷（当前届回看窗增量路径）。

        **丢弃可观测**（F4 审查追加，S1 台账 (c) 项）：当前窗查询按 datestamp 而非卷号
        取数，天然会带回其它卷的记录（如历史卷论文因勘误被重新 touch）——
        ``record.volume != volume`` 的丢弃是**正常路由噪声**，非本届数据缺失（那些
        记录仍会被各自届的收割路径覆盖，不是真丢失）。此前零日志、纯静默；现汇总
        计数于收割自然跑完时经 obslog DEBUG 可观测（逐记录打日志噪声太大，故只在
        生成器耗尽时汇总一条）。
        """
        other_volume_count = 0
        for page in self._iter_pages(venue, issue, oai_base, url):
            for record in page.records:
                # DOI-卷号客户端过滤（§4）：只保留 DOI 解析出的卷号 == 本届卷号者。
                if record.volume != volume:
                    other_volume_count += 1
                    continue
                yield parse.to_paper_stub(record)
        if other_volume_count:
            log_event(
                "DEBUG",
                "aaai current-window records skipped for non-matching volume",
                venue=venue.id,
                stage="enumerate",
                bucket=issue.label,
                volume=volume,
                skipped_other_volume=other_volume_count,
            )

    # -- 跨卷分区缓存（审计 S1-P1：全时间轴冷回填单趟化，含当前届基线）-----------------------

    def _backfill_pages(
        self, venue: VenueSpec, issue: IssueRef, volume: str, oai_base: str, url: str
    ) -> Iterator[PaperStub]:
        """单趟全库回填：目标卷即时产出 + 其余已注册卷（**含当前届**，P0-3）就地 partition
        缓存。历史届触发、或当前届冷启动触发（`_enumerate_current_edition`）均走这条路径。

        为什么不用日期窗替代（**已否决**，理由入档以免后人重蹈）：OAI `from/until` 过滤的
        是 `datestamp`（入库/修改时间）而非发表日，survey §11.2 实测 Vol.26 的 383 条里
        362 条 `dc:date` 因批量勘误落在 2021——按发表年切窗必然漏收；且 `datestamp` 会被
        站点侧再编辑改写，"今天正确的窗"明天就静默少收。故窗口分区对历史届不可用，
        单趟全库 + 跨卷 partition 才是 design §4 ★A "一次全库收割按卷 partition" 的原意。

        缓存只在收割**自然跑完**（resumptionToken 耗尽）时发布：调用方提前 break 而中断
        生成器，则本趟不发布任何缓存（宁可下次重扫，不要发布残缺分区）。

        **真丢弃可观测**（F4 审查追加，S1 台账 (c) 项）：未注册卷号/volume=None（非
        AAAI DOI 形态）的记录不属任何已知届——既非目标卷也非其余已注册卷（含当前届），
        此后也不会被任何届的收割路径覆盖，是真正的数据丢失面（区别于 `_enumerate_pages`
        同构位置"记录属于别的届、稍后自会被覆盖"的路由噪声）。此前零日志、纯静默；
        现汇总计数于收割自然跑完时经 obslog INFO 可观测（真丢弃比路由噪声更值得
        留意，故用 INFO 而非 DEBUG；逐记录打日志噪声太大，只在跑完时汇总一条）。
        """
        cacheable = self._cacheable_volumes(venue)
        partitions: dict[str, list[PaperStub]] | None = {v: [] for v in cacheable}
        buffered = 0
        discarded_unregistered = 0
        for page in self._iter_pages(venue, issue, oai_base, url):
            for record in page.records:
                vol = record.volume
                # DOI-卷号 partition（§4）：目标卷即时产出；其余已注册卷（含当前届）进
                # 缓存；未注册卷号/非 AAAI 形态（volume=None）不属任何届，真丢弃。
                if vol is None or (vol != volume and vol not in cacheable):
                    discarded_unregistered += 1
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
        if discarded_unregistered:
            log_event(
                "INFO",
                "aaai backfill records discarded for unregistered/unparseable volume",
                venue=venue.id,
                stage="enumerate",
                bucket=issue.label,
                volume=volume,
                discarded_unregistered_volume=discarded_unregistered,
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
        """可进缓存的卷集合 = 已注册卷全集（**含当前届**，P0-3 修复：不再排除 latest）。

        与旧版刻意不同（旧版排除当前届：当前届恒走回看窗、不吃缓存）——现在当前届也纳入，
        使任一卷（历史或当前）触发的单趟全量收割都顺带把当前届一并 partition 缓存，那份
        分区既是"当前届基线已建"的判据，**也是首次交付时真正吐给消费方的基线数据**
        （`_enumerate_current_edition` 的首次交付分支 chain 它 + 一次回看窗查询；此后的
        稳态轮次才只走回看窗真增量，新鲜度优先不变；结构改造对齐 econsoc
        `_cacheable_years`，适配 aaai 的卷号 partition 键）。
        """
        return frozenset(str(v) for v in _volume_map(venue).values())

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


def _stub_doi(stub: PaperStub) -> str | None:
    """`PaperStub` 的 DOI（`identifiers` 恒为单一 `(('doi', ...),)`，parse §3.3）。

    取不到时返回 None（防御性：走到当前届交付路径的 stub 其卷号本就由 DOI 解析而来，
    理论上必有 DOI；None 时按"不去重"处理，宁可多产一条也不静默吞掉记录）。
    """
    return dict(stub.identifiers).get("doi")


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
