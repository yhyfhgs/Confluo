"""Econometric Society（`econsoc`）`SourceAdapter` 主体（design/adapters/econsoc.md §1/§4/§5）。

把零网络纯逻辑（`parse`）与 T2 共享 `HttpClient` 组装成 adapter。family=`open_access`
（匿名 OA galley），capabilities ``DISCOVER | ENUMERATE | RESOLVE | FETCH``——**按 venue
非对称行使**（§2/§3.1，见包 docstring）：TE/QE 走全四位（自持 OJS OAI-PMH 枚举）；ECMA 只实际
行使 `RESOLVE | FETCH`（枚举委 crossref，ECMA 无 OAI 端点）。**不声明 SEARCH**（冻结协议无
`search()`，先例 arxiv/aaai）。

阶段分工（§4）：

- `discover_timeline`（零网络，**TE/QE only**）：`quirks.volume_map`（year→volume）逐年产
  刊/年聚合 IssueRef（幂等键 `(venue, year)`，沿 aaai-ojs.md §3.2 方案 B）。ECMA venue
  无 volume_map → discover 委 crossref（本 adapter 对 ECMA 不参与 discover），误调即 `CONFIG`。
- `enumerate_issue`（OAI-PMH 收割，**TE/QE only**）：`ListRecords` + `resumptionToken` 翻页
  （信封复用 `_oai`）；**客户端过滤 = DOI 后缀刊别（membership）+ dc:date 年（partition）**
  ——DOI 后缀（ecta/te/qe）判刊别（design §4），dc:date 年把刊全量切成"一年一 issue"的片
  （econsoc DOI **不编码卷号**，异于 aaai 的 DOI-卷号切片，故年切片由 dc:date 承担、令
  `--year Y` 语义正确）。当前刊（volume_map 最大年）加 `from=<今日−回看天数>` datestamp 窗
  做增量（datestamp≠发表日，故仅作窗、membership 仍靠后缀/年）；去重由下游 `identifier('doi')`
  主键天然保证。ECMA 委 crossref（不经本 adapter）。
- `resolve_assets`（★ 网络绑定，`resolve_offline=False`）：**ECMA 分段前置**（§3.3 方向 a）——
  按 DOI+落地域名判段：过刊段（doi.wiley.com）→ `NO_ENTITLEMENT`/skip（跨 adapter handoff
  defer，D-028）、pre-DOI 段（JSTOR/10.2307）→ 零资产 skip、当前段 → 下述统一路径。**统一
  路径**（三刊当前段）：`GET econometricsociety.org/doi/{DOI}` →302→ 落地页 → 抽 galley 链
  `/publications/.../file/{file}.PDF` → 单个 PDF `AssetPlan`（galley `{file}`/`{slug}` 非 DOI
  可构造，故必 GET 落地页，异于 aaai 零网络 resolve）。CF 质询页 body → `Challenged`（BLOCKED，
  不对抗 AC-0.2）。
- `fetch_asset`（流式）：`HttpClient.stream` → `io.write_stream`；首字节嗅探把"PDF url 却回
  HTML"归 CF 质询（`CHALLENGE`）或撤稿（`GONE`）；`%PDF` 权威校验归 pipeline（冻结分工）。
- `healthcheck`：TE OAI `Identify` 200 + `repositoryName` 含 "Theoretical Economics"（存活
  基线，匿名零 token）。跨刊 GetRecord canary 的已知答案回归 + econometricsociety.org galley
  HEAD 探针是**测试层/在线冒烟**职责（test_econsoc_canary.py / 冒烟，沿 aaai §7 分层——不给
  运行期 healthcheck 增网络面）。

**限速/礼貌**（§5）：`default_rate` 取**两域保守并集**——CF 前置的 econometricsociety.org
`≥3s 硬下限/5s 起步`（rpm=12、并发 1）为绑定约束，OAI 域 econtheory.org 经 `route_for` alias
到同一桶（单 adapter 单 default_rate 无法各域异率——取更保守者，OAI 被一并降速但**宁慢勿封**，
对齐 CF+反 AI 姿态 §5）。连续 CF 质询即 BLOCKED（不对抗）。

**HttpClient 注入**（同 arxiv/aaai 先例）：`load_adapters()` 无参实例化——`__init__(http=None)`，
首次网络调用惰性自建（UA 走 D-014，email 从环境变量取，缺失用占位 `.invalid`）。测试注入
`HttpClient(transport=MockTransport(...))` 达成零真实网络。
"""

