---
title: 站点勘察：NBER Working Papers（nber.org / back.nber.org）
status: approved
owner: fable5
updated: 2026-07-27
---

# NBER Working Papers LIVE 勘察报告 [Phase 5 R0b]

- 勘察对象：`www.nber.org`（landing/PDF，nginx/Drupal）+ `back.nber.org`（RSS/sitemap，Akamai）；对照旧稿 `docs/research/site-survey/econ-fin-preprints.md` 的 NBER 段
- 勘察时间：2026-07-24
- UA：`PaperCrawler/0.1.0 (personal research; mailto:yhyfhgs@gmail.com)`（全程恒定，未伪装）
- 请求节奏：curl 逐条串行；`www.nber.org` 间隔 ≥2s；`back.nber.org` 遵其 `Crawl-delay: 10` ≥10s；第三方 API ≥1s
- **实测请求总数：13**（站点 10 + 第三方 3；预算内；明细见文末"请求清单"）
- 标签：`[LIVE]`=本次实测证实；`[DOC]`=旧稿断言未经本次直接验证；`[LIVE-推断]`=由实测推导未直抓；`[UNRESOLVED]`=预算内未查清
- **合规红线遵守**：全程未触碰 <18 月新论文软门（旧稿 `econ-fin-preprints.md` §合规敏感发现③ 标注禁止绕过）；PDF 只对 >18 月完全开放论文发 1 次 HEAD 探头，未下载任何 PDF 正文；未使用被 robots 禁止的 `/search/`。

---

## 0. 结论速览（供详设先读）

| 维度 | 本次实测结论 |
|---|---|
| 元数据主干 | **走聚合 API（Crossref + OpenAlex），符合 D-005**。Crossref 前缀 `10.3386` 一次可枚举 NBER 全部 **35,976** 个 DOI（title/authors/date/type=report），但**无摘要、无 JEL**；OpenAlex 补摘要（inverted index）+ concepts/topics + `oa_status`。 |
| DOI 体系 | **`10.3386/w{n}` 证实成立**（landing 页 `citation_doi` meta + Crossref/OpenAlex 双向解析均命中）。 |
| 全文 PDF | `www.nber.org/system/files/working_papers/w{n}/w{n}.pdf`；>18 月开放论文匿名 `HEAD` 得 `200 application/pdf`、`accept-ranges: bytes`。**<18 月按机构 IP/订阅/配额门控（软门），设计层不绕过 → BLOCKED 边界**。 |
| 枚举路径 | 首选 **Crossref 前缀枚举**（35,976 DOI 一条 API 线）；增量走 **RSS**（全量 `new.xml` 39 条/周 + 19 个 program 分 feed）；`sitemap.txt` 为 bulk 种子（有陈旧风险）；顺序 `w{n}` 也可（w1..~w35506 连续，但 `/search/` 被禁）。 |
| 规模量级 | w 系列现最大约 **w35506**（2026-07）；Crossref 前缀 **35,976** DOI（含少量非 w：t/技术报告、章节）。量级 ≈ **3.6 万**。 |
| 反爬 | www.nber.org=nginx 无挑战；back.nber.org=Akamai 有 `Crawl-delay: 10` 须遵守；全程无 429/CAPTCHA/挑战页。 |

**3 项最重要发现**：
1. **NBER 不需要自建脆弱爬虫做元数据**：Crossref 前缀 `10.3386` 全覆盖（35,976 DOI），是最省的 discover/enumerate 主干；NBER 站点只承担全文 PDF（>18 月开放部分）。
2. **摘要/JEL 分工明确**：Crossref 无摘要无 JEL → 摘要从 OpenAlex（inverted index）或 NBER RSS `<description>` 补；**JEL 分类三条站内/聚合路径均无**（landing meta、Crossref subject、OpenAlex 均缺），只能靠 RePEc `nbr:nberwo` ReDIF（旧稿 `[DOC]`，本次未验），是待实现期解决的字段缺口。
3. **两个不同主机、两套 robots、两套限速**：`www.nber.org`（全文，无 crawl-delay）与 `back.nber.org`（RSS/sitemap，crawl-delay 10s）须在 adapter 里分别建速率闸；apex `nber.org` 与低号老论文 `www2.nber.org` 是额外重定向主机。

---

## 1. robots.txt 判读（双主机）

**[LIVE]** `HEAD https://nber.org/robots.txt` → `301` → `https://www.nber.org/robots.txt`（apex 收敛到 www）。

**[LIVE]** `GET https://www.nber.org/robots.txt` → `200`（`server: nginx`，标准 Drupal robots）。关键段：

