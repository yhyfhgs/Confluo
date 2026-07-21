"""neurips_proceedings fixture 加载器（`tests/fixtures/neurips_proceedings/`）。

十一件套 + D-019 锚点表均为**合成/部分真实 fixture**（design/adapters/
neurips-proceedings.md §6）——每个文件头以注释标注哪些字段值是逐字复用
docs/research/site-survey/neurips-proceedings.md 的 [LIVE] 实测（hash/citation
meta 等），哪些是本次实现标注合成的占位内容。本次实现未做真实网络录制，按 D-014
约定合成路径处理（同 pmlr/arxiv/openreview fixture 先例）。

``.http`` 格式（错误状态码件，响应头随 body 落盘——沿用 arxiv/openreview fixtures
约定）：以 ``#`` 开头的行为注释；``HTTP-STATUS: <int>`` 声明状态码；其余
``Key: Value`` 为响应头；**首个空行**后为原始 body。
"""

from __future__ import annotations

from pathlib import Path

_RAW = Path(__file__).resolve().parents[1] / "fixtures" / "neurips_proceedings"


def fixture_bytes(name: str) -> bytes:
    """读取 `neurips_proceedings/<name>` 的原始字节。"""
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
