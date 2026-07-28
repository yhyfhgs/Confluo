---
title: Adapter 设计 · Wiley Online Library（实现级）
status: implemented
owner: fable5
updated: 2026-07-29
---

# Adapter · `wiley`(实现级详设)

> **裁决=纳入本 Phase + token 门控**（D-024，R0 2026-07-23）：端点/头/速率已升级为活验；实现模式 = 完整 adapter +
> TDM 客户端 + token 存在性门控（缺失→在线层 skip，不阻塞验收，s2 先例）。
> 勘察：[publisher-platforms-econfin.md](../../research/site-survey/publisher-platforms-econfin.md)（[LIVE] 2026-07-20）
> + [publisher-platforms-p4-recheck.md §3](../../research/site-survey/publisher-platforms-p4-recheck.md)（[LIVE 2026-07-23]，R0 升级为活验）。
> 接缝：[auth-framework.md §2/§3](../auth-framework.md)（ApiKeyProvider/[auth.wiley].token）、
> [ratelimit.py](../../../src/paper_crawler/ratelimit.py)（**双窗口限速表达 = 本文档 §4 接缝设计点**）。
> 红线：只用用户自有合法凭证；TDM 条款要求下载物仅本地挖掘、不再分发——与本系统红线天然一致（AC-0.1）。

## 1. 定位

- **family**：`auth_gated`（推荐档：**TDM API 优先**，页面 cookie 兜底——第 1→2 档，design/04 §3）。
- **capabilities**：`RESOLVE | FETCH`——enumerate 走 crossref（DOI 前缀 **10.1111 / 10.1002**；`10.3982` **已移除**，2026-07-24 修正）。**`10.3982` 不再由 wiley 持有**：该前缀 Econometric Society 自持、ECMA/TE/QE 三刊共用（crossref member 2359），裸 `10.3982→wiley` 会误路由 TE/QE、漏取自营新 ECMA；ECMA 过刊（doi.wiley.com）→wiley 的归属判定改由 **econsoc 运行时域名路由（方向 a）** 承担（见 [econsoc.md](econsoc.md) §3.3 / D-028 草案），**wiley 侧不再持有 `10.3982` 路由知识**。domains：`api.wiley.com`（TDM 主干；页面兜底 `onlinelibrary.wiley.com`）。
- **AuthProvider**：`ApiKeyProvider`（kind=`api_key`，backend=`bearer_token`）；token `[auth.wiley].token`（UUID），
  走 Config-slot（auth-framework §3.4 两级凭证模型①，不触 cryptography）。
- **服务 venue**：JF、Econometrica(ECMA)、RAND Journal、International Economic Review、Mathematical Finance、
  JEEA（部分年代）——金融第一刊与计量第一刊所在平台。**venue 注册实况（2026-07-29，审计修复 R4 批）**：JF、
  Mathematical Finance、RAND Journal of Economics、International Economic Review，**四刊 venue 已注册**
  （`venues/finance/{jf,mathfin}.yaml`、`venues/econ/{rand,ier}.yaml`，`fulltext_source: wiley`；此前 adapter
  虽实现但零 venue 引用，属装配缝缺口，本批补齐）。**ECMA 过刊段维持 econsoc 运行时域名分段路由**承接
  （不新增 wiley venue，D-028，见上一条）；JEEA 尚未注册（本批未交付，仍是本 adapter"设计声明但未落地"
  的唯一遗留覆盖面）。

## 2. 站点勘察摘要（含 R0 2026-07-23 升级取证）

