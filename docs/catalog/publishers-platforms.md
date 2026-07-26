---
title: 平台 → Adapter 映射总表
status: approved
owner: fable5
updated: 2026-07-27
---

# 平台 → Adapter 映射总表

> D-002 的骨架：期刊/会议高度平台化，一个 adapter 服务一族 venue。本表是"为什么只需 ~40 个 adapter（首批实现 16 个 + planned）就能覆盖数百 venue"的证据。（D-002 原估 15~25，经全量 catalog 盘点后修正为 ~40，见 D-015。）
> 反爬列来自 research/site-survey [LIVE] 勘察（2026-07-20）。

## Open-Access 平台（无需认证）

| adapter | 平台域 | 服务 venue（例） | 接口/bulk | 反爬 | 备注 |
|---|---|---|---|---|---|
| `arxiv` | export.arxiv.org / oaipmh.arxiv.org | arXiv 全站 | Query API + OAI-PMH + Kaggle/S3 bulk | 1req/3s ToU；listing 15s | 分类切 venue |
| `ssrn` | papers.ssrn.com | SSRN eJournals | 浏览页（无 API） | **Cloudflare**；5s；禁 GPTBot | 浏览器抓取，D-011 |
| `openreview` | api2/api.openreview.net | ICLR、CoRL、NeurIPS 评审 | REST API + openreview-py | 无 | v1/v2 双端点 |
| `pmlr` | proceedings.mlr.press | ICML、AISTATS、COLT、UAI、CoRL | 卷页 + bib | 无 | 卷号↔年映射表 |
| `cvf` | openaccess.thecvf.com | CVPR、ICCV、WACV | 目录页（静态） | 无 | 2013+ |
| `acl_anthology` | aclanthology.org + GitHub | ACL、EMNLP、NAACL、COLING、EACL | **GitHub 数据仓库 bulk** | 无 | Anthology ID |
| `neurips_proceedings` | proceedings.neurips.cc | NeurIPS 正式 | 年页（静态） | 无 | 1987+ |
| `aaai_ojs` | ojs.aaai.org | AAAI、AIES | OJS，主路径 **OAI-PMH**（`ListRecords`+`resumptionToken`；REST API 匿名 403 不可用） | 无 | 2019+ 已注册（volume_map），2010–2018 同构可收割待裁决扩容——见 design/adapters/aaai-ojs.md §10 |
| `acm_dl` | dl.acm.org | KDD、WWW、WSDM、CIKM、SIGIR、RecSys、STOC、SOSP、EC、SIGMOD | DOI 结构 | — | **2026 起全面 OA（D-013）** |
| `lipics` | drops.dagstuhl.de | ITCS(2017+) | 卷页 + DOI 10.4230 | 无 | OA |
| `usenix` | usenix.org | OSDI、NSDI | 会话页（静态） | 无 | 全 OA |
| `pvldb` | vldb.org/pvldb | VLDB(2008+) | 卷页 | 无 | CC BY-NC-ND |
| `isca` | isca-archive.org | INTERSPEECH | 归档页 | 无 | 含前身刊 |
| `rss_proceedings` | roboticsproceedings.org | RSS | `/rss{NN}/` | 无 | 极规整 |
| `nber` | nber.org / back.nber.org | NBER WP | program RSS | 无 AI 封禁 | >18月开放 |
| `econsoc` | econometricsociety.org | TE、QE、ECMA(当前段；过刊段归 wiley，D-028) | 站点 | 无 | TE/QE 全开放 |
| `repec` | ftp.repec.org / oai.repec.org | Econ WP 元数据主干 | **FTP/OAI-PMH bulk** | 宽松 | 覆盖 NBER/CEPR 书目 |

## Aggregator（元数据/发现层）

