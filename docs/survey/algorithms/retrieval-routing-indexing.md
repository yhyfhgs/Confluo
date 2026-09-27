---
title: 算法与架构调研：多源检索、路由、索引结构与多用户数据平台
status: draft
owner: opus5.5-survey
updated: 2026-09-26
---

# 算法与架构调研：多源检索、路由、索引结构与多用户数据平台

> **定位**：v2 重设计的"检索 × 路由 × 索引 × 数据平台"底座调研。只做调研与选型建议，不含实现代码；文中标"设计伪代码"的代码块均为示意，不是接口冻结。
>
> **标注约定**：事实性断言以 `[标签]` 指向 §14 参考来源（URL + 访问日期；除另注外均于 **2026-09-26** 核验）。`⚠ 未核验` = 未能从一手来源确认；`[估算]` = 本文按公式计算；`[判断]` = 本文作者的工程判断（不是事实）；`厂商自测` = 由产品方发布、存在利益相关的基准；`[LIVE]` = 本次对线上接口的实测。
>
> **合规前提**（贯穿全文）：只经合法来源与用户自有授权凭证获取；遵守 robots.txt/ToS、保守限速、诚实可识别 UA；不绕付费墙/CAPTCHA；不集成盗版源；Google Scholar 不做自动化主源；多用户后 auth-gated 全文**不得在用户间共享/再分发**，每个用户只能用自己的凭证取回并私有存放。

---

## 0. 结论速览（TL;DR）

1. **架构总原则："先收割、后联邦"（harvest-first, federate-on-miss）**。订阅、最新论文、卡片流全部走"预先收割 → 全局语料层 → 本地索引"；只有长尾即席查询才在查询时联邦到远端源。依据：远端源限速严（arXiv legacy API ≤1 请求/3 秒且单连接 [arXiv-ToU]；S2 带 key 入门额度 1 RPS [S2-api]；OpenAlex 关键词/语义检索 $1/千次 [OA-cost]），且三家主要元数据 API 实测**不返回 ETag/Last-Modified**，HTTP 条件缓存无从谈起 [LIVE-headers]。
2. **路由 = 能力感知 + 覆盖感知 + 成本感知**。以"Topic 树 × Source 覆盖矩阵"估计每个源对某查询的期望召回（ReDDE 的"相关文档分布"思想 [ReDDE03]，把"查询采样"换成 OpenAlex `group_by` 统计与自有入库日志），再按"边际召回 / 成本"贪心选源（预算最大覆盖的经典近似 [Submod78][BudgetMC99]）；源不支持的谓词走"健全放宽（sound relaxation）+ 本地残差过滤"，这是 v1 design/09"下推 + 本地补偿"的通用化 [v1-design09][TSIMMIS98]。
3. **本地检索用 PostgreSQL 单栈起步**：BM25（pg_textsearch 或 ParadeDB pg_search，许可不同）+ pgvector `halfvec` HNSW（0.8 起的 iterative scan 解决过滤后结果不足）+ RRF 融合 + 小型 cross-encoder 重排。≤约 1000 万篇、≤千级用户可由单节点承载 [判断]；超出后把向量/全文外移到专用引擎（Qdrant / Vespa / OpenSearch 三选一），PG 仍是事实源。
4. **图不引入独立图数据库**：引文/作者/概念图存 PG 邻接表，在线查询限 ≤2 跳（递归 CTE + `CYCLE`）[PG-WITH]，批量图算法夜间导出内存 CSR（rustworkx/igraph）。Kùzu 已于 2025-10 归档 [Kuzu]，是"风投开源依赖"风险的现成教训。
5. **Topic 树是一等索引**：OpenAlex 4 domain → 26 field → 252 subfield → 4,516 topic [OA-topics]，既作路由索引（每节点挂"源分布/更新率/滞后"统计），也作兴趣树与过滤标签（subfield/topic 编号可直接放进 pgvectorscale 的 `smallint[]` 标签过滤 [pgvectorscale]）。
6. **去重**：identifier 图 + union-find 物化稳定 `cluster_id` [UnionFind75]；弱信号用 MinHash-LSH / trigram 召回 + Fellegi–Sunter（Splink）打分 [MinHash97][FS69][Splink]，仍遵守 D-007"弱信号不自动合并"[v1-D007]。
7. **新鲜度**：订阅编译为去重后的 **watch key**（多用户共享轮询、引用计数）；日历型源（arXiv 等）按发布日历调度，连续型源按 Poisson 率在线估计 + politeness 约束下的最优刷新（Cho & Garcia-Molina；Kolobov 2019）[Cho00][Kolobov19]；新论文入库后用"反向检索（percolate）"一次性匹配全部订阅 [OS-percolate]。
8. **稳定性**：在 v1 token bucket 之上补齐**重试预算**（每请求 ≤3 次 + 每客户端重试占比 ≤10%）[SRE-overload]、**AIMD 自适应并发**（上限 = 源方书面限额，只在其下调节）[Netflix-CL]、**熔断 + 舱壁（交互/后台分道）**、**截止时间 + 部分结果**；对同一第三方主机**不做对冲请求**，只在"同能力的不同源"之间做 ≤5% 额外负载的对冲 [TailAtScale13]。
9. **多用户数据平台**：共享语料层（无 RLS，应用只读）与用户私有层（共享表 + `user_id` + RLS）分离 [PG-RLS][AWS-MT]；**付费墙全文按用户私有存放、禁止跨用户去重/共享**；事件日志用按时间分区的 append-only 表 [PG-partition]，量级到 10⁹ 行/年再引入 ClickHouse；暂不上特征存储。
10. **任务队列**：Postgres 原生优先——procrastinate 或 pgqueuer；需要长时持久工作流时评估 DBOS / Hatchet / absurd；**不选 arq（已进入维护模式）**[arq]。
11. **SQLite→PostgreSQL**：v1 本地库只有 179 篇论文（2026-09-26 只读计数）[v1-db-count]，迁移成本极低；以一次性 Python ETL（COPY）+ 新 schema 起步，FTS5 按 D-034 决策 6 替换为 tsvector 或 BM25 扩展 [v1-D034]。

---

## 1. 调研范围与方法

### 1.1 范围与边界

| 本文覆盖（对应任务书 ①–⑧） | 本文不覆盖（交由姊妹调研） |
|---|---|
| ① 联邦检索与源选择、QPP、mediator/wrapper、能力感知查询计划 | 一级/二级来源名录本身与各出版商接口细节（`docs/survey/sources/`） |
| ② 混合检索（BM25/稠密/学习稀疏、融合、重排）与查询理解（NL→AST） | 推荐/匹配/社媒算法、双向匹配（另文） |
| ③ ANN 索引与向量/检索引擎选型、1M–10M 规模的内存/延迟参照 | 前端交互与卡片流（另文） |
| ④ 引文/作者/概念图存储；分类树作路由/兴趣索引；倒排/位图/前缀结构 | GitHub 开源项目与初创公司全景（`docs/survey/oss/`、`docs/survey/market/`；本文只在选型需要时引用） |
| ⑤ 去重与实体消解；已见集合 | 许可/法务结论（本文只标注风险） |
| ⑥ 抓取调度与新鲜度 | |
| ⑦ 稳定性工程 | |
| ⑧ 多租户 PG、共享/私有分层、事件日志、特征存储、任务队列、SQLite→PG 迁移 | |

### 1.2 方法

- **基线梳理**：通读 README、`docs/INDEX.md`、design/01/05/06/09、decision-log（D-001/005/007/021/029/031/034/037/039）、`research/github-similar-projects.md`、`research/site-survey/{metadata-apis,aggregators-unpaywall-dblp-core,arxiv}.md`，并对照源码核实关键能力（§2.1）。在其基础上增量调研，不重复 v1 已有的站点勘察。
- **一手来源优先**：官方文档、README、CHANGELOG 与发布说明经 `gh api` / `curl` 直接取回；论文书目经 **Crossref REST API**（`/works/{doi}` 与 `query.bibliographic`）和 **arXiv API**（`id_list` 批量）逐条核验 DOI / arXiv ID，杜绝引用幻觉。
- **GitHub 指标**：`gh api repos/OWNER/REPO` 取 star / license / pushed_at / archived，`/releases` 取最新版本与日期，统一为 2026-09-26 快照（附表 A）。
- **基准处理**：厂商基准只作量级参考，注明日期、硬件、利益相关；内存以官方公式 [估算]。
- **线上探针**：对 Crossref / OpenAlex / S2 各发 1 个单条 GET，读限速与缓存响应头 [LIVE-headers]。
- **合规与隐私**：未使用任何凭证或 API key；遇 CAPTCHA / 403 **不绕过**，改用其他一手或二手来源并如实标注。UA 如实记录：最早对 help.openalex.org 的 12 次文档请求在 UA 中带了 `mailto` 联系邮箱，此后全部请求改为不含个人信息的 UA（`PaperCrawler-survey/0.1 (design research; non-commercial)`）。

### 1.3 过程记录（可复现；日期均为 2026-09-26）

| # | 动作 | 检索式 / URL / 命令 | 结果与用途 |
|---|---|---|---|
| 1 | 读仓库文档 | README.md；docs/INDEX.md；design/01、05、06、09；plan/decision-log.md；research/github-similar-projects.md；research/site-survey/metadata-apis.md、aggregators-unpaywall-dblp-core.md、arxiv.md | v1 基线（§2.1）与已知源事实 |
| 2 | 源码核对 | `grep -rli etag src`（0 命中）；阅读 `ratelimit.py`、`http.py`、`browserfetch.py` | ETag 缓存仅为设计声明；token bucket 与熔断语义 |
| 3 | 本地库只读计数 | `sqlite3` URI `mode=ro` 打开 `.paper-crawler/catalog.sqlite` 统计行数 | paper=179、identifier=228、asset=3、fulltext=3、subscription=2、task=23 |
| 4 | WebSearch（31 次） | 例："Callan Lu Croft 1995 Searching distributed collections with inference networks"；"Si Callan 2003 ReDDE"；"ReSLLM federated search"；"Dai Kim Callan Learning to Rank Resources"；"Shokouhi Si Federated Search FnTIR"；"Wiederhold 1992 Mediators"；"Information Manifold VLDB 1996"；"Capability based mediation in TSIMMIS"；"Shtok NQC TOIS 2012"；"Cormack RRF k=60"；"SPLADE v2 2109.10086"；"LitSearch EMNLP 2024"；"PaSa 2501.10120"；"SciRepEval SPECTER2"；"Qwen3-Embedding 2506.05176"；"pgvectorscale vs Qdrant 50M"；"Timescale renamed TigerData"；"Big ANN NeurIPS'23 results"；"DiskANN NeurIPS 2019"；"HNSW TPAMI"；"ScaNN ICML 2020"；"The Faiss library"；"Product quantization TPAMI 2011"；"Milvus 3.0 release 2026"；"Milvus 2.5 full text search"；"Elasticsearch RRF license"；"Elastic AGPL 2024"；"OpenSearch RRF 2.19"；"pg_textsearch BM25"；"Kuzu archived fork"；"OpenAlex topics hierarchy" | 定位一手来源 |
| 5 | WebSearch 预算耗尽 | 第 32、33 次（"Crossref REST API rate limits 2026"、"Semantic Scholar API rate limit 2026"）返回"会话 WebSearch 预算 200/200 已用尽" | 之后全部改为直接取回一手页面（curl / gh / WebFetch） |
| 6 | OpenAlex 文档 | `curl https://help.openalex.org/llms.txt`，再取 `data/topics.md`、`access/{example-costs,pricing,snapshot,sync,overview}.md`、`api/{authentication,semantic-search,tag-aboutness,grouping}.md`、`data/works/corpus.md`（以上 12 次 UA 含 mailto），随后取 `api/{searching,paging,oql}.md`（不含个人信息的 UA） | 计费、限速、快照、Topics、语义检索、group_by（§2.2、§3.4、§6.2） |
| 7 | Crossref 文档 | `crossref.org/documentation/retrieve-metadata/rest-api/access-and-authentication/` | 三档池限额（§2.2） |
| 8 | Semantic Scholar | `semanticscholar.org/product/api`；`api.semanticscholar.org/graph/v1/swagger.json` | key 1 RPS、匿名共享池；bulk 检索能力 |
| 9 | arXiv | `info.arxiv.org/help/api/tou.html`；`arxiv.org/robots.txt` | 1 请求/3 秒单连接；`Crawl-delay: 15` |
| 10 | bioRxiv | `api.biorxiv.org` | details 每页 30、pubs 每页 100 |
| 11 | NCBI E-utilities | `ncbi.nlm.nih.gov/books/NBK25497/` | **reCAPTCHA 拦截，未绕过** → PubMed 限速标 ⚠ |
| 12 | 书目核验 | Crossref `/works/{doi}` 与 `query.bibliographic` 约 45 条（间隔 1.2 s；遇一次 429 后退避 15 s 重试） | 全部 DOI 核实（§14） |
| 13 | arXiv API | `export.arxiv.org/api/query?id_list=…` 3 次批量请求（间隔 ≥3 s） | 20 篇 arXiv 论文标题/日期核实，另取 6 篇摘要 |
| 14 | 论文全文 | `barroso.org/publications/TheTailAtScale.pdf`、`cormack.uwaterloo.ca/cormacksigir09-rrf.pdf`（pdftotext） | 对冲请求数字；RRF k=60 |
| 15 | 引擎/项目文档 | pgvector README/CHANGELOG；pgvectorscale README；Qdrant capacity-planning / hybrid-queries / indexing；OpenSearch disk-based / percolate；Elastic BBQ 博客；Typesense、Meilisearch 文档；pg_textsearch、ParadeDB、LanceDB README；Milvus 3.0.0 发布说明；TigerData 基准博客；Qdrant benchmarks | §4、§5 选型事实 |
| 16 | 稳定性文档 | Envoy 熔断（retry budget）与 adaptive concurrency 文档；gRPC A6 提案；Google SRE《Handling Overload》；AWS《Exponential Backoff And Jitter》；Netflix concurrency-limits README；Fowler CircuitBreaker | §9 |
| 17 | 数据平台文档 | PostgreSQL 文档（RLS、WITH、分区、pg_trgm、PG18 发布公告）；Supabase RLS；Citus 12 博客；AWS 多租户 PG 分区模型；各队列项目 README | §10 |
| 18 | GitHub 指标 | `gh api repos/…` 约 80 个仓库 + `/releases` | 附表 A |
| 19 | HF 模型许可 | `huggingface.co/api/models/{id}`（9 个模型） | SPLADE 官方权重为 CC BY-NC-SA 4.0 等（§4.5） |
| 20 | 线上响应头探针 | Crossref `/works/10.1145/1571941.1572114`；OpenAlex `/works/doi:10.1145/1571941.1572114`；S2 `/paper/DOI:10.1145/1571941.1572114?fields=title`（各 1 次） | 三家均无 ETag/Last-Modified；Crossref 匿名为 `public-single` 池 |
| 21 | 访问失败记录 | cacm.acm.org（证书链错误）→ 改取作者自存 PDF；dl.acm.org（403）→ 改用 Crossref / S2 元数据；allenai 博客（404）→ 改用 `allenai/s2search` README；Cho & Garcia-Molina 2000/2003 全文未取回（S2 显示摘要被出版方隐去）→ 相关公式标 ⚠，结论引二手综述 | 透明性 |
| 22 | 对抗式核验（独立一轮） | 逐条复核承重断言：`gh api`、`curl`、WebFetch、arXiv/Crossref/S2 API，另发少量 LIVE 探针；方法、失败记录与逐条结论见文末“核验记录” | 就地修正或补充，均标“核验修正”或“核验补充” |

---

## 2. v1 基线与 v2 外部约束

### 2.1 v1 已有能力与缺口（与本主题相关）

| 领域 | v1 现状 | 出处 | v2 缺口 |
|---|---|---|---|
| 源能力声明 | adapter `capabilities()`（DISCOVER/ENUMERATE/RESOLVE/FETCH…）；OpenAlex/S2 为 enrich-only，不能做 watch | [v1-design09] §3 修订 #5 | 无"查询能力"细粒度描述、无覆盖/成本统计、无查询时联邦 |
| 查询编译 | 订阅 DSL → 各源原生能力下推 + 本地补偿谓词；原则"下推尽可能多，正确性以本地过滤为准"；arXiv `query_bool` 参数化谓词 | [v1-design09] §3 | 无通用查询 AST、无自然语言查询理解、无多源融合排序 |
| 本地检索 | FTS5 content-owning `paper_fts(title, abstract)`，约 13 MB/万篇；正文与向量索引 defer | [v1-design06] §2、[v1-D034] | 无语义/混合检索、无重排 |
| 去重 | identifier(scheme,value) 全局唯一强合并；观测级弱键候审；`same_as` 连通分量聚合；preprint_of 建边 | [v1-design06] §3、[v1-D007]、[v1-D031] | 无近重复召回（LSH）、无概率打分、无物化的跨源 cluster id |
| 增量 | DateCursor / IdSetDiff / arXiv 重叠 1 天窗口 + id 去重 | [v1-design09] §5 | 无按更新率自适应轮询；无多用户共享轮询 |
| 稳定性 | per-domain token bucket（多方声明取最保守值）；Retry-After 解析；transient 指数退避 3 次（2/8/30 s）；challenge 域冷却 24 h；浏览器通道同域连续 3 败当日熔断 | [v1-design05] §3–4；[v1-code] | 无自适应并发、无重试预算、无对冲；**ETag 条件缓存在 design/01、03 声明但 `src/` 0 命中** |
| 调度 | 单进程 `flock` 互斥；FIFO 任务队列，无优先级 | [v1-design05] §3、[v1-D039] | 多用户需要"交互 / 后台"分道 |
| 存储 | SQLite WAL；schema 方言中性（仅 0005 FTS 例外）；预留 PG 迁移 | D-001、[v1-design06] §6 | 多用户、RLS、事件日志、向量、图 |

### 2.2 v2 外部约束（事实）

| 源 / 事项 | 关键约束（2026-09-26） | 来源 |
|---|---|---|
| OpenAlex 计费 | 数据 CC0 免费，**API 按用量计费**：单实体查询免费；list+filter $0.10/千次；search 与 semantic search $1/千次；内容（缓存 PDF）下载 $10/千次；免费 key $1/日，无 key $0.10/日；超预算或 >100 req/s 返回 429 | [OA-cost][OA-auth] |
| OpenAlex 查询上限 | `per_page` 最大 100（200 为遗留行为，将移除）；基础分页 ≤10,000 条，更多用 cursor；单过滤 OR 值 ≤100；请求 URL ≈4 KB 上限，超长布尔 OR 需拆分后客户端并集 | [OA-auth][OA-paging][OA-search] |
| OpenAlex 语义检索 | `search.semantic`：GTE-Large EN 1024 维（title+abstract），单次最多 50 条、1 req/s；输入只用前 2000 字符，超出部分截断；不支持国家与被引数过滤 | [OA-semantic] |
| OpenAlex 语料 | core 默认 320M+ works；expansion 约 190M（2025-11 Walden 一次性批次，默认不返回）；（核验补充）2026-08 新增 works 专用参数 `corpus=`（取值 core / expansion / all），旧的 `include_xpac` 参数与 `is_xpac` 过滤已弃用，二者混用直接报错 | [OA-corpus][OA-deprecations] |
| OpenAlex 快照 | 公共桶**免费**、季度发布（1/4/7/10 月第二个周三；下一次 2026-10-14）；2026-09 版约 6.26 亿条记录，JSONL 压缩约 745 GB（works 约 615 GB），Parquet 约 770 GB；按 `updated_date` 分区；works 删除日志自 2026-09-23 版进入公共桶；日更快照与 `from_created_date`/`from_updated_date` 过滤属付费（Member+ $10,000/年起） | [OA-snapshot][OA-pricing] |
| Crossref | Public 5 req/s、并发 1；Polite（带 mailto）10 req/s、并发 3；Plus 150 req/s、无并发限；超限 429，人工封禁 403 | [Crossref-limits]；[LIVE-headers] 实测匿名为 `x-api-pool: public-single`、`x-rate-limit-limit: 5`、`x-concurrency-limit: 1` |
| Semantic Scholar | 未认证用户共享 1000 req/s（高峰可能进一步限流）；API key 入门额度 1 RPS（全端点）；语料 214M 论文、2.49B 引用；bulk 检索支持布尔逻辑、每次 ≤1000 条、续传 token、总计 ≤1000 万 | [S2-api][S2-swagger] |
| arXiv | legacy API（含 OAI-PMH、RSS、Query API）≤1 请求/3 秒、单连接，按"你控制的全部机器合计"；`arxiv.org` robots `Crawl-delay: 15`，禁止 `/api`、`/search` 等 | [arXiv-ToU][arXiv-robots] |
| bioRxiv / medRxiv | `details/[server]/[interval]/[cursor]` 每页 30 篇；`pubs`（预印本→正式发表映射）每页 100 篇；⚠ 未见书面限速 | [bioRxiv-API] |
| DBLP / CORE / Unpaywall | DBLP：**核验修正**——2026-09-26 复核 `dblp.org/robots.txt`（`dblp.uni-trier.de`、`dblp.dagstuhl.de` 两个镜像内容相同）：对 `User-agent: *` 全站 `Disallow: /`，对一长串具名 AI/爬虫 UA 同样全站禁止，文件中已无 `Crawl-delay` 行。v1（2026-07）记录的 `Crawl-delay: 4` + `Disallow: /search` 已过时。结论：在线站点（含 search API 与 `/db/**` 卷 XML）一律不得自动化访问（v1 已令 dblp 出列，D-037）；月度 XML 快照改经 DROPS 获取（`drops.dagstuhl.de` 的 robots 只禁 `/api/*` 与 metadata 路径），⚠ 下载路径与条款待来源调研确认。CORE：token 制。Unpaywall：仅按 DOI 查询，独立快照已停；“10 万次/日”为 v1 记录，本次因 unpaywall.org 产品页为 JS 渲染未能复核 ⚠ | [dblp-robots][DROPS-robots][v1-aggregators][v1-D037][OA-unpaywall] |
| PubMed / Europe PMC | （核验补充）PubMed E-utilities：无 API key 为 3 req/s，带 key 为 10 req/s，超限报错；需要更高速率须向 NCBI 申请。依据为 NLM Support Center KA-05317 与 NCBI Insights 2017-11-02 公告；E-utilities 帮助页 NBK25497 遇 reCAPTCHA，未绕过。Europe PMC ⚠ 未核验（文档页返回 403，此前为 JS 渲染，均未取回） | [NLM-eutils][NCBI-apikey17][NCBI-blocked] |
| HTTP 条件缓存 | Crossref / OpenAlex / S2 单条 GET 均**未返回** `ETag`/`Last-Modified`/`Cache-Control` → 对这三家只能做应用层 TTL 缓存 | [LIVE-headers] |

