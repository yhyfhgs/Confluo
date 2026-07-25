"""SQLite 连接工厂与迁移器（接口冻结件 §2.4 `Database`）。

设计依据：
- design/06 §6：`schema_version` 单行表；顺序执行 `migrations/000N_*.sql`，每步事务 +
  执行前 db 文件 copy 备份；SQLite→PostgreSQL 迁移路径（方言中性 DDL）。
- Global Constraints §7/§9：ULID 文本主键、UTC 时间戳、方言中性、不用 FTS5。

连接采用 autocommit（`isolation_level=None`）+ 显式 BEGIN/COMMIT，配合 WAL：
迁移每步与 `tx()` 均为手动事务，崩溃时 ROLLBACK 保证原子性。
"""

from __future__ import annotations

import json
import shutil
import sqlite3
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path

# 迁移脚本目录（包内）。测试可 monkeypatch 本常量指向临时目录以覆盖多步迁移/备份路径。
MIGRATIONS_DIR = Path(__file__).parent / "migrations"

# doi 归一碰撞 candidate_duplicate 的置信度（归一后同 DOI=强证据，但仍留人审不自动合并）。
_DOI_COLLISION_CONFIDENCE = 0.99


def _backfill_title_norm(conn: sqlite3.Connection) -> None:
    """schema v2（0002）Python 回填：为存量 paper 行计算 `title_norm`。

    SQL 无法表达 `ids.normalize_title` 的 LaTeX 宏剥离/Unicode 折叠——故以 Python 步在
    同一迁移事务内、`ADD COLUMN` 之后执行。`WHERE title_norm IS NULL` 使其幂等（重跑或
    部分回填后再跑均安全）。局部 import 避免 storage 层顶层依赖上层模块（`ids` 是无内部
    依赖的叶子模块，无环）。
    """
    from paper_crawler.ids import normalize_title

    rows = conn.execute("SELECT id, title FROM paper WHERE title_norm IS NULL").fetchall()
    for row in rows:
        conn.execute(
            "UPDATE paper SET title_norm = ? WHERE id = ?",
            (normalize_title(row["title"]), row["id"]),
        )


