"""arXiv `SourceAdapter` 主体（design/adapters/arxiv.md §1/§3-§6）。

把 T4 三个纯逻辑件（`ids`/`buckets`/`parse`）与 T2 共享 `HttpClient` 组装成第一个
真实 adapter。能力口径（arxiv.md §1 裁决）：``DISCOVER | ENUMERATE | RESOLVE |
FETCH``——**不声明 SEARCH**（冻结 `SourceAdapter` 协议无 `search()`，订阅命中经
enumerate 增量 + 本地过滤达成，SEARCH 位统一推迟 Phase 6）。

阶段分工（arxiv.md §3）：

- `discover_timeline`：venue `quirks.inception`（'YYYY-MM'）→ 逐月虚拟桶（`buckets`），
  **零网络**；未声明 inception 回退全局起点 ``1991-08``。
- `enumerate_issue`：OAI-PMH `ListRecords`（``set`` = archive 级、子分类客户端过滤）
  + `resumptionToken` 翻页 + 月度桶窗口 ``from/until`` 构造 + 墓碑跳过数 obslog。
- `resolve_assets`：纯 URL 构造、**零网络**（``https://arxiv.org/pdf/{id}``，
  ``version=None`` 最新版语义）。
- `fetch_asset`：`HttpClient.stream` 取流交 `FetchIO.write_stream`；对 HTML 回应
  （撤稿/合并/不存在页）判 `GONE`（``%PDF`` 权威校验归 pipeline）。
- `healthcheck`：Query API 固定 canary id_list，规整化 title + primary_category 双字段比对。

**限速/礼貌**：`default_rate` = 1 req/3s（=20 req/min）带 ToU 出处（`RatePolicy.source_note`
强制）；`domains[0]='export.arxiv.org'` 作为三域共享的单一限速账本键（ToU「并发 1」，
三个官方端点共用一份 1req/3s 预算）。实际限速由 pipeline `acquire_and_wait` 依
`default_rate` 强制，不在本 adapter。

**HttpClient 注入**（brief）：`load_adapters()` 无参实例化——现无 config→UA 注入通道，
故 `__init__(http=None)`；`http=None` 时首次网络调用惰性自建（UA 走 D-014，email 从环境
变量 `PAPER_CRAWLER_CONTACT_EMAIL` 取、缺省用占位 `.invalid` 地址）。**测试注入
`HttpClient(transport=MockTransport(...))` 达成零真实网络**；真实在线（T5/T7 冒烟、
未来 CLI/watch 编排）应注入配置化 client 使 UA 携真实联系方式。
"""

from __future__ import annotations

import os
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from urllib.parse import urlencode

from paper_crawler.adapter import AdapterBase, AdapterFamily
from paper_crawler.adapters.arxiv import buckets, parse
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

# --- 端点与常量（arxiv.md §2 表）---------------------------------------------------------------

_OAI_ENDPOINT = "https://oaipmh.arxiv.org/oai"  # 2025-03 迁移后域（旧域 301）
_QUERY_ENDPOINT = "https://export.arxiv.org/api/query"
_PDF_BASE = "https://arxiv.org/pdf/"
_GLOBAL_INCEPTION = "1991-08"  # arXiv 全站起点；venue 未声明 quirks.inception 时回退
_PDF_MAGIC = b"%PDF-"

_CONTACT_EMAIL_ENV = "PAPER_CRAWLER_CONTACT_EMAIL"
# RFC 2606 保留 .invalid 顶级域——占位联系人不可能是真实地址（隐私安全），且明确
# 信号「该走配置化 client 注入真实 mailto」。仅在惰性自建且未设环境变量时使用。
_PLACEHOLDER_EMAIL = "anonymous@paper-crawler.invalid"


# --- User-Agent（D-014）----------------------------------------------------------------------
# `build_user_agent` 已上移中性模块 `paper_crawler.useragent`（T6-C2 backlog）；此处仅保留
# arxiv 专属的惰性自建兜底（env 联系人 + `.invalid` 占位）。


def _default_user_agent() -> str:
    """惰性自建 client 的 UA：email 从环境变量取（不硬编码），缺省用 `.invalid` 占位。"""
    email = os.environ.get(_CONTACT_EMAIL_ENV, "").strip() or _PLACEHOLDER_EMAIL
    return build_user_agent(email)


