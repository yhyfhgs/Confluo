-- schema v1 (design/06 §2 十二张表 + phase1-plan §2.4 补的 paper_issue_link/task/fetch_log
-- + schema_version)。方言中性（保留 PostgreSQL 迁移路径，D-001）：全部主键 ULID 文本，
-- 时间戳 UTC ISO8601 文本，弹性字段 JSON 文本列；不建 FTS5（D-017，推迟 Phase 6）。
-- 表顺序按外键依赖排列（被引用表在前——PostgreSQL 建表期即校验引用存在性）。

-- ---------------------------------------------------------------------------
-- 核心元数据表（design/06 §2 原文逐列转写）
-- ---------------------------------------------------------------------------

CREATE TABLE venue (
  id TEXT PRIMARY KEY,               -- 'jfe', 'iclr'（与 VenueSpec.id 一致）
  kind TEXT NOT NULL,                -- journal|conference|preprint_channel
  name TEXT NOT NULL,
  field_json TEXT NOT NULL,          -- ["finance"]
  tier TEXT,                         -- T1|T2|T3
  spec_snapshot_json TEXT,           -- 注册时的 VenueSpec 快照（审计）
  status TEXT DEFAULT 'active'
);

CREATE TABLE venue_era (             -- D-012：会议每届/期刊改版期的地址记录
  id TEXT PRIMARY KEY,
  venue_id TEXT REFERENCES venue,
  year INTEGER,                      -- 会议届年；期刊可空
  label TEXT,                        -- 'NeurIPS 2024'
  official_site TEXT,
  proceedings_url TEXT,
  metadata_source TEXT,              -- 该届实际用的源（老届可能与新届不同）
  verified_at TEXT,
  status TEXT,                       -- active|dead|wayback_only
  UNIQUE(venue_id, year, label)
);

CREATE TABLE issue (
  id TEXT PRIMARY KEY,
  venue_id TEXT REFERENCES venue,
  era_id TEXT REFERENCES venue_era,
  volume TEXT,                       -- 期刊卷（文本：存在 'S1' 类特刊）
  number TEXT,                       -- 期刊期
  year INTEGER,
  label TEXT,                        -- 会议: label='2024'/'2024-workshop-xx'
  pub_date TEXT,
  source TEXT NOT NULL,              -- 该行来自哪个 adapter（crossref/dblp/...）
  paper_count_claimed INTEGER,       -- 源头宣称数（对账 enumerate 完整性）
  UNIQUE(venue_id, volume, number, label)
);

CREATE TABLE paper (
  id TEXT PRIMARY KEY,               -- 内部 ULID（D-007：不用外部 id 做主键）
  title TEXT NOT NULL,
  abstract TEXT,
  year INTEGER,
  pub_date TEXT,
  venue_id TEXT REFERENCES venue,    -- 主发表 venue（预印本=该渠道）
  meta_json TEXT,                    -- 页码/关键词/JEL 码/track 等弹性字段
  ingest_state TEXT NOT NULL,        -- metadata_only|resolved|fetched|extracted
  created_at TEXT,
  updated_at TEXT
);

CREATE TABLE identifier (
  paper_id TEXT REFERENCES paper,
  scheme TEXT NOT NULL,              -- doi|arxiv|ssrn|openalex|s2|dblp|anthology|...
  value TEXT NOT NULL,               -- '10.1016/j.jfineco...' / '2401.12345'
  is_primary INTEGER DEFAULT 0,
  PRIMARY KEY (scheme, value)        -- 全局唯一 → 天然强合并锚点
);

CREATE TABLE asset (
  id TEXT PRIMARY KEY,
  paper_id TEXT REFERENCES paper,
  kind TEXT NOT NULL,                -- pdf|si|html|bibtex|source
  version TEXT,                      -- arXiv v2 / camera-ready / published
  url TEXT,
  auth_needed TEXT,                  -- 解析出的获取计划（resolve 产物）
  state TEXT NOT NULL,               -- planned|fetched|gone|no_entitlement|failed
  file_path TEXT,
  bytes INTEGER,
  sha256 TEXT,
  fetched_at TEXT,
  source_adapter TEXT,
  UNIQUE(paper_id, kind, version)
);

