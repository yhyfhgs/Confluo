---
title: Adapter 设计 · NBER Working Papers（实现级）
status: implemented
owner: D2
updated: 2026-07-26
---

# Adapter · `nber`(实现级详设)

> **controller 预裁决**（Phase 5 W0）：auth=`none`(open_access)；元数据主干=Crossref 前缀 `10.3386` 枚举
> （**elsevier_sd 同构**，D-005）+ OpenAlex 补摘要/topics；全文=`www.nber.org/system/files` 直链**仅 >18 月开放段**，
> <18 月软门=`no_entitlement` 终态（**不绕过、不利用 3 篇/年匿名配额**）→ 既有 OA-fallback 天然兜底。
> 勘察：[research/site-survey/nber.md](../../research/site-survey/nber.md)（[LIVE] 2026-07-24，approved，13 请求预算内）。
> 复用面：[crossref/adapter.py](../../../src/paper_crawler/adapters/crossref/adapter.py)（enumerate 主干，**需 prefix 模式扩展**）、
> [unpaywall/adapter.py](../../../src/paper_crawler/adapters/unpaywall/adapter.py)（OA-fallback）、[elsevier-sd.md](elsevier-sd.md)（结构模板）。
> 接缝：[auth-framework.md §8.1/§8.5](../auth-framework.md)（no_entitlement→OA-fallback、不计 failures）、
> [design/05 §4](../05-pipeline.md)（错误分类学）、[ratelimit.py](../../../src/paper_crawler/ratelimit.py)（**双域分桶 = §4 接缝设计点**）。
> 红线（AGENTS §6.3 / AC-0.2）：`/search/` 被 robots 禁 → 不作枚举路径；`back.nber.org` `Crawl-delay:10` 硬遵守；
> **<18 月软门绕过属调研伦理明令禁区（AC-5.2 批注），设计层永不实现绕过**。

## 1. 定位

- **family**：`open_access`（无认证；获取策略阶梯第 0 档=匿名直取 + OA-fallback）。
- **capabilities**：`RESOLVE | FETCH`——**enumerate 一律走 crossref**（D-005，与 elsevier_sd 同口径）；RSS 增量 watch
  以 `DISCOVER` 通道表达（§3.5，Phase 5 可选、Phase 6 订阅转主）。
- **domains**：`("www.nber.org", "www2.nber.org")`——全文 host + 低号老论文重定向 host（§4 说明为何 `back.nber.org`
  **不**进本 tuple）。apex `nber.org` 301→www。
- **AuthProvider**：无（`AuthLevel.NONE`）。不触 cryptography/keyring/Config-slot。
- **服务 venue**：单 venue `nber`（NBER Working Paper 系列；`w{n}` + 少量 `t{n}` 技术工作论文，均 type=report）。
- **`resolve_offline = True`**：resolve 为纯日期判定 + URL 构造（零网络，D-022 免限速闸）——**区别于 elsevier_sd**
  （后者 resolve 需网络查 entitlement；NBER 的"entitlement"=18 月窗，可离线由 `pub_date` 算）。

## 2. 站点勘察摘要（全 [LIVE] 2026-07-24）

- **元数据主干 = Crossref 前缀 `10.3386`**：`api.crossref.org/prefixes/10.3386/works` 一条 API 线枚举 **35,976** DOI
  （含 `w` 工作论文 + 少量 `t` 技术报告/章节），`type=report`，`title/authors(given/family 拆分)/date`；**无摘要、`subject:[]`
  无 JEL**。DOI 体系 `10.3386/w{n}` 双向解析命中（landing `citation_doi` + Crossref + OpenAlex）。
- **摘要/topics = OpenAlex 补充层**：OpenAlex `W4225331229` → `oa_status=green`、`abstract_inverted_index`、13 concepts/2 topics
  （受 D-005 信用预算约束）；备源=RSS `<description>`（完整摘要）。
