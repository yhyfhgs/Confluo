"""cvf fixture 加载器（`tests/fixtures/cvf/`）。

**十件套均为合成 fixture**（design/adapters/cvf.md §6 T3；条目 1/2 的首条目逐字
转录自 [LIVE] 站点勘察，其余合成——各文件头注释标注出处）。`.http` 格式沿用
arxiv/openreview fixtures 约定，见 `tests/fixtures/README.md`。
"""

from __future__ import annotations

from pathlib import Path

_RAW = Path(__file__).resolve().parents[1] / "fixtures" / "cvf"


def fixture_text(name: str) -> str:
    """读取 `cvf/<name>` 的 UTF-8 文本（HTML 件）。"""
    return (_RAW / name).read_text(encoding="utf-8")


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


__all__ = ["fixture_text", "http_fixture"]
