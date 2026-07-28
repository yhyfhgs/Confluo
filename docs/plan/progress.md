---
title: 项目进度跟踪
status: approved
owner: fable5
updated: 2026-07-29
---

# 项目进度

> 本文件是"当前状态"的单一事实来源。每次工作 session 结束时更新。
> 历史细节见 `docs/logs/`；阶段总结见 `docs/reports/`。

## 当前快照（2026-07-27）

- **当前 Phase**：7（全文抽取与库增强）**全部任务卡与 AC-7 验收已闭合**（2026-07-27，`main` @ `0a9ce11`；门禁 **4617 passed / 31 skipped / 覆盖率 98.98%**、EXIT=0；`tag phase-7` **待 controller**——fable 全分支终审后打，本次 T21 收尾仅产出文档链）。**22 卡**5 波次全交付（W0 六卡 T1–T6 并行铺开 → W1 T7/T8/T9/T10 滚动补位 → W2 T11–T15 → W3 T16–T18 → W4 T19 在线验收批 → T20 独立审计批 → T21 文档收尾（本报告）→ T22 controller 终审+tag）：
  - **主线交付**（T1–T19，前一编排 session 已完成合并）：T1 D-033 全文抽取详设 ADR（pypdf 基线+GROBID 可选增强+asset 级幂等键全序取 max）；T2 D-034 FTS5+D-035 repec 接入双 ADR；T3 E-2 冷却键统一+`crawler cooldown status|clear`；T4 机动预算运行时账本（`scripts/budget_ledger.py`+`.paper-crawler/state/budget.json`+`docs/process/online-budget.md` 三条纪律，闭合 phase6-report 事件⑤的协调缺口）；T5 文档微清账（检查单 #12+#15，AEJ 四刊注记+ECMA 归属表述统一）；T6 browser-fetch 横切件核心（`fetch_one`+`BrowserFetchHandle` 冻结件+`[browserfetch]` 四槽）；T7 extract 核心落地（stage 5 noop→真实抽取，schema v4 五列，降级链+asset 级幂等）；T8 repec enrich 首批（两域 robots 附条件核验后落地，bulk ReDIF 零网络本地 join）；T9 arxiv 参数化谓词机制（检查单 #4 谓词半边，替代 `title_regex_any` 手工镜像约定）；T10 preprint_of 建边引擎（`merge.py` 新增建边分支，方向固定 from(预印本)→to(发表版)）；T11 browser-fetch 三消费方接入（ssrn 模式 B/aea pubs/wiley 页面兜底）；T12 FTS5 落地（`0005_fts_paper.sql`+`crawler search`/`reindex [--check]`）；T13 dedupe review CLI（AC-7.3，`same_as(decided=merged)` 聚合语义）；T14 verify 全库扩展（+si/+fulltext 两段，新增 `stale_fulltext` 信息级）；T15 econsoc 回看窗闭合（跨年分区缓存+当前年首拉全量收割）；T16 preprint↔published 关联报告；T17 全库 `Database` 构造审计（检查单 #10，88 处/43 文件四分类甄别，36 处补资源纪律）；T18 AC-BF 编号转正+AC-5.1b 承接指针+AC-7 验收记录骨架；T19 在线验收批（AC-7 四条回填+预算对账，过程中自行发现 P0 缺陷）。
  - **T20 终态独立审计**（Opus 深审×2：①extract+browserfetch+三消费方、②repec+merge 建边+dedupe 聚合；+Sonnet 面审×1：谓词/FTS/verify/cooldown/回看窗/审计卡；审查规格=亲自构造对抗输入+变异测试）抓出 **4 处跨卡缝缺陷**（R1 域：F-1 ssrn 模式 B 同批闭包生产端漏接线、F-2 签名 volatile URL 未脱敏；R2 域：F-3 repec w/t series 塌缝致假重复+静默污染、F-4 `search`/`list` 聚合语义矛盾），叠加 T19 在线批自行发现的 **P0**（`crawler subs watch` 遇 crossref 偏日期整轮崩溃，SSRN 首次真实运行即触发，窗内 99.5% 候选携 partial 日期）——本 session 完成三条修复批全部闭环（各经"执行→独立审查→回修→复核→controller 合并+门禁"）：①**P0 修复**（`75b33f2`+`c04c8c4`：拆分宽松/严格日期解析双路径+订阅级真隔离两层，初审 NEEDS_FIX 抓出原缺陷 B 修法是死代码，回修后复审 APPROVE）；②**R1 修复批**（`46fade4`/`b060c5b`/`9f1d772`/`79450fb`/`d6079e7`：能力发现式接线+签名脱敏三层纵深+两跳限速间隔归位+P2 六项）；③**R2 修复批**（`243ef10`/`93ffedd`/`82fbfa9`：w-only 收窄+search/list 聚合统一+**D-036** ADR 补账）。
  - **在线重跑（卡 D）**：P0 修复合入 main 后，`asset-pricing` 三源端到端重跑——12 请求全部 200、EXIT=0、三腿全跑、`subscription_run` 行+当日日报+三源水位三件套俱全；partial 日期剔除（窗内 5670/5696 条，占 99.5%）经 WARNING 可观测、整轮不受影响——**P0 修复的首次真实数据验证**。
  - 门禁轨迹：3832（Phase 7 开工基线，main @ `d56313f`）→**4617 passed / 31 skipped**，coverage **98.98%**，EXIT=0（main @ `0a9ce11`，controller 亲跑）。四条新 ADR：**D-033**（extract 语义：pypdf 基线+GROBID 可选+asset 级幂等全序取 max）、**D-034**（FTS5 检索：title+abstract content-owning 虚表+触发器同步）、**D-035**（repec 接入：`_ENRICH_SOURCES` 扩位+`SOURCE_PRIORITY` 七位重编号+`state/repec/` 快照契约）、**D-036**（repec w-only 收窄+search 聚合展示与 list 统一，T20 修复批补账）。AC-7 四条判据：AC-7.1/7.4 真实数据**PASS**（真实 3 篇标题比 0.0000/verify 注入复验 EXIT 0↔1↔0）；AC-7.3 **条件 PASS**（离线三件套齐备+在线空态如实标注，真实候选需跨源重叠语料）；AC-7.2 离线 **PASS**、在线**条件项**（本机无 GROBID，环境未就绪）。报告：[phase7-report](../reports/2026-07-27-phase7-report.md)（判定列待 controller 终审）。→ 下一 Phase：8**待用户令**，开工检查单见 phase7-report「Phase 8 开工检查单」节（14 项）。
