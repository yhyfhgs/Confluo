---
title: 来源调研：理科（数学/物理/化学）出版商、预印本与平台
status: draft
owner: opus5.5-survey
updated: 2026-09-26
---

# 来源调研：理科（数学/物理/化学）出版商、预印本与平台

> 本文是 v2 重设计"调研阶段"的来源主题之一，产出理科侧的**来源名录（source registry）条目**、**代表性 venue→平台映射**与**接口对接优先级**，供设计阶段与社科、生命科学、CS/AI、聚合源等姊妹主题合并为总名录。
> v1 只覆盖 CS/AI、经济、金融、OR/MS（理科仅登记了 `arxiv-math-oc`），本文**不重复** v1 已勘察的 Elsevier/Wiley/OUP/Crossref/OpenAlex/Unpaywall 机制细节（见 [N113]），只做理科增量与复核。
> 附属证据（同名子目录）：[`natural-sciences/venue-verification-2026-09-26.csv`](natural-sciences/venue-verification-2026-09-26.csv)（115 个理科刊/论文集的 Crossref + OpenAlex 核验原始数据）、[`natural-sciences/request-ledger-2026-09-26.tsv`](natural-sciences/request-ledger-2026-09-26.tsv)（站点/接口直测请求台账，已去除 IP）。

## 摘要（结论速览）

1. **理科期刊元数据可以全部走 Crossref**：对 115 个理科代表刊与论文集系列逐一查询 `api.crossref.org/journals/{ISSN}`，全部可枚举（首轮 17 个 429、1 个 500 经限速重试后成功）[N94]。v1 的"期刊元数据主干 = Crossref"（D-005）在理科成立。需要处理两类坑：ISSN 迁移（Physical Review B 的 2010 年内容只能按旧 ISSN 查到、2024 年内容只能按新 ISSN 查到，必须合并查询 [N114]；核验：切换发生在 2016 年，2015 年内容只能按旧 ISSN 查到 5,001 条，2016 年内容只能按新 ISSN 查到 5,486 条 [N138]）与 Crossref 刊记录数据错误（如 Proc. LMS 电子 ISSN 被登记为 `1234-5678`、GRL 的印刷/电子 ISSN 颠倒）[N94]。
2. **摘要缺口是卡片流的首要风险**。Crossref 当前内容的摘要覆盖率：Elsevier 全部 9 刊为 0.00，ACS 14 刊 0.07–0.15，Nature 系 0.10–0.21，PRL 0.29、PRB 0.11、RMP 0.00，MSP 三刊 0.00，IMS/Duke/International Press ≤0.14。IOP、AIP、EMS Press、OUP、Optica、A&A 则 ≥0.97 [N94]。因此需要**按出版商路由的摘要补齐链**。另外 Crossref 明示部分摘要受出版商或作者版权保护 [N96]。
3. **arXiv OAI-PMH 已支持 `group:archive:category` 三级 set**。ListSets 返回 183 个 setSpec（9 个物理单体 archive 各重复一次，去重后 174 个），`math:math:AG` 按分类收割实测可用 [N62][N63][N61]。v1"archive 级收割 + 客户端过滤"应升级。v1 的 set 推导对物理 archive 会失效：合法值是 `physics:cond-mat`、`physics:hep-th`，而 v1 推导出的是 `cond-mat`、`hep-th`；核验时 `set=cond-mat` 直接返回 `badArgument`（"Set does not exist"），旧名不被当作别名接受 [N132]。
4. **2025–2026 平台迁移密集**，v2 必须有来源漂移监控：
   - ChemRxiv 于 2026-01-21 迁到 Wiley Research Exchange [N67]。新 DOI 形如 `10.26434/chemrxiv.15009478/v1`，旧 Open Engage API 路径现在返回 Cloudflare 挑战 [N70][N69]。
   - RSC 期刊宣布迁 Silverchair（2026-02-26）[N21]，robots 已换成 Silverchair 模板 [N23]。
   - Royal Society 于 2025-12-02 上线 Silverchair [N22]。
   - Publ. Math. IHÉS 已迁 Centre Mersenne（`10.5802/pmihes.*`），但 OpenAlex 仍把它挂在 Springer Nature 名下 [N93][N95]。
   - APS 新 DOI 后缀改为不透明的 `xxxx-xxxx` 形式 [N94]。
   - arXiv 自 2026-07-01 起成为独立非营利机构 [N64]；ADS 于 2026 年向 SciX 过渡 [N85]。
5. **合规、结构化的官方通道比想象中多**：
   - **APS Harvest API**：OA 集可免认证，返回摘要、PhySH 分类、arXiv 号和 CC BY 许可 [N1][N3]。
   - **Springer Nature Meta/OA/Full-text API**：OA API 免费档每日 500 次、每分钟 100 次；做 TDM 时 UA 必须包含 `TextDataMining`；TDMRep 声明保留权利 [N25–N27][N26][N32]。
   - **INSPIRE**：每 5 秒 15 次，元数据以 CC0 为主 [N80]。
   - **zbMATH Open**：REST + OAI-PMH，CC BY-SA 4.0 [N76][N77]。
   - **ADS/SciX**：token 制，每日 5,000 次（各端点单独计）[N83]。
   - **SCOAP3 repo**：CC BY 全文，元数据 CC0 [N90][N91]。
6. **robots 硬约束**：
   - IOPscience 对 `*` 为 `Disallow: /`，AI UA 列表也整体禁止 [N10]。
   - link.springer.com 对 `*` 为 `Disallow: /` 加白名单，`/search.rss` 不在白名单内 [N31]。
   - MathSciNet 基本全禁 [N49]。
   - Optica、Nature、Springer、Research Square、SciEngine 具名禁止 ClaudeBot 等 AI UA [N16][N34][N31][N71][N104]。
   - ACS、AMS、zbmath.org、Cambridge、Preprints.org、SPIE 连 robots.txt 都被 WAF 拦截 [N19][N48][N116][N108][N74][N101]。

   结论：这些站点的后台流程一律零自动化。
7. **出版商 RSS 大多不能作为"最新论文"通道**。Atypon 族 robots 统一禁止 `/rss` 与 `/action`：Wiley、T&F、WSP、ChemRxiv、ESS Open Archive 都是如此；IOP 更是全站禁止 [N107][N41][N44][N68][N73][N10]。

   可用的例外：
   - APS feeds：小时级更新，但版权声明为"Personal use only"[N7]。
   - nature.com RSS [N35]。
   - SIAM、Science、PNAS 的 `/action/showFeed`，robots 明确 Allow [N46][N37][N38]。
   - Quantum [N99]。

   默认做法：以 Crossref 的 `from-created-date` 增量驱动。
8. **理科 OA 比重高**，CC BY 类全文可以进入多用户共享缓存：
   - JHEP、PLB、NPB、EPJC 在 OpenAlex 中为期刊级 OA 且 APC=0，符合 SCOAP3 资助特征 [N95]。核验：SCOAP3 2025–2027 期刊表中这 4 刊为 100% 覆盖；PRL（13%）、PRD（56%）、PRC（9%）、PTEP、Chinese Physics C、Acta Phys. Pol. B、AHEP 只覆盖投到 arXiv HEP 分类的文章 [N117]。
   - EMS Press 22 种 S2O 刊，2024–2026 全 OA [N50]。
   - AAS 期刊、MNRAS、A&A、PRX 系、NJP、Optica、Optics Express 均为全 OA [N95]。
   - AIP 的 JAP、Physics of Plasmas 在 2024–2025 年经 S2O 全 OA [N14]。核验修正：AIP 已于 2025-10-29 宣布 S2O 试点在 2025 年底结束，2026 年起两刊转入 Author Select / AIP Fusion / Read and Publish 框架，不再按 S2O 整刊开放，OA 改为作者自选或机构协议 [N118]。
   - Royal Society 8 种订阅刊在 2026 年走 S2O [N59]；2026-02-16 官方确认 2026 年门槛已达成 [N119]。

   但 arXiv 多数论文采用非独占许可，**平台不得自行再分发 arXiv PDF** [N60]。
9. **学科分类法可直接作为推荐系统的标签空间**：arXiv category（元数据 CC0）[N60]、MSC（zbMATH Open KG 含 6.7K+ MSC 类）[N79]、PhySH（APS，CC0，GitHub 提供 JSON/RDF）[N97]。APS Harvest 的记录直接带 `classificationSchemes` 字段 [N3]。核验补充：MSC2020 方案本身由 MR 与 zbMATH 以 **CC BY-NC-SA 4.0** 联合发布 [N120]，带非商业与相同方式共享条件，不同于 PhySH 的 CC0。
10. **TDM/批量授权普遍是"个案、付费或须申请"**：
    - ACS：付费方案，按项目交付 [N18]。
    - Springer Nature（核验修正）：订阅机构的 TDM 权利不另收费，但只限直接下载、每秒 1 次；TDM API 另行收费 [N25]。
    - IOP：邮件申请，经 SFTP 交付 [N9]。
    - AIP：个案授权（二手来源）[N15]。
    - RSC：需申请（二手来源）[N15]。
    - APS：Harvest 全量需授权 [N2]。
    - Cambridge：每小时下载超过 500 个 PDF 可撤销访问 [N58]。
    - WSP：短时间内 200 次下载即切断（二手来源）[N45]。

    v2 的受控全文只能走"用户自有凭证 + 交互式或低频 + 私有存储"。

## 1. 调研范围与方法

### 1.1 范围

- **学科**：
  - 数学（含应用数学、概率）。
  - 物理（含高能、凝聚态、天文、光学、流体）。
  - 化学（含化学物理）。
  - 材料与地学只做简述（§2.3.6、§2.8.4）。
- **层级**：
  - L1：出版商、学会平台、期刊平台、预印本、会议平台。
  - L2：学科数据库、仓库、学科聚合（zbMATH Open、MathSciNet、INSPIRE、ADS/SciX、PubChem、SCOAP3、Numdam）。
- **不在本文**：
  - 生物、医学、心理（姊妹主题）。
  - Crossref/OpenAlex/S2/Unpaywall/CORE 的通用机制（v1 已勘察 [N113]，v2 聚合主题另述）。本文只给这些聚合源的**理科侧实测数据**，例如 §2.4 的摘要覆盖。
  - CNKI 等中文聚合库（仅在 §2.3.6 简述中文期刊平台）。

### 1.2 证据等级与标注

| 标注 | 含义 |
|---|---|
| **[LIVE]** | 本 agent 于 2026-09-26（UTC 约 14:59–17:30）从本机直接请求的结果，包括 HTTP 状态、响应头、正文片段。逐条见附属台账。核验阶段的直测（UTC 约 19:10–19:50）另记在文末"核验记录"，未并入附属台账 |
| **[DOC]** | 同日经 WebFetch 读取的官方页面、官方文档或官方 GitHub 仓库 |
| **[SEC]** | 二手来源（高校图书馆指南、维基百科、搜索引擎摘要）。置信度较低，设计阶段须复核一手来源 |
| **⚠ 未核验** | 本轮无法取证，列出只为提示 |
| 覆盖率数值 | 取自 Crossref `/journals/{ISSN}` 的 `coverage.{abstracts,resource-links,licenses}-current` 字段，即 Crossref 定义的"current"内容段，口径以 Crossref 文档为准 [N94] |

引用号 `[Nxx]` 对应 §5。编号前缀 N 表示 natural sciences，合并总名录时可避免与姊妹文档的 `[Rxx]` 冲突。

### 1.3 本轮自我约束（合规纪律）

- **UA**：`PaperCrawler-Survey/0.2 (personal research tool; …)`，诚实标识，不冒充浏览器。按用户隐私要求**未在 UA 或 URL 中携带邮箱**，所以 Crossref 只能走 public pool。
- **请求频率**：每站点以 1 次为主（robots、首页或 1 个 API 样本）。同站间隔 ≥2.5 s；Crossref 重试间隔 6 s；arXiv 两次请求间隔大于 3 s。
- **遇拦即停**：遇到 Cloudflare、Incapsula、Akamai、Radware 挑战时立即记录并停止，零重试、零绕过。
- **不使用凭证**：未登录，未使用任何凭证或 API key，未下载任何论文 PDF 全文。
- **请求量**：站点/接口单次请求约 90 条。另有 Crossref 约 160 次、OpenAlex 109 次（匿名，单实体查询 `x-ratelimit-cost-usd: 0`）、DataCite 1 次、GitHub API 约 30 次。台账共 97 行，批量查询以汇总行记录。

### 1.4 过程记录（可复现）

**1.4.1 环境。**
- **网络出口**：本机 macOS 经本地代理出网（DNS fake-IP 段 198.18.0.0/15）。Cloudflare 边缘节点在 LAX、SEA、NRT、HKG 等地之间变化。**因此挑战与拦截结论受代理出口信誉影响，不等价于校园网或家庭宽带下的结果。**
- **WebFetch 出口**：WebFetch 走另一出口，对 ams.org、science.org、rsc.org、pubs.acs.org、aanda.org、essopenarchive.org 等多次返回 403 或 TLS 错误，这些条目均改用直测或降级为 [SEC]。
- **WebSearch 预算**：会话共享的 WebSearch 预算为 200 次，在本 agent 第 32 次检索时耗尽。之后改用"已知 URL 的 WebFetch + 直测"。

**1.4.2 WebSearch 检索式（按执行顺序，均为 2026-09-26）。**

1. `APS Physical Review text and data mining harvest API policy harvest.aps.org`
2. `IOP Publishing text and data mining policy IOPscience TDM`
3. `AIP Publishing text and data mining policy pubs.aip.org`
4. `Optica Publishing Group text and data mining policy`
5. `"AIP Publishing" "text and data mining" rights@aip.org TDM license subscribers`
6. `ACS Publications text and data mining policy subscribers API 2025`
7. `Royal Society of Chemistry text and data mining policy pubs.rsc.org`
8. `api.springernature.com meta v2 json rate limit "Basic" plan calls per day Springer Nature API portal 2025`
9. `Science AAAS science.org terms of service text and data mining "reasonable" rate non-commercial`
10. `PNAS text and data mining policy pnas.org TDM license`
11. `De Gruyter Brill text and data mining policy TDM reservation`
12. `World Scientific worldscientific.com text and data mining policy`
13. `AMS journals free access back issues older than five years JAMS Transactions Proceedings Mathematics of Computation`
14. `EMS Press Subscribe to Open 2026 journals open access ems.press`
15. `Project Euclid platform OAI-PMH projecteuclid.org Duke University Press journals list`
16. `SIAM journals text and data mining terms of use epubs.siam.org automated download`
17. `zbMATH Open API api.zbmath.org OAI-PMH license CC BY-SA rate limit documentation`
18. `INSPIRE-HEP REST API rate limit "15 requests" 5 seconds inspirehep.net/api documentation`
19. `NASA ADS API rate limit 5000 requests per day token SciX api.adsabs.harvard.edu 2025`
20. `SciX Science Explorer ADS transition scixplorer.org API 2026 astrophysics data system`
21. `ChemRxiv public API Cambridge Open Engage items endpoint 2025 2026 new platform migration`
22. `Preprints.org MDPI API OAI-PMH feed preprints.org`
23. `Research Square preprint platform 2026 Springer Nature In Review changes API`
24. `ESS Open Archive essopenarchive.org Authorea AGU Wiley preprint platform API`
25. `ChemRxiv announcement 2025 new platform "ChemRxiv" moving Cambridge University Press Open Engage closure`
26. `"Cambridge Open Engage" closing OR retire OR sunset 2025 2026 preprint platform`
27. `chemrxiv API broken 2026 "Research Exchange" paperscraper OR "public-api" chemrxiv items`
28. `PNAS research articles free after six months open access policy 2026 pnas.org`
29. `APS Physical Review open access 2026 announcement "Physical Review" journals fully open access transition`
30. `Royal Society of Chemistry transition all journals fully open access 2028 progress 2026`
31. `IOP Publishing 2026 open access transition journals "fully open access" announcement`
32. （预算耗尽，未执行）`Royal Society of Chemistry Silverchair platform migration pubs.rsc.org 2026`；`ChemRxiv "Research Exchange" Wiley launch January 2026 API …`。前者改由 Silverchair 新闻页 WebFetch 取证 [N21][N22]。

**1.4.3 WebFetch 访问的页面（2026-09-26）。**

| 结果 | 页面 | 对应引用 |
|---|---|---|
| 成功 | APS Harvest 文档与首页、APS terms、APS datasets、APS Open Science | [N1][N2][N4][N5][N8] |
| 成功 | IOP TDM 政策 | [N9] |
| 成功 | Cranfield、ASU 图书馆 TDM 汇总 | [N15][N45] |
| 成功 | ACS TDM 方案页 | [N18] |
| 成功 | Springer Nature TDM 页、支持页（2 篇）、OA/Metadata API 产品页 | [N25–N29] |
| 成功 | Elsevier TDM | [N36] |
| 成功 | T&F TDM | [N40] |
| 成功 | EMS Press 公告与 S2O 页 | [N50–N52] |
| 成功 | Project Euclid About 与 Librarians | [N54][N55] |
| 成功 | Cambridge Core terms | [N58] |
| 成功 | Royal Society S2O | [N59] |
| 成功 | arXiv ToU、OAI 文档、博客 3 篇 | [N60][N61][N64][N65][N115] |
| 成功 | ACS 的 ChemRxiv 迁移 FAQ | [N67] |
| 成功 | Wikipedia Authorea | [N72] |
| 成功 | zbMATH API 条款 | [N76] |
| 成功 | INSPIRE API 文档 | [N80] |
| 成功 | ADS 开发者 API 文档 | [N83] |
| 成功 | arXiv:2609.18091 | [N85] |
| 成功 | SCOAP3 repository 说明 | [N90] |
| 成功 | Crossref REST API 文档 | [N96] |
| 成功 | Silverchair 新闻列表与 RSC 新闻 | [N21][N22] |
| 失败（403、TLS 错误或 JS 空壳，已降级处理） | rsc.org TDM 页、pubs.acs.org terms、science.org librarian portal、ams.org subscriber info、pubs.ams.org、aanda.org、essopenarchive.org/about、chemrxiv.org API 文档与新闻页、opticaopen.org、UNSW 指南、publishing.aip.org（改为直测成功）、dev.springernature.com 文档页、PubChem 文档页、ADS 限速页、scixplorer.org | — |

**1.4.4 [LIVE] 直测（明细见附属台账，共 97 行）。**

- 53 个域名的 `robots.txt`。
- 13 个 feed/API 探针：APS RSS、IOP RSS、nature.com RSS、Quantum RSS、zbMATH OAI 与 REST、INSPIRE、EMS、MSP、SciPost、PoS、Numdam OAI、EarthArXiv API。
- arXiv OAI 2 次：ListSets 与分类级 ListIdentifiers。
- ChemRxiv 旧 API 1 次、RSC 首页 1 次、APS Harvest OA 集 1 次。
- TDMRep 6 次：T&F、Wiley、IOP、Springer、SN 策略、Nature。
- PubChem 2 次、SCOAP3 1 次。
- Crossref：journals 批量、prefixes、ISSN 别名窗口。
- OpenAlex sources 批量、DataCite 1 次。

**1.4.5 偏差与自我披露。**

- (a) 对 `iopscience.iop.org/journal/rss/…` 发出了 1 次请求，事后才发现该站 robots 对 `*` 为 `Disallow: /` [N10]。
- (b) 对 PubChem PUG-REST 发出了 1 次请求，事后发现 `/rest/pug/` 落在其 robots `*` 组的 Disallow 内 [N88]。PUG-REST 本身是 PubChem 官方文档化的编程接口 [N89]。
- (c) Crossref public pool 共出现 17 次以上 429（推测是多 agent 共享出口并发所致），改为 6 s 间隔后恢复。响应头观测为 `X-Rate-Limit-Limit: 5` / `X-Rate-Limit-Interval: 1s`，而姊妹文档同日观测到 `limit: 1` [N112]。**核验修正**：两者差异不是"动态限额"，而是 Crossref 自 2025-12-01 起按请求类型分档：公共池单条记录 5 次/秒、列表查询 1 次/秒，并发均为 1；polite 池分别为 10 次/秒与 3 次/秒，并发 3 [N121]。核验时实测 `/works?filter=…&rows=5` 返回 `x-api-pool: public-array`、`x-rate-limit-limit: 1`；`/journals/{ISSN}` 与 `/works/{DOI}` 返回 `public-single`、`limit: 5`，两者都带 `x-concurrency-limit: 1`。
- (d) 首轮 Crossref prefix 查询因 `select`/`sort` 参数不合法得到 10 次 400，修正后重跑。

(a)(b) 正是 v2 需要在 ADR 中裁决的"robots 与官方 API/Feed 冲突"样例，见 §4-1。

## 2. 主体内容

### 2.1 v1 基线与理科差距

| 维度 | v1 现状（证据） | 理科差距 |
|---|---|---|
| VenueSpec 学科枚举 | `field: list[Literal["finance","econ","cs_ai","or_ms"]]`（`src/paper_crawler/types.py:204`） | 没有 math、physics、chemistry、materials、earth、astro 等枚举，需扩展，并配套学科分类法（§3-11） |
| arXiv | adapter 已实现。理科只登记了 `arxiv-math-oc`。set 由 archive 段推导（`category.split('.')[0]`），带连字符的 archive 须显式写 `quirks.arxiv_set`（`scripts/gen_arxiv_venues.py`、`adapters/arxiv/adapter.py::_oai_target`） | 物理 archive 的合法 set 是 `physics:cond-mat`、`physics:hep-th` 等。v1 推导出的 `cond-mat`、`hep-th` 不在 ListSets 中 [N62]；核验实测 `set=cond-mat` 返回 `badArgument`（"Set does not exist"），旧名不被接受 [N132]。数学 32 个、物理 51 个叶子分类都未登记（§2.3.5） |
| 期刊元数据 | `crossref` adapter 按 (ISSN, 年) 枚举，`published`/`created` 双日期轴。摘要"常缺约 70%"（`adapters/crossref/parse.py` 注释） | §2.4 给出按出版商的精确缺口。PRB 等刊需要多 ISSN 合并查询 [N114] |
| 全文 adapter | 已实现 `elsevier_sd`、`wiley`、`oup_silverchair`；`springer`、`siam`、`cambridge` 仅为 planned（`docs/design/adapters/README.md`） | APS、IOP、ACS、RSC、AIP、AMS 等理科主力平台都没有 adapter，而且多数**不应**做站点抓取 adapter（§3-4） |
| OA 兜底 | `unpaywall` | 理科还有 SCOAP3、APS OA 集、SN OA API、EMS S2O 等更强、许可更明确的 OA 通道 |
| 学科 L2 | 无 | zbMATH Open、INSPIRE、ADS/SciX 均未接入 |
| 合规框架 | D-014：诚实 UA、遵守 robots/Content-Signal、敏感站白名单式抓取 | 需要补充"robots 与官方 API/Feed 冲突"以及"多用户下全文/摘要的再分发边界"两条裁决（§4-1、§4-2） |

### 2.2 来源名录总表（统一列）

**列说明。**
- 层级类型沿用任务约定：L1-publisher、L1-preprint、L1-journal-platform、L1-conference-platform、L2-repository、L2-aggregator。
- 覆盖率数值为 Crossref `*-current` 字段 [N94]。
- "v1 是否已支持"只有三种取值：
  - **是**：adapter 已实现。
  - **部分**：v1 的 `crossref` 通用 adapter 可按 ISSN 枚举元数据，但没有 VenueSpec，也没有全文 adapter。
  - **否**。
- 优先级：P0 为 v2 首批；P1 为第二批；P2 为按需；"仅元数据"表示只经 Crossref 或官方 API 收录元数据；"排除"表示不做任何自动化。

#### 2.2.1 L1 出版商、学会平台与期刊平台

