"""AEA `SourceAdapter` 主体（design/adapters/aea.md §1/§3/§4；phase5-plan T5）。

**capabilities = RESOLVE**（offline，`resolve_offline=True`，D-022 免限速闸）——
**ENUMERATE 不声明**：元数据 100% 委 Crossref 标准 ISSN 路径（D-005，与 elsevier_sd/
wiley 同口径；venue YAML `metadata_source: crossref`）。**FETCH 本 Phase 不声明**：
全文域 `pubs.aeaweb.org` 对 stateless 客户端一律 `cf-mitigated: challenge`（连 gold OA
的 JEP 亦然，站点勘察 [LIVE] 2026-07-24 实证），D-006 禁对抗——声明恒 BLOCKED 的能力
不诚实，故不声明（aea.md §4 完整论证）。**本 adapter 全程零网络**（连 `www.aeaweb.org`
发现层也不触达——`domains` 仅为契约完整性声明，§5 备用）。

`resolve_assets`（**零网络**）= DOI 双形态解析（`parse.parse_doi`）+ venue `auth.level`
静态分类（§3.3）：

- **订阅刊**（`venue.auth.level != NONE`，即 aer/aeri/aej_*）→ **raise
  `NO_ENTITLEMENT`**（不产平台 `AssetPlan`；pipeline 侧按 auth-framework §8.1 转
  unpaywall OA-fallback，§8.5"不计 failures"终态）。
- **OA 刊**（`venue.auth.level == NONE`，即 jel/jep）→ **返回空列表**——§3.4 反直觉
  发现：`pubs.aeaweb.org/doi/pdfplus/{DOI}` 对该域的全文取回一律 CF challenge，
  即便"gold OA"的 JEP 亦然，故同样不产可 stateless-fetch 的计划。**不** raise
  `NO_ENTITLEMENT`（无认证问题——venue 本就声明 `auth.level: none`，raise 该错误类
  会误导为"权限不足"而非"平台层技术阻断"，语义不诚实）。

两分支均先记一条 **DEBUG 观测**：`pubs.aeaweb.org/doi/pdfplus/{DOI}` 的 deferred 全文
URL（供未来 browser-fetch 通道消费，§3.3"deferred 全文 URL 记录"）。**不构造实际
`AssetPlan`**：aea.md §3.3 提及的 `url_strategy=BROWSER`/`AssetPlan.state=deferred`
是否入冻结件由 browser-fetch 通道详设（D1）统一定，**本 adapter 不新增冻结件**
（★接缝 A-1，`types.py` 零改动）——因此 `resolve_assets` 结构性地从不返回非空
`AssetPlan` 列表（全部落 raise/空列表两分支），这是刻意的诚实边界，不是遗漏：伪造
一个我们知道无法 stateless fetch 的 `AssetPlan`（凭空套用现有 `UrlStrategy` 值）
会让 pipeline 误以为存在可执行的取回路径，与"声明恒 BLOCKED 的能力不诚实"（§4）
同一原则的镜像应用。

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
    AssetPlan,
    AuthLevel,
    Capability,
    HealthReport,
    PaperStub,
    RatePolicy,
    SessionHandle,
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
    # §4 论证：ENUMERATE 不声明（委 crossref，D-005）；FETCH 不声明（全文域恒 CF
    # challenge，声明恒 BLOCKED 的能力不诚实）。RESOLVE 是本 Phase 唯一声明的能力。
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
        """DOI 双形态解析 + venue OA-class 静态分类（零网络，§3.3）——订阅刊 raise
        `NO_ENTITLEMENT`；OA 刊（jel/jep）返回空列表。两分支均先记 deferred 全文 URL
        的 DEBUG 观测（模块 docstring 展开）。`session` 未使用（本 Phase 无认证会话，
        冻结协议签名要求携带该形参）。
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
        log_event(
            "DEBUG",
            "aea fulltext deferred (browser-fetch channel pending; pubs.aeaweb.org CF challenge)",
            stage="resolve",
            domain=_FULLTEXT_HOST,
            deferred_url=_deferred_fulltext_url(doi),
            doi=doi,
            doi_form=parsed.doi_form,
            venue=venue.id,
            auth_needed=(AuthLevel.INSTITUTIONAL if subscription else AuthLevel.NONE).value,
        )

        if subscription:
            # AC-4.3 同构映射（§3.3/§6）：无机构订阅会话 → no_entitlement，不计
            # failures（auth-framework §8.5）；pipeline 侧转 OA-fallback（§8.1）。
            raise CrawlerError(
                ErrorClass.NO_ENTITLEMENT,
                f"aea: no institutional session for {doi} (subscription venue {venue.id!r})",
                detail="no_entitlement",
            )
        return []

    def healthcheck(self, session: SessionHandle | None = None) -> HealthReport:
        """本 Phase 无网络 FETCH 探针——恒 `NotImplementedError`（→ canary SKIP，§3.5）。"""
        raise NotImplementedError(
            "aea 全文能力本 Phase 未落地（browser-fetch 通道待裁，aea.md §3.5）"
        )

    # `discover_timeline`/`enumerate_issue`/`fetch_asset` 未声明能力（capabilities 仅
    # RESOLVE）——不覆写，沿用 `AdapterBase` 默认的 `CapabilityNotSupported`（crossref/
    # elsevier_sd/unpaywall 先例）。


__all__ = ["AeaAdapter"]
