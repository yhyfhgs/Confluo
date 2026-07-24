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

- **当前 Phase**：4（认证框架 + 出版社 adapters）**T8 收尾中**（DoD 离线口径达成，待 controller 终验签署 + `tag phase-4`）——AuthProvider 四实现（APIKey/CookieSession/SSOFlow/EZProxy）+ AES-GCM 凭证库（D-023）+ `crawler auth login/status/logout` CLI + `ChallengeDetector` 四态判定器（纯防御，AC-0.2）；config 分层加载 + 敏感键护栏 + `crawler config show`（D-025）；三平台 adapter 落地（`elsevier_sd` API 档 429 熔断、`oup_silverchair` cookie/SSO 档 + QJE fulltext_source 收敛、`wiley` TDM 档双窗口限速）；pipeline OA-fallback 全链 + 健康门 + 日配额 + 冷却 + 工作时段窗（T5）；`crawler grab` 单篇命令。验收：[AC-4 离线汇总记录](../testing/records/2026-07-23-ac4-acceptance.md)（T7a draft，AC-4.2~4.6 **PASS（离线口径）**；AC-4.1 真实 key/token 冒烟按 D-018 分层归 T7b，不阻塞离线 DoD）；AC-0 系统性扫描见 [phase4-report](../reports/2026-07-23-phase4-report.md) §AC-0（五条全 PASS）。终态门禁 **2712 passed / 21 skipped / 98.84%**（21 skip 全为 contract 层能力缺口预期 skip，零凭证门控 skip 混入 offline 套件）。→ 下一 Phase：5（SSRN 与特殊源），检查单见报告 §Phase 5 开工检查单
- **Phase 3 已完成**（2026-07-23，tag `phase-3` @ `35c79a6`）：合并引擎（AC-3.1/3.2/3.4）、verify 三类检出（AC-3.3）、五源 adapter、五刊 VenueSpec + AC-3.5 在线实跑双层 PASS。验收：[Phase 3 汇总记录](../testing/records/2026-07-23-phase3-acceptance.md)（最终签署：**达成**）；报告：[phase3-report](../reports/2026-07-23-phase3-report.md)。
- **Phase 2 遗留 C-C/C-D 已修复**：C-C（大 venue pull 可用性——零网络 resolve 豁免限速闸 + `--limit` 前置圈选，D-022，`eeef820`/`7d3424d`）、C-D（openreview venueid 异构缺陷——2018/2019 逐年 accepted 规则，`8cc2a75`/`3b9e332`/`45c8250`）均已合并；openreview AC-2.1/2.2 在线层随之转 PASS（用户 token 已配置并建立自动刷新脚本）。Phase 2 报告检查单 #1（用户 token）与终检增补置顶 C-C/C-D 两项均已清零。
- **待补验（不阻塞进行中状态，如实记录）**：S2 API key 未到（enrich/canary 在线层 SKIP 门控，D-021）；elsevier API key 未到（BLOCKER-1，AC-4.1 真实取回归 T7b）；wiley token 未到（在线层 SKIP 门控，D-024）；AC-3.1/3.2/3.3/3.4 尚无独立汇总验收记录文档（T8 Phase 3 残项，本次 Phase 4 收尾未处理，随 Phase 5 一并考虑）；D-019 锚点表 openalex 正锚点、s2 锚点仍 `[PENDING]`（需 key/credit）；`test_cli_canary.py` 断言列表遗漏 `oup_silverchair`/`wiley`（本次复核新发现，功能不受影响——二者无凭证时清洁 SKIP，同 openalex/s2 先例，仅断言列表与 `pyproject.toml` 一条注释文字滞后，详见模块状态表"canary"行与 phase4-report 检查单）。**aaai_ojs 全库 OAI 补跑已完成**（2026-07-23，Phase 2 检查单 #3 → Phase 3 报告 §6 检查单 #8 跨 3 Phase 清账：234/262 页/22352 条活记录，D-019 锚点表 8 行 `oai_count` 已回填，UNRESOLVED①③已闭合——详见 research/site-survey/aaai-ojs.md §11 与 design/adapters/aaai-ojs.md §10）；**新增待裁决项**：实测确认 Vol.24–32（2010–2018，9 个届）同构可收割，是否扩容 `volume_map` 纳入需主 agent 裁决（design/adapters/aaai-ojs.md §10 ★F）。
- **总体进度**：Phase 0/1/2/3 = 100%；Phase 4 = **DoD 达成（离线口径），T8 收尾中**（待 controller 终验签署 + `tag phase-4`，遗留细项移交 Phase 5，见 phase4-report §Phase 5 开工检查单）。新 ADR：D-023/D-024/D-025。
- **待用户执行**：①S2 API key 申请（`config.toml [auth.s2] api_key`，enrich/canary 在线层补验前提）；②Elsevier API key 申请（BLOCKER-1，`config.toml [auth.elsevier] api_key`，AC-4.1 真实 JFE 取回前提，外部依赖 1–2 周）；③Wiley TDM token 申请（自助 click-through，`config.toml [auth.wiley] token`）；④oup SSO/campus cookie 首登 runbook（T7b）；⑤`config.toml [identity].email` 补配（AC-3.5 验收记录 C5 延续，默认 home 缺 email 会掉出 Crossref polite pool）；⑥Kaggle key 状态复核（Phase 2 检查单 #2 残项，跨 3 个 Phase 未清）。
- **阻塞**：无（BLOCKER-1 elsevier key 为外部依赖已计划内，不阻塞离线 DoD/tag）