| source_id（snake_case） | 名称 | 层级类型 | 学科 | 平台技术栈 | 元数据通道 | 最新论文通道 | 全文通道与门控 | 认证方式 | 限速与 ToS/robots 要点（来源+日期） | v1 是否已支持 | 建议优先级及理由 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `aps` | American Physical Society（Physical Review 系列，journals.aps.org） | L1-publisher | 物理 | 自研 + Cloudflare [LIVE N6] | 委托 Crossref（前缀 10.1103，ISSN 别名需合并 [N114]）；官方 Harvest API 返回 JSON，含摘要、PhySH、arXiv 号、许可 [N1][N3] | RSS `feeds.aps.org/rss/recent/{code}.xml`（RSS 1.0，小时级）[LIVE N7]；Harvest `from`/`until`；Crossref `from-created-date` | OA：PRX、PRX Quantum、PR Research 为全 OA，另有 SCOAP3/CC BY 单篇。Harvest `set=openaccess` 可免认证取 JSON/XML/PDF [N1][LIVE N3]。其余订阅 | 机构订阅。Harvest 全量需 JWT key、IP 授权或 CHORUS token，联系 help@aps.org [N1][N2] | ToS 禁止系统化下载及使用 robots/加速器 [N4]。robots（2026-09-23 修改）`*` 只禁 /search、/account、/login；文件自述由 CF 托管前置 AI 禁列与 `Content-Signal: ai-train=no`，但取回的文件中未见前置块 [LIVE N6]。RSS 版权"Personal use only" [N7] | 部分 | **P0**：物理核心（PRB/PRD/PRL 2025 年分别 5,677/5,126/3,015 个 DOI [N94]）。Harvest OA 集是合规的"元数据 + 摘要 + OA 全文"一体通道 |
| `iop` | IOP Publishing（IOPscience；含 AAS 天文刊、JPCS） | L1-publisher | 物理/天文 | 自研 + Radware Bot Manager（`.well-known` 路径 302 到挑战脚本）[LIVE N12] | 委托 Crossref（10.1088、AAS 为 10.3847；摘要 0.98–1.00，TDM link 1.00）[N94] | Crossref 增量。站点 RSS 可用 [LIVE N11]，但 robots `*` 为 `Disallow: /`，因此不用 | OA（NJP、JPCS、AAS 刊）或订阅。批量 TDM 须发邮件申请，经 SFTP 交付；API 访问需另签书面协议 [N9] | 机构订阅 | robots：只放行具名搜索引擎，AI UA 与 `*` 均 `Disallow: /` [LIVE N10]。政策（2026-07 更新）写明平台"blocks systematic downloading" [N9] | 部分 | **P0（仅元数据）**：Crossref 元数据质量在理科中最好。全文只走用户交互式单篇或 OA 副本（SCOAP3/arXiv/Unpaywall） |
| `aip` | AIP Publishing（pubs.aip.org；含 AIP Conf. Proc.） | L1-publisher | 物理/化学物理 | Silverchair（robots 模板指纹）+ Cloudflare [LIVE N13] | 委托 Crossref（10.1063；摘要 0.98–0.99，licenses 0.07–0.19）[N94] | Crossref 增量；站点 RSS ⚠ 未核验 | 订阅为主。JAP 与 Physics of Plasmas 在 2024–2025 年经 S2O 全 OA [LIVE N14]；核验修正：S2O 试点已于 2025 年底结束，2026 年起两刊不再按 S2O 整刊开放，OA 改走 Author Select / AIP Fusion / R&P [N118] | 机构订阅（robots 可见 Shibboleth 路径） | TDM 个案授权；未经授权禁止系统下载或抓取 [SEC N15] | 部分 | **P1**：APL/JCP/PoF 体量大（PoF 2025 年 6,192 个 DOI）。元数据走 Crossref，全文走用户单篇 |
| `optica` | Optica Publishing Group（opg.optica.org） | L1-publisher | 光学/光子学 | 自研（ColdFusion `.cfm`）[LIVE N16] | 委托 Crossref（10.1364；摘要 0.98）[N94] | Crossref 增量 | Optica、Optics Express 等为全 OA（OpenAlex 期刊级 `is_oa`）[N95]；其余订阅 | 机构订阅；robots 可见 OpenAthens 路径 | robots 具名禁止 ClaudeBot、anthropic-ai、GPTBot 等 30 多个 AI UA；`*` 只禁 viewmedia、user 等 [LIVE N16]。数据条款保留 TDM 与 AI 训练权利 [SEC N17]。核验补充：条款页对本系统 UA 302 到 Radware Bot Manager（validate.perfdrive.com）挑战，未能直读 [N131] | 部分 | **P1**：OA 比例高。本系统 UA 不属被点名的 AI 爬虫，但仍须遵守数据条款 |
| `edp_sciences` | EDP Sciences（A&A、EPJ Web of Conferences） | L1-publisher | 天文/物理 | 自研（Joomla robots 模板）[LIVE N102] | 委托 Crossref（A&A 摘要 0.99；EPJ WoC 0.99）[N94] | Crossref 增量 | A&A 期刊级 `is_oa=true` 且在 DOAJ [N95]；EPJ WoC 为 OA 论文集（许可逐卷 ⚠） | 无（OA） | robots 只禁 CMS 目录 [LIVE N102] | 部分 | **P1**：天文核心 OA 刊 |
| `royal_society` | Royal Society Publishing（Proc. R. Soc. A、Phil. Trans. A） | L1-publisher | 综合/数理 | Silverchair（2025-12-02 上线）[DOC N22] | 委托 Crossref（摘要 0.89–0.98）[N94] | Crossref 增量 | 8 种订阅刊 2026 年以 S2O 转 OA，前提是订阅门槛达成 [DOC N59]；2026-02-16 官方确认门槛已达成 [N119] | 机构订阅 | 核验补充：robots 为 Silverchair 模板，`*` 只禁检索、登录、下载等路径，Last-Modified 2026-09-26 [N130] | 部分 | **P2** |
| `scipost` | SciPost（SciPost Physics 等） | L1-journal-platform | 物理 | 自研 Django（git.scipost.org 开源）[LIVE N98] | 委托 Crossref（10.21468；2026 年至今 958 个 DOI；摘要/TDM link 0.96）[N70][N94]。站点有 `/api/` 页 ⚠ 接口细节未核验 | Crossref 增量；站点 `/feeds` 页 [LIVE N98] | 全 OA [N95] | 无 | robots 只禁 /search 和少数 AI UA（Applebot-Extended、meta-externalagent）[LIVE N98] | 否 | **P1**：OA 且元数据完备，适合进入共享缓存 |
| `quantum_journal` | Quantum（arXiv overlay 刊） | L1-journal-platform | 量子 | WordPress [LIVE N99] | 委托 Crossref（摘要与 TDM link 均 1.00）[N94] | RSS `/feed/`，robots 允许 [LIVE N99] | 全 OA [N95]；全文即 arXiv 版本 | 无 | robots 只禁 wp-admin [LIVE N99] | 否 | **P2** |
| `springer_nature_link` | Springer Nature Link（link.springer.com；含 Birkhäuser 等品牌） | L1-publisher | 全理科 | 自研"Oscar Platform"（server 头）[LIVE N31] | 官方 Meta、Metadata、OA、Full-text（TDM）API，基址 `https://api.springernature.com/`，需 api_key [DOC N29][N30]；另委托 Crossref（10.1007；摘要 0.40–0.99）[N94] | Crossref 增量；Meta API 按日期约束查询 | OA：JHEP/EPJC 为期刊级 OA 且 APC=0 [N95]，另有 OA API（CC BY）。订阅内容：订阅机构对订阅范围内内容的 TDM 权利不另收费（直接下载）；**核验修正：TDM API 另行收费** [DOC N25] | 每用户 api_key；机构 IP 或 SSO | 直接下载 ≤1 req/s；付费 TDM API（带 key）150 req/min [DOC N25]。API 条款禁止以多账号或多 key 规避限额 [N126]。TDM 流量的 UA 须包含 `TextDataMining` [DOC N26]。OA API 免费档每日 500 次、每分钟 100 次；Premium 每日 10,000 次、每分钟 300 次 [DOC N27]。robots `*` 为 `Disallow: /` 加白名单（含 `/article/`、`/content/`、`/journal*`；`/search.rss` 不在白名单）；ClaudeBot 等具名禁止 [LIVE N31]。TDMRep `tdm-reservation: 1`，挖掘需 `obtainConsent` [LIVE N32][N33] | 否（v1 planned `springer`） | **P0**：数学/物理顶刊集中（Inventiones、Math. Ann.、CMP、JHEP），官方 API 合规路径清晰 |
| `nature_portfolio` | Nature Portfolio（nature.com） | L1-publisher | 全理科 | 与 SN Link 同平台（Oscar）[LIVE N34] | 委托 Crossref（摘要只有 0.10–0.21，Nat. Commun. 0.47）[N94]；另有 SN Meta API | RSS `https://www.nature.com/{code}.rss` [LIVE N35] | 订阅，另有 OA 刊（Nat. Commun.、LSA 等）[N95] | 机构订阅 | robots `*` 禁 /search 等；ClaudeBot 等具名 `Disallow: /`；TDMRep 与 SN 相同 [LIVE N34] | 否 | **P0（元数据 + RSS）**：顶刊的新鲜度靠 RSS，摘要须由 SN API 或 OpenAlex 补齐 |
| `elsevier_sd` | Elsevier ScienceDirect（含 Cell Press 的 Chem 等） | L1-publisher | 全理科 | 自研 + Cloudflare（v1 勘察 [N113]） | 委托 Crossref（10.1016；9 刊摘要**全部 0.00**）[N94]；Elsevier API（v1 已接） | Crossref 增量 | 订阅或 OA（PLB、NPB 为期刊级 OA 且 APC=0 [N95]）。TDM 经开发者门户 API key，限非商业 [DOC N36] | 每用户 API key（+ insttoken） | v1 已勘察：robots 禁止 20 多个 AI UA（含 claude-code）[N113] | **是** | **P0（沿用）**：只需批量登记理科 VenueSpec，并为其增加摘要补齐 |
| `wiley_vch` | Wiley Online Library（Wiley-VCH：Angew、Adv. Mater.、Chem. Eur. J.；另有 CPAM，以及 LMS 与 AGU 的期刊，其托管关系 ⚠ 以 OpenAlex host 为据） | L1-publisher | 化学/材料/数学/地学 | Atypon + Cloudflare [LIVE N107] | 委托 Crossref（10.1002 与 10.1111；摘要 0.61–0.93；TDM link 0.28–0.56）[N94] | Crossref（robots 禁 /rss 与 /action）[LIVE N107] | 订阅或混合 OA；TDM API（v1 已接） | 每用户 TDM token | robots Crawl-delay 1；`/.well-known/tdmrep.json` 被 Allow，但取回时遇 CF 挑战 [LIVE N107] | **是** | **P0（沿用）** |
| `oup` | Oxford Academic（IMRN、MNRAS、NSR 等） | L1-publisher | 数学/天文/综合 | Silverchair + Cloudflare [LIVE N107] | 委托 Crossref（10.1093；摘要 0.78–0.98）[N94] | Crossref 增量 | MNRAS、NSR 期刊级 OA [N95]；IMRN 订阅 | 机构订阅 | robots 无 AI 条目（与 v1 一致）[LIVE N107] | **是**（`oup_silverchair`） | **P1（沿用）** |
| `cambridge_core` | Cambridge Core（JFM、Forum of Math. Pi/Sigma、Compositio） | L1-publisher | 数学/流体 | 自研 + Cloudflare；robots.txt 本身也被挑战 [LIVE N108] | 委托 Crossref（10.1017；摘要 0.76–0.99）[N94] | Crossref 增量 | Forum Pi/Sigma 全 OA [N95]；其余订阅 | 机构订阅 | ToU：对合法可及内容可做非商业 TDM；个人或集体下载超过每小时 500 个 PDF 时可撤销访问 [DOC N58] | 否（v1 planned `cambridge`） | **P1** |
| `aaas_science` | Science / AAAS（science.org） | L1-publisher | 综合 | Atypon + Cloudflare [LIVE N37] | 委托 Crossref（10.1126；摘要 0.85–0.98；licenses 0.05–0.10）[N94] | eTOC `/action/showFeed`，robots 明确 Allow [LIVE N37] | Science 订阅；Science Advances 全 OA [N95] | 机构订阅 | robots 具名禁止 anthropic-ai、GPTBot、CCBot 等 [LIVE N37]。TDM 限非商业，须以"reasonable rate and speed"进行 [SEC N15] | 否 | **P1** |
| `pnas` | PNAS（pnas.org） | L1-publisher | 综合 | Atypon + Cloudflare [LIVE N38] | 委托 Crossref（10.1073；摘要 0.85）[N94] | eTOC `/action/showFeed`，robots 明确 Allow [LIVE N38] | 订阅；6 个月后经 PMC 免费，另有即时 OA 选项 [SEC N39]。核验：NLM PMC 刊表记 PNAS 为 Release Delay 6 months、All articles 存缴 [N122] | 机构订阅 | robots 只具名禁止 GPTBot [LIVE N38] | 否 | **P1**：6 个月后可走 PMC OA 副本 |
| `tandf` | Taylor & Francis Online（Mol. Phys. 等） | L1-publisher | 物理/化学/数学 | Atypon + Cloudflare [LIVE N41] | 委托 Crossref（10.1080；Mol. Phys. 摘要 0.00）[N94] | Crossref（robots 禁 /rss、/action）[LIVE N41] | 订阅。订阅者可做非商业 TDM 且不另收费（STM 模型许可），须发邮件到 tdm@ 报备 [DOC N40] | 机构订阅 | robots Crawl-delay 1；`tdmrep.json` 被 Allow，但取回时遇 CF 挑战 [LIVE N41] | 否 | **P1（元数据）** |
| `degruyter_brill` | De Gruyter Brill（degruyterbrill.com：Crelle、Pure Appl. Chem. 等） | L1-publisher | 数学/化学/物理 | 自研（CloudFront）；degruyter.com 301 跳转过来 [LIVE N42] | 委托 Crossref（10.1515；摘要 0.87–1.00；TDM link 1.00）[N94] | Crossref 增量 | 订阅或 OA 刊 | 机构订阅 | robots 明文依德国著作权法 §44b 保留商业 TDM 权利，并具名禁止 GPTBot、CCBot、Google-Extended 等 [LIVE N42]。二手来源对其 TDM 许可口径互相矛盾 [SEC N15][N43] | 否 | **P1（元数据）** |
| `world_scientific` | World Scientific（IJMPA、Commun. Contemp. Math. 等） | L1-publisher | 物理/数学 | Atypon + Cloudflare [LIVE N44] | 委托 Crossref（10.1142；摘要 0.96–0.99；TDM link 0）[N94] | Crossref（robots 禁 /rss）[LIVE N44] | 订阅 | 机构订阅 | robots Crawl-delay 1 [LIVE N44]。平台在短时间内 200 次下载后会自动切断 [SEC N45] | 否 | **P2（元数据）** |
| `acs` | ACS Publications（pubs.acs.org） | L1-publisher | 化学/材料 | ⚠ 未能核验（robots 被 WAF 拒）。据 `/doi/`、`/action/showFeed` 的 URL 惯例推断为 Atypon | 委托 Crossref（10.1021；**摘要只有 0.07–0.15**；TDM link 0.82–0.98）[N94] | Crossref 增量 | 订阅；OA 刊有 JACS Au、ACS Central Science [N95]。TDM 是付费"解决方案"，按项目交付 [DOC N18] | 机构订阅 | robots.txt 本身返回 Cloudflare 403"administrative rules" [LIVE N19]。二手来源称 TDM 不被允许（2023-03）[SEC N15] | 部分 | **P0（仅元数据）**：化学最大出版商，但摘要须另找来源；全文只走用户交互式单篇 |
| `rsc` | Royal Society of Chemistry（pubs.rsc.org） | L1-publisher | 化学 | Silverchair：2026-02-26 公告迁移期刊组合 [DOC N21]，2026-09-26 robots 已是 Silverchair 模板 [LIVE N23]；首页有 Cloudflare 挑战 [LIVE] | 委托 Crossref（10.1039；摘要 0.77–0.93；TDM link 0）[N94] | Crossref 增量 | Chemical Science 等为全 OA [N95]；其余订阅。TDM 须提前申请，以 XML 交付 [SEC N15][N20] | 机构订阅 | 依 DSM 指令第 4 条保留 TDM 权利 [SEC N20]。OA 策略已从"2028 年全 OA"改为区域化模式 [SEC N24] | 部分 | **P1**：正处迁移期，URL 与 PDF 路径须等迁移完成后重勘 |
| `ccs_chemistry` | CCS Chemistry（中国化学会，chinesechemsoc.org） | L1-publisher | 化学 | Atypon（robots 模板）[LIVE N104] | 委托 Crossref（摘要 0.00）[N94] | Crossref 增量 | 全 OA，在 DOAJ [N95] | 无 | robots 为 Atypon 模板，Crawl-delay 1 [LIVE N104] | 否 | **P2** |
| `ams` | American Mathematical Society（ams.org / pubs.ams.org） | L1-publisher | 数学 | 自研 ⚠ + Cloudflare 挑战（robots.txt 也被挑战）[LIVE N48] | 委托 Crossref（10.1090；摘要 0.70–0.87）[N94] | Crossref 增量 | 订阅；**5 年滑动墙后免费** [SEC N47] | 机构订阅 | 无法读取 robots，因此不做站点自动化 | 部分 | **P1**：数学核心（JAMS、Trans.、Math. Comp.），全文只走用户单篇 |
| `siam` | SIAM Publications Library（epubs.siam.org） | L1-publisher | 应用数学 | Atypon + Cloudflare [LIVE N46] | 委托 Crossref（10.1137；摘要 0.76–1.00）[N94] | Crossref；eTOC `/action/showFeed` 被 robots 明确 Allow [LIVE N46] | 订阅；SIURO 为 OA（v1 [N113]） | 机构订阅 / Shibboleth | robots Crawl-delay 1，只具名禁止 GPTBot [LIVE N46]。TDM 不被许可（2023）[SEC N15] | 否（v1 planned `siam`） | **P1** |
| `ems_press` | EMS Press（欧洲数学会出版社） | L1-publisher | 数学 | 自研 ⚠；robots 全放行 [LIVE N53] | 委托 Crossref（10.4171；摘要 1.00）[N94] | Crossref 增量（站点 RSS ⚠ 未见） | **22 种 S2O 刊在 2024–2026 年连续全 OA（CC BY 4.0）**，往期仍为订阅 [DOC N50][N52]。FoCM、Archiv der Math. 自 2027 年起以 L2O 模式在 EMS Press 出版 [DOC N51] | 无（当年卷 OA） | robots `Allow: /` [LIVE N53] | 否 | **P1**：高质量 OA 数学源，接入成本低 |
| `project_euclid` | Project Euclid（Duke University Press 托管；IMS、Duke Math. J. 等 100 多种刊） | L1-journal-platform | 数学/统计 | IIS（平台 ⚠）[LIVE N56] | 委托 Crossref（各出版者前缀；Duke/IMS 摘要只有 0.09–0.14）[N94]。OAI-PMH ⚠：OpenAIRE 仍登记旧 DPubS 端点，现行端点未核验 | Crossref 增量 | 超过 80% 的文章开放 [DOC N54]；其余订阅 | IP / Shibboleth（eduGAIN）[DOC N55] | robots `Crawl-delay: 10` [LIVE N56] | 否 | **P1** |
| `msp` | Mathematical Sciences Publishers（msp.org：G&T、ANT、APDE、PJM 等） | L1-publisher | 数学 | 自研静态站（Apache；每刊一个 sitemap）[LIVE N57] | 委托 Crossref（10.2140；**摘要 0.00**）[N94] | Crossref；站点 sitemap | 订阅；S2O 状态 ⚠ 未核验 | 机构订阅 | robots 只列 sitemap，无禁令 [LIVE N57] | 否 | **P1**：顶级几何/数论刊，摘要须从 arXiv 或 zbMATH 补 |
| `centre_mersenne_numdam` | Centre Mersenne / Numdam（MathDoc，CNRS） | L1-journal-platform（兼 L2-repository） | 数学 | 自研（WordPress 前台 + Numdam OAI）[LIVE N92][N105] | Crossref（10.5802）+ Numdam OAI-PMH `http://www.numdam.org/oai`（earliestDatestamp 2018-10-09）[LIVE N92] | Crossref / OAI 增量 | 多为钻石 OA ⚠。**Publ. Math. IHÉS 已迁至 Centre Mersenne**（`10.5802/pmihes.*`）[LIVE N93] | 无 | Numdam robots `Crawl-delay: 2` [LIVE N92] | 否 | **P1** |
| `episciences` | Episciences（overlay 期刊平台，如 ÉpiGA） | L1-journal-platform | 数学/CS | 自研 [LIVE N105] | Crossref/DataCite ⚠；OAI ⚠ 未核验 | ⚠ | 钻石 OA ⚠ | 无 | robots 禁止导出格式路径（/json、/crossref、/dc 等）[LIVE N105] | 否 | **P2** |
| `annals_math` | Annals of Mathematics（Princeton） | L1-journal-platform | 数学 | 自研（WordPress + Apache）[LIVE N106] | 委托 Crossref（10.4007；摘要 0.11）[N94] | Crossref | 订阅（往期经 JSTOR ⚠） | 机构订阅 | robots `Disallow: /annals`，即内容路径被禁 [LIVE N106] | 否 | **仅元数据** |
| `intl_press` | International Press（Acta Math.、J. Differential Geom. 等） | L1-publisher | 数学 | Cloudflare（intlpress.com 301）[LIVE] | 委托 Crossref（摘要 0.00–0.03）[N94] | Crossref | Acta Math. 期刊级 OA（OpenAlex，不在 DOAJ）[N95]；其余订阅 | 机构订阅 | robots 未取到（301） | 否 | **P2** |
| `geoscienceworld` | GeoScienceWorld（GSA、SEG 等地学刊） | L1-journal-platform | 地学 | Silverchair（robots 模板）+ CF [LIVE N103] | Crossref ⚠ 未测 | Crossref | 订阅 | 机构订阅 | robots 为 Silverchair 模板 [LIVE N103] | 否 | **P2（地学简述）** |
| `sciengine` | SciEngine（中国科学、科学通报等） | L1-journal-platform | 综合 | 自研（openresty）[LIVE N104] | Crossref ⚠ 未测 | Crossref | 订阅/OA 混合 ⚠ | ⚠ | robots 具名禁止 ClaudeBot、anthropic-ai、GPTBot 等 [LIVE N104] | 否 | **P2（仅元数据）** |
| `wulixb` | 物理学报（中国物理学会，wulixb.iphy.ac.cn） | L1-journal-platform | 物理（中文） | 自研（nginx）[LIVE N104] | Crossref ⚠ 未测 | ⚠ | ⚠ | ⚠ | robots `Allow: /`（2026-09-19 生成）[LIVE N104] | 否 | **P2** |
| `mdpi`（核验补充） | MDPI（Molecules、Materials、Mathematics 等理科刊） | L1-publisher | 化学/材料/数学/物理 | 自研 + Akamai（www 与 robots.txt 被 Akamai 403，见姊妹文档 [N134]） | 委托 Crossref（member "MDPI AG"；Molecules、Materials、Mathematics 摘要与 licenses 均 1.00，TDM link 0）[N133]；OAI-PMH `oai.mdpi.com`（姊妹文档同日实测可用 [N134]；本次核验 504 后超时 ⚠） | Crossref 增量；OAI `from` | 全 OA（CC BY）[N134] | 无 | 站点层面不可读，零自动化；只走 Crossref 与 OAI [N134] | 否 | **P1（元数据经 Crossref）**：2025 年 Molecules 4,830、Materials 5,709、Mathematics 4,071 个 DOI [N133]，理科体量大，需按刊过滤 |

#### 2.2.2 L1 预印本

