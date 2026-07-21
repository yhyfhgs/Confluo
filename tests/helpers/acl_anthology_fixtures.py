"""acl_anthology fixture 加载器（`tests/fixtures/acl_anthology/`）。

**全部为合成 fixture（SYNTHETIC）**（design/adapters/acl-anthology.md §7）：结构依
`data/xml/schema.rnc`（RelaxNG Compact，官方权威定义）与 research/site-survey/
acl-anthology.md [LIVE] 实测的真实字段/取值形态手写（部分标题/摘要/作者直接借用
[LIVE] 勘察中记录的真实公开文本，属公开发表论文的可核实事实，非虚构），内容规模
按比例缩样（T3 小 fixture ≠ AC-2.5 离线层用的全量计数生成器，见
`tests/helpers/acl_anthology_bulk.py`）。

``.http`` 格式（错误状态码件，响应头随 body 落盘——沿用 arxiv/openreview fixtures
约定）：以 ``#`` 开头的行为注释；``HTTP-STATUS: <int>`` 声明状态码；其余
``Key: Value`` 为响应头；**首个空行**后为原始 body。
"""

from __future__ import annotations

from pathlib import Path

_RAW = Path(__file__).resolve().parents[1] / "fixtures" / "acl_anthology"


def fixture_bytes(name: str) -> bytes:
    """读取 `acl_anthology/<name>` 的原始字节。"""
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
