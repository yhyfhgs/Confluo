---
title: Adapter 设计 · SSRN（实现级 · 聚合元数据主路径）
status: draft
owner: D1
updated: 2026-07-24
---

# Adapter · `ssrn`(实现级详设)

> **controller 预裁决（D-011 修订方向，本稿据此展开；裁决记录草案见 §10）**：模式 A（**Crossref 前缀 `10.2139` 枚举主干 + OpenAlex 交叉核对/补摘要**）升为**主路径**；模式 B（浏览器全文）降为 **opt-in 低配额能力**（§11 两案评估，controller 终裁）。SSRN 站点本体（`*.ssrn.com`）**默认零请求**（robots crawl-delay 5s + Cloudflare 门 + 本环境 TLS 阻断，三重证据）。**元数据与全文能力解耦**（D-005 同款）：元数据能力不依赖任何 SSRN 站点连通性。
> 勘察：[research/site-survey/ssrn.md](../../research/site-survey/ssrn.md)（R0a [LIVE 2026-07-24]，含 [PRIOR-LIVE 2026-07-20] 复用项）。
> 接缝：[aggregators.md §5.1/§5.3/§5.5](aggregators.md)（crossref 客户端/`parse` 复用、openalex `enrich_batch`、unpaywall OA-fallback）、[auth-framework.md §8.1/§9/§10/§11](../auth-framework.md)（OA-fallback 接线、browser 假 seam、`[auth-browser]`、`ChallengeDetector`）、[design/05 §4/§6](../05-pipeline.md)（错误分类学 / `resolve_offline`）、[arxiv.md §1/§3](arxiv.md)（`preprint_channel` + 虚拟桶先例）。
> 红线（AGENTS §6 / AC-0）：匿名 HTTP 直连 SSRN = **BLOCKED**（2026-07-20 Cloudflare + 2026-07-24 环境 TLS，双独立证据）；内部 `api.ssrn.com` **禁用**（D-014 第 4 条 / AC-0）；诚实 UA；不对抗挑战（AC-0.2）。

## 1. 定位

- **family**：`open_access`。**元数据层**取回姿态 = httpx 直连聚合 API（无认证，`auth_level=none`）——不是页面爬取，`*.ssrn.com` 零接触。**全文层（模式 B）**另绑 auth-framework browser seam（opt-in，§11）。**D-011 原 `free_account_preferred` 收窄注记**：元数据主路径 `auth_level=none`（聚合 API 无认证、零 SSRN 接触）；免费账号 session 仅在模式 B（浏览器全文）落地时才有意义，非元数据前提（§10 裁决记录）。
- **capabilities（集合论证见 §4.1）**：
  - **元数据层（Phase 5 committed）= `DISCOVER | ENUMERATE`**（前缀 10.2139 虚拟时间桶 + 枚举）。
  - `RESOLVE`：**元数据层仅产 landing 引用**（零网络 URL 构造，`resolve_offline=True`，D-022），全文 PDF 经 pipeline unpaywall OA-fallback（§8.1）——SSRN 侧勘察证实**无第三方 PDF 旁路**（landing-only）。
  - `FETCH`：**全文层（模式 B）条件能力**，Phase 5 默认**不点亮**（§11 案 B 推荐 defer 至 Phase 6 横切件）。
  - **无 `SEARCH`**：沿 arxiv.md §1 / aggregators §1 先例（冻结 `SourceAdapter` 协议无 `search()`；订阅命中经 enumerate + 本地 `Selector.filter_expr` 过滤，DSL 下推推迟 Phase 6 / AC-6.4）。
- **domains**：`api.crossref.org`（枚举主干）、`api.openalex.org`（enrich 交叉核对/补摘要，信用计费 ⚡）；`api.unpaywall.org`（OA-fallback，pipeline 侧）。`*.ssrn.com` / `papers.ssrn.com` **仅模式 B 触及，元数据层永不接触**。
- **服务 venue**：**单一 `ssrn` venue**（前缀 10.2139 全库）+ econ/fin 子网**近似**过滤（venue 建模裁决见 §3；对照 arxiv category-venue 的差异论证同 §3）。
- **AuthProvider**：元数据层 **无**（聚合 API 无认证）；模式 B = auth-framework browser seam（`auth/browser.py` 惰性 Playwright，§11），非 Phase 5 committed。

## 2. 站点勘察摘要（出处分级：[LIVE 2026-07-24] / [PRIOR-LIVE 2026-07-20] / [DOCS] / [推断]）

**结论：SSRN 无官方 API；第三方聚合 API 是完整、合规、无挑战门的元数据主通道；SSRN 站点本体匿名直连不可行（BLOCKED）。**

