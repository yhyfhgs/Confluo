---
title: Phase 4 实施计划 — 认证框架 + 出版社 adapters
status: draft
owner: fable5
updated: 2026-07-23
---

# Phase 4 实施计划 — 认证框架 + 出版社 adapters

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development 逐任务派发执行。
> 判定依据：[development-plan §Phase 4](development-plan.md)、[acceptance-criteria AC-4/AC-0](../testing/acceptance-criteria.md)、
> [Phase 3 报告 §6 开工检查单](../reports/2026-07-23-phase3-report.md)、D-006（认证设计）/D-014（UA 身份）/D-018（分层验收）。
> 实施模式沿用 phase1/2/3 验证过的全部纪律（详设 approved 硬门禁 / worktree 波次并行 / 每任务独立审查 +
> 限量真实交叉验证 / fix 循环 / 主 agent 合并亲跑门禁 / 全分支终审 / SDD ledger）。
> 详设载体：[design/auth-framework.md](../design/auth-framework.md)（W0 扩写至实现级后双评审 approved）+
> [design/07-auth-session.md](../design/07-auth-session.md)/[04-auth-gated-module.md](../design/04-auth-gated-module.md)（已 approved，语义基座）；
> 平台内部详设 `elsevier-sd.md`/`oup-silverchair.md`/`wiley.md`（P0b 依 R0 勘察定稿，本计划引用不复制）。

**Goal**：AuthProvider 四实现（APIKey/CookieSession/SSOFlow/EZProxy）+ 凭证库 + `crawler auth login/status/logout`
CLI + session 健康门上线；平台深做 `elsevier_sd`（AC-4.1 载体，API 路径）+ `oup_silverchair`（QJE fulltext 收敛，
cookie 路径）+ `wiley`（**R0 裁决=纳入**，TDM 路径 + token 门控，D-024）；pipeline 认证接缝全接线（OA-fallback / 健康门 /
日配额 / BLOCKED 恢复）；闭合 Phase 3 移交检查单 #2/#3/#4/#12/#13。AC-4.1~4.6 全过（离线 mock 层 + 真实凭证 runbook 分层）。

**Architecture**：Phase 1/2/3 冻结接口不变（SourceAdapter 五方法协议 / HttpClient 签名 / pipeline 六阶段 /
MergeEngine）。Phase 4 增量全部**纯附加**：①`types.SessionHandle = Any` → 具体 frozen dataclass（既有代码
line 128 注释预留的受控具体化）；②`errors.CrawlerError` 加 `status_code` 字段 + `AuthRequired`/`Challenged` 子类
（不新增 ErrorClass 九类）；③新包 `src/paper_crawler/auth/`（provider/store/challenge/browser/manager/cli）；
④pipeline 新增默认关闭的 auth 接线（OA-fallback 第七 handler / 健康门 / 日配额 / challenge 冷却）。两条平台主线
（elsevier API 档 / oup cookie 档）经既有 `resolve_assets(…, session)`/`fetch_asset(…, session)` 冻结形参接 session，
**不新增协议方法**。auth 框架与平台 adapter 接口解耦（框架管 session，adapter 管取回），可波次并行。

**Tech Stack**：不变（Python 3.12+ / httpx / sqlite3 / pydantic v2 / typer / pytest+coverage / ruff / mypy strict）。
**新增可选依赖**（`[project.optional-dependencies]`，**不进核心 dependencies**）：`[auth] = cryptography>=42, keyring>=24`
（AES-GCM 凭证库 + 主密钥存储，auth-framework §3.2）；`[auth-browser] = playwright>=1.40`（首登 headed / 浏览器上下文
下载，仅真实首登路径，不进 CI，§9/§10）。**不引入**：任何进核心路径的运行时依赖——mock IdP 测试纯 httpx（复用
既有 `MockTransport` seam），Playwright 惰性 + skip 门控绝不成硬依赖。

## Global Constraints（每个任务隐含继承）

- **AC-0 红线五条**：无盗版源集成点；无 CAPTCHA 求解/风控对抗（挑战一律 BLOCKED）；凭证/session/PDF 不入 git
  （新增 `*.enc`/`.filekey`/`profiles.toml`/`auth/state/` gitignore 双保险）；日志报告无未脱敏敏感值
  （新增 `insttoken` 等脱敏键）；限速 ≤ 站点声明、robots 禁区不访问（elsevier robots 全禁→**API 唯一正道**）。
- **认证红线（AGENTS §6 / D-006）**：只用用户自有合法凭证；首登人在回路（headed 浏览器，含 MFA）；
  绝不对抗风控/不解 CAPTCHA/不伪装浏览器裸抓闭源 PDF/不并行多 session 同平台/不深夜高频（工作时段窗）。
