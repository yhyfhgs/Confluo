"""迁移器与 schema v1 结构测试（phase1-plan Task 2；Refs: D-017, AC-1.1）。

覆盖：全表存在性对 DDL 清单断言、migrate 幂等、外键约束生效、不建 FTS5、
WAL/foreign_keys pragma、每步事务备份、tx 提交/回滚、语句切分器。
"""

from __future__ import annotations

import shutil
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from paper_crawler.storage import db as db_module
from paper_crawler.storage.db import Database, _iter_statements

_REAL_MIGRATIONS_DIR = Path(db_module.__file__).parent / "migrations"


def _staged_migrations_dir(tmp_path: Path, *names: str) -> Path:
    """把指定真实迁移文件拷进临时目录（保留原文件名，Python 步按文件名绑定才生效）。"""
    mig_dir = tmp_path / "migrations"
    mig_dir.mkdir(exist_ok=True)
    for name in names:
        shutil.copy(_REAL_MIGRATIONS_DIR / name, mig_dir / name)
    return mig_dir


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
    "idx_paper_title_norm",  # schema v2（0002_title_norm.sql，Phase 3 T1）
}

# 当前最新 schema 版本 = migrations/ 下迁移文件数。schema v2（Phase 3 T1）新增
# 0002_title_norm.sql（title_norm 列 + doi identifier 归一回填）。
LATEST_SCHEMA_VERSION = 2


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


def test_migrate_returns_latest_version(db: Database) -> None:
    assert db.migrate() == LATEST_SCHEMA_VERSION


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
    assert rows[0]["version"] == LATEST_SCHEMA_VERSION


def test_migrate_idempotent(db: Database) -> None:
    """连跑 2 次：版本不变、无异常、表不重复建。"""
    assert db.migrate() == LATEST_SCHEMA_VERSION
    tables_after_first = _table_names(db)
    assert db.migrate() == LATEST_SCHEMA_VERSION  # 第二次不报错、版本不变
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