| 通道 | 可用性 | 关键实测（出处） |
|---|---|---|
| **Crossref** | ✅ 枚举主干 | `filter=prefix:10.2139` 注册方 Elsevier BV，总量 **1,414,774**；DOI 形态 `10.2139/ssrn.{abstract_id}`（内嵌下载主键）；支持 `sort=created`、`from-created-date`、facet、cursor 深分页（[LIVE]） |
| **OpenAlex** | ✅ enrich/交叉核对 | source `S4210172589`（"SSRN Electronic Journal"，host RELX），works **1,632,966**；`group_by=publication_year / primary_topic.field / open_access.is_oa`（[LIVE]，信用计费 ⚡） |
| **Unpaywall** | ⚠ 索引但非旁路 | 收录 SSRN DOI、`is_oa=true`，但唯一 `oa_location` 指回 `doi.org/10.2139/ssrn.*`（= SSRN 自身），`url_for_pdf=None`——**无第三方全文**（[LIVE]） |
| SSRN 官方 API / OAI / RSS / sitemap | ❌ / 未证实 | 无官方 API；内部 `api.ssrn.com` **禁用**（D-014）；RSS/sitemap 今日不可验证（传输阻断），列开放问题（§9） |

- **类型分布**（[LIVE]）：Journal Article **757,677** / Posted Content **657,096** / Conference Paper 1。**同一投稿在 Crossref 里类型不一致**——枚举**两类都收**（`journal-article` container="SSRN Electronic Journal"；`posted-content` 无 container）。此即**不能按 SSRN Electronic Journal 单一 ISSN 枚举**的证据（posted-content 半数不挂 journal container）→ 枚举须走**前缀**而非 ISSN（§4.2）。
- **规模/新鲜度**（[LIVE]）：全库 1.41M（crossref）/ 1.63M（openalex，含无 DOI 补录）；近年 2025≈243–262K、2024≈210K、2026(至 7 月)≈152K；最新 `created=2026-07-23`（勘察前一日）、abstract_id ~7.15–7.17M ⇒ Crossref 对新 DOI 有 **~1 日延迟**，足以驱动"近 N 天新 WP"增量（AC-5 元数据层）。
- **id 空间稀疏**（[LIVE]）：DOI'd 1.41M vs abstract_id 空间高至 ~7.17M；`ssrn.3000000`/`6000000` 均 404、`4056799` 200——id 空间有洞、非连续。缺口成因（① 大量投稿无 DOI / ② 稀疏跳号）须实现期量化（§9 覆盖率量化任务）。
- **挑战门 / BLOCKED**（合并双证）：`papers.ssrn.com` stateless 抓取 → **403 + "verify you are human"（Cloudflare `cf-chl`）**（[PRIOR-LIVE]）；本环境对**所有 Cloudflare 前置域**在 TLS 握手 reset（`SSL_ERROR_SYSCALL`，本机代理 `127.0.0.1:6152` fake-IP DNS，[LIVE 2026-07-24]）——**二者同向**：匿名 HTTP 直连 SSRN 不可行，记 BLOCKED，不对抗（详见 §6）。
- **robots**（[PRIOR-LIVE]）：具名封禁 `GPTBot`/`ChatGPT-User`/`Google-Extended`，`crawl-delay: 5s`。本系统 UA `PaperCrawler/...` **不属**被具名封禁者，落入 `User-agent: *`；`Disallow` 路径面今日未取得（**元数据层不触 SSRN 故不受其约束**；模式 B 落地前须重取，§9）。
- **全文下载形态**（[PRIOR-LIVE]）：`ssrn.com/abstract={id}` → `papers.ssrn.com/sol3/papers.cfm?abstract_id={id}`；下载 `Delivery.cfm/{name}.pdf?abstractid={id}&mirid=1`——**一次性 token，必须同一浏览器上下文即时使用**（模式 B 约束，§11）。

## 3. 覆盖边界与 venue 建模（controller 裁决点 #4：给方案 + 论据，正文出建议案）

**建议案：单一 `ssrn` venue（键 = crossref 前缀 `10.2139` 全库）；econ/fin/FEN 子网作 opt-in 的近似本地主题过滤层，而非独立的 crossref 可枚举 venue。**

