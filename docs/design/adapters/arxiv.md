---
title: Adapter 设计 · arXiv
status: implemented
owner: fable5
updated: 2026-07-22
---

# Adapter · `arxiv`

> 2026-07-21 评审修订：双独立评审（技术一致性 / 测试+红线）共 2 BLOCKER + 10 CONCERN，主 agent 裁决全部闭合——watch 增量改为零接口变更的"当月桶重复 enumerate"模型、fixture 扩为八件套、SEARCH 位本期不声明、Kaggle backfill 显式推迟、AC-2.3 验收证据分层（D-018）。评审报告归档于 session 日志。

## 1. 定位

- **family**: `open_access`
- **服务 venue**：arXiv 全站，按 category 切分为 `preprint_channel` 型 venue（`arxiv-cs-lg`、`arxiv-q-fin-pr`…，白名单以 [catalog/preprint-platforms.md](../../catalog/preprint-platforms.md) §1 为准）
- **capabilities**: `DISCOVER | ENUMERATE | RESOLVE | FETCH`（Phase 2 实现口径）。
  **SEARCH 位本期不声明**：冻结 `SourceAdapter` 协议（接口冻结件 §2.3）无 `search()` 方法、Phase 2 亦无任何消费方；arXiv 的订阅命中经 **enumerate 增量 + 本地过滤**（`Selector.filter_expr` 语义）达成。DSL→`search_query` 字段级下推与 `search()` 方法的接口新增（须走仲裁）统一推迟 Phase 6（AC-6.4「下推/本地一致」），届时再点亮 SEARCH 位。
- 元数据/全文分工：本 adapter 同时承担元数据与全文；历史回填元数据优先走 Kaggle bulk（**backfill 能力本期 deferred**，见 §3）。

## 2. 站点勘察摘要

来源：[research/site-survey/arxiv.md](../../research/site-survey/arxiv.md)（[LIVE] 2026-07-20）。要点：

| 通道 | 用途 | 关键约束 |
|---|---|---|
| Query API `export.arxiv.org/api/query` | 精确查询/healthcheck | 1 req/3s 单连接（ToU）；分页硬上限 30000 |
| OAI-PMH `oaipmh.arxiv.org/oai`（2025-03 迁移后域） | 增量收割（官方推荐 bulk 方式） | resumptionToken 每日过期；set 只到 archive 级 |
| RSS `rss.arxiv.org/rss/{cat}` | 当日速览（本期不用） | 单日快照，2000 条上限 |
| Kaggle bulk（Cornell-University/arxiv） | 历史全量元数据（backfill，deferred） | 需 Kaggle 免费账号；周更、CC0 |
| S3 requester-pays | 全量 PDF/LaTeX | 按流量计费（~9.2TB），默认不启用 |
| `arxiv.org/abs|pdf/{id}` | 单篇取回 | robots Crawl-delay 15s（listing）；PDF 归 1 req/3s 口径 |

- 认证范围限定：**在线接口（Query API / OAI-PMH / RSS / abs / pdf）无认证**；Kaggle bulk 需 Kaggle 账号；S3 需 AWS 计费账号。反爬：无 Cloudflare，但 ToU 明文禁止无差别批量抓取。
- ID 两代：`YYMM.NNNNN`（2007-04 起）与 `archive.subject/YYMMNNN`（更早）；版本后缀 `v{n}`。

## 3. 各阶段实现方案

- **discover_timeline**：预印本无"期"概念——按 (category, 年月) 生成虚拟月度桶 Issue（design/08 §1），无需网络。
  - **月度桶字段分解（幂等键定死）**：`volume=NULL`、`number='MM'`（两位零填充月份字符串）、`year=YYYY`、`label='YYYY-MM'`——`upsert_issue` 四列幂等与 `--year` selector 过滤（走 `year` 列）由此确定性成立。
  - **起点**：venue YAML `quirks.inception: 'YYYY-MM'` 声明该 category 的起始月（依 catalog 数据）；未声明则回退 arXiv 全局起点 `1991-08`。`paper_count_claimed` 留空（无权威口径）。
