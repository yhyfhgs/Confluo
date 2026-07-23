"""adapter.py（§2.3）单测：注册发现、元数据完备、能力路由（Capability/NotImplemented）。"""

import pytest

from paper_crawler.adapter import (
    HttpClientConsumer,
    SourceAdapter,
    bind_http_client,
    load_adapters,
)
from paper_crawler.errors import CapabilityNotSupported
from paper_crawler.http import HttpClient
from paper_crawler.types import (
    AssetKind,
    AssetPlan,
    AuthLevel,
    Capability,
    HealthReport,
    IssueRef,
    PaperStub,
    RatePolicy,
    VenueSpec,
)

EXPECTED_ADAPTER_IDS = {
    "mock_platform",
    "crossref",
    "openreview",
    "elsevier_sd",
    "arxiv",
    "pmlr",
    "acl_anthology",
    "cvf",
    "aaai_ojs",
    "neurips_proceedings",
    "unpaywall",
    "dblp",
    "wiley",  # Phase 4 T-wiley（auth_gated；RESOLVE|FETCH，TDM API + token 门控）
    "openalex",  # T6
    "s2",  # T6
    "oup_silverchair",  # Phase 4 T4（auth_gated，RESOLVE|FETCH）
    "aea",  # Phase 5 T5（auth_gated，RESOLVE-only offline；enumerate 走 crossref）
}
VALID_FAMILIES = {"open_access", "auth_gated", "aggregator"}


@pytest.fixture
def adapters() -> dict[str, SourceAdapter]:
    return load_adapters()


def test_load_adapters_discovers_all_registered(adapters: dict[str, SourceAdapter]) -> None:
    # 内置 mock + 全部真实 adapter（entry point 注册；占位 stub 均已退役，含 Phase 4 T3 的
    # elsevier_sd——现为真实 auth_gated adapter，非 stub）。
    assert set(adapters) == EXPECTED_ADAPTER_IDS


def test_every_adapter_has_complete_metadata(adapters: dict[str, SourceAdapter]) -> None:
    for adapter_id, adapter in adapters.items():
        assert adapter.adapter_id == adapter_id
        assert adapter.family in VALID_FAMILIES
        assert isinstance(adapter.capabilities, Capability)
        assert isinstance(adapter.default_rate, RatePolicy)
        assert adapter.default_rate.source_note != ""  # 出处必注（design/02）
        assert adapter.default_rate.requests_per_minute > 0
        assert isinstance(adapter.auth_requirement, AuthLevel)
        assert adapter.domains  # 非空
        assert all(isinstance(d, str) and d for d in adapter.domains)


def test_adapters_satisfy_runtime_checkable_protocol(
    adapters: dict[str, SourceAdapter],
) -> None:
    for adapter in adapters.values():
        assert isinstance(adapter, SourceAdapter)


def test_mock_platform_attributes(adapters: dict[str, SourceAdapter]) -> None:
    mock = adapters["mock_platform"]
    assert mock.family == "open_access"
    assert (
        mock.capabilities
        == Capability.DISCOVER | Capability.ENUMERATE | Capability.RESOLVE | Capability.FETCH
    )
    assert mock.default_rate.requests_per_minute == 600
    assert mock.default_rate.burst == 10
    assert mock.auth_requirement is AuthLevel.NONE
    assert mock.domains == ("mock.local",)


def test_crossref_attributes(adapters: dict[str, SourceAdapter]) -> None:
    # Phase 3 T3：crossref 落地为真实 aggregator adapter（entry point 注册），非 stub。
    crossref = adapters["crossref"]
    assert crossref.family == "aggregator"
    # aggregators.md §1：DISCOVER|ENUMERATE，无 SEARCH/RESOLVE/FETCH（五源均无 FETCH）。
    assert crossref.capabilities == Capability.DISCOVER | Capability.ENUMERATE
    assert Capability.SEARCH not in crossref.capabilities
    assert Capability.FETCH not in crossref.capabilities
    assert crossref.default_rate.requests_per_minute == 300.0  # 5 req/s 保守上限（§4）
    assert "X-Rate-Limit" in crossref.default_rate.source_note  # 出处（非占位 ⚠）
    assert crossref.auth_requirement is AuthLevel.NONE
    assert crossref.domains == ("api.crossref.org",)


