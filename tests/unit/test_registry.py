"""registry.py（§2.8）单测：加载/目录覆盖语义/get/route/all。

lint() 规则细节（七类非法 spec）见 test_venue_yaml_lint.py；本文件聚焦
VenueRegistry 的加载与查询机制本身。
"""

from pathlib import Path

import pytest

from paper_crawler.adapter import AdapterBase, AdapterFamily, SourceAdapter, load_adapters
from paper_crawler.errors import CrawlerError, ErrorClass
from paper_crawler.registry import Route, VenueRegistry
from paper_crawler.types import AuthLevel, Capability, RatePolicy, VenueSpec

REPO_VENUES_DIR = Path(__file__).resolve().parents[2] / "venues"


class _NoDomainAdapter(AdapterBase):
    """domains 为空元组的畸形 adapter（防御性测试用；正常 adapter 恒有主域）。"""

    adapter_id = "no_domain"
    family: AdapterFamily = "open_access"
    capabilities = Capability.RESOLVE | Capability.FETCH
    default_rate = RatePolicy(600, source_note="test")
    auth_requirement = AuthLevel.NONE
    domains: tuple[str, ...] = ()


@pytest.fixture
def adapters() -> dict[str, SourceAdapter]:
    return load_adapters()


@pytest.fixture
def registry(adapters: dict[str, SourceAdapter]) -> VenueRegistry:
    reg = VenueRegistry(adapters)
    reg.load_dirs([REPO_VENUES_DIR])
    return reg


def _write_minimal_venue(path: Path, venue_id: str, full_name: str) -> None:
    path.write_text(
        "\n".join(
            [
                f"id: {venue_id}",
                "kind: conference",
                f"names: {{full: {full_name}}}",
                "field: [cs_ai]",
                "metadata_source: mock_platform",
                "fulltext_source: mock_platform",
            ]
        ),
        encoding="utf-8",
    )


# -- load_dirs: 基础加载 ------------------------------------------------------


def test_load_dirs_returns_empty_list_for_shipped_venues(
    adapters: dict[str, SourceAdapter],
) -> None:
    reg = VenueRegistry(adapters)
    issues = reg.load_dirs([REPO_VENUES_DIR])
    assert issues == []


def test_load_dirs_finds_shipped_venues(registry: VenueRegistry) -> None:
    ids = {spec.id for spec in registry.all()}
    # 基础三件 + arxiv preprint_channel 白名单（catalog §1，31 个）；全集校验见
    # test_venue_yaml_lint.test_shipped_venues_pass_lint_cleanly。
    assert {"mock_journal", "jfe", "iclr"} <= ids
    assert len([i for i in ids if i.startswith("arxiv_")]) == 31


def test_load_dirs_skips_nonexistent_directory(
    adapters: dict[str, SourceAdapter], tmp_path: Path
) -> None:
    reg = VenueRegistry(adapters)
    issues = reg.load_dirs([tmp_path / "does_not_exist"])
    assert issues == []
    assert reg.all() == []


def test_load_dirs_resets_state_on_repeated_call(
    adapters: dict[str, SourceAdapter], tmp_path: Path
) -> None:
    dir1 = tmp_path / "d1"
    dir1.mkdir()
    _write_minimal_venue(dir1 / "one.yaml", "one", "One")

    reg = VenueRegistry(adapters)
    reg.load_dirs([dir1])
    assert {s.id for s in reg.all()} == {"one"}

    dir2 = tmp_path / "d2"
    dir2.mkdir()
    _write_minimal_venue(dir2 / "two.yaml", "two", "Two")
    reg.load_dirs([dir2])  # 第二次调用应重置，而非累加
    assert {s.id for s in reg.all()} == {"two"}


# -- 目录覆盖语义（design/02 §4：用户目录覆盖项目目录） -------------------------


def test_cross_directory_same_id_overrides_without_lint_issue(
    adapters: dict[str, SourceAdapter], tmp_path: Path
) -> None:
    project_dir = tmp_path / "project_venues"
    user_dir = tmp_path / "user_venues"
    project_dir.mkdir()
    user_dir.mkdir()
    _write_minimal_venue(project_dir / "shared-venue.yaml", "shared_venue", "From Project Dir")
    _write_minimal_venue(user_dir / "shared-venue.yaml", "shared_venue", "From User Dir")

    reg = VenueRegistry(adapters)
    issues = reg.load_dirs([project_dir, user_dir])

    assert issues == []  # 跨目录同 id = 覆盖合法，不是错误
    spec = reg.get("shared_venue")
    assert spec.names.full == "From User Dir"  # 后目录覆盖前目录


