---
title: 来源调研：生命科学与心理学出版商、预印本与平台
status: draft
owner: opus5.5-survey
updated: 2026-09-26
---

# 来源调研：生命科学与心理学出版商、预印本与平台

> 定位：v2 重新设计调研阶段（Survey）的"来源"子报告之一，覆盖**生物/生命科学（以基础生命科学为主，含神经科学、计算生物学）与心理学（含认知科学）**的一级来源，以及这两个领域特有的二级基础设施（PubMed / PMC / Europe PMC 等）。通用聚合层（Crossref / OpenAlex / Semantic Scholar / Unpaywall / CORE）只写与本领域相关的用法，其余见 v1 勘察 [R74] 与同批 `aggregators-repositories.md`。
>
> **证据标记**：`[LIVE]` 表示 2026-09-26 本机实测（curl、API 调用，读取响应头或正文）；`[DOC]` 表示官方文档页（WebFetch 或 curl 读取正文）；`[v1]` 表示引用 v1 仓库已有勘察（注明原勘察日期）；`[3P]` 表示第三方来源（GitHub issue、维基、检索摘要）；`⚠ 未核验` 表示今日无法核实，并写明原因。`[R#]` 指向 §5 参考来源，未另注的访问/核验日期均为 **2026-09-26**。
>
> **合规口径**（贯穿全文，涉及处以【合规】标注）：只经合法来源与用户自有授权凭证获取；遵守 robots.txt/ToS，保守限速，诚实可识别 UA；不绕付费墙、CAPTCHA 或 WAF 挑战；不集成 Sci-Hub/LibGen 等盗版源，不冒充；Google Scholar 不做自动化主源；v2 为多用户平台后，auth-gated 全文**不得在用户间共享或再分发**，每位用户只能用自己的凭证取回并私有存放。

## 0. 结论速览

1. **两个学科的元数据骨干不一样。** 生命科学有 NCBI/EBI 公共基础设施：PubMed 有 4,000 万以上引文和年度 baseline + 日更文件，Europe PMC 已收录 1,247,001 篇预印本，并支持章节级、实体级检索 [LIVE]。它的 L2 比 Crossref 更适合作检索与摘要骨干。心理学的情况相反：PubMed 只覆盖 MEDLINE 收录的一部分刊，2025 年 *J Mem Lang* 只有 8 篇，AMPPS 与 CogSci 论文集都是 0 [LIVE]，所以心理学必须以 Crossref 为骨干、PubMed 为增强，预印本走 PsyArXiv/OSF。
2. **Crossref 摘要覆盖在本领域严重不均。** Elsevier/Cell Press、APA、T&F 的样本刊 `abstracts-current` 都是 **0%**，Nature 系为 12–47%，eLife、SAGE、OUP、MDPI、Frontiers、PLOS 在 82–100% [LIVE]。推荐系统需要的摘要必须经 PubMed/Europe PMC 补全。核验补充：摘要为 0 不等于没有 OA。Cell Press 与 Elsevier 心理学刊 2026 年带即时 CC 许可的比例约 36–53%（*Cell* 241/463），属于混合 OA（§2.4.1）。
3. **2025–2026 年有几项必须写进设计的时效变化。**
   - bioRxiv/medRxiv 于 2025-03-11 移交非营利组织 openRxiv [R1]，**2025-12-01 起启用新 DOI 前缀 10.64898**（Crossref member 54368 "openRxiv"）[R2][LIVE]。**核验修正**：旧 `10.1101/…` 预印本 DOI 的 Crossref 记录已整体转入 openRxiv 名下（记录的 `prefix`/owner prefix 字段为 10.64898、member 54368；该 member 共 441,217 条 posted-content，CSHL member 246 只剩 34 条）。所以 Crossref 过滤器 `prefix:10.1101` 已查不到任何 bioRxiv/medRxiv 记录，这不等于"旧前缀停止新增"。一条 `prefix:10.64898`（或 `member:54368`）查询即可覆盖新旧两种 DOI 字符串 [LIVE R13][LIVE R81]。
   - **`api.biorxiv.org/details` 在 2026-09-26 对 5 种 URL 形态都返回 HTTP 200、正文 0 字节**，同日有第三方 issue 报告相同现象，未见官方退役公告 [LIVE][R10]。**核验补充**：同日 19:2x UTC 复测，`/details` 仍为空体，**`/funder` 也返回 200 + 0 字节**（含文档示例 URL）；`/pubs`、`/pub`、`/publisher`、`/sum`、`/usage` 正常。
   - **PMC 于 2026-08-24 那一周删除全部旧版 Article Dataset 文件，OA Web Service 于 2026-08-25 下线。** 官方声明只有 Cloud(S3)、OAI-PMH、E-utilities、BioC 四个通道可用于自动化获取，其他方式的系统性获取被禁止 [DOC R33–R37]。
   - BMC 全部期刊域名与 EMBO Press 已 301 到 `link.springer.com` [LIVE]。*Child Development* 的 DOI 所有权（含历史 `10.1111/cdev.*`）已转到 OUP [LIVE]。
   - NIH 2024 Public Access Policy（AAM 零 embargo 进入 PMC）自 2025-07-01 生效 [DOC R41]。
   - Europe PMC 的 SSRN 预印本收录停在 2023-10-28 [LIVE]。核验补充：之后只有 1 条补录，`PPR602478` 的 firstPublicationDate 为 2024-08-06，是一篇 2022 年旧稿。
4. **出版商站点大面积对程序化访问设卡。**
   - 本日实测：Cloudflare 挑战（europepmc.org、cambridge.org、jneurosci.org 连 robots.txt 都挑战）、Akamai 403（preprints.org、mdpi.com）、Imperva/Incapsula（apa.org）、CloudFront WAF（escholarship.org 网页）、reCAPTCHA（NCBI Bookshelf）、TLS 握手中断（journals.sagepub.com、ssrn.com）[LIVE]。
   - psycnet.apa.org 与 sciencedirect.com 的 robots 都是 `User-agent: *` 全禁 [LIVE]。
   - nature.com、link.springer.com、cell.com、science.org、psycnet、bioRxiv、Research Square 都点名禁止 ClaudeBot 或 anthropic-ai 等 AI 爬虫 [LIVE]。
   - **v2 服务端只能依赖 L2 开放通道、官方 API 与用户侧自有会话。**
5. **"最新论文"通道要按 feed 逐条做 robots 判定。**
   - 实测可用且 robots 允许的 eTOC：Cell Press `/{journal}/current.rss`、PNAS/Science `/action/showFeed`（robots 有 `Allow: /action/showFeed`）、Nature `/{journal}.rss`、Wiley `/feed/{issn}/most-recent`、T&F `/feed/rss/{code}`、OUP `/rss/site_*`、Frontiers、eLife、PLOS [LIVE]。
   - 不可用：Springer Link `search.rss` 不在 robots 允许清单内，PubMed `/rss` 被 robots 禁，APA 全站禁，Annual Reviews/PeerJ 的 RSS 被 CF 挑战，MDPI 被 Akamai 拒，CSHL 的 RSS 跳转登录 [LIVE]。
   - 兜底一律用 Crossref `from-index-date`、Europe PMC `FIRST_IDATE`、PubMed EDAT。
6. **OA 全文主通道已经明确，但必须按条目许可证门控。**
   - 通道：PMC S3（约 800 万个文章版本，每个版本的 JSON 带 `license_code`，README 明文"只再分发许可允许再分发的数据"）、Europe PMC `fullTextXML`、bioRxiv/medRxiv S3（requester-pays，月更，明文"不作为再分发来源"）、PLOS 与 eLife 官方 API [DOC/LIVE]。
   - openRxiv 2026-08 的许可分布：CC BY 36.7%、CC BY-NC-ND 29.2%、**"no reuse" 约 19%**（bioRxiv 837 + medRxiv 241 条，占当月 5,693 条）[LIVE]。
   - **多用户共享缓存必须做许可证门控。**
7. **订阅全文只能用个人凭证。** Springer Nature TDM 条款要求内容存放在"无第三方访问的安全内部服务器"，**且只在 TDM 项目期间保存**（核验补充）。API 限 150 请求/分钟，直接下载 ≤1 请求/秒 [DOC R43]。Elsevier Article Retrieval API 和 Wiley TDM token 均为个人或机构授权 [v1]。Elsevier 配额经官方 API key 设置页复核：每周 50,000 次、10 请求/秒，TDM 专用 key 不限周配额 [DOC R77]。凭证库、配额与存储都必须按用户隔离。
8. **本领域有高价值的质量和关系信号。**
   - eLife Assessment 结构化词表：significance 5 级 × strength 6 级 [DOC]。
   - Europe PMC `HAS_VERSION_EVALUATIONS`：41,177 篇预印本带评审。
   - 预印本到正式版的链接：bioRxiv `/pubs`、OSF `attributes.doi`、Crossref `relation.is-preprint-of`（Preprints.org 样本 33%、PsyArXiv 30%）、EPMC `HAS_PUBLISHED_VERSION`。
   - PMC `is_retracted` [LIVE/DOC]。
   - 这些可直接作为推荐特征和过滤条件。
9. **主题树以 MeSH 2026 为主干**：免费、有树号、有 RDF/JSON 查询 API、每年版本化，Psychology = `F04.096.628` [LIVE]。APA Thesaurus 为 APA 专有且官方页面无法程序化读取，不建议嵌入。心理学用 MeSH F 分支、PsycInfo 分类码（22 大类/135 子类，⚠）、Cognitive Atlas（API 可用）、OSF/bioRxiv/eLife 自带学科做 crosswalk。
10. **优先级。**
    - **P0**：`pubmed`、`europe_pmc`、`pmc`、`biorxiv`/`medrxiv`（元数据经 Crossref + EPMC 路由）、`psyarxiv`、`arxiv_qbio`（v1 adapter 零成本扩展）、PNAS（全文经 PMC）。
    - **P1**：PLOS、eLife、Springer Nature、Cell Press 与其他 Elsevier 刊（复用 v1 `elsevier_sd`）、Wiley 与 OUP（复用 v1）、Frontiers、MDPI（OAI）、SAGE/APS、CogSci（OAI）、Research Square/Preprints.org（仅 L2）、Annual Reviews。
    - **仅元数据**：APA PsycNet、Science 主刊（全文按用户）、SSRN Sneak Peek。
    - **排除**：盗版源、Google Scholar 自动化、PsycInfo 自动抓取、任何绕挑战手段。

## 1. 调研范围与方法

### 1.1 范围

| 类别 | 本文覆盖 | 不覆盖（交由他处） |
|---|---|---|
| 预印本 | bioRxiv、medRxiv（openRxiv）、Research Square、PsyArXiv 及 OSF Preprints 其他社区、Preprints.org、SSRN 生医通道（Cell Press Sneak Peek / Preprints with The Lancet）、Authorea、arXiv q-bio、F1000 系、PsychArchives | ChemRxiv（化学，见 `natural-sciences.md`）、经济金融工作论文（见 v1 与 `social-sciences-econ-fin-mgmt.md`） |
| 开放/检索基础设施 | PubMed E-utilities 与 baseline、PMC（OAI-PMH/S3/BioC/ID Converter）、Europe PMC（REST/全文/注释）、NCBI 限速与 API key 规则 | Crossref/OpenAlex/S2/Unpaywall/CORE 的通用细节（v1 [R74]、`aggregators-repositories.md`） |
| 出版商/平台 | Cell Press/Elsevier、Nature Portfolio/Springer Nature Link（含 BMC、EMBO Press）、AAAS Science、PNAS、eLife、PLOS、Frontiers、MDPI、PeerJ、OUP、Cambridge、Annual Reviews、APA PsycNet、SAGE（APS 期刊）、Taylor & Francis、Wiley、CSHL Press、SfN | 临床医学大刊（NEJM/Lancet/JAMA/BMJ）只在 medRxiv/EPMC 处提及 |
| 会议/论文集 | CogSci Proceedings（eScholarship）、PSB；ISMB/RECOMB 仅作映射说明 | CS 类会议（v1 已覆盖） |
| 分类体系 | MeSH、APA Thesaurus 与 PsycInfo 分类码、bioRxiv/medRxiv/eLife/arXiv q-bio 学科、Cognitive Atlas | OpenAlex Topics 全量（其他调研） |

### 1.2 请求纪律与证据分级

- **UA**：统一使用 `PaperCrawler-survey/0.2 (site survey; personal research)`，**不携带用户邮箱**（隐私约束），因此 Crossref 落在 public 池。响应头实测为 `x-rate-limit-limit: 5`、`x-rate-limit-interval: 1s`、`x-concurrency-limit: 1`、`x-api-pool: public-single` [LIVE]。
- **顺序与间隔**：先取 robots.txt；同主机请求间隔 ≥1–3 s；脚本化探针串行执行，Crossref 约 1 请求/1.1–1.3 s，NCBI 约 1 请求/0.6 s，低于 3 rps 上限。
- **遇阻处理**：遇到挑战页或 403 只记录一次后停，**不重试、不换 UA、不走代理绕过**。全程无登录、无 API key、无 cookie 注入。
- **诚实记录的偏差**：
  - 3 次 `api.biorxiv.org` 请求误用了 curl 默认 UA。该主机无 robots.txt（404）；但 `www.biorxiv.org` 的 robots 对 `curl` UA 全禁，此后全部改用显式 UA。
  - 首轮 Crossref 期刊探针的输入文件被同批另一调研 agent 覆盖（scratch 目录同名冲突），已在隔离目录全量重跑，文中数据均以重跑结果为准。
  - WebSearch 用了 5 次后，会话共享配额（200 次）耗尽，其余事实改由 WebFetch、curl、`gh api` 直接取证。
- **请求量**：直接 HTTP 请求约 480 次，其中脚本化元数据 API 约 350 次（Crossref 约 190、NCBI 约 120、DOAJ 约 60）；robots.txt 约 45 个主机；WebFetch 约 40 次；`gh api` 约 35 次。

### 1.3 过程记录（可复现）

| # | 时间窗（UTC，2026-09-26） | 工具 | 对象 | 检索式 / 请求要点 | 结果摘要 |
|---|---|---|---|---|---|
| 1 | 14:40–14:55 | 本地读档 | README、INDEX、catalog、site-survey、decision-log | — | v1 无生命科学与心理学来源；已有 `elsevier_sd`/`wiley`/`oup_silverchair`/`ssrn`/`arxiv`/`crossref` adapter |
| 2 | 14:55–15:00 | WebSearch ×5（第 6 次因配额耗尽失败） | 检索引擎 | ① `openRxiv bioRxiv medRxiv new organization 2025 announcement` ② `bioRxiv new DOI prefix 10.64898 December 2025 date-encoded suffix` ③ `api.biorxiv.org details endpoint empty response 2026` ④ `Research Square preprint platform API access Springer Nature 2025 2026` ⑤ `OSF API v2 rate limit throttling requests per hour preprints psyarxiv filter[provider]` ⑥ `Research Square API documentation JSON endpoint …`（失败） | 线索见 R1–R4、R10、R11、R17、R75 |
| 3 | 14:56–15:00 | curl | `api.biorxiv.org` | `/details/{server}/{from}/{to}/0/json` 5 种形态；`/pubs/biorxiv/2025-03-01/2025-03-02/0`；`/sum/m/json`；`/usage/m/medrxiv/json` | `/details` 5/5 返回 200 + 0 字节（15:43 复测仍如此）；`/pubs`、`/sum` 正常 |
| 4 | 14:57–15:00 | WebFetch | `api.biorxiv.org`、`biorxiv.org/tdm`、`medrxiv.org/tdm`、`/alertsrss`、`/about/FAQ` | 端点与 bulk 说明 | 7 个端点、S3 桶、许可 6 选 1、RSS 模式 |
| 5 | 15:00–15:05 | curl | Crossref `/prefixes/*`、`/works?filter=prefix:…,type:posted-content,from-posted-date:…` | openRxiv/CSHL/COS/MDPI/Research Square/Authorea/SSRN 前缀 | 月度量、许可分布、摘要覆盖、relation |
| 6 | 15:01–15:05 | curl | robots：biorxiv、medrxiv、researchsquare、preprints.org、osf.io、api.osf.io、europepmc.org、ebi.ac.uk、eutils/pubmed/pmc/www.ncbi | `GET /robots.txt` | 见 §2.9 |
| 7 | 15:02–15:03 | curl | `api.osf.io/v2/preprints/?filter[provider]=psyarxiv`、`/v2/providers/preprints/` | `page[size]`、`filter[date_created][gte]` | PsyArXiv `meta.total` 64,345；32 个 provider |
| 8 | 15:05–15:10 | curl | Europe PMC REST | `SRC:PPR`、`PUBLISHER:"…"`、`HAS_VERSION_EVALUATIONS:Y`、`FIRST_IDATE:[…]`；`/fields`；`/PMC12314748/fullTextXML`、`/supplementaryFiles`；annotations API | 预印本 1,247,001 篇；17 个预印本平台；字段 143 个（核验修正：原记"约 130"） |
| 9 | 15:05–15:12 | curl / WebFetch | E-utilities、PubMed FTP、NCBI Bookshelf、PMC `/tools/*` 6 页、NCBI Insights | `esearch` 读 `x-ratelimit-*`；FTP README | 3 rps 头；2026 baseline 1,334 文件；Bookshelf 返回 reCAPTCHA；PMC 2026-08 服务变更 |
| 10 | 15:08–15:12 | curl（批量） | 26 个出版商主机的 robots.txt | 用自写的最长匹配判定器检查 feed 与文章路径 | 见 §2.9 |
| 11 | 15:14–15:20 | curl / WebFetch | Springer Nature API（无 key）、SN TDM 页、PLOS API 与 FAQ、eLife API 与 assessments、MDPI OAI、Frontiers/PeerJ/eLife RSS、PNAS/Science 政策页 | — | SN 401；PLOS 限速原文；eLife 计数；MDPI OAI 可用；PNAS/Science 政策页 403 |
| 12 | 15:21–15:24 | curl | CSHL、BMC、SAGE、J Neurosci、EMBO 的 robots 与重定向；eScholarship OAI；MeSH 文件与 RDF API；APA；PsychArchives；Cognitive Atlas | — | BMC/EMBO 迁入 link.springer.com；CogSci OAI 21,720 条；apa.org Incapsula |
| 13 | 15:24–15:40 | Python 脚本（串行） | Crossref `/journals/{issn}` + `/journals/{issn}/works?filter=from-pub-date:2026-01-01`（57 刊）；E-utilities `esearch` 计数（57 刊 × PubMed/PMC）；DOAJ `/api/search/journals/issn:{issn}`（57 刊） | 每刊 1–2 次 | §2.8 映射表数据 |
| 14 | 15:33–15:42 | curl / gh | PMC ID Converter、BioC、OAI GetRecord、S3 README；各 feed；Crossref eISSN 复查与 `facet=license:*`；`gh api repos/…`；OSF 源码限速配置 | — | 见正文 |

**复现示例**（只读 GET，已于 2026-09-26 实测）：

```text
# bioRxiv/medRxiv 元数据兜底（Crossref；prefix 过滤按记录所有者匹配，10.64898 已含旧 10.1101 预印本 DOI）
https://api.crossref.org/works?filter=prefix:10.64898,type:posted-content,from-posted-date:2026-09-01,until-posted-date:2026-09-07&rows=500&select=DOI,abstract,group-title,license,posted,relation
# PsyArXiv 最新
https://api.osf.io/v2/preprints/?filter[provider]=psyarxiv&filter[date_created][gte]=2026-09-20&page[size]=100
# Europe PMC 增量（首次入索引日）与预印本评审信号
https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=FIRST_IDATE:[2026-09-24 TO 2026-09-25]&format=json&resultType=core&pageSize=1000&cursorMark=*
https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=SRC:PPR AND HAS_VERSION_EVALUATIONS:Y&format=json&resultType=idlist
# PubMed（按 MeSH 和 Entrez 日期）
https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term=psychology[mh]+AND+2026/09/01:2026/09/20[edat]&retmode=json&tool=<tool>
# PMC OAI-PMH（全文 JATS，仅限可再用许可的条目）
https://pmc.ncbi.nlm.nih.gov/api/oai/v1/mh/?verb=GetRecord&identifier=oai:pubmedcentral.nih.gov:12314748&metadataPrefix=pmc
# CogSci Proceedings（eScholarship OAI-PMH）
https://escholarship.org/oai?verb=ListRecords&metadataPrefix=oai_dc&set=cognitivesciencesociety
```

## 2. 主体内容

### 2.1 来源全景与分层

```text
L2-aggregator   PubMed(>4,000 万引文，MEDLINE+MeSH) · Europe PMC(期刊+1,247,001 预印本，章节/实体检索)
                · [通用层：Crossref / OpenAlex / S2 / Unpaywall，见 v1]
L2-repository   PMC(约 800 万文章版本，S3/OAI/BioC) · PsychArchives(ZPID, OAI) · eScholarship(OAI)
L1-preprint     bioRxiv · medRxiv (openRxiv) · Research Square · PsyArXiv + OSF 其他社区(32 provider)
                · Preprints.org · SSRN 生医通道 · Authorea · arXiv q-bio
L1-journal-platform  eLife(Reviewed Preprint 模式) · PeerJ · PNAS · F1000 系(发表后评审)
L1-publisher    Elsevier/Cell Press · Springer Nature(Nature/Springer/BMC/EMBO) · AAAS · PLOS · Frontiers
                · MDPI · OUP · Cambridge · Annual Reviews · APA · SAGE(APS) · T&F · Wiley · CSHL Press · SfN
L1-conference   CogSci Proceedings(eScholarship) · PSB · (ISMB→Bioinformatics 增刊, RECOMB→Springer LNCS)
分类体系         MeSH 2026 · APA Thesaurus/PsycInfo 分类码(专有) · 各平台学科 · Cognitive Atlas
```

**与 v1（CS/经济/金融）的结构性差异**：

1. 生命科学有政府/国际机构运营的高质量 L2（NCBI、EMBL-EBI），元数据（MeSH、出版类型、撤稿标记）和 OA 全文（PMC）都比 Crossref 更丰富，所以"聚合 API 为元数据主干"这一 D-005 原则在本领域要换主角。
2. 心理学更像社科：出版商集中（APA、SAGE/APS、Elsevier、Springer/Psychonomic、Wiley、T&F、Cambridge），APA 自有平台对自动化完全关闭，只能依赖 Crossref + 部分 PubMed + PsyArXiv。
3. 预印本生态在生命科学已成主流：openRxiv 称约 80% 手稿随后在期刊正式发表 [R2]。所以"预印本到正式版"的合并与版本追踪是一等公民。

### 2.2 预印本

#### 2.2.1 bioRxiv / medRxiv（openRxiv）

**概况与规模**

- 2025-03-11 起由独立非营利组织 openRxiv 运营（原托管方为 CSHL），获 CZI 早期资助 [DOC R1]。检索摘要称资助额为 1,600 万美元 [3P R3/R4]，**⚠ 未核验**：官方公告 R1 和 2025-03-12 新闻稿 [R78] 都没有写金额；Nature 新闻页取回的 HTML 里没有正文，Science 页返回 403。
- 2025 年新稿：bioRxiv 49,256、medRxiv 14,973，两者合计托管 38.9 万篇以上；约 80% 随后在期刊发表 [DOC R2]。核验补充：`/sum` 接口按月加总的 2025 年 bioRxiv 新稿为 49,318，与年报差 62 篇，口径差异原因不明 [LIVE R12]。
- `/sum` 接口显示 bioRxiv 2026-01 至 2026-08 每月新稿 3,924–5,165 篇，修订稿 1,536–1,831 篇 [LIVE R12]。

**DOI（设计要点）**

- 旧前缀 `10.1101`（Crossref member 246 "Cold Spring Harbor Laboratory"）；**2025-12-01 起新前缀 `10.64898`**（member 54368 "openRxiv"），后缀含日期，如 `10.64898/2026.08.28.747911`；一篇预印本的所有版本共用一个 DOI [DOC R2][LIVE R13]。
- Crossref 实测：2026-08 以 `10.1101` 前缀计的 posted-content 为 **0 条**；`10.64898` 当月 5,693 条 [LIVE]。
  - **核验修正（解释）**：Crossref 的 `prefix` 过滤器匹配记录的 owner prefix（所有者前缀），不匹配 DOI 字符串。
  - 旧 bioRxiv/medRxiv 记录已转给 openRxiv。例如 `10.1101/2020.09.09.20191205` 现在的 `prefix` 为 10.64898、member 为 54368、publisher 为 openRxiv。
  - 因此 `prefix:10.64898,until-posted-date:2025-11-30` 可查到 383,608 条 2025-12-01 之前发布的历史预印本，抽样 DOI 均为 `10.1101/…` 字符串；`prefix:10.1101` 在 2025-12 与 2026-08 都是 0。
  - 当月 5,693 条的 1,000 条样本全部是 `10.64898/…` 字符串 [LIVE R13][LIVE R81]。