- **2026-07 终审审计修复批（`fix/audit-2026-07` 分支，进行中）**：终审审计（P0×5/P1×24）修复分 R1–R4 批次推进——R1（keyring 跨 home 隔离/限速面护栏/pypdf 代理字符清洗/pipeline fetch 前置门路由）与 R2（凭证装配/subs 能力校验/ezproxy 接线/cooldown 键规范化五卡装配缝）与 R3（aaai 当前届全量基线/repo 弱信号落库/性能索引+任务 GC+进程锁/oup cookie 与 CLI 退出码收口）均已合入；R4（本批，docs 收口——decision-log 新增 D-037/038/039 + 七篇设计文档实况订正）进行中。
- **待补验（不阻塞，如实记录，沿自 Phase 6 快照 + 本 Phase 新发现）**：S2 API key 未到（D-021 SKIP 门控）；elsevier API key 未到（**BLOCKER-1**，AC-4.1 真实取回归 T7b，跨 Phase 3–7 五阶段仍未清）；wiley TDM token 未到；D-019 锚点表 openalex/s2 锚点仍 `[PENDING]`（需 key/credit）；aaai **全文回填批**（~5049 篇，≈2.8h@30rpm+5–15GB）待用户令另行插单；econsoc `[UNRESOLVED①④]`（ECMA 是否全刊 OA / 过刊运行期终态）遇 Cloudflare 交互质询维持未解决，建议提升 canary 优先级。**新增（Phase 7 期发现，转 Phase 8）**：见 phase7-report「Phase 8 开工检查单」节全 14 项——含 `papers.ssrn.com` robots Disallow 面核验（design/11 §2 红线 4 前置门，首次真实演练前必核）、F-2 脱敏对真实 ssrn Delivery 形态未核验、search 折叠丢类内最佳 rank 未记 docstring、日报落盘根 CWD 相对 vs config-home 两套 reports 并存、AC-7.3 在线真实候选（需跨源重叠语料）、AC-7.2 GROBID 真实开模式+AC-BF 真实冒烟（playwright，`T19-bf` 预算行已调剂用尽）、CLI `--issue` 单用限制、OpenAlex 补枚举 ladder(a)（§8 出列沿账）等。
- **总体进度**：Phase 0/1/2/3/4/5/6/7 = 100%（tag `phase-0`…`phase-6` 全落；`tag phase-7` 待 controller 终审）；Phase 8 planned **待用户令**。新 ADR（Phase 7）：D-033/D-034/D-035/D-036
- **待用户执行**：①S2 API key 申请（`config.toml [auth.s2] api_key`）；②Elsevier API key 申请（**BLOCKER-1**，`config.toml [auth.elsevier] api_key`，外部依赖，跨 5 个 Phase 未清）；③Wiley TDM token 申请（自助 click-through，`config.toml [auth.wiley] token`）；④oup SSO/campus cookie 首登 runbook（T7b）；⑤`config.toml [identity].email` 补配；⑥Kaggle key 状态复核（跨 6 个 Phase 未清）；⑦aaai 全文回填批用户令（~5049 篇，成本已注②）；⑧Phase 8 开工令（届时按 phase7-report「Phase 8 开工检查单」节开工）
- **阻塞**：无（elsevier key 为计划内外部依赖；econsoc Cloudflare 质询风险如实登记非阻断；phase6-report 事件⑤的机动预算台账协调缺口已由本 Phase T4 运行时账本机制解决；`T8-robots` 预算行超线与 P0 诊断表述两处历史 NEEDS_DECISION 均已裁决落档，见 AC-7 记录）

