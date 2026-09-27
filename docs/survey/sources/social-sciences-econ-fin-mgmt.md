---
title: 来源调研：社科（经济/金融/商业/管理）出版商、工作论文与平台
status: draft
owner: opus5.5-survey
updated: 2026-09-26
---

# 来源调研：社科（经济/金融/商业/管理）出版商、工作论文与平台

> 本文是 v2 重设计"调研阶段"的来源主题之一，服务于 v2 的**来源名录（source registry）**与接口对接计划。
> v1 已深度覆盖经济金融（SSRN/NBER/AEA/Econometric Society/RePEc/Elsevier/Wiley/OUP 等），本文**不重复 v1 的勘察细节**，只做三件事：
> ① 复核 v1 结论在 2026-09-26 是否仍成立；② 扩展到商业与管理（AOM/SMS/INFORMS/SAGE/Emerald/T&F/Springer/HBS 等）与央行/国际组织工作论文；③ 给出统一列的来源名录、期刊名录体系、会议论文形态与 v2 接口对接优先级。
> 中国平台（CNKI 等）不在本主题（由聚合主题覆盖）；arXiv `econ.*`/`q-fin.*` 由预印本主题覆盖，本文只引用。

## 摘要（结论速览）

1. **SSRN 在 2026 年发生结构性变化**：Elsevier 于 2026-04-13 宣布 SSRN 回归"预印本核心使命"，Research Paper Series、Site Subscriptions、付费 Conference Proceedings、Data Feeds 等商业产品在 **2026-12-31 前关停**，并表示"希望未来"提供免费 Research Alert、更快上线、改进 Crossref 元数据、版本化、ORCID 集成与"预印本↔发表版"链接（[R2][R3][R4]，部分为搜索摘要级证据；另注：检索中常见的"SSRN 将迁至 Mendeley 技术平台"一语出自 2016-05-17 收购新闻稿，**不是** 2026 年的新计划 [R82]）。Crossref 前缀 `10.2139` 现有 **1,487,447** 个 DOI（2026-09-26 下午复测；上午为 1,487,290），新 DOI 当日可见，2026 年新建 226,338 条中 **91.2%** 带摘要（[R1][R78]，LIVE）。但 SSRN 使用条款禁止"任何形式的自动化查询"（[R5]，搜索摘要级）→ v2 对 SSRN **只走 Crossref 元数据，全文仅做"在 SSRN 打开"的外链**，应收窄 v1 D-029 的"浏览器 opt-in 取全文"模式。**核验补充**：SSRN 自 2026-07 起允许作者投稿时选择 CC BY / BY-NC / BY-NC-ND / CC0 或保留全部权利（[R91]，SNIPPET），Crossref 已同步登记 license——2026-07-20 后新建 76,405 条中 69,436 条带 license，其中 CC 类 13,101 条（CC BY 6,875）（[R1]，核验 LIVE 2026-09-26）→ `license` 字段须入库，但 CC 许可不解除 ToU 的自动化禁令。
2. **NBER 18 个月规则仍在**，网站用户（含匿名）每年 3 篇免费（[R8][R9]；核验：原文为 "All users of the NBER website are entitled to three complimentary downloads annually"）。新发现：NBER 官方提供**每周更新的元数据批量文件**（含 JEL、program、摘要、已发表信息、DOI）（[R10]），可补 v1 的"JEL 缺口"；但 `data.nber.org` 对非浏览器 UA 返回 403 "Prevent Bots from data downloads"（[R11]，LIVE）→ 需向 NBER 申请或由用户手动下载导入，**不得绕过**。
3. **Econometrica 是混合 OA 而非全刊 OA**：学会访问页把图书馆订阅指向 Wiley Online Library，1999 年起的文章经 WOL 提供（[R16]；核验修正：页面并未直接写"由 Wiley 出版"，Crossref `publisher` 字段为 The Econometric Society）；2025–2026 年 170 条 journal-article 中 79 条带 CC 许可，其中 CC BY 53、CC BY-NC 10、CC BY-NC-ND 16（[R17]，LIVE；核验修正：原文误作"均为 CC BY"）→ v1 未决项"当前 ECMA 是否全刊 OA"可结案为"否，按单篇 license 判定"。
4. **CEPR robots 已变**：2026-09-24 版 robots.txt 不再具名封禁 ClaudeBot/GPTBot，也无 Content-Signal（[R18]，LIVE），与 v1（07-20）记录不同；但 DP 全文仍是订阅/单篇购买，v2 维持"仅元数据"。
5. **商科核心平台高度集中**：UTD24 的 24 刊中 7 刊在 INFORMS（Atypon）、2 刊在 AOM（Atypon）、多刊在 Wiley/SAGE（Atypon）与 OUP/AAA/MISQ（Silverchair 系；AAA 2022-12、MISQ 2025-08 迁入 Silverchair 已由平台方公告确认，核验修正 [R83]）（[R65][R45][R70]）→ v2 以"平台族基类"（Atypon / Silverchair）承接大部分商科刊，元数据统一走 Crossref。
6. **出版社 RSS/eTOC 不应作为"最新论文"通道**：Atypon 族 robots 统一 `Disallow: /action` 与 `/rss`（eTOC 在 `/action/showFeed`），`rss.sciencedirect.com` 的 robots 为 `Disallow: /`（[R25][R29][R30][R33][R34]，LIVE）→ "最新论文"一律以 Crossref 增量（`from-created-date`/`from-index-date`）驱动；央行/国际组织例外（Fed/ECB/BIS RSS、World Bank 官方 API 均合规可用）。
7. **摘要覆盖率差异巨大**：Crossref current 摘要覆盖率 Elsevier（实测 19 刊）=0%、AOM（7 项）=0%、UChicago（5 刊）=0%，Wiley(RAND/IER)≈83–85%，SAGE(JOM)=99%（[R70]，LIVE）；OpenAlex 对 JFE/JET/AMJ/QF/ASQ 的 2026-09 新文同样无摘要（[R77]）→ v2 需 Crossref→OpenAlex→RePEc 的摘要补齐链，并记录摘要来源与版权属性（Crossref 明示"部分摘要可能受出版商/作者版权"，Springer 规定 API 摘要仅限个人使用）（[R26][R39]）。
8. **全文许可与多用户红线直接相关**：Springer Nature API 条款要求订阅内容 TDM 仅存于"机构内部服务器"、不得让第三方访问，且**不得用多账号/多 key 规避限额**（[R39]）；Elsevier 仅向订阅机构研究者开放非商业 TDM，API key 不得转让/披露给他人，联邦检索政策禁止持久存储 API 结果（[R22][R23][R81]）；T&F 按 STM 模型许可允许订阅者非商业 TDM（[R35]）→ v2 的 auth-gated 全文必须"每用户凭证、私有存储、零共享"，限额按平台级共享账本控制。
9. **Crossref 公共池已降速**：2026-09-26 实测无 mailto 请求返回 `x-rate-limit-limit: 1`、`x-concurrency-limit: 1`（[R28]），而官方文档（2025-10-16 版）写 public 5 / polite 10 / Plus 150（[R27]）→ v2 必须用 polite pool（带平台运营者联系邮箱）并按响应头动态限速。
10. **期刊名录体系可分两类**：可公开获取的（UTD24 在线列表、ABDC JQL 2025 公开 xlsx；其中建议只直接内置 UTD24，ABDC 内置再分发前需确认许可）与仅能"用户自带导入"的（Chartered ABS AJG 需登录且版权所有；FT50 原文在 FT 站点、本环境不可达。核验补充：FT 已于 2026-04-29 发布 2016 年以来首次修订版，移出 Human Relations、Journal of Business Ethics、Organization Studies，加入 Academy of Management Annals、American Sociological Review、Psychological Science，经图书馆指南交叉核验 [R86]）（[R65][R66][R67][R69]）。ABDC 站点另声明"其他可检索版本未经 ABDC 授权"（[R67]，核验补充）。
11. **（核验补充）2026 年经管出版格局变动**：Wiley 以 £337m 收购 Emerald（2026-06-02；Emerald 已于 2025-05 收购 now publishers，CFR 与 Foundations and Trends 系列随之归入）[R87]；MIT Sloan Management Review 2026-05 宣布停办，秋季刊后停印，冬季改出纯数字版 [R90]；OpenAlex 2026 年起改为 API key + 按量计费（注册 key 每日 $1 免费额度，无 key 仅约 $0.1/日）[R93] → 平台族归属、名录状态与补齐链预算都应纳入"政策漂移监测"（§3-14）。

## 1. 调研范围与方法

### 1.1 范围

| 维度 | 纳入 | 不纳入（去向） |
|---|---|---|
| 学科 | 经济学、金融学、会计、商业与管理（战略/组织/营销/IS/运营）；社会学、政治学简述 | 心理学（理科主题）；CS/AI（CS 主题） |
| 一级来源 | 出版商平台、学会期刊平台、工作论文系列（含央行/国际组织）、社科预印本、会议程序平台 | CNKI 等中国平台（聚合主题） |
| 二级来源 | 经管特有的仓库/聚合器（RePEc、EconStor、EconBiz、World Bank OKR、FRASER） | Crossref/OpenAlex/Unpaywall/CORE/S2 的通用细节（聚合主题；本文只记与本主题相关的实测） |
| 名录体系 | UTD24、FT50、AJG、ABDC、VHB、RePEc 排名 | 中国期刊分级目录 |

### 1.2 证据等级标注

| 标记 | 含义 |
|---|---|
| `[LIVE 2026-09-26]` | 本次直接请求并读取响应（curl/WebFetch/API），日期即核验日 |
| `[DOC 2026-09-26]` | 本次直接读取的官方文档页 |
| `[SNIPPET 2026-09-26]` | 目标页本环境不可直连，仅经搜索引擎结果摘要获得；属"部分核验"，须在可达网络复核 |
| `[v1 …]` | 沿用 v1 勘察（注明原日期），本次未复测 |
| `⚠ 未核验` / `⚠ 推断` | 未能核验，或依据间接特征推断 |

正文中 `[Rn]` 指 §5 参考来源编号（每条均附 URL 与访问日期）。

### 1.3 过程记录（可复现）

**执行日期**：2026-09-26（全部请求在同一日完成）。

**请求纪律**：UA 恒为 `PaperCrawler-survey/0.2 (v2 source survey; personal research)`（诚实标识，不伪装浏览器，不携带任何个人邮箱）；同域请求串行、间隔 ≥2s（遵守 robots 中更严的 Crawl-delay）；Crossref 按实测公共池 1 req/s 串行；**遇 Cloudflare 挑战（`cf-mitigated: challenge`）、403 bot 拦截或 TLS 阻断即停止该域后续请求，不更换 UA、不重试绕过**；零登录、零凭证、零 PDF 正文下载。

**检索式（WebSearch，按执行顺序）**：
1. `SSRN 2026 download policy change sign in required`
2. `NBER working papers access policy free download 2026`
3. `Econometrica self-publishing Econometric Society 2026 open access Wiley`
4. `SSRN terms of use "automated" robots spiders scraping text mining clause`
5. `"send automated queries of any sort to SSRN"`
6. `SSRN new platform 2025 Elsevier SSRN changes preprints "SSRN" announcement 2026`
7. `blog.ssrn.com 2026 SSRN refocus preprints Mendeley platform migration commercial products`
8. `"SSRN" "Research Alert" free subscriptions eJournals 2026 strategic update`
9. `SSRN "Advanced Search" 2026 blog new search filters`
10. `Elsevier API key policy 2026 ScienceDirect Article Retrieval API text mining changes`
11. `Elsevier text and data mining policy 2025 update AI LLM restrictions subscribers`
12. `American Economic Association journals access 2026 open access AER free AEA members policy change`
13. `CEPR Discussion Papers free access 2025 2026 subscription change open access`
14. `RePEc 2026 news IDEAS EconPapers changes OAI-PMH ftp getdata`
15. （SAGE / Taylor & Francis TDM 两条检索未执行：本会话 WebSearch 配额于此耗尽；后续改为直接访问已知官方 URL 与 API。）

**直接访问的站点/端点（节选，完整 URL 见 §5）**：
- robots.txt：nber.org 三主机、aeaweb.org 两主机、cepr.org、ideas.repec.org、journals.aom.org、www.aom.org、pubsonline.informs.org、onlinelibrary.wiley.com、www.tandfonline.com、link.springer.com、www.emerald.com、academic.oup.com、www.cambridge.org（403 挑战）、www.journals.uchicago.edu、publications.aaahq.org、misq.umn.edu、direct.mit.edu、www.annualreviews.org、www.degruyterbrill.com、www.sciencedirect.com、rss.sciencedirect.com、federalreserve.gov（404）、ecb.europa.eu、bis.org、imf.org、openknowledge.worldbank.org、documents.worldbank.org、iza.org、econstor.eu、econbiz.de、osf.io、api.osf.io、mpra.ub.uni-muenchen.de、hbs.edu、westernfinance.org、sfs.org、newyorkfed.org、oecd.org、bankofengland.co.uk、brookings.edu、fraser.stlouisfed.org。
- API：Crossref（`/journals/{ISSN}` 107 刊 + 最新条目各 1 次、`/prefixes/{prefix}/works` 若干、`/journals?query=` 标题检索、`/works` 头信息）、OpenAlex（单实体 `works/doi:`、`sources/issn:`，以及 107 次 `group_by=open_access.oa_status` 分组查询与 2 次 25 条摘要抽样）、World Bank D&R API v3、EconBiz API v1、OSF API v2（2 次，见下"自我纠错"）、EconStor OAI-PMH（Identify、ListSets）、Elsevier 开发者门户文档、Springer Nature 开发者门户（条款/TDM 保留政策页）。
- 补充核验：Elsevier TDM Provisions 页（key 停用与输出片段条款）、librarytechnology.org 2016-05-17 SSRN 收购新闻稿（用于纠正"Mendeley 迁移"的年代归属）、doi.org RA 查询 API（ECB/FEDS DOI 的登记机构）。FT 名录页 WebFetch 被拒（不可访问）。
- 官方页面：NBER（订阅与访问、帮助页、元数据页）、AEA（订阅页、ASSA 2026 程序与 session 页）、Econometric Society（Econometrica 访问页）、SSRN 支持中心（elsevier.support）、Digital Commons（RPS 关停说明）、CRIV 博客、Elsevier TDM/API 政策、Crossref 文档、T&F TDM 政策、AOM 期刊与 OA 期刊页、UTD 名录页、Chartered ABS AJG 页、ABDC JQL 页、Fed 与 ECB 的 RSS 目录页、SocArXiv AI 政策页、NBER SI 2026 页。

**环境障碍（与站点判罚严格区分）**：
- `www.ssrn.com`、`journals.sagepub.com`：本机网络在 TLS 握手即 reset（curl `SSL_ERROR_SYSCALL`），WebFetch 亦 `Socket is closed` → 属环境障碍，**不是**站点对本 UA 的判罚；两站 robots/ToS 原文本次未取得（v1 07-24 SSRN 勘察已记录同一现象）。
- 站点级拦截（已按红线停手）：`www.cambridge.org/robots.txt` 403 CF 挑战；`pubsonline.informs.org` 除 robots 外 4/4 页面 403 CF 挑战；`www.emerald.com/` 与 `emeraldgrouppublishing.com` 跳转后 CF managed challenge；`journals.aom.org`（WebFetch）403；`www.tandfonline.com` 与 `onlinelibrary.wiley.com` 的 `/.well-known/tdmrep.json` 403 CF 挑战；`www.imf.org` RSS 403（Akamai "Access Denied"）；`data.nber.org` 403（bot 拦截页）；`www.hbs.edu/faculty/...` 403。

**自我纠错记录（诚实留痕）**：
- `rss.sciencedirect.com`：先取 robots（`Disallow: /`）后又对 JFE feed 发出 1 次 GET（200，RSS 2.0）——该请求与 robots 冲突，属本次调研操作失误，已立即停止；结论据此写为"不可作为自动化通道"。
- `api.osf.io`：先发出 2 次 OSF API 查询（SocArXiv 计数与最新 2 条），随后读取其 robots 发现 `User-agent: * / Disallow: /`，即停止；设计建议改为 Crossref（前缀 `10.31235`）承担 SocArXiv 元数据。

**预算与限制**：WebSearch 配额在第 14 条检索后耗尽，SAGE/INFORMS/AOM/Emerald 的 TDM 条款、FT50 原文列表等因此未能经搜索补证，均在文中标 `⚠ 未核验`。（核验阶段已补证 SAGE TDM/AI 政策 [R85]、INFORMS 使用条款（摘要级）[R88] 与 FT50 2026 版名单 [R86]，逐条见文末"核验记录"；AOM/Emerald 的 TDM 条款仍未取得。）

## 2. 主体内容

### 2.1 v1 结论复核（2026-09-26）

> v1 原始勘察与决策出处见 [R73]（`docs/research/site-survey/*.md`、`docs/plan/decision-log.md`）；下表"出处"列给出具体文件。

| # | v1 结论（出处） | 2026-09-26 复核结果 | 证据 | 对 v2 的影响 |
|---|---|---|---|---|
| 1 | SSRN 全库经 Crossref `10.2139` 可读（1,414,774 DOI，07-24）；DOI 内嵌 abstract_id；约半数类型为 journal-article（ssrn.md） | **成立且更好**：总量 **1,487,290**（上午）/ **1,487,447**（下午复测）；上午口径 2026 年新建 226,181 条，其中 posted-content 225,740（99.8%）、journal-article 441 → 类型已基本统一；有摘要 206,368（91.2%；下午 206,525/226,338）；最新 `created` = 2026-09-26T13:55Z（当日）；最新 abstract_id ≈ 7.52M；`relation.type:is-preprint-of` 仅 266 条 | [R1][R78] LIVE | Crossref 可独立承担 SSRN 的"最新/检索/摘要"；"预印本→发表版"链接不能指望 Crossref relation |
| 2 | SSRN 无官方 API；浏览器 opt-in 单篇全文（D-029 模式 B） | **需收窄**：SSRN ToU 写明用户保证"不使用任何发送重复查询的软件，或以任何方式向 SSRN 发送自动化查询"；2026 年关停 Data Feeds 等商业产品；新增 Fuzzy/Boolean 高级检索（仅网页）；"迁至 Mendeley 平台"为 2016 年旧表述，未见完成证据 [R82]；**核验补充**：2026-07 起投稿可选 CC 许可，Crossref 已登记 license（见 §2.4 ssrn 行）[R91][R1] | [R5] SNIPPET（精确短语检索命中 ToU 页）；[R2][R7] SNIPPET；[R3][R4][R6] DOC | v2 对 SSRN 全文零自动化，只给外链；监控商业线关停后的平台改造对 landing URL 的影响 |
| 3 | SSRN robots 禁 GPTBot/ChatGPT-User/Google-Extended，crawl-delay 5（07-20） | **本次无法复核**（环境 TLS 阻断） | — | 维持 v1 记录并标注待复核 |
| 4 | NBER：>18 月开放、近期受限、匿名 3 篇/年（nber.md） | **成立**；免费群体表述更新为"人均 GDP < $35,000（PPP，2024 IMF 数据）国家居民"；机构按 IP 自动识别 | [R8][R9] DOC | 不变 |
| 5 | NBER JEL 仅能经 RePEc 获得（nber.md §3） | **有新渠道**：NBER 元数据页列出周更 CSV/TSV/DTA（abs、date、jel、prog、auth、title、published、ref(DOI)），但 `data.nber.org` 对非浏览器 UA 返回 403 "Prevent Bots from data downloads … If you have a legitimate need, please contact us" | [R10] DOC；[R11] LIVE | JEL/program/已发表信息可"申请授权后批量导入"，不可自动抓取 |
| 6 | NBER robots：www 无 crawl-delay；back Crawl-delay 10 | **成立**（逐行一致） | [R12] LIVE | 不变 |
| 7 | AEA：www 仅禁 GPTBot/Amazonbot；pubs Atypon + Crawl-delay 1；JEP gold/免费 | **成立**；OpenAlex 标 JEP=diamond、JEL=green（非出版方 OA）、P&P 与 AER=closed；2027 机构价 Tier1 $3,715 / Tier2 $1,370；2024-02-01 起停售纸本 | [R13] LIVE；[R14] DOC；[R15] LIVE | v1 对 JEL"免费"的记录（[DOC] 未单验）未获支持：OpenAlex 标 JEL 新文为 green（非出版方 OA），AEA 订阅页亦未列 JEL 为免费 → catalog 宜改为"订阅（有 green 副本）" ⚠ |
| 8 | ECMA 当前段自营 OA、是否全刊 OA 未决（econometric-society.md） | **结案**：学会访问页把图书馆订阅指向 Wiley Online Library，非会员经 WOL（1999 起）或 JSTOR（1933–2002）访问，会员经学会站访问全部年份（核验修正：页面未直接写"由 Wiley 出版"，Crossref publisher = The Econometric Society）；2026 DOI 仍解析到 econometricsociety.org；2025–26 年 170 条中 79 条带 CC 许可（BY 53 / BY-NC 10 / BY-NC-ND 16）→ **混合 gold OA** | [R16] DOC；[R17] LIVE | econsoc 路由按单篇 `license` 判定 OA；非 OA 单篇走用户自有 Wiley/会员凭证 |
| 9 | CEPR robots 具名禁 ClaudeBot + `ai-train=no`（07-20） | **已变化**：robots（Last-Modified 2026-09-24，Cloudflare 缓存）只含 Drupal 默认规则、facet 反爬陷阱规则与 Bing/Baidu/Yandex Crawl-delay 3；无 AI 具名条目、无 Content-Signal；DP 仍为订阅/单篇购买 | [R18] LIVE；[R19] DOC（核验阶段由 SNIPPET 升级） | 敏感度从"具名封禁"降为"订阅墙"；v2 仍仅元数据（RePEc） |
| 10 | RePEc：FTP/rsync/OAI（flaky），API 邮件门控，不建议爬网页 | **成立**；getdata 页原文仍强调"强烈不建议抓网页"，推荐 ssh rsync；2026 年新增多个 archive 与 NEP 报告调整 | [R20] DOC/SNIPPET | 不变（D-035 enrich 形态延续） |
| 11 | Elsevier：robots 默认全禁 + AI 三类治理；API 50k/周 10 rps；SD Search 20k/周 2 rps | **成立并更新**：robots 标注 "Last updated: Sep 2026"，`*` 仍 `Disallow: /`；ClaudeBot、anthropic-ai、Claude-Web、claude-code 禁；**Claude-User、Claude-SearchBot、OAI-SearchBot 显式 Allow**；配额表未变；API key 可因 6 个月未启用、1 年未访问、订阅到期或向他人披露/转让被停用；TDM 输出片段上限 200 字符 | [R24] LIVE；[R21][R81] DOC | 全文仍只走 Article Retrieval API；不做页面抓取 |
| 12 | EJOR 等可用 `rss.sciencedirect.com/publication/science/{ISSN}`（or-ms-journals.md） | **不可作为自动化通道**：该主机 robots 为 `User-agent: * / Disallow: /` | [R25] LIVE | catalog 中 RSS 表述应删除；最新论文走 Crossref |
| 13 | OUP robots 无 AI 条目 | **成立**（与 v1 一致；仅 `User-agent: 008` 全禁） | [R42] LIVE | 不变 |
| 14 | Cambridge Core：CF 前置但直连 200 未触发质询（07-20） | **已变化**：`/robots.txt` 本身即 403 `cf-mitigated: challenge` | [R43] LIVE | Cambridge 自动化面收窄为"用户会话内按需取回" |
| 15 | Springer 对数据中心 IP 在 TLS 层拒连（v1） | **本环境已可达**：robots 200（`server: Oscar Platform`），且 `/.well-known/tdmrep.json` = `tdm-reservation: 1` | [R36][R37] LIVE | 可达性与出口 IP 相关，不应写死为"不可达" |
| 16 | INFORMS 对云 IP 连接层拒绝，robots 无法勘察（informs.md §2） | **robots 已可取**：`*` 不禁 `/doi/`，Crawl-delay 1；GPTBot、ChatGPT-User、Google-Extended、PerplexityBot、anthropic-ai 被禁 `/doi/full`、`/doi/pdf`、`/doi/epdf`（允许 `/doi/abs/`）；其余页面 403 CF 挑战；无 `tdmrep.json` | [R29] LIVE | informs.md §7"实现期首项"可部分关闭（robots 已知，TDM 条款仍缺） |
| 17 | Crossref polite pool 10 req/s 并发 3（metadata-apis.md） | **公共池降速**：无 mailto 请求头为 `x-rate-limit-limit: 1`、`x-concurrency-limit: 1`、`x-api-pool: public-array`；文档（2025-10-16 版）仍写 public 5 / polite 10 / Plus 150 | [R28] LIVE；[R27] DOC | 必须带 mailto 进 polite 池并读头动态限速 |

