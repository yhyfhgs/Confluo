"""迁移器与 schema v1 结构测试（phase1-plan Task 2；Refs: D-017, AC-1.1）。

覆盖：全表存在性对 DDL 清单断言、migrate 幂等、外键约束生效、不建 FTS5、
WAL/foreign_keys pragma、每步事务备份、tx 提交/回滚、语句切分器。
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from paper_crawler.storage import db as db_module
from paper_crawler.storage.db import Database, _iter_statements

# schema v1 全表清单（design/06 §2 十二张 + plan §2.4 补三张 + schema_version）。
EXPECTED_TABLES = {
    "venue",
    "venue_era",
    "issue",
    "paper",
    "identifier",
    "asset",
    "author",
    "authorship",
    "paper_relation",
    "fulltext",
    "subscription",
    "subscription_run",
    "paper_issue_link",
    "task",
    "fetch_log",
    "schema_version",
}

EXPECTED_INDEXES = {
    "idx_task_active_idem",
    "idx_task_state_kind",
    "idx_fetch_log_domain_ts",
    "idx_asset_state",
}


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Database]:
    database = Database(tmp_path / "test.sqlite")
    yield database
    database.close()


def _table_names(database: Database) -> set[str]:
    rows = database.query("SELECT name FROM sqlite_master WHERE type='table'")
    return {r["name"] for r in rows}


def _index_names(database: Database) -> set[str]:
    rows = database.query("SELECT name FROM sqlite_master WHERE type='index'")
    return {r["name"] for r in rows}


# -- 建表与版本 --------------------------------------------------------------


def test_migrate_returns_version_one(db: Database) -> None:
    assert db.migrate() == 1


def test_migrate_creates_all_tables(db: Database) -> None:
    db.migrate()
    assert EXPECTED_TABLES <= _table_names(db)


def test_migrate_creates_expected_indexes(db: Database) -> None:
    db.migrate()
    assert EXPECTED_INDEXES <= _index_names(db)


def test_schema_version_single_row(db: Database) -> None:
    db.migrate()
    rows = db.query("SELECT version FROM schema_version")
    assert len(rows) == 1
    assert rows[0]["version"] == 1


def test_migrate_idempotent(db: Database) -> None:
    """连跑 2 次：版本不变、无异常、表不重复建。"""
    assert db.migrate() == 1
    tables_after_first = _table_names(db)
    assert db.migrate() == 1  # 第二次不报错、版本不变
    assert _table_names(db) == tables_after_first


def test_partial_unique_index_on_task_is_present(db: Database) -> None:
    """活跃任务幂等键为部分唯一索引（带 WHERE），非 SQLite 专有特性。"""
    db.migrate()
    row = db.query(
        "SELECT sql FROM sqlite_master WHERE type='index' AND name='idx_task_active_idem'"
    )[0]
    assert "WHERE" in row["sql"].upper()
    assert "PENDING" in row["sql"] and "RUNNING" in row["sql"]


# -- 方言中性 / 无 FTS5 ------------------------------------------------------


def test_no_fts5_virtual_table(db: Database) -> None:
    """D-017：Phase 1 不建 FTS5。断言无任何 fts 虚表。"""
    db.migrate()
    rows = db.query("SELECT sql FROM sqlite_master WHERE sql IS NOT NULL")
    joined = " ".join((r["sql"] or "").lower() for r in rows)
    assert "fts5" not in joined
    assert "virtual table" not in joined


# -- 连接层 pragma -----------------------------------------------------------


def test_wal_mode_enabled(db: Database) -> None:
    assert db.query("PRAGMA journal_mode")[0][0].lower() == "wal"


def test_foreign_keys_pragma_on(db: Database) -> None:
    assert db.query("PRAGMA foreign_keys")[0][0] == 1


# -- 外键约束生效 ------------------------------------------------------------


def test_foreign_key_orphan_issue_rejected(db: Database) -> None:
    """issue.venue_id 指向不存在的 venue → IntegrityError。"""
    db.migrate()
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO issue (id, venue_id, source) VALUES (?,?,?)",
            ("i1", "ghost_venue", "mock"),
        )


def test_foreign_key_orphan_identifier_rejected(db: Database) -> None:
    """identifier.paper_id 指向不存在的 paper → IntegrityError。"""
    db.migrate()
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO identifier (paper_id, scheme, value) VALUES (?,?,?)",
            ("ghost_paper", "doi", "10.x/1"),
        )


# -- 迁移备份（每步事务 + 文件 copy） ----------------------------------------


def _write_migration(dir_: Path, name: str, body: str) -> None:
    (dir_ / name).write_text(body, encoding="utf-8")


def test_first_build_skips_backup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """首次建库（version 0→1）不产生备份文件。"""
    db_path = tmp_path / "app.sqlite"
    database = Database(db_path)
    database.migrate()
    database.close()
    assert list(tmp_path.glob("*.bak")) == []


def test_second_migration_creates_backup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """存在既有 schema 时，应用下一步迁移前 copy 备份 db 文件。"""
    mig_dir = tmp_path / "migrations"
    mig_dir.mkdir()
    _write_migration(
        mig_dir,
        "0001_a.sql",
        "CREATE TABLE schema_version (version INTEGER NOT NULL);\n"
        "CREATE TABLE t1 (id TEXT PRIMARY KEY);",
    )
    _write_migration(mig_dir, "0002_b.sql", "CREATE TABLE t2 (id TEXT PRIMARY KEY);")
    monkeypatch.setattr(db_module, "MIGRATIONS_DIR", mig_dir)

    db_path = tmp_path / "app.sqlite"
    database = Database(db_path)
    final = database.migrate()
    database.close()

    assert final == 2
    backups = list(tmp_path.glob("*.v1.bak"))
    assert len(backups) == 1, "应用 0002 前应对 v1 状态做一次备份"


def test_migrate_applies_only_pending(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """已在 v1，新增 0002 后再 migrate 只应用 0002（不重跑 0001）。"""
    mig_dir = tmp_path / "migrations"
    mig_dir.mkdir()
    _write_migration(
        mig_dir,
        "0001_a.sql",
        "CREATE TABLE schema_version (version INTEGER NOT NULL);\n"
        "CREATE TABLE t1 (id TEXT PRIMARY KEY);",
    )
    monkeypatch.setattr(db_module, "MIGRATIONS_DIR", mig_dir)

    db_path = tmp_path / "app.sqlite"
    database = Database(db_path)
    assert database.migrate() == 1

    _write_migration(mig_dir, "0002_b.sql", "CREATE TABLE t2 (id TEXT PRIMARY KEY);")
    assert database.migrate() == 2  # 只应用 0002；若重跑 0001 会因 t1 已存在而报错
    database.close()


def test_migration_step_is_atomic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """迁移脚本中途失败 → 整步回滚，版本不前进。"""
    mig_dir = tmp_path / "migrations"
    mig_dir.mkdir()
    _write_migration(
        mig_dir,
        "0001_a.sql",
        "CREATE TABLE schema_version (version INTEGER NOT NULL);\n"
        "CREATE TABLE ok1 (id TEXT PRIMARY KEY);\n"
        "CREATE TABLE ok1 (id TEXT PRIMARY KEY);",  # 重复建表 → 报错
    )
    monkeypatch.setattr(db_module, "MIGRATIONS_DIR", mig_dir)

    database = Database(tmp_path / "app.sqlite")
    with pytest.raises(sqlite3.OperationalError):
        database.migrate()
    # 回滚后：schema_version 表本身也在同一失败事务内 → 版本仍为 0。
    assert database._current_version() == 0
    database.close()


# -- 事务上下文 --------------------------------------------------------------


def test_tx_commits_on_success(db: Database) -> None:
    db.migrate()
    with db.tx() as conn:
        conn.execute(
            "INSERT INTO venue (id, kind, name, field_json) VALUES (?,?,?,?)",
            ("v1", "journal", "V1", "[]"),
        )
    assert db.query("SELECT id FROM venue")[0]["id"] == "v1"


def test_tx_rolls_back_on_error(db: Database) -> None:
    db.migrate()
    with pytest.raises(RuntimeError):
        with db.tx() as conn:
            conn.execute(
                "INSERT INTO venue (id, kind, name, field_json) VALUES (?,?,?,?)",
                ("v2", "journal", "V2", "[]"),
            )
            raise RuntimeError("boom")
    assert db.query("SELECT id FROM venue WHERE id='v2'") == []


def test_close_releases_connection(tmp_path: Path) -> None:
    database = Database(tmp_path / "c.sqlite")
    database.migrate()
    database.close()
    with pytest.raises(sqlite3.ProgrammingError):
        database.query("SELECT 1")


# -- 语句切分器 --------------------------------------------------------------


def test_iter_statements_splits_on_semicolons() -> None:
    stmts = list(_iter_statements("CREATE TABLE a (x TEXT); CREATE TABLE b (y TEXT);"))
    assert stmts == ["CREATE TABLE a (x TEXT)", "CREATE TABLE b (y TEXT)"]


def test_iter_statements_ignores_semicolon_in_string() -> None:
    stmts = list(_iter_statements("INSERT INTO t VALUES ('a;b'); SELECT 1;"))
    assert stmts == ["INSERT INTO t VALUES ('a;b')", "SELECT 1"]


def test_iter_statements_handles_escaped_quote() -> None:
    stmts = list(_iter_statements("INSERT INTO t VALUES ('it''s; ok');"))
    assert stmts == ["INSERT INTO t VALUES ('it''s; ok')"]


def test_iter_statements_drops_line_comments() -> None:
    script = "-- a comment; with semicolon\nCREATE TABLE a (x TEXT);\n-- trailing\n"
    assert list(_iter_statements(script)) == ["CREATE TABLE a (x TEXT)"]


def test_iter_statements_skips_empty_between_semicolons() -> None:
    assert list(_iter_statements("SELECT 1;; SELECT 2;")) == ["SELECT 1", "SELECT 2"]


def test_iter_statements_yields_tail_without_trailing_semicolon() -> None:
    assert list(_iter_statements("SELECT 1")) == ["SELECT 1"]


def test_migrate_ignores_non_numeric_sql_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """迁移目录中非数字前缀的 .sql（如 notes.sql）被忽略。"""
    mig_dir = tmp_path / "migrations"
    mig_dir.mkdir()
    _write_migration(
        mig_dir,
        "0001_a.sql",
        "CREATE TABLE schema_version (version INTEGER NOT NULL);\n"
        "CREATE TABLE t1 (id TEXT PRIMARY KEY);",
    )
    _write_migration(mig_dir, "notes.sql", "CREATE TABLE ignored (id TEXT PRIMARY KEY);")
    monkeypatch.setattr(db_module, "MIGRATIONS_DIR", mig_dir)

    database = Database(tmp_path / "app.sqlite")
    assert database.migrate() == 1
    assert "ignored" not in _table_names(database)
    database.close()
