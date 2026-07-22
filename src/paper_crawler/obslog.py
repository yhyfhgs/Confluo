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
  api_key(含下划线、短横变体)/password/secret/session_id(含短横变体)/email 的
  键值对（`Key: value`、`key=value`，以及二者的引号变体 `"Key": "value"` /
  `'key'='value'` 等——JSON 体、Python dict repr 常见），把值替换为 `***`；
  不匹配的文本原样返回。**`email`（T5 先决步骤，aggregators.md §3 B-B4）**：
  Unpaywall 把联系邮箱走 URL 查询参数 `?email=<addr>`（design/adapters/
  aggregators.md §5.5），而 `http.py` 对每一次请求无条件 `log_event(url=...)`
  经本函数脱敏——`email` 并入下方 `_SENSITIVE_KEYS`、复用既有 `_QUERY_STYLE`/
  `_HEADER_STYLE` 分支（无需新正则），使 `?email=me@example.com` 落盘前即变
  `?email=***`，不再有 unpaywall adapter 之前先补齐此项，避免明文邮箱进 jsonl。
- `**extra` 中 dict/list/tuple 结构化值会递归脱敏（任意深度）：dict 的键名
  若整体匹配敏感关键词，对应值整体替换为 `"***"`（不再逐字符扫描该值本身，
  因为像 `"session=abc123"` 这类值单看文本不含可识别的"键=值"形态，必须靠
  外层键名 `Cookie` 才能判定敏感）；其余键与 list/tuple 元素递归处理；字符串
  叶子仍过 `redact()`（捕获值自身内联的凭证文本）；非字符串标量原样保留。
"""

import json
import logging
import re
from datetime import UTC, datetime
from pathlib import Path

from paper_crawler.types import utcnow_iso

_LOGGER_NAME = "paper_crawler"

# design/05 §7 + 接口冻结件 §2.6 的脱敏键名清单（大小写不敏感）。`email`
# 2026-07-22 并入（aggregators.md §3 B-B4，T5 先决步骤）：Unpaywall `?email=`
# 查询参数须与 cookie/token 同等脱敏，见上方 docstring「email」小节。
_SENSITIVE_KEYS = (
    r"set-cookie|cookie|authorization|token|api[_-]?key|password|secret|session[_-]?id|email"
)
# extra 结构体里"键名整体等于某个敏感关键词"的判定（而非"文本中包含"）。
_SENSITIVE_KEY_NAME = re.compile(_SENSITIVE_KEYS, re.IGNORECASE)

# `Key: value` / `"Key": "value"` / `'Key': 'value'` 形态（HTTP 头、JSON 体、
# Python dict repr 均可）——键与分隔符之间、值两侧允许可选的单/双引号：
#   - 值带引号：只消费到与开引号匹配的闭合引号（用 \3 回引用同一种引号），
#     结构外壳（如末尾的 `}`）留给原文，不被吞掉。
#   - 值不带引号：取到本行末尾——值本身可能含空格（如 "Bearer tok"），没有
#     更精确的边界可用。
_HEADER_STYLE = re.compile(
    rf"\b({_SENSITIVE_KEYS})(['\"]?\s*:\s*)(?:(['\"])(.*?)\3|[^\r\n]*)",
    re.IGNORECASE,
)
# `key=value` / `"key"="value"` 形态（URL query 一类）：
#   - 值带引号：同上，只消费到闭合引号。
#   - 值不带引号：只取到下一个 `&`/空白，保留其余参数不动。
_QUERY_STYLE = re.compile(
    rf"\b({_SENSITIVE_KEYS})(['\"]?\s*=\s*)(?:(['\"])(.*?)\3|[^&\s]*)",
    re.IGNORECASE,
)


def _sub_key_value(match: re.Match[str]) -> str:
    """`_HEADER_STYLE`/`_QUERY_STYLE` 共用的替换：带引号保留引号包裹 `***`。"""
    quote = match.group(3)
    if quote:
        return f"{match.group(1)}{match.group(2)}{quote}***{quote}"
    return f"{match.group(1)}{match.group(2)}***"


def redact(text: str) -> str:
    """脱敏 cookie/token/authorization/api_key/password/secret/session_id 形态内容。"""
    if not text:
        return text
    redacted = _HEADER_STYLE.sub(_sub_key_value, text)
    redacted = _QUERY_STYLE.sub(_sub_key_value, redacted)
    return redacted


def _redact_leaf(value: object) -> object:
    """`**extra` 值的递归脱敏（Important 修复：结构化值此前绕过 redact()）。

    - `dict`：键名整体匹配敏感关键词的项，对应值整体替换为 `"***"`
      （不管值本身是否为字符串/是否含可识别形态——外层键名已足以判定敏感，
      如 `{"Cookie": "session=abc123"}` 的 value 单看文本并不匹配任何模式，
      必须靠键名 `Cookie` 才能判定）；其余键递归处理其值。
    - `list`/`tuple`：逐元素递归，任意嵌套深度。
    - `str`：过 `redact()`（捕获值自身文本内联的凭证形态）。
    - 其余标量（int/float/bool/None 等）：原样返回。
    """
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, dict):
        redacted_dict: dict[object, object] = {}
        for key, sub_value in value.items():
            if isinstance(key, str) and _SENSITIVE_KEY_NAME.fullmatch(key.strip()):
                redacted_dict[key] = "***"
            else:
                redacted_dict[key] = _redact_leaf(sub_value)
        return redacted_dict
    if isinstance(value, list):
        return [_redact_leaf(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact_leaf(item) for item in value)
    return value


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
        if _SENSITIVE_KEY_NAME.fullmatch(key.strip()):
            # extra kwarg 名本身就是敏感关键词（如 log_event(..., cookie=raw)）：
            # 整值替换，不管其类型/内容是否"看起来"含凭证形态。
            payload[key] = "***"
        else:
            payload[key] = _redact_leaf(value)

    logger.log(numeric_level, safe_msg, extra={"_event": payload})


__all__ = ["log_event", "redact", "setup_logging"]
