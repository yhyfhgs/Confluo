# Phase 4 阶段报告 — 认证框架 + 出版社 adapters（2026-07-23）

> 格式仿 [2026-07-23-phase3-report.md](2026-07-23-phase3-report.md)。**本稿为 T8 收尾中草稿**：
> AC-0 系统性扫描本次由 T8 独立执行（§2）；AC-4.2~4.6 判定引自 [AC-4 离线汇总记录](../testing/records/2026-07-23-ac4-acceptance.md)
> （T7a draft，尚待 controller 终验签署）；`tag phase-4` **未打**（controller 亲打，T8 职责边界之外）。
> 判定列（DoD 表 + AC-0 表）由 T8 填证据，最终逐条判定占位 `[待 controller 终审签署]`——
> 判定依据：[development-plan §Phase 4](../plan/development-plan.md)、
> [acceptance-criteria AC-4/AC-0](../testing/acceptance-criteria.md)、
> [phase4-implementation-plan](../plan/phase4-implementation-plan.md)、
> [AC-4 离线汇总记录](../testing/records/2026-07-23-ac4-acceptance.md)、
> [decision-log D-023/D-024/D-025](../plan/decision-log.md)。
> 代码版本：`main` @ `911df8d`（`tag phase-4` 待前述项收口后由 controller 打）。
> `phase-3..HEAD` 共 **63 commits / 14 merges**——14 次 merge 精确对应
> phase4-implementation-plan §4 的任务卡（R0 + W0 + M2a + M2b + T1a + T1b + T2 + T3 +
> T-wiley + T4 + T6 + T5 + T7a，另一次为 W0 内部分支合流）；T8 尚未产生独立 merge（文档收尾，无代码分支）。

## 1. DoD 判定

development-plan.md Phase 4 DoD 原文："验收场景 AC-4.x（如"保存的机构 session 下载 1 篇 JFE
正式版 PDF；session 过期后被正确检测并提示重登"）；全部认证 adapter 默认限速符合各自文档声明；
BLOCKED 人工介入流程演练通过。"AC-0 红线（每 Phase 强制基线）与 `make check`/覆盖率门禁一并列入
本表。

| DoD 项 | 判定 | 证据 |
|---|---|---|
| AC-4.1 首登+取一篇（`auth login` → `grab --doi` 得合法 PDF，魔数校验过） | **PASS（离线载体 + runbook 就位）** | 离线：`tests/unit/test_cli_grab.py` 6 用例（grab 三退出码全链骨架，含"未入库→crossref lookup→建行→resolve+fetch"路径，本次亲跑通过）+ `tests/unit/test_auth_cli.py` 19 用例（`login`/`status`/`logout` 全分支，含 `test_login_api_key_missing_exit_2_with_guidance` 等 guidance 断言，本次亲跑通过）。真实 API 冒烟（JFE DOI 经 Elsevier Article Retrieval API 取回、`%PDF` 魔数校验）因 **BLOCKER-1**（R0 [LIVE 2026-07-23] 确认 config/env 无 elsevier key，外部依赖 1–2 周）按 D-018 分层归 **T7b**；`tests/manual/elsevier_runbook.md`/`oup_runbook.md`/`wiley_runbook.md` 三份 runbook 已就位（含前置凭证配置/退出码判据/`%PDF` 判据清单），**不阻塞** T8 离线收尾与 tag |
| AC-4.2 过期检测不轰炸 | **PASS（离线）** | [AC-4 离线汇总记录](../testing/records/2026-07-23-ac4-acceptance.md) §1：T5 批级门 5 用例 + T6 provider 层双源 4 用例；`test_auth_pipeline.py` 31 passed / `test_auth_lifecycle.py` 10 passed（本次随全量 `make check` 复跑吻合） |
| AC-4.3 无权限降级 | **PASS（离线）** | 同上记录 AC-4.3：真实 `ElsevierScienceDirectAdapter` resolve entitlement:false→NE→unpaywall OA 兜底全链（fable 审查 MAJOR-1 修复的端到端断言，`test_elsevier_resolve_entitlement_false_derives_oa_fallback`）+ 泛 mock 全链 + 7 边界用例 |
| AC-4.4 日配额 | **PASS（离线）** | 同上记录 AC-4.4：`count_fetch_today` 的 `DATE(ts)` 对账 3 用例，含 controller 令对照用例（真实 `config.toml` 字段 vs getattr 默认值） |
| AC-4.5 登出无残留 | **PASS（离线）** | 同上记录 AC-4.5：`test_lifecycle_05_logout_forensic_wipe_full_home_tree` 全 home 目录树逐文件字节扫描（非局限已知路径）+ store 层取证式覆写删除 4 用例 + manager 层按 kind 分列 6 用例 |
| AC-4.6 风控即停 | **PASS（离线）** | 同上记录 AC-4.6：冷却持久化 3 用例 + provider 双路径（`health_check`/`refresh`）一致性 2 用例 + `ChallengeDetector` 特征库判定器 23 用例（本次逐行复核零 solve/bypass 代码，见 §2 AC-0.2） |
| AC-0 五条红线 | **全 PASS** | 本报告 §2 AC-0 系统性扫描——本次 T8 独立执行 grep/源码复核 + 转录 controller 亲检 AC-0.3 结果，五条逐条列证据 |
| 全部认证 adapter 默认限速符合各自文档声明 | **PASS** | `elsevier_sd`/`oup_silverchair`/`wiley` 三 `default_rate.source_note` 与 [R0 LIVE 2026-07-23 复核](../research/site-survey/publisher-platforms-p4-recheck.md) 交叉核对一致，本次逐 adapter 源码复核（§2 AC-0.5 详述） |
| BLOCKED 人工介入流程演练通过 | **PASS（离线）** | pipeline BLOCKED 状态携可读 `blocked_reason`（如 `"session expired；refresh 失败 → 整批 BLOCKED(auth)"`，`runner.py`）；`auth status` 暴露 EXPIRED/CHALLENGED 供人工判读；`auth login` 缺 key/token → exit 2 + guidance 文案指引重新配置（`test_login_api_key_missing_exit_2_with_guidance`）；真实平台撞墙演练（Cloudflare 挑战墙等）随 canary 周检 + T7b runbook 归线上口径，离线状态机转移已被 T5/T6 套件充分锁定 |
| `make check` 全绿 / 核心覆盖率 ≥80% 不回退 | **PASS** | 本次终检亲跑 `make check` exit 0：**2712 passed / 21 skipped / 98.84%**（21 skip 全为 `test_adapter_contract.py` 能力缺口预期 skip：8 例 openalex/s2 duck-typed enrich 不参与协议 + 13 例各 adapter 缺 DISCOVER/ENUMERATE/RESOLVE/FETCH 之一；零凭证门控 skip 混入本离线套件）；较 phase-3 tag 的 99.18% 微降 0.34pp，系新增 8374 stmts 中 64 miss 的防御分支+待补单测增量（§5 已知限制逐条列） |
| auth 包 + 三平台 adapter 覆盖 ≥90% | **PASS** | 本次亲测：`auth/` 全 12 文件 100%；`elsevier_sd`/`oup_silverchair`/`wiley` 三 adapter 的 `adapter.py`/`parse.py` 全部 100% |

