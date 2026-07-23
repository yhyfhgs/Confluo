---
title: 站点勘察：AEA（aeaweb.org / pubs.aeaweb.org）— AER + AEJ 四系 + AER:Insights + JEL/JEP
status: approved
owner: fable5
updated: 2026-07-24
---

# AEA LIVE 勘察报告 [Phase 5 R0b]

- 勘察对象：`www.aeaweb.org`（发现/landing，Apache）+ `pubs.aeaweb.org`（全文平台，Atypon/Literatum + Cloudflare）；对照 `docs/catalog/economics-journals.md` AEA 系列段
- 勘察时间：2026-07-24
- UA：`PaperCrawler/0.1.0 (personal research; mailto:yhyfhgs@gmail.com)`（全程恒定，未伪装）
- 请求节奏：curl 逐条串行；`www/pubs.aeaweb.org` 间隔 ≥2s；第三方 API ≥1s（unpaywall 带 email）
- **实测请求总数：18**（站点 9 + 第三方 9〔crossref 5 + unpaywall 4〕；预算内；明细见文末）
- 标签：`[LIVE]`=本次实测证实；`[DOC]`=旧稿/目录断言未直验；`[LIVE-推断]`=实测推导；`[UNRESOLVED]`=预算内未查清
- **合规**：PDF 全文只发 HEAD 探头（未下任何正文）；遇 Cloudflare 挑战即停手不对抗（见 §4）；未触被禁路径。

> **⚠ 环境障碍甄别（controller 中途情报 + 本次实测对照）**：本机网络环境存在"对 Cloudflare 前置域 TLS 握手被强制代理 reset"的已知障碍（并行 R0a SSRN 勘察实测，症状=UA 发出前连接被重置）。**本次 AEA 勘察未出现该 TLS 症状**：对 CF 域 `pubs.aeaweb.org` 的 `robots.txt` 实测 `200`（TLS 握手成功），随后 `/doi/pdfplus/` 得**应用层 HTTP/2 403 + `cf-mitigated: challenge` + 5672B 挑战体**（非连接 reset）。故 §4 的 403 判定为**站点级 Cloudflare 判罚（BLOCKED）**，而非环境障碍——两者已严格区分。其余主机（www.aeaweb.org=Apache、非 CF）全程 200。

---

## 0. 结论速览（供详设先读）

| 维度 | 本次实测结论 |
|---|---|
| 元数据主干 | **Crossref 前缀 `10.1257` 走主干，且含摘要——比 NBER 更完整**。抽查 AER/JEP 近期文 `has_abstract=True`（len ~700–850）。前缀总 **50,692** DOI。→ **adapter 元数据 100% 走 Crossref，站点零元数据爬取**（elsevier_sd enumerate 先例成立）。 |
| DOI 体系 | **`10.1257` 证实**（landing `citation_doi` + Crossref 解析）。**两种 DOI 形态**：近年 `aer.{8 位投稿号}`（`aer.20230344`）；早年 `aer.{卷}.{期}.{页}`（`aer.106.6.i`）；P&P=`aer.p{...}` / `pandp.{...}`。 |
| 全文形态 | **两层双主机**：`www.aeaweb.org`=发现层（Apache，开放，全 `citation_*` meta）；`pubs.aeaweb.org`=全文层（Atypon + **Cloudflare**）。AER 近文 PDF 匿名得 HTML 挡板（订阅墙）；JEP PDF 302 跳 pubs。 |
| OA 例外 | **JEP=gold OA**（unpaywall `journal_is_oa=True`，publisher 托管）；JEL 同属免费刊（`[DOC]`，本次未单验）。AER/AEJ/AER:Insights=订阅。 |
| Unpaywall 覆盖 | **对 10.1257 green 覆盖偏低**：AER 抽查 3 例（近期研究文 + P&P + front matter）全 `closed`、0 OA location。NBER/SSRN 先行版有独立 DOI，未登记为 AEA DOI 的 OA 副本 → 跨源合并须靠 D-007，不能指望 unpaywall。 |
| 规模/节奏 | 前缀 50,692 DOI；AER 5,643（月刊，2026=Vol.116）；JEP 2,330（季刊）；AEJ 四系 + AER:Insights（季刊）。 |
| 反爬 | www=Apache 无挑战；**pubs=Cloudflare，stateless 全文请求被 challenge 判罚 → BLOCKED 边界**。 |

**3 项最重要发现**：
1. **AEA 是 Crossref 主干的理想案例**：元数据（含摘要）在 Crossref 完整，站点只需承担全文；与 D-005 完全吻合，且优于 NBER（NBER 摘要不在 Crossref）。
2. **全文是硬边界**：订阅内容（AER/AEJ/AER:Insights）经 `pubs.aeaweb.org`（Atypon）交付，该域 Cloudflare 对 stateless 客户端判罚 403 challenge——**即便 OA 的 JEP 全文也住在同一 CF 域**。→ 全文层须 Playwright 浏览器上下文（D-006 CookieSession + storage_state），stateless httpx 连 OA PDF 都拿不到。
3. **Unpaywall 不是 AEA 全文的可靠 OA 路**（green 覆盖低）；JEP/JEL 免费全文 + AER/AEJ 订阅墙才是真实分层。

