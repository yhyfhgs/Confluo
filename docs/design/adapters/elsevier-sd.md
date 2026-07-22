---
title: Adapter 设计 · Elsevier ScienceDirect（实现级）
status: approved
owner: fable5
updated: 2026-07-23
---

# Adapter · `elsevier_sd`(实现级详设)

> **AC-4.1 载体**（controller 预裁决，auth-framework §0）：`auth login elsevier` = APIKey 配置校验 + 配额探测；
> JFE DOI 经 Article Retrieval API 取 PDF——**不依赖机构 SSO**，使 AC-4.1 离线 DoD 不被真实机构首登阻塞。
> 勘察：[publisher-platforms-econfin.md](../../research/site-survey/publisher-platforms-econfin.md)（[LIVE] 2026-07-20，approved）
> + [publisher-platforms-p4-recheck.md](../../research/site-survey/publisher-platforms-p4-recheck.md)（[LIVE] 2026-07-23，R0 增量）。
> 接缝：[auth-framework.md §2/§3/§6/§8](../auth-framework.md)（AuthProvider/凭证库/status_code/pipeline 接线）、
> [design/04 §3](../04-auth-gated-module.md)（获取策略阶梯第 1 档=官方 API）、[design/05 §4](../05-pipeline.md)（错误分类学）。
> 红线（AGENTS §6）：只用用户自有合法凭证；elsevier robots 默认全禁 + 全站 TDMRep → **页面爬取双重不可行 → API 是唯一正道**。

## 1. 定位

- **family**：`auth_gated`（推荐档：**官方 API**——auth_gated 三档阶梯第 1 档，design/04 §3）。
- **capabilities**：`RESOLVE | FETCH`——enumerate 一律 crossref（D-005）。domains：`api.elsevier.com`
  （**非** `www.sciencedirect.com`；现 stub 的 `www.sciencedirect.com` 域在 T3 改为 API host——页面路线不走）。
- **AuthProvider**：`ApiKeyProvider`（kind=`api_key`，backend=`bearer_token`）；密钥 `[auth.elsevier].api_key`
  (+ 可选 `.insttoken`)，走 Config-slot（auth-framework §3.4 两级凭证模型①，**不触 cryptography/keyring**）。
- **服务 venue**：JFE、JAcctEcon、JBF、JFI、JFM、JCorpFin、JEmpFin（金融）；JME、JET、JinTEco、JPubEco、
  JDevEco（经济）；EJOR（OR）；AIJ、Pattern Recognition、Neural Networks、Neurocomputing（AI）——一 adapter 覆盖 15+ 刊（NFR-1 杠杆）。

## 2. 站点勘察摘要（含 R0 2026-07-23 增量）

- **反爬 / robots（[LIVE] 07-20，07-23 复核一致）**：`www.sciencedirect.com` robots 默认全禁（`*`→`Disallow: /`）+
  Cloudflare 深度集成（403 + `cf-mitigated: challenge`）+ 全站 TDMRep（`tdm-reservation: 1`）；**`api.elsevier.com` 无 robots**
  （404 JSON error 封套 → 无路径级限制）。页面路线合规与工程双重不可行 → **API 唯一正道**（本 adapter 不实现页面兜底）。
- **官方 API（设计基座，[LIVE] 07-20）**：`Article Retrieval API`（`GET api.elsevier.com/content/article/doi/{doi}`
  或 `/pii/{pii}`，全文 XML/PDF；覆盖 Subscribed+OA+Complimentary）：**每周 50,000 次、10 req/s**，TDM 专用 key 不限量；
  `ScienceDirect Search API v2`（本 adapter 不用——enumerate 走 crossref）。配额 7 天重置，`X-RateLimit-*` 头，
  超限 429 + `X-ELS-Status: QUOTA_EXCEEDED`（**认证态**配额耗尽）。申请：机构订阅关联研究者免费（非商业）+ insttoken/校园 IP。