### 2.2 平台技术栈族与共性规则

| 平台族 | 本主题成员（判定依据） | robots 共性 | "最新论文"入口 | 全文入口 | 反爬 |
|---|---|---|---|---|---|
| **Atypon / Literatum** | Wiley、T&F、INFORMS、AOM、AEA(pubs)、UChicago、SAGE（v1）、SIAM（v1） | `Disallow: /action`、`/rss`、`/search`、`/doi/mlt/`、`/doi/metrics/` 等；`Allow: /action/showJournal` 等；`Crawl-delay: 1`；GPTBot 普遍被禁 [R29][R30][R33][R34][R44] | eTOC 在 `/action/showFeed` → **robots 禁** | `/doi/pdf/`、`/doi/epdf/`（T&F 禁 `/doi/epdf/*`；INFORMS 对 AI UA 禁全文路径） | Cloudflare（页面普遍挑战） |
| **Silverchair** | OUP、MIT Press Direct、AAA（2022-12 上线）、MISQ（2025-08 上线）、Emerald（2025-07 新版上线；2026-06 Emerald 被 Wiley 收购，平台去向待观察）（核验：平台方公告确认 [R83][R87]） | 同一模板：`User-agent: 008 / Disallow: /`，`*` 禁 `/signin.aspx`、`/DownloadFile/`、`/Citation/Download`、`/Shibboleth.sso/` 等 [R41][R42][R45] | RSS 路径 ⚠（未测） | `article-pdf` 链接需从文章页解析（v1 OUP） | Cloudflare |
| **ScienceDirect**（Elsevier 自研） | Elsevier 全部刊、AOM 新 OA 刊 AMIO/AMOE（核验：AOM 页面直链 ScienceDirect 刊页，已确认 [R32]） | `*` 全禁；AI 三类治理 [R24] | `rss.sciencedirect.com` robots 全禁 [R25] | 仅 Article Retrieval API | Cloudflare 深集成 |
| **Springer Oscar** | SpringerLink（含 Palgrave 的 JIBS） | `*` 先全禁后白名单放行；20+ AI UA 全禁（含 ClaudeBot）[R36] | sitemap 可用（robots 声明多个 sitemap）；Crossref | `/content/pdf/`（机构会话） | TDMRep 保留 [R37] |
| **Cambridge Core** 自研 | JFQA、APSR、Econometric Theory | robots 本身被 CF 挑战 [R43] | Crossref | 机构会话 | Cloudflare |
| **Drupal 站群** | NBER、CEPR、BIS | Drupal 默认模板；NBER back 主机 Crawl-delay 10 | RSS（NBER/BIS） | 直链 PDF | NBER、BIS 本次无挑战；CEPR 经 Cloudflare 但 robots 可取 |
| **DSpace** | EconStor（JSPUI）、World Bank OKR（DSpace 7） | EconStor 宽松；OKR 禁 `/server/oai/`、`/server/api/`（仅放行 bitstream 等）、Crawl-delay 10 [R53][R55] | OAI-PMH（EconStor 可用；OKR 被 robots 禁） | bitstream | — |
| **EPrints** | MPRA | `*` 禁 `/cgi/`（EPrints 默认 OAI 路径 `/cgi/oai2` 落在其中，⚠ 端点未实测）；具名禁 Claude 系三 UA [R59] | 经 RePEc | 直链 PDF | — |
| **bepress Digital Commons** | AIS eLibrary（ICIS/JAIS 等） | `Disallow: /do/`（Digital Commons 默认 OAI 路径 `/do/oai/` 落在其中，⚠ 端点未实测）[R76] | 经 Crossref（有 DOI 部分） | 直链 | Cloudflare |
| **OSF** | SocArXiv | `osf.io`：`*` Crawl-delay 10、禁 `/api/*`；`api.osf.io`：`Disallow: /` [R57] | Crossref（`10.31235`） | osf.io 下载 | — |

**结论**：商科/经济核心刊约 3/4 落在 Atypon 与 Silverchair 两族；两族 robots 都把"订阅流/eTOC/检索"列为禁区，因此 v2 的"发现+最新"层**必须与出版社站点解耦**（Crossref 主干），站点仅在用户自有会话中承担"单篇全文取回"。

### 2.3 来源名录 A：一级出版商 / 期刊平台（L1-publisher / L1-journal-platform）

> 统一列供设计阶段合并为总名录。"最新论文通道"一栏凡写"Crossref 增量"者，均指按 ISSN 的 `filter=from-created-date:`（新 DOI）+ `from-index-date:`（元数据更新）增量拉取，Crossref 官方建议以 `from-index-date`/`until-index-date` 同步本地数据（[R80]；v1 metadata-apis.md）。Crossref 摘要/许可覆盖率取自 §2.8 实测。

| source_id（snake_case） | 名称 | 层级类型 | 学科 | 平台技术栈 | 元数据通道 | 最新论文通道 | 全文通道与门控 | 认证方式 | 限速与 ToS/robots 要点（来源+日期） | v1 是否已支持 | 建议优先级及理由 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| elsevier_sd | Elsevier ScienceDirect | L1-publisher | 经济/金融/会计/管理/OR | ScienceDirect 自研 + Cloudflare | 委托 Crossref（10.1016）；**Crossref current 摘要 0%**（JFE/JME/JET 等 19 刊实测），OpenAlex 对 2026 新文亦无摘要（JFE、JET 抽样）[R70][R77]；SD Search API 受"联邦检索结果不得存储"政策约束 [R22] | Crossref 增量（`rss.sciencedirect.com` robots `Disallow: /` → 不轮询）[R25] | 订阅/混合；全文仅经 Article Retrieval API（订阅机构研究者非商业 TDM）[R23]；页面 PDF 路径 robots 禁 [R24] | 用户个人 API key（+可选 insttoken）；机构 IP entitlement | Article Retrieval 50k/周·10 rps（TDM key 不限量）、SD Search 20k/周·2 rps [R21]；key 可因 6 个月未启用、1 年未访问、订阅到期或**出售/转让/披露给他人**而被停用；TDM 输出片段 ≤200 字符、不得用于与 Elsevier 产品竞争的仓储/服务 [R81]；robots（Sep 2026）`*` 全禁，ClaudeBot/claude-code 禁，Claude-User/Claude-SearchBot/OAI-SearchBot Allow [R24] | ✅ 已实现（`elsevier_sd`；JFE/JBF/JET/JPubE 已注册） | **P0**：经济金融 OR 场内刊最多；元数据零接触，全文按用户 key 私有取回；摘要需另行补齐 |
| wiley_wol | Wiley Online Library（含 `sms.`/`myscp.` 学会子域） | L1-publisher | 金融/经济/战略/会计/政治 | Atypon + Cloudflare | Crossref（10.1111/10.1002），current 摘要 64–90%（JF 73%、SMJ 78%、JAR 70%）[R70] | Crossref 增量（Atypon `/action`、`/rss` robots 禁）[R33] | 订阅/混合；TDM API `api.wiley.com/onlinelibrary/tdm/v1/articles/{DOI}`（token；受订阅 entitlement 约束）[v1 2026-07-23] | 用户个人 TDM token；机构 SSO | TDM 至多 3 篇/s 且 60 次/10 min（持续运行约 10 s/次）[v1；核验：WileyLabs/tdm-client README 复述官方 TDM 资源页 [R84]]；robots `*` 路径级、GPTBot/Google-Extended 全禁、Crawl-delay 1；`tdmrep.json` 被 CF 挑战 [R33] | ✅ 已实现（JF/MathFin/RAND/IER 已注册） | **P0**：JF、SMJ、JOM(运营)、JAR、CAR、JMS、SEJ 等 UTD24/FT50 大户 |
| oup_academic | Oxford Academic | L1-publisher | 经济/金融/营销 | Silverchair + Cloudflare | Crossref（10.1093），current 摘要 90–99%、license ≥97% [R70] | Crossref 增量 | 订阅/混合；无公开 TDM API（机构订阅含非商业 TDM）[v1] | 机构 SSO cookie（用户自有） | robots 无 AI 条目、无 Crawl-delay（与 v1 一致）[R42]；页面 CF 质询 [v1 2026-07-23] | ✅ 已实现（`oup_silverchair`；QJE 已注册） | **P0**：QJE、REStud、RFS、RoF、RAPS、RCFS、JEEA、EJ、JCR |
| cup_core | Cambridge Core | L1-publisher | 金融/计量/实验经济/政治 | 自研（SSR）+ Cloudflare | Crossref（10.1017），JFQA 摘要 84%；Experimental Economics 已迁 CUP（DOI `10.1017/eec.*`）[R70] | Crossref 增量 | 订阅/混合；TDMRep 生效 [v1] | 机构 SSO | **变化**：`/robots.txt` 本身 403 `cf-mitigated: challenge`（v1 为 200）[R43] | ⛔ 仅设计（`cambridge`） | **P1**：JFQA（金融 Top3 之外的核心刊，v1 T1/T2）、APSR、Experimental Economics |
| springer_link | SpringerLink（含 Palgrave） | L1-publisher | 国际商务/会计/营销/伦理/经济 | "Oscar Platform"（响应头 `server`）| Crossref（10.1007/10.1057），摘要 36–61%；Springer Nature Meta API（摘要仅限个人非商业使用）[R39] | Crossref 增量；robots 声明多组 sitemap [R36] | 订阅/混合；OA API；Full-Text TDM API（机构许可，仅限机构内部服务器，不得第三方访问）[R39] | API key（**不得多账号/多 key 规避限额**）[R39]；机构 SSO | robots `*` 先全禁后白名单（/article、/content、/journal*、/doi…）；ClaudeBot/anthropic-ai/Claude-Web/GPTBot 等 20+ AI UA 全禁；TDMRep `tdm-reservation:1`，政策保留 EU DSM Art.4(3) TDM 与 AI 训练权 [R36][R37][R38]；API 配额数字门户为 JS 渲染 ⚠ 未取得 [R40] | ⛔ 仅设计（`springer`） | **P1**：JIBS（UTD24）、RAST、JAMS、JBE、Finance & Stochastics、JEG |
| tandf_online | Taylor & Francis Online | L1-publisher | 计量/量化金融/IS/会计 | Atypon + Cloudflare | Crossref（10.1080），**QF/JMIS 摘要 0%**，OpenAlex 新文亦缺 [R70][R77] | Crossref 增量 | 订阅/混合；TDM：订阅者非商业、按 STM 模型许可，无公开 API [R35] | 机构 SSO | robots Atypon 族 + `Disallow: /doi/epdf/*`、GPTBot 全禁、Crawl-delay 1；`tdmrep.json` 被 CF 挑战 [R34] | ⛔ 未设计 | **P1**：JMIS（FT50）、Quantitative Finance、JBES |
| sage_journals | SAGE Journals | L1-publisher | 管理/营销/组织/社会学/运营 | Atypon + Cloudflare（v1 [LIVE 2026-07]） | Crossref（10.1177），摘要 JOM/ETP/POM ≥99%、JM 95%、JMR 98%，但 ASQ 仅 39% [R70] | Crossref 增量 | 订阅/混合；TDM（核验补充）：对合法可访问内容做非商业 TDM 无需另签许可，AI（含生成式 AI）用途须另获 Sage 许可，建议经 Crossref API 取全文链接 [R85]；TDM 许可页限速为 PT 工作日 0–12 时 1 次/6 s、其余时段 1 次/2 s（[R85] SNIPPET） | 机构 SSO | 本环境 TLS reset，`journals.sagepub.com` robots/ToS **⚠ 未核验**（2026-09-26）[R75]；TDM/AI 政策已经 `www.sagepub.com` 核验 [R85] | ⛔ 仅设计（`sage`，仅 POM） | **P1**：ASQ、JM、JMR、POM（UTD24）+ JOM、OrgStud、HR、ETP |
| emerald_insight | Emerald Insight | L1-publisher | 管理/营销/运营/金融 | Silverchair（2025-07-22 新版 Emerald Insight 上线，平台方公告确认 [R83]；robots 模板亦同构）；Cloudflare | Crossref（10.1108）；Critical Finance Review 已归 Emerald（DOI `10.1108/cfr-*`）[R70] | Crossref 增量 | 订阅/混合；TDM ⚠ 未核验 | 机构 SSO | robots 显式 Allow ChatGPT-User/OAI-SearchBot/Claude-User 等检索型 AI；首页 CF managed challenge；`emeraldgrouppublishing.com` 301 至 `emerald.com` [R41] | ❌ | **仅元数据（P2）**：多为 AJG 2–3 级刊；CFR 例外可 P1。**核验补充**：Emerald 于 2025-05 收购 now publishers（14 刊 + 28 种 Foundations and Trends 系列），2026-06-02 又被 Wiley 收购 [R87] → 列入漂移监测（平台迁移、AI 授权取向） |
| informs_pubsonline | INFORMS PubsOnline | L1-journal-platform | 管理科学/营销/IS/OR/组织 | Atypon + Cloudflare | Crossref（10.1287），摘要 85–97%，license 0%（不登记许可）[R70] | Crossref 增量（eTOC 在 `/action/showFeed`，robots 禁） | 订阅；pubsonline 条款页全部 CF 挑战、无 `tdmrep.json`（404）；**核验补充**：informs.org 的 PubsOnLine Terms and Conditions（本环境同样 CF 挑战，仅 SNIPPET）称未经 INFORMS 明确批准禁止以机器人或其他自动流程系统性下载，离线浏览器每分钟不超过 20 页，违规即封禁 [R88] | 机构 SSO / 会员 | robots：`*` 不禁 `/doi/`、Crawl-delay 1；GPTBot/ChatGPT-User/Google-Extended/PerplexityBot/anthropic-ai 禁 `/doi/full`、`/doi/pdf`、`/doi/epdf`；除 robots 外 4/4 页面 403 CF [R29] | ⛔ 仅设计（`informs`，review） | **P0**：UTD24 中 7 刊（MS、Mkt Sci、ISR、OR、MSOM、OrgSci、IJOC），杠杆最大 |
| aom_journals | AOM Journals | L1-journal-platform | 管理/战略/组织/创业 | Atypon + Cloudflare | Crossref（10.5465），**7 刊摘要 0%**；OpenAlex 摘要有滞后（AMJ 2025 抽样 23/25，2026-09 新文缺）[R70][R77] | Crossref 增量 | 订阅/会员（"AOM members must be signed in"）；无 `tdmrep.json` [R31] | 会员登录 / 机构 | robots `*` 不禁 `/doi/`、Crawl-delay 1、GPTBot 全禁；`www.aom.org` robots 首行为孤立的 `Crawl-delay: 10`（作用域含糊，按保守解释遵守）；**新**：Vision 2030 与 Elsevier 出版合作，新增 OA 刊 Inside Organizations（AMIO）与 Organizations and Their Environments（AMOE），两刊刊页位于 ScienceDirect（核验确认）[R30][R32] | ❌ | **P0**：AMJ、AMR（UTD24）+ Annals、AMP、AMLE、AMD、Proceedings |
| aea_journals | AEA Journals | L1-journal-platform | 经济 | www（Apache）+ pubs（Atypon + CF） | Crossref（10.1257），摘要 80–94% [R70] | Crossref 增量 | AER/AEJ/Insights/P&P 订阅（OpenAlex=closed）；JEP diamond OA；JEL 仅 green [R15] | 机构 IP / 会员 | 与 v1 一致：www 仅禁 GPTBot/Amazonbot；pubs Atypon 族 + Crawl-delay 1 [R13]；2027 机构价 Tier1 $3,715 / Tier2 $1,370 [R14] | ✅ 已实现（`aea`，8 刊） | **P0**（维护） |
| econsoc_journals | Econometric Society（ECMA/TE/QE） | L1-journal-platform | 经济/计量 | 自营 econometricsociety.org（CF）+ OJS；ECMA 过刊 Wiley | Crossref（10.3982）；TE/QE OJS OAI-PMH [v1] | Crossref 增量 | TE/QE 全 OA；**ECMA 混合 gold OA**（2025–26：79/170 带 CC 许可，BY 53 / BY-NC 10 / BY-NC-ND 16，核验修正）[R17]；非会员经 Wiley（1999–）/JSTOR（1933–2002）[R16] | 会员登录 / 机构（Wiley） | econometricsociety.org robots 具名禁 ClaudeBot 等，自营域曾现 CF 质询 [v1 2026-07-24/26] | ✅ 已实现（`econsoc`） | **P0**（维护；按单篇 `license` 判 OA） |
| uchicago_journals | UChicago Press Journals | L1-publisher | 经济/社会学/政治 | Atypon + Cloudflare | Crossref（10.1086），**JPE/JOLE/JLE/AJS/JOP 摘要 0%** [R70] | Crossref 增量 | 订阅；epdf 阅读器；批量下载需事先许可 [v1] | 机构 SSO | robots Crawl-delay 1、GPTBot 条目 [R44] | ⛔ 仅设计（`uchicago`） | **P1**：JPE（Top5）、JOLE、JLE、AJS、JOP |
| mit_press_direct | MIT Press Direct | L1-publisher | 经济 | Silverchair（robots 同构）[R45] | Crossref（10.1162），REStat 摘要 99% [R70] | Crossref 增量 | 订阅；TDM 需书面特批并明禁脚本抓取 [v1] | 机构 SSO | 同 Silverchair 族 | ⛔ 仅设计（`mit_press`） | **P2 / 仅按需单篇**：REStat |
| aaa_pubs | AAA Publications | L1-journal-platform | 会计 | Silverchair（2022-12-13 上线，平台方公告确认 [R83]）+ CF [R45] | Crossref（10.2308），TAR 摘要 91% [R70] | Crossref 增量 | 订阅 | 会员 / 机构 | ToS ⚠ 未核验 | ❌ | **P1**：TAR（UTD24） |
| misq | MIS Quarterly | L1-journal-platform | 信息系统 | Silverchair（2025-08-21 上线，平台方公告确认 [R83]）+ CF [R45] | Crossref（10.25300），摘要 90% [R70] | Crossref 增量 | 订阅 | 机构 | ToS ⚠ 未核验 | ❌ | **P1**：MISQ（UTD24） |
| apa_psycnet | APA PsycNet（JAP 等） | L1-publisher | 组织心理 | 自研（`doi.apa.org`） | Crossref（10.1037），JAP 摘要 0% [R70] | Crossref 增量 | 订阅 | 机构 | ⚠（心理学另有主题文档） | ❌ | **仅元数据（P2）**：JAP 属 FT50，交心理学主题统筹 |
| annual_reviews | Annual Reviews | L1-publisher | 经济/金融/组织心理（综述） | Ingenta Edify（Annual Reviews 迁移 FAQ 称 2024-03-19 迁入，SNIPPET 级确认 [R89]；与 robots `/deliver/`、`/carnet/`、`/counterstats/` 路径特征一致）+ CF | Crossref（10.1146），ARFE 摘要 95%、license 62% [R70] | Crossref 增量 | 部分 OA（license 覆盖 62%，OpenAlex source 标 `is_oa:false`）⚠ | 机构 | robots `*` Crawl-delay 2、`/deliver/` 禁 [R46] | ❌（v1 T3） | **P2** |
| pm_research | PM Research（JPM 等） | L1-publisher | 实务金融/量化 | ⚠ | Crossref（10.3905，出版者现为 "With Intelligence LLC"），摘要 0% [R70] | Crossref 增量 | 订阅 | 机构/个人 | ⚠ | ⛔ 仅设计 | **P2** |
| degruyter_brill | De Gruyter Brill | L1-publisher | 经济（B.E. Journals） | CloudFront | Crossref（10.1515） | Crossref 增量 | 订阅/混合 | 机构 | robots 含 Google-Extended/GPTBot/CCBot/FacebookBot/Omgilibot 具名条目 [R47] | ❌ | **P2** |
| jstor | JSTOR | L1-journal-platform（过刊档案） | 全学科过刊 | Fastly + PerimeterX [v1] | Crossref（10.2307）；人工数据集申请 [v1] | 不适用 | 订阅；EJC 免费；Constellate 2025-07 停运 [v1] | 机构 / JPASS | robots 具名禁 ClaudeBot/CCBot/GPTBot [v1 2026-07-20] | ⛔ 仅设计 | **仅元数据（P2）** |
| hbp_hbr | Harvard Business Review | L1-publisher（实务刊） | 管理 | 自研 | **ISSN 0017-8012 在 Crossref 不存在（404）→ 无 DOI 枚举** [R70] | ⚠ | 订阅（HBP） | 个人/机构 | ⚠ | ❌ | **排除**（FT50 实务刊；无开放元数据通道） |
| mit_smr | MIT Sloan Management Review | L1-publisher（实务刊） | 管理 | 自研（sloanreview.mit.edu） | Crossref 新前缀 10.63383（仅 135 DOI）[R70] | Crossref 增量 | 订阅 | 个人 | ⚠ | ❌ | **仅元数据（P2，观望）**。**核验补充**：MIT Sloan 于 2026-05-06 宣布停办；2026-09-10 更新为秋季刊后停印，数字内容持续至 2026-11，冬季推出纯数字新版，存档保留 [R90] → 新前缀的后续登记不确定 |