def test_directory_order_determines_winner(
    adapters: dict[str, SourceAdapter], tmp_path: Path
) -> None:
    dir_a = tmp_path / "a"
    dir_b = tmp_path / "b"
    dir_a.mkdir()
    dir_b.mkdir()
    _write_minimal_venue(dir_a / "shared-venue.yaml", "shared_venue", "First")
    _write_minimal_venue(dir_b / "shared-venue.yaml", "shared_venue", "Second")

    # 反过来传参：dir_b 在前、dir_a 在后 → dir_a（"First"）应该赢。
    reg = VenueRegistry(adapters)
    reg.load_dirs([dir_b, dir_a])
    assert reg.get("shared_venue").names.full == "First"


def test_duplicate_id_within_same_directory_is_error_and_first_wins(
    adapters: dict[str, SourceAdapter], tmp_path: Path
) -> None:
    venues_dir = tmp_path / "venues"
    venues_dir.mkdir()
    # 文件名归一后与 id 一致，避免和 filename-mismatch 规则混淆断言；第二个文件名
    # 刻意排到字母序更后（避免 '-' < '.' 的 ASCII 陷阱让它排到前面抢注）。
    _write_minimal_venue(venues_dir / "dup-venue.yaml", "dup_venue", "Winner")
    _write_minimal_venue(venues_dir / "zz-dup-venue-copy.yaml", "dup_venue", "Loser")

    reg = VenueRegistry(adapters)
    issues = reg.load_dirs([venues_dir])

    dup_issues = [i for i in issues if i.venue_id == "dup_venue"]
    assert len(dup_issues) == 1
    assert dup_issues[0].field == "id"
    assert "dup_venue" in dup_issues[0].message
    assert reg.get("dup_venue").names.full == "Winner"  # 排序后先出现者保留


# -- get() --------------------------------------------------------------------


def test_get_returns_spec_by_id(registry: VenueRegistry) -> None:
    spec = registry.get("mock_journal")
    assert isinstance(spec, VenueSpec)
    assert spec.id == "mock_journal"
    assert spec.kind == "journal"


def test_get_unknown_id_raises_config_error(registry: VenueRegistry) -> None:
    with pytest.raises(CrawlerError) as exc_info:
        registry.get("does_not_exist")
    assert exc_info.value.error_class is ErrorClass.CONFIG


# -- route() --------------------------------------------------------------------


def test_route_mock_journal_binds_same_adapter_both_sides(
    registry: VenueRegistry, adapters: dict[str, SourceAdapter]
) -> None:
    route = registry.route("mock_journal")
    assert isinstance(route, Route)
    assert route.venue.id == "mock_journal"
    assert route.metadata_adapter is adapters["mock_platform"]
    assert route.fulltext_adapter is adapters["mock_platform"]
    assert route.auth_profile is None  # provider_hint 未设置
    assert route.rate_overrides == {}  # venue 未声明 rate_limit


def test_route_jfe_binds_crossref_and_elsevier_with_rate_override(
    registry: VenueRegistry, adapters: dict[str, SourceAdapter]
) -> None:
    route = registry.route("jfe")
    assert route.metadata_adapter is adapters["crossref"]
    assert route.fulltext_adapter is adapters["elsevier_sd"]
    assert route.auth_profile == "elsevier"
    assert route.rate_overrides == {"www.sciencedirect.com": 10.0}


def test_route_iclr_binds_openreview_both_sides(
    registry: VenueRegistry, adapters: dict[str, SourceAdapter]
) -> None:
    route = registry.route("iclr")
    assert route.metadata_adapter is adapters["openreview"]
    assert route.fulltext_adapter is adapters["openreview"]
    assert route.auth_profile == "openreview"  # provider_hint（§3 token 通道勘误）
    assert route.rate_overrides == {}  # iclr 未声明 rate_limit


def test_route_unknown_venue_raises_config_error(registry: VenueRegistry) -> None:
    with pytest.raises(CrawlerError) as exc_info:
        registry.route("does_not_exist")
    assert exc_info.value.error_class is ErrorClass.CONFIG


