"""迁移器与 schema v1 结构测试（phase1-plan Task 2；Refs: D-017, AC-1.1）。

覆盖：全表存在性对 DDL 清单断言、migrate 幂等、外键约束生效、不建 FTS5、
WAL/foreign_keys pragma、每步事务备份、tx 提交/回滚、语句切分器。

连接关闭纪律（post-phase5-audit §3[S4]/§6 处置 4）：`db` fixture 经 pytest 的
yield-teardown 保证关闭（正常/异常任一路径都会跑到 `yield` 之后的 `database.close()`），
本就健壮；本文件内**手工构造** `Database` 的用例一律改用 `contextlib.closing` 包裹
（而非"构造 - 操作 - 末尾手写 `.close()`"的旧模式）——旧模式下若包裹体内任何一条
`assert`/迁移调用先于 `.close()` 抛出，连接就不会被关闭，须手工在每个未来新增用例里
记得补 `.close()`，且改动前的写法在 `-W error::ResourceWarning` 下也确实测不出问题
（改前/改后隔离单跑本文件均为 0 条——CPython 引用计数在这种简单场景下够快，等不到
gc 分代阈值触发就已经同步析构）；`closing()` 经 `__exit__` 保证无论体内正常返回还是
异常都调用 `.close()`，是结构性更稳的写法，不依赖"顺序写对了"这种脆弱前提。

★核查记录：全量 `make check`（`tests/unit`+`tests/contract`+`tests/integration` 一起跑）
下确有 27 条 `ResourceWarning: unclosed database`（post-phase5-audit §3[S4] 原始发现），
但本次改造后实测该数字不变——进一步隔离定位（`--ignore`/仅跑子目录组合）证实这 27 条
并不集中于本文件：`tests/unit` 单独跑、`tests/unit`+`tests/contract`、`tests/unit`+
`tests/integration` 三种组合下均为 0 条，只有三者全部一起跑时才出现，指向与本文件
无关的全库级 gc 分代阈值效应（`sqlite3.Connection.__del__` 在对象参与引用环时的析构
时机取决于累计分配量触发的 gc 扫描，警告信息里的文件:行号只是扫描发生时恰好在执行
的代码，不是泄漏的真实来源）。该发现已作为独立事项上报，不在本文件修复范围内。
"""

from __future__ import annotations

import re
import shutil
import sqlite3
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path

import pytest

from paper_crawler.errors import CrawlerError, ErrorClass
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
    "paper_weak_key",  # schema v3（0003_paper_weak_key.sql，Phase 6 F1）
    "paper_fts",  # schema v5（0005_fts_paper.sql，Phase 7 T12，D-034）—— FTS5 虚表
}

EXPECTED_INDEXES = {
    "idx_task_active_idem",
    "idx_task_state_kind",
    "idx_fetch_log_domain_ts",
    "idx_asset_state",
    "idx_paper_title_norm",  # schema v2（0002_title_norm.sql，Phase 3 T1）
    "idx_paper_weak_key_lookup",  # schema v3（0003_paper_weak_key.sql，Phase 6 F1）
}

# 当前最新 schema 版本 = migrations/ 下迁移文件数。schema v2（Phase 3 T1）新增
# 0002_title_norm.sql（title_norm 列 + doi identifier 归一回填）；schema v3（Phase 6 F1）新增
# 0003_paper_weak_key.sql（观测级弱信号键倒排表 + 存量回填）；schema v4（Phase 7 T7，D-033）
# 新增 0004_fulltext_asset.sql（fulltext 表 asset 级幂等键五列 + 存量 noop 回填）；schema v5
# （Phase 7 T12，D-034）新增 0005_fts_paper.sql（paper_fts FTS5 虚表 + 三触发器 + 存量回填）。
#
# **rebase 合并注记（T12 独立审查 P2-2，如实记录）**：T7 与 T12 各自独立分支开发时把本行
# 从 3 分别改到 4、5——rebase 时是同一行的常规 git 冲突，已手工解为 5（终态版本号，非
# 两处改动相加）。真正需要留意的是"P2-2 静默转红"陷阱（见
# `test_first_build_skips_backup_of_empty_v0` 内的完整记述）：本常量的改动 git 能正确
# 识别为冲突并要求手工解决，但两支各自往 `.bak` 清单加同一行文本时 git 判定为无冲突、
# 自动合并，实际却因五步迁移链多出一个中间态而需要额外手改。
LATEST_SCHEMA_VERSION = 5


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


# -- 方言中性 / FTS5 限于 paper_fts（D-034 修订 D-017 决策 4）-----------------------


