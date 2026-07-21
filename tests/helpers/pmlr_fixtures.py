"""pmlr fixture 加载器（`tests/fixtures/pmlr/raw/`）。

七件套均为**合成 fixture**（Phase 2，pmlr adapter 实现）——结构依
docs/research/site-survey/pmlr.md 的 [LIVE] 2026-07-22 勘察记录构造，第一条
真实条目（v235/abad-rocamora24a）复用勘察记录的真实字段值，其余为标注合成的
占位内容；各文件头以注释标注 "SYNTHETIC"。本次实现未做真实网络录制（D-014
约定：录制脚本要求 `PAPER_CRAWLER_CONTACT_EMAIL` 环境变量存在，本会话未设，
按约定全走合成路径）。
"""

from __future__ import annotations

from pathlib import Path

_RAW = Path(__file__).resolve().parents[1] / "fixtures" / "pmlr" / "raw"


def fixture_bytes(name: str) -> bytes:
    """读取 `raw/<name>` 的原始字节。"""
    return (_RAW / name).read_bytes()


__all__ = ["fixture_bytes"]
