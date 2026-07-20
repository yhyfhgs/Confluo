"""mock_platform —— Phase 1 的假 adapter（T1 只落骨架）。

类属性齐全，供 registry 路由与契约测试的元数据校验消费；四个能力方法体在 T6
实现（确定性、程序内生成语料，零网络）。healthcheck 沿用 AdapterBase 的 healthy 默认
（本地 mock 恒健康）。
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


class MockPlatformAdapter(AdapterBase):
    """本地确定性 mock；驱动 Phase 1 全 pipeline（AC-1.x）。"""

    adapter_id = "mock_platform"
    family: AdapterFamily = "open_access"
    capabilities = (
        Capability.DISCOVER | Capability.ENUMERATE | Capability.RESOLVE | Capability.FETCH
    )
    default_rate = RatePolicy(600, burst=10, source_note="本地 mock，无真实站点约束")
    auth_requirement = AuthLevel.NONE
    domains: tuple[str, ...] = ("mock.local",)

    def discover_timeline(self, venue: VenueSpec, since: str | None = None) -> Iterable[IssueRef]:
        raise NotImplementedError("T6")

    def enumerate_issue(self, venue: VenueSpec, issue: IssueRef) -> Iterable[PaperStub]:
        raise NotImplementedError("T6")

    def resolve_assets(
        self, venue: VenueSpec, paper: PaperStub, session: SessionHandle | None = None
    ) -> list[AssetPlan]:
        raise NotImplementedError("T6")

    def fetch_asset(
        self, plan: AssetPlan, io: FetchIO, session: SessionHandle | None = None
    ) -> FetchResult:
        raise NotImplementedError("T6")
