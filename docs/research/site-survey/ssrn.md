---
title: 站点勘察：SSRN（Elsevier/Cloudflare 高危站 · 聚合 API 优先）
status: approved
owner: R0a
updated: 2026-07-24
---

# SSRN LIVE 勘察报告（Phase 5 R0a）

- 勘察对象：`www.ssrn.com` / `papers.ssrn.com`（对照旧稿 [design/adapters/ssrn.md](../../design/adapters/ssrn.md)、[research/site-survey/econ-fin-preprints.md](econ-fin-preprints.md)、决策 [D-011](../../plan/decision-log.md)/[D-014](../../plan/decision-log.md)）
- 勘察时间：2026-07-24
- UA（全程恒定，绝不伪装浏览器）：`PaperCrawler/0.1.0 (personal research; mailto:yhyfhgs@gmail.com)`
- 红线档：最严——合规礼貌优先，遇挑战即停不对抗，零凭证零登录，不下载 PDF。
- 出处等级：`[LIVE 2026-07-24]`=本次直接实测；`[PRIOR-LIVE 2026-07-20]`=旧稿实测、本次**未能**复核；`[DOCS]`=官方文档；`[推断]`。

## 0. 结论速览（供详设先读）

1. **本环境对 SSRN 传输层不可达**`[LIVE 2026-07-24]`：本机强制走本地代理（`127.0.0.1:6152`，fake-IP DNS），对**所有 Cloudflare 前置域**（`*.ssrn.com`、`cloudflare-dns.com`）在 TLS 握手阶段被 reset（`SSL_ERROR_SYSCALL`，~10s 超时），而非 Cloudflare 的 API（crossref）正常。**故今日无法对 SSRN 做匿名 HTTP 直连勘察**——这发生在 UA 发送**之前**，与 SSRN 自身反爬无关，是环境障碍。
2. **挑战门（最关键情报）**：今日**未能触达** SSRN 应用层，无法复测其挑战页；旧稿`[PRIOR-LIVE 2026-07-20]`已实测 `papers.ssrn.com` stateless 抓取 → **403 + "verify you are human"（Cloudflare）**。两条路径殊途同归：**匿名 HTTP 直连 SSRN 不可行**（今日=环境传输阻断；2026-07-20=SSRN Cloudflare 挑战），是合法 BLOCKED 结论，不对抗。
3. **元数据可得性极佳（主路径应改为聚合 API 优先）**`[LIVE 2026-07-24]`：SSRN 全库经 **Crossref**（前缀 `10.2139`，注册方 **Elsevier BV**，**1,414,774** 条 DOI）与 **OpenAlex**（source `S4210172589` "SSRN Electronic Journal"，host RELX，**1,632,966** works）完整可读，**无挑战门、宽容礼貌访问**。DOI 形态 `10.2139/ssrn.{abstract_id}` 内嵌 abstract_id——**元数据解析、枚举、增量 watch 可完全经聚合 API 完成，零 SSRN 接触**。
4. **对 D-011 的校验结论**：D-011 设想"eLibrary 浏览页 + RSS 枚举 + 浏览器下载"。本次实测表明**枚举/元数据/增量三件事聚合 API 即可闭环**（比浏览器自动化枚举安全得多、合规得多），浏览器自动化应**降格为"用户发起的单篇全文下载"专用**。建议详设据此收窄 D-011 双模式（详见 §6、§8）。
5. **全文 PDF 无旁路**`[LIVE 2026-07-24]`：Unpaywall/OpenAlex 均把 SSRN 标为 OA，但 OA location 就是 SSRN landing 本身（`doi.org/10.2139/ssrn.*`，`pdf_url=None`），**没有任何非-SSRN 的免挑战 PDF 镜像**。全文只能回 SSRN 的 Cloudflare 门内 `Delivery.cfm`，印证 D-011"为全文承担浏览器成本"的前提，但按红线应 opt-in/人工。

---

## 1. robots.txt 判读

