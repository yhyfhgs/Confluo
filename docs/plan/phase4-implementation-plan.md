---
title: Phase 4 实施计划 — 认证框架 + 出版社 adapters
status: approved
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
- **详设硬门禁**：`auth-framework.md`/`10-config-layout.md` 双评审 approved 前 T1a~T7 不开工；`elsevier-sd.md`/
  `oup-silverchair.md`/`wiley.md` 平台详设（P0b，依 R0）approved 前 T3/T4/T-wiley 平台实现不开工（框架件 T1a/T2 不受平台详设门禁约束，可先行）。
- **范围只减不增**（development-plan R5 范围锁定）：深做 elsevier_sd + oup_silverchair + **wiley（R0 裁决纳入，D-024）**；
  uchicago/informs/ieee_xplore/cambridge/springer/jstor 顺延；**acm_dl 维持 D-020 出列**（D-024：挑战墙+ToS 禁自动下载证据未变，
  全文改道 unpaywall OA-fallback、元数据维持 crossref+dblp）。
- **提交规范**：Conventional Commits，scope `auth` / `adapter:<id>` / `pipeline` / `core` / `testing`；
  尾行 `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`；任何 git 写操作前确认分支（worktree 纪律）。
- **fixture 纪律**：认证响应录制**一律脱敏**（无 cookie/token/storage_state/个人信息）；auth 四类 fixture
  （已登录/未登录跳转/无权限/风控）人工过目后入库；golden 重录 `UPDATE_GOLDEN=1`。

## §2 接口冻结件（Phase 4 增量；T1a/T2 落盘后冻结，改动须仲裁）

> 逐字签名见 [auth-framework.md §2/§6](../design/auth-framework.md)。本节列冻结锚点与 owner 任务，不复制全文。

1. **`types.SessionHandle` 具体化 + 枚举**（T1a；auth-framework §2.1）：`HealthStatus{OK,EXPIRED,CHALLENGED}` /
   `SessionBackend{HTTPX_COOKIES,PLAYWRIGHT_STATE,BEARER_TOKEN}` / `SessionHandle(provider_id, backend, payload_ref,
   established_at, est_ttl=None)` frozen dataclass——替换 `types.py:128` 的 `= Any`；`SourceAdapter` 冻结协议
   `session` 形参由 `Any\|None` 精化为 `SessionHandle\|None`，既有 adapter 零改动。
2. **`AuthProvider` Protocol 五方法**（T1a 冻结 Protocol / T1b 实现四 provider；auth-framework §2.2）：`ensure_session(*, interactive=False)->SessionHandle` /
   `health_check(session)->HealthStatus` / `refresh(session)->SessionHandle\|None` / `invalidate(session)->None` /
   `rewrite_url(url)->str`。`@runtime_checkable`；`AuthProviderBase` 提供 rewrite 恒等 + invalidate 样板。
3. **`CredentialStore` 读写接口**（T1b；auth-framework §2.3）：`read_state/write_state/delete_state`（AES-GCM 密文，
   0600）+ `read_key/has_key`（keyring/config）+ `load_profiles`（profiles.toml schema §3.4）。
4. **`errors.CrawlerError.status_code`（纯附加）+ `AuthRequired`/`Challenged` 子类**（T2；auth-framework §2.4/§6）：
   `status_code: int\|None = None`（keyword-only，既有构造点零改动）；`AuthRequired`→AUTH_EXPIRED、`Challenged`→CHALLENGE
   固定 error_class（沿 `CapabilityNotSupported` 先例，不新增 ErrorClass）。
5. **pipeline auth 接缝**（T5；auth-framework §8，纯附加/默认关闭）：`StageContext.oa_fallback: bool=False` +
   `unpaywall_adapter` + **`http: HttpClient|None`** 注入槽（A-B1 direct 取回）；`_stage_oa_fallback` 第七 handler +
   **`_fetch_oa_direct` 通用 direct**（A-B1）；`PipelineRunner.__init__(clock=)`（B-M1）；runner `_auth_batch`（健康门）/
   `_challenge_cooldown` 运行态 + 工作时段窗（A-M2）+ NO_ENTITLEMENT 独立终态不计 failed（A-m5）；`Repo.count_fetch_today(domain)->int`
   只读（`DATE(ts)`，B-m5）；`Config.auth_daily_cap=200`/`auth_health_interval=20`/`auth_health_max_age_s=900`/
   `auth_work_hours="8-23"`/`oa_fallback_rate_rpm`/`[auth].active_profile`（**config.py 归 T2 独占**，D-025）。**默认关闭 + clock 有默认→Phase 1-3 venue 零行为变化**（回归锁定）。
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