# --- canary（healthcheck，arxiv.md §6）-------------------------------------------------------


@dataclass(frozen=True)
class _Canary:
    """一条 healthcheck 锚点：跨域固定 id（带版本号查询）+ 规整化后期望 title/primary_category。"""

    base_id: str  # 去版本规范 id（比对键，与 ArxivRecord.base_id 对齐）
    query_id: str  # 带版本号的查询 id（id_list 参数用）
    title: str  # 空白规整化后的期望标题（ArxivRecord.title 已规整，直接等值比对）
    primary_category: str


# 真实稳定 canary（T7 在线冒烟 2026-07-22 实测选定，tests/online/test_arxiv_smoke.py 的
# canary 选样：跨域 cs.LG / econ.EM / q-fin.PR 各取一篇**主分类即该 category** 的早期原生
# 论文——年代久远且主分类正确，最稳定，贴合 arxiv.md §6 跨域语义）。title 为 Query API 实测
# 规整化后的标题（与 parse.parse_atom_feed 产物逐字对齐，healthcheck 直接等值比对）。
_CANARIES: tuple[_Canary, ...] = (
    _Canary(
        "cs/9901001",
        "cs/9901001v1",
        "TDLeaf(lambda): Combining Temporal Difference Learning with Game-Tree Search",
        "cs.LG",
    ),
    _Canary(
        "1801.00973",
        "1801.00973v1",
        "A New Wald Test for Hypothesis Testing Based on MCMC outputs",
        "econ.EM",
    ),
    _Canary(
        "1001.0615",
        "1001.0615v1",
        "Adaptive Wave Models for Option Pricing Evolution: "
        "Nonlinear and Quantum Schrödinger Approaches",
        "q-fin.PR",
    ),
)


# --- adapter 主体 ----------------------------------------------------------------------------


