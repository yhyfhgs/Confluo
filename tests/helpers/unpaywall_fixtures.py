"""unpaywall fixture 加载器（`tests/fixtures/unpaywall/`）。

**十二件套均为合成 fixture**（design/adapters/aggregators.md §5.5/§8；Phase 3 尚未做
真实站点录制）——JSON 体结构依 Unpaywall v2 响应 schema 手写，`01_normal_gold_fallback.json`
的 `is_oa`/`oa_status`/`best_oa_location.version`/`best_oa_location.url_for_pdf`/
`oa_locations` 计数四个字段为 [LIVE] 2026-07-22 核验值（同 D-019 锚点，aggregators.md §7），
其余字段与其他文件均为构造值，文件头以 `_grounded`/`_synthetic` 键标注。

``.http`` 格式（错误状态码件，响应头随 body 落盘——沿用 arxiv/openreview fixtures 约定）：
以 ``#`` 开头的行为注释；``HTTP-STATUS: <int>`` 声明状态码；其余 ``Key: Value`` 为
响应头；**首个空行**后为原始 body。
"""

from __future__ import annotations

from pathlib import Path

_RAW = Path(__file__).resolve().parents[1] / "fixtures" / "unpaywall"


def fixture_bytes(name: str) -> bytes:
    """读取 `unpaywall/<name>` 的原始字节。"""
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