from __future__ import annotations

import os
from collections.abc import Iterable, Iterator
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

from paper_crawler.adapter import AdapterBase, AdapterFamily
from paper_crawler.adapters.econsoc import parse
from paper_crawler.adapters.econsoc.parse import EcmaSegment
from paper_crawler.auth.challenge import ChallengeDetector, ClassifyResult
from paper_crawler.errors import Challenged, CrawlerError, ErrorClass
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

# --- 端点与常量（§2/§4/§5）------------------------------------------------------------------

# OJS OAI-PMH 多刊实例（survey §4 [LIVE]）：{oai_base}/index.php/{ojs_code}/oai。oai_base 可经
# quirks 覆盖（默认 econtheory.org/ojs）；ojs_code∈{te,qe}（ECMA 不在此实例，无 OAI 端点）。
_DEFAULT_OAI_BASE = "https://econtheory.org/ojs"
_METADATA_PREFIX = "oai_dc"
# 当前刊增量的固定回看天数（§4，沿 aaai 常量语义）。窗口越长越抗 datestamp 滞后；当前刊初始
# 完整基线由历史全量收割建立，本窗口只捕获增量新增（去重由 DOI 主键保证）。
_LOOKBACK_DAYS = 30

# 合并前端（当前段 landing + galley fetch，CF 前置，survey §4）。resolve 按 DOI 构造 landing。
_LANDING_TMPL = "https://www.econometricsociety.org/doi/{doi}"
# healthcheck 存活基线：TE OAI Identify（repositoryName 含 "Theoretical Economics"，survey §4）。
_HEALTHCHECK_OJS_CODE = "te"
_HEALTHCHECK_REPO_TOKEN = "theoretical economics"

_PDF_MAGIC = b"%PDF-"
# 首字节嗅探缓冲：足以覆盖 CF "Just a moment" 质询页顶部标记（challenge.py body 特征）。
_SNIFF_BYTES = 4096

_CONTACT_EMAIL_ENV = "PAPER_CRAWLER_CONTACT_EMAIL"
# RFC 2606 保留 .invalid 顶级域——占位联系人（仅惰性自建且未设环境变量时用，同 aaai 先例）。
_PLACEHOLDER_EMAIL = "anonymous@paper-crawler.invalid"

# ECMA 分段路由的落地域名 pre-filter 信号 meta 键（design §3.4；crossref `resource.primary.URL`
# 域名——**有陈旧风险**，仅作 pre-filter，权威取实时落地，见 parse.classify_ecma_segment caveat）。
_PRIMARY_DOMAIN_META = "primary_url_domain"


def _default_user_agent() -> str:
    email = os.environ.get(_CONTACT_EMAIL_ENV, "").strip() or _PLACEHOLDER_EMAIL
    return build_user_agent(email)