- **真实网络纪律**：默认测试零真实网络（socket 禁网护栏在位）；`tests/online/` 显式 `-m online` + `MAX_REAL_REQUESTS`
  预算头；真实凭证 runbook 走 `tests/manual/`（records 留痕，不进 CI）；UA `PaperCrawler/<ver> (personal research; mailto:<email>)`。
- **凭证隔离红线**：携密头（`X-ELS-APIKey`/`X-ELS-Insttoken`/`Cookie`/TDM token）必须随**专属 HttpClient** 一次性
  注入，绝不复用跨 adapter 共享 client（沿 openreview token 专属 client 先例）——否则头随他域请求外泄。
- **门禁**：`make check` 全绿方可合并（覆盖率 ≥80% 不回退，现 99.18%）；auth 包解析/判定模块 + 平台解析器 ≥90%。
- **详设硬门禁**：`auth-framework.md` 双评审 approved 前 T1~T7 不开工；`elsevier-sd.md`/`oup-silverchair.md`
  平台详设（P0b，依 R0）approved 前 T3/T4 平台实现不开工（框架件 T1/T2 不受平台详设门禁约束，可先行）。
- **范围只减不增**（development-plan R5 范围锁定）：深做 elsevier_sd + oup_silverchair + **wiley（R0 裁决纳入，D-024）**；
  uchicago/informs/ieee_xplore/cambridge/springer/jstor 顺延；**acm_dl 维持 D-020 出列**（D-024：挑战墙+ToS 禁自动下载证据未变，
  全文改道 unpaywall OA-fallback、元数据维持 crossref+dblp）。
- **提交规范**：Conventional Commits，scope `auth` / `adapter:<id>` / `pipeline` / `core` / `testing`；
  尾行 `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`；任何 git 写操作前确认分支（worktree 纪律）。
- **fixture 纪律**：认证响应录制**一律脱敏**（无 cookie/token/storage_state/个人信息）；auth 四类 fixture
  （已登录/未登录跳转/无权限/风控）人工过目后入库；golden 重录 `UPDATE_GOLDEN=1`。

## §2 接口冻结件（Phase 4 增量；T1/T2 落盘后冻结，改动须仲裁）

> 逐字签名见 [auth-framework.md §2/§6](../design/auth-framework.md)。本节列冻结锚点与 owner 任务，不复制全文。

1. **`types.SessionHandle` 具体化 + 枚举**（T1；auth-framework §2.1）：`HealthStatus{OK,EXPIRED,CHALLENGED}` /
   `SessionBackend{HTTPX_COOKIES,PLAYWRIGHT_STATE,BEARER_TOKEN}` / `SessionHandle(provider_id, backend, payload_ref,
   established_at, est_ttl=None)` frozen dataclass——替换 `types.py:128` 的 `= Any`；`SourceAdapter` 冻结协议
   `session` 形参由 `Any\|None` 精化为 `SessionHandle\|None`，既有 adapter 零改动。
2. **`AuthProvider` Protocol 五方法**（T1；auth-framework §2.2）：`ensure_session(*, interactive=False)->SessionHandle` /
   `health_check(session)->HealthStatus` / `refresh(session)->SessionHandle\|None` / `invalidate(session)->None` /
   `rewrite_url(url)->str`。`@runtime_checkable`；`AuthProviderBase` 提供 rewrite 恒等 + invalidate 样板。
3. **`CredentialStore` 读写接口**（T1；auth-framework §2.3）：`read_state/write_state/delete_state`（AES-GCM 密文，
   0600）+ `read_key/has_key`（keyring/config）+ `load_profiles`（profiles.toml schema §3.4）。
4. **`errors.CrawlerError.status_code`（纯附加）+ `AuthRequired`/`Challenged` 子类**（T2；auth-framework §2.4/§6）：
   `status_code: int\|None = None`（keyword-only，既有构造点零改动）；`AuthRequired`→AUTH_EXPIRED、`Challenged`→CHALLENGE
   固定 error_class（沿 `CapabilityNotSupported` 先例，不新增 ErrorClass）。
5. **pipeline auth 接缝**（T5；auth-framework §8，纯附加/默认关闭）：`StageContext.oa_fallback: bool=False` +
   `unpaywall_adapter` 注入槽；`_stage_oa_fallback` 第七 handler；runner `_auth_batch`（健康门）/`_challenge_cooldown`
   运行态；`Repo.count_fetch_today(domain)->int` 只读查询；`Config.auth_daily_cap=200`/`auth_health_interval=20`/
   `auth_health_max_age_s=900`/`[auth].active_profile`。**默认关闭→Phase 1-3 venue 零行为变化**（回归锁定）。