| source_id（snake_case） | 名称 | 层级类型 | 学科 | 平台技术栈 | 元数据通道 | 最新论文通道 | 全文通道与门控 | 认证方式 | 限速与 ToS/robots 要点（来源+日期） | v1 是否已支持 | 建议优先级及理由 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `arxiv` | arXiv（math 组、physics 组全部 archive） | L1-preprint | 数学/物理 | 自研（Google Frontend）[LIVE N62] | OAI-PMH `oaipmh.arxiv.org/oai`，**set 支持 `group:archive:category` 三级**，共 183 个 set [LIVE N62][DOC N61]；另有 Query API 与 Kaggle/S3 bulk（v1 [N113]）；DOI 由 DataCite 注册（10.48550 前缀共 3,180,774 个）[LIVE N66] | OAI `from` 增量（datestamp 为最后修改时间，不是首发时间）[DOC N61]；RSS（v1） | 全文 PDF 公开，但多数为非独占分发许可，**不得在自有服务器再分发** [DOC N60] | 无 | 每 3 秒 1 次、单连接、所有机器合计 [DOC N60]；元数据 CC0 [N60]；2026-07-01 起为独立非营利机构 [DOC N64] | **是**（理科只登记了 math.OC） | **P0**：数学与物理的第一来源。v2 升级为分类级 set 收割（§2.3.5） |
| `chemrxiv` | ChemRxiv | L1-preprint | 化学/材料 | Wiley Research Exchange Preprints（Atypon 系），2026-01-21 上线 [DOC N67][LIVE N68] | 委托 Crossref（10.26434，posted-content）。**新 DOI 形如 `10.26434/chemrxiv.15009478/v1`**。2025 年 10,085 个，2026 年至今 9,906 个 [LIVE N70] | Crossref `from-posted-date` / `from-created-date` 增量；站点 `/rss` 被 robots 禁止 [LIVE N68] | 预印本 PDF 公开，许可逐篇 ⚠ | 无（阅读） | 旧 Open Engage API 路径返回 CF 挑战 [LIVE N69]；robots Crawl-delay 1，禁 /action 与 /rss [LIVE N68] | 否 | **P0（元数据经 Crossref）**：化学预印本主源；新平台 API 形态待官方公布 |
| `research_square` | Research Square（含 Springer Nature 的 In Review） | L1-preprint | 多学科 | 自研 + Cloudflare [LIVE N71] | 委托 Crossref（10.21203；2025 年 60,377 个，2026 年至今 71,044 个；`group-title` 为 In Review）[LIVE N70] | Crossref 增量 | 预印本公开 | 无 | robots `*` 为 `Disallow: /api/`，另外 20 多个 AI UA（含 ClaudeBot）全禁 [LIVE N71] | 否 | **P2（元数据经 Crossref）**：体量大、跨学科噪声高，需按学科过滤 |
| `preprints_org` | Preprints.org（MDPI） | L1-preprint | 多学科 | Akamai（robots.txt 返回 403）[LIVE N74] | 委托 Crossref（10.20944；2025 年 31,838 个，2026 年至今 22,159 个；`group-title` 为学科大类）[LIVE N70]；有官方 API 客户端注册页，文档 ⚠ 未核验 [SEC N74] | Crossref 增量 | 预印本公开 | 无 | 无法读取 robots，因此不做站点自动化 | 否 | **P2（元数据经 Crossref）** |
| `ess_open_archive` | ESS Open Archive（AGU/Wiley） | L1-preprint | 地学/空间 | Wiley Research Exchange（Atypon 模板）[LIVE N73]。核验修正：维基百科只说 Authorea 及其合作预印本库于 2026 年迁至 Research Exchange Preprints，"2026-05"指 Authorea 迁移后暂停直接投稿的时间（引 Authorea 通知页，403 未能直读）；ESSOAr 本身的迁移月份 ⚠ 未核验 [SEC N72] | 委托 Crossref（10.22541；Authorea 系 2026 年至今 6,122 个，落地域以 essopenarchive.org 为主）[LIVE N70] | Crossref 增量 | 预印本公开 | 无 | robots Crawl-delay 1，禁 /rss [LIVE N73] | 否 | **P2** |
| `eartharxiv` | EarthArXiv | L1-preprint | 地学 | Janeway（Python）[LIVE N75] | Crossref（10.31223；2026 年至今 1,445 个）[LIVE N70] + Janeway REST（`/api/preprints/`）[LIVE N75] | Crossref 增量 | 预印本公开 | 无 | robots 无禁令 [LIVE] | 否 | **P2** |
| `optica_open` | Optica Open（Optica 的预印本服务） | L1-preprint | 光学 | Figshare 式 URL（preprints.opticaopen.org）；robots 返回 202 空响应，疑似 WAF ⚠ [LIVE N109] | Crossref（`10.1364/opticaopen.*`；2026 年至今 1,225 个 posted-content，含版本 DOI）[LIVE N70] | Crossref 增量 | 预印本公开 | 无 | ⚠ | 否 | **P2** |
| `chinaxiv` | ChinaXiv（中国科学院科技论文预发布平台） | L1-preprint | 多学科（中文） | nginx；2026-09-26 返回"系统正在维护中"[LIVE N104] | ⚠ | ⚠ | ⚠ | ⚠ | ⚠ | 否 | **待复核（P2）** |

#### 2.2.3 L2 学科数据库、仓库与聚合

| source_id（snake_case） | 名称 | 层级类型 | 学科 | 平台技术栈 | 元数据通道 | 最新论文通道 | 全文通道与门控 | 认证方式 | 限速与 ToS/robots 要点（来源+日期） | v1 是否已支持 | 建议优先级及理由 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `zbmath_open` | zbMATH Open（FIZ Karlsruhe） | L2-aggregator | 数学 | 自研（REST 服务为 uvicorn）[LIVE] | REST API `api.zbmath.org/v1`（文档、作者、期刊、MSC）[LIVE N78]；OAI-PMH `oai.zbmath.org/v1/`（earliestDatestamp 1755，秒级粒度）[LIVE N77]；RDF 知识图谱全量 dump（Zenodo）[N79] | OAI `from` 增量 | 无全文（DOI 或外链）；部分评论因许可冲突不提供 [LIVE N78] | 无 | 数据 CC BY-SA 4.0，须保留版权标注；要求"reasonable rate"，否则可能被限流或封禁 [DOC N76]；zbmath.org 网页有 CF 挑战 [LIVE] | 否 | **P0（数学）**：MSC 分类、评论和作者消歧，是数学检索与推荐的结构化主干 |
| `mathscinet` | MathSciNet（AMS） | L2-aggregator | 数学 | 自研 + Cloudflare [LIVE N49] | 无开放 API（订阅数据库） | — | — | 机构订阅 | robots `*` 为 `Disallow: /`（只放行 MRAuthorID 与 publications-search），Crawl-delay 10 [LIVE N49] | 否 | **排除自动化**：只提供"在 MathSciNet 中打开"的外链 |
| `inspire_hep` | INSPIRE-HEP | L2-aggregator | 高能物理 | 自研（开源 inspirehep/inspirehep，MIT）[N111] | 官方 REST API：literature、authors、conferences、journals 等 9 类记录；`size` ≤1000；单查询最多 10,000 条 [DOC N80] | `sort=mostrecent` 加查询 [LIVE N81] | 无全文（链接到 arXiv 或 DOI） | 无 | 每 IP 每 5 秒 15 次，超限返回 429 [DOC N80]；元数据多数 CC0，部分字段受限 [N80]；robots 只禁账户、提交等路径 [LIVE N82] | 否 | **P0（物理）**：HEP 检索、引用和 arXiv↔DOI 映射的主干 |
| `nasa_ads_scix` | NASA ADS / SciX | L2-aggregator | 天文/行星/日球/地学 | 自研（AWS；robots 返回 202 空响应）[LIVE] | 官方 API `api.adsabs.harvard.edu/v1`（search、export、metrics、libraries）[DOC N83] | 查询 API | 链接到 OA、arXiv 或出版商 | 用户 token（Bearer）[N83] | 每个端点单独限速，README 示例为每日 5,000 次，UTC 午夜重置；可申请提升 [DOC N83][SEC N84]。2026 年为 ADS→SciX 过渡年 [DOC N85]；官方站点只说"今年秋季"切换，并确认账户、设置、通知与 library 不变、旧链接自动重定向 [N123]；"2026-11-16 完成"仍只见搜索摘要 ⚠ [SEC N86] | 否 | **P1**：天文检索主干；token 必须由每个用户自己持有 |
| `scoap3_repo` | SCOAP3 Repository | L2-repository | 高能物理 | 自研（新版 GitHub SCOAP3/scoap3；旧版 scoap3-next 已归档）[N111] | 官方 API `/api/records/`，共 87,667 条，含摘要以及 PDF/XML 文件链接 [LIVE N91] | API 分页（增量参数 ⚠ 未核验） | OA 全文（PDF、PDF/A、XML，CC BY；元数据 CC0）[DOC N90] | 无 | robots.txt 为 404，无约束 [LIVE] | 否 | **P1**：HEP 期刊 OA 全文的合规中转站，可进入共享缓存 |
| `pubchem` | PubChem（NCBI） | L2-aggregator | 化学（化合物） | 自研（NCBI） | PUG-REST（化合物 → PubMed/专利 xref）[LIVE N87] | 不适用 | 不适用（不是论文源） | 无 | 响应头 `X-Throttling-Control` 动态告警 [LIVE N87]；robots `*` 组 `Disallow: /rest/pug/`，与其文档化 API 用途冲突 [LIVE N88]；数值限额：PubChem 团队论文（2019）给出每秒 ≤5 次、每分钟 ≤400 次、每分钟运行时间 ≤300 s，超载时动态收紧 [N124]；现行文档页为 JS 渲染，未能直读确认现值 ⚠ [N89] | 否 | **仅作关联（P2）**：阿司匹林 CID 2244 关联 26,452 个 PMID [LIVE N87]，偏生物医学，不作为化学论文的发现主源 |
| `osti_gov`（核验补充） | OSTI.GOV（美国能源部 DOE 科技信息办公室） | L2-repository | 物理/化学/材料/能源 | 自研（Apache）[N127] | 官方 REST API `https://www.osti.gov/api/v1/records`，参数含 `q`、`doi`、`publication_date_start/end`、`entry_date_start/end`、`has_fulltext`、`rows`、`page`；JSON/XML/BibTeX [N127] | `entry_date_start` 增量（实际语义与计数口径 ⚠ 待实现前复测） | 收录 DOE 资助成果：期刊论文与接受稿、技术报告、数据集、软件等，自述 400 多万条记录 [N127]；记录带 `links[rel=fulltext]`；各篇许可 ⚠ 未核验 | 无（文档未列认证） | 文档未写数值限额；分页用 `Link` 头与 `X-Total-Count` [N127]；robots `*` 只禁 `/search/`、`/account` 等页面路径，未禁 `/api/`（Last-Modified 2024-12-05）[N127] | 否 | **P2**：DOE 资助的物理、化学、材料成果与接受稿；v2 可作为"OA 全文定位"的补充源 |
| `eudml`（核验补充） | EuDML（European Digital Mathematics Library） | L2-aggregator | 数学（回溯库） | ⚠ | OAI-PMH `https://eudml.org/oai/OAIHandler`（EuDML 2.0 / oai_dc / ESE）[SEC N129] | — | 链接到各成员库 | 无 | 核验时 robots.txt 与 Identify 均返回 nginx 403；图书馆知识库称集合长期未更新、部分收割失败 [SEC N129] | 否 | **不优先**：数学回溯内容已由 Numdam、zbMATH 覆盖 |

> 核验补充：HAL（法国国家 OA 仓储，数学、物理自存档比例高）已由聚合源主题 `aggregators-repositories.md` §2.2.18 覆盖（API v3 与 OAI，robots 与 API 冲突待 ADR），本文不重复登记。

#### 2.2.4 L1 会议平台（理科以期刊为主，会议平台是少数例外）

| source_id（snake_case） | 名称 | 层级类型 | 学科 | 平台技术栈 | 元数据通道 | 最新论文通道 | 全文通道与门控 | 认证方式 | 限速与 ToS/robots 要点（来源+日期） | v1 是否已支持 | 建议优先级及理由 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `pos_sissa` | Proceedings of Science（SISSA） | L1-conference-platform | 高能/天体物理 | 自研（Apache）[LIVE N100] | Crossref（10.22323；2025 年 2,852 条）[LIVE N110]；INSPIRE 有其期刊记录 [LIVE] | Crossref / INSPIRE | OA（许可逐卷 ⚠） | 无 | robots `Crawl-delay: 5` [LIVE N100] | 否 | **P2** |
| `spie_dl` | SPIE Digital Library（Proceedings of SPIE 等） | L1-conference-platform | 光学/光子学 | Imperva Incapsula，连 robots.txt 都返回挑战页 [LIVE N101] | 委托 Crossref（10.1117；2025 年 proceedings-article 27,794 条）[LIVE N110] | Crossref 增量 | 订阅或单篇购买 ⚠ | 机构订阅 | 无法读取 robots，因此视为禁止自动化 | 否 | **仅元数据**：会议量很大，但站点不可自动化 |
| （由 `iop` 承载）J. Phys.: Conf. Ser. | IOP | L1-conference-platform | 物理 | 同 `iop` | Crossref（2025 年 10,049 个 DOI；摘要 1.00）[N94] | Crossref | OA ⚠ 本轮未核验 | 无 | 同 `iop` | 部分 | 随 `iop` 定级 |
| （由 `aip` 承载）AIP Conf. Proc. | AIP | L1-conference-platform | 物理 | 同 `aip` | Crossref（10.1063 前缀下 2025 年 proceedings-article 13,239 条）[LIVE N110] | Crossref | 订阅或 OA 混合 ⚠ | 机构订阅 | 同 `aip` | 部分 | 随 `aip` 定级 |
| （由 `edp_sciences` 承载）EPJ Web of Conferences | EDP | L1-conference-platform | 物理 | 同 EDP | Crossref（2025 年 2,008 个 DOI；licenses 1.00）[N94] | Crossref | OA ⚠ 许可逐卷 | 无 | 同 EDP | 部分 | 随 EDP 定级 |
| （由 `ems_press` 承载）ICM Proceedings、Oberwolfach Reports | EMS Press | L1-conference-platform | 数学 | 同 EMS | Crossref（ICM 2022 为 edited-book DOI `10.4171/icm2022-N`；Oberwolfach Reports 2025 年 57 个）[LIVE N110][N94] | Crossref | ICM 2022 为 OA ⚠ | 无 | 同 EMS | 否 | 随 EMS 定级 |

#### 2.2.5 排除或不做自动化

| source_id（snake_case） | 名称 | 层级类型 | 处理 | 理由 |
|---|---|---|---|---|
| `sci_hub`、`libgen`、`annas_archive` | 盗版源 | — | **排除** | 项目红线（AGENTS.md，v1 需求 §非目标） |
| `google_scholar` | Google Scholar | L2-aggregator | **排除自动化** | 延续 v1 结论（需求 §5；v1 勘察 [N113]） |
| `mathscinet` | MathSciNet | L2-aggregator | **排除自动化**，只做外链 | robots `Disallow: /` [N49]；属订阅数据库 |
| `acs`、`ams`、`cambridge_core`、`preprints_org`、`spie_dl` 的站点层面 | 见上文 | — | 站点零自动化，元数据只经 Crossref | 连 robots.txt 都被 WAF 拦截 [N19][N48][N108][N74][N101] |
| `cas_scifinder`（核验补充） | CAS SciFinder（ACS 旗下化学文献与物质数据库） | L2-aggregator | **排除自动化**，只做外链 | 学术版条款（Version 10/10/2023）禁止用脚本批量抽取或汇编数据、禁止自动化登录与原本手工的流程、禁止用于机器学习等 AI 目的、禁止再分发；每个 Named User 同时存储不超过 5,000 条记录 [N128]。Reaxys 等同类订阅库的条款 ⚠ 本轮未核验 |

### 2.3 分源详述：三通道、门控与 v2 对接建议

#### 2.3.1 物理

**APS（Physical Review）**

- **元数据**：
  - Crossref 可完整枚举。
  - ISSN 发生过迁移（核验：PRB 在 2016 年切换，2015 年旧 ISSN 5,001 条、新 ISSN 0 条，2016 年新 ISSN 5,486 条、旧 ISSN 0 条 [N138]；其他 APS 刊的切换年份 ⚠ 未逐刊核验）。以 PRB 为例，2010-06 窗口按旧 ISSN 1098-0121 可查到 531 条、按新 ISSN 2469-9950 为 0 条；2024-06 窗口则是新 ISSN 410 条、旧 ISSN 0 条 [LIVE N114]。PRD 的 Crossref 刊记录仍挂着旧 ISSN 1550-7998/1089-4918 [N94]。因此 VenueSpec 必须登记全部别名并合并查询。
  - 新发 DOI 已改为不透明后缀，如 `10.1103/fxpf-vzxx`，落地页为 `link.aps.org/doi/…`；老 DOI 仍是 `10.1103/physrevb.109.214425` 的形式 [LIVE N94][N114]。解析器不应依赖 `PhysRev*` 模式。
  - Crossref 摘要覆盖很低（PRL 0.29、PRB 0.11、RMP 0.00）；OA 刊较高（PRX 0.92、PRR 0.95）[N94]。
- **Harvest API** [N1][N2][LIVE N3]：
  - 端点：`GET https://harvest.aps.org/v2/journals/articles?from=&until=&date=(modified|published)&journals=&set=openaccess&per_page≤100`；单篇为 `/v2/journals/articles/{doi}`。
  - 分页：`Link` 头的 `rel=next` / `rel=last`。
  - 格式：APS Article JSON、BagIt zip、PDF、XML。
  - 认证：OA 集免认证（实测 2026-09-20 至 09-21 修改的 OA 记录共 31 页 × 2 条）；全量需 JWT、IP 或 CHORUS token。
  - JSON 字段含 `abstract`、`authors`、`affiliations`、`classificationSchemes`、`identifiers.arxiv`、`rights.licenses`（如 CC BY 4.0 + SCOAP3）。
- **最新论文**：
  - RSS `http://feeds.aps.org/rss/recent/prl.xml`：RDF/RSS 1.0，`syn:updatePeriod=hourly`，版权"Personal use only, all commercial or other reuse prohibited"；feeds.aps.org 没有 robots.txt [LIVE N7]。
- **合规**：
  - ToS 禁止未经书面许可的系统化下载（含目次与摘要），并禁止 robots 与网络加速器 [N4]（核验：条款页署 2017-12，未单列 TDM 条款）。
  - APS Data Sets（引用对与元数据，45 万多篇，自 1893 年起）须填表申请，仅限申请人及合作者用于所述研究 [N5]，**不适合**作为多用户产品的数据源。
  - 2025-12-03 发布 APS Open Science（CC BY 4.0，2026-02 下旬开始投稿）[N8]。
- **v2 建议**：
  - 新建 `aps_harvest` adapter，只对 OA 集自动化：拉取元数据、摘要、PhySH 与 arXiv 映射，CC BY 全文进入共享缓存。
  - 非 OA 论文：用 Crossref 元数据，摘要取 arXiv 版本（Harvest 与 INSPIRE 都给出 arXiv 号），全文只做用户交互式单篇。
  - Harvest 全量授权若由用户或机构自行取得，按"每用户凭证"接入，不共享。
  - RSS 只作为"新鲜度信号"，不入库展示摘要（版权为"Personal use only"）。

**IOP Publishing**

- **元数据**：Crossref 质量最佳。摘要 0.98–1.00，TDM link 1.00，licenses 1.00（NJP、RoPP、CQG、CPL、JCAP、JPCS；AAS 的 ApJ 同样如此）[N94]。
- **robots**：`user-agent: *` → `Disallow: /`。具名搜索引擎放行；约 40 个 AI UA（含 ClaudeBot、anthropic-ai）同样 `Disallow: /` [LIVE N10]。
- **政策（2026-07 更新）** [N9]：
  - 订阅内容仅允许非商业 TDM。
  - 大批量须邮件 contentsupport@ioppublishing.org 申请，经 SFTP 交付；全文 XML/PDF 可能收取象征性费用，元数据 XML 免费。
  - 订阅不含经 API 获取内容的权利，需另签书面协议。核验补充：2026-07 版把 API、机器可读 feed、MCP server/connector、自动化软件 agent 等所有机器对机器访问都列入"需另签协议并可能另收费"。
  - 平台会屏蔽系统化下载。
- **防护**：`/.well-known/tdmrep.json` 路径 302 到 Radware（ShieldSquare）挑战脚本 [LIVE N12]。
- **v2 建议**：
  - 不建站点 adapter。
  - 元数据和摘要全部走 Crossref。
  - OA 全文走 SCOAP3（HEP 刊，SCOAP3 repo 样本即为 IOP 的 Chinese Physics C）[LIVE N91]、arXiv 或 Unpaywall。
  - 订阅全文只提供"在浏览器中打开 DOI"。

**AIP Publishing**

- robots 为 Silverchair 模板（`/Shibboleth.sso/`、`/cassette.axd`、`/data/sitemap/Site_*`）[LIVE N13]。
- Crossref 摘要 0.98–0.99；licenses 与 TDM link 很低（licenses 0.07–0.19，TDM link 0.04–0.08）[N94]。
- JAP 与 Physics of Plasmas 在 2025 年经 S2O 全 OA，任何 CC 许可均为作者自选 [LIVE N14]。核验修正：两刊 S2O 覆盖 2024、2025 两年；AIP 2025-10-29 宣布试点在 2025 年底结束，2026 年起转入 Author Select / AIP Fusion / Read and Publish，新卷不再按 S2O 整刊开放 [N118]。
- TDM 个案处理，联系 rights@aip.org [SEC N15]。
- **v2 建议**：
  - 元数据走 Crossref。
  - S2O 年份的论文按单篇许可判定是否可进共享缓存。

**Optica**

- robots 具名禁止 ClaudeBot、Claude-Web、anthropic-ai、GPTBot、PerplexityBot 等 30 多个 UA；`*` 只禁 viewmedia、getImage、user、openathens 等路径 [LIVE N16]。
- 数据与媒体条款保留包括 AI 训练在内的 TDM 权利；OA 协议文章允许非商业 TDM [SEC N17]。
- Crossref 摘要 0.98 [N94]。Optica 与 Optics Express 在 DOAJ [N95]。
- 预印本服务 Optica Open 的 DOI 为 `10.1364/opticaopen.{id}[.vN]`，落地在 `preprints.opticaopen.org`（Figshare 式路径），2026 年至今共 1,225 条 [LIVE N70]；`opticaopen.org` 根域 302 到登录页 [LIVE N109]。

**天文与 HEP 的 OA 生态**

- ApJ（AAS，IOP 出版）、MNRAS（OUP）、A&A（EDP）在 OpenAlex 中均为期刊级 `is_oa=true` 且在 DOAJ [N95]。
- JHEP、PLB、NPB、EPJC 为 `is_oa=true`、APC=0（SCOAP3 资助的特征）[N95]。核验：SCOAP3 2025–2027 期刊表共 11 刊，其中 EPJC、JHEP、NPB、PLB 为 100% 覆盖；其余 7 刊（PRL 13%、PRD 56%、PRC 9%、PTEP 51%、Chinese Physics C 44%、Acta Phys. Pol. B 36%、AHEP 68%）只资助投到 arXiv HEP 分类的文章，百分比为 2022–2023 年 HEP 文章占比 [N117]。因此 PRL/PRD 的 CC BY 判定必须逐篇读许可，不能按刊判定。
- **v2 建议**：天文与 HEP 的 OA 全文以 SCOAP3 repo 与出版商 OA 为主。

**SCOAP3 Repository**

- API：`https://repo.scoap3.org/api/records/?page_size=N` 返回 `count`（87,667；核验时为 87,669，持续增长）、`next` 以及 `hits.hits[].metadata`（含摘要、`_files` 中位于 CERN S3 的 PDF/XML）[LIVE N91]。
- 官方说明：CC BY 全文，元数据 CC0，2014 年 2 月上线 [DOC N90]。旧代码库 scoap3-next 已归档，新库 SCOAP3/scoap3 活跃（MIT，2026-09-01 有推送）[N111]。
- **v2 建议**：做 `scoap3` adapter，作为 HEP 的 OA 全文源，可进入共享缓存。

**INSPIRE-HEP**

- 基址 `https://inspirehep.net/api/`，共 9 类记录。
- 查询：`q` 使用 INSPIRE 语法，`sort=mostrecent|mostcited`，`size≤1000`，单查询上限 10,000 条。
- 输出格式：JSON、BibTeX、LaTeX（EU/US）。
- 限速：每 IP 每 5 秒 15 次，超限 429，被拒请求也计入配额 [DOC N80]。
- 实测 `q=t higgs` 共 24,879 条，最新记录创建于 2026-09-25，带 arXiv 分类 [LIVE N81]。
- robots 只禁 `/api/accounts`、`/api/submissions` 等 [LIVE N82]。
- **v2 建议**：
  - 作为 HEP 的"查询与引用层"。
  - arXiv↔DOI↔会议（conferences 记录）映射，用于身份图（v1 D-007）。
  - 限速器设为每 5 秒 15 次，全局共享。

**NASA ADS / SciX**

- API 基址 `https://api.adsabs.harvard.edu/v1/`，Bearer token。
- 响应头 `X-RateLimit-Limit/Remaining/Reset` 在 UTC 午夜重置。
- 每个端点单独限速，README 以 search 为例给出每日 5,000 次 [DOC N83]，可发邮件申请提升 [SEC N84]。
- arXiv:2609.18091（2026-09-16）确认 ADS 正在过渡为 SciX，并承诺维持天文服务 [DOC N85]。核验：官方站点源码（2026 What's New）只写"今年秋季"切换，过渡页确认可用 ADS 凭证登录 SciX，账户、设置、邮件通知与 library 不变，旧链接自动重定向 [N123]。"2026-11-16 完成"与"API 不变"仍只见搜索摘要 [SEC N86] ⚠。
- **v2 建议**：
  - token 由用户自行持有。
  - SciX 切换后须重测端点。

#### 2.3.2 化学

**ACS Publications**

