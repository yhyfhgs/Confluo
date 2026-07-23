---
title: Adapter 设计 · SSRN（实现级 · 聚合元数据主路径）
status: approved
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
3. **故：一个 `ssrn` venue = 前缀 10.2139 全库**；econ/fin 定位表达为**可选本地过滤**（`Selector.filter_expr`），经 OpenAlex `primary_topic.field ∈ {Economics·Econometrics·Finance, Business·Management·Accounting}`（enrich 层已实现）**近似**实现，**如实标注为近似**（验收 = **确定性过滤逻辑单测**（§8 AC-5.1a②：固定 fixture 输入→期望输出精确断言），**非**精确枚举断言；原"≥95% vs OpenAlex field 基准"因过滤信号本取自 OpenAlex field、自比恒 100% 空判而废）。勘察 [推断]：Economics/Finance + Business 领域 ≈ 48 万+，但 SSRN 已多学科化（Engineering 22 万、Medicine 7 万），非纯经济金融站——单 venue + 主题过滤如实反映此现实。
4. **未来物化子网视图的低成本路径（保留 D-002 杠杆）**：若用户确需 per-子网视图，可增薄 YAML 声明**同一 `ssrn` adapter** + `quirks.topic_filter`（econ/fin/law…）——**零 adapter 改动**；但它们是**同一枚举之上的派生切片**，非独立枚举单元。此与 §9 开放问题④（FEN→聚合过滤映射）联动。
5. **精确 per-eJournal 唯一硬路径 = SSRN 浏览页（Cloudflare 门）**——与红线冲突，降级/可选（模式 B 语境，§11），不作元数据主路径。

**覆盖边界（硬约束）**：① 元数据层覆盖 = crossref 前缀 10.2139 所含 DOI'd 投稿（已知盲区 = 无 DOI 投稿，§9 量化）；② 全文层覆盖 = **仅** unpaywall OA 直链命中者（SSRN 勘察证实 landing-only ⇒ 元数据层实际 PDF 命中 ≈ 0，如实标注）；③ 任何按 SSRN network 的**精确**枚举 = 无合规路径（不承诺）。

## 4. 各阶段实现方案（字段级）

### 4.1 capabilities 集合论证

| 能力 | 元数据层（Phase 5 committed） | 论证 |
|---|---|---|
| `DISCOVER` | ✅ | 预印本无"期"概念 → 按 created 年生成**虚拟时间桶** Issue（沿 arxiv.md §3 月度桶先例），**零 SSRN 接触**；**纯生成零网络**（`paper_count_claimed=None`，规模锚移交 M1 census——真实 Crossref `facet=created:*` 返 HTTP 400，发现①仲裁令，§4.3）。 |
| `ENUMERATE` | ✅ | crossref `filter=prefix:10.2139` + created-date 窗 + cursor（§4.2）；产 `identifier(ssrn)` + `identifier(doi)` 的 PaperStub 流。 |
| `RESOLVE` | ✅（landing-only） | 零网络 landing URL 构造（`resolve_offline=True`）；PDF 交 pipeline unpaywall OA-fallback（§8.1）——SSRN 无第三方 PDF 旁路，默认无可下载 PDF asset（§4.4）。 |
| `FETCH` | ❌（模式 B 条件能力） | 全文唯一路径 = 浏览器 Delivery.cfm（Cloudflare 门）；Phase 5 默认不声明，§11 案 B 推荐 defer Phase 6 横切件。 |
| `SEARCH` | ❌ | 冻结协议无 `search()`；本地过滤（arxiv/crossref 先例）。 |

- **能力面净结论**：Phase 5 `ssrn.capabilities() = {DISCOVER, ENUMERATE, RESOLVE}`（RESOLVE 为 landing-only 零网络）；`FETCH` 随 §11 终裁点亮。**此集合全程 CI 可判、零 SSRN 接触**（controller 预裁决 #1/#2 兑现）。

### 4.2 `enumerate_issue(venue, issue)`（ENUMERATE，枚举主干）