class EconsocAdapter(AdapterBase):
    """Econometric Society（`econsoc`）adapter（`open_access` family）。

    服务三刊当前面：Econometrica(ECMA)/Theoretical Economics(TE)/Quantitative Economics(QE)。
    能力按 venue 非对称（§3.1）：TE/QE 全四位（自持 OJS OAI-PMH 枚举）；ECMA 只 RESOLVE|FETCH
    （枚举委 crossref，ECMA 无 OAI 端点）。版权：三刊开放许可（CC BY/BY-NC）个人科研只读、
    诚实 UA、不再分发（§1 红线）。
    """

    adapter_id = "econsoc"
    family: AdapterFamily = "open_access"
    capabilities = (
        Capability.DISCOVER | Capability.ENUMERATE | Capability.RESOLVE | Capability.FETCH
    )
    # §5：两域保守并集——CF 前置 econometricsociety.org 的 ≥3s 硬下限/5s 起步（rpm=12、并发 1）
    # 为绑定约束；OAI 域 econtheory.org 经 route_for alias 到同一桶（单 default_rate 取更保守者）。
    default_rate = RatePolicy(
        requests_per_minute=12.0,
        burst=1,
        source_note=(
            "econsoc 两域保守并集：CF 前置 econometricsociety.org 具名封 ClaudeBot 反 AI + CF → "
            "≥3s 硬下限/5s 起步（rpm=12、并发 1，宁慢勿封）；OAI 域 econtheory.org（robots 极宽松、"
            "本可 30rpm）经 route_for alias 到同一桶被一并降速（单 adapter 单 default_rate 无法各域"
            "异率，取更保守者）；连续 CF 质询即 BLOCKED；docs/design/adapters/econsoc.md §5 "
            "[LIVE 2026-07-24 R0c]"
        ),
    )
    auth_requirement = AuthLevel.NONE
    # 主域=合并前端（resolve/fetch，rate 锚点）；econometricsociety.org（无 www）与 OAI 域
    # econtheory.org 一并声明 → route_for alias 到主域同一桶（www/非 www 重定向 + OAI 均覆盖，
    # 逐请求限速闸不因未注册 host fail-fast）。
    domains: tuple[str, ...] = (
        "www.econometricsociety.org",
        "econometricsociety.org",
        "econtheory.org",
    )
    # resolve 发真实网络请求（GET 落地页抽 galley，galley 不可由 DOI 构造）→ 不满足
    # resolve_offline 零网络契约，保留默认 False（resolve 仍过限速闸，CF 前置正确需限速）。

    def __init__(self, http: HttpClient | None = None) -> None:
        self._http = http

    def set_http_client(self, client: HttpClient) -> None:
        """注入组装好的 `HttpClient`（`adapter.HttpClientConsumer` 协议，同 arxiv/aaai 先例）。"""
        self._http = client

    def _client(self) -> HttpClient:
        if self._http is None:
            self._http = HttpClient(user_agent=_default_user_agent())
        return self._http

    # -- discover（零网络，TE/QE）------------------------------------------------------------

    def discover_timeline(self, venue: VenueSpec, since: str | None = None) -> Iterable[IssueRef]:
        """`quirks.volume_map`（year→volume）逐年产刊/年聚合 IssueRef（零网络，§4/§3.2）。

        `volume`=裸数字串（一年=一卷，TE/QE 自 2006 连续卷）、`number`=None、`year`=int
        （--year selector 生效字段）、`label`=f'{ojs_code}-{year}'、其余 None（enumerate 回填）。
        `since`（'YYYY' 前缀）晚于最小年时收窄起点。**ECMA venue 无 volume_map → CONFIG**
        （ECMA discover 委 crossref，本 adapter 不参与——误调响亮停机）。
        """
        volume_map = _volume_map(venue)
        code = _ojs_code(venue)
        since_year = _parse_since_year(since)
        for year in sorted(volume_map):
            if since_year is not None and year < since_year:
                continue
            yield IssueRef(
                venue_id=venue.id,
                volume=str(volume_map[year]),
                number=None,
                year=year,
                label=f"{code}-{year}",
                pub_date=None,
                paper_count_claimed=None,
            )

    # -- enumerate（OAI-PMH 收割，TE/QE）-----------------------------------------------------

    def enumerate_issue(self, venue: VenueSpec, issue: IssueRef) -> Iterable[PaperStub]:
        """刊/年 IssueRef → OAI-PMH `ListRecords` 收割（DOI 后缀刊别 + dc:date 年双过滤）。

        目标/窗口在此**急切**求值（非法 issue 早失败为 CONFIG）；翻页与网络在返回的生成器
        惰性执行。当前刊（volume_map 最大年）加 `from=<今日−回看天数>` datestamp 窗做增量，
        历史刊无窗全量收割；去重由下游 `identifier('doi')` 主键天然保证（§4）。
        """
        year = _issue_year(issue, venue)
        code = _ojs_code(venue)
        oai_base = _oai_endpoint(venue, code)
        frm = _lookback_from() if year == max(_volume_map(venue)) else None
        url = _oai_list_url(oai_base, frm)
        return self._enumerate_pages(venue, issue, code, year, oai_base, url)

    def _enumerate_pages(
        self,
        venue: VenueSpec,
        issue: IssueRef,
        code: str,
        year: int,
        oai_base: str,
        url: str,
    ) -> Iterator[PaperStub]:
        client = self._client()
        while True:
            page = parse.parse_oai_page(client.get_bytes(url))
            for record in page.records:
                # membership = DOI 后缀刊别（防御，端点已单刊）；partition = dc:date 年（§4）。
                if record.journal != code:
                    continue
                if _record_year(record) != year:
                    continue
                yield parse.to_paper_stub(record)
            if page.resumption_token is None:
                return
            url = _oai_resume_url(oai_base, page.resumption_token)

    # -- resolve（★ 网络绑定：ECMA 分段前置 + 统一落地页抽 galley）-----------------------------

    def resolve_assets(
        self, venue: VenueSpec, paper: PaperStub, session: SessionHandle | None = None
    ) -> list[AssetPlan]:
        """DOI → 单个 galley PDF `AssetPlan`（§4）。ECMA 分段前置（§3.3 方向 a）。

        **ECMA 分段**（DOI 后缀 ecta）：`classify_ecma_segment(doi, landing_domain=meta
        primary_url_domain)`——过刊段（doi.wiley.com）→ `NO_ENTITLEMENT`（跨 adapter handoff
        defer，D-028）；pre-DOI 段（JSTOR/10.2307）→ 零资产 skip（界外，非错误）；当前段 → 下述
        统一路径。TE/QE 恒当前段（不分段）。**统一路径**：`GET econometricsociety.org/doi/{DOI}`
        → 抽 galley 链 → PDF `AssetPlan`；CF 质询 body → `Challenged`；无 galley（撤稿/合并/非 OA）
        → 0 资产（非阻塞，ECMA 非全刊 OA 的 no_entitlement 判定归 [UNRESOLVED①] 在线闭合）。
        """
        doi = _doi_of(paper)
        # ECMA-family（modern 10.3982/ecta ∪ pre-DOI 10.2307）→ 分段路由；TE/QE 不分段（§3.3）。
        if parse.journal_of_doi(doi) == "ecma" or parse.is_pre_doi(doi):
            segment = parse.classify_ecma_segment(doi, landing_domain=_primary_domain(paper))
            if segment is EcmaSegment.BACKFILE:
                raise CrawlerError(
                    ErrorClass.NO_ENTITLEMENT,
                    f"econsoc: ECMA {doi} 落过刊段（doi.wiley.com）——非本 adapter 覆盖面，"
                    "跨 adapter 交 wiley 的 handoff 显式 defer（Phase 5，D-028/§3.3）",
                    detail="ecma-backfile",
                )
            if segment is EcmaSegment.PRE_DOI:
                return []  # JSTOR pre-DOI（10.2307）界外零资产，非错误（§6）
        landing = _landing_url(doi)
        data = self._client().get_bytes(landing)
        _guard_challenge(data, landing)
        galley = parse.extract_galley_url(data, base_url=landing)
        if galley is None:
            return []
        return [
            AssetPlan(
                kind=AssetKind.PDF,
                url=galley,
                expected_type="application/pdf",
                url_strategy=UrlStrategy.DIRECT,
                auth_needed=AuthLevel.NONE,
                version=None,
            )
        ]

    # -- fetch（流式，撤稿/CF 质询首字节嗅探）-----------------------------------------------

    def fetch_asset(
        self, plan: AssetPlan, io: FetchIO, session: SessionHandle | None = None
    ) -> FetchResult:
        """`HttpClient.stream` → `io.write_stream`；首字节嗅探区分 CF 质询/撤稿页（§4/§6）。

        `%PDF` 权威校验归 pipeline（冻结分工）；本层把"PDF url 却回 HTML"归类：命中 CF 质询
        特征 → `CHALLENGE`（BLOCKED，不对抗 AC-0.2）；其它 HTML（撤稿/合并/不存在）→ `GONE`。
        HTTP 4xx（404/410）由 `HttpClient` 直接映射。
        """
        stream = self._client().stream(plan.url)
        bytes_written, sha256 = io.write_stream(_gone_or_challenge_guarded_stream(stream, plan.url))
        return FetchResult(ok=True, bytes_written=bytes_written, sha256=sha256)

    # -- healthcheck（TE OAI Identify）------------------------------------------------------

    def healthcheck(self, session: SessionHandle | None = None) -> HealthReport:
        """TE OAI `Identify` 200 + `repositoryName` 含 "Theoretical Economics"（存活基线，§4）。

        跨刊 GetRecord canary 的已知答案回归 + econometricsociety.org galley HEAD 探针是测试层/
        在线冒烟职责（test_econsoc_canary.py / 冒烟，沿 aaai §7 分层——不给运行期 healthcheck
        增网络面）。
        """
        url = _oai_identify_url(_oai_endpoint_for_code(_DEFAULT_OAI_BASE, _HEALTHCHECK_OJS_CODE))
        try:
            data = self._client().get_bytes(url)
        except CrawlerError as exc:
            return HealthReport(
                healthy=False,
                detail=f"econsoc OAI identify unreachable ({exc.error_class.value}): {exc}",
            )
        try:
            name = parse.identify_repository_name(data)
        except CrawlerError as exc:
            return HealthReport(healthy=False, detail=f"identify parse failed: {exc}")
        if name is None or _HEALTHCHECK_REPO_TOKEN not in name.lower():
            return HealthReport(
                healthy=False,
                detail=f"identify repositoryName missing 'Theoretical Economics': {name!r}",
            )
        return HealthReport(healthy=True, detail=f"oai identify ok (repositoryName={name!r})")