- **站点零可读**：robots.txt 本身返回 Cloudflare 403（"Request forbidden by administrative rules"）[LIVE N19]；WebFetch 读取 terms 页也是 403。
- **TDM**：官方"Text & Data Mining"方案页将 TDM 定位为付费方案，费用取决于数据范围、时长、频率和交付方式，按项目交付 JATS/BITS XML [DOC N18]。二手来源记为"不允许"（2023-03）[SEC N15]。
- **Crossref**：摘要 0.07–0.15，14 刊都极低；TDM link 0.82–0.98 [N94]。可以拿到"全文 link"，但访问仍须有权限。
- **v2 建议**：
  - 元数据只走 Crossref。
  - 摘要走"ChemRxiv 版本 → OpenAlex → 无"降级链。
  - 全文只做用户交互式单篇。
  - 不建站点 adapter。

**RSC**

- Silverchair 于 2026-02-26 宣布承接 RSC 50 多种期刊（书籍平台自 2023 年起已在 Silverchair 上），尚未公布上线日期 [DOC N21]。
- 2026-09-26 的 robots 已是 Silverchair 模板（含 `/specificToClient1/`、`/data/sitemap/sitemap.xml`）[LIVE N23]；首页遇 CF 挑战 [LIVE]。
- 一手 TDM 页无法直读，二手来源：保留 DSM 第 4 条 TDM 权利；须提前申请，以 XML 整库交付 [SEC N20][N15]。
- OA 路线已从"2028 年全 OA"转向区域化模式 [SEC N24]。
- Crossref 摘要 0.77–0.93，TDM link 0 [N94]。
- **v2 建议**：元数据走 Crossref；等迁移完成后重勘 PDF 路径；Chemical Science 等 OA 刊的全文可进共享缓存。

**ChemRxiv**

- **平台**：ACS 的迁移 FAQ 称 2026-01-14 停止收稿、2026-01-21 在 Wiley Research Exchange Preprints 上线；3.6 万多篇存量迁移；旧 DOI 继续解析；将向 Crossref 重新提交登记 [DOC N67]。
- **实测** [LIVE]：
  - robots 已是 Atypon 模板，禁止 `/action`、`/rss`、`/doc`、`/lw`，Crawl-delay 1 [N68]。
  - 旧 `engage/chemrxiv/public-api/v1/items` 路径返回 CF 挑战 [N69]。
  - Crossref 中新 DOI 为 `10.26434/chemrxiv.{8位}/v{n}`，落地为 `chemrxiv.org/doi/full/…` [N70]。
  - 核验补充：Crossref 中 ChemRxiv 记录带摘要。2026-06-01 至 09-26 的 posted-content 有 4,603/4,678 条带摘要，2025 年 10,085 条全部带摘要 [N137]。
- **开源工具**：paperscraper（542★，MIT，2026-09-23 有推送）支持 ChemRxiv [N111]。核验：它在 2026-01-25（PR #99）遇到 Cloudflare 后先改走 Cambridge 端点，2026-02-24（PR #103）加入"OpenEngage API 返回 403 时回退到 Crossref 前缀 `10.26434`"的实现 [N125]。该 PR 的代码注释称 Crossref 不含 ChemRxiv 摘要，与上条实测不符，应以实测为准。
- **v2 建议**：
  - 以 Crossref prefix `10.26434` + `type:posted-content` 做增量，同一 id 的版本号用 `/vN` 解析。
  - 不依赖旧 API；待 Wiley 公布新 API 后再评估。

**PubChem**

- PUG-REST 可按化合物反查 PubMed/专利 xref。实测阿司匹林（CID 2244）有 26,452 个 PMID；响应带 `X-Throttling-Control`（请求数、请求时间、服务状态三档颜色）[LIVE N87]。
- robots `*` 组禁止 `/rest/pug/` [LIVE N88]，与"官方文档化 API"定位冲突（§4-1）。
- 数值限额在文档页（JS 渲染）中未能取到 ⚠ [N89]。核验补充：PubChem 团队 2019 年论文给出每秒 ≤5 次、每分钟 ≤400 次、每分钟运行时间 ≤300 s，超载时动态收紧，并要求按响应头的流量状态调节速度 [N124]；现值须在实现前复核。
- **v2 建议**：只作为"化合物 → 文献"的关联增强，并延后到 robots 冲突裁决之后。

#### 2.3.3 数学

**AMS 与 MathSciNet**

- `www.ams.org` 与 `pubs.ams.org` 的 robots.txt 都是 CF 挑战 [LIVE N48]，无法判断其机器访问政策，因此零自动化。
- 二手来源（搜索摘要引自 ams.org 订阅页）：AMS 期刊超过 5 年的全部往期免费，订阅覆盖最近 5 年 [SEC N47]。核验：ams.org 订阅页与 JAMS 主页的搜索摘要口径一致，但页面对 WebFetch 返回 403，仍未直读。另外 OpenAlex 把 JAMS 2020 年卷（已超 5 年）标为 closed 15 篇、green 15 篇，没有 bronze [N135]，说明 OpenAlex/Unpaywall 不能可靠识别这道滑动墙。
- MathSciNet robots：`*` 为 `Disallow: /`，只放行 `/mathscinet/MRAuthorID` 与 `/mathscinet/publications-search`，Crawl-delay 10 [LIVE N49]。
- **v2 建议**：
  - AMS 元数据走 Crossref（摘要 0.70–0.87）。
  - "5 年墙外"的免费 PDF 只做用户交互式获取。经 Unpaywall 发现不可靠（见上条核验），需要按"出版年 + 5 年"规则自行判定。
  - MathSciNet 只提供外链（MR 号可由用户手动补录）。

**zbMATH Open**

- **REST**：`https://api.zbmath.org/v1/document/_search?search_string=…&page=&results_per_page=`，返回 JSON，含 `msc`、`links`（DOI）、`source`、`editorial_contributions`。
  - 实测：部分评论文本显示"unavailable due to conflicting licenses" [LIVE N78]。
- **OAI**：`https://oai.zbmath.org/v1/`，earliestDatestamp 1755，granularity 到秒 [LIVE N77]。
- **条款**：CC BY-SA 4.0；须保留版权标注；"reasonable rate"，否则可能被限流或封禁；2021-06 版 [DOC N76]（核验：原地址现 307 跳转到 `api.zbmath.org/v1/static/terms-and-conditions.html`）。
- **知识图谱**：zbMATH Open KG 统计截至 2026-07，基于 2026-01 的 API dump [N79]：
  - 1.68 亿多个三元组、400 万多篇出版物。
  - 300 万多条评论、6.7K+ 个 MSC 类、3 万多条软件记录。
  - RDF dump 在 Zenodo；配套论文为 arXiv:2609.00969。
- **相关开源**：MaRDI4NFDI/python-zbMathRest2Oai（GPL-3.0）[N111]。
- **v2 建议**：
  - 作为数学的 L2 主干（P0）：MSC 兴趣标签、作者消歧、DOI↔zbMATH id 映射。
  - 注意 **CC BY-SA 的相同方式共享义务**：派生数据若对外发布须同许可（⚠ 需法务评估）。
  - 核验补充：MSC2020 分类方案本身由 MR 与 zbMATH 以 **CC BY-NC-SA 4.0** 联合发布 [N120]。把 MSC 码表用作 v2 标签空间时，还要满足非商业条件。

**SIAM**

- robots（Atypon）明确 Allow `/action/showFeed`，Crawl-delay 1，只具名禁止 GPTBot [LIVE N46]。
- Crossref 摘要 0.76–1.00 [N94]。二手来源称 TDM 不被许可（2023）[SEC N15]。
- v1 已知 SODA 为 book 结构 [N113]。
- **v2 建议**：元数据走 Crossref；eTOC 可作为新鲜度补充；全文走用户单篇。

**EMS Press**

- 2026-02-12 宣布连续第三年全 OA：22 种 S2O 刊，2026 年卷为 CC BY 4.0 [DOC N50]。
- S2O 按年生效，往期仍在订阅墙后 [DOC N52]。
- 2026-03-30 宣布 Launch to Open：FoCM 与 Archiv der Math. 自 2027-01-01 起按 L2O 出版 [DOC N51]（二者此前的出版方与迁移细节 ⚠ 未核验）。
- robots 全放行 [LIVE N53]。Crossref 摘要 1.00（JEMS、CMH、Oberwolfach Reports）[N94]。
- **v2 建议**：做轻量 adapter，或直接用 Crossref + 按单篇许可判定全文是否共享（2024–2026 年卷可共享）。

**Project Euclid**

- Duke University Press 自 2022 年起独立运营；托管 35 家以上合作出版方的 100 多种出版物；超过 80% 的期刊文章开放 [DOC N54]。
- 支持 IP 与 Shibboleth（eduGAIN）认证，提供 KBART 与 COUNTER 5 [DOC N55]。
- robots `Crawl-delay: 10` [LIVE N56]。
- Crossref 摘要很低（Duke Math. J. 0.09、IMS 0.13–0.14）[N94]。
- **v2 建议**：元数据走 Crossref，摘要走 arXiv 或 zbMATH；OAI 端点须重新核验。

**MSP**

- robots 只有各刊 sitemap [LIVE N57]。
- Crossref 摘要 0.00（G&T、ANT、APDE）[N94]。
- **v2 建议**：摘要必须由 arXiv 或 zbMATH 补齐；该站点也可以用 sitemap 做低频"新刊"探测（robots 无禁令），但默认仍以 Crossref 为主。

**Centre Mersenne 与 Numdam**

- Crossref 实测：Publ. Math. IHÉS 的最新 5 个 DOI 都是 `10.5802/pmihes.25–30`（2026-04 至 09），落地在 `pmihes.centre-mersenne.org` [LIVE N93]。
- 但 OpenAlex 的 `host_organization_name` 仍为 Springer Nature [N95]，存在滞后。
- Numdam OAI 的 Identify：baseURL `http://www.numdam.org/oai`，earliestDatestamp 2018-10-09 [LIVE N92]；robots `Crawl-delay: 2`。
- **v2 建议**：做"mersenne/numdam" OAI adapter（P1），覆盖法国数学 OA 刊。

**其他数学平台**

- Annals of Mathematics：robots `Disallow: /annals` [LIVE N106]，只做元数据。
- International Press：Acta Math. 在 OpenAlex 为期刊级 OA，J. Differential Geom. 为订阅 [N95]。
- Episciences 与 Discrete Analysis：robots 禁止元数据导出格式路径 [LIVE N105]，应走 Crossref 或 OAI。

#### 2.3.4 综合与大型商业出版商（理科增量）

**Springer Nature（Link）**

- **官方 API**：
  - 支持页列出 Metadata API（近 1,200 万文档）、Meta API（版本化元数据）、OA API（46 万多份文档，含全文）和 Integro（期刊信息）[DOC N29]。
  - 官方 Python 客户端的基址为 `https://api.springernature.com/`，模块包括 meta、metadata、openaccess、tdm [N30]。
  - OA API 免费档每日 500 次、每分钟 100 次；Premium 每日 10,000 次、每分钟 300 次 [DOC N27]。
  - Metadata API 的免费档只说"每月有限请求量"，没有给出数字 [DOC N28]。
  - 关于免费档每次查询 25 条的说法 ⚠ 来自搜索摘要，未核验。
- **TDM**：
  - 订阅机构对其订阅内容做 TDM 不另收费。核验修正：这里的"不另收费"指 TDM 权利（经平台直接下载）；同页写明使用 SN 的 TDM API 要另行付费 [DOC N25]。
  - 直接下载限每秒 1 次；付费 TDM API（带 key）每分钟 150 次 [DOC N25]。
  - TDM 流量的 UA 必须包含 `TextDataMining`，此类流量会从 COUNTER 报告中剔除 [DOC N26]。
  - TDMRep：`link.springer.com` 与 `www.nature.com` 的 `/.well-known/tdmrep.json` 均为 `tdm-reservation: 1`，策略 JSON 规定 `tdm:mine` 须 `obtainConsent` [LIVE N32][N33]。
  - 姊妹文档另记录了 SN API 条款：订阅 TDM 内容只能存于机构内部服务器，不得让第三方访问，不得用多个账号或 key 规避限额 [N112 R39]。核验：已直读一手 API 条款，上述三点均确认；另外网站摘要只授予"个人使用"许可，未经许可不得商用 [N126]。
- **robots**：
  - link.springer.com 对 `*` 为 `Disallow: /`，白名单包括 `/article/`、`/content/`、`/journal*`、`/book*`、`/chapter/`、`/10*`、`/search$` 等 [LIVE N31]。
  - v1 记录的检索 RSS `search.rss?...` [N113] **不在白名单内**，v2 不应使用。
  - 另具名禁止 ClaudeBot、anthropic-ai、GPTBot 等。
  - 本轮 link.springer.com 可以连通（v1 曾记录云 IP 下 TLS reset）[LIVE N31]。
- **v2 建议**：
  - 新建 `springer_nature_api` adapter（P0），包含 Meta 元数据、OA 全文（CC BY，可进共享缓存）、每用户 api_key、按 key 计量。
  - 订阅全文的 TDM API 必须由机构授权（且为付费产品），严格"每用户私有"。
  - 页面层只用于用户交互式打开。

**Nature Portfolio**

- RSS `https://www.nature.com/nphys.rss`（RDF）可用 [LIVE N35]。
- Crossref 摘要很低：Nature 0.12、Nat. Phys. 0.16、Nat. Chem. 0.20、Nat. Mater. 0.10 [N94]。
- **v2 建议**："新鲜度"用 RSS；摘要用 SN Meta API（官方产品页称字段包含 Abstract [DOC N28]），或用 OpenAlex。

**Elsevier / Wiley / OUP**

- 沿用 v1 adapter，本轮只补理科数据：
  - Elsevier 9 刊（Adv. Math.、JFA、PLB、NPB、Chem、CCR、J. Catal.、Acta Mater.、EPSL）Crossref 摘要全为 0.00 [N94]。v2 的卡片需要经 Elsevier API（用户 key）或 OpenAlex 补摘要。
  - Wiley 5 刊（CPAM、Angew、Chem. Eur. J.、Adv. Mater.、AFM）摘要 0.61–0.93 [N94]；Wiley robots 禁 `/rss` [LIVE N107]。
  - OUP 3 刊摘要 0.78–0.98 [N94]。
- Elsevier 官方 TDM 页：研究者可在开发者门户自助注册 API key，用于非商业用途 [DOC N36]。

**Cambridge Core**

- ToU：对可合法访问的内容可做非商业 TDM；下载超过每小时 500 个 PDF 可撤销访问；平台监控下载行为 [DOC N58]（核验：条款页署 2025-03 更新，500 PDF/小时按"个人或集体"合计）。
- robots.txt 本身为 CF 挑战 [LIVE N108]。
- **v2 建议**：v1 planned 的 `cambridge` adapter 限于用户交互式单篇获取，并设置每用户每小时远低于 500 个 PDF 的硬顶。

**Science 与 PNAS**

- 两站都是 Atypon，robots 明确 Allow `/action/showFeed` [LIVE N37][N38]。Science 具名禁 anthropic-ai、GPTBot 等；PNAS 只禁 GPTBot。
- PNAS 6 个月后经 PMC 免费 [SEC N39]。核验：NLM PMC 刊表记 PNAS 为 Release Delay 6 months、Agreement to Deposit 为 All articles、PMC 回溯到 1915 年第 1 卷 [N122]。
- **v2 建议**：新鲜度走 eTOC 或 Crossref；PNAS 6 个月后的 OA 副本经 PMC/Unpaywall 获取。

**Taylor & Francis / De Gruyter Brill / World Scientific**

- 均为"元数据走 Crossref，全文走用户单篇"。
- T&F 与 WSP 的 robots 禁 `/rss` [LIVE N41][N44]。
- De Gruyter 在 robots 中写明 §44b 商业 TDM 保留 [LIVE N42]。
- T&F 的 Mol. Phys. 摘要 0.00 [N94]。

#### 2.3.5 arXiv：理科分类体系与 v1 升级要点

**arXiv OAI-PMH 理科 set 结构**（ListSets 实测共 183 个 setSpec，数量含重复项 [LIVE N62]；核验：重复的是 9 个物理单体 archive，去重后 174 个；OAI 服务在 2025-03 重写并换到新基址，v1 adapter 已使用新域 [N61]）：

| 组（group） | archive | 叶子分类数 | setSpec 形态示例 |
|---|---|---|---|
| `math` | `math` | 32（AC、AG、AP、AT、CA、CO、CT、CV、DG、DS、FA、GM、GN、GR、GT、HO、IT、KT、LO、MG、MP、NA、NT、OA、OC、PR、QA、RA、RT、SG、SP、ST） | `math:math:AG` |
| `physics` | `astro-ph` | 6（CO、EP、GA、HE、IM、SR） | `physics:astro-ph:CO` |
| `physics` | `cond-mat` | 9（dis-nn、mes-hall、mtrl-sci、other、quant-gas、soft、stat-mech、str-el、supr-con） | `physics:cond-mat:mtrl-sci` |
| `physics` | `nlin` | 5（AO、CD、CG、PS、SI） | `physics:nlin:CD` |
| `physics` | `physics` | 22（acc-ph、ao-ph、app-ph、atm-clus、atom-ph、bio-ph、chem-ph、class-ph、comp-ph、data-an、ed-ph、flu-dyn、gen-ph、geo-ph、hist-ph、ins-det、med-ph、optics、plasm-ph、pop-ph、soc-ph、space-ph） | `physics:physics:optics` |
| `physics` | 单体 archive：gr-qc、hep-ex、hep-lat、hep-ph、hep-th、math-ph、nucl-ex、nucl-th、quant-ph | 9 | `physics:hep-th` |

合计：理科叶子分类为数学 32 个加物理 51 个（6+9+5+22+9），共 83 个。化学相关的分类是 `physics.chem-ph` 与 `cond-mat.mtrl-sci`。

**要点。**

1. **分类级 set 可直接收割**。实测 `ListIdentifiers&set=math:math:AG&from=2026-09-23&until=2026-09-24` 返回 181 个标识符 [LIVE N63]。其中包含交叉列出和元数据更新过的老论文（如 0810.0442），原因是 datestamp 为最后修改时间 [DOC N61]。v2 仍需按 `arXivRaw` 的版本历史判定"新论文"与"更新"。
2. **v1 物理 set 推导会失效**。官方文档与 ListSets 都只有带 `physics:` 前缀的形态 [N61][N62]。核验：`set=cond-mat` 返回 `badArgument`（"Set does not exist"）[N132]。
3. **分类别名**，如 math.MP≡math-ph、math.IT≡cs.IT、math.ST≡stat.TH、cs.NA≡math.NA。核验：官方分类表逐条确认，写法为"math.MP is an alias for math-ph""stat.TH is an alias for math.ST"等；同表还有 q-fin.EC≡econ.GN、cs.SY≡eess.SY [N136]。ListSets 同时列出了 `math:math:MP` 与 `physics:math-ph` [N62]。去重键必须是 arXiv id，不能用分类。
4. **量级与治理**：
   - 全站 2026 年 3、5、6 月的投稿量分别为 30,045、31,604、32,040 篇；2026 年 4 月总量超过 300 万篇 [DOC N65]。
   - DataCite 前缀 10.48550 共 3,180,774 个 DOI [LIVE N66]。
   - 自 2026-07-01 起成为独立非营利机构，官方称使命不变，公告未提及 API 或费用变化 [DOC N64]。
5. **ToU**：API 每 3 秒 1 次、单连接、所有机器合计；元数据 CC0；自有服务器不得存储并提供 e-print，除非获得版权人许可或论文采用宽松许可 [DOC N60]。多用户平台只能"链接到 arxiv.org"，或"每用户私有取回"，不可做共享 PDF 镜像（CC BY 论文除外，许可须逐篇读取）。

#### 2.3.6 材料、地学与中文来源（简述）

- **材料**：
  - Nature Materials、Advanced Materials、Advanced Functional Materials、Acta Materialia 的平台分别归 `nature_portfolio`、`wiley_vch`、`elsevier_sd` [N94]。
  - arXiv `cond-mat.mtrl-sci` 与 ChemRxiv 覆盖预印本。
  - 不需要额外的平台 adapter。
- **地学**：
  - GRL（AGU/Wiley）在 OpenAlex 为期刊级 OA [N95]。
  - EPSL（Elsevier）、Nature Geoscience 为订阅。
  - GeoScienceWorld 为 Silverchair [LIVE N103]。
  - 预印本有 ESS Open Archive 与 EarthArXiv。
  - 地学的完整名录建议由后续专题补齐。
- **中文**：
  - SciEngine（中国科学系）robots 具名禁止 ClaudeBot 等 AI UA。
  - 物理学报 robots 全放行。
  - CCS Chemistry 为 Atypon 模板，期刊为全 OA。
  - ChinaXiv 当日在维护 [LIVE N104]。
  - Chinese Physics Letters 由 IOP 出版，Crossref 摘要 0.98 [N94]。
  - 建议作为"中文用户可选包"（P2），元数据优先走 Crossref。

#### 2.3.7 相关开源客户端与数据集（GitHub 实测，2026-09-26 [N111]）

| 仓库 | ★ | 许可 | 最近推送 | 状态与用途 |
|---|---|---|---|---|
| lukasschwab/arxiv.py | 1,548 | MIT | 2026-09-01 | arXiv API 的 Python 封装（Query API） |
| jannisborn/paperscraper | 542 | MIT | 2026-09-23 | 覆盖 PubMed、arXiv、bioRxiv、medRxiv、ChemRxiv；核验：2026-02-24 起 ChemRxiv 在旧 API 403 时回退 Crossref（PR #103）[N125] |
| mcs07/PubChemPy | 515 | MIT | 2025-09-08 | PUG-REST 封装 |
| ElsevierDev/elsapy | 433 | BSD-3-Clause | 2022-11-09 | **已归档**，v2 不应依赖 |
| adsabs/adsabs-dev-api | 202 | 无 | 2025-04-21 | ADS API 说明与示例 |
| andycasey/ads | 191 | MIT | 2026-09-24 | ADS Python 客户端 |
| inspirehep/rest-api-doc | 59 | CC-BY-SA-4.0 | 2025-07-14 | INSPIRE API 文档 |
| WileyLabs/tdm-client | 28 | MIT | 2026-07-02 | Wiley TDM 客户端（v1 已引用） |
| inspirehep/inspirehep | 26 | MIT | 2026-09-24 | INSPIRE 平台源码 |
| physh-org/PhySH | 24 | CC0（LICENSE.md；GitHub API 显示 NOASSERTION） | 2026-03-24 | APS 的 PhySH 分类法，提供 JSON、NT、RDF、TTL |
| springernature/springernature_api_client | 8 | MIT | 2026-08-10 | SN 官方 Python 客户端 |
| MaRDI4NFDI/python-zbMathRest2Oai | 4 | GPL-3.0 | 2026-03-24 | zbMATH REST 到 OAI 的数据管道 |
| zbMATHOpen/zbmath-open-kg | 3 | 无 LICENSE 文件；README 声明 KG 内容为 CC BY-SA 4.0 | 2026-09-15 | zbMATH Open RDF 知识图谱 |
| SCOAP3/scoap3 | 3 | MIT | 2026-09-01 | 新版 SCOAP3 仓库（Django）；旧库 scoap3-next 已归档 |
| arXiv/arxiv-oaipmh | 3 | MIT | 2026-08-12 | arXiv 新版 OAI-PMH 服务源码 |

### 2.4 横切实测：Crossref 元数据质量（按出版商聚合）

数据为 Crossref `coverage.*-current`，按出版商取样本刊的最小值和最大值 [N94]。