- **端点**：`GET api.crossref.org/works?filter=prefix:10.2139,from-created-date:{桶起},until-created-date:{桶止}` + `cursor=*`→`message.next-cursor` 深翻至 `items` 空。**两类型全收**（不加 `type:` 过滤——journal-article + posted-content，§2）。
- **枚举接缝（controller 终裁 2026-07-24：扩展 `CrossrefAdapter` 通用 prefix 模式，与 nber 并轨 N-1=YES）**：`ssrn` 元数据枚举 = **消费扩展后的 `CrossrefAdapter`**，**非** ssrn 自持。**裁决背景（评审实码核实）**：`parse.py:114 parse_facet_years` 硬绑 `message.facets.published`、`to_paper_stub` 仅产 `(doi,)` identifier——故原稿"零改 crossref"**不成立**（prefix 枚举与 created facet 均触 crossref parse/adapter）。**扩展参数化两轴**（`CrossrefAdapter` 本体改动，nber/ssrn 共用**实现卡**，**规范出处 = [nber.md §3.1](nber.md)**，本稿只写消费侧契约）：① **enum-key** = `issn` XOR `prefix`（ssrn 走 `prefix=10.2139`）；② **date-field** = `published | created`（ssrn 走 `created`——枚举窗 `from/until-created-date`、discover facet `created`，§4.3）。cursor 契约、限速、UA、`to_paper_stub` 映射沿 crossref 既有（aggregators §5.1，逐字），共享 `HttpClient`（`HttpClientConsumer.bind_http_client`，携 `[identity].email` polite pool）。**SSRN 专属逻辑落 `ssrn` adapter 后处理层**（消费 crossref 产出的 `PaperStub` 流后加工，见下 abstract_id 条）。
- **DOI→abstract_id 抽取（`ssrn` 后处理层，消费 crossref `PaperStub` 流后加工）**：取 `to_paper_stub` 既产的 `(doi,)` identifier 的 DOI 值 → 正则 `^10\.2139/ssrn\.(\d+)$` 取 group(1) = abstract_id → **增补 `(ssrn, abstract_id)`**（下载主键；`to_paper_stub` 仅产 `(doi,)`，第二 identifier 由本层补）。DOI 锚点保留（跨源合并，D-007）。**护栏**：DOI 不匹配 `ssrn\.` 中缀者 → **不增补** `ssrn` identifier、计 `skipped_non_ssrn` 观测（防前缀 10.2139 下潜在非-SSRN DOI 误纳）。
- **字段映射**：复用 crossref `parse`——`title[0]`（空数组跳过 + `parse` 观测，沿 aggregators §5.1 裁决）、`published/issued` 日期族、authors、abstract（JATS，SSRN 侧常缺 → OpenAlex 补，§4.5）。source provenance tag = `"ssrn"`（枚举归属）/ DOI 锚点所有权中性。
- **增量 watch（"近 N 天新 WP"，AC-5 元数据层）**：`from-created-date:{今-N}`（created ≈ SSRN 新投稿入 crossref 时刻，~1 日延迟）整窗收割；去重由 `identifier(ssrn)` 主键天然保证（重叠窗口不产重复行，沿 arxiv "当月桶整窗重收割"先例）。**不依赖显式 watermark**（隐式经 created-date 窗表达）。`index-date` 作候补游标（含元数据更新，噪声高，[推断]），默认用 created-date。

### 4.3 `discover_timeline(venue, since)`（DISCOVER）

> **controller 发现①仲裁令（2026-07-24，优先于本节原文）**：T1 在线实测真实 Crossref `GET /prefixes/10.2139/works?facet=created:*` 返 **HTTP 400 `facet-not-available`**（`created` 非该路由合法 facet；合法含 `published`、不含 `created`）——活体哨兵 `tests/online/test_crossref_prefix_smoke.py::test_prefix_created_facet_ssrn`（XFAIL）。故本节**原 facet 方案（1 请求 created facet 产年桶）不可实现**，仲裁改**纯生成零网络年桶**（下）。**`enumerate`/watch 的 `from/until-created-date` filter 不受影响**（filter≠facet，勘察 §2 [LIVE] 已证有效）。

- **纯生成零网络年桶（现行方案）**：`discover_timeline` **纯本地生成** 1990..今年 逐年 `IssueRef`——**零请求、零 facet 依赖**（arxiv 月度桶纯生成同构，arxiv.md §3）。上界"今年"经**注入 clock** 取（沿 `TaskQueue.__init__(clock=)` / `pipeline.runner` 先例，保可测性——**不硬调 `date.today()`**）；下界默认 **1990**，`since` = 可选 created 年下界（取前 4 位、早于 1990 起点则钳到 1990）。字段：`label='YYYY'`、`year=YYYY`、`volume=NULL`、`number=NULL`、`pub_date=NULL`、`paper_count_claimed=None`（沿 arxiv 月度桶字段分解，幂等键 **(venue, year)** 不变）。**规模锚（每年计数）职责移交 M1 census**（OpenAlex source 代理，§9.1）——纯生成无权威计数、恒 `None`。**脏未来年天然不产**：纯生成连续区间 `[1990, 今年]` + 上界截断，故旧 facet 方案里的脏未来年（**2077/2103/2104**）根本不出现（无 facet 数据可污染）。watch 语境的增量新鲜度由 `enumerate` 的 `from/until-created-date` **filter** 窗表达（§4.2），非 discover。
- ~~**原方案（作废，存证）**：经扩展 `CrossrefAdapter`（date-field=`created`）`GET .../works?filter=prefix:10.2139&rows=0&facet=created:*`（1 请求）→ 按 created 年 facet 产逐年 `IssueRef`（`paper_count_claimed`=该年计数）；`parse.parse_facet_years` 泛化按 date-field 取 `facets.{field}`。~~ **T1 实测 `created` 非 Crossref 合法 facet（HTTP 400，[LIVE 2026-07-24]），改纯生成**（见上仲裁令 + §10.3 修订记录 #4）。`CrossrefAdapter` 的 created-facet 代码（T1 落地）仍为防御性泛化件、离线单测覆盖，但**对真实 Crossref 不可用**，ssrn discover 不消费之。

### 4.4 `resolve_assets(venue, paper, session)`（RESOLVE，landing-only 零网络）

