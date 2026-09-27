# 文档索引

> main 上全部文档的清单。新增、改名或删除文档时，在同一提交内更新本表。status 的取值与流转见 [AGENTS.md](../AGENTS.md)。
> **最后盘点：2026-09-27（精简）**：设计、名录与调研都换成了精简版；完整长稿在标签 `v2-drafts`，v1 在分支 `archive/v1`，读法见[归档说明](archive.md)。

## 先读

| 文档 | 内容 | status |
|---|---|---|
| [../README.md](../README.md) | 项目入口 | — |
| [plan/v2/README.md](plan/v2/README.md) | v2 方案总览：一篇看完方案与待你拍板的事 | draft |
| [plan/progress.md](plan/progress.md) | 当前进度与下一步 | approved |

## v2 设计（plan/v2/）

| 文档 | 内容 | status |
|---|---|---|
| [01-vision-and-requirements.md](plan/v2/01-vision-and-requirements.md) | 愿景与需求：用户、场景、需求分组、红线、北极星 | draft |
| [02-architecture.md](plan/v2/02-architecture.md) | 总体架构：组件、部署、数据流、出站网关、用户侧取回、API | draft |
| [03-sources-and-corpus-pipeline.md](plan/v2/03-sources-and-corpus-pipeline.md) | 来源接入与语料流水线 | draft |
| [04-retrieval-and-routing.md](plan/v2/04-retrieval-and-routing.md) | 检索、路由与 TSRG | draft |
| [05-data-platform.md](plan/v2/05-data-platform.md) | 多用户数据平台 | draft |
| [06-recommendation-and-matching.md](plan/v2/06-recommendation-and-matching.md) | 推荐、反馈学习与双向匹配 | draft |
| [07-frontend-interaction.md](plan/v2/07-frontend-interaction.md) | 前端交互与视觉 | draft |
| [08-compliance-security-privacy.md](plan/v2/08-compliance-security-privacy.md) | 合规、隐私与安全（含 HC-01…HC-32） | draft |
| [09-roadmap-and-milestones.md](plan/v2/09-roadmap-and-milestones.md) | 路线图与里程碑 V0–V7 | draft |
| [demo/paper-feed-demo.html](plan/v2/demo/paper-feed-demo.html) | 卡片流交互 demo 与视觉案例（已发布为 Artifact） | — |

## 查阅

| 文档 | 内容 | status |
|---|---|---|
| [catalog/source-directory.md](catalog/source-directory.md) | 来源支持名录（187 条） | draft |
| [survey/README.md](survey/README.md) | 调研结论 | draft |
| [plan/decision-log.md](plan/decision-log.md) | ADR 登记：v2 草案 D-040…D-071 与 v1 索引 | approved |
| [GLOSSARY.md](GLOSSARY.md) | 术语速查 | draft |
| [archive.md](archive.md) | 归档说明：v2 完整长稿与 v1 | approved |
| [../AGENTS.md](../AGENTS.md) | AI 协作者规范 | — |

## 配图（diagrams/）

| 图 | 内容 |
|---|---|
| [v2-01-architecture.svg](diagrams/v2-01-architecture.svg) | 分层组件与四个数据域 |
| [v2-02-dataflow.svg](diagrams/v2-02-dataflow.svg) | 主数据流与合规边界 |
| [v2-03-source-model.svg](diagrams/v2-03-source-model.svg) | Source、通道、Venue、连接器与策略引擎的关系 |
| [v2-04-tsrg.svg](diagrams/v2-04-tsrg.svg) | TSRG 主题-来源路由图及四种用途 |
| [v2-05-query-execution.svg](diagrams/v2-05-query-execution.svg) | 从 Query AST 到并行联邦执行与合并 |
| [v2-06-data-domains.svg](diagrams/v2-06-data-domains.svg) | 四个数据域、主要表与 RLS 边界 |
| [v2-07-rec-pipeline.svg](diagrams/v2-07-rec-pipeline.svg) | 推荐管线与学习闭环 |
| [v2-08-bidirectional-matching.svg](diagrams/v2-08-bidirectional-matching.svg) | 三层双向匹配 |
| [v2-09-card-anatomy.svg](diagrams/v2-09-card-anatomy.svg) | 论文卡片解剖 |
| [v2-10-data-boundaries.svg](diagrams/v2-10-data-boundaries.svg) | 共享、私有、用户侧与上游之间的数据流与禁止路径 |
| [v2-11-source-confluence.svg](diagrams/v2-11-source-confluence.svg) | 宣传概念图：一级、二级来源汇入统一语料 |

图注里的章节号指 `v2-drafts` 上的完整长稿。

## 工作日志（logs/）

| 日志 | 内容 |
|---|---|
| [2026-09-27-session-014.md](logs/2026-09-27-session-014.md) | 精简 docs，清理仓库与分支 |

更早的日志：设计阶段的 011–013 在标签 `v2-drafts`，v1 的 001–010 在分支 `archive/v1`。里程碑报告从 V0 起写入 `reports/`。
