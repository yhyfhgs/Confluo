"""PMLR `SourceAdapter` 主体（design/adapters/pmlr.md §1/§3-§5）。

把零网络纯逻辑（`parse`）与 T2 共享 `HttpClient` 组装成 adapter。能力口径
（pmlr.md §1 裁决）：``DISCOVER | ENUMERATE | RESOLVE | FETCH``——**不声明
SEARCH**（冻结 `SourceAdapter` 协议无 `search()`，卷级枚举 + 本地过滤已满足
需求，先例 arxiv.md §1 / openreview.md §1）。

阶段分工（pmlr.md §3）：

- `discover_timeline`：venue `quirks.volume_map`（``dict[year:int → volume:int]``）
  逐条产出 IssueRef，**零网络**；`since` 为可选年份下界。
- `enumerate_issue`：卷 index 页（``v{N}/``，1 请求，主源）解析；**仅当** HTML
  0 条 div 时才额外 GET ``bibliography.bib``（辅源）计 entry 数消歧"合法空卷"
  （非错误）与"HTML 解析器失效"（`parse`）。
- `resolve_assets`：**纯读 `PaperStub.meta`**、零网络、域无关——`meta['pdf_url']`
  原样透传进 `AssetPlan.url`，不按卷号/年份推断域（B3 解法：托管迁移对本阶段
  透明，双域 `proceedings.mlr.press`/`raw.githubusercontent.com` 都只是带内值）。
- `fetch_asset`：`HttpClient.stream` 取流交 `FetchIO.write_stream`；`%PDF` 权威
  校验归 pipeline（冻结分工），本层不做 arxiv 式的 GONE 嗅探（PMLR 无撤稿页
  惯例，站点现象表 §5 无此行）。
- `healthcheck`：GET 站点根（全卷列表页），断言 200 + 含站点标题文本 + ≥1 条
  "Volume N Proceedings of" 锚点（pmlr.md §3.5；匿名可用）。3 样本"已知答案"
  比对（pmlr.md §6.4 canary）是**测试层**的解析回归断言，不在本方法内
  （design §3.5 与 §6.4 分属"运行期健康 ping"与"测试套件已知答案回归"两层，
  参见 tests/unit/test_pmlr_canary.py）。

**限速/礼貌**：`default_rate` = 1 req/2s（=30 req/min），双域各自声明同一保守
默认值（pmlr.md §4 表）；`domains=('proceedings.mlr.press', 'raw.githubusercontent.com')`——
pipeline `route_for` 对多域 adapter 统一把 `domains[1:]` alias 到 `domains[0]`
（framework 既有机制，见 pipeline/stages.py，非本 adapter 职责），故两域共用
一份 30rpm 预算，与 arxiv 三域共享同一账本同构。

**HttpClient 注入**（同 arxiv 先例）：`load_adapters()` 无参实例化——`__init__
(http=None)`，首次网络调用惰性自建（UA 走 D-014，email 从环境变量
`PAPER_CRAWLER_CONTACT_EMAIL` 取，缺失用占位 `.invalid` 地址）。**测试注入
`HttpClient(transport=MockTransport(...))` 达成零真实网络**；真实在线应注入
配置化 client 使 UA 携真实联系方式。
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterable

from paper_crawler.adapter import AdapterBase, AdapterFamily
from paper_crawler.adapters.pmlr import parse
from paper_crawler.errors import CrawlerError, ErrorClass
from paper_crawler.http import HttpClient
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

# --- 端点与常量（pmlr.md §2/§3 表）------------------------------------------------------------

SITE_ROOT = parse.SITE_ROOT  # "https://proceedings.mlr.press/"（唯一"卷 base URL"）
_BIB_PATH_TMPL = "v{volume}/assets/bib/bibliography.bib"
_VOLUME_PATH_TMPL = "v{volume}/"

_HEALTHCHECK_TITLE_TEXT = "Proceedings of Machine Learning Research"
_VOLUME_ANCHOR_RE = re.compile(r"Volume\s+\d+\s+Proceedings\s+of")

_CONTACT_EMAIL_ENV = "PAPER_CRAWLER_CONTACT_EMAIL"
# RFC 2606 保留 .invalid 顶级域——占位联系人不可能是真实地址，且明确信号「该走
# 配置化 client 注入真实 mailto」。仅在惰性自建且未设环境变量时使用（同 arxiv 先例）。
_PLACEHOLDER_EMAIL = "anonymous@paper-crawler.invalid"


def _default_user_agent() -> str:
    """惰性自建 client 的 UA：email 从环境变量取（不硬编码），缺省用 `.invalid` 占位。"""
    email = os.environ.get(_CONTACT_EMAIL_ENV, "").strip() or _PLACEHOLDER_EMAIL
    return build_user_agent(email)


# --- adapter 主体 ----------------------------------------------------------------------------


class PmlrAdapter(AdapterBase):
    """PMLR（Proceedings of Machine Learning Research）adapter（`open_access` family）。

    服务 venue：本 adapter 只覆盖各会议的 **PMLR 时代**（ICML 2013+/v28、AISTATS
    2007+/v2、COLT 2011+/v19、UAI 2020+/v124、CoRL 2017+/v78）；多段 era venue
    （COLT/UAI）的 era 边界解析是 Registry/框架职责，不在本 adapter（pmlr.md §1）。
    """

    adapter_id = "pmlr"
    family: AdapterFamily = "open_access"
    # pmlr.md §1 裁决：无 SEARCH。
    capabilities = (
        Capability.DISCOVER | Capability.ENUMERATE | Capability.RESOLVE | Capability.FETCH
    )
    # 1 req/2s = 30 req/min；两域各自声明同一保守默认值，pipeline route_for 把
    # domains[1:] alias 到 domains[0]，实际共用一份预算（模块 docstring）。
    default_rate = RatePolicy(
        requests_per_minute=30.0,
        burst=1,
        source_note=(
            "proceedings.mlr.press 与 raw.githubusercontent.com 均无官方文档化速率数字"
            "（两域 robots.txt 均 404，无禁则）→ NFR-4 保守默认 1 req/2s/domain；"
            "research/site-survey/pmlr.md [LIVE] 2026-07-22"
        ),
    )
    auth_requirement = AuthLevel.NONE
    # [0] 主域（元数据 + 旧卷 PDF）；[1] 新卷 PDF 托管（2024 起，边界按上传时间非卷号）。
    domains: tuple[str, ...] = ("proceedings.mlr.press", "raw.githubusercontent.com")

    def __init__(self, http: HttpClient | None = None) -> None:
        # http=None：首次网络调用时惰性自建（见模块 docstring 的注入说明）。
        self._http = http

    def set_http_client(self, client: HttpClient) -> None:
        """注入组装好的 `HttpClient`（`adapter.HttpClientConsumer` 协议，同 arxiv 先例）。"""
        self._http = client

    def _client(self) -> HttpClient:
        if self._http is None:
            self._http = HttpClient(user_agent=_default_user_agent())
        return self._http

    # -- discover（零网络）-------------------------------------------------------------------

    def discover_timeline(self, venue: VenueSpec, since: str | None = None) -> Iterable[IssueRef]:
        """`quirks.volume_map`（year→volume）逐条产出 IssueRef（零网络，pmlr.md §3.1）。

        字段分解定死：``volume``=裸数字串、``number``=None（PMLR 只有卷无期）、
        ``year``=int、``label``=f'v{volume}'、``pub_date``=None、
        ``paper_count_claimed``=None（discover 阶段无权威口径，enumerate 回填）。
        `since` 是可选年份下界，给出时只产 ``year >= int(since)`` 的 Issue。
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
                label=f"v{volume}",
                pub_date=None,
                paper_count_claimed=None,
            )

    # -- enumerate（卷 index HTML 主源 + bib 0-div 消歧辅源）---------------------------------

    def enumerate_issue(self, venue: VenueSpec, issue: IssueRef) -> Iterable[PaperStub]:
        """单请求卷级抓取（pmlr.md §3.2）：HTML>0 单请求信任；HTML=0 时抓 bib 消歧。

        - HTML div 数 >0：不抓 bib，直接产出（常态单请求）。
        - HTML div 数 ==0 且 bib entry 数 ==0：**合法空卷**，正常完成、产 0 stub
          （非错误——占位/未上传完的卷）。
        - HTML div 数 ==0 且 bib entry 数 >0：HTML 解析器在非空卷读出 0，判定
          `parse`（结构漂移信号）。
        - bib 请求本身失败（4xx/5xx/timeout）：不武断判空，HttpClient 的错误
          分类原样传播（`transient`/`rate_limited`/`gone` 等）。
        """
        volume = _issue_volume(issue, venue)
        data = self._client().get_bytes(f"{SITE_ROOT}{_VOLUME_PATH_TMPL.format(volume=volume)}")
        papers = parse.parse_volume_index(data)
        if papers:
            return [parse.to_paper_stub(p, volume=volume, year=issue.year) for p in papers]

        bib_count = self._bib_entry_count(volume)
        if bib_count > 0:
            raise CrawlerError(
                ErrorClass.PARSE,
                f"pmlr v{volume}: HTML volume index has 0 papers but bibliography.bib has "
                f"{bib_count} entries — HTML parser likely broken, not a legitimately "
                "empty volume",
            )
        return []  # 合法空卷：HTML 与 bib 均为 0，正常完成（非错误）。

    def _bib_entry_count(self, volume: str) -> int:
        url = f"{SITE_ROOT}{_BIB_PATH_TMPL.format(volume=volume)}"
        data = self._client().get_bytes(url)
        return parse.count_bib_entries(data)

    # -- resolve（纯读 meta，零网络，域无关）--------------------------------------------------

    def resolve_assets(
        self, venue: VenueSpec, paper: PaperStub, session: SessionHandle | None = None
    ) -> list[AssetPlan]:
        """纯读 `PaperStub.meta['pdf_url']` 构造 AssetPlan（pmlr.md §3.3，B3 解法）。

        **域无关**：url 取 meta 内带内值原样——无论 `proceedings.mlr.press` 还是
        `raw.githubusercontent.com` 都透传，绝不按卷号/年份推断域、绝不在 resolve
        阶段重发请求。meta 缺 `pdf_url`（不应发生）→产 0 个 pdf plan（非错误，
        openreview note-no-pdf 先例）。
        """
        pdf_url = dict(paper.meta).get("pdf_url")
        if not pdf_url:
            return []
        return [
            AssetPlan(
                kind=AssetKind.PDF,
                url=pdf_url,
                expected_type="application/pdf",
                url_strategy=UrlStrategy.DIRECT,
                auth_needed=AuthLevel.NONE,
                version=None,
            )
        ]

    # -- fetch（流式）------------------------------------------------------------------------

    def fetch_asset(
        self, plan: AssetPlan, io: FetchIO, session: SessionHandle | None = None
    ) -> FetchResult:
        """`HttpClient.stream` → `io.write_stream`（pmlr.md §3.4）。

        `%PDF` 权威校验归 pipeline（冻结分工）；GitHub raw 的 `Content-Type:
        application/octet-stream`（非 `application/pdf`）对流式下载无影响——
        本层不依赖 Content-Type，也不做 arxiv 式的 HTML 撤稿页嗅探（PMLR 站点
        现象表 §5 无撤稿页形态，404/410 已由 HttpClient 统一映射 `gone`）。
        """
        stream = self._client().stream(plan.url)
        bytes_written, sha256 = io.write_stream(stream)
        return FetchResult(ok=True, bytes_written=bytes_written, sha256=sha256)

    # -- healthcheck（站点根匿名 ping）--------------------------------------------------------

    def healthcheck(self, session: SessionHandle | None = None) -> HealthReport:
        """GET 站点根，断言 200 + 含标题文本 + ≥1 条卷锚点（pmlr.md §3.5）。

        匿名可用（无 auth）；此页亦是 track 新卷探测源（design/08 §4，不在本
        adapter 范围）。3 样本已知答案回归比对是测试层职责（§6.4，见模块
        docstring），不在本方法。

        **两个断言都对 `parse.clean_text()` 转换后的可见文本匹配，不对带标签
        原始 HTML 做正则**（独立审查 2026-07-22 发现并修复）：真实站点根页
        647 条卷条目均为 ``<a href="v235"><b>Volume 235</b></a> Proceedings of
        ICML 2024``——"Volume N" 被 ``<b>`` 包裹、锚点在 ``</b>`` 处提前闭合，
        "Proceedings of…" 落在锚点外的纯文本，与"Volume N"之间隔着
        ``</b></a> `` 标签边界；对原始带标签文本直接 `\\s+` 正则永不匹配，会
        让生产环境的 pmlr 站点被恒定误报 unhealthy（见 `clean_text` 文档字符串）。
        """
        try:
            text = self._client().get_text(SITE_ROOT)
        except CrawlerError as exc:
            return HealthReport(
                healthy=False, detail=f"site root unreachable ({exc.error_class.value}): {exc}"
            )
        visible = parse.clean_text(text)
        if _HEALTHCHECK_TITLE_TEXT not in visible:
            return HealthReport(
                healthy=False, detail=f"site root missing expected title text {visible!r}"[:200]
            )
        if _VOLUME_ANCHOR_RE.search(visible) is None:
            return HealthReport(
                healthy=False, detail="site root has no 'Volume N Proceedings of' anchor"
            )
        return HealthReport(
            healthy=True, detail="site root reachable with expected title + volume anchor"
        )


