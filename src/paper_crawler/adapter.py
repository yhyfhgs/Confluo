"""SourceAdapter 协议、便利基类与注册发现（接口冻结件 §2.3）。

注册语义（design/02 §4）：`load_adapters()` 先注册包内内置者（mock——占位 stub 均已随
各 Phase 落地退役），再扫描 entry point 组 `paper_crawler.adapters` 覆盖/新增（第三方
可插拔的"插"）。key = adapter_id。
"""

from collections.abc import Callable, Iterable, Mapping, Sequence
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

# cookie 供给函数：auth_gated cookie 档 adapter（如 oup_silverchair）经此把活跃
# `SessionHandle` 换成 cookie name→value 映射。CLI 在 auth 装配期注入一个懒解析闭包
# （见 `CookieSupplierConsumer` / `bind_cookie_supplier` / cli._cookie_supplier_for）。
CookieSupplier = Callable[[SessionHandle], Mapping[str, str]]


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


@runtime_checkable
class ApiKeyConsumer(Protocol):
    """真实 adapter 声明"可注入可选 API key 字符串"的可选协议（duck-typed，沿
    `EmailConsumer` 先例；T6 openalex/s2 引入）。

    与 `EmailConsumer` 同构但语义不同：本协议注入的是**服务端认证密钥**（openalex
    的 `api_key` 查询参数、s2 的 `x-api-key` 请求头），而非联系邮箱。key 缺省
    （`None`）时由各 adapter 自行决定匿名/降级行为——openalex 匿名仍可用（key 只是
    提升每日 credit 额度），s2 无 key 时 `enrich_batch` 直接判定 `CONFIG`、不发请求
    （aggregators.md §5.3/§5.4）。CLI 装配期传入值来源 `Config.openalex_api_key`/
    `Config.s2_api_key`。**头级 key（s2）不可经本协议反过来影响已注入的 `HttpClient`
    实例**——`x-api-key` 头必须随专属 client 的构造一次性注入（凭证隔离义务在调用
    方，避免头随共享 client 外泄到其它域，见 `adapters/s2/__init__.py` docstring）；
    本协议只负责让 adapter 自己知道"key 是否已配置"，用于 `enrich_batch`/
    `healthcheck` 的判定分支。
    """

    def set_api_key(self, key: str | None) -> None: ...


@runtime_checkable
class CookieSupplierConsumer(Protocol):
    """真实 adapter 声明"可注入 cookie 供给函数"的可选协议（duck-typed，沿
    `HttpClientConsumer` 先例；auth_gated cookie 档引入，oup_silverchair 首个实现）。

    `load_adapters()` 经 entry point 无参实例化 adapter（`_cookie_supplier=None`），无法
    在构造期注入依赖；实现本协议的 cookie 档 adapter 暴露 `set_cookie_supplier`，供 CLI
    在 auth 装配期经 `bind_cookie_supplier` 注入一个**懒解析**闭包——闭包捕获 `AuthManager`，
    真实 fetch 时才按 `session.provider_id` 解析对应 provider → `load_cookies` 解密
    storage_state → cookie 表（装配期不触发；无凭证配置时不解析、不抛）。

    与 `HttpClientConsumer` 不同：注入的是**cookie 供给函数**而非已装配 client——cookie
    必须挂在 adapter 内部的**携密专属 client**（凭证隔离红线），绝不复用共享 `HttpClient`
    （否则随他站请求外泄）；本协议只把"给 session 返 cookie 表"的能力交给 adapter，专属
    client 的构造与域限定归 adapter 自身。
    """

    def set_cookie_supplier(self, supplier: CookieSupplier) -> None: ...


@runtime_checkable
class EnrichmentSource(Protocol):
    """补充层富化源的 duck-typed 可选接口（**立于 SourceAdapter 冻结协议之外**，非五
    方法之一；plan §2-5 冻结契约，T6 openalex/s2 引入，沿 `HttpClientConsumer` 先例：
    运行期 duck-typed 甄别，不实现者静默不参与）。

    实现者（如 openalex/s2）的 `capabilities` 恒为空集——不声明 DISCOVER/ENUMERATE/
    RESOLVE/FETCH/SEARCH 中任一项，不参与 `crawler pull` 六阶段主流程。驱动路径是
    独立的 `crawler enrich` CLI 命令：扫库内带 `doi` identifier 的 paper → 按本方法
    分批查询 → 产出的 `PaperStub` 经 `MergeEngine.ingest(stub, source=…)` 回注既有
    paper（字段级来源优先级收敛天然实现"补缺不覆盖"）。`dois` 去重/长度处理是实现者
    自己的职责（不同源批量机制不同：openalex 按 URL 长度自算批量，s2 按官方文档
    ≤500/批固定切分）。
    """

    def enrich_batch(self, dois: Sequence[str]) -> list[PaperStub]: ...


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


def bind_cookie_supplier(
    adapters: Mapping[str, SourceAdapter], supplier: CookieSupplier
) -> list[str]:
    """把 cookie 供给函数注入所有实现 `CookieSupplierConsumer` 的 adapter；返回被注入 id 列表。

    不实现该协议的 adapter（无 cookie 档需求者）静默跳过——沿 `bind_http_client` 先例，对
    未来 cookie 档 adapter 通用（不硬编码 oup 单例）。`supplier` 为懒解析闭包：装配期只注入
    不调用，真实 fetch 时才解析 provider（见 `CookieSupplierConsumer` docstring）。
    """
    injected: list[str] = []
    for adapter_id, adapter in adapters.items():
        if isinstance(adapter, CookieSupplierConsumer):
            adapter.set_cookie_supplier(supplier)
            injected.append(adapter_id)
    return injected


def load_adapters() -> dict[str, SourceAdapter]:
    """构建 adapter_id → adapter 实例表。

    顺序：先内置（mock），再扫描 entry point 组覆盖/新增（design/02 §4）。
    延迟导入内置 adapter 以避免与本模块的 import 环。
    """
    # 延迟导入：adapters.* 在模块顶层 `from paper_crawler.adapter import AdapterBase`，
    # 若在此模块顶层导入它们会成环。
    from paper_crawler.adapters.mock_platform import MockPlatformAdapter

    # 占位 stub 均已退役：CrossrefStub（Phase 3 T3）、OpenReviewStub（Phase 2）、
    # ElsevierScienceDirectStub（Phase 4 T3——elsevier_sd 落地为真实 entry point adapter，
    # `adapters/elsevier_sd/`）——不再需要在此预注册必然被 entry point 扫描覆盖的死实例。
    # mock_platform 保留为内置（亦有 entry point，行为等价；Phase 1 假 adapter 基线）。
    adapters: dict[str, SourceAdapter] = {}
    for builtin in (MockPlatformAdapter(),):
        adapters[builtin.adapter_id] = builtin

    for entry_point in metadata.entry_points(group=ADAPTER_ENTRY_POINT_GROUP):
        adapter_cls = entry_point.load()
        instance = adapter_cls()
        adapters[instance.adapter_id] = instance

    return adapters