- **enumerate_issue**：OAI-PMH `ListRecords`（set=archive 级如 `cs`，子分类客户端过滤）+ resumptionToken 翻页；按月度桶边界构造 `from/until` 窗口。
  - **增量（watch，Phase 2 最小实现——零接口变更）**：watch 运行时对**当月虚拟桶**（及跨月边界时的上一月桶）重复调用 `enumerate_issue`；adapter 内部以 `from=<桶月 1 日>` `until=<今日>` 收割整窗。去重由 `identifier(scheme='arxiv')` 主键天然保证（重叠窗口不产生重复行）。**不依赖 `subscription.watermark_json`**——"水位线"（watermark）在本期由"当月桶 + 整窗收割"隐式表达；显式 watermark 游标作为省流量优化推迟 Phase 6。`enumerate_issue` 不新增形参。
  - **watch 框架侧净新增清单**（超出 adapter 自身、属 Phase 2 pipeline/CLI 工作）：`crawler watch` 命令 + watch 编排（对 preprint venue 当月桶执行 enumerate 级联，复用新鲜度 TTL 机制）；subscription 表读写面推迟 Phase 6。
  - **历史回填（backfill）：本期 deferred**。排期实现前需补充设计：Kaggle 凭证存放（走标准 kaggle CLI 惯例 `~/.kaggle/kaggle.json`，仓库外；**禁止任何项目内路径存放**，AGENTS §6.4）与本地小样本 JSONL fixture 测试策略（非 HTTP 快照，需扩展 fixture 规范）。此推迟不阻塞本文档批准。**绝不用 Query API 翻历史全量**（30000 上限 + ToU）。
  - **字段映射**：`id → identifier(scheme='arxiv')`，**value 一律存去版本规范 id**（新代 `2401.12345`；旧代保留斜杠原形、小写归一 `hep-th/9901001`）——跨版本/跨源强合并锚点由此成立（AC-3.1 前提）。版本号只入 `asset.version`。`journal_ref`/`doi` 回填字段**不产出为 identifier**，放 `PaperStub.meta`（键 `journal_ref`/`doi`）——Phase 3 ingest 依 D-007 决定 `preprint_of` 建边，避免 Phase 2 意外触发跨源强合并。
- **resolve_assets**：纯 URL 构造、零网络：`https://arxiv.org/pdf/{id}`（pdf，最新版语义）、`https://arxiv.org/abs/{id}`（landing）。默认最新版 `asset.version=None`（与 `(paper_id, kind, version)` 幂等键及 re-resolve `_match_plan` 复位稳定对齐）。`--all-versions`（经 OAI `arXivRaw` 拿版本史、逐版 `v1/v2/...` 生成 AssetPlan）**本期 deferred**——CLI 无此承诺，随全文库增强需求排期。`url_strategy=direct`，`auth_needed=none`。
- **fetch_asset**：经共享 `HttpClient.stream` 取流交 `FetchIO.write_stream`；**`%PDF` 魔数权威校验在 pipeline**（冻结分工）；adapter 职责是对 HTML 回应（撤稿/合并页）判 `gone`。
- **healthcheck**：GET Query API 固定查询（`id_list=<带版本号样本>`），比对**空白规整化后的 title + primary_category** 双字段（见 §6 canary）。

## 4. 限速与礼貌

| domain | 速率 | 依据 |
|---|---|---|
| export.arxiv.org / oaipmh.arxiv.org | 1 req/3s，并发 1 | 官方 ToU（[LIVE] 勘察） |
| arxiv.org（listing 页，本期不访问） | 1 req/15s | robots.txt Crawl-delay 15 |
| arxiv.org（abs/pdf 单篇） | 1 req/3s，并发 1 | ToU 口径统一 |

- UA：`PaperCrawler/<ver> (personal research; mailto:<user>)`（D-014）；`default_rate` 带 `source_note` 出处（types.RatePolicy 强制）。
- **robots 合规（两域名分别对待）**：`arxiv.org` robots 允许 `/list /abs /pdf`（Crawl-delay 15）、禁 `/search /api` 等——我们不访问其禁区。`export.arxiv.org` robots 对通用爬虫全禁——**本 adapter 对该域仅走官方文档化 API（Query API），其程序化访问依据是 arXiv API ToU 的明确邀请（api.arxiv.org 文档），robots.txt 的网页爬虫公约不适用于 ToU 授权的 API 消费**；**复核已执行（T7 在线冒烟 2026-07-22）**：`export.arxiv.org/robots.txt` 实测 `Disallow: /`（blanket 形态，与勘察记录一致）——维持本节推理（ToU 授权的文档化 API 消费不受网页爬虫公约约束），无 AC-0.5 升级；书面 ToU 条款引用列为增强项（终审补充）。
- bulk 需求走 Kaggle/S3 而非在线刷取。

## 5. 失败模式映射

| 站点现象 | error_class | 说明 |
|---|---|---|
| HTTP 503 + Retry-After（API 惯用） | `rate_limited` | pipeline 固定退避重试（2/8/30s，通常 ≥ 站点 Retry-After，保守合规）；HttpClient 解析头值入 detail（`retry_after_s=<n>`）仅作观测（计划 §2.1 冻结裁决）；domain 冷却维持 Phase 1 近似（真实冷却随 Phase 4） |
| 分页 offset 超 30000 → 400 | `config` | 设计缺陷信号：应改走日期切片，不重试 |
| id 不存在 / withdrawn 版本 | `gone` | Asset 标 gone，记录 withdrawn 备注 |
| Atom 解析 0 条且 totalResults>0 | `parse` | canary 标红 |
| OAI resumptionToken 过期（badResumptionToken） | `transient` | **token 契约**：resumptionToken 仅单次收割内有效、绝不持久化、绝不跨重试复用；transient 重试时从月度桶窗口**重建** `from/until` 请求（任务级重跑天然满足）。单日窗口不会超 token TTL（大回填不走此路） |
| OAI `noRecordsMatch` | —（**非错误**） | 空窗口/空桶的 OAI 合法响应：解析为**空记录序列正常完成**（watch 空日、新 category 月初的常态）。勘误补全 2026-07-22：T4 审查 ⚠ 复核暴露的设计空白——若误归 parse 会使空日 watch 假故障 |
| OAI badArgument / badVerb / cannotDisseminateFormat | `config` | 我方请求构造缺陷，响亮停机（与 HttpClient 4xx→CONFIG 口径一致，勘误同批） |
| OAI idDoesNotExist | `gone` | 单 id 查询场景（--all-versions deferred，本期低频） |

