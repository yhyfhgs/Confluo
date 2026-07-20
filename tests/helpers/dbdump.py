"""AC-1.3 canonical dump 口径的可执行定义（phase1-implementation-plan.md「执行期重排记录」
Task 9 节冻结签名）。

## 用途

断点续爬幂等验收（AC-1.3）：同一批输入分别经"kill -9 打断后重跑"与"一次性连续跑完"两条
路径各自落一个 SQLite 库；两个库的主键（`id` 列，均为 `new_ulid()` 生成的 ULID 文本）与
写入时间戳在两次独立运行间必然不同，不能直接逐行比较整张表。`canonical_dump(db_path)`
把一个库变换为只含"业务内容"的 dict，供调用方对两个库的返回值做 `==` 断言——业务数据
相同则返回值相等，即便两库的物理主键/时间戳完全不同。

## 表集与列处理规则

比较表 = `venue` / `issue` / `paper` / `identifier` / `asset` / `paper_issue_link`
（design/06 §1 ER 图核心元数据流；`venue_era`/`author`/`authorship`/`paper_relation`/
`fulltext`/`subscription*` 当前阶段无写入路径，不参与）。`task`/`fetch_log` 记录运行轨迹
本身，两条路径的任务/日志历史天然不同（一条含中断记录一条没有），AC-1.3 只约束"最终
数据状态一致"，不参与本函数的逐行对比（调用方对 fetch_log 单独断言，如"每 asset 成功
fetch_log 条数 ≤1"）。

每表的具体规则：

1. **剔除 volatile 列**：`id`（本库内部 ULID 主键）、`created_at` / `updated_at` /
   `fetched_at`（写入时钟时间戳）、`file_path`（内含 ULID 文件名片段，design/06 §4 布局
   `data/pdf/{venue}/{year}/{paper_ulid}.pdf`）——两次独立运行天然不同，非"业务数据"的
   一部分。`venue.id` 字面同名 `id` 也一并剔除；它实际上是 `VenueSpec.id`（用户配置的
   稳定 slug，`Repo.upsert_venue` 直接使用、不经 `new_ulid()`），并非不可复现的 ULID，
   但为使剔除规则对全表集保持单一、机械、可核对的口径（而非"逐表判断这个 id 是不是真
   ULID"的主观规则），统一剔除；`venue` 行的等价性由其余列（name/kind/...）+ 其它表原样
   保留的 `venue_id` 值共同保证，不因剔除 `venue.id` 本身而失真。
2. **外键列翻译为业务键**：ULID 外键在两个独立库间不可比较，翻译为被引行的业务键
   （每个 FK 列翻译后仍占原来 1 个位置；若业务键本身是复合键，该位置的值是一个嵌套
   tuple）：
   - `issue.venue_id` / `paper.venue_id`：venue 的业务键就是 `venue_id` 原值本身
     （见规则 1），无需二次查表翻译，原样保留为标量。
   - `issue.era_id`：翻译为 `venue_era` 的业务键 `(year, label)`（对应 DDL
     `UNIQUE(venue_id, year, label)`）；`era_id` 为 NULL 时该位置整体记 `None`。当前
     阶段没有代码写入 `venue_era`（`era_id` 恒 NULL），此规则是前向兼容（见
     `tests/unit/test_dbdump.py` 手工建行验证）。
   - `identifier.paper_id` / `asset.paper_id` / `paper_issue_link.paper_id`：翻译为该
     paper 的 `title`（标量）——paper 的强合并锚点是 identifier，但 `title` 恒非空且是
     本计划钦定的 paper 业务键（phase1-implementation-plan.md Task 9 节原文）。
   - `paper_issue_link.issue_id`：翻译为该 issue 的业务键
     `(venue_id, volume, number, label)`（对应 issue 表自身的 `UNIQUE` 约束）。
3. **行序**：每表按业务键升序排序，使比较不受两次运行内部插入顺序差异影响（kill-9
   重跑与一次性跑完途中 upsert 的调用顺序不保证相同）。具体排序键（SQL `ORDER BY`，
   NULL 排序遵循 SQLite 默认语义）：
   - `venue`：`id`（业务键本身，但依规则 1 不出现在输出列中——仅用于排序）；
   - `issue`：`(venue_id, volume, number, label)`（Task 9 节列出前三项，补 `label` 为
     第四项，与表自身 `UNIQUE` 约束一致——防止会议类 issue 因 volume/number 皆空而排序
     不稳定）；
   - `paper`：`(title, venue_id, year, pub_date)`（Task 9 节口径为 `title`；后三项仅作
     同名标题时的稳定兜底，Phase 1 mock 语料标题含卷期号不会重复）；
   - `identifier`：`(scheme, value)`（表自身主键，天然唯一，Task 9 节口径）；
   - `asset`：`(paper.title, kind, version)`（对应 `UNIQUE(paper_id,kind,version)` 翻译
     业务键后的排序键，Task 9 节口径）；
   - `paper_issue_link`：`(paper.title, venue_id, volume, number, label)`（Task 9 节未
     列出该表排序键，取 paper 与 issue 两侧业务键顺序拼接）。

## 返回值形状

`{table_name: [row_tuple, ...]}`；每张表的 `row_tuple` 字段顺序固定，与下方各 `_dump_*`
函数的 SQL `SELECT` 列表一一对应（顺序即含义，无需查 schema）：

- `venue`: `(kind, name, field_json, tier, spec_snapshot_json, status)`
- `issue`: `(venue_id, era_key, volume, number, year, label, pub_date, source,
  paper_count_claimed)` —— `era_key` 见规则 2
- `paper`: `(title, abstract, year, pub_date, venue_id, meta_json, ingest_state)`
- `identifier`: `(paper_title, scheme, value, is_primary)`
- `asset`: `(paper_title, kind, version, url, auth_needed, state, bytes, sha256,
  source_adapter)`
- `paper_issue_link`: `(paper_title, issue_key)` —— `issue_key` 见规则 2

两个库若代表"同一批业务数据"，`canonical_dump(a) == canonical_dump(b)` 应为 `True`；
任何一行字段的真实差异、或缺行/多行，都会使其为 `False`（用例见
`tests/unit/test_dbdump.py`）。本函数只读，不修改数据库。
"""