- **全文 PDF（只 HEAD 探头，未下正文）**：`www.nber.org/system/files/working_papers/w{n}/w{n}.pdf`，>18 月开放论文匿名
  `HEAD` → `200 application/pdf`、`accept-ranges: bytes`、`server: nginx`、无跳登录/无挑战页。URL 由 landing `citation_pdf_url`
  给出、亦可确定性构造。**<18 月新论文**：机构 IP/订阅/配额软门（旧稿 [LIVE]，本次遵红线未探）→ 设计层 `no_entitlement`。
- **双主机双 robots 双限速**：`www.nber.org`（nginx，**无** `Crawl-delay`，无挑战）；`back.nber.org`（Akamai，RSS/sitemap
  住址，**`Crawl-delay: 10` 硬约束**）。`/papers/`、`/system/files/`、`/rss/` 均放行；`/search/` 被 Disallow（不作枚举）。
- **增量通道 = RSS**：`back.nber.org/rss/new.xml`（周更、39 item、含摘要、`guid=/papers/w{n}`）+ 19 个 program 分 feed
  `new{code}.xml`（`newcf` 实证可用）。`sitemap.txt` 陈旧（2025-10）作 bulk 种子须叠加补新。
- **规模**：w 系列现最大 ≈ **w35506**（2026-07），年增约 1200–1500；量级 ≈ 3.6 万。

## 3. 各阶段实现方案（字段级）

### 3.1 enumerate = Crossref **参数化枚举扩展**（★N-1 裁决=YES；本节 = 全谱规范出处）

**controller 终裁 N-1=YES**（W0 双评审对"扩 crossref vs adapter 自持"反案独立收敛到本方向）：`CrossrefAdapter` 升为**通用参数化
枚举源**，**本节为该扩展的规范出处**——消费方清单 = **nber（prefix + published）** 与 **ssrn（同一扩展、走 created，见 ssrn.md）**。
NBER **无 ISSN**，现 `discover_timeline`/`enumerate_issue` 硬走 `/journals/{issn}/works` 且 `_issn_of()` 缺 ISSN 即 `CONFIG` 早失败——
故作**最小、同构、两轴参数化扩展**（不新建独立 adapter）：

- **轴① enum-key（issn XOR prefix）**：venue `identifiers.issn`（期刊）**或** `identifiers.crossref_prefix`（前缀系列，nber=`"10.3386"`），
  二者互斥择一 → URL 基址 `/journals/{issn}/works` **XOR** `/prefixes/{prefix}/works`。
- **轴② date-field（published | created）**：**三处联动**——发现 facet + 枚举 filter + facet 解析键：
  - `published`（nber 默认，出版年轴）：facet `published:*` / filter `from-pub-date,until-pub-date` / 解析 `facets.published`。
  - `created`（ssrn 消费，登记年轴）：facet `created:*` / filter `from-created-date,until-created-date` / 解析 `facets.created`。
  - **⚠ 评审实证（参数化必须覆盖）**：`parse.parse_facet_years`（parse.py:114-125）**硬绑 `message.facets.published`**——须泛化为
    按 date-field 取 `facets.{field}`，否则 ssrn 的 `created` facet 解析恒空（评审据此判 MAJOR 联动）。
  - **⚠ [LIVE 2026-07-24] T1 实测限定（发现①仲裁令）**：**facet 仅 `published` 轴可用**——真实 Crossref 对
    `/prefixes/{prefix}/works?facet=created:*` 返 **HTTP 400 `facet-not-available`**（`created` 非合法 facet，活体哨兵
    `tests/online/test_crossref_prefix_smoke.py::test_prefix_created_facet_ssrn` XFAIL）。故 `created` 轴的 **facet 路径**
    （discover）不可实现：其消费方 ssrn 的 `discover` **不依赖 facet**、改**纯生成零网络年桶**（ssrn.md §4.3）。**`created` 轴的
    filter 路径（`from/until-created-date`，enumerate）不受此限**（filter≠facet，[LIVE] 已证有效）；nber 走 `published` 轴、
    facet 正常可用。上方两轴表的 `created` 行 facet 子项**仅离线单测/防御性泛化有效，对真实 Crossref 不可用**。
