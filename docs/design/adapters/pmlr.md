---
title: Adapter 设计 · PMLR
status: implemented
owner: fable5
updated: 2026-07-22
---

# Adapter · `pmlr`

> 2026-07-22 全文重写：原稿被独立评审退回（8 BLOCKER + 9 CONCERN），且 [LIVE] 勘察（21 请求实测，全项 LIVE）证伪原稿两处关键假设——PDF 单一同域托管、AISTATS 2007–2016 旧域缺口。本稿依据勘察实测（归档 [research/site-survey/pmlr.md](../../research/site-survey/pmlr.md)，[LIVE] 2026-07-22）逐项闭合。**验收走通用 DoD + D-019 锚点（★5 裁决：否决新增 AC-2.7，验收面执行期只减不增）**，详见 §6.5。

## 闭合声明（评审 8 BLOCKER + 9 CONCERN → 落点节）

| 编号 | 议题 | 闭合摘要 | 落点 |
|---|---|---|---|
| **B1** | Issue 幂等键字段分解未定义 | `volume` 存裸数字串、`number=None`、`year=int`、`label='v{vol}'`、`pub_date=None`、`paper_count_claimed=None`——逐字段定死 | §3 discover |
| **B2** | identifier 归一规则不完整/与站点不符 | `scheme='pmlr'`、`value=` 官方 bibkey 全串 `pmlr-v{N}-{slug}`（[LIVE] 实证），大小写原样保留、无归一变换 | §3 enumerate |
| **B3** | resolve 数据来源未定义 + PDF 单域假设被证伪 | **域无关设计**：enumerate 带内取 `citation_pdf_url` 存 `PaperStub.meta['pdf_url']` → resolve 纯读 meta 构造 AssetPlan（零网络、不按卷号推断域）；`domains` 声明双域 | §2 / §3 resolve |
| **B4** | AC 引用不存在的编号 + 未落实 D-019 | 改走**通用 DoD 口径**（★5 裁决否决新增编号）+ 建 D-019 锚点快照表 `dblp-icml-anchor.json`（v235=2610） | §6 |
| **B5** | 合法空态未与 parse 区分 | HTML>0 单请求信任；HTML 0 时抓 bib 消歧——bib 0＝合法空卷（非错误，count=0 正常完成）、bib>0＝parse（HTML 解析器失效） | §5 |
| **B6** | fixture 覆盖不全 | 扩为七件：卷 index HTML / 卷 bib / 解析 golden / parse 故障 / 404 / 合法空 / 单篇详情页（citation_* meta）——全 error_class 有落点 | §6 |
| **B7** | canary 弱于先例（1 样本纯计数） | 扩 3 跨会议/跨托管样本（含 ≥1 GitHub 新卷 + ≥1 自托管旧卷），比对规整化 title + pages 双字段；era 路由移出本 adapter canary | §6 |
| **B8** | 缺"已知冻结限制"承认块 | 追加与 arxiv/openreview 同批的三点承认（http_status/FetchLog/Retry-After） | §5 末 |
| **C1** | discover 与 track 归属歧义 | discover_timeline **恒零网络**（只读 volume_map）；新卷探测归 track 子系统（design/08 §4），非 discover 第二路径 | §3 discover |
| **C2** | 未显式声明无 SEARCH | 显式声明并给理由（冻结协议无 search()，先例 arxiv/openreview §1） | §1 |
| **C3** | 限速未表格化 | §4 改 `domain | 速率 | 依据` 双域表 | §4 |
| **C4** | 风险定性偏乐观 | 下调"最低档"——承认 2023→2024 托管迁移史；但 B3 域无关设计已中和该风险（自愈） | §7 |
| **C5** | AISTATS 旧卷误判为死链缺口 | [LIVE] 证伪：2007–2016 全在 PMLR 存活；jmlr.org 旧路径 404 但无依赖；reissue r0–r6 仅覆盖 pre-2007，不重叠 | §7（+§2） |
| **C6** | OpenReview 跨源信号未捕获 | enumerate 存 `PaperStub.meta['openreview']`（forum id），**不产 identifier**（arxiv/openreview R3 先例，Phase 3 建边） | §3 enumerate |
| **C7** | 未评估 GitHub bulk clone | 评估结论：在线卷页 1 请求已含全量，bulk-clone 作可选兜底不默认采用（净收益有限） | §7 |
| **C8** | robots 表述停留"实现期复核" | [LIVE] 实测结论直写：两域 robots.txt 均 404（无禁则）；无 cf-ray（无 Cloudflare）；无站点级 ToS | §4 |
| **C9** | UA/D-014 声明缺失 | 补 UA 句（D-014 格式；由 HttpClient 调用方注入，非 adapter 职责） | §4 |

---

## 1. 定位

- **family**: `open_access`（**完全开放获取**：无登录、无 API-key、无付费墙——auth 等级 `none`，弱于 openreview 的 free_account、SSRN 的 free_account_preferred）
- **服务 venue**（PMLR 时代，卷号区间 [LIVE] 实测）：
  - **ICML** 2013+（v28 起系统收录）
  - **AISTATS** 2007+（v2 起；2007–2016 全在 PMLR，见 §7 对 C5 的订正）
  - **COLT** 2011+（v19 起——**订正**旧稿"2013+"，[LIVE] 实测 v19/v23/v30 均在）
  - **UAI** 2020+（v124 起；此前 AUAI Press，多段 era）
  - **CoRL** 2017+（v78 起，最干净单一体系）