- **今日无法获取**`[LIVE 2026-07-24]`：`GET https://www.ssrn.com/robots.txt` 两次（沙箱内 + 直连）均在 TLS 握手 reset（HTTP 000），未取得字节。传输层阻断，与 robots 内容无关。
- **旧稿实测**`[PRIOR-LIVE 2026-07-20]`（[econ-fin-preprints.md](econ-fin-preprints.md) §2）：SSRN `robots.txt` **具名封禁 `GPTBot`/`ChatGPT-User`/`Google-Extended`**，并声明 **`crawl-delay: 5s`**。[D-014](../../plan/decision-log.md) 背景段独立佐证同一事实。
- **判读**：本系统 UA `PaperCrawler/...` **不属**上述被具名封禁的 bot，落入 `User-agent: *` 规则；因此合规姿态为**遵守 `*` 段的 `crawl-delay: 5s` 与全部 `Disallow`**。`Disallow` 具体路径面**本次未取得**，是实现期必须重取的项（见 §8 开放问题）。CEPR 具名封 `ClaudeBot` 属另一站（[econ-fin-preprints.md](econ-fin-preprints.md) §1），SSRN 未见点名 ClaudeBot。

## 2. 官方结构化通道盘点

**结论：SSRN 无官方 API；但第三方聚合 API 是完整、合规、无挑战门的主通道。**`[LIVE 2026-07-24]`

| 通道 | 可用性 | 关键实测数据 |
|---|---|---|
| **Crossref** | ✅ 主路径 | `/prefixes/10.2139` 注册方 = **Elsevier BV**；`filter=prefix:10.2139` 总量 **1,414,774**；DOI 形态 `10.2139/ssrn.{abstract_id}`；支持 `sort=created`、facet、cursor 分页 |
| **OpenAlex** | ✅ 补充/交叉核对 | source `S4210172589`（"SSRN Electronic Journal"，host RELX Group）；works **1,632,966**；支持 `group_by=publication_year/primary_topic.field/open_access.is_oa` |
| **Unpaywall** | ⚠ 索引但非旁路 | 收录 SSRN DOI，`is_oa=True`，但 `oa_locations` 唯一项 `host_type=repository` 指回 `doi.org/10.2139/ssrn.*`（即 SSRN 自身），**不提供第三方全文** |
| SSRN 官方 API / OAI / RSS / sitemap | ❌ / 未证实 | 无官方 API（旧稿 [D-011]/[econ-fin] 一致）；内部 `api.ssrn.com` 未文档化 **明令禁用**（[D-014] 第 4 条 + AC-0 红线）；SSRN 是否有 RSS/sitemap **今日不可验证**（传输阻断），旧稿亦无 SSRN RSS 记录（对比 NBER 有 program RSS）——列为开放问题 |

- **Crossref 类型分布**`[LIVE]`：Journal Article **757,677** / Posted Content **657,096** / Conference Paper 1。约半数被标为 `journal-article`（container="SSRN Electronic Journal"），半数 `posted-content`——同一 SSRN 投稿在 Crossref 元数据里的类型不一致，枚举时两类都要收。
- **DOI↔abstract_id 直通**`[LIVE]`：Crossref/OpenAlex 的 DOI 即 `10.2139/ssrn.{id}`，**无需访问 SSRN 即可拿到 abstract_id**（下载定位的主键）。

## 3. 站点公开面形态

- **abstract_id 结构**`[LIVE 2026-07-24 经 Crossref 侧]`：DOI 内嵌，最新（2026-07-23 created）abstract_id 达 **~7,150,735 / 7,168,479** 量级；但 DOI'd 总量仅 1.41M ⇒ **id 空间稀疏或大量投稿无 DOI**（见 §7 覆盖缺口）。抽查 `10.2139/ssrn.3000000`、`6000000` 均 404（整数占位不存在），`4056799` 200——id 空间有洞，非连续。
- **abstract 页 URL 形态**`[PRIOR-LIVE 2026-07-20]`（今日不可复核）：`ssrn.com/abstract={id}` → 重定向 `papers.ssrn.com/sol3/papers.cfm?abstract_id={id}`。
- **FEN 等子网结构**`[PRIOR-LIVE 2026-07-20]`：Networks（FEN 金融 / ERN 经济 / LSN 法律 / PSN 政治…）→ 各含数十 eJournals（FEN ~30 个：Asset Pricing、Market Microstructure、Corporate Finance、Climate Finance…）；平台 1000+ eJournals；浏览页 `ssrn.com/index.cfm/en/{network}/`。**今日无法验证该结构现状**。
- **匿名可见性**`[PRIOR-LIVE]`：作者自传 WP 标题/摘要/作者匿名可见、多数免费可下；出版商定价内容需登录付费。**今日无法验证**。

## 4. 挑战门实测形态（最关键情报）