# --- 模块级纯函数 -----------------------------------------------------------------------------


def _volume_map(venue: VenueSpec) -> dict[int, int]:
    """从 `venue.quirks['volume_map']` 取 year→volume 映射；结构非法 → `CONFIG`（aaai 先例）。

    ECMA venue 无 volume_map（枚举委 crossref）——若对 ECMA 误调 discover/enumerate 即在此
    响亮停机（提示 ECMA 走 crossref，非本 adapter 的 DISCOVER/ENUMERATE 面）。
    """
    raw = venue.quirks.get("volume_map")
    if not isinstance(raw, dict) or not raw:
        raise CrawlerError(
            ErrorClass.CONFIG,
            f"venue {venue.id!r} 缺少非空的 quirks.volume_map（year→volume，econsoc.md §4）"
            "——ECMA 枚举委 crossref、本 adapter 不参与其 DISCOVER/ENUMERATE",
        )
    result: dict[int, int] = {}
    for key, value in raw.items():
        try:
            result[int(key)] = int(value)
        except (TypeError, ValueError) as exc:
            raise CrawlerError(
                ErrorClass.CONFIG,
                f"venue {venue.id!r} quirks.volume_map 含非法条目: {key!r}: {value!r}",
            ) from exc
    return result


def _parse_since_year(since: str | None) -> int | None:
    if since is None:
        return None
    try:
        return int(since[:4])
    except ValueError as exc:
        raise CrawlerError(ErrorClass.CONFIG, f"invalid since year: {since!r}") from exc