- **TDM API（端点/头/速率 R0 [LIVE 2026-07-23] 升级为活验，07-20 因 CF 拦截仅转引）**：
  - 端点 `GET https://api.wiley.com/onlinelibrary/tdm/v1/articles/{DOI}` —— 按 DOI 返全文 PDF，**不支持关键词检索**。
  - 请求头 `Wiley-TDM-Client-Token`（token 为 UUID）——搜索索引原文："passing your Clickthrough Client token as the value of the `Wiley-TDM-Client-Token` header"。
  - 速率 **3 req/s + 60 次/10 分钟**（另一口径"约 10s/次持续"）——**双窗口**，§4 表达方案。
  - 客户端活跃维护：`WileyLabs/tdm-client` **v1.2.0（2026-07-02，80 commits）**；PyPI `wiley-tdm`（GitHub + 搜索索引二手确证）。
- **token 自助 + entitlement 订阅约束（R0 [LIVE]）**：token 签发 = **可自助**（WOL 个人账号 → click-through TDM
  license → 即得 Client API Token UUID，**无需人工邮件审批**）；**但 entitlement 受订阅域约束**——无机构订阅的个人账号
  即使持 token，对非订阅内容仍 403（`no_entitlement`）。现状：config/env **无 Wiley token**。
- **反爬 / robots（[LIVE] 07-20）**：`onlinelibrary.wiley.com` Cloudflare 通用质询（403）；robots 宽松（AI 点名仅
  GPTBot/Google-Extended，孤立 `Crawl-delay: 1` 作用域含糊、保守遵守）；无 TDMRep。**TDM API host `api.wiley.com` 是合规正道**。
- **ECMA 平台迁移修正（2026-07-24，依据 [econometric-society.md](../../research/site-survey/econometric-society.md) R0c [LIVE 2026-07-24]）**：Econometric Society 拥有 `10.3982` 前缀（三刊共用）；ECMA 已**前向切换**——新刊自营 `econometricsociety.org`（CC BY 4.0，走 `econsoc`）、**仅过刊段（~2010–切换点）留 Wiley**（doi.wiley.com，本 adapter 的**唯一有效覆盖面**）、pre-DOI 段（10.2307）在 JSTOR。R0c 实测：2015 DOI `10.3982/ECTA12058`→doi.wiley.com（TDM link 佐证过刊仍 Wiley）、2026 DOI `10.3982/ECTA23709`→econometricsociety.org 自营 200。故 wiley 对 ECMA 是"部分且正在失效"（PARTIAL & DECLINING），继续把新 ECMA 交 wiley 会 no_entitlement 漏取——**wiley 侧移除 `10.3982` 路由键**（`_WILEY_DOI_PREFIXES` 仅留 10.1111/10.1002；`is_wiley_doi(doi:str)` 单入参无域名/年代信息、无法判"过刊段"，故取移除非收窄），ECMA 过刊归属改由 econsoc 运行时域名路由（方向 a）判定，分段主设计见 econsoc.md §3.3 / D-028 草案。TE/QE 全开放走 `econsoc`（Phase 5）；JF 常有 SSRN 先行版 → ingest 的 `preprint_of` 高频场景（D-007）。

## 3. 各阶段实现方案（字段级）

### 3.1 `resolve_assets(venue, paper, session)`（RESOLVE）
- 输入 paper 的 `doi`。**首选** `AssetPlan(kind=PDF, url=api.wiley.com/onlinelibrary/tdm/v1/articles/{DOI},
  url_strategy=API_CALL, auth_needed=INSTITUTIONAL, expected_type="application/pdf")`（token 已配置时）。