> 依赖（controller 增量令 2026-07-23 细拆重构）：**T2、T1a 无依赖（复审通过即开工，可同波）→ T1a+T2 解锁 T3/T4/T-wiley
> → T1b（依 T1a+T2）→ T6（依 T1b）‖ T5（依 T1b+T2）→ T7a（依 T5+T6）；T7b（依 T3+key，游离）；T8（依 T7a，T7b 可后补）；
> M2a/M2b 全程游离**。每任务 = implementer(worktree) → 双裁决审查（Spec+质量，限量真实交叉验证 ≤5 req 授权）→ fix 回派 →
> controller 合并亲跑 `make check`。

### T1a 冻结件实体化先行包（`feat/auth-freeze`，fable/fable，**快件·无依赖**）
**Files**：`src/paper_crawler/types.py`（SessionHandle 具体化 + HealthStatus/SessionBackend 枚举，§2-1）、
新建 `src/paper_crawler/auth/__init__.py` + `auth/protocol.py`（AuthProvider Protocol + ProviderKind + `AuthProviderBase`
便利基类，§2-2）、`auth/challenge.py`（`ChallengeDetector` 纯逻辑判定器——**零依赖且是 T4 上游**，故入先行包，auth-framework §11）、
`pyproject.toml`（`[project.optional-dependencies]` auth/auth-browser extras 声明 + uv.lock）、`.gitignore`（`*.enc`/`.filekey`/
`profiles.toml`/`auth/state/` 四条目）、`tests/unit/test_auth_{types,protocol,challenge}.py`。**不动 config.py**。
**Interfaces**：冻结 §2-1/§2-2（auth-framework §2）；`ChallengeDetector.classify` 四态（HTML 判定器，OUP 上游）。
**DoD**：`make check` 绿（零网络、零真实依赖 import——extras 仅声明未装亦不破坏默认 make check）；ChallengeDetector 四态单测 ≥90%；
`SessionHandle=Any` 具体化**现状盘点义务**：先读全部消费点（adapter/stages/runner 传 None 处），diff 具体化影响面入报告证零回归。
**测试判据**：AC-0.3（`.gitignore` 四条目生效验证）；SessionHandle 精化后既有契约测试全绿（零回归）。

### T1b auth 本体（`feat/auth-core`，fable/fable，**最重件·依 T1a+T2**）
**Files**：`src/paper_crawler/auth/store.py`（AES-GCM + keyring 降级链 + profiles.toml 解析，§3）、`auth/providers/
{api_key,cookie_session,sso_flow,ezproxy}.py`（四实现）、`auth/browser.py`（Playwright 惰性 seam + 一次性 mkdtemp
profile，A-M7）、`auth/manager.py`（AuthManager）、`auth/cli.py` + `src/paper_crawler/cli.py`（挂载 `auth` 子 app）、
`tests/unit/test_auth_{store,providers,manager,cli}.py`。**不动 config.py**（凭证槽解析归 T2）。
**Interfaces**：冻结 §2-3（CredentialStore）；四 provider 全实现（APIKey 真实验证；CookieSession/SSO headless 复用 + 首登经
browser seam；EZProxy `rewrite_url` 真实重写）。加密 = `cryptography.AESGCM`（`[auth]` extra 惰性 import，§3.2）；主密钥
keyring→文件密钥降级 + 显式警告（§3.3）；异常子类 `import` 自 **T2 权威版 errors.py**（不本地重定义，D-024/§5）。
**DoD**：`make check` 绿（CI 装 `[auth]` extra，B-m7）；auth 包解析/判定模块 ≥90%；URL 重写表/脱敏/AES-GCM round-trip +
每次新 nonce（A-m1）/keyring 降级判定 + 警告/profiles schema 校验/mkdtemp 清理（A-M7）单测全绿；`crawler auth status`
（只读，读 `.meta.json` sidecar，A-m2）对空配置正确呈现；`crawler auth logout` 取证式删除（AC-4.5 按 kind 分列，B-m6）。
**测试判据**：AC-4.5（logout store 无残留 + ⑥无残留 user-data-dir，取证清单逐项）；AC-0.3/0.4（凭证不入 git、脱敏）。