- **capabilities**: `DISCOVER | ENUMERATE | RESOLVE | FETCH`（四位）。
  **无 SEARCH**：冻结 `SourceAdapter` 协议（adapter.py §2.3）无 `search()` 方法、Phase 2 无消费方；卷级枚举 + 本地过滤（`Selector.filter_expr`）已满足需求。先例 arxiv.md §1 / openreview.md §1。
- **多段 era**：COLT（ACM→Springer→PMLR）、UAI（AUAI Press→PMLR）早年在其他平台——本 adapter **只服务 PMLR 时代**；`(venue, year)→adapter` 的 era 路由是 Registry/框架级职责（design/08 §2），不在本 adapter 内解析（B7/AC-8.1 边界，见 §6）。
- **元数据/全文分工**：本 adapter 同时承担二者（卷页给全部元数据 + 每篇 PDF 直链）；历史回填的外源交叉对账走 DBLP（D-005/D-012），见 §6 锚点表。

## 2. 站点勘察摘要

来源：[research/site-survey/pmlr.md](../../research/site-survey/pmlr.md)（[LIVE] 2026-07-22，21 请求实测，8 项全 LIVE）。要点：

| 事实 | 值 | 出处 |
|---|---|---|
| 整站托管 | GitHub Pages（`Server: GitHub.com`）+ Fastly CDN（`via: 1.1 varnish`）；**无 Cloudflare**（无 `cf-ray`） | [LIVE] |
| 全卷列表 | `proceedings.mlr.press/`（40KB 单页含全部 v2–v336 + 复刊 r0–r6）；锚点为**相对链接无前导斜杠**：`<a href="v235">Volume 235 Proceedings of ICML 2024</a>`（**非** `/v235/`——旧解析器假设 `/vN/` 会漏抓） | [LIVE] |
| 卷页 | `v{N}/`：静态 HTML，每篇一个 `<div class="paper">`（v235 计 **2610** 个），块内含 `[abs]`(→`v{N}/{slug}.html`) / `[Download PDF]`(→PDF 真实域) / `[OpenReview]`(→forum id) 三链；卷首 `[bib]` 指向**独立文件** `./assets/bib/bibliography.bib`（v235 约 5.2MB，非页内嵌） | [LIVE] |
| 单篇 abs 页 | `v{N}/{slug}.html`：含完整 Google Scholar `citation_*` meta（`citation_pdf_url` / `citation_title` / `citation_firstpage`/`citation_lastpage` / 每作者一行 / `citation_publication_date` / `citation_issn=2640-3498`）；内嵌 BibTeX entry key = `pmlr-v{N}-{slug}` | [LIVE] |
| **PDF 双域托管** | 旧卷自托管 `proceedings.mlr.press`（`Content-Type: application/pdf`）；**新卷迁至** `raw.githubusercontent.com/mlresearch/v{N}/main/assets/{slug}/{slug}.pdf`（`application/octet-stream`）。**切分按上传时间非卷号**：v202(ICML2023)、v229(CoRL2023) 仍自托管，v235(ICML2024) 才在 GitHub——**不可硬编码固定切分点** | [LIVE]（核心发现） |
| Content-Type 不可靠 | GitHub raw 返 `application/octet-stream`（非 pdf）+ `nosniff` → **必须 `%PDF` 魔数校验，勿用 Content-Type 判定** | [LIVE] |
| 不存在卷 | `v9999/` → HTTP **404** + GitHub Pages 通用 404 页（`content-length: 9379`，`<title>Page not found · GitHub Pages</title>`）；与旧式 PDF 路径 404、robots 404 同一张通用页——**判据靠 HTTP status，不靠 body** | [LIVE] |
| robots / ToS | 两域 `robots.txt` 均 **404**（不存在，无禁则）；无站点级 ToS/AUP（footer `spec.html` 是投稿方卷制作规范非爬虫 ToU；`feed.xml` 是 RSS）；仅 `Copyright © [year] by the author(s)` | [LIVE] |
| GitHub bulk | 一卷一 repo `github.com/mlresearch/v{N}`（默认分支 `gh-pages`）；`_config.yml`（卷级元数据）+ `_posts/YYYY-MM-DD-{slug}.md`（单篇 YAML front matter，含 `pdf`/`openreview` 字段）；全 repo≈6.8GB（含 assets PDF），仅元数据 sparse-checkout 数 MB | [LIVE] |
| 无挑战门 | 全程无 403/429/验证码/JS 墙；两域静态直取 | [LIVE] |

> **三条结构化元数据源互证**：卷级 `bibliography.bib` / 单篇 `citation_*` meta / GitHub `_posts` md——三者的 `pdf` 域一致，且**都自带 PDF 真实域**（无需按卷号猜测）。这是 §3 域无关设计（B3）的事实基础。

## 3. 各阶段实现方案

### 3.1 discover_timeline（零网络；闭合 B1 / C1）

**恒零网络**——只读 `venue.quirks.volume_map`（`dict[year:int → volume:int]`），逐条产出 IssueRef：

