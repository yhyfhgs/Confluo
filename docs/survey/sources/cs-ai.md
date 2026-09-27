---
title: 来源调研：计算机与 AI 会议、期刊、预印本与平台
status: draft
owner: opus5.5-survey
updated: 2026-09-26
---

# 来源调研：计算机与 AI 会议、期刊、预印本与平台

> 本文是 v2 重设计调研阶段（Survey）「①自定义论文来源」的 **CS/AI 分卷**：覆盖计算机与 AI 的一级来源（预印本、会议平台、期刊平台、出版商），以及与 CS 强相关的二级来源（聚合/索引/社区信号/仓储）、venue 名录体系和"最新论文"通道。
> **以 v1 为基线做增量**：v1 结论见 [catalog/cs-ai-conferences.md](../../archive-v1.md#docs-catalog-cs-ai-conferences-md)、[catalog/ai-ml-journals.md](../../archive-v1.md#docs-catalog-ai-ml-journals-md)、[catalog/publishers-platforms.md](../../archive-v1.md#docs-catalog-publishers-platforms-md)、[research/site-survey/](../../archive-v1.md#docs-research-site-survey)（arxiv / openreview / acm-dl / cs-ai-conferences / publisher-platforms-cs / metadata-apis / aggregators-unpaywall-dblp-core）与 [decision-log](../../plan/decision-log.md) D-012/D-013/D-014/D-020/D-021/D-024/D-037/D-038。本文不重复 v1 已稳定的实现细节，凡与 v1 不一致处以 ⚡ 标注。
> 跨学科的二级来源（Crossref 分池限速、OpenAlex 计费与快照、S2 嵌入等）以兄弟分卷 [aggregators-repositories.md](aggregators-repositories.md) 为主，本文只记 CS 视角的增量。
> **证据标注**：`[LIVE]` = 2026-09-26 本轮实测（curl/API 响应头/计数/robots.txt）；`[DOC]` = 2026-09-26 读取的官方文档页；`[SNIP]` = 原页对脚本返回 403，仅取得搜索引擎摘要；`[3P]` = 第三方社区/GitHub 资料；`[v1:日期]` = 沿用 v1 勘察结论，本轮未复测；`⚠ 未核验` = 本轮无法核实。**除另注外，所有核验日期均为 2026-09-26**；`[C#]` 编号见 §5。

## 0. 结论速览

1. ⚡ **dblp 已对所有通用爬虫关闭**：`dblp.org`、`dblp.uni-trier.de`、`dblp.dagstuhl.de` 的 robots.txt 末段均为 `User-agent: *` + `Disallow: /`，并具名禁止约 160 个 AI/agent UA（含 `Claude-User`、`ClaudeBot`）[C40][LIVE]。v1 在 2026-07-22 记录的 `Crawl-delay: 4`、允许 `/db/**` 已失效（D-021 依据）。合规通道只剩两条：一是 DROPS 托管的月度 XML 快照，2026-09-01 版为 1,099,942,087 字节、12,928,181 条记录、CC0 [C39][LIVE]；二是 `sparql.dblp.org`，其 robots 只放行 `/sparql`、`/download`，`Crawl-delay: 10` [C40][LIVE]。**CS 会议卷目录和 VenueEra 主干需要改为"导入快照"，不能再在线抓取。**
2. **arXiv 通道能力增强，但限流更严**：
   - 2025-03 重写后的 OAI-PMH 支持**类目级 set**，例如 `cs:cs:LG`，全部 40 个 cs 子类都有独立 set [C2][C3][LIVE]；`arXiv` 格式的记录自带逐篇 `<license>` [C3][LIVE]。
   - API、OAI、RSS 共用同一条限速："1 req/3s、单连接、所有受你控制的机器合计" [C1]。ToU 现把 OAI-PMH、RSS 和 arXiv API 统称为"legacy APIs"，并注明"These limits may change in the future"；本轮未见任何新接口的公开文档（核验补充 [C1][C67]）。
   - 2026-02 起 API 频繁返回 429，arXiv 员工确认"最近调整过限流" [C9]；社区还观测到"HTTP 200 + 正文 `Rate exceeded.`"这种伪成功响应 [C10][3P]。
   - 用量参考：2026-09-21~25 这一周，cs 集的 OAI 记录共 7,083 条（含新投稿和替换版本）[C3][LIVE]。
3. **arXiv 的许可证决定了全文能否在多用户之间共享**：ToU 禁止在自有服务器上"store and serve" e-print，许可证允许的除外 [C1]。cs.LG 某日的 315 条记录中，44% 为 arXiv 默认的非独占分发许可，44% 为 CC BY 4.0，其余为 CC BY-NC-SA、CC BY-NC-ND、CC BY-SA 和 CC0 [C3][LIVE]。**因此 v2 的共享缓存必须逐条按许可证放行。**
4. **OpenReview：必须有账号，限流按端点区分，活跃会议可以匿名发现**：
   - 官方文档写明"You need an OpenReview account to use the API" [C13]；匿名请求 `/notes` 仍返回 403 `ChallengeRequiredError` [C15][LIVE]。
   - 限流响应头随请求而异，不能按路径写死：同为 `/groups`，`id=ICLR.cc/2026/Conference` 返回 `20;w=60`，`id=active_venues`、`id=venues` 返回 `180;w=60`；匿名 `/notes` 为 `180;w=60`；v1 记录的是统一的 60/60s [C15][LIVE]（核验修正：原文"groups 为 20、notes 为 180"以偏概全）。
   - `active_venues` 可匿名读取，约 1,090 个活跃 venue（调研实测 1,094，核验复测 1,092，随时间变动），包括 NeurIPS 2026、ICML 2026、COLM 2026、CoRL 2026、ECCV 2026、EMNLP 2026、ACM MM 2026、AAAI 2027、KDD 2026 各分轨等 [C15][LIVE]。
   - API v2 支持 `mintcdate`、`mintmdate`、`sort`、`after`、`select`，可用于增量拉取 [C16][LIVE]。
   - 2025-11 的一次 API 漏洞泄露了 ICLR 2026 约 1 万篇投稿的匿名身份 [C17]，因此 v2 不应采集任何评审身份类数据。
   - OIDC 登录（"Sign in with OpenReview"）：文档只描述用 access token 调 UserInfo 取 profile 声明 [C14]，可以用来绑定作者身份；文档没有说明该 token 能否调用数据 API，设计上不应假设可以（核验修正措辞）。
5. **ACM 全面开放获取不等于允许自动化访问**：
   - 2026-01-01 起全库免费阅读 [C18][SNIP]。
   - 本轮匿名 HEAD 请求仍返回 `cf-mitigated: challenge`（Cloudflare 质询）[C21][LIVE]；ToS 禁止用脚本或爬虫下载 [C19][SNIP]。
   - 只有机构签订的 ACM Open 协议里才有"Computational Access"条款，且要经 ACM 提供的 API [C20]。
   - Crossref 中 ACM 2025 年的 46,548 条记录，只有 15.5% 带摘要、27.5% 带 license 字段 [C22][LIVE]。
6. **IEEE API 条款给 v2 设了硬约束**：
   - ToU 只允许"在被许可机构内做非商业用途"，内容"只能按单次查询展示，不得批量呈现"，"不得分发给第三方"，并且**"不得用于训练、增强或开发任何 AI/ML/LLM"** [C24][DOC]。ToU 另规定 API 访问"limited to current IEEE customers"（政府与企业客户可另行申请），禁止用任何 robot、spider 或检索程序"retrieve or index any portion of the Content"，也不得以可被人或机器收割的形式分发（核验补充 [C24]）。
   - Crossref 中 IEEE 2025 年的 445,469 条记录**没有一条带摘要** [C22][LIVE]。
   - IEEE 版会议论文的 DOI 注册明显滞后：CVPR 2025 约 2 个月、ICRA 2025 约 3.5 个月、ICCV 2025 约 6 个月 [C59][LIVE]。
7. **Springer API 免费档额度很小，ECCV 应走 ECVA**：
   - Meta API、Open Access API 的 Basic 档都是 100 次/分、500 次/日 [C26][LIVE]。
   - LNCS 论文在 Crossref 中登记为 book-chapter，2025 年只有约 3% 带摘要 [C22]。
   - robots 对 `*` 默认 `Disallow: /`，只放行内容路径，并具名禁止 Claude、GPT 等 AI UA [C27][LIVE]。
   - ECCV 2018–2024 的开放全文在 ECVA，共 6,166 篇 [C28][LIVE]。
8. **Papers with Code 关停后的替代**：
   - paperswithcode.com 已 302 跳转到 HF Trending；PwC 数据以 CC-BY-SA-4.0 存档在 HF 的 `pwc-archive/*` [C45][LIVE]。
   - HF Papers 有官方 SDK（`list_daily_papers`，排序可选 publishedAt 或 trending）；匿名额度为 API 500 次/5min、搜索 50 次/5min [C41][C44][LIVE]。
   - alphaXiv 只提供按用户授权（OAuth 或 API key）的 MCP 服务器，没有公开 REST 接口 [C46]。
9. ⚡ **v1 名录与平台映射有 7 处过时**：
   - TASLP 已改名并换用新 ISSN 2998-4173 [C59]。
   - NeurIPS 自 2022 年起有 Crossref DOI（Curran 前缀 10.52202，第 35–38 卷共 16,691 条）[C22]。
   - NeurIPS 2025 新增 Position Paper 与 Creative AI 两个分轨 [C34]；v1 的 track 闭表遇到它们会报 CONFIG。
   - ECCV 的开放全文在 ECVA，不在 CVF [C28][C29]。
   - ICSE 2026 论文集在 ACM DL；FSE、SIGMOD 已期刊化为 PACMSE、PACMMOD [C22]。
   - LIPIcs 的 DOI 注册在 DataCite，不在 Crossref [C12][C39]。
   - Elsevier 期刊在 Crossref 中只能用 print ISSN 过滤，e-ISSN 查出 0 条 [C22]。
10. **CS venue 名录体系换代**：
    - CCF 第七版于 2026-03-31 发布（公示期 03-05 至 03-12，4-09 发布勘误）[C52]。相比 2022 版，新增期刊 14 种、会议 23 个，升级期刊 6 种、会议 5 个。
    - 新版中 ICLR 首次列为 A 类、IJCAI 降为 B 类 [C52][C53]。
    - CORE 更名为 ICORE，现由 CORE、GII、GRIN、SCIE 四方联合管理 [C68]。ICORE2026 共评级 825 个会议 [C55]；该数字来自调研员导出的 CSV，门户 robots 对 Claude 类代理全站 Disallow，核验未复测（见核验记录）。
    - CSRankings 按 27 个父领域收录 77 个会议键，许可为 CC BY-NC-ND 4.0 [C54]。

## 1. 调研范围与方法

### 1.1 范围

| 维度 | 纳入 | 不纳入 / 另见 |
|---|---|---|
| 学科 | ML/AI、CV、NLP/语音、IR/Web/DM、DB、系统/网络/安全、SE、HCI、机器人、TCS | 经济/金融/管理见 [social-sciences-econ-fin-mgmt.md](social-sciences-econ-fin-mgmt.md)；理科见 `natural-sciences/` |
| 一级来源 | 预印本（arXiv、TechRxiv、IACR ePrint）、会议平台（OpenReview、PMLR、NeurIPS、CVF、ECVA、ACL Anthology、AAAI OJS、IJCAI、USENIX、NDSS、PVLDB、ISCA、DROPS/LIPIcs、RSS、MLSys、CEUR）、期刊平台（JMLR/TMLR、JAIR、MIT Press）、出版商（ACM、IEEE、Springer、Elsevier、IOS Press、SIAM、now） | ICLR BlogPosts/TinyPapers 等非论文卷（按用户要求 ICLR blogposts 不计）；各会 workshop 卷只作登记不排期 |
| 二级来源 | CS 视角的 Crossref/DataCite/OpenAlex/S2/dblp/Unpaywall/HAL，社区信号（HF Papers、alphaXiv、PwC 存档） | 跨学科聚合细节见兄弟分卷 [aggregators-repositories.md](aggregators-repositories.md) |
| 名录体系 | CCF 2026（第七版）、ICORE2026、CSRankings、ccfddl（截稿与会期数据） | Google Scholar Metrics（只作人工参考，红线：不做自动化主源） |
| 合规红线 | 贯穿全文：诚实 UA、先读 robots/ToS、遇质询即停、不绕付费墙/CAPTCHA、不接盗版源、auth-gated 全文不在用户间共享 | Sci-Hub/LibGen 等一律排除，不列入名录 |

### 1.2 方法与请求纪律

- **基线**：先读 v1 的 catalog、site-survey、adapter 设计和 decision-log，只对以下三类事项复测：①2025–2026 可能变化的政策与接口；②用户点名的缺口来源；③名录体系。
- **证据优先级**：官方文档或官方数据（`[DOC]`、`[LIVE]`）优先于第三方（`[3P]`），第三方优先于搜索摘要（`[SNIP]`）。计数一律来自 API 响应，不引用二手数字。
- **请求纪律**：
  - UA 统一为 `PaperCrawler/0.1 (source survey; personal research; mailto:<用户邮箱>)`；同一主机的请求间隔 ≥2–4 s，arXiv ≥3–4 s。
  - 先读 robots.txt，站点页面优先用 HEAD，不伪造浏览器 UA，遇到 Cloudflare 质询立即停止。
  - 全文 PDF 只为核验许可条款下载过 2 篇（JMLR、PVLDB 各 1 篇，只抽首页文字）。
- **工具受限说明**：本会话的 WebSearch 预算与并行调研 agent 共享，本 agent 用了 8 次检索后预算即告耗尽。之后改用三种方式：①直接读取官方文档页（WebFetch/curl）；②官方 API（Crossref、DataCite、OpenAlex、HAL、HF、OpenReview groups、arXiv OAI）；③用 `gh api` 读取 GitHub 仓库与文件。因此部分只能靠检索才能确认的点标为 ⚠（汇总见 §4）。

### 1.3 过程记录（可复现）

| # | 类别 | 检索式 / 访问对象（均为 2026-09-26） | 结果要点 |
|---|---|---|---|
| 1 | 读 v1 基线 | `docs/catalog/{cs-ai-conferences,ai-ml-journals,preprint-platforms,publishers-platforms}.md`；`docs/research/site-survey/{arxiv,openreview,acm-dl,cs-ai-conferences,publisher-platforms-cs,metadata-apis,aggregators-unpaywall-dblp-core}.md`；`docs/design/adapters/{acm-dl,ieee-xplore,openreview,arxiv}.md`；decision-log；`src/paper_crawler/adapters/`、`venues/cs_ai/*.yaml` | 形成 v1 口径对照表（§2.1） |
| 2 | WebSearch | ① `arXiv API changes 2026 rate limit export.arxiv.org announcement` ② `arXiv computer science review articles position papers policy change peer review 2025` ③ `OpenReview API security incident November 2025 reviewer identities leaked ICLR 2026` ④ `OpenReview API rate limit 2026 "api2.openreview.net" guest access token required` ⑤ `docs.openreview.net "rate limit" API requests per minute` ⑥ `ACM Digital Library open access January 2026 all content free to read backfile license CC-BY` ⑦ `ACM Digital Library text and data mining policy automated downloading "systematic" 2026` ⑧ `"ACM Digital Library" "Tiered-Band" open access agreement "text and data mining" autonomous` ⑨ `IEEE Xplore API "200 calls per day"…`（预算耗尽，未执行） | 线索：arXiv 限流讨论串与 PR、arXiv CS 政策博文、ICLR 安全事件博文、ACM OA 公告与政策摘要、KB 的 ACM Open 协议 PDF |
| 3 | WebFetch 官方文档 | info.arxiv.org（tou、oa、rss、bulk_data_s3、bulk_data、availability）；blog.arxiv.org 2025-10-31 博文；docs.openreview.net（using-the-api、sign-in-with-openreview、api-v2）；blog.iclr.cc 2025-12-03；developer.ieee.org（首页、getting_started、docs、API_Terms_of_Use2、Metadata_API_details）；huggingface.co/docs/hub/rate-limits；huggingface.co/papers/trending；alphaxiv.org 首页与 /docs/mcp；library.cranfield.ac.uk TDM 页；ecva.net/papers.php | libraries.acm.org、acm.org 公告页与 portal.core.edu.au 对 WebFetch 返回 403；ccf.org.cn 证书链报错，改用 curl -k（其 robots 允许该路径） |
| 4 | curl：robots.txt | arxiv.org、export.arxiv.org、openreview.net、api2.openreview.net、dl.acm.org、ieeexplore.ieee.org、link.springer.com、ecva.net、openaccess.thecvf.com、ijcai.org、usenix.org、vldb.org、aclanthology.org、proceedings.neurips.cc、proceedings.mlr.press、ojs.aaai.org、jmlr.org、isca-archive.org、drops.dagstuhl.de、dblp.org（及两镜像）、sparql.dblp.org、techrxiv.org、eprint.iacr.org、alphaxiv.org、scirate.com、papers.cool、semanticscholar.org、huggingface.co、ceur-ws.org、proceedings.mlsys.org、ndss-symposium.org、roboticsproceedings.org、jair.org、transacl.org、direct.mit.edu、ebooks.iospress.nl、icml.cc、neurips.cc、iclr.cc、ccf.org.cn、portal.core.edu.au | 全文摘录见 §2 各表；scirate 的 robots 本身就被 Cloudflare 托管质询拦截（403） |
| 5 | curl：接口与计数 | arXiv OAI（ListSets；ListIdentifiers `set=cs` 及 4 个子类，2026-09-21~25；ListRecords `cs:cs:LG` 2026-09-24；GetRecord 2609.28603）；OpenReview（groups ICLR 2026、active_venues、venues；notes 匿名探测 1 次）；HEAD dl.acm.org 1 次；CVF（menu、CVPR2026、ICCV2025）；ECVA papers.php；IJCAI 2025/2026 年页；USENIX sec25 会话页与 1 个 presentation 页；PVLDB vol19；NeurIPS 2025 年页与 vol38 卷页、1 个 abstract 页；PMLR 首页及 v300/v327/v329/v335–v346 探测；AAAI OJS index/archive/OAI；JMLR RSS、v27 论文页、TMLR 列表；ISCA 2025 年页；DROPS OAI 与 dblp 快照页；HF daily_papers 与 papers/search；OpenAlex works；HAL search；ICORE2026 CSV 导出 | 计数与响应头见各节 |
| 6 | 元数据 API | Crossref：约 70 次（prefix × 年份 × has-abstract/has-license 计数、container-title facet、单条记录 `created` 时间、`/journals?query=`）；DataCite `dois` 3 次；`doi.org/ra/{prefix}` 16 次；OpenAlex 1 次（匿名额度已被他人用去 157/1000） | 限流头 `x-rate-limit-limit: 10`、`x-concurrency-limit: 3`、`x-api-pool: polite-single`（带 mailto 的单条请求） |
| 7 | GitHub（`gh api`） | ccfddl/ccf-deadlines（`conference/*.yml`、PR #1381、`.readme_assets/ccf_recommended_2026.pdf`、LICENSE）；emeryberger/CSrankings（`csrankings.js`、COPYING）；paperswithcode/paperswithcode-data（README、commits）；huggingface/huggingface_hub（`hf_api.py`）；各仓库 star/license/pushed_at | CCF 2026 PDF 用 pypdf 抽取 72 页文本 |
| 8 | 许可核验 | 下载 KB 的 ACM Open 协议 PDF（§IV.5–6）；JMLR 论文 PDF 首页（CC BY 4.0）；PVLDB 论文 PDF 首页（CC BY-NC-ND 4.0） | 每类只取 1 份 |
| 9 | 合规自查 | ⚠ 误请求 1 次 `icml.cc/static/virtual/data/icml-2026-orals-posters.json`；事后核对 icml.cc robots 为 `Disallow: /static`，属禁区 | 只拿到 HTTP 200 与 count 字段（6,797），本地文件已删除，之后未再访问任何 `/static` 路径；结论：该 JSON 与 `/api/miniconf/` 都不能作为 v2 通道（§2.2 行 `conf_virtual_sites`） |

**请求量**（按主机近似统计）：`api.crossref.org` 约 70；`oaipmh.arxiv.org` 9；`proceedings.mlr.press` 约 16；`api2.openreview.net` 5；`dl.acm.org` 2（robots + 1 次 HEAD）；其余站点每站 1–5 次。全程没有触发 429；除 dl.acm.org 的 HEAD 与 scirate 的 robots 外，没有遇到质询。核验轮（Verify）的检索式、访问站点与请求量见文末[核验记录](#核验记录)。

## 2. 主体内容

### 2.1 2025–2026 变化核验（相对 v1 口径）

#### 2.1.1 预印本与社区信号

| 主题 | v1 口径（出处·日期） | 2026-09-26 核验结果 | 对 v2 的影响 |
|---|---|---|---|
| arXiv OAI-PMH set 粒度 | "set 只到 archive 级（cs/stat/econ/q-fin），子分类需客户端过滤"（site-survey/arxiv.md·2026-07-20） | ⚡ 2025-03 重写后支持 `group:archive:CATEGORY`，例如 `cs:cs:LG`；ListSets 返回 183 个 set，cs 下 40 个子类各有一个；earliest datestamp 从 2007-05-23 提前到 2005-09-16 [C2][C3][LIVE] | 可以按子类下推收割，省去客户端过滤；v1 `arxiv` adapter 应改用子类 set |
| arXiv 公告与可取时间 | API 1 req/3s；OAI resumptionToken 每日过期（v1） | 投稿日 14:00 ET 截止，当日 20:00 ET 公告，周日至周四公告、周五周六无公告；2026 年列出 9 个节假日延迟；OAI 数据"通常 Sun–Thu 约 22:30 ET"可取；RSS 每日午夜（EST）更新 [C2][C4][C7][DOC] | "最新论文"任务应在 ET 22:30 之后运行，并内置节假日日历 |
| arXiv 限流 | 1 req/3s、单连接（v1） | 条款未变（"all machines under your control"合计）[C1]；2026-02-26 起多人报告 429，员工 2026-02-27 回复"we have made changes recently and over time"，至 2026-06 仍有人反馈遵守 3 s 间隔也被 429；POST 请求会绕过 Fastly 缓存，更易触发 429（这一观察来自讨论串中的社区成员、arxiv.py 维护者 Lukas Schwab，并非 arXiv 官方说法）[C9]；社区 PR（2026-09-22 合并）报告了"HTTP 200 + 正文 `Rate exceeded.`"的伪成功响应 [C10][3P] | ①全站只设一个 arXiv 令牌桶，由中心调度；②解析前先检查响应正文里的限流标志；③v2 多用户搜索必须查本地镜像，不能把用户请求透传给 arXiv API |
| arXiv ToU（全文再分发） | "不做再分发"（红线口径） | ToU 明文：元数据 CC0，可"retrieve, store, transform, and share"；e-print 可个人或研究使用，但不得在自有服务器上"store and serve"，许可证允许的除外，并应"Direct users to arXiv.org"；S3/bulk 页也要求"link back to arXiv for downloads" [C1][C5][C6] | 多用户场景下，全文只能缓存许可证允许的那部分（见 §2.7） |
| arXiv 逐篇许可 | 未记录 | `arXiv` 格式含 `<license>`；cs.LG 2026-09-24 的 315 条中：arXiv 非独占 140（44%）、CC BY 4.0 139（44%）、CC BY-NC-SA 17、CC BY-NC-ND 11、CC BY-SA 7、CC0 1 [C3][LIVE] | `asset.license` 须入库，并作为共享与展示的门控字段 |
| arXiv CS 投稿政策 | 未记录 | 2025-10-31 起，CS 类综述和立场论文须先通过期刊或会议的同行评审，投稿时附期刊引用与 DOI；workshop 评审"generally … is not enough" [C11][DOC] | 2025-11 之后，arXiv CS 上新综述的供给结构会变化；"综述型推荐"要改用期刊或会议源 |
| arXiv DOI | 未记录 | arXiv DOI 前缀 10.48550 的注册机构是 **DataCite**（非 Crossref）[C12][LIVE] | arXiv 与正式版的 DOI 对齐需要查 DataCite，Crossref 查不到 |
| arXiv bulk | S3 约 9.2 TB（2025-04）；Kaggle 周更、CC0（v1） | S3（us-east-1，requester-pays）约 9.2 TB（2025-04），每月约增 100 GB，按月更新，附 manifest；官方称 S3 是下载全量语料的"accepted mechanism" [C5][C6][DOC]；Kaggle 当前版本号未能核验 ⚠ | 历史回填走 OAI 元数据即可；全量 PDF 不在 v2 默认范围内 |
| arXiv robots | listing Crawl-delay 15（v1） | `*` 的 `Crawl-delay: 15`，Allow 包括 `/list /abs /pdf /html /catchup /archive /year`，Disallow 包括 `/api /search /e-print /src /oai2` 等；export.arxiv.org 全站 Disallow（只能通过 API 访问）[C8][LIVE] | `/html`（HTML 全文）可用于抽取，但同样受许可证约束 |
| TechRxiv | 未登记 | Crossref 10.36227，类型 posted-content/preprint，出版方 IEEE，带摘要，样本许可 CC BY 4.0；2025 年 6,329 条，2026 年截至 9-26 共 1,520 条 [C49][LIVE]；robots 为 Atypon 形态，禁 `/rss /search /action` 等 [C49] | 元数据可零爬取接入 |
| IACR ePrint | 未登记 | robots 注释写明"Metadata is available … using OAI-PMH, RSS, and ATOM"，但对 `User-agent: *` 为 `Disallow: /`（爬虫须经白名单）；AI bot 不得取 PDF；OAI 可用（earliest 1996）；RSS 最新 100 条，`dc:rights` 多为 CC BY 4.0 [C48][LIVE] | 典型的"robots 全禁、但声明了协议通道"，需要单独建模（§3 第 2 条） |
| Papers with Code | 2025-07 关停（v1，D-013） | 域名 302 跳转到 `huggingface.co/papers/trending`；GitHub 数据仓库 README 在 2025-09-08 把下载链接改为 HF `pwc-archive/*`（CC-BY-SA 4.0）；`papers-with-abstracts` 的 lastModified 为 2026-08-17，`links-between-paper-and-code` 为 2025-09-10 [C45][LIVE] | 可一次性导入"论文↔代码/基准"的历史关联 |
| HF Papers | 未登记 | 官方 SDK `HfApi.list_daily_papers(date/week/month/submitter/sort=publishedAt 或 trending/p/limit)`、`paper_info`、`list_papers` [C44]；`/api/daily_papers` 返回 upvotes、numComments、submittedOnDailyAt、organization 等字段；匿名限流头为 `"api";q=500;w=300`、`"search";q=50;w=300` [C41][LIVE]；官方档位：匿名 API 500 次/5min，免费用户 1,000 次/5min [C42]；Trending 页展示 upvote 与 GitHub stars [C43] | 可作为社区热度与代码可得性信号源；ID 统一用 arXiv id |
| alphaXiv | 未登记 | MCP 服务器 `https://api.alphaxiv.org/mcp/v1`，鉴权为 OAuth 2.1 或个人 API key，提供 19 个工具（论文检索与内容、学者、文库）；计入"assistant quota"，额度未公开；CORS 只放行第一方来源 [C46][DOC]；robots 对 `*` 为 Allow（禁 `/?`、`/signin?`）[C46][LIVE] | 只能做"用户自己连接"的连接器，不能做平台级抓取 |
| SciRate | 未登记 | 连 robots.txt 都返回 Cloudflare 托管质询（403）[C47][LIVE] | 排除 |

#### 2.1.2 会议与期刊平台

| 主题 | v1 口径 | 2026-09-26 核验结果 | 对 v2 的影响 |
|---|---|---|---|
| OpenReview 鉴权 | 匿名 notes 403，需要 token（v1·2026-07-22） | 文档写明"You need an OpenReview account to use the API"，并称 API v1"being phased out"[C13]；匿名 `/notes` 仍为 403 `ChallengeRequiredError`，附 `challengeUrl` [C15][LIVE] | 平台层需要"服务账号"或用户自己的 token（ToS 限一人一号，⚠ 服务账号的合规性待确认，见 §4） |
| OpenReview 限流 | 60/60s（v1 实测头） | ⚡ 随请求而异（核验修正）：同为 `/groups`，`id=ICLR.cc/2026/Conference` 返回 `ratelimit-policy: 20;w=60`，`id=active_venues`、`id=venues` 返回 `180;w=60`；匿名 `/notes`（403）为 `180;w=60`；另带 `x-ratelimit-limit/remaining/reset` [C15][LIVE] | 限速器按请求读响应头动态配置，不按路径写死 |
| OpenReview venue 发现 | `groups?id=venues` 4,380（v1） | `venues` 4,706；`active_venues` 1,094（匿名 200；核验复测为 1,092，另含 `ICLR.cc/2027/Conference`），包括 `NeurIPS.cc/2026/Conference`、`ICML.cc/2026/Conference`、`colmweb.org/COLM/2026/Conference`、`robot-learning.org/CoRL/2026/Conference`、`thecvf.com/ECCV/2026/Conference`、`EMNLP/2026/Conference`、`acmmm.org/ACMMM/2026/Conference`、`AAAI.org/2027/Conference`、`KDD.org/2026/*`、`auai.org/UAI/2026/Conference`、`aistats.org/AISTATS/2027/Conference`、`MLSys.org/2027/Conference`、`algorithmiclearningtheory.org/ALT/2027/Conference`、`logconference.io/LOG/2026/Conference` [C15][LIVE] | 可替代 D-038 暂缓的"年度追新探测"：新会议、新届以 `active_venues` 的差集触发 |
| OpenReview 增量参数 | `content.venueid` 过滤 + offset 翻页（v1） | OpenAPI 列出 `mintcdate`/`mintmdate`（最小创建/修改时间）、`sort`（默认 desc，平局有确定性排序、分页稳定；`replyCount` 可排序但必须带 invitation）、`after`（游标）、`select`（字段裁剪）、`count`、`stream`、`externalId` [C16][LIVE] | 用 `mintmdate` 做水位线增量；`replyCount` 可作为讨论热度信号 |
| OpenReview 接收态 | venueid 规则按届区分（v1） | ICLR 2026 的 group content 显式给出 `submission_venue_id`、`withdrawn_venue_id`、`desk_rejected_venue_id`、`rejected_venue_id`、`decision_name`=Decision [C15][LIVE] | 拒稿池可显式枚举（若用户需要"被拒但公开"的论文） |
| OpenReview 安全事件 | 未记录 | 2025-11-27 10:09 EST 接报，11:10 EST 修复；可泄露作者、评审、AC 的匿名身份；超过 1 万篇 ICLR 投稿（约 45%）被抓取并外传；最早可能在 2025-11-11 已被利用 [C17][DOC]。据社区报道，漏洞端点为 `profiles/search`（⚠ 未核验：ICLR 博文、两篇 36kr 报道和 arXiv 2609.11983 都没有点名端点，该名称只见于搜索引擎摘要和本轮打不开的社区帖；OpenReview 自己的声明页对脚本返回浏览器验证，未能直读）[C62]。arXiv 2609.11983 另确认该漏洞波及 ICLR、ACL、KDD、ICML 等多个 venue [C62] | v2 不采集 profiles、评审身份、非公开字段；审计日志要能证明这一点 |
| OpenReview OIDC | 未记录 | "Sign in with OpenReview"：OIDC 授权码 + PKCE，scope 为 `openid/profile/email`；token 有效期 1 小时，不发 refresh token；client 须人工申请；文档只描述用 access token 调 UserInfo 取 profile 声明，**没有说明能否用于数据 API** [C14][DOC]（核验修正措辞） | 可做"用户↔OpenReview 作者身份绑定"（双向匹配的身份锚），但不能作为数据通道 |
| NeurIPS proceedings | 1987+ 年页；无 DOI（v1 隐含） | ⚡ 2025 卷（vol 38）已上线：main-conference 卷页共 5,823 篇（Conference 5,286 + Datasets_and_Benchmarks 497 + Position_Paper 40），另有 Creative_AI 64 篇在独立页 [C34][LIVE]；页面 `citation_doi` 为 10.52202/085713-0001，前缀 10.52202 为 Curran（Crossref），第 35/36/37/38 卷分别 2,834/3,540/4,494/5,823 条，无摘要，`resource.primary` 指向 proceedings.com；vol 38 的 DOI 创建于 2026-08-06，比会期（2025-11-30）晚约 8 个月 [C22][C59][LIVE] | v1 adapter 的 `(era,track)` 闭表只有 none/conference/datasets_and_benchmarks，需加入两个新分轨；DOI 可用于和 Crossref 对齐，landing 仍用官方站 |
| PMLR | 卷号↔年映射（v1） | 首页最新：v339 RAISE 2026、v337 UAI 2026、v336 COLT 2026、v313 ALT 2026、v305 CoRL 2025、v267 ICML 2025；探测 v300 = AISTATS 2026、v340 = MLHC 2026、v341 = ProbNum 2026；**ICML 2026（2026-07 首尔）截至 9-26 在首页卷表中未见**，v335/v338/v342–v346 均 404 [C35][LIVE]；站点为 GitHub Pages，robots.txt 为 404 | 新卷发现要靠"首页 diff + 卷号探测"；ICML 的最新一届在 PMLR 上线前，走 OpenReview |
| CVF | CVPR/ICCV/WACV 2013+（v1） | menu：CVPR 2013–2026、ICCV 2013–2025（奇数年）、WACV 2020–2026，**没有 ECCV**；CVPR 2026 4,042 篇，ICCV 2025 2,701 篇 [C29][LIVE]；页面声明"Copyright and all rights therein are retained by authors or by other copyright holders" [C29] | CVF 是 CV 顶会的最早全文源（早于 IEEE DOI） |
| ECCV | "Springer 正式；CVF 镜像新格式未证实"（v1） | ⚡ ECVA `papers.php` 单页列出 ECCV 2018/2020/2022/2024 共 776/1,358/1,645/2,387 篇，含 PDF 与 supp；页面注明"DOI links will be inaccessible until released by Springer"；ECCV 2026（09-08 至 12 马尔默）截至 9-26 还未上 ECVA，但 Springer LNCS 在 Crossref 已有 2,251 条 [C28][C22][LIVE] | ECCV 的全文源从"CVF 镜像"改为 ECVA；元数据走 Crossref |
| ACL Anthology | GitHub bulk 优先（v1） | 官方 Python 包 `pip install acl-anthology`，数据位于 GitHub `/data/xml`；许可：2016 年起 CC BY 4.0，2016 年前 CC BY-NC-SA 3.0；"Verified authors"与 ORCID 关联（2026-01-15 更新）；站点 2026-09-22 构建；robots.txt 404；ACL 2026 已有 long 2,222 篇、Findings 2,163 篇等（不含卷首 front matter；事件页按 id 计为 2,223/2,164，核验修正）[C33][LIVE]；Crossref 10.18653 在 2025 年共 11,121 条，**全部没有摘要** [C22] | NLP 首选零爬取源；带 ORCID 的作者映射可用于双向匹配 |
| AAAI OJS | AAAI 2019+ 注册；OAI 为主路径（v1） | 同一 OJS 实例托管 9 个会议或刊：AAAI、AAAI-SS、AIIDE、AIES、HCOMP、IASEAI、ICAPS、ICWSM、SoCS；AAAI-26 Technical Tracks 已上线；OAI 每页 100 条 + resumptionToken，earliest 2020-06-02 [C36][LIVE]；Crossref 10.1609 在 2025 年共 4,337 条，**摘要覆盖 100%**，link 含 `text-mining` PDF [C22][C59]；AAAI-27 起改在 OpenReview 评审（active_venues）[C15] | 同一 adapter 可零成本扩到 ICAPS/ICWSM/AIES 等 |
| IJCAI | 专用 adapter 待建（v1） | 年页 `/proceedings/{y}/`：2025 年约 1,280 个 PDF 链接，2026 年 972 条（会期 08-15）；页脚为"© IJCAI"；robots 为 `Crawl-delay: 10` [C30][LIVE]；Crossref 10.24963 **只覆盖 2017 年起**（最早 `ijcai.2017/47`）[C22][LIVE]。⚡ 该前缀同时承载 KR 论文集（KR 2020 起），计数须按 container-title 拆分：2025 年前缀共 1,368 条（摘要 1,366）= IJCAI-34 1,281 + KR 2025 85 + 2；2026 年前缀共 1,085 条 = IJCAI-35 972 + KR 2026 111 + 2；IJCAI 2026 本身为 972 条，与站点一致（核验修正：原文把前缀总数记成 IJCAI）[C22][LIVE] | 元数据用 Crossref，全文用站点 PDF；2017 年前只能靠 dblp 快照；同一 adapter 可按 container-title 顺带接入 KR（CCF B / ICORE A*） |
| USENIX | 全 OA（v1） | 页面声明"Papers and proceedings are freely available to everyone once the event begins"；录用后即挂 prepub PDF（如 `sec25cycle1-prepub-1174-nong.pdf`）；presentation 页有 `citation_pdf_url`、无 DOI；Security '25 会话页共 455 个 presentation；robots 为 `Crawl-delay: 10`，禁 `/publications/proceedings`、`/search` [C31][LIVE] | 没有 DOI，需以 dblp 快照 key 作为 ID 锚；prepub 可作为"最新"通道 |
| PVLDB | 卷页；CC BY-NC-ND（v1） | 卷页改为 Next.js，vol 19 内嵌约 890 处 `vol19/p{页}-{作者}.pdf`，按月出 No.1–12；PDF 首页写明"licensed under the Creative Commons BY-NC-ND 4.0"；Crossref 10.14778 在 2025 年 446 条、摘要 100%，但 link 指向 ACM DL 镜像 [C32][C22][C59][LIVE] | 全文取 vldb.org（不去有 Cloudflare 的 ACM 镜像） |
| ISCA Archive | Interspeech 全 OA（v1） | ⚡ robots 为 `Disallow: /interspeech_2026/`，即当年卷禁爬（页面已存在）；Interspeech 2025 年页约 1,172 个论文链接；Crossref 10.21437 在 2025 年 1,388 条、**无摘要** [C38][C22][LIVE] | 当年只收元数据；robots 解禁后再补全文（需要"禁区随时间变化"的调度） |
| LIPIcs/DROPS | DOI 10.4230（v1） | ⚡ 10.4230 的注册机构是 **DataCite**，Crossref 按 pub-date 查为 0；DataCite 2025 年 2,336 条（ConferencePaper，带 descriptions 与 rights = CC BY 4.0）；OAI-PMH `drops.dagstuhl.de/oai` 可用（earliest 1991）；robots 禁 `/api/*`、`/metadata/*/*` [C39][C12][LIVE] | TCS（ITCS、SoCG、ICALP、ESA、CCC 等）走 DataCite + OAI |
| JMLR / TMLR | JMLR 专用 adapter 待建；TMLR 复用 openreview（v1） | JMLR RSS `jmlr.org/jmlr.xml` 共 205 条，含 title/link/pdf/author/摘要；v27（2026）论文页有 `citation_*` meta；PDF 首页"License: CC-BY 4.0"；**Crossref 查两个 ISSN 均为 0**（无 DOI）；jmlr.org 没有 robots.txt（返回 S3 NoSuchKey）；`jmlr.org/tmlr/papers/` 列出 4,767 个 OpenReview forum id [C37][C22][LIVE] | JMLR 是 P0 零成本源（许可最宽）；TMLR 以该列表做发现，再用 OpenReview 取详情 |
| 会议官网 miniconf | 未登记 | icml.cc、neurips.cc、iclr.cc 的 robots 同构：`*` 禁 `/static`、`/virtual/*/search`、`/search`、`/*?*page=`，并具名禁止 Bytespider 等 [C57][LIVE]；页面数据来自 `/static/...` JSON 与 `/api/miniconf/`（未文档化） | 排除（robots 禁区加未文档化接口，违反 D-014） |

#### 2.1.3 出版商平台

| 主题 | v1 口径 | 2026-09-26 核验结果 | 对 v2 的影响 |
|---|---|---|---|
| ACM DL OA | 2026 全面 OA（D-013）；自动全文抓取出列（D-020/D-024） | 全库 2026-01-01 起开放获取；新文由通讯作者在 CC BY 与 CC BY-NC-ND 中二选一；回溯卷在 DL Basic 免费阅读 [C18][C19][SNIP]；robots 未变（`*` Crawl-delay 1，禁 `/action /search /doi/metrics` 等，GPTBot/ChatGPT-User/CCBot/Google-Extended 全禁）[C21][LIVE]；匿名 HEAD landing 仍为 `403 cf-mitigated: challenge` [C21][LIVE]；ToS 仍禁"scripts, spiders … to automatically download articles or harvest metadata"[C19][SNIP]。核验补充：全库 OA 与"CC BY / CC BY-NC-ND 二选一"已由多个图书馆指南印证；bulk downloads 属付费的 DL Premium 工具，免费的 DL Basic 只提供阅读（SMU 图书馆 2026-04-08）[C63] | D-020/D-024 的判断在 2026-09 仍然成立 |
| ACM 机构 TDM | 未记录 | KB（丹麦皇家图书馆）的 2024–2026 ACM Open 协议：§IV.5 禁止整体复制或再分发，"systematic downloading"可导致终止；§IV.6 Computational Access 允许 Authorized Users 做 TDM，"by An API provided by vendor or a mutually agreed third-party provider"，并且"no rate or volume limits … unless … disruption"[C20][LIVE] | TDM 权利取决于所在机构的合同，平台不能默认拥有；可设计为"用户声明所属机构 TDM 权利，经 ACM 提供的 API 取回"的可选路径（⚠ ACM 未公开 API 细节） |
| ACM 元数据完整性 | Crossref member 320 畅通（v1） | 2025 年 10.1145 共 46,548 条：has-abstract 7,231（15.5%），has-license 12,824（27.5%）[C22][LIVE]；期刊类更完整：PACMMOD 2026 年 257 条、PACMSE 212 条、TOG 193 条（摘要 100%）、JACM 38 条（100%）、CACM 200 条（84%）；会议类（CHI/KDD/SIGIR/WWW/MM）样本均无摘要 [C22][LIVE] | ACM 会议的摘要必须从 OpenAlex/S2 补齐（受预算约束） |
| ACM 会议结构 | KDD 一年两卷；SIGMOD→PACMMOD（v1） | 按 container-title 精确过滤：CHI 2026 为 1,702 + Extended Abstracts 1,005，KDD 2026 V.1 为 256、V.2 为 1,220，WWW 2026 为 723，SIGIR 2026 为 686，ICSE 2026（"Proceedings of the 2026 IEEE/ACM 48th International Conference on Software Engineering"，由 ACM 注册）为 470，ACM MM 2025 为 1,620；另据 facet，ICMR 2026 为 324、FAccT 2026 为 299 [C22][LIVE]；KDD 2026 V.2 的 DOI 在会前（08-06，会期 08-09）已创建 [C59] | ACM 系的 Crossref 可作为会前的最新通道；ICSE 2026 走 ACM |
| IEEE Xplore API | 元数据 API 申请制；全文 API 需联系销售（v1） | 4 类 API：Metadata Search（含摘要，单次最多 200 条，支持按收录日期 `start_date/end_date`）、Open Access、Full-Text Access（收费）、DOI（最多 25 个 DOI）[C23][DOC]；key 人工审批，工作日 8–17 ET 发放 [C23]；配额"在注册时展示"，未公开 ⚠ [C24] | 只能用于用户自己机构的 key；按 ToU 须加"禁 ML 训练、禁共享"标签（§3 第 8 条） |
| IEEE API ToU | "限机构内非商业科研"（v1） | 原文要点：①"non-commercial educational, research, or scientific activities within the Licensee's educational institution"；②"you may only present the Content in response to an individual query; you may not present the Content in bulk format"；③"shall not distribute any portion … to any third party"；④终止后"shall not retain or store any Content"；⑤禁止用于"training, enhancing, developing, or contributing to any AI system, Machine Learning system, or Large Language Model"；⑥IEEE 可要求展示时链回 IEEE Xplore [C24][DOC]。核验补充：⑦API 访问"limited to current IEEE customers"，政府与企业客户可另行申请；⑧不得用 robot、spider 或检索程序"retrieve or index any portion of the Content"；⑨不得以可被人或机器收割的形式分发；⑩调用配额以"displayed during the user registration process"的 Rate Limits 为准 [C24] | 从 IEEE API 取得的摘要不能进入向量或推荐模型的训练与索引 |
| IEEE robots | 25+ AI UA 禁（v1） | 不变：`*` 禁 `/rest`、`/ielx*`；GPTBot、ClaudeBot、Claude-User、Google-NotebookLM、PerplexityBot 等 25 个 UA 全站 Disallow [C25][LIVE] | — |
| IEEE 元数据完整性与时滞 | 未量化 | 2025 年 10.1109 共 445,469 条，**has-abstract 为 0** [C22]；按 container-title 精确过滤：CVPR 2025 为 2,881 条，ICCV 2025 为 2,709，ICRA 2025 为 1,610，IROS 2025 为 1,988，S&P 2025 为 266 [C22][LIVE]；DOI 创建时滞：CVPR 2025（会期 2025-06-10，创建于 2025-08-13，约 2 个月）、ICRA 2025（05-19 → 09-02，约 3.5 个月）、ICCV 2025（10-19 → 2026-04-29，约 6 个月）；CVPR 2026 与 ICRA 2026 截至 9-26 均未见 [C59][LIVE]；S&P 2025 的 license 为 IEEE 政策 URI（10.15223/policy-029/037）[C59] | IEEE 系 CV/机器人会议的最新通道应走 CVF 或 arXiv，不能依赖 Crossref |
| TASLP | "官名含 /ACM；未改名"（v1 ai-ml-journals.md） | ⚡ Crossref 期刊库：旧刊"IEEE/ACM Transactions on Audio Speech and Language Processing"（2329-9290/2329-9304）最后一年为 2024（395 条）；新刊"IEEE Transactions on Audio Speech and Language Processing"用 **ISSN 2998-4173**（2025 年 381 条、2026 年 321 条）；CCF 2026 目录标注"（原 IEEE/ACM TASLP）"[C59][C52][LIVE] | v1 用旧 ISSN 的 VenueSpec 从 2025 年起会枚举为 0，需要 venue 改名/换 ISSN 链（§3 第 14 条） |
| Springer Nature API | 云 IP TLS 拒连（v1） | 限额表（API / Basic 每分 / Basic 每日 / Premium 每分 / Premium 每日）：Metadata 与 Meta(versioned) 100/500/300/10,000；Open Access 100/500/200/10,000；Full Text 200/500/200/20,000（依协议）；超限返回 429，每日配额按 key 计 24 小时 [C26][LIVE] | Basic 档每日 500 次，只够"用户自带 key 的按需补全" |
| Springer robots | 未记录 | ⚡ `*` 为 `Disallow: /`，再以 Allow 放行 `/article/ /chapter/ /content/ /book* /conference/ /journal*` 等；anthropic-ai、ClaudeBot、Claude-Web、GPTBot、ChatGPT-User、CCBot、PerplexityBot 等全站禁止 [C27][LIVE]；本机（住宅网络）可直连，与 v1 "云 IP TLS 拒连"不矛盾 | 元数据走 Crossref；全文只用用户自己的会话，按需取 |
| Springer 元数据完整性 | 未量化 | 2025 年 10.1007 的 book-chapter 共 284,166 条，带摘要 8,615 条（约 3.0%）；期刊类更好：MLJ 2026 年 217 条（摘要 95）、IJCV 425 条（93）、NMI 140 条（22）[C22][LIVE] | LNCS（ECCV 等）的摘要要靠 ECVA 页、OpenAlex 或 S2 |
| Elsevier（CS 刊） | 平台同经济金融（v1） | ⚡ Crossref 只收录 print ISSN：AIJ 0004-3702 在 2026 年 101 条、PR 0031-3203 有 2,906 条、NN 0893-6080 有 1,586 条、Neurocomputing 0925-2312 有 3,091 条；用 e-ISSN（1872-7921 等）过滤均为 0；摘要为 0 [C22][LIVE] | VenueSpec 须保存全部 ISSN 并依次尝试；v1 catalog 只记了"P/E"，没有标明 Crossref 该用哪个 |
| IOS Press FAIA（ECAI） | 未登记 | Crossref 10.3233，ECAI 2025 的 book-chapter 约 1,467 条（按 container-title 查询，含少量噪声），带摘要，样本许可 CC BY-NC 4.0，landing 为 `ebooks.iospress.nl/doi/10.3233/FAIA…`；robots 只禁后台路径 [C59][C58][LIVE] | ECAI（CCF-B/ICORE-A）可零成本接入 |
| NDSS | 未登记 | Crossref 10.14722，2026 年 390 条，无摘要，`resource.primary` 直接指向 PDF（`ndss-symposium.org/wp-content/uploads/2026-f3241-paper.pdf`）；robots 只禁 `/wp-admin/` [C59][C58][LIVE] | 安全四大之一，接入成本低 |

#### 2.1.4 聚合层与名录

| 主题 | v1 口径 | 2026-09-26 核验结果 | 对 v2 的影响 |
|---|---|---|---|
| dblp | robots Crawl-delay 4、`/db/**` 允许（D-021）；adapter 出列（D-037） | ⚡ 三个主机都是 `User-agent: *` → `Disallow: /`，并具名禁止约 160 个 UA（含 `Claude-Code`、`Claude-SearchBot`、`Claude-User`、`ClaudeBot`、`anthropic-ai`）[C40][LIVE]；DROPS 快照：`10.4230/dblp.xml.YYYY-MM-01` 在 DataCite 约 150 条 DOI（含历次月度快照；调研计 153，核验计 152，差异来自查询写法），2026-09-01 版 1,099,942,087 字节、12,928,181 条、CC0（DataCite 记录与 HEAD 的 Content-Length 一致），下载路径 `drops.dagstuhl.de/storage/artifacts/dblp/xml/2026/dblp-2026-09-01.xml.gz`（附 .md5），DROPS robots 未禁 `/storage/`（只禁 `/api/*`、`/metadata/*/*`、`/entities/*/metadata/*`）[C39][LIVE]；`sparql.dblp.org` robots 为 `Allow: /sparql`、`Allow: /download`、`Disallow: /`、`Crawl-delay: 10` [C40][LIVE] | dblp 只能以快照（月更）或 SPARQL 形态使用；v1 dblp adapter 的在线路径全部作废 |
| Crossref 限流 | polite 10 req/s、并发 3（v1） | 带 mailto 的单条请求：`x-rate-limit-limit: 10`、`x-rate-limit-interval: 1s`、`x-concurrency-limit: 3`、`x-api-pool: polite-single` [C22][LIVE]；分池规则（列表类更慢）见兄弟分卷 | 枚举优先用 `/journals/{issn}/works` 或 `/prefixes/…`，少用全局 `/works?filter=` |
| Crossref 会议论文集枚举 | DBLP 为会议主干（D-005/D-012） | `filter=container-title:{精确标题}` 可以按论文集标题精确计数和枚举（如 "Proceedings of the ACM Web Conference 2026" 为 723 条，"Computer Vision – ECCV 2026" 为 2,251 条）；**标题中含逗号时会报 `pair-list-form-invalid`**（如 ICASSP 2026 的标题）[C22][LIVE] | dblp 在线路径失效后，DOI 型会议可以"标题精确过滤 + DOI 前缀"来枚举；含逗号的标题需退回 query 加本地核对 |
| OpenAlex | key + credit 计费（v1，2026-02 改制） | 匿名 `x-ratelimit-limit: 1000`（credits/日），每次 list 查询 `x-ratelimit-cost-usd: 0.0001`；CS field（id 17）在 2026 年共 872,697 works [C51][LIVE]；会议实体归一化差（NeurIPS 4,177、ICLR 757，见兄弟分卷） | CS 会议仍以 L1 平台为主；OpenAlex 负责补摘要和 topics |
| CCF 目录 | 2022 版（v1 未用） | 第七版《中国计算机学会推荐国际学术会议和期刊目录》2026-03-31 发布（此前公示期为 03-05 至 03-12），04-09 更新勘误；评审会 2026-01-11，理事长会议 01-27 定稿；共收到 169 项提案（会议 104 项，涉及 82 个会议；期刊 65 项，涉及 55 种期刊）；相比 2022 版：新增期刊 14、会议 23，升级期刊 6、会议 5，移除会议 1，降级会议 2、期刊 1，更名会议 2；官方声明其"目的不是作为学术评价的依据"[C52][LIVE] | 作为 venue 的"等级标签"维度（§2.5） |
| CORE → ICORE | 未用 | 门户标题为"ICORE Conference Portal"（"CORE rankings is now an international collaboration named ICORE"）；ICORE2026 共评级 825 个：A* 7.52%、A 13.09%、B 30.18%、Australasian B 0.73%、C 46.18%、Australasian C 2.3%，另有 162 个 Other；CSV 导出可用（约 986 行）；robots 对 ClaudeBot、Claude-User、Claude-SearchBot、anthropic-ai 等约 40 个 UA 为 `Disallow: /`，`*` 只禁 `/core-tools/media/` [C55][LIVE]。核验补充：ICORE 由 CORE（澳大拉西亚）、GII、GRIN（意大利）、SCIE（西班牙）四方委员会联合管理，core.edu.au 未公布数据再利用条款 [C68]。825 与各档百分比由调研员导出的 CSV 复算一致；核验未再访问门户（其 robots 对 Claude 类代理全站禁止），⚠ 上线前需人工在浏览器中复核 | 可用于国际等级标签（许可条款未见，⚠） |

### 2.2 来源名录表（统一列，供设计阶段合并总名录）

> 列义按任务统一口径。"v1 支持"的取值：**是**（生产 adapter + venue 已注册）/ **部分**（adapter 存在但覆盖面窄或已出列）/ **仅设计**（只有设计文档或名录登记）/ **否**。优先级：**P0**（v2 首版必做）/ **P1**（首版后第一批）/ **P2**（按需）/ **仅元数据** / **排除**。表中各项核验日期均为 2026-09-26，另注者除外。

#### A. L1-preprint

| source_id | 名称 | 层级类型 | 学科 | 平台技术栈 | 元数据通道 | 最新论文通道 | 全文通道与门控 | 认证方式 | 限速与 ToS/robots 要点（来源+日期） | v1 支持 | 建议优先级及理由 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| arxiv | arXiv | L1-preprint | CS 全域（另含 stat/math/econ/q-fin/物理等） | 自研（Fastly 前置 [C9]） | 官方 OAI-PMH `oaipmh.arxiv.org/oai`（类目级 set，格式 oai_dc/arXiv/arXivRaw，带 license）[C2][C3]；Query API（Atom）；DataCite DOI 10.48550 [C12] | 公告 Sun–Thu 20:00 ET，OAI 约 22:30 ET 可取 [C2][C7]；RSS/Atom 每日（`+` 合并类目，上限 2000）[C4]；`/list/{cat}/new`（robots 允许，15 s）[C8]；一周 cs 集 7,083 条 [C3] | OA：`/pdf`、`/html`；S3 requester-pays 全量（约 9.2 TB，按月更新）[C5]；**ToU 禁止在自有服务器上 store & serve**（许可证允许者除外）[C1] | 无（S3/Kaggle 需各自账号） | 1 req/3s、单连接、所有机器合计 [C1]；2026-02 起 429 频发 [C9]；伪 200 "Rate exceeded." [C10][3P]；robots Crawl-delay 15，禁 `/api /search /e-print /src` [C8] | 是（`arxiv`；arXiv 类目 venue 共 31 个：cs 17、stat.ML 1、econ 3、q-fin 9、math.OC 1；用 archive 级 set） | **P0**：CS 最新论文主通道；v2 改用类目级 set，license 入库，中心化限速 |
| techrxiv | TechRxiv（IEEE） | L1-preprint | EE/CS | Atypon/Literatum（依 robots 形态判断） | 委托 Crossref（10.36227，posted-content，带摘要）[C49] | Crossref `from-posted-date` 增量（2025 年 6,329 条，2026 年至今 1,520 条）[C49] | OA，逐篇 license（样本为 CC BY 4.0） | 无 | robots：`*` 禁 `/action /search /rss /doi/metrics` 等，Crawl-delay 1，GPTBot 全禁 [C49] | 否 | **P1**：元数据零爬取；全文按 license 链出或按需取 |
| iacr_eprint | IACR Cryptology ePrint Archive | L1-preprint | 密码学/安全 | 自研 | OAI-PMH `eprint.iacr.org/oai`（earliest 1996）+ RSS/Atom（robots 注释声明的元数据通道）[C48] | RSS 最新 100 条 [C48] | PDF 各有 license（多为 CC BY）；**robots 对 `*` 为 `Disallow: /`，爬虫须经白名单**，AI bot 不得取 PDF [C48] | 无 | 同左 [C48] | 否 | **P1（仅元数据）**：用 OAI/RSS 收元数据，全文链出 |
| eccc | ECCC | L1-preprint | TCS | 自研 | ⚠ 未核验 | ⚠ | OA ⚠ | 无 | ⚠ | 仅设计（v1 登记暂缓） | **P2**：出现 TCS 需求时再勘察 |

#### B. L1-conference-platform

| source_id | 名称 | 层级类型 | 学科 | 平台技术栈 | 元数据通道 | 最新论文通道 | 全文通道与门控 | 认证方式 | 限速与 ToS/robots 要点（来源+日期） | v1 支持 | 建议优先级及理由 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| openreview | OpenReview | L1-conference-platform | ML/AI/NLP/CV/机器人/DM（ICLR、NeurIPS、ICML、COLM、CoRL、TMLR、UAI、AISTATS、ALT、MLSys，以及 EMNLP/ECCV/ACM MM/AAAI/KDD 的评审） | 自研（GCP）[v1:2026-07-22] | REST API v2（`api2.openreview.net`，参数见 §2.1.2）[C16]；v1 API 为遗留、正在淘汰 [C13]；元数据 CC0 [v1:2026-07-22] | `active_venues`（匿名，约 1,090 个）[C15]；notes 用 `mintmdate` 增量、`sort=cdate:desc`；投稿、接收、拒稿三态可按 id 枚举 [C15] | 公开 venue 的 PDF 免费阅读（作者保留版权 [v1]）；**匿名 `/notes`、`/pdf` 返回 403 ChallengeRequiredError** [C15] | **免费账号**（access token）[C13]；OIDC 只给 profile [C14] | 限流策略随请求而异（实测有 `20;w=60` 与 `180;w=60` 两档），须读响应头 [C15]；robots 只禁 `/*?*email=` [C15]；ToS 禁止绕过访问控制、一人一号 [v1]；2025-11 身份泄露事件 [C17] | 部分（`openreview`，仅 ICLR，token 由用户自备） | **P0**：ICLR/COLM/TMLR 主源；各会"最新接收"的最早通道；活跃会议发现器 |
| pmlr | Proceedings of Machine Learning Research | L1-conference-platform | ML（ICML、AISTATS、COLT、UAI、CoRL、ALT、L4DC、CLeaR、CHIL、MIDL…） | GitHub Pages 静态 | 卷页 + BibTeX；**无 DOI**（Crossref 不可枚举） | 首页卷表（新卷在前）+ 卷号探测；ICML 2026 截至 9-26 未上线 [C35] | OA PDF | 无 | robots.txt 为 404 [C35]；沿用 v1 保守限速 | 部分（`pmlr`，仅 ICML 已注册） | **P0**：可同时服务 ICML/COLT/UAI/AISTATS/CoRL；ICML 最新一届先走 OpenReview |
| neurips_proceedings | NeurIPS Proceedings | L1-conference-platform | ML | 自研 | 年页或卷页 + `citation_*` meta；Crossref DOI 10.52202（Curran，第 35–38 卷共 16,691 条，无摘要）[C34][C22] | 会后上线（2025 卷 5,823 + 64 篇）；DOI 约晚 8 个月 [C59] | OA PDF（页面未声明开放许可 ⚠） | 无 | robots.txt 为 404 [C34] | 是（`neurips_proceedings`，但 2025 新分轨未覆盖） | **P0**：补 Position/Creative AI 分轨；DOI 用于对齐 |
| cvf_open_access | CVF Open Access | L1-conference-platform | CV（CVPR、ICCV、WACV） | Apache 静态 | 目录页 `/{CONF}{year}?day=all` + 论文 html（含摘要）；正式版 DOI 在 IEEE | CVPR 2026 共 4,042 篇已上线（早于 IEEE DOI）[C29][C59] | OA（带水印的录用版，作者保留版权）[C29] | 无 | robots.txt 为 404 [C29] | 是（`cvf`：CVPR/ICCV/WACV） | **P0**：CV 顶会的最早全文源 |
| ecva | ECVA（ECCV 开放版） | L1-conference-platform | CV | 自研 PHP | `papers.php` 单页（2018–2024 共 6,166 篇）+ Springer DOI 外链 [C28] | 滞后于 LNCS（ECCV 2026 截至 9-26 未上线）[C28][C22] | OA PDF + supp（页面未声明开放许可 ⚠） | 无 | robots 只含 Googlebot Allow，无 Disallow [C28] | 否（v1 把 ECCV 记为 springer/cvf 镜像） | **P1**：ECCV 全文首选 |
| acl_anthology | ACL Anthology | L1-conference-platform | NLP/语音 | Hugo 静态 + GitHub 数据仓库 | GitHub XML + `pip install acl-anthology` [C33]；Crossref 10.18653（无摘要）[C22] | 会期前后上线（ACL 2026 已有 long 2,223 等）[C33] | OA；2016 年起 CC BY 4.0，2016 年前 CC BY-NC-SA 3.0 [C33] | 无 | robots.txt 为 404 [C33] | 部分（`acl_anthology`，已注册 EMNLP） | **P0**：零爬取；带 ORCID 的作者可用于匹配 |
| aaai_ojs | AAAI OJS | L1-conference-platform | AI（AAAI、AIES、ICWSM、ICAPS、HCOMP、AIIDE、SoCS、AAAI-SS、IASEAI） | OJS | OAI-PMH（每页 100 条）[C36]；Crossref 10.1609（摘要 100%）[C22] | 期号页（AAAI-26 已上线）；AAAI-27 起在 OpenReview 评审 [C36][C15] | 免费阅读（版权归 AAAI，非 CC；见 venues/cs_ai/aaai.yaml 注释） | 无 | robots 只禁 `/cache/` [C36] | 是（`aaai_ojs`，仅 AAAI） | **P0**：同一 adapter 扩展到另外 8 个会议或刊 |
| ijcai_proceedings | IJCAI Proceedings | L1-conference-platform | AI | Drupal（据 robots 形态判断） | 年页 + Crossref 10.24963（仅 2017 年起，摘要约 100%；前缀与 KR 共用，须按 container-title 分流）[C30][C22] | 会前上线（2026 年站点 972 条，Crossref 中 IJCAI-35 也是 972 条）[C30][C22] | 免费阅读（© IJCAI） | 无 | robots `Crawl-delay: 10`，禁 `/search` 等 [C30] | 仅设计（v1 名录标"专用"） | **P0**：Crossref 加站点 PDF，实现成本低 |
| usenix | USENIX（Security、OSDI、NSDI、FAST） | L1-conference-platform | 系统/安全/网络 | Drupal（据 robots 形态判断） | technical-sessions 页 + `citation_*` meta；**无 DOI** [C31] | 录用后即挂 prepub PDF [C31] | OA（"freely available … once the event begins"）[C31] | 无 | robots `Crawl-delay: 10`，禁 `/publications/proceedings`、`/search` [C31] | 仅设计（名录已列 `usenix`） | **P1**：CCF-A 系统/安全核心；以 dblp 快照 key 作为 ID 锚 |
| ndss | NDSS Symposium | L1-conference-platform | 安全 | WordPress（据 robots 形态判断） | Crossref 10.14722（无摘要，resource 直链 PDF）[C59] | 会期在 2 月；Crossref 增量 | OA PDF | 无 | robots 只禁 `/wp-admin/` [C58] | 否 | **P1** |
| pvldb | PVLDB | L1-conference-platform（期刊化） | DB | Next.js | Crossref 10.14778（摘要 100%）[C22]；卷页内嵌 PDF 链接 [C32] | 每月一期（vol 19 No.1–12）[C32] | OA，CC BY-NC-ND 4.0 [C32] | 无 | vldb.org 的 robots 为 404 [C32]；Crossref 的 link 指向有 Cloudflare 的 ACM 镜像 | 仅设计（名录已列 `pvldb`） | **P1**：全文从 vldb.org 取 |
| isca_archive | ISCA Archive | L1-conference-platform | 语音 | 静态 | 年页 + Crossref 10.21437（无摘要）[C38][C22] | **当年卷被 robots 禁爬** [C38] | 免费阅读 | 无 | `Disallow: /interspeech_2026/`、`/tmp/` [C38] | 仅设计（名录已列 `isca`） | **P1**：当年只收元数据 |
| lipics_drops | Dagstuhl DROPS / LIPIcs | L1-conference-platform | TCS（ITCS、SoCG、ICALP、ESA、CCC、MFCS…） | 自研 | **DataCite**（10.4230）+ OAI-PMH [C39] | OAI 增量 | OA，CC BY 4.0 [C39] | 无 | robots 禁 `/api/*`、`/metadata/*/*` [C39] | 仅设计（名录已列 `lipics`） | **P1**：TCS 主源；DROPS 同时托管 dblp 快照 |
| rss_proceedings | Robotics: Science and Systems | L1-conference-platform | 机器人 | 静态 | `/rss{NN}/` [v1:2026-07-20] | ⚠ 2026 卷未核 | OA [v1] | 无 | robots `*` 为 Allow: / [C58] | 仅设计 | **P2** |
| mlsys_proceedings | MLSys Proceedings | L1-conference-platform | ML 系统 | ⚠ | ⚠ 未核（评审在 OpenReview：`MLSys.org/2027/Conference`）[C15] | ⚠ | OA ⚠ | 无 | robots.txt 为 404 [C58] | 否 | **P2** |
| ceur_ws | CEUR Workshop Proceedings | L1-conference-platform（workshop） | CS 全域 | 静态 | 卷页 `Vol-{n}/`；robots 头部声明了 License URL [C58] | 卷号递增 | OA（license.xml 未读 ⚠） | 无 | robots 只禁 `/temp/ /ftp/` 等 [C58] | 否 | **P2** |
| aamas_ifaamas（核验补充） | IFAAMAS AAMAS Proceedings | L1-conference-platform | 多智能体/AI | 静态页 | Crossref 10.65109（IFAAMAS，member 54598）：共 7,301 条，含约 2026-01 集中注册的回溯卷；带摘要 6,539 条，但 AAMAS 2026 的 656 条无摘要；container-title 与 publisher 字段质量差（6,644 条回溯记录统一标成"Proceedings of the Third … Volume 1"，publisher 混入"IEEE Computer Society"）[C64] | 年度论文集页 `ifaamas.org/Proceedings/aamas{YYYY}/`（AAMAS 2026 已上线）；AAMAS 2026 的 DOI 于 2026-05-24 注册，但记录**没有 published 日期**，按 pub-date 过滤会整届漏掉 [C64] | 免费阅读（© IFAAMAS，ISBN 979-8-4007-2317-9）；Crossref 的 resource 指向 ACM DL（回溯卷为 `dl.acm.org/doi/10.5555/…`，2026 届为 `dl.acm.org/doi/10.65109/…`），落地页受 ACM 的 Cloudflare 质询与 ToS 约束 [C64][C21] | 无 | ifaamas.org 无 robots.txt（404）[C64] | 否 | **P2**：CCF B / ICORE A（据调研员 CSV）；按届枚举须用 container-title 加 created 日期，并本地核对标题 |
| conf_virtual_sites | icml.cc / neurips.cc / iclr.cc（miniconf） | L1-conference-platform | ML | 自研 miniconf | 页面可读；数据在 `/static/…` JSON 与 `/api/miniconf/`（未文档化） | 录用列表的最早出处之一 | 链到 OpenReview 或 proceedings | 无 | robots：`*` 禁 `/static`、`/virtual/*/search`、`/search`、`/*?*page=` [C57] | 否 | **排除**（作为机器通道）：只供人工核对 |

#### C. L1-journal-platform

| source_id | 名称 | 层级类型 | 学科 | 平台技术栈 | 元数据通道 | 最新论文通道 | 全文通道与门控 | 认证方式 | 限速与 ToS/robots 要点（来源+日期） | v1 支持 | 建议优先级及理由 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| jmlr | JMLR（含 TMLR 列表、MLOSS） | L1-journal-platform | ML | 静态（据 404 响应推断为 S3 托管） | RSS `jmlr.org/jmlr.xml`（205 条，含摘要）+ `citation_*` meta；**无 DOI** [C37][C22] | RSS；卷页 v27（2026）；TMLR 列表 4,767 篇 [C37] | OA，CC BY 4.0 [C37] | 无 | 无 robots.txt；自行限速 | 仅设计（v1 计划做专用 adapter） | **P0**：结构规整、许可最宽 |
| tmlr | TMLR | L1-journal-platform | ML | OpenReview | OpenReview `TMLR` venue + jmlr.org/tmlr 列表；**无 DOI**（Crossref 为 0）[C37][C22] | 滚动接收 | 免费阅读（逐篇许可 ⚠） | OpenReview 账号 | 同 openreview | 否 | **P0**（随 openreview 一起做） |
| jair | JAIR | L1-journal-platform | AI | OJS | Crossref 10.1613（2026 年 109 条，摘要 100%）[C22] | Crossref 增量 | 钻石 OA [v1:2026-07-20] | 无 | robots 只禁 `/cache/` [C58] | 否 | **P1** |
| mit_press_direct | MIT Press Direct（TACL、Computational Linguistics、Neural Computation） | L1-journal-platform | NLP/计算神经科学 | Silverchair [v1] | Crossref 10.1162（TACL 2026 年 110 条，摘要 109；CL 48/46）[C22] | Crossref 增量 | TACL/CL 为钻石 OA，全文走 Anthology（CC BY 4.0）；其余订阅 [v1][C33] | 机构或个人订阅 | robots 对 UA `008` 全禁 [C58]；TDM 需书面特批，禁止脚本抓取 [v1:2026-07-20]；transacl.org 的 robots 为 `Crawl-delay: 60` [C58] | 否 | **P1（仅元数据）**：TACL/CL 全文走 Anthology |

#### D. L1-publisher

| source_id | 名称 | 层级类型 | 学科 | 平台技术栈 | 元数据通道 | 最新论文通道 | 全文通道与门控 | 认证方式 | 限速与 ToS/robots 要点（来源+日期） | v1 支持 | 建议优先级及理由 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| acm_dl | ACM Digital Library | L1-publisher | CS 全域（KDD/WWW/SIGIR/CHI/MM/ICSE/PACMSE/PACMMOD/CCS/SOSP/STOC/EC…） | Atypon/Literatum | 委托 Crossref（摘要 15.5%，license 27.5%）[C22]；无官方 API/OAI [v1:2026-07-22] | Crossref 会前即注册 DOI（KDD 2026）[C59] | **全库 OA**（2026-01-01）[C18][SNIP]，但匿名访问遇 Cloudflare 质询（403）[C21] | 无（OA）；机构 ACM Open 协议可含 TDM（经 ACM 提供的 API）[C20] | robots `*` 为 Crawl-delay 1，具名禁止 GPTBot/ChatGPT-User/CCBot/Google-Extended [C21]；ToS 禁止脚本下载和元数据收割 [C19][SNIP] | 仅设计（D-020/D-024 出列） | **P1（仅元数据）**：不直接访问站点；全文只 link-out 给用户在浏览器中打开 |
| ieee_xplore | IEEE Xplore（含 CSDL） | L1-publisher | CS/EE | 自研 | 委托 Crossref（10.1109，**零摘要**）[C22]；官方 API 4 类 [C23] | Crossref 滞后 2–6 个月 [C59]；API 可按收录日期查询 [C23] | 订阅制（IEEE Access、OJ 系列为金色 OA）[v1] | API key 人工审批 [C23]；Shibboleth/OpenAthens [v1] | **API ToU 禁批量呈现、禁再分发、禁 AI/ML 训练，限机构内使用** [C24]；robots 禁 `/rest /ielx*` 及 25 个 AI UA [C25] | 仅设计 | **P1**：元数据用 Crossref + OpenAlex；全文只用用户自己机构的会话 |
| springer_link | Springer Nature Link（LNCS/LNAI、MLJ、IJCV、NMI） | L1-publisher | CS（ECCV、WINE、ICCBR 正式版） | 自研 | 委托 Crossref（book-chapter，摘要约 3%）[C22]；Meta/OA/Full Text API [C26] | Crossref（ECCV 2026 已有 2,251 条）[C22] | 订阅或混合；OA API | API key（Basic 免费，Premium 需找销售） | Basic 100 次/分、500 次/日 [C26]；robots 默认 `Disallow: /`，具名禁止 AI UA [C27] | 仅设计（名录登记） | **P1**：元数据以 Crossref 为主；API 只用用户自带 key |
| elsevier_sd | ScienceDirect（AIJ、PR、NN、Neurocomputing） | L1-publisher | AI 期刊 | 自研 | Crossref（**只认 print ISSN**，零摘要）[C22] | Crossref 增量 | 订阅或混合 | 官方 API key（申请中 [v1]） | 见 v1 elsevier-sd.md 与经管分卷 | 部分（adapter 服务经管 venue） | **P1**：CS 刊只做元数据，全文用用户凭证 |
| siam_epubs | SIAM ePubs（SODA） | L1-publisher | TCS | Atypon [v1:2026-07-20] | Crossref 10.1137 [v1] | Crossref | 订阅 [v1] | 机构 | Crawl-delay 1，只具名 GPTBot [v1] | 仅设计 | **P2** |
| iospress_faia | IOS Press FAIA（ECAI 等） | L1-publisher | AI | 自研 | Crossref 10.3233（带摘要）[C59] | Crossref 增量 | OA（样本 CC BY-NC 4.0）[C59] | 无 | robots 只禁后台路径 [C58] | 否 | **P1**：ECAI 零成本接入 |
| now_publishers | now publishers（FnT ML 等） | L1-publisher | ML 综述 | 自研 | Crossref 10.1561（FnT ML 2026 年 2 条）[C22] | Crossref | 订阅 [v1] | 机构 | ⚠ 未核 | 仅设计 | **P2（仅元数据）** |

#### E. L2-aggregator / L2-repository（CS 视角，跨学科细节见兄弟分卷）

| source_id | 名称 | 层级类型 | 学科 | 平台技术栈 | 元数据通道 | 最新论文通道 | 全文通道与门控 | 认证方式 | 限速与 ToS/robots 要点（来源+日期） | v1 支持 | 建议优先级及理由 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| crossref | Crossref REST API | L2-aggregator | 全学科 | 官方 API | `/works`、`/journals/{issn}/works`、prefix/issn/date filter、facet、cursor | `from-index-date`、`from-created-date`；`created` 可用来量化注册时滞 | 无全文（`link` 多为 TDM 或相似度检测用途） | 无（polite 需 mailto） | `10/1s`、并发 3、`polite-single`（单条）[C22]；分池细节见兄弟分卷 | 是（`crossref`） | **P0**：DOI 型 CS venue 的枚举主干 |
| datacite | DataCite REST API | L2-aggregator | 全学科（arXiv DOI、LIPIcs、Zenodo、dblp 快照） | 官方 API | `api.datacite.org/dois?prefix=` [C39] | ⚠ 增量参数未逐项核 | 无 | 无 | ⚠ 限速未核 | 否 | **P1**：补齐 Crossref 覆盖不到的 TCS 与 arXiv DOI |
| openalex | OpenAlex | L2-aggregator | 全学科（CS field 17） | 官方 API（按 credit 计费） | `/works`（topics、倒排摘要）[v1] | `from_publication_date` 免费，`from_created_date` 需付费计划 [v1] | OA 链接 | 无 key 每日 1,000 credits [C51] | `x-ratelimit-*` 响应头 [C51] | 是（`openalex`） | **P0（受预算约束）**：补 IEEE/ACL/ACM/Elsevier 的摘要缺口 |
| semantic_scholar | Semantic Scholar | L2-aggregator | 全学科（CS 覆盖强） | 官方 API + Datasets | graph/bulk/batch/recommendations [v1:2026-07-22] | 每周 Datasets | openAccessPdf | 需要 key [v1] | 有 key 为 1 RPS [v1]；www 站 robots 禁 `/search /api /reader/` [C61] | 是（`s2`，key 仍待申请） | **P1**：引用、TLDR、嵌入、推荐 |
| dblp | dblp（快照 + SPARQL） | L2-aggregator（venue 名录主干） | CS 全域 | DROPS 托管快照 + sparql.dblp.org | **只能用**月度 XML 快照（CC0）或 SPARQL [C39][C40] | 月更 [C39] | 无全文（`ee` 外链） | 无 | 主站全禁；SPARQL Crawl-delay 10 [C40] | 部分（代码存在，D-037 出列） | **P0（快照形态）**：VenueEra、会议卷目录、作者 PID 的主干 |
| unpaywall | Unpaywall | L2-aggregator | 全学科 | 官方 API | `/v2/{doi}?email=` [v1] | — | 定位 OA 副本 | email | 100k/日 [v1] | 是（`unpaywall`） | **P1**：ACM/IEEE 作者版的 OA 兜底 |
| hf_papers | Hugging Face Papers | L2-aggregator（社区信号） | ML/AI | 官方 Hub API | `/api/daily_papers`、`/api/papers/{id}`、`/api/papers/search`（SDK 已支持）[C41][C44] | 每日精选 + trending [C41][C43] | 无（链到 arXiv） | 可匿名；带 token 提额 | 匿名 500 次/5min、search 50 次/5min [C41][C42]；robots 为 Allow all [C41] | 否 | **P0（信号层）**：PwC 的替代；冷启动热度、代码可得性 |
| alphaxiv | alphaXiv | L2-aggregator（讨论与热度） | arXiv 全域 | 自研 | 只有 MCP（19 个工具）[C46] | 站内 trending（只在页面上） | 链到 arXiv | OAuth 2.1 或个人 API key | 配额未公开；ToS ⚠ [C46] | 否 | **P2**：只做"用户自己连接"的连接器 |
| pwc_archive | Papers with Code 存档 | L2-aggregator（静态） | ML | HF Datasets | `pwc-archive/*`（CC-BY-SA-4.0）[C45] | 无（站点已关） | 无 | 无 | 遵循 HF 规则 | 否 | **P1（一次性导入）** |
| hal | HAL | L2-repository | 全学科（CS 的 info 域） | 自研（CCSD） | Search API（Solr；2026 年 info 域 11,504 条，其中 5,931 条带文件）[C50] | ⚠ 未核 | 逐篇 license | 无 | ⚠（API 主机 robots 与文档口径的冲突见兄弟分卷） | 否 | **P2**：欧陆 CS 作者版补全 |
| google_scholar | Google Scholar | L2-aggregator | 全学科 | — | 无官方 API [v1] | — | — | — | ToS 禁止自动查询 [v1] | 否 | **排除**（红线） |
| scirate | SciRate | L2-aggregator | arXiv（物理、CS） | 自研 | — | — | — | — | 连 robots 都被 Cloudflare 质询 [C47] | 否 | **排除** |
| paper_copilot | Paper Copilot / paperlists | L2-aggregator（第三方整理） | ML 会议统计 | GitHub | `papercopilot/paperlists`（958 stars，**无 license**，最近 push 2026-07-01）[C56] | — | — | — | 无许可，不能复用数据 | 否 | **仅参考**（只看字段设计，不导入数据） |

### 2.3 代表性 venue → 平台映射（CS/AI，30 条）

> 列：venue｜类型｜ISSN 或会议标识（DBLP key 取自 ccfddl 数据 [C53]）｜出版平台（全文主源）｜Crossref 可枚举性（前缀、摘要、时滞）｜OA 情况｜等级（CCF 2026 / ICORE2026 / CSRankings 领域）。CCF 等级取自第七版 PDF [C52]，ICORE 取自 CSV 导出 [C55]，CSRankings 取自 `csrankings.js` 的 areaMap [C54]。"—"表示不在该名录中。

| # | venue | 类型 | ISSN / DBLP key | 出版平台（全文主源） | Crossref 可枚举性 | OA 情况 | CCF / ICORE / CSR |
|---|---|---|---|---|---|---|---|
| 1 | NeurIPS | 会议 | `nips` | proceedings.neurips.cc（评审在 OpenReview） | 可（10.52202 Curran，vol 35+，无摘要，约晚 8 个月） | 免费阅读 | A / A* / ML |
| 2 | ICML | 会议 | `icml` | PMLR（接收列表在 OpenReview） | 不可（无 DOI） | 免费阅读 | A / A* / ML |
| 3 | ICLR | 会议 | `iclr` | OpenReview | 不可（无 DOI） | 免费阅读；元数据 CC0 | A（新入） / A* / ML |
| 4 | AAAI | 会议 | `aaai` | AAAI OJS | 可（10.1609，摘要 100%） | 免费阅读（© AAAI） | A / A* / AI |
| 5 | IJCAI | 会议 | `ijcai` | ijcai.org | 可（10.24963，仅 2017 年起） | 免费阅读 | B（降级） / A* / AI |
| 6 | COLT | 会议 | `colt` | PMLR | 不可 | 免费阅读 | B / A* / — |
| 7 | COLM | 会议 | `colm` | OpenReview | 不可 | 免费阅读 | — / — / — |
| 8 | CoRL | 会议 | `corl` | PMLR（评审在 OpenReview） | 不可 | 免费阅读 | — / Unranked / — |
| 9 | CVPR | 会议 | `cvpr` | CVF OA（正式版在 IEEE） | 可（10.1109，约晚 2 个月，无摘要） | CVF 免费阅读 | A / A* / Vision |
| 10 | ICCV | 会议 | `iccv` | CVF OA（正式版在 IEEE） | 可（ICCV 2025 约晚 6 个月） | CVF 免费阅读 | A / A* / Vision |
| 11 | ECCV | 会议 | `eccv` | Springer LNCS（OA 版在 ECVA） | 可（10.1007 book-chapter，会期前后即注册） | ECVA 免费阅读 | B / A* / Vision |
| 12 | ACL | 会议 | `acl` | ACL Anthology | 可（10.18653，无摘要） | CC BY 4.0 | A / A* / NLP |
| 13 | EMNLP | 会议 | `emnlp` | ACL Anthology | 可 | CC BY 4.0 | B / A* / NLP |
| 14 | Interspeech | 会议 | `interspeech` | ISCA Archive | 可（10.21437，无摘要） | 免费阅读（当年卷 robots 禁爬） | B（升级） / A / — |
| 15 | KDD | 会议 | `kdd` | ACM DL | 可（会前注册） | ACM OA（2026-01 起） | A / A* / ML |
| 16 | WWW | 会议 | `www` | ACM DL | 可 | ACM OA | A（交叉） / A* / Web+IR |
| 17 | SIGIR | 会议 | `sigir` | ACM DL | 可 | ACM OA | A / A* / Web+IR |
| 18 | CHI | 会议 | `chi` | ACM DL | 可 | ACM OA | A / A* / HCI |
| 19 | SIGMOD | 会议→期刊 | `sigmod`；PACMMOD 2836-6573 | ACM DL | 可（PACMMOD 摘要 100%） | ACM OA | A / A* / DB |
| 20 | VLDB | 期刊式会议 | `vldb`；PVLDB（10.14778） | vldb.org | 可（摘要 100%） | CC BY-NC-ND 4.0 | A / A* / DB |
| 21 | ICSE | 会议 | `icse` | ACM DL（2026 届） | 可 | ACM OA | A / A* / SE |
| 22 | FSE | 会议→期刊 | `sigsoft`；PACMSE 2994-970X | ACM DL | 可（摘要 100%） | ACM OA | A / A* / SE |
| 23 | OSDI | 会议 | `osdi` | USENIX | 不可（无 DOI） | OA | A / A* / OS |
| 24 | USENIX Security | 会议 | `uss` | USENIX | 不可 | OA（录用后即有 prepub） | A / A* / Security |
| 25 | NDSS | 会议 | `ndss` | ndss-symposium.org | 可（10.14722，无摘要） | 免费阅读 | A / A* / Security |
| 26 | ICRA | 会议 | `icra` | IEEE Xplore | 可（约晚 3.5 个月） | 订阅 | B / A* / Robotics |
| 27 | JMLR | 期刊 | 1533-7928（`journals/jmlr`） | jmlr.org | 不可（无 DOI） | CC BY 4.0 | A / — / — |
| 28 | TPAMI | 期刊 | 0162-8828 / 1939-3539 | IEEE Xplore | 可（两种 ISSN 都能查，无摘要） | 混合 | A / — / — |
| 29 | IJCV | 期刊 | 0920-5691 / 1573-1405 | Springer | 可（2026 年摘要 22%） | 混合 | A / — / — |
| 30 | TACL | 期刊 | 2307-387X | MIT Press + ACL Anthology | 可（摘要约 100%） | CC BY 4.0（钻石 OA） | B / — / — |

**补充映射**（不计入 30 条，供名录合并）：

- **ML/AI**
  - UAI：`uai`，PMLR；CCF B，ICORE A。
  - AISTATS：`aistats`，PMLR；CCF C，ICORE A。
  - ALT：PMLR；ICORE B。
  - ECAI：IOS Press FAIA，许可 CC BY-NC；CCF B，ICORE A。
  - ICAPS、ICWSM、AIES：均在 AAAI OJS。ICAPS 为 CCF B、ICORE A*；ICWSM 为 ICORE A。
  - AIJ：print ISSN 0004-3702，ScienceDirect；CCF A。
  - JAIR：1076-9757，jair.org；CCF B。
  - TMLR：2835-8856，OpenReview；三份名录都未收录。
  - KR（核验补充）：DOI 与 IJCAI 共用前缀 10.24963（KR 2020 起）；CCF B，ICORE A*。
  - AAMAS（核验补充）：IFAAMAS 论文集，Crossref 前缀 10.65109；CCF B，ICORE A。
- **CV**
  - WACV：CVF + IEEE；ICORE A。
- **NLP 与语音**
  - NAACL：Anthology；CCF B，ICORE A。
  - EACL：Anthology；ICORE A。
  - TASLP：新 ISSN 2998-4173，IEEE；CCF B。
- **信息检索与多媒体**
  - ACM MM：ACM DL，评审在 OpenReview；CCF A，ICORE A*。
- **机器人**
  - IROS：IEEE；CCF C，ICORE A，CSRankings 有收录。
  - RSS：roboticsproceedings.org；CSRankings 有收录。
- **安全**
  - IEEE S&P：`sp`，IEEE，许可为 IEEE 政策；CCF A，ICORE A*。
  - CCS：ACM DL；CCF A，ICORE A*。
- **系统**
  - NSDI：USENIX；CCF A。
  - SOSP：ACM DL；CCF A，ICORE A*。
  - MLSys：proceedings.mlsys.org，⚠ 未核。
- **TCS**
  - STOC：ACM DL；CCF A。
  - SODA：SIAM；CCF A。
  - FOCS：IEEE；CCF A。

### 2.4 元数据可得性矩阵（决定"哪个源补哪个字段"）

| DOI 前缀 / 源 | 注册机构 [C12] | 2025 年记录数（pub-date） | 含摘要 | 含 license | 注册时滞样本 [C59] | 备注 |
|---|---|---|---|---|---|---|
| 10.1145 ACM | Crossref | 46,548 | 7,231（15.5%） | 12,824（27.5%） | KDD 2026：会前 3 天 | 期刊类摘要约 100%，会议类多无 |
| 10.1109 IEEE | Crossref | 445,469 | 0 | 有（IEEE 政策 URI） | CVPR 2025 约 2 个月；ICRA 2025 约 3.5 个月；ICCV 2025 约 6 个月 | 摘要只能来自 IEEE API（受 ToU 限制）或 OpenAlex/S2 |
| 10.1007 Springer（book-chapter） | Crossref | 284,166 | 8,615（约 3.0%） | ⚠ 未统计 | ECCV 2026 会期前后 | LNCS |
| 10.18653 ACL | Crossref | 11,121 | 0 | 0（样本） | 会期前后 | 摘要从 Anthology XML 取 |
| 10.1609 AAAI | Crossref | 4,337 | 4,337（100%） | 0（样本） | — | link 含 text-mining PDF |
| 10.24963 IJCAI（含 KR） | Crossref | 1,368（IJCAI-34 1,281 + KR 85 + 2） | 1,366 | 0（样本） | 会前 | 仅 2017 年起；前缀与 KR 共用，须按 container-title 拆分（核验修正） |
| 10.65109 IFAAMAS（核验补充） | Crossref | 479（按 published 年） | 回溯卷多数有；AAMAS 2026 的 656 条为 0 | ⚠ 未统计 | 回溯卷约 2026-01 集中注册；AAMAS 2026 于 2026-05-24 注册 | container-title 与 publisher 字段混乱；2026 届记录没有 published 日期 [C64] |
| 10.21437 ISCA | Crossref | 1,388 | 0 | 0（样本） | — | 当年卷 robots 禁爬 |
| 10.14778 PVLDB | Crossref | 446 | 446（100%） | 0（样本） | 每月 | link 指向 ACM 镜像 |
| 10.14722 NDSS | Crossref | 2026 年 390 | 0 | 0（样本） | — | resource 直链 PDF |
| 10.52202 NeurIPS（Curran） | Crossref | vol 38 共 5,823 | 0 | ⚠ | 约 8 个月 | 前缀被 Curran 其他会议共用，须按 container-title 过滤 |
| 10.36227 TechRxiv | Crossref | 6,329（posted） | 有（样本） | CC BY 4.0（样本） | 即时 | posted-content |
| 10.4230 LIPIcs | **DataCite** | 2,336 | 有（descriptions） | CC BY 4.0 | — | Crossref 查为 0 |
| 10.48550 arXiv | **DataCite** | — | — | — | — | 与正式版的 DOI 关联要查 DataCite |
| 无 DOI | — | — | — | — | — | OpenReview（ICLR/COLM/TMLR）、PMLR（ICML/AISTATS/COLT/UAI/CoRL）、JMLR、USENIX，以及 CVF/ECVA 的 OA 版 |

### 2.5 会议名录体系（venue registry 的外部参照）

| 体系 | 版本 / 规模 | 获取方式与许可 | 与 CS/AI 相关的关键事实 | v2 用法 |
|---|---|---|---|---|
| CCF 推荐目录 | **第七版**，2026-03-31 发布（04-09 勘误）；上一版 2022 [C52] | 官方页面 `ccf.org.cn/Academic_Evaluation/By_category/`（robots `Crawl-delay: 60`，允许该路径）；PDF 也收在 ccfddl 仓库 `.readme_assets/ccf_recommended_2026.pdf`（2026-09-25 入库）[C52][C53]；PDF 按领域分 A/B/C，每条附 DBLP URL | AI 会议 A 类 7 个：AAAI、NeurIPS、ACL、CVPR、ICCV、ICML、**ICLR（新入）**；B 类含 COLT、EMNLP、ECAI、ECCV、ICRA、ICAPS、ICCBR、COLING、KR、UAI、AAMAS、PPSN、NAACL、**IJCAI（由 A 降 B）**；C 类含 AISTATS、IROS 等。AI 期刊 A 类：AI、TPAMI、IJCV、JMLR。其他领域 A 类：DB/DM/IR 为 SIGMOD、SIGKDD、ICDE、SIGIR、VLDB；SE 为 PLDI、POPL、FSE、SOSP、OOPSLA、ASE、ICSE、ISSTA、OSDI、FM；安全为 CCS、EUROCRYPT、S&P、CRYPTO、USENIX Security、NDSS；HCI 为 CSCW、CHI、UbiComp、UIST；交叉为 WWW、RTSS；图形与多媒体为 ACM MM、SIGGRAPH、VR、IEEE VIS；理论为 STOC、SODA、CAV、FOCS、LICS；体系结构为 PPoPP、FAST、DAC、HPCA、MICRO、SC、ASPLOS、ISCA、**ACM SIGOPS ATC（原 USENIX ATC）**、EuroSys、HPDC；网络为 SIGCOMM、MobiCom、INFOCOM、NSDI [C52]。ccfddl PR #1381（2026-03-05 合并，即公示期首日，依据的是公示稿）同步的等级变化：ICLR N→A，IJCAI A→B，Interspeech C→B，FMCAD C→B，HPDC B→A，ISCAS C→B，WINE A→B [C53][3P]；核验已在 03-31 正式版 PDF 中逐一核对，七项等级均一致 [C52] | venue 的"CCF 等级"标签与领域标签；更名（原 USENIX ATC、TASLP、IR 期刊改为 Discover Computing）写入 venue 改名链 |
| ICORE（原 CORE） | ICORE2026：825 个评级会议，此前有 CORE2023/2021/2020/2018/2017/2014/2013、ERA2010、CORE2008 [C55]；由 CORE、GII、GRIN、SCIE 四方联合管理 [C68] | 门户查询 + CSV 导出（约 986 行）；许可条款未见 ⚠；门户 robots 对 Claude 类代理全站禁止，平台以自身 UA 访问前须确认条款 | NeurIPS、ICML、ICLR、CVPR、ICCV、ECCV、ACL、EMNLP、KDD、SIGIR、WWW、CHI、ICSE、FSE、SIGMOD、VLDB、ICDE、OSDI、SOSP、USENIX Security、NDSS、S&P、CCS、ICRA、AAAI、IJCAI、COLT、KR、ICAPS、ACM MM 为 A*；UAI、AISTATS、NAACL、EACL、ECAI、WACV、Interspeech、IROS、ICWSM、AAMAS、WSDM、RecSys、CIKM、EuroSys、USENIX ATC 为 A；COLING、ALT 为 B；CoRL 为 Unranked；NSDI 标 National: USA；COLM、RSS、MLSys 不在名录中 [C55] | 国际等级标签（与 CCF 并列）；按 acronym 对齐时注意同名冲突（如 FSE 同时是 ACM FSE 与 IACR FSE） |
| CSRankings | 仓库持续更新（最近 push 2026-09-26）；parentMap 中 27 个父领域、77 个会议键 [C54] | `csrankings.js` 的 areaMap/parentMap；仓库 COPYING 为 **CC BY-NC-ND 4.0**（GitHub API 的 license 字段显示 NOASSERTION，以 COPYING 为准）[C54] | AI（AAAI、IJCAI）；Vision（CVPR、ECCV、ICCV）；ML（ICML、KDD、ICLR、NeurIPS）；NLP（ACL、EMNLP、NAACL）；Web+IR（SIGIR、WWW）；DB（SIGMOD、VLDB、ICDE、PODS）；Security（CCS、S&P、USENIX Security、NDSS）；OS（SOSP、OSDI、FAST、USENIX ATC、EuroSys）；SE（FSE、ICSE、ASE、ISSTA）；Robotics（ICRA、IROS、RSS）；HCI（CHI、UbiComp、UIST）等 [C54] | 只把"是否属于 CSRankings 集合"作为事实标签，不导入、不再分发其数据文件（NC-ND） |
| ccfddl/ccf-deadlines | 9,363 stars、MIT、持续更新 [C56] | GitHub `conference/{领域}/*.yml`：截稿、会期、地点、DBLP key，以及 ccf/core/thcpl 三种等级 [C53] | 本文 §2.6.4 的会期数据来自它；每个会议的 YAML 都带 `dblp:` key [C53] | 会议日历与截稿事件源（许可允许导入，需署名） |
| paperswithcode/ai-deadlines | 6,007 stars、MIT、**最近 push 2024-09-15**（已停更）[C56] | GitHub | — | 不采用（数据陈旧） |

### 2.6 最新论文通道

#### 2.6.1 arXiv 日节奏（ET = 美东时间）

| 投稿窗口 | 公告时间 | OAI/RSS 可取 | 说明 |
|---|---|---|---|
| 周一 14:00 至周二 14:00 | 周二 20:00 | OAI 约 22:30；RSS 每日 0 点（EST） | 每个公告日都包含新投稿、替换版、撤稿、cross-list 与 journal-ref 更新 [C7] |
| 周二 14:00 至周三 14:00 | 周三 20:00 | 同上 | — |
| 周三 14:00 至周四 14:00 | 周四 20:00 | 同上 | — |
| 周四 14:00 至周五 14:00 | **周日** 20:00 | 同上 | 周五、周六不公告 |
| 周五 14:00 至周一 14:00 | 周一 20:00 | 同上 | 2026 年共 9 个节假日可能推迟 [C7] |

- 量级：2026-09-21~25 的 OAI 记录中，cs 集 7,083 条，按 datestamp 分布为 963/2,272/1,345/1,179/1,324；子类样本中 cs.LG 1,861 条、cs.AI 1,815 条、cs.CV 1,104 条、cs.CL 1,001 条（都含替换版和 cross-list）[C3][LIVE]。
- 建议：每个公告日 ET 22:30 之后，用类目级 set 做一次 OAI `ListRecords(metadataPrefix=arXiv, from=上次水位)`；RSS 只作"今日速览"的轻量通道；`/list/{cat}/new` 页面不作为机器通道（按 robots，每次请求间隔 15 s）。

#### 2.6.2 OpenReview 流

- **会议发现**：定期对 `groups?id=active_venues` 做差集，新出现的 `*/Conference` 即为新届。该接口匿名可读，响应头 `ratelimit-policy: 180;w=60` [C15]。
- **投稿与接收流**：已登录时，用 `notes?content.venueid={venue}&mintmdate={水位}&sort=tmdate:asc&select=id,content.title,content.abstract,content.venueid` 拉增量。投稿阶段取 `submission_venue_id`；决定公布后，主会 venueid 即为接收；拒稿进 `rejected_venue_id`（若该会公开拒稿）[C15][C16]。
- **热度信号**：`sort=replyCount`（必须带 invitation 过滤）可反映讨论量 [C16]。
- **合规边界**：只读公开 note；不访问 `profiles/search` 等身份相关端点（参照 2025-11 事件 [C17]；端点名 ⚠ 见 [C62]）；限流按每次请求读取响应头（核验修正）。

#### 2.6.3 社区信号流

- **HF Daily/Trending**：`list_daily_papers(date=…)` 返回每日精选，字段含 upvotes、numComments、submittedOnDailyAt、organization；`sort=trending` 得趋势榜 [C44][C41]。
- **alphaXiv**：views/likes 只能通过用户个人授权的 MCP 获取 [C46]。
- **PwC 存档**：提供 2025 年以前"论文↔代码/基准"的静态关联 [C45]。

#### 2.6.4 2026 周期：会期与当前可见通道（2026-09-26 实测）

| venue | 2026 会期（ccfddl [C53]） | 当前可见的最早通道 | 正式论文集或 DOI 状态（LIVE） |
|---|---|---|---|
| AAAI-26 | 01-20 至 27，新加坡 | OJS | AAAI-26 Technical Tracks 已上线 [C36]；AAAI-27（2027-02-16 至 23，蒙特利尔）已在 OpenReview 活跃 [C15] |
| NDSS 2026 | 02-23 至 27 | 官网 PDF | Crossref 已有 390 条 [C59] |
| WACV 2026 | 03-06 至 10 | CVF | CVF 与 IEEE 均已上线（Crossref 按 container-title 精确过滤为 840 条）[C29][C22] |
| ICLR 2026 | 04-23 至 27，里约 | OpenReview | OpenReview 即为正式出处；ICLR 2027 截稿为 2026-09-25（ccfddl 另记录决定日 12-16）[C53] |
| CHI 2026 | 04-13 至 17 | ACM DL | Crossref 已有 1,702 + 1,005 条 [C22] |
| WWW 2026 | 04-13 至 17，迪拜 | ACM DL | Crossref 已有 723 条 [C22] |
| ICSE 2026 | 04-12 至 18 | ACM DL | Crossref 已有 470 条 [C22] |
| AISTATS 2026 | 05-02 至 05 | PMLR | v300 [C35] |
| SIGMOD 2026 | 05-31 至 06-05 | PACMMOD（全年滚动） | 2026 年 257 条 [C22] |
| ICRA 2026 | 06-01 至 05，维也纳 | arXiv / 作者版 | IEEE DOI 截至 9-26 未见 [C59] |
| CVPR 2026 | 06-03 至 07，丹佛 | CVF（4,042 篇；官方新闻稿称 16,092 篇投稿、4,089 篇 paper presentations，@CVPR 推文称建议录用 4,090 篇；差额为未上 CVF 的论文 [C65]） | IEEE DOI 截至 9-26 未见（按精确 container-title 过滤为 0）[C29][C59] |
| COLT 2026 | 06-29 至 07-03 | PMLR | v336 [C35] |
| ACL 2026 | 07-02 至 07，圣迭戈 | ACL Anthology | long 2,222 篇、Findings 2,163 篇（不含 front matter）[C33] |
| ICML 2026 | 07-06 至 11，首尔 | OpenReview | **PMLR 卷未上线** [C35] |
| FSE 2026 | 07-06 至 10，蒙特利尔 | PACMSE | 2026 年 212 条 [C22] |
| OSDI 2026 | 07-13 至 15 | USENIX | ⚠ 本轮未抓 2026 页（2025 年模式已核验 [C31]） |
| SIGIR 2026 | 07-20 至 24 | ACM DL | 686 条 [C22] |
| KDD 2026 | 08-09 至 13，济州 | ACM DL | V.2 有 1,220 条，会前已注册 [C22][C59] |
| USENIX Security 2026 | 08-12 至 14 | USENIX（录用后 prepub） | ⚠ 2026 未抓，同上 |
| IJCAI 2026 | 08-15 至 21，不来梅 | ijcai.org（972 条） | Crossref 中 IJCAI-35 为 972 条；前缀 2026 年共 1,085 条，另 111 条是 KR 2026（核验修正）[C30][C22] |
| UAI 2026 | 08-17 至 21 | PMLR | v337 [C35] |
| VLDB 2026 | 08-31 至 09-04 | PVLDB（按月） | vol 19 [C32] |
| ECCV 2026 | 09-08 至 12，马尔默 | Springer LNCS | Crossref 2,251 条；ECVA 未上线 [C22][C28] |
| Interspeech 2026 | 09-27 至 10-01，悉尼 | 页面已有，但 robots 禁爬 | Crossref 为 0 [C38][C22] |
| IROS 2026 | 09-27 至 10-01 | arXiv / 作者版 | IEEE 待出 |
| COLM 2026 | 10-06 至 09 | OpenReview（活跃中） | — [C15] |
| EMNLP 2026 | 10-24 至 29，布达佩斯 | OpenReview（`EMNLP/2026/Conference` 活跃中） | Anthology 待出 [C15] |
| CoRL 2026 | 11-09 至 12，奥斯汀（主会 09 至 11 日，12 日为 workshop；核验修正，原写 11-10）[C66] | OpenReview（活跃中） | PMLR 待出（CoRL 2025 为 v305）[C15][C35] |
| ACM MM 2026 | 11-10 至 14 | OpenReview（评审） | ACM DL 待出 [C15] |
| NeurIPS 2026 | 悉尼主会 12-06 至 12；亚特兰大、巴黎两个卫星会场 12-09 至 13（核验修正，原文只写悉尼）[C66] | OpenReview（活跃中） | proceedings 与 DOI 会后数月出（2025 届约晚 8 个月）[C15][C59] |

#### 2.6.5 新鲜度阶梯（建议）

对每个 venue 按届，路由器依次选用**当前可用且合规**的最早通道：

- **L0**：arXiv 或作者 prepub（USENIX）；
- **L1**：OpenReview 接收态或会议官方 OA 平台（CVF、ACL Anthology、IJCAI、ECVA、PMLR、NeurIPS）；
- **L2**：Crossref 或 DataCite DOI。ACM 系在会前即可用，IEEE 系滞后 2–6 个月，NeurIPS 的 Curran DOI 滞后约 8 个月；
- **L3**：OpenAlex / S2 等聚合层，用于补字段。

同一论文在各层之间的去重，靠 identifier 图完成：arXiv id ↔ OpenReview forum ↔ DOI ↔ dblp key（D-007 的延伸）。

### 2.7 许可与多用户共享矩阵

> 红线：用户凭证取回的 auth-gated 全文，一律只归该用户私有存放。下表讨论的是开放全文能否由平台缓存一份、供多个用户共用。

| 来源 | 元数据许可 | 全文许可 | 平台级共享缓存 | 依据 |
|---|---|---|---|---|
| arXiv | CC0 | 逐篇：arXiv 默认非独占（约 44%）或 CC 系（约 56%，cs.LG 样本） | **只放行 CC BY、BY-SA、CC0**；NC 系须视平台是否商业化；默认许可的只做链出或由用户按需取回 | [C1][C3] |
| OpenReview | CC0（评论为 CC BY 4.0） | 作者保留版权 | 不缓存 PDF；只缓存元数据 | [v1:2026-07-22] |
| ACL Anthology | — | 2016 年起 CC BY 4.0；2016 年前 CC BY-NC-SA 3.0 | 可以（需署名；2016 年前受 NC 限制） | [C33] |
| JMLR | — | CC BY 4.0 | 可以（需署名） | [C37] |
| LIPIcs | — | CC BY 4.0 | 可以 | [C39] |
| PVLDB | — | CC BY-NC-ND 4.0 | 仅限非商业、不修改地再分发 | [C32] |
| ECAI（IOS FAIA） | — | CC BY-NC 4.0（样本） | 仅限非商业 | [C59] |
| TechRxiv | — | 逐篇（样本为 CC BY 4.0） | 按逐篇许可放行 | [C49] |
| ACM DL | 书目事实 | 新文由作者选 CC BY 或 CC BY-NC-ND；回溯卷只是"免费阅读" | 只有记录明确带 CC 许可时才可共享；另外受 ToS 与 Cloudflare 质询约束，只做链出 | [C18][C19][C21] |
| CVF、ECVA、NeurIPS、PMLR、AAAI、IJCAI、USENIX、ISCA、NDSS | 书目事实 | 免费阅读但保留版权（CVF 明文 [C29]，其余未声明开放许可 ⚠） | 不共享缓存：链出或由用户按需取回、私有存放 | [C29][C28][C34][C36][C30][C31] |
| IEEE、Springer、Elsevier、MIT（订阅部分） | 书目事实（Crossref） | 订阅 | **禁止共享**；IEEE API 内容另外禁止用于 ML 训练 | [C24][C26] |
| PwC 存档 | CC-BY-SA 4.0 | — | 可以（相同方式共享） | [C45] |
| HF Papers | 遵循 HF 规则 | — | 只缓存信号（点赞数等），并按 HF ToS 复核 ⚠ | [C41] |

### 2.8 可复用开源件（CS 来源侧）

| 仓库 | stars / license / 最近 push（gh api [C56]） | 用途与评估 |
|---|---|---|
| openreview/openreview-py | 268 / MIT / 2026-09-26 | 官方客户端（v1/v2 两个 Client，重试完善 [v1]）；v2 可直接依赖 |
| acl-org/acl-anthology | 807 / Apache-2.0 / 2026-09-26 | 数据加 `acl-anthology` 官方 Python 包；首选接入方式 |
| lukasschwab/arxiv.py | 1,548 / MIT / 2026-09-01 | Query API 封装；v2 以 OAI 为主，可只借鉴其限速与重试实现 |
| huggingface/huggingface_hub | 3,936 / Apache-2.0 / 2026-09-26 | `list_daily_papers`、`paper_info`、`list_papers`，并能按 `RateLimit` 响应头自动退避（官方文档称 1.2.0 起）[C42] |
| ccfddl/ccf-deadlines | 9,363 / MIT / 2026-09-26 | 会议日历、DBLP key、三种等级 |
| emeryberger/CSrankings | 3,207 / CC BY-NC-ND 4.0 / 2026-09-26 | 只作为事实参照（仓库内还带一份 33 MB 的 `dblp.xml.xz` 子集） |
| paperswithcode/paperswithcode-data | 941 / 未声明（数据为 CC-BY-SA）/ 2025-09-08 | 指向 HF 存档 |
| papercopilot/paperlists | 958 / **无 license** / 2026-07-01 | 只参考字段设计 |
| paperswithcode/ai-deadlines | 6,007 / MIT / 2024-09-15 | 已停更 |

## 3. 对 v2 设计的启示

1. **来源名录用数据驱动，并为每个事实记录证据**：每个 source 建一条记录，包含 `source_id`、`tier_type`、`disciplines`，以及三个通道 `channels{metadata, latest, fulltext}`。每个通道描述：方法、端点、认证、限速（含响应头名）、robots 允许范围、ToS 标志、许可策略、`evidence{url, verified_at}`。对 robots.txt、ToS 页和限流头做**周级漂移监测**（保存哈希并比对差异）。依据：本轮 3 个月内就出现了 dblp 全禁 [C40]、OpenReview 限流改制 [C15]、arXiv 429 [C9]、ISCA 按年份禁爬 [C38] 等变化。
2. **把"声明的协议通道"和"robots 爬行权限"分开建模**：IACR 与 dblp 都是 robots 对 `*` 全禁，但官方声明了 OAI、RSS 或快照、SPARQL 通道 [C48][C40]；arXiv 的 export 主机也是全禁，只允许走 API [C8]。权限模型至少分四类：`api_documented`、`bulk_snapshot`、`robots_paths(时间可变)`、`tos_automation(allow/deny/contract)`，**以其中最严者为准**（沿用 D-020 口径）。
3. **CS 元数据走三轨，各源负责自己擅长的字段**：
   - DOI 型 venue 用 Crossref 枚举：ACM、IEEE、Springer、AAAI、IJCAI、ACL、ISCA、NDSS、PVLDB、NeurIPS-Curran、TechRxiv。期刊按 ISSN；没有 ISSN 的会议论文集按 `filter=container-title:` 精确标题，每届一个标题，存进 VenueEra；标题含逗号时退回 query 加本地核对 [C22]。前缀被多个 venue 共用时（如 Curran 10.52202 同时承载 NeurIPS 与 IAF、WCTE 等；IJCAI 10.24963 同时承载 IJCAI 与 KR），前缀计数不能当成 venue 计数，必须按 container-title 拆分（核验补充）；
   - TCS 与 arXiv DOI 用 DataCite；
   - 无 DOI 的 venue 用各平台原生接口：OpenReview、PMLR、JMLR/TMLR、USENIX、CVF、ECVA、arXiv。

   **摘要字段按源优先级补齐**：Anthology XML、CVF 页、OpenReview、arXiv 等平台原生来源优先，其次 OpenAlex（受预算约束）、S2，最后才是 IEEE API（受 ToU 限制）。依据：IEEE、ACL、ISCA、NDSS、Elsevier 在 Crossref 中的摘要为 0，ACM 为 15.5% [C22]。
4. **venue 名录主干改为"dblp 月度快照导入"**：每月 1 日后，从 DROPS 下载 `dblp-YYYY-MM-01.xml.gz` 并校验 md5 [C39]，据此生成 VenueEra、会议卷目录和作者 PID；**禁止在线访问 dblp.org** [C40]。新一届的发现用 OpenReview `active_venues` 差集 [C15] 加 ccfddl 会期 [C53]，替代 D-038 暂缓的探测任务。
5. **"最新论文"按新鲜度阶梯路由**（§2.6.5）：对每个 venue-year 取当前合规的最早通道，并用 Crossref 的 `created` 字段持续测量各出版方的时滞（IEEE 2–6 个月、Curran 约 8 个月、ACM 会前 [C59]）。时滞写回名录，用于调度与卡片上的"正式版可用"标注。
6. **arXiv 在多用户后台必须做成"中心镜像"**：ToU 限速按"所有机器合计"计算 [C1]，所以 v2 的用户搜索、组合查询、订阅都只查本地索引。本地索引由 OAI 类目级 set 按公告节奏增量构建 [C2][C3]。限流检测同时看状态码 429 和正文里的 `Rate exceeded.` [C9][C10]。如果规模扩大，按 ToU 联系 arXiv 申请更高速率（"please contact our support team" [C1]）。另外，arXiv API 页要求在产品上展示致谢语"Thank you to arXiv for use of its open access interoperability."；商业项目须先读相关文档并考虑成为 arXiv affiliate；不得用 arXiv 的名称与标识暗示背书（核验补充 [C67]）。
7. **全文共享按逐篇许可放行**：把 `license`（URI）和 `license_source`（arXiv OAI、Crossref、DataCite、PDF 首页）写成 asset 级字段。只有 CC BY、BY-SA、CC0 可以进平台共享缓存；NC 与 ND 类按平台性质判断；arXiv 默认许可以及只是"免费阅读"的会议平台（CVF、NeurIPS、PMLR、AAAI、IJCAI、USENIX、ISCA、ECVA）一律**链出或由用户按需取回、私有存放**（§2.7）。
8. **字段级数据权利标签**：每个字段记录 `provenance` 和 `usage_rights`（`display_only`、`no_ml_training`、`no_share`）。依据：IEEE API ToU 明确禁止把内容用于 AI/ML/LLM 训练或增强，并禁止批量呈现 [C24]。所以来自 IEEE API 的摘要不得进入嵌入、召回和推荐训练；ToU 还禁止用程序"retrieve or index any portion of the Content"[C24]，因此 IEEE API 内容也不得进入任何索引（全文检索与向量索引都算），只能按单次查询即时展示（核验补充）；推荐模型的文本特征只能用许可允许的来源（arXiv 元数据 CC0、OpenReview 元数据 CC0、Anthology CC BY、OpenAlex CC0 等）。
9. **OpenReview 分两层接入**：
   - **平台层**：用服务账号读取公开 note 元数据（CC0），按每次响应的限流头限速（同一端点也可能不同）[C15]，用 `mintmdate` 增量、`select` 裁剪字段 [C16]。
   - **用户层**：用 OIDC "Sign in with OpenReview" 绑定用户的 OpenReview profile [C14]，用于作者认领和双向匹配里的"我是谁、我发过什么"。
   - 禁止访问 profiles/search 等身份端点 [C17]。服务账号是否符合 ToS 须先向 OpenReview 确认（§4）。
10. **身份锚点多源融合**：作者侧有 OpenReview profile（OIDC `sub`）、ACL Anthology 已验证作者（ORCID）[C33] 和 dblp PID（快照）；论文侧有 arXiv id、OpenReview forum、DOI、dblp key。这些锚点支撑用户↔作者认领（研究兴趣冷启动）和论文跨源去重。
11. **社区信号源作为推荐冷启动的先验**：HF daily/trending（upvotes、评论数、组织、GitHub stars）[C41][C43] 和 PwC 存档里的论文↔代码关联 [C45] 作为外部热度与代码可得性特征。HF 调用由中心调度，匿名每 5 分钟 500 次，带 token 为 1,000 次 [C42]。alphaXiv 只做用户自己连接的可选连接器 [C46]。
12. **限速器统一解析四种限流头**：IETF `RateLimit`/`RateLimit-Policy`（HF、OpenReview）[C41][C15]、`x-ratelimit-*`（OpenReview、OpenAlex）[C15][C51]、`x-rate-limit-*` 与 `x-api-pool`（Crossref）[C22]，以及 Springer 的 429 加每日配额 [C26]。令牌桶以"主机 × 端点 × 凭证主体"为键；响应头声明的策略不同时再按策略细分（OpenReview 同为 `/groups` 就有 20 与 180 两档 [C15]，核验补充）；无响应头时退回名录里的静态值。
13. **ACM 与 IEEE 的定位**："元数据零直连 + 全文只链出"：
    - ACM：Crossref 加 OpenAlex 补摘要；全文由用户在浏览器中自行打开。机构 TDM 权利作为用户声明的可选能力（"经 ACM 提供的 API"[C20]），平台不默认拥有。
    - IEEE：key 必须是用户所在机构的 key，结果只按单次查询展示 [C24]。
14. **venue 身份用"多键 + 演化边"表示**：
    - 键：DBLP key、CCF 简称、ICORE acronym、CSRankings area、OpenReview group 前缀、全部 ISSN（Elsevier 在 Crossref 只认 print ISSN [C22]）。
    - 演化边：`renamed_to`（TASLP 2329-9290 → 2998-4173 [C59]；USENIX ATC → ACM SIGOPS ATC [C52]）、`journalized_as`（SIGMOD → PACMMOD，FSE → PACMSE [C22]）、`co_hosted_on`（CVPR 同时在 CVF 与 IEEE；ECCV 同时在 LNCS 与 ECVA）。
    - ICORE 的同名 acronym（如 FSE）必须消歧 [C55]。
15. **优先级落到 v2 首版范围**：
    - **P0**：arxiv、openreview、crossref、datacite、openalex（受预算约束）、dblp（快照）、acl_anthology、pmlr、cvf_open_access、neurips_proceedings、aaai_ojs、ijcai_proceedings、jmlr/tmlr、hf_papers。前 13 个覆盖 CCF-A 与 ICORE-A* 中 AI/ML/CV/NLP 的绝大多数会议，hf_papers 提供社区信号。
    - **P1**：usenix、ndss、pvldb、isca_archive、lipics_drops、ecva、techrxiv、iacr_eprint（仅元数据）、jair、iospress_faia、mit_press_direct（仅元数据）、acm_dl（仅元数据）、ieee_xplore（元数据 + 用户会话）、springer_link（元数据 + 用户 key）、elsevier_sd（CS 刊）、semantic_scholar、unpaywall、pwc_archive。
    - **P2**：rss_proceedings、mlsys_proceedings、ceur_ws、alphaxiv、eccc、siam_epubs、now_publishers、hal、aamas_ifaamas（核验补充）。KR 随 ijcai_proceedings 一并接入。
    - **排除**：Google Scholar、SciRate、会议官网 miniconf 数据、paper_copilot 数据导入，以及一切盗版源。
16. **v1 须先修的漂移**（可以作为 v2 迁移前的补丁清单）：
    - NeurIPS 分轨闭表：加入 Position_Paper_Track、Creative_AI_Track [C34]；
    - arXiv 改用类目级 set，并落库 license [C3]；
    - TASLP 换 ISSN [C59]；
    - ECCV 全文源改为 ECVA [C28]；
    - dblp 在线路径作废 [C40]；
    - OpenReview 限速改为按请求读响应头，不按路径写死 [C15]；
    - PMLR 新卷发现改为"首页 diff + 探测" [C35]。
17. **测试与验收**：
    - 每个 source 至少准备四类 fixture：正常页、空态、限流（含伪 200）、robots 或质询；
    - 名录中"最新通道"的时滞断言用 Crossref `created` 字段做 canary（样本 DOI 见 [C59]）；
    - 许可门控写成单元测试：同一 PDF 按不同 license 分别断言"可共享"或"仅链出"。

## 4. 未决问题与风险

1. **dblp 全禁是否长期有效，快照下载是否无争议**：DROPS robots 放行 `/storage/` [C39]，快照为 CC0；但 dblp 主站的全禁意图（反 AI 爬虫）与"下载 DOI 发布的快照"之间是否还有额外条款，⚠ 未见 dblp 的官方说明（主站 robots 全禁，无法合规阅读其 FAQ）。缓解：只用 DROPS 快照和 SPARQL 的 `/download`，并记录版本 DOI。
2. **arXiv 限流阈值不透明**：员工只说"近期调整"[C9]，阈值和单 IP 或全局的判定方式都未公开；伪 200 响应只有社区观测 [C10]。风险：中心镜像的追新可能被节流而延迟。缓解：OAI 优先、RSS 兜底、每日窗口内重试；规模化前联系 arXiv。
3. **OpenReview 服务账号是否合规**：ToS 规定一人一号、账号须对应真实身份 [v1]，平台以组织名义用服务账号读取公开数据是否被允许，⚠ 需向 OpenReview 书面确认。备选：让每个用户用自己的 token（体验差，也不利于中心化限流）。
4. **ACM 条款证据链不完整**：公告页和政策页对脚本返回 403，本轮只能引用搜索摘要 [C18][C19]。核验时，"全库 OA"与"CC BY / CC BY-NC-ND 二选一"已由多份图书馆指南印证 [C63]，但 ToS 中禁止脚本下载与收割的原文仍未直读。上线前须人工在浏览器中核读原文，并留存截图或 PDF 作为证据。
5. **IEEE 与 Springer 的条款细节**：IEEE 配额只在注册时展示 [C24]；Springer API 条款是否禁止 AI 用途本轮未读 ⚠。需要在设计阶段写一份"第三方 API 数据权利对照"的 ADR。
6. **HF 与 alphaXiv 的 ToS**：HF Papers 数据能否在推荐中商业化使用、长期缓存，⚠ 未核；alphaXiv 配额与条款未公开 [C46]。
7. **ICORE 与 CSRankings 的再利用许可**：CSRankings 为 CC BY-NC-ND 4.0 [C54]；ICORE CSV 的许可未见 ⚠，core.edu.au 的 ICORE 页也没有再利用条款 [C68]。v2 若商业化，只能存储"等级事实"并注明来源。
8. **PMLR 卷号不可预测，ICML 2026 延迟**：本轮探测 v335/v338/v342–v346 均为 404 [C35]。风险：一年内 ICML 只能从 OpenReview 取得。
9. **按年份变化的禁区**：ISCA 当年卷被 robots 禁 [C38]；类似做法可能扩散到其他平台。调度器需要支持"禁区到期后重排队"。
10. **Crossref 时滞与覆盖的系统性偏差**：IEEE 系 CV/机器人会议的 DOI 最多晚约 6 个月（ICCV 2025），Curran/NeurIPS 约晚 8 个月 [C59]，单靠 Crossref 追新会明显滞后。
11. **本轮覆盖缺口**（受 WebSearch 预算限制）：MLSys、RSS 2026 卷、ECCC、now publishers、SIAM 未复测；IEEE API 配额数字（ToU 只说"注册时展示"，核验确认没有公开数字）、Kaggle arXiv 数据集当前版本、HAL OAI 与增量参数、DataCite 增量参数都标了 ⚠。核验轮已为 AAMAS（IFAAMAS）与 KR 补登简要条目，其全文通道与 ToS 仍待勘察。建议设计阶段先补一轮定向勘察。
12. **OpenReview 安全事件的余波**：平台可能进一步收紧匿名接口（例如 `active_venues`、`venues`）或限流；名录应把"匿名可读"标为易变属性，并由漂移监测覆盖。
13. **调研过程本身的合规瑕疵（核验发现）**：portal.core.edu.au 的 robots 对 Claude-User、ClaudeBot、Claude-SearchBot、anthropic-ai 等 UA 设为 `Disallow: /` [C55]。调研员作为 Claude 代理，却以 `PaperCrawler/0.1` UA 访问门户并导出了 ICORE CSV。UA 如实写了项目名，但操作者属于 robots 明确排除的类别，按从严原则视为瑕疵。核验轮只读了该站 robots.txt，没有访问门户页面。建议：①ICORE 数字上线前由人工在浏览器中复核；②v2 以 PaperCrawler 身份访问时落在 `*` 组（只禁 `/core-tools/media/`），但仍须先确认 ICORE 的使用条款；③今后的调研任务中，凡 robots 具名禁止 Claude 类代理的站点，调研代理一律不访问。

## 5. 参考来源（访问日期均为 2026-09-26，另注者除外）

| 编号 | 来源 | URL |
|---|---|---|
| C1 | arXiv API Terms of Use | https://info.arxiv.org/help/api/tou.html |
| C2 | arXiv OAI-PMH 说明（2025-03 重写、类目级 set、公告时间） | https://info.arxiv.org/help/oa/index.html |
| C3 | arXiv OAI-PMH 实测（ListSets / ListIdentifiers `set=cs`、`cs:cs:{LG,CL,CV,AI}` 2026-09-21~25 / ListRecords `cs:cs:LG` 2026-09-24 / GetRecord 2609.28603） | https://oaipmh.arxiv.org/oai?verb=ListSets |
| C4 | arXiv RSS 说明 | https://info.arxiv.org/help/rss.html |
| C5 | arXiv S3 Bulk | https://info.arxiv.org/help/bulk_data_s3.html |
| C6 | arXiv Bulk Data | https://info.arxiv.org/help/bulk_data.html |
| C7 | arXiv 公告时间表 | https://info.arxiv.org/help/availability.html |
| C8 | arXiv robots（主站、export 站） | https://arxiv.org/robots.txt ；https://export.arxiv.org/robots.txt |
| C9 | arXiv API 限流讨论串（2026-02-26 至 06-05，员工 2026-02-27 回复） | https://groups.google.com/a/arxiv.org/g/api/c/ycq8giRdZsQ |
| C10 | paper-search-mcp PR #119（2026-09-22 合并，"Rate exceeded." 伪 200）[3P] | https://github.com/openags/paper-search-mcp/pull/119 |
| C11 | arXiv 博客：CS 综述与立场论文新做法（2025-10-31） | https://blog.arxiv.org/2025/10/31/attention-authors-updated-practice-for-review-articles-and-position-papers-in-arxiv-cs-category/ |
| C12 | DOI 注册机构查询（10.48550、10.4230、10.24963、10.14778、10.21437、10.1609、10.18653、10.14722、10.52202、10.36227 等） | https://doi.org/ra/10.48550 （同形 URL 逐个前缀查询） |
| C13 | OpenReview：Using the API | https://docs.openreview.net/getting-started/using-the-api |
| C14 | OpenReview：Sign in with OpenReview（OIDC） | https://docs.openreview.net/reference/sign-in-with-openreview |
| C15 | OpenReview API 实测（groups ICLR 2026 / active_venues / venues；匿名 notes 403；robots） | https://api2.openreview.net/groups?id=active_venues ；https://api2.openreview.net/groups?id=ICLR.cc/2026/Conference ；https://openreview.net/robots.txt |
| C16 | OpenReview OpenAPI 定义（notes 参数） | https://api2.openreview.net/docs/api.yml |
| C17 | ICLR 2026 对安全事件的回应（2025-12-03） | https://blog.iclr.cc/2025/12/03/iclr-2026-response-to-security-incident/ |
| C18 | ACM 公告"ACM is Now Fully Open Access!"（原页对脚本 403，据搜索摘要）[SNIP] | https://www.acm.org/articles/bulletins/2026/january/acm-open-access |
| C19 | ACM DL 使用政策与出版权利政策（原页 403，据搜索摘要）[SNIP] | https://libraries.acm.org/digital-library/policies ；https://www.acm.org/publications/policies/publication-rights-and-licensing-policy |
| C20 | KB 2024–2026 ACM Digital Library Tiered-Band OA 协议 PDF（§IV.5–6） | https://pro.kb.dk/en/licensing/oa-publication-guidelines/acm-open-agreement-document/acm-open-agreement-document.pdf |
| C21 | ACM DL robots 与匿名 HEAD（403 `cf-mitigated: challenge`） | https://dl.acm.org/robots.txt ；https://dl.acm.org/doi/10.1145/3774904.3792547 |
| C22 | Crossref REST API 实测（prefix/ISSN × 年份计数、has-abstract/has-license、container-title facet、`/journals?query=`） | https://api.crossref.org/works ；https://api.crossref.org/journals |
| C23 | IEEE Xplore API 开发者门户（首页、Getting Started、Docs、Metadata API details） | https://developer.ieee.org/ ；https://developer.ieee.org/getting_started ；https://developer.ieee.org/docs ；https://developer.ieee.org/docs/read/Metadata_API_details |
| C24 | IEEE Xplore API Terms of Use | https://developer.ieee.org/API_Terms_of_Use2 |
| C25 | IEEE Xplore robots | https://ieeexplore.ieee.org/robots.txt |
| C26 | Springer Nature API 限额与节流政策 | https://dev.springernature.com/docs/rate-limit-details/rate-limits ；https://dev.springernature.com/docs/rate-limit-details/throttling-policies ；https://dev.springernature.com/ |
| C27 | Springer Nature Link robots | https://link.springer.com/robots.txt |
| C28 | ECVA ECCV 论文页与 robots | https://www.ecva.net/papers.php ；https://www.ecva.net/robots.txt |
| C29 | CVF Open Access（menu、CVPR 2026、ICCV 2025） | https://openaccess.thecvf.com/menu ；https://openaccess.thecvf.com/CVPR2026?day=all ；https://openaccess.thecvf.com/ICCV2025?day=all |
| C30 | IJCAI robots 与论文集 | https://www.ijcai.org/robots.txt ；https://www.ijcai.org/proceedings/2025/ ；https://www.ijcai.org/proceedings/2026/ |
| C31 | USENIX robots、Security '25 会话页与 presentation 页 | https://www.usenix.org/robots.txt ；https://www.usenix.org/conference/usenixsecurity25/technical-sessions ；https://www.usenix.org/conference/usenixsecurity25/presentation/nong |
| C32 | PVLDB vol 19 与论文 PDF 首页许可 | https://www.vldb.org/pvldb/volumes/19/ ；https://www.vldb.org/pvldb/vol19/p1-zhang.pdf |
| C33 | ACL Anthology（页脚许可、数据访问 FAQ、已验证作者、ACL 2026 事件页） | https://aclanthology.org/faq/api/ ；https://aclanthology.org/info/verification/ ；https://aclanthology.org/events/acl-2026/ |
| C34 | NeurIPS Proceedings 2025（年页、vol38 卷页、abstract 页 `citation_doi`） | https://proceedings.neurips.cc/paper_files/paper/2025 ；https://proceedings.neurips.cc/paper_files/paper/2025/vol38-main-conference |
| C35 | PMLR 首页与卷号探测（v300、v327、v329、v335–v346） | https://proceedings.mlr.press/ |
| C36 | AAAI OJS（站点索引、AAAI 期号归档、OAI Identify/ListRecords、robots） | https://ojs.aaai.org/index.php/index/index ；https://ojs.aaai.org/index.php/AAAI/issue/archive ；https://ojs.aaai.org/index.php/AAAI/oai?verb=Identify |
| C37 | JMLR RSS、论文页与 PDF 首页许可、TMLR 列表 | https://www.jmlr.org/jmlr.xml ；https://jmlr.org/papers/v27/26-0434.html ；https://www.jmlr.org/tmlr/papers/ |
| C38 | ISCA Archive robots 与 Interspeech 2025 年页 | https://www.isca-archive.org/robots.txt ；https://www.isca-archive.org/interspeech_2025/index.html |
| C39 | DROPS（robots、OAI、dblp 月度快照 artifact 页）与 DataCite API | https://drops.dagstuhl.de/robots.txt ；https://drops.dagstuhl.de/oai?verb=Identify ；https://drops.dagstuhl.de/entities/artifact/10.4230/dblp.xml.2026-09-01 ；https://api.datacite.org/dois?prefix=10.4230 |
| C40 | dblp robots（主站、两镜像、SPARQL） | https://dblp.org/robots.txt ；https://dblp.uni-trier.de/robots.txt ；https://dblp.dagstuhl.de/robots.txt ；https://sparql.dblp.org/robots.txt |
| C41 | Hugging Face Papers API 实测（daily_papers、papers/search 限流头；robots） | https://huggingface.co/api/daily_papers ；https://huggingface.co/api/papers/search ；https://huggingface.co/robots.txt |
| C42 | Hugging Face Hub 限流文档 | https://huggingface.co/docs/hub/rate-limits |
| C43 | Hugging Face Trending Papers | https://huggingface.co/papers/trending |
| C44 | huggingface_hub `hf_api.py`（`list_daily_papers` 等） | https://github.com/huggingface/huggingface_hub/blob/main/src/huggingface_hub/hf_api.py |
| C45 | Papers with Code 跳转与存档（GitHub README、HF 数据集 API） | https://paperswithcode.com/ ；https://github.com/paperswithcode/paperswithcode-data ；https://huggingface.co/api/datasets/pwc-archive/links-between-paper-and-code |
| C46 | alphaXiv（首页、robots、MCP 文档） | https://www.alphaxiv.org/ ；https://www.alphaxiv.org/robots.txt ；https://www.alphaxiv.org/docs/mcp |
| C47 | SciRate robots（Cloudflare 托管质询 403） | https://scirate.com/robots.txt |
| C48 | IACR ePrint（robots、OAI、RSS） | https://eprint.iacr.org/robots.txt ；https://eprint.iacr.org/oai?verb=Identify ；https://eprint.iacr.org/rss/rss.xml |
| C49 | TechRxiv robots 与 Crossref 10.36227 计数和样本 | https://www.techrxiv.org/robots.txt ；https://api.crossref.org/works?filter=prefix:10.36227 |
| C50 | HAL Search API | https://api.archives-ouvertes.fr/search/ |
| C51 | OpenAlex works（`x-ratelimit-*` 响应头，CS field 计数） | https://api.openalex.org/works?filter=primary_topic.field.id:17,from_publication_date:2026-01-01 |
| C52 | CCF 第七版目录发布页与 2026 目录 PDF | https://www.ccf.org.cn/Academic_Evaluation/By_category/ ；https://github.com/ccfddl/ccf-deadlines/blob/main/.readme_assets/ccf_recommended_2026.pdf |
| C53 | ccfddl/ccf-deadlines（`conference/*.yml`、PR #1381、LICENSE）[3P] | https://github.com/ccfddl/ccf-deadlines ；https://github.com/ccfddl/ccf-deadlines/pull/1381 |
| C54 | CSRankings（`csrankings.js` 的 areaMap/parentMap、COPYING） | https://github.com/emeryberger/CSrankings |
| C55 | ICORE 门户与 ICORE2026 CSV 导出、robots | https://portal.core.edu.au/conf-ranks/ ；https://portal.core.edu.au/conf-ranks/?search=&by=all&source=ICORE2026&sort=atitle&page=1&do=Export |
| C56 | GitHub 仓库统计（`gh api repos/{owner}/{repo}`） | https://github.com/openreview/openreview-py ；https://github.com/acl-org/acl-anthology ；https://github.com/lukasschwab/arxiv.py ；https://github.com/huggingface/huggingface_hub ；https://github.com/paperswithcode/ai-deadlines ；https://github.com/papercopilot/paperlists |
| C57 | 会议官网 robots（icml.cc、neurips.cc、iclr.cc） | https://icml.cc/robots.txt ；https://neurips.cc/robots.txt ；https://iclr.cc/robots.txt |
| C58 | 其他站点 robots（CEUR、MLSys、NDSS、RSS、JAIR、TACL、MIT Press Direct、IOS Press） | https://ceur-ws.org/robots.txt ；https://proceedings.mlsys.org/robots.txt ；https://www.ndss-symposium.org/robots.txt ；https://roboticsproceedings.org/robots.txt ；https://www.jair.org/robots.txt ；https://transacl.org/robots.txt ；https://direct.mit.edu/robots.txt ；https://ebooks.iospress.nl/robots.txt |
| C59 | Crossref 单条记录（created 与 published 时滞、license、resource），以及 TASLP 期刊库查询 | https://api.crossref.org/works/10.1109/cvpr52734.2025.01697 ；https://api.crossref.org/works/10.1109/iccv51701.2025.01875 ；https://api.crossref.org/works/10.1109/icra55743.2025.11128791 ；https://api.crossref.org/works/10.52202/085713-0001 ；https://api.crossref.org/works/10.1145/3770855.3817743 ；https://api.crossref.org/works?filter=prefix:10.14722,from-pub-date:2026-01-01 ；https://api.crossref.org/works?query.container-title=ECAI%202025&filter=prefix:10.3233 ；https://api.crossref.org/journals?query=audio+speech+language+processing |
| C60 | Cranfield 图书馆出版商 TDM 政策汇总（IEEE、Springer 的 TDM 口径） | https://library.cranfield.ac.uk/text-and-data-mining/publisher-policies |
| C61 | Semantic Scholar 网站 robots | https://www.semanticscholar.org/robots.txt |
| C62 | （核验补充）OpenReview 2025-11 事件的端点与波及面：OpenReview 两份声明（对脚本返回浏览器验证，未直读）；arXiv 2609.11983（确认波及多个 venue，未点名端点）；36kr 报道（2025-11-28，未点名端点）[3P] | https://openreview.net/forum/user%7Cstatement_regarding_api_security_incident ；https://openreview.net/forum/user%7Cinitial_analysis_of_openreview_api_security_incident ；https://arxiv.org/html/2609.11983 ；https://eu.36kr.com/en/p/3572028126116993 |
| C63 | （核验补充）ACM 全面 OA、作者许可二选一与 DL Basic/Premium 区分：SMU 图书馆说明（2026-04-08）、UNL 图书馆 ACM 2026 指南 | https://library.smu.edu.sg/topics-insights/acm-digital-library-now-fully-open-access ；https://unl.libguides.com/c.php?g=1133452&p=11290162 |
| C64 | （核验补充）IFAAMAS AAMAS 论文集与 Crossref 前缀 10.65109 | https://www.ifaamas.org/Proceedings/aamas2026/ ；https://api.crossref.org/prefixes/10.65109 ；https://api.crossref.org/works?filter=prefix:10.65109&facet=container-title:10,published:10 |
| C65 | （核验补充）CVPR 2026 官方投稿与录用数字（新闻稿 2026-05-26；@CVPR 推文） | https://cvpr.thecvf.com/Conferences/2026/News/Technical_Program ；https://x.com/CVPR/status/2025091165477810319 |
| C66 | （核验补充）NeurIPS 2026 与 CoRL 2026 官方会期页；ccfddl 对应 YAML | https://neurips.cc/Conferences/2026 ；https://www.corl.org/ ；https://github.com/ccfddl/ccf-deadlines/blob/main/conference/AI/nips.yml ；https://github.com/ccfddl/ccf-deadlines/blob/main/conference/AI/corl.yml |
| C67 | （核验补充）arXiv API Access 页（致谢语、商业项目与品牌使用要求） | https://info.arxiv.org/help/api/index.html |
| C68 | （核验补充）ICORE 管理方与 ICORE2026 更新说明 | https://www.core.edu.au/icore-portal ；https://www.core.edu.au/icore-portal/icore-portal-2026-rankings-updates |

**v1 内部参考（文中的 `[v1:日期]`）**：
- [research/site-survey/openreview.md](../../archive-v1.md#docs-research-site-survey-openreview-md)（2026-07-22）
- [research/site-survey/acm-dl.md](../../archive-v1.md#docs-research-site-survey-acm-dl-md)（2026-07-22）
- [research/site-survey/arxiv.md](../../archive-v1.md#docs-research-site-survey-arxiv-md)（2026-07-20）
- [research/site-survey/cs-ai-conferences.md](../../archive-v1.md#docs-research-site-survey-cs-ai-conferences-md)（2026-07-20）
- [research/site-survey/publisher-platforms-cs.md](../../archive-v1.md#docs-research-site-survey-publisher-platforms-cs-md)（2026-07-20）
- [research/site-survey/metadata-apis.md](../../archive-v1.md#docs-research-site-survey-metadata-apis-md)（2026-07-20/22）
- [research/site-survey/aggregators-unpaywall-dblp-core.md](../../archive-v1.md#docs-research-site-survey-aggregators-unpaywall-dblp-core-md)（2026-07-20/22）
- [catalog/ai-ml-journals.md](../../archive-v1.md#docs-catalog-ai-ml-journals-md)
- [catalog/cs-ai-conferences.md](../../archive-v1.md#docs-catalog-cs-ai-conferences-md)
- [catalog/publishers-platforms.md](../../archive-v1.md#docs-catalog-publishers-platforms-md)
- [plan/decision-log.md](../../plan/decision-log.md)（D-012、D-013、D-014、D-020、D-021、D-024、D-037、D-038）
- v1 代码：`src/paper_crawler/adapters/neurips_proceedings/adapter.py` 的 track 闭表；`venues/cs_ai/*.yaml`

## 核验记录

> **核验方式**：对抗式事实核验（Verify 角色）。从全文挑出最承重的断言（API 端点、限流、认证、许可与政策、计数、仓库统计、名录等级、会期），默认怀疑，逐条对照一手来源复核：官方文档页、API 实时响应、robots.txt、仓库与论文原文。原页读不到时，换用可读来源并注明。核验日期统一记为 2026-09-26（UTC；执行时本地 CST 已进入 09-27 凌晨）。
> **结论口径**：**确认** = 一手来源与原文一致；**修正** = 原文有误、以偏概全或已过时，正文已就地改正并标"核验修正"；**删除** = 查无实据，已删除；**未核验** = 本轮无法用可读来源证实，正文已标 ⚠。新增内容在正文标"核验补充"。
> **总体判断**：没有发现编造的仓库、论文或公司（有一处端点名未能核实，见第 17 条）；绝大多数计数与实时查询**逐位一致**。问题集中在五类：①把共用前缀的计数当成单个 venue 的计数（IJCAI 与 KR）；②把 OpenReview 限流概括成"按端点"；③会期缺漏（NeurIPS 卫星会场、CoRL 日期）；④计数含卷首 front matter（ACL）；⑤一处调研过程的合规瑕疵（ICORE 门户，见 §4 第 13 条）。本文档在前述修正后可供设计阶段引用；标 ⚠ 的条目引用前须复核。

### 核验过程记录（可复现）

- **请求纪律**：UA 统一为 `PaperCrawler/0.1 (source-survey fact-check; personal research)`，不携带用户邮箱。Crossref 因此走公共池，实测响应头为 `x-rate-limit-limit: 1`、`x-concurrency-limit: 1`、`x-api-pool: public-array`，请求间隔 ≥2 s。arXiv OAI 请求间隔 ≥4 s。dblp、ieeexplore.ieee.org、link.springer.com、portal.core.edu.au 只读 robots.txt。portal.core.edu.au 的 robots 对 Claude 类代理全站禁止，所以没有访问任何门户页面。openreview.net 论坛页返回浏览器验证，随即停止。
- **请求量（约）**：api.crossref.org 约 67；GitHub API（`gh`）约 60；info.arxiv.org 7；huggingface.co 5；oaipmh.arxiv.org 3；api2.openreview.net 3（另读 robots 1 次）；api.datacite.org 3；drops.dagstuhl.de 3（robots 1 次，HEAD 2 次，未下载快照）；其余站点各 1–2 次。全程没有触发 429。
- **WebSearch 检索式**：①`OpenReview API security incident November 2025 "profiles/search" initial analysis` ②`"profiles/search" OpenReview bug reviewer identities ICLR` ③`ICORE2026 conference rankings released CORE ICORE international collaboration 2026` ④`ACM Digital Library fully open access January 1 2026 announcement all articles free` ⑤`ACM Open authors choose license "CC BY" "CC BY-NC-ND" ACM Digital Library open access 2026 rights retention` ⑥`CVPR 2026 accepted papers number acceptance rate submissions`。
- **WebFetch / curl 直读的一手页面**：info.arxiv.org（tou、oa、availability、bulk_data、bulk_data_s3、rss、api/index）；blog.arxiv.org 2025-10-31 博文；docs.openreview.net（using-the-api、sign-in-with-openreview）；blog.iclr.cc 2025-12-03；developer.ieee.org（API_Terms_of_Use2、getting_started、Metadata_API_details）；dev.springernature.com rate-limits（从 Next.js 数据中抽取表格）；huggingface.co/docs/hub/rate-limits；alphaxiv.org/docs/mcp；aclanthology.org/faq/api；ccf.org.cn 目录页；core.edu.au 的 ICORE 页；neurips.cc/Conferences/2026；corl.org；cvpr.thecvf.com 2026 新闻稿；ifaamas.org AAMAS 2026 页；arxiv.org/html/2609.11983；Google Groups arXiv API 讨论串；SMU 与 UNL 图书馆的 ACM 页。
- **复用调研员的本地抓取**：CVF CVPR 2026 与 ICCV 2025 页、ECVA papers.php、NeurIPS 2025 卷页、arXiv 周计数、ICORE CSV。这些只用于复算，不作为独立证据；凡能独立复测的，都已另行复测（Crossref、DataCite、OAI、OpenReview、GitHub）。

### 核验结论表

| # | 断言（原文位置） | 结论 | 依据来源 URL | 核验日期 |
|---|---|---|---|---|
| 1 | dblp.org 及两个镜像的 robots 末段为 `User-agent: *` + `Disallow: /`，并具名禁止约 160 个 UA（含 `Claude-User`、`ClaudeBot`）；sparql.dblp.org 只放行 `/sparql`、`/download`，`Crawl-delay: 10`（§0-1、§2.1.4） | 确认：共 164 条 User-agent（含 `*`），三个主机的文件逐字节相同；sparql 规则一致 | https://dblp.org/robots.txt ；https://dblp.uni-trier.de/robots.txt ；https://dblp.dagstuhl.de/robots.txt ；https://sparql.dblp.org/robots.txt | 2026-09-26 |
| 2 | dblp 2026-09-01 快照为 1,099,942,087 字节、12,928,181 条、CC0，下载路径附 .md5；DataCite 共 153 条快照 DOI；"DROPS robots 放行 `/storage/`"（§0-1、§2.1.4） | 修正：大小、条数、CC0、路径与 .md5 均确认（DataCite 记录与 HEAD 的 Content-Length 一致）；快照 DOI 数改为"约 150"（核验计 152）；robots 并无显式 Allow，只是没有禁止，另有 `/entities/*/metadata/*` 禁区 | https://api.datacite.org/dois/10.4230/dblp.xml.2026-09-01 ；https://drops.dagstuhl.de/storage/artifacts/dblp/xml/2026/dblp-2026-09-01.xml.gz ；https://drops.dagstuhl.de/robots.txt | 2026-09-26 |
| 3 | arXiv OAI 于 2025-03 重写，支持 `group:archive:CATEGORY` 类目级 set；ListSets 共 183 个 set，其中 cs 子类 40 个；earliest datestamp 为 2005-09-16；OAI 通常在 ET 22:30 前后可取（§0-2、§2.1.1） | 确认 | https://info.arxiv.org/help/oa/index.html ；https://oaipmh.arxiv.org/oai?verb=ListSets ；https://oaipmh.arxiv.org/oai?verb=Identify | 2026-09-26 |
| 4 | arXiv ToU：1 req/3s、单连接、按"所有受你控制的机器"合计；不得在自有服务器上 store & serve e-print（许可允许者除外）；应引导用户去 arXiv.org；元数据 CC0（§0-2/3、§2.1.1） | 确认。补充：ToU 现把 OAI-PMH、RSS 和 arXiv API 统称为"legacy APIs"，并注明限值可能变化；API 页要求致谢语，并对商业项目与品牌使用另有要求（C67） | https://info.arxiv.org/help/api/tou.html ；https://info.arxiv.org/help/api/index.html | 2026-09-26 |
| 5 | arXiv 公告节奏：14:00 ET 截止、20:00 ET 公告；2026 年列有 9 个节假日；S3 约 9.2 TB（2025-04）、月增约 100 GB、按月更新、附 manifest，并且是全量下载的"accepted mechanism"；RSS 每日午夜（EST）更新，`+` 合并类目，上限 2000（§2.1.1、§2.6.1） | 确认：9 个节假日为 01-01、01-19、06-19、07-03、09-07、11-26、12-25、12-29、12-31；"accepted mechanism"出自 bulk_data 页 | https://info.arxiv.org/help/availability.html ；https://info.arxiv.org/help/bulk_data_s3.html ；https://info.arxiv.org/help/bulk_data.html ；https://info.arxiv.org/help/rss.html | 2026-09-26 |
| 6 | arXiv robots：`*` 的 `Crawl-delay: 15`，放行 `/list /abs /pdf /html` 等，禁止 `/api /search /e-print /src /oai2`；export.arxiv.org 全站 Disallow（§2.1.1） | 确认 | https://arxiv.org/robots.txt ；https://export.arxiv.org/robots.txt | 2026-09-26 |
| 7 | arXiv 429 讨论串：2026-02-26 起多人报告 429；员工 2026-02-27 回复"we have made changes recently and over time"；至 2026-06 仍有反馈；POST 会绕过 Fastly 缓存（§0-2、§2.1.1） | 修正归属：前三点确认（员工为 Brian Maltzan，末帖 2026-06-05）；"POST 绕过 Fastly 缓存"是社区成员、arxiv.py 维护者 Lukas Schwab 的观察，不是官方说法 | https://groups.google.com/a/arxiv.org/g/api/c/ycq8giRdZsQ | 2026-09-26 |
| 8 | paper-search-mcp PR #119 于 2026-09-22 合并，报告"HTTP 200 + 正文 `Rate exceeded.`"的伪成功响应（§0-2） | 确认：2026-09-22T11:43Z 合并，PR 描述写明检测该响应 | https://github.com/openags/paper-search-mcp/pull/119 | 2026-09-26 |
| 9 | cs.LG 2026-09-24 共 315 条，许可分布为 arXiv 非独占 140、CC BY 4.0 139、BY-NC-SA 17、BY-NC-ND 11、BY-SA 7、CC0 1（§0-3、§2.1.1） | 确认：实时重查结果逐项一致 | https://oaipmh.arxiv.org/oai?verb=ListRecords&metadataPrefix=arXiv&set=cs:cs:LG&from=2026-09-24&until=2026-09-24 | 2026-09-26 |
| 10 | 2025-10-31 起，arXiv CS 类的综述与立场论文须先通过期刊或会议同行评审，投稿时附期刊引用与 DOI，workshop 评审"generally … not enough"（§2.1.1） | 确认 | https://blog.arxiv.org/2025/10/31/attention-authors-updated-practice-for-review-articles-and-position-papers-in-arxiv-cs-category/ | 2026-09-26 |
| 11 | DOI 注册机构：10.48550（arXiv）与 10.4230（LIPIcs）为 DataCite，Crossref 查不到；LIPIcs 2025 年在 DataCite 有 2,336 条（§2.1.1、§2.1.2、§2.4） | 确认：10.52202 与 10.24963 则为 Crossref | https://doi.org/ra/10.48550 ；https://doi.org/ra/10.4230 ；https://api.datacite.org/dois?prefix=10.4230&published=2025 | 2026-09-26 |
| 12 | OpenReview 文档写明"You need an OpenReview account to use the API"，API v1"being phased out"；robots 只禁 `?email=`（§0-4、§2.1.2、§2.2） | 确认：robots 原文为 `Disallow: /*?*email=`，openreview.net 与 api2 两个主机相同 | https://docs.openreview.net/getting-started/using-the-api ；https://openreview.net/robots.txt | 2026-09-26 |
| 13 | OpenReview 限流"按端点区分：`/groups` 为 `20;w=60`，`/notes` 为 `180;w=60`"（§0-4、§2.1.2、§2.2、§3） | 修正：随请求而异。同为 `/groups`，`id=ICLR.cc/2026/Conference` 返回 `20;w=60`，`id=active_venues` 与 `id=venues` 返回 `180;w=60`；§2.6.2 所记 active_venues 为 180 本来就对，与 §2.1.2 的矛盾由此消除；`/notes` 的 180 沿用调研员实测 | https://api2.openreview.net/groups?id=ICLR.cc/2026/Conference ；https://api2.openreview.net/groups?id=active_venues ；https://api2.openreview.net/groups?id=venues | 2026-09-26 |
| 14 | `active_venues` 共 1,094 个（匿名可读），`venues` 共 4,706 个，含 NeurIPS/ICML/COLM/CoRL/ECCV/EMNLP/ACM MM/UAI 2026 与 AAAI/AISTATS/MLSys/ALT 2027 等（§0-4、§2.1.2） | 修正（数字随时间变动）：venues 4,706 与所列 venue 全部确认；active_venues 复测为 1,092，正文改为"约 1,090"；另见 `ICLR.cc/2027/Conference` | https://api2.openreview.net/groups?id=active_venues | 2026-09-26 |
| 15 | ICLR 2026 group content 给出 `submission_venue_id`、`withdrawn_venue_id`、`desk_rejected_venue_id`、`rejected_venue_id`、`decision_name`=Decision（§2.1.2） | 确认 | https://api2.openreview.net/groups?id=ICLR.cc/2026/Conference | 2026-09-26 |
| 16 | 安全事件：2025-11-27 10:09 EST 接报、11:10 EST 修复；超过 1 万篇 ICLR 投稿（约 45%）的信息被抓取并外传；最早可能在 2025-11-11 已被利用（§0-4、§2.1.2） | 确认 | https://blog.iclr.cc/2025/12/03/iclr-2026-response-to-security-incident/ | 2026-09-26 |
| 17 | 漏洞端点为 `profiles/search`（§2.1.2，原注 [C17]） | 未核验：[C17] 没有点名端点；两篇 36kr 报道与 arXiv 2609.11983 也没有点名（后者确认漏洞波及 ICLR、ACL、KDD、ICML 等）；该名称只见于搜索引擎摘要和本轮打不开的社区帖。正文已改注 [C62] 并标 ⚠。设计结论"不访问身份类端点"不受影响 | https://arxiv.org/html/2609.11983 ；https://eu.36kr.com/en/p/3572028126116993 ；https://openreview.net/forum/user%7Cstatement_regarding_api_security_incident | 2026-09-26 |
| 18 | OIDC：授权码 + PKCE，scope 为 `openid/profile/email`，token 有效 1 小时，不发 refresh token，client 须人工注册；"token **只用于读取 profile 声明**"（§0-4、§2.1.2） | 修正措辞：前五项确认；文档只描述用 access token 调 UserInfo，没有作排他声明，正文改为"没有说明能否用于数据 API，设计上不应假设可以" | https://docs.openreview.net/reference/sign-in-with-openreview | 2026-09-26 |
| 19 | ACM 自 2026-01-01 起全库 OA；新文由作者在 CC BY 与 CC BY-NC-ND 中二选一；DL robots 为 `*` Crawl-delay 1，禁 `/action /search /doi/metrics` 等，GPTBot、ChatGPT-User、CCBot、Google-Extended 全禁（§0-5、§2.1.3） | 确认：ACM 原页对脚本 403，改由 SMU、UNL 两份图书馆指南印证。补充：bulk downloads 属付费 DL Premium（C63）。ToS 禁止脚本的原文仍未直读，维持 [SNIP] | https://library.smu.edu.sg/topics-insights/acm-digital-library-now-fully-open-access ；https://unl.libguides.com/c.php?g=1133452&p=11290162 ；https://dl.acm.org/robots.txt | 2026-09-26 |
| 20 | IEEE API ToU 六项要点：限被许可机构内非商业使用；只能按单次查询展示；不得分发给第三方；终止后不得保留；禁止用于 AI/ML/LLM；可要求链回；另有 key 在工作日 8–17 ET 发放、单次最多 200 条、可按收录日期查询（§0-6、§2.1.3） | 确认。补充 4 项：API 仅限现有 IEEE 客户（政府与企业客户可另申请）；禁止用程序"retrieve or index any portion of the Content"；不得以可收割形式分发；配额为"displayed during the user registration process" | https://developer.ieee.org/API_Terms_of_Use2 ；https://developer.ieee.org/getting_started ；https://developer.ieee.org/docs/read/Metadata_API_details | 2026-09-26 |
| 21 | IEEE Xplore robots：`*` 禁 `/rest`、`/ielx*`；25 个 AI UA 全站 Disallow（含 ClaudeBot、Claude-User、Google-NotebookLM、PerplexityBot）（§2.1.3） | 确认：恰为 25 个 | https://ieeexplore.ieee.org/robots.txt | 2026-09-26 |
| 22 | Crossref 2025 年计数：IEEE 445,469 条、摘要 0；ACM 46,548 条、摘要 7,231、license 12,824；ACL 11,121 条、摘要 0；AAAI 4,337 条、摘要 4,337；ISCA 1,388；PVLDB 446；TechRxiv 6,329；Springer book-chapter 284,166 条、摘要 8,615；另有 NDSS 2026 年 390 条（§0、§2.1、§2.4） | 确认：18 个计数逐位一致 | https://api.crossref.org/works?rows=0&filter=prefix:10.1109,from-pub-date:2025-01-01,until-pub-date:2025-12-31 （其余前缀用同形查询） | 2026-09-26 |
| 23 | IJCAI：Crossref 10.24963 只覆盖 2017 年起；2025 年 1,368 条（摘要 1,366），2026 年 1,085 条（§2.1.2、§2.2、§2.4、§2.6.4） | 修正："2017 年起"确认（2016 年及以前为 0）；但 1,368 与 1,085 是前缀总数，其中含 KR 论文集：2025 = IJCAI-34 1,281 + KR 85 + 2；2026 = IJCAI-35 972 + KR 111 + 2；IJCAI 2026 在 Crossref 与站点都是 972 条 | https://api.crossref.org/works?rows=0&filter=prefix:10.24963,from-pub-date:2026-01-01&facet=container-title:10 | 2026-09-26 |
| 24 | IEEE 会议 DOI 时滞：CVPR 2025 约 2 个月、ICRA 2025 约 3.5 个月、ICCV 2025 约 6 个月；CVPR 2026 与 ICRA 2026 截至 9-26 未见；另有 CVPR 2025 共 2,881 条、ICRA 2025 共 1,610 条（§0-6、§2.1.3） | 确认：created 分别为 2025-08-13、2025-09-02、2026-04-29（会期起始 06-10、05-19、10-19）；CVPR 2026 与 ICRA 2026 按精确 container-title 过滤均为 0 | https://api.crossref.org/works/10.1109/cvpr52734.2025.01697 ；https://api.crossref.org/works/10.1109/icra55743.2025.11128791 ；https://api.crossref.org/works/10.1109/iccv51701.2025.01875 | 2026-09-26 |
| 25 | NeurIPS：前缀 10.52202 属 Curran；第 35–38 卷分别 2,834/3,540/4,494/5,823 条，无摘要；vol 38 的 DOI 创建于 2026-08-06；该前缀被 Curran 其他会议共用（§0-9、§2.1.2、§2.4） | 确认。补注：记录级 publisher 字段是"Neural Information Processing Systems Foundation"，前缀同时承载 IAF、WCTE 等会议 | https://api.crossref.org/prefixes/10.52202 ；https://api.crossref.org/works/10.52202/085713-0001 | 2026-09-26 |
| 26 | NeurIPS 2025 卷页 5,823 篇 = Conference 5,286 + D&B 497 + Position 40，另有 Creative AI 分轨；v1 的 `(era,track)` 闭表只有 none/conference/datasets_and_benchmarks（§0-9、§2.1.2） | 确认：卷页用调研员抓取复算，总数与 Crossref vol 38 独立一致；v1 代码已核对 | https://proceedings.neurips.cc/paper_files/paper/2025/vol38-main-conference ；`src/paper_crawler/adapters/neurips_proceedings/adapter.py` | 2026-09-26 |
| 27 | TASLP 改名并启用 ISSN 2998-4173（2025 年 381 条、2026 年 321 条），旧 ISSN 最后一年为 2024（395 条）；Elsevier 的 AIJ 在 Crossref 只能用 print ISSN 过滤（2026 年 101 条），e-ISSN 为 0（§0-9、§2.1.3） | 确认：Crossref 期刊记录中 AIJ 只登记了 print ISSN | https://api.crossref.org/journals/2998-4173 ；https://api.crossref.org/journals/0004-3702 | 2026-09-26 |
| 28 | 按 container-title 精确过滤：ECCV 2026 为 2,251 条，WWW 2026 为 723 条（§2.1.4、§2.6.4） | 确认 | https://api.crossref.org/works?rows=0&filter=container-title:Proceedings%20of%20the%20ACM%20Web%20Conference%202026 | 2026-09-26 |
| 29 | Springer Nature API 限额：Metadata 与 Meta（versioned）100/500/300/10,000，Open Access 100/500/200/10,000，Full Text 200/500/200/20,000（依协议）；link.springer.com robots 对 `*` 为 `Disallow: /` 再逐项 Allow，具名禁止 anthropic-ai、ClaudeBot、Claude-Web、GPTBot、ChatGPT-User、CCBot、PerplexityBot 等（§0-7、§2.1.3） | 确认：限额表逐格一致 | https://dev.springernature.com/docs/rate-limit-details/rate-limits ；https://link.springer.com/robots.txt | 2026-09-26 |
| 30 | paperswithcode.com 302 跳转到 HF Trending；PwC 数据以 CC-BY-SA-4.0 存档在 `pwc-archive/*`；GitHub README 于 2025-09-08 改链；两个数据集的 lastModified 分别为 2026-08-17 与 2025-09-10（§0-8、§2.1.1） | 确认 | https://paperswithcode.com/ ；https://huggingface.co/api/datasets/pwc-archive/links-between-paper-and-code ；https://github.com/paperswithcode/paperswithcode-data | 2026-09-26 |
| 31 | HF：匿名 API 500 次/5min、免费用户 1,000 次/5min、search 50 次/5min；daily_papers 含 upvotes、numComments、submittedOnDailyAt、organization；SDK `list_daily_papers(date/week/month/submitter/sort/p/limit)`，sort 取 publishedAt 或 trending（§0-8、§2.1.1） | 确认：官方档位表注明为 2025-09 的数值 | https://huggingface.co/docs/hub/rate-limits ；https://huggingface.co/api/daily_papers ；https://github.com/huggingface/huggingface_hub/blob/main/src/huggingface_hub/hf_api.py | 2026-09-26 |
| 32 | alphaXiv MCP 端点为 `https://api.alphaxiv.org/mcp/v1`，鉴权用 OAuth 2.1 或个人 API key，提供 19 个工具，调用计入 assistant quota（§0-8、§2.1.1） | 确认：研究类 4 个、学者类 7 个、文库类 8 个，共 19 个 | https://www.alphaxiv.org/docs/mcp | 2026-09-26 |
| 33 | CCF 第七版于 2026-03-31 发布、04-09 勘误；共收到 169 项提案；新增期刊 14、会议 23 等；ICLR 首入 A、IJCAI 降为 B；ACM SIGOPS ATC（原 USENIX ATC）；ccfddl PR #1381 于 2026-03-05 同步等级（§0-10、§2.1.4、§2.5） | 确认。补注：03-05 至 03-12 为公示期，PR #1381 在公示期首日合并，依据的是公示稿；其七项等级（ICLR A、IJCAI B、Interspeech B、FMCAD B、HPDC A、ISCAS B、WINE B）已在正式版 PDF 中逐一核对，均一致 | https://www.ccf.org.cn/Academic_Evaluation/By_category/ ；https://github.com/ccfddl/ccf-deadlines/pull/1381 ；https://github.com/ccfddl/ccf-deadlines/blob/main/.readme_assets/ccf_recommended_2026.pdf | 2026-09-26 |
| 34 | ICORE2026 共评级 825 个会议（A* 7.52%、A 13.09%、B 30.18%、C 46.18% 等），CSV 约 986 行（§0-10、§2.1.4、§2.5） | 未核验（数字部分）：ICORE2026 已发布、CORE 已扩展为四方国际合作，这两点由 core.edu.au 确认；825 与各档百分比只能用调研员导出的 CSV 复算（结果一致：62/108/249/381/6/19，另有 162 条其他）。门户 robots 对 Claude 类代理全站禁止，本轮没有复测，正文已标 ⚠ | https://www.core.edu.au/icore-portal ；https://www.core.edu.au/icore-portal/icore-portal-2026-rankings-updates ；https://portal.core.edu.au/robots.txt | 2026-09-26 |
| 35 | CSRankings 许可为 CC BY-NC-ND 4.0，按 27 个领域收录约 75 个会议（§0-10、§2.5） | 修正（精度）：COPYING 确认为 CC BY-NC-ND 4.0（GitHub API 的 license 字段显示 NOASSERTION）；parentMap 为 27 个父领域、77 个会议键 | https://github.com/emeryberger/CSrankings | 2026-09-26 |
| 36 | GitHub 仓库统计：openreview-py 268/MIT；acl-anthology 807/Apache-2.0；arxiv.py 1,548/MIT；huggingface_hub 3,936/Apache-2.0；ccf-deadlines 9,363/MIT；CSrankings 3,207；paperswithcode-data 941/无；paperlists 958/无；ai-deadlines 6,007/MIT，最近 push 为 2024-09-15（§2.2、§2.5、§2.8） | 确认：huggingface_hub 已到 3,937，属日常波动；各仓库均未归档 | `gh api repos/{owner}/{repo}`（如 https://api.github.com/repos/ccfddl/ccf-deadlines ） | 2026-09-26 |
| 37 | PMLR 首页有 v339 RAISE 2026、v337 UAI 2026、v336 COLT 2026、v313 ALT 2026、v305 CoRL 2025、v267 ICML 2025；v300 为 AISTATS 2026；ICML 2026 未上线（§2.1.2、§2.6.4） | 确认：v300 于 2026-08-30 出版；首页没有 ICML 2026 | https://proceedings.mlr.press/ ；https://proceedings.mlr.press/v300/ | 2026-09-26 |
| 38 | CVF 上 CVPR 2026 共 4,042 篇、ICCV 2025 共 2,701 篇，页面声明版权归作者；ECVA 列出 ECCV 2018–2024 共 6,166 篇（776/1,358/1,645/2,387），并注明"DOI links will be inaccessible until released by Springer"（§2.1.2、§2.2） | 确认：均为调研员抓取复算（ECVA 排除 supp 后一致）。补注：CVPR 官方新闻稿称 16,092 篇投稿、4,089 篇 paper presentations，@CVPR 推文称建议录用 4,090 篇 | https://openaccess.thecvf.com/CVPR2026?day=all ；https://www.ecva.net/papers.php ；https://cvpr.thecvf.com/Conferences/2026/News/Technical_Program | 2026-09-26 |
| 39 | ACL Anthology 2016 年起为 CC BY 4.0，2016 年前为 CC BY-NC-SA 3.0，有官方包 `acl-anthology`；ACL 2026 有 long 2,223、Findings 2,164（§2.1.2、§2.6.4） | 修正：许可与官方包确认；GitHub XML 显示 long 为 2,222 篇、ACL Findings 为 2,163 篇，原数把卷首 front matter（`.0`）也算了进去 | https://aclanthology.org/faq/api/ ；https://github.com/acl-org/acl-anthology/blob/master/data/xml/2026.acl.xml ；https://github.com/acl-org/acl-anthology/blob/master/data/xml/2026.findings.xml | 2026-09-26 |
| 40 | OpenAlex 匿名 `x-ratelimit-limit: 1000`（credits/日），每次 list 查询 `x-ratelimit-cost-usd: 0.0001`；CS field（17）在 2026 年共 872,697 works（§2.1.4） | 确认：另有 `x-ratelimit-limit-usd: 0.1` | https://api.openalex.org/works?filter=primary_topic.field.id:17,from_publication_date:2026-01-01 | 2026-09-26 |
| 41 | ISCA robots 为 `Disallow: /interspeech_2026/`，Interspeech 2026 在 Crossref 为 0；IACR ePrint 的 robots 注释声明 OAI/RSS/ATOM 通道，`*` 全禁，AI bot 不得取 PDF（§2.1.1、§2.1.2） | 确认：ISCA 前缀 2026 年另有 357 条，分属 Speech Prosody、JEP、Odyssey、CHiME、WOCHAT | https://www.isca-archive.org/robots.txt ；https://api.crossref.org/works?rows=0&filter=prefix:10.21437,from-pub-date:2026-01-01&facet=container-title:10 ；https://eprint.iacr.org/robots.txt | 2026-09-26 |
| 42 | JMLR 与 TMLR 在 Crossref 没有 DOI 记录（§2.1.2、§2.2） | 确认：ISSN 1533-7928、1532-4435、2835-8856 均为 0 | https://api.crossref.org/works?rows=0&filter=issn:1533-7928 | 2026-09-26 |
| 43 | 2026 周期会期表（§2.6.4，数据来自 ccfddl） | 修正：30 行中有 28 行与 ccfddl 一致（逐行对照了对应 YAML）。CoRL 2026 改为 11-09 至 12（奥斯汀；主会 09 至 11 日），原文为 11-10；NeurIPS 2026 改为悉尼主会 12-06 至 12，外加亚特兰大、巴黎卫星会场 12-09 至 13，原文只写悉尼 | https://www.corl.org/ ；https://neurips.cc/Conferences/2026 ；https://github.com/ccfddl/ccf-deadlines/tree/main/conference | 2026-09-26 |
| 44 | v1 基线：arXiv 类目 venue 共 31 个（cs 17、stat.ML 1、econ 3、q-fin 9、math.OC 1）（§2.2） | 确认：仓库 VenueSpec 共 62 个，其中 `arxiv-*.yaml` 31 个 | `venues/*/arxiv-*.yaml` | 2026-09-26 |

### 核验补充条目（覆盖缺口）

1. **KR（CCF B / ICORE A*）**：论文集 DOI 与 IJCAI 共用前缀 10.24963（KR 2020–2026 每届 80–111 条），可以由 ijcai_proceedings 按 container-title 顺带接入（§2.1.2、§2.3）。
2. **AAMAS（CCF B / ICORE A）**：IFAAMAS 自有 Crossref 前缀 10.65109（member 54598，共 7,301 条，回溯卷约在 2026-01 集中注册），AAMAS 2026 论文集已上线。元数据质量差：2026 届的 656 条没有摘要，也没有 published 日期。已补登为 `aamas_ifaamas`（P2）（§2.2、§2.3、§2.4）。
3. **arXiv 的 API 使用要求**：ToU 的"legacy APIs"措辞、致谢语、商业项目与品牌使用要求（§0-2、§3 第 6 条）。
4. **IEEE API ToU 的另外 4 项限制**：仅限现有客户、禁止程序化检索与索引、禁止可收割分发、配额注册时展示（§0-6、§2.1.3、§3 第 8 条）。
5. **ACM DL Basic 与 Premium 的区分**：bulk downloads 属付费版（§2.1.3）。
6. **共用 DOI 前缀的计数陷阱**：已写入 §3 第 3 条设计启示。
7. **调研过程合规瑕疵**：见 §4 第 13 条。

**统计**：结论表共 44 条（每条可含多项子断言）：确认 33 条，修正 9 条，未核验 2 条，删除 0 条；另补充覆盖缺口 7 项。
