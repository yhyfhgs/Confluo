"""arxiv fixture 加载器（`tests/fixtures/arxiv/raw/`）。

八件套（+ 补充件）均为 **合成 fixture**（Phase 2 T5）——结构依 OAI-PMH 2.0 / Atom 1.0 /
arXiv API 规范，内容为构造值，各文件头以注释标注 "SYNTHETIC"。T7 在线冒烟负责用实测
响应对照保真度（并可经 `scripts/record_arxiv_fixtures.py` 重录）。

``.http`` 格式（⑥ 503 快照，响应头随 body 落盘——fixtures README 扩展）：
以 ``#`` 开头的行为注释；``HTTP-STATUS: <int>`` 声明状态码；其余 ``Key: Value`` 为
响应头；**首个空行**后为原始 body。
"""

from __future__ import annotations

from pathlib import Path

_RAW = Path(__file__).resolve().parents[1] / "fixtures" / "arxiv" / "raw"


def fixture_bytes(name: str) -> bytes:
    """读取 `raw/<name>` 的原始字节。"""
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
