---
title: 站点勘察：经济金融闭源出版社六平台（Elsevier/Wiley/OUP/UChicago/Cambridge/JSTOR）
status: approved
owner: fable5
updated: 2026-07-20
---

# 站点勘察 · Econ/Fin 闭源出版社平台

> 来源：Sonnet subagent 于 2026-07-20 实测（curl 直连 robots.txt/响应头 + WebFetch/WebSearch 交叉验证，75 次工具调用）。[LIVE] 为当日直接测试；"转引"为二手来源（图书馆指南等），官方原文被 Cloudflare 拦截未直接核验。
> 提炼结论已并入各 adapter 文档与 publishers-platforms.md。

## Elsevier ScienceDirect

- **robots.txt**（[LIVE]，自称 Last updated: June 2026）：默认"先禁后放"——`User-agent: * / Disallow: /`；具名放行的搜索引擎仍禁 `*/pdfft*`、`/sdfe/pdf/download/*`、`/search*` 等。AI 治理三类：①训练类全禁 30+ UA（GPTBot、ClaudeBot、CCBot、Bytespider、Amazonbot…）；②AI 检索类多数禁：ChatGPT-User、Claude-User、**claude-code**、PerplexityBot 等；③仅 OAI-SearchBot 与 Claude-SearchBot 显式 Allow（保留 AI 搜索引用）。无 Crawl-delay。
- **TDMRep 协议**（[LIVE]）：全站响应头 `tdm-policy: .../tdmrep-policy.json` + `tdm-reservation: 1`；policy 规定 `stm:eu-dsm-article3`（欧盟科研例外）可挖掘，否则 `obtainConsent`（tdm-license@elsevier.com）。
- **反爬**（[LIVE]）：Cloudflare 深度集成（`cf-mitigated: challenge`，403 + 835KB 定制验证页）——程序化客户端无法免挑战取页面。
- **官方 API（dev.elsevier.com，配额官方数字 [LIVE]）**：
  - **Article Retrieval API**：`GET api.elsevier.com/content/article/doi/{DOI}`（或 `/pii/{PII}`）；每周 **50,000 次、10 req/s**；**Text Mining 专用 key 不限量**；覆盖 "All Subscribed, OpenAccess and Complimentary Articles"；原生 XML。
  - **ScienceDirect Search API v2**：每周 20,000 次、2 req/s、单次 ≤200 条/总 6000 条。
  - 配额 7 天重置；`X-RateLimit-Limit/Remaining/Reset` 头；超限 429 + `X-ELS-Status: QUOTA_EXCEEDED`。
  - 申请条件：机构订阅关联的研究者免费（非商业）。
- **URL 模式**（[LIVE] 实例）：期刊 `/journal/journal-of-financial-economics`；卷期 `/journal/{name}/vol/146/issue/3`；文章 `/science/article/pii/S0304405X25001515`（摘要版 `/abs/pii/`）；**无匿名 PDF 直链**（pdfft/sdfe 路径对全部 UA Disallow）。
- **认证**：SeamlessAccess（Shibboleth/OpenAthens/SAML）；个人免费账号不解锁全文。
- **开放内容**：摘要免费；~700/2800 刊完全 OA；JFE/JME/JET/GEB/EJOR 均订阅+混合。

## Wiley Online Library

- **robots.txt**（[LIVE]）：`*` 组仅路径级限制（/action /search /doi/am-pdf/ /doi/metrics/ 等），**非全站禁**；AI 点名仅 **GPTBot、Google-Extended**（全禁）；ClaudeBot/CCBot 落入宽松通用组；社交预览 bot 显式 Allow；文件尾部孤立 `Crawl-delay: 1`（作用域含糊）。无 TDMRep。
- **反爬**（[LIVE]）：Cloudflare 通用质询（403 "Just a moment..."）。
- **TDM API**（转引 wolsupport.wiley.com + WileyLabs/tdm-client）：`GET https://api.wiley.com/onlinelibrary/tdm/v1/articles/{DOI}` + 头 `Wiley-TDM-Client-Token: {token}`；返回 PDF；限机构订阅范围；**~3 req/s**（另一口径 60 次/10 分钟）；流程=登录个人账号→click-through TDM 协议→取 token；TDM@wiley.com。⚠ 官方原文页被 CF 拦截未直接核验。
- **URL 模式**（[LIVE] 实例）：期刊 `/journal/15406261`（ISSN 去连字符）；卷期 `/toc/15406261/2025/80/1`；文章 `/doi/10.1111/jofi.13477`（`/doi/abs/`、`/doi/full/` 变体）；PDF `/doi/pdf/10.1111/jofi.13424`（无权限跳登录墙）。
- **认证**：Institutional Login（Shibboleth/OpenAthens 联邦弹窗）；**JF 的 AFA 会员通道**（会员含期刊访问，个人路径，未逐条核验现行条款）。
- **开放内容**：摘要公开；JF/ECMA/RAND 订阅制。