### 2.3 合规约束对架构的直接影响

1. **远端并发与速率上限 = 源方书面限额**；自适应算法只在其下调节，绝不"探测上限"（§9）。
2. **付费墙全文按用户私有**：私有资产表 + 私有存储命名空间；**不做跨用户内容去重**（避免"一人取回、多人可读"的事实共享）[判断：保守解释]。
3. **OA 全文**：只有许可允许再分发（如 CC BY）时才进入全局共享层；许可不明（如 bronze）只存链接与元数据，由用户各自取回 [判断，⚠ 需法务确认]。
4. **Google Scholar** 不进入任何自动化路由（沿用 v1）。
5. 共享轮询（watch key）只共享**元数据**收割，不共享任何需要用户凭证的取回。

---

## 3. 联邦检索、源选择与能力感知查询计划（①）

### 3.1 源选择（resource selection）方法谱系

| 方法 | 出处 | 核心思想 | 需要的统计 | 对 v2 的可迁移点 |
|---|---|---|---|---|
| CORI | Callan、Lu、Croft，SIGIR'95 [CORI95] | 在推理网络框架下对"集合"排序，并给出选集与结果合并方法 | 每源词项统计 | 无监督基线；学术 API 通常不暴露词表统计，只能采样近似 |
| ReDDE | Si & Callan，SIGIR'03 [ReDDE03] | 估计"相关文档在各源的分布"：查询采样建集中样本库 + sample-resample 估计源规模，按估计相关文档数排序；源规模差异大时优于 CORI | 采样文档 + 源规模估计 | **核心借鉴**：用"源 × 主题覆盖计数"直接替代采样（§3.5） |
| 分类式源选择 | Arguello、Callan、Diaz，CIKM'09 [Arguello09] | 把源选择当作分类问题，融合多种证据特征 | 训练查询与标注 | 有日志后可训练 |
| Selective search | Kulkarni & Callan，TOIS 2015 [SelSearch15] | 大集合按主题聚类成 shard，查询时只检索少数 shard | 主题分片 + 源选择 | 本地索引 >5000 万时的分片策略（§5.4） |
| Learning to Rank Resources | Dai、Kim、Callan，SIGIR'17 [LTRR17] | 用 LTR 排序 shard；指出浅层指标可与穷举持平，召回型指标会掉 | 查询日志 + 特征 | 召回型任务（如系统综述）要选更多源 |
| LTRR + GNN | Ergashev 等，WWW'23 [LTRR-GNN23] | 用图神经网络建模查询–资源关系 | 同上 | 远期选项 |
| ReSLLM | Wang 等，arXiv 2024 / WWW'25 Companion [ReSLLM] | 零样本用 LLM 做源选择；SLAT：用现成 LLM 给历史查询–片段打相关性伪标签再微调 | 源描述 + 片段 | 新源冷启动兜底 |
| FeB4RAG | Wang 等，SIGIR'24 [FeB4RAG24] | RAG 场景下的联邦检索评测集 | — | 评测方法参考 |
| LTRR（检索器路由） | Kim & Diaz，arXiv 2025 [LTRR-Ret25] | 把"选哪个检索器"建模为 LTR；成对排序的 XGBoost 效果最好，OOD 泛化更强 | 查询特征 + 下游效用 | 学到的路由器宜用轻量 GBDT，而非大模型 |
| 综述 | Shokouhi & Si，FnTIR 2011 [FS-FnTIR11]；Garba 等，KAIS 2023 [FS-Survey23] | — | — | 术语与评测体系 |

### 3.2 查询性能预测（QPP）：可用，但只作弱信号

| 方法 | 出处 | 要点 |
|---|---|---|
| Clarity score | Cronen-Townsend、Zhou、Croft，SIGIR'02 [Clarity02] | 以结果语言模型与集合语言模型的差异预测查询难度 |
| NQC 等 | Shtok 等，TOIS 2012 [NQC12] | 以检索得分的离散程度（query drift）预测 |
| 局限性 | Chifu 等，ACM TOIS 44(6)，2026（Crossref：印本 2026-07-31、在线 2026-08-11；核验修正，原写“2025 在线”）[QPP-Limits] | 跨范式评测：QPP 泛化差，集合是最大影响因素，其次是排序器类型；QPP 驱动的选择性查询处理只带来约 4% NDCG 增益，可靠性随设置剧烈波动 |

**结论**：QPP 只作"是否扩展到远端源 / 是否放宽查询"的弱信号之一；主依据应是结构化覆盖统计 + 结果计数 + 在线反馈。

### 3.3 Mediator / Wrapper 与"能力描述"

- Wiederhold（1992）提出在应用与数据源之间插入 mediator 层 [Mediator92]。
- Information Manifold（VLDB'96）用"源描述"在查询时剪枝不相关源，统一访问 100+ 个 Web 源 [InfoManifold96]。
- TSIMMIS 的 capability-based mediation（SIGMOD'98）指出：只看内容关系、不看源的查询能力，会生成源无法回答的计划；mediator 必须按源能力生成可行计划 [TSIMMIS98]。
- **对照 v1**：adapter capabilities + design/09 的"下推 + 本地补偿"本质上就是 wrapper + 能力感知改写。v2 要把它从"订阅专用"推广到"所有查询"，并加入覆盖与成本两个维度。

### 3.4 学术聚合源"查询能力矩阵"（路由器输入）

| 源 | 关键词检索 | 布尔 / 短语 / 字段 | 语义检索 | 主要过滤 | 增量 / 新鲜度 | 分页上限 | 限速 / 计费 | 批量 | 出处 |
|---|---|---|---|---|---|---|---|---|---|
| OpenAlex | `search`（词干化）、`search.exact` | AND/OR/NOT、短语、邻近 `~N`、通配（仅 exact） | `search.semantic`（≤50 条、1 rps） | topic/subfield/field/domain、来源、年份、OA、类型等 | 免费档只能按 `publication_date` 窗口；`from_created/updated_date` 付费 | per_page ≤100；基础 ≤1 万；cursor 无限 | list $0.10/千；search $1/千；单实体免费；≤100 rps | 季度免费快照；日更付费 | [OA-search][OA-cost][OA-snapshot] |
| Crossref | `query`、`query.bibliographic` | 字段化 `query.*`：swagger 列出 title、author、bibliographic、container-title、affiliation、funder-name 等 20 余种（核验补充）；文档未给出布尔/短语语法 | 无 | ISSN、日期族（index/pub/created…）、类型、prefix | `from-index-date`（官方推荐增量） | rows ≤1000；offset ≤1 万；cursor（5 分钟未用即过期） | Public 5/1；Polite 10/3；Plus 150/无 | Metadata Plus（付费） | [Crossref-limits][Crossref-swagger][v1-metadata-apis] |
| Semantic Scholar | `/paper/search`（相关性排序，最多返回 1000 条） | `/paper/search/bulk` 布尔；`/paper/search/match` 标题最近匹配；`/paper/autocomplete`；（核验补充）`/snippet/search`：约 500 词的正文片段检索，覆盖标题、摘要与正文，limit ≤1000 | （核验修正，原为“⚠ 推荐 API 未核验”）Recommendations API：`GET /recommendations/v1/papers/forpaper/{paper_id}`，以及 `POST /recommendations/v1/papers/`（正例/负例论文列表）；Graph API 可返回 SPECTER2 嵌入 | year / publicationDate 区间、venue（模糊名）、fieldsOfStudy | 无增量游标；Datasets 快照 | bulk 每次 1000、续传、≤1000 万 | key 1 RPS；匿名共享池 | Datasets API | [S2-swagger][S2-rec-swagger][S2-api][v1-metadata-apis] |
| arXiv | Query API `search_query` | 字段前缀 ti/au/abs/cat…、AND/OR/ANDNOT、短语、`submittedDate` 区间 | 无 | 分类、日期 | OAI-PMH `from/until`（日粒度）+ resumptionToken；RSS 当日快照 | `max_results` ≤2000/次、总翻页 ≤3 万 | 1 请求/3 秒单连接 | Kaggle 元数据、S3 全文（requester-pays） | [arXiv-ToU][v1-arxiv] |
| bioRxiv / medRxiv | 无关键词端点 | — | 无 | 日期区间；最近 N 篇 / N 天 | 区间游标 | 30/页（details）；100/页（pubs） | ⚠ | — | [bioRxiv-API] |
| CORE | `search/works` | ES 式 `field:value`、AND/OR/NOT | ⚠ | yearFrom / yearTo | ⚠ | ⚠ | token 制 | 有 | [v1-aggregators] |
| DBLP | 在线站点被 robots 全站禁止（2026-09-26 核验修正） | — | — | — | 月度 XML 快照（DROPS）⚠ | — | 不得自动化访问 | `dblp.xml.gz`（经 DROPS）⚠ | [dblp-robots][DROPS-robots][v1-aggregators] |
| Unpaywall | 无检索，只按 DOI | — | — | — | — | 批量 POST ≤1000 DOI | 10 万/日（v1 记录 ⚠） | 改用 OpenAlex 快照 | [v1-aggregators][OA-unpaywall] |
| PubMed / Europe PMC | ⚠ | ⚠ | ⚠ | ⚠ | ⚠ | ⚠ | E-utilities 无 key 3 req/s，带 key 10 req/s（核验补充）；Europe PMC ⚠ | ⚠ | [NLM-eutils][NCBI-apikey17][NCBI-blocked] |

### 3.5 v2 推荐：能力 × 覆盖 × 成本的路由器

#### 3.5.1 路由图（Routing Graph）

- **节点三类**：
  - **F（查询面）**：Topic 树节点（domain / field / subfield / topic）、venue、identifier scheme（doi / arxiv / pmid / ssrn…）、查询意图（LOOKUP / SEARCH / LATEST / SIMILAR / EXPAND）；
  - **C（能力）**：`kw.bool`、`kw.phrase`、`kw.field`、`sem.search`、`filter.date`、`filter.topic`、`filter.venue`、`id.lookup.<scheme>`、`incr.since`、`oa.pdf` 等；
  - **S（源端点）**：`openalex.works.search`、`crossref.works.query`、`arxiv.query`、`s2.bulk`、`local.bm25`、`local.ann` 等。
- **边与权重**：F→S 带 `(coverage, lag_days, λ_new/day)`；S→C 带 `native | emulated | none` 与保真度；S 本身带 `cost`（$/credit/次、翻页数）、`politeness`（最小间隔、并发）、`health`（成功率 EWMA、p95 延迟）、`budget_remaining`。
- **统计来源与成本**：
  - OpenAlex `group_by` 对 works 聚合，单页最多 200 组、cursor 翻页 [OA-groupby]。对 4,516 个 topic 各做约 2 次调用，约 9,000 次 × $0.10/千 ≈ **$0.90** [估算]，在免费 key 的 $1/日额度内，可周更。（核验修正，原为“假设 `group_by` 按 list+filter 计价，⚠ 未核验”）[LIVE] 2026-09-26 匿名发出 1 次 `group_by` 请求，响应头为 `x-ratelimit-credits-used: 1`、`x-ratelimit-cost-usd: 0.0001`，与 list+filter 同价；单实体请求计 0。某 topic 的来源数超过 200 时需按 cursor 多翻页，调用数会高于估算。另一选择是直接用免费季度快照离线计算（零 API 成本）[OA-snapshot]。
  - 自有入库日志：每个源在每个 topic 上的"独有贡献"（其他源未覆盖的 work 数）、真实滞后（发布日 → 可见日）。
  - 不在 OpenAlex 中或 OpenAlex 覆盖弱的源（如 SSRN 走 Crossref prefix，见 D-029），只用自有日志估计。

#### 3.5.2 路由算法（设计伪代码）

```python
# 设计伪代码 —— 非接口冻结
def route(ast: QueryAST, ctx: RouteContext) -> list[SourcePlan]:
    intent = ast.intent
    if intent == LOOKUP and ast.identifiers:
        return lookup_chain(ast)                 # 本地 → 同能力替补链（§3.5.5），无需选源

    topics = topic_posterior(ast)                 # P(t|q)：显式过滤 > 本地分类器 > OpenAlex /text（冷启动）
    plans = [local_plan(ast)]                     # 本地 BM25 + ANN + facet 永远参与
    if local_coverage(ast, topics) >= ctx.coverage_target and not ctx.force_remote:
        return plans                              # "先收割、后联邦"：本地覆盖够就不出网

    cands = []
    for s in sources_with_required_caps(ast):     # 硬约束：必需能力（如 id.lookup / filter.date）
        if breaker_open(s):                       # 熔断中的源直接剔除
            continue
        q_s = relax(ast, caps(s))                 # 健全放宽：保证 P ⇒ P_s（不丢结果）
        gain = sum(p * cov(s, t) * (1 - overlap(s, t, plans)) for t, p in topics.items())
        cost = (w_lat * p95_latency(s) + w_money * money(s, q_s)
                + w_polite * politeness_time(s, q_s) + w_risk * (1 - health(s)))
        cands.append((s, q_s, gain, cost))
    plans += greedy_budgeted_cover(cands, budget=ctx.budget)  # 按 gain/cost 贪心 + 单项最优兜底
    return plans
```

- `greedy_budgeted_cover`：覆盖函数单调次模，普通基数约束下贪心有 (1−1/e) 近似 [Submod78]；带成本的预算版本需"贪心 + 单项最优/部分枚举"修正才有常数近似 [BudgetMC99]。本场景候选源通常 <20，精确枚举也可行 [判断]。
- `topic_posterior`：优先使用本地分类器（用 OpenAlex 已标注 work 的向量求各 topic 质心，查询向量取最近若干 topic 并 softmax）；冷启动或低置信时调用 OpenAlex `/text/topics`（$0.01/次、1 rps、输入 20–2000 字符）[OA-text]。（核验补充）OpenAlex example-costs 页已把 “Text / Aboutness” 标为 *deprecated*（$10/千次，与 $0.01/次一致），而 tag-aboutness 页与 deprecations 页均未说明弃用，两处文档不一致。因此 `/text` 只宜作可替换的冷启动兜底，不作长期依赖 [OA-cost][OA-deprecations]。

#### 3.5.3 健全放宽（sound relaxation）规则

目标：对每个源生成 `P_s`，使满足原谓词 `P` 的文档一定满足 `P_s`（即 `P ⇒ P_s`，源侧只会多返回、不会少返回），精度由本地残差过滤 `P` 保证。

| AST 算子 | 源不支持时的放宽 | 本地残差 | 代价提示 |
|---|---|---|---|
| `Not(X)` | 删除该子句（视为 true） | 本地求 `Not(X)` | 结果量可能暴涨 → 成本模型可能改选他源 |
| `And(A, B)`，B 不支持 | 只下推 A | 本地求 B | 常见、便宜 |
| `Or(A, B)`，B 不支持 | 整个 `Or` 视为 true（无约束） | 本地求 `Or` | 往往不可接受 → 该源剔除 |
| 短语 `"a b"` | 退化为 `a AND b` | 本地短语匹配 | 小幅扩量 |
| 邻近 `~N` | 退化为短语或 AND | 本地邻近 | 同上 |
| 前缀 / 通配 | 删除或改用 exact 字段 | 本地前缀 | OpenAlex 通配只在 `search.exact` 可用 [OA-search] |
| 日期区间 | 放宽为整年或删除 | 本地精确日期 | 删除日期可能导致翻页量不可控 |
| 超长 OR 列表 | **拆分**为多个子查询，客户端并集（分配律，结果集不变） | — | OpenAlex 请求 URL 约 4 KB 上限、单过滤 OR ≤100 [OA-search][OA-auth] |
| `Semantic(text)` | 源无语义能力 → 改为关键词抽取后的 `kw` 查询 | 本地向量重排 | 召回质量下降，需在报告中标注 |

- **极性前提（正确性要点）**：上表"替换为 true"只在正极性位置成立。实现时先把 AST 规范化为否定范式（NNF，否定只作用于原子），再对**正极性**位置的不支持子式替换为 `true`、**负极性**位置替换为 `false`；否则如 `Not(A And Not(B))` 中直接删掉 `Not(B)` 会把查询收紧而丢结果 [判断：标准逻辑推导]。每条放宽规则都应有"放宽后结果 ⊇ 原结果"的属性测试。
- **分析器一致性风险**：远端词干化（OpenAlex 默认 `search` 做词干与停用词处理 [OA-search]）而本地残差用正则，会把远端命中的变形词误杀。v2 的本地残差必须使用与目标源对齐的分析器（至少同为词干化 + 大小写归一），并对"远端命中而本地拒绝"的样本单独计数、告警。

#### 3.5.4 学习与探索

1. **冷启动**：覆盖统计来自 OpenAlex `group_by`/快照 + 规则先验（例：经济学 WP → SSRN/NBER/RePEc 高权重）。
2. **在线探索**：对"源 × topic 的有效产出率"维护 Beta 后验，用 Thompson sampling 决定是否偶尔多选一个不确定的源 [TS-Tutorial18]，防止统计冻结。
3. **有日志后**：以"每个源的独有贡献 + 用户保存/点赞"作监督信号，训练 LTR 路由器（GBDT 成对排序，形态参照 LTRR [LTRR-Ret25]）。
4. **新源接入**：先用 LLM 零样本源选择（ReSLLM 形态 [ReSLLM]）给出初始边权，积累日志后被统计值替代。

#### 3.5.5 同能力替补链（稳定性）

| 能力 | 替补顺序（首选 → 兜底） | 说明 |
|---|---|---|
| DOI 元数据 | 本地 → Crossref → OpenAlex 单实体（免费）→ S2 | OpenAlex 单实体不计费 [OA-cost] |
| OA PDF 定位 | 本地 → Unpaywall → OpenAlex `best_oa_location` → CORE | 沿用 v1 OA-fallback；PDF 下载仍走用户侧合规通道 |
| arXiv 最新 | 本地收割（OAI-PMH / RSS）→ arXiv Query API | 查询时联邦受 1 请求/3 秒约束 |
| 标题精确匹配 | 本地 trigram → S2 `/paper/search/match` → Crossref `query.bibliographic` | [S2-swagger] |
| 语义探索 | 本地 ANN → OpenAlex `search.semantic`（≤50 条） | 远端只作补充 |

#### 3.5.6 规模边界与失败模式

- 源数 ≤50、topic 节点 ≤5,000 时，路由决策是内存中的毫秒级计算 [判断]。
- 覆盖统计本身会过时：OpenAlex topic 分类只覆盖约 88% 的 work（2026 年中约 39.6M/322M 无 topic）[OA-topics]，无 topic 的 work 需要用自有分类器补标。
- 路由错误表现为"召回缺口"，必须有离线评测（§12 第 21 条）和线上"未覆盖反馈"入口。

---

## 4. 混合检索与查询理解（②）

### 4.1 组件与证据

| 组件 | 代表 | 关键事实 | 对 v2 的意义 |
|---|---|---|---|
| BM25 / 词法 | BM25 [BM25-09]；Lucene/Tantivy；PG 扩展 | BEIR 显示 BM25 是零样本检索中强且稳健的基线 [BEIR21] | 本地第一路召回；对术语、缩写、公式名精准 |
| 学习稀疏 | SPLADE [SPLADE21]、SPLADE v2 [SPLADEv2] | SPLADE v2 以蒸馏等改进在 TREC DL 2019 上 NDCG@10 提升超 9%，BEIR 上领先 [SPLADEv2]；**官方代码与权重为 CC BY-NC-SA 4.0（非商业）**[SPLADE-lic] | 若平台商业化，不能用官方权重；可选 Apache-2.0 的替代（§4.5） |
| 稠密双塔 | DPR [DPR20]；SPECTER [SPECTER20]；SPECTER2 / SciRepEval [SciRepEval23]；BGE-M3 [BGE-M3]；Qwen3-Embedding [Qwen3Emb25] | SciRepEval：按任务格式的适配器比单一嵌入 SOTA 高 2 分以上 [SciRepEval23]；OpenAlex 语义检索用 GTE-Large EN 1024 维 [OA-semantic] | 语义召回主力；学术领域需自有评测选型 |
| 后期交互 | ColBERT [ColBERT20]、ColBERTv2 [ColBERTv2] | 词元级向量，精度高、存储大 | T2 以上可评估，T1 不建议 |
| 交叉编码 / LLM 重排 | RankGPT [RankGPT23]；Qwen3-Reranker [Qwen3Emb25] | LitSearch：LLM 重排在最佳稠密检索器之上再提升 4.4% [LitSearch24] | 只对前 50–100 条重排，控制成本 |
| 智能体检索 | PaSa [PaSa25] | Crawler + Selector 双智能体，调用检索工具、读论文、沿引文扩展；用 3.5 万条合成学术查询做强化学习；在真实查询集 RealScholarQuery 上，PaSa-7B 比最强 Google 基线（Google + GPT-4o）recall@20 高 37.78%、recall@50 高 39.90% | "深度检索"模式的参考形态（异步、可取消） |
| 工业参照 | Semantic Scholar 搜索重排器 [s2search] | 标准流水线 = 一阶段召回（如 Elasticsearch）+ 重排器；开源模型需 >17 GB 内存（大型 kenlm 模型） | 两段式是共识 |

**学术检索的直接证据**：LitSearch（597 条真实文献检索问题，ML/NLP 领域）中，最佳稠密检索器与 BM25 的 recall@5 绝对差为 24.8%；Google Search 等商业搜索引擎与研究工具落后最佳稠密检索器 32 个点 [LitSearch24]。BEIR 同时提醒：BM25 是稳健基线，重排与后期交互模型零样本平均最好但计算代价高，稠密/稀疏模型更省却常常落后 [BEIR21]。结论：学术检索必须有语义通道，BM25 不能单独承担，但也不能丢掉。

### 4.2 融合方式对比