- **数据来源**：`quirks.volume_map`（venue YAML）。单平台 venue（ICML/CoRL）为顶层 quirks；多段 era venue（COLT/UAI）为 PMLR-era 切片（design/08 §2 `eras[].quirks.volume_map`），Registry 已按 era 把对应 quirks 交给本 adapter——adapter 只认它拿到的 `volume_map`，**不自解析 era 边界**（框架职责）。
- **`since` 语义**：`since` 为可选年份下界；给出时只产 `year >= int(since)` 的 Issue（默认 None＝volume_map 全区间）。零网络不变。
- **`--refresh` / 新卷探测归属（闭合 C1）**：discover_timeline **不含**任何"抓全卷列表页 diff 出新卷"的网络路径。新卷发现是 **track 子系统**职责（design/08 §4 "PMLR 新卷"探测器）：轮询 `proceedings.mlr.press/feed.xml`（结构化 RSS，优于 diff HTML 首页）或解析首页锚点 `Volume (\d+) Proceedings of (.+?) (\d{4})` → 产候选 → 人工 confirm（D-012）→ 写回 `volume_map`。discover 与 track 是两条独立路径，无第二网络路径挂在 discover 名下。

**IssueRef 字段分解（定死，闭合 B1）**——`upsert_issue` 幂等与 `--year`/`--volume` selector（design/05 §6）由此确定性成立：

| 字段 | 值 | 理由 |
|---|---|---|
| `venue_id` | `venue.id` | |
| `volume` | 裸数字串，如 `"235"`（**无前导 `v`**） | 与 `_config.volume:'235'`（[LIVE]）、catalog 数值列一致；URL 拼接 `f"v{volume}/"` 直接复用；`--volume 235` selector 命中此列 |
| `number` | 恒 `None` | PMLR 只有"卷"无"期" |
| `year` | `int`（volume_map 的 key） | `--year` selector 的生效字段 |
| `label` | `f"v{volume}"`，如 `"v235"` | PMLR 站点自身的卷标识（用户在站上所见），比"ICML 2024"更 disambiguating（后者与 venue+year 列冗余）；对齐 openreview `label='YYYY'` 的极简取向 |
| `pub_date` | `None` | discover 零网络无法取；卷级出版日（`_config.published`＝`2024-07-08` / abs 页 `citation_publication_date`）仅 enumerate 阶段可得，登记到 Issue 属**推迟的富化**，非 Phase 2 幂等所需 |
| `paper_count_claimed` | `None` | volume_map 无篇数；enumerate 阶段以实解析数回填（对照 arxiv"留空"处理） |

### 3.2 enumerate_issue（单请求卷级抓取；闭合 B2 / B3 / B5 / C6）

**主源 = 卷 index HTML（`v{N}/`，1 请求得全量）**；**辅源 = 卷 `bibliography.bib`（对账 + 降级兜底）**。选型理由见本节末。

**主源解析**（GET `https://proceedings.mlr.press/v{volume}/`，1 请求）：逐 `<div class="paper">` 提取——
- `title`（标题元素）
- `authors`（作者 span → `tuple[str,...]`）
- 页码（details 内 `PMLR {vol}:{first}-{last}` → firstpage/lastpage）
- `slug`：从 `[abs]` 相对 href `v{N}/{slug}.html` 取（**相对链接无前导斜杠，须以卷 base URL 解析**）
- `pdf_url`：从 `[Download PDF]` href 取——**带内 PDF 真实域**（v235 为 `raw.githubusercontent.com`，v202 为 `proceedings.mlr.press`），域无关（B3）
- `landing_url`：`https://proceedings.mlr.press/v{N}/{slug}.html`
- `openreview` id：从 `[OpenReview]` href `openreview.net/forum?id=<id>` 提取

**identifier（定死，闭合 B2）**：`identifiers = (("pmlr", f"pmlr-v{volume}-{slug}"),)`——
- 采用**官方 BibTeX entry key 全串** `pmlr-v{N}-{slug}`（[LIVE] 实证 `pmlr-v235-abad-rocamora24a`），即站点在"cite this paper"场景对外发布的规范 key；人工核对时可直接以 `value` 反查官网 bib，最大化跨源可核验性。
- `value` 含 `pmlr-` 前缀与 `scheme='pmlr'` 的冗余是**有意的**——`value` 精确复刻站点规范 cite key（可 grep bibliography.bib 直命中），优先于去冗余的简洁性。
- **大小写原样保留**：站点自生成小写 slug（多词姓保留连字符 `abad-rocamora`，后缀 a/b 消歧）——**不做 `lower()`/`upper()` 归一变换**（明确断言，非留白）。`(scheme, value)` 主键唯一性由此稳定，D-007 强合并锚点成立。
- slug 从 abs URL 尾段取（URL slug == bibkey 尾段，[LIVE] 一致）；bibkey 可由 `N + slug` 直接构造，**不依赖抓 bib 文件**。

**字段映射与 meta（闭合 C6）**：
```
PaperStub(
  title=…, identifiers=(("pmlr", "pmlr-v235-<slug>"),),
  year=issue.year, authors=(…,),
  meta=(
    ("pdf_url", <带内 Download PDF href>),     # B3：resolve 零网络读此
    ("landing_url", <abs html url>),
    ("openreview", <forum id, 如 AZWqXfM6z9>),  # C6：不产 identifier
  ),
)
```
- **OpenReview forum id 存 `meta['openreview']`、不产 identifier**——arxiv/openreview R3 裁决先例（防 Phase 2 意外跨源早合并；Phase 3 ingest 依 D-007 建 `preprint_of`/评审关联边）。高价值 D-007 信号。
- `abstract`：卷 index 不含（仅 abs 页有）→ 本期留 `None`；如需回填走 abs 页 `citation_*` meta（逐篇一请求，推迟）。

