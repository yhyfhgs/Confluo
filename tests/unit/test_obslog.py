"""obslog.py（接口冻结件 §2.6）单测：jsonl 结构化日志、控制台摘要、redact() 脱敏族、AC-0.4 扫描。"""

import json
import logging
import re
from pathlib import Path

import pytest

from paper_crawler.obslog import log_event, redact, setup_logging


@pytest.fixture(autouse=True)
def _reset_paper_crawler_logger() -> None:
    """每个测试后关闭并清空全局 logger 的 handler，避免跨测试文件句柄泄漏。"""
    yield
    logger = logging.getLogger("paper_crawler")
    for handler in list(logger.handlers):
        handler.close()
        logger.removeHandler(handler)


def _jsonl_path(log_dir: Path) -> Path:
    files = list(log_dir.glob("crawler-*.jsonl"))
    assert len(files) == 1, f"expected exactly one jsonl file, found {files}"
    return files[0]


# ---------------------------------------------------------------------------
# setup_logging / log_event：文件落盘、追加、去重 handler
# ---------------------------------------------------------------------------


def test_setup_logging_creates_dated_jsonl_file(tmp_path: Path) -> None:
    setup_logging(tmp_path)
    log_event("INFO", "hello")

    files = list(tmp_path.glob("crawler-*.jsonl"))
    assert len(files) == 1
    assert re.fullmatch(r"crawler-\d{8}\.jsonl", files[0].name)


def test_log_event_appends_multiple_lines(tmp_path: Path) -> None:
    setup_logging(tmp_path)
    log_event("INFO", "one")
    log_event("INFO", "two")
    log_event("INFO", "three")

    lines = [ln for ln in _jsonl_path(tmp_path).read_text(encoding="utf-8").splitlines() if ln]
    assert len(lines) == 3


def test_repeated_setup_logging_does_not_duplicate_handlers(tmp_path: Path) -> None:
    setup_logging(tmp_path)
    setup_logging(tmp_path)
    setup_logging(tmp_path)

    logger = logging.getLogger("paper_crawler")
    assert len(logger.handlers) == 2


def test_repeated_setup_logging_preserves_prior_appended_content(tmp_path: Path) -> None:
    setup_logging(tmp_path)
    log_event("INFO", "before re-setup")
    setup_logging(tmp_path)
    log_event("INFO", "after re-setup")

    lines = [ln for ln in _jsonl_path(tmp_path).read_text(encoding="utf-8").splitlines() if ln]
    assert len(lines) == 2


# ---------------------------------------------------------------------------
# log_event：jsonl 行结构（键集合、None 省略、json.loads 合法）
# ---------------------------------------------------------------------------


def test_log_event_line_is_valid_json_with_correct_keys(tmp_path: Path) -> None:
    setup_logging(tmp_path)
    log_event(
        "INFO",
        "fetched",
        task_id="t1",
        venue="jfe",
        stage="fetch",
        domain="mock.local",
        url="https://mock.local/x",
        error_class=None,
        extra_field="value",
    )

    line = _jsonl_path(tmp_path).read_text(encoding="utf-8").strip()
    record = json.loads(line)

    assert record["level"] == "INFO"
    assert record["msg"] == "fetched"
    assert record["task_id"] == "t1"
    assert record["venue"] == "jfe"
    assert record["stage"] == "fetch"
    assert record["domain"] == "mock.local"
    assert record["url"] == "https://mock.local/x"
    assert record["extra_field"] == "value"
    assert "ts" in record
    assert "error_class" not in record  # 传 None → 键省略


def test_log_event_omits_none_valued_optional_keys(tmp_path: Path) -> None:
    setup_logging(tmp_path)
    log_event("INFO", "minimal")

    record = json.loads(_jsonl_path(tmp_path).read_text(encoding="utf-8").strip())

    assert set(record) == {"ts", "level", "msg"}


def test_log_event_omits_none_valued_extra_keys(tmp_path: Path) -> None:
    setup_logging(tmp_path)
    log_event("INFO", "minimal", bytes_written=None, http_status=200)

    record = json.loads(_jsonl_path(tmp_path).read_text(encoding="utf-8").strip())

    assert "bytes_written" not in record
    assert record["http_status"] == 200


def test_log_event_redacts_url_before_writing(tmp_path: Path) -> None:
    setup_logging(tmp_path)
    log_event("INFO", "fetch", url="https://mock.local/x?api_key=deadbeef123456")

    record = json.loads(_jsonl_path(tmp_path).read_text(encoding="utf-8").strip())

    assert record["url"] == "https://mock.local/x?api_key=***"
    assert "deadbeef123456" not in record["url"]