| 方式 | 定义 / 默认值 | 出处 | 适用 |
|---|---|---|---|
| RRF | `score(d) = Σ 1/(k + r(d))`；原论文 k=60，在试点中确定、之后未再调 | [RRF09] | 分数不可比时的默认选择（跨源融合必用） |
| Qdrant RRF | 同公式但带每路权重 `w_r`（默认 1），**默认 k=2**，零起点排名；v1.16 起可用 `{"rrf": {"k": 60}}` 设定 k（核验补充） | [Qdrant-hybrid] | 注意与原论文 k 值不同 |
| DBSF | 每路按均值 ±3σ 归一后相加（Qdrant ≥1.11） | [Qdrant-hybrid] | 分数分布稳定时 |
| Typesense rank fusion | 关键词与语义两路按排名加权（默认 0.7/0.3，`alpha` 可调） | [Typesense-hybrid] | 简单权重 |
| Meilisearch | `hybrid.semanticRatio`（0–1）；`rankingScoreThreshold` 过滤低相关 | [Meili-hybrid] | 简单权重 |
| OpenSearch | 分数型 normalization-processor；2.19 起 score-ranker-processor（RRF） | [OS-RRF] | 两者皆开源可用 |
| Elasticsearch | RRF retriever。（核验修正：已直接核验订阅页）elastic.co/subscriptions 功能矩阵（2026-09-26）中，“Reciprocal Rank Fusion (RRF) for hybrid search” 与 “Retrievers: linear, rule, RRF, text similarity re-ranker” 两项只在 Enterprise 档打勾；第三方文章另称 Basic 档调用返回 403 | [ES-RRF][ES-subs][ES-RRF-lic] | 自托管免费版需自行在应用层做 RRF |

**v2 融合策略**：跨源（本地 + 远端）一律 RRF（k=60 起步）；本地 BM25 + 向量两路也用 RRF 起步，积累点击/保存后改学习型加权（按查询意图分桶学权重）。

### 4.3 查询理解：自然语言 → 结构化查询 AST

#### 4.3.1 AST 定义（设计伪代码）

```text
# 设计伪代码 —— 非接口冻结
Query    := { intent: LOOKUP | SEARCH | LATEST | SIMILAR | EXPAND,
              expr: BoolExpr?, filters: [Filter], sort: RELEVANCE | RECENCY | CITATIONS,
              k: int, freshness_sla: duration?, lang_pref: [lang] }
BoolExpr := And[BoolExpr] | Or[BoolExpr] | Not[BoolExpr]
          | Term{ field: any|title|abstract|author|venue|fulltext, text,
                  mode: word|phrase|prefix|near(n) }
          | Semantic{ text }                              # 交给稠密/学习稀疏通道
          | IdRef{ scheme: doi|arxiv|pmid|ssrn|openalex|s2, value }
Filter   := DateRange{ field: published|indexed|created, from, to }
          | TopicIn{ ids, level: domain|field|subfield|topic, match: primary|any }
          | VenueIn{ ids } | AuthorIs{ id|name } | InstitutionIs{ id }
          | IsOA{ bool } | TypeIn{ ... } | LangIn{ ... }
          | Cites{ work } | CitedBy{ work } | InLibrary{ user } | NotSeen{ user }
```

- `TopicIn.match` 区分 `primary` 与 `any`：OpenAlex 指出只用 primary topic 精确度高但召回低，用 `topics.subfield.id` 覆盖全部三个 topic 可找回部分召回 [OA-topics]。
- `NotSeen{user}` 由用户私有的 roaring 位图实现（§6.3）。

#### 4.3.2 解析流水线

1. **快速路径（规则，毫秒级）**：正则抽取 DOI、arXiv 新旧两代 ID（v1 已兼容 [v1-arxiv]）、PMID、SSRN id、URL；识别引号短语与 `ti:` / `au:` 等 arXiv 风格前缀；识别"2023 年以来""近三个月"等时间表达。
2. **LLM 结构化输出**：以 JSON Schema 约束生成 AST；自托管模型用受约束解码（outlines / xgrammar / llguidance，均为 Apache-2.0 或 MIT）[ConstrainedDec]。中文查询同时产出英文检索词，原文保留给多语向量通道。
3. **实体链接**：venue / 作者 / topic 名称 → 内部 ID（本地 pg_trgm 相似度 [pg_trgm] + 向量近邻）；歧义时以"可编辑筛选条"交给用户确认，而不是静默猜测。
4. **校验与成本预览**：Schema 校验 → 能力可行性检查 → 预估远端调用次数与费用；超预算时提示收窄。
5. **投机执行**：LLM 解析期间先用原始文本跑一次本地 BM25 + 向量检索，先出首屏，解析完成后再精排替换 [判断]。
6. **缓存**：规范化查询文本 → AST 的缓存，降低 LLM 调用量。

### 4.4 v2 推荐（混合检索）

- **两段式**：候选生成（本地 BM25 + 本地 ANN + 路由器选中的远端源）→ 以 work cluster 去重 → RRF → 小型 cross-encoder 重排前 100 → 个性化重排挂点（交推荐文档）。
- **可选深度模式**：PaSa 式"检索—阅读—沿引文扩展"的异步任务，结果以增量方式推送，用户可随时取消 [PaSa25]。
- **规模边界**：≤1000 万篇、检索 ≤50 QPS 时 PG 单节点即可；更大或更高 QPS 时外移到专用引擎（§5.4）[判断]。

### 4.5 模型许可速查（Hugging Face 模型页 API，2026-09-26）

| 模型 | 许可 | 备注 |
|---|---|---|
| naver/splade-v3、naver/splade-cocondenser-ensembledistil | CC BY-NC-SA 4.0 | 非商业 [HF-lic][SPLADE-lic] |
| opensearch-project/opensearch-neural-sparse-encoding-doc-v3-distill | Apache-2.0 | 学习稀疏的商业可用替代 [HF-lic] |
| prithivida/Splade_PP_en_v1 | Apache-2.0 | 同上 [HF-lic] |
| BAAI/bge-m3 | MIT | 多语；稠密 + 稀疏 + 多向量 [BGE-M3][HF-lic] |
| Qwen/Qwen3-Embedding-0.6B | Apache-2.0 | 多语；同系列有 Reranker [Qwen3Emb25][HF-lic] |
| allenai/specter2_base | Apache-2.0 | 科学文献专用 [SciRepEval23][HF-lic] |
| thenlper/gte-large | MIT | OpenAlex 语义检索所用模型 [OA-semantic][HF-lic] |
| google/embeddinggemma-300m | Gemma 许可（需手动申请） | 许可条款需单独审查 [HF-lic] |

---

## 5. ANN 索引与向量 / 检索引擎选型（③）

### 5.1 算法谱系

| 算法 | 出处 | 核心机制 | 优点 | 代价 / 风险 |
|---|---|---|---|---|
| HNSW | Malkov & Yashunin，TPAMI 2020 [HNSW20] | 分层可导航小世界图 | 内存内高召回、低延迟；增量插入 | 内存大；过滤后召回可能塌陷 |
| IVF / IVF-PQ | Jégou、Douze、Schmid，TPAMI 2011 [PQ11]；Faiss [Faiss24] | 倒排聚类 + 乘积量化压缩 | 内存省，批量构建快 | 召回依赖 nprobe；更新需重训 |
| DiskANN / Vamana | Subramanya 等，NeurIPS 2019 [DiskANN19] | SSD 上的图索引 + 内存压缩向量 | 单机 64 GB 内存 + SSD 索引 10 亿点；SIFT1B 上 16 核 >5000 QPS、平均 <3 ms、1-recall@1 ≥95% | 构建慢；需要 NVMe |
| Filtered-DiskANN | Gollapudi 等，WWW 2023 [FilteredDiskANN23] | 构图时感知标签 | 标签过滤下仍保持召回 | 标签需预定义 |
| FreshDiskANN | Singh 等，arXiv 2021 [FreshDiskANN21] | 流式增删 | 适合持续入库 | 实现复杂 |
| ScaNN | Guo 等，ICML 2020 [ScaNN20] | 各向异性向量量化 | 同召回下吞吐高 | 生态主要在 Google 系 |
| 过滤 ANN 研究 | FANNS 综述 [FANNS-Survey25]；Curator [Curator26] | 低选择率过滤下图索引连通性崩塌；Curator 以"分区索引 + 图索引"双索引，低选择率查询延迟相对预过滤回退最多降 20.9×，构建时间与内存仅 +5.5% / +4.3% | 指出 pre/post-filter 之外的第三条路 | 学术原型 |
| 基准 | ANN-Benchmarks [ANNB20]；Big-ANN NeurIPS'23 [BigANN23] | NeurIPS'23 四赛道：过滤、OOD、稀疏、流式；稀疏赛道为 MS MARCO 8,841,823 段 SPLADE 向量，论文只写“维度 <10⁵”、平均约 120 个非零；查询 6,980 条，平均约 49 个非零（核验修正：原写“约 3 万维”，论文无此数） | 独立、可复现 | 与真实学术数据分布不同 |

### 5.2 引擎选型对比（版本与活跃度见附表 A）

| 引擎 | 形态 | 混合检索 | 过滤 ANN | 多租户 | 许可 | 对 v2 的适配判断 |
|---|---|---|---|---|---|---|
| **pgvector 0.8.6** | PG 扩展 | 与 PG 全文 / BM25 扩展组合，RRF 或 cross-encoder 在应用层 [pgvector] | 0.8.0（2024-10-30）起 iterative index scan：`hnsw.iterative_scan = strict_order/relaxed_order`，`hnsw.max_scan_tuples` 默认 20,000 [pgvector] | 官方建议 list 分区或分表实现租户隔离 [pgvector] | PostgreSQL 许可 | **T1 首选**：与事务数据同库、零新增运维 |
| **pgvectorscale 0.9.1** | PG 扩展（Rust） | 同上 | StreamingDiskANN + SBQ 量化；`smallint[]` 标签过滤（Filtered-DiskANN 思路），`&&` 重叠算子 [pgvectorscale] | 同 PG | PostgreSQL 许可 | 内存吃紧或 >1000 万时的 PG 内升级路径 |
| VectorChord 1.1.1 | PG 扩展 | 配套 VectorChord-bm25 | 支持 | 同 PG | AGPLv3 / ELv2 双许可 [VectorChord] | 许可偏重，备选 |
| **pg_textsearch 1.4.0** | PG 扩展（C） | BM25（k1、b 可配）+ Block-Max WAND；表达式/部分/分区索引；并行建索引 [pg_textsearch]。（核验补充）分区表的 BM25 统计（IDF）按分区各自计算，跨分区分数不可直接比较 | — | 同 PG | PostgreSQL 许可；**正式支持 PG 17/18**，PG 19 beta 期间为 best-effort | BM25 首选候选（许可宽松）；语料表若分区，需按分区查询或另做分数归一 |
| **ParadeDB pg_search 0.25.x** | PG 扩展（Rust，基于 Tantivy） | 全文 + 向量 + 聚合 + facets [ParadeDB] | 支持过滤 | 同 PG | **AGPL-3.0** | 功能更全；AGPL 需评估（SaaS 场景） |
| Qdrant 1.19.1 | 独立服务 | Query API：prefetch 多路 + RRF/DBSF [Qdrant-hybrid] | 可过滤 HNSW（payload 索引需先于数据建立）；基于过滤基数估计的查询规划；`full_scan_threshold` 默认 10,000 KB 以下改全扫 [Qdrant-indexing] | ≥1.11 Tenant Index（按租户建子索引）[Qdrant-indexing] | Apache-2.0 | T2 专用向量库首选候选 |
| LanceDB 0.40（beta） | 嵌入式 / 云；Lance 列式格式 | 向量 + 全文 + SQL [LanceDB] | 支持 | — | Apache-2.0 | 适合离线分析与数据湖，不作在线主库 |
| Milvus 3.0.2 / 2.6.24 | 分布式服务 | 2.5 起内置 Tantivy 与稀疏 BM25 [Milvus25]；lake-native External Collection 由 3.0-beta 引入、3.0.0（2026-07-29）完善（可原地查询 Parquet / Lance / Iceberg / Vortex）；3.0.0 另有在线加列、回填与删列，以及稀疏索引改造（SINDI、Block-Max WAND/MaxScore）[Milvus3] | 支持 | 支持 | Apache-2.0 | 规模 >1 亿再考虑；运维重 |
| Vespa | 独立服务 | 声明式分阶段排序：内容节点上 first-phase / second-phase，合并后在容器上 global-phase（可做跨路分数归一）[Vespa-phases] | 支持 | 支持 | Apache-2.0 | T2 候选（排序表达力最强，学习曲线陡）[判断] |
| OpenSearch 3.8.0 | 独立服务 | normalization / RRF 处理器 [OS-RRF]；percolate 反向检索 [OS-percolate] | `on_disk` 模式默认 32× 压缩 + 全精度重打分 [OS-disk] | 索引 / 别名级 | Apache-2.0 | T2 候选；percolate 适合订阅匹配 |
| Elasticsearch 9.5.4 | 独立服务 | RRF retriever（Enterprise 级，已按订阅页核验）[ES-subs]；BBQ 量化约 95% 内存降低（2024-11-11，厂商自测）[ES-BBQ24] | 支持 | 同上 | 默认 AGPLv3 / SSPL / ELv2 三选一（2024-08-29 宣布增加 AGPL 选项）[ES-AGPL24]；（核验补充）`x-pack` 目录代码只以 ELv2 授权 [ES-lic] | 许可与付费功能门槛使其不如 OpenSearch |
| Weaviate 1.39.7（核验补充） | 独立服务（Go） | BM25 + 向量混合，融合方式有 `relativeScoreFusion`（v1.24 起默认）与 `rankedFusion`，用 `alpha` 调权 [Weaviate-hybrid] | 支持 | **原生多租户**：每个租户一个独立 shard，租户可置为 ACTIVE / INACTIVE / OFFLOADED [Weaviate-MT] | `wl/` 目录外为 BSD-3-Clause；`wl/` 内功能为 Weaviate License，需 license key 才启用 [Weaviate-lic] | T2 候选；若需要“每用户私有向量空间”，其多租户模型最直接 [判断] |
| Tantivy 0.26.1 | Rust 库 | BM25、短语、facets、范围、聚合；启动 <10 ms [Tantivy] | — | — | MIT | 嵌入式全文的底层积木（ParadeDB、Milvus 已采用） |
| Meilisearch 1.54 | 独立服务 | `semanticRatio` 混合 [Meili-hybrid] | 支持 | — | MIT + BUSL-1.1（企业部分）[Meili-lic] | 面向产品搜索框，非学术大语料首选 |
| Typesense v30.2 | 独立服务（内存型） | rank fusion（`alpha`）[Typesense-hybrid] | 支持 | — | GPL-3.0 | 同上 |

### 5.3 1M–10M 规模的内存估算与已发表基准

**内存估算** [估算]：公式取自 Qdrant 容量规划文档——稠密向量 `N × d × 每维字节`；HNSW 链接 `N × m × 2 × 4 B × 1.2`（m 默认 16）[Qdrant-capacity]。pgvector HNSW 索引大小按"每向量 = 向量字节 + 约 2m 个 6 字节邻居指针 + 约 64 B 开销"粗估（⚠ 粗估，实测为准）。FTS 按 v1 D-034 的 content-owning FTS5 约 13 MB/万篇外推 [v1-D034]。

| N | d | float32 | halfvec（fp16） | int8 | 二值 | HNSW 链接（m=16） | pgvector halfvec HNSW 索引（粗估） | 标题+摘要全文索引（外推） |
|---|---|---|---|---|---|---|---|---|
| 100 万 | 768 | 3.07 GB | 1.54 GB | 0.77 GB | 0.10 GB | 0.15 GB | ≈1.8 GB | ≈1.3 GB |
| 100 万 | 1024 | 4.10 GB | 2.05 GB | 1.02 GB | 0.13 GB | 0.15 GB | ≈2.3 GB | ≈1.3 GB |
| 500 万 | 1024 | 20.5 GB | 10.2 GB | 5.1 GB | 0.64 GB | 0.77 GB | ≈11.6 GB | ≈6.5 GB |
| 1000 万 | 768 | 30.7 GB | 15.4 GB | 7.7 GB | 0.96 GB | 1.54 GB | ≈18 GB | ≈13 GB |
| 1000 万 | 1024 | 41.0 GB | 20.5 GB | 10.2 GB | 1.28 GB | 1.54 GB | ≈23 GB | ≈13 GB |
| 5000 万 | 1024 | 204.8 GB | 102.4 GB | 51.2 GB | 6.4 GB | 7.7 GB | ≈116 GB | ≈65 GB |

解读：1000 万篇 × 1024 维用 `halfvec` 时，HNSW 常驻约 20–25 GB，64–128 GB 内存的单机可容纳并留出事务与缓存空间 [判断]；若改为"二值量化 HNSW + 原始向量重打分"（pgvector 表达式索引 `binary_quantize(...)::bit(n)` 后重排 [pgvector]），常驻可降到约 3 GB 量级 [估算]，代价是召回需重排补偿。

**已发表基准**（注意日期、硬件与利益相关）：

| 基准 | 日期 | 规模 / 硬件 | 结果 | 性质 |
|---|---|---|---|---|
| TigerData：pgvector + pgvectorscale vs Qdrant [Tiger-QdrantBench25] | 2025-04-29 | 5000 万 Cohere 768 维；AWS r6id.4xlarge（16 vCPU、128 GB、950 GB NVMe），单节点（Qdrant 1.13.4，2 分片；当前 Qdrant 已到 1.19.1，结论可能已变化） | 99% 召回：PG 471.57 QPS vs Qdrant 41.47 QPS（11.4×）；p50 31.07 vs 30.75 ms；p95 60.42 vs 36.73 ms；p99 74.60 vs 38.71 ms；建索引 11.1 h vs 3.3 h | **厂商自测**（PG 方） |
| pgvectorscale README vs Pinecone s1 [pgvectorscale] | 未注日期 | 5000 万 Cohere 768 维 | 99% 召回下 p95 延迟低 28×、吞吐高 16× | **厂商自测** |
| Qdrant benchmarks [Qdrant-bench] | 2024 | dbpedia-openai 100 万 × 1536、deep-image 1000 万 × 96 等；8 vCPU / 32 GB 服务器 | 自称多数场景 RPS 与延迟最佳 | **厂商自测**（Qdrant 方） |
| DiskANN 论文 [DiskANN19] | 2019 | SIFT1B（10 亿 × 128），64 GB 内存 + SSD，16 核 | >5000 QPS，平均 <3 ms，1-recall@1 ≥95% | 学术 |
| Elastic BBQ [ES-BBQ24] | 2024-11-11 | 多数据集 | float32 → 1 bit，约 95% 内存降低；相对 PQ 量化时间少 20–30×、查询快 2–5× | **厂商自测** |
| OpenSearch `on_disk` [OS-disk] | 文档（未注日期） | — | 默认 32× 压缩，全精度向量从磁盘重打分 | 文档说明 |

**方法论提醒**：两份厂商基准对同一对手（Qdrant）给出相反的吞吐与尾延迟结论，说明结果对并发模型、分片、召回点与构建参数高度敏感。v2 必须用**自有语料 + 自有查询集**在目标硬件上复测，至少报告 recall@k、p50/p95/p99、构建时间、常驻内存四项。

### 5.4 v2 推荐与规模边界

| 档位 | 向量索引 | 词法索引 | 迁移触发条件 [判断] |
|---|---|---|---|
| T0/T1（≤1000 万篇） | pgvector `halfvec` HNSW（m=16、ef_construction 64–128；在线 `SET LOCAL hnsw.ef_search`；过滤查询开 `relaxed_order` + 物化 CTE 保序 [pgvector]） | pg_textsearch（首选，PG 许可）或 ParadeDB（AGPL） | HNSW 无法常驻内存；检索 p95 >300 ms；建索引窗口 >夜间维护窗口 |
| T1+（1000 万–5000 万） | pgvectorscale `diskann` + SBQ；subfield/topic 编号作 `smallint[]` 标签过滤（252 个 subfield 与 4,516 个 topic 均在 smallint 范围内）[pgvectorscale][OA-topics] | 同上 | 写入与检索争用；需要水平扩展 |
| T2（5000 万–1 亿+） | 专用引擎（Qdrant / Vespa / OpenSearch 三选一），经 outbox/CDC 从 PG 同步；按主题分片 + selective search [SelSearch15] | 专用引擎内置 | — |

---

## 6. 图与树：引文 / 作者 / 概念图与分类树路由（④）

### 6.1 图存储选型

| 方案 | 形态 | 查询语言 | 许可 / 状态（2026-09-26） | 适用 | 判断 |
|---|---|---|---|---|---|
| PG 邻接表 + 递归 CTE | 与主库同体 | SQL `WITH RECURSIVE`；PG14+ 支持 `SEARCH DEPTH/BREADTH FIRST` 与 `CYCLE ... SET ... USING` 环检测 [PG-WITH] | PostgreSQL | 1–2 跳在线查询、祖先/后代、引文邻域 | **T1 首选** |
| Apache AGE | PG 扩展 | openCypher | Apache-2.0；分支覆盖 PG11–PG19，PG18 版 1.8.0-rc0（2026-07-09）[AGE] | 多跳模式匹配 | 需要 Cypher 时的第一备选（不离开 PG） |
| Neo4j | 独立服务 | Cypher | 社区版 GPL-3.0；日历版本号（2026.09.0）[Neo4j] | 重度图应用 | 多一套运维与数据同步，暂不引入 |
| Kùzu | 嵌入式 | Cypher | **已归档**：仓库 README 称"Kuzu is working on something new"，最后推送 2025-10-10 [Kuzu]；社区分支 LadybugDB（MIT，活跃）、Bighorn（MIT）、RyuGraph（2026-01 后未更新）[Kuzu-forks] | 嵌入式分析 | **不选**；归档是依赖风险教训 |
| DuckDB + DuckPGQ | 嵌入式分析 | SQL/PGQ + 图算法扩展 | DuckDB MIT（v1.5.5，2026-07-22）；DuckPGQ MIT [DuckPGQ] | 离线图分析、快照分析 | 离线分析可选 |
| igraph / networkx / rustworkx | 内存库 | Python API | GPL-2.0 / BSD-3 / Apache-2.0 [GH-snapshot] | PageRank、社区发现、共被引 | 夜间批处理；分发时注意 igraph 的 GPL |
| 综述 | — | — | Coimbra 等，arXiv 2505.24758（v4，2026-07-01）[GraphDB-Survey25] | 选型参考 | — |

**规模参照** [估算]：1000 万篇 × 平均约 30 条参考文献 ≈ 3 亿条边；内存 CSR 用 int32 存目标节点约 1.2 GB（外加偏移数组约 40 MB），单机批处理可行。在线服务不需要把整图装进内存，按索引做 1–2 跳即可。

### 6.2 分类树作路由索引与兴趣树

**OpenAlex Topics 事实** [OA-topics][OA-text]：

