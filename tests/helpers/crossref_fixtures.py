"""crossref fixture 加载器（`tests/fixtures/crossref/`）。

**全部合成 fixture**（Phase 3 T3，无真实网络录制）——JSON 体结构依 Crossref REST
`/journals/{issn}/works` [DOCS] 与 aggregators.md §5.1，**关键数值 [LIVE]-grounded**
（QJE ISSN `0033-5533`、`total_2024=46`、`total_all=6655`，见 §7 锚点表）；样本条目的
DOI/title/author 为构造值。JSON 件顶层带 `_synthetic` 键、`.http` 件以 `#` 注释标注。

``.http`` 格式（错误状态码件，响应头随 body 落盘——沿 arxiv/openreview fixtures 约定）：
以 ``#`` 开头行为注释；``HTTP-STATUS: <int>`` 声明状态码；其余 ``Key: Value`` 为响应
头；**首个空行**后为原始 body。
"""

from __future__ import annotations

from pathlib import Path

_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "crossref"


def fixture_bytes(name: str) -> bytes:
    """读取 `crossref/<name>` 的原始字节。"""
    return (_DIR / name).read_bytes()


def http_fixture(name: str) -> tuple[int, dict[str, str], bytes]:
    """解析 ``.http`` 快照 → ``(status, headers, body)``（见模块 docstring 的格式说明）。"""
    raw = (_DIR / name).read_bytes()
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