- **陷阱**：`10.1101` 这个 DOI 字符串前缀同时出现在 CSHL Press 期刊（*Genome Research* 等，journal-article，Crossref 所有者仍为 CSHL）和旧 bioRxiv/medRxiv 预印本（所有者已是 openRxiv）上，**不能单凭 DOI 字符串前缀路由**，必须结合 `type`、member 与 container 判断。

**元数据通道**

- **官方 API** `https://api.biorxiv.org/` [DOC R5]：
  - `/details/[server]/[interval]/[cursor]/[format]`：每页 30 条，含 DOI、版本、许可、学科、`jatsxml` 路径、`published`。
  - `/pubs/[server]/[interval]/[cursor]`：预印本到正式版，每页 100 条。
  - `/pub/`、`/publisher/[prefix]/…`：按出版社前缀查。
  - `/funder/[server]/[interval]/[ROR]/…`：按资助方 ROR 查，数据自 2025-04-10 起。
  - `/sum/`、`/usage/`：统计。
  - 文档页未写限速与使用条款。
- **[LIVE] 可用性问题**：
  - 2026-09-26 14:56–15:43 UTC，`/details` 对日期区间、`Nd` 形式、DOI 查询、medRxiv 等 5 种形态都返回 `HTTP 200, content-length: 0, application/json`；`/pubs`、`/sum` 正常。
  - 第三方 issue 同日报告相同现象（8/8 空响应），并建议迁到 `/pubs`。但 `/pubs` 只含"已有正式版配对"的记录，缺 `version`、`jatsxml`，不能替代 [3P R10]。
  - 另一 issue（2026-09-22）报告 `/pubs` 按 DOI 查询无法解析 `10.64898` 前缀 [3P R11]。
    - 核验补充：该 issue 当天就以客户端绕行方案关闭。做法是先从 `/details` 的 `published` 字段取期刊 DOI，再按期刊 DOI 反查 `/pubs`，上游并未修复。
    - 核验时 `/pubs/medrxiv/10.64898/2026.01.07.26343585/json` 仍返回 "no articles found for published version of "，DOI 没被解析。
    - 既然 `/details` 已是空体，这条绕行也同时失效。
  - 核验补充：19:2x UTC 复测时，`/funder/{server}/{interval}/{ROR}/{cursor}` 也返回 200 + 0 字节，文档示例 `…/funder/biorxiv/2025-04-10/2025-07-10/00k4n6c32/45` 同样为空。推测它与 `/details` 共用同一后端（⚠ 推断）。
  - 未找到官方退役公告，判定为**故障或未公告变更**。
- **Crossref 兜底 [LIVE]**：
  - `filter=prefix:10.64898,type:posted-content,from-posted-date:2026-09-01,until-posted-date:2026-09-07` 返回 1,342 条。
  - 500 条样本中**摘要覆盖 100%**，`group-title` 即学科（bioRxiv 27 类 + medRxiv 各临床学科，含 "Psychiatry and Clinical Psychology"），`institution.name` 为 bioRxiv 或 medRxiv，带 `license` URL，`link` 指向 `syndication.highwire.org`（平台为 HighWire）。
  - 新鲜样本的 `relation` 为 0，正式版链接仍要靠 `/pubs` 或 EPMC。
- **Europe PMC**：以 `SRC:PPR` 收录，`bookOrReportDetails.publisher` 为 bioRxiv 或 medRxiv [LIVE]。

**最新论文通道**

- RSS：`http://connect.biorxiv.org/biorxiv_xml.php?subject={a+b}`，每个 feed 最近 30 篇 [DOC R8]。**核验修正**：实际返回的是 RSS 1.0（`rdf:RDF`，含 PRISM 命名空间），不是 Atom 1.0，`subject=neuroscience` 实测 30 个 `<item>`。`connect.biorxiv.org` 的 robots 为 `User-agent: *`、`crawl-delay: 10` [LIVE]。
- Crossref `from-posted-date`；`/pubs` 按区间取。

**全文通道与门控**

- **许可 6 选 1**：no reuse、CC BY-NC-ND、CC BY-ND、CC BY-NC、CC BY、CC0 [DOC R9]。FAQ 声明机器分析也应"free and unrestricted"。
- **2026-08 实际分布（Crossref facet，openRxiv 5,693 条）** [LIVE]：
  - CC BY 2,088（36.7%）
  - CC BY-NC-ND 1,665（29.2%）
  - bioRxiv no-reuse（`/about/FAQ#license`）837（14.7%）
  - CC BY-NC 587
  - medRxiv no-reuse 241
  - CC BY-ND 189
- **Bulk**：
  - `s3://biorxiv-src-monthly`、`s3://medrxiv-src-monthly`（us-east-1，**requester-pays**）。
  - 内容为 MECA 包（zip：`manifest.xml` + `content/` 下的 PDF、JATS XML、图、补充材料），**每月**一交付，Back_Content 自 2018 年末起。
  - 【合规】条款原意："not intended as a source for further redistribution"，要求 link back，不得重新托管 [DOC R6/R7]。
- 单篇：网站 PDF。

**认证**：元数据、网站均无需认证；S3 需要 AWS 账号并自付流量。

**限速 / robots / 反爬**

- `www.biorxiv.org` robots [LIVE R15]：`User-agent: *` 设 `Crawl-delay: 7`，禁 `/search/`。**点名全禁** ClaudeBot、GPTBot、CCBot、openai、ChatGPT-User、Applebot、Amazonbot、PerplexityBot、Bytespider 等 AI/SEO 爬虫，以及 **`python-requests/2.32.3`、`wget`、`curl`** UA。前置 Cloudflare。
- `www.medrxiv.org`：只有 `*` 组，`Crawl-delay: 7`。
- `api.biorxiv.org`：无 robots（404）。

**v2 建议（P0）**

- 元数据走 Crossref + EPMC。Crossref 用 `member:54368` 或 `prefix:10.64898` 查一次即可覆盖新旧两种 DOI 字符串（核验修正：原写"两个前缀并查"，但 `prefix:10.1101` 已查不到预印本）。`/details` 恢复后作为版本、`jatsxml` 的补充，并挂金丝雀。
- 正式版链接：`/pubs` 与 EPMC `HAS_PUBLISHED_VERSION` 并用。
- 全文按许可分级（§3 第 3 条）：CC BY/CC0 可平台共享；no-reuse 只存派生特征 + 链接。
- S3 只用于内部 TDM（如向量化），不对外分发。
- 单篇网页 PDF 只在用户触发时取，遵守 7 s 间隔。

#### 2.2.2 Research Square（Springer Nature）

- **归属**（核验修正，改用一手来源）：Springer Nature 2022-12-01 新闻稿称其"increased its investment in Research Square Company (RSC) to take full ownership"，即增持至全资 [DOC R76]；维基条目 [3P R17] 与此一致。同一新闻稿称集成式预印本投稿服务 In Review 已覆盖 700 余种 Springer Nature 期刊（含 Nature 系），这是 2022 年口径，现状 ⚠ 未核验。
- **元数据**：
  - Crossref 前缀 `10.21203`（member 名 "Research Square Platform LLC"）。2026-08 共 8,995 条 posted-content，**许可 100% 为 CC BY 4.0**；100 条样本摘要覆盖 100%，只有 2/100 带 `has-version`/`is-version-of` 关系 [LIVE R14]。
  - Europe PMC 收录（3 天 1,000 条样本中占 394 条，为最大单一来源）[LIVE]。
  - 官方 JSON API 为**申请制**（`/request-api`，条款未读到 ⚠）。
- **最新**：Crossref `from-posted-date`；EPMC。
- **全文**：CC BY 4.0 允许再分发（须署名）；PDF 在网站。
- **robots** [LIVE]：`*` 组 `Disallow: /api/`；anthropic-ai、ClaudeBot、GPTBot、CCBot、Google-Extended、PerplexityBot、cohere-ai 等全禁；前置 Cloudflare。
- **v2（P1）**：只经 L2 获取；全文优先 EPMC，网站 PDF 仅在用户触发时取。

#### 2.2.3 PsyArXiv 与 OSF Preprints

**元数据**：OSF API v2（JSON:API）。

- `GET https://api.osf.io/v2/preprints/?filter[provider]=psyarxiv&sort=-date_created` [LIVE R18]：
  - `links.meta.total` = **64,345**（是否含多版本 ⚠）。核验时（19:3x UTC）为 64,354，数值随新稿增长。
  - `filter[date_created][gte]=2026-09-20` 返回 248 条，即约 40 条/天（含新版本）。核验时为 257 条。
  - 记录 id 带版本号（如 `wkcgf_v3`），**每个版本一个 DOI**（`10.31234/osf.io/wkcgf_v3`）。
  - `attributes.doi` 是**正式发表版 DOI**（如 `10.1037/abn0001175`），`relationships` 含 `primary_file`、`license`、`versions`、`review_actions`、`identifiers`。
- Crossref `10.31234`（member "Center for Open Science"）：2026-08 共 1,162 条，许可为 CC BY 968、CC0 107，其余未标；样本 30% 带 `is-preprint-of` [LIVE]。
- Europe PMC：`PUBLISHER:"PsyArXiv"` 共 65,080 条 [LIVE]。

**Provider 全景**（`/v2/providers/preprints/`，32 个）[LIVE]：

- 与本领域相关的：`psyarxiv`（开放投稿、先审后发）、`metaarxiv`（元科学）、`newaddictionsx`（成瘾）、`edarxiv`、`socarxiv`、`biohackrxiv`。
- `allow_submissions=false`（已停收或迁出）的有：`mindrxiv`、`ecoevorxiv`、`nutrixiv`、`sportrxiv`、`engrxiv` 等。**provider 状态需周期性刷新。**

**最新**：`filter[date_created][gte]`、`filter[date_modified]`、`sort=-date_created`。

**全文**：`primary_file` → files API → 下载链接；许可按条取（CC BY 为主）。

**限速**

- 官方文档页为前端渲染，未取到正文 ⚠。
- OSF 服务端源码（`develop` 分支 `api/base/settings/defaults.py`，最近提交 2026-07-28）的 `DEFAULT_THROTTLE_RATES`：`user` 10,000/day、`non-cookie-auth`（匿名、无 cookie）100/hour、`burst` 10/second、`files` 75/minute、`files-burst` 3/second [LIVE R19]。第三方教程给出的"匿名 100/小时、带 token 10,000/天"与此一致 [3P R75]。**生产值可能覆盖默认值 ⚠。**

**robots** [LIVE R20]：

- `api.osf.io` 为 `User-agent: *` / `Disallow: /`。
- `osf.io` 的 `*` 组 `crawl-delay: 10`，禁 `/api/*` 与 `*?view_only=`，并对"行为不当"的 PerplexityBot、GPTBot、Meta-ExternalAgent 等全禁。
- 【合规】API 主机 robots 全禁与官方 API 文档邀请程序化使用存在张力（同批 `aggregators-repositories.md` 也记录了这一现象）。**需在设计中写明例外理由并向 COS 确认。** 这一点列入未决问题（§4）。

**v2（P0，心理学预印本主源）**

- 平台级 PAT，只用于公开数据以提高配额。
- 增量以 `date_modified` 为水位。
- 预印本到正式版链接用 `attributes.doi`。

#### 2.2.4 Preprints.org（MDPI）

- **元数据**：Crossref `10.20944`（member "MDPI AG"），2026-08 共 2,505 条，**100% CC BY 4.0**，样本摘要 100%，**33% 带 relation**（`is-preprint-of`/`has-version`）[LIVE]；Europe PMC 收录（样本 174/1,000）[LIVE]。
- **反爬**：`www.preprints.org/robots.txt` 本身即返回 **Akamai "Access Denied" 403** [LIVE R22]，视为网站不接受自动化访问。
- **v2（P1）**：只经 L2 获取；全文只取 EPMC 已有的部分。

#### 2.2.5 SSRN 生医通道（Cell Press Sneak Peek / Preprints with The Lancet）

- v1 已有 `ssrn` adapter（Crossref `10.2139` 枚举 + landing 解析，浏览器全文为 opt-in，D-029）[v1]。
- Crossref SSRN 记录的 `group-title` **恒为 "SSRN"**（2026-08-01/02 共 1,000 条样本全部如此），**无法区分 Sneak Peek** [LIVE]。SSRN 2026-08 在 Crossref 新建 28,374 条，其中 28,370 条为 posted-content；按 `from-posted-date` 过滤得 0 条，须改用 `from-created-date` [LIVE]。
- Europe PMC 中 `PUBLISHER:"SSRN"` 共 17,659 条，**最新 firstPublicationDate = 2023-10-28**，即 SSRN 到 EPMC 的流已停 [LIVE]。
- Sneak Peek 现状 ⚠ 未核验：`cell.com/sneak-peek` 返回 403，`ssrn.com` 本机 TLS 握手失败。
- **v2（仅元数据，P2）**：不单独建 adapter，沿用 v1 `ssrn` 泛化通道。

#### 2.2.6 其他预印本/发表后评审平台

| 平台 | 本日证据 | 处理 |
|---|---|---|
| Authorea（Wiley） | Crossref `10.22541` 2026-08 共 412 条，无 license 元数据，摘要 93%；EPMC 名为 "Authorea Preprints" [LIVE] | P2，仅 L2 |
| arXiv q-bio | 10 个分类：q-bio.BM/CB/GN/MN/NC/OT/PE/QM/SC/TO；相关的还有 physics.bio-ph、stat.AP、cs.HC [DOC R69]；EPMC `SRC:PPR AND PUBLISHER:"arXiv"` 共 7,866 条 [LIVE] | **P0**：v1 `arxiv` adapter 只需新增 VenueSpec |
| F1000Research、Wellcome Open Research、Open Research Europe、VeriXiv 等 | 均出现在 EPMC 3 天样本中 [LIVE] | P2，经 EPMC |
| MetaArXiv、EcoEvoRxiv、SciELO Preprints、ARPHA、Beilstein Archives、Access Microbiology | 均在 EPMC 样本中 [LIVE] | P2，经 EPMC |
| PsychArchives（ZPID，心理学学科仓储） | OAI-PMH `https://www.psycharchives.org/oai/request` 返回 200；robots `*` `Crawl-delay: 2` [LIVE R66] | P2，经 OAI |
| ChemRxiv | EPMC 8,952 条（生化交叉）[LIVE] | 见 `natural-sciences.md` |

### 2.3 开放与检索基础设施

#### 2.3.1 PubMed / E-utilities / baseline

**规模与 bulk** [DOC R28][LIVE]：

- FTP README（2026-01-30 更新）写明 PubMed"more than 40 million citations"。
- 2026 年度 baseline 为 `pubmed26n0001`–`pubmed26n1334`（每年 12 月发布）。日更文件从 `pubmed26n1335` 起，含新增、修订、**删除**；调研时（约 15:10 UTC）目录最新为 `pubmed26n1638`。核验补充：同日目录时间戳 14:05 又新增 `1639`、`1640`，前两天也各有 2 个文件，即**每日约 2 个文件**；einfo 显示 PubMed 共 41,210,260 条 [LIVE]。
- 条款：须致谢 NLM，不得使用 PubMed 标识；"some abstracts may be protected by copyright"。

**E-utilities**：base `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/`（`esearch`/`efetch`/`esummary`/`elink`/`einfo`/`epost` 等）。

- **限速**：无 key 按 IP 计 **3 rps**（本日响应头 `x-ratelimit-limit: 3`、`x-ratelimit-remaining`）[LIVE]；有 key 默认 **10 rps**，更高速率需发邮件至 eutilities@ncbi.nlm.nih.gov 申请；参数为 `api_key`，key 在 NCBI 账号设置中生成 [DOC R29]。
- **上限**：ESearch 单次查询最多返回 10,000 条，超出须用 EDirect 或按日期、许可等过滤切片 [DOC R37]。
- **大任务**：PMC 文档要求超过 100 次请求的脚本避开高峰（美东工作日 05:00–21:00），且不得并发 [DOC R34]。核验注：这条原文出自 PMC OAI-PMH 服务页。E-utilities 总指南是否有同样要求，因 reCAPTCHA 未能读到原文确认 ⚠。E-utilities 总指南（Bookshelf NBK25497）本日对程序化访问返回 **reCAPTCHA 页**，原文未读到 ⚠ [LIVE R31]。
- `tool`/`email` 参数：PMC ID Converter 缺失时返回 warning（"query param `email` is missing"）[LIVE R39]。E-utilities 同类要求的原文因 reCAPTCHA 未读到 ⚠。

**robots** [LIVE R32]：

- `eutils.ncbi.nlm.nih.gov`：`Disallow: /`，注释为 "back-end server version - no robots!"，即后端 API 主机，使用受用法指南约束。
- `pubmed.ncbi.nlm.nih.gov`：`Crawl-delay: 1`，并禁 `/api`、`/rss`、`/*/citedby/`、`/*/similar/` 等。**网站 RSS 不对机器开放。**

**增量**：`esearch` 的 `datetype=edat`（Entrez 日期）或 `[crdt]` 日窗；bulk 场景用日更文件。

**心理学覆盖**：2025 年 PubMed 计数（按 `[is]`/`[ta]` + `2025[dp]`）为 JPSP 165、Psych Sci 66、*J Mem Lang* **8**、AMPPS **0**、*Collabra* 4、CogSci **0** [LIVE]，覆盖明显不完整。

**v2（P0）**：生命科学元数据、摘要与 MeSH 的主干；心理学的增强层。若需全量镜像，用 baseline + updatefiles（条款清晰、免 API 配额），不要用 API 翻页。

#### 2.3.2 PMC（2026-08 服务变更后）

**允许的自动化通道只有 4 个** [DOC R33]：PMC Cloud Service（S3）、PMC OAI-PMH、E-utilities、BioC API。原文要点："Systematic retrieval (or bulk retrieval) of articles through any other automated process is prohibited"。**因此即使 `pmc.ncbi.nlm.nih.gov` 的 robots `Allow: /articles/`（`Crawl-delay: 1`），也不得爬网页全文** [LIVE R32]。

**时效变化**：

- 2026-02-12 宣布数据集分发变更；**2026-08-24 那一周删除全部旧 Article Dataset 文件**（FTP 与 Cloud）[DOC R36/R37]。
- **OA Web Service 已不可用**（页面 2026-08-19 修改）[DOC R35]。
- FTP 只保留 `PMC-ids.csv.gz`（ID 对照）[DOC R36]。

**S3（`s3://pmc-oa-opendata`，us-east-1，匿名 `--no-sign-request`，亦可 HTTPS）** [DOC R37]：

- 约 **800 万个文章版本**，按 `PMCID.版本` 前缀组织，含 `.xml`（JATS）、`.txt`、`.json`，许可允许时还有 PDF、图、补充材料。
- JSON 字段：`pmcid`、`version`、`pmid`、`doi`、`license_code`（CC 代码，或作者手稿用的 **`TDM`**，即"可做文本挖掘及合理使用"）、`is_manuscript`、`is_retracted`、`is_historical_ocr`、`xml_url`/`pdf_url`/`text_url`（带 md5）。
- **每日 inventory CSV**；**不再提供 baseline 或增量包**。按日增量用 `[pmcrdat]` 加 `open_access[filter] OR author_manuscript[filter]` 的 eSearch，再到 S3 取文件。
- 版本号不代表新旧，要读 JSON 判断是否为 AM。**删除没有通知，只能靠 inventory 对账发现。**
- 【合规】README 条款："Users who redistribute the data … agree to only distribute data that are licensed for redistribution"。
- 核验补充：PMC AWS FAQ 在讲"可商用子集"的查询式时，说已分发的作者手稿"available for commercial reuse regardless of license"[DOC R37]。README 对 `TDM` 码的定义则是"可做文本挖掘，并可按合理使用原则使用全文"。两处都没有明说平台能否向其他用户展示全文，所以 §3 第 3 条与 Q11 仍按"私有 TDM + 跳转"处理。

**OAI-PMH**（base `https://pmc.ncbi.nlm.nih.gov/api/oai/v1/mh/`）[DOC R34][LIVE]：

- 格式 `pmc`（全文 JATS）、`pmc_fm`（front matter）、`oai_dc`；`set=pmc-open` 为可取全文的集合，另有按刊的 set（如 `bmj`）。
- 分页：ListIdentifiers 每页 50，ListRecords 每页 10。
- 限速：**3 rps**，超过 100 次请求须在美东非高峰时段，禁并发。文档要求设置 `Accept-Encoding: gzip, deflate`，原文说是为了"最高效传输"。

**辅助 API** [LIVE]：

- ID Converter 新 base：`https://pmc.ncbi.nlm.nih.gov/tools/idconv/api/v1/articles/?ids=…&format=json`。
- BioC：`https://www.ncbi.nlm.nih.gov/research/bionlp/RESTful/pmcoa.cgi/BioC_json/{PMCID}/unicode`，返回段落级 JSON 与 license。
- Literature Citation Exporter：`/api/ctxp/` [DOC]。

**许可检索过滤器**：可商用子集查询式 `((cc0 license[filter] OR cc by license[filter] OR cc by-sa license[filter] OR cc by-nd license[filter]) OR author manuscript[sb]) NOT pmc embargo[filter]` [DOC R37]。

**政策背景**：NIH 2024 Public Access Policy 要求 AAM 在正式出版日零 embargo 公开，自 **2025-07-01** 对当日及以后接收的稿件生效（原定 2025-12-31，后提前）[DOC R41]。所以 NIH 资助论文的 AM（`license_code=TDM` 为主）在 PMC 的比例会上升。

**覆盖实测**（2025 年 PMC/PubMed）：PNAS 4,374/4,466、*Front Psychol* 4,267/4,808、*Cell* 215/550、*Science* 222/1,924、JPSP 11/165 [LIVE]。

**v2（P0）**：OA 全文主通道，逐条按 `license_code` 门控，并用 inventory 做删除对账。

#### 2.3.3 Europe PMC（EMBL-EBI）

**REST API**（base `https://www.ebi.ac.uk/europepmc/webservices/rest/`）[LIVE R23–R25]：

- `search`：`format=json`，`resultType=idlist|lite|core`，`pageSize` 实测 1,000，`cursorMark` 深分页。
- `/{PMCID}/fullTextXML`：JATS 1.4。
- `/{src}/{id}/supplementaryFiles`：zip。
- `/fields`：143 个可检索字段（核验修正：原记"约 130"；下文列出的 32 个字段名已逐一在 `/fields` 列表中核对存在）。
- 注释 API：`/europepmc/annotations_api/annotationsByArticleIds?articleIds=PMC:…`，返回带 ChEBI 等本体 URI 的实体标注。

**高价值字段**（本领域组合查询的"下推"目标）：

- **章节级**：`INTRO`、`METHODS`、`RESULTS`、`DISCUSS`、`CONCL`、`FIG`、`TABLE`、`DATA_AVAILABILITY`、`SUPPL`。
- **实体**：`GENE_PROTEIN`、`DISEASE`、`CHEM`/`CHEBITERM`、`ORGANISM`、`GOTERM`、`EXPERIMENTAL_METHOD`。
- **关系/信号**：`HAS_PREPRINT`、`HAS_PUBLISHED_VERSION`、`HAS_VERSION_EVALUATIONS`、`CITES`/`REFFED_BY`。
- **许可/OA**：`LICENSE`、`OPEN_ACCESS`、`HAS_FT`、`HAS_PDF`。
- **增量**：`FIRST_IDATE`、`INDEX_DATE`、`UPDATE_DATE`、`FT_CDATE`。
- **资助**：`GRANT_AGENCY`、`GRANT_ID`、`FUNDER_INITIATIVE`。

**规模** [LIVE]：

- `SRC:PPR` 共 **1,247,001**；其中 `HAS_FT:Y` 76,185，`HAS_VERSION_EVALUATIONS:Y` 41,177。
- 2026-09-01 至 09-20 首发预印本 13,938 篇（`SRC:PPR AND FIRST_PDATE`）；`FIRST_IDATE:[2026-09-24 TO 2026-09-25]` 为 3,295 条。核验修正：3,295 是全库、不限来源的条数，加 `SRC:PPR` 后为 1,179 条。
- 2026-09-14 至 16 的 1,000 条样本来自 17 个平台：Research Square 394、bioRxiv 215、Preprints.org 174、PsyArXiv 86、medRxiv 76，另有 F1000Research、Wellcome Open Res、SciELO、EcoEvoRxiv、MetaArXiv、Authorea、ARPHA、Beilstein、Open Res Europe、Open Res Africa、Access Microbiology、VeriXiv。**新鲜预印本几乎都没有 EPMC 全文**（样本 `inEPMC=Y` 为 0/1,000）。

