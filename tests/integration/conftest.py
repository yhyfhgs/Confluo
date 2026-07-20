"""AC-1 集成测试的共享装配（Task 9）。

四份 AC 测试（kill-resume/dry-run/ratelimit/blocked-resume）都要建一个"真实
`Config.load(home)` 路径"的隔离 HOME：`config.toml` 钉住 `venues_dirs`、写一份
mock venue YAML、可选叠加 `rate_limit`（venue 级覆盖）与 `[rate] scale`（把限速
sleep 快进——不测限速的 AC 借此免去真实等待）。这套装配与 `test_cli.py` 的
`_make_home`/`_write_venue` 同形，此处抽成可复用件供四份新测试共享；venue 语料
口径（`VENUE`/`DEFAULT_QUIRKS`）继续复用 `test_pipeline_e2e`，全仓一致。

`build_home`/`write_mock_venue` 是模块级函数（供 kill-resume 建两个 home、
blocked-resume 中途改写 YAML 模拟人工修复时按 `from integration.conftest import ...`
取用）；`make_home` 是便捷 fixture（单 home 的常见情形，免 import）。
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
import yaml

from integration.test_pipeline_e2e import DEFAULT_QUIRKS, VENUE

__all__ = ["DEFAULT_QUIRKS", "VENUE", "build_home", "make_home", "write_mock_venue"]


def write_mock_venue(
    venues_dir: Path, quirks: dict[str, object], *, rate_limit_rpm: float | None = None
) -> None:
    """写/覆盖一份 mock venue YAML（形状同 test_cli._write_venue，lint 可过、路由 mock）。"""
    doc: dict[str, object] = {
        "id": VENUE,
        "kind": "journal",
        "names": {"full": "Mock Journal", "aliases": ["MJ"]},
        "field": ["cs_ai"],
        "tier": "T1",
        "identifiers": {"issn": ["0000-0000"]},
        "metadata_source": "mock_platform",
        "fulltext_source": "mock_platform",
        "auth": {"level": "none"},
        "quirks": quirks,
        "status": "active",
    }
    if rate_limit_rpm is not None:
        doc["rate_limit"] = {"requests_per_minute": rate_limit_rpm}
    (venues_dir / "mock-journal.yaml").write_text(
        yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8"
    )


def build_home(
    base: Path,
    quirks: dict[str, object],
    *,
    name: str = "home",
    rate_limit_rpm: float | None = None,
    rate_scale: float | None = None,
) -> Path:
    """在 `base/name` 下装配一个隔离 HOME（config.toml + 一份 mock venue）。"""
    home = base / name
    venues_dir = home / "venues"
    venues_dir.mkdir(parents=True)
    config_lines = ["[paths]", 'venues_dirs = ["venues"]']
    if rate_scale is not None:
        config_lines += ["", "[rate]", f"scale = {rate_scale}"]
    (home / "config.toml").write_text("\n".join(config_lines) + "\n", encoding="utf-8")
    write_mock_venue(venues_dir, dict(quirks), rate_limit_rpm=rate_limit_rpm)
    return home


@pytest.fixture
def make_home(tmp_path: Path) -> Callable[..., Path]:
    """便捷 home 工厂：`make_home(quirks, name=..., rate_limit_rpm=..., rate_scale=...)`。"""

    def _make(
        quirks: dict[str, object],
        *,
        name: str = "home",
        rate_limit_rpm: float | None = None,
        rate_scale: float | None = None,
    ) -> Path:
        return build_home(
            tmp_path, quirks, name=name, rate_limit_rpm=rate_limit_rpm, rate_scale=rate_scale
        )

    return _make
