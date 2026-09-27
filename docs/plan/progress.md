---
title: 项目进度跟踪
status: approved
owner: opus5.5-primary
updated: 2026-09-27
---

# 项目进度

> "当前状态"的单一事实来源，每个工作 session 结束时更新。过程细节见 `docs/logs/`。

## 现状（2026-09-27）

- **阶段**：v2 设计已完成，等你评审；main 上没有实现代码。
- **main 上的文档**（都是精简版）：
  - [v2 方案总览](v2/README.md)与 01–09 九篇设计；
  - [支持名录](../catalog/source-directory.md)（187 条）、[调研结论](../survey/README.md)、[ADR 登记](decision-log.md)（32 条草案待确认）；
  - 11 张配图与交互 demo。
- **归档**：完整长稿在标签 `v2-drafts`，v1 的实现与文档在分支 `archive/v1`（标签 `v1-final`），见[归档说明](../archive.md)。
- **待你决定**：见 [v2 方案总览](v2/README.md)的"待你拍板"一节，以及 32 条 ADR 草案。
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