- **逐字复用面（两轴之外零改）**：`discover_timeline`→`parse.parse_facet_years`（泛化后）逐年 `IssueRef`（`paper_count_claimed`=该年计数）；
  `enumerate_issue`→`(key, year)` 日期窗 + `cursor=*` 深翻 → `parse.parse_works_page`（**cursor 契约、`(doi)` 去重、首页空判 parse
  原样复用**，adapter.py:181-223）。
- **实现形态建议**：`_issn_of`→`_enum_key_of(venue)->(mode,key)`（issn|prefix 互斥校验）+ 新 `_date_field_of(venue)`（默认 published）；
  URL builder 与 facet-parse 按两轴分派、cursor 循环零改动。扩展面 = URL 基址 + filter 前缀 + facet 键 + 键/字段取值（独立审查易验），风险低。
- **prefix 枚举含非 w 项**：`t{n}` 技术工作论文（同 NBER、type=report）**折入同 venue**（series 标识 = DOI 后缀 `w`/`t`）；
  少量 book chapter（type≠report）由 `parse.to_paper_stub` 的 type 落库、resolve 侧按 §3.3 谓词天然不产 NBER 全文计划。
- **abstract/topics 补充**：enumerate 产 stub 后由 **OpenAlex 补充层**（源=`openalex`，D-005 信用预算，D-007 merge ingest）
  回填 `abstract`（inverted_index 重建）+ topics；OpenAlex 不可达/超预算时降级用 RSS `<description>`（§3.5）。**JEL 缺口见 §9**。

### 3.2 resolve_assets(venue, paper, session)（RESOLVE，零网络）

输入 paper 的 `doi`（`10.3386/w{n}`）+ `pub_date`。**纯离线流程**（无网络，`resolve_offline=True`）：

1. 从 DOI 后缀取 series 号 `w{n}`/`t{n}`（正则 `^10\.3386/([wt]\d+)$`；不匹配→不产计划 + DEBUG 观测，非异常）。
2. **18 月开放窗判定**（离线，替代 elsevier 的网络 entitlement 预检）：`open := (today − pub_date) ≥ 18 个月`。
   - **开放**（>18 月）→ `AssetPlan(kind=PDF, url="https://www.nber.org/system/files/working_papers/{sid}/{sid}.pdf",
     url_strategy=DIRECT, auth_needed=NONE, expected_type="application/pdf")`（`sid`=w/t 号；确定性构造，免抓 landing）。
   - **软门**（<18 月）→ **不产 NBER 平台计划**、标 `no_entitlement`（`recent_gated`）→ pipeline 转 unpaywall OA-fallback
     （auth-framework §8.1；unpaywall 对 `10.3386` 覆盖按勘察 `oa_status=green` 预期良好）。**不利用配额、不构造软门 URL**。
   - **`pub_date` 缺失**（罕见）→ 保守**尝试开放路径**，交 §3.4 fetch 时 `%PDF` 守卫兜底（非"猜配额"）。
3. `t{n}` 全文 PDF 路径**未经勘察实证**（仅 `w{n}` HEAD 200）——见 §9 开放题 N-2：Phase 5 全文实现范围建议先限 `w`，
   `t` 全文路径核验后再放开（元数据 `t` 不受限，enumerate 照收）。

### 3.3 fetch_asset(plan, io, session)（FETCH，`www.nber.org` 匿名直取）

- 复用 pipeline 通用 direct-fetch（同 OA-fallback `_fetch_oa_direct` 家族）：共享 `HttpClient` GET plan.url → `io.write_stream`
  → **`%PDF` 魔数 + bytes>0 校验**（`validate_pdf_magic`）→ 落盘 `data/pdf/nber/{year}/{ulid}.pdf`。**无凭证、无专属 header**。
