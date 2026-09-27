---
title: 架构决策记录（ADR）
status: approved
owner: opus5.5-primary
updated: 2026-09-27
---

# 架构决策记录（Decision Log / ADR）

> **2026-09-27 v2 重新开始**：v1 实现与文档已归档到分支 `archive/v1`（标签 `v1-final`）。v1 决策 D-001…D-039 的正文同样只在该分支上，本文只保留它们的编号索引；v2 草案 D-040…D-071 见文末登记节。
> 格式：每条决策一节，编号 D-NNN 单调递增，永不复用。推翻旧决策时新增一条并注明 `supersedes: D-XXX`，旧条目标注 `superseded-by`。
> 状态：`accepted`（生效）/ `proposed`（待定）/ `superseded`（被取代）。

---

## v1 决策索引（D-001…D-039）

- 正文、依据与 v1 内的修订关系见 `archive/v1` 上的 [decision-log](../archive-v1.md#docs-plan-decision-log-md)：`git show archive/v1:docs/plan/decision-log.md`。
- 这 39 条在 v1 中均为 `accepted`，继续约束 v1 实现。它们在 v2 中继承、修订、取代还是不适用，由 D-040（proposed，全文见 [adr-proposals](v2/adr-proposals.md)）逐条列明。D-040 起的 ADR 经用户确认后，在下表对应行标注 `superseded-by` 或 `revised-by`（限定"在 v2 中"）。

| 编号 | 标题 | 日期 |
|---|---|---|
| D-001 | 目标技术栈假设：Python 3.12+ / httpx / Playwright / SQLite→PostgreSQL | 2026-07-20 |
| D-002 | 可插拔核心：Platform Adapter × Venue Spec 两层结构 | 2026-07-20 |
| D-003 | 双模块划分：open_access 与 auth_gated 共享同一 Adapter 协议 | 2026-07-20 |
| D-004 | 六阶段 Pipeline：discover → enumerate → resolve → fetch → extract → ingest | 2026-07-20 |
| D-005 | 元数据主干走聚合 API，官网站点只做全文与补充 | 2026-07-20 |
| D-006 | 认证设计：人在回路首次登录 + storage_state 复用 + 绝不对抗风控 | 2026-07-20 |
| D-007 | 跨源同文合并：Identifier 图 + preprint_of 关系 | 2026-07-20 |
| D-008 | 文本系统：docs-as-code + front matter 状态机 + INDEX 单一索引 | 2026-07-20 |
| D-009 | Git 流程：trunk-based 轻量变体，设计阶段直提 main，实现阶段强制分支 | 2026-07-20 |
| D-010 | 双状态机：文档 status 与模块 dev-status 联动 | 2026-07-20 |
| D-011 | SSRN 定位：预印本主源之一，匿名+免费账号双模式，严格限速 | 2026-07-20 |
| D-012 | 会议历年网址漂移：VenueEra 表 + DBLP 为历史主干 + 年度探测任务 | 2026-07-20 |
| D-013 | ACM DL 按 2026 全面 OA 新政归入 open_access 族 | 2026-07-20 |
| D-014 | 尊重站点 AI-bot 指令：诚实 UA + robots/Content-Signal 遵守 + 敏感站白名单式抓取 | 2026-07-20 |
| D-015 | Phase-0 收官一致性审查的三项设计修正 | 2026-07-20 |
| D-016 | 第二轮深度审计：可追溯性与可读性增强批次 | 2026-07-21 |
| D-017 | Phase 1 工具链与包布局 | 2026-07-21 |
| D-018 | AC-2.3（arXiv 订阅 7 日增量）验收证据分层 | 2026-07-21 |
| D-019 | 外源比对类验收的锚点快照模式（AC-2.1 首例） | 2026-07-22 |
| D-020 | acm_dl 自动全文抓取 Phase 2 出列（红线优先），Phase 4 重评 | 2026-07-22 |
| D-021 | Phase 3 开工勘察增量复核：DBLP robots 合规修正与聚合层口径定稿 | 2026-07-22 |
| D-022 | 零网络 resolve 豁免限速闸 + --limit 前置圈选（C-C 修复语义定案） | 2026-07-22 |
| D-023 | 认证凭证库加密方案：cryptography>=42 AES-GCM 作 [auth] optional extra | 2026-07-23 |
| D-024 | Phase 4 R0 平台勘察裁决：wiley 纳入（token 门控）+ acm_dl 维持出列（全文改道 unpaywall） | 2026-07-23 |
| D-025 | config 归集：仓库内 config/ 规范文件夹 + 分层加载链 + 敏感边界护栏 | 2026-07-23 |
| D-026 | dblp robots 路径级读法：同后缀通配词按最长匹配前缀判定（ADR 化） | 2026-07-24 |
| D-027 | RePEc Phase 5 出列：降级为 enrich 通道候选（挂 Phase 6 DSL 富化评估） | 2026-07-24 |
| D-028 | ECMA（Econometrica）年代分段路由：10.3982 归 Econometric Society，裸前缀路由 wiley 作废 | 2026-07-24 |
| D-029 | SSRN 定位修订：聚合元数据主路径确立 + 浏览器全文降 opt-in（修订 D-011 定位） | 2026-07-24 |
| D-030 | Browser-Fetch 横切件形态定稿（案 A）+ CF-403 挑战判定契约演进（S-c）+ 冷却键粒度修复（E-1） | 2026-07-26 |
| D-031 | 弱信号候审匹配键改为观测级键集合（新表 paper_weak_key）+ 同级 tie-break 复合序 | 2026-07-26 |
| D-032 | config-home 迁入仓库根 `.paper-crawler/`（env 主指向；凭证红线表述收窄） | 2026-07-26 |
| D-033 | 全文抽取（stage 5 extract）语义定稿：pypdf 基线 + GROBID 可选增强 + asset 级幂等键全序取 max | 2026-07-27 |
| D-034 | FTS5 检索索引形态：content-owning `paper_fts`（title+abstract）+ 触发器同步 + `0005` 方言隔离迁移（修订 D-017 决策 4 的兑现 Phase） | 2026-07-27 |
| D-035 | repec 接入形态：`_ENRICH_SOURCES` 元组扩位 + `SOURCE_PRIORITY` 七位重编号（修订 D-021 决策 3）+ `state/repec/` bulk 快照契约 + 零网络 `enrich_batch` | 2026-07-27 |
| D-036 | repec DOI↔handle 映射收窄为 w-only + `search` 聚合展示与 `list` 统一（T20 审计修复批） | 2026-07-27 |
| D-037 | dblp adapter 出列生产链（保留代码与测试） | 2026-07-29 |
| D-038 | design/08 venue-tracking 整域 defer（Phase 8 候选） | 2026-07-29 |
| D-039 | 任务优先级队列 + `crawler backfill` 命令 defer | 2026-07-29 |

---

## v2 重新设计 ADR 草案登记（D-040…D-071，proposed）

- 状态：proposed · 日期：2026-09-27 · 全文：[plan/v2/adr-proposals.md](v2/adr-proposals.md)（背景、决策、理由、影响，以及 supersedes/修订的旧 ADR 逐条写明）
- 说明：v2 重新设计阶段（调研见 [docs/survey/](../survey/README.md)，设计见 [plan/v2/](v2/README.md)）起草了以下 32 条 ADR。本节在决策日志中**预留编号**并登记状态，防止与其他工作冲突；全文只维护在草案文件中。每条经用户确认后，按本日志格式把全文移入本文件、状态改为 `accepted`，并在被取代或修订的旧条目上标注 `superseded-by` / `revised-by`。在此之前，D-001…D-039 对 v1 继续有效。
- 主 agent 的第 2、3 轮设计裁决（[简报](v2/00-design-brief.md) §10、§11）中需要 ADR 的条目已并入下表各条。

| 编号 | 标题 | 状态 |
|---|---|---|
| D-040 | v1 ADR 在 v2 中的适用范围（总则） | proposed |
| D-041 | 需求范围修订：Web UI 与多用户进入 v2，"不再分发"细化为数据三域与用户侧取回 | proposed |
| D-042 | v2 单栈 PostgreSQL 18、v1 维护冻结与一次性 ETL | proposed |
| D-043 | 数据四域、单向流、派生继承最严与共享索引资格 | proposed |
| D-044 | 依赖、模型与数据的许可门禁四级 | proposed |
| D-045 | 内容许可闸与商用开关 | proposed |
| D-046 | SourceSpec v2、Source 与 Venue 分离、ConnectorFamily 九族 | proposed |
| D-047 | 语料流水线六段（在 v2 中取代 D-004） | proposed |
| D-048 | 身份模型三层与版本边投票（修订 D-007 的表示） | proposed |
| D-049 | robots/ToS 统一规则：文档化 API 冲突、needs_confirmation、例外附表与漂移分档 | proposed |
| D-050 | dblp：停止在线访问，改用 DROPS 月度快照或 SPARQL | proposed |
| D-051 | SSRN：只取元数据与外链，删除浏览器 opt-in 全文 | proposed |
| D-052 | OpenReview 平台服务账号的使用边界 | proposed |
| D-053 | 受限全文的执行位置在用户侧 | proposed |
| D-054 | 用户级凭证与私有全文的端到端加密与多设备同步 | proposed |
| D-055 | Egress Gateway：唯一出口、五元组令牌桶、全局配额账本与三道舱壁 | proposed |
| D-056 | LLM 路由、AI 生成内容标识与数据出境 | proposed |
| D-057 | 地区单元与特性开关前置清单 | proposed |
| D-058 | TSRG：路由、调度、兴趣与反向推送的统一索引结构 | proposed |
| D-059 | Query AST v2 与用户频道取代 v1 订阅 DSL | proposed |
| D-060 | 检索索引选型（修订 D-034 决策 6） | proposed |
| D-061 | 推荐分阶段栈 R0→R1→R2 与 ValueModel 配置化 | proposed |
| D-062 | 事件契约、曝光绑定、ID 生成与公共信号准入 | proposed |
| D-063 | 新论文曝光下限：资格集合与全局预算 | proposed |
| D-064 | k 匿名阈值与差分隐私决策点 | proposed |
| D-065 | 研究者匹配的 opt-in 边界 | proposed |
| D-066 | 审计日志：HMAC 假名、哈希链、单写者与每日锚点 | proposed |
| D-067 | 数据权利实现与备份：导出、注销、加密粉碎与拉取式异地备份 | proposed |
| D-068 | API 契约：OpenAPI 3.1、URI 主版本与 SSE 流式语义 | proposed |
| D-069 | 事务性 outbox 与 PG 原生队列 | proposed |
| D-070 | 对象存储：ObjectStore 抽象，不选 MinIO | proposed |
| D-071 | GROBID 启用 `teiCoordinates=figure`（修订 D-033 与 design/12） | proposed |
