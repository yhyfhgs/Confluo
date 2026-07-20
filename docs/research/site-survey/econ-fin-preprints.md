---
title: 站点勘察：Econ/Fin 预印本与工作论文（SSRN/RePEc/NBER/CEPR）
status: approved
owner: fable5
updated: 2026-07-20
---

# 站点勘察 · Econ/Fin 预印本与 WP

> 来源：subagent 于 2026-07-20 实测（[LIVE-TESTED] 标记为当日直接验证）。含合规敏感发现。

## ⚠ 合规敏感发现（先读，约束设计）

1. **CEPR robots.txt 明确点名禁止 `ClaudeBot`**（及 GPTBot/Amazonbot/CCBot），并设 Content-Signal `ai-train=no, use=reference`。→ 本系统对 CEPR 全文默认**不自动抓取**，仅用 RePEc 元数据；如需全文引导用户手动订阅访问。
2. **SSRN 有 Cloudflare bot 管理**[LIVE-TESTED]：`papers.ssrn.com` 触发"verify you are human"，stateless fetch 得 403；robots.txt 禁 GPTBot/ChatGPT-User/Google-Extended，crawl-delay 5s。→ SSRN 必须走浏览器上下文 + ≤1 req/5s（印证 D-011）。
3. **两个"非官方经验发现"明确不采纳**：SSRN 内部 `api.ssrn.com/papers/v1/papers/{id}`（未文档化）、NBER 对 <18 月论文静态 PDF 路径的软门可绕过——调研者已标注需伦理/ToS 审查。→ 设计层**禁止**依赖这两条（写入 AC-0 与 adapter 文档 quirks 禁区）。

## SSRN（Elsevier 所有）

- 结构：Networks（FEN 金融/ERN 经济/LSN 法律/PSN 政治…）→ 各含数十 eJournals（FEN ~30 个：Asset Pricing、Market Microstructure、Corporate Finance、Climate Finance…）；平台 1000+ eJournals。浏览 `ssrn.com/index.cfm/en/{network}/`、`.../fen-ejournals/`。
- abstract 页[LIVE]：`ssrn.com/abstract={id}`→`papers.ssrn.com/sol3/papers.cfm?abstract_id={id}`。下载 `Delivery.cfm/{filename}.pdf?abstractid={id}&mirid=1`（filename 内部约定）。
- 访问：个人作者上传免费无需登录；出版商定价的需登录+付费。无固定匿名配额（自适应按流量风控）。
- First Look：期刊预印本先行渠道（`.../{network}-first-look/`）；JFE/JAE 专属合作**未证实**。
- 无官方 API。
- **设计结论**：ssrn adapter 归 open_access，`auth_level: free_account_preferred`；枚举走 network/eJournal 浏览页 + 本地关键词过滤（无查询 API）；下载浏览器上下文内解析 Delivery token 即时用；Cloudflare 挑战→BLOCKED。

## RePEc / IDEAS / EconPapers（元数据最友好）

- 去中心：2000+ archive 贡献 ReDIF 元数据；IDEAS(`ideas.repec.org`) 与 EconPapers(`econpapers.repec.org`) 是同一数据的独立前端。5.4M+ 条目、4.8M+ 可全文（~89% 链出到源）。
- **不自托管全文**（CEPR 自有 `repec.cepr.org` 镜像等少数例外）；每条=元数据+摘要+指向源的下载链。
- Handle：`RePEc:aaa:ssssss:xxxxx`；NBER WP=`RePEc:nbr:nberwo`、CEPR DP=`RePEc:cpr:ceprdp`。
- 官方程序化通道（`ideas.repec.org/getdata.html`）：**FTP 批量**（`ftp.repec.org/opt/ReDIF/RePEc/`）、**rsync**（`rsync.repec.org`，需联系）、**OAI-PMH**（`oai.repec.org`，官方称"sometimes flaky"）。**官方强烈不建议爬网页**。
- RePEc API（`ideas.repec.org/api.html`）：**邮件申请门控**，JSON，功能如 getrecentpapers/getpubsfromwpseries，无搜索，非批量。CitEc API：`citec.repec.org/api/{type}/{handle}` XML，前 500 次免 key。
- robots[LIVE]：IDEAS 仅禁 `/cgi-bin/`，EconPapers 少数路径，均较宽松无 AI-bot 封禁。
- **设计结论**：repec adapter 归 open_access aggregator 类；作 Econ WP 元数据主干（含 NBER/CEPR 的书目），走 FTP/OAI-PMH bulk；全文仍回各源。

## NBER Working Papers

- URL[LIVE]：landing `nber.org/papers/w{n}`；PDF `nber.org/system/files/working_papers/w{n}/w{n}.pdf`（Drupal）。
- RSS[LIVE 可用]：全量 `nber.org/rss/new.xml`；**19 个 program 分 feed** `back.nber.org/rss/new{code}.xml`（Asset Pricing=`newap`、Corporate Finance=`newcf`、Monetary=`newme`、Public=`newpe`、Labor=`newls`… 全 19 个已列）。
- 访问策略[LIVE 当前]：**>18 月完全开放**；近期论文限机构 IP/订阅/记者/政府/低收入国 + 匿名 3 篇/年配额。
- 无官方 bulk API；元数据可经 RePEc `nbr:nberwo` bulk 获取。
- **设计结论**：nber adapter 归 open_access；枚举走 program RSS + landing 页；下载仅 >18 月开放部分；<18 月按策略提示（不利用软门）。

## CEPR Discussion Papers

- abstract 页公开[LIVE]：`cepr.org/publications/dp{n}`；全文**订阅/单篇付费**（实测非订阅价 £6.00，无 rolling embargo）。RePEc 镜像 `repec.cepr.org/repec/cpr/ceprdp/DP{n}.pdf` 实测 403。
- 无 API/bulk。robots 禁 ClaudeBot（见上）。
- **设计结论**：仅收 RePEc 元数据；全文不自动抓（合规）；catalog 标 `fulltext: subscription_manual`。

## 汇总：Econ/Fin 预印本源分级

| 源 | 元数据 | 全文 | 抓取方式 | 合规注意 |
|---|---|---|---|---|
| SSRN | 浏览页/本地过滤 | 多数免费 | 浏览器+5s 限速 | Cloudflare；禁 GPTBot |
| RePEc/IDEAS | **FTP/OAI bulk（首选）** | 链出 | bulk | 最友好 |
| NBER | program RSS | >18 月开放 | httpx | 软门不绕过 |
| CEPR | 经 RePEc | 订阅付费 | 仅元数据 | **禁 ClaudeBot** |