- **R0 增量（[LIVE] 2026-07-23，keyless 层实测）**：
  - `api.elsevier.com` 无 robots（404，`RESOURCE_NOT_FOUND` JSON 封套）——复核一致。
  - **匿名 keyless** `GET /content/article/doi/{JFE DOI}` → **HTTP 429 `RATE_LIMIT_EXCEEDED`**（**非 401**）；
    响应 `server: cloudflare`、`cf-ray …-HKG`、`x-els-reqid`/`x-els-transid` 有值；**无 `X-RateLimit-*`、无 `X-ELS-Status`**；
    错误封套 `{"error-response":{"error-code":"RATE_LIMIT_EXCEEDED","error-message":"Rate of requests exceeds specified limits…"}}`。
  - **判读**：keyless 层被**即时限流**（叠加云 egress IP 被 CF 判高风险）——**未触达 401/entitlement 层**。
    **正面结论**：API 返**结构化 JSON error（非挑战页 HTML）**，印证"API 是合规正道、非 challenge 墙"设计前提成立。
  - **429 保守化处置（B-M2，不依赖 X-ELS-Status 真值分流）**：keyless 429（无 `X-ELS-Status`，R0 [LIVE] 实测）与
    认证态配额耗尽 429（07-20 文档口径称带 `X-ELS-Status: QUOTA_EXCEEDED`，**keyless 层不可活验其真值**）
    **一律按认证态 429 保守处置**——读 `Retry-After` + **当日熔断**（rate_limited 特化），**不靠 `X-ELS-Status` 真值区分行为**
    （真值未活验，作行为分流不可靠）。`X-ELS-Status`/body error-code 仅入 detail 作观测，不改处置（§5）。
- **⚠ 待核验（BLOCKER-1，key 到位后 T3 实测）**：entitlement 端点/字段（AC-4.3）、`X-RateLimit-*` 真值、
  全文响应 PDF vs XML 可得性（按刊差异）、SI/attachment（objects）清单字段名——R0 keyless 429 拦在 auth 层前全部无法活验。
  **认证态 429 的 `X-ELS-Status` 真值同属不可活验项**（B-M2：故不作行为依据）。

## 3. 各阶段实现方案（字段级）

### 3.1 `resolve_assets(venue, paper, session)`（RESOLVE）
- 输入 paper 的 `doi` identifier（crossref enumerate 产出）。**流程**：
  ① entitlement 预检（design/04 §4"能查则查"最佳案例——Elsevier API 有 entitlement 语义 ⚠ 端点/字段待 T3 实测）→
  ② **有权** → `AssetPlan(kind=PDF, url=Article Retrieval API URL, url_strategy=API_CALL, auth_needed=INSTITUTIONAL,
  expected_type="application/pdf")`；XML 全文标记版作 `AssetPlan(kind=SOURCE, expected_type="text/xml")` **可选同存**
  （extract 阶段免 OCR 之利）→ ③ **无权** → 不产平台 AssetPlan、标 `no_entitlement`（pipeline 转 unpaywall OA-fallback，auth-framework §8.1）。
- **无 key 分支（BLOCKER-1）**：`ApiKeyProvider.ensure_session(interactive=False)` 见 key 缺失 → `raise AuthRequired`
  （error_class=AUTH_EXPIRED，detail="配置 [auth.elsevier].api_key 或 env PAPER_CRAWLER_ELSEVIER_API_KEY"）→
  pipeline 整批 BLOCKED(auth)、提示 `crawler auth login elsevier`。**离线测试不受阻**（resolve 逻辑经 mock/fixture 覆盖，
  key 缺失分支单测断言 AuthRequired，不发真实请求）。

### 3.2 `fetch_asset(plan, io, session)`（FETCH）
- `ApiKeyProvider` 构造**专属 HttpClient**（`extra_headers={"X-ELS-APIKey": <key>}`，配置了 insttoken 再加
  `"X-ELS-Insttoken": <insttoken>}`）——**绝不复用共享 client**（携密头随他域外泄属凭证红线，沿 s2/openreview 先例，auth-framework §凭证隔离）。
- httpx GET Article Retrieval API（`Accept: application/pdf` 优先，回退 `application/xml`）→ `io.write_stream` →
  pipeline 校验 `%PDF` 魔数 + bytes>0（stages `validate_pdf_magic`）。XML source 资产（若同取）expected_type=text/xml，跳 PDF 魔数校验。

### 3.3 `healthcheck(session)`
- **无 key** → `raise NotImplementedError("elsevier api_key 未配置")` → `crawler canary` SKIP（复用 s2/openalex
  NotImplementedError→SKIP 先例，零 canary 改动；auth-framework §7 凭证注入后生效）。
