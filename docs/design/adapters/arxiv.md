---
title: Adapter 设计 · arXiv
status: review
owner: fable5
updated: 2026-07-20
---

# Adapter · `arxiv`

## 1. 定位

- **family**: `open_access`
- **服务 venue**：arXiv 全站，按 category 切分为 `preprint_channel` 型 venue（`arxiv-cs-lg`、`arxiv-q-fin-pr`…，覆盖 cs.*/stat.ML/econ.*/q-fin.*，见 [catalog/preprint-platforms.md](../../catalog/preprint-platforms.md)）
- **capabilities**: `DISCOVER | ENUMERATE | RESOLVE | FETCH | SEARCH`（五项全能力，SEARCH 是订阅 DSL 的主执行端）
- 元数据/全文分工：本 adapter 同时承担元数据与全文；历史回填元数据优先走 Kaggle bulk（非在线接口）。

## 2. 站点勘察摘要

来源：[research/site-survey/arxiv.md](../../research/site-survey/arxiv.md)（[LIVE] 2026-07-20）。要点：

| 通道 | 用途 | 关键约束 |
|---|---|---|
| Query API `export.arxiv.org/api/query` | 精确查询/订阅 | 1 req/3s 单连接（ToU）；分页硬上限 30000 |
| OAI-PMH `oaipmh.arxiv.org/oai`（2025-03 迁移后域） | 增量收割（官方推荐 bulk 方式） | resumptionToken 每日过期；set 只到 archive 级 |
| RSS `rss.arxiv.org/rss/{cat}` | 当日速览 | 单日快照，2000 条上限 |
| Kaggle bulk（Cornell-University/arxiv） | 历史全量元数据 | 需 Kaggle 免费账号；周更、CC0 |
| S3 requester-pays | 全量 PDF/LaTeX | 按流量计费（~9.2TB），默认不启用 |
| `arxiv.org/abs|pdf/{id}` | 单篇精取 | robots Crawl-delay 15s（listing）；PDF 归 1 req/3s 口径 |

- 认证：无；反爬：无 Cloudflare，但 ToU 明文禁止无差别批量抓取；
- ID 两代：`YYMM.NNNNN`（2007-04 起）与 `archive.subject/YYMMNNN`（更早）；版本后缀 `v{n}`。

## 3. 各阶段实现方案

- **discover_timeline**：预印本无"期"概念——按 (category, 年月) 生成虚拟月度桶 Issue（`cs.LG/2024-07`，design/08 §1）。历史桶一次性生成（arXiv 1991-08 起），无需网络；`paper_count_claimed` 留空（无权威口径）。
- **enumerate_issue**：
  - 历史回填（backfill）：Kaggle bulk JSONL 本地过滤 `categories` 字段 → 按提交月分桶入库。**绝不用 Query API 翻历史全量**（30000 上限 + ToU）。
  - 增量（watch）：OAI-PMH `from/until` 日收割（set=archive 级如 `cs`，子分类客户端过滤）；Query API 仅用于用户 DSL 的字段级精确查询。
  - 字段映射：`id→identifier(arxiv)`、`journal_ref/doi` 回填字段 → ingest 建 `preprint_of` 候选（D-007）。
- **resolve_assets**：纯 URL 构造（无网络）：`https://arxiv.org/pdf/{id}v{n}`（pdf）、`https://arxiv.org/abs/{id}`（landing）、可选 `e-print`（LaTeX source）。默认取最新版；`--all-versions` 时经 `arXivRaw`（OAI）拿版本史逐版生成 AssetPlan。`url_strategy=direct`，`auth_needed=none`。
- **fetch_asset**：HttpFetcher 直取；校验 `%PDF` 魔数；HTML 回应（撤稿/合并页）判 `gone`。
- **search**：订阅 DSL 编译为 `search_query`（`ti:/abs:/cat:/au:` + `AND/OR/ANDNOT` + `submittedDate:[A TO B]`，design/09 §3）；结果分页 ≤2000/次；水位线=submittedDate 上界，重叠 1 天窗口防 announce 延迟丢失。
- **healthcheck**：GET Query API 固定查询（`id_list=已知id`），比对返回 title。

## 4. 限速与礼貌

| domain | 速率 | 依据 |
|---|---|---|
| export.arxiv.org / oaipmh.arxiv.org | 1 req/3s，并发 1 | 官方 ToU（[LIVE] 勘察） |
| arxiv.org（listing 页，尽量不用） | 1 req/15s | robots.txt Crawl-delay 15 |
| arxiv.org（abs/pdf 单篇） | 1 req/3s，并发 1 | ToU 口径统一 |

- UA：`PaperCrawler/<ver> (personal research; mailto:<user>)`（D-014）；
- robots 合规：`/search` `/api` 等 Disallow 路径不访问（我们只用文档化 API）；bulk 需求走 Kaggle/S3 而非在线刷取。

## 5. 失败模式映射

| 站点现象 | error_class | 说明 |
|---|---|---|
| HTTP 503 + Retry-After（API 惯用） | `rate_limited` | 按头等待重试 |
| 分页 offset 超 30000 → 400 | `config` | 设计缺陷信号：应改走日期切片，不重试 |
| id 不存在 / withdrawn 版本 | `gone` | Asset 标 gone，记录 withdrawn 备注 |
| Atom 解析 0 条且 totalResults>0 | `parse` | canary 标红 |
| OAI resumptionToken 过期（badResumptionToken） | `transient` | 从当日窗口重新发起收割 |

## 6. Fixtures 与测试

- **T1 单元**：ID 两代解析/构造矩阵（新旧格式 × 版本后缀）；DSL→search_query 编译用例表；月度桶生成边界（1991-08 起点、当月未满）。
- **T3 fixture 三件套**：①Query API Atom 响应（10 条正常）②OAI-PMH ListRecords 页（含 resumptionToken）③空结果 Atom + 一个 withdrawn 记录页。
- **T4 集成**：watch 水位线推进与重叠去重（注入两日重叠数据无重复入库）。
- **T5 canary 样本**：`2401.00001` 类已知 id 的 title 精确匹配；`cat:cs.LG` 单日计数 >0。
- **验收关联**：AC-2.3（订阅 7 天无重复无遗漏）、AC-6.1/6.4；测试类型定义见 [testing/test-plan.md](../../testing/test-plan.md)。

## 7. 风险与维护

- OAI-PMH 域名 2025-03 已迁移一次（旧域 301）——client 跟随重定向并在 canary 监控 301 链变化；
- Kaggle 数据集 schema 偶有列变动：bulk 导入器做 schema 校验，失败即 `parse` 并提示锁定旧版本数据集；
- S3 全量 PDF 属付费重型操作：默认关闭，启用需显式配置 + 费用预估提示（文档化在 CLI help）。