- **软门守卫（红线核心）**：若 >18 月判定错边界、命中软门返 **非 PDF**（HTML 登录/付费页）→ 魔数失败**不判 `integrity`**、
  改判 **`no_entitlement`**（预期内门控、非伪装泄漏）→ 交 OA-fallback；**绝不重试凑配额、不换 IP、不走软门**。
- 301 重定向：老论文 `www.nber.org/papers/w1`→`www2.nber.org`；PDF host 亦可能 301 至 www2——`www2.nber.org` 经 `domains[1]`
  别名共享 `www` 桶（§4），实际请求 host `acquire` 不 fail-fast。

### 3.4 RSS 增量 watch 通道（`DISCOVER`；Phase 5 可选设计，**Phase 6 T7 watch 主通道已落地**）

- `discover_timeline` 备用实现：GET `back.nber.org/rss/new.xml`（或 program `new{code}.xml`）→ 解析 `<item>`
  （`title`（含 `-- by <作者>`）/`description`（**完整摘要**）/`guid`（`/papers/w{n}` → 反解 DOI `10.3386/w{n}`））→ 近周新论文 stub。
- **定位**：RSS 是**新鲜度/watch** 通道（周更，补 Crossref 收录延迟窗），**非全量枚举**（全量恒走 §3.1 prefix）。摘要在此
  免费得（`<description>`），是 OpenAlex 超预算时的 abstract 降级源。**须在 `back.nber.org` 独立桶下发**（≥10s，§4）。
- Phase 5 交付以 AC-5.2（`pull nber --year` = prefix enumerate + fetch）为准；RSS watch 与订阅 DSL 联动的**完整 7 日增量**
  验收随 Phase 6（沿 D-018 arxiv AC-2.3 分层先例）——本详设给通道设计，不在 Phase 5 判 watch 完整性。
