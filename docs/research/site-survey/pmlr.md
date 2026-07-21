---
title: 勘察：PMLR（双托管/bibkey/卷结构）
status: approved
owner: fable5
updated: 2026-07-22
---

# PMLR 站点勘察报告（LIVE 实测）

- 勘察员：站点勘察 subagent（Paper Crawler）
- 日期：2026-07-22
- 目标站点：`proceedings.mlr.press`（+ `raw.githubusercontent.com`、`github.com/mlresearch`、`www.jmlr.org`、`dblp.org`）
- 目的：为重写 `docs/design/adapters/pmlr.md`（评审 REJECT）补做 LIVE 勘察，逐项回应 `pmlr-review.md` 文末 8 项清单与 BLOCKER/CONCERN。
- 合规：UA 全程 `PaperCrawler/0.1 (site survey; personal research)`（curl 请求均带；WebFetch 用其自身 UA）；请求间隔 ≥1.2s（后台脚本自节流）；HEAD 优先；**全部只读 GET/HEAD，无认证、无写操作、无账号副作用**；**未遇任何挑战门/验证码/403/429**（全部 200/404 正常响应）。
- **总网络请求数 = 21**（19 curl 按计划 2xx/4xx；1 curl→DBLP count API 得 503；1 WebFetch→DBLP TOC 因 >10MB 中止）。远低于 ≤25 上限。

## 请求日志（21 条）

| # | 方法 | URL | 结果 |
|---|---|---|---|
| 1 | HEAD | proceedings.mlr.press/v202/aamand23a/aamand23a.pdf | 200 `application/pdf` 3.85MB（自托管） |
| 2 | HEAD | proceedings.mlr.press/v235/abad-rocamora24a/abad-rocamora24a.pdf | **404**（新卷不走旧路径） |
| 3 | HEAD | raw.githubusercontent.com/mlresearch/v235/main/assets/abad-rocamora24a/abad-rocamora24a.pdf | 200 `application/octet-stream` 6.98MB（GitHub 托管） |
| 4 | GET | proceedings.mlr.press/robots.txt | **404**（无 robots；server: GitHub.com） |
| 5 | GET | raw.githubusercontent.com/robots.txt | **404**（14B "404: Not Found"） |
| 6 | HEAD | proceedings.mlr.press/v9999/ | **404**（GitHub Pages 通用 404，9379B） |
| 7 | HEAD | proceedings.mlr.press/v9/ | **200**（AISTATS 2010，99894B） |
| 8 | HEAD | proceedings.mlr.press/v15/ | **200**（AISTATS 2011，93826B） |
| 9 | HEAD | www.jmlr.org/proceedings/papers/v9/ | **404**（server: AmazonS3 / CloudFront，旧域已死） |
| 10 | GET | proceedings.mlr.press/ | 200 40KB（全卷列表，v2–v336 + r0–r6） |
| 11 | GET | proceedings.mlr.press/v235/ | 200 2.55MB（ICML 2024 卷页，2610 条目） |
| 12 | GET | proceedings.mlr.press/v235/abad-rocamora24a.html | 200 15.6KB（单篇 abs，含 citation_* meta） |
| 13 | GET | api.github.com/repos/mlresearch/v235 | 200（repo 元数据：public, default gh-pages, size 6.8GB） |
| 14 | GET | api.github.com/repos/mlresearch/v235/contents | 200（顶层：_config.yml/_posts/index.html/…） |
| 15 | GET | raw.githubusercontent.com/mlresearch/v235/main/_config.yml | 404（config 在 gh-pages 分支，非 main） |
| 16 | GET | raw.githubusercontent.com/mlresearch/v235/gh-pages/_config.yml | 200 2191B（卷级元数据 YAML） |
| 17 | GET | api.github.com/repos/mlresearch/v235/contents/_posts?ref=gh-pages | 200 872KB（_posts 目录，API 截断至 1000/2610 条） |
| 18 | GET | raw.githubusercontent.com/mlresearch/v235/gh-pages/_posts/2024-07-08-abad-rocamora24a.md | 200 2082B（单篇元数据 YAML front matter） |
| 19 | GET | proceedings.mlr.press/v229/ | 200 194KB（CoRL 2023，PDF **仍自托管**——边界证据） |
| 20 | GET | dblp.org/search/publ/api?q=toc:…icml2024…&h=0 | **503**（DBLP 暂时不可用，锚点交叉核对未成） |
| 21 | GET(WebFetch) | dblp.org/db/conf/icml/icml2024.html | 中止（响应 >10MB 超限） |

