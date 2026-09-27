---
title: 开源调研：论文获取、检索与学术搜索相关 GitHub 项目
status: draft
owner: opus5.5-survey
updated: 2026-09-26
---

# 开源调研：论文获取、检索与学术搜索相关 GitHub 项目

> **定位**：v2 重设计"调研阶段"开源生态专题（draft，待主 agent 评审）。在 v1 调研
> [github-similar-projects.md](../../archive-v1.md#docs-research-github-similar-projects-md)（2026-07-20，20 项）基础上**复核全部 20 项**，
> 并按"多源检索客户端 / 学术 MCP / LLM 研究助手 / 每日推送与刷论文 feed / 开源学术搜索与知识组织 /
> 文献管理 / PDF 解析 / 检索与存储基础设施 / 合规反例"九类扩展，共覆盖 **197 个项目**（196 个 GitHub 仓库 + ORKG 的 GitLab 仓库组）。
>
> **数据快照**：所有 ★（star）、license、最近提交、发版信息均为 **2026-09-26** 通过 GitHub REST API 实测
> （UTC 约 14:50–15:40），原始数据见附件
> [repo-metrics-2026-09-26.tsv](paper-acquisition-and-search-oss/repo-metrics-2026-09-26.tsv)（198 行数据，生成命令见 §1.4）。
> 外部政策/API 事实均附来源 URL，核验日期同为 2026-09-26；无法核验者标 **⚠ 未核验**。
>
> **对抗式核验**（2026-09-26，UTC 约 19:00–20:00，另一 agent 执行）：196 个 GitHub 仓库经 API 复测全部存在，★ 偏差 ≤8、许可/归档状态零差异
> （[repo-metrics-verify-2026-09-26.tsv](paper-acquisition-and-search-oss/repo-metrics-verify-2026-09-26.tsv)）；
> 正文中凡标"**核验修正**/**核验补充**"处为本轮改动，逐条依据见文末"核验记录"。
>
> **相邻专题**（其他调研 agent 产出，本文不重复）：推荐算法开源见 [recommendation-oss.md](recommendation-oss.md)；
> 社媒推荐算法见 [../algorithms/social-media-recsys.md](../algorithms/social-media-recsys.md)；初创与产品见
> [../market/startups-and-products.md](../market/startups-and-products.md)；来源名录见 [../sources/](../sources/)。

## 0. 速览（TL;DR）

1. **外部环境在 2025-07 → 2026-09 发生了三次"地基级"变化**：Papers with Code 于 2025-07-24 关停并重定向到 HF；
   Crossref 自 2025-12-01 按"单条/列表"分档限速；OpenAlex 自 2026-02-13 强制 API key 并改为**按美元计费**
   （singleton 免费、list $0.1/千次、search $1/千次、PDF $10/千次，每 key 每日 $1 免费），同时开放 OA 作品的
   PDF/TEI 下载（博客 2026-02 称 6,000 万；**核验修正**：帮助页 2026-09-18 口径为"5,000 万+，TEI 约 4,300 万"，且声明 PDF 保留原版权、
   OpenAlex 不授予额外权利）、语义检索（beta）、官方 CLI 与官方 MCP（OAuth + 用户自有额度）。依赖这些源的开源工具大量出现文档漂移或失效。
2. **依赖漂移是真实风险**：`arxiv.py` 4.0.0（2026-05-17）移除 `Search.results()` 后，1,500★ 的 `cv-arxiv-daily`
   "Daily" workflow（实为每 5 天一次的 cron）**自 2026-05-21 起每次运行均失败**（截至 2026-09-26 共 29 次，日志 `AttributeError`；
   **核验修正**：原文仅列 09-16/21/26 三次）——印证 v1"自有薄 adapter + canary"路线。
3. **多源检索的最佳开源范式**是 findpapers main 分支重写版：统一查询 AST → 每源 `QueryBuilder`（声明支持的过滤码）→
   `QueryExecutionPlan`（**核验修正**：实为"不能原生表达时展开为析取范式 DNF、每个合取子句一个远端请求、结果按并集去重"，
   并非通用的交/并/差集合代数）→ DOI/标题去重合并 → 富化 → 引用雪球/相似检索。**但其默认富化源 `web_scraping` 用 curl_cffi
   冒充 Chrome TLS 指纹以绕过出版商 WAF**（核验补充），该组件属红线，只借鉴查询编译。
4. **路由算法的最佳开源参照**是 Ai2 Asta PaperFinder（冻结快照）："查询→结构化对象→执行规划器→按找论文意图分流到不同工作流→LLM
   相关性判定→按内容相关性与附加准则综合排序"。
5. **推荐/推送类开源项目很多但都很"单机/单人"**：zotero-arxiv-daily（5,991★，以个人库嵌入 + 时间衰减打分）、
   daily-paper-reader（多 lane 召回 → 统一候选池 → Qwen3-Reranker 重排 → LLM refine）、PaperFlow（强/弱反馈与兴趣漂移）、
   papertok（信号全集 + 诚实标签）是 v2 候选生成/排序/反馈设计的主要样本；**卡片/竖滑式"刷论文"开源前端
   （papertok 27★、arxivtok 91★、paper-deck 15★、flopap 7★）均 <100★**，无成熟对手。
6. **多用户隔离的现成积木**：Qdrant `is_tenant` + 每租户 HNSW、pgvector 迭代扫描 + 分区、Vespa streaming（`g=userid`）、
   Meilisearch tenant token / Typesense scoped key、local-deep-research 的"每用户 SQLCipher 加密库"。
7. **合规红线在开源生态中普遍被越过**：Sci-Hub/LibGen MCP、Google Scholar 代理池/浏览器自动化、UA 冒充升级重试、
   CNKI 浏览器自动化下载均存在于高星项目中（组件级）；**核验补充**：findpapers（Chrome TLS 指纹冒充）、gpt_academic（Sci-Hub 数据源 +
   冒充 Chrome UA 抓 Scholar）、paper-search-mcp-nodejs（Sci-Hub + Scholar 代抓服务）、PaperFlow（抓取公开 Scholar 主页）同样含越线组件。
   v2 只能"借鉴架构、排除组件"。
8. **PDF 解析进入 VLM 时代，但许可分层复杂**：代码多为 Apache/MIT，权重另有门槛（Marker/Surya <500 万美元、Chandra <200 万且不得与其 API 竞争、
   MinerU 按 MAU/营收阈值且在线服务须显著标注、Nougat/Dolphin/MonkeyOCR 非商用或研究许可）；GROBID（0.9.1）仍是参考文献/TEI 结构化的事实标准。

---

## 1. 调研范围与方法

### 1.1 范围

**纳入**：GitHub（及 ORKG 所在 GitLab）上与以下主题相关、截至 2026-09-26 仍可访问的开源项目——
多来源论文获取与元数据检索、学术检索/推荐/每日论文追踪、个人文献库与插件、PDF 全文结构化、检索与存储基础设施、
二级仓储平台软件（OAI-PMH 源族）。对闭源产品（如 Scholar Inbox、Cool Papers 站点）只在其有公开仓库或论文时提及。

**排除**：纯论文清单类 awesome 仓库；纯模型训练代码（除非直接用于论文表示/抽取）；推荐算法本体（归
[recommendation-oss.md](recommendation-oss.md)）；初创公司商业分析（归 [market/](../market/)）。

### 1.2 字段口径

| 字段 | 口径 |
|---|---|
| ★ | GitHub REST `GET /repos/{owner}/{repo}` 的 `stargazers_count`，2026-09-26 实测；仓库改名/迁组时以 API 返回的规范名为准（如 `kermitt2/grobid`→`grobidOrg/grobid`） |
| License | API `license.spdx_id`；为 `NOASSERTION`/`none` 时**读 LICENSE 原文**判定（如 Meilisearch=MIT+BUSL、Weaviate=BSD-3+Weaviate License、Dolphin=Qwen Research License、ChatPaper=CC BY-NC-ND 4.0）；模型权重许可单独标注 |
| 最近活跃 | `GET /repos/{r}/commits?per_page=1` 默认分支最近提交日（优于 `pushed_at`，后者会被其他分支推高，如 arxiv-sanity-lite `pushed_at`=2023-06-19 但默认分支最近提交=2022-02-14）；`/releases/latest` 的 tag 与日期；无 GitHub release 者补查 PyPI JSON |
| 定位 / 架构要点 | 读 README 与关键文档/源码目录（`gh api repos/{r}/readme`、`contents/`、`git/trees`）；未读代码处只陈述 README 自述 |
| 可借鉴 / 合规风险 | 对照 v1 红线（AGENTS.md、D-006/D-014/D-020 等）与本轮 v2 红线（多用户下 auth-gated 全文不得跨用户共享） |

### 1.3 v2 分级定义

| 级 | 含义 |
|---|---|
| **R 直接复用** | 以依赖库/组件形式进入 v2 代码或部署；许可宽松（MIT/Apache/BSD/PostgreSQL/Blue Oak 等）、活跃、无合规问题 |
| **I 集成** | 以独立服务、sidecar、外部 API/MCP 或"用户自有账号"方式对接，不链接其源码；或带明确前置条件（许可门槛、UA 改造、每用户凭证） |
| **B 仅借鉴** | 学习其架构/算法/交互；因许可（AGPL/GPL/无 license）、停更、形态不符而不引入代码 |
| **X 排除** | 触碰合规红线（盗版源、Scholar 自动化、冒充、绕验证码），或技术性淘汰（已归档/平台关停/非商用权重） |

### 1.4 过程记录（可复现）

**时间**：2026-09-26（UTC 约 14:40–15:50，即北京时间 22:40–23:50），单次会话完成。

**工具与命令**：

```bash
# 1) 仓库事实（star/license/推送/归档/创建/描述 + 最新 release + 默认分支最近提交）
gh api repos/OWNER/REPO --jq '[.full_name,.stargazers_count,(.license.spdx_id//"none"),.pushed_at[0:10],.archived,.created_at[0:10],.description]|@tsv'
gh api repos/OWNER/REPO/releases/latest --jq '[.tag_name,.published_at[0:10]]|@tsv'
gh api "repos/OWNER/REPO/commits?per_page=1" --jq '.[0].commit.committer.date[0:10]'
gh api repos/OWNER/REPO/license --jq '.content|@base64d'        # NOASSERTION 时读原文
gh api repos/OWNER/REPO/readme --jq .content | base64 -d         # README 精读
# 2) 候选发现（GitHub 搜索，sort=stars）
gh api -X GET search/repositories -f q="<query>" -f sort=stars -f order=desc -f per_page=8
gh api "orgs/ourresearch/repos?per_page=100&sort=pushed"          # 官方组织新仓库
# 3) 发版口径补充
curl -s https://pypi.org/pypi/<pkg>/json                           # 无 GitHub release 者
curl -s "https://gitlab.com/api/v4/projects/TIBHannover%2Forkg%2Forkg-backend?license=true"
# 4) 失败佐证
gh api repos/Vincentqyw/cv-arxiv-daily/actions/runs?per_page=5
gh api repos/Vincentqyw/cv-arxiv-daily/actions/jobs/108324242049/logs --allow-escape-sequences
```

**GitHub 检索式**（`search/repositories`，按 star 排序）：`arxiv mcp server`、`paper search mcp`、`semantic scholar mcp`、
`openalex mcp`、`zotero mcp`、`pubmed mcp`、`google scholar mcp`、`academic search mcp`、`crossref mcp`、`scholarly mcp`、
`arxiv daily`、`daily arxiv llm`、`arxiv recommendation`、`paper recommendation zotero`、`personalized arxiv`、`arxiv digest`、
`paper feed`、`scholar inbox`、`arxiv sanity`、`tiktok papers arxiv`、`swipe papers`、`tinder papers`、`papertok`、`wikitok arxiv`、
`arxiv scroll feed`、`research paper feed swipe`、`paper swipe app`、`scroll arxiv`、`paper-qa`、`openscholar`、`local citation network`、
`citation gecko`、`connected papers open source`、`openalex cli`、`research knowledge graph orkg`、`academic search engine`、
`openalex`、`semantic scholar`、`arxiv api`、`crossref`、`scientific pdf parsing`、`literature review`。
另有 9 条（`storm wikipedia`、`gpt-researcher`、`deep research agent`、`literature review agent`、`paper search agent`、`scholar qa`、
`asta allenai`、`survey generation llm`、`research assistant arxiv llm`）触发 GitHub 搜索二级限流（403），改为已知仓库名直接查询补齐。

**Web 检索式**（WebSearch，均 2026-09-26）：`Papers with Code shut down 2025 Hugging Face trending papers redirect`；
`OpenAlex API key required 2026 pricing credits free tier announcement`；`Crossref REST API rate limits change 2025 public pool polite pool concurrency`；
`Semantic Scholar API 2026 rate limit API key changes`；`arXiv API changes 2026 rate limit export.arxiv.org new API announcement`；
`Quickwit Datadog acquisition Apache 2.0 relicense Tantivy 2025`；`Meilisearch enterprise edition BUSL license community edition MIT 2025`；
`MinerU license change 2025 AGPL "MinerU Open Source License"`；`OpenAlex "example costs" per request ...`。
**之后会话级 WebSearch 预算（200 次，与并行 agent 共享）耗尽**，其余事实改为 WebFetch 定点读取官方页面或 GitHub API 直查。

**WebFetch 访问站点**（均 2026-09-26）：Crossref 限速公告、OpenAlex 帮助中心定价/示例成本页、OpenAlex 用户组公告、OpenAlex 博客、
Semantic Scholar API 产品页与 License 页、arXiv API 使用条款、MinerU changelog、Marker 仓库页、paperscraper PDF 文档、
Zotero changelog、arXiv 2411.14199 / 2504.08385 摘要页、papers.cool、Qdrant 多租户指南、Vespa streaming 文档、Meilisearch tenant token 文档、
OpenSearch hybrid 与 score-ranker 文档（后者正文未渲染）、OpenSearch Foundation 页、ASReview 模型文档、PwC 数据仓 issue #116、HyperAI 新闻、
HF 模型卡（dots.ocr、Qwen3-Embedding）、三个 OAI-PMH `Identify`（Zenodo、MIT DSpace、White Rose EPrints）。完整 URL 见 §5。

**局限**：未覆盖 Gitee/GitCode 等国内托管平台；GitHub 搜索存在英文关键词偏差；架构结论以 README/文档/目录结构为主，
仅对 findpapers（`query/propagator.py`、`query/builder.py`）、s2_fos（`constants.py`）、cv-arxiv-daily（`daily_arxiv.py` 与 workflow）读到源码级。

### 1.5 与 v1 调研的衔接

v1 调研（2026-07-20）结论"增量订阅是全场最薄弱维度""限速/重试/缓存应为正交中间件""统一 schema=核心强字段+raw dict"
在本轮复核中**全部仍成立**；本轮新增的主要是：①2025–2026 外部 API/政策变化对开源工具的冲击；②MCP/Agent 化的检索接口；
③多用户与个性化推荐相关的开源积木；④VLM 时代的 PDF 解析与许可分层。

---

## 2. 主体内容

### 2.1 2025–2026 外部环境变化（影响开源工具可用性的事实）

| 事件 | 日期 | 事实（摘要） | 对开源生态/本项目的影响 | 来源 |
|---|---|---|---|---|
| Papers with Code 关停 | 2025-07-24 关停；2025-07-25 公告 | Meta 关停 PwC，域名重定向到 Hugging Face "Trending Papers"（HF CEO 在 issue #116 回帖称系 HF 向 Meta 提议重定向）；**核验修正**：最后一次公开数据快照由 HF 组织 `pwc-archive` 托管（papers-with-abstracts、links-between-paper-and-code、evaluation-tables、methods、datasets 等 7 个数据集） | `paperswithcode-client` 失效；cv-arxiv-daily 已移除 PwC 代码链接；"论文↔代码"信号改用 HF Hub，历史链接可取 `pwc-archive` | HyperAI 新闻；PwC 数据仓 issue #116（2025-08-14）；https://huggingface.co/pwc-archive |
| Quickwit 被 Datadog 收购并改许可 | 2025-01-09 公告；2025-01-23 实际改许可 | 宣布将以 Apache-2.0（原 AGPL）发布；**核验补充**：LICENSE 提交 "Relicense to Apache 2.0 (#5645)" 于 2025-01-23，此前 LICENSE.md 为 AGPL | Tantivy 生态（MIT）+ Quickwit（Apache）许可友好 | Quickwit 博客（已直读）；quickwit-oss/quickwit LICENSE 提交史 |
| Meilisearch 双许可 | **核验修正**：2025-08（EE 条款 2025-08-19 入库，官方博客 2025-08-27，自 v1.19） | CE 为 MIT；EE（代码中 `enterprise_edition` 模块：分片、网络/联邦检索、S3 快照等）为 BUSL-1.1，仅非生产用途免许可，生产用需商业许可；Change Date 为发布后 4 年转 MIT | 只用 CE 功能；LICENSE / LICENSE-EE 原文已核 | Meilisearch LICENSE、LICENSE-EE 与提交史；博客 |
| Crossref REST 新限速 | 公告 2025-11-05，生效 2025-12-01 | public：单条 5 rps/并发 1，列表 1 rps/并发 1；polite（带 mailto）：单条 10 rps/并发 3，列表 3 rps/并发 3；Plus/XML/OAI-PMH 不变 | 限速器需按**端点类型**分桶；findpapers 文档仍写"polite ~50 rps"已过时 | Crossref 博客 |
| OpenAlex 强制 API key + 计费 | 公告 2026-01-13；生效 2026-02-13；博客 2026-02-24；帮助页 2026-08-09 更新 | 无 key 仅少量测试额度（公告：100 credits 后返回 409；帮助页现写每日 $0.10）；取消 polite pool 与 email 参数；每 key 每日 $1 免费；singleton 免费、list+filter $0.10/千、search $1/千、semantic $1/千、content 下载 $10/千；年费档 $5k/$10k/≥$20k（每日预算 $20/$100/$200+）；**4.8 亿作品 CC0 快照仍免费**；新增 OA 作品 PDF/TEI（博客称 6,000 万；**核验修正**：Fulltext 帮助页 2026-09-18 版称"5,000 万+，TEI 约 4,300 万"，"PDF 保留原版权，OpenAlex 不授予额外权利"，使用者须逐作品遵守许可）、语义检索 beta、查询至 8KB | v1 openalex adapter 与所有第三方客户端需改；多用户平台应"用户自带 key"或走快照；全文共享须按 `best_oa_location.license` 逐篇判定 | OpenAlex 公告/博客/帮助中心（Pricing、Example costs、Fulltext） |
| OpenAlex 官方 CLI / MCP | CLI 仓库 2026-02-02 建；MCP 2026-09-19 建 | `openalex-official` 批量下载元数据+PDF/TEI；官方 MCP 托管于 `mcp.openalex.org`，OAuth 2.1、按用户 key 与预算执行 | "平台代用户持外部额度"的标准做法 | GitHub（ourresearch） |
| arxiv.py 4.0 破坏性变更 | 4.0.0：2026-05-17（3.0.0：2026-04-12） | 移除 `Search.results`、`Result.download_pdf/download_source`、`arxiv.arxiv` 导入垫片，`max_results=math.inf` 改为 `None`；feedparser→lxml；UA 改为 `arxiv.py/{version}`；3.0.0 已弃 Py3.9、默认 `max_results=100` | 未锁版本的日推项目失效（cv-arxiv-daily 实证：4.0.0 发布后首次运行 2026-05-21 起全部失败） | arxiv.py release notes（4.0.0/3.0.0，已直读）；Actions 日志 |
| arXiv API 限流收紧 | 社区线程 2026-02-26 起；**核验修正**：arXiv 员工 2026-02-27 回帖承认"近期及持续做了调整"，未公布新数值 | 用户反映 3–4 秒间隔仍 429/503，投诉持续至 2026-06-05；官方未更新 TOU 数值（仍为 1 req/3s、单连接） | 维持 1 req/3s 单连接，并准备退避 + 缓存 | arXiv API Google Group 线程（已直读） |
| MinerU 许可切换与 4.0 | 3.1.0（GitHub release 2026-04-17 UTC，即北京时间 04-18）改 MinerU Open Source License；4.0.0（2026-09-16）…4.0.7（2026-09-23） | AGPLv3 → Apache-2.0 + 附加条款：MAU>1 亿或月收入>2,000 万美元需商业许可；**核验补充**：基于 MinerU 向第三方提供在线服务须在界面或公开文档显著标注使用 MinerU，违反即许可自动终止 | 可作为可选抽取器（v2 平台形态须履行标注义务） | MinerU LICENSE.md（已直读）、3.1.0 release notes |
| Marker 2.0 | v2.0.0：2026-07-20 | 代码 Apache-2.0；权重修改版 OpenRAIL-M（<500 万美元免费） | 同上，有条件 | Marker 仓库 |
| Zotero 10 | 10.0：2026-08-17；10.0.4：2026-09-22 | 本地 API 支持写入；全文检索大幅提速；高级检索重做 | 用户个人库双向同步门槛降低（zotero-mcp 已支持 10+ 本地写） | Zotero changelog |
| JabRef 6.0 beta | 2026-09-21（预发布） | 稳定版仍为 5.15（2024-07-10） | — | GitHub releases |
| Kùzu 归档 | 最后发版 v0.11.3（2025-10-10），仓库已归档 | 嵌入式图库停维护 | 不可选型 | GitHub API `archived=true` |
| LangChain open_deep_research 归档 | 最近提交 2026-08-10，现已归档 | — | 不作依赖 | GitHub API |
| S2 社区仓库 s2-folks 归档 | 2025-01-24 | API 社区支持渠道变化（去向 ⚠ 未核验） | — | GitHub API |

### 2.2 v1 已调研 20 项复核（2026-07-20 → 2026-09-26）

★ 为 2026-09-26 实测；v1 列为当时近似值。

| # | 项目 | v1 ★ | 现 ★ | License | 最近提交 / 最新发版 | 2025–26 变化与现状 | v2 级 |
|---|---|---|---|---|---|---|---|
| 1 | [jannisborn/paperscraper](https://github.com/jannisborn/paperscraper) | 530 | 542 | MIT | 2026-09-22 / v1.0.0（2026-06-16） | 1.0 发布；bio/med/chemRxiv 全量下载为本地 JSONL 再检索；arXiv 本地 dump 可走 Kaggle 或 API 后端；PDF 回退=BioC-PMC XML、eLife XML、Wiley/Elsevier TDM token、bioRxiv S3 requester-pays（文档未提影子库）；**Scholar 指标仍经 scholarly** | B（"先 dump 后本地检索"模式）；scholarly 组件 X |
| 2 | [lukasschwab/arxiv.py](https://github.com/lukasschwab/arxiv.py) | ~1.4k | 1,548 | MIT | 2026-07-31 / 4.0.1 | 3.0.0（2026-04-12）默认 `max_results=100`、弃 Py3.9；4.0.0 移除 `Search.results` 等旧 API、UA 自带版本号；`Client`/`Search`/`Result` 三段式不变 | B（v1 已有自研 adapter；若引入须锁版本） |
| 3 | [ferru97/PyPaperBot](https://github.com/ferru97/PyPaperBot) | 630 | 655 | MIT | 2024-12-08 / v1.4.1 | 停更；仍以 SciHub/SciDB 兜底下载 | X |
| 4 | [scholarly-python-package/scholarly](https://github.com/scholarly-python-package/scholarly) | 1,877 | 1,880 | Unlicense | 2026-03-24 / v1.7.11（2023-01-16） | 三年未发版；仍是 paperscraper、mcp-scholarly 等的 Scholar 抓取依赖 | X（作为源） |
| 5 | [danielnsilva/semanticscholar](https://github.com/danielnsilva/semanticscholar) | 474 | 481 | MIT | 2026-07-03 / v0.12.0（2026-03-29） | 持续维护 | B |
| 6 | [J535D165/pyalex](https://github.com/J535D165/pyalex) | 397 | 417 | MIT | 2026-02-23 / v0.21 | 适配强制 key（`pyalex.config.api_key`）；新增 `Works().similar()` 语义检索、`w.pdf/w.tei` 内容下载；README 仍以"credits"表述计费，与官方 USD 口径不一 | B |
| 7 | [sckott/habanero](https://github.com/sckott/habanero) | 250 | 251 | MIT | 2026-09-25 / v2.9.2（2026-06-17） | 活跃 | B |
| 8 | [openreview/openreview-py](https://github.com/openreview/openreview-py) | 249 | 268 | MIT | 2026-09-26 / v2.6.3（2026-09-23） | 官方客户端，高频发版 | R |
| 9 | [pybliometrics-dev/pybliometrics](https://github.com/pybliometrics-dev/pybliometrics) | 495 | 500 | MIT（原文；API 显示 NOASSERTION） | 2026-02-27 / PyPI 4.4.1（2026-01-01） | 无 GitHub release | I（用户自带 Scopus key） |
| 10 | [karpathy/arxiv-sanity-lite](https://github.com/karpathy/arxiv-sanity-lite) | 1,656 | 1,696 | MIT | 2022-02-14 / — | 休眠；tag→TF-IDF+SVM 每 tag 推荐、cron 守护、"无新数据不重算特征" | B |
| 11 | [zotero/translators](https://github.com/zotero/translators) | 1,654 | 1,704 | AGPL（文件级） | 2026-09-02 / — | 活跃 | B（经 translation-server 可 I） |
| 12 | [neuml/paperetl](https://github.com/neuml/paperetl) | 697 | 697 | Apache-2.0 | 2025-12-07 / v2.5.2 | 低频 | B |
| 13 | [jonatasgrosman/findpapers](https://github.com/jonatasgrosman/findpapers) | 382 | 405 | MIT | 2026-08-18 / PyPI 0.6.7（2022-11-09） | **main 分支彻底重写**（见 §2.3.1）：Engine（search/get/snowball/similar/download）、8 库、查询 AST+执行计划；README 警示新版未发布。**核验补充**：search/snowball/similar 的默认富化源含 `web_scraping`，该连接器与下载器用 curl_cffi `impersonate="chrome"` 冒充浏览器 TLS 指纹，源码注释自述用于绕过 Akamai（PubMed/NCBI）、Cloudflare（MDPI）等 WAF | B（查询编译首要参照）；`web_scraping` 富化与下载组件 X |
| 14 | [monk1337/resp](https://github.com/monk1337/resp) | 488 | 491 | Apache-2.0 | 2026-07-07 / v0.1.2（2025-12-24） | 新增 MCP 版（resp_mcp）；Google Scholar 走 SerpAPI，Connected Papers 走 Selenium | B；上述两组件 X |
| 15 | [george-gca/ai_papers_scrapper](https://github.com/george-gca/ai_papers_scrapper) | 53 | 53 | MIT | 2026-03-03 / — | 仅抓会议公开 PDF，按会议/年落盘 | B |
| 16 | [pranftw/openreview_scraper](https://github.com/pranftw/openreview_scraper) | 67 | 69 | 无 | 2025-03-03 / — | 停滞；无 license 不可复用 | B |
| 17 | [paperswithcode/paperswithcode-client](https://github.com/paperswithcode/paperswithcode-client) | 188 | 191 | Apache-2.0 | 2024-05-10 / — | 平台已关停 | X（技术性） |
| 18 | [Mahdisadjadi/arxivscraper](https://github.com/Mahdisadjadi/arxivscraper) | 337 | 339 | MIT | 2026-02-19 / v0.0.6（2026-01-19） | 维护中 | B |
| 19 | [titipata/pubmed_parser](https://github.com/titipata/pubmed_parser) | 734 | 738 | MIT | 2025-07-31 / 0.5 | 低频 | R（PMC OA XML/MEDLINE 解析） |
| 20 | [mattbierbaum/arxiv-public-datasets](https://github.com/mattbierbaum/arxiv-public-datasets) | 479 | 483 | MIT | 2022-07-15 / v0.2.0 | 停滞 | B |

**复核结论**：20 项中 1 项因平台关停失效（PwC client），2 项停更且含盗版兜底/Scholar 抓取（PyPaperBot、scholarly 维持 X），
3 项出现 2026 年破坏性或计费相关变更（arxiv.py 4.0、pyalex 适配强制 key、findpapers 重写），其余稳定。

### 2.3 多源检索与元数据客户端库（v1 之外新增 6 项）

★ 均为 2026-09-26 实测。

| 仓库 | ★ | License | 最近提交 / 发版 | 定位 | 架构要点 | 可借鉴 / 复用 | 合规风险 | 级 |
|---|---|---|---|---|---|---|---|---|
| [ourresearch/openalex-official](https://github.com/ourresearch/openalex-official) | 35 | MIT | 2026-09-19 / v0.3.3（2026-03-18） | **OpenAlex 官方 CLI**（原 openalex-content-downloader） | `openalex download --api-key … --filter … --content pdf,xml`；支持 ID/DOI 列表与 stdin、S3 落盘；`openalex status` 查 key 状态 | 批量元数据 + OA 全文的官方通道；可接 v2 成本器 | PDF 按 $0.01/篇计费；PDF 许可随作品而异，平台共享前须按 license 过滤 | I |
| [ropensci/openalexR](https://github.com/ropensci/openalexR) | 146 | MIT（R 包 LICENSE；API 显示 NOASSERTION） | 2026-09-02 / v3.1.0（2026-07-06） | R 生态 OpenAlex 客户端（rOpenSci） | — | 社科/经济用户 R 工作流的导出对接参考 | 同 OpenAlex 计费 | B |
| [metapub/metapub](https://github.com/metapub/metapub) | 160 | Apache-2.0 | 2026-09-24 / v0.7.5 | NCBI eutils/PubMed 元数据与文本挖掘（官方主仓） | eutils 封装；文章/引文查找 | 生物/心理学 PubMed adapter 可直接依赖 | NCBI 频率要求：无 key >3 req/s 报错、带 key 10 req/s（**核验**：NCBI Insights 官方公告，2018-05-01 生效；NCBI Bookshelf 文档页对自动访问弹 reCAPTCHA，未直读） | R |
| [fabiobatalha/crossrefapi](https://github.com/fabiobatalha/crossrefapi) | 349 | BSD-2-Clause | 2025-07-07 / 1.7.0 | Crossref REST 客户端 | 同步 requests | 与 habanero 对照 | 需自行适配 2025-12 新限速 | B |
| [NLeSC/litstudy](https://github.com/NLeSC/litstudy) | 223 | Apache-2.0 | 2025-05-27 / v1.0.6（2023-10-05） | Jupyter 内文献计量分析 | notebook 工作流 | 文献计量可视化思路 | — | B |
| [unpywall/unpywall](https://github.com/unpywall/unpywall) | 36 | MIT | 2024-02-19 / v0.2 | Unpaywall Python 客户端 | 薄封装 | 停更；直接按 Unpaywall API 自建 | 需 email | B |

#### 2.3.1 深读：findpapers 重写版的查询引擎（MIT，2026-08 main 分支）

- **库覆盖与能力矩阵**：arXiv、Crossref、IEEE Xplore、OpenAlex、PubMed、Scopus、Semantic Scholar、Web of Science 八库；
  文档以"Search / Snowball / Similar / Rate Limit"四列声明每库能力（如 Crossref 不可检索，仅 DOI 查找与**后向**雪球——
  这是 findpapers 的实现取舍，Crossref REST `/works` 本身支持 `query.*` 检索；IEEE 约 200 次/日；arXiv 3 秒间隔）。
  这正是 v1 Capability 声明（D-002）的同构物。
- **查询语言**：`[term]` 方括号词项 + `AND`/`OR`/`AND NOT` + 括号分组 + 字段过滤码
  `ti/abs/key/au/src/aff/tiabs/tiabskey`；无方括号时自动把引号或整串当词项（shorthand）。
- **编译管线**（源码 `findpapers/query/`）：`parser → validator → normalizer → propagator → builders/<db>.py`。
  `FilterPropagator` 实现"**最内层过滤码优先**"的继承规则并标注 `children_match_filter`；
  抽象基类 `QueryBuilder` 要求每源声明 `_SUPPORTED_FILTERS`，实现 `validate_query`/`convert_query`，可选 `expand_query`；
  输出 `QueryExecutionPlan{request_payloads, combination_expression}`——当某库无法原生表达整条布尔式时（如 OpenAlex），
  `expand_query` 把查询展开为**析取范式（DNF）**：OR 拆成多个子请求 `q0,q1,…`，AND 在子句内做笛卡尔积后整体下推，
  `AND NOT` 无法安全分配时保留在同一子句；默认 `combination_expression` 为 `q0 OR q1 …`，连接器按 DOI/URL/标题做**并集去重**。
  **核验修正**：原文"以集合语义（AND=交、OR=并、NOT=差）在本地合并"不符源码（`query/builder.py`、`query/builders/openalex.py`、
  `connectors/openalex.py`）——findpapers 没有实现跨请求的本地交/差运算，v2 若需要须自行设计。
- **执行与合并**：`runners/`（search/get/snowball/similar/download/discovery）+ `utils/parallel.py` 并行；
  去重键=DOI（大小写不敏感）或规范化标题，字段级 merge 保留最富信息；`failed_databases` 与 `skipped_databases` 分开报告。
- **合规警示（核验补充）**：`connectors/web_scraping.py` 与 `runners/download_runner.py` 使用 `curl_cffi` 的
  `impersonate="chrome"`，注释写明目的是让 JA3 指纹"与真实 Chrome 一致"，从而"透明绕过" Akamai/Cloudflare 类 WAF，
  并对每次请求新建会话以规避 bot 评分；`web_scraping` 还是 search/snowball/similar 的**默认**富化源。这触犯 D-014 诚实 UA 与
  "不冒充、不对抗风控"红线：v2 只借鉴查询编译，不得引入该组件，也不得照搬其默认配置。
- **相似检索（`similar`）**：S2 Recommendations（SPECTER 嵌入，显式用 `all-cs` 池——文档实测该池并不限于 CS）>
  PubMed ELink `neighbor_score`（PMRA，MeSH 加权，上限 100）> OpenAlex `related_works`（主题标签重叠，最粗）；
  **只做并集按来源优先级排序，不合成分数**（各源不给可比分数）。
- **文档漂移警示**：其数据库文档仍写"OpenAlex ~10 req/s with email""Crossref polite ~50 req/s"，与 2025-12/2026-02 后官方口径不符
  （核验：`docs/databases.md` 已直读；同页"无 key 约 10 次/天、$0.01 预算"亦与官方"无 key 每日 $0.10"不一致）。

#### 2.3.2 核验补充：学科专门来源的开源平台/客户端与 IR 工具包（5 项，未计入附件快照 TSV）

原文开源样本集中在 CS 与生物医学，物理、心理学/社科预印本、NLP 会议元数据、离线检索评测基线这几块缺少开源参照。
下表 ★/许可/活跃度为核验阶段复测值（2026-09-26 UTC，见 repo-metrics-verify TSV 的 `verify-supplement` 行）；
各平台 API 端点与限速归来源名录专题（[../sources/](../sources/)），此处不重复。

| 仓库 | ★ | License | 最近提交 / 发版 | 定位 | 对 v2 的用途 | 合规/许可注意 | 级 |
|---|---|---|---|---|---|---|---|
| [inspirehep/inspirehep](https://github.com/inspirehep/inspirehep) | 26 | MIT | 2026-09-24 / v1.3.312（2026-09-24） | inspirehep.net 背后的 monorepo（高能物理开放获取数字图书馆） | 物理学一级来源的官方实现参照（元数据模型、记录处理工作流；README 称 Backoffice 为 Django 应用） | 按其公开 API 条款与限速对接（见 sources/natural-sciences.md） | B（平台）/ I（API 源） |
| [andycasey/ads](https://github.com/andycasey/ads) | 191 | MIT | 2026-09-24 / 0.12.7（2024-12-23） | NASA ADS 的 Python 客户端（天文/物理） | 天体物理/物理文献 adapter 的现成客户端 | 需**用户自有** ADS API token（`ads.config.token`），不得跨用户共用 | I（用户自带 token） |
| [CenterForOpenScience/osf.io](https://github.com/CenterForOpenScience/osf.io) | 732 | Apache-2.0 | 2026-09-23 / 26.22.0（2026-09-17） | OSF 平台源码（PsyArXiv 等 OSF Preprints 社区所在平台：psyarxiv.com 301 至 osf.io/preprints/psyarxiv，OSF API v2 `preprint_providers/psyarxiv` 可查） | 心理学/社科预印本源的数据模型与 API v2 行为参照 | 预印本各自许可；按 OSF API 条款限速 | B（平台）/ I（API 源） |
| [acl-org/acl-anthology](https://github.com/acl-org/acl-anthology) | 807 | Apache-2.0（构建代码） | 2026-09-22 / —（PyPI 包 `acl-anthology`） | ACL Anthology 全部论文/作者/venue 元数据 + Python 访问包 | NLP 会议 VenueSpec 的权威元数据底座，免抓站 | 元数据/论文许可 ⚠ 未核验（README 只声明代码 Apache-2.0） | R（Python 包）/ I（数据） |
| [castorini/pyserini](https://github.com/castorini/pyserini) | 2,166 | Apache-2.0 | 2026-09-26 / pyserini-2.4.0（2026-08-27） | 可复现 IR 工具包：稀疏检索经 Anserini（Lucene），稠密检索经 Faiss，自带预建索引与评测脚本 | v2 检索/路由离线评测的 BM25、稠密、混合基线 | 需 Java 21（Anserini 依赖） | B（离线评测） |

### 2.4 学术 MCP 服务器与 Agent Skill（17 项；合规排除项另见 §2.11）

| 仓库 | ★ | License | 最近提交 / 发版 | 定位 | 架构要点 | 可借鉴 / 复用 | 合规风险 | 级 |
|---|---|---|---|---|---|---|---|---|
| [blazickjp/arxiv-mcp-server](https://github.com/blazickjp/arxiv-mcp-server) | 3,175 | Apache-2.0 | 2026-08-26 / v0.7.2（2026-08-24） | 本地 arXiv 文献工作 MCP（已入官方 MCP Registry） | 19 工具；论文存 `~/.arxiv-mcp-server/papers`；下载**先 HTML 后 PDF 回退**转 Markdown（默认 12,000 字符截断）；`get_paper_outline`→`read_paper_section` 渐进读取；作者 LaTeX 源分节读取；`watch_topic`/`check_alerts` 本地记录 last_checked；`citation_graph` 走 S2 且按篇磁盘缓存；`semantic_search` 为 `[pro]` extra | "outline→section + 字符预算"阅读接口；最小主题订阅范式 | arXiv TOU 允许个人本地使用，平台内对他人再分发 e-print 需许可；S2 key 可选（**核验修正**：README 称无 key 可用至共享配额耗尽，key 仅提升可靠性） | I/B |
| [openags/paper-search-mcp](https://github.com/openags/paper-search-mcp) | 2,705 | MIT | 2026-09-22 / PyPI 0.1.4（2026-07-02） | 多源检索/下载 MCP + CLI + Skill | **两层**：统一工具层（`search_papers` 并发检索+去重、`download_with_fallback` 顺序回退）+ 平台 connector 层；约 22 源（arXiv/PubMed/bioRxiv/medRxiv/S2/Crossref/OpenAlex/PMC/CORE/Europe PMC/dblp/OpenAIRE/CiteSeerX/DOAJ/BASE/Zenodo/HAL/SSRN/Unpaywall/IACR 等）；README 附**实测能力矩阵**（Search/Download/Read） | 能力矩阵 + OA-first 回退链（源原生→OpenAIRE/CORE/Europe PMC/PMC→Unpaywall）编排；IEEE/ACM 仅"有 key 才注册工具"的骨架设计 | ❌ 可选 **Sci-Hub**（默认关闭）；❌ Google Scholar 以代理"绕过 bot 检测"；❌ OpenAIRE 403 时升级到"Mozilla UA 的原始 requests"重试（冒充浏览器） | B（上述组件 X） |
| [54yyyu/zotero-mcp](https://github.com/54yyyu/zotero-mcp) | 5,167 | MIT | 2026-09-24 / v0.13.1 | Zotero 库 ↔ LLM 客户端 | 本地模式直读 `zotero.sqlite`；写入走 **Zotero 10+ 本地 API**（一次授权）或 Web API；`[semantic]` extra=ChromaDB + sentence-transformers/OpenAI/Gemini/Ollama 嵌入；`[pdf]` extra=PyMuPDF；README 实测默认 38 工具的 schema **每请求 13,448 tokens**，改 Skill 仅 98 tokens | 每用户 Zotero 同步通道；工具分组 + Skill 惰性加载降 token 成本 | 私人库不得跨用户共享；PyMuPDF 为 AGPL（仅 extra） | I |
| [cookjohn/zotero-mcp](https://github.com/cookjohn/zotero-mcp) | 1,185 | MIT | 2026-09-09 / v1.6.0 | Zotero 插件内嵌 MCP | 运行于 Zotero 进程内 | 插件内置服务形态 | 同作者另有 CNKI/Scholar 自动化 skills（§2.11） | B |
| [ourresearch/openalex-mcp-server](https://github.com/ourresearch/openalex-mcp-server) | 0（2026-09-19 新建） | MIT | 2026-09-21 / — | **OpenAlex 官方 MCP**（托管 `https://mcp.openalex.org/mcp`） | Streamable HTTP；**OAuth 2.1 provider**：每次查询用**用户自己的 key 与预算**，余额低时结果附提示，轮换 key 即断开连接；只读 8 工具（`search_works` 含 `mode:"semantic"`、`get_work`、`resolve_references`（每次核 25 条引用、防伪造）、`list_citations`、`search_entities`、`get_entity`、`group_works`（可按 topic/subfield/field/domain 等分组）、`analyze_works`）；每次返回 **canonical OQL + 可复跑 URL**；响应为 LLM 整形（倒排索引重建摘要、作者折叠前 5、控制在工具结果上限内） | ①用户自有额度的 OAuth 模式；②可复现查询；③引用核验工具 | 按 OpenAlex 计费；依赖托管可用性 | I |
| [huggingface/hf-mcp-server](https://github.com/huggingface/hf-mcp-server) | 299 | MIT | 2026-09-23 / v0.4.23 | HF Hub MCP（模型/数据集/Space/论文） | bouquet 选择工具集；可通过 CSV 代理外部 MCP（示例含 papers Space） | AI 论文热度与"论文↔代码/模型"关联（PwC 替代信号） | HF ToS；仅 AI 领域 | I |
| [genomoncology/biomcp](https://github.com/genomoncology/biomcp) | 643 | MIT | 2026-09-26 / v0.9.0 | 生物医学约 30 源统一 CLI + MCP | 一套命令语法；`search article` 扇出 PubTator3 + Europe PMC 并按 PMID/PMCID/DOI 去重，可加 S2 腿；`article citations/references/recommendations` 链式 pivot | 垂直学科"统一语法 + pivot"的交互；生物/医学源族参考 | 各源条款不同 | B |
| [takashiishida/arxiv-latex-mcp](https://github.com/takashiishida/arxiv-latex-mcp) | 146 | MIT | 2026-09-19 / v0.2.2 | 取 arXiv LaTeX 源供 LLM 精读公式 | 基于 arxiv-to-prompt | 数学/物理重公式论文"源码优先"阅读 | 源文件许可随投稿 | B |
| [zongmin-yu/semantic-scholar-fastmcp-mcp-server](https://github.com/zongmin-yu/semantic-scholar-fastmcp-mcp-server) | 165 | MIT | 2026-03-20 / — | S2 API 的 FastMCP 实现 | 模块化包 | S2 工具面参考 | S2 许可禁止再分发数据 | B |
| [oksure/openalex-research-mcp](https://github.com/oksure/openalex-research-mcp) | 54 | MIT | 2026-06-22 / v0.5.0 | 社区 OpenAlex MCP | `npx … setup` 自动写客户端配置 | — | 描述仍写"240M+ works"（官方已 480M）——文档漂移示例 | B |
| [drAbreu/alex-mcp](https://github.com/drAbreu/alex-mcp) | 56 | MIT | 2025-08-11 / — | 社区 OpenAlex MCP | — | — | 最近提交早于 2026-02 强制 key | B |
| [andybrandt/mcp-simple-pubmed](https://github.com/andybrandt/mcp-simple-pubmed) | 172 | MIT | 2026-03-19 / — | PubMed 检索 MCP | — | — | NCBI 规范 | B |
| [Dianel555/paper-search-mcp-nodejs](https://github.com/Dianel555/paper-search-mcp-nodejs) | 186 | MIT | 2026-09-20 / 0.3.2 | paper-search-mcp 的 Node.js 实现（14 平台，含 WoS/Scopus/ScienceDirect/Springer/Wiley 等 key 型源） | — | — | **核验修正**：含 `SciHubSearcher`（默认关闭、opt-in）与 Google Scholar 解析（可选 ScrapingAnt 代抓服务） | B（上述组件 X） |
| [introfini/ZotSeek](https://github.com/introfini/ZotSeek) | 214 | 无 | 2026-09-24 / v1.22.4 | Zotero 插件：本地语义检索 + 内置 MCP | Transformers.js 端侧推理、数据不出机；支持 Zotero 8/9/10；引用直达 PDF 页 | 端侧嵌入的隐私优先个人库检索 | 无 license 不可复用代码 | B |
| [Galaxy-Dawn/claude-scholar](https://github.com/Galaxy-Dawn/claude-scholar) | 5,635 | MIT | 2026-09-23 / v1.0.0（2026-02-25） | Claude Code/Codex/OpenCode/Kimi 科研 skills+agents 套件（2026-01 新建） | skills/agents/hooks；集成 Zotero MCP、Obsidian 知识库、"证据记录 + 结论门控"研究流程 | Skill 惰性加载；证据门控 | 取决于被调外部源 | B |
| [wp-a/nature-academic-search](https://github.com/wp-a/nature-academic-search) | 276 | MIT | 2026-09-16 / v0.3.1 | 面向中文用户的检索→去重→核验→导出 Skill + MCP | 跨 Crossref/PubMed/arXiv/OpenAlex 等；种子论文追踪参考与引用 | 中文交互的可复现检索流程 | README 推广第三方模型中转（非论文源） | B |
| [Hylouis233/bibverify](https://github.com/Hylouis233/bibverify) | 100 | MIT | 2026-09-11 / v0.3.0（2026-08-13） | BibTeX 存在性/一致性核验（CLI/API/MCP） | 非破坏式核验 | 防"幻觉引用" | — | B |

#### 2.4.1 深读：MCP 化检索接口的三个共性

1. **"工具少而精 + 渐进披露"**：zotero-mcp 实测 38 个工具 schema 每请求占 13,448 tokens，因此提供 Skill（98 tokens）与工具分组；
   arxiv-mcp-server 以 outline→section 与 12,000 字符默认截断控制上下文；OpenAlex 官方 MCP 在列表中截断摘要、折叠作者。
2. **额度与身份下沉到用户**：OpenAlex 官方 MCP 用 OAuth 2.1 把每次调用绑定到用户自己的 API key 与日预算——
   这是 v2"多用户平台不代付/不共享计量型第三方额度"的现成范式。
3. **可复现性**：OpenAlex MCP 每次返回 canonical OQL 与复跑 URL；arxiv-mcp-server 的 BibTeX 取自 arXiv 权威元数据。

### 2.5 LLM 研究助手 / Deep Research（学术向，14 项）

| 仓库 | ★ | License | 最近提交 / 发版 | 定位 | 架构要点 | 可借鉴 / 复用 | 合规风险 | 级 |
|---|---|---|---|---|---|---|---|---|
| [Future-House/paper-qa](https://github.com/Future-House/paper-qa) | 9,251 | Apache-2.0 | 2026-08-12 / v2026.08.12（2025-12 起改 CalVer） | 科学文献高精度 RAG（PaperQA2） | Agentic RAG（agent 迭代改写查询）；本地 PDF 目录→**tantivy 全文索引**，索引按 Settings 哈希复用，manifest CSV 注入 DOI/标题避免 LLM 猜元数据；元数据冗余取自 S2/Crossref/Unpaywall（含引用数、**撤稿检查**、期刊质量）；RCS（LLM 重排 + 上下文摘要）；LiteLLM 多模型 | 证据链 + 行内引用的回答结构；本地全文索引用 tantivy | 需用户自有 PDF；元数据 API 需 key | B |
| [AkariAsai/OpenScholar](https://github.com/AkariAsai/OpenScholar) | 1,605 | Apache-2.0 | 2025-08-13 / — | 检索增强 LM 综合科学文献（8B） | 离线 datastore（arXiv 摘要称 4,500 万篇 OA 论文）+ S2 Paper API + you.com 网页检索；retriever + reranker；ScholarQABench 2,967 个专家查询；摘要称 GPT-4o 引用幻觉 78–90% | "大规模离线 passage 库 + 在线 API 补充"双通道 | S2 key；数据/模型许可见 HF；**核验修正**：已于 2026-02-04 发表于 *Nature*（DOI 10.1038/s41586-025-10072-4，Ai2 博客确认） | B |
| [stanford-oval/storm](https://github.com/stanford-oval/storm) | 31,507 | MIT | 2025-09-30 / v1.1.0（PyPI knowledge-storm 1.1.1，2025-09-29） | 维基式长文报告（STORM/Co-STORM） | dspy 模块化；多视角提问→大纲→成文；Co-STORM 维护动态 mind map；检索模块可插拔（YouRM/Bing/VectorRM/Serper/Brave/SearXNG/DDG/Tavily/Google/AzureAI） | 多视角问题生成用于兴趣扩展与综述卡片 | 依赖通用搜索 API 条款 | B |
| [assafelovic/gpt-researcher](https://github.com/assafelovic/gpt-researcher) | 29,634 | Apache-2.0（GitHub LICENSE；PyPI 元数据标 MIT） | 2026-09-26 / v3.6.1（快照时；同日稍后发布 v3.7.0） | 通用 deep research agent | planner→execution agents→publisher；retrievers 插件目录含 `arxiv`、`openalex`、`pubmed_central`、`semantic_scholar` 与各网页搜索及 `mcp`；Deep Research 树状深挖 | retriever 插件接口；学术源与网页源并列 | 网页搜索 API 条款 | B |
| [allenai/ai2-scholarqa-lib](https://github.com/allenai/ai2-scholarqa-lib) | 282 | Apache-2.0 | 2026-03-19 / PyPI 0.8.13（2026-03-20） | Ai2 Scholar QA 开源实现 | 检索=S2 公共 API `snippet/search`（开放论文全文片段索引）+ 关键词检索补摘要；重排=mxbai-rerank-large-v1 并按论文聚合；生成=**引语抽取→大纲规划 + 引语聚类→分节生成**（默认 Claude Sonnet 3.7）；称语料 1,100 万+ 全文、1 亿+ 摘要 | 可解释综述卡（每结论挂引语） | S2 API 许可 | B |
| [allenai/asta-paper-finder](https://github.com/allenai/asta-paper-finder) | 245 | Apache-2.0 | 2026-03-17 / — | Asta PaperFinder 冻结快照（复现评测用，不再维护） | 查询→**结构化对象**→**执行规划器把分析后的查询路由到若干"找论文意图"工作流之一**→LLM 判定摘要/片段相关性→按内容相关性并结合查询中的附加准则（如"早期工作""有影响力"）排序；fast（约 30s）/diligent（约 3min）；**核验补充**：README 称线上版另用"产品内合法、公共 API 不可用"的数据集与索引，并支持多轮对话，开源快照不含 | **v2 查询路由器最直接参照** | 需 OpenAI/S2/Cohere/Google key | B |
| [allenai/asta-bench](https://github.com/allenai/asta-bench) | 138 | Apache-2.0 | 2026-09-03 / — | Ai2 科研 agent 基准 | — | 检索/综述离线评测 | — | B |
| [bytedance/pasa](https://github.com/bytedance/pasa) | 1,661 | Apache-2.0 | 2025-05-27 / — | 论文检索 agent（ACL 2025） | **Crawler**（生成查询、调用检索、按章节扩展引用、入队）+ **Selector**（逐篇判定）两个 RL 优化的 7B agent；数据集 AutoScholarQuery / RealScholarQuery（50 个真实查询）；README 称 RealScholarQuery 上较 PaSa-GPT-4o recall +30.36%、precision +4.25% | "引用扩展 + 逐篇判定"的高召回范式 | 本地运行依赖 serper.dev（Google 结果转售 API） | B（Serper 组件 X） |
| [LearningCircuit/local-deep-research](https://github.com/LearningCircuit/local-deep-research) | 9,132 | MIT | 2026-09-26 / v1.10.7 | 本地/隐私优先 deep research | LangGraph agent 按查询选引擎（arXiv、PubMed、S2、Wikipedia、SearXNG）；**每用户独立 SQLCipher（AES-256）数据库，密钥由口令派生且不存储，登录即尝试解密**；研究来源可下载进加密个人库并索引；期刊质量系统（OpenAlex/DOAJ + 掠夺性期刊名单）；无遥测 | 多用户私有层强隔离范式；来源质量标签 | SearXNG 上游条款 | B |
| [langchain-ai/open_deep_research](https://github.com/langchain-ai/open_deep_research) | 12,680 | MIT | 2026-08-10 / —（**已归档**） | LangGraph deep research 参考实现 | 可配模型/搜索/MCP | — | 已归档 | B |
| [Alibaba-NLP/DeepResearch](https://github.com/Alibaba-NLP/DeepResearch) | 19,989 | Apache-2.0 | 2026-02-27 / — | 通义 DeepResearch（30.5B 总参/3.3B 激活） | agentic 模型 + WebAgent 系列 | 可自托管的开源 agent 模型选项 | 网页检索条款 | B |
| [AutoSurveys/AutoSurvey](https://github.com/AutoSurveys/AutoSurvey) | 476 | 无 | 2025-02-07 / — | LLM 自动综述 | — | — | 无 license | B |
| [khoj-ai/openpaper](https://github.com/khoj-ai/openpaper) | 482 | AGPL-3.0 | 2026-09-03 / — | 论文阅读工作台 | 上传 PDF→简报与起始问题；回答引文可点回原文；项目级跨论文问答与自定义抽取表；Zotero 导入同步；OA 文献发现 | "答案可溯源到原文位置"的阅读交互 | AGPL | B |
| [ScholarXIV/OpenScholarXIV](https://github.com/ScholarXIV/OpenScholarXIV) | 1,189 | GPL-3.0 | 2026-08-29 / v4.2.0 | Android arXiv 查找/阅读/收藏/AI 摘要 App | 自带 Gemini key（BYOK） | 移动端 arXiv 阅读形态 | GPL | B |

#### 2.5.1 深读：四种"学术检索 agent"范式对照

| 范式 | 代表 | 召回来源 | 判定/排序 | 成本特征 | 对 v2 的可用部分 |
|---|---|---|---|---|---|
| 规划-路由型 | Asta PaperFinder | S2 检索 + 片段 | 意图工作流 + LLM 相关性判定 + 准则加权 | fast 约 30s / diligent 约 3min | 意图分类与路由层 |
| 引用扩展型 | PaSa | Google（Serper）+ 引用扩展 | Selector 逐篇判定（RL 7B） | 高召回、调用量大 | "从这篇扩展"功能的算法骨架 |
| 片段 RAG 综述型 | Ai2 ScholarQA、PaperQA2 | S2 snippet / 本地 tantivy 全文 | 交叉编码器重排 + 引语抽取 + 聚类 | 每问多次 LLM 调用 | 阅读页"证据卡"与综述卡 |
| 离线 datastore 型 | OpenScholar | 4,500 万 OA 论文 passage 库 + API | retriever + reranker + 自反馈 | 离线建库重、在线便宜 | 公共 OA 语料的离线索引思路 |

### 2.6 每日论文推送 / 个性化推荐 / 刷论文 Feed（19 项；arxiv-sanity-lite 见 §2.2）

| 仓库 | ★ | License | 最近提交 / 发版 | 定位 | 架构要点 | 可借鉴 / 复用 | 合规风险 | 级 |
|---|---|---|---|---|---|---|---|---|
| [TideDra/zotero-arxiv-daily](https://github.com/TideDra/zotero-arxiv-daily) | 5,991 | AGPL-3.0 | 2026-09-01 / v1.1.0（2026-04-14） | 按个人 Zotero 库每日推荐新论文并发邮件 | GitHub Actions（默认 22:00 UTC）零成本；源 arXiv/bioRxiv/medRxiv/chemRxiv（chemRxiv 经 Crossref 取）；本地嵌入默认 `jina-embeddings-v5-text-nano` 或 API；**分数=候选与用户 Zotero 全部论文的加权平均相似度，越新加入的文献权重越高**；LLM 生成 TL;DR；`include_path` glob 限定集合 | 冷启动：以"已收藏文献"作兴趣原型 + 时间衰减 | AGPL（借鉴不复用）；邮箱/Zotero key 存 Actions secrets | B |
| [dw-dengwei/daily-arXiv-ai-enhanced](https://github.com/dw-dengwei/daily-arXiv-ai-enhanced) | 3,012 | Modified Apache（附第三方内容免责条款） | 2026-09-08 / — | arXiv 日抓 + AI 摘要 + Pages 展示 | Actions→DeepSeek 摘要（README 称约 0.2 元/天）→静态站；关键词/作者偏好存浏览器本地并可一键导出；SKILL 插件式过滤；可设访问口令 | 本地偏好 + 可导出偏好配置 | README 提示二次分发需内容合规审查 | B |
| [ziwenhahaha/daily-paper-reader](https://github.com/ziwenhahaha/daily-paper-reader) | 928 | MIT | 2026-09-12 / — | arXiv/OpenReview/会议论文推荐 + AI 阅读（Fork 即用，2025-12 新建） | Actions + Pages + Supabase；源 arXiv、OpenReview、bioRxiv/medRxiv/ChemRxiv 与 ICML/ACL/CVPR/OSDI/S&P 等会议库（如 ICML 2026 从 OpenReview 同步 6,555 篇）；**召回=BM25/exact（时间分片 + 递归细分兜底）+ 向量（exact 优先、ANN 低密度回退）→统一候选池（各 lane 保底、池预算随规模动态）→本地 Qwen3-Reranker-0.6B 重排→LLM refine 补分**；每 tag 独立维护 carryover 与 seen_ids；query embedding 按 hash 缓存；远程 embedding 首败即整轮熔断回退本地模型 | **v2 候选生成→重排→精评流水线最完整的开源样本** | 会议 PDF 仅外链官方 OA；LLM API 条款 | B |
| [Vincentqyw/cv-arxiv-daily](https://github.com/Vincentqyw/cv-arxiv-daily) | 1,500 | Apache-2.0 | 2026-09-21（自动提交）/ — | Actions 按关键词拉 arXiv 生成列表 | `arxiv.Search(...).results()`；PwC API 弃用后已跳过代码链接更新 | **反例**：workflow 中 `pip install arxiv` 未锁版本，arxiv.py 4.0 移除 `Search.results` 后 "Run Arxiv Papers Daily"（cron `0 0 */5 * *`，实为每 5 天）**自 2026-05-21 起 29 次运行全部失败**（**核验修正**；最新 2026-09-26 日志：装 arxiv-4.0.1 后 `AttributeError: 'Search' object has no attribute 'results'`）；另一个"Weekly"链接更新 workflow 仍成功并自动提交，仓库表面"活跃" | — | B |
| [AutoLLM/ArxivDigest](https://github.com/AutoLLM/ArxivDigest) | 467 | MIT | 2023-07-13 / — | 按自然语言兴趣描述让 LLM 给摘要打 1–10 分 | gpt-3.5-turbo-16k 打分→HTML 邮件（SendGrid） | "自然语言兴趣 + LLM 评分"冷启动/解释 | 停更 | B |
| [tatsu-lab/gpt_paper_assistant](https://github.com/tatsu-lab/gpt_paper_assistant) | 551 | Apache-2.0 | 2024-03-26 / — | GPT-4 + 关注作者的每日 arXiv 扫描 | arXiv RSS→标题预过滤降本→GPT 主题过滤；关注作者用 S2 author ID；推 Slack/Pages；README 记录 2024-02-07 因 arXiv RSS 格式变更而修复 | "关注作者（ID 化）+ LLM 主题过滤"双通道 | 停更 | B |
| [JoeLeelyf/customize-arxiv-daily](https://github.com/JoeLeelyf/customize-arxiv-daily) | 160 | MIT | 2025-09-24 / — | 定制化每日 arXiv 推荐 | — | — | — | B |
| [OpenRaiser/PaperFlow](https://github.com/OpenRaiser/PaperFlow) | 167 | MIT | 2026-08-22 / —（2026-05 新建） | 闭环个性化推荐 + 阅读 + 报告（CLI/本地 GUI/飞书 bot） | 本地 SQLite；**`user_id` 为身份边界**；反馈语义：推送内选中=正、**首次反馈时同批未选=弱负**、追加回复只增不删、`none`=整批无用、精读=保守正信号；更新 topic_weights 与短/长期漂移状态；可镜像到本地 wiki 图（paper/trajectory/topic 节点）；附 PaperFlow-Bench（反馈语义出处为 `docs/feedback-loop.md`，已直读） | 反馈语义与漂移建模可直接移植 | **核验修正**：画像引导支持 `--scholar-url`，README 明示"scrapes the public page"（抓取公开 Google Scholar 个人主页）→ 该入口 X | B（Scholar 引导组件 X） |
| [gaoxin492/PaperFeeder](https://github.com/gaoxin492/PaperFeeder) | 138 | 无 | 2026-06-02 / — | 论文 + 博客每日分拣 agent（邮件） | — | — | 无 license | B |
| [iai-group/arXivDigest](https://github.com/iai-group/arXivDigest) | 28 | MIT | 2025-12-13 / — | arXiv 推荐"living lab"（斯塔万格大学） | broker 连接真实用户与多个实验推荐系统（系统经 REST API 读用户数据、上传推荐）；前端独立仓库 | **v2 推荐在线评测框架**（多策略并行评估） | — | B |
| [karpathy/arxiv-sanity-preserver](https://github.com/karpathy/arxiv-sanity-preserver) | 5,794 | MIT | 2021-11-27 / — | arxiv-sanity 旧版 | — | 历史参考 | 停更 | B |
| [bojone/papers.cool](https://github.com/bojone/papers.cool)（Cool Papers） | 809 | 无 | 2026-07-06 / — | "沉浸式刷论文"站点的**更新日志/反馈仓库**（站点源码未开源） | 仓库仅含 README、Chrome/Zotero 辅助；站点覆盖 arXiv 多学科分类与 AAAI/ACL/CVPR/ICLR/ICML/NeurIPS 等；**点击 [PDF] 或 [Kimi] 即自动星标**，底栏汇总"至少一瞬间引起兴趣"的论文 | 隐式行为即收藏候选；极简列表流 | 站点闭源 | B |
| [mugar123/papertok](https://github.com/mugar123/papertok) | 27 | MIT | 2026-09-26 / v0.2.0（2026-08-27） | 开源个性化"刷论文"feed（papertok.app） | React + Vite + Firebase + Framer Motion + KaTeX；Cloudflare Worker 做查询缓存、凭证保护与 API 代理；源 arXiv/OpenAlex/PubMed/OpenReview/NIH iCite/HF Hub，**先归一再排序**；信号=显式学科偏好、交互学得亲和、关注（作者/主题/机构/项目）、**有界**时效、**有界**影响力、语义概念、探索、多样性；卡片"诚实标签"（Preprint/Verified，Open access/Open version/Subscription，未知则不显示） | v2 卡片信息架构 + 混合信号排序样板 | 声明不隶属数据源；各 API 条款 | B |
| [Miguel07Alm/arxivtok](https://github.com/Miguel07Alm/arxivtok) | 91 | MIT | 2025-02-07 / — | TikTok 式竖滑 arXiv 浏览 | SolidJS/SolidStart + Tailwind + KaTeX；源 arXiv/medRxiv/bioRxiv/PubMed/HN；无限滚动、收藏 | 竖滑交互原型 | — | B |
| [cookiegg/flopap](https://github.com/cookiegg/flopap) | 7 | 无 | 2026-01-15 / — | "像刷抖音一样刷论文" | — | 概念验证 | 无 license | B |
| [khuynh22/paper-deck](https://github.com/khuynh22/paper-deck) | 15 | MIT | 2026-09-20 / v0.4.0 | 聚合 arXiv/HF/S2 的卡组 + 应用内阅读 | — | — | — | B |
| [a1henu/arxiv-daily-scroll](https://github.com/a1henu/arxiv-daily-scroll) | 26 | GPL-3.0 | 2026-09-26 / — | 分类日更 + DeepSeek 中文要点 | — | — | GPL | B |
| [yzr278892/arxiv-daily-researcher](https://github.com/yzr278892/arxiv-daily-researcher) | 318 | AGPL-3.0 | 2026-09-26 / v4.7 | 每日论文摘要推送 | — | — | AGPL | B |
| [Scriptbash/Wispar](https://github.com/Scriptbash/Wispar) | 214 | GPL-3.0 | 2026-09-21 / v0.10.5+41（2026-06-07） | 跨平台（Flutter/Dart）**期刊追踪** feed App（Android/iOS/桌面） | 用 Crossref/OpenAlex 搜索并**关注期刊**，新文章摘要进主 feed；保存查询入 feed；**EZproxy 集成（Library Proxy URL Database）+ Unpaywall**；可自托管同步后端；本地库导入导出；**可自定义滑动手势**；发送到 Zotero；后台更新与通知 | 期刊 TOC 关注 + 每用户机构代理 + 手势可配置的移动 feed——与 v2 最接近的开源产品形态 | "抓取缺失摘要/图文摘要"涉及出版社页面抓取（⚠ 需逐站 ToS）；GPL | B |

**闭源参照（非仓库，不计数）**：Scholar Inbox（arXiv 2504.08385，2025-04 提交/2025-06 修订）——以用户评分训练个性化模型、
用"科学地图"解冷启动、主动学习迭代请用户评分，并公开 80 万条用户评分数据集。**核验补充**：未见官方平台代码；
数据集由 Autonomous Vision Group 组织发布于 [avg-dev/scholar_inbox_datasets](https://github.com/avg-dev/scholar_inbox_datasets)
（6★，许可 NOASSERTION ⚠ 未核验）：显式赞/踩评分 N=774k、隐式交互（阅读/收藏/分享等）N=556k、摘要句分类 2,538 条——
可作 v2 推荐离线评估的公开基线数据。

#### 2.6.1 深读：开源推送/推荐项目的算法谱系

| 层 | 最简做法 | 进阶做法 | 代表 |
|---|---|---|---|
| 兴趣表示 | 类别/关键词白名单 | 个人库嵌入原型（时间衰减）；自然语言兴趣描述；关注作者 ID | cv-arxiv-daily → zotero-arxiv-daily、ArxivDigest、gpt_paper_assistant |
| 召回 | 分类日列表全量 | 多 lane（BM25/精确/向量/关注）+ 统一候选池保底配额 | daily-paper-reader |
| 排序 | 余弦相似度 | 交叉编码器重排 → LLM 精评（仅 Top-K） | daily-paper-reader、arxiv-at-home（生成式逐点重排） |
| 反馈 | 无 | 选中/未选（强/弱）、精读信号、短长期漂移；隐式点击即星标 | PaperFlow、Cool Papers |
| 探索/多样性 | 无 | 有界时效/影响力、探索位、来源多样性 | papertok |
| 评估 | 无 | living lab 多系统在线评估；离线 Bench | arXivDigest、PaperFlow-Bench |

### 2.7 开源学术搜索引擎、前端与学术知识组织（26 项）

| 仓库 | ★ | License | 最近提交 / 发版 | 定位 | 架构要点 | 可借鉴 / 复用 | 合规风险 | 级 |
|---|---|---|---|---|---|---|---|---|
| [arXiv/arxiv-search](https://github.com/arXiv/arxiv-search) | 160 | MIT | 2026-08-20 / 0.5.6（2020） | arXiv 官方检索 UI 与 API | Flask + Elasticsearch；建索引需 CUL 内网 `/docmeta` | 官方字段/分类检索实现 | — | B |
| [arXiv/arxiv-browse](https://github.com/arXiv/arxiv-browse) | 192 | MIT | 2026-08-24 / 0.3.2.5（2020） | arXiv 摘要页/列表页 Flask 应用 | — | listing（new/cross-list/replace）语义参照 | — | B |
| [ourresearch/openalex-gui](https://github.com/ourresearch/openalex-gui) | 48 | MIT | 2026-09-24 / — | OpenAlex 官方前端 | — | 实体检索/筛选 UI | — | B |
| [ourresearch/openalex-elastic-api](https://github.com/ourresearch/openalex-elastic-api) | 42 | MIT | 2026-09-24 / — | OpenAlex API 中由 Elasticsearch 支撑的端点 | — | 4.8 亿文档规模 ES 过滤/聚合 API | — | B |
| [ourresearch/openalex-guts](https://github.com/ourresearch/openalex-guts) | 157 | MIT | 2026-03-06 / — | OpenAlex 数据计算"内脏" | — | 实体解析/合并管线 | — | B |
| [ourresearch/openalex-walden](https://github.com/ourresearch/openalex-walden) | 22 | MIT | 2026-09-26 / —（2025-05 新建） | OpenAlex 数据管线 | 与 guts 关系 ⚠ 未核验 | — | — | B |
| [ourresearch/oadoi](https://github.com/ourresearch/oadoi) | 398 | MIT | 2026-09-18 / — | Unpaywall 后端 | Python + PL/pgSQL | OA 位置发现（出版商页/仓储）逻辑 | — | B |
| [allenai/s2search](https://github.com/allenai/s2search) | 113 | Apache-2.0 | 2020-10-26 / — | Semantic Scholar 搜索重排器 | 一阶段（如 ES）+ 重排；特征含 kenlm 语言模型（数据约 10GB 压缩/17GB 解压，需 >17GB 内存） | 学术检索 LTR 特征工程 | 停更 | B |
| [allenai/s2-folks](https://github.com/allenai/s2-folks) | 278 | 非标准 | 2025-01-24 / —（**已归档**） | S2 API 用户社区空间 | — | 历史 API 发布说明 | — | B |
| ORKG（GitLab [orkg-backend](https://gitlab.com/TIBHannover/orkg/orkg-backend) / [orkg-frontend](https://gitlab.com/TIBHannover/orkg/orkg-frontend)） | 9 / 17（GitLab） | MIT | 2026-09-25 / — | 开放研究知识图谱（TIB） | 论文"贡献"结构化（属性–值）+ 对比表 | 论文卡片"方法/数据/结果"结构化字段 | — | B |
| [OpenKnowledgeMaps/Headstart](https://github.com/OpenKnowledgeMaps/Headstart) | 222 | MIT | 2026-09-23 / v7（2021） | 知识地图（Open Knowledge Maps） | TS 前端 + R/Python 后端，自动生成主题聚类地图 | 主题聚类可视化 | — | B |
| [LocalCitationNetwork/LocalCitationNetwork.github.io](https://github.com/LocalCitationNetwork/LocalCitationNetwork.github.io) | 148 | GPL-3.0 | 2026-05-08 / — | 本地引文网络 Web 应用 | 数据源 OpenAlex/S2/Crossref/Zotero Cita；给定种子集建局部引文图，推荐缺失的 "Top Cited / Top Citing"；纯前端 | "种子→局部引文图→缺失推荐" | 维护者寻求接手；GPL | B |
| [CitationGecko/gecko-react](https://github.com/CitationGecko/gecko-react) | 167 | 无 | 2023-03-09 / v0.1.0 | Citation Gecko React 版 | — | 同上 | 停更、无 license | B |
| [WDscholia/scholia](https://github.com/WDscholia/scholia) | 257 | GPL-3.0 | 2026-05-12 / v0.3 | 基于 Wikidata 的学术画像 | SPARQL 模板 | 作者/主题/机构画像页 | — | B |
| [colonelwatch/abstracts-search](https://github.com/colonelwatch/abstracts-search) | 105 | Apache-2.0 | 2026-06-19 / — | 2 亿+ OpenAlex 摘要语义检索 | 快照摘要→`stella_en_1.5B_v5` 嵌入→faiss 索引（嵌入与索引以 CC0 发布于 HF）；查询仅返回 OpenAlex ID 再回查；最近同步 2026-03-30；初建约 4×L4 一周，增量可在 RTX 3060 级机器维护 | "CC0 快照离线建全局语义索引 + 在线按 ID 回查" | 回查 OpenAlex 已计费 | B |
| [mrapplexz/arxiv-at-home](https://github.com/mrapplexz/arxiv-at-home) | 53 | Apache-2.0 | 2026-02-09 / v0.2.0 | 自托管学术检索引擎 | Postgres + Qdrant；稠密 + 稀疏（BM25）混合召回；因果 LLM 逐点生成式重排；引用数对数加权；**标题模糊匹配加权（已知条目检索）**；Postgres 行锁"预约"实现多 worker exactly-once 索引；按源增量同步；数据=Kaggle arXiv 元数据快照 | 已知条目检测、引用加权、幂等增量索引 | S2 引用数需 key | B |
| [whiskyechobravo/kerko](https://github.com/whiskyechobravo/kerko) | 381 | GPL-3.0 | 2026-06-29 / — | Zotero 书目库分面检索 Web 组件 | Flask + Whoosh；Zotero 同步；集合/标签→分面；PDF 附件全文 | "集合即分面"的个人库浏览 | GPL | B |
| [openreview/openreview-expertise](https://github.com/openreview/openreview-expertise) | 51 | MIT | 2026-08-31 / v2.3.3 | 论文–审稿人亲和度建模 | SPECTER+MFR（分数级 0.8/0.2 集成）；SPECTER2+SciNCL（相似度级 0.5/0.5 集成）；README 评测：SPECTER2+SciNCL loss 0.21 / easy 0.91 / hard 0.65，TPMS 0.28 / 0.80 / 0.62 | "用户=其论文/收藏集合"与候选论文的亲和度——双向匹配打分层 | — | B |
| [openreview/openreview-matcher](https://github.com/openreview/openreview-matcher) | 23 | **无 license** | 2026-08-26 / v2.0.7 | 带约束的论文–审稿人分配 | MinMax（OR-Tools 最小费用流）、FairFlow、FairIR、Randomized（BvN 采样）、FairSequence（WEF1）、PerturbedMaximization；只存每人 top-K 分数的稀疏矩阵；Flask + Celery | 双向匹配 + 配额/公平约束（如新论文曝光保底、用户每日上限） | 无 license→仅借鉴论文算法 | B |
| [allenai/SPECTER2](https://github.com/allenai/SPECTER2) | 144 | Apache-2.0 | 2025-10-24 / — | 科学文档嵌入 | base 以 23 学科 600 万引用三元组训练；适配器：proximity（论文↔论文）、adhoc_query（短查询）、classification、regression | 论文/查询分适配器编码 | **核验**：HF `allenai/specter2_base` 权重 Apache-2.0 | R |
| [allenai/s2_fos](https://github.com/allenai/s2_fos) | 34 | Apache-2.0 | 2024-01-02 / — | S2 学科分类器 | SciBERT 微调 + fastText 语言识别；**23 类**：Agricultural and Food Sciences、Art、Biology、Business、Chemistry、Computer Science、Economics、Education、Engineering、Environmental Science、Geography、Geology、History、Law、Linguistics、Materials Science、Mathematics、Medicine、Philosophy、Physics、Political Science、Psychology、Sociology | v2 跨学科一级分类的现成标签体系 | **核验修正**：权重与训练数据在 HF 门控发布，适用 AI2 ImpACT License Low Risk（须登录并同意协议）；语言识别用 fastText `lid.176.bin` | R（标签体系）；权重 I（许可评审后） |
| [allenai/S2AND](https://github.com/allenai/S2AND) | 116 | CC-BY-4.0 | 2026-07-01 / v1.1_no_refs（2021） | 作者姓名消歧基准 + 生产模型 | Python + 可选 Rust 加速 | "关注作者"所需的作者实体消解 | 署名 | B |
| [allenai/citeomatic](https://github.com/allenai/citeomatic) | 197 | Apache-2.0 | 2020-01-22 / — | 引文推荐（历史） | — | — | 停更 | B |
| [allenai/s2orc](https://github.com/allenai/s2orc) | 1,088 | 无 | 2024-04-26 / — | S2ORC 语料说明 | — | — | 数据许可另见 S2 | B |
| [asreview/asreview](https://github.com/asreview/asreview) | 1,019 | Apache-2.0 | 2026-08-31 / v3.0.8（2026-06-18） | 系统综述主动学习筛选 | ELAS 预置模型：**u5（默认）=TF-IDF（含 bigram）+ SVM + Maximum 查询 + Balanced**；l2/l3 用 multilingual-e5-large；h3/h4 用 mxbai-embed-large-v1；含模拟工具包 | "少量标注→主动学习"冷启动/筛选 | — | R |
| [vitorfs/parsifal](https://github.com/vitorfs/parsifal) | 520 | MIT | 2026-02-08 / v2.2.1 | 系统综述协作工具 | Django | 综述流程（协议/筛选/抽取） | — | B |

### 2.8 文献管理与插件生态（19 项）

| 仓库 | ★ | License | 最近提交 / 发版 | 定位 | 架构要点 | 可借鉴 / 复用 | 合规风险 | 级 |
|---|---|---|---|---|---|---|---|---|
| [zotero/zotero](https://github.com/zotero/zotero) | 15,400 | AGPL-3.0 | 2026-09-25 / 10.0.4（2026-09-22；10.0 于 2026-08-17） | 事实标准开源文献管理器 | 10.0：**本地 API 写入**、全文检索大幅提速、高级检索支持嵌套条件组；10.0.2 说明单数选择 getter 不再抛错但插件仍应迁移到新的复数 getter | 用户个人库的首选互通对象 | AGPL（不嵌入代码） | I |
| [zotero/translation-server](https://github.com/zotero/translation-server) | 165 | AGPL-3.0 | 2026-07-31 / — | 无客户端运行 Zotero translators 的 Node 服务 | `/web`（URL→元数据）、`/search`（DOI/ISBN/PMID/arXiv ID→元数据）、`/export`、`/import`；Docker 端口 1969；可配 HTTP(S)_PROXY | "任意 URL/标识符→结构化元数据" sidecar | **默认使用标准 Chrome UA**（README 建议部署时自定义）→与 D-014 诚实 UA 冲突，必须改；AGPL 独立进程；仅用户触发 + 限速 | I（有条件） |
| [retorquere/zotero-better-bibtex](https://github.com/retorquere/zotero-better-bibtex) | 7,157 | MIT | 2026-09-16 / v9.0.64 | Zotero BibTeX/BibLaTeX 与稳定 citekey | — | citekey 规则、LaTeX 导出 | — | B |
| [windingwind/zotero-pdf-translate](https://github.com/windingwind/zotero-pdf-translate) | 11,919 | AGPL-3.0 | 2026-09-21 / v2.4.7 | 阅读时翻译（20+ 服务） | Zotero 插件 | 中文用户阅读辅助需求 | AGPL | B |
| [windingwind/zotero-better-notes](https://github.com/windingwind/zotero-better-notes) | 8,260 | AGPL-3.0 | 2026-08-24 / v3.3.3 | 笔记管理 | — | 笔记↔论文双链 | AGPL | B |
| [windingwind/zotero-plugin-template](https://github.com/windingwind/zotero-plugin-template) | 846 | AGPL-3.0 | 2025-12-16 / v3.1.0 | Zotero 7+ 插件模板 | — | 若 v2 出 Zotero 插件的起点 | 模板 AGPL | B |
| [MuiseDestiny/zotero-gpt](https://github.com/MuiseDestiny/zotero-gpt) | 7,436 | AGPL-3.0 | 2026-04-20 / 3.1.4 | Zotero 内 LLM 助手 | — | — | AGPL | B |
| [yilewang/llm-for-zotero](https://github.com/yilewang/llm-for-zotero) | 3,155 | AGPL-3.0 | 2026-09-20 / v3.9.9（2026-01 新建） | Zotero 研究 agent 系统 | — | — | AGPL | B |
| [papersgpt/papersgpt-for-zotero](https://github.com/papersgpt/papersgpt-for-zotero) | 2,654 | AGPL-3.0 | 2026-09-21 / v1.6.0 | Zotero AI + MCP 插件 | — | — | AGPL | B |
| [urschrei/pyzotero](https://github.com/urschrei/pyzotero) | 1,421 | Blue Oak Model License 1.0.0 | 2026-09-26 / v1.15.2 | Zotero Web API Python 客户端 | — | v2 每用户 Zotero 同步直接依赖 | 用户 key 私存 | R |
| [JabRef/jabref](https://github.com/JabRef/jabref) | 4,766 | MIT | 2026-09-26 / v6.0-beta.1（预发布 2026-09-21；稳定 v5.15, 2024-07-10） | BibTeX/BibLaTeX 桌面管理（Java） | — | 期刊缩写库 abbrv.jabref.org（CC0，被 local-deep-research 使用） | — | B |
| [papis/papis](https://github.com/papis/papis) | 1,781 | GPL-3.0 | 2026-09-19 / v0.16.1 | 命令行文献管理 | 插件化；`papis add --from doi`；BibTeX 导入导出；Vim/Emacs 集成 | CLI 个人库形态（贴近 v1 CLI 用户） | GPL | B |
| [Future-Scholars/paperlib](https://github.com/Future-Scholars/paperlib) | 2,295 | GPL-3.0 | 2025-11-08 / electron 3.1.12（2025-09-28） | 开源论文管理（Electron/Vue） | 多个**元数据刮取器**（为无 DOI 的会议论文定制，可自写）；RSS 订阅新论文；扩展系统（含自然语言语义检索） | 会议论文元数据补全的 scraper 链 | 刮取须遵站点 ToS；GPL | B |
| [vict0rsch/PaperMemory](https://github.com/vict0rsch/PaperMemory) | 578 | MIT | 2026-04-20 / 1.0.3（2025-11-15） | 浏览器扩展式自动文献记录 | 自动识别所读论文（arXiv/OpenReview 等），匹配**正式发表版本**与代码仓库 | 被动记录阅读；预印本→正式版匹配 | 扩展在用户端运行 | B |
| [binary-husky/gpt_academic](https://github.com/binary-husky/gpt_academic) | 71,385 | GPL-3.0 | 2026-01-25 / version3.91（2024-12-19） | 中文学术 LLM 交互工具箱 | 函数插件化（阅读/润色/翻译等） | 中文科研需求面 | **核验修正**：含 Sci-Hub 数据源（`crazy_functions/review_fns/data_sources/scihub_source.py`，内置 20 个镜像）与以 Chrome UA + 代理抓取 Google Scholar 的插件（`Google_Scholar_Assistant_Legacy.py`）；GPL | B（上述组件 X） |
| [PDFMathTranslate/PDFMathTranslate](https://github.com/PDFMathTranslate/PDFMathTranslate) | 37,201 | AGPL-3.0 | 2026-09-26 / v1.9.11（2025-07-11） | 保排版 PDF 双语翻译（EMNLP 2025 Demo） | — | 阅读辅助 | AGPL；译文再分发涉版权 | B |
| [funstory-ai/BabelDOC](https://github.com/funstory-ai/BabelDOC) | 9,610 | AGPL-3.0 | 2026-08-05 / v0.6.4 | 文档翻译引擎 | — | — | AGPL | B |
| [kaixindelele/ChatPaper](https://github.com/kaixindelele/ChatPaper) | 19,872 | **CC BY-NC-ND 4.0** | 2025-11-19 / — | ChatGPT 论文总结/翻译/润色/审稿 | — | — | 非商用 + 禁演绎 | B（代码不可用） |
| [larsgw/citation.js](https://github.com/larsgw/citation.js) | 241 | MIT | 2026-09-18 / v0.3.4（2018） | BibTeX/Wikidata/CSL-JSON 格式互转 | JS | 前端引用导出 | — | R |

### 2.9 PDF 解析与全文结构化（23 项）

| 仓库 | ★ | 代码 License / 权重条款 | 最近提交 / 发版 | 定位 | 架构要点 | 可借鉴 / 复用 | 合规风险 | 级 |
|---|---|---|---|---|---|---|---|---|
| [grobidOrg/grobid](https://github.com/grobidOrg/grobid)（原 kermitt2） | 5,143 | Apache-2.0 | 2026-09-22 / 0.9.1（2026-08-04） | 学术 PDF→TEI 结构化事实标准 | Java（OpenJDK 21）+ 可选 DeLFT 深度模型（经 JEP；**默认仅 CRF**）；68 类标签；头部/参考文献/引文上下文/全文/坐标；参考文献 F1 约 .87（PMC 1,943 篇）/约 .90（bioRxiv 2,000 篇，DL 模型）；经 biblio-glutton 或 Crossref 合并解析 DOI；**可识别版权方与 CC 许可**；生产用户含 Semantic Scholar、ResearchGate、HAL、scite、IA Scholar 等 | v1 D-033 已定"GROBID 可选增强"；许可识别可喂"能否平台共享"判定 | 仅处理用户有权获取的 PDF | I |
| [grobidOrg/grobid-client-python](https://github.com/grobidOrg/grobid-client-python) | 416 | Apache-2.0 | 2026-08-22 / v0.2.0 | GROBID 批处理客户端 | 并发调服务 | 可直接依赖 | — | R |
| [kermitt2/biblio-glutton](https://github.com/kermitt2/biblio-glutton) | 152 | Apache-2.0（README 声明；API 未识别） | 2026-09-22 / 0.2（2022） | 书目匹配/元数据查找服务 | 原始参考串或关键字段→消歧对象 + DOI；DOI/PMID/PMC/ISTEX 映射；以 OpenAlex 数据集做 OA 解析 | 本地托管数据后的"零 API 调用解析" | 需本地大体量数据 | I |
| [facebookresearch/nougat](https://github.com/facebookresearch/nougat) | 10,079 | MIT / 权重 CC-BY-NC | 2025-02-21 / 0.1.0-base（2023） | 学术 PDF→Markdown（含公式） | — | — | 权重非商用 + 停更 | X |
| [datalab-to/marker](https://github.com/datalab-to/marker) | 39,983 | Apache-2.0 / 权重=修改版 AI Pubs OpenRAIL-M（研究、个人、融资或营收 <500 万美元初创免费） | 2026-09-13 / v2.0.0（2026-07-20） | PDF→Markdown/JSON/HTML/chunks | 基于 Surya VLM；README 自报 olmOCR-bench：balanced 76.0% @2.9 页/秒、fast 66.6% @7.4 页/秒（同表 MinerU pipeline 72.7% @0.54、Docling 50.3% @2.1；吞吐为单台 B200 的并发页/秒） | 可选抽取器（速度/质量双档） | 权重商用门槛 | I（有条件） |
| [datalab-to/surya](https://github.com/datalab-to/surya) | 21,418 | Apache-2.0 / 权重同上（<500 万美元） | 2026-09-11 / v0.22.1 | OCR/版面/阅读顺序/表格（90+ 语言） | — | — | 同上 | I（有条件） |
| [datalab-to/chandra](https://github.com/datalab-to/chandra) | 12,327 | Apache-2.0 / 权重=修改版 OpenRAIL-M（<200 万美元，**不得与其 API 竞争**） | 2026-06-26 / v0.2.0（2026-03-18） | 复杂表格/表单/手写 OCR | olmOCR README 所列 Chandra 0.1.0 为 83.1±0.9；**核验补充**：Chandra 2（2026-03）README 自报 85.8±0.8；README 称"商用自托管需许可" | — | 竞争条款对"平台"更严 | I（有条件） |
| [opendatalab/MinerU](https://github.com/opendatalab/MinerU) | 80,671 | MinerU Open Source License（Apache-2.0 + 附加条款：MAU>1 亿或月收入>2,000 万美元需商业许可；**在线服务须显著标注使用 MinerU，违者许可自动终止**（核验补充）；3.1.0 即 2026-04-18 由 AGPLv3 改换） | 2026-09-23 / 4.0.7 | PDF/Office→LLM 友好 Markdown/JSON | 4.0：解析 + 本地文档库 + 服务工具一体；小模型 ONNX/Torch，VLM 走 llama.cpp/vLLM/LMDeploy；MinerU2.5（1.2B VLM，2025-09-19） | 可选抽取器（中文文档强） | 阈值条款 | I |
| [docling-project/docling](https://github.com/docling-project/docling) | 67,985 | MIT（模型各自许可） | 2026-09-25 / v2.130.0 | 多格式文档解析（LF AI & Data 项目） | PDF/DOCX/PPTX/XLSX/HTML/EPUB/LaTeX/图像等→Markdown/HTML/DocTags/无损 JSON；支持 GraniteDocling（258M）等 VLM；自带 MCP server | 许可最干净的通用解析基线 | — | R |
| [allenai/olmocr](https://github.com/allenai/olmocr) | 19,663 | Apache-2.0 | 2026-03-25 / v0.4.27 | PDF 线性化（训练数据级 OCR） | olmOCR-2-7B-1025-FP8（2025-10-21，合成数据 + RL）；vLLM；**olmOCR-Bench**（1,400 文档、7,000+ 用例） | 基准可复用于 v2 抽取器选型 | 需 GPU | I |
| [studio-dots-ai/dots.ocr](https://github.com/studio-dots-ai/dots.ocr)（原 rednote-hilab） | 9,153 | MIT（HF 模型卡亦 MIT） | 2026-03-24 / — | 小红书 hi lab 多语种版面解析 VLM（1.7B LLM 基座，约 3B 参数） | 2025-07-30 发布；2026-03-19 dots.ocr-1.5 更名 dots.mocr；GitHub/HF 均已重定向到新组织 | 多语种（含中文）解析备选 | — | I |
| [deepseek-ai/DeepSeek-OCR](https://github.com/deepseek-ai/DeepSeek-OCR) | 23,911 | MIT | 2026-01-27 / — | "上下文光学压缩" OCR | vLLM 上游支持（2025-10-23）；README 称 A100-40G 上 PDF 并发约 2,500 tokens/s | — | — | I |
| [PaddlePaddle/PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) | 90,243 | Apache-2.0 | 2026-09-16 / v3.7.0 | OCR 全家桶（含 PaddleOCR-VL） | — | 中文 OCR 强项 | — | I |
| [bytedance/Dolphin](https://github.com/bytedance/Dolphin) | 9,053 | **Qwen RESEARCH LICENSE**（仓库 LICENSE 文件；**核验补充**：README 徽章仍写 MIT，HF `ByteDance/Dolphin-v2` 未标 license，口径冲突时按 LICENSE 从严） | 2026-03-25 / — | 文档图像解析（ACL 2025）；Dolphin-v2（2025-12-12，3B）为现行版本 | — | — | 研究许可、非商用 | X |
| [Yuliang-Liu/MonkeyOCR](https://github.com/Yuliang-Liu/MonkeyOCR) | 6,652 | Apache-2.0（代码）/ **核验修正**：v1 权重仅限学术研究与非商用评估，商用部署、SaaS、再分发需书面商业许可 | 2026-07-20 / — | 轻量 LMM 文档解析 | — | — | 权重非商用 | B（权重 X） |
| [Unstructured-IO/unstructured](https://github.com/Unstructured-IO/unstructured) | 15,501 | Apache-2.0 | 2026-09-25 / 0.27.8 | 通用文档 ETL | — | 非学术格式兜底 | — | B |
| [pymupdf/pymupdf4llm](https://github.com/pymupdf/pymupdf4llm) | 2,216 | AGPL-3.0 | 2026-09-09 / v0.3.4 | PyMuPDF 的 LLM 友好输出 | — | — | AGPL | B |
| [allenai/papermage](https://github.com/allenai/papermage) | 803 | Apache-2.0 | 2024-11-08 / v0.18.0 | 科学论文 NLP/CV 统一表示库 | — | — | 停更 | B |
| [allenai/science-parse](https://github.com/allenai/science-parse) | 706 | Apache-2.0 | 2019-10-07 / v2.0.3 | 旧版科学 PDF 解析 | — | — | 停更 | X |
| [allenai/pdffigures2](https://github.com/allenai/pdffigures2) | 759 | Apache-2.0 | 2023-11-27 / — | 图表/标题抽取（Scala/Java） | — | daily-paper-reader 已于 2026-05-30 因 Java 依赖移除 | 停更 | B |
| [CeON/CERMINE](https://github.com/CeON/CERMINE) | 512 | AGPL-3.0 | 2018-02-04 / 1.13（2017） | 旧版元数据抽取 | — | — | 停更 | X |
| [inukshuk/anystyle](https://github.com/inukshuk/anystyle) | 1,292 | BSD-2-Clause | 2025-05-11 / — | 参考文献串解析（Ruby） | — | 参考文献解析备选 | — | B |
| [allenai/s2orc-doc2json](https://github.com/allenai/s2orc-doc2json) | 477 | Apache-2.0 | 2023-08-22 / — | PDF/TeX/JATS→JSON | 基于 GROBID | JATS→JSON 路径 | 停更 | B |

#### 2.9.1 深读：olmOCR-Bench 快照（引自 olmOCR README，Ai2 自报）

| 系统 | Overall | 备注 |
|---|---|---|
| Chandra OCR 0.1.0* | 83.1 ± 0.9 | 权重有竞争条款 |
| Infinity-Parser 7B* | 82.5 | — |
| olmOCR v0.4.0 | 82.4 ± 1.1 | Apache-2.0 |
| PaddleOCR-VL* | 80.0 ± 1.0 | Apache-2.0 |
| Marker 1.10.1 | 76.1 ± 1.1 | 权重 <500 万美元 |
| DeepSeek-OCR | 75.7 ± 1.0 | MIT |
| MinerU 2.5.4* | 75.2 ± 1.1 | 阈值条款 |
| Mistral OCR API | 72.0 ± 1.1 | 闭源 API |
| Nanonets-OCR2-3B | 69.5 ± 1.1 | — |

**注意**：Marker README 对同一基准给出不同口径（Marker balanced 76.0%，MinerU pipeline 72.7%，Docling 50.3%），
各方自报不可直接横比；v2 选型须在自有样本（含经济/金融长表格、数学公式、中文论文）上复测。

### 2.10 检索与存储基础设施（45 项）

#### 2.10.1 全文 / 混合检索引擎（10）

| 仓库 | ★ | License | 最近提交 / 发版 | 定位 | 架构要点 | 可借鉴 / 复用 | 合规/许可风险 | 级 |
|---|---|---|---|---|---|---|---|---|
| [meilisearch/meilisearch](https://github.com/meilisearch/meilisearch) | 59,413 | MIT（CE）+ BUSL-1.1（EE：分片、S3 流式快照等） | 2026-09-24 / v1.54.0 | 开发者友好搜索引擎（Rust） | 全文 + 语义 + **混合检索**；容错拼写；过滤/分面；地理；**tenant token**（由 API key 派生的 JWT，内嵌过滤规则，**只约束 search 端点**，不约束索引/设置/密钥管理） | 平台模式公共论文索引首选之一（单机 CE 足够） | 只用 CE 功能 | I |
| [meilisearch/charabia](https://github.com/meilisearch/charabia) | 360 | MIT | 2026-08-13 / v0.10.0（2026-08-13；核验修正，原记无发版） | Meilisearch 分词库 | 中文 jieba-rs；日韩 lindera；泰语词典 | 中文查询分词 | — | R |
| [typesense/typesense](https://github.com/typesense/typesense) | 26,597 | GPL-3.0 | 2026-09-24 / v30.2 | 容错搜索 + 向量/混合（C++） | 内置嵌入模型（S-BERT/E5 等）或外部 API；**scoped API keys** 限定可访问记录；Raft 集群；内置对话式 RAG | 多租户检索 | GPL（独立服务可接受） | I |
| [quickwit-oss/tantivy](https://github.com/quickwit-oss/tantivy) | 16,144 | MIT | 2026-09-23 / 0.26.1 | Rust 版 Lucene 式全文库 | BM25、短语、增量索引、mmap、分面、快速字段；启动 <10ms；中文需第三方 tantivy-jieba/cang-jie；自报约为 Lucene 2 倍速 | 嵌入式全文索引（PaperQA2、ParadeDB、Quickwit 的底座） | — | R |
| [quickwit-oss/tantivy-py](https://github.com/quickwit-oss/tantivy-py) | 427 | MIT | 2026-09-23 / 0.26.2 | Tantivy Python 绑定 | — | v2 Python 内嵌全文（每用户私有索引） | — | R |
| [quickwit-oss/quickwit](https://github.com/quickwit-oss/quickwit) | 11,678 | Apache-2.0（收购后由 AGPL 改换） | 2026-09-24 / v0.9.1 | 面向可观测性的云原生搜索 | 基于 Tantivy + 对象存储 | 行为/事件日志检索 | 产品重心为日志 | B |
| [vespa-engine/vespa](https://github.com/vespa-engine/vespa) | 7,110 | Apache-2.0 | 2026-09-26 / v8.753.16 | 大规模搜索/推荐平台 | 多阶段排序、张量；**streaming 模式**：文档 ID 带 `g=userid` 分组，查询以 `streaming.groupname` 只扫该用户子集，内存约 45 字节/文档，可在单节点放数十亿文档；最近邻为**精确**计算（streaming 不支持 HNSW） | 同一引擎承载"公共索引（indexed）+ 个人私有库（streaming）" | 运维复杂 | I（规模化阶段） |
| [opensearch-project/OpenSearch](https://github.com/opensearch-project/OpenSearch) | 13,776 | Apache-2.0 | 2026-09-25 / 3.8.0 | 分布式搜索（ES 分叉） | hybrid 查询 + 搜索管道的 normalization / score-ranker 处理器（文档目录可见；RRF 版本细节 ⚠ 未核验）；Foundation 提供基础设施、技术治理归项目 | 平台规模化全文 + 向量 | — | I |
| [elastic/elasticsearch](https://github.com/elastic/elasticsearch) | 77,998 | AGPLv3 / SSPL / ELv2 三选一（默认；**核验补充**：`x-pack` 目录代码仅 ELv2） | 2026-09-26 / v9.5.4 | 事实标准搜索引擎 | arXiv 检索与 OpenAlex API 均基于 ES | 生态最成熟 | 许可需法务评估 | B |
| [paradedb/paradedb](https://github.com/paradedb/paradedb) | 9,308 | AGPL-3.0（Community；Enterprise 另议） | 2026-09-26 / v0.25.10 | Postgres 内全文/向量/聚合（pg_search） | Tantivy 驱动 BM25、混合、分面、join | 单库（Postgres）内 BM25 + 向量 | AGPL 扩展 | I（需法务） |

#### 2.10.2 向量数据库 / 嵌入式检索（6）

| 仓库 | ★ | License | 最近提交 / 发版 | 定位 | 架构要点 | 可借鉴 / 复用 | 风险 | 级 |
|---|---|---|---|---|---|---|---|---|
| [qdrant/qdrant](https://github.com/qdrant/qdrant) | 34,834 | Apache-2.0 | 2026-09-03 / v1.19.1 | 向量数据库 | **多租户**：单集合 + payload `group_id` 建 keyword 索引并设 `is_tenant: true`（同租户向量共址顺序读，v1.11.0 起）；多小租户时 `m: 0` + `payload_m: 16` 建每租户 HNSW；v1.16.0+ **分层多租户**：大租户（约 2 万点）经 `replicate_points` 提升到独立分片；稀疏 + 稠密混合 | 每用户私有向量层（收藏/笔记/私有全文 chunk） | — | R |
| [lancedb/lancedb](https://github.com/lancedb/lancedb) | 11,535 | Apache-2.0 | 2026-09-25 / v0.39.0 | 嵌入式多模态检索库 | 基于 Lance 列式格式；向量 + 全文 + SQL | 本地/单用户模式嵌入式向量存储 | — | R |
| [lance-format/lance](https://github.com/lance-format/lance)（原 lancedb/lance） | 7,116 | Apache-2.0 | 2026-09-26 / v12.0.0 | Lance 列式格式 | 随机访问快、版本化 | — | — | B |
| [milvus-io/milvus](https://github.com/milvus-io/milvus) | 46,255 | Apache-2.0 | 2026-09-26 / v3.0.2 | 分布式向量库 | — | 超大规模才需要 | 运维重 | B |
| [weaviate/weaviate](https://github.com/weaviate/weaviate) | 16,850 | BSD-3 + Weaviate License（`wl/` 目录功能需 license key） | 2026-09-24 / v1.39.7 | 向量库 | — | — | 开放核心 | B |
| [chroma-core/chroma](https://github.com/chroma-core/chroma) | 29,386 | Apache-2.0 | 2026-09-24 / 1.5.9 | AI 检索基础设施 | zotero-mcp semantic extra 所用 | 原型期嵌入式 | — | B |

#### 2.10.3 Postgres 向量扩展（3）与嵌入式分析（3）

| 仓库 | ★ | License | 最近提交 / 发版 | 定位 | 架构要点 | 可借鉴 / 复用 | 风险 | 级 |
|---|---|---|---|---|---|---|---|---|
| [pgvector/pgvector](https://github.com/pgvector/pgvector) | 23,161 | PostgreSQL License | 2026-09-22 / — | Postgres 向量检索 | HNSW/IVFFlat；vector、halfvec（≤4,000 维）、sparsevec（≤1,000 非零）、binary；**0.8.0（2024-10-30）起迭代索引扫描**（strict/relaxed；最新 tag v0.8.6，无 GitHub release），缓解"近似索引先扫后过滤导致结果不足"；按租户 list 分区或部分索引；与 Postgres FTS 组合混合检索 | 平台模式首选（与业务库同事务） | — | R |
| [timescale/pgvectorscale](https://github.com/timescale/pgvectorscale) | 3,135 | PostgreSQL License | 2026-09-07 / 0.9.1 | pgvector 增强（Rust/PGRX） | StreamingDiskANN、SBQ 压缩、**label 过滤向量检索**（Filtered DiskANN）；另支持任意 WHERE 的流式后过滤；自报 5,000 万×768 维对比 Pinecone 的基准 | 学科/来源等 label 过滤下的大规模 ANN | 基准为厂商自报 | R |
| [supervc-stack/VectorChord](https://github.com/supervc-stack/VectorChord)（原 tensorchord） | 1,802 | AGPLv3 / ELv2 双许可 | 2026-04-23 / 1.1.1 | Postgres 向量扩展（pgvecto.rs 后继） | — | — | 许可限制 | B |
| [duckdb/duckdb-vss](https://github.com/duckdb/duckdb-vss) | 267 | MIT | 2026-09-25 / — | DuckDB HNSW 扩展（实验性，基于 usearch） | 索引须整体驻留内存；持久化时每次 checkpoint 全量序列化；删除仅标记需 `PRAGMA hnsw_compact_index`；仅 FLOAT；支持前过滤 | 离线分析/评测 | 非生产持久化 | B |
| [asg017/sqlite-vec](https://github.com/asg017/sqlite-vec) | 8,137 | Apache-2.0 / MIT 双许可 | 2026-05-18 / v0.1.9 | SQLite 向量扩展（Mozilla Builders 主赞助；**pre-v1**） | `vec0` 虚表；float/int8/binary；metadata/auxiliary/partition key 列；纯 C 零依赖、可 WASM | **v1 SQLite + FTS5（D-034）的自然延伸**：本地模式加向量 | pre-v1 破坏性变更（须锁版本） | R |
| [cwida/duckpgq-extension](https://github.com/cwida/duckpgq-extension) | 499 | MIT | 2026-09-17 / — | DuckDB SQL/PGQ 图查询与图算法 | — | 离线引文图分析 | 社区扩展 | B |

#### 2.10.4 ANN 图索引库（4）、图数据库（5）、嵌入/重排服务（4）

| 仓库 | ★ | License | 最近提交 / 发版 | 定位 | 要点 | 可借鉴 / 复用 | 风险 | 级 |
|---|---|---|---|---|---|---|---|---|
| [facebookresearch/faiss](https://github.com/facebookresearch/faiss) | 40,985 | MIT | 2026-09-25 / v1.15.1 | 稠密向量检索/聚类库 | IVF/PQ/HNSW 等 | 离线大规模索引（abstracts-search 所用） | — | R |
| [nmslib/hnswlib](https://github.com/nmslib/hnswlib) | 5,334 | Apache-2.0 | 2026-09-14 / v0.9.0 | HNSW 头文件库 | 分层可导航小世界图 | 轻量内存 ANN | — | R |
| [microsoft/DiskANN](https://github.com/microsoft/DiskANN) | 1,936 | MIT | 2026-09-26 / v0.59.0 | 磁盘友好图索引（Vamana）+ 过滤检索 | — | 大于内存规模的图索引原理 | — | B |
| [unum-cloud/USearch](https://github.com/unum-cloud/USearch) | 4,320 | Apache-2.0 | 2026-08-31 / v2.26.2 | 多语言 ANN/聚类引擎 | DuckDB VSS 底层 | — | — | B |
| [apache/age](https://github.com/apache/age) | 4,852 | Apache-2.0 | 2026-09-18 / PG18/v1.8.0-rc0（2026-07-09） | Postgres 图扩展（openCypher） | — | 引文/作者/主题图与业务库同库 | — | I |
| [neo4j/neo4j](https://github.com/neo4j/neo4j) | 17,256 | GPL-3.0（社区版） | 2026-09-14 / — | 图数据库 | — | — | 企业功能商业许可 | B |
| [kuzudb/kuzu](https://github.com/kuzudb/kuzu) | 4,025 | MIT | 2025-10-10 / v0.11.3（**已归档**） | 嵌入式属性图库 | — | — | 已停止维护 | X |
| [FalkorDB/FalkorDB](https://github.com/FalkorDB/FalkorDB) | 6,316 | SSPL | 2026-09-24 / v4.20.7 | GraphBLAS 图库 | — | — | SSPL | X |
| [memgraph/memgraph](https://github.com/memgraph/memgraph) | 4,581 | BSL-1.1 + Memgraph Enterprise License | 2026-09-25 / v3.13.1 | 内存图库 | — | — | 非 OSI 许可 | X |
| [huggingface/text-embeddings-inference](https://github.com/huggingface/text-embeddings-inference) | 5,063 | Apache-2.0 | 2026-09-23 / v1.9.4 | 嵌入/重排模型推理服务 | — | 嵌入与重排服务化 | — | R |
| [huggingface/sentence-transformers](https://github.com/huggingface/sentence-transformers)（原 UKPLab） | 19,123 | Apache-2.0 | 2026-09-21 / v6.1.0 | 嵌入/检索/重排框架 | — | — | — | R |
| [FlagOpen/FlagEmbedding](https://github.com/FlagOpen/FlagEmbedding) | 12,196 | MIT | 2026-08-24 / v1.4.2 | BGE 系列嵌入/重排 | — | 中英双语嵌入候选 | 模型许可逐个核 | R |
| [QwenLM/Qwen3-Embedding](https://github.com/QwenLM/Qwen3-Embedding) | 2,040 | 仓库无 LICENSE；HF 权重 Apache-2.0 | 2025-09-30 / — | Qwen3 嵌入/重排（0.6B/4B/8B） | 模型卡称 8B 于 2025-06-05 MTEB 多语榜第一（70.58） | daily-paper-reader 采用 Qwen3-Reranker-0.6B 本地重排 | — | R |

#### 2.10.5 实体消解（2）、采集基础件（3）、二级仓储平台族（4）、阅读组件（1）

| 仓库 | ★ | License | 最近提交 / 发版 | 定位 | 要点 | 可借鉴 / 复用 | 风险 | 级 |
|---|---|---|---|---|---|---|---|---|
| [moj-analytical-services/splink](https://github.com/moj-analytical-services/splink) | 2,434 | MIT | 2026-09-22 / v4.0.17 | 概率记录链接 | Fellegi-Sunter + EM；DuckDB（笔记本约 1 分钟百万记录）/ Spark / Postgres 后端 | 跨源论文/作者去重的概率匹配层（补 v1 identifier 图） | — | R |
| [dedupeio/dedupe](https://github.com/dedupeio/dedupe) | 4,516 | MIT | 2025-07-29 / — | 主动学习式实体消解 | — | 人工标注驱动阈值学习 | 维护放缓 | B |
| [mloesch/sickle](https://github.com/mloesch/sickle) | 117 | BSD 风格 | 2020-05-17 / 0.7.0 | OAI-PMH Python 客户端 | — | — | 停更 | B |
| [miku/metha](https://github.com/miku/metha) | 133 | GPL-3.0 | 2026-09-17 / v0.7.1 | OAI-PMH 增量采集器（Go，内置缓存） | — | 仓储族批量采集的断点/缓存思路 | GPL | B |
| [scrapy/protego](https://github.com/scrapy/protego) | 94 | BSD-3-Clause | 2026-09-22 / 0.6.2 | 纯 Python robots.txt 解析（Scrapy 采用） | 支持现代约定 | v2 robots 合规组件 | — | R |
| [DSpace/DSpace](https://github.com/DSpace/DSpace) | 1,098 | BSD-3-Clause | 2026-09-17 / dspace-10.1（2026-09-14） | 机构仓储平台 | OAI-PMH：DSpace 7+ 形如 `/server/oai/request`（MIT 实例 Identify 实测 baseURL `https://dspace.mit.edu/server/oai/request`） | **平台族 adapter**：一套覆盖所有 DSpace 实例 | 各实例 robots/ToS 不同 | I（源族） |
| [pkp/pkp-lib](https://github.com/pkp/pkp-lib)（OJS/OPS/OMP） | 349 | GPL-3.0 | 2026-09-26 / — | 学术出版平台共享库 | OJS OAI：`/index.php/<journal>/oai`（v1 在 AAAI 与 Econometric Society 实例已实测） | 同上 | — | I（源族） |
| [inveniosoftware/invenio-app-rdm](https://github.com/inveniosoftware/invenio-app-rdm) | 181 | MIT | 2026-09-23 / — | 研究数据仓储（Zenodo 所用） | OAI `…/oai2d`（Zenodo Identify 实测，earliestDatestamp 2014-02-03）+ REST | 同上 | — | I（源族） |
| [eprints/eprints3.4](https://github.com/eprints/eprints3.4) | 44 | LGPL-3.0 | 2026-09-25 / v3.4.7（2025-08-29） | 机构仓储平台 | OAI `/cgi/oai2`（White Rose Research Online 实测，自报 EPrints 3.4.6） | 同上 | — | I（源族） |
| [mozilla/pdf.js](https://github.com/mozilla/pdf.js) | 53,947 | Apache-2.0 | 2026-09-25 / v6.3.289 | 浏览器 PDF 渲染 | — | 阅读器组件 | — | R |

#### 2.10.6 深读：多用户隔离能力对比（基础设施层）

| 方案 | 隔离粒度 | 机制 | 适合承载 | 注意 |
|---|---|---|---|---|
| Qdrant `is_tenant` | 同集合 payload 分区 | 租户共址 + 每租户 HNSW（`m:0`,`payload_m:16`）+ 大租户升独立分片（v1.16+） | 私有向量（收藏/笔记/私有全文 chunk） | 过滤必须由后端注入，不可信任前端 |
| pgvector 分区 | 表分区/部分索引 | list 分区按 user_id；迭代扫描保证过滤后召回 | 与业务数据同事务的私有向量 | 分区数量与维护成本 |
| Vespa streaming | 文档组（`g=userid`） | 每查询只流式扫描该组，内存 45B/文档，精确 NN | 大量"小而私"的个人库 | 无 ANN；运维重 |
| Meilisearch tenant token | 查询时过滤 | JWT 内嵌过滤规则，仅约束 search | 公共索引上的"我的收藏视图" | 不约束写入/管理端点 |
| Typesense scoped key | 查询时过滤 | 派生 key 限定可见记录 | 同上 | GPL 服务 |
| 每用户加密库（local-deep-research） | 物理隔离 | SQLCipher AES-256，口令派生密钥不落盘 | auth-gated 全文与凭证 | 失去跨用户检索（正是红线要求） |

### 2.11 合规反例与排除清单（8 项；另 PyPaperBot/scholarly/PwC client 见 §2.2）

| 仓库 | ★ | License | 最近提交 / 发版 | 定位 | 触发的红线 | 级 |
|---|---|---|---|---|---|---|
| [Tishacy/SciDownl](https://github.com/Tishacy/SciDownl) | 325 | MIT | 2024-02-11 / — | Sci-Hub 非官方下载 API | 盗版源 | X |
| [JackKuo666/Sci-Hub-MCP-Server](https://github.com/JackKuo666/Sci-Hub-MCP-Server) | 161 | 无 | 2025-04-04 / — | Sci-Hub MCP | 盗版源 | X |
| [jmrplens/libgen-mcp](https://github.com/jmrplens/libgen-mcp) | 16 | MIT | 2026-09-25 / v2.0.1（2026-09-23；2026-07 新建） | LibGen MCP（Go） | 盗版源 | X |
| [JackKuo666/Google-Scholar-MCP-Server](https://github.com/JackKuo666/Google-Scholar-MCP-Server) | 409 | 无 | 2025-03-25 / — | Google Scholar MCP | Scholar 自动化 | X |
| [adityak74/mcp-scholarly](https://github.com/adityak74/mcp-scholarly) | 186 | MIT | 2026-08-25 / — | arXiv + Google Scholar（经 scholarly 与**免费代理池**）+ SerpBase 网页搜索 | 代理池绕封锁 | X（Scholar 部分） |
| [cookjohn/gs-skills](https://github.com/cookjohn/gs-skills) | 515 | MIT | 2026-03-13 / — | 经 Chrome DevTools MCP 驱动 Google Scholar 检索/引用追踪；`gs-fulltext` 返回含 **Sci-Hub** 的全文链接；遇 CAPTCHA 暂停交人工 | Scholar 自动化 + 盗版链接 | X |
| [cookjohn/cnki-skills](https://github.com/cookjohn/cnki-skills) | 960 | 无 | 2026-03-13 / — | 经 Chrome DevTools MCP 驱动 CNKI 检索、期刊目录、**PDF/CAJ 下载**、导出 Zotero；遇验证码暂停交人工 | 对无开放 API 站点的浏览器自动化批量操作（CNKI 条款细则 ⚠ 未逐条核验）；无 license | X |
| [searxng/searxng](https://github.com/searxng/searxng) | 37,654 | AGPL-3.0 | 2026-09-25 / — | 元搜索引擎（local-deep-research 默认网页源；README 提及有含 Google Scholar 引擎的学术向 fork） | 聚合上游搜索服务（上游 ToS ⚠ 未逐一核验） | X（作为学术主源） |

**组件级排除**（项目本体可借鉴、特定组件不得引入）：paper-search-mcp 的 Sci-Hub 连接器、Scholar 代理、OpenAIRE"Mozilla UA 升级重试"；
resp 的 SerpAPI-Scholar 与 Selenium-Connected Papers；PaSa 的 Serper（Google 结果转售）依赖；paperscraper 的 scholarly 指标；
Zotero translation-server 的默认 Chrome UA（改诚实 UA 后可用）。
**核验补充**：findpapers 的 `web_scraping` 富化与下载器（curl_cffi 冒充 Chrome TLS 指纹绕 WAF，且为默认富化源）；
gpt_academic 的 Sci-Hub 数据源与 Scholar 抓取插件；paper-search-mcp-nodejs 的 Sci-Hub 适配器与 Scholar/ScrapingAnt 通道；
PaperFlow 的 Google Scholar 主页抓取引导；MonkeyOCR v1 权重（非商用）。

### 2.12 横向归纳

**(a) 多源适配层**：v1 调研的"三层成熟度"（零抽象 → 能力组合基类 → 运行时自注册）之上，2026 年出现两种新形态：
①**能力矩阵公开化**（paper-search-mcp、findpapers 把"哪些源能 search/download/read/snowball/similar"写进文档并由回归测试维护）；
②**MCP 化**（同一 connector 层同时暴露为 Python API、CLI、MCP 工具与 Agent Skill）。

**(b) 查询编译**：只有 findpapers 实现了"统一 AST → 每源能力校验 → 远端下推 + 必要时 DNF 拆分、本地并集去重"的完整链
（**核验修正**：原写"本地集合代数补偿"，实际只有并集，不含跨请求的交/差）；
其余项目要么只支持关键词直通，要么（如 v1 subs DSL）只对单源做本地补偿谓词。

**(c) 路由**：显式"意图→工作流"路由仅见 Asta PaperFinder；LLM agent 类（gpt-researcher、local-deep-research、STORM）
以"agent 自选检索器"代替显式路由，成本与稳定性不可控。

**(d) 候选生成与排序**：从"余弦相似度 + 阈值"（zotero-arxiv-daily）进化到"多 lane 召回 + 统一池 + 交叉编码器 + LLM 精评"
（daily-paper-reader）与"混合检索 + 生成式重排 + 引用/标题加权"（arxiv-at-home）。

**(e) 反馈与学习**：只有 PaperFlow 明确定义了强/弱正负与漂移；papertok 明确列出探索与多样性；arXivDigest 提供在线评估；
其余项目基本无反馈闭环。

**(f) 存储与隔离**：几乎所有推送项目是"每人 fork 一个仓库"的单人形态（GitHub Actions + Pages + 可选 Supabase），
**没有一个开源项目实现"多用户 + 每用户凭证 + 合规分层共享"**；local-deep-research 的每用户加密库是最接近的多用户范式。

### 2.13 生态空白（v2 差异化机会）

1. **多用户合规平台**：开源界无"共享公共元数据、私有化 auth-gated 全文与凭证"的现成系统。
2. **社科/经管覆盖**：日推/检索工具几乎全部以 arXiv 与生物医学为中心；SSRN/RePEc/NBER、经济金融期刊 TOC（Crossref ISSN）
   的持续追踪仅见 Wispar（期刊关注）与 v1 自身。
3. **严谨增量订阅**：开源实现止于 `last_checked`（arxiv-mcp-server）或 `seen_ids`/carryover（daily-paper-reader）；
   v1 的 watermark + 重叠窗口 + 标识符去重（design/09）仍无开源对标。
4. **"刷论文"交互**：papertok（27★）、arxivtok（91★）等均为早期原型，无成熟开源对手。
5. **推荐评估闭环**：仅 arXivDigest（living lab）与少数 Bench；v2 若从第一天记录曝光/反馈日志即可建立优势。

---

## 3. 对 v2 设计的启示

1. **查询编译层照搬 findpapers 的执行计划范式**：统一查询 AST（词项 + 布尔 + 字段过滤码，"最内层过滤码优先"）→
   每源 `QueryBuilder` 声明 `_SUPPORTED_FILTERS` 并实现 `validate_query`/`convert_query`（可选 `expand_query`）→
   `QueryExecutionPlan{request_payloads, combination_expression}`，
   无法原生表达的布尔式按 DNF 拆成子请求、本地并集去重（**核验修正**：findpapers 只做到这一步；AND/NOT 的跨请求本地交/差
   以及"远端取超集 + 本地谓词过滤"须由 v2 自行设计，可复用 v1 本地补偿谓词）。v1 `subs/compile.py` + `arxiv.query_bool` 本地补偿谓词
   应升级为这一通用机制，并纳入 v1 Capability 声明（D-002）。**不得引入**其默认 `web_scraping` 富化（Chrome TLS 指纹冒充，§2.3.1）。
2. **显式意图路由（参照 Asta PaperFinder）**：至少四类工作流——
   ① *known-item*（DOI/arXiv ID/标题模糊匹配 → singleton 查询，OpenAlex singleton 免费；参考 arxiv-at-home 的标题模糊加权）；
   ② *metadata*（作者/机构/期刊/年份 → OpenAlex filter、Crossref ISSN、v1 VenueSpec 枚举）；
   ③ *content*（语义 → 本地向量索引优先，其次 OpenAlex semantic / S2 snippet）；
   ④ *feed*（时间窗新论文 → 各源增量通道与 v1 watch）。路由结果记录 canonical query（OpenAlex MCP 做法），同时作为缓存键与复现凭据。
3. **限速器升级为"端点类型令牌桶 + 美元预算器"**：Crossref 自 2025-12-01 按单条/列表分档（polite：单条 10 rps/并发 3、列表 3 rps/并发 3；
   public：5/1 与 1/1）；OpenAlex 按操作计价（singleton 免费、list $0.1/千、search 与 semantic $1/千、PDF $10/千，每 key 每日 $1 免费）；
   S2 key 起步 1 RPS；arXiv 3 秒 1 次且单连接。多用户平台对共享源必须**全局调度 + 缓存优先**，禁止按用户数线性放大请求。
4. **本地数据底座优先**：以 OpenAlex CC0 快照（4.8 亿作品）+ arXiv 元数据（OAI-PMH / Kaggle 快照）+ Crossref 为本地底座，
   API 只做增量与补全。abstracts-search 证明"快照→离线嵌入→faiss 全局语义索引"在单张消费级 GPU 上可维护；
   据此 v1 中"OpenAlex/S2 为 enrich-only"的定位（design/09 §3）在 v2 可升级为"快照驱动的 DISCOVER 源 + 计量 API 补全"。
5. **计量型与订阅型访问一律"用户自带凭证/额度"**：OpenAlex 官方 MCP 的 OAuth 2.1 + 用户自有 key/预算、Wispar 的每用户 EZproxy、
   pybliometrics 的用户 Scopus key 是现成范式。平台仅加密保管每用户凭证（v1 D-023 AES-GCM 凭证库扩为每用户），
   auth-gated 结果只落该用户私有层。
6. **两层存储 + 私有层强隔离**：公共元数据层（共享）与用户私有层（偏好、反馈、收藏、笔记、私有全文、私有向量）分离。
   私有向量用 Qdrant `is_tenant`/每租户 HNSW 或 pgvector 用户分区 + 迭代扫描；私有全文与凭证参照 local-deep-research 的每用户加密库；
   Meilisearch tenant token / Typesense scoped key 只可用于"读视图"，写入与管理必须后端鉴权（§2.10.6）。
7. **再分发红线写进数据模型**：arXiv API 条款禁止在自有服务器"存储并服务" e-print（除非获版权人许可或投稿许可允许），元数据为 CC0；
   S2 API 许可仅授予"access and display"，并禁止 repackage/distribute/sublicense the API（数据再分发未获授权，按禁止处理）；
   OpenAlex content：官方声明"PDF 保留原版权，OpenAlex 不授予额外权利"，使用者须逐作品遵守许可（**核验修正**，原标待核）。
   → 卡片只放元数据/摘要 + 原站链接；
   平台缓存全文仅对明确 CC 许可者开放共享（许可来源：Crossref license 字段、GROBID 许可识别、OpenAlex `best_oa_location.license`），其余全文仅限用户私有。
8. **候选生成→排序流水线采用 daily-paper-reader 已验证形态**：多 lane 召回（BM25/精确 + 向量 + 关注作者/期刊 + 订阅流）→
   统一候选池（每 lane 保底配额，池预算随规模动态）→ 本地交叉编码器重排（Qwen3-Reranker-0.6B、BGE reranker 等）→
   仅对 Top-K 调 LLM 精评 → 业务规则（去重、多样性、探索位）。query embedding 按 hash 缓存，远程模型失败即整轮熔断回退本地。
9. **冷启动四件套**：①导入个人库（Zotero/BibTeX）→ 嵌入原型 + 按加入时间衰减加权（zotero-arxiv-daily）；
   ②自然语言兴趣描述 → LLM 相关性评分（ArxivDigest）；③关注作者（S2/OpenAlex author ID，gpt_paper_assistant；作者消歧参考 S2AND）；
   ④少量评分主动学习（Scholar Inbox 思路；ASReview ELAS u5 可作最小实现）。
10. **反馈语义显式定义并记录曝光**：显式（赞/收藏/评分/评论）与隐式（点开 PDF、停留、滑过）分级；采用 PaperFlow 的
    "同批未选=弱负、追加只增不删、精读=保守正"，Cool Papers 的"点开即候选收藏"；必须记录曝光日志（push/impression id），
    才能区分"没看到"与"看到没选"。
11. **排序特征 v0 直接取 papertok 的信号全集**：显式偏好、学得亲和、关注、**有界**时效、**有界**影响力（防高引垄断）、语义相关、探索、来源多样性；
    卡片附"诚实标签"（Preprint/Verified，Open access/Open version/Subscription，未知不显示）。
12. **表示层**：论文向量用 SPECTER2 proximity 适配器、短查询用 adhoc_query 适配器（HF 权重 Apache-2.0）；OpenReview 评测表中 SPECTER2+SciNCL 0.5/0.5 集成
    loss 0.21、easy 0.91 为全表最优，hard triples 0.65 与 SciNCL 单模型并列最高（**核验修正**：原写"hard triples 上最好"；该表部分引自 Stelmakh 等）；
    跨学科一级分类用 s2_fos 23 类**标签体系**（覆盖数学/物理/化学/生物/心理/经济/商业/CS 等；其 SciBERT 权重为 AI2 ImpACT-LR 门控许可，引入前须评审），
    细主题用 OpenAlex topic 层级（domain→field→subfield→topic）。
13. **双向匹配借鉴 OpenReview 两件套**：亲和度层参考 openreview-expertise（用户=其论文/收藏集合）；分配层参考 openreview-matcher 的
    约束分配（最小费用流/FairFlow/FairSequence、配额、top-K 稀疏矩阵），用于"新论文曝光保底""用户日上限""避免少数热门论文垄断"。
    matcher 无 license，只能按论文自行实现。
14. **图结构不自研存储**：平台用 Postgres + Apache AGE（或递归 CTE），离线分析用 DuckPGQ；避开 Kùzu（已归档）、FalkorDB（SSPL）、Memgraph（BSL）。
    "从这篇扩展"功能组合 LocalCitationNetwork 的"种子→局部引文图→Top Cited/Top Citing"与 PaSa 的"引用扩展 + 逐篇判定"。
    ANN 图索引交给 pgvector HNSW / pgvectorscale DiskANN / Qdrant，不自研。
15. **双部署形态的索引选型**：本地单用户 = SQLite FTS5（v1 D-034）+ sqlite-vec（pre-v1，锁版本）或 LanceDB + tantivy-py；
    平台 = Postgres（业务 + pgvector/pgvectorscale + AGE）+ 独立检索服务（Meilisearch CE 或 OpenSearch；规模化再评估 Vespa，其 streaming 模式天然契合个人库）。
    AGPL/SSPL/BUSL 组件（ParadeDB、Elasticsearch、Meilisearch EE、VectorChord）不进核心链路，或先行法务评估。
16. **二级仓储采用"平台族 adapter + 实例注册表"**：DSpace（`/server/oai/request`）、EPrints（`/cgi/oai2`）、InvenioRDM/Zenodo（`/oai2d`）、
    OJS（`/index.php/<journal>/oai`）各一个 OAI-PMH adapter，实例以 RepositorySpec（baseURL、set、限速、robots 快照）登记，
    一族覆盖成百上千机构仓储；OA 全文定位以 Unpaywall/OpenAlex OA location 为主路径。
17. **单条元数据解析分三级**：DOI/arXiv ID → Crossref/OpenAlex singleton（免费）；失败再走 Zotero translation-server sidecar
   （AGPL 独立进程、**必须改为诚实 UA**、仅用户触发 + 限速）；参考文献串走 GROBID/biblio-glutton。
18. **实体消解加一层概率匹配**：在 v1 identifier 图（D-007/D-031）之外，用 splink（Fellegi-Sunter + EM，DuckDB 后端）处理无 DOI 的
    会议论文、预印本↔正式版（PaperMemory 的思路）、跨源作者合并（S2AND 作参考）。
19. **全文抽取插件化并按"三重许可"准入**：默认 pypdf → GROBID（D-033）；可选 VLM 抽取器按"代码许可 × 权重许可 × 商用门槛"分级：
    Docling（MIT）、olmOCR（Apache-2.0）、DeepSeek-OCR（MIT）、dots.ocr（MIT）优先；Marker/Surya（<500 万美元）、Chandra（<200 万且不得竞争，商用自托管需许可）、
    MinerU（MAU/营收阈值 + 在线服务显著标注义务）有条件；Nougat、Dolphin、MonkeyOCR v1 权重（非商用/研究许可）排除。选型以 olmOCR-Bench 框架在自有样本上复测。
20. **依赖治理继续"自有薄 adapter + canary + 契约测试"**：cv-arxiv-daily 因 arxiv.py 4.0 失效、findpapers/pyalex/社区 MCP 的限速/计费文档已与官方不符，
    说明第三方客户端必须锁版本并隔离；外部政策事实（限速、计费、许可）集中登记于一张"外部事实表"，定期复核并驱动 canary 断言。
21. **对外提供自有只读 MCP**：工具少而精（参照 zotero-mcp 实测 38 工具 13,448 tokens/请求）、分组与 Skill 惰性加载、结果回显 canonical query 与预算、
    长文 outline→section 渐进读取（arxiv-mcp-server）、附引用核验工具（OpenAlex `resolve_references`、bibverify）。
22. **评测从第一天开始**：离线用 olmOCR-Bench（抽取）、ScholarQABench/AstaBench/RealScholarQuery/PaperFlow-Bench（检索与推荐），
    外加 Scholar Inbox 公开的 774k 显式评分 + 556k 隐式交互数据（核验补充，许可待核）与 pyserini 的 BM25/稠密基线；
    在线采用 arXivDigest living lab 式"多策略并行 + 分流/交错评估"，前提是完整记录曝光、点击、收藏、评分、停留。
23. **前端/交互参照（供 UX 专题）**：papertok（React + Vite + Framer Motion、卡片诚实标签、Worker 代理保护密钥）、arxivtok（竖滑 + KaTeX + 无限滚动）、
    Wispar（可配置滑动手势、关注期刊 feed）、Cool Papers（极简列表 + 隐式收藏）；以上均为轻量原型，v2 需自行建立完整交互规范。
24. **差异化定位**：开源空白集中在"多用户合规分层 + 社科经管覆盖 + 严谨增量订阅 + 推荐评估闭环"（§2.13），恰为 v1 已有能力
    （VenueSpec、watermark 订阅、认证框架、canary）的延长线，v2 应把这些作为核心卖点而非重做通用检索。

## 4. 未决问题与风险

1. **OpenAlex 计费口径仍在变**：2026-01-13 公告称数值"非最终"且用 credits 表述；2026-02-24 博客与 2026-08-09 帮助页用 USD 计价；
   帮助页称无 key 每日 $0.10、有 key 为 10 倍；pyalex README 写"list 1 credit"、findpapers 文档写"无 key 约 10 次/天"——三方口径不一，实现前需再核并写入外部事实表。
2. **OpenAlex content 的许可与平台内再分发边界**——**核验后已部分解决**：Fulltext 帮助页（2026-09-18 版）称缓存"5,000 万+ OA 作品"
   （博客 2026-02 称 6,000 万，口径不一），"PDF 保留原版权，OpenAlex 不授予额外权利"，使用者须逐作品遵守许可，可按 `best_oa_location.license` 过滤；
   整库 PDF 同步只作为年费档付费附加服务出售（卖同步服务而非文档）。平台缓存并对他人提供仍须逐作品按 license 判定。
3. **Semantic Scholar 可用性**：key 起步 1 RPS 对多用户明显不足；API 许可"at will"可随时终止、仅授予 access and display 且禁止分发/转授 API；
   S2ORC 为 ODC-By 1.0（allenai/s2orc README，核验补充），S2AG 其余数据集许可/商用条件 ⚠ 未核验 → S2 只能作可降级的补充源。
4. **arXiv API 限流**：2026-02-26 起社区报告 3–4 秒间隔仍 429/503，arXiv 员工 2026-02-27 回帖承认"近期及持续做了调整"但未公布新数值，投诉持续至 2026-06
   （核验修正）；原文"部分查询仅返回最近约 1,000 篇"在所引线程中未找到，出处不明（⚠ 未核验）。需在 canary 中持续观测。
5. **copyleft 与非 OSI 许可在"网络服务"形态下的义务**：Zotero translation-server（AGPL）、ParadeDB（AGPL）、Typesense（GPL）、Elasticsearch（AGPL/SSPL/ELv2）、
   Meilisearch EE（BUSL）、VectorChord（AGPL/ELv2）需法务评估；本文分级按"未修改、独立进程"为前提。
6. **VLM 抽取权重许可**：Marker/Surya/Chandra 的营收/融资门槛与"不得与其 API 竞争"条款、MinerU 阈值条款与在线服务标注义务对 v2 商业化的影响待法务确认；
   核验已查明：MonkeyOCR v1 权重仅限学术/非商用评估，s2_fos 权重为 AI2 ImpACT License Low Risk（HF 门控）；Dolphin 的 README 徽章（MIT）与 LICENSE（Qwen Research）冲突。
7. **自报基准不可横比**：olmOCR README 与 Marker README 对同类系统给出不同数值；pgvectorscale 对比 Pinecone 的基准亦为厂商自报。
8. **低星/新建项目稳定性**：papertok（27★）、OpenAlex 官方 MCP（0★，2026-09-19 新建）、arxiv-at-home（53★）等作为参照可以，作为依赖需谨慎；托管 MCP 依赖第三方可用性。
9. **未核验事项汇总**（核验后更新）：仍未核验——CNKI 用户条款对自动化的具体约束；SearXNG 上游 ToS；OpenSearch RRF score-ranker 的引入版本；
   openalex-walden 与 guts 的关系；S2AG（除 S2ORC 外）数据集许可；ACL Anthology 元数据许可；Scholar Inbox 数据集许可；arXiv"约 1,000 篇"说法的出处。
   已由核验解决——OpenScholar 已发表于 *Nature*（2026-02-04）；Scholar Inbox 未见平台代码、仅开源数据集；Meilisearch EE 自 2025-08（v1.19）；
   PaperFlow 抓取公开 Scholar 主页；paper-search-mcp-nodejs 含 Sci-Hub 与 Scholar 组件；gpt_academic 含 Sci-Hub 数据源与 Scholar 抓取插件。
10. **调研盲区**：未覆盖 Gitee/GitCode；WebSearch 预算耗尽后新项目发现依赖 GitHub 关键词搜索（可能漏掉非英文描述项目）；
    架构结论多为 README/文档层核验，仅少数读到源码级。
11. **快照时效**：★、版本、许可均为 2026-09-26 快照；附件 TSV 可用 §1.4 命令一键复测。

## 5. 参考来源

### 5.1 政策、API 与文档（访问日期均为 2026-09-26）

- Crossref，《Announcing changes to REST API rate limits》（2025-11-05）：https://www.crossref.org/blog/announcing-changes-to-rest-api-rate-limits/
- OpenAlex 用户组公告《API keys required starting Feb 13 (and some new endpoints!)》（2026-01-13）：https://groups.google.com/g/openalex-users/c/rI1GIAySpVQ
- OpenAlex 博客《New Features and Usage-Based Pricing》（2026-02-24）：https://blog.openalex.org/openalex-api-new-features-and-usage-based-pricing/
- OpenAlex 帮助中心 Pricing：https://help.openalex.org/access/pricing/
- OpenAlex 帮助中心 Example costs（页面标注 2026-08-09 更新）：https://help.openalex.org/access/example-costs/
- OpenAlex 旧文档限速页（301 跳转至帮助中心）：https://docs.openalex.org/how-to-use-the-api/rate-limits-and-authentication
- Semantic Scholar API 产品页：https://www.semanticscholar.org/product/api
- Semantic Scholar API License Agreement：https://www.semanticscholar.org/product/api/license
- arXiv API Terms of Use：https://info.arxiv.org/help/api/tou.html
- arXiv API Google Group（社区 429 报告，仅检索摘要）：https://groups.google.com/a/arxiv.org/g/api/c/ycq8giRdZsQ
- HyperAI《Paper With Code Shuts Down…》：https://hyper.ai/en/news/42900
- PwC 数据仓 issue #116（2025-08-14）：https://github.com/paperswithcode/paperswithcode-data/issues/116
- Coursera《What Happened to Papers With Code》（仅检索摘要）：https://www.coursera.org/articles/papers-with-code
- Quickwit《Quickwit joins Datadog》（仅检索摘要）：https://quickwit.io/blog/quickwit-joins-datadog ；Datadog：https://www.datadoghq.com/blog/datadog-acquires-quickwit/
- Meilisearch《Introducing the Meilisearch Enterprise Edition license》（仅检索摘要）：https://www.meilisearch.com/blog/enterprise-license ；LICENSE：https://github.com/meilisearch/meilisearch/blob/main/LICENSE
- Meilisearch tenant tokens：https://www.meilisearch.com/docs/learn/security/multitenancy_tenant_tokens
- MinerU changelog：https://opendatalab.github.io/MinerU/reference/changelog/ ；LICENSE：https://github.com/opendatalab/MinerU/blob/master/LICENSE.md
- Zotero changelog：https://www.zotero.org/support/changelog
- Qdrant Multitenancy 指南：https://qdrant.tech/documentation/guides/multitenancy/
- Vespa Streaming Search：https://docs.vespa.ai/en/performance/streaming-search.html
- OpenSearch Hybrid search：https://docs.opensearch.org/latest/vector-search/ai-search/hybrid-search/index/ ；Score ranker：https://docs.opensearch.org/latest/search-plugins/search-pipelines/score-ranker-processor/ ；Foundation：https://opensearch.org/foundation/
- ASReview 模型文档：https://asreview.readthedocs.io/en/latest/lab/models.html
- paperscraper PDF 检索文档：https://jannisborn.github.io/paperscraper/examples/pdf-retrieval/
- OpenScholar 论文：https://arxiv.org/abs/2411.14199
- Scholar Inbox 论文：https://arxiv.org/abs/2504.08385
- Cool Papers 站点：https://papers.cool/
- HF 模型卡 dots.ocr（重定向至 dots-studio）：https://huggingface.co/rednote-hilab/dots.ocr
- HF 模型卡 Qwen3-Embedding-0.6B：https://huggingface.co/Qwen/Qwen3-Embedding-0.6B
- OAI-PMH Identify 实测：https://zenodo.org/oai2d?verb=Identify ；https://dspace.mit.edu/oai/request?verb=Identify ；https://eprints.whiterose.ac.uk/cgi/oai2?verb=Identify
- arxiv.py 4.0.0 发版说明：https://github.com/lukasschwab/arxiv.py/releases/tag/4.0.0
- cv-arxiv-daily 失败 run（2026-09-26）：https://github.com/Vincentqyw/cv-arxiv-daily/actions/runs/36213328160
- findpapers 文档：https://github.com/jonatasgrosman/findpapers/tree/main/docs
- PyPI JSON（版本/日期口径）：https://pypi.org/pypi/{package}/json（pybliometrics、scholarly、findpapers、paperscraper、pyalex、habanero、semanticscholar、arxiv、openreview-py、paper-search-mcp、arxiv-mcp-server、zotero-mcp-server、paper-qa、ai2-scholar-qa、knowledge-storm、gpt-researcher、local-deep-research、asreview、papis、metapub、grobid-client-python、mineru、docling、olmocr、marker-pdf、openalex-official）
- GitLab API（ORKG）：https://gitlab.com/api/v4/projects/TIBHannover%2Forkg%2Forkg-backend ；https://gitlab.com/api/v4/projects/TIBHannover%2Forkg%2Forkg-frontend
- **核验阶段新增来源**（均 2026-09-26 访问）：OpenAlex Fulltext 帮助页 https://help.openalex.org/access/fulltext/ ；
  HF `pwc-archive` 组织 https://huggingface.co/pwc-archive ；Quickwit 改许可提交 https://github.com/quickwit-oss/quickwit/commits/main/LICENSE.md ；
  Meilisearch 博客 https://www.meilisearch.com/blog/enterprise-license 与 LICENSE-EE https://github.com/meilisearch/meilisearch/blob/main/LICENSE-EE ；
  MinerU 3.1.0 发版说明 https://github.com/opendatalab/MinerU/releases/tag/mineru-3.1.0-released ；
  arXiv API 线程（员工 2026-02-27 回帖）https://groups.google.com/a/arxiv.org/g/api/c/ycq8giRdZsQ ；
  NCBI Insights《New API Keys for the E-utilities》https://ncbiinsights.ncbi.nlm.nih.gov/2017/11/02/new-api-keys-for-the-e-utilities/ ；
  Ai2《Now in Nature》https://allenai.org/blog/openscholar-nature （Nature DOI 10.1038/s41586-025-10072-4）；
  S2ORC 许可 https://github.com/allenai/s2orc ；Scholar Inbox 数据集 https://github.com/avg-dev/scholar_inbox_datasets ；
  findpapers 源码 https://github.com/jonatasgrosman/findpapers/blob/main/findpapers/connectors/web_scraping.py 、
  https://github.com/jonatasgrosman/findpapers/blob/main/findpapers/query/builder.py 、https://github.com/jonatasgrosman/findpapers/blob/main/docs/similar.md ；
  cv-arxiv-daily workflow https://github.com/Vincentqyw/cv-arxiv-daily/blob/main/.github/workflows/cv-arxiv-daily.yml 与 runs 列表
  https://github.com/Vincentqyw/cv-arxiv-daily/actions/workflows/cv-arxiv-daily.yml ；PsyArXiv 提供方 https://api.osf.io/v2/preprint_providers/psyarxiv/

### 5.2 代码仓库（访问日期均为 2026-09-26；★/许可/活跃度见附件 TSV）

- v1 复核：各仓库链接见 §2.2 表。
- 客户端与 MCP：https://github.com/ourresearch/openalex-official ，https://github.com/ropensci/openalexR ，https://github.com/metapub/metapub ，https://github.com/fabiobatalha/crossrefapi ，https://github.com/NLeSC/litstudy ，https://github.com/unpywall/unpywall ，https://github.com/blazickjp/arxiv-mcp-server ，https://github.com/openags/paper-search-mcp ，https://github.com/54yyyu/zotero-mcp ，https://github.com/cookjohn/zotero-mcp ，https://github.com/ourresearch/openalex-mcp-server ，https://github.com/huggingface/hf-mcp-server ，https://github.com/genomoncology/biomcp ，https://github.com/takashiishida/arxiv-latex-mcp ，https://github.com/zongmin-yu/semantic-scholar-fastmcp-mcp-server ，https://github.com/oksure/openalex-research-mcp ，https://github.com/drAbreu/alex-mcp ，https://github.com/andybrandt/mcp-simple-pubmed ，https://github.com/Dianel555/paper-search-mcp-nodejs ，https://github.com/introfini/ZotSeek ，https://github.com/Galaxy-Dawn/claude-scholar ，https://github.com/wp-a/nature-academic-search ，https://github.com/Hylouis233/bibverify
- LLM 研究助手：https://github.com/Future-House/paper-qa ，https://github.com/AkariAsai/OpenScholar ，https://github.com/stanford-oval/storm ，https://github.com/assafelovic/gpt-researcher ，https://github.com/allenai/ai2-scholarqa-lib ，https://github.com/allenai/asta-paper-finder ，https://github.com/allenai/asta-bench ，https://github.com/bytedance/pasa ，https://github.com/LearningCircuit/local-deep-research ，https://github.com/langchain-ai/open_deep_research ，https://github.com/Alibaba-NLP/DeepResearch ，https://github.com/AutoSurveys/AutoSurvey ，https://github.com/khoj-ai/openpaper ，https://github.com/ScholarXIV/OpenScholarXIV
- 推送与 feed：https://github.com/TideDra/zotero-arxiv-daily ，https://github.com/dw-dengwei/daily-arXiv-ai-enhanced ，https://github.com/ziwenhahaha/daily-paper-reader ，https://github.com/Vincentqyw/cv-arxiv-daily ，https://github.com/AutoLLM/ArxivDigest ，https://github.com/tatsu-lab/gpt_paper_assistant ，https://github.com/JoeLeelyf/customize-arxiv-daily ，https://github.com/OpenRaiser/PaperFlow ，https://github.com/gaoxin492/PaperFeeder ，https://github.com/iai-group/arXivDigest ，https://github.com/karpathy/arxiv-sanity-preserver ，https://github.com/bojone/papers.cool ，https://github.com/mugar123/papertok ，https://github.com/Miguel07Alm/arxivtok ，https://github.com/cookiegg/flopap ，https://github.com/khuynh22/paper-deck ，https://github.com/a1henu/arxiv-daily-scroll ，https://github.com/yzr278892/arxiv-daily-researcher ，https://github.com/Scriptbash/Wispar
- 检索引擎/知识组织：https://github.com/arXiv/arxiv-search ，https://github.com/arXiv/arxiv-browse ，https://github.com/ourresearch/openalex-gui ，https://github.com/ourresearch/openalex-elastic-api ，https://github.com/ourresearch/openalex-guts ，https://github.com/ourresearch/openalex-walden ，https://github.com/ourresearch/oadoi ，https://github.com/allenai/s2search ，https://github.com/allenai/s2-folks ，https://gitlab.com/TIBHannover/orkg ，https://github.com/OpenKnowledgeMaps/Headstart ，https://github.com/LocalCitationNetwork/LocalCitationNetwork.github.io ，https://github.com/CitationGecko/gecko-react ，https://github.com/WDscholia/scholia ，https://github.com/colonelwatch/abstracts-search ，https://github.com/mrapplexz/arxiv-at-home ，https://github.com/whiskyechobravo/kerko ，https://github.com/openreview/openreview-expertise ，https://github.com/openreview/openreview-matcher ，https://github.com/allenai/SPECTER2 ，https://github.com/allenai/s2_fos ，https://github.com/allenai/S2AND ，https://github.com/allenai/citeomatic ，https://github.com/allenai/s2orc ，https://github.com/asreview/asreview ，https://github.com/vitorfs/parsifal
- 文献管理：https://github.com/zotero/zotero ，https://github.com/zotero/translation-server ，https://github.com/retorquere/zotero-better-bibtex ，https://github.com/windingwind/zotero-pdf-translate ，https://github.com/windingwind/zotero-better-notes ，https://github.com/windingwind/zotero-plugin-template ，https://github.com/MuiseDestiny/zotero-gpt ，https://github.com/yilewang/llm-for-zotero ，https://github.com/papersgpt/papersgpt-for-zotero ，https://github.com/urschrei/pyzotero ，https://github.com/JabRef/jabref ，https://github.com/papis/papis ，https://github.com/Future-Scholars/paperlib ，https://github.com/vict0rsch/PaperMemory ，https://github.com/binary-husky/gpt_academic ，https://github.com/PDFMathTranslate/PDFMathTranslate ，https://github.com/funstory-ai/BabelDOC ，https://github.com/kaixindelele/ChatPaper ，https://github.com/larsgw/citation.js
- PDF 解析：https://github.com/grobidOrg/grobid ，https://github.com/grobidOrg/grobid-client-python ，https://github.com/kermitt2/biblio-glutton ，https://github.com/facebookresearch/nougat ，https://github.com/datalab-to/marker ，https://github.com/datalab-to/surya ，https://github.com/datalab-to/chandra ，https://github.com/opendatalab/MinerU ，https://github.com/docling-project/docling ，https://github.com/allenai/olmocr ，https://github.com/studio-dots-ai/dots.ocr ，https://github.com/deepseek-ai/DeepSeek-OCR ，https://github.com/PaddlePaddle/PaddleOCR ，https://github.com/bytedance/Dolphin ，https://github.com/Yuliang-Liu/MonkeyOCR ，https://github.com/Unstructured-IO/unstructured ，https://github.com/pymupdf/pymupdf4llm ，https://github.com/allenai/papermage ，https://github.com/allenai/science-parse ，https://github.com/allenai/pdffigures2 ，https://github.com/CeON/CERMINE ，https://github.com/inukshuk/anystyle ，https://github.com/allenai/s2orc-doc2json
- 基础设施：https://github.com/meilisearch/meilisearch ，https://github.com/meilisearch/charabia ，https://github.com/typesense/typesense ，https://github.com/quickwit-oss/tantivy ，https://github.com/quickwit-oss/tantivy-py ，https://github.com/quickwit-oss/quickwit ，https://github.com/vespa-engine/vespa ，https://github.com/opensearch-project/OpenSearch ，https://github.com/elastic/elasticsearch ，https://github.com/paradedb/paradedb ，https://github.com/qdrant/qdrant ，https://github.com/lancedb/lancedb ，https://github.com/lance-format/lance ，https://github.com/milvus-io/milvus ，https://github.com/weaviate/weaviate ，https://github.com/chroma-core/chroma ，https://github.com/pgvector/pgvector ，https://github.com/timescale/pgvectorscale ，https://github.com/supervc-stack/VectorChord ，https://github.com/duckdb/duckdb-vss ，https://github.com/asg017/sqlite-vec ，https://github.com/cwida/duckpgq-extension ，https://github.com/facebookresearch/faiss ，https://github.com/nmslib/hnswlib ，https://github.com/microsoft/DiskANN ，https://github.com/unum-cloud/USearch ，https://github.com/apache/age ，https://github.com/neo4j/neo4j ，https://github.com/kuzudb/kuzu ，https://github.com/FalkorDB/FalkorDB ，https://github.com/memgraph/memgraph ，https://github.com/huggingface/text-embeddings-inference ，https://github.com/huggingface/sentence-transformers ，https://github.com/FlagOpen/FlagEmbedding ，https://github.com/QwenLM/Qwen3-Embedding ，https://github.com/moj-analytical-services/splink ，https://github.com/dedupeio/dedupe ，https://github.com/mloesch/sickle ，https://github.com/miku/metha ，https://github.com/scrapy/protego ，https://github.com/DSpace/DSpace ，https://github.com/pkp/pkp-lib ，https://github.com/inveniosoftware/invenio-app-rdm ，https://github.com/eprints/eprints3.4 ，https://github.com/mozilla/pdf.js
- 合规反例：https://github.com/Tishacy/SciDownl ，https://github.com/JackKuo666/Sci-Hub-MCP-Server ，https://github.com/jmrplens/libgen-mcp ，https://github.com/JackKuo666/Google-Scholar-MCP-Server ，https://github.com/adityak74/mcp-scholarly ，https://github.com/cookjohn/gs-skills ，https://github.com/cookjohn/cnki-skills ，https://github.com/searxng/searxng
- 核验补充（§2.3.2）：https://github.com/inspirehep/inspirehep ，https://github.com/andycasey/ads ，https://github.com/CenterForOpenScience/osf.io ，https://github.com/acl-org/acl-anthology ，https://github.com/castorini/pyserini
- 本仓库既有调研：[../../research/github-similar-projects.md](../../archive-v1.md#docs-research-github-similar-projects-md)、[../../research/site-survey/aaai-ojs.md](../../archive-v1.md#docs-research-site-survey-aaai-ojs-md)（OJS OAI 实测）

## 6. v2 分级清单（末尾汇总）

> 级别定义见 §1.3。同一项目在不同组件上可能分属不同级别（如 paper-search-mcp 本体 B、Sci-Hub 组件 X）。

### 6.1 R — 直接复用（作为依赖/组件）

| 类别 | 项目 | 前置条件 |
|---|---|---|
| 检索与存储 | pgvector、pgvectorscale、Qdrant、tantivy / tantivy-py、sqlite-vec（本地模式）、LanceDB（本地模式备选）、faiss、hnswlib | sqlite-vec pre-v1 须锁版本；过滤由后端注入 |
| 表示与重排 | sentence-transformers、text-embeddings-inference、FlagEmbedding（BGE）、Qwen3-Embedding/Reranker 权重（Apache-2.0）、SPECTER2（HF 权重 Apache-2.0）、s2_fos 标签体系 | 各模型权重许可逐个登记；s2_fos 权重为 AI2 ImpACT-LR（门控），只复用标签体系，权重须评审 |
| 数据与合规基础件 | protego（robots）、splink（实体消解）、pyzotero（Blue Oak）、openreview-py、pubmed_parser、metapub、grobid-client-python、citation.js、charabia（经 Meilisearch）、Docling（MIT）、acl-anthology Python 包（核验补充） | 第三方客户端锁版本 + 契约测试；ACL Anthology 数据许可待核 |
| 交互与阅读 | pdf.js、ASReview（主动学习筛选/冷启动模块） | — |

### 6.2 I — 集成（独立服务 / 外部接口 / 有条件）

| 类别 | 项目 | 条件 |
|---|---|---|
| 解析服务 | GROBID、biblio-glutton、Zotero translation-server | translation-server：AGPL 独立进程、改诚实 UA、仅用户触发 + 限速 |
| 可选抽取器 | olmOCR、DeepSeek-OCR、dots.ocr、PaddleOCR（-VL）、MinerU、Marker / Surya / Chandra | MinerU 阈值条款 + 在线服务显著标注义务；Marker/Surya <500 万美元；Chandra <200 万且不得竞争、商用自托管需许可 |
| 检索服务 | Meilisearch CE、OpenSearch、Typesense、Vespa（规模化）、Apache AGE、ParadeDB | 禁用 Meilisearch EE 功能；Typesense/ParadeDB 许可需法务评估 |
| 外部 API / 用户账号 | OpenAlex（API、openalex-official CLI、官方 MCP）、Zotero（用户库）、pybliometrics（用户 Scopus key）、HF Hub（hf-mcp-server）、arxiv-mcp-server、54yyyu/zotero-mcp、NASA ADS（andycasey/ads，用户自有 token；核验补充）、INSPIRE / OSF API（核验补充） | 一律用户自带 key/OAuth；结果按许可分层 |
| 源族 | DSpace、EPrints、InvenioRDM（Zenodo）、OJS（pkp-lib） | 实例注册表 + robots/ToS 快照 + 保守限速 |

### 6.3 B — 仅借鉴

| 借鉴主题 | 项目 |
|---|---|
| 查询编译与路由 | findpapers（仅查询编译；web_scraping 组件 X）、Asta PaperFinder、paper-search-mcp（架构/能力矩阵）、biomcp、OpenAlex 官方 MCP（canonical OQL、OAuth 额度）、pyserini（离线评测基线；核验补充） |
| 候选生成/排序/反馈 | daily-paper-reader、zotero-arxiv-daily、PaperFlow、papertok、ArxivDigest、gpt_paper_assistant、arxiv-sanity-lite、arxiv-at-home、Cool Papers、arXivDigest（living lab） |
| 双向匹配与表示 | openreview-expertise、openreview-matcher（无 license，只按论文实现）、S2AND、s2search、citeomatic |
| RAG / Agent | PaperQA2、OpenScholar、Ai2 ScholarQA、PaSa、STORM、gpt-researcher、local-deep-research（每用户加密库）、Tongyi DeepResearch、open_deep_research（已归档）、AutoSurvey、openpaper、asta-bench |
| 引擎与数据管线 | arXiv search/browse、OpenAlex elastic-api / guts / walden / gui、Unpaywall oadoi、abstracts-search、paperetl、pybliometrics（缓存/key 池）、zotero/translators（manifest + testCases）、Elasticsearch、Quickwit、Lance 格式（lance-format/lance）、Milvus、Weaviate、Chroma、VectorChord、DuckDB VSS、DuckPGQ、DiskANN、USearch、Neo4j CE、dedupe、metha、sickle |
| 知识组织与可视化 | ORKG、Headstart、LocalCitationNetwork、Citation Gecko、Scholia、Kerko |
| 前端与移动形态 | Wispar、arxivtok、flopap、paper-deck、OpenScholarXIV、arxiv-daily-scroll、arxiv-daily-researcher、daily-arXiv-ai-enhanced、cv-arxiv-daily（反例）、customize-arxiv-daily、PaperFeeder、arxiv-sanity-preserver |
| 文献管理/阅读 | Zotero 插件生态（AGPL：pdf-translate、better-notes、plugin-template、zotero-gpt、llm-for-zotero、papersgpt）、better-bibtex、JabRef、papis、paperlib、PaperMemory、ZotSeek、cookjohn/zotero-mcp、gpt_academic、PDFMathTranslate、BabelDOC、ChatPaper（代码不可用）、claude-scholar、nature-academic-search、bibverify |
| 客户端与数据 | paperscraper（dump 模式）、arxiv.py、semanticscholar、pyalex、habanero、crossrefapi、openalexR、litstudy、unpywall、resp（非 Scholar 部分）、ai_papers_scrapper、openreview_scraper（无 license）、arxivscraper、arxiv-public-datasets、s2orc、s2-folks、parsifal |
| 解析（停更/备选） | MonkeyOCR（仅思路，v1 权重非商用）、Unstructured、pymupdf4llm（AGPL）、papermage、pdffigures2、anystyle、s2orc-doc2json |
| 学科平台实现（核验补充） | INSPIRE（inspirehep monorepo）、OSF（osf.io） |
| 社区 MCP | semantic-scholar-fastmcp、openalex-research-mcp、alex-mcp、mcp-simple-pubmed、paper-search-mcp-nodejs、arxiv-latex-mcp |

### 6.4 X — 排除

| 原因 | 项目 / 组件 |
|---|---|
| 盗版源 | PyPaperBot、SciDownl、Sci-Hub-MCP-Server、libgen-mcp；paper-search-mcp 的 Sci-Hub 连接器；gs-skills 的 Sci-Hub 链接；**核验补充**：gpt_academic 的 Sci-Hub 数据源、paper-search-mcp-nodejs 的 Sci-Hub 适配器 |
| Google Scholar 自动化 / 绕封锁 | scholarly（作为源）、Google-Scholar-MCP-Server、mcp-scholarly（Scholar 部分）、gs-skills；paper-search-mcp 的 Scholar 代理；resp 的 SerpAPI-Scholar；paperscraper 的 scholarly 指标；SearXNG（作为学术主源）；**核验补充**：gpt_academic 的 Scholar 抓取插件、paper-search-mcp-nodejs 的 Scholar/ScrapingAnt 通道、PaperFlow 的 Scholar 主页抓取引导 |
| 冒充 / 非 API 站点浏览器自动化 | paper-search-mcp 的"Mozilla UA 升级重试"；cnki-skills（CNKI 浏览器自动化下载）；resp 的 Selenium-Connected Papers；**核验补充**：findpapers 的 `web_scraping` 富化与下载器（curl_cffi 冒充 Chrome TLS 指纹以绕 WAF） |
| 第三方 SERP 转售依赖 | PaSa 的 serper.dev 依赖（算法可借鉴） |
| 技术淘汰 / 许可不兼容 | paperswithcode-client（平台关停）、Kùzu（已归档）、FalkorDB（SSPL）、Memgraph（BSL）、Nougat（权重非商用 + 停更）、Dolphin（Qwen 研究许可）、MonkeyOCR v1 权重（非商用；核验补充）、science-parse、CERMINE（停更） |

## 核验记录

**核验方式**：对抗式事实核验（默认怀疑），由独立 agent 于 2026-09-26（UTC 约 19:00–20:00，即北京时间 09-27 03:00–04:00）完成，只改本文件与附件目录。

**过程记录（可复现）**：

- 仓库复测：对附件 TSV 中 196 个 GitHub 仓库逐一调用 `gh api repos/{r}`、`repos/{r}/releases/latest`、`repos/{r}/commits?per_page=1`（与 §1.4 同口径），
  结果存 [repo-metrics-verify-2026-09-26.tsv](paper-acquisition-and-search-oss/repo-metrics-verify-2026-09-26.tsv)
  （复测时刻 UTC 约 19:00–19:30；列 `stars_live`/`stars_snapshot`/`delta`（复测减快照）/`license_live`/`archived_live`/…/`scope`，
  `scope=survey` 为原 196 项、`verify-supplement` 为 §2.3.2 的 5 个核验补充仓库）；
  ORKG 用 GitLab API `projects/TIBHannover%2Forkg%2Forkg-{backend,frontend}?license=true`。
- 源码/文档直读：`gh api repos/{r}/readme`、`contents/{path}`、`git/trees/{branch}?recursive=1`、`releases/tags/{tag}`、`commits?path=LICENSE*`；
  cv-arxiv-daily 另读 `actions/workflows`、`actions/runs?per_page=100`（翻 3 页）、`actions/jobs/108324242049/logs`。
- 官方页面：WebFetch 读取 Crossref 博客、OpenAlex 用户组公告/博客/帮助中心（Pricing、Example costs、Fulltext）、OpenAlex MCP README、S2 API 页与许可页、
  arXiv API TOU 与 API Google Group 线程、Quickwit 博客、Meilisearch 博客与多租户文档、Qdrant/Vespa 文档、Zotero changelog、arXiv 2411.14199 / 2504.08385 摘要页、
  Ai2 博客、HF 模型卡（Qwen3-Embedding-8B、specter2_base）与 HF `pwc-archive`、NCBI Insights、ASReview 模型文档、paperscraper 文档。
  NCBI Bookshelf 与 PubMed 页面对自动访问返回 reCAPTCHA，未尝试绕过，改用 NCBI 官方博客与 Ai2 博客。
- 协议实测：对 Zenodo、MIT DSpace、White Rose EPrints 各发 1 次 OAI-PMH `Identify`（诚实 UA，间隔 3 秒）。
- 检索式（WebSearch，2026-09-26）：`Semantic Scholar Academic Graph datasets license ODC-BY abstracts s2orc commercial use`；
  `OpenScholar Nature 2026 "Synthesizing scientific literature with retrieval-augmented language models" published`；
  `OpenAlex content endpoint PDF TEI full text license redistribution ...`（限定 openalex.org 域）。GitHub 检索式：`scholar inbox`、`scholar-inbox`，
  以及 `tiktok arxiv`、`tiktok papers`、`tiktok research papers`、`swipe papers`、`arxiv swipe`、`tinder papers`、`doomscroll papers`、`scroll papers arxiv`、
  `papers feed tiktok`、`arxiv reels`（用于检验"刷论文前端均 <100★"）。
- 前次中断检查：核验开始时本文件无任何"核验"类章节或半截修改（文件最后修改时间与调研员完成时间一致），故本节为首次建立。

**核验结论汇总**：抽查 44 条承重断言（外加 196 个仓库的批量复测）——确认 28 条、修正 15 条、仍未核验 1 条
（另有第 14 行中"约 1,000 篇"子项改标出处不明 ⚠；核验补充条目中 ACL Anthology 数据许可、Scholar Inbox 数据集许可新标 ⚠）；未发现编造的仓库、论文或公司，
无需删除条目；另补充 5 个覆盖缺口仓库（§2.3.2）与 1 个数据集仓库（Scholar Inbox）。影响设计的主要修正有 5 处：findpapers 的合并语义（只做 DNF 并集，
没有交/差运算）；findpapers、gpt_academic、paper-search-mcp-nodejs、PaperFlow 四个项目含越线组件；OpenAlex 全文许可边界；MinerU 的在线服务标注义务；
MonkeyOCR、s2_fos 的权重许可。

| # | 断言（原文要点） | 结论（确认/修正/删除/未核验） | 依据来源 URL | 核验日期（2026-09-26） |
|---|---|---|---|---|
| 1 | 196 个 GitHub 仓库存在，★/License/归档/最近提交/发版如附件 TSV | 确认（全部存在；★ 偏差 ≤8；许可、归档零差异；charabia 漏记 v0.10.0、gpt-researcher 同日新发 v3.7.0，已修正） | https://api.github.com/repos/{owner}/{repo}（逐仓复测，见 verify TSV） | 2026-09-26 |
| 2 | PwC 2025-07-24 关停、07-25 公告，重定向至 HF Trending Papers | 确认 | https://hyper.ai/en/news/42900 ；https://github.com/paperswithcode/paperswithcode-data/issues/116 | 2026-09-26 |
| 3 | PwC"历史数据仅存静态存档" | 修正：最后公开快照由 HF `pwc-archive` 托管（7 个数据集） | https://huggingface.co/pwc-archive | 2026-09-26 |
| 4 | Crossref 2025-11-05 公告、2025-12-01 生效；public 单条 5 rps/并发 1、列表 1/1；polite 10/3、3/3；Plus/XML/OAI-PMH 不变 | 确认 | https://www.crossref.org/blog/announcing-changes-to-rest-api-rate-limits/ | 2026-09-26 |
| 5 | OpenAlex 2026-01-13 公告、02-13 强制 key；无 key 100 credits 后 409；取消 polite pool 与 email 参数；数值"非最终" | 确认 | https://groups.google.com/g/openalex-users/c/rI1GIAySpVQ | 2026-09-26 |
| 6 | OpenAlex USD 计价：singleton 免费、list $0.10/千、search 与 semantic $1/千、content $10/千；每 key 每日 $1；无 key $0.10/日；Example costs 页 2026-08-09 更新 | 确认 | https://help.openalex.org/access/example-costs/ | 2026-09-26 |
| 7 | OpenAlex 年费档 $5k/$10k/≥$20k | 确认（补每日预算 $20/$100/$200+；Pricing 页 2026-08-11 更新） | https://help.openalex.org/access/pricing/ | 2026-09-26 |
| 8 | OpenAlex 4.8 亿作品 CC0 免费；语义检索 beta；查询至 8KB；官方 CLI | 确认 | https://blog.openalex.org/openalex-api-new-features-and-usage-based-pricing/ | 2026-09-26 |
| 9 | OpenAlex 新增"6,000 万 OA 作品 PDF/TEI"；其再分发边界 ⚠ 未核验 | 修正：帮助页（2026-09-18 版）为 5,000 万+、TEI 约 4,300 万；"PDF 保留原版权，不授予额外权利"，使用者逐作品遵守许可 | https://help.openalex.org/access/fulltext/ | 2026-09-26 |
| 10 | OpenAlex 官方 MCP：`mcp.openalex.org/mcp`、Streamable HTTP、OAuth 2.1 用户自有 key/预算、8 个只读工具、`resolve_references` 每次 25 条、canonical OQL + 可复跑 URL、低余额提示、轮换 key 断连；MIT；2026-09-19 建 | 确认 | https://github.com/ourresearch/openalex-mcp-server | 2026-09-26 |
| 11 | openalex-official CLI（原 openalex-content-downloader）：`download --api-key … --content pdf,xml`、stdin、S3；2026-02-02 建，v0.3.3（2026-03-18） | 确认 | https://github.com/ourresearch/openalex-official | 2026-09-26 |
| 12 | arxiv.py 4.0.0（2026-05-17）移除 `Search.results`、`download_pdf/source`，feedparser→lxml，UA 带版本；3.0.0（2026-04-12）弃 Py3.9、默认 `max_results=100` | 确认 | https://github.com/lukasschwab/arxiv.py/releases/tag/4.0.0 ；https://github.com/lukasschwab/arxiv.py/releases/tag/3.0.0 | 2026-09-26 |
| 13 | cv-arxiv-daily 日更 workflow 于 2026-09-16/21/26 连续失败（`AttributeError`） | 修正：cron 实为每 5 天；自 2026-05-21（4.0.0 发布后首次运行）起 29 次全部失败；09-26 日志为装 arxiv-4.0.1 后 `AttributeError` | https://github.com/Vincentqyw/cv-arxiv-daily/actions/runs/36213328160 ；https://github.com/Vincentqyw/cv-arxiv-daily/blob/main/.github/workflows/cv-arxiv-daily.yml | 2026-09-26 |
| 14 | arXiv API 2026-02 下旬社区报告 429（⚠ 非官方）；"部分查询仅返回约 1,000 篇" | 修正：线程 02-26 起、arXiv 员工 02-27 承认"做了调整"、投诉持续至 06-05；"约 1,000 篇"在线程中未找到，改标出处不明 ⚠ | https://groups.google.com/a/arxiv.org/g/api/c/ycq8giRdZsQ | 2026-09-26 |
| 15 | arXiv API TOU：1 req/3s 单连接；不得在自有服务器存储并服务 e-print（除非获版权人许可或投稿许可允许）；元数据 CC0 | 确认 | https://info.arxiv.org/help/api/tou.html | 2026-09-26 |
| 16 | S2 API key 起步 1 RPS；无 key 共享 1,000 RPS | 确认 | https://www.semanticscholar.org/product/api | 2026-09-26 |
| 17 | S2 API 许可"at will"可终止、禁止再分发数据 | 修正措辞：at will 属实；许可仅授予"access and display"，禁止 repackage/distribute/sublicense **the API**，数据再分发未获授权 | https://www.semanticscholar.org/product/api/license | 2026-09-26 |
| 18 | S2AG 数据集许可/商用条件 ⚠ 未核验 | 未核验（部分补充：S2ORC 为 ODC-By 1.0；其余 S2AG 数据集仍未核验） | https://github.com/allenai/s2orc | 2026-09-26 |
| 19 | Quickwit 2025-01-09 宣布改 Apache-2.0（原 AGPL） | 确认（补：实际改许可提交 2025-01-23 #5645；此前 LICENSE.md 为 AGPL） | https://quickwit.io/blog/quickwit-joins-datadog ；https://github.com/quickwit-oss/quickwit/commits/main/LICENSE.md | 2026-09-26 |
| 20 | Meilisearch EE 为 BUSL-1.1（"2025，月份未核验"） | 修正：EE 条款 2025-08-19 入库，博客 2025-08-27，自 v1.19；EE 模块含分片/网络/S3；仅非生产免许可；4 年后转 MIT | https://github.com/meilisearch/meilisearch/blob/main/LICENSE-EE ；https://www.meilisearch.com/blog/enterprise-license | 2026-09-26 |
| 21 | MinerU 3.1.0（2026-04-18）由 AGPLv3 改为 Apache-2.0 + MAU>1 亿/月收入>2,000 万美元阈值 | 确认 + 修正遗漏：GitHub release 为 04-17 UTC；另有"在线服务须显著标注使用 MinerU、违者许可自动终止"条款 | https://github.com/opendatalab/MinerU/blob/master/LICENSE.md ；https://github.com/opendatalab/MinerU/releases/tag/mineru-3.1.0-released | 2026-09-26 |
| 22 | Marker 代码 Apache-2.0、权重修改版 OpenRAIL-M（<500 万美元）；olmOCR-bench balanced 76.0@2.9、fast 66.6@7.4、MinerU 72.7@0.54、Docling 50.3@2.1 | 确认（补：吞吐为单台 B200 并发页/秒） | https://github.com/datalab-to/marker | 2026-09-26 |
| 23 | Chandra 权重 <200 万美元且不得与其 API 竞争 | 确认 + 补充：Chandra 2（2026-03）自报 85.8±0.8；"商用自托管需许可" | https://github.com/datalab-to/chandra | 2026-09-26 |
| 24 | Nougat 代码 MIT、权重 CC-BY-NC；Dolphin 为 Qwen Research License | 确认（补：Dolphin README 徽章写 MIT，与 LICENSE 冲突，按 LICENSE 从严） | https://github.com/facebookresearch/nougat ；https://github.com/bytedance/Dolphin/blob/master/LICENSE | 2026-09-26 |
| 25 | MonkeyOCR 权重许可 ⚠ 未核验 | 修正：v1 权重仅限学术研究与非商用评估，商用/SaaS/再分发需书面许可 → 权重 X | https://github.com/Yuliang-Liu/MonkeyOCR | 2026-09-26 |
| 26 | Zotero 10.0（2026-08-17）本地 API 写入、全文检索提速、嵌套条件组；10.0.4（2026-09-22）；10.0.2 getter 说明 | 确认 | https://www.zotero.org/support/changelog | 2026-09-26 |
| 27 | JabRef 6.0-beta.1 预发布 2026-09-21，稳定版 5.15（2024-07-10）；Kùzu 已归档、最后 v0.11.3（2025-10-10） | 确认 | https://github.com/JabRef/jabref/releases ；https://github.com/kuzudb/kuzu | 2026-09-26 |
| 28 | findpapers：`QueryBuilder` 声明 `_SUPPORTED_FILTERS`，实现 `validate_query`/`convert_query`/可选 `expand_query`；`QueryExecutionPlan`；`FilterPropagator` 最内层过滤码优先、`children_match_filter` | 确认 | https://github.com/jonatasgrosman/findpapers/blob/main/findpapers/query/builder.py ；https://github.com/jonatasgrosman/findpapers/blob/main/findpapers/query/propagator.py | 2026-09-26 |
| 29 | findpapers 子请求"以集合语义（AND=交、OR=并、NOT=差）在本地合并" | 修正：DNF 展开、默认 `q0 OR q1 …`、连接器并集去重；`AND NOT` 不拆分；没有跨请求交/差 | https://github.com/jonatasgrosman/findpapers/blob/main/findpapers/query/builders/openalex.py ；https://github.com/jonatasgrosman/findpapers/blob/main/findpapers/connectors/openalex.py | 2026-09-26 |
| 30 | findpapers 文档仍写 OpenAlex ~10 req/s with email、Crossref polite ~50 req/s；similar 按 S2(all-cs)>PubMed ELink>OpenAlex 优先级并集、不合成分数 | 确认 | https://github.com/jonatasgrosman/findpapers/blob/main/docs/databases.md ；https://github.com/jonatasgrosman/findpapers/blob/main/docs/similar.md | 2026-09-26 |
| 31 | （原文未提）findpapers 的合规风险 | 修正遗漏：`web_scraping` 与下载器用 curl_cffi 冒充 Chrome TLS 指纹绕 WAF，且为 search/snowball/similar 默认富化源 → 组件 X | https://github.com/jonatasgrosman/findpapers/blob/main/findpapers/connectors/web_scraping.py ；https://github.com/jonatasgrosman/findpapers/blob/main/docs/search.md | 2026-09-26 |
| 32 | Asta PaperFinder 冻结快照：结构化对象→执行规划器→意图工作流→LLM 相关性→按附加准则排序；fast ~30s / diligent ~3min；需 OpenAI/S2/Cohere/Google key | 确认（措辞修正为"路由到若干工作流之一"；补：线上版另用公共 API 不可得的数据与索引） | https://github.com/allenai/asta-paper-finder | 2026-09-26 |
| 33 | paper-search-mcp：Sci-Hub 可选且默认关；Scholar 经代理"bypasses bot-detection"；OpenAIRE 403 时以 `Mozilla/5.0` 原始请求重试；IEEE/ACM 有 key 才注册 | 确认 | https://github.com/openags/paper-search-mcp ；https://github.com/openags/paper-search-mcp/blob/main/paper_search_mcp/academic_platforms/openaire.py | 2026-09-26 |
| 34 | zotero-mcp 默认 38 工具 schema 每请求 13,448 tokens，Skill 98 tokens；Zotero 10+ 本地写 | 确认 | https://github.com/54yyyu/zotero-mcp | 2026-09-26 |
| 35 | arxiv-mcp-server 19 工具、HTML 先 PDF 回退、12,000 字符默认截断、已入官方 MCP Registry；"S2 须 key" | 确认；"S2 须 key"修正为可选（无 key 可用至共享配额耗尽） | https://github.com/blazickjp/arxiv-mcp-server | 2026-09-26 |
| 36 | 推荐/推送样本：zotero-arxiv-daily 加权平均相似度（新加入权重高）、默认 jina-embeddings-v5-text-nano、22:00 UTC；daily-paper-reader 多 lane→统一池→Qwen3-Reranker-0.6B→LLM refine、ICML 2026 6,555 篇；papertok 有界时效/影响力与诚实标签；Cool Papers 点 [PDF]/[Kimi] 即星标 | 确认 | https://github.com/TideDra/zotero-arxiv-daily ；https://github.com/ziwenhahaha/daily-paper-reader ；https://github.com/mugar123/papertok ；https://github.com/bojone/papers.cool | 2026-09-26 |
| 37 | PaperFlow 反馈语义（同批未选=弱负、追加只增、`none`、精读=保守正）；"Google Scholar 页面"输入方式 ⚠ 未核验 | 反馈语义确认（出处为 docs/feedback-loop.md）；Scholar 输入修正为"抓取公开 Scholar 主页"→ 组件 X | https://github.com/OpenRaiser/PaperFlow/blob/main/docs/feedback-loop.md ；https://github.com/OpenRaiser/PaperFlow | 2026-09-26 |
| 38 | gpt_academic 部分插件涉 Scholar 抓取（⚠ 未逐插件核验）；paper-search-mcp-nodejs 是否继承 Sci-Hub（⚠） | 修正：gpt_academic 含 Sci-Hub 数据源（20 个镜像）+ Chrome UA 抓 Scholar；nodejs 版含 Sci-Hub（opt-in）与 Scholar/ScrapingAnt → 均为组件 X | https://github.com/binary-husky/gpt_academic/blob/master/crazy_functions/review_fns/data_sources/scihub_source.py ；https://github.com/Dianel555/paper-search-mcp-nodejs | 2026-09-26 |
| 39 | local-deep-research 每用户 SQLCipher（AES-256）、口令派生密钥不存储、无遥测、期刊质量系统 | 确认（补：每用户 LLM key 也存于其加密库） | https://github.com/LearningCircuit/local-deep-research | 2026-09-26 |
| 40 | 多租户积木：Qdrant `is_tenant`、`m:0`+`payload_m:16`、v1.16.0 分层多租户约 2 万点；pgvector 0.8.0 迭代扫描、租户 list 分区；Vespa streaming 45 B/文档、NN 恒精确；Meilisearch tenant token 只约束 search | 确认（补：`is_tenant` 自 v1.11.0；pgvector 0.8.0 发布于 2024-10-30） | https://qdrant.tech/documentation/guides/multitenancy/ ；https://github.com/pgvector/pgvector ；https://docs.vespa.ai/en/performance/streaming-search.html ；https://www.meilisearch.com/docs/learn/security/multitenancy_tenant_tokens | 2026-09-26 |
| 41 | 基础设施许可：Elasticsearch AGPLv3/SSPL/ELv2；FalkorDB SSPL；Memgraph BSL + MEL；ParadeDB AGPL；VectorChord AGPLv3/ELv2 | 确认（补：Elasticsearch `x-pack` 仅 ELv2） | 各仓库 LICENSE 原文（elastic/elasticsearch、FalkorDB/FalkorDB、memgraph/memgraph、paradedb/paradedb、supervc-stack/VectorChord） | 2026-09-26 |
| 42 | GROBID 0.9.1（2026-08-04）、68 标签、参考文献 F1 ~.87（PMC 1,943）/~.90（bioRxiv 2,000，DL）、默认仅 CRF、许可识别；olmOCR-Bench 快照 9 行数值 | 确认 | https://github.com/grobidOrg/grobid ；https://github.com/allenai/olmocr | 2026-09-26 |
| 43 | 论文结论：OpenScholar 4,500 万 OA 论文、ScholarQABench 2,967 查询、GPT-4o 引用幻觉 78–90%、"是否期刊发表 ⚠"；PaSa ACL 2025、RealScholarQuery 50 条、较 PaSa-GPT-4o recall +30.36%/precision +4.25%；Scholar Inbox 80 万评分、代码是否开源 ⚠ | 数值确认；OpenScholar 修正为已发表于 *Nature*（2026-02-04）；Scholar Inbox 补充"未见平台代码、仅开源数据集（774k/556k，许可 ⚠）" | https://arxiv.org/abs/2411.14199 ；https://allenai.org/blog/openscholar-nature ；https://github.com/bytedance/pasa ；https://arxiv.org/abs/2504.08385 ；https://github.com/avg-dev/scholar_inbox_datasets | 2026-09-26 |
| 44 | 表示与分类：Qwen3-Embedding-8B MTEB 多语榜第一（70.58，2025-06-05）；SPECTER2 600 万三元组/23 学科、四类适配器；s2_fos 23 类（权重 ⚠）；OpenReview SPECTER2+SciNCL"hard triples 最好 0.65" | Qwen3、SPECTER2（HF 权重 Apache-2.0）确认；s2_fos 修正为 ImpACT-LR 门控权重；OpenReview 修正为与 SciNCL 并列 0.65 | https://huggingface.co/Qwen/Qwen3-Embedding-8B ；https://github.com/allenai/SPECTER2 ；https://github.com/allenai/s2_fos ；https://github.com/openreview/openreview-expertise | 2026-09-26 |
| 45 | 二级仓储 OAI-PMH：Zenodo `/oai2d`（earliest 2014-02-03）、MIT DSpace `/server/oai/request`、White Rose EPrints `/cgi/oai2`（3.4.6） | 确认（MIT 旧路径 `/oai/request` 会重定向到 `/server/oai/request`） | https://zenodo.org/oai2d?verb=Identify ；https://dspace.mit.edu/server/oai/request?verb=Identify ；https://eprints.whiterose.ac.uk/cgi/oai2?verb=Identify | 2026-09-26 |
| 46 | 其余抽查：NCBI 3/10 req/s（原标 ⚠）；translation-server 默认 Chrome UA；abstracts-search 2 亿+、stella_en_1.5B_v5、CC0、最近同步 2026-03-30；Wispar EZproxy + 可配置滑动手势；"刷论文开源前端均 <100★"（GitHub 10 组检索，最高 arxivtok 91★） | 确认（NCBI 数值由官方博客确认，去掉 ⚠） | https://ncbiinsights.ncbi.nlm.nih.gov/2017/11/02/new-api-keys-for-the-e-utilities/ ；https://github.com/zotero/translation-server ；https://github.com/colonelwatch/abstracts-search ；https://github.com/Scriptbash/Wispar ；GitHub search API | 2026-09-26 |

> 计数口径：第 1 行是批量复测，不计入 44 条；第 2–45 行计 44 条（第 46 行为补充抽查，不计入）。结论栏含"修正"字样者（含"修正措辞""修正遗漏"
> 及确认/修正混合行）计为修正，共 15 条：第 3、9、13、14、17、20、21、25、29、31、35、37、38、43、44 行；第 18 行计为未核验；其余 28 条为确认
> （含"确认 + 补充"）。仍未核验的事项汇总见 §4 第 9 条。