**学会 → 平台归属速查（本主题新增学会）**：Strategic Management Society 的 SMJ/SEJ/GSJ 在 Wiley 学会子域 `sms.onlinelibrary.wiley.com`（DOI 10.1002）；Academy of International Business 的 JIBS 在 SpringerLink（Palgrave，DOI 10.1057）；AMA 的 JM/JMR 在 SAGE；SCP 的 JCP 在 Wiley `myscp.` 子域；AFA 的 JF 在 Wiley；SFS 的 RFS/RAPS/RCFS 与 EFA 的 RoF 在 OUP；Economic Science Association 的 Experimental Economics 已在 CUP（`10.1017/eec.*`）；Critical Finance Review 已在 Emerald（`10.1108/cfr-*`；原出版方 now publishers 于 2025-05 被 Emerald 收购，核验补充 [R87]）（均 [R70] LIVE 2026-09-26）。

### 2.4 来源名录 B：一级预印本 / 工作论文系列（L1-preprint，含央行与国际组织）

| source_id（snake_case） | 名称 | 层级类型 | 学科 | 平台技术栈 | 元数据通道 | 最新论文通道 | 全文通道与门控 | 认证方式 | 限速与 ToS/robots 要点（来源+日期） | v1 是否已支持 | 建议优先级及理由 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ssrn | SSRN | L1-preprint | 经济/金融/管理/会计/法律等 | Elsevier 自研 + CF（2026 商业线关停后平台改造中，[R2]） | 委托 Crossref（10.2139）：1,487,447 DOI；2026 年新建 226,338 条，摘要 91.2%；类型几乎全为 posted-content [R1]；**核验补充**：2026-07-20 后新建 76,405 条中 69,436 条登记 license（全部权利保留 56,335、CC BY 6,875、CC BY-NC-ND 3,887、CC BY-NC 2,053、CC0 286）[R1][R91] | Crossref `from-created-date`（新 DOI 当日可见）[R1]；eJournal 邮件继续，未来拟提供免费 Research Alert [R2] | 作者上传版免费、出版商/机构上传可收费 [R6]；**ToU 禁止任何自动化查询** [R5] → 全文只外链 | 元数据无需；全文=用户在浏览器自行下载 | ToU 自动化禁令 [R5 SNIPPET]；robots 本环境不可达（v1：禁 GPTBot 等、crawl-delay 5s）；商业线（RPS、Site Subscriptions、付费 Conference Proceedings、Data Feeds、Jobs 等）2026-12-31 前关停，RPS 仅能导出元数据 [R2][R3][R4] | ✅ 元数据（`ssrn` 委 crossref）；浏览器全文模式 B 已落地但默认关闭（Phase 7 T11，D-029/D-030） | **P0（元数据）；全文排除自动化**：经管 WP 第一来源，但 ToU 明禁自动化 → 建议 v2 移除模式 B |
| nber_wp | NBER Working Papers | L1-preprint | 经济/金融 | Drupal（www/nginx）+ back（Akamai） | Crossref（10.3386）：36,256 DOI，2026 年新建 1,207 条，**摘要 0 条** [R78]；NBER 周更元数据文件（abs/jel/prog/published/ref 等 TSV/CSV/DTA）[R10] 但 `data.nber.org` 对 bot 403 [R11] | RSS `back.nber.org/rss/new.xml` 与 program feed（Crawl-delay 10）[R12] | 18 个月后开放；近 18 个月在高收入国家需订阅，匿名每年 3 篇；机构 IP 自动识别 [R8][R9] | 机构 IP / 订阅 | robots 与 v1 一致 [R12]；**不利用软门**（D-014） | ✅ 已实现（`nber`） | **P0**（维护；JEL/已发表映射走"申请授权的批量文件"或 RePEc） |
| cepr_dp | CEPR Discussion Papers | L1-preprint | 经济/金融 | Drupal + Cloudflare | RePEc（`cpr:ceprdp`）[v1]；Crossref 无对应刊名/系列记录（journals 检索为空）[R78] | RePEc 增量；CEPR 站每周"New Discussion Papers"新闻页 [R19] | 订阅/单篇购买（1984 年以来 20,000+ 篇）[R19] | 订阅 | **变化**：robots（Last-Modified 2026-09-24）无 AI 具名条目、无 Content-Signal；Bing/Baidu/Yandex Crawl-delay 3 [R18] | ✅ 仅元数据（经 repec） | **仅元数据** |
| iza_dp | IZA Discussion Papers | L1-preprint | 劳动/人口/发展 | 自研 CMS | 站点列表页（DP 号、题名、JEL 在详情页；无 `citation_*` meta）；RePEc（`iza:izadps` ⚠ 未核）；Crossref 无系列记录 [R54][R78] | 列表页按号倒序（2026-09-26 最新 DP 18966）[R54] | 免费 PDF（`docs.iza.org/dp{n}.pdf`）[R54] | 无 | robots `User-agent: * / Disallow:`（全允许，无 crawl-delay）[R54] | ❌ | **P1**：劳动经济核心 OA 系列；优先经 RePEc 取元数据，PDF 直链按需 |
| fed_board_wp | Fed Board：FEDS / IFDP / FEDS Notes | L1-preprint | 宏观/金融/国际金融 | 自研 + Cloudflare | Crossref（10.17016）：4,991 DOI，2026 年新建 170 条，摘要 168 条（99%）；RA=Crossref [R78][R79] | RSS `feeds/feds.xml`、`ifdp.xml`（各 15 条，含作者与摘要），另有 `feds_notes.xml` [R48] | 免费 | 无 | `robots.txt` 404（无限制）[R48] | ❌ | **P1**：Crossref + RSS 双通道，元数据质量高 |
| ecb_wp | ECB Working Paper Series | L1-preprint | 货币/宏观/金融稳定 | 自研（`server: myracloud`） | RSS；**DOI 10.2866 由欧盟出版局 RA（OP）登记，不在 Crossref** [R79]；RePEc/SSRN 亦收录 ⚠ | RSS `rss/wppub.html`（RSS 2.0，含摘要，lastBuildDate 2026-09-25）[R49] | 免费 PDF | 无 | robots Crawl-delay 5 [R49] | ❌ | **P1**：唯一合规增量是其 RSS；Crossref 枚举不可用 |
| bis_wp | BIS Working Papers | L1-preprint | 国际金融/宏观审慎 | Drupal | RSS 1.0 + Dublin Core + **CB-RSS 扩展**（`cb:keyword`、`cb:person`、`cb:resource` PDF 链接）[R50] | RSS `doclist/wppubls.rss`（25 条；最新 WP 1379，2026-09-23）[R50] | 免费 PDF（`/publications/…pdf`，不在 robots 禁区）| 无 | robots Drupal 默认 + `Disallow: /p/`、`/sites/default/files/` [R50] | ❌ | **P1**：CB-RSS 字段最全，可做通用央行解析器 |
| imf_wp | IMF Working Papers | L1-preprint | 国际宏观/金融 | www（Vercel）+ Akamai 边缘 | Crossref（10.5089）：105,381 DOI；2026 年新建 76,378 条中 65,142 为 component、10,372 为 chapter（eLibrary 批量登记）；`query.container-title=IMF Working Papers` 命中 23,858（相关度检索，⚠ 近似）[R78] | Crossref 增量（需按 container 过滤）；官方 RSS 对本 UA 403（Akamai "Access Denied"）→ 已停手 [R51] | 免费 | 无 | robots 宽松（仅禁 `/external/...` 等）[R51] | ❌ | **P1（元数据经 Crossref/RePEc）** |
| worldbank_prwp | World Bank Policy Research WP（及 D&R 文献库） | L1-preprint | 发展/公共/金融 | Documents & Reports（CF）+ OKR（DSpace 7） | **官方 API v3** `search.worldbank.org/api/v3/wds`：`docty=Policy Research Working Paper` 共 11,380 条，返回摘要、`pdfurl`、`repnb`（WPS 号）[R52]；Crossref（10.1596）仅覆盖部分 PRWP（`Policy Research Working Papers` 检索 2,221）[R78] | API `sort=docdt&order=desc` | 免费（许可 ⚠ 逐篇字段） | 无 | API 主机无 robots（404）；OKR robots 禁 `/server/oai/`、`/server/api/`（仅放行 bitstream 等）、Crawl-delay 10 [R52][R53] | ❌ | **P1**：走官方 API，勿用 OKR OAI |
| hbs_wp | HBS Working Papers | L1-preprint | 管理/战略/营销 | SharePoint 系 | 经 SSRN（Crossref 10.2139）/ RePEc ⚠ | Crossref（SSRN） | 免费 PDF ⚠ | 无 | 研究页对本 UA 403；robots Crawl-delay 2 [R60]；SSRN RPS 年底关停可能影响其 SSRN 系列页 [R3][R4] | ❌ | **仅元数据（P2）** |
| mpra | MPRA | L1-preprint（仓储型） | 经济 | EPrints | RePEc（`pra:mprapa` ⚠） | RePEc | 免费 PDF | 无 | robots：`*` 禁 `/cgi/`（EPrints 默认 OAI 路径 `/cgi/oai2` 在禁区内 → 不收割，⚠ 端点未实测）；**具名禁 ClaudeBot/Claude-User/Claude-SearchBot**，Bingbot Crawl-delay 10 [R59] | ❌ | **仅元数据（P2）** |
| socarxiv | SocArXiv | L1-preprint | 社会学/政治/经济/管理 | OSF（Center for Open Science） | Crossref（10.31235，登记方 Center for Open Science）：25,786 DOI，2026 年新建 4,807 条，摘要 99% [R78]；OSF API 计数 25,141（但 `api.osf.io` robots `Disallow: /`）[R57] | Crossref 增量 | OA（`osf.io` 下载，Crawl-delay 10）| 无 | osf.io 禁 GPTBot/PerplexityBot/Meta-ExternalAgent 等；2026-03-08 新 AI 政策收紧审核 [R57][R58] | ❌ | **P1**：社科 OA 预印本；元数据走 Crossref |
| arxiv_econ_qfin | arXiv `econ.*`、`q-fin.*` | L1-preprint | 经济/量化金融 | arXiv | 见预印本主题文档 | 同左 | OA | 无 | 同左 | ✅ 已实现（12 个分类 VenueSpec） | P0（已有） |
| cesifo_wp | CESifo Working Papers | L1-preprint | 经济 | ⚠ | RePEc（`ces:ceswps` ⚠） | RePEc | 免费 ⚠ | 无 | `www.cesifo.org` 301（未深探） | ❌ | P2 |
| other_cb_wp | 其他央行/国际组织 WP（NY Fed Staff Reports、BoE、OECD、Brookings 等） | L1-preprint | 宏观/金融/政策 | 各异 | 优先 RePEc/Crossref（有 DOI 者） | 各自 RSS ⚠ | 多为免费 | 无 | robots：newyorkfed、bankofengland、brookings、oecd 均仅 `User-agent: *` 常规条目 [R74] | ❌ | P2（按用户订阅需求逐个接入） |

### 2.5 来源名录 C：一级会议平台（L1-conference-platform）

| source_id（snake_case） | 名称 | 层级类型 | 学科 | 平台技术栈 | 元数据通道 | 最新论文通道 | 全文通道与门控 | 认证方式 | 限速与 ToS/robots 要点（来源+日期） | v1 是否已支持 | 建议优先级及理由 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| assa_meetings | ASSA 年会（AEA 主办，含 AFA 等学会分会场） | L1-conference-platform | 经济/金融 | aeaweb.org 自研 | 程序 HTML：session 带 JEL 码与主办学会（如 "Hosted By: American Finance Association"），论文页含作者、机构与摘要；另提供按学会/按日程的程序下载 [R61] | 年度（1 月会期；`/conference/{yyyy}/program` 分页）| 部分论文有作者上传 "Download Preview (PDF)"（`/conference/{yyyy}/program/paper/{token}`）[R61] | 无 | robots 仅禁 GPTBot/Amazonbot [R13] | ❌ | **P1**：经济/金融会议最结构化的公开源（JEL + 摘要 + 部分 PDF） |
| nber_conferences | NBER Summer Institute 与各类会议 | L1-conference-platform | 经济/金融 | nber.org + conference.nber.org | 会议页（SI 2026 页面列出 50 个 `si-2026-*` 分会链接，如 `si-2026-asset-pricing`）+ 议程页 `conference.nber.org/agenda/simple_printable?conf_id=SI26AP` [R64] | 年度（SI 7 月） | 论文多链至 NBER WP（`/papers/w{n}`），其余 ⚠ | 无 | 同 nber | 部分（nber 仅 WP） | **P1**：复用 `nber` adapter 增加"会议标签" |
| wfa_meeting | WFA 年会 | L1-conference-platform | 金融 | WordPress + 会员门户 | 程序位于登录门户（`westernfinance-portal.org` 跳转 `/login`）[R62] | — | 作者自存（多在 SSRN） | 会员登录 | 主站 robots 宽松，但程序需登录 → 不自动化 [R62] | ❌ | **仅元数据（经 SSRN）** |
| sfs_cavalcade | SFS Cavalcade（北美/亚太） | L1-conference-platform | 金融 | WordPress | 程序页 HTML ⚠ | — | robots 禁 `/acceptedpaper`、`/portal`、`/wp-content` [R63] | — | 同左 | ❌ | **排除全文；仅会议标签** |
| efa_meeting | EFA 年会 | L1-conference-platform | 金融 | ⚠ 未核验 | ⚠ | — | ⚠ | — | ⚠ | ❌ | P2 |
| aom_proceedings | AOM Annual Meeting Proceedings | L1-conference-platform | 管理 | Atypon（journals.aom.org） | Crossref（`10.5465/amproc.*`，ISSN 0065-0668）：69,864 DOI、current 16,766，摘要 0%（DOI 形如 `…10716abstract`）[R70] | Crossref 增量 | 摘要/简版论文，会员 | 会员 | 同 aom_journals | ❌ | **P2**：量大质杂，适合作"会议标签 + 作者兴趣信号" |
| ais_icis | ICIS / AIS eLibrary | L1-conference-platform | 信息系统 | bepress Digital Commons + CF | Digital Commons 默认 OAI 路径 `/do/oai/` 落在 robots `Disallow: /do/` → 不收割（⚠ 端点未实测）[R76] | — | 多为 OA | 无 | 同左 | ❌ | P2 |
| sed_meetings | SED Meetings | L1-conference-platform | 宏观 | RePEc 系列 ⚠ | RePEc ⚠ | — | ⚠ | — | ⚠ | ❌ | P2 |
| informs_annual | INFORMS Annual Meeting | L1-conference-platform | OR/MS | ⚠ | 仅摘要级程序 ⚠ | — | 无论文 | — | ⚠ | ❌ | 排除 |

### 2.6 来源名录 D：二级仓库 / 聚合（L2，经管特有）

| source_id（snake_case） | 名称 | 层级类型 | 学科 | 平台技术栈 | 元数据通道 | 最新论文通道 | 全文通道与门控 | 认证方式 | 限速与 ToS/robots 要点（来源+日期） | v1 是否已支持 | 建议优先级及理由 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| repec | RePEc（IDEAS / EconPapers） | L2-aggregator | 经济/金融 | 分布式 ReDIF（2,400+ archive、106 国，550 万+ 条目，覆盖 4,600 刊与 5,900 个 WP 系列；核验修正，原作 2,250+ [R92]）| FTP `ftp.repec.org` 镜像 / ssh rsync（官方推荐）；OAI-PMH（"sometimes flaky"）；API（邮件申请，仅切片）[R20] | rsync/FTP 增量；NEP 主题报告 | 链出（不自托管） | 无 | getdata 页"强烈不建议抓取网站"；IDEAS robots 仅禁 `/cgi-bin/` [R20][R72] | ✅ enrich（D-035） | **P0（enrich）**：JEL、工作论文↔发表版关联、非 DOI 长尾（IZA/CEPR/MPRA/CESifo） |
| econstor | EconStor（ZBW） | L2-repository | 经济/管理 | DSpace（JSPUI） | OAI-PMH：`earliestDatestamp` 2009-01-28、秒级粒度、`deletedRecord: transient`、按学科/文献类型分 set [R55] | OAI `from=` 增量 | OA 全文（机构 WP 为主） | 无 | robots 仅禁 `/discover`、`/simple-search` 及若干浏览路径 [R55] | ❌（v1 T3 登记） | **P1**：欧洲经管 WP 的 OA 全文层 |
| econbiz | EconBiz（ZBW） | L2-aggregator | 经济/管理 | VuFind（据 robots 路径特征推断 ⚠）+ REST API | API v1（JSON；beta；当前无配额；"不应用于大规模复制索引"，ECONIS 全量需申请；建议申请应用名以便识别）[R56] | 记录含 `econbiz_created` 时间戳 [R56] | 链出（`identifier_url` 含 DOI/PDF） | 无 | www robots 仅禁 MyResearch/Export 等 [R56] | ❌ | **P1**：STW 标准词表主题标引，补经管学科路由 |
| worldbank_okr | World Bank OKR | L2-repository | 发展 | DSpace 7 | robots 禁 `/server/oai/` 与大部分 `/server/api/` → 以 D&R API 代替 [R53] | — | OA | 无 | Crawl-delay 10 [R53] | ❌ | 并入 `worldbank_prwp` |
| fraser | FRASER（St. Louis Fed） | L2-repository | 经济史/政策文献 | Apache | API ⚠ 未核验 | — | 免费 | 无 | robots Crawl-delay 10 [R74] | ❌ | P2 |
| crossref（及 openalex/unpaywall/core/s2） | 通用聚合层 | L2-aggregator | 全学科 | — | 详见聚合主题文档；本主题相关实测：Crossref 公共池头 1 req/s、并发 1（文档：public 5/polite 10/Plus 150）；Crossref 声明"部分摘要可能受版权"；OpenAlex 对 Elsevier/AOM/T&F/SAGE 的 2026-09 新文无摘要 [R26][R27][R28][R77]；**核验补充**：OpenAlex 2026 年起改为 API key + 按量计费（注册 key 每日 $1 免费额度；无 key 请求仍可用但额度极小，实测请求头 `x-ratelimit-limit-usd: 0.1`、list 请求单价 $0.0001）[R93]；Crossref 2026 年度公共数据文件（2026-03-17 发布，约 1.8 亿条、208 GB）可承担首轮全史回填 [R94] | — | — | — | — | ✅ | **P0（元数据主干）** |
| econlit | EconLit（AEA）（核验补充） | L2-aggregator（书目索引） | 经济 | AEA 书目库（经订阅供应商提供，⚠ 渠道条款未核验） | 200 万+ 记录、覆盖约 140 年与 75 国文献、JEL 编码标引；页面未见公开 API 或批量下载 [R95] | — | 订阅（可加购 500+ 刊全文包）[R95] | 机构订阅 | 页面仅 "All rights reserved"，无公开数据许可 [R95] | ❌ | **排除（参考）**：JEL 权威索引但仅限订阅；v2 的 JEL 路由仍以 RePEc/NBER jel.tsv/ASSA 为主 |

### 2.7 期刊名录体系（venue 名录来源）

| list_id | 名录 | 维护方 | 当前版本（核验） | 规模 / 分级 | 获取方式与许可 | v2 用法建议 |
|---|---|---|---|---|---|---|
| utd24 | UTD 24 | UT Dallas Naveen Jindal School（"UTD Top 100 Business School Research Rankings"） | 在线列表：24 刊，多数 "Since: 1990"，MSOM "Since: 1999"，POM "Since: 1992" [R65] | 24 刊 = 会计 3（TAR、JAE、JAR）、金融 3（JF、JFE、RFS）、IS 3（ISR、INFORMS JoC、MISQ）、营销 4（JCR、JM、JMR、Mkt Sci）、运营/管理科学 5（MS、OR、JOM、MSOM、POM）、管理 6（AMJ、AMR、ASQ、OrgSci、JIBS、SMJ） | 公开网页（名单为事实性列表） | **内置种子名录**：名单+ISSN 可直接进入公共 venue 库 |
| ft50 | FT50（FT Research Rank 用刊） | Financial Times | **2026-04-29 修订版**（2016 年以来首次修订）：移出 Human Relations、Journal of Business Ethics、Organization Studies，加入 Academy of Management Annals、American Sociological Review、Psychological Science（核验修正；FT 原文 `www.ft.com/ft50-journals` 本环境不可访问，经 USC/McMaster 图书馆指南与学者博客交叉核验 [R69][R86]） | 50 刊（McMaster 图书馆指南列出全表 [R86]）；其中 MIT SMR 2026 年停印转数字版 [R90] | FT 站点付费/不可达；名单被多所图书馆转载（事实性列表），FT 使用条款未取得 | 仍建议"用户自带名录导入"（私有 list）或许可确认后内置；新增的 Psychological Science 交心理学主题统筹 |
| ajg | Academic Journal Guide（原 ABS 名录） | Chartered Association of Business Schools | **AJG 2024**（中期复审：新增刊与指标显著变化刊）；**2027 版**编委与科学委员会已组建；上下文指标由 Elsevier SciVal 提供 [R66] | 分级体系 ⚠ 未核验（公开页面未展示评级表） | 需登录/注册查看；站点 "Copyright © 2024 … All rights reserved" [R66] | 仅用户自带导入；v2 存"用户私有评级"，不做公共再分发 |
| abdc_jql | ABDC Journal Quality List | Australian Business Deans Council | **2025 复审已完成**；公开 xlsx `ABDC-JQL-2025-v3-210926.xlsx`（含 2022/2019/2016/2013/2010 历史 sheet）；2025 与 2022 复审报告 [R67] | A*/A/B/C；按 ANZSRC FoR 码筛选（如 3801 应用经济、3802 计量、3803 经济理论、4609 信息系统、4905 统计）[R67] | 公开下载；网站 "Copyright All Rights Reserved © 2026"，ABDC logo 使用受限 [R67]；站点另声明"唯一有效的可检索 JQL 是 ABDC 自行发布者，其他工具未经 ABDC 授权"（核验补充 [R67]） | 可作"公开可下载名录"导入；**内置再分发前需确认许可** ⚠；FoR 码可作为商科学科路由维度 |
| vhb2024 | VHB-Rating 2024 | 德国商业研究学会（VHB） | 2024-04-18 发布，取代 VHB-JOURQUAL3（2015）（核验补充 [R68]） | 18 个领域评级（Teilratings）+ 科学期刊总目录；官方称因出版媒介异质性不编制总排名 [R68] | 公开网页/PDF（使用许可 ⚠ 未核验） | 用户导入 |
| repec_rank | RePEc/IDEAS 期刊与系列影响因子、排名 | RePEc | getdata 页：期刊与系列影响因子提供"全部年份"与"近十年"两版；IDEAS 另有排名数据 [R20] | 覆盖全部 RePEc 期刊/WP 系列 | 公开 | 经济学"质量信号"补充（尤其非 UTD/FT 覆盖的经济学刊与 WP 系列） |
| econ_top5 / fin_top3 | 经济学 Top 5 / 金融 Top 3（学界约定） | —（约定俗成） | v1 catalog 既有：AER、ECMA、JPE、QJE、REStud；JF、JFE、RFS | 5 / 3 | 无许可问题（约定名单） | 内置标签 |

