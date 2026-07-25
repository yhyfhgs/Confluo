"""仓储层：领域实体的读写与幂等 upsert（接口冻结件 §2.4 `Repo`）。

关键语义：
- `upsert_paper` 强合并（design/06 §3）：identifier (scheme,value) 命中 → 复用既有
  paper，字段仅补缺不覆盖非空。
- `upsert_issue` 幂等键 UNIQUE(venue_id,volume,number,label)。SQLite UNIQUE 视 NULL 互不相等
  （会议 issue volume/number 为 NULL），故在事务内以业务键 SELECT 后 INSERT（方言中性；
  Phase 1 串行 runner 天然并发安全，见风险表"WAL 单写者"）。
- `plan_asset` 幂等键 UNIQUE(paper_id,kind,version)，version 可空同样 NULL 语义，走查后插；
  已 fetched 的资产再 plan 不回退状态。
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from paper_crawler.errors import CrawlerError, ErrorClass, SubscriptionInvalid
from paper_crawler.ids import normalize_identifier, normalize_title
from paper_crawler.obslog import redact
from paper_crawler.storage.db import Database
from paper_crawler.types import (
    AssetPlan,
    IssueRef,
    PaperStub,
    VenueSpec,
    new_ulid,
    utcnow_iso,
)

if TYPE_CHECKING:  # 仅类型：运行期由 SubscriptionRepo 内的局部 import 承担（见其 docstring）
    from paper_crawler.subs.model import Subscription

# MergeEngine.ingest 的动作枚举（接口冻结件 §2-1）。定义在 repo 层，供 merge.py 复用其
# `IngestResult.action` 的类型——避免 repo→merge 反向导入形成环（merge 依赖 repo）。
IngestAction = Literal["created", "merged", "candidate_flagged"]

# 弱信号候审 / 跨 paper identifier 冲突的 candidate_duplicate 置信度（固定常量→确定性）。
_WEAK_SIGNAL_CONFIDENCE = 0.5
_IDENTIFIER_CONFLICT_CONFIDENCE = 0.9
# 未知来源（无 provenance 记录的存量字段，如 upsert_paper pull 路径所写）的优先级视为
# **最高**——只补空、绝不被覆盖，保守保护既有（多为官方 proceedings）数据。
_UNKNOWN_RANK = float("inf")


@dataclass(frozen=True)
class IngestOutcome:
    """`Repo.merge_ingest` 的返回值——`MergeEngine.ingest` 原样包装为 `IngestResult`。

    与 `IngestResult` 字段一一对应，独立于 merge.py 存在以断开 repo↔merge 导入环。
    """

    paper_id: str
    action: IngestAction
    matched_identifiers: tuple[str, ...]


@dataclass(frozen=True)
class MergeInput:
    """`Repo.merge_ingest` 的入参字段包（merge↔repo 契约）——由 `MergeEngine` 构造并归一
    （identifiers/title_norm/first_author 归一、注入 `priority` 优先级表）后传入。打包成值
    对象避免长参数列表，并把「策略在 merge、机制在 repo」的边界物化为一个类型。"""

    title: str
    title_norm: str
    first_author: str | None
    abstract: str | None
    year: int | None
    pub_date: str | None
    meta: tuple[tuple[str, str], ...]
    source: str
    priority: Mapping[str, int]


@dataclass(frozen=True)
class FetchLogRow:
    """`finalize_fetch` 的 fetch_log 载荷（id/asset_id/ts 由 repo 生成，不在此）。

    与 `add_fetch_log` 的关键字参数一一对应，仅打包成一个不可变值对象，便于把"取回
    审计行"作为一个整体传给组合事务 API。`url` 由 repo 落库前统一经 `redact` 脱敏。
    """

    task_id: str | None
    domain: str
    url: str
    http_status: int | None
    bytes_: int
    elapsed_ms: int
    rate_wait_ms: int
    error_class: str | None = None


def _meta_to_json(meta: tuple[tuple[str, str], ...]) -> str | None:
    """把弹性 meta（tuple-of-tuples）序列化为 JSON 文本；空则 None。"""
    if not meta:
        return None
    return json.dumps(dict(meta), ensure_ascii=False, sort_keys=True)


def _null_safe_eq(column: str, value: object, params: list[object]) -> str:
    """生成方言中性的 NULL-安全等值子句：None → `col IS NULL`，否则 `col = ?`。

    避免 SQLite 专有的 `col IS ?`（PostgreSQL 需 `IS NOT DISTINCT FROM`）。
    """
    if value is None:
        return f"{column} IS NULL"
    params.append(value)
    return f"{column} = ?"


def _is_empty(value: object) -> bool:
    """字段级收敛的"空值"判定：None 或空串视为空（可被任意来源填补）。int 0 不算空。"""
    return value is None or value == ""


def _rank(priority: Mapping[str, int], source: str | None) -> float:
    """来源优先级排名（越大越强）。未记录/未知来源 → 最高（`_UNKNOWN_RANK`，只补空不覆盖）。"""
    if source is None:
        return _UNKNOWN_RANK
    known = priority.get(source)
    return _UNKNOWN_RANK if known is None else float(known)


class Repo:
    """领域仓储；所有写操作经 `Database` 的 autocommit / 事务上下文落库。"""

    def __init__(self, db: Database) -> None:
        self.db = db

    # -- venue ---------------------------------------------------------------

    def upsert_venue(self, spec: VenueSpec) -> None:
        """按 id 幂等写入 venue，附 VenueSpec 快照（审计）。就地 UPDATE，保留子行外键。"""
        self.db.execute(
            "INSERT INTO venue (id, kind, name, field_json, tier, spec_snapshot_json, status) "
            "VALUES (?,?,?,?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET "
            "  kind=excluded.kind, name=excluded.name, field_json=excluded.field_json, "
            "  tier=excluded.tier, spec_snapshot_json=excluded.spec_snapshot_json, "
            "  status=excluded.status",
            (
                spec.id,
                spec.kind,
                spec.names.full,
                json.dumps(spec.field, ensure_ascii=False),
                spec.tier,
                spec.model_dump_json(),
                spec.status,
            ),
        )

    # -- issue ---------------------------------------------------------------

    def upsert_issue(self, ref: IssueRef, source: str) -> str:
        """幂等写入 issue，返回 issue_id。业务键 (venue_id,volume,number,label) 查后插。"""
        with self.db.tx() as conn:
            params: list[object] = [ref.venue_id]
            where = " AND ".join(
                [
                    "venue_id = ?",
                    _null_safe_eq("volume", ref.volume, params),
                    _null_safe_eq("number", ref.number, params),
                    _null_safe_eq("label", ref.label, params),
                ]
            )
            existing = conn.execute(f"SELECT id FROM issue WHERE {where}", params).fetchone()
            if existing is not None:
                return str(existing["id"])
            issue_id = new_ulid()
            conn.execute(
                "INSERT INTO issue "
                "(id, venue_id, era_id, volume, number, year, label, pub_date, source, "
                " paper_count_claimed) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    issue_id,
                    ref.venue_id,
                    None,
                    ref.volume,
                    ref.number,
                    ref.year,
                    ref.label,
                    ref.pub_date,
                    source,
                    ref.paper_count_claimed,
                ),
            )
            return issue_id

    def list_issues(
        self,
        venue_id: str,
        *,
        volume: str | None = None,
        number: str | None = None,
        year: int | None = None,
    ) -> list[sqlite3.Row]:
        """列出某 venue 的 issue，可按 volume/number/year 过滤；按卷/期稳定排序。"""
        clauses = ["venue_id = ?"]
        params: list[object] = [venue_id]
        if volume is not None:
            clauses.append("volume = ?")
            params.append(volume)
        if number is not None:
            clauses.append("number = ?")
            params.append(number)
        if year is not None:
            clauses.append("year = ?")
            params.append(year)
        sql = (
            "SELECT * FROM issue WHERE "
            + " AND ".join(clauses)
            + " ORDER BY year, volume, number, label"
        )
        return self.db.query(sql, params)

    # -- paper ---------------------------------------------------------------

    def upsert_paper(self, venue_id: str, issue_id: str | None, stub: PaperStub) -> str:
        """强合并 upsert：identifier 命中 → 复用 paper 并补缺字段；否则新建。幂等建 issue 链。

        design/06 §3 强合并锚点：任一 (scheme,value) 命中既有 identifier → 返回该 paper_id，
        新字段仅填补空缺、不覆盖非空。

        **identifier 归一（D-裁决 2026-07-22）**：写入前经 `ids.normalize_identifier`
        （scheme=doi 的值小写化/剥前缀，其余原样）——与 `MergeEngine` 共用同一归一入口，
        使 pull 路径与 aggregator 路径的 DOI 键收敛到同一规范形（AC-3.1 混合双路无条件命中）。

        **title_norm 维护**：新建 paper 时一并写 `title_norm`（schema v2 列，`normalize_title`）
        ——使 pull 路径 paper 也进弱信号候审匹配面（否则 title_norm=NULL 对 MergeEngine 的
        title 匹配不可见），且与 0002 迁移的存量回填口径一致。title 是强合并锚点、恒不更新，
        故 title_norm 仅在建行时写、合并分支不动。
        """
        identifiers = tuple(
            normalize_identifier(scheme, value) for scheme, value in stub.identifiers
        )
        with self.db.tx() as conn:
            paper_id: str | None = None
            for scheme, value in identifiers:
                hit = conn.execute(
                    "SELECT paper_id FROM identifier WHERE scheme = ? AND value = ?",
                    (scheme, value),
                ).fetchone()
                if hit is not None:
                    paper_id = str(hit["paper_id"])
                    break

            now = utcnow_iso()
            if paper_id is None:
                paper_id = new_ulid()
                conn.execute(
                    "INSERT INTO paper "
                    "(id, title, abstract, year, pub_date, venue_id, meta_json, title_norm, "
                    " ingest_state, created_at, updated_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        paper_id,
                        stub.title,
                        stub.abstract,
                        stub.year,
                        stub.pub_date,
                        venue_id,
                        _meta_to_json(stub.meta),
                        normalize_title(stub.title),
                        "metadata_only",
                        now,
                        now,
                    ),
                )
            else:
                self._merge_paper_fields(conn, paper_id, stub, now)

            self._ensure_identifiers(conn, paper_id, identifiers)

            if issue_id is not None:
                conn.execute(
                    "INSERT INTO paper_issue_link (paper_id, issue_id) VALUES (?,?) "
                    "ON CONFLICT (paper_id, issue_id) DO NOTHING",
                    (paper_id, issue_id),
                )
            return paper_id

    @staticmethod
    def _merge_paper_fields(
        conn: sqlite3.Connection,
        paper_id: str,
        stub: PaperStub,
        now: str,
    ) -> None:
        """补缺不覆盖：仅当既有列为空/NULL 时用 stub 的非空值填充。

        合并的是跨源可残缺的字段（abstract/year/pub_date/meta）。title 是必填的强合并锚点
        （PaperStub 恒有值），venue_id 建 paper 时即由外键约束绑定，二者不参与补缺。
        """
        existing = conn.execute("SELECT * FROM paper WHERE id = ?", (paper_id,)).fetchone()
        updates: dict[str, object] = {}
        if not existing["abstract"] and stub.abstract:
            updates["abstract"] = stub.abstract
        if existing["year"] is None and stub.year is not None:
            updates["year"] = stub.year
        if not existing["pub_date"] and stub.pub_date:
            updates["pub_date"] = stub.pub_date
        if not existing["meta_json"] and stub.meta:
            updates["meta_json"] = _meta_to_json(stub.meta)
        if not updates:
            return
        updates["updated_at"] = now
        set_clause = ", ".join(f"{col} = ?" for col in updates)
        conn.execute(
            f"UPDATE paper SET {set_clause} WHERE id = ?",
            (*updates.values(), paper_id),
        )

    @staticmethod
    def _ensure_identifiers(
        conn: sqlite3.Connection, paper_id: str, identifiers: tuple[tuple[str, str], ...]
    ) -> None:
        """确保每个（已归一的）identifier 存在并指向 paper_id；已存在的保持不动（全局唯一锚点）。

        `is_primary` 单一性：一个 paper 至多一个 primary。仅当该 paper 尚无 primary 时，
        才把首个（index==0）**新增** identifier 标为 primary；合并进已有 primary 的
        paper 时新来者一律非 primary（否则合并路径会产生双 is_primary）。入参 `identifiers`
        已由调用方经 `ids.normalize_identifier` 归一。
        """
        has_primary = (
            conn.execute(
                "SELECT 1 FROM identifier WHERE paper_id = ? AND is_primary = 1 LIMIT 1",
                (paper_id,),
            ).fetchone()
            is not None
        )
        for index, (scheme, value) in enumerate(identifiers):
            present = conn.execute(
                "SELECT paper_id FROM identifier WHERE scheme = ? AND value = ?",
                (scheme, value),
            ).fetchone()
            if present is None:
                is_primary = 1 if (index == 0 and not has_primary) else 0
                conn.execute(
                    "INSERT INTO identifier (paper_id, scheme, value, is_primary) VALUES (?,?,?,?)",
                    (paper_id, scheme, value, is_primary),
                )
                if is_primary:
                    has_primary = True

    # -- merge engine 组合事务（Phase 3 T1；接口冻结件 §2-1） -----------------

    def merge_ingest(
        self, incoming: MergeInput, identifiers: tuple[tuple[str, str], ...]
    ) -> IngestOutcome:
        """`MergeEngine.ingest` 的原子机制载体（查→并→补 单事务；SQL/事务在 repo，策略注入）。

        沿 `finalize_fetch` 先例：整条「identifier 查重 → 分支（新建 / 强合并 / 跨 paper
        冲突 / 弱信号候审）→ 字段级来源优先级收敛 → 补 identifier / 建 candidate_duplicate」
        在单个 `BEGIN IMMEDIATE` 事务内完成——立即取写锁，读+写同一快照，杜绝并发裂脑
        （plan §2-1「防并发裂脑」）。`identifiers` 已由 MergeEngine 经 `ids.normalize_identifier`
        归一（含 doi）。裁决语义的**权威说明在 merge.py docstring**（跨冲突取 identifier 多者/
        平局小 id、弱信号绝不自动合并、未知 provenance 视最高、candidate 端点按最小 identifier
        定向）；本方法只承载其 SQL 机制。返回 `IngestOutcome`，由 MergeEngine 包装为
        `IngestResult`。
        """
        with self.db.tx() as conn:
            matched: list[str] = []
            hit_papers: dict[str, None] = {}
            for scheme, value in identifiers:
                row = conn.execute(
                    "SELECT paper_id FROM identifier WHERE scheme = ? AND value = ?",
                    (scheme, value),
                ).fetchone()
                if row is not None:
                    hit_papers.setdefault(str(row["paper_id"]), None)
                    matched.append(f"{scheme}:{value}")

            distinct = list(hit_papers)
            if not distinct:
                return self._merge_ingest_no_hit(conn, incoming, identifiers)
            if len(distinct) == 1:
                paper_id = distinct[0]
                self._converge_fields(conn, paper_id, incoming)
                self._ensure_identifiers(conn, paper_id, identifiers)
                return IngestOutcome(paper_id, "merged", tuple(matched))
            return self._merge_ingest_conflict(
                conn, distinct, incoming, identifiers, tuple(matched)
            )

    def _merge_ingest_no_hit(
        self,
        conn: sqlite3.Connection,
        incoming: MergeInput,
        identifiers: tuple[tuple[str, str], ...],
    ) -> IngestOutcome:
        """无 identifier 命中：弱信号候审（title_norm 精确匹配 + 首作者姓氏一致）或纯新建。

        弱信号**绝不自动合并**（06 §3：WP↔刊发版标题常变，宁可两条待审）——新建 paper 后
        对**每个**匹配到的既有 paper 建 candidate_duplicate。「对每个匹配都建边」而非「只对
        其一」是顺序无关的关键：任意注入顺序下，同 (title_norm, first_author) 簇内的每对
        paper 最终都被建边（后建者对先在者建边），终态 = 该簇全体两两 candidate，与顺序无关
        （AC-3.4）。title_norm 为空或 stub 无首作者时不触发弱信号（避免空键误配）。
        """
        matches: list[str] = []
        if incoming.title_norm and incoming.first_author is not None:
            rows = conn.execute(
                "SELECT id FROM paper WHERE title_norm = ? ORDER BY id",
                (incoming.title_norm,),
            ).fetchall()
            for row in rows:
                pid = str(row["id"])
                if self._read_first_author(conn, pid) == incoming.first_author:
                    matches.append(pid)

        new_id = self._create_paper(conn, incoming, identifiers)
        if not matches:
            return IngestOutcome(new_id, "created", ())
        for other in matches:
            self._insert_candidate(
                conn,
                new_id,
                other,
                _WEAK_SIGNAL_CONFIDENCE,
                {
                    "reason": "weak-signal-title-author",
                    "title_norm": incoming.title_norm,
                    "first_author": incoming.first_author,
                },
            )
        return IngestOutcome(new_id, "candidate_flagged", ())

    def _merge_ingest_conflict(
        self,
        conn: sqlite3.Connection,
        distinct: list[str],
        incoming: MergeInput,
        identifiers: tuple[tuple[str, str], ...],
        matched: tuple[str, ...],
    ) -> IngestOutcome:
        """跨 paper identifier 冲突（stub 的 identifier 命中≥2 个不同既有 paper）。

        裁决（plan §2-1 / merge.py docstring）：**不自动合并两 paper**；stub 并入 identifier
        数最多者（平局取 paper_id 字典序最小者——确定性），其余每个命中 paper 与胜者建
        candidate_duplicate(evidence=identifier-conflict) 留人审。stub 的 identifier 里指向
        败者的那些**原地不动**（`_ensure_identifiers` 只补库中尚不存在的孤儿 identifier，
        不重指既存者）——绝不物理迁移 identifier 行。
        """
        winner = min(distinct, key=lambda pid: (-self._identifier_count(conn, pid), pid))
        self._converge_fields(conn, winner, incoming)
        self._ensure_identifiers(conn, winner, identifiers)
        for other in distinct:
            if other != winner:
                self._insert_candidate(
                    conn,
                    winner,
                    other,
                    _IDENTIFIER_CONFLICT_CONFIDENCE,
                    {"reason": "identifier-conflict", "identifiers": sorted(matched)},
                )
        return IngestOutcome(winner, "candidate_flagged", matched)

    def _create_paper(
        self,
        conn: sqlite3.Connection,
        incoming: MergeInput,
        identifiers: tuple[tuple[str, str], ...],
    ) -> str:
        """新建 paper（venue-agnostic：venue_id=NULL，MergeEngine 冻结签名不带 venue）。

        建库时所有非空入参字段记 provenance=incoming.source（`_field_src`）；首作者姓氏存
        `meta_json._first_author`（弱信号比对锚，types.py PaperStub.authors 冻结为名字串组，
        不改 types——由现有字段推导）。`title_norm` 落 schema v2 列。
        """
        paper_id = new_ulid()
        now = utcnow_iso()
        meta_obj: dict[str, object] = dict(incoming.meta)
        field_src: dict[str, str] = {"title": incoming.source}
        if incoming.abstract:
            field_src["abstract"] = incoming.source
        if incoming.year is not None:
            field_src["year"] = incoming.source
        if incoming.pub_date:
            field_src["pub_date"] = incoming.source
        if incoming.first_author is not None:
            meta_obj["_first_author"] = incoming.first_author
            field_src["authors"] = incoming.source
        for key, _value in incoming.meta:
            field_src[f"meta:{key}"] = incoming.source
        meta_obj["_field_src"] = field_src
        conn.execute(
            "INSERT INTO paper "
            "(id, title, abstract, year, pub_date, venue_id, meta_json, title_norm, "
            " ingest_state, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                paper_id,
                incoming.title,
                incoming.abstract,
                incoming.year,
                incoming.pub_date,
                None,
                json.dumps(meta_obj, ensure_ascii=False, sort_keys=True),
                incoming.title_norm,
                "metadata_only",
                now,
                now,
            ),
        )
        self._ensure_identifiers(conn, paper_id, identifiers)
        return paper_id

    def _converge_fields(
        self, conn: sqlite3.Connection, paper_id: str, incoming: MergeInput
    ) -> None:
        """字段级来源优先级收敛（AC-3.4 基石）：新值仅当①现值空 或 ②新源优先级严格高时写入。

        provenance 记于 `meta_json._field_src`（field_key→source）；未记录来源的存量字段
        （upsert_paper pull 路径所写）视为最高优先（`_rank` 返回 `_UNKNOWN_RANK`）——只补空、
        绝不覆盖。收敛字段：title（连带 title_norm 列）/abstract/year/pub_date/首作者姓氏
        （`authors`→`_first_author`）/每个 meta 键（`meta:<k>`）。同级不覆盖（`>` 严格），故
        任意到达顺序收敛到同一终态。
        """
        row = conn.execute(
            "SELECT title, abstract, year, pub_date, meta_json FROM paper WHERE id = ?",
            (paper_id,),
        ).fetchone()
        meta_obj: dict[str, object] = json.loads(row["meta_json"]) if row["meta_json"] else {}
        raw_src = meta_obj.get("_field_src")
        field_src: dict[str, str] = dict(raw_src) if isinstance(raw_src, dict) else {}
        col_updates: dict[str, object] = {}

        def better(field_key: str, incoming_value: object, current_value: object) -> bool:
            if _is_empty(incoming_value):
                return False
            if _is_empty(current_value):
                return True
            return _rank(incoming.priority, incoming.source) > _rank(
                incoming.priority, field_src.get(field_key)
            )

        if better("title", incoming.title, row["title"]):
            col_updates["title"] = incoming.title
            col_updates["title_norm"] = incoming.title_norm
            field_src["title"] = incoming.source
        if better("abstract", incoming.abstract, row["abstract"]):
            col_updates["abstract"] = incoming.abstract
            field_src["abstract"] = incoming.source
        if better("year", incoming.year, row["year"]):
            col_updates["year"] = incoming.year
            field_src["year"] = incoming.source
        if better("pub_date", incoming.pub_date, row["pub_date"]):
            col_updates["pub_date"] = incoming.pub_date
            field_src["pub_date"] = incoming.source
        if incoming.first_author is not None and better(
            "authors", incoming.first_author, meta_obj.get("_first_author")
        ):
            meta_obj["_first_author"] = incoming.first_author
            field_src["authors"] = incoming.source
        for key, value in incoming.meta:
            if better(f"meta:{key}", value, meta_obj.get(key)):
                meta_obj[key] = value
                field_src[f"meta:{key}"] = incoming.source

        if field_src:
            meta_obj["_field_src"] = field_src
        new_meta_json = (
            json.dumps(meta_obj, ensure_ascii=False, sort_keys=True) if meta_obj else None
        )
        if col_updates or new_meta_json != row["meta_json"]:
            col_updates["meta_json"] = new_meta_json
            col_updates["updated_at"] = utcnow_iso()
            set_clause = ", ".join(f"{col} = ?" for col in col_updates)
            conn.execute(
                f"UPDATE paper SET {set_clause} WHERE id = ?",
                (*col_updates.values(), paper_id),
            )

    @staticmethod
    def _identifier_count(conn: sqlite3.Connection, paper_id: str) -> int:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM identifier WHERE paper_id = ?", (paper_id,)
        ).fetchone()
        return int(row["n"])

    @staticmethod
    def _read_first_author(conn: sqlite3.Connection, paper_id: str) -> str | None:
        row = conn.execute("SELECT meta_json FROM paper WHERE id = ?", (paper_id,)).fetchone()
        if row is None or not row["meta_json"]:
            return None
        value = json.loads(row["meta_json"]).get("_first_author")
        return value if isinstance(value, str) else None

    @staticmethod
    def _paper_min_identifier(conn: sqlite3.Connection, paper_id: str) -> tuple[str, str]:
        """paper 名下按 (scheme,value) 字典序最小的 identifier；无则 ('','')。candidate 定向锚。"""
        row = conn.execute(
            "SELECT scheme, value FROM identifier WHERE paper_id = ? "
            "ORDER BY scheme, value LIMIT 1",
            (paper_id,),
        ).fetchone()
        return (str(row["scheme"]), str(row["value"])) if row is not None else ("", "")

    def _insert_candidate(
        self,
        conn: sqlite3.Connection,
        paper_a: str,
        paper_b: str,
        confidence: float,
        evidence: dict[str, object],
    ) -> None:
        """建 candidate_duplicate(decided=NULL)；端点按各自最小 identifier 定向（顺序无关）。"""
        if self._paper_min_identifier(conn, paper_a) <= self._paper_min_identifier(conn, paper_b):
            from_paper, to_paper = paper_a, paper_b
        else:
            from_paper, to_paper = paper_b, paper_a
        conn.execute(
            "INSERT INTO paper_relation "
            "(from_paper, to_paper, kind, confidence, evidence_json, decided) "
            "VALUES (?,?,?,?,?,?) "
            "ON CONFLICT (from_paper, to_paper, kind) DO NOTHING",
            (
                from_paper,
                to_paper,
                "candidate_duplicate",
                confidence,
                json.dumps(evidence, ensure_ascii=False, sort_keys=True),
                None,
            ),
        )

    def list_papers(self, venue_id: str, issue_id: str | None = None) -> list[sqlite3.Row]:
        """列出某 venue 的 paper；给定 issue_id 时限定该期内（经 paper_issue_link）。按标题排序。"""
        if issue_id is not None:
            return self.db.query(
                "SELECT p.* FROM paper p "
                "JOIN paper_issue_link l ON p.id = l.paper_id "
                "WHERE p.venue_id = ? AND l.issue_id = ? "
                "ORDER BY p.title, p.id",
                (venue_id, issue_id),
            )
        return self.db.query(
            "SELECT * FROM paper WHERE venue_id = ? ORDER BY title, id", (venue_id,)
        )

    def set_paper_state(self, paper_id: str, ingest_state: str) -> None:
        """更新 paper.ingest_state（metadata_only|resolved|fetched|extracted）。"""
        self.db.execute(
            "UPDATE paper SET ingest_state = ?, updated_at = ? WHERE id = ?",
            (ingest_state, utcnow_iso(), paper_id),
        )

    def bind_paper_venue(self, paper_id: str, venue_id: str) -> None:
        """把**尚未绑定 venue** 的 paper 绑定到 venue_id（`grab` 单篇路径）。

        `MergeEngine.ingest`（crossref 等 aggregator 路径）建的 paper venue_id=NULL；grab 须
        绑定后 fetch 才可经 asset→paper→venue_id 路由到目标平台 adapter。`WHERE venue_id IS
        NULL` 保证幂等且**不改写既有归属**（保守——反查命中的已绑定 paper 不动）。
        """
        self.db.execute(
            "UPDATE paper SET venue_id = ?, updated_at = ? WHERE id = ? AND venue_id IS NULL",
            (venue_id, utcnow_iso(), paper_id),
        )

    # -- asset ---------------------------------------------------------------

    def plan_asset(self, paper_id: str, plan: AssetPlan, source_adapter: str) -> str:
        """幂等登记一个 planned asset，返回 asset_id。业务键 (paper_id,kind,version) 查后插；
        已存在（含已 fetched）则原样返回既有 id，不回退状态。"""
        with self.db.tx() as conn:
            params: list[object] = [paper_id, plan.kind.value]
            where = " AND ".join(
                [
                    "paper_id = ?",
                    "kind = ?",
                    _null_safe_eq("version", plan.version, params),
                ]
            )
            existing = conn.execute(f"SELECT id FROM asset WHERE {where}", params).fetchone()
            if existing is not None:
                return str(existing["id"])
            asset_id = new_ulid()
            conn.execute(
                "INSERT INTO asset "
                "(id, paper_id, kind, version, url, auth_needed, state, file_path, bytes, "
                " sha256, fetched_at, source_adapter) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    asset_id,
                    paper_id,
                    plan.kind.value,
                    plan.version,
                    plan.url,
                    plan.auth_needed.value,
                    "planned",
                    None,
                    None,
                    None,
                    None,
                    source_adapter,
                ),
            )
            return asset_id

    def refresh_asset_plan(self, asset_id: str, *, url: str, auth_needed: str) -> None:
        """fetch 前 re-resolve 后同步 asset 行的执行细节（T7c 追加设计裁决，phase1-plan）。

        asset 的幂等身份 = (paper, kind, version) 不变；url/auth_needed 属执行细节，
        fetch 子任务执行时现场 resolve 取最新值后经本方法落库再 fetch（signed url /
        entitlement 时效、mock 故障注入解除等场景）。**已 fetched 的不回退不改**；
        其余状态（planned/failed 等）只刷新这两列、不触碰状态机。asset 不存在时
        零行更新、静默返回（缺行由 fetch 阶段自身的 CONFIG 路由处理）。
        """
        self.db.execute(
            "UPDATE asset SET url = ?, auth_needed = ? WHERE id = ? AND state <> 'fetched'",
            (url, auth_needed, asset_id),
        )

    def list_assets(
        self, *, venue_id: str | None = None, state: str | None = None
    ) -> list[sqlite3.Row]:
        """列出 asset，可按 venue（经 paper 关联）与 state 过滤；稳定排序。"""
        sql = "SELECT a.* FROM asset a"
        clauses: list[str] = []
        params: list[object] = []
        if venue_id is not None:
            sql += " JOIN paper p ON a.paper_id = p.id"
            clauses.append("p.venue_id = ?")
            params.append(venue_id)
        if state is not None:
            clauses.append("a.state = ?")
            params.append(state)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY a.paper_id, a.kind, a.version"
        return self.db.query(sql, params)

    def get_asset(self, asset_id: str) -> sqlite3.Row | None:
        """按 id 取单个 asset；不存在返回 None。"""
        rows = self.db.query("SELECT * FROM asset WHERE id = ?", (asset_id,))
        return rows[0] if rows else None

    def mark_asset(
        self,
        asset_id: str,
        *,
        state: str,
        file_path: str | None = None,
        bytes_: int | None = None,
        sha256: str | None = None,
    ) -> None:
        """更新 asset 状态与下载产物字段；state='fetched' 时补记 fetched_at。"""
        updates: dict[str, object] = {"state": state}
        if file_path is not None:
            updates["file_path"] = file_path
        if bytes_ is not None:
            updates["bytes"] = bytes_
        if sha256 is not None:
            updates["sha256"] = sha256
        if state == "fetched":
            updates["fetched_at"] = utcnow_iso()
        set_clause = ", ".join(f"{col} = ?" for col in updates)
        self.db.execute(
            f"UPDATE asset SET {set_clause} WHERE id = ?",
            (*updates.values(), asset_id),
        )

    # -- fetch_log -----------------------------------------------------------

    def add_fetch_log(
        self,
        *,
        asset_id: str | None,
        task_id: str | None,
        domain: str,
        url: str,
        http_status: int | None,
        bytes_: int,
        elapsed_ms: int,
        rate_wait_ms: int,
        error_class: str | None = None,
    ) -> None:
        """追加一条取回审计记录（FetchLog；限速合规证据源，design/05 §7）。

        `url` 落库前经 `obslog.redact`（AC-0.4/NFR-8：fetch_log.url 不得含未脱敏凭证——
        Phase 2 起签名 URL/token 会进入此审计路径）。
        """
        self.db.execute(
            "INSERT INTO fetch_log "
            "(id, asset_id, task_id, domain, url, http_status, bytes, elapsed_ms, "
            " rate_wait_ms, error_class, ts) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                new_ulid(),
                asset_id,
                task_id,
                domain,
                redact(url),
                http_status,
                bytes_,
                elapsed_ms,
                rate_wait_ms,
                error_class,
                utcnow_iso(),
            ),
        )

    def finalize_fetch(
        self,
        asset_id: str,
        *,
        file_path: str,
        bytes_: int,
        sha256: str | None,
        fetch_log_row: FetchLogRow,
    ) -> None:
        """fetch 成功收尾的组合事务 API（Phase 2 T1；仓储层唯一的组合事务入口）。

        在单个 `BEGIN IMMEDIATE` 事务内原子完成两步：
          1. asset → state='fetched'（并补 file_path/bytes/sha256/fetched_at）；
          2. 追加一条成功 fetch_log 行（url 经 `redact` 脱敏，与 `add_fetch_log` 同源）。

        取代旧的 `mark_asset(fetched)` + `add_fetch_log` 两次独立提交——消除二者之间的
        SIGKILL 缝隙（AC-1.3："已 fetched 但成功日志缺失"的已知窗口）。**直接组合 SQL、
        不调用自带事务的 `mark_asset`/`add_fetch_log`**（repo 事务不可嵌套）。事务中途
        任何异常都整体 ROLLBACK（asset 状态与日志同进同退）。
        """
        now = utcnow_iso()
        with self.db.tx() as conn:
            conn.execute(
                "UPDATE asset SET state = 'fetched', file_path = ?, bytes = ?, sha256 = ?, "
                "fetched_at = ? WHERE id = ?",
                (file_path, bytes_, sha256, now, asset_id),
            )
            conn.execute(
                "INSERT INTO fetch_log "
                "(id, asset_id, task_id, domain, url, http_status, bytes, elapsed_ms, "
                " rate_wait_ms, error_class, ts) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    new_ulid(),
                    asset_id,
                    fetch_log_row.task_id,
                    fetch_log_row.domain,
                    redact(fetch_log_row.url),
                    fetch_log_row.http_status,
                    fetch_log_row.bytes_,
                    fetch_log_row.elapsed_ms,
                    fetch_log_row.rate_wait_ms,
                    fetch_log_row.error_class,
                    now,
                ),
            )

    def fetch_logs(self, *, domain: str | None = None) -> list[sqlite3.Row]:
        """取回 FetchLog，可按 domain 过滤；按时间戳稳定排序。"""
        if domain is not None:
            return self.db.query(
                "SELECT * FROM fetch_log WHERE domain = ? ORDER BY ts, id", (domain,)
            )
        return self.db.query("SELECT * FROM fetch_log ORDER BY ts, id")

    def count_fetch_today(self, domain: str) -> int:
        """某 domain **当日（UTC）fetch 尝试篇次**（auth-framework §8.3；AC-4.4 日配额对账）。

        口径统一为"fetch 尝试篇次"：fetch 阶段每次尝试落一行 fetch_log（design/05 §7），
        **成败均计**（失败行 error_class 非空同样计入，故不加 error_class 过滤）；resolve
        页请求不写 fetch_log、天然不计。`ts` 是 fetch_log 实名列，`DATE(ts)=DATE('now')`
        经索引 `idx_fetch_log_domain_ts` 支撑（`ts` 存 UTC ISO8601，SQLite DATE() 归一到
        UTC 日）。OA-fallback direct fetch 落第三方 OA host 域、非 auth 平台 domain，按本
        查询天然不占 auth 平台配额（§8.1 限速隔离的对账侧印证）。
        """
        rows = self.db.query(
            "SELECT COUNT(*) AS n FROM fetch_log WHERE domain = ? AND DATE(ts) = DATE('now')",
            (domain,),
        )
        return int(rows[0]["n"])

    # -- 对账 ----------------------------------------------------------------

    def counts(self, venue_id: str) -> dict[str, int]:
        """AC-1.1 对账口径：某 venue 的 issue/paper 数，及 asset 计划总数与已取回数。

        `assets_planned` = 该 venue 全部 asset 行（每个 asset 建立即为已计划）；
        `assets_fetched` = 其中 state='fetched' 的行数。二者构成"计划 vs 完成"对账。
        """

        def scalar(sql: str) -> int:
            return int(self.db.query(sql, (venue_id,))[0]["n"])

        return {
            "issues": scalar("SELECT COUNT(*) AS n FROM issue WHERE venue_id = ?"),
            "papers": scalar("SELECT COUNT(*) AS n FROM paper WHERE venue_id = ?"),
            "assets_planned": scalar(
                "SELECT COUNT(*) AS n FROM asset a "
                "JOIN paper p ON a.paper_id = p.id WHERE p.venue_id = ?"
            ),
            "assets_fetched": scalar(
                "SELECT COUNT(*) AS n FROM asset a "
                "JOIN paper p ON a.paper_id = p.id "
                "WHERE p.venue_id = ? AND a.state = 'fetched'"
            ),
        }


class SubscriptionRepo:
    """订阅仓储（Phase 6 T1 冻结件）：`subscription` / `subscription_run` 两表 + watermark。

    与 `Repo` 并列而非合并——订阅是独立聚合根（design/06 §1 ER：Subscription 1─N
    SubscriptionRun），与论文/资产那套没有共享事务面；分开也让 T4/T5 的消费面只暴露
    它们真正需要的方法。

    **DSL 类型走局部 import**（沿 `db.py::_backfill_title_norm` 的先例："局部 import
    避免 storage 层顶层依赖上层模块"）：`subs.model` 反过来不依赖 storage，故本类
    与订阅域之间恒无导入环——即使 T5 之后把 `subs/watch.py`（依赖本类）导出到
    `subs/__init__.py` 也不会成环。

    表结构核对（design/06 §2 ↔ `migrations/0001_init.sql`）：两表逐列一致，本卡未改表。

    - `subscription(name PK, query_json NOT NULL, watermark_json, guard_json,
      created_at, last_run_at)`；
    - `subscription_run(id PK, name REFERENCES subscription, started_at, new_count,
      fetched_count, truncated, report_path)`。

    时间列一律 UTC ISO8601（`utcnow_iso`），`truncated` 用 0/1 整数（SQLite 无 bool，
    方言中性；读出时归一为 Python bool 由调用方按需转换）。
    """

    def __init__(self, db: Database) -> None:
        self.db = db

    # -- subscription CRUD ---------------------------------------------------

    def upsert(self, subscription: Subscription) -> None:
        """按 name 幂等写入订阅（DSL 主体 + 护栏）。

        **只更新 `query_json`/`guard_json`**：`watermark_json`/`created_at`/`last_run_at`
        是运行期状态，改订阅内容（如收窄正则）绝不能顺手把增量游标清零——否则下一次
        watch 会把整个历史窗重刷一遍（design/09 §5 增量语义的基本要求）。
        """
        self.db.execute(
            "INSERT INTO subscription "
            "(name, query_json, watermark_json, guard_json, created_at, last_run_at) "
            "VALUES (?,?,?,?,?,?) "
            "ON CONFLICT(name) DO UPDATE SET "
            "  query_json=excluded.query_json, guard_json=excluded.guard_json",
            (
                subscription.name,
                # sort_keys=False：`to_query_dict()` 已是确定序，含 sources 声明序（P1-1）。
                _json_text(subscription.to_query_dict(), sort_keys=False),
                None,
                _json_text(subscription.guard.to_dict(), sort_keys=False),
                utcnow_iso(),
                None,
            ),
        )

    def get(self, name: str) -> Subscription | None:
        """按 name 取订阅并**还原为 `Subscription`**；不存在返回 None。

        还原走 `Subscription.from_stored`（= 文件加载的同一校验器）：库内存量若因
        手改/旧版本而不合法，此处响亮报错（`SubscriptionInvalid`），不返回半截对象。
        """
        rows = self.db.query("SELECT * FROM subscription WHERE name = ?", (name,))
        return self._row_to_subscription(rows[0]) if rows else None

    def all(self) -> list[Subscription]:
        """全部订阅，按 name 排序（确定性输出，`watch --all` 的遍历序）。"""
        rows = self.db.query("SELECT * FROM subscription ORDER BY name")
        return [self._row_to_subscription(row) for row in rows]

    @staticmethod
    def _row_to_subscription(row: sqlite3.Row) -> Subscription:
        """`subscription` 行 → `Subscription`（`get`/`all` 的单一还原路径）。"""
        from paper_crawler.subs.model import Subscription

        guard_json = row["guard_json"]
        return Subscription.from_stored(
            str(row["name"]),
            str(row["query_json"]),
            str(guard_json) if guard_json is not None else None,
        )

    def list_names(self) -> list[str]:
        """全部订阅名（升序）——不做 DSL 反序列化，供只需清单的调用方。"""
        rows = self.db.query("SELECT name FROM subscription ORDER BY name")
        return [str(row["name"]) for row in rows]

    def delete(self, name: str) -> bool:
        """删除订阅及其全部运行记录；返回是否真的删到（不存在 → False，非错误）。

        先删 `subscription_run` 子行再删父行——外键 `PRAGMA foreign_keys=ON`
        （`Database.__init__`）下顺序不可颠倒。单事务，同进同退。
        """
        with self.db.tx() as conn:
            conn.execute("DELETE FROM subscription_run WHERE name = ?", (name,))
            cursor = conn.execute("DELETE FROM subscription WHERE name = ?", (name,))
            return cursor.rowcount > 0

    def exists(self, name: str) -> bool:
        """订阅是否存在（不解析 DSL）。"""
        return bool(self.db.query("SELECT 1 FROM subscription WHERE name = ?", (name,)))

    # -- watermark（design/09 §5；格式归 T4）---------------------------------

    def read_watermark(self, name: str) -> dict[str, object]:
        """读 `watermark_json` → dict；未运行过（NULL）或空串 → `{}`（首跑语义）。

        本层不解释格式（`{source: {...}, "schema_ver": N}` 归 T4），只保证"存进去
        什么读出来什么"。未知订阅名 → `CrawlerError(CONFIG)`（与 `registry.get`
        对未知 venue_id 的处置同构），不返回 `{}` 假装首跑。

        **畸形 JSON 也归 CONFIG，且抛 `SubscriptionInvalid`**（P2#1 热修：异常类型
        统一，`error_class` 仍是 CONFIG，行为兼容——不让裸 `JSONDecodeError` 逃出
        错误分类学，也不再用泛型 `CrawlerError` 兜底；审计对 config TOML 同型缺口
        的 P1 教训）：损坏的游标若被当成"首跑"会静默重刷全窗。
        """
        rows = self.db.query("SELECT watermark_json FROM subscription WHERE name = ?", (name,))
        if not rows:
            raise _unknown_subscription(name)
        raw = rows[0]["watermark_json"]
        if raw is None or not str(raw).strip():
            return {}
        try:
            loaded = json.loads(str(raw))
        except json.JSONDecodeError as exc:
            raise SubscriptionInvalid(
                f"subscription {name!r} 的 watermark_json 解析失败: {exc}",
                detail=name,
            ) from None
        if not isinstance(loaded, dict):
            raise SubscriptionInvalid(
                f"subscription {name!r} 的 watermark_json 顶层不是对象",
                detail=type(loaded).__name__,
            )
        return {str(key): value for key, value in loaded.items()}

    def write_watermark(self, name: str, watermark: Mapping[str, object]) -> None:
        """覆盖写 `watermark_json`（T4 的推进出口）。未知订阅名 → `CrawlerError(CONFIG)`。

        整体覆盖而非合并：watermark 的"哪些源该留、该删"由 T4 按订阅当前 `sources`
        决定，仓储层做部分合并只会让退订的源留下幽灵游标。
        """
        with self.db.tx() as conn:
            cursor = conn.execute(
                "UPDATE subscription SET watermark_json = ? WHERE name = ?",
                # sort_keys=True：payload 是调用方 dict，键序不受本层控制（P1-1）。
                (_json_text(dict(watermark), sort_keys=True), name),
            )
            if cursor.rowcount == 0:
                raise _unknown_subscription(name)

    def touch_last_run(self, name: str, *, at: str | None = None) -> None:
        """推进 `last_run_at`（缺省取当前 UTC）。未知订阅名 → `CrawlerError(CONFIG)`。"""
        with self.db.tx() as conn:
            cursor = conn.execute(
                "UPDATE subscription SET last_run_at = ? WHERE name = ?",
                (at if at is not None else utcnow_iso(), name),
            )
            if cursor.rowcount == 0:
                raise _unknown_subscription(name)

    # -- subscription_run ----------------------------------------------------

    def record_run(
        self,
        *,
        name: str,
        started_at: str,
        new_count: int,
        fetched_count: int = 0,
        truncated: bool = False,
        report_path: str | None = None,
    ) -> str:
        """落一条运行记录，返回其 ULID。

        字段与 `subs.types.RunSummary` 一一对应（T5 直接从 summary 取值调用）。
        **熔断也要落记录**（`truncated=1` + 零入库，plan §4 T5 已裁决歧义②）——
        "跑过但被拦下"与"没跑"必须可区分。dry-run **不落**（T5 侧不调用本方法）。
        """
        if not self.exists(name):
            raise _unknown_subscription(name)
        run_id = new_ulid()
        self.db.execute(
            "INSERT INTO subscription_run "
            "(id, name, started_at, new_count, fetched_count, truncated, report_path) "
            "VALUES (?,?,?,?,?,?,?)",
            (run_id, name, started_at, new_count, fetched_count, int(truncated), report_path),
        )
        return run_id

    def runs(self, name: str | None = None, *, limit: int | None = None) -> list[sqlite3.Row]:
        """运行记录，按 `started_at` 降序（最近在前）；可限订阅、可限条数。"""
        sql = "SELECT * FROM subscription_run"
        params: list[object] = []
        if name is not None:
            sql += " WHERE name = ?"
            params.append(name)
        sql += " ORDER BY started_at DESC, id DESC"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        return self.db.query(sql, params)

    def last_run(self, name: str) -> sqlite3.Row | None:
        """某订阅最近一次运行记录；从未运行 → None。"""
        rows = self.runs(name, limit=1)
        return rows[0] if rows else None


def _json_text(payload: Mapping[str, object], *, sort_keys: bool) -> str:
    """订阅域 JSON 列的序列化（非 ASCII 原样）；`sort_keys` 按列语义显式选择
    （P1-1 热修——原先恒 `sort_keys=True` 会打乱 `sources` 的 YAML 声明序）。

    - `query_json`/`guard_json`：payload 来自 `to_query_dict()`/`Guard.to_dict()`，
      两者已按 DSL 字段序构造好确定序（含 `sources` 的**声明序**，编译计划步骤序
      的来源）——排序会把 `sources` 的键序打成字母序，破坏声明序往返（回归判据见
      `tests/integration/test_subscription_repo.py` 的 `asset-pricing-wp` 参数化，
      其声明序 ssrn→arxiv→nber 非字母序）。调用方须传 `sort_keys=False`。
    - `watermark_json`：payload 是调用方（T4）传入的 dict，键序不受本层控制，传
      `sort_keys=True` 换取确定性输出（可读 diff、可测试）。

    无默认值——强制每个调用点显式做出选择，不给"复制上一行却传错"留空子。
    """
    return json.dumps(dict(payload), ensure_ascii=False, sort_keys=sort_keys)


def _unknown_subscription(name: str) -> CrawlerError:
    """未知订阅名的统一错误（同 `registry.get` 对未知 venue_id 的 CONFIG 处置）。"""
    return CrawlerError(ErrorClass.CONFIG, f"unknown subscription: {name!r}")