def test_first_build_skips_backup_of_empty_v0(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """version 0 空库不备份（无 .v0.bak）。

    真实迁移目录含 0001+0002 后，一次全新建库跨 0→1→2：0→1 步（from_version=0）跳过备份，
    1→2 步（from_version=1>0）会对 v1 中间态备份——故断言"无 .v0.bak"而非"零 .bak"，精确
    锁定「初始空库不备份」这一规则（migrate() 的 `if current > 0` 分支）。
    """
    db_path = tmp_path / "app.sqlite"
    database = Database(db_path)
    assert database.migrate() == 2
    database.close()
    assert list(tmp_path.glob("*.v0.bak")) == []
    # 跨到 0002 时对 v1 中间态备份（from_version=1）。
    assert [p.name for p in tmp_path.glob("*.bak")] == ["app.sqlite.v1.bak"]


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


# -- schema v2（0002）v1→v2 自动升级 + Python 回填 -----------------------------


def _seed_v1(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Database:
    """建一个停在 v1 的库（仅应用 0001_init.sql）；MIGRATIONS_DIR 已被 monkeypatch。"""
    mig_dir = _staged_migrations_dir(tmp_path, "0001_init.sql")
    monkeypatch.setattr(db_module, "MIGRATIONS_DIR", mig_dir)
    database = Database(tmp_path / "app.sqlite")
    assert database.migrate() == 1
    database.execute(
        "INSERT INTO venue (id, kind, name, field_json) VALUES (?,?,?,?)",
        ("v", "journal", "V", "[]"),
    )
    return database


def _add_0002(tmp_path: Path) -> None:
    shutil.copy(_REAL_MIGRATIONS_DIR / "0002_title_norm.sql", tmp_path / "migrations")


def _insert_paper(database: Database, pid: str, title: str) -> None:
    database.execute(
        "INSERT INTO paper (id, title, ingest_state) VALUES (?,?,?)",
        (pid, title, "metadata_only"),
    )


def test_v1_to_v2_upgrade_backfills_title_norm(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """v1 存量 paper 行升级到 v2 时用 Python 步回填 title_norm（含 LaTeX/Unicode 归一）。"""
    database = _seed_v1(tmp_path, monkeypatch)
    _insert_paper(database, "p1", r"Erd\H{o}s--R\'enyi!")
    _insert_paper(database, "p2", "Café Society")

    _add_0002(tmp_path)
    assert database.migrate() == 2

    norms = {r["id"]: r["title_norm"] for r in database.query("SELECT id, title_norm FROM paper")}
    assert norms == {"p1": "erdos renyi", "p2": "cafe society"}
    idx = database.query(
        "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_paper_title_norm'"
    )
    assert len(idx) == 1
    database.close()


def _insert_doi(database: Database, paper_id: str, value: str, *, is_primary: int = 0) -> None:
    database.execute(
        "INSERT INTO identifier (paper_id, scheme, value, is_primary) VALUES (?,?,?,?)",
        (paper_id, "doi", value, is_primary),
    )


def test_v1_to_v2_normalizes_doi_identifier_in_place(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """存量 doi 大小写异形、无归一形冲突 → 就地归一（小写化），行不丢。"""
    database = _seed_v1(tmp_path, monkeypatch)
    _insert_paper(database, "p1", "Some Paper")
    _insert_doi(database, "p1", "10.1016/J.X")

    _add_0002(tmp_path)
    assert database.migrate() == 2

    ids = database.query("SELECT paper_id, value FROM identifier WHERE scheme='doi'")
    assert [(r["paper_id"], r["value"]) for r in ids] == [("p1", "10.1016/j.x")]
    database.close()


def test_v1_to_v2_doi_case_collision_cross_paper_builds_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """两 paper 各持同一 DOI 的大小写异形 → 留归一形行、删异形行、建 candidate 留人审。"""
    database = _seed_v1(tmp_path, monkeypatch)
    _insert_paper(database, "p_lower", "Same Work")
    _insert_paper(database, "p_upper", "Same Work WP")
    _insert_doi(database, "p_lower", "10.1/abc")  # 已归一形
    _insert_doi(database, "p_upper", "10.1/ABC")  # 异形，归一后碰撞

    _add_0002(tmp_path)
    assert database.migrate() == 2

    # 归一形行保留（指向 p_lower），异形行删除——不静默丢 paper。
    ids = database.query("SELECT paper_id, value FROM identifier WHERE scheme='doi'")
    assert [(r["paper_id"], r["value"]) for r in ids] == [("p_lower", "10.1/abc")]
    # 两 paper 行都在。
    papers = {r["id"] for r in database.query("SELECT id FROM paper")}
    assert {"p_lower", "p_upper"} <= papers
    # candidate_duplicate(decided=NULL, 中性 evidence 标签) 建成，端点按 id 升序。
    rel = database.query("SELECT * FROM paper_relation WHERE kind='candidate_duplicate'")
    assert len(rel) == 1
    assert rel[0]["decided"] is None
    assert {rel[0]["from_paper"], rel[0]["to_paper"]} == {"p_lower", "p_upper"}
    assert "doi-normalization-collision" in rel[0]["evidence_json"]
    database.close()


def test_v1_to_v2_doi_prefix_collision_uses_neutral_label(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """前缀异形（非纯大小写）碰撞同样走中性标签 doi-normalization-collision（名副其实）。"""
    database = _seed_v1(tmp_path, monkeypatch)
    _insert_paper(database, "p_bare", "Work")
    _insert_paper(database, "p_url", "Work Preprint")
    _insert_doi(database, "p_bare", "10.1/abc")  # 已归一形
    _insert_doi(database, "p_url", "https://doi.org/10.1/abc")  # 前缀异形，归一后碰撞

    _add_0002(tmp_path)
    assert database.migrate() == 2

    ids = database.query("SELECT paper_id, value FROM identifier WHERE scheme='doi'")
    assert [(r["paper_id"], r["value"]) for r in ids] == [("p_bare", "10.1/abc")]
    rel = database.query("SELECT * FROM paper_relation WHERE kind='candidate_duplicate'")
    assert len(rel) == 1
    assert "doi-normalization-collision" in rel[0]["evidence_json"]
    database.close()


def test_v1_to_v2_doi_collision_restores_primary_when_deleted_row_was_primary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """碰撞删除的异形行若为 primary → 保留的归一行提为 primary（补单一 primary 不变量）。"""
    database = _seed_v1(tmp_path, monkeypatch)
    _insert_paper(database, "p1", "Some Paper")
    _insert_doi(database, "p1", "10.1/abc", is_primary=0)  # 归一形，非 primary
    _insert_doi(database, "p1", "10.1/ABC", is_primary=1)  # 异形，恰为 primary → 将被删

    _add_0002(tmp_path)
    assert database.migrate() == 2

    ids = database.query("SELECT value, is_primary FROM identifier WHERE scheme='doi'")
    assert [(r["value"], r["is_primary"]) for r in ids] == [("10.1/abc", 1)]  # 保留行提为 primary
    database.close()


def test_v1_to_v2_doi_case_collision_same_paper_drops_redundant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """同一 paper 上异形冗余 doi → 删冗余行、不建 candidate；归一行本就是 primary 则原样保留。"""
    database = _seed_v1(tmp_path, monkeypatch)
    _insert_paper(database, "p1", "Some Paper")
    _insert_doi(database, "p1", "10.1/abc", is_primary=1)  # 归一形本就是 primary
    _insert_doi(database, "p1", "10.1/ABC", is_primary=0)  # 异形冗余，非 primary → 将被删

    _add_0002(tmp_path)
    assert database.migrate() == 2

    ids = database.query("SELECT paper_id, value, is_primary FROM identifier WHERE scheme='doi'")
    # 删非 primary 异形后 paper 仍有 primary → 不重复提升，归一行原样保留其 primary。
    assert [(r["paper_id"], r["value"], r["is_primary"]) for r in ids] == [("p1", "10.1/abc", 1)]
    assert database.query("SELECT COUNT(*) AS n FROM paper_relation")[0]["n"] == 0
    database.close()