- **纯 URL 构造（`resolve_offline=True`，免限速闸 D-022）**：由 `identifier(ssrn)` 产 landing 引用 `papers.ssrn.com/sol3/papers.cfm?abstract_id={id}`（`AssetPlan(kind=LANDING, url_strategy=direct, auth_needed=none)` 或仅入 `meta.landing_url`——**不产 PDF asset**）。
- **PDF 全文**：默认交 pipeline **unpaywall OA-fallback**（§8.1，VenueSpec 声明 `oa_fallback=true`）——按 DOI 查 unpaywall。**如实低预期**（勘察 §5）：SSRN 的 unpaywall `oa_location` 指回 SSRN 自身、`url_for_pdf=None` ⇒ `_oa_pdf_url_and_version` 返 None ⇒ `_stage_oa_fallback` 返 `done`**无 asset**（auth-framework §8.1 line 532：landing-only 不产 asset）。**净效果：SSRN 元数据层论文 = 元数据 + landing 链接，实际 PDF 命中 ≈ 0**（少数 econ WP 可经 RePEc/NBER/作者主页 OA 副本替代——Phase 5 联动 repec/nber adapter，非本 adapter 职责）。
- 模式 B 启用时（§11）：resolve 追加浏览器门 Delivery.cfm 计划（`url_strategy=render_page`、标 `volatile`、resolve/fetch 必须同批），此路径 Phase 5 默认不实现。

### 4.5 OpenAlex enrich（交叉核对 / 补摘要，非枚举）

- 走既有 `enrich_batch` 通道（aggregators §5.3）+ `crawler enrich --source openalex`：按 DOI 批查 OpenAlex source S4210172589 → 补 `abstract`（crossref 侧 ~70% 缺）、`primary_topic.field`（§3 子网近似过滤依据）、`open_access` 交叉核对。**受 credit 预算熔断**（`meta.cost_usd` 实时核销，aggregators §4）。openalex 位阶低于 crossref（字段级"补缺不覆盖"，§6 优先级表），不推翻 crossref 既有值。

## 5. 限速与预算表（每行带出处）

| 域 / 通道 | 默认策略 | 出处 | 标注 |
|---|---|---|---|
| `api.crossref.org`（枚举主干） | 静态 **5 req/s 上限** + 429→`rate_limited` 退避（读 Retry-After 入 detail）；UA 携 `mailto` polite pool | 沿 crossref 既有裁决（`X-Rate-Limit-Limit:10/1s`，留余量） | [LIVE] 07-22（aggregators §5.1） |
| `api.openalex.org`（enrich） | **每日 credit 预算 + `meta.cost_usd` 实时核销**熔断 | 2026-02 计费制 | [LIVE]/[DOCS]（aggregators §4） |
| `api.unpaywall.org`（OA-fallback） | 5 req/s 且日总量 < 100k；email 走查询参数（obslog 已脱敏） | 官方 | [DOCS]（aggregators §5.5） |
| `*.ssrn.com`（**仅模式 B**） | **1 req/5s（= robots crawl-delay 5s）+ 2–5s 抖动 → 有效 5–10s**；并发 1；日配额（默认 100/日，可配）；challenge→BLOCKED+冷却 24h | robots `crawl-delay:5s` | [PRIOR-LIVE] 07-20 |

- **元数据主路径预算 = 零 SSRN 请求**（controller 预裁决 #1）。上表 `*.ssrn.com` 行**仅模式 B 落地后生效**，Phase 5 默认不接触。
- **UA**：`PaperCrawler/<ver> (personal research; mailto:<user>)`（D-014，全程恒定、绝不伪装浏览器）；`default_rate` 带 `source_note`（`types.RatePolicy` 强制）。
- **日配额口径 = "fetch 尝试篇次"**（auth-framework §8.3，三处一字不差）：元数据层**无 fetch 阶段**（RESOLVE landing-only、无平台 PDF asset）→ **不占任何日配额**；OA-fallback direct fetch 落**第三方 OA host 桶**（§8.1，不占 SSRN 配额）。模式 B 的 `Delivery.cfm` 取回才计 `papers.ssrn.com` 域配额。
- **限速审计证据源**：元数据层聚合 API 请求**不入 FetchLog**（design/05 §7 口径：metadata 侧请求证据 = obslog jsonl 逐请求事件）；FetchLog 仅在模式 B fetch 或 OA-fallback direct 取回时落行。

## 6. Challenge 与 BLOCKED 边界（失败模式映射）

**核心不变式：元数据主路径零 SSRN 接触 ⇒ 元数据层永不触发 Cloudflare 挑战。Challenge/BLOCKED 边界只存在于模式 B。**

### 6.1 元数据层失败模式（对齐 HttpClient 冻结错误类 + `status_code`，design/05 §4）

沿 aggregators 逐字（crossref/openalex/unpaywall 三源错误映射，§5.1/5.3/5.5）：429/触顶→`rate_limited`（读 Retry-After）；4xx（filter/前缀语法）→`config`（响亮停机不重试）；5xx / 连接错→`transient`（退避 3 次）；cursor 过期→`transient`（窗口重建 `cursor=*`）；`total>0` 但 items 空→`parse`（canary 标红）；openalex 402/credit 耗尽→`rate_limited` 特化（当日熔断）。**新增 SSRN 专属**：DOI 不匹配 `ssrn\.` 中缀→**非错误**，计 `skipped_non_ssrn` 观测跳过（§4.2 护栏）。

### 6.2 模式 B 失败模式（仅全文层，Cloudflare 语境）

