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
- **总体进度**：Phase 0/1/2/3 = 100%（Phase 4 M2b 债务清理复核时勘正：本行此前仍写
  "Phase 3 T8 进行中/未打 tag"，与本文件顶部快照及下方"Phase 进度板"表的"tag
  phase-3"状态自相矛盾——T8 收尾项已随 `35c79a6` 终验签署 + `tag phase-3` 完成，
  遗留细项移交 Phase 4，见报告 §6 检查单）。新 ADR：D-021/D-022。
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

> **2026-07-23 刷新**（Phase 4 M2b 检查单 #11）：下表按当前 `src/paper_crawler/` 的
> 包/模块结构重建，取代自 Phase 1 起未再更新、仍停留在 T1-T9 任务卡命名的旧表。
> "状态"列沿用 [status-workflow.md §2](../process/status-workflow.md#2-代码模块状态机实现阶段生效)
> 定义的代码模块状态机词汇（`planned/spec_approved/in_dev/testing/stable/deprecated`）
> ——与本表既有行保持同一套值域，不引入 `implemented`（该词在本仓库是**文档**状态机
> 用语，§1，不是代码模块状态机用语，二者刻意分离，见 §3 联动规则）。"覆盖"列为
> `make check`（`pytest --cov=paper_crawler --cov-report=term-missing`）本次亲跑的
> 实测行覆盖率（多文件聚合为一行时取 min–max 区间）；`storage/migrations/*.sql`
> 非 Python，不计入覆盖率统计。全量结果：**2186 collected / 2167 passed / 19
> skipped，TOTAL 99%（精确 99.18%，6418 stmts/26 miss）**，`make check` exit 0。

### 核心模块

| 模块 | 状态 | 覆盖 | 备注 |
|---|---|---|---|
| errors / types / adapter / useragent（接口冻结件） | stable | 100% | Capability/AuthLevel/AdapterBase 协议冻结；`adapter.py` 已退役死代码 `CrossrefStub`（检查单 #15d） |
| config / http / ratelimit / obslog | stable | 97–100% | `config.py` 97%/`http.py` 99%（缺口为防御性早失败分支）；`ratelimit.py`/`obslog.py` 100% |
| registry + venues YAML lint | stable | 100% | lint 七类校验；`crawler venues lint` 本次亲跑 45 个 venue 全过 |
| tasks（任务队列与状态机） | stable | 100% | 7 合法转移 + `recover_running` |
| storage（db / migrations / repo） | stable | 100% | schema v2（`0002_title_norm` 迁移，Phase 3 新增）；`db.py`/`repo.py` 均 100% |
| pipeline（fetchio / report / runner / stages） | stable | 97–100% | re-resolve、整批 BLOCKED、串行 drain；`runner.py` 98%/`stages.py` 97% |
| verify（对账三类检出） | stable | 100% | AC-1.3/AC-3.3 口径；canonical dump 辅助另见 `tests/helpers/dbdump.py`（测试代码，不入本覆盖率统计） |
| canary（healthcheck 三态分类 + `--record`） | stable | 100% | 14 个已注册 adapter 全覆盖（`test_cli_canary.py` 断言列表遗漏 aaai_ojs/dblp 已随检查单 #15d 补齐） |
| ids + merge（Phase 3 归并层） | stable | 100% | `ids.py` DOI/title 归一；`merge.py` `MergeEngine`（强合并/字段优先级收敛/弱信号候审/跨 paper 冲突裁决，AC-3.1/3.2/3.4） |
| cli（命令层） | stable | 97% | `pull`/`enrich`/`oa-report`/`canary`/`verify`/`venues` 等；退出码 0/1/2/3 契约 |

### Adapter（13 个已注册 + 1 stub，`crawler venues lint`/`load_adapters()` 口径）

| 模块 | 状态 | 覆盖 | 备注 |
|---|---|---|---|
| `_oai.py`（共享 OAI-PMH 解析层） | stable | 100% | arxiv + aaai_ojs 共用 |
| mock_platform（open_access，测试基建） | stable | 100% | 确定性语料 + 故障注入；契约/golden 基建载体 |
| arxiv（open_access） | stable | 100% | OAI-PMH 月度桶枚举 |
| openreview（open_access，free_account） | stable | 96–100% | AC-2.1/2.2 在线层 PASS（Phase 3 期间用户 token 到位补验）；`adapter.py` 96% |
| pmlr（open_access） | stable | 100% | 自托管 + GitHub 双域 resolve |
| acl_anthology（open_access） | stable | 100% | git-tree 发现 + legacy/modern 双命名 |
| cvf（open_access） | stable | 99–100% | flat / day-landing 双形态；`parse.py` 99% |
| aaai_ojs（open_access） | stable | 98–99% | OAI 收割；全库补跑残项见下方"待补验" |
| neurips_proceedings（open_access） | stable | 100% | legacy/modern 后缀边界 |
| crossref（aggregator，Phase 3 T3） | stable | 98–100% | facet 逐年 + cursor 深翻断点续拉（检查单 #15a 补端到端窗口重建去重用例）；healthcheck golden 已转正 |
| dblp（aggregator，Phase 3 T4） | stable | 100% | conf 索引发现 + 单请求整卷；线上 `<bht>` 真实 schema 已修（`c144573`） |
| unpaywall（aggregator，Phase 3 T5） | stable | 100% | RESOLVE only；`oa-report` CLI 限速链路已补直接证明（检查单 #15b） |
| openalex（aggregator/enrich，Phase 3 T6） | stable | 98–100% | duck-typed `enrich_batch`；日预算熔断（`budget.py` 100%，跨进程 flock 加固见检查单 #10） |
| s2（aggregator/enrich，Phase 3 T6） | stable | 98–100% | key 门控批查；无 key → SKIP（D-021 产品取舍，非缺陷） |
| elsevier_sd（auth_gated，stub） | planned（stub 占位） | 100%（`NotImplementedError` 分支） | 设计文档仍 `review`（未 `approved`）；QJE `fulltext_source` 借用 `elsevier_sd` 键名的占位状态见 Phase 4 检查单 #2 |

AC 验收记录不再随本表逐条列出（AC-1/AC-2/AC-3 分散在多个 Phase，条目已超出"模块状态"
的粒度）——权威清单见 [acceptance-criteria.md](../testing/acceptance-criteria.md)，
逐次验收记录见 [testing/records/](../testing/records/)。

## Session 记录索引

| 日期 | 日志 | 主要产出 |
|---|---|---|
| 2026-07-20 | [logs/2026-07-20-session-001.md](../logs/2026-07-20-session-001.md) | 文本系统建立；核心设计 00–09；plan/testing/process；catalog 6 篇；调研 5 篇（日志为 002 补记） |
| 2026-07-20 | [logs/2026-07-20-session-002.md](../logs/2026-07-20-session-002.md) | 6 SVG；16 篇 adapter 详设；catalog 补 2 篇；出版社/同类项目调研 4 篇归档；INDEX；Phase-0 报告；git 初始提交 |
| 2026-07-20 | [logs/2026-07-20-session-003.md](../logs/2026-07-20-session-003.md) | 一致性审查第 1 轮：需求矩阵 17/17；13 项修复（D-015） |
| 2026-07-21 | [logs/2026-07-21-session-004.md](../logs/2026-07-21-session-004.md) | 深度审计第 2 轮：10 项修复；GLOSSARY+INDEX 导航+FR→AC 映射表（D-016） |
| 2026-07-21 | [logs/2026-07-21-session-005.md](../logs/2026-07-21-session-005.md) | **Phase 1 全程**：实施计划+D-017；多 agent 并行开发 10 任务（fable/opus/sonnet 分档）；10 轮审查+终审；AC-1 全过；文档 implemented；tag phase-1/schema-v1 |
| 2026-07-21/22 | [logs/2026-07-22-session-006.md](../logs/2026-07-22-session-006.md) | **Phase 2 全程**：W0 门禁+D-018/019/020；7 站 LIVE 勘察（~185 只读请求）；6 详设重写门禁；7 adapter 实现+审查+真实交叉验证；6 站在线冒烟实跑；终审放行；tag phase-2 |