**paper_count_claimed 与空态/parse 区分（定死，闭合 B5）**：
- `paper_count_claimed` = 解析出的 `<div class="paper">` 数。
- **常态单请求**：`HTML div 数 > 0` 时**不抓 bib**——直接信任 HTML 全字段并产出（"单请求卷级抓取"，绝大多数届走此路）。
- **仅 0-div 时触发辅源对账**：`HTML div 数 == 0` 是唯一歧义态（合法空 vs HTML 解析器失效）——此时且仅此时 GET 卷 `bibliography.bib`（`{base}assets/bib/bibliography.bib`）计 BibTeX entry 数消歧：

| HTML div 数 | 触发 bib？ | bib 条目数 | 判定 |
|---|---|---|---|
| >0 | 否 | — | 正常，信任 HTML；单请求完成 |
| **0** | 是 | **0** | **合法空卷**（占位/未上传完）——`paper_count_claimed=0` **正常完成，非错误** |
| 0 | 是 | >0 | `parse`——HTML 解析器在非空卷上读出 0＝失效信号，canary 标红 |
| 0 | 是 | bib 请求失败（5xx/timeout） | 无法确证空态 → 交 HttpClient 映射（`transient`，重试）；不武断判空 |
| >0 | 否 | bib 语法坏 | 不影响（未抓 bib）；若走降级兜底（下）时 bib 坏 → `parse` |

  > 辅源 bib 仅在 0-div 歧义态（罕见）触发，故 enumerate 常态 = 1 请求、罕见 = 2 请求（§4"1–2 请求/届"）。bib 的另一职责是 HTML 结构劣化时的**降级结构化兜底**（当 canary 报 HTML 解析异常、实现期临时切 bib 主源），**不作常态字段主源**。

**主/辅选型理由（★）**：卷 index HTML 一请求即含 title/authors/pages/slug→identifier/pdf_url/openreview 全部所需字段，且直接给出权威篇数（div 计数）；bibkey 可由 `N+slug` 构造无需 bib。故 **HTML index 为主、bib 为 0-div 消歧 + 降级兜底**。备选（bib 为主、HTML 对账）net 收益相近，本稿取 HTML 主以最小化热路径请求量与解析脆弱性——**★ 主 agent 可复核此主/辅取向**。

### 3.3 resolve_assets（域无关，零网络；闭合 B3）

**纯读 `PaperStub.meta` 构造 AssetPlan，零额外网络、域自描述**：
- `meta['pdf_url']` → `AssetPlan(kind=PDF, url=<pdf_url 原样>, expected_type="application/pdf", url_strategy=DIRECT, auth_needed=NONE, version=None)`。
- **域无关**：`url` 取 meta 内带内值原样——无论 `proceedings.mlr.press` 还是 `raw.githubusercontent.com` 都透传，**绝不按卷号/年份推断域、绝不在 resolve 阶段重发请求**。这正是 B3 的解法：托管迁移（§7/C4）对本阶段透明。
- `landing_url` 存于 meta 供参考，不产可下载 AssetPlan（落地页 abs html 非下载目标）。
- **supplementary**：部分卷有 `-supp.pdf`；若 enumerate 从辅源（bib supp 字段 / `_posts` md）解析到 supp url 并入 meta，则产 `kind=SI` 同域 AssetPlan；无则产 0 个（正常非错误）。本期 SI 为条件产出（勘察未深探 supp 覆盖率，实现期按源字段判定）。
- 防御：PMLR 每篇必有 PDF；若 meta 缺 `pdf_url`（不应发生）→ 产 0 个 pdf plan（非错误，openreview note-no-pdf 先例）。

### 3.4 fetch_asset（闭合 B3 的 Content-Type 陷阱）

- `HttpClient.stream(plan.url)` 取流 → `io.write_stream`（冻结分工）。**`%PDF` 魔数权威校验在 pipeline**（types.py FetchIO 注释：校验/rename 归 pipeline）。
- **不依赖 Content-Type 判 PDF**：GitHub raw 返 `application/octet-stream`（§2）——若以 Content-Type 判定会误伤新卷。pipeline 的 `%PDF` 魔数校验正确覆盖此形态；非 PDF 内容（如异常 HTML）由魔数校验落 `integrity`。
- GitHub raw 的 `Content-Security-Policy`/`nosniff` 响应头针对浏览器渲染，对流式下载无影响。
- 两域均由本 adapter 的 `domains` 覆盖（限速/日志归属）。

### 3.5 healthcheck（匿名）

- GET `https://proceedings.mlr.press/`（全卷列表，40KB），断言 200 且含 `Proceedings of Machine Learning Research` 与 ≥1 条 `Volume \d+ Proceedings of` 锚点。匿名可用（无 auth）。此页亦是 track 新卷探测源（§3.1 / design/08 §4）。

## 4. 限速与礼貌（闭合 C3 / C8 / C9）