---

## 逐项勘察结论

### 项 1 · 卷索引页结构 + 卷号↔会议映射 —— [LIVE] 完成

`GET proceedings.mlr.press/`（40KB 静态 HTML）**单页含全部卷**（v2…v336 逆序 + 复刊 r0–r6）。锚点形态为**相对链接无前导斜杠无尾斜杠**：`<a href="v235">Volume 235 Proceedings of ICML 2024</a>`（注意：不是 `/v235/`——评审附录与旧解析器若假设 `/vN/` 形态会漏抓）。每条形如 `Volume {N} Proceedings of {CONF} {YEAR}`，v→会议→年映射可一次性正则提取。

**LIVE 实测映射（各会议早年+近年，覆盖 ICML/AISTATS/COLT/UAI/CoRL）**：

| 会议 | PMLR 全区间（实测） |
|---|---|
| **ICML** | v28(2013) v32(2014) v37(2015) v48(2016) v70(2017) v80(2018) v97(2019) v119(2020) v139(2021) v162(2022) v202(2023) **v235(2024)** v267(2025) |
| **AISTATS** | v2(2007) v5(2009) v9(2010) v15(2011) v22(2012) v31(2013) v33(2014) v38(2015) v51(2016) v54(2017) v84(2018) v89(2019) v108(2020) v130(2021) v151(2022) v206(2023) v238(2024) v258(2025) |
| **COLT** | v19(2011) v23(2012) v30(2013) v35(2014) v40(2015) v49(2016) v65(2017) v75(2018) v99(2019) v125(2020) v134(2021) v178(2022) v195(2023) v247(2024) v291(2025) v336(2026) |
| **UAI** | v124(2020) v161(2021) v180(2022) v216(2023) v244(2024) v286(2025)（2020 起入 PMLR，此前 AUAI Press） |
| **CoRL** | v78(2017) v87(2018) v100(2019) v155(2020) v164(2021) v205(2022) v229(2023) v270(2024) v305(2025) |
| **复刊 Reissue** | r0=AISTATS1995(pre-proc) r1=1997 r2=1999 r3=2001 r4=2003 r5=2005 **r6=UAI1998** |

> **修订提示（对 catalog）**：`docs/catalog/cs-ai-conferences.md` 的 volume_map 表只列 2021–2025 五年；上表提供各会议至 PMLR 起点的完整历史，可直接补全（回应清单项 7 的"历史完整性"）。
> **小订正**：pmlr.md §1 写"COLT（2013+ era）"——实测 PMLR-era COLT 自 **v19=2011** 起（v19/v23/v30 均在），应改为 **2011+**。ICML 起点 v28=2013 与 catalog 一致。

### 项 2 · 单卷页 + 单篇页结构（含 citation_* meta、bibkey 实测）—— [LIVE] 完成

**卷页 `v{N}/`**：每篇一个 `<div class="paper">`（v235 计 2610 个），块内含 `[abs]`(→`v{N}/{slug}.html`)、`[Download PDF]`、`[OpenReview]` 三链；卷首 `[bib]` 指向 **独立文件** `./assets/bib/bibliography.bib`（非页内嵌，v235 该 bib 约 5.2MB）。

**单篇 abs 页 `v{N}/{slug}.html`**：含**完整 Google Scholar `citation_*` meta 标签**（实测 v235/abad-rocamora24a）：
```
citation_publisher = PMLR
citation_title = Revisiting Character-level Adversarial Attacks for Language Models
citation_pdf_url = https://raw.githubusercontent.com/mlresearch/v235/main/assets/abad-rocamora24a/abad-rocamora24a.pdf
citation_abstract_html_url = https://proceedings.mlr.press/v235/abad-rocamora24a.html
citation_firstpage = 1 ; citation_lastpage = 30
citation_author = Elias Abad Rocamora  (每作者一行，共 5 行)
citation_publication_date = 2024/07/08
citation_conference_title = International Conference on Machine Learning
citation_issn = 2640-3498
```
→ **`citation_*` meta 是除 bib 外的第三条结构化来源**，且 `citation_pdf_url` 直接给出 PDF 真实托管域（无需猜测），`citation_issn=2640-3498` 是 PMLR 系列 ISSN。