**名录与数据模型的对接要点**：名录条目应落为 `venue_list(list_id, version, venue_id, rating, field_code, source_url, license_scope)`；`license_scope ∈ {public_builtin, user_private}`；名录→ISSN→Crossref `/journals/{ISSN}` 自动解析平台与 DOI 前缀（§2.8 的做法即是样例），ISSN 在 Crossref 404 的（如 HBR）标记为"无开放元数据通道"。


### 2.8 代表性期刊 / 会议 → 平台映射（Crossref 与 OpenAlex 实测，2026-09-26）

> **口径**：`总 DOI / 当前 DOI` 取 Crossref `/journals/{ISSN}` 的 `counts.total-dois` / `counts.current-dois`；"当前摘要覆盖"取 `coverage.abstracts-current`；"最新出版"为按 `published` 倒序第 1 条；落地主机取该条 `resource.primary.URL` 的主机名（[R70]，107 刊逐一请求）。OA 构成取 OpenAlex `works?filter=primary_location.source.issn:{ISSN},publication_year:2025,type:article&group_by=open_access.oa_status`（[R71]），"OA%"=非 closed 占比（含 green 仓储副本），dia=diamond、hyb=hybrid、grn=green、brz=bronze。平台族判定见 §2.2。"名录"列只标已核验的 UTD24 与学界约定 Top5/Top3。分组按经济（两组）、金融与会计、管理、商业与社会/政治学，每组控制在 15–30 个 venue（社政学为简表）。

#### 经济学 · 综合 / 理论 / 宏观 / 计量（21 个 venue）

| 名称 | ISSN | 出版方 · 落地主机 | 平台族 | Crossref 可枚举性（总 DOI / 当前 DOI · 当前摘要覆盖 · DOI 前缀 · 最新出版） | 2025 年 article 的 OA 构成（OpenAlex，%） | 名录/备注 |
|---|---|---|---|---|---|---|
| American Economic Review | 0002-8282 | AEA · `pubs.aeaweb.org` | Atypon | 5,666 / 360 · 摘要 89% · 前缀 10.1257 · 最新 2026-09-01 | n=118；OA 19%（grn 17 / brz 2） | Econ Top5 |
| Econometrica | 0012-9682 | The Econometric Society · `www.econometricsociety.org` | 自营(CF) | 7,320 / 264 · 摘要 69% · 前缀 10.3982 · 最新 2026 | n=75；OA 59%（hyb 53 / grn 5） | Econ Top5 |
| Journal of Political Economy | 0022-3808 | UChicago Press · `www.journals.uchicago.edu` | Atypon | 15,841 / 381 · 摘要 0% · 前缀 10.1086 · 最新 2026-09-25 | n=117；OA 24%（hyb 3 / grn 15 / brz 7） | Econ Top5 |
| Journal of Political Economy Microeconomics | 2832-9368 | UChicago Press · `www.journals.uchicago.edu` | Atypon | 154（Crossref journals 检索）· 前缀 10.1086 · 最早 2023-02 | ⚠ 未测 | JPE 子刊（2023 创刊） |
| Journal of Political Economy Macroeconomics | 2832-9341 | UChicago Press · `www.journals.uchicago.edu` | Atypon | 94（Crossref journals 检索）· 前缀 10.1086 · 最早 2023-03 | ⚠ 未测 | JPE 子刊（2023 创刊） |
| The Quarterly Journal of Economics | 0033-5533 | OUP · `academic.oup.com` | Silverchair | 6,665 / 149 · 摘要 97% · 前缀 10.1093 · 最新 2026-09-25 | n=53；OA 42%（hyb 32 / grn 9） | Econ Top5 |
| The Review of Economic Studies | 0034-6527 | OUP · `academic.oup.com` | Silverchair | 4,292 / 331 · 摘要 98% · 前缀 10.1093 · 最新 2026-09-22 | n=100；OA 48%（gold 1 / hyb 37 / grn 10） | Econ Top5 |
| American Economic Review Insights | 2640-205X | AEA · `pubs.aeaweb.org` | Atypon | 274 / 101 · 摘要 89% · 前缀 10.1257 · 最新 2026-09-01 | n=34；OA 26%（grn 26） |  |
| AEA Papers and Proceedings | 2574-0768 | AEA · `pubs.aeaweb.org` | Atypon | 1,323 / 452 · 摘要 80% · 前缀 10.1257 · 最新 2026-05-01 | n=150；OA 30%（dia <1 / hyb <1 / grn 11 / brz 17） |  |
| Journal of Economic Literature | 0022-0515 | AEA · `pubs.aeaweb.org` | Atypon | 2,073 / 211 · 摘要 90% · 前缀 10.1257 · 最新 2026-09-01 | n=75；OA 12%（grn 12） |  |
| Journal of the European Economic Association | 1542-4766 | OUP · `academic.oup.com` | Silverchair | 1,713 / 190 · 摘要 97% · 前缀 10.1093 · 最新 2026-09-25 | n=67；OA 43%（hyb 33 / grn 10） |  |
| The Economic Journal | 0013-0133 | OUP · `academic.oup.com` | Silverchair | 19,717 / 383 · 摘要 97% · 前缀 10.1093 · 最新 2026-09-25 | n=129；OA 51%（hyb 34 / grn 16 / brz <1） |  |
| Theoretical Economics | 1933-6837 | The Econometric Society · `www.econometricsociety.org` | 自营(CF) | 735 / 142 · 摘要 85% · 前缀 10.3982 · 最新 2026 | n=38；OA 100%（dia 100） |  |
| Quantitative Economics | 1759-7323 | The Econometric Society · `www.econometricsociety.org` | 自营(CF) | 617 / 114 · 摘要 81% · 前缀 10.3982 · 最新 2026 | n=35；OA 100%（dia 100） |  |
| Journal of Economic Theory | 0022-0531 | Elsevier · `linkinghub.elsevier.com` | ScienceDirect | 6,272 / 332 · 摘要 0% · 前缀 10.1016 · 最新 2026-12 | n=108；OA 66%（hyb 60 / grn 3 / brz 3） |  |
| Games and Economic Behavior | 0899-8256 | Elsevier · `linkinghub.elsevier.com` | ScienceDirect | 4,329 / 451 · 摘要 0% · 前缀 10.1016 · 最新 2026-11 | n=140；OA 60%（hyb 52 / grn 4 / brz 4） |  |
| Journal of Econometrics | 0304-4076 | Elsevier · `linkinghub.elsevier.com` | ScienceDirect | 6,486 / 601 · 摘要 0% · 前缀 10.1016 · 最新 2026-11 | n=159；OA 45%（hyb 37 / grn 6 / brz 1） |  |
| Journal of Monetary Economics | 0304-3932 | Elsevier · `linkinghub.elsevier.com` | ScienceDirect | 4,016 / 318 · 摘要 0% · 前缀 10.1016 · 最新 2026-11 | n=80；OA 48%（dia 2 / hyb 42 / grn 1 / brz 1） |  |
| Review of Economic Dynamics | 1094-2025 | Elsevier · `linkinghub.elsevier.com` | ScienceDirect | 1,405 / 99 · 摘要 0% · 前缀 10.1016 · 最新 2026-11 | n=26；OA 35%（hyb 31 / grn 4） |  |
| American Economic Journal Macroeconomics | 1945-7707 | AEA · `pubs.aeaweb.org` | Atypon | 744 / 144 · 摘要 92% · 前缀 10.1257 · 最新 2026-07-01 | n=31；OA 26%（grn 23 / brz 3） |  |
| American Economic Journal Microeconomics | 1945-7669 | AEA · `pubs.aeaweb.org` | Atypon | 862 / 148 · 摘要 93% · 前缀 10.1257 · 最新 2026-08-01 | n=46；OA 24%（grn 24） |  |

#### 经济学 · 应用 / 领域 / 政策（15 个 venue）

| 名称 | ISSN | 出版方 · 落地主机 | 平台族 | Crossref 可枚举性（总 DOI / 当前 DOI · 当前摘要覆盖 · DOI 前缀 · 最新出版） | 2025 年 article 的 OA 构成（OpenAlex，%） | 名录/备注 |
|---|---|---|---|---|---|---|
| American Economic Journal Applied Economics | 1945-7782 | AEA · `pubs.aeaweb.org` | Atypon | 843 / 149 · 摘要 93% · 前缀 10.1257 · 最新 2026-07-01 | n=30；OA 20%（grn 20） |  |
| American Economic Journal Economic Policy | 1945-7731 | AEA · `pubs.aeaweb.org` | Atypon | 919 / 179 · 摘要 94% · 前缀 10.1257 · 最新 2026-08-01 | n=61；OA 25%（grn 23 / brz 2） |  |
| Journal of Economic Perspectives | 0895-3309 | AEA · `pubs.aeaweb.org` | Atypon | 2,342 / 138 · 摘要 84% · 前缀 10.1257 · 最新 2026-08-01 | n=37；OA 100%（dia 100） |  |
| The Review of Economics and Statistics | 0034-6535 | MIT Press · `direct.mit.edu` | Silverchair | 7,631 / 607 · 摘要 99% · 前缀 10.1162 · 最新 2026-09-08 | n=117；OA 15%（hyb 5 / grn 10） |  |
| International Economic Review | 0020-6598 | Wiley · `onlinelibrary.wiley.com` | Atypon | 3,594 / 233 · 摘要 85% · 前缀 10.1111 · 最新 2026-09-25 | n=79；OA 71%（dia 1 / hyb 48 / grn 4 / brz 18） |  |
| The RAND Journal of Economics | 0741-6261 | Wiley · `onlinelibrary.wiley.com` | Atypon | 1,790 / 132 · 摘要 83% · 前缀 10.1111 · 最新 2026-09-21 | n=50；OA 80%（hyb 64 / grn 2 / brz 14） |  |
| Journal of Public Economics | 0047-2727 | Elsevier · `linkinghub.elsevier.com` | ScienceDirect | 5,457 / 533 · 摘要 0% · 前缀 10.1016 · 最新 2026-11 | n=165；OA 56%（hyb 48 / grn 4 / brz 3） |  |
| Journal of Development Economics | 0304-3878 | Elsevier · `linkinghub.elsevier.com` | ScienceDirect | 4,822 / 636 · 摘要 0% · 前缀 10.1016 · 最新 2027-02 | n=214；OA 50%（gold <1 / hyb 42 / grn 7 / brz <1） |  |
| Journal of International Economics | 0022-1996 | Elsevier · `linkinghub.elsevier.com` | ScienceDirect | 4,222 / 369 · 摘要 0% · 前缀 10.1016 · 最新 2026-12 | n=112；OA 56%（hyb 49 / grn 6 / brz <1） |  |
| Journal of Labor Economics | 0734-306X | UChicago Press · `www.journals.uchicago.edu` | Atypon | 1,923 / 199 · 摘要 0% · 前缀 10.1086 · 最新 2026-07-01 | n=49；OA 8%（grn 8） |  |
| The Journal of Human Resources | 0022-166X | University of Wisconsin Press · `jhr.uwpress.org` | UW Press ⚠ | 2,948 / 156 · 摘要 0% · 前缀 10.3368 · 最新 2026-09-09 | n=56；OA 25%（hyb 21 / grn 4） |  |
| The Journal of Law and Economics | 0022-2186 | UChicago Press · `www.journals.uchicago.edu` | Atypon | 1,989 / 87 · 摘要 0% · 前缀 10.1086 · 最新 2026-08-01 | n=28；OA 11%（grn 11） |  |
| Journal of Economic Growth | 1381-4338 | Springer-Verlag · `link.springer.com` | Springer Oscar | 420 / 31 · 摘要 55% · 前缀 10.1007 · 最新 2026-09-08 | n=13；OA 38%（hyb 31 / grn 8） |  |
| Experimental Economics | 1386-4157 | CUP · `www.cambridge.org` | Cambridge Core | 935 / 117 · 摘要 97% · 前缀 10.1017 · 最新 2026-09-22 | n=60；OA 100%（hyb 100） | 已迁 CUP |
| Brookings Papers on Economic Activity | 0007-2303 | Project MUSE · `www.jstor.org` | JSTOR | 1,214 / 54 · 摘要 54% · 前缀 10.2307 · 最新 1999 | n=21；OA 14%（grn 14） | Crossref 仅至 1999（JSTOR 段），新刊 ⚠ |

#### 金融与会计（27 个 venue）

| 名称 | ISSN | 出版方 · 落地主机 | 平台族 | Crossref 可枚举性（总 DOI / 当前 DOI · 当前摘要覆盖 · DOI 前缀 · 最新出版） | 2025 年 article 的 OA 构成（OpenAlex，%） | 名录/备注 |
|---|---|---|---|---|---|---|
| The Journal of Finance | 0022-1082 | Wiley · `onlinelibrary.wiley.com` | Atypon | 15,494 / 309 · 摘要 73% · 前缀 10.1111 · 最新 2026-10 | n=92；OA 62%（hyb 36 / grn 3 / brz 23） | UTD24、Fin Top3 |
| Journal of Financial Economics | 0304-405X | Elsevier · `linkinghub.elsevier.com` | ScienceDirect | 4,537 / 399 · 摘要 0% · 前缀 10.1016 · 最新 2026-11 | n=140；OA 44%（hyb 38 / grn 4 / brz 2） | UTD24、Fin Top3 |
| Review of Financial Studies | 0893-9454 | OUP · `academic.oup.com` | Silverchair | 3,285 / 294 · 摘要 98% · 前缀 10.1093 · 最新 2026-09-24 | n=103；OA 30%（gold <1 / hyb 24 / grn 3 / brz 2） | UTD24、Fin Top3 |
| Journal of Financial and Quantitative Analysis | 0022-1090 | CUP · `www.cambridge.org` | Cambridge Core | 4,096 / 282 · 摘要 84% · 前缀 10.1017 · 最新 2026-09-24 | n=142；OA 77%（hyb 70 / grn 3 / brz 4） |  |
| Review of Finance | 1572-3097 | OUP · `academic.oup.com` | Silverchair | 1,153 / 138 · 摘要 99% · 前缀 10.1093 · 最新 2026-09-26 | n=15；OA 93%（hyb 60 / grn 33） |  |
| The Review of Asset Pricing Studies | 2045-9920 | OUP · `academic.oup.com` | Silverchair | 271 / 41 · 摘要 98% · 前缀 10.1093 · 最新 2026-09-01 | n=12；OA 42%（hyb 33 / grn 8） |  |
| The Review of Corporate Finance Studies | 2046-9128 | OUP · `academic.oup.com` | Silverchair | 307 / 86 · 摘要 99% · 前缀 10.1093 · 最新 2026-08-31 | n=28；OA 50%（hyb 36 / grn 14） |  |
| Journal of Financial Intermediation | 1042-9573 | Elsevier · `linkinghub.elsevier.com` | ScienceDirect | 1,037 / 89 · 摘要 0% · 前缀 10.1016 · 最新 2026-10 | n=32；OA 47%（hyb 44 / grn 3） |  |
| Journal of Banking & Finance | 0378-4266 | Elsevier · `linkinghub.elsevier.com` | ScienceDirect | 7,534 / 539 · 摘要 0% · 前缀 10.1016 · 最新 2026-11 | n=148；OA 42%（hyb 38 / grn 3 / brz 1） |  |
| Journal of Corporate Finance | 0929-1199 | Elsevier · `linkinghub.elsevier.com` | ScienceDirect | 2,856 / 432 · 摘要 0% · 前缀 10.1016 · 最新 2027-01 | n=146；OA 51%（hyb 43 / grn 8） |  |
| Journal of Financial Markets | 1386-4181 | Elsevier · `linkinghub.elsevier.com` | ScienceDirect | 918 / 128 · 摘要 0% · 前缀 10.1016 · 最新 2026-09 | n=45；OA 42%（hyb 40 / grn 2） |  |
| Journal of Empirical Finance | 0927-5398 | Elsevier · `linkinghub.elsevier.com` | ScienceDirect | 1,870 / 234 · 摘要 0% · 前缀 10.1016 · 最新 2026-11 | n=66；OA 27%（hyb 23 / grn 5） |  |
| Journal of Financial Econometrics | 1479-8409 | OUP · `academic.oup.com` | Silverchair | 701 / 78 · 摘要 97% · 前缀 10.1093 · 最新 2026 | n=27；OA 37%（hyb 30 / grn 7） |  |
| Mathematical Finance | 0960-1627 | Wiley · `onlinelibrary.wiley.com` | Atypon | 1,264 / 118 · 摘要 78% · 前缀 10.1111 · 最新 2026-10 | n=34；OA 76%（hyb 68 / brz 9） |  |
| Finance and Stochastics | 0949-2984 | Springer-Verlag · `link.springer.com` | Springer Oscar | 831 / 79 · 摘要 54% · 前缀 10.1007 · 最新 2026-09-18 | n=29；OA 55%（hyb 52 / grn 3） |  |
| Quantitative Finance | 1469-7688 | Taylor & Francis · `www.tandfonline.com` | Atypon | 3,040 / 300 · 摘要 0% · 前缀 10.1080 · 最新 2026-09-21 | n=104；OA 47%（hyb 36 / grn 10 / brz 2） |  |
| Financial Management | 0046-3892 | Wiley · `onlinelibrary.wiley.com` | Atypon | 2,158 / 148 · 摘要 78% · 前缀 10.1111 · 最新 2026-09-06 | n=41；OA 71%（hyb 44 / grn 2 / brz 24） |  |
| Journal of money credit and banking | 0022-2879 | Wiley · `onlinelibrary.wiley.com` | Atypon | 4,560 / 256 · 摘要 76% · 前缀 10.1111 · 最新 2026-09-18 | n=54；OA 52%（hyb 39 / grn 2 / brz 11） |  |
| Annual Review of Financial Economics | 1941-1367 | Annual Reviews · `www.annualreviews.org` | Ingenta Edify（SNIPPET 级确认 [R89]） | 361 / 65 · 摘要 95% · 前缀 10.1146 · 最新 2026-09-15 | n=1；OA 100%（grn 100） | OpenAlex 多将综述记为 review，article 样本过小 |
| Critical Finance Review | 2164-5744 | Emerald (MCB UP) · `www.emerald.com` | Silverchair（Emerald 2025-07 上线 [R83]） | 183 / 50 · 摘要 28% · 前缀 10.1108 · 最新 2026-07-27 | n=22；OA 23%（hyb 14 / grn 9） | 原 now publishers（2025-05 被 Emerald 收购），现 Emerald（2026-06 Emerald 被 Wiley 收购）[R87] |
| The Journal of Portfolio Management | 0095-4918 | With Intelligence LLC · `pm-research.com` | ⚠ | 3,646 / 373 · 摘要 0% · 前缀 10.3905 · 最新 2026-09-26 | n=114；OA 3%（grn 3） | 出版者现为 With Intelligence |
| Journal of Accounting and Economics | 0165-4101 | Elsevier · `linkinghub.elsevier.com` | ScienceDirect | 1,871 / 217 · 摘要 0% · 前缀 10.1016 · 最新 2026-11 | n=49；OA 39%（hyb 33 / grn 6） | UTD24 |
| Journal of Accounting Research | 0021-8456 | Wiley · `onlinelibrary.wiley.com` | Atypon | 2,805 / 209 · 摘要 70% · 前缀 10.1111 · 最新 2026-09-20 | n=56；OA 57%（hyb 45 / brz 12） | UTD24 |
| The Accounting Review | 0001-4826 | American Accounting Association · `publications.aaahq.org` | Silverchair（2022-12 上线 [R83]） | 11,750 / 328 · 摘要 91% · 前缀 10.2308 · 最新 2026-09-01 | n=89；OA 73%（hyb 4 / grn 8 / brz 61） | UTD24 |
| Contemporary Accounting Research | 0823-9150 | Wiley · `onlinelibrary.wiley.com` | Atypon | 2,468 / 259 · 摘要 90% · 前缀 10.1111 · 最新 2026-09-22 | n=94；OA 73%（hyb 52 / grn 5 / brz 16） |  |
| Review of Accounting Studies | 1380-6653 | Springer-Verlag · `link.springer.com` | Springer Oscar | 1,198 / 178 · 摘要 61% · 前缀 10.1007 · 最新 2026-09-25 | n=57；OA 81%（hyb 79 / grn 2） |  |
| Accounting Organizations and Society | 0361-3682 | Elsevier · `linkinghub.elsevier.com` | ScienceDirect | 2,222 / 107 · 摘要 0% · 前缀 10.1016 · 最新 2026-12 | n=27；OA 63%（hyb 59 / grn 4） |  |

#### 管理（战略 / 组织 / 创业 / 人力 / 国际商务）（26 个 venue）