- **有 key** → 配额/连通探测（`quota_probe` = 已知有权 JFE DOI 的 Article API）→ 断言 200 + entitlement=true
  比对（⚠ entitlement 字段真值待 T3 实测捕获，`_HEALTHCHECK_*` UPDATE_GOLDEN 候选）。

## 4. 限速与预算表（每行带出处）

| 维度 | 默认策略 | 出处 | 标注 |
|---|---|---|---|
| API | **自限 2 req/s** + 读 `X-RateLimit-*` 头动态退避（远离官方 10 req/s，留余量给交互式使用） | 官方配额 Article API 10 req/s / 50k 周 | [LIVE] 07-20 |
| 日配额 | `Config.auth_daily_cap`（默认 200，04 §4；FetchLog 对账，auth-framework §8.3） | 全局纪律 | [DOCS] |
| 身份 | UA D-014 + `X-ELS-APIKey` 头即身份声明 | D-014 | — |

- `X-RateLimit-*` 动态读头在冻结 `HttpClient.get_bytes`（不暴露响应头）下**不可达**——落地为静态 2 req/s 保守上限 +
  429→`rate_limited` 退避（沿 crossref 同款裁决，aggregators.md §5.1）。`default_rate = RatePolicy(120, burst=1,
  source_note="Elsevier Article API 自限 2 req/s；官方 10 req/s，留余量 [LIVE 2026-07-20]")`。

## 5. 失败模式映射（对齐 HttpClient 冻结错误类 + `status_code`，auth-framework §6）

| 现象 | status_code | error_class | 说明 |
|---|---|---|---|
| **任意 429**（keyless `RATE_LIMIT_EXCEEDED` / 认证态 `QUOTA_EXCEEDED`，**统一保守**，B-M2） | 429 | `rate_limited` **特化** | 读 `Retry-After` + **当日熔断**（沿 openalex 预算熔断口径）；**不靠 `X-ELS-Status` 真值分流行为**（真值不可活验）；报告提示（keyless 时提示配 key） |
| API 401/403（key 失效 / insttoken 错） | 401/403 | `auth_expired` | → BLOCKED，提示重配 key（`crawler auth login elsevier`） |
| entitlement=false（有权探测否） | 200/403 | `no_entitlement` | 不计 failures（auth-framework §8.5）；转 unpaywall OA-fallback（§8.1）⚠ 判定字段待 T3 |
| API 404（DOI 未收录/太新） | 404 | `gone` | 新文收录延迟属常态 → 延迟重试队列 24h 一次 |
| XML/PDF 空壳 | — | `integrity`(auth_leak) | 魔数/大小校验失败 → 触发 healthcheck |

- **`status_code` 精确分流**（auth-framework §6，检查单 #4）：401 vs 403 vs 429 的分类不再靠异常消息文本嗅探——
  `exc.status_code` 直读。**429 一律保守当日熔断**（B-M2）；`X-ELS-Status`/body error-code 仅入 detail 作**观测**
  （keyless-vs-quota 区分是诊断信息、**非行为分流依据**——认证态真值不可活验）。

## 6. AC-4.1 载体细化（`auth login elsevier` + `grab JFE DOI` 全链）

1. **`crawler auth login elsevier`**（auth-framework §4.1，api_key 分支）：校验 `[auth.elsevier].api_key` 存在
   （keyring/config/env）→ 调 `quota_probe`（已知有权 JFE DOI）连通 + entitlement 探测 → 写/更新
   `SessionHandle(provider_id="elsevier", backend=BEARER_TOKEN)`。退出码：0 成功；2 key 缺失（AuthRequired 提示配置路径）；1 探测失败。
2. **`crawler grab --doi <JFE DOI>`**：resolve（entitlement 预检 → AssetPlan API_CALL）→ fetch（`X-ELS-APIKey`
   专属 client GET Article API → PDF）→ `%PDF` 魔数校验 → 落盘 `data/pdf/jfe/<year>/<ulid>.pdf`。
   **AC-4.1 判据**：真实 key 下单篇 JFE DOI 得魔数校验合格 PDF（真实凭证 runbook，`tests/manual/elsevier_runbook.md`，records 留痕）。
3. **key 缺失期（BLOCKER-1）**：AC-4.1 降级为 runbook-only 分层（D-018）——离线层（resolve/fetch 逻辑经 fixture
   回放、AuthRequired 分支单测）先行 PASS，真实 key 到位后补跑在线冒烟 + runbook 签署。**离线 DoD 不阻塞于 key**。

