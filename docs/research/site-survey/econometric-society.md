---
title: 勘察：Econometric Society 三刊（ECMA/TE/QE）——平台迁移实测与 adapter 路线
status: review
owner: fable5
updated: 2026-07-24
---

# 站点勘察 · Econometric Society 三刊（Econometrica / Theoretical Economics / Quantitative Economics）

> **验证元数据**
> - 勘察执行：Phase 5 勘察 agent **R0c（opus）**，2026-07-24。
> - UA 恒为 `PaperCrawler/0.1.0 (personal research; mailto:yhyfhgs@gmail.com)`（绝不伪装）；curl 逐条串行，同域 ≥2s、第三方 API（crossref/doi.org）≥1.5s。
> - **实测完成请求：26**（本源；两源合计预算 ≤40，明细见文末"请求台账"）；零 PDF 正文下载（仅 HEAD/Range 头探测）；零登录零凭证；**未调 Wiley TDM API**（无 token 且判定不需要）。
> - `[LIVE]` = 2026-07-24 本次直测；`[DOCS]` = 官方文档/既有勘察转引。
> - **前置勘察**（本文档增量升级其结论）：[econ-fin-preprints.md](econ-fin-preprints.md)、[publisher-platforms-econfin.md](publisher-platforms-econfin.md)（均 2026-07-20）；对照详设：[adapters/wiley.md](../../design/adapters/wiley.md)、[catalog/economics-journals.md](../../catalog/economics-journals.md)。

## 0. 结论速览（供详设/重写者先读）

**头条发现：Econometric Society 已把三刊统一迁移/收拢到自营平台 `www.econometricsociety.org`（Cloudflare 前置），推翻 2026-07-20/23 catalog 与 wiley.md 的托管假设。**

| 既有假设（catalog/wiley.md，07-20/23） | 本次 [LIVE 2026-07-24] 实测 |
|---|---|
| ECMA 由 Wiley 出版发行，走 `wiley` adapter（TDM API by DOI） | **仅对 Wiley 时代过刊成立**。ECMA 最新文章（2026）DOI 已解析到 **econometricsociety.org 自营页**（非 Wiley），且带 **CC BY 4.0**；2015 年 DOI 仍解析到 `doi.wiley.com`（stateless 403 CF）。**迁移是前向切换，过刊留在 Wiley、新刊自营。** |
| `wiley` 路由前缀含 `10.3982[ECMA]` | **危险的过宽路由**：`10.3982` 是 **Econometric Society 自持前缀**（crossref member 2359），**ECMA/TE/QE 三刊共用此前缀**，仅靠 DOI 后缀（`ECTA`/`TE`/`QE`）区分。裸前缀 `10.3982→wiley` 会把 TE/QE（econsoc）**误路由到 wiley**。 |
| TE/QE 走独立 `econsoc` adapter，自营开放平台 econtheory.org / qeconomics.org | 方向正确但站点形态已变：两刊是 **同一个多刊 OJS 实例**（`econtheory.org/ojs/index.php/{te,qe}`，OAI-PMH 均活）＋**合并前端 econometricsociety.org**；独立域 econtheory.org / qeconomics.org 现均 **301/302 跳转** 到 econometricsociety.org（**qeconomics.org TLS 证书已过期**）。 |
| 三刊枚举 | **crossref 按 ISSN 全解**（member 2359、prefix 10.3982）：ECMA 7307 / TE 735 / QE 617 DOIs；TE/QE 另有 OJS OAI-PMH（earliestDatestamp 2006）可作二级校验。 |

**一句话 adapter 路线**：三刊 **DISCOVER/ENUMERATE 全部 crossref-by-ISSN**（与全系统同构，零站点抓取）；**FETCH 分三支**——TE/QE + **当前 ECMA** → 新建/沿用 **`econsoc`** adapter（open_access，取 econometricsociety.org 匿名 OA PDF）；**Wiley 时代 ECMA 过刊** → 沿用既有 `wiley` adapter（TDM token，仅过刊 DOI 区间）；**pre-DOI 过刊** → JSTOR（tier T3）。

## 1. 三刊标识体系与 Crossref 覆盖（[LIVE] 全部 200）