## Phase 进度板

| Phase | 状态 | 进度 | 备注 |
|---|---|---|---|
| 0 设计与文本系统 | done | 100% | 报告：reports/2026-07-20-phase0-report.md |
| 1 核心框架 | **done** | 100% | 报告：reports/2026-07-21-phase1-report.md；tag phase-1 + schema-v1 |
| 2 Open-Access MVP | **done** | 100% | 报告：reports/2026-07-22-phase2-report.md；tag phase-2；openreview 在线层已于 Phase 3 期间补验 PASS（用户 token 到位，见下） |
| 3 聚合元数据层 | **done** | 100%（tag phase-3） | 全部任务卡合并+汇总验收最终签署（AC-3 全 PASS/AC-0 全 PASS/预算零超支）；验收：testing/records/2026-07-23-phase3-acceptance.md |
| 4 认证框架+出版社 | **done**（tag `phase-4`） | 100% | 全部任务卡合并；AC-4.2~4.6 离线 DoD PASS（T7a）+ controller 终验签署；AC-4.1 真实凭证归 T7b（D-018，不阻塞，跨 Phase 遗留见下）；验收：testing/records/2026-07-23-ac4-acceptance.md；报告：reports/2026-07-23-phase4-report.md |
| 5 SSRN 与特殊源 | **T8 收尾中** | ~100%（8 卡全交付，DoD 离线口径达成，待 opus 全分支终审+tag） | 全部任务卡合并（T1 crossref 两轴扩展/T3 nber/T4 ssrn/T5 aea/T6 econsoc+wiley 联动/T7 AC-5 正式化/M1 census）；AC-5 四条 PASS + 5.1b N/A defer（T7 draft→controller 终验 approved）；4 新 adapter（16→20）+ 13 新 venue（45→58）；验收：testing/records/2026-07-24-ac5-acceptance.md；报告：reports/2026-07-24-phase5-report.md（判定：待终审） |
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
> 非 Python，不计入覆盖率统计。
>
> **2026-07-23 二次刷新**（Phase 4 T8 收尾）：新增 `auth 包`（§下）+ 三平台 adapter 行
> （`elsevier_sd` 由 stub 转真实、新增 `oup_silverchair`/`wiley`）；核心模块表
> `config/http/ratelimit/obslog/sensitive`/`cli`/`pipeline` 行覆盖率与备注随 Phase 4
> 改动同步刷新。全量结果（`test_cli_grab.py`/`test_auth_*.py`/三 adapter 测试树等
> 新增测试计入）：**2712 passed / 21 skipped，TOTAL 99%（精确 98.84%，8374 stmts/64
> miss）**，`make check` exit 0（21 skip 全为 `test_adapter_contract.py` 能力缺口
> 预期 skip：8 例 openalex/s2 duck-typed enrich 不参与协议 + 13 例各 adapter 缺
> DISCOVER/ENUMERATE/RESOLVE/FETCH 之一，零凭证门控 skip 混入本离线套件）。

### 核心模块