```
User-agent: *
Allow: /core/*.css$ ... /profiles/*.svg      # 静态资源放行
Disallow: /core/  /profiles/                  # Drupal 内部
Disallow: /admin/  /search/  /user/login/ ...  # 管理/搜索/账户
```

- **放行**：`/papers/`、`/rss/`、`/system/files/working_papers/` 均**未被 Disallow** → landing、PDF、feed 全部合规可取。
- **禁区**：`/search/`（含 `/index.php/search/`）被 Disallow → **on-site 搜索不能作枚举路径**（改用 Crossref/RSS）。
- **无** `Crawl-delay`、**无** AI-bot 专项封禁（不禁 ClaudeBot/GPTBot）、**无** `Sitemap` 声明。

**[LIVE]** `GET https://back.nber.org/robots.txt` → `200`（`server-timing: cdn-cache`，Akamai）：

```
Sitemap: http://back.nber.org/sitemap.txt
User-agent: *
Crawl-delay: 10
User-agent: *
Disallow: /wpsubmit/ /confsubmit/ /chapter_revise/ /2009_redesign/ /marc/ /nominate/ /nomreview/ /sendthisfile/
```

- **`Crawl-delay: 10`** — 本主机须 ≥10s/请求（严于系统 2s 基线，硬约束）。
- **`/rss/`、`/sitemap.txt` 未被 Disallow** → feed 与 sitemap 合规。禁区均为投稿/管理路径，与抓取无关。

**[LIVE 2026-07-27]** `GET https://www2.nber.org/robots.txt` → **403 Forbidden**（`Apache/2.4.66 (FreeBSD)` 源站签名，非代理拦截）——**该第三主机不提供可判读 robots.txt**，`www.nber.org` 的 nginx/Drupal robots **不可外推**（REP 按 origin 生效，两域服务器栈不同）。403 系 `/robots.txt` **路径特异**：同域数据路径 [LIVE 2026-07-26] 4/4 成功。合规取舍已由 fable 裁决（RFC 9309 §2.3.1.3 4xx="Unavailable"、无可违反规则；附条件＝数据端点遇 403/429 立即停手），详见 [aggregators.md §5.7](../../design/adapters/aggregators.md)。本节原双主机判读不受影响（`www2` 是 `nber` adapter `domains[1]` 的低号 301 目标，非枚举/取回主路径）。

---

## 2. 官方结构化通道盘点

**[LIVE]** NBER **无官方 JSON/REST bulk API**（本次未发现，旧稿亦称"无官方 bulk API"）。可用结构化通道：

1. **RSS feed（主增量通道，托管在 back.nber.org）**
   - `www.nber.org/rss/new.xml` → **`301` 跳** `back.nber.org/rss/new.xml`（feed 实际住 back 主机）。
   - **[LIVE]** `back.nber.org/rss/new.xml` → `200 application/xml`，53,605 bytes，**39 个 `<item>`**，`last-modified: Mon, 20 Jul 2026`（**周更**）。字段：`<title>`（含 `-- by <作者串>`）、`<description>`（**完整摘要**）、`<link>`/`<guid>`（`www.nber.org/papers/w{n}#fromrss`）。**无 dc: 命名空间、无 DOI、无 JEL**。
   - **[LIVE]** program 分 feed：`back.nber.org/rss/new{code}.xml` 证实可用（抽验 `newcf.xml`=Corporate Finance → `200`，3 条 item，为 all-feed 的程序过滤子集）。旧稿列 **19 个 program**（`newap`/`newcf`/`newme`/`newpe`/`newls`…），`[DOC]` 未逐一复验，但命名规律与主 feed 一致。
2. **sitemap.txt（bulk 种子）** — **[LIVE]** `HEAD back.nber.org/sitemap.txt` → `200 text/plain`，`last-modified: Tue, 28 Oct 2025`（**陈旧 ~9 月**，不含最新论文；Drupal 惯例=每行一 URL）。可作全量 seed，但须叠加 RSS/Crossref 补新。
3. **DOI 体系** — **[LIVE]** `10.3386/w{n}` 成立：landing 页 `citation_doi=10.3386/w30000`；Crossref `works/10.3386/w30000` 与 OpenAlex 均解析命中。前缀 `10.3386` 属 NBER。

---

## 3. 元数据形态（标题/作者/摘要/JEL 的可得路径）

**[LIVE]** landing `GET www.nber.org/papers/w30000` → `200`，Highwire `citation_*` + `og:` meta（**无 DC.***）：