| 刊 | id | ISSN（print/e） | DOI 前缀·后缀 | crossref member | publisher | total-dois | 最新样本 DOI |
|---|---|---|---|---|---|---|---|
| Econometrica | ecma | 0012-9682 / 1468-0262 | 10.3982 · `ECTA{n}` | 2359 | The Econometric Society | **7307** | `10.3982/ecta23709`（2026-03） |
| Theoretical Economics | te | 1933-6837 / 1555-7561 | 10.3982 · `TE{n}` | 2359 | The Econometric Society | **735** | `10.3982/te6021` |
| Quantitative Economics | qe | 1759-7323 / 1759-7331 | 10.3982 · `QE{n}` | 2359 | The Econometric Society | **617** | `10.3982/qe2297`（2026-01） |

- **`prefixes/10.3982` → `name: "The Econometric Society"`** [LIVE]：前缀为学会自持，非 Wiley。三刊 `publisher` 字段亦均为 "The Econometric Society"（即使 Wiley 时代 DOI 亦然——出版商元数据归学会）。
- **枚举结论**：三刊各有独立 ISSN，`metadata_source: crossref`（按 ISSN 枚举全史卷期）**完全可用、零站点访问**，与系统主干（aggregators.md §5.1）同构。ECMA 的 7307 含 pre-DOI/JSTOR 时代记录（见 §2）。
- **license（crossref [LIVE]）**：TE、QE 最新样本均 **CC BY-NC 4.0**（确认 OA）；**ECMA 最新样本 CC BY 4.0**（OA 信号，见 §3 [UNRESOLVED]）。

## 2. 平台迁移实测：Wiley / 自营 OJS → 合并至 econometricsociety.org

**方法**：对样本 DOI 走 `doi.org` HEAD `-L`（headers only，读实时重定向链）＋ crossref `resource.primary.URL`（登记落地）双证。

| 样本 | 年代 | 实时 doi.org 解析终点 [LIVE] | 判读 |
|---|---|---|---|
| ECMA `10.2307/1912227` | 1933 | `jstor.org/stable/1912227` | pre-DOI 过刊在 **JSTOR**（旧前缀 10.2307） |
| ECMA `10.3982/ECTA12058` | 2015 | `doi.wiley.com/10.3982/ECTA12058` → **403 Cloudflare**（stateless） | **Wiley 时代过刊**（登记 link 含 `api.wiley.com/onlinelibrary/tdm/v1/...` + `onlinelibrary.wiley.com/.../fullpdf`） |
| ECMA `10.3982/ECTA23709` | 2026 | `econometricsociety.org/doi/10.3982/ECTA23709` → `/publications/econometrica/2026/03/01/{slug}` → **200** | **当前自营**（CF 前置，无挑战） |
| QE `10.3982/QE2297` | 2026 | `econometricsociety.org/doi/10.3982/QE2297` → `/publications/quantitative-economics/2026/01/01/{slug}` → **200** | 当前自营（其 crossref link 仍留 `onlinelibrary.wiley.com/doi/pdf/...` = **陈旧遗留元数据**） |
| TE `10.3982/TE6021` | — | `econometricsociety.org/10.3982/TE6021` → **404** | TE 的 crossref 登记落地用了 **无 `/doi/` 前缀的坏 URL**；TE 真身在 OJS/econtheory（见 §4） |

- **切换形态 = 前向**：过刊（Wiley 时代 ~2010–202x、JSTOR 时代 pre-2010）**不迁移**、留在原平台；新刊落自营。**切换日历日 [UNRESOLVED]**（实现期用 crossref 按年枚举 + doi.org HEAD 抽样二分确定 DOI 区间分界，预算内可完成）。
- **合并落地 URL 形态（自营）**：`/doi/10.3982/{ECTA|TE|QE}{n}` → 302 → `/publications/{journal-slug}/{yyyy}/{mm}/{dd}/{title-slug}`（文章页），全 Cloudflare 前置、`cf-cache-status: DYNAMIC`，本次 stateless 200 无挑战。
- **独立域现状**：`econtheory.org/` 与 `qeconomics.org/` 根路径均跳转到 `econometricsociety.org/publications/{theoretical-economics|quantitative-economics}`；**`qeconomics.org` TLS 证书已过期**（curl(60)，`-k` 方可探）——adapter 绝不可依赖该域直连、且不得关校验绕过（本次 `-k` 仅勘察诊断）。

## 3. ECMA — `wiley` adapter 复用判断（本源最关键情报）

