"""占位 adapters（Phase 2/3/4 实现）——让 jfe/iclr 等 VenueSpec 可通过 lint。

三者由 `load_adapters()` 内置注册（不走 entry point，包内占位）。已声明能力的方法
抛 `NotImplementedError("stub until Phase N")`（声明但未实现）；未声明能力的方法
沿用 `AdapterBase` 的 `CapabilityNotSupported`。限速默认值均为占位（`⚠`），真实值在
对应 Phase 按站点勘察核定。
"""

from collections.abc import Iterable

from paper_crawler.adapter import AdapterBase, AdapterFamily
from paper_crawler.types import (
    AssetPlan,
    AuthLevel,
    Capability,
    FetchIO,
    FetchResult,
    IssueRef,
    PaperStub,
    RatePolicy,
    SessionHandle,
    VenueSpec,
)


class CrossrefStub(AdapterBase):
    """Crossref 元数据主干（Phase 3）。仅 discover/enumerate。"""

    adapter_id = "crossref"
    family: AdapterFamily = "aggregator"
    capabilities = Capability.DISCOVER | Capability.ENUMERATE
    default_rate = RatePolicy(
        50, source_note="⚠ 占位；Phase 3 按 research/site-survey/metadata-apis.md 定值"
    )
    auth_requirement = AuthLevel.NONE
    domains: tuple[str, ...] = ("api.crossref.org",)

    def discover_timeline(self, venue: VenueSpec, since: str | None = None) -> Iterable[IssueRef]:
        raise NotImplementedError("stub until Phase 3")

    def enumerate_issue(self, venue: VenueSpec, issue: IssueRef) -> Iterable[PaperStub]:
        raise NotImplementedError("stub until Phase 3")


class OpenReviewStub(AdapterBase):
    """OpenReview（ICLR/NeurIPS 评审等，Phase 2）。全能力。"""

    adapter_id = "openreview"
    family: AdapterFamily = "open_access"
    capabilities = (
        Capability.DISCOVER | Capability.ENUMERATE | Capability.RESOLVE | Capability.FETCH
    )
    default_rate = RatePolicy(30, source_note="⚠ 占位；Phase 2 定值")
    auth_requirement = AuthLevel.NONE
    domains: tuple[str, ...] = ("api2.openreview.net",)

    def discover_timeline(self, venue: VenueSpec, since: str | None = None) -> Iterable[IssueRef]:
        raise NotImplementedError("stub until Phase 2")

    def enumerate_issue(self, venue: VenueSpec, issue: IssueRef) -> Iterable[PaperStub]:
        raise NotImplementedError("stub until Phase 2")

    def resolve_assets(
        self, venue: VenueSpec, paper: PaperStub, session: SessionHandle | None = None
    ) -> list[AssetPlan]:
        raise NotImplementedError("stub until Phase 2")

    def fetch_asset(
        self, plan: AssetPlan, io: FetchIO, session: SessionHandle | None = None
    ) -> FetchResult:
        raise NotImplementedError("stub until Phase 2")


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