## OUP / Silverchair（academic.oup.com）

- **robots.txt**（[LIVE]）：**无任何 AI bot 专门条目**、无 Crawl-delay；`*` 组仅禁后台/登录（`/Shibboleth.sso/` 印证 SP 部署）/搜索/下载/引文导出等路径。无 TDMRep（/.well-known/tdmrep.json 404）。
- **反爬**（[LIVE]）：Cloudflare 通用质询 403。
- **API/TDM**：**无公开 TDM API**；非商业 TDM 含在机构订阅条款内；商业需单独协议；Data.Mining@oup.com（转引 Bodleian/Georgetown 图书馆指南）。
- **URL 模式**（[LIVE] 实例）：期刊 `/qje`；卷期 `/qje/issue/140/1`；文章 `/qje/article/{vol}/{iss}/{page}/{silverchair_id}`（如 `/qje/article/141/3/2205/8662148`）；**PDF `/qje/article-pdf/{vol}/{iss}/{page}/{file_id}/qjae044.pdf`**（file_id 不可构造，须从文章页解析）。
- **认证**：Sign in via your institution（SeamlessAccess，Shibboleth/OpenAthens）；部分刊有个人订阅与单篇购买。
- **开放内容**：摘要免费；Oxford Open 混合；QJE/RFS/REStud/RoF 订阅制。

## University of Chicago Press（journals.uchicago.edu）

- **⚡ 平台栈确认 = Atypon Literatum**：robots.txt 与 Wiley **高度同构**（同一套 /action /doi/mlt/ /doi/metrics/ 禁止清单与 Allow 清单）+ 同款 Cloudflare 质询模板——判定与 Wiley 共用 Atypon 平台（此前 catalog 中 "Atypon/Silverchair 待辨" 的答案）。
- **robots.txt**（[LIVE]）：AI 点名仅 GPTBot；孤立 `Crawl-delay: 1`；**显式 `Allow: /.well-known/tdmrep.json`** 且 TDMRep 生效（[LIVE]：301→`/pb-assets/.well-known/tdmrep.json` 200，`tdm-reservation:1`；policy JSON 本身又被 CF 拦——防护按路径动态触发）。
- **API/TDM**：**无公开 API**；UChicago 图书馆 TDM 指南原话：允许 text mining，但**自动化批量下载软件须事先向出版社申请许可**。
- **URL 模式**（[LIVE] 实例）：期刊 `/journal/jpe`；卷期 **`/toc/jpe/{year}/{vol}/{issue}`（含年份**，如 `/toc/jpe/1896/4/3`）；文章 `/doi/full/10.1086/734341`（`/doi/abs/` 变体）；**PDF 走 `/doi/epdf/10.1086/{id}` 增强阅读器——Atypon 此站不暴露纯静态 `/doi/pdf/` 直链**（需 entitlement 的 epdf）。
- **认证**：Atypon 登录体系（Institutional Account 绑定 Shibboleth Entity ID，InCommon 联邦）；journalsupport@press.uchicago.edu。
- **开放内容**：摘要免费；JPE/JOLE 订阅制。

## Cambridge Core

