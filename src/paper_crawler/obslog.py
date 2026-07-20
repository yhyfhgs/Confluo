"""结构化观测日志（接口冻结件 §2.6；design/05 §7 观测性）。

命名为 `obslog.py` 而非 `logging.py`——本模块内部需要 `import logging`（标准库），
若模块本身叫 `logging.py`，包内 `import logging` 会自我遮蔽而不是导入标准库。

行为：
- `setup_logging`：为 `log_dir/crawler-YYYYMMDD.jsonl`（UTC 日期）挂一个"全量写入"
  的文件 handler（不受 console_level 过滤，机读全量）；再挂一个按 console_level
  过滤的人读控制台 handler（`[LEVEL] venue/stage msg`，人读摘要）。重复调用会先
  关闭并清空旧 handler 再重建，不会重复输出。
- `log_event`：拼装一行结构化记录并落盘；jsonl 行键集合 = {ts, level, msg,
  task_id, venue, stage, domain, url, error_class, ...extra}，值为 None 的键省略。
  `url` 字段按接口冻结件强制先 `redact()`。此外——Global Constraints §6
  （"日志/异常文本不得含凭证形态内容"）与 NFR-8/AC-0.4 的义务覆盖日志文本整体，
  不止 url 一个字段——本实现额外对 `msg` 与字符串类型的 `**extra` 值也过
  `redact()`，作为纵深防御（不改变函数签名，只加固内部行为）。
- `redact`：大小写不敏感识别 cookie/set-cookie/authorization/token/
  api_key(含下划线、短横变体)/password/secret/session_id(含短横变体) 的键值对
  （`Key: value` 与 `key=value` 两种写法），把值替换为 `***`；不匹配的文本原样
  返回。
"""

import json
import logging
import re
from datetime import UTC, datetime
from pathlib import Path

from paper_crawler.types import utcnow_iso

_LOGGER_NAME = "paper_crawler"

# design/05 §7 + 接口冻结件 §2.6 的脱敏键名清单（大小写不敏感）。
_SENSITIVE_KEYS = (
    r"set-cookie|cookie|authorization|token|api[_-]?key|password|secret|session[_-]?id"
)
# `Key: value` 形态（HTTP 头一类）——值取到本行末尾（值本身可含空格，如 "Bearer tok"）。
_HEADER_STYLE = re.compile(rf"\b({_SENSITIVE_KEYS})(\s*:\s*)[^\r\n]*", re.IGNORECASE)
# `key=value` 形态（URL query 一类）——值只取到下一个 `&`/空白，保留其余参数不动。
_QUERY_STYLE = re.compile(rf"\b({_SENSITIVE_KEYS})(=)[^&\s]*", re.IGNORECASE)


def redact(text: str) -> str:
    """脱敏 cookie/token/authorization/api_key/password/secret/session_id 形态内容。"""
    if not text:
        return text
    redacted = _HEADER_STYLE.sub(lambda m: f"{m.group(1)}{m.group(2)}***", text)
    redacted = _QUERY_STYLE.sub(lambda m: f"{m.group(1)}{m.group(2)}***", redacted)
    return redacted


class _JsonlFormatter(logging.Formatter):
    """把 `log_event` 拼好的 dict（挂在 `record._event`）序列化为一行 JSON。"""

    def format(self, record: logging.LogRecord) -> str:
        payload_obj: object = getattr(record, "_event", {})
        payload: dict[str, object] = payload_obj if isinstance(payload_obj, dict) else {}
        return json.dumps(payload, ensure_ascii=False)


class _ConsoleFormatter(logging.Formatter):
    """人读单行：`[LEVEL] venue/stage msg`（venue/stage 任一缺省则对应省略）。"""

    def format(self, record: logging.LogRecord) -> str:
        payload_obj: object = getattr(record, "_event", {})
        payload: dict[str, object] = payload_obj if isinstance(payload_obj, dict) else {}
        level = str(payload.get("level", record.levelname))
        msg = str(payload.get("msg", record.getMessage()))
        scope_parts = (payload.get("venue"), payload.get("stage"))
        scope = "/".join(str(part) for part in scope_parts if part)
        if scope:
            return f"[{level}] {scope} {msg}"
        return f"[{level}] {msg}"


def setup_logging(log_dir: Path, *, console_level: str = "INFO") -> None:
    """挂载 jsonl 文件 handler（全量）+ 控制台 handler（按 level 过滤）。

    重复调用是安全的：会先关闭并清空旧 handler 再重建，不会重复输出
    （`logger.handlers` 调用后恒为 2 个）。
    """
    log_dir.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(_LOGGER_NAME)
    for handler in list(logger.handlers):
        handler.close()
        logger.removeHandler(handler)
    logger.propagate = False
    logger.setLevel(logging.DEBUG)

    date_str = datetime.now(UTC).strftime("%Y%m%d")
    jsonl_path = log_dir / f"crawler-{date_str}.jsonl"
    file_handler = logging.FileHandler(jsonl_path, mode="a", encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)  # 文件机读全量：不受 console_level 影响
    file_handler.setFormatter(_JsonlFormatter())
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(getattr(logging, console_level.upper(), logging.INFO))
    console_handler.setFormatter(_ConsoleFormatter())
    logger.addHandler(console_handler)


def log_event(
    level: str,
    msg: str,
    *,
    task_id: str | None = None,
    venue: str | None = None,
    stage: str | None = None,
    domain: str | None = None,
    url: str | None = None,
    error_class: str | None = None,
    **extra: object,
) -> None:
    """写一条结构化日志：jsonl 全量落盘 + 控制台按 level 摘要。

    jsonl 行键集合：{ts, level, msg, task_id, venue, stage, domain, url,
    error_class, ...extra}；值为 None 的键省略。
    """
    logger = logging.getLogger(_LOGGER_NAME)
    level_name = level.upper()
    numeric_level = getattr(logging, level_name, logging.INFO)

    safe_msg = redact(msg)
    payload: dict[str, object] = {"ts": utcnow_iso(), "level": level_name, "msg": safe_msg}

    named_fields: dict[str, object | None] = {
        "task_id": task_id,
        "venue": venue,
        "stage": stage,
        "domain": domain,
        "url": redact(url) if url is not None else None,
        "error_class": error_class,
    }
    for key, value in named_fields.items():
        if value is not None:
            payload[key] = value

    for key, value in extra.items():
        if value is None:
            continue
        payload[key] = redact(value) if isinstance(value, str) else value

    logger.log(numeric_level, safe_msg, extra={"_event": payload})


__all__ = ["log_event", "redact", "setup_logging"]