## 2. AC-0 系统性扫描（2026-07-23，T8 独立执行）

> 判定依据：[acceptance-criteria.md](../testing/acceptance-criteria.md) AC-0.1~0.5 原文；范式仿
> [phase3-acceptance.md §3](../testing/records/2026-07-23-phase3-acceptance.md)。**AC-0.3 的 git 全历史扫描
> 由 controller 于 2026-07-23 亲执**（T8 worktree 零在线、非 git-history 取证角色）——本节转录其结论并附
> T8 本次可独立核验的旁证（sensitive.py 脱敏键在位性、worktree 内 dangling object 抽查）；其余四条
> （AC-0.1/0.2/0.4/0.5）为本次 T8 独立执行的 grep + 源码复核。

### AC-0.1 · 盗版源集成点 — **0 命中，PASS**

`grep -rniE "sci-hub|scihub|libgen|library genesis|z-library|zlibrary|annas-archive|sci hub"`
覆盖 `docs/` 与 `src/`：

- `src/` 全仓库 **0 命中**。
- `docs/` **3 处命中**，逐条核实均为红线条款自述，非集成点：
  1. `docs/research/github-similar-projects.md:49` — PyPaperBot 项目评估笔记："合规排除：下载兜底链含 Sci-Hub/SciDB——仅借鉴其'来源优先级顺序尝试'编排形态，数据源本身排除（AC-0.1）"。
  2. `docs/design/00-requirements.md:82` — 需求红线原文："绕过付费墙：无有效凭证时不通过任何灰色渠道获取闭源全文（不集成 Sci-Hub/LibGen 等）"。
  3. `docs/testing/acceptance-criteria.md:95` — AC-0.1 判据条款本身。

**判定：PASS**（与 Phase 3 §3① 结论一致，Phase 4 新增代码零引入）。

### AC-0.2 · CAPTCHA 求解 — **0 命中，PASS**

`src/paper_crawler/auth/challenge.py`（`ChallengeDetector`）逐行复核（164 行全文本次通读）：
模块 docstring 自陈"**防御性判定器**：只做'命中特征 → 如实分类'……**本模块不含任何求解/绕过/重试逻辑**"；
`classify()` 方法体仅含字符串/头部特征比对 + 优先级判定返回四态 `ClassifyResult`（`OK`/
`LOGIN_REDIRECT`/`NO_ENTITLEMENT`/`CHALLENGE`），**零网络请求、零异常抛出、零重试循环**——命中
CHALLENGE 后上游一律 `Challenged` → BLOCKED + 平台冷却（AC-4.6），无任何路径尝试规避。

`src/paper_crawler/` 全量精确 grep（词边界，排除 "resolve" 对 "solve" 的误命中）：

- `\bcaptcha\b`：3 处，均为 docstring/注释描述判定特征（`errors.py:78`、`challenge.py:25,50`），非求解代码。
- `\bsolve(s|d|r|rs)?\b|\bsolving\b`：**0 命中**。
- `\bbypass(es|ed|ing)?\b`：**0 命中**。
- `\bcircumvent|\bcrack(s|ed|ing)?\b|\bdefeat(s|ed|ing)?\b`：**0 命中**。

`docs/` 全量 "captcha" 命中 **33 处**，抽查 20 处（含全部 Phase 4 新增设计文档命中）逐条为
BLOCKED 处置设计描述（如 `04-auth-gated-module.md:55`"检测到 CAPTCHA…→ 立即 BLOCKED + 停止该
平台全部队列 + 冷却"；`auth-framework.md:766`"AC 对应：…AC-0.2（无 CAPTCHA 求解）"）或勘察记录
"未遇到 CAPTCHA"类客观陈述，无一处描述求解/外包/绕过方案。

**判定：PASS**（引 T1a 冻结件实体化审查 + 本次独立复核，双重核实一致）。

### AC-0.3 · git 全历史无凭证/PDF — **PASS（controller 亲检转录 + T8 旁证）**

