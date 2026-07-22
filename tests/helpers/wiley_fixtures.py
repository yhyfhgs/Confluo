"""wiley fixture 加载器（`tests/fixtures/wiley/`）。

**四件套均为合成/[DOCS] fixture**（design/adapters/wiley.md §6；无 token 未取过真实响应）：
- `01_tdm_article_success.pdf`：TDM 成功响应的截断脱敏 PDF 样例（`%PDF-` 魔数 + application/pdf）
  ——⚠ [DOCS] 端点已 [LIVE 2026-07-23] 活验但无 token 未取真实体，待 token 到位重录。
- `02_tdm_401_token_invalid.http` / `03_tdm_403_no_entitlement.http` /
  `04_tdm_429_rate_limited.http`：401/403/429 三态封套——⚠ [DOCS] 依官方 TDM 文档形态合成，
  各文件头注出处等级与核验计划（token 到位后按 tests/manual/wiley_runbook.md 重录真实响应）。

``.http`` 格式（沿 arxiv/openreview/unpaywall fixtures 约定）：``#`` 开头行为注释；
``HTTP-STATUS: <int>`` 声明状态码；其余 ``Key: Value`` 为响应头；**首个空行**后为原始 body。
"""

from __future__ import annotations

from pathlib import Path

_RAW = Path(__file__).resolve().parents[1] / "fixtures" / "wiley"


def fixture_bytes(name: str) -> bytes:
    """读取 `wiley/<name>` 的原始字节。"""
    return (_RAW / name).read_bytes()


def http_fixture(name: str) -> tuple[int, dict[str, str], bytes]:
    """解析 ``.http`` 快照 → ``(status, headers, body)``（见模块 docstring 的格式说明）。"""
    raw = (_RAW / name).read_bytes()
    head, sep, body = raw.partition(b"\n\n")
    if not sep:  # 无空行分隔——整体视为 body，200 无头
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


__all__ = ["fixture_bytes", "http_fixture"]
