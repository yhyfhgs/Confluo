# 文档索引（唯一权威清单）

> 本表是 main 上全部文档的单一事实来源：新增、改名或废弃文档时，在同一提交内更新本表。status 取值与流转见 [process/status-workflow.md](process/status-workflow.md)。
> **最后盘点：2026-09-27（v2 重新开始）**：main 只保留 v2 的调研、计划与 demo，均为 draft、待评审；v1 的实现与文档已归档到分支 `archive/v1`（标签 `v1-final`），路径索引见 [archive-v1.md](archive-v1.md)。

## 按意图导航

| 你想… | 阅读路径 |
|---|---|
| 5 分钟了解 v2 | [plan/v2/README](plan/v2/README.md) → [简报](plan/v2/00-design-brief.md) → [demo](plan/v2/demo/paper-feed-demo.html) |
| 看调研证据 | [survey/README](survey/README.md) → [调研综合](survey/00-survey-synthesis.md) → 各主题 |
| 看支持哪些来源 | [catalog/source-directory](catalog/source-directory.md) → [plan/v2/03](plan/v2/03-sources-and-corpus-pipeline.md) |
| 理解检索、路由与 TSRG | [plan/v2/04](plan/v2/04-retrieval-and-routing.md) → [图 v2-04](diagrams/v2-04-tsrg.svg) |
| 理解推荐与双向匹配 | [plan/v2/06](plan/v2/06-recommendation-and-matching.md) → [图 v2-07](diagrams/v2-07-rec-pipeline.svg)、[图 v2-08](diagrams/v2-08-bidirectional-matching.svg) |
| 理解合规边界 | [plan/v2/08](plan/v2/08-compliance-security-privacy.md) → [图 v2-10](diagrams/v2-10-data-boundaries.svg) |
| 开始实施（V0） | [plan/v2/09 路线图](plan/v2/09-roadmap-and-milestones.md) → [adr-proposals](plan/v2/adr-proposals.md) |
| 查"为什么这样设计" | [plan/decision-log.md](plan/decision-log.md)（D-001…D-039 为 v1 历史；D-040…D-071 为 v2 proposed） |
| 查 v1 的某个文件 | [archive-v1.md](archive-v1.md) |

## 根文档

| 路径 | 标题 | status | updated |
|---|---|---|---|
| [../README.md](../README.md) | 项目总览（v2 重新开始） | — | 2026-09-27 |
| [../AGENTS.md](../AGENTS.md) | AI/LLM 协作者工作规范 | — | 2026-09-27 |
| [GLOSSARY.md](GLOSSARY.md) | 术语表（Glossary） | draft | 2026-09-27 |
| [archive-v1.md](archive-v1.md) | v1 归档说明与路径索引 | approved | 2026-09-27 |

## plan/ — 计划与决策

| 路径 | 标题 | status | updated |
|---|---|---|---|
| [plan/progress.md](plan/progress.md) | 项目进度跟踪 | approved | 2026-09-27 |
| [plan/decision-log.md](plan/decision-log.md) | 架构决策记录（ADR） | approved | 2026-09-27 |

## plan/v2/ — v2 设计与实施计划包