**bibkey 实测（解 BLOCKER B2）**：单篇页内嵌 BibTeX entry key = **`@InProceedings{pmlr-v235-abad-rocamora24a`**。即官方规范 key = **`pmlr-v{N}-{slug}`**；slug = `{姓}{yy}{后缀}`（`abad-rocamora24a`，多词姓保留连字符，后缀 a/b 消歧）。URL slug 与 key 尾段一致。站点自生成小写，原样保留、勿做大小写归一。

### 项 3 · PDF 双域实锤（含 Content-Type/重定向链）—— [LIVE] 完成（核心发现）

| 卷 | 会议年 | PDF 直链域 | 状态 | Content-Type | 重定向 |
|---|---|---|---|---|---|
| v202 | ICML 2023 | proceedings.mlr.press | 200 | **`application/pdf`** | 无（直连） |
| v229 | CoRL 2023（晚 2023） | proceedings.mlr.press | 200（卷页全部自托管） | application/pdf | 无 |
| v235 | ICML 2024 | **raw.githubusercontent.com** | 200 | **`application/octet-stream`** | 无（直连） |
| v235（旧式路径） | — | proceedings.mlr.press/v235/…/*.pdf | **404** | — | — |

**实锤结论**：
1. **托管迁移确实存在**：旧卷自托管于 `proceedings.mlr.press`，新卷 PDF 迁至 `raw.githubusercontent.com/mlresearch/v{N}/main/assets/{slug}/{slug}.pdf`。新卷的旧式自托管路径直接 404。
2. **切分边界不是整齐的卷号/年份线**：实测 **v202(ICML2023) 与 v229(CoRL2023) 均仍自托管**，v235(ICML2024) 才在 GitHub。故边界落在 **晚 2023(v229) 与 中 2024(v235) 之间**，按**上传时间**而非卷号切分（同年不同会议可不同）。**不可硬编码固定卷号切分点。**
3. **Content-Type 不可靠**：GitHub raw 返 `application/octet-stream`（非 `application/pdf`），且带 CSP `default-src 'none'; sandbox`、`x-content-type-options: nosniff`。→ **fetch_asset 必须用 `%PDF` 魔数校验**（pmlr.md §3 已写 `%PDF` 校验，正确，须保留并强调；勿用 Content-Type 判定）。
4. **域名清单**：`domains` 冻结字段至少声明 `("proceedings.mlr.press", "raw.githubusercontent.com")`；两域均 GitHub 基础设施（Pages + raw，Fastly CDN `via: 1.1 varnish`），**无 Cloudflare**（无 `cf-ray`，证实 §2）。

**设计落点（解 BLOCKER B3）**：PDF 真实域**始终在带内可得**——`citation_pdf_url`(abs 页 meta) / bib 的 `pdf` 字段 / `_posts` md 的 `pdf:` 字段三者一致。enumerate 阶段把 `pdf_url`+`landing_url` 写入 `PaperStub.meta`，resolve_assets 读 meta 构造 AssetPlan、**零额外网络、域无关**。不要在 resolve 阶段重新发请求或按卷号推断域。

### 项 4 · 空态/不存在卷 —— [LIVE] 完成

`HEAD v9999/` → **HTTP 404**，返 **GitHub Pages 通用 404 页**（`content-length: 9379`，`<title>Page not found · GitHub Pages</title>`，`server: GitHub.com`）——与 v235 旧式 PDF 路径 404、robots 404 是**同一张通用 404 页**。
- **判据**：不存在卷靠 **HTTP status 404** 判定，**不能靠 body 内容**（body 是 GitHub 通用页，非 PMLR 风格）→ 映射 `gone`。
- **本次未观测到"200 但空"的合法空卷**（B5 的"合法空态"是推定态，非实测态）。真实"已发布但 0 篇"卷应表现为 200 + 卷页 0 个 `<div class="paper">`；与 parse 故障的区分信号 = **bib 条目数 vs HTML 条目数是否一致**（都为 0 = 合法空；HTML>0 而 bib=0 = parse 故障）。建议合成 fixture。

### 项 5 · robots.txt + ToS/使用条款 —— [LIVE] 完成

- `proceedings.mlr.press/robots.txt` → **404**（无 robots.txt）。响应头 `server: GitHub.com`、Fastly（`via: varnish`, `x-served-by: cache-*`）、**无 `cf-ray`**。
- `raw.githubusercontent.com/robots.txt` → **404**（14B `404: Not Found`；`content-security-policy: default-src 'none'; sandbox`、`x-content-type-options: nosniff`）。
- **无站点级 ToS/AUP 页面**。首页页脚仅有 `spec.html`（"Proceedings Specification"，是**投稿方给编者的卷制作规范**，非爬虫使用条款，本次未抓，低优先）与 `feed.xml`（RSS）。单篇/卷页仅有 `Copyright © [year] by the author(s)` 声明（版权归作者）。**完全开放获取，无登录/无 API-key/无付费墙**。
- → 使用约束仅来自"礼貌限速 + 各论文版权"。pmlr.md §4"robots ⚠ 实现期复核"应改为实测结论：**两域 robots.txt 均 404（不存在），无 robots 限制**。
- **[UNRESOLVED / 后续]**：`raw.githubusercontent.com` 的限速/滥用阈值属 GitHub 基础设施（Fastly），**无文档化数字**，robots 404 不代表无限流；清单项 2 建议查 GitHub 官方 ToS/rate-limit 文档后在 quirks 标注保守速率。

### 项 6 · GitHub bulk 替代（mlresearch org 卷 repo 结构）—— [LIVE] 完成

- **一卷一 repo**：`github.com/mlresearch/v{N}`（实测 v235）。public、非 fork/archive、语言 Ruby（Jekyll）、**默认分支 `gh-pages`**（故 `main/_config.yml` 404，须用 gh-pages）。
- **顶层结构**：`_config.yml` + `_posts/`（每篇一 md）+ `assets/`（PDF）+ `index.html` + `Gemfile` + `.github/`。
- **卷级元数据 `_config.yml`**（gh-pages）：`booktitle / shortname(ICML) / volume(235) / year(2024) / start(2024-07-21) / end / published(2024-07-08) / conference_number(41) / series / publisher(PMLR) / issn(2640-3498) / id(ICML-2024) / editor[given/family]…`。
- **单篇元数据 `_posts/YYYY-MM-DD-{slug}.md`** YAML front matter（**全字段**）：`title / author[given,family] / abstract(全文) / firstpage / lastpage / page(1-30) / order(1) / id(slug) / pdf(raw github URL) / openreview(forum id) / date / container-title / volume …`。
- **结论**：**每卷全部元数据可经 `git clone`/sparse-checkout 获取，无需解析 HTML** → bulk-first **可行**，与 acl_anthology 的"GitHub bulk 优先"先例（AC-2.5）同构（回应 CONCERN C7）。
- **权衡（须写清）**：
  - 全 repo ≈ **6.8 GB**（`size` 6,876,025 KB，含 assets/ 全部 PDF）；**仅元数据**的 sparse-checkout（`_config.yml`+`_posts`，排除 assets）仅数 MB。
  - Contents API 目录列举**上限 1000 条**（v235 _posts 有 2610）→ 若走 API 枚举须用 git-trees API 或直接 clone。
  - **对比在线爬**：单张卷页（1 请求）即含全部 2610 条目 + bib 链接，**在线卷级枚举本已极轻量（1–2 请求/卷）**。建议：**在线卷页为主**，bulk-clone 作为**可选**路径（全量回填/HTML 结构劣化时的兜底），不必默认采用——净收益有限。

### 项 7 · AISTATS 早年缺卷（jmlr.org 死链）—— [LIVE] 完成（**订正评审 C5**）

- `www.jmlr.org/proceedings/papers/v9/` → **404**（`server: AmazonS3` via CloudFront）。旧 JMLR W&CP proceedings 路径**确已死**。
- **但内容已迁至 PMLR**：AISTATS 2007–2016 **全部在 `proceedings.mlr.press` 存活**——v2(2007) v5(2009) **v9(2010, HEAD 200)** **v15(2011, HEAD 200)** v22(2012) v31(2013) v33(2014) v38(2015) v51(2016) v54(2017) 均在首页卷列表且可达。
- **→ 评审 C5 "AISTATS 2007–2016 可能是彻底不可达的真死链"被 LIVE 证伪**：不存在该缺口。site-survey/catalog 中"2007–2016 或在旧域 jmlr.org/proceedings ⚠核验重定向"的表述**过时且错误**，应改为"**已在 PMLR，jmlr.org 旧路径 404 但无需依赖**"。
- **复刊 Reissue r0–r6 仅覆盖 pre-2007**（AISTATS 1995/1997/1999/2001/2003/2005 + UAI 1998），**与 2007–2016 不重叠**——因为 2007–2016 本就在 PMLR，无需复刊。
- 说明：2007–2016 间"缺"的年份（如 2008）是 **AISTATS 早期为双年会**（2007→2009 隔年，2010 起转年会），**非死链**，volume_map 无该年属正常。
- Wayback/`offline_only` 兜底（design/08 §3）目前**仅对 pre-2007 且未复刊者**才可能需要；2007+ 无需。

### 项 8 · AC-2 锚点：v235(ICML 2024) 总篇数 —— [LIVE] 完成

- **v235 = ICML 2024，总篇数 = 2610**（LIVE 三重互证：卷页 `<div class="paper">` = 2610、`[Download PDF]` = 2610、去重 `/v235/{slug}.html` = 2610）。**页面可数**。
- 卷级 `_config.yml`：`conference_number: 41`、`published: 2024-07-08`、`issn: 2640-3498`。
- **[UNRESOLVED]** DBLP 外源交叉核对：`dblp.org` count API 本次返 **503**（暂时不可用），未取到 DBLP 侧计数。DBLP slug = `conf/icml/icml2024`，建议重写期重试补该列。
- **D-019 锚点行建议**（写入 `tests/fixtures/pmlr/dblp-icml-anchor.json` 等）：
  `{year:2024, venue:"icml", volume:235, paper_count_claimed:2610, dblp_slug:"conf/icml/icml2024", pdf_host:"raw.githubusercontent.com", note:"count 三重互证自卷页；DBLP 待补"}`

---

## 附加发现（未在清单但影响设计）

- **[LIVE] OpenReview 交叉链接（证实 C6）**：每篇 abs 页与 `_posts` md 均带 `openreview` forum id（实测 `AZWqXfM6z9`），卷页每篇 2 个 openreview 链接。→ 建议 enumerate 把它存 `PaperStub.meta['openreview']`（不产 identifier），作 D-007 跨源合并高价值信号。
- **[LIVE] RSS 新卷源（关联 C1）**：`proceedings.mlr.press/feed.xml` 提供结构化 feed。→ `--refresh`/track 探测新卷可轮询 feed.xml，优于 diff HTML 首页（更稳、更省）。
- **[LIVE] IssueRef 字段可填值（解 B1）**：`pub_date` **可得**——`_config.yml.published`（2024-07-08）或 abs 页 `citation_publication_date`；`volume` 存裸数字 `"235"`（`_config.volume:'235'`）；`number` 恒 `None`（PMLR 只有卷无期）；`label` 可由 `_config.shortname`+`year` 组"ICML 2024"或"v235"；`paper_count_claimed` discover 阶段（仅 volume_map）**给不出**，须 enumerate 回填。
- **[LIVE] 无挑战门**：全程无 403/429/验证码/JS 墙；proceedings.mlr.press 与 raw.githubusercontent 均静态直取。

## 一句话给重写者

三条结构化元数据源（卷级 `bibliography.bib` / 单篇 `citation_*` meta / GitHub `_posts` md）字段一致且都自带 `pdf` 真实域——**enumerate 抓一次卷页即可拿全 2610 条元数据 + 每篇 PDF 域，resolve 零网络读 meta**；PDF 域按**上传时间**双托管、Content-Type 不可靠须 `%PDF` 校验；AISTATS 2007–2016 无缺口（评审 C5 证伪）；robots 双域 404、无 ToS、开放获取。
