---
title: Browser-Fetch 横切件（浏览器上下文取回通道）实现级详设
status: approved
owner: fable5
updated: 2026-07-26
---

# 11 · Browser-Fetch 横切件详设

> **状态**：`approved`（fable 定稿 2026-07-26，裁决记录 [D-030](../plan/decision-log.md)；§12 表已回填八项裁决结果）。**本文交付设计，不承诺实现**——
> 实现立卡权在 controller（S-c/E-1 两项缺口修复已立 F6 卡先行；横切件本体落地 Phase 6 末 stretch 或 Phase 7 另裁）。
> **承接**：[ssrn.md §11](adapters/ssrn.md) 设计种子（案 A/B + 评估维度）、[D-029](../plan/decision-log.md) 案 B 终裁、
> [phase5-report §6 检查单 #2/#9](../reports/2026-07-24-phase5-report.md)、[post-phase5-audit §3 S3-P2 + §6 处置 #2](../reports/2026-07-24-post-phase5-audit.md)（CF-403 冷却缺口）。
> **接缝**：[auth-framework §8.3/§8.4/§9/§10/§11](auth-framework.md)（日配额/BLOCKED 冷却/假 seam/Playwright extra/ChallengeDetector）、
> [04 §3/§4/§5/§7](04-auth-gated-module.md)（三档阶梯/下载流水线/风控规范/失败模式）、[07 §2/§4/§5](07-auth-session.md)（Provider/凭证库/运行时协议）、
> [05 §2/§4/§7](05-pipeline.md)（BLOCKED-resume/错误分类学/FetchLog）、[aea.md §3.3 ★接缝 A-1](adapters/aea.md)（移交本文裁决）、
> [wiley.md §3.2/§4](adapters/wiley.md)（页面兜底 + 双窗口限速）。
> **红线**：[AGENTS §6](../../AGENTS.md) / [AC-0.2](../testing/acceptance-criteria.md) —— **仅检测分类，零求解、零绕过**（§2 为硬约束段，先于一切方案）。
> **决策依据**：D-006（人在回路 + 绝不对抗风控）、D-014（诚实 UA + robots/软门禁区）、D-029（模式 B opt-in 低配额 + 横切件统一）。

## 0. 本文定位与交付边界

| 项 | 内容 |
|---|---|
| **交付** | 三消费方统一的浏览器上下文取回通道详设：职责边界、形态两案量化取舍与推荐、`ChallengeDetector` 接线、CF-403 冷却缺口系统性方案、BLOCKED 人工介入流、预算护栏离线逻辑、上下文接缝伪代码、测试方法/类型、AC 草案 |
| **不交付** | 任何实现代码；任何冻结件的实际改动；落地 Phase 承诺；真实站点在线验收（§11 环境约束） |
| **裁决移交** | [aea.md §3.3 ★接缝 A-1](adapters/aea.md)（`url_strategy=BROWSER` / `AssetPlan.state=deferred` 是否入冻结件）→ 本文 §4.6 给出裁决建议 |
| **提请仲裁** | §5.5 CF-403 契约演进案（触 Phase 2 冻结映射表）、§5.6 冷却键粒度演进案、§10 AC 编号归属——三项列 §12 |

## 1. 功能说明

### 1.1 三消费方需求归纳（取回形态与差异）

| 维度 | **ssrn 模式 B**（AC-5.1b 载体） | **aea pubs 全文** | **wiley 页面兜底** |
|---|---|---|---|
| 出处 | [ssrn.md §11/§4.4/§6.2](adapters/ssrn.md) | [aea.md §3.3/§3.4](adapters/aea.md) | [wiley.md §3.1/§3.2](adapters/wiley.md) |
| 目标域 | `papers.ssrn.com`（元数据层**永不接触**） | `pubs.aeaweb.org`（发现域 `www.aeaweb.org` 无挑战，**不同域**） | `onlinelibrary.wiley.com`（TDM 主干域 `api.wiley.com` 无挑战） |
| adapter family | `open_access`（元数据面） | `open_access`（元数据面）+ auth_gated（全文面未落地） | **`auth_gated`** |
| 通道地位 | **唯一**全文路径（unpaywall 对 SSRN 仅 landing，`url_for_pdf=None`，[LIVE 2026-07-24]） | **唯一**平台全文路径（连 gold OA 的 JEP 亦住 CF 域，[LIVE 2026-07-24] 反直觉发现） | **第三档兜底**（TDM API 为主干，cookie 直取为次，浏览器为末档） |
| URL 形态 | `Delivery.cfm/{name}.pdf?abstractid={id}&mirid=1`——**一次性 token** | `/doi/pdfplus/{DOI}`——**稳定路径**（无一次性 token 证据） | `/doi/pdf/{DOI}`——**稳定路径** |
| **resolve/fetch 同批约束** | **强制**（token 易失，跨批复用即设计违规 → `config`，ssrn.md §6.2） | 不需要（可分批） | 不需要（可分批） |
| 凭证需求 | 免费账号 session（**opt-in**；D-029 修订：非元数据前提） | 机构订阅 CookieSession（订阅刊）／无（JEP/JEL gold） | 机构 CookieSession（TDM token 之外的第二凭证面） |
| 挑战形态 | 403 + `cf-mitigated` + "verify you are human"（[PRIOR-LIVE 2026-07-20]） | **403 + `cf-mitigated: challenge` + 5672B 挑战体**（[LIVE 2026-07-24]，站点级判罚） | 403 CF 通用质询（[LIVE 2026-07-20]） |
| 限速基准 | **1 req/5s**（robots `crawl-delay:5`）+ 2–5s 抖动 ⇒ 有效 5–10s；并发 1 | robots `Crawl-delay:1`，但 CF 判罚非 robots ⇒ 须**保守自定**（本文 §7.5 取 1 req/6s） | **1 req/6s + 日配额 200**（wiley.md §4 全局纪律） |
| 触发姿态 | **用户显式发起单篇**（非批量、非默认，D-029 第 2 条） | 同左 | 批内自动**兜底一次**（wiley.md §3.2 字面：拦截后同 context 兜底一次，仍失败 BLOCKED） |
| 日配额建议 | 100/日（ssrn.md §5） | 待定（本文 §7.5 建议 50/日起步） | 沿 `auth_daily_cap=200`（与 TDM/页面共桶，wiley.md §4） |

**三方差异的设计含义（逐条落到方案）**：

1. **同批约束是 ssrn 独有的最强约束** → 横切件必须支持「resolve 与 fetch 在同一浏览器上下文内串联」的调用形态，
   而非只支持「拿到 URL 再单独下载」（§4.4）。若只按 aea/wiley 的稳定 URL 设计，ssrn 无法接入。
2. **触发姿态两分**（ssrn/aea = 用户显式单篇；wiley = 批内自动末档兜底）→ 门控须**两级**：全局 opt-in 开关
   （默认关）+ 每次调用的来源标记（`manual` / `pipeline_fallback`），二者共用同一预算账本（§7）。
3. **family 两分**（wiley 是 auth_gated，ssrn/aea 是 open_access）→ 直接暴露既有冷却门只覆盖 auth_gated 的缺口（§5.6）。
4. **凭证面三分**（免费账号 / 机构订阅 / 无凭证 gold OA）→ 上下文接缝必须支持 `storage_state` 可选注入
   （无凭证时以干净 context 启动，不是错误路径，§4.3）。

### 1.2 共性抽取 = 横切件职责边界

**做**（横切件的五件事）：

1. 在**用户已合法登录/无需登录**的浏览器上下文内，打开目标 URL 并取回单个 PDF 资产；
2. 对取回过程中的响应做**四态判定**（复用 `ChallengeDetector`，§5.1）；
3. 判定为 CHALLENGE → 立即停手、抛 `Challenged` → BLOCKED + 冷却（§6），**不做任何后续尝试**；
4. 执行**预算护栏**：域级限速、每日每 venue 配额、熔断、记账（§7）；
5. 落盘走既有三原语（`PartFileIO` / `validate_pdf_magic` / `finalize_fetch(FetchLog)`），不另起落盘路径（§4.5）。

**不做**（明确出列，防范围蔓延）：

- 不做 discover/enumerate/search——横切件只服务 **RESOLVE 尾段 + FETCH**；
- 不做登录（首登仍归 `auth/browser.py::run_headed_login` + `crawler auth login`，D-006 人在回路）；
- 不做批量/并发（并发恒 1，§7.1）；
- 不做挑战求解、重试、UA 轮换、代理切换、指纹伪装（§2 红线）；
- 不做常驻浏览器进程/上下文池（案 A 推荐结论，§3.5）。

### 1.3 与既有模块的分工

```
crawler grab --doi <X> --browser        ← 用户显式单篇入口（CLI，opt-in）
  └─ pipeline/stages._stage_fetch
       ├─ asset.url_strategy == RENDER_PAGE 且 ctx.browser_fetch 开 → _fetch_via_browser  ← 本文新增分支
       │    └─ browserfetch.fetch_one(plan, storage_state?, budget) ─┐
       │                                                             ├─ auth/browser.py（launch seam 模式复用）
       │                                                             ├─ auth/challenge.py（ChallengeDetector，零改）
       │                                                             └─ pipeline/io.py（PartFileIO/魔数/FetchLog）
       └─ 既有 direct / api_call / OA-fallback 分支（零改动）
```

## 2. AC-0.2 红线段（硬约束，先于一切方案）

> 本节为**不可协商**约束。任何方案、任何实现卡、任何"临时开关"都不得与之冲突；违反即 REJECT。

1. **仅检测分类，零求解、零绕过。** 浏览器上下文中遇到挑战（Cloudflare 质询页、CAPTCHA、"unusual activity"/
   "verify you are human" 文案、`cf-mitigated: challenge` 头）→ **唯一合法动作是分类为 CHALLENGE 并停手**。
   禁止：等待质询自动通过后继续、点击"我不是机器人"、注入/执行质询脚本、调用第三方打码服务、
   轮换 UA/指纹/代理重试、降级到 headless-stealth 类反检测手段。`auth/challenge.py` 现状即此姿态
   （"hcaptcha"/"recaptcha" 仅作**检测子串**，无任何求解逻辑；[post-phase5-audit §4 第 1 条](../reports/2026-07-24-post-phase5-audit.md) O3 逐行复核 PASS），本横切件继承之。
2. **挑战出现即 BLOCKED 转人工。** 抛 `Challenged` → pipeline `_route_error` → `queue.block` + 平台冷却 24h；
   **不占重试次数、不自动恢复**（05 §2）。恢复只能由人：用户自行在浏览器处理挑战后 `crawler resume`，
   或冷却期满后 resume（§6）。
3. **UA 恒定诚实**（D-014）：浏览器上下文默认 UA 由 Playwright 提供，**须显式追加**本系统身份串
   （`PaperCrawler/<ver> (personal research; mailto:<user>)` 作为 UA 后缀或 `X-Paper-Crawler` 标识，
   ⚠ 具体形态见 §11 开放问题③）——**绝不为通过检测而伪装成纯浏览器**。
4. **robots/软门禁区**（D-014 第 4 条）：`Disallow` 路径不访问；已知软门（SSRN 内部 `api.ssrn.com`、
   NBER 静态 PDF 路径）**禁止依赖**，本通道不得成为软门绕过的载体。ssrn 模式 B 落地**前置**：
   重取 `papers.ssrn.com/robots.txt` 全文核对 `Disallow` 面（[ssrn.md §9.2 开放问题①](adapters/ssrn.md)，⚠ 未核验）。
5. **凭证只用用户自有合法凭证**（AGENTS §6.1）：`storage_state` 来自用户人工首登，经 `CredentialStore`
   AES-GCM 解密注入；不共享、不入 git、不落明文临时文件（§4.3）。
6. **无再分发**：取回内容仅落本地 `data_dir`，不提供任何导出/上传/分享路径（AGENTS §6.5）。

> **AC 对应**：本节 = AC-0.2（无 CAPTCHA 求解/绕过）+ AC-0.5（限速/robots）+ AC-4.6（风控即停）+ AC-BF.1/AC-BF.2（§10）。

## 3. 实现方案：形态两案 + 量化取舍 + 推荐

### 3.1 两案重铸说明（先澄清一处继承歧义）

[ssrn.md §11](adapters/ssrn.md) 的"案 A/案 B"是**时序两案**（Phase 5 落地最小件 vs defer 至 Phase 6 横切件），
D-029 已终裁**案 B**，该问题**已闭合**，本文不重开。Phase 6 承接后需要回答的是**形态问题**：横切件长什么样。
故本节把两案**重铸为形态两案**（沿用 §11 案 A 的"最小件"形态描述作为新案 A 的直系来源，避免概念断裂）：

- **新案 A ≈ 旧 §11 案 A 的形态内核**（薄接缝、无新子系统、用户显式单篇）——只是落地时点按 D-029 后移；
- **新案 B = 旧 §11 未展开的另一极**（独立子系统、上下文池、批量能力、独立预算账本）。

### 3.2 案 A：薄接缝最小件（`browserfetch.py` 单模块 + 一 fetch 分支 + 一 CLI flag）

- **形态**：`src/paper_crawler/browserfetch.py`（或 `auth/browser_fetch.py`）单模块，导出一个纯函数
  `fetch_one(...)` + 一个 `BrowserFetchHandle` Protocol（鸭型，假 seam 可测）。**每次调用起一个一次性上下文，
  用完即毁**（继承 A-M7 一次性 profile 目录纪律，§4.2）。
- **新增面**：① `stages._stage_fetch` 顶部**一个分支**（`url_strategy == RENDER_PAGE` 且 `ctx.browser_fetch` 开）
  → `_fetch_via_browser`；② `StageContext.browser_fetch: bool = False` **一个纯附加槽**（默认关，
  沿 `oa_fallback`/`http` 先例）；③ CLI `grab --browser` **一个 flag**；④ `Config` 四个保守默认槽（§7.5）；
  ⑤ 消费方 adapter 各自在 `resolve_assets` 产 `RENDER_PAGE` 计划（ssrn/aea 各约 10 行，wiley 已有兜底位）。
- **预算护栏**：**复用**既有 `count_fetch_today(domain)` + challenge 冷却 JSON + `RateLimiter` 桶，
  只加一层 per-venue 计数查询（§7.2）——不新建表、不新建状态目录。
- **不含**：上下文池、跨任务复用、批量入口、独立账本表、交互式挑战处理 UI。

### 3.3 案 B：独立横切子系统（`browserfetch/` 包 + 上下文管理器 + 独立预算账本）

- **形态**：`src/paper_crawler/browserfetch/` 包（`session.py` 上下文池 + `budget.py` 账本 + `policy.py`
  三消费方 profile 注册表 + `fetcher.py`），一个可跨任务存活的 `BrowserSession`（同 venue 多篇复用同一 context）。
- **新增面**：新包 4 文件；新迁移（`browser_fetch_ledger` 表：venue/domain/day/attempts/outcomes）；
  `PipelineRunner` 增会话生命周期编排（建/健康/销毁）；批量入口 `pull <venue> --browser`；
  挑战态的交互式挂起/恢复通道。
- **收益**：多篇取回省去重复启动开销（每次冷启 Playwright ≈ 1–3s [推断]，⚠ 未实测）；跨篇 CF cookie 复用可减少质询频次；
  预算维度更细（可按 venue×域×日多维核销）。

### 3.4 量化取舍维度表

> 计数口径：**新增/改动文件数**与**新增冻结件数**为设计推算（非实码统计，标 [推算]）；
> "离线可判比例"= 可由 fixture/假 seam 断言的逻辑分支占该案总逻辑分支的估计比例 [推算]。

| # | 维度 | 案 A（薄接缝最小件） | 案 B（独立子系统） | 判 |
|---|---|---|---|---|
| 1 | **复杂度**（新增文件 / 改动既有文件 / 新迁移） | 1 新文件 / 4 改动（stages·cli·config·types 零改）/ **0 迁移** [推算] | 4 新文件 / 6 改动 / **1 新迁移** [推算] | **A** |
| 2 | **新增冻结件** | **0**（`RENDER_PAGE` 用既有枚举；`StageContext` 纯附加槽沿先例） | ≥3（`BrowserSession` 生命周期契约、账本表 schema、profile 注册表格式） | **A** |
| 3 | **维护面**（受站点漂移影响的接缝数） | 3（每消费方一条 resolve 计划构造）+ 1（判定器特征表，与 httpx 侧共用） | 同上 **+ 3**（profile 注册表逐消费方策略 + 池健康判定 + 账本一致性） | **A** |
| 4 | **预算可控性** | 复用 FetchLog 单一证据源（`count_fetch_today` 已有、AC-4.4 对账口径三处一致）；per-venue 维度经 `task` join 派生（§7.2）——**零新事实源** | 独立账本更细，但**引入第二事实源** → 与 FetchLog 可能不一致（对账负担 + 审计面翻倍） | **A** |
| 5 | **AC-0 合规面**（红线暴露面） | 能力面**恰好等于**红线允许的面（单篇、非批量、非默认、并发 1）——**无可误用的富余能力** | 批量入口 + 常驻上下文 = **红线明令不允许使用的能力**（D-029 第 2 条"非批量非默认"）；设计出来只能闲置，且构成误用/滑坡面 | **A（决定性）** |
| 6 | **复用 `auth/browser.py` 程度** | **高**：直接沿用其 launch-seam 模式（`LaunchFn` 注入）、一次性 profile 目录 `try/finally` 纪律、惰性 import + `AuthRequired` 安装指引；新增仅一个并列 Protocol（`BrowserFetchHandle`），**`run_headed_login` 与 `BrowserContextHandle` 零改** | 中：池化需把"一次性目录"改为"受管目录生命周期"，A-M7 纪律须重写而非继承（凭证残留风险面扩大） | **A** |
| 7 | **可测性（离线可判比例）** | **高**（≈90% [推算]）：单次调用是纯函数，假 seam 注入 handle 即可覆盖全部分支 | 中（≈70% [推算]）：池状态机 + 账本并发面需额外集成测试，且并发面本身无真实并发（并发恒 1）→ 测试成本换不来行为价值 | **A** |
| 8 | **性能收益** | 每篇冷启开销 ≈ 1–3s [推断，未实测] | 省去重复冷启 | **B** |
| 9 | **三消费方覆盖度** | 全覆盖（同批约束经"单次调用内 resolve+fetch 串联"满足，§4.4） | 全覆盖 | 平 |
| 10 | **可验证性**（本环境） | 在线不可验（§11 环境约束），离线全覆盖 → **最小件的"不可验面"最小** | 在线不可验 + 池行为亦不可验 → 不可验面更大 | **A** |

### 3.5 推荐案与三条关键取舍

**推荐：案 A（薄接缝最小件）。**

三条关键取舍（按权重降序）：

1. **AC-0 合规面决定形态**（维度 5）：D-029 第 2 条把模式 B 钉死为"opt-in / 用户发起单篇 / 非批量非默认"。
   案 B 的核心增量能力（批量入口、跨任务上下文池）**恰是红线不允许行使的能力**——设计并实现一套只能闲置的
   能力，既是浪费，又构成"某天顺手打开"的滑坡面。**能力面应当恰好等于合规面**，这是本推荐的第一理由。
2. **预算事实源唯一性优于预算维度丰富度**（维度 4）：项目已确立"FetchLog 是日配额与限速审计的唯一证据源"
   （auth-framework §8.3 / AC-4.4 / 05 §7，三处口径一字不差）。案 B 的独立账本引入第二事实源，一旦与
   FetchLog 漂移，AC-4.4 类对账即失去权威性。案 A 的 per-venue 维度经 `fetch_log ⋈ task` 派生（§7.2），
   **零新事实源**。
3. **"不可验面最小化"是本通道的第一性纪律**（维度 10 + §11）：本机环境对 CF 前置域 TLS 层阻断
   （curl/httpx [LIVE 2026-07-24] 实测；浏览器上下文 [推断] 同源本机代理同样受阻），且即便换网络，
   红线下"遇挑战即停"意味着 happy path 本身也依赖用户已 CF-cleared 的 session——**在线验收永远是
   用户参与 runbook 而非 CI**。在这种前提下，shipping 面越小越好；案 A 的离线可判比例更高（维度 7）。

**反方公平呈现**：案 B 在"用户合法持有订阅、需连续取十几篇"的现实场景下体验更好（省冷启、少质询）；
案 A 每篇重启上下文，在 CF 域可能**更容易**触发质询（每次都是新指纹/新 cookie）[推断，未实测]——
这是案 A 的真实代价，如实登记为 §11 风险②，并由 §3.6 演进缝兜住。

### 3.6 演进缝（案 B 元素的按需升级路径，当前不做）

若未来实测证实"每篇冷启显著抬高质询频次"（§11 风险②），最小升级 = 在 `fetch_one` 之上加一个
**调用方作用域的 context 复用器**（`with browser_scope() as scope: for plan in plans: scope.fetch_one(plan)`），
**不引入常驻进程、不引入账本表、不引入批量 CLI**——即只取案 B 的维度 8 收益，不取其维度 5 的合规面代价。
该升级对 `fetch_one` 签名零破坏（`scope` 为可选注入参数），故当前设计**已预留**该缝（§4.2 伪代码 `scope` 形参）。

## 4. 浏览器上下文接缝（设计伪代码）

> 以下为**设计伪代码**（AGENTS §5），表达接口与算法意图，不追求可运行。

### 4.1 模块布局

| 文件 | 职责 | 与既有件关系 |
|---|---|---|
| `browserfetch.py`（新） | `fetch_one` 纯函数 + `BrowserFetchHandle` Protocol + 假 seam 注入点 + 预算前置判定调用 | **并列**于 `auth/browser.py`，不改其任何签名 |
| `auth/browser.py` | 首登（`run_headed_login`）——**零改动** | 本文只**复用其模式**（惰性 import / 一次性目录 / launch seam），不复用其函数 |
| `auth/challenge.py` | `ChallengeDetector.classify`——**零改动** | 传输无关（§5.1），浏览器四元组直接喂入 |
| `pipeline/stages.py` | `_stage_fetch` 增一分支 + `_fetch_via_browser` 一函数 | 纯附加（沿 §8.1 OA-fallback 先例的"单分支+一函数"量级纪律） |

### 4.2 Protocol 与调用形态

```python
# browserfetch.py —— 设计伪代码

class BrowserFetchHandle(Protocol):
    """一次浏览器上下文的最小把手（鸭型；假 seam 可测，沿 BrowserContextHandle 先例）。"""
    def goto(self, url: str) -> "PageResponse": ...
    #   PageResponse 最小四元组：status:int / headers:Mapping[str,str] / final_url:str / body:bytes
    #   —— **恰好是 ChallengeDetector.classify 的入参形态**（§5.1），不多不少。
    def download_via(self, trigger: Callable[[], None], dest: Path) -> int: ...
    #   Playwright `expect_download` 的抽象：执行 trigger（点击/导航）→ 落盘 → 返字节数。
    def close(self) -> None: ...

LaunchFetchFn = Callable[[str, bytes | None], BrowserFetchHandle]
#   (user_data_dir, storage_state_bytes | None) -> handle；默认实现惰性 import playwright。

def fetch_one(
    *,
    plan: AssetPlan,                    # url_strategy 必须为 RENDER_PAGE（否则 CONFIG 响亮拒绝）
    venue_id: str,
    dest: Path,                         # PartFileIO 的 .part 路径（落盘仍归 pipeline）
    storage_state: bytes | None,        # CredentialStore 解密后的字节；None = 干净上下文（gold OA 场景）
    budget: "BudgetGate",               # §7：限速/配额/熔断的统一前置门（离线可判）
    detector: ChallengeDetector,        # 注入（默认单例）——判定器零改动
    resolve_in_context: Callable[["BrowserFetchHandle"], AssetPlan] | None = None,
    #   ↑ ssrn 同批约束的载体（§4.4）：非 None 时先在**同一上下文内**跑一次 resolve 得到 volatile URL
    scope: "BrowserScope | None" = None,  # §3.6 演进缝：复用上层 context；None = 一次性上下文
    launch: LaunchFetchFn | None = None,  # 测试 seam（假 launcher 注入，零真实浏览器）
) -> "BrowserFetchOutcome":
    """单篇浏览器上下文取回。**不重试、不对抗、并发恒 1**（§2）。"""

    budget.check_or_raise(venue_id=venue_id, domain=host_of(plan.url))
    #   ↑ 配额/熔断/冷却三判定合一，全离线；失败抛 CrawlerError(CONFIG|CHALLENGE)（§7）

    profile_dir = tempfile.mkdtemp(prefix="pc-bfetch-")      # A-M7 纪律继承（一次性目录）
    try:
        handle = (scope.handle if scope else (launch or _launch_playwright)(profile_dir, storage_state))
        try:
            budget.wait_rate(domain=host_of(plan.url))       # 域级限速闸（含抖动，§7.1）
            effective_plan = resolve_in_context(handle) if resolve_in_context else plan
            resp = handle.goto(effective_plan.url)
            verdict = detector.classify(status=resp.status, headers=resp.headers,
                                        final_url=resp.final_url, body=resp.body)
            match verdict:
                case CHALLENGE:        raise Challenged(...)   # → BLOCKED + 冷却（§6）；**零后续动作**
                case LOGIN_REDIRECT:   raise AuthRequired(...) # → BLOCKED(auth)，提示 `crawler auth login`
                case NO_ENTITLEMENT:   return Outcome(no_entitlement=True)   # → OA-fallback（§8.1 既有链）
                case OK:               pass
            n = handle.download_via(trigger=lambda: handle_click_or_goto(effective_plan), dest=dest)
            return Outcome(ok=True, bytes_written=n)
        finally:
            if scope is None: handle.close()
    finally:
        shutil.rmtree(profile_dir, ignore_errors=True)        # 异常路径亦清理（凭证残留红线）
    #   注：**无 except 重试块**——任何失败一次性上抛，交 pipeline 错误分类学处置（05 §4）。
```

### 4.3 storage_state 复用链（Playwright 上下文复用 auth 凭证）

```
crawler auth login <provider>            （既有，D-006 人在回路，零改动）
  → auth/browser.py::run_headed_login    （headed，一次性 profile 目录）
  → storage_state bytes
  → CredentialStore.write(ref)           （AES-GCM，AAD=ref，0600，既有）
        ⋮  （落盘态，跨进程）
  → [本通道] CredentialStore.read(ref)   → bytes（**仅内存**，不落明文临时文件）
  → LaunchFetchFn(user_data_dir, storage_state_bytes)
        └─ playwright.chromium.launch_persistent_context(user_data_dir, headless=True)
             + context.add_cookies / new_context(storage_state=json.loads(bytes))
```

- **`storage_state=None` 是合法路径**，非错误：aea JEP/JEL 为 gold OA，无需凭证；ssrn 模式 B 的免费账号
  为 opt-in（无账号时以干净上下文尝试，遇挑战即 BLOCKED，符合红线）。
- **provider 归属**：`storage_state` 的 `ref` 由消费方 venue 的 `provider_hint`/`active_profile` 解析
  （07 §6 既有机制）；本通道**不自行管理 provider**，只消费解析结果。
- **明文零落盘**：解密后的 `storage_state` 只以 bytes 传入 launcher；一次性 profile 目录在 `finally`
  中 `rmtree`（浏览器 profile 内含明文 cookie/缓存，残留等价 session 泄漏——A-M7 原文纪律）。
- **headless 复用是默认**；headed 仅在首登（既有通道）。本通道**不**开 headed 让用户"手动过挑战"——
  那属于 §6 的人工介入流（用户在**自己的**浏览器里处理，系统只等 `crawler resume`）。

### 4.4 resolve/fetch 同批约束（ssrn volatile 计划）

- **约束来源**：`Delivery.cfm` 的下载 token 一次性、必须同一浏览器上下文即时使用；跨批次复用 = 设计违规信号
  → `config`（ssrn.md §6.2 逐字）。
- **表达方式**：`AssetPlan` **不新增 `volatile` 字段**（避免动冻结件）。改由 `fetch_one(resolve_in_context=…)`
  的**调用形态**表达同批语义：ssrn adapter 提供一个 `resolve_in_context(handle) -> AssetPlan` 闭包，
  在同一 handle 内先访问 landing 页取出 `Delivery.cfm` URL，立即用于本次下载。
- **持久化纪律**：同批产出的 volatile URL **不写入 `asset.url`**（写入即为跨批复用埋雷）。`asset.url` 记
  **landing 引用**（`papers.ssrn.com/sol3/papers.cfm?abstract_id={id}`，ssrn.md §4.4 既有形态），
  volatile URL 只存在于单次调用的栈上。
- **护栏测试**：若某实现把 volatile URL 落库并在下一批复用 → 专测断言其被判 `config` 响亮失败（§8 T-4）。

### 4.5 落盘复用三原语（不另起路径）

`fetch_one` **只负责把字节落到调用方给的 `dest`（.part 路径）**；`_fetch_via_browser` 负责：
`PartFileIO`（原子写）→ `validate_pdf_magic`（`%PDF` 魔数 + <10KB 疑似拦截页判 `INTEGRITY(auth_leak)`，04 §4）
→ `io.commit(final)` → `repo.finalize_fetch(..., fetch_log_row=FetchLogRow(domain=…))`。
**三原语一件不绕过**（沿 §8.1 `_fetch_oa_direct` 的先例纪律）——这同时保证了 FetchLog 记账的完整性（§7.2）。

### 4.6 ★接缝 A-1 裁决（aea.md §3.3 移交本文）

**移交原文**：`url_strategy=BROWSER` / `AssetPlan.state=deferred` 是否入冻结件，由 browser-fetch 详设统一定
（[aea.md §3.3](adapters/aea.md)；`adapters/aea/adapter.py` docstring 同步登记）。

**裁决建议（提请 fable 定稿确认）**：

| 项 | 裁决 | 理由 |
|---|---|---|
| `url_strategy=BROWSER` | **不新增枚举值**；统一用既有 `UrlStrategy.RENDER_PAGE` | `types.UrlStrategy` 是 Phase 1 冻结件（`DIRECT`/`RENDER_PAGE`/`API_CALL`）；`RENDER_PAGE` 语义（"需渲染页面才能取回"）**恰好覆盖**浏览器上下文取回，无需新值。aea.md/aea adapter docstring 的 `BROWSER` 字面属**文档先行时的临时命名**，与冻结枚举不符——实现卡随手校正（登记为联动修正项，§12-裁决点⑤） |
| `AssetPlan.state=deferred` | **不新增**（`AssetPlan` 本无 `state` 字段；`asset.state` 枚举 `planned\|fetched\|gone\|no_entitlement\|failed` 不加第六值） | 新增 asset state 触 schema + 全库状态判定面。改用**门控表达**：`RENDER_PAGE` 计划照常以 `state=planned` 入库；`ctx.browser_fetch` 关（默认）时 `_stage_fetch` 该分支返回 `skipped`（detail=`browser_fetch_disabled`），**不派生失败、不计 failures**。语义等价于"deferred"且零冻结件改动 |
| aea 是否改为产计划 | **是**（browser 通道落地卡内）：aea 现"结构性从不返回非空 `AssetPlan`"的诚实边界，在本通道落地后**失去理由**——届时存在真实可执行路径，产 `RENDER_PAGE` 计划不再是"伪造可取回假象" | aea adapter docstring 已把该边界明确标为"待 A-1 裁决"，非遗漏 |

## 5. `ChallengeDetector` 接线 + CF-403 冷却缺口系统性方案

### 5.1 正面结论：判定器与传输无关，浏览器路径天然完整

`ChallengeDetector.classify(*, status, headers, final_url, body)`（`auth/challenge.py`）**不依赖 httpx**——
入参是纯结构化四元组。浏览器上下文可**完整**提供该四元组（Playwright `Response.status/.headers/.url/.body()`）。

**故：本横切件的挑战判定不受 CF-403 缺口影响**，`auth/challenge.py` **零改动**即可接线（§4.2 伪代码 `detector.classify`）。
缺口只影响 **httpx 直连路径**（econsoc resolve / wiley 页面兜底 / oup fetch）——即下节。

### 5.2 CF-403 冷却缺口：现状三段事实（逐条给出处）

| # | 事实 | 出处（实码） |
|---|---|---|
| ① | `HttpClient` 把 **403 统一映射 `NO_ENTITLEMENT`**（无头部/内容判别） | `http.py:89-90`（`_error_for_status`）；映射表为 Phase 2 T2 **冻结件**（http.py 模块 docstring "§2.1 冻结，逐行"） |
| ② | **仅 `CHALLENGE` 触发 24h 平台冷却**；`NO_ENTITLEMENT` 是独立终态（不计 failures、不冷却、还会派生 OA-fallback） | `runner.py:663`（`_BLOCK_CLASSES` 分支内 `_enter_challenge_cooldown`）+ `runner.py` NO_ENTITLEMENT 独立终态段（§8.5） |
| ③ | 消费方侧的挑战嗅探**只对 200 状态的 body 型挑战页生效** | `adapters/econsoc/adapter.py::_guard_challenge` docstring 自陈："`HttpClient.get_bytes` 不暴露状态/响应头，故只判 200-body 型质询；头级质询（403 `cf-mitigated`）经 `HttpClient` 映射 NO_ENTITLEMENT" |

**合成后果**：真实 CF 形态 **403 + `cf-mitigated: challenge`**（[LIVE 2026-07-24] aea `pubs.aeaweb.org` 实测；
[LIVE 2026-07-23] OUP QJE 同头；wiley.md §2 同判定）→ 被判 `no_entitlement` → **不冷却、不 BLOCKED、
不显著提示，反而派生 OA-fallback 继续动作**。这与 04 §5"检测到风控页立即 BLOCKED + 停止该平台全部队列 +
冷却 24h"的规范**语义相反**——虽方向 fail-safe（不会绕过挑战，只是不停手），但**违反 AC-4.6 字面**，
且在 CF 判罚期继续对同平台发请求，实际抬高被进一步判罚的风险。

### 5.3 受限面（三 adapter 逐条）

| adapter | 受限表现 | 现状缓解 | 残余风险 |
|---|---|---|---|
| **econsoc**（首个实际会触网遇到它者，S3-P2） | ECMA 自营域 resolve 落地页若返 403+`cf-mitigated` → `no_entitlement` → 与"过刊留 Wiley"的既有 NE 语义**混淆**（adapter 已用 `ecma-current-not-hosted` detail 区分 404，但 403 无区分） | `_guard_challenge` 覆盖 200-body 型 | 403 型质询静默降级为"无权限"；CF 测试**均只 mock 200，403 场景零覆盖**（审计原文） |
| **wiley** | 页面兜底域 `onlinelibrary.wiley.com` 的 CF 403 → `no_entitlement`；而 wiley.md §5 映射表**声明**该场景应为 `challenge`→BLOCKED+冷却 | TDM 主干域无 CF，主路径不受影响 | **文档与实现不一致**（wiley.md §5 第 4 行 vs `http.py:90`）——登记为文档/实现漂移，随本方案一并收口 |
| **oup_silverchair** | 403 CF 质询同样降级；叠加既有 P2「429 缺专属处置」（`ChallengeDetector` 判 OK 后落 `PARSE`/`INTEGRITY`） | fetch 路径用 `ChallengeDetector` 判 body（有权取到页面时有效） | 403 时 body 是质询页但状态先被映射，判定器**根本没机会看到** |

### 5.4 三方案 + 量化比较

| 维度 | **S-a：新增"不抛错取元信息"方法** | **S-b：`CrawlerError` 携带响应头快照** | **S-c：映射表增判别（403+`cf-mitigated`→CHALLENGE）** |
|---|---|---|---|
| 做法 | `HttpClient` 纯附加 `get_with_meta(url) -> ResponseMeta(status, headers, final_url, body)`，**≥400 不抛**，分类权交调用方 | `CrawlerError` 追加 `headers: Mapping[str,str] \| None`（keyword-only，沿 `status_code` 先例）；`_error_for_status` 构造时带上（脱敏后）；调用方在 `except` 内用 `ChallengeDetector` 重分类 | `_error_for_status` 的 403 分支内判 `cf-mitigated == challenge` → 返 `CrawlerError(CHALLENGE)`，否则维持 `NO_ENTITLEMENT` |
| 动冻结契约？ | **否**（新方法；`get_text`/`get_bytes`/`stream` 逐字不变） | **否**（纯附加字段；映射表不变，既有构造点零改） | **是**——映射表"逐行冻结"字面被改 → **须仲裁** |
| 修复彻底性 | 局部：只有改调新方法的调用点受益 | 局部：只有写了重分类 `except` 的调用点受益 | **系统性**：全部 20 adapter 一次受益，**新 adapter 自动继承** |
| 反模式风险 | **高**：三次复现过的「注册了却没验证」同构——逐 adapter 记得改，漏一个就静默 | **高**（同上） | **低**（单点） |
| 改动量 [推算] | http.py +1 方法（≈25 行）+ 3 adapter 调用点改写 | errors.py +1 字段 / http.py 2 处 + 3 adapter `except` 块 | http.py **3 行** |
| 兼容性风险 | 低（新方法无既有调用者） | 低（默认 None） | **需论证**：见下"S-c 兼容性论证" |
| 脱敏面 | `ResponseMeta.headers` 须过 `sensitive.redact`（Set-Cookie 等） | 同左（异常对象可能进日志，脱敏更关键） | 无（不新增数据出口） |
| 对本横切件的必要性 | **中**（浏览器路径自带四元组，不依赖之；但 §7 的"取回前 HEAD 预判"若做则需要） | 低 | 低 |

**S-c 兼容性论证（决定其可行性的关键）**：改判只在 `403 且响应头 cf-mitigated == "challenge"` 时发生。
逐一核对既有 403 消费者：① wiley TDM 403（无该刊权限）走 `api.wiley.com`——**API 域无 CF 前置**
（wiley.md §2 [LIVE]），不携该头 ⇒ 行为不变；② elsevier 走 JSON 封套，非页面型 ⇒ 不受影响；
③ oup/econsoc/aea 的 403+`cf-mitigated` **本就应当**判 CHALLENGE（wiley.md §5 / aea.md §6 / auth-framework §11
三处文档已如此声明）⇒ 改判是**让实现追上文档**，非语义变更；④ 无 CF 的普通 403 一律不携该头 ⇒ 不变。
**结论：S-c 的行为变更面 = 恰好是三处文档已声明应改的场景**，无既有正确行为被破坏。⚠ 该论证依赖
"403+`cf-mitigated` 不出现在任何期望 NE 的场景"，**须实现卡以全库 fixture 扫描复核**（§8 T-6）。

### 5.5 推荐 + 契约演进案（提请仲裁）

**推荐（主案）：S-c 作为契约演进案提交 fable 仲裁；获准则单点根治，`http.py` 映射表新增一行判别。**

**降级案（若仲裁不允许动映射表）：S-b + 三 adapter 逐点重分类**，并**必须**同时加一条**集合等值自断言**测试
（枚举全部"消费 403 的 adapter"集合 == "已接重分类"集合），以根治「注册了却没验证」反模式的第四次复现
（该反模式已在 canary 断言列表复现三次，审计 O4-P2）。

**S-a 的定位**：**不作为 CF-403 缺口的解**（其局部性与 S-b 同），但**建议随本横切件一并落地**——
理由：§7.1 的"取回前 HEAD 预判是否已被 CF 判罚"若要做（可选优化），以及 canary 对 CF 域的健康探测，
都需要"取元信息而不抛错"的能力。**若 §7.1 决定不做 HEAD 预判（本文倾向不做，见 §7.1），S-a 亦可不做。**

**无论采哪案，以下三条不变**：
1. 判定统一走 `ChallengeDetector`（不在 `http.py` 里散写特征子串——特征库单一权威源纪律）；
   S-c 的实现形态应为 `http.py` 调用 `ChallengeDetector` 的**头级子判定**（或把 `_CHALLENGE_HEADER_SIGNATURES`
   暴露为只读常量供 `http.py` 消费），**不复制特征串**。
2. 改判后的 CHALLENGE 一律走既有 `_BLOCK_CLASSES` 路径 → BLOCKED + 冷却 24h，**零新增处置逻辑**。
3. **不得**因此改动"403 无 CF 头 → NO_ENTITLEMENT"的既有语义（wiley TDM/机构无订阅的真实场景）。

### 5.6 第二缺口：冷却键粒度（本文新发现，一并提交仲裁）

**现状**（实码）：`runner._platform_of(venue) = registry.route(venue).fulltext_adapter.adapter_id`；冷却状态落
`<config-home>/state/cooldown/<adapter_id>.json`；且**冷却检查只在 auth_gated family 的 fetch 门内**
（`runner.py:456` `if getattr(adapter, "family", None) != "auth_gated": return True` **先于** `runner.py:461`
的冷却判定）。

**两个后果**：

1. **open_access family 的冷却检查不生效**：ssrn / aea 均为 `open_access` family（[ssrn.md §1](adapters/ssrn.md)/[aea.md §1](adapters/aea.md)）——
   本横切件的两个主要消费方**恰好落在冷却门之外**。若不处理，ssrn/aea 遇 CHALLENGE 会写冷却 JSON
   但**下一次照样发起**（`_enter_challenge_cooldown` 在 `_route_error` 内无 family 判别，写得进；
   `_challenge_cooldown_active` 在门内被 family 早返回跳过，读不到）——**写而不读**。
2. **冷却键是 adapter 而非域**：aea 一个 adapter 服务 8 刊且**两域异质**（`www.aeaweb.org` 无挑战 /
   `pubs.aeaweb.org` CF）。按 adapter 冷却会连坐无辜域；按域冷却才精确。

**演进案（提交仲裁，二选一或组合）**：

- **E-1（最小）**：把冷却判定**上移**到 family 判别之前（`runner.py` 语句顺序调整），并令 `_platform_of`
  在 `RENDER_PAGE` 计划场景改用**域**作键。改动量 ≈ 5 行 + 键格式迁移（旧 `<adapter_id>.json` 与新
  `<domain>.json` 共存读取，向前兼容）。
- **E-2（彻底）**：冷却键统一改为**域**，`_cooldown_path(domain)`，全 adapter 一致；旧键一次性迁移。
  更干净但触及既有 auth_gated 行为（wiley/oup/elsevier 的冷却粒度由平台变域——**语义上更准确**，
  但属 implemented 件的行为变更，须 ADR）。

**本文倾向 E-1**（横切件落地卡内顺带闭合，风险面最小）；E-2 列为后续清账候选。

## 6. BLOCKED 人工介入流

### 6.1 状态机映射（沿 auth-framework §8.4，本通道增列）

| 触发 | 抛出 | error_class | 处置 | 恢复动作 |
|---|---|---|---|---|
| 浏览器响应判 CHALLENGE | `Challenged` | `challenge` | `queue.block` + **域/平台冷却 24h**（§5.6 键粒度）+ 报告显著提示 | 用户自行在**其本人浏览器**处理挑战后 `crawler resume --all`；或冷却期满 resume |
| 判 LOGIN_REDIRECT | `AuthRequired` | `auth_expired` | `queue.block` + 同 venue 剩余连带 BLOCKED（`_auth_blocked_venues` 既有） | `crawler auth login <provider>` 重登 → `crawler resume` |
| 判 NO_ENTITLEMENT | 不抛（返 Outcome） | `no_entitlement` | asset 标 `no_entitlement`（**不计 failures**，§8.5）→ 派生 OA-fallback（若有 DOI） | 无需人工 |
| 日配额/熔断达上限 | `CrawlerError(CONFIG)` | `config` | `queue.block`，detail=`browser_quota`/`browser_breaker` | 次日自然恢复，或 `crawler resume` + 调 Config |
| Playwright 未安装 | `AuthRequired` | `auth_expired` | `queue.block`，detail = `[auth-browser]` 安装指引（复用 `auth/browser.py` 逐字提示） | `pip install paper-crawler[auth-browser] && playwright install chromium` |
| volatile token 跨批复用 | `CrawlerError(CONFIG)` | `config` | `queue.block`——**设计违规信号**（ssrn.md §6.2） | 修实现（非用户可恢复） |

### 6.2 人工介入的红线姿态（关键澄清）

- **系统绝不代替用户"处理挑战"**：不开 headed 浏览器让 agent 点击、不引导用户"在系统内过验证"。
  合法形态只有一种：**用户在自己的浏览器里正常访问该站点、按站点要求完成验证**，之后系统凭
  用户已合法建立的 session（`storage_state`）重试——这与 D-006"首登人在回路"同构。
- **冷却期内不自动重试**：`crawler resume` 只把任务转回 PENDING；若冷却未满，下次 drain 会再次 BLOCKED
  （§5.6 修复后）。想立即重试须显式清冷却——建议提供 `crawler cooldown status|clear <domain>`
  （**新 CLI，提请仲裁**，§12-裁决点④）；在此之前用户只能手删 `<config-home>/state/cooldown/*.json`
  （现状，不友好但不阻塞）。
- **报告呈现**：`RunReport` 增 `blocked` 明细中显著呈现 challenge 事件（域、时刻、冷却至、人工动作提示）——
  沿 AC-4.6"报告显著提示"判据既有形态，**不新增报告结构**。

## 7. 预算护栏（全离线逻辑）

### 7.1 四层护栏（自外向内）

| 层 | 机制 | 离线可判 | 出处/默认 |
|---|---|---|---|
| L1 **全局 opt-in** | `Config.browser_fetch_enabled: bool = False` + `StageContext.browser_fetch` + CLI `--browser`；三者**全开**才走本通道 | ✅ | D-029 第 2 条"非默认" |
| L2 **域级限速** | `RateLimiter` 既有桶 + **抖动**：ssrn `1 req/5s + 2–5s 抖动 ⇒ 有效 5–10s`；aea/wiley `1 req/6s`；**并发恒 1** | ✅（假时钟断言，沿 ratelimit 单测先例） | ssrn.md §5 [PRIOR-LIVE]；wiley.md §4 |
| L3 **每日配额（per-venue × per-domain）** | 取回前查当日计数 ≥ cap → `CrawlerError(CONFIG)` → BLOCKED | ✅（真 sqlite 集成测试） | §7.2 |
| L4 **熔断** | 连续 CHALLENGE ≥1（即刻）/ 连续非挑战失败 ≥3 → 该域当日停发；冷却 24h 优先于配额 | ✅ | 04 §5 + §5.6 |

**是否做"取回前 HEAD 预判"（可选优化）**：**建议不做**。理由：① HEAD 本身即一次请求，占配额、可能自身触发判罚；
② 判罚状态高度时变，预判过期即无意义；③ 会引入对 S-a（§5.4）的强依赖。**结论：直接尝试 + 一次判定 + 遇挑战即停**
是更诚实也更省请求的形态。

### 7.2 配额口径与数据源（唯一事实源 = FetchLog）

**口径**（与 auth-framework §8.3 / oup §4 / wiley §4 **一字不差**）：**"fetch 尝试篇次"——fetch 阶段每次尝试落一行
`fetch_log`，成败均计；resolve 页请求不计。** 本通道的每次 `fetch_one` 调用 = 一次 fetch 尝试 = 一行 fetch_log
（§4.5 强制经 `finalize_fetch`／失败路径 `add_fetch_log(error_class=…)`，两条路径都落行）。

**per-venue 维度的派生查询（零新表、零新事实源，设计伪代码）**：

```sql
-- 域维度（既有 repo.count_fetch_today(domain)，零改动）
SELECT COUNT(*) FROM fetch_log WHERE domain = ? AND DATE(ts) = DATE('now');

-- venue 维度（新增只读查询 count_browser_fetch_today(venue_id, domain)）
SELECT COUNT(*) FROM fetch_log f JOIN task t ON t.id = f.task_id
WHERE t.venue_id = ? AND f.domain = ? AND DATE(f.ts) = DATE('now');
```

- `fetch_log` 无 `venue` 列（`0001_init.sql:172-184`），但有 `task_id`；`task.venue_id` 提供 venue 维度 ⇒
  **join 派生即可，不加列、不加表、不加迁移**。
- ⚠ 该 join 依赖 `fetch_log.task_id` 非空——实现卡须核实 `finalize_fetch` 是否恒填 `task_id`；
  若存在空值路径，则 venue 维度退化为域维度（fail-safe 方向：域配额仍生效）。登记为 §11 开放问题④。
- `DATE(ts)` 为 UTC 日（`ts` 存 UTC ISO8601），与既有 `count_fetch_today` 一致——**不引入第二时区口径**。

### 7.3 熔断（离线判定，无状态外溢）

```
BudgetGate.check_or_raise(venue_id, domain):
    if cooldown_active(domain):                    # §5.6 修复后的域级冷却
        raise CrawlerError(CHALLENGE, "域 {domain} 处于挑战冷却期（至 {until}）", detail="browser_cooldown")
    if count_browser_fetch_today(venue_id, domain) >= cap(venue_id):
        raise CrawlerError(CONFIG, "browser-fetch 日配额已达上限 cap={cap}", detail="browser_quota")
    if consecutive_failures(domain) >= 3:          # 运行态计数（_new_report 重置）
        raise CrawlerError(CONFIG, "域 {domain} 连续失败熔断，当日停发", detail="browser_breaker")
```

- 三判定**全部只读本地状态**（sqlite + 冷却 JSON + 运行态字典）——**零网络**，故 100% 离线可判。
- **CHALLENGE 熔断阈值 = 1**（即刻）：不是"连续 N 次"——04 §5"立即 BLOCKED"字面。
- `consecutive_failures` 是**运行态**（进程内，`_new_report` 重置），不落盘：跨运行的持久约束由 L3 配额承担。

### 7.4 obslog 记账（观测证据面）

每次 `fetch_one` 无论成败落一条 obslog 事件（INFO/WARNING），字段：
`domain` / `venue` / `stage="fetch"` / `channel="browser"` / `verdict`（ok\|challenge\|login_redirect\|no_entitlement）/
`quota_used` / `quota_cap` / `rate_wait_ms` / `elapsed_ms`。**URL 经 `sensitive.redact`**（既有单一权威脱敏源）。
`channel="browser"` 是**新字段值**（非新字段——`log_event(**kwargs)` 自由 kwargs），用于把浏览器通道请求
从 obslog 中一键筛出，服务 AC-BF.4 的限速审计。

### 7.5 Config 槽位（纯附加，全部保守默认）

| 槽 | 默认 | 说明 |
|---|---|---|
| `browser_fetch_enabled` | `False` | L1 全局开关（D-029"非默认"） |
| `browser_daily_cap` | `50` | 每 venue×域 每日上限（比 `auth_daily_cap=200` 更严——本通道是最敏感面） |
| `browser_rate_rpm` | `10` | = 1 req/6s（aea/wiley 基线）；ssrn 由 VenueSpec `rate_limit` 收窄为 1 req/5s + 抖动 |
| `browser_jitter_s` | `(2, 5)` | 抖动区间（ssrn.md §5 逐字） |

⚠ `browser_daily_cap=50` 为**本文建议值**，ssrn.md §5 另记 SSRN 域 100/日——二者不冲突（取 min），
但**须 fable 定稿时确认口径统一**（§12-裁决点⑥）。

## 8. 测试方法

> 全部**离线可判**；真实浏览器取回**不进 CI**（`PC_BROWSER_TESTS` 手动门 + runbook，沿 auth-framework §9/§10）。

| # | 测试 | 方法 | 断言要点 |
|---|---|---|---|
| T-1 | **假 seam 全链** | 注入假 `LaunchFetchFn` 返回 stub `BrowserFetchHandle`（预置 `PageResponse` 四元组 + mock download），零真实浏览器 | `fetch_one` 四态分支各一例；OK 路径落盘字节数正确 |
| T-2 | **挑战判定四态** | 复用既有 challenge fixture（CF `cf-mitigated: challenge` 头 / "Just a moment" body / hcaptcha / 正常全文页）喂 stub handle | CHALLENGE→`Challenged`；LOGIN_REDIRECT→`AuthRequired`；NO_ENTITLEMENT→Outcome 非异常；OK→下载 |
| T-3 | **零对抗断言**（红线专测） | 对 CHALLENGE 用例统计 stub handle 的调用序列 | `goto` **恰好 1 次**、`download_via` **0 次**、无二次 `goto`——即"检测即停、零重试"可被机器判定 |
| T-4 | **同批约束护栏** | 构造"volatile URL 被落库并跨批复用"的场景 | 判 `config` 响亮失败；且正常路径下 `asset.url` 存的是 landing 而非 `Delivery.cfm` |
| T-5 | **预算护栏三判定** | 真 sqlite：预置 fetch_log 行至 cap−1/cap；预置冷却 JSON；运行态注入连续失败计数 | 边界（=cap 不熔断 / >cap 熔断，沿 T3 护栏引擎同款边界纪律）；冷却优先于配额；三者各抛正确 error_class |
| T-6 | **CF-403 改判**（S-c 采纳时） | httpx `MockTransport` 返 403+`cf-mitigated: challenge` / 403 无该头 / 403 wiley TDM 形态 | 前者→`CHALLENGE`+冷却写入；后二者→`NO_ENTITLEMENT` 行为逐字不变（**回归锁定**）。**外加全库 fixture 扫描**：断言无既有 fixture 因改判而翻转（§5.4 兼容性论证的机器化复核） |
| T-7 | **冷却键粒度**（E-1 采纳时） | open_access family venue 触发 CHALLENGE → 再次 drain | 第二次被 BLOCKED（现状为写而不读，故本测在修复前**必失败**，是修复的判据载体） |
| T-8 | **一次性目录清理** | 令 stub handle 在 `goto`/`download_via` 抛异常 | `profile_dir` 在异常路径亦被 `rmtree`（沿 A-M7 既有单测形态） |
| T-9 | **Playwright 缺失** | 无 `[auth-browser]` 环境（或猴补 import 失败） | 抛 `AuthRequired` 且 detail 含安装指引；**模块顶层零 playwright import**（`make check` 不因此变重） |
| T-10 | **obslog 记账** | 跑一次 T-1 OK 路径 + 一次 CHALLENGE 路径 | jsonl 各一条含 `channel="browser"`、`verdict`、`quota_used`；URL 已脱敏（无 token/cookie 残留） |
| T-11 | **真实取回 runbook**（不进 CI） | `tests/manual/browser_fetch_runbook.md`：换非-CF-阻断网络 + 用户已 CF-cleared session → 取 1 篇 → 魔数校验 → records 留痕 | 沿 wiley_runbook 既有形态；**结果无论成败如实回填** |

## 9. 测试类型

| 类型 | 覆盖 | 位置 |
|---|---|---|
| **unit（离线，零网络）** | T-1/T-2/T-3/T-4/T-8/T-9：`fetch_one` 分支、判定接线、护栏语义、清理纪律、惰性 import | `tests/unit/test_browser_fetch.py` |
| **unit（限速/时钟）** | L2 抖动与桶行为（假时钟精确断言，沿 `ratelimit` 单测先例） | 同上 |
| **contract** | `BrowserFetchHandle` Protocol 形态稳定性；`RENDER_PAGE` 计划的 pipeline 识别契约；**集合等值自断言**（"声明 `RENDER_PAGE` 的 adapter 集合" == "已接本通道的集合"，根治漏接反模式） | `tests/contract/test_browser_fetch_contract.py` |
| **integration（真 sqlite + mock）** | T-5/T-6/T-7/T-10：配额对账走真库、CF-403 改判回归、冷却粒度、obslog 落盘 | `tests/integration/` |
| **manual runbook（不进 CI）** | T-11 真实浏览器取回 | `tests/manual/browser_fetch_runbook.md` + `testing/records/` |
| **canary** | 三消费方 CF 域的健康行：无 session/未开通道 → `NotImplementedError`→**SKIP**（沿 elsevier/wiley/aea 先例，auth-framework §7），**不产生真实 CF 请求** | `canary.py`（零改动，复用既有分类规则） |

**覆盖率纪律**：新模块 ≥90%（对齐 auth 包/adapter 解析器纪律）；`make check` 全绿方可合并。
**禁网护栏**：本通道全部 CI 测试受既有 `socket.connect` autouse 猴补看守，零真实网络。

## 10. 验收标准草案（AC-BF.x）

> **编号说明**：`AC-BF.x` 为**临时编号**——本通道落地 Phase 未定（Phase 6 末 stretch 或 Phase 7），
> 落地 Phase 确定后转正为 `AC-<phase>.x` 并回填 [acceptance-criteria.md](../testing/acceptance-criteria.md)
> 及其 FR→AC 覆盖映射表（D-016）。**提请 fable 定稿裁决编号归属**（§12-裁决点⑦）。
> 形态对齐 AC-4.1（单篇取回）/ AC-4.3（no_entitlement 降级）/ AC-4.6（风控即停）三条先例。

| 草案 ID | 场景 | 通过判据 | 验收形态 |
|---|---|---|---|
| **AC-BF.1** | **风控即停（红线核心）** | 注入 CF 挑战响应（403+`cf-mitigated` / 200+"Just a moment" / CAPTCHA 三形态各一）→ ① 判 CHALLENGE ② 抛 `Challenged`→BLOCKED ③ 域冷却 24h 写入且**下次 drain 读得到** ④ 报告显著提示 ⑤ **零重试零绕过**（T-3 调用序列断言：`goto`=1、`download_via`=0） | **离线全判**（fixture + 假 seam），CI |
| **AC-BF.2** | **AC-0.2 静态红线** | 全仓静态扫描：本通道代码无求解/绕过语义（无打码服务调用、无 UA/指纹轮换、无 stealth 插件、无质询脚本执行）；`hcaptcha`/`recaptcha` 串仅出现在**检测**上下文 | 静态扫描 + 人工核（沿 AC-0.1/0.2 既有形态） |
| **AC-BF.3** | **单篇取回**（对标 AC-4.1） | 用户已 CF-cleared session + 非阻断网络下，`crawler grab --doi <X> --browser` 取回 1 篇，`%PDF` 魔数校验过、>10KB、DB↔文件对账一致 | **用户参与 runbook**（`tests/manual/`，records 留痕）——**非 CI**；离线对应物 = T-1 OK 路径 |
| **AC-BF.4** | **预算与限速审计**（对标 AC-4.4/AC-0.5） | ① 单 venue×域 单日 browser-fetch 尝试 ≤ `browser_daily_cap`（**FetchLog 对账**，成败均计）；② 相邻两次请求间隔 ≥ 域声明下限（ssrn ≥5s；obslog `channel="browser"` 事件时序审计）；③ 达 cap → BLOCKED 非 FAILED | **离线全判**（真 sqlite + 假时钟），CI |
| **AC-BF.5** | **无权限降级**（对标 AC-4.3） | 判 NO_ENTITLEMENT → asset 标 `no_entitlement`、**不计 failures**、不重试；有 DOI 时派生 OA-fallback（既有链）；无 OA 副本时如实无副本 | **离线全判**，CI |
| **AC-BF.6** | **CF-403 缺口闭合**（S-c 或 S-b 落地后） | 403+`cf-mitigated: challenge` → `challenge`（非 `no_entitlement`）+ 冷却；403 无该头 / wiley TDM 403 → `no_entitlement` **行为逐字不变**（回归锁定）；全库 fixture 零翻转 | **离线全判**，CI |

**与既有 AC 的关系**：
- **AC-5.1b**（ssrn 全文层，现 `defer Phase 6` 状态）由 **AC-BF.1+AC-BF.3+AC-BF.4** 承接兑现——
  其原文三判据（挑战正确 BLOCKED+冷却 24h ／ 真实取回落盘经 runbook ／ 限速 ≤1 req/5s FetchLog 审计）
  与上表逐条对应，**不重复立条**；定稿时在 acceptance-criteria.md 的 AC-5.1b 行加一条"承接指针"。
- **aea 全文 AC**（[phase5-report 检查单 #9](../reports/2026-07-24-phase5-report.md)"待 browser-fetch 通道 + auth 落地时立专属 AC"）
  同样由 AC-BF.x 承接——aea 的机构认证面（D-006 CookieSession）**另属 auth 域**，不在本文范围。
- **AC-4.6**（风控即停）在本通道的浏览器路径上是 **AC-BF.1 的父条**：AC-BF.1 是其在浏览器传输层的具化，
  不替代原条（原条覆盖 httpx 路径）。

## 11. 风险与开放问题

**风险**：

1. **本环境在线不可验**（[LIVE 2026-07-24] curl/httpx 对 CF 前置域 TLS 握手 reset；Playwright 同经本机代理
   `127.0.0.1:6152` fake-IP DNS ⇒ [推断] 同样受阻）——AC-BF.3 结构性只能是 runbook。**缓解**：离线可判面
   最大化（§8 十项 CI 测试），且 §3.5 取舍③已把"不可验面最小化"作为选案第一性纪律。
2. **每篇冷启可能抬高质询频次**（案 A 代价，[推断] 未实测）：新指纹/新 cookie 每次重来，CF 可能更敏感。
   **缓解**：§3.6 演进缝（调用方作用域 context 复用）已预留，不需重构。
3. **站点策略随时收紧**（SSRN=Elsevier、AEA=Atypon/CF、Wiley=CF）：本通道遇挑战即停，**风险表现为
   "通道失效"而非"被判罚升级"**——这是红线姿态的天然收益。canary 对三消费方走 SKIP 路径（§9），
   **不主动探测 CF 域**（探测本身即请求）。
4. **文档/实现漂移面**：wiley.md §5 声明的 `challenge` 映射与 `http.py:90` 实况不一致（§5.3）——
   本方案若只落降级案 S-b 而漏改 wiley，漂移会保留。**缓解**：AC-BF.6 的回归锁定 + contract 集合等值自断言。

**开放问题（逐条标触发层与出处）**：

| # | 问题 | 触发层 | 状态 |
|---|---|---|---|
| ① | `papers.ssrn.com/robots.txt` 全文（Disallow 面 + crawl-delay 复核） | **ssrn 模式 B 落地前置**（§2 红线 4） | ⚠ 未核验（ssrn.md §9.2 开放问题①，2026-07-24 未取得） |
| ② | `pubs.aeaweb.org` / `onlinelibrary.wiley.com` 的浏览器上下文实际可达性 | 实现卡在线冒烟（换网络） | ⚠ 未核验（本环境 TLS 阻断） |
| ③ | 浏览器上下文的 UA 形态：Playwright 默认 UA + 本系统身份串的**具体拼接方式**（后缀？自定义头？）与站点接受度 | 实现卡 | ⚠ 未核验；D-014"诚实 UA"约束方向明确，形态待定 |
| ④ | `fetch_log.task_id` 是否恒非空（per-venue 配额 join 的前提） | 实现卡（读实码可闭合，无需网络） | 待核（§7.2） |
| ⑤ | ssrn `Delivery.cfm` token 的实际有效期与"同上下文"的确切边界（同 context 跨页？同 page？） | 实现卡 runbook | ⚠ 未核验（[PRIOR-LIVE 2026-07-20] 仅知"一次性、需同浏览器上下文即时使用"） |
| ⑥ | 每篇冷启的真实开销与质询频次影响（风险②的量化） | 实现卡 runbook | ⚠ 未实测 |

## 12. 裁决点小结（供 fable 定稿）

| # | 裁决点 | 起草建议案 | 依据 | 需仲裁？ | **裁决结果（fable 2026-07-26，D-030）** |
|---|---|---|---|---|---|
| ① | **横切件形态** | **案 A（薄接缝最小件）** | §3.4 量化表 10 维（A 胜 8、平 1、负 1）；决定性 = AC-0 合规面（维度 5） | 定稿确认 | **采纳案 A** |
| ② | **CF-403 缺口方案** | **S-c 契约演进案**（403+`cf-mitigated`→CHALLENGE，`http.py` 3 行）；降级 S-b + 集合等值自断言 | §5.4 + S-c 兼容性论证（改判面 = 三处文档已声明应改的场景） | **是**（触 Phase 2 冻结映射表） | **采纳 S-c**（受控演进入 D-030；实现归 F6 卡，附全库 fixture 扫描） |
| ③ | **冷却键粒度缺口** | **E-1**（冷却判定上移至 family 判别前 + 域级键，向前兼容读旧键） | §5.6（写而不读的实证：`runner.py:456` 早返回先于 `:461` 冷却判定） | **是**（触 implemented 件行为） | **采纳 E-1**（实现归 F6 卡；E-2 列后续清账候选） |
| ④ | **`crawler cooldown status\|clear` 新 CLI** | 建议提供（否则用户只能手删 JSON） | §6.2 | **是**（新 CLI 面） | **缓议**（登记 Phase 7 检查单候选，横切件实现卡时重估） |
| ⑤ | **★接缝 A-1**（aea 移交） | `url_strategy` 用既有 `RENDER_PAGE`（不新增枚举）；不新增 `asset.state=deferred`（改门控表达）；aea 落地卡内改产计划 + 校正 `BROWSER` 字面 | §4.6 | 定稿确认 | **采纳**（RENDER_PAGE 复用/不新增 state/aea 归实现卡） |
| ⑥ | **配额口径统一** | `browser_daily_cap=50` 默认 + VenueSpec 可收窄；与 ssrn.md §5 的"100/日"取 min | §7.5 | 定稿确认 | **采纳**（50 默认与 VenueSpec 取 min） |
| ⑦ | **AC 编号归属** | 临时 `AC-BF.x`；落地 Phase 定后转正 `AC-<phase>.x` + 回填 FR→AC 映射（D-016）；AC-5.1b 加承接指针 | §10 | 定稿确认 | **采纳**（AC-BF.x 临时；落地转正+承接指针） |
| ⑧ | **是否同时落 S-a**（`get_with_meta`） | **不落**（§7.1 决定不做 HEAD 预判 ⇒ S-a 无必要消费方） | §5.5 | 定稿确认 | **采纳**（不落 S-a） |

## 13. 修订记录

| # | 日期 | 修订 | 依据 |
|---|---|---|---|
| 2 | 2026-07-26 | **fable 定稿（draft→approved）**：§12 八项裁决回填（①案 A ②S-c ③E-1 ④CLI 缓议 ⑤A-1 三合一 ⑥配额 min ⑦AC-BF 临时编号 ⑧不落 S-a）；D-030 ADR 落 decision-log；S-c/E-1 立 F6 实现卡（phase6-plan 增补） | fable 通读全文 + [D-030](../plan/decision-log.md) |
| 1 | 2026-07-26 | 初稿（Phase 6 R1，status draft，opus 起草）：三消费方需求归纳；ssrn.md §11 时序两案**重铸为形态两案** + 10 维量化取舍表 + 推荐案 A；AC-0.2 红线段前置；`ChallengeDetector` 接线（判定器传输无关的正面结论）+ **CF-403 冷却缺口三方案量化比较与 S-c 契约演进案**；**新发现第二缺口：冷却键粒度 + open_access family 写而不读**；BLOCKED 人工介入流；四层预算护栏（唯一事实源 = FetchLog，零新表）；上下文接缝伪代码（含 §3.6 演进缝预留）；★接缝 A-1 裁决建议；11 项测试方法 + 6 类测试类型 + AC-BF.1~6 草案 | [ssrn.md §11](adapters/ssrn.md) 设计种子 + [D-029](../plan/decision-log.md) + [phase5-report §6 #2/#9](../reports/2026-07-24-phase5-report.md) + [post-phase5-audit §3 S3-P2/§6 #2](../reports/2026-07-24-post-phase5-audit.md) + [auth-framework §8/§9/§10/§11](auth-framework.md) + 实码核对（`http.py:89-90`、`runner.py:456/461/663/589-608`、`auth/browser.py`、`auth/challenge.py`、`0001_init.sql:152-185`） |