| 现象 | status_code | error_class | 说明 |
|---|---|---|---|
| Cloudflare 挑战页（`cf-mitigated: challenge` / "verify you are human" / `cf-chl`） | 403 | `challenge` | `ChallengeDetector.classify`（auth/challenge.py，§11 特征库）→ `Challenged` → **BLOCKED(challenge) + 平台冷却 24h**（auth-framework §8.4）；**绝不破解/绕过/重试**（AC-0.2） |
| 本环境 TLS 握手 reset（`SSL_ERROR_SYSCALL`，CF 前置域整体不通） | — | 环境障碍 | 本机代理 fake-IP，发生在 UA 发送前、**非 SSRN 判罚**；记 BLOCKED 停止该域后续请求，不换 UA/不绕行（勘察 §4） |
| `Delivery.cfm` 返 HTML 登录/付费页 | 200/302 | `no_entitlement` | 付费定价内容 → 标记 + OA-fallback（多为 landing-only 无副本，§4.4） |
| Delivery token 过期（跨批次复用） | — | `config` | **设计违规信号**：resolve/fetch 必须同浏览器上下文同批（§11 约束） |

### 6.3 BLOCKED 硬边界（勘察 §8，红线）

1. **任何对 `*.ssrn.com` 的直连 HTTP 枚举/抓取 = BLOCKED**（2026-07-20 Cloudflare 挑战 + 2026-07-24 环境 TLS 阻断，双独立证据）——元数据层因此**根本不走** SSRN 域。
2. **内部 `api.ssrn.com` 未文档化端点 = 禁用**（D-014 第 4 条 / AC-0 静态扫描项）。
3. **全文批量下载 = 无合规路径**；仅模式 B 用户发起单篇、浏览器上下文、限速内、遇挑战即 BLOCKED。

## 7. 测试与 fixture 计划（全离线可判；出处分级 [LIVE]/[DOCS]/合成）

- **T1 单元（零网络）**：① `DOI→abstract_id` 抽取正则矩阵（合法 `10.2139/ssrn.4056799`→`4056799`；非 `ssrn.` 中缀的 10.2139 DOI→护栏拒绝；大小写/前缀经 `normalize_doi` 归一）；② created-date 虚拟桶生成边界（下界起点、上界"今日"截断、**脏未来年 2077/2103/2104 不产桶**）；③ prefix+created-date URL 构造 + cursor 续拉窗口重建（假响应，`next-cursor`→items 空）；④ 复用 `crossref.parse` 的 works→PaperStub 已有覆盖，本 adapter 仅增 prefix-URL 与 SSRN identifier 产出单测。
- **T3 fixture（脱敏，复用 aggregators crossref/unpaywall fixture 规范）**：① crossref 前缀 works 正常页（**混 journal-article + posted-content 两类型** + 合法 `ssrn.` DOI，证两类全收）；② 空 created 窗（合法空，`total:0`）；③ cursor 两页续拉；④ 前缀 10.2139 下**非-ssrn 中缀** DOI（护栏路径 → `skipped_non_ssrn`）；⑤ **unpaywall SSRN 响应**（`is_oa:true`、`oa_location` 指回 doi.org、`url_for_pdf:null`）→ 断言 `_stage_oa_fallback` **不产 asset**（验证 §4.4"landing-only 净效果 = PDF 命中≈0"）；⑥ **7 收割日回放序列**（AC-5.1a① 判据载体）：跨 7 日 created 窗序列，含**重叠窗口**（相邻日窗交叠）+ **created 延迟注入**（某投稿延至次日窗出现）→ 断言 7 日累计去重后无重复无遗漏（沿 arxiv.md §6 七收割日回放 + D-018）；⑦ **主题过滤单测输入集**（混 econ/fin/非-econ 的 `primary_topic.field` stub）→ 期望过滤输出的确定性断言（AC-5.1a② 判据载体）。
- **模式 B fixture（仅 §11 案 A 落地时补）**：Cloudflare 挑战页（复用 auth-framework §11 challenge fixture，`cf-mitigated`/"Just a moment…" 脱敏）→ `ChallengeDetector` 判 CHALLENGE → `Challenged`→BLOCKED；`Delivery.cfm` token 语义经 browser 假 seam 单测（auth-framework §9/§10）。**案 B 下本组不需**。
- **T5 在线冒烟（元数据层，授权真实网络，`MAX_REAL_REQUESTS≤5`，零 SSRN 域）**：crossref 前缀单窗口枚举首页 1 + openalex source S4210172589 计数 1 + unpaywall SSRN DOI 1（证 landing-only）——**均非 SSRN 域**。SSRN 站点连通性**永不进 CI/冒烟**（环境 TLS 阻断 + 红线）。
- **模式 B 真实性验证 = 用户参与 runbook**（`tests/manual/`，换非-CF-阻断网络，records 留痕）——类 D-018 分层：离线 seam/challenge 单测先行 PASS，真实浏览器取回 defer 至可验证环境（§11 案 B）。

## 8. 验收 AC-5 草案（controller 裁决点 #5：按新现实分层改写；写在本文档内，不改 acceptance-criteria.md）

> development-plan 原 DoD：「按 FEN 子网增量拉取 SSRN 近 7 天新工作论文清单并按配额下载」。acceptance-criteria 现 AC-5.1：「按 FEN 子网枚举近 7 天清单成功率 ≥95%；全程限速 ≤1 req/5s（FetchLog 审计）；遇 Cloudflare 挑战正确 BLOCKED」。**按主路径改聚合优先 + 全文降 opt-in 的新现实，分层改写如下（草案，提请 controller 定夺是否回落 AC 本表）**。

