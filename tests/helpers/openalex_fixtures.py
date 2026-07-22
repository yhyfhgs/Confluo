"""openalex fixture 加载器（`tests/fixtures/openalex/`）。

**全部合成 fixture**（Phase 3 T6，无真实网络录制）——JSON 体结构依 OpenAlex REST
`/works` [DOCS] 与 aggregators.md §5.3；`01_works_normal.json`/`08_single_work_
healthcheck.json` 的 DOI/OpenAlex id/title 取自真实存在的知名条目（Piwowar et al.
2018 "The state of OA"，[LIVE] 未经本次实现在线核验，仅借其真实存在性避免"合成假设"
——Phase 2 教训），其余字段（abstract_inverted_index/open_access 等）为构造值。

``.http`` 格式（错误状态码件，响应头随 body 落盘——沿 crossref/unpaywall fixtures
约定）：以 ``#`` 开头行为注释；``HTTP-STATUS: <int>`` 声明状态码；其余 ``Key: Value``
为响应头；**首个空行**后为原始 body。
"""

from __future__ import annotations

from pathlib import Path

_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "openalex"


def fixture_bytes(name: str) -> bytes:
    """读取 `openalex/<name>` 的原始字节。"""
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