6. **在线预算**（§3）：Phase 总预算 **≤120 请求**；每源在线冒烟沿 `MAX_REAL_REQUESTS` 硬护栏。

## §3 在线预算分项表（总 ≤120；超支须如 Phase 2 C-A 入档）

| 分项 | 估算 | 依据 |
|---|---|---|
| R0 平台勘察复核（elsevier API/oup URL·挑战态/wiley TDM/acm ToS） | **已执行 5**（上限 25） | [publisher-platforms-p4-recheck.md](../research/site-survey/publisher-platforms-p4-recheck.md) 台账实耗 5/25（keyless E2 429 一次即停、oup O2 403 challenge 记录即停、robots ×3） |
| elsevier 真实 key 实测冒烟（AC-4.1 载体；**BLOCKER-1：key 到位后执行**） | ≤40 | entitlement 预检 + JFE 单篇取回 + 配额头审计 + keyless/quota 429 分流核验 + 重录缓冲（真实 key 授权窗口一次性用足） |
| **wiley TDM 冒烟（D-024；token 到位后执行 · 条件项）** | ≤10 | 已知有权 DOI 单篇取回 + 401/403/429 三态核验 + 双窗口 429 实触审计（token 自助可得，entitlement 受订阅约束） |
| D-019 四站锚点补跑（检查单 #13：pmlr/cvf/acl_anthology/neurips_proceedings） | ≤25 | 每站 ≥1 锚点人工核准复核（Phase 2 末 partial 状态清账，随本 Phase 在线窗一并核） |
| 缓冲（重试/重录/边界复核/oup cookie 真实 runbook 抽验） | ≤20 | oup 真实 SSO 首登属 runbook（不计 CI），此处仅留抽验余量 |
| **合计** | **≤120**（R0 已耗 5，余 ≤115） | — |

- **离线 DoD 不消耗在线预算**：AC-4.2/4.3/4.4/4.5/4.6 全在 mock IdP 离线层判定（auth-framework §9/§12）；
  在线预算只服务 R0 勘察（已执行）、AC-4.1 真实 key 冒烟、wiley token 冒烟、D-019 锚点补跑四类**必须真实网络**的项。
- **BLOCKER-1 应对策略**（R0 [LIVE 2026-07-23]：config/env 无 elsevier key）：elsevier key 是 AC-4.1 前置外部依赖
  （机构订阅关联、非商业；申请周期 1–2 周）——**T3 在线冒烟层标注"key 到位后执行"**（`tests/online/test_elsevier_smoke.py`
  `skipif` 无 key）；未到位则 AC-4.1 降级 runbook-only 分层（D-018），**离线 DoD（resolve/fetch 逻辑 + AuthRequired 分支 +
  fixture 回放）先行 PASS 不阻塞**。同理 wiley token 缺失→在线层 skip（条件项），s2/Kaggle key 缺失沿检查单 #16 复核。

## §4 任务卡

> 依赖：**T3/T4/T-wiley/T5 依赖 T1+T2；T6 依赖 T1；T7 依赖 T3/T4/T-wiley/T5/T6；M2 独立**。每任务 = implementer(worktree) →
> 双裁决审查（Spec+质量，限量真实交叉验证 ≤5 req 授权）→ fix 回派 → controller 合并亲跑 `make check`。

### T1 auth 核心框架 + 凭证库 + CLI（`feat/auth-core`）——最重件，安全红线密度最高
**Files**：新建 `src/paper_crawler/auth/`（`__init__.py`/`protocol.py`/`store.py`/`challenge.py`/`manager.py`/`cli.py`/
`browser.py` + `providers/{api_key,cookie_session,sso_flow,ezproxy}.py`）、`src/paper_crawler/types.py`（SessionHandle
具体化 §2-1）、`src/paper_crawler/config.py`（`[auth].active_profile` + 三 auth 配置项）、`src/paper_crawler/cli.py`
（挂载 `auth` 子 app）、`pyproject.toml`（`[project.optional-dependencies]` auth/auth-browser + uv.lock）、`.gitignore`
（`*.enc`/`.filekey`/`profiles.toml`/`auth/state/`）、`tests/unit/test_auth_*.py`。
**Interfaces**：冻结 §2-1/2-2/2-3（auth-framework §2）；四 provider 全实现（APIKey 真实验证逻辑；CookieSession/SSO
的 headless 复用 + 首登经 browser seam；EZProxy `rewrite_url` 真实重写 + 纯逻辑）。加密 = `cryptography.AESGCM`
（`[auth]` extra，惰性 import，auth-framework §3.2）；主密钥 keyring→文件密钥降级链 + 显式警告（§3.3）。
**DoD**：`make check` 绿（全程零真实网络，惰性依赖不破坏默认 `make check`）；auth 包解析/判定模块 ≥90%；
URL 重写表/脱敏/AES-GCM round-trip/keyring 降级判定/profiles schema 校验单测全绿；`crawler auth status`（只读）
对空配置正确呈现；`crawler auth logout` 取证式删除（AC-4.5 断言）。**现状盘点义务**：先读 `SessionHandle=Any`
全部消费点（adapter/stages/runner 传 None 处），diff 出具体化影响面入报告，证明零回归。
**测试判据**：AC-4.5（logout store 无残留，取证清单逐项）；AC-0.3/0.4（凭证不入 git、脱敏）；`insttoken` 明文
注入→jsonl 无残留。