- 层级：4 domain → 26 field → 252 subfield → 4,516 topic；topic ID 形如 `T11636`。
- 构建：先按引文网络对有引用关系的 work 聚类，再由 LLM 生成名称与描述，最后按 Scopus ASJC 映射到 subfield/field/domain；与 CWTS（莱顿大学）合作开发。
- 分配：深度学习分类器读取标题、摘要、引文与期刊名，给每篇 work 打分，最高者为 `primary_topic`，`topics` 数组最多 3 个；无标题、摘要、引文者无法分类——2026 年中约 12%（39.6M/322M）无 topic。
- 旧的 concepts 已弃用（高召回低精确）。
- `/text/topics` 可对任意文本（20–2000 字符）打 topic，$0.01/次、1 rps。（核验补充）example-costs 页已把该端点标为 deprecated，见 §3.5.2。
- 分类器精度数字（如"top-1 0.72"）仅见于二手摘要，⚠ 未在一手文档核验。

**跨分类体系对齐**：Science Data Lake（arXiv 2603.03126，2026-03）用 BGE-large 句向量把 4,516 个 OpenAlex topic 映射到 13 个科学本体（约 130 万术语），得到 16,150 条映射，覆盖 99.8% 的 topic（阈值 ≥0.65），推荐工作点（≥0.85）F1 = 0.77 [SDL26]。说明 arXiv 分类、JEL、MeSH 等源原生分类挂到 OpenAlex 树上是可行的，但需要人工校验。

**v2 用法（设计）**：

1. **路由索引**：每个树节点存 `route_stat(node, source) = (coverage, lag_days, λ_new)`，查询得到 `P(t|q)` 后自底向上汇总（§3.5）。
2. **层级平滑**：topic 级样本少时向父节点回退：`θ_topic = (n·θ̂_topic + α·θ_parent)/(n + α)` [判断：经典收缩估计，非引自特定文献]。
3. **兴趣树**：用户画像表示为树上的分布，同样做层级平滑，冷启动时由少量显式选择（field/subfield）初始化——具体推荐算法交推荐文档。
4. **过滤标签**：work 的 subfield / topic 编号同时作为 ANN 标签（pgvectorscale）与 facet（位图）。

### 6.3 过滤结构：倒排、位图、前缀、三元组

| 结构 | 代表实现 | 适用 | 事实 |
|---|---|---|---|
| B-tree / GIN（数组、jsonb） | PG 原生 | 年份、venue、类型、`topic_ids int[]` | — |
| 三元组（trigram） | `pg_trgm` | 标题模糊匹配、实体链接、LIKE/ILIKE/正则加速 | 提供 GiST/GIN 索引，支持相似度算子与 LIKE、ILIKE、`~`、`~*`、`=` [pg_trgm] |
| Roaring 位图 | CRoaring（Apache/MIT）、pg_roaringbitmap（Apache-2.0）、PyRoaringBitMap（MIT）[Roaring-impl] | facet 交并差、"已看过"集合、订阅命中集合 | 按 2¹⁶ 分块，块内按密度选择数组 / 位图容器 [Roaring16]，后续加入游程容器 [Roaring16b][Roaring18] |
| 前缀 / FST | Tantivy、Lucene；Qdrant keyword 索引可选前缀匹配 [Tantivy][Qdrant-indexing] | 自动补全（venue/作者/topic 名） | — |
| 选择率感知规划 | Qdrant（按 payload 索引估计过滤基数，小于阈值改全扫）[Qdrant-indexing]；pgvector iterative scan [pgvector] | "过滤 + 向量"组合查询 | 过滤选择率 10%、ef_search=40 时，pgvector 平均只剩约 4 行结果（README 示例），需开启 iterative scan |

**v2 组合查询执行（设计）**：先用位图或 GIN 求过滤候选集并估计基数 `|C|` → 若 `|C|` ≤ 约 2 万，直接对候选做精确距离计算（1024 维 halfvec 约读 40 MB，毫秒到十毫秒级 [估算]）→ 否则走 HNSW + iterative scan（或 pgvectorscale 标签过滤）。阈值取法与 Qdrant 的 `full_scan_threshold` 思路一致，需实测校准。

### 6.4 v2 推荐

1. `corpus.citation(citing, cited, source, confidence)`，主键 `(citing, cited)`，并在 `cited` 上建索引；共被引、文献耦合等在线查询限 top-k。
2. 在线图查询只做 ≤2 跳，递归 CTE 必带 `CYCLE` 与 `LIMIT`；更深的遍历走离线批处理。
3. 离线：夜间导出 CSR → rustworkx/igraph 计算 PageRank、社区、共被引向量，结果回写为 work 特征。
4. 若多跳模式查询成为主要需求，先评估 Apache AGE（同库），再考虑独立图库。
5. 引文边来源：OpenAlex `referenced_works`（快照内）、Crossref 公开参考文献、S2 references API（1 RPS）；三者覆盖不同，需按来源记录与去重（⚠ 覆盖差异未量化）。

---

## 7. 去重与实体消解（⑤）

### 7.1 三层结构

| 层 | 技术 | 出处 | v2 做法 |
|---|---|---|---|
| L0 强标识 | identifier 图 + union-find（路径压缩 + 按秩合并，均摊近常数时间）[UnionFind75] | v1：`identifier(scheme,value)` 全局唯一；`same_as` 连通分量 [v1-design06] | 物化 `work.cluster_id`（并查集的根）；合并与拆分记入可回滚的合并日志（沿用 v1"物理不删行"） |
| L1 候选召回（blocking） | MinHash [MinHash97] + LSH [LSH98]（datasketch：MinHash LSH、LSH Forest、LSH Ensemble、LSHBloom，可接 Redis/Cassandra [datasketch]）；SimHash [SimHash02]（Google 用于网页爬虫近重复检测，WWW'07 [NearDup07]）；pg_trgm | 学术 | 标题 shingle MinHash（Jaccard ≥0.8）+ 年份 ±1 + v1 的观测级弱键 `(title_norm, 首作者姓)` [v1-D031] |
| L2 概率打分 | Fellegi–Sunter [FS69]；Splink（MIT；笔记本上约 1 分钟链接百万记录；DuckDB 默认后端，Spark 可到 1 亿+，可选 PG 后端）[Splink]；dedupe（MIT，最后推送 2025-07）；Zingg（AGPL-3.0）[dedupe-libs] | 学术 + 开源 | 特征：标题相似度、作者姓集合 Jaccard、年份差、venue 相容性、DOI 前缀关系、摘要向量余弦 |
| L3 裁决 | 规则 + 人工复核 | v1 D-007 | 精确重复（同 DOI 大小写/前缀差异）自动；**WP↔刊发版仍不自动合并**，走 `preprint_of` / 候审 |

**preprint_of 线索（v2 增补）**：arXiv `journal_ref`/`doi`（v1 已有）；bioRxiv `pubs` 端点给出预印本→正式发表映射 [bioRxiv-API]；Crossref 关系字段与 OpenAlex 版本信息（⚠ 字段名未核验，v1 已记录"产出侧未实现"）[v1-design06]。

### 7.2 "已见集合"选型

| 结构 | 误判 | 删除 | 空间（每元素） | 适用 |
|---|---|---|---|---|
| Roaring 位图 [Roaring16] | 无（精确） | 支持 | 稀疏时约 2 B/元素（数组容器）[估算] | **用户已看/已划/已存集合**（按内部整数 work_id） |
| Bloom filter [Bloom70] | 仅假阳性 | 不支持 | 误判率 p=1% 时约 9.6 bit（标准推导 `−ln p / (ln 2)²`）[估算] | 超大集合的廉价预检（如跨系统"是否见过该 URL"） |
| Cuckoo filter [Cuckoo14] | 仅假阳性 | 支持 | 与 Bloom 同量级 | 需要删除的近似集合 |
| Xor filter [Xor20] | 仅假阳性 | 不支持（静态） | 比 Bloom 更省（论文结论） | 只读快照集合 |
| HyperLogLog（datasketch 提供）[datasketch] | 基数估计 | — | 固定小内存 | 统计去重计数（如某论文被多少不同用户看过） |

**规模估算** [估算]：每用户每天 200 次卡片曝光 × 365 天 ≈ 7.3 万个 id/年；用 Roaring 精确存储约 150 KB/用户/年；1 万用户约 1.5 GB——可放 PG（pg_roaringbitmap）或 Valkey。精确集合没有误判，适合用来保证"卡片流不重复"。

### 7.3 v2 推荐流水线

1. 入库即做 L0：规范化 identifier（DOI 小写去前缀、arXiv 去版本号等）→ 查 `work_identifier` → union-find 合并 → 写 `cluster_id`。
2. 异步 L1/L2：新 work 生成 MinHash 签名并入 LSH 桶 → 产生候选对 → Splink 打分 → 超高分精确重复自动合并；其余进候审队列（沿用 v1 `dedupe review`）。
3. 查询期：结果按 `cluster_id` 折叠；来源、版本、OA 链接合并展示（v1 聚合视图语义）。
4. 可观测：每日报告候选对数量、自动合并数量、人工驳回率（误合并信号）。

---

## 8. 抓取调度与新鲜度（⑥）

### 8.1 理论基础

| 工作 | 出处 | 要点 | 对 v2 的意义 |
|---|---|---|---|
| Cho & Garcia-Molina | SIGMOD 2000 [Cho00]；TODS 2003 [Cho03-TODS]；TOIT 2003 [Cho03-TOIT] | 以 Poisson 过程建模变化；定义 freshness 与 age；平均新鲜度上**均匀刷新优于按变化率比例刷新**（模拟与真实爬取均成立）；最优策略既非均匀也非比例，应对变化过快的元素降权 [WP-crawler] | 预算有限时不要把轮询都砸给最活跃的源 |
| 变化率估计 | TOIT 2003 [Cho03-TOIT] | 只观测到"两次访问间是否变化"时，朴素估计有偏，需修正估计量（⚠ 常引公式 `r̂ = −ln((n − X + 0.5)/(n + 0.5))` 为转述，未对照原文全文） | 对"是否有新论文"的二值观测适用 |
| 期望新鲜度 | 同上框架 | 固定间隔 I、Poisson 率 λ 下期望新鲜度 `(1 − e^{−λI})/(λI)`（标准结果，⚠ 未对照原文全文） | 调度目标函数 |
| politeness 约束下最优 | Kolobov 等，SIGIR 2019 [Kolobov19] | PoliteBinaryLambdaCrawl：首个同时考虑主机级 politeness、非均匀重要性与爬虫自身请求上限的最优新鲜度调度；在 14 周、每日 1850 万 URL 的数据上评估 | 与"每源 token bucket + 全局预算"同构 |
| 近线性最优 | Azar 等，PNAS 2018 [Azar18] | 最优随机策略可在 O(n log n) 内精确求解；由此生成的确定性调度在实验中达到最优值的 99% | 数万个 watch key 也能每日重算 |
| OAI-PMH 增量 | 协议 2.0 [OAI-PMH] | `from/until` 必须支持日粒度（秒粒度可选）；删除记录三级支持（no/persistent/transient）；resumptionToken 流控 | 日粒度 + 重叠窗口是正确性底线 |

### 8.2 学术源的特殊性

1. **多数源是"新条目流"，不是"页面变化"**：关心的是新论文到达率 λ（篇/天），而非某页面是否变化。
2. **日历型 vs 连续型**：arXiv 按公告日批量发布、期刊按期发布（日历型，按日历在发布窗口后轮询即可）；Crossref 期刊 DOI 注册、SSRN 等更接近连续到达（Poisson 型）[判断]。
3. **增量机制不同**：Crossref `from-index-date`（v1 已记为官方推荐增量）[v1-metadata-apis]；arXiv OAI-PMH 日粒度 [v1-arxiv]；bioRxiv 日期区间游标 [bioRxiv-API]；OpenAlex 免费档无 created/updated 增量过滤，只能按 `publication_date` 窗口或季度快照 [OA-snapshot]。
4. **多用户共享**：100 个用户订阅 cs.LG，不应轮询 100 次——应把订阅编译为去重的 watch key。

### 8.3 v2 调度设计（设计伪代码）

```python
# 设计伪代码 —— 非接口冻结
# watch key = (source_endpoint, normalized_pushdown_query)；订阅编译后对其引用计数
class WatchKey:
    refcount: int            # 引用它的订阅数
    weight: float            # Σ 活跃订阅者权重（近期有互动的用户权重高）
    lam: Gamma               # 新条目到达率 λ 的共轭后验（Gamma–Poisson）
    calendar: Calendar|None  # 日历型源的发布窗口先验
    watermark: Cursor        # v1 DateCursor / IdSetDiff / OAI from
    cost_per_poll: float     # 请求数（含翻页）

def plan_day(keys_by_source, budget_by_source):
    for source, keys in keys_by_source.items():
        cal = [k for k in keys if k.calendar]            # 日历型：发布窗口后各轮询一次（+ 兜底重试）
        poi = [k for k in keys if not k.calendar]        # 连续型：拉格朗日注水分配轮询频率 f_k
        f = water_fill(poi, objective=lambda k, f: k.weight * freshness(k.lam.mean, f),
                       constraint=sum(k.cost_per_poll * f_k) <= budget_by_source[source] - cost(cal))
        schedule(cal, f)

def on_poll_result(k, n_new, dt):
    k.lam.update(n_new, dt)   # Gamma(α+n_new, β+dt)
    ingest(n_new)             # 入库 → 去重 → percolate 匹配全部订阅 → 写用户 feed 收件箱
```

- **正确性与效率分离**：v1 的重叠窗口 + id 去重保证"不漏不重"；调度器只决定"何时拉"。
- **反向检索（percolate）**：新 work 批量入库后，用"订阅条件倒排"（按订阅中出现的 topic/词项/venue 建索引）只评估可能命中的订阅，产出每用户的 feed 候选；OpenSearch 的 percolate 查询即"查找匹配某文档的已存查询"，常用于告警与通知 [OS-percolate]。T1 可在 PG 内用倒排表实现 [判断]。
- **快照 + API 双轨**：全量回填用 OpenAlex 免费季度快照（按 `updated_date` 分区增量 upsert，删除日志清理）[OA-snapshot]；季度之间的新鲜度依赖各一级源的增量接口，而非 OpenAlex 付费日更。

---

## 9. 稳定性工程（⑦）

### 9.1 模式对比

| 模式 | 机制与参数（来源） | v1 状态 | v2 建议 |
|---|---|---|---|
| 令牌桶限速 | per-domain，多方声明取最保守值 | 已有 [v1-code] | 保留；OpenAlex 另加"按信用/美元计费"的预算桶（读 `x-ratelimit-*` 头实时核销）[OA-auth] |
| 自适应并发 | Netflix concurrency-limits：借 TCP 拥塞控制思想，服务端推荐 Vegas（排队估计 `L × (1 − minRTT/sampleRTT)`），客户端推荐 AIMD 或损失 + 延迟组合 [Netflix-CL]；Envoy 梯度控制器：`gradient = (minRTT + B)/sampleRTT`，`B = minRTT × buffer_pct`，`limit_new = gradient × limit_old + headroom` [Envoy-AC] | 无 | 每源客户端 AIMD：窗口内无 429/5xx/超时且延迟未膨胀则 +1，出错则 ×0.5；**上限 = 源方书面并发**（arXiv 1、Crossref polite 3），只降不超 |
| 重试 + 抖动 | 指数退避 + Full / Equal / Decorrelated Jitter（2015-03-04）[AWS-jitter] | 固定 2/8/30 s，3 次 | Full Jitter，基数 1 s、封顶 60 s；Retry-After 优先 |
| 重试预算 | SRE：每请求最多 3 次尝试；每客户端重试占比 <10% 才允许重试 [SRE-overload]；Envoy：重试并发 ≤ 活跃请求的 20%（默认），下限 3 [Envoy-retry]；gRPC：`maxTokens`（0–1000，示例 10）、`tokenRatio`（示例 0.1），token 低于 `maxTokens/2` 时停止重试与对冲 [gRPC-A6] | 无 | 每源滑动 2 分钟窗口：重试占比 ≤10%；超出则只报错不重试 |
| 客户端自适应节流 | SRE：每客户端记录近 2 分钟的 `requests` 与 `accepts`，`requests` 超过 `K × accepts`（文中举例 K=2，调小更激进）后按概率在本地拒绝（拒绝概率公式在原文以图片呈现，此处只转述机制）[SRE-overload] | 无 | 对持续 429 的源在本地丢弃低优先级请求 |
| 对冲请求 | 首请求超过该类请求 p95 延迟后再发备份请求，额外负载约 5%；Google BigTable 示例：100 台服务器上读 1000 个键，10 ms 后发对冲，99.9 分位从 1,800 ms 降到 74 ms，只多发 2% 请求 [TailAtScale13] | 无 | **不对同一第三方主机对冲**（等于变相加压，违背礼貌原则）；只在"同能力不同源"间对冲（如 DOI 元数据：Crossref 超 p95 后问 OpenAlex 单实体，后者免费），额外请求 ≤5% 并计入预算 |
| 熔断器 | Closed/Open/Half-open（Fowler，2014-03-06）[Fowler-CB] | challenge 域冷却 24 h；浏览器通道连续 3 败当日熔断 [v1-code] | 按"源 × 端点"熔断：连续 5 次失败或 60 s 内 20 次请求错误率 >50% 打开；半开探测间隔 30 s 起指数增长至 30 min [判断] |
| 舱壁 | Netflix 百分比策略：为不同流量类型保证并发份额（如实时 90%、批量 10%）[Netflix-CL] | 单一 FIFO [v1-D039] | 每源分三道：交互检索 / 收割 / enrich；交互道保留每源预算 ≥50% [判断] |
| 截止时间与部分结果 | 请求带截止时间，逐层传递 [判断] | 无 | 交互检索首屏全局 2.5 s；远端结果超时后以"补充结果"流式追加 |
| 缓存 | 三家主 API 不给 ETag [LIVE-headers] | ETag 仅设计声明 | 应用层结果缓存：键 = 源 + 规范化子查询，TTL 与 λ̂ 挂钩（如 `min(24h, 0.1/λ̂)`）[判断]；实体缓存长 TTL + 后台刷新；404 负缓存短 TTL；hishel（BSD-3，RFC 9111 语义的 httpx 缓存）可用于确实支持缓存头的源 [py-resilience] |

### 9.2 Python 生态可复用库（2026-09-26）

| 库 | 用途 | 许可 | 最近推送 | 备注 |
|---|---|---|---|---|
| tenacity | 通用重试 | Apache-2.0 | 2026-09-01 | 成熟 |
| stamina | 带合理默认（退避 + 抖动）的重试 | MIT | 2026-09-07 | 上层封装 |
| aiolimiter | asyncio 漏桶 | MIT | 2026-09-25 | 轻量 |
| PyrateLimiter | 多后端限速（含分布式） | MIT | 2026-09-23 | 多进程共享限速可用 |
| pybreaker | 熔断器 | BSD-3 | 2026-09-25 | — |
| hishel | httpx 的 HTTP 缓存 | BSD-3 | 2026-09-18 | — |
| httpx | v1 现用 HTTP 客户端 | BSD-3 | **2026-03-29** | 近 6 个月无推送，需关注维护状态 [判断] |

出处：[py-resilience][GH-snapshot]。

### 9.3 v2 每源初始参数（需压测与线上校准）

| 源 | 速率上限（书面） | 并发上限 | v2 起步值 [判断] | 来源 |
|---|---|---|---|---|
| arXiv legacy API | 1 请求/3 秒 | 1 | 1/3 s，并发 1（全部机器合计） | [arXiv-ToU] |
| Crossref（polite） | 10 req/s | 3 | 5 req/s，并发 2 | [Crossref-limits] |
| OpenAlex | ≤100 req/s + 日预算 | — | 10 req/s；按日预算核销；search 类优先走本地 | [OA-auth][OA-cost] |
| OpenAlex 语义检索 / `/text` | 1 req/s | — | 1 req/s，仅交互道 | [OA-semantic][OA-text] |
| Semantic Scholar | key 1 RPS | — | 1 RPS | [S2-api] |
| DBLP | robots.txt 全站 `Disallow: /`（2026-09-26；核验修正，原写 `Crawl-delay: 4`） | — | 在线站点零自动化请求；不在生产链（D-037） | [dblp-robots][v1-D037] |
| bioRxiv | ⚠ 未见书面值 | — | 1 req/s 保守 | [bioRxiv-API] |
| PubMed E-utilities（核验补充） | 无 key 3 req/s；带 key 10 req/s | ⚠ | 带 key 时 ≤3 req/s 起步 [判断] | [NLM-eutils][NCBI-apikey17] |

---

## 10. 多用户数据平台（⑧）

### 10.1 多租户模式对比

| 模式 | 说明 | 优点 | 缺点 | 出处 |
|---|---|---|---|---|
| Silo（每租户独立库） | 物理隔离 | 合规对齐、无跨租户影响、可按租户调优、租户级可用性 | 敏捷性受损、成本高、部署复杂、无集中管理 | [AWS-MT] |
| Bridge（每租户独立 schema） | 共享实例、分 schema | 部分合规对齐、敏捷、成本优、集中管理（核验修正：按 AWS 原表补全） | 部分合规挑战、（多数情况下）全有或全无的可用性、跨租户影响、部署复杂；租户多时迁移与目录膨胀 [判断，非 AWS 原文] | [AWS-MT] |
| Pool（共享表 + `tenant_id` + RLS） | 共享一切 | 敏捷、成本优、集中管理、部署简单 | 跨租户影响、合规挑战、可用性"全有或全无" | [AWS-MT] |
| Citus 行分片 / schema 分片 | 按 `tenant_id` 行哈希分片（适合大表）；Citus 12（2023-07-18）新增按 schema 透明分片 | 横向扩展 | AGPL-3.0；运维复杂 | [Citus12] |

**本项目的"租户"是个人用户**，数量可到万级，且大部分数据（论文语料）天然共享——典型的 **Pool + 共享语料层** 场景。

### 10.2 分层数据模型（设计伪代码 DDL）