| 名称 | ISSN | 出版方 · 落地主机 | 平台族 | Crossref 可枚举性（总 DOI / 当前 DOI · 当前摘要覆盖 · DOI 前缀 · 最新出版） | 2025 年 article 的 OA 构成（OpenAlex，%） | 名录/备注 |
|---|---|---|---|---|---|---|
| Academy of Management Journal | 0001-4273 | Academy of Management · `journals.aom.org` | Atypon | 4,520 / 197 · 摘要 0% · 前缀 10.5465 · 最新 2026-09-15 | n=59；OA 17%（grn 15 / brz 2） | UTD24 |
| Academy of Management Review | 0363-7425 | Academy of Management · `journals.aom.org` | Atypon | 4,398 / 226 · 摘要 0% · 前缀 10.5465 · 最新 2026-09-15 | n=50；OA 10%（grn 10） | UTD24 |
| Academy of Management Annals | 1941-6520 | Academy of Management · `journals.aom.org` | Atypon | 393 / 71 · 摘要 0% · 前缀 10.5465 · 最新 2026-08-10 | n=26；OA 46%（grn 42 / brz 4） |  |
| Academy of Management Perspectives | 1558-9080 | Academy of Management · `journals.aom.org` | Atypon | 2,425 / 132 · 摘要 0% · 前缀 10.5465 · 最新 2026-09-22 | n=51；OA 22%（grn 22） |  |
| Academy of Management Learning and Education | 1537-260X | Academy of Management · `journals.aom.org` | Atypon | 1,550 / 143 · 摘要 0% · 前缀 10.5465 · 最新 2026-09-16 | n=43；OA 30%（hyb 2 / grn 26 / brz 2） |  |
| Academy of Management Discoveries | 2168-1007 | Academy of Management · `journals.aom.org` | Atypon | 411 / 117 · 摘要 0% · 前缀 10.5465 · 最新 2026-09-22 | n=29；OA 17%（grn 17） |  |
| Academy of Management Proceedings | 0065-0668 | Academy of Management · `journals.aom.org` | Atypon | 69,864 / 16,766 · 摘要 0% · 前缀 10.5465 · 最新 2026-07 | ⚠ 无数据 | 会议论文集（摘要/简版） |
| Administrative Science Quarterly | 0001-8392 | SAGE Publications · `journals.sagepub.com` | Atypon | 4,309 / 168 · 摘要 39% · 前缀 10.1177 · 最新 2026-09-25 | n=38；OA 47%（hyb 39 / grn 3 / brz 5） | UTD24 |
| Organization Science | 1047-7039 | INFORMS · `pubsonline.informs.org` | Atypon | 2,628 / 339 · 摘要 95% · 前缀 10.1287 · 最新 2026-09-25 | n=82；OA 21%（gold 2 / grn 15 / brz 4） | UTD24 |
| Strategic Management Journal | 0143-2095 | Wiley · `sms.onlinelibrary.wiley.com` | Atypon | 4,411 / 344 · 摘要 78% · 前缀 10.1002 · 最新 2026-10 | n=101；OA 84%（hyb 78 / grn <1 / brz 5） | UTD24 |
| Strategic Entrepreneurship Journal | 1932-4391 | Wiley · `sms.onlinelibrary.wiley.com` | Atypon | 669 / 116 · 摘要 80% · 前缀 10.1002 · 最新 2026-09-21 | n=32；OA 78%（hyb 66 / grn 3 / brz 9） |  |
| Global Strategy Journal | 2042-5791 | Wiley · `sms.onlinelibrary.wiley.com` | Atypon | 532 / 76 · 摘要 71% · 前缀 10.1002 · 最新 2026-09-17 | n=16；OA 75%（hyb 56 / brz 19） |  |
| Journal of International Business Studies | 0047-2506 | Springer Nature（Palgrave）· `link.springer.com` | Springer Oscar | 3,321 / 236 · 摘要 36% · 前缀 10.1057 · 最新 created 2026-09-23 | n=66；OA 61%（hyb 48 / grn 3 / brz 9） | UTD24 |
| Journal of Management | 0149-2063 | SAGE Publications · `journals.sagepub.com` | Atypon | 3,259 / 273 · 摘要 99% · 前缀 10.1177 · 最新 2026-09-22 | n=91；OA 66%（hyb 47 / grn 10 / brz 9） |  |
| Journal of Management Studies | 0022-2380 | Wiley · `onlinelibrary.wiley.com` | Atypon | 3,763 / 442 · 摘要 78% · 前缀 10.1111 · 最新 2026-09-25 | n=147；OA 86%（hyb 78 / grn 4 / brz 5） |  |
| Organization Studies | 0170-8406 | SAGE Publications · `journals.sagepub.com` | Atypon | 4,227 / 284 · 摘要 69% · 前缀 10.1177 · 最新 2026-09-08 | n=75；OA 73%（gold 1 / hyb 59 / grn 8 / brz 5） |  |
| Human Relations | 0018-7267 | SAGE Publications · `journals.sagepub.com` | Atypon | 4,901 / 156 · 摘要 88% · 前缀 10.1177 · 最新 2026-09-15 | n=52；OA 69%（hyb 48 / grn 10 / brz 12） |  |
| Journal of Applied Psychology | 0021-9010 | American Psychological Association · `doi.apa.org` | APA PsycNet | 12,593 / 375 · 摘要 0% · 前缀 10.1037 · 最新 2026-09-24 | n=78；OA 21%（hyb 12 / grn 9） |  |
| Organizational Behavior and Human Decision Processes | 0749-5978 | Elsevier · `linkinghub.elsevier.com` | ScienceDirect | 2,624 / 106 · 摘要 0% · 前缀 10.1016 · 最新 2026-11 | n=23；OA 48%（hyb 43 / grn 4） |  |
| Journal of Business Venturing | 0883-9026 | Elsevier · `linkinghub.elsevier.com` | ScienceDirect | 1,773 / 183 · 摘要 0% · 前缀 10.1016 · 最新 2027-01 | n=46；OA 83%（hyb 78 / grn 4） |  |
| Entrepreneurship Theory and Practice | 1042-2587 | SAGE Publications · `journals.sagepub.com` | Atypon | 1,877 / 155 · 摘要 99% · 前缀 10.1177 · 最新 2026-09-23 | n=48；OA 46%（hyb 31 / grn 15） |  |
| Research Policy | 0048-7333 | Elsevier · `linkinghub.elsevier.com` | ScienceDirect | 5,262 / 539 · 摘要 0% · 前缀 10.1016 · 最新 2026-12 | n=152；OA 78%（hyb 74 / grn 3 / brz <1） |  |
| Journal of Business Ethics | 0167-4544 | Springer-Verlag · `link.springer.com` | Springer Oscar | 10,649 / 888 · 摘要 43% · 前缀 10.1007 · 最新 2026-09-25 | n=313；OA 50%（hyb 44 / grn 5 / brz <1） |  |
| Human Resource Management | 0090-4848 | Wiley · `onlinelibrary.wiley.com` | Atypon | 3,242 / 248 · 摘要 85% · 前缀 10.1002 · 最新 2026-09-20 | n=91；OA 73%（hyb 62 / grn 1 / brz 10） |  |
| Harvard Business Review | — | — | — | Crossref 无此 ISSN（404） | — | FT50 实务刊；无 DOI |
| MIT Sloan Management Review | 1532-9194 | MIT Sloan School of Management · `sloanreview.mit.edu` | 自研 | 135 / 93 · 摘要 100% · 前缀 10.63383 · 最新 2026-06-02 | n=37；OA 11%（grn 11） | 新前缀 10.63383；FT50 成员；2026 秋季刊后停印、冬季转纯数字版 [R90] |

#### 商业（营销 / 信息系统 / 运营与管理科学）（15 个 venue）

| 名称 | ISSN | 出版方 · 落地主机 | 平台族 | Crossref 可枚举性（总 DOI / 当前 DOI · 当前摘要覆盖 · DOI 前缀 · 最新出版） | 2025 年 article 的 OA 构成（OpenAlex，%） | 名录/备注 |
|---|---|---|---|---|---|---|
| Management Science | 0025-1909 | INFORMS · `pubsonline.informs.org` | Atypon | 12,478 / 1,650 · 摘要 97% · 前缀 10.1287 · 最新 2026-09-25 | n=502；OA 18%（hyb <1 / grn 16 / brz 2） | UTD24 |
| Marketing Science | 0732-2399 | INFORMS · `pubsonline.informs.org` | Atypon | 2,290 / 253 · 摘要 85% · 前缀 10.1287 · 最新 2026-09-25 | n=64；OA 9%（grn 8 / brz 2） | UTD24 |
| Journal of Marketing | 0022-2429 | SAGE Publications · `journals.sagepub.com` | Atypon | 12,018 / 197 · 摘要 95% · 前缀 10.1177 · 最新 2026-09-18 | n=67；OA 57%（hyb 43 / grn 9 / brz 4） | UTD24 |
| Journal of Marketing Research | 0022-2437 | SAGE Publications · `journals.sagepub.com` | Atypon | 7,592 / 153 · 摘要 98% · 前缀 10.1177 · 最新 2026-09-23 | n=60；OA 40%（hyb 30 / grn 7 / brz 3） | UTD24 |
| Journal of Consumer Research | 0093-5301 | OUP · `academic.oup.com` | Silverchair | 3,427 / 195 · 摘要 90% · 前缀 10.1093 · 最新 2026-09-18 | n=70；OA 44%（hyb 40 / grn 1 / brz 3） | UTD24 |
| Journal of the Academy of Marketing Science | 0092-0703 | Springer-Verlag · `link.springer.com` | Springer Oscar | 3,608 / 211 · 摘要 48% · 前缀 10.1007 · 最新 2026-09-23 | n=48；OA 56%（hyb 44 / grn 6 / brz 6） |  |
| Journal of Consumer Psychology | 1057-7408 | Wiley · `myscp.onlinelibrary.wiley.com` | Atypon | 1,880 / 120 · 摘要 78% · 前缀 10.1002 · 最新 2026-10 | n=36；OA 58%（hyb 47 / brz 11） |  |
| Information Systems Research | 1047-7047 | INFORMS · `pubsonline.informs.org` | Atypon | 1,966 / 450 · 摘要 93% · 前缀 10.1287 · 最新 2026-09-25 | n=126；OA 11%（grn 11） | UTD24 |
| MIS Quarterly | 0276-7783 | MIS Quarterly · `misq.umn.edu` | Silverchair（2025-08 上线 [R83]） | 2,264 / 221 · 摘要 90% · 前缀 10.25300 · 最新 2026-09-01 | n=63；OA 19%（hyb 11 / grn 5 / brz 3） | UTD24 |
| Journal of Management Information Systems | 0742-1222 | Taylor & Francis · `www.tandfonline.com` | Atypon | 1,801 / 124 · 摘要 0% · 前缀 10.1080 · 最新 2026-09-09 | n=41；OA 41%（hyb 37 / brz 5） |  |
| INFORMS Journal on Computing | 1091-9856 | INFORMS · `pubsonline.informs.org` | Atypon | 2,656 / 656 · 摘要 95% · 前缀 10.1287 · 最新 2026-09-21 | n=202；OA 6%（hyb <1 / grn 5） | UTD24 |
| Journal of Operations Management | 0272-6963 | Wiley · `onlinelibrary.wiley.com` | Atypon | 2,436 / 179 · 摘要 64% · 前缀 10.1002 · 最新 2026-09 | n=55；OA 71%（hyb 51 / brz 20） | UTD24 |
| Manufacturing & Service Operations Management | 1523-4614 | INFORMS · `pubsonline.informs.org` | Atypon | 1,800 / 440 · 摘要 95% · 前缀 10.1287 · 最新 2026-09-25 | n=131；OA 9%（hyb <1 / grn 8） | UTD24 |
| Production and Operations Management | 1059-1478 | SAGE Publications · `journals.sagepub.com` | Atypon | 3,929 / 675 · 摘要 99% · 前缀 10.1177 · 最新 2026-09-23 | n=221；OA 28%（hyb 21 / grn 6） | UTD24 |
| Operations Research | 0030-364X | INFORMS · `pubsonline.informs.org` | Atypon | 7,922 / 559 · 摘要 93% · 前缀 10.1287 · 最新 2026-09-24 | n=141；OA 16%（gold <1 / hyb <1 / grn 15） | UTD24 |

#### 社会学与政治学（简）（5 个 venue）

| 名称 | ISSN | 出版方 · 落地主机 | 平台族 | Crossref 可枚举性（总 DOI / 当前 DOI · 当前摘要覆盖 · DOI 前缀 · 最新出版） | 2025 年 article 的 OA 构成（OpenAlex，%） | 名录/备注 |
|---|---|---|---|---|---|---|
| American Sociological Review | 0003-1224 | SAGE Publications · `journals.sagepub.com` | Atypon | 13,231 / 107 · 摘要 94% · 前缀 10.1177 · 最新 2026-09-24 | n=38；OA 39%（hyb 26 / brz 13） |  |
| American Journal of Sociology | 0002-9602 | UChicago Press · `www.journals.uchicago.edu` | Atypon | 27,765 / 335 · 摘要 0% · 前缀 10.1086 · 最新 2026-09-03 | n=36；OA 11%（grn 8 / brz 3） |  |
| American Political Science Review | 0003-0554 | CUP · `www.cambridge.org` | Cambridge Core | 32,370 / 299 · 摘要 83% · 前缀 10.1017 · 最新 2026-09-25 | n=88；OA 91%（hyb 81 / brz 10） |  |
| American Journal of Political Science | 0092-5853 | Wiley · `onlinelibrary.wiley.com` | Atypon | 3,401 / 265 · 摘要 90% · 前缀 10.1111 · 最新 2026-09-22 | n=82；OA 84%（hyb 66 / grn 1 / brz 17） |  |
| The Journal of Politics | 0022-3816 | UChicago Press · `www.journals.uchicago.edu` | Atypon | 12,432 / 528 · 摘要 0% · 前缀 10.1086 · 最新 2026-10-01 | n=168；OA 7%（grn 7） |  |

**从映射表可直接读出的设计事实**：
- **Crossref 可枚举性**：107 个 ISSN 中 106 个在 Crossref 可按 ISSN 枚举（例外 HBR 无记录；BPEA 仅覆盖至 1999 年 JSTOR 段）；各刊最新出版日期均在 2026-09 前后（Elsevier 的 `published` 已排到 2026-11 至 2027-02，即"在线先行+卷期日期"），说明 Crossref 足以承担"最新论文"。
- **摘要覆盖分四档**：高（≥90%：OUP、MIT、AAA、MISQ，以及 INFORMS/SAGE/AEA 的多数刊）；中（50–89%：Wiley、CUP 的 JFQA/APSR、Econometric Society、Springer 的 JEG/F&S/RAST）；低（<50%：JIBS 36%、JBE 43%、JAMS 48%、ASQ 39%、CFR 28%）；零（Elsevier 实测 19 刊全部、AOM 7 项全部（含 Proceedings）、UChicago 实测 5 刊全部、T&F 的 QF/JMIS、JHR、JAP、JPM）。零档刊的新文在 OpenAlex 中也常缺摘要（2026-09 抽样：JFE、JET、AMJ、QF、ASQ 均缺；AMJ 2025 抽样 23/25 已补齐，JFE 2024 抽样仅 10/25）[R77]。
- **全文/TDM 链接登记差异**（Crossref `coverage.resource-links-current`）：Elsevier、Springer、SAGE 实测刊均为 100%，Wiley 29–56%，T&F 15–19%，CUP 0–39%，OUP/INFORMS/AOM/AEA/UChicago/AAA 均为 0% [R70] → 可用 Crossref `link[]` 作为"出版商官方全文/TDM 端点"的发现线索，但**链接存在 ≠ 有权访问**（v1 metadata-apis.md 同结论），entitlement 仍以用户凭证实测为准。
- **OA 结构差异**：学会自营/OA 刊（JEP、TE、QE 为 diamond 100%）；Wiley/Elsevier/SAGE/CUP 的 hybrid 占比普遍 30–80%（如 SMJ 78%、JMS 78%、Research Policy 74%、JFQA 70%）；**INFORMS 与 AOM 几乎无 hybrid**（MS/ISR/MSOM/IJOC 的 OA 主要是 green 副本，AMR 10%）→ 这两家的"可读全文"主要依赖用户订阅或作者自存版。

### 2.9 会议论文获取形态（经济 / 金融 / 管理）

| 形态 | 代表 | 可自动化获取的内容 | 结论 |
|---|---|---|---|
| **公开程序 + 摘要 + 部分 PDF** | ASSA（含 AFA 分会场）[R61] | session（标题、JEL、主办学会、时间地点）、论文（作者、机构、摘要），部分作者上传 PDF | 可作 L1 会议源：产出"会议报告"事件与 JEL 标签；PDF 仅对作者公开上传者按需取 |
| **会议页 + 议程，论文多为本机构 WP** | NBER SI 及各类会议 [R64] | 分会列表、议程（conference.nber.org）、指向 `w{n}` 的链接 | 复用 `nber`：把 WP 打上"在 SI-2026-AP 报告"标签 |
| **程序在会员登录后** | WFA [R62] | 无（登录墙） | 不自动化；论文经 SSRN 版本出现 |
| **程序公开但论文路径 robots 禁** | SFS Cavalcade [R63] | 程序 HTML（⚠ 结构未测） | 全文排除；最多做会议标签 |
| **论文集入 Crossref** | AOM Annual Meeting Proceedings [R70] | 69,864 条 DOI（摘要级/简版） | 用 Crossref 枚举；作为作者兴趣与"新方向"信号 |
| **仓储型、OAI 被 robots 禁** | ICIS（AIS eLibrary）[R76] | 无（除非另获许可） | P2；可待许可或走 Crossref（有 DOI 部分） |
| **未核验** | EFA、SED、Econometric Society 各区域会议、SMS、Marketing Science Conference | ⚠ | 列入后续勘察 |

另：SSRN 的"付费 Conference Proceedings"产品随商业线于 2026-12-31 前关停 [R2]，以 SSRN 为载体的会议论文集入口将消失；金融会议论文的公开全文几乎都以 SSRN/作者主页预印本存在 → v2 中"会议"更适合作为**论文的属性/事件**（presented_at），而不是独立全文源。

## 3. 对 v2 设计的启示

1. **"发现/最新"层与出版社站点彻底解耦**：期刊与有 DOI 的 WP 系列一律以 Crossref 为主干（按 ISSN 或 DOI 前缀），"最新论文"用 `from-created-date`（新 DOI）+ `from-index-date`（元数据变更）两条增量流驱动；**不轮询出版社 RSS/eTOC**（Atypon 的 `/action`、`/rss` 与 `rss.sciencedirect.com` 均被 robots 禁止，§2.2）。例外清单只含合规的官方通道：Fed RSS、ECB RSS、BIS CB-RSS、World Bank D&R API、NBER back.nber.org RSS（Crawl-delay 10）。
2. **限速是"平台级共享账本"，不是"每用户叠加"**：多用户后台对同一来源的请求必须汇入同一个 (source, host) 令牌桶。依据：Crossref 公共池实测 1 req/s·并发 1、polite 池 10/3（需平台运营者 mailto）[R27][R28]；Springer Nature 明禁"多账号/多 key 规避限额"[R39]；NBER back、World Bank OKR、OSF、FRASER Crawl-delay 10，ECB 5，HBS 2，Atypon 族 1 [R12][R49][R53][R57][R60][R74]。用户查询优先命中本地库，冷数据才回源。
3. **摘要补齐链 + 摘要版权分级**：Crossref 摘要覆盖率按出版商呈"四档"（§2.8），Elsevier/AOM/UChicago/T&F 部分刊为 0，且 OpenAlex 对这些新文常同样缺失 [R70][R77] → 补齐链建议 Crossref → OpenAlex（滞后补）→ RePEc/NBER 批量文件（WP）→ 用户会话内的出版社页面/API（仅该用户可见）。每条摘要存 `abstract_source` 与 `abstract_rights ∈ {cc, publisher_deposited, personal_use_only, unknown}`；Crossref 明示"部分摘要可能受版权保护"[R26]、Springer 摘要"仅限个人非商业使用"[R39]，多用户公共卡片对 `personal_use_only` 摘要应降级为"要点/标题级"展示或只对本人显示（见 §4-6）。
4. **SSRN = 元数据-only + 外链**：Crossref `10.2139` 已能当日提供新 DOI、91% 带摘要 [R1]，足以支撑"SSRN 最新 WP"信息流；而 ToU 明禁任何自动化查询 [R5] → v2 删除 v1 的浏览器 opt-in 全文模式 B（D-029/D-030 需以新 ADR 取代），全文只提供"在 SSRN 打开"外链。另需跟踪 2026 商业线关停后的平台改造（landing URL、DOI 解析、免费 Research Alert 是否提供机器可读订阅）[R2]。**核验补充**：SSRN 自 2026-07 起在 Crossref 登记 license（含 CC BY 等）[R1][R91]，应入库为 `license`；CC 许可放宽的是"合法取得后"的再利用边界，并不解除 ToU 对自动化查询的禁止，故仍只外链（用户自行下载的 CC 论文能否进入平台级缓存，见 §4-16）。
5. **"工作论文 ↔ 正式发表版"版本图谱以 RePEc/NBER 为主证据**：SSRN 的 Crossref `is-preprint-of` 关系 2026 年仅 266/226k [R1]；NBER 元数据 `published.tsv` 与 RePEc "Published in" 是更强的策展信号 [R10][R20] → 延续 D-007 的 `preprint_of` 边，但证据源优先级改为 RePEc/NBER > Crossref relation > 标题/作者模糊匹配（候审）。
6. **学科路由三主轴**：经济/金融用 **JEL**（RePEc、NBER jel.tsv、ASSA session 码）；商科用 **ABDC FoR 码 + UTD 学科分组**；德语区/欧洲经管 WP 可借 **EconBiz STW 词表**。这为多来源路由与用户兴趣建模提供了"来源无关"的统一标签层（OpenAlex topic 作兜底）。
7. **全文三档门控与多用户隔离**：
   - OA（CC 许可，含 diamond 刊 JEP/TE/QE、SocArXiv；央行/国际组织 WP 须逐源确认许可，见 §4-15）：可平台级缓存，但须按 license 条件（NC/ND）限制派生用途；
   - 订阅（Elsevier API、Wiley TDM、INFORMS/AOM/SAGE/OUP/CUP/UChicago/AAA/MISQ 会话）：**每用户凭证、每用户私有存储、零共享、零预取**——Springer 要求 TDM 内容仅存"机构内部服务器、不得第三方访问"[R39]，Elsevier 仅限订阅机构研究者非商业 TDM、API key 不得转让或披露给他人、TDM 输出片段 ≤200 字符 [R23][R81]；
   - ToU/robots 禁止自动化（SSRN、SFS accepted papers、MPRA OAI、OKR OAI、api.osf.io）：只外链，不入全文队列。