| domain | 速率 | 依据 |
|---|---|---|
| **proceedings.mlr.press**（主域，元数据 + 旧卷 PDF） | 1 req/2s，并发 1 | 无官方声明 → NFR-4 保守默认（≤1 req/2s/domain）；`robots.txt` 404（无禁则）[LIVE] |
| **raw.githubusercontent.com**（新卷 PDF） | 1 req/2s，并发 1 | GitHub 基础设施无文档化速率数字（Fastly CDN）；`robots.txt` 404 ≠ 无限流 → 同取保守默认 [LIVE/UNRESOLVED]：⚠ 实现期查 GitHub 官方 ToS/rate-limit 文档后按需下调并注明出处 |

- **卷级枚举天然低频**：一届卷页含全部条目，enumerate 常态 = 1 请求/届（HTML 主源），仅 0-div 歧义态 + 1 请求（bib 消歧）——非高频小请求。
- **UA（D-014，闭合 C9）**：`PaperCrawler/<ver> (personal research; mailto:<user>)`——诚实标身份用途，不伪装。功能上 UA 由 `HttpClient` 调用方（pipeline 从 config 组装 D-014 格式）统一注入，`http.py` 本模块不读 config、非 adapter 自身职责；此处记录以对齐样板格式完整性。`default_rate.source_note` 依 `types.RatePolicy` 强制注明上述出处。
- **robots / ToS（实测结论，闭合 C8）**：两域 `robots.txt` 均 **404（不存在）**[LIVE 2026-07-22]——无 robots 禁则。`proceedings.mlr.press` 响应头 `Server: GitHub.com`、Fastly（`via: varnish`）、**无 `cf-ray`**（证实无 Cloudflare）。**无站点级 ToS/AUP**（footer `spec.html` 是投稿方卷制作规范、非爬虫使用条款，本期不抓；`feed.xml` 是 RSS）。完全开放获取，无登录/API-key/付费墙——约束仅来自"礼貌限速 + 各论文版权（`© author(s)`）"。

## 5. 失败模式映射（闭合 B5 / B8）

| 站点现象 | error_class | 说明 |
|---|---|---|
| 卷号未在 `volume_map`（新一届未登记） | `config` | 纯本地判断，`raise CrawlerError(CONFIG)`，提示走 `track` 流程（D-012）；CONFIG 经 pipeline 特判转 BLOCKED |
| 卷页 404（HTTP status） | `gone` | HttpClient `404→GONE` 自动映射；**判据靠 HTTP status，不靠 body**（body 是 GitHub Pages 通用 404 页，非 PMLR 风格，§2） |
| 200 且 HTML 0 条，bib 对账亦 0 条 | —（**非错误**） | 合法空卷（占位/未上传完）：产 0 stub、`paper_count_claimed=0`、**正常完成**（§3.2 判据表；误归 parse 会使新卷/workshop 卷假故障） |
| HTML 0 条 但 bib >0 条（0-div 消歧触发） | `parse` | HTML 解析器在非空卷读出 0＝失效信号；canary 标红（§3.2） |
| bib 文件畸形 / BibTeX 语法错误 | `parse` | 仅在 bib 被触发时（0-div 消歧 / 降级兜底）相关；HTML>0 常态不抓 bib、不受影响 |
| 429 / 5xx / timeout / 连接错 | HttpClient 统一映射 | `rate_limited`/`transient`（两域同理；30rpm 自限下罕见）；503+Retry-After→`rate_limited` |

**已知冻结限制（本期承认，收紧随 Phase 4 走接口仲裁；闭合 B8）**：①`FetchResult` 无 `http_status` 字段，`fetch_log.http_status` 本期恒 NULL；②**metadata 阶段请求（本 adapter 即卷页 HTML / bibliography.bib 拉取）不入 FetchLog**——其限速审计证据为 obslog jsonl（HttpClient 每请求 debug 事件：domain / url 脱敏 / status / elapsed_ms），AC-4.4（日配额）与 AC-0.5（限速审计）的证据链依赖此认知；③`Retry-After` 仅被解析入 detail 观测，**不驱动重试调度**（pipeline 按 RETRY_TABLE 固定退避 2/8/30s）。

### 网络层需求（Phase 2 共享 `HttpClient`）

缓冲 GET→文本（卷 index HTML / bibliography.bib 解析输入）；流式 GET→`Iterator[bytes]`（`fetch_asset` 喂 `FetchIO.write_stream`）；3xx 跟随 + obslog 事件；状态码→ErrorClass 映射；UA 注入。**属 adapter 自身职责**：HTML `<div class="paper">` 解析、相对链接解析（无前导斜杠）、BibTeX 解析、bibkey 构造、volume_map 路由。**不归 adapter**：限速（pipeline `acquire_and_wait`）、`%PDF` 校验（pipeline）、落盘（FetchIO）。

## 6. Fixtures 与测试（闭合 B4 / B6 / B7）

### 6.1 T1 单元
- volume_map 路由（year→vol；缺年 → `config`；`since` 下界过滤）；
- **identifier 构造矩阵**：`pmlr-v{N}-{slug}` 由 `N+slug` 构造、大小写原样、多词姓连字符（`abad-rocamora24a`）、后缀消歧（a/b）；
- **相对链接解析**：无前导斜杠锚点（`href="v235"` / `href="v235/slug.html"`）以卷 base URL 正确解析；
- HTML `<div class="paper">` 解析（title/authors/pages/pdf_url/openreview 提取）；
- BibTeX 解析器（转义 / Unicode / entry 计数）；
- **空/parse 判别矩阵**（§3.2 表：HTML>0 单请求信任、HTML 0＋bib 0 空态、HTML 0＋bib>0 parse、HTML 0＋bib 失败 transient）；
- `pdf_url` 域无关透传（`proceedings.mlr.press` 与 `raw.githubusercontent.com` 两形态都原样进 AssetPlan，不被改写）。