```sql
-- 设计伪代码 —— 非 schema 冻结；类型与约束在详设中确定
-- ① 共享语料层 corpus：无 RLS；应用角色只读，写入只经 ingest 服务角色
CREATE TABLE corpus.work (
  work_id          bigint PRIMARY KEY,        -- 内部整数 id：利于位图 / ANN / 分区
  public_id        uuid UNIQUE,               -- 对外 id；PG18 提供 uuidv7()（2025-09-25 发布）
  cluster_id       bigint NOT NULL,           -- union-find 根
  title text, abstract text, pub_date date, year smallint,
  primary_venue_id bigint, primary_subfield smallint, topic_ids int[],
  is_oa boolean, oa_license text, lang text, meta jsonb, updated_at timestamptz
);
CREATE TABLE corpus.work_identifier (scheme text, value text, work_id bigint, PRIMARY KEY (scheme, value));
CREATE TABLE corpus.source_record (source text, source_key text, work_id bigint,
                                   payload jsonb, fetched_at timestamptz, PRIMARY KEY (source, source_key));
CREATE TABLE corpus.citation (citing bigint, cited bigint, source text, PRIMARY KEY (citing, cited));
CREATE TABLE corpus.work_embedding (work_id bigint PRIMARY KEY, model text, emb halfvec(1024));
CREATE TABLE corpus.topic (topic_id int PRIMARY KEY, level smallint, parent_id int, name text,
                           centroid halfvec(1024));
CREATE TABLE corpus.route_stat (node_id int, source text, coverage real, lag_days real,
                                lambda_per_day real, updated_at timestamptz, PRIMARY KEY (node_id, source));
CREATE TABLE corpus.oa_asset (asset_id bigint PRIMARY KEY, work_id bigint, license text, storage_key text);
                                -- 只收许可允许再分发的 OA 全文

-- ② 用户私有层 usr：所有表带 user_id，启用 RLS
CREATE TABLE usr.subscription   (sub_id bigint PRIMARY KEY, user_id uuid NOT NULL, ast jsonb, ...);
CREATE TABLE usr.library_item   (user_id uuid, work_id bigint, state text, tags text[], note text,
                                 PRIMARY KEY (user_id, work_id));
CREATE TABLE usr.private_asset  (asset_id bigint PRIMARY KEY, user_id uuid NOT NULL, work_id bigint,
                                 storage_key text, sha256 bytea, entitlement text, fetched_at timestamptz);
                                -- 付费墙全文：按用户命名空间存储，不跨用户去重、不共享
CREATE TABLE usr.credential     (user_id uuid, provider text, sealed bytea, PRIMARY KEY (user_id, provider));
CREATE TABLE usr.seen           (user_id uuid PRIMARY KEY, seen roaringbitmap);   -- pg_roaringbitmap
CREATE TABLE usr.review         (review_id bigint PRIMARY KEY, user_id uuid, work_id bigint,
                                 rating smallint, body text, visibility text);    -- public / private
CREATE TABLE usr.event          (event_id uuid, user_id uuid, work_id bigint, type text, value real,
                                 ctx jsonb, client_ts timestamptz, server_ts timestamptz)
                                 PARTITION BY RANGE (server_ts);

ALTER TABLE usr.library_item ENABLE ROW LEVEL SECURITY;
CREATE POLICY own_rows ON usr.library_item
  USING (user_id = (SELECT current_setting('app.user_id')::uuid));
-- review：可读 = 自己的全部 + 他人 visibility='public'；可写 = 仅自己

-- ③ 运维层 ops：watch_key（引用计数）、harvest_run、source_health、fetch_log、任务队列表
```

### 10.3 RLS 要点

1. 启用 RLS 而没有策略时为**默认拒绝**；超级用户与带 `BYPASSRLS` 的角色总是绕过；表 owner 默认绕过，除非 `FORCE ROW LEVEL SECURITY` [PG-RLS]。→ 应用连接必须用非 owner、无 `BYPASSRLS` 的角色。
2. 策略涉及的列必须建索引（B-tree 首列）；策略中的函数用 `(SELECT fn())` 包裹，让优化器生成 initPlan、每条语句只算一次 [Supabase-RLS]。
3. 以 `SET LOCAL app.user_id = …` 在事务内设置用户上下文，与事务级连接池配合（⚠ 连接池模式需在实现期验证）[判断]。（核验补充）PgBouncer 功能矩阵（1.26.0 于 2026-09-23 发布，2026-09-26 查阅）显示，事务池模式下会话级 `SET/RESET`、`LISTEN`、SQL 级 `PREPARE/DEALLOCATE`、会话级 advisory lock 均为 “Never”。`SET LOCAL` 与 `set_config(…, true)` 是事务级设置，文档未单列，⚠ 仍需实测 [PgBouncer-features]。
4. RLS 测试用 pgTAP 类工具覆盖"越权读 / 越权写 / 公开评论可见性"三类用例 [Supabase-RLS]。

### 10.4 交互事件日志

| 方案 | 事实 | 适用 | 判断 |
|---|---|---|---|
| PG 原生声明式分区（按月/周） | 分区裁剪；以 `DROP`/`DETACH PARTITION` 代替批量删除，免去 VACUUM 开销 [PG-partition]；pg_partman 自动维护分区 | ≤约 10⁹ 行/年 | **T1 首选** |
| TimescaleDB | 源码分两类许可：`tsl` 目录外 Apache-2.0，`tsl` 内为 Timescale License [Timescale-lic]；公司于 2025-06-17 更名 TigerData，扩展名不变 [TigerData-rename] | 时序聚合 | 许可需评估；非必需 |
| ClickHouse | Apache-2.0 [ClickHouse] | ≥10⁹–10¹⁰ 行分析 | T2 引入，经 outbox/CDC 从 PG 同步 |
| DuckDB / Parquet 离线 | Science Data Lake：DuckDB + Parquet 在单盘承载约 960 GB、约 2.93 亿篇论文的多源整合 [SDL26] | 离线分析、特征回填 | 分析沙箱可选 |

**事件语义（设计）**：`event_id` 由客户端生成（幂等去重）；同时记录 `client_ts` 与 `server_ts`；事件只追加、不更新；用户画像等聚合物化到独立表并可由事件重放重建（事件溯源式）[判断]。
**量级估算** [估算]：1 万日活 × 每日 200 张卡片 × 约 3 个事件（曝光、滑动、停留）≈ 600 万行/日 ≈ 22 亿行/年——超过 T1 单表舒适区，需在 T1 后期引入 ClickHouse 或缩短热数据保留期。

### 10.5 特征存储

- Feast（Apache-2.0，2026-09-26 仍活跃）[Feast] 解决"离线/在线特征一致性 + 时间点正确的训练集"。
- **v2 早期不引入** [判断]：模型少（一个召回、一个重排）、特征源集中在 PG；以"PG 物化表 + Valkey 在线缓存"替代（Valkey 为 BSD-3；Redis 8 起为 RSALv2 / SSPLv1 / AGPLv3 三选一许可）[Redis-lic]。
- **引入条件**：出现 ≥3 个线上模型共享特征，或需要严格的时间点训练集回放时再评估。

### 10.6 任务队列与持久化工作流

| 项目 | 后端 | 特性 | 许可 | 活跃度（2026-09-26） | 适配判断 |
|---|---|---|---|---|---|
| **procrastinate** | PG 13+ | 同步/异步、Django 集成、周期任务、重试、任务锁 | MIT | 1,395★，2026-09-26 推送 | **T1 首选**：与 v1 单进程模型最接近 |
| **pgqueuer** | PG | Python 后台任务队列；`FOR UPDATE SKIP LOCKED` 领取任务（不重复处理）+ `LISTEN/NOTIFY` 即时唤醒（带轮询兜底） | MIT | 1,526★，2026-09-17 | 首选备选 |
| chancy | PG | Python 任务队列 | MIT | 288★，2026-09-23 | 较新 |
| pgmq | PG 扩展 | 类 SQS 的轻量消息队列 | PostgreSQL | 5,298★，2026-09-24（仓库已迁至 `pgmq/pgmq`） | 适合做 outbox / 事件总线 |
| absurd | 仅 PG | 持久执行（durable execution）工作流，2025-11-03 发布公告 | Apache-2.0 | 2,443★，2026-08-10 | 长流程（深度检索、批量回填）候选 |
| DBOS Transact（Python） | PG | 数据库支撑的持久 Python 工作流 | MIT | 1,591★，2026-09-25 | 同上 |
| Hatchet | PG（持久层）+ 服务 | 任务、智能体、持久工作流；自称压测到 1 万任务/秒，资源开销高于 Redis/RabbitMQ 方案 | MIT | 8,009★，2026-09-25 | T2 候选 |
| Temporal | 独立集群 | 成熟持久工作流 | MIT | 23,303★ | 运维重，T2 以上 |
| Celery | Redis / RabbitMQ | 生态最大 | BSD-3 | 28,916★ | 不需要额外 broker 时不选 |
| Dramatiq | Redis / RabbitMQ | 简洁可靠 | LGPL-3.0 | 5,312★ | 同上 |
| arq | Redis | asyncio | MIT | 3,014★，2026-04-16；**README 声明仅维护模式** | **不选** |

出处：[queues][absurd][Hatchet][arq][GH-snapshot]。

**连接池约束（核验补充）**：pgqueuer 用 `LISTEN/NOTIFY` 即时唤醒 worker；procrastinate 默认也用 `LISTEN`（`listen_notify=True`，可关闭，退回轮询）。PgBouncer 事务池模式不支持 `LISTEN`，因此 worker 的监听连接必须直连 PG 或走会话池；Web/API 侧可继续用事务池 [PgBouncer-features][queues]。

### 10.7 SQLite → PostgreSQL 迁移路径

- **现状**：v1 本地库 179 篇 paper / 228 个 identifier / 3 个 asset / 23 个 task [v1-db-count]；schema 0001–0004、0006 方言中性，0005 为唯一 SQLite 专有迁移（FTS5 + 触发器）[v1-D034]。
- **路径（建议）**：
  1. **不做原地升级**：v2 以新 schema（§10.2）起步；v1 数据走一次性 Python ETL：读 SQLite（只读）→ 转换（ULID 文本保留为 `legacy_id`，另发 bigint `work_id`；JSON 文本 → jsonb；ISO 文本 → timestamptz；identifier 重新规范化）→ `COPY` 写入。
  2. **派生结构重建**：BM25/tsvector 索引、向量、`cluster_id`、route_stat 均在 PG 侧重新计算，不搬运。
  3. **校验**：逐表行数、identifier 唯一性、随机抽样字段比对、FTS 对照查询（D-034 已列出三项不可移植面：查询语法、排序函数、词干化实现）[v1-D034]。
  4. **切换**：v2 服务端只支持 PG；v1 CLI 改为调用 v2 API 的客户端，或保留为"离线个人版"（SQLite + Litestream 备份，Apache-2.0）[Litestream]。
- **工具取舍**：pgloader 支持 SQLite→PG 全量迁移，但 v4 是 Clojure/JVM 重写（需 Java 21+，v4-dev 预发布 2026-06-20；v3 最后稳定版 v3.6.9 为 2022-10-24）[pgloader]——数据量极小，**自写 ETL 更可控** [判断]。
- **PG 版本**：选 PG 18（2025-09-25 发布：异步 I/O、`uuidv7()`、B-tree skip scan、虚拟生成列、OAuth 2.0 认证）[PG18]；pg_textsearch 只支持 PG 17/18 [pg_textsearch]；PG 19 仍在 Beta（2026-09-24 发布 Beta 4）[PG18]。

---

## 11. 参考架构草案与规模分级

```text
                    ┌──────────────── 交互道（低延迟） ────────────────┐
 用户/前端 ──► API ──► 查询理解（规则快速路径 → LLM 结构化 AST → 实体链接）
                    │        │
                    │        ▼
                    │   路由器（Topic 树 × 源覆盖矩阵 × 能力 × 成本；熔断感知）
                    │     ├─► 本地检索：PG{BM25 扩展 + pgvector/pgvectorscale + 位图/GIN facets}
                    │     └─► 远端联邦：连接器（令牌桶 + AIMD + 重试预算 + 截止时间 + 同能力替补/对冲）
                    │        ▼
                    │   合并：cluster_id 折叠 → RRF → cross-encoder 重排 →（个性化挂点）→ 流式返回
                    └──────────────────────────────────────────────────┘
 后台道：watch key 调度（日历 + λ 注水）→ 收割 → 入库（L0 union-find）→ LSH/Splink 候审
        → 向量化 worker → 索引更新 → percolate 订阅匹配 → 用户 feed 收件箱
 数据层：corpus（共享，只读）/ usr（RLS，私有资产与凭证）/ ops（队列、健康）/ 事件分区表 →（T2）ClickHouse
```

| 档位 | 用户 | 语料 | 事件 | 推荐栈 | 升级触发条件 |
|---|---|---|---|---|---|
| T0 个人 / 开发 | 1 | ≤100 万 | — | PG 18（容器）+ pgvector + pg_textsearch；或沿用 v1 SQLite 离线版 | — |
| T1 小平台 | ≤1,000 | ≤1000 万 | ≤10⁷/日 | 单主 PG（64–128 GB 内存、NVMe）+ pgvector `halfvec`（或 pgvectorscale）+ BM25 扩展 + procrastinate + 分区事件表 + Valkey（可选） | HNSW 不能常驻内存；检索 p95 >300 ms；事件 >10⁹ 行/年 |
| T2 中平台 | ≤10 万 | 1000 万–1 亿 | 10⁷–10⁹/日 | PG 主从 + 专用检索集群（Qdrant / Vespa / OpenSearch 择一，CDC 同步）+ ClickHouse + Hatchet/Temporal（按需） | 单集群写入瓶颈；多地域 |
| T3 | >10 万 | ≥1 亿（全量 OpenAlex 镜像） | — | 主题分片 + selective search + DiskANN 类索引 | 超出本轮范围 |

以上阈值均为 [判断]，需在 §12 第 21–24 条的评测与压测中校准。

---

## 12. 对 v2 设计的启示（编号列出，可直接指导设计）

1. **确立"先收割、后联邦"**：订阅、最新、卡片流只读本地语料；即席查询先查本地，覆盖不足才联邦（§3.5.2）。
2. **引入 Source Capability Descriptor（SCD）**：在 adapter 能力位之外，声明查询能力（布尔/短语/字段/语义/过滤维度/增量方式/分页上限）、成本模型（$/credit、翻页）、礼貌参数；路由器与健全放宽都以 SCD 为唯一输入（§3.4、§3.5.3）。
3. **Topic 树作为一等实体入库**（OpenAlex 4/26/252/4,516），每节点挂 `route_stat`；周期性用 `group_by` 或免费快照重算，成本约 $1/次全量 [估算]（§3.5.1、§6.2）。
4. **路由采用"覆盖 × 能力 × 成本"的预算贪心**，并保留 Thompson sampling 探索；日志积累后升级为 GBDT 成对排序路由器（§3.5.4）。
5. **QPP 只作弱信号**，不作为是否联邦的主判据（§3.2）。
6. **健全放宽 + 本地残差**写成可测试的规则表；本地残差分析器须与目标源对齐（词干化、大小写），并统计"远端命中、本地拒绝"比例（§3.5.3）。
7. **同能力替补链**为每个关键能力（DOI 元数据、OA 定位、最新 arXiv、标题匹配、语义探索）至少配置两级（§3.5.5）。
8. **定义查询 AST**（§4.3.1），自然语言解析走"规则快速路径 → LLM 结构化输出（受约束解码）→ 实体链接 → 用户可编辑筛选条"，并以投机执行保证首屏延迟。
9. **本地混合检索 = BM25 + 稠密 + RRF + cross-encoder**；学习稀疏只在确认许可后引入（官方 SPLADE 为非商业许可）（§4.1、§4.5）。
10. **嵌入模型以自有评测选型**：候选 Qwen3-Embedding（Apache-2.0）、BGE-M3（MIT）、SPECTER2（Apache-2.0）；存 `halfvec`；模型版本写入 `work_embedding.model` 以支持双写迁移（§4.5、§5.4）。
11. **T1 向量索引用 pgvector HNSW + iterative scan**；内存吃紧时切 pgvectorscale（diskann + SBQ + subfield/topic 标签过滤）（§5.4）。
12. **BM25 扩展二选一需先做许可决策**：pg_textsearch（PostgreSQL 许可，正式支持 PG17/18；分区表的 IDF 按分区局部计算）vs ParadeDB（AGPL-3.0）（§5.2）。
13. **组合查询执行采用选择率感知计划**：位图/GIN 求候选 → 小候选集精确扫描、大候选集走 ANN + iterative scan（§6.3）。
14. **不引入独立图数据库**：PG 邻接表 + ≤2 跳在线查询 + 夜间 CSR 批处理；多跳 Cypher 需求出现时先评估 Apache AGE（§6.4）。
15. **物化 `cluster_id`**（union-find）并以可回滚合并日志维护；弱信号走 MinHash-LSH + Splink，继续遵守 D-007（§7）。
16. **用户已见集合用 Roaring 精确位图**（pg_roaringbitmap），Bloom 类只用于跨系统廉价预检（§7.2）。
17. **订阅编译为共享 watch key**（引用计数）；新论文入库后 percolate 匹配全部订阅，写用户 feed 收件箱（§8.3）。
18. **调度区分日历型与连续型源**：前者按发布窗口，后者按 λ 后验做 politeness 约束下的注水分配；正确性仍由重叠窗口 + id 去重保证（§8）。
19. **稳定性四件套补齐**：每源 AIMD（上限=书面限额）、重试预算（≤3 次 + ≤10%）、按"源 × 端点"熔断、交互/收割/enrich 三道舱壁；**禁止对同一第三方主机对冲**（§9）。
20. **不依赖 HTTP 条件缓存**（主 API 无 ETag）：做应用层 TTL 缓存，TTL 与 λ̂ 挂钩；OpenAlex 用信用预算桶实时核销（§9.1）。
21. **建立检索评测基线**：LitSearch（ML/NLP）+ SciRepEval 检索类任务 + 各学科自建 gold set（理科/社科/CS 各 ≥200 条）；指标 recall@k、nDCG@10、源独有贡献率。
22. **建立路由评测**：以"全源穷举"为参照，评估路由器在给定预算下的召回保持率与成本节省。
23. **建立稳定性演练**：故障注入（429 风暴、延迟尖峰、5xx、挑战页）验证熔断、预算与降级；复用 v1 的 fixture 回放体系。
24. **建立容量压测**：在目标硬件上用自有语料复测向量/全文索引的 recall@k、p50/p95/p99、构建时间、常驻内存（§5.3 方法论提醒）。
25. **数据分层 + RLS**：`corpus` 只读共享、`usr` 全部 RLS、应用角色无 `BYPASSRLS` 且非表 owner；策略列建索引、函数 `(SELECT …)` 包裹（§10.3）。
26. **付费墙全文按用户私有存储、不跨用户去重**；OA 全文按许可分流（§2.3、§10.2）。
27. **事件日志 append-only + 月分区 + 客户端幂等 id**；T1 后期或 >10⁹ 行/年时引入 ClickHouse（§10.4）。
28. **任务队列选 PG 原生**（procrastinate / pgqueuer），长流程评估 absurd / DBOS；不选 arq。两者依赖 `LISTEN/NOTIFY`，worker 连接须直连 PG 或走 PgBouncer 会话池（§10.6，核验补充）。
29. **迁移走新 schema + 自写 ETL**，选 PG 18；v1 CLI 转为 API 客户端或离线版（§10.7）。
30. **依赖治理**：对风投支持的开源组件（pgvectorscale/TigerData、Qdrant、LanceDB、ParadeDB 等）一律经内部接口抽象，保留可替换性（Kùzu 归档先例）。
31. **（核验补充）源合规参数要带核验日期并定期复检**。先例：dblp 的 robots.txt 在 2026-07 到 2026-09 之间从 `Crawl-delay: 4` 改为全站 `Disallow: /`；OpenAlex 在同一年内先后改动计费、`corpus` 参数，并给 `/text` 打上弃用标记。因此 SCD 中的 politeness、计费与端点状态字段应记录“核验日期”，并由定时任务复检 robots.txt 与 deprecations 页；一旦出现变化，自动熔断相关端点并提醒人工复核（§2.2、§13 第 16、17 条）。

---

## 13. 未决问题与风险

| # | 问题 / 风险 | 影响 | 建议处置 |
|---|---|---|---|
| 1 | OpenAlex 计费与免费档仍可能变化（2026-02 已从免费 polite pool 改为计费制 [v1-metadata-apis]；deprecations 页已确认 polite pool 由 API key 取代 [OA-deprecations]） | 路由成本模型与覆盖统计来源 | 覆盖统计优先用免费快照离线计算；成本参数配置化 |
| 2 | PubMed E-utilities 限速已由 NLM 支持文档补齐（无 key 3 req/s，带 key 10 req/s），但其检索语法与能力细项仍 ⚠；Europe PMC 限速与能力 ⚠ 未核验（文档页 403 / JS 渲染） | 生物医学与心理学路由 | 由来源调研或人工浏览补齐后再定参数 |
| 3 | Cho & Garcia-Molina 估计量与新鲜度公式 ⚠ 未对照原文全文 | 调度目标函数正确性 | 实现前取得原文核对（机构访问） |
| 4 | OpenAlex topic 覆盖约 88%，分类器精度未在一手来源核验 | 路由与兴趣树偏差 | 自有分类器补标无 topic 的 work；抽样人工评估 |
| 5 | 厂商基准互相矛盾（TigerData vs Qdrant） | 选型误判 | 以自有压测为准（启示 24） |
| 6 | 许可：SPLADE 官方权重非商业；ParadeDB、VectorChord（含 VectorChord-bm25）、Citus 为 AGPL；Elasticsearch RRF 属 Enterprise 付费级（订阅页已核验）；Meilisearch 部分 BUSL；Weaviate `wl/` 目录为专有许可 | 商业化与 SaaS 合规 | 先确定 v2 是否商业化，再定组件 |
| 7 | 单节点 PG 同时承担事务、BM25、向量、事件，资源争用 | 延迟抖动 | 读副本 + 事件写入异步批量 + 分阶段外移 |
| 8 | RLS 性能与连接池交互（`SET LOCAL` 语义）未实测；PgBouncer 事务池不支持会话级 `SET` 与 `LISTEN`（已核验） | 越权、性能退化，或队列 worker 收不到通知 | 实现期 pgTAP + 压测验证；队列监听连接直连或走会话池 |
| 9 | OA 全文共享的法律边界（许可不明的 bronze OA） | 合规 | 默认只共享明确开放许可的全文；⚠ 需法务意见 |
| 10 | LLM 查询理解的延迟、成本与幻觉（生成不存在的 venue/作者） | 准确率与体验 | 实体链接只接受库内 ID；可编辑筛选条；投机执行 |
| 11 | percolate 匹配在订阅数达 10⁵ 级时的性能 | feed 时效 | T1 用 PG 倒排表；T2 评估 OpenSearch percolate |
| 12 | 事件日志与画像涉及个人数据（中国 PIPL、欧盟 GDPR 等）⚠ 未做法律调研 | 合规 | 最小化采集、保留期、删除权流程纳入设计 |
| 13 | 依赖健康：httpx 近 6 个月无推送；arq 维护模式；Kùzu 归档 | 维护风险 | 关注上游；关键依赖经接口抽象 |
| 14 | 分析器不一致导致远端命中被本地残差误杀 | 召回损失 | 启示 6 的对齐与监控 |
| 15 | 引文边多源覆盖差异未量化（OpenAlex / Crossref / S2） | 图特征偏差 | 小样本三源对比后定来源优先级 |
| 16 | （核验补充）dblp.org 的 robots.txt 已改为全站 `Disallow: /`（2026-09-26），v1 保留的 dblp adapter（conf 索引页 + 卷 XML）若重新接入即违反 robots | 合规 | 维持 D-037 出列；任何 dblp 数据只经 DROPS 快照获取，并在来源名录中更新该事实 |
| 17 | （核验补充）OpenAlex 文档把 `/text` 标为 deprecated，但各页口径不一；OpenAlex 近一年接连改动计费、`corpus` 参数与 polite pool | 路由冷启动与成本模型漂移 | `/text` 只作可替换兜底；OpenAlex 参数配置化，每季度对照 deprecations 页复核 |