| adapter | 平台 | 用途 | 认证 | 限速[LIVE] |
|---|---|---|---|---|
| `crossref` | api.crossref.org | **期刊枚举主干**（ISSN+日期） | 无（polite 需 mailto） | polite 10req/s 并发3 |
| `dblp` | dblp.org | **会议枚举主干**（conf XML）+ VenueEra 历史 | 无 | ~1-2s；429 退避；重活用 dump |
| `openalex` | api.openalex.org | 摘要补全、OA 链接、topics | **免费 key（信用制）** | 10k credits/天(免费key) ⚠2026-02 改制 |
| `s2` | api.semanticscholar.org | 引用、TLDR、领域标签 | 需申请 key | 1 req/s |
| `unpaywall` | api.unpaywall.org | OA 副本发现（按 DOI） | email 参数 | 100k/天 |
| `core` | api.core.ac.uk | 次级 OA 全文兜底 | 免费 key | ~5 单请求/10s |

## Auth-Gated 平台（需用户自有凭证）

| adapter | 平台域 | 服务 venue（例） | 推荐档 | 反爬[LIVE] | DOI 前缀 |
|---|---|---|---|---|---|
| `elsevier_sd` | sciencedirect.com | JFE、JME、JET、JBF、JFI、JFM、JEDC、EJOR、JoE(计量) | **官方 API** | **Cloudflare 深集成**；robots 默认全禁+AI 三类治理（含 claude-code）；TDMRep | 10.1016 |
| `wiley` | onlinelibrary.wiley.com | JF、ECMA、RAND、JEEA、MathFin、Econ Journal、IER | **TDM API**(api.wiley.com, ~3req/s) → cookie | Cloudflare；robots 宽松（仅 GPTBot/G-Ext 点名） | 10.1111/10.1002 |
| `oup_silverchair` | academic.oup.com | QJE、RFS、REStud、RF、EJ、JFEc、RAPS、JEEA(部分) | cookie | Silverchair；CF 质询；robots 无 AI 条目；无 TDM API | 10.1093 |
| `uchicago` | journals.uchicago.edu | JPE、JOLE、JLE | cookie(epdf 出口) | **Atypon（[LIVE]确认）**；CF；批量下载需事先许可 | 10.1086 |
| `informs` | pubsonline.informs.org | MS、OR、M&SOM、IJOC、MOR、Marketing Sci | cookie | Atypon；CF/WAF（云 IP 拒连） | 10.1287 |
| `ieee_xplore` | ieeexplore.ieee.org | ICASSP、ICRA、IROS、ICDM、FOCS、TPAMI、TAC | browser(`stampPDF/getPDF.jsp`) | robots 禁 25+ AI-bot（含 ClaudeBot）；conhome 逐年随机；官方元数据 API 申请制 | 10.1109 |
| `siam` | epubs.siam.org | SODA、SIAM 刊 | cookie | **Atypon（[LIVE]确认）**；仅 GPTBot 点名；Crawl-delay 1；SODA=book 结构 | 10.1137 |
| `sage` | journals.sagepub.com | **POM**（[LIVE]确认 SAGE 非 Wiley） | cookie | Cloudflare（风险评分制） | 10.1177 |
| `aea` | aeaweb.org | AER、AEJ 系、JEL、JEP(免费) | cookie | robots 极宽松（仅 GPTBot/Amazonbot）；issue 号不透明；**JEP 全刊免费**[LIVE] | 10.1257 |
| `cambridge` | cambridge.org/core | JFQA、Econometric Theory、ET | cookie | CF 前置+Varnish（[LIVE]直连未触发质询）；SSR 可读；**issue 用 32 位不透明 ID**；TDMRep | 10.1017 |
| `springer` | link.springer.com | Math Programming、Finance & Stochastics、Annals of OR、ECCV、WINE | cookie | 云 IP TLS 拒连[LIVE] | 10.1007 |
| `mit_press` | direct.mit.edu | **REStat（[LIVE]确认，code=rest）** | cookie | Silverchair；**TDM 需书面特批+明文禁脚本抓取**→仅按需单篇 | 10.1162 |
| `jstor` | jstor.org | 历史过刊兜底（EJC 开放：US 1923 前） | browser | **Fastly+PerimeterX**（非 CF）；robots 点名禁 ClaudeBot/CCBot；Constellate 已停运(2025-07) | 10.2307 |
| `pm_research` | pm-research.com | JPM、Journal of Derivatives、JFDS | browser | 小平台谨慎 | 10.3905 |