**限速与条款**：

- 未找到公开的数值限速 ⚠。EMBL-EBI ToU 写明："to a level that prevents … EMBL-EBI providing services to others, will result in the user being blocked" [DOC R26]。
- 【合规】`europepmc.org` 网站（含 robots.txt）本日返回 Cloudflare managed challenge；`www.ebi.ac.uk` robots 的 `*` 组 `Crawl-Delay: 10` 且无 europepmc 专条 [LIVE R27]。**只用 ebi.ac.uk 上的 API，不碰网站。**

**v2（P0）**：作为生命科学"组合查询路由"的联邦后端。章节级、实体级、预印本关系和评审信号直接下推到 EPMC，本地只缓存用户兴趣子集。多用户规模上线前应联系 EBI 约定用量（⚠ 未决）。

#### 2.3.4 核验补充：NCBI PubTator3 与 NIH iCite（生命科学专属的 L2 信号层）

> 本节由核验员补写。原文只写了 Europe PMC 注释 API，漏掉了 NCBI 侧两个与"实体图索引"和"影响力信号"直接相关的公共服务。以下事实均于 2026-09-26 核验。

| 服务 | 做什么 | 已核验事实 | 未核验 / 注意 | v2 用途 |
|---|---|---|---|---|
| **PubTator3**（NCBI） | 为 PubMed 摘要与 PMC OA 全文做实体标注和关系抽取 | ① 论文 Wei et al., "PubTator 3.0: an AI-powered literature resource for unlocking biomedical knowledge", *Nucleic Acids Research* 2024（DOI 10.1093/nar/gkae235，Crossref 核对）[R79]。② `https://www.ncbi.nlm.nih.gov/research/pubtator3-api/publications/export/biocjson?pmids=29355051` 返回 200 BioC JSON；样本标注类型为 Chemical、Disease、Species、CellLine，并带 `relations`（Association、Positive_Correlation、Negative_Correlation）[LIVE] | 官方 API 文档页为前端渲染，没读到正文。限速只有第三方 MCP 项目 README 写"≤3 rps"，⚠ 未核验；数据许可 ⚠ 未核验 | 与 EPMC 注释互为备份，用于实体节点（基因、疾病、化学物、物种）建图、实体级过滤和"相关论文"扩散；建议 P1 |
| **iCite / NIH Open Citation Collection**（NIH OPA） | PubMed 条目的引文链接与 RCR（Relative Citation Ratio）等指标 | ① 论文 Hutchins et al., "The NIH Open Citation Collection: A public access, broad coverage resource", *PLOS Biology* 2019（DOI 10.1371/journal.pbio.3000385，Crossref 核对）[R80]。② `https://icite.od.nih.gov/api/pubs?pmids=29355051` 返回 200 JSON，字段含 `relative_citation_ratio`、`citation_count`、`cited_by`、`references`、`is_research_article` 等 27 个 [LIVE] | 文档页 `/api` 返回 401（路由已变）；`robots.txt` 返回 SPA 页面，不是真正的 robots 文件；限速、许可与批量快照渠道 ⚠ 未核验 | PubMed 子集的开放引文图与领域归一化影响力特征，可用于冷启动排序与"高影响力"过滤；建议 P1，上线前确认限速 |

### 2.4 出版商与期刊平台

> 共同事实：以下出版商的文章页、PDF 都不对匿名程序化访问开放，或受 WAF 挑战，或被 robots 禁止。v1 已记录"数据中心 IP 在 TLS 层被拒"的现象 [v1 R74]。本节按"元数据 / 最新 / 全文 / 认证 / 限速与 robots"逐项列出，汇总见 §2.7 名录表。

#### 2.4.1 Cell Press（Elsevier）

- **平台**：`www.cell.com` 的 robots 路径（`/na101/`、`/na102/`、`/doi/mlt/`、`/action/showPdf`）与 Atypon Literatum 站点（science.org、pnas.org、tandfonline、wiley）同构，**推断为 Atypon**；前置 Cloudflare。同一批文章也在 ScienceDirect（相同 PII）[LIVE R46]。
- **元数据**：
  - Crossref 可按 ISSN 完整枚举，但 **`abstracts-current` 为 0%**（Cell、Neuron、Mol Cell、Curr Biol、Cell Reports、TICS、Cognition、JML 全是 0）。
  - `license` 为 Elsevier TDM user license + TDMRep license + STM ASF，`link` 指向 `api.elsevier.com`（`intended-application: text-mining`）[LIVE R71]。
  - 摘要走 PubMed。
- **最新**：`https://www.cell.com/{journal}/current.rss` 与 `/inpress.rss`（RDF/RSS 1.0，本日 200，robots 允许）[LIVE]。
- **全文**：
  - **核验修正**：原写"*Cell* 2026 年 463 条中无 CC 许可"，与 Crossref 不符 [LIVE R71]。
    - *Cell* 2026 年 463 条中 **241 条带即时 CC 许可**：`content-version=vor`，CC BY 165、BY-NC-ND 47、BY-NC 29。另有 51 条为 Elsevier OA user license，全部 463 条都带 Elsevier TDM 许可。
    - 同口径下其他 Cell Press 刊的 CC 占比：*Neuron* 130/366、*Mol Cell* 123/300、*Curr Biol* 266/722、*TICS* 62/174。
    - 结论：Cell Press 旗舰刊是**混合 OA（CC 约 36–52%）**，不是纯订阅，许可要逐条门控。
  - *Cell Reports* 全 OA（DOAJ：CC BY/BY-NC/BY-NC-ND）。
  - 订阅内容走 Elsevier Article Retrieval API，要求**用户自有 API key/insttoken**：v1 记录为 50,000 次/周、10 req/s，TDM 专用 key 不限量 [v1 2026-07-20]。核验：官方 API key 设置页写的是"Unlimited for Text Mining API Keys"，与 v1 一致 [DOC R77]。
  - 【合规】`cell.com` 的 `/action/showPdf` 落在 `Disallow: /action` 下 [LIVE]。
- **robots** [LIVE]：
  - cell.com：`*` 组 `Crawl-delay: 1`，禁 `/action`、`/rss`、`/search`；GPTBot、ChatGPT-User、CCBot、Google-Extended、PerplexityBot、anthropic-ai、ClaudeBot、Bytespider 全禁。
  - ScienceDirect：`*` 组 `Disallow: /`，并点名 claude-code 等 [LIVE R47]。
- **v1**：`elsevier_sd` 已实现，可直接复用（auth_gated / 官方 API）。

#### 2.4.2 Springer Nature（Nature Portfolio、Springer、BMC、EMBO Press、Psychonomic Society 期刊）

**平台迁移（本日实测）** [LIVE R44]：

- `genomebiology.biomedcentral.com` 301 到 `link.springer.com/journal/13059`。
- `bmcbiol.biomedcentral.com/articles/most-recent/rss.xml` 301 到 `link.springer.com/journal/12915/articles`，**BMC 旧 RSS 已失效**。
- `www.biomedcentral.com` 301 到 `link.springer.com/brands/bmc`。
- `www.embopress.org` 301 到 `link.springer.com/partners/embo-press`；*EMBO J* 为 `/journal/44318`，2026 年 DOI 为 `10.1038/s44318-…`。

**元数据**：

- Crossref 摘要覆盖：Nature 12%、Nat Genet 23%、Nat Neurosci 25%、Nat Commun 47%、Nat Hum Behav 19%、Genome Biol 56%、PB&R 57%、BRM 62% [LIVE]。
- **Crossref 数据质量问题** [LIVE]：
  - `/journals/1548-7091`（*Nature Methods*）返回 "Nature Chemical Biology" 的期刊记录（ISSN 被错挂），但 works 路由返回的 DOI（`s41592-…`）正确。
  - *EMBO J*（0261-4189）、BRM（1554-351X）用**印本 ISSN 查 2026 年记录为 0**，改用 eISSN（1460-2075、1554-3528）才分别得到 247、275 条。
- **Springer Nature Meta API**：需 `api_key`，无 key 返回 401 JSON [LIVE R42]。官方 Python 客户端 `springernature/springernature_api_client`（8★，MIT，2026-08-10 推送）[LIVE R73]。

**最新**：

- `https://www.nature.com/{journal}.rss`（RSS 1.0，含 DOI 与 PRISM 字段，约 90 条）[LIVE R45]。
- 【合规】`link.springer.com` 的 robots 为 `User-agent: *` + `Disallow: /`，外加允许清单（`/journal*`、`/article/`、`/content/`、`/search$` 等）。**`search.rss?...` 不在允许清单内**（本地最长匹配判定器：DISALLOW）[LIVE]。v1 catalog 记载的 Springer 检索 RSS 用法需要复核（§4）。

**全文与 TDM 条款** [DOC R43]：

- 通过订阅机构、为非商业研究可做 TDM。平台直接下载 **≤1 请求/秒**；API key **150 请求/分钟**。
- 【合规】内容须存于"secure internal server without access for third parties"，这直接禁止多用户平台跨用户共享订阅全文。核验补充：原文紧接着还写了"and only for the duration of the TDM project"，即**保存期限只到 TDM 项目结束**，v2 的私有存储需要支持按项目到期清理。
- OA 部分（Nat Commun、Genome Biol、Mol Syst Biol 全 OA；Nature 2026 年 3,312 条中 656 条为 CC）可共享。

**robots / 反爬** [LIVE]：

- nature.com：`*` 组只禁 `/search`、`/*/*/*/pf/` 等；anthropic-ai、ClaudeBot、Claude-Web、GPTBot、ChatGPT-User、CCBot、Google-Extended、PerplexityBot、Bytespider 全禁。
- nature.com 文章页对无 cookie 的客户端 303 到 `idp.nature.com/authorize?response_type=cookie`（WebFetch 观察）。

**v1**：catalog 以 `springer`（cookie 档，planned）登记，未实现。

#### 2.4.3 AAAS（Science、Science Advances 等）

- **平台**：Atypon（robots 路径同构）+ Cloudflare；政策页对 WebFetch 返回 403 ⚠ [LIVE R48]。
- **元数据**：Crossref 摘要覆盖 Science 85%、Sci Adv 98% [LIVE]。
- **最新**：`/action/showFeed?type=etoc&feed=rss&jc=science`（jc 另有 sciadv 等）。虽然 `*` 组 `Disallow: /action`，但有更长的 `Allow: /action/showFeed`，按最长匹配判定为**允许**；本日返回 200 [LIVE]。
- **全文**：
  - *Science* 订阅：2026 年 1,563 条中只有 101 条带 `science-licenses-journal-article-reuse` 许可，部分 `delay-in-days: 365` [LIVE]。
  - *Science Advances* 全 OA（DOAJ：CC BY/BY-NC）[LIVE]。
  - PMC 2025：Science 222、Sci Adv 3,184 [LIVE]。
- **robots**：Google-Extended、anthropic-ai、GPTBot、ChatGPT-User、CCBot 全禁 [LIVE]。
- **v2**：Sci Adv 为 P1（全文走 PMC）；*Science* 主刊只收元数据，全文按用户自取。

#### 2.4.4 PNAS

- **平台**：Atypon + Cloudflare；robots 只点名 GPTBot，`*` 组禁 `/action`、`/search`、`/doi/epdf/`、`/doi/reader`、`/doi/ref`、`/doi/citedby` 等 [LIVE R49]。
- **最新**：`/action/showFeed?type=etoc&feed=rss&jc=pnas`（有 Allow，本日 200）[LIVE]。
- **全文**：
  - Crossref 显示 2026 年 3,688 条中 **3,649 条带 CC 许可**（CC BY-NC-ND 2,841、CC BY 808），**事实上接近全 OA**；政策公告未能读取 ⚠。
  - **PMC 覆盖 98%**（2025 年 4,374/4,466）[LIVE]。
- **v2（P0）**：元数据走 Crossref + PubMed，全文走 PMC S3/OAI，零出版商接触。

#### 2.4.5 eLife（新模式）

- **模式**：发布经同行评审的预印本（Reviewed Preprint），附编辑与审稿人撰写的 **eLife Assessment**。评估词表：significance 为 landmark > fundamental > important > valuable > useful；strength 为 exceptional > compelling > convincing > solid > incomplete > inadequate [DOC R50]。
- **官方 API**（`https://api.elifesciences.org`，无需 key）[LIVE]：
  - `/articles` total 19,543，含 `status`（vor/poa）、`version`、`versionDate`、`elifeAssessment`、`subjects`。
  - `/reviewed-preprints` total 4,806；样本记录的 DOI 是 medRxiv 预印本 DOI（`10.64898/2026.06.15.26355613`），即 RP 挂在预印本 DOI 上。
  - `/subjects` 共 19 个。
  - 使用厂商媒体类型（`application/vnd.elife.article-list+json; version=1`），`cache-control: max-age=300`。
  - 限速 ⚠ 未核验（文档页为前端渲染）。
- **其他通道**：Crossref 摘要 99%，许可 CC BY（vor/am/tdm），TDM link 指向 `cdn.elifesciences.org` [LIVE]；RSS `https://elifesciences.org/rss/recent.xml` 本日 200 [LIVE]；JATS 全量仓库 `elifesciences/elife-article-xml`（2026-09-25 推送）[LIVE R73]。
- **robots**：网站 `*` 组 `Crawl-delay: 10`，禁 `/search`、`/download/`；API 主机 `Disallow: /` [LIVE]。
- **v2（P1）**：评估词表作为推荐与排序的**结构化质量信号**；全文 CC BY 可共享。

#### 2.4.6 PLOS

- **Search API**（Solr，无需 key）[DOC/LIVE R51]：
  - 请求 `https://api.plos.org/search?q=…&fl=…&wt=json`；`doc_type:full` 过滤整篇文档（默认含 `/title` 等子文档）。
  - 限速原文：**7,200 次/天、300 次/小时、10 次/分钟**，并要求"allow 5 seconds for your search to return results"，即每次检索预留 5 秒；超限封 IP；**同一 IP 最多 5 个并发连接**；每次请求**不超过 100 行** [DOC R51，核验确认]。
- **规模**：2026-09-01 至 25 全刊 1,711 篇 [LIVE]。**核验修正**：这些文章分布在 **16 个刊**，facet 共 18 个值，其中 2 个为 0（原写 15 个刊、17 个值）。较新的刊有 PLOS Mental Health 19、PLOS Aging and Health 9、PLOS Ecosystems 8、PLOS Complex Systems 5 等；16 刊计数合计正好 1,711。
- **全文**：全 OA（CC BY，个别 CC0）；JATS 取自 `journals.plos.org/{journal}/article/file?id={DOI}&type=manuscript`（302 重定向）[LIVE]；全量语料 `PLOS/allofplos`（67★，MIT，2026-09-09）[LIVE]。
- **Crossref 陷阱**：印本 ISSN（1544-9173、1553-734X）2026 年无记录，须用 eISSN（1545-7885 得 413 条，1553-7358 得 737 条）[LIVE]。
- **robots**：`journals.plos.org` 的 `*` 组 **`Crawl-delay: 30`**，禁 `*/search` 等；`api.plos.org` 无 robots [LIVE]。
- **v2（P1）**：API 配额很小，只作补充；全文走 allofplos 或 PMC。

#### 2.4.7 Frontiers

- **元数据**：Crossref 摘要 90–92%，许可全为 CC BY 4.0，link 只有 similarity-checking [LIVE]。
- **最新**：`https://www.frontiersin.org/journals/{slug}/rss`（本日 200）[LIVE]。
- **全文**：全 OA；PMC 覆盖高（2025 年 *Front Psychol* 4,267/4,808、*Front Neurosci* 1,108/1,219）[LIVE]。
- **robots**：`*` 组 `Allow: /`，只禁少数目录 [LIVE]；条款页为前端渲染，未读到 ⚠。
- **v2（P1）**：元数据走 Crossref + RSS，全文走 PMC S3。

#### 2.4.8 MDPI

- **反爬**：`www.mdpi.com` 的 robots 与 RSS 都被 **Akamai 403** [LIVE R53]。
- **OAI-PMH**：`https://oai.mdpi.com/oai/oai2.php` 可用；earliestDatestamp 2012-01-12，日粒度，gzip；格式 `oai_dc`、`oai_agris`；**set 只按文章类型划分（67 个，如 research-article、review-article），没有按期刊的 set** [LIVE]。
  - 核验：调研员存档的 ListSets 响应（responseDate 2026-09-26T15:20:56Z）确有 67 个按文章类型的 setSpec。
  - **核验补充**：19:30–19:38 UTC 共 4 次请求 `verb=Identify`/`ListSets`，其中 3 次在约 60 s 后返回 nginx **504 Gateway Time-out**，另 1 次没有有效响应。该端点可用但不稳定，adapter 需要长超时、退避，并以 Crossref 按刊枚举兜底。
- **元数据/全文**：Crossref 摘要 100%，全部 CC BY；IJMS 2026 年已有 8,065 条；PMC 覆盖约 100% [LIVE]。按 ISSN 1422-0067 查 DOAJ 无结果 [LIVE R70]。核验补充：按刊名 `bibjson.title:"International Journal of Molecular Sciences"` 检索也是 0 条，说明 IJMS 当前确实不在 DOAJ，而不是 ISSN 口径问题。从未收录还是被下架，原因 ⚠ 未核验。
- **v2（P1）**：OAI 做全社增量、本地按刊过滤，或直接用 Crossref 按刊；体量大，须配"过载护栏"。

#### 2.4.9 PeerJ

- **元数据**：Crossref（member 名仍为 "PeerJ"），摘要 100%，许可 CC BY/BY-NC，link 含 text-mining [LIVE]；PMC 覆盖 100%（2025 年 1,752/1,752）[LIVE]。
- **最新**：`peerj.com/articles/index.rss` 被 **Cloudflare 挑战**，只能走 Crossref [LIVE]。robots `*` 组 `Crawl-delay: 2` [LIVE]。
- 所有权变更 ⚠ 未核验。
- **v2（P2）**：经 L2 即足够。

#### 2.4.10 Oxford Academic（OUP）

- **平台**：Silverchair + Cloudflare（v1）。本日 robots 复核仍无 AI-bot 专条 [LIVE]。
- **最新**：`/rss/site_{id}/{id}.xml`，NAR 本日 200 [LIVE]。
- **本领域刊**（2026 年 Crossref 许可 facet，按 eISSN 查询）：
  - NAR：1,037/1,056 为 CC，在 DOAJ。
  - *Bioinformatics*：698/705 为 CC。**核验修正**：原写"不在 DOAJ"，实际已被 DOAJ 收录。记录按 eISSN 1367-4811 登记，2023-07-11 入库，许可 CC BY，OA 起始年 2023，出版者 OUP；原结论来自用印本 ISSN 1367-4803 查询，该号在 DOAJ 查无结果 [LIVE R70]。
  - *SCAN*：78/79 为 CC。
  - **Child Development**：见下条。
- **Child Development 迁移**：Crossref 中该刊全部记录（含 `10.1111/cdev.14179` 这类历史 DOI）的 publisher 已是 OUP（member 286），解析到 `academic.oup.com/chidev/...`；2026 年新 DOI 为 `10.1093/chidev/*`；按印本 ISSN 查 2026 年为 0，eISSN 1467-8624 得 231 条 [LIVE]。
- **v1**：`oup_silverchair` 已实现，可复用。

#### 2.4.11 Cambridge Core

- **本日**：`www.cambridge.org/robots.txt` 即返回 **Cloudflare 挑战 403**。v1 在 2026-07-20 记载"直连 200、未触发质询"，**已发生漂移** [LIVE R56]。
- **元数据**：BBS 摘要 99%（2026 年 412 条，含开放同行评论）、*Psychological Medicine* 91% [LIVE]。
- **全文**：BBS 在 PMC 为 0；*Psych Med* 在 PMC 有 396（2025 年）[LIVE]。
- **v1**：catalog 登记为 `cambridge`（planned）。

#### 2.4.12 Annual Reviews

- **robots**：`*` 组 `Crawl-delay: 2`，禁 `/deliver/`、`/search` 等 [LIVE]；RSS 路径被 **Cloudflare 挑战** [LIVE R57]。平台未核验 ⚠（robots 路径结构与 Atypon 不同）。
- **Subscribe to Open（S2O）**：官方页 403 ⚠。Crossref 显示 *Annu Rev Psychol* 2026 年 25/34 条为 CC BY，*Annu Rev Biochem* 样本 23/24 为 CC BY-NC(-ND)，与"当年卷开放"一致 [LIVE]。
- **v2（P1）**：综述文章对用户画像冷启动有价值；元数据走 Crossref，全文取可再分发的 CC 版本。

#### 2.4.13 APA PsycNet（APA 期刊与 PsycInfo）

- **robots**：`psycnet.apa.org` 为 **`User-agent: *` / `Disallow: /`**，只放行 Googlebot、CrossrefEventDataBot、Twitterbot、bingbot（Crawl-delay 17）等。anthropic-ai、ClaudeBot、Claude-Web、GPTBot、CCBot、PerplexityBot、OAI-SearchBot 等全禁 [LIVE R58]。`www.apa.org` 本身受 **Imperva/Incapsula** 保护，robots.txt 也返回 JS 挑战页 [LIVE]。
- **元数据**：
  - Crossref `10.1037` 可完整枚举，但 **`abstracts-current` 为 0%**（9 个样本刊全为 0）。
  - 许可有两类：少量 CC（JPSP 2026 年 22/184）；以及 APA open-access 说明页，`content-version: am`，`delay-in-days` 多为 365 [LIVE]。
  - PubMed 覆盖部分核心刊（2025 年 JPSP 165、Dev Psych 316、Psych Bull 50）。
- **PsycInfo**：订阅数据库（经 APA PsycNet 或第三方平台）。22 个大类、135 个子类，Thesaurus 条目超过 8,400 个（出自维基引述 2007 年第 11 版，**已过时** ⚠）[3P R59]。官方页面无法程序化读取 ⚠。
- **v2（仅元数据）**：
  - 【合规】不做任何 PsycNet 或 PsycInfo 自动化。
  - 摘要缺口靠 PubMed（有则用）、OpenAlex（计费）、PsyArXiv 预印本补。
  - 提供"用户导入 RIS/BibTeX（含 PsycInfo 导出）"这一合法通道。
  - 全文由用户在自己的会话中手动获取。

#### 2.4.14 SAGE（APS 期刊：Psych Sci、PPS、CPS、AMPPS、CDPS）

- **本日**：`journals.sagepub.com` 从本机网络在 **TLS 握手阶段即中断**（`SSL_ERROR_SYSCALL`）。v1 在 2026-07-20 记载为 Cloudflare 风险评分 403 [LIVE][v1]。需要换网络复测（§4）。
- **元数据**：Crossref APS 刊摘要覆盖 91–98%；每篇都带 `journals.sagepub.com/page/policies/text-and-data-mining-license`（tdm）许可，以及 `journals.sagepub.com` 的 text-mining link [LIVE]。
- **OA 比例**：*Psych Sci* 2026 年 28/46 为 CC（BY 15、BY-NC 13）；AMPPS 全 OA（DOAJ）[LIVE]。SAGE TDM 政策旧 URL 已 404，新条款页内容未读到 ⚠ [LIVE R60]。
- **PubMed/PMC 覆盖偏低**：*Psych Sci* 2025 年 66/38，AMPPS 0/0 [LIVE]。
- **v1**：catalog 登记为 `sage`（planned）。
- **v2（P1）**：元数据走 Crossref；CC 全文可共享；订阅全文按用户自取。

#### 2.4.15 Taylor & Francis Online

- **平台**：Atypon + Cloudflare。
- **robots**：`*` 组 `Crawl-delay: 1`，禁 `/action`、`/rss`、`/doi/epdf/`、`/doi/epub/`；只点名 GPTBot；显式 `Allow: /.well-known/tdmrep.json` [LIVE R61]。
- **最新**：`/feed/rss/{code}`，如 *Cognition & Emotion* 的 `pcem20`，本日 200，robots 允许；`/action/showFeed` 被禁 [LIVE]。
- **元数据**：Crossref **`abstracts-current` 为 0%**（*Cognition & Emotion*）[LIVE]。
- **全文**：2026 年 *C&E* 108 条中 47 条为 CC，另有 46 条带 `10.1080/policies-text-data-mining` 许可 [LIVE]。TDM 政策：订阅者与 OA 内容可做**非商业** TDM，建议事先联系，遵循 STM model licence；商业用途须另谈 [DOC R61]。
- **v2（P1/P2）**。