### 6.2 T3 fixture（七件套，覆盖 §5 全部 error_class——test-plan §6 强制；难录形态合成并标注"合成 fixture"）
1. **卷 index HTML 正常页**（`v{N}/`，节选含数个 `<div class="paper">`，混 ≥1 GitHub 托管 + ≥1 自托管 pdf_url，保证双域端到端）——常态单请求主源；
2. **卷 `bibliography.bib` 正常文件**（真实卷节选）——供 BibTeX 解析器单测 + 0-div 消歧/降级兜底路径 fixture（非常态路径）；
3. **① 的期望解析 golden**（PaperStub 列表 + identifier + meta + count；HTML 主源单请求口径）；
4. **parse 故障页**：HTML index 0 条 + 配套 bib >0 条（HTML 结构劣化，0-div 消歧判 parse）→ `parse`（合成，标注）；
5. **404 卷页**：GitHub Pages 通用 404 页（`v9999/` 形态）→ `gone`；
6. **合法空卷**：HTML 0 条 + 配套 bib 0 条 → **非错误**、`count=0`（合成，标注 B5 判据）；
7. **单篇 abs 详情页**（`v{N}/{slug}.html`，含 `citation_*` meta + 内嵌 BibTeX key）——test-plan §2"三件套"的详情页；覆盖 bibkey 反查/identifier 端到端与 abstract 回填（推迟路径）的解析回归。

  > `config`（卷号未登记）是纯本地逻辑，无需网络 fixture。`transient`/`rate_limited`/`integrity` 由共享 `HttpClient` 统一映射，其触发路径在 http.py 自身测试覆盖；本 adapter 如需可复用合成的 5xx/429 快照（非本 adapter 独有语义）。

### 6.3 T4 集成
- MockTransport 全链路 `discover→enumerate→resolve`（→ fetch mock）；
- **双域 resolve 断言**：注入一个自托管卷 + 一个 GitHub 卷，断言 `AssetPlan.url` 域**等于带内 pdf_url**（证明域无关、非按卷号推断）；
- accepted 计数 / 空态 / parse 判别注入断言；
- 重跑幂等：`identifier(scheme='pmlr')` 主键天然去重（AC-1.3 不变式）。

### 6.4 canary（抗 flake，闭合 B7）
- **3 个跨会议/跨托管固定样本**，覆盖不同 volume_map 条目且**含 ≥1 个 2024+ GitHub 托管卷 + ≥1 个 2023- 自托管卷**（覆盖 §2 双托管形态）：
  1. `v235/abad-rocamora24a`（ICML 2024，**GitHub 托管**）——title="Revisiting Character-level Adversarial Attacks for Language Models"、pages 1–30（[LIVE] 已知答案）；
  2. 一个自托管旧卷（≤2023，如 `v202/aamand23a` ICML 2023，`application/pdf` 自托管）——title/pages 于实现期 UPDATE_GOLDEN 锁定；
  3. 一个异会议卷（如 AISTATS `v238`(2024) 或 CoRL `v229`(2023) 首条）——扩会议覆盖 + 佐证"切分非按年"（v229/2023 自托管 vs v235/2024 GitHub）。
- **比对口径**：规整化（空白折叠）后的 `title` + `pages`（firstpage-lastpage）**双字段**——非纯计数（避免勘误/撤稿 ±1 假阳性；纯计数会漏字段解析错的假阴性，先例 arxiv/openreview canary）。
- **era 路由移出本 adapter canary（闭合 B7 第 2 点）**：`(venue,year)→adapter` 的 COLT 三段 era 解析是框架/Registry 级（design/08 §2），在框架层测试验证；本 adapter 仅内自证"对 COLT 2011+ 的 `volume_map` 覆盖正确 + 字段解析正确"，不把 era 路由算进 `healthcheck()` 范围。

### 6.5 完整性验收：D-019 锚点快照 + 通用 DoD（闭合 B4；★5 裁决口径）

**背景**：逐条核对 `acceptance-criteria.md`，AC-2.1~2.6 **无一条**关于 pmlr/icml（AC-2.1/2.2=iclr、2.3=arxiv、2.4=cvf、2.5=acl、2.6=acm 已 deferred）；phase2-implementation-plan 排期表 pmlr 亦未挂 AC 编号。旧稿"AC-2 系（pull icml --year 2024）"引用不存在的编号（status-workflow review→approved 自查硬项"编号有效"不满足）。且未落实 D-019（2026-07-22 立项，**明确点名 pmlr**）的锚点快照模式。

**闭合（两步；第 1 步须配套编辑他文件，本稿以依赖标注、不越界改动）**：

