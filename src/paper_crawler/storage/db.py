"""SQLite 连接工厂与迁移器（接口冻结件 §2.4 `Database`）。

设计依据：
- design/06 §6：`schema_version` 单行表；顺序执行 `migrations/000N_*.sql`，每步事务 +
  执行前 db 文件 copy 备份；SQLite→PostgreSQL 迁移路径（方言中性 DDL）。
- Global Constraints §7/§9：ULID 文本主键、UTC 时间戳、方言中性、不用 FTS5。

连接采用 autocommit（`isolation_level=None`）+ 显式 BEGIN/COMMIT，配合 WAL：
迁移每步与 `tx()` 均为手动事务，崩溃时 ROLLBACK 保证原子性。
"""

from __future__ import annotations

import shutil
import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path

# 迁移脚本目录（包内）。测试可 monkeypatch 本常量指向临时目录以覆盖多步迁移/备份路径。
MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def _iter_statements(script: str) -> Iterator[str]:
    """把一个 SQL 脚本切分为独立语句（在事务内逐条执行以保证每步原子性）。

    识别单引号字符串（含 `''` 转义）与 `--` 行注释，仅在字符串/注释之外的 `;`
    处断句；注释被丢弃，空语句被跳过。本项目迁移 DDL 不含触发器/复合语句，
    该切分器足够健壮（避免 `executescript` 的隐式 COMMIT 破坏手动事务边界）。
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
                if nxt == "'":  # 转义的单引号 —— 原样保留，跳过两个字符
                    stmt.append(nxt)
                    i += 2
                    continue
                in_string = False
            i += 1
            continue
        # 字符串/注释之外
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


class Database:
    """SQLite 连接封装：WAL + 外键约束 + 顺序迁移。

    单连接、串行使用（Phase 1 pipeline 天然串行；WAL 单写者）。
    """

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        # autocommit：事务由 migrate()/tx() 显式管理。
        self._conn = sqlite3.connect(str(db_path), isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")

    # -- 迁移 ---------------------------------------------------------------

    def migrate(self) -> int:
        """顺序执行未应用的迁移脚本，返回最终 `schema_version`。

        每步：（若已有既存 schema）先 copy 备份 db 文件 → BEGIN → 执行脚本各语句 →
        写 `schema_version` → COMMIT。首次建库（version 0）跳过备份。幂等：
        无未应用脚本时不改动版本、不报错。
        """
        current = self._current_version()
        for version, path in self._pending_migrations(current):
            # 首次建库（version 0）无既存数据 → 跳过备份；之后每步迁移前 copy 备份。
            if current > 0:
                self._backup(current)
            self._apply(version, path)
            current = version
        return current

    def _current_version(self) -> int:
        """读取当前 schema 版本；`schema_version` 表不存在时视为 0。"""
        exists = self._conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_version'"
        ).fetchone()
        if exists is None:
            return 0
        row = self._conn.execute("SELECT version FROM schema_version").fetchone()
        return int(row["version"]) if row is not None else 0

    @staticmethod
    def _pending_migrations(current: int) -> list[tuple[int, Path]]:
        """列出版本号 > current 的迁移文件，按版本升序。文件名形如 `0001_init.sql`。"""
        found: list[tuple[int, Path]] = []
        for path in MIGRATIONS_DIR.glob("*.sql"):
            prefix = path.name.split("_", 1)[0]
            if not prefix.isdigit():
                continue
            version = int(prefix)
            if version > current:
                found.append((version, path))
        found.sort(key=lambda item: item[0])
        return found

    def _backup(self, from_version: int) -> Path:
        """迁移前把 db 文件 copy 备份（design/06 §6）。

        仅在存在既有 schema（`from_version > 0`，见 `migrate`）时调用，故此时 db 文件必已
        落有数据。WAL 模式下先 checkpoint，使已提交数据落入主文件，再 copy。
        """
        self._conn.execute("PRAGMA wal_checkpoint(FULL)")
        backup_path = self.db_path.with_name(f"{self.db_path.name}.v{from_version}.bak")
        shutil.copy2(self.db_path, backup_path)
        return backup_path

    def _apply(self, version: int, path: Path) -> None:
        """在单个事务内执行一个迁移脚本并写入版本号；失败则整步回滚。"""
        script = path.read_text(encoding="utf-8")
        conn = self._conn
        conn.execute("BEGIN")
        try:
            for statement in _iter_statements(script):
                conn.execute(statement)
            # schema_version 由 0001 创建（0 行）或既存（1 行）；DELETE+INSERT 两种情形统一。
            conn.execute("DELETE FROM schema_version")
            conn.execute("INSERT INTO schema_version(version) VALUES (?)", (version,))
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise

    # -- 查询/执行 ----------------------------------------------------------

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        """写事务上下文（BEGIN IMMEDIATE → COMMIT / 异常 ROLLBACK）。

        BEGIN IMMEDIATE 立即取写锁，冲突时早失败（风险表：WAL 单写者）。
        """
        conn = self._conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            yield conn
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise

    def query(self, sql: str, params: Sequence[object] = ()) -> list[sqlite3.Row]:
        """执行 SELECT，返回全部行。"""
        return self._conn.execute(sql, params).fetchall()

    def execute(self, sql: str, params: Sequence[object] = ()) -> None:
        """执行单条写语句（autocommit 立即生效）。"""
        self._conn.execute(sql, params)

    def close(self) -> None:
        """关闭连接。"""
        self._conn.close()