| 草案 ID | 层 | 场景 | 通过判据 | 验收形态 |
|---|---|---|---|---|
| **AC-5.1a** | 元数据（**CI 可判**） | crossref 前缀近 7 天 created 窗增量枚举 | ① T4 回放 7 收割日（含重叠窗口 + created ~1 日延迟注入）→ abstract_id 清单**无重复无遗漏**（沿 D-018 分层，机制正确性）；② econ/fin 主题过滤 = **确定性过滤逻辑单测**（固定 fixture 输入 → 期望过滤输出精确断言，CI 稳定；**废止**原"一致率≥95% vs OpenAlex field 基准"——评审证实过滤信号本取自 OpenAlex field、自比恒 100% 为空判）；③ **全程零 SSRN 接触**（obslog 无 `*.ssrn.com` 请求）；限速审计经 obslog jsonl（元数据层无 FetchLog） | 离线 T4 + 单次在线冒烟（D-018） |
| **AC-5.1b** | 全文（**opt-in + 环境依赖，非 CI**） | 模式 B 单篇浏览器取回 | 遇 Cloudflare 挑战**正确 BLOCKED(challenge)+冷却 24h**（离线 challenge fixture 可判）；真实取回落盘 = 用户参与 runbook（换非阻断网络）；限速 ≤1 req/5s（仅模式 B 触 `*.ssrn.com` 时，FetchLog 审计） | **案 B 下 defer Phase 6**（§11） |

- **「按 FEN 子网」修订注记**：精确子网枚举**无合规路径**（§3）→ 判据改「econ/fin 主题**确定性过滤逻辑单测**」（AC-5.1a②），与 development-plan 原 DoD 的"FEN 子网"字面差异如实公开（不静默弱化）。
- **「遇 Cloudflare 挑战正确 BLOCKED」保留但语境收窄**：仅模式 B；元数据层零 SSRN 接触故**永不触发挑战**——该判据在元数据层退化为"obslog 证零 SSRN 请求"。
- **关联**：AC-5.1a②（确定性过滤单测，CI）↔ AC-6.3（Phase 6 SSRN 无下推补偿：**人工浏览基准**一致率，runbook 层，异于同信号自比）/ AC-2.3 分层先例（D-018）；AC-5.1b↔AC-4.6（风控即停）。**AC-5.2/5.3/5.4（nber/TE-QE/路由）不属本 adapter**，由 Phase 5 同批 adapter 承接。

## 9. 风险与开放问题

### 9.1 DOI 覆盖缺口量化（实现期任务，controller 裁决点 #3）

- **问题**：crossref 1.41M DOI vs abstract_id 空间 ~7.17M；缺口成因 **① 无 DOI 投稿** / **② 稀疏跳号**混淆，不许假设 crossref 全覆盖。
- **零-SSRN-接触量化法**（关键约束：**不能**采样整数 abstract_id——多数整数本非存在投稿，混淆两成因；**不能**采样 SSRN 本体 census——Cloudflare 门）：**以 OpenAlex source S4210172589 作 census 代理**（1.63M works，含无 DOI 补录）→ 随机采样 N works → 测「带 DOI 且 crossref 可解析」比率。**首阶估计 = 1.41M / 1.63M ≈ 87%**（openalex-相对覆盖）。细化：N≈1000（95%±3% CI），经 openalex `filter=primary_location.source.id:S4210172589` + 分页随机偏移，credit 预算内（§5 熔断）。
- **判定阈值**：openalex-相对 DOI 覆盖 **≥90% → crossref 前缀枚举判"覆盖充分"，无候补**；**<90% → 评估候补路径**（下）。
- **候补路径评估条件（缺口过大时，阶梯）**：(a) OpenAlex 补枚举无-DOI works（但 openalex 已**收回 ENUMERATE**，aggregators §1，且信用计费——需重评能力面）；(b) RePEc/NBER 交叉（Phase 5 同批，econ WP 书目）；(c) 有限度 SSRN 浏览页 census——**触 Cloudflare，须专门 BLOCKED 处置**，红线下降级/可选。默认不启用。
- **固有天花板（如实标注）**：本法测「crossref 相对 openalex」覆盖，**非**「crossref 相对 SSRN 真实全库」——后者需 SSRN census（无合规路径）。OpenAlex 自身对 SSRN 的覆盖上界未知，是量化的天花板，记开放问题。

**census 实测记录 [LIVE 2026-07-24]**（P5-M1 在线执行，独立脚本 httpx，非 CI）：