- **controller 亲检结果（2026-07-23，转录）**：git 全历史扫凭证态 blob（`.enc`/`.filekey`/
  `profiles.toml`/`storage_state`）**零命中**；git 全历史扫真实 PDF **零真实 `.pdf`**（仅
  `.pdf.bin` 合成占位——`f99b3d5` 修复的 wiley fixture 命名教训延续，见 §5 过程质量机制）。
  本条判定权威来源为 controller 本人扫描，T8 未重跑（任务边界；worktree 起点 `911df8d` 已是
  controller 核验后的状态）。
- **T8 本次核验的脱敏键在位性**（AC-0.3 的运行时对应护栏，`src/paper_crawler/sensitive.py`
  逐行复核）：`REDACT_KEY_PATTERN`（obslog 脱敏用）含核心凭证键 `set-cookie`/`cookie`/
  `authorization`/`token`/`api[_-]?key`/`password`/`secret`/`session[_-]?id`/`insttoken`/
  `inst[-_]?token` + obslog 专属追加 `email`/`x-els-apikey`/`tdm[-_]?token`/
  `wiley-tdm-client-token`；`obslog.py:41,52` 确认 `_SENSITIVE_KEYS = REDACT_KEY_PATTERN`
  单一权威源接线（D-025，两处消费方不再各自维护正则副本）。
- **T8 本次旁证（worktree 本地 git object 抽查，非替代 controller 全历史扫描）**：
  `git fsck --unreachable --no-reflogs` 在本 worktree 发现少量 dangling commit/tree/blob
  （3 个 dangling commit，日期均为 2026-07-21/22，早于 Phase 4 启动）——逐一核验其中一个为
  `git stash` 遗留对象（"WIP on main: …"消息格式，日常操作痕迹）、另两个为普通全量 tree 快照
  （`git ls-tree` 核对内容为常规 docs/src 文件，无凭证/PDF 形态文件名或内容）。**未发现**任何
  filter-branch 式历史重写的直接证据（如 `refs/original/*` 备份引用）；此项旁证范围有限
  （仅限本 worktree 可达对象，非 controller 用的全历史专用扫描工具/范围），如实记录边界，不
  代为宣称已复现 controller 的扫描过程。
- **config/ 样例文件核查**（D-025 新增三文件）：`config/config.example.toml`/
  `profiles.example.toml`/`README.md` 本次逐一读取确认——`config.example.toml` 顶部注释自陈
  "本文件所有值为占位/空样例，绝不含真实凭证（AC-0.3 不变式）"，实际内容为
  `you@example.edu`/路径占位/数值默认，无真实凭证形态字符串。

**判定：PASS**（controller 权威结论 + T8 运行时护栏在位性核验 + 有限旁证一致，无矛盾发现）。

### AC-0.4 · 日志与报告无未脱敏凭证 — **0 命中，PASS**

`grep -rniE` 对 `docs/testing/records/` 与 `docs/reports/` 扫描凭证形态键值对
（`(api[_-]?key|token|password|secret|cookie|authorization|insttoken)\s*[:=]\s*['"a-z0-9]{6,}`，
排除占位/example/脱敏/N/A 类噪声）：**0 命中**。Phase 4 专属记录
（`2026-07-23-ac4-acceptance.md`）额外核查 `email`/`mailto` 关键词：**0 命中**（该记录全程离线，
未涉及 unpaywall email 查询参数场景，与 Phase 3 记录"4 处 email 均为 UA mailto 合规声明"的性质
不同——本记录压根不产生该类字段，非"有但已脱敏"而是"未产生"）。

**判定：PASS**。

### AC-0.5 · 限速 ≤ 站点声明 + robots 禁区 — **PASS**

逐平台 `default_rate.source_note` 与 [R0 LIVE 2026-07-23 复核](../research/site-survey/publisher-platforms-p4-recheck.md) 交叉核对（本次源码 + 勘察文档双向核实）：

| 平台 | robots/站点声明 | adapter 实际限速 | 合规判定 |
|---|---|---|---|
| `elsevier_sd` | `www.sciencedirect.com` robots **全禁**（`User-agent: * / Disallow: /`，具名封禁 30+ AI UA 含 ClaudeBot，[LIVE] 07-20）；`api.elsevier.com` **无 robots**（404，R0 [LIVE] 07-23，纯 API host 无路径级限制） | `domains=("api.elsevier.com",)`（源码确认**非** `www.sciencedirect.com`，页面路线不走，`adapter.py:6`）；自限 **2 req/s**（官方 10 req/s，留 5 倍余量），429 当日熔断 | **PASS**——页面路线因 robots 全禁不可行，API 为唯一正道（合规上更严格，非规避）；本次源码 grep 确认零 `www.sciencedirect.com`/禁区路径构造 |
| `oup_silverchair` | `academic.oup.com` robots 200，**无 Crawl-delay、无 AI-bot 具名条目**（R0 O1 [LIVE] 07-23 复核一致）；`*` 组禁 `/bin/ /config/ /signin.aspx /search-results /DownloadFile/ /Citation/Download /Shibboleth.sso/ /user/logout` 等，article/article-pdf 路径未禁 | 站点未声明速率上限（Crawl-delay 缺失不等于"无限速"）→ 保守默认 **1 req/6s（10 rpm）并发 1**（design/04 §4/§5 原文），`source_note` 显式记录"robots.txt (200) has no Crawl-delay and no AI-bot rule" | **PASS**——站点未强制数值时选择保守默认（而非"未禁即放飞"），符合 D-014 精神；本次源码 grep 确认零 `/bin//config//signin.aspx/…` 等禁区路径构造 |
| `wiley` | TDM API 官方声明 **3 req/s + 60 次/10 分钟**（R0 [LIVE 2026-07-23] 升级为活验：GitHub `WileyLabs/tdm-client` v1.2.0 + 搜索索引二手确证，双口径） | 双窗口用单桶 `RatePolicy(rpm=5, burst=3)` 保守表达（60/10min≈6rpm 为绝对主导约束，取 rpm=5 留 1/min 头寸；burst=3 令第 4 连发等 60/5=12s，源码注释推导过程详见 `adapter.py:33-35`） | **PASS**——单桶算术验证：rpm=5 < 6rpm 滑动均值上限，burst=3 ≤ 3req/s 瞬时上限，双向不超官方声明；页面兜底域 `onlinelibrary.wiley.com` 本次未落码（deferred，零风险） |

