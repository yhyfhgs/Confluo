---
title: 数据模型与入库设计
status: implemented
owner: fable5
updated: 2026-07-27
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

CREATE TABLE paper_issue_link (      -- 勘误补全 2026-07-21：§1 ER 总览已声明本表，v1 草案漏列 DDL；实现（schema v1）已含
  paper_id TEXT REFERENCES paper, issue_id TEXT REFERENCES issue,
  PRIMARY KEY (paper_id, issue_id)
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
-- kind=candidate_duplicate 语义上是**无序对**（"这两篇疑似同一著作"）：from/to 由建边时刻
-- 两 paper 各自最小 identifier 定序，是快照而非不变量（后补更小 identifier 不重定向），
-- 消费方一律按无序对处理，不得依赖 from/to 字面顺序。

CREATE TABLE paper_weak_key (       -- schema v3（0003）：弱信号候审的**观测级**匹配键集合
  paper_id TEXT NOT NULL REFERENCES paper,
  title_norm TEXT NOT NULL,         -- 该次观测标题的归一形（ids.normalize_title）
  first_author TEXT NOT NULL,       -- 该次观测的首作者姓氏归一形
  PRIMARY KEY (paper_id, title_norm, first_author)
);
-- 一 paper 多行 = 它历次观测给出的键全集：单调只增、不被 §3 的字段级收敛改写，故候审终态
-- 是输入集合（而非注入顺序）的函数 —— AC-3.4 的实现基石，见 §3。索引
-- idx_paper_weak_key_lookup(title_norm, first_author) 服务"谁曾观测过这个键"的反查。

CREATE TABLE fulltext (             -- schema v4（0004_fulltext_asset.sql）后的形态
  paper_id TEXT PRIMARY KEY REFERENCES paper,   -- 1─1 基数不变；asset 级的是**幂等键**
  extractor TEXT, extractor_ver TEXT,           -- 'pypdf' | 'grobid' | 'noop'（P1 占位）
  text_path TEXT,                   -- fulltext/{venue}/{year}/{ulid}.txt|.tei.xml（**相对 data_dir，无 `data/` 前缀**）
  char_count INTEGER, lang TEXT, extracted_at TEXT,
  -- v4 增列（Phase 7 T7 / D-033；纯附加、方言中性）
  asset_id TEXT REFERENCES asset,   -- 产物出自哪个 asset（legacy 行 NULL）
  source_sha256 TEXT,               -- 抽取时源 PDF 的 sha256（陈旧判据 = stale_fulltext）
  text_sha256 TEXT,                 -- 落盘产物 sha256（verify 的 hash_mismatch 依据）
  state TEXT,                       -- extracted | extract_failed | noop
  note TEXT                         -- 失败 token：encrypted|image_only|corrupt|empty_text
);
-- 幂等键 = (asset_id, source_sha256, extractor, extractor_ver)；取代规则 = 全序取 max
-- (rank, ver_key, char_count, asset_id)，rank：grobid 2 > pypdf 1 > extract_failed 0 > noop −1
-- > 陈旧/产物失效 −2 —— 终态是输入集合的函数、与注入顺序无关（D-031 纪律）。失败态**不进**
-- paper.ingest_state 四值阶梯（那是单调前进的进度轴），由 state 列承载。详见 design/12 §5/§6。
-- ⚠ `text_path` **不含 `data/` 前缀**：verify._resolve 把相对路径挂在 Config.data_dir 下，而
-- data_dir 本身即指向 …/data，带前缀会解析成 …/data/data/fulltext/… 使全库每行都报 missing_file。
-- （0001_init.sql 的旧列注释含该前缀，是既成事实的文档缺陷，不改一个字节；以此处为准。）

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

索引要点：`identifier(scheme,value)` 主键即索引；`asset(state)`、`task(state, kind)` 部分索引服务调度查询；
**全文检索索引见下**。

> **迁移号顺延注记（P7-T7 合并期）**：本小节下文的 `schema v4 / 0004_fts_paper.sql` 应读作
> **`schema v5 / 0005_fts_paper.sql`** —— T7（D-033 fulltext asset 级幂等键）先行占用 0004，按
> [D-033 R3](../plan/decision-log.md)「先合者取小号」；**正文引用由 T12 落地时全面更新**，此注记
> 只为消除 T12 合并前的双 0004 误导窗。

**FTS5 检索索引（schema v4 / `0004_fts_paper.sql`；权威决策 [D-034](../plan/decision-log.md)）**——本节原文
曾写「`paper(title)` 建 FTS5 虚表（标题+摘要检索）」，那是**未落地的设计声明**：D-017 决策 4 把它推迟到
Phase 6，Phase 6 关账时未兑现（该 Phase 的搜索面全部落在订阅 DSL 的本地过滤谓词上），D-034 如实记债后把
兑现 Phase 改判 Phase 7 T12。落地形态：

- **表**：`paper_fts(paper_id UNINDEXED, title, abstract)`，**content-owning**（自持内容）形态，
  `tokenize='porter unicode61 remove_diacritics 2'`。**不取** external-content / contentless——`paper.id` 是
  ULID 文本主键、无 INTEGER PRIMARY KEY，二者均以隐式 rowid 为唯一连接键而 `VACUUM` 可重编号 rowid，
  会让检索结果**静默指向错误的 paper**；content-owning 把 `paper_id` 物化进索引行，结果正确性不依赖
  rowid 稳定性（代价＝多存一份 title+abstract 副本，估算 ≈13 MB/万篇，D-034 决策 2 定价）。
- **范围**：`title` + `abstract` **二字段**。**全文正文索引与向量索引 defer**（phase7-plan §8：正文索引等
  抽取产物规模实测后于 P8 评估经济性；向量索引无消费场景 + 引重依赖）——故 `fulltext.text_path` 指向的
  正文**不入库、不入索引**，`fulltext` 表语义不变。
- **同步**：`0004` 内三触发器（`AFTER INSERT` / `AFTER UPDATE OF title, abstract` / `AFTER DELETE` ON
  `paper`），FTS 行 rowid 显式绑 `paper.rowid`。触发器而非应用层同步——写 `paper` 的路径不止一处且仍在
  增长，漏一处即索引静默漂移。**两条不变式（D-034 决策 3 写死 SQL）**：①`paper_id` 每次写入同写 `new.id`、
  UPDATE 取 DELETE+INSERT 形态（写成 `UPDATE … SET title=…WHERE rowid=` 会在 rowid 重编号后复活静默错
  映射）；②两处 DELETE 带 `AND paper_id = old.id` 双条件（只按 rowid 删会误删无辜他行＝假阴性；加判别后
  DELETE 落空 → 后续 INSERT 撞占用 rowid 抛 `IntegrityError`＝**写入响亮失败+回滚**，须 `crawler reindex`
  恢复写路径，T12 须把该异常同款翻译为可操作 `CrawlerError`）。**迁移器须先扩展**：`db.py::_iter_statements` 现逐 `;` 断句、切不了
  `BEGIN…END` 触发器（实测复现），T12 范围内含该扩展。
- **方言隔离**：`0001`–`0003` 保持方言中性（§6/D-001 不变）；`0004` 是**唯一**允许含 SQLite 专有特性的
  迁移文件，PG 迁移时整文件替换为 `tsvector` 生成列 + GIN 索引（等价性与**不可移植面**——查询语法、
  排序函数、词干化实现三项不等价——见 D-034 决策 6）。检索一律经 `repo.search_papers()` 单点封装。
- **维护**：`crawler reindex`（全表重灌，单事务幂等）；`--check` ＝**只读一致性校验三项并跑**——`paper` ⟂
  `paper_fts` **双向差集**（漏索引 / 孤儿行）+ **行数与同 `paper_id` 多行**校验 + FTS5 `integrity-check`。
  **单靠 `integrity-check` 检不出目标漂移**（它只校倒排索引与 FTS 自持 content 的自洽，实测对 `paper_id`↔
  `title` 错配、`paper` 有行而 `paper_fts` 无行两种漂移均 PASS）——前两项才是与 `paper` 对账的部分。日常由
  触发器维护，仅在分词器变更、执行过 `VACUUM`、手工 DB 手术后或 `--check` 报不一致时需要重建。

## 3. 去重与合并（ingest 阶段算法）

**强合并（自动）**：新纸带 identifier (scheme,value) 已存在 → 直接并入既有 paper（字段按"来源优先级表"补缺不覆盖：出版社/官方 proceedings > Crossref > DBLP > OpenAlex > S2 > **RePEc** > 启发式——七位表见 [D-035](../plan/decision-log.md) 决策 2 与 [aggregators.md §6](adapters/aggregators.md)；RePEc 取最低非-heuristic 位＝其重叠字段是二手面，独家增值 JEL/`Publication-Status` 落 `meta`、三路皆缺，只补空即全额兑现）。字段级收敛的完整判据（实现：`storage/repo.py::_converge_fields`，权威说明见 `merge.py` 裁决点 2）：新值仅在①现值为空、②新源优先级**严格更高**、或③**同源二次观测**按确定性 tie-break 胜出时写入；未记录 provenance 的存量值（pull 路径所写）视为最高优先只补空。tie-break（③）取全序而非"先到者胜"，否则注入顺序即决定终值：文本字段（title/abstract/首作者/meta）**更长者胜、等长取字典序小者**（同源复查最常见形态是信息增补，纯字典序会让截断/前缀版恒压制完整版），year/pub_date 取更早者。被 tie-break 压制掉不同值的字段记入 `meta_json._field_tie`（仅记**当前生效来源**的自相矛盾），供 Phase 7 `dedupe review` 复核。
**弱信号（进候审）**：无共同 identifier 时计算：标题规范化（去标点/大小写/LaTeX 宏）精确匹配 + 首作者姓氏一致 → `candidate_duplicate(confidence)`；**绝不自动合并**（D-007：WP↔刊发版标题常变，宁可两条待审）。匹配键是**观测级**的（Phase 6 F1 修正）：每次 ingest 把该次观测的 `(title_norm, 首作者姓氏)` 并入 `paper_weak_key`（§2，单调只增），新键即触发重判，对每个曾持同键的 paper 建边——终态候审边 = 「键集合有交的每一对 paper」，与注入顺序无关（AC-3.4）。取 paper **行**的当前 title_norm/首作者做键则不成立：二者参与上条的字段收敛，后到的高优先源改写标题即抹掉匹配面，同批观测按不同序注入产生不同候审边（审计 P1 实测）。代价如实记：观测级键不含"A 观测标题 × B 观测姓氏"的跨观测拼接键，故对仅靠拼接键才撞得上的候审**漏标**（fail-safe 侧；行态键随收敛漂移，不可序无关化）。
**preprint_of 建边**：Crossref/OpenAlex 的 preprint 关系字段、arXiv 的 `journal_ref/doi` 回填字段、SSRN→DOI 提示 → 自动建 `preprint_of`（保留双条 paper 双份全文）。**T10 实况核验注记（2026-07-27，独立审查 P2-2）**：Crossref/OpenAlex 的 preprint 关系字段、SSRN→DOI 提示两类——现有 `adapters/{crossref,openalex,ssrn}/parse.py` 均未产出对应字段，**产出侧未实现，消费通道已预留**（`storage/repo.py::_apply_preprint_clues`/`_PREPRINT_CLUE_ROLES` 已就位，逐键可插拔；目前仅 arXiv `journal_ref`/`doi` 回填字段与 cvf/openreview 的 `arxiv` 线索键两类有实际产出侧、已接通消费）；补齐 Crossref/OpenAlex/SSRN 三源的产出侧（新增对应字段解析）挂 **P8 评估**，非本卡（T10）范围。
**审核工具**（Phase 7）：`crawler dedupe review` 逐条展示证据，人工 merge/reject；merge 保留两 paper 行并置 `same_as(decided=merged)`，查询层聚合——**物理不删行**，可回滚。

## 4. 文件存储布局

```
data/
├── pdf/{venue_id}/{year}/{paper_ulid}.pdf        # 主全文
├── si/{venue_id}/{year}/{paper_ulid}/...         # 补充材料（保持原名）
├── fulltext/{venue_id}/{year}/{paper_ulid}.txt   # 抽取文本（GROBID 路径为 .tei.xml）
├── export/                                        # bibtex/csv 导出产物
└── tmp/*.part                                     # 下载中转（启动清理）
```

- 文件名用内部 ULID（跨源稳定、无非法字符问题）；人类可读性靠 `crawler export` 生成 `AuthorYearTitle` 别名清单/软链接，不改动库内文件名。
- **落库形态（Phase 7 T7 / D-033）**：`fulltext.text_path` 存**相对 `data_dir` 的路径**（`fulltext/{venue}/{year}/{ulid}{suffix}`，**不含 `data/` 前缀**——`data_dir` 本身即指向 `…/data`）。选相对形态的理由：config-home 可整体迁移（D-032），绝对路径迁移后全库失效；且 `verify._resolve` 已支持相对形态。`pdf/{v}/{y}/{ulid}.pdf` 与 `fulltext/{v}/{y}/{ulid}.txt` 恒**同 v/y 对位**，verify 对账与人肉查阅都依赖它。**如实入档的债务**：`asset.file_path` 现存**绝对**形态，与本列不一致（改动会使存量库路径全失效、需数据迁移），`verify` 的双形态兼容已覆盖两者——登记 P8 清账候选。
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

## 8. 修订记录

| # | 日期 | 修订 | 依据 |
|---|---|---|---|
| 4 | 2026-07-27 | **纯注记（非设计变更）**：§3 preprint_of 建边段补充"Crossref/OpenAlex 的 preprint 关系字段"与"SSRN→DOI 提示"两类线索的实况核验结果——产出侧（对应 adapter 解析能力）当前未实现，消费通道（`storage/repo.py::_apply_preprint_clues`）已预留、可插拔；产出侧补齐挂 P8 评估。不改动 §3 既有设计文字，只补实况差距如实记录。 | Phase 7 T10（preprint_of 建边引擎实现）独立审查 P2-2；[phase7-implementation-plan.md §4 T10](../plan/phase7-implementation-plan.md) |
| 3 | 2026-07-27 | **FTS5 索引要点落地化（设计声明→冻结形态）**：§2 索引要点行由一句「`paper(title)` 建 FTS5 虚表（标题+摘要检索）」展开为 FTS5 索引小节——表形态（content-owning `paper_fts`，附 external-content/contentless 的否决理由）、范围（title+abstract，正文与向量索引 defer）、触发器同步、`0004` 方言隔离不变式与 PG 替代方案指针、`crawler reindex` 维护面。**同批如实记债**：原句是 D-017 决策 4 推迟到 Phase 6 而 Phase 6 未兑现的悬空声明。§2 表定义与实体语义零变更（FTS 虚表是 `paper` 的派生索引、不引入新实体），故 status 保持 `implemented`。 | [D-034](../plan/decision-log.md)（T2 卡产出，独立审查 NEEDS_FIX→修复→fable 落章生效）；[phase7-implementation-plan §2/§4 T2/§8](../plan/phase7-implementation-plan.md)；D-017 决策 4 |
| 2 | 2026-07-26 | **实现级演进（AC-3.4 顺序无关修复）**：§2 新增 `paper_weak_key` 表（schema v3 / `0003_paper_weak_key.sql`，纯附加、方言中性、Python 步回填存量键）+ `paper_relation` 的 candidate_duplicate 无序对语义注记；§3 补齐字段级收敛的第③条（同源二次观测确定性 tie-break + `meta_json._field_tie` 取证）与弱信号匹配键改为观测级键集合（含漏标代价如实记）。实体模型语义不变（新表是弱信号匹配面的倒排索引，不引入新实体），故 status 保持 `implemented`。 | Phase 6 F1（[phase6-implementation-plan §4 F1](../plan/phase6-implementation-plan.md)）；缺陷台账 [post-phase5-audit §3 P1-1 + P3「同源二次观测异值先到胜」](../reports/2026-07-24-post-phase5-audit.md)；**[D-031](../plan/decision-log.md) 已落（2026-07-26）**（decision-log 补记后本行补链接） |
| 1 | 2026-07-24 | **开放修订议题登记（非设计变更）**：`asset` 表落盘路径布局（§4 `data/pdf/{venue_id}/{year}/{paper_ulid}.pdf`）不含 `version`（§2 `asset.version`，如 `publishedVersion`）判别位——OA-fallback 产生的 OA 副本 asset 与原平台 asset（`version=None`）仅靠内部 ULID 区分，版本身份并存但路径本身不可读出版本语义；该并存不覆盖行为已被 `test_no_entitlement_triggers_oa_fallback_direct_fetch` 验证，但设计文档层面此前未显式承认此路径布局缺口。本条**仅登记议题**，不改 §2/§4 既有设计；是否需在路径中纳入 version 判别位留待后续修订评估。 | Phase 4 T7a 发现；[2026-07-23-phase4-report.md §5「asset 路径 version 债务」](../reports/2026-07-23-phase4-report.md) + [AC-4 离线汇总记录 §5「asset 路径 version 债务（→ T8 / design 修订）」](../testing/records/2026-07-23-ac4-acceptance.md)；phase4-report §6 开工检查单 #1② 移交 |