---

## 14. 参考来源（访问日期：除另注外均为 2026-09-26）

### 14.1 联邦检索、源选择、QPP、Mediator

- [CORI95] Callan, Lu, Croft. Searching distributed collections with inference networks. SIGIR 1995. https://doi.org/10.1145/215206.215328 （Crossref 核验）
- [ReDDE03] Si, Callan. Relevant document distribution estimation method for resource selection. SIGIR 2003. https://doi.org/10.1145/860435.860490
- [FS-FnTIR11] Shokouhi, Si. Federated Search. FnTIR 5(1), 2011. https://doi.org/10.1561/1500000010
- [Arguello09] Arguello, Callan, Diaz. Classification-based resource selection. CIKM 2009. https://doi.org/10.1145/1645953.1646115
- [SelSearch15] Kulkarni, Callan. Selective Search. ACM TOIS, 2015. https://doi.org/10.1145/2738035
- [LTRR17] Dai, Kim, Callan. Learning To Rank Resources. SIGIR 2017. https://doi.org/10.1145/3077136.3080657
- [LTRR-GNN23] Ergashev, Dragut, Meng. Learning To Rank Resources with GNN. WWW 2023. https://doi.org/10.1145/3543507.3583360
- [ReSLLM] Wang, Zhuang, Koopman, Zuccon. ReSLLM. arXiv:2401.17645；WWW 2025 Companion https://doi.org/10.1145/3701716.3715595
- [FeB4RAG24] Wang, Khramtsova, Zhuang, Zuccon. FeB4RAG. SIGIR 2024. https://doi.org/10.1145/3626772.3657853 ；arXiv:2402.11891
- [LTRR-Ret25] Kim, Diaz. LTRR: Learning To Rank Retrievers for LLMs. arXiv:2506.13743（v2 2026-04-18）https://arxiv.org/abs/2506.13743
- [FS-Survey23] Garba, Wu, Khalid. Federated search techniques: an overview of the trends and state of the art. KAIS 2023. https://doi.org/10.1007/s10115-023-01922-6
- [Clarity02] Cronen-Townsend, Zhou, Croft. Predicting query performance. SIGIR 2002. https://doi.org/10.1145/564376.564429
- [NQC12] Shtok, Kurland, Carmel, Raiber, Markovits. Predicting Query Performance by Query-Drift Estimation. TOIS 30(2), 2012. https://doi.org/10.1145/2180868.2180873
- [QPP-Limits] Chifu, Déjean, Garouani, Mothe, Ortiz, Ullah. Uncovering the Limitations of Query Performance Prediction: Failures, Insights, and Implications for Selective Query Processing. ACM TOIS 44(6), 2026（Crossref：印本 2026-07-31、在线 2026-08-11）. https://doi.org/10.1145/3774427 （摘要经 S2 API 取回；书目经 Crossref 核验，2026-09-26）
- [Mediator92] Wiederhold. Mediators in the architecture of future information systems. IEEE Computer, 1992. https://doi.org/10.1109/2.121508
- [InfoManifold96] Levy, Rajaraman, Ordille. Querying Heterogeneous Information Sources Using Source Descriptions. VLDB 1996. https://www.vldb.org/conf/1996/P251.PDF
- [TSIMMIS98] Li, Yerneni, Vassalos, Garcia-Molina, Papakonstantinou, Ullman, Valiveti. Capability based mediation in TSIMMIS. SIGMOD 1998. https://doi.org/10.1145/276304.276382 ；https://sigmodrecord.org/1998/06/06/capability-based-mediation-in-tsimmis/ （摘要经 S2 API 取回，2026-09-26；ACM PDF 403 未绕过）
- [Submod78] Nemhauser, Wolsey, Fisher. An analysis of approximations for maximizing submodular set functions—I. Math. Programming, 1978. https://doi.org/10.1007/BF01588971
- [BudgetMC99] Khuller, Moss, Naor. The budgeted maximum coverage problem. IPL, 1999. https://doi.org/10.1016/S0020-0190(99)00031-9
- [TS-Tutorial18] Russo, Van Roy, Kazerouni, Osband, Wen. A Tutorial on Thompson Sampling. FnT ML, 2018. https://doi.org/10.1561/2200000070

### 14.2 混合检索与查询理解

- [BM25-09] Robertson, Zaragoza. The Probabilistic Relevance Framework: BM25 and Beyond. FnTIR, 2009. https://doi.org/10.1561/1500000019
- [RRF09] Cormack, Clarke, Buettcher. Reciprocal rank fusion outperforms Condorcet and individual rank learning methods. SIGIR 2009. https://doi.org/10.1145/1571941.1572114 ；全文（k=60 核验）https://cormack.uwaterloo.ca/cormacksigir09-rrf.pdf
- [SPLADE21] Formal, Piwowarski, Clinchant. SPLADE. SIGIR 2021. https://doi.org/10.1145/3404835.3463098
- [SPLADEv2] Formal, Lassance, Piwowarski, Clinchant. SPLADE v2. arXiv:2109.10086. https://arxiv.org/abs/2109.10086
- [SPLADE-lic] naver/splade LICENSE（CC BY-NC-SA 4.0）. https://github.com/naver/splade
- [DPR20] Karpukhin 等. Dense Passage Retrieval for Open-Domain QA. EMNLP 2020. https://doi.org/10.18653/v1/2020.emnlp-main.550
- [ColBERT20] Khattab, Zaharia. ColBERT. SIGIR 2020. https://doi.org/10.1145/3397271.3401075
- [ColBERTv2] Santhanam 等. ColBERTv2. arXiv:2112.01488. https://arxiv.org/abs/2112.01488
- [SPECTER20] Cohan 等. SPECTER. ACL 2020. https://doi.org/10.18653/v1/2020.acl-main.207
- [SciRepEval23] Singh, D'Arcy, Cohan, Downey, Feldman. SciRepEval. EMNLP 2023. https://aclanthology.org/2023.emnlp-main.338/ ；arXiv:2211.13308
- [BEIR21] Thakur 等. BEIR. arXiv:2104.08663. https://arxiv.org/abs/2104.08663
- [LitSearch24] Ajith, Xia, Chevalier, Goyal, Chen, Gao. LitSearch. EMNLP 2024. https://aclanthology.org/2024.emnlp-main.840/ ；https://github.com/princeton-nlp/LitSearch
- [PaSa25] He 等. PaSa: An LLM Agent for Comprehensive Academic Paper Search. arXiv:2501.10120（v2 2025-05-27）https://arxiv.org/abs/2501.10120 ；https://github.com/bytedance/pasa
- [RankGPT23] Sun 等. Is ChatGPT Good at Search? EMNLP 2023. https://doi.org/10.18653/v1/2023.emnlp-main.923
- [Qwen3Emb25] Zhang 等. Qwen3 Embedding. arXiv:2506.05176. https://arxiv.org/abs/2506.05176
- [BGE-M3] M3-Embedding. arXiv:2402.03216. https://arxiv.org/abs/2402.03216
- [HF-lic] Hugging Face 模型 API（许可标签）：https://huggingface.co/api/models/naver/splade-v3 ；…/naver/splade-cocondenser-ensembledistil ；…/prithivida/Splade_PP_en_v1 ；…/opensearch-project/opensearch-neural-sparse-encoding-doc-v3-distill ；…/thenlper/gte-large ；…/BAAI/bge-m3 ；…/Qwen/Qwen3-Embedding-0.6B ；…/allenai/specter2_base ；…/google/embeddinggemma-300m
- [s2search] allenai/s2search README（Semantic Scholar 搜索重排器）. https://github.com/allenai/s2search
- [OA-semantic] OpenAlex: Semantic Search. https://help.openalex.org/api/semantic-search
- [OA-search] OpenAlex: Searching. https://help.openalex.org/api/searching
- [Qdrant-hybrid] Qdrant: Hybrid Queries. https://qdrant.tech/documentation/concepts/hybrid-queries/
- [Typesense-hybrid] Typesense v30.0 Vector Search. https://typesense.org/docs/30.0/api/vector-search.html
- [Meili-hybrid] Meilisearch: Hybrid search getting started（原 URL `…/learn/ai_powered_search/getting_started_with_ai_search` 已重定向至此，2026-09-26）. https://www.meilisearch.com/docs/capabilities/hybrid_search/getting_started
- [OS-RRF] OpenSearch: Introducing reciprocal rank fusion for hybrid search. https://opensearch.org/blog/introducing-reciprocal-rank-fusion-hybrid-search/ ；https://docs.opensearch.org/latest/vector-search/ai-search/hybrid-search/rrf/
- [ES-RRF] Elasticsearch RRF retriever. https://www.elastic.co/docs/reference/elasticsearch/rest-apis/retrievers/rrf-retriever
- [ES-RRF-lic] u11d. Reciprocal Rank Fusion on free Elasticsearch（2026-06-03）. https://u11d.com/blog/reciprocal-rank-fusion-on-free-elasticsearch-licensing-workarounds-and-the-open-search-alternative/
- [ES-subs] Elastic Subscriptions 功能矩阵（RRF 行仅 Enterprise 打勾；核验补充，2026-09-26）. https://www.elastic.co/subscriptions
- [ConstrainedDec] https://github.com/dottxt-ai/outlines ；https://github.com/mlc-ai/xgrammar ；https://github.com/guidance-ai/llguidance

### 14.3 ANN 与检索引擎

- [HNSW20] Malkov, Yashunin. HNSW. IEEE TPAMI 42(4), 2020. https://doi.org/10.1109/TPAMI.2018.2889473 ；arXiv:1603.09320
- [PQ11] Jégou, Douze, Schmid. Product Quantization for Nearest Neighbor Search. IEEE TPAMI, 2011. https://doi.org/10.1109/TPAMI.2010.57
- [DiskANN19] Subramanya 等. DiskANN. NeurIPS 2019. https://www.microsoft.com/en-us/research/publication/diskann-fast-accurate-billion-point-nearest-neighbor-search-on-a-single-node/
- [FilteredDiskANN23] Gollapudi 等. Filtered-DiskANN. WWW 2023. https://doi.org/10.1145/3543507.3583552
- [FreshDiskANN21] Singh 等. FreshDiskANN. arXiv:2105.09613. https://arxiv.org/abs/2105.09613
- [ScaNN20] Guo 等. Accelerating Large-Scale Inference with Anisotropic Vector Quantization. ICML 2020. https://proceedings.mlr.press/v119/guo20h.html
- [Faiss24] Douze 等. The Faiss library. arXiv:2401.08281（v4 2025-10-23）. https://arxiv.org/abs/2401.08281
- [ANNB20] Aumüller, Bernhardsson, Faithfull. ANN-Benchmarks. Information Systems, 2020. https://doi.org/10.1016/j.is.2019.02.006 ；https://ann-benchmarks.com/
- [BigANN23] Simhadri 等. Results of the Big ANN: NeurIPS'23 competition. arXiv:2409.17424. https://arxiv.org/abs/2409.17424
- [FANNS-Survey25] Lin 等. Survey of Filtered ANN Search over the Vector-Scalar Hybrid Data. arXiv:2505.06501. https://arxiv.org/abs/2505.06501
- [Curator26] Jin 等. Curator: Efficient Vector Search with Low-Selectivity Filters. arXiv:2601.01291. https://arxiv.org/abs/2601.01291
- [pgvector] pgvector README 与 CHANGELOG（0.8.0 于 2024-10-30 加入 iterative index scan；0.8.6 于 2026-07-29）. https://github.com/pgvector/pgvector
- [pgvectorscale] pgvectorscale README（0.9.1，2026-09-04）. https://github.com/timescale/pgvectorscale
- [Tiger-QdrantBench25] TigerData. Pgvector vs. Qdrant（2025-04-29）. https://www.tigerdata.com/blog/pgvector-vs-qdrant
- [Qdrant-bench] Qdrant Vector Search Benchmarks. https://qdrant.tech/benchmarks/
- [Qdrant-capacity] Qdrant Capacity Planning. https://qdrant.tech/documentation/capacity-planning/
- [Qdrant-indexing] Qdrant Indexing. https://qdrant.tech/documentation/concepts/indexing/
- [Milvus25] Introducing Milvus 2.5. https://milvus.io/blog/introduce-milvus-2-5-full-text-search-powerful-metadata-filtering-and-more.md
- [Milvus3] Milvus v3.0.0 发布说明（2026-07-29）. https://github.com/milvus-io/milvus/releases/tag/v3.0.0
- [ES-BBQ24] Elastic Search Labs. Better Binary Quantization（2024-11-11）. https://www.elastic.co/search-labs/blog/better-binary-quantization-lucene-elasticsearch
- [ES-AGPL24] Elastic. Elasticsearch Is Open Source. Again!（2024-08-29）. https://www.elastic.co/blog/elasticsearch-is-open-source-again
- [OS-disk] OpenSearch: Disk-based vector search. https://docs.opensearch.org/latest/vector-search/optimizing-storage/disk-based-vector-search/
- [Vespa-phases] Vespa: Phased ranking. https://docs.vespa.ai/en/phased-ranking.html
- [pg_textsearch] timescale/pg_textsearch README 与 releases（v1.4.0，2026-08-18）. https://github.com/timescale/pg_textsearch
- [ParadeDB] paradedb/paradedb README；`pg_search/Cargo.toml` 依赖 tantivy. https://github.com/paradedb/paradedb
- [VectorChord] tensorchord/VectorChord LICENSE（AGPLv3 / ELv2）. https://github.com/tensorchord/VectorChord
- [Tantivy] quickwit-oss/tantivy README. https://github.com/quickwit-oss/tantivy
- [Meili-lic] meilisearch LICENSE（MIT AND BUSL-1.1）. https://github.com/meilisearch/meilisearch/blob/main/LICENSE
- [LanceDB] lancedb/lancedb README. https://github.com/lancedb/lancedb
- [ES-lic] elastic/elasticsearch LICENSE.txt（默认三选一；`x-pack` 仅 ELv2；核验补充，2026-09-26）. https://github.com/elastic/elasticsearch/blob/main/LICENSE.txt
- [Weaviate-hybrid] Weaviate: Hybrid search（relativeScoreFusion 自 v1.24 为默认；核验补充，2026-09-26）. https://docs.weaviate.io/weaviate/search/hybrid
- [Weaviate-MT] Weaviate: Multi-tenancy operations（每租户独立 shard；核验补充，2026-09-26）. https://docs.weaviate.io/weaviate/manage-collections/multi-tenancy
- [Weaviate-lic] weaviate/weaviate LICENSE（BSD-3-Clause + `wl/` 目录 Weaviate License；v1.39.7 于 2026-09-25 发布；核验补充，2026-09-26）. https://github.com/weaviate/weaviate/blob/main/LICENSE
- [GH-snapshot] GitHub REST API 仓库元数据快照（附表 A 所列仓库）. https://api.github.com/repos/{owner}/{repo}

### 14.4 图、树与过滤结构

- [PG-WITH] PostgreSQL 18 文档：WITH Queries（SEARCH / CYCLE）. https://www.postgresql.org/docs/current/queries-with.html ；对照 https://www.postgresql.org/docs/14/queries-with.html （含 SEARCH/CYCLE）与 https://www.postgresql.org/docs/13/queries-with.html （不含），确认自 PG14 起支持
- [AGE] apache/age（分支与 release 标签）. https://github.com/apache/age
- [Neo4j] neo4j/neo4j. https://github.com/neo4j/neo4j
- [Kuzu] kuzudb/kuzu（archived）README. https://github.com/kuzudb/kuzu
- [Kuzu-forks] https://github.com/LadybugDB/ladybug ；https://github.com/Kineviz/bighorn ；https://github.com/predictable-labs/ryugraph
- [DuckPGQ] cwida/duckpgq-extension. https://github.com/cwida/duckpgq-extension
- [GraphDB-Survey25] Coimbra 等. Survey: On the Landscape of Graph Databases. arXiv:2505.24758. https://arxiv.org/abs/2505.24758
- [OA-topics] OpenAlex: Topics. https://help.openalex.org/data/topics
- [OA-text] OpenAlex: Tag Aboutness. https://help.openalex.org/api/tag-aboutness
- [OA-groupby] OpenAlex: Group. https://help.openalex.org/api/grouping
- [SDL26] Wilinski. The Science Data Lake. arXiv:2603.03126（2026-03-03）. https://arxiv.org/abs/2603.03126
- [Roaring16] Chambi, Lemire, Kaser, Godin. Better bitmap performance with Roaring bitmaps. SPE, 2016（在线 2015-04-21）. https://doi.org/10.1002/spe.2325
- [Roaring16b] Lemire, Ssi-Yan-Kai, Kaser. Consistently faster and smaller compressed bitmaps with Roaring. SPE, 2016. https://doi.org/10.1002/spe.2402
- [Roaring18] Lemire 等. Roaring bitmaps: Implementation of an optimized software library. SPE, 2018. https://doi.org/10.1002/spe.2560
- [Roaring-impl] https://github.com/RoaringBitmap/CRoaring ；https://github.com/ChenHuajun/pg_roaringbitmap ；https://github.com/Ezibenroc/PyRoaringBitMap
- [pg_trgm] PostgreSQL 文档：pg_trgm. https://www.postgresql.org/docs/current/pgtrgm.html

### 14.5 去重与实体消解

- [UnionFind75] Tarjan. Efficiency of a Good But Not Linear Set Union Algorithm. JACM, 1975. https://doi.org/10.1145/321879.321884
- [MinHash97] Broder. On the resemblance and containment of documents. SEQUENCES 1997. https://doi.org/10.1109/SEQUEN.1997.666900
- [LSH98] Indyk, Motwani. Approximate nearest neighbors. STOC 1998. https://doi.org/10.1145/276698.276876
- [SimHash02] Charikar. Similarity estimation techniques from rounding algorithms. STOC 2002. https://doi.org/10.1145/509907.509965
- [NearDup07] Manku, Jain, Das Sarma. Detecting near-duplicates for web crawling. WWW 2007. https://doi.org/10.1145/1242572.1242592
- [FS69] Fellegi, Sunter. A Theory for Record Linkage. JASA, 1969. https://doi.org/10.1080/01621459.1969.10501049
- [Splink] moj-analytical-services/splink README. https://github.com/moj-analytical-services/splink
- [datasketch] ekzhu/datasketch README. https://github.com/ekzhu/datasketch
- [dedupe-libs] https://github.com/dedupeio/dedupe ；https://github.com/zinggAI/zingg ；https://github.com/allenai/S2AND
- [Bloom70] Bloom. Space/time trade-offs in hash coding with allowable errors. CACM, 1970. https://doi.org/10.1145/362686.362692
- [Cuckoo14] Fan, Andersen, Kaminsky, Mitzenmacher. Cuckoo Filter. CoNEXT 2014. https://doi.org/10.1145/2674005.2674994
- [Xor20] Graf, Lemire. Xor Filters. ACM JEA, 2020. https://doi.org/10.1145/3376122

### 14.6 抓取调度与新鲜度

- [Cho00] Cho, Garcia-Molina. Synchronizing a database to improve freshness. SIGMOD 2000. https://doi.org/10.1145/342009.335391 （仅核验书目）
- [Cho03-TODS] Cho, Garcia-Molina. Effective page refresh policies for Web crawlers. ACM TODS, 2003. https://doi.org/10.1145/958942.958945 （仅核验书目）
- [Cho03-TOIT] Cho, Garcia-Molina. Estimating frequency of change. ACM TOIT, 2003. https://doi.org/10.1145/857166.857170 （仅核验书目）
- [WP-crawler] Wikipedia: Web crawler（Re-visit policy 一节，二手综述）. https://en.wikipedia.org/wiki/Web_crawler
- [Kolobov19] Kolobov, Peres, Lubetzky, Horvitz. Optimal Freshness Crawl Under Politeness Constraints. SIGIR 2019. https://doi.org/10.1145/3331184.3331241 （摘要经 S2 API 取回）
- [Azar18] Azar, Horvitz, Lubetzky, Peres, Shahaf. Tractable near-optimal policies for crawling. PNAS, 2018. https://doi.org/10.1073/pnas.1801519115 （摘要经 S2 API 取回）
- [OAI-PMH] The Open Archives Initiative Protocol for Metadata Harvesting v2.0. https://www.openarchives.org/OAI/openarchivesprotocol.html
- [OA-snapshot] OpenAlex: Snapshot；Sync. https://help.openalex.org/access/snapshot ；https://help.openalex.org/access/sync
- [bioRxiv-API] bioRxiv API. https://api.biorxiv.org/
- [OS-percolate] OpenSearch: Percolate query. https://docs.opensearch.org/latest/query-dsl/specialized/percolate/

### 14.7 稳定性工程

