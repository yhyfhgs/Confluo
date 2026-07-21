---
title: 项目进度跟踪
status: approved
owner: fable5
updated: 2026-07-21
---

# 项目进度

> 本文件是"当前状态"的单一事实来源。每次工作 session 结束时更新。
> 历史细节见 `docs/logs/`；阶段总结见 `docs/reports/`。

## 当前快照（2026-07-21）

- **当前 Phase**：2 **进行中**。**arxiv adapter 整链完成并验收**（T1-T7 全合并，AC-2.3 双层 PASS 见[验收记录](../testing/records/2026-07-22-arxiv-acceptance.md)，arxiv.md 转 implemented；首次真网冒烟 7 请求全程合规）。Stage A 地基 + 31 个 arxiv venue + socket 禁网护栏就位。
- **Stage B 门禁全清**（6/6 approved：openreview/pmlr/cvf/acl/neurips/aaai——各经 LIVE 勘察→重写→复审；acm_dl 红线出列 D-020、AC-2.6 deferred）；实现滚动开闸：openreview（AC-2.1/2.2）先行 + pmlr 并行。
- **总体进度**：Phase 0/1 = 100%；Phase 2 ≈ 55%（main 822 测试 / 覆盖率 99.31%）。新 ADR：D-018/D-019/D-020。
- **待用户执行**：①OpenReview 免费账号 token（openreview 在线验收前提，config.toml [auth.openreview]）；②外部 API 申请（Elsevier/S2/Kaggle，Phase 3/4 前）。
- **阻塞**：无

## Phase 进度板

| Phase | 状态 | 进度 | 备注 |
|---|---|---|---|
| 0 设计与文本系统 | done | 100% | 报告：reports/2026-07-20-phase0-report.md |
| 1 核心框架 | **done** | 100% | 报告：reports/2026-07-21-phase1-report.md；tag phase-1 + schema-v1 |
| 2 Open-Access MVP | **in_progress** | W0 完成 | 实施计划 approved；arxiv 详设 approved；T1/T2 开发中 |
| 3 聚合元数据层 | planned | 0% | |
| 4 认证框架+出版社 | planned | 0% | |
| 5 SSRN 与特殊源 | planned | 0% | |
| 6 订阅与搜索 | planned | 0% | |
| 7 全文抽取与库增强 | planned | 0% | |

## 模块状态表（status-workflow §4，实现阶段增设）

| 模块 | 状态 | 覆盖 | 备注 |
|---|---|---|---|
| errors / types / adapter / config（T1） | stable | 100% | 接口冻结件 |
| storage（db/migrations/repo，T2） | stable | 100% | schema v1；tag schema-v1 |
| registry + venues YAML（T3） | stable | 100% | lint 七类校验 |
| ratelimit / obslog（T4） | stable | 100% | redact 含引号/嵌套形态 |
| tasks 队列与状态机（T5） | stable | 100% | 7 合法转移 + recover_running |
| mock_platform + 契约/golden 基建（T6） | stable | 100% | 确定性语料 + 故障注入 |
| pipeline（fetchio/report/stages/runner，T7a-c） | stable | 96-100% | re-resolve、整批 BLOCKED、串行 drain |
| verify + dbdump（T8a） | stable | 100% | AC-1.3 口径可执行定义 |
| cli（T8b） | stable | 99% | 退出码 0/1/2/3 契约 |
| AC-1 验收测试（T9） | stable | — | 六条 AC 全部自动化 |

## Session 记录索引

| 日期 | 日志 | 主要产出 |
|---|---|---|
| 2026-07-20 | [logs/2026-07-20-session-001.md](../logs/2026-07-20-session-001.md) | 文本系统建立；核心设计 00–09；plan/testing/process；catalog 6 篇；调研 5 篇（日志为 002 补记） |
| 2026-07-20 | [logs/2026-07-20-session-002.md](../logs/2026-07-20-session-002.md) | 6 SVG；16 篇 adapter 详设；catalog 补 2 篇；出版社/同类项目调研 4 篇归档；INDEX；Phase-0 报告；git 初始提交 |
| 2026-07-20 | [logs/2026-07-20-session-003.md](../logs/2026-07-20-session-003.md) | 一致性审查第 1 轮：需求矩阵 17/17；13 项修复（D-015） |
| 2026-07-21 | [logs/2026-07-21-session-004.md](../logs/2026-07-21-session-004.md) | 深度审计第 2 轮：10 项修复；GLOSSARY+INDEX 导航+FR→AC 映射表（D-016） |
| 2026-07-21 | [logs/2026-07-21-session-005.md](../logs/2026-07-21-session-005.md) | **Phase 1 全程**：实施计划+D-017；多 agent 并行开发 10 任务（fable/opus/sonnet 分档）；10 轮审查+终审；AC-1 全过；文档 implemented；tag phase-1/schema-v1 |