## 7. Fixtures 与测试

- **T1 单元**：DOI/PII 规范化；entitlement 响应判定（⚠ 真值待 T3，先合成占位 + 结构断言）；**任意 429→保守当日熔断**
  （B-M2，不靠 X-ELS-Status 分流）；无 key → AuthRequired 分支。
- **T3 fixture（JSON 封套集，非 HTML——B-M3：elsevier API 返结构化 error 非挑战页）**（脱敏）：
  ① Article API 全文响应截断样本（脱敏 key）② entitlement true/false 两样本
  ③ **keyless 429 `RATE_LIMIT_EXCEEDED`**（R0 [LIVE] 真实封套脱敏）
  ④ 认证态 429 `QUOTA_EXCEEDED`（**⚠[DOCS]-合成，keyless 层不可活验**，B-M2；标注合成来源）。**不设 HTML 四类**（无页面路线）。
- **T3 在线冒烟**（`tests/online/test_elsevier_smoke.py`，`-m online`，**committed 层 `MAX_REAL_REQUESTS≤5`**）：**key 门控**——
  无 key → pytest `skipif`（不发请求；canary 层 NotImplementedError→SKIP）；有 key → entitlement 预检 1 + JFE 单篇 1（≤2）。
- **预算层次分列（B-m9）**：committed 在线冒烟 ≤5 req（本行，进 CI 的 `-m online`，BLOCKER-1 key 到位后 committed）
  **≠** T7b runbook 真实 key 窗 ≤40 req（plan §3 分项，不进 CI 的 `tests/manual/`）——两层预算独立标注，勿混。
- **T7b runbook**（`tests/manual/elsevier_runbook.md`，records 留痕，用户参与层）：真实 key：entitlement 预检 → 取 1 篇 JFE →
  配额头审计 → key 失效演练。**验收关联**：AC-4.1（JFE 单篇，本 adapter 核心场景）、AC-4.3（no_entitlement 降级）、AC-4.4（日配额）。

## 8. 风险与维护

- **BLOCKER-1（Elsevier API key 缺失）**：Phase 4 前置外部依赖（机构订阅关联、非商业；申请周期 1–2 周预留，R1 缓冲）——
  R0 已确认 config/env 无 key、已请求用户提供；未到位则 AC-4.1 runbook-only 分层，离线 DoD 不阻塞（D-018）。
- Elsevier API 条款演变（TDM 政策收紧趋势）：每次大版本前复读条款；配额变化经 healthcheck 探测自动发现。
- 本 adapter 是"API 优先原则"样板——API 现状 R0 复核确认（结构化 error、非挑战墙），设计假设成立；
  剩余 T3 实测仅为 entitlement 字段名 / PDF vs XML 可得性 / attachment objects 清单（key 到位后一次性核验）。

## 9. 修订记录

| # | 日期 | 修订 | 依据 |
|---|---|---|---|
| 1 | 2026-07-20 | 初稿（survey 级，status review） | publisher-platforms-econfin.md [LIVE] |
| 2 | 2026-07-23 | **扩写至实现级**（status draft）：resolve/fetch/healthcheck 字段级 + R0 增量（keyless 429 语义、结构化 error 非挑战墙）+ AC-4.1 载体全链 + BLOCKER-1 key 缺失期行为（AuthRequired 离线不阻塞）+ `[auth.elsevier]` Config-slot + status_code 精确分流（#4）+ SI/attachment ⚠ 留 T3；域 www.sciencedirect.com→api.elsevier.com | [R0 复核](../../research/site-survey/publisher-platforms-p4-recheck.md) [LIVE 2026-07-23] + auth-framework.md |
| 3 | 2026-07-23 | **双评审修订轮**：B-M2 **任意 429 统一保守当日熔断**（废止"两 429 X-ELS-Status 真值分流"——认证态真值不可活验，只作观测）；B-M3 fixture 改 **JSON 封套集**（非 HTML 四类；quota-429 标 ⚠[DOCS]-合成）；B-m9 预算层次分列（committed 冒烟 ≤5 vs T7b runbook ≤40）；no_entitlement 不计 failures（auth-framework §8.5）；runbook 归 T7b 用户参与层 | 评审 B 裁决 |