## Phase 进度板

| Phase | 状态 | 进度 | 备注 |
|---|---|---|---|
| 0 设计与文本系统 | done | 100% | 报告：reports/2026-07-20-phase0-report.md |
| 1 核心框架 | **done** | 100% | 报告：reports/2026-07-21-phase1-report.md；tag phase-1 + schema-v1 |
| 2 Open-Access MVP | **done** | 100% | 报告：reports/2026-07-22-phase2-report.md；tag phase-2；openreview 在线层已于 Phase 3 期间补验 PASS（用户 token 到位，见下） |
| 3 聚合元数据层 | **done** | 100%（tag phase-3） | 全部任务卡合并+汇总验收最终签署（AC-3 全 PASS/AC-0 全 PASS/预算零超支）；验收：testing/records/2026-07-23-phase3-acceptance.md |
| 4 认证框架+出版社 | **done**（tag `phase-4`） | 100% | 全部任务卡合并；AC-4.2~4.6 离线 DoD PASS（T7a）+ controller 终验签署；AC-4.1 真实凭证归 T7b（D-018，不阻塞，跨 Phase 遗留见下）；验收：testing/records/2026-07-23-ac4-acceptance.md；报告：reports/2026-07-23-phase4-report.md |
| 5 SSRN 与特殊源 | **done**（tag `phase-5` @ `c577d6c`） | 100% | 8 卡 4 波次全交付（T1 crossref 两轴扩展/T3 nber/T4 ssrn/T5 aea/T6 econsoc+wiley 联动/T7 AC-5 正式化/M1 census/T8 收尾）；AC-5 四条 PASS + 5.1b N/A defer Phase 6；4 新 adapter（16→20）+ 13 新 venue（45→58）；门禁 3056/28/98.78%；验收：testing/records/2026-07-24-ac5-acceptance.md；报告：reports/2026-07-24-phase5-report.md（终审判定：**达成**）；终审后独立全库审计：reports/2026-07-24-post-phase5-audit.md（八域附条件达标、零 P0，发现入 Phase 6 检查单） |
| 6 订阅与搜索 | **done**（tag `phase-6` @ `614ab70`） | 100% | 21 卡 5 波次全交付（T1 DSL 地基+T1b 接缝终裁/T2 编译器/T3 过滤+护栏/T4 watermark/T5 watch runner+CLI/T6 日报/T7 nber RSS/T8 9 preset/T9 AC-6 验收 + F1–F7 修复批（含 T9 后增补的 F7）+ R1/R2 设计批 + M1 在线批）；AC-6.1~6.4 离线 DoD 四条 PASS，fable 亲验签署"达成"；门禁 3056→**3820 passed/28 skipped/98.99%**（+764 测试）；adapter/venue 数不变（20/58，本 Phase 不新增平台）；新 ADR D-030/D-031；实施计划：[phase6-implementation-plan](phase6-implementation-plan.md)；验收：[2026-07-26-ac6-acceptance.md](../testing/records/2026-07-26-ac6-acceptance.md)；报告：[phase6-report](../reports/2026-07-26-phase6-report.md)（opus 终审"放行附条件"，六项文档修正条件已闭合；`tag phase-6` 已由 fable 合并裁决落地） |
| 7 全文抽取与库增强 | **done**（tag `phase-7` 待 controller 终审） | 100% | 22 卡 5 波次全交付（T1 D-033 extract ADR/T2 D-034+D-035 双 ADR/T3 冷却统一/T4 预算账本/T5 文档清账/T6 browser-fetch 核心/T7 extract 落地/T8 repec enrich/T9 谓词机制/T10 preprint_of 建边/T11 三消费方接入/T12 FTS5/T13 dedupe review/T14 verify 扩展/T15 econsoc 回看窗/T16 关联报告/T17 DB 构造审计/T18 AC-BF 转正/T19 在线验收批 + T20 独立审计（4 处跨卡缝缺陷）+ P0/R1/R2 三条修复批闭环 + 在线重跑卡 D）；AC-7 四条判据 AC-7.1/7.4 **PASS**、AC-7.3 **条件 PASS**、AC-7.2 离线 **PASS**/在线条件项；门禁 3832→**4617 passed/31 skipped/98.98%**；新 ADR D-033/D-034/D-035/D-036；实施计划：[phase7-implementation-plan](phase7-implementation-plan.md)；验收：[2026-07-27-ac7-acceptance.md](../testing/records/2026-07-27-ac7-acceptance.md)（draft，待 fable 终审签署）；报告：[phase7-report](../reports/2026-07-27-phase7-report.md)（判定列待 controller 终审；`tag phase-7` 待打） |

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
>
> **2026-07-24 三次刷新**（Phase 5 收尾 + 终审后独立全库审计）：新增 Phase 5 四
> adapter 行（`ssrn`/`nber`/`aea`/`econsoc`，16→20）；`crossref` 行随 T1 两轴扩展
> 刷新（覆盖率回升 99%，`lookup()` 已补直测）；`canary` 行 adapter 计数 16→20。
> 覆盖率数字取自审计基线亲跑（`make check`：**3056 passed / 28 skipped，TOTAL
> 98.78%**，9154 stmts/69 miss，EXIT=0；28 skip 全为 contract 能力缺口型，审计 S4
> 逐行核对台账干净）。审计发现的模块级问题以
> [post-phase5-audit](../reports/2026-07-24-post-phase5-audit.md) §3 为权威台账，
> 本表备注仅摘 P1/P2 级要点。
>
> **2026-07-26 四次刷新**（Phase 6 收尾，T10）：新增 `subs` 包一节（8 模块，见下，
> 全部 `stable`）；`nber` 行下新增 `rss.py` 子行（program RSS watch 通道，T7 转主）；
> `crossref` 行随 F7 补记日窗通道 `_window_bounds`（`quirks` 交集裁窗，backfill 主路径
> 零回归）；`canary` 行随 F5 补记"注册了却没验证"反模式（三次复现）已根治为集合等值
> 自断言常绿。adapter/venue 计数**不变**（20/58——Phase 6 不新增平台 adapter/venue，
> 仅扩展既有 `nber` 增量通道 + 3 个既有 venue YAML 的 ISSN/quirks 小改）。覆盖率数字
> 取自 T10 亲跑（`make check`：**3820 passed / 28 skipped，TOTAL 98.99%**，EXIT=0；
> 28 skip 与 Phase 5 终态同构，未新增 skip）。

