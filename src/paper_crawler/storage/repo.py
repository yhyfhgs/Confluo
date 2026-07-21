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
from dataclasses import dataclass

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
        """
        with self.db.tx() as conn:
            paper_id: str | None = None
            for scheme, value in stub.identifiers:
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
                    "(id, title, abstract, year, pub_date, venue_id, meta_json, "
                    " ingest_state, created_at, updated_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (
                        paper_id,
                        stub.title,
                        stub.abstract,
                        stub.year,
                        stub.pub_date,
                        venue_id,
                        _meta_to_json(stub.meta),
                        "metadata_only",
                        now,
                        now,
                    ),
                )
            else:
                self._merge_paper_fields(conn, paper_id, stub, now)

            self._ensure_identifiers(conn, paper_id, stub)

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
    def _ensure_identifiers(conn: sqlite3.Connection, paper_id: str, stub: PaperStub) -> None:
        """确保 stub 的每个 identifier 存在并指向 paper_id；已存在的保持不动（全局唯一锚点）。

        `is_primary` 单一性：一个 paper 至多一个 primary。仅当该 paper 尚无 primary 时，
        才把 stub 首个（index==0）**新增** identifier 标为 primary；合并进已有 primary 的
        paper 时新来者一律非 primary（否则合并路径会产生双 is_primary）。
        """
        has_primary = (
            conn.execute(
                "SELECT 1 FROM identifier WHERE paper_id = ? AND is_primary = 1 LIMIT 1",
                (paper_id,),
            ).fetchone()
            is not None
        )
        for index, (scheme, value) in enumerate(stub.identifiers):
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

    def list_papers(self, venue_id: str, issue_id: str | None = None) -> list[sqlite3.Row]:
        """列出某 venue 的 paper；给定 issue_id 时限定该期内（经 paper_issue_link）。按标题排序。"""
        if issue_id is not None:
            return self.db.query(
                "SELECT p.* FROM paper p "
                "JOIN paper_issue_link l ON p.id = l.paper_id "
                "WHERE p.venue_id = ? AND l.issue_id = ? "
                "ORDER BY p.title",
                (venue_id, issue_id),
            )
        return self.db.query("SELECT * FROM paper WHERE venue_id = ? ORDER BY title", (venue_id,))

    def set_paper_state(self, paper_id: str, ingest_state: str) -> None:
        """更新 paper.ingest_state（metadata_only|resolved|fetched|extracted）。"""
        self.db.execute(
            "UPDATE paper SET ingest_state = ?, updated_at = ? WHERE id = ?",
            (ingest_state, utcnow_iso(), paper_id),
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
        """追加一条取回审计记录（FetchLog;限速合规证据源, design/05 §7）。

        `url` 落库前经 `obslog.redact`（AC-0.4/NFR-8: fetch_log.url 不得含未脱敏凭证——
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