**① 通用 DoD 判据**（★5 裁决：不新增 AC 编号，acceptance-criteria.md 不动；判据如下，验收记录按此执行）：
> `pull icml --year 2024 --limit 10` + `timeline icml`
> 判据（比照 AC-2.2 落盘 + AC-2.1 外源一致，经 D-019 锚点传递）：
> - `pull icml --year 2024 --limit 10`：落盘 10 文件，每个魔数=`%PDF` 且 >10KB（PDF 来自 `raw.githubusercontent.com`，B3 双域）；DB↔文件对账一致；
> - `timeline icml`：各年届列表 + 每届 `paper_count_claimed` 与锚点表 `dblp-icml-anchor.json` **全等**。

**② D-019 锚点快照表** `tests/fixtures/pmlr/dblp-icml-anchor.json`——逐年 ICML `{year, volume, paper_count_claimed, dblp_slug, pdf_host, note}`：

| year | volume | paper_count_claimed | dblp_slug | pdf_host | note |
|---|---|---|---|---|---|
| 2024 | 235 | **2610** | conf/icml/icml2024 | raw.githubusercontent.com | count 三重互证（div/Download PDF/去重 slug 各 2610，[LIVE]）；DBLP count API 勘察时 503 → 实现期重试核准 |
| 2023 | 202 | (实现期填) | conf/icml/icml2023 | proceedings.mlr.press | 自托管旧卷 |
| 2025 | 267 | (实现期填) | conf/icml/icml2025 | raw.githubusercontent.com | GitHub 托管 |
| … | … | … | conf/icml/icml{year} | (逐卷实测) | volume_map 全区间逐年补 |

- **生成程序（实现期）**：对每个 ICML 卷 enumerate（div 计数）取 `paper_count_claimed` + `pdf_host`（带内 pdf_url 域实测，逐卷——`pdf_host` 记录 LIVE 实测域，**不假设固定切分**：ICML 恰好 2023→2024 边界，但 CoRL v229/2023 自托管证明同年跨会议可不同）；**人工对照 DBLP `dblp.org/db/conf/icml/icml{year}.html` TOC 核准**——双源核对、UPDATE_GOLDEN 纪律、人工过目留痕 `testing/records/`。
- **验收判定** = `timeline icml` 输出与锚点表全等（届列表 + 计数 + host 元数据）；"与 DBLP ±0"经人工核准的锚点表传递。
- **模式外推**：AISTATS/COLT/UAI/CoRL 各自完整性 AC 定义时沿用同表模式（各建 `dblp-{venue}-anchor.json`）；本稿仅落 ICML（通用 DoD 主载体）。

### 6.6 AC-8.1 关系（era 路由，非本 adapter 独担）
- AC-8.1（`timeline colt` 三段 era 各路由到对应 adapter）是**框架级**验收——pmlr 的贡献仅是"提供正确的 PMLR-era COLT `volume_map` 覆盖（2011+/v19 起）、并作为 PMLR 段被正确路由到"。era 路由断言本身在 design/08 §2 框架层验证，不在 pmlr 的 `canary`/`healthcheck`（闭合 B7）。
- **验收关联**：通用 DoD（★5 裁决口径，本 adapter 主判据）；AC-8.1（PMLR-era COLT 覆盖贡献）；AC-1.3（幂等，全 adapter 生效）。测试类型定义见 [testing/test-plan.md](../../testing/test-plan.md)。

## 7. 风险与维护（闭合 C4 / C5 / C7）

### 7.1 托管基础设施迁移（C4 风险重定性）
- **下调旧稿"站点极稳定 / 腐化风险最低档"**：[LIVE] 实测存在 2023→2024 一次 PDF 托管迁移（旧卷自建 `proceedings.mlr.press` → 新卷 `raw.githubusercontent.com`），风险非"最低档"。比照 arxiv.md §7 记录 OAI 域名迁移的方式，记维护提示："托管基础设施可能随时间迁移（已有先例，2024 起新卷 GitHub 托管 PDF；边界按上传时间非卷号）"。
- **但 B3 域无关设计已中和该风险（自愈）**：resolve 读带内 `pdf_url`，从不硬编码/推断域——无论未来迁到何域，只要卷页 `[Download PDF]`/bib `pdf`/`_posts` `pdf` 字段仍带内给出真实域，本 adapter 无需改动即跟随。canary 双托管样本（§6.4）监控此不变量。

### 7.2 AISTATS 无缺口（C5 证伪订正）
- **[LIVE] 证伪旧稿/catalog 的"AISTATS 2007–2016 或在旧域 jmlr.org ⚠核验重定向"**：该区间**全部在 `proceedings.mlr.press` 存活**（v2/2007 … v9/2010 HEAD 200、v15/2011 HEAD 200 … v54/2017 均在首页卷列表且可达）；`www.jmlr.org/proceedings/papers/v9/` 确 404（AmazonS3/CloudFront，旧 W&CP 路径已死）但**无需依赖**。
- **复刊 Reissue r0–r6 仅覆盖 pre-2007**（r0=AISTATS1995 / r1=1997 / r2=1999 / r3=2001 / r4=2003 / r5=2005 / r6=UAI1998），与 2007–2016 **不重叠**（后者本就在 PMLR，无需复刊）。
- 2007–2016 间"缺"的年份（如 2008）是 **AISTATS 早期双年会**（2007→2009 隔年，2010 起转年会），**非死链**——volume_map 无该年属正常（`timeline --audit` 的"官方未举办"而非"数据缺失"，AC-8.3 口径）。
- 结论：**2007+ 无 `offline_only` 缺口**；design/08 §3 Wayback 兜底仅理论上对 pre-2007 未复刊者，而 reissue 已覆盖 → 本 adapter 无需 Wayback 路径。**catalog `cs-ai-conferences.md` 的"2007–2016 或在旧域"表述应订正**（配套编辑建议，非本稿改动）。