```html
<meta name="citation_title" content="The US COVID-19 Baby Bust and Rebound"/>
<meta name="citation_author" content="Melissa Schettini Kearney"/>   <!-- 每作者一条 -->
<meta name="citation_doi" content="10.3386/w30000"/>
<meta name="citation_publication_date" content="2022/05/02"/>
<meta name="citation_technical_report_institution" content="National Bureau of Economic Research"/>
<meta name="citation_technical_report_number" content="w30000"/>
<meta name="citation_pdf_url" content="https://www.nber.org/system/files/working_papers/w30000/w30000.pdf"/>
```

- **无 `citation_abstract` meta、无 JEL**（grep `JEL` 于全 HTML 零命中）。摘要在 landing 正文 div 与 RSS `<description>` 里。

各路径**字段可得性对照**：

| 字段 | landing meta | RSS | Crossref `10.3386` | OpenAlex |
|---|---|---|---|---|
| 标题 | ✅ | ✅ | ✅ | ✅ |
| 作者 | ✅（逐条） | ✅（挤在 title） | ✅（given/family 拆分） | ✅ |
| 摘要 | 正文 div（非 meta） | ✅ `<description>` | ❌ **无** | ✅ inverted_index |
| DOI | ✅ | ❌ | ✅ | ✅ |
| 发表日期 | ✅ | ❌ | ✅（2022-04） | ✅ |
| 类型 | report（隐含） | — | ✅ `report` | ✅ `report` |
| **JEL** | ❌ | ❌ | ❌ `subject:[]` | ❌（仅自有 concepts/topics） |

**[LIVE]** Crossref `works/10.3386/w30000`：`type=report`、`institution=[NBER, Cambridge MA]`、`has_abstract=False`、`subject=[]`、`is-referenced-by-count=14`。
**[LIVE]** OpenAlex `W4225331229`：`oa_status=green`、`host_source=NBER`、`abstract_inverted_index=True`、13 concepts / 2 topics。

**JEL 缺口 `[UNRESOLVED/DOC]`**：站内/Crossref/OpenAlex 三路均无 JEL；旧稿指 RePEc `nbr:nberwo` ReDIF 携带 JEL，本次未验，实现期若需 JEL 须走 RePEc bulk。

---

## 4. 全文 PDF 匿名可下政策（只 HEAD 探头，未下载正文）

**[LIVE]** `HEAD www.nber.org/system/files/working_papers/w30000/w30000.pdf`（w30000=2022-05，**>18 月完全开放**区）：

```
HTTP/2 200
content-type: application/pdf
accept-ranges: bytes
content-length: 1077387          # ~1.03 MB，仅头部得知，未取 body
cache-control: private, must-revalidate
server: nginx
```

- **>18 月开放论文匿名直取成立**：无跳登录、无付费墙、无挑战页，`200 application/pdf`。
- URL 由 landing `citation_pdf_url` meta 直接给出，resolve 阶段可省构造。
- **<18 月新论文**：旧稿 `[LIVE]` 记为机构 IP/订阅/记者/政府/低收入国 + 匿名 3 篇/年配额。**本次遵合规红线，未对任何 <18 月论文做 PDF 探测**（软门绕过属旧稿明令禁区）。→ **设计层：<18 月全文=BLOCKED 边界，提示用户订阅，不自动抓、不利用软门**。

---

## 5. 枚举路径可行性

| 路径 | 形态 | 评价 |
|---|---|---|
| **Crossref 前缀** | `api.crossref.org/prefixes/10.3386/works`（date 过滤翻页） | **首选**：一条 API 线枚举全 35,976 DOI，无脆弱翻页，免费 polite pool（带 mailto）。 |
| RSS 全量 | `back.nber.org/rss/new.xml`（39 条/周） | 增量新论文主通道；周更；须遵 crawl-delay 10s。 |
| RSS program | `back.nber.org/rss/new{code}.xml`（19 program） | 按 program 增量分片（对应 NBER program 维度）。 |
| sitemap.txt | `back.nber.org/sitemap.txt`（text/plain） | bulk 种子；**陈旧（2025-10）**，须叠加补新。 |
| 顺序 `w{n}` | `www.nber.org/papers/w1..~w35506` | **[LIVE]** `w1` 存在（`HEAD` → `301` 跳 `www2.nber.org` 老主机）；连续可顺扫，但 `/search/` 被 robots 禁，只能靠已知 DOI 枚举而非站内搜索。 |

**[LIVE]** w 系列下界 `w1` 存在（低号老论文由 `www2.nber.org` 承载，本次未深入该主机）；上界 `w35506`（本周 feed 最大号）。编号连续、稠密。

---

## 6. 规模量级

