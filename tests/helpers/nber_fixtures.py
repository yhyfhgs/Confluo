"""nber fixture 加载器（`tests/fixtures/nber/`）。

出处分级（nber.md §7）：
- `01_rss_new_truncated.xml`：[LIVE] 结构（back.nber.org/rss/new.xml 2026-07-24），脱敏截断
  2 item + 1 畸形（缺 guid series 段）；标题/摘要构造值。
- `02_pdf_head_w30000.bin`：[LIVE-shape] w30000 开放 PDF 头（`%PDF-` 魔数，不含真实正文；
  `.bin` 扩展名——`.pdf` 被 .gitignore 全禁，AC-0 红线「PDF 不入 git」；本件仅魔数样例非真实正文）。
- `03_softgate_synth.html`：**[SYNTH]** 合成非 PDF 软门（<18 月软门无真实抓取——红线未探，§7）。
- `04_crossref_prefix_facet.json` / `05_crossref_prefix_works.json`：SYNTHETIC（crossref 形状，
  DOI [LIVE]-grounded 10.3386/w{n}）——nber 消费 T1 prefix+published 契约的枚举实跑证据。
"""

from __future__ import annotations

from pathlib import Path

_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "nber"


def fixture_bytes(name: str) -> bytes:
    """读取 `nber/<name>` 的原始字节。"""
    return (_DIR / name).read_bytes()


__all__ = ["fixture_bytes"]