**论据（对照 arxiv category-venue 先例的关键差异）**：
1. **arxiv 把 category 建为独立 `preprint_channel` venue（`arxiv-cs-lg`…）成立的前提是：其枚举源（OAI-PMH）原生支持按 category 精确过滤**（`set=archive` + 客户端 subject 过滤，arxiv.md §3）——每个 category venue 只枚举自己那一片。
2. **SSRN 的枚举源（crossref 前缀查询）无 network/eJournal 过滤维度**（勘察 §8 明证："Crossref/OpenAlex 无法按 SSRN network/eJournal 精确过滤"）。若把 FEN/ERN 各建为独立 venue，**每个子网 venue 都得枚举整个 1.41M 前缀再本地过滤**——零枚举成本节省，且子网边界只能用**主题近似**（OpenAlex field/topic），并非 SSRN 真实的 FEN/ERN 成员籍。以近似冒充精确 venue 边界会误导用户（把"econ 主题"当成"FEN 子网"）。
3. **故：一个 `ssrn` venue = 前缀 10.2139 全库**；econ/fin 定位表达为**可选本地过滤**（`Selector.filter_expr`），经 OpenAlex `primary_topic.field ∈ {Economics·Econometrics·Finance, Business·Management·Accounting}`（enrich 层已实现）**近似**实现，**如实标注为近似**（验收取 AC-6.3 式"本地过滤一致率 ≥95%"形态，**非**精确枚举断言）。勘察 [推断]：Economics/Finance + Business 领域 ≈ 48 万+，但 SSRN 已多学科化（Engineering 22 万、Medicine 7 万），非纯经济金融站——单 venue + 主题过滤如实反映此现实。
4. **未来物化子网视图的低成本路径（保留 D-002 杠杆）**：若用户确需 per-子网视图，可增薄 YAML 声明**同一 `ssrn` adapter** + `quirks.topic_filter`（econ/fin/law…）——**零 adapter 改动**；但它们是**同一枚举之上的派生切片**，非独立枚举单元。此与 §9 开放问题④（FEN→聚合过滤映射）联动。
5. **精确 per-eJournal 唯一硬路径 = SSRN 浏览页（Cloudflare 门）**——与红线冲突，降级/可选（模式 B 语境，§11），不作元数据主路径。

**覆盖边界（硬约束）**：① 元数据层覆盖 = crossref 前缀 10.2139 所含 DOI'd 投稿（已知盲区 = 无 DOI 投稿，§9 量化）；② 全文层覆盖 = **仅** unpaywall OA 直链命中者（SSRN 勘察证实 landing-only ⇒ 元数据层实际 PDF 命中 ≈ 0，如实标注）；③ 任何按 SSRN network 的**精确**枚举 = 无合规路径（不承诺）。

## 4. 各阶段实现方案（字段级）

### 4.1 capabilities 集合论证

| 能力 | 元数据层（Phase 5 committed） | 论证 |
|---|---|---|
| `DISCOVER` | ✅ | 预印本无"期"概念 → 按 (created 年 [/月/周]) 生成**虚拟时间桶** Issue（沿 arxiv.md §3 月度桶先例），**零 SSRN 接触**；桶计数 = crossref facet。 |
| `ENUMERATE` | ✅ | crossref `filter=prefix:10.2139` + created-date 窗 + cursor（§4.2）；产 `identifier(ssrn)` + `identifier(doi)` 的 PaperStub 流。 |
| `RESOLVE` | ✅（landing-only） | 零网络 landing URL 构造（`resolve_offline=True`）；PDF 交 pipeline unpaywall OA-fallback（§8.1）——SSRN 无第三方 PDF 旁路，默认无可下载 PDF asset（§4.4）。 |
| `FETCH` | ❌（模式 B 条件能力） | 全文唯一路径 = 浏览器 Delivery.cfm（Cloudflare 门）；Phase 5 默认不声明，§11 案 B 推荐 defer Phase 6 横切件。 |
| `SEARCH` | ❌ | 冻结协议无 `search()`；本地过滤（arxiv/crossref 先例）。 |

- **能力面净结论**：Phase 5 `ssrn.capabilities() = {DISCOVER, ENUMERATE, RESOLVE}`（RESOLVE 为 landing-only 零网络）；`FETCH` 随 §11 终裁点亮。**此集合全程 CI 可判、零 SSRN 接触**（controller 预裁决 #1/#2 兑现）。

### 4.2 `enumerate_issue(venue, issue)`（ENUMERATE，枚举主干）