- entitlement：TDM API 的 4xx 语义即预检（401 token 失效 / 403 无该刊权限，§5）。
- **无 token 分支——实况订正为 RENDER_PAGE 页面兜底（2026-07-29，引 [design/11](../11-browser-fetch.md) T11）**：
  本节原写"`ApiKeyProvider.ensure_session(interactive=False)` 见 token 缺失 → `raise AuthRequired` → BLOCKED(auth)"，
  browser-fetch 横切件定稿（D-030）后已改判——`resolve_assets` 无 token 时**不再**早退抛错，改产页面兜底
  `AssetPlan(kind=PDF, url=onlinelibrary.wiley.com/doi/pdf/{DOI}, url_strategy=RENDER_PAGE,
  auth_needed=INSTITUTIONAL)`；两态（TDM `API_CALL` / 页面 `RENDER_PAGE`）互斥、恒一、不双发。理由：
  browser-fetch 落地后，"本层不产不可取回的兜底计划"这条诚实边界已失去意义（同 aea ★接缝 A-1 同一原则，
  design/11 §4.6）——现存在真实可执行的浏览器上下文路径，继续 raise 会让一条真实可执行的全文路径对用户不可见。
  **`fetch_asset` 的 token 门控逐字不变**（见 §3.2）：它只服务 TDM `API_CALL` 计划，无 token 直调仍
  `raise AuthRequired`；`RENDER_PAGE` 计划从不经 `fetch_asset`，改经 browser-fetch 横切件（`_fetch_via_browser`/
  stages 层）执行，受 `[browserfetch].enabled` 三级门控制——门关时计划仍照常产出，由 stages 门拦截为
  `skipped`（不计 failures，D-030 裁决⑤门控表达纪律）。**离线测试经 fixture 覆盖，不发真实请求**。

### 3.2 `fetch_asset(plan, io, session)`（FETCH）
- TDM 主干：`ApiKeyProvider` 构造**专属 HttpClient**（`extra_headers={"Wiley-TDM-Client-Token": <token>}`；绝不复用共享 client，凭证红线）→
  httpx GET TDM endpoint → PDF → `io.write_stream` → `%PDF` 魔数校验。**本方法只服务该 TDM 计划**。
- 页面兜底：**实况订正（2026-07-29）**——本节原写"cookie jar 直取 `/doi/pdf/{DOI}`，被 Cloudflare 拦 →
  BrowserFetcher 同 context 兜底一次 → 仍失败 BLOCKED"，该路径**从未经本方法**；`RENDER_PAGE` 计划（§3.1）
  径由 browser-fetch 横切件在浏览器上下文内取回，`fetch_asset` 对它不可达（无 token 场景下 `fetch_asset`
  只会被 TDM 计划调用，而 TDM 计划恰恰要求有 token——故 `_require_token` 的门控在实践中不会被
  `RENDER_PAGE` 路径触发）。

### 3.3 `healthcheck(session)`
- **无 token** → `raise NotImplementedError("wiley token 未配置")` → canary SKIP（复用先例，auth-framework §7）。
- **有 token** → 已知有权 DOI HEAD/GET 探测（TDM token 连通）或账号页探针 → 断言 200 + PDF content-type。

## 4. 双窗口限速表达方案（**接缝设计点**：3 req/s 瞬时 + 60/10min 滑动）

**评估结论：现有单 token bucket（`ratelimit.py`）可表达，无需扩展冻结件。**

**映射**：`default_rate = RatePolicy(requests_per_minute=6, burst=3, source_note="Wiley TDM 3 req/s(瞬时,→burst=3) +
60/10min(滑动均值,→rpm=6) [LIVE 2026-07-23]；宁慢勿封起步保守，观测 429 后调（同 wiley.md 既有纪律）")`。

**论证**（`ratelimit.py` 单桶语义：rpm=refill 速率、burst=capacity）：
- **60/10min = 6 rpm 是绝对主导约束**——3 req/s(=180 rpm) 若跑满则 20s 即耗尽 10min 预算。把它设为 `rpm=6`
  令长程速率 ≤ 滑动窗均值（token bucket refill 6/min = 0.1/s）。
- **3 req/s 作 `burst=3` 桶容量**——令任意瞬时至多 3 连发（capacity=3；第 4 请求需等 1/0.1=10s，比"3/s 每秒"更严，合"最保守值"）。
- **token bucket 固有"容量级突发"**：首个 10min 窗最坏可超 60 至多 (burst−1)=2 次（初始满桶 3 + 后续每 10s 补 1 → 首窗约 63）。
  **"宁慢勿封"收口**：起步取**更保守** `burst=1`（严格 6/min 无突发，首窗 ≤60）**或** `rpm=5`（留突发头寸），
  实测真实 429 后按 wiley.md 既有"起步保守、观测后调"纪律放宽。**Phase 4 起步值建议 `rpm=5, burst=3`**（留 1/min 头寸 + 3 连发）。