8. **平台族基类 + 会话内按需取回**：Atypon（17 刊）与 Silverchair（4 刊：RFS、JCR、TAR、MISQ；AAA 与 MISQ 的平台归属已由 Silverchair 公告确认 [R83]）两族合计覆盖 UTD24 的 21/24（其余为 ScienceDirect 的 JAE/JFE 与 Springer 的 JIBS，§2.8）→ adapter 以族基类实现"DOI→落地页/PDF 规则、挑战页识别、登录态探针"，各刊只写 VenueSpec；但取回动作只在用户显式请求且持有有效会话时执行（沿用 D-006/D-014 的"遇挑战即 BLOCKED"）。
9. **源名录（source registry）新增合规字段**：`tos_automation ∈ {allowed, api_only, user_initiated_only, forbidden}`、`ai_bot_sensitivity`（robots 是否具名封禁 AI UA，如 Springer/MPRA/Elsevier/JSTOR/econsoc；INFORMS 对 AI UA 禁全文路径）、`crawl_delay_s`、`api_quota`、`tdm_policy_url`、`tdmrep`（Springer reservation=1）、`verified_at`；v2 policy engine 据此自动决定"是否允许后台抓取/预取"。
10. **名录体系分"公共内置"与"用户私有"两层**：UTD24、学界 Top5/Top3 可内置；ABDC 2025 公开可下但站点声明版权所有，且明示第三方可检索版本未经授权 [R67]，内置前需许可确认；AJG（需登录、版权所有）与 FT50（2026-04-29 修订版名单已经二手来源核验 [R86]，FT 原文与使用条款未取得）只做"用户自带名录导入"，存为用户私有 list，不进入公共库 [R65][R66][R67][R69]。名录条目需带 `version`（如 FT50 分 2016 与 2026 两版），venue 需有 `status ∈ {active, ceased, transformed}`（如 MIT SMR 转纯数字版 [R90]）。
11. **会议 = 论文的属性/事件，而非独立全文源**：ASSA（含 AFA）是唯一高结构化公开程序，可产出 `presented_at` 事件与 JEL；NBER SI 复用 nber 适配器打标签；WFA（登录墙）、SFS（robots 禁 accepted paper）只经 SSRN 版本关联 [R61][R62][R63][R64]。
12. **央行/国际组织 WP 用官方通道，ECB 例外需特别处理**：Fed（Crossref 10.17016 + RSS，摘要 99%）、BIS（CB-RSS）、World Bank（D&R API v3，11,380 PRWP）均合规；**ECB 的 DOI 由欧盟出版局 RA（OP）登记、不在 Crossref**[R79]，只能靠其 RSS/RePEc；IMF 在 Crossref 中混有大量 component/chapter 记录，需按 container（"IMF Working Papers"）或 DOI 形态过滤 [R78]；BIS 的 CB-RSS 字段可抽象为通用 `cbrss` 解析器（其他央行采用情况 ⚠ 待核）。
13. **新文"摘要待补"的卡片降级**：对摘要缺失的新文（Elsevier/AOM/T&F 等），卡片流应以"标题 + 期刊 + 作者 + JEL/主题标签"先上屏，并在补齐后刷新；推荐模型的冷启动特征不能强依赖摘要。
14. **政策漂移监测做成定时任务**：本主题 2 个月内即出现 SSRN 商业线关停、CEPR robots 改写、Cambridge robots 上 CF、INFORMS/Springer 可达性变化、Crossref 公共池降速、ScienceDirect robots 放行 Claude-User 等漂移（§2.1），核验阶段又发现 FT50 修订（2026-04）、Wiley 收购 Emerald（2026-06）、SSRN 许可选择（2026-07）、MIT SMR 停印（2026-09）与 OpenAlex 改为 key + 按量计费（2026）[R86][R87][R91][R90][R93] → v2 需"源健康/政策探针"（robots 哈希、ToS 页哈希、tdmrep、挑战率、API 头配额），漂移即告警并自动降级到"仅元数据"。
15. **数据模型新增 `series` 与标识符方案**：WP 系列（NBER w、FEDS、IFDP、ECB WP、BIS WP、IMF WP、WB PRWP、IZA DP、CEPR DP、HBS WP）应为一等实体（发行机构、编号规则、DOI 前缀/RA、元数据通道）；标识符新增 `wb_repnb`（WPS 号）、`iza_dp`、`cepr_dp`、`ecb_wp`、`bis_wp`、`imf_wp`、`repec_handle`（沿用 D-035）、`ssrn_id`（已有）。

**源名录条目示例（设计伪代码，非实现；字段取值来自本文实测）**：

```yaml
# 设计伪代码：v2 source registry 条目（供设计阶段合并总名录时参考）
- source_id: informs_pubsonline
  tier_type: L1-journal-platform
  disciplines: [management_science, marketing, information_systems, operations, organization]
  platform_family: atypon
  metadata_channel: {kind: crossref_issn, doi_prefix: "10.1287"}
  latest_channel: {kind: crossref_incremental, filters: [from-created-date, from-index-date]}
  fulltext_gate: subscription            # 用户会话内按需单篇；不预取、不共享
  auth_kinds: [institutional_sso, member_login]
  tos_automation: user_initiated_only    # PubsOnLine T&C（摘要级）：未经批准禁止系统性下载，离线浏览 ≤20 页/分钟
  ai_bot_sensitivity: fulltext_paths_blocked_for_ai_uas   # robots 对 GPTBot/anthropic-ai 等禁 /doi/full、/doi/pdf、/doi/epdf
  crawl_delay_s: 1
  tdmrep: none                           # /.well-known/tdmrep.json 404
  verified_at: 2026-09-26
- source_id: ecb_wp
  tier_type: L1-preprint
  metadata_channel: {kind: rss, url: "https://www.ecb.europa.eu/rss/wppub.html", doi_ra: OP}   # 不在 Crossref
  latest_channel: {kind: rss_poll, min_interval_s: 5}
  fulltext_gate: open_pdf                # 平台级缓存前需确认许可（§4-15）
  tos_automation: allowed
  crawl_delay_s: 5
  verified_at: 2026-09-26
- source_id: ssrn
  tier_type: L1-preprint
  metadata_channel: {kind: crossref_prefix, doi_prefix: "10.2139"}
  latest_channel: {kind: crossref_incremental, filters: [from-created-date]}
  fulltext_gate: link_out_only           # ToU 禁止任何自动化查询
  tos_automation: forbidden
  verified_at: 2026-09-26
```

### 3.1 接口对接优先级建议（汇总）

| 优先级 | 来源（source_id） | 对接方式 | 理由 |
|---|---|---|---|
| **P0** | crossref（主干）、ssrn（元数据）、nber_wp、aea_journals、econsoc_journals、elsevier_sd、wiley_wol、oup_academic、repec（enrich）、arxiv_econ_qfin | v1 已有，v2 迁入多用户架构；SSRN 删除模式 B | 已实现且覆盖经济金融 Top 刊与 WP 主体 |
| **P0（新增）** | informs_pubsonline、aom_journals | Crossref 元数据 + Atypon 族基类（用户会话按需取回） | UTD24 中 9 刊（INFORMS 7 + AOM 2），商科杠杆最大 |
| **P1** | sage_journals、springer_link、tandf_online、cup_core、uchicago_journals、aaa_pubs、misq、fed_board_wp、ecb_wp、bis_wp、imf_wp、worldbank_prwp、iza_dp、socarxiv、econstor、econbiz、assa_meetings、nber_conferences | 元数据走 Crossref/官方 RSS/API/OAI；全文按许可分档 | 补齐 UTD24 余下刊、FT50 常见刊与政策类 WP |
| **P2** | emerald_insight、annual_reviews、mit_press_direct（按需单篇）、pm_research、degruyter_brill、apa_psycnet、hbs_wp、mpra、cesifo_wp、aom_proceedings、ais_icis、sed/efa、fraser、other_cb_wp、mit_smr（2026 停印转数字，观望） | 以 Crossref/RePEc 元数据为主 | 覆盖面补充，价值/成本比低或合规面受限 |
| **仅元数据 / 排除** | cepr_dp（仅元数据）、jstor（仅元数据）、wfa_meeting、sfs_cavalcade（全文排除）、hbp_hbr（无 DOI，排除）、informs_annual（排除） | — | 订阅墙、登录墙、robots 禁或无开放元数据 |

## 4. 未决问题与风险

1. **SSRN 原文不可达**：SSRN ToU 与 2026-04-13 战略公告均因本环境 TLS 阻断只取得搜索摘要（[R2][R5] SNIPPET）；需在可达网络逐字复核 ToU 自动化条款、robots（v1 记录为禁 GPTBot 等 + crawl-delay 5）与商业线关停后的平台路线图。若 ToU 措辞与摘要不符，§3 第 4、7 条结论需回调。
2. **SSRN 平台改造风险**：商业线关停后的改造（以及 2016 年即宣布、至今未见完成证据的 Mendeley 平台整合 [R82]）可能改变 landing URL 与 abstract_id 语义；Crossref DOI 承诺保持不变 [R4]，但 v2 的外链与去重键应以 DOI 为主、abstract_id 为辅。
3. **NBER 批量元数据的授权**：`data.nber.org` 明确拒绝 bot，需向 NBER 申请（页面联系人为 Daniel Feenberg）[R10][R11]；在授权前 JEL/已发表映射仍依赖 RePEc。
4. **多家商科出版社 TDM/ToS 未核验**：AOM（403）、Emerald（CF 挑战；另受 Wiley 收购后的政策整合影响 [R87]）、AAA、MISQ 的 TDM 与自动下载条款仍未取得（核验阶段已补 SAGE TDM/AI 政策 [R85]，以及 INFORMS 使用条款的摘要级证据 [R88]；后者原文仍需在可达网络逐字复核）；在取得前，这些平台的全文只允许"用户显式单篇 + 会话内"，不做批量。
5. **名录许可**：FT50 2026 版名单已经图书馆指南二手核验，但 FT 原文与使用条款未取得 [R86]；AJG 需登录且版权所有；ABDC 站点声明"All Rights Reserved"并称第三方可检索版本未经授权 [R67]——三者的再分发边界需法务/许可确认，v2 首版只内置 UTD24 与学界约定名单。
6. **摘要展示的版权边界**：多用户平台公开展示出版商摘要是否构成超出"个人使用"的复制（Springer 条款明确限制）[R39]；Crossref 仅提示"可能受版权"[R26]。需在设计阶段裁决：公共卡片是否仅展示 CC 摘要/自生成要点、原始摘要是否仅对本人或经许可展示。
7. **机器人协议冲突的裁决**：`api.osf.io` robots 为 `Disallow: /` 而 OSF API 为公开文档化 API；World Bank OKR 与 MPRA、AIS eLibrary 的 OAI 端点落在 robots 禁区。本调研按最严口径改走 Crossref/官方 API/RePEc，但若需要 OSF 的版本/许可字段，应先向 COS 书面确认。
8. **Crossref 公共池 1 req/s 是否临时**：文档（2025-10-16）仍写 public 5 [R27]，实测头为 1 [R28]；若为动态降级，v2 的回源预算与首轮回填（107 刊 × 全史）排期需按最坏情况设计，必要时评估 Crossref Metadata Plus（付费）或 Crossref 年度公共数据文件（核验补充：2026 版于 2026-03-17 发布，约 1.8 亿条、压缩后 208 GB，经 Academic Torrents 或 AWS 获取 [R94]）。
9. **AOM × Elsevier 合作走向**：目前 AMR/AMJ 最新 DOI 仍落 `journals.aom.org` [R70]，新 OA 刊 AMIO/AMOE 在 Crossref 尚无刊记录（journals 检索为空，[R78]）；若旗舰刊未来迁 ScienceDirect，AOM 的全文通道将改为 Elsevier API 并受其政策约束。
10. **平台归属**（核验更新）：Emerald、AAA、MISQ 的 Silverchair 归属已由平台方公告确认 [R83]；Annual Reviews 迁入 Ingenta Edify 为摘要级确认 [R89]；Emerald 被 Wiley 收购后是否迁往 Wiley 旗下平台尚无公开信息（⚠ 推测风险）[R87]；实现前仍需在登录态下核实页面结构。
11. **可达性与出口 IP 强相关**：v1 记录的 Springer/INFORMS"云 IP 连接层拒绝"本次已不复现，而 Cambridge 反而在 robots 层就挑战——同一站点的判罚随出口 IP/客户端指纹变化；v2 服务端（数据中心 IP）与用户端（校园/家庭网络）应分别建立可达性画像，且全文取回默认放在用户侧执行。
12. **IMF/World Bank 的 Crossref 覆盖不完整**：IMF WP 需按 container 过滤（检索计数为相关度近似值），World Bank PRWP 在 Crossref 仅约 2.2k/11.4k [R52][R78]——两者都应以官方渠道为准做对账。
13. **会议来源大量未核验**：EFA、SED、Econometric Society 区域会议、SMS、Marketing Science Conference 的程序与论文形态均未勘察；ASSA 论文 PDF 的作者授权/再分发条款未核验。
14. **ECMA 过刊与会员通道**：ECMA 1999 年后在 Wiley、1933–2002 在 JSTOR、会员可在学会站访问全部年份 [R16]；v2 若支持"会员凭证"作为一种用户凭证类型，需要确认学会站对自动化取回的态度（其 robots 具名禁 ClaudeBot，自营域曾出现 CF 质询，v1 记录）。
15. **央行 WP 的再分发许可逐源不同**（本次未逐一核验）：平台级缓存 OA 全文前需按来源确认（美国联邦政府作品按 17 U.S.C. §105 原则上不享版权，但 Fed 站点声明本次未核验；ECB/BIS/IMF/World Bank 各有条款 ⚠）。
16. **（核验补充）SSRN 的 CC 许可论文如何处理**：Crossref 已登记 SSRN license [R1][R91]。CC BY 等许可允许合法取得后的再分发，但 SSRN ToU 仍禁止自动化查询 [R5]。设计阶段需裁决："用户手动下载的 CC 许可 SSRN 论文"能否进入平台级 OA 缓存；同时确认 SSRN 是否会提供机器可读的许可或全文通道。在裁决前按"仅外链"处理。
17. **（核验补充）外部成本与名录状态的漂移**：OpenAlex 2026 年起改为 API key + 按量计费 [R93]，摘要补齐链中的 OpenAlex 环节需纳入平台级预算与限流；MIT SMR 停印转数字版 [R90]、FT50 修订 [R86] 会改变 venue 状态与名录版本，需在数据模型中留出 `status` 与 `version` 字段。

## 5. 参考来源（URL + 访问日期）

> 访问日期均为 **2026-09-26**。标注：LIVE=本次直接请求并读取；DOC=本次读取的官方文档；SNIPPET=目标页不可直连，仅经搜索引擎摘要获得（部分核验）；✗=本次不可访问。