- **端点**：`GET api.crossref.org/works?filter=prefix:10.2139,from-created-date:{桶起},until-created-date:{桶止}` + `cursor=*`→`message.next-cursor` 深翻至 `items` 空。**两类型全收**（不加 `type:` 过滤——journal-article + posted-content，§2）。
- **复用面（不改 crossref 冻结件）**：`ssrn` adapter **自持**枚举（前缀+created-date 语义 SSRN 专属，不属 crossref 按-ISSN 期刊主干），但**复用** `adapters/crossref/parse.py` 的 works JSON→`PaperStub` **纯逻辑映射** + 共享 `HttpClient`（`HttpClientConsumer.bind_http_client`，携 `[identity].email` polite pool）。cursor 契约、限速、UA 沿 crossref 既有实现（aggregators §5.1，逐字）。**裁决**：不给 crossref 加"前缀枚举模式"（避免改 implemented 冻结 adapter + 污染其按-ISSN 期刊语义）；SSRN 专属枚举策略留在 `ssrn` adapter。此为设计接缝点，提请评审确认（§10）。
- **DOI→abstract_id 抽取**：`items[].DOI` 经 `ids.normalize_doi()` → 正则 `^10\.2139/ssrn\.(\d+)$` 取 group(1) = abstract_id。产 `identifier(ssrn, abstract_id)`（下载主键）+ `identifier(doi, 全 DOI)`（跨源合并锚点，D-007）。**护栏**：DOI 不匹配 `ssrn\.` 中缀者 → 不产 `ssrn` identifier、计 `skipped_non_ssrn` 观测（防前缀 10.2139 下潜在非-SSRN DOI 误纳）。
- **字段映射**：复用 crossref `parse`——`title[0]`（空数组跳过 + `parse` 观测，沿 aggregators §5.1 裁决）、`published/issued` 日期族、authors、abstract（JATS，SSRN 侧常缺 → OpenAlex 补，§4.5）。source provenance tag = `"ssrn"`（枚举归属）/ DOI 锚点所有权中性。
- **增量 watch（"近 N 天新 WP"，AC-5 元数据层）**：`from-created-date:{今-N}`（created ≈ SSRN 新投稿入 crossref 时刻，~1 日延迟）整窗收割；去重由 `identifier(ssrn)` 主键天然保证（重叠窗口不产重复行，沿 arxiv "当月桶整窗重收割"先例）。**不依赖显式 watermark**（隐式经 created-date 窗表达）。`index-date` 作候补游标（含元数据更新，噪声高，[推断]），默认用 created-date。

### 4.3 `discover_timeline(venue, since)`（DISCOVER）

- **零网络虚拟桶**：`GET .../works?filter=prefix:10.2139&rows=0&facet=created:*`（1 请求）→ 按 created 年 facet 产逐年 `IssueRef`（`paper_count_claimed`=该年计数）；`label='YYYY'`、`year=YYYY`、`volume=NULL`（沿 arxiv 月度桶字段分解，幂等键 (venue, year)）。watch 语境下细化到月/周桶（`from/until-created-date` 边界）。`since` = 可选 created 年下界（勘察回溯 68 年桶，含脏未来年 2077/2103 → 上界按"今日"截断、下界默认合理起点如 1990，脏年不产桶）。

### 4.4 `resolve_assets(venue, paper, session)`（RESOLVE，landing-only 零网络）

- **纯 URL 构造（`resolve_offline=True`，免限速闸 D-022）**：由 `identifier(ssrn)` 产 landing 引用 `papers.ssrn.com/sol3/papers.cfm?abstract_id={id}`（`AssetPlan(kind=LANDING, url_strategy=direct, auth_needed=none)` 或仅入 `meta.landing_url`——**不产 PDF asset**）。
- **PDF 全文**：默认交 pipeline **unpaywall OA-fallback**（§8.1，VenueSpec 声明 `oa_fallback=true`）——按 DOI 查 unpaywall。**如实低预期**（勘察 §5）：SSRN 的 unpaywall `oa_location` 指回 SSRN 自身、`url_for_pdf=None` ⇒ `_oa_pdf_url_and_version` 返 None ⇒ `_stage_oa_fallback` 返 `done`**无 asset**（auth-framework §8.1 line 532：landing-only 不产 asset）。**净效果：SSRN 元数据层论文 = 元数据 + landing 链接，实际 PDF 命中 ≈ 0**（少数 econ WP 可经 RePEc/NBER/作者主页 OA 副本替代——Phase 5 联动 repec/nber adapter，非本 adapter 职责）。
- 模式 B 启用时（§11）：resolve 追加浏览器门 Delivery.cfm 计划（`url_strategy=render_page`、标 `volatile`、resolve/fetch 必须同批），此路径 Phase 5 默认不实现。

### 4.5 OpenAlex enrich（交叉核对 / 补摘要，非枚举）

- 走既有 `enrich_batch` 通道（aggregators §5.3）+ `crawler enrich --source openalex`：按 DOI 批查 OpenAlex source S4210172589 → 补 `abstract`（crossref 侧 ~70% 缺）、`primary_topic.field`（§3 子网近似过滤依据）、`open_access` 交叉核对。**受 credit 预算熔断**（`meta.cost_usd` 实时核销，aggregators §4）。openalex 位阶低于 crossref（字段级"补缺不覆盖"，§6 优先级表），不推翻 crossref 既有值。

<!-- SECTION-1-4-END -->
