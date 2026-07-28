"""VenueSpec YAML 校验规则单测（design/02 §2.2 校验段；AC-1.6）。

八类非法各至少一例，断言 LintIssue.field 与 message 内容：
未知 adapter / **能力位不足**（R2b/P1-12）/ auth 等级不足 / 同目录 id 重复 /
journal 缺 issn / issn 格式错 / YAML 解析失败 / pydantic 结构错误（含文件名-id 不一致）。

结构性问题（文件读取失败、YAML 解析失败、pydantic 校验失败、同目录 id 冲突、
文件名-id 不一致）由 `load_dirs()` 直接返回；语义问题（未知 adapter、能力位、auth
不兼容、issn 规则）需要 `lint()`（在已加载的 venue 上叠加校验）。仓库自带的 58 份
YAML 必须全过 lint。
"""

from pathlib import Path

import pytest

from paper_crawler.adapter import AdapterBase, AdapterFamily, SourceAdapter, load_adapters
from paper_crawler.errors import CrawlerError, ErrorClass
from paper_crawler.registry import LintIssue, VenueRegistry
from paper_crawler.types import AuthLevel, Capability, RatePolicy

REPO_VENUES_DIR = Path(__file__).resolve().parents[2] / "venues"


@pytest.fixture
def adapters() -> dict[str, SourceAdapter]:
    return load_adapters()


def _issues_for_field(issues: list[LintIssue], field: str) -> list[LintIssue]:
    return [issue for issue in issues if issue.field == field]