| Crossref publisher | 样本刊数 | 摘要覆盖 | TDM link（`resource-links`） | licenses | 对 v2 的含义 |
|---|---|---|---|---|---|
| American Chemical Society | 14 | **0.07–0.15** | 0.82–0.98 | 0.82–0.98 | 摘要需另行补齐；全文 link 存在，但仍须有权限 |
| Elsevier | 9 | **0.00** | 1.00 | 1.00 | 同上；Elsevier API（用户 key）或 OpenAlex |
| Springer Nature（Nature 系，登记名 "Springer Science and Business Media LLC"） | 9 | **0.10–0.21**（Nat. Commun. 0.47；LSA 0.97） | 1.00 | 1.00 | SN Meta API 或 OpenAlex |
| American Physical Society | 8 | 0.00–0.95（PRL 0.29、PRB 0.11；OA 刊 ≥0.92） | 0.00–0.29 | 1.00 | APS Harvest（OA）或 arXiv |
| Springer（登记名 "Springer-Verlag"） | 7 | 0.40–0.99 | 1.00 | 1.00 | 部分需补 |
| Royal Society of Chemistry | 7 | 0.77–0.93 | **0.00** | 0.77–0.93 | 基本可用 |
| IOP Publishing / AAS | 6+1 | 0.98–1.00 | 1.00 | 1.00 | **完备** |
| Wiley | 5 | 0.61–0.93 | 0.28–0.56 | 0.80–0.99 | 部分需补 |
| Cambridge University Press | 4 | 0.76–0.99 | 0.00 | 1.00 | 基本可用 |
| American Mathematical Society | 3 | 0.70–0.87 | 0.00 | 0.71–0.87 | 部分需补 |
| EMS Press | 3 | 1.00 | 0.00 | 0.00 | 摘要完备，但无许可元数据，须从站点或 S2O 规则判定 |
| Mathematical Sciences Publishers | 3 | **0.00** | 0.00 | 0.00 | 需 arXiv 或 zbMATH |
| Oxford University Press | 3 | 0.78–0.98 | 0.00 | 0.99–1.00 | 基本可用 |
| American Institute of Physics | 3 | 0.98–0.99 | 0.04–0.08 | **0.07–0.19** | 摘要可用，许可元数据缺失 |
| Institute of Mathematical Statistics / Duke UP / Intl Press / Annals / SMF | 各 1–2 | 0.00–0.14 | 0.00 | 0.00 | 需 arXiv 或 zbMATH |
| De Gruyter | 2 | 0.87–1.00 | 1.00 | 0.12–0.28 | 可用 |
| SIAM | 2 | 0.76–1.00 | 0.00 | 0.00 | 可用 |
| AAAS | 2 | 0.85–0.98 | 0.00 | 0.05–0.10 | 可用，许可元数据缺失 |
| PNAS | 1 | 0.85 | 0.00 | 0.99 | 可用 |
| EDP / Optica / SciPost / Quantum / AGU / Royal Society | 各 1–2 | 0.89–1.00 | 0.00–1.00 | 0.94–1.00 | 可用 |
| World Scientific（附加核验）| 2 | 0.96–0.99 | 0.00 | 0.00 | 可用 |
| Taylor & Francis（Mol. Phys.）| 1 | **0.00** | 0.16 | 0.26 | 需补 |

**数据质量问题（同批实测）。**

- PLMS 的 e-ISSN 被登记为 `1234-5678`。
- MNRAS 的刊级记录把 e-ISSN 登记为 `1365-8711`，而其论文级记录用的是 `1365-2966`（复核时 [LIVE] 取最新 2 篇确认）。
- GRL 的 print 与 electronic ISSN 颠倒。
- NPB、CCR 的 p/e 相同。
- Acta Materialia、PLB、Chem 缺 e-ISSN。
- Crossref publisher 字段与实际平台可能不一致：Am. J. Math. 登记为 "Project MUSE"；IHÉS 在 Crossref 中已改为 "MathDoc/Centre Mersenne"，而 OpenAlex 未更新 [N94][N95]。

### 2.5 横切实测：平台技术栈指纹与防护矩阵

**技术栈指纹（robots 模板法与响应头）。**

| 平台族 | 指纹 | 实测站点 [LIVE] |
|---|---|---|
| Atypon / Literatum | robots 含 `/action`、`/na101/`、`/doi/mlt/`、`Allow: /action/showXml` 等；多数禁 `/rss` | science.org、pnas.org、tandfonline.com、worldscientific.com、epubs.siam.org、onlinelibrary.wiley.com、chemrxiv.org、essopenarchive.org、chinesechemsoc.org |
| Silverchair | robots 含 `/Shibboleth.sso/`、`/cassette.axd`、`/DownloadFile/`、`/data/sitemap/Site_*` | pubs.aip.org、pubs.rsc.org、academic.oup.com、pubs.geoscienceworld.org、royalsocietypublishing.org（核验补充 [N130]；上线见 [N22]） |
| Springer Nature 自研 | 响应头 `server: Oscar Platform` | link.springer.com、www.nature.com |
| IOPscience 自研 | Radware / ShieldSquare 脚本（`__uzdbm_*`） | iopscience.iop.org |
| 其他自研 | ColdFusion（Optica）、CloudFront（De Gruyter Brill）、IIS（Project Euclid）、Joomla（EDP）、Janeway（EarthArXiv）、Django（SciPost）、WordPress（Quantum、Centre Mersenne、Annals） | 见 §2.2 |

**防护与可达性矩阵（本机代理出口，2026-09-26）。**

| 表现 | 站点 |
|---|---|
| Cloudflare 挑战（`cf-mitigated: challenge`） | www.ams.org 与 pubs.ams.org 的 robots、zbmath.org 的 robots、www.cambridge.org 的 robots、pubs.rsc.org 首页、chemrxiv 旧 API、T&F 与 Wiley 的 `tdmrep.json` |
| Cloudflare 403"administrative rules" | pubs.acs.org 的 robots |
| Akamai 403 | preprints.org 的 robots |
| Imperva Incapsula 挑战页 | spiedigitallibrary.org 的 robots |
| Radware 302 挑战 | iopscience 的 `/.well-known/tdmrep.json`；opg.optica.org 的条款页（核验补充 [N131]） |
| 202 空响应（疑似 AWS WAF ⚠） | ui.adsabs.harvard.edu 与 preprints.opticaopen.org 的 robots |
| 维护页 | chinaxiv.org |
| 可正常读取 | 其余 40 多个 robots，以及 APS feeds、nature RSS、zbMATH、INSPIRE、SCOAP3、APS Harvest、arXiv OAI、EarthArXiv API、Numdam OAI |

### 2.6 "最新论文"通道矩阵

| 来源 | 候选 feed 或增量接口 | robots 或条款态度 | v2 结论 |
|---|---|---|---|
| 全部 Crossref 可枚举刊 | `filter=from-created-date:`（或 `from-index-date:`）按 ISSN 增量 | Crossref API 无 robots（v1 [N113]）；自 2025-12-01 按请求类型分档限速（公共池列表查询 1 次/秒、并发 1）[N121] | **默认通道** |
| APS | `feeds.aps.org/rss/recent/{code}.xml`（小时级）；Harvest `from/until` | feeds 无 robots；RSS 版权为"Personal use only" [N7] | 作为新鲜度信号；展示内容取自 Crossref/Harvest |
| Nature Portfolio | `www.nature.com/{code}.rss` | `*` 未禁 `.rss` [N34] | 可用 |
| SIAM / Science / PNAS | `/action/showFeed?...` | robots 明确 Allow [N46][N37][N38] | 可用（低频） |
| Quantum / SciPost | `/feed/`、`/feeds` | 允许 [N99][N98] | 可用 |
| arXiv | OAI `from`（分类级 set）+ RSS | 官方 API [N61] | 主通道 |
| INSPIRE / zbMATH / ADS | `sort=mostrecent` / OAI `from` / 查询 | 官方 API | 可用 |
| IOP | `journal/rss/{issn}` | `*` 为 `Disallow: /` [N10] | **不用** |
| Wiley / T&F / WSP / ChemRxiv / ESSOAr | `/action/showFeed` 或 `/rss` | robots 禁 `/rss` 与 `/action` [N107][N41][N44][N68][N73] | **不用** |
| Springer（Link） | `search.rss` | 不在白名单 [N31] | **不用** |
| ACS / AMS / RSC / Cambridge | eTOC | robots 读不到或有挑战 | **不用** |

### 2.7 会议形态：物理和数学以期刊为主，例外情形

- **物理**：成果以期刊为主，会议论文集集中在少数系列。

  | 系列 | 2025 年量级 | 性质 |
  |---|---|---|
  | J. Phys.: Conf. Ser.（IOP） | 10,049 个 DOI [N94] | OA ⚠ |
  | AIP Conf. Proc. | 13,239 条 proceedings-article（10.1063 前缀）[N110] | — |
  | Proc. SPIE | 27,794 条（10.1117 前缀）[N110] | 光学领域的会议是一等成果 |
  | PoS（SISSA） | 2,852 条（10.22323）[N110] | HEP / 天体物理 |
  | EPJ Web of Conferences | 2,008 个 DOI [N94] | OA ⚠ |

  这些系列的 VenueSpec 建议用 `kind: proceedings_series`，按"卷 = 会议"组织，元数据走 Crossref。INSPIRE 的 conferences 记录可作为 HEP 会议索引 [N80]。APS March Meeting 的 BAPS 摘要在 Crossref 按 ISSN 0003-0503 查询为 404 [N110]，只做外链 ⚠。

- **数学**：
  - ICM 论文集由 EMS Press 出版，2022 届为 edited-book DOI `10.4171/icm2022-N` [LIVE N110]，建议作为 book/volume 级 venue。
  - Oberwolfach Reports（EMS Press，2025 年 57 个 DOI [N94]）是研讨会报告集，不是同行评审论文（性质描述 ⚠ 本轮未核验）。
  - SIAM 会议（如 SODA）为 book 结构（v1 [N113]），属于 CS/应用数学交叉。
- **化学**：会议基本不作为论文载体（学会年会只有摘要）⚠，名录中不单列。

### 2.8 代表性期刊/会议 → 平台映射表

**列说明。**
- ISSN 为 Crossref 刊记录中的 print / electronic [N94]。
- "Crossref 可枚举性"写作"✓ 总 DOI 数 / 2025 年发行 DOI 数 / 摘要覆盖"，均为 2026-09-26 [LIVE] 数据。
- "OA 情况"以 OpenAlex 期刊级 `is_oa` / DOAJ 为准 [N95]，并补充已核验的政策。
- "订阅"指期刊级非 OA，可能含混合 OA 单篇。

#### 2.8.1 数学（30）

| venue | ISSN（p / e） | 出版平台（source_id） | Crossref 可枚举性 | OA 情况 |
|---|---|---|---|---|
| Annals of Mathematics | 0003-486X / 1939-8980 | `annals_math` | ✓ 6,301 / 27 / 0.11 | 订阅 |
| Acta Mathematica | 0001-5962 / 1871-2509 | `intl_press` | ✓ 2,279 / 6 / 0.00 | 期刊级 OA（不在 DOAJ） |
| Inventiones Mathematicae | 0020-9910 / 1432-1297 | `springer_nature_link` | ✓ 4,878 / 88 / 0.50 | 订阅 |
| Journal of the AMS | 0894-0347 / 1088-6834 | `ams` | ✓ 1,383 / 22 / 0.70 | 订阅；5 年后免费 [SEC N47] |
| Publ. Math. IHÉS | 0073-8301 / 1618-1913 | `centre_mersenne_numdam`（**已迁出 Springer**，10.5802）[N93] | ✓ 604 / 9 / 0.96 | ⚠（OpenAlex 仍标 Springer，不可信） |
| Duke Mathematical Journal | 0012-7094 / 1547-7398 | `project_euclid` | ✓ 6,818 / 61 / 0.09 | 订阅 |
| Journal of the EMS | 1435-9855 / 1435-9863 | `ems_press` | ✓ 1,871 / 174 / 1.00 | OA（DOAJ；S2O 2024–26）[N50] |
| Forum of Mathematics, Pi | — / 2050-5086 | `cambridge_core` | ✓ 195 / 25 / 0.99 | OA（DOAJ） |
| Forum of Mathematics, Sigma | 2050-5094 / 2050-5094 | `cambridge_core` | ✓ 1,031 / 200 / 0.98 | OA（DOAJ） |
| Geometric and Functional Analysis | 1016-443X / 1420-8970 | `springer_nature_link`（Birkhäuser） | ✓ 1,440 / 31 / 0.51 | 订阅 |
| Comm. Pure Appl. Math. | 0010-3640 / 1097-0312 | `wiley_vch` | ✓ 4,310 / 63 / 0.61 | 订阅 |
| Advances in Mathematics | 0001-8708 / 1090-2082 | `elsevier_sd` | ✓ 11,365 / 467 / 0.00 | 订阅 |
| Mathematische Annalen | 0025-5831 / 1432-1807 | `springer_nature_link` | ✓ 14,276 / 241 / 0.40 | 订阅 |
| J. reine angew. Math.（Crelle） | 0075-4102 / 1435-5345 | `degruyter_brill` | ✓ 12,133 / 103 / 1.00 | 订阅 |
| Compositio Mathematica | 0010-437X / 1570-5846 | `cambridge_core` | ✓ 2,538 / 109 / 0.76 | 订阅 |
| American Journal of Mathematics | 0002-9327 / 1080-6377 | Project MUSE（JHU Press）⚠ 平台未勘察 | ✓ 6,498 / 39 / 0.98 | 订阅 |
| Transactions of the AMS | 0002-9947 / 1088-6850 | `ams` | ✓ 28,011 / 272 / 0.80 | 订阅；5 年后免费 [SEC] |
| Proceedings of the LMS | 0024-6115 /（Crossref 登记值 `1234-5678`，数据错误） | `wiley_vch`（LMS） | ✓ 8,275 / 76 / 0.75 | 订阅 |
| Geometry & Topology | 1465-3060 / 1364-0380 | `msp` | ✓ 1,777 / 93 / 0.00 | 订阅（S2O ⚠） |
| Algebra & Number Theory | 1937-0652 / 1944-7833 | `msp` | ✓ 1,354 / 77 / 0.00 | 订阅（S2O ⚠） |
| Analysis & PDE | 2157-5045 / 1948-206X | `msp` | ✓ 1,057 / 67 / 0.00 | 订阅（S2O ⚠） |
| Annals of Probability | 0091-1798 / 2168-894X | `project_euclid`（IMS；托管关系 ⚠ 本轮未核验） | ✓ 4,855 / 56 / 0.13 | 订阅 |
| SIAM J. Numer. Anal. | 0036-1429 / 1095-7170 | `siam` | ✓ 6,286 / 98 / 1.00 | 订阅 |
| Mathematics of Computation | 0025-5718 / 1088-6842 | `ams` | ✓ 12,693 / 130 / 0.87 | 订阅；5 年后免费 [SEC] |
| Comm. Math. Phys. | 0010-3616 / 1432-0916 | `springer_nature_link` | ✓ 12,663 / 321 / 0.46 | 订阅 |
| IMRN | 1073-7928 / 1687-0247 | `oup` | ✓ 7,420 / 385 / 0.98 | 订阅 |
| J. Differential Geometry | 0022-040X / 1945-743X | `intl_press`（Project Euclid 亦收录 ⚠） | ✓ 2,750 / 47 / 0.03 | 订阅 |
| J. Functional Analysis | 0022-1236 / 1096-0783 | `elsevier_sd` | ✓ 10,852 / 357 / 0.00 | 订阅 |
| Comment. Math. Helv. | 0010-2571 / 1420-8946 | `ems_press` | ✓ 2,889 / 26 / 1.00 | OA（DOAJ；S2O） |
| Ann. Sci. ENS | 0012-9593 / 1873-2151 | SMF（平台 ⚠ 未勘察） | ✓ 2,668 / 44 / 0.00 | 订阅 |

#### 2.8.2 物理（30）

| venue | ISSN（p / e） | 出版平台（source_id） | Crossref 可枚举性 | OA 情况 |
|---|---|---|---|---|
| Physical Review Letters | 0031-9007 / 1079-7114 | `aps` | ✓ 143,948 / 3,015 / 0.29 | 订阅（单篇 CC BY） |
| Physical Review X | — / 2160-3308 | `aps` | ✓ 3,366 / 311 / 0.92 | OA（DOAJ） |
| Reviews of Modern Physics | 0034-6861 / 1539-0756 | `aps` | ✓ 3,646 / 33 / 0.00 | 订阅 |
| Physical Review B | 查询用 2469-9950；刊记录挂旧 ISSN 1098-0121 / 1550-235X | `aps` | ✓ 228,343 / 5,677 / 0.11；**须合并新旧 ISSN** [N114] | 订阅 |
| Physical Review D | 查询用 2470-0010；刊记录挂 1550-7998 / 1089-4918 | `aps` | ✓ 121,677 / 5,126 / 0.57 | 订阅（SCOAP3 单篇 CC BY [N3]） |
| PRX Quantum | — / 2691-3399 | `aps` | ✓ 1,448 / 277 / 0.94 | OA（DOAJ） |
| Physical Review Research | — / 2643-1564 | `aps` | ✓ 10,578 / 1,628 / 0.95 | OA（DOAJ） |
| Nature Physics | 1745-2473 / 1745-2481 | `nature_portfolio` | ✓ 7,504 / 410 / 0.16 | 订阅 |
| Nature Photonics | 1749-4885 / 1749-4893 | `nature_portfolio` | ✓ 5,348 / 235 / 0.15 | 订阅 |
| Reports on Progress in Physics | 0034-4885 / 1361-6633 | `iop` | ✓ 2,774 / 102 / 0.98 | 订阅 |
| New Journal of Physics | — / 1367-2630 | `iop` | ✓ 14,728 / 397 / 0.99 | OA（DOAJ） |
| Classical and Quantum Gravity | 0264-9381 / 1361-6382 | `iop` | ✓ 16,079 / 448 / 0.99 | 订阅 |
| Chinese Physics Letters | 0256-307X / 1741-3540 | `iop` | ✓ 18,684 / 336 / 0.98 | 订阅 |
| JCAP | 1475-7508 / 1475-7516 | `iop` | ✓ 13,653 / 1,102 / 0.99 | 订阅 |
| JHEP | 1126-6708 / 1029-8479 | `springer_nature_link` | ✓ 47,565 / 2,643 / 0.99 | OA（DOAJ，APC 0，SCOAP3 特征） |
| Physics Letters B | 0370-2693 / — | `elsevier_sd` | ✓ 67,403 / 878 / 0.00 | OA（DOAJ，APC 0） |
| Nuclear Physics B | 0550-3213 / 0550-3213 | `elsevier_sd` | ✓ 31,650 / 456 / 0.00 | OA（DOAJ，APC 0） |
| Eur. Phys. J. C | 1434-6044 / 1434-6052 | `springer_nature_link` | ✓ 24,129 / 1,486 / 0.98 | OA（DOAJ，APC 0） |
| Astrophysical Journal | 0004-637X / 1538-4357 | `iop`（AAS，10.3847） | ✓ 134,332 / 4,155 / 0.99 | OA（DOAJ） |
| MNRAS | 0035-8711 / 1365-2966（论文级记录；刊级记录误登为 1365-8711 [LIVE N94]）| `oup` | ✓ 93,301 / 2,268 / 0.97 | OA（DOAJ） |
| Astronomy & Astrophysics | 0004-6361 / 1432-0746 | `edp_sciences` | ✓ 58,633 / 3,912 / 0.99 | OA（DOAJ） |
| Applied Physics Letters | 0003-6951 / 1077-3118 | `aip` | ✓ 141,141 / 2,787 / 0.99 | 订阅 |
| Physics of Fluids | 1070-6631 / 1089-7666 | `aip` | ✓ 35,939 / 6,192 / 0.99 | 订阅 |
| Journal of Fluid Mechanics | 0022-1120 / 1469-7645 | `cambridge_core` | ✓ 32,731 / 1,346 / 0.97 | 订阅 |
| Optica | — / 2334-2536 | `optica` | ✓ 2,862 / 240 / 0.98 | OA（DOAJ） |
| Optics Express | — / 1094-4087 | `optica` | ✓ 67,749 / 4,032 / 0.98 | OA（DOAJ） |
| Light: Science & Applications | — / 2047-7538 | `nature_portfolio` | ✓ 2,860 / 399 / 0.97 | OA（DOAJ） |
| SciPost Physics | 2542-4653 / 2542-4653 | `scipost` | ✓ 2,517 / 392 / 0.96 | OA（DOAJ） |
| Quantum | — / 2521-327X | `quantum_journal` | ✓ 2,214 / 378 / 1.00 | OA（DOAJ） |
| Int. J. Mod. Phys. A | 0217-751X / 1793-656X | `world_scientific` | ✓ 13,855 / 384 / 0.96 | ⚠ 未查 OpenAlex（期刊级订阅 ⚠） |

#### 2.8.3 化学（30）

| venue | ISSN（p / e） | 出版平台（source_id） | Crossref 可枚举性 | OA 情况 |
|---|---|---|---|---|
| JACS | 0002-7863 / 1520-5126 | `acs` | ✓ 221,071 / 4,832 / 0.10 | 订阅 |
| Chemical Reviews | 0009-2665 / 1520-6890 | `acs` | ✓ 10,703 / 251 / 0.07 | 订阅 |
| Angew. Chem. Int. Ed. | 1433-7851 / 1521-3773 | `wiley_vch` | ✓ 81,883 / 5,814 / 0.92 | 订阅 |
| Nature Chemistry | 1755-4330 / 1755-4349 | `nature_portfolio` | ✓ 5,109 / 332 / 0.20 | 订阅 |
| Chemical Society Reviews | 0306-0012 / 1460-4744 | `rsc` | ✓ 9,324 / 403 / 0.77 | 订阅 |
| Chemical Science | 2041-6520 / 2041-6539 | `rsc` | ✓ 21,106 / 2,311 / 0.91 | OA（DOAJ） |
| Accounts of Chemical Research | 0001-4842 / 1520-4898 | `acs` | ✓ 9,238 / 339 / 0.09 | 订阅 |
| ACS Catalysis | 2155-5435 / 2155-5435 | `acs` | ✓ 17,796 / 1,853 / 0.15 | 订阅 |
| ACS Nano | 1936-0851 / 1936-086X | `acs` | ✓ 29,425 / 3,282 / 0.07 | 订阅 |
| Nano Letters | 1530-6984 / 1530-6992 | `acs` | ✓ 27,693 / 2,343 / 0.10 | 订阅 |
| J. Chem. Phys. | 0021-9606 / 1089-7690 | `aip` | ✓ 150,900 / 2,294 / 0.98 | 订阅 |
| Chem（Cell Press） | 2451-9294 / — | `elsevier_sd` | ✓ 2,920 / 290 / 0.00 | 订阅 |
| Nature Catalysis | — / 2520-1158 | `nature_portfolio` | ✓ 1,610 / 188 / 0.11 | 订阅 |
| Energy & Environ. Sci. | 1754-5692 / 1754-5706 | `rsc` | ✓ 8,287 / 825 / 0.86 | 订阅 |
| J. Mater. Chem. A | 2050-7488 / 2050-7496 | `rsc` | ✓ 38,558 / 3,455 / 0.93 | 订阅 |
| Chemical Communications | 1359-7345 / 1364-548X | `rsc` | ✓ 78,105 / 3,398 / 0.89 | 订阅 |
| J. Org. Chem. | 0022-3263 / 1520-6904 | `acs` | ✓ 102,604 / 1,978 / 0.07 | 订阅 |
| Organic Letters | 1523-7060 / 1523-7052 | `acs` | ✓ 45,822 / 2,608 / 0.08 | 订阅 |
| Inorganic Chemistry | 0020-1669 / 1520-510X | `acs` | ✓ 77,665 / 2,617 / 0.09 | 订阅 |
| Analytical Chemistry | 0003-2700 / 1520-6882 | `acs` | ✓ 140,192 / 3,197 / 0.09 | 订阅 |
| J. Phys. Chem. Lett. | 1948-7185 / 1948-7185 | `acs` | ✓ 20,105 / 1,757 / 0.08 | 订阅 |
| J. Chem. Theory Comput. | 1549-9618 / 1549-9626 | `acs` | ✓ 12,095 / 1,055 / 0.09 | 订阅 |
| Chem. Eur. J. | 0947-6539 / 1521-3765 | `wiley_vch` | ✓ 52,322 / 2,060 / 0.88 | 订阅 |
| Green Chemistry | 1463-9262 / 1463-9270 | `rsc` | ✓ 15,487 / 1,371 / 0.87 | 订阅 |
| PCCP | 1463-9076 / 1463-9084 | `rsc` | ✓ 58,603 / 2,492 / 0.93 | 订阅 |
| Coord. Chem. Rev. | 0010-8545 / 0010-8545 | `elsevier_sd` | ✓ 10,762 / 698 / 0.00 | 订阅 |
| CCS Chemistry | 2096-5745 / 2096-5745 | `ccs_chemistry` | ✓ 2,201 / 332 / 0.00 | OA（DOAJ） |
| Pure Appl. Chem.（IUPAC） | 0033-4545 / 1365-3075 | `degruyter_brill` | ✓ 11,266 / 199 / 0.87 | 订阅 |
| ACS Central Science | 2374-7943 / 2374-7951 | `acs` | ✓ 2,861 / 274 / 0.09 | OA（DOAJ，APC 0） |
| Molecular Physics | 0026-8976 / 1362-3028 | `tandf` | ✓ 20,194 / 234 / 0.00 | ⚠ 未查 OpenAlex |

另外已核验但未列入上表的刊：JACS Au（2691-3704，OA）、J. Catal.（0021-9517，Elsevier，摘要 0.00）。数据见附属 CSV。