### T2 HttpClient status_code + canary 凭证注入（`feat/http-status-canary`，#3/#4 小件）
**Files**：`src/paper_crawler/errors.py`（`status_code` 字段 §2-4）、`src/paper_crawler/http.py`（`_error_for_status`/
`_rate_limited` 带 status）、`src/paper_crawler/obslog.py`（`_SENSITIVE_KEYS` 补 `insttoken` 等 §5）、
`src/paper_crawler/adapters/openalex/adapter.py`（`_looks_like_status` 文本嗅探→`exc.status_code==402` 迁移）、
`src/paper_crawler/cli.py`（`_bind_healthcheck_credentials` 抽取 + canary 调用 §7）、`tests/unit/test_{errors,http,
obslog,cli_canary}.py`、`tests/unit/test_openalex_*.py`（402 路径改断言）。
**Interfaces**：`CrawlerError.status_code: int|None=None`（纯附加，keyword-only）；`_bind_healthcheck_credentials(env,
adapters)->list[HttpClient]`（复用 `bind_http_client`+`_bind_openreview_token_client`+enrich key 装配 + auth session
注入槽）。
**DoD**：`make check` 绿；映射表与冻结文本逐行一致；openalex 402 不再靠正则文本嗅探（模块 docstring 更新）；
canary 对配置了 openreview_token 的 config 不再显示匿名态。**动 HttpClient 冻结面——全 adapter 受影响**，回归锁定
（1600+ 既有测试是安全网，opus 审查）。
**测试判据**：检查单 #4（status_code 默认 None + 各状态码携值）、#3（canary 凭证注入，auth_gated 无 session→SKIP）；
AC-0.4（`insttoken` 脱敏）。

### T3 elsevier_sd adapter（`adapter/elsevier-sd`，API 档全链 + 真实 key 冒烟）——AC-4.1 载体
**Files**：新建 `src/paper_crawler/adapters/elsevier_sd/`（`adapter.py`/`parse.py` + entry point 注册，替换 stubs.py
的 `ElsevierScienceDirectStub`）、`tests/fixtures/elsevier_sd/`（Article API 全文响应截断脱敏 / entitlement true+false /
429+QUOTA_EXCEEDED / 挑战页四类）、`tests/{unit,contract}/test_elsevier_*.py`、`tests/online/test_elsevier_smoke.py`
（`-m online`，MAX_REAL_REQUESTS≤5）、`tests/manual/elsevier_runbook.md`。
**Interfaces**：`RESOLVE|FETCH`（enumerate 走 crossref，D-005）；`resolve_assets` = entitlement 预检 → 有权 AssetPlan
（`url_strategy=api_call`, Article Retrieval API, pdf 优先/XML 备选）/ 无权 no_entitlement；`fetch_asset` = APIKeyProvider
注入 `X-ELS-APIKey`(+`X-ELS-Insttoken`) 专属 client → httpx GET → PDF 落盘校验；`healthcheck` = quota/entitlement 探测
+ 已知 DOI entitlement 比对。错误映射（elsevier-sd.md §5）：401/403→auth_expired、entitlement=false→no_entitlement、
429/quota→rate_limited、404→gone（延迟重试）、空壳→integrity。domains 改 `api.elsevier.com`。
**DoD**：`make check` 绿；解析器 ≥90%；四类 fixture 回放全绿；在线冒烟 ≤5 req（entitlement 预检 + JFE 单篇）；
**真实 key runbook 通过 AC-4.1**（`auth login elsevier` → JFE DOI 经 Article API 得魔数校验合格 PDF）。**平台详设
门禁**：`elsevier-sd.md`（P0b，依 R0）approved 后开工。
**测试判据**：AC-4.1（真实 key 单篇）、AC-4.3（no_entitlement 降级）、AC-4.4（配额）。