---

## 1. robots.txt 判读（双主机）

**[LIVE]** apex `aeaweb.org/robots.txt` → `301` → `www.aeaweb.org`。

**[LIVE]** `GET www.aeaweb.org/robots.txt` → `200`（`Server: Apache`，非 CF），**全文仅**：

```
User-agent: GPTBot
Disallow: /
User-agent: Amazonbot
Disallow: /
```

- **无 `User-agent: *` 规则** → 对本 UA（非 GPTBot/Amazonbot）**无任何 Disallow**，landing/articles 路径全部合规可取。
- **合规信号（D-014）**：站点明确点名封禁 AI 训练类 bot（GPTBot/Amazonbot）。本系统用诚实 UA、只做少量礼貌请求、元数据走 Crossref、不做 AI 训练用途——与站点意图不冲突；但**详设应把"AEA 对 AI-bot 敏感"记入 quirks**，全文抓取从严。

**[LIVE]** `GET pubs.aeaweb.org/robots.txt` → `200`（`Server: cloudflare`，`cf-ray`），`Sitemap: /sitemap-index-1.txt`，`Crawl-delay: 1`：

```
User-agent: *
Disallow: /action /help /search /feedback /rss /media /servlet/linkout
Disallow: /na101/ /na102/ /doi/mlt/ /topic /author/ /doi/metrics/ /authored-by/ /history/
Allow: /action/showJournal /action/showPublications /action/showXml ...
User-agent: GPTBot
Disallow: /
```

- **`/doi/pdfplus/`、`/doi/pdf/` 未被 Disallow** → robots 层面全文 PDF 路径**允许**（仅 `/doi/mlt/`、`/doi/metrics/` 等子路径禁）。GPTBot 全禁。
- 真正拦截不在 robots，而在 **Cloudflare bot 管理**（见 §4）。

---

## 2. 期刊结构盘点（8 刊 + P&P）

**[LIVE]** `GET www.aeaweb.org/journals` → `200`，journal code 全表（`/journals/{code}`）：

| id（目录） | code | 名称 | 节奏 | auth |
|---|---|---|---|---|
| aer | `aer` | American Economic Review | 月刊（Vol.116@2026） | 订阅 |
| aeri | `aeri` | AER: Insights | 季刊 | 订阅 |
| aej_macro | `mac` | AEJ: Macroeconomics | 季刊 | 订阅 |
| aej_applied | `app` | AEJ: Applied Economics | 季刊 | 订阅 |
| aej_micro | `mic` | AEJ: Microeconomics | 季刊 | 订阅 |
| aej_policy | `pol` | AEJ: Economic Policy | 季刊 | 订阅 |
| jel | `jel` | Journal of Economic Literature | 季刊 | **免费**（`[DOC]`） |
| jep | `jep` | Journal of Economic Perspectives | 季刊 | **免费/gold**（§4 [LIVE]） |
| （附）| `pandp` | AER: Papers & Proceedings（年度会议特刊） | 年刊 | 订阅 |

**[LIVE] URL 形态**（从 AER 文章页 + journals 页提取）：
- 期刊主页 `/journals/{code}`；期刊全部期 `/journals/{code}/issues`；当期 `/journals/{code}/current-issue`。
- 单期 `/issues/{numId}`（数字期 id，如 `/issues/853`）；期内锚点 `/issues/853#{DOI}`。
- 文章 landing `/articles?id={DOI}`；全文 PDF `/articles/pdf/doi/{DOI}`（`citation_pdf_url` 直给）。

**[LIVE] DOI 前缀 `10.1257` 证实**（`citation_doi` meta + Crossref 双向解析）。**DOI 形态随年代变**：近年 `aer.20230344`（8 位投稿号）；早年 `aer.106.6.i`（卷.期.页）；P&P `aer.p20151048` / `pandp.116.742`；各子刊前缀 `aeri.` `mac.` `app.` `mic.` `pol.` `jel.` `jep.`。→ **adapter DOI 解析器须容两种 aer 形态**。

---

## 3. 元数据路径：Crossref 覆盖度与质量（主干判断）

**[LIVE]** Crossref 抽查（含 `select=abstract`）——**AEA 向 Crossref 存交摘要**（与 NBER 相反）：

| 查询 | total-results | has_abstract |
|---|---|---|
| `journals/0002-8282`（AER） | **5,643** | ✅ 近 3 文全 True（len 724/844/723） |
| `journals/0895-3309`（JEP） | **2,330** | ✅ True |
| `prefixes/10.1257`（全 AEA） | **50,692** | — |