#### 2.4.16 Wiley Online Library

- **v1 已实现**：`wiley`，TDM API + token 门控 [v1]。
- **本日复核** [LIVE]：robots 与 v1 一致；`/feed/{eissn}/most-recent`（*Cognitive Science* 为 15516709）返回 200，且 robots 允许。
- *Cognitive Science*：Crossref 摘要 82%，2026 年 54/115 为 CC，106/115 带 Wiley TDM license 1.1，并带 text-mining link [LIVE]。
- **v2（P1）**：复用 v1。

#### 2.4.17 CSHL Press 与 SfN（HighWire 系）

- **CSHL（*Genome Research*、*Genes & Dev*）**：
  - robots 为 Drupal 模板；RSS `genome.cshlp.org/rss/current.xml` 被 302 到 `idp.sams-sigma.com`（HighWire SAMS Sigma 登录）[LIVE R63]。
  - Crossref 摘要 98%，但**没有 license 元数据**；DOI 前缀 `10.1101`（注意与旧 bioRxiv 前缀相同）[LIVE]。
  - PMC 2025 年覆盖 213/213。
- **SfN（*J Neurosci*）**：
  - robots.txt 即被 **Cloudflare 挑战** [LIVE R64]。
  - Crossref 显示 2026 年 439/523 条为 **CC BY-NC-SA**，`delay-in-days` 约 181–223，即**约 6 个月后开放**；link 指向 `syndication.highwire.org` [LIVE]。
  - PMC 2025 年 766 条，不少于 PubMed 的 718 [LIVE]。
- **v2**：P1/P2，全文一律走 PMC。

#### 2.4.18 核验补充：Royal Society Publishing 与 Hogrefe

> 由核验员补写。原文的出版商清单漏了生物学领域的 Royal Society（*Proc R Soc B*、*Biology Letters*、*Royal Society Open Science*。*RSOS* 也发表心理学 Registered Report，例如 10.1098/rsos.250367；2025 年以来 Crossref 书目检索"registered report"命中 19 条），也漏了欧洲心理学的主要出版商 Hogrefe。以下均为 2026-09-26 实测 [LIVE R84]，只列已核验事实。

| 项 | Royal Society（Crossref member 175，前缀 10.1098） | Hogrefe（Crossref member 101，前缀 10.1027） |
|---|---|---|
| 平台与 robots | `royalsocietypublishing.org` 的 robots 路径（`cassette.axd` 等）与 academic.oup.com 同构，推断为 Silverchair（⚠ 推断）。`*` 组只禁搜索、下载、登录等路径，没有 AI 爬虫专条，也没有 Crawl-delay | `econtent.hogrefe.com` 的 robots 为 Atypon 模板（`/na101/`、`/action` 等）。`*` 组 `Crawl-delay: 1`，禁 `/action`、`/rss`、`/search`；GPTBot 全禁；显式允许 `/.well-known/tdmrep.json` |
| Crossref 元数据 | 摘要覆盖：*Proc B* 96–97%、*Biol Lett* 96%、*RSOS* 99%。**ISSN 陷阱**：*Proc B* 有两条期刊记录，印本号 0962-8452（14,955 个 DOI，2026 年仅 10 条）和 eISSN 1471-2954（16,133 个 DOI，2026 年 429 条），必须 p/e 双查 | 摘要覆盖：*European Psychologist* 81%、*Zeitschrift für Psychologie* 71% |
| OA 与许可（2026 年，Crossref facet） | *Proc B* 428/429 为 CC BY，*RSOS* 519/519 为 CC BY，事实上全 OA（翻转公告 ⚠ 未核验） | 全社 357 条中 119 条带 CC（BY 84、BY-NC 22、BY-NC-ND 11、BY-ND 2），属混合 OA |
| PubMed / PMC（2025） | *Proc B* 604 / 550；*RSOS* 620 / 621，全文基本可经 PMC 取得 | *European Psychologist* PubMed 为 0，属于心理学 PubMed 覆盖缺口 |
| 最新通道 | Crossref `from-index-date`；站点 RSS ⚠ 未测 | Crossref `from-index-date`（robots 禁 `/rss`） |
| v2 建议 | P1：元数据走 Crossref（eISSN），全文走 PMC | P2：只取元数据，CC 条目按条许可共享，订阅内容按用户自取 |

### 2.5 会议与论文集

| venue | 平台 | 元数据通道 | 全文 | 本日证据 | 建议 |
|---|---|---|---|---|---|
| **CogSci**（Proceedings of the Annual Meeting of the Cognitive Science Society，ISSN 1069-7977） | eScholarship（UC），CloudFront WAF | **OAI-PMH** `https://escholarship.org/oai`，`set=cognitivesciencesociety`，`oai_dc`；**completeListSize 21,720**，每页 500，resumptionToken 24 小时后过期；`dc:source` 形如 "Proceedings … vol 48, iss 0"（卷号 = 届），带 `dc:subject`、摘要、`dc:rights` | OA（样本为 CC-BY），PDF 链接为 `https://escholarship.org/content/qt{id}/qt{id}.pdf` | 网页（`/uc/cognitivesciencesociety`、robots.txt）返回 CloudFront 403；**OAI 返回 200**；Crossref 以该 ISSN 查询为 404；PubMed 0 [LIVE R65] | **P1**：按会议 VenueSpec 建模（届 = 卷），OAI `from` 增量 |
| **PSB**（Pacific Symposium on Biocomputing） | World Scientific / PSB 站点 ⚠ | PubMed（2025 年 57 条，ISSN 2335-6936）；Crossref 以 2335-6936 与 2335-6928 查询均无 2026 记录 [LIVE] | ⚠ 未核验 | — | P2 |
| **ISMB** | 论文集作为 *Bioinformatics*（OUP）专刊发表 ⚠ | 经 *Bioinformatics* 的 ISSN 枚举 | 样本全为 CC BY [LIVE] | 专刊标识方式未核验 ⚠ | 并入 `oup_academic` |
| **RECOMB** | Springer LNCS/LNBI ⚠ | DBLP 与 Crossref（v1 已有 dblp 与 crossref 通道） | 订阅 | 未核验 ⚠ | 并入 `springer_link` |

心理学其他会议（Psychonomic Society 年会、SPSP、CCN 等）多数只有摘要集，本轮未调研 ⚠。

### 2.6 领域分类体系（后续主题树可用）

| vocab_id | 名称 | 覆盖 | 结构 | 获取 | 许可/条款 | 本日证据 | v2 用途 |
|---|---|---|---|---|---|---|---|
| `mesh` | MeSH 2026（NLM） | 生物医学全域，含 **F：精神病学与心理学** | 多层树号（如 Psychology `D011584` 的树号 `F04.096.628`，上位 `D001525`）+ 限定词 + 补充概念 | XML 文件 `desc2026.xml`、`qual2026.xml`、`supp2026.xml`、`pa2026.xml`（nlmpubs）；RDF/JSON 查询 API `id.nlm.nih.gov/mesh/lookup/descriptor?label=…`、`/mesh/{UI}.json` | 免费；须致谢 NLM；再分发须保持最新或标明版本；MeSH 翻译文件（MTMS）另有条款 [DOC R68] | 文件列表、lookup 与 JSON 均为 200 [LIVE] | **主题树主干**：用户兴趣以 MeSH UI 为节点，按树聚合与扩散；PubMed/PMC 条目自带 MeSH |
| `apa_thesaurus` | APA Thesaurus of Psychological Index Terms | 心理学 | 层级叙词表（维基引述约 8,400 条，2007 年第 11 版，⚠ 过时） | 仅在 PsycInfo 内 | APA 专有，需许可 | apa.org 被 Imperva 拦截，无法读取 ⚠ [3P R59] | **不嵌入**；如果用户导入的 PsycInfo 记录带叙词，只作用户私有标签 |
| `psycinfo_class` | PsycInfo 分类码 | 心理学 | 22 大类 / 135 子类（每条记录 1–2 个）[3P R59] | 代码表在 apa.org（无法读取 ⚠） | ⚠ 公开代码表能否用于产品需评估 | ⚠ | 可作为心理学一级学科划分的参考（按 MeSH-F 自建同义节点，不直接照搬） |
| `biorxiv_subjects` | bioRxiv 学科 | 生命科学 | 27 个平级类 | Crossref `group-title`、RSS 参数 | 平台元数据 | [DOC R8][LIVE] | 预印本粗分类到 MeSH 的映射 |
| `medrxiv_subjects` | medRxiv 学科 | 临床/健康（含 Psychiatry and Clinical Psychology） | 平级；Crossref 500 条样本中出现约 37 个 medRxiv 学科名，全表数量 ⚠ 未核验 | Crossref `group-title` | 同上 | [LIVE] | 同上 |
| `elife_subjects` | eLife 学科 | 生命科学 | 19 个 | `/subjects` API | CC BY 内容 | [LIVE] | 同上 |
| `osf_subjects` | OSF/PsyArXiv 学科 | 多学科 | 分层学科（bepress 三级体系 ⚠）| OSF API `subjects` | — | 本轮未展开 ⚠ | 心理学子领域标签 |
| `arxiv_qbio` | arXiv q-bio | 定量生物 | 10 类 | arXiv taxonomy | — | [DOC R69] | 与 v1 arXiv 分类体系统一 |
| `cognitive_atlas` | Cognitive Atlas | 认知科学（概念、任务、关系） | 概念图（is-a / part-of / 任务测量概念） | API `https://www.cognitiveatlas.org/api/v-alpha/concept?id=…` | **核验补充**：站点页脚标注 CC BY-SA 3.0 US（`creativecommons.org/licenses/by-sa/3.0/us/`）。ShareAlike 意味着含其概念的派生映射表再分发时必须沿用同一许可 [R83] | API 返回 200（含定义）[LIVE R67] | 心理学细粒度概念节点，补 MeSH-F 的不足 |

### 2.7 来源名录表（统一列，供设计阶段合并）

> 列义：`层级类型` 取 L1-publisher / L1-preprint / L1-journal-platform / L1-conference-platform / L2-repository / L2-aggregator；限速与 robots 列未另注的日期均为 2026-09-26；"v1"列中的"是"指 v1 已有可复用 adapter。

| source_id | 名称 | 层级类型 | 学科 | 平台技术栈 | 元数据通道 | 最新论文通道 | 全文通道与门控 | 认证方式 | 限速与 ToS/robots 要点（来源+日期） | v1 是否已支持 | 建议优先级及理由 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `pubmed` | PubMed / MEDLINE（NLM） | L2-aggregator | 生物医学、神经、部分心理 | NCBI Entrez | 官方 API（E-utilities）+ 年度 baseline 与日更 XML（FTP/HTTPS） | EDAT 或 `[crdt]` 日窗；日更文件（含删除）；网站 RSS 被 robots 禁 | 无全文，链到 PMC 或出版商；部分摘要可能受版权保护 | 可选 NCBI API key | 无 key 3 rps（响应头实测），有 key 10 rps；ESearch 上限 10,000；eutils robots `Disallow: /`（后端声明）；pubmed 站点 `Crawl-delay: 1`、禁 `/rss` [R28–R32] | 否 | **P0**：生命科学元数据、摘要与 MeSH 主干；心理学增强 |
| `pmc` | PubMed Central | L2-repository | 生物医学全文 | NCBI；S3 Cloud、OAI-PMH、BioC | OAI-PMH（`pmc_fm`/`oai_dc`）、E-utilities（db=pmc）、ID Converter | `[pmcrdat]` 日窗 + S3 每日 inventory；OAI `from` | OA 子集与作者手稿经 S3/OAI/BioC，按条 `license_code`（CC 或 TDM）门控；其余不可自动获取 | 无 | OAI 3 rps，超过 100 次请求须在美东非高峰，禁并发；**只允许 4 个自动化通道**；旧数据集 2026-08-24 周删除，OA Web Service 2026-08-25 下线 [R33–R40] | 否 | **P0**：OA 全文主通道 |
| `europe_pmc` | Europe PMC | L2-aggregator | 生命科学 + 预印本 | EBI REST + Annotations API | REST `search`（143 字段，`cursorMark`，pageSize ≤1,000）、`fullTextXML`、`supplementaryFiles` | `FIRST_IDATE`/`INDEX_DATE`/`UPDATE_DATE` | JATS 全文（PMC OA + 76,185 篇预印本）；新鲜预印本多无全文 | 无 | 无公开数值限速 ⚠；EBI ToU 写明影响他人即封禁；europepmc.org 网站 CF 挑战，ebi.ac.uk `Crawl-Delay: 10` [R23–R27] | 否 | **P0**：组合查询的联邦后端 |
| `biorxiv` | bioRxiv（openRxiv） | L1-preprint | 生命科学（27 类） | HighWire + Cloudflare | 官方 API（`/details`、`/funder` ⚠ 本日空体（核验修正：原写 `/funder` 正常）；`/pubs`、`/sum`、`/usage` 正常）；**委托 Crossref**（`member:54368` 或 owner prefix `10.64898` 一次覆盖新旧两种 DOI 字符串，摘要 100%）；EPMC | RSS `connect.biorxiv.org/biorxiv_xml.php?subject=`（RSS 1.0，最近 30 篇，`crawl-delay: 10`）；Crossref `from-posted-date` | OA，许可 6 选 1（约 19% 为 no-reuse）；S3 `biorxiv-src-monthly`（付费下载，MECA，月更，**不得作为再分发来源**） | 无（S3 需 AWS） | `*` 组 `Crawl-delay: 7`；ClaudeBot、GPTBot、CCBot、`curl`、`wget`、`python-requests` 全禁；API 主机无 robots [R5–R15] | 否 | **P0**：量大且质量高；元数据经 L2 更稳 |
| `medrxiv` | medRxiv（openRxiv） | L1-preprint | 临床/健康（含精神病学与临床心理学） | 同上 | 同上（server=medrxiv） | 同上 | 同上；S3 `medrxiv-src-monthly` | 同上 | `*` 组 `Crawl-delay: 7`，无 AI 专条 [R15] | 否 | **P0**（默认只订阅心理、神经相关学科，其余 P2） |
| `research_square` | Research Square（Springer Nature） | L1-preprint | 多学科（生医为主） | 自研 + Cloudflare | 委托 Crossref（10.21203，2026-08 共 8,995 条）+ EPMC；官方 API 申请制 ⚠ | Crossref、EPMC | **CC BY 4.0（Crossref 100%）**；PDF 在网站 | API 申请制 | `*` 组禁 `/api/`；anthropic-ai、ClaudeBot 等全禁 [R16] | 否（catalog T3 暂缓） | **P1**：只经 L2 |
| `psyarxiv` | PsyArXiv（OSF） | L1-preprint | 心理学 | OSF（Django/DRF，JSON:API） | **官方 API** OSF v2（`filter[provider]=psyarxiv`，total 64,345）+ 委托 Crossref（10.31234）+ EPMC（65,080） | API `filter[date_created][gte]`、`sort=-date_created` | OA；按条许可（CC BY 为主，另有 CC0）；`primary_file` → files API | 可选 PAT | 源码默认：匿名 100 次/小时、登录 10,000 次/天、burst 10/s、files 75/min（生产值 ⚠）；`api.osf.io` robots `Disallow: /`（⚠ 与 API 文档矛盾）；osf.io `crawl-delay: 10` [R18–R20] | 否 | **P0**：心理学预印本主源 |
| `osf_preprints` | OSF 其他社区（MetaArXiv、NewAddictionsX、EdArXiv、SocArXiv、BioHackrXiv 等） | L1-preprint | 元科学、成瘾、教育等 | 同上 | 同上（切换 provider） | 同上 | 同上 | 同上 | 同上；部分 provider 已停收（`allow_submissions=false`）[R18] | 否 | P1 |
| `preprints_org` | Preprints.org（MDPI） | L1-preprint | 多学科 | 自研 + Akamai | 委托 Crossref（10.20944，2026-08 共 2,505 条）+ EPMC | Crossref、EPMC | **CC BY 4.0（100%）** | — | **robots.txt 即返回 Akamai 403** [R22] | 否 | **P1**：只经 L2 |
| `ssrn_life` | SSRN 生医通道（Cell Press Sneak Peek / Lancet） | L1-preprint | 生医 | SSRN（Elsevier）+ Cloudflare | v1 `ssrn`（Crossref 10.2139，group-title 恒为 "SSRN"）；EPMC 只到 2023-10-28 | 无可靠通道 | 同 v1（浏览器 opt-in） | 免费账号 | v1：CF，1 req/5s；本日 TLS 失败 [v1][LIVE] | 部分（`ssrn`） | **P2 / 仅元数据**：现状未核验 |
| `authorea` | Authorea Preprints（Wiley） | L1-preprint | 多学科 | 自研 ⚠ | 委托 Crossref（10.22541）+ EPMC | Crossref | ⚠（Crossref 无 license 元数据） | — | ⚠ | 否 | P2 |
| `arxiv_qbio` | arXiv q-bio（10 类） | L1-preprint | 定量生物、计算神经 | arXiv | v1 `arxiv`（Query API + OAI-PMH） | v1 listing/OAI | OA | 无 | v1：1 req/3s [v1] | **是**（adapter 已有，需加 VenueSpec） | **P0**：零成本 |
| `f1000_platforms` | F1000Research、Wellcome Open Res、Open Res Europe、VeriXiv | L1-journal-platform | 生医、多学科 | F1000 ⚠ | EPMC + Crossref | EPMC | OA ⚠ | — | ⚠ | 否 | P2 |
| `psycharchives` | PsychArchives（ZPID） | L2-repository | 心理学 | 仓储 + OAI | OAI-PMH `…/oai/request` | OAI `from` | OA，按条许可 ⚠ | — | `Crawl-delay: 2` [R66] | 否 | P2 |
| `cell_press` | Cell Press（Elsevier） | L1-publisher | 生命、神经、认知（TICS） | Atypon（推断）+ Cloudflare；另有 ScienceDirect | 委托 Crossref（**摘要 0%**）+ PubMed（摘要）；Elsevier API | `/{journal}/current.rss`、`/inpress.rss`（robots 允许，本日 200） | 混合 OA：2026 年旗舰刊 CC 约占 36–52%，按条许可门控（核验修正：原写"订阅为主"）；部分刊全 OA；订阅部分走 Elsevier Article Retrieval API（每用户自己的 key） | 用户 API key/insttoken、机构 SSO | `*` 组 `Crawl-delay: 1`，禁 `/action`（含 showPdf）与 `/rss`；AI bots 全禁；SD `*` 组全禁 [R46–R47] | **是**（`elsevier_sd`） | **P1**：元数据走 L2；全文按用户 |
| `elsevier_sd` | Elsevier ScienceDirect 期刊（Cognition、JML、Neuropsychologia 等非 Cell Press 刊） | L1-publisher | 心理、认知、神经、生命 | ScienceDirect + Cloudflare | 委托 Crossref（**摘要 0%**）+ PubMed（覆盖不全，JML 2025 年仅 8 篇）；Elsevier Search/Article API | Crossref `from-index-date`；ScienceDirect RSS 未测 ⚠ | 订阅 + 混合 OA（核验补充：2026 年 Cognition CC 135/254、JML 25/52）；Article Retrieval API（每用户自己的 key） | 用户 API key/insttoken、机构 SSO | SD `*` 组 `Disallow: /`，claude-code 等点名禁；API 主机无 robots（v1）[R47][v1] | **是**（`elsevier_sd`） | **P1**：与 `cell_press` 共用 adapter，只是 VenueSpec 不同 |
| `nature_portfolio` | Nature Portfolio（Springer Nature） | L1-publisher | 综合、生命、心理（Nat Hum Behav） | nature.com（Oscar Platform） | 委托 Crossref（摘要 12–47%）+ PubMed；Meta API（需 key） | `nature.com/{journal}.rss`（RSS 1.0） | 订阅 + 部分 OA（Nature 2026 年约 20% 为 CC）；TDM：非商业，API 150/min，直接下载 ≤1/s，**不得让第三方访问** | api_key、机构 IP/SSO | `*` 组宽松；anthropic-ai、ClaudeBot、Claude-Web 等全禁；文章页 cookie 跳转到 idp.nature.com [R42–R45] | 否 | **P1** |
| `springer_link` | Springer Nature Link（Springer、BMC、EMBO Press、Psychonomic 刊） | L1-publisher | 生命、心理（PB&R、BRM） | link.springer.com（Oscar Platform） | 委托 Crossref（**必须用 eISSN**）+ Meta API | `/journal/{id}` 页（允许）；**`search.rss` 不被 robots 允许** | BMC、EMBO 等全 OA；订阅内容同上 TDM 条款 | 同上 | `*` 组 `Disallow: /` + 允许清单；AI bots 全禁；BMC/EMBO 域名 301 到本站 [R44] | 部分（catalog `springer` planned） | **P1** |
| `aaas_science` | Science 系列（AAAS） | L1-publisher | 综合 | Atypon + Cloudflare | 委托 Crossref（摘要 85–98%）+ PubMed | `/action/showFeed?…jc=science`（有 Allow） | *Science* 订阅（2026 年 1,563 条中 101 条带复用许可，部分延迟 365 天）；Sci Adv 全 OA | 机构 | AI bots 全禁；政策页 403 ⚠ [R48] | 否 | **P1**（Sci Adv 全文走 PMC）/ *Science* 仅元数据 |
| `pnas` | PNAS | L1-journal-platform | 综合、生命、心理 | Atypon + Cloudflare | 委托 Crossref（摘要 85%）+ PubMed | `/action/showFeed?…jc=pnas`（有 Allow） | 2026 年 3,649/3,688 带 CC；**PMC 覆盖 98%** | — | 只点名 GPTBot；禁 `/doi/epdf/` 等 [R49] | 否 | **P0**：全文走 PMC，零出版商接触 |
| `elife` | eLife | L1-journal-platform | 生命、神经 | 自研（API 优先） | **官方 API**（`/articles` 19,543、`/reviewed-preprints` 4,806）+ Crossref（摘要 99%）+ GitHub XML | `/rss/recent.xml`；API `order=desc` | 全 OA（CC BY/CC0）；`cdn.elifesciences.org` TDM 链接 | 无 | 网站 `Crawl-delay: 10`；API 主机 robots `Disallow: /`；API 限速 ⚠ [R50] | 否 | **P1**：评估词表是强信号 |
| `plos` | PLOS | L1-publisher | 生命、医学、心理健康 | 自研 ⚠ | **官方 API**（Solr，无 key）+ Crossref（**必须用 eISSN**） | API `publication_date` 日窗；`/{journal}/feed/atom`（允许） | 全 OA（CC BY）；JATS `article/file?…type=manuscript`；allofplos 全量 | 无 | **10 次/分钟、300 次/小时、7,200 次/天，≤5 并发，≤100 行/请求，超限封 IP**；站点 `Crawl-delay: 30` [R51] | 否 | **P1** |
| `frontiers` | Frontiers | L1-publisher | 神经、心理、生命 | 自研 | 委托 Crossref（摘要 90–92%） | `/journals/{slug}/rss`（本日 200） | 全 OA（CC BY）；PMC 覆盖高 | 无 | `*` 组 `Allow: /`；条款页未读到 ⚠ [R52] | 否 | **P1**：全文走 PMC |
| `mdpi` | MDPI | L1-publisher | 生命、心理 | 自研 + Akamai | **OAI-PMH**（`oai_dc`/`oai_agris`；set 只按文章类型）+ Crossref（摘要 100%） | OAI `from`；Crossref | 全 OA（CC BY）；PMC | 无 | www 与 RSS 被 Akamai 403；OAI 可用但不稳定（15:20 UTC 正常，19:30–19:38 UTC 连续返回 504，核验补充）[R53] | 否 | **P1**：须配过载护栏 |
| `peerj` | PeerJ | L1-journal-platform | 生命、环境 | 自研 + Cloudflare | 委托 Crossref（摘要 100%） | RSS 被 CF 挑战，改走 Crossref | 全 OA；PMC 100% | 无 | `Crawl-delay: 2` [R54] | 否 | P2 |
| `oup_academic` | Oxford Academic（NAR、Bioinformatics、SCAN、Child Development） | L1-publisher | 生命、心理 | Silverchair + Cloudflare | 委托 Crossref（摘要 94–98%） | `/rss/site_*`（NAR 本日 200） | 部分刊全 OA；订阅内容按用户 | 机构 SSO（v1） | robots 无 AI 条目（本日复核）；v1 记载 CF 质询 [R55][v1] | **是**（`oup_silverchair`） | **P1** |
| `cambridge_core` | Cambridge Core（BBS、Psych Med） | L1-publisher | 心理、精神 | Cambridge Core + Cloudflare | 委托 Crossref（摘要 91–99%） | ⚠（本日 robots 即被挑战） | 订阅 + 部分 OA | 机构 | **本日 robots.txt 被 CF 挑战 403**（v1 07-20 时为 200）[R56] | 否（catalog planned） | P1/P2 |
| `annual_reviews` | Annual Reviews | L1-publisher | 综述 | ⚠ + Cloudflare | 委托 Crossref（摘要 93–96%） | RSS 被 CF 挑战，改走 Crossref | S2O：当年卷多为 CC | — | `*` 组 `Crawl-delay: 2` [R57] | 否 | P1（画像冷启动） |
| `apa_psycnet` | APA PsycNet（APA 期刊） | L1-publisher | 心理学核心 | APA 自研；apa.org 用 Imperva | 委托 Crossref（10.1037，**摘要 0%**）+ PubMed（部分） | Crossref `from-index-date`（无合规 feed） | 订阅（少量 CC）；PsycInfo 为订阅库 | 机构或个人订阅 | **`*` 组 `Disallow: /`**；ClaudeBot、anthropic-ai、Claude-Web 点名禁 [R58] | 否 | **仅元数据**：不做自动化 |
| `sage_journals` | SAGE Journals（APS 期刊） | L1-publisher | 心理 | Atypon + Cloudflare | 委托 Crossref（摘要 91–98%，带 TDM link） | ⚠（本日 TLS 中断），改走 Crossref | 混合（Psych Sci 2026 年 61% 为 CC；AMPPS 全 OA）；订阅内容按用户 | 机构 | 本日 TLS 握手中断；v1 记载 CF 403 [R60][v1] | 否（catalog planned） | **P1** |
| `tandf_online` | Taylor & Francis Online | L1-publisher | 心理、生命 | Atypon + Cloudflare | 委托 Crossref（**摘要 0%**） | `/feed/rss/{code}`（允许，本日 200） | 混合（C&E 2026 年 44% 为 CC）；TDM：非商业、需联系、STM 许可 | 机构 | `*` 组 `Crawl-delay: 1`，禁 `/action` 与 `/rss`；只点名 GPTBot；有 tdmrep.json [R61] | 否 | P1/P2 |
| `wiley_online` | Wiley Online Library | L1-publisher | 心理、生命 | Atypon + Cloudflare | 委托 Crossref（Cognitive Science 摘要 82%） | `/feed/{eissn}/most-recent`（允许） | 混合；**TDM API**（每用户 token） | TDM token | robots 同 v1 [R62][v1] | **是**（`wiley`） | **P1** |
| `cshl_press` | CSHL Press（Genome Res、Genes Dev） | L1-publisher | 基因组、分子 | HighWire（Drupal + SAMS Sigma）+ CF | 委托 Crossref（摘要 98%，无 license 元数据） | RSS 跳转登录，改走 Crossref | 订阅/延迟开放 ⚠；PMC 100% | 机构 | Drupal 模板 robots [R63] | 否 | P2（全文走 PMC） |
| `sfn_journals` | SfN（J Neurosci、eNeuro） | L1-journal-platform | 神经 | HighWire + Cloudflare | 委托 Crossref（摘要 84%） | ⚠（robots 被挑战），改走 Crossref | **约 6 个月后以 CC BY-NC-SA 开放**；PMC 766 | 机构 | robots.txt 即被 CF 挑战 [R64] | 否 | P1（全文走 PMC） |
| `cogsci_proceedings` | CogSci Proceedings | L1-conference-platform | 认知科学 | eScholarship（CloudFront WAF） | **OAI-PMH**（`set=cognitivesciencesociety`，21,720 条） | OAI datestamp | OA（CC BY），PDF 直链 | 无 | 网页 403，OAI 200；Crossref 与 PubMed 均无 [R65] | 否 | **P1** |
| `psb_proceedings` | Pacific Symposium on Biocomputing | L1-conference-platform | 计算生物 | ⚠ | PubMed（2025 年 57 条） | ⚠ | ⚠ | — | ⚠ | 否 | P2 |
| `ucpress_online` | UC Press 期刊（Collabra: Psychology） | L1-publisher | 心理 | online.ucpress.edu ⚠ | 委托 Crossref（摘要 99%） | Crossref | 全 OA（CC BY） | — | 本轮未取 robots ⚠ | 否 | P2 |
| `royal_society`（核验补充） | Royal Society Publishing（Proc B、Biol Lett、RSOS） | L1-publisher | 生物、多学科（含心理学） | Silverchair（推断 ⚠） | 委托 Crossref（10.1098，摘要 96–99%；**Proc B 必须用 eISSN**） | Crossref `from-index-date`；RSS 未测 ⚠ | 2026 年 Proc B、RSOS 事实上全 OA（CC BY）；PMC 覆盖高 | — | `*` 组无 AI 专条、无 Crawl-delay（2026-09-26）[§2.4.18] | 否 | P1：全文走 PMC |
| `hogrefe`（核验补充） | Hogrefe（European Psychologist、Z Psychol 等） | L1-publisher | 心理学（欧洲） | Atypon | 委托 Crossref（10.1027，摘要 71–81%） | Crossref（robots 禁 `/rss`） | 混合（2026 年全社 CC 119/357） | 机构 | `*` 组 `Crawl-delay: 1`，禁 `/action`、`/rss`；GPTBot 全禁 [§2.4.18] | 否 | P2：仅元数据 |
| `pubtator3`（核验补充） | NCBI PubTator3 | L2-aggregator（实体标注层） | 生物医学 | NCBI REST | `pubtator3-api/publications/export/biocjson?pmids=` | 随 PubMed 更新 | 只有标注，不含受限全文 | 无 | 限速 ⚠（第三方称 ≤3 rps）；许可 ⚠ [§2.3.4] | 否 | P1：实体图与实体过滤 |
| `icite`（核验补充） | NIH iCite / Open Citation Collection | L2-aggregator（引文指标层） | 生物医学 | NIH REST | `icite.od.nih.gov/api/pubs?pmids=` | — | 只有指标与引文链接 | 无 | 限速、许可 ⚠；文档页 401 [§2.3.4] | 否 | P1：RCR 与引文图特征 |
| — | Google Scholar；Sci-Hub/LibGen 等 | — | — | — | — | — | — | — | 【合规】ToS 与法律红线 | — | **排除** |

