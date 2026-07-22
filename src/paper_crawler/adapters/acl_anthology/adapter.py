"""ACL Anthology `SourceAdapter` 主体（design/adapters/acl-anthology.md §1/§3-§6）。

**AC-2.5 的验收载体。** family=`open_access`（`auth.level=none`，勘察 §7 全程匿名可读）。
能力 ``DISCOVER | ENUMERATE | RESOLVE | FETCH``（无 SEARCH，冻结协议无 search()，
arxiv.md §1 先例）。**获取策略阶梯的模范生**：GitHub 官方数据仓库 bulk 优先，
网站仅承担 PDF 全文兜底（§1 量化理由：`data/xml/{year}.{venue}.xml` 比对应
`/events/{venue}-{year}/` 站点页更小更结构化）。

阶段分工（§4）：

- `discover_timeline`：**唯一非零网络的 discover**（区别于 arxiv/openreview 的零网络
  discover）——`GET api.github.com/.../git/trees/master?recursive=1`（一次拿全
  `data/xml/` 清单，实现选择见 `tree.py` 模块 docstring）取得该 venue 的候选年份集，
  **进程内缓存 24h**（`_TREE_TTL_SECONDS`）。
- `enumerate_issue`：由 §discover 的进程内清单缓存把 (venue, year) 映射到实际文件名
  （**零网络**短路 legal-empty）；缓存冷（如单独进程只跑 enumerate 子任务）则回退
  新式→旧式**构造探测**（`_resolve_and_fetch_primary`）。**Findings 跨文件 join**：
  额外读 `{year}.findings.xml` 并按 `volume id == venue slug` 过滤（`_resolve_and_
  fetch_findings` + `_enumerate` 内的 volume 匹配）。两文件均 404（或清单证实均不存在）
  → legal-empty，返回空序列，非错误（§6）。
- `resolve_assets`：**纯构造零网络**。PDF：`https://aclanthology.org/{anthology_id}.pdf`；
  SI（`<attachment>`，[UNRESOLVED] 实验性——§4/§8）：`https://aclanthology.org/
  attachments/{local-filename}`（URL 前缀未经 LIVE HEAD 核实，见模块末尾风险注记）。
- `fetch_asset`：`HttpClient.stream` → `io.write_stream`；PDF 404（早期无 PDF /
  `<removed>`/`<retracted>`）由 `HttpClient` 直接映射 `GONE`，无需 adapter 重分类
  （区别于 raw 元数据 404，§6：勘察未见 aclanthology.org 对存在资源返回非 PDF 200 体
  的先例，故不设 HTML 嗅探兜底——与 arxiv/openreview 的差异点，如实注记）。
- `healthcheck`：`schema.rnc` GET 200 + 断言含 `Collection`/`Paper` 元素定义（同时验证
  `master` 分支名正确）＋ `aclanthology.org/` 首页 GET 200，均匿名无解析。

**失败模式重分类（§6，两条）**：
1. raw.githubusercontent.com 元数据 GET 404 → **legal-empty**（该 venue-year /
   Findings track 无数据，非错误）——`_get_raw_or_none` 吞掉 `GONE`。
2. api.github.com 403 → **`rate_limited`**（冻结 HttpClient 不透传响应头，无法读
   `x-ratelimit-remaining`，故域级无条件重分类；该域对公开仓库匿名读的 403 压倒性
   语义即限流，同 openreview 403→auth_expired 先例）——`_reclassify_github_403`。
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable, Iterable, Iterator

from paper_crawler.adapter import AdapterBase, AdapterFamily
from paper_crawler.adapters.acl_anthology import parse, tree
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

# --- 端点与常量（§2/§4/§9-★4）------------------------------------------------------------------

_REPO = "acl-org/acl-anthology"
_BRANCH = "master"  # 勘察 §1：default_branch 是 master，非 main（原稿证伪点）
_TREE_URL = f"https://api.github.com/repos/{_REPO}/git/trees/{_BRANCH}?recursive=1"
_RAW_BASE = f"https://raw.githubusercontent.com/{_REPO}/{_BRANCH}/data/xml/"
_SCHEMA_URL = f"{_RAW_BASE}schema.rnc"
_PDF_SITE = "https://aclanthology.org"
_HOMEPAGE_URL = f"{_PDF_SITE}/"

_TREE_TTL_SECONDS = 24 * 3600  # §4 discover 裁决：清单进程内缓存 24h 语义

_CONTACT_EMAIL_ENV = "PAPER_CRAWLER_CONTACT_EMAIL"
_PLACEHOLDER_EMAIL = "anonymous@paper-crawler.invalid"


def _default_user_agent() -> str:
    email = os.environ.get(_CONTACT_EMAIL_ENV, "").strip() or _PLACEHOLDER_EMAIL
    return build_user_agent(email)


# --- adapter 主体 ----------------------------------------------------------------------------


class AclAnthologyAdapter(AdapterBase):
    """ACL Anthology adapter（`open_access`/none）；Phase 2 服务 venue 仅 emnlp。"""

    adapter_id = "acl_anthology"
    family: AdapterFamily = "open_access"
    # §1 裁决：无 SEARCH。
    capabilities = (
        Capability.DISCOVER | Capability.ENUMERATE | Capability.RESOLVE | Capability.FETCH
    )
    # §5：三域共享 30rpm/并发1 预算；source_note 出处强制（types.RatePolicy）。
    default_rate = RatePolicy(
        requests_per_minute=30.0,
        burst=1,
        source_note=(
            "aclanthology.org has no robots.txt (404) and no Crawl-delay/rate-limit "
            "headers; raw.githubusercontent.com likewise unthrottled (Fastly edge); "
            "NFR-4 default <=1 req/2s/domain applied to both. api.github.com "
            "unauthenticated REST caps at 60 req/hr (x-ratelimit-limit observed), but "
            "the 24h in-process git-tree cache keeps discover well under that ceiling; "
            "research/site-survey/acl-anthology.md [LIVE] 2026-07-21 §1/§6/§7"
        ),
    )
    auth_requirement = AuthLevel.NONE
    # [0] 主域 = 限速/日志账本键（§5 表：raw.githubusercontent.com 标注"主域 [0]"）；
    # aclanthology.org/api.github.com 经 route_for 的 domains[1:] alias 落到同一桶。
    domains: tuple[str, ...] = ("raw.githubusercontent.com", "aclanthology.org", "api.github.com")
    # resolve_assets 读 anthology_id 拼 PDF URL + 逐条 attachment，零网络 → 豁免限速闸。
    resolve_offline = True

    def __init__(
        self, http: HttpClient | None = None, *, clock: Callable[[], float] = time.monotonic
    ) -> None:
        # http=None：首次网络调用惰性自建（同 arxiv/openreview 先例）。
        self._http = http
        self._clock = clock
        # git-tree 清单缓存（§4"进程内缓存 24h 语义"）：仅本 adapter 实例、单进程生命周期
        # 内有效——不做磁盘持久化，重进程即冷启动（enumerate 的构造探测回退兜底该场景）。
        self._tree_filenames: frozenset[str] | None = None
        self._tree_fetched_at: float | None = None

    def set_http_client(self, client: HttpClient) -> None:
        """注入组装好的 `HttpClient`（`adapter.HttpClientConsumer` 协议，同 arxiv 先例）。"""
        self._http = client

    def _client(self) -> HttpClient:
        if self._http is None:
            self._http = HttpClient(user_agent=_default_user_agent())
        return self._http

    # -- discover（唯一非零网络的 discover：git-tree 清单，24h 缓存）-------------------------

    def discover_timeline(self, venue: VenueSpec, since: str | None = None) -> Iterable[IssueRef]:
        """venue 候选年份集（git-tree 清单驱动）→ 逐年 `IssueRef`（§4 字段分解定死）。

        清单缺该年文件 ⟺ 无 `IssueRef`——缺届自然表达（NAACL/EACL 非年度举办场景，
        AC-8.3 跨 Phase 议题，本 adapter 只如实呈现"有数据的年"）。
        """
        filenames = self._ensure_tree()
        since_year = _year_prefix(since)
        years = tree.candidate_years(venue, filenames)
        return [
            IssueRef(
                venue_id=venue.id,
                volume=None,
                number=None,
                year=year,
                label=str(year),
                pub_date=None,
                paper_count_claimed=None,
            )
            for year in years
            if since_year is None or year >= since_year
        ]

    def _tree_is_fresh(self) -> bool:
        return (
            self._tree_filenames is not None
            and self._tree_fetched_at is not None
            and (self._clock() - self._tree_fetched_at) < _TREE_TTL_SECONDS
        )

    def _cached_tree_if_fresh(self) -> frozenset[str] | None:
        """enumerate 的**只读**缓存探测：缓存冷时返回 None，绝不由此触发一次清单拉取
        （§4"无清单时回退构造探测"——避免为单个 (venue,year) 查询付出整清单拉取的代价）。
        """
        return self._tree_filenames if self._tree_is_fresh() else None

    def _ensure_tree(self) -> frozenset[str]:
        """discover 专用：缓存新鲜则复用，否则拉取一次并刷新缓存。"""
        if self._tree_is_fresh():
            assert self._tree_filenames is not None  # _tree_is_fresh 已保证非 None
            return self._tree_filenames
        data = self._get_tree_bytes()
        filenames = tree.parse_tree_response(data)
        self._tree_filenames = filenames
        self._tree_fetched_at = self._clock()
        return filenames

    def _get_tree_bytes(self) -> bytes:
        try:
            return self._client().get_bytes(_TREE_URL)
        except CrawlerError as exc:
            raise _reclassify_github_403(exc) from exc

    # -- enumerate（清单/构造探测 → 主文件 + Findings join）----------------------------------

    def enumerate_issue(self, venue: VenueSpec, issue: IssueRef) -> Iterable[PaperStub]:
        """一 (venue,year) → 全部 PaperStub（主文件全 volume ∪ Findings join 子集）。

        `issue.year` 缺失（路由缺陷，非外部数据）→ `CrawlerError(CONFIG)`，急切校验；
        文件读取/解析在返回的生成器内惰性执行（同 openreview `_enumerate_pages` 先例）。
        """
        if issue.year is None:
            raise CrawlerError(
                ErrorClass.CONFIG, f"acl_anthology enumerate needs issue.year, got {issue!r}"
            )
        return self._enumerate(venue, issue.year)

    def _enumerate(self, venue: VenueSpec, year: int) -> Iterator[PaperStub]:
        emitted = 0
        primary_file: str | None = None
        findings_file: str | None = None

        primary = self._resolve_and_fetch_primary(venue, year)
        if primary is not None:
            primary_file, content = primary
            collection = parse.parse_collection_xml(content)
            for volume in collection.volumes:
                for paper in volume.papers:
                    yield parse.to_paper_stub(
                        collection.id,
                        volume.id,
                        paper,
                        track=volume.id,
                        volume_year=volume.year,
                        volume_month=volume.month,
                    )
                    emitted += 1

        findings = self._resolve_and_fetch_findings(venue, year)
        if findings is not None:
            findings_file, content = findings
            collection = parse.parse_collection_xml(content)
            # join 键 = volume id（== venue slug），非 meta/venue 文本（恒为字面
            # "findings"）——parse.py 模块 docstring 已详述该结构性陷阱。
            target = next((v for v in collection.volumes if v.id == venue.id), None)
            if target is not None:
                for paper in target.papers:
                    yield parse.to_paper_stub(
                        collection.id,
                        target.id,
                        paper,
                        track="findings",  # 固定字面值，见 parse.py 模块 docstring
                        volume_year=target.year,
                        volume_month=target.month,
                    )
                    emitted += 1

        log_event(
            "INFO",
            f"enumerate {venue.id} {year}: {emitted} paper(s) "
            f"(primary={primary_file!r} findings={findings_file!r})",
            venue=venue.id,
            stage="enumerate",
            domain=self.domains[0],
        )

    def _resolve_and_fetch_primary(self, venue: VenueSpec, year: int) -> tuple[str, bytes] | None:
        """(venue,year) 的主文件名解析 + 取回；两代候选均无 → None（legal-empty，§6）。"""
        cached = self._cached_tree_if_fresh()
        if cached is not None:
            filename = tree.resolve_primary_filename(venue, year, cached)
            if filename is None:
                return None  # 清单已证实两代候选均不存在——零网络短路
            return filename, self._get_raw(filename)

        # 缓存冷：新式→旧式构造探测（§4"无清单时回退构造探测"）。
        new_name = tree.new_style_filename(venue.id, year)
        content = self._get_raw_or_none(new_name)
        if content is not None:
            return new_name, content

        prefix = tree.legacy_prefix(venue)
        if prefix is not None:
            old_name = tree.old_style_filename(prefix, year)
            content = self._get_raw_or_none(old_name)
            if content is not None:
                return old_name, content

        return None  # 两代候选均 404（或无 legacy prefix 可试旧式）→ legal-empty

    def _resolve_and_fetch_findings(self, venue: VenueSpec, year: int) -> tuple[str, bytes] | None:
        """Findings 伴生文件的取回；不存在（该年无 Findings track）→ None（legal-empty）。"""
        filename = tree.findings_filename(year)
        cached = self._cached_tree_if_fresh()
        if cached is not None and filename not in cached:
            return None  # 零网络短路
        content = self._get_raw_or_none(filename)
        if content is None:
            return None
        return filename, content

    def _get_raw(self, filename: str) -> bytes:
        return self._client().get_bytes(_RAW_BASE + filename)

    def _get_raw_or_none(self, filename: str) -> bytes | None:
        """取回 bulk XML；404 → None（§6 raw 404→legal-empty 重分类，吞掉非重新抛出）。"""
        try:
            return self._get_raw(filename)
        except CrawlerError as exc:
            if exc.error_class is ErrorClass.GONE:
                return None
            raise

    # -- resolve（零网络纯构造）--------------------------------------------------------------

    def resolve_assets(
        self, venue: VenueSpec, paper: PaperStub, session: SessionHandle | None = None
    ) -> list[AssetPlan]:
        """PDF（恒产）+ SI（`<attachment>` 逐条，实验性——§4/§8 [UNRESOLVED]）→ `AssetPlan`。

        anthology_id 直接读 stub 的 `identifier('anthology')`，不重新发请求（真零网络）。
        """
        anthology_id = _anthology_identifier(paper)
        plans = [
            AssetPlan(
                kind=AssetKind.PDF,
                url=f"{_PDF_SITE}/{anthology_id}.pdf",
                expected_type="application/pdf",
                url_strategy=UrlStrategy.DIRECT,
                auth_needed=AuthLevel.NONE,
                version=None,
            )
        ]
        for key, value in paper.meta:
            if key == parse.META_ATTACHMENT:
                plans.append(
                    AssetPlan(
                        kind=AssetKind.SI,
                        url=f"{_PDF_SITE}/attachments/{value}",
                        expected_type="application/octet-stream",
                        url_strategy=UrlStrategy.DIRECT,
                        auth_needed=AuthLevel.NONE,
                        version=None,
                    )
                )
        return plans

    # -- fetch（流式）------------------------------------------------------------------------

    def fetch_asset(
        self, plan: AssetPlan, io: FetchIO, session: SessionHandle | None = None
    ) -> FetchResult:
        """`HttpClient.stream` → `io.write_stream`；404（早期无 PDF/removed/retracted）由
        `HttpClient` 直接映射 `GONE`，无需本层重分类（模块 docstring 已注记与 arxiv/
        openreview 的差异点：勘察未见 aclanthology.org 对存在资源返回非 PDF 200 体的
        先例，故不设 HTML 嗅探兜底）。`%PDF` 权威校验在 pipeline（冻结分工）。
        """
        stream = self._client().stream(plan.url)
        bytes_written, sha256 = io.write_stream(stream)
        return FetchResult(ok=True, bytes_written=bytes_written, sha256=sha256)

    # -- healthcheck（匿名、轻量，§4）---------------------------------------------------------

    def healthcheck(self, session: SessionHandle | None = None) -> HealthReport:
        """bulk 路径存活（`schema.rnc` 断言含 `Collection`/`Paper` 定义，同时验证
        `master` 分支名）＋ PDF 域存活（首页 200）。两项均无认证、无解析 landing。
        """
        try:
            schema_text = self._client().get_bytes(_SCHEMA_URL).decode("utf-8", errors="replace")
        except CrawlerError as exc:
            return HealthReport(
                healthy=False,
                detail=f"raw.githubusercontent.com/schema.rnc unreachable "
                f"({exc.error_class.value}): {exc}",
            )
        if (
            "Collection = element collection" not in schema_text
            or "Paper = element paper" not in schema_text
        ):
            return HealthReport(
                healthy=False,
                detail=(
                    "schema.rnc reachable but missing expected Collection/Paper element "
                    "definitions (schema drift, or branch/path pointed at the wrong ref)"
                ),
            )

        try:
            self._client().get_bytes(_HOMEPAGE_URL)
        except CrawlerError as exc:
            return HealthReport(
                healthy=False,
                detail=f"aclanthology.org unreachable ({exc.error_class.value}): {exc}",
            )

        return HealthReport(
            healthy=True,
            detail="raw.githubusercontent.com schema.rnc + aclanthology.org homepage reachable",
        )


# --- 模块级纯函数 -----------------------------------------------------------------------------


def _reclassify_github_403(exc: CrawlerError) -> CrawlerError:
    """api.github.com 403（冻结 HttpClient 默认 `no_entitlement`）→ `rate_limited`（§6）。

    该域对公开仓库匿名读的 403 压倒性语义即未认证限流耗尽（无"真无权限"场景，公开
    仓库不存在私有 403）；冻结 `HttpClient` 不透传响应头，无法读 `x-ratelimit-remaining`
    做更细粒度判定，故域级无条件重分类（openreview 403→auth_expired 同款先例）。
    其余 error_class 原样透传。
    """
    if exc.error_class is ErrorClass.NO_ENTITLEMENT:
        return CrawlerError(
            ErrorClass.RATE_LIMITED,
            f"api.github.com 403 (reclassified, unauthenticated rate limit "
            f"likely exhausted): {exc}",
            detail="github_403_ratelimit",
        )
    return exc


def _year_prefix(since: str | None) -> int | None:
    """`since`（'YYYY...' 或 None）→ 年下界 int；前 4 字符非年份 → None（不设界，同
    openreview `_year_prefix` 先例）。
    """
    if since is None or len(since) < 4 or not since[:4].isdigit():
        return None
    return int(since[:4])


def _anthology_identifier(paper: PaperStub) -> str:
    """从 stub 取 anthology 规范 id（scheme='anthology'）；缺失 → CONFIG（路由缺陷）。"""
    for scheme, value in paper.identifiers:
        if scheme == "anthology":
            return value
    raise CrawlerError(
        ErrorClass.CONFIG, f"paper has no anthology identifier: {paper.identifiers!r}"
    )


__all__ = ["AclAnthologyAdapter"]
