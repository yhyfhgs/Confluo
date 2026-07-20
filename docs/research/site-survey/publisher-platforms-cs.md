---
title: 站点勘察：CS 学会与其他出版平台（IEEE/AEA/SIAM/MIT Press）
status: approved
owner: fable5
updated: 2026-07-20
---

# 站点勘察 · IEEE / AEA / SIAM / MIT Press

> 来源：Sonnet subagent 于 2026-07-20 实测（curl+WebFetch，38 次工具调用；精简版——首轮大范围勘察 agent 两次因 API 中断失败后缩小范围重派）。提炼结论已并入相关 adapter 文档与 publishers-platforms.md。
> INFORMS/Springer 未在本轮（云 IP 拒连已在 publishers-platforms §网络层现实记录；Springer journal-id 映射此前已 [LIVE]）。

## IEEE Xplore（ieeexplore.ieee.org）

- **robots.txt**（[LIVE]，curl；WebFetch 被 418 拦截）：通用 UA 禁 `/rest`、`/ielx*`；**AI 爬虫大面积封禁**——GPTBot、Google-Extended、**ClaudeBot、Claude-User**、Google-NotebookLM、Perplexity 系、MistralAI 系、CCBot、Amazonbot、Applebot-Extended、ByteSpider、PetalBot、ResearchGateBot 等 25+ UA 均 `Disallow: /`；无 crawl-delay。
- **API**：developer.ieee.org——元数据 API + **新上线全文 API**（全文需联系销售代表）；注册账号+说明用途+机构网址申请 key，**人工审批**（工作日 8:00–17:00 ET 发放）；条款限机构内非商业教育/科研用途；配额未核验。
- **URL 模式**（TPAMI punumber=34 例，[LIVE]）：期刊页 `xpl/aboutJournal.jsp?punumber=34`；当期 TOC `xpl/mostRecentIssue.jsp?punumber=34`；文章 `/document/9910340`；**PDF `stampPDF/getPDF.jsp?arnumber=9910340`**（加水印版，需登录）。
- **认证**：Shibboleth/OpenAthens（"Institutional Sign-In"，需图书馆员预注册）+ IP 段识别。
- **开放**：IEEE Access 等 gold OA 刊免费（open.ieee.org）；其余订阅。

## AEA（aeaweb.org）

- **robots.txt**（[LIVE]，双工具确认）：**仅两条**——GPTBot 与 Amazonbot `Disallow: /`；无通用 Disallow、无 crawl-delay——四平台中最宽松。
- **API**：无官方 API/批量接口；AEA Data and Code Repository（openICPSR）只存复现数据非全文；TDM 书面政策未核验。
- **URL 模式**（AER 例，[LIVE]）：期刊页 `/journals/aer`；卷期 TOC `/issues/853`（**不透明期号**，需从期刊页解析）；文章 `/articles?id=10.1257/aer.20180338`；**PDF `/articles/pdf/doi/10.1257/aer.20180338`**（非免费刊需登录）。
- **认证**：未见 Shibboleth/OpenAthens 明确证据，推测 IP 段为主 ⚠ 未核验。
- **开放**：**JEP 全刊完全免费**（官方 "publicly accessible at no charge"）；AER/AEJ 系/JEL 订阅制。

## SIAM（epubs.siam.org）

- **robots.txt**（[LIVE]）：Atypon 通用路径禁（/action /search /doi/metrics/ /history/ 等 + Allow 白名单）；**仅 GPTBot 点名**；`Crawl-delay: 1`；社交爬虫全站 Allow。
- **平台栈确认 = Atypon/Literatum**（与 Wiley/INFORMS/UChicago 同族）。
- **API/TDM**：无公开 API/独立 TDM 政策页；个案邮件 service@siam.org ⚠ 条款未核验。
- **URL 模式**（SODA 2023 例，[LIVE]）：会议卷=book `doi/book/10.1137/1.9781611977554`（TOC 即 book 页章节列表，无独立 URL）；章节 `doi/10.1137/1.9781611977554.ch1`；**PDF `doi/pdf/...ch1?download=true`**（另有 `/doi/epdf/` 阅读器）。
- **认证**：Shibboleth（`/action/ssostart`）+ 账号登录；OpenAthens 未见专页（Atypon 惯例支持 ⚠ 未核验）。
- **开放**：SIURO 开放获取；其余订阅。

## MIT Press Direct（direct.mit.edu）

- **REStat 确认在 direct.mit.edu**，期刊代码 `rest`（此前 catalog ⚠ 已解决）；平台=Silverchair（article-pdf URL 通例同 OUP）。
- **robots.txt**（[LIVE]，curl；WebFetch 403）：UA `008` 全禁；通用 UA 禁 /bin/ /signin.aspx /DownloadFile/ **/Shibboleth.sso/** /store/* 等；**无 AI-bot 专项条目**；3 个 sitemap；无 crawl-delay。
- **⚠ 合规关键（TDM 条款，转引自其机构许可协议页，直接抓取被 403）**：TDM 仅限"机构订阅方获 MIT Press **书面特批**"（免费但须申请）；限非商业学术用途；**明确禁止用脚本/爬虫抓取站内内容**；未经书面许可不得用于 AI 训练。
- **URL 模式**（[LIVE]）：期刊页 `/rest`；卷期 `/rest/issue/104/3`；文章 `/rest/article/104/3/i/111062/...`；PDF `{code}/article-pdf/{vol}/{iss}/{page}/{fileid}/{code}_a_{id}.pdf`（Silverchair 通例；rest 具体文件名未核验）。
- **认证**：Shibboleth（robots 路径证实）；OpenAthens ⚠ 未核验。
- **开放**：D2O 只覆盖**书籍**非期刊；REStat 订阅制。

## 对 adapter 设计的直接结论

1. **ieee_xplore**：元数据绝不爬页面（robots 大面积禁 AI + 通用禁 /rest）——走 DBLP/Crossref + 官方元数据 API（申请制）；全文出口更新为 `stampPDF/getPDF.jsp?arnumber=`；OJ 系 gold OA 刊可免登录。
2. **aea**：robots 宽松 + JEP 免费；issue 号不透明需解析；PDF 直链规整（`/articles/pdf/doi/{doi}`）——实现难度低。
3. **siam**：挂 `atypon_base`；SODA 卷=book 结构（章节遍历），与期刊型 Atypon 站枚举逻辑不同。
4. **mit_press**：**须遵守其"禁脚本抓取；TDM 需书面特批"条款**——设计定位降为"按需单篇（用户交互式触发）+ 引导申请 TDM 特批后才允许批量"；默认日配额最低档；catalog 对 REStat 标注此获取边界。
