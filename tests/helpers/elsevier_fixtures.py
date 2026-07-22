"""elsevier_sd fixture 加载器（`tests/fixtures/elsevier_sd/`）。

**JSON 封套集**（B-M3：elsevier API 返结构化 JSON error/封套，非挑战页 HTML——不设 HTML
四类）。全部 `.http` 格式（`#` 头注释出处等级 + 核验计划，逐文件；见各 fixture 文件头）。

**出处分级表**（elsevier-sd.md §7 / 任务契约"每个合成 fixture 标注出处等级"）：

| fixture | 出处等级 | 说明 |
|---|---|---|
| `03_keyless_429_rate_limit_exceeded.http` | **[LIVE 2026-07-23]** | R0 §0-E2 keyless 429 |
| `01_entitlement_true.http` | ⚠[DOCS] | Entitlement 端点文档形态；`entitled` 字段待 T7b 核验 |
| `02_entitlement_false.http` | ⚠[DOCS] | 同上；无权分支（AC-4.3） |
| `04_quota_429_exceeded.http`| ⚠[DOCS] | 认证态配额耗尽 429（X-ELS-Status，不可活验；B-M2 兜底） |
| `05_article_fulltext_truncated_xml.http` | ⚠[DOCS] | Article Retrieval 全文 XML 截断样本 |

计：**[LIVE] ×1 + ⚠[DOCS] ×4**。BLOCKER-1（Elsevier key 缺失）下 keyless 层以外全部合成——
真值待 T7b 真实 key 到位后活验、UPDATE_GOLDEN 转正（elsevier-sd.md §2 "⚠ 待核验"）。

`.http` 格式同 s2/crossref/unpaywall/openalex fixtures 约定：`# ` 头注释 + `HTTP-STATUS:`/头行
+ 空行 + body（见 `http_fixture`）。
"""

from __future__ import annotations

from pathlib import Path

_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "elsevier_sd"


def fixture_bytes(name: str) -> bytes:
    """读取 `elsevier_sd/<name>` 的原始字节（含 `.http` 头，罕用——多数场景走 `http_fixture`）。"""
    return (_DIR / name).read_bytes()


def http_fixture(name: str) -> tuple[int, dict[str, str], bytes]:
    """解析 ``.http`` 快照 → ``(status, headers, body)``（`#` 头注释与空行跳过）。"""
    raw = (_DIR / name).read_bytes()
    head, sep, body = raw.partition(b"\n\n")
    if not sep:
        return 200, {}, raw
    status = 200
    headers: dict[str, str] = {}
    for line in head.decode("utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        key, _, value = stripped.partition(":")
        key, value = key.strip(), value.strip()
        if key.upper() == "HTTP-STATUS":
            status = int(value)
        else:
            headers[key] = value
    return status, headers, body


def body_bytes(name: str) -> bytes:
    """便捷取 ``.http`` fixture 的 body（丢弃 status/headers）——parse 单测常用。"""
    return http_fixture(name)[2]


__all__ = ["body_bytes", "fixture_bytes", "http_fixture"]