**代码面禁区构造核查**：本次对三新 adapter 源码 grep 各自 robots `Disallow` 清单中的具体路径
片段（如 `/bin/`、`/config/`、`/signin.aspx` 等），**零命中**——三 adapter 均只构造官方文档化的
API/资源路径。

**判定：PASS**（三平台限速声明与代码实测逐一交叉核对一致，无一处超出站点声明或误踩 robots 禁区）。

## 3. 交付清单

development-plan §Phase 4 范围逐项：

| 范围项 | 交付 |
|---|---|
| 认证框架本体（T1a 冻结件 + T1b 实体） | `src/paper_crawler/auth/`：`protocol.py`（`AuthProvider` 五方法 Protocol 冻结）、`challenge.py`（`ChallengeDetector` 四态判定器）、`store.py`（`CredentialStore` AES-GCM 加解密 + keyring↔文件密钥降级链）、`providers/{api_key,cookie_session,ezproxy,sso_flow}.py`（四实现）、`manager.py`（`AuthManager` 编排入口）、`browser.py`（Playwright 薄封装，惰性 import）、`cli.py`（`auth login/status/logout`）——12 文件全 100% 覆盖 |
| 平台地基件（T2） | `config.py` 四层加载链改造（D-025）+ 项目级敏感键护栏 + `crawler config show`；`errors.py`/`http.py` 结构化 `status_code` 权威版（`AuthRequired`/`Challenged` 子类）；`crawler canary` 凭证注入装配；`src/paper_crawler/sensitive.py`（脱敏键单一权威源，obslog + config 护栏共享） |
| config/ 归集（D-025） | `config/README.md`（配置规范总纲）+ `config/config.example.toml`（全键注释样例）+ `config/profiles.example.toml`（四 kind profile 样例，真实值绝不入） |
| `elsevier_sd` adapter（T3，AC-4.1/4.3 载体） | `adapters/elsevier_sd/{adapter,parse}.py`：官方 API 档（`api.elsevier.com`，非页面路线）、entitlement 预检、429 保守熔断（当日 circuit breaker）、stub 正式退役；100% 覆盖 |
| `oup_silverchair` adapter（T4，QJE 收敛#2 + AC-4.6 载体） | `adapters/oup_silverchair/{adapter,parse}.py`：cookie/SSO 双 profile 档、`ChallengeDetector` 四类判定接线、QJE `fulltext_source` 收敛完成（不再借用 `elsevier_sd` 占位）；100% 覆盖 |
| `wiley` adapter（T-wiley，D-024 R0 裁决纳入） | `adapters/wiley/{adapter,parse}.py`：TDM API 档、双窗口限速单桶表达、`resolve_offline=True`（纯 URL 构造零网络）；100% 覆盖 |
| pipeline 集成 + grab（T5，AC-4.2~4.6/OA-fallback 载体） | `pipeline/{runner,stages}.py` 全接线：no_entitlement→unpaywall OA-fallback 全链、批级健康门（`_BatchGate`）、日配额对账（`FetchLog` `DATE(ts)`）、挑战冷却持久化（24h 跨运行）、工作时段窗；`cli.py` 新增 `grab --doi` 单篇精取命令 |
| mock IdP 集成测试（T6，AC-4.2/4.5/4.6 离线载体） | `tests/integration/test_auth_lifecycle.py`：provider 层全生命周期五段真证（探测/续期/登出/双源/双路径） |
| AC-4 离线汇总验收（T7a） | [AC-4 离线汇总记录](../testing/records/2026-07-23-ac4-acceptance.md)：AC-4.2~4.6 逐条判定 + 亲跑台账 275 passed（auth 全离线套件） |
| 真实凭证 runbook（T7b 载体，游离于本次离线收尾） | `tests/manual/{elsevier,oup,wiley}_runbook.md` + `tests/online/test_{elsevier,oup,wiley}_smoke.py`（key/token 门控 skipif）+ `tests/helpers/{auth,elsevier_fixtures,oup_silverchair_fixtures,wiley_fixtures}.py` |
| 在线债务清理（M2a） | D-019 四站锚点核准（pmlr/cvf/acl_anthology/neurips_proceedings，12 请求 [LIVE 2026-07-23]，`a56a065`）；aaai_ojs 全库 OAI 量级评估（~262 req，仅评估未执行）；`neurips_proceedings` dblp_slug 纠正（`conf/nips/nips2023`→`conf/nips/neurips2023`） |
| 离线债务清理（M2b） | 测试补强批（cursor 中断→窗口重建→DOI 去重端到端 fixture；oa-report 循环端到端限速锁；契约 factory 补齐）；`progress.md` 模块状态表首次重建（自 Phase 1 起未更新的旧表清零）；`budget.py` 跨进程 `fcntl.flock` 加固 |
| 合规/文档 | D-023/D-024/D-025 三条新 ADR；`elsevier-sd.md`/`oup-silverchair.md`/`wiley.md` 三平台实现级详设（review→approved→**implemented**）；`auth-framework.md`/`10-config-layout.md`/`07-auth-session.md`/`04-auth-gated-module.md` 四篇框架级详设转 **implemented**（本次 T8） |

