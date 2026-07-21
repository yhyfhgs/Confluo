"""openreview fixture 加载器（`tests/fixtures/openreview/`）。

**十一件套（+分页/groups 辅助件）均为合成 fixture**（design/adapters/openreview.md §7；
Phase 2 无用户 token 故全部合成）——JSON 体结构依 docs.openreview.net v1/v2 note schema
与勘察 [DOC]/[LIVE]，内容为构造值，文件头（JSON `_synthetic` 键 / `.http` `#` 注释）
标注 "SYNTHETIC；待 token 后真实校验"。带 token 后可用实测响应对照保真度并重录。

``.http`` 格式（错误状态码件，响应头随 body 落盘——沿用 arxiv fixtures 约定）：
以 ``#`` 开头的行为注释；``HTTP-STATUS: <int>`` 声明状态码；其余 ``Key: Value`` 为
响应头；**首个空行**后为原始 body。
"""

from __future__ import annotations

from pathlib import Path

_RAW = Path(__file__).resolve().parents[1] / "fixtures" / "openreview"


def fixture_bytes(name: str) -> bytes:
    """读取 `openreview/<name>` 的原始字节。"""
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