### T2 平台地基件：config 分层加载 + HttpClient status_code + canary 凭证注入（`feat/platform-foundation`，**opus**/opus，**无依赖·扩容 D-025**）
**Files**：`src/paper_crawler/errors.py`（`status_code` 字段 + `AuthRequired`/`Challenged` **权威版**，§2-4/D-024）、
`src/paper_crawler/http.py`（`_error_for_status`/`_rate_limited` 带 status）、`src/paper_crawler/obslog.py`（`_SENSITIVE_KEYS`
补 `insttoken` 等 §5）、`src/paper_crawler/adapters/openalex/adapter.py`（`_looks_like_status`→`exc.status_code==402` 迁移）、
**`src/paper_crawler/config.py`（T2 独占：分层加载链 env>项目级>home>默认 + `[auth.elsevier\|wiley]`/`auth.*` 运行时槽 +
敏感键护栏，D-025/10-config-layout.md）**、**新建 `config/{README.md,config.example.toml,profiles.example.toml}`（D-025）**、
`src/paper_crawler/cli.py`（`_bind_healthcheck_credentials` 抽取 + `_register_rate_domains`（A-M1）+ canary 调用 §7；
新增 `crawler config show` 命令）、`.gitignore`（`paper-crawler.toml` 防误提交）、`tests/unit/test_{errors,http,obslog,config,cli_canary,config_show}.py`。
**Interfaces**：`CrawlerError.status_code: int|None=None`（纯附加 keyword-only）+ `AuthRequired`/`Challenged` 子类（§2-4，单一权威版）；
`_bind_healthcheck_credentials(env,adapters)->list[HttpClient]`（复用 `bind_http_client`+openreview+enrich key + `_register_rate_domains`
限速域登记（A-M1）+ auth session 注入槽）；config 四层加载链 + 敏感键拒启动护栏（10-config-layout §3）。
**DoD**：`make check` 绿；映射表与冻结文本逐行一致；openalex 402 不再靠正则文本嗅探；canary 对配置了 token 的 config 不再显示匿名态
+ auth_gated 无 session→SKIP（B-M4）+ 限速域已登记不 CONFIG fail-fast（A-M1）；`config show` 脱敏 + 来源层正确；项目级敏感键→拒启动。
**动 HttpClient/errors 冻结面——全 adapter 受影响**，回归锁定（2154 既有测试是安全网，opus 实现+opus 审查）。
**测试判据**：检查单 #4（status_code 默认 None + 各状态码携值）、#3（canary 凭证注入 + 限速域登记）；AC-0.3/0.4（`insttoken` 脱敏、敏感键护栏、`config/**` 无凭证）。

### T3 elsevier_sd adapter（`adapter/elsevier-sd`，API 档全链）——AC-4.1 载体（真实 key 冒烟归 T7b）·**依 T1a+T2**
**Files**：新建 `src/paper_crawler/adapters/elsevier_sd/`（`adapter.py`/`parse.py` + entry point 注册，替换 stubs.py
的 `ElsevierScienceDirectStub`）、`tests/fixtures/elsevier_sd/`（**JSON 封套集非 HTML，B-M3**：Article API 全文截断脱敏 /
entitlement true+false / **keyless-429 `RATE_LIMIT_EXCEEDED` R0 [LIVE] 真实脱敏** / **quota-429 `QUOTA_EXCEEDED` ⚠[DOCS]-合成**）、
`tests/{unit,contract}/test_elsevier_*.py`、`tests/online/test_elsevier_smoke.py`（`-m online`，committed MAX_REAL_REQUESTS≤5，key 门控 skip）。
**Interfaces**：`RESOLVE|FETCH`（enumerate 走 crossref，D-005）；`resolve_assets` = entitlement 预检 → 有权 AssetPlan
（`url_strategy=api_call`, Article Retrieval API, pdf 优先/XML 备选）/ 无权 no_entitlement（不计 failures，§8.5）；`fetch_asset` =
ApiKeyProvider 注入 `X-ELS-APIKey`(+`X-ELS-Insttoken`) 专属 client → httpx GET → PDF 落盘校验；`healthcheck` = 无 key→NotImplementedError→SKIP /
有 key→quota/entitlement 探测。错误映射（elsevier-sd.md §5，**B-M2**）：401/403→auth_expired、entitlement=false→no_entitlement、
**任意 429→rate_limited 保守当日熔断（不靠 X-ELS-Status 分流）**、404→gone、空壳→integrity。domains 改 `api.elsevier.com`。
**DoD**：`make check` 绿；解析器 ≥90%；JSON 封套 fixture 回放全绿；committed 在线冒烟 ≤5 req（key 门控 skip；BLOCKER-1 key 到位后）。
**AC-4.1 真实 key runbook 归 T7b**（key 到位后执行）。**平台详设门禁**：`elsevier-sd.md`（P0b approved）后开工。
**测试判据**：AC-4.3（no_entitlement 降级不计 failed）、AC-4.4（配额）；AC-4.1 真实取回移交 T7b。

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
**测试判据**：AC-4.2/4.3（mock 层）、AC-4.6（挑战判定）；检查单 #2（QJE fulltext 收敛）。**依 T1a+T2**（消费 T1a 的
`ChallengeDetector`/`SessionHandle` 冻结件 + T2 config；CookieSessionProvider 运行时 wiring 归 T1b、集成终验归 T5——
adapter 单测用 mock session/fixture，不待 T1b）。