**已知冻结限制（本期承认，收紧随 Phase 4 走接口仲裁）**：①`FetchResult` 无 `http_status` 字段，`fetch_log.http_status` 本期恒 NULL；②metadata 阶段调用（OAI/Query）不入 FetchLog——其限速审计证据为 obslog jsonl（HttpClient 每请求 debug 事件：domain/url 脱敏/status/elapsed_ms）；③`Retry-After` 不驱动重试调度（仅观测）。

### 网络层需求（Phase 2 共享 `HttpClient`，见 phase2-implementation-plan §2.1 冻结件）

流式 GET→`Iterator[bytes]`（喂 `FetchIO.write_stream`）；缓冲 GET→文本/字节（Atom/OAI XML 解析输入）；3xx 跟随（OAI 域 2025-03 曾 301 迁移）+ obslog 事件；UA 注入与 Retry-After 读取；超时/连接错→`transient`；状态码→ErrorClass 映射。**属 adapter 自身职责**：XML/Atom 解析、ID 两代解析、月度桶窗口构造。**不归 adapter**：限速（pipeline `acquire_and_wait` 依 `default_rate` 强制）、`%PDF` 校验（pipeline）、落盘（FetchIO）。

## 6. Fixtures 与测试

- **T1 单元**：ID 两代解析/构造/归一矩阵（新旧格式 × 版本后缀 × 非法形态拒绝）；月度桶生成边界（inception 起点、当月未满、跨月）；Atom/OAI 解析器（与网络解耦，bytes 进中间记录出）。
- **T3 fixture 八件套**（覆盖 §5 全部 error_class，test-plan §6 强制）：
  ①Query API Atom 正常页（10 条，**其中混 1 条老格式 ID entry** 保证两代 ID 端到端）；②OAI ListRecords 正常页（含 resumptionToken）；③空结果 Atom（totalResults=0，边界正常态）；④Atom `totalResults>0` 但 entry 空 → `parse`（真实难录制则合成，PR 标注"合成 fixture"）；⑤withdrawn/gone 记录页（独立文件，不与③混同）；⑥HTTP 503 + Retry-After 快照 → `rate_limited`（**响应头随 body 一并落盘**，fixture 规范扩展）；⑦OAI badResumptionToken 错误 XML → `transient`；⑧Query API 400 offset 超限响应 → `config`。
- **T4 集成**：watch 当月桶重复 enumerate 去重（注入重叠窗口数据无重复入库）；**七收割日回放模拟**（含 announce 延迟场景：某日数据延至次日出现），断言 7 日累计无重复无遗漏（AC-2.3 离线证据层）。
- **T5 在线冒烟**（预算 ≤10 请求）：healthcheck 1 + 单桶 enumerate 首页 1 + 单篇 PDF fetch 1 + robots/ToU 复核（§4 ⚠ 项）；`cat:cs.LG` 当日增量结构核对。
- **canary 样本（抗 flake 加固）**：**3 个跨域固定 id 带版本号**（cs.LG / econ.* / q-fin.* 各 1，如 `2401.xxxxx v1`），比对**空白规整化 title + primary_category** 双字段（不做原串精确匹配——Atom title 跨行折行、作者改标题均不应误报 DRIFT）；附 `cat:cs.LG` 单日计数 >0。
- **AC-2.3 验收证据分层（D-018）**：①T4 七日回放（CI 化，机制正确性）＋②T5 单次在线冒烟（真实解析入库）＝ **Phase 2 判定依据**；③真实连续 7 自然日 watch + 第 7 天抽样 20 篇对官方 listing 人工比对 ＝ **T6 runbook**，随 Phase 6 AC-6.1 联合执行，结果记 `testing/records/`。口径拆分公开于 D-018，不静默弱化 AC 字面。
- **验收关联**：AC-2.3、AC-6.1/6.4；测试类型定义见 [testing/test-plan.md](../../testing/test-plan.md)。

## 7. 风险与维护

- OAI-PMH 域名 2025-03 已迁移一次（旧域 301）——client 跟随重定向并在 canary 监控 301 链变化；
- Kaggle 数据集 schema 偶有列变动：bulk 导入器（deferred）实现时做 schema 校验，失败即 `parse` 并提示锁定旧版本数据集；
- S3 全量 PDF 属付费重型操作：默认关闭，启用需显式配置 + 费用预估提示（按 S3 manifest 大小 × 现行 requester-pays 费率估算，文档化在 CLI help）。