**[LIVE]** 单条字段（`10.1257/aer.20230344`）：`type=journal-article`、`container=American Economic Review`、`title` ✅、`abstract` ✅（724 字符）、`author`（given/family 拆分 + `affiliation`）、`published=2026-07`、`volume=116`、`issue=7`、`page`。landing 页另有全套 `citation_*` meta（title/journal_title/issn/volume/issue/firstpage/lastpage/doi/pdf_url/author/author_institution）。

**判断证实**：**AEA adapter 元数据 100% 走 Crossref（按 ISSN + 日期枚举全史卷期），站点零元数据爬取**——正是 D-005"期刊=Crossref 主干"与 elsevier_sd 先例的标准形态。摘要、题录、作者机构均在 Crossref/landing meta 齐备；OpenAlex 可作 topics/引用补充层（本次未额外验，NBER §7 已证 OpenAlex 对经济 report 覆盖良好，期刊文覆盖只会更好）。

---

## 4. 全文形态实测（订阅墙 + OA 例外；只 HEAD/未下正文）

**[LIVE] AER 近文（订阅）**：`HEAD www.aeaweb.org/articles/pdf/doi/10.1257/aer.20230344` → `HTTP 200` 但 **`Content-Type: text/html`**（非 pdf）+ 下发 `aeawebcookie`/`PHPSESSID`。即匿名访问 PDF URL 得到的是**订阅挡板 HTML，不吐 PDF 字节** → **订阅墙成立**。landing 页显示"Download Full Text PDF"+"Log In"，无匿名全文。

**[LIVE] JEP（免费刊）**：`HEAD www.aeaweb.org/articles/pdf/doi/10.1257/jep.20251473` → **`302`** → `Location: https://pubs.aeaweb.org/doi/pdfplus/10.1257/jep.20251473`。即全文交付在 **Atypon 平台 `pubs.aeaweb.org`**（`/doi/pdfplus/` 经典 Literatum 形态）。

**[LIVE] pubs.aeaweb.org = Cloudflare BLOCKED 边界**：`HEAD pubs.aeaweb.org/doi/pdfplus/10.1257/jep.20251473` → **`HTTP/2 403` + `cf-mitigated: challenge` + `server: cloudflare` + `cf-ray` + 5672B 挑战体**。按红线**即停手、不对抗、不重试**。
- **属站点级判罚**（非环境障碍）：同域 `robots.txt` 先前 `200`（TLS 握手成功），此处是应用层 403 challenge（非连接 reset）。
- **关键含义**：**连 OA 的 JEP 全文也住在 CF 域**——stateless httpx 拿不到任何 AEA 全文 PDF（订阅或 OA 皆然）。全文层必须走浏览器上下文。

**OA 例外确认**：**[LIVE]** unpaywall JEP `10.1257/jep.20251473` → `is_oa=True, oa_status=gold, journal_is_oa=True, best_oa host_type=publisher`。JEP 确系全刊 gold OA（publisher 托管）；JEL 目录标免费同类（`[DOC]` 未单验）。AER/AEJ/AER:Insights 为订阅。

---

## 5. Unpaywall 对 10.1257 的 OA 覆盖抽查

**[LIVE]** 4 次 unpaywall（带 email）：

| DOI | 说明 | 结果 |
|---|---|---|
| `jep.20251473` | JEP 免费刊 | `is_oa=True` gold（publisher） |
| `aer.20230344` | 近期 AER 研究文 | `closed`，0 OA location |
| `aer.106.6.i` | AER front matter | `closed`，0 |
| `aer.p20151048` | AER P&P 短文 | `closed`，0 |

**结论**：**Unpaywall 对 AEA 订阅内容 green 覆盖偏低**（3/3 AER 样本 closed）。结构性原因：AEA 文章的 NBER/SSRN 先行版持**独立 DOI**（`10.3386/*`、SSRN id），未被登记为 `10.1257` DOI 的 OA location；AEA 版权也限制作者自存公开版。→ **"订阅版 ↔ 工作论文版"跨源合并须靠 D-007 标识图 + 题录/作者模糊匹配**，不能依赖 unpaywall 找 OA 副本。JEP/JEL 免费刊则 unpaywall 直报 gold 可用。
（样本以近期研究文 + P&P 为主，量小；更老的重磅研究文 green 命中率可能略高，但独立-DOI 结构性缺口是真实的，实现期不应把 unpaywall 当 AEA 全文主路。）

---

## 6. 规模量级与更新节奏