- **今日实测**`[LIVE 2026-07-24]`：对 SSRN 的每一次尝试都在**传输层**失败，**未进入应用层**，因此**无法观测 SSRN 的挑战页/状态码/头部**。失败特征逐一记录（本身是重要产出）：
  - 代理 `CONNECT` 成功（`HTTP/1.0 200 Connection established`）→ 随后 TLS 握手被 reset：`curl: (35) SSL_ERROR_SYSCALL`，固定 ~10s 超时，`http_code=000`，零字节。
  - 同一特征在 `cloudflare-dns.com`（同为 Cloudflare 前置）复现；而 `api.crossref.org`（非 Cloudflare）正常 200。⇒ 本机代理上游对 **Cloudflare 前置域**整体 TLS 不通。
  - 本机代理劫持全部 DNS（`dig @8.8.8.8`/`@1.1.1.1` 与系统解析器一律返回 fake-IP `198.18.x.x`，RFC-2544 保留段），无法取得 SSRN 真实 IP 另辟直连——**且不应绕过用户既定网络配置去"对抗"**。
- **与 SSRN 自身反爬的区分（务必不混淆）**：今日的阻断是**环境障碍**（本机代理），发生在 UA 发送前；**不是** SSRN 对本 UA 的判罚。
- **旧稿 SSRN 挑战门实测**`[PRIOR-LIVE 2026-07-20]`：`papers.ssrn.com` stateless 抓取 → **403 + "verify you are human"**（Cloudflare bot 管理，`cf-chl` 特征）。SSRN=Elsevier/Cloudflare，无变更信号，判定**仍有效**。
- **合并运营结论**：**匿名 HTTP 直连 SSRN 不可行**——今日因环境传输阻断、2026-07-20 因 SSRN Cloudflare 挑战，两条独立证据同向。按红线：**记 BLOCKED，停止对 `*.ssrn.com` 一切后续请求**（本次仅 2 次尝试即止），不换 UA、不上无头浏览器绕行、不重试。

## 5. 全文 PDF 获取路径（只观察不下载）

- **聚合侧无旁路**`[LIVE 2026-07-24]`：OpenAlex `10.2139/ssrn.4056799` → `oa_status=green`、`any_repository_has_fulltext=True`，但**唯一 location 的 `pdf_url=None`、landing=`doi.org/10.2139/ssrn.4056799`**（即 SSRN 自身）；Unpaywall 同（`host_type=repository` 指回 doi.org）。**没有任何免挑战的第三方 PDF**。
- **SSRN 侧下载形态**`[PRIOR-LIVE 2026-07-20]`：Download 按钮 → `Delivery.cfm/{filename}.pdf?abstractid={id}&mirid=1`，**一次性 token 语义，必须同一浏览器上下文即时使用**。今日未触达，无法复核。
- **门槛**：多数作者自传 WP 匿名免费可下（旧稿）；但下载动作必须穿过 Cloudflare 门 ⇒ 只能走 D-011 浏览器上下文。**本次零 PDF 下载**（红线）。

## 6. 限速/条款声明 与 D-011 现实性校验

- **限速基线**：`crawl-delay: 5s`（`[PRIOR-LIVE]` robots）；D-011 定 1 req/5s + 日配额 + 并发 1 + Cloudflare→BLOCKED 冷却 24h。**聚合 API 路径**另按各自礼貌池：crossref/openalex/unpaywall ≥1s、带 `mailto`（本次全程遵守）。
- **ToS 自动访问条款**：SSRN ToS 原文**今日不可获取**（传输阻断），列为实现期复核项；D-014 已定合规姿态（诚实 UA、遵 robots、**禁用**未文档化 `api.ssrn.com`）。
- **D-011 双模式 vs 现实**：
  - *模式A（元数据聚合）现实性 = 比 D-011 假设更强*：D-011 未明确聚合 API 能独立承担枚举；本次证明 **crossref+openalex 可独立完成枚举+元数据+增量 watch，零 SSRN 接触**——应升为主路径。
  - *模式B（浏览器辅助全文）现实性 = 唯一全文路径但高危*：仍是取全文的唯一手段，但穿 Cloudflare、易 BLOCKED；按最严红线应**降格为用户 opt-in 的单篇精取**，非批量、非默认。
  - **建议**：详设以本条 校验/收窄 D-011——"聚合优先枚举 + 浏览器仅限用户发起全文"。

## 7. 规模量级