### 2.8 代表性期刊、会议到平台的映射

> 数据口径（均为 2026-09-26 实测 [R70–R72]）：
>
> - **Crossref**：`/journals/{ISSN}` 的 `total-dois` 与 `coverage.abstracts-current`，外加 `/journals/{ISSN}/works?filter=from-pub-date:2026-01-01,until-pub-date:2026-09-26` 的计数。
> - **PubMed/PMC**：`{ISSN}[is] AND 2025[dp]`、`{ISSN}[issn] AND 2025[pdat]` 的计数。
> - **OA**：DOAJ 按 ISSN 是否收录 + Crossref 2026 年条目许可 facet 或 40 条样本。
> - "印本号路由 0"表示按印本 ISSN 查 2026 年无记录，须改用 eISSN。

#### 2.8.1 生命科学（含神经、计算生物；28 个 venue）

| # | Venue | ISSN（p / e） | 出版平台（source_id） | Crossref 可枚举性：总 DOI / 2026 年 / 摘要覆盖 | PubMed / PMC（2025） | OA 情况 |
|---|---|---|---|---|---|---|
| 1 | Cell | 0092-8674 | `cell_press` | 可 / 26,747 / 463 / **0%** | 550 / 215 | 混合（**核验修正**：2026 年 CC 241/463，均为即时 VOR 许可；全部带 Elsevier TDM 许可） |
| 2 | Nature | 0028-0836 / 1476-4687 | `nature_portfolio` | 可 / 447,366 / 3,312（含新闻）/ 12% | 4,593 / 1,041 | 混合（2026 年 CC 656/3,312） |
| 3 | Science | 0036-8075 / 1095-9203 | `aaas_science` | 可 / 384,026 / 1,563 / 85% | 1,924 / 222 | 订阅（101 条带复用许可，部分延迟 365 天） |
| 4 | PNAS | 0027-8424 / 1091-6490 | `pnas` | 可 / 171,866 / 3,688 / 85% | 4,466 / 4,374 | 2026 年 99% 带 CC（BY-NC-ND 为主） |
| 5 | eLife | 2050-084X | `elife` | 可 / 23,021 / 1,547 / 99% | 1,445 / 1,446 | 全 OA（DOAJ：CC BY、CC0） |
| 6 | Nature Genetics | 1061-4036 / 1546-1718 | `nature_portfolio` | 可 / 11,748 / 306 / 23% | 432 / 223 | 混合 |
| 7 | Nature Neuroscience | 1097-6256 / 1546-1726 | `nature_portfolio` | 可 / 8,165 / 262 / 25% | 359 / 173 | 混合 |
| 8 | Nature Methods | 1548-7091 / 1548-7105 | `nature_portfolio` | **注意**：期刊记录被错挂为 "Nature Chemical Biology"，works 路由 DOI 正确 / 13,894（错挂口径）/ 253 / 18% | 457 / 183 | 混合 |
| 9 | Nature Communications | 2041-1723 | `nature_portfolio` | 可 / 92,701 / 10,076 / 47% | 12,633 / 12,633 | 全 OA（DOAJ） |
| 10 | Neuron | 0896-6273 | `cell_press` | 可 / 14,341 / 366 / **0%** | 396 / 141 | 混合（核验修正：2026 年 CC 130/366） |
| 11 | Molecular Cell | 1097-2765 | `cell_press` | 可 / 10,528 / 300 / **0%** | 396 / 151 | 混合（核验修正：2026 年 CC 123/300） |
| 12 | Current Biology | 0960-9822 | `cell_press` | 可 / 25,731 / 722 / **0%** | 918 / 176 | 混合（核验修正：2026 年 CC 266/722） |
| 13 | Cell Reports | 2211-1247 | `cell_press` | 可 / 17,203 / 1,226 / **0%** | 1,627 / 592 | 全 OA（DOAJ） |
| 14 | Science Advances | 2375-2548 | `aaas_science` | 可 / 20,410 / 2,717 / 98% | 3,171 / 3,184 | 全 OA（DOAJ） |
| 15 | PLOS Biology | 1544-9173 / 1545-7885 | `plos` | **印本号路由 0**；eISSN 得 413 / 总 8,713 / 82% | 571 / 569 | 全 OA（CC BY，个别 CC0） |
| 16 | PLOS Computational Biology | 1553-734X / 1553-7358 | `plos` | **印本号路由 0**；eISSN 得 737 / 总 13,029 / 95% | 886 / 884 | 全 OA |
| 17 | Nucleic Acids Research | 0305-1048 / 1362-4962 | `oup_academic` | 可 / 55,929 / 1,056 / 94% | 1,581 / 1,572 | 全 OA（DOAJ；2026 年 1,037/1,056 为 CC） |
| 18 | Bioinformatics（含 ISMB 论文集） | 1367-4803 / 1367-4811 | `oup_academic` | 可（印本号得 640，eISSN 得 705）/ 21,227 / 98% | 607 / 612 | 全 OA（**核验修正**：DOAJ 按 eISSN 1367-4811 收录，CC BY，自 2023 年起；2026 年 698/705 为 CC） |
| 19 | Genome Research | 1088-9051 / 1549-5469 | `cshl_press` | 可 / 6,375 / 155 / 98%（无 license 元数据；前缀 10.1101） | 213 / 213 | 订阅或延迟开放 ⚠ |
| 20 | The EMBO Journal | 0261-4189 / 1460-2075 | `springer_link`（EMBO Press 迁入） | **印本号路由 0**；eISSN 得 247（10.1038/s44318-…）/ 21,969 / 89% | 360 / 330 | 2026 年 244/247 为 CC BY（事实上全 OA；政策公告未核验 ⚠） |
| 21 | Molecular Systems Biology | 1744-4292 | `springer_link` | 可 / 1,667 / 67 / 88% | 105 / 99 | 全 OA（DOAJ） |
| 22 | Genome Biology | 1474-760X（Crossref 另记 1465-6906） | `springer_link`（BMC 迁入） | 可 / 9,087 / 380 / 56% | 441 / 441 | 全 OA（DOAJ） |
| 23 | Journal of Neuroscience | 0270-6474 / 1529-2401 | `sfn_journals` | 可 / 42,175 / 523 / 84% | 718 / 766 | 约 6 个月后开放（CC BY-NC-SA，439/523） |
| 24 | Annual Review of Biochemistry | 0066-4154 / 1545-4509 | `annual_reviews` | 可 / 3,103 / 24 / 96% | 22 / 10 | S2O（样本 23/24 为 CC） |
| 25 | Int J Mol Sci（IJMS） | 1422-0067 | `mdpi` | 可 / 114,593 / 8,065 / 100% | 12,341 / 12,342 | 全 OA（CC BY；按 ISSN 查 DOAJ 无结果 ⚠） |
| 26 | Frontiers in Neuroscience | 1662-4548 / 1662-453X | `frontiers` | 可 / 19,735 / 1,061 / 90% | 1,219 / 1,108 | 全 OA（DOAJ） |
| 27 | PeerJ | 2167-8359 | `peerj` | 可 / 21,597 / 1,238 / 100% | 1,752 / 1,752 | 全 OA（DOAJ） |
| 28 | PSB（会议） | 2335-6936 / 2335-6928 | `psb_proceedings` | **不可**（两个 ISSN 在 Crossref 均无） | 57 / 29 | ⚠ |

补充：RECOMB 属 Springer LNCS 体系，可经 DBLP + Crossref 按卷枚举（v1 已有这两个通道，未单独核验 ⚠）。

#### 2.8.2 心理学（含认知科学；30 个 venue）

| # | Venue | ISSN（p / e） | 出版平台（source_id） | Crossref 可枚举性：总 DOI / 2026 年 / 摘要覆盖 | PubMed / PMC（2025） | OA 情况 |
|---|---|---|---|---|---|---|
| 1 | Psychological Bulletin | 0033-2909 / 1939-1455 | `apa_psycnet` | 可 / 10,706 / 37 / **0%** | 50 / 4 | 订阅（少量 CC；AM 许可延迟 365 天） |
| 2 | Psychological Review | 0033-295X / 1939-1471 | `apa_psycnet` | 可 / 6,914 / 97 / **0%** | 119 / 5 | 订阅（样本 11/40 为 CC） |
| 3 | J Personality & Social Psychology | 0022-3514 / 1939-1315 | `apa_psycnet` | 可 / 14,722 / 184 / **0%** | 165 / 11 | 订阅（2026 年 CC 22/184） |
| 4 | J Exp Psych: General | 0096-3445 / 1939-2222 | `apa_psycnet` | 可 / 5,169 / 237 / **0%** | 221 / 21 | 订阅 |
| 5 | American Psychologist | 0003-066X / 1935-990X | `apa_psycnet` | 可 / 21,002 / 177 / **0%** | 155 / 13 | 订阅（部分 CC） |
| 6 | J Applied Psychology | 0021-9010 / 1939-1854 | `apa_psycnet` | 可 / 12,593 / 137 / **0%** | 128 / 1 | 订阅 |
| 7 | J Psychopathology & Clinical Science（原 J Abnormal Psych） | 2769-7541 / 2769-755X | `apa_psycnet` | 可（新 ISSN 下共 804）/ 162 / **0%** | 130 / 55 | 订阅 |
| 8 | Developmental Psychology | 0012-1649 / 1939-0599 | `apa_psycnet` | 可 / 11,231 / 350 / **0%** | 316 / 60 | 订阅 |
| 9 | Psychological Methods | 1082-989X / 1939-1463 | `apa_psycnet` | 可 / 2,053 / 124 / **0%** | 153 / 5 | 订阅 |
| 10 | Psychological Science | 0956-7976 / 1467-9280 | `sage_journals`（APS） | 可 / 5,727 / 46 / 98% | 66 / 38 | 混合（2026 年 CC 28/46） |
| 11 | Perspectives on Psych Science | 1745-6916 / 1745-6924 | `sage_journals`（APS） | 可 / 1,533 / 44 / 91% | 58 / 8 | 混合 |
| 12 | Current Directions in Psych Science | 0963-7214 / 1467-8721 | `sage_journals`（APS） | 可 / 2,226 / 31 / 98% | 22 / 19 | 混合 |
| 13 | Clinical Psychological Science | 2167-7026 / 2167-7034 | `sage_journals`（APS） | 可 / 1,095 / 67 / 97% | 45 / 24 | 混合 |
| 14 | AMPPS | 2515-2459 / 2515-2467 | `sage_journals`（APS） | 可 / 377 / 59 / 92% | **0 / 0** | 全 OA（DOAJ） |
| 15 | Annual Review of Psychology | 0066-4308 / 1545-2085 | `annual_reviews` | 可 / 1,917 / 34 / 93% | 58 / 6 | S2O（2026 年 CC BY 25/34） |
| 16 | Behavioral and Brain Sciences | 0140-525X / 1469-1825 | `cambridge_core` | 可 / 17,153 / 412（含评论）/ 99% | 224 / **0** | 订阅 |
| 17 | Psychological Medicine | 0033-2917 / 1469-8978 | `cambridge_core` | 可 / 14,651 / 290 / 91% | 389 / 396 | 混合 |
| 18 | Nature Human Behaviour | 2397-3374 | `nature_portfolio` | 可 / 2,556 / 213 / 19% | 332 / 98 | 混合 |
| 19 | Trends in Cognitive Sciences | 1364-6613 | `cell_press` | 可 / 4,326 / 174 / **0%** | 194 / 32 | 混合（核验修正：2026 年 CC 62/174） |
| 20 | Cognition | 0010-0277 | `elsevier_sd` | 可 / 6,659 / 254 / **0%** | 362 / 22 | 混合（核验补充：2026 年 CC 135/254） |
| 21 | J Memory and Language | 0749-596X / 1096-0821 | `elsevier_sd` | 可 / 2,731 / 52 / **0%** | **8** / 7 | 混合（核验补充：2026 年 CC 25/52） |
| 22 | Psychonomic Bulletin & Review | 1069-9384 / 1531-5320 | `springer_link` | 可 / 4,787 / 221 / 57% | 255 / 96 | 混合（2026 年 CC BY 139/221） |
| 23 | Behavior Research Methods | 1554-351X / 1554-3528 | `springer_link` | **印本号路由 0**；eISSN 得 275 / 5,595 / 62% | 341 / 212 | 混合 |
| 24 | Cognitive Science | 0364-0213 / 1551-6709 | `wiley_online` | 可 / 3,790 / 115 / 82% | 124 / 72 | 混合（2026 年 CC 54/115） |
| 25 | Child Development | 0009-3920 / 1467-8624 | `oup_academic`（由 Wiley 转入，DOI 所有权已归 OUP） | **印本号路由 0**；eISSN 得 231 / 12,388 / 94% | 149 / 61 | 混合 |
| 26 | Frontiers in Psychology | 1664-1078 | `frontiers` | 可 / 53,686 / 5,764 / 92% | 4,808 / 4,267 | 全 OA（DOAJ） |
| 27 | Collabra: Psychology | 2474-7394 | `ucpress_online` | 可 / 779 / 96 / 99% | 4 / 4 | 全 OA（DOAJ） |
| 28 | Social Cognitive & Affective Neuroscience | 1749-5016 / 1749-5024 | `oup_academic` | 可 / 2,369 / 79 / 97% | 126 / 126 | 全 OA（DOAJ） |
| 29 | Cognition and Emotion | 0269-9931 / 1464-0600 | `tandf_online` | 可 / 3,396 / 108 / **0%** | 257 / 8 | 混合（2026 年 CC 47/108） |
| 30 | CogSci Proceedings（会议） | 1069-7977 | `cogsci_proceedings` | **不可**（Crossref 404）；OAI-PMH 全量 21,720 条 | **0 / 0** | OA（CC BY） |

**从两表可以直接读出的结论**：

- (a) 心理学 APA、Elsevier、T&F 三家共 13 个核心刊在 Crossref 上摘要为 0，PMC 覆盖大多不到 20%。
- (b) 生命科学 OA 刊与 PNAS、J Neurosci 的全文几乎都能经 PMC 合规取得。
- (c) 5 个刊用印本 ISSN 查 2026 年记录为 0，必须改用 eISSN：PLOS Biol、PLOS Comput Biol、EMBO J、BRM、Child Dev；*Bioinformatics* 用印本号只能查到部分（640 对 705）。另有 *Nature Methods* 期刊记录错挂、*Genome Biology* ISSN 登记异常。ISSN 路由必须 p/e 双查。
  - 核验补充：DOAJ 也有同样问题。*Bioinformatics* 只能用 eISSN 查到。
  - 核验补充：*Proc R Soc B* 在 Crossref 被拆成两条期刊记录。印本号 0962-8452 下有 14,955 个 DOI、2026 年 10 条；eISSN 1471-2954 下有 16,133 个 DOI、2026 年 429 条。
- (d) 核验补充：Elsevier/Cell Press 刊 2026 年的即时 CC 占比约 36–53%（Cell 241/463、Cognition 135/254 等），属于混合 OA。"Crossref 摘要为 0"不代表"没有可共享全文"，全文门控必须按条读 `license`。

### 2.9 robots / WAF 横向矩阵与 feed 判定

| 主机 | 前置防护（本日） | `*` 组要点 | AI 爬虫点名（全禁） | feed 或关键路径判定（本地最长匹配判定器） |
|---|---|---|---|---|
| www.biorxiv.org | Cloudflare（HEAD 文章页 200） | `Crawl-delay: 7`，禁 `/search/` | ClaudeBot、GPTBot、CCBot、openai、ChatGPT-User、PerplexityBot 等，另禁 `curl`、`wget`、`python-requests` | 内容页允许，须 7 s 间隔 |
| www.medrxiv.org | Cloudflare | `Crawl-delay: 7` | 无 | 同上 |
| connect.biorxiv.org（核验补充） | — | `crawl-delay: 10`，无 Disallow | 无 | 学科 RSS（RSS 1.0）允许，须 10 s 间隔 |
| api.biorxiv.org / api.plos.org / api.springernature.com | —（Apache / istio） | 无 robots.txt（404） | — | API |
| api.osf.io / api.elifesciences.org / eutils.ncbi.nlm.nih.gov | — | **`Disallow: /`** | — | API 主机全禁，与官方 API 文档矛盾 ⚠ |
| osf.io | Google LB | `crawl-delay: 10`，禁 `/api/*` | PerplexityBot、GPTBot、Meta-ExternalAgent 等"行为不当"者 | — |
| www.researchsquare.com | Cloudflare | 禁 `/api/` | anthropic-ai、ClaudeBot、GPTBot、CCBot、Google-Extended 等 | — |
| www.preprints.org / www.mdpi.com | **Akamai 403**（连 robots.txt 也拒） | 不可读 | 不可读 | 全站不可自动化；MDPI 改用 `oai.mdpi.com` |
| pubmed.ncbi.nlm.nih.gov | — | `Crawl-delay: 1`，禁 `/api`、`/rss`、`/*/citedby/` 等 | — | `/rss/…` 被禁 |
| pmc.ncbi.nlm.nih.gov | istio-envoy | `Crawl-delay: 1`，`Allow: /articles/`、`/api/`、`/tools/`，其余禁 | — | 网页允许，**但 PMC 政策禁止任何非 4 通道的系统性获取** |
| www.ncbi.nlm.nih.gov/books | **reCAPTCHA** | — | — | 文档不可程序化读取 |
| europepmc.org | **Cloudflare managed challenge**（robots.txt 也被挑战） | 不可读 | 不可读 | 只用 ebi.ac.uk 上的 API |
| www.ebi.ac.uk | nginx | `Crawl-Delay: 10` | — | API 路径未单列 |
| www.cell.com | Cloudflare | `Crawl-delay: 1`，禁 `/action`、`/rss` | GPTBot、ChatGPT-User、CCBot、Google-Extended、PerplexityBot、anthropic-ai、ClaudeBot、Bytespider | `/cell/current.rss` 允许；`/action/showPdf` 禁止 |
| www.sciencedirect.com | Cloudflare | **`Disallow: /`** | ClaudeBot、anthropic-ai、Claude-Web、claude-code 全禁；Claude-SearchBot、Claude-User 为显式 `Allow: /`（核验修正：原写"部分允许"） | 文章页禁止 |
| www.nature.com | Oscar Platform | 禁 `/search` 等少数路径 | anthropic-ai、ClaudeBot、Claude-Web、GPTBot、ChatGPT-User、CCBot、Google-Extended、PerplexityBot、Bytespider | `/nature.rss` 允许 |
| link.springer.com | Oscar Platform | **`Disallow: /` + 允许清单** | 同上 | `/journal/…`、`/article/…`、`/content/pdf/…` 允许；**`/search.rss?…` 禁止** |
| *.biomedcentral.com、www.embopress.org | nginx 301 | —（robots 也被 301） | — | 全部 301 到 link.springer.com |
| www.science.org | Cloudflare | 禁 `/action` 等，**`Allow: /action/showFeed`** | Google-Extended、anthropic-ai、GPTBot、ChatGPT-User、CCBot | eTOC 允许 |
| www.pnas.org | Cloudflare | 同 Atypon 模板，**`Allow: /action/showFeed`** | GPTBot | eTOC 允许 |
| elifesciences.org | nginx | `Crawl-delay: 10`，禁 `/search`、`/download/` | Amazonbot 等 | `/rss/recent.xml` 允许 |
| journals.plos.org | Apache | **`Crawl-delay: 30`** | — | `/…/feed/atom` 允许 |
| www.frontiersin.org | — | `Allow: /`，只禁少数目录 | — | `/journals/{slug}/rss` 允许 |
| peerj.com | Cloudflare（RSS 被挑战） | `Crawl-delay: 2` | — | RSS 不可用 |
| academic.oup.com | Cloudflare | 无 AI 条目，无 Crawl-delay | — | `/rss/site_*` 允许 |
| www.cambridge.org | **Cloudflare 挑战（robots.txt）** | 不可读 | 不可读 | —（与 v1 07-20 不同） |
| www.annualreviews.org | Cloudflare（RSS 被挑战） | `Crawl-delay: 2` | — | RSS 不可用 |
| psycnet.apa.org | — | **`Disallow: /`**（只放行搜索引擎） | anthropic-ai、ClaudeBot、Claude-Web、GPTBot、CCBot、OAI-SearchBot、PerplexityBot 等 | 全部禁止 |
| www.apa.org | **Imperva/Incapsula** | 不可读 | 不可读 | 政策与词表页不可读 |
| journals.sagepub.com | **TLS 握手中断**（本机） | 不可读 | — | v1：CF |
| www.tandfonline.com | Cloudflare | `Crawl-delay: 1`，禁 `/action`、`/rss`，`Allow: /.well-known/tdmrep.json` | GPTBot | `/feed/rss/{code}` 允许；`/action/showFeed` 禁止 |
| onlinelibrary.wiley.com | Cloudflare | `Crawl-delay: 1`，禁 `/action`、`/rss` | GPTBot、Google-Extended | `/feed/{eissn}/most-recent` 允许 |
| genome.cshlp.org | Cloudflare | Drupal 模板 | — | RSS 302 跳转 SAMS Sigma 登录 |
| www.jneurosci.org | **Cloudflare 挑战（robots.txt）** | 不可读 | 不可读 | — |
| escholarship.org | **CloudFront WAF 403**（网页与 robots） | 不可读 | 不可读 | OAI `/oai` 返回 200 |
| www.psycharchives.org | — | `Crawl-delay: 2` | — | OAI 允许 |