### T4 oup_silverchair adapter（`adapter/oup-silverchair`，cookie 档 + 四类判定器 + QJE fulltext 收敛 #2）
**Files**：新建 `src/paper_crawler/adapters/oup_silverchair/`（`adapter.py`/`parse.py`（PDF 链接抽取器 + entitlement
判定器）+ entry point）、`venues/econ/qje.yaml`（`fulltext_source: elsevier_sd` 占位 → `oup_silverchair` 收敛 #2）、
`tests/fixtures/oup_silverchair/`（auth 四件套：登录态全文页 / 未登录跳转 / abstract-only / 挑战页，脱敏）、
`tests/{unit,contract}/test_oup_*.py`、`tests/online/test_oup_smoke.py`、`tests/manual/oup_runbook.md`。
**Interfaces**：`RESOLVE|FETCH`（enumerate 走 crossref，DOI 前缀 10.1093）；`resolve_assets` = DOI→doi.org 跟随重定向
到落地页 → 解析页内 PDF 链接（不可构造，含 file id）→ AssetPlan(`url_strategy=direct`+cookie)；entitlement 启发式
= article-abstract 路由且无 PDF 链接→no_entitlement；`fetch_asset` = CookieSessionProvider cookie jar 直取 → 被拒→
BrowserFetcher 同 context 重试一次（`[auth-browser]`）→ 仍失败按错误分类；`healthcheck` = 探针账号页。挑战页经
`ChallengeDetector`（auth-framework §11）判定器分类。错误映射（oup-silverchair.md §5）：302→signin→auth_expired、
article-abstract→no_entitlement、PDF 解析 0 命中→parse、HTML 伪装→integrity(auth_leak)、验证码→challenge。
**DoD**：`make check` 绿；解析器 ≥90%；auth 四件套判定器回归全绿；QJE `fulltext_source` 由占位改真实（#2 收敛，
`crawler venues lint` 绿）；在线冒烟 ≤5 req（匿名探测 URL 模式，真实取回归 runbook——oup 需 SSO session）。**平台详设
门禁**：`oup-silverchair.md`（P0b，依 R0）approved 后开工。
**测试判据**：AC-4.2/4.3（mock 层）、AC-4.6（挑战判定）；检查单 #2（QJE fulltext 收敛）。

### T-wiley wiley adapter（`adapter/wiley`，TDM 档 + 双窗口限速 + token 门控）——D-024 纳入，W2 平台波第三件
**Files**：新建 `src/paper_crawler/adapters/wiley/`（`adapter.py`/`parse.py` + entry point）、`tests/fixtures/wiley/`
（TDM 成功响应截断脱敏 / 401·403·429 三态 / 页面 auth 四件套）、`tests/{unit,contract}/test_wiley_*.py`、
`tests/online/test_wiley_smoke.py`（`-m online`，token 门控）、`tests/manual/wiley_runbook.md`。
**Interfaces**：`RESOLVE|FETCH`（enumerate 走 crossref，DOI 前缀 10.1111/10.1002/10.3982）；TDM 客户端 = httpx +
`Wiley-TDM-Client-Token` 专属 client（wiley.md §3）；**双窗口限速** = 单 token bucket `RatePolicy(rpm=5, burst=3)`
（起步保守；wiley.md §4 接缝结论：**无需扩展 ratelimit.py 冻结件**）；`ApiKeyProvider` token `[auth.wiley].token`（Config-slot，
T1 凭证库面）；错误映射（wiley.md §5）：401→auth_expired、403→no_entitlement（订阅域约束）、429→rate_limited、CF→challenge。
**DoD**：`make check` 绿；解析器 ≥90%；三态 fixture 回放全绿；双窗口限速器映射单测（3 连发 wait=0、第 4 wait≈10s，假时钟）；
**token 门控**——无 token → 在线冒烟 skip + canary NotImplementedError→SKIP（不阻塞验收，s2 先例）；有 token → 单篇冒烟 ≤1。
**平台详设门禁**：`wiley.md`（本次 P0b approved）后开工。
**测试判据**：AC-4.1（JF/ECMA 单篇，token 到位）、AC-4.3（403 no_entitlement 降级）、AC-4.4（日配额）。**依赖 T1+T2**（同 T3/T4）。