统计：**63 commits**（`phase-3..HEAD`，含 **14 次 merge**）——14 次 merge 精确对应
phase4-implementation-plan §4 的任务卡（R0/W0/M2a/M2b/T1a/T1b/T2/T3/T-wiley/T4/T6/T5/T7a，
另一次为 W0 内部分支合流）。测试从 phase-3 tag 的 **2154 passed / 24 skipped**（99.18%）增至
终态的 **2712 passed / 21 skipped**（98.84%）；新增 22 个 `src/` 文件（auth 包 12 + 三 adapter
包 9 + `sensitive.py` 1）、47 个 `tests/` 文件（含 `tests/manual/` runbook 3 篇、`tests/online/`
smoke 3 篇、`tests/helpers/` fixture 助手 4 篇）、3 个 `config/` 规范文件；整体 **136 files
changed / +17306 / -582**（`git diff --shortstat phase-3..HEAD`）。已注册 adapter 由 13 个
（Phase 3 末）增至 **16 个**（新增 `elsevier_sd`[stub 转真实]/`oup_silverchair`/`wiley`，stub
清零）；`crawler venues lint` 本次亲跑 `OK：45 个 venue 全部通过 lint`（含 `qje.yaml`
`fulltext_source` 收敛）。

**在线预算台账**（plan §3 契约 ≤120）：

| 分项 | 实际 | 备注 |
|---|---|---|
| R0 平台勘察复核（elsevier API/oup URL·挑战态/wiley TDM/acm ToS） | 5 | keyless E2 429 一次即停、oup O2 403 challenge 记录即停、robots ×3；[publisher-platforms-p4-recheck.md](../research/site-survey/publisher-platforms-p4-recheck.md) |
| M2a：D-019 四站锚点核准（pmlr/cvf/acl_anthology/neurips_proceedings） | 12 | dblp.org，UA 携 mailto，Crawl-delay:4 合规；`a56a065` |
| elsevier 真实 key 冒烟 / wiley token 冒烟 | 0 | 均门控待 T7b（key/token 未到位，D-018 分层） |
| D-019 补跑缓冲 / aaai OAI 全库收割 | 0 | 前者预算充足未耗用；后者仅完成量级评估（262 req 估算），未批量执行（见 §6 检查单 #4） |
| **合计** | **17** | 远离 ≤120 预算硬顶，零超支 |

## 4. 过程与质量机制

- **W0 双评审拦截 3 BLOCKER**：`auth-framework.md`/三平台详设/`10-config-layout.md` 详设包首轮
  评审 A **Reject**（3 BLOCKER + 7 MAJOR + 5 minor）、评审 B **Approve-with-fixes**（4 MAJOR +
  5 minor），修订轮逐条闭合（`e221a29`，见 auth-framework.md §14 修订记录 #3）：核心闭合项含
  OA-fallback 取回全链缺失（A-B1）、日配额口径三处不统一（A-B2/B-m5）、工作时段窗缺失（A-M2）、
  一次性 user-data-dir 清理缺失（A-M7）、假时钟注入缺失（B-M1）、fixture 未按平台分形态
  （B-M3）、canary SKIP 语义未钉死（B-M4）——若未拦截，其中多项（尤其 OA-fallback 全链缺失）
  会直接导致 AC-4.3 在实现期落地时结构性缺失，而非到 T5 才被 fable 二次抓获（见下条）。
- **fable 缝合面审查抓 MAJOR-1（AC-4.3 真实缺口）**：T5 merge 前 fable 审查发现 NO_ENTITLEMENT
  的 `oa_fallback` 派生**仅在 `kind=="fetch"`**（asset_id 门控）时触发，**resolve 阶段 NE 不
  派生**——直接违反 auth-framework §8.1 接线点 A"fetch 失败 **或** resolve entitlement 预检
  否"的原文，而 `elsevier_sd` 恰好在 **resolve** 阶段做 entitlement 预检抛 NE（无权 DOI），
  若不修复，真实场景下 elsevier 无权 DOI 将**得不到** Unpaywall 兜底——AC-4.3 字面判据"给出
  Unpaywall 副本（若存在）"落空。修复（`99d6f1b`）：resolve NE 从 `params["paper"]` 派生（`_enqueue_oa_fallback` 改收
  `paper_id`），并补端到端测试（真实 `ElsevierScienceDirectAdapter` 场景，非泛 mock）锁定回归。
  同批修复 MAJOR-2（§8.2 INTEGRITY→健康门归零联动未实现，防伪装 PDF 连环命中的机制缺失）。
- **wiley fixture 合并事故**：T-wiley 分支 worktree 本地 `make check` 全绿、opus 审查
  Approve，但合并后 `main` 门禁复跑抓到 **3 测试红**——根因是 `.gitignore` 的 `*.pdf` 规则
  吞掉了一个作为 untracked 文件存在于 agent 磁盘的 PDF fixture（本地能通过是因为文件**确实
  在磁盘上**，但从未进 `git add`/`commit`，故 worktree 本地绿 ≠ 分支内容完整——这正是"合并
  亲跑门禁"作为最后一道防线存在的理由）。修复（`f99b3d5`）：fixture 改名 `.pdf.bin` 入库
  （避开 `.gitignore` 的 `*.pdf` 规则，同时延续 Phase 3 已确立的"git 历史零真实 `.pdf`"
  不变式，见 §2 AC-0.3）。