## 平台归属易错点（调研纠偏）

- **POM = SAGE**（journals.sagepub.com，DOI 10.1177），非 Wiley、非 INFORMS——POMS 官网残留旧 Wiley 表述已过时（[LIVE] 四重验证）。
- **SODA = SIAM**（epubs.siam.org），非 ACM DL——不受 ACM 2026 OA 覆盖；且 SODA 卷在 SIAM 是 **book 结构**（`doi/book/10.1137/1.{isbn}` + `.ch{N}` 章节），枚举逻辑与期刊型不同。
- **ICDM/FOCS = IEEE**，非 ACM。
- **REStat = MIT Press 已确认**（direct.mit.edu/rest，Silverchair 系，[LIVE] 2026-07-20）；注意其 TDM 条款禁脚本抓取（获取边界=按需单篇）。
- **UChicago Press = Atypon 已确认**（robots 与 Wiley 同构 + 同款 CF 模板，[LIVE]）；其 PDF 出口为 epdf 阅读器（无静态 /doi/pdf/ 直链）。
- ECMA(Econometrica) 由 Wiley 出版但归 Econometric Society；TE/QE 同学会但**开放获取**（econsoc adapter）。
- **JSTOR 防护栈是 Fastly+PerimeterX**（非 Cloudflare），且 robots 点名禁 ClaudeBot——兜底地位仅限用户认证态的低量人工触发（D-014 口径）。

## 一个平台多刊的杠杆效应（NFR-1 证据）

`oup_silverchair` 一个 adapter 覆盖 QJE+RFS+REStud+RF+EJ 等 5+ 顶刊；`elsevier_sd` 覆盖 JFE+JME+JET+EJOR 等 10+ 刊；`informs` 覆盖 MS+OR+MSOM+IJOC+MOR 全部 INFORMS 刊。→ 新增同平台刊=写 YAML（≤30 分钟）。

## ⚠ 网络层现实（[LIVE] 勘察，强化 D-005）

多个出版社平台对**数据中心/云主机出口 IP 直接在 TCP/TLS 层拒绝连接**（比 Cloudflare JS 挑战更硬）：
- `link.springer.com`：TLS 握手即 reset（数据中心 IP）；
- `pubsonline.informs.org`：三种工具多次连接失败；
- `sciencedirect.com`、`journals.sagepub.com`：Cloudflare 403。

**设计含义**：(1) discover/enumerate 一律走聚合 API（Crossref/DBLP，云 IP 可达），不从这些站点页面枚举；(2) fetch 全文需在**用户机构网络/家庭 IP + 真实登录 session** 下进行——auth_gated 模块本就假设用户自有网络与凭证，与此现实一致；(3) CI/canary 的 auth 族只在用户本机跑（test-plan §8）。

## Springer journal-id 映射（`/journal/{id}` 结构，[LIVE]）

Springer 用数字 journal-id 组织：Mathematical Programming=10107（ISSN 0025-5610/1436-4646）、Annals of OR=10479（0254-5330/1572-9338）、Math Programming Computation=12532。URL：目录 `/journal/{id}/volumes-and-issues/{vol}-{issue}`、文章 `/article/10.1007/{suffix}`、检索 RSS `link.springer.com/search.rss?query=&facet-journal-id={id}`、订阅 alert `springer.com/alerts-frontend/subscribe?journalNo={id}`。认证 Shibboleth + OpenAthens。
