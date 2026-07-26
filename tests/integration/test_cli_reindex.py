"""`crawler reindex [--check]` CLI 集成测试（Phase 7 T12；权威决策 D-034 决策 5）。

覆盖 CLI 接线本身（重建行数呈现、`--check` 一致/不一致两态的退出码与文案），不重复
`tests/unit/test_repo.py::check_fts_consistency`/`reindex_fts` 已覆盖的差集/去重/
integrity-check 逻辑细节。零真实网络：直接经 `Repo`/`Database` 操作库（绕过 pull
流水线），同 `test_cli_oa_report.py`/`test_cli_search.py` 既有手法。
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from typer.testing import CliRunner

from paper_crawler.cli import app
from paper_crawler.storage.db import Database
from paper_crawler.storage.repo import Repo
from paper_crawler.types import PaperStub, VenueSpec

runner = CliRunner()

_VENUE_ID = "mock_journal"


def _venue_spec() -> VenueSpec:
    return VenueSpec(
        id=_VENUE_ID,
        kind="journal",
        names={"full": _VENUE_ID, "aliases": []},
        field=["cs_ai"],
        identifiers={"issn": ["0000-0000"]},
        metadata_source="mock_platform",
        fulltext_source="mock_platform",
    )


def _make_home(tmp_path: Path) -> Path:
    return tmp_path / "home"


def _seed_papers(home: Path, papers: list[tuple[str, str]]) -> None:
    """经 `Repo` 插入 (doi, title) 论文行；返回打开的 `Database` 供调用方直接做
    低层破坏（模拟索引漂移）后自行 `close()`。
    """
    db = Database(home / "catalog.sqlite")
    db.migrate()
    repo = Repo(db)
    repo.upsert_venue(_venue_spec())
    for doi, title in papers:
        repo.upsert_paper(_VENUE_ID, None, PaperStub(title=title, identifiers=(("doi", doi),)))
    db.close()


def _break_index_with_orphan_row(home: Path) -> None:
    """直接往 `paper_fts` 插入一条不对应任何 `paper` 行的孤儿行，模拟索引漂移
    （不经过 CLI 进程——CLI 每次调用各自开关 DB 连接，故须在 CLI 调用之间以独立
    连接操作同一 db 文件）。
    """
    db = Database(home / "catalog.sqlite")
    db.execute(
        "INSERT INTO paper_fts(rowid, paper_id, title, abstract) VALUES (999, 'ghost', 'x', '')"
    )
    db.close()


# --- reindex（无 --check）：默认重建 ------------------------------------------------------------


def test_reindex_reports_rebuilt_row_count(tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    _seed_papers(home, [("10.0/a", "Paper A"), ("10.0/b", "Paper B")])

    result = runner.invoke(app, ["reindex", "--home", str(home)])

    assert result.exit_code == 0, result.output
    assert "重建 2 行" in result.output


def test_reindex_fixes_orphan_row(tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    _seed_papers(home, [("10.0/a", "Paper A")])
    _break_index_with_orphan_row(home)

    result = runner.invoke(app, ["reindex", "--home", str(home)])
    assert result.exit_code == 0, result.output

    check_result = runner.invoke(app, ["reindex", "--check", "--home", str(home)])
    assert check_result.exit_code == 0, check_result.output
    assert "一致，未发现问题" in check_result.output


def test_reindex_empty_library(tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    _seed_papers(home, [])

    result = runner.invoke(app, ["reindex", "--home", str(home)])

    assert result.exit_code == 0, result.output
    assert "重建 0 行" in result.output


# --- reindex --check：一致 ----------------------------------------------------------------------


def test_reindex_check_ok_when_in_sync(tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    _seed_papers(home, [("10.0/a", "Paper A"), ("10.0/b", "Paper B")])

    result = runner.invoke(app, ["reindex", "--check", "--home", str(home)])

    assert result.exit_code == 0, result.output
    assert "一致，未发现问题" in result.output
    assert "paper 行数: 2" in result.output
    assert "paper_fts 行数: 2" in result.output


# --- reindex --check：不一致三种漂移 -------------------------------------------------------------


def test_reindex_check_detects_orphan_row_and_exits_1(tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    _seed_papers(home, [("10.0/a", "Paper A")])
    _break_index_with_orphan_row(home)

    result = runner.invoke(app, ["reindex", "--check", "--home", str(home)])

    assert result.exit_code == 1
    assert "孤儿行样本" in result.output
    assert "ghost" in result.output
    assert "跑 `crawler reindex` 修复" in result.output


def test_reindex_check_detects_missing_index_and_exits_1(tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    _seed_papers(home, [("10.0/a", "Paper A")])
    db = Database(home / "catalog.sqlite")
    db.execute("DELETE FROM paper_fts")
    db.close()

    result = runner.invoke(app, ["reindex", "--check", "--home", str(home)])

    assert result.exit_code == 1
    assert "漏索引样本" in result.output


def test_reindex_check_reports_failed_integrity_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`integrity-check` 本身失败时 CLI 正确呈现"FAIL"文案（真实损坏难以在测试环境
    人为构造，经 monkeypatch 模拟——同 `test_repo.py` 的验证手法，此处只补 CLI 呈现面）。
    """
    home = _make_home(tmp_path)
    _seed_papers(home, [("10.0/a", "Paper A")])

    real_execute = Database.execute

    def _fake_execute(self: Database, sql: str, params: tuple[object, ...] = ()) -> None:
        if "integrity-check" in sql:
            raise sqlite3.DatabaseError("database disk image is malformed")
        real_execute(self, sql, params)

    monkeypatch.setattr(Database, "execute", _fake_execute)

    result = runner.invoke(app, ["reindex", "--check", "--home", str(home)])

    assert result.exit_code == 1
    assert "integrity-check: FAIL" in result.output
    assert "malformed" in result.output


