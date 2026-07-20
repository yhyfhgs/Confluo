---
title: 数据模型与入库设计
status: approved
owner: fable5
updated: 2026-07-20
---

# 06 · 数据模型与入库设计

> 决策依据：D-007（identifier 图与 preprint_of）。配图：[diagrams/05-data-model.svg](../diagrams/05-data-model.svg)。
> 存储：SQLite（WAL）起步，schema 设计避免 SQLite 专有特性以保留 PostgreSQL 迁移路径（D-001）。

## 1. 实体关系总览

```
Venue 1─N VenueEra          (会议历年官网/proceedings 地址漂移，D-012)
Venue 1─N Issue             (期刊: 卷/期；会议: 届/track；预印本: 虚拟月度桶)
Issue 1─N PaperIssueLink N─1 Paper     (论文可出现于多 venue —— 少见但存在)
Paper 1─N Identifier        (doi / arxiv / ssrn / openalex / s2 / dblp / anthology ...)
Paper 1─N Asset             (pdf / si / html / bibtex / source；含版本)
Paper 1─N Authorship N─1 Author
Paper 1─N PaperRelation     (preprint_of / same_as / candidate_duplicate / extends)
Paper 1─1 Fulltext          (抽取文本与结构化产物指针)
Subscription 1─N SubscriptionRun       (watch 订阅与 watermark)
Task / FetchLog             (运行时，见 design/05)
```

## 2. 表定义（schema v1 草案，DDL 风格伪代码）

```sql
-- 注：全部主键用 ULID 文本；时间戳 UTC ISO8601；JSON 列存放弹性字段。

CREATE TABLE venue (
  id TEXT PRIMARY KEY,              -- 'jfe', 'iclr'（与 VenueSpec.id 一致）
  kind TEXT NOT NULL,               -- journal|conference|preprint_channel
  name TEXT NOT NULL,
  field_json TEXT NOT NULL,         -- ["finance"]
  tier TEXT,                        -- T1|T2|T3
  spec_snapshot_json TEXT,          -- 注册时的 VenueSpec 快照（审计）
  status TEXT DEFAULT 'active'
);

CREATE TABLE venue_era (            -- D-012：会议每届/期刊改版期的地址记录
  id TEXT PRIMARY KEY,
  venue_id TEXT REFERENCES venue,
  year INTEGER,                     -- 会议届年；期刊可空
  label TEXT,                       -- 'NeurIPS 2024'
  official_site TEXT, proceedings_url TEXT,
  metadata_source TEXT,             -- 该届实际用的源（老届可能与新届不同）
  verified_at TEXT, status TEXT,    -- active|dead|wayback_only
  UNIQUE(venue_id, year, label)
);

CREATE TABLE issue (
  id TEXT PRIMARY KEY,
  venue_id TEXT REFERENCES venue,
  era_id TEXT REFERENCES venue_era,
  volume TEXT, number TEXT,         -- 期刊卷/期（文本：存在 'S1' 类特刊）
  year INTEGER, label TEXT,         -- 会议: label='2024'/'2024-workshop-xx'
  pub_date TEXT,
  source TEXT NOT NULL,             -- 该行来自哪个 adapter（crossref/dblp/...）
  paper_count_claimed INTEGER,      -- 源头宣称数（对账 enumerate 完整性）
  UNIQUE(venue_id, volume, number, label)
);

CREATE TABLE paper (
  id TEXT PRIMARY KEY,              -- 内部 ULID（D-007：不用外部 id 做主键）
  title TEXT NOT NULL,
  abstract TEXT,
  year INTEGER, pub_date TEXT,
  venue_id TEXT REFERENCES venue,   -- 主发表 venue（预印本=该渠道）
  meta_json TEXT,                   -- 页码/关键词/JEL 码/track 等弹性字段
  ingest_state TEXT NOT NULL,       -- metadata_only|resolved|fetched|extracted
  created_at TEXT, updated_at TEXT
);

CREATE TABLE identifier (
  paper_id TEXT REFERENCES paper,
  scheme TEXT NOT NULL,             -- doi|arxiv|ssrn|openalex|s2|dblp|anthology|pmlr|ieee|acm|openreview|cvf|neurips|repec|url（开放枚举，adapter 注册时声明）
  value TEXT NOT NULL,              -- '10.1016/j.jfineco...' / '2401.12345'
  is_primary INTEGER DEFAULT 0,
  PRIMARY KEY (scheme, value)       -- 全局唯一 → 天然强合并锚点
);

CREATE TABLE asset (
  id TEXT PRIMARY KEY,
  paper_id TEXT REFERENCES paper,
  kind TEXT NOT NULL,               -- pdf|si|html|bibtex|source
  version TEXT,                     -- arXiv v2 / camera-ready / published
  url TEXT, auth_needed TEXT,       -- 解析出的获取计划（resolve 产物）
  state TEXT NOT NULL,              -- planned|fetched|gone|no_entitlement|failed
  file_path TEXT, bytes INTEGER, sha256 TEXT,
  fetched_at TEXT, source_adapter TEXT,
  UNIQUE(paper_id, kind, version)
);

CREATE TABLE author (
  id TEXT PRIMARY KEY, name TEXT NOT NULL,
  orcid TEXT, meta_json TEXT
);
CREATE TABLE authorship (
  paper_id TEXT REFERENCES paper, author_id TEXT REFERENCES author,
  position INTEGER, affiliation TEXT,
  PRIMARY KEY (paper_id, author_id, position)
);

CREATE TABLE paper_relation (       -- D-007
  from_paper TEXT REFERENCES paper, to_paper TEXT REFERENCES paper,
  kind TEXT NOT NULL,               -- preprint_of|same_as|candidate_duplicate
  confidence REAL, evidence_json TEXT,
  decided TEXT,                     -- null=待审 | merged | rejected
  PRIMARY KEY (from_paper, to_paper, kind)
);

CREATE TABLE fulltext (
  paper_id TEXT PRIMARY KEY REFERENCES paper,
  extractor TEXT, extractor_ver TEXT,
  text_path TEXT,                   -- data/fulltext/{...}.txt|.tei.xml
  char_count INTEGER, lang TEXT, extracted_at TEXT
);

CREATE TABLE subscription (         -- design/09
  name TEXT PRIMARY KEY,
  query_json TEXT NOT NULL,         -- DSL 序列化
  watermark_json TEXT,              -- 各源游标（arXiv: last submittedDate；ssrn: last seen ids）
  guard_json TEXT,                  -- 阈值护栏配置
  created_at TEXT, last_run_at TEXT
);
CREATE TABLE subscription_run (
  id TEXT PRIMARY KEY, name TEXT REFERENCES subscription,
  started_at TEXT, new_count INTEGER, fetched_count INTEGER,
  truncated INTEGER, report_path TEXT
);

-- task / fetch_log 见 design/05 §2、§7（字段同文档所列）
```