def test_fts5_confined_to_paper_fts_virtual_table(db: Database) -> None:
    """D-034（修订 D-017 决策 4）：FTS5 不再全面禁用，但**限于** `0005_fts_paper.sql`
    建的 `paper_fts` 单表——0001-0003（及未来 0004，T7）保持方言中性不变。原
    `test_no_fts5_virtual_table`（D-017 原始"零 FTS5"断言）已被 D-034 修订取代，
    改断言"仅此一处、别无分店"，延续原测试"方言隔离"的检查意图。
    """
    db.migrate()
    rows = db.query(
        "SELECT name, sql FROM sqlite_master WHERE sql IS NOT NULL AND type != 'trigger'"
    )
    fts_tables = [r["name"] for r in rows if "fts5" in (r["sql"] or "").lower()]
    assert fts_tables == ["paper_fts"]
    other_sql = " ".join((r["sql"] or "").lower() for r in rows if r["name"] != "paper_fts")
    assert "fts5" not in other_sql
    assert "virtual table" not in other_sql


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

    真实迁移目录含 0001+0002+0003+0004+0005 后，一次全新建库跨 0→1→2→3→4→5：0→1 步
    （from_version=0）跳过备份，其后每步（from_version>0）会对中间态备份——故断言
    "无 .v0.bak"而非"零 .bak"，精确锁定「初始空库不备份」这一规则（migrate() 的
    `if current > 0` 分支）。

    **rebase 静默转红提醒（T12 独立审查 P2-2，如实记录）**：T7（0004_fulltext_asset.sql）
    与 T12（本文件，0005_fts_paper.sql）各自独立分支开发期间，都把本用例的 `.bak`
    清单从两项（v1/v2）加到三项（v1/v2/v3）——两支修改文本恰好逐字相同，git rebase/
    merge 时不会报冲突，但两支合流后真实迁移链变成五步（1→2→3→4→5），实际会在
    v1/v2/v3/v4 四个中间态各备份一次，第四项 `v4.bak` 因"两支都不知道对方也加了
    一项"而被双方独立版本共同遗漏——merge 完全静默、测试却会转红。本次 rebase 已
    据此手工把清单改为四项（而非依赖 git 自动合并的三项）。
    """
    db_path = tmp_path / "app.sqlite"
    with closing(Database(db_path)) as database:
        assert database.migrate() == LATEST_SCHEMA_VERSION
    assert list(tmp_path.glob("*.v0.bak")) == []
    # 跨到 0002/0003/0004/0005 时分别对 v1/v2/v3/v4 中间态备份（from_version=1/2/3/4）。
    assert sorted(p.name for p in tmp_path.glob("*.bak")) == [
        "app.sqlite.v1.bak",
        "app.sqlite.v2.bak",
        "app.sqlite.v3.bak",
        "app.sqlite.v4.bak",
    ]


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
    with closing(Database(db_path)) as database:
        final = database.migrate()

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
    with closing(Database(db_path)) as database:
        assert database.migrate() == 1

        _write_migration(mig_dir, "0002_b.sql", "CREATE TABLE t2 (id TEXT PRIMARY KEY);")
        assert database.migrate() == 2  # 只应用 0002；若重跑 0001 会因 t1 已存在而报错


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

    with closing(Database(tmp_path / "app.sqlite")) as database:
        with pytest.raises(sqlite3.OperationalError):
            database.migrate()
        # 回滚后：schema_version 表本身也在同一失败事务内 → 版本仍为 0。
        assert database._current_version() == 0


def test_apply_rolls_back_and_reraises_non_operational_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`_apply` 的通用 `except Exception` 分支（T12 新增 `sqlite3.OperationalError`
    专属分支之外的兜底）：Python 后置步（`_PY_MIGRATIONS`）抛出的非 `OperationalError`
    异常同样整步回滚、原样上抛——不被 FTS5 专属分支误吞（二者是互斥的 except 子句）。
    """
    mig_dir = tmp_path / "migrations"
    mig_dir.mkdir()
    _write_migration(
        mig_dir,
        "0001_a.sql",
        "CREATE TABLE schema_version (version INTEGER NOT NULL);\n"
        "CREATE TABLE t1 (id TEXT PRIMARY KEY);",
    )
    monkeypatch.setattr(db_module, "MIGRATIONS_DIR", mig_dir)

    def _boom(conn: sqlite3.Connection) -> None:
        raise RuntimeError("boom")

    monkeypatch.setitem(db_module._PY_MIGRATIONS, "0001_a.sql", _boom)

    with closing(Database(tmp_path / "app.sqlite")) as database:
        with pytest.raises(RuntimeError, match="boom"):
            database.migrate()
        assert database._current_version() == 0


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
    with closing(Database(tmp_path / "c.sqlite")) as database:
        database.migrate()
    # `with` 块退出时 `closing()` 已调用 `database.close()`——此处验证关闭后果
    # （后续操作报 ProgrammingError），不是本用例需要额外手工 close 的信号。
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


# -- 语句切分器：CREATE TRIGGER … BEGIN … END 复合语句块（D-034，T12）----------------
#
# D-034 决策 4（改口记录）：本切分器原逐 `;` 断句，docstring 自述"迁移 DDL 不含触发器/
# 复合语句"——`0005_fts_paper.sql`（paper_fts 三触发器）证伪该假设，本卡扩展切分器识别
# `BEGIN…END` 块（块内 `;` 不断句，`END` 之后的 `;` 才收尾），使 SQLite 语法上的单一
# `CREATE TRIGGER … END` 语句原样整条喂给 `sqlite3.Cursor.execute()`（该 API 只接受单条
# 语句；`executescript` 因隐式 COMMIT 破坏 `_apply` 手动事务边界，不得使用，见 db.py
# `_iter_statements` docstring）。


def test_iter_statements_keeps_trigger_body_semicolons_together() -> None:
    """单个 CREATE TRIGGER 的 BEGIN…END 内两条子语句的 `;` 不断句——整体只产出一条语句。"""
    script = (
        "CREATE TRIGGER t_ai AFTER INSERT ON paper BEGIN\n"
        "  INSERT INTO paper_fts(rowid, paper_id) VALUES (new.rowid, new.id);\n"
        "  UPDATE paper SET updated_at = new.updated_at WHERE id = new.id;\n"
        "END;"
    )
    stmts = list(_iter_statements(script))
    assert len(stmts) == 1
    assert stmts[0] == (
        "CREATE TRIGGER t_ai AFTER INSERT ON paper BEGIN\n"
        "  INSERT INTO paper_fts(rowid, paper_id) VALUES (new.rowid, new.id);\n"
        "  UPDATE paper SET updated_at = new.updated_at WHERE id = new.id;\n"
        "END"
    )


