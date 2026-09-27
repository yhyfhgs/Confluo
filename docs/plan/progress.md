---
title: 项目进度跟踪
status: approved
owner: opus5.5-primary
updated: 2026-09-27
---

# 项目进度

> 本文件是"当前状态"的单一事实来源，每次工作 session 结束时更新。细节见 `docs/logs/`，阶段总结见 `docs/reports/`。

## 当前快照（2026-09-27）

- **阶段**：v2 重新开始，**调研与设计计划已完成，待用户评审**。main 上没有实现代码。
- **已有**：
  - [docs/survey/](../survey/README.md)：14 个主题的调研，逐篇对抗核验，另有一篇综合；
  - [plan/v2/](v2/README.md)：简报与三轮裁决、01–08 设计、09 路线图、32 条 ADR 草案 D-040…D-071、设计过程记录、交互 demo；
  - [支持名录](../catalog/source-directory.md)：187 条；
  - 10 张 v2 配图。
- **v1**：Phase 0–7 与 2026-07 审计修复已完成，完整归档在分支 `archive/v1`（标签 `v1-final`），见 [archive-v1](../archive-v1.md)。v1 的 ADR D-001…D-039 保留在 [decision-log](decision-log.md) 中作为历史，由 v2 ADR 点名修订或取代。
- **待用户决定**：
  - Q1 是否商业化；
  - Q2 是否面向中国大陆公众运营；
  - Q3 是否购买付费数据档；
  - Q4 robots 规则与官方 API 冲突时的处置（D-049）；
  - T1 是否配 GPU；
  - 32 条 ADR 逐条确认；
  - 用户之声调研与可用性测试的时点。

  详见 [v2 README](v2/README.md) §4 与 [简报](v2/00-design-brief.md) §12。
- **阻塞**：无。法务结论与外部书面确认（NCBI、EMBL-EBI、OpenReview）是 V0/V1 的外部依赖。

## 里程碑进度板（v2）

| 里程碑 | 内容 | 状态 |
|---|---|---|
| 设计阶段 | 调研、设计、路线图、demo | **done（待评审）** |
| V0 | 基线：ADR 与设计定稿、书面确认发函、工程底座、PG 骨架、策略引擎与出站网关骨架 | planned |
| V1 | 语料底座与 P0 来源 | planned |
| V2 | 检索与 TSRG | planned |
| V3 | 多用户平台 | planned |
| V4 | 推荐 R0 与 Feed API | planned |
| V5 | 前端 PWA 与可用性（v2.0 公开内测） | planned |
| V6 | 社交、双向匹配与推荐 R1（v2.1） | planned |
| V7 | 规模化与加固（v2.2） | planned |

里程碑内容、任务卡与验收标准见 [09 路线图](v2/09-roadmap-and-milestones.md)。

## 下一步

1. 用户评审 v2 计划包与 demo，确认 ADR 与 Q1–Q7。
2. 启动 V0：把简报 §11 回填进各设计文档，发出书面确认函，建立工程底座，并把代码目录与命令写入 `AGENTS.md`。
