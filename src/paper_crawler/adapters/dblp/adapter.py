"""DBLP `SourceAdapter` 主体（design/adapters/aggregators.md §1/§3/§4/§5.2）。

把零网络纯逻辑（`parse`）与共享 `HttpClient` 组装成 adapter。能力口径
（aggregators.md §1 表）：``DISCOVER | ENUMERATE``——**无 SEARCH**（`/search`、
`/search/publ`、`/rec/{xml,bib,ris,nt,rdf}` 是 robots `Disallow` 禁区，见下方
"合规红线"）、**无 RESOLVE/FETCH**（五源聚合 adapter 统一无 FETCH 契约，
plan §2-3；本 adapter 只产元数据 `PaperStub` 流，不下载全文——未声明的方法
沿用 `AdapterBase` 默认 `CapabilityNotSupported`，本文件不覆写）。

**合规红线（AC-0.5，aggregators.md §3 "DBLP robots 红线框"，最高优先级约束）**：
本文件的全部请求构造只落在两类允许区路径——conf 索引页 ``/db/conf/{acr}/``
与卷 XML ``/db/conf/{acr}/{slug}.xml``；**代码中不出现任何对 `/search`、
`/search/publ`、`/rec/{xml,bib,ris,nt,rdf}` 路径的请求构造**。限速
``≥4s/req`` 并发 1（`default_rate`，出处 robots `Crawl-delay: 4`）。

阶段分工（aggregators.md §5.2）：

- `discover_timeline`：**非零网络**（区别于 arxiv/pmlr/cvf 的零网络
  discover，同 acl_anthology "唯一非零网络 discover" 先例）——conf 索引页
  `GET /db/conf/{acr}/` 解析出该会议**实际存在**的卷链接（`parse.
  parse_conf_index`）。**不得拼接猜测 key**：venue 命名不规则（`nips2023`
  404，真实 slug 是 `neurips2023`）是本方法存在的直接理由，见 `parse.py`
  模块 docstring。
- `enumerate_issue`：单请求整取卷 XML（**无分页**，aggregators.md §5.2：
  "分页：无。dblp 逐卷一次性整取"）→ `parse.parse_volume_xml` → 逐
  `inproceedings` 经 `parse.to_paper_stub`（含 ee→DOI 护栏）产出
  `PaperStub` 流。卷 key 404 时按 §5.2 错误映射表做**一次性自愈**：回索引页
  重发现该年份的实际 slug 并重试一次；重试仍失败（含"索引页也找不到该年份"）
  → `ErrorClass.PARSE`（"命名超预期"，`_recover_after_gone`）。
- `healthcheck`：固定 canary `conf/icml/icml2023`（aggregators.md §5.2/§7；
  "已知答案"精确比对锚点因未做真实网络录制而 **[PENDING]**——见
  `_MIN_HEALTHY_RECORDS` 处注释与 `tests/unit/test_dblp_canary.py` 模块
  docstring）。只做**结构性**判定（200 可达 + 能解析出 ≥1 条记录 + 首条记录
  key/title 非空 + 记录数不低于一个保守下限），**不**把未经现场核验的标题/
  计数精确值硬编码为生产判据——防止把"合成假设"当成盲区（Phase 2 教训，
  aggregators.md §10 "canary 存在性纪律"）。

**限速/礼貌**：`default_rate` = 15 rpm（= 60s/4s，robots `Crawl-delay: 4`
折算）、`burst=1`、`domains=("dblp.org",)` 单域。实际限速由 pipeline
`acquire_and_wait` 依 `default_rate` 强制，加上 `HttpClient` 的逐请求限速闸
（C4 修复先例：discover/enumerate 内部即使发出多个请求——如 404 自愈路径的
"再取一次索引页 + 重试一次卷 XML"——也逐请求过闸，不绕过 4s 间隔）。

**HttpClient 注入**（先例 arxiv/pmlr/cvf/acl_anthology）：`load_adapters()`
无参实例化——`__init__(http=None)`，首次网络调用惰性自建（UA 走 D-014，email
从环境变量 `PAPER_CRAWLER_CONTACT_EMAIL` 取，缺省用占位 `.invalid` 地址）。
测试注入 `HttpClient(transport=MockTransport(...))` 达成零真实网络；真实在线
（T5 冒烟/未来 CLI）应注入配置化 client 使 UA 携真实联系方式。
"""

from __future__ import annotations

import os
from collections.abc import Iterable