# ---------------------------------------------------------------------------
# 控制台：level 过滤 + `[LEVEL] venue/stage msg` 格式；文件不受 console_level 影响
# ---------------------------------------------------------------------------


def test_console_only_shows_events_at_or_above_console_level(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    setup_logging(tmp_path, console_level="WARNING")
    log_event("INFO", "quiet event")
    log_event("ERROR", "loud event", venue="jfe", stage="fetch")

    captured = capsys.readouterr()
    assert "quiet event" not in captured.err
    assert "loud event" in captured.err


def test_console_format_is_level_scope_msg(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    setup_logging(tmp_path, console_level="INFO")
    log_event("INFO", "did the thing", venue="jfe", stage="fetch")

    captured = capsys.readouterr()
    assert "[INFO] jfe/fetch did the thing" in captured.err


def test_console_format_without_venue_or_stage_omits_scope(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    setup_logging(tmp_path, console_level="INFO")
    log_event("INFO", "no scope here")

    captured = capsys.readouterr()
    assert "[INFO] no scope here" in captured.err


def test_file_receives_all_levels_regardless_of_console_level(tmp_path: Path) -> None:
    setup_logging(tmp_path, console_level="ERROR")
    log_event("DEBUG", "debug event")
    log_event("INFO", "info event")

    content = _jsonl_path(tmp_path).read_text(encoding="utf-8")
    assert "debug event" in content
    assert "info event" in content


# ---------------------------------------------------------------------------
# redact()：cookie/token/authorization/api_key/password/secret/session_id 族
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Cookie: session=abc123", "Cookie: ***"),
        ("cookie: session=abc123", "cookie: ***"),
        ("COOKIE: session=abc123", "COOKIE: ***"),
        ("Set-Cookie: id=xyz; Path=/", "Set-Cookie: ***"),
        ("Authorization: Bearer tok", "Authorization: ***"),
        ("authorization: Bearer tok", "authorization: ***"),
        ("Token: abcdef123456", "Token: ***"),
        ("Password: hunter2", "Password: ***"),
        ("Secret: shh", "Secret: ***"),
        ("Session-Id: xyz789", "Session-Id: ***"),
        ("Session_Id: xyz789", "Session_Id: ***"),
    ],
)
def test_redact_header_style_key_value(raw: str, expected: str) -> None:
    assert redact(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("?api_key=xyz&x=1", "?api_key=***&x=1"),
        ("?api-key=xyz&x=1", "?api-key=***&x=1"),
        ("?apikey=xyz&x=1", "?apikey=***&x=1"),
        ("?token=abc123&y=2", "?token=***&y=2"),
        ("?session_id=abc123&z=3", "?session_id=***&z=3"),
        ("a=1&password=topsecret&b=2", "a=1&password=***&b=2"),
    ],
)
def test_redact_url_query_style_param(raw: str, expected: str) -> None:
    assert redact(raw) == expected


def test_redact_leaves_normal_text_untouched() -> None:
    text = "fetched 10 papers for venue jfe volume 160 issue 2"
    assert redact(text) == text


def test_redact_empty_string_returns_empty() -> None:
    assert redact("") == ""


# ---------------------------------------------------------------------------
# AC-0.4：日志与报告中无未脱敏的 cookie/token（正则扫描断言）
# ---------------------------------------------------------------------------


def test_ac_0_4_no_unredacted_credentials_survive_in_jsonl(tmp_path: Path) -> None:
    """Closes: AC-0.4 —— 写出的 jsonl 全文不得残留 (session|token|key)=[A-Za-z0-9]{6,} 形态。"""
    setup_logging(tmp_path, console_level="CRITICAL")  # 静音控制台，避免测试输出噪音

    log_event(
        "INFO",
        "fetched asset",
        task_id="01ARZ3NDEKTSV4RRFFQ69G5FAV",
        venue="mock_journal",
        stage="fetch",
        domain="mock.local",
        url="https://mock.local/pdf/x?api_key=deadbeef123456&session_id=abcdef987654",
    )
    log_event(
        "ERROR",
        "auth failed; Authorization: Bearer sometoken123456; Cookie: session_id=zzzzzz999999",
        venue="mock_journal",
        stage="fetch",
        error_class="auth_expired",
        raw_header="Set-Cookie: token=qwerty123456; Password: hunter22222",
    )

    full_text = _jsonl_path(tmp_path).read_text(encoding="utf-8")

    leak_pattern = re.compile(r"(session|token|key)=[A-Za-z0-9]{6,}")
    assert leak_pattern.search(full_text) is None

    lines = [ln for ln in full_text.splitlines() if ln.strip()]
    assert len(lines) == 2
    for line in lines:
        json.loads(line)  # 每行仍是合法 JSON
