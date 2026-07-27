"""`crawler search` CLI 集成测试（Phase 7 T12；权威决策 D-034）。

覆盖 CLI 接线本身（`--limit`/`--venue` 透传、零命中提示、未知 venue/语法错误的退出码），
不重复 `tests/unit/test_repo.py::search_papers` 已覆盖的检索/排序/触发器同步逻辑细节。
零真实网络：直接经 `Repo`/`Database` 往库里插入 paper 行（绕过 pull 流水线），同
`test_cli_oa_report.py` 既有手法。
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml
from typer.testing import CliRunner

from paper_crawler.cli import app
from paper_crawler.storage.db import Database
from paper_crawler.storage.repo import Repo
from paper_crawler.types import PaperStub, VenueSpec

runner = CliRunner()

_VENUE_A = "mock_journal_a"
_VENUE_B = "mock_journal_b"


def _venue_spec(venue_id: str) -> VenueSpec:
    return VenueSpec(
        id=venue_id,
        kind="journal",
        names={"full": venue_id, "aliases": []},
        field=["cs_ai"],
        identifiers={"issn": ["0000-0000"]},
        metadata_source="mock_platform",
        fulltext_source="mock_platform",
    )


def _write_venue_yaml(venues_dir: Path, venue_id: str) -> None:
    doc = {
        "id": venue_id,
        "kind": "journal",
        "names": {"full": venue_id, "aliases": []},
        "field": ["cs_ai"],
        "identifiers": {"issn": ["0000-0000"]},
        "metadata_source": "mock_platform",
        "fulltext_source": "mock_platform",
    }
    (venues_dir / f"{venue_id}.yaml").write_text(
        yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8"
    )


def _make_home(tmp_path: Path, *, with_venues_dir: bool = False) -> Path:
    home = tmp_path / "home"
    if with_venues_dir:
        venues_dir = home / "venues"
        venues_dir.mkdir(parents=True)
        (home / "config.toml").write_text('[paths]\nvenues_dirs = ["venues"]\n', encoding="utf-8")
        _write_venue_yaml(venues_dir, _VENUE_A)
        _write_venue_yaml(venues_dir, _VENUE_B)
    return home


def _seed_papers(home: Path, papers_by_venue: dict[str, list[tuple[str, str, str | None]]]) -> None:
    """直接经 `Repo` 往 `home/catalog.sqlite` 插入 (doi, title, abstract) 论文行。"""
    db = Database(home / "catalog.sqlite")
    db.migrate()
    repo = Repo(db)
    for venue_id, papers in papers_by_venue.items():
        repo.upsert_venue(_venue_spec(venue_id))
        for doi, title, abstract in papers:
            repo.upsert_paper(
                venue_id,
                None,
                PaperStub(title=title, identifiers=(("doi", doi),), abstract=abstract),
            )
    db.close()


# --- 正常命中 ---------------------------------------------------------------------------------


def test_search_matches_title_prints_table(tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    _seed_papers(
        home,
        {"mock_journal": [("10.0/a", "Deep Learning for Asset Pricing", None)]},
    )

    result = runner.invoke(app, ["search", "pricing", "--home", str(home)])

    assert result.exit_code == 0, result.output
    assert "Deep Learning for Asset Pricing" in result.output


def test_search_matches_abstract(tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    _seed_papers(
        home,
        {"mock_journal": [("10.0/a", "Paper One", "We study neural networks in finance.")]},
    )

    result = runner.invoke(app, ["search", "neural", "--home", str(home)])

    assert result.exit_code == 0, result.output
    assert "Paper One" in result.output


# --- 聚合显示：与 `list` 同名同义同默认（R2-F4）------------------------------------------------


def _seed_merged_pair(home: Path) -> tuple[str, str]:
    """两篇同题 paper + 一条已裁决 `same_as(merged)`（经 `dedupe decide merge` 同一入口）。"""
    db = Database(home / "catalog.sqlite")
    db.migrate()
    repo = Repo(db)
    repo.upsert_venue(_venue_spec("mock_journal"))
    ids = [
        repo.upsert_paper(
            "mock_journal",
            None,
            PaperStub(title=title, identifiers=(("doi", doi),), year=year),
        )
        for doi, title, year in (
            ("10.9999/a", "Deep Learning for Asset Pricing", 2023),
            ("10.9999/b", "Deep learning for asset pricing", 2024),
        )
    ]
    db.execute(
        "INSERT INTO paper_relation "
        "(from_paper, to_paper, kind, confidence, evidence_json, decided) VALUES (?,?,?,?,?,?)",
        (ids[0], ids[1], "candidate_duplicate", 0.5, json.dumps({"reason": "weak"}), None),
    )
    repo.decide_candidate(ids[0], ids[1], "merge")
    db.close()
    return ids[0], ids[1]


def test_search_folds_merged_rows_by_default_like_list(tmp_path: Path) -> None:
    """R2-F4：同一个库、同一批人工裁决，`search` 与 `list` 必须给出同一个聚合答案——
    修复前 `list` 折叠而 `search` 恒不折叠，"库里到底有几篇"取决于用了哪条命令。"""
    home = _make_home(tmp_path)
    a, b = _seed_merged_pair(home)

    result = runner.invoke(app, ["search", "pricing", "--home", str(home)])

    assert result.exit_code == 0, result.output
    assert result.output.count("Asset Pricing") + result.output.count("asset pricing") == 1
    assert min(a, b) in result.output and max(a, b) not in result.output  # 只留类代表
    assert "已按 same_as(merged) 折叠 1 行" in result.output
    assert "--no-aggregate" in result.output  # 注记给出展开方法


def test_search_no_aggregate_expands_merged_rows(tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    a, b = _seed_merged_pair(home)

    result = runner.invoke(app, ["search", "pricing", "--no-aggregate", "--home", str(home)])

    assert result.exit_code == 0, result.output
    assert a in result.output and b in result.output
    assert "已按 same_as(merged) 折叠" not in result.output


def test_search_result_rows_survive_the_fold_path_columns_intact(tmp_path: Path) -> None:
    """列对齐回归：检索行（`paper_id`/`title`/`year`/`venue_id`）走完折叠仍照常渲染——
    修复前 search 行进折叠即 `IndexError: No item with that key`（列名 `id` vs `paper_id`）。"""
    home = _make_home(tmp_path)
    a, b = _seed_merged_pair(home)

    result = runner.invoke(app, ["search", "pricing", "--home", str(home)])

    assert result.exit_code == 0, result.output
    assert "IndexError" not in result.output
    header, _, first = result.output.splitlines()[:3]
    assert header.split() == ["paper_id", "title", "year", "venue_id"]
    assert first.startswith(min(a, b))  # 首行首列仍是类代表的 paper_id
    assert "mock_journal" in first and "2023" in first  # venue_id/year 列未错位


def test_search_no_fold_note_when_nothing_was_folded(tmp_path: Path) -> None:
    """没折掉任何行就不出注记——恒挂一句"折叠 0 行"是纯噪声。"""
    home = _make_home(tmp_path)
    _seed_papers(home, {"mock_journal": [("10.0/a", "Pricing Paper", None)]})

    result = runner.invoke(app, ["search", "pricing", "--home", str(home)])

    assert result.exit_code == 0, result.output
    assert "已按 same_as(merged) 折叠" not in result.output


# --- 零命中 -------------------------------------------------------------------------------------


def test_search_no_match_prints_message_and_exits_0(tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    _seed_papers(home, {"mock_journal": [("10.0/a", "Some Paper", None)]})

    result = runner.invoke(app, ["search", "nonexistentterm", "--home", str(home)])

    assert result.exit_code == 0, result.output
    assert "无匹配结果" in result.output


# --- --limit 截断 -----------------------------------------------------------------------------


def test_search_limit_truncates_results(tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    _seed_papers(
        home,
        {"mock_journal": [(f"10.0/{i}", f"Pricing Paper {i}", None) for i in range(5)]},
    )

    result = runner.invoke(app, ["search", "pricing", "--limit", "2", "--home", str(home)])

    assert result.exit_code == 0, result.output
    assert result.output.count("Pricing Paper") == 2


# --- --venue 过滤 -----------------------------------------------------------------------------


def test_search_venue_filter_only_matches_that_venue(tmp_path: Path) -> None:
    home = _make_home(tmp_path, with_venues_dir=True)
    _seed_papers(
        home,
        {
            _VENUE_A: [("10.0/a", "Pricing in Venue A", None)],
            _VENUE_B: [("10.0/b", "Pricing in Venue B", None)],
        },
    )

    result = runner.invoke(app, ["search", "pricing", "--venue", _VENUE_A, "--home", str(home)])

    assert result.exit_code == 0, result.output
    assert "Pricing in Venue A" in result.output
    assert "Pricing in Venue B" not in result.output


def test_search_unknown_venue_exits_2(tmp_path: Path) -> None:
    home = _make_home(tmp_path, with_venues_dir=True)
    _seed_papers(home, {_VENUE_A: [("10.0/a", "Some Paper", None)]})

    result = runner.invoke(
        app, ["search", "some", "--venue", "not_a_real_venue", "--home", str(home)]
    )

    assert result.exit_code == 2


# --- 检索表达式语法错误 --------------------------------------------------------------------------


def test_search_invalid_match_syntax_exits_2(tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    _seed_papers(home, {"mock_journal": [("10.0/a", "Some Paper", None)]})

    # FTS5 MATCH 语法错误：裸悬空的列限定符（无值）。
    result = runner.invoke(app, ["search", "title:", "--home", str(home)])

    assert result.exit_code == 2


# --- paper_fts 表整体缺失（T12 独立审查 P2-3）-----------------------------------------------------


def test_search_missing_fts_table_exits_2_with_actionable_message(tmp_path: Path) -> None:
    """`paper_fts` 表整体不存在时（手动 DB 操作等场景，正常路径不应发生）不得让裸
    `OperationalError` 冒出——须呈现可操作 `CrawlerError` 消息并退出 2。
    """
    home = _make_home(tmp_path)
    _seed_papers(home, {"mock_journal": [("10.0/a", "Some Paper", None)]})
    db = Database(home / "catalog.sqlite")
    db.execute("DROP TABLE paper_fts")
    db.close()

    result = runner.invoke(app, ["search", "some", "--home", str(home)])

    assert result.exit_code == 2
    assert "paper_fts" in result.output