**判定：复用 `wiley` adapter 对 ECMA 是"部分且正在失效"（PARTIAL & DECLINING），不能作为 ECMA 的单一/主 FETCH 路线。**

- ✅ **仍有效（唯一有效面）**：**Wiley 时代 ECMA 过刊 DOI**（约 2010–切换点）——其 doi.org 仍解析到 `doi.wiley.com`，全文经 `api.wiley.com/onlinelibrary/tdm/v1/articles/{DOI}`（token 门控，wiley.md §3 既有设计）。本次 [LIVE] 2015 DOI 的 crossref link 明确含该 TDM 端点，佐证过刊仍在 Wiley entitlement 域。stateless 直连 `doi.wiley.com` **403 CF** → 按红线 **记 Wiley 域 BLOCKED、停手**，合规正道仍是 TDM token（无 token 则该面 skip，wiley.md 门控先例不变）。
- ❌ **已失效（当前+未来）**：**2026 起 ECMA 新刊在 econometricsociety.org 自营**，crossref 无 Wiley link（`link: []`），Wiley TDM 对新 DOI 大概率 `no_entitlement`。继续把新 ECMA 交给 wiley adapter 会**系统性漏取**。
- ❌ **路由缺陷（须修 wiley.md/catalog）**：`wiley.md §1` 把 `10.3982[ECMA]` 列为 wiley 的 enumerate/resolve 前缀——**裸前缀 10.3982 覆盖 TE/QE（econsoc），会误路由**。正确键 = **venue（ISSN）+ DOI 后缀（`ECTA` vs `TE`/`QE`）+ 年代区间**，绝非裸前缀。

**给详设的处置建议**：
1. **catalog `ecma` 行**：`fulltext_source` 由单一 `wiley` 改为 **年代分段**——`wiley`（过刊，token）＋ `econsoc`（当前，OA/自营）；enumerate 仍 `crossref`（不变）。
2. **wiley.md §1/§2**：移除"10.3982[ECMA]"作为 wiley 前缀路由键的表述，改注"仅 Wiley 时代 ECMA 过刊 DOI 区间；新刊已迁 econometricsociety.org（见 econometric-society.md）"。
3. **[UNRESOLVED① 当前 ECMA 是否 journal-wide OA]**：最新文章 CC BY 4.0 + 自营 200 匿名落地是强 OA 信号，但**单篇 license 不足以断全刊**（Econometrica 历史为订阅制；学会自营后可能转 diamond/subscribe-to-open）。实现期确认（HEAD 一篇当前 ECMA galley PDF 即可判匿名可下否）——本次为尊重 econometricsociety.org 的 ClaudeBot 反 AI 信号（§5）**未加探**。若确 OA，则当前 ECMA 与 TE/QE **完全同构**，`econsoc` 一个 adapter 覆盖三刊当前面。

## 4. TE / QE — OJS OAI-PMH + 合并平台 OA 全文（[LIVE] 全绿）

- **平台栈 = 单一多刊 OJS 实例 + econometricsociety.org 前端**：
  - **OAI-PMH 均活**：`econtheory.org/ojs/index.php/te/oai?verb=Identify` → 200，`repositoryName: Theoretical Economics`、`repositoryIdentifier: ojs.theoretical.economics`、`earliestDatestamp: 2006-03-02`、granularity 秒级、gzip、`deletedRecord: no`；`.../index.php/qe/oai` → 200（同实例第二刊，adminEmail 空、名未改仍返标准响应）。
  - **ListRecords（oai_dc）**：TE `completeListSize: **656**`（vs crossref 735——差额约为编辑部记录/DOI 粒度差，实现期对账）；标准 `resumptionToken` 收割循环；单记录含 title / `dc:date` / `dc:source`（"Vol X, No Y (yyyy); pp"）/ `dc:rights`（Creative Commons）/ 文章页 URL。**是与 AAAI-OJS 同款的理想 ENUMERATE 通道。**