#### 2.8.4 材料、地学与综合（简表）

| venue | ISSN（p / e） | 平台 | Crossref 可枚举性 | OA 情况 |
|---|---|---|---|---|
| Nature Materials | 1476-1122 / 1476-4660 | `nature_portfolio` | ✓ 6,996 / 384 / 0.10 | 订阅 |
| Advanced Materials | 0935-9648 / 1521-4095 | `wiley_vch` | ✓ 45,201 / 4,258 / 0.88 | 订阅 |
| Advanced Functional Materials | 1616-301X / 1616-3028 | `wiley_vch` | ✓ 43,321 / 6,615 / 0.93 | 订阅 |
| Acta Materialia | 1359-6454 / — | `elsevier_sd` | ✓ 21,318 / 998 / 0.00 | 订阅 |
| Geophysical Research Letters | Crossref 登记 1944-8007 / 0094-8276（p/e 颠倒） | `wiley_vch`（AGU；托管于 Wiley ⚠ 本轮未核验） | ✓ 53,101 / 2,069 / 0.99 | OA（DOAJ） |
| Earth Planet. Sci. Lett. | 0012-821X / 1385-013X | `elsevier_sd` | ✓ 21,830 / 437 / 0.00 | 订阅 |
| Nature Geoscience | 1752-0894 / 1752-0908 | `nature_portfolio` | ✓ 5,020 / 265 / 0.21 | 订阅 |
| Nature | 0028-0836 / 1476-4687 | `nature_portfolio` | ✓ 447,366 / 4,550 / 0.12 | 订阅 |
| Science | 0036-8075 / 1095-9203 | `aaas_science` | ✓ 384,026 / 2,037 / 0.85 | 订阅 |
| PNAS | 0027-8424 / 1091-6490 | `pnas` | ✓ 171,866 / 4,359 / 0.85 | 订阅；6 个月后经 PMC 免费 [SEC N39] |
| Science Advances | 2375-2548 / 2375-2548 | `aaas_science` | ✓ 20,410 / 3,181 / 0.98 | OA（DOAJ） |
| Nature Communications | — / 2041-1723 | `nature_portfolio` | ✓ 92,701 / 12,633 / 0.47 | OA（DOAJ） |
| National Science Review | 2095-5138 / 2053-714X | `oup` | ✓ 3,712 / 597 / 0.78 | OA（DOAJ） |
| Proc. R. Soc. A | 1364-5021 / 1471-2946 | `royal_society` | ✓ 6,862 / 374 / 0.98 | 订阅；2026 年 S2O [N59] |
| Phil. Trans. R. Soc. A | 1364-503X / 1471-2962 | `royal_society` | ✓ 8,718 / 316 / 0.89 | 订阅；2026 年 S2O [N59] |

#### 2.8.5 会议与论文集系列

| 系列 | 标识 | 平台 | Crossref 可枚举性（2025） | OA |
|---|---|---|---|---|
| J. Phys.: Conference Series | ISSN 1742-6588 / 1742-6596 | `iop` | ✓ 218,936 / 10,049 / 摘要 1.00 [N94] | OA ⚠（本轮未核验；licenses-current 1.00） |
| AIP Conference Proceedings | 10.1063 前缀下的 proceedings-article | `aip` | 前缀计数 13,239 [N110]；刊级 ISSN 0094-243X 查询 404，1551-7616 查询 429 未复测 ⚠ | 混合 ⚠ |
| Proceedings of SPIE | 10.1117 前缀下的 proceedings-article | `spie_dl` | 前缀计数 27,794 [N110]；ISSN 0277-786X 刊级查询 404 | 订阅 ⚠ |
| Proceedings of Science（PoS） | 10.22323 前缀 | `pos_sissa` | 前缀计数 2,852 [N110]；ISSN 1824-8039 刊级查询 404 | OA ⚠（许可逐卷，本轮未核验） |
| EPJ Web of Conferences | ISSN 2100-014X | `edp_sciences` | ✓ 27,443 / 2,008 / 0.99 [N94] | OA ⚠（本轮未核验；licenses-current 1.00） |
| Oberwolfach Reports | ISSN 1660-8933 / 1660-8941 | `ems_press` | ✓ 1,263 / 57 / 1.00 [N94] | ⚠ |
| Proceedings of the ICM 2022 | edited-book DOI `10.4171/icm2022-N` | `ems_press` | ✓（作为书目可查）[N110] | ⚠ |
| BAPS（APS 会议摘要） | ISSN 0003-0503 | `aps` | ✗（Crossref 刊级查询 404）[N110] | 只做外链 |

## 3. 对 v2 设计的启示（可直接指导设计）

1. **元数据主干不变，但要"理科化"**。
   - 期刊与论文集一律以 Crossref 按 ISSN 枚举，用 `from-created-date` 做增量。
   - VenueSpec 的 `identifiers.issn` 必须登记**全部历史 ISSN**，adapter 按 ISSN 合并查询后以 DOI 去重（PRB 实测需要 [N114]）。
   - 登记时用 DOI 前缀、`container-title`、Crossref `member` 交叉校验，拦截 Crossref ISSN 数据错误（§2.4）。
   - 论文集用 prefix + `type:proceedings-article` 或 `container-title` 枚举，新增 `kind: proceedings_series`。
2. **摘要补齐路由表（新模块）**。
   - 卡片流不能依赖 Crossref 摘要。对每个出版商维护 `abstract_sources` 的优先链，例如：
     - APS：Harvest（OA）→ arXiv → OpenAlex。
     - ACS：ChemRxiv 版本 → OpenAlex。
     - Elsevier：Elsevier API（用户 key）→ arXiv → OpenAlex。
     - Nature 与 Springer：SN Meta API → OpenAlex。
     - MSP、IMS、Duke：arXiv → zbMATH。
   - 链依据 §2.4 的实测覆盖率，可由周期任务自动重算。
   - 摘要记录须保存 `source` 与 `license` 字段。
3. **摘要与全文的"可展示/可共享"判定必须数据化**。
   - Crossref 明示部分摘要受出版商或作者版权保护 [N96]；APS RSS 为"Personal use only" [N7]；SN 规定 API 摘要只能个人使用（见姊妹文档 [N112]；一手条款已核验 [N126]）。
   - v2 应给每条摘要和全文打 `display_scope ∈ {public_shared, per_user_only, link_only}`：
     - CC BY / CC0（APS OA 集、SCOAP3、EMS S2O、SciPost、Quantum、PRX 系等）→ `public_shared`。
     - 订阅内容与版权不明的摘要 → `per_user_only` 或 `link_only`。
     - arXiv 非独占许可的 PDF → `link_only`，或由用户私有取回 [N60]。
4. **不为理科主力站点写"抓取型" adapter**。
   - IOP、ACS、AMS、RSC（迁移期）、Cambridge、SPIE、Preprints.org、MathSciNet 或者 robots 全禁，或者连 robots 都读不到。对这些站点：元数据只走 Crossref 或官方 API；全文只做"用户在自己浏览器中打开 DOI"或用户交互式单篇获取。
   - 新写的 adapter 限于**官方 API 型**：`aps_harvest`、`springer_nature_api`、`inspire_hep`、`zbmath_open`、`nasa_ads_scix`、`scoap3`、`numdam_oai`。另外对 v1 的 `arxiv` 做升级。
5. **arXiv adapter 升级**。
   - 使用分类级 set（`group:archive:category`）[N61][N63]。
   - 修正物理 archive 的 set 推导（加 `physics:` 前缀）。
   - 用生成脚本一次性登记 83 个理科叶子分类（每个分类的 `inception` 须核准），并处理分类别名。
   - 因为 datestamp 是最后修改时间，按 `arXivRaw` 版本历史区分"新论文"与"更新"[N61]。
   - 限速保持每 3 秒 1 次、全局单连接 [N60]。
   - 对"arXiv 独立非营利化"之后的 ToU 变化设置监控 [N64]。
6. **"最新论文"通道以 Crossref 增量为默认，feed 只作新鲜度信号**（§2.6）。
   - 只用 robots 明确允许、且无挑战的 feed：APS feeds、nature RSS、SIAM/Science/PNAS 的 showFeed、Quantum、SciPost、arXiv、INSPIRE、zbMATH OAI。
   - feed 内容不直接展示（版权原因），只用于触发 Crossref/API 补全。
7. **官方 API 的凭证模型**（多用户）。
   - 每用户凭证：ADS token、SN api_key、Elsevier key、Wiley token、APS Harvest 授权。
   - 平台级免 key 的公开 API（INSPIRE、zbMATH、arXiv OAI、SCOAP3、Crossref、APS Harvest OA 集）由平台以单一全局限速器访问，结果进入共享元数据库（许可允许的部分）。
   - **禁止用多 key 或多账号规避限额**（SN 条款，见 [N112]；一手条款已核验 [N126]）。
   - 所有 TDM 流量的 UA 须带平台身份，访问 SN 时须含 `TextDataMining` [N26]。
   - 联系邮箱由部署方配置，不硬编码。
8. **全局限速器与配额账本**（多 agent / 多用户共享出口）。
   - 本轮 Crossref 公共池出现 17 次以上 429，同日另一 agent 观测到限额为 1 [N112]。核验修正：限额不是随机"动态"，而是按请求类型分档（公共池单条 5 次/秒、列表 1 次/秒，并发 1；polite 池 10/3 次/秒，并发 3；Metadata Plus 150 次/秒）[N121]；429 来自多 agent 共享出口叠加。限速器应按响应头 `x-api-pool`、`X-Rate-Limit-*`、`X-Concurrency-Limit` 分档调整，并优先使用 polite pool（带运营联系邮箱）。
   - 需要登记的限额：

     | 来源 | 限额 |
     |---|---|
     | Crossref 公共池（核验补充） | 单条记录每秒 5 次、列表查询每秒 1 次，并发 1 [N121] |
     | Crossref polite 池（核验补充） | 单条每秒 10 次、列表每秒 3 次，并发 3 [N121] |
     | arXiv | 每 3 秒 1 次 |
     | INSPIRE | 每 5 秒 15 次 |
     | ADS | 每日 5,000 次（按端点单独计） |
     | SN 直接下载 | 每秒 1 次 |
     | SN TDM API（付费，需 key） | 每分钟 150 次 |
     | SN OA API（免费档） | 每日 500 次、每分钟 100 次 |
     | PubChem PUG（核验补充，2019 口径） | 每秒 ≤5 次、每分钟 ≤400 次、每分钟运行时间 ≤300 s [N124] |
     | Cambridge | 每小时 ≤500 PDF |
     | Project Euclid | Crawl-delay 10 |
     | MathSciNet | Crawl-delay 10（且禁止） |
     | PoS | Crawl-delay 5 |
     | Numdam | Crawl-delay 2 |
     | Atypon 系 | Crawl-delay 1 |
     | WSP | 短时 200 次下载即切断 [SEC] |

9. **来源漂移监控（source health / drift）**，建议作为 v2 的一等公民任务。
   - 周期比对每个 VenueSpec 在 Crossref 中最新 DOI 的 `prefix`、`member`、`publisher` 与 `resource.primary.URL` 域名。本轮已观测到的漂移：IHÉS→Centre Mersenne，ChemRxiv 与 ESSOAr→Wiley REX，RSC→Silverchair，APS DOI 形态变化。
   - 同时比对 robots.txt 哈希与挑战状态（APS robots 2026-08 才撤掉 2014 年起的 `Disallow: /` [N6]，说明 robots 会突变）。
   - **OpenAlex 的 host 字段不可用于路由**：IHÉS 在 OpenAlex 仍标为 Springer [N95]。
10. **OA 全文优先链（理科专用）**：出版商官方 OA API（APS Harvest OA、SN OA API）→ SCOAP3 → arXiv（`link_only` 或私有）→ Unpaywall/PMC（PNAS 6 个月后）→ 用户单篇。S2O 刊（EMS、AIP 的 JAP/PoP、Royal Society）按"年份 + 单篇许可"判定。核验修正：AIP 的 JAP/PoP 只有 2024–2025 年卷是 S2O 整刊 OA，2026 年起须逐篇判定 [N118]；SCOAP3 对 PRL/PRD/PRC 等只资助 HEP 分类文章，也须逐篇读许可 [N117]。
11. **学科分类法作为推荐的标签空间**。
    - 物理：PhySH（CC0 JSON/RDF [N97]；APS Harvest 直接返回 [N3]）。
    - 数学：MSC（zbMATH Open KG 含 6.7K+ 类 [N79]）。核验补充：MSC2020 为 CC BY-NC-SA 4.0 [N120]，与 PhySH 的 CC0 不同；若 v2 有商业化可能，须先做许可评估。
    - 通用：arXiv 分类（CC0 元数据 [N60]）。
    - 化学没有同等开放的细粒度分类（ChemRxiv 分类与 Crossref `subject` 可作起点 ⚠）。
    - 把这些分类映射到统一的 `topic` 表，可同时服务检索过滤、用户兴趣冷启动（让用户勾选分类）和推荐特征。
    - VenueSpec 的 `field` 枚举扩展为 `math`、`physics`、`chemistry`、`materials`、`earth`、`astro` 等。
12. **身份图（v1 D-007）接入学科映射源**。APS Harvest 的 `identifiers.arxiv` [N3]、INSPIRE 的 arXiv/DOI/会议记录 [N81]、ADS 的 bibcode↔arXiv↔DOI（⚠ 本轮未实测，需 token）、zbMATH 的 DOI↔zbMATH id [N78]。这些都是"预印本↔正式版"强标识映射，可以显著提升跨源合并的准确率。
13. **优先级落地建议**。
    - **P0**：
      - `arxiv`（理科扩展）。
      - Crossref 理科 VenueSpec 批量登记（§2.8 的约 100 刊）。
      - `aps_harvest`、`springer_nature_api`、`inspire_hep`、`zbmath_open`。
      - `chemrxiv`（经 Crossref）。
      - 沿用 `elsevier_sd`、`wiley`。
      - 摘要路由表。
    - **P1**：`scoap3`、`nasa_ads_scix`、`numdam_oai`、`oup`/`cambridge` 的用户单篇，以及 IOP、ACS、RSC、AIP、Optica、AMS、SIAM、EMS、Project Euclid、MSP、Science、PNAS、T&F、De Gruyter、MDPI（核验补充）的 VenueSpec（仅元数据）。
    - **P2**：预印本长尾（Research Square、Preprints.org、ESSOAr、EarthArXiv、Optica Open）、会议论文集系列、中文源、PubChem 关联、OSTI.GOV（核验补充）。
14. **预印本长尾走 Crossref，不走站点**。ChemRxiv（10.26434）、Research Square（10.21203）、Preprints.org（10.20944，`group-title` 即学科）、Authorea/ESSOAr（10.22541）、EarthArXiv（10.31223）、Optica Open（10.1364/opticaopen）都在 Crossref 中有 posted-content [N70]。v2 用一个"Crossref 预印本前缀 adapter"加学科过滤就能覆盖。各前缀的 DOI 版本后缀形态不同（`/v1` 与 `.v1`），须写成解析规则。
15. **ToS 的"系统化下载"条款是全文的硬边界**。APS [N4]、IOP [N9]、AIP [SEC N15]、Cambridge [N58]、WSP [SEC N45] 都明确限制。即使用户有订阅，后台批量预取全文也不合规。v2 的全文获取必须是**用户触发、按需、单篇、低频**；预取只允许 `public_shared` 类 OA 全文。

## 4. 未决问题与风险

1. **robots 与"官方 API/Feed/用户触发"之间的冲突，需要写 ADR 裁决**。
   - IOPscience 的 `*` 为 `Disallow: /`，但 RSS 在提供服务 [N10][N11]。
   - PubChem 的 robots 禁止 `/rest/pug/`，而 PUG-REST 是官方文档化 API [N88][N89]。
   - link.springer.com 对白名单外路径全禁 [N31]。
   - 需要裁决的问题：D-014"明确 Disallow 的路径不访问"是否适用于用户在界面中逐篇触发的获取（类浏览器行为），以及是否适用于官方文档化 API。建议的保守默认：后台一律遵守；用户触发的单篇获取按 ToS 判断，并在 UI 中明示。
   - 本轮已有 2 次偏差（§1.4.5），须在 ADR 中说明。
2. **多用户平台展示摘要的版权风险**：Crossref 声明 [N96]、APS RSS 声明 [N7]、SN 摘要仅限个人使用（见 [N112]）。**建议设计阶段请法务或用户确认**："摘要对所有用户可见"是否只限于 CC 许可来源。
3. **APS Harvest 全量授权的条件不透明**：首页只写"Contact help@aps.org to obtain access"[N2]。个人研究者能否取得授权、授权是否允许多用户平台使用，都未知。
4. **ACS 的机器政策无法读取**（robots 403 [N19]），二手来源互相矛盾（付费方案 [N18] 与"不允许"[N15]）。在官方书面确认之前，ACS 站点保持零自动化。
5. **RSC 迁移完成度未知**：公告日期为 2026-02-26 [N21]，robots 已切换 [N23]，但 PDF/HTML 路径和 TDM 条款的一手页面都无法读取（403）。
6. **ChemRxiv、ESSOAr 在 Wiley REX 上的 API 未知**：旧 API 已受 CF 挑战 [N69]，Wiley REX 是否提供公开 API ⚠。ESSOAr 的迁移日期只有维基百科来源，且"2026-05"实指 Authorea 迁移后暂停投稿的时间（核验修正，见 §2.2.2）[N72]。缓解：Crossref 中 ChemRxiv 记录约 98% 带摘要 [N137]，Crossref 通道可独立支撑元数据与摘要。
7. **ADS→SciX 切换**：官方站点只确认"今年秋季"切换、账户与 library 保留 [N123]；2026-11-16 这一日期和"API 与 token 保持不变"仍只有二手来源 [N86]；域名、配额、条款在切换后须复测。
8. **arXiv 独立非营利化后的治理风险**：目前官方称"使命不变"[N64]，但 API ToU、bulk 渠道（Kaggle/S3）或会员制都可能调整，需设季度复核。
9. **Crossref 公共池容量有限**：本轮 429 频发，姊妹文档还观测到 `limit: 1` [N112]。核验修正：`limit: 1` 是 2025-12-01 起公共池列表查询的固定档位，不是异常 [N121]。按"列表查询每秒 1 次"估算，公共池单出口每天最多约 8.6 万次列表请求（估算），v2 必须用 polite pool；多用户规模扩大后，需评估 Metadata Plus（付费，每秒 150 次、无并发限制 [N121]）。
10. **zbMATH 的 CC BY-SA 相同方式共享义务**：若 v2 对外提供基于 zbMATH 数据的派生内容（如推荐理由、主题标签），可能触发 SA 义务 ⚠。另有部分评论因许可冲突缺失 [N78]。
11. **二手证据比例偏高的政策条目**：AIP、SIAM、ACS、De Gruyter、Science 的 TDM 口径，WSP 的 200 次阈值，AMS 的 5 年墙，PNAS 的 6 个月，都来自图书馆指南或搜索摘要 [N15][N45][N47][N39]。进入 ADR 前应取得一手条款。De Gruyter 的二手口径互相冲突（"不允许"与"授权用户可非商业"）[N15][N43]。核验进展：PNAS 的 6 个月已由 NLM PMC 刊表确认 [N122]；Cranfield（2026-09-01 更新）与 ASU（2026-07-06 更新）两份指南的原文已直读，与文中转述一致，但仍属二手来源。
12. **代理出口偏差**：本机经代理出网，大量站点的挑战结论可能受出口 IP 信誉影响 [§1.4.1]，与用户在校园网下的实际体验不同。设计阶段应在"用户本地网络"下复测 auth 族（与 v1 test-plan §8 一致 [N113]）。
13. **分类法许可与覆盖**：PhySH 为 CC0 [N97]；MSC2020 为 CC BY-NC-SA 4.0（核验补充 [N120]），zbMATH API 数据整体为 CC BY-SA；化学缺少开放的细粒度分类，推荐冷启动在化学侧可能偏弱。
14. **OpenAlex 匿名配额**：单实体查询 `x-ratelimit-cost-usd: 0`，匿名每日 1,000 credits（实测响应头 `x-ratelimit-limit: 1000`）。如果 v2 用 OpenAlex 补摘要（需 list/search 查询），成本须纳入预算（v1 已知计费改制 [N113]）。
15. **地学与材料名录不完整**：本文只做简述（§2.3.6），AGU、EGU/Copernicus、GSA 等须由后续专题补齐。

## 5. 参考来源（访问日期均为 2026-09-26）