### T5 pipeline 集成（`pipeline/auth-integration`，OA-fallback #12 + 健康门 + 日配额 + BLOCKED 恢复）——跨模块缝合面
**Files**：`src/paper_crawler/pipeline/stages.py`（`StageContext.oa_fallback`/`unpaywall_adapter` 槽 + `_stage_oa_fallback`
第七 handler + 健康门/日配额前置检查）、`src/paper_crawler/pipeline/runner.py`（`_auth_batch` 健康门编排 +
`_challenge_cooldown` + NO_ENTITLEMENT 分支接 OA-fallback）、`src/paper_crawler/storage/repo.py`（`count_fetch_today` +
`plan_asset` 支持 version="oa"）、`src/paper_crawler/config.py`（auth_daily_cap/health_interval/health_max_age_s，若 T1
未落则此处补）、`src/paper_crawler/cli.py`（pull/grab 装配 AuthManager + unpaywall OA-fallback 注入）、`tests/integration/
test_auth_pipeline.py`。
**Interfaces**：auth-framework §8 全节接线点（§8.1 OA-fallback / §8.2 健康门 N=20/15min / §8.3 日配额 FetchLog 对账 /
§8.4 BLOCKED(auth)/BLOCKED(challenge)+冷却 24h）。**纯附加/默认关闭**：`oa_fallback=False` 时 Phase 1-3 venue 零行为
变化（回归锁定 = 现有全部 pipeline 集成测试）。
**DoD**：`make check` 绿；mock IdP 集成（依 T6 的 mock 载体）验证：no_entitlement→unpaywall OA asset 产出；健康门
≤20 篇内检出 EXPIRED→整批 BLOCKED 无 401 轰炸；日配额达上限→BLOCKED；challenge→BLOCKED+冷却；`resume` 恢复。
**跨 pipeline/auth/unpaywall 三模块缝合面——fable 审查**。
**测试判据**：AC-4.2/4.3/4.4（集成层）、design/05 §2 BLOCKED-resume；检查单 #12（OA-fallback 接线）。

### T6 mock IdP 集成测试全生命周期（`test/mock-idp`，AC-4.2/4.5/4.6 离线载体）
**Files**：`tests/integration/test_auth_lifecycle.py`（login→state 保存→复用→过期→refresh 全周期）、`tests/integration/
conftest.py`（mock IdP `MockTransport` handler + 进程内状态字典 + 假时钟 seam）、`tests/unit/test_auth_browser_seam.py`
（假 Playwright seam 单测首登逻辑，不触真实浏览器）。
**Interfaces**：mock IdP = `httpx.MockTransport` 处理函数（复用 HttpClient `transport` DI seam），路由 `/login`/
`/my-account`/`/InstitutionalLogin`/`/article-pdf` 按 cookie 有效性+假时钟返 200/302/403（auth-framework §9）；
**纯 httpx 零真实网络零 Playwright**（生命周期全段可测性论证见 §9）；真实浏览器测试 `skipif(not [auth-browser] or not
$PC_BROWSER_TESTS)` 默认 CI 双重跳过。
**DoD**：`make check` 绿（默认不 import playwright）；全生命周期用例覆盖 OK/EXPIRED/CHALLENGED 三态 + refresh 成功/
返 None 两路 + logout 取证；健康门/日配额/OA-fallback 的 mock 载体就绪供 T5 消费。
**测试判据**：AC-4.2（过期检测≤20 篇 BLOCKED）、AC-4.5（logout 无残留）、AC-4.6（挑战→BLOCKED+冷却）——**三者 CI 离线判定**。

### T7 AC-4 端到端 + elsevier 真实 runbook + BLOCKED 演练（`feat/ac4-e2e`）
**Files**：`docs/testing/records/2026-MM-DD-ac4-acceptance.md`（AC-4.1~4.6 汇总验收记录）、`tests/manual/`（elsevier/oup
runbook 执行留痕）、`tests/online/test_elsevier_smoke.py`（真实 key 冒烟 committed）。
**Interfaces**：依 T3/T4/T-wiley/T5/T6 合流；分层验收（D-018）：离线 mock 层（AC-4.2~4.6）+ 真实凭证层（AC-4.1 elsevier API /
oup SSO runbook）。BLOCKED 人工介入演练：auth login→resume 恢复、challenge 冷却→resume。
**DoD**：AC-4.1~4.6 全过（离线 PASS + runbook 留痕）；elsevier 真实 key 单篇 JFE PDF 魔数校验合格；日配额对账
（FetchLog）；BLOCKED-resume 演练通过。**controller 亲验**。
**测试判据**：AC-4.1~4.6 全线 + AC-4.4 配额对账。

