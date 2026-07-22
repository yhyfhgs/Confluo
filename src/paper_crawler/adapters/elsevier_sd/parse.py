"""Elsevier Article / Entitlement API 响应解析（design/adapters/elsevier-sd.md §3/§5 逐行）。

零网络、零 obslog（沿 crossref/s2/unpaywall parse.py 先例）。只用标准库 `json`。

本模块解析两类**结构化 JSON 封套**（B-M3：elsevier API 返 JSON error 封套，非挑战页
HTML；elsevier-sd.md §2 R0 [LIVE] 印证）：

① **entitlement 端点**（`GET /content/article/entitlement/doi/{doi}`）响应——
   `entitlement-response.document-entitlement.entitled`(bool)（`@status` 伴随）。
   **⚠[DOCS] 字段名/类型待 T7b 真实 key 核验**（BLOCKER-1：R0 keyless 429 拦在 auth 层前，
   entitlement 语义无法活验；本解析器依 Elsevier Article Entitlement API 官方文档形态实现，
   `entitled` 字段名/布尔类型 = 待核验假设，elsevier-sd.md §2 "⚠ 待核验"）。`document-entitlement`
   容错为 dict 或 list（多文档查询返 list；本 adapter 单 DOI 查询预期单对象，防御性两容）。
   **entitled 字段在所有条目中均缺失 → 抛 PARSE**（响亮暴露"字段名假设失效"，供 T7b 修正——
   而非静默判 no_entitlement 污染路由）。

② **error 封套**（任意错误状态 body）——`{"error-response": {"error-code": "...",
   "error-message": "..."}}`（R0 [LIVE] 2026-07-23 keyless 429 实测封套）。`parse_error_envelope`
   **纯观测、绝不 raise**（畸形/非 JSON → 空 `ErrorEnvelope`）：仅供 detail 记录 error-code
   诊断，**不作行为分流依据**（B-M2：任意 429 一律保守当日熔断，不靠 `X-ELS-Status`/error-code
   真值区分 keyless-vs-quota——认证态真值不可活验，§5）。
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from paper_crawler.errors import CrawlerError, ErrorClass


@dataclass(frozen=True)
class EntitlementDecision:
    """entitlement 端点判定结果：是否有权 + 观测到的 `@status`（诊断用）。"""

    entitled: bool
    status: str | None


@dataclass(frozen=True)
class ErrorEnvelope:
    """error 封套的 `error-code`/`error-message`（纯观测；缺失/畸形 → None）。"""

    code: str | None
    message: str | None


def parse_entitlement(data: bytes, *, doi: str) -> EntitlementDecision:
    """解析 entitlement 端点响应 → `EntitlementDecision`（§3.1）。

    结构：`entitlement-response.document-entitlement[.entitled]`（⚠[DOCS] 字段名待 T7b 核验，
    见模块 docstring）。`document-entitlement` 容错 dict|list；任一条目 `entitled` 真值即判有权
    （防御多文档场景）。**所有条目均无 `entitled` 字段 → PARSE**（字段名假设失效，响亮暴露）。
    """
    doc = _load_json(data)
    if not isinstance(doc, dict):
        raise CrawlerError(
            ErrorClass.PARSE,
            f"elsevier entitlement response top level must be a JSON object, "
            f"got {type(doc).__name__} (doi={doi})",
        )
    response = doc.get("entitlement-response")
    if not isinstance(response, dict):
        raise CrawlerError(
            ErrorClass.PARSE,
            f"elsevier entitlement response missing 'entitlement-response' object (doi={doi})",
        )
    entries = _as_entry_list(response.get("document-entitlement"))
    if not entries:
        raise CrawlerError(
            ErrorClass.PARSE,
            f"elsevier entitlement response missing 'document-entitlement' (doi={doi})",
        )

    entitled = False
    status: str | None = None
    saw_entitled_field = False
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if status is None:
            status = _clean_str(_first(entry, "@status", "status"))
        decision = _coerce_bool(_first(entry, "entitled", "@entitled"))
        if decision is not None:
            saw_entitled_field = True
            entitled = entitled or decision

    if not saw_entitled_field:
        raise CrawlerError(
            ErrorClass.PARSE,
            f"elsevier entitlement: no 'entitled' field in document-entitlement (doi={doi}; "
            "⚠ field-name assumption unverified — elsevier-sd.md §2, capture real envelope at T7b)",
        )
    return EntitlementDecision(entitled=entitled, status=status)


def parse_error_envelope(data: bytes) -> ErrorEnvelope:
    """解析 error 封套的 `error-code`/`error-message`（**纯观测，绝不 raise**；§5）。

    畸形/非 JSON/结构不符 → 空 `ErrorEnvelope(None, None)`（用于 detail 诊断记录，非行为分流
    依据，B-M2）。兼容 `error-response`（常见）与 `service-error`（部分 4xx）两种封套外壳。
    """
    try:
        doc = json.loads(data)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return ErrorEnvelope(code=None, message=None)
    if not isinstance(doc, dict):
        return ErrorEnvelope(code=None, message=None)
    shell = doc.get("error-response")
    if not isinstance(shell, dict):
        shell = doc.get("service-error")
    if not isinstance(shell, dict):
        return ErrorEnvelope(code=None, message=None)
    return ErrorEnvelope(
        code=_clean_str(shell.get("error-code")),
        message=_clean_str(shell.get("error-message")),
    )


# --- 模块级纯函数 ------------------------------------------------------------------------------


def _load_json(data: bytes) -> object:
    try:
        return json.loads(data)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise CrawlerError(ErrorClass.PARSE, f"malformed elsevier json: {exc}") from exc


def _as_entry_list(node: object) -> list[object]:
    """`document-entitlement` 容错为条目列表：list 原样、dict 包一层、其余空。"""
    if isinstance(node, list):
        return node
    if isinstance(node, dict):
        return [node]
    return []


def _first(entry: dict[str, object], *keys: str) -> object:
    """按序取首个存在的键值（容忍 `entitled`/`@entitled` 等命名差异）；均缺 → None。"""
    for key in keys:
        if key in entry:
            return entry[key]
    return None


def _coerce_bool(raw: object) -> bool | None:
    """把 `entitled` 归一为布尔（容忍 JSON bool 与字符串 "true"/"false"/"1"/"0"）；不可判 None。"""
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        low = raw.strip().lower()
        if low in ("true", "1", "yes"):
            return True
        if low in ("false", "0", "no"):
            return False
    return None


def _clean_str(raw: object) -> str | None:
    if not isinstance(raw, str):
        return None
    collapsed = " ".join(raw.split())
    return collapsed or None


__all__ = [
    "EntitlementDecision",
    "ErrorEnvelope",
    "parse_entitlement",
    "parse_error_envelope",
]
