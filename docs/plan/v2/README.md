---
title: v2 重新设计计划包（入口）
status: draft
owner: opus5.5-primary
updated: 2026-09-27
---

# Paper Crawler v2 重新设计计划包

> 本目录是 v2 重新设计的全部设计与计划文档。全部为 `draft`，**尚未经用户评审**，在此之前 v1 的设计文档与 ADR（D-001…D-039）继续有效。
> 调研过程与结论归档在 [docs/survey/](../../survey/README.md)；设计过程归档在 [design-process-record.md](design-process-record.md)。
> v1 的实现与设计文档已归档到分支 `archive/v1`（标签 `v1-final`），本仓库 main 只保留 v2 的调研、计划与 demo；文中指向 v1 文档的链接统一跳转到 [archive-v1.md](../../archive-v1.md)。

## 1. 一句话

面向研究者的跨学科论文发现平台。它从合法来源持续收割论文，用可解释、可学习的个性化推荐，把"今天值得看的论文"做成一叠有限的卡片，用户靠滑动分拣；用户自己的机构权限只用于本人在用户侧取回全文。

## 2. 用户五项需求 → 本计划的回答

| 需求 | 核心设计 | 主文档 |
|---|---|---|
| ① 自定义来源与支持名录 | Source 与 Venue 分离；SourceSpec v2 声明 metadata / latest / fulltext 三条来源通道及其合规证据；九个 ConnectorFamily 覆盖长尾（多数期刊零代码接入，由 Crossref 承接）；策略引擎与漂移探针。名录共 187 条（v2-P0 36、P1 63、P2 44，另有仅元数据、仅外链、仅用户导入与 13 条排除项），覆盖数理化、生命科学、心理学、经济、金融、商业管理、CS/AI 与二级仓库和聚合平台 | [03](03-sources-and-corpus-pipeline.md)、[名录](../../catalog/source-directory.md) |
| ② 检索、路由与多用户数据库 | "先收割、后联邦"；统一 Query AST 支持五种意图（LOOKUP/SEARCH/SIMILAR/LATEST/EXPAND）与组合查询；**主题-来源路由图 TSRG** 以 OpenAlex 四级主题树为骨架，同时服务查询路由、收割调度、兴趣建模与论文→读者反向推送；预算贪心选源 + 健全放宽 + 并行联邦执行；PostgreSQL 18 四个数据域，用户私有层全表 RLS | [04](04-retrieval-and-routing.md)、[05](05-data-platform.md) |
| ③ 推荐、反馈与双向匹配 | 借鉴 X 开源的 Candidate Pipeline 与抖音/X 的价值模型 Σ V·P̂，但北极星是"有价值阅读"而非时长；R0 起步用"共享论文嵌入 + 每用户逻辑回归"（Scholar Inbox 配方）与主动学习冷启动；新论文贝叶斯分级曝光；双向匹配分三层（读者↔论文、论文→读者、研究者↔研究者 opt-in）；打分、点赞、收藏、私人笔记先行，公开评论在 V6 | [06](06-recommendation-and-matching.md) |
| ④ 卡片流前端 | 今日分拣 Deck + 收藏库瀑布流 + 详情 Sheet 三件套，只有 3 个一级入口；→ 想读、← 不感兴趣、↑ 跳过、↓ 撤回；投影判定与显式弹簧参数；每日有限批次，看完就结束 | [07](07-frontend-interaction.md)、[demo](demo/paper-feed-demo.html) |
| ⑤ 开源与初创调研 | 14 个主题的调研经对抗核验后汇总，逐条进入设计输入（SI-01…SI-70）与合规硬约束（HC-01…HC-28） | [docs/survey/](../../survey/README.md) |

**交互 demo 与视觉案例**：[demo/paper-feed-demo.html](demo/paper-feed-demo.html)（已发布为 claude.ai Artifact：<https://claude.ai/artifact/YYZiiZjCVVeTzbESeFxqQr>）。使用 24 篇真实 arXiv 论文与 4 篇 Crossref 期刊论文；包含评审调参面板、实时事件日志与 14 组视觉案例。

## 3. 阅读顺序与文档清单