- [N1] APS Harvest API 文档 — https://harvest.aps.org/docs/harvest-api [DOC]
- [N2] APS Harvest 首页 — https://harvest.aps.org/ [DOC]
- [N3] APS Harvest OA 集实测 — https://harvest.aps.org/v2/journals/articles?from=2026-09-20&until=2026-09-21&set=openaccess&per_page=2 [LIVE]
- [N4] APS 使用条款 — https://journals.aps.org/info/terms.html [DOC]
- [N5] APS Data Sets for Research — https://journals.aps.org/datasets [DOC]
- [N6] APS robots.txt（Last-Modified 2026-09-23）— https://journals.aps.org/robots.txt [LIVE]
- [N7] APS RSS（PRL）— http://feeds.aps.org/rss/recent/prl.xml [LIVE]；feeds.aps.org/robots.txt 为 404 [LIVE]
- [N8] APS Open Science 公告（2025-12-03）— https://www.aps.org/about/news/2025/12/open-science-expand-global-participation [DOC]
- [N9] IOP Publishing T&DM 与 AI 政策（2026-07 更新）— https://ioppublishing.org/legal/textanddataminingpolicy/ [DOC]
- [N10] IOPscience robots.txt — https://iopscience.iop.org/robots.txt [LIVE]
- [N11] IOPscience RSS（NJP）— https://iopscience.iop.org/journal/rss/1367-2630 [LIVE]
- [N12] IOPscience TDMRep 路径（Radware 302）— https://iopscience.iop.org/.well-known/tdmrep.json [LIVE]
- [N13] AIP Publishing robots.txt — https://pubs.aip.org/robots.txt [LIVE]
- [N14] AIP Publishing S2O 页面 — https://publishing.aip.org/resources/researchers/open-science/publish-for-free-%20through-our-subscribe-to-opens2o-pilot/ [LIVE 直取]
- [N15] Cranfield University Library：Publisher policies for TDM — https://library.cranfield.ac.uk/text-and-data-mining/publisher-policies [SEC]
- [N16] Optica Publishing Group robots.txt — https://opg.optica.org/robots.txt [LIVE]
- [N17] Optica 数据与媒体对象使用条款 — https://opg.optica.org/include/datasets_termsofuse.cfm [SEC 搜索摘要]
- [N18] ACS Solutions：Text & Data Mining — https://solutions.acs.org/solutions/text-and-data-mining/ [DOC]
- [N19] ACS Publications robots.txt（403）— https://pubs.acs.org/robots.txt [LIVE]
- [N20] RSC：AI and TDM applications — https://www.rsc.org/journals-books-databases/research-tools/text-and-data-mining/ [SEC 搜索摘要；WebFetch 403]
- [N21] Silverchair 新闻：RSC Expands Partnership（2026-02-26）— https://www.silverchair.com/news/rsc-expands-partnership/ [DOC]
- [N22] Silverchair 新闻列表（Royal Society Publishing 2025-12-02 上线等）— https://www.silverchair.com/news/ ；条目 https://www.silverchair.com/news/royal-society-publishing-launches/ [DOC]
- [N23] RSC robots.txt — https://pubs.rsc.org/robots.txt [LIVE]；首页 https://pubs.rsc.org/ 返回 CF 挑战 [LIVE]
- [N24] Chemistry World：RSC 调整 OA 推进方向 — https://www.chemistryworld.com/news/royal-society-of-chemistry-changes-direction-on-open-access-rollout-following-community-feedback/4021761.article [SEC；核验时已直读：2025-06-25 报道，原目标为 2028 年前 58 种刊全 OA，改为按地区定制模式]
- [N25] Springer Nature：Text and Data Mining（研究者）— https://www.springernature.com/gp/researchers/text-and-data-mining [DOC]
- [N26] Springer Nature Support：Text and data mining / TDM — https://support.springernature.com/en/support/solutions/articles/6000251800-text-and-data-mining-tdm [DOC]
- [N27] Springer Nature Data Solutions：Open Access API — https://datasolutions.springernature.com/products/open-access/ [DOC]
- [N28] Springer Nature Data Solutions：Metadata API — https://datasolutions.springernature.com/products/meta-data/ [DOC]
- [N29] Springer Nature Support：Link API details — https://support.springernature.com/en/support/solutions/articles/6000195668-springer-nature-link-api-details [DOC]
- [N30] springernature/springernature_api_client — https://github.com/springernature/springernature_api_client [gh LIVE]
- [N31] link.springer.com robots.txt — https://link.springer.com/robots.txt [LIVE]
- [N32] link.springer.com TDMRep — https://link.springer.com/.well-known/tdmrep.json [LIVE]
- [N33] Springer Nature TDMRep 策略（ODRL）— https://dev.springernature.com/tdm/SNTDMPolicy.json [LIVE]
- [N34] nature.com robots.txt 与 TDMRep — https://www.nature.com/robots.txt ；https://www.nature.com/.well-known/tdmrep.json [LIVE]
- [N35] Nature Physics RSS — https://www.nature.com/nphys.rss [LIVE]
- [N36] Elsevier：Text and data mining policy — https://www.elsevier.com/about/policies-and-standards/text-and-data-mining [DOC]
- [N37] Science（AAAS）robots.txt — https://www.science.org/robots.txt [LIVE]
- [N38] PNAS robots.txt — https://www.pnas.org/robots.txt [LIVE]
- [N39] UTMB Moody Medical Library：PNAS APC 与 OA — https://guides.utmb.edu/oa/pnas [SEC]
- [N40] Taylor & Francis：Text and Data Mining — https://taylorandfrancis.com/our-policies/textanddatamining/ [DOC]
- [N41] Taylor & Francis Online robots.txt — https://www.tandfonline.com/robots.txt [LIVE]；`/.well-known/tdmrep.json` 返回 CF 挑战 [LIVE]
- [N42] De Gruyter Brill robots.txt — https://www.degruyterbrill.com/robots.txt [LIVE]
- [N43] UNSW Library：AI/TDM/API publisher resources — https://subjectguides.library.unsw.edu.au/ai-tdm-api/tdm/publisher-resources [SEC 搜索摘要；WebFetch 证书错误]
- [N44] World Scientific robots.txt — https://www.worldscientific.com/robots.txt [LIVE]
- [N45] ASU Library：TDM data sources — https://libguides.asu.edu/textanddatamining/datasources [SEC]
- [N46] SIAM robots.txt — https://epubs.siam.org/robots.txt [LIVE]
- [N47] AMS Subscription Information（5 年滑动墙）— https://www.ams.org/publications/journals/subscriberinfo [SEC 搜索摘要；直连 403]
- [N48] AMS robots.txt（CF 挑战）— https://www.ams.org/robots.txt ；https://pubs.ams.org/robots.txt [LIVE]
- [N49] MathSciNet robots.txt — https://mathscinet.ams.org/robots.txt [LIVE]
- [N50] EMS Press：2026 S2O 公告（2026-02-12）— https://ems.press/updates/2026-02-12-2026-s2o-announcement [DOC]
- [N51] EMS Press：Launch to Open（2026-03-30）— https://ems.press/updates/2026-03-30-ems-press-unveils-l2o [DOC]
- [N52] EMS Press：Subscribe To Open — https://ems.press/subscribe-to-open [DOC]
- [N53] EMS Press robots.txt — https://ems.press/robots.txt [LIVE]
- [N54] Project Euclid：About — https://projecteuclid.org/about [DOC]
- [N55] Project Euclid：Librarians — https://projecteuclid.org/librarians [DOC]
- [N56] Project Euclid robots.txt — https://projecteuclid.org/robots.txt [LIVE]
- [N57] MSP robots.txt — https://msp.org/robots.txt [LIVE]
- [N58] Cambridge Core Terms of Use — https://www.cambridge.org/core/legal-notices/terms [DOC]
- [N59] Royal Society：Subscribe to Open（2025-08-06）— https://royalsociety.org/news/2025/08/subscribe-to-open/ [DOC]
- [N60] arXiv API Terms of Use — https://info.arxiv.org/help/api/tou.html [DOC]
- [N61] arXiv OAI-PMH 文档 — https://info.arxiv.org/help/oa/index.html [DOC]
- [N62] arXiv OAI ListSets — https://oaipmh.arxiv.org/oai?verb=ListSets [LIVE]
- [N63] arXiv OAI ListIdentifiers（set=math:math:AG）— https://oaipmh.arxiv.org/oai?verb=ListIdentifiers&metadataPrefix=oai_dc&set=math:math:AG&from=2026-09-23&until=2026-09-24 [LIVE]
- [N64] arXiv Blog：arXiv is becoming an independent nonprofit（2026-04-02）— https://blog.arxiv.org/2026/04/02/arxiv-is-becoming-an-independent-nonprofit/ [DOC]
- [N65] arXiv Blog：arXiv now hosts over 3 million articles（2026-07-09）— https://blog.arxiv.org/2026/07/09/arxiv-now-hosts-over-3-million-articles/ [DOC]
- [N66] DataCite API：arXiv 前缀计数 — https://api.datacite.org/dois?query=prefix:10.48550&page[size]=1 [LIVE]
- [N67] ACS：ChemRxiv Site Migration FAQs — https://connect.acspubs.org/chemrxiv-migration-FAQ [DOC]
- [N68] ChemRxiv robots.txt — https://chemrxiv.org/robots.txt [LIVE]
- [N69] ChemRxiv 旧 Open Engage API（CF 挑战）— https://chemrxiv.org/engage/chemrxiv/public-api/v1/items?limit=1 [LIVE]
- [N70] Crossref 预印本前缀查询 — https://api.crossref.org/prefixes/{10.26434,10.20944,10.21203,10.22541,10.31223,10.1364,10.21468}/works?filter=type:posted-content,from-posted-date:… [LIVE]
- [N71] Research Square robots.txt — https://www.researchsquare.com/robots.txt [LIVE]
- [N72] Wikipedia：Authorea — https://en.wikipedia.org/wiki/Authorea [SEC]
- [N73] ESS Open Archive robots.txt — https://essopenarchive.org/robots.txt [LIVE]
- [N74] Preprints.org robots.txt（Akamai 403）— https://www.preprints.org/robots.txt [LIVE]；API 客户端注册页 https://www.preprints.org/apiclient/new [SEC 搜索结果]
- [N75] EarthArXiv API 根 — https://eartharxiv.org/api/ [LIVE]
- [N76] zbMATH Open REST API 条款 — https://api.zbmath.org/static/terms-and-conditions.html [DOC]（核验时 307 跳转到 https://api.zbmath.org/v1/static/terms-and-conditions.html ）
- [N77] zbMATH Open OAI-PMH Identify — https://oai.zbmath.org/v1/?verb=Identify [LIVE]
- [N78] zbMATH Open REST 检索样本 — https://api.zbmath.org/v1/document/_search?search_string=py%3A2026&page=0&results_per_page=1 [LIVE]
- [N79] zbMATHOpen/zbmath-open-kg（README）— https://github.com/zbMATHOpen/zbmath-open-kg [gh LIVE]
- [N80] INSPIRE REST API 文档 — https://github.com/inspirehep/rest-api-doc/blob/master/README.md [DOC]
- [N81] INSPIRE API 样本 — https://inspirehep.net/api/literature?sort=mostrecent&size=1&q=t%20higgs&fields=titles,dois,arxiv_eprints,created [LIVE]
- [N82] INSPIRE robots.txt — https://inspirehep.net/robots.txt [LIVE]
- [N83] adsabs/adsabs-dev-api — https://github.com/adsabs/adsabs-dev-api [DOC]
- [N84] ADS API Rate Limit Policy — https://ui.adsabs.harvard.edu/help/policies/rate-limits [SEC 搜索摘要；页面 JS 渲染]
- [N85] Bartlett, Kundu, Accomazzi, Kurtz, "Transitioning from ADS to SciX to Serve 21st Century Astronomy", arXiv:2609.18091（2026-09-16）— https://arxiv.org/abs/2609.18091 [DOC]
- [N86] SciX：Transition from ADS to SciX — https://scixplorer.org/adstoscix/ [SEC 搜索摘要]
- [N87] PubChem PUG-REST 样本 — https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/aspirin/xrefs/PubMedID/JSON [LIVE]
- [N88] PubChem robots.txt — https://pubchem.ncbi.nlm.nih.gov/robots.txt [LIVE]
- [N89] PubChem Programmatic Access 文档 — https://pubchem.ncbi.nlm.nih.gov/docs/programmatic-access [DOC；JS 渲染，未取到数值]
- [N90] SCOAP3 Repository 说明 — https://scoap3.org/scoap3-repository/ [DOC]
- [N91] SCOAP3 Repository API 样本 — https://repo.scoap3.org/api/records/?page_size=1 [LIVE]
- [N92] Numdam OAI-PMH Identify 与 robots — https://www.numdam.org/oai/?verb=Identify ；https://www.numdam.org/robots.txt [LIVE]
- [N93] Crossref：Publ. Math. IHÉS 最新 DOI — https://api.crossref.org/journals/0073-8301/works?sort=created&order=desc&rows=5 [LIVE]
- [N94] Crossref 期刊批量核验 — https://api.crossref.org/journals/{ISSN}（115 个刊或系列；原始数据见附属 CSV）；附带复核 https://api.crossref.org/journals/{0004-637X,0035-8711}/works?sort=created&order=desc&rows=2（ApJ 前缀 10.3847、MNRAS 论文级 e-ISSN）[LIVE]
- [N95] OpenAlex sources 批量核验 — https://api.openalex.org/sources/issn:{ISSN} [LIVE]
- [N96] Crossref REST API 文档（元数据版权与摘要例外）— https://www.crossref.org/documentation/retrieve-metadata/rest-api/ [DOC]
- [N97] physh-org/PhySH（README、LICENSE.md 为 CC0）— https://github.com/physh-org/PhySH [gh LIVE]
- [N98] SciPost robots.txt 与 /api/ — https://scipost.org/robots.txt ；https://scipost.org/api/ [LIVE]
- [N99] Quantum RSS 与 robots — https://quantum-journal.org/feed/ ；https://quantum-journal.org/robots.txt [LIVE]
- [N100] Proceedings of Science robots.txt — https://pos.sissa.it/robots.txt [LIVE]
- [N101] SPIE Digital Library robots.txt（Incapsula 挑战页）— https://www.spiedigitallibrary.org/robots.txt [LIVE]
- [N102] EDP Sciences robots.txt（A&A、EPJ WoC）— https://www.aanda.org/robots.txt ；https://www.epj-conferences.org/robots.txt [LIVE]
- [N103] GeoScienceWorld robots.txt — https://pubs.geoscienceworld.org/robots.txt [LIVE]
- [N104] 中文源 robots.txt：SciEngine https://www.sciengine.com/robots.txt ；CCS https://www.chinesechemsoc.org/robots.txt ；物理学报 https://wulixb.iphy.ac.cn/robots.txt ；ChinaXiv https://chinaxiv.org/robots.txt（维护页）[LIVE]
- [N105] 数学 OA 平台 robots.txt：Centre Mersenne https://www.centre-mersenne.org/robots.txt ；Episciences https://epiga.episciences.org/robots.txt ；Discrete Analysis https://discreteanalysisjournal.com/robots.txt [LIVE]
- [N106] Annals of Mathematics robots.txt — https://annals.math.princeton.edu/robots.txt [LIVE]
- [N107] OUP 与 Wiley robots.txt — https://academic.oup.com/robots.txt ；https://onlinelibrary.wiley.com/robots.txt [LIVE]；Wiley `/.well-known/tdmrep.json` 返回 CF 挑战 [LIVE]
- [N108] Cambridge Core robots.txt（CF 挑战）— https://www.cambridge.org/robots.txt [LIVE]
- [N109] Optica Open — https://opticaopen.org/（302 到登录页）；https://preprints.opticaopen.org/robots.txt（202 空响应）[LIVE]
- [N110] Crossref 会议与论文集前缀计数（10.1117、10.22323、10.1063 的 proceedings-article；ICM 2022 在 10.4171 下的查询；BAPS ISSN 0003-0503）— https://api.crossref.org/prefixes/{prefix}/works?filter=type:proceedings-article,from-pub-date:2025-01-01,until-pub-date:2025-12-31&rows=0 等 [LIVE]
- [N111] GitHub 仓库核验（gh api，stars/license/pushed_at/archived）：lukasschwab/arxiv.py、jannisborn/paperscraper、andycasey/ads、adsabs/adsabs-dev-api、inspirehep/inspirehep、inspirehep/rest-api-doc、WileyLabs/tdm-client、ElsevierDev/elsapy、springernature/springernature_api_client、SCOAP3/scoap3、SCOAP3/scoap3-next、mcs07/PubChemPy、MaRDI4NFDI/python-zbMathRest2Oai、zbMATHOpen/zbmath-open-kg、physh-org/PhySH、arXiv/arxiv-oaipmh — https://github.com/{owner}/{repo} [gh LIVE]
- [N112] 姊妹调研：docs/survey/sources/social-sciences-econ-fin-mgmt.md（Crossref 公共池同日观测；Springer Nature API 条款 [R39]；Crossref 摘要版权 [R26]）[仓库内文档]
- [N113] v1 文档：docs/catalog/publishers-platforms.md、docs/catalog/preprint-platforms.md、docs/research/site-survey/metadata-apis.md、docs/research/site-survey/arxiv.md、docs/research/site-survey/aggregators-unpaywall-dblp-core.md、docs/research/site-survey/publisher-platforms-cs.md、docs/research/site-survey/publisher-platforms-p4-recheck.md、docs/plan/decision-log.md（D-005/D-007/D-013/D-014）、docs/design/adapters/README.md、src/paper_crawler/types.py [仓库内文档]
- [N114] Crossref：PRB ISSN 别名窗口查询 — https://api.crossref.org/journals/{1098-0121,2469-9950,2469-9969,1550-235X}/works?filter=from-pub-date:{2010-06-01|2024-06-01},until-pub-date:{…-30}&rows=1 [LIVE]
- [N115] arXiv Blog 索引（2025–2026 文章列表）— https://blog.arxiv.org/ [DOC]
- [N116] zbmath.org robots.txt（CF 挑战）— https://zbmath.org/robots.txt [LIVE]

**核验补充来源**（核验阶段新增，访问日期均为 2026-09-26）

- [N117] SCOAP3 Journals 2025–2027（11 刊及覆盖比例）— https://scoap3.org/journals-2025-2027/ [DOC]
- [N118] AIP Publishing 新闻：S2O 试点 2024 年（2024-03-07）— https://publishing.aip.org/about/news/two-aip-publishing-journals-now-open-access-under-subscribe-to-open-pilot/ ；2025 年（2025-03-19）— https://publishing.aip.org/about/news/journal-of-applied-physics-physics-of-plasmas-open-access-in-2025-under-subscribe-to-open-pilot/ ；试点结束（2025-10-29）— https://publishing.aip.org/about/news/evolving-our-open-access-strategy-aip-publishing-concludes-the-subscribe-to-open-pilot/ [DOC]
- [N119] Royal Society：2026 年 S2O 门槛达成公告（2026-02-16）— https://royalsociety.org/news/2026/02/subscribe-to-open-announcement/ [DOC]
- [N120] MSC2020（MR 与 zbMATH 联合发布，CC BY-NC-SA 4.0）— https://msc2020.org/ [DOC]
- [N121] Crossref 限速：博客"Announcing changes to REST API rate limits"（2025-11-05 发布，2025-12-01 生效）— https://www.crossref.org/blog/announcing-changes-to-rest-api-rate-limits/ ；文档 Access and authentication（页面署 2025-10-16 更新）— https://www.crossref.org/documentation/retrieve-metadata/rest-api/access-and-authentication/ ；响应头实测 https://api.crossref.org/works?filter=prefix:10.1103,from-created-date:2026-09-25&rows=5 （`public-array`）与 https://api.crossref.org/works/10.1103/fxpf-vzxx （`public-single`）[DOC/LIVE]
- [N122] NLM PMC 期刊清单 CSV（PNAS 行：Release Delay 6 months，Agreement to Deposit 为 All articles）— https://cdn.ncbi.nlm.nih.gov/pmc/home/jlist.csv [LIVE]
- [N123] ADS/SciX 官方站点源码：`adstoscix/index.md`、`help/whats_new/_posts/2026-01-01-whats-new.md` — https://github.com/adsabs/adsabs.github.io [gh LIVE]；scixplorer.org/adstoscix/ 直连返回 202 空响应 [LIVE]
- [N124] Kim S, Thiessen PA, Cheng T, Zhang J, Gindulyte A, Bolton EE. "PUG-View: programmatic access to chemical annotations integrated in PubChem." J Cheminform 11:56（2019-08-09），PMC6688265 — https://europepmc.org/article/PMC/PMC6688265 [DOC，经 Europe PMC REST API 取全文]
- [N125] jannisborn/paperscraper PR #99（2026-01-25 合并）与 PR #103（2026-02-24 合并）— https://github.com/jannisborn/paperscraper/pull/99 ；https://github.com/jannisborn/paperscraper/pull/103 [gh LIVE]
- [N126] Springer Nature API Terms and conditions — https://dev.springernature.com/terms-conditions/ [DOC；页面未标版本日期]
- [N127] OSTI.GOV：API 文档 https://www.osti.gov/api/v1/docs ；About https://www.osti.gov/about ；robots https://www.osti.gov/robots.txt （Last-Modified 2024-12-05）；样本 https://www.osti.gov/api/v1/records?has_fulltext=true&rows=1 [DOC/LIVE]
- [N128] CAS Terms of Use – Academic Users（Version 10/10/2023）— https://web.cas.org/marketing/pdf/product-use-terms-academic-10-10-23.pdf [DOC]
- [N129] EuDML OAI-PMH 说明 — https://initiative.eudml.org/oai-pmh-server ；Ex Libris 知识库 EuDML 条目 — https://knowledge.exlibrisgroup.com/Content/Knowledge_Articles/Alma/Knowledge_Articles/360_KB:_Collection-_EuDML:_The_European_Digital_Mathematics_Library [SEC 搜索摘要]；https://eudml.org/robots.txt 与 https://eudml.org/oai/OAIHandler?verb=Identify 均返回 nginx 403 [LIVE]
- [N130] Royal Society Publishing robots.txt（Last-Modified 2026-09-26）— https://royalsocietypublishing.org/robots.txt [LIVE]
- [N131] Optica 数据条款页 302 到 Radware Bot Manager（validate.perfdrive.com）— https://opg.optica.org/include/datasets_termsofuse.cfm [LIVE；遇挑战即停，未跟随]
- [N132] arXiv OAI 旧式 set 测试 — https://oaipmh.arxiv.org/oai?verb=ListIdentifiers&metadataPrefix=oai_dc&set=cond-mat&from=2026-09-23&until=2026-09-23 （`badArgument`：Set does not exist）[LIVE]
- [N133] Crossref：MDPI 理科刊 — https://api.crossref.org/journals/1420-3049 ；https://api.crossref.org/journals/1996-1944 ；https://api.crossref.org/journals/2227-7390 [LIVE]；MDPI OAI Identify https://oai.mdpi.com/oai/oai2.php?verb=Identify 本次 504 后超时 [LIVE]
- [N134] 姊妹调研：docs/survey/sources/life-sciences-psychology.md（`mdpi` 行与 [R53] MDPI OAI-PMH、Akamai 实测）[仓库内文档]
- [N135] OpenAlex：JAMS 按年 OA 状态分组 — https://api.openalex.org/works?filter=primary_location.source.issn:0894-0347,publication_year:2020&group_by=open_access.oa_status （及 2018、2021、2022、2024）[LIVE]
- [N136] arXiv Category Taxonomy（别名声明）— https://arxiv.org/category_taxonomy [DOC]
- [N137] Crossref：ChemRxiv 摘要覆盖 — https://api.crossref.org/prefixes/10.26434/works?filter=type:posted-content,from-posted-date:2026-06-01,until-posted-date:2026-09-26,has-abstract:true&rows=0 （及同期总量、2025 年同口径）[LIVE]
- [N138] Crossref：PRB ISSN 切换年份 — https://api.crossref.org/journals/1098-0121/works?filter=from-pub-date:2015-01-01,until-pub-date:2015-12-31&rows=0 （及 2016 年，与 2469-9950 的 2015、2016 年同口径）[LIVE]

## 核验记录

> **核验人**：对抗式事实核验员（Verify 角色，opus5.5-survey 批次）。**核验日期**统一记为 2026-09-26（UTC；arXiv、zbMATH OAI 的 `responseDate` 均为 2026-09-26T19Z 前后）。
>
> **方法**：默认怀疑，优先一手来源。
> - 官方文档与条款页：WebFetch，WebFetch 被拒时改用 curl。
> - 官方接口实测：arXiv OAI、Crossref、DataCite、OpenAlex、INSPIRE、APS Harvest、SCOAP3、zbMATH、Numdam、OSTI.GOV、Europe PMC。
> - GitHub 元数据与源码：`gh api`，只读。
>
> **请求纪律**：
> - UA 为诚实的 `PaperCrawler-Verify/0.1 (personal research tool; survey fact-check)`，不带邮箱，因此 Crossref 走公共池。
> - 网页与 robots.txt 每站点 1–3 次，同站间隔 ≥2.5 s；arXiv OAI 3 次、arXiv Query API 1 次，间隔 >3 s。
> - Crossref API 约 40 次，串行、间隔 ≥2.5 s，对 429 做 8 s 退避重试；OpenAlex 7 次。
> - 遇 Cloudflare、Radware、Akamai 挑战或 nginx 403 即停，不重试、不绕过。
> - 未使用任何凭证，未下载论文全文。对 IOP RSS、PubChem PUG-REST 等 robots 禁区路径**未发出任何请求**。
>
> **前次中断检查**：本文此前没有核验记录节，全文也没有核验者留下的"核验补充""核验修正"类标记，未发现前次中断留下的半截修改。附属 CSV 中 107 行刊级数值（总 DOI / 2025 年 DOI / 摘要覆盖）与正文 §2.8 逐行比对，0 处不符；按出版商重算 §2.4 的区间，也与正文一致。
>
> **结论口径**：
> - **确认**：一手来源与原文一致。
> - **修正**：原文有误、口径不当，或原标 ⚠ 的条目经核验得出结论；均已就地改正。
> - **核验补充**：原文缺失的重要事实或条目，已补入正文。
> - **未核验**：仍无可靠一手来源，正文保留 ⚠ 或 [SEC]。
> - **删除**：查无实据。本轮 0 条，被抽查的仓库、论文、产品与公告都真实存在。
>
> **对设计阶段最承重的修正**：
> 1. Springer Nature 的 TDM API 另行收费。
> 2. AIP 的 S2O 试点已在 2025 年底结束。
> 3. Crossref 限额按请求类型分档，公共池列表查询只有每秒 1 次。
> 4. MSC2020 为 CC BY-NC-SA 4.0。
> 5. SCOAP3 对 PRL、PRD、PRC 只做部分覆盖。

### A. 接口、协议与限速