def test_iter_statements_splits_multiple_triggers_in_sequence() -> None:
    """多个 CREATE TRIGGER 连排（`0005_fts_paper.sql` 实况：ai/au/ad 三触发器紧挨）
    ——各自独立成句，`END;` 正确收尾并让下一个 `CREATE TRIGGER` 开新句。"""
    script = (
        "CREATE TRIGGER t_ai AFTER INSERT ON paper BEGIN\n"
        "  INSERT INTO paper_fts(rowid, paper_id) VALUES (new.rowid, new.id);\n"
        "END;\n"
        "CREATE TRIGGER t_au AFTER UPDATE OF title ON paper BEGIN\n"
        "  DELETE FROM paper_fts WHERE rowid = old.rowid AND paper_id = old.id;\n"
        "  INSERT INTO paper_fts(rowid, paper_id) VALUES (new.rowid, new.id);\n"
        "END;\n"
        "CREATE TRIGGER t_ad AFTER DELETE ON paper BEGIN\n"
        "  DELETE FROM paper_fts WHERE rowid = old.rowid AND paper_id = old.id;\n"
        "END;\n"
        "INSERT INTO paper_fts(rowid, paper_id) SELECT rowid, id FROM paper;"
    )
    stmts = list(_iter_statements(script))
    assert len(stmts) == 4
    assert stmts[0].startswith("CREATE TRIGGER t_ai") and stmts[0].endswith("END")
    assert stmts[1].startswith("CREATE TRIGGER t_au") and stmts[1].endswith("END")
    assert stmts[2].startswith("CREATE TRIGGER t_ad") and stmts[2].endswith("END")
    assert stmts[3] == "INSERT INTO paper_fts(rowid, paper_id) SELECT rowid, id FROM paper"


def test_iter_statements_trigger_body_string_containing_semicolon() -> None:
    """触发器体内字符串字面量含 `;` 不误断句（字符串识别与 BEGIN…END 识别正交组合）。"""
    script = (
        "CREATE TRIGGER t_ai AFTER INSERT ON paper BEGIN\n"
        "  INSERT INTO paper_fts(rowid, paper_id, title) "
        "VALUES (new.rowid, new.id, 'a;b');\n"
        "END;"
    )
    stmts = list(_iter_statements(script))
    assert len(stmts) == 1
    assert "'a;b'" in stmts[0]
    assert stmts[0].endswith("END")


def test_iter_statements_nested_begin_end_tracks_depth() -> None:
    """嵌套 `BEGIN…BEGIN…END…END`（合成用例，锁定计数器按深度而非布尔标志实现）：
    内层 `END` 只把深度降到 1，其后的 `;` 仍不断句；外层 `END;` 深度降到 0 才收尾。"""
    script = "CREATE TRIGGER t AFTER INSERT ON paper BEGIN BEGIN SELECT 1; END; END;"
    stmts = list(_iter_statements(script))
    assert stmts == ["CREATE TRIGGER t AFTER INSERT ON paper BEGIN BEGIN SELECT 1; END; END"]


def test_iter_statements_bare_end_outside_trigger_is_ordinary_text() -> None:
    """`trigger_depth` 钳制在 0：深度已为 0 时遇到孤立 `END`（如 CASE 表达式）不会让
    计数器变负、不影响后续 `;` 的正常断句语义（本项目现有迁移脚本均无此用法，
    属防御性钳制，非本次扩展的功能目标）。"""
    script = "SELECT CASE WHEN 1 THEN 2 ELSE 3 END; SELECT 1;"
    stmts = list(_iter_statements(script))
    assert stmts == ["SELECT CASE WHEN 1 THEN 2 ELSE 3 END", "SELECT 1"]


def test_iter_statements_begin_end_case_insensitive() -> None:
    """`begin`/`end` 关键字大小写不敏感（SQL 关键字惯例），与 SQLite 自身解析行为一致。"""
    script = "create trigger t after insert on paper begin select 1; end;"
    stmts = list(_iter_statements(script))
    assert stmts == ["create trigger t after insert on paper begin select 1; end"]


def test_iter_statements_does_not_match_identifier_substrings() -> None:
    """`BEGIN`/`END` 必须整词匹配——标识符子串（如 `beginning_date`/`ending_date`）
    不得被误判为关键字（否则会错误改变 `trigger_depth`，进而错误影响断句）。"""
    script = "CREATE TABLE t (beginning_date TEXT, ending_date TEXT); SELECT 1;"
    stmts = list(_iter_statements(script))
    assert stmts == [
        "CREATE TABLE t (beginning_date TEXT, ending_date TEXT)",
        "SELECT 1",
    ]


def test_iter_statements_does_not_match_when_preceded_by_identifier_char() -> None:
    """`_keyword_at` 的"前一字符不是标识符字符"分支——`beginning_date` 覆盖了"后一
    字符非标识符"分支（见上一用例），本用例专门覆盖"前一字符非标识符"分支的反面：
    `BEGIN`/`END` 紧跟在字母/数字/下划线之后（如 `xBEGIN`）同样不得误判。
    """
    script = "SELECT xBEGIN, xEND FROM t;"
    stmts = list(_iter_statements(script))
    assert stmts == ["SELECT xBEGIN, xEND FROM t"]


# -- 已知未覆盖边界的特征测试（T12 独立审查 P2-1，如实记录当前行为，非"须修复的
# 缺陷"——见 `_iter_statements` docstring"已知未覆盖边界"一节的完整论证；三点在
# 本项目现有全部迁移文件中均未出现，测试目的是让文档断言可验证、不是纸面假设）---


def test_iter_statements_case_end_inside_trigger_body_mis_splits_loudly() -> None:
    """已知边界 1：触发器体内出现 `CASE … END`（而非本卡三触发器的简单 DML）会被
    误判为触发器自身的收尾，切成两段——响亮失败（两段单独喂给 `execute()` 均非
    合法独立语句），而非静默错误。
    """
    script = (
        "CREATE TRIGGER t AFTER INSERT ON paper BEGIN\n"
        "  UPDATE paper SET x = CASE WHEN new.y > 0 THEN 1 ELSE 0 END WHERE id = new.id;\n"
        "END;"
    )
    stmts = list(_iter_statements(script))
    # 被切成两段（而非 1 段完整触发器）——`END` 被 CASE 表达式的 END 提前吃掉。
    assert len(stmts) == 2
    assert stmts[1] == "END"
    assert not stmts[0].rstrip().endswith("END")  # 第一段缺失真正的触发器收尾