- **git 历史安全检查（filter-branch 类操作）**：controller 于 2026-07-23 对 git 全历史执行
  凭证态 blob 与真实 PDF 扫描，确认零命中（§2 AC-0.3 转录）；**T8 未能在本 worktree 独立
  复现该操作的具体触发原因或执行细节**——本 worktree 以 `911df8d` 为起点，该状态已是扫描后
  的确认清洁态，git-history 取证不在 T8 的 worktree 隔离 + 零在线职责范围内。T8 本次做的是
  有限旁证（worktree 内 `git fsck --unreachable` 抽查，见 §2 AC-0.3 第三条），发现的 dangling
  object 均为日期早于 Phase 4、内容为普通 stash/tree 快照的常规调试痕迹，**未发现**与
  该安全检查直接对应的证据链。如实记录此边界：本条目的"过程质量"意义在于——即便在一个
  以"文档先行、双评审、fixture 纪律"为核心防线的项目里，git 历史卫生仍需要 controller 层面
  独立于代码评审之外的专项检查兜底，这本身是防线设计的合理延伸，而非某个环节失职的证据（本
  报告未见可归因于具体某任务卡的失误细节，不作无据推断）。
- **config knobs 编排缝隙（controller 裁决闭合）**：T2 任务卡范围写"config 分层加载"，
  T5 任务卡因"config.py 归 T2 独占"的分工原则而**假定** §8 运行时 knob（`auth_daily_cap`/
  `auth_health_interval`/`auth_health_max_age_s`/`auth_work_hours`/`oa_fallback_rate_rpm`/
  `auth_active_profile`）已由 T2 落地——但 T2 范围描述实际只覆盖了**凭证槽**（`[auth.*].
  api_key`/`token`），未包含这些**运行时行为参数**，两边"都以为对方认领"，造成真实缝隙
  （pipeline 侧靠 `getattr` 兜底默认值运行，功能不受影响，但 `config.toml` 显式配置这些
  项**不会生效**——这是一个"测试全绿但用户配置被静默忽略"的隐蔽缺陷类别）。controller
  亲裁后补真实 Config 字段（`3c022b1`，commit message 显式标注"controller 裁决"），
  `runner.py`/`stages.py` 的既有 `getattr` 兜底自动接住新字段、消费侧零改动；新增
  `test_runner_reads_real_config_field_not_getattr_default` 类对照用例，专门区分"读到
  真实配置值"与"读到 getattr 默认值恰好相同"两种表面等价、语义不同的情形。
- **fixture 纪律延续**：`wiley` fixture 合并事故（上条）促使 PDF 类 fixture 统一走
  `.pdf.bin` 命名入库，延续 Phase 3"合成假设是盲区源"教训在文件层面的具体化——`.gitignore`
  的宽泛规则本身没错（防真实 PDF 误入库是 AC-0.3 不变式），但需要 fixture 命名规范与之配合，
  而非依赖"本地能跑"作为入库完整性的替代证据。

## 5. 已知限制（如实记录）

- **AC-4.1 真实 API/token 冒烟未执行**：BLOCKER-1（elsevier key，外部依赖 1–2 周）+ wiley
  token（自助可得但本次未申请）均未到位；`oup` SSO/campus cookie 首登为纯人工 runbook，本
  Phase 未执行。三份 runbook 已就位（`tests/manual/`），按 D-018 分层不阻塞离线 DoD/tag，
  移交 T7b（见 §6 检查单）。
- **`test_cli_canary.py` 断言列表遗漏 `oup_silverchair`/`wiley`**（本次 T8 复核新发现）：
  `tests/integration/test_cli_canary.py:97-162`（`test_canary_without_filter_checks_all_
  registered_adapters`）的 adapter_id 断言列表与内联注释仍写"现 14 个"，未随 T4/T-wiley
  合并补上两个新 adapter_id——**功能不受影响**（`oup_silverchair`/`wiley` 的 `healthcheck()`
  无凭证时清洁 `raise NotImplementedError`→SKIP，同 openalex/s2 既有先例，故该测试仍全绿），
  纯断言覆盖面滞后，与 Phase 3 检查单 #15d（当时是 aaai_ojs/dblp 遗漏）同一模式的第二次出现。
  `pyproject.toml:28` 注释同样滞后（仍称"stubs（elsevier_sd）"，T3 已转真实 entry point，
  见 `pyproject.toml:44`）。两处均登记 §6 检查单，**本次 T8 未修改**（docs-only 任务边界，
  两处均是测试/构建配置文件而非纯文档）。
- **crossref adapter 覆盖率较 Phase 3 报告下降**（92–95%，此前 98–100%）：M2b 检查单 #15a
  新增的 cursor-resume 端到端测试补强未连带覆盖 `grab`（T5）新用的 `CrossrefAdapter.lookup()`
  方法与 healthcheck `[PENDING golden]` 分支——`test_cli_grab.py` 走 mock 而非真实
  `lookup()`，本次 `make check` 亲测确认（`adapter.py:226-241,265` 未命中）。非回归、纯增量
  代码缺直接单测，模块整体仍 `stable`，聚合覆盖率门禁 ≥80% 达标，不阻塞。