| 路径 | 标题 | status | updated |
|---|---|---|---|
| [plan/v2/README.md](plan/v2/README.md) | v2 重新设计计划包（入口） | draft | 2026-09-27 |
| [plan/v2/00-design-brief.md](plan/v2/00-design-brief.md) | v2 设计决策简报（主 agent 架构裁决） | draft | 2026-09-27 |
| [plan/v2/01-vision-and-requirements.md](plan/v2/01-vision-and-requirements.md) | v2 愿景、用户场景与需求规格 | draft | 2026-09-27 |
| [plan/v2/02-architecture.md](plan/v2/02-architecture.md) | v2 总体架构 | draft | 2026-09-27 |
| [plan/v2/03-sources-and-corpus-pipeline.md](plan/v2/03-sources-and-corpus-pipeline.md) | 来源接入与语料流水线（SourceSpec v2 / Connector / 策略引擎） | draft | 2026-09-27 |
| [plan/v2/04-retrieval-and-routing.md](plan/v2/04-retrieval-and-routing.md) | 检索、路由与 TSRG 索引（查询 / 最新 / 筛选 / 多来源 / 组合） | draft | 2026-09-27 |
| [plan/v2/05-data-platform.md](plan/v2/05-data-platform.md) | 多用户数据平台与数据库设计 | draft | 2026-09-27 |
| [plan/v2/06-recommendation-and-matching.md](plan/v2/06-recommendation-and-matching.md) | 推荐、反馈学习与双向匹配 | draft | 2026-09-27 |
| [plan/v2/07-frontend-interaction.md](plan/v2/07-frontend-interaction.md) | 前端交互与视觉规范（论文卡片流） | draft | 2026-09-27 |
| [plan/v2/08-compliance-security-privacy.md](plan/v2/08-compliance-security-privacy.md) | 合规、隐私、安全与内容治理 | draft | 2026-09-27 |
| [plan/v2/09-roadmap-and-milestones.md](plan/v2/09-roadmap-and-milestones.md) | v2 实施路线图与里程碑 | draft | 2026-09-27 |
| [plan/v2/adr-proposals.md](plan/v2/adr-proposals.md) | v2 ADR 草案（proposed） | draft | 2026-09-27 |
| [plan/v2/design-process-record.md](plan/v2/design-process-record.md) | v2 设计过程记录 | draft | 2026-09-27 |
| [plan/v2/demo/paper-feed-demo.html](plan/v2/demo/paper-feed-demo.html) | 卡片流交互 demo + 视觉案例（HTML；已发布为 Artifact） | — | 2026-09-27 |
| plan/v2/design-process-record/ | 设计过程附件（首轮 agent 结构化返回 JSON） | — | 2026-09-27 |

## catalog/ — 来源名录

| 路径 | 标题 | status | updated |
|---|---|---|---|
| [catalog/source-directory.md](catalog/source-directory.md) | v2 来源支持名录（Source Directory） | draft | 2026-09-27 |

## survey/ — v2 调研归档（2026-09-26，14 个主题并行调研 + 逐篇对抗核验）

> 各篇的同名子目录存放可复测的原始数据附件（请求台账、实测统计、仓库指标）。

| 路径 | 标题 | status | updated |
|---|---|---|---|
| [survey/README.md](survey/README.md) | Survey 目录：v2 重新设计调研归档 | draft | 2026-09-26 |
| [survey/00-survey-synthesis.md](survey/00-survey-synthesis.md) | 调研综合：v2 重新设计的输入与结论 | draft | 2026-09-26 |
| [survey/sources/natural-sciences.md](survey/sources/natural-sciences.md) | 来源调研：理科（数学/物理/化学）出版商、预印本与平台 | draft | 2026-09-26 |
| [survey/sources/life-sciences-psychology.md](survey/sources/life-sciences-psychology.md) | 来源调研：生命科学与心理学出版商、预印本与平台 | draft | 2026-09-26 |
| [survey/sources/social-sciences-econ-fin-mgmt.md](survey/sources/social-sciences-econ-fin-mgmt.md) | 来源调研：社科（经济/金融/商业/管理）出版商、工作论文与平台 | draft | 2026-09-26 |
| [survey/sources/cs-ai.md](survey/sources/cs-ai.md) | 来源调研：计算机与 AI 会议、期刊、预印本与平台 | draft | 2026-09-26 |
| [survey/sources/aggregators-repositories.md](survey/sources/aggregators-repositories.md) | 来源调研：二级来源——仓库与聚合平台 | draft | 2026-09-26 |
| [survey/oss/paper-acquisition-and-search-oss.md](survey/oss/paper-acquisition-and-search-oss.md) | 开源调研：论文获取、检索与学术搜索相关 GitHub 项目 | draft | 2026-09-26 |
| [survey/oss/recommendation-oss.md](survey/oss/recommendation-oss.md) | 开源调研：推荐系统与学术推荐相关 GitHub 项目 | draft | 2026-09-26 |
| [survey/market/startups-and-products.md](survey/market/startups-and-products.md) | 市场调研：学术发现与论文推荐相关初创与产品 | draft | 2026-09-26 |
| [survey/algorithms/social-media-recsys.md](survey/algorithms/social-media-recsys.md) | 算法调研：抖音/TikTok、小红书、X、快手、Meta 等社媒推荐核心算法 | draft | 2026-09-26 |
| [survey/algorithms/scholarly-recommendation-and-matching.md](survey/algorithms/scholarly-recommendation-and-matching.md) | 算法调研：学术论文推荐、用户兴趣建模与双向匹配 | draft | 2026-09-26 |
| [survey/algorithms/retrieval-routing-indexing.md](survey/algorithms/retrieval-routing-indexing.md) | 算法与架构调研：多源检索、路由、索引结构与多用户数据平台 | draft | 2026-09-26 |
| [survey/algorithms/paper-understanding-and-card-content.md](survey/algorithms/paper-understanding-and-card-content.md) | 技术调研：论文理解与卡片内容生成（TL;DR、关键图、翻译、标签） | draft | 2026-09-26 |
| [survey/ux/card-feed-interaction.md](survey/ux/card-feed-interaction.md) | UX 调研：卡片流与滑动交互（抖音/小红书/Tinder 式）及实现技术 | draft | 2026-09-26 |
| [survey/compliance/multi-user-platform-compliance.md](survey/compliance/multi-user-platform-compliance.md) | 合规调研：从单用户本地工具到多用户平台的许可、ToS 与监管边界 | draft | 2026-09-26 |