### 核心模块

| 模块 | 状态 | 覆盖 | 备注 |
|---|---|---|---|
| errors / types / adapter / useragent（接口冻结件） | stable | 100% | Capability/AuthLevel/AdapterBase 协议冻结；`adapter.py` 已退役死代码 `CrossrefStub`（检查单 #15d）；`errors.py` 新增 `AuthRequired`/`Challenged` 子类 + `status_code` 权威版（D-024 P0a 开放题③，T2） |
| config / http / ratelimit / obslog / sensitive | stable | 99–100% | `config.py` 99%（D-025 四层加载链+项目级敏感键护栏+`crawler config show`；Phase 6 F2 补畸形 TOML→`CrawlerError(CONFIG)` 包裹）/`http.py` 99%（缺口为防御性早失败分支，结构化 `status_code` 新增；**Phase 6 F6** 403 分支新增 `cf-mitigated: challenge` 头判别→CHALLENGE，D-030 S-c，全库 fixture 扫描零翻转）；`ratelimit.py`/`obslog.py`/`sensitive.py` 均 100%；`sensitive.py` 为 Phase 4 新增单一权威敏感键源（`REDACT_KEY_PATTERN`/`CONFIG_GUARD_KEY_PATTERN` 双消费方共享，D-025） |
| registry + venues YAML lint | stable | 100% | lint 七类校验；`crawler venues lint` 本次（T10）亲跑 **58** 个 venue 全过（含 `qje.yaml` fulltext_source 收敛 `elsevier_sd`→`oup_silverchair`；Phase 6 未新增 venue，仅 `aeri`/`jel`/`nber` 三个既有 YAML 的 ISSN/quirks 字段小改） |
| tasks（任务队列与状态机） | stable | 100% | 7 合法转移 + `recover_running`；`oa_fallback` 阶段键（T5）复用既有 fresh_skip 语义 |
| storage（db / migrations / repo） | stable | 100% | schema v3（`0003_paper_weak_key` 迁移，Phase 6 F1/D-031 新增，单调只增+存量回填零倒退零扩张；`0002_title_norm` Phase 3）；`db.py`/`repo.py` 均 100%；`SubscriptionRepo`（subscription/subscription_run CRUD + watermark 读写，Phase 6 T1）同住 `repo.py` |
| pipeline（fetchio / report / runner / stages） | stable | 96–100% | `runner.py` 97%/`stages.py` 97%/`fetchio.py`/`report.py` 100%；Phase 4 新增 OA-fallback 全链（no_entitlement→unpaywall 派生+直取落盘）、批级健康门（`_BatchGate`）、日配额对账、挑战冷却持久化、工作时段窗（T5，auth-framework §8 全接线）；**Phase 6 F6** 冷却判定上移至 family 判别前（修复 open_access 冷却"写而不读"）+ 冷却键改域级（向前兼容旧 `<adapter_id>.json` 键，D-030 E-1） |
| verify（对账三类检出） | stable | 100% | AC-1.3/AC-3.3 口径；canonical dump 辅助另见 `tests/helpers/dbdump.py`（测试代码，不入本覆盖率统计） |
| canary（healthcheck 三态分类 + `--record`） | stable | 100% | **20 个已注册 adapter，数量 Phase 6 不变**（Phase 5 新增 `ssrn`/`nber`/`aea`/`econsoc`；Phase 6 未新增平台）；「注册了却没验证」反模式（aaai_ojs/dblp→oup_silverchair/wiley→aea，**三次复现**，审计 O4-P2）已由 **Phase 6 F5 根治**：`test_cli_canary.py` 断言列表改**集合等值自断言**（`assert set(listed) == set(registry.all())`，与 `load_adapters()` 实际注册表动态比对）——未来新 adapter 忘记同步清单会响亮失败，不再靠人工发现；同批补齐本地周跑自动化模板（`scripts/canary_weekly.sh` + launchd/cron plist 模板，[canary/README.md](../testing/records/canary/README.md)，不常驻不改 CI） |
| ids + merge（Phase 3 归并层；Phase 6 F1 D-031 修复） | stable | 100% | `ids.py` DOI/title 归一；`merge.py` `MergeEngine`（强合并/字段优先级收敛/弱信号候审/跨 paper 冲突裁决，AC-3.1/3.2/3.4）；**F1 修复注入顺序无关性缺陷**（AC-3.4，D-031）：弱信号候审匹配键改**观测级键集合**（`paper_weak_key` 表，不随字段收敛改写）+ tie-break 复合序（文本更长者胜/等长字典序小者，year/pub_date 纯 min）+ `_field_tie` 取证抓手；24 全排列 property 测试锁定顺序无关性 |
| cli（命令层） | stable | 96% | `pull`/`enrich`/`oa-report`/`canary`/`verify`/`venues`/`auth login,status,logout`/`grab`（Phase 4 新增单篇精取，T5）/`config show`（D-025）/`subs watch <name>\|--all [--dry-run]`（Phase 6 T5，订阅增量，与既有 `watch <venue>` 语义分离共存）等；退出码 0/1/2/3 契约 |

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

