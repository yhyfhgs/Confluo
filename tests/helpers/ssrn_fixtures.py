"""ssrn fixture 加载器（`tests/fixtures/ssrn/`）+ works 页构造器（7 日回放）。

全部合成 fixture（Phase 5 T4，无真实网络录制）——crossref `/prefixes/10.2139/works`
JSON 体结构依 aggregators.md §5.1 + crossref REST [DOCS]；样本 DOI/title 为构造值
（合法 `10.2139/ssrn.{id}` 形态）。JSON 件顶层带 `_synthetic` 键。

`works_page_bytes` 供 7 收割日回放：把一组 ssrn DOI 编成一页合法 works 响应
（每 DOI 一条最小记录），避免逐日一份冗长静态件——回放的重叠/延迟结构在
`06_replay_7days.json` 的 `days` 里可审计，本构造器只负责把 `dois` 渲染成 crossref 页形态。
"""

from __future__ import annotations

import json
from pathlib import Path

_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "ssrn"


def fixture_bytes(name: str) -> bytes:
    """读取 `ssrn/<name>` 的原始字节。"""
    return (_DIR / name).read_bytes()


def fixture_json(name: str) -> dict[str, object]:
    """读取并解析 `ssrn/<name>` 为 dict（回放 spec / unpaywall 响应等）。"""
    return json.loads(fixture_bytes(name))


def works_page_bytes(
    dois: list[str], *, next_cursor: str | None = None, total: int | None = None
) -> bytes:
    """把一组 DOI 渲染成 crossref `/prefixes/10.2139/works` 页 bytes（7 日回放用）。

    每 DOI 一条最小合法记录（DOI + title + type + 空 author）。`next_cursor=None` →
    `next-cursor:null`（单页终止）；`total` 缺省 = 记录数。
    """
    items = [
        {
            "DOI": doi,
            "title": [f"SSRN Working Paper {doi}"],
            "type": "journal-article",
            "author": [],
        }
        for doi in dois
    ]
    message = {
        "total-results": total if total is not None else len(items),
        "next-cursor": next_cursor,
        "items-per-page": len(items),
        "items": items,
    }
    doc = {"status": "ok", "message-type": "work-list", "message": message}
    return json.dumps(doc).encode("utf-8")


__all__ = ["fixture_bytes", "fixture_json", "works_page_bytes"]