def _write(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


# -- 三份仓库自带 YAML 全过 lint（design/02 §6 验收前提） -----------------------


_NON_ARXIV_VENUE_IDS = {
    "mock_journal",
    "jfe",
    "iclr",
    "icml",
    "emnlp",
    "cvpr",
    "iccv",
    "wacv",
    "aaai",
    "neurips",
    # Phase 3 T7 期刊聚合层（crossref metadata_source；fulltext_source Phase 4 占位）。
    "qje",
    "jet",
    "jpubeco",
    "jbf",
    # Phase 5 T5：aea 8 刊（crossref metadata_source；fulltext_source=aea，RESOLVE-only）。
    "aer",
    "aeri",
    "aej_macro",
    "aej_micro",
    "aej_applied",
    "aej_policy",
    "jel",
    "jep",
    # Phase 5 T6 Econometric Society 三刊（econsoc；TE/QE OJS OAI，ECMA crossref+域名分段，D-028）。
    "ecma",
    "te",
    "qe",
    # Phase 5 T4：SSRN（聚合元数据主路径，站点零接触，D-029）——metadata/fulltext 均 ssrn adapter
    # （enumerate 内部委 crossref prefix 10.2139 + created 后处理，非独立 crossref 源）。
    "ssrn",
    # Phase 5 T3 nber（preprint_channel；crossref prefix 10.3386 metadata_source + nber fulltext）。
    "nber",
}


def test_shipped_venues_pass_lint_cleanly(adapters: dict[str, SourceAdapter]) -> None:
    reg = VenueRegistry(adapters)
    load_issues = reg.load_dirs([REPO_VENUES_DIR])
    assert load_issues == []
    assert reg.lint() == []
    ids = {spec.id for spec in reg.all()}
    # 基础常驻件（Phase 1 三件 + icml/emnlp + cvf 三会）。
    assert _NON_ARXIV_VENUE_IDS <= ids
    # 其余全为 arxiv preprint_channel 白名单（catalog §1，31 个 category），
    # 由 scripts/gen_arxiv_venues.py 生成；每个都 preprint_channel 且路由到 arxiv。
    arxiv_ids = {i for i in ids if i.startswith("arxiv_")}
    assert arxiv_ids == ids - _NON_ARXIV_VENUE_IDS

    assert len(arxiv_ids) == 31
    for venue_id in arxiv_ids:
        spec = reg.get(venue_id)
        assert spec.kind == "preprint_channel"
        assert spec.metadata_source == "arxiv"
        assert spec.fulltext_source == "arxiv"
    emnlp = reg.get("emnlp")
    assert emnlp.kind == "conference"
    assert emnlp.metadata_source == "acl_anthology"
    assert emnlp.fulltext_source == "acl_anthology"


def test_icml_venue_routes_to_pmlr_adapter(adapters: dict[str, SourceAdapter]) -> None:
    reg = VenueRegistry(adapters)
    reg.load_dirs([REPO_VENUES_DIR])
    spec = reg.get("icml")
    assert spec.kind == "conference"
    assert spec.metadata_source == "pmlr"
    assert spec.fulltext_source == "pmlr"
    assert spec.quirks["volume_map"] == {
        2013: 28,
        2014: 32,
        2015: 37,
        2016: 48,
        2017: 70,
        2018: 80,
        2019: 97,
        2020: 119,
        2021: 139,
        2022: 162,
        2023: 202,
        2024: 235,
        2025: 267,
    }


def test_cvf_venues_route_to_cvf_adapter(adapters: dict[str, SourceAdapter]) -> None:
    reg = VenueRegistry(adapters)
    reg.load_dirs([REPO_VENUES_DIR])
    for venue_id in ("cvpr", "iccv", "wacv"):
        spec = reg.get(venue_id)
        assert spec.kind == "conference"
        assert spec.metadata_source == "cvf"
        assert spec.fulltext_source == "cvf"


def test_aaai_venue_routes_to_aaai_ojs_adapter(adapters: dict[str, SourceAdapter]) -> None:
    reg = VenueRegistry(adapters)
    reg.load_dirs([REPO_VENUES_DIR])
    spec = reg.get("aaai")
    assert spec.kind == "conference"
    assert spec.metadata_source == "aaai_ojs"
    assert spec.fulltext_source == "aaai_ojs"
    assert spec.quirks["ojs_code"] == "AAAI"
    assert spec.quirks["volume_map"] == {
        2010: 24,
        2011: 25,
        2012: 26,
        2013: 27,
        2014: 28,
        2015: 29,
        2016: 30,
        2017: 31,
        2018: 32,
        2019: 33,
        2020: 34,
        2021: 35,
        2022: 36,
        2023: 37,
        2024: 38,
        2025: 39,
        2026: 40,
    }


def test_neurips_venue_routes_to_neurips_proceedings_adapter(
    adapters: dict[str, SourceAdapter],
) -> None:
    reg = VenueRegistry(adapters)
    reg.load_dirs([REPO_VENUES_DIR])
    spec = reg.get("neurips")
    assert spec.kind == "conference"
    assert spec.metadata_source == "neurips_proceedings"
    assert spec.fulltext_source == "neurips_proceedings"
    assert spec.auth.level.value == "none"
    assert spec.quirks["first_year"] == 1987
    assert spec.identifiers["dblp_key"] == "conf/nips"


_AEA_VENUE_IDS = {
    "aer",
    "aeri",
    "aej_macro",
    "aej_micro",
    "aej_applied",
    "aej_policy",
    "jel",
    "jep",
}
_AEA_SUBSCRIPTION_VENUE_IDS = {"aer", "aeri", "aej_macro", "aej_micro", "aej_applied", "aej_policy"}
_AEA_OPEN_VENUE_IDS = {"jel", "jep"}


@pytest.mark.parametrize("venue_id", sorted(_AEA_VENUE_IDS))
def test_aea_venues_route_to_aea_adapter(adapters: dict[str, SourceAdapter], venue_id: str) -> None:
    """8 刊全部 metadata_source=crossref（D-005）、fulltext_source=aea（aea.md §7）。"""
    reg = VenueRegistry(adapters)
    reg.load_dirs([REPO_VENUES_DIR])
    spec = reg.get(venue_id)
    assert spec.kind == "journal"
    assert spec.metadata_source == "crossref"
    assert spec.fulltext_source == "aea"
    assert spec.identifiers["issn"]  # D-015 期刊必填，非空
    assert spec.quirks["doi_forms"] == ["submission", "vol_issue_page", "pnp"]
    assert spec.quirks["ai_bot_sensitive"] is True


def test_aea_subscription_venues_declare_institutional_auth(
    adapters: dict[str, SourceAdapter],
) -> None:
    """订阅 6 刊（aer/aeri/aej_×4）auth.level=institutional——刊物访问级前瞻声明
    （aea.md §1 层次澄清；不触 registry.py:234，adapter auth_requirement=none 是零门槛
    下限，任何 venue auth.level 都不会低于它）。
    """
    reg = VenueRegistry(adapters)
    reg.load_dirs([REPO_VENUES_DIR])
    for venue_id in sorted(_AEA_SUBSCRIPTION_VENUE_IDS):
        assert reg.get(venue_id).auth.level.value == "institutional", venue_id


def test_aea_open_venues_declare_no_auth(adapters: dict[str, SourceAdapter]) -> None:
    """jel/jep 免费/gold OA 刊——auth.level=none（aea.md §7）。"""
    reg = VenueRegistry(adapters)
    reg.load_dirs([REPO_VENUES_DIR])
    for venue_id in sorted(_AEA_OPEN_VENUE_IDS):
        assert reg.get(venue_id).auth.level.value == "none", venue_id


def test_aea_code_to_venue_routing_table_matches_shipped_venues() -> None:
    """`parse.CODE_TO_VENUE` 的路由目标恰为本次 shipped 的 8 刊 id 集合（防止路由表
    与实际注册 venue 静默漂移——8 刊路由正确性是 aea.md §9 建议关联 AC-5.4 的判据）。
    """
    from paper_crawler.adapters.aea.parse import CODE_TO_VENUE

    assert set(CODE_TO_VENUE.values()) == _AEA_VENUE_IDS
    # code≠venue id 的非平凡路由（子刊路由表核心裁决，aea.md §3.2）。
    assert CODE_TO_VENUE["mac"] == "aej_macro"
    assert CODE_TO_VENUE["app"] == "aej_applied"
    assert CODE_TO_VENUE["mic"] == "aej_micro"
    assert CODE_TO_VENUE["pol"] == "aej_policy"


def test_econsoc_venues_route_correctly(adapters: dict[str, SourceAdapter]) -> None:
    """econsoc 三刊路由（D-028/econsoc.md §3.5）：TE/QE 自持 OJS OAI（metadata=fulltext=econsoc
    + ojs_code/oai_base/volume_map quirks）；ECMA crossref-枚举 + econsoc 分段 fulltext（真分离，
    crossref 为 aggregator——lint 通过）。"""
    reg = VenueRegistry(adapters)
    assert reg.load_dirs([REPO_VENUES_DIR]) == []
    assert reg.lint() == []
    for venue_id in ("te", "qe"):
        spec = reg.get(venue_id)
        assert spec.kind == "journal"
        assert spec.metadata_source == "econsoc"
        assert spec.fulltext_source == "econsoc"
        assert spec.quirks["ojs_code"] == venue_id
        assert spec.quirks["oai_base"] == "https://econtheory.org/ojs"
        assert isinstance(spec.quirks["volume_map"], dict) and spec.quirks["volume_map"]
    ecma = reg.get("ecma")
    assert ecma.kind == "journal"
    assert ecma.metadata_source == "crossref"  # 无 OAI 端点 → crossref by-ISSN（D-005）
    assert ecma.fulltext_source == "econsoc"  # 域名分段路由（§3.3；单值 fulltext_adapter）
    assert ecma.auth.level.value == "none"
    # 三刊 route() 可解析（metadata/fulltext adapter 均已注册）。
    for venue_id in ("ecma", "te", "qe"):
        assert reg.route(venue_id).venue.id == venue_id


def test_nber_venue_routes_to_crossref_and_nber(adapters: dict[str, SourceAdapter]) -> None:
    # Phase 5 T3：nber preprint_channel——元数据走 crossref（prefix 10.3386），全文走 nber。
    reg = VenueRegistry(adapters)
    reg.load_dirs([REPO_VENUES_DIR])
    spec = reg.get("nber")
    assert spec.kind == "preprint_channel"
    assert spec.metadata_source == "crossref"  # D-005 元数据主干分离
    assert spec.fulltext_source == "nber"
    assert spec.auth.level.value == "none"
    assert spec.identifiers["crossref_prefix"] == "10.3386"  # T1 prefix 枚举键（无 issn）
    assert "issn" not in spec.identifiers  # 工作论文系列固有无 ISSN（preprint_channel 豁免）
    assert spec.quirks["fulltext_open_after_months"] == 18  # 18 月开放窗（resolve 谓词）
    assert spec.quirks["series_prefixes"] == ["w", "t"]
    route = reg.route("nber")  # 分离路由：metadata=crossref（aggregator），fulltext=nber
    assert route.metadata_adapter.adapter_id == "crossref"
    assert route.fulltext_adapter.adapter_id == "nber"


@pytest.mark.parametrize("venue_id", sorted(_NON_ARXIV_VENUE_IDS))
def test_each_shipped_venue_is_routable(adapters: dict[str, SourceAdapter], venue_id: str) -> None:
    reg = VenueRegistry(adapters)
    reg.load_dirs([REPO_VENUES_DIR])
    route = reg.route(venue_id)
    assert route.venue.id == venue_id


# -- 1. 未知 adapter -----------------------------------------------------------


def test_unknown_metadata_adapter_reported(
    adapters: dict[str, SourceAdapter], tmp_path: Path
) -> None:
    _write(
        tmp_path / "unknown-adapter.yaml",
        "\n".join(
            [
                "id: unknown_adapter",
                "kind: conference",
                "names: {full: Unknown Adapter Venue}",
                "field: [cs_ai]",
                "metadata_source: totally_made_up_adapter",
                "fulltext_source: mock_platform",
            ]
        ),
    )
    reg = VenueRegistry(adapters)
    reg.load_dirs([tmp_path])
    issues = reg.lint()

    hits = _issues_for_field(issues, "metadata_source")
    assert len(hits) == 1
    assert hits[0].venue_id == "unknown_adapter"
    assert "totally_made_up_adapter" in hits[0].message


def test_unknown_fulltext_adapter_reported(
    adapters: dict[str, SourceAdapter], tmp_path: Path
) -> None:
    _write(
        tmp_path / "unknown-fulltext.yaml",
        "\n".join(
            [
                "id: unknown_fulltext",
                "kind: conference",
                "names: {full: Unknown Fulltext Venue}",
                "field: [cs_ai]",
                "metadata_source: mock_platform",
                "fulltext_source: nope_not_registered",
            ]
        ),
    )
    reg = VenueRegistry(adapters)
    reg.load_dirs([tmp_path])
    issues = reg.lint()

    hits = _issues_for_field(issues, "fulltext_source")
    assert len(hits) == 1
    assert hits[0].venue_id == "unknown_fulltext"
    assert "nope_not_registered" in hits[0].message


# -- 1b. 能力位不足（R2b/P1-12：Capability 全枚举此前零消费）-----------------------
#
# 缺陷形态：`Capability` 五位枚举在 `lint`/`route`/`stages`/`runner` 里一处都不被读，
# 于是"venue 指到一个不具备该阶段能力的 adapter"没有任何静态出口——只能在真实 pull
# 跑到那一阶段时以 `CapabilityNotSupported` 炸出来，违 design/02 §4「启动即校验失败
# 早报」。下面两个 fixture adapter 各缺一侧能力，验证 lint 现在会当场报出来。


class _ResolveOnlyAdapter(AdapterBase):
    """只有 RESOLVE：当 `fulltext_source` 合法（aea 就是这形态），当 `metadata_source` 不合法。"""

    adapter_id = "resolve_only_probe"
    # aggregator：让它当 `metadata_source` 时**只**触发能力位这一条，不连带触发 D-005 的
    # "分离的 metadata_source 须为 aggregator"（两条规则各测各的，断言才读得懂）。
    family: AdapterFamily = "aggregator"
    capabilities = Capability.RESOLVE
    default_rate = RatePolicy(600, source_note="lint test fixture")
    auth_requirement = AuthLevel.NONE
    domains: tuple[str, ...] = ("resolve-only.local",)


class _DiscoverOnlyAdapter(AdapterBase):
    """只有 DISCOVER（缺 ENUMERATE、缺 RESOLVE）：两侧都不合法。"""

    adapter_id = "discover_only_probe"
    family: AdapterFamily = "open_access"
    capabilities = Capability.DISCOVER
    default_rate = RatePolicy(600, source_note="lint test fixture")
    auth_requirement = AuthLevel.NONE
    domains: tuple[str, ...] = ("discover-only.local",)


def _probe_adapters(adapters: dict[str, SourceAdapter]) -> dict[str, SourceAdapter]:
    return {
        **adapters,
        "resolve_only_probe": _ResolveOnlyAdapter(),
        "discover_only_probe": _DiscoverOnlyAdapter(),
    }


def test_metadata_source_without_discover_and_enumerate_is_reported(
    adapters: dict[str, SourceAdapter], tmp_path: Path
) -> None:
    """timeline/enumerate 两阶段调的就是 `metadata_adapter` 的两个方法——缺位必须报。"""
    _write(
        tmp_path / "meta-cap-short.yaml",
        "\n".join(
            [
                "id: meta_cap_short",
                "kind: conference",
                "names: {full: Metadata Capability Short}",
                "field: [cs_ai]",
                "metadata_source: resolve_only_probe",
                "fulltext_source: mock_platform",
            ]
        ),
    )
    reg = VenueRegistry(_probe_adapters(adapters))
    reg.load_dirs([tmp_path])
    issues = reg.lint()

    hits = _issues_for_field(issues, "metadata_source")
    assert len(hits) == 1
    assert hits[0].venue_id == "meta_cap_short"
    assert "DISCOVER" in hits[0].message and "ENUMERATE" in hits[0].message
    assert "resolve_only_probe" in hits[0].message
    # fulltext 侧（mock_platform 能力全开）不该被连坐。
    assert _issues_for_field(issues, "fulltext_source") == []


def test_fulltext_source_without_resolve_is_reported(
    adapters: dict[str, SourceAdapter], tmp_path: Path
) -> None:
    """resolve 阶段调的就是 `fulltext_adapter.resolve_assets`——缺 RESOLVE 必须报。"""
    _write(
        tmp_path / "fulltext-cap-short.yaml",
        "\n".join(
            [
                "id: fulltext_cap_short",
                "kind: conference",
                "names: {full: Fulltext Capability Short}",
                "field: [cs_ai]",
                "metadata_source: crossref",  # aggregator，避开 D-005 分离规则的连带报错
                "fulltext_source: discover_only_probe",
            ]
        ),
    )
    reg = VenueRegistry(_probe_adapters(adapters))
    reg.load_dirs([tmp_path])
    issues = reg.lint()

    hits = _issues_for_field(issues, "fulltext_source")
    assert len(hits) == 1
    assert hits[0].venue_id == "fulltext_cap_short"
    assert "RESOLVE" in hits[0].message
    assert "discover_only_probe" in hits[0].message


def test_absent_metadata_source_is_judged_by_the_inherited_fulltext_adapter(
    adapters: dict[str, SourceAdapter], tmp_path: Path
) -> None:
    """`metadata_source` 缺省 = 沿用 `fulltext_source`（D-005 / `route()` 语义）。

    故此时校验的是 fulltext adapter 的枚举能力，但问题报在 `metadata_source` 字段上
    ——用户要补的正是这一行。aea/elsevier_sd 一类 RESOLVE-only 平台就是这个形态：
    它们必须显式声明一个 aggregator 做元数据主干，缺省沿用是跑不动的。
    """
    _write(
        tmp_path / "inherited-meta.yaml",
        "\n".join(
            [
                "id: inherited_meta",
                "kind: conference",
                "names: {full: Inherited Metadata Venue}",
                "field: [cs_ai]",
                "fulltext_source: resolve_only_probe",  # 无 metadata_source
            ]
        ),
    )
    reg = VenueRegistry(_probe_adapters(adapters))
    reg.load_dirs([tmp_path])
    issues = reg.lint()

    hits = _issues_for_field(issues, "metadata_source")
    assert len(hits) == 1
    assert "缺省沿用 fulltext_source" in hits[0].message
    # fulltext 侧只要 RESOLVE，该 adapter 有 → 不报（FETCH 不作门槛）。
    assert _issues_for_field(issues, "fulltext_source") == []


def test_unregistered_adapter_does_not_also_get_a_capability_complaint(
    adapters: dict[str, SourceAdapter], tmp_path: Path
) -> None:
    """未注册的 adapter 只报"未注册"一条——不叠一条"能力不足"把用户往错方向引。"""
    _write(
        tmp_path / "double-report.yaml",
        "\n".join(
            [
                "id: double_report",
                "kind: conference",
                "names: {full: Double Report Venue}",
                "field: [cs_ai]",
                "metadata_source: totally_made_up_adapter",
                "fulltext_source: also_made_up",
            ]
        ),
    )
    reg = VenueRegistry(adapters)
    reg.load_dirs([tmp_path])
    issues = reg.lint()

    assert len(_issues_for_field(issues, "metadata_source")) == 1
    assert len(_issues_for_field(issues, "fulltext_source")) == 1
    assert all("能力位" not in issue.message for issue in issues)


def test_fetch_capability_is_not_a_gate_for_browser_delegated_fulltext(
    adapters: dict[str, SourceAdapter],
) -> None:
    """aea（RESOLVE-only、全文经 browser-fetch 横切件）必须干净过 lint。

    取回阶段的分派**只看 `plan.url_strategy`**（`stages._stage_fetch` 见 RENDER_PAGE
    即转 `_fetch_via_browser`，不读能力位、不调 `adapter.fetch_asset`），所以把 FETCH
    立成 fulltext 门槛会把这类 venue 整批误判。8 个 aea 刊是这条的真实载体。
    """
    assert Capability.FETCH not in adapters["aea"].capabilities
    assert Capability.RESOLVE in adapters["aea"].capabilities

    reg = VenueRegistry(adapters)
    assert reg.load_dirs([REPO_VENUES_DIR]) == []
    aea_venues = [spec.id for spec in reg.all() if spec.fulltext_source == "aea"]
    assert len(aea_venues) == 8
    assert [issue for issue in reg.lint() if issue.venue_id in set(aea_venues)] == []


def test_capability_rules_pass_on_all_shipped_venues(adapters: dict[str, SourceAdapter]) -> None:
    """新规则跑过全部 58 个 venue：零既有错配（R2b 卡的"跑过全库"判据）。"""
    reg = VenueRegistry(adapters)
    assert reg.load_dirs([REPO_VENUES_DIR]) == []
    assert len(reg.all()) == 58
    assert [issue for issue in reg.lint() if "能力位" in issue.message] == []


# -- 2. auth 等级不足 -----------------------------------------------------------


def test_auth_level_insufficient_for_fulltext_adapter(
    adapters: dict[str, SourceAdapter], tmp_path: Path
) -> None:
    _write(
        tmp_path / "under-authed.yaml",
        "\n".join(
            [
                "id: under_authed",
                "kind: conference",
                "names: {full: Under Authed Venue}",
                "field: [cs_ai]",
                "metadata_source: crossref",
                "fulltext_source: elsevier_sd",  # 需要 institutional
                "auth: {level: none}",
            ]
        ),
    )
    reg = VenueRegistry(adapters)
    reg.load_dirs([tmp_path])
    issues = reg.lint()

    hits = _issues_for_field(issues, "auth.level")
    assert len(hits) == 1
    assert hits[0].venue_id == "under_authed"
    assert "institutional" in hits[0].message


def test_auth_level_equal_to_requirement_is_not_an_error(
    adapters: dict[str, SourceAdapter], tmp_path: Path
) -> None:
    _write(
        tmp_path / "properly-authed.yaml",
        "\n".join(
            [
                "id: properly_authed",
                "kind: conference",
                "names: {full: Properly Authed Venue}",
                "field: [cs_ai]",
                "metadata_source: crossref",
                "fulltext_source: elsevier_sd",
                "auth: {level: institutional}",
            ]
        ),
    )
    reg = VenueRegistry(adapters)
    reg.load_dirs([tmp_path])
    issues = reg.lint()
    assert _issues_for_field(issues, "auth.level") == []


# -- 3. 同目录 id 重复 -----------------------------------------------------------


def test_duplicate_id_in_same_directory_reported(
    adapters: dict[str, SourceAdapter], tmp_path: Path
) -> None:
    _write(
        tmp_path / "dup-venue.yaml",
        "\n".join(
            [
                "id: dup_venue",
                "kind: conference",
                "names: {full: First}",
                "field: [cs_ai]",
                "metadata_source: mock_platform",
                "fulltext_source: mock_platform",
            ]
        ),
    )
    # 第二个文件名刻意排到字母序更后（避免 '-' < '.' 的 ASCII 陷阱让它排到前面抢注，
    # 从而和 filename-mismatch 规则混淆断言）。
    _write(
        tmp_path / "zz-dup-venue-copy.yaml",
        "\n".join(
            [
                "id: dup_venue",
                "kind: conference",
                "names: {full: Second}",
                "field: [cs_ai]",
                "metadata_source: mock_platform",
                "fulltext_source: mock_platform",
            ]
        ),
    )
    reg = VenueRegistry(adapters)
    issues = reg.load_dirs([tmp_path])

    hits = [i for i in issues if i.venue_id == "dup_venue"]
    assert len(hits) == 1
    assert hits[0].field == "id"
    assert "dup_venue" in hits[0].message


# -- 4. journal 缺 issn ---------------------------------------------------------


def test_journal_missing_issn_reported(adapters: dict[str, SourceAdapter], tmp_path: Path) -> None:
    _write(
        tmp_path / "no-issn.yaml",
        "\n".join(
            [
                "id: no_issn",
                "kind: journal",
                "names: {full: No Issn Journal}",
                "field: [cs_ai]",
                "metadata_source: mock_platform",
                "fulltext_source: mock_platform",
            ]
        ),
    )
    reg = VenueRegistry(adapters)
    reg.load_dirs([tmp_path])
    issues = reg.lint()

    hits = _issues_for_field(issues, "identifiers.issn")
    assert len(hits) == 1
    assert hits[0].venue_id == "no_issn"


def test_conference_without_issn_is_not_an_error(
    adapters: dict[str, SourceAdapter], tmp_path: Path
) -> None:
    _write(
        tmp_path / "conf-no-issn.yaml",
        "\n".join(
            [
                "id: conf_no_issn",
                "kind: conference",
                "names: {full: Conference No Issn}",
                "field: [cs_ai]",
                "metadata_source: mock_platform",
                "fulltext_source: mock_platform",
            ]
        ),
    )
    reg = VenueRegistry(adapters)
    reg.load_dirs([tmp_path])
    issues = reg.lint()
    assert _issues_for_field(issues, "identifiers.issn") == []


# -- 5. issn 格式错 ---------------------------------------------------------------


def test_journal_bad_issn_format_reported(
    adapters: dict[str, SourceAdapter], tmp_path: Path
) -> None:
    _write(
        tmp_path / "bad-issn.yaml",
        "\n".join(
            [
                "id: bad_issn",
                "kind: journal",
                "names: {full: Bad Issn Journal}",
                "field: [cs_ai]",
                "identifiers: {issn: ['12345']}",
                "metadata_source: mock_platform",
                "fulltext_source: mock_platform",
            ]
        ),
    )
    reg = VenueRegistry(adapters)
    reg.load_dirs([tmp_path])
    issues = reg.lint()

    hits = _issues_for_field(issues, "identifiers.issn[0]")
    assert len(hits) == 1
    assert hits[0].venue_id == "bad_issn"
    assert "12345" in hits[0].message


def test_journal_issn_not_a_list_reported(
    adapters: dict[str, SourceAdapter], tmp_path: Path
) -> None:
    # identifiers.issn 是裸字符串而非列表——同一 D-015 规则的另一种畸形输入。
    _write(
        tmp_path / "issn-not-list.yaml",
        "\n".join(
            [
                "id: issn_not_list",
                "kind: journal",
                "names: {full: Issn Not List Journal}",
                "field: [cs_ai]",
                "identifiers: {issn: '0304-405X'}",
                "metadata_source: mock_platform",
                "fulltext_source: mock_platform",
            ]
        ),
    )
    reg = VenueRegistry(adapters)
    reg.load_dirs([tmp_path])
    issues = reg.lint()

    hits = _issues_for_field(issues, "identifiers.issn")
    assert len(hits) == 1
    assert hits[0].venue_id == "issn_not_list"
    assert "列表" in hits[0].message


def test_journal_issn_lowercase_x_check_digit_rejected(
    adapters: dict[str, SourceAdapter], tmp_path: Path
) -> None:
    """Closes: AC-1.6（ISSN 校验位仅接受大写 X——小写 x 不合法）。

    D-015 规则 `^\\d{4}-\\d{3}[\\dX]$` 的字符类只含大写 `X`；`0304-405x`（小写）应被
    逐字符类拒绝，定位到 `identifiers.issn[0]`。防止"看着像合法 ISSN"的小写变体漏网。
    """
    _write(
        tmp_path / "lowercase-x-issn.yaml",
        "\n".join(
            [
                "id: lowercase_x_issn",
                "kind: journal",
                "names: {full: Lowercase X Issn Journal}",
                "field: [cs_ai]",
                "identifiers: {issn: ['0304-405x']}",  # 小写 x 校验位
                "metadata_source: mock_platform",
                "fulltext_source: mock_platform",
            ]
        ),
    )
    reg = VenueRegistry(adapters)
    reg.load_dirs([tmp_path])
    issues = reg.lint()

    hits = _issues_for_field(issues, "identifiers.issn[0]")
    assert len(hits) == 1
    assert hits[0].venue_id == "lowercase_x_issn"
    assert "0304-405x" in hits[0].message


def test_journal_mixed_issn_list_locates_each_invalid_by_index(
    adapters: dict[str, SourceAdapter], tmp_path: Path
) -> None:
    """Closes: AC-1.6（同列表混合有效/无效 ISSN：逐 index 定位无效项，有效项不误报）。

    `_lint_issn` 逐项 enumerate，`field=identifiers.issn[{index}]`——校验的可定位性要求
    多个无效项各自带自己的 index，且有效项之间不"连坐"。列表
    `['0000-0000'(有效), '12345'(短), '1234-567X'(有效,大写X), '0304-405x'(小写x)]`
    → 仅 index 1、3 报错，index 0、2 干净。
    """
    _write(
        tmp_path / "mixed-issn.yaml",
        "\n".join(
            [
                "id: mixed_issn",
                "kind: journal",
                "names: {full: Mixed Issn Journal}",
                "field: [cs_ai]",
                "identifiers: {issn: ['0000-0000', '12345', '1234-567X', '0304-405x']}",
                "metadata_source: mock_platform",
                "fulltext_source: mock_platform",
            ]
        ),
    )
    reg = VenueRegistry(adapters)
    reg.load_dirs([tmp_path])
    issues = reg.lint()

    # 有效项（index 0、2）不误报
    assert _issues_for_field(issues, "identifiers.issn[0]") == []
    assert _issues_for_field(issues, "identifiers.issn[2]") == []
    # 无效项各自逐 index 定位（index 1 短一位、index 3 小写 x）
    bad1 = _issues_for_field(issues, "identifiers.issn[1]")
    bad3 = _issues_for_field(issues, "identifiers.issn[3]")
    assert len(bad1) == 1 and "12345" in bad1[0].message
    assert len(bad3) == 1 and "0304-405x" in bad3[0].message
    assert bad1[0].venue_id == "mixed_issn" and bad3[0].venue_id == "mixed_issn"
    # 全部 issn 相关问题恰好 2 条（无有效项连坐）
    assert len([i for i in issues if i.field.startswith("identifiers.issn")]) == 2


# -- 6. YAML 解析失败 --------------------------------------------------------------


def test_yaml_parse_failure_reported(adapters: dict[str, SourceAdapter], tmp_path: Path) -> None:
    _write(tmp_path / "broken-syntax.yaml", "id: broken\nfield: [cs_ai\n")
    reg = VenueRegistry(adapters)
    issues = reg.load_dirs([tmp_path])

    hits = [i for i in issues if i.file.endswith("broken-syntax.yaml")]
    assert len(hits) == 1
    assert hits[0].venue_id is None
    assert hits[0].field == "<yaml>"


def test_yaml_non_mapping_top_level_reported(
    adapters: dict[str, SourceAdapter], tmp_path: Path
) -> None:
    # 合法 YAML，但顶层是列表而非映射——无法喂给 VenueSpec(**raw)。
    _write(tmp_path / "not-a-mapping.yaml", "- a\n- b\n- c\n")
    reg = VenueRegistry(adapters)
    issues = reg.load_dirs([tmp_path])

    hits = [i for i in issues if i.file.endswith("not-a-mapping.yaml")]
    assert len(hits) == 1
    assert hits[0].venue_id is None
    assert hits[0].field == "<yaml>"


# -- 6b. 文件读取失败（非 UTF-8 编码 / 不可读） --------------------------------------
#
# 复审 Important 修复：`path.read_text(encoding="utf-8")` 此前无异常保护，非 UTF-8
# 编码（GBK/Latin-1 误存）或不可读文件（权限/悬空符号链接）会让
# UnicodeDecodeError/OSError 穿透 load_dirs()，违反"只返回 LintIssue、从不 raise"
# 的契约。两个用例分别覆盖 UnicodeDecodeError 与 OSError 两条异常路径。


def test_non_utf8_encoded_yaml_reported_not_raised(
    adapters: dict[str, SourceAdapter], tmp_path: Path
) -> None:
    # GBK 编码的中文内容按 UTF-8 解码必然失败（GBK 汉字字节不是合法 UTF-8 序列）。
    path = tmp_path / "gbk-encoded.yaml"
    path.write_bytes("id: 测试期刊\nkind: journal\n".encode("gbk"))

    reg = VenueRegistry(adapters)
    issues = reg.load_dirs([tmp_path])  # 不应 raise

    hits = [i for i in issues if i.file.endswith("gbk-encoded.yaml")]
    assert len(hits) == 1
    assert hits[0].venue_id is None
    assert hits[0].field == "<yaml>"
    assert "UnicodeDecodeError" in hits[0].message


def test_latin1_encoded_yaml_reported_not_raised(
    adapters: dict[str, SourceAdapter], tmp_path: Path
) -> None:
    path = tmp_path / "latin1-encoded.yaml"
    path.write_bytes("notes: café\nkind: journal\n".encode("latin-1"))

    reg = VenueRegistry(adapters)
    issues = reg.load_dirs([tmp_path])

    hits = [i for i in issues if i.file.endswith("latin1-encoded.yaml")]
    assert len(hits) == 1
    assert hits[0].venue_id is None
    assert hits[0].field == "<yaml>"
    assert "UnicodeDecodeError" in hits[0].message


def test_dangling_symlink_yaml_reported_not_raised(
    adapters: dict[str, SourceAdapter], tmp_path: Path
) -> None:
    # 悬空符号链接：rglob 按名字匹配会收录它，但 read_text 时目标不存在 → OSError。
    # 比 chmod 000 更跨平台稳定（不受"以 root 运行绕过权限位"影响）。
    broken_link = tmp_path / "dangling.yaml"
    broken_link.symlink_to(tmp_path / "does_not_exist_target.yaml")

    reg = VenueRegistry(adapters)
    issues = reg.load_dirs([tmp_path])  # 不应 raise

    hits = [i for i in issues if i.file.endswith("dangling.yaml")]
    assert len(hits) == 1
    assert hits[0].venue_id is None
    assert hits[0].field == "<yaml>"
    assert "OSError" in hits[0].message or "FileNotFoundError" in hits[0].message


def test_unreadable_yaml_via_monkeypatched_read_text_reported_not_raised(
    adapters: dict[str, SourceAdapter], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 权限拒绝的直接构造（chmod 000）在部分 CI/沙箱环境下不稳定（例如以 root 运行
    # 会绕过权限位）。用 monkeypatch 强制 Path.read_text 抛 PermissionError，
    # 稳定模拟"文件存在但不可读"这一支路径，与上面的悬空符号链接用例互补。
    path = tmp_path / "permission-denied.yaml"
    path.write_text("id: whatever\n", encoding="utf-8")

    original_read_text = Path.read_text

    def _raise_permission_error(self: Path, *args: object, **kwargs: object) -> str:
        if self == path:
            raise PermissionError(13, "Permission denied", str(self))
        return original_read_text(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "read_text", _raise_permission_error)

    reg = VenueRegistry(adapters)
    issues = reg.load_dirs([tmp_path])  # 不应 raise

    hits = [i for i in issues if i.file.endswith("permission-denied.yaml")]
    assert len(hits) == 1
    assert hits[0].venue_id is None
    assert hits[0].field == "<yaml>"
    assert "PermissionError" in hits[0].message


# -- 7. pydantic 结构错误（loc 路径进 field） --------------------------------------


def test_pydantic_structural_error_reported_with_loc_in_field(
    adapters: dict[str, SourceAdapter], tmp_path: Path
) -> None:
    _write(
        tmp_path / "extra-field.yaml",
        "\n".join(
            [
                "id: extra_field_venue",
                "kind: conference",
                "names: {full: Extra Field Venue}",
                "field: [cs_ai]",
                "metadata_source: mock_platform",
                "fulltext_source: mock_platform",
                "this_field_does_not_exist: 1",
            ]
        ),
    )
    reg = VenueRegistry(adapters)
    issues = reg.load_dirs([tmp_path])

    hits = _issues_for_field(issues, "this_field_does_not_exist")
    assert len(hits) == 1
    assert hits[0].venue_id == "extra_field_venue"
    assert hits[0].file.endswith("extra-field.yaml")
    assert "extra" in hits[0].message.lower() or "permitted" in hits[0].message.lower()


def test_pydantic_nested_structural_error_loc_joined_into_field(
    adapters: dict[str, SourceAdapter], tmp_path: Path
) -> None:
    _write(
        tmp_path / "bad-kind.yaml",
        "\n".join(
            [
                "id: bad_kind_venue",
                "kind: magazine",  # 不在 journal|conference|preprint_channel 枚举内
                "names: {full: Bad Kind Venue}",
                "field: [cs_ai]",
                "metadata_source: mock_platform",
                "fulltext_source: mock_platform",
            ]
        ),
    )
    reg = VenueRegistry(adapters)
    issues = reg.load_dirs([tmp_path])

    hits = _issues_for_field(issues, "kind")
    assert len(hits) == 1
    assert hits[0].venue_id == "bad_kind_venue"


# -- 8. 文件名 stem 与 id 不一致 -----------------------------------------------------


def test_filename_id_mismatch_reported(adapters: dict[str, SourceAdapter], tmp_path: Path) -> None:
    _write(
        tmp_path / "totally-different-name.yaml",
        "\n".join(
            [
                "id: proper_id",
                "kind: conference",
                "names: {full: Mismatched Venue}",
                "field: [cs_ai]",
                "metadata_source: mock_platform",
                "fulltext_source: mock_platform",
            ]
        ),
    )
    reg = VenueRegistry(adapters)
    issues = reg.load_dirs([tmp_path])

    hits = [i for i in issues if i.venue_id == "proper_id" and i.field == "id"]
    assert len(hits) == 1
    assert "totally-different-name" in hits[0].message
    assert "proper_id" in hits[0].message
    # 仍应正常注册（lint 报告问题，但不阻塞加载）。
    assert reg.get("proper_id").id == "proper_id"


def test_kebab_case_filename_matches_snake_case_id(
    adapters: dict[str, SourceAdapter], tmp_path: Path
) -> None:
    # mock-journal.yaml ↔ id: mock_journal 是合法归一（不是 mismatch）。
    _write(
        tmp_path / "mock-journal.yaml",
        "\n".join(
            [
                "id: mock_journal",
                "kind: journal",
                "names: {full: Mock Journal}",
                "field: [cs_ai]",
                "identifiers: {issn: ['0000-0000']}",
                "metadata_source: mock_platform",
                "fulltext_source: mock_platform",
            ]
        ),
    )
    reg = VenueRegistry(adapters)
    issues = reg.load_dirs([tmp_path])
    assert issues == []


# -- 9. rate_limit.requests_per_minute ≤ 0（R1b P1-3：token bucket 补充速率归零会死锁）--------


def test_venue_rate_limit_zero_rpm_reported_readable_not_raw_traceback(
    adapters: dict[str, SourceAdapter], tmp_path: Path
) -> None:
    """rpm=0 的 venue YAML：load_dirs 必须把 pydantic gt=0 校验失败包成带 venue id 与
    字段名的可读 LintIssue（同 `bad-kind.yaml`/`extra-field.yaml` 既有包装路径），
    而不是让裸 `pydantic.ValidationError` traceback 逃逸出 `load_dirs`（其"只返回问题
    列表，从不 raise"的契约，见 registry.py 模块 docstring）。"""
    _write(
        tmp_path / "zero-rpm.yaml",
        "\n".join(
            [
                "id: zero_rpm_venue",
                "kind: conference",
                "names: {full: Zero Rpm Venue}",
                "field: [cs_ai]",
                "metadata_source: mock_platform",
                "fulltext_source: mock_platform",
                "rate_limit: {requests_per_minute: 0}",
            ]
        ),
    )
    reg = VenueRegistry(adapters)
    issues = reg.load_dirs([tmp_path])  # 不应 raise

    hits = _issues_for_field(issues, "rate_limit.requests_per_minute")
    assert len(hits) == 1
    assert hits[0].venue_id == "zero_rpm_venue"
    assert hits[0].file.endswith("zero-rpm.yaml")
    # 可读：定位到具体字段名+来源文件，而非 "Traceback"/"ValidationError" 裸异常文本。
    assert "Traceback" not in hits[0].message
    assert "greater than" in hits[0].message.lower()
    # 该文件的其余部分合法——只此一条问题，不该被结构性错误一路吞掉变成 <root>/<yaml>。
    assert len([i for i in issues if i.file.endswith("zero-rpm.yaml")]) == 1
    # 未注册进 registry（校验失败视同加载失败，同结构性错误处置一致）。
    with pytest.raises(CrawlerError) as exc_info:
        reg.get("zero_rpm_venue")
    assert exc_info.value.error_class is ErrorClass.CONFIG


def test_venue_rate_limit_negative_rpm_reported(
    adapters: dict[str, SourceAdapter], tmp_path: Path
) -> None:
    _write(
        tmp_path / "negative-rpm.yaml",
        "\n".join(
            [
                "id: negative_rpm_venue",
                "kind: conference",
                "names: {full: Negative Rpm Venue}",
                "field: [cs_ai]",
                "metadata_source: mock_platform",
                "fulltext_source: mock_platform",
                "rate_limit: {requests_per_minute: -5}",
            ]
        ),
    )
    reg = VenueRegistry(adapters)
    issues = reg.load_dirs([tmp_path])

    hits = _issues_for_field(issues, "rate_limit.requests_per_minute")
    assert len(hits) == 1
    assert hits[0].venue_id == "negative_rpm_venue"