### 7.3 GitHub bulk-clone 评估（C7）
- **形态**：一卷一 repo `github.com/mlresearch/v{N}`（默认分支 `gh-pages`）；全元数据可经 sparse-checkout（`_config.yml`+`_posts`，排除 `assets/`）数 MB 获取，与 acl_anthology"GitHub bulk 优先"（AC-2.5）同构。
- **结论：不默认采用**——在线单张卷页（1 请求）即含全部条目（v235=2610）+ bib 链接，**在线卷级枚举本已极轻量（1–2 请求/届）**；全 repo≈6.8GB（含 assets PDF），Contents API 目录列举上限 1000 条（v235 有 2610，须走 git-trees API 或直接 clone）——净收益有限。bulk-clone 定位为**可选兜底**（全量回填 / HTML 结构劣化时），不列入 Phase 2 主路径。

### 7.4 常规维护
- **volume_map 年度追加**：track 探测器（design/08 §4）从 `feed.xml`（RSS，优于 diff HTML 首页）或首页锚点 `Volume N Proceedings of CONF YEAR`（注意相对链接无前导斜杠形态）产候选 → 人工 confirm（D-012）→ 写回各 venue YAML `quirks.volume_map`（多段 era venue 写对应 era 切片）。
- **Reissue r0–r6 本期不纳入**（pre-2007 AISTATS/UAI）：若后续纳入，IssueRef `label` 需区分 `r` 卷与 `v` 卷（如 `label='r5'`）、volume 存 `"r5"` 形态——届时补设计；当前明确排除（Phase 2 范围为 PMLR-era `v` 卷）。
- **[UNRESOLVED / 实现期]**：①`raw.githubusercontent.com` 限速/滥用阈值属 GitHub Fastly 基础设施、无文档化数字，查 GitHub 官方 ToS/rate-limit 后在 §4 下调并注明；②DBLP 锚点交叉核对（勘察时 count API 503）实现期重试补 `paper_count_claimed` 外源列。

### 附：venue YAML `quirks` 形态（实现期落地，示例）
```yaml
# venues/cs_ai/icml.yaml 片段（单平台 venue，顶层 volume_map）
quirks:
  volume_map: {2013: 28, 2014: 32, 2015: 37, 2016: 48, 2017: 70, 2018: 80,
               2019: 97, 2020: 119, 2021: 139, 2022: 162, 2023: 202,
               2024: 235, 2025: 267}
# venues/cs_ai/colt.yaml 片段（多段 era，volume_map 在 PMLR era 切片——design/08 §2）
eras:
  - {from: 2011, metadata_source: pmlr,
     quirks: {volume_map: {2011: 19, 2012: 23, 2013: 30, 2014: 35, 2015: 40,
                           2016: 49, 2017: 65, 2018: 75, 2019: 99, 2020: 125,
                           2021: 134, 2022: 178, 2023: 195, 2024: 247,
                           2025: 291, 2026: 336}}}
  - {from: 2001, to: 2010, metadata_source: springer}
  - {from: 1988, to: 2000, metadata_source: acm_dl}
```
> volume_map 各会议至 PMLR 起点的完整历史（ICML v28/2013、AISTATS v2/2007、COLT v19/2011、UAI v124/2020、CoRL v78/2017）见勘察 §1 LIVE 全表；catalog 现表只列 2021–2026，实现期据勘察补全（回应勘察"历史完整性"提示）。

## 裁决记录（主 agent，2026-07-22——正文 ★ 各点就此落定）

| ★ | 裁决 | 理由 |
|---|---|---|
| ★1 卷→会议映射 | **采纳 venue YAML `quirks.volume_map`**（零网络 discover；feed.xml 仅 track 探测源） | 映射是跨 5 venue 的 venue 属性数据，归属 YAML 而非 adapter 常量——与 openreview 内置表的差异根源在数据归属 |
| ★2 identifier | **采纳** scheme='pmlr'、value=官方 bibkey 全串 `pmlr-v{N}-{slug}`（原样无归一） | 可 grep 反查官网 bib 的可核验性；前缀冗余系有意 |
| ★3 enumerate 主/辅 | **采纳 HTML 卷 index 主源**（常态单请求）+ `bibliography.bib` 仅 0-div 歧义态消歧（空 vs parse） | 单请求最省；bib 消歧使"合法空"与"结构漂移"可区分 |
| ★4 IssueRef | **采纳** volume='235'（裸数字）/number=None/year=int/label='v235' | PMLR 卷号是真实领域概念（异于 cvf/aaai 的 None）——有卷则填卷 |
| ★5 AC-2.7 新增 | **否决**——pmlr 走**通用 DoD + D-019 锚点**（v235=2610），§6.5 的 AC 引用按此口径修正 | 验收面执行期只减不增（防范围蔓延，D-020 先例是减）；aaai ★E 同判 |
| 配套 | catalog 两处订正采纳（AISTATS 2007-2016 实测存活于 PMLR、COLT 起点 v19/2011+），随批量提交执行 | 勘误性修改，勘察 [LIVE] 依据 |