def _insert_doi_collision_candidate(
    conn: sqlite3.Connection, paper_a: str, paper_b: str, normalized: str, original: str
) -> None:
    """两 paper 的 doi 归一后同形（实为同一著作）→ 建 candidate_duplicate(decided=NULL) 留人审。

    碰撞形态涵盖大小写异形**与前缀异形**（`https://doi.org/`、`doi:`）——故 evidence reason
    用中性标签 `doi-normalization-collision`（非仅 case）。端点按 paper id 升序定向（迁移
    一次性、单库内确定性即可）；`ON CONFLICT DO NOTHING` 幂等。绝不自动合并两 paper 行
    （06 §3：宁可两条待审）。
    """
    from_paper, to_paper = sorted((paper_a, paper_b))
    evidence = json.dumps(
        {
            "reason": "doi-normalization-collision",
            "doi_normalized": normalized,
            "doi_original": original,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    conn.execute(
        "INSERT INTO paper_relation "
        "(from_paper, to_paper, kind, confidence, evidence_json, decided) "
        "VALUES (?,?,?,?,?,?) "
        "ON CONFLICT (from_paper, to_paper, kind) DO NOTHING",
        (from_paper, to_paper, "candidate_duplicate", _DOI_COLLISION_CONFIDENCE, evidence, None),
    )


def _restore_primary_if_needed(conn: sqlite3.Connection, paper_id: str) -> None:
    """paper 删 identifier 后若失去 primary 但仍有 identifier → 把最小 (scheme,value) 提为 primary。

    0002 归一删除碰撞的 doi 异形行时，被删的可能正是该 paper 的 `is_primary` 行（如同一 paper
    上大小写/前缀异形冗余、异形恰为 primary），留下"有 identifier 却无 primary"的破缺——补回
    单一 primary 不变量。同 paper 冗余场景下留存的正是归一行（doi-only 时即最小行），故被提为
    primary，与 controller 裁定一致。已有 primary 则空操作。
    """
    has_primary = conn.execute(
        "SELECT 1 FROM identifier WHERE paper_id = ? AND is_primary = 1 LIMIT 1",
        (paper_id,),
    ).fetchone()
    if has_primary is not None:
        return
    row = conn.execute(
        "SELECT scheme, value FROM identifier WHERE paper_id = ? ORDER BY scheme, value LIMIT 1",
        (paper_id,),
    ).fetchone()
    if row is not None:
        conn.execute(
            "UPDATE identifier SET is_primary = 1 WHERE paper_id = ? AND scheme = ? AND value = ?",
            (paper_id, row["scheme"], row["value"]),
        )


def _normalize_doi_identifiers(conn: sqlite3.Connection) -> None:
    """schema v2（0002）Python 回填：把 identifier 表 doi 行归一到 `normalize_doi` 规范形。

    D-裁决 2026-07-22：`normalize_doi` 是 identifier 写入的唯一归一入口，存量 doi 行一并
    收敛。逐行（`ORDER BY value` 确定性）处理归一前后不同的 doi（大小写/前缀异形）：
      - 归一形无既有行 → 就地 UPDATE 该行 value；
      - 归一形已存在且指向**同一** paper（异形冗余）→ 删归一前的冗余行；
      - 归一形已存在且指向**不同** paper（归一碰撞=库内本存同一著作两行）→ 删本行、
        保留归一形所在行、两 paper 间建 `candidate_duplicate` 留人审——**不静默丢 paper 行**。
    删行后经 `_restore_primary_if_needed` 补回被删 primary 异形留下的 primary 破缺。
    快照先 `fetchall` 再逐行处理（避免游标随写失效）；每次 target 查询为实时态（含前序迭代
    的写），故顺序敏感的碰撞判定确定。全程在 0002 迁移事务内。
    """
    from paper_crawler.ids import DOI_SCHEME, normalize_doi

    rows = conn.execute(
        "SELECT paper_id, value FROM identifier WHERE scheme = ? ORDER BY value",
        (DOI_SCHEME,),
    ).fetchall()
    for row in rows:
        original = str(row["value"])
        normalized = normalize_doi(original)
        if normalized == original:
            continue
        this_paper = str(row["paper_id"])
        target = conn.execute(
            "SELECT paper_id FROM identifier WHERE scheme = ? AND value = ?",
            (DOI_SCHEME, normalized),
        ).fetchone()
        if target is None:
            conn.execute(
                "UPDATE identifier SET value = ? WHERE scheme = ? AND value = ?",
                (normalized, DOI_SCHEME, original),
            )
            continue
        conn.execute(
            "DELETE FROM identifier WHERE scheme = ? AND value = ?",
            (DOI_SCHEME, original),
        )
        _restore_primary_if_needed(conn, this_paper)
        target_paper = str(target["paper_id"])
        if target_paper != this_paper:
            _insert_doi_collision_candidate(conn, this_paper, target_paper, normalized, original)


def _migrate_v2(conn: sqlite3.Connection) -> None:
    """schema v2（0002_title_norm.sql）的 Python 后置步：title_norm 回填 + doi identifier 归一。"""
    _backfill_title_norm(conn)
    _normalize_doi_identifiers(conn)


def _migrate_v3(conn: sqlite3.Connection) -> None:
    """schema v3（0003_paper_weak_key.sql）Python 回填：存量 paper 的历史弱信号键。

    存量行的键 = 旧实现的匹配面本身：`paper.title_norm` 列 + `meta_json._first_author`
    （`_first_author` 藏在 JSON 里，抽取函数方言专有，故不写进 SQL 脚本）。两者齐备且非空
    的行才有匹配资格（与旧 `_merge_ingest_no_hit` 判据一致——空键不参与匹配，避免误配），
    故只回填这些行；v2 库升级后弱信号覆盖面零倒退、零扩张。`ON CONFLICT DO NOTHING` 幂等。
    """
    rows = conn.execute(
        "SELECT id, title_norm, meta_json FROM paper "
        "WHERE title_norm IS NOT NULL AND title_norm <> '' AND meta_json IS NOT NULL"
    ).fetchall()
    for row in rows:
        first_author = json.loads(row["meta_json"]).get("_first_author")
        if not isinstance(first_author, str) or not first_author:
            continue
        conn.execute(
            "INSERT INTO paper_weak_key (paper_id, title_norm, first_author) VALUES (?,?,?) "
            "ON CONFLICT (paper_id, title_norm, first_author) DO NOTHING",
            (row["id"], row["title_norm"], first_author),
        )


# 迁移的 Python 后置步：**按文件名绑定**（非仅版本号），故对测试里 monkeypatch 出的
# 同版本号但不同内容的迁移（如 `0002_b.sql`）不误触发——只有 0001_init.sql 之后真正的
# `0002_title_norm.sql` 会跑本步。每个 Python 步在其 SQL 语句之后、写 schema_version
# 之前、同一事务内执行（见 `_apply`）。
_PY_MIGRATIONS: dict[str, Callable[[sqlite3.Connection], None]] = {
    "0002_title_norm.sql": _migrate_v2,
    "0003_paper_weak_key.sql": _migrate_v3,
}


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
            # SQL 之后、写版本号之前：若本迁移文件注册了 Python 后置步（如 0002 的
            # title_norm 回填），在同一事务内执行——SQL 失败或 Python 步失败都整步回滚。
            py_step = _PY_MIGRATIONS.get(path.name)
            if py_step is not None:
                py_step(conn)
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
