---
title: 项目进度跟踪
status: approved
owner: fable5
updated: 2026-07-23
---

# 项目进度

> 本文件是"当前状态"的单一事实来源。每次工作 session 结束时更新。
> 历史细节见 `docs/logs/`；阶段总结见 `docs/reports/`。

## 当前快照（2026-07-23）

- **当前 Phase**：3（聚合元数据层）**已完成**（2026-07-23，tag `phase-3` @ `35c79a6`）——合并引擎（AC-3.1/3.2/3.4）、verify 三类检出（AC-3.3）、五源 adapter（crossref/dblp/unpaywall + openalex/s2 enrich 通道）、`crawler enrich`/`oa-report` CLI、五刊 VenueSpec + AC-3.5 在线实跑双层 PASS（抽样年对账全部 diff=0）。验收：[Phase 3 汇总记录](../testing/records/2026-07-23-phase3-acceptance.md)（最终签署：**达成**）；报告：[phase3-report](../reports/2026-07-23-phase3-report.md)。终态门禁 **2154 passed / 24 skipped / 99.18%**（草稿期发现的 1 回归已于 `f114a09` 跟修）。→ 下一 Phase：4（认证框架+出版社），检查单见报告 §6（含终检增补）
- **Phase 2 遗留 C-C/C-D 已修复**：C-C（大 venue pull 可用性——零网络 resolve 豁免限速闸 + `--limit` 前置圈选，D-022，`eeef820`/`7d3424d`）、C-D（openreview venueid 异构缺陷——2018/2019 逐年 accepted 规则，`8cc2a75`/`3b9e332`/`45c8250`）均已合并；openreview AC-2.1/2.2 在线层随之转 PASS（用户 token 已配置并建立自动刷新脚本）。Phase 2 报告检查单 #1（用户 token）与终检增补置顶 C-C/C-D 两项均已清零。
- **待补验（不阻塞进行中状态，如实记录）**：S2 API key 未到（enrich/canary 在线层 SKIP 门控，D-021）；aaai_ojs 全库 OAI 补跑（Phase 2 检查单 #3 残项，本 Phase 未排期，仍缺）；AC-3.1/3.2/3.3/3.4 尚无独立汇总验收记录文档（现由 `tests/integration/test_merge_acceptance.py`/`test_merge_property.py`/`tests/unit/test_verify.py` 承载判据，T8 待收口成文）；D-019 锚点表 openalex 正锚点、s2 锚点仍 `[PENDING]`（需 key/credit）。
- **总体进度**：Phase 0/1/2 = 100%；Phase 3 T1-T7 完成 / T8 进行中（未打 tag）。新 ADR：D-021/D-022。
- **待用户执行**：①S2 API key 申请（`config.toml [auth.s2] api_key`，enrich/canary 在线层补验前提）；②`config.toml [identity].email` 补配（AC-3.5 验收记录 C5：默认 home 缺 email 会掉出 Crossref polite pool，本次经隔离 home 规避、非长期方案）；③外部 API 申请提醒沿用（Elsevier/Kaggle，Phase 4/5 前置）。
- **阻塞**：无

## Phase 进度板

| Phase | 状态 | 进度 | 备注 |
|---|---|---|---|
| 0 设计与文本系统 | done | 100% | 报告：reports/2026-07-20-phase0-report.md |
| 1 核心框架 | **done** | 100% | 报告：reports/2026-07-21-phase1-report.md；tag phase-1 + schema-v1 |
| 2 Open-Access MVP | **done** | 100% | 报告：reports/2026-07-22-phase2-report.md；tag phase-2；openreview 在线层已于 Phase 3 期间补验 PASS（用户 token 到位，见下） |
| 3 聚合元数据层 | **done** | 100%（tag phase-3） | 全部任务卡合并+汇总验收最终签署（AC-3 全 PASS/AC-0 全 PASS/预算零超支）；验收：testing/records/2026-07-23-phase3-acceptance.md |
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
| 2026-07-21/22 | [logs/2026-07-22-session-006.md](../logs/2026-07-22-session-006.md) | **Phase 2 全程**：W0 门禁+D-018/019/020；7 站 LIVE 勘察（~185 只读请求）；6 详设重写门禁；7 adapter 实现+审查+真实交叉验证；6 站在线冒烟实跑；终审放行；tag phase-2 |