def _issue_year(issue: IssueRef, venue: VenueSpec) -> int:
    """校验并取 `issue.year`（须在 venue 的 volume_map 注册；partition 维度，§4）。

    两类 `config`：year 缺失（foreign/畸形 IssueRef）、以及 year 未在 volume_map 注册
    （新一年未登记，提示走 track 流程 D-012；aaai 先例）。
    """
    if issue.year is None:
        raise CrawlerError(
            ErrorClass.CONFIG,
            f"econsoc enumerate needs IssueRef.year, got {issue.year!r}",
        )
    if issue.year not in _volume_map(venue):
        raise CrawlerError(
            ErrorClass.CONFIG,
            f"year {issue.year!r} not registered in venue {venue.id!r} "
            "quirks.volume_map (unregistered edition — use `crawler track`, D-012)",
        )
    return issue.year


def _ojs_code(venue: VenueSpec) -> str:
    """OJS journal context 代码（`quirks.ojs_code`，∈{te,qe}）；缺失 → `CONFIG`（enumerate 必需）。

    归一小写（与 OAI 端点/DOI 后缀刊别小写口径一致）；ECMA venue 无此 quirk（走 crossref），
    误调即响亮停机。
    """
    code = venue.quirks.get("ojs_code")
    if isinstance(code, str) and code.strip():
        return code.strip().lower()
    raise CrawlerError(
        ErrorClass.CONFIG,
        f"venue {venue.id!r} 缺少 quirks.ojs_code（te|qe，econsoc.md §3.5）"
        "——ECMA 无 OAI 端点、枚举委 crossref、本 adapter 不参与其 DISCOVER/ENUMERATE",
    )


def _oai_endpoint(venue: VenueSpec, code: str) -> str:
    base = venue.quirks.get("oai_base")
    base_str = base.strip() if isinstance(base, str) and base.strip() else _DEFAULT_OAI_BASE
    return _oai_endpoint_for_code(base_str, code)


def _oai_endpoint_for_code(base: str, code: str) -> str:
    return f"{base.rstrip('/')}/index.php/{code}/oai"


def _lookback_from() -> str:
    """当前刊增量的 datestamp 窗下界 ``from``（今日 − 回看天数，UTC 日期，date 粒度）。"""
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