### subs 包（`src/paper_crawler/subs/`，Phase 6 新增）

| 模块 | 状态 | 覆盖 | 备注 |
|---|---|---|---|
| model.py（`Subscription`/`SourceSelector`/`LocalFilter`/`Guard`/`Actions` + YAML 加载校验，T1 冻结件） | stable | 99% | 未知字段/非法正则/负数 guard 一律 fail-loud；`_DuplicateKeySafeLoader` 拒绝 YAML 重复键静默覆盖 |
| types.py（`CompiledPlan`/`PlanStep`/`RunSummary`/`ReportEntry`/`WatermarkStrategy` 等冻结件，T1） | stable | 100% | `DATE_WINDOW_PARAMS`/`is_source_scoped_predicate()` 单一权威源（T2 产/T3 收/T5 分流三方消费） |
| compile.py（六源查询编译器，`Subscription→CompiledPlan`，T2） | stable | 100% | duck-typed per-source；下推不了的谓词标 `local_only`；ssrn `topic_filter` 接线（检查单 #10） |
| filter.py（本地过滤器，`title_regex_any`/`exclude_regex`/`min_year`，T3） | stable | 100% | 大小写不敏感；`PREDICATE_REGISTRY` 只登记有实现的补偿谓词（防未实现谓词悄悄崩掉整轮 watch） |
| guard.py（护栏引擎，熔断判定+过载报告数据结构，T3） | stable | 100% | `max_new_per_run` 等于阈值不熔断/超过熔断；`dedupe_against_library` 走真 sqlite |
| watermark.py（增量语义三策略，T4） | stable | 100% | 日期上界+重叠窗/日期游标/id 集合差分；`schema_ver` 留演进缝；推进纪律=成功才推进 |
| watch.py（watch 编排 + CLI 接线，T5） | stable | 100% | 批内去重（`_dedupe_within_batch`）+ 参数下达面（`venue_for` 不丢 `request.params`）+ 熔断/dry-run/零新增四场景 |
| report.py（日报渲染，`render_daily`，T6） | stable | 100% | 纯函数；golden 快照三例字符级稳定；过载分布+收窄建议渲染 |

