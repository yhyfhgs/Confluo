---
title: Adapter 设计 · OUP（Silverchair 平台，实现级）
status: implemented
owner: fable5
updated: 2026-07-23
---

# Adapter · `oup_silverchair`(实现级详设)

> **QJE fulltext_source 收敛载体**（检查单 #2，phase3-report §6）：收敛 `venues/econ/qje.yaml` 当前借用
> `elsevier_sd` 的占位 → 真实 `oup_silverchair`。
> **CookieSession + SSOFlow provider 载体 + mock IdP 集成验证**（auth-framework §0 controller 预裁决）。
> 勘察：[publisher-platforms-econfin.md](../../research/site-survey/publisher-platforms-econfin.md)（[LIVE] 2026-07-20）
> + [publisher-platforms-p4-recheck.md](../../research/site-survey/publisher-platforms-p4-recheck.md)（[LIVE] 2026-07-23，R0）。
> 接缝：[auth-framework.md §2/§9/§11](../auth-framework.md)（AuthProvider/mock IdP/挑战判定器）、
> [design/04 §3](../04-auth-gated-module.md)（获取策略阶梯第 2 档=HTTP+session cookie）。
> 红线：只用用户自有合法凭证；QJE 匿名 403 challenge 持续 → **登录 session 态为工作前提**；挑战即 BLOCKED、不对抗。

## 1. 定位

- **family**：`auth_gated`（推荐档：**HTTP + session cookie**——第 2 档，design/04 §3）。
- **capabilities**：`RESOLVE | FETCH`——enumerate 走 crossref（DOI 前缀 10.1093）。domains：`academic.oup.com`。
- **AuthProvider**：`CookieSessionProvider`（出版社直接账号/校内已认证态，kind=`cookie_session`）或
  `SSOFlowProvider`（Shibboleth/OpenAthens，kind=`sso_flow`）；backend=`httpx_cookies`（storage_state 导出 cookie jar 直取）。
  多 profile：`oup@campus`（cookie）/ `oup@shib`（SSO），`config.toml [auth].active_profile` 选（auth-framework §3.4）。
- **服务 venue**：QJE、REStud、RFS、Review of Finance、EJ、JEEA、J. Financial Econometrics、RAPS、RCFS——
  一 adapter 覆盖 5+ 顶刊（经济金融密度最高平台，NFR-1 杠杆最大）。
- 平台族：Silverchair 托管平台（academic.oup.com 最大部署）；UChicago/MIT Press 结构近似但独立域（**顺延后续 Phase**，auth-framework §0），
  解析器基类 `silverchair_base` 预留共享（§8）。

## 2. 站点勘察摘要（含 R0 2026-07-23 增量）

- **URL 模式（[LIVE] 07-20 实例确认）**：期列表 `/{code}/issue/{vol}/{iss}`（如 `/qje/issue/140/1`）；文章
  `/{code}/article/{vol}/{iss}/{page}/{silverchair_id}`（如 `/qje/article/141/3/2205/8662148`；无权时 302→`/article-abstract/`）；
  **PDF `/{code}/article-pdf/{vol}/{iss}/{page}/{file_id}/{name}.pdf`**（如 `/qje/article-pdf/140/2/889/61701561/qjae044.pdf`
  ——**`file_id`（61701561）不可构造，须从文章页解析**，见 §3.1）。
- **robots.txt（[LIVE] 07-20，07-23 复核一致）**：**无任何 AI-bot 专门条目**（唯一具名 UA 为遗留爬虫 `008`）、无 Crawl-delay；
  `*` 组禁 `/bin/ /config/ /signin.aspx /search-results /DownloadFile/ /Citation/Download /Shibboleth.sso/ /user/logout`
  （SP 部署印证）；**期刊 `article`/`article-pdf` 路径未禁**（放行）；无 TDMRep。
  - **R0 补充差异（非颠覆）**：新增若干 society 门户 path 禁列（`/aaea/ /asm/ /pnas/ …`、`/*/chapter-ag-pdf`、`/store/*`）
    ——**不含** econ/fin 目标刊码（qje/restud/rfs/rof/ej）；目标刊仍 robots 放行。