| 模块 | 状态 | 覆盖 | 备注 |
|---|---|---|---|
| errors / types / adapter / useragent（接口冻结件） | stable | 100% | Capability/AuthLevel/AdapterBase 协议冻结；`adapter.py` 已退役死代码 `CrossrefStub`（检查单 #15d）；`errors.py` 新增 `AuthRequired`/`Challenged` 子类 + `status_code` 权威版（D-024 P0a 开放题③，T2） |
| config / http / ratelimit / obslog / sensitive | stable | 99–100% | `config.py` 99%（D-025 四层加载链+项目级敏感键护栏+`crawler config show`）/`http.py` 99%（缺口为防御性早失败分支，结构化 `status_code` 新增）；`ratelimit.py`/`obslog.py`/`sensitive.py` 均 100%；`sensitive.py` 为 Phase 4 新增单一权威敏感键源（`REDACT_KEY_PATTERN`/`CONFIG_GUARD_KEY_PATTERN` 双消费方共享，D-025） |
| registry + venues YAML lint | stable | 100% | lint 七类校验；`crawler venues lint` 本次亲跑 45 个 venue 全过（含 `qje.yaml` fulltext_source 收敛 `elsevier_sd`→`oup_silverchair`） |
| tasks（任务队列与状态机） | stable | 100% | 7 合法转移 + `recover_running`；`oa_fallback` 阶段键（T5）复用既有 fresh_skip 语义 |
| storage（db / migrations / repo） | stable | 100% | schema v2（`0002_title_norm` 迁移，Phase 3 新增）；`db.py`/`repo.py` 均 100% |
| pipeline（fetchio / report / runner / stages） | stable | 96–100% | `runner.py` 96%/`stages.py` 97%/`fetchio.py`/`report.py` 100%；Phase 4 新增 OA-fallback 全链（no_entitlement→unpaywall 派生+直取落盘）、批级健康门（`_BatchGate`）、日配额对账、挑战冷却持久化、工作时段窗（T5，auth-framework §8 全接线） |
| verify（对账三类检出） | stable | 100% | AC-1.3/AC-3.3 口径；canonical dump 辅助另见 `tests/helpers/dbdump.py`（测试代码，不入本覆盖率统计） |
| canary（healthcheck 三态分类 + `--record`） | stable | 100% | 16 个已注册 adapter（Phase 4 新增 `elsevier_sd`[stub 转真实]/`oup_silverchair`/`wiley`）；**本次复核新发现**：`test_cli_canary.py::test_canary_without_filter_checks_all_registered_adapters` 断言列表（第 146–161 行）与内联注释仍写"现 14 个"，未随 T4/T-wiley 合并补上 `oup_silverchair`/`wiley` 两个新 adapter_id——功能不受影响（二者 `healthcheck()` 无凭证时清洁 `raise NotImplementedError`→SKIP，同 openalex/s2 先例，故测试仍绿），纯断言列表滞后，同 Phase 3 检查单 #15d 模式（同类问题第二次出现）；另 `pyproject.toml:28` 注释仍称"`stubs（elsevier_sd）`"，T3 已转真实 entry point（见 44 行），注释文字未跟上——均登记 Phase 5 检查单，不阻塞 tag |
| ids + merge（Phase 3 归并层） | stable | 100% | `ids.py` DOI/title 归一；`merge.py` `MergeEngine`（强合并/字段优先级收敛/弱信号候审/跨 paper 冲突裁决，AC-3.1/3.2/3.4） |
| cli（命令层） | stable | 95% | `pull`/`enrich`/`oa-report`/`canary`/`verify`/`venues`/`auth login,status,logout`/`grab`（Phase 4 新增单篇精取，T5）/`config show`（D-025）等；退出码 0/1/2/3 契约 |

### auth 包（`src/paper_crawler/auth/`，Phase 4 新增）

| 模块 | 状态 | 覆盖 | 备注 |
|---|---|---|---|
| protocol.py（`AuthProvider` Protocol 冻结件） | stable | 100% | `@runtime_checkable`；五方法签名 T1a 冻结（`ensure_session`/`health_check`/`refresh`/`invalidate`/`rewrite_url`） |
| challenge.py（`ChallengeDetector`） | stable | 100% | 四态判定器（OK/LOGIN_REDIRECT/NO_ENTITLEMENT/CHALLENGE），纯防御分类、不含求解/绕过逻辑（AC-0.2 红线，本次复核逐行核实） |
| store.py（`CredentialStore`） | stable | 100% | AES-GCM（`cryptography>=42`，D-023）加解密 + keyring↔文件密钥降级链 + 0600 强制 + `profiles.toml` 加载；`[auth]` extra 惰性 import |
| providers/{api_key,cookie_session,ezproxy,sso_flow}.py | stable | 100% | 四实现：`ApiKeyProvider`（elsevier/wiley）、`CookieSessionProvider`+`SSOFlowProvider`（oup，mock IdP 集成验证）、`EZProxyProvider`（URL 重写，纯逻辑+mock，无需真实机构凭证） |
| manager.py（`AuthManager`） | stable | 100% | provider 注册表 + `active_profile` 解析 + session 缓存 + 健康门/配额编排入口；DI 缺口（不支持注入 `http_factory`/`login_flow` 测试 seam）见 Phase 5 检查单 |
| browser.py（Playwright 薄封装） | stable | 100% | 首登有头启动/storage_state 导出/浏览器上下文下载；`[auth-browser]` extra 惰性 import，本 Phase 未触真实浏览器（`PC_BROWSER_TESTS` 手动门） |
| cli.py（`auth login/status/logout`） | stable | 100% | 薄接线，纯逻辑在 manager/store |