def test_openreview_attributes(adapters: dict[str, SourceAdapter]) -> None:
    # Phase 2 T-openreview：真实 adapter（entry point 注册），非 stub。
    openreview = adapters["openreview"]
    assert openreview.family == "open_access"
    assert (
        openreview.capabilities
        == Capability.DISCOVER | Capability.ENUMERATE | Capability.RESOLVE | Capability.FETCH
    )
    assert Capability.SEARCH not in openreview.capabilities
    assert openreview.default_rate.requests_per_minute == 30
    assert "OpenReview" in openreview.default_rate.source_note  # 出处（非占位 ⚠）
    assert openreview.auth_requirement is AuthLevel.FREE_ACCOUNT  # notes/PDF 需 token（§3）
    assert openreview.domains == (
        "api2.openreview.net",
        "api.openreview.net",
        "openreview.net",
    )


def test_elsevier_attributes(adapters: dict[str, SourceAdapter]) -> None:
    # Phase 4 T3：elsevier_sd 落地为真实 auth_gated/官方 API adapter（entry point 注册），非 stub。
    # 域自 www.sciencedirect.com（页面路线，robots 全禁）改 api.elsevier.com（API 唯一正道，
    # elsevier-sd.md §2）；限速自占位 10 → 自限 2 req/s = 120 rpm（§4）。
    elsevier = adapters["elsevier_sd"]
    assert elsevier.family == "auth_gated"
    assert elsevier.capabilities == Capability.RESOLVE | Capability.FETCH  # enumerate 走 crossref
    assert Capability.DISCOVER not in elsevier.capabilities
    assert Capability.ENUMERATE not in elsevier.capabilities
    assert elsevier.auth_requirement is AuthLevel.INSTITUTIONAL
    assert elsevier.default_rate.requests_per_minute == 120.0
    assert "Elsevier" in elsevier.default_rate.source_note  # 出处（非占位 ⚠）
    assert elsevier.domains == ("api.elsevier.com",)
    # 凭证注入 seam（专属 client + key 门控）：实现 HttpClientConsumer + ApiKeyConsumer。
    assert isinstance(elsevier, HttpClientConsumer)


def test_arxiv_attributes(adapters: dict[str, SourceAdapter]) -> None:
    arxiv = adapters["arxiv"]
    assert arxiv.family == "open_access"
    # arxiv.md §1 裁决：DISCOVER|ENUMERATE|RESOLVE|FETCH，无 SEARCH。
    assert (
        arxiv.capabilities
        == Capability.DISCOVER | Capability.ENUMERATE | Capability.RESOLVE | Capability.FETCH
    )
    assert Capability.SEARCH not in arxiv.capabilities
    assert arxiv.default_rate.requests_per_minute == 20.0  # 1 req/3s
    assert "Terms of Use" in arxiv.default_rate.source_note  # ToU 出处
    assert arxiv.auth_requirement is AuthLevel.NONE
    assert arxiv.domains == ("export.arxiv.org", "oaipmh.arxiv.org", "arxiv.org")


def test_pmlr_attributes(adapters: dict[str, SourceAdapter]) -> None:
    pmlr = adapters["pmlr"]
    assert pmlr.family == "open_access"
    # pmlr.md §1 裁决：DISCOVER|ENUMERATE|RESOLVE|FETCH，无 SEARCH。
    assert (
        pmlr.capabilities
        == Capability.DISCOVER | Capability.ENUMERATE | Capability.RESOLVE | Capability.FETCH
    )
    assert Capability.SEARCH not in pmlr.capabilities
    assert pmlr.default_rate.requests_per_minute == 30.0  # 1 req/2s
    assert pmlr.auth_requirement is AuthLevel.NONE
    assert pmlr.domains == ("proceedings.mlr.press", "raw.githubusercontent.com")


def test_cvf_attributes(adapters: dict[str, SourceAdapter]) -> None:
    cvf = adapters["cvf"]
    assert cvf.family == "open_access"
    # design/adapters/cvf.md §1 裁决：DISCOVER|ENUMERATE|RESOLVE|FETCH，无 SEARCH。
    assert (
        cvf.capabilities
        == Capability.DISCOVER | Capability.ENUMERATE | Capability.RESOLVE | Capability.FETCH
    )
    assert Capability.SEARCH not in cvf.capabilities
    assert cvf.default_rate.requests_per_minute == 30.0  # 1 req/2s
    assert "site-survey/cvf.md" in cvf.default_rate.source_note  # 出处（非占位 ⚠）
    assert cvf.auth_requirement is AuthLevel.NONE  # 匿名可读、无认证（§2/§4）
    assert cvf.domains == ("openaccess.thecvf.com",)