from paper_crawler.adapter import AdapterBase, AdapterFamily
from paper_crawler.adapters.dblp import parse
from paper_crawler.errors import CrawlerError, ErrorClass
from paper_crawler.http import HttpClient
from paper_crawler.obslog import log_event
from paper_crawler.types import (
    AuthLevel,
    Capability,
    HealthReport,
    IssueRef,
    PaperStub,
    RatePolicy,
    SessionHandle,
    VenueSpec,
)
from paper_crawler.useragent import build_user_agent

# --- 端点（aggregators.md §5.2 表；合规红线：仅这两类允许区路径）------------------------------

_BASE = "https://dblp.org"
_CONF_PREFIX = "conf/"  # venue.identifiers['dblp_key'] 的约定前缀（如 'conf/icml'）

_CONTACT_EMAIL_ENV = "PAPER_CRAWLER_CONTACT_EMAIL"
# RFC 2606 保留 .invalid：占位联系人不可能是真实地址（隐私安全），且明确信号
# 「该走配置化 client 注入真实 mailto」。仅在惰性自建且未设环境变量时使用
# （同 arxiv/pmlr/cvf 先例）。
_PLACEHOLDER_EMAIL = "anonymous@paper-crawler.invalid"

# healthcheck 固定 canary（aggregators.md §5.2/§7）。记录数下限是**保守占位**，
# 不是精确锚点——真实 icml2023.xml 的记录数/首条 title 未经本次实现的在线核验
# （[PENDING]，实现期/T5 在线冒烟捕获后按 UPDATE_GOLDEN 纪律补精确比对，同
# aggregators.md §5.1/§5.3/§5.4/§7 各 [PENDING] 行的处置口径一致）；ICML 每届
# 收录论文以千计，50 是"明显未结构性损坏"的极低安全阈值，不会因真实值围绕某个
# 具体数字波动而误报 DRIFT。
_HEALTHCHECK_ACR = "icml"
_HEALTHCHECK_SLUG = "icml2023"
_MIN_HEALTHY_RECORDS = 50


def _default_user_agent() -> str:
    """惰性自建 client 的 UA：email 从环境变量取（不硬编码），缺省用 `.invalid` 占位。"""
    email = os.environ.get(_CONTACT_EMAIL_ENV, "").strip() or _PLACEHOLDER_EMAIL
    return build_user_agent(email)


def _index_url(acr: str) -> str:
    return f"{_BASE}/db/conf/{acr}/"


def _volume_xml_url(acr: str, slug: str) -> str:
    return f"{_BASE}/db/conf/{acr}/{slug}.xml"


def _acr_of(venue: VenueSpec) -> str:
    """从 `venue.identifiers['dblp_key']`（约定形如 `'conf/icml'`）派生 DBLP acr。

    该字段是既有约定（`make_pmlr_venue`/`make_openreview_venue` 等既已在用，
    如 `identifiers={'dblp_key': 'conf/icml'}`），非本 adapter 新造；缺失/形态
    不符 → `CrawlerError(CONFIG)`（venue 配置缺陷，非外部数据问题，早失败）。
    """
    raw = venue.identifiers.get("dblp_key")
    if not isinstance(raw, str) or not raw.strip():
        raise CrawlerError(
            ErrorClass.CONFIG,
            f"venue {venue.id!r} is missing identifiers.dblp_key "
            "(needed to derive the DBLP conf acronym, e.g. 'conf/icml')",
        )
    dblp_key = raw.strip()
    if not dblp_key.startswith(_CONF_PREFIX):
        raise CrawlerError(
            ErrorClass.CONFIG,
            f"venue {venue.id!r} identifiers.dblp_key={dblp_key!r} does not start with "
            f"{_CONF_PREFIX!r}",
        )
    acr = dblp_key[len(_CONF_PREFIX) :].strip("/")
    if not acr:
        raise CrawlerError(
            ErrorClass.CONFIG,
            f"venue {venue.id!r} identifiers.dblp_key={dblp_key!r} has an empty acronym "
            f"after stripping {_CONF_PREFIX!r}",
        )
    return acr


def _year_prefix(since: str | None) -> int | None:
    """`since`（'YYYY...' 或 None）→ 年下界 int；前 4 字符非年份 → None（不设界，先例）。"""
    if since is None or len(since) < 4 or not since[:4].isdigit():
        return None
    return int(since[:4])


# --- adapter 主体 ----------------------------------------------------------------------------


