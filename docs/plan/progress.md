---
title: 项目进度跟踪
status: approved
owner: opus5.5-primary
updated: 2026-09-30
---

# 项目进度

> "当前状态"的单一事实来源，每个工作 session 结束时更新。过程细节见 `docs/logs/`。

## 现状（更新至 2026-09-30）

- **项目名称与归属**：更名为 Confluo，仓库迁入 [ActionMesh AI](https://github.com/ActionMesh-AI/Confluo)；过程见 [session-017](../logs/2026-09-28-session-017.md)。
- **阶段**：v2 设计已完成，等你评审；main 上没有实现代码。
- **main 上的文档**（都是精简版）：
  - [v2 方案总览](v2/README.md)与 01–09 九篇设计；
  - [支持名录](../catalog/source-directory.md)（187 条）、[调研结论](../survey/README.md)、[ADR 登记](decision-log.md)（37 条草案待确认）；
  - 11 张配图与交互 demo。
- **来源分层与 venue 名录**（2026-09-27 新增，draft）：[来源七类分层与现状总表](../catalog/source-taxonomy.md)、[候选来源](../catalog/source-candidates.md)（156 个）、[评级体系](../catalog/venue-rankings.md)（45 个）、[按学科的 venue 名录](../catalog/venues/README.md)（866 个）；支持名录按七类分节，ADR 草案增至 33 条（新增 D-072）。
- **支持分级**（2026-09-29，draft）：来源分支持 134、登记 35、不接入 18，M2 与 L2 的非排除行全部支持；venue 分核心 305、登记 561，子领域由 141 个归并为 66 个；长尾靠问卷与用户关注逐步升级。汇总表见[支持名录 Excel](../catalog/source-support-catalog.xlsx)，ADR 草案增至 34 条（新增 D-073）。
- **连接器标准化计划与接口增量 UI**（2026-09-30，draft，待评审）：连接器接口契约 v1、一致性等级 CL0–CL3/CLX 与测试规范、卡片模板、九族规范与逐连接器卡片、实施计划（波次 W0–W4）、接口相关增量 UI 设计与交互 demo，以及[来源 × 连接器矩阵](../catalog/connector-matrix.md)；总览见[连接器工作总览](v2/connectors/README.md)，过程见 [session-018](../logs/2026-09-30-session-018.md)。ADR 草案增至 37 条（新增 D-074…D-076）。
- **归档**：完整长稿在标签 `v2-drafts`，v1 的实现与文档在分支 `archive/v1`（标签 `v1-final`），见[归档说明](../archive.md)。
- **待你决定**：见 [v2 方案总览](v2/README.md)的"待你拍板"一节，以及 37 条 ADR 草案；其中 D-073 支持分级与升级阈值、D-072 七类分层与评级标签的内置、导入口径（[评级体系](../catalog/venue-rankings.md)"平台怎么用"）是 2026-09-27 至 09-29 新增。连接器的 12 项待拍板（NBER 零自动化、ORCID 只用年度文件、RePEc 与 HAL 补 ⚑COMM、登记来源不运行连接器、CL2 生产口径、v1_bridge 退役时限、05 DDL 增补等）与 D-074…D-076 是 2026-09-30 新增，见[连接器工作总览](v2/connectors/README.md#待你拍板)。
- **阻塞**：无。书面确认（NCBI、EMBL-EBI、OpenReview）与法务结论是 V0、V1 的外部依赖。

## 里程碑

| 里程碑 | 内容 | 状态 |
|---|---|---|
| 设计阶段 | 调研、设计、路线图、demo | **done（待评审）** |
| V0 | 设计定稿、书面确认发函、工程底座、PG 骨架、策略引擎与出站网关骨架 | planned |
| V1 | 语料底座与 P0 来源 | planned |
| V2 | 检索与路由 | planned |
| V3 | 多用户平台 | planned |
| V4 | 推荐 R0 与 Feed API | planned |
| V5 | 前端 PWA 与可用性（v2.0 公开内测） | planned |
| V6 | 社交、双向匹配与推荐 R1（v2.1） | planned |
| V7 | 规模化与加固（v2.2） | planned |

各里程碑的交付与出口条件见 [09 路线图](v2/09-roadmap-and-milestones.md)。

## 下一步

1. 你评审总览与各分篇，逐条确认 ADR 草案与待拍板事项。
2. 启动 V0：把精简版设计推进到 approved，发出书面确认函，建立工程底座，并把代码目录与命令写入 `AGENTS.md`。