def test_iter_statements_begin_inside_block_comment_swallows_rest_of_script() -> None:
    """已知边界 2：`/* … */` 块注释未被识别，注释内的 `BEGIN` 被误判为真实关键字；
    脚本此后再无真实 `END` 与之配平时，`trigger_depth` 卡在 >0 直到脚本结尾——
    整个脚本被粘成一条"语句"（而非局部影响），响亮失败发生在喂给
    `sqlite3.Cursor.execute()` 时（多语句拼一条会被拒绝），非本测试断言范围。
    """
    script = "/* explanation of BEGIN keyword */\nCREATE TABLE t (x TEXT);\nSELECT 1;"
    stmts = list(_iter_statements(script))
    assert len(stmts) == 1  # 未按 `;` 断句——整个脚本粘成一条
    assert "SELECT 1" in stmts[0]


def test_iter_statements_bracket_quoted_begin_identifier_swallows_rest_of_script() -> None:
    """已知边界 3：`[begin]` 方括号标识符未被识别，`begin` 前后恰为 `[`/`]`
    （非标识符字符）而被判定为真实关键字；后果同边界 2——无配平 `END` 时波及
    脚本剩余全部内容。
    """
    script = "CREATE TABLE t ([begin] TEXT); SELECT 1;"
    stmts = list(_iter_statements(script))
    assert len(stmts) == 1
    assert "SELECT 1" in stmts[0]


# -- 回归锁定：既有 0001-0003 迁移文件的切分结果逐字不变 -----------------------------


def _iter_statements_pre_t12(script: str) -> Iterator[str]:
    """T12（D-034）扩展前 `_iter_statements` 的逐字冻结副本——仅识别单引号字符串与
    `--` 行注释，不识别 `BEGIN…END`。回归锁定专用：既有 0001-0003 三个迁移文件均不含
    `BEGIN`/`END` 关键字（已核实），故扩展后的切分结果理应与本副本逐字相同；用真实
    历史实现比对，比手抄一份 golden 输出/哈希值更不容易出现誊抄失误。
    """
    stmt: list[str] = []
    in_string = False
    in_comment = False
    i, n = 0, len(script)
    while i < n:
        ch = script[i]
        nxt = script[i + 1] if i + 1 < n else ""
        if in_comment:
            if ch == "\n":
                in_comment = False
            i += 1
            continue
        if in_string:
            stmt.append(ch)
            if ch == "'":
                if nxt == "'":
                    stmt.append(nxt)
                    i += 2
                    continue
                in_string = False
            i += 1
            continue
        if ch == "-" and nxt == "-":
            in_comment = True
            i += 2
            continue
        if ch == "'":
            in_string = True
            stmt.append(ch)
            i += 1
            continue
        if ch == ";":
            candidate = "".join(stmt).strip()
            if candidate:
                yield candidate
            stmt = []
            i += 1
            continue
        stmt.append(ch)
        i += 1
    tail = "".join(stmt).strip()
    if tail:
        yield tail


@pytest.mark.parametrize(
    "name",
    [
        "0001_init.sql",
        "0002_title_norm.sql",
        "0003_paper_weak_key.sql",
        # T7 的 0004（Phase 7，独立分支，rebase 后并入）——T12 独立审查 P2-2 已核实其
        # 五条 ALTER TABLE + 一条 UPDATE 不含整词 BEGIN/END（见下方断言的运行时核验），
        # 可安全并入同一回归锁定网；0005（本卡自身）含真实触发器，不适用本"未扩展前后
        # 应逐字相同"断言，故不纳入本参数化列表。
        "0004_fulltext_asset.sql",
    ],
)
def test_iter_statements_0001_to_0004_unchanged_by_trigger_extension(name: str) -> None:
    """既有四个迁移文件（0001-0004）均不含整词 `BEGIN`/`END`，扩展后的切分结果须与
    扩展前逐字相同。

    整词（`\\b…\\b`）匹配而非子串检查——`PENDING`/`RUNNING`（0001 的 task.state 默认值/
    部分索引 WHERE 子句）子串含 `end`，子串检查会误判；扩展后的 `_iter_statements` 本身
    也是整词匹配（`_keyword_at`），故此处用同等严格度的前提校验才有意义。
    """
    text = (_REAL_MIGRATIONS_DIR / name).read_text(encoding="utf-8")
    assert not re.search(r"(?i)\b(begin|end)\b", text), (
        f"{name} 意外含整词 BEGIN/END 关键字——回归锁定假设失效，需人工复核"
    )
    assert list(_iter_statements(text)) == list(_iter_statements_pre_t12(text))


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

    with closing(Database(tmp_path / "app.sqlite")) as database:
        assert database.migrate() == 1
        assert "ignored" not in _table_names(database)


# -- schema v2（0002）v1→v2 自动升级 + Python 回填 -----------------------------


