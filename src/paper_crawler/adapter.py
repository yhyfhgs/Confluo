"""SourceAdapter 协议、便利基类与注册发现（接口冻结件 §2.3）。

注册语义（design/02 §4）：`load_adapters()` 先注册包内内置者（三个占位 stub +
mock），再扫描 entry point 组 `paper_crawler.adapters` 覆盖/新增（第三方可插拔的
"插"）。key = adapter_id。
"""

from collections.abc import Iterable
from importlib import metadata
from typing import Literal, Protocol, runtime_checkable

from paper_crawler.errors import CapabilityNotSupported
from paper_crawler.types import (
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
    VenueSpec,
)

ADAPTER_ENTRY_POINT_GROUP = "paper_crawler.adapters"

AdapterFamily = Literal["open_access", "auth_gated", "aggregator"]


@runtime_checkable
class SourceAdapter(Protocol):
    """一个平台的爬取协议；能力缺失即由 Registry 路由给 metadata_source（design/02 §3）。"""

    adapter_id: str
    family: AdapterFamily
    capabilities: Capability
    default_rate: RatePolicy
    auth_requirement: AuthLevel
    domains: tuple[str, ...]  # 限速/日志归属域；[0] 为主域

    def discover_timeline(
        self, venue: VenueSpec, since: str | None = None
    ) -> Iterable[IssueRef]: ...

    def enumerate_issue(self, venue: VenueSpec, issue: IssueRef) -> Iterable[PaperStub]: ...

    def resolve_assets(
        self, venue: VenueSpec, paper: PaperStub, session: SessionHandle | None = None
    ) -> list[AssetPlan]: ...

    def fetch_asset(
        self, plan: AssetPlan, io: FetchIO, session: SessionHandle | None = None
    ) -> FetchResult: ...

    def healthcheck(self, session: SessionHandle | None = None) -> HealthReport: ...


class AdapterBase:
    """便利基类：未声明能力的方法默认 raise CapabilityNotSupported；healthcheck 默认 healthy。

    子类只需设类属性（adapter_id/family/capabilities/default_rate/auth_requirement/domains）
    并覆盖自己声明能力对应的方法。
    """

    adapter_id: str
    family: AdapterFamily
    capabilities: Capability
    default_rate: RatePolicy
    auth_requirement: AuthLevel
    domains: tuple[str, ...]

    def discover_timeline(self, venue: VenueSpec, since: str | None = None) -> Iterable[IssueRef]:
        raise CapabilityNotSupported(f"{self.adapter_id} lacks DISCOVER")

    def enumerate_issue(self, venue: VenueSpec, issue: IssueRef) -> Iterable[PaperStub]:
        raise CapabilityNotSupported(f"{self.adapter_id} lacks ENUMERATE")

    def resolve_assets(
        self, venue: VenueSpec, paper: PaperStub, session: SessionHandle | None = None
    ) -> list[AssetPlan]:
        raise CapabilityNotSupported(f"{self.adapter_id} lacks RESOLVE")

    def fetch_asset(
        self, plan: AssetPlan, io: FetchIO, session: SessionHandle | None = None
    ) -> FetchResult:
        raise CapabilityNotSupported(f"{self.adapter_id} lacks FETCH")

    def healthcheck(self, session: SessionHandle | None = None) -> HealthReport:
        return HealthReport(healthy=True)


def load_adapters() -> dict[str, SourceAdapter]:
    """构建 adapter_id → adapter 实例表。

    顺序：先内置（stubs + mock），再扫描 entry point 组覆盖/新增（design/02 §4）。
    延迟导入内置 adapter 以避免与本模块的 import 环。
    """
    # 延迟导入：adapters.* 在模块顶层 `from paper_crawler.adapter import AdapterBase`，
    # 若在此模块顶层导入它们会成环。
    from paper_crawler.adapters.mock_platform import MockPlatformAdapter
    from paper_crawler.adapters.stubs import (
        CrossrefStub,
        ElsevierScienceDirectStub,
        OpenReviewStub,
    )

    adapters: dict[str, SourceAdapter] = {}
    for builtin in (
        CrossrefStub(),
        OpenReviewStub(),
        ElsevierScienceDirectStub(),
        MockPlatformAdapter(),
    ):
        adapters[builtin.adapter_id] = builtin

    for entry_point in metadata.entry_points(group=ADAPTER_ENTRY_POINT_GROUP):
        adapter_cls = entry_point.load()
        instance = adapter_cls()
        adapters[instance.adapter_id] = instance

    return adapters