### T8 收尾（`fable 编排 + sonnet 执行`）
**Files**：`docs/testing/records/`（AC-4 验收记录终稿）、AC-0 系统性扫描脚本产物、`elsevier-sd.md`/`oup-silverchair.md`/
`wiley.md` → implemented、`auth-framework.md`/`07`/`04` → implemented、`docs/INDEX.md`（登记 auth-framework.md/phase4-plan +
三平台状态）/`progress.md`/`decision-log.md`（D-023/D-024 已于 P0b 落地，此处只需 INDEX 摘要与状态同步）、
`docs/reports/2026-MM-DD-phase4-report.md`、tag `phase-4`。
**DoD**：AC-4.1~4.6 + AC-0 系统性扫描（git 全历史无 `*.enc`/cookie 形态 AC-0.3、日志正则 AC-0.4、限速/robots AC-0.5）
全过；INDEX/progress/decision-log 同步；阶段报告成稿；`make check` 全绿状态打 tag。**fable 全分支终审**。

### M2 债务清理包（`chore/phase4-debt`，独立可并行）
**Files**：D-019 四站锚点（pmlr/cvf/acl_anthology/neurips_proceedings，检查单 #13）；测试补强批（检查单 #15：cursor
中断→窗口重建→DOI 去重端到端 fixture / oa-report 循环端到端限速锁 / 契约 factory 补齐收窄 24 skip）；aaai_ojs 全库
OAI 补跑（检查单 #8，跨 2 Phase 未清）；aaai/neurips 六项 `[UNRESOLVED]`（检查单 #14）；progress.md 模块状态表 +
decision-log INDEX 摘要滞后（检查单 #11）；budget.py 跨进程原子性加固（检查单 #10，非阻塞）。
**DoD**：各残项逐条闭合或明确改期入报告；D-019 四站锚点人工核准入 fixture（在线预算 §3 ≤25）。**独立于 T1-T7**，
sonnet 执行 + 轻审，随主线并行不阻塞。

## §5 波次并行图与冲突面预算

```
W0(现在):  R0 平台勘察（elsevier API/oup URL/wiley TDM 裁决）‖ auth-framework.md 双评审 → approved + 本计划定稿
                                                              ‖ elsevier-sd.md/oup-silverchair.md 平台详设(P0b)
W1:        T1 auth 核心框架(fable)  ‖  T2 HttpClient status_code+canary(sonnet)     [框架件不受平台详设门禁]
W2:        T3 elsevier_sd(opus) ‖ T4 oup_silverchair(opus) ‖ T-wiley(opus) ‖ T6 mock IdP(sonnet)  [T3/T4/T-wiley 依 T1+T2；T6 依 T1]
                                                                                        [T3/T4/T-wiley 另依各自平台详设 approved]
W3:        T5 pipeline 集成(opus)                              [依 T1+T2；消费 T6 mock 载体]
W4:        T7 AC-4 端到端(opus→controller 亲验)  →  T8 收尾(sonnet+fable 终审)   [T7 依 T3/T4/T-wiley/T5/T6]
并行全程:  M2 债务清理包(sonnet)                              [独立，随主线任意波次并行]
每任务: implementer(worktree) → 双裁决审查(Spec+质量, 限量真实交叉验证 ≤5 req) → fix 回派 → controller 合并亲跑 make check
```

**冲突面预算（worktree 波次并行的写文件重叠分析）**：
| 文件 | 写方任务 | 冲突管理 |
|---|---|---|
| `types.py` | T1（SessionHandle 具体化） | T1 独占；T2-T7 只读消费 |
| `errors.py`/`http.py` | T2（status_code + AuthRequired/Challenged 异常子类，**权威版**） | **controller 裁决 2026-07-23（D-024 波次）**：T2 为 `errors.py`/`http.py` **单一权威版**——T1/T2 同波开工，T1 provider 若需本地最小异常定义，合并时取 **T2 权威版**（沿 Phase 3 `ids.py` 单一权威约定，非各自维护分叉）；小件 T2 先合、T1 rebase 后 `import` 引用 |
| `http.py` | T2（status_code 映射） | T2 独占（冻结面，opus 审）|
| `obslog.py` | T2（脱敏键） | T2 独占 |
| `cli.py` | T1（auth 子 app 挂载）、T2（canary 装配）、T5（pull/grab AuthManager 注入） | **三方写同文件**——按波次序化（T1→T2→T5 逐波合并，各自 rebase）；分节写入降低文本冲突 |
| `config.py` | T1（[auth] 配置）、T5（auth 门控项，若 T1 未落） | T1 优先落全部 auth 配置，T5 只读——消除重叠 |
| `pipeline/{stages,runner}.py` | T5 独占 | T5 单任务，无并行冲突 |
| `pyproject.toml`/`.gitignore` | T1（extras + gitignore） | T1 独占 |
| `venues/econ/qje.yaml` | T4（fulltext 收敛） | T4 独占 |