def _record_year(record: parse.EconsocRecord) -> int | None:
    """从 `EconsocRecord.date`（dc:date 发表日）抽年（partition 维度）；缺/畸形 → None。"""
    date = record.date
    if date is None or len(date) < 4 or not date[:4].isdigit():
        return None
    return int(date[:4])


def _landing_url(doi: str) -> str:
    """当前段落地页 URL：`econometricsociety.org/doi/{DOI}`（DOI 已归一小写，§4）。"""
    return _LANDING_TMPL.format(doi=doi)


def _doi_of(paper: PaperStub) -> str:
    """从 stub 取 DOI（scheme='doi'）；缺失 → CONFIG（路由缺陷——econsoc 只按 DOI resolve，
    同 wiley/elsevier `_doi_of` 先例）。"""
    for scheme, value in paper.identifiers:
        if scheme == "doi":
            return value
    raise CrawlerError(
        ErrorClass.CONFIG,
        f"econsoc resolve_assets needs a doi identifier: {paper.identifiers!r}",
    )


def _primary_domain(paper: PaperStub) -> str | None:
    """ECMA 分段路由的落地域名 pre-filter 信号（meta['primary_url_domain']，§3.3）。

    crossref `resource.primary.URL` 域名——**有陈旧风险**（当前 ECMA 的 crossref link 可能仍留
    遗留 Wiley link），故仅作 pre-filter 提示、缺省 None → 乐观归当前段（权威取实时落地域名，见
    parse.classify_ecma_segment caveat 与在线冒烟 doi.org HEAD 核对）。crossref adapter 现未
    产出该键 → 运行期恒 None（乐观当前段），跨 adapter 精确路由随该键落地为非阻塞升级路径。
    """
    return dict(paper.meta).get(_PRIMARY_DOMAIN_META)


def _guard_challenge(data: bytes, url: str) -> None:
    """resolve 落地页 body 命中 CF 质询特征 → `Challenged`（BLOCKED，不对抗 AC-0.2，§6）。

    `HttpClient.get_bytes` 不暴露状态/响应头，故只判 200-body 型质询（"Just a moment"/
    `/cdn-cgi/challenge-platform/`，challenge.py 平台无关特征）；头级质询（403 `cf-mitigated`）
    经 `HttpClient` 映射 NO_ENTITLEMENT（二者皆阻塞；canary/冒烟监质询，§5）。
    """
    verdict = ChallengeDetector().classify(status=200, headers={}, final_url=url, body=data)
    if verdict is ClassifyResult.CHALLENGE:
        raise Challenged(f"econsoc landing hit a Cloudflare challenge page (not resolvable): {url}")


def _gone_or_challenge_guarded_stream(chunks: Iterable[bytes], url: str) -> Iterator[bytes]:
    """透传字节流，先嗅探首字节：PDF 魔数放行；HTML → CF 质询(`CHALLENGE`)或撤稿(`GONE`)。

    首个非 PDF 且形似 HTML 的响应体分两类（§6）：命中 CF 质询特征 → `Challenged`（BLOCKED，
    不对抗）；其它 HTML（撤稿/合并/不存在）→ `GONE`。既非 PDF 又不形似 HTML 的体透传，交
    pipeline 的 `%PDF` 权威校验处置。复用 arxiv `_gone_guarded_stream` 首字节嗅探形态。
    """
    iterator = iter(chunks)
    head = bytearray()
    for chunk in iterator:
        head.extend(chunk)
        if len(head) >= _SNIFF_BYTES:
            break
    stripped = bytes(head).lstrip()
    if not stripped.startswith(_PDF_MAGIC) and _looks_like_html(stripped):
        verdict = ChallengeDetector().classify(
            status=200, headers={}, final_url=url, body=bytes(head)
        )
        if verdict is ClassifyResult.CHALLENGE:
            raise Challenged(
                f"econsoc galley returned a Cloudflare challenge page, not a PDF: {url}"
            )
        raise CrawlerError(
            ErrorClass.GONE,
            "econsoc galley returned an HTML page (withdrawn/merged/not-found), not a PDF",
        )
    if head:
        yield bytes(head)
    yield from iterator


def _looks_like_html(head: bytes) -> bool:
    # 子串扫描（非 startswith）覆盖前导注释/BOM/空白后才出现的 HTML 标记（CF 质询页/撤稿页均
    # 以标准 HTML 文档标记起手）。
    low = head[:_SNIFF_BYTES].lower()
    return b"<!doctype html" in low or b"<html" in low


__all__ = ["EconsocAdapter"]
