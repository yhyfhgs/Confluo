"""AEA `SourceAdapter` 主体（design/adapters/aea.md §1/§3/§4；phase5-plan T5；design/11 §4.6 T11）。

**capabilities = RESOLVE**（offline，`resolve_offline=True`，D-022 免限速闸）——
**ENUMERATE 不声明**：元数据 100% 委 Crossref 标准 ISSN 路径（D-005，与 elsevier_sd/
wiley 同口径；venue YAML `metadata_source: crossref`）。**FETCH 仍不声明**：本 adapter
自身不实现 `fetch_asset`（全文取回经 browser-fetch 横切件在 stages 层执行，不经
`adapter.fetch_asset()`——同 ssrn/wiley 页面兜底口径）。**本 adapter 全程零网络**（连
`www.aeaweb.org` 发现层也不触达——`domains` 仅为契约完整性声明，§5 备用）。

`resolve_assets`（**零网络**）= DOI 双形态解析（`parse.parse_doi`）+ venue `auth.level`
静态分类（§3.3）+ **模式 B `RENDER_PAGE` 计划产出**（design/11 §4.6 ★接缝 A-1 裁决，
D-030）：

- **订阅刊**（`venue.auth.level != NONE`，即 aer/aeri/aej_*）：`auth_needed=
  INSTITUTIONAL`。**不再在 resolve 时静态猜测 `NO_ENTITLEMENT`**——真实的"有无权限"
  现由浏览器上下文实际访问后由 `ChallengeDetector`/`_fetch_via_browser` 判定（同一
  NO_ENTITLEMENT 终态仍在，只是从"resolve 时猜测"移到"fetch 时实测"，更诚实）。
- **OA 刊**（`venue.auth.level == NONE`，即 jel/jep）：`auth_needed=NONE`（gold OA，
  无需凭证——§3.4 反直觉发现：即便"gold OA"，`pubs.aeaweb.org` 全文仍住同一 Cloudflare
  域，浏览器上下文取回同样可能遇挑战，但这与"无认证问题"不矛盾）。

两分支均先记一条 **DEBUG 观测**（`pubs.aeaweb.org/doi/pdfplus/{DOI}`），随后返回**同一
URL 的 `AssetPlan(url_strategy=RENDER_PAGE)`**——**★接缝 A-1 裁决结果**（design/11 §4.6，
D-030）：`url_strategy` 复用既有 `RENDER_PAGE`（不新增 `BROWSER` 枚举值）；`AssetPlan`
不新增 `state=deferred` 字段（门控改由 stages 层的 `ctx.browser_fetch`/`Config.
browser_fetch_enabled` 三级门表达，关闭时该计划仍产出、由 stages 门拦为 `skipped`，
不计 failures）。**本 adapter 此前"结构性地从不返回非空 `AssetPlan`"的诚实边界已随
browser-fetch 落地失去理由**：届时存在真实可执行的浏览器上下文取回路径，继续
raise/返回空列表会让一条真实可执行的全文路径对用户不可见（同一原则的镜像应用，
§4.6 原文）。**限速/配额/挑战冷却/robots 合规全部由 browser-fetch 横切件统一护栏
承担**（design/11 §7）——本 adapter 不写任何该类代码。

未知 DOI code（新子刊上线，不在 `parse.CODE_TO_VENUE` 表中，且非已知的 P&P 暂缓
形态）→ 记一条 **WARNING** 观测，不崩（§3.2）。

`healthcheck`：本 Phase 无网络 FETCH 探针——恒 `raise NotImplementedError`（→ canary
SKIP，复用 elsevier_sd/wiley "keyless/无凭证 auth_gated adapter" 先例，auth-framework
§7 B-M4）。元数据面健康由 crossref adapter 自有 canary 覆盖，不重复（§3.5）。
"""

from __future__ import annotations

from paper_crawler.adapter import AdapterBase, AdapterFamily
from paper_crawler.adapters.aea import parse
from paper_crawler.errors import CrawlerError, ErrorClass
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