- **[落地 2026-07-26，Phase 6 T7，phase5-report §6 检查单 #3]**：program watch 通道实现于
  [`adapters/nber/rss.py`](../../../src/paper_crawler/adapters/nber/rss.py)——`PROGRAM_FEEDS`
  program 代码→feed URL 映射表（大小写归一入口 `normalize_program`）、`discover_incremental`
  （duck-typed 条目流，供 `subs/watch.py` T5 消费；非生成器外壳，调用即校验，见 rss.py
  docstring）、`to_paper_stub` 字段映射（RSS 字段薄，尽力而为）。id 集合差分不再由本模块
  自持占位逻辑——`subs/watermark.py`（T4，已落地 main）的 `IdSetDiff` 策略权威承接，
  `rss.ids_of(entries)` 只负责产出喂给该策略的保序去重 id 序列。backfill/全量枚举**不变**，
  仍恒走 §3.1 crossref prefix（本次落地零改动该主干、零改动 `NberAdapter`/`AdapterBase`
  既有公开签名）。

  **证据分级（2026-07-26 审查后在线补测闭合，5/5 全 [LIVE]）**：NBER 官方声称 19 个
  program，本项目文档（[catalog/preprint-platforms.md](../../catalog/preprint-platforms.md)
  §4）只对 5 个给出 `[VERIFIED]` 代码 + 语义（`AP`/`CF`/`EFG`/`IFM`/`ME`）——审查后 controller
  批准动用 phase6 计划 §3 机动预算余量 4 请求，对 `newap`/`newefg`/`newifm`/`newme` 四个原
  "命名模式外推"的 feed 逐条 `GET`（遵 `Crawl-delay:10`，间隔 ≥10s，UA 表明身份），全部
  `200 application/xml` 且解析出实际 item（4/5/2/2 条）；`newcf` 沿用 2026-07-24 原勘察
  [LIVE] 证据。**故 `PROGRAM_FEEDS` 现 5/5 全 [LIVE] 实证**，非"命名模式外推"。补测同时
  实锤两条此前未知的真实字段形态：① 真实 `<item>` **均无** `<pubDate>` 子元素（呼应
  site-survey §3 字段表"发表日期 RSS ❌"，而非本模块臆断）；② `<guid>` 真实形态带
  `#fromrss` 片段（`.../papers/w{n}#fromrss`），`rss.py` 复用的 `parse.doi_from_guid`
  对此零解析失败（13/13 真实条目）。官方 `PE` 代码因两义（Public/Political Economy）未
  核验被明确排除（未获在线核验该代码本身含义的预算），其余 ~14 个未点名代码同样排除而非
  按命名模式硬猜（猜错代码悄悄产出 404/空 feed，属"看似能跑实为静默失效"，违反响亮失败
  纪律）。**最终口径**：有据可查（含义+代码双确认）的 program 全部实证收录（5/19），
  其余 14 个官方 program 无码不猜；如需扩展先补勘察证据（含 `PE` 语义核验），不改此表。

  **`year` 字段与 `min_year` 预设的已知残余风险（P1，红线级）**：`to_paper_stub()` 的
  `year` 从 `pub_date` 派生（`_year_from_date`，对齐 `adapters/crossref/parse.py` 同名
  函数）——**必须填**，否则与 `subs/filter.py` 的 `min_year` 判据相撞（"已声明 `min_year`
  但 `year is None`"视为不通过）：T8 仅有的两个带 nber 的预设（`asset-pricing-wp` 的
  `min_year: 2022`、`corporate-finance` 的 `min_year: 2020`）一旦接线，`year` 恒 `None`
  会让 nber 恒零产出、且表现为"本周没有新论文"这种不会主动报错的静默失效。**但
  2026-07-26 在线补测实证：真实 RSS `<item>` 100% 不带 `<pubDate>`**——这意味着
  `to_paper_stub().year` 在生产环境里几乎恒为 `None`，`min_year` 判据在 nber 源上
  实际仍会系统性判不通过（这不是代码缺陷：没有日期就是没有日期，不能编造）。**残余
  风险与兜底方向留给 T5/T9**：T5 编排层可考虑为 nber 增补一个廉价的日期兜底信号（如
  由 series 号数值大小近似排序、或对已入库 crossref 记录的 `pub_date` 做二次关联），
  或在 daily-report 标注"日期缺失"提示；T9 AC-6 验收须把"nber pub_date 常缺失、
  `min_year` 预设可能系统性漏收"列为**已知限制**逐条验收，而非误判 nber watch 功能
  故障——本详设与 `rss.py` 均已如实标注，不视为本卡遗留 bug。

### 3.5 healthcheck(session)

- 全文 host 结构性探测：对**已知 >18 月开放** `w{n}`（如 `w30000`，[LIVE] 2026-07-24 = 200）发 `HEAD` →
  断言 `200 application/pdf`（不下正文）。真值 [PENDING online-smoke UPDATE_GOLDEN]：捕获实测 `content-type` 后转精确比对。
- 元数据侧健康由 crossref adapter 自有 canary 覆盖（不重复）。canary 须注册 `www.nber.org` 限速域（§4；沿 A-M1 补桶纪律）。

## 4. 限速与预算表（**双域分桶** = 接缝设计点）

**架构约束**：`route_for`（stages.py:160）对 `adapter.domains[1:]` 一律 `alias` 到 `domains[0]` **共享一桶**；`RateLimiter.
register/alias` 单调收紧取 min。故若把 `back.nber.org` 放进 `domains`，它会被别名到 `www` 桶、**错误共享 www 的宽松 ≥5s 预算**，
违反 `Crawl-delay:10`。**结论：`back.nber.org` 必须是独立桶，不进 `domains` tuple。**

| 域 | 默认策略 | 注册方式 | 出处 |
|---|---|---|---|
| `www.nber.org`（全文，`domains[0]`） | `RatePolicy(rpm=12, burst=1)`（=1 req/5s，无声明 crawl-delay 保守取 5s） | `route_for` 注册 `default_rate` | robots 无 Crawl-delay [LIVE 07-24] |
| `www2.nber.org`（老论文，`domains[1]`） | 同 `www` 桶（别名共享） | `route_for` `alias(www2→www)` | 低号 301 目标 [LIVE] |
| `back.nber.org`（RSS/sitemap） | `RatePolicy(rpm=6, burst=1)`（=1 req/10s，硬 Crawl-delay） | **独立注册**（watch 路径 on-demand，仿 OA-host 自动建桶 stages.py:577；**不 alias**） | robots `Crawl-delay: 10` [LIVE 07-24] |
| `api.crossref.org`（enumerate） | crossref adapter 自有 `default_rate`（rpm=300, burst=1） | crossref 侧注册 | crossref adapter.py |
| `api.openalex.org`（补充层） | openalex adapter 自有（信用预算熔断） | openalex 侧注册 | D-005/D-021 |

- `default_rate = RatePolicy(requests_per_minute=12, burst=1, source_note="www.nber.org 全文匿名直取；robots 无 Crawl-delay，
  保守 1 req/5s；back.nber.org(RSS) 独立桶 1 req/10s 遵 Crawl-delay:10 [LIVE 2026-07-24]")`。
- **日配额**：全文 fetch 走全局 `auth_daily_cap`/FetchLog 对账口径（"fetch 尝试篇次"，auth-framework §8.3）——NBER 无认证但
  纳入同一礼貌纪律。**★接缝 N-3**：`back.nber.org` 独立桶注册在冻结 `route_for` 里无 nber 专属钩子——建议 watch 路径落地时
  经"域出现即 `register` 保守桶"（OA-host 先例）实现，**不扩展 ratelimit.py 冻结件**（同 wiley §4 结论口径）。

## 5. 失败模式映射（对齐 HttpClient 冻结错误类 + `status_code`，design/05 §4）

| 现象 | status_code | error_class | 说明 |
|---|---|---|---|
| <18 月软门（返非 PDF / 登录页 / 付费面板） | 200/403 | **`no_entitlement`** | 预期内门控；**不计 failures**（auth-framework §8.5）；转 unpaywall OA-fallback（§8.1）；**不绕过** |
| PDF 404（DOI 太新/收录延迟 / `t` 路径异构） | 404 | `gone` | 延迟重试队列 24h（同 elsevier 口径）；`t` 系统性 404 → 触发 §9 N-2 复核 |
| PDF 魔数失败（>18 月却非 PDF） | — | `no_entitlement`（非 integrity） | 边界误判兜底：软门返 HTML → 归门控而非伪装泄漏（§3.3） |
| `back.nber.org` 429 / crawl-delay 触顶 | 429 | `rate_limited` | 读 `Retry-After` 退避；独立桶 1 req/10s 下罕见 |
| 挑战页（本次未遇；www=nginx/back=Akamai 均无） | 403 | `challenge` | 若未来出现 `cf-mitigated` 类 → `Challenged` → BLOCKED(challenge)+冷却 24h（auth-framework §8.4，沿 wiley 边界写法） |
| crossref/openalex 侧错误 | — | — | 归各源 adapter 既有映射（不在本 adapter 重复治理） |

## 6. venue 建模与 YAML 字段设计（**只给字段设计，YAML 属实现期交付**）

单 venue `nber`（沿既有 econ 惯例；建议置 `venues/econ/nber.yaml`）：

- `id: nber`；`kind: preprint_channel`（working paper=预印性质，与 arxiv 同族；type-level=report）；`field: [econ]`；`tier: T1`。
- `identifiers.crossref_prefix: "10.3386"`（**枚举键**，§3.1 新 scheme，替代期刊的 `issn`）；`openalex_source`: NBER source id
  （⚠ 实现期核验，补充层用）。**无 ISSN**（工作论文系列固有）——**现码已满足、零 lint 变更**（N-4 收口）：`registry.py` `_lint_issn`
  仅 `kind=journal` 必填 issn（`kind != "journal"` 即 `return []`），`preprint_channel` 天然豁免（**arxiv 31 个 preprint_channel
  venue 无 identifiers 块、全过 lint** 实证）；`identifiers` 为自由 dict（types.py:205 `dict[str, object]`），`crossref_prefix` 键结构合法。
- `metadata_source: crossref`（prefix 模式）；`fulltext_source: nber`；`auth.level: none`。
- `quirks`：`fulltext_open_after_months: 18`（软门窗，resolve 谓词参数）；`series_prefixes: [w, t]`（enumerate 收录范围）。
- `status: active`；`notes` 标注 JEL 缺口（§9）与 `preprint_of` 高频（NBER WP 常后发 AER/QJE，D-007）。

## 7. Fixtures 与测试（出处分级）

- **T-nber 单元**（零网络）：① DOI→series 号正则（`10.3386/w30000`→`w30000`；`t`/畸形/非 nber 分支）；② **18 月窗谓词**
  （假时钟：pub_date 跨 18 月边界 open/gated 断言——**红线核心用例**）；③ resolve 产 `AssetPlan` 字段断言（>18 月）
  + `no_entitlement` 分支（<18 月不产计划）；④ prefix URL builder（`/prefixes/10.3386/works` facet+cursor）；⑤ 软门非 PDF
  → `no_entitlement`（非 integrity）映射。
- **T-nber fixture**（脱敏，出处标级）：① Crossref `/prefixes/10.3386/works` facet 页 + cursor 页（[LIVE] 结构，脱敏截断）；
  ② landing `citation_*` meta（w30000，[LIVE]）；③ RSS `new.xml` 截断（[LIVE] 结构，1–2 item 含 `<description>`）；
  ④ OpenAlex inverted_index 样本（[LIVE] W4225331229）；⑤ **PDF HEAD 200 响应头**（w30000，[LIVE]，不含 body）。
  **不设 <18 月软门 fixture 之真实抓取**（红线未探）——软门分支用**合成非 PDF 响应**（标 `[SYNTH]` 来源）。
- **T-nber 在线冒烟**（`tests/online/test_nber_smoke.py`，`-m online`，`MAX_REAL_REQUESTS≤5`）：crossref prefix facet 1 +
  已知 >18 月 `w{n}` PDF HEAD 1（**不下正文**）+ landing 1 ≤3；**全程不触 <18 月论文**（红线）。
- **预算层次**：committed 冒烟 ≤5（本行）**≠** RSS 7 日 watch 完整验收（Phase 6 runbook，D-018 分层）。

## 8. 验收关联

- **AC-5.2（NBER >18 月开放）为核心载体**："`pull nber --year <当前−2>` 无凭证成功；<18 月按策略提示配额/订阅（不利用软门绕过）"：
  - `--year <当前−2>`（即 >18 月区）→ prefix enumerate 该年 + resolve 直链 + fetch PDF 魔数合格（离线 fixture 回放 PASS +
    在线冒烟 1 篇实证；沿 D-018 分层）。
  - <18 月抽样 → resolve 判 `no_entitlement`、报告提示订阅、**断言无软门请求发出**（obslog 审计：无 <18 月 PDF host 命中）。
- 通用 adapter DoD：resolve/fetch/enumerate 逻辑单测 + fixture 回放 + 限速双桶假时钟断言全 PASS 即离线 DoD PASS。
- OA-fallback 兜底关联 AC-4.3 口径（no_entitlement→OA direct 落盘）——NBER 无认证，为"无条件 OA-fallback"特例。

## 9. 风险与开放问题

- **N-2 `t{n}` 全文路径未证实**（勘察只 HEAD 过 `w{n}`）：Phase 5 全文实现建议先限 `w` 系列；`t` 元数据照收、全文路径核验后放开。
- **N-5 JEL 缺口 `[UNRESOLVED/DOC]`**：站内/Crossref/OpenAlex 三路均无 JEL；唯一已知源 RePEc `nbr:nberwo` ReDIF（旧稿 [DOC]，
  本次未验）——**RePEc enrich 挂 Phase 6，不在本详设实现**（controller 令）；`nber.yaml` notes 如实标注字段缺口。
- **18 月边界模糊**：NBER 分批开放，恰 ~18 月论文 open/gated 不确定 → §3.3 双守卫（离线日期预判 + fetch 魔数 `no_entitlement`
  兜底）诚实处置，不猜配额。
- **sitemap.txt 陈旧**（2025-10，~9 月）：仅作 bulk 种子须叠加 RSS/Crossref 补新；Phase 5 主路径不依赖 sitemap。
- **已裁决**：N-1=YES（crossref 升通用 prefix 枚举源，§3.1 规范出处）、N-4=现码满足零 lint 变更（§6）。**余开放**：N-2（`t{n}`
  全文路径，impl 核验）、N-3（back 独立桶注册钩子，§4 接缝）、N-5（JEL 经 RePEc，Phase 6）。
- **勘察事实无冲突**：本详设全部依据 [LIVE 2026-07-24] 勘察，未见与旧稿 `econ-fin-preprints.md` 断言矛盾（旧稿软门/RePEc 段
  均 `[DOC]` 承接、未反驳）。

## 10. 修订记录

| # | 日期 | 修订 | 依据 |
|---|---|---|---|
| 1 | 2026-07-24 | 初稿（实现级，status draft）：crossref prefix 模式扩展（enumerate 主干）+ 零网络 resolve（18 月离线窗谓词）+ www/back 双域分桶（back 独立桶避 alias 陷阱）+ 软门 `no_entitlement` 双守卫（红线不绕过）+ RSS watch 通道 + venue 字段设计 + AC-5.2 载体 + JEL/`t`-path 开放题 | [research/site-survey/nber.md](../../research/site-survey/nber.md) [LIVE 2026-07-24] + crossref/unpaywall adapter + auth-framework §8 + elsevier-sd.md 模板 |
| 2 | 2026-07-24 | **W0 双评审修订轮**（Approve-with-fixes）：§3.1 升格为**全谱参数化枚举扩展规范出处**（★N-1 裁决=YES：crossref 升通用 prefix 枚举源；两轴 enum-key〔issn XOR prefix〕+ date-field〔published\|created，评审实证 parse.py:114 硬绑 published 须泛化〕；消费方 nber〔published〕/ssrn〔created〕）；§6/§9 **N-4 收口**（现码零变更：registry `_lint_issn` 仅 journal 必填 issn、preprint_channel 豁免、identifiers 自由 dict——arxiv 31 venue 实证）+ JEL 缺口相碰号改 N-5 | controller W0 回派（双评审收敛）+ registry.py/types.py/parse.py 实证 |
| 3 | 2026-07-24 | W0 双评审（A/B 独立实例，2026-07-24）Approve-with-fixes → 修订轮闭合 → controller approved | controller W0 收口 |
| 4 | 2026-07-26 | **Phase 6 T7 落地**：§3.4 状态行同步"watch 主通道已落地"——`adapters/nber/rss.py` 新增（program feed 映射表 5/19 如实标注证据缺口 + `discover_incremental` + id 集合差分桥接）；backfill/crossref 主干零改动 | [phase6-implementation-plan.md](../../plan/phase6-implementation-plan.md) T7 + [catalog/preprint-platforms.md](../../catalog/preprint-platforms.md) §4 |
| 5 | 2026-07-26 | **T7 审查后 P1/P2 修订**：§3.4 证据分级升级为 5/5 全 [LIVE]（在线补测 `newap`/`newefg`/`newifm`/`newme` 四条 + 沿用 `newcf` 原勘察）；补 `year` 字段派生与 `min_year` 预设残余风险如实标注（P1 红线，真实 feed 100% 无 `<pubDate>` 实证）；id 集合差分改由 `subs/watermark.py`（T4，已落地）`IdSetDiff` 权威承接，`rss.py` 不再自持占位差分逻辑 | controller 审查回执（放行附条件）+ 2026-07-26 在线补测（4 请求，`Crawl-delay:10` 遵守）+ `subs/watermark.py` 类文档 |

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