# --- 模块级纯函数 -----------------------------------------------------------------------------


def _volume_map(venue: VenueSpec) -> dict[int, int]:
    """从 `venue.quirks['volume_map']` 取 year→volume 映射；结构非法 → `CONFIG`。

    键值宽容强转 `int()`（PyYAML 对无引号整数键给 int，有引号则给 str；两种
    形态都接受）——非法条目响亮报错而非静默丢弃（纯本地判断，config 语义）。
    """
    raw = venue.quirks.get("volume_map")
    if not isinstance(raw, dict) or not raw:
        raise CrawlerError(
            ErrorClass.CONFIG,
            f"venue {venue.id!r} 缺少非空的 quirks.volume_map（year→volume，pmlr.md §3.1）",
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


def _parse_since_year(since: str | None) -> int | None:
    """`since`（可选年份下界字符串）→ int；非法格式 → `CONFIG`。"""
    if since is None:
        return None
    try:
        return int(since)
    except ValueError as exc:
        raise CrawlerError(ErrorClass.CONFIG, f"invalid since year: {since!r}") from exc


def _issue_volume(issue: IssueRef, venue: VenueSpec) -> str:
    """校验并取出 `issue.volume`（裸数字串，须在 venue 的 volume_map 中注册）。

    两类 `config`：形态非法（非 None 且非纯数字串——foreign/畸形 IssueRef，如
    误传 arxiv 月度桶）、以及卷号未在 `volume_map` 注册（新一届未登记，pmlr.md
    §5"卷号未在 volume_map"行，提示走 track 流程 D-012）。
    """
    if issue.volume is None or not issue.volume.isdigit():
        raise CrawlerError(
            ErrorClass.CONFIG,
            f"pmlr enumerate needs IssueRef.volume as a bare digit string, got {issue.volume!r}",
        )
    volume_map = _volume_map(venue)
    if int(issue.volume) not in volume_map.values():
        raise CrawlerError(
            ErrorClass.CONFIG,
            f"volume {issue.volume!r} not registered in venue {venue.id!r} "
            "quirks.volume_map (unregistered edition — use `crawler track`, D-012)",
        )
    return issue.volume


__all__ = ["PmlrAdapter"]