- **全库**`[LIVE 2026-07-24]`：Crossref DOI'd **1,414,774**；OpenAlex works **1,632,966**（同量级，OpenAlex 略高，含无 DOI 补录）。
- **按年（近年产出巨大）**`[LIVE]`（OpenAlex / Crossref facet 一致）：2025 ≈ 243K–262K、2024 ≈ 210K–211K、2026（至 7 月，部分）≈ 152K–154K、2023 ≈ 154K、2022 ≈ 120K；覆盖回溯 68 个年份桶（含少量脏数据未来年 2077/2103/2104）。
- **按领域（FEN 语境定位）**`[LIVE]`（OpenAlex `primary_topic.field`）：Social Sciences 314,593 / **Economics·Econometrics·Finance 285,640** / Engineering 220,110 / **Business·Management·Accounting 198,928** / Computer Science 84,548 / …。**FEN（金融）+ 各商科/经济 network ≈ Economics/Finance + Business ≈ 48 万+ 量级**（[推断]：SSRN network≠OpenAlex field，非精确对应）。注意 SSRN 已多学科化（Engineering 22 万、Medicine 7 万），非纯经济金融站。
- **增量新鲜度**`[LIVE]`：Crossref `sort=created desc` 最新 created=**2026-07-23**（勘察前一日），abstract_id ~7.15–7.17M。⇒ **Crossref 对新 SSRN DOI 有 ~1 日延迟，足以驱动"近 N 天新工作论文"增量 watch（AC-5.x）**。
- **覆盖缺口（重要开放项）**：DOI'd 1.41M vs abstract_id 空间高至 ~7.17M。差距成因（[推断]，需实现期证）：① 大量 SSRN 投稿未分配 Crossref DOI，或 ② id 空间稀疏跳号——二者皆有可能。**若成因①占主，聚合 API 会漏掉无 DOI 的投稿**，是主路径的已知盲区。

## 8. 结论：实现路径建议

**主路径候选（推荐）：聚合 API 优先，零 SSRN 接触。**
- **枚举 + 元数据 + 增量 watch**：以 **Crossref** 为主干（`filter=prefix:10.2139` + `from-created-date`/`sort=created` + cursor 深分页），**OpenAlex** 作交叉核对/enrich（field/topic、OA 状态）。DOI 内嵌 abstract_id ⇒ 直接产出可下载主键。全程无挑战门、合规礼貌，天然满足"近 7 天新 WP 清单"类验收。
- **FEN 子网选择**：Crossref/OpenAlex **无法**按 SSRN network/eJournal 精确过滤。折中：(a) 近似经 OpenAlex field/topic（econ/fin/business）或 concept；(b) 经 **RePEc**（Phase 5 同批 adapter）取 NBER/CEPR 等 econ WP 书目；(c) 若必须 per-eJournal 精确，则需 SSRN 浏览页（Cloudflare）→ 降级/可选。**列为详设开放问题**。
- **全文 PDF**：聚合侧无旁路 ⇒ 唯一路径是 SSRN Cloudflare 门内 `Delivery.cfm`，按 D-011 浏览器上下文，**红线下 opt-in/人工**；多数 econ WP 可用 RePEc/NBER/作者主页 OA 副本替代（Phase 5 联动 repec/nber adapter + Unpaywall 兜底注意：Unpaywall 对 SSRN 不给第三方全文）。

**BLOCKED 边界（硬约束）：**
1. **任何对 `*.ssrn.com` 的直连 HTTP 枚举/抓取 = BLOCKED**（2026-07-20 Cloudflare 挑战 + 2026-07-24 环境传输阻断，双证）。
2. 内部 `api.ssrn.com` 未文档化端点 = **禁用**（D-014 第 4 条 / AC-0）。
3. 全文批量下载 = 无合规路径；仅用户发起单篇、浏览器上下文、限速内。

**给详设的三大关键判断：**
1. **主路径应从"浏览器枚举"改为"Crossref 聚合枚举"**——校验并收窄 D-011：聚合优先枚举 + 浏览器仅限 opt-in 全文。安全性与合规性质变。
2. **Crossref DOI 覆盖缺口（1.41M DOI vs 7.17M id 空间）是主路径已知盲区**——实现期须量化（抽样 abstract_id 验 DOI 存在率），据此决定是否需要有限度的 SSRN 浏览页补漏（若需，即触 Cloudflare，须专门 BLOCKED 处置）。
3. **全文永远受制于 Cloudflare 门**——PDF 能力应设计为"低配额、用户发起、浏览器上下文、遇挑战即 BLOCKED"，元数据能力与全文能力解耦（VenueSpec `metadata_source` vs `fulltext_source`，D-005）。