### Adapter（16 个已注册，`crawler venues lint`/`load_adapters()` 口径；stub 清零）

| 模块 | 状态 | 覆盖 | 备注 |
|---|---|---|---|
| `_oai.py`（共享 OAI-PMH 解析层） | stable | 100% | arxiv + aaai_ojs 共用 |
| mock_platform（open_access，测试基建） | stable | 100% | 确定性语料 + 故障注入；契约/golden 基建载体 |
| arxiv（open_access） | stable | 100% | OAI-PMH 月度桶枚举 |
| openreview（open_access，free_account） | stable | 96–100% | AC-2.1/2.2 在线层 PASS（Phase 3 期间用户 token 到位补验）；`adapter.py` 96% |
| pmlr（open_access） | stable | 100% | 自托管 + GitHub 双域 resolve |
| acl_anthology（open_access） | stable | 100% | git-tree 发现 + legacy/modern 双命名 |
| cvf（open_access） | stable | 99–100% | flat / day-landing 双形态；`parse.py` 99% |
| aaai_ojs（open_access） | stable | 99% | OAI 收割；全库补跑已完成（2026-07-23，见"待补验"新增待裁决项：2010–2018 覆盖扩容） |
| neurips_proceedings（open_access） | stable | 100% | legacy/modern 后缀边界 |
| crossref（aggregator，Phase 3 T3） | stable | 92–95% | facet 逐年 + cursor 深翻断点续拉（检查单 #15a 补端到端窗口重建去重用例）；healthcheck golden 已转正；**本次复核覆盖率较 Phase 3 报告的 98–100% 下降**——`grab`（T5）新用的 `lookup()` 方法（`adapter.py:226-241`）与 healthcheck `[PENDING golden]` 分支（`:265`）未被任何单测直接命中（`test_cli_grab.py` 走 mock 而非真实 `CrossrefAdapter.lookup`），非回归、纯增量代码缺直接单测，不阻塞（模块整体仍 stable，聚合覆盖率门禁 ≥80% 达标） |
| dblp（aggregator，Phase 3 T4） | stable | 100% | conf 索引发现 + 单请求整卷；线上 `<bht>` 真实 schema 已修（`c144573`） |
| unpaywall（aggregator，Phase 3 T5） | stable | 100% | RESOLVE only；`oa-report` CLI 限速链路已补直接证明（检查单 #15b）；Phase 4 起兼任 pipeline OA-fallback 的 OA 副本来源（T5，AC-4.3 载体） |
| openalex（aggregator/enrich，Phase 3 T6） | stable | 98–100% | duck-typed `enrich_batch`；日预算熔断（`budget.py` 100%，`add_spend` 跨进程 `fcntl.flock` 加固已落地，检查单 #10；Windows 无 fcntl 降级为加固前现状） |
| s2（aggregator/enrich，Phase 3 T6） | stable | 98–100% | key 门控批查；无 key → SKIP（D-021 产品取舍，非缺陷） |
| elsevier_sd（auth_gated，Phase 4 T3） | **stable**（stub 已退役） | 100% | `RESOLVE\|FETCH`，domains=`api.elsevier.com`（非 `www.sciencedirect.com`，页面路线不走——elsevier robots 全禁）；`ApiKeyProvider`；429 保守熔断（自限 2 req/s，官方 10 req/s 留余量）+ 当日 circuit breaker；无 key → `NotImplementedError`→SKIP；BLOCKER-1（真实 key 未到）AC-4.1 在线冒烟归 T7b |
| oup_silverchair（auth_gated，Phase 4 T4） | **stable**（新增） | 100% | `RESOLVE\|FETCH`，domains=`academic.oup.com`；`CookieSessionProvider`/`SSOFlowProvider`（`oup@campus`/`oup@shib` 双 profile）；`ChallengeDetector` 四类判定接线；QJE `fulltext_source` 收敛完成（不再借用 `elsevier_sd` 占位，Phase 3 检查单 #2 清零）；限速 1 req/6s（robots 无声明，保守默认） |
| wiley（auth_gated，Phase 4 T-wiley） | **stable**（新增） | 100% | `RESOLVE\|FETCH`，domains=`api.wiley.com`（TDM 主干；页面兜底 `onlinelibrary.wiley.com` deferred）；`ApiKeyProvider`（TDM token）；双窗口限速单桶表达 `RatePolicy(rpm=5,burst=3)`（D-024）；`resolve_offline=True`（纯 URL 构造零网络）；无 token → SKIP |

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
