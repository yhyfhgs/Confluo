"""OpenReview AC-2.1 离线验收层（design/adapters/openreview.md §7）。

**AC-2.1 判定 = `timeline iclr` 输出与 anchor 表全等（届列表 + venueid 结构）。** 正式
count 待用户 token（在线部分 BLOCKED，anchor accepted_count 全 null/PENDING_TOKEN）——
本离线层断言**结构**：内置届表 ≡ anchor 逐年 venueid（大小写精确）、2015/2016 缺届、
`timeline iclr`（零网络 discover）落库年集合 == anchor 非空年集合。零真实网络。
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml
from typer.testing import CliRunner

from helpers import make_openreview_venue
from paper_crawler.adapters.openreview import venues
from paper_crawler.cli import app
from paper_crawler.storage.db import Database

runner = CliRunner()

_ANCHOR_PATH = (
    Path(__file__).resolve().parents[1] / "fixtures" / "openreview" / "dblp-iclr-anchor.json"
)
_ANCHOR = json.loads(_ANCHOR_PATH.read_text(encoding="utf-8"))
_ANCHOR_BY_YEAR: dict[int, dict[str, object]] = {int(e["year"]): e for e in _ANCHOR["years"]}


# --- 内置届表 ≡ anchor 结构（届列表 + venueid 大小写）--------------------------------------


def test_builtin_table_year_set_equals_anchor() -> None:
    table = venues.resolve_venue_table(make_openreview_venue())
    assert set(table) == set(_ANCHOR_BY_YEAR)  # 年集合全等


def test_builtin_table_venueids_match_anchor_case_exact() -> None:
    table = venues.resolve_venue_table(make_openreview_venue())
    for year, entry in _ANCHOR_BY_YEAR.items():
        assert table[year] == entry["openreview_venueid"], f"year {year} venueid mismatch"


def test_lowercase_2013_2017_uppercase_2018plus_in_anchor() -> None:
    # 大小写规约（勘察 §2）在 anchor 与内置表同口径。
    assert _ANCHOR_BY_YEAR[2013]["openreview_venueid"] == "ICLR.cc/2013/conference"
    assert _ANCHOR_BY_YEAR[2017]["openreview_venueid"] == "ICLR.cc/2017/conference"
    assert _ANCHOR_BY_YEAR[2018]["openreview_venueid"] == "ICLR.cc/2018/Conference"
    assert _ANCHOR_BY_YEAR[2024]["openreview_venueid"] == "ICLR.cc/2024/Conference"


def test_2015_2016_missing_in_both() -> None:
    table = venues.resolve_venue_table(make_openreview_venue())
    for year in (2015, 2016):
        assert table[year] is None
        assert _ANCHOR_BY_YEAR[year]["openreview_venueid"] is None


def test_2013_2014_note_marks_arxiv_body() -> None:
    for year in (2013, 2014):
        assert "arxiv" in str(_ANCHOR_BY_YEAR[year]["note"]).lower()


def test_anchor_counts_pending_token() -> None:
    # 正式 count 待 token（在线部分 BLOCKED）——离线层不判 count。
    assert _ANCHOR["count_status"] == "PENDING_TOKEN"
    assert all(e["accepted_count"] is None for e in _ANCHOR["years"])


# --- timeline iclr（零网络）落库年集合 == anchor 非空年 -------------------------------------


def _write_iclr_home(base: Path) -> Path:
    home = base / "home"
    venues_dir = home / "venues"
    venues_dir.mkdir(parents=True)
    (home / "config.toml").write_text('[paths]\nvenues_dirs = ["venues"]\n', encoding="utf-8")
    doc = {
        "id": "iclr",
        "kind": "conference",
        "names": {
            "full": "International Conference on Learning Representations",
            "aliases": ["ICLR"],
        },
        "field": ["cs_ai"],
        "tier": "T1",
        "identifiers": {"dblp_key": "conf/iclr"},
        "metadata_source": "openreview",
        "fulltext_source": "openreview",
        "auth": {"level": "free_account", "provider_hint": "openreview"},
        "quirks": {"openreview_group_overrides": {}},
        "status": "active",
    }
    (venues_dir / "iclr.yaml").write_text(yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8")
    return home


def _issue_years(home: Path) -> set[int]:
    db = Database(home / "catalog.sqlite")
    try:
        rows = db.query(
            "SELECT DISTINCT year FROM issue WHERE venue_id='iclr' AND year IS NOT NULL"
        )
        return {int(r["year"]) for r in rows}
    finally:
        db.close()


def test_timeline_iclr_issue_years_equal_anchor_non_null(tmp_path: Path) -> None:
    """Closes: AC-2.1 (offline layer). timeline iclr（零网络 discover）届列表 ≡ anchor 非空年。"""
    home = _write_iclr_home(tmp_path)
    result = runner.invoke(app, ["timeline", "iclr", "--home", str(home)])
    assert result.exit_code == 0, result.output

    non_null_years = {int(e["year"]) for e in _ANCHOR["years"] if e["openreview_venueid"]}
    # 缺届（2015/2016）不产 Issue；其余每届各一行。
    assert _issue_years(home) == non_null_years
    assert 2015 not in _issue_years(home) and 2016 not in _issue_years(home)
    # 输出里可见若干代表年（结构呈现）。
    assert "2024" in result.output and "2013" in result.output


def test_timeline_iclr_omits_missing_years_from_output(tmp_path: Path) -> None:
    """缺届不作为 issue 行落库——2015/2016 不在 timeline 的 issue 年集合。"""
    home = _write_iclr_home(tmp_path)
    result = runner.invoke(app, ["timeline", "iclr", "--home", str(home)])
    assert result.exit_code == 0, result.output
    assert 2015 not in _issue_years(home)
    assert 2016 not in _issue_years(home)