## process/ — 流程规范（沿用 v1）

| 路径 | 标题 | status | updated |
|---|---|---|---|
| [process/git-workflow.md](process/git-workflow.md) | Git 工作流程规范 | approved | 2026-07-20 |
| [process/status-workflow.md](process/status-workflow.md) | 文档与代码状态流程 | approved | 2026-07-20 |
| [process/doc-conventions.md](process/doc-conventions.md) | 文档写作与目录规范 | approved | 2026-07-20 |

## diagrams/ — SVG 图（源文件即交付物）

| 文件 | 内容 | 对应文档 |
|---|---|---|
| [diagrams/06-status-machine.svg](diagrams/06-status-machine.svg) | 双状态机与联动（v1 沿用的流程图） | process/status-workflow |
| [diagrams/v2-01-architecture.svg](diagrams/v2-01-architecture.svg) | v2 分层组件与四个数据域 | plan/v2/02 |
| [diagrams/v2-02-dataflow.svg](diagrams/v2-02-dataflow.svg) | v2 主数据流与合规边界 | plan/v2/02 |
| [diagrams/v2-03-source-model.svg](diagrams/v2-03-source-model.svg) | Source / SourceChannel / Venue / Connector / Policy 关系 | plan/v2/03 |
| [diagrams/v2-04-tsrg.svg](diagrams/v2-04-tsrg.svg) | TSRG 主题-来源路由图及四种用途 | plan/v2/04 |
| [diagrams/v2-05-query-execution.svg](diagrams/v2-05-query-execution.svg) | Query AST 到并行联邦执行与合并 | plan/v2/04 |
| [diagrams/v2-06-data-domains.svg](diagrams/v2-06-data-domains.svg) | 四个数据域、主要表与 RLS 边界 | plan/v2/05 |
| [diagrams/v2-07-rec-pipeline.svg](diagrams/v2-07-rec-pipeline.svg) | 推荐管线与学习闭环 | plan/v2/06 |
| [diagrams/v2-08-bidirectional-matching.svg](diagrams/v2-08-bidirectional-matching.svg) | 三层双向匹配 | plan/v2/06 |
| [diagrams/v2-09-card-anatomy.svg](diagrams/v2-09-card-anatomy.svg) | 论文卡片解剖 | plan/v2/07 |
| [diagrams/v2-10-data-boundaries.svg](diagrams/v2-10-data-boundaries.svg) | 共享、私有、用户侧与上游之间的数据流与禁止路径 | plan/v2/08 |

## logs/ · reports/ — 留痕（无 front matter 义务）

| 路径 | 内容 |
|---|---|
| [logs/2026-09-27-session-011.md](logs/2026-09-27-session-011.md) | v2 调研与设计 session（含 v1 归档与 main 清理的追加记录）。v1 的 session 001–010 与阶段报告见 [archive-v1](archive-v1.md) |
| reports/ | v2 里程碑报告（待 V0 起产生） |
