"""aaai_ojs fixture 加载器（`tests/fixtures/aaai/raw/`）。

十一件套均为**合成 fixture**（Phase 2，aaai_ojs adapter 实现）——结构依
docs/research/site-survey/aaai-ojs.md 的 [LIVE] 2026-07-21 勘察记录构造（原始响应
归档 `aaai-raw/`）；第一条真实条目（Vol.33/AAAI-19 的 `article/3745`，勘察 §5.2 逐字
样本）复用实测字段值，其余为标注合成的占位内容；各文件头以注释标注 "SYNTHETIC"。
本次实现未做真实网络录制（D-014 约定：录制脚本要求 `PAPER_CRAWLER_CONTACT_EMAIL`
环境变量存在，本会话未设，按约定全走合成路径）。
"""

from __future__ import annotations

from pathlib import Path

_RAW = Path(__file__).resolve().parents[1] / "fixtures" / "aaai" / "raw"


def fixture_bytes(name: str) -> bytes:
    """读取 `raw/<name>` 的原始字节。"""
    return (_RAW / name).read_bytes()


__all__ = ["fixture_bytes"]