- **robots.txt**（[LIVE]，整域）：点名禁 Yandex、ChatGPT-User、"ChatGPT"（非标准 token）；**无 ClaudeBot/CCBot/GPTBot(标准名) 条目**；`*` 组仅禁后台/结账/登录；**显式放行 PDF 服务端点** `/core/services/aop-cambridge-core/content/view/`。无 Crawl-delay。
- **反爬**（[LIVE]）：Cloudflare 前置 + Varnish 源站；**本次直连 200 未触发质询**（六平台唯一）；Vue/Nuxt SSR，原始 HTML 含元数据/摘要（无需 JS 执行）。高频/异常 IP 仍可能触发质询（tdm-policy.json 端点即遇 503/质询）。
- **TDMRep**（[LIVE]）：生效（`tdm-reservation:1`）；policy 同 Elsevier 格式：eu-dsm-article3 可挖掘否则 obtainConsent（business.development@cambridge.org）。ToU：合法访问前提下允许非商业 TDM，大规模项目联系 openresearch@cambridge.org。**无公开 API**。
- **URL 模式**（[LIVE] 实例）：期刊 `/core/journals/journal-of-financial-and-quantitative-analysis`；**卷期 ID 为 32 位不透明十六进制**（`/issue/C8535831B53058C7A75DEF226C6EC10F`，不可拼构，需从 `/all-issues` 页解析）；文章 `/article/{slug}/{32hex}`（无权限 302 → `/article/abs/`）；PDF `/core/services/aop-cambridge-core/content/view/{contentId}/S0022109026103123a.pdf`（contentId + DOI 后缀 + `a.pdf`）。
- **认证**：Shibboleth（shibboleth.cambridge.org WAYF）+ OpenAthens Federation；免费账号仅书签/提醒。
- **开放内容**：摘要免费（若有）；JFQA/ET 订阅制；OA 聚合页 `/core/publications/open-access`。

## JSTOR

- **robots.txt**（[LIVE]）：极严——连 `/doi/abs`、`/stable/view`、`/citation`、`/api` 都禁；仅 Allow 少量导航端点；文件尾部**点名封禁 ClaudeBot、CCBot、GPTBot、Google-Extended**（每条附官方文档注释链接，治理意图明确）。
- **反爬**（[LIVE]）：**Fastly/Varnish + PerimeterX**（`_pxhd` cookie 签发；非 Cloudflare/Akamai——六平台唯一例外）；403 "JSTOR: Access Check"。
- **API/TDM**：**Constellate 已于 2025-07-01 停运**（官方原话）；现役=JSTOR Text Analysis Support：**人工申请制**（免费账号→JSONL 元数据→提交清单→人工审核→邮件下载链接 60 天失效；单次 <1.5M items）——**无可编程实时 API**。
- **URL 模式**（[LIVE] 实例）：期刊 `/journal/jpoliecon`（短别名）；卷期不透明 ID 三代并存（`/stable/i331689`、`/stable/e26550379`、`/stable/10.1086/jpe.1999.107.issue-4`，均需从 TOC 解析）；文章 `/stable/2937956`；PDF `/stable/pdf/{id}.pdf`（无权限重定向）。
- **认证**：Shibboleth/OpenAthens；个人：**JPASS**（年付）或**免费注册 100 篇/30 天在线阅读**（开放内容不计额）。
- **开放内容**：Early Journal Content（US 1923 前/其他 1870 前，~66 万篇）永久免费；现代内容有 **moving wall**（最近数年不上 JSTOR，各刊年限未逐一核验）。

## 跨平台速览（adapter 设计口径）

| 平台 | CDN/WAF | 点名禁 Claude 系 | 可编程 API | 全文合规路径 |
|---|---|---|---|---|
| ScienceDirect | Cloudflare（深度集成） | **是（含 claude-code）** | **有**（配额官方数字齐备） | 官方 API（首选）/机构认证态 |
| Wiley | Cloudflare | 否（仅 GPTBot/G-Ext） | **有**（TDM，~3 req/s） | TDM API / 机构认证态 |
| OUP | Cloudflare | 否（无 AI 条目） | 无 | 机构认证态 |
| UChicago（**Atypon 确认**） | Cloudflare | 否（仅 GPTBot） | 无（批量需事先许可） | 机构认证态（epdf） |
| Cambridge | CF 前置+Varnish（未触发质询） | 否 | 无（ToU 允许非商业 TDM） | 机构认证态 |
| JSTOR | Fastly+**PerimeterX** | **是（逐条注释）** | 无（Constellate 停运） | 机构认证态/JPASS/人工数据集申请 |

**共同结论**：六家真实文章/PDF 层均无匿名直链；全文获取收敛到"机构认证态"或"官方 TDM/API 令牌"两条合规路径——与 D-005/D-006 架构假设完全一致。
