"""VenueSpec YAML 校验规则单测（design/02 §2.2 校验段；AC-1.6）。

七类非法各至少一例，断言 LintIssue.field 与 message 内容：
未知 adapter / auth 等级不足 / 同目录 id 重复 / journal 缺 issn /
issn 格式错 / YAML 解析失败 / pydantic 结构错误（含文件名-id 不一致）。

结构性问题（文件读取失败、YAML 解析失败、pydantic 校验失败、同目录 id 冲突、
文件名-id 不一致）由 `load_dirs()` 直接返回；语义问题（未知 adapter、auth 不兼容、
issn 规则）需要 `lint()`（在已加载的 venue 上叠加校验）。三份仓库自带 YAML 必须
全过 lint。
"""

from pathlib import Path

import pytest

from paper_crawler.adapter import SourceAdapter, load_adapters
from paper_crawler.registry import LintIssue, VenueRegistry

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