### T-wiley wiley adapter（`adapter/wiley`，TDM 档 + 双窗口限速 + token 门控）——D-024 纳入，W2 平台波第三件·**依 T1a+T2**
**Files**：新建 `src/paper_crawler/adapters/wiley/`（`adapter.py`/`parse.py` + entry point）、`tests/fixtures/wiley/`
（TDM 成功响应截断脱敏 / 401·403·429 三态 / 页面 auth 四件套）、`tests/{unit,contract}/test_wiley_*.py`、
`tests/online/test_wiley_smoke.py`（`-m online`，token 门控）、`tests/manual/wiley_runbook.md`。
**Interfaces**：`RESOLVE|FETCH`（enumerate 走 crossref，DOI 前缀 10.1111/10.1002/10.3982）；TDM 客户端 = httpx +
`Wiley-TDM-Client-Token` 专属 client（wiley.md §3）；**双窗口限速** = 单 token bucket `RatePolicy(rpm=5, burst=3)`
（起步保守；wiley.md §4 接缝结论：**无需扩展 ratelimit.py 冻结件**）；`ApiKeyProvider`（T1b）token `[auth.wiley].token`
（Config-slot 解析归 **T2**，D-025）；错误映射（wiley.md §5，B-M2）：401→auth_expired、403→no_entitlement（订阅域约束，不计 failed）、
**任意 429→rate_limited**、CF→challenge。
**DoD**：`make check` 绿；解析器 ≥90%；三态 fixture 回放全绿；双窗口限速器映射单测（3 连发 wait=0、第 4 wait≈10s，假时钟）；
**token 门控**——无 token → 在线冒烟 skip + canary NotImplementedError→SKIP（不阻塞验收，s2 先例）；有 token → 单篇冒烟 ≤1。
**平台详设门禁**：`wiley.md`（本次 P0b approved）后开工。
**测试判据**：AC-4.1（JF/ECMA 单篇，token 到位，真实取回归 T7b）、AC-4.3（403 no_entitlement 降级）、AC-4.4（日配额）。**依 T1a+T2**（同 T3/T4）。