| 编号 | 来源 | URL | 类型 |
|---|---|---|---|
| R1 | Crossref：SSRN 前缀 10.2139 计数/类型/摘要/关系/最新 | https://api.crossref.org/prefixes/10.2139/works?rows=0 （另加 `filter=from-created-date:2026-01-01`、`facet=type-name:*`、`has-abstract:true`、`relation.type:is-preprint-of`、`sort=created&order=desc` 变体） | LIVE |
| R2 | SSRN Strategic Update（2026-04-13） | https://blog.ssrn.com/2026/04/13/ssrn-strategic-update-renewed-focus-on-core-research-sharing-mission/ | SNIPPET（直连 Socket closed） |
| R3 | CRIV Blog：SSRN Ending Commercial Products（2026-04-20） | https://crivblog.com/2026/04/20/social-science-research-network-ssrn-ending-commercial-products/ | DOC |
| R4 | Elsevier Digital Commons：SSRN RPS Sunset | https://digitalcommons.elsevier.com/en_US/integration-preservation/ssrn-research-paper-series-sunset-dc-options | DOC |
| R5 | SSRN Terms of Use（自动化查询条款） | https://www.ssrn.com/index.cfm/en/terms-of-use/ | SNIPPET（直连 TLS reset） |
| R6 | SSRN 支持中心：Are all papers on SSRN free?（页内 Last updated 2026-08-03） | https://www.elsevier.support/ssrn/answer/are-all-papers-on-ssrn-free | DOC |
| R7 | SSRN Blog：New Advanced Search（2026-03-16） | https://blog.ssrn.com/2026/03/16/ssrns-new-advanced-search-makes-finding-papers-easier-and-faster/ | SNIPPET |
| R8 | NBER：Working Papers Subscriptions and Access | https://www.nber.org/subscribe/working-papers-subscriptions-and-access | DOC |
| R9 | NBER Help：Working Papers General Information（18 个月规则） | https://www.nber.org/nber-help-working-papers-general-information | DOC |
| R10 | NBER Working Papers and Chapters Metadata | https://www.nber.org/research/data/nber-working-papers-and-chapters-metadata | DOC |
| R11 | data.nber.org 元数据目录与 robots（403 "Prevent Bots from data downloads"） | https://data.nber.org/nber_paper_chapter_metadata/tsv/ ；https://data.nber.org/robots.txt | LIVE |
| R12 | NBER robots（www / back） | https://www.nber.org/robots.txt ；https://back.nber.org/robots.txt | LIVE |
| R13 | AEA robots（www / pubs） | https://www.aeaweb.org/robots.txt ；https://pubs.aeaweb.org/robots.txt | LIVE |
| R14 | AEA Journal Subscriptions | https://www.aeaweb.org/journals/subscriptions | DOC |
| R15 | OpenAlex：AEA 样本 DOI 的 OA 状态 | https://api.openalex.org/works/doi:10.1257/jep.20261505 （及 jel.20261775、pandp.20261094、aer.20241087） | LIVE |
| R16 | Econometric Society：Econometrica Access | https://www.econometricsociety.org/publications/econometrica/access | DOC |
| R17 | Crossref：ECMA 2025–26 license 计数；doi.org 解析 | https://api.crossref.org/journals/0012-9682/works?rows=0&filter=from-pub-date:2025-01-01,type:journal-article,has-license:true ；https://doi.org/10.3982/ECTA23709 | LIVE |
| R18 | CEPR robots（Last-Modified: Thu, 24 Sep 2026 10:40:21 GMT） | https://cepr.org/robots.txt | LIVE |
| R19 | CEPR Discussion Paper Subscriptions；New Discussion Papers 新闻页 | https://cepr.org/publications/discussion-papers/discussion-paper-subscriptions | SNIPPET（核验阶段 WebFetch 直读成功，升级为 DOC："archive of more than 20,000 papers" since 1984） |
| R20 | RePEc getdata 页；RePEc Blog | https://ideas.repec.org/getdata.html ；https://blog.repec.org/ | DOC / SNIPPET |
| R21 | Elsevier API Key Settings（配额表） | https://dev.elsevier.com/api_key_settings.html | DOC |
| R22 | Elsevier Developer Portal Policy（含 Federated Search 政策） | https://dev.elsevier.com/policy.html | DOC |
| R23 | Elsevier Text and Data Mining Policy | https://www.elsevier.com/about/policies-and-standards/text-and-data-mining | DOC |
| R24 | ScienceDirect robots（"Last updated: Sep 2026"） | https://www.sciencedirect.com/robots.txt | LIVE |
| R25 | rss.sciencedirect.com robots | https://rss.sciencedirect.com/robots.txt | LIVE |
| R26 | Crossref REST API 文档（元数据许可、摘要版权提示） | https://www.crossref.org/documentation/retrieve-metadata/rest-api/ | DOC |
| R27 | Crossref Access and Authentication（池限额；页面更新 2025-10-16） | https://www.crossref.org/documentation/retrieve-metadata/rest-api/access-and-authentication/ | DOC |
| R28 | Crossref 实测响应头（`x-rate-limit-limit: 1` 等） | https://api.crossref.org/works?rows=0 | LIVE |
| R29 | INFORMS robots；条款页（4 页 403 CF）；tdmrep（404） | https://pubsonline.informs.org/robots.txt ；https://pubsonline.informs.org/page/termsofuse ；https://pubsonline.informs.org/.well-known/tdmrep.json | LIVE |
| R30 | AOM robots（journals / www）；tdmrep（404） | https://journals.aom.org/robots.txt ；https://www.aom.org/robots.txt ；https://journals.aom.org/.well-known/tdmrep.json | LIVE |
| R31 | AOM Journals 页 | https://www.aom.org/publications/journals/ | DOC |
| R32 | AOM Open Access Research Journals（Vision 2030 / Elsevier 合作） | https://www.aom.org/publications/journals/open-access-journals/ | DOC |
| R33 | Wiley Online Library robots；tdmrep（403 CF） | https://onlinelibrary.wiley.com/robots.txt ；https://onlinelibrary.wiley.com/.well-known/tdmrep.json | LIVE |
| R34 | T&F Online robots；tdmrep（403 CF） | https://www.tandfonline.com/robots.txt ；https://www.tandfonline.com/.well-known/tdmrep.json | LIVE |
| R35 | Taylor & Francis：Text and Data Mining 政策 | https://taylorandfrancis.com/our-policies/textanddatamining/ | DOC |
| R36 | SpringerLink robots | https://link.springer.com/robots.txt | LIVE |
| R37 | SpringerLink TDMRep | https://link.springer.com/.well-known/tdmrep.json | LIVE |
| R38 | Springer Nature API：TDM Reservation Policy | https://dev.springernature.com/tdm-reservation-policy/ | DOC |
| R39 | Springer Nature API：Additional terms for API users | https://dev.springernature.com/terms-conditions/ | DOC |
| R40 | Springer Nature API 门户与订阅页（JS 渲染，配额数字未取得） | https://dev.springernature.com/ ；https://dev.springernature.com/subscription/ | DOC（部分） |
| R41 | Emerald robots；首页（CF）；旧企业站跳转；tdmrep（404） | https://www.emerald.com/robots.txt ；https://www.emeraldgrouppublishing.com/robots.txt | LIVE |
| R42 | Oxford Academic robots | https://academic.oup.com/robots.txt | LIVE |
| R43 | Cambridge Core robots（403 `cf-mitigated: challenge`） | https://www.cambridge.org/robots.txt | LIVE |
| R44 | UChicago Journals robots | https://www.journals.uchicago.edu/robots.txt | LIVE |
| R45 | AAA / MISQ / MIT Press Direct robots（Silverchair 模板） | https://publications.aaahq.org/robots.txt ；https://misq.umn.edu/robots.txt ；https://direct.mit.edu/robots.txt | LIVE |
| R46 | Annual Reviews robots | https://www.annualreviews.org/robots.txt | LIVE |
| R47 | De Gruyter Brill robots | https://www.degruyterbrill.com/robots.txt | LIVE |
| R48 | Federal Reserve RSS 目录与 FEDS/IFDP feed；robots（404） | https://www.federalreserve.gov/feeds/feeds.htm ；https://www.federalreserve.gov/feeds/feds.xml ；https://www.federalreserve.gov/feeds/ifdp.xml ；https://www.federalreserve.gov/robots.txt | LIVE |
| R49 | ECB RSS 目录、WP feed、robots | https://www.ecb.europa.eu/home/html/rss.en.html ；https://www.ecb.europa.eu/rss/wppub.html ；https://www.ecb.europa.eu/robots.txt | LIVE |
| R50 | BIS WP RSS（CB-RSS）与 robots | https://www.bis.org/doclist/wppubls.rss ；https://www.bis.org/robots.txt | LIVE |
| R51 | IMF WP RSS（403 Akamai）与 robots | https://www.imf.org/en/Publications/RSS?language=eng&series=IMF%20Working%20Papers ；https://www.imf.org/robots.txt | LIVE |
| R52 | World Bank Documents & Reports API v3 与文档；robots | https://search.worldbank.org/api/v3/wds?format=json&rows=2&docty=Policy%20Research%20Working%20Paper&sort=docdt&order=desc ；https://documents.worldbank.org/en/publication/documents-reports/api ；https://documents.worldbank.org/robots.txt | LIVE / DOC |
| R53 | World Bank OKR robots（DSpace 7） | https://openknowledge.worldbank.org/robots.txt | LIVE |
| R54 | IZA robots、DP 列表与详情页 | https://www.iza.org/robots.txt ；https://www.iza.org/publications/dp | LIVE |
| R55 | EconStor OAI-PMH（Identify/ListSets）与 robots | https://www.econstor.eu/oai/request?verb=Identify ；https://www.econstor.eu/robots.txt | LIVE |
| R56 | EconBiz API v1 与文档；www robots | https://api.econbiz.de/v1/search?q=monetary+policy&size=2 ；https://api.econbiz.de/doc ；https://www.econbiz.de/robots.txt | LIVE / DOC |
| R57 | OSF API（SocArXiv）与 robots（api.osf.io / osf.io） | https://api.osf.io/v2/preprints/?filter[provider]=socarxiv ；https://api.osf.io/robots.txt ；https://osf.io/robots.txt | LIVE |
| R58 | SocArXiv AI Policy（2026-03-08） | https://socopen.org/ai-policy/ | DOC |
| R59 | MPRA robots | https://mpra.ub.uni-muenchen.de/robots.txt | LIVE |
| R60 | HBS robots；研究出版物页（403） | https://www.hbs.edu/robots.txt ；https://www.hbs.edu/faculty/research/publications/Pages/default.aspx | LIVE |
| R61 | ASSA 2026 程序与 session 页 | https://www.aeaweb.org/conference/2026/program ；https://www.aeaweb.org/conference/2026/program/1063 | LIVE |
| R62 | WFA 主站 robots 与会议门户（跳转登录） | https://westernfinance.org/robots.txt ；https://westernfinance-portal.org/conference.php | LIVE |
| R63 | SFS robots 与主页 | https://sfs.org/robots.txt ；https://sfs.org/ | LIVE |
| R64 | NBER Summer Institute 2026 与 SI Asset Pricing 页 | https://www.nber.org/conferences/summer-institute-2026 ；https://www.nber.org/conferences/si-2026-asset-pricing | LIVE |
| R65 | UTD 24 名录页 | https://jsom.utdallas.edu/the-utd-top-100-business-school-research-rankings/list-of-journals | LIVE |
| R66 | Chartered ABS：Academic Journal Guide | https://charteredabs.org/academic-journal-guide/ | DOC |
| R67 | ABDC Journal Quality List（xlsx 链接仅观察未下载） | https://abdc.edu.au/abdc-journal-quality-list/ ；https://abdc.edu.au/wp-content/uploads/2026/09/ABDC-JQL-2025-v3-210926.xlsx | DOC |
| R68 | VHB 站点（导航含 "VHB Rating 2024"）；核验补充：VHB Publication Media Rating 2024 官方页 | https://www.vhbonline.org/vhb4you/vhb-rating-2024 （404 页，导航可见）；https://www.vhbonline.org/en/services/vhb-rating-2024 | LIVE / DOC |
| R69 | FT：FT Research Rank 用刊列表（2016 版）；2026 修订版页 | https://www.ft.com/content/3405a512-5cbb-11e1-8f1f-00144feabdc0 ；https://www.ft.com/ft50-journals | ✗（两页本环境均不可访问） |
| R70 | Crossref `/journals/{ISSN}` 与最新条目（107 刊，清单见 §2.8） | https://api.crossref.org/journals/{ISSN} ；https://api.crossref.org/journals/{ISSN}/works?rows=1&sort=published&order=desc | LIVE |
| R71 | OpenAlex 2025 OA 构成与 source 记录 | https://api.openalex.org/works?filter=primary_location.source.issn:{ISSN},publication_year:2025,type:article&group_by=open_access.oa_status ；https://api.openalex.org/sources/issn:{ISSN} | LIVE |
| R72 | IDEAS robots | https://ideas.repec.org/robots.txt | LIVE |
| R73 | v1 内部勘察与决策（本地文件） | `docs/research/site-survey/{ssrn,nber,aea,econometric-society,repec,econ-fin-preprints,publisher-platforms-econfin,publisher-platforms-p4-recheck,metadata-apis}.md`；`docs/plan/decision-log.md`（D-005/D-006/D-007/D-011/D-014/D-027/D-028/D-029/D-030/D-035） | 本地 |
| R74 | 其他 robots：NY Fed、OECD、BoE、Brookings、FRASER、CESifo（301） | https://www.newyorkfed.org/robots.txt ；https://www.oecd.org/robots.txt ；https://www.bankofengland.co.uk/robots.txt ；https://www.brookings.edu/robots.txt ；https://fraser.stlouisfed.org/robots.txt ；https://www.cesifo.org/robots.txt | LIVE |
| R75 | SAGE：企业站 robots；journals.sagepub.com（TLS reset） | https://www.sagepub.com/robots.txt ；https://journals.sagepub.com/robots.txt | LIVE / ✗ |
| R76 | AIS eLibrary robots | https://aisel.aisnet.org/robots.txt | LIVE |
| R77 | OpenAlex 摘要可得性抽样（JFE、JET、AMJ、QF、ASQ 新文；JFE 2024、AMJ 2025 各 25 条） | https://api.openalex.org/works/doi:10.1016/j.jfineco.2026.104355 ；https://api.openalex.org/works?filter=primary_location.source.issn:0304-405X,publication_year:2024,type:article&per-page=25&select=doi,abstract_inverted_index | LIVE |
| R78 | Crossref 前缀/系列探针（NBER、FRB、IMF、World Bank、SocArXiv、SSRN；journals 标题检索） | https://api.crossref.org/prefixes/{10.3386,10.17016,10.5089,10.1596,10.31235}/works?rows=0 （含 `from-created-date:2026-01-01`、`has-abstract:true`、`facet=type-name:*`、`query.container-title=` 变体）；https://api.crossref.org/journals?query=Journal+of+Political+Economy+Microeconomics | LIVE |
| R79 | doi.org RA 查询（ECB DOI 属 OP；FEDS DOI 属 Crossref） | https://doi.org/ra/10.2866/6086982 ；https://doi.org/ra/10.17016/FEDS.2026.001 | LIVE |
| R80 | Crossref：Tips for using the Crossref REST API（`from-index-date` 同步、cursor、`select`、`rows` 等建议） | https://www.crossref.org/documentation/retrieve-metadata/rest-api/tips-for-using-the-crossref-rest-api/ | DOC |
| R81 | Elsevier Text and Data Mining (TDM) Provisions（key 停用条件、输出片段 200 字符、竞争性用途限制） | https://dev.elsevier.com/tdm_service.html | DOC |
| R82 | SSRN 被 Elsevier 收购新闻稿（2016-05-17，含"In time, SSRN will migrate onto the Mendeley technology platform"）；SSRN 站内对应页 | https://librarytechnology.org/pr/21606 ；https://www.ssrn.com/index.cfm/en/ssrn-joins-mendeley-elsevier/ | DOC / SNIPPET |
| R83 | （核验补充）Silverchair 平台公告：AAA 期刊上线（2022-12-13）、Emerald Insight 新版上线（2025-07-22）、MIS Quarterly 上线（2025-08-21） | https://www.silverchair.com/news/american-accounting-association-journals-launch/ ；https://www.silverchair.com/news/emerald-publishing-launches-new-emerald-insight/ ；https://www.silverchair.com/news/mis-quarterly-launches-on-the-silverchair-platform/ | DOC |
| R84 | （核验补充）WileyLabs/tdm-client README（Wiley 官方 GitHub，最近推送 2026-07-02；复述 WOL TDM 资源页限速：至多 3 篇/s、60 次/10 min） | https://github.com/WileyLabs/tdm-client ；https://onlinelibrary.wiley.com/library-info/resources/text-and-datamining （WebFetch 403） | DOC / ✗ |
| R85 | （核验补充）Sage Policy on TDM and AI；Sage Journals TDM License Agreement（限速条款） | https://www.sagepub.com/tdm-ai-policy ；https://journals.sagepub.com/page/policies/text-and-data-mining-license | DOC / SNIPPET（后者 Socket closed） |
| R86 | （核验补充）FT50 2026 修订：USC Marshall 图书馆博客（2026-04-30）；McMaster 图书馆 FT50 全表；G. Schnyder 博客（2026-05-01，确认 FT 于 2026-04-29 发布、为 2016 年以来首次修订） | https://libguides.usc.edu/blogs/marshall/financial-times-50 ；https://libguides.mcmaster.ca/ft-top50 ；https://www.gerhardschnyder.com/blog/2026/5/1/short-reflection-on-the-2026-ft50-journal-ranking-update | DOC（二手） |
| R87 | （核验补充）Emerald 收购 now publishers（2025-05-06）；Wiley 收购 Emerald（2026-06-02，£337m / 约 $452m，卖方 Cambridge Information Group） | https://librarytechnology.org/pr/31323 ；https://newsroom.wiley.com/press-releases/press-release-details/2026/Wiley-Acquires-Emerald-Expanding-Research-Scale-and-Deepening-Proprietary-Content-Across-the-AI-Driven-Knowledge-Economy/default.aspx | DOC |
| R88 | （核验补充）INFORMS PubsOnLine Terms and Conditions（系统性下载禁令、离线浏览 ≤20 页/分钟） | https://www.informs.org/Publications/Librarians-Portal/PubsOnLine-Terms-and-Conditions | SNIPPET（WebFetch 403；curl 遇 `cf-mitigated: challenge` 即停） |
| R89 | （核验补充）Annual Reviews 平台迁移 FAQ（2024-03-19 迁入 Ingenta Edify） | https://www.annualreviews.org/page/librarians/MigrationFAQ_LRC | SNIPPET（WebFetch 403） |
| R90 | （核验补充）MIT Sloan：Update on MIT Sloan Management Review（2026-09-10）；Poets&Quants 停办报道（2026-05-06） | https://mitsloan.mit.edu/press/update-mit-sloan-management-review ；https://poetsandquants.com/2026/05/06/mit-sloan-management-review-to-shut-down-after-67-years/ | DOC |
| R91 | （核验补充）SSRN Blog：许可选择（2026-07-20）；SSRN's Ongoing Commitment to Legal Scholarship（2026-06-04） | https://blog.ssrn.com/2026/07/20/ssrn-will-now-allow-you-to-choose-the-licence-thats-right-for-your-work/ ；https://blog.ssrn.com/2026/06/04/ssrns-ongoing-commitment-to-legal-scholarship/ | SNIPPET（blog.ssrn.com 直连 Socket closed） |
| R92 | （核验补充）RePEc 首页统计（2,400+ archives、106 国、5.5M+ 条目、4,600 刊、5,900 WP 系列、74,000+ 注册作者） | http://repec.org/ | LIVE |
| R93 | （核验补充）OpenAlex 定价页（注册账户获 API key，免费每日 $1；页面更新 2026-08-11）；OpenAlex 实测响应头（`x-ratelimit-limit-usd: 0.1`、`x-ratelimit-cost-usd: 0.0001`） | https://help.openalex.org/access/pricing/ ；https://api.openalex.org/works?filter=primary_location.source.issn:0012-9682,publication_year:2025,type:article&group_by=open_access.oa_status | DOC / LIVE |
| R94 | （核验补充）Crossref Blog：2026 public data file now available（2026-03-17） | https://www.crossref.org/blog/2026-public-data-file-now-available/ | DOC |
| R95 | （核验补充）AEA EconLit 介绍页 | https://www.aeaweb.org/econlit/ | DOC |

## 核验记录

> 角色：对抗式事实核验（Verify）。核验日期统一为 **2026-09-26**（请求发生在 2026-09-26 19:13–19:45 UTC）。本节是全文唯一的核验记录。开工前检查过：原文没有既有的"核验记录"章节，也没有"核验补充"标记，文件修改时间早于本轮，未发现前次中断遗留的半截修改。本节新增的来源编号为 [R83]–[R95]，见 §5。

### 核验方法与过程记录（可复现）

- **请求纪律**：UA 恒为 `PaperCrawler-verify/0.2 (v2 source survey fact-check; personal research)`，不伪装浏览器、不带个人邮箱、零登录、零 PDF 正文下载。同域请求间隔 ≥2 s，遵守 robots 中更严的 Crawl-delay（back.nber.org 为 10 s）。Crossref 起初间隔 1.2–1.3 s；因本机出口 IP 与并行调研代理共享公共池，触发过 1 次 HTTP 429，随即降到 ≥2.5 s/次。遇 `cf-mitigated: challenge`（www.cambridge.org、www.informs.org）或 bot 拦截（data.nber.org，Akamai）立即停止该域后续请求，不换 UA、不重试。
- **直接请求（LIVE）**：
  - Crossref：`/prefixes/{10.2139,10.3386,10.17016,10.5089,10.1596,10.31235}/works`（含 `from-created-date`、`has-abstract`、`has-license`、`relation.type`、`facet=type-name:*`、`facet=license:*` 变体）；`/journals/{ISSN}` 抽查 26 刊（另含 HBR 的 404 探针）；`/journals?query=`。
  - doi.org RA API；OpenAlex（`group_by=open_access.oa_status` 共 3 次，摘要抽样 3 次）。
  - robots.txt：cepr、sciencedirect、rss.sciencedirect、pubsonline.informs、link.springer（含 tdmrep.json）、mpra、api.osf.io、osf.io、back/www.nber、sfs、cambridge（403）、econometricsociety、journals/www.aom、onlinelibrary.wiley、tandfonline、iza、hbs、openknowledge.worldbank、westernfinance、ideas.repec、vhbonline、aisel、ecb、bis、imf、academic.oup、publications.aaahq、misq.umn、journals.uchicago、federalreserve（404）、data.nber（403）、informs.org（403 CF）。
  - 页面与数据：Econometrica 访问页、AOM OA 刊页、UTD24 名录页、ABDC JQL 页、World Bank D&R API v3、BIS/ECB/Fed/NBER RSS、IZA DP 列表、EconBiz API、EconStor OAI Identify、repec.org 首页；GitHub API `repos/WileyLabs/tdm-client`（含 README）。
- **WebFetch 读取的官方文档**：
  - Crossref：访问与认证、REST API、Tips、2026 公共数据文件博客。
  - Elsevier：api_key_settings、tdm_service、policy。
  - Springer Nature：terms-conditions、tdm-reservation-policy。T&F：TDM 政策。
  - NBER：订阅页、帮助页、元数据页。AEA：订阅页、EconLit、ASSA 程序与 session 页。
  - 其他：CEPR 订阅页、Chartered ABS AJG、SocArXiv AI 政策、EconBiz 文档、RePEc getdata、SSRN 支持页、CRIV 博客、Digital Commons、librarytechnology.org（2016、2025 两篇）、Silverchair 公告 ×3、Wiley 新闻稿、MIT Sloan 声明、Poets&Quants、USC/McMaster 图书馆指南、Schnyder 博客、VHB 页、Sage TDM/AI 政策、OpenAlex 定价页。
- **不可达（按环境障碍或站点判罚记录，未绕过）**：
  - `blog.ssrn.com` 与 `www.ssrn.com`：WebFetch Socket closed。
  - `journals.sagepub.com`：Socket closed。
  - `www.informs.org`：CF 挑战。
  - `onlinelibrary.wiley.com` TDM 页、`www.annualreviews.org` FAQ、`emeraldgrouppublishing.com` FAQ：WebFetch 403。
  - `www.ft.com`：无法抓取。
  - `dev.springernature.com` 限速页：JS 渲染，未取得正文。
- **WebSearch 检索式（按执行顺序）**：
  1. `American Accounting Association Silverchair platform publications.aaahq.org launch`
  2. `MIS Quarterly Silverchair platform misq.umn.edu`
  3. `Emerald Insight platform Silverchair partnership`
  4. `Annual Reviews new website platform provider 2024 Ingenta OR Atypon OR Silverchair annualreviews.org`
  5. `"Annual Reviews" Ingenta Edify platform migration annualreviews.org`
  6. `SSRN "strategic update" April 2026 Research Paper Series Site Subscriptions Data Feeds discontinued December 31 2026`
  7. `"automated queries of any sort" SSRN terms of use`
  8. `blog.ssrn.com strategic update 2026 "Research Alert" ORCID versioning Crossref preprint published version link`
  9. `"Building the Future of Research Sharing at SSRN" July 2026`
  10. `SSRN's Ongoing Commitment to Legal Scholarship June 2026 blog`
  11. `"SSRN will now allow you to choose the licence" CC BY licence July 2026`
  12. `Constellate ITHAKA JSTOR retired July 2025 text analysis platform sunset`
  13. `FT50 journals list Financial Times research rank 50 journals 2025 OR 2026 update`
  14. `Financial Times April 2026 FT50 list revised "Psychological Science" "American Sociological Review" "Academy of Management Annals" added`
  15. `MIT Sloan Management Review closure 2026 ceases publication`
  16. `Wiley text and data mining API rate limit "3 requests per second" "60 requests per 10 minutes"`
  17. `SAGE Publishing text and data mining policy subscribers non-commercial TDM license journals.sagepub.com`
  18. `INFORMS PubsOnline text and data mining policy terms of use automated downloading`
  19. `Critical Finance Review Emerald Publishing now publishers acquisition journal moved`
  20. `Wiley acquires Emerald Publishing`
  21. `"Critical Finance Review" "now publishers" Ivo Welch journal publisher Emerald 2024`
  22. `Emerald Publishing acquires now publishers`
  23. `Econometric Society Econometrica 2026 open access transition Wiley contract ends`
  24. `Academy of Management Journal Elsevier ScienceDirect 2026 AMJ AMR move publishing partnership announcement`
  25. `"Journal of Management" Southern Management Association Elsevier 2026 publisher change SAGE`
  26. `OpenAlex API key required 2026 free daily usage $1 credits pricing rate limit`
  27. `Crossref 2026 public data file released metadata annual`
  28. `Springer Nature API free plan limits requests per day per minute 2025 dev.springernature.com Meta API OpenAccess API`
  29. `SSRN new advanced search March 2026 fuzzy Boolean blog`
  30. `VHB-Rating 2024 VHB Publication Media Rating Gesamtliste Teilratings vhbonline`
- **阴性结果（查无证据，未写入正文）**：
  - 未见 Econometrica 结束与 Wiley 合作或转为全刊 OA 的公告（检索 23）。
  - 未见 AMJ/AMR 迁往 ScienceDirect 的公告（检索 24）。
  - 未见 SAGE 版 Journal of Management（SMA）更换出版方（检索 25；Crossref 显示该刊仍为 SAGE，最新 2026-09-22）。

### 逐条核验表