def test_neurips_proceedings_attributes(adapters: dict[str, SourceAdapter]) -> None:
    neurips = adapters["neurips_proceedings"]
    assert neurips.family == "open_access"
    # design/adapters/neurips-proceedings.md §1 裁决：DISCOVER|ENUMERATE|RESOLVE|FETCH，无 SEARCH。
    assert (
        neurips.capabilities
        == Capability.DISCOVER | Capability.ENUMERATE | Capability.RESOLVE | Capability.FETCH
    )
    assert Capability.SEARCH not in neurips.capabilities
    assert neurips.default_rate.requests_per_minute == 30.0  # 1 req/2s
    assert neurips.auth_requirement is AuthLevel.NONE
    assert neurips.domains == (
        "proceedings.neurips.cc",
        "papers.neurips.cc",
        "papers.nips.cc",
    )


def test_aea_attributes(adapters: dict[str, SourceAdapter]) -> None:
    # Phase 5 T5：aea 落地为真实 auth_gated adapter（entry point 注册）。RESOLVE-only
    # offline——enumerate 走 crossref（D-005）、FETCH 本 Phase 不声明（全文域
    # pubs.aeaweb.org 恒 CF challenge，aea.md §4 论证；声明恒 BLOCKED 的能力不诚实）。
    aea = adapters["aea"]
    assert aea.family == "auth_gated"
    # `not in` 断言须排在单值 `==` 断言之前——mypy 对 Flag 单值 Literal 窄化后的
    # `in`/`not in` 支持不佳（同 elsevier_sd 复合位组合 `RESOLVE | FETCH` 无此问题，
    # 只有单一位 `RESOLVE` 才触发，纯 mypy 顺序敏感性、非语义差异）。
    assert Capability.DISCOVER not in aea.capabilities
    assert Capability.ENUMERATE not in aea.capabilities
    assert Capability.FETCH not in aea.capabilities
    assert aea.capabilities == Capability.RESOLVE
    # 本 Phase 无认证实现（D-006 CookieSession 留将来）——adapter 自身零门槛；订阅刊
    # venue YAML 的 auth.level=institutional 是前瞻声明，不矛盾（aea.md §1）。
    assert aea.auth_requirement is AuthLevel.NONE
    assert aea.default_rate.requests_per_minute == 30.0
    assert "aeaweb.org" in aea.default_rate.source_note  # 出处（非占位 ⚠）
    assert aea.domains == ("www.aeaweb.org",)
    # resolve_assets 证明零网络（DOI 形态解析 + venue.auth.level 静态分类）——pipeline
    # 据此在 resolve 阶段豁免限速闸（adapter.py `resolve_offline` docstring）。`resolve_
    # offline` 不进 `SourceAdapter` 冻结协议（纯附加标记，adapter.py docstring）——
    # `getattr` 读取沿 pipeline 消费方的兜底约定，避免对 Protocol 类型断言未声明属性。
    assert getattr(aea, "resolve_offline", None) is True


def test_healthcheck_defaults_healthy(adapters: dict[str, SourceAdapter]) -> None:
    # mock_platform 不覆写 healthcheck → 继承 AdapterBase 默认恒 healthy。
    # （stub adapter 现已覆写为抛 NotImplementedError，见下一个测试。）
    report = adapters["mock_platform"].healthcheck()
    assert isinstance(report, HealthReport)
    assert report.healthy is True


@pytest.mark.parametrize("adapter_id", ["elsevier_sd"])
def test_keyless_auth_gated_healthcheck_raises_not_implemented_for_canary_skip(
    adapters: dict[str, SourceAdapter], adapter_id: str
) -> None:
    """canary SKIP 语义（B-M4）：无 key 的 auth_gated adapter healthcheck 抛 NotImplementedError。

    `load_adapters()` 拿到的 elsevier_sd 未经装配期注入 key（`set_api_key` 未调用）——无 key
    分支抛 `NotImplementedError`（复用 s2/openalex 先例），`run_canary` 归为 SKIP（不影响退出码，
    见 canary.py），而非匿名假报"健康"或"不健康"。有 key 时改走 entitlement 探测（见
    tests/unit/test_elsevier_adapter.py::test_healthcheck_*）。elsevier_sd 已 Phase 4 T3 落地为
    真实 adapter，此处验证的是其**无凭证**路径（AuthProvider session 注入归 T5）。
    """
    with pytest.raises(NotImplementedError):
        adapters[adapter_id].healthcheck()