- **方法**：`GET api.openalex.org/works`，`filter=primary_location.source.id:S4210172589` + `sample=1000&seed=42`（OpenAlex 原生随机采样，一举锁定 1000 条固定样本）+ `per-page=200&page=1..5`（5 页翻完整个样本）+ `select=id,doi`（精简载荷）+ `mailto=yhyfhgs@gmail.com`；UA `PaperCrawler/0.1.0 (personal research; mailto:yhyfhgs@gmail.com)`。**`sample`+分页组合验证有效**（未触发退化分支）：5 页全 200 OK、每页 `meta.count=1000` 与请求量吻合、1000 条 `id` 去重后仍为 1000（无重复、无缺漏）——`seed=42` 下确定性覆盖，可复现。
- **样本量**：N=1000（达标 §9.1 细化目标"N≈1000"）。
- **DOI 非空率**：869/1000 = **86.9%**（本法定义的 crossref DOI 存在率代理下界）。补充细分（非本判定指标，供参考）：869 条非空 DOI 中 5 条（0.58%）前缀非 `10.2139`（`10.5897`×2/`10.13140`×1/`10.5281`×2——OpenAlex source 收录了少量非-SSRN-DOI 记录，佐证 §4.2 `skipped_non_ssrn` 护栏设计的必要性）；严格 `10.2139` 前缀非空率 = 864/1000 = 86.4%，与主指标差异 0.5pp，不影响判定。
- **判定**（§9.1 阈值 90%）：**86.9% < 90% → 触发候补阶梯记录**（本次仅记录触发，按红线不执行候补路径评估/实现）。首阶粗估 87%（1.41M/1.63M 全量比）与本次随机采样实测 86.9% 高度吻合，交叉验证粗估合理。
- **候补路径触发记录**（§9.1 阶梯，按序列出、均未执行）：(a) OpenAlex 补枚举无-DOI works——该能力已收回 ENUMERATE（aggregators §1）+ 信用计费，需重评能力面；(b) RePEc/NBER 交叉核对（Phase 5 同批 adapter 书目）；(c) 有限度 SSRN 浏览页 census——触 Cloudflare 门，红线下降级/可选，默认不启用。**优先级与执行时点留待 controller / 后续任务卡定夺**，本次不评估、不实现，仅完成"触发"侧的忠实记录（按 §9.1 判据要求）。
- **请求台账**：本项共 7 请求（2 次前置连通性/`sample`+分页形态探测 + 5 次正式采样页 page=1..5），均 200 OK、零 429/5xx、`api.openalex.org` 单域、串行间隔 ≥1.2s。原始响应（5 页 JSON + 汇总统计）存 scratchpad，不入 git。
- **固有天花板复述**：本次实测口径同 §9.1 原定义——测「OpenAlex 收录 works 中 DOI 挂载率」，非「crossref 相对 SSRN 真实全库」；OpenAlex 自身对 SSRN 覆盖上界未知仍是开放问题，不因本次实测而消解。

### 9.2 其他风险与开放问题

- **开放问题**（勘察 §8 清单，标注触发层）：① 重取 SSRN `robots.txt` 全文（Disallow 面 + crawl-delay 复核）——**仅模式 B 前置**，元数据层不触；② SSRN RSS/sitemap 作 crossref 外新鲜度源——今日不可验证；③ DOI 覆盖率量化（§9.1）；④ FEN network→聚合过滤映射（§3 子网近似）；⑤ crossref `journal-article` vs `posted-content` 语义差异是否可利用；⑥ 换非-CF-阻断网络对 SSRN 挑战门真实复测（确认 2026-07-20 结论现状）——**模式 B 前置**。
- **风险**：crossref 计费/政策演变（aggregators §10 已备降级路径）；openalex 信用制（预算护栏）；**SSRN=Elsevier 风控随时收紧**——**元数据层零 SSRN 接触故天然免疫**，仅模式 B 受影响（canary 对模式 B 周检、连续 CHALLENGED 时 catalog 标降级）；crossref 前缀枚举腐化（canary 比对 healthcheck 固定 DOI title，沿 crossref 先例）。
- **healthcheck**：元数据层 = `GET api.crossref.org/works/10.2139/ssrn.4056799` 比对规整化 `title[0]`（固定已知存在 DOI，[LIVE] 200，真值 [PENDING] 实现期 UPDATE_GOLDEN 捕获）；模式 B = 无 session 时 `NotImplementedError`→canary SKIP（沿 auth_gated 先例）。

## 10. 裁决记录

### 10.1 D-029 决策草案（聚合主路径确立 + 模式 B 降级；修订 D-011 定位）——供 controller 追加为新 ADR，**本稿不改 decision-log.md 本身**（已正式化 → decision-log D-029，2026-07-24）

> 以下为草案文本，措辞对齐 ADR 格式，待 controller 采纳后落 decision-log。

```
## D-029 SSRN 定位修订：聚合元数据主路径确立 + 浏览器全文降 opt-in（修订 D-011 定位）
- 状态：proposed · 依据：research/site-survey/ssrn.md [LIVE 2026-07-24] R0a + design/adapters/ssrn.md
- 背景：D-011（2026-07-20）设想「eLibrary 浏览页 + RSS 枚举 + 浏览器下载」双模式、auth_level
  free_account_preferred。R0a 勘察（2026-07-24）实测颠覆三点：① SSRN 全库经 Crossref 前缀 10.2139
  （1.41M DOI）+ OpenAlex（1.63M）完整可读，枚举/元数据/增量 watch 聚合 API 即可闭环、零 SSRN 接触；
  ② 匿名 HTTP 直连 SSRN 不可行（2026-07-20 Cloudflare 挑战 + 2026-07-24 环境 TLS 阻断，双独立证据）；
  ③ 全文无第三方旁路（unpaywall 对 SSRN 仅 landing）。
- 决策（修订 D-011，收窄双模式定位，不 supersede）：
  1. 模式 A（聚合元数据）升主路径：Crossref 前缀 10.2139 枚举主干 + OpenAlex 交叉核对/补摘要；
     auth_level=none；SSRN 站点本体零请求。
  2. 模式 B（浏览器全文）降 opt-in 低配额：唯一全文路径但穿 Cloudflare 门，按最严红线 opt-in/
     用户发起单篇、非批量非默认；实现 defer 评估（ssrn.md §11，controller 终裁案 B）。
  3. 元数据与全文能力解耦（D-005 同款）：元数据能力不依赖 SSRN 站点连通性。
  4. venue 建模：单一 ssrn venue（前缀全库）+ econ/fin 主题近似过滤，非 per-FEN 独立 venue
     （聚合源无子网过滤维度，对照 arxiv 差异，ssrn.md §3）。
- 影响：ssrn.md 实现级详设据此；AC-5.1 分层改写（元数据 CI 可判 / 全文 opt-in，ssrn.md §8）；
  development-plan Phase 5 DoD「按 FEN 子网…下载」相应收窄为「近 7 天新 WP 元数据 + econ/fin 近似过滤」。
```