- **[LIVE]** Crossref 前缀 `10.1257` = **50,692 DOI**（AER + AEJ×4 + AER:Insights + JEL + JEP + P&P + 早年内容，全史）。
- **[LIVE]** AER 5,643（月刊，2026=Vol.116）；JEP 2,330（季刊）。AEJ 四系 + AER:Insights 均季刊。
- 量级 ≈ **5 万 DOI**；年增以 AER 月刊为主力，AEJ/insights/JEL/JEP 季刊补充。

---

## 7. 结论：adapter 可行性预判

- **归类**：`aea` 独立 adapter。`metadata_source: crossref`（按各刊 ISSN + 日期枚举全史）；`fulltext_source: aea`（订阅）/ `oa`（JEP/JEL）。
- **元数据主路径（高置信）**：**Crossref 前缀/ISSN 枚举**——含摘要、题录、作者机构，**站点零元数据爬取**。这是本 adapter 最稳的一面，与 elsevier_sd/D-005 同构。OpenAlex 作 topics/引用补充。
- **全文主路径与 BLOCKED 边界**：
  - JEP/JEL（gold OA）：全文 URL 经 `pubs.aeaweb.org/doi/pdfplus/{DOI}`，但**该域 Cloudflare 对 stateless 判罚 403** → 须 **Playwright 浏览器上下文**取（D-006 CookieSession，即便 OA 也如此），或退而经其它 OA 镜像。
  - AER/AEJ/AER:Insights（订阅）：`www.aeaweb.org/articles/pdf/doi/{DOI}` 匿名得挡板 HTML；真实交付在 pubs（Atypon）需**机构订阅登录**。→ **auth 形态预判：D-006 `CookieSession`（Playwright 有头首登机构账号 → storage_state 复用）**，且全文域是 Cloudflare，遇 challenge 一律 `BLOCKED` 转人工、绝不对抗。
  - 跨源全文兜底：订阅无门时经 **NBER（`10.3386`）/SSRN/RePEc 找工作论文版**（经 D-007 关系互联，非 unpaywall）。
- **限速/反爬**：`www.aeaweb.org`（Apache）≥2s 无挑战；`pubs.aeaweb.org`（Cloudflare，robots `Crawl-delay: 1`）**须浏览器上下文 + 保守限速**，challenge 即停。
- **环境障碍留待复测**：本次对 CF 域 `pubs` 的 TLS 握手成功（robots 200），403 系站点判罚；但已知本机对部分 CF 域有 TLS-reset 环境障碍（R0a/SSRN），实现期在干净网络环境应**复测 pubs 全文在浏览器上下文下的真实可达性**（区分"站点 CF 判罚"与"环境 TLS 障碍"）。

---

## 附：请求清单（共 18 次；站点 9 + 第三方 9）

| # | 主机 | 方法 | 路径 | 结果 |
|---|---|---|---|---|
| 1 | aeaweb.org | HEAD | /robots.txt | 301→www |
| 2 | www.aeaweb.org | GET | /robots.txt | 200（仅禁 GPTBot/Amazonbot） |
| 3 | api.crossref.org | GET | /journals/0002-8282/works（AER） | 200（5643，含摘要） |
| 4 | api.crossref.org | GET | /prefixes/10.1257/works?rows=0 | 200（50692） |
| 5 | api.crossref.org | GET | /journals/0895-3309/works（JEP） | 200（2330） |
| 6 | www.aeaweb.org | GET | /articles?id=10.1257/aer.20230344 | 200（citation_* meta） |
| 7 | www.aeaweb.org | HEAD | /articles/pdf/doi/10.1257/aer.20230344 | 200 text/html（订阅挡板） |
| 8 | www.aeaweb.org | GET | /articles?id=10.1257/jep.20251473 | 200 |
| 9 | www.aeaweb.org | HEAD | /articles/pdf/doi/10.1257/jep.20251473 | 302→pubs |
| 10 | pubs.aeaweb.org | GET | /robots.txt | 200（Cloudflare；TLS OK） |
| 11 | pubs.aeaweb.org | HEAD | /doi/pdfplus/10.1257/jep.20251473 | **403 cf-mitigated:challenge（站点 BLOCKED）** |
| 12 | api.unpaywall.org | GET | /v2/10.1257/aer.20230344 | 200（closed） |
| 13 | api.unpaywall.org | GET | /v2/10.1257/jep.20251473 | 200（gold） |
| 14 | api.crossref.org | GET | /journals/0002-8282/works?filter=2016 | 200（front matter） |
| 15 | api.unpaywall.org | GET | /v2/10.1257/aer.106.6.i | 200（closed） |
| 16 | api.crossref.org | GET | /journals/0002-8282/works?filter=2015 | 200（研究文） |
| 17 | api.unpaywall.org | GET | /v2/10.1257/aer.p20151048 | 200（closed） |
| 18 | www.aeaweb.org | GET | /journals | 200（8 刊 code） |

原始响应存 `scratchpad/aea-raw/`，非 git 产物，供详设复核。
