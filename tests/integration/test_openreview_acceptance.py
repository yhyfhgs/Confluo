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


def test_anchor_accepted_counts_live_populated() -> None:
    # accepted_count 已由 [LIVE] 2026-07-22 token 化查询填充（content.venueid=<group_id>
    # count；见 live_verification）。2024 是唯一 DBLP 交叉核验的干净 accepted 值。
    assert _ANCHOR["count_status"] == "LIVE_2026-07-22_HETEROGENEOUS"
    e2024 = _ANCHOR_BY_YEAR[2024]
    assert e2024["accepted_count"] == 2260  # [LIVE] api2 v2 content.venueid count
    assert e2024["accepted_count"] == e2024["dblp_toc_count"]  # 2260 == 2260 两源互证
    assert e2024["accepted_count_endpoint"] == "v2"
    # 缺届（2015/2016）无 OpenReview 群 → accepted_count 恒 None。
    for year in (2015, 2016):
        assert _ANCHOR_BY_YEAR[year]["accepted_count"] is None
    # 其余有 venueid 的届均已填充为 int（含异常届 2013/2014/2018/2019 记 0）。
    for year, entry in _ANCHOR_BY_YEAR.items():
        if entry["openreview_venueid"]:
            assert isinstance(entry["accepted_count"], int), f"year {year} accepted_count 未填充"
    # heterogeneity 口径（method + caveat）在 live_verification 明示（如实记录，非静默）。
    lv = _ANCHOR["live_verification"]
    assert "accepted_count_method" in lv and "accepted_count_caveat" in lv


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