class ArxivAdapter(AdapterBase):
    """arXiv 全站 adapter（`open_access` family）；venue 按 category 切 `preprint_channel`。"""

    adapter_id = "arxiv"
    family: AdapterFamily = "open_access"
    # arxiv.md §1 裁决：无 SEARCH。
    capabilities = (
        Capability.DISCOVER | Capability.ENUMERATE | Capability.RESOLVE | Capability.FETCH
    )
    # 1 req/3s = 20 req/min（三域共享 ToU 预算）；source_note 出处强制（types.RatePolicy）。
    default_rate = RatePolicy(
        requests_per_minute=20.0,
        burst=1,
        source_note=(
            "arXiv API Terms of Use: 1 request / 3 seconds, single connection "
            "(export.arxiv.org / oaipmh.arxiv.org / arxiv.org); "
            "research/site-survey/arxiv.md [LIVE] 2026-07-20"
        ),
    )
    auth_requirement = AuthLevel.NONE
    # [0] 主域 = 限速/日志账本键（三域共享一份 1req/3s 预算，ToU「并发 1」）。
    domains: tuple[str, ...] = ("export.arxiv.org", "oaipmh.arxiv.org", "arxiv.org")

    def __init__(self, http: HttpClient | None = None) -> None:
        # http=None：首次网络调用时惰性自建（见模块 docstring 的注入说明）。
        self._http = http

    def set_http_client(self, client: HttpClient) -> None:
        """注入组装好的 `HttpClient`（`adapter.HttpClientConsumer` 协议）。

        CLI 经 `bind_http_client` 在 `load_adapters()` 后调用，把从 config 组装
        （UA 携 `[identity].email`）的共享 client 注入本 adapter——优先级
        **显式注入 > config > env**：注入覆盖 `__init__(http=None)` 的惰性 env 兜底
        （见模块 docstring）。`load_adapters()` 无参实例化后由此接通 config。
        """
        self._http = client

    def _client(self) -> HttpClient:
        if self._http is None:
            self._http = HttpClient(user_agent=_default_user_agent())
        return self._http

    # -- discover（零网络）-------------------------------------------------------------------

    def discover_timeline(self, venue: VenueSpec, since: str | None = None) -> Iterable[IssueRef]:
        """venue 起点 → 逐月虚拟桶 `IssueRef`（零网络）。

        起点 = ``quirks.inception``（'YYYY-MM'）或全局 ``1991-08``；`since`（可选下界，
        取前 7 字符 'YYYY-MM'）晚于起点时收窄起点（增量发现——零填充 YYYY-MM 的词典序
        即时间序）。终点 = 当前 UTC 月（含）。桶字段分解由 `buckets.month_buckets` 定死。
        """
        inception = _str_or_none(venue.quirks.get("inception")) or _GLOBAL_INCEPTION
        start = inception
        if since:
            since_month = since[:7]
            if since_month > inception:
                start = since_month
        until = datetime.now(UTC).date()
        return buckets.month_buckets(venue.id, start, until)

    # -- enumerate（OAI-PMH）----------------------------------------------------------------

    def enumerate_issue(self, venue: VenueSpec, issue: IssueRef) -> Iterable[PaperStub]:
        """月度桶 → OAI-PMH `ListRecords` 收割（子分类客户端过滤 + resumptionToken 翻页）。

        窗口 ``from/until`` 由桶月边界构造（当月桶 `until` 收窄到今日——watch 整窗语义）；
        ``set`` = archive 级、子分类经 `quirks.arxiv_category` 客户端过滤（见 `_oai_target`）。
        目标/窗口构造在此**急切**求值（非法桶早失败为 CONFIG）；翻页与网络在返回的生成器
        惰性执行。去重由下游 `identifier(scheme='arxiv')` 主键天然保证（重叠窗口不产生重复）。
        """
        oai_set, sub_category = _oai_target(venue)
        window = _oai_window(issue)
        if window is None:  # 空窗口（未来桶，理论不由 discover 产生）——零请求、空序列
            return iter(())
        frm, until = window
        url = _oai_list_url(oai_set, frm.isoformat(), until.isoformat())
        return self._enumerate_pages(venue, issue, sub_category, url)

    def _enumerate_pages(
        self, venue: VenueSpec, issue: IssueRef, sub_category: str | None, url: str
    ) -> Iterator[PaperStub]:
        client = self._client()
        while True:
            data = client.get_bytes(url)
            page = parse.parse_oai_page(data)
            if page.skipped_tombstones:
                # 墓碑可观测（T4 审查 Important）：venue/桶/跳过数落 obslog debug 事件。
                log_event(
                    "DEBUG",
                    "oai tombstones skipped",
                    venue=venue.id,
                    stage="enumerate",
                    bucket=issue.label,
                    skipped_tombstones=page.skipped_tombstones,
                )
            for record in page.records:
                # 子分类客户端过滤：按 primary_category（该 category 的「主渠道」语义）。
                if sub_category is not None and record.primary_category != sub_category:
                    continue
                yield parse.to_paper_stub(record)
            if page.resumption_token is None:
                return
            url = _oai_resume_url(page.resumption_token)

    # -- resolve（零网络）--------------------------------------------------------------------

    def resolve_assets(
        self, venue: VenueSpec, paper: PaperStub, session: SessionHandle | None = None
    ) -> list[AssetPlan]:
        """纯 URL 构造：单个 PDF `AssetPlan`（``https://arxiv.org/pdf/{id}``、最新版语义）。

        `version=None`（最新版）与 `(paper_id, kind, version)` 幂等键、re-resolve `_match_plan`
        复位稳定对齐。abs landing（HTML）本期不物化为可取回 asset——Phase 2 pipeline fetch
        仅落 pdf（`_asset_final_path` 非 pdf 即 CONFIG），materialize landing 推迟至全文库
        增强需求（见报告 concerns）。
        """
        arxiv_id = _arxiv_id_of(paper)
        return [
            AssetPlan(
                kind=AssetKind.PDF,
                url=f"{_PDF_BASE}{arxiv_id}",
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
        """`HttpClient.stream` → `io.write_stream`；HTML 回应（撤稿/合并/不存在页）判 `GONE`。

        `%PDF` 权威校验归 pipeline（冻结分工）；adapter 只负责把「PDF url 却回了 HTML 页」
        这一 arXiv 撤稿特征归为 `GONE`（而非让 pipeline 的 `%PDF` 校验误判为 INTEGRITY 重试）。
        HTTP 4xx（404/410）由 `HttpClient` 直接映射 `GONE`；HTTP 200 + HTML 体由本层嗅探。
        """
        stream = self._client().stream(plan.url)
        bytes_written, sha256 = io.write_stream(_gone_guarded_stream(stream))
        return FetchResult(ok=True, bytes_written=bytes_written, sha256=sha256)

    # -- healthcheck（Query API canary）-----------------------------------------------------

    def healthcheck(self, session: SessionHandle | None = None) -> HealthReport:
        """Query API 固定 canary id_list → 规整化 title + primary_category 双字段比对（§6）。

        双字段比对（非原串精确匹配）抗 flake：Atom title 跨行折行/作者改标题均已在解析层
        规整化，不误报 DRIFT。任一 canary 缺失或双字段任一漂移 → unhealthy。
        """
        url = _query_url([c.query_id for c in _CANARIES])
        try:
            data = self._client().get_bytes(url)
        except CrawlerError as exc:
            return HealthReport(
                healthy=False, detail=f"query api unreachable ({exc.error_class.value}): {exc}"
            )
        try:
            records = {rec.base_id: rec for rec in parse.parse_atom_feed(data)}
        except CrawlerError as exc:
            return HealthReport(healthy=False, detail=f"canary parse failed: {exc}")

        drifts = [msg for c in _CANARIES if (msg := _canary_drift(c, records.get(c.base_id)))]
        if drifts:
            return HealthReport(healthy=False, detail="canary drift — " + "; ".join(drifts))
        return HealthReport(
            healthy=True, detail=f"{len(_CANARIES)} canaries matched (title + primary_category)"
        )


# --- 模块级纯函数 -----------------------------------------------------------------------------


def _str_or_none(value: object) -> str | None:
    """venue.quirks 弹性值取字符串：非 str 或空白串 → None。"""
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return None


def _arxiv_id_of(paper: PaperStub) -> str:
    """从 stub 取 arXiv 规范 id（scheme='arxiv'）；缺失 → CONFIG（路由缺陷，非外部数据）。"""
    for scheme, value in paper.identifiers:
        if scheme == "arxiv":
            return value
    raise CrawlerError(ErrorClass.CONFIG, f"paper has no arxiv identifier: {paper.identifiers!r}")


def _oai_target(venue: VenueSpec) -> tuple[str, str | None]:
    """从 venue 推导 (OAI ``set``, 子分类过滤)。

    - 子分类过滤 = ``quirks.arxiv_category``（如 'cs.LG'，大小写敏感的权威来源）；缺省 None
      （不做子分类过滤、收割整 archive set）。
    - ``set`` = ``quirks.arxiv_set`` > `category` 的 archive 段（``'cs.LG'.split('.')[0]='cs'``、
      ``'q-fin.PR'→'q-fin'`` 可靠）> venue id 推导（仅简单 archive 可靠——`cs`/`econ`/`math`/
      `stat`；带连字符的 archive 如 `q-fin`/`hep-th` 无法从 snake_case id 复原，须 quirks）。
    """
    quirks = venue.quirks
    sub_category = _str_or_none(quirks.get("arxiv_category"))
    oai_set = _str_or_none(quirks.get("arxiv_set"))
    if oai_set is None and sub_category is not None:
        oai_set = sub_category.split(".", 1)[0]
    if oai_set is None:
        oai_set = _set_from_venue_id(venue.id)
    if oai_set is None:
        raise CrawlerError(
            ErrorClass.CONFIG,
            f"venue {venue.id!r} needs quirks.arxiv_set or quirks.arxiv_category "
            "to derive the OAI-PMH set (archive level)",
        )
    return oai_set, sub_category


def _set_from_venue_id(venue_id: str) -> str | None:
    """从 `arxiv_<archive>[_<subject>]` 形式的 venue id 推导 archive set（best-effort）。

    仅对无连字符的简单 archive 可靠（`arxiv_cs_lg`→`cs`）；带连字符的 archive（q-fin/hep-th/
    cond-mat）会被 snake_case 抹平，须显式 quirks——本函数对这些返回错误的段，故仅作为
    quirks 均缺省时的兜底。
    """
    prefix = "arxiv_"
    if not venue_id.startswith(prefix):
        return None
    rest = venue_id[len(prefix) :]
    if not rest:
        return None
    return rest.split("_", 1)[0]


def _oai_window(issue: IssueRef) -> tuple[date, date] | None:
    """月度桶 → (from, until) 日期对；当月桶 until 收窄到今日；空窗口（未来桶）→ None。

    桶月来自 `issue.year` + `issue.number`（'MM'）——`buckets` 定死的字段分解。缺 year 或
    number 非法月份 → CONFIG（enumerate 只接受月度桶）。
    """
    month = _month_of(issue)
    if issue.year is None or month is None:
        raise CrawlerError(
            ErrorClass.CONFIG,
            f"arxiv enumerate needs a monthly-bucket issue (year + number='MM'), got {issue!r}",
        )
    frm = date(issue.year, month, 1)
    until = min(_last_day_of_month(issue.year, month), datetime.now(UTC).date())
    if until < frm:
        return None
    return frm, until


def _month_of(issue: IssueRef) -> int | None:
    if issue.number is None:
        return None
    try:
        month = int(issue.number)
    except ValueError:
        return None
    return month if 1 <= month <= 12 else None


def _last_day_of_month(year: int, month: int) -> date:
    if month == 12:
        return date(year, 12, 31)
    return date(year, month + 1, 1) - timedelta(days=1)


def _oai_list_url(oai_set: str, frm: str, until: str) -> str:
    params = {
        "verb": "ListRecords",
        "metadataPrefix": "arXiv",
        "set": oai_set,
        "from": frm,
        "until": until,
    }
    return f"{_OAI_ENDPOINT}?{urlencode(params)}"


def _oai_resume_url(token: str) -> str:
    # OAI-PMH 规范：resumptionToken 与其他实参互斥，续页只带 verb + resumptionToken。
    return f"{_OAI_ENDPOINT}?{urlencode({'verb': 'ListRecords', 'resumptionToken': token})}"


def _query_url(id_list: list[str]) -> str:
    params = {"id_list": ",".join(id_list), "max_results": str(len(id_list))}
    return f"{_QUERY_ENDPOINT}?{urlencode(params)}"


def _gone_guarded_stream(chunks: Iterable[bytes]) -> Iterator[bytes]:
    """透传字节流，但先嗅探首字节：PDF 魔数放行；HTML 页（撤稿/合并/不存在）→ `GONE`。

    首个非 PDF 且形似 HTML 的响应体是 arXiv 撤稿/合并页的特征——归 `GONE`（资源终态、
    不重试），避免 pipeline 的 `%PDF` 校验把它误判为 INTEGRITY（重下）。既非 PDF 又不
    形似 HTML 的体透传，交 pipeline 的 `%PDF` 权威校验处置。
    """
    iterator = iter(chunks)
    head = bytearray()
    for chunk in iterator:
        head.extend(chunk)
        if len(head) >= len(_PDF_MAGIC):
            break
    stripped = bytes(head).lstrip()
    if not stripped.startswith(_PDF_MAGIC) and _looks_like_html(stripped):
        raise CrawlerError(
            ErrorClass.GONE,
            "arxiv returned an HTML page (withdrawn/merged/not-found), not a PDF",
        )
    if head:
        yield bytes(head)
    yield from iterator


def _looks_like_html(head: bytes) -> bool:
    low = head[:64].lower()
    return low.startswith(b"<!doctype html") or low.startswith(b"<html") or b"<html" in low


def _canary_drift(canary: _Canary, record: parse.ArxivRecord | None) -> str | None:
    """单条 canary 的漂移诊断；无漂移返回 None。"""
    if record is None:
        return f"{canary.base_id}: missing from response"
    if record.title != canary.title:  # ArxivRecord.title 已规整化，直接等值
        return f"{canary.base_id}: title drift"
    if record.primary_category != canary.primary_category:
        return (
            f"{canary.base_id}: primary_category drift "
            f"({record.primary_category!r} != {canary.primary_category!r})"
        )
    return None


__all__ = ["ArxivAdapter"]