### 10.2 本稿设计裁决点小结（供双评审 / controller）

| # | 裁决点 | 建议案 | 依据 |
|---|---|---|---|
| 1 | capabilities 集合（Phase 5） | `{DISCOVER, ENUMERATE, RESOLVE(landing-only)}`；`FETCH` 随 §11 终裁 | §4.1；controller 预裁决 #1/#2 |
| 2 | venue 建模 | 单一 `ssrn` venue + econ/fin 主题近似过滤（非 per-FEN venue） | §3；对照 arxiv category-venue 差异 |
| 3 | 枚举接缝 | **扩展 `CrossrefAdapter` 通用 prefix 模式**（enum-key: `issn` XOR `prefix`；date-field: `published`\|`created`，ssrn 走 prefix+created）——nber/ssrn 共用实现卡，规范出处 [nber.md §3.1](nber.md)；ssrn 只写消费侧契约 + 后处理层（abstract_id / `skipped_non_ssrn` / 增补 `(ssrn)` identifier） | §4.2；**controller 终裁 2026-07-24**（`parse.py:114` 硬绑 `published`、`to_paper_stub` 仅产 `(doi,)`，"零改"不成立；N-1=YES 并轨 nber） |
| 4 | 全文能力 | 元数据层 landing-only；全文 defer（§11 案 B） | §4.4；勘察 §5 无旁路 |
| 5 | AC-5 分层 | AC-5.1a（元数据 CI）/ AC-5.1b（全文 opt-in，defer） | §8；controller 预裁决 #5 |
| 6 | 覆盖率量化 | OpenAlex census 代理采样法 + 90% 阈值 + 缺口候补阶梯 | §9.1；controller 预裁决 #3 |

### 10.3 修订记录

| # | 日期 | 修订 | 依据 |
|---|---|---|---|
| 1 | 2026-07-20 | 初稿（D-011 双模式 survey 级，status review，owner fable5） | econ-fin-preprints.md [LIVE] 2026-07-20 |
| 2 | 2026-07-24 | **重写至实现级**（status draft，owner D1）：模式 A 升主路径（crossref 前缀枚举 + openalex enrich，零 SSRN 接触）/ 模式 B 降 opt-in；单 venue + 主题近似过滤 venue 建模；capabilities 集合论证；AC-5 分层草案；DOI 覆盖率量化任务；browser fetch 两案评估。**旧稿浏览器枚举路线作废** | R0a [LIVE 2026-07-24] + controller 预裁决 |
| 3 | 2026-07-24 | W0 双评审（A/B 独立实例，2026-07-24）Approve-with-fixes → 修订轮闭合 → controller approved | controller W0 收口 |
| 4 | 2026-07-24 | **§4.3 DISCOVER 改纯生成零网络年桶**（controller 发现①仲裁令，T4 实现随卡联动）：T1 在线实测真实 Crossref `facet=created:*` 返 **HTTP 400**（`created` 非合法 facet，活体哨兵 XFAIL），原「1 请求 created facet 产年桶」**不可实现** → 纯本地生成 1990..今年（clock 注入上界，`paper_count_claimed=None`，规模锚移交 M1 census）；`enumerate` 的 `from/until-created-date` **filter** 不受影响。§4.1 DISCOVER 行「桶计数」联动改 `None`；联动 nber.md §3.1 facet 限定注记 | T1 [LIVE 2026-07-24] 冒烟实证 + controller 发现①仲裁 |

## 11. 横切件专章：browser fetch 通道两案评估（评审后 controller 终裁）

**三处共需**：ssrn 模式 B（全文）/ aea 全文域（pubs Cloudflare）/ wiley deferred 页面兜底（wiley.md §3.2）。故本通道宜作**横切件**统一设计，非 SSRN 单独 bolt-on。

### 11.1 案 A：Phase 5 落地最小件（单 DOI 手动触发 `grab --browser`）

