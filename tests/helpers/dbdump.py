"""AC-1.3 canonical dump 口径的可执行定义（phase1-implementation-plan.md「执行期重排记录」
Task 9 节冻结签名）。

## 用途

断点续爬幂等验收（AC-1.3）：同一批输入分别经"kill -9 打断后重跑"与"一次性连续跑完"两条
路径各自落一个 SQLite 库；两个库的主键（`id` 列，均为 `new_ulid()` 生成的 ULID 文本）与
写入时间戳在两次独立运行间必然不同，不能直接逐行比较整张表。`canonical_dump(db_path)`
把一个库变换为只含"业务内容"的 dict，供调用方对两个库的返回值做 `==` 断言——业务数据
相同则返回值相等，即便两库的物理主键/时间戳完全不同，也**不受两库内部插入顺序差异
影响**（kill-9 重跑与一次性跑完途中各表的插入顺序不保证相同——这是本函数存在的核心
前提，见规则 2 关于 paper 复合业务键的说明）。

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
   - `identifier.paper_id`：翻译为该 paper 的 `title`（**标量**，不需要规则 2 下面这条
     的复合键）。`identifier` 表自身每一行的排序/相等性已经由该行自身的
     `(scheme, value)`（表的主键，全局唯一）保证；即使两个不同 paper 恰好同名，各自的
     identifier 行仍然逐行天然可区分——`paper_title` 只是附带的可读信息，不参与该表的
     去重或排序，用标量已经足够、不产生歧义。
   - `asset.paper_id` / `paper_issue_link.paper_id`：翻译为该 paper 的**复合业务键**
     `(title, primary_identifier)`。`primary_identifier` 是该 paper 名下全部 identifier
     里按 `(scheme, value)` 字典序最小的一个（相关子查询算出，`ORDER BY scheme, value
     LIMIT 1`；**不是** `identifier.is_primary` 列——那一列由写入时 `stub.identifiers`
     元组的顺序决定`is_primary = 1 if index == 0 else 0`（见 `repo.py`
     `_ensure_identifiers`），两次独立运行如果 identifiers 传入顺序不同，`is_primary`
     可能落在不同行上，本身就是不可复现的，不能拿来做跨库比较的消歧锚点）。
     仅用 `title` 不足以唯一确定 paper：当两个 paper 恰好同标题（design/06 §3 明确列出
     的 candidate_duplicate 场景，例如 WP 与刊发版合并前，或两篇标题偶然撞车的独立
     论文——非理论边角）、且它们各自的 asset 又恰好 `kind`/`version` 相同时，仅靠
     `ORDER BY title, kind, version` 排不出确定顺序，退化为依赖 SQLite 对并列行的隐式
     顺序（与该库当次的插入顺序相关）——这会让"业务数据完全相同、只是两库插入顺序不同"
     （kill-9 重跑的典型情形）被误判为 dump 不相等，直接违反本节开头"不受插入顺序差异
     影响"的承诺。`primary_identifier` 全局唯一（`identifier` 表主键），补上后
     `(title, primary_identifier)` 对每个 paper 恒唯一，`asset`/`paper_issue_link` 的
     排序与相等性判断都不再受插入顺序影响（对抗用例见
     `tests/unit/test_dbdump.py` 的
     `test_canonical_dump_disambiguates_asset_ownership_on_title_collision` 与
     `test_canonical_dump_equal_when_title_collision_only_insertion_order_differs`）。
     若某 paper 意外没有任何 identifier（不应发生——`PaperStub` 要求 identifiers 至少
     1 个），子查询退化为 NULL，此时复合键第二位记 `None`，行为退化为等价于仅用
     title（不会崩溃，但那种情况下本函数无法保证消歧，因为已经违反了域内不变式）。
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
     同名标题时的稳定兜底——`paper` 表本身没有 asset/paper_issue_link 那样"kind/version
     也相同"的强制去重需求，这里的兜底不要求全局唯一，只求实践中足够稳定，Phase 1
     mock 语料标题含卷期号不会重复）；
   - `identifier`：`(scheme, value)`（表自身主键，天然唯一，Task 9 节口径）；
   - `asset`：`(paper.title, primary_identifier, kind, version)`（在 Task 9 节口径
     `(paper.title, kind, version)` 的基础上按规则 2 插入 `primary_identifier` 消歧
     标题碰撞，对应 `UNIQUE(paper_id,kind,version)` 翻译业务键后的排序键）；
   - `paper_issue_link`：`(paper.title, primary_identifier, venue_id, volume, number,
     label)`（Task 9 节未列出该表排序键，取 paper 复合业务键与 issue 业务键顺序拼接）。

## 返回值形状

`{table_name: [row_tuple, ...]}`；每张表的 `row_tuple` 字段顺序固定，与下方各 `_dump_*`
函数的 SQL `SELECT` 列表一一对应（顺序即含义，无需查 schema）：

- `venue`: `(kind, name, field_json, tier, spec_snapshot_json, status)`
- `issue`: `(venue_id, era_key, volume, number, year, label, pub_date, source,
  paper_count_claimed)` —— `era_key` 见规则 2
- `paper`: `(title, abstract, year, pub_date, venue_id, meta_json, ingest_state)`
- `identifier`: `(paper_title, scheme, value, is_primary)` —— `paper_title` 为标量
- `asset`: `(paper_key, kind, version, url, auth_needed, state, bytes, sha256,
  source_adapter)` —— `paper_key` 见规则 2，形如 `(title, (scheme, value) | None)`
- `paper_issue_link`: `(paper_key, issue_key)` —— `paper_key`/`issue_key` 均见规则 2

两个库若代表"同一批业务数据"，`canonical_dump(a) == canonical_dump(b)` 应为 `True`；
任何一行字段的真实差异、或缺行/多行，都会使其为 `False`（用例见
`tests/unit/test_dbdump.py`）。本函数只读，不修改数据库。
"""

