---
title: 项目进度跟踪
status: approved
owner: fable5
updated: 2026-07-26
---

# 项目进度

> 本文件是"当前状态"的单一事实来源。每次工作 session 结束时更新。
> 历史细节见 `docs/logs/`；阶段总结见 `docs/reports/`。

## 当前快照（2026-07-26）

- **当前 Phase**：6（订阅与搜索）**全部任务卡与 AC-6 验收已闭合**（2026-07-26，`main` @ `e80f213`；门禁 **3820 passed / 28 skipped / 覆盖率 98.99%**、EXIT=0；`tag phase-6` **待 controller**——opus 全分支终审后打，本次 T10 收尾仅产出文档链）。**21 卡**5 波次全交付（主线 T1+T1b/T2–T10 共 11 卡、修复 F1–F7 共 7 卡、设计 R1/R2 共 2 卡、在线 M1 共 1 卡；T1b/F7 系执行期间增补卡，已按 F6"定稿增补卡"先例补入 phase6-implementation-plan.md §4/§5）（该文档 §5 波次并行图与实际合并顺序吻合）：
  - **主线**（新包 `src/paper_crawler/subs/`，8 模块 model/types/compile/filter/guard/watermark/watch/report）：T1 订阅 DSL 模型+解析校验+`SubscriptionRepo`（接口冻结件产出，供 T2/T3/T4/T5/T6/T8 消费）；T2 六源查询编译器（`Subscription→CompiledPlan`，逐源能力映射对齐 design/09 §3）；T3 本地过滤器+护栏引擎（正则命中矩阵+`max_new_per_run` 熔断判定+过载报告数据结构）；T4 watermark 增量语义三策略（日期上界+重叠窗/日期游标/id 集合差分，序列化 `subscription.watermark_json`，推进纪律=成功才推进）；T5 watch runner + `crawler subs watch` CLI（批内去重+参数下达面+熔断编排，与既有 `crawler watch <venue>` 语义分离共存）；T6 日报渲染（`render_daily` 纯函数，golden 快照三例字符级稳定）；T7 nber program RSS watch 转主通道（19 feed 中 5 个 `[LIVE]` 实证：AP/CF/EFG/IFM/ME，其余未点名代码不臆造，proxy year 缓解 `min_year` 系统性排除）；T8 9 个预置 topic 包（`subscriptions/presets/`，经典论文标题回归实测修复 P1×7）；T9 AC-6 离线端到端验收+在线冒烟（[AC-6 记录](../testing/records/2026-07-26-ac6-acceptance.md)：四条判据**建议 PASS**，fable 亲验签署**达成**）。
  - **修复批**（审计遗留 F1–F7，全部独立交付、与主线零文件交集）：F1 AC-3.4 合并顺序无关修复（弱信号候审匹配键改**观测级键集合**，新表 `paper_weak_key`，D-031）；F2 config 畸形 TOML 错误分类修正+三处文档滞后修正；F3 aaai_ojs 历史卷冷回填窗口分区修复（跨卷缓存，冷回填请求数 O(历史届数×全库页数)→O(全库页数)）；F4 静默降级六项清账（响亮失败优于静默空结果）；F5 测试基建（canary 集合等值自断言根治"注册了却没验证"反模式第三次复现+migrations 连接纪律+周跑 launchd/cron 模板）；F6 CF-403 头级判定 S-c+冷却键粒度 E-1（D-030 裁决的两项 httpx 路径缺口实现，全库 fixture 扫描零翻转）；F7 watch 在线可用性两接缝修复（arxiv `since` 下达+ssrn 日窗服务端下推，AC-6 记录 §4 已知限制 #1/#2 转"已修复"）。
  - **设计批**：R1 browser-fetch 横切件详设定稿（`docs/design/11-browser-fetch.md` approved，D-030：形态采案 A 薄接缝最小件+CF-403 契约演进 S-c+冷却键粒度 E-1；**实现未落地**，草案验收标准 `AC-BF.x` 待落地 Phase 转正）；R2 repec enrich 通道 + ssrn 覆盖候补 ladder 合并评估定稿（repec 判"再缓"、定档 Phase 7 首批候选，前置探针 P1-P3 三项全绿"GO"；ssrn ladder (b) RePEc 交叉核对出列、(c) 浏览页 census 永久否决、(a) OpenAlex 补枚举条件立卡 Phase 7 stretch）。
  - **在线批**（全部谨慎执行、逐请求入 obslog，详见 phase6-report 在线预算台账）：M1（econsoc UNRESOLVED 部分闭合+aaai A⑥⑦复查+aea ISSN 转 `[LIVE]`+OpenAlex 抽样供数 R2，15/35 预算）+ repec 前置探针（6/6，R2 供数）+ acl_anthology SI 附件 URL 核实（1，独立小项）+ T7 nber RSS 5 feed 坐实（4，新增请求）+ T9 AC-6 冒烟（3/15）+ F7 接缝复验（3/6，controller 特批）+ T9 环境连通性探测（2，不占预算行，AC-6 记录 §3.4 如实并记）——**已知可核实的在线请求合计 34**，全部在 phase6-implementation-plan.md §3 ≤60 名义预算内；**机动 ≤10 行台账缺口**：repec 探针(6)+acl_anthology(1)+T7(4)=11，三次独立会话各自据静态余额推算（而非共享运行时账本）导致轻微超线 1 请求，如实登记（phase6-report 事件与教训）。
  - 门禁轨迹：3056（phase-5 终态）→**3820 passed / 28 skipped**（+764 测试），coverage 98.78%→**98.99%**（Phase 6 期间中途峰值 99.00%，F7 卡新增测试行数比例小幅拉低末位小数）。adapter 数**不变**（仍 20——Phase 6 未新增平台 adapter，仅扩展既有 `nber` 的 RSS 通道）；venue 数**不变**（仍 58，仅 `aeri`/`jel`/`nber` 三个既有 YAML 的 ISSN/quirks 字段小改）。新 ADR：**D-030**（browser-fetch 横切件形态定稿案 A+CF-403 契约演进 S-c+冷却键粒度 E-1）、**D-031**（弱信号候审观测级键集合+tie-break 复合序）。报告：[phase6-report](../reports/2026-07-26-phase6-report.md)（opus 全分支终审"**放行附条件**"——零 P0/代码缺陷/红线、门禁逐位复现；六项文档修正条件已闭合，`tag phase-6` 待 controller）。→ 下一 Phase：7（全文抽取与库增强）**待用户令**，开工检查单见 phase6-report「Phase 7 开工检查单」节