| # | 文档 | 内容 | 状态 |
|---|---|---|---|
| 00 | [00-design-brief.md](00-design-brief.md) | 主 agent 的架构裁决：原则 P-01…P-09、术语、子系统裁决，以及第 2、3 轮裁决（§10 R2-01…R2-50、§11 R3-01…R3-22）与待确认事项（§12） | draft |
| 01 | [01-vision-and-requirements.md](01-vision-and-requirements.md) | 愿景、11 类用户画像、32 个场景、FR-17…FR-87、NFR-9…NFR-27、成功指标、术语登记 | draft |
| 02 | [02-architecture.md](02-architecture.md) | 组件、部署形态（platform/personal）、API 面、出站网关、v1 模块复用映射、许可白名单 | draft |
| 03 | [03-sources-and-corpus-pipeline.md](03-sources-and-corpus-pipeline.md) | SourceSpec v2、SCD、ConnectorFamily、策略引擎、分学科接入计划、语料流水线、用户侧全文取回 | draft |
| — | [../../catalog/source-directory.md](../../catalog/source-directory.md) | **支持名录**：187 条来源的逐行状态、通道、门控与证据；分学科覆盖统计；代表性 venue 索引 | draft |
| 04 | [04-retrieval-and-routing.md](04-retrieval-and-routing.md) | Query AST、TSRG、路由算法与近似保证、健全放宽、并行联邦执行器、本地混合检索、新鲜度调度、Percolator、稳定性工程、评测 | draft |
| 05 | [05-data-platform.md](05-data-platform.md) | 四个数据域的 DDL（设计伪代码）、RLS、事件分区与留存、对象存储、端到端加密凭证、数据权利、v1→v2 ETL | draft |
| 06 | [06-recommendation-and-matching.md](06-recommendation-and-matching.md) | 社媒算法借鉴表、事件契约、用户模型、推荐管线、在线学习、冷启动、分级曝光、三层双向匹配、社交与评价、解释与控制、评测 | draft |
| 07 | [07-frontend-interaction.md](07-frontend-interaction.md) | 信息架构、手势与动效参数、卡片状态机与信息架构、详情 Sheet、可访问性、性能预算、design tokens、前端技术栈 | draft |
| 08 | [08-compliance-security-privacy.md](08-compliance-security-privacy.md) | HC 登记、许可闸、robots/ToS 统一政策、执行位置与凭证、隐私、算法治理、UGC 审核、威胁模型、法律待决问题 | draft |
| 09 | [09-roadmap-and-milestones.md](09-roadmap-and-milestones.md) | 里程碑 V0…V7、113 张任务卡（约 599 人日）、243 条正式验收标准、测试策略、迁移步骤、决策门、风险登记 | draft |
| — | [adr-proposals.md](adr-proposals.md) | 32 条 ADR 草案 D-040…D-071（proposed），已在 [decision-log](../decision-log.md) 登记预留 | draft |
| — | [design-process-record.md](design-process-record.md) | 设计过程归档：时间线、方法、逐篇评审发现与处理、审计、待裁决事项（附首轮 agent 结构化返回 JSON） | draft |

配图：[docs/diagrams/](../../diagrams/) 下 `v2-01`…`v2-10` 十张 SVG。

## 4. 需要你决定的事

设计已按默认假设推进（简报 §8、§12），以下决定会改变范围或节奏：

1. **是否商业化**（Q1，默认否）与**是否面向中国大陆公众运营**（Q2，默认否）：决定许可口径、算法备案与数据出境要求。
2. **robots 与官方 API 文档冲突时的处置**（Q4）：默认保守，已细化为 D-049 草案；V1 开工前需要你确认。
3. **是否购买 OpenAlex / Crossref 付费档**（Q3，默认否）与 **T1 是否配 GPU 和自托管 LLM**（默认否）。
4. **32 条 ADR 草案**的逐条确认：V0 的第一张任务卡。
5. **用户之声调研与 demo 可用性测试**的时点：建议在 V1 之前做。

法务与外部书面确认事项见简报 §12。

## 5. 下一步

1. 你评审本计划包与 demo，逐条确认 ADR 与 Q1–Q7。
2. 按 09 路线图启动 V0：设计定稿（把简报 §11 回填进各文档）、发出书面确认函、v1 打 `v1-final` 标签后冻结、搭建 PG 骨架与出站网关骨架。
3. 通过评审的文档转 `review`/`approved`；V0 建立 v2 的 `docs/testing/acceptance-criteria.md`（以 09 §4 的 AC-V 为底），并把 01 §14 的术语并入 [GLOSSARY](../../GLOSSARY.md) 正式章节。