def test_undeclared_capability_raises_capability_not_supported(
    adapters: dict[str, SourceAdapter], venue: VenueSpec
) -> None:
    paper = PaperStub(title="T", identifiers=(("doi", "10.9999/x"),))
    plan = AssetPlan(kind=AssetKind.PDF, url="https://x/y")

    # crossref 无 RESOLVE/FETCH（AdapterBase 兜底）。
    with pytest.raises(CapabilityNotSupported):
        adapters["crossref"].resolve_assets(venue, paper)
    with pytest.raises(CapabilityNotSupported):
        adapters["crossref"].fetch_asset(plan, io=_null_io())

    # elsevier_sd 无 DISCOVER/ENUMERATE（AdapterBase 兜底）。
    with pytest.raises(CapabilityNotSupported):
        adapters["elsevier_sd"].discover_timeline(venue)
    with pytest.raises(CapabilityNotSupported):
        adapters["elsevier_sd"].enumerate_issue(venue, IssueRef(venue_id=venue.id))


# （Phase 4 T3：曾有 `test_declared_stub_methods_are_not_implemented` 断言 elsevier_sd stub 的
# RESOLVE|FETCH 抛 NotImplementedError——elsevier_sd 落地为真实 adapter 后已移除：无占位 stub 残留，
# 且其无 key 分支现抛 `AuthRequired`（非 NotImplementedError，见 test_elsevier_adapter.py 的
# resolve/fetch 无 key 用例）。）


def test_mock_platform_methods_are_implemented_after_t6(
    adapters: dict[str, SourceAdapter], venue: VenueSpec
) -> None:
    # T6 落地：mock_platform 不再 NotImplementedError（区别于仍是 stub 的
    # crossref/openreview，见 test_declared_stub_methods_are_not_implemented）。
    # 语料细节（quirks 派生、故障注入等）见 tests/unit/test_mock_platform.py；
    # 这里只验证经 load_adapters() 拿到的实例确实可用。
    issues = list(adapters["mock_platform"].discover_timeline(venue))
    assert issues


# --- HttpClient 注入（bind_http_client / HttpClientConsumer 协议）--------------------------


def test_arxiv_is_http_client_consumer(adapters: dict[str, SourceAdapter]) -> None:
    """真实 http adapter 实现 `HttpClientConsumer`（可注入共享 client）；stub/mock 不实现。

    ★共享花名册（5 线并行 union 点，T6 关闭——五源全部加入）：crossref/dblp/unpaywall/
    openalex/s2 均已加入 consumer 集。
    """
    for adapter_id in (
        "arxiv",
        "openreview",
        "pmlr",
        "acl_anthology",
        "cvf",
        "aaai_ojs",
        "neurips_proceedings",
        "crossref",  # T3：aggregator 亦经注入携 config mailto 的 client（polite pool 硬要求）
        "openalex",  # T6
        "s2",  # T6
        "elsevier_sd",  # Phase 4 T3：auth_gated，专属 client 注入（X-ELS-APIKey 头）
    ):
        assert isinstance(adapters[adapter_id], HttpClientConsumer)

    assert not isinstance(adapters["mock_platform"], HttpClientConsumer)


def test_bind_http_client_injects_only_consumers(adapters: dict[str, SourceAdapter]) -> None:
    """`bind_http_client` 只注入实现协议的 adapter，返回被注入的 id 列表。

    ★共享花名册（5 线并行 union 点，T6 关闭——五源全部加入）。
    """
    client = HttpClient(user_agent="PaperCrawler/test (personal research)")
    injected = bind_http_client(adapters, client)
    # 真实 http adapter；注入生效——_client() 返回被注入实例，不再惰性自建。
    assert set(injected) == {
        "arxiv",
        "openreview",
        "pmlr",
        "acl_anthology",
        "cvf",
        "aaai_ojs",
        "neurips_proceedings",
        "crossref",
        "unpaywall",
        "dblp",
        "wiley",  # Phase 4 T-wiley（auth_gated；专属 token client 的 CLI 覆盖属后续 union 点）
        "openalex",  # T6
        "s2",  # T6
        "elsevier_sd",  # Phase 4 T3：auth_gated，专属 client 注入 seam（X-ELS-APIKey 头）
    }
    # 注入生效：各 adapter 的 _client() 返回被注入的实例，不再惰性自建。

    arxiv = adapters["arxiv"]
    pmlr = adapters["pmlr"]
    neurips = adapters["neurips_proceedings"]
    assert isinstance(arxiv, HttpClientConsumer)
    assert isinstance(pmlr, HttpClientConsumer)
    assert isinstance(neurips, HttpClientConsumer)
    assert arxiv._client() is client  # type: ignore[attr-defined]
    assert pmlr._client() is client  # type: ignore[attr-defined]
    assert neurips._client() is client  # type: ignore[attr-defined]


class _NullIO:
    def write_stream(self, chunks: object) -> tuple[int, str]:
        return (0, "")


def _null_io() -> _NullIO:
    return _NullIO()