| 断言 | 结论 | 依据来源 URL | 核验日期 |
|---|---|---|---|
| arXiv OAI 支持 `group:archive:category` 三级 set；ListSets 共 183 个；`math:math:AG` 在 2026-09-23 至 09-24 返回 181 个标识符（含 0810.0442） | 确认；补充：183 个中 9 个物理单体 archive 各重复一次，去重后 174 个 | https://oaipmh.arxiv.org/oai?verb=ListSets ；https://oaipmh.arxiv.org/oai?verb=ListIdentifiers&metadataPrefix=oai_dc&set=math:math:AG&from=2026-09-23&until=2026-09-24 | 2026-09-26 |
| 理科叶子分类：数学 32 个，物理 51 个（6+9+5+22+9） | 确认（按 ListSets 前缀逐一计数） | https://oaipmh.arxiv.org/oai?verb=ListSets | 2026-09-26 |
| v1 推导出的 `cond-mat`、`hep-th` 不在 ListSets；"旧名是否被接受 ⚠ 未测" | 修正（⚠→已测）：`set=cond-mat` 返回 `badArgument`（Set does not exist） | https://oaipmh.arxiv.org/oai?verb=ListIdentifiers&metadataPrefix=oai_dc&set=cond-mat&from=2026-09-23&until=2026-09-23 | 2026-09-26 |
| 分类别名 math.MP≡math-ph、math.IT≡cs.IT、math.ST≡stat.TH、cs.NA≡math.NA（原标 ⚠） | 修正（⚠→确认）：官方分类表逐条确认；补 q-fin.EC≡econ.GN、cs.SY≡eess.SY | https://arxiv.org/category_taxonomy | 2026-09-26 |
| OAI datestamp 为记录最后修改时间；格式为 oai_dc、arXiv、arXivRaw | 确认；补充：OAI 服务 2025-03 重写并更换基址，v1 adapter 已用新域 | https://info.arxiv.org/help/oa/index.html | 2026-09-26 |
| arXiv API ToU：每 3 秒 1 次、单连接、所有机器合计；元数据 CC0；未经许可不得自行存储并提供 e-print | 确认 | https://info.arxiv.org/help/api/tou.html | 2026-09-26 |
| DataCite 前缀 10.48550 共 3,180,774 个 DOI | 确认（数字完全一致） | https://api.datacite.org/dois?query=prefix:10.48550&page%5Bsize%5D=1 | 2026-09-26 |
| Crossref 公共池 limit 5 与姊妹文档的 limit 1"说明限额是动态的" | **修正**：2025-12-01 起按请求类型分档，公共池单条 5 次/秒、列表 1 次/秒，并发 1；polite 池 10/3 次/秒，并发 3。实测 `public-single`=5，`public-array`=1 | https://www.crossref.org/blog/announcing-changes-to-rest-api-rate-limits/ ；https://www.crossref.org/documentation/retrieve-metadata/rest-api/access-and-authentication/ ；https://api.crossref.org/works?filter=prefix:10.1103,from-created-date:2026-09-25&rows=5 | 2026-09-26 |
| Crossref 摘要覆盖：JACS 0.10、Adv. Math. 0.00、PRL 0.29、G&T 0.00、Nature 0.12、NJP 0.99；§2.8 的 107 行刊级数值 | 确认（6 刊重查一致；CSV 与正文逐行比对 0 处不符） | https://api.crossref.org/journals/0002-7863 ；https://api.crossref.org/journals/0001-8708 ；https://api.crossref.org/journals/0031-9007 ；https://api.crossref.org/journals/1465-3060 ；https://api.crossref.org/journals/0028-0836 ；https://api.crossref.org/journals/1367-2630 | 2026-09-26 |
| Crossref 刊记录数据错误：PLMS e-ISSN 为 `1234-5678`；MNRAS 刊级 e-ISSN 为 1365-8711；GRL 的 p/e 颠倒；PRD 刊记录挂 1550-7998/1089-4918 | 确认 | https://api.crossref.org/journals/0024-6115 ；https://api.crossref.org/journals/0035-8711 ；https://api.crossref.org/journals/0094-8276 ；https://api.crossref.org/journals/2470-0010 | 2026-09-26 |
| PRB ISSN 别名窗口：2010-06 旧 ISSN 531 条、新 ISSN 0 条；2024-06 新 ISSN 410 条、旧 ISSN 0 条 | 确认（1098-0121、1550-235X、2469-9950、2469-9969 四个 ISSN 全部重查一致） | https://api.crossref.org/journals/1098-0121/works?filter=from-pub-date:2010-06-01,until-pub-date:2010-06-30&rows=0 ；https://api.crossref.org/journals/2469-9950/works?filter=from-pub-date:2024-06-01,until-pub-date:2024-06-30&rows=0 | 2026-09-26 |
| PRB ISSN"切换年份 ⚠ 未逐年核验" | 修正（⚠→已核验）：切换发生在 2016 年，2015 年只有旧 ISSN（5,001 条），2016 年只有新 ISSN（5,486 条）；其他 APS 刊仍未逐刊核验 | https://api.crossref.org/journals/1098-0121/works?filter=from-pub-date:2015-01-01,until-pub-date:2015-12-31&rows=0 ；https://api.crossref.org/journals/2469-9950/works?filter=from-pub-date:2016-01-01,until-pub-date:2016-12-31&rows=0 | 2026-09-26 |
| APS 新 DOI 为不透明后缀（`10.1103/fxpf-vzxx`），落地 `link.aps.org/doi/…` | 确认 | https://api.crossref.org/journals/0031-9007/works?sort=created&order=desc&rows=3 | 2026-09-26 |
| APS Harvest：`/v2/journals/articles`，`per_page` ≤100，`Link` 分页，JSON/BagIt/PDF/XML，JWT/IP/CHORUS；OA 集免认证；实测 31 页 × 2 条，字段含 abstract、PhySH、arXiv 号、CC BY 4.0 | 确认 | https://harvest.aps.org/docs/harvest-api ；https://harvest.aps.org/v2/journals/articles?from=2026-09-20&until=2026-09-21&set=openaccess&per_page=2 | 2026-09-26 |
| APS RSS 为 RDF/RSS 1.0、`updatePeriod=hourly`、"Personal use only" | 确认 | http://feeds.aps.org/rss/recent/prl.xml | 2026-09-26 |
| INSPIRE：每 IP 每 5 秒 15 次，超限 429，被拒请求也计入；`size` ≤1000；单查询 ≤10,000；9 类记录；元数据多数 CC0；`q=t higgs` 共 24,879 条 | 确认 | https://github.com/inspirehep/rest-api-doc/blob/master/README.md ；https://inspirehep.net/api/literature?sort=mostrecent&size=1&q=t%20higgs&fields=titles,dois,arxiv_eprints,created | 2026-09-26 |
| ADS API：Bearer token；"多数端点每日 5,000 次"；UTC 午夜重置 | 确认；措辞修正：README 写的是"每个端点单独限速"，5,000 是以 search 为例的数值 | https://github.com/adsabs/adsabs-dev-api | 2026-09-26 |
| zbMATH 条款（2021-06 版）：CC BY-SA、要求"reasonable rate"、可限流或封禁；OAI earliestDatestamp 1755、粒度到秒 | 确认；补充：条款原地址 307 跳转到 `/v1/static/…` | https://api.zbmath.org/v1/static/terms-and-conditions.html ；https://oai.zbmath.org/v1/?verb=Identify | 2026-09-26 |
| SCOAP3 repo：API `count` 87,667；全文 CC BY、元数据 CC0；2014-02 上线；新库 SCOAP3/scoap3（Django，MIT），scoap3-next 已归档 | 确认（`count` 现为 87,669，持续增长；样本记录为 Chinese Physics C、CC-BY-3.0） | https://repo.scoap3.org/api/records/?page_size=1 ；https://scoap3.org/scoap3-repository/ ；https://github.com/SCOAP3/scoap3 | 2026-09-26 |
| Numdam OAI：baseURL `http://www.numdam.org/oai`，earliestDatestamp 2018-10-09；robots Crawl-delay 2 | 确认 | https://www.numdam.org/oai/?verb=Identify ；https://www.numdam.org/robots.txt | 2026-09-26 |
| OpenAlex：单实体查询 `x-ratelimit-cost-usd: 0`，匿名每日 1,000 credits；IHÉS 的 host 仍为 Springer Nature | 确认；补充：列表查询每次计 1 credit（0.0001 美元） | https://api.openalex.org/sources/issn:0073-8301 ；https://api.openalex.org/works?filter=primary_location.source.issn:0073-8301&per_page=1 | 2026-09-26 |
| PubChem robots `*` 组禁 `/rest/pug/`；"数值限额 ⚠ 未核验" | 确认 robots；核验补充：PubChem 团队 2019 年论文给出每秒 ≤5 次、每分钟 ≤400 次、每分钟运行时间 ≤300 s；现行文档仍未直读，现值 ⚠ | https://pubchem.ncbi.nlm.nih.gov/robots.txt ；https://europepmc.org/article/PMC/PMC6688265 | 2026-09-26 |

### B. 政策、条款与许可

| 断言 | 结论 | 依据来源 URL | 核验日期 |
|---|---|---|---|
| SN OA API：免费档每日 500 次、每分钟 100 次；Premium 每日 10,000 次、每分钟 300 次 | 确认 | https://datasolutions.springernature.com/products/open-access/ | 2026-09-26 |
| SN："订阅机构经 API 做 TDM 不另收费"；直接下载每秒 1 次、API 每分钟 150 次 | **修正**：TDM 权利（直接下载，每秒 1 次）不另收费；同页写明 SN 的 TDM API 另行收费，每分钟 150 次指付费 TDM API | https://www.springernature.com/gp/researchers/text-and-data-mining | 2026-09-26 |
| SN：TDM 流量的 UA 须含 `TextDataMining`，此类流量从 COUNTER 报告剔除 | 确认 | https://support.springernature.com/en/support/solutions/articles/6000251800-text-and-data-mining-tdm | 2026-09-26 |
| SN API 条款三点（TDM 内容只放机构内部服务器、不得让第三方访问、不得用多账号或多 key 规避限额），原文"本文未独立复核" | 修正（→已核验）：一手条款确认三点；补充：网站摘要只授予个人使用许可，未经许可不得商用 | https://dev.springernature.com/terms-conditions/ | 2026-09-26 |
| SN Metadata API 免费档未给数字、字段含 Abstract；支持页：Metadata 近 1,200 万文档、OA 46 万多份 | 确认 | https://datasolutions.springernature.com/products/meta-data/ ；https://support.springernature.com/en/support/solutions/articles/6000195668-springer-nature-link-api-details | 2026-09-26 |
| link.springer.com：`*` 为 `Disallow: /` 加白名单，`/search.rss` 不在白名单，ClaudeBot 等具名；link 与 nature.com 的 TDMRep 为 `tdm-reservation: 1`，策略要求 `obtainConsent` | 确认 | https://link.springer.com/robots.txt ；https://link.springer.com/.well-known/tdmrep.json ；https://www.nature.com/.well-known/tdmrep.json ；https://dev.springernature.com/tdm/SNTDMPolicy.json | 2026-09-26 |
| IOP：robots `*` 为 `Disallow: /`，ClaudeBot、anthropic-ai 具名；政策 2026-07 版：订阅内容仅限非商业 TDM、邮件 contentsupport@ 申请、SFTP 交付、API 需另签协议、平台屏蔽系统化下载 | 确认；核验补充：API、feed、MCP server/connector、自动化 agent 等机器对机器访问都须另签协议；元数据 XML 免费、全文可能收费 | https://iopscience.iop.org/robots.txt ；https://ioppublishing.org/legal/textanddataminingpolicy/ | 2026-09-26 |
| APS robots：Last-Modified 2026-09-23；`*` 只禁 /search、/account、/login；2014 年起的 `Disallow: /` 于 2026-08 撤除；文件自述 CF 托管前置块（含 ClaudeBot 禁列与 Content-Signal） | 确认（文件注释原文） | https://journals.aps.org/robots.txt | 2026-09-26 |
| APS ToS 禁止系统化下载与 robots/网络加速器；APS Data Sets 45 万多篇、1893 年起、仅限申请人及所列合作者 | 确认；补充：条款页署 2017-12，未单列 TDM | https://journals.aps.org/info/terms.html ；https://journals.aps.org/datasets | 2026-09-26 |
| Cambridge ToU：可做非商业 TDM；个人或集体每小时下载超过 500 个 PDF 可撤销访问；平台监控下载 | 确认；补充：条款页署 2025-03 更新 | https://www.cambridge.org/core/legal-notices/terms | 2026-09-26 |
| Elsevier：开发者门户自助注册 API key，限非商业；T&F：订阅者做非商业 TDM 不另收费，须邮件报备，遵循 STM 模型许可；ACS：TDM 为付费方案，按范围、时长、频率与交付方式计价，交付 JATS/BITS XML | 确认 | https://www.elsevier.com/about/policies-and-standards/text-and-data-mining ；https://taylorandfrancis.com/our-policies/textanddatamining/ ；https://solutions.acs.org/solutions/text-and-data-mining/ | 2026-09-26 |
| robots 抽查：Atypon 族（Wiley、T&F、WSP、ChemRxiv、ESSOAr）禁 `/rss` 与 `/action`，Crawl-delay 1；SIAM、Science、PNAS 明确 `Allow: /action/showFeed`；Science 具名 anthropic-ai，PNAS 只具名 GPTBot；OUP 无 AI 条目；De Gruyter 依 §44b 保留商业 TDM；MathSciNet `Disallow: /`、Crawl-delay 10；Research Square `*` 禁 `/api/` 并具名 ClaudeBot；Project Euclid、PoS 的 Crawl-delay 为 10、5 | 确认（逐站重取 robots.txt） | https://onlinelibrary.wiley.com/robots.txt ；https://www.tandfonline.com/robots.txt ；https://www.worldscientific.com/robots.txt ；https://chemrxiv.org/robots.txt ；https://essopenarchive.org/robots.txt ；https://epubs.siam.org/robots.txt ；https://www.science.org/robots.txt ；https://www.pnas.org/robots.txt ；https://academic.oup.com/robots.txt ；https://www.degruyterbrill.com/robots.txt ；https://mathscinet.ams.org/robots.txt ；https://www.researchsquare.com/robots.txt ；https://projecteuclid.org/robots.txt ；https://pos.sissa.it/robots.txt | 2026-09-26 |
| Optica：robots 具名 ClaudeBot 等 30 多个 UA，`*` 只禁 ViewMedia 等；数据条款保留 TDM 与 AI 训练权利 [SEC N17] | 确认 robots；条款仍未核验（条款页 302 到 Radware 挑战，已补入 §2.5 防护矩阵） | https://opg.optica.org/robots.txt ；https://opg.optica.org/include/datasets_termsofuse.cfm | 2026-09-26 |
| 二手政策转述：AIP 个案授权、ACS/SIAM/De Gruyter"不允许（2023-03）"、RSC 需提前申请、Science 要求"reasonable rate and speed"（Cranfield）；WSP 短时 200 次下载即切断（ASU） | 确认转述准确（两份指南分别更新于 2026-09-01、2026-07-06），但仍属二手来源 | https://library.cranfield.ac.uk/text-and-data-mining/publisher-policies ；https://libguides.asu.edu/textanddatamining/datasources | 2026-09-26 |
| PNAS 6 个月后经 PMC 免费 [SEC] | 修正（SEC→一手确认）：NLM PMC 刊表记 Release Delay 6 months、All articles | https://cdn.ncbi.nlm.nih.gov/pmc/home/jlist.csv | 2026-09-26 |
| AMS 期刊超过 5 年的往期免费 [SEC] | 未核验：ams.org 官方域名的搜索摘要一致，但页面 403；补充：OpenAlex 未把 JAMS 2020 年卷标为 OA，发现链不可依赖 | https://www.ams.org/publications/journals/subscriberinfo ；https://api.openalex.org/works?filter=primary_location.source.issn:0894-0347,publication_year:2020&group_by=open_access.oa_status | 2026-09-26 |
| PhySH 为 CC0，GitHub 提供 JSON、NT、RDF、TTL | 确认（LICENSE.md 为 CC0 1.0；GitHub API 显示 NOASSERTION） | https://github.com/physh-org/PhySH | 2026-09-26 |
| MSC 许可"⚠ 本轮未核验" | **修正**（→已核验）：MSC2020 由 MR 与 zbMATH 以 CC BY-NC-SA 4.0 联合发布 | https://msc2020.org/ | 2026-09-26 |
| zbMATH Open KG：2026-07 统计、基于 2026-01 API dump；1.68 亿多三元组、400 万多出版物、300 万多条评论、6.7K+ MSC 类、3 万多条软件；配套论文 arXiv:2609.00969 | 确认；补充：README 声明 KG 内容为 CC BY-SA 4.0（仓库无 LICENSE 文件） | https://github.com/zbMATHOpen/zbmath-open-kg ；https://arxiv.org/abs/2609.00969 | 2026-09-26 |

### C. 2025–2026 变化与机构动态

| 断言 | 结论 | 依据来源 URL | 核验日期 |
|---|---|---|---|
| arXiv 自 2026-07-01 起成为独立非营利机构（博客 2026-04-02），公告未提 API 或费用变化 | 确认 | https://blog.arxiv.org/2026/04/02/arxiv-is-becoming-an-independent-nonprofit/ | 2026-09-26 |
| arXiv 2026-04 超过 300 万篇；2026 年 3、5、6 月投稿量为 30,045、31,604、32,040 篇 | 确认 | https://blog.arxiv.org/2026/07/09/arxiv-now-hosts-over-3-million-articles/ | 2026-09-26 |
| ChemRxiv：2026-01-14 停止收稿，01-21 在 Wiley Research Exchange 上线，36,000 多篇迁移，旧 DOI 继续解析，并重新向 Crossref 登记 | 确认（FAQ 未提新平台 API） | https://connect.acspubs.org/chemrxiv-migration-FAQ | 2026-09-26 |
| ChemRxiv 新 DOI 形如 `10.26434/chemrxiv.15009478/v1`；Crossref 登记 2025 年 10,085 条、2026 年至今 9,906 条 | 确认；核验补充：Crossref 摘要覆盖约 98%（2026-06 至 09：4,603/4,678；2025 年 10,085/10,085） | https://api.crossref.org/prefixes/10.26434/works?filter=type:posted-content,from-posted-date:2026-01-01&rows=3&sort=created&order=desc ；https://api.crossref.org/prefixes/10.26434/works?filter=type:posted-content,from-posted-date:2026-06-01,until-posted-date:2026-09-26,has-abstract:true&rows=0 | 2026-09-26 |
| paperscraper 依赖的 ChemRxiv 旧 API"能否继续使用 ⚠" | 修正（⚠→已核验）：2026-01-25 PR #99 遇 Cloudflare 后改走 Cambridge 端点；2026-02-24 PR #103 加入"403 时回退 Crossref 10.26434"的实现 | https://github.com/jannisborn/paperscraper/pull/99 ；https://github.com/jannisborn/paperscraper/pull/103 | 2026-09-26 |
| RSC：Silverchair 于 2026-02-26 公告承接 50 多种期刊，书籍平台自 2023 年起已在 Silverchair，未公布上线日期；pubs.rsc.org robots 已为 Silverchair 模板 | 确认（robots Last-Modified 2026-09-26） | https://www.silverchair.com/news/rsc-expands-partnership/ ；https://pubs.rsc.org/robots.txt | 2026-09-26 |
| RSC OA 路线从"2028 年全 OA"改为区域化模式 [原为 SEC 搜索摘要] | 确认（已直读 Chemistry World 2025-06-25 报道：原计划 58 种刊 2028 年前全 OA） | https://www.chemistryworld.com/news/royal-society-of-chemistry-changes-direction-on-open-access-rollout-following-community-feedback/4021761.article | 2026-09-26 |
| Royal Society：2025-12-02 在 Silverchair 上线；8 种订阅刊 2026 年走 S2O（2025-08-06 公告），"前提是门槛达成"；robots ⚠ 未测 | 确认；核验补充：2026-02-16 官方确认门槛达成；robots 为 Silverchair 模板 | https://www.silverchair.com/news/royal-society-publishing-launches/ ；https://royalsociety.org/news/2025/08/subscribe-to-open/ ；https://royalsociety.org/news/2026/02/subscribe-to-open-announcement/ ；https://royalsocietypublishing.org/robots.txt | 2026-09-26 |
| Publ. Math. IHÉS 迁至 Centre Mersenne：最新 DOI 为 `10.5802/pmihes.25–30`，Crossref publisher 为 MathDoc/Centre Mersenne；OpenAlex 仍标 Springer Nature | 确认 | https://api.crossref.org/journals/0073-8301/works?sort=created&order=desc&rows=5 ；https://api.openalex.org/sources/issn:0073-8301 | 2026-09-26 |
| APS Open Science：2025-12-03 公告，新 OA 刊，CC BY 4.0，2026-02 下旬开放投稿 | 确认 | https://www.aps.org/about/news/2025/12/open-science-expand-global-participation | 2026-09-26 |
| EMS Press：2026-02-12 公告 22 种 S2O 刊连续第三年全 OA，2026 年卷为 CC BY 4.0；S2O 按年生效，往期仍在订阅墙后；2026-03-30 公布 L2O，FoCM 与 Archiv der Math. 自 2027-01-01 起在 EMS Press 出版；robots `Allow: /` | 确认 | https://ems.press/updates/2026-02-12-2026-s2o-announcement ；https://ems.press/subscribe-to-open ；https://ems.press/updates/2026-03-30-ems-press-unveils-l2o ；https://ems.press/robots.txt | 2026-09-26 |
| AIP：JAP 与 PoP 在 2025 年经 S2O 全 OA，"2026 年是否延续 ⚠" | **修正**：S2O 覆盖 2024、2025 两年；AIP 2025-10-29 宣布试点于 2025 年底结束，2026 年起转入 Author Select / AIP Fusion / R&P，不再按 S2O 整刊开放 | https://publishing.aip.org/about/news/evolving-our-open-access-strategy-aip-publishing-concludes-the-subscribe-to-open-pilot/ ；https://publishing.aip.org/about/news/two-aip-publishing-journals-now-open-access-under-subscribe-to-open-pilot/ | 2026-09-26 |
| JHEP、PLB、NPB、EPJC 为 SCOAP3 刊（原标"⚠ 刊表以 scoap3.org 为准"） | 修正（⚠→已核验）：SCOAP3 2025–2027 共 11 刊，这 4 刊为 100% 覆盖；PRL 13%、PRD 56%、PRC 9%、PTEP 51%、CPC 44%、APPB 36%、AHEP 68% 为部分覆盖 | https://scoap3.org/journals-2025-2027/ | 2026-09-26 |
| arXiv:2609.18091（Bartlett、Kundu、Accomazzi、Kurtz，2026-09-16）确认 ADS 向 SciX 过渡 | 确认 | https://arxiv.org/abs/2609.18091 | 2026-09-26 |
| ADS→SciX 于 2026-11-16 完成，账户、library 与 API 工具保留 [SEC] | 未核验（部分确认）：官方站点源码只写"今年秋季"切换，确认账户、设置、通知与 library 不变、旧链接重定向；具体日期与"API 不变"仍只见搜索摘要；scixplorer.org 直连返回 202 空响应 | https://github.com/adsabs/adsabs.github.io/blob/master/adstoscix/index.md ；https://scixplorer.org/adstoscix/ | 2026-09-26 |
| ESSOAr 迁移于 2026-05 完成 [SEC 维基百科] | 修正（口径）：维基百科的"2026-05"指 Authorea 迁移后暂停直接投稿的时间；ESSOAr 自身迁移月份仍未核验 | https://en.wikipedia.org/wiki/Authorea | 2026-09-26 |
| Project Euclid：Duke University Press 自 2022 年起独立运营；托管 35 家以上合作方的 100 多种出版物；80% 以上期刊文章开放 | 确认 | https://projecteuclid.org/about | 2026-09-26 |
| 16 个 GitHub 仓库的 star、许可、最近推送与归档状态（arxiv.py 1,548 到 arxiv-oaipmh 3） | 确认（全部与 `gh api` 一致）；补充 zbmath-open-kg 的许可口径 | https://github.com/lukasschwab/arxiv.py ；https://github.com/jannisborn/paperscraper ；https://github.com/ElsevierDev/elsapy ；https://github.com/SCOAP3/scoap3-next ；https://github.com/arXiv/arxiv-oaipmh （其余见 [N111]） | 2026-09-26 |

### D. 覆盖缺口（核验补充）

| 断言 | 结论 | 依据来源 URL | 核验日期 |
|---|---|---|---|
| 理科 L1 名录缺 MDPI（Molecules、Materials、Mathematics 等） | 核验补充：§2.2.1 新增 `mdpi` 行。Crossref 实测 2025 年 DOI 分别为 4,830、5,709、4,071，摘要与 licenses 均 1.00；MDPI OAI 本次 504 后超时，可用性未核验 | https://api.crossref.org/journals/1420-3049 ；https://api.crossref.org/journals/1996-1944 ；https://api.crossref.org/journals/2227-7390 ；https://oai.mdpi.com/oai/oai2.php?verb=Identify | 2026-09-26 |
| 理科 L2 缺 OSTI.GOV（DOE 资助成果库，有官方 API） | 核验补充：§2.2.3 新增 `osti_gov` 行（API 参数、分页头、fulltext 链接、robots 未禁 `/api/`）；数值限额与各篇许可未核验 | https://www.osti.gov/api/v1/docs ；https://www.osti.gov/about ；https://www.osti.gov/robots.txt | 2026-09-26 |
| 化学发现库 CAS SciFinder 未列入排除表 | 核验补充：§2.2.5 新增 `cas_scifinder` 行（条款禁止脚本批量抽取与自动化、禁止 AI 用途、每人至多存 5,000 条记录）；Reaxys 条款未核验 | https://web.cas.org/marketing/pdf/product-use-terms-academic-10-10-23.pdf | 2026-09-26 |
| 数学回溯库 EuDML、法国仓储 HAL 未提及 | 核验补充：EuDML 列为不优先（robots 与 Identify 均 403；集合陈旧的说法来自二手来源）；HAL 注明由聚合源主题 §2.2.18 覆盖 | https://initiative.eudml.org/oai-pmh-server ；https://eudml.org/oai/OAIHandler?verb=Identify ；docs/survey/sources/aggregators-repositories.md | 2026-09-26 |
