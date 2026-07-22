"""SourceAdapter 协议、便利基类与注册发现（接口冻结件 §2.3）。

注册语义（design/02 §4）：`load_adapters()` 先注册包内内置者（三个占位 stub +
mock），再扫描 entry point 组 `paper_crawler.adapters` 覆盖/新增（第三方可插拔的
"插"）。key = adapter_id。
"""

from collections.abc import Iterable, Mapping
from importlib import metadata
from typing import Literal, Protocol, runtime_checkable

from paper_crawler.errors import CapabilityNotSupported
from paper_crawler.http import HttpClient
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
    # 可选加固标记（**不进** SourceAdapter 冻结协议——纯附加，缺省语义与既有一致）：声明本
    # adapter 的 `resolve_assets` 是**可证明零网络**的纯 URL 构造（从 identifier / enumerate
    # 携带的 meta 直接拼 URL，不发任何 HTTP 请求）。pipeline 据此在 resolve 阶段豁免
    # per-domain 限速闸——大 venue pull 可用性：2260 篇量级不再被逐篇限速空转（缺陷 C-C）。
    # 默认 False = 安全侧（保留限速闸）：只有子类**逐个证明**零网络后才显式置 True；真实网络
    # resolve 策略（需发请求）绝不置 True——其限速仍由闸 + HttpClient 逐请求限速承担。未继承
    # 本基类的第三方 adapter 无此属性时，pipeline 经 getattr 兜底 False（同样保留闸）。
    resolve_offline: bool = False

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


@runtime_checkable
class HttpClientConsumer(Protocol):
    """真实 adapter 声明"可注入共享 `HttpClient`"的可选协议（duck-typed）。

    `load_adapters()` 经 entry point 无参实例化 adapter，无法在构造期注入依赖；
    实现本协议的 adapter（如 arxiv）暴露 `set_http_client`，供 CLI 在装配期经
    `bind_http_client` 注入从 config 组装（UA 携 `[identity].email`）的共享 client。
    """

    def set_http_client(self, client: HttpClient) -> None: ...


@runtime_checkable
class EmailConsumer(Protocol):
    """真实 adapter 声明"可注入裸联系邮箱字符串"的可选协议（duck-typed，沿
    `HttpClientConsumer` 先例）。

    与 `HttpClientConsumer` 不同：本协议注入的是**裸邮箱字符串**，而非已装配好的
    `HttpClient`。存在原因——unpaywall 的 `?email=<addr>` 是 URL 查询参数（而非
    HTTP 头），无法从已装配的 `HttpClient`（只暴露 header/UA）反推出邮箱原文；
    CLI 装配期另行注入（值来源 `Config.identity_email`，T5 aggregators.md §3）。
    不实现该协议的 adapter 不参与此注入（如无需邮箱的 adapter）。
    """

    def set_email(self, email: str | None) -> None: ...


def bind_http_client(adapters: Mapping[str, SourceAdapter], client: HttpClient) -> list[str]:
    """把共享 `client` 注入所有实现 `HttpClientConsumer` 的 adapter；返回被注入的 id 列表。

    不实现该协议的 adapter（stub / mock）静默跳过——它们无网络访问、无需 client。
    """
    injected: list[str] = []
    for adapter_id, adapter in adapters.items():
        if isinstance(adapter, HttpClientConsumer):
            adapter.set_http_client(client)
            injected.append(adapter_id)
    return injected


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
    )

    adapters: dict[str, SourceAdapter] = {}
    for builtin in (
        CrossrefStub(),
        ElsevierScienceDirectStub(),
        MockPlatformAdapter(),
    ):
        adapters[builtin.adapter_id] = builtin

    for entry_point in metadata.entry_points(group=ADAPTER_ENTRY_POINT_GROUP):
        adapter_cls = entry_point.load()
        instance = adapter_cls()
        adapters[instance.adapter_id] = instance

    return adapters