from __future__ import annotations

from pathlib import Path

from paper_crawler.storage.db import Database


def _dump_venue(db: Database) -> list[tuple[object, ...]]:
    rows = db.query(
        "SELECT kind, name, field_json, tier, spec_snapshot_json, status FROM venue ORDER BY id"
    )
    return [
        (
            row["kind"],
            row["name"],
            row["field_json"],
            row["tier"],
            row["spec_snapshot_json"],
            row["status"],
        )
        for row in rows
    ]


def _dump_issue(db: Database) -> list[tuple[object, ...]]:
    rows = db.query(
        "SELECT i.era_id, i.venue_id, ve.year AS era_year, ve.label AS era_label, "
        "       i.volume, i.number, i.year, i.label, i.pub_date, i.source, "
        "       i.paper_count_claimed "
        "FROM issue i "
        "LEFT JOIN venue_era ve ON ve.id = i.era_id "
        "ORDER BY i.venue_id, i.volume, i.number, i.label"
    )
    result: list[tuple[object, ...]] = []
    for row in rows:
        era_key = None if row["era_id"] is None else (row["era_year"], row["era_label"])
        result.append(
            (
                row["venue_id"],
                era_key,
                row["volume"],
                row["number"],
                row["year"],
                row["label"],
                row["pub_date"],
                row["source"],
                row["paper_count_claimed"],
            )
        )
    return result


def _dump_paper(db: Database) -> list[tuple[object, ...]]:
    rows = db.query(
        "SELECT title, abstract, year, pub_date, venue_id, meta_json, ingest_state "
        "FROM paper ORDER BY title, venue_id, year, pub_date"
    )
    return [
        (
            row["title"],
            row["abstract"],
            row["year"],
            row["pub_date"],
            row["venue_id"],
            row["meta_json"],
            row["ingest_state"],
        )
        for row in rows
    ]


def _dump_identifier(db: Database) -> list[tuple[object, ...]]:
    rows = db.query(
        "SELECT p.title AS paper_title, ident.scheme, ident.value, ident.is_primary "
        "FROM identifier ident "
        "JOIN paper p ON p.id = ident.paper_id "
        "ORDER BY ident.scheme, ident.value"
    )
    return [(row["paper_title"], row["scheme"], row["value"], row["is_primary"]) for row in rows]


def _dump_asset(db: Database) -> list[tuple[object, ...]]:
    rows = db.query(
        "SELECT p.title AS paper_title, a.kind, a.version, a.url, a.auth_needed, "
        "       a.state, a.bytes, a.sha256, a.source_adapter "
        "FROM asset a "
        "JOIN paper p ON p.id = a.paper_id "
        "ORDER BY p.title, a.kind, a.version"
    )
    return [
        (
            row["paper_title"],
            row["kind"],
            row["version"],
            row["url"],
            row["auth_needed"],
            row["state"],
            row["bytes"],
            row["sha256"],
            row["source_adapter"],
        )
        for row in rows
    ]


def _dump_paper_issue_link(db: Database) -> list[tuple[object, ...]]:
    rows = db.query(
        "SELECT p.title AS paper_title, i.venue_id AS issue_venue_id, "
        "       i.volume AS issue_volume, i.number AS issue_number, i.label AS issue_label "
        "FROM paper_issue_link l "
        "JOIN paper p ON p.id = l.paper_id "
        "JOIN issue i ON i.id = l.issue_id "
        "ORDER BY p.title, i.venue_id, i.volume, i.number, i.label"
    )
    return [
        (
            row["paper_title"],
            (row["issue_venue_id"], row["issue_volume"], row["issue_number"], row["issue_label"]),
        )
        for row in rows
    ]


def canonical_dump(db_path: Path) -> dict[str, list[tuple[object, ...]]]:
    """见模块 docstring —— AC-1.3 canonical dump 口径的可执行定义。只读，不修改数据库。"""
    db = Database(db_path)
    try:
        return {
            "venue": _dump_venue(db),
            "issue": _dump_issue(db),
            "paper": _dump_paper(db),
            "identifier": _dump_identifier(db),
            "asset": _dump_asset(db),
            "paper_issue_link": _dump_paper_issue_link(db),
        }
    finally:
        db.close()