- **反爬（[LIVE] 07-20，07-23 复核一致）**：Cloudflare 通用质询——**匿名 GET `/qje/article/141/3/2205/8662148` → 403
  `cf-mitigated: challenge`**（"Just a moment…" 5604B，含 `challenge-platform`/Enable JavaScript）；质询前无 404，路径与
  URL 模式一致。**结论**：匿名程序化访问不可行，**登录 session 态为工作前提**（adapter 设计假设成立）；挑战即 BLOCKED、不对抗（AC-0.2/4.6）。
- **官方 API/TDM**：**无公开 API**；非商业 TDM 含在机构订阅条款内（Data.Mining@oup.com）。认证：
  "Sign in through your institution"（SeamlessAccess/Shibboleth/OpenAthens）+ 部分个人订阅。abstract 免费；Oxford Open 混合 OA。

## 3. 各阶段实现方案（字段级）

### 3.1 `resolve_assets(venue, paper, session)`（RESOLVE）— **PDF file_id 解析器规格**
- 输入 paper 的 `doi`（10.1093/…，crossref 产出）。**流程**：
  ① `session` cookie jar 携带 GET `doi.org/10.1093/…` → 跟随重定向到 `academic.oup.com/{code}/article/{vol}/{iss}/{page}/{id}` 落地页 →
  ② **解析页内 PDF 链接**（`ChallengeDetector.classify` 先分类，OK 态才解析，auth-framework §11）：
  - **file_id 解析器**（`silverchair_base.extract_pdf_link`）：在落地页 HTML 内匹配 `article-pdf/{vol}/{iss}/{page}/{file_id}/{name}.pdf`
    的**完整链接**（`file_id`/`name` 均从页面锚点/`<a href>`/`citation_pdf_url` meta 抽取，**不构造**）——正则/DOM 双路
    （`<meta name="citation_pdf_url">` 首选，回退 `<a>` 含 `article-pdf` 的 href）；命中 → `AssetPlan(kind=PDF,
    url=<完整 article-pdf URL>, url_strategy=DIRECT, auth_needed=INSTITUTIONAL, expected_type="application/pdf")`。
  ③ **entitlement 启发式**：落地页为 `article-abstract` 路由**或**无 PDF 链接（`ClassifyResult.NO_ENTITLEMENT`，
    "Get access"/"Purchase" 面板）→ 不产平台 AssetPlan、标 `no_entitlement`（转 unpaywall OA-fallback，auth-framework §8.1）。
  ④ **SI（Supplementary data）**：文章页 "Supplementary data" 区解析生成附属 `AssetPlan(kind=SI)`（保持原名）。
- **无 session 分支**：`CookieSessionProvider.ensure_session(interactive=False)` 无 storage_state → `raise AuthRequired`
  （提示 `crawler auth login oup@campus`）→ 整批 BLOCKED(auth)。**离线测试**经四类 fixture 覆盖，不发真实请求。

### 3.2 `fetch_asset(plan, io, session)`（FETCH）
- `CookieSessionProvider` 导出的 **cookie jar 注入专属 HttpClient**（`extra_headers` 挂 Cookie；绝不复用共享 client，凭证红线）→
  httpx GET `article-pdf` 直取 PDF → `io.write_stream` → `%PDF` 魔数校验。
- **被拒兜底**（403/跳转）→ **BrowserFetcher 同 context 重试一次**（`[auth-browser]` 惰性；未装则不兜底、按错误分类处置）→
  仍失败按 §5 错误分类。下载物为 HTML（`%PDF` 校验失败）→ `integrity`(auth_leak) → 触发 healthcheck（拦截页伪装）。