- **关键序化（controller 裁决，D-024 波次）**：`errors.py`/`http.py`（T2）→ `auth/providers/*`（T1 抛异常）跨任务依赖——
  **T2 = 单一权威版**（sole authoritative；T1 不维护分叉，合并取 T2，沿 Phase 3 `ids.py` 约定）；执行序 = 小件 T2 先合入、
  T1 rebase 后 `import` 引用。冲突面最重处 = `cli.py` 三方写（T1 auth 子 app / T2 canary 装配 / T5 pull 注入），靠波次逐合 + 分节降冲突。
- **T-wiley/T3/T4 平台并行无相互冲突**：三平台各独占自己的 `adapters/<id>/` 包目录 + fixture 目录（disjoint），
  仅共享只读的 T1/T2 冻结件——W2 三平台波真并行安全（沿 Phase 2/3 逐 adapter 独立分支先例）。

## §6 模型分配建议

**分配原则**：fable = 安全红线密度与裁决密度最高处（T1 凭证安全、T5 缝合面、终审门）；opus = 判断力密集
（平台 adapter、端到端）；sonnet = 规格已写死到字段级的执行件。

| 件 | 实现档 | 审查档 |
|---|---|---|
| W0 详设评审 A（技术一致性 + 安全架构） | — | fable |
| W0 详设评审 B（测试红线） | — | opus |
| T1 auth 核心框架 + 凭证库 + CLI | **fable** | **fable**（独立实例，实现审查分离） |
| T2 HttpClient status_code + canary 注入 | sonnet | opus（动 HttpClient 冻结面，全 adapter 受影响） |
| T3 elsevier_sd | opus | opus |
| T4 oup_silverchair | opus | opus |
| T-wiley wiley adapter（TDM + 双窗口限速 + token 门控，D-024） | **opus** | **opus** |
| T5 pipeline 集成（OA-fallback / 健康门 / 日配额 / BLOCKED） | opus | **fable**（跨 pipeline/auth/unpaywall 三模块缝合面） |
| T6 mock IdP 集成测试 | sonnet | opus |
| T7 AC-4 端到端 + runbook + BLOCKED 演练 | opus | controller 亲验 |
| M2 债务清理包 | sonnet | sonnet 轻审 |
| T8 收尾 | sonnet + controller | fable 全分支终审 |

## §7 AC 映射与风险

| AC | 载体任务 | 验收形态 |
|---|---|---|
| AC-4.1 首登+取一篇 | T3（elsevier API，主载体）+ T-wiley（JF/ECMA，token 到位）+ T7 | 真实 key/token runbook（JFE/JF 单篇魔数校验） |
| AC-4.2 过期检测不轰炸 | T5+T6 | mock IdP 集成（≤20 篇 BLOCKED，无 401 轰炸） |
| AC-4.3 无权限降级 | T5+T6（+T3/T4 真实 no_entitlement） | 集成（no_entitlement→unpaywall OA） |
| AC-4.4 日配额 | T5 | FetchLog 对账集成 |
| AC-4.5 登出无残留 | T1+T6 | 取证清单（store 无残留） |
| AC-4.6 风控即停 | T5+T6（+T4 判定器） | mock 挑战页→BLOCKED+冷却 |

风险：①**elsevier key 未到位**（AC-4.1 前置外部依赖，申请 1–2 周）——R0 阶段确认，未到则 AC-4.1 降级 runbook-only
分层、离线 DoD 不阻塞（D-018）；②**oup 真实 SSO 含 MFA 无法自动化**（D-006 R2 已接受）——oup 取回归 runbook，
CI 层只测判定器 + mock；③**cryptography 首个二进制依赖**（虽 optional extra）——已由 **D-023** 定裁（optional extra + 惰性 import，APIKey 路径不触）；
④**wiley 已纳入**（D-024）但 token 缺失→在线层 skip（条件项，不阻塞主线；elsevier+oup 已覆盖 AC-4 全判据）；⑤**Cloudflare 挑战升级**
（elsevier/oup/wiley 均 Cloudflare 深度集成，R1 风险，R0 复核 elsevier API 返结构化 error 非挑战墙、oup/wiley 页面档撞挑战）——
API 优先（elsevier/wiley TDM）+ 挑战即 BLOCKED（不对抗）+ canary 周检。
