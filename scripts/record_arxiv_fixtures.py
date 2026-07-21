#!/usr/bin/env python3
"""一次性 arXiv fixture 录制脚本（**不属测试；单次人工运行**）。

用途：把 `tests/fixtures/arxiv/raw/` 的合成 fixture 用真实响应对照/替换（T7 在线冒烟，
或需要提升保真度时）。默认写入 `tests/fixtures/arxiv/_staging/`（**不入 git**，人工过目
脱敏后再手动挪进 `raw/`）。

护栏（AGENTS §6「真实网络纪律」）：
- 硬预算 ≤ `_MAX_REQUESTS` 次真实请求；单连接、每请求间隔 `_MIN_INTERVAL_S`（1 req/3s ToU）。
- UA 走 D-014（`PaperCrawler/<ver> (personal research; mailto:<email>)`）；email 从
  `PAPER_CRAWLER_CONTACT_EMAIL` 环境变量取，**不硬编码**；未设则拒绝运行。
- arXiv 无认证——脱敏只需人工确认无个人信息即可（无 cookie/token）。

⚠ **实现期复核义务（arxiv.md §4）**：首次在线前须实测 `export.arxiv.org/robots.txt` 与
现行 API ToU 文本；若与「robots 网页公约不适用于 ToU 授权的 API 消费」这一推理相悖，
立即停用该通道并升级 decision-log 仲裁（AC-0.5 红线优先）。本脚本只访问官方文档化 API
端点（Query API / OAI-PMH），不触 robots 禁区。

用法：
    PAPER_CRAWLER_CONTACT_EMAIL=you@example.edu uv run python scripts/record_arxiv_fixtures.py
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from paper_crawler import __version__
from paper_crawler.http import HttpClient

_STAGING = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "arxiv" / "_staging"
_MAX_REQUESTS = 10
_MIN_INTERVAL_S = 3.0  # arXiv ToU：1 req/3s 单连接

# (文件名, url)——只覆盖真实可录制的正常态（① Query Atom、② OAI 首页、③ 空 Atom、
# ⑨ healthcheck canary）；错误态（④⑥⑦⑧）与撤稿页（⑤）保持合成（难可靠触发/易变）。
# ② 的 from/until 取极窄窗口 + 单一 category 的 archive set，避免拉回海量记录。
_TARGETS: tuple[tuple[str, str], ...] = (
    (
        "01_query_atom_normal.xml",
        "https://export.arxiv.org/api/query?search_query=cat:cs.LG&start=0&max_results=10",
    ),
    (
        "02_oai_listrecords_page1.xml",
        "https://oaipmh.arxiv.org/oai?verb=ListRecords&metadataPrefix=arXiv"
        "&set=cs&from=2024-01-01&until=2024-01-01",
    ),
    (
        "03_query_atom_empty.xml",
        "https://export.arxiv.org/api/query?id_list=2401.99999&max_results=1",
    ),
    (
        "09_query_atom_healthcheck.xml",
        "https://export.arxiv.org/api/query?id_list=2401.00001v1,2312.00002v1,2311.00003v2",
    ),
)


def _user_agent() -> str:
    email = os.environ.get("PAPER_CRAWLER_CONTACT_EMAIL", "").strip()
    if not email:
        sys.exit(
            "refusing to run: set PAPER_CRAWLER_CONTACT_EMAIL (D-014 UA must carry a real "
            "contact; it is never hardcoded)."
        )
    return f"PaperCrawler/{__version__} (personal research; mailto:{email})"


def main() -> int:
    if len(_TARGETS) > _MAX_REQUESTS:  # pragma: no cover - 静态护栏
        sys.exit(f"targets ({len(_TARGETS)}) exceed request budget ({_MAX_REQUESTS})")
    _STAGING.mkdir(parents=True, exist_ok=True)
    print(f"recording {len(_TARGETS)} target(s) to {_STAGING} at 1 req/{_MIN_INTERVAL_S:g}s")
    print("REMINDER: verify export.arxiv.org/robots.txt + API ToU live first (arxiv.md §4).")

    client = HttpClient(user_agent=_user_agent())
    try:
        for index, (name, url) in enumerate(_TARGETS):
            if index:
                time.sleep(_MIN_INTERVAL_S)
            print(f"  GET {url}")
            (_STAGING / name).write_bytes(client.get_bytes(url))
    finally:
        client.close()

    print(
        "done. Manually review _staging/ for de-identification (arXiv has no auth — confirm no "
        "personal info), trim oversized OAI pages, then move vetted files into raw/."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