from __future__ import annotations

from pathlib import Path

from paper_crawler.storage.db import Database

# 相关子查询：给定 asset/paper_issue_link 所在别名的 paper_id 外键列（``{fk}``
# 占位符），取该 paper 名下按 (scheme,value) 字典序最小的 identifier 的 scheme/value
# ——即规则 2 定义的 primary_identifier。两处调用（asset、paper_issue_link）共享同一
# 逻辑，用字符串模板避免复制粘贴出现不一致。
_PRIMARY_IDENTIFIER_SCHEME_SQL = (
    "(SELECT ident.scheme FROM identifier ident WHERE ident.paper_id = {fk} "
    "ORDER BY ident.scheme, ident.value LIMIT 1)"
)
_PRIMARY_IDENTIFIER_VALUE_SQL = (
    "(SELECT ident.value FROM identifier ident WHERE ident.paper_id = {fk} "
    "ORDER BY ident.scheme, ident.value LIMIT 1)"
)


def _paper_key(
    title: object, primary_scheme: object, primary_value: object
) -> tuple[object, object]:
    """组装规则 2 的 paper 复合业务键：``(title, (scheme, value) | None)``。

    ``primary_scheme``/``primary_value`` 任一为 None（正常情况下只会同时为 None——
    该 paper 没有任何 identifier，违反域内不变式的边角情形）时，第二位整体记 None。
    """
    if primary_scheme is None or primary_value is None:
        return (title, None)
    return (title, (primary_scheme, primary_value))


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
    primary_scheme_sql = _PRIMARY_IDENTIFIER_SCHEME_SQL.format(fk="a.paper_id")
    primary_value_sql = _PRIMARY_IDENTIFIER_VALUE_SQL.format(fk="a.paper_id")
    rows = db.query(
        "SELECT p.title AS paper_title, "
        f"       {primary_scheme_sql} AS primary_scheme, "
        f"       {primary_value_sql} AS primary_value, "
        "       a.kind, a.version, a.url, a.auth_needed, a.state, a.bytes, a.sha256, "
        "       a.source_adapter "
        "FROM asset a "
        "JOIN paper p ON p.id = a.paper_id "
        "ORDER BY p.title, primary_scheme, primary_value, a.kind, a.version"
    )
    return [
        (
            _paper_key(row["paper_title"], row["primary_scheme"], row["primary_value"]),
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
    primary_scheme_sql = _PRIMARY_IDENTIFIER_SCHEME_SQL.format(fk="l.paper_id")
    primary_value_sql = _PRIMARY_IDENTIFIER_VALUE_SQL.format(fk="l.paper_id")
    rows = db.query(
        "SELECT p.title AS paper_title, "
        f"       {primary_scheme_sql} AS primary_scheme, "
        f"       {primary_value_sql} AS primary_value, "
        "       i.venue_id AS issue_venue_id, i.volume AS issue_volume, "
        "       i.number AS issue_number, i.label AS issue_label "
        "FROM paper_issue_link l "
        "JOIN paper p ON p.id = l.paper_id "
        "JOIN issue i ON i.id = l.issue_id "
        "ORDER BY p.title, primary_scheme, primary_value, "
        "         i.venue_id, i.volume, i.number, i.label"
    )
    return [
        (
            _paper_key(row["paper_title"], row["primary_scheme"], row["primary_value"]),
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


def dump_paper_relations(db_path: Path) -> list[tuple[object, ...]]:
    """`paper_relation` 的 canonical dump（Phase 3 T1 合并引擎新增写入路径）。

    `canonical_dump` 刻意不含此表（Phase 1 无写入路径）；合并引擎的弱信号候审 / 跨 paper
    冲突 / 迁移 doi 碰撞会写 candidate_duplicate，AC-3.4 顺序无关属性测试须逐行比对它。

    `from_paper`/`to_paper`（ULID，跨库不可比）翻译为 paper 复合业务键
    `(title, primary_identifier)`（同 `canonical_dump` 规则 2）；两端点按 repr 排序使
    **方向无关**（写侧已按最小 identifier 定向，dump 侧再排序作双重保险，跨库/跨注入顺序
    的两库对同一对 paper 得同一行）。行按整行 repr 排序，不受插入顺序影响。返回
    `[(endpoints, kind, confidence, evidence_json, decided), ...]`，`endpoints` 为已排序
    的两 paper_key 元组。只读。
    """
    from_scheme = _PRIMARY_IDENTIFIER_SCHEME_SQL.format(fk="r.from_paper")
    from_value = _PRIMARY_IDENTIFIER_VALUE_SQL.format(fk="r.from_paper")
    to_scheme = _PRIMARY_IDENTIFIER_SCHEME_SQL.format(fk="r.to_paper")
    to_value = _PRIMARY_IDENTIFIER_VALUE_SQL.format(fk="r.to_paper")
    db = Database(db_path)
    try:
        rows = db.query(
            "SELECT pf.title AS from_title, "
            f"       {from_scheme} AS from_scheme, {from_value} AS from_value, "
            "       pt.title AS to_title, "
            f"       {to_scheme} AS to_scheme, {to_value} AS to_value, "
            "       r.kind, r.confidence, r.evidence_json, r.decided "
            "FROM paper_relation r "
            "JOIN paper pf ON pf.id = r.from_paper "
            "JOIN paper pt ON pt.id = r.to_paper"
        )
        result: list[tuple[object, ...]] = []
        for row in rows:
            key_from = _paper_key(row["from_title"], row["from_scheme"], row["from_value"])
            key_to = _paper_key(row["to_title"], row["to_scheme"], row["to_value"])
            endpoints = tuple(sorted((key_from, key_to), key=repr))
            result.append(
                (
                    endpoints,
                    row["kind"],
                    row["confidence"],
                    row["evidence_json"],
                    row["decided"],
                )
            )
        return sorted(result, key=repr)
    finally:
        db.close()