> 判定器是本地实现的"Google 式最长匹配、Allow 在同长时优先"规则，属于调研工具，不是 v2 实现。v2 应使用经测试的 robots 解析库，并对 `$` 与 `*` 语义做回归用例。

### 2.10 可复用的开源客户端（GitHub，2026-09-26 经 `gh api` 核验）

| 仓库 | ★ | License | 最近推送 | 用途 | 评估 |
|---|---|---|---|---|---|
| biopython/biopython | 5,209 | NOASSERTION（Biopython License） | 2026-09-22 | `Bio.Entrez`（E-utilities） | 成熟；v2 可直接用或参考限速实现 |
| metapub/metapub | 160 | Apache-2.0 | 2026-09-24 | PubMed/PMC/Crossref 工具集 | 活跃 |
| titipata/pubmed_parser | 738 | MIT | 2025-07-31 | PubMed/PMC XML 解析 | 放缓（v1 已记） |
| gijswobben/pymed | 214 | MIT | 2021-12（**已归档**） | PubMed | 不用 |
| jannisborn/paperscraper | 542 | MIT | 2026-09-23 | PubMed、bio/med/chemRxiv | 活跃。核验补充：它的 bioRxiv/medRxiv dump（`paperscraper/xrxiv/xrxiv_api.py`）调用 `{api_base_url}/details/{server}`，**确认依赖 `/details`**，会直接受本次空体故障影响 [R82] |
| CenterForOpenScience/osf.io | 732 | Apache-2.0 | 2026-09-25 | OSF 服务端（限速源码依据） | — |
| osfclient/osfclient | 145 | BSD-3-Clause | 2023-10-17 | OSF 客户端 | 停滞 |
| CenterForOpenScience/SHARE | 107 | Apache-2.0 | 2026-09-01 | OSF 元数据聚合 | 参考 |
| PLOS/allofplos | 67 | MIT | 2026-09-09 | PLOS 全量 XML 语料 | 可用于全文初始化 |
| elifesciences/elife-article-xml | 30 | —（未标） | 2026-09-25 | eLife JATS 全量 | 可用于全文初始化 |
| elifesciences/api-raml | 4 | MIT | 2026-04-24 | eLife API 规范 | 参考 |
| springernature/springernature_api_client | 8 | MIT | 2026-08-10 | Springer Nature API 官方客户端 | 参考 |
| ElsevierDev/elsapy | 433 | BSD-3-Clause | 2022-11（**已归档**） | Elsevier API | 不用（v1 `elsevier_sd` 自研） |
| WileyLabs/tdm-client | 28 | MIT | 2026-07-02 | Wiley TDM | v1 已参考 |
| ropensci/europepmc | 32 | —（未标） | 2024-07-01 | Europe PMC（R） | 只作参考 |
| sckott/habanero | 251 | MIT | 2026-09-25 | Crossref | v1 已记 |

## 3. 对 v2 设计的启示

> 编号即结论，可直接转为设计条目；【合规】为硬约束。

1. **按学科和查询特征做来源路由（routing），而不是一刀切的主干。**
   - 生命科学：检索、摘要、主题走 `europe_pmc` 与 `pubmed`；枚举与 DOI 权威走 Crossref。
   - 心理学：Crossref 为主，PubMed 为增强，预印本走 `psyarxiv`。
   - 路由器需要每个 venue 的**覆盖画像向量**：Crossref 摘要率、按 p/e ISSN 可路由性、PubMed/PMC 覆盖率、DOAJ/OA 比例、最新通道可用性。§2.8 的 58 行数据就是首批样本，应作为种子数据入库并定期重测。
2. **摘要补全链是推荐系统的前置依赖。**
   - 顺序：Crossref → PubMed `efetch` → Europe PMC → 出版商 API（仅在当前用户凭证下）→ OpenAlex（计费，v1 已记）。
   - 缺摘要的卡片降级为"标题 + 期刊 + MeSH/主题 + 预印本摘要（如有关联）"，并在排序特征中显式标注 `abstract_source`。
   - 【合规】NLM 声明部分摘要受版权保护：平台可展示并注明来源，但不做摘要全量再分发（如导出 API）。
3. **许可证门控的共享层是多用户架构的核心不变量。**
   - 每个 asset 必须记录：`license_code`（归一到 CC0 / CC-BY / CC-BY-SA / CC-BY-ND / CC-BY-NC* / PMC-TDM / NO-REUSE / PUBLISHER-TDM / SUBSCRIPTION / UNKNOWN）、`content_version`（vor/am/tdm/preprint vN）、`delay_in_days` 与 `license_start`、`license_source`（Crossref、PMC JSON、OSF、bioRxiv 等）。
   - 设计伪代码（非实现）：`shareable = license in {CC0, CC-BY, CC-BY-SA} or (license startswith CC-BY-NC and deployment.non_commercial)`；`CC-BY-ND` 可共享原文但不得做 AI 改写或翻译类衍生展示 ⚠；`PMC-TDM` / `NO-REUSE` / `PUBLISHER-TDM` 只存私有派生特征（向量、关键词）加跳转链接，是否可行需法务确认 ⚠；`SUBSCRIPTION` 严格按用户私有存放。
   - 依据：PMC README"只分发许可允许再分发的数据"；bioRxiv S3"不作为再分发来源"；Springer Nature TDM 要求"第三方不可访问"。
4. **【合规】凭证、配额、存储三者都按用户隔离。**
   - Elsevier key/insttoken、Springer Nature API key、Wiley TDM token 是个人或机构授权，不得池化或跨用户复用。
   - 平台级凭证只用于公开元数据：NCBI API key、OSF PAT、Crossref polite 联系方式或 Metadata Plus。
   - 数据模型：`credential(owner_user_id, provider, scope, quota_state)`；订阅全文的 `asset.owner_user_id` 非空，且不得进入共享缓存。
5. **中央配额调度器 + 离峰批处理窗口。**
   - 需要管理的额度：NCBI（按 IP 或 key 汇总：3/10 rps）、PMC OAI（3 rps、禁并发、工作日白天超过 100 次须离峰）、PLOS（10 次/分钟）、OSF（匿名 100 次/小时）、Crossref public（5 rps、并发 1）、Springer TDM（150 次/分钟，按用户计）。
   - 多用户平台出口 IP 共享 NCBI 额度，必须用 token-bucket 统一计量。
   - 大批任务排到美东 21:00–05:00 与周末；用户实时查询优先命中已缓存或已索引数据。
6. **"最新论文"注册表 = feed URL × robots 快照 × 复核周期。**
   - §2.9 已给出首批判定（允许：Cell/PNAS/Science/Nature/Wiley/T&F/OUP/Frontiers/eLife/PLOS；禁止或不可用：Springer `search.rss`、PubMed `/rss`、APA、Annual Reviews、PeerJ、MDPI、CSHL）。
   - 所有 venue 的兜底统一为 Crossref `from-index-date`（v1 已有）、EPMC `FIRST_IDATE`、PubMed EDAT。feed 只作加速和低延迟通道，不作真值来源。
7. **Work / Version / Manifestation 三层模型与预印本合并。**
   - 版本标识要全部纳入 identifier 图（延续 v1 D-007）：bioRxiv 一个 DOI 带 vN（两个前缀）、OSF 每版本一个 DOI（`_vN`）、Research Square `/vN`、PMC `PMCID.N`（版本号不代表新旧）、eLife RP 版本 DOI。
   - 预印本到正式版的边来自：bioRxiv `/pubs`、OSF `attributes.doi`、Crossref `relation.is-preprint-of`/`has-version`、EPMC `HAS_PUBLISHED_VERSION`。多源投票，冲突进待审。
   - 卡片 UI 显示"已发表于 X"与版本差异提示。
8. **质量与评审信号直接进入推荐特征。**
   - eLife Assessment：significance 5 级 × strength 6 级，可作序数特征。
   - EPMC `HAS_VERSION_EVALUATIONS`（41,177 篇预印本）。
   - PubMed 出版类型（Review、RCT、Retracted Publication）与 PMC `is_retracted`：**撤稿必须过滤或强提示**。
   - SfN、PNAS 等许可的 delay 信息可用于"何时可读全文"提醒。
9. **主题树以 MeSH 为主干，加多词表 crosswalk。**
   - 节点主键用 MeSH UI，层级用树号（一个概念可以有多个树号，是 DAG 而不是严格树）。
   - 来源自带标签（bioRxiv/medRxiv 学科、eLife subjects、OSF subjects、arXiv q-bio、Cognitive Atlas 概念）经映射表挂到节点上，并记录映射置信度。
   - 用户兴趣画像存节点权重，支持在树或 DAG 上向上聚合、向下扩散，也支持"兄弟节点探索"。
   - 【合规】APA Thesaurus 与 PsycInfo 分类码受许可限制，不作产品内置词表。MeSH 再分发须标明版本（年度版本化）。
10. **Europe PMC 作为可下推（push-down）的联邦检索后端。**
    - v2 查询 DSL 应有"字段能力映射"：章节检索（METHODS/RESULTS/FIG/TABLE/DATA_AVAILABILITY）、实体检索（GENE_PROTEIN/DISEASE/CHEM/ORGANISM/GOTERM）、关系过滤（HAS_PUBLISHED_VERSION 等）直接翻译成 EPMC 查询。
    - 本地只为用户兴趣子集建向量与倒排索引，避免复制 EPMC 或 PMC 的全量全文索引。
    - 这也是"组合查询 + 路由 + 并行查找"在生命科学上成本最低的实现。
11. **稳定性：每个 P0/P1 来源至少 2 条元数据通道 + 金丝雀 + 漂移检测。**
    - 本日实证的漂移类型：
      - API 端点"200 空体"：bioRxiv `/details`，核验时 `/funder` 也是如此。
      - 服务下线：PMC OA Web Service。
      - 服务间歇超时（核验补充）：MDPI OAI 返回 504。
      - 期刊记录 ISSN 错挂：Crossref 1548-7091。
      - 印本号停用：PLOS 等 5 刊查 2026 年为 0，*Bioinformatics* 部分缺失；Proc R Soc B 被拆成两条期刊记录（核验补充）。
      - 平台迁移：BMC/EMBO 迁入 Springer Link，Child Development 迁入 OUP。
      - 前缀迁移：10.1101 → 10.64898。核验补充：Crossref 旧 DOI 记录的所有权也一起迁移，owner prefix 与 member 同时改变，旧的按前缀过滤查询会静默归零。
      - WAF 口径变化：Cambridge。
    - 金丝雀应检测：零字节、计数骤降、前缀或后缀模式不符、publisher/member 变化。
    - ISSN 路由同时查 p/e 两个号；venue 归属用 DOI 模式（如 `s41592`）交叉校验。
12. **VenueSpec 增加 `platform_history`、`doi_prefix_history`、`issn_routing`。** 把 v1 VenueEra 的思路扩展到期刊（平台与 DOI 所有权会追溯变更：旧 `10.1111/cdev.*` 已属 OUP），并且**永远不要只按 DOI 前缀路由**（`10.1101` 同时属于 CSHL 期刊与旧 bioRxiv）。核验补充：Crossref 的 `prefix` 过滤器按记录的 owner prefix 匹配，不按 DOI 字符串匹配。所以 `doi_prefix_history` 要分开记"DOI 字符串前缀"和"Crossref 所有者（member / owner prefix）"两条历史，枚举查询优先用 `member:`。
13. **【合规】全文获取架构只有三条合法通道。**
    - ① L2 OA 通道：PMC S3/OAI/BioC、EPMC、bioRxiv S3、PLOS/eLife。
    - ② 官方 TDM API：按用户使用 key。
    - ③ 用户侧会话：用户本机、浏览器或客户端代理用自己的机构登录取回，文件只落在该用户的私有存储。
    - 服务端直连出版商网页在本领域基本不可行（Cloudflare/Akamai/Imperva/CloudFront/TLS 拦截普遍），且不得对抗。
14. **【合规】AI-bot 条款与 LLM 链路。**
    - nature.com、link.springer.com、cell.com、science.org、psycnet、bioRxiv、Research Square 都点名禁止 Claude 或 anthropic 系爬虫。
    - v2 的 LLM 组件（摘要、推荐解释）只处理已合规取得的数据，不作为网页抓取主体。
    - 抓取 UA 始终是诚实的产品 UA，并为每个主机记录其 AI 条款快照，供审计。
15. **心理学的缺口要产品化应对，不能用技术手段硬补。**
    - APA 全站禁爬，APA/Elsevier/T&F 心理学刊在 Crossref 上摘要为 0。
    - 应对方式：优先关联 PsyArXiv 预印本（样本 30% 带 `is-preprint-of`）；OpenAlex 摘要（计费）；开放"用户导入"（RIS/BibTeX/PsycInfo 导出）与 OpenURL/link resolver（跳转到用户机构），作为合法补充。
    - 核验补充：Elsevier 心理学刊 2026 年约一半带即时 CC 许可（Cognition 135/254、JML 25/52）。这部分可以在用户自有 Elsevier key 下取全文补摘要，PMC 有收录的也可以从 PMC 取。平台级 key 能否批量取 CC 内容，要先查 Elsevier API 条款，⚠ 未核验。另外 ScienceDirect 网页对 `*` 全禁，不能爬。
16. **会议论文集用 OAI 建模。** CogSci 在 Crossref 与 PubMed 都没有，只能用 eScholarship OAI（`dc:source` 带卷号）。按会议 VenueSpec（届 = 卷）处理，与 v1 conference 族同构。
17. **不做全量镜像，做"兴趣子图"缓存。**
    - 体量：PubMed 4,000 万以上、PMC 约 800 万版本、EPMC 预印本 125 万、bioRxiv 每月 4–5 千篇、PsyArXiv 每天约 40 条。
    - 按全体用户的兴趣并集（MeSH 节点、期刊、作者、关键词订阅）增量拉取与缓存，其余按需实时查询。
    - 若确需全量元数据，PubMed baseline + updatefiles 是唯一条款清晰、零 API 配额的 bulk 通道。
18. **落地优先级（与 §2.7 一致）。**
    - **P0**：`pubmed`、`europe_pmc`、`pmc`、`biorxiv`、`medrxiv`（元数据经 Crossref + EPMC）、`psyarxiv`、`arxiv_qbio`、`pnas`（全文经 PMC）；复用 v1 `crossref` 做期刊枚举。
    - **P1**：`plos`、`elife`、`nature_portfolio`/`springer_link`、`cell_press` 与 `elsevier_sd`（同一 adapter）、`wiley_online`（复用 `wiley`）、`oup_academic`（复用 `oup_silverchair`）、`frontiers`、`mdpi`、`sage_journals`、`cogsci_proceedings`、`research_square`、`preprints_org`、`annual_reviews`、`sfn_journals`、`osf_preprints`；核验补充 `royal_society`、`pubtator3`、`icite`。
    - **P2 / 仅元数据**：`apa_psycnet`、`aaas_science`（*Science* 主刊）、`cambridge_core`、`tandf_online`、`cshl_press`、`peerj`、`authorea`、`f1000_platforms`、`psycharchives`、`ssrn_life`、`psb_proceedings`、`ucpress_online`；核验补充 `hogrefe`。
    - **排除**：盗版源、Google Scholar 自动化、PsycNet/PsycInfo 自动化、任何对抗 WAF 的手段。

## 4. 未决问题与风险

| # | 问题/风险 | 影响 | 建议下一步 |
|---|---|---|---|
| Q1 | bioRxiv `/details` 本日返回 200 空体（14:56–15:43 UTC 持续），是故障还是退役？`/pubs` 对 10.64898 前缀的 DOI 查询失效（第三方 2026-09-22 报告） | 版本与 `jatsxml` 信息缺失。核验补充：同日 19:2x UTC `/funder` 也是空体；paperscraper 的 xrxiv 模块确认调用 `/details`，会同时失效；`/pubs` 的 DOI 路径在核验时仍解析不了 10.64898 | 设计上不依赖 `/details`、`/funder`，走 Crossref（`member:54368`）+ EPMC；挂金丝雀每日探测；向 openRxiv 确认 |
| Q2 | API 主机 robots 全禁（`api.osf.io`、`api.elifesciences.org`、`eutils`）与官方 API 文档邀请程序化使用相矛盾 | 按 AGENTS.md，robots 例外须文档记载理由 | v2 设计写一条统一 ADR："文档化 API 以其 ToS 与用法指南为准，robots 约束网页爬取"，并逐站发邮件确认（COS、eLife、NCBI） |
| Q3 | Europe PMC 无公开数值限速；多用户规模下可能被封 | P0 后端的可用性 | 上线前联系 EBI；实现自适应退避和结果缓存 |
| Q4 | PubMed 摘要版权声明、CC-ND 与"AI 摘要/翻译"是否构成演绎、no-reuse 预印本能否做派生向量索引 | 共享层门控规则的法律边界 | 需法务意见；在得到结论前，默认只存派生特征 + 链接，不展示改写内容 |
| Q5 | Springer Link robots 允许清单不含 `search.rss`，而 v1 catalog 记载了该检索 RSS 用法 | v1 现有合规口径 | 对 v1 做一次合规复核（本文不改 v1 文档） |
| Q6 | Cambridge、J Neurosci 的 robots.txt 本日即被 CF 挑战；SAGE、SSRN 从本机 TLS 中断（可能与本地代理网络有关） | 这些站点的事实状态不确定 | 换网络（机构网、无代理）复测，并与 v1 07-20 数据比对 |
| Q7 | APA 官方页（TDM、Thesaurus、分类码）、PNAS/AAAS/Annual Reviews/SAGE 政策页、Research Square API 条款、Frontiers 条款都无法程序化读取 | 相关事实为 ⚠ | 由人工浏览器阅读后补录（记录版本日期）；APA TDM 需向 APA 书面确认 |
| Q8 | Cell Press Sneak Peek 现状未知；EPMC 的 SSRN 流停在 2023-10 | 生医预印本的 SSRN 子集缺失 | 优先级低，维持 P2 |
| Q9 | 按 ISSN 查 DOAJ 找不到 IJMS。核验修正：IJMS 按刊名也查不到，确实不在 DOAJ；*Bioinformatics* 其实已被 DOAJ 收录（eISSN 1367-4811，2023 年起），只是用印本号查不到 | 以期刊为单位的 OA 判定不可靠，DOAJ 查询也要 p/e 双查 | OA 判定一律用条目级 license（Crossref、PMC JSON），DOAJ 只作辅助，查询时 p/e ISSN 都要试 |
| Q10 | bioRxiv S3 为 requester-pays，且禁止再分发 | 成本与用途受限 | 只在"内部 TDM/向量化"场景使用，并先做成本估算（MECA 月包体量未测 ⚠） |
| Q11 | PMC 作者手稿 `license_code=TDM`：可做 TDM 与合理使用，但平台展示全文的边界不清；NIH 零 embargo 后比例上升。核验补充：PMC AWS FAQ 称已分发的作者手稿"available for commercial reuse regardless of license"，但没有说明能否向第三方展示全文 | 共享层规则 | 默认按私有 TDM 处理，展示时跳转到 PMC 原页；向 PMC Help Desk 书面确认"商用再利用"是否包括平台内展示 |
| Q12 | Crossref public 池并发为 1，多用户后台会成为瓶颈；polite 池需要运营联系方式（本次为隐私未带邮箱） | 枚举吞吐 | v2 使用平台运营邮箱进入 polite 池，或评估 Metadata Plus |
| Q13 | OSF 源码默认限速与生产值可能不同；PsyArXiv `meta.total` 是否含多版本未确认 | 容量估算 | 用平台 PAT 实测响应头；按 `is_latest_version` 去重 |
| Q14 | OSF bepress 学科体系、medRxiv 学科全表未核验。Cognitive Atlas 许可已核验为 CC BY-SA 3.0 US（核验补充） | 主题树 crosswalk；ShareAlike 会约束含其概念的派生映射表的再分发许可 | 设计阶段补查；Cognitive Atlas 映射表单独存放并标注 SA 许可 |
| Q15 | 心理学会议（Psychonomics、SPSP、CCN）与 ISMB/RECOMB 的具体可枚举方式未核验 | 会议覆盖 | 第二轮调研 |
| Q16 | 跨法域 TDM 例外（EU DSM 第 3 条、UK CDPA）与美国合理使用不同；Elsevier/Cambridge 的 TDMRep 以 EU 例外为条件 | 多用户平台部署地与用户所在地会影响合规 | 在 v2 合规设计中引入"部署法域 + 用户法域"参数 |

## 5. 参考来源

> 除另注外，访问/核验日期均为 **2026-09-26**。`[LIVE]` 类条目给出实测 URL（只读 GET）。