索引要点：`identifier(scheme,value)` 主键即索引；`paper(title)` 建 FTS5 虚表（标题+摘要检索）；`asset(state)`、`task(state, kind)` 部分索引服务调度查询。

## 3. 去重与合并（ingest 阶段算法）

**强合并（自动）**：新纸带 identifier (scheme,value) 已存在 → 直接并入既有 paper（字段按"来源优先级表"补缺不覆盖：出版社/官方 proceedings > Crossref > OpenAlex > S2 > 启发式）。
**弱信号（进候审）**：无共同 identifier 时计算：标题规范化（去标点/大小写/LaTeX 宏）精确匹配 + 首作者姓氏一致 → `candidate_duplicate(confidence)`；**绝不自动合并**（D-007：WP↔刊发版标题常变，宁可两条待审）。
**preprint_of 建边**：Crossref/OpenAlex 的 preprint 关系字段、arXiv 的 `journal_ref/doi` 回填字段、SSRN→DOI 提示 → 自动建 `preprint_of`（保留双条 paper 双份全文）。
**审核工具**（Phase 7）：`crawler dedupe review` 逐条展示证据，人工 merge/reject；merge 保留两 paper 行并置 `same_as(decided=merged)`，查询层聚合——**物理不删行**，可回滚。

## 4. 文件存储布局

```
data/
├── pdf/{venue_id}/{year}/{paper_ulid}.pdf        # 主全文
├── si/{venue_id}/{year}/{paper_ulid}/...         # 补充材料（保持原名）
├── fulltext/{venue_id}/{year}/{paper_ulid}.txt   # 抽取文本（或 .tei.xml）
├── export/                                        # bibtex/csv 导出产物
└── tmp/*.part                                     # 下载中转（启动清理）
```

- 文件名用内部 ULID（跨源稳定、无非法字符问题）；人类可读性靠 `crawler export` 生成 `AuthorYearTitle` 别名清单/软链接，不改动库内文件名。
- `verify` 对账规则见 design/05 §5。

## 5. 与聚合源的字段映射（enumerate 的落库口径）

| 目标字段 | Crossref | OpenAlex | DBLP | OpenReview |
|---|---|---|---|---|
| title | `title[0]` | `title` | `title` | `content.title` |
| doi | `DOI` | `doi`(裸) | `ee` 中提取 | 可空 |
| pub_date | `published-print/-online` | `publication_date` | `year` | `cdate` |
| volume/issue | `volume/issue` | `biblio.*` | 卷 key | —（届即 label） |
| abstract | 常缺 | `abstract_inverted_index`（需重建） | 无 | `content.abstract` |
| authors | `author[]` | `authorships[]` | `author[]` | `content.authors` |

约定：abstract 缺失不阻塞入库（`metadata_only` 允许字段残缺）；OpenAlex 倒排索引重建为纯文本在 ingest 内完成。

## 6. 迁移策略

- `schema_version` 单行表；启动比对，向前迁移脚本 `migrations/000N_*.sql` 顺序执行，每步事务+备份（SQLite 文件 copy）；
- 破坏性变更（列删除/语义变更）必须先出 ADR；
- SQLite→PostgreSQL：类型对齐已预留（TEXT 主键、ISO 时间戳、JSON 文本列）；届时 identifier 主键改复合唯一约束语法即可。

## 7. 测试与验收

- **单元**：标题规范化（LaTeX/Unicode 用例表）；合并优先级表；倒排索引重建。
- **属性测试**：随机顺序注入同一批多源记录，最终库状态与注入顺序无关（合并交换律）。
- **验收**（AC-3.x 摘录）：
  - AC-3.1 同一论文经 arXiv 与 Crossref 两路注入后库内一条 paper、两个 identifier；
  - AC-3.2 标题改名的 WP↔刊发版不被自动合并且出现在候审队列；
  - AC-3.3 `verify` 能检出人为制造的三类不一致（丢文件/孤儿文件/哈希不符）并给出正确修复建议。