- **OA 全文实测（匿名门槛）**：
  - OJS 旧端点 `article/download/{id}/{galley}` **stateless 302 跳登录**（`/te/login`）——**遗留/弃用路径，非当前 OA 入口**。
  - 当前入口：`article/view/{id}` **302 跳合并前端** `econometricsociety.org/publications/{journal}/{yyyy}/{mm}/{dd}/{slug}`，页面标 **"Open Access"**，含 galley 链 `/publications/.../file/{file}.PDF`。
  - **该 galley PDF HEAD [LIVE]** → `HTTP/2 200`、`content-type: application/pdf`、`accept-ranges: bytes`、CF 无挑战 → **TE 匿名 OA 全文确认可下**（Range 支持，利于断点/校验）。QE 同平台，判定同构（本次未逐刊 HEAD QE PDF，[LIVE] 仅 TE；QE OA 由 crossref CC BY-NC + 同实例强推定）。
- **枚举面小结**：TE/QE 有 **两条独立可用枚举通道**——① crossref-by-ISSN（系统主干，推荐）② OJS OAI-PMH（2006 全史，二级校验/补摘要）。RSS/卷期浏览未专测（OJS 默认均有，非必需）。

## 5. robots / 合规（每域 [LIVE] 2026-07-24）

| 域 | robots 结论 | 对 PaperCrawler（UA 恒不含 ClaudeBot token）的约束 |
|---|---|---|
| `econometricsociety.org` | `*` 仅禁 `/admin/ /ckeditor/ /temp/`；**具名封禁 `ClaudeBot`、GPTBot、ChatGPT-User、Amazonbot、meta-external* 等 `Disallow: /`** | 字面上 PaperCrawler 落 `*` 组、`/doi/`+`/publications/`（OA 全文）**允许**；但学会明确反 AI 爬（与 CEPR 先例同构）＋ CF 前置 → **保守限速 + 诚实 UA + canary**，**降级信号交 controller 裁决**（见 §6）。 |
| `econtheory.org` | 仅 `dotbot` 全禁、`bingbot` crawl-delay 5；**无 `*` 组、无 AI 封禁** | 极宽松；OJS `/ojs/index.php/*/oai` 与文章路径均允许。 |
| `qeconomics.org` | **TLS 证书过期**，未取到 robots（curl 60）；根跳 econometricsociety.org | 不作直连源；一切经 crossref / econometricsociety.org。 |
| `onlinelibrary.wiley.com` | `*` 路径级（禁 /action /search /doi/mlt/ /doi/metrics/ /doi/am-pdf/ /author/ …，**不禁 /doi/pdf/**）；AI 仅禁 GPTBot/Google-Extended；`Crawl-delay: 1` | 与既有勘察一致；stateless CF 403（本次 doi.wiley.com 实测）→ **BLOCKED**，合规正道 = TDM token（wiley.md 不变）。 |

- 红线执行记录：Wiley 域遇 403 CF 即停手、未续探；econometricsociety.org 仅取 robots + 已由 doi.org 跳转自然抵达的 OA 落地/galley（未主动深爬）；零 PDF 正文下载；未调 TDM API。

## 6. 结论：三刊 adapter 路线预判

1. **`econsoc` adapter（open_access，新建/沿用）= 三刊当前面主承载**：
   - **family**：`open_access`；**capabilities**：`ENUMERATE`（可选，实走 crossref）`| RESOLVE | FETCH`。
   - **ENUMERATE**：一律 **crossref-by-ISSN**（三刊 member 2359）；TE/QE 可选 OJS OAI-PMH 二级校验。
   - **RESOLVE/FETCH**：`AssetPlan(url = econometricsociety.org/publications/{journal}/{y}/{m}/{d}/{slug}/file/{file}.PDF, url_strategy=direct/render_page, auth_needed=none)`；file-id 需从文章落地页解析（不可构造）→ resolve 阶段 GET 落地页抽 galley 链，fetch 阶段直取（匿名 200 + `application/pdf`）。
   - **礼貌**：CF 前置 + 反 AI robots → 串行、保守限速（建议 ≥5s/req 起步 + 抖动，对齐 ssrn 纪律）、canary 监 challenge；连续挑战即 catalog 降级（仅元数据 via crossref/RePEc）。
2. **`wiley` adapter（既有，token 门控）= 仅 Wiley 时代 ECMA 过刊**：保留，但路由收窄为"ECMA 且 DOI 落 Wiley 区间"，非裸 10.3982 前缀。无 token → 该面 skip（不阻塞 OA 面）。
3. **JSTOR（tier T3）= pre-DOI ECMA 过刊**：暂缓，同 catalog 既定。
4. **落库拆分**：`ecma` 单一 venue，`fulltext_source` 年代分段（econsoc 当前 / wiley 过刊 / jstor pre-DOI）；`te`、`qe` → `econsoc`，OA、优先级最高最省心（catalog "Phase 5 早做"判断成立且被本次强化）。
5. **须回改的既有件（交 controller/详设）**：catalog `ecma` 行 fulltext 分段；`wiley.md §1/§2` 去除裸 10.3982 路由键并加迁移注记；`economics-journals.md` TE/QE 平台注记从 "econsoc（自营 econtheory/qeconomics）" 更新为 "econsoc（OJS@econtheory.org/ojs + 合并前端 econometricsociety.org；qeconomics.org 证书过期停用）"。

**[UNRESOLVED] 汇总**：① 当前 ECMA 是否 journal-wide OA（§3，强信号未终证）；② Wiley→自营 的 DOI 切换日历日/区间分界（§2，实现期二分）；③ TE completeListSize 656 vs crossref 735 差额来源（§4，实现期对账）。三者均 [PENDING·实现期]，不阻塞路线判定。

## 附. 请求台账（26 次完成请求；[LIVE] 2026-07-24）

| # | 方法 | 目标 | 结果 |
|---|---|---|---|
| 1 | GET | econometricsociety.org/robots.txt | 200（ClaudeBot 等具名封禁；* 仅 admin） |
| 2 | GET | onlinelibrary.wiley.com/robots.txt | 200（路径级；CD1） |
| 3 | GET | econtheory.org/robots.txt | 200（仅禁 dotbot） |
| 4 | GET | qeconomics.org/robots.txt | **TLS 证书过期**（curl 60，未取到） |
| 5 | GET | crossref prefixes/10.3982 | 200 → owner=The Econometric Society |
| 6 | GET | crossref journals/0012-9682（ECMA meta） | 200（total 7307） |
| 7 | GET | crossref ECMA works rows=1 desc | 200 → `ecta23709`，落地 econometricsociety.org |
| 8 | GET | crossref journals/1933-6837（TE meta） | 200（total 735） |
| 9 | GET | crossref TE works rows=1 desc | 200 → `te6021`，CC BY-NC |
| 10 | GET | crossref journals/1759-7323（QE meta） | 200（total 617） |
| 11 | GET | crossref QE works rows=1 desc | 200 → `qe2297`，CC BY-NC，遗留 Wiley link |
| 12 | GET | crossref ECMA works rows=1 asc（最旧） | 200 → 1933，10.2307→JSTOR |
| 13 | GET | crossref ECMA works until-2015 | 200 → `ecta12058`，Wiley TDM link |
| 14 | HEAD-L | doi.org/10.3982/ECTA23709 | 200 → econometricsociety.org 自营 |
| 15 | HEAD-L | doi.org/10.3982/TE6021 | 404（econometricsociety.org 坏 URL） |
| 16 | HEAD-L | doi.org/10.3982/QE2297 | 200 → econometricsociety.org 自营 |
| 17 | HEAD-L | doi.org/10.3982/ECTA12058（2015） | **403 CF @ doi.wiley.com**（过刊留 Wiley） |
| 18 | GET-L | econtheory.org/ | 200 → 跳 econometricsociety.org（含 ojs/index.php/te 标记） |
| 19 | GET-L(-k) | qeconomics.org/ | 200 → 跳 econometricsociety.org（证书过期，-k 诊断） |
| 20 | GET | econtheory.org/ojs/index.php/te/oai?verb=Identify | 200（OAI-PMH，earliest 2006） |
| 21 | GET | econtheory.org/ojs/index.php/te/oai ListRecords | 200（completeListSize 656） |
| 22 | HEAD-L | te article/download/{id}/{galley}（旧端点） | 302 → 登录页（遗留路径） |
| 23 | GET | econtheory.org/ojs/index.php/qe/oai?verb=Identify | 200（QE 同实例 OAI 活） |
| 24 | GET-L | te article/view/{id}（cookie jar） | 200 → econometricsociety.org 落地，标 "Open Access" |
| 25 | HEAD-L | econometricsociety.org TE galley .PDF | **200 application/pdf, accept-ranges**（匿名 OA 确认） |

（另有 1 次拼错的 galley URL 被 curl 客户端拒绝、未发出，不计入。）
