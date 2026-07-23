"""econsoc fixture 加载器（`tests/fixtures/econsoc/raw/`）。

五件套均为**合成 fixture**（Phase 5 T6，econsoc adapter 实现）——结构依
docs/research/site-survey/econometric-society.md 的 [LIVE] 2026-07-24 R0c 勘察记录构造
（TE OAI ListRecords oai_dc completeListSize 656；DOI 后缀 `te{n}` 为实测形态；
econometricsociety.org 当前段落地页含 galley 链 `/publications/.../file/{file}.PDF`）；
各文件头以注释标注 "SYNTHETIC"。本次实现未做真实网络录制（D-014 约定：录制脚本要求
`PAPER_CRAWLER_CONTACT_EMAIL` 环境变量，本会话未设，按约定全走合成路径）。
"""

from __future__ import annotations

from pathlib import Path

_RAW = Path(__file__).resolve().parents[1] / "fixtures" / "econsoc" / "raw"


def fixture_bytes(name: str) -> bytes:
    """读取 `raw/<name>` 的原始字节。"""
    return (_RAW / name).read_bytes()


__all__ = ["fixture_bytes"]