- **待补验（不阻塞，如实记录，沿自 Phase 5 快照 + 本 Phase 新发现）**：S2 API key 未到（D-021 SKIP 门控）；elsevier API key 未到（**BLOCKER-1**，AC-4.1 真实取回归 T7b，跨 Phase 3–6 四阶段仍未清）；wiley TDM token 未到；D-019 锚点表 openalex/s2 锚点仍 `[PENDING]`（需 key/credit）；aaai **全文回填批**（~5049 篇，≈2.8h@30rpm+5–15GB）待用户令另行插单（enumerate 侧成本已由 F3 降至 0 请求，仅剩 fetch 阶段待令）；econsoc `[UNRESOLVED①④]`（ECMA 是否全刊 OA / 过刊运行期终态）遇 Cloudflare 交互质询维持未解决——`econometricsociety.org` 对本项目当前存在质询风险，与 2026-07-24 勘察畅通结果不一致，成因未定性，建议提升 canary 优先级；`economics-journals.md` ECMA 行 adapter 字段与 `publishers-platforms.md` 仍不一致（Phase 5 T8 已登记 `spawn_task`，本 Phase 未处理，跨 Phase 5-6 未清）；**新增（F7 期发现，转 Phase 7）**：arxiv `search_query`（分类组+关键词布尔式）结构性无本地补偿谓词、且 venue 路由只取首个分类，多分类订阅实际只收一类；nber 隔离在线验证+`asset-pricing` preset CLI 端到端补验（F7 §4.1a 残留，controller 亲验裁定转 Phase 7、风险低——T7 已有 5/5 feed `[LIVE]` 证据）。
- **总体进度**：Phase 0/1/2/3/4/5/6 = 100%（tag `phase-0`…`phase-5` 全落；`tag phase-6` 待 controller）；Phase 7（全文抽取与库增强）planned **待用户令**。新 ADR（Phase 6）：D-030/D-031
- **待用户执行**：①S2 API key 申请（`config.toml [auth.s2] api_key`）；②Elsevier API key 申请（**BLOCKER-1**，`config.toml [auth.elsevier] api_key`，外部依赖，跨 4 个 Phase 未清）；③Wiley TDM token 申请（自助 click-through，`config.toml [auth.wiley] token`）；④oup SSO/campus cookie 首登 runbook（T7b）；⑤`config.toml [identity].email` 补配；⑥Kaggle key 状态复核（跨 5 个 Phase 未清）；⑦aaai 全文回填批用户令（~5049 篇，成本已注②）；⑧Phase 7 开工令（届时按 phase6-report「Phase 7 开工检查单」节开工）
- **阻塞**：无（elsevier key 为计划内外部依赖；econsoc Cloudflare 质询风险与机动预算台账缺口均非阻断、已如实登记）

