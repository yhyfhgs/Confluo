"""`pipeline/cooldown.py` 单测（E-2；检查单 #7 / D-030 裁决点④）。

本模块是纯 Path/JSON I/O（零 DB、零 registry、零网络）——`runner.py`（写入侧）与
`crawler cooldown` CLI（只读/清理侧）的公用读写层，见 `pipeline/cooldown.py`
模块 docstring。所有用例走 `tmp_path`（不触真实 config-home，Global Constraints
§8/D-032 红线）。

覆盖：路径布局、**路径穿越防护（独立审查 P0 修复）**、键解析（E-1/D-030 裁决③
域级优先+旧键兼容的纯函数化）、写读回环、损坏/缺失文件的容错与诊断
（`scan_problems`，独立审查 P1 修复）、过期清理、目录级列举（`status` 消费）与
清空（`clear` 消费）。
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from paper_crawler.errors import CrawlerError, ErrorClass
from paper_crawler.pipeline import cooldown

# ---------------------------------------------------------------------------
# 常量 + 路径布局
# ---------------------------------------------------------------------------


def test_challenge_cooldown_is_24_hours() -> None:
    """§8.4 平台冷却窗口 = 24h（原 `runner._CHALLENGE_COOLDOWN`，值不变）。"""
    assert cooldown.CHALLENGE_COOLDOWN == timedelta(hours=24)


def test_cooldown_dir_layout(tmp_path: Path) -> None:
    assert cooldown.cooldown_dir(tmp_path) == tmp_path / "state" / "cooldown"


def test_cooldown_path_layout(tmp_path: Path) -> None:
    assert cooldown.cooldown_path(tmp_path, "mock.local") == (
        tmp_path / "state" / "cooldown" / "mock.local.json"
    )


# ---------------------------------------------------------------------------
# 路径穿越防护（独立审查 P0 修复）：`cooldown_path` 白名单校验 + is_relative_to 兜底。
# 三条对抗向量——`../` 注入、绝对路径、含 `/` 键——外加穿透 write/read_until/drop
# 的覆盖，以及一条端到端"确实不会删到 home 外"的证据测试。
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "key",
    [
        "../../../victim/important",  # `../` 注入
        "/etc/passwd",  # 绝对路径
        "sub/dir",  # 含 `/`（无 `..` 也拒绝——单键单文件承诺）
        "..\\..\\victim",  # 反斜杠（Windows 形态，防御纵深）
        "..",  # 字面 `..`
        ".",  # 字面 `.`
        "",  # 空串
    ],
)
def test_cooldown_path_rejects_traversal_keys(tmp_path: Path, key: str) -> None:
    with pytest.raises(CrawlerError) as exc_info:
        cooldown.cooldown_path(tmp_path, key)
    assert exc_info.value.error_class is ErrorClass.CONFIG


@pytest.mark.parametrize(
    "key",
    ["pubs.aeaweb.org", "mock_platform", "mock.local", "a", "elsevier_sd", "oup-silverchair"],
)
def test_cooldown_path_accepts_realistic_keys(tmp_path: Path, key: str) -> None:
    """白名单不能误伤真实域名/adapter_id 形态（否则合法冷却写入会被拒）。"""
    path = cooldown.cooldown_path(tmp_path, key)
    assert path == tmp_path / "state" / "cooldown" / f"{key}.json"


def test_write_rejects_traversal_key(tmp_path: Path) -> None:
    with pytest.raises(CrawlerError):
        cooldown.write(tmp_path, "../../../victim/important", datetime.now(UTC))


def test_read_until_rejects_traversal_key(tmp_path: Path) -> None:
    with pytest.raises(CrawlerError):
        cooldown.read_until(tmp_path, "../../../victim/important")


def test_drop_rejects_traversal_key(tmp_path: Path) -> None:
    with pytest.raises(CrawlerError):
        cooldown.drop(tmp_path, "../../../victim/important")


def test_clear_rejects_traversal_key_and_does_not_touch_victim_file(tmp_path: Path) -> None:
    """端到端证据：曾实测的漏洞（`clear "../../../victim/important"` 真删 home 外文件）已堵死。"""
    home = tmp_path / "home"
    home.mkdir()
    victim = tmp_path / "victim" / "important.json"
    victim.parent.mkdir(parents=True)
    victim.write_text('{"sentinel": "do-not-delete"}', encoding="utf-8")

    with pytest.raises(CrawlerError) as exc_info:
        cooldown.clear(home, "../../../victim/important")
    assert exc_info.value.error_class is ErrorClass.CONFIG

    assert victim.is_file()  # home 外文件毫发无损
    assert victim.read_text(encoding="utf-8") == '{"sentinel": "do-not-delete"}'


# ---------------------------------------------------------------------------
# `host_of`：asset URL → host（域级键来源）
# ---------------------------------------------------------------------------


def test_host_of_extracts_hostname_from_url() -> None:
    assert cooldown.host_of("https://pubs.mock.local/pdf/10.9999/x") == "pubs.mock.local"


def test_host_of_none_for_empty_string() -> None:
    assert cooldown.host_of("") is None


def test_host_of_none_for_none() -> None:
    assert cooldown.host_of(None) is None


def test_host_of_none_for_relative_path_without_host() -> None:
    assert cooldown.host_of("/relative/no-host.pdf") is None


# ---------------------------------------------------------------------------
# `resolve_keys`：域级新键在前、adapter_id 旧键在后（去重）——E-1/D-030 裁决③
# ---------------------------------------------------------------------------


def test_resolve_keys_domain_first_then_adapter_id() -> None:
    assert cooldown.resolve_keys("pubs.mock.local", "mock_platform") == (
        "pubs.mock.local",
        "mock_platform",
    )


def test_resolve_keys_host_only_when_adapter_id_missing() -> None:
    assert cooldown.resolve_keys("pubs.mock.local", None) == ("pubs.mock.local",)


def test_resolve_keys_adapter_id_only_when_host_missing() -> None:
    assert cooldown.resolve_keys(None, "mock_platform") == ("mock_platform",)


def test_resolve_keys_empty_when_both_missing() -> None:
    assert cooldown.resolve_keys(None, None) == ()


def test_resolve_keys_dedupes_when_host_equals_adapter_id() -> None:
    """退化去重：host 恰与 adapter_id 同名时只留一个键（同 runner 既有测试锁定的同构行为）。"""
    assert cooldown.resolve_keys("mock_platform", "mock_platform") == ("mock_platform",)


# ---------------------------------------------------------------------------
# `write` / `read_until`：落盘回环 + 容错（不存在/损坏 → None，不抛）
# ---------------------------------------------------------------------------


def test_write_then_read_until_roundtrip(tmp_path: Path) -> None:
    until = datetime(2026, 7, 28, 12, 0, 0, tzinfo=UTC)
    cooldown.write(tmp_path, "mock.local", until)

    assert cooldown.read_until(tmp_path, "mock.local") == until


def test_write_creates_parent_dirs(tmp_path: Path) -> None:
    until = datetime.now(UTC) + timedelta(hours=24)
    cooldown.write(tmp_path, "fresh_key", until)

    path = cooldown.cooldown_path(tmp_path, "fresh_key")
    assert path.is_file()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["until"] == until.isoformat()


def test_read_until_missing_file_returns_none(tmp_path: Path) -> None:
    assert cooldown.read_until(tmp_path, "no_such_key") is None


def test_read_until_corrupt_json_returns_none(tmp_path: Path) -> None:
    path = cooldown.cooldown_path(tmp_path, "broken")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("not json{{{", encoding="utf-8")

    assert cooldown.read_until(tmp_path, "broken") is None


def test_read_until_missing_key_in_payload_returns_none(tmp_path: Path) -> None:
    path = cooldown.cooldown_path(tmp_path, "no_until")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"unexpected": "field"}), encoding="utf-8")

    assert cooldown.read_until(tmp_path, "no_until") is None


def test_read_until_invalid_timestamp_returns_none(tmp_path: Path) -> None:
    path = cooldown.cooldown_path(tmp_path, "bad_ts")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"until": "not-a-timestamp"}), encoding="utf-8")

    assert cooldown.read_until(tmp_path, "bad_ts") is None


# ---------------------------------------------------------------------------
# `drop`：幂等删除（不存在也不抛）
# ---------------------------------------------------------------------------


def test_drop_removes_existing_file(tmp_path: Path) -> None:
    cooldown.write(tmp_path, "mock.local", datetime.now(UTC))
    assert cooldown.cooldown_path(tmp_path, "mock.local").is_file()

    cooldown.drop(tmp_path, "mock.local")

    assert not cooldown.cooldown_path(tmp_path, "mock.local").exists()


def test_drop_missing_file_is_noop(tmp_path: Path) -> None:
    cooldown.drop(tmp_path, "no_such_key")  # 不抛

    assert not cooldown.cooldown_path(tmp_path, "no_such_key").exists()
    assert not cooldown.cooldown_dir(tmp_path).exists()  # 未曾创建过目录，本调用不应凭空建它


def test_drop_is_idempotent(tmp_path: Path) -> None:
    cooldown.write(tmp_path, "mock.local", datetime.now(UTC))
    path = cooldown.cooldown_path(tmp_path, "mock.local")
    assert path.is_file()

    cooldown.drop(tmp_path, "mock.local")
    assert not path.exists()  # 首次调用：文件确实被删

    cooldown.drop(tmp_path, "mock.local")  # 第二次仍不抛
    assert not path.exists()  # 状态保持不变（幂等——不是"第二次又删了什么"）


# ---------------------------------------------------------------------------
# `list_entries`：目录级列举（`crawler cooldown status` 消费）
# ---------------------------------------------------------------------------


def test_list_entries_empty_when_dir_missing(tmp_path: Path) -> None:
    assert cooldown.list_entries(tmp_path, now=datetime.now(UTC)) == []


def test_list_entries_empty_when_dir_exists_but_empty(tmp_path: Path) -> None:
    cooldown.cooldown_dir(tmp_path).mkdir(parents=True)
    assert cooldown.list_entries(tmp_path, now=datetime.now(UTC)) == []


def test_list_entries_reports_active_and_expired(tmp_path: Path) -> None:
    now = datetime.now(UTC)
    active_until = now + timedelta(hours=12)
    expired_until = now - timedelta(hours=1)
    cooldown.write(tmp_path, "still_active", active_until)
    cooldown.write(tmp_path, "already_expired", expired_until)

    entries = {e.key: e for e in cooldown.list_entries(tmp_path, now=now)}

    assert entries["still_active"].until == active_until
    assert entries["still_active"].active is True
    assert entries["already_expired"].until == expired_until
    assert entries["already_expired"].active is False


def test_list_entries_sorted_by_key(tmp_path: Path) -> None:
    now = datetime.now(UTC)
    cooldown.write(tmp_path, "zzz_last", now + timedelta(hours=1))
    cooldown.write(tmp_path, "aaa_first", now + timedelta(hours=1))

    keys = [e.key for e in cooldown.list_entries(tmp_path, now=now)]

    assert keys == ["aaa_first", "zzz_last"]


def test_list_entries_lists_both_domain_and_legacy_adapter_id_keys(tmp_path: Path) -> None:
    """E-1"两形态键"如实并列（无迁移脚本，本卡不做任何键形态区分/迁移，仅如实列出）。"""
    now = datetime.now(UTC)
    cooldown.write(tmp_path, "pubs.mock.local", now + timedelta(hours=1))  # 域级新键
    cooldown.write(tmp_path, "mock_platform", now + timedelta(hours=1))  # adapter_id 旧键

    keys = {e.key for e in cooldown.list_entries(tmp_path, now=now)}

    assert keys == {"pubs.mock.local", "mock_platform"}


def test_list_entries_skips_corrupt_files_without_raising(tmp_path: Path) -> None:
    now = datetime.now(UTC)
    cooldown.write(tmp_path, "good_key", now + timedelta(hours=1))
    corrupt = cooldown.cooldown_path(tmp_path, "corrupt_key")
    corrupt.write_text("{{{not json", encoding="utf-8")

    entries = cooldown.list_entries(tmp_path, now=now)

    assert [e.key for e in entries] == ["good_key"]


# ---------------------------------------------------------------------------
# `scan_problems`：损坏文件诊断（`crawler cooldown status` 消费；独立审查 P1 修复
# ——`list_entries` 对损坏文件的静默跳过不能是全部诊断信息的唯一来源）。
# ---------------------------------------------------------------------------


def test_scan_problems_empty_when_dir_missing(tmp_path: Path) -> None:
    assert cooldown.scan_problems(tmp_path) == []


def test_scan_problems_empty_when_all_files_valid(tmp_path: Path) -> None:
    cooldown.write(tmp_path, "good_key", datetime.now(UTC))
    assert cooldown.scan_problems(tmp_path) == []


def test_scan_problems_reports_corrupt_json_with_filename_and_reason(tmp_path: Path) -> None:
    corrupt = cooldown.cooldown_path(tmp_path, "corrupt_key")
    corrupt.parent.mkdir(parents=True, exist_ok=True)
    corrupt.write_text("{{{not json", encoding="utf-8")

    problems = cooldown.scan_problems(tmp_path)

    assert len(problems) == 1
    filename, reason = problems[0]
    assert filename == "corrupt_key.json"
    assert reason  # 非空、可读的原因字符串


def test_scan_problems_reports_missing_until_field(tmp_path: Path) -> None:
    path = cooldown.cooldown_path(tmp_path, "no_until")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"unexpected": "field"}), encoding="utf-8")

    problems = cooldown.scan_problems(tmp_path)

    assert problems == [("no_until.json", problems[0][1])]  # 恰一条
    assert "until" in problems[0][1] or "Key" in problems[0][1]  # KeyError('until') 的呈现


def test_scan_problems_reports_multiple_corrupt_files_and_ignores_valid_ones(
    tmp_path: Path,
) -> None:
    """独立审查 P1 复现场景：目录只含 2 个损坏文件——两条都要被点名，一条都不许漏。"""
    cooldown.write(tmp_path, "good_key", datetime.now(UTC))
    cooldown.cooldown_path(tmp_path, "broken_one").write_text("not json", encoding="utf-8")
    cooldown.cooldown_path(tmp_path, "broken_two").write_text("{}", encoding="utf-8")

    problems = cooldown.scan_problems(tmp_path)

    assert {name for name, _ in problems} == {"broken_one.json", "broken_two.json"}
    assert all(reason for _, reason in problems)  # 每条原因都非空


# ---------------------------------------------------------------------------
# `clear`：按键删除 / 全量清空（`crawler cooldown clear` 消费）
# ---------------------------------------------------------------------------


def test_clear_specific_key_removes_only_that_file(tmp_path: Path) -> None:
    cooldown.write(tmp_path, "keep_me", datetime.now(UTC))
    cooldown.write(tmp_path, "drop_me", datetime.now(UTC))

    removed = cooldown.clear(tmp_path, "drop_me")

    assert removed == 1
    assert cooldown.cooldown_path(tmp_path, "keep_me").is_file()
    assert not cooldown.cooldown_path(tmp_path, "drop_me").exists()


def test_clear_specific_missing_key_returns_zero(tmp_path: Path) -> None:
    assert cooldown.clear(tmp_path, "no_such_key") == 0


def test_clear_all_removes_every_file_and_returns_count(tmp_path: Path) -> None:
    cooldown.write(tmp_path, "a", datetime.now(UTC))
    cooldown.write(tmp_path, "b", datetime.now(UTC))
    cooldown.write(tmp_path, "c", datetime.now(UTC))

    removed = cooldown.clear(tmp_path, None)

    assert removed == 3
    assert cooldown.list_entries(tmp_path, now=datetime.now(UTC)) == []


def test_clear_all_on_missing_dir_returns_zero(tmp_path: Path) -> None:
    assert cooldown.clear(tmp_path, None) == 0


def test_clear_all_on_empty_dir_returns_zero(tmp_path: Path) -> None:
    cooldown.cooldown_dir(tmp_path).mkdir(parents=True)
    assert cooldown.clear(tmp_path, None) == 0