- **asset 路径 version 债务**（T7a 发现，design/06 缺口）：OA-fallback 产生的 OA 副本 asset
  唯一键含 `version`（如 `publishedVersion`），但落盘路径 `data/pdf/<venue>/<year>/<ulid>.pdf`
  不含 version 判别位，原平台 asset 与 OA 副本仅靠 ULID 区分——身份并存语义已被
  `test_no_entitlement_triggers_oa_fallback_direct_fetch` 验证不覆盖，但设计文档层面尚未
  显式承认此路径布局缺口。非离线 DoD 阻塞项。
- **AuthManager DI 缺口**（T6 发现）：`AuthManager.resolve`/`get` 走 provider 默认构造，
  **不支持**注入 `http_factory`/`login_flow` 测试 seam——T6 全生命周期集成测试因此须绕过
  `AuthManager` 直接构造 `SSOFlowProvider(...)`（仅 `logout` 经 manager 驱动）。生产路径
  无影响（默认构造即真实路径），但集成测试无法端到端经 manager 装配 mock 平台，是可测性
  backlog 而非功能缺陷。
- **oup `_PROBE_URL`（`/my-account`）未经真实网络核实**：`oup_silverchair.md` §3.3 controller
  亲读标注"R0 未实测，待 runbook 核验"——`healthcheck()`/session 探针逻辑离线层完整覆盖
  （`ChallengeDetector` 四态判定 + mock IdP 集成），但探针 URL 本身的真实可达性/正确性
  待 oup SSO runbook（T7b）首次真实登录时核验。
- **`docs/plan/decision-log.md` INDEX 摘要范围核实**：本次核对 `docs/INDEX.md` 两处摘要
  （"查为什么这样设计"导航行 + `plan/` 表格行）**均已正确写"D-001…D-025"**（与
  `decision-log.md` 实际条目数一致），**无需本次更正**——该项在 Phase 3 报告曾两次记录为
  滞后（"D-001…D-019"），本次复核确认已在此前的提交中同步清零，如实记录现状供追溯。
- **AC-3.1/3.2/3.3/3.4 独立汇总验收记录仍缺失**：Phase 3 报告 §5/§6 已两次记录此残项（判据
  分散在 `test_merge_acceptance.py`/`test_merge_property.py`/`test_verify.py` 三个测试文件），
  本 Phase 未处理（不在 phase4-implementation-plan 范围内），移交 Phase 5（见 §6 检查单）。
- **本 Phase 无 `docs/logs/` session 日志**：延续 Phase 3 的同一已知限制（现有日志止于
  `2026-07-22-session-006.md`），Phase 3/4 两个 Phase 全程均未见新 session 日志文件，本次
  任务范围未创建。
- **本次 T8 复核发现的 11 处 INDEX 日期漂移（超出本次任务范围，未修改）**：交叉核对
  `docs/INDEX.md` 全表 `updated` 列与对应文件实际 frontmatter 后，发现 11 个文件（
  `GLOSSARY.md`、`design/adapters/{pmlr,cvf,acl-anthology,neurips-proceedings,uchicago,
  informs}.md`、`catalog/cs-ai-conferences.md`、`testing/acceptance-criteria.md`、
  `research/site-survey/{metadata-apis,aggregators-unpaywall-dblp-core}.md`）的 INDEX
  日期比文件自身 `updated` 字段落后 1 天，均为 Phase 1–3 遗留、与本次 Phase 4 改动无关的
  既存漂移（非本次任务引入）。本次仅修正了直接触碰的 `development-plan.md`/`progress.md`
  两处（编辑该文件的同一提交同步）；其余 11 处超出本次窄范围任务边界，未一并修改，登记
  §6 检查单供后续文档盘点批处理，避免与本次 Phase 4 专属改动混杂在同一批提交里。

## 6. Phase 5 开工检查单

1. 【待用户】**T7a 移交三项**（AC-4 离线汇总记录 §5）：①**AC-4.1 真实 key/token 冒烟**——
   elsevier key（BLOCKER-1，外部依赖 1–2 周）+ wiley token（自助可得）到位后按
   `tests/manual/{elsevier,wiley}_runbook.md` 执行，`oup` 按 `oup_runbook.md` 走真实 SSO
   首登；②**asset 路径 version 债务**——design/06 数据模型层缺口（OA 副本与原平台 asset
   路径不含 version 判别位），建议 design/06 修订议题；③**AuthManager DI 缺口**——不支持
   注入 `http_factory`/`login_flow` 测试 seam，登记可测性改进 backlog。
2. 【待用户】**Elsevier API key 申请状态复核**（BLOCKER-1，`config.toml [auth.elsevier]
   api_key`）；**Wiley TDM token 申请**（自助 click-through，`config.toml [auth.wiley]
   token`）；**Kaggle key 状态复核**（Phase 2 检查单 #2 残项，跨 3 个 Phase 未清零）。
3. **`test_cli_canary.py` 断言列表补 `oup_silverchair`/`wiley`**（§5 已知限制；文件
   `tests/integration/test_cli_canary.py:97-162`）+ **`pyproject.toml:28` 注释同步**（elsevier_sd
   已非 stub，见 `pyproject.toml:44`）——均为纯断言/注释补全，无行为变更，可作低成本清理项。
4. **aaai_ojs 全库 OAI 收割批准待执行**（跨 3 个 Phase 未清：Phase 2 检查单 #3 → Phase 3
   检查单 #8 移交 → Phase 4 M2a 完成量级评估）：设计已定案（`aaai-ojs.md` §7 ★A 附属）——
   一趟 **~262 请求 @30rpm ≈9 分钟**、按 DOI 卷号 partition 落盘全部届、pipeline upsert
   去重；建议 Phase 5 开工窗口择期批量执行（超出单次 committed 冒烟 ≤5 req 的常规预算，
   需专项预算行）。