# --- 端点与常量（aea.md §1/§3.3/§5）------------------------------------------------------------

# 发现/landing host（Apache，开放）。本 Phase resolve 零网络，此域仅作契约完整性声明
# （§5"此桶仅备 landing 补字段，如需"）——**全文 host `pubs.aeaweb.org` 刻意不进
# domains**（Cloudflare 全文层，本 Phase 无 stateless 请求，§1）。
_DISCOVERY_HOST = "www.aeaweb.org"

# 全文层 host（Atypon/Literatum + Cloudflare）——**本 adapter 从不向此域发请求**，
# 只用它拼一条 deferred 全文 URL 供 DEBUG 观测（供未来 browser-fetch 通道消费）。
_FULLTEXT_HOST = "pubs.aeaweb.org"


def _deferred_fulltext_url(doi: str) -> str:
    """`pubs.aeaweb.org/doi/pdfplus/{DOI}` 的规范全文 URL（§3.3/§3.4；纯字符串拼接，
    不发请求）——JEP 免费刊全文的真实交付路径（站点勘察 [LIVE] 实证），订阅刊亦经
    同一 Atypon 平台交付（多一层机构订阅门）。
    """
    return f"https://{_FULLTEXT_HOST}/doi/pdfplus/{doi}"


def _doi_of(paper: PaperStub) -> str:
    """从 stub 取 DOI（scheme='doi'）；缺失 → CONFIG（路由缺陷——aea 只按 DOI resolve，
    沿 elsevier_sd/unpaywall `_doi_of` 先例）。
    """
    for scheme, value in paper.identifiers:
        if scheme == "doi":
            return value
    raise CrawlerError(
        ErrorClass.CONFIG,
        f"aea resolve_assets needs a doi identifier: {paper.identifiers!r}",
    )


