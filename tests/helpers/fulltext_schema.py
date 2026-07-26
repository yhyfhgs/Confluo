"""T14（`verify` 全库扩展）的 fulltext 表测试 helper：T7 依赖处置。

design/12-fulltext-extract.md §5.1 冻结了 T7 要落地的 0004 迁移——`fulltext` 表新增
`asset_id`/`source_sha256`/`text_sha256`/`state`/`note` 五列（Phase 1 起只有
`paper_id`/`extractor`/`extractor_ver`/`text_path`/`char_count`/`lang`/`extracted_at`
七列）。phase7-implementation-plan.md §5 把 T14 与 T7 排进同一波次、明确"可并行"、
不保证合并顺序——本模块是任务卡对这一依赖的裁决处置："测试自建表"：`ensure_
fulltext_asset_columns` 按 `PRAGMA table_info` 探测缺列才 `ALTER TABLE ADD COLUMN`，
T7 合并后（列已由真实 0004 迁移创建）本函数探测到列已存在即跳过，天然兼容、零冲突
（不会对已存在的列重复 `ADD COLUMN` 报错）。

`write_fulltext_row`/`write_legacy_fulltext_row` 供测试快速构造 fulltext 行：前者写
T7 完整列契约（design/12 §4），后者只写 Phase 1 现存四列（模拟 main 当前真实 schema、
或 T7 未合并时的存量行），两者都在 `tests/unit/test_verify.py` 与
`tests/integration/test_cli.py` 复用，避免重复定义。
"""

from __future__ import annotations

from paper_crawler.storage.db import Database
from paper_crawler.storage.repo import Repo

FULLTEXT_ASSET_COLUMNS: dict[str, str] = {
    "asset_id": "TEXT REFERENCES asset",
    "source_sha256": "TEXT",
    "text_sha256": "TEXT",
    "state": "TEXT",
    "note": "TEXT",
}


def ensure_fulltext_asset_columns(database: Database) -> None:
    """模拟 T7(design/12 §5.1) 的 0004 迁移新增列（"测试自建表"——T7 依赖的裁决处置）。"""
    existing = {row["name"] for row in database.query("PRAGMA table_info(fulltext)")}
    for column, ddl_type in FULLTEXT_ASSET_COLUMNS.items():
        if column not in existing:
            database.execute(f"ALTER TABLE fulltext ADD COLUMN {column} {ddl_type}")


def write_fulltext_row(
    repo: Repo,
    paper_id: str,
    *,
    text_path: str | None = None,
    text_sha256: str | None = None,
    asset_id: str | None = None,
    source_sha256: str | None = None,
    state: str | None = "extracted",
    extractor: str = "pypdf",
    extractor_ver: str = "1",
    char_count: int = 0,
) -> None:
    """写/覆盖一行 `fulltext`（自建 T7 增量列；design/12 §4 列契约，T7 合并后天然兼容）。

    `paper_id` 是该表 PK（1-1，design/12 §5.1），故用 upsert 语义——同一 paper 多次
    调用即覆盖，供崩溃窗测试模拟"重跑后状态改变"。
    """
    ensure_fulltext_asset_columns(repo.db)
    repo.db.execute(
        "INSERT INTO fulltext "
        "(paper_id, extractor, extractor_ver, text_path, char_count, lang, extracted_at, "
        " asset_id, source_sha256, text_sha256, state, note) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?) "
        "ON CONFLICT(paper_id) DO UPDATE SET "
        "  extractor=excluded.extractor, extractor_ver=excluded.extractor_ver, "
        "  text_path=excluded.text_path, char_count=excluded.char_count, "
        "  asset_id=excluded.asset_id, source_sha256=excluded.source_sha256, "
        "  text_sha256=excluded.text_sha256, state=excluded.state, note=excluded.note",
        (
            paper_id,
            extractor,
            extractor_ver,
            text_path,
            char_count,
            None,
            None,
            asset_id,
            source_sha256,
            text_sha256,
            state,
            None,
        ),
    )


def write_legacy_fulltext_row(repo: Repo, paper_id: str, *, extractor: str = "noop") -> None:
    """写一行 Phase 1 形态的 legacy fulltext 行（只用 main 现存四列，不碰 T7 增量列）；
    用于证明"T7 未合并时的真实存量 schema"下 `verify_store`/`count_pending_extraction`
    仍正确运行（不依赖 `ensure_fulltext_asset_columns` 已跑过）。
    """
    repo.db.execute(
        "INSERT INTO fulltext (paper_id, extractor, extractor_ver, text_path, char_count) "
        "VALUES (?,?,?,?,?) "
        "ON CONFLICT(paper_id) DO UPDATE SET extractor=excluded.extractor, "
        "extractor_ver=excluded.extractor_ver, text_path=excluded.text_path, "
        "char_count=excluded.char_count",
        (paper_id, extractor, "1", None, 0),
    )


__all__ = [
    "FULLTEXT_ASSET_COLUMNS",
    "ensure_fulltext_asset_columns",
    "write_fulltext_row",
    "write_legacy_fulltext_row",
]