5. **9 项 UNRESOLVED 专项核实**（Phase 2 检查单 #7 → Phase 3 检查单 #14 延续，Phase 4 M2a
   仅盘点未处理，本次 T8 逐条重新点验去重后精确计数）：
   - aaai_ojs（4 项，`research/site-survey/aaai-ojs.md` + `design/adapters/aaai-ojs.md`）：
     ①1980–2018 是否在本 OJS 实例范围内（`site-survey:296`，当前实测下界 2019）；
     ②"AAAI-38"届序号命名 vs 站点 `Vol.N`/`AAAI-YY` 品牌名对应关系未直接验证
     （`site-survey:29,166`）；③IAAI/EAAI 论文是否占独立 issue 号还是穿插于 48 期内
     （`site-survey:150`，`design:92`）；④`ListSets` 展示的 setSpec 与 `ListIdentifiers`
     实际可查询 setSpec 层级/命名差异（`site-survey:284`）。
   - neurips_proceedings（5 项，`research/site-survey/neurips-proceedings.md` +
     `design/adapters/neurips-proceedings.md`）：①2021 年 OpenReview 强 id 内嵌链接覆盖率
     （仅 n=1 样本，`design:183`）；②`Metadata.json` bulk 端点可用年份窗（1987 有、2021 无，
     边界未测，`design:184`）；③详情页 Bibtex 按钮畸形 URL 是否可解析（未实发请求验证，
     `design:185`）；④`sitemap.xml` 未探测（`design:186`）；⑤1987/1988 vol 0/1 约定对其余
     年份是否成立、`conf/nips/nips{year}` vs `neurips{year}` slug 切换的确切年份边界未验证
     （`design:177`，仅 2023 行经 D-019 M2a 核准闭合）。
   - 不计入本次 9 项计数：`neurips.cc` 宣传站稳定性（`design:42⑤`，勘察任务书明确排除，
     非"未解决"而是"未纳入范围"）。
6. **dblp robots `/*.xml` 路径解读的显式 ADR 化**：当前 `/rec/xml`（`Disallow` 禁区，
   per-record 导出）vs `/xml`（`Allow`，`dblp.xml.gz` 全量 dump 所在前缀）vs `/db/**/*.xml`
   （`Allow`，per-conference 卷目录，dblp adapter 主枚举路径）三类路径的区分目前散落在
   `aggregators.md` §3 DBLP 红线框、`dblp/adapter.py` 源码注释、`decision-log.md` D-021
   决策 1 三处，尚无一条 ADR 显式给出"同一 `xml` 后缀词在不同路径前缀下 robots 读法不同"
   的一般性原则（AC-0.5 判据"记录例外需 ADR"的精神延伸）——建议后续新源遇到类似 robots
   通配歧义时，本条可作为该类判断的可援引先例，登记为独立小节或新 ADR。非阻塞项。
7. **acm_dl 维持出列**：D-020（Phase 2 出列）→ D-024（Phase 4 R0 重评，2026-07-23，维持
   出列）——两次独立复核均确认 Cloudflare 挑战墙 + ToS 禁自动下载条款未变。本 Phase 已把
   全文获取通道正式改道 `unpaywall` OA-fallback（pipeline `no_entitlement` 兜底，T5 落码），
   `acm-dl.md` 顶部已补 Phase 4 重评注记（本次 T8）。**下次重评时机未定**——若 Phase 5+
   有专项需求触及 ACM 系会议全文，建议先核 browser-fetcher 落地进度（`wiley.md` 同款 deferred
   页面兜底域待落地）再决定是否第三次重评，不建议无新证据的例行重评。
8. **budget.py 跨进程原子性**：M2b 已落地 `fcntl.flock` 加固（检查单 #10 闭合），但
   `progress.md` 模块表已注明"Windows 无 fcntl 降级为加固前现状"——若未来需跨平台一致的
   跨进程原子性，需评估 Windows 等价机制（如 `msvcrt.locking`），非当前阻塞项。
9. **11 处 INDEX 日期漂移批量清理**（§5 已知限制新记录）：`GLOSSARY.md` + 5 篇
   `design/adapters/*.md` + `catalog/cs-ai-conferences.md` + `testing/acceptance-criteria.md`
   + 2 篇 `research/site-survey/*.md`，均为 1 日粒度的 `updated` 列滞后，建议下次全文档
   状态盘点时批量同步（非本次 Phase 4 专属改动范围，故未随本报告一并修改）。
10. **AC-3.1/3.2/3.3/3.4 独立汇总验收记录成文**（Phase 3 检查单 #7 延续，跨 2 个 Phase
    未清零，本 Phase 未排期）：现判据分散三个测试文件，未收口成 `testing/records/` 下的
    独立记录文档。

## 7. 签署

- **T8 初判（2026-07-23）**：AC-4.2~4.6 离线载体 PASS（引 T7a 记录）、AC-4.1 离线载体+runbook
  就位（真实冒烟归 T7b，D-018 分层不阻塞）、AC-0 五条本次独立执行全 PASS、认证 adapter 限速
  合规 PASS、BLOCKED 演练 PASS、`make check` 全绿（2712 passed / 21 skipped / 98.84%）、
  在线预算 17/120 零超支。
- **最终判定**：**[待 controller 终审签署]**——待 controller 亲验 AC-4 离线记录（`make check`
  复跑吻合 + 载体计数复现）+ 本报告 AC-0 复核抽查 + §6 检查单条目确认后，签署 `tag phase-4`。