class AeaAdapter(AdapterBase):
    """AEA 8 刊 adapter（`auth_gated`；RESOLVE-only offline；元数据委 crossref，§1）。"""

    adapter_id = "aea"
    family: AdapterFamily = "auth_gated"
    # §4 论证：ENUMERATE 不声明（委 crossref，D-005）；FETCH 不声明——本 adapter 自身
    # 不实现 `fetch_asset`（全文经 browser-fetch 横切件在 stages 层执行，不经此方法，
    # 同 ssrn/wiley 页面兜底口径）。RESOLVE 是本 Phase 唯一声明的能力。
    capabilities = Capability.RESOLVE
    default_rate = RatePolicy(
        requests_per_minute=30.0,
        burst=1,
        source_note=(
            "www.aeaweb.org 发现层 Apache 无挑战，保守 1 req/2s；本 Phase resolve 零网络，"
            "此桶仅备 landing 补字段（如需）；全文域 pubs.aeaweb.org（Cloudflare）本 Phase "
            "不 stateless 触达；docs/design/adapters/aea.md §5 [LIVE 2026-07-24]"
        ),
    )
    # 本 Phase 不实现 aea 认证（D-006 CookieSession 留将来，§1）——adapter 自身零门槛。
    # 订阅刊 venue YAML 的 `auth.level: institutional` 是刊物真实访问级的**前瞻声明**，
    # 与此不矛盾（registry.py `_lint_adapter_refs` 仅当 venue auth.level 低于 adapter
    # 要求时报错；`none` 天然是零门槛下限，不会触发，§1"层次澄清"）。
    auth_requirement = AuthLevel.NONE
    domains: tuple[str, ...] = (_DISCOVERY_HOST,)
    # resolve_assets 纯 DOI 形态解析 + venue.auth.level 静态分类，证明零网络（§1）。
    resolve_offline = True

    def resolve_assets(
        self, venue: VenueSpec, paper: PaperStub, session: SessionHandle | None = None
    ) -> list[AssetPlan]:
        """DOI 双形态解析 + venue OA-class 静态分类（零网络，§3.3）→ 模式 B `RENDER_PAGE`
        `AssetPlan`（design/11 §4.6 ★接缝 A-1 裁决，D-030；模块 docstring 展开）。

        两分支（订阅刊/OA 刊）均先记 deferred 全文 URL 的 DEBUG 观测，随后返回**同一
        URL** 的 `AssetPlan(url_strategy=RENDER_PAGE)`——`auth_needed` 按分支区分
        （INSTITUTIONAL/NONE），执行与 no_entitlement 终态判定移交 browser-fetch
        横切件在实际 fetch 时处理（不再在此静态猜测）。`session` 未使用（本 Phase
        无认证会话，冻结协议签名要求携带该形参）。

        **AC-0 合规复述**：本方法**不**发起任何 `pubs.aeaweb.org` 请求、**不绕过任何
        付费墙**——订阅刊遇到的付费墙由浏览器上下文实际访问后如实判 `no_entitlement`
        （既有链路，不计 failures），CF 挑战由既有 `ChallengeDetector` 分类停手（AC-0.2）。
        限速/配额/挑战冷却/robots 合规全部由 browser-fetch 横切件统一护栏承担（design/11
        §7），本 adapter 侧零限速/配额代码。`ctx.browser_fetch`/`Config.
        browser_fetch_enabled` 三级门在 stages 层——本层不判，门关时计划仍产出，由
        stages 门拦为 `skipped`（不计 failures）。
        """
        doi = _doi_of(paper)
        parsed = parse.parse_doi(doi)
        if parsed is None:
            raise CrawlerError(
                ErrorClass.CONFIG,
                f"aea resolve_assets got a non-10.1257 doi (adapter routing mismatch?): {doi!r}",
            )

        if parsed.venue_id is None and parsed.doi_form != "pnp":
            # 未知 code（非已知的 P&P 暂缓形态）→ WARN 观测，不崩（§3.2"防新子刊上线"）。
            log_event(
                "WARNING",
                "aea doi code not in code->venue routing table (new sub-journal?)",
                stage="resolve",
                domain=self.domains[0],
                doi=doi,
                code=parsed.code,
            )

        subscription = venue.auth.level is not AuthLevel.NONE
        auth_needed = AuthLevel.INSTITUTIONAL if subscription else AuthLevel.NONE
        fulltext_url = _deferred_fulltext_url(doi)
        log_event(
            "DEBUG",
            "aea fulltext render_page plan (browser-fetch mode B; pubs.aeaweb.org CF likely)",
            stage="resolve",
            domain=_FULLTEXT_HOST,
            deferred_url=fulltext_url,
            doi=doi,
            doi_form=parsed.doi_form,
            venue=venue.id,
            auth_needed=auth_needed.value,
        )
        return [
            AssetPlan(
                kind=AssetKind.PDF,
                url=fulltext_url,
                expected_type="application/pdf",
                url_strategy=UrlStrategy.RENDER_PAGE,
                auth_needed=auth_needed,
            )
        ]

    def healthcheck(self, session: SessionHandle | None = None) -> HealthReport:
        """本 adapter 无独立网络探针——恒 `NotImplementedError`（→ canary SKIP，§3.5）。

        全文取回经 browser-fetch 横切件（T11 落地），但该通道走独立的一次性浏览器
        上下文，不适合作为常驻 canary 探针（会消耗每日配额/触发限速）；元数据面健康
        由 crossref adapter 自有 canary 覆盖，不重复。
        """
        raise NotImplementedError(
            "aea healthcheck: no dedicated network probe (fulltext via browser-fetch, §3.5)"
        )

    # `discover_timeline`/`enumerate_issue`/`fetch_asset` 未声明能力（capabilities 仅
    # RESOLVE）——不覆写，沿用 `AdapterBase` 默认的 `CapabilityNotSupported`（crossref/
    # elsevier_sd/unpaywall 先例）。


__all__ = ["AeaAdapter"]
