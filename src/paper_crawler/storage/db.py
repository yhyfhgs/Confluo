"""SQLite 连接工厂与迁移器（接口冻结件 §2.4 `Database`）。

设计依据：
- design/06 §6：`schema_version` 单行表；顺序执行 `migrations/000N_*.sql`，每步事务 +
  执行前 db 文件 copy 备份；SQLite→PostgreSQL 迁移路径（方言中性 DDL）。
- Global Constraints §7/§9：ULID 文本主键、UTC 时间戳、方言中性（0001-0004）；FTS5 限于
  `0005_fts_paper.sql` 单文件（D-034 修订 D-017 决策 4——原推迟 Phase 6 的承诺未兑现，
  如实记债后改判 Phase 7 T12；migrations 号位见该 SQL 文件头注释）。

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

from paper_crawler.errors import CrawlerError, ErrorClass

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


def _keyword_at(script: str, i: int, word: str) -> bool:
    """大小写不敏感的整词匹配：`script[i:]` 以 `word`（全大写常量）开头，且紧邻的前后
    字符（若存在）都不是标识符字符（字母/数字/下划线）。

    用于 `_iter_statements` 识别 `BEGIN`/`END` 关键字——纯子串匹配会把 `PENDING`/
    `RUNNING`（0001_init.sql 的 task.state 默认值/部分索引 WHERE 子句）之类标识符的
    子串误判为关键字，整词匹配杜绝此类假阳性。
    """
    end = i + len(word)
    if script[i:end].upper() != word:
        return False
    if i > 0 and (script[i - 1].isalnum() or script[i - 1] == "_"):
        return False
    if end < len(script) and (script[end].isalnum() or script[end] == "_"):
        return False
    return True


def _iter_statements(script: str) -> Iterator[str]:
    """把一个 SQL 脚本切分为独立语句（在事务内逐条执行以保证每步原子性）。

    识别单引号字符串（含 `''` 转义）与 `--` 行注释，仅在字符串/注释之外的 `;`
    处断句；注释被丢弃，空语句被跳过。

    **D-034 扩展（T12）**：本切分器原仅逐 `;` 断句、docstring 曾自述"迁移 DDL 不含
    触发器/复合语句"——`0005_fts_paper.sql`（paper_fts 三触发器）证伪该假设，此处
    如实改口并扩展。额外识别 `CREATE TRIGGER … BEGIN … END;` 复合语句块：整词
    `BEGIN`（大小写不敏感、前后非标识符字符，见 `_keyword_at`）使 `trigger_depth`
    +1，整词 `END` 在 `trigger_depth > 0` 时 -1（钳制在 0——孤立 `END`，如 `CASE …
    END` 表达式落在 `trigger_depth == 0` 处，不使计数变负、不影响断句；本项目现有
    迁移脚本的触发器体内均无 `CASE…END` 用法，该钳制是防御性质，非本次扩展的功能
    目标）。`trigger_depth > 0` 期间 `;` 不断句，使 `BEGIN…END` 内的多条子语句随
    触发器整体作为**单一语句**喂给 `sqlite3.Cursor.execute()`——该 API 只接受单条
    语句，但 `CREATE TRIGGER … END` 整体在 SQLite 语法上正是单一顶层语句，内部 `;`
    是触发器体的语法组成部分而非顶层语句边界。**不得改用 `executescript`**——其
    隐式 COMMIT 会破坏 `_apply` 的手动事务边界（该切分器存在的初衷）。

    **已知未覆盖边界（T12 独立审查 P2-1，如实记录，非本次扩展目标——留给下一位
    author 的显式提醒，而非留白让其踩坑）**：
    1. **触发器体内的 `CASE … END` 表达式会切错**——若某触发器体内出现
       `CASE WHEN … END`（而非本卡三触发器所用的简单 DML），其 `END` 会被当成
       该触发器自身 `BEGIN…END` 的收尾（`trigger_depth` 提前减到 0），导致其后的
       `;` 被误判为顶层语句边界，把触发器体切成两段。**这是响亮失败而非静默错误
       ——切碎的半截 SQL 交给 `execute()` 几乎必然抛 `sqlite3.OperationalError`
       （语法不完整）**，migrate() 整步回滚（`_apply` 的既有事务边界），不会有
       数据静默损坏；但报错信息不会直接指向"CASE 表达式"这个根因，容易让下一位
       author 费解。
    2. **`/* … */` 块注释未被识别**——本切分器只认 `--` 行注释，若脚本含
       `/* 说明 BEGIN 之类 */` 这种块注释，注释内的 `BEGIN`/`END` 整词会被误判为
       真实关键字（字符层面无从区分"注释里的文字"与"代码"），错误改变
       `trigger_depth`；**若该脚本此后再无真实 `END` 与之配平，`trigger_depth`
       将一直 >0 直到脚本结尾**（实测复现：`trigger_depth` 卡在 1，其后全部 `;`
       不再断句，整个脚本被粘成一条"语句"），同样在 `execute()` 处响亮报错
       （多语句拼一条喂给 `sqlite3.Cursor.execute()` 会被拒绝），而非局部影响。
    3. **`[bracket]` 括号括起的标识符未被识别**——SQLite 兼容 T-SQL/Access 风格的
       `[begin]` 方括号标识符（列名/表名含 SQL 关键字时的转义写法），本切分器只认
       单引号字符串，`[begin]` 中的 `begin` 前后恰为 `[`/`]`（非标识符字符），会被
       `_keyword_at` 判定为真实关键字，同样错误改变 `trigger_depth`——后果同第 2
       点（无配平 `END` 则波及脚本剩余全部内容）。

    以上三点在本项目现有全部迁移文件（含 `0004_fulltext_asset.sql`、
    `0005_fts_paper.sql`）中均未出现（无 `CASE…END`、无块注释、无方括号标识符），
    故不影响当前正确性；本卡范围内不实现完整 SQL 词法分析器来堵上这些边界
    （成本与当前收益不成比例），只如实记录以便未来真的用到这些写法时不致误踩。
    """
    stmt: list[str] = []
    in_string = False
    in_comment = False
    trigger_depth = 0
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
        if _keyword_at(script, i, "BEGIN"):
            trigger_depth += 1
            stmt.append(script[i : i + 5])
            i += 5
            continue
        if trigger_depth > 0 and _keyword_at(script, i, "END"):
            trigger_depth -= 1
            stmt.append(script[i : i + 3])
            i += 3
            continue
        if ch == ";" and trigger_depth == 0:
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
        """在单个事务内执行一个迁移脚本并写入版本号；失败则整步回滚。

        **D-034 决策 4**：无 FTS5 编译支持的 SQLite 在 `CREATE VIRTUAL TABLE … USING
        fts5` 抛 `sqlite3.OperationalError: no such module: fts5`——既有机制已整步
        回滚，但裸异常面向用户不可读。本方法把该特定错误翻译为可操作
        `CrawlerError(CONFIG)`；其余 `OperationalError`（如既有测试覆盖的"重复建表"）
        原样透传，不改变既有失败行为。
        """
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
        except sqlite3.OperationalError as exc:
            conn.execute("ROLLBACK")
            if "no such module: fts5" in str(exc).lower():
                raise CrawlerError(
                    ErrorClass.CONFIG,
                    "当前 SQLite 未编译 FTS5 模块，无法建立/迁移全文检索索引",
                    detail=(
                        f"{path.name}: {exc}；请改用编译了 FTS5 支持的 SQLite"
                        "（CPython 官方发行版通常已内置），或联系维护者更换运行环境"
                    ),
                ) from exc
            raise
        except Exception:
            conn.execute("ROLLBACK")
            raise

    # -- 查询/执行 ----------------------------------------------------------

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        """写事务上下文（BEGIN IMMEDIATE → COMMIT / 异常 ROLLBACK）。

        BEGIN IMMEDIATE 立即取写锁，冲突时早失败（风险表：WAL 单写者）。

        **D-034 决策 3（`0005_fts_paper.sql` 触发器）**：若 `paper_fts` 的 rowid 因
        外部 `VACUUM`（`paper` 无 INTEGER PRIMARY KEY，rowid 隐式，SQLite 文档载明
        `VACUUM` 可重编号此类 rowid）等原因与 `paper` 错位，`paper` 写路径触发的
        `paper_fts_ai`/`paper_fts_au` 触发器会撞已被占用的 rowid，抛
        `sqlite3.IntegrityError`——本卡实测该异常消息恒为裸 `constraint failed`
        （虚表 xUpdate 返回 SQLITE_CONSTRAINT 不带扩展错误码，sqlite3 退化为无表名/
        列名的通用消息），经验区别于 FK/`UNIQUE`/`NOT NULL`/`CHECK` 违例的带前缀消息
        （分别形如 `FOREIGN KEY constraint failed`/`UNIQUE constraint failed: t.c`/
        `NOT NULL constraint failed: t.c`/`CHECK constraint failed: expr`）。本方法
        只翻译裸 `constraint failed` 这一特定信号为可操作 `CrawlerError(CONFIG)`
        （提示跑 `crawler reindex`）；其余 `IntegrityError`（FK/唯一约束等既有语义，
        如 `test_foreign_key_orphan_issue_rejected`）原样透传，不改变既有调用方行为。

        **rowid 错位的第二种结局（T12 独立审查 P1-1/P2-5，与上述"响亮撞车"并存、
        非互斥）**：`paper_fts_au`/`paper_fts_ad` 的 `DELETE … WHERE rowid=old.rowid
        AND paper_id=old.id` 因 rowid 错位而找不到匹配行时（删 0 行，不报错——
        `DELETE` 影响 0 行本身不是异常），若紧随其后的 `INSERT … VALUES(new.rowid,
        …)` 目标 rowid **恰好当前空闲**（而非被占用），插入会**静默成功**——旧的
        错位陈旧行原地不动、新行携正确内容与正确 rowid 落地，两行共享同一
        `paper_id`：既未撞车（本方法翻译的这一支不会被触发），也未被任何写路径
        察觉，直到检索命中重复结果或 `crawler reindex --check` 主动扫出（`--check`
        的 `duplicate_ids` 项/`rowid_misaligned_ids` 项——前者事后可查"已产出的重复
        行"，后者能在**潜伏阶段**、即"重复行尚未被产出、旧行仍孤立错位"时提前查出
        ——两项互补而非冗余，完整说明见 `storage/migrations/0005_fts_paper.sql`
        文件头与 `Repo.FtsCheckReport` docstring）。
        """
        conn = self._conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            yield conn
            conn.execute("COMMIT")
        except sqlite3.IntegrityError as exc:
            conn.execute("ROLLBACK")
            if str(exc).strip().lower() == "constraint failed":
                raise CrawlerError(
                    ErrorClass.CONFIG,
                    "FTS 索引与 paper 的 rowid 已错位，请跑 `crawler reindex` 修复",
                    detail=str(exc),
                ) from exc
            raise
        except Exception:
            conn.execute("ROLLBACK")
            raise

    def query(self, sql: str, params: Sequence[object] = ()) -> list[sqlite3.Row]:
        """执行 SELECT，返回全部行。"""
        return self._conn.execute(sql, params).fetchall()

    def execute(self, sql: str, params: Sequence[object] = ()) -> None:
        """执行单条写语句（autocommit 立即生效）。

        **已知边界（T12 独立审查 P2-4）**：本方法**不**做 `tx()` 那样的
        `IntegrityError` 翻译——若经本方法直写 `paper` 且撞上 `paper_fts` 触发器
        的 rowid 冲突，裸 `sqlite3.IntegrityError`（`constraint failed`）会原样
        透传，不会被译成可操作 `CrawlerError`。**现状核验**：`storage/repo.py`
        内经本方法直写 `paper` 表的仅 `set_paper_state`/`bind_paper_venue` 两处
        （均为 `UPDATE paper SET ingest_state=…`/`UPDATE paper SET venue_id=…`），
        二者均**不触及** `title`/`abstract` 列——而 `paper_fts_au` 触发器限定
        `AFTER UPDATE OF title, abstract`，故这两处写入根本不会触发该触发器，
        现状下不存在实际风险。此为**已知、当前安全的边界**而非已修复的缺口：
        若未来新增经本方法（而非 `tx()`）直写 `paper.title`/`paper.abstract` 的
        路径，须一并考虑是否也需要本方法级别的翻译，或改走 `tx()`。
        """
        self._conn.execute(sql, params)

    def close(self) -> None:
        """关闭连接。"""
        self._conn.close()