CREATE TABLE author (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  orcid TEXT,
  meta_json TEXT
);

CREATE TABLE authorship (
  paper_id TEXT REFERENCES paper,
  author_id TEXT REFERENCES author,
  position INTEGER,
  affiliation TEXT,
  PRIMARY KEY (paper_id, author_id, position)
);

CREATE TABLE paper_relation (        -- D-007
  from_paper TEXT REFERENCES paper,
  to_paper TEXT REFERENCES paper,
  kind TEXT NOT NULL,                -- preprint_of|same_as|candidate_duplicate
  confidence REAL,
  evidence_json TEXT,
  decided TEXT,                      -- null=待审 | merged | rejected
  PRIMARY KEY (from_paper, to_paper, kind)
);

CREATE TABLE fulltext (
  paper_id TEXT PRIMARY KEY REFERENCES paper,
  extractor TEXT,
  extractor_ver TEXT,
  text_path TEXT,                    -- data/fulltext/{...}.txt|.tei.xml
  char_count INTEGER,
  lang TEXT,
  extracted_at TEXT
);

CREATE TABLE subscription (          -- design/09
  name TEXT PRIMARY KEY,
  query_json TEXT NOT NULL,          -- DSL 序列化
  watermark_json TEXT,               -- 各源游标
  guard_json TEXT,                   -- 阈值护栏配置
  created_at TEXT,
  last_run_at TEXT
);

CREATE TABLE subscription_run (
  id TEXT PRIMARY KEY,
  name TEXT REFERENCES subscription,
  started_at TEXT,
  new_count INTEGER,
  fetched_count INTEGER,
  truncated INTEGER,
  report_path TEXT
);

-- ---------------------------------------------------------------------------
-- phase1-plan §2.4 实现期补全：paper_issue_link（ER 总览已声明，§2 草案漏列）
-- ---------------------------------------------------------------------------

CREATE TABLE paper_issue_link (
  paper_id TEXT REFERENCES paper,
  issue_id TEXT REFERENCES issue,
  PRIMARY KEY (paper_id, issue_id)
);

-- ---------------------------------------------------------------------------
-- 运行时表（design/05 §2/§7 字段清单；task.kind 含 'pull'）
-- ---------------------------------------------------------------------------

CREATE TABLE task (
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  venue_id TEXT,
  params_json TEXT NOT NULL,
  state TEXT NOT NULL DEFAULT 'PENDING',
  error_class TEXT,
  blocked_reason TEXT,
  attempts INTEGER NOT NULL DEFAULT 0,
  last_error TEXT,
  parent_id TEXT REFERENCES task(id),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
-- 活跃任务幂等键（部分唯一索引；SQLite 与 PostgreSQL 均支持 WHERE 子句，非专有特性）。
-- COALESCE(venue_id,'') 归一 NULL：SQL 视 NULL 互不相等，否则 venue-less 活跃任务无法去重；C1 仲裁 2026-07-21 方案 a（索引层修 NULL），表达式唯一索引 SQLite/PG 均支持、方言中性。
CREATE UNIQUE INDEX idx_task_active_idem ON task(kind, COALESCE(venue_id, ''), params_json)
  WHERE state IN ('PENDING', 'RUNNING');
CREATE INDEX idx_task_state_kind ON task(state, kind);

CREATE TABLE fetch_log (
  id TEXT PRIMARY KEY,
  asset_id TEXT REFERENCES asset(id),
  task_id TEXT,
  domain TEXT NOT NULL,
  url TEXT NOT NULL,
  http_status INTEGER,
  bytes INTEGER NOT NULL DEFAULT 0,
  elapsed_ms INTEGER NOT NULL DEFAULT 0,
  rate_wait_ms INTEGER NOT NULL DEFAULT 0,
  error_class TEXT,
  ts TEXT NOT NULL
);
CREATE INDEX idx_fetch_log_domain_ts ON fetch_log(domain, ts);

CREATE INDEX idx_asset_state ON asset(state);

-- ---------------------------------------------------------------------------
-- 迁移版本单行表（design/06 §6：启动比对，向前迁移）。行由 migrate() 维护。
-- ---------------------------------------------------------------------------

CREATE TABLE schema_version (version INTEGER NOT NULL);