def test_route_unknown_adapter_reference_raises_config_error(
    adapters: dict[str, SourceAdapter], tmp_path: Path
) -> None:
    venues_dir = tmp_path / "venues"
    venues_dir.mkdir()
    (venues_dir / "broken.yaml").write_text(
        "\n".join(
            [
                "id: broken",
                "kind: conference",
                "names: {full: Broken Venue}",
                "field: [cs_ai]",
                "metadata_source: nonexistent_adapter",
                "fulltext_source: mock_platform",
            ]
        ),
        encoding="utf-8",
    )
    reg = VenueRegistry(adapters)
    reg.load_dirs([venues_dir])
    with pytest.raises(CrawlerError) as exc_info:
        reg.route("broken")
    assert exc_info.value.error_class is ErrorClass.CONFIG


def _write_no_domain_venue(venues_dir: Path, *, rate_limit_rpm: float | None = None) -> None:
    lines = [
        "id: nodomain_venue",
        "kind: conference",
        "names: {full: No Domain Venue}",
        "field: [cs_ai]",
        "metadata_source: mock_platform",
        "fulltext_source: no_domain",
    ]
    if rate_limit_rpm is not None:
        lines.append(f"rate_limit: {{requests_per_minute: {rate_limit_rpm}}}")
    (venues_dir / "nodomain-venue.yaml").write_text("\n".join(lines), encoding="utf-8")


def test_route_empty_fulltext_domains_with_rate_limit_raises_config_not_indexerror(
    adapters: dict[str, SourceAdapter], tmp_path: Path
) -> None:
    """rate_limit 需要 fulltext_adapter.domains[0] 做键；domains 为空元组时必须以
    CrawlerError(CONFIG) 早失败（周边 route() 风格），而非裸 IndexError 穿透。"""
    adapters = {**adapters, "no_domain": _NoDomainAdapter()}
    venues_dir = tmp_path / "venues"
    venues_dir.mkdir()
    _write_no_domain_venue(venues_dir, rate_limit_rpm=30.0)
    reg = VenueRegistry(adapters)
    reg.load_dirs([venues_dir])
    with pytest.raises(CrawlerError) as exc_info:
        reg.route("nodomain_venue")
    assert exc_info.value.error_class is ErrorClass.CONFIG


def test_route_empty_fulltext_domains_without_rate_limit_is_clean(
    adapters: dict[str, SourceAdapter], tmp_path: Path
) -> None:
    """无 rate_limit 时 route() 不触碰 domains[0]，空 domains 不影响路由（overrides 空）。"""
    adapters = {**adapters, "no_domain": _NoDomainAdapter()}
    venues_dir = tmp_path / "venues"
    venues_dir.mkdir()
    _write_no_domain_venue(venues_dir, rate_limit_rpm=None)
    reg = VenueRegistry(adapters)
    reg.load_dirs([venues_dir])
    route = reg.route("nodomain_venue")
    assert route.rate_overrides == {}


def test_route_unknown_fulltext_adapter_reference_raises_config_error(
    adapters: dict[str, SourceAdapter], tmp_path: Path
) -> None:
    # metadata_source 合法但 fulltext_source 未注册 —— 单独覆盖 route() 的第二个校验分支。
    venues_dir = tmp_path / "venues"
    venues_dir.mkdir()
    (venues_dir / "broken2.yaml").write_text(
        "\n".join(
            [
                "id: broken2",
                "kind: conference",
                "names: {full: Broken Venue 2}",
                "field: [cs_ai]",
                "metadata_source: mock_platform",
                "fulltext_source: nonexistent_adapter",
            ]
        ),
        encoding="utf-8",
    )
    reg = VenueRegistry(adapters)
    reg.load_dirs([venues_dir])
    with pytest.raises(CrawlerError) as exc_info:
        reg.route("broken2")
    assert exc_info.value.error_class is ErrorClass.CONFIG


# -- all() --------------------------------------------------------------------


def test_all_returns_sorted_by_id(registry: VenueRegistry) -> None:
    ids = [spec.id for spec in registry.all()]
    # 确定性输出 = 全按 id 升序（不钉死具体集合——arxiv 白名单会增补；集合校验见
    # test_load_dirs_finds_shipped_venues）。
    assert ids == sorted(ids)
    assert {"iclr", "jfe", "mock_journal"} <= set(ids)


# -- lint(): 干净通过（细节规则见 test_venue_yaml_lint.py） ----------------------


def test_lint_passes_for_shipped_venues(registry: VenueRegistry) -> None:
    assert registry.lint() == []