## Phase 进度板

| Phase | 状态 | 进度 | 备注 |
|---|---|---|---|
| 0 设计与文本系统 | done | 100% | 报告：reports/2026-07-20-phase0-report.md |
| 1 核心框架 | **done** | 100% | 报告：reports/2026-07-21-phase1-report.md；tag phase-1 + schema-v1 |
| 2 Open-Access MVP | **done** | 100% | 报告：reports/2026-07-22-phase2-report.md；tag phase-2；openreview 在线层已于 Phase 3 期间补验 PASS（用户 token 到位，见下） |
| 3 聚合元数据层 | **done** | 100%（tag phase-3） | 全部任务卡合并+汇总验收最终签署（AC-3 全 PASS/AC-0 全 PASS/预算零超支）；验收：testing/records/2026-07-23-phase3-acceptance.md |
| 4 认证框架+出版社 | **done**（tag `phase-4`） | 100% | 全部任务卡合并；AC-4.2~4.6 离线 DoD PASS（T7a）+ controller 终验签署；AC-4.1 真实凭证归 T7b（D-018，不阻塞，跨 Phase 遗留见下）；验收：testing/records/2026-07-23-ac4-acceptance.md；报告：reports/2026-07-23-phase4-report.md |
| 5 SSRN 与特殊源 | **done**（tag `phase-5` @ `c577d6c`） | 100% | 8 卡 4 波次全交付（T1 crossref 两轴扩展/T3 nber/T4 ssrn/T5 aea/T6 econsoc+wiley 联动/T7 AC-5 正式化/M1 census/T8 收尾）；AC-5 四条 PASS + 5.1b N/A defer Phase 6；4 新 adapter（16→20）+ 13 新 venue（45→58）；门禁 3056/28/98.78%；验收：testing/records/2026-07-24-ac5-acceptance.md；报告：reports/2026-07-24-phase5-report.md（终审判定：**达成**）；终审后独立全库审计：reports/2026-07-24-post-phase5-audit.md（八域附条件达标、零 P0，发现入 Phase 6 检查单） |
| 6 订阅与搜索 | **done**（tag `phase-6` 待 controller） | 100% | 21 卡 5 波次全交付（T1 DSL 地基+T1b 接缝终裁/T2 编译器/T3 过滤+护栏/T4 watermark/T5 watch runner+CLI/T6 日报/T7 nber RSS/T8 9 preset/T9 AC-6 验收 + F1–F7 修复批（含 T9 后增补的 F7）+ R1/R2 设计批 + M1 在线批）；AC-6.1~6.4 离线 DoD 四条 PASS，fable 亲验签署"达成"；门禁 3056→**3820 passed/28 skipped/98.99%**（+764 测试）；adapter/venue 数不变（20/58，本 Phase 不新增平台）；新 ADR D-030/D-031；实施计划：[phase6-implementation-plan](phase6-implementation-plan.md)；验收：[2026-07-26-ac6-acceptance.md](../testing/records/2026-07-26-ac6-acceptance.md)；报告：[phase6-report](../reports/2026-07-26-phase6-report.md)（opus 终审"放行附条件"，六项文档修正条件已闭合；tag `phase-6` 待 controller） |
| 7 全文抽取与库增强 | planned | 0% | 待用户令；开工检查单见 [phase6-report](../reports/2026-07-26-phase6-report.md)「Phase 7 开工检查单」节 |

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
