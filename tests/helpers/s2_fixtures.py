"""s2 fixture 加载器（`tests/fixtures/s2/`）。

**全部合成 fixture**（Phase 3 T6，无真实网络录制，无 key 故无法录制）——JSON 体结构
依 Semantic Scholar Graph API `/paper/batch` [DOCS] 与 aggregators.md §5.4；
`01_batch_normal.json`/`07_single_paper_healthcheck.json` 的 `paperId`/DOI/title
取自真实存在的知名论文（"Attention Is All You Need"，Vaswani et al. 2017，[LIVE]
未经本次实现在线核验——S2 key 用户申请中，仅借其真实存在性避免"合成假设"，Phase 2
教训），`citationCount`/`tldr` 等具体数值为构造值（真实引用数会随时间增长，不宜写死
断言精确值）。

``.http`` 格式同 crossref/unpaywall/openalex fixtures 约定（见其模块 docstring）。
"""

from __future__ import annotations

from pathlib import Path

_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "s2"


def fixture_bytes(name: str) -> bytes:
    """读取 `s2/<name>` 的原始字节。"""
    return (_DIR / name).read_bytes()


def http_fixture(name: str) -> tuple[int, dict[str, str], bytes]:
    """解析 ``.http`` 快照 → ``(status, headers, body)``。"""
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


__all__ = ["fixture_bytes", "http_fixture"]