### 3.3 `healthcheck(session)`
- **无 session** → `raise NotImplementedError("oup session 未配置")` → canary SKIP（复用先例，auth-framework §7）。
- **有 session** → 探针账号页（`/my-account` 类，**⚠ 设计假设，controller 亲读②：R0 无凭证未实测该路径**——
  真实 URL 待 runbook 首登时核验，允许 profiles `probe_url` 覆盖）→ `ChallengeDetector.classify`：OK（含账号标识）→ healthy；
  302→signin → EXPIRED；challenge 特征 → CHALLENGED。

## 4. 限速与礼貌

- **串行 1 req/6s + 日配额 200 + 工作时段窗**（design/04 §4/§5 全局纪律）；`default_rate = RatePolicy(10, burst=1,
  source_note="OUP 无明文 TDM 速率→全局保守 1req/6s [LIVE 2026-07-20]")`。
- **限速 vs 日配额两层，口径分离（A-M5，与 auth-framework §8.3 一字不差）**：resolve（页面解析）与 fetch（PDF 下载）
  **均过同一 `academic.oup.com` 域桶的逐请求限速**（每篇实际 2 请求，1 req/6s throttle 对两者都生效）；但**日配额
  按"fetch 尝试篇次"计**——只数 fetch 阶段 fetch_log 行（成败均计），**resolve 页请求不计**（resolve 不写 fetch_log）。
  即：限速器管每请求节奏（含 resolve），日配额 200 管 PDF 下载次数（不含 resolve 页请求）。OUP TDM 无明文速率数字 →
  维持全局保守；实现期可选礼貌动作：向 Data.Mining@oup.com 报备用途。

## 5. 失败模式映射（对齐 HttpClient 冻结错误类 + `ChallengeDetector`）

| 现象 | ClassifyResult | error_class | 说明 |
|---|---|---|---|
| 落地页 302→signin | LOGIN_REDIRECT | `auth_expired` | → 整批 BLOCKED；提示 `crawler auth login oup@campus` |
| article-abstract 路由 / "Get access" 面板（无全文） | NO_ENTITLEMENT | `no_entitlement` | 转 unpaywall OA-fallback（§8.1） |
| PDF 链接解析 0 命中（改版） | OK 但无链接 | `parse` | canary 标红（adapter 腐化信号） |
| 下载物为 HTML（伪装 PDF） | — | `integrity`(auth_leak) | 魔数校验失败 → 触发 healthcheck |
| 验证码 / 异常页（`cf-mitigated: challenge`/"Just a moment…"） | CHALLENGE | `challenge` | → `Challenged` → BLOCKED(challenge) + 平台冷却 24h（auth-framework §8.4）；**无破解尝试** |

## 6. QJE fulltext_source 收敛方案（检查单 #2）

- **现状**（`venues/econ/qje.yaml`）：`fulltext_source: elsevier_sd`（Phase 3 占位——真实平台 oup_silverchair 未注册，
  借已注册机构认证占位使 registry lint 通过；notes 已注明"待 Phase 4 落地 oup_silverchair 后改写"）。
- **收敛（T4）**：`oup_silverchair` adapter 经 entry point 注册后，改 `fulltext_source: oup_silverchair` +
  `auth: {level: institutional, provider_hint: oup_silverchair}`；`metadata_source: crossref` 不变（QJE 元数据仍 Crossref
  按 ISSN 0033-5533 全史枚举，AC-3.5 不受影响）。删占位 notes、`crawler venues lint` 亲跑绿。
- **对照验证**（oup-silverchair.md 特有）：AC-3.5 的 QJE 零爬取枚举依赖 crossref、**不做枚举**——本 adapter 只 RESOLVE|FETCH，
  收敛后 QJE 全文取回走 oup（需 session），元数据枚举仍 crossref，两条路职责分离验证。

## 7. Fixtures 与测试（**四类判定器 fixture，防御性判定用途**）