- **[R1]** openRxiv — Introducing openRxiv（2025-03-11 公告）：https://openrxiv.org/introducing-openrxiv/ 〔WebFetch〕
- **[R2]** openRxiv — 2025 year in review（稿量、80% 发表率、DOI 前缀 10.64898）：https://openrxiv.org/2025-year-in-review/ 〔WebFetch〕
- **[R3]** Nature News d41586-025-00762-4（openRxiv 与 CZI 资助；本次只经检索摘要取得，直接访问被 303 跳转到 idp.nature.com）：https://www.nature.com/articles/d41586-025-00762-4
- **[R4]** Science News：bioRxiv 与 medRxiv 迁入新非营利组织（检索摘要）：https://www.science.org/content/article/bid-expand-biorxiv-and-medrxiv-preprint-servers-move-newly-formed-nonprofit
- **[R5]** bioRxiv API 文档：https://api.biorxiv.org/ 〔WebFetch〕
- **[R6]** bioRxiv TDM（S3 `biorxiv-src-monthly`）：https://www.biorxiv.org/tdm 〔WebFetch〕
- **[R7]** medRxiv TDM（S3 `medrxiv-src-monthly`）：https://www.medrxiv.org/tdm 〔WebFetch〕
- **[R8]** bioRxiv Alerts/RSS 与学科列表：https://www.biorxiv.org/alertsrss ；medRxiv：https://www.medrxiv.org/alertsrss 〔WebFetch〕
- **[R9]** bioRxiv FAQ（许可 6 选 1）：https://www.biorxiv.org/about/FAQ 〔WebFetch〕
- **[R10]** GitHub issue hherb/bmlib#325（`/details` 空 200，2026-09-26）：https://github.com/hherb/bmlib/issues/325 ；相关 #323：https://github.com/hherb/bmlib/issues/323 〔WebFetch/检索〕
- **[R11]** GitHub issue cyanheads/biorxiv-mcp-server#46（`/pubs` 不识别 10.64898 DOI，2026-09-22）：https://github.com/cyanheads/biorxiv-mcp-server/issues/46 〔WebFetch〕
- **[R12]** [LIVE] bioRxiv API：https://api.biorxiv.org/details/biorxiv/2025-03-01/2025-03-02/0/json （空体）；https://api.biorxiv.org/pubs/biorxiv/2025-03-01/2025-03-02/0 ；https://api.biorxiv.org/sum/m/json ；https://api.biorxiv.org/usage/m/medrxiv/json
- **[R13]** [LIVE] Crossref prefixes：https://api.crossref.org/prefixes/10.64898 、/10.1101、/10.21203、/10.20944、/10.31234、/10.22541、/10.2139
- **[R14]** [LIVE] Crossref works（posted-content、许可与 relation facet）：https://api.crossref.org/works?filter=prefix:10.64898,type:posted-content,from-posted-date:2026-08-01,until-posted-date:2026-08-31&rows=0&facet=license:* （其他前缀同构）
- **[R15]** [LIVE] robots：https://www.biorxiv.org/robots.txt ；https://www.medrxiv.org/robots.txt ；https://api.biorxiv.org/robots.txt （404）
- **[R16]** Research Square：API 申请页 https://www.researchsquare.com/request-api （前端渲染，未取到正文）；robots [LIVE] https://www.researchsquare.com/robots.txt
- **[R17]** Wikipedia：Research Square（2022 年被 Springer Nature 收购；检索摘要）：https://en.wikipedia.org/wiki/Research_Square
- **[R18]** [LIVE] OSF API：https://api.osf.io/v2/preprints/?filter[provider]=psyarxiv&page[size]=2&sort=-date_created ；https://api.osf.io/v2/providers/preprints/?page[size]=100
- **[R19]** OSF 源码限速默认值（`develop` 分支，最近提交 2026-07-28，`gh api` 读取）：https://github.com/CenterForOpenScience/osf.io/blob/develop/api/base/settings/defaults.py
- **[R20]** [LIVE] robots：https://osf.io/robots.txt ；https://api.osf.io/robots.txt
- **[R21]** PsyArXiv Blog（2026-01-27，OSF 检索语法）：https://blog.psyarxiv.com/2026/01/27/how-to-search-for-psyarxiv-preprints-on-the-osf-platform/ 〔WebFetch〕
- **[R22]** [LIVE] https://www.preprints.org/robots.txt （Akamai 403）
- **[R23]** [LIVE] Europe PMC REST：https://www.ebi.ac.uk/europepmc/webservices/rest/search ；字段 https://www.ebi.ac.uk/europepmc/webservices/rest/fields?format=json
- **[R24]** [LIVE] Europe PMC 全文与补充材料：https://www.ebi.ac.uk/europepmc/webservices/rest/PMC12314748/fullTextXML ；…/PMC12314748/supplementaryFiles
- **[R25]** [LIVE] Europe PMC Annotations API：https://www.ebi.ac.uk/europepmc/annotations_api/annotationsByArticleIds?articleIds=PMC%3A12314748&format=JSON
- **[R26]** EMBL-EBI Terms of Use：https://www.ebi.ac.uk/about/terms-of-use/ 〔curl〕
- **[R27]** [LIVE] https://europepmc.org/robots.txt （CF 挑战）；https://www.ebi.ac.uk/robots.txt
- **[R28]** PubMed FTP README（2026-01-30 更新）与目录：https://ftp.ncbi.nlm.nih.gov/pubmed/README.txt ；https://ftp.ncbi.nlm.nih.gov/pubmed/baseline/ ；https://ftp.ncbi.nlm.nih.gov/pubmed/updatefiles/
- **[R29]** NCBI Insights：New API Keys for the E-utilities（2017-11-02）：https://ncbiinsights.ncbi.nlm.nih.gov/2017/11/02/new-api-keys-for-the-e-utilities/ 〔WebFetch〕
- **[R30]** [LIVE] E-utilities `esearch`（`x-ratelimit-limit: 3`）：https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term=psychology%5Bmh%5D&retmode=json&retmax=0
- **[R31]** [LIVE] NCBI Bookshelf E-utilities 指南（返回 reCAPTCHA 页）：https://www.ncbi.nlm.nih.gov/books/NBK25497/
- **[R32]** [LIVE] robots：https://eutils.ncbi.nlm.nih.gov/robots.txt ；https://pubmed.ncbi.nlm.nih.gov/robots.txt ；https://pmc.ncbi.nlm.nih.gov/robots.txt ；https://www.ncbi.nlm.nih.gov/robots.txt
- **[R33]** PMC For Developers：https://pmc.ncbi.nlm.nih.gov/tools/developers/ 〔curl〕
- **[R34]** PMC OAI-PMH API（2026-08-20 修改）：https://pmc.ncbi.nlm.nih.gov/tools/oai/ 〔curl〕
- **[R35]** PMC OA Web Service（已下线说明，2026-08-19 修改）：https://pmc.ncbi.nlm.nih.gov/tools/oa-service/ 〔curl〕
- **[R36]** PMC FTP Service（2026-08-26 公告）：https://pmc.ncbi.nlm.nih.gov/tools/ftp/ 〔curl〕
- **[R37]** PMC AWS 与 FAQ（2026-08-31 修改）：https://pmc.ncbi.nlm.nih.gov/tools/pmcaws/ ；S3 README：https://pmc-oa-opendata.s3.amazonaws.com/README.txt 〔curl〕
- **[R38]** PMC OA Subset：https://pmc.ncbi.nlm.nih.gov/tools/openftlist/ 〔curl〕
- **[R39]** [LIVE] PMC ID Converter：https://pmc.ncbi.nlm.nih.gov/tools/idconv/api/v1/articles/?ids=PMC12314748&format=json
- **[R40]** [LIVE] BioC API：https://www.ncbi.nlm.nih.gov/research/bionlp/RESTful/pmcoa.cgi/BioC_json/PMC12314748/unicode ；OAI GetRecord：https://pmc.ncbi.nlm.nih.gov/api/oai/v1/mh/?verb=GetRecord&identifier=oai:pubmedcentral.nih.gov:12314748&metadataPrefix=oai_dc
- **[R41]** NIH NOT-OD-25-101（生效日提前至 2025-07-01）：https://grants.nih.gov/grants/guide/notice-files/NOT-OD-25-101.html ；NOT-OD-25-047（"without embargo"）：https://grants.nih.gov/grants/guide/notice-files/NOT-OD-25-047.html 〔WebFetch〕
- **[R42]** Springer Nature Developer Portal：https://dev.springernature.com/ 〔WebFetch〕；[LIVE] 无 key 返回 401：https://api.springernature.com/meta/v2/json?q=journal:Nature
- **[R43]** Springer Nature TDM 政策（1 req/s；API 150/min；安全服务器）：https://www.springernature.com/gp/researchers/text-and-data-mining 〔WebFetch〕
- **[R44]** [LIVE] robots 与重定向：https://www.nature.com/robots.txt ；https://link.springer.com/robots.txt ；https://genomebiology.biomedcentral.com/ （301）；https://www.biomedcentral.com/ （301）；https://www.embopress.org/journal/14602075 （301）
- **[R45]** Nature RSS：https://www.nature.com/nature.rss 〔WebFetch〕
- **[R46]** [LIVE] https://www.cell.com/robots.txt ；https://www.cell.com/cell/current.rss ；https://www.cell.com/cell/inpress.rss
- **[R47]** [LIVE] https://www.sciencedirect.com/robots.txt ；Elsevier API 配额见 v1 勘察 `docs/research/site-survey/publisher-platforms-econfin.md`（2026-07-20）
- **[R48]** [LIVE] https://www.science.org/robots.txt ；https://www.science.org/action/showFeed?type=etoc&feed=rss&jc=science ；政策页 403：https://www.science.org/content/page/science-journals-editorial-policies
- **[R49]** [LIVE] https://www.pnas.org/robots.txt ；https://www.pnas.org/action/showFeed?type=etoc&feed=rss&jc=pnas ；政策页 403：https://www.pnas.org/about/rights-and-permissions
- **[R50]** [LIVE] eLife API：https://api.elifesciences.org/articles?per-page=1&order=desc ；/reviewed-preprints；/subjects；评估词表 https://elifesciences.org/about/elife-assessments 〔WebFetch〕；robots https://elifesciences.org/robots.txt 、https://api.elifesciences.org/robots.txt ；RSS https://elifesciences.org/rss/recent.xml
- **[R51]** PLOS Search API FAQ（限速原文）：https://api.plos.org/solr/faq/ 〔curl〕；[LIVE] https://api.plos.org/search?q=doc_type:full ；robots https://journals.plos.org/robots.txt
- **[R52]** [LIVE] https://www.frontiersin.org/robots.txt ；https://www.frontiersin.org/journals/psychology/rss
- **[R53]** [LIVE] MDPI OAI-PMH：https://oai.mdpi.com/oai/oai2.php?verb=Identify （另有 ListSets、ListMetadataFormats）；https://www.mdpi.com/robots.txt （Akamai 403）
- **[R54]** [LIVE] https://peerj.com/robots.txt ；https://peerj.com/articles/index.rss （CF 挑战）
- **[R55]** [LIVE] https://academic.oup.com/robots.txt ；https://academic.oup.com/rss/site_5127/3091.xml
- **[R56]** [LIVE] https://www.cambridge.org/robots.txt （CF 挑战）；v1 对照 `docs/research/site-survey/publisher-platforms-econfin.md`
- **[R57]** [LIVE] https://www.annualreviews.org/robots.txt ；RSS（CF 挑战）https://www.annualreviews.org/rss/content/journals/psych/latestarticles?fmt=rss ；S2O 页（403）https://www.annualreviews.org/page/subscriptions/subscribe-to-open
- **[R58]** [LIVE] https://psycnet.apa.org/robots.txt ；https://www.apa.org/robots.txt （Incapsula）
- **[R59]** Wikipedia：PsycINFO（22/135 分类、Thesaurus 第 11 版）：https://en.wikipedia.org/wiki/PsycINFO 〔WebFetch〕
- **[R60]** [LIVE] https://journals.sagepub.com/robots.txt （TLS 中断）；旧 TDM 页 404：https://us.sagepub.com/en-us/nam/text-and-data-mining ；Crossref 许可 URL：https://journals.sagepub.com/page/policies/text-and-data-mining-license （未能读取）
- **[R61]** Taylor & Francis TDM 政策：https://taylorandfrancis.com/our-policies/textanddatamining/ 〔WebFetch〕；[LIVE] https://www.tandfonline.com/robots.txt ；https://www.tandfonline.com/feed/rss/pcem20
- **[R62]** [LIVE] https://onlinelibrary.wiley.com/robots.txt ；https://onlinelibrary.wiley.com/feed/15516709/most-recent ；v1 `docs/research/site-survey/publisher-platforms-p4-recheck.md`（2026-07-23）
- **[R63]** [LIVE] https://genome.cshlp.org/robots.txt ；https://genome.cshlp.org/rss/current.xml （302 到 SAMS Sigma）
- **[R64]** [LIVE] https://www.jneurosci.org/robots.txt （CF 挑战）
- **[R65]** [LIVE] eScholarship OAI：https://escholarship.org/oai?verb=Identify ；https://escholarship.org/oai?verb=ListRecords&metadataPrefix=oai_dc&set=cognitivesciencesociety ；网页（403）https://escholarship.org/uc/cognitivesciencesociety
- **[R66]** [LIVE] PsychArchives：https://www.psycharchives.org/oai/request?verb=Identify ；https://www.psycharchives.org/robots.txt
- **[R67]** [LIVE] Cognitive Atlas API：https://www.cognitiveatlas.org/api/v-alpha/concept?id=trm_4a3fd79d096be
- **[R68]** MeSH：[LIVE] https://nlmpubs.nlm.nih.gov/projects/mesh/MESH_FILES/xmlmesh/ ；https://id.nlm.nih.gov/mesh/lookup/descriptor?label=Psychology&match=exact&limit=3 ；https://id.nlm.nih.gov/mesh/D011584.json ；条款 https://www.nlm.nih.gov/databases/download/terms_and_conditions_mesh.html 〔curl〕
- **[R69]** arXiv Category Taxonomy：https://arxiv.org/category_taxonomy 〔WebFetch〕
- **[R70]** [LIVE] DOAJ API：https://doaj.org/api/search/journals/issn%3A{ISSN} （57 个 ISSN）
- **[R71]** [LIVE] Crossref 期刊与作品：https://api.crossref.org/journals/{ISSN} ；https://api.crossref.org/journals/{ISSN}/works?filter=from-pub-date:2026-01-01,until-pub-date:2026-09-26 ；https://api.crossref.org/works?filter=issn:{ISSN},from-pub-date:2026-01-01&rows=0&facet=license:* ；https://api.crossref.org/works/10.1111/cdev.14179
- **[R72]** [LIVE] E-utilities 计数：`esearch.fcgi?db=pubmed&term={ISSN}[is] AND 2025[dp]` 与 `db=pmc&term={ISSN}[issn] AND 2025[pdat]`（57 刊 + *Cognition & Emotion*）
- **[R73]** [LIVE] GitHub（`gh api repos/{owner}/{repo}`）：biopython/biopython、metapub/metapub、titipata/pubmed_parser、gijswobben/pymed、jannisborn/paperscraper、CenterForOpenScience/osf.io、osfclient/osfclient、CenterForOpenScience/SHARE、PLOS/allofplos、elifesciences/elife-article-xml、elifesciences/api-raml、springernature/springernature_api_client、ElsevierDev/elsapy、WileyLabs/tdm-client、ropensci/europepmc、sckott/habanero
- **[R74]** v1 仓库勘察（仓库内）：`docs/research/site-survey/metadata-apis.md`（2026-07-20/22）；`docs/research/site-survey/publisher-platforms-econfin.md`（2026-07-20）；`docs/research/site-survey/publisher-platforms-p4-recheck.md`（2026-07-23）；`docs/catalog/publishers-platforms.md`；`docs/catalog/preprint-platforms.md`
- **[R75]** UA Libraries Scholarly API Cookbook — OSF（检索摘要给出"匿名 100 次/小时、带 token 10,000 次/天"；本日直接访问 404）：https://ua-libraries-research-data-services.github.io/UALIB_ScholarlyAPI_Cookbook/src/python/osf.html

以下 R76–R84 为核验时新增（访问日期 2026-09-26）：

- **[R76]** Springer Nature 新闻稿（2022-12-01）"Springer Nature completes acquisition of Research Square Company"：https://group.springernature.com/gp/group/media/press-releases/springer-nature-completes-acquisition-of-research-square-company/23768186 〔WebFetch〕
- **[R77]** Elsevier Developer Portal — API Key Settings（Article Retrieval 每周 50,000、10 rps、TDM key 不限）：https://dev.elsevier.com/api_key_settings.html 〔WebFetch〕
- **[R78]** openRxiv 上线新闻稿（EurekAlert，2025-03-12，未写 CZI 金额）：https://www.eurekalert.org/news-releases/1076771 〔WebFetch〕
- **[R79]** Wei C-H 等，PubTator 3.0，*Nucleic Acids Research* 2024，DOI 10.1093/nar/gkae235（Crossref 核对）；[LIVE] https://www.ncbi.nlm.nih.gov/research/pubtator3-api/publications/export/biocjson?pmids=29355051
- **[R80]** Hutchins BI 等，The NIH Open Citation Collection，*PLOS Biology* 2019，DOI 10.1371/journal.pbio.3000385（Crossref 核对）；[LIVE] https://icite.od.nih.gov/api/pubs?pmids=29355051
- **[R81]** [LIVE] Crossref 所有权迁移证据：https://api.crossref.org/works/10.1101/2020.09.09.20191205 （prefix 10.64898、member 54368）；https://api.crossref.org/members/54368 ；https://api.crossref.org/members/246 ；https://api.crossref.org/works?filter=prefix:10.64898,type:posted-content,until-posted-date:2025-11-30&rows=0
- **[R82]** [LIVE] paperscraper 源码 `paperscraper/xrxiv/xrxiv_api.py`（`gh api` 读取 main 分支）：https://github.com/jannisborn/paperscraper/blob/main/paperscraper/xrxiv/xrxiv_api.py
- **[R83]** [LIVE] Cognitive Atlas 首页与 About 页页脚许可（CC BY-SA 3.0 US）：https://www.cognitiveatlas.org/ ；https://www.cognitiveatlas.org/about
- **[R84]** [LIVE] Royal Society 与 Hogrefe：https://royalsocietypublishing.org/robots.txt ；https://econtent.hogrefe.com/robots.txt ；https://api.crossref.org/journals/0962-8452 ；https://api.crossref.org/journals/1471-2954 ；https://api.crossref.org/prefixes/10.1027 ；https://api.crossref.org/prefixes/10.1098

## 核验记录

> **范围与方法**：对抗式事实核验（Verify 角色），默认怀疑，只认一手来源（官方文档页、API 实测响应、仓库源码、Crossref 记录与论文元数据）。核验日期统一记为 2026-09-26（UTC；被访服务器 `Date` 头为 2026-09-26 19:1x–19:4x GMT，本地时钟已进入 09-27 凌晨）。
>
> **与前次中断的衔接**：本节是文档中唯一的核验记录。核验开始时文档内没有核验记录节，也没有"核验修正/核验补充"标记，文件自调研员定稿（本地 2026-09-27 00:00:46）后未被改动，所以不存在前次中断留下的半截修改需要复核。
>
> **结论口径**：确认＝一手来源与正文一致；修正＝已就地改正，正文标"核验修正"；补充＝原文遗漏，已补写，正文标"核验补充"；未核验＝仍拿不到一手来源，正文标 ⚠；删除＝查无实据已删。本次**没有**发现编造的仓库、issue、论文或数字，因此无删除项。16 个 GitHub 仓库、3 个 GitHub issue、2 篇新增引用论文都能解析，且与描述一致。

**过程记录（可复现）**

- **UA 与纪律**：全部 curl 请求使用 `PaperCrawler-verify/0.1 (fact-check; personal research)`，不携带邮箱。
  - 先取 robots.txt，只访问 robots 允许的路径或 API 主机；同主机请求间隔 ≥0.7–2 s，bioRxiv 站点 ≥7 s。
  - 遇到 403 或挑战页只记录一次，不重试、不换 UA。
  - 没有访问 psycnet、sciencedirect、apa.org 的受限页面，因此 Imperva 与 Cloudflare 挑战只以 403 状态码记录。
- **API 实测**：
  - Crossref 约 70 次：`/prefixes`、`/members/54368|246`、`/journals/{ISSN}` 与 `/journals/{ISSN}/works`、`/works?filter=…&facet=license:*`、`/works/{DOI}`。
  - E-utilities 约 30 次：`esearch` 读 `x-ratelimit-*`，外加 `einfo`。
  - Europe PMC 约 20 次：`search`（idlist/lite）、`/fields`、`fullTextXML`、annotations。
  - OSF API 5 次；bioRxiv API 约 15 次，覆盖 `/details`、`/funder`、`/pubs`、`/pub`、`/publisher`、`/sum`、`/usage`。
  - eLife API 3 次；PLOS Search API 1 次（facet）；DOAJ 约 10 次；PMC ID Converter、BioC 各 1 次；MeSH lookup/JSON 2 次；eScholarship OAI 1 次；MDPI OAI 4 次（均超时或 504）；PubTator3 与 iCite API 各 1 次；Cognitive Atlas API 1 次。
- **文档与政策页**：
  - curl 读取：PMC `/tools/developers|oai|oa-service|ftp|pmcaws/`、PMC S3 `README.txt`、PubMed FTP `README.txt` 与目录、PLOS `solr/faq`、NIH `NOT-OD-25-101|047`、bioRxiv `/tdm`、`/about/FAQ`、`api.biorxiv.org` 文档页、MeSH 条款页、EMBL-EBI 条款页、arXiv taxonomy。
  - WebFetch 读取：openRxiv 两篇公告、EurekAlert 新闻稿、STAT 报道、Springer Nature TDM 页、Springer Nature 2022-12-01 新闻稿、eLife assessments 页、NCBI Insights 2017-11-02、Elsevier API key 设置页、维基 PsycINFO。
  - 读取失败：NCBI Bookshelf NBK25497 为 reCAPTCHA；apa.org class-codes 为 Imperva 空页；science.org 新闻为 403；PubTator3 API 文档为前端渲染；iCite `/api` 文档为 401。
- **robots.txt**：共 40 个主机，包括正文 §2.9 全部主机，另加 connect.biorxiv.org、royalsocietypublishing.org、econtent.hogrefe.com、cognitiveatlas.org。
- **GitHub（`gh api`）**：
  - 16 个仓库的 star、许可、`pushed_at` 与归档状态。
  - `CenterForOpenScience/osf.io` 的 `api/base/settings/defaults.py`、`api/base/throttling.py`，以及该文件最近提交时间。
  - `jannisborn/paperscraper` 的 `paperscraper/xrxiv/xrxiv_api.py`。
  - issue `hherb/bmlib#325/#323`、`cyanheads/biorxiv-mcp-server#46`，含评论与关闭原因。
- **WebSearch 5 次**：
  - `openRxiv Chan Zuckerberg Initiative $16 million bioRxiv medRxiv nonprofit March 2025`
  - `"openRxiv" "16 million" Chan Zuckerberg Nature news preprint servers`
  - `Springer Nature acquires Research Square 2022 press release`
  - `Cognitive Atlas license Creative Commons content cognitiveatlas.org terms`（结论以站点页脚原文为准）
  - `PubTator3 API "requests per second" limit pubtator3-api export biocjson`
- **中间文件**：均在会话 scratchpad 的 `verify-lsp/` 目录，不入库。

**核验统计**：共核验 54 组承重断言。
- 确认 39 组，其中多组附带补充细节，见表。
- 修正 13 组，其中 2 组是把原 ⚠ 改为已核验事实：Cognitive Atlas 许可、paperscraper 对 `/details` 的依赖。
- 未核验 2 组：CZI 金额改标 ⚠；E-utilities 离峰要求新标 ⚠。
- 删除 0 组。
- 另补 4 项覆盖缺口：Royal Society、Hogrefe、PubTator3、iCite。