**未来选项（当前不做，过度设计）**：真需严格多窗口强一致 → 最小扩展 = 同 domain 挂多个 `_Bucket`（3/s 桶 + 60/10min 桶），
`acquire` 取 `max(wait)`。当前主导窗单一（60/10min），单桶 + 保守参数已合规——**不扩展 `ratelimit.py` 冻结件**（接缝结论）。

- 页面兜底路径：`onlinelibrary.wiley.com` 域独立桶，**串行 1 req/6s + 日配额 200**（全局纪律）。
- **日配额口径 = "fetch 尝试篇次"**（A-M5，与 auth-framework §8.3 / oup §4 一字不差）：只数 fetch 阶段 fetch_log 行
  （成败均计，`DATE(ts)`）；TDM API 取回与页面兜底下载均属 fetch，resolve 页请求不计。

## 5. 失败模式映射（对齐 HttpClient 冻结错误类 + `status_code`）

| 现象 | status_code | error_class | 说明 |
|---|---|---|---|
| TDM 401（token 失效） | 401 | `auth_expired` | → BLOCKED，提示重配 token |
| TDM 403（无该刊权限） | 403 | `no_entitlement` | 订阅域约束（R0：持 token 亦可 403）→ 转 unpaywall/SSRN 版兜底（§8.1） |
| TDM 429（双窗口触顶） | 429 | `rate_limited` | 读 Retry-After 退避；限速器已压到 6 rpm 下罕见 |
| 页面 Cloudflare 挑战 | 403 | `challenge` | `cf-mitigated: challenge` → `Challenged` → BLOCKED + 冷却 24h（auth-framework §8.4） |
| PDF 魔数失败（伪装页） | — | `integrity`(auth_leak) | → 触发 healthcheck |

## 6. Fixtures 与测试（token 门控 skip 策略）

- **T-wiley 单元**：DOI 前缀路由（10.1111/10.1002 → 同 adapter；**`10.3982` 已从 `_WILEY_DOI_PREFIXES` 移除**——`is_wiley_doi(doi:str)` 单入参无域名/年代信息、无法判"过刊段"，故移除非收窄。**联动**：`tests/unit/test_wiley_parse.py:21,32` 锁死 `is_wiley_doi("10.3982/…") is True` 断言须随移除**同卡翻转**（10.3982 移入非 Wiley 组）；**实现顺序**＝`parse.py` 移除 + `ecma/te/qe` venue YAML 落地**同一实现卡**（`is_wiley_doi` 现零 runtime 调用属**休眠**，落地前无活风险）；见 §1/§2 + econsoc.md D-028 草案）；TDM 响应/错误码判定表；双窗口限速器映射
  （`RatePolicy(6,burst=3)` 的 acquire 序列断言：3 连发 wait=0，第 4 wait≈10s——假时钟精确断言，沿 ratelimit 单测先例）。
- **T-wiley fixture**：① TDM 成功响应（截断脱敏 token）② 401/403/429 三态 ③ 页面 auth 四件套（cookie 兜底档）。
- **T-wiley 在线冒烟**（`tests/online/test_wiley_smoke.py`，`-m online`）：**token 门控**——无 token → pytest `skipif`
  （不发请求；canary NotImplementedError→SKIP）；有 token → 已知有权 DOI 单篇 1（≤1）。**token 到位条件项**（plan §3 预算行 ≤10）。
- **runbook**（`tests/manual/wiley_runbook.md`，records 留痕，用户参与层）：TDM token 自助申请 → JF/ECMA 单篇 → token 失效演练。
  **验收关联**：AC-4.1（JF/ECMA 单篇，token 到位）、AC-4.3（403 no_entitlement 降级）、AC-4.4（日配额）。