| # | 断言（原文要点） | 结论 | 依据来源 URL | 核验日期 |
|---|---|---|---|---|
| 1 | SSRN：Crossref `10.2139` 约 148.7 万 DOI，新 DOI 当日可见；2026 年新建约 22.6 万条，91.2% 带摘要；2026 年 `is-preprint-of` 仅 266 条 | 确认。19:14Z 复测总量 1,487,671；2026 年新建 226,562 条，其中带摘要 206,749 条（91.3%）。`is-preprint-of` 2026 年 266 条，全量 2,158 条。最新 created 为 2026-09-26T18:35Z | https://api.crossref.org/prefixes/10.2139/works?rows=0 （及 filter/sort 变体） | 2026-09-26 |
| 2 | SSRN 于 2026-04-13 发布战略更新，商业产品在 2026 年底前关停，并计划提供免费 Research Alert、改进 Crossref 元数据、版本化、ORCID 集成与"预印本↔发表版"链接 | 确认（SNIPPET 级；原文直连 Socket closed）。关停清单全称为 RPS、Sponsored Networks and Site Subscriptions、paid Conference Proceedings、Data Analytics Dashboards、Partners in Publishing、Jobs and Announcements、Data Feeds。CRIV 博客（DOC）可旁证 | https://blog.ssrn.com/2026/04/13/ssrn-strategic-update-renewed-focus-on-core-research-sharing-mission/ ；https://crivblog.com/2026/04/20/social-science-research-network-ssrn-ending-commercial-products/ | 2026-09-26 |
| 3 | SSRN RPS 只能导出元数据，既有内容与 DOI 保持不变 | 确认 | https://digitalcommons.elsevier.com/en_US/integration-preservation/ssrn-research-paper-series-sunset-dc-options | 2026-09-26 |
| 4 | SSRN ToU 禁止任何形式的自动化查询 | 确认（SNIPPET 级；ToU 页直连 Socket closed，仍需在可达网络逐字复核） | https://www.ssrn.com/index.cfm/en/terms-of-use/ | 2026-09-26 |
| 5 | "SSRN 迁往 Mendeley 平台"出自 2016-05-17 收购新闻稿，不是 2026 年的新计划 | 确认（原句为 "In time, SSRN will migrate onto the Mendeley technology platform"） | https://librarytechnology.org/pr/21606 | 2026-09-26 |
| 6 | SSRN 支持页称：个人作者上传的论文一律免费下载，出版方或机构上传的可收费（Last updated 2026-08-03） | 确认 | https://www.elsevier.support/ssrn/answer/are-all-papers-on-ssrn-free | 2026-09-26 |
| 7 | SSRN 于 2026-03-16 新增 Fuzzy/Boolean 高级检索 | 确认（SNIPPET 级） | https://blog.ssrn.com/2026/03/16/ssrns-new-advanced-search-makes-finding-papers-easier-and-faster/ | 2026-09-26 |
| 8 | SSRN robots（v1 记录：禁 GPTBot 等，crawl-delay 5） | 未核验（本环境 SSRN 主机不可达，维持 v1 记录） | https://www.ssrn.com/robots.txt | 2026-09-26 |
| 9 | NBER：每人每年 3 篇免费下载；人均 GDP（PPP）低于 $35,000（2024 年 IMF 数据）国家的居民免费；机构按 IP 识别 | 确认 | https://www.nber.org/subscribe/working-papers-subscriptions-and-access | 2026-09-26 |
| 10 | NBER：近 18 个月的论文对高收入国家访客需订阅 | 确认 | https://www.nber.org/nber-help-working-papers-general-information | 2026-09-26 |
| 11 | NBER 元数据文件每周自动更新，提供 csv/dta/tsv，含 abs、date、jel、prog、auth、title、published、ref(DOI)；联系人为 Daniel Feenberg | 确认 | https://www.nber.org/research/data/nber-working-papers-and-chapters-metadata | 2026-09-26 |
| 12 | `data.nber.org` 对非浏览器 UA 返回 403 "Prevent Bots from data downloads" | 确认（robots.txt 与 tsv 目录均为 403，Akamai；已停手） | https://data.nber.org/robots.txt ；https://data.nber.org/nber_paper_chapter_metadata/tsv/ | 2026-09-26 |
| 13 | NBER Crossref `10.3386`：36,256 个 DOI，2026 年新建 1,207 条，摘要 0 条 | 确认 | https://api.crossref.org/prefixes/10.3386/works?rows=0 | 2026-09-26 |
| 14 | NBER back 主机 Crawl-delay 10；RSS `back.nber.org/rss/new.xml` 可用 | 确认（RSS 共 29 条，含摘要） | https://back.nber.org/robots.txt ；https://back.nber.org/rss/new.xml | 2026-09-26 |
| 15 | Econometric Society 访问页"写明由 Wiley 出版" | **修正**。页面只把图书馆订阅指向 Wiley Online Library，并称 1999 年起的文章经 WOL 提供，并未写"由 Wiley 出版"；Crossref `publisher` 字段为 The Econometric Society | https://www.econometricsociety.org/publications/econometrica/access ；https://api.crossref.org/journals/0012-9682 | 2026-09-26 |
| 16 | ECMA 2025–26 年 170 条 journal-article 中 79 条"带 CC BY" | **修正**。79 条带 CC 许可，其中 CC BY 53、CC BY-NC 10、CC BY-NC-ND 16。NC/ND 会限制派生用途 | https://api.crossref.org/journals/0012-9682/works?rows=100&filter=from-pub-date:2025-01-01,type:journal-article,has-license:true&select=DOI,license | 2026-09-26 |
| 17 | ECMA 2025 年 article 的 OA 占 59%（hybrid 53 / green 5） | 确认（n=75：hybrid 40、green 4、closed 31） | https://api.openalex.org/works?filter=primary_location.source.issn:0012-9682,publication_year:2025,type:article&group_by=open_access.oa_status | 2026-09-26 |
| 18 | CEPR robots Last-Modified 为 2026-09-24，无 AI 具名条目和 Content-Signal，Bing/Baidu/Yandex Crawl-delay 3；DP 自 1984 年以来 20,000+ 篇，需订阅 | 确认（订阅页由 SNIPPET 升级为 DOC） | https://cepr.org/robots.txt ；https://cepr.org/publications/discussion-papers/discussion-paper-subscriptions | 2026-09-26 |
| 19 | Crossref 公共池响应头为 `x-rate-limit-limit: 1`、`x-concurrency-limit: 1`、`x-api-pool: public-array` | 确认（出口 IP 为共享池，触发过 1 次 429） | https://api.crossref.org/works?rows=0 | 2026-09-26 |
| 20 | Crossref 文档：public 5 req/s（并发 1）、polite 10 req/s（并发 3，mailto）、Plus 150；页面更新于 2025-10-16 | 确认 | https://www.crossref.org/documentation/retrieve-metadata/rest-api/access-and-authentication/ | 2026-09-26 |
| 21 | Crossref 提示"部分摘要可能受出版商或作者版权"；同步本地数据宜用 `from-index-date` 加 `until-index-date` | 确认 | https://www.crossref.org/documentation/retrieve-metadata/rest-api/ ；https://www.crossref.org/documentation/retrieve-metadata/rest-api/tips-for-using-the-crossref-rest-api/ | 2026-09-26 |
| 22 | Elsevier 配额：Article Retrieval 每周 50,000 次（TDM key 不限量）、10 rps；SD Search 每周 20,000 次、2 rps | 确认 | https://dev.elsevier.com/api_key_settings.html | 2026-09-26 |
| 23 | Elsevier TDM：key 在 6 个月未启用、1 年未访问、订阅到期，或被出售、转让、披露给他人时可被停用；输出片段不超过 200 字符；不得产出与 Elsevier 产品竞争的衍生品；仅限订阅机构的非商业研究 | 确认 | https://dev.elsevier.com/tdm_service.html | 2026-09-26 |
| 24 | Elsevier 联邦检索政策：API 数据不得索引或持久存储，只允许临时缓存 | 确认（另：ScienceDirect 结果可展示摘要，Scopus 只可展示核心书目） | https://dev.elsevier.com/policy.html | 2026-09-26 |
| 25 | ScienceDirect robots 标注 "Last updated: Sep 2026"，`*` 为 Disallow /；ClaudeBot、anthropic-ai、Claude-Web、claude-code 被禁；OAI-SearchBot、Claude-SearchBot、Claude-User 为 Allow；`rss.sciencedirect.com` 为 Disallow / | 确认（两者 Last-Modified 均为 2026-09-10） | https://www.sciencedirect.com/robots.txt ；https://rss.sciencedirect.com/robots.txt | 2026-09-26 |
| 26 | Springer Nature API 条款：摘要限个人使用、不得商用；TDM 内容只能存于内部服务器；不得用多账号或多 key 规避限额 | 确认 | https://dev.springernature.com/terms-conditions/ | 2026-09-26 |
| 27 | SpringerLink robots 对 `*` 先全禁再按白名单放行，20+ 个 AI UA 全禁；`tdmrep.json` 为 `tdm-reservation: 1`；政策保留 DSM 指令 Art.4(3) 下的 TDM 权与 AI 训练权 | 确认（共 23 个具名 UA 为 Disallow /，含 ClaudeBot、GPTBot、anthropic-ai、Claude-Web） | https://link.springer.com/robots.txt ；https://link.springer.com/.well-known/tdmrep.json ；https://dev.springernature.com/tdm-reservation-policy/ | 2026-09-26 |
| 28 | Springer Nature API 的配额数字 | 未核验（限速页为 JS 渲染，未取得正文） | https://dev.springernature.com/docs/rate-limit-details/rate-limits/ | 2026-09-26 |
| 29 | T&F：订阅者可做非商业 TDM，须遵守 STM 模型许可（或 TDM 补充条款） | 确认 | https://taylorandfrancis.com/our-policies/textanddatamining/ | 2026-09-26 |
| 30 | Wiley TDM 限速为 3 req/s 且每 10 分钟 60 次（v1 记录） | 确认（Wiley 官方 GitHub README 复述 WOL TDM 页；WOL 页本身返回 403） | https://github.com/WileyLabs/tdm-client | 2026-09-26 |
| 31 | INFORMS robots：`*` 不禁 `/doi/`，Crawl-delay 1；GPTBot、ChatGPT-User、Google-Extended、PerplexityBot、anthropic-ai 被禁 `/doi/full`、`/doi/pdf`、`/doi/epdf` | 确认 | https://pubsonline.informs.org/robots.txt | 2026-09-26 |
| 32 | AOM 与 Elsevier 合作（Vision 2030），新办 OA 刊 AMIO 与 AMOE；原文写"⚠ 推测将上线 ScienceDirect" | **修正**：AOM 页面直接链接两刊的 ScienceDirect 刊页，已确认 | https://www.aom.org/publications/journals/open-access-journals/ | 2026-09-26 |
| 33 | AMIO 与 AMOE 在 Crossref 尚无刊记录 | 确认（`journals?query` 返回 0 条） | https://api.crossref.org/journals?query=Inside+Organizations | 2026-09-26 |
| 34 | AOM robots：journals 主机 Crawl-delay 1，GPTBot 为 Disallow /；www 主机首行是孤立的 Crawl-delay 10 | 确认 | https://journals.aom.org/robots.txt ；https://www.aom.org/robots.txt | 2026-09-26 |
| 35 | UTD24 共 24 刊，多数标 "Since: 1990"，MSOM 为 1999、POM 为 1992；其中 INFORMS 7 刊、AOM 2 刊 | 确认（页面本身不分学科组，文中分组由调研员自拟） | https://jsom.utdallas.edu/the-utd-top-100-business-school-research-rankings/list-of-journals | 2026-09-26 |
| 36 | AAA、MISQ、Emerald 属 Silverchair（原文依据 robots 模板同构推断） | **修正**：由推断改为确认。上线时间：AAA 2022-12-13，Emerald 新版 2025-07-22，MISQ 2025-08-21 | https://www.silverchair.com/news/american-accounting-association-journals-launch/ ；https://www.silverchair.com/news/emerald-publishing-launches-new-emerald-insight/ ；https://www.silverchair.com/news/mis-quarterly-launches-on-the-silverchair-platform/ | 2026-09-26 |
| 37 | Annual Reviews 的平台为 pub2web/Edify（原文为推断） | **修正**：SNIPPET 级确认 2024-03-19 迁入 Ingenta Edify（官方 FAQ 页 WebFetch 返回 403） | https://www.annualreviews.org/page/librarians/MigrationFAQ_LRC | 2026-09-26 |
| 38 | ABDC JQL 2025 提供公开 xlsx `ABDC-JQL-2025-v3-210926.xlsx`，含 2022/2019/2016/2013/2010 各版 sheet；站点标注 "Copyright All Rights Reserved © 2026" | 确认（另补：站点声明其他可检索版本未经 ABDC 授权） | https://abdc.edu.au/abdc-journal-quality-list/ | 2026-09-26 |
| 39 | AJG 2024 为中期复审；AJG 2027 的科学委员会与编辑团队已组建；情境指标来自 Elsevier SciVal；查看需登录；版权所有 | 确认 | https://charteredabs.org/academic-journal-guide/ | 2026-09-26 |
| 40 | FT50 为"50 刊，⚠ 未核验" | **修正**：FT 于 2026-04-29 发布 2016 年以来首次修订版，移出 Human Relations、Journal of Business Ethics、Organization Studies，加入 Academy of Management Annals、American Sociological Review、Psychological Science；全表经 McMaster 图书馆指南核对（FT 原文不可达） | https://libguides.usc.edu/blogs/marshall/financial-times-50 ；https://libguides.mcmaster.ca/ft-top50 ；https://www.gerhardschnyder.com/blog/2026/5/1/short-reflection-on-the-2026-ft50-journal-ranking-update | 2026-09-26 |
| 41 | Fed：Crossref `10.17016` 共 4,991 个 DOI，2026 年新建 170 条，其中 168 条带摘要；RA 为 Crossref；`feeds/feds.xml` 15 条，含作者与摘要；robots.txt 返回 404 | 确认 | https://api.crossref.org/prefixes/10.17016/works?rows=0 ；https://doi.org/ra/10.17016/FEDS.2026.001 ；https://www.federalreserve.gov/feeds/feds.xml | 2026-09-26 |
| 42 | ECB：DOI 前缀 10.2866 由 OP 登记，不在 Crossref；WP RSS 含摘要，lastBuildDate 为 2026-09-25；robots Crawl-delay 5 | 确认 | https://doi.org/ra/10.2866 ；https://www.ecb.europa.eu/rss/wppub.html ；https://www.ecb.europa.eu/robots.txt | 2026-09-26 |
| 43 | BIS：WP RSS 为 RSS 1.0 加 CB-RSS 扩展，共 25 条，最新为 WP 1379（2026-09-23）；robots 禁 `/p/` 与 `/sites/default/files/` | 确认 | https://www.bis.org/doclist/wppubls.rss ；https://www.bis.org/robots.txt | 2026-09-26 |
| 44 | IMF：Crossref `10.5089` 共 105,381 个 DOI；2026 年新建 76,378 条，其中 component 65,142、chapter 10,372 | 确认 | https://api.crossref.org/prefixes/10.5089/works?rows=0&filter=from-created-date:2026-01-01&facet=type-name:* | 2026-09-26 |
| 45 | World Bank：D&R API v3 中 PRWP 共 11,380 条，返回摘要、pdfurl 与 repnb；Crossref 检索命中 2,221；OKR robots 禁 `/server/oai/` 与 `/server/api/`（仅放行 bitstream 等），Crawl-delay 10 | 确认 | https://search.worldbank.org/api/v3/wds?format=json&rows=1&docty=Policy%20Research%20Working%20Paper ；https://openknowledge.worldbank.org/robots.txt | 2026-09-26 |
| 46 | IZA robots 全部放行；2026-09-26 最新为 DP 18966 | 确认 | https://www.iza.org/robots.txt ；https://www.iza.org/publications/dp | 2026-09-26 |
| 47 | EconStor OAI：earliestDatestamp 为 2009-01-28，粒度到秒，deletedRecord 为 transient | 确认 | https://www.econstor.eu/oai/request?verb=Identify | 2026-09-26 |
| 48 | EconBiz API：处于 beta，当前无配额（可随时调整），不得用于大规模复制索引，ECONIS 全量需另行联系；记录含 `econbiz_created` 字段 | 确认 | https://api.econbiz.de/doc ；https://api.econbiz.de/v1/search?q=monetary+policy&size=1 | 2026-09-26 |
| 49 | SocArXiv：Crossref `10.31235` 约 2.58 万个 DOI，2026 年新建约 4.8k 条，摘要覆盖 99%；AI 政策发布于 2026-03-08；`api.osf.io` robots 为 Disallow /；`osf.io` crawl-delay 10，并禁 GPTBot 等 | 确认（复测：25,789 / 4,810 / 99.3%） | https://api.crossref.org/prefixes/10.31235/works?rows=0 ；https://socopen.org/ai-policy/ ；https://api.osf.io/robots.txt ；https://osf.io/robots.txt | 2026-09-26 |
| 50 | MPRA robots：`*` 禁 `/cgi/`；ClaudeBot、Claude-User、Claude-SearchBot 全禁；Bingbot Crawl-delay 10 | 确认 | https://mpra.ub.uni-muenchen.de/robots.txt | 2026-09-26 |
| 51 | RePEc getdata 页强烈不建议抓取网站，提供 FTP/rsync，OAI 标注 "sometimes flaky"，API 适合取数据切片 | 确认 | https://ideas.repec.org/getdata.html | 2026-09-26 |
| 52 | RePEc 有 "2,250+ archive" | **修正**：首页数据为 2,400+ archives（来自 106 国），5.5M+ 条目，覆盖 4,600 刊与 5,900 个 WP 系列 | http://repec.org/ | 2026-09-26 |
| 53 | ASSA 2026 程序：session 标有 JEL 码与主办学会（含 AFA）；论文页含作者、机构与摘要，部分有 "Download Preview (PDF)"；程序可按学会或按日下载 | 确认 | https://www.aeaweb.org/conference/2026/program ；https://www.aeaweb.org/conference/2026/program/1063 | 2026-09-26 |
| 54 | NBER SI 2026 页面列有 50 个 `si-2026-*` 分会链接 | 确认（会期 2026-07-13 至 07-31） | https://www.nber.org/conferences/summer-institute-2026 | 2026-09-26 |
| 55 | SFS robots 禁 `/acceptedpaper`、`/portal`、`/wp-content` | 确认 | https://sfs.org/robots.txt | 2026-09-26 |
| 56 | AEA：2027 年机构价 Tier1 $3,715、Tier2 $1,370；2024-02-01 起停售纸本；订阅页未把 JEP/JEL 列为免费 | 确认 | https://www.aeaweb.org/journals/subscriptions | 2026-09-26 |
| 57 | OpenAlex：JEP 2025 年 diamond 占 100%，JEL green 占 12% | 确认（JEP n=37 全部为 diamond；JEL n=75，closed 66、green 9） | https://api.openalex.org/works?filter=primary_location.source.issn:0895-3309,publication_year:2025,type:article&group_by=open_access.oa_status | 2026-09-26 |
| 58 | §2.8 刊级 Crossref 计数与摘要覆盖率（抽查 26 刊：JFE、AMJ、ASQ、JF、SMJ、JOM、QF、JAP、TAR、MISQ、MS、QJE、JMIS、JFQA、JEP、JEL、JPE、POM、Experimental Economics、CFR、JPM、MIT SMR、Econometrica、AOM Proceedings、JPE Micro/Macro）；HBR 的 ISSN 返回 404 | 确认（26 刊逐项一致）。publisher 字段：POM 为 SAGE、Experimental Economics 为 CUP、CFR 为 Emerald (MCB UP)、JPM 为 With Intelligence LLC | https://api.crossref.org/journals/{ISSN} | 2026-09-26 |
| 59 | OpenAlex 摘要抽样：JFE 2026-09 新文缺摘要；AMJ 2025 为 23/25；JFE 2024 为 10/25 | 确认 | https://api.openalex.org/works/doi:10.1016/j.jfineco.2026.104355 ；https://api.openalex.org/works?filter=primary_location.source.issn:0001-4273,publication_year:2025,type:article&per-page=25&select=doi,abstract_inverted_index | 2026-09-26 |
| 60 | JSTOR Constellate 于 2025-07 停运（v1 记录） | 确认（2025-07-01 停运） | https://github.com/ithaka/constellate-notebooks | 2026-09-26 |
| 61 | Cambridge Core 的 `/robots.txt` 本身返回 403 `cf-mitigated: challenge` | 确认（已停手） | https://www.cambridge.org/robots.txt | 2026-09-26 |
| 62 | econometricsociety.org 的 robots 具名禁 ClaudeBot 等 | 确认（Last-Modified 2025-05-02） | https://www.econometricsociety.org/robots.txt | 2026-09-26 |
| 63 | Wiley 与 T&F robots：GPTBot 全禁（Wiley 另禁 Google-Extended），Crawl-delay 1；T&F 禁 `/doi/epdf/*` | 确认 | https://onlinelibrary.wiley.com/robots.txt ；https://www.tandfonline.com/robots.txt | 2026-09-26 |
| 64 | 其他 robots：HBS Crawl-delay 2；IDEAS 仅禁 `/cgi-bin/`；AISeL 禁 `/do/`；WFA 主站宽松 | 确认 | https://www.hbs.edu/robots.txt ；https://ideas.repec.org/robots.txt ；https://aisel.aisnet.org/robots.txt ；https://westernfinance.org/robots.txt | 2026-09-26 |
| 65 | AOM、Emerald、AAA、MISQ 的 TDM 与自动下载条款 | 未核验（AOM 与 Emerald 企业站 FAQ 返回 403，本轮未找到可达的一手条款） | https://www.emeraldgrouppublishing.com/news-and-press-releases/emerald-publishing-joining-wiley-frequently-asked-questions | 2026-09-26 |
| 66 | OUP、AAA、MISQ 的 robots 同属 Silverchair 模板（只有 `*` 与 `User-agent: 008` 两组，无 AI 条目）；UChicago robots 为 Crawl-delay 1，含 GPTBot 条目 | 确认 | https://academic.oup.com/robots.txt ；https://publications.aaahq.org/robots.txt ；https://misq.umn.edu/robots.txt ；https://www.journals.uchicago.edu/robots.txt | 2026-09-26 |

### 核验补充条目（覆盖缺口，已写入正文并标注"核验补充"）

| # | 补充条目 | 写入位置 | 依据来源 URL | 证据级 | 核验日期 |
|---|---|---|---|---|---|
| S1 | **SSRN 许可选择**：2026-07 起投稿可选 CC BY、BY-NC、BY-NC-ND、CC0 或保留全部权利。Crossref 已登记 license：2026-07-20 后新建的 76,405 条中 69,436 条带 license，其中全部权利保留 56,335、CC BY 6,875、BY-NC-ND 3,887、BY-NC 2,053、CC0 286 | 摘要 1、§2.1#2、§2.4 ssrn、§3-4、§4-16 | https://blog.ssrn.com/2026/07/20/ssrn-will-now-allow-you-to-choose-the-licence-thats-right-for-your-work/ ；https://api.crossref.org/prefixes/10.2139/works?rows=0&filter=from-created-date:2026-07-20&facet=license:* | SNIPPET + LIVE | 2026-09-26 |
| S2 | **FT50 2026 修订**（见上表 #40） | 摘要 10、§2.7、§3-10、§4-5 | 同 #40 | DOC（二手） | 2026-09-26 |
| S3 | **MIT SMR**：2026-05-06 宣布停办；2026-09-10 更新为秋季刊后停印，数字内容持续到 2026-11，冬季推出纯数字新版，存档保留 | 摘要 11、§2.3 mit_smr、§2.8、§3.1、§4-17 | https://mitsloan.mit.edu/press/update-mit-sloan-management-review ；https://poetsandquants.com/2026/05/06/mit-sloan-management-review-to-shut-down-after-67-years/ | DOC | 2026-09-26 |
| S4 | **Wiley 收购 Emerald**（2026-06-02，£337m，约 $452m）；Emerald 此前于 2025-05-06 收购 now publishers（14 刊与 28 种 Foundations and Trends 系列，含 CFR） | 摘要 11、§2.2、§2.3 emerald、学会→平台、§2.8 CFR、§4-4/10 | https://newsroom.wiley.com/press-releases/press-release-details/2026/Wiley-Acquires-Emerald-Expanding-Research-Scale-and-Deepening-Proprietary-Content-Across-the-AI-Driven-Knowledge-Economy/default.aspx ；https://librarytechnology.org/pr/31323 | DOC | 2026-09-26 |
| S5 | **SAGE TDM/AI 政策**：对合法可访问内容做非商业 TDM 无需另签许可；AI 用途（含生成式）须另获许可；建议经 Crossref API 取全文链接。TDM 许可页限速：PT 工作日 0–12 时每 6 s 1 次，其余时段每 2 s 1 次 | §2.3 sage、§4-4 | https://www.sagepub.com/tdm-ai-policy ；https://journals.sagepub.com/page/policies/text-and-data-mining-license | DOC / SNIPPET | 2026-09-26 |
| S6 | **INFORMS PubsOnLine 使用条款**：未经批准禁止以机器人或自动流程系统性下载；离线浏览器每分钟不超过 20 页；违规封禁 | §2.3 informs、YAML 示例、§4-4 | https://www.informs.org/Publications/Librarians-Portal/PubsOnLine-Terms-and-Conditions | SNIPPET ⚠（原文 CF 挑战，需复核） | 2026-09-26 |
| S7 | **OpenAlex 改为 API key + 按量计费**：注册 key 每日 $1 免费额度；无 key 请求仍可用但额度极小，实测请求头 `x-ratelimit-limit-usd: 0.1`，list 请求单价 $0.0001 | 摘要 11、§2.6 crossref 行、§4-17 | https://help.openalex.org/access/pricing/ | DOC + LIVE | 2026-09-26 |
| S8 | **Crossref 2026 公共数据文件**：2026-03-17 发布，约 1.8 亿条，压缩后 208 GB | §2.6 crossref 行、§4-8 | https://www.crossref.org/blog/2026-public-data-file-now-available/ | DOC | 2026-09-26 |
| S9 | **EconLit（AEA）**：200 万+ 条记录，JEL 编码，只能订阅，未见公开 API | §2.6 新增 econlit 行 | https://www.aeaweb.org/econlit/ | DOC | 2026-09-26 |
| S10 | **VHB-Rating 2024**：2024-04-18 发布，取代 JOURQUAL3，含 18 个领域评级，官方不编制总排名 | §2.7 vhb2024 | https://www.vhbonline.org/en/services/vhb-rating-2024 | DOC | 2026-09-26 |
| S11 | **ABDC 声明**：唯一有效的可检索 JQL 由 ABDC 发布，其他工具未经授权 | 摘要 10、§2.7 abdc、§3-10、§4-5 | https://abdc.edu.au/abdc-journal-quality-list/ | DOC | 2026-09-26 |

### 核验统计与残余风险

- **核验断言**：66 组。确认 56 组；修正 7 组（#15、#16、#32、#36、#37、#40、#52）；未核验 3 组（#8、#28、#65）；删除 0 组。未发现编造的仓库、产品、论文或公司。原文中带数字的 Crossref/OpenAlex 实测值在抽查范围内全部可复现，小幅增长属当日新增数据。
- **核验补充**：11 条（S1–S11）。
- **残余风险**：
  1. SSRN 的 ToU、战略更新和许可博客都只有 SNIPPET 级证据，§3-4 的结论依赖 ToU 措辞，需在可达网络逐字复核。
  2. INFORMS 使用条款只有摘要级证据。
  3. Wiley 收购 Emerald 后，平台和 AI 授权政策可能变化。
  4. FT50 修订版名单依赖二手来源，FT 原文未取得。
  5. OpenAlex 的计费细则仍可能调整。