### Adapter（20 个已注册，`crawler venues lint`/`load_adapters()` 口径；stub 清零）

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
| crossref（aggregator，Phase 3 T3；Phase 5 T1 两轴扩展；Phase 6 F7 日窗通道） | stable | 99% | facet 逐年 + cursor 深翻断点续拉；**T1 参数化枚举扩展**（enum-key `issn` XOR `prefix` + date-field `published|created`，nber/aea/econsoc-ECMA/ssrn 四消费方，既有 by-ISSN venue 零回归——本 Phase 唯一动 implemented 冻结件的改动）；**Phase 6 F7 新增日窗通道** `_window_bounds`（venue `quirks` 的 `from/until-{pub\|created}-date` 与桶年取交集拼进 `filter=`，交集为空零请求；ssrn 7 天窗从整年 155,461 条收敛至 6,067 条 `[LIVE]` 实测，backfill 主路径不声明日窗时行为零回归）；Phase 4 记录的 `lookup()` 无直测**已清账**（审计 S2 确认有直接单测，覆盖率回升）；healthcheck golden 已转正；审计 P3 备忘：cursor 深翻无「游标不推进」哨兵（服务端异常回放可无限循环，无防御无测试） |
| dblp（aggregator，Phase 3 T4） | stable | 100% | conf 索引发现 + 单请求整卷；线上 `<bht>` 真实 schema 已修（`c144573`） |
| unpaywall（aggregator，Phase 3 T5） | stable | 100% | RESOLVE only；`oa-report` CLI 限速链路已补直接证明（检查单 #15b）；Phase 4 起兼任 pipeline OA-fallback 的 OA 副本来源（T5，AC-4.3 载体） |
| openalex（aggregator/enrich，Phase 3 T6） | stable | 98–100% | duck-typed `enrich_batch`；日预算熔断（`budget.py` 100%，`add_spend` 跨进程 `fcntl.flock` 加固已落地，检查单 #10；Windows 无 fcntl 降级为加固前现状） |
| s2（aggregator/enrich，Phase 3 T6） | stable | 98–100% | key 门控批查；无 key → SKIP（D-021 产品取舍，非缺陷） |
| elsevier_sd（auth_gated，Phase 4 T3） | **stable**（stub 已退役） | 100% | `RESOLVE\|FETCH`，domains=`api.elsevier.com`（非 `www.sciencedirect.com`，页面路线不走——elsevier robots 全禁）；`ApiKeyProvider`；429 保守熔断（自限 2 req/s，官方 10 req/s 留余量）+ 当日 circuit breaker；无 key → `NotImplementedError`→SKIP；BLOCKER-1（真实 key 未到）AC-4.1 在线冒烟归 T7b |
| oup_silverchair（auth_gated，Phase 4 T4） | **stable**（新增） | 100% | `RESOLVE\|FETCH`，domains=`academic.oup.com`；`CookieSessionProvider`/`SSOFlowProvider`（`oup@campus`/`oup@shib` 双 profile）；`ChallengeDetector` 四类判定接线；QJE `fulltext_source` 收敛完成（不再借用 `elsevier_sd` 占位，Phase 3 检查单 #2 清零）；限速 1 req/6s（robots 无声明，保守默认） |
| wiley（auth_gated，Phase 4 T-wiley） | **stable** | 100% | `RESOLVE\|FETCH`，domains=`api.wiley.com`（TDM 主干；页面兜底 `onlinelibrary.wiley.com` deferred）；`ApiKeyProvider`（TDM token）；双窗口限速单桶表达 `RatePolicy(rpm=5,burst=3)`（D-024）；`resolve_offline=True`（纯 URL 构造零网络）；无 token → SKIP；Phase 5 T6 联动：`parse.py` 移除 `10.3982`（ECMA 归 econsoc 分段路由，D-028，审计 S3 三方一致性核实） |
| ssrn（Phase 5 T4；Phase 6 T2/T4/F7 增量接线） | stable | 97–100% | prefix `10.2139` 聚合元数据主路径（domains 仅 `api.crossref.org`），**站点零接触**（D-029 案 B，审计 S3 核实代码层面成立——`landing_url` 纯字符串构造，无任何 `*.ssrn.com` 请求路径）；`FETCH` 未声明（AC-5.1b defer browser-fetch 横切件，D-030 详设 approved 但实现仍未落地）；econ/fin `topic_filter` **已接线**（Phase 6 T2 `subs/compile.py` 读入 `local_predicates`，检查单 #10 闭合）；watermark 由"id 集合差分"设想改**日期游标**（`from-created-date`，D-029 后时间过滤已可靠，T4 审查裁定）+ F7 日窗收窄（crossref `_window_bounds` 交集，7 天窗 6,067 条 vs 整年 155,461 条）；healthcheck golden 已双源确认转正（M1） |
| nber（Phase 5 T3；Phase 6 T7 增量通道转主） | stable | 97–100% | prefix `10.3386` 枚举 + >18 月开放窗离线全文（D-014 软门不绕过，fetch 阶段 `_soft_gate_guarded_stream` 兜底）+ `www`/`back` 双域分桶（`route_for` alias 陷阱专测规避）；backfill 主干仍走 crossref 枚举，watch 增量改走下行 `rss.py` 主通道（Phase 5 曾是可选通道，Phase 6 T7 已转主）；审计 P3 备忘：`_today` 用本地时区（项目内唯一未 UTC 化的时间敏感点，±1 日边界由软门兜底、不可被利用） |
| nber/rss.py（program RSS watch 通道，Phase 6 T7，**新增**） | stable | 100% | 19 feed 中 5 个 `[LIVE]` 实证映射（AP/CF/EFG/IFM/ME；PE 两义未核验排除，其余未点名代码不臆造，映射表键集与声明支持集合等值自断言防清单漂移）；`discover_incremental` duck-typed watch 流 + id 集合差分桥接（接 `subs/watermark.py::IdSetDiff`）；proxy year 缓解——真实 `<item>` 100% 无 `pubDate`（在线实证），`fetch_year` 派生失败时兜底、backfill/18 月开放窗判定零影响 |
| aea（Phase 5 T5，**新增**） | stable | 100% | prefix `10.1257` 八刊 `CODE_TO_VENUE` 路由（8 venue ISSN 审计三方核对一致）；RESOLVE 结构性恒空、healthcheck 结构性 `NotImplementedError`→canary SKIP（均设计内，契约 skip 台账收录）；全文域 pubs 全域 CF deferred（P6 browser-fetch + D-006 机构认证届时立专属 AC）；`aeri`/`jel` ISSN 仍 `[DOC]` 待 [LIVE] 核实（M1 仅转正 4 刊） |
| econsoc（Phase 5 T6，**新增**） | stable | 92–94% | TE/QE OJS-OAI 自枚举 + ECMA crossref 枚举 + 运行时年代分段路由（D-028）；审计 P2×2：①CF-403 挑战冷却缺口——冻结 `HttpClient` 把 403 统一映射 `NO_ENTITLEMENT`、仅 `CHALLENGE` 触发 24h 冷却，`ChallengeDetector` 嗅探只对 200 挑战页生效（Phase 2/4 冻结架构系统性边界，wiley/oup 同受限，P6 browser-fetch 同批评估）；②当前年 30 天回看窗完整性缺口（与 aaai_ojs 同构，首拉当年漏收超 30 天论文）——均登记 Phase 6 检查单 |

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
| 2026-07-24/26 | [logs/2026-07-26-session-007.md](../logs/2026-07-26-session-007.md) | **Phase 5 终审后全库独立审计**：8 subagent（4 Opus 深审 + 4 Sonnet 面审）复审 Phase 1–5 存量代码——八域附条件达标、零 P0，P1×3/P2×12 登记 [post-phase5-audit](../reports/2026-07-24-post-phase5-audit.md)；progress/INDEX Phase 5 终态同步（快照重写 + 进度板 done + 模块表 20 adapter） |
| 2026-07-26 | [logs/2026-07-26-session-008.md](../logs/2026-07-26-session-008.md) | **acl_anthology SI 附件 URL 前缀 LIVE 核实闭合**：F4 执行中升级项，主 agent 裁决走验证路径而非无限期挂"实验性"；HEAD 核实 200 + 元数据吻合，撤销限定语，`resolve_assets` 实现零改动 |
| 2026-07-26 | [logs/2026-07-26-session-009.md](../logs/2026-07-26-session-009.md) | **Phase 6 全程（订阅与搜索）**：21 卡 5 波次（主线 T1+T1b/T2–T9/修复批 F1–F7/设计批 R1-R2/在线批 M1）；`subs` 包落地（8 模块）+ nber RSS 转主 + 9 preset + `crawler subs watch`；D-030/D-031 新 ADR；AC-6 四条 PASS，fable 签署"达成"；门禁 3056→3820/28/98.99%；T10 收尾：[phase6-report](../reports/2026-07-26-phase6-report.md) + 幻影字段清账 + design/09 转 implemented + GLOSSARY 增量 |