## 7. 风险与维护

- **token 缺失（计划内前置依赖）**：token 自助可得（无邮件审批）但 entitlement 受机构订阅约束——门控 skip 不阻塞验收（D-024）；
  未到位则 live FETCH/runbook skip，离线 DoD（resolve/fetch 逻辑 + 双窗口限速 + 错误映射单测）先行 PASS。
- Cloudflare 策略变化：canary 周检；页面兜底失效不算整体失效（TDM 为主干）。
- 双窗口起步保守（rpm=5/burst=3），实测 429 后调——**首次真实 token 冒烟须审计实际 429 触发行为**再定稳态值。

## 8. 修订记录

| # | 日期 | 修订 | 依据 |
|---|---|---|---|
| 1 | 2026-07-21 | 初稿（survey 级，status review） | publisher-platforms-econfin.md [LIVE] |
| 2 | 2026-07-23 | **扩写至实现级 + 纳入本 Phase（D-024）**（status draft）：TDM 客户端规格（httpx + `Wiley-TDM-Client-Token`）+ **双窗口限速表达方案**（结论：单桶 rpm=6/burst=3 可表达，起步 rpm=5/burst=3 保守，无需扩展 ratelimit.py 冻结件；未来多窗口选项记录）+ `[auth.wiley].token` Config-slot + token 门控 skip 策略 + R0 升级活验（端点/头/速率 GitHub 二手确证、token 自助+订阅约束） | [R0 复核 §3](../../research/site-survey/publisher-platforms-p4-recheck.md) [LIVE 2026-07-23] + auth-framework.md + ratelimit.py |
| 3 | 2026-07-23 | **双评审修订轮**：§4 补日配额口径 **"fetch 尝试篇次"**（A-M5，与 auth-framework §8.3 统一）；no_entitlement 不计 failures（§8.5） | 评审 A A-M5 |
| 4 | 2026-07-24 | **10.3982 路由键联动修正 → 移除**（econsoc 详设 D3b；W0 评审 B 实证 `is_wiley_doi(doi:str)` 单入参无法判过刊段、"收窄"不可实现 → controller 终裁移除）：§1/§2 从 `_WILEY_DOI_PREFIXES` 移除 `10.3982`（仅留 10.1111/10.1002）+ ECMA 前向迁移注记；§6 点名 `test_wiley_parse.py:21,32` 断言随移除同卡翻转。ECMA 过刊归属改由 econsoc 域名路由（方向 a）。**分段主设计见 econsoc.md §3.3 / D-028 草案**；`parse.py` 移除 + venue YAML 落地同卡（`is_wiley_doi` 休眠零 runtime 调用），本次未改码 | [econometric-society.md](../../research/site-survey/econometric-society.md) R0c [LIVE 2026-07-24] |
| 5 | 2026-07-29 | **实况回填（非设计变更）**：①§3.1 无 token 分支由"`raise AuthRequired` → BLOCKED(auth)"更新为"产页面兜底 `RENDER_PAGE` 计划"（browser-fetch 横切件 D-030/design/11 T11 落地后的行为，此前本节仍停留在 T11 之前的旧语义）；②§3.2 页面兜底描述由"cookie jar 直取 + BrowserFetcher 兜底"更正为"`RENDER_PAGE` 计划径由 browser-fetch 横切件执行，不经 `fetch_asset`"；③§1"服务 venue"行补 venue 注册实况——JF/Mathematical Finance/RAND/IER 四刊已注册（R4 批），ECMA 过刊段维持 econsoc 路由，JEEA 仍未注册 | [D-030](../../plan/decision-log.md)；[design/11-browser-fetch.md](../11-browser-fetch.md) T11；`src/paper_crawler/adapters/wiley/adapter.py` 实码核实；`venues/finance/{jf,mathfin}.yaml`/`venues/econ/{rand,ier}.yaml` |