### T5 pipeline 集成 + `grab` 命令（`pipeline/auth-integration`，OA-fallback #12 + 健康门 + 日配额 + 工作时段 + BLOCKED）——跨模块缝合面·**依 T1b+T2**
**Files**：`src/paper_crawler/pipeline/stages.py`（`StageContext.oa_fallback`/`unpaywall_adapter`/**`http`** 槽 + `_stage_oa_fallback`
第七 handler + **`_fetch_oa_direct` 通用 direct 取回**（A-B1）+ `_stage_fetch` 顶部 OA-asset 分支 + 健康门/日配额/工作时段前置检查）、
`src/paper_crawler/pipeline/runner.py`（**`__init__(clock=)`**（B-M1）+ `_auth_batch` 健康门 + `_challenge_cooldown` +
`_stage_oa_fallback` 接 NO_ENTITLEMENT 分支 + **NO_ENTITLEMENT 改独立终态不计 failed**（A-m5）+ 工作时段窗（A-M2））、
`src/paper_crawler/storage/repo.py`（`count_fetch_today`（`DATE(ts)`，B-m5）+ `plan_asset` 支持 `source_adapter="unpaywall"`/`version=<oa串>`）、
**新增 `crawler grab --doi X [--venue Y]` 命令**（A-B3：DOI→venue 判定=显式 `--venue` 优先，缺省按 DOI 前缀/已入库 paper 反查 →
单篇 resolve+fetch 复用既有全链）、`src/paper_crawler/cli.py`（pull/grab 装配 AuthManager + unpaywall OA-fallback 注入 + `StageContext.http`）、
`src/paper_crawler/pipeline/report.py`（RunReport `no_entitlement=<n>` 字段+渲染，复审 n1）、`tests/integration/test_auth_pipeline.py`、`tests/unit/test_cli_grab.py`。**config.py 不在本卡**（凭证槽/加载链归 T2 独占，A-m3/D-025）。
**grab 补规格（复审 n2，controller 裁决 2026-07-23）**：退出码沿 design/05 Task 口径（0=成功 / 1=业务失败 / 2=用法·配置错）；DOI 未入库时先经 crossref 单篇 lookup → `MergeEngine.ingest(source="crossref")` 建最小 paper 行，再走 resolve+fetch（复用 Phase 3 全链零新协议；AC-4.1 runbook 的 JFE DOI 即此场景）。
**Interfaces**：auth-framework §8 全节（§8.1 OA-fallback direct 三接线点 / §8.2 健康门 N=20/15min（注入 clock）/ §8.3 日配额
`DATE(ts)` "fetch 尝试篇次" / §8.4 BLOCKED+冷却 24h / §8.5 no_entitlement 不计 failed / §8.6 工作时段窗）；`grab` = DOI→venue→单篇全链。
**纯附加/默认关闭**：`oa_fallback=False`+`clock` 有默认 → Phase 1-3 venue 零行为变化（回归锁定 = 现有全部 pipeline 集成测试；
NO_ENTITLEMENT 计数迁移经回归锁定）。
**DoD**：`make check` 绿；mock IdP 集成（依 T6 mock 载体接口约定）验证：no_entitlement→不计 failed + OA-fallback **direct 取回落盘** OA asset；
健康门 ≤20 篇内 EXPIRED→整批 BLOCKED 无 401 轰炸；日配额达上限→BLOCKED；工作时段窗外→延迟不失败；challenge→BLOCKED+冷却；`resume` 恢复；
`grab --doi <JFE DOI>` 单篇全链（离线 mock adapter）。**跨 pipeline/auth/unpaywall 三模块缝合面——fable 审查**。
**测试判据**：AC-4.2/4.3/4.4（集成层）、design/05 §2 BLOCKED-resume；检查单 #12（OA-fallback direct 取回接线）；AC-4.1 全链骨架（grab，真实取回归 T7b）。

### T6 mock IdP 集成测试全生命周期（`test/mock-idp`，AC-4.2/4.5/4.6 离线载体）·**依 T1b**
**Files**：`tests/integration/test_auth_lifecycle.py`（login→state 保存→复用→过期→refresh 全周期）、`tests/integration/
conftest.py`（mock IdP `MockTransport` handler + 进程内状态字典 + **注入时钟 seam**）、`tests/unit/test_auth_browser_seam.py`
（假 Playwright seam 单测首登逻辑 + mkdtemp 清理断言，不触真实浏览器）。
**Interfaces**：mock IdP = `httpx.MockTransport` 处理函数（复用 HttpClient `transport` DI seam），路由 `/login`/
`/my-account`/`/InstitutionalLogin`/`/article-pdf` 返 200/302/403（auth-framework §9）；**过期语义由 mock 状态驱动（B-M1，
不依赖 httpx cookiejar 真实 TTL）**——mock handler cookie-过期标志 + 注入时钟（`PipelineRunner`/provider `clock=`，
先例 `TaskQueue`/`AclAnthologyAdapter`）；**纯 httpx 零真实网络零 Playwright**；真实浏览器测试 `skipif(not [auth-browser] or not $PC_BROWSER_TESTS)` 双重跳过。
**DoD**：`make check` 绿（默认不 import playwright；CI 装 `[auth]`，B-m7）；全生命周期覆盖 OK/EXPIRED/CHALLENGED 三态 +
refresh 成功/返 None 两路 + logout 取证；**mock 载体接口约定**就绪供 T5 并行消费（集成终验在 T6 合并后）。
**测试判据**：**AC-4.2 断言双源（B-m8：MockTransport handler 请求计数为主 + obslog 401 事件扫描为辅）**；AC-4.5（logout 无残留）、
AC-4.6（挑战→BLOCKED+冷却）——**三者 CI 离线判定**。

### T7a AC-4 离线端到端（`feat/ac4-e2e-offline`，opus/controller 亲验）·**依 T5+T6**
**Files**：`docs/testing/records/2026-MM-DD-ac4-acceptance.md`（AC-4.2~4.6 mock 层汇总验收记录初稿）、`tests/integration/`（端到端场景）。
**Interfaces**：分层验收（D-018）离线层——AC-4.2（过期检测≤20 篇 BLOCKED 无轰炸，双源断言）/4.3（no_entitlement 不计 failed + OA-fallback direct 取回）/
4.4（日配额 `DATE(ts)` 对账）/4.5（logout 取证无残留）/4.6（挑战→BLOCKED+冷却）全在 mock 层跑通；BLOCKED-resume 演练（auth login→resume、challenge 冷却→resume）。
**DoD**：AC-4.2~4.6 离线 PASS；验收记录初稿成文（含适用边界）。**controller 亲验**。**独立于 key——不阻塞 T8 离线收尾**。
**测试判据**：AC-4.2~4.6 全线（mock 层）+ AC-4.4 配额对账。

### T7b 在线 runbook（`feat/ac4-runbook`，opus+controller 亲验）·**依 T3+key 到位（BLOCKER-1 外部依赖，游离）**
**Files**：`tests/manual/{elsevier,oup,wiley}_runbook.md`（真实凭证执行留痕）、`tests/online/test_elsevier_smoke.py`（真实 key 冒烟 committed）、
`docs/testing/records/`（AC-4.1 真实取回补录）。
**Interfaces**：真实凭证"用户参与层"——AC-4.1（`auth login elsevier`→JFE DOI 经 Article API 得魔数校验合格 PDF；wiley token→JF/ECMA；oup SSO→QJE）+
BLOCKED 真实演练。在线预算 T7b runbook 真 key 窗 ≤40 req（plan §3，不进 CI 的 `tests/manual/`，B-m9 与 committed 冒烟 ≤5 分列）。
**DoD**：key/token 到位后 AC-4.1 真实单篇魔数校验合格 + 日配额对账 + BLOCKED-resume 真实演练留痕。**key 未到位则按 plan §3 降级口径（runbook-only 分层，离线 DoD 不阻塞）**。
**测试判据**：AC-4.1（真实 key/token 单篇）。**游离于主线**——T8 离线收尾不待 T7b，T7b 可后补。

### T8 收尾（`fable 编排 + sonnet 执行`）·**依 T7a（T7b 可后补）**
**Files**：`docs/testing/records/`（AC-4 验收记录终稿）、AC-0 系统性扫描脚本产物、`elsevier-sd.md`/`oup-silverchair.md`/
`wiley.md` → implemented、`auth-framework.md`/`10-config-layout.md`/`07`/`04` → implemented、`docs/INDEX.md`（登记
auth-framework.md/10-config-layout.md/phase4-plan + 三平台状态）/`progress.md`/`decision-log.md`（D-023/D-024/D-025 已于 P0b 落地，
此处只需 INDEX 摘要与状态同步）、`docs/reports/2026-MM-DD-phase4-report.md`、tag `phase-4`。
**DoD**：**AC-4.2~4.6 离线全过（不待 key）**；AC-4.1 = key 到位则 T7b PASS，否则 runbook-only 分层如实记录（D-018，不阻塞 tag）；
AC-0 系统性扫描（git 全历史无 `*.enc`/`.filekey`/`paper-crawler.toml` 敏感/cookie 形态 AC-0.3、日志正则 AC-0.4、限速/robots AC-0.5）
全过；INDEX/progress/decision-log 同步；阶段报告成稿；`make check` 全绿状态打 tag。**fable 全分支终审**。

### M2a 在线债务（`chore/phase4-debt-online`，sonnet/轻审，**已先行开工 2026-07-23**·游离）
**Files**：D-019 四站锚点核准（pmlr/cvf/acl_anthology/neurips_proceedings，检查单 #13，≤25 req 入 fixture）；aaai_ojs 全库 OAI
**量级评估** ≤3 req（**只评估，批预算后另行执行**，检查单 #8）；六项 `[UNRESOLVED]` 盘点（文档级，检查单 #14）。
**DoD**：D-019 四站锚点人工核准入 fixture（UPDATE_GOLDEN + records 留痕）；aaai OAI 量级评估结论入报告；UNRESOLVED 盘点清单成文。
**规格源 = Phase 3 报告检查单**（不待本 plan approved，已派）；在线预算 M2a：锚点 ≤25 计 §3 D-019 分项、aaai 评估 ≤3 计缓冲行（复审 n5）。

### M2b 离线债务（`chore/phase4-debt-offline`，sonnet/轻审，**已先行开工 2026-07-23**·游离）
**Files**：测试补强批（检查单 #15：cursor 中断→窗口重建→DOI 去重端到端 fixture / oa-report 循环端到端限速锁 / 契约 factory
补齐收窄 24 skip / F2/F1 美容项）；`progress.md` 模块状态表刷新（检查单 #11）；`budget.py` 跨进程 `fcntl.flock`（检查单 #10，非阻塞）。
**DoD**：各残项逐条闭合或明确改期入报告；`make check` 绿。**规格源 = Phase 3 报告检查单**（不待本 plan approved，已派）；**离线零在线预算**。

## §5 波次并行图与冲突面预算

```
W0(已完成): R0 平台勘察(实耗5/25) ‖ auth-framework.md + 三平台详设 + 10-config-layout 双评审修订轮 → 待复审 approved
W1:        T1a 冻结件先行包(fable) ‖ T2 平台地基件+config(opus)          [两者无依赖，复审通过即同波开工]
W2:        T3 elsevier(opus) ‖ T4 oup(opus) ‖ T-wiley(opus) ‖ T1b auth 本体(fable)   [T3/T4/T-wiley 依 T1a+T2；T1b 依 T1a+T2]
                                                                        [T3/T4/T-wiley 另依各自平台详设 approved]
W3:        T6 mock IdP(sonnet) ‖ T5 pipeline 集成+grab(opus)            [T6 依 T1b；T5 依 T1b+T2；用 conftest mock 载体接口约定并行，集成终验在 T6 合并后]
W4:        T7a 离线端到端(opus→controller 亲验) → T8 收尾(sonnet+fable 终审)  [T7a 依 T5+T6；T8 依 T7a，T7b 可后补]
游离全程:  T7b 在线 runbook(opus+controller，依 T3+key 到位·BLOCKER-1) ‖ M2a 在线债务(sonnet，已派) ‖ M2b 离线债务(sonnet，已派)
峰值并行 6 线：T1b + T3 + T4 + T-wiley + M2a + M2b
每任务: implementer(worktree) → 双裁决审查(Spec+质量, 限量真实交叉验证 ≤5 req) → fix 回派 → controller 合并亲跑 make check
```

**冲突面预算（worktree 波次并行的写文件重叠分析）**：
| 文件 | 写方任务 | 冲突管理 |
|---|---|---|
| `types.py` | **T1a**（SessionHandle 具体化 + 枚举） | T1a 独占；其余只读消费 |
| `errors.py`/`http.py`/`obslog.py` | **T2**（status_code + `AuthRequired`/`Challenged` **权威版** + 脱敏键） | **controller 裁决（D-024 波次）**：T2 为**单一权威版**——T1b provider 若需本地最小异常定义，合并取 T2（沿 Phase 3 `ids.py` 约定，非分叉）；T2 先合、T1b rebase 后 `import` |
| `config.py` | **T2 独占**（加载链 + `[auth.*]` 槽 + 敏感护栏，D-025） | **撞面消除**（替代旧"T1 优先落 config"）：T1a/T1b **零触** config.py |
| `config/` 三文件 | **T2**（README/config.example/profiles.example，D-025） | T2 独占（新建目录） |
| `cli.py` | **T1b**（auth 子 app 挂载）、**T2**（canary 装配 + `config show`）、**T5**（pull/grab AuthManager 注入） | 三方写——波次序化（T2→T1b→T5 逐波合并 rebase）+ 分节写入降文本冲突 |
| `pyproject.toml` `[project.optional-dependencies]` | **T1a**（auth/auth-browser extras + uv.lock） | T1a 独占 |
| **`pyproject.toml` `[project.entry-points]`（A-M6）** | **T3 + T4 + T-wiley 三方写**（各注册自己的 adapter entry point） | **已知 union 点**——controller 合并时统一 union（Phase 3 五源 entry-point 先例），各任务只加自己一行、不动他行 |
| `.gitignore` | **T1a**（`*.enc`/`.filekey`/`profiles.toml`/`auth/state/` 四条目）、**T2**（`paper-crawler.toml` 防误提交） | 分条目 append，无重叠行 |
| `pipeline/{stages,runner}.py` `storage/repo.py` | **T5 独占** | 单任务，无并行冲突 |
| `venues/econ/qje.yaml` | **T4**（fulltext 收敛 #2） | T4 独占 |

- **关键序化（controller 裁决，D-024 波次）**：`errors.py`/`http.py`（T2）→ `auth/providers/*`（T1b 抛异常）跨任务依赖——
  **T2 = 单一权威版**（T1b 不维护分叉，合并取 T2，沿 Phase 3 `ids.py` 约定）；执行序 = T2 先合、T1b rebase 后 `import`。
  `cli.py` 三方写（T1b/T2/T5）靠波次逐合 + 分节降冲突；**`pyproject.toml` entry-points 三平台 union 由 controller 合并统一（A-M6）**。
- **T-wiley/T3/T4 平台并行无相互冲突**：三平台各独占 `adapters/<id>/` 包目录 + fixture 目录（disjoint），仅共享只读的
  T1a/T2 冻结件 + entry-points union 点（A-M6）——W2 三平台波真并行安全（沿 Phase 2/3 逐 adapter 独立分支先例）。

## §6 模型分配建议

**分配原则**：fable = 安全红线密度与裁决密度最高处（T1a/T1b 凭证安全、T5 缝合面、终审门）；opus = 判断力密集
（T2 地基件、平台 adapter、端到端）；sonnet = 规格已写死到字段级的执行件（T6、M2a/M2b）。

| 件 | 实现档 | 审查档 |
|---|---|---|
| W0 详设评审 A（技术一致性 + 安全架构） | — | fable |
| W0 详设评审 B（测试红线） | — | opus |
| T1a 冻结件实体化先行包（types/protocol/challenge/extras/gitignore） | **fable** | **fable**（独立实例，实现审查分离） |
| T1b auth 本体（store/providers/browser/manager/cli） | **fable** | **fable** |
| T2 平台地基件：config 分层加载 + status_code + canary 注入（**D-025 扩容，sonnet→opus**） | **opus** | **opus**（动 HttpClient/errors 冻结面 + config 加载链，全 adapter 受影响） |
| T3 elsevier_sd | opus | opus |
| T4 oup_silverchair | opus | opus |
| T-wiley wiley adapter（TDM + 双窗口限速 + token 门控，D-024） | **opus** | **opus** |
| T5 pipeline 集成 + grab（OA-fallback / 健康门 / 日配额 / 工作时段 / BLOCKED） | opus | **fable**（跨 pipeline/auth/unpaywall 三模块缝合面） |
| T6 mock IdP 集成测试 | sonnet | opus |
| T7a AC-4 离线端到端 | opus | controller 亲验 |
| T7b 在线 runbook（依 T3+key，游离） | opus | opus + controller 亲验 |
| M2a 在线债务（已派） | sonnet | sonnet 轻审 |
| M2b 离线债务（已派） | sonnet | sonnet 轻审 |
| T8 收尾 | sonnet + controller | fable 全分支终审 |

## §7 AC 映射与风险

| AC | 载体任务 | 验收形态 |
|---|---|---|
| AC-4.1 首登+取一篇 | T3（elsevier API 骨架）+ T-wiley（JF/ECMA）+ T5（grab 全链）+ **T7b**（真实 key/token 取回） | 真实 key/token runbook（JFE/JF 单篇魔数校验，key 到位后 T7b） |
| AC-4.2 过期检测不轰炸 | T5+T6（+T7a 汇总） | mock IdP 集成（≤20 篇 BLOCKED，无 401 轰炸，双源断言 B-m8） |
| AC-4.3 无权限降级 | T5+T6（+T3/T4/T-wiley 真实 no_entitlement） | 集成（no_entitlement 不计 failed + OA-fallback direct 取回） |
| AC-4.4 日配额 | T5 | FetchLog `DATE(ts)` "fetch 尝试篇次" 对账集成 |
| AC-4.5 登出无残留 | **T1b**+T6 | 取证清单按 kind 分列（store 无残留 + ⑥无残留 user-data-dir） |
| AC-4.6 风控即停 | T5+T6（+T4 `ChallengeDetector` 判定器） | mock 挑战页→BLOCKED+冷却 |

风险：①**elsevier key 未到位**（AC-4.1 前置外部依赖，申请 1–2 周）——R0 阶段确认，未到则 AC-4.1 降级 runbook-only
分层、离线 DoD 不阻塞（D-018）；②**oup 真实 SSO 含 MFA 无法自动化**（D-006 R2 已接受）——oup 取回归 runbook，
CI 层只测判定器 + mock；③**cryptography 首个二进制依赖**（虽 optional extra）——已由 **D-023** 定裁（optional extra + 惰性 import，APIKey 路径不触）；
④**wiley 已纳入**（D-024）但 token 缺失→在线层 skip（条件项，不阻塞主线；elsevier+oup 已覆盖 AC-4 全判据）；⑤**Cloudflare 挑战升级**
（elsevier/oup/wiley 均 Cloudflare 深度集成，R1 风险，R0 复核 elsevier API 返结构化 error 非挑战墙、oup/wiley 页面档撞挑战）——
API 优先（elsevier/wiley TDM）+ 挑战即 BLOCKED（不对抗）+ canary 周检。