- **auth 四件套 fixture**（T4，脱敏；`ChallengeDetector` 判定器回归 = 04 §8 离线判定器基石）：
  ① **已登录全文页**（storage_state 态，含 `article-pdf` 链接 + `citation_pdf_url` meta）→ `ClassifyResult.OK`
  ② **未登录跳转页**（302→signin / `Shibboleth.sso`）→ `LOGIN_REDIRECT`
  ③ **无权限页**（article-abstract 路由 / "Get access"/"Purchase" 面板，无 PDF 链接）→ `NO_ENTITLEMENT`
  ④ **风控页**（R0 [LIVE] 真实 `403 cf-mitigated: challenge` "Just a moment…" 5604B，脱敏）→ `CHALLENGE`。
  真实响应**脱敏**（无 cookie/token/storage_state/个人信息）后入库；HTML 伪装 PDF 另入文件验证器单测。
- **T4 单元**：file_id 解析器（全文页/abstract 页/OA 页三态）；entitlement 判定器；`ChallengeDetector` 四态。
- **T4 在线冒烟**（`tests/online/test_oup_smoke.py`，`-m online`，`MAX_REAL_REQUESTS≤5`）：**匿名仅探测 URL 模式/robots
  一致性**（真实取回归 runbook——oup 需 SSO session，匿名必撞 403 challenge → 断言 challenge 特征即停，不重试绕过）。
- **真实 SSO runbook**（**"用户参与层"，D-018；`tests/manual/oup_runbook.md`，records 留痕，不进 CI**）：机构凭证
  SSO 首登（headed 浏览器，含 MFA）→ QJE 单篇取回 → 过期演练（删 cookie）→ 重登。**验收关联**：AC-4.1（QJE DOI
  `10.1093/qje/…` 即需求 US-9 样例）、AC-4.2/4.3（mock 层，auth-framework §9）、AC-4.6（挑战判定）；AC-3.5（QJE 枚举依赖 crossref 对照）。

## 8. 风险与维护

- **Silverchair 族基类**：`silverchair_base`（PDF 链接解析、entitlement 判定、探针逻辑）抽象——oup 本 Phase 落地，
  uchicago/mit_press 顺延后续 Phase 继承（平台升级一处修，NFR-2 摊薄）。
- **file_id 是黑盒**：`file_id` 规则不可构造 → fixture 覆盖多刊样本（qje+rfs 各一）防单刊特化；OUP 改版节奏较慢但改版即 `parse` canary 标红早发现。
- **真实 SSO 含 MFA 无法自动化**（D-006 R2 已接受）：oup 取回归 runbook（用户参与层），CI 层只测判定器 + mock IdP（auth-framework §9）。
- **探针 URL 定稿**（`/my-account` 类精确路径）留 T4 实现期定；TDM 用途邮件报备（可选礼貌动作）。

## 9. 修订记录

| # | 日期 | 修订 | 依据 |
|---|---|---|---|
| 1 | 2026-07-21 | 初稿（survey 级，status review） | publisher-platforms-econfin.md [LIVE] |
| 2 | 2026-07-23 | **扩写至实现级**（status draft）：CookieSession/SSO 全链 + **PDF file_id 解析器规格**（不可构造、从落地页/citation_pdf_url meta 抽取）+ **四类判定器 fixture 清单**（含 R0 真实 challenge 页脱敏）+ **QJE fulltext_source 收敛方案**（#2）+ 真实 SSO runbook 归用户参与层 + `ChallengeDetector` 接线 + R0 复核（robots 一致、QJE 403 challenge 持续、目标刊 robots 放行） | [R0 复核](../../research/site-survey/publisher-platforms-p4-recheck.md) [LIVE 2026-07-23] + auth-framework.md |
| 3 | 2026-07-23 | **双评审修订轮**：A-M5 §4 日配额口径改**"fetch 尝试篇次"**（resolve 页请求不计，与 auth-framework §8.3 一字不差）；controller 亲读② probe_url `/my-account` 标 ⚠ 设计假设（R0 未实测、runbook 核验、profiles 可覆盖）；no_entitlement 不计 failures（§8.5） | 评审 A A-M5 + controller 亲读 |
