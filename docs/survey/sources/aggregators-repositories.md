---
title: 来源调研：二级来源——仓库与聚合平台
status: draft
owner: opus5.5-survey
updated: 2026-09-26
---

# 来源调研：二级来源——仓库与聚合平台

> 本文是 v2 重设计「调研阶段（Survey）」的来源主题之一，覆盖**跨出版商的二级来源（L2）**：元数据聚合器、开放仓储（repository）、引文/身份/机构注册表、学科聚合库、商业索引库与中文/区域平台。它是 v2「多来源查询 + 路由」的主干输入。
> 本文**以 v1 勘察为基线做增量更新**，不重复 v1 已有细节：v1 基线见 [metadata-apis.md](../../archive-v1.md#docs-research-site-survey-metadata-apis-md)（Crossref/OpenAlex/S2，2026-07-20/22）[S106]、[aggregators-unpaywall-dblp-core.md](../../archive-v1.md#docs-research-site-survey-aggregators-unpaywall-dblp-core-md)（Unpaywall/DBLP/CORE/Scholar）[S107]、[adapters/aggregators.md](../../archive-v1.md#docs-design-adapters-aggregators-md)（六源实现级详设）[S108]，以及 [decision-log](../../plan/decision-log.md) D-005/D-021/D-037 [S109]。凡与 v1 结论不一致处以 ⚡ 标注。
> 标记约定：**[LIVE]** = 2026-09-26 本次实测（HTTP 请求读响应头/计数/robots.txt）；**[DOCS]** = 2026-09-26 读取的官方文档/政策页；**[v1]** = 沿用 v1 勘察、本次未复核；**⚠ 未核验** = 无法在本次核实（原因随注）。所有 [S#] 编号见 §5 参考来源。

## 0. 结论速览

1. ⚡ **Crossref 已按请求类型分池限速，全局检索最慢**：2026-07-21 起单条类与列表/检索类请求分开限速，公告口径为 public 单条 5/s、列表 1/s，polite 单条 10/s、列表 3/s [S4]。[LIVE] 无 mailto 时的归类如下：
   - `/works?filter=…` 与 `/works?query.bibliographic=…` 归入 `public-array`，1/s，并发 1；
   - `/works/{doi}`、`/journals/{issn}`、`/journals/{issn}/works`（含 `cursor` 深翻）、`/members/{id}/works` 归入 `public-single`，5/s，并发 1 [S5]。

   因此 v2 做 venue 枚举和增量时，应走 `/journals/{issn}/works`，不要用全局 `/works?filter=issn:`（同样的查询慢 5 倍）；关键词检索类请求不应打到 Crossref。v1 adapter 恰好使用 `/journals/{issn}/works` + 静态 5 req/s，目前在 public 池内不超限；但这一归类属于实测行为，官方未承诺，路由器必须读 `x-api-pool`/`x-rate-limit-*` 头动态调整。
2. ⚡ **DBLP 全站 robots.txt 已改为全面禁止**：[LIVE] `dblp.org`、`dblp.uni-trier.de`、`dblp.dagstuhl.de` 三个主机的 robots 完全相同：163 个具名 AI/agent UA 共用一组 `Disallow: /`，外加 `User-agent: * / Disallow: /`，无 `Crawl-delay`、无 `Allow` [S51]（核验 2026-09-26 复测一致）。v1（2026-07-22）记录的是 `Crawl-delay: 4`、允许 `/db`、`/xml`，因此 v1 的 `/db/conf/**.xml` 通道已不合规（D-037 已把 dblp 移出生产链，影响限于代码存量）。合规替代：`sparql.dblp.org`（robots 显式 `Allow: /sparql`、`/download`，`Crawl-delay: 10`；另提供 6.1 GB 知识图谱包）[S52]，以及 Dagstuhl DROPS 月度 XML 快照（CC0，2026-09 版 1.02 GB）[S53]。
3. **OpenAlex 适合做 v2 的覆盖面主干，但要按预算使用**：[LIVE] core 语料 327,236,598 works，`corpus=all`（含 XPAC 扩展包）474,545,499 [S25]；CC0 [S19]；Topics 四级为 4 domains / 26 fields / 252 subfields / 4,516 topics [LIVE]。计费：单实体免费、列表 $0.0001、搜索与语义搜索 $0.001、PDF $0.01，免费 key $1/天，无 key $0.10/天（[LIVE] 响应头 `x-ratelimit-limit-usd: 0.1`）[S13][S25]。`from_created_date` 与 `from_updated_date` 过滤需要付费计划（[LIVE] 返回 "Plan upgrade required … requires a Premium, Institutional, or Partner plan"；定价页写明 Member+ 起含 `from_updated_date` 日同步）；公共快照改为**季度**更新（每年 1/4/7/10 月第二个周三），日更快照仅对付费用户开放 [S16][S18]。
4. **Semantic Scholar 的价值在嵌入和推荐，不在元数据**：SPECTER2 可在 API 中通过 `fields=embedding.specter_v2` 取得，也可下载 1.2 亿条嵌入数据集（Apache-2.0）[S29][S31]；Recommendations API 接受正例和负例论文 ID，单次最多返回 500 条，候选池为 `recent` 或 `all-cs` [S30]；Datasets 每周发布一次（最新为 2026-09-22），可用 diffs 端点做增量 [S29][S32]。[LIVE] 不带 key 时 DOI 查询返回 404，搜索返回 429；带 key 的默认限速是 1 RPS [S27]。
5. ⚡ **Unpaywall 已在 2025 年末迁到 OpenAlex 数据库**：官方说明只保留「DOI 输入、OA 答案输出」的 API、浏览器扩展和 Data Feed，其他用途改用 OpenAlex；数据只覆盖 Crossref DOI，不含 DataCite [S24]。
6. **许可分三档，摘要处在灰区**：①可以放心缓存和展示的 CC0 数据：Crossref 的书目事实、OpenAlex、DOAJ、DataCite、ROR、OpenCitations、Wikidata、DBLP 快照 [S8][S19][S42][S62][S67][S79][S83][S53]；②需要署名的：OpenAIRE（CC-BY）、S2 数据集（ODC-BY）、CORE 旧版 dump（ODC-By）[S74][S29][S35]；③有限制的：ORCID Public API 仅限非商业用途、Lens 仅限机构订阅、Dimensions 只对非商业科学计量研究免费、Scopus 和 WoS 的使用受订阅及展示条款约束 [S56][S85][S86][S88][S89]。核验补充：HAL 元数据为 CC0（归入①）[S115]；zbMATH Open 为 CC BY-SA（署名且相同方式共享，归入②并需评估 ShareAlike）[S114]；S2 API 条款未明文允许商用 [S28]。**摘要**方面，Crossref 明确说明摘要仍归出版方或作者所有 [S8]，OpenAlex「因法律原因」不直接提供明文摘要，只给倒排索引 [S23]。卡片是否展示摘要全文需要单独决策（见 §4）。
7. **很多 API 主机的 robots.txt 与官方 API 文档互相矛盾，v2 需要一条统一的解释规则**：[LIVE] `eutils.ncbi.nlm.nih.gov`、`pub.orcid.org`、`api.osf.io`、`api.base-search.net` 都是 `Disallow: /`；HAL API 主机禁止 `/search/` 和 `/oai/`，但 `hal.science` 的 robots 注释大意是"要下载大量元数据请使用 API"；Zenodo 禁止 `/api`，官方文档推荐走 OAI-PMH 或数据 dump [S47][S57][S70][S38][S72][S69]。核验补充：PubMed/PMC 的 bulk 主机 `ftp.ncbi.nlm.nih.gov` 与 Europe PMC 的 bulk 主机 `ftp.ebi.ac.uk` 同样 `Disallow: /`，所以"走 bulk"本身也要经 ADR 裁定 [S113][S123]；CiNii Research 的 robots 禁 `/opensearch` [S119]。这需要一条 ADR 来裁定（见 §4 Q1）。
8. **越来越多的站点在前面加了挑战门**：[LIVE] BASE 网站用了 Anubis 工作量证明，robots 附法律声明禁止未经授权的自动获取，API 按 IP 白名单拒绝访问 [S38]；IA Scholar 检索会跳转到 ALTCHA 验证；Europe PMC 网站、zbMATH 网站、NCBI 文档页分别有 Cloudflare 或 reCAPTCHA；SciELO 检索用 Bunny Shield。v2 对这些站点只走官方 API 或批量通道，不去解挑战。
9. **哪些 OA 全文可以在用户之间共享，取决于每一篇的许可证**：OpenAlex content（5,000 万以上 PDF、约 4,300 万 TEI，保留原版权，不授予额外权利）[S17]、CORE（4 亿以上记录、4,000 万以上全文，未认证用户拿不到全文）[S33][S36]、Europe PMC OA 子集 8,273,746 篇 [LIVE]、PMC Cloud（NLM 条款要求只再分发许可允许再分发的内容）[S49]。v2 只能缓存并共享许可证明确允许再分发的全文（如 CC-BY）；其余只存链接，由每个用户各自取回并私有存放。
10. **学科专用聚合源补齐 OpenAlex 的短板**：INSPIRE（高能物理，大部分元数据 CC0，15 次请求/5 秒）[S92]、NASA ADS（天文，需 token，示例配额 5,000 次/天）[S93]、zbMATH Open（数学 MSC 分类，[LIVE] API 可用）[S94]、Europe PMC/PubMed（生物医学 MeSH）[S44][S47]、EconBiz 与 RePEc（经济学）[S96]。[LIVE] OpenAlex 对机器学习顶会的 source 归一化较差：NeurIPS 会议实体只有 4,177 条 works，ICLR 只有 757 条。**会议论文仍然要靠 L1 平台适配器**。
11. **中文与区域平台基本没有合规的自动化通道**：[LIVE] `kns.cnki.net` 的 robots 为 `Disallow: /`；万方检索前有 WAF；中国科技论文在线在 2026-09-26 显示「网站维护升级、暂停所有线上服务」；ChinaXiv 首页可访问，但 robots.txt 返回 403 维护页 [S97]–[S101]。可对接的是 J-STAGE WebAPI（商业用途须申请，浏览政策不允许大批量下载）[S102] 和 SciELO ArticleMeta API（[LIVE] 巴西合集 564,934 篇）[S104]。
12. **社交、事件类信号源在收缩**：Crossref Event Data API 已于 2026-04-23 停用，改为提供数据引用端点 [S7]；DataCite Event Data 在 2026 年第三、四季度收缩范围 [S63]。v2 的热度和社交信号只能来自平台内交互，以及 OpenAlex、OpenCitations 的引用增量。

## 1. 调研范围与方法

### 1.1 范围界定

| 类别 | 定义 | 本文覆盖 |
|---|---|---|
| **L2-aggregator** | 汇聚多出版方/多仓储元数据的索引服务，本身通常不是首发地 | Crossref、OpenAlex、Semantic Scholar、OpenAIRE Graph、OpenCitations、Lens、Dimensions、Scopus、Web of Science、BASE、DOAJ、Unpaywall、Wikidata/WikiCite、Fatcat/IA Scholar、学科库（PubMed、Europe PMC、INSPIRE、ADS、zbMATH Open、MathSciNet、EconBiz、RePEc）、区域库（CNKI、万方、维普、SciELO、Redalyc） |
| **L2-repository** | 存放作者自存档、数据、预印本或 OA 全文的仓储或仓储网络 | CORE（仓储聚合）、Zenodo、OSF（含 PsyArXiv/SocArXiv 等 32 个社区）、HAL、PMC/Europe PMC OA 子集、中国科技论文在线、EconStor |
| **注册表（identity/registry）** | 为作者、机构、DOI 提供权威标识，是去重和消歧的底座 | ORCID、ROR、DataCite（DOI 注册机构，兼作数据/软件元数据源） |
| **历史/排除** | 已关停，或按合规红线排除 | Microsoft Academic（已关停）、Google Scholar（排除自动化） |

不在本文范围：L1 出版商、预印本、期刊平台、会议平台（由其他调研主题覆盖；arXiv、SSRN 等只在路由矩阵中被引用）；J-STAGE 与 ChinaXiv 本质上属于 L1（期刊平台/预印本），因任务要求在此一并评估可对接性。

### 1.2 方法

1. **官方文档与政策复核**：限速、配额、许可、快照、弃用计划等，一律以官方文档页或官方博客为准，并记录读取日期；页面被挑战门拦截的，标注 ⚠ 并写明原因。
2. **LIVE 探针**：对每个源发送最少量的只读请求，读取响应头（`x-rate-limit-*`、`x-ratelimit-*`、`x-api-pool`）、总量计数与 `robots.txt`；**不登录、不使用任何 API key、不携带用户邮箱**（刻意不走 Crossref polite pool，因此 polite 池数值只来自文档和公告）。
3. **与 v1 对比漂移**：逐项对照 v1 勘察（2026-07-20/22），变化处标 ⚡。
4. **代表性 venue 实证**：对 §2.6 中 204 本期刊，逐一调用 Crossref `/journals/{issn}`（取出版方、DOI 总量、摘要/参考文献/ORCID/ROR 覆盖率）和 OpenAlex `/sources/issn:{issn}`（取宿主机构、是否全 OA、是否在 DOAJ、OA 作品占比），ISSN 以响应为准，不采用凭记忆填写的数值；会议另做核验。

### 1.3 过程记录（可复现）

#### 1.3.1 环境与身份

- 时间窗：2026-09-26，约 14:45–16:00 UTC（北京时间 22:45–24:00）。
- 客户端：`curl` 与 Python `urllib`；统一 UA `PaperCrawler-survey/0.1 (docs research; low-volume)`（诚实标识，未冒充浏览器）；少量页面由 WebFetch 工具代取（其 UA 不受本调研控制，已在 [S85] 等处注明）。
- 凭证：**无登录、无 API key、无 cookie，不携带用户邮箱**，所以 Crossref 只走 public 池，OpenAlex 只用匿名 $0.10/天额度。
- 节流：同一主机串行，间隔 ≥0.6 s；Crossref 列表类间隔 ≥1.6 s；遇 429 线性退避（5–24 s）。本机出口 IP 上还有其他并行调研任务，Crossref public 池并发上限为 1，导致 venue 核验中 19 次 429，均已退避重试补齐，仅 TMLR 最终为 404（该刊不在 Crossref）。

#### 1.3.2 检索式（WebSearch）

会话级检索配额在第 12 次时耗尽（配额由同会话的其他调研任务共享），此后改为直接访问官方文档 URL 与 API：

| # | 检索式 | 用途 |
|---|---|---|
| 1 | `Crossref REST API rate limits public pool polite pool change 2025` | 定位 2025–2026 限速公告 |
| 2 | `Crossref "polite-array" OR "public-array" x-api-pool rate limit` | 池命名与第三方观测 |
| 3 | `Crossref blog 2026 REST API announcement` | 定位 2026-07-21 限速细化帖、Event Data 停用、2026 公共数据文件 |
| 4 | `Crossref metadata license "abstracts" copyright REST API reuse "not subject to copyright" documentation` | 许可口径 |
| 5 | `OpenAlex API key pricing credits per day 2026 documentation rate limits` | 计费规则 |
| 6 | `help.openalex.org snapshot download S3 openalex bucket 2026` | 快照 |
| 7 | `OpenAlex Walden rewrite launch 2025 new works xpac changes` | Walden 与 XPAC |
| 8 | `OpenAlex "include_xpac" parameter works` | `corpus=` 参数 |
| 9 | `OpenAlex pricing plans Member "Member+" Supporter annual price premium API 2026` | 付费档 |
| 10 | `Semantic Scholar API key application 2026 approval paused rate limit 1 RPS introductory` | S2 key 现状 |
| 11 | `Crossref "saying goodbye to Event Data" data citations API 2026` | Event Data 停用 |
| 12 | `BASE Bielefeld Academic Search Engine HTTP API access registration …` | **配额耗尽，未执行** |

检索结果只用于定位官方页面，所有事实都回到官方页面或 LIVE 响应核实（检索摘要与官方页面冲突时以官方页面为准，例如 OpenAlex 无 key 额度：检索摘要写 $0.01/天，官方页与 LIVE 响应头均为 $0.10/天）。

#### 1.3.3 执行步骤

> 访问过的站点与端点全集见 §5：每条都注明访问日期，以及属于 [DOCS]（官方文档）还是 [LIVE]（实测）。

| 步骤 | 动作 | 产出 |
|---|---|---|
| 1 | 读 v1 基线：README、INDEX、metadata-apis.md、aggregators-unpaywall-dblp-core.md、adapters/aggregators.md、publishers-platforms.md、preprint-platforms.md、decision-log、catalog/*-journals.md、github-similar-projects.md | 确定增量调研边界与 v1 口径 |
| 2 | 逐源读官方文档/政策页（§5 [DOCS] 各条） | 限速、许可、快照、弃用计划 |
| 3 | 逐源 LIVE 探针：响应头、计数、`robots.txt`（§5 [LIVE] 各条） | ⚡ 漂移项、robots 与 API 冲突清单 |
| 4 | 204 本期刊 Crossref + OpenAlex 双源核验（脚本 `verify.py`/`retry.py`，结果见附件 JSONL） | §2.6 表 |
| 5 | Crossref 全局覆盖统计 14 次（`has-abstract`/`has-references`/`has-orcid`/`update-type`/`posted-content`/Elsevier 成员）与池归类对照 4 次 | §2.2.1 实测覆盖、§0-1 分池结论 |
| 6 | 会议 Crossref 分面核验 12 次 | §2.6.11 |
| 7 | OpenAlex 2025 年按 field 的 `group_by` 5 次 + 主题层级计数 5 次 | §2.4.1 画像、Topics 规模 |
| 8 | API 主机 robots 横扫（15 个主机，另有各源单独检查） | §3 第 14 条、Q1 |
| 9 | GitHub 客户端库元数据（`gh api repos/…`） | §2.7 |

#### 1.3.4 请求台账与合规自检

- 请求量（约数，全部为只读 GET）：Crossref API 约 300 次（含 204 次刊级核验与重试）、OpenAlex API 约 230 次（其中 204 次单实体查询为 0 成本；列表/分组约 25 次、名称检索 3 次，匿名额度消耗约 60 积分 ≈ $0.006）、其余各源 1–15 次不等；全部文档页合计约 90 次。无任何全文 PDF 下载。
- 挑战门与拦截：遇到 Anubis（BASE）、ALTCHA（IA Scholar）、Cloudflare（Europe PMC 官网、zbMATH 主站）、reCAPTCHA（NCBI 文档）、Bunny Shield（SciELO 检索），以及原因不明的 HTTP 403（Lens 条款页 curl、`openalex.org/pricing` WebFetch、zbMATH 条款页、Redalyc robots）。**全部立即停止，未尝试求解或绕过**，相关事实改用其他官方页面核实，或标注 ⚠。
- ⚠ **自检发现 9 次"先请求、后读 robots"**。这些请求发生在读取对应 robots.txt 之前，读取后均未再访问相关路径：
  - `zenodo.org/api/records`：1 次（robots 禁 `/api`）；
  - `api.osf.io/v2/…`：2 次（robots 全禁）；
  - `api.archives-ouvertes.fr/search/`：2 次（robots 禁 `/search/`）；
  - `scholar.archive.org/search`：1 次（robots 禁 `/search`，已被重定向到验证页）；
  - `eutils.ncbi.nlm.nih.gov` esearch/einfo：2 次（robots 全禁）；
  - `api.base-search.net`：1 次（robots 全禁，已被拒绝访问）。

  这 9 次请求量极低、未造成负载，但说明调研流程同样需要 robots-first 闸门（§3 第 15 条、Q15）。
- 未访问 `dblp.org` 除 `robots.txt` 以外的任何路径。
- ⚠ 核验补充（2026-09-26）：[S48][S49] 所读的 `ftp.ncbi.nlm.nih.gov/pubmed/README.txt`、`/pub/pmc/readme.txt`，以及 [S46] 所列的 `ftp.ebi.ac.uk/pub/databases/pmc/`，所在主机的 `robots.txt` 都是 `User-agent: * / Disallow: /`；原稿没有读取这两个主机的 robots，它们也不在上面 9 次之列。这说明台账需要按主机做 robots 自检，而不是只查"API 主机"。

#### 1.3.5 附件（同名子目录）

| 文件 | 内容 |
|---|---|
| [venue-verification-2026-09-26.jsonl](aggregators-repositories/venue-verification-2026-09-26.jsonl) | 204 本期刊的 Crossref `/journals/{issn}` + OpenAlex `/sources/issn:` 原始摘录（每行一刊） |
| [crossref-stats-2026-09-26.json](aggregators-repositories/crossref-stats-2026-09-26.json) | Crossref 全局覆盖统计与池归类（§2.2.1） |
| [conference-crossref-check-2026-09-26.json](aggregators-repositories/conference-crossref-check-2026-09-26.json) | 会议 Crossref 分面核验（§2.6.11） |
| [openalex-field-stats-2025.json](aggregators-repositories/openalex-field-stats-2025.json) | OpenAlex 2025 年按 field 的覆盖画像（§2.4.1） |


## 2. 主体内容

### 2.1 L2 来源全景：按"在 v2 中承担的职能"分层

| 职能层 | 主力源（建议） | 补充/学科源 | 仅元数据/观察 | 排除 |
|---|---|---|---|---|
| **A. DOI 注册与书目事实（权威层）** | Crossref（期刊/书/会议 DOI）、DataCite（数据/软件/部分预印本 DOI） | — | — | — |
| **B. 覆盖面主干与主题图谱** | OpenAlex（CC0，Topics 四级） | OpenAIRE Graph（欧洲资助/仓储）、Wikidata（跨库 ID） | Lens（机构订阅） | Dimensions/Scopus/WoS（平台层）、MAG（已停） |
| **C. 语义与推荐信号** | Semantic Scholar（SPECTER2、Recommendations、TLDR） | OpenAlex 语义搜索（beta） | — | Google Scholar |
| **D. 引文图** | OpenCitations（CC0）、OpenAlex `referenced_works` | S2 citations（带 intent/context，需 key） | Crossref `reference`（按存缴） | — |
| **E. OA 定位与全文** | OpenAlex `best_oa_location`/content、Unpaywall（DOI→OA，兼容层） | CORE、Europe PMC OA、PMC Cloud、HAL、Zenodo | Fatcat/IA Scholar | BASE（未授权）、任何盗版源 |
| **F. 身份与机构** | ORCID（用户 OAuth 自授权）、ROR（dump） | OpenAlex authors/institutions、DBLP PID（快照） | — | — |
| **G. 学科聚合** | Europe PMC、PubMed（生物医学/心理）；INSPIRE（HEP）；zbMATH Open（数学） | ADS（天文，token）、EconBiz、RePEc（经济） | MathSciNet（订阅） | — |
| **H. 区域** | — | J-STAGE WebAPI、SciELO ArticleMeta | ChinaXiv（待其恢复 robots）、Redalyc | CNKI/万方/维普自动化（仅用户手动导入） |

### 2.2 逐源档案

> 每源一张"维度—事实"表；限速/许可类事实均带 [S#] 与核验标记。"v2 结论"中的 P0/P1/P2 与 §2.5 名录一致。

#### 2.2.1 Crossref（`crossref`，v1 已实现）

| 维度 | 事实 |
|---|---|
| 覆盖/规模 | [LIVE] `/works?rows=0` total-results = 186,986,937（约 40 分钟后复测为 186,987,698）[S5]；2026 年度公共数据文件：约 1.8 亿条、压缩 208 GB JSON-lines，2026-03-17 发布 [S6] |
| 字段 | 书目事实；参考文献（按出版方存缴）；摘要（按存缴，JATS）；ORCID、机构/ROR；资助（funder/award）；许可 `license`；TDM `link`；更新/撤稿 `update-to`（含 Retraction Watch 数据，2025-01-29 起）；被引只有计数 `is-referenced-by-count`（无引用列表）[S9][S10]。各刊摘要/参考文献/ORCID/ROR 覆盖率差异很大，见 §2.6 实测列 |
| 查询 | `/works`、`/journals/{issn}/works`、`/members/{id}/works`、`/prefixes/{p}/works`；`filter`（`from/until-{pub,online-pub,created,update,index}-date`、`type`、`has-abstract`、`has-references`、`update-type:retraction` 等）；`query.*` 字段检索；`sort`；`rows≤1000`；深翻 `cursor=*` [v1][S10] |
| 增量 | `from-index-date`（v1 已用作 watch 游标）；`from-update-date` 补抓更正 [v1]。核验补充 [LIVE 2026-09-26]：Nature Methods（`/journals/1548-7091/works`）自 2026-09-01 起 `from-index-date` 命中 3,223 条（该刊共 8,419 条），`from-update-date` 63 条，`from-created-date` 仅 32 条。重建索引会让大量旧记录重新落入 index-date 窗口，所以"最新论文"增量要么叠加 `from-created-date`/`from-pub-date`，要么依赖本地 DOI 去重，并按约百倍的放大量估算配额 [S5] |
| 限速 | ⚡ 按池 × 请求类：公告为 public 单条 5/s、列表 1/s，polite（`mailto`）单条 10/s、列表 3/s，并称新增 `x-rate-limit-type` 头；Plus 150/s、无并发上限（付费）[S1][S4]。⚠ 核验（2026-09-26）：public 池响应中**未见** `x-rate-limit-type` 头，请求类目前只编码在 `x-api-pool` 的后缀里（`-single`/`-array`），限速器不能依赖前者。[LIVE] 归类（public，并发 1）：`/works?filter=`、`/works?query.*` 属于 `public-array`，1/s；`/works/{doi}`、`/journals/{issn}`、**`/journals/{issn}/works`（含 cursor）**、`/members/{id}/works`、`/prefixes/{p}/works`（核验补测）属于 `public-single`，5/s [S5]。第三方 2026-09-18 观测：polite 单条池响应头为 `x-api-pool: polite-single`、`10/1s`、并发 3 [S12]；该 PR 的 `polite-multi` 只是测试参数，并非实测，polite 列表池的真实名称 ⚠ 未核验（按 public 侧命名推测为 `polite-array`） |
| 许可 | 书目元数据（含参考文献）视为事实、不受版权保护（CC0 口径）；**摘要保留出版方/作者版权**（Crossref 依会员协议可分发）；Crossref 自生数据 CC0；Open Funder Registry 与 Retraction Watch 数据均为 CC0 [S8] |
| bulk | 年度公共数据文件（Academic Torrents DOI 10.13003/nggf-vt1j，或 AWS 请求方付费）[S6]；Metadata Plus 快照（付费） |
| 2025–2026 变化 | ⚡ 2025-12-01 首次调限（公告 2025-11-05）[S2] → 2025-12-02 社区帖称"暂不能区分请求类型"[S3] → ⚡ 2026-07-21 正式按请求类型分池 [S4]；⚡ Event Data API 2026-04-23 停用，改提供数据引用端点 [S7] |
| 实测覆盖 | [LIVE] 全库 186,987,698 条，其中有摘要 45,187,859 条（24.2%）；期刊文章 124,068,499 条，有摘要 38,837,648 条（31.3%）；**2025 年期刊文章 6,635,682 条：有摘要 55.2%、有参考文献 57.3%、有 ORCID 41.3%**；撤稿通告（`update-type:retraction`）75,776 条；posted-content 4,086,004 条（2025 年 625,574 条）；**Elsevier（member 78）2025 年期刊文章 1,040,981 条，有摘要的仅 424 条** [S5]。作为对照，I4OA 在 2020-09 发起时，Crossref 全部作品的摘要覆盖为 6.6%、期刊文章为 8.3% [S11] |
| 数据质量 | [LIVE] `/journals/1548-7091`（Nature Methods 的 ISSN）返回的刊名是 "Nature Chemical Biology"，该记录同时挂着两刊的 ISSN（Nature Methods 两个 ISSN 的类型为 null）；但 `/journals/1548-7091/works` 的 container-title 分面是 Nature Methods 8,418 条（共 8,419）。也就是说**刊级元数据可能张冠李戴，按 ISSN 枚举的作品本身正确**，v2 必须用 OpenAlex source 与 container-title 做二次校验 [S5] |
| v2 结论 | **P0**：期刊 venue 枚举（走 `/journals/{issn}/works`，归 single 池）、期刊"最新论文"增量（`from-index-date`）、DOI 权威解析、撤稿/更正标记；须用 polite 池（平台运营者邮箱）并按 `x-api-pool` 分桶限速；关键词检索不走 Crossref（array 池 1–3/s）；摘要覆盖存在出版商级缺口（如 Elsevier），需 OpenAlex 与学科源补齐 |

#### 2.2.2 OpenAlex（`openalex`，v1 已实现为 enrich 通道）

| 维度 | 事实 |
|---|---|
| 覆盖/规模 | [LIVE] core 语料 327,236,598 works；`corpus=all` 474,545,499 [S25]；XPAC 扩展包（2025-11 随 Walden 加入 1.9 亿条，博客原文为来自 DataCite 与数千个仓储的数据集、软件等研究对象；当前官方页称其"主要是数据集与仓储记录"、需经 `corpus` 参数显式纳入，默认 `corpus=core` 不含；"平均质量较低""含全部 DataCite"两点只见于已 301 下线的旧文档页的检索摘要，⚠ 未能在现行官方页核到原文）[S20][S21]；快照 2026-09 版约 6.26 亿条记录（全实体）[S16] |
| 字段 | [LIVE] `abstract_inverted_index`（2022 年作品 >60% 有，2000 年前约 45%）、`authorships`（作者消歧 + 机构 ROR）、`referenced_works`/`related_works`、`cited_by_count`/`counts_by_year`/`fwci`/`citation_normalized_percentile`、`topics`/`primary_topic`（domain→field→subfield→topic）、`keywords`、`mesh`、`sustainable_development_goals`、`funders`/`awards`、`open_access`/`best_oa_location`/`locations`、`is_retracted`、`has_content`/`content_urls`、`language`、`is_xpac` [S23][S25] |
| 主题体系 | [LIVE] domains 4 / fields 26 / subfields 252 / topics 4,516；keywords 65,004 [S25] |
| 查询 | `filter`（AND/OR/NOT/比较，单 filter 最多 100 个 OR 值）、`search`（标题/摘要/全文）、语义搜索（beta）、`sort`、`group_by`、`sample`、`select`、`cursor`（基本分页上限 1 万条）、`corpus`（core、expansion、all；2026-08 取代 `include_xpac`）[S21][S22]。[LIVE] `per_page=200` 仍被接受（文档写上限 100） |
| 增量 | `publication_date` 区间免费档可用；⚡ `from_created_date`/`from_updated_date` 需 Premium/Institutional/Partner 计划（[LIVE] "Plan upgrade required"）；Member+（$10,000/年）含"日同步 + from_updated_date"[S18][S25] |
| 限速/计费 | 100 req/s 硬顶；单实体免费、列表 $0.0001、搜索与语义搜索 $0.001、PDF/TEI $0.01；无 key $0.10/天（[LIVE] `x-ratelimit-limit: 1000` 积分）、免费 key $1/天、Member $20/天、Member+ $100/天、Partner ≥$200/天；响应头 `x-ratelimit-*` + `meta.cost_usd` [S13][S14][S18][S25] |
| 许可 | 数据 CC0 [S19]；**不直接提供明文摘要（法律原因）**，只给倒排索引 [S23]；PDF/TEI 保留原作品版权，OpenAlex 不授予额外权利 [S17] |
| bulk | S3 `s3://openalex` 免费匿名（`--no-sign-request`），**季度**发布（1/4/7/10 月第二个周三），JSONL 约 745 GB、Parquet 约 770 GB；付费日快照；`deleted_ids` 删除日志 [S16]；PDF 同步为年度计划付费附加（约 250 TB）[S17][S18] |
| 2025–2026 变化 | ⚡ 2025-11-03 Walden 重写上线（参考文献、OA 检测、语言与许可覆盖改进）[S20]；⚡ 2026-02 起 API key + 用量计费（v1 已记）；⚡ 2026-02-24 语义搜索 beta、PDF/TEI 下载、文档重建 [S15]；⚡ 2026-08 `corpus=`；⚡ 快照改季度；Concepts 弃用、改用 Topics；`mailto`/polite pool 失效 [S21] |
| v2 结论 | **P0**：覆盖面主干（跨学科发现、主题路由、作者/机构/资助维度、OA 定位、撤稿）；**以季度快照建本地索引 + API 按 `publication_date` 补新**；付费档只在"近实时全量同步"需求出现时再评估 |

#### 2.2.3 Semantic Scholar（`s2`，v1 已实现为 enrich 通道，需 key）

| 维度 | 事实 |
|---|---|
| 覆盖/规模 | 2.14 亿论文、24.9 亿引用、7,900 万作者 [S27]；[LIVE] 最新 Datasets release 2026-09-22：papers 2 亿、abstracts 1 亿、citations 24 亿、embeddings-specter_v2 1.2 亿、s2orc_v2 1,600 万全文、tldrs 5,800 万 [S29] |
| 字段 | paperId/externalIds、abstract、tldr、fieldsOfStudy/s2FieldsOfStudy、citations（含 contexts、intents、isInfluential）、references、openAccessPdf、embedding（`embedding.specter_v2` 显式选 v2）、authors（S2 作者 ID）、publicationVenue [S31][S29] |
| 查询 | [LIVE swagger] `/paper/search`（≤100/页）、`/paper/search/bulk`（token 续页，可按 paperId/publicationDate/citationCount 排序）、`/paper/search/match`、`/paper/autocomplete`、`/snippet/search`、`/paper/batch`（≤500 id、≤10 MB）、citations/references（≤1000/页）；过滤 publicationDateOrYear、year、venue、fieldsOfStudy、publicationTypes、openAccessPdf、minCitationCount [S31] |
| 推荐 | [LIVE swagger] `POST /recommendations/v1/papers/`（`positivePaperIds` + `negativePaperIds`，limit ≤500）；`GET /papers/forpaper/{id}`（`from` 取 recent 或 all-cs）[S30] |
| 增量 | Datasets 周更 + `GET /datasets/v1/diffs/{start}/to/{end}/{dataset}` 增量包 [S32]；bulk search 按 publicationDate 排序 |
| 限速 | 匿名：官方称所有匿名用户共享 1000 RPS、高峰节流；[LIVE] 匿名 DOI 查询返回 404、搜索返回 429（提示申请 key）；有 key：入门 1 RPS（全端点）[S27] |
| 许可 | API License Agreement（2023-05-17）：授予"有限、非独占、不可转让、不可再许可、可终止"的使用许可，用于在第三方产品中访问和展示 S2 Data；⚠ 核验更正：条款**没有**明文"允许商业与非商业使用"，商用既未明文授权也未明文禁止，平台若商业化须向 AI2 书面确认；须署名 "Semantic Scholar"；不得重新打包、出售、出租、分发或再许可 API；经 API 取得的数据按各自许可（条款举例 CC BY-NC 或 ODC-BY）[S28]。[LIVE] 数据集 README：papers/abstracts/citations/tldrs/s2orc_v2 为 ODC-BY，嵌入为 Apache-2.0 [S29] |
| bulk | 全量下载需 key；按 release 发放 S3 预签名链接 [S29] |
| v2 结论 | **P1（嵌入/推荐专用，申请到 key 后升 P0）**：SPECTER2 嵌入做论文向量冷启动与相似召回；Recommendations 正负样本接口可直接映射"赞/踩"反馈；TLDR（ODC-BY）可作卡片短摘要；不作元数据主干 |

#### 2.2.4 Unpaywall（`unpaywall`，v1 已实现 RESOLVE）

| 维度 | 事实 |
|---|---|
| 状态 | ⚡ 2025 年末迁到 OpenAlex 数据库，两者使用同一份数据；DOI 查询 API、浏览器扩展、Data Feed 继续保留；"搜索、列刊、查仓储等其它用途请用 OpenAlex" [S24] |
| 覆盖 | 只覆盖 Crossref DOI，不含 DataCite DOI [S24] |
| 端点 | `GET /v2/{doi}?email=`；[LIVE] 根路径返回 version 1.3.0；缺 email 返回 422 [S39]；Simple Query Tool 一次可提交 1,000 个 DOI（结果邮件发送）[S24] |
| 限速 | 100,000 次/日 [v1 2026-07-20]；⚠ 本次未复核（官网为 JS 渲染） |
| v2 结论 | **P1（兼容层）**：保留 v1 的"DOI → OA 副本"兜底；新能力一律用 OpenAlex `best_oa_location`/`locations` |

#### 2.2.5 CORE（`core`，v1 设计存档、未实现）

| 维度 | 事实 |
|---|---|
| 覆盖/规模 | 4 亿+记录、可机器访问的全文 4,000 万+（about 页）[S36]；v1 记为 431M/46M（2025-11）[v1] |
| 端点 | `/v3/search/works`、`/v3/works/{id}`、`/download`、`/recommend`；Elasticsearch 式查询 [v1] |
| 限速 | 未认证：100 token/日、每分钟最多 10 次，**不提供全文**；注册个人：1,000/日、25/分；注册学术（非会员机构）：5,000/日、10/分；会员机构/非学术组织：约 200k/日；简单查询 1 token、复杂查询 3–5 token；响应头 `X-RateLimit-*` [S33] |
| 许可 | API 可商用（须遵守 T&C；机构/企业有 30 天试用，可申请免费许可）[S34]；旧版 dump 免费、ODC-By，新版 dump 需购买许可（会员免费）[S35] |
| robots | [LIVE] `core.ac.uk` 禁止 `/search`；api 主机只有 content-signal 样板说明，无具体指令 [S37] |
| v2 结论 | **P1**：OA 全文兜底（排在 OpenAlex/Unpaywall 之后）、仓储绿色 OA 发现；需注册 key（个人档或学术档） |

#### 2.2.6 BASE（Bielefeld Academic Search Engine）

| 维度 | 事实 |
|---|---|
| 访问 | [LIVE] HTTP 检索接口对未登记 IP 返回 `{"error": "Access denied for IP address … and user agent …"}`；`api.base-search.net` robots 为 `Disallow: /`；`www` 站 robots（2025-09-16 更新）：`Crawl-delay: 2`，只放行首页/高级检索/about，具名封禁 ClaudeBot、anthropic-ai、AI2Bot、Scrapy、GPTBot 等，并附"未经明确许可禁止自动获取，违者追究"的法律声明；about/开发者页面由 Anubis 工作量证明挑战保护 [S38] |
| 规模/条款 | ⚠ 未核验（文档页被 Anubis 拦截） |
| v2 结论 | **排除**（除非取得 Bielefeld 大学图书馆书面授权并登记 IP）；其覆盖可经 CORE/OpenAIRE/OpenAlex 间接获得 |

#### 2.2.7 DOAJ

| 维度 | 事实 |
|---|---|
| 覆盖 | [LIVE] 收录期刊 23,544 本；2026 年文章 926,488 条 [S43] |
| 字段 | 文章 bibjson：abstract、author、identifier、journal、keywords、link、subject（LCC 分类）、title、year；期刊级 bibjson（以 eLife 为例）：apc（金额/币种）、boai、copyright、deposit_policy、editorial、license（如 CC BY、CC0）、oa_start、plagiarism、preservation、publication_time_weeks、subject（LCC）、waiver 等 [LIVE S43] |
| 端点 | API v4.0.0（`/api/search/journals/…`、`/api/search/articles/…`）、OAI-PMH、期刊 CSV [S40] |
| 限速 | 全部路由 2 req/s，突发最多排队 5 个 [S40] |
| 许可 | 期刊级、文章级元数据均为 CC0 [S42] |
| bulk | ⚡ 全量 dump 需邮件申请、逐案审批；全体用户月更、付费高级用户日更；期刊 CSV 可直接下载 [S41] |
| robots | [LIVE] 仅禁止 `/search`、`/account`、`/admin` 等，`/api/*` 未被禁止 |
| v2 结论 | **P1**：OA 期刊白名单与期刊质量信号（是否被 DOAJ 收录、许可类型）、venue 名录种子（期刊 CSV） |

#### 2.2.8 OpenAIRE Graph

| 维度 | 事实 |
|---|---|
| 覆盖 | [LIVE] Graph API v1 `researchProducts?type=publication` numFound = 238,619,345 [S76] |
| 端点 | Graph API、SKG-IF API、ScholeXplorer（文献—数据链接）、Broker、DSpace/EPrints API [S74] |
| 限速 | 文档（v11.4.0）：认证请求最多 7,200 次/小时，匿名最多 60 次/小时；个人 token 有效期 1 小时 [S74]。[LIVE] 匿名请求返回 `x-ratelimit-limit: 7199`，与文档不符，⚠ 以文档为准保守执行 |
| 许可 | CC-BY（商业、非商业均可，须注明 OpenAIRE 为来源）[S74] |
| bulk | Zenodo 全图 dump（DOI 10.5281/zenodo.3516917，CC-BY 4.0，按实体分文件、单文件 ≤10 GB）[S75] |
| v2 结论 | **P2**：资助/项目维度（欧洲资助方强）、欧洲仓储覆盖补充；以 dump 为主 |

#### 2.2.9 OpenCitations

| 维度 | 事实 |
|---|---|
| 覆盖 | Index：25 亿+ 条引用（2026-07-28 更新）；Meta 2026-06 dump：1.47 亿书目实体、4.22 亿作者、230 万 venue（已对齐 OpenAlex ID）[S78] |
| 端点 | Index REST v2（v2.2.0，2025-04-15）：`citation`、`citation-count`、`venue-citation-count`、`reference-count`、`citations`、`references`；Meta API；SPARQL；SKG-IF [S77] |
| 限速 | 每 IP 180 次/分钟；建议申请 access token 放入 `authorization` 头；大规模取数用 dump [S77] |
| 许可 | 全部数据 CC0 [S79] |
| 交叉校验 | [LIVE] DOI 10.1371/journal.pmed.0020124：OpenCitations 被引 9,262，OpenAlex `cited_by_count` 10,801 [S25] |
| v2 结论 | **P1**：CC0 引文图（可合法缓存和展示），用于引文扩展、"被引增量"热度信号，并与 OpenAlex 交叉校验 |

#### 2.2.10 Europe PMC

| 维度 | 事实 |
|---|---|
| 覆盖 | [LIVE] 全库 48,938,549 条；`OPEN_ACCESS:y` 8,273,746 条；预印本（`SRC:PPR`）1,247,001 条 [S45] |
| 端点 | [LIVE] REST v6.9：`search`/`searchPOST`（`cursorMark` 深翻，pageSize ≤1000）、`article`、`references`、`citations`、`fullTextXML`、`supplementaryFiles`、`datalinks`、`profile`、`fields`、`evaluations` [S44] |
| 限速 | ⚠ 数值未核验（官网文档页受 Cloudflare 挑战，OpenAPI spec 中没有限速条款）。核验补充：Europe PMC 团队在开发者论坛（2024-12-11）只确认"API 限额按 IP 计"，提问中提到的 10 次/秒、500 次/分钟未获官方确认 [S118] |
| bulk | [LIVE] `ftp.ebi.ac.uk/pub/databases/pmc/`：`oa/`（2026-09-26 更新）、`preprints/`、`PMCLiteMetadata/`、`TextMinedTerms/` 等 [S46]。⚠ 核验补充：`ftp.ebi.ac.uk/robots.txt` 为 `User-agent: * / Disallow: /`，与 NCBI FTP 主机同属"bulk 主机全禁"，经 HTTPS 批量下载前须由 Q1 的 ADR 登记依据 [S123] |
| robots | ⚠ 核验更正（2026-09-26 复测）：`www.ebi.ac.uk/robots.txt` 除封禁个别爬虫（sogou、MJ12bot 等）外，**通用 UA 组（`User-agent: *`）设有 `Crawl-Delay: 10` 与 170 条 Disallow**；这些 Disallow 不覆盖 `/europepmc/webservices/rest/`，所以 REST 路径允许访问，但若按 robots 执行，每次请求须间隔 10 秒（原文"通用 UA 不受限"不准确）[S117] |
| v2 结论 | **P0（生物/医学/心理）**：生物医学主通道（期刊 + 预印本、MeSH、全文 XML、引文），摘要展示遵循 §4 的摘要策略 |

#### 2.2.11 PubMed / PMC（NCBI）

| 维度 | 事实 |
|---|---|
| 覆盖 | [LIVE] einfo：PubMed 41,210,260 条（lastupdate 2026/09/26）[S47] |
| 端点/限速 | E-utilities；[LIVE] 无 key 时 `x-ratelimit-limit: 3`（每秒）[S47]；有 key 默认 10 次/秒（核验确认：NCBI Insights 2017-11-02 官方公告，2018-05-01 起执行，更高速率可申请）[S111] |
| robots | ⚡ [LIVE] `eutils.ncbi.nlm.nih.gov/robots.txt` 为 `User-agent: * / Disallow: /`。⚠ 核验补充：bulk 所在的 `ftp.ncbi.nlm.nih.gov/robots.txt`（HTTPS）**同样是 `User-agent: * / Disallow: /`**，经 HTTPS 下载 baseline/updatefiles 也会落在 robots 冲突里，不能当作"避开 robots"的通道；NLM 官方文档邀请批量下载，这一冲突须一并交给 Q1 的 ADR 裁定 [S113] |
| bulk | PubMed 年度 baseline（2026 版：pubmed26n0001–1334，每年 12 月发布）+ 日更 updatefiles（截至 2026-09-25 已到 pubmed26n1638）[S48]（核验未复访：该主机 robots 全禁）；⚡ PMC 旧版 FTP 数据集 2026-08 起下线，统一改用 PMC Cloud Service（AWS，免费、免登录）[S49]。核验补充：按 NCBI 2026-02-12 公告，2026-08 同时停用 **PMC OA Web Service API**；新 Cloud Service 中的文件**逐篇单独提供**，不再有压缩包或批量包，全量同步须按文件清单增量拉取 [S112] |
| 许可 | 须明确声明 NLM 为数据来源；部分摘要受版权保护；再分发者须保持数据为最新，或明示非最新；PMC 只可再分发许可允许再分发的数据 [S48][S49] |
| v2 结论 | **P0（生物/医学/心理）**：以 baseline + updatefiles 本地化为主，E-utilities 只做按 PMID 的少量补查。注意 FTP 主机与 E-utilities 主机的 robots 都是全禁，两条通道都须等 Q1 的 ADR 逐源登记后才能启用（核验更正：原文"bulk 可避开 robots 冲突"不成立） |

#### 2.2.12 DBLP（`dblp`，v1 已实现但已出列，D-037）

| 维度 | 事实 |
|---|---|
| robots | ⚡ [LIVE] `dblp.org`、`dblp.uni-trier.de`、`dblp.dagstuhl.de`（三者逐字节相同）：163 个具名 AI/agent UA 共用一组 `Disallow: /`，外加 `User-agent: * / Disallow: /`（167 行，4,125 字节）[S51] |
| 合规通道 | [LIVE] `sparql.dblp.org` robots：`Crawl-delay: 10`、`Allow: /sparql`、`Allow: /download`、其余 Disallow；`/download/dblp_KG_with_associated_data.tar`（6.1 GB，2026-09-26）[S52]；DROPS 月度快照 `dblp-2026-09-01.xml.gz` 1.02 GB，CC0，DOI 10.4230/dblp.xml.2026-09-01 [S53]；DROPS robots 只禁 `/api/*`、`/metadata/*/*`、`/entities/*/metadata/*` [S54] |
| 规模 | ⚠ 本次未复核（未访问主站）；v1 记 866 万出版物、7,140 个会议、1,900 种期刊 [v1] |
| v2 结论 | **P1（只用离线快照 + SPARQL）**：CS 会议卷目录与作者 PID 消歧；v1 在线 adapter 路径（`/db/**`）停用 |

#### 2.2.13 ORCID

| 维度 | 事实 |
|---|---|
| 限速 | 匿名 API：12 req/s（突发 40）、每 IP 每天 2.5 万次读取；注册 Public API：12 req/s、每个 client ID 每天 10 万次；Member API：24 req/s，无配额 [S55] |
| 条款 | Public API 仅限非商业用途（不得收取再使用费，不得用于任何产生收入的产品或服务），条款最后更新 2024-10-23 [S56] |
| robots | ⚡ [LIVE] `pub.orcid.org` 为 `Disallow: /` [S57] |
| bulk | 年度公共数据文件（CC0，发布在 figshare，官方列出 2020–2025 各年版本；核验确认）[S120] |
| v2 结论 | **P1**：由用户通过 OAuth 授权读取**本人** ORCID 记录（作品、任职）作为兴趣冷启动与作者身份绑定；平台级批量需求改用年度数据文件；平台若商业化，需成为 ORCID Member |

#### 2.2.14 DataCite

| 维度 | 事实 |
|---|---|
| 覆盖 | [LIVE] `api.datacite.org/dois` 共 135,809,025 个 DOI [S64] |
| 限速 | 认证：3,000 次/5 分钟/IP；带身份标识（UA 含邮箱或 `mailto=`）：1,000 次/5 分钟；匿名：500 次/5 分钟；doi.org 内容协商：1,000 次/5 分钟 [S58] |
| bulk | 年度公共数据文件（CC0；2025 版 2026-01-06 生成，DOI 10.14454/t5qb-d995）；月度数据文件只对会员开放 [S60][S61][S62] |
| 变化 | ⚡ GraphQL API 将于 2027-07 弃用 [S59]；⚡ Event Data：2026 Q3 停止摄入范围外事件，Q4 删除 [S63] |
| v2 结论 | **P2**：数据集、软件、部分预印本 DOI 的元数据与关联关系（`is-supplement-to` 等）；注意 Unpaywall 不覆盖 DataCite DOI |

#### 2.2.15 ROR

| 维度 | 事实 |
|---|---|
| 限速 | 目前无需注册，每 IP 2,000 次/5 分钟；社区已通过的方案是"带 client ID 2,000 次/5 分钟、不带只有 50 次/5 分钟"，但 client ID 注册暂停期间不按有无 ID 区分限速 [S65][S66] |
| bulk | Zenodo dump（DOI 10.5281/zenodo.6347574，CC0）；也可用 Docker 在本地部署 ROR API [S67][S65] |
| v2 结论 | **P1**：机构归一（用户的机构偏好、机构订阅 ↔ 出版商访问映射），以 dump 本地化 |

#### 2.2.16 Zenodo

| 维度 | 事实 |
|---|---|
| 覆盖 | [LIVE] `resource_type.type:publication` 共 4,837,975 条 [S69] |
| 限速 | 访客：60 次/分钟、2,000 次/小时；认证用户：100 次/分钟、5,000 次/小时；搜索 REST 与 OAI-PMH 各 30 次/分钟；OAI 每页 50 条，resumptionToken 2 分钟内有效 [S68] |
| robots | [LIVE] 禁止 `/api`（只放行 `/api/records/*/files`）和 `/search`，`Crawl-delay: 10`；`/oai2d` 未被禁止 [S69] |
| 许可 | 元数据 CC0；文件按各自许可 [S68] |
| v2 结论 | **P2**：用 OAI-PMH 按 community/set 增量收割（会议社区、学科社区等）；不走 `/api` 检索 |

#### 2.2.17 OSF（含 SHARE）

| 维度 | 事实 |
|---|---|
| 覆盖 | [LIVE] 32 个预印本社区（psyarxiv、socarxiv、edarxiv、metaarxiv、mindrxiv 等），共 202,217 篇预印本 [S70] |
| robots | ⚡ [LIVE] `api.osf.io` 为 `Disallow: /`；`osf.io` 禁止 `/api/*`，`crawl-delay: 10`，并具名封禁 GPTBot、PerplexityBot、Meta-ExternalAgent；`share.osf.io` 禁止 `/api/*` 与 `/oai-pmh/*` [S70] |
| 旁路 | [LIVE] Center for Open Science 是 Crossref 会员 15934，名下 23 个前缀（PsyArXiv 10.31234、SocArXiv 10.31235、EdArXiv 10.35542、OSF Preprints 10.31219、BITSS 10.31222、MindRxiv 10.31231 等），DOI 共 230,767 个；PsyArXiv posted-content 66,794 条 [S71] |
| v2 结论 | **P1（经 Crossref 前缀枚举）**：心理学/社科预印本"最新论文"用 Crossref `prefix + type:posted-content + from-index-date` 获取，不直连 OSF API |

#### 2.2.18 HAL

| 维度 | 事实 |
|---|---|
| 覆盖 | [LIVE] 4,673,169 条，其中带全文文件 1,800,217 条 [S73] |
| robots | [LIVE] `api.archives-ouvertes.fr` 禁止 `/search/`、`/*/search/`、`/ref/`、`/oai/`、`/sword/`；而 `hal.science/robots` 注释大意为"如需大量下载元数据请使用 API，API 更适合元数据收割"（英文原文见 [S72]） |
| 许可 | 核验补充（2026-09-26）：HAL 官方文档《conditions de réutilisation》写明 **CC-0 自动适用于全部存缴的元数据**；带文件的存缴按其所选许可（CC 系列、Etalab、版权保留等）；自 2026 年 2 月起，所有上传文件（主文件和附件）都必须标注许可 [S115] |
| v2 结论 | **P2**：法国/欧洲绿色 OA 全文与元数据；API 可否使用以 Q1 的 ADR 为准，ADR 之前经 CORE/OpenAlex 旁路 |

#### 2.2.19 Wikidata / WikiCite

| 维度 | 事实 |
|---|---|
| 变化 | ⚡ 2025-05-09 WDQS 图拆分：学术文章迁入独立端点 `query-scholarly.wikidata.org`，主端点 `query.wikidata.org` 不再含学术文章，跨两图的查询须用 SPARQL 联邦；legacy 全量端点保留到 2025-12 [S81] |
| 限速 | 单次查询 60 秒截止；每个客户端（UA + IP）每 60 秒最多 60 秒处理时间；每分钟最多 30 次错误查询；每 IP 最多 5 个并行查询；超限返回 429 + Retry-After；UA 不合规可能被封 [S82] |
| 许可 | 结构化数据 CC0 [S83] |
| v2 结论 | **P2**：实体链接与跨库 ID 映射（作者、期刊、机构的多标识），不作论文主源 |

#### 2.2.20 Fatcat / Internet Archive Scholar

| 维度 | 事实 |
|---|---|
| 状态 | ⚠ [LIVE] `fatcat.wiki`、`api.fatcat.wiki`、`guide.fatcat.wiki` 均在 25 秒内 TCP 连接超时（从本次网络环境看不可达，无法区分是服务下线还是网络问题）；`scholar.archive.org/search` 302 跳转到 `/verify`（ALTCHA 挑战），robots 禁止 `/search`、`/verify`、`/altcha/`，只提供 sitemap [S80]。核验补充：2026-09-26 复测 `fatcat.wiki`、`api.fatcat.wiki` 仍然 20 秒连接超时；GitHub `internetarchive/fatcat` 最近一次推送是 2024-07-31，最后几次提交为"spn-retire""decom-pixy"等退役性质的变更，项目至少处于停更状态 [S121] |
| v2 结论 | **仅元数据/观察**：可作为长尾 OA 保存副本的链接来源，不做自动检索 |

#### 2.2.21 Lens.org

| 维度 | 事实 |
|---|---|
| API | Lens API 2.19.3（文档最后更新 2026-04-17）；token 认证（Bearer 头或 `?token=`）；申请时须提交全名、机构地址、用途说明；须展示 Lens logo 署名；响应头给出每分钟、每月请求量和每月记录量的剩余额度 [S84] |
| 条款 | Scholarly API 条款 v2026.06.01：试用仅限非商业；正式使用"只能通过机构订阅获得"；商业用途须签定制合同；不得转让或转售 [S85] |
| v2 结论 | **仅元数据**：只作为用户自带机构 token 的私有富化（专利—论文关联），平台层不作数据源 |

#### 2.2.22 Dimensions

| 维度 | 事实 |
|---|---|
| 条款 | 只向**非商业科学计量研究项目**免费开放（Analytics、API、BigQuery），需申请 [S86]；其余为商业订阅 |
| v2 结论 | **排除（平台层）**：v2 的发现与推荐不属于"科学计量研究项目" |

#### 2.2.23 Scopus（Elsevier）

| 维度 | 事实 |
|---|---|
| 配额 | Scopus Search：每周 2 万次、9 次/秒（不用游标时结果上限 5,000 条）；Abstract Retrieval：每周 1 万次、9 次/秒；Citations Count：每周 5 万次、10 次/秒；超额返回 429 + `QUOTA_EXCEEDED` [S87] |
| 政策 | 按用例授权。例如"展示被引数"用例要求应用**不能主要是（科学）搜索引擎、A&I 数据库或全文聚合器**；IR/CRIS 用例不得公开展示摘要；科学计量研究只限非商业，且不得挖掘整个数据集 [S88] |
| v2 结论 | **排除（平台层）**；可选：用户自带机构 key、在本地私有使用（只富化被引数，不对外展示） |

#### 2.2.24 Web of Science（Clarivate）

| 维度 | 事实 |
|---|---|
| 配额 | Starter API：免费试用档对任何人开放，1 次/秒、每天 50 次，不返回被引数；机构会员档（订阅机构）5 次/秒、每天 5,000 次；机构集成档每天 2 万次（只批给机构管理人员）[S89] |
| v2 结论 | **排除（平台层）**；可选：用户自带机构 key 的私有富化 |

#### 2.2.25 Google Scholar（排除，理由复核）

| 维度 | 事实 |
|---|---|
| robots | [LIVE] 禁止 `/search`、`/scholar`、`/citations?`（个人主页等少数路径放行）[S90] |
| 其它 | 无官方 API；ToS 禁止自动查询；v1 已记录挑战与法律风险 [v1] |
| v2 结论 | **排除**：维持需求 §5 与 v1 结论，只建议用户自行配置 Scholar Alerts 邮件互补 |

#### 2.2.26 Microsoft Academic（历史）

| 维度 | 事实 |
|---|---|
| 状态 | 2021-05-04 宣布退役：网站与 Academic Knowledge API 在 2021-12-31 后停止访问，MAG 停止更新；官方推荐的替代包括 OpenAlex、Crossref、Semantic Scholar、OpenCitations、Lens 等 [S91] |
| v2 结论 | **历史**：OpenAlex 承接了 MAG 的 ID 体系与数据，v2 只需兼容 `mag` 这一外部 ID 类型 |

#### 2.2.27 学科聚合源（理科、社科）

| 源 | 学科 | 事实 | v2 结论 |
|---|---|---|---|
| **INSPIRE-HEP** | 高能物理/天体粒子 | [LIVE] `/api/literature` 共 1,888,025 条；每 IP 每 5 秒 15 次，超限 429，被拒请求也计入配额；大部分元数据 CC0（部分字段受限，不允许批量收集邮箱）；robots 放行 `/api/literature`，只禁 accounts/submissions/import/holdingpen 等 [S92] | **P1**：物理 HEP 子域主源（人工策展的引用、作者、实验、机构） |
| **NASA ADS** | 天文/天体物理（兼物理） | 须注册 ADS 账户并生成 token；响应头 `X-RateLimit-Limit` 示例为每天 5,000 次（UTC 午夜重置）；受 ADS Terms of Use 约束 [S93]；UI 帮助页为 JS 渲染，未读到正文 | **P2**：用户或平台自带 token 时启用的天文检索与引用源 |
| **zbMATH Open** | 数学 | [LIVE] `api.zbmath.org/v1/document/_search` 可用（`py:2026` 命中 125,723 条），字段含 `msc`（MSC2020）、`references`、`keywords`、`contributors`、`license`、`zbmath_url`；主站 `zbmath.org` 连 robots.txt 都在 Cloudflare 托管挑战之后；API 条款页 `static.zbmath.org/legal/api-terms-and-conditions.html` 返回 403 [S94]。核验补充：同一条款的 API 主机副本 `api.zbmath.org/v1/static/terms-and-conditions.html`（OAI 主机有相同副本）可读，写明 **"All data are allowed to be used under a CC-BY-SA license"**，并要求控制请求速率；API 对部分条目返回"zbMATH Open Web Interface contents unavailable due to conflicting licenses"，评论/摘要并非全部可得 [S114] | **P1**：数学 MSC 分类路由与评论/引用补充；CC BY-SA 属于"署名 + 相同方式共享"，平台缓存或再展示须署名，并评估 ShareAlike 对衍生数据集的约束 |
| **MathSciNet（AMS）** | 数学 | 订阅产品；[LIVE] robots `Disallow: /`，只放行 `/mathscinet/MRAuthorID`、`/mathscinet/publications-search`，`Crawl-delay: 10` [S95] | **排除自动化**（订阅内人工使用） |
| **Europe PMC / PubMed** | 生物医学、心理（部分） | 见 §2.2.10–2.2.11 | P0 |
| **EconBiz（ZBW）** | 经济/商管 | [LIVE] `api.econbiz.de/v1/search` 与 `record` 可用，支持按作者/主题的 "More like this"；文档中未检出数据许可 ⚠ [S96] | **P2**：德语区及机构工作论文的补充检索 |
| **RePEc** | 经济 | v1 已定位为 enrich 通道（bulk ReDIF 本地 join、零 HTML，JEL 与"工作论文↔正式发表"独家价值）[v1 repec.md][S109] | **P1**（维持 v1） |
| **EconStor / SSOAR** | 经济 / 社会科学 OA 仓储 | [LIVE] EconStor robots 禁止 `/discover`、`/simple-search` 与各类浏览页，提供 sitemap；SSOAR 本次 robots 请求连接失败 ⚠ | **仅元数据**：经 CORE/OpenAlex 覆盖 |

#### 2.2.28 中文与区域平台

| 源 | 类型 | 事实（[LIVE] 2026-09-26） | 合规边界与 v2 结论 |
|---|---|---|---|
| **CNKI 中国知网** | L2-aggregator（商业全文库） | `kns.cnki.net/robots.txt` 为 `User-agent: * / Disallow: /`；`www`/`oversea` 的 robots 返回 404 页 [S97]；无公开元数据 API（⚠ 未发现官方开放接口文档） | **排除自动化**：只支持用户在机构授权下**手动导出**题录（RIS/EndNote 等）后导入 v2 个人库；不做代理、不绕开 IP 授权 |
| **万方数据** | L2-aggregator（商业） | `www.wanfangdata.com.cn/robots.txt` 404；检索子域 `s.wanfangdata.com.cn` 返回 "fault filter abort"（WAF 拦截）[S98] | **排除自动化**：同 CNKI，只支持用户导入 |
| **维普（CQVIP）** | L2-aggregator（商业） | `www.cqvip.com` robots 只封禁部分百度子爬虫；`qikan.cqvip.com` 禁止 `/Read/Read.aspx` [S99]；未发现开放 API ⚠ | **排除自动化**（全文订阅制）；只支持用户导入 |
| **ChinaXiv** | L1-preprint（中科院预印本） | 首页可访问：ChinaXiv 论文 47,810 篇，另索引国际预印本 4,104,372 篇；`/robots.txt` 返回 403 且页面为"系统正在维护中"[S100]；OAI 等机器接口 ⚠ 未核验 | **仅元数据/观察**：robots 恢复可读后再评估；可先经 Crossref/OpenAlex 旁路（⚠ 其 DOI 注册情况未核验） |
| **中国科技论文在线（paper.edu.cn）** | L2-repository | 全站显示"网站维护升级提示：…暂停所有线上服务"[S101] | **暂缓**：维护结束后复核 |
| **J-STAGE（日本 JST）** | L1-journal-platform（兼聚合） | WebAPI [LIVE] 可用（`service=3` 文章检索，Atom XML；必须带 issn/cdjournal/keyword 等参数之一，否则返回 ERR_012）；条款仅有日文版；**商业用途须事先申请**；浏览政策不允许大批量下载；须注明出处；2026-03-26 新增期刊检索功能；`www` 的 robots 禁止 `/*_pdf` [S102][S103] | **P2**：日本学会期刊元数据（按期刊增量）；多用户平台若有收费属性，须先申请商业许可 |
| **SciELO** | L2-aggregator（拉美/伊比利亚 OA 期刊网络） | ArticleMeta API [LIVE] 可用（`collection=scl` 巴西合集 564,934 篇）；`www.scielo.org` robots `Crawl-delay: 10`；检索站 `search.scielo.org` 在 Bunny Shield 挑战之后 [S104] | **P2**：拉美 OA 期刊（大多有 Crossref DOI），可按合集增量 |
| **Redalyc** | L2-aggregator（拉美 OA） | `www.redalyc.org/robots.txt` 返回 403（IBM HTTP Server）[S105]；OAI-PMH 端点 ⚠ 未核验 | **仅元数据**：经 OpenAlex/Crossref/DOAJ 旁路 |

#### 2.2.29 核验补充：原稿遗漏的来源

> 以下条目由核验阶段补充（2026-09-26），只写已核到的事实，其余标 ⚠。

| 源 | 类型 | 事实 | v2 结论 |
|---|---|---|---|
| **Jisc Open policy finder**（由 Sherpa Romeo/Juliet/Fact 合并而来，⚠ 合并时间只见第三方报道） | 政策注册表（期刊/出版方自存档政策、资助方 OA 要求） | "What's new" 页：2026-02-11 发布新 API，旧 Sherpa API 原定 2026-04 退役；2026-05-07 公告迁移期延长到 2026-07；站点内容标注 **CC BY-NC-ND 4.0** [S116]。新 API 的注册方式与额度 ⚠ 未核验（`v2.sherpa.ac.uk` 本次被 Jisc WAF 返回 403） | **P2**：判定"某版本全文能否公开共享"的辅助信号（出版方允许存档的版本、禁运期）；NC-ND 意味着不能把其数据加工后对外展示，商业化前须与 Jisc 谈许可 |
| **OpenDOAR**（Jisc，OA 仓储名录） | 仓储注册表 | ⚠ 未核验：`v2.sherpa.ac.uk/opendoar` 本次被 WAF 返回 403，其现状以及与 Open policy finder 的关系都未能从官方页确认 | **观察**：可用于枚举机构仓储的 OAI-PMH 端点；启用前须重新核验 API 与许可 |
| **CiNii Research**（日本 NII） | L2-aggregator（日本学术信息） | OpenSearch API（`cir.nii.ac.jp/opensearch/{type}` 与 `/opensearch/v2/{type}`）**必须带 `appid`**；每页 1–200 条，`start` 最大 10,000；输出 html/rss/atom/json [S119]。⚠ `cir.nii.ac.jp/robots.txt` 对通用 UA 只放行 `/`、`/crid/`、`/sitemaps/`、`/resourcesync/`（`Crawl-Delay: 1`），其余路径包括 `/opensearch` 都是 `Disallow`，与 API 文档冲突；ResourceSync 是 robots 放行的批量同步通道 [S119]。覆盖范围（机构仓储、KAKEN 等）⚠ 未核验 | **P2（日本）**：与 J-STAGE 互补；在线 API 纳入 Q1 的 ADR，默认先评估 ResourceSync |

### 2.3 跨源对比

#### 2.3.1 字段可得性矩阵

> 图例：**Y** = 有且开放可取；**P** = 部分（按存缴/覆盖不全/粗粒度）；**K** = 需 key 或注册；**$** = 付费或订阅；**N** = 无；⚠ = 未核验。依据见 §2.2 各源 [S#]。

| 源 | 摘要 | 参考文献 | 被引列表 | 主题分类 | 作者消歧 | 机构/ROR | 资助 | OA 状态/位置 | 嵌入/语义 | 撤稿/更正 | 全文 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Crossref | P（存缴，版权保留） | P（存缴，事实） | N（仅计数） | N ⚠ | P（ORCID 存缴） | P（ROR 存缴） | P（funder/award） | P（`license`，无 OA 分类） | N | **Y**（`update-to` + Retraction Watch） | N（TDM 链接指向出版方） |
| OpenAlex | P（倒排索引，2022 年作品 >60%） | Y | Y（`cites:` 过滤） | **Y**（4 级 Topics + keywords + MeSH + SDG） | Y | Y | Y（funders/awards） | **Y** | P（语义搜索 beta，不提供向量）⚠ | Y（`is_retracted`） | $（OA 作品 PDF/TEI 按次计费） |
| Semantic Scholar | P（数据集 1 亿，ODC-BY） | Y·K | **Y·K**（含 intent/context/influential） | P（fieldsOfStudy 粗粒度） | Y | P ⚠ | N ⚠ | P（`openAccessPdf`） | **Y**（SPECTER2） | ⚠ | P（s2orc_v2 1,600 万，ODC-BY） |
| OpenCitations | N | Y | **Y**（CC0） | N | P（Meta） | N | N | N | N | N | N |
| OpenAIRE Graph | P | ⚠ | P（关系）⚠ | P ⚠ | P（ORCID） | Y（组织） | **Y**（项目，欧洲资助强） | Y | N | ⚠ | N |
| CORE | P ⚠ | ⚠ | N ⚠ | ⚠ | P | P（数据提供方） | N ⚠ | Y（全为 OA） | N | N | **Y·K**（未认证不给全文） |
| DOAJ | P | N | N | Y（LCC） | N | N | N | Y（刊级许可/APC） | N | N | N（链接） |
| Europe PMC | Y（版权保留） | Y | Y | Y（MeSH + 文本挖掘术语） | P | P | ⚠ | Y | N | ⚠ | Y（OA 子集 XML） |
| PubMed | Y（版权保留） | P ⚠ | N ⚠ | Y（MeSH） | P | P | P ⚠ | P（PMC 链接） | N | P ⚠ | N |
| DBLP（快照） | N | N | N | N | **Y**（人工策展 PID） | N | N | ⚠ | N | N | N |
| DataCite | P（description） | Y（relatedIdentifiers） | P（计数） | P（subjects） | P | P | Y（fundingReferences） | P（rights） | N | N | N |
| INSPIRE | Y | Y | Y | P ⚠ | Y | Y | ⚠ | P | N | ⚠ | N |
| zbMATH Open | P（评论/摘要）⚠ | Y | ⚠ | **Y**（MSC2020） | Y ⚠ | N | N | P（`license`） | N | N | N |
| Lens / Dimensions / Scopus / WoS | $ | $ | $ | $ | $ | $ | $ | $ | N | $ | N |

#### 2.3.2 查询能力矩阵

| 源 | 关键词检索 | 结构化过滤 | 排序 | 日期增量 | 深翻/游标 | 批量 ID | 语义/推荐 | 聚合统计 |
|---|---|---|---|---|---|---|---|---|
| Crossref | `query.*`（书目匹配型） | 丰富（日期族/type/prefix/member/has-*） | Y | **`from-index-date`/`from-update-date`** | `cursor` | N（逐条 5–10/s） | N | `facet` |
| OpenAlex | `search`（$0.001） | 极丰富（OR ≤100 值） | Y | `publication_date` 免费；created/updated 需付费 | `cursor` | filter OR 拼接 | 语义搜索 beta（$0.001） | **`group_by`** |
| Semantic Scholar | relevance / bulk / match / snippet | year/venue/fos/type/OA/minCitation | bulk：publicationDate/citationCount | Datasets diffs；bulk 按日期排序 | bulk token | `/paper/batch` ≤500 | **Recommendations（正负样本）** | N |
| OpenCitations | N | N | N | dump 版本 | N | 多 ID 批量 ⚠ | N | 计数端点 |
| Europe PMC | 丰富 Lucene 语法 | 字段（FIRST_PDATE、SRC、OPEN_ACCESS…） | Y | FIRST_PDATE 区间 | `cursorMark` | searchPOST | N | `profile` |
| PubMed | Entrez 语法 | MeSH/日期/类型 | Y | `[edat]`/`[pdat]` + 日更文件 | WebEnv/history ⚠ | efetch 批量 ⚠ | 相似文章（ELink）⚠ | N |
| CORE | ES 式 `field:value` | yearFrom/To 等 | ⚠ | ⚠ | scroll（更耗 token） | ⚠ | `/recommend` | ⚠ |
| DOAJ | Elasticsearch query string | 字段查询 | Y ⚠ | 年份/创建时间 ⚠ | 分页 | N | N | N |
| OpenAIRE | Y | Y | Y ⚠ | ⚠ | 游标 ⚠ | N | N | N |
| INSPIRE | SPIRES/Invenio 语法 | Y | `mostrecent`/`mostcited` | 按 earliest_date 等 ⚠ | 分页 | N | N | facets |
| zbMATH Open | `search_string`（py:/msc: 等） | Y | ⚠ | `py:` | 分页 | N | N | N |
| DataCite | Elasticsearch query | 丰富 | Y | created/updated/registered 日期 | cursor | N | N | facets |

#### 2.3.3 限速与配额归一表（单实例、不带付费档）

| 源 | 无凭证 | 免费注册/身份标识 | 付费/机构档 | 计量头 | 依据 |
|---|---|---|---|---|---|
| Crossref | 单条 5/s、列表 1/s、并发 1 | polite（mailto）：单条 10/s、列表 3/s | Plus 150/s | `x-rate-limit-limit/-interval`、`x-concurrency-limit`、`x-api-pool`（`x-rate-limit-type` 见于公告，2026-09-26 public 池实测未返回）| [S4][S5] |
| OpenAlex | $0.10/天（≈1,000 次列表查询） | 免费 key：$1/天（≈1 万次列表或 1,000 次搜索） | Member $20/天起 | `x-ratelimit-*`（含 USD）、`meta.cost_usd` | [S13][S18][S25] |
| Semantic Scholar | 共享池（实测 429/404） | key：1 RPS | 合作方档 ⚠ | ⚠ | [S27] |
| CORE | 100 token/日、10/分，无全文 | 1,000/日·25/分（个人）；5,000/日·10/分（学术） | 约 200k/日（会员） | `X-RateLimit-*` | [S33] |
| OpenCitations | 180/分钟/IP | token（建议） | — | ⚠ | [S77] |
| OpenAIRE | 60/小时（文档） | 7,200/小时（token） | — | `x-ratelimit-*` | [S74] |
| DOAJ | 2/s（突发 5） | 同左 | 高级档 dump 日更 | ⚠ | [S40][S41] |
| DataCite | 500/5 分钟 | 1,000/5 分钟（带邮箱标识） | 3,000/5 分钟（认证） | ⚠ | [S58] |
| ROR | 2,000/5 分钟 | client ID 方案暂停 | — | ⚠ | [S65][S66] |
| ORCID | 12/s、2.5 万读/日·IP | 12/s、10 万读/日·client | Member 24/s，无配额 | 503（超突发） | [S55] |
| Zenodo | 60/分、2,000/时（检索与 OAI 各 30/分） | 100/分、5,000/时 | — | `X-RateLimit-*` | [S68] |
| PubMed E-utilities | 3/s | key 10/s（核验确认） | 更高速率可申请 | `x-ratelimit-limit` | [S47][S111] |
| Europe PMC | ⚠ 未公布（官方仅称按 IP 计）；`www.ebi.ac.uk` robots 对通用 UA `Crawl-Delay: 10` | — | — | ⚠ | [S117][S118] |
| INSPIRE | 15/5s | — | — | `X-RateLimit-*` | [S92] |
| ADS | — | token：示例 5,000/日 | — | `X-RateLimit-*` | [S93] |
| Wikidata WDQS | 每客户端 60 秒处理时间/分钟，5 并发/IP | — | — | 429 + Retry-After | [S82] |
| Scopus | — | key：Search 2 万/周·9/s 等 | 机构订阅 | `X-RateLimit-*`、`X-ELS-Status` | [S87] |
| WoS Starter | — | 免费试用 50/日·1/s | 5,000–20,000/日·5/s | ⚠ | [S89] |

#### 2.3.4 许可与"多用户平台可用性"

> v2 是多用户平台：同一份元数据会被缓存、跨用户展示，并用于推荐排序。下表按"能否缓存""能否对他人展示"两个维度评估；**全文一律不在用户间共享**，唯一例外是许可证明确允许再分发的 OA 作品（红线见 §3 第 10 条）。

| 源 | 数据许可 | 可缓存（平台级） | 可对其他用户展示元数据 | 展示摘要 | 商业化限制 | 依据 |
|---|---|---|---|---|---|---|
| Crossref | 事实 CC0；摘要版权保留 | Y | Y | ⚠ 灰区（见 §4 Q2） | 无 | [S8] |
| OpenAlex | CC0 | Y | Y | ⚠ 灰区（官方因法律原因只给倒排索引） | 无（按用量付费） | [S19][S23] |
| Semantic Scholar | API 协议 + ODC-BY/Apache-2.0 | Y（遵守数据集许可） | Y（须署名 "Semantic Scholar"） | ODC-BY 数据集可用（须署名） | 不得转售或再分发 API；API 条款未明文允许商用（核验更正），商业化前须书面确认 | [S28][S29] |
| OpenCitations | CC0 | Y | Y | —（无摘要） | 无 | [S79] |
| OpenAIRE | CC-BY | Y | Y（须署名） | 随来源 | 无（须署名） | [S74] |
| DOAJ | CC0 | Y | Y | 随来源 | 无 | [S42] |
| DataCite / ROR / Wikidata / DBLP 快照 | CC0 | Y | Y | — | 无 | [S62][S67][S83][S53] |
| INSPIRE | 大部分 CC0 | Y | Y | ⚠ 部分字段受限 | ⚠ | [S92] |
| HAL（核验补充） | 元数据 CC0；文件按存缴者所选许可 | Y | Y | 随来源 | 无（元数据） | [S115] |
| zbMATH Open（核验补充） | CC BY-SA（"All data"） | Y（须署名） | Y（须署名） | 部分评论因许可冲突不返回 | ShareAlike：衍生数据集可能须以相同许可发布，须法务评估 | [S114] |
| Open policy finder（核验补充） | CC BY-NC-ND 4.0（站点内容） | ⚠ | ⚠（不可改编） | — | NC：商业化须另谈 | [S116] |
| CORE | API T&C；旧 dump ODC-By | Y（依 T&C）⚠ | Y ⚠ | ⚠ | 商用须同意 T&C，可能需许可 | [S34][S35] |
| PubMed/Europe PMC | NLM 条款；摘要可能受版权保护 | Y（声明来源、保持最新） | Y | ⚠ 灰区 | 可再分发，但须声明来源 | [S48][S49] |
| ORCID Public API | 非商业 | 仅限用户本人授权的数据 | 限本人 | — | **禁止用于收费产品** | [S56] |
| Lens | 机构订阅合同 | N（平台层） | N | N | 须定制合同 | [S85] |
| Dimensions | 研究申请/商业合同 | N | N | N | — | [S86] |
| Scopus / WoS | 订阅 + 使用政策 | N（平台层） | N | N（Scopus 政策在 IR/CRIS 用例中明示不得公开展示摘要） | — | [S88][S89] |
| BASE | 未授权 | N | N | N | — | [S38] |

### 2.4 查询路由能力矩阵（初步）

> 目的：为 v2 "多来源查询 + 路由器"给出**每类查询首选/备选/兜底源**的初版能力表。原则：①本地索引优先（最好的限速是不请求）；②谓词下推到过滤能力最强、成本最低的源，其余谓词本地后过滤；③CC0/开放许可源优先于限制性许可源；④任何源失败或配额耗尽都有降级链。成本单位：Crossref 按"请求类 × 池"限速计；OpenAlex 按美元计；S2 按 1 RPS 计。

| # | 查询类 | 首选 | 备选 | 兜底 / 学科特化 | 关键约束（来源） |
|---|---|---|---|---|---|
| R1 | **DOI 精确解析**（单篇详情卡片） | 本地库 → Crossref `/works/{doi}`（单条池，polite 10/s） | OpenAlex 单实体 `/works/doi:…`（**免费**） | DataCite DOI 走 DataCite `/dois/{doi}`；Unpaywall 仅取 OA 位置 | Unpaywall 只覆盖 Crossref DOI [S24]；OpenAlex 单实体 0 成本 [S13][LIVE] |
| R2 | **期刊"最新论文"**（按 venue 订阅） | Crossref `/journals/{issn}/works?filter=from-index-date:…`（[LIVE] 归 single 池，public 5/s；**不要用** `/works?filter=issn:`，它归 array 池 1/s） | OpenAlex `primary_location.source.id:S… + from_publication_date`（$0.0001/次） | 生医：Europe PMC `ISSN:` + `FIRST_PDATE`；日本：J-STAGE `issn=`；数学：zbMATH `py:`/刊名 | 刊级元数据可能张冠李戴（§2.2.1 实测 Nature Methods 的 ISSN 挂在 Nature Chemical Biology 刊记录下，但按 ISSN 枚举的作品正确）；OpenAlex created/updated 增量需付费 [LIVE] |
| R3 | **会议"最新论文"** | L1 会议平台适配器（OpenReview/PMLR/CVF/ACL Anthology/NeurIPS 等，v1 已有） | 有 DOI 的会议走 Crossref 前缀/ISBN 枚举（ACM 10.1145、IEEE 10.1109、AAAI 10.1609、IJCAI 10.24963、ACL 10.18653，见 §2.6.11） | DBLP DROPS 月度快照做全量对账；SPARQL（Crawl-delay 10）按需补查 | DBLP 主站已全面禁止 [S51]；OpenAlex 会议实体碎片化（NeurIPS 4,177 条、ICLR 757 条）[LIVE] |
| R4 | **预印本最新**（按分类/社区） | arXiv（L1，v1 已有）；Crossref `type:posted-content` + 前缀（OSF 系 23 个前缀、SSRN 10.2139 等） | Europe PMC `SRC:PPR`（生医预印本 124.7 万条） | OpenAlex `type:preprint`（2025 年 CS 11.9 万、物理 6.8 万、数学 3.2 万，见 §2.4.1） | OSF API 被 robots 禁止，需经 Crossref 旁路 [S70][S71] |
| R5 | **主题"最新论文"**（跨 venue、按兴趣） | OpenAlex `topics.id` / `primary_topic.subfield.id` + `from_publication_date`（$0.0001/次，可 `group_by` 统计） | S2 `/paper/search/bulk` 按 `publicationDate` 排序 + `fieldsOfStudy`（需 key，1 RPS） | 生医 MeSH（Europe PMC/PubMed）；HEP（INSPIRE `sort=mostrecent`）；数学 MSC（zbMATH）；经济 JEL（RePEc 快照 join） | OpenAlex Topics 为机器分类，需以用户反馈校正 |
| R6 | **关键词检索**（用户即时查询） | 本地 FTS + 向量混合索引（v1 已有 FTS5） | OpenAlex `search`（$0.001/次）；S2 relevance（key） | Crossref `query.bibliographic` 只用于引文串匹配；CORE 全文检索（key）；Europe PMC（生医） | OpenAlex 搜索单价是列表查询的 10 倍 [S13] |
| R7 | **语义检索 / 相似论文** | 本地向量索引（SPECTER2：S2 嵌入数据集 Apache-2.0，或自算） | S2 Recommendations（正/负样本，≤500 条）[S30] | OpenAlex 语义搜索 beta（$0.001，官方不建议用于敏感生产）[S15]；OpenAlex `related_works` | S2 需 key，1 RPS [S27] |
| R8 | **组合查询**（venue × topic × 日期 × OA × 被引阈值 × 类型） | OpenAlex `filter`（下推能力最强：AND/OR/NOT/比较，单 filter ≤100 个 OR 值） | S2 bulk（year/venue/fos/type/minCitationCount/openAccessPdf） | Crossref（venue/date/type/has-* 可下推，主题需本地过滤） | 路由器按"谓词覆盖度 × 成本 × 许可"打分选源，未下推的谓词本地过滤 |
| R9 | **作者/机构维度** | OpenAlex authors/institutions（消歧 + ROR） | 用户 ORCID OAuth 自授权记录 [S56] | CS：DBLP PID（快照）；HEP：INSPIRE；数学：zbMATH；机构：ROR dump | ORCID Public API 仅限非商业 [S56] |
| R10 | **引文扩展**（参考文献/被引/共被引） | OpenCitations（CC0）+ OpenAlex `referenced_works`/`cites:` | S2 citations（带 intent/context，key） | INSPIRE（HEP 策展引用）；Europe PMC citations | 同一篇论文各源被引数不一致（OC 9,262 与 OpenAlex 10,801）[LIVE] |
| R11 | **OA 全文定位/取回** | OpenAlex `best_oa_location`/`locations`（与 Unpaywall 同源） | CORE `/download`（key）；Europe PMC `fullTextXML`；PMC Cloud | HAL/Zenodo 仓储；**用户自有授权**的出版方通道（L1 auth-gated，只供本人） | 全文保留原版权，只可再分发许可允许的 [S17][S49] |
| R12 | **撤稿/更正过滤** | Crossref `update-type:retraction` / `update-to`（含 Retraction Watch） | OpenAlex `is_retracted` | — | [S10][LIVE] |
| R13 | **资助/项目** | OpenAlex `funders`/`awards` | Crossref funder/award | OpenAIRE 项目（欧洲）；Europe PMC grants（生医） | — |
| R14 | **数据集/软件关联** | DataCite relatedIdentifiers | Crossref 数据引用端点（2026 新增）[S7] | OpenAIRE ScholeXplorer；Zenodo OAI | DataCite GraphQL 将于 2027-07 弃用 [S59] |
| R15 | **venue 元信息**（APC、OA 政策、DOAJ、出版方） | OpenAlex sources（`is_oa`、`is_in_doaj`、`apc_usd`、`oa_works_count`） | DOAJ 期刊 API/CSV（CC0） | Crossref `/journals/{issn}`（各类覆盖率） | 见 §2.6 实测 |
| R16 | **中文/区域** | 用户手动导入 CNKI/万方/维普题录（RIS/EndNote） | OpenAlex/Crossref 中覆盖的中文 DOI 刊 | J-STAGE WebAPI（日）、SciELO ArticleMeta（拉美） | CNKI robots 全站禁止 [S97] |
| R17 | **热度/社交信号** | 平台内交互（赞/藏/评/停留） | OpenAlex `counts_by_year`、OpenCitations 被引增量 | — | Crossref Event Data 已停用 [S7] |

#### 2.4.1 学科 × 通道默认路由（OpenAlex 2025 年文章实测画像）

> [LIVE] OpenAlex `publication_year:2025`，按 `primary_topic.field` 分组（5 次 group_by 查询，每次 $0.0001）[S25]。OA% 取 `is_oa:true`（含 gold/green/hybrid/bronze）；"预印本"取 `type:preprint` 计数。**注意**：field 为 OpenAlex 机器分类，且计数包含全部期刊（含低质量刊），只用于比较各学科的相对结构，不代表顶刊情况。

| 学科（OpenAlex field） | 2025 文章数 | 有摘要% | OA% | 有 DOI% | 2025 预印本数 | 默认"最新论文"通道 | 学科特化分类/源 |
|---|---|---|---|---|---|---|---|
| Mathematics | 82,378 | 75.8 | 66.0 | 97.3 | 32,319 | arXiv math.* + Crossref ISSN | zbMATH MSC2020 |
| Physics and Astronomy | 146,091 | 81.5 | 66.7 | 96.7 | 68,197 | arXiv + Crossref（APS/IOP/AIP 等） | INSPIRE（HEP）、ADS（天文） |
| Chemistry | 86,214 | 75.2 | 49.6 | 98.1 | 10,212 | Crossref ISSN（ACS/RSC/Wiley） | ChemRxiv（L1）；OA 率低，全文依赖用户授权 |
| Materials Science | 201,590 | 65.6 | 45.8 | 98.4 | 25,455 | Crossref ISSN | — |
| Biochemistry, Genetics & Mol. Biology | 309,111 | 78.0 | 71.2 | 97.8 | 43,981 | Europe PMC / PubMed 日更 + Crossref | MeSH；bioRxiv（经 Europe PMC `SRC:PPR`） |
| Agricultural & Biological Sciences | 348,737 | 85.0 | 77.8 | 96.2 | 23,804 | Crossref + Europe PMC | MeSH（部分） |
| Neuroscience | 93,046 | 79.7 | 72.7 | 97.0 | 23,861 | Europe PMC + Crossref | MeSH |
| Psychology | 237,318 | 84.1 | 74.1 | 92.4 | 32,356 | Crossref ISSN（APA/SAGE/Elsevier）+ PsyArXiv（Crossref 前缀 10.31234） | APA PsycInfo 为订阅库（排除） |
| Economics, Econometrics & Finance | 171,507 | 75.6 | 73.1 | 92.4 | 28,309 | Crossref ISSN + NBER/SSRN/arXiv econ（L1） | JEL（RePEc 快照、EconBiz） |
| Business, Management & Accounting | 252,562 | 87.9 | 76.1 | 94.7 | 24,068 | Crossref ISSN（INFORMS/AOM/SAGE/Wiley） | — |
| Decision Sciences | 67,635 | 79.8 | 73.2 | 94.6 | 14,970 | Crossref ISSN（INFORMS/Elsevier） | — |
| Computer Science | 401,895 | 83.1 | 71.2 | 95.7 | 119,499 | 会议 L1 平台 + arXiv cs.* + Crossref（ACM/IEEE） | DBLP 快照（PID/卷目录）、S2 嵌入 |
| Social Sciences（参照） | 1,078,487 | 85.3 | 78.0 | 90.1 | 64,690 | Crossref + SocArXiv（10.31235） | — |
| Medicine（参照） | 1,320,135 | 76.1 | 71.6 | 97.5 | 81,418 | PubMed/Europe PMC | MeSH |

#### 2.4.2 路由器需要的源能力描述（设计输入，伪结构）

> 下为**设计伪代码**（非可运行），用于把本调研的事实沉淀为可机读的 `SourceCapability`，供路由器打分；字段值以 §2.2 为准。

```yaml
# 设计伪代码：SourceCapability（示例：crossref）
source_id: crossref
layer: L2-aggregator
id_schemes: [doi, issn, isbn, orcid, ror, funder_doi]
predicates:            # 可下推到源端的过滤谓词
  venue_issn: native
  pub_date_range: native
  index_date_since: native      # 增量游标
  type: native
  has_abstract: native
  topic: none                   # 需本地过滤
  oa_status: none
sort_keys: [published, indexed, updated, is-referenced-by-count]
cursor: deep_cursor
rate_limits:                    # 按请求类分桶，读 x-api-pool / x-rate-limit-* 动态调整
  single: {pool_polite: 10/s, concurrency: 3}   # /works/{doi}、/journals/{issn}/works（LIVE 归类）
  array:  {pool_polite: 3/s,  concurrency: 3}   # /works?filter=…、/works?query.*
cost_model: {usd_per_call: 0}
license: {metadata: CC0_facts, abstract: publisher_copyright}
quirks: [issn_collision_possible]   # 见 §2.6 Nature Methods 实测
robots_policy: api_host_no_robots   # 404
freshness: near_real_time
```

### 2.5 来源名录（L2 部分，统一列，供设计阶段合并为总名录）

> `source_id` 沿用 v1 已有 id（`crossref`/`openalex`/`s2`/`unpaywall`/`core`/`dblp`/`repec`），新源用 snake_case。"限速与 ToS/robots"一列的核验日期除注明外均为 2026-09-26。"v1 是否已支持"：✓ = v1 代码已实现；✗ = 无。

| source_id | 名称 | 层级类型 | 学科 | 平台技术栈 | 元数据通道 | 最新论文通道 | 全文通道与门控 | 认证方式 | 限速与 ToS/robots 要点（来源+日期） | v1 是否已支持 | 建议优先级及理由 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `crossref` | Crossref | L2-aggregator（DOI 注册机构） | 全学科 | 自研 REST（响应头 Jetty 9.4）[LIVE] | 官方 API；年度公共数据文件 | `/journals/{issn}/works` + `from-index-date`；posted-content 按前缀 | 无（只有 TDM/出版方链接） | 无 / `mailto`（polite）/ Plus token | single 5/s、array 1/s（public，并发 1），polite 10/3；API 主机无 robots（404）[S4][S5] | ✓（ENUMERATE） | **P0**：期刊枚举、增量、DOI 权威、撤稿 |
| `openalex` | OpenAlex | L2-aggregator | 全学科 | 自研 API（代码开源，ourresearch/openalex-elastic-api）[S110] | 官方 API；S3 季度快照（CC0） | `from_publication_date` 过滤（免费）；日同步需付费 | OA 作品 PDF/TEI（content 端点，$0.01/次，保留原版权） | API key（免费 $1/天） | 按次计费、100 req/s；`content.openalex.org` robots `Allow: /`[S13][S18] | ✓（enrich） | **P0**：覆盖面主干 + Topics 主题图谱 |
| `s2` | Semantic Scholar | L2-aggregator | 全学科（CS、生医强） | 自研 API（AWS API Gateway，响应头可见）[LIVE] | 官方 API；Datasets 周更 | bulk search 按 publicationDate；Datasets diffs | s2orc_v2 全文数据集（ODC-BY，只含 OA） | API key（申请制） | key 1 RPS；匿名实测 404/429；须署名、不得再分发 API [S27][S28] | ✓（enrich） | **P1**：嵌入与推荐专用（拿到 key 后升 P0） |
| `unpaywall` | Unpaywall | L2-aggregator（OA 叠加层） | 全学科（仅 Crossref DOI） | 运行在 OpenAlex 数据库上 [S24] | DOI 单查 API；Data Feed（订阅） | —（不是发现源） | OA 位置（指向仓储/出版方） | `email` 参数 | 100k/日 [v1]；缺 email 返回 422 [LIVE] | ✓（RESOLVE） | **P1**：兼容层，新功能改用 OpenAlex |
| `core` | CORE | L2-repository（仓储聚合） | 全学科（OA） | 自研 API v3 | 官方 API；Dataset（新版需许可） | ⚠ 按日期增量能力未核 | **全文**（需注册；未认证不给全文） | API key（注册） | 未认证 100 token/日；个人 1,000/日；学术 5,000/日；`core.ac.uk` 禁 `/search` [S33][S37] | ✗（设计存档） | **P1**：OA 全文兜底 |
| `base` | BASE | L2-aggregator（OAI 仓储索引） | 全学科 | ⚠（文档被 Anubis 拦截） | API（IP 白名单）⚠ | — | 链接 | IP 白名单 + 申请 | 网站 robots 附法律声明、禁止未授权自动获取；API 主机 `Disallow: /` [S38] | ✗ | **排除**（未取得授权前） |
| `doaj` | DOAJ | L2-aggregator（OA 期刊目录） | 全学科（OA 刊） | 自研（页脚署名 Cottage Labs）[LIVE] | API v4；OAI-PMH；期刊 CSV；dump（申请） | OAI-PMH / 按年份检索 | 链接（全部为 OA） | 读取无需认证 | 2 req/s（突发 5）；robots 只禁 `/search` 等 [S40][S41] | ✗ | **P1**：OA 期刊白名单与质量信号 |
| `openaire` | OpenAIRE Graph | L2-aggregator | 全学科（欧洲强） | ⚠ | Graph API v1；Zenodo dump（CC-BY） | ⚠ | 链接 | token（可选） | 文档：匿名 60/h、认证 7,200/h；[LIVE] 匿名头 7199 [S74][S76] | ✗ | **P2**：资助/项目维度 |
| `opencitations` | OpenCitations | L2-aggregator（引文） | 全学科 | RAMOSE 生成的 REST [S77] | REST v2；SPARQL；dump（CC0） | dump 版本 | 无 | token（建议） | 180/分钟/IP；API 主机无 robots（404）[S77][S79] | ✗ | **P1**：CC0 引文图 |
| `europe_pmc` | Europe PMC | L2-aggregator + L2-repository | 生医/生命科学（心理部分） | 自研 REST v6.9 | 官方 API；FTP | `FIRST_PDATE` 区间 + `cursorMark` | OA 子集全文 XML（按单篇许可） | 无 | 限速数值未公布 ⚠（官方称按 IP 计）；`www.ebi.ac.uk` robots 对通用 UA `Crawl-Delay: 10`（REST 路径未被禁止）；bulk 主机 `ftp.ebi.ac.uk` robots 全禁（核验补充）；网站有 Cloudflare 挑战，REST 可达 [S44][S45][S117][S118][S123] | ✗ | **P0（生医/心理）** |
| `pubmed` | PubMed（NCBI） | L2-aggregator | 生物医学 | E-utilities | 年度 baseline + 日更文件；E-utilities | updatefiles 日更 | 无（链接到 PMC/出版方） | 无 / API key | 无 key 3/s [LIVE]，key 10/s [S111]；eutils 主机与 `ftp.ncbi.nlm.nih.gov`（bulk）的 robots 都是 `Disallow: /`（后者为核验补充）；NLM 条款 [S47][S48][S113] | ✗ | **P0（生医/心理）**：以 bulk 为主，须等 Q1 的 ADR |
| `pmc` | PMC Cloud Service | L2-repository | 生物医学 | AWS（HTTPS/S3，免登录）[S49] | 云服务（旧 FTP 已于 2026-08 下线） | ⚠ | OA 子集/作者手稿全文（按许可） | 无 | 只可再分发许可允许的内容 [S49] | ✗ | **P1**：生医 OA 全文 |
| `dblp` | dblp | L2-aggregator（人工策展） | CS | 自研 | ⚡ 只剩 DROPS 月度 XML + `sparql.dblp.org` | 月度快照 | 无（ee 外链） | 无 | ⚡ 主站 robots 全禁；SPARQL `Crawl-delay: 10` [S51][S52][S53] | ✓（代码保留，已出列 D-037） | **P1（离线）**：CS 会议卷目录与作者 PID |
| `orcid` | ORCID | 注册表 | 全学科 | 自研 | Public API（OAuth）；年度数据文件 | — | 无 | OAuth（用户授权）/ client credentials | 匿名 2.5 万读/日·IP，注册 10 万/日；**仅限非商业**；`pub.orcid.org` robots `Disallow: /` [S55][S56][S57] | ✗ | **P1**：用户身份与兴趣冷启动 |
| `datacite` | DataCite | L2-aggregator（DOI 注册机构） | 全学科（数据/软件） | 自研 REST（GraphQL 将于 2027-07 弃用） | REST；年度公共数据文件（CC0） | 按 created/updated 日期 ⚠ | 无（链接到仓储） | 无 / mailto / 认证 | 500 → 1,000 → 3,000 次/5 分钟 [S58][S59] | ✗ | **P2**：数据/软件关联 |
| `ror` | ROR | 注册表 | 全学科 | 自研（可 Docker 自托管）[S65] | REST v2；Zenodo dump（CC0） | dump 发布 | — | 无（client ID 方案暂停） | 2,000/5 分钟 [S65][S66] | ✗ | **P1**：机构归一 |
| `zenodo` | Zenodo | L2-repository | 全学科 | InvenioRDM ⚠ | OAI-PMH（`/oai2d`）；REST（robots 禁 `/api`） | OAI-PMH 增量（resumptionToken 2 分钟内有效） | 文件（按单条记录许可） | 无 / token | 访客 60/分，OAI 30/分；robots `Crawl-delay: 10` [S68][S69] | ✗ | **P2**：按社区/学科 OAI 收割 |
| `osf` | OSF Preprints（32 个社区） | L2-repository（预印本基础设施） | 心理/社科/教育等 | 自研 | ⚡ 委托 Crossref（COS 名下 23 个前缀） | Crossref `prefix + type:posted-content + from-index-date` | OA 预印本 PDF（按许可）⚠ | 无 | `api.osf.io` robots `Disallow: /`；`share.osf.io` 禁 `/api`、`/oai-pmh` [S70][S71] | ✗ | **P1**（经 Crossref） |
| `hal` | HAL | L2-repository | 全学科（法国/欧洲） | 自研（CCSD） | API v3（search/OAI-PMH），与 robots 冲突 | OAI-PMH / API 日期过滤 ⚠ | OA 全文（180 万条带文件） | 无 | API 主机 robots 禁 `/search/`、`/oai/`；`hal.science` robots 注释鼓励用 API；元数据 CC0 [S72][S73][S115] | ✗ | **P2**（待 Q1 的 ADR） |
| `wikidata` | Wikidata / WikiCite | L2-aggregator（知识图谱） | 全学科 | Blazegraph WDQS（已拆为两个图）[S82] | SPARQL；dump | — | 无 | 无 | 每客户端每分钟 60 秒处理时间，5 并发/IP [S81][S82] | ✗ | **P2**：跨库 ID 映射 |
| `fatcat_ia_scholar` | Fatcat / IA Scholar | L2-aggregator（保存副本） | 全学科 | 自研 | ⚠（fatcat 不可达；Scholar 检索有 ALTCHA 挑战） | — | IA 保存副本（链接） | — | robots 禁 `/search`、`/verify` [S80] | ✗ | **仅元数据/观察** |
| `lens` | Lens.org | L2-aggregator（机构订阅） | 全学科 + 专利 | 自研 API 2.19.3 | token API | ⚠ | 无 | token（机构订阅） | 月度额度；须展示 Lens logo；条款 v2026.06.01 [S84][S85] | ✗ | **仅元数据**（用户自带 token） |
| `dimensions` | Dimensions | L2-aggregator（商业） | 全学科 | 商业平台 | API/BigQuery（申请或合同） | — | 无 | 合同 | 只对非商业科学计量研究免费（需申请）[S86] | ✗ | **排除**（平台层） |
| `scopus` | Scopus | L2-aggregator（商业 A&I） | 全学科 | Elsevier API | API key + 机构订阅 | ⚠ | 无 | API key + 机构凭证 | 按周配额；按用例授权，不得公开展示摘要等 [S87][S88] | ✗ | **排除**（平台层）；可由用户自带 key 私用 |
| `web_of_science` | Web of Science | L2-aggregator（商业 A&I） | 全学科 | Clarivate API | Starter/Expanded API | ⚠ | 无 | API key + 订阅 | 免费档 50 次/日；机构档 5,000–20,000 次/日 [S89] | ✗ | **排除**（平台层）；可由用户自带 key 私用 |
| `google_scholar` | Google Scholar | L2-aggregator | 全学科 | — | 无 API | — | — | — | robots 禁 `/scholar`、`/search` [S90] | ✗（明确排除） | **排除** |
| `microsoft_academic` | Microsoft Academic | L2-aggregator（历史） | 全学科 | — | 2021-12-31 已关停 | — | — | — | [S91] | ✗ | **排除**（历史；兼容 `mag` ID） |
| `inspire_hep` | INSPIRE-HEP | L2-aggregator（学科） | 高能物理 | Invenio ⚠ | REST API | `sort=mostrecent` | 链接（arXiv 等） | 无 | 15 次/5 秒/IP；大部分 CC0 [S92] | ✗ | **P1（物理）** |
| `nasa_ads` | NASA ADS | L2-aggregator（学科） | 天文/天体物理 | 自研 API | token API | ⚠ | 链接 | token（ADS 账户） | 示例额度 5,000 次/日 [S93] | ✗ | **P2（天文）** |
| `zbmath_open` | zbMATH Open | L2-aggregator（学科） | 数学 | 自研 API | REST API（OAI ⚠） | `py:` 年份过滤 | 无（链接） | 无 | 主站有 Cloudflare 挑战；`static` 条款页 403，API 主机副本可读：数据 CC BY-SA、要求合理控速（核验补充）[S94][S114] | ✗ | **P1（数学）**：须署名并评估 ShareAlike |
| `mathscinet` | MathSciNet | L2-aggregator（订阅 A&I） | 数学 | AMS | 订阅 | — | — | 机构订阅 | robots 只放行少数路径，`Crawl-delay: 10` [S95] | ✗ | **排除自动化** |
| `econbiz` | EconBiz（ZBW） | L2-aggregator（学科） | 经济/商管 | 自研 API | REST API | ⚠ | 链接 | 无 | 未检出许可 ⚠ [S96] | ✗ | **P2** |
| `repec` | RePEc | L2-aggregator（学科，分布式） | 经济 | ReDIF bulk / OAI [v1] | bulk ReDIF（零 HTML） | OAI（2021-09 起）[v1] | 链接 | 无 | 见 [v1 repec.md] | ✓（enrich） | **P1**（维持） |
| `econstor` | EconStor | L2-repository | 经济 | DSpace ⚠ | OAI-PMH ⚠；sitemap | ⚠ | OA 全文 | 无 | robots 禁检索与浏览页 [LIVE] | ✗ | **仅元数据**（经 CORE/OpenAlex） |
| `ssoar` | SSOAR | L2-repository | 社会科学 | ⚠ | ⚠ | ⚠ | OA 全文 | — | 本次连接失败 ⚠ | ✗ | **仅元数据** |
| `cnki` | 中国知网 | L2-aggregator（商业） | 全学科（中文） | 自研 | 未发现开放 API ⚠ | — | 订阅 | 机构 IP/账号 | `kns.cnki.net` robots `Disallow: /` [S97] | ✗ | **排除自动化**（用户导入题录） |
| `wanfang` | 万方数据 | L2-aggregator（商业） | 全学科（中文） | 自研 | 未发现开放 API ⚠ | — | 订阅 | 机构 | 检索子域 WAF 拦截 [S98] | ✗ | **排除自动化**（用户导入题录） |
| `cqvip` | 维普 | L2-aggregator（商业） | 全学科（中文） | 自研 | 未发现开放 API ⚠ | — | 订阅 | 机构 | robots 部分禁止 [S99] | ✗ | **排除自动化**（用户导入题录） |
| `chinaxiv` | ChinaXiv | L1-preprint | 自然科学（中文/英文） | 自研 | ⚠ | ⚠ | OA 预印本 | 无 | robots.txt 返回 403 维护页 [S100] | ✗ | **仅元数据/观察** |
| `paper_edu_cn` | 中国科技论文在线 | L2-repository | 全学科（中文） | 自研 | ⚠（维护停服） | — | OA | — | 全站维护，暂停服务 [S101] | ✗ | **暂缓** |
| `jstage` | J-STAGE | L1-journal-platform（兼聚合） | 全学科（日本） | JST 自研 | WebAPI（Atom XML） | 按 issn/年份检索 | OA 为主，各刊不同 ⚠ | 无（商业用途需申请） | 不允许大批量下载；robots 禁 `/*_pdf` [S102][S103] | ✗ | **P2** |
| `scielo` | SciELO | L2-aggregator（OA 期刊网络） | 全学科（拉美/伊比利亚） | ArticleMeta API | API；OAI ⚠ | 按合集/处理日期 | OA | 无 | `www` robots `Crawl-delay: 10`；检索站有 Bunny Shield 挑战 [S104] | ✗ | **P2** |
| `redalyc` | Redalyc | L2-aggregator（OA） | 全学科（拉美） | ⚠ | OAI-PMH ⚠ | ⚠ | OA | — | robots.txt 返回 403 [S105] | ✗ | **仅元数据** |
| `open_policy_finder` | Jisc Open policy finder（原 Sherpa，核验补充） | 政策注册表 | 全学科 | Jisc 自研 ⚠ | 新 API（2026-02 发布；旧 Sherpa API 迁移期到 2026-07） | — | 无（只提供政策信息） | ⚠（注册方式未核验） | 内容 CC BY-NC-ND 4.0；`v2.sherpa.ac.uk` WAF 403 [S116] | ✗ | **P2**：全文共享合规判定的辅助信号 |
| `cinii_research` | CiNii Research（NII，核验补充） | L2-aggregator（区域） | 全学科（日本） | NII 自研 | OpenSearch API（需 `appid`）；ResourceSync | ⚠ | 链接 | `appid` | robots 只放行 `/`、`/crid/`、`/sitemaps/`、`/resourcesync/`，`Crawl-Delay: 1`，`/opensearch` 被禁 [S119] | ✗ | **P2（日本）**：先评估 ResourceSync，API 待 Q1 的 ADR |

**优先级小结**：P0 = `crossref`、`openalex`、`europe_pmc`、`pubmed`（后两者限生医/心理路由）；P1 = `s2`、`unpaywall`、`core`、`doaj`、`opencitations`、`pmc`、`dblp`（离线）、`orcid`、`ror`、`osf`（经 Crossref）、`inspire_hep`、`zbmath_open`、`repec`；P2 = `openaire`、`datacite`、`zenodo`、`hal`、`wikidata`、`nasa_ads`、`econbiz`、`jstage`、`scielo`，以及核验补充的 `open_policy_finder`、`cinii_research`；其余为仅元数据/暂缓/排除。

### 2.6 代表性期刊/会议 → 平台映射（聚合源视角，实测）

> **方法**：[LIVE] 2026-09-26 对下列 204 本期刊逐一请求 Crossref `/journals/{issn}` 与 OpenAlex `/sources/issn:{issn}`（19 条 Crossref 429 退避重试后补齐），原始结果随本文附在 [aggregators-repositories/venue-verification-2026-09-26.jsonl](aggregators-repositories/venue-verification-2026-09-26.jsonl)。表中 ISSN 取 Crossref 返回的 `issn-type`（print / electronic），不采用手填值。
> **字段口径**：
> - "Crossref 可枚举"指 `/journals/{issn}/works` 可按 ISSN 与日期枚举全部 DOI；DOI 总数与年份跨度取 `counts.total-dois` 与 `breakdowns.dois-by-issued-year` 的首末年。
> - "摘要/参考文献/ORCID 覆盖"取 Crossref `coverage.*-current`（Crossref 定义的近期内容区间），反映**该刊通过 Crossref 能拿到多少摘要**，决定摘要要不要走补齐链。
> - "OA 情况"取 OpenAlex source 的 `is_oa`（全刊 OA）、`is_in_doaj`、`oa_flip_year`，以及 `oa_works_count / works_count`。后者**包含绿色 OA（如 arXiv 副本）**，所以订阅刊也可能很高（如 Annals of Statistics 90%）。
> - "Crossref 出版方"与"OpenAlex 宿主"各自照录，两者不一致是真实数据现象（例如刊物易主、社团与出版商并列），出版平台的技术栈（Atypon/Silverchair 等）由 L1 平台调研主题负责，本表不重复。
>
> **学科汇总**（中位数，Crossref current 覆盖）：
>
> | 学科 | 样本刊数 | 摘要覆盖中位数 | 摘要 <5% 的刊数 | 参考文献覆盖中位数 | ORCID 覆盖中位数 | 全刊 OA 刊数 |
> |---|---|---|---|---|---|---|
> | 数学 | 22 | 55% | 3 | 94% | 12% | 3 |
> | 物理/天文 | 22 | 54% | 4 | 96% | 94% | 11 |
> | 化学/材料 | 21 | 11% | 1 | 94% | 88% | 2 |
> | 生物/综合 | 24 | 51% | 5 | 94% | 79% | 11 |
> | 心理学 | 21 | **0%** | **13** | 86% | 61% | 2 |
> | 经济学 | 25 | 85% | 8 | 91% | 0% | 3 |
> | 金融学 | 18 | 76% | 7 | 93% | 47% | 0 |
> | 商学 | 17 | 78% | 3 | 89% | 76% | 0 |
> | 管理学 | 19 | 64% | 7 | 91% | 81% | 0 |
> | CS/AI 期刊 | 15 | 32% | 5 | 94% | 85% | 3 |
>
> **按出版方的 Crossref 摘要覆盖**（同一样本内求均值）：Elsevier 0%（34 刊）、APA 0%（8 刊）、AOM 0%（3 刊）、IEEE 0%（3 刊）、UChicago Press 0%（2 刊）、Taylor & Francis 0%（2 刊）、ACS 9%（11 刊）、Springer Nature 28–50%、APS 39%；OUP 94%、INFORMS 94%、ACM 93%、SIAM 92%、AEA 91%、SAGE 89%、RSC 86%、Wiley 75–79%、IOP/AIP 98–99%。另外，APA 8 本刊在 Crossref 的**参考文献覆盖也全部为 0%**，心理学的引文图要靠 OpenAlex/S2/OpenCitations 补齐。**结论**：v2 的"摘要补齐链"必须按出版方路由——Elsevier、APA、IEEE、ACS、T&F、AOM 的摘要要走 OpenAlex 倒排、PubMed/Europe PMC 或学科源，并记录摘要的来源与版权属性。

#### 2.6.1 数学（含统计/概率）

| 名称 | ISSN（print / e） | Crossref 出版方 | OpenAlex 宿主 | Crossref 可枚举（DOI 总数；年份跨度） | 摘要/参考文献/ORCID 覆盖（Crossref current） | OA 情况（OpenAlex） |
|---|---|---|---|---|---|---|
| Annals of Mathematics | 0003-486X / 1939-8980 | Annals of Mathematics | Princeton University | ✓ 6,301；1884–2026 | 11% / 0% / 11% | 订阅/混合；OA 作品占比 16% |
| Acta Mathematica | 0001-5962 / 1871-2509 | International Press of Boston, Inc. | Mittag-Leffler Institute | ✓ 2,279；1882–2026 | 0% / 0% / 0% | 全刊 OA、OA 转型 2001；OA 作品占比 84% |
| Inventiones Mathematicae | 0020-9910 / 1432-1297 | Springer-Verlag | Springer Science+Business Media | ✓ 4,878；1966–2026 | 50% / 100% / 2% | 订阅/混合；OA 作品占比 29% |
| Journal of the American Mathematical Society | 0894-0347 / 1088-6834 | American Mathematical Society | American Mathematical Society | ✓ 1,383；1988–2027 | 70% / 70% / 2% | 订阅/混合；OA 作品占比 74% |
| Publications Mathematiques de l'IHES | 0073-8301 / 1618-1913 | MathDoc/Centre Mersenne | Springer Nature | ✓ 604；1959–2026 | 96% / 100% / 12% | 订阅/混合；OA 作品占比 46% |
| Duke Mathematical Journal | 0012-7094 / 1547-7398 | Duke University Press | Duke University Press | ✓ 6,818；1935–2026 | 9% / 100% / 0% | 订阅/混合；OA 作品占比 18% |
| Communications on Pure and Applied Mathematics | 0010-3640 / 1097-0312 | Wiley (John Wiley & Sons) | Wiley | ✓ 4,310；1948–2026 | 61% / 61% / 2% | 订阅/混合；OA 作品占比 21% |
| Journal of the European Mathematical Society | 1435-9855 / 1435-9863 | EMS Press | European Mathematical Society | ✓ 1,871；1999–2026 | 100% / 0% / 92% | 全刊 OA、DOAJ、OA 转型 2020；OA 作品占比 92% |
| Advances in Mathematics | 0001-8708 / 1090-2082 | Elsevier | Elsevier BV | ✓ 11,365；1961–2026 | 0% / 94% / 0% | 订阅/混合；OA 作品占比 86% |
| Compositio Mathematica | 0010-437X / 1570-5846 | Cambridge University Press | Cambridge University Press | ✓ 2,538；1997–2026 | 76% / 72% / 54% | 订阅/混合；OA 作品占比 91% |
| Geometric and Functional Analysis | 1016-443X / 1420-8970 | Springer-Verlag | Birkhäuser | ✓ 1,440；1991–2026 | 51% / 100% / 0% | 订阅/混合；OA 作品占比 33% |
| Forum of Mathematics, Pi | — / 2050-5086 | Cambridge University Press | Cambridge University Press | ✓ 195；2013–2026 | 99% / 97% / 69% | 全刊 OA、DOAJ、OA 转型 2012；OA 作品占比 100% |
| Mathematische Annalen | 0025-5831 / 1432-1807 | Springer-Verlag | Springer Nature | ✓ 14,276；1869–2026 | 40% / 98% / 79% | 订阅/混合；OA 作品占比 26% |
| American Journal of Mathematics | 0002-9327 / 1080-6377 | Project MUSE | Johns Hopkins University Press | ✓ 6,498；1878–2026 | 98% / 0% / 0% | 订阅/混合；OA 作品占比 10% |
| Annals of Statistics | 0090-5364 / 2168-8966 | Institute of Mathematical Statistics | Institute of Mathematical Statistics | ✓ 6,384；1973–2026 | 14% / 100% / 6% | 订阅/混合；OA 作品占比 90% |
| Journal of the American Statistical Association | 0162-1459 / 1537-274X | Informa UK (American Statistical Association) | — | ✓ 25,324；1922–2026 | 0% / 96% / 65% | 订阅/混合；OA 作品占比 9% |
| Journal of the Royal Statistical Society Series B | 1369-7412 / 1467-9868 | Oxford University Press | Oxford University Press | ✓ 4,201；1934–2026 | 60% / 84% / 73% | 订阅/混合；OA 作品占比 25% |
| Biometrika | 0006-3444 / 1464-3510 | Oxford University Press | Oxford University Press | ✓ 13,125；1901–2026 | 95% / 93% / 65% | 订阅/混合；OA 作品占比 9% |
| Annals of Probability | 0091-1798 / 2168-894X | Institute of Mathematical Statistics | Institute of Mathematical Statistics | ✓ 4,855；1973–2026 | 13% / 100% / 5% | 订阅/混合；OA 作品占比 92% |
| Probability Theory and Related Fields | 0178-8051 / 1432-2064 | Springer-Verlag | Springer Science+Business Media | ✓ 5,283；1962–2026 | 45% / 95% / 13% | 订阅/混合；OA 作品占比 90% |
| SIAM Journal on Numerical Analysis | 0036-1429 / 1095-7170 | Society for Industrial and Applied Mathematics | Society for Industrial and Applied Mathematics | ✓ 6,286；1966–2026 | 100% / 100% / 88% | 订阅/混合；OA 作品占比 19% |
| SIAM Review | 0036-1445 / 1095-7200 | Society for Industrial and Applied Mathematics | Society for Industrial and Applied Mathematics | ✓ 6,453；1959–2026 | 76% / 48% / 41% | 订阅/混合；OA 作品占比 6% |

#### 2.6.2 物理与天文

| 名称 | ISSN（print / e） | Crossref 出版方 | OpenAlex 宿主 | Crossref 可枚举（DOI 总数；年份跨度） | 摘要/参考文献/ORCID 覆盖（Crossref current） | OA 情况（OpenAlex） |
|---|---|---|---|---|---|---|
| Physical Review Letters | 0031-9007 / 1079-7114 | American Physical Society | American Physical Society | ✓ 143,948；1958–2026 | 29% / 96% / 95% | 订阅/混合；OA 作品占比 48% |
| Reviews of Modern Physics | 0034-6861 / 1539-0756 | American Physical Society | American Physical Society | ✓ 3,646；1929–2026 | 0% / 84% / 80% | 订阅/混合；OA 作品占比 28% |
| Physical Review X | — / 2160-3308 | American Physical Society | American Physical Society | ✓ 3,366；2011–2026 | 92% / 94% / 93% | 全刊 OA、DOAJ、OA 转型 2010；OA 作品占比 100% |
| Physical Review B | 1098-0121 / 1550-235X | American Physical Society | American Physical Society | ✓ 228,343；1970–2026 | 11% / 96% / 94% | 订阅/混合；OA 作品占比 63% |
| Physical Review D | 1550-7998 / 1089-4918 | American Physical Society | American Physical Society | ✓ 121,677；1970–2026 | 57% / 96% / 94% | 订阅/混合；OA 作品占比 87% |
| Physical Review A | 1050-2947 / 1094-1622 | American Physical Society | American Physical Society | ✓ 98,148；1970–2026 | 12% / 96% / 94% | 订阅/混合；OA 作品占比 43% |
| Physical Review E | 1539-3755 / 1550-2376 | American Physical Society | American Physical Society | ✓ 72,604；1993–2026 | 13% / 96% / 94% | 订阅/混合；OA 作品占比 57% |
| Physical Review Research | — / 2643-1564 | American Physical Society | American Physical Society | ✓ 10,578；2019–2026 | 95% / 96% / 95% | 全刊 OA、DOAJ、OA 转型 2018；OA 作品占比 100% |
| Nature Physics | 1745-2473 / 1745-2481 | Springer Science and Business Media LLC | Nature Portfolio | ✓ 7,504；2005–2026 | 16% / 88% / 80% | 订阅/混合；OA 作品占比 44% |
| Journal of High Energy Physics | 1126-6708 / 1029-8479 | Springer-Verlag | Springer Nature | ✓ 47,565；1997–2026 | 99% / 99% / 95% | 全刊 OA、DOAJ、OA 转型 2013；OA 作品占比 99% |
| Nuclear Physics B | 0550-3213 / 0550-3213 | Elsevier | Elsevier BV | ✓ 31,650；1967–2026 | 0% / 99% / 96% | 全刊 OA、DOAJ、OA 转型 2013；OA 作品占比 51% |
| Physics Letters B | 0370-2693 / — | Elsevier | Elsevier BV | ✓ 67,403；1967–2026 | 0% / 99% / 98% | 全刊 OA、DOAJ、OA 转型 2013；OA 作品占比 52% |
| New Journal of Physics | — / 1367-2630 | IOP Publishing | IOP Publishing | ✓ 14,728；1999–2026 | 99% / 97% / 94% | 全刊 OA、DOAJ、OA 转型 1997；OA 作品占比 100% |
| Physics Reports | 0370-1573 / — | Elsevier | Elsevier BV | ✓ 6,062；1971–2027 | 0% / 54% / 39% | 订阅/混合；OA 作品占比 21% |
| Reports on Progress in Physics | 0034-4885 / 1361-6633 | IOP Publishing | IOP Publishing | ✓ 2,774；1934–2026 | 98% / 94% / 95% | 订阅/混合；OA 作品占比 69% |
| Communications in Mathematical Physics | 0010-3616 / 1432-0916 | Springer-Verlag | Springer Science+Business Media | ✓ 12,663；1965–2026 | 46% / 99% / 86% | 订阅/混合；OA 作品占比 49% |
| Applied Physics Letters | 0003-6951 / 1077-3118 | American Institute of Physics | American Institute of Physics | ✓ 141,141；1962–2026 | 99% / 100% / 100% | 订阅/混合；OA 作品占比 19% |
| Quantum | — / 2521-327X | Verein zur Forderung des Open Access Publizierens in den Quantenwissenschaften | Verein zur Förderung des Open Access Publizierens in den Quantenwissenschaften | ✓ 2,214；2017–2026 | 100% / 100% / 37% | 全刊 OA、DOAJ、OA 转型 2016；OA 作品占比 98% |
| npj Quantum Information | — / 2056-6387 | Springer Science and Business Media LLC | Nature Portfolio | ✓ 1,381；2015–2026 | 51% / 84% / 45% | 全刊 OA、DOAJ、OA 转型 2014；OA 作品占比 100% |
| The Astrophysical Journal | 0004-637X / 1538-4357 | American Astronomical Society | IOP Publishing | ✓ 134,332；1895–2026 | 99% / 100% / 99% | 全刊 OA、DOAJ、OA 转型 2021；OA 作品占比 67% |
| Monthly Notices of the Royal Astronomical Society | 0035-8711 / 1365-8711 | Oxford University Press | Oxford University Press | ✓ 93,301；1827–2026 | 97% / 95% / 93% | 全刊 OA、DOAJ、OA 转型 2023；OA 作品占比 88% |
| Astronomy & Astrophysics | 0004-6361 / 1432-0746 | EDP Sciences | EDP Sciences | ✓ 58,633；2001–2026 | 99% / 94% / 93% | 全刊 OA、DOAJ、OA 转型 2021；OA 作品占比 99% |

#### 2.6.3 化学与材料

| 名称 | ISSN（print / e） | Crossref 出版方 | OpenAlex 宿主 | Crossref 可枚举（DOI 总数；年份跨度） | 摘要/参考文献/ORCID 覆盖（Crossref current） | OA 情况（OpenAlex） |
|---|---|---|---|---|---|---|
| Journal of the American Chemical Society | 0002-7863 / 1520-5126 | American Chemical Society | American Chemical Society | ✓ 221,071；1879–2026 | 10% / 96% / 97% | 订阅/混合；OA 作品占比 13% |
| Angewandte Chemie International Edition | 1433-7851 / 1521-3773 | Wiley (John Wiley & Sons) | Wiley | ✓ 81,883；1982–2026 | 92% / 92% / 87% | 订阅/混合；OA 作品占比 33% |
| Nature Chemistry | 1755-4330 / 1755-4349 | Springer Science and Business Media LLC | Nature Portfolio | ✓ 5,109；2008–2026 | 20% / 95% / 88% | 订阅/混合；OA 作品占比 33% |
| Chemical Reviews | 0009-2665 / 1520-6890 | American Chemical Society | American Chemical Society | ✓ 10,703；1924–2026 | 7% / 80% / 82% | 订阅/混合；OA 作品占比 18% |
| Chemical Society Reviews | 0306-0012 / 1460-4744 | The Royal Society of Chemistry | Royal Society of Chemistry | ✓ 9,324；1972–2026 | 77% / 75% / 75% | 订阅/混合；OA 作品占比 24% |
| Chemical Science | 2041-6520 / 2041-6539 | The Royal Society of Chemistry | Royal Society of Chemistry | ✓ 21,106；2010–2026 | 91% / 89% / 88% | 全刊 OA、DOAJ、OA 转型 2014；OA 作品占比 92% |
| Accounts of Chemical Research | 0001-4842 / 1520-4898 | American Chemical Society | American Chemical Society | ✓ 9,238；1968–2026 | 9% / 85% / 86% | 订阅/混合；OA 作品占比 20% |
| ACS Catalysis | 2155-5435 / 2155-5435 | American Chemical Society | American Chemical Society | ✓ 17,796；2010–2026 | 15% / 96% / 97% | 订阅/混合；OA 作品占比 28% |
| ACS Nano | 1936-0851 / 1936-086X | American Chemical Society | American Chemical Society | ✓ 29,425；2007–2026 | 7% / 95% / 96% | 订阅/混合；OA 作品占比 28% |
| Nature Catalysis | — / 2520-1158 | Springer Science and Business Media LLC | Nature Portfolio | ✓ 1,610；2017–2026 | 11% / 81% / 80% | 订阅/混合；OA 作品占比 32% |
| Chem | 2451-9294 / — | Elsevier | Elsevier BV | ✓ 2,920；2016–2026 | 0% / 94% / 70% | 订阅/混合；OA 作品占比 87% |
| JACS Au | 2691-3704 / 2691-3704 | American Chemical Society | American Chemical Society | ✓ 2,466；2020–2026 | 12% / 94% / 96% | 全刊 OA、DOAJ、OA 转型 2019；OA 作品占比 100% |
| Journal of Physical Chemistry Letters | 1948-7185 / 1948-7185 | American Chemical Society | American Chemical Society | ✓ 20,105；2009–2026 | 8% / 94% / 94% | 订阅/混合；OA 作品占比 29% |
| Journal of Chemical Physics | 0021-9606 / 1089-7690 | American Institute of Physics | American Institute of Physics | ✓ 150,900；1933–2026 | 98% / 100% / 100% | 订阅/混合；OA 作品占比 18% |
| Journal of Chemical Theory and Computation | 1549-9618 / 1549-9626 | American Chemical Society | American Chemical Society | ✓ 12,095；2004–2026 | 9% / 94% / 95% | 订阅/混合；OA 作品占比 42% |
| Analytical Chemistry | 0003-2700 / 1520-6882 | American Chemical Society | American Chemical Society | ✓ 140,192；1947–2026 | 9% / 96% / 96% | 订阅/混合；OA 作品占比 8% |
| Organic Letters | 1523-7060 / 1523-7052 | American Chemical Society | American Chemical Society | ✓ 45,822；1999–2026 | 8% / 95% / 95% | 订阅/混合；OA 作品占比 14% |
| Inorganic Chemistry | 0020-1669 / 1520-510X | American Chemical Society | American Chemical Society | ✓ 77,665；1962–2026 | 9% / 96% / 96% | 订阅/混合；OA 作品占比 10% |
| Chemical Communications | 1359-7345 / 1364-548X | The Royal Society of Chemistry | Royal Society of Chemistry | ✓ 78,105；1996–2026 | 89% / 87% / 87% | 订阅/混合；OA 作品占比 18% |
| Advanced Materials | 0935-9648 / 1521-4095 | Wiley (John Wiley & Sons) | — | ✓ 45,201；1989–2026 | 88% / 88% / 87% | 订阅/混合；OA 作品占比 33% |
| Energy & Environmental Science | 1754-5692 / 1754-5706 | The Royal Society of Chemistry | Royal Society of Chemistry | ✓ 8,287；2008–2026 | 86% / 84% / 84% | 订阅/混合；OA 作品占比 29% |

#### 2.6.4 生物与生命科学（含综合刊）

| 名称 | ISSN（print / e） | Crossref 出版方 | OpenAlex 宿主 | Crossref 可枚举（DOI 总数；年份跨度） | 摘要/参考文献/ORCID 覆盖（Crossref current） | OA 情况（OpenAlex） |
|---|---|---|---|---|---|---|
| Cell | 0092-8674 / — | Elsevier | Cell Press | ✓ 26,747；1973–2026 | 0% / 92% / 65% | 订阅/混合；OA 作品占比 66% |
| Nature | 0028-0836 / 1476-4687 | Springer Science and Business Media LLC | Nature Portfolio | ✓ 447,366；1869–2026 | 12% / 64% / 39% | 订阅/混合；OA 作品占比 17% |
| Science | 0036-8075 / 1095-9203 | American Association for the Advancement of Science (AAAS) | American Association for the Advancement of Science | ✓ 384,026；1880–2026 | 85% / 62% / 41% | 订阅/混合；OA 作品占比 8% |
| Proceedings of the National Academy of Sciences | 0027-8424 / 1091-6490 | Proceedings of the National Academy of Sciences | National Academy of Sciences | ✓ 171,866；1915–2026 | 85% / 94% / 91% | 订阅/混合；OA 作品占比 98% |
| Nature Communications | — / 2041-1723 | Springer Science and Business Media LLC | Nature Portfolio | ✓ 92,701；2010–2026 | 47% / 94% / 99% | 全刊 OA、DOAJ、OA 转型 2014；OA 作品占比 100% |
| Science Advances | 2375-2548 / 2375-2548 | American Association for the Advancement of Science (AAAS) | American Association for the Advancement of Science | ✓ 20,410；2015–2026 | 98% / 98% / 98% | 全刊 OA、DOAJ、OA 转型 2014；OA 作品占比 100% |
| eLife | — / 2050-084X | eLife Sciences Publications, Ltd. | eLife Sciences Publications Ltd | ✓ 23,021；2012–2026 | 99% / 98% / 100% | 全刊 OA、DOAJ、OA 转型 2011；OA 作品占比 100% |
| PLOS Biology | 1544-9173 / 1545-7885 | Public Library of Science | Public Library of Science | ✓ 8,713；2003–2026 | 82% / 100% / 95% | 全刊 OA、DOAJ、OA 转型 2002；OA 作品占比 100% |
| Nature Genetics | 1061-4036 / 1546-1718 | Springer Science and Business Media LLC | Nature Portfolio | ✓ 11,748；1992–2026 | 23% / 82% / 78% | 订阅/混合；OA 作品占比 40% |
| Nature Biotechnology | 1087-0156 / 1546-1696 | Springer Science and Business Media LLC | Nature Portfolio | ✓ 19,448；1983–2026 | 11% / 62% / 50% | 订阅/混合；OA 作品占比 22% |
| Nature Methods（⚠ Crossref 刊记录标题为 Nature Chemical Biology，见 §2.2.1） | 1548-7091 / 1548-7105（刊记录中类型为 null） | Springer Science and Business Media LLC | Nature Portfolio | ✓ 按 ISSN 枚举 8,419 条（container-title=Nature Methods 8,418）；刊记录计数 13,894 为两刊合并值 | 18% / 81% / 72%（合并记录值） | 订阅/混合；OA 作品占比 38% |
| Molecular Cell | 1097-2765 / — | Elsevier | Elsevier BV | ✓ 10,528；1997–2026 | 0% / 96% / 62% | 订阅/混合；OA 作品占比 96% |
| Current Biology | 0960-9822 / — | Elsevier | Elsevier BV | ✓ 25,731；1991–2026 | 0% / 92% / 45% | 订阅/混合；OA 作品占比 92% |
| The EMBO Journal | 0261-4189 / 1460-2075 | Springer Science and Business Media LLC | Springer Nature | ✓ 21,969；1982–2026 | 89% / 96% / 99% | 全刊 OA、DOAJ、OA 转型 2023；OA 作品占比 95% |
| Genome Research | 1088-9051 / 1088-9051 | Cold Spring Harbor Laboratory | Cold Spring Harbor Laboratory Press | ✓ 6,375；1991–2026 | 98% / 70% / 89% | 订阅/混合；OA 作品占比 97% |
| Genome Biology | 1465-6906 / 1465-6906 | Springer (Biomed Central Ltd.) | BioMed Central | ✓ 9,087；2000–2026 | 56% / 92% / 40% | 全刊 OA、DOAJ、OA 转型 1999；OA 作品占比 100% |
| Nucleic Acids Research | 0305-1048 / 1362-4962 | Oxford University Press | Oxford University Press | ✓ 55,929；1974–2026 | 94% / 94% / 94% | 全刊 OA、DOAJ、OA 转型 2004；OA 作品占比 99% |
| Bioinformatics | 1367-4803 / 1367-4811 | Oxford University Press | Oxford University Press | ✓ 21,227；1985–2026 | 98% / 96% / 94% | 全刊 OA、DOAJ、OA 转型 2022；OA 作品占比 82% |
| PLOS Computational Biology | 1553-734X / 1553-7358 | Public Library of Science | Public Library of Science | ✓ 13,029；2005–2026 | 95% / 100% / 98% | 全刊 OA、DOAJ、OA 转型 2004；OA 作品占比 100% |
| Molecular Biology and Evolution | 0737-4038 / 1537-1719 | Oxford University Press | Oxford University Press | ✓ 9,558；1984–2026 | 94% / 94% / 97% | 全刊 OA、DOAJ、OA 转型 2020；OA 作品占比 82% |
| Neuron | 0896-6273 / — | Elsevier | Cell Press | ✓ 14,341；1988–2026 | 0% / 95% / 63% | 订阅/混合；OA 作品占比 89% |
| Nature Neuroscience | 1097-6256 / 1546-1726 | Springer Science and Business Media LLC | Nature Portfolio | ✓ 8,165；1998–2026 | 25% / 81% / 80% | 订阅/混合；OA 作品占比 48% |
| Cell Reports | 2211-1247 / — | Elsevier | Cell Press | ✓ 17,203；2012–2026 | 0% / 95% / 78% | 全刊 OA、DOAJ、OA 转型 2011；OA 作品占比 100% |
| Nature Ecology & Evolution | — / 2397-334X | Springer Science and Business Media LLC | Nature Portfolio | ✓ 3,148；2016–2026 | 17% / 81% / 77% | 订阅/混合；OA 作品占比 50% |

#### 2.6.5 心理学

| 名称 | ISSN（print / e） | Crossref 出版方 | OpenAlex 宿主 | Crossref 可枚举（DOI 总数；年份跨度） | 摘要/参考文献/ORCID 覆盖（Crossref current） | OA 情况（OpenAlex） |
|---|---|---|---|---|---|---|
| Psychological Science | 0956-7976 / 1467-9280 | SAGE Publications | SAGE Publishing | ✓ 5,727；1990–2026 | 98% / 98% / 95% | 订阅/混合；OA 作品占比 29% |
| Psychological Bulletin | 0033-2909 / 1939-1455 | American Psychological Association | American Psychological Association | ✓ 10,706；1904–2026 | 0% / 0% / 53% | 订阅/混合；OA 作品占比 12% |
| Psychological Review | 0033-295X / 1939-1471 | American Psychological Association | American Psychological Association | ✓ 6,914；1894–2026 | 0% / 0% / 77% | 订阅/混合；OA 作品占比 24% |
| Journal of Personality and Social Psychology | 0022-3514 / 1939-1315 | American Psychological Association | American Psychological Association | ✓ 14,722；1965–2026 | 0% / 0% / 56% | 订阅/混合；OA 作品占比 7% |
| Journal of Experimental Psychology: General | 0096-3445 / 1939-2222 | American Psychological Association | American Psychological Association | ✓ 5,169；1975–2026 | 0% / 0% / 58% | 订阅/混合；OA 作品占比 27% |
| Annual Review of Psychology | 0066-4308 / 1545-2085 | Annual Reviews | Annual Reviews | ✓ 1,917；1950–2026 | 93% / 86% / 1% | 订阅/混合；OA 作品占比 18% |
| American Psychologist | 0003-066X / 1935-990X | American Psychological Association | American Psychological Association | ✓ 21,002；1946–2026 | 0% / 0% / 62% | 订阅/混合；OA 作品占比 4% |
| Nature Human Behaviour | — / 2397-3374 | Springer Science and Business Media LLC | Nature Portfolio | ✓ 2,556；2016–2026 | 19% / 95% / 88% | 订阅/混合；OA 作品占比 47% |
| Trends in Cognitive Sciences | 1364-6613 / — | Elsevier | Elsevier BV | ✓ 4,326；1997–2026 | 0% / 86% / 71% | 订阅/混合；OA 作品占比 33% |
| Cognition | 0010-0277 / — | Elsevier | Elsevier BV | ✓ 6,659；1972–2027 | 0% / 94% / 11% | 订阅/混合；OA 作品占比 40% |
| Cognitive Psychology | 0010-0285 / 1095-5623 | Elsevier | Elsevier BV | ✓ 1,610；1970–2026 | 0% / 79% / 56% | 订阅/混合；OA 作品占比 23% |
| Journal of Memory and Language | 0749-596X / 1096-0821 | Elsevier | Elsevier BV | ✓ 2,731；1985–2027 | 0% / 91% / 59% | 订阅/混合；OA 作品占比 32% |
| Perspectives on Psychological Science | 1745-6916 / 1745-6924 | SAGE Publications | SAGE Publishing | ✓ 1,533；2006–2026 | 91% / 97% / 95% | 订阅/混合；OA 作品占比 40% |
| Advances in Methods and Practices in Psychological Science | 2515-2459 / 2515-2467 | SAGE Publications | SAGE Publishing | ✓ 377；2018–2026 | 92% / 99% / 98% | 全刊 OA、DOAJ、OA 转型 2020；OA 作品占比 95% |
| Psychonomic Bulletin & Review | 1069-9384 / 1531-5320 | Springer - Psychonomic Society | Springer Science+Business Media | ✓ 4,787；1994–2026 | 57% / 98% / 61% | 订阅/混合；OA 作品占比 90% |
| Behavior Research Methods | 1554-351X / 1554-3528 | Springer - Psychonomic Society | Springer Science+Business Media | ✓ 5,595；1968–2026 | 62% / 97% / 67% | 订阅/混合；OA 作品占比 92% |
| Developmental Psychology | 0012-1649 / 1939-0599 | American Psychological Association | American Psychological Association | ✓ 11,231；1969–2026 | 0% / 0% / 59% | 订阅/混合；OA 作品占比 17% |
| Clinical Psychology Review | 0272-7358 / — | Elsevier | Elsevier BV | ✓ 3,125；1981–2026 | 0% / 90% / 1% | 订阅/混合；OA 作品占比 24% |
| Journal of Applied Psychology | 0021-9010 / 1939-1854 | American Psychological Association | American Psychological Association | ✓ 12,593；1917–2026 | 0% / 0% / 78% | 订阅/混合；OA 作品占比 5% |
| Collabra: Psychology | — / 2474-7394 | University of California Press | University of California Press | ✓ 779；2017–2026 | 99% / 0% / 71% | 全刊 OA、DOAJ、OA 转型 2016；OA 作品占比 100% |
| Journal of Psychopathology and Clinical Science | 2769-7541 / 2769-755X | American Psychological Association | American Psychological Association | ✓ 804；2020–2026 | 0% / 0% / 58% | 订阅/混合；OA 作品占比 45% |

#### 2.6.6 经济学

| 名称 | ISSN（print / e） | Crossref 出版方 | OpenAlex 宿主 | Crossref 可枚举（DOI 总数；年份跨度） | 摘要/参考文献/ORCID 覆盖（Crossref current） | OA 情况（OpenAlex） |
|---|---|---|---|---|---|---|
| American Economic Review | 0002-8282 / 1944-7981 | American Economic Association | American Economic Association | ✓ 5,666；1999–2026 | 89% / 90% / 0% | 订阅/混合；OA 作品占比 18% |
| Econometrica | 0012-9682 / 1468-0262 | The Econometric Society | Wiley | ✓ 7,320；1933–2026 | 69% / 74% / 0% | 订阅/混合；OA 作品占比 13% |
| Journal of Political Economy | 0022-3808 / 1537-534X | The University of Chicago Press | University of Chicago Press | ✓ 15,841；1892–2026 | 0% / 74% / 0% | 订阅/混合；OA 作品占比 8% |
| Quarterly Journal of Economics | 0033-5533 / 1531-4650 | Oxford University Press | Oxford University Press | ✓ 6,665；1886–2026 | 97% / 93% / 1% | 订阅/混合；OA 作品占比 10% |
| Review of Economic Studies | 0034-6527 / 1467-937X | Oxford University Press | Oxford University Press | ✓ 4,292；1933–2026 | 98% / 95% / 1% | 订阅/混合；OA 作品占比 19% |
| AEJ: Applied Economics | 1945-7782 / 1945-7790 | American Economic Association | American Economic Association | ✓ 843；2009–2026 | 93% / 93% / 0% | 订阅/混合；OA 作品占比 44% |
| AEJ: Macroeconomics | 1945-7707 / 1945-7715 | American Economic Association | American Economic Association | ✓ 744；2009–2026 | 92% / 92% / 0% | 订阅/混合；OA 作品占比 35% |
| AEJ: Microeconomics | 1945-7669 / 1945-7685 | American Economic Association | American Economic Association | ✓ 862；2009–2026 | 93% / 93% / 0% | 订阅/混合；OA 作品占比 35% |
| AEJ: Economic Policy | 1945-774X / 1945-774X | American Economic Association | American Economic Association | ✓ 919；2009–2026 | 94% / 94% / 0% | 订阅/混合；OA 作品占比 39% |
| Journal of Economic Perspectives | 0895-3309 / — | American Economic Association | American Economic Association | ✓ 2,342；1987–2026 | 84% / 84% / 0% | 全刊 OA、OA 转型 2017；OA 作品占比 56% |
| Journal of Economic Literature | 0022-0515 / 2328-8175 | American Economic Association | American Economic Association | ✓ 2,073；1999–2026 | 90% / 75% / 0% | 订阅/混合；OA 作品占比 7% |
| Review of Economics and Statistics | 0034-6535 / 1530-9142 | MIT Press | The MIT Press | ✓ 7,631；1919–2026 | 99% / 55% / 0% | 订阅/混合；OA 作品占比 13% |
| Journal of the European Economic Association | 1542-4766 / 1542-4774 | Oxford University Press | Oxford University Press | ✓ 1,713；2003–2026 | 97% / 92% / 4% | 订阅/混合；OA 作品占比 38% |
| The Economic Journal | 0013-0133 / 1468-0297 | Oxford University Press | Oxford University Press | ✓ 19,717；1891–2026 | 97% / 74% / 6% | 订阅/混合；OA 作品占比 14% |
| International Economic Review | 0020-6598 / 1468-2354 | Wiley (Blackwell Publishing) | Wiley | ✓ 3,594；1960–2026 | 85% / 88% / 5% | 订阅/混合；OA 作品占比 21% |
| Journal of Economic Theory | 0022-0531 / 1095-7235 | Elsevier | Elsevier BV | ✓ 6,272；1969–2026 | 0% / 93% / 68% | 订阅/混合；OA 作品占比 22% |
| Journal of Econometrics | 0304-4076 / 1872-6895 | Elsevier | Elsevier BV | ✓ 6,486；1973–2026 | 0% / 94% / 38% | 订阅/混合；OA 作品占比 26% |
| Journal of Monetary Economics | 0304-3932 / — | Elsevier | Elsevier BV | ✓ 4,016；1975–2026 | 0% / 91% / 42% | 订阅/混合；OA 作品占比 21% |
| Journal of Public Economics | 0047-2727 / — | Elsevier | Elsevier BV | ✓ 5,457；1972–2026 | 0% / 93% / 55% | 订阅/混合；OA 作品占比 25% |
| Journal of Development Economics | 0304-3878 / — | Elsevier | Elsevier BV | ✓ 4,822；1974–2027 | 0% / 96% / 83% | 订阅/混合；OA 作品占比 23% |
| Journal of International Economics | 0022-1996 / — | Elsevier | Elsevier BV | ✓ 4,222；1971–2026 | 0% / 94% / 53% | 订阅/混合；OA 作品占比 23% |
| Journal of Labor Economics | 0734-306X / 1537-5307 | The University of Chicago Press | University of Chicago Press | ✓ 1,923；1983–2026 | 0% / 89% / 0% | 订阅/混合；OA 作品占比 16% |
| RAND Journal of Economics | 0741-6261 / 1756-2171 | Wiley (Blackwell Publishing) | Wiley | ✓ 1,790；1984–2026 | 83% / 83% / 11% | 订阅/混合；OA 作品占比 26% |
| Theoretical Economics | 1933-6837 / 1555-7561 | The Econometric Society | Econometric Society | ✓ 735；2010–2026 | 85% / 85% / 0% | 全刊 OA、DOAJ、OA 转型 2009；OA 作品占比 100% |
| Quantitative Economics | 1759-7323 / 1759-7331 | The Econometric Society | Wiley | ✓ 617；2010–2026 | 81% / 81% / 0% | 全刊 OA、DOAJ、OA 转型 2009；OA 作品占比 98% |

#### 2.6.7 金融学

| 名称 | ISSN（print / e） | Crossref 出版方 | OpenAlex 宿主 | Crossref 可枚举（DOI 总数；年份跨度） | 摘要/参考文献/ORCID 覆盖（Crossref current） | OA 情况（OpenAlex） |
|---|---|---|---|---|---|---|
| Journal of Finance | 0022-1082 / 1540-6261 | Wiley (Blackwell Publishing) | Wiley | ✓ 15,494；1946–2026 | 73% / 73% / 1% | 订阅/混合；OA 作品占比 8% |
| Journal of Financial Economics | 0304-405X / — | Elsevier | Elsevier BV | ✓ 4,537；1974–2026 | 0% / 91% / 45% | 订阅/混合；OA 作品占比 22% |
| Review of Financial Studies | 0893-9454 / 1465-7368 | Oxford University Press | Oxford University Press | ✓ 3,285；1988–2026 | 98% / 95% / 3% | 订阅/混合；OA 作品占比 22% |
| Journal of Financial and Quantitative Analysis | 0022-1090 / 1756-6916 | Cambridge University Press | Cambridge University Press | ✓ 4,096；1966–2026 | 84% / 68% / 83% | 订阅/混合；OA 作品占比 32% |
| Review of Finance | 1572-3097 / 1573-692X | Oxford University Press | Oxford University Press | ✓ 1,153；1997–2026 | 99% / 93% / 6% | 订阅/混合；OA 作品占比 69% |
| Journal of Financial Intermediation | 1042-9573 / 1096-0473 | Elsevier | Elsevier BV | ✓ 1,037；1990–2026 | 0% / 85% / 52% | 订阅/混合；OA 作品占比 20% |
| Journal of Banking & Finance | 0378-4266 / — | Elsevier | Elsevier BV | ✓ 7,534；1977–2026 | 0% / 93% / 63% | 订阅/混合；OA 作品占比 20% |
| Journal of Financial Markets | 1386-4181 / — | Elsevier | Elsevier BV | ✓ 918；1998–2026 | 0% / 88% / 62% | 订阅/混合；OA 作品占比 23% |
| Journal of Corporate Finance | 0929-1199 / — | Elsevier | Elsevier BV | ✓ 2,856；1994–2027 | 0% / 95% / 26% | 订阅/混合；OA 作品占比 31% |
| Review of Asset Pricing Studies | 2045-9920 / 2045-9939 | Oxford University Press | Oxford University Press | ✓ 271；2011–2026 | 98% / 100% / 2% | 订阅/混合；OA 作品占比 26% |
| Review of Corporate Finance Studies | 2046-9128 / 2046-9136 | Oxford University Press | Oxford University Press | ✓ 307；2012–2026 | 99% / 99% / 1% | 订阅/混合；OA 作品占比 33% |
| Mathematical Finance | 0960-1627 / 1467-9965 | Wiley (Blackwell Publishing) | Wiley | ✓ 1,264；1991–2026 | 78% / 77% / 69% | 订阅/混合；OA 作品占比 36% |
| Finance and Stochastics | 0949-2984 / 1432-1122 | Springer-Verlag | Springer Science+Business Media | ✓ 831；1996–2026 | 54% / 100% / 0% | 订阅/混合；OA 作品占比 42% |
| Quantitative Finance | 1469-7688 / 1469-7696 | Informa UK (Taylor & Francis) | Taylor & Francis | ✓ 3,040；2000–2026 | 0% / 97% / 48% | 订阅/混合；OA 作品占比 28% |
| SIAM Journal on Financial Mathematics | 1945-497X / 1945-497X | Society for Industrial and Applied Mathematics | Society for Industrial and Applied Mathematics | ✓ 673；2010–2026 | 100% / 100% / 82% | 订阅/混合；OA 作品占比 44% |
| Journal of Financial Econometrics | 1479-8409 / 1479-8417 | Oxford University Press | Oxford University Press | ✓ 701；2003–2026 | 97% / 100% / 99% | 订阅/混合；OA 作品占比 33% |
| Journal of Empirical Finance | 0927-5398 / — | Elsevier | Elsevier BV | ✓ 1,870；1993–2026 | 0% / 93% / 67% | 订阅/混合；OA 作品占比 25% |
| Annual Review of Financial Economics | 1941-1367 / 1941-1375 | Annual Reviews | Annual Reviews | ✓ 361；2008–2026 | 95% / 62% / 0% | 订阅/混合；OA 作品占比 46% |

#### 2.6.8 商学（营销/会计/信息系统/国际商务/创业）

| 名称 | ISSN（print / e） | Crossref 出版方 | OpenAlex 宿主 | Crossref 可枚举（DOI 总数；年份跨度） | 摘要/参考文献/ORCID 覆盖（Crossref current） | OA 情况（OpenAlex） |
|---|---|---|---|---|---|---|
| Journal of Marketing | 0022-2429 / 0022-2429 | SAGE Publications | SAGE Publishing | ✓ 12,018；1936–2026 | 95% / 89% / 84% | 订阅/混合；OA 作品占比 3% |
| Journal of Marketing Research | 0022-2437 / 1547-7193 | SAGE Publications | SAGE Publishing | ✓ 7,592；1964–2026 | 98% / 90% / 86% | 订阅/混合；OA 作品占比 5% |
| Journal of Consumer Research | 0093-5301 / 1537-5277 | Oxford University Press | Oxford University Press | ✓ 3,427；1974–2026 | 90% / 86% / 75% | 订阅/混合；OA 作品占比 15% |
| Marketing Science | 0732-2399 / 1526-548X | Institute for Operations Research and the Management Sciences | Institute for Operations Research and the Management Sciences | ✓ 2,290；1982–2026 | 85% / 83% / 85% | 订阅/混合；OA 作品占比 12% |
| Journal of the Academy of Marketing Science | 0092-0703 / 1552-7824 | Springer-Verlag | Springer Science+Business Media | ✓ 3,608；1973–2026 | 48% / 96% / 82% | 订阅/混合；OA 作品占比 13% |
| Journal of Consumer Psychology | 1057-7408 / 1532-7663 | Wiley (John Wiley & Sons) | Elsevier BV | ✓ 1,880；1992–2026 | 78% / 80% / 72% | 订阅/混合；OA 作品占比 26% |
| The Accounting Review | 0001-4826 / 1558-7967 | American Accounting Association | American Accounting Association | ✓ 11,750；1926–2026 | 91% / 83% / 91% | 订阅/混合；OA 作品占比 5% |
| Journal of Accounting Research | 0021-8456 / 1475-679X | Wiley (Blackwell Publishing) | Wiley | ✓ 2,805；1963–2026 | 70% / 70% / 53% | 订阅/混合；OA 作品占比 18% |
| Journal of Accounting and Economics | 0165-4101 / — | Elsevier | Elsevier BV | ✓ 1,871；1979–2026 | 0% / 85% / 81% | 订阅/混合；OA 作品占比 16% |
| Review of Accounting Studies | 1380-6653 / 1573-7136 | Springer-Verlag | Springer Science+Business Media | ✓ 1,198；1996–2026 | 61% / 98% / 88% | 订阅/混合；OA 作品占比 36% |
| Contemporary Accounting Research | 0823-9150 / 1911-3846 | Wiley (Blackwell Publishing) | Wiley | ✓ 2,468；1984–2026 | 90% / 90% / 63% | 订阅/混合；OA 作品占比 23% |
| MIS Quarterly | 0276-7783 / 2162-9730 | MIS Quarterly | MIS Quarterly | ✓ 2,264；1977–2026 | 90% / 93% / 1% | 订阅/混合；OA 作品占比 12% |
| Information Systems Research | 1047-7047 / 1526-5536 | Institute for Operations Research and the Management Sciences | Institute for Operations Research and the Management Sciences | ✓ 1,966；1990–2026 | 93% / 88% / 93% | 订阅/混合；OA 作品占比 15% |
| Journal of Management Information Systems | 0742-1222 / 1557-928X | Informa UK (Taylor & Francis) | Taylor & Francis | ✓ 1,801；1984–2026 | 0% / 94% / 49% | 订阅/混合；OA 作品占比 14% |
| Journal of International Business Studies | 0047-2506 / 1478-6990 | Springer Science and Business Media LLC | Palgrave Macmillan | ✓ 3,321；1970–2026 | 36% / 94% / 5% | 订阅/混合；OA 作品占比 24% |
| Journal of Business Venturing | 0883-9026 / — | Elsevier | Elsevier BV | ✓ 1,773；1985–2027 | 0% / 89% / 11% | 订阅/混合；OA 作品占比 25% |
| Journal of Business Ethics | 0167-4544 / 1573-0697 | Springer-Verlag | Springer Science+Business Media | ✓ 10,649；1982–2026 | 43% / 97% / 76% | 订阅/混合；OA 作品占比 22% |

#### 2.6.9 管理学（组织/战略/运营/OR）

| 名称 | ISSN（print / e） | Crossref 出版方 | OpenAlex 宿主 | Crossref 可枚举（DOI 总数；年份跨度） | 摘要/参考文献/ORCID 覆盖（Crossref current） | OA 情况（OpenAlex） |
|---|---|---|---|---|---|---|
| Academy of Management Journal | 0001-4273 / 1948-0989 | Academy of Management | Academy of Management | ✓ 4,520；1958–2026 | 0% / 100% / 51% | 订阅/混合；OA 作品占比 6% |
| Academy of Management Review | 0363-7425 / 1930-3807 | Academy of Management | Academy of Management | ✓ 4,398；1976–2026 | 0% / 100% / 44% | 订阅/混合；OA 作品占比 4% |
| Academy of Management Annals | 1941-6520 / 1941-6067 | Academy of Management | Routledge | ✓ 393；2007–2026 | 0% / 100% / 48% | 订阅/混合；OA 作品占比 20% |
| Administrative Science Quarterly | 0001-8392 / 1930-3815 | SAGE Publications | SAGE Publishing | ✓ 4,309；1956–2026 | 39% / 79% / 90% | 订阅/混合；OA 作品占比 8% |
| Strategic Management Journal | 0143-2095 / 1097-0266 | Wiley (John Wiley & Sons) | Wiley | ✓ 4,411；1980–2026 | 78% / 78% / 70% | 订阅/混合；OA 作品占比 24% |
| Organization Science | 1047-7039 / 1526-5455 | Institute for Operations Research and the Management Sciences | Institute for Operations Research and the Management Sciences | ✓ 2,628；1990–2026 | 95% / 90% / 95% | 订阅/混合；OA 作品占比 18% |
| Management Science | 0025-1909 / 1526-5501 | Institute for Operations Research and the Management Sciences | Institute for Operations Research and the Management Sciences | ✓ 12,478；1954–2026 | 97% / 95% / 97% | 订阅/混合；OA 作品占比 13% |
| Journal of Management | 0149-2063 / 1557-1211 | SAGE Publications | SAGE Publishing | ✓ 3,259；1975–2026 | 99% / 100% / 99% | 订阅/混合；OA 作品占比 20% |
| Journal of Management Studies | 0022-2380 / 1467-6486 | Wiley (Blackwell Publishing) | Wiley | ✓ 3,763；1964–2026 | 78% / 82% / 81% | 订阅/混合；OA 作品占比 32% |
| Research Policy | 0048-7333 / — | Elsevier | Elsevier BV | ✓ 5,262；1971–2026 | 0% / 94% / 25% | 订阅/混合；OA 作品占比 32% |
| Organizational Behavior and Human Decision Processes | 0749-5978 / 1095-9920 | Elsevier | Elsevier BV | ✓ 2,624；1985–2026 | 0% / 81% / 39% | 订阅/混合；OA 作品占比 16% |
| Personnel Psychology | 0031-5826 / 1744-6570 | Wiley (Blackwell Publishing) | Wiley | ✓ 4,071；1948–2026 | 55% / 65% / 57% | 订阅/混合；OA 作品占比 8% |
| The Leadership Quarterly | 1048-9843 / — | Elsevier | Elsevier BV | ✓ 2,081；1990–2026 | 0% / 85% / 52% | 订阅/混合；OA 作品占比 18% |
| Operations Research | 0030-364X / 1526-5463 | Institute for Operations Research and the Management Sciences | Institute for Operations Research and the Management Sciences | ✓ 7,922；1956–2026 | 93% / 91% / 93% | 订阅/混合；OA 作品占比 10% |
| Manufacturing & Service Operations Management | 1523-4614 / 1526-5498 | Institute for Operations Research and the Management Sciences | Institute for Operations Research and the Management Sciences | ✓ 1,800；1999–2026 | 95% / 88% / 94% | 订阅/混合；OA 作品占比 16% |
| Mathematics of Operations Research | 0364-765X / 1526-5471 | Institute for Operations Research and the Management Sciences | Institute for Operations Research and the Management Sciences | ✓ 3,114；1976–2026 | 97% / 97% / 97% | 订阅/混合；OA 作品占比 19% |
| Production and Operations Management | 1059-1478 / 1937-5956 | SAGE Publications | Wiley | ✓ 3,929；1992–2026 | 99% / 97% / 92% | 订阅/混合；OA 作品占比 20% |
| Journal of Operations Management | 0272-6963 / 1873-1317 | Wiley (Blackwell Publishing) | Wiley | ✓ 2,436；1980–2026 | 64% / 74% / 74% | 订阅/混合；OA 作品占比 20% |
| European Journal of Operational Research | 0377-2217 / — | Elsevier | Elsevier BV | ✓ 24,778；1977–2027 | 0% / 95% / 90% | 订阅/混合；OA 作品占比 21% |

#### 2.6.10 计算机与 AI（期刊）

| 名称 | ISSN（print / e） | Crossref 出版方 | OpenAlex 宿主 | Crossref 可枚举（DOI 总数；年份跨度） | 摘要/参考文献/ORCID 覆盖（Crossref current） | OA 情况（OpenAlex） |
|---|---|---|---|---|---|---|
| Journal of Machine Learning Research | 1532-4435 / — | Unmaintained records | The MIT Press | ✗（刊记录存在但 0 个 DOI） | 0% / 0% / 0% | 订阅/混合；OA 作品占比 1%（⚠ 与 v1 核验"完全 OA"不符，OpenAlex OA 判定偏差） |
| Transactions on Machine Learning Research | 2835-8856 | — | — | ✗（Crossref /journals 返回 404） | — | 全刊 OA、DOAJ、OA 转型 2021；OA 作品占比 100% |
| Journal of Artificial Intelligence Research | — / 1076-9757 | AI Access Foundation | AI Access Foundation | ✓ 1,873；1993–2026 | 100% / 0% / 59% | 全刊 OA、DOAJ、OA 转型 1992；OA 作品占比 100% |
| Transactions of the ACL | — / 2307-387X | MIT Press | Association for Computational Linguistics | ✓ 911；2013–2026 | 100% / 100% / 0% | 全刊 OA、DOAJ、OA 转型 2012；OA 作品占比 100% |
| IEEE Transactions on Pattern Analysis and Machine Intelligence | 0162-8828 / 2160-9292 | Institute of Electrical and Electronics Engineers | IEEE Computer Society | ✓ 12,447；1979–2026 | 0% / 88% / 91% | 订阅/混合；OA 作品占比 20% |
| IEEE Transactions on Neural Networks and Learning Systems | 2162-237X / 2162-2388 | Institute of Electrical and Electronics Engineers | Institute of Electrical and Electronics Engineers | ✓ 9,042；2012–2026 | 0% / 86% / 96% | 订阅/混合；OA 作品占比 19% |
| IEEE Transactions on Knowledge and Data Engineering | 1041-4347 / 1558-2191 | Institute of Electrical and Electronics Engineers | IEEE Computer Society | ✓ 8,056；1989–2026 | 0% / 93% / 95% | 订阅/混合；OA 作品占比 13% |
| Artificial Intelligence | 0004-3702 / — | Elsevier | Elsevier BV | ✓ 4,850；1970–2026 | 0% / 89% / 84% | 订阅/混合；OA 作品占比 67% |
| International Journal of Computer Vision | 0920-5691 / 1573-1405 | Springer-Verlag | Springer Science+Business Media | ✓ 4,011；1987–2026 | 19% / 96% / 86% | 订阅/混合；OA 作品占比 31% |
| Machine Learning | 0885-6125 / 1573-0565 | Springer-Verlag | Springer Science+Business Media | ✓ 3,341；1986–2026 | 44% / 97% / 33% | 订阅/混合；OA 作品占比 75% |
| Nature Machine Intelligence | — / 2522-5839 | Springer Science and Business Media LLC | Nature Portfolio | ✓ 1,301；2019–2026 | 20% / 97% / 92% | 订阅/混合；OA 作品占比 50% |
| Journal of the ACM | 0004-5411 / 1557-735X | Association for Computing Machinery | Association for Computing Machinery | ✓ 3,336；1954–2026 | 100% / 100% / 100% | 订阅/混合；OA 作品占比 74% |
| Communications of the ACM | 0001-0782 / 1557-7317 | Association for Computing Machinery | Association for Computing Machinery | ✓ 15,452；1958–2026 | 80% / 65% / 38% | 订阅/混合；OA 作品占比 52% |
| Proceedings of the VLDB Endowment | 2150-8097 / — | VLDB Endowment | Association for Computing Machinery | ✓ 5,220；2008–2026 | 100% / 99% / 0% | 订阅/混合；OA 作品占比 18%（⚠ v1 记为 CC BY-NC-ND 开放，OpenAlex OA 判定偏差） |
| ACM Computing Surveys | 0360-0300 / 1557-7341 | Association for Computing Machinery | Association for Computing Machinery | ✓ 3,825；1969–2026 | 100% / 99% / 100% | 订阅/混合；OA 作品占比 54% |

> **ISSN 归一提示（[LIVE] 核验副产品）**：有 7 本刊，查询所用 ISSN 不在 Crossref 刊记录的 typed ISSN 里（表中 ISSN 列显示的是 typed 值）：
> - Physical Review A/B/D/E：每条刊记录挂 5–7 个历代 ISSN，例如 PRB 记录同时含 0163-1829、0556-2805、1095-3795、1098-0121、1550-235X、2469-9950、2469-9969；
> - Nature Methods：两个 ISSN 挂在 Nature Chemical Biology 的记录下；
> - Genome Biology、AEJ: Economic Policy：typed 值为另一个号。
>
> 因此 v2 的 venue 标识必须用"ISSN 集合 + ISSN-L + OpenAlex source ID"归一，不能以单个 ISSN 作主键。

#### 2.6.11 计算机与 AI（会议）

> [LIVE] 2026-09-26 Crossref `/works` 分面查询（`facet=container-title`）：有 DOI 前缀的会议用 `prefix:` + 日期窗口，无前缀的会议用 `query.container-title` 模糊查询，看前 6 个分面中有没有该会议。"✗"的含义是模糊查询前 6 个分面里没有出现，不等于严格证明"完全不在 Crossref"。OA 与平台情况沿用 v1 目录 [v1 publishers-platforms.md]。

| 会议 | 标识 / DOI 前缀 | 首发平台（L1） | Crossref 可枚举 | 实测证据 | OA 情况 | 路由建议 |
|---|---|---|---|---|---|---|
| NeurIPS | 无 DOI 前缀 | proceedings.neurips.cc + OpenReview | ✗ | 模糊查询前 6 分面均为无关容器 | 全 OA [v1] | L1 适配器（v1 `neurips_proceedings`/`openreview`）；OpenAlex 会议实体仅 4,177 条（碎片化） |
| ICML | 无（PMLR） | proceedings.mlr.press | ✗ | 同上 | 全 OA [v1] | L1 `pmlr` |
| ICLR | 无（OpenReview） | openreview.net | ✗ | 同上 | 全 OA [v1] | L1 `openreview`；OpenAlex 实体仅 757 条 |
| AAAI | 10.1609 | ojs.aaai.org | ✓ | 2025 年以来 9,807 条，其中 "Proceedings of the AAAI Conference on Artificial Intelligence" 8,406 条 | 免费阅读 [v1] | Crossref 前缀增量 + L1 `aaai_ojs`（OAI-PMH） |
| IJCAI | 10.24963 | ijcai.org | ✓ | IJCAI-25 1,281 条、IJCAI-26 972 条 | 免费阅读 ⚠ | Crossref 前缀增量 |
| ACL / EMNLP / NAACL / Findings | 10.18653 | aclanthology.org | ✓ | 2025 年以来 19,129 条（ACL 2026 Long 2,223、Findings ACL 2026 2,164、EMNLP 2025 1,810 …） | 全 OA，CC BY [v1] | Crossref 前缀增量 + L1 `acl_anthology`（GitHub bulk） |
| CVPR / ICCV | 10.1109（IEEE）+ CVF 开放版 | ieeexplore + openaccess.thecvf.com | ✓（IEEE 版） | "2024 IEEE/CVF CVPR" 2,724 条（另有 CVPRW 810 条） | CVF 版免费 [v1] | 元数据走 Crossref（IEEE），全文走 L1 `cvf` |
| ECCV | 10.1007（Springer LNCS） | link.springer.com | ✓ | "Computer Vision – ECCV 2024" 2,361 条 | 混合 ⚠ | Crossref（按 ISBN/容器） |
| KDD / WWW / SIGIR / CIKM / CHI | 10.1145（ACM） | dl.acm.org | ✓ | KDD 2025 V.2 594 条、SIGIR 2025 540 条、CIKM 2025 852 条、CHI 2025 1,249 条、WWW 2025 447 条（各在查询窗口内） | ACM 自 2026-01-01 起全面 OA（v1 D-013；核验确认 ACM 官方公告 [S122]） | Crossref 前缀 + 容器名 |
| SODA | 10.1137（SIAM） | epubs.siam.org | ✓ | SODA 2025 193 条 | 订阅 [v1] | Crossref（book 结构，见 v1） |
| OSDI / NSDI | 无（USENIX） | usenix.org | ✗ | 模糊查询前 6 分面无 USENIX | 全 OA [v1] | L1 `usenix`（v1 已登记，未实现） |
| VLDB | PVLDB ISSN 2150-8097 | vldb.org/pvldb | ✓（按期刊） | 5,220 个 DOI（2008–2026） | CC BY-NC-ND [v1] | Crossref ISSN |

### 2.7 客户端库与开源参考（实现参考，GitHub 元数据 [S110] 2026-09-26）

| 仓库 | ★ | License | 最近推送 | 状态/用途 | 对 v2 的意义 |
|---|---|---|---|---|---|
| J535D165/pyalex | 417 | MIT | 2026-07-06 | OpenAlex Python 客户端 | 可参考其链式查询与分页封装；计费与预算须自建 |
| sckott/habanero | 251 | MIT | 2026-09-25 | Crossref Python 客户端 | 活跃；池/限速头处理需自核 |
| fabiobatalha/crossrefapi | 349 | BSD-2-Clause | 2025-07-07 | Crossref Python 客户端 | 近一年无推送 |
| danielnsilva/semanticscholar | 481 | MIT | 2026-08-01 | S2 Python 客户端（同步/异步） | 可直接用于 S2 enrich |
| allenai/s2-folks | 278 | NOASSERTION | 2025-01-24 | S2 社区文档 | **已归档**（v1 已记） |
| allenai/SPECTER2 | 144 | Apache-2.0 | 2026-02-24 | SPECTER2 模型代码 | 自算嵌入时与 S2 嵌入数据集兼容 [S29] |
| ourresearch/openalex-elastic-api | 42 | MIT | 2026-09-25 | OpenAlex API 服务端代码 | 可读懂过滤/排序语义的权威实现 |
| ourresearch/openalex-official | 35 | MIT | 2026-09-19 | 官方 PDF/TEI 批量下载工具 | OA 全文批量获取的官方途径（按次计费，保留原版权）|
| ourresearch/openalex-walden | 22 | MIT | 2026-09-26 | OpenAlex 数据管线（Walden） | 了解字段来源与去重逻辑 |
| ourresearch/openalex-mcp-server | 0 | MIT | 2026-09-21 | 官方 MCP server | 可作为 agent 工具链参考 |
| ourresearch/oadoi | 398 | MIT | 2026-09-18 | Unpaywall 后端历史代码 | OA 检测逻辑参考 |
| opencitations/oc_meta | 9 | ISC | 2026-09-22 | OpenCitations Meta 构建代码 | 引文元数据去重参考 |
| ror-community/ror-api | 67 | MIT | 2026-09-25 | ROR API（可本地 Docker 部署） | 机构归一可自托管 |
| inspirehep/rest-api-doc | 59 | CC-BY-SA-4.0 | 2025-07-14 | INSPIRE API 文档 | 限速/许可权威来源 [S92] |
| adsabs/adsabs-dev-api | 202 | — | 2025-04-21 | ADS API 文档与示例 | token/限速说明 [S93] |

### 2.8 与 v1 勘察的漂移汇总（⚡）

| # | 源 | v1 口径（日期） | 本次实测/文档（2026-09-26） | 对 v2 的影响 |
|---|---|---|---|---|
| 1 | Crossref | polite 10 req/s、并发 3，不区分请求类（2026-07-22）[S106] | 按池 × 请求类分桶：public 单条 5/s、array 1/s；`/journals/{issn}/works` 归 single 池 [S4][S5] | 限速器按请求类分桶，读 `x-api-pool` 头；枚举走 `/journals/{issn}/works` |
| 2 | dblp | `Crawl-delay: 4`，允许 `/db`、`/xml`（2026-07-22）[S107] | 三个主机均 `User-agent: * Disallow: /`；只剩 sparql（`Crawl-delay: 10`）和 DROPS 快照 [S51][S52][S53] | v1 在线路径停用，改走离线快照 |
| 3 | OpenAlex | 计费制上线，快照月度（2026-07-20）[S106][S107] | 快照改季度；`corpus=` 参数；语义搜索、PDF/TEI 下载；Walden 重写 [S16][S21][S15][S20] | 本地快照更新节奏改为季度，并用 API 补新 |
| 4 | Unpaywall | 独立服务，快照停发（2026-07-20）[S107] | 已迁入 OpenAlex 数据库，只保留 DOI 查询/扩展/Data Feed [S24] | 降为兼容层 |
| 5 | CORE | 未认证 100/日·10/分，注册 1,000/日·25/分，更高档 5,000/日（2026-07-22）[S107] | 口径细化：5,000/日档为"非会员机构的学术用户"（10/分），未认证不提供全文，会员约 200k/日 [S33] | 以学术档注册；全文取回必须带 key |
| 6 | Semantic Scholar | 匿名返回 404（2026-07-22）[S106] | 匿名返回 404 或 429；Datasets 周更、有 diffs 端点 [S29][S32] | 必须申请 key；嵌入走数据集 |
| 7 | Crossref Event Data | —（v1 未用） | 2026-04-23 停用 [S7] | 热度信号不能依赖它 |
| 8 | PMC | —（v1 未用） | 旧 FTP 数据集 2026-08 下线，改用 Cloud Service [S49] | 新 adapter 直接对接云服务 |

## 3. 对 v2 设计的启示

1. **按职能分五层组织来源，每个源都用机读的能力描述接入路由器**：
   - 权威层：Crossref、DataCite；
   - 广度层：OpenAlex；
   - 信号层：S2 嵌入与推荐、OpenCitations 引文、平台内交互；
   - 学科层：Europe PMC、PubMed、INSPIRE、zbMATH、RePEc、DBLP 快照；
   - 全文层：OpenAlex content、CORE、PMC、各仓储，以及用户私有授权通道。

   每个源以 `SourceCapability` 声明可下推谓词、排序键、增量游标、分桶限速、计费模型、许可与 robots 策略（§2.4.2 伪结构）。v1 的 `SourceAdapter` + capabilities 可以扩展成这套描述。
2. **本地优先，用 bulk 快照建"学术知识底座"，API 只负责增量和长尾**。可免费或开放获取的快照：OpenAlex 季度快照（JSONL 约 745 GB，CC0）、Crossref 年度文件（208 GB）、PubMed baseline + 日更、DBLP 月度 XML（1.02 GB，CC0）、OpenCitations dump（CC0）、ROR/DataCite/DOAJ（CC0，其中 DOAJ 需申请）、S2 Datasets（需 key，ODC-BY）、OpenAIRE dump（CC-BY）。这样一次性解决三件事：单位查询成本（OpenAlex 搜索每千次 $1）、稳定性（不受 429 或配额影响），以及合规（少打在线 API）。核验补充：bulk 也要逐主机过 robots，PubMed/PMC 所在的 `ftp.ncbi.nlm.nih.gov` 与 Europe PMC 所在的 `ftp.ebi.ac.uk` robots 都是全禁，须在 Q1 的 ADR 中登记依据后再用；PMC Cloud Service 自 2026-08 起只提供逐篇文件，不再有批量包 [S112][S113][S123]。
3. **增量策略按源定制，并统一抽象为"游标 + 重叠窗口 + 标识符去重"**（v1 design/09 的 watermark 思路可以推广）：
   - Crossref：`/journals/{issn}/works?filter=from-index-date`，[LIVE] 归 single 池（含 cursor，核验复测一致）；核验补充：index-date 窗口会被重建索引放大约百倍（§2.2.1 增量行），"新论文"判定应叠加 `from-created-date` 或本地 DOI 去重；
   - OpenAlex：免费档只能按 `publication_date` 滑窗，**捕获不到元数据更新**，需要用季度快照对账；
   - S2：Datasets diffs；
   - PubMed：updatefiles 日更；
   - OAI-PMH 源：Zenodo 的 resumptionToken 2 分钟过期，必须立即续拉，不能排队；
   - DBLP：DROPS 月度快照。
4. **路由器采用"能力匹配 + 代价模型 + 许可约束"**。把组合查询拆成谓词，按"谓词覆盖度 × 召回 × 成本 × 时效 × 许可"给候选源打分，未能下推的谓词在本地过滤；多源 fan-out 采用并行加对冲请求（hedged request）、单源熔断和降级链（§2.4 每行的首选 → 备选 → 兜底）。R8 组合查询优先下推到 OpenAlex filter（AND/OR/NOT/比较 + `group_by`），它是目前下推能力最强的源。
5. **限速必须由响应头驱动，并且在平台全局共享**：
   - 需要读取的头：Crossref `x-api-pool`/`x-rate-limit-*`/`x-concurrency-limit`，OpenAlex `x-ratelimit-*`（含美元额度），CORE、Zenodo、INSPIRE、ADS 的 `X-RateLimit-*`，Lens 的每月额度头。
   - v1 的 `HttpClient.get_bytes` 不暴露响应头，只能用静态限速（[aggregators.md §5.1](../../archive-v1.md#docs-design-adapters-aggregators-md)）；v2 的 HTTP 层要把响应头交给限速器。
   - 多用户平台的令牌桶按"源 × 请求类 × 凭证 × 出口 IP"全局共享，不能按用户各自计。
6. **"不去规避配额"要写成硬约束**：Crossref 并发 1–3/IP，ORCID、OpenCitations、ROR、Zenodo 按 IP 计额，S2、CORE 按 key 计额。平台水平扩展时，禁止用多 IP 或多 key 绕过单源配额，需要更高额度时走付费档或官方申请（OpenAlex Member、S2 合作方、CORE 会员）。
7. **身份与去重以 DOI 为锚，扩展成多标识图**：
   - 标识类型：doi、openalex W/A/S/I、s2 corpusId、pmid、pmcid、arxiv、dblp key/PID、mag、zbMATH id、inspire recid、repec handle、ror、orcid。
   - 刊级元数据不可盲信：[LIVE] Crossref 的 Nature Methods ISSN 挂在 Nature Chemical Biology 刊记录下。venue 须用 ISSN-L、OpenAlex source ID、container-title 三方校验。
   - 会议不依赖 OpenAlex source（[LIVE] NeurIPS/ICLR 实体碎片化），沿用 v1 VenueSpec，并以 DBLP venue key 作对账。
8. **主题体系以 OpenAlex Topics 为跨学科主干**（4 domains / 26 fields / 252 subfields / 4,516 topics），挂接学科分类：MSC2020（zbMATH）、MeSH（PubMed/Europe PMC/OpenAlex `mesh`）、JEL（RePEc）、arXiv 类目（L1）。这张"主题图"有两个用途：①路由，决定某个 topic 该去哪个学科源；②推荐，作为用户兴趣向量的可解释层，也是"双向匹配"中论文侧的结构化画像。
9. **摘要要有分层策略**：Crossref 摘要覆盖按出版方差异极大（[LIVE] 本次样本中 Elsevier、APA、IEEE、AOM、UChicago、T&F 为 0%，2025 年全量只有 55.2%），OpenAlex 出于法律原因只给倒排索引，S2 abstracts 数据集为 ODC-BY。建议：
   - **检索和嵌入**：可使用合法取得的摘要文本（是否算合理使用仍需法律评估，见 Q2）；
   - **卡片展示**：优先顺序为开放许可摘要原文 > S2 TLDR（ODC-BY）> 首句或片段 + 原文链接；
   - **溯源**：每条摘要记录来源和版权属性。
10. **OA 全文共享要逐篇判定许可**。只有许可证明确允许再分发的全文（CC BY、CC0 等）可以在平台缓存并对多用户开放，许可依据取 OpenAlex `best_oa_location.license`、Unpaywall、Europe PMC。bronze 或许可不明的 OA 只存链接。auth-gated 全文只能由用户用自己的凭证取回并私有存放，不进入任何共享缓存或推荐特征的原文层（这是 v2 多用户红线）。
11. **推荐冷启动可以直接利用开放嵌入和本人授权数据**：
   - 论文侧：S2 SPECTER2 嵌入（1.2 亿，Apache-2.0）作为免训练向量起点；
   - 用户侧：ORCID 本人作品（OAuth 授权）、用户导入的 BibTeX/Zotero 条目、关注的 venue 与 Topics；
   - S2 Recommendations 的正负样本接口天然对应"赞/踩"，但每个 key 只有 1 RPS，只能作离线或批量基线，不能给多用户实时调用。
12. **热度信号的外部来源在收缩**：Crossref Event Data 已停用，DataCite Event Data 在收缩。可用的外部信号只剩 OpenAlex `counts_by_year`、OpenCitations 新增引用、预印本版本更新，其余靠平台内交互。社交媒体信号不属于 L2 范围。
13. **合规信息要落到数据层**：每条记录带 provenance（来源、许可、获取方式、能否跨用户展示、能否用于商业化）。在此基础上：
   - ORCID Public API 仅限非商业，平台一旦收费就要成为 Member；
   - Lens、Scopus、WoS、Dimensions 只能以"用户自带凭证 + 私有富化"方式接入；
   - BASE、CNKI、万方、维普、Google Scholar 不做自动化。
14. **robots 解释规则需要一条 ADR**（按 AGENTS.md，以新 ADR 点名并修订 D-014）：
   - (a) 网站主机的 robots 一律遵守；
   - (b) 运营方提供了 robots 允许的机器通道时，只走该通道（dblp → sparql/DROPS，OSF → Crossref 前缀，Zenodo → OAI-PMH）；
   - (c) 专用 API 主机 robots 全禁、但运营方文档明确邀请程序化访问的（NCBI E-utilities、ORCID、HAL API；核验补充：bulk 主机 `ftp.ncbi.nlm.nih.gov`、`ftp.ebi.ac.uk` 与 CiNii Research 的 `/opensearch` 也属此类），在 ADR 中逐源登记文档依据和日期，并优先用 bulk；bulk 主机本身也可能全禁，不能默认"走 bulk 就合规"；
   - (d) 任何挑战门（Anubis、ALTCHA、Cloudflare、Bunny、reCAPTCHA）一律停止，不求解。
15. **"先读 robots 再请求"要做进基础设施**。本次调研就出现了 9 次"先请求、后读 robots"（§1.3.4），说明靠人工纪律不可靠。v2 的 HTTP 层应内置 robots 缓存、按路径判定的闸门（v1 D-026 有路径级读法先例）和挑战门检测（基于响应内容，参考 v1 的 CF-403 判定契约）。
16. **成本边界**：OpenAlex 免费 key 每天 $1，约等于 1 万次列表或 1,000 次搜索；S2 每个 key 最多每天 86,400 次调用。多用户"即时检索"必须主要由本地索引承接，外部 API 只做补充；OpenAlex Member（$5,000/年，$20/天）是自然的第一个升级点。
17. **中文与区域只做"用户导入 + 元数据旁路"**：CNKI、万方、维普的题录由用户在机构授权下手动导出后导入；Crossref/OpenAlex 已收录的中文 DOI 期刊走常规通道；J-STAGE 与 SciELO 作为 P2 适配器。
18. **v1 资产的迁移路径**：
   - `crossref`、`openalex`、`s2`、`unpaywall`、`repec` 可平移为 v2 适配器（Crossref 限速改为头驱动并区分池）；
   - `dblp` 改造成 DROPS 快照加 SPARQL 通道，原 `/db/**` 在线路径废止；
   - `core` 按 v1 存档设计落地；
   - 新增 `europe_pmc`、`pubmed`、`opencitations`、`doaj`、`ror`、`orcid`（OAuth）、`inspire_hep`、`zbmath_open`。
19. **建立跨源数据质量治理**。本次实测已发现四类问题：
   - 被引数不一致：OpenCitations 9,262 对 OpenAlex 10,801；
   - OpenAlex OA 误判：JMLR 1%、PVLDB 18%；
   - Crossref 刊记录 ISSN 冲突；
   - OpenAlex 会议实体碎片化。

   v1 D-021 的字段级来源优先级应扩展成"字段 × 学科 × 源"的可信度矩阵，在 UI 中可追溯（卡片上的"来源"徽标）。

## 4. 未决问题与风险

| # | 问题/风险 | 影响 | 建议处置（交设计阶段裁决） |
|---|---|---|---|
| Q1 | **API 主机 robots 全禁与官方文档邀请程序化访问相冲突**：E-utilities、`pub.orcid.org`、`api.osf.io`、`api.base-search.net` 都是 `Disallow: /`；HAL API 禁 `/search/`、`/oai/`；Zenodo 禁 `/api` [S47][S57][S70][S38][S72][S69]。核验补充：PubMed/PMC 的 bulk 主机 `ftp.ncbi.nlm.nih.gov` 与 Europe PMC 的 bulk 主机 `ftp.ebi.ac.uk` 同样 `Disallow: /`[S113][S123]；CiNii Research 的 robots 禁 `/opensearch`[S119]；Europe PMC 所在 `www.ebi.ac.uk` 对通用 UA `Crawl-Delay: 10`[S117] | 决定 PubMed、ORCID、HAL 等 P0/P1 源能否在线调用，**也决定 PubMed bulk 能否下载** | 出 ADR（§3 第 14 条 建议规则）；ADR 之前只用 robots 放行的 bulk 与官方指定的替代通道（NCBI bulk 不在其列） |
| Q2 | **摘要展示的法律边界**：Crossref 声明摘要保留版权；OpenAlex 因法律原因不提供明文；PubMed 声明部分摘要受版权保护；S2 abstracts 为 ODC-BY [S8][S23][S48][S29] | 卡片 UI 能否直接显示摘要全文；基于受版权保护的摘要生成 AI 摘要是否构成衍生作品 | 法律评估；默认展示"开放许可摘要 > TLDR > 片段 + 链接"，按来源打标 |
| Q3 | **平台是否商业化**会改变多个源的可用性：ORCID Public API 仅限非商业 [S56]；J-STAGE 商业用途需申请 [S102]；CORE 商用需同意 T&C [S34]；S2 许可未明文允许或禁止商用，且不得再分发 API（核验更正：原文"S2 允许商用"无条款依据）[S28]；Lens 只提供机构订阅 [S85]；zbMATH Open 为 CC BY-SA，Open policy finder 为 CC BY-NC-ND（核验补充）[S114][S116] | 来源名录的优先级与许可列 | 在需求层先明确商业属性，之后按属性重排优先级 |
| Q4 | **Crossref polite 池的实际数值未实测**（本次刻意不使用用户邮箱）；`/journals/{issn}/works` 归 single 池属于实测行为，官方未承诺 [S4][S5] | 期刊增量的吞吐估算 | 用平台运营者专用联系邮箱复测；限速器必须头驱动，禁止硬编码 |
| Q5 | **S2 key 的获取与额度**：匿名实测不可用，有 key 只有 1 RPS [S27] | 嵌入与推荐冷启动的可行性 | 尽早申请 key；嵌入走 Datasets 离线下载（需 key），不走在线 API |
| Q6 | **OpenAlex 预算与新鲜度**：免费 key 每天 $1；`from_updated_date` 需付费；公共快照改为季度 [S16][S18] | 近实时追新、元数据更新捕获能力 | 先用免费档加季度快照，量化缺口后再决定是否升 Member+（$10,000/年，含日同步） |
| Q7 | **来源可用性波动**：Fatcat 不可达；ChinaXiv 的 robots 返回维护页；中国科技论文在线全站维护 [S80][S100][S101] | 相应源的可用性 | 纳入 canary 周期复核（v1 已有 canary 框架） |
| Q8 | **BASE 授权**：未登记 IP 被拒，网站附法律声明 [S38] | 是否值得向 Bielefeld 申请授权（覆盖与 CORE/OpenAIRE 高度重叠） | 默认不申请；若出现 CORE/OpenAlex 覆盖不到的仓储需求再评估 |
| Q9 | **未能核验的细节**：Unpaywall 当前限速（第三方资料一致为 10 万次/日，官方页为 JS 渲染未读到）、Europe PMC 限速数值、OpenAIRE 实际匿名限额（文档 60/h，核验复测匿名头仍为 `x-ratelimit-limit: 7199`）、Crossref polite 列表池名称。**核验阶段已解决**：NCBI 带 key 为 10/s [S111]；zbMATH 数据为 CC BY-SA [S114]；HAL 元数据为 CC0 [S115]；ORCID 公共数据文件为年度发布、CC0（figshare）[S120] | 限速与许可列的准确性 | 实现前逐项复核（adapter 开工门禁沿用 v1 的"勘察复核前置"） |
| Q10 | **OpenAlex 分类与 OA 判定有误差**：JMLR 被判 OA 1%、PVLDB 18%，与 v1 核验不符；Topics 为机器分类 | 推荐的主题特征、"只看 OA"过滤 | OA 状态由多源投票（OpenAlex + Unpaywall + DOAJ + venue 白名单）；Topics 用用户反馈校正 |
| Q11 | **按 IP 计额与多实例部署的冲突**：Crossref 并发 1–3/IP，ORCID、OpenCitations、ROR 按 IP 计额 | 平台水平扩展时单出口 IP 成为瓶颈 | 集中式抓取服务 + 全局令牌桶；需要更高额度时走付费或官方申请，不用多 IP 规避 |
| Q12 | **存储与处理成本**：OpenAlex JSONL 约 745 GB 或 Parquet 约 770 GB，Crossref 208 GB 压缩，另加 PubMed baseline、S2 datasets 等 [S16][S6] | 基础设施预算 | 设计阶段做容量规划；先按学科子集导入（`topics`/`source` 过滤） |
| Q13 | **接口生命周期**：DataCite GraphQL 2027-07 弃用；PMC 旧 FTP 已下线；Crossref Event Data 已停；OpenAlex `include_xpac` 已被 `corpus=` 取代 [S59][S49][S7][S21] | adapter 维护成本 | 名录中增加"接口弃用日期"字段，由 canary 跟踪 |
| Q14 | **中文学术覆盖不足**：CNKI、万方、维普没有合规的自动化通道 [S97][S98][S99] | 中文用户的核心需求 | 产品上明示"用户导入"模式；评估 Crossref/OpenAlex 对中文 DOI 期刊的实际覆盖（本次未测） |
| Q15 | **本次调研自身的合规瑕疵**：9 次"先请求、后读 robots"（§1.3.4）；核验补充：原稿对 `ftp.ncbi.nlm.nih.gov` 的 README/readme 实测（[S48][S49]）和对 `ftp.ebi.ac.uk` 目录的实测（[S46]）都发生在 robots 全禁的主机上，且原稿没有读取这两个主机的 robots；核验阶段自身也有 1 次同类瑕疵（见文末核验记录） | 流程风险 | 在 v2 勘察流程与 HTTP 层同时强制 robots-first（§3 第 15 条），脚本内"读 robots → 判定 → 再请求"必须串行，不能在同一条命令里并发发出 |

## 5. 参考来源

> 访问/核验日期除特别注明外均为 **2026-09-26**。[DOCS] = 官方文档/公告；[LIVE] = 本次 HTTP 实测（响应头、计数、robots.txt）；[3P] = 第三方材料，仅作佐证。

**Crossref**
- [S1] [DOCS] Crossref, *Access and authentication*（public 5/1、polite 10/3、Plus 150）— https://www.crossref.org/documentation/retrieve-metadata/rest-api/access-and-authentication/
- [S2] [DOCS] Crossref blog, *Announcing changes to REST API rate limits*（2025-11-05，2025-12-01 生效）— https://www.crossref.org/blog/announcing-changes-to-rest-api-rate-limits/
- [S3] [DOCS] Crossref community, *Updates to REST API rate limits*（2025-12-02）— https://community.crossref.org/t/updates-to-rest-api-rate-limits/14872
- [S4] [DOCS] Crossref community, *Refining REST API limits for improved stability and reliability*（2026-07-21）— https://community.crossref.org/t/refining-rest-api-limits-for-improved-stability-and-reliability/16137
- [S5] [LIVE] Crossref REST API：`https://api.crossref.org/works?rows=0`、`/works/10.1371/journal.pmed.0020124`、`/journals/{issn}`、`/journals/{issn}/works`、`/works?filter=…`、`/members/78/works`（响应头 `x-api-pool`、`x-rate-limit-*`、`x-concurrency-limit` 与 `total-results`）
- [S6] [DOCS] Crossref blog, *2026 public data file now available*（2026-03-17）— https://www.crossref.org/blog/2026-public-data-file-now-available/
- [S7] [DOCS] Crossref blog, *Strengthening support for data citations and saying goodbye to Event Data*（2026-03-24）— https://www.crossref.org/blog/strengthening-support-for-data-citations-and-saying-goodbye-to-event-data/
- [S8] [DOCS] Crossref, *Metadata Retrieval*（Licensing 段：事实为 CC0 口径，摘要版权保留）— https://www.crossref.org/documentation/retrieve-metadata/ （原 license 信息页 https://www.crossref.org/documentation/retrieve-metadata/rest-api/rest-api-metadata-license-information/ 本日返回 404）
- [S9] [DOCS] Crossref, *REST API* — https://www.crossref.org/documentation/retrieve-metadata/rest-api/
- [S10] [DOCS] Crossref blog, *Retraction Watch retractions now in the Crossref API*（2025-01-29）— https://www.crossref.org/blog/retraction-watch-retractions-now-in-the-crossref-api/
- [S11] [DOCS] Initiative for Open Abstracts — https://i4oa.org/
- [S12] [3P] hunter-heidenreich/academic-tools-mcp PR #141（2026-09-18，polite 池响应头观测）— https://github.com/hunter-heidenreich/academic-tools-mcp/pull/141

**OpenAlex / Unpaywall**
- [S13] [DOCS] OpenAlex Help, *Example costs* — https://help.openalex.org/access/example-costs/
- [S14] [DOCS] OpenAlex Help, *Authentication*（developers.openalex.org 301 跳转至此）— https://help.openalex.org/api-reference/authentication
- [S15] [DOCS] OpenAlex blog, *New Features and Usage-Based Pricing*（2026-02-24）— https://blog.openalex.org/openalex-api-new-features-and-usage-based-pricing/
- [S16] [DOCS] OpenAlex Help, *Snapshot* — https://help.openalex.org/access/snapshot/
- [S17] [DOCS] OpenAlex Help, *Fulltext* — https://help.openalex.org/access/fulltext/
- [S18] [DOCS] OpenAlex Help, *Pricing*（页面更新于 2026-08-11）— https://help.openalex.org/access/pricing/
- [S19] [DOCS] AWS Registry of Open Data, *OpenAlex*（License: CC0）— https://registry.opendata.aws/openalex/
- [S20] [DOCS] OpenAlex blog, *OpenAlex rewrite ("Walden") launch!*（2025-11-03）— https://blog.openalex.org/openalex-rewrite-walden-launch/
- [S21] [DOCS] OpenAlex Help, *Deprecations*（页面更新于 2026-09-22）— https://help.openalex.org/api/deprecations/
- [S22] [DOCS] OpenAlex Help, *LLM Quick Reference* — https://help.openalex.org/api/llm-quick-reference/
- [S23] [DOCS] OpenAlex Help, *Works attributes*（`abstract_inverted_index` 的法律说明）— https://help.openalex.org/data/works/attributes/
- [S24] [DOCS] OpenAlex Help, *Unpaywall* — https://help.openalex.org/access/unpaywall/
- [S25] [LIVE] OpenAlex API：`https://api.openalex.org/works?filter=…`（含 `corpus=all`、`from_created_date`/`from_updated_date` 付费拦截、`group_by=primary_topic.field.id`）、`/works/doi:10.1371/journal.pmed.0020124`、`/sources/issn:{issn}`、`/domains`、`/fields`、`/subfields`、`/topics`、`/keywords`（响应头 `x-ratelimit-*` 与 `meta.cost_usd`）
- [S39] [LIVE] Unpaywall API：`https://api.unpaywall.org/`（version 1.3.0）、`/v2/{doi}`（缺 email 返回 422）

**Semantic Scholar**
- [S27] [DOCS] Semantic Scholar, *API* 产品页 — https://www.semanticscholar.org/product/api
- [S28] [DOCS] Semantic Scholar, *API License Agreement*（2023-05-17）— https://www.semanticscholar.org/product/api/license
- [S29] [LIVE] S2 Datasets `release/latest`（2026-09-22 release，含各数据集 README 与许可）— https://api.semanticscholar.org/datasets/v1/release/latest
- [S30] [LIVE] S2 Recommendations swagger — https://api.semanticscholar.org/recommendations/v1/swagger.json
- [S31] [LIVE] S2 Graph swagger — https://api.semanticscholar.org/graph/v1/swagger.json
- [S32] [LIVE] S2 Datasets swagger（diffs 端点）— https://api.semanticscholar.org/datasets/v1/swagger.json

**CORE / BASE / DOAJ / OpenAIRE / OpenCitations**
- [S33] [DOCS] CORE API v3 文档（Rate limits 段，文本内嵌于页面 spec）— https://api.core.ac.uk/docs/v3
- [S34] [DOCS] CORE, *API* 服务页 — https://core.ac.uk/services/api
- [S35] [DOCS] CORE, *Dataset* 服务页 — https://core.ac.uk/services/dataset
- [S36] [DOCS] CORE, *About* — https://core.ac.uk/about
- [S37] [LIVE] CORE robots — https://core.ac.uk/robots.txt ；https://api.core.ac.uk/robots.txt
- [S38] [LIVE] BASE：https://www.base-search.net/robots.txt （更新于 2025-09-16）；https://api.base-search.net/robots.txt ；`https://api.base-search.net/cgi-bin/BaseHttpSearchInterface.fcgi`（拒绝访问）；https://www.base-search.net/about/en/about_develop.php （Anubis 挑战）
- [S40] [DOCS] DOAJ API v4 文档 — https://doaj.org/api/v4/docs
- [S41] [DOCS] DOAJ, *Public data dump* — https://doaj.org/docs/public-data-dump/
- [S42] [DOCS] DOAJ, *Terms and conditions* — https://doaj.org/terms/
- [S43] [LIVE] DOAJ API：`https://doaj.org/api/search/journals/*`、`/api/search/articles/bibjson.year:2026`、`/api/search/journals/issn:2050-084X`；https://doaj.org/robots.txt
- [S74] [DOCS] OpenAIRE Graph, *Terms of use*（文档 v11.4.0）— https://graph.openaire.eu/docs/apis/terms/
- [S75] [DOCS] OpenAIRE Graph, *Full graph dataset* — https://graph.openaire.eu/docs/downloads/full-graph/
- [S76] [LIVE] OpenAIRE Graph API — https://api.openaire.eu/graph/v1/researchProducts?pageSize=1&type=publication
- [S77] [DOCS/LIVE] OpenCitations Index REST API v2（v2.2.0）— https://api.opencitations.net/index/v2 ；实测 `/citation-count/doi:10.1371/journal.pmed.0020124`
- [S78] [DOCS] OpenCitations downloads — https://download.opencitations.net/
- [S79] [DOCS] OpenCitations, *Governance*（License：CC0）— https://opencitations.net/governance/

**生物医学**
- [S44] [LIVE] Europe PMC REST OpenAPI — https://www.ebi.ac.uk/europepmc/webservices/rest/v3/api-docs （官网 https://europepmc.org/RestfulWebService 本日 Cloudflare 挑战 403）
- [S45] [LIVE] Europe PMC search — https://www.ebi.ac.uk/europepmc/webservices/rest/search （`query=*`、`OPEN_ACCESS:y`、`SRC:PPR`）
- [S46] [LIVE] Europe PMC FTP — https://ftp.ebi.ac.uk/pub/databases/pmc/
- [S47] [LIVE] NCBI E-utilities：`https://eutils.ncbi.nlm.nih.gov/entrez/eutils/einfo.fcgi?db=pubmed&retmode=json`、`esearch.fcgi`；https://eutils.ncbi.nlm.nih.gov/robots.txt
- [S48] [LIVE] PubMed FTP README（2026-01-30）— https://ftp.ncbi.nlm.nih.gov/pubmed/README.txt ；目录 https://ftp.ncbi.nlm.nih.gov/pubmed/baseline/ 、https://ftp.ncbi.nlm.nih.gov/pubmed/updatefiles/
- [S49] [LIVE] PMC FTP readme（2026-08-25）— https://ftp.ncbi.nlm.nih.gov/pub/pmc/readme.txt
- [S50] [DOCS] NCBI, *E-utilities usage guidelines* — https://www.ncbi.nlm.nih.gov/books/NBK25497/ （本日 reCAPTCHA 拦截，未读到正文）

**dblp / 身份与注册表 / 仓储**
- [S51] [LIVE] dblp robots — https://dblp.org/robots.txt ；https://dblp.uni-trier.de/robots.txt ；https://dblp.dagstuhl.de/robots.txt
- [S52] [LIVE] dblp SPARQL — https://sparql.dblp.org/robots.txt ；https://sparql.dblp.org/download/
- [S53] [LIVE] dblp 月度快照 — https://doi.org/10.4230/dblp.xml.2026-09-01 → https://drops.dagstuhl.de/entities/artifact/10.4230/dblp.xml.2026-09-01
- [S54] [LIVE] DROPS robots — https://drops.dagstuhl.de/robots.txt
- [S55] [DOCS] ORCID, *What are the API usage quotas and limits?*（2022-11-14）— https://info.orcid.org/ufaqs/what-are-the-api-limits/
- [S56] [DOCS] ORCID, *Public APIs Terms of Service*（最后更新 2024-10-23）— https://info.orcid.org/public-client-terms-of-service/
- [S57] [LIVE] ORCID robots — https://pub.orcid.org/robots.txt
- [S58] [DOCS] DataCite, *API Rate Limits* — https://support.datacite.org/docs/rate-limit
- [S59] [DOCS] DataCite, *GraphQL API Deprecation*（页面更新 2026-08-17）— https://support.datacite.org/docs/datacite-graphql-api-deprecation.md
- [S60] [DOCS] DataCite, *Public Data File* — https://support.datacite.org/docs/datacite-public-data-file.md
- [S61] [DOCS] DataCite, *Monthly Data File* — https://support.datacite.org/docs/datacite-monthly-data-file.md
- [S62] [DOCS] DataCite, *Data File Use Policy*（CC0）— https://support.datacite.org/docs/datacite-data-file-use-policy.md
- [S63] [DOCS] DataCite, *Event Data Changes* — https://support.datacite.org/docs/datacite-event-data-changes.md
- [S64] [LIVE] DataCite REST — https://api.datacite.org/dois?page[size]=1
- [S65] [DOCS] ROR, *REST API* — https://ror.readme.io/docs/rest-api
- [S66] [DOCS] ROR, *Register for a client ID* — https://ror.readme.io/docs/client-id
- [S67] [DOCS] ROR, *Data dump* — https://ror.readme.io/docs/data-dump
- [S68] [DOCS] Zenodo, *Developers* — https://developers.zenodo.org/
- [S69] [LIVE] Zenodo — https://zenodo.org/robots.txt ；`https://zenodo.org/api/records?q=resource_type.type:publication&size=1`
- [S70] [LIVE] OSF — `https://api.osf.io/v2/preprint_providers/`、`https://api.osf.io/v2/preprints/`；https://api.osf.io/robots.txt ；https://osf.io/robots.txt ；https://share.osf.io/robots.txt
- [S71] [LIVE] Crossref member 15934（Center for Open Science）— https://api.crossref.org/members/15934 ；`https://api.crossref.org/prefixes/10.31234/works?rows=0&filter=type:posted-content`
- [S72] [DOCS/LIVE] HAL — https://api.archives-ouvertes.fr/docs ；https://api.archives-ouvertes.fr/robots.txt ；https://hal.science/robots
- [S73] [LIVE] HAL search — `https://api.archives-ouvertes.fr/search/?q=*:*&rows=0&wt=json`（及 `fq=submitType_s:file`）
- [S80] [LIVE] Fatcat / IA Scholar — https://fatcat.wiki/ 、https://api.fatcat.wiki/ 、https://guide.fatcat.wiki/ （TCP 连接超时）；https://scholar.archive.org/robots.txt ；`https://scholar.archive.org/search?q=…`（302 → /verify）
- [S81] [DOCS] Wikidata, *WDQS graph split* — https://www.wikidata.org/wiki/Wikidata:SPARQL_query_service/WDQS_graph_split
- [S82] [DOCS] MediaWiki, *Wikidata Query Service/User Manual* — https://www.mediawiki.org/wiki/Wikidata_Query_Service/User_Manual
- [S83] [DOCS] Wikidata, *Licensing* — https://www.wikidata.org/wiki/Wikidata:Licensing

**商业/机构库与排除项**
- [S84] [DOCS] Lens API 文档（2.19.3）— https://docs.api.lens.org/ ；https://docs.api.lens.org/getting-started.html
- [S85] [DOCS] Lens, *Scholarly API Terms of Use*（v2026.06.01；curl 403，经 WebFetch 读取）— https://about.lens.org/lens-scholarly-api-terms-of-use/
- [S86] [DOCS] Dimensions, *Scientometric research* — https://www.dimensions.ai/scientometric-research/
- [S87] [DOCS] Elsevier Developer Portal, *API Key Settings* — https://dev.elsevier.com/api_key_settings.html
- [S88] [DOCS] Elsevier Developer Portal, *Policy* — https://dev.elsevier.com/policy.html
- [S89] [DOCS] Clarivate, *Web of Science Starter API* — https://developer.clarivate.com/apis/wos-starter
- [S90] [LIVE] Google Scholar robots — https://scholar.google.com/robots.txt
- [S91] [DOCS] Microsoft Research, *Next Steps for Microsoft Academic – Expanding into New Horizons*（2021-05-04，2021-06-04 更新）— https://www.microsoft.com/en-us/research/articles/microsoft-academic-to-expand-horizons-with-community-driven-approach/

**学科与区域**
- [S92] [DOCS/LIVE] INSPIRE — https://github.com/inspirehep/rest-api-doc ；`https://inspirehep.net/api/literature?size=1&sort=mostrecent`；https://inspirehep.net/robots.txt
- [S93] [DOCS] NASA ADS — https://github.com/adsabs/adsabs-dev-api
- [S94] [LIVE] zbMATH Open — `https://api.zbmath.org/v1/document/_search?search_string=py%3A2026&page=0&results_per_page=1`；https://zbmath.org/robots.txt （Cloudflare 挑战）；https://static.zbmath.org/legal/api-terms-and-conditions.html （403）
- [S95] [LIVE] MathSciNet robots — https://mathscinet.ams.org/robots.txt
- [S96] [DOCS/LIVE] EconBiz API — https://api.econbiz.de/doc ；`https://api.econbiz.de/v1/search?q=monetary+policy&size=1`
- [S97] [LIVE] CNKI — https://kns.cnki.net/robots.txt ；https://www.cnki.net/robots.txt （404）
- [S98] [LIVE] 万方 — https://www.wanfangdata.com.cn/robots.txt （404）；https://s.wanfangdata.com.cn/robots.txt （WAF）
- [S99] [LIVE] 维普 — https://www.cqvip.com/robots.txt ；https://qikan.cqvip.com/robots.txt
- [S100] [LIVE] ChinaXiv — https://chinaxiv.org/ ；https://chinaxiv.org/robots.txt （403 维护页）
- [S101] [LIVE] 中国科技论文在线 — https://www.paper.edu.cn/
- [S102] [DOCS] J-STAGE WebAPI — https://www.jstage.jst.go.jp/static/pages/JstageServices/TAB3/-char/en
- [S103] [LIVE] J-STAGE — `https://api.jstage.jst.go.jp/searchapi/do?service=3&keyword=economics&pubyearfrom=2026&count=1`；https://www.jstage.jst.go.jp/robots.txt
- [S104] [LIVE] SciELO — `https://articlemeta.scielo.org/api/v1/article/identifiers/?collection=scl&limit=1`；https://www.scielo.org/robots.txt ；https://search.scielo.org/robots.txt （Bunny Shield）
- [S105] [LIVE] Redalyc — https://www.redalyc.org/robots.txt （403）

**v1 基线与 GitHub**
- [S106] v1 勘察：[research/site-survey/metadata-apis.md](../../archive-v1.md#docs-research-site-survey-metadata-apis-md)（2026-07-20/22）
- [S107] v1 勘察：[research/site-survey/aggregators-unpaywall-dblp-core.md](../../archive-v1.md#docs-research-site-survey-aggregators-unpaywall-dblp-core-md)（2026-07-20/22）
- [S108] v1 详设：[design/adapters/aggregators.md](../../archive-v1.md#docs-design-adapters-aggregators-md)
- [S109] v1 ADR：[plan/decision-log.md](../../plan/decision-log.md)（D-005、D-013、D-014、D-021、D-026、D-035、D-037）；v1 勘察 [research/site-survey/repec.md](../../archive-v1.md#docs-research-site-survey-repec-md)；v1 目录 [catalog/publishers-platforms.md](../../archive-v1.md#docs-catalog-publishers-platforms-md)、[catalog/ai-ml-journals.md](../../archive-v1.md#docs-catalog-ai-ml-journals-md)
- [S110] [LIVE] GitHub REST（`gh api repos/{owner}/{repo}`）：J535D165/pyalex、sckott/habanero、fabiobatalha/crossrefapi、danielnsilva/semanticscholar、allenai/s2-folks、allenai/SPECTER2、ourresearch/openalex-elastic-api、ourresearch/openalex-official、ourresearch/openalex-walden、ourresearch/openalex-mcp-server、ourresearch/oadoi、opencitations/oc_meta、ror-community/ror-api、inspirehep/rest-api-doc、adsabs/adsabs-dev-api

**核验补充来源（核验阶段新增，访问日期均为 2026-09-26）**
- [S111] [DOCS] NCBI Insights, *New API Keys for the E-utilities*（2017-11-02；无 key 3 次/秒，有 key 10 次/秒，2018-05-01 起执行）— https://ncbiinsights.ncbi.nlm.nih.gov/2017/11/02/new-api-keys-for-the-e-utilities/
- [S112] [DOCS] NCBI Insights, *Changes to PMC Article Dataset Distribution Services Coming in 2026*（2026-02-12）— https://ncbiinsights.ncbi.nlm.nih.gov/2026/02/12/pmc-article-dataset-distribution-services/
- [S113] [LIVE] NCBI FTP 主机 robots（`User-agent: * / Disallow: /`）— https://ftp.ncbi.nlm.nih.gov/robots.txt
- [S114] [DOCS/LIVE] zbMATH Open API Terms & Conditions（API 与 OAI 主机副本，"All data are allowed to be used under a CC-BY-SA license"）— https://api.zbmath.org/v1/static/terms-and-conditions.html ；https://oai.zbmath.org/static/terms-and-conditions.html ；实测 `https://api.zbmath.org/v1/document/_search?search_string=py%3A2026&page=0&results_per_page=1`
- [S115] [DOCS] HAL 文档, *Les conditions de réutilisation*（元数据自动适用 CC-0；2026-02 起文件必须标注许可）— https://doc.hal.science/en/aspects-juridiques/conditions-de-reutilisation/
- [S116] [DOCS] Jisc Open policy finder, *What's new?*（2026-02-11 新 API；2026-05-07 迁移期延至 2026-07；CC BY-NC-ND 4.0）— https://openpolicyfinder.jisc.ac.uk/whats-new （`https://v2.sherpa.ac.uk/robots.txt` 返回 WAF 403）
- [S117] [LIVE] EMBL-EBI robots（通用 UA `Crawl-Delay: 10`、170 条 Disallow）— https://www.ebi.ac.uk/robots.txt
- [S118] [3P] Europe PMC Developer Forum, *Europe PMC API Usage for Web Service*（Europe PMC 团队 2024-12-11 回复"限额按 IP 计"）— https://groups.google.com/a/ebi.ac.uk/g/epmc-webservices/c/cZLnV1JhCj8
- [S119] [DOCS/LIVE] CiNii Research OpenSearch API 文档 — https://support.nii.ac.jp/en/cir/r_opensearch ；robots — https://cir.nii.ac.jp/robots.txt
- [S120] [DOCS] ORCID, *Working with bulk data*（年度公共数据文件，CC0，figshare）— https://info.orcid.org/documentation/integration-guide/working-with-bulk-data/
- [S121] [LIVE] GitHub REST `gh api repos/internetarchive/fatcat` 与 commits（最近推送 2024-07-31）— https://github.com/internetarchive/fatcat
- [S122] [DOCS] ACM, *ACM is Now Fully Open Access!*（2026-01；页面对本核验 UA 返回 403，内容经检索摘要确认，⚠ 未读到全文）— https://www.acm.org/articles/bulletins/2026/january/acm-open-access
- [S123] [LIVE] EMBL-EBI FTP 主机 robots（`User-agent: * / Disallow: /`）— https://ftp.ebi.ac.uk/robots.txt

## 核验记录

> 核验角色：对抗式事实核验（Verify），核验日期 **2026-09-26**（UTC；本机时区当时为 2026-09-27 凌晨）。做法：从全文挑出承重断言，逐条回到一手来源（官方文档与公告、仓库、API 实测）复核；错误就地修正并标"核验更正"，新增内容标"核验补充"，查不到依据的标"⚠ 未核验"。
> 本节是全文唯一的核验记录节。核验开始时文中没有既有的核验章节，也没有发现前次中断留下的半截核验修改（文件最后修改时间与调研员交稿时间一致）；只顺带修正了原稿 §0 第 2 条与 §2.2.12 中"具名…具名"的重复用词。
> 未在下表列出的其余 [LIVE] 计数与细节（如 INSPIRE、DataCite、Zenodo、HAL 总量，Lens API 版本号，万方/维普 robots 等）沿用调研员原值，未逐条复核。

### 核验过程记录（可复现）

- **检索式（WebSearch）**：① `Semantic Scholar API "commercial" use allowed FAQ license agreement`；② `Unpaywall REST API "100,000 calls per day" email parameter`；③ `NCBI E-utilities API key "10 requests per second" "3 requests per second"`；④ `HAL archives ouvertes métadonnées licence CC0 API réutilisation des métadonnées`；⑤ `Europe PMC REST API rate limit requests per second fair use policy`；⑥ `zbMATH Open API data license CC-BY-SA terms and conditions metadata`；⑦ `fatcat.wiki Internet Archive fatcat shut down OR retired OR offline 2025 2026`；⑧ `OpenAlex XPAC expansion pack works quality excluded by default help.openalex.org`；⑨ `Jisc OpenDOAR API v2 sherpa.ac.uk API key registration Sherpa Romeo API terms`；⑩ `"Open policy finder" Jisc Sherpa Romeo replaced 2025 API`；⑪ `ACM Digital Library fully open access January 2026 transition complete`。检索结果只用于定位官方页面。
- **LIVE 复测**：`curl`，UA 为 `PaperCrawler-verify/0.1 (docs fact-check; low-volume)`，不带 key、邮箱或 cookie；只读 GET，同主机串行。涉及 api.crossref.org（约 25 次，列表类间隔 ≥1.6 s）、api.openalex.org（约 16 次，匿名额度消耗约 $0.004）、api.semanticscholar.org、api.opencitations.net、www.ebi.ac.uk（按其 `Crawl-Delay: 10` 间隔 ≥10 s）、api.openaire.eu、articlemeta.scielo.org、doaj.org、api.zbmath.org、drops.dagstuhl.de、core.ac.uk、doc.hal.science、openpolicyfinder.jisc.ac.uk 等主机，另读取约 30 个主机的 robots.txt。GitHub 数据用 `gh api`。
- **合规自检**：
  - 1 次瑕疵：读取 `ftp.ncbi.nlm.nih.gov/robots.txt` 与请求 `/pub/pmc/readme.txt` 写在同一条命令里，后者在 robots（全禁）判定之前就发出了。此后改为"读 robots → 判定 → 再请求"分步执行，未再访问该主机。
  - `www.paper.edu.cn/robots.txt` 302 到挑战页 `/GE/CC/VALIDATOR`，随后对首页做了 1 次请求（200，维护页），未尝试求解挑战。
  - 遇到 WAF 或 403 的站点（`www.jisc.ac.uk` 新闻页、`v2.sherpa.ac.uk`、`www.acm.org` 公告页，以及 CORE 文档与 J-STAGE 页的 WebFetch）一律停止，改用其他官方页或标 ⚠。

### 核验表

| 断言 | 结论 | 依据来源 URL | 核验日期 |
|---|---|---|---|
| C1 Crossref 2025-11-05 公告、2025-12-01 生效：public 单条 5/s 并发 1、列表 1/s；polite 单条 10/s、列表 3/s、并发 3；2025-12-02 社区帖称暂不能区分请求类型 | 确认 | https://www.crossref.org/blog/announcing-changes-to-rest-api-rate-limits/ ；https://community.crossref.org/t/updates-to-rest-api-rate-limits/14872 | 2026-09-26 |
| C2 Crossref 2026-07-21 正式按请求类型限速，并新增 `x-rate-limit-type` 头 | 修正：日期与数值确认；public 池实测响应中没有 `x-rate-limit-type`（§2.2.1、§2.3.3 已改） | https://community.crossref.org/t/refining-rest-api-limits-for-improved-stability-and-reliability/16137 ；https://api.crossref.org/works?rows=0 | 2026-09-26 |
| C3 [LIVE] `/works?filter=`、`?query.*` 归 `public-array` 1/s；`/works/{doi}`、`/journals/{issn}`、`/journals/{issn}/works`（含 cursor）、`/members/{id}/works` 归 `public-single` 5/s，并发 1 | 确认（逐项复测；另测得 `/prefixes/{p}/works` 也是 `public-single`） | https://api.crossref.org/journals/1548-7091/works?cursor=*&rows=1 ；https://api.crossref.org/works?filter=issn:1548-7091&rows=0 ；https://api.crossref.org/members/78/works?rows=0 | 2026-09-26 |
| C4 Crossref access 页：public 5/并发 1、polite 10/并发 3、Plus 150（无并发上限） | 确认（该页更新于 2025-10-16，不区分请求类，以 C2 为准） | https://www.crossref.org/documentation/retrieve-metadata/rest-api/access-and-authentication/ | 2026-09-26 |
| C5 第三方观测：polite 池名为 `polite-single`/`polite-multi`、10/1s、并发 3 | 修正：只有 `polite-single`（10/1s、并发 3）是实测，`polite-multi` 只是 PR 的测试参数；polite 列表池名称改标 ⚠ | https://github.com/hunter-heidenreich/academic-tools-mcp/pull/141 | 2026-09-26 |
| C6 Crossref Event Data API 于 2026-04-23 停用（博客 2026-03-24），改由数据引用端点承接 | 确认 | https://www.crossref.org/blog/strengthening-support-for-data-citations-and-saying-goodbye-to-event-data/ | 2026-09-26 |
| C7 Crossref 2026 公共数据文件：约 1.8 亿条、压缩 208 GB、2026-03-17 发布 | 确认 | https://www.crossref.org/blog/2026-public-data-file-now-available/ | 2026-09-26 |
| C8 Crossref 许可：书目事实不受版权保护，摘要版权归出版方/作者，自生数据 CC0；Retraction Watch 自 2025-01-29 进入 API | 确认；措辞修正：Retraction Watch 与 Funder Registry 为 CC0（原文"公开"） | https://www.crossref.org/documentation/retrieve-metadata/ ；https://www.crossref.org/blog/retraction-watch-retractions-now-in-the-crossref-api/ | 2026-09-26 |
| C9 I4OA 2020-09 发起时摘要覆盖：全部作品 6.6%、期刊文章 8.3% | 确认 | https://i4oa.org/ | 2026-09-26 |
| C10 Crossref 摘要覆盖：全库 24.2%、2025 年期刊文章 55.2%；Elsevier 2025 年约 104 万篇期刊文章中只有 424 篇带摘要 | 确认（复测 45,190,122/186,990,632；3,660,041/6,635,703；424/1,040,980，差异为当日增长） | https://api.crossref.org/works?rows=0&filter=has-abstract:true ；https://api.crossref.org/members/78/works?rows=0&filter=type:journal-article,from-pub-date:2025-01-01,until-pub-date:2025-12-31,has-abstract:true | 2026-09-26 |
| C11 刊级数据质量：Nature Methods 的 ISSN 挂在 Nature Chemical Biology 刊记录下；PRB 刊记录挂 7 个 ISSN；§2.6 抽查 JASA 0/96/65、Psychological Review 0/0/77、JMLR 0 个 DOI | 确认（抽查逐位一致） | https://api.crossref.org/journals/1548-7091 ；https://api.crossref.org/journals/1098-0121 ；https://api.crossref.org/journals/0162-1459 ；https://api.crossref.org/journals/0033-295X ；https://api.crossref.org/journals/1532-4435 | 2026-09-26 |
| C12 （核验补充）`from-index-date` 增量放大：Nature Methods 自 2026-09-01 起 index-date 3,223 条，update-date 63 条，created-date 32 条 | 确认（已写入 §2.2.1 增量行与 §3 第 3 条） | https://api.crossref.org/journals/1548-7091/works?rows=0&filter=from-created-date:2026-09-01 （index/update 同构） | 2026-09-26 |
| C13 AAAI 前缀 10.1609 自 2025 年起 9,807 条（主会 8,406）；COS（member 15934）名下 23 个前缀、230,767 个 DOI；PsyArXiv posted-content 66,794 条 | 确认（PsyArXiv 复测为 66,800，属日常增长） | https://api.crossref.org/works?rows=0&facet=container-title:6&filter=prefix:10.1609,from-pub-date:2025-01-01 ；https://api.crossref.org/members/15934 ；https://api.crossref.org/prefixes/10.31234/works?rows=0&filter=type:posted-content | 2026-09-26 |
| C14 OpenAlex core 327,236,598、`corpus=all` 474,545,499；Topics 4/26/252/4,516；`per_page=200` 可用 | 确认（逐位一致） | https://api.openalex.org/works?per_page=1&select=id ；https://api.openalex.org/works?per_page=1&select=id&corpus=all ；https://api.openalex.org/topics?per_page=1 | 2026-09-26 |
| C15 OpenAlex 计费：单实体免费、列表 $0.0001、搜索/语义 $0.001、PDF $0.01；无 key $0.10/天、免费 key $1/天；100 req/s 硬顶 | 确认（LIVE 头 `x-ratelimit-limit-usd: 0.1`） | https://help.openalex.org/access/example-costs/ ；https://help.openalex.org/api-reference/authentication | 2026-09-26 |
| C16 OpenAlex 计划：Member $5,000/年（$20/天）、Member+ $10,000/年（$100/天，含日同步和"任意日期以来新增/变更"过滤）、Partner $20,000+/年 | 确认（页面更新于 2026-08-11） | https://help.openalex.org/access/pricing/ | 2026-09-26 |
| C17 `from_created_date`/`from_updated_date` 需付费计划 | 确认（LIVE 返回 429 "Plan upgrade required … Premium, Institutional, or Partner plan"） | https://api.openalex.org/works?filter=from_created_date:2026-09-01 | 2026-09-26 |
| C18 OpenAlex 公共快照改为季度（1/4/7/10 月第二个周三）；JSONL 约 745 GB、Parquet 约 770 GB；S3 匿名；日快照限付费 | 确认 | https://help.openalex.org/access/snapshot/ | 2026-09-26 |
| C19 `corpus=` 于 2026-08 取代 `include_xpac`；`mailto`/polite pool 自 2026-02 起失效；Concepts 弃用 | 确认（页面更新于 2026-09-22） | https://help.openalex.org/api/deprecations/ | 2026-09-26 |
| C20 Walden 2025-11-03 上线；XPAC 1.9 亿条，"含全部 DataCite""质量较低"，默认排除 | 部分未核验：日期、数量、默认排除已确认；"含全部 DataCite""质量较低"只见于已 301 下线的旧文档页的检索摘要，已改写并标 ⚠ | https://blog.openalex.org/openalex-rewrite-walden-launch/ ；https://help.openalex.org/guides/key-concepts | 2026-09-26 |
| C21 OpenAlex 因法律原因不提供明文摘要（2022 年作品 >60% 有倒排索引）；fulltext 50M+ PDF、约 43M TEI，保留原版权；2026-02-24 语义搜索 beta，官方不建议用于敏感生产 | 确认 | https://help.openalex.org/data/works/attributes/ ；https://help.openalex.org/access/fulltext/ ；https://blog.openalex.org/openalex-api-new-features-and-usage-based-pricing/ | 2026-09-26 |
| C22 OpenAlex 会议实体碎片化（NeurIPS 4,177、ICLR 757）；OA 判定偏差（JMLR ≈1%、PVLDB ≈18%） | 确认（NeurIPS 另有一个 168 条的 journal 型同名实体；JMLR 0.6%、PVLDB 17.7%） | https://api.openalex.org/sources?search=neural%20information%20processing%20systems ；https://api.openalex.org/sources/issn:1532-4435 ；https://api.openalex.org/sources/issn:2150-8097 | 2026-09-26 |
| C23 OpenAlex 2025 年按 field 画像（CS 401,895、Math 82,378、Psychology 237,318、Economics 171,507、Medicine 1,320,135） | 确认（抽查 5 个学科逐位一致） | https://api.openalex.org/works?filter=publication_year:2025,type:article&group_by=primary_topic.field.id | 2026-09-26 |
| C24 S2 规模 2.14 亿论文、24.9 亿引用、7,900 万作者；匿名用户共享 1000 RPS；key 入门 1 RPS | 确认 | https://www.semanticscholar.org/product/api | 2026-09-26 |
| C25 S2 API 许可"允许商业与非商业使用" | 修正：条款无此明文，只授予有限、不可转让、不可再许可的使用许可，禁止打包、出售或分发 API，须署名（§0、§2.2.3、§2.3.4、Q3 已改） | https://www.semanticscholar.org/product/api/license | 2026-09-26 |
| C26 S2 Datasets 最新 release 2026-09-22：abstracts 1 亿（ODC-BY）、embeddings-specter_v2 1.2 亿（Apache-2.0）、s2orc_v2 1,600 万与 tldrs 5,800 万（ODC-BY） | 确认 | https://api.semanticscholar.org/datasets/v1/release/latest | 2026-09-26 |
| C27 S2 Recommendations 接受正/负样本，limit ≤500，`from` 取 recent/all-cs；匿名 DOI 查询 404、搜索 429 | 确认 | https://api.semanticscholar.org/recommendations/v1/swagger.json ；https://api.semanticscholar.org/graph/v1/paper/DOI:10.1371/journal.pmed.0020124 | 2026-09-26 |
| C28 Unpaywall 于 2025 年末迁入 OpenAlex 数据库；DOI API、扩展与 Data Feed 保留；只覆盖 Crossref DOI | 确认 | https://help.openalex.org/access/unpaywall/ | 2026-09-26 |
| C29 Unpaywall 限速 10 万次/日 | 未核验（官方页为 JS 渲染；第三方资料一致） | https://unpaywall.org/products/api | 2026-09-26 |
| C30 CORE：未认证 100 token/日、10/分且不给全文；个人 1,000/日、25/分；学术 5,000/日、10/分；会员约 200k/日；4 亿+记录、4,000 万+全文；API 可商用（遵守 T&C，30 天试用）；旧 dump ODC-By，新 dump 需购买许可 | 确认 | https://api.core.ac.uk/docs/v3 ；https://core.ac.uk/about ；https://core.ac.uk/services/api ；https://core.ac.uk/services/dataset | 2026-09-26 |
| C31 dblp 三个主机 robots 全禁（167 行、4,125 字节、163 个具名 UA 加 `*`）；`sparql.dblp.org` `Crawl-delay: 10`，只放行 `/sparql`、`/download`；DROPS robots 只禁 3 类路径 | 确认（三个主机逐字节相同） | https://dblp.org/robots.txt ；https://sparql.dblp.org/robots.txt ；https://drops.dagstuhl.de/robots.txt | 2026-09-26 |
| C32 DROPS 月度快照 `dblp-2026-09-01.xml.gz` 1.02 GB，CC0，DOI 10.4230/dblp.xml.2026-09-01 | 确认 | https://drops.dagstuhl.de/entities/artifact/10.4230/dblp.xml.2026-09-01 | 2026-09-26 |
| C33 ORCID：匿名 12/s（突发 40）、每 IP 2.5 万次/日；注册 12/s、每 client 10 万次/日；Member 24/s 无配额；Public API 仅限非商业（2024-10-23）；年度公共数据文件 CC0 | 确认（原 ⚠ 的数据文件条款已核） | https://info.orcid.org/ufaqs/what-are-the-api-limits/ ；https://info.orcid.org/public-client-terms-of-service/ ；https://info.orcid.org/documentation/integration-guide/working-with-bulk-data/ | 2026-09-26 |
| C34 robots 与文档冲突：eutils、`pub.orcid.org`、`api.osf.io`、`api.base-search.net` 全禁；HAL API 禁 `/search/`、`/oai/`，`hal.science` 注释鼓励用 API；Zenodo 禁 `/api`（放行 `/api/records/*/files`），`/oai2d` 未禁；`osf.io`、`share.osf.io` 禁 `/api` 等 | 确认 | https://eutils.ncbi.nlm.nih.gov/robots.txt ；https://pub.orcid.org/robots.txt ；https://api.osf.io/robots.txt ；https://api.base-search.net/robots.txt ；https://api.archives-ouvertes.fr/robots.txt ；https://hal.science/robots ；https://zenodo.org/robots.txt | 2026-09-26 |
| C35 （核验补充）PubMed/PMC 的 bulk 主机 robots；原稿称"以 baseline 本地化可避开 robots 冲突" | 修正：`ftp.ncbi.nlm.nih.gov/robots.txt` 同为 `Disallow: /`，bulk 也须经 Q1 的 ADR（§0、§1.3.4、§2.2.11、§2.5、§3、Q1、Q15 已改） | https://ftp.ncbi.nlm.nih.gov/robots.txt | 2026-09-26 |
| C36 E-utilities 带 key 10 次/秒（原标 ⚠） | 确认，⚠ 已解除 | https://ncbiinsights.ncbi.nlm.nih.gov/2017/11/02/new-api-keys-for-the-e-utilities/ | 2026-09-26 |
| C37 PMC 旧 FTP 数据集 2026-08 下线，改用 PMC Cloud Service（AWS，免费免登录） | 确认；核验补充：同时停用 PMC OA Web Service API，Cloud 文件逐篇提供、不再有批量包 | https://ftp.ncbi.nlm.nih.gov/pub/pmc/readme.txt （见合规自检）；https://ncbiinsights.ncbi.nlm.nih.gov/2026/02/12/pmc-article-dataset-distribution-services/ | 2026-09-26 |
| C38 Europe PMC OA 子集 8,273,746 篇、预印本 1,247,001 条 | 确认（逐位一致） | https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=OPEN_ACCESS:y&format=json&pageSize=1&resultType=idlist | 2026-09-26 |
| C39 `www.ebi.ac.uk` robots"通用 UA 不受限" | 修正：通用 UA 组有 `Crawl-Delay: 10` 和 170 条 Disallow（REST 路径未被禁止） | https://www.ebi.ac.uk/robots.txt | 2026-09-26 |
| C40 Europe PMC 限速 | 未核验（官方只说限额按 IP 计，数值未公布） | https://groups.google.com/a/ebi.ac.uk/g/epmc-webservices/c/cZLnV1JhCj8 | 2026-09-26 |
| C41 DataCite：每 5 分钟认证 3,000 / 带标识 1,000 / 匿名 500 次，doi.org 1,000 次；GraphQL 于 2027-07 弃用；Event Data 2026 Q3 停止摄入、Q4 删除范围外事件；2025 年度文件 2026-01-06 生成（CC0）；月度文件限会员 | 确认 | https://support.datacite.org/docs/rate-limit ；https://support.datacite.org/docs/datacite-graphql-api-deprecation.md ；https://support.datacite.org/docs/datacite-event-data-changes.md ；https://support.datacite.org/docs/datacite-public-data-file.md ；https://support.datacite.org/docs/datacite-monthly-data-file.md | 2026-09-26 |
| C42 ROR 每 IP 2,000 次/5 分钟；client ID 方案（2,000 对 50）暂停，目前不区分；dump 在 Zenodo（CC0） | 确认 | https://ror.readme.io/docs/rest-api ；https://ror.readme.io/docs/client-id ；https://ror.readme.io/docs/data-dump | 2026-09-26 |
| C43 Zenodo：访客 60/分、2,000/时；认证 100/分、5,000/时；检索与 OAI-PMH 各 30/分；OAI 50 条/页，resumptionToken 2 分钟；元数据 CC0 | 确认 | https://developers.zenodo.org/ | 2026-09-26 |
| C44 Wikidata 图拆分于 2025-05-09 生效，学术端点为 query-scholarly，legacy 保留到 2025-12；WDQS 限额（单查询 60 s、每客户端每 60 s 60 s 处理时间、30 次错误/分、每 IP 5 并发） | 确认 | https://www.wikidata.org/wiki/Wikidata:SPARQL_query_service/WDQS_graph_split ；https://www.mediawiki.org/wiki/Wikidata_Query_Service/User_Manual | 2026-09-26 |
| C45 OpenAIRE：认证 7,200/时、匿名 60/时、token 1 小时、CC-BY（文档 v11.4.0）；实测匿名头 7199 | 确认（矛盾复现：匿名头仍为 `x-ratelimit-limit: 7199`，numFound 238,619,971） | https://graph.openaire.eu/docs/apis/terms/ ；https://api.openaire.eu/graph/v1/researchProducts?pageSize=1&type=publication | 2026-09-26 |
| C46 OpenCitations：每 IP 180 次/分钟，v2.2.0（2025-04-15）；Index 25 亿+（2026-07-28）；Meta 2026-06（1.47 亿实体、4.22 亿作者、230 万 venue，对齐 OpenAlex ID）；CC0；同一 DOI 被引 9,262 对 OpenAlex 10,801 | 确认 | https://api.opencitations.net/index/v2 ；https://download.opencitations.net/ ；https://opencitations.net/governance/ ；https://api.opencitations.net/index/v2/citation-count/doi:10.1371/journal.pmed.0020124 | 2026-09-26 |
| C47 DOAJ：2 req/s（最多排队 5）；期刊与文章元数据 CC0；全量 dump 需邮件申请，全体月更、高级用户日更；收录 23,544 刊 | 确认（文档页标 v4.0.0，版本史最新为 2025-08-21 的 v4.0.1） | https://doaj.org/api/v4/docs ；https://doaj.org/terms/ ；https://doaj.org/docs/public-data-dump/ ；https://doaj.org/api/search/journals/* | 2026-09-26 |
| C48 Lens 条款 v2026.06.01（试用仅非商业、正式仅机构订阅、商用需定制合同、不得转让或转售）；Dimensions 只对非商业科学计量研究免费（需申请） | 确认 | https://about.lens.org/lens-scholarly-api-terms-of-use/ ；https://www.dimensions.ai/scientometric-research/ | 2026-09-26 |
| C49 Scopus 配额（Search 2 万/周、9/s；Abstract 1 万/周、9/s；Citation Count 5 万/周、10/s；超额 429 + QUOTA_EXCEEDED）与按用例授权；WoS Starter（试用 1/s、50/日、无被引；机构 5/s、5,000/日；集成 2 万/日） | 确认 | https://dev.elsevier.com/api_key_settings.html ；https://dev.elsevier.com/policy.html ；https://developer.clarivate.com/apis/wos-starter | 2026-09-26 |
| C50 INSPIRE 每 IP 15 次/5 秒（被拒也计额），大部分元数据 CC0，robots 放行 `/api/literature`；NASA ADS 5,000 次/日 | 确认 | https://github.com/inspirehep/rest-api-doc ；https://inspirehep.net/robots.txt ；https://github.com/adsabs/adsabs-dev-api | 2026-09-26 |
| C51 zbMATH Open API `py:2026` 命中 125,723 条；许可"据信 CC BY-SA ⚠" | 确认，⚠ 已解除：API 主机上的条款副本写明 CC-BY-SA；部分评论因许可冲突不返回 | https://api.zbmath.org/v1/document/_search?search_string=py%3A2026&page=0&results_per_page=1 ；https://api.zbmath.org/v1/static/terms-and-conditions.html | 2026-09-26 |
| C52 HAL 元数据许可 ⚠ | 确认，⚠ 已解除：元数据自动适用 CC-0；2026-02 起上传文件必须标注许可 | https://doc.hal.science/en/aspects-juridiques/conditions-de-reutilisation/ | 2026-09-26 |
| C53 Microsoft Academic 于 2021-05-04 宣布退役，网站与 API 在 2021-12-31 后停止；替代列表含 OpenAlex、Crossref、S2、OpenCitations、Lens 等 | 确认（编者注日期为 2021-06-04） | https://www.microsoft.com/en-us/research/articles/microsoft-academic-to-expand-horizons-with-community-driven-approach/ | 2026-09-26 |
| C54 Google Scholar、MathSciNet、IA Scholar、Redalyc 的 robots 描述；Fatcat 三个主机连接超时 | 确认（Fatcat 复现超时；GitHub 最近推送为 2024-07-31） | https://scholar.google.com/robots.txt ；https://mathscinet.ams.org/robots.txt ；https://scholar.archive.org/robots.txt ；https://www.redalyc.org/robots.txt ；https://github.com/internetarchive/fatcat | 2026-09-26 |
| C55 BASE `www` robots：2025-09-16 更新，`Crawl-delay: 2`，只放行首页、高级检索与 about；具名封禁 ClaudeBot、anthropic-ai、AI2Bot、Scrapy、GPTBot 等，附法律声明 | 确认 | https://www.base-search.net/robots.txt | 2026-09-26 |
| C56 `kns.cnki.net` robots 全禁；ChinaXiv 的 robots 返回 403 维护页；中国科技论文在线全站维护 | 确认（paper.edu.cn 的 robots.txt 302 到挑战页，首页为"网站维护升级提示"） | https://kns.cnki.net/robots.txt ；https://chinaxiv.org/robots.txt ；https://www.paper.edu.cn/ | 2026-09-26 |
| C57 J-STAGE WebAPI：商用须事先申请，条款只有日文，浏览政策禁止大批量下载，须注明出处，2026-03-26 新增期刊检索；`www` robots 禁 `/*_pdf`；SciELO ArticleMeta 巴西合集 564,934 篇 | 确认 | https://www.jstage.jst.go.jp/static/pages/JstageServices/TAB3/-char/en ；https://www.jstage.jst.go.jp/robots.txt ；https://articlemeta.scielo.org/api/v1/article/identifiers/?collection=scl&limit=1 | 2026-09-26 |
| C58 ACM 自 2026-01-01 起全面 OA（v1 D-013） | 确认（依据为 acm.org 官方域检索摘要；原页对本 UA 返回 403，⚠ 未读到全文） | https://www.acm.org/articles/bulletins/2026/january/acm-open-access | 2026-09-26 |
| C59 §2.7 所列 15 个 GitHub 仓库的 star、license、最近推送与归档状态 | 确认（全部一致；`allenai/SPECTER2_0` 重定向到 `allenai/SPECTER2`，S2 数据集 README 仍用旧名） | `gh api repos/{owner}/{repo}`，例如 https://github.com/J535D165/pyalex | 2026-09-26 |
| C60 （核验补充）原稿遗漏的来源：Jisc Open policy finder（原 Sherpa；2026-02-11 新 API，旧 API 迁移期延至 2026-07，CC BY-NC-ND 4.0）、OpenDOAR、CiNii Research（OpenSearch 需 `appid`；robots 禁 `/opensearch`，放行 ResourceSync） | 确认（已写入 §2.2.29、§2.3.4、§2.5；OpenDOAR 现状与 Open policy finder 新 API 的注册方式 ⚠ 未核验） | https://openpolicyfinder.jisc.ac.uk/whats-new ；https://support.nii.ac.jp/en/cir/r_opensearch ；https://cir.nii.ac.jp/robots.txt | 2026-09-26 |
| C61 （核验补充）Europe PMC bulk 通道 `ftp.ebi.ac.uk/pub/databases/pmc/`（原稿 [S46] 实测列目录，未提 robots） | 修正：`ftp.ebi.ac.uk/robots.txt` 为 `User-agent: * / Disallow: /`，与 C35 同类（§0、§1.3.4、§2.2.10、§2.5、§3、Q1、Q15 已改） | https://ftp.ebi.ac.uk/robots.txt | 2026-09-26 |

**核验结论摘要**：抽查的 61 组断言中，数字类 [LIVE] 结果（Crossref、OpenAlex、Europe PMC、OpenCitations、SciELO、DOAJ、GitHub）全部可复现，未发现编造的仓库、产品或数字，因此没有删除任何条目。需要改动的集中在**许可与 robots 的解读**：S2 商用口径、EBI 的 `Crawl-Delay`、NCBI 与 EBI 的 bulk 主机同样全禁、Crossref `x-rate-limit-type` 头实测缺失、第三方 polite 池名称。此外解除了 4 个 ⚠（E-utilities 带 key 限速、zbMATH 许可、HAL 元数据许可、ORCID 数据文件），补充了 3 个遗漏来源。设计阶段引用本文时，Q1（robots 冲突 ADR）的适用范围应按 C35、C39、C60、C61 扩大，生医 P0 源的 bulk 本地化方案在 ADR 落定前不能视为已合规。