| # | 断言 | 结论 | 依据来源 URL | 核验日期 |
|---|---|---|---|---|
| 1 | openRxiv 于 2025-03-11 接管 bioRxiv/medRxiv，原由 CSHL 支持，获 CZI 早期资助（§0、§2.2.1） | 确认 | https://openrxiv.org/introducing-openrxiv/ | 2026-09-26 |
| 2 | CZI 资助额 1,600 万美元（原标 3P 检索摘要） | 未核验（正文改标 ⚠）：官方公告与 2025-03-12 新闻稿均没有写金额，STAT 报道只说"substantial funding"，Nature 新闻页正文未能取回，Science 页 403 | https://openrxiv.org/introducing-openrxiv/ ；https://www.eurekalert.org/news-releases/1076771 ；https://www.statnews.com/2025/03/11/life-sciences-preprint-servers-openrxiv-richard-sever-qa/ | 2026-09-26 |
| 3 | 2025 年 bioRxiv 49,256、medRxiv 14,973 篇新稿；托管 38.9 万篇以上；约 80% 后续发表；2025-12-01 起新前缀 10.64898 | 确认。另附 `/sum` 按月加总 49,318，与年报差 62 | https://openrxiv.org/2025-year-in-review/ ；https://api.biorxiv.org/sum/m/json | 2026-09-26 |
| 4 | Crossref：10.64898 属 openRxiv（member 54368），10.1101 属 CSHL（member 246） | 确认（前缀层面） | https://api.crossref.org/prefixes/10.64898 ；https://api.crossref.org/prefixes/10.1101 | 2026-09-26 |
| 5 | "2026-08 以 10.1101 计的 posted-content 为 0 条"＝旧前缀不再新增；建议"两个前缀并查" | **修正**：Crossref 的 `prefix` 过滤器按 owner prefix 匹配。旧 `10.1101/…` 预印本记录已转入 openRxiv（owner prefix 10.64898，member 54368 共 441,217 条 posted-content；CSHL 只剩 34 条），`prefix:10.64898,until-posted-date:2025-11-30` 即有 383,608 条 2025-12 之前的记录，抽样均为 `10.1101/…`。改为按 `member:54368` 或 `prefix:10.64898` 单查（§0、§2.2.1、§2.7、§3 第 11–12 条） | https://api.crossref.org/works/10.1101/2020.09.09.20191205 ；https://api.crossref.org/members/54368 ；https://api.crossref.org/members/246 ；https://api.crossref.org/works?filter=prefix:10.64898,type:posted-content,until-posted-date:2025-11-30&rows=0 | 2026-09-26 |
| 6 | 10.64898 在 2026-08 共 5,693 条：CC BY 2,088（36.7%）、BY-NC-ND 1,665、bioRxiv no-reuse 837、BY-NC 587、medRxiv no-reuse 241、BY-ND 189 | 确认（另有 CC0 86 条） | https://api.crossref.org/works?filter=prefix:10.64898,type:posted-content,from-posted-date:2026-08-01,until-posted-date:2026-08-31&rows=0&facet=license:* | 2026-09-26 |
| 7 | 2026-09-01 至 07 共 1,342 条；500 条样本摘要 100%、relation 0、link 指向 syndication.highwire.org；含 "Psychiatry and Clinical Psychology" | 确认 | https://api.crossref.org/works?filter=prefix:10.64898,type:posted-content,from-posted-date:2026-09-01,until-posted-date:2026-09-07&rows=500&select=DOI,abstract,group-title,license,link,relation | 2026-09-26 |
| 8 | `api.biorxiv.org/details` 返回 200 + 0 字节 | 确认（19:1x UTC 复测，3 种形态仍为空体） | https://api.biorxiv.org/details/biorxiv/2026-09-01/2026-09-02/0/json | 2026-09-26 |
| 9 | `/pubs`、`/funder`、`/sum` 正常（§2.7） | **修正**：`/funder` 也返回 200 + 0 字节，含文档示例 URL；`/pubs`、`/pub`、`/publisher`、`/sum`、`/usage` 正常 | https://api.biorxiv.org/funder/biorxiv/2025-04-10/2025-07-10/00k4n6c32/45 ；https://api.biorxiv.org/pubs/biorxiv/2026-09-01/2026-09-02/0 | 2026-09-26 |
| 10 | 第三方 issue：bmlib #325/#323（2026-09-26，`/details` 空体）；biorxiv-mcp-server #46（2026-09-22，`/pubs` 无法按 10.64898 DOI 查询） | 确认；补充：#46 当日以客户端绕行方案关闭，上游未修，复测 `/pubs/medrxiv/10.64898/…` 仍解析失败 | https://github.com/hherb/bmlib/issues/325 ；https://github.com/cyanheads/biorxiv-mcp-server/issues/46 ；https://api.biorxiv.org/pubs/medrxiv/10.64898/2026.01.07.26343585/json | 2026-09-26 |
| 11 | `/sum`：2026-01 至 08 月新稿 3,924–5,165，修订稿 1,536–1,831 | 确认 | https://api.biorxiv.org/sum/m/json | 2026-09-26 |
| 12 | bioRxiv S3 `biorxiv-src-monthly` 为 requester-pays、us-east-1、每月 MECA 包、Back_Content 自 2018 年末；"not intended as a source for further redistribution"，须 link back、不得重新托管 | 确认 | https://www.biorxiv.org/tdm | 2026-09-26 |
| 13 | 许可 6 选 1；FAQ 称机器分析也应"free and unrestricted" | 确认 | https://www.biorxiv.org/about/FAQ | 2026-09-26 |
| 14 | 学科 RSS 为 Atom 1.0，最近 30 篇 | **修正**：实际为 RSS 1.0（`rdf:RDF`），30 个 item；`connect.biorxiv.org` robots 为 `crawl-delay: 10` | https://connect.biorxiv.org/biorxiv_xml.php?subject=neuroscience ；https://connect.biorxiv.org/robots.txt | 2026-09-26 |
| 15 | `www.biorxiv.org` robots：`*` 组 Crawl-delay 7、禁 `/search/`；ClaudeBot、GPTBot、CCBot、openai、python-requests/2.32.3、wget、curl 等全禁 | 确认 | https://www.biorxiv.org/robots.txt | 2026-09-26 |
| 16 | Research Square 于 2022 年被 Springer Nature 收购（原据维基）；In Review 关联 ⚠ | **修正**（改用一手来源）：2022-12-01 新闻稿称增持至全资；同稿称 In Review 覆盖 700 余种 SN 期刊，这是 2022 年口径，现状仍 ⚠ | https://group.springernature.com/gp/group/media/press-releases/springer-nature-completes-acquisition-of-research-square-company/23768186 | 2026-09-26 |
| 17 | 2026-08：Research Square（10.21203）8,995 条，100% CC BY；Preprints.org（10.20944）2,505 条，100% CC BY；COS（10.31234）1,162 条，CC BY 968、CC0 107；Authorea 412 条无 license | 确认 | https://api.crossref.org/works?filter=prefix:10.21203,type:posted-content,from-posted-date:2026-08-01,until-posted-date:2026-08-31&rows=0&facet=license:* （其余前缀同构） | 2026-09-26 |
| 18 | PsyArXiv `meta.total` 64,345；每版本一个 DOI（`_vN`）；`attributes.doi` 为正式版 DOI；PsyArXiv 为 pre-moderation；共 32 个 provider；mindrxiv 等 `allow_submissions=false` | 确认（total 随时间增至 64,354；样例 `w6phu_v1` 的 doi 为 `10.1037/abn0001175`） | https://api.osf.io/v2/preprints/?filter[provider]=psyarxiv&page[size]=100&sort=-date_created ；https://api.osf.io/v2/providers/preprints/?page[size]=100 | 2026-09-26 |
| 19 | OSF 源码默认限速：user 10000/day、non-cookie-auth 100/hour、burst 10/s、files 75/min、files-burst 3/s；最近提交 2026-07-28 | 确认；`NonCookieAuthThrottle` 只对未认证且无 cookie 的请求限流 | https://github.com/CenterForOpenScience/osf.io/blob/develop/api/base/settings/defaults.py ；https://github.com/CenterForOpenScience/osf.io/blob/develop/api/base/throttling.py | 2026-09-26 |
| 20 | `api.osf.io`、`api.elifesciences.org`、`eutils` 的 robots 为 `Disallow: /`；osf.io 为 crawl-delay 10 并禁 `/api/*` | 确认 | https://api.osf.io/robots.txt ；https://api.elifesciences.org/robots.txt ；https://eutils.ncbi.nlm.nih.gov/robots.txt ；https://osf.io/robots.txt | 2026-09-26 |
| 21 | PMC 只允许 Cloud、OAI-PMH、E-utilities、BioC 四个通道自动化获取；"Systematic retrieval … through any other automated process is prohibited" | 确认 | https://pmc.ncbi.nlm.nih.gov/tools/developers/ | 2026-09-26 |
| 22 | 2026-02-12 宣布数据集变更；2026-08-24 那一周删除全部旧数据集文件；OA Web Service 已不可用（公告日 2026-08-25，页面修改日 08-19）；FTP 只留 `PMC-ids.csv.gz` | 确认 | https://pmc.ncbi.nlm.nih.gov/tools/ftp/ ；https://pmc.ncbi.nlm.nih.gov/tools/oa-service/ | 2026-09-26 |
| 23 | PMC S3 约 800 万个文章版本；JSON 含 `license_code`（CC 或 `TDM`）、`is_manuscript`、`is_retracted` 等；README 规定只再分发许可允许再分发的数据；inventory 每日生成；没有 baseline 与增量包；删除不通知 | 确认。补充：FAQ 称已分发的作者手稿"available for commercial reuse regardless of license"，已写入 §2.3.2 与 Q11 | https://pmc-oa-opendata.s3.amazonaws.com/README.txt ；https://pmc.ncbi.nlm.nih.gov/tools/pmcaws/ | 2026-09-26 |
| 24 | PMC OAI：3 rps；超过 100 次请求须在美东非高峰时段；禁并发；须设 gzip；ListIdentifiers 每页 50、ListRecords 每页 10；`set=pmc-open` | 确认 | https://pmc.ncbi.nlm.nih.gov/tools/oai/ | 2026-09-26 |
| 25 | E-utilities 无 key 3 rps（响应头 `x-ratelimit-limit: 3`），有 key 10 rps，提速写信 eutilities@ncbi.nlm.nih.gov；ESearch 单次上限 10,000 | 确认；10,000 上限原文见 PMC AWS FAQ | https://ncbiinsights.ncbi.nlm.nih.gov/2017/11/02/new-api-keys-for-the-e-utilities/ ；https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term=psychology%5Bmh%5D&retmode=json&retmax=0 ；https://pmc.ncbi.nlm.nih.gov/tools/pmcaws/ | 2026-09-26 |
| 26 | E-utilities 的"离峰、禁并发"要求（§2.3.1 以 PMC 文档为据） | 未核验（新标 ⚠）：原文出自 PMC OAI 页；E-utilities 总指南 NBK25497 返回 reCAPTCHA，无法确认是否同样适用 | https://www.ncbi.nlm.nih.gov/books/NBK25497/ | 2026-09-26 |
| 27 | PubMed README（2026-01-30）">40 million citations"；baseline 为 `pubmed26n0001`–`1334`；日更自 `1335` 起；最新为 `1638` | 确认；补充：同日 14:05（服务器时间）新增 1639、1640，每日约 2 个文件；einfo 计数 41,210,260 | https://ftp.ncbi.nlm.nih.gov/pubmed/README.txt ；https://ftp.ncbi.nlm.nih.gov/pubmed/updatefiles/ | 2026-09-26 |
| 28 | NIH 2024 Public Access Policy 生效日提前至 2025-07-01（原定 2025-12-31），适用于该日及以后接收的 AAM | 确认 | https://grants.nih.gov/grants/guide/notice-files/NOT-OD-25-101.html ；https://grants.nih.gov/grants/guide/notice-files/NOT-OD-25-047.html | 2026-09-26 |
| 29 | 2025 年 PubMed 心理学覆盖：JPSP 165、Psych Sci 66、JML 8（印本、电子 ISSN 与 `[ta]` 三种口径均为 8）、AMPPS 0、Collabra 4、CogSci 0 | 确认 | https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term=0749-596X%5Bis%5D+AND+2025%5Bdp%5D&retmode=json | 2026-09-26 |
| 30 | PubMed/PMC 2025 抽查：PNAS 4,466/4,374、Cell 550/215、JPSP PMC 11、Front Psychol 4,808/4,267、Science 1,924/222、J Neurosci 718/766 | 确认 | https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pmc&term=0027-8424%5Bissn%5D+AND+2025%5Bpdat%5D&retmode=json （其余同构） | 2026-09-26 |
| 31 | Europe PMC：`SRC:PPR` 1,247,001；`HAS_FT:Y` 76,185；`HAS_VERSION_EVALUATIONS:Y` 41,177；PsyArXiv 65,080；arXiv 7,866；ChemRxiv 8,952；9-14 至 16 的样本来自 17 个平台，`inEPMC=Y` 为 0/1,000；13,938（9-01 至 20 首发） | 确认（逐项数值一致） | https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=SRC:PPR&format=json&resultType=idlist&pageSize=1 | 2026-09-26 |
| 32 | Europe PMC `/fields` 约 130 个 | **修正**：143 个；文中列出的 32 个字段名全部存在 | https://www.ebi.ac.uk/europepmc/webservices/rest/fields?format=json | 2026-09-26 |
| 33 | `FIRST_IDATE:[2026-09-24 TO 2026-09-25]` 为 3,295 条（写在预印本规模下） | **修正**：3,295 是全库条数，预印本（`SRC:PPR`）为 1,179 | https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=SRC:PPR%20AND%20FIRST_IDATE:%5B2026-09-24%20TO%202026-09-25%5D&format=json&resultType=idlist | 2026-09-26 |
| 34 | EPMC 的 SSRN 预印本停在 2023-10-28；EMBL-EBI ToU"… will result in the user being blocked" | 确认；补充：其后只有 1 条 2024-08-06 补录（2022 年旧稿 PPR602478） | https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=SRC:PPR%20AND%20PUBLISHER:%22SSRN%22&sort=FIRST_PDATE_D%20desc&format=json&resultType=lite ；https://www.ebi.ac.uk/about/terms-of-use/ | 2026-09-26 |
| 35 | Springer Nature TDM：直接下载 ≤1 req/s；API 150 req/min；"secure internal server without access for third parties"；非商业；Meta API 无 key 返回 401 | 确认；补充原文"only for the duration of the TDM project"（§0 第 7 条、§2.4.2） | https://www.springernature.com/gp/researchers/text-and-data-mining ；https://api.springernature.com/meta/v2/json?q=journal:Nature | 2026-09-26 |
| 36 | Elsevier Article Retrieval：每周 50,000 次、10 rps，TDM key 不限（原仅引 v1） | 确认（升级为官方来源 R77） | https://dev.elsevier.com/api_key_settings.html | 2026-09-26 |
| 37 | BMC 各域名、BMC 旧 RSS、EMBO Press 均 301 到 `link.springer.com`（`/journal/13059`、`/journal/12915/articles`、`/brands/bmc`、`/partners/embo-press`、`/journal/44318`） | 确认 | https://genomebiology.biomedcentral.com/ ；https://www.embopress.org/journal/14602075 | 2026-09-26 |
| 38 | robots 与 AI 条款：link.springer.com 为 `Disallow: /` 加允许清单，`search.rss` 不在清单内；nature.com、link.springer、cell.com、Research Square、psycnet 点名禁 ClaudeBot 与 anthropic-ai；science.org 禁 anthropic-ai；PNAS 与 T&F 只点名 GPTBot；psycnet `*` 为 `Disallow: /` | 确认 | https://link.springer.com/robots.txt ；https://www.nature.com/robots.txt ；https://www.cell.com/robots.txt ；https://www.science.org/robots.txt ；https://psycnet.apa.org/robots.txt ；https://www.researchsquare.com/robots.txt | 2026-09-26 |
| 39 | ScienceDirect robots：`*` 为 `Disallow: /`；"Claude-SearchBot、Claude-User 部分允许" | **修正**：两者都是显式 `Allow: /`；ClaudeBot、anthropic-ai、Claude-Web、claude-code 全禁 | https://www.sciencedirect.com/robots.txt | 2026-09-26 |
| 40 | WAF 与站点状态：europepmc.org、cambridge.org、jneurosci.org、escholarship.org、preprints.org、mdpi.com 的 robots.txt 返回 403；journals.sagepub.com TLS 失败；api.biorxiv.org 与 api.plos.org 无 robots（404）；各 eTOC feed 可用性（Cell、Nature、PNAS、Science、Wiley、T&F、OUP、Frontiers、eLife 为 200；CSHL 302 到 SAMS Sigma；PeerJ 403） | 确认（逐项复现） | https://europepmc.org/robots.txt ；https://www.cell.com/cell/current.rss ；https://genome.cshlp.org/rss/current.xml ；https://peerj.com/articles/index.rss | 2026-09-26 |
| 41 | Crossref `abstracts-current`：Cell、JPSP、Psych Bull、Cognition、Cognition & Emotion 均为 0；Nature 约 12%；Genome Biol 56%；eLife 99%；IJMS 100%；Front Psychol 92%、Front Neurosci 90%；public 池响应头为 5 rps、并发 1 | 确认 | https://api.crossref.org/journals/0092-8674 ；https://api.crossref.org/journals/0022-3514 ；https://api.crossref.org/journals/0028-0836 | 2026-09-26 |
| 42 | *Cell* 2026 年 463 条中无 CC 许可；Cell Press 刊标为"订阅" | **修正**：*Cell* 241/463 带即时 VOR CC 许可（BY 165、BY-NC-ND 47、BY-NC 29）；*Neuron* 130/366、*Mol Cell* 123/300、*Curr Biol* 266/722、*TICS* 62/174；*Cognition* 135/254、*JML* 25/52。§2.4.1、§2.7、§2.8 与 §3 第 15 条已改为"混合 OA" | https://api.crossref.org/works?filter=issn:0092-8674,from-pub-date:2026-01-01,until-pub-date:2026-09-26&rows=0&facet=license:* | 2026-09-26 |
| 43 | 2026 年许可 facet：PNAS 3,649/3,688 带 CC；Nature 656/3,312；Science 101/1,563 带 reuse 许可；J Neurosci 439/523 为 BY-NC-SA；EMBO J 244/247 为 BY；Psych Sci 28/46；Annu Rev Psychol 25/34；JPSP 22 条 CC | 确认（JPSP 分母 184 未加 `until-pub-date`，加上后为 174） | https://api.crossref.org/works?filter=issn:0027-8424,from-pub-date:2026-01-01,until-pub-date:2026-09-26&rows=0&facet=license:* | 2026-09-26 |
| 44 | Crossref `/journals/1548-7091` 返回 Nature Chemical Biology 的记录；按印本 ISSN 查 2026 年为 0（PLOS Biol 0/413、PLOS CB 0/737、EMBO J 0/247、BRM 0/275、Child Dev 0/231），*Bioinformatics* 640/705；Child Dev 的 `10.1111/cdev.14179` 归 OUP（member 286） | 确认 | https://api.crossref.org/journals/1548-7091 ；https://api.crossref.org/journals/1545-7885/works?filter=from-pub-date:2026-01-01,until-pub-date:2026-09-26&rows=0 ；https://api.crossref.org/works/10.1111/cdev.14179 | 2026-09-26 |
| 45 | DOAJ：*Bioinformatics* 不在 DOAJ；IJMS 按 ISSN 查无结果 | **修正**：*Bioinformatics* 已按 eISSN 1367-4811 收录（2023-07-11，CC BY），原结论源于用印本号查询；IJMS 按 ISSN 与刊名均查无结果（补充），原因仍 ⚠ | https://doaj.org/api/search/journals/issn%3A1367-4811 ；https://doaj.org/api/search/journals/issn%3A1422-0067 | 2026-09-26 |
| 46 | PLOS Search API 限速（7,200/天、300/时、10/分，5 并发，≤100 行）；2026-09-01 至 25 共 1,711 篇、15 个刊、facet 17 个值 | 限速确认；刊数**修正**为 16 个刊、facet 18 个值（新增 PLOS Aging and Health 9 篇） | https://api.plos.org/solr/faq/ ；https://api.plos.org/search?q=publication_date:%5B2026-09-01T00:00:00Z%20TO%202026-09-25T23:59:59Z%5D%20AND%20doc_type:full&rows=0&facet=true&facet.field=journal | 2026-09-26 |
| 47 | eLife：评估词表 significance 5 级、strength 6 级；API `/articles` 19,543、`/reviewed-preprints` 4,806（样例 DOI 为 10.64898 预印本）、`/subjects` 19；厂商媒体类型，`max-age=300` | 确认 | https://elifesciences.org/about/elife-assessments ；https://api.elifesciences.org/articles?per-page=1&order=desc | 2026-09-26 |
| 48 | MDPI OAI 可用，有 67 个按文章类型的 set，无按刊 set | **修正/补充**：调研员 15:20 UTC 的存档确有 67 个 set。19:30–19:38 UTC 的 4 次请求中 3 次返回 nginx 504、1 次无有效响应，已改为"可用但不稳定" | https://oai.mdpi.com/oai/oai2.php?verb=Identify ；https://oai.mdpi.com/oai/oai2.php?verb=ListSets | 2026-09-26 |
| 49 | CogSci 论文集只在 eScholarship OAI：`set=cognitivesciencesociety` 的 `completeListSize` 为 21,720，每页 500，resumptionToken 24 小时过期，`dc:source` 带卷号，许可为 CC-BY（样本中另有 5 条 "public"）；Crossref ISSN 1069-7977 返回 404；PubMed 为 0 | 确认 | https://escholarship.org/oai?verb=ListRecords&metadataPrefix=oai_dc&set=cognitivesciencesociety ；https://api.crossref.org/journals/1069-7977 | 2026-09-26 |
| 50 | MeSH 2026 的 desc/qual/supp/pa 文件齐全；Psychology 为 D011584，树号 F04.096.628，上位为 D001525；条款要求致谢 NLM、保持最新或标明版本，MTMS 另有条款 | 确认 | https://nlmpubs.nlm.nih.gov/projects/mesh/MESH_FILES/xmlmesh/ ；https://id.nlm.nih.gov/mesh/D011584.json ；https://www.nlm.nih.gov/databases/download/terms_and_conditions_mesh.html | 2026-09-26 |
| 51 | arXiv q-bio 共 10 类；PsycInfo 分类为 22 大类、135 子类，Thesaurus 第 11 版（2007）有 8,400 条以上 | 确认。PsycInfo 只有维基这一第三方来源，APA 官方页被 Imperva 挡住读不到，维持 ⚠ | https://arxiv.org/category_taxonomy ；https://en.wikipedia.org/wiki/PsycINFO | 2026-09-26 |
| 52 | Cognitive Atlas API 返回 200；许可 ⚠ 未核验 | **修正**（⚠ 已解除）：站点页脚标注 CC BY-SA 3.0 US | https://www.cognitiveatlas.org/api/v-alpha/concept?id=trm_4a3fd79d096be ；https://www.cognitiveatlas.org/ | 2026-09-26 |
| 53 | §2.10 的 16 个 GitHub 仓库：star、许可、最近推送时间、是否归档 | 确认（16/16 与 `gh api` 结果逐项一致，含 pymed、elsapy 已归档） | https://github.com/biopython/biopython 等（`gh api repos/{owner}/{repo}`） | 2026-09-26 |
| 54 | paperscraper 的 bioRxiv 路径是否依赖 `/details`（原标 ⚠） | **修正**（⚠ 已解除）：`xrxiv_api.py` 拼接 `{api_base_url}/details/{server}`，确认依赖 | https://github.com/jannisborn/paperscraper/blob/main/paperscraper/xrxiv/xrxiv_api.py | 2026-09-26 |
| 补1 | 覆盖缺口：Royal Society Publishing（*Proc B*、*Biol Lett*、*RSOS*）——元数据、OA、PMC 覆盖与 robots（§2.4.18、§2.7） | 补充（附 *Proc B* 在 Crossref 被拆成印本、电子两条期刊记录的数据陷阱） | https://api.crossref.org/journals/1471-2954 ；https://api.crossref.org/journals/0962-8452 ；https://royalsocietypublishing.org/robots.txt | 2026-09-26 |
| 补2 | 覆盖缺口：Hogrefe（欧洲心理学出版商，Atypon）——元数据、混合 OA、PubMed 缺口与 robots（§2.4.18、§2.7） | 补充 | https://api.crossref.org/prefixes/10.1027 ；https://api.crossref.org/journals/1016-9040 ；https://econtent.hogrefe.com/robots.txt | 2026-09-26 |
| 补3 | 覆盖缺口：NCBI PubTator3 实体标注与关系 API（§2.3.4、§2.7） | 补充（限速与许可 ⚠） | https://api.crossref.org/works/10.1093/nar/gkae235 ；https://www.ncbi.nlm.nih.gov/research/pubtator3-api/publications/export/biocjson?pmids=29355051 | 2026-09-26 |
| 补4 | 覆盖缺口：NIH iCite / Open Citation Collection（RCR 与引文 API，§2.3.4、§2.7） | 补充（限速与许可 ⚠） | https://api.crossref.org/works/10.1371/journal.pbio.3000385 ；https://icite.od.nih.gov/api/pubs?pmids=29355051 | 2026-09-26 |

**残余风险（供设计阶段引用时注意）**

1. 时效数字（OSF total、PubMed 更新文件号、EPMC 计数）会持续变化，引用时应标注"截至 2026-09-26"。
2. bioRxiv `/details`、`/funder` 与 MDPI OAI 的状态是当日快照，是否已恢复需上线前复测。
3. 仍为 ⚠ 的事实：CZI 资助金额、In Review 现状、E-utilities 离峰要求原文、Europe PMC 数值限速、APA 官方分类码与 Thesaurus、Research Square API 条款、SAGE/PNAS/AAAS/Annual Reviews 政策页、PubTator3 与 iCite 的限速和许可。
4. 部分 robots/WAF 判定受本机网络影响（SAGE、SSRN 的 TLS 中断），需要换网络复测。
