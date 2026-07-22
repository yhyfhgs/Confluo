"""占位 adapters（Phase 4 实现）——让 jfe 等 VenueSpec 可通过 lint。

由 `load_adapters()` 内置注册（不走 entry point，包内占位）。已声明能力的方法抛
`NotImplementedError("stub until Phase N")`（声明但未实现）；未声明能力的方法沿用
`AdapterBase` 的 `CapabilityNotSupported`。限速默认值为占位（`⚠`），真实值在对应
Phase 按站点勘察核定。

（openreview 已在 Phase 2 落地为真实 adapter，经 entry point 注册——见
adapters/openreview/；此前的 OpenReviewStub 已退役。crossref 同理已在 Phase 3
落地为真实 adapter，经 entry point 注册——见 adapters/crossref/；此前的
CrossrefStub 已退役，Phase 4 M2b 债务清理一并移除本文件里的残留类与过时注释，见
docs/reports/2026-07-23-phase3-report.md §6 检查单 #15d。本文件现只剩
`elsevier_sd` 一个真占位——它没有 entry point 注册，`load_adapters()` 返回的
就是这里定义的 stub 本身，不是"内置注册但被覆盖"的死代码。）
"""

from paper_crawler.adapter import AdapterBase, AdapterFamily
from paper_crawler.types import (
    AssetPlan,
    AuthLevel,
    Capability,
    FetchIO,
    FetchResult,
    HealthReport,
    PaperStub,
    RatePolicy,
    SessionHandle,
    VenueSpec,
)


class ElsevierScienceDirectStub(AdapterBase):
    """Elsevier ScienceDirect（JFE 等，Phase 4）。仅 resolve/fetch，机构认证。"""

    adapter_id = "elsevier_sd"
    family: AdapterFamily = "auth_gated"
    capabilities = Capability.RESOLVE | Capability.FETCH
    default_rate = RatePolicy(10, source_note="⚠ 占位；Phase 4 定值")
    auth_requirement = AuthLevel.INSTITUTIONAL
    domains: tuple[str, ...] = ("www.sciencedirect.com",)

    def resolve_assets(
        self, venue: VenueSpec, paper: PaperStub, session: SessionHandle | None = None
    ) -> list[AssetPlan]:
        raise NotImplementedError("stub until Phase 4")

    def fetch_asset(
        self, plan: AssetPlan, io: FetchIO, session: SessionHandle | None = None
    ) -> FetchResult:
        raise NotImplementedError("stub until Phase 4")

    def healthcheck(self, session: SessionHandle | None = None) -> HealthReport:
        # canary SKIP 语义修正（T3 backlog）：stub 未实现健康探测——抛
        # NotImplementedError 让 canary 归为 SKIP，而非继承 AdapterBase 默认恒
        # healthy 假报"健康"（stub 无真实站点可探）。真实 healthcheck 随 Phase 4。
        raise NotImplementedError("stub until Phase 4")