def test_reindex_check_detects_duplicate_paper_id_and_exits_1(tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    _seed_papers(home, [("10.0/a", "Paper A")])
    db = Database(home / "catalog.sqlite")
    paper_id = str(db.query("SELECT id FROM paper")[0]["id"])
    db.execute(
        "INSERT INTO paper_fts(rowid, paper_id, title, abstract) VALUES (54321, ?, 'dup', '')",
        (paper_id,),
    )
    db.close()

    result = runner.invoke(app, ["reindex", "--check", "--home", str(home)])

    assert result.exit_code == 1
    assert "重复索引样本" in result.output


def test_reindex_check_detects_rowid_misalignment_and_exits_1(tmp_path: Path) -> None:
    """T12 独立审查 P1-1：`paper_fts` 全体 rowid 相对 `paper` 整体产生固定偏移
    （真实 VACUUM 坏态特征）——原 D-034 决策 5 三项对此坏态全部误报"一致"，须靠
    新增的 rowid 对齐项在 CLI 层面同样正确检出。
    """
    home = _make_home(tmp_path)
    _seed_papers(home, [("10.0/a", "Paper A"), ("10.0/b", "Paper B")])
    db = Database(home / "catalog.sqlite")
    db.execute("UPDATE paper_fts SET rowid = rowid + 100")
    db.close()

    result = runner.invoke(app, ["reindex", "--check", "--home", str(home)])

    assert result.exit_code == 1
    assert "rowid 错位样本" in result.output

    # reindex 修复后 --check 恢复一致。
    fix_result = runner.invoke(app, ["reindex", "--home", str(home)])
    assert fix_result.exit_code == 0, fix_result.output
    check_result = runner.invoke(app, ["reindex", "--check", "--home", str(home)])
    assert check_result.exit_code == 0, check_result.output


# --- paper_fts 表整体缺失（T12 独立审查 P2-3）-----------------------------------------------------


def test_reindex_missing_fts_table_exits_2_with_actionable_message(tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    _seed_papers(home, [("10.0/a", "Paper A")])
    db = Database(home / "catalog.sqlite")
    db.execute("DROP TABLE paper_fts")
    db.close()

    result = runner.invoke(app, ["reindex", "--home", str(home)])

    assert result.exit_code == 2
    assert "paper_fts" in result.output


def test_reindex_check_missing_fts_table_exits_2_with_actionable_message(tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    _seed_papers(home, [("10.0/a", "Paper A")])
    db = Database(home / "catalog.sqlite")
    db.execute("DROP TABLE paper_fts")
    db.close()

    result = runner.invoke(app, ["reindex", "--check", "--home", str(home)])

    assert result.exit_code == 2
    assert "paper_fts" in result.output
