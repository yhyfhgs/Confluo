"""pipeline/report.py（接口冻结件 §2.7 RunReport）单测。

覆盖 design/05 §7 观测性的"运行报告"语义：成功/失败/阻塞/跳过计数、失败清单 top、
下一步提示；以及 §6 dry-run 的"将下载 N 篇 / 估 M MB"预览行。

设计决策记录（冻结件字段未显式携带 `dry_run: bool`，本实现以此为准）：
- dry-run 预览行的显示条件 = `planned_downloads > 0 or planned_bytes > 0`
  （非 dry-run 的实跑报告不应设置这两个字段，语义详见 report.py 模块 docstring）。
- 字节→MB 换算按 1024*1024（MiB，通俗标注为 MB）为基数，保留 1 位小数。
- Global Constraints §6（日志/异常文本不得含凭证形态内容）延伸到报告文本：
  `failures[].msg` 与 `notes` 渲染/落盘前一律经 `obslog.redact()` 纵深防御。
"""

import json
from pathlib import Path

from paper_crawler.pipeline.report import RunReport

# ---------------------------------------------------------------------------
# 构造 helper
# ---------------------------------------------------------------------------


def _report(**overrides: object) -> RunReport:
    defaults: dict[str, object] = {
        "command": "pull",
        "venue_id": "mock_journal",
        "started_at": "2026-07-21T08:00:00+00:00",
        "finished_at": "2026-07-21T08:01:23+00:00",
    }
    defaults.update(overrides)
    return RunReport(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# render_markdown：标题（command + venue + 时间窗）
# ---------------------------------------------------------------------------


def test_render_markdown_includes_command_venue_and_time_window() -> None:
    report = _report()
    md = report.render_markdown()

    assert "pull" in md
    assert "mock_journal" in md
    assert "2026-07-21T08:00:00+00:00" in md
    assert "2026-07-21T08:01:23+00:00" in md


def test_render_markdown_handles_none_venue_id_without_crashing() -> None:
    report = _report(venue_id=None)
    md = report.render_markdown()

    assert isinstance(md, str)
    assert "pull" in md


# ---------------------------------------------------------------------------
# render_markdown：计数表
# ---------------------------------------------------------------------------


def test_render_markdown_counts_table_shows_all_four_numbers() -> None:
    report = _report(succeeded=10, failed=2, blocked=1, skipped=3)
    md = report.render_markdown()

    assert "10" in md
    assert "2" in md
    assert "1" in md
    assert "3" in md
    assert "成功" in md
    assert "失败" in md
    assert "阻塞" in md
    assert "跳过" in md


def test_no_entitlement_row_shown_only_when_nonzero() -> None:
    """auth-framework §8.5：no_entitlement 独立计数——仅在 >0 时加一行（不污染零值报告）。"""
    zero = _report(succeeded=1).render_markdown()
    assert "无订阅权限" not in zero  # 默认 0：整行省略

    with_ne = _report(succeeded=1, no_entitlement=3).render_markdown()
    assert "| 无订阅权限 | 3 |" in with_ne


def test_no_entitlement_field_defaults_zero_and_survives_save_roundtrip(tmp_path: Path) -> None:
    """字段默认 0（既有构造点零改动）；落盘 history.jsonl 后可原样读回。"""
    assert _report().no_entitlement == 0
    _report(no_entitlement=2).save(tmp_path)
    line = (tmp_path / "history.jsonl").read_text(encoding="utf-8").strip()
    assert json.loads(line)["no_entitlement"] == 2


# ---------------------------------------------------------------------------
# render_markdown：dry-run 预览行的两形态
# ---------------------------------------------------------------------------


def test_render_markdown_shows_dry_run_line_when_planned_downloads_set() -> None:
    report = _report(planned_downloads=5, planned_bytes=5 * 1024 * 1024)
    md = report.render_markdown()

    assert "将下载 5 篇" in md
    assert "估 5.0 MB" in md


def test_render_markdown_mb_conversion_keeps_one_decimal() -> None:
    report = _report(planned_downloads=3, planned_bytes=1_572_864)  # 1.5 * 1024 * 1024
    md = report.render_markdown()

    assert "估 1.5 MB" in md


def test_render_markdown_omits_dry_run_line_when_no_planned_downloads() -> None:
    report = _report(succeeded=5)  # 实跑报告：未设置 planned_downloads/planned_bytes
    md = report.render_markdown()

    assert "将下载" not in md
    assert "MB" not in md


def test_render_markdown_shows_dry_run_line_when_only_bytes_set() -> None:
    """planned_downloads 为 0 但 planned_bytes>0（防御性边界）仍应渲染预览行。"""
    report = _report(planned_downloads=0, planned_bytes=1024 * 1024)
    md = report.render_markdown()

    assert "将下载 0 篇" in md
    assert "估 1.0 MB" in md


# ---------------------------------------------------------------------------
# render_markdown：失败清单 top 10 + 截断提示
# ---------------------------------------------------------------------------


def _failure(i: int) -> dict[str, object]:
    return {
        "task_id": f"task-{i}",
        "stage": "fetch",
        "error_class": "transient",
        "msg": f"error number {i}",
    }


def test_render_markdown_lists_all_failures_when_ten_or_fewer() -> None:
    report = _report(failed=5, failures=[_failure(i) for i in range(5)])
    md = report.render_markdown()

    for i in range(5):
        assert f"task-{i}" in md
    assert "及另" not in md


def test_render_markdown_truncates_failures_beyond_ten_with_count_note() -> None:
    failures = [_failure(i) for i in range(12)]
    report = _report(failed=12, failures=failures)
    md = report.render_markdown()

    for i in range(10):
        assert f"task-{i}" in md
    assert "task-10" not in md
    assert "task-11" not in md
    assert "及另 2 项" in md


def test_render_markdown_omits_failures_section_when_empty() -> None:
    report = _report(failed=0, failures=[])
    md = report.render_markdown()

    assert "失败清单" not in md


# ---------------------------------------------------------------------------
# render_markdown：blocked 下一步提示
# ---------------------------------------------------------------------------


def test_render_markdown_shows_next_step_hint_when_blocked() -> None:
    report = _report(blocked=2)
    md = report.render_markdown()

    assert "crawler status --blocked" in md
    assert "crawler resume" in md


def test_render_markdown_omits_next_step_hint_when_not_blocked() -> None:
    report = _report(blocked=0)
    md = report.render_markdown()

    assert "crawler status --blocked" not in md
    assert "crawler resume" not in md


# ---------------------------------------------------------------------------
# render_markdown：notes 逐条
# ---------------------------------------------------------------------------


def test_render_markdown_lists_each_note() -> None:
    report = _report(notes=["first note", "second note"])
    md = report.render_markdown()

    assert "first note" in md
    assert "second note" in md


def test_render_markdown_omits_notes_section_when_empty() -> None:
    report = _report(notes=[])
    md = report.render_markdown()

    assert "Notes" not in md


# ---------------------------------------------------------------------------
# render_markdown：Global Constraints §6 —— failures/notes 文本纵深防御脱敏
# ---------------------------------------------------------------------------


def test_render_markdown_redacts_credential_shaped_failure_msg() -> None:
    report = _report(
        failed=1,
        failures=[
            {
                "task_id": "t1",
                "stage": "fetch",
                "error_class": "auth_expired",
                "msg": "Authorization: Bearer sometoken123456",
            }
        ],
    )
    md = report.render_markdown()

    assert "sometoken123456" not in md
    assert "Authorization: ***" in md


def test_render_markdown_redacts_credential_shaped_note() -> None:
    report = _report(notes=["Cookie: session=abc123456"])
    md = report.render_markdown()

    assert "abc123456" not in md
    assert "Cookie: ***" in md


# ---------------------------------------------------------------------------
# save()：覆盖 last-run.md + 追加 history.jsonl + 目录自动创建 + 返回路径
# ---------------------------------------------------------------------------


def test_save_creates_reports_dir_when_missing(tmp_path: Path) -> None:
    reports_dir = tmp_path / "nested" / "reports"
    report = _report()

    result = report.save(reports_dir)

    assert reports_dir.is_dir()
    assert result == reports_dir / "last-run.md"
    assert result.is_file()


def test_save_returns_last_run_path_and_content_matches_render(tmp_path: Path) -> None:
    report = _report(succeeded=7)

    result = report.save(tmp_path)

    assert result == tmp_path / "last-run.md"
    assert result.read_text(encoding="utf-8") == report.render_markdown()


def test_save_overwrites_last_run_on_subsequent_calls(tmp_path: Path) -> None:
    _report(succeeded=1).save(tmp_path)
    second = _report(succeeded=99)
    second.save(tmp_path)

    content = (tmp_path / "last-run.md").read_text(encoding="utf-8")
    assert "99" in content
    # 第一次调用的内容不应叠加残留（覆盖语义）：last-run.md 只应含一份报告。
    assert content == second.render_markdown()


def test_save_appends_to_history_jsonl_across_calls(tmp_path: Path) -> None:
    _report(succeeded=1).save(tmp_path)
    _report(succeeded=2).save(tmp_path)
    _report(succeeded=3).save(tmp_path)

    lines = [
        ln for ln in (tmp_path / "history.jsonl").read_text(encoding="utf-8").splitlines() if ln
    ]
    assert len(lines) == 3
    assert [json.loads(ln)["succeeded"] for ln in lines] == [1, 2, 3]


def test_save_history_jsonl_lines_are_individually_valid_json(tmp_path: Path) -> None:
    report = _report(
        succeeded=4,
        failed=1,
        blocked=0,
        skipped=2,
        planned_downloads=5,
        planned_bytes=1024,
        failures=[_failure(0)],
        notes=["a note"],
    )
    report.save(tmp_path)

    line = (tmp_path / "history.jsonl").read_text(encoding="utf-8").strip()
    record = json.loads(line)

    assert record["command"] == "pull"
    assert record["venue_id"] == "mock_journal"
    assert record["started_at"] == "2026-07-21T08:00:00+00:00"
    assert record["finished_at"] == "2026-07-21T08:01:23+00:00"
    assert record["succeeded"] == 4
    assert record["failed"] == 1
    assert record["blocked"] == 0
    assert record["skipped"] == 2
    assert record["planned_downloads"] == 5
    assert record["planned_bytes"] == 1024
    assert record["failures"] == [_failure(0)]
    assert record["notes"] == ["a note"]


def test_save_redacts_failure_msg_in_history_jsonl(tmp_path: Path) -> None:
    report = _report(
        failed=1,
        failures=[
            {
                "task_id": "t1",
                "stage": "fetch",
                "error_class": "auth_expired",
                "msg": "Authorization: Bearer sometoken123456",
            }
        ],
    )
    report.save(tmp_path)

    line = (tmp_path / "history.jsonl").read_text(encoding="utf-8").strip()
    record = json.loads(line)

    assert record["failures"][0]["msg"] == "Authorization: ***"
    assert "sometoken123456" not in line


def test_save_redacts_notes_in_history_jsonl(tmp_path: Path) -> None:
    report = _report(notes=["Cookie: session=abc123456"])
    report.save(tmp_path)

    line = (tmp_path / "history.jsonl").read_text(encoding="utf-8").strip()
    record = json.loads(line)

    assert record["notes"] == ["Cookie: ***"]
    assert "abc123456" not in line