- **形态**：`crawler grab --ssrn <id> --browser`（或 `grab --doi <ssrn DOI> --browser`）——**单篇、用户显式发起**，非批量、非 watch 默认。
- **复用面（Phase 4 基建已在）**：`auth/browser.py`（惰性 Playwright，persistent context，storage_state 导出，A-M7 一次性 profile 目录 `try/finally` 清理，auth-framework §10）+ `ChallengeDetector`（challenge.py，§11 特征库）+ 预算护栏（日配额 §8.3、challenge 冷却 24h §8.4）+ `[auth-browser]` extra（已声明，§10）。
- **模块边界 / 新增面**：① `ssrn.capabilities` 追加 `FETCH`；② `resolve_assets` 追加 volatile `Delivery.cfm` 计划（`url_strategy=render_page`、标易失、**resolve/fetch 必须同浏览器上下文同批**）；③ CLI `grab` 追加 `--browser` flag；④ pipeline fetch 识别 browser-plan → 派 `auth/browser.py` 同 context 点击下载（`expect_download`）→ `%PDF` 校验落盘。**净新增 ≈ 一 fetch 分支 + 一 resolve 计划类型 + 一 CLI flag**（无新子系统）。
- **测试策略（离线 mock 层）**：browser.py **假 seam** 单测（注入预置 storage_state + mock download，auth-framework §9/§10 先例）；`ChallengeDetector` challenge fixture → `Challenged`→BLOCKED（离线可判）；resolve/fetch 同批约束 + token 易失单测。真实浏览器取回 = `PC_BROWSER_TESTS` 手动门 + runbook（**不进 CI**）。
- **工作量估计**：**中等**——基建已在 Phase 4，增量 = ssrn FETCH 分支 + volatile 计划 + CLI flag + 离线 seam 单测 ≈ 2–3 张 T-卡；但**在线验收在本环境不可行**（见 §11.3）。

### 11.2 案 B：deferred 至 Phase 6，SSRN 本 Phase 纯聚合元数据

- SSRN Phase 5 = `{DISCOVER, ENUMERATE, RESOLVE(landing-only)}`；全文经 pipeline **unpaywall OA-fallback 既有管线**（§4.4）。**命中率按勘察低预期如实标注**：SSRN 的 unpaywall 为 landing-only（`url_for_pdf=None`）⇒ **PDF 命中 ≈ 0**（元数据 + landing 链接为主，少数 econ WP 经 Phase 5 同批 repec/nber OA 副本替代）。
- browser fetch 横切件在 **Phase 6** 与 aea pubs CF / wiley deferred 页面兜底**一并设计**（三消费方共用一次横切件，非逐 adapter 重复）。

### 11.3 关键评估维度

- **本机环境对 CF 前置域 TLS 层阻断（R0a [LIVE] 实测 curl/httpx）——浏览器上下文**同样被阻断 [推断]**（R0a 未实测 Playwright）**：本机强制走代理 `127.0.0.1:6152`（fake-IP DNS），对**所有 Cloudflare 前置域**在 TLS 握手 reset（curl/httpx 实测）。Playwright 浏览器上下文的网络出口 = **同一本机代理** ⇒ [推断] 同样被 reset ⇒ **案 A 在线验收（真实 `Delivery.cfm` 取回）在本环境大概率不可行——happy path 亦无法验一次**。
- **离线可验证边界**：案 A 逻辑（challenge 判定 / BLOCKED / 同批约束 / 预算护栏）可经假 seam + fixture **离线全覆盖**；但「真穿 Cloudflare 取回 PDF」**永不可离线验**，且红线下遇挑战即 BLOCKED（不自动过）⇒ **即便非阻断环境**，诚实验收 = 用户已 CF-cleared 的浏览器 session 下取回，本质**用户参与 runbook、非 CI**。
- **D-011 承诺与 R4 缓解兑现度**：案 A 兑现「设计 + 最小实现」；案 B 兑现「设计」（本 §11 + auth-framework §9/§10 基建已在），defer「实现」至可验证环境 + 横切件统一。两案的 R4 缓解（SSRN 无 API→浏览器自动化 + 严限速）**设计层等价兑现**，差异仅在「是否本 Phase 落实现代码」。

### 11.4 推荐与理由（controller 终裁）

**推荐：案 B（defer 至 Phase 6 横切件）。（controller 已正式采纳案 B；本 §11 保留为 Phase 6 横切件设计种子。）**

1. **环境 TLS 阻断 CF 前置域（curl/httpx [LIVE]；浏览器上下文 [推断] 同源本机代理）⇒ 案 A 在线验收本环境大概率不可行**——shipping 无法验一次的代码，违项目「勘察先行 / 可验证」纪律（Phase 2 REJECT 教训）。
2. D-011 修订（controller #1）已降模式 B 为 opt-in 低配额；**defer 实现至 Phase 6 让它与 aea/wiley 两消费方作一次横切件设计**，非 SSRN 单独 bolt-on（DRY + 一致 challenge/预算处置）。
3. Phase 5 SSRN 元数据价值（crossref spine）零 SSRN 接触、全 CI 可判——**defer 全文不丢价值**。
4. R4 缓解经「设计浏览器通道」（本 §11 + auth-framework 基建）兑现，「实现落地」待可验证环境 + 横切件 Phase。
5. 案 A 会引入**无法在线验**的 FETCH 面（volatile `Delivery.cfm` / browser context / opt-in flag / 预算护栏），与勘察先行纪律冲突。

**反方（公平呈现）**：案 A 增量成本适中（browser.py 基建已在 Phase 4）、离线 seam 可覆盖逻辑；若未来主力网络非 CF-阻断，案 A 可较快转在线。但**决定性因素 = 本环境在线验收不可行 + 横切件统一论据** → defer。**本 §11 即该横切件的设计种子**（Phase 6 直接承接）。

