"""cvf D-019 锚点快照验收（design/adapters/cvf.md §6）。

**D-019 模式**：外源比对类验收以人工核准的锚点快照为可执行判定。CVF 的 cadence
届表是**时间相对**的（`edition_years(current_year=...)` 依赖"现在是哪一年"，不同
于 openreview `_ICLR_TABLE` 那种时间无关的固定字典）——锚点快照 `dblp-cvf-anchor.json`
标注 `current_year_basis=2026`（本快照捕获时的"当前年"），结构性比对须在**同一时间
基准**下进行（`cadence.edition_years(..., current_year=2026)` 对齐锚点的
`current_year_basis`），而非依赖测试运行时的真实时钟——这是"锚点快照"模式对
"时间相对生成规则"场景的正确应用（真实时钟会使年集合逐年增长，用真实时钟比对
固定快照会在锚点捕获年之后的每一年都产生虚假 DRIFT）。

种子行 CVPR2023=2353（[LIVE] 三法计数，见 anchor `note`）；其余 25 届
`paper_count_claimed=null` + `note='PENDING_DBLP_CROSSCHECK'`——待人工逐届核对
DBLP TOC 后回填（同 openreview `PENDING_TOKEN` 口径，D-019 "特例显式标注"）。

CLI 端到端 wiring 校验（`timeline cvpr`）用**真实时钟**（`load_adapters()` 无参
实例化，无 current_year 注入 seam）——为保持对未来年份的时间鲁棒性，只断言
"过去不变"的具体年份（2013 起点、2023 已知在案），不对全量年集合做时间敏感的
精确相等（那类断言留给上面的结构性锚点比对，已用固定 current_year 消除时间依赖）。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from helpers import make_cvf_venue
from paper_crawler.adapters.cvf import cadence
from paper_crawler.cli import app
from paper_crawler.storage.db import Database

runner = CliRunner()

_ANCHOR_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "cvf" / "dblp-cvf-anchor.json"
_ANCHOR = json.loads(_ANCHOR_PATH.read_text(encoding="utf-8"))
_CURRENT_YEAR_BASIS: int = _ANCHOR["current_year_basis"]
_EDITIONS: list[dict[str, object]] = _ANCHOR["editions"]


def _anchor_years(venue_id: str) -> set[int]:
    return {int(e["year"]) for e in _EDITIONS if e["venue"] == venue_id}


# --- 结构性锚点比对（固定 current_year_basis，时间无关、CI 安全）------------------------------


@pytest.mark.parametrize("venue_id", ["cvpr", "iccv", "wacv"])
def test_cadence_year_set_equals_anchor_at_pinned_current_year(venue_id: str) -> None:
    """Closes: D-019 结构比对。cadence 输出（钉死 current_year）≡ anchor 该 venue 年集合。"""
    computed = set(
        cadence.edition_years(make_cvf_venue(venue_id), current_year=_CURRENT_YEAR_BASIS)
    )
    assert computed == _anchor_years(venue_id)


def test_anchor_covers_exactly_three_venues() -> None:
    assert {str(e["venue"]) for e in _EDITIONS} == {"cvpr", "iccv", "wacv"}


def test_anchor_total_edition_count() -> None:
    # cvpr 14（2013-2026 逐年）+ iccv 7（2013-2025 奇数年）+ wacv 7（2020-2026 逐年）。
    assert len(_EDITIONS) == 28


def test_anchor_dblp_slug_convention_matches_venue_and_year() -> None:
    for entry in _EDITIONS:
        expected = f"conf/{entry['venue']}/{entry['venue']}{entry['year']}"
        assert entry["dblp_slug"] == expected


# --- 种子行 vs pending 行（D-019 "特例显式标注"）-----------------------------------------------


def test_cvpr2023_is_the_only_seeded_row() -> None:
    """Closes: D-019 锚点快照种子行。CVPR2023=2353（[LIVE] 三法计数一致）。"""
    seeded = [e for e in _EDITIONS if e["paper_count_claimed"] is not None]
    assert len(seeded) == 1
    (cvpr2023,) = seeded
    assert cvpr2023["venue"] == "cvpr"
    assert cvpr2023["year"] == 2023
    assert cvpr2023["paper_count_claimed"] == 2353
    assert "[LIVE]" in str(cvpr2023["note"])


def test_all_other_editions_are_pending_dblp_crosscheck() -> None:
    pending = [e for e in _EDITIONS if e["paper_count_claimed"] is None]
    assert len(pending) == 27
    assert all(e["note"] == "PENDING_DBLP_CROSSCHECK" for e in pending)


def test_anchor_count_status_is_partial_seed() -> None:
    assert _ANCHOR["count_status"] == "PARTIAL_SEED"


# --- CLI 端到端 wiring（真实时钟；只断言时间鲁棒的具体年份）------------------------------------


def _write_cvpr_home(base: Path) -> Path:
    home = base / "home"
    venues_dir = home / "venues"
    venues_dir.mkdir(parents=True)
    (home / "config.toml").write_text('[paths]\nvenues_dirs = ["venues"]\n', encoding="utf-8")
    doc = {
        "id": "cvpr",
        "kind": "conference",
        "names": {
            "full": "IEEE/CVF Conference on Computer Vision and Pattern Recognition",
            "aliases": ["CVPR"],
        },
        "field": ["cs_ai"],
        "tier": "T1",
        "identifiers": {"dblp_key": "conf/cvpr"},
        "metadata_source": "cvf",
        "fulltext_source": "cvf",
        "quirks": {"cvf_edition_overrides": {}},
        "status": "active",
    }
    (venues_dir / "cvpr.yaml").write_text(yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8")
    return home


def _issue_years(home: Path) -> set[int]:
    db = Database(home / "catalog.sqlite")
    try:
        rows = db.query(
            "SELECT DISTINCT year FROM issue WHERE venue_id='cvpr' AND year IS NOT NULL"
        )
        return {int(r["year"]) for r in rows}
    finally:
        db.close()


def test_timeline_cvpr_cli_wiring_includes_known_past_editions(tmp_path: Path) -> None:
    """Closes: AC-2.4 相关 CLI wiring 校验。`timeline cvpr`（零网络 discover，真实时钟）

    落库年集合含 2013（起点）与 2023（anchor 种子年）——两者均早于本快照捕获年
    （2026），对任意未来运行时刻恒真，不因真实时钟推进而漂移（不同于对全量年
    集合做精确相等，那类判定见上面固定 current_year 的结构性比对）。
    """
    home = _write_cvpr_home(tmp_path)
    result = runner.invoke(app, ["timeline", "cvpr", "--home", str(home)])
    assert result.exit_code == 0, result.output

    years = _issue_years(home)
    assert 2013 in years
    assert 2023 in years
    assert 2012 not in years  # CVF 收录边界之前（design §1）
    assert "2023" in result.output


def test_timeline_cvpr_since_narrows_via_discover_refresh(tmp_path: Path) -> None:
    # --refresh 走强制 enqueue+drain 路径（cli.py 模块 docstring 实现选择 1）；
    # 与普通 timeline 应产生同一批年（cadence 是纯函数，force 只影响新鲜度记账）。
    home = _write_cvpr_home(tmp_path)
    result = runner.invoke(app, ["timeline", "cvpr", "--refresh", "--home", str(home)])
    assert result.exit_code == 0, result.output
    assert 2013 in _issue_years(home)
