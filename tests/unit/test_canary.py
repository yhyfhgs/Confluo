"""canary.py 单测（T3）：`run_canary` 的三态分类（healthy/unhealthy/skip）、
`canary_exit_code` 判据、`render_canary_markdown` 的渲染细节（含 redact/转义）、
`--record` 落盘的纯函数层（`canary_record_path`/`render_canary_record`）。

CLI 接线层（`crawler canary` 对 mock 的健康/SKIP 两态、`--adapter` 过滤/未知 id、
`--record` 实际写文件）见 `tests/integration/test_cli_canary.py`；这里只测纯函数层，
不经 typer、不碰文件系统。
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from paper_crawler.canary import (
    CanaryRow,
    canary_exit_code,
    canary_record_path,
    render_canary_markdown,
    render_canary_record,
    run_canary,
)
from paper_crawler.types import HealthReport


class _FakeAdapter:
    """最小假 adapter：`run_canary` 只依赖 `healthcheck()`，不需要满足完整协议。"""

    def __init__(
        self,
        *,
        healthy: bool | None = None,
        detail: str = "",
        exc: BaseException | None = None,
    ) -> None:
        self._healthy = healthy
        self._detail = detail
        self._exc = exc

    def healthcheck(self, session: object = None) -> HealthReport:
        if self._exc is not None:
            raise self._exc
        assert self._healthy is not None
        return HealthReport(healthy=self._healthy, detail=self._detail)


# --- run_canary：三态分类 -----------------------------------------------------


def test_healthy_report_yields_healthy_row() -> None:
    rows = run_canary({"a": _FakeAdapter(healthy=True, detail="ok")})
    assert rows == [CanaryRow("a", "healthy", "ok")]


def test_unhealthy_report_yields_unhealthy_row() -> None:
    rows = run_canary({"a": _FakeAdapter(healthy=False, detail="site down")})
    assert rows == [CanaryRow("a", "unhealthy", "site down")]


def test_not_implemented_error_yields_skip_row() -> None:
    rows = run_canary({"a": _FakeAdapter(exc=NotImplementedError("stub until Phase 3"))})
    assert rows == [CanaryRow("a", "skip", "stub until Phase 3")]


def test_not_implemented_error_without_message_defaults_detail_text() -> None:
    rows = run_canary({"a": _FakeAdapter(exc=NotImplementedError())})
    assert rows == [CanaryRow("a", "skip", "未实现")]


def test_arbitrary_exception_yields_unhealthy_row_with_type_and_message() -> None:
    rows = run_canary({"a": _FakeAdapter(exc=RuntimeError("boom"))})
    assert rows == [CanaryRow("a", "unhealthy", "RuntimeError: boom")]


def test_one_adapter_raising_does_not_stop_others_from_being_checked() -> None:
    """探测健壮性：一个 adapter 异常不能拖垮整次 canary（模块 docstring 的核心承诺）。"""
    rows = run_canary(
        {
            "broken": _FakeAdapter(exc=RuntimeError("boom")),
            "fine": _FakeAdapter(healthy=True),
        }
    )
    assert {row.adapter_id: row.status for row in rows} == {
        "broken": "unhealthy",
        "fine": "healthy",
    }


def test_rows_sorted_by_adapter_id_regardless_of_input_order() -> None:
    rows = run_canary(
        {
            "zeta": _FakeAdapter(healthy=True),
            "alpha": _FakeAdapter(healthy=True),
            "mid": _FakeAdapter(healthy=True),
        }
    )
    assert [row.adapter_id for row in rows] == ["alpha", "mid", "zeta"]


def test_empty_adapter_map_yields_no_rows() -> None:
    assert run_canary({}) == []


def test_detail_is_redacted_before_being_stored_on_the_row() -> None:
    """AC-0 红线纵深防御：healthcheck 透传的 detail 文本先经 redact() 再落进 CanaryRow。"""
    rows = run_canary({"a": _FakeAdapter(healthy=False, detail="token=abc123 still failing")})
    assert "abc123" not in rows[0].detail
    assert "token=***" in rows[0].detail


def test_exception_message_is_redacted_too() -> None:
    rows = run_canary({"a": _FakeAdapter(exc=RuntimeError('auth failed, cookie="s3cr3t"'))})
    assert "s3cr3t" not in rows[0].detail
    assert "***" in rows[0].detail


# --- canary_exit_code ---------------------------------------------------------


def test_canary_exit_code_empty_is_zero() -> None:
    assert canary_exit_code([]) == 0


def test_canary_exit_code_all_healthy_or_skip_is_zero() -> None:
    rows = [CanaryRow("a", "healthy", ""), CanaryRow("b", "skip", "")]
    assert canary_exit_code(rows) == 0


def test_canary_exit_code_any_unhealthy_is_one() -> None:
    rows = [CanaryRow("a", "healthy", ""), CanaryRow("b", "unhealthy", "")]
    assert canary_exit_code(rows) == 1


# --- render_canary_markdown ---------------------------------------------------


def test_render_canary_markdown_header_and_rows() -> None:
    rows = [CanaryRow("mock_platform", "healthy", "ok"), CanaryRow("crossref", "skip", "stub")]
    markdown = render_canary_markdown(rows)
    lines = markdown.splitlines()
    assert lines[0] == "| adapter | healthy | detail |"
    assert lines[1] == "| --- | --- | --- |"
    assert "| mock_platform | healthy | ok |" in markdown
    assert "| crossref | SKIP | stub |" in markdown


def test_render_canary_markdown_unhealthy_label_is_lowercase() -> None:
    markdown = render_canary_markdown([CanaryRow("a", "unhealthy", "down")])
    assert "| a | unhealthy | down |" in markdown


def test_render_canary_markdown_escapes_pipe_in_detail() -> None:
    markdown = render_canary_markdown([CanaryRow("a", "unhealthy", "left|right")])
    assert "left\\|right" in markdown


def test_render_canary_markdown_empty_detail_renders_dash() -> None:
    markdown = render_canary_markdown([CanaryRow("a", "healthy", "")])
    assert "| a | healthy | - |" in markdown


def test_render_canary_markdown_no_rows_still_has_header() -> None:
    assert render_canary_markdown([]) == "| adapter | healthy | detail |\n| --- | --- | --- |"


# --- canary_record_path --------------------------------------------------------


def test_canary_record_path_uses_given_day() -> None:
    path = canary_record_path(date(2026, 7, 22))
    assert path == Path("docs/testing/records/canary/2026-07-22-canary.md")


def test_canary_record_path_defaults_to_today() -> None:
    path = canary_record_path()
    assert path.name == f"{date.today().isoformat()}-canary.md"


def test_canary_record_path_is_relative_not_absolute() -> None:
    # 相对当前工作目录解析（预期仓库根目录下调用）；不做仓库根探测/绝对化。
    assert not canary_record_path(date(2026, 7, 22)).is_absolute()


# --- render_canary_record -------------------------------------------------------


def test_render_canary_record_has_dated_title() -> None:
    content = render_canary_record([], day=date(2026, 7, 22))
    assert content.startswith("# Canary 健康矩阵 — 2026-07-22")


def test_render_canary_record_defaults_day_to_today() -> None:
    content = render_canary_record([])
    assert date.today().isoformat() in content


def test_render_canary_record_embeds_same_table_as_terminal_output() -> None:
    """落盘内容与终端输出同源：`render_canary_markdown` 的完整产出原样出现在记录里。"""
    rows = [CanaryRow("mock_platform", "healthy", "ok"), CanaryRow("crossref", "skip", "stub")]
    content = render_canary_record(rows, day=date(2026, 7, 22))
    assert render_canary_markdown(rows) in content


def test_render_canary_record_notes_auto_generated_do_not_hand_edit() -> None:
    content = render_canary_record([], day=date(2026, 1, 1))
    assert "自动生成" in content


def test_render_canary_record_ends_with_single_trailing_newline() -> None:
    content = render_canary_record([CanaryRow("a", "healthy", "ok")], day=date(2026, 7, 22))
    assert content.endswith("\n")
    assert not content.endswith("\n\n")