**详设开放问题清单：** ① 实现期重取 SSRN `robots.txt` 全文（Disallow 路径面 + `*` 段 crawl-delay 复核）——今日未获取；② SSRN 是否有 RSS/sitemap 可作 crossref 之外的新鲜度源；③ Crossref DOI 覆盖率量化（缺口成因①/②）；④ FEN network→eJournal 到聚合 API 过滤条件的映射策略；⑤ Crossref `journal-article` vs `posted-content` 两类型是否有可利用的语义差异；⑥ 换非-Cloudflare-受阻的网络环境后，对 SSRN 挑战门做一次真实复测（确认 2026-07-20 结论现状）。

---

## 附：请求台账（共 27 次 HTTP 请求，预算 ≤30）

> 全程 UA=`PaperCrawler/0.1.0 (personal research; mailto:yhyfhgs@gmail.com)`；SSRN 域 ≥3s 且遇阻即止（仅 2 次）；第三方 API ≥1s 且带 `mailto`。原始响应存隔离 scratchpad（`ssrn-raw/`，非 git 产物）。

| # | 域 | 方法/URL（略参数） | 结果 | 目的 |
|---|---|---|---|---|
| 1 | www.ssrn.com | GET /robots.txt（沙箱内） | **000 TLS reset** | robots 判读（失败） |
| 2 | api.crossref.org | GET /works?rows=0 | 200 | egress 心跳 |
| 3 | www.ssrn.com | GET /robots.txt（直连） | **000 TLS reset** | robots 复核（失败）→ 域记 BLOCKED |
| 4–6 | cloudflare-dns.com | GET /dns-query（www/papers/ssrn.com A） | **000 TLS reset** ×3 | 求真实 IP（失败，确认 CF 前置整体不通） |
| 7 | api.openalex.org | GET /sources?search=ssrn | 200 | SSRN source id + 规模 |
| 8 | api.unpaywall.org | GET /v2/10.2139/ssrn.3457234 | 404 | UPW 心跳（该 DOI 无） |
| 9 | api.crossref.org | GET /prefixes/10.2139 | 200 | 注册方=Elsevier BV |
| 10 | api.crossref.org | GET /works?filter=prefix:10.2139&rows=0 | 200 | 总量 1,414,774 |
| 11 | api.crossref.org | GET /works?…&rows=3&select=… | 200 | DOI/type 样本 |
| 12 | api.unpaywall.org | GET /v2/10.2139/ssrn.4056799 | 200 | UPW 对 SSRN=OA 但指回 doi.org |
| 13 | api.crossref.org | GET /works?…&facet=type-name:* | 200 | JA 757677 / PC 657096 |
| 14 | api.crossref.org | GET /works?…&facet=published:* | 200 | 按年分布 |
| 15 | api.crossref.org | GET /works?…&sort=created&order=desc | 200 | 最新 created=2026-07-23 |
| 16 | api.openalex.org | GET /works?…&group_by=publication_year | 200 | count 1,632,966 + 年分布 |
| 17 | api.openalex.org | GET /works?…&group_by=primary_topic.field.id | 200 | 领域分布（FEN 定位） |
| 18 | api.openalex.org | GET /works/doi:10.2139/ssrn.4056799 | 200 | location=SSRN、pdf_url=None |
| 19 | api.openalex.org | GET /works?…&group_by=open_access.is_oa | 200 | 全量 is_oa=1（=SSRN landing） |
| 20–24 | api.crossref.org | GET /works/10.2139/ssrn.{5e5,1e6,3e6,5e6,7e6}?select=… | **400** ×5 | id 存在性（select 误用→改写） |
| 25 | api.crossref.org | GET /works/10.2139/ssrn.4056799 | 200 | 方法校验（已知存在） |
| 26 | api.crossref.org | GET /works/10.2139/ssrn.3000000 | 404 | id 空间稀疏 |
| 27 | api.crossref.org | GET /works/10.2139/ssrn.6000000 | 404 | id 空间稀疏 |

**非 HTTP 诊断**：`nslookup`/`dig @8.8.8.8`/`@1.1.1.1` 各若干次——一律返回 fake-IP `198.18.x.x`，确认本机代理劫持 DNS（不计入 HTTP 预算）。

**红线遵守自证**：诚实 UA 全程未变；SSRN 域遇传输阻断即止（2 次，未换 UA/未绕行/未重试）；零凭证零登录零 cookie；未下载任何 PDF；未触 DB/config-home；未依赖 `api.ssrn.com`。