- [TailAtScale13] Dean, Barroso. The Tail at Scale. CACM 56(2), 2013. https://doi.org/10.1145/2408776.2408794 ；PDF https://www.barroso.org/publications/TheTailAtScale.pdf
- [SRE-overload] Google SRE Book: Handling Overload. https://sre.google/sre-book/handling-overload/
- [Envoy-retry] Envoy: config.cluster.v3.CircuitBreakers（RetryBudget）. https://www.envoyproxy.io/docs/envoy/latest/api-v3/config/cluster/v3/circuit_breaker.proto
- [Envoy-AC] Envoy: Adaptive Concurrency filter. https://www.envoyproxy.io/docs/envoy/latest/configuration/http/http_filters/adaptive_concurrency_filter
- [gRPC-A6] gRPC proposal A6: Client Retries. https://github.com/grpc/proposal/blob/master/A6-client-retries.md
- [Netflix-CL] Netflix/concurrency-limits README. https://github.com/Netflix/concurrency-limits
- [AWS-jitter] Brooker. Exponential Backoff And Jitter（2015-03-04）. https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/
- [Fowler-CB] Fowler. CircuitBreaker（2014-03-06）. https://martinfowler.com/bliki/CircuitBreaker.html
- [py-resilience] https://github.com/jd/tenacity ；https://github.com/hynek/stamina ；https://github.com/mjpieters/aiolimiter ；https://github.com/vutran1710/PyrateLimiter ；https://github.com/danielfm/pybreaker ；https://github.com/karpetrosyan/hishel ；https://github.com/encode/httpx
- [LIVE-headers] 本次线上探针（2026-09-26，各 1 次 GET，匿名、非识别性 UA）：https://api.crossref.org/works/10.1145/1571941.1572114 ；https://api.openalex.org/works/doi:10.1145/1571941.1572114 ；https://api.semanticscholar.org/graph/v1/paper/DOI:10.1145/1571941.1572114?fields=title

### 14.8 多用户数据平台

- [PG-RLS] PostgreSQL 文档：Row Security Policies. https://www.postgresql.org/docs/current/ddl-rowsecurity.html
- [Supabase-RLS] Supabase: Row Level Security. https://supabase.com/docs/guides/database/postgres/row-level-security
- [AWS-MT] AWS Prescriptive Guidance: Partitioning models for multi-tenant PostgreSQL. https://docs.aws.amazon.com/prescriptive-guidance/latest/saas-multitenant-managed-postgresql/partitioning-models.html
- [Citus12] Slot. Citus 12: Schema-based sharding for PostgreSQL（2023-07-18）. https://www.citusdata.com/blog/2023/07/18/citus-12-schema-based-sharding-for-postgres/
- [PG-partition] PostgreSQL 文档：Table Partitioning. https://www.postgresql.org/docs/current/ddl-partitioning.html
- [Timescale-lic] timescale/timescaledb LICENSE. https://github.com/timescale/timescaledb/blob/main/LICENSE
- [TigerData-rename] Timescale Becomes Tiger Data（2025-06-17）. https://www.tigerdata.com/newsroom/timescale-becomes-tiger-data-defining-a-new-standard-as-the-fastest-postgresql-platform-for-modern-applications
- [ClickHouse] https://github.com/ClickHouse/ClickHouse
- [Feast] https://github.com/feast-dev/feast
- [queues] https://github.com/procrastinate-org/procrastinate ；https://github.com/janbjorge/pgqueuer ；https://github.com/TkTech/chancy ；https://github.com/pgmq/pgmq ；https://github.com/dbos-inc/dbos-transact-py ；https://github.com/temporalio/temporal ；https://github.com/celery/celery ；https://github.com/Bogdanp/dramatiq
- [absurd] earendil-works/absurd README（公告 https://lucumr.pocoo.org/2025/11/3/absurd-workflows/）. https://github.com/earendil-works/absurd
- [Hatchet] hatchet-dev/hatchet README. https://github.com/hatchet-dev/hatchet
- [arq] python-arq/arq README（"In maintenance only mode"）. https://github.com/python-arq/arq
- [pgloader] dimitri/pgloader README（v4 Clojure 重写）与 releases. https://github.com/dimitri/pgloader
- [Litestream] https://github.com/benbjohnson/litestream
- [PG18] PostgreSQL 18 Released!（2025-09-25）. https://www.postgresql.org/about/news/postgresql-18-released-3142/
- [Redis-lic] redis/redis LICENSE（Redis 8 起三选一许可）；https://github.com/valkey-io/valkey
- [PgBouncer-features] PgBouncer: Features（SQL feature map for pooling modes；PgBouncer 1.26.0 于 2026-09-23 发布；核验补充，2026-09-26）. https://www.pgbouncer.org/features.html

### 14.9 源能力事实

- [Crossref-limits] Crossref REST API: Access and authentication（Request limits 一节）. https://www.crossref.org/documentation/retrieve-metadata/rest-api/access-and-authentication/
- [OA-cost] OpenAlex: Example costs. https://help.openalex.org/access/example-costs
- [OA-pricing] OpenAlex: Pricing overview. https://help.openalex.org/access/pricing
- [OA-auth] OpenAlex: Authentication（rate limits、响应头）. https://help.openalex.org/api/authentication
- [OA-paging] OpenAlex: Page through Results. https://help.openalex.org/api/paging
- [OA-corpus] OpenAlex: Expansion corpus. https://help.openalex.org/data/works/corpus
- [S2-api] Semantic Scholar API 产品页. https://www.semanticscholar.org/product/api
- [S2-swagger] Semantic Scholar Graph API swagger. https://api.semanticscholar.org/graph/v1/swagger.json
- [arXiv-ToU] arXiv API Terms of Use. https://info.arxiv.org/help/api/tou.html
- [arXiv-robots] https://arxiv.org/robots.txt
- [NCBI-blocked] https://www.ncbi.nlm.nih.gov/books/NBK25497/ （2026-09-26 访问遇 reCAPTCHA，未绕过，内容未核验；核验时复访仍为 reCAPTCHA）
- [NLM-eutils] NLM Support Center KA-05317: What is an API Key and how can I get it?（E-utilities 3 rps / 带 key 10 rps；核验补充，2026-09-26）. https://support.nlm.nih.gov/kbArticle/?pn=KA-05317
- [NCBI-apikey17] NCBI Insights: New API Keys for the E-utilities（2017-11-02）. https://ncbiinsights.ncbi.nlm.nih.gov/2017/11/02/new-api-keys-for-the-e-utilities/ （核验补充，2026-09-26）
- [OA-deprecations] OpenAlex: Deprecations（2026-02 起 polite pool 由 API key 取代；`include_xpac` 弃用，改用 `corpus`；核验补充，2026-09-26）. https://help.openalex.org/api/deprecations
- [OA-unpaywall] OpenAlex: Unpaywall（Unpaywall 各入口与 Data Feed；核验补充，2026-09-26）. https://help.openalex.org/access/unpaywall
- [Crossref-swagger] Crossref REST API swagger-docs（field queries、rows ≤1000、offset ≤10,000、cursor 5 分钟过期；核验补充，2026-09-26）. https://api.crossref.org/swagger-docs
- [S2-rec-swagger] Semantic Scholar Recommendations API swagger（核验补充，2026-09-26）. https://api.semanticscholar.org/recommendations/v1/swagger.json
- [dblp-robots] https://dblp.org/robots.txt （另查 https://dblp.uni-trier.de/robots.txt 、https://dblp.dagstuhl.de/robots.txt ，内容相同；核验补充，2026-09-26）
- [DROPS-robots] https://drops.dagstuhl.de/robots.txt （核验补充，2026-09-26）

### 14.10 仓库内部文档（v1 基线）

- [v1-design05] docs/design/05-pipeline.md（updated 2026-07-29）
- [v1-design06] docs/design/06-data-model.md（updated 2026-07-29）
- [v1-design09] docs/design/09-search-filter.md（updated 2026-07-29）
- [v1-D007] [v1-D031] [v1-D034] [v1-D037] [v1-D039] docs/plan/decision-log.md 对应条目
- [v1-metadata-apis] docs/research/site-survey/metadata-apis.md（2026-07-20/22 实测）
- [v1-aggregators] docs/research/site-survey/aggregators-unpaywall-dblp-core.md（2026-07-20/22 实测）
- [v1-arxiv] docs/research/site-survey/arxiv.md（2026-07-20 核验）
- [v1-code] src/paper_crawler/ratelimit.py、http.py、browserfetch.py（2026-09-26 阅读；`grep -rli etag src` 0 命中）
- [v1-db-count] `.paper-crawler/catalog.sqlite` 只读计数（2026-09-26）

---

## 附表 A：GitHub 项目快照（2026-09-26，`gh api`）

| 仓库 | ★ | 许可 | 最近推送 | 最新版本（发布日期） | 备注 |
|---|---|---|---|---|---|
| pgvector/pgvector | 23,161 | PostgreSQL 类（API 显示 NOASSERTION） | 2026-09-26 | v0.8.6（2026-07-29） | — |
| timescale/pgvectorscale | 3,135 | PostgreSQL | 2026-09-07 | 0.9.1（2026-09-04） | TigerData 维护 |
| tensorchord/VectorChord | 1,802 | AGPLv3 / ELv2 | 2026-08-06 | 1.1.1（2026-02-28） | — |
| tensorchord/VectorChord-bm25 | 379 | AGPLv3 / ELv2（API 显示 NOASSERTION；LICENSE 文件核验修正） | 2026-08-05 | — | — |
| timescale/pg_textsearch | 4,001 | PostgreSQL | 2026-09-26 | v1.4.0（2026-08-18） | 仅 PG17/18 |
| paradedb/paradedb | 9,308 | AGPL-3.0 | 2026-09-26 | v0.25.10（2026-09-23） | 基于 Tantivy |
| qdrant/qdrant | 34,833 | Apache-2.0 | 2026-09-26 | v1.19.1（2026-09-04） | — |
| lancedb/lancedb | 11,535 | Apache-2.0 | 2026-09-26 | v0.40.0-beta.11（2026-09-24） | — |
| milvus-io/milvus | 46,255 | Apache-2.0 | 2026-09-26 | v3.0.2（2026-09-20）；v2.6.24（2026-09-16） | 3.0.0 于 2026-07-29 |
| vespa-engine/vespa | 7,110 | Apache-2.0 | 2026-09-26 | — | — |
| opensearch-project/OpenSearch | 13,776 | Apache-2.0 | 2026-09-25 | 3.8.0（2026-08-05） | — |
| elastic/elasticsearch | 77,998 | AGPLv3 / SSPL / ELv2 | 2026-09-26 | v9.5.4（2026-09-15） | — |
| quickwit-oss/tantivy | 16,144 | MIT | 2026-09-25 | 0.26.1（2026-05-10） | — |
| meilisearch/meilisearch | 59,413 | MIT + BUSL-1.1 | 2026-09-24 | v1.54.0（2026-09-21） | — |
| typesense/typesense | 26,597 | GPL-3.0 | 2026-09-24 | v30.2（2026-04-19） | — |
| weaviate/weaviate | 16,850 | BSD-3-Clause + Weaviate License（`wl/`；API 显示 NOASSERTION） | 2026-09-26 | v1.39.7（2026-09-25） | 核验补充 |
| facebookresearch/faiss | 40,985 | MIT | 2026-09-26 | — | — |
| microsoft/DiskANN | 1,936 | MIT | 2026-09-26 | — | — |
| nmslib/hnswlib | 5,334 | Apache-2.0 | 2026-09-15 | — | — |
| unum-cloud/usearch | 4,320 | Apache-2.0 | 2026-08-31 | — | — |
| erikbern/ann-benchmarks | 5,735 | MIT | 2026-07-10 | — | — |
| zilliztech/VectorDBBench | 1,183 | MIT | 2026-09-22 | — | Zilliz 维护（厂商） |
| harsha-simhadri/big-ann-benchmarks | 450 | MIT | 2026-07-13 | — | — |
| apache/age | 4,852 | Apache-2.0 | 2026-09-19 | PG18/v1.8.0-rc0（2026-07-09） | 分支 PG11–PG19 |
| neo4j/neo4j | 17,256 | GPL-3.0 | 2026-09-22 | 标签 2026.09.0 | — |
| kuzudb/kuzu | 4,025 | MIT | 2025-10-10 | — | **archived** |
| LadybugDB/ladybug | 1,787 | MIT | 2026-09-26 | — | Kùzu 分支 |
| Kineviz/bighorn | 134 | MIT | 2026-08-10 | — | Kùzu 分支 |
| predictable-labs/ryugraph | 146 | NOASSERTION | 2026-01-20 | — | Kùzu 分支 |
| duckdb/duckdb | 41,714 | MIT | 2026-09-25 | v1.5.5（2026-07-22） | — |
| cwida/duckpgq-extension | 499 | MIT | 2026-09-17 | — | — |
| igraph/python-igraph | 1,464 | GPL-2.0 | 2026-05-14 | — | — |
| networkx/networkx | 17,289 | BSD-3 | 2026-09-25 | — | — |
| Qiskit/rustworkx | 1,760 | Apache-2.0 | 2026-09-24 | — | — |
| ekzhu/datasketch | 2,969 | MIT | 2026-08-09 | — | — |
| moj-analytical-services/splink | 2,434 | MIT | 2026-09-25 | — | — |
| dedupeio/dedupe | 4,516 | MIT | 2025-07-29 | — | 活跃度下降 |
| zinggAI/zingg | 1,252 | AGPL-3.0 | 2026-09-13 | — | — |
| allenai/S2AND | 116 | NOASSERTION | 2026-09-05 | — | 作者消歧 |
| RoaringBitmap/CRoaring | 1,888 | Apache-2.0 / MIT | 2026-09-24 | — | — |
| ChenHuajun/pg_roaringbitmap | 289 | Apache-2.0 | 2026-09-18 | — | — |
| Ezibenroc/PyRoaringBitMap | 239 | MIT | 2026-05-06 | — | — |
| Netflix/concurrency-limits | 3,615 | Apache-2.0 | 2026-01-16 | — | Java |
| jd/tenacity | 8,797 | Apache-2.0 | 2026-09-01 | — | — |
| hynek/stamina | 1,457 | MIT | 2026-09-07 | — | — |
| mjpieters/aiolimiter | 781 | MIT | 2026-09-25 | — | — |
| vutran1710/PyrateLimiter | 525 | MIT | 2026-09-23 | — | — |
| danielfm/pybreaker | 693 | BSD-3 | 2026-09-25 | — | — |
| karpetrosyan/hishel | 412 | BSD-3 | 2026-09-18 | — | — |
| encode/httpx | 15,509 | BSD-3 | 2026-03-29 | — | v1 依赖 |
| procrastinate-org/procrastinate | 1,395 | MIT | 2026-09-26 | — | — |
| janbjorge/pgqueuer | 1,526 | MIT | 2026-09-17 | — | — |
| TkTech/chancy | 288 | MIT | 2026-09-23 | — | — |
| pgmq/pgmq | 5,298 | PostgreSQL | 2026-09-24 | — | 原 tembo-io/pgmq |
| earendil-works/absurd | 2,443 | Apache-2.0 | 2026-08-10 | — | — |
| dbos-inc/dbos-transact-py | 1,591 | MIT | 2026-09-25 | — | — |
| hatchet-dev/hatchet | 8,009 | MIT | 2026-09-25 | — | — |
| temporalio/temporal | 23,303 | MIT | 2026-09-26 | — | — |
| temporalio/sdk-python | 1,199 | MIT | 2026-09-22 | — | — |
| celery/celery | 28,916 | BSD-3 | 2026-09-26 | — | — |
| Bogdanp/dramatiq | 5,312 | LGPL-3.0 | 2026-09-14 | — | — |
| python-arq/arq | 3,014 | MIT | 2026-04-16 | — | **维护模式** |
| feast-dev/feast | 7,310 | Apache-2.0 | 2026-09-26 | — | — |
| timescale/timescaledb | 23,596 | Apache-2.0 + Timescale License | 2026-09-26 | — | — |
| ClickHouse/ClickHouse | 50,081 | Apache-2.0 | 2026-09-26 | — | — |
| pgpartman/pg_partman | 2,825 | PostgreSQL License（API 显示 NOASSERTION；LICENSE.txt 核验修正） | 2026-08-21 | — | 版权方现为 Snowflake（2025–2026） |
| citusdata/citus | 12,787 | AGPL-3.0 | 2026-09-25 | — | — |
| dimitri/pgloader | 6,539 | PostgreSQL 类 | 2026-09-14 | v4-dev（2026-06-20）；v3.6.9（2022-10-24） | v4 为 Clojure/JVM 重写 |
| benbjohnson/litestream | 14,398 | Apache-2.0 | 2026-09-25 | — | — |
| duckdb/pg_duckdb | 3,248 | MIT | 2026-07-17 | — | — |
| valkey-io/valkey | 27,297 | BSD-3 | 2026-09-26 | 9.1.2（2026-09-01，GitHub latest；同日另发 9.0.6；9.2.0-rc1 为 2026-09-16 预发布） | 核验修正：原写最新版 9.0.6 |
| redis/redis | 76,485 | RSALv2 / SSPLv1 / AGPLv3（8.0 起） | 2026-09-24 | 8.10.2（2026-09-17） | — |
| naver/splade | 1,015 | CC BY-NC-SA 4.0 | 2024-05-03 | — | 非商业 |
| stanford-futuredata/ColBERT | 3,944 | MIT | 2025-10-14 | — | — |
| FlagOpen/FlagEmbedding | 12,196 | MIT | 2026-08-24 | — | BGE 系列 |
| QwenLM/Qwen3-Embedding | 2,040 | （仓库未声明；HF 模型 Apache-2.0） | 2025-09-30 | — | — |
| allenai/SPECTER2 | 144 | Apache-2.0 | 2026-02-24 | — | — |
| castorini/rank_llm | 657 | Apache-2.0 | 2026-09-24 | — | LLM 重排 |
| huggingface/sentence-transformers | 19,123 | Apache-2.0 | 2026-09-24 | — | 核验修正：原 `UKPLab/sentence-transformers` 已迁至 huggingface 组织（旧路径重定向） |
| bytedance/pasa | 1,661 | Apache-2.0 | 2025-05-27 | — | — |
| princeton-nlp/LitSearch | 111 | MIT | 2024-12-02 | — | — |
| allenai/s2search | 113 | Apache-2.0 | 2020-10-26 | — | — |
| dottxt-ai/outlines | 15,885 | Apache-2.0 | 2026-09-21 | — | — |
| mlc-ai/xgrammar | 1,935 | Apache-2.0 | 2026-09-24 | — | — |
| guidance-ai/llguidance | 876 | MIT | 2026-09-25 | — | — |
| ourresearch/openalex-topic-classification | 59 | MIT | 2025-08-04 | — | OpenAlex topic 模型代码 |

---

## 核验记录

> **核验范围与方法**（对抗式核验，2026-09-26）：文中未发现此前留下的核验节或半截修改，本节为唯一核验记录。挑选承重断言，逐条对照一手来源复核：官方文档与 README 经 `gh api` / `curl` / WebFetch 取回；论文书目经 Crossref `/works/{doi}`（46 个 DOI，间隔 1.2 s）与 arXiv API `id_list`（2 次批量，间隔 ≥3 s）核对；书目核对之外另有 3 次 Crossref 单条查询（QPP、Roaring、budgeted MC）；S2 API 取回摘要与标题匹配共 5 次，间隔 2–3 s，另取 swagger 2 份；arXiv 取回 1 个 PDF（Big-ANN）。另发 [LIVE] 探针 7 次（OpenAlex 5 次：`group_by`、单实体、list、topics、subfields；Crossref 1 次；S2 1 次）。以上请求全部匿名，UA 为 `PaperCrawler-survey-verify/0.1 (design research; non-commercial)`，不含个人信息。**访问失败不绕过**：NCBI NBK25497 为 reCAPTCHA；Europe PMC 文档与 ACM PDF 返回 403；Cho & Garcia-Molina 作者自存 PDF 超时，Stanford 副本返回 500。结论取值：确认 / 修正 / 删除 / 未核验；新增内容在正文中标“核验补充”。本轮未发现编造的仓库、论文或产品，删除 0 项。