class DblpAdapter(AdapterBase):
    """DBLP 会议元数据主干 adapter（`aggregator` family；无 FETCH，只产元数据）。"""

    adapter_id = "dblp"
    family: AdapterFamily = "aggregator"
    # aggregators.md §1 裁决：DISCOVER|ENUMERATE，无 SEARCH（robots 禁区）、
    # 无 RESOLVE/FETCH（五源聚合 adapter 统一无 FETCH 契约，plan §2-3）。
    capabilities = Capability.DISCOVER | Capability.ENUMERATE
    default_rate = RatePolicy(
        requests_per_minute=15.0,  # 60s / 4s，见下方 source_note
        burst=1,
        source_note=(
            "dblp.org/robots.txt: 'Crawl-delay: 4' (site-wide; concurrency 1); "
            "'Disallow: /search, /search/publ, /rec/{xml,bib,ris,nt,rdf}' (SEARCH 与逐条 "
            "/rec/xml 禁区，本 adapter 只走 /db/conf/** 允许区); "
            "docs/design/adapters/aggregators.md §3/§4 [LIVE] 2026-07-22 (D-021); "
            "docs/research/site-survey/aggregators-unpaywall-dblp-core.md [LIVE] 2026-07-22"
        ),
    )
    auth_requirement = AuthLevel.NONE
    domains: tuple[str, ...] = ("dblp.org",)

    def __init__(self, http: HttpClient | None = None) -> None:
        # http=None：首次网络调用时惰性自建（见模块 docstring 的注入说明）。
        self._http = http

    def set_http_client(self, client: HttpClient) -> None:
        """注入组装好的 `HttpClient`（`adapter.HttpClientConsumer` 协议，先例 arxiv/pmlr）。"""
        self._http = client

    def _client(self) -> HttpClient:
        if self._http is None:
            self._http = HttpClient(user_agent=_default_user_agent())
        return self._http

    # -- discover（非零网络：conf 索引页发现实际卷 key）--------------------------------------

    def discover_timeline(self, venue: VenueSpec, since: str | None = None) -> Iterable[IssueRef]:
        """conf 索引页 → 该会议已发现的届列表（`IssueRef`，字段分解定死）。

        字段分解：`volume`/`number` 恒 None（DBLP 卷概念用 `label` 承载真实
        slug，非数字卷号语义，区别于 pmlr）；`year`=int；`label`=索引页发现的
        真实 slug（`enumerate_issue` 据此构造 XML URL，**绝不重新猜测**）；
        `pub_date`/`paper_count_claimed` 恒 None（discover 阶段无权威口径，
        计数需整取卷 XML 才知道，同 pmlr "enumerate 回填"先例）。`since`
        （可选年份下界字符串）只做下界裁剪。
        """
        acr = _acr_of(venue)
        links = self._fetch_index_links(acr)
        since_year = _year_prefix(since)
        return [
            IssueRef(
                venue_id=venue.id,
                volume=None,
                number=None,
                year=link.year,
                label=link.slug,
                pub_date=None,
                paper_count_claimed=None,
            )
            for link in links
            if since_year is None or link.year >= since_year
        ]

    def _fetch_index_links(self, acr: str) -> tuple[parse.DblpVolumeLink, ...]:
        data = self._client().get_bytes(_index_url(acr))
        return parse.parse_conf_index(data)

    # -- enumerate（单请求整取卷 XML + 404 一次性自愈）----------------------------------------

    def enumerate_issue(self, venue: VenueSpec, issue: IssueRef) -> Iterable[PaperStub]:
        """一届（`issue.label`=slug）→ 该卷全部论文的 `PaperStub`（§5.2 字段映射）。

        急切求值（非法 issue 早失败为 CONFIG；网络与解析在本方法内同步完成——
        DBLP 无需像 arxiv/openreview 那样翻页，单请求即拿到全卷，同 cvf/pmlr
        "列表页一次拿全"的设计语言）。`issue.label` 必须来自 `discover_timeline`
        （真实发现的 slug），不接受调用方自行拼接猜测。
        """
        if issue.label is None or issue.year is None:
            raise CrawlerError(
                ErrorClass.CONFIG,
                "dblp enumerate needs IssueRef.label (real volume slug, from "
                f"discover_timeline) and .year, got {issue!r}",
            )
        acr = _acr_of(venue)
        slug = issue.label
        try:
            data = self._fetch_volume_xml(acr, slug)
        except CrawlerError as exc:
            if exc.error_class is not ErrorClass.GONE:
                raise
            data = self._recover_after_gone(acr, issue.year, slug, exc)

        volume = parse.parse_volume_xml(data)
        if volume.skipped_missing_title:
            log_event(
                "WARNING",
                f"dblp {acr}/{slug}: skipped {volume.skipped_missing_title} inproceedings "
                "record(s) missing <title>",
                venue=venue.id,
                stage="enumerate",
                domain=self.domains[0],
            )
        log_event(
            "INFO",
            f"enumerate {acr}/{slug}: {len(volume.records)} paper(s) parsed (paper_count_claimed)",
            venue=venue.id,
            stage="enumerate",
            domain=self.domains[0],
        )
        return [parse.to_paper_stub(record, volume.container_dois) for record in volume.records]

    def _fetch_volume_xml(self, acr: str, slug: str) -> bytes:
        return self._client().get_bytes(_volume_xml_url(acr, slug))

    def _recover_after_gone(
        self, acr: str, year: int, stale_slug: str, original: CrawlerError
    ) -> bytes:
        """卷 key 404 的一次性自愈（§5.2 错误映射表："404→gone→回索引页重发现一次，
        再失败→parse（命名超预期）"）。

        回索引页重取该年份的候选 slug（排除已知失败的 `stale_slug`，避免重复
        白打一次同样会 404 的请求——≥4s/req 下每一次请求都值得省）；逐候选重试
        一次卷 XML 取回，任一成功即返回。索引页取回本身失败、或年份无候选、或
        全部候选仍失败——三种情形统一归为 `ErrorClass.PARSE`（不是原样的
        `GONE`：走到这一步说明"资源单纯消失"这一简单解释已被证伪，命名假设
        超出预期，值得 canary 标红而非被 pipeline 的 GONE 语义悄悄归档）。
        """
        try:
            links = self._fetch_index_links(acr)
        except CrawlerError as exc:
            raise CrawlerError(
                ErrorClass.PARSE,
                f"dblp {acr}/{stale_slug}.xml gone (404) and index re-discovery failed too "
                f"({exc.error_class.value}) — naming beyond expectation",
                detail=str(original),
            ) from original

        candidates = [link.slug for link in links if link.year == year and link.slug != stale_slug]
        if not candidates:
            raise CrawlerError(
                ErrorClass.PARSE,
                f"dblp {acr}/{stale_slug}.xml gone (404); re-discovered index has no (other) "
                f"volume for year {year} — naming beyond expectation",
                detail=str(original),
            ) from original

        last_error: CrawlerError = original
        for candidate_slug in candidates:
            try:
                return self._fetch_volume_xml(acr, candidate_slug)
            except CrawlerError as exc:
                last_error = exc
                continue
        raise CrawlerError(
            ErrorClass.PARSE,
            f"dblp {acr}/{stale_slug}.xml gone (404); re-discovered candidate(s) "
            f"{candidates!r} for year {year} also failed — naming beyond expectation",
            detail=str(last_error),
        ) from last_error

    # -- healthcheck（固定 canary，结构性判定，§5.2/§7）---------------------------------------

    def healthcheck(self, session: SessionHandle | None = None) -> HealthReport:
        """固定卷 `conf/icml/icml2023` → 结构性判定（模块 docstring 已述判据/理由）。"""
        url = _volume_xml_url(_HEALTHCHECK_ACR, _HEALTHCHECK_SLUG)
        try:
            data = self._client().get_bytes(url)
        except CrawlerError as exc:
            return HealthReport(
                healthy=False,
                detail=f"{_HEALTHCHECK_SLUG}.xml unreachable ({exc.error_class.value}): {exc}",
            )
        try:
            volume = parse.parse_volume_xml(data)
        except CrawlerError as exc:
            return HealthReport(
                healthy=False, detail=f"{_HEALTHCHECK_SLUG}.xml parse failed: {exc}"
            )

        if not volume.records:
            return HealthReport(
                healthy=False,
                detail=f"{_HEALTHCHECK_SLUG}.xml parsed but has 0 inproceedings records",
            )
        # `volume.records[0]` 的 key/title 非空是 `parse.parse_volume_xml` 自身的构造
        # 不变量（key 缺失即 PARSE、title 缺失即被跳过而不入 records）——此处不再重复
        # 判空（那会是死代码：正常路径不可达），直接引用即符合"首条 key/title 存在"
        # 判据（design §5.2）。
        first = volume.records[0]
        if len(volume.records) < _MIN_HEALTHY_RECORDS:
            return HealthReport(
                healthy=False,
                detail=(
                    f"only {len(volume.records)} record(s) parsed, below the conservative "
                    f"floor of {_MIN_HEALTHY_RECORDS} (possible structural drift)"
                ),
            )
        return HealthReport(
            healthy=True,
            detail=(
                f"{_HEALTHCHECK_SLUG}.xml reachable, {len(volume.records)} record(s), "
                f"first key={first.key!r}"
            ),
        )


__all__ = ["DblpAdapter"]