def _seed_v1(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Database:
    """建一个停在 v1 的库（仅应用 0001_init.sql）；MIGRATIONS_DIR 已被 monkeypatch。

    返回一个**未关闭**的 `Database`——按约定调用方须用 `contextlib.closing` 包裹
    （本文件模块 docstring"连接关闭纪律"一节）。构造后的首次 migrate/seed 写入本身
    也兜一层：万一在 `return` 之前就失败，调用方根本拿不到对象、也就没机会经
    `closing()` 兜底，此处必须自行关闭后再原样重新抛出，避免半途连接泄漏。
    """
    mig_dir = _staged_migrations_dir(tmp_path, "0001_init.sql")
    monkeypatch.setattr(db_module, "MIGRATIONS_DIR", mig_dir)
    database = Database(tmp_path / "app.sqlite")
    try:
        assert database.migrate() == 1
        database.execute(
            "INSERT INTO venue (id, kind, name, field_json) VALUES (?,?,?,?)",
            ("v", "journal", "V", "[]"),
        )
    except Exception:
        database.close()
        raise
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
    with closing(_seed_v1(tmp_path, monkeypatch)) as database:
        _insert_paper(database, "p1", r"Erd\H{o}s--R\'enyi!")
        _insert_paper(database, "p2", "Café Society")

        _add_0002(tmp_path)
        assert database.migrate() == 2

        norms = {
            r["id"]: r["title_norm"] for r in database.query("SELECT id, title_norm FROM paper")
        }
        assert norms == {"p1": "erdos renyi", "p2": "cafe society"}
        idx = database.query(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_paper_title_norm'"
        )
        assert len(idx) == 1


def _insert_doi(database: Database, paper_id: str, value: str, *, is_primary: int = 0) -> None:
    database.execute(
        "INSERT INTO identifier (paper_id, scheme, value, is_primary) VALUES (?,?,?,?)",
        (paper_id, "doi", value, is_primary),
    )


def test_v1_to_v2_normalizes_doi_identifier_in_place(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """存量 doi 大小写异形、无归一形冲突 → 就地归一（小写化），行不丢。"""
    with closing(_seed_v1(tmp_path, monkeypatch)) as database:
        _insert_paper(database, "p1", "Some Paper")
        _insert_doi(database, "p1", "10.1016/J.X")

        _add_0002(tmp_path)
        assert database.migrate() == 2

        ids = database.query("SELECT paper_id, value FROM identifier WHERE scheme='doi'")
        assert [(r["paper_id"], r["value"]) for r in ids] == [("p1", "10.1016/j.x")]


def test_v1_to_v2_doi_case_collision_cross_paper_builds_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """两 paper 各持同一 DOI 的大小写异形 → 留归一形行、删异形行、建 candidate 留人审。"""
    with closing(_seed_v1(tmp_path, monkeypatch)) as database:
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


def test_v1_to_v2_doi_prefix_collision_uses_neutral_label(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """前缀异形（非纯大小写）碰撞同样走中性标签 doi-normalization-collision（名副其实）。"""
    with closing(_seed_v1(tmp_path, monkeypatch)) as database:
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


def test_v1_to_v2_doi_collision_restores_primary_when_deleted_row_was_primary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """碰撞删除的异形行若为 primary → 保留的归一行提为 primary（补单一 primary 不变量）。"""
    with closing(_seed_v1(tmp_path, monkeypatch)) as database:
        _insert_paper(database, "p1", "Some Paper")
        _insert_doi(database, "p1", "10.1/abc", is_primary=0)  # 归一形，非 primary
        _insert_doi(database, "p1", "10.1/ABC", is_primary=1)  # 异形，恰为 primary → 将被删

        _add_0002(tmp_path)
        assert database.migrate() == 2

        ids = database.query("SELECT value, is_primary FROM identifier WHERE scheme='doi'")
        # 保留行提为 primary。
        assert [(r["value"], r["is_primary"]) for r in ids] == [("10.1/abc", 1)]


def test_v1_to_v2_doi_case_collision_same_paper_drops_redundant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """同一 paper 上异形冗余 doi → 删冗余行、不建 candidate；归一行本就是 primary 则原样保留。"""
    with closing(_seed_v1(tmp_path, monkeypatch)) as database:
        _insert_paper(database, "p1", "Some Paper")
        _insert_doi(database, "p1", "10.1/abc", is_primary=1)  # 归一形本就是 primary
        _insert_doi(database, "p1", "10.1/ABC", is_primary=0)  # 异形冗余，非 primary → 将被删

        _add_0002(tmp_path)
        assert database.migrate() == 2

        ids = database.query(
            "SELECT paper_id, value, is_primary FROM identifier WHERE scheme='doi'"
        )
        # 删非 primary 异形后 paper 仍有 primary → 不重复提升，归一行原样保留其 primary。
        assert [(r["paper_id"], r["value"], r["is_primary"]) for r in ids] == [
            ("p1", "10.1/abc", 1)
        ]
        assert database.query("SELECT COUNT(*) AS n FROM paper_relation")[0]["n"] == 0


# -- schema v3（0003）v2→v3 自动升级 + 弱信号键回填 ----------------------------


def _add_0003(tmp_path: Path) -> None:
    shutil.copy(_REAL_MIGRATIONS_DIR / "0003_paper_weak_key.sql", tmp_path / "migrations")


def test_v2_to_v3_backfills_weak_keys_from_existing_papers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """v2 存量 paper 的历史弱信号键回填 = 旧实现的匹配面（title_norm + meta_json._first_author）。

    键不全的行（无 `_first_author` / 无 title_norm）本就不参与旧实现的弱信号匹配，故不回填
    ——升级后覆盖面零倒退、零扩张。
    """
    database = _seed_v1(tmp_path, monkeypatch)
    _add_0002(tmp_path)
    assert database.migrate() == 2
    database.execute(
        "INSERT INTO paper (id, title, title_norm, meta_json, ingest_state) VALUES (?,?,?,?,?)",
        ("p1", "Some Paper", "some paper", '{"_first_author": "smith"}', "metadata_only"),
    )
    database.execute(  # 无 _first_author（pull 路径所建）→ 不回填
        "INSERT INTO paper (id, title, title_norm, meta_json, ingest_state) VALUES (?,?,?,?,?)",
        ("p2", "Other Paper", "other paper", '{"pages": "1-2"}', "metadata_only"),
    )

    _add_0003(tmp_path)
    assert database.migrate() == 3

    rows = database.query("SELECT paper_id, title_norm, first_author FROM paper_weak_key")
    assert [(r["paper_id"], r["title_norm"], r["first_author"]) for r in rows] == [
        ("p1", "some paper", "smith")
    ]
    database.close()


# -- schema v4（0004_fulltext_asset.sql；Phase 7 T7 / D-033）---------------------------------


def _add_0004(tmp_path: Path) -> None:
    shutil.copy(_REAL_MIGRATIONS_DIR / "0004_fulltext_asset.sql", tmp_path / "migrations")


_FULLTEXT_V4_COLUMNS = {"asset_id", "source_sha256", "text_sha256", "state", "note"}


def test_v4_adds_five_columns_and_backfills_noop_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """v3 库（含 Phase 1 noop 行）→ v4：五列存在、noop 行回填 `state='noop'`、
    `ingest_state` **不回滚**（「只前进不回退」不破坏；design/12 §5.1）。"""
    database = _seed_v1(tmp_path, monkeypatch)
    _add_0002(tmp_path)
    _add_0003(tmp_path)
    assert database.migrate() == 3
    database.execute(
        "INSERT INTO paper (id, title, ingest_state) VALUES (?,?,?)",
        ("p1", "Legacy Paper", "extracted"),
    )
    database.execute(
        "INSERT INTO fulltext (paper_id, extractor, extractor_ver, text_path, char_count, "
        "lang, extracted_at) VALUES (?,?,?,?,?,?,?)",
        ("p1", "noop", "1", None, 0, None, "2026-01-01T00:00:00Z"),
    )

    _add_0004(tmp_path)
    assert database.migrate() == 4

    columns = {r["name"] for r in database.query("PRAGMA table_info(fulltext)")}
    assert _FULLTEXT_V4_COLUMNS <= columns
    row = database.query("SELECT * FROM fulltext WHERE paper_id = 'p1'")[0]
    assert row["state"] == "noop"
    assert row["asset_id"] is None and row["text_sha256"] is None  # legacy 行归一为 NULL
    assert database.query("SELECT ingest_state FROM paper WHERE id = 'p1'")[0][0] == "extracted"
    database.close()


def test_v4_keeps_fulltext_primary_key_on_paper_id(db: Database) -> None:
    """PK 保持 `paper_id`（design/06 §1「Paper 1─1 Fulltext」）——asset 级的是**键**不是基数。"""
    db.migrate()
    pk = [r["name"] for r in db.query("PRAGMA table_info(fulltext)") if r["pk"]]
    assert pk == ["paper_id"]


def test_v4_is_dialect_neutral() -> None:
    """五条 ADD COLUMN + 一条 UPDATE，无 SQLite 专有特性（design/06 §6 迁移纪律）。"""
    script = (_REAL_MIGRATIONS_DIR / "0004_fulltext_asset.sql").read_text(encoding="utf-8")
    statements = list(_iter_statements(script))
    assert len(statements) == 6
    assert sum(1 for s in statements if s.upper().startswith("ALTER TABLE")) == 5
    assert statements[-1].upper().startswith("UPDATE")
    for token in ("AUTOINCREMENT", "WITHOUT ROWID", "fts5", "PRAGMA"):
        assert token.lower() not in script.lower()


def test_v4_backfill_is_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """迁移幂等重跑：已 v4 的库再 migrate 不改版本、不改行。"""
    database = _seed_v1(tmp_path, monkeypatch)
    _add_0002(tmp_path)
    _add_0003(tmp_path)
    _add_0004(tmp_path)
    assert database.migrate() == 4
    assert database.migrate() == 4
    database.close()


def test_v4_column_comment_uses_the_prefix_free_relative_form() -> None:
    """`text_path` 形态写死为**不含 `data/` 前缀**的相对路径（design/12 §5.4）。

    带前缀会被 `verify._resolve` 解析成 `…/data/data/fulltext/…` 使**全库每一行都报
    missing_file**。`0001_init.sql` 的旧列注释含该前缀，是既成事实的文档缺陷，**一个字节
    都不改**；正确形态以本迁移的列注释与 design/06 §2 为准。
    """
    script = (_REAL_MIGRATIONS_DIR / "0004_fulltext_asset.sql").read_text(encoding="utf-8")
    assert "data/fulltext/{" not in script
    assert "相对 data_dir" in script


# -- schema v5（0005）paper_fts 虚表 + 触发器同步 + 存量回填（Phase 7 T12，D-034）------
#
# rebase 后 T7 的 0004 已在库中：以下大多数升级测试仍从 v3 直接跨到 v5（只加
# `0005_fts_paper.sql` 一份迁移文件——`_pending_migrations` 按数字前缀取号、不要求
# 连续，跳过中间的 0004 是合法的独立测试手法，验证的是"0005 自身机制"而非"0004 对
# 0005 有无影响"，二者本就无耦合）；另有一条 `test_v1_through_v5_realistic_upgrade_
# chain` 补齐真实生产路径（1→2→3→4→5 顺序应用全部五个文件）。


def _add_0005(tmp_path: Path) -> None:
    shutil.copy(_REAL_MIGRATIONS_DIR / "0005_fts_paper.sql", tmp_path / "migrations")


def test_v1_through_v5_realistic_upgrade_chain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """rebase 后的真实生产路径：0001→0002→0003→0004→0005 依次应用（而非本文件其余
    v5 测试为隔离验证 0005 自身机制而采用的"跳过 0004"简化路径），确认两个独立卡
    （T7/T12）的迁移文件在真实合流顺序下能顺利叠加、互不干扰。
    """
    database = _seed_v1(tmp_path, monkeypatch)
    _add_0002(tmp_path)
    assert database.migrate() == 2
    _add_0003(tmp_path)
    assert database.migrate() == 3
    _add_0004(tmp_path)
    assert database.migrate() == 4
    _add_0005(tmp_path)
    assert database.migrate() == 5

    assert "paper_fts" in _table_names(database)
    fulltext_columns = {r["name"] for r in database.query("PRAGMA table_info(fulltext)")}
    assert _FULLTEXT_V4_COLUMNS <= fulltext_columns
    database.close()


def test_v3_to_v5_creates_paper_fts_table_and_three_triggers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """0005 建虚表 + 三触发器（ai/au/ad），一次迁移到位，无需 Python 后置步。"""
    database = _seed_v1(tmp_path, monkeypatch)
    _add_0002(tmp_path)
    assert database.migrate() == 2
    _add_0003(tmp_path)
    assert database.migrate() == 3

    _add_0005(tmp_path)
    assert database.migrate() == 5

    assert "paper_fts" in _table_names(database)
    trigger_rows = database.query(
        "SELECT name FROM sqlite_master WHERE type='trigger' ORDER BY name"
    )
    assert [r["name"] for r in trigger_rows] == [
        "paper_fts_ad",
        "paper_fts_ai",
        "paper_fts_au",
    ]
    database.close()


def test_v3_to_v5_backfills_existing_papers_into_fts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """存量 paper 行（升级前已存在）由 0005 的纯 SQL 回填一次性灌入 paper_fts；
    NULL abstract 回填为空串（`COALESCE(abstract, '')`，与 schema 未来写路径一致）。
    """
    database = _seed_v1(tmp_path, monkeypatch)
    _add_0002(tmp_path)
    assert database.migrate() == 2
    _add_0003(tmp_path)
    assert database.migrate() == 3
    database.execute(
        "INSERT INTO paper (id, title, abstract, ingest_state) VALUES (?,?,?,?)",
        ("p1", "Deep Learning", "About neural nets", "metadata_only"),
    )
    database.execute(
        "INSERT INTO paper (id, title, abstract, ingest_state) VALUES (?,?,?,?)",
        ("p2", "No Abstract Paper", None, "metadata_only"),
    )

    _add_0005(tmp_path)
    assert database.migrate() == 5

    rows = database.query("SELECT paper_id, title, abstract FROM paper_fts ORDER BY paper_id")
    assert [(r["paper_id"], r["title"], r["abstract"]) for r in rows] == [
        ("p1", "Deep Learning", "About neural nets"),
        ("p2", "No Abstract Paper", ""),
    ]
    database.close()


def test_paper_fts_match_query_finds_backfilled_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """冒烟：回填后的虚表真的可查（MATCH 命中），非仅建表/建索引行。"""
    database = _seed_v1(tmp_path, monkeypatch)
    _add_0002(tmp_path)
    assert database.migrate() == 2
    _add_0003(tmp_path)
    assert database.migrate() == 3
    database.execute(
        "INSERT INTO paper (id, title, abstract, ingest_state) VALUES (?,?,?,?)",
        ("p1", "Asset Pricing Models", "Finance theory content", "metadata_only"),
    )
    _add_0005(tmp_path)
    assert database.migrate() == 5

    rows = database.query("SELECT paper_id FROM paper_fts WHERE paper_fts MATCH 'pricing'")
    assert [r["paper_id"] for r in rows] == ["p1"]
    database.close()


def test_paper_insert_syncs_into_fts_via_trigger(db: Database) -> None:
    """`paper_fts_ai`：新建 paper 行即时同步进 `paper_fts`（写路径全覆盖，非仅回填），
    rowid 显式绑定 `paper.rowid`（decision 3：查询正确性不依赖此绑定，但写路径定位靠它）。
    """
    db.migrate()
    db.execute(
        "INSERT INTO paper (id, title, abstract, ingest_state) VALUES (?,?,?,?)",
        ("p1", "New Paper", "New abstract", "metadata_only"),
    )
    paper_rowid = db.query("SELECT rowid AS rid FROM paper WHERE id='p1'")[0]["rid"]
    rows = db.query("SELECT rowid AS rid, paper_id, title, abstract FROM paper_fts")
    assert len(rows) == 1
    assert rows[0]["rid"] == paper_rowid
    assert rows[0]["paper_id"] == "p1"
    assert rows[0]["title"] == "New Paper"
    assert rows[0]["abstract"] == "New abstract"


def test_paper_insert_with_null_abstract_syncs_empty_string(db: Database) -> None:
    """`COALESCE(new.abstract, '')`：NULL abstract 写路径同样回填空串（与存量回填口径一致）。"""
    db.migrate()
    db.execute(
        "INSERT INTO paper (id, title, ingest_state) VALUES (?,?,?)",
        ("p1", "No Abstract", "metadata_only"),
    )
    rows = db.query("SELECT abstract FROM paper_fts WHERE paper_id='p1'")
    assert rows[0]["abstract"] == ""


def test_paper_update_title_resyncs_fts_via_delete_insert(db: Database) -> None:
    """`paper_fts_au`（不变式 A）：UPDATE title 走 DELETE+INSERT 形态，paper_fts 反映新值。"""
    db.migrate()
    db.execute(
        "INSERT INTO paper (id, title, abstract, ingest_state) VALUES (?,?,?,?)",
        ("p1", "Old Title", "Old Abs", "metadata_only"),
    )
    db.execute("UPDATE paper SET title = ? WHERE id = ?", ("New Title", "p1"))
    rows = db.query("SELECT paper_id, title, abstract FROM paper_fts WHERE paper_id='p1'")
    assert len(rows) == 1
    assert rows[0]["title"] == "New Title"
    assert rows[0]["abstract"] == "Old Abs"


def test_paper_update_abstract_resyncs_fts(db: Database) -> None:
    """`AFTER UPDATE OF title, abstract`：单独改 abstract 同样触发重同步。"""
    db.migrate()
    db.execute(
        "INSERT INTO paper (id, title, abstract, ingest_state) VALUES (?,?,?,?)",
        ("p1", "Title", "Old Abs", "metadata_only"),
    )
    db.execute("UPDATE paper SET abstract = ? WHERE id = ?", ("New Abs", "p1"))
    rows = db.query("SELECT abstract FROM paper_fts WHERE paper_id='p1'")
    assert rows[0]["abstract"] == "New Abs"


def test_paper_update_unrelated_column_does_not_touch_fts(db: Database) -> None:
    """`UPDATE OF title, abstract` 限定列：更新 `ingest_state` 等高频列不触发
    DELETE+INSERT 重建（避免空转）——同一 rowid 原样保留即为证据。
    """
    db.migrate()
    db.execute(
        "INSERT INTO paper (id, title, abstract, ingest_state) VALUES (?,?,?,?)",
        ("p1", "Title", "Abs", "metadata_only"),
    )
    before_rowid = db.query("SELECT rowid AS rid FROM paper_fts WHERE paper_id='p1'")[0]["rid"]
    db.execute("UPDATE paper SET ingest_state = ? WHERE id = ?", ("resolved", "p1"))
    after_rowid = db.query("SELECT rowid AS rid FROM paper_fts WHERE paper_id='p1'")[0]["rid"]
    assert before_rowid == after_rowid


def test_paper_delete_removes_fts_row(db: Database) -> None:
    """`paper_fts_ad`：paper 行删除后，`paper_fts` 对应行同步删除（双条件 `AND paper_id`
    见下方 rowid 冲突场景测试，本用例只覆盖"正常无漂移"路径）。
    """
    db.migrate()
    db.execute(
        "INSERT INTO paper (id, title, abstract, ingest_state) VALUES (?,?,?,?)",
        ("p1", "Title", "Abs", "metadata_only"),
    )
    assert len(db.query("SELECT 1 AS x FROM paper_fts WHERE paper_id='p1'")) == 1
    db.execute("DELETE FROM paper WHERE id = ?", ("p1",))
    assert db.query("SELECT 1 AS x FROM paper_fts WHERE paper_id='p1'") == []


# -- FTS5 缺失模块 / rowid 冲突：翻译为可操作 CrawlerError（D-034 决策 3/4）-------------


class _FtsBlockingConnProxy:
    """包一层真实连接：拦截含 `USING FTS5` 的建表语句、人为抛出
    `sqlite3.OperationalError: no such module: fts5`。

    本机 SQLite 已编译 FTS5（`sqlite_compileoption_used('ENABLE_FTS5')` 实测为 1），
    无法在真实环境直接复现"未编译 FTS5"这一错误——D-034 决策 4 原文明确要求"专测
    （monkeypatch 触发）"。`sqlite3.Connection` 是不可变 C 扩展类型，无法在类级别
    monkeypatch 其 `execute` 方法（实测 `TypeError: cannot set 'execute' attribute
    of immutable type`），故改为在 `Database._conn`（普通 Python 属性）层面替换成
    本代理对象，未拦截的调用经 `__getattr__` 原样转发给真实连接。
    """

    def __init__(self, real: sqlite3.Connection) -> None:
        self._real = real

    def execute(self, sql: str, *args: object) -> sqlite3.Cursor:
        if "using fts5" in sql.lower():
            raise sqlite3.OperationalError("no such module: fts5")
        return self._real.execute(sql, *args)

    def __getattr__(self, name: str) -> object:
        return getattr(self._real, name)


def test_apply_translates_fts5_missing_module_to_crawler_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D-034 决策 4：`CREATE VIRTUAL TABLE … USING fts5` 撞"未编译 FTS5"时，
    `_apply` 把裸 `sqlite3.OperationalError` 翻译为可操作 `CrawlerError(CONFIG)`；
    整步仍回滚（版本不前进）。
    """
    mig_dir = _staged_migrations_dir(tmp_path, "0001_init.sql")
    monkeypatch.setattr(db_module, "MIGRATIONS_DIR", mig_dir)

    with closing(Database(tmp_path / "app.sqlite")) as database:
        assert database.migrate() == 1
        _write_migration(mig_dir, "0005_fts_paper.sql", "CREATE VIRTUAL TABLE x USING fts5(a);")
        database._conn = _FtsBlockingConnProxy(database._conn)  # type: ignore[assignment]

        with pytest.raises(CrawlerError) as exc_info:
            database.migrate()

        assert exc_info.value.error_class == ErrorClass.CONFIG
        assert "fts5" in str(exc_info.value).lower()
        assert database._current_version() == 1  # 整步回滚，版本未前进


def test_tx_translates_paper_fts_rowid_collision_to_crawler_error(db: Database) -> None:
    """D-034 决策 3 不变式 B 的实测场景：`paper_fts` 里有一行"孤儿"占着某个 rowid
    （模拟 `VACUUM` 重编号后遗留的漂移状态——直接工程化该状态，因为本机 SQLite 实测
    对无 INTEGER PRIMARY KEY 的表并不总是在 `VACUUM` 时重编号 rowid，无法可靠地
    从真实 `VACUUM` 复现，见本卡报告）；随后经 `paper` 表的正常写路径插入新 paper，
    SQLite 按"空表 rowid 从 1 起"的规则自动把新行分配到同一个 rowid，
    `paper_fts_ai` 触发器的 INSERT 因而撞车——`Database.tx()` 须把这一 IntegrityError
    翻译为可操作 CrawlerError，且原 paper 写入连同触发器整体回滚（不留半成品）。
    """
    db.migrate()
    # 模拟漂移：paper_fts 里有一行指向一个并不存在于 paper 的 "ghost" paper_id，
    # 占用 rowid=1（此刻 paper 表为空，故其后任何新 paper 的首行会自动落在 rowid=1）。
    db.execute(
        "INSERT INTO paper_fts(rowid, paper_id, title, abstract) VALUES (1, 'ghost', 'Ghost', '')"
    )

    with pytest.raises(CrawlerError) as exc_info:
        with db.tx() as conn:
            conn.execute(
                "INSERT INTO paper (id, title, abstract, ingest_state) VALUES (?,?,?,?)",
                ("real-paper", "Real Paper", "Real abstract", "metadata_only"),
            )

    assert exc_info.value.error_class == ErrorClass.CONFIG
    assert "reindex" in str(exc_info.value)
    # 回滚验证：paper 行未落库（触发器失败连同触发它的 INSERT 一并回滚），
    # paper_fts 里的 ghost 行原样保留（未被半途破坏）。
    assert db.query("SELECT 1 AS x FROM paper WHERE id='real-paper'") == []
    ghost_rows = db.query("SELECT paper_id FROM paper_fts WHERE rowid=1")
    assert [r["paper_id"] for r in ghost_rows] == ["ghost"]


def test_tx_does_not_translate_foreign_key_violation(db: Database) -> None:
    """回归护栏：`tx()` 的翻译只认裸 `constraint failed`（FTS 虚表信号），既有
    FK/唯一约束等 `IntegrityError` 必须原样透传——不能被本次改动误吞。
    """
    db.migrate()
    with pytest.raises(sqlite3.IntegrityError) as exc_info:
        with db.tx() as conn:
            conn.execute(
                "INSERT INTO issue (id, venue_id, source) VALUES (?,?,?)",
                ("i1", "ghost_venue", "mock"),
            )
    assert not isinstance(exc_info.value, CrawlerError)