| 断言 | 结论 | 依据来源 URL | 核验日期 |
|---|---|---|---|
| V01 §2.2/§3.4 OpenAlex 按用量计费：单实体免费；list+filter $0.10/千；search 与 semantic $1/千；内容下载 $10/千；免费 key $1/日，无 key $0.10/日 | 确认 | https://help.openalex.org/access/example-costs ；https://help.openalex.org/access/pricing | 2026-09-26 |
| V02 §2.2 OpenAlex 限额：超预算或 >100 req/s 返回 429；`per_page` ≤100（200 为遗留行为）；基础分页 ≤10,000；单过滤 OR ≤100；请求 URL 约 4 KB（报错文案写 4094 字节），超长 OR 拆分后取并集结果不变 | 确认 | https://help.openalex.org/api/authentication ；https://help.openalex.org/api/paging ；https://help.openalex.org/api/searching | 2026-09-26 |
| V03 §3.5.1 `group_by` 按 list+filter 计价（原标“⚠ 未核验”） | 修正：升级为 [LIVE] 确认，每次 1 credit（$0.0001）；另确认单页 ≤200 组、翻页用 cursor | [LIVE] https://api.openalex.org/works?filter=topics.id:T11636&group_by=primary_location.source.id&per_page=200 ；https://help.openalex.org/api/grouping | 2026-09-26 |
| V04 §2.2 OpenAlex `search.semantic`：GTE-Large EN 1024 维；每次 ≤50 条；1 req/s；输入 ≤2000 字符（超出截断）；不支持国家与被引数过滤 | 确认 | https://help.openalex.org/api/semantic-search | 2026-09-26 |
| V05 §2.2 OpenAlex 语料：core 320M+；expansion 约 190M（2025-11 Walden 一次性批次）；默认只返回 core | 确认；补充 2026-08 新增的 `corpus` 参数 | https://help.openalex.org/data/works/corpus ；https://help.openalex.org/api/deprecations | 2026-09-26 |
| V06 §2.2 OpenAlex 快照：免费、按季度发布（第二个周三，下次 2026-10-14）；2026-09 版约 6.26 亿条，JSONL 约 745 GB（works 约 615 GB），Parquet 约 770 GB；按 `updated_date` 分区；works 删除日志自 2026-09-23 版进入公共桶；日更快照与 `from_created_date`/`from_updated_date` 属付费（Member+ 起 $10,000/年） | 确认 | https://help.openalex.org/access/snapshot ；https://help.openalex.org/access/sync ；https://help.openalex.org/access/pricing | 2026-09-26 |
| V07 §6.2 Topics 层级 4 / 26 / 252 / 4,516；每篇 work 最多 3 个 topic；约 12%（39.6M/322M）无 topic；与 CWTS 合作、按 ASJC 映射；编号可放进 `smallint` | 确认（[LIVE]：topic 计数 4,516，最大编号 T14521；subfield 计数 252，最大编号 3616） | https://help.openalex.org/data/topics ；https://api.openalex.org/topics?sort=id:desc&per_page=2 ；https://api.openalex.org/subfields?sort=id:desc&per_page=2 | 2026-09-26 |
| V08 §3.5.2/§6.2 `/text/topics`：$0.01/次，1 rps，输入 20–2000 字符 | 确认；补充 example-costs 页已把 Text/Aboutness 标为 deprecated | https://help.openalex.org/api/tag-aboutness ；https://help.openalex.org/access/example-costs | 2026-09-26 |
| V09 §2.2 Crossref 三档池：Public 5 req/s、并发 1；Polite 10 req/s、并发 3；Plus 150 req/s、不限并发；超限 429，人工封禁 403 | 确认（[LIVE] 复测：`x-api-pool: public-single`、`x-rate-limit-limit: 5`、`x-rate-limit-interval: 1s`、`x-concurrency-limit: 1`） | https://www.crossref.org/documentation/retrieve-metadata/rest-api/access-and-authentication/ ；https://api.crossref.org/works/10.1145/1571941.1572114 | 2026-09-26 |
| V10 §3.4 Crossref：rows ≤1000、offset ≤1 万、支持 cursor；字段化 `query.*`（原标“⚠ 细项未核验”） | 确认；补充字段查询清单，以及 cursor 5 分钟未用即过期 | https://api.crossref.org/swagger-docs | 2026-09-26 |
| V11 §2.2 S2：未认证用户共享 1000 req/s（高峰可能进一步限流）；API key 入门额度 1 RPS（全端点）；语料 214M 论文、2.49B 引用 | 确认 | https://www.semanticscholar.org/product/api | 2026-09-26 |
| V12 §3.4 S2 bulk 检索：支持布尔、每次 ≤1000 条、续传 token、总量 ≤1000 万；`/paper/search` 最多返回 1000 条 | 确认 | https://api.semanticscholar.org/graph/v1/swagger.json | 2026-09-26 |
| V13 §3.4 S2 语义与推荐能力（原标“⚠ 推荐 API 未核验”） | 修正：Recommendations API 的两个端点确认存在；补充 `/snippet/search` | https://api.semanticscholar.org/recommendations/v1/swagger.json ；https://api.semanticscholar.org/graph/v1/swagger.json ；https://www.semanticscholar.org/product/api | 2026-09-26 |
| V14 §2.2 arXiv legacy API（OAI-PMH、RSS、Query API）≤1 请求/3 秒、单连接，按所控全部机器合计；robots 为 `Crawl-delay: 15`，禁止 `/api`、`/search` | 确认 | https://info.arxiv.org/help/api/tou.html ；https://arxiv.org/robots.txt | 2026-09-26 |
| V15 §3.4 arXiv `max_results`：每次 ≤2000，合计 ≤30,000（超过返回 400） | 确认 | https://info.arxiv.org/help/api/user-manual.html | 2026-09-26 |
| V16 §2.2 bioRxiv：details 每页 30 条，pubs 每页 100 条；未见书面限速 | 确认 | https://api.biorxiv.org/ | 2026-09-26 |
| V17 §2.2/§9.1 Crossref / OpenAlex / S2 单条 GET 均不返回 ETag、Last-Modified、Cache-Control | 确认（各复测 1 次；OpenAlex 只在 `access-control-expose-headers` 中列出 Cache-Control，响应里并无该头） | 同 [LIVE-headers] 三个 URL | 2026-09-26 |
| V18 §2.2/§3.4/§9.3 DBLP 为 `Crawl-delay: 4`，robots 只禁 `/search` | **修正**：robots 已改为 `User-agent: *` 全站 `Disallow: /`，三个镜像相同，文件中已无 Crawl-delay 行；DROPS 只禁 `/api/*` 与 metadata 路径 | https://dblp.org/robots.txt ；https://dblp.uni-trier.de/robots.txt ；https://dblp.dagstuhl.de/robots.txt ；https://drops.dagstuhl.de/robots.txt | 2026-09-26 |
| V19 §2.2/§3.4 PubMed 限速（原标 ⚠） | 修正（核验补充）：E-utilities 无 key 3 rps、带 key 10 rps；NBK25497 仍为 reCAPTCHA，未绕过 | https://support.nlm.nih.gov/kbArticle/?pn=KA-05317 ；https://ncbiinsights.ncbi.nlm.nih.gov/2017/11/02/new-api-keys-for-the-e-utilities/ ；https://www.ncbi.nlm.nih.gov/books/NBK25497/ | 2026-09-26 |
| V20 §2.2 Europe PMC 限速与能力 | 未核验（文档页 403，未绕过） | https://europepmc.org/RestfulWebService | 2026-09-26 |
| V21 §2.2 Unpaywall 10 万次/日 | 未核验（unpaywall.org 产品页为 JS 渲染；OpenAlex 的 Unpaywall 页未写日限额）；“仅按 DOI 查询”与“Data Feed 属付费”两点确认 | https://unpaywall.org/products/api ；https://help.openalex.org/access/unpaywall | 2026-09-26 |
| V22 §4.1 LitSearch：597 条查询；最佳稠密检索器与 BM25 的 recall@5 绝对差 24.8%；LLM 重排再 +4.4%；Google 等落后 32 点 | 确认 | https://aclanthology.org/2024.emnlp-main.840/ | 2026-09-26 |
| V23 §4.1 PaSa：AutoScholarQuery 约 3.5 万条；PaSa-7B 比 Google+GPT-4o 的 recall@20 高 37.78%、recall@50 高 39.90% | 确认 | https://arxiv.org/abs/2501.10120 | 2026-09-26 |
| V24 §3.2 QPP 局限：选择性处理只带来约 4% NDCG 增益，集合是首要影响因素；原写“TOIS（2025 在线）” | 数字确认；**日期修正**为 TOIS 44(6)，2026（在线 2026-08-11） | https://api.crossref.org/works/10.1145/3774427 ；https://api.semanticscholar.org/graph/v1/paper/DOI:10.1145/3774427?fields=abstract | 2026-09-26 |
| V25 §4.1/§4.5 SPLADE v2 在 TREC DL 2019 上 NDCG@10 提升超 9%；naver/splade 代码与权重为 CC BY-NC-SA 4.0；另 8 个模型的许可 | 确认（`naver/splade-v3` 为 gated=auto） | https://arxiv.org/abs/2109.10086 ；https://github.com/naver/splade/blob/main/LICENSE ；https://huggingface.co/api/models/naver/splade-v3 （其余 8 个见 [HF-lic]） | 2026-09-26 |
| V26 §4.1 SciRepEval：按任务格式定制的控制码/适配器比单嵌入 SOTA 绝对高 2 分以上 | 确认 | https://arxiv.org/abs/2211.13308 | 2026-09-26 |
| V27 §4.2 RRF 的 k=60 由试点确定，接近最优 | 确认 | https://cormack.uwaterloo.ca/cormacksigir09-rrf.pdf | 2026-09-26 |
| V28 §9.1 Tail at Scale 对冲：等到 p95 再发，额外负载约 5%；BigTable 示例 1,000 键 / 100 台，10 ms 后对冲，99.9 分位从 1,800 ms 降到 74 ms，只多发 2% 请求 | 确认 | https://www.barroso.org/publications/TheTailAtScale.pdf | 2026-09-26 |
| V29 §8.1 Kolobov 2019：PoliteBinaryLambdaCrawl 是首个礼貌约束下的最优算法，数据为 14 周、每日 1850 万 URL；Azar 2018：最优随机策略 O(n log n)，由其导出的确定性调度达最优值 99% | 确认 | https://doi.org/10.1145/3331184.3331241 ；https://doi.org/10.1073/pnas.1801519115 （两篇摘要均经 S2 API 取回） | 2026-09-26 |
| V30 §8.1 Cho & Garcia-Molina 的变化率估计量与期望新鲜度公式 | 未核验（作者自存 PDF：HTTPS 握手失败、HTTP 超时；Stanford 副本返回 500） | http://oak.cs.ucla.edu/cho/papers/cho-freq.pdf ；http://ilpubs.stanford.edu:8090/471/1/2000-4.pdf | 2026-09-26 |
| V31 §5.1/§5.3 DiskANN：64 GB 内存 + SSD、10 亿点、>5000 QPS、平均 <3 ms、1-recall@1 ≥95%、16 核 | 确认 | https://www.microsoft.com/en-us/research/publication/diskann-fast-accurate-billion-point-nearest-neighbor-search-on-a-single-node/ | 2026-09-26 |
| V32 §5.1 Big-ANN'23 稀疏赛道“约 3 万维” | **修正**：论文只写“维度 <10⁵”，平均约 120 个非零；补充查询 6,980 条、平均约 49 个非零 | https://arxiv.org/abs/2409.17424 （PDF §2.3、表 1） | 2026-09-26 |
| V33 §5.1 Curator：低选择率查询延迟最多降 20.9×，构建时间与内存仅 +5.5% / +4.3% | 确认；补充“相对预过滤回退”的限定 | https://arxiv.org/abs/2601.01291 | 2026-09-26 |
| V34 §6.2/§10.4 Science Data Lake：4,516 个 topic 映射到 13 个本体（约 130 万术语），得 16,150 条映射，覆盖 99.8%；推荐工作点 F1=0.77；约 960 GB Parquet、约 2.93 亿篇 | 确认 | https://arxiv.org/abs/2603.03126 | 2026-09-26 |
| V35 §3.3 Information Manifold 统一访问 100+ 个 Web 源，并用源描述剪枝；TSIMMIS 按源能力生成可行计划 | 确认 | https://www.vldb.org/conf/1996/P251.PDF ；https://doi.org/10.1145/276304.276382 （摘要经 S2 API 取回） | 2026-09-26 |
| V36 §14 书目：46 个 DOI 与 18 个 arXiv ID 是否存在，题名与作者是否相符 | 确认（全部可解析且相符，未发现编造） | https://api.crossref.org/works/{doi} ；https://export.arxiv.org/api/query?id_list=… | 2026-09-26 |
| V37 §5.2/§6.3 pgvector：0.8.0（2024-10-30）起支持 iterative scan；0.8.6 发布于 2026-07-29；`hnsw.max_scan_tuples` 默认 20,000；ef_search=40 且过滤选择率 10% 时平均只剩约 4 行；halfvec 索引 ≤4,000 维；租户隔离用 list 分区或分表 | 确认 | https://github.com/pgvector/pgvector （README、CHANGELOG.md） | 2026-09-26 |
| V38 §5.2 pgvectorscale 0.9.1（2026-09-04）：StreamingDiskANN、SBQ、`smallint[]` 标签配合 `&&`；README 称相对 Pinecone s1，p95 延迟低 28×、吞吐高 16×（厂商自测） | 确认 | https://github.com/timescale/pgvectorscale | 2026-09-26 |
| V39 §5.2 pg_textsearch 1.4.0（2026-08-18），PostgreSQL 许可，“仅支持 PG 17/18” | 确认；补充 PG19 beta 为 best-effort，分区表的 IDF 按分区局部计算 | https://github.com/timescale/pg_textsearch | 2026-09-26 |
| V40 §5.2 ParadeDB：AGPL-3.0，基于 Tantivy，v0.25.10 发布于 2026-09-23 | 确认 | https://github.com/paradedb/paradedb （README、`pg_search/Cargo.toml`、releases） | 2026-09-26 |
| V41 §4.2/§5.2 Qdrant：RRF 默认 k=2、排名从 0 起；DBSF 自 1.11；`full_scan_threshold` 为 10,000 KB；Tenant Index 自 1.11；payload 索引需先于数据建立；容量规划公式 | 确认；补充 1.16 起 k 可配置 | https://qdrant.tech/documentation/concepts/hybrid-queries/ ；https://qdrant.tech/documentation/concepts/indexing/ ；https://qdrant.tech/documentation/capacity-planning/ | 2026-09-26 |
| V42 §5.3 TigerData 基准（2025-04-29）：471.57 vs 41.47 QPS；p50 / p95 / p99；建索引 11.1 h vs 3.3 h；机型 r6id.4xlarge。另有 Qdrant 自家基准：2024 年 1 月/6 月更新；数据集含 dbpedia-openai 100 万 × 1536、deep-image 1000 万 × 96；服务器 8 vCPU / 32 GiB；自称“几乎所有场景 RPS 最高、延迟最低” | 确认；补充 TigerData 基准的对手版本为 Qdrant 1.13.4 | https://www.tigerdata.com/blog/pgvector-vs-qdrant ；https://qdrant.tech/benchmarks/ | 2026-09-26 |
| V43 §4.2/§5.2 Elasticsearch RRF 属 Enterprise 订阅（原标 ⚠，只有第三方来源） | **修正**：已按订阅页直接核验确认 | https://www.elastic.co/subscriptions | 2026-09-26 |
| V44 §5.2 Elasticsearch 自 2024-08-29 起加入 AGPL；BBQ（2024-11-11）内存约降 95%、量化时间少 20–30×、查询快 2–5× | 确认；措辞改为“宣布增加 AGPL 选项”；补充 `x-pack` 代码只以 ELv2 授权 | https://www.elastic.co/blog/elasticsearch-is-open-source-again ；https://github.com/elastic/elasticsearch/blob/main/LICENSE.txt ；https://www.elastic.co/search-labs/blog/better-binary-quantization-lucene-elasticsearch | 2026-09-26 |
| V45 §5.2 Milvus 3.0.0（2026-07-29）引入 External Collection | **修正**：External Collection 由 3.0-beta 引入，3.0.0 完善；在线加列/回填/删列、SINDI、Block-Max WAND/MaxScore 确认 | https://github.com/milvus-io/milvus/releases/tag/v3.0.0 | 2026-09-26 |
| V46 §4.2/§5.2 OpenSearch 自 2.19 支持 RRF（`rank_constant` 默认 60）；`on_disk` 默认 32× 压缩并用全精度向量重打分；Typesense 按 0.7/0.3 融合（`alpha` 可调）；Meilisearch 有 `semanticRatio` 与 `rankingScoreThreshold` | 确认（Meilisearch 文档 URL 已重定向，参考链接已更新） | https://docs.opensearch.org/latest/vector-search/ai-search/hybrid-search/rrf/ ；https://docs.opensearch.org/latest/vector-search/optimizing-storage/disk-based-vector-search/ ；https://typesense.org/docs/30.0/api/vector-search.html ；https://www.meilisearch.com/docs/capabilities/hybrid_search/getting_started | 2026-09-26 |
| V47 §6.1 Kùzu 已归档（最后推送 2025-10-10，README 写 “Kuzu is working on something new”）；LadybugDB（README 称 formerly known as Kuzu）、Bighorn（GitHub fork）、RyuGraph（自称 fork，2026-01 后未更新）；Apache AGE 分支覆盖 PG11–PG19，PG18/v1.8.0-rc0 发布于 2026-07-09 | 确认 | https://github.com/kuzudb/kuzu ；https://github.com/LadybugDB/ladybug ；https://github.com/Kineviz/bighorn ；https://github.com/predictable-labs/ryugraph ；https://github.com/apache/age | 2026-09-26 |
| V48 §6.1/§10 PG14 起支持 SEARCH/CYCLE（对照 13 与 14 文档）；PG18（2025-09-25）带来 AIO、`uuidv7()`、skip scan、虚拟生成列、OAuth 2.0；PG19 Beta 4 发布于 2026-09-24；RLS 无策略时默认拒绝，BYPASSRLS 角色与表 owner 默认绕过（可用 FORCE 强制） | 确认 | https://www.postgresql.org/docs/14/queries-with.html ；https://www.postgresql.org/docs/13/queries-with.html ；https://www.postgresql.org/about/news/postgresql-18-released-3142/ ；https://www.postgresql.org/about/newsarchive/ ；https://www.postgresql.org/docs/current/ddl-rowsecurity.html | 2026-09-26 |
| V49 §10.3 Supabase：策略列要建索引；用 `(select fn())` 包裹函数以触发 initPlan；用 pgTAP 测试 | 确认 | https://supabase.com/docs/guides/database/postgres/row-level-security | 2026-09-26 |
| V50 §10.1 AWS Silo / Bridge / Pool 三种模式的优缺点 | **修正**：Bridge 行按 AWS 原表补全，“迁移与目录膨胀”改标 [判断]；Silo 行补全 | https://docs.aws.amazon.com/prescriptive-guidance/latest/saas-multitenant-managed-postgresql/partitioning-models.html | 2026-09-26 |
| V51 §9.1 Google SRE：每请求最多尝试 3 次；每客户端重试占比 <10%；自适应节流用最近 2 分钟窗口，K 举例为 2 | 确认 | https://sre.google/sre-book/handling-overload/ | 2026-09-26 |
| V52 §9.1 Envoy 重试预算默认 20%、最小并发 3，以及自适应并发的梯度公式；gRPC A6 中 `maxTokens` 取值 (0, 1000]，示例为 10 / 0.1，token ≤ maxTokens/2 时停止重试与对冲；Netflix 的 Vegas 队列估计，服务端推荐 Vegas、客户端推荐 AIMD，live/batch 按 90%/10% 分区 | 确认 | https://www.envoyproxy.io/docs/envoy/latest/api-v3/config/cluster/v3/circuit_breaker.proto ；https://www.envoyproxy.io/docs/envoy/latest/configuration/http/http_filters/adaptive_concurrency_filter ；https://github.com/grpc/proposal/blob/master/A6-client-retries.md ；https://github.com/Netflix/concurrency-limits | 2026-09-26 |
| V53 §10.6/§10.7 arq 声明“仅维护模式”；pgloader v4 为 Clojure/JVM 重写（需 Java 21+），v3.6.9 发布于 2022-10-24；Hatchet 自称压测到 1 万任务/秒；absurd 公告发布于 2025-11-03；procrastinate 要求 PG13+；pgqueuer 用 SKIP LOCKED + LISTEN/NOTIFY | 确认 | https://github.com/python-arq/arq ；https://github.com/dimitri/pgloader ；https://github.com/hatchet-dev/hatchet ；https://lucumr.pocoo.org/2025/11/3/absurd-workflows/ ；https://github.com/procrastinate-org/procrastinate ；https://github.com/janbjorge/pgqueuer | 2026-09-26 |
| V54 §10.4/§10.5 TimescaleDB 的 `tsl/` 目录为 Timescale License，其余 Apache-2.0；Timescale 于 2025-06-17 更名 TigerData；Redis 8 起 RSALv2 / SSPLv1 / AGPLv3 三选一；Meilisearch 为 MIT AND BUSL-1.1 | 确认 | https://github.com/timescale/timescaledb/blob/main/LICENSE ；https://www.tigerdata.com/newsroom/timescale-becomes-tiger-data-defining-a-new-standard-as-the-fastest-postgresql-platform-for-modern-applications ；https://github.com/redis/redis/blob/unstable/LICENSE.txt ；https://github.com/meilisearch/meilisearch/blob/main/LICENSE | 2026-09-26 |
| V55 §4.1/§7.1 Splink 在笔记本上约 1 分钟链接百万记录，后端可选 DuckDB、Spark（1 亿+）、PostgreSQL；datasketch 提供 LSH Forest、LSH Ensemble、LSHBloom，并支持 Redis/Cassandra；s2search 需要 >17 GB 内存 | 确认 | https://github.com/moj-analytical-services/splink ；https://github.com/ekzhu/datasketch ；https://github.com/allenai/s2search | 2026-09-26 |
| V56 附表 A：85 个仓库的 star、许可、最近推送 | 确认（star 偏差 ≤0.1%，推送日期一致）；**修正 4 项**：sentence-transformers 已迁至 huggingface 组织；VectorChord-bm25 实为 AGPLv3/ELv2；pg_partman 实为 PostgreSQL License；Valkey 最新版为 9.1.2 | https://api.github.com/repos/{owner}/{repo} （含 `/license`、`/releases`） | 2026-09-26 |
| V57 §2.1/§10.7 v1 基线：本地库 paper=179、identifier=228、asset=3、fulltext=3、subscription=2、task=23；`grep -rli etag src` 0 命中 | 确认（本地只读复核） | 本地 `.paper-crawler/catalog.sqlite`（`mode=ro`）与 `src/` | 2026-09-26 |
| V58 §5.2（覆盖缺口）Weaviate：混合检索融合方式、原生多租户（每租户一个 shard）、许可结构 | 确认（核验补充） | https://docs.weaviate.io/weaviate/search/hybrid ；https://docs.weaviate.io/weaviate/manage-collections/multi-tenancy ；https://github.com/weaviate/weaviate/blob/main/LICENSE | 2026-09-26 |
| V59 §10.3/§10.6（覆盖缺口）PgBouncer 事务池不支持会话级 SET/RESET、LISTEN、SQL 级 PREPARE 与会话级 advisory lock；procrastinate 默认 `listen_notify=True` | 确认（核验补充）；`SET LOCAL` 能否与事务池配合仍 ⚠ 待实测 | https://www.pgbouncer.org/features.html ；https://github.com/procrastinate-org/procrastinate/blob/main/docs/discussions.md | 2026-09-26 |

**核验结论摘要**：本表共 59 行（多数行合并了同一来源的若干数字）。结论为“确认”的 47 行，其中 V56 另含附表 A 的 4 项修正；结论为“修正”的 9 行（V03、V13、V18、V19、V24、V32、V43、V45、V50），连同 V56 共计 13 项修正；未核验 3 行（Europe PMC、Unpaywall 日限额、Cho & Garcia-Molina 公式）；删除 0 行。另有 5 处表述精度调整：Curator 加“相对预过滤回退”限定、ES 的 AGPL 改为“宣布”、pg_textsearch 的 PG 版本支持说明、Meilisearch 链接迁移、TigerData 基准注明对手为 Qdrant 1.13.4。核验补充 12 处：PubMed 限速（§2.2、§3.4、§9.3）、S2 推荐与 snippet 检索、Weaviate、PgBouncer 约束（§10.3、§10.6、启示 28）、OpenAlex `corpus` 参数、`/text` 弃用信号、Crossref 字段查询与 cursor 过期、pg_textsearch 分区 IDF、Qdrant k 可配、ES `x-pack` 许可、风险第 16 与 17 条、启示第 31 条。设计阶段最需要注意的两项修正：一是 **dblp 全站 robots 禁止**，影响来源名录，也影响 v1 保留的 dblp adapter；二是 **OpenAlex `/text` 的弃用信号**，影响路由冷启动方案。