- **[LIVE]** w 系列现最大 ≈ **w35506**（2026-07-20 feed）。
- **[LIVE]** Crossref 前缀 `10.3386` `total-results = 35,976`（含 w 工作论文 + 少量 t 技术报告 / 章节）。
- 量级 ≈ **3.6 万篇**，年增约 1200–1500（由 w30000@2022-05 → w35506@2026-07 线性推）。

---

## 7. 与既有生态交点（覆盖抽查）

- **[LIVE] Crossref**：前缀全覆盖 35,976 DOI；单条元数据= title/authors(拆分)/date/type=report/institution，**缺摘要缺 JEL**。
- **[LIVE] OpenAlex**：抽查命中，`oa_status=green`、补 `abstract_inverted_index` + concepts/topics；可作摘要与主题分类补充层（受信用预算约束，D-005 修订）。
- **[DOC] RePEc `nbr:nberwo`**：旧稿指其 ReDIF bulk 携 JEL + 书目，是 JEL 唯一已知来源；本次预算未验，`[UNRESOLVED]`。

---

## 8. 结论：adapter 可行性预判

- **归类**：`open_access` 模块；`metadata_source: crossref`（+OpenAlex 补摘要/topics），`fulltext_source: nber`（仅 >18 月开放段）。与 D-005（元数据走聚合、站点只做全文）**完全吻合**，无需为 NBER 建脆弱 HTML 爬虫做元数据。
- **主路径候选**：
  1. discover/enumerate = **Crossref 前缀 `10.3386` + date 窗口**（全 3.6 万 DOI）；增量 = RSS `new.xml`/program feed。
  2. 摘要 = OpenAlex inverted_index 或 NBER RSS `<description>`；**JEL = RePEc `nbr:nberwo`（待验）**。
  3. resolve/fetch = landing `citation_pdf_url` → `www.nber.org/system/files/working_papers/w{n}/w{n}.pdf`，**仅 >18 月开放论文**匿名 httpx 直取。
- **BLOCKED 边界**：<18 月新论文全文（机构 IP/订阅/配额软门）——**不绕过、不利用软门**，标 `fulltext: recent_gated`，提示用户。
- **限速基线建议**：`www.nber.org` ≥2–5s（无声明 crawl-delay，保守取 5s 更稳）；**`back.nber.org` ≥10s（robots `Crawl-delay: 10` 硬约束）**；第三方 Crossref polite pool（带 mailto）/OpenAlex 按信用预算。三主机（www / back / www2）+ apex 分别处理重定向。
- **反爬**：www=nginx 无挑战；back=Akamai 仅 crawl-delay，无 429/CAPTCHA。遇挑战页即 BLOCKED（本次未遇）。
- **paper 类型**：Crossref/OpenAlex 均判 `report`（工作论文非 journal-article），数据模型 venue/type 建模需支持 working_paper/report 类，且与正式刊发版经 D-007 `preprint_of` 关系互联（NBER WP 常后续发表于 AER/QJE 等）。

---

## 附：请求清单（共 13 次 HTTP 请求；站点 10 + 第三方 3）

| # | 主机 | 方法 | 路径 | 结果 |
|---|---|---|---|---|
| 1 | nber.org | HEAD | /robots.txt | 301→www |
| 2 | www.nber.org | GET | /robots.txt | 200（nginx，无 crawl-delay） |
| 3 | www.nber.org | GET | /rss/new.xml | 301→back |
| 4 | back.nber.org | GET | /robots.txt | 200（Crawl-delay:10；Sitemap） |
| 5 | back.nber.org | GET | /rss/new.xml | 200（39 item，周更） |
| 6 | www.nber.org | GET | /papers/w30000 | 200（citation_* meta） |
| 7 | www.nber.org | HEAD | /system/files/working_papers/w30000/w30000.pdf | 200 application/pdf（>18 月开放） |
| 8 | www.nber.org | HEAD | /papers/w1 | 301→www2（下界存在） |
| 9 | api.crossref.org | GET | /works/10.3386/w30000 | 200（无摘要无 JEL） |
| 10 | api.crossref.org | GET | /prefixes/10.3386/works?rows=0 | 200（total=35976） |
| 11 | api.openalex.org | GET | /works/doi:10.3386/w30000 | 200（green，含 abstract inverted） |
| 12 | back.nber.org | HEAD | /sitemap.txt | 200 text/plain（2025-10 陈旧） |
| 13 | back.nber.org | GET | /rss/newcf.xml | 200（program feed，3 item） |

原始响应（headers+body）存 `scratchpad/nber-raw/`，非 git 产物，供详设复核。
