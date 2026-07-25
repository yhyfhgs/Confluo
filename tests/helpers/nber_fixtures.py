"""nber fixture 加载器（`tests/fixtures/nber/`）。

出处分级（nber.md §7）：
- `01_rss_new_truncated.xml`：[LIVE] 结构（back.nber.org/rss/new.xml 2026-07-24），脱敏截断
  2 item + 1 畸形（缺 guid series 段）；标题/摘要构造值。
- `02_pdf_head_w30000.bin`：[LIVE-shape] w30000 开放 PDF 头（`%PDF-` 魔数，不含真实正文；
  `.bin` 扩展名——`.pdf` 被 .gitignore 全禁，AC-0 红线「PDF 不入 git」；本件仅魔数样例非真实正文）。
- `03_softgate_synth.html`：**[SYNTH]** 合成非 PDF 软门（<18 月软门无真实抓取——红线未探，§7）。
- `04_crossref_prefix_facet.json` / `05_crossref_prefix_works.json`：SYNTHETIC（crossref 形状，
  DOI [LIVE]-grounded 10.3386/w{n}）——nber 消费 T1 prefix+published 契约的枚举实跑证据。
- `06_rss_program_cf_synth.xml`（Phase 6 T7）：SYNTHETIC，结构对齐 `newcf.xml` 的 [LIVE]
  200/3-item 实测（nber.md §2 请求清单 #13）；3 item 覆盖逗号作者/and-连接作者（无逗号）/
  无作者尾巴三种标题形态 + 缺 pubDate + 畸形 pubDate + w/t 两种 series 前缀，供 `rss.py`
  `_parse_feed_entries` 解析回归。
- `07_rss_program_empty.xml`（Phase 6 T7）：SYNTHETIC，合法 RSS 结构但零 `<item>`——program
  某周无新增的边界（非畸形，parse 侧应返回空元组）。
- `08_rss_program_malformed.xml`（Phase 6 T7）：SYNTHETIC，故意未闭合标签的畸形 XML——
  fail-loud `PARSE` 边界。
"""

from __future__ import annotations

from pathlib import Path

_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "nber"


def fixture_bytes(name: str) -> bytes:
    """读取 `nber/<name>` 的原始字节。"""
    return (_DIR / name).read_bytes()


__all__ = ["fixture_bytes"]
