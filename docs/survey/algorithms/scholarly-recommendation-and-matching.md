---
title: 算法调研：学术论文推荐、用户兴趣建模与双向匹配
status: draft
owner: opus5.5-survey
updated: 2026-09-26
---

# 算法调研：学术论文推荐、用户兴趣建模与双向匹配

> 定位：v2 重新设计（多用户论文发现平台 + 卡片流推荐）调研阶段的**算法子报告**，回答"怎样把论文推荐给对的人、怎样把人和论文/人和人双向匹配、怎样持续学习"。产品/竞品层面见并行调研 [market/startups-and-products.md](../market/startups-and-products.md) [S98]；来源接入、检索索引与路由、社媒推荐机制若有并行专题，以对应专题为准，本文只引用与学术推荐直接相关的部分。
>
> **证据约定**：`[S#]` 指向 §5 参考来源（均含 URL；除另注外访问/核验日期均为 **2026-09-26**）。`[实测]` = 本次直接调用 API / 读取仓库源码或结果文件得到的数据；`⚠ 未核验` = 未能取得一手来源；`估算` = 本文按明示假设推算、非实测。设计片段一律标注"设计伪代码"。

## 0. 结论速览

1. **三个独立的学术推荐系统收敛到同一骨架**：共享的论文表示（TF-IDF 或文献嵌入）+ **每用户一个轻量线性分类器**（arxiv-sanity-lite 的 LinearSVC [S39]、Semantic Scholar Research Feeds 的两个线性 SVM [S40]、Scholar Inbox 的逻辑回归 [S42]）。Scholar Inbox 在 2.3 万注册用户、80 万条公开评分上验证了该骨架 [S42]。这是 v2 R0 阶段最稳妥的起点。
2. **不存在"一个嵌入打天下"**：在 Scholar Inbox 的用户评分评测里 TF-IDF(10k 维) 的 nDCG 最高（88.67），而 GTE-large 的 AUC/平衡准确率最高 [S42]；在 MDCR 引文推荐上 BM25 胜过 SPECTER、SciNCL [S4]；在自然语言文献检索 LitSearch 上稠密检索比 BM25 高 24.8 个 recall@5 点 [S16]。结论：**稀疏 + 稠密双通道融合**（S2 Feeds 正是两个 SVM 取平均 [S40]）。
3. **通用嵌入已在科学检索基准上反超**：MTEB 结果库 [实测] 中 SCIDOCS nDCG@10：Qwen3-Embedding-8B 0.327、-4B 0.314、voyage-3-large 0.272、gemini-embedding-001 0.252、OpenAI text-embedding-3-large 0.231、BM25s 0.158 [S8]。但 MTEB 的 SCIDOCS 是"以论文标题检索其所引论文摘要"的引文预测代理任务 [S8]，不等于个性化推荐效果；SPECTER2 不在该结果库中，无法同表比较。
4. **许可是硬约束**：jina-embeddings-v3/v5 与 NV-Embed-v2 为 CC-BY-NC-4.0，jina-v4 为 Qwen Research License，embeddinggemma 为 Gemma 许可 [S12][S13]；Apache-2.0/MIT 可选项有 Qwen3-Embedding、SPECTER2、SciNCL、BGE-M3、gte-large、e5 系列、nomic 系列 [S4][S6][S10][S11][S13]。**注意 zotero-arxiv-daily 默认模型 jina-v5-text-nano 为非商用许可** [S47][S12]。
5. **OpenAlex 语义检索用的就是 gte-large（1024 维，标题+摘要）** [S48]，Scholar Inbox 也选 GTE-large [S42]。若 v2 本地采用同一模型，可把 OpenAlex `search.semantic` 当作外部候选源并在同一向量空间里重打分——这是本次调研最具可操作性的发现之一。
6. **引文图方法对"新论文"天然偏科**：共被引需要未来的引用，新论文只有参考文献；文献耦合（共享参考文献）对新论文立即可用 [S19][S20]。Connected Papers 与 Litmaps 的公开说明都以共被引 + 文献耦合（及"共享引用与参考"）为核心 [S26][S27]。
7. **协同过滤在学术场景证据偏弱且易放大马太效应**：Beel 等综述 200+ 篇文献中 CF 仅占 18%、CBF 55% [S34]；CiteULike 已于 2019-03 停运（官方宣布 2019-03-30 停止运营，维基百科信息框记为 2019-03-28 起离线；核验修正）[S38]；Scholar Inbox 明确批评 X/ResearchGate/LinkedIn 式推荐偏向热门作者与机构 [S42]。CF 应在 v2 有足够用户后作为**补充信号**引入。
8. **LLM 适合离线/近线增强，不适合在滑动路径上同步排序**：listwise 重排确有增益（RankGPT、LitSearch +4.4）[S52][S16]，但存在位置/流行度偏置 [S53]，且在审稿人专长匹配上 LLM 反而不如专用方法 [S75]。按 2026-09 官方价，"每用户每日一次 30 篇 listwise 重排"约 $0.0006（gpt-5-nano）～$0.011（Claude Haiku 4.5）/用户·日（估算，§2.6.6）。
9. **双向匹配有成熟工具链可复用**：审稿人—论文匹配 = 亲和度（SPECTER2+SciNCL 等集成）+ 带配额的最小费用流/公平分配（OpenReview matcher 的 MinMax/FairFlow/FairSequence 等）[S73][S74]；"论文找读者"可借鉴 SimClusters 的"社区倒排 + 用点赞者兴趣累加更新内容向量" [S87] 与 X 的"新作者曝光提升" [S86]。
10. **兴趣树应以 OpenAlex Topics 为骨架**（4 domains → 26 fields → 252 subfields → 4,516 topics [实测][S48][S49]），再挂接学科原生分类（ACM CCS 2,299 概念、JEL 1,015 码、MSC2020 6,603 码、PhySH 3,882 概念、MeSH 约 3.06 万主题词）[S91–S95]。但 OpenAlex 每篇至多 3 个 topic、约 12% 作品无 topic、且分配有噪声 [S48]，经济学 field 只有 3 个 subfield [实测]——需要本地嵌入映射与 JEL 细化补足。
11. **合规新发现（高优先级）**：`dblp.org`、`dblp.uni-trier.de`、`dblp.dagstuhl.de` 的 robots.txt 于 2026-09-26 均为 `User-agent: * / Disallow: /`，且站点启用 Anubis 反爬挑战 [实测][S61]——与仓库 2026-07-22 勘察（`Crawl-delay: 4`、`Allow: /db,/pid…`）[S97] 冲突，**影响 v1 DBLP adapter 与 v2 的 DBLP 作者档案导入**，需主 agent 立项复核。（核验补充：该 robots.txt 与反爬中间件 Anubis 的默认 `web/static/robots.txt` 逐字节一致（md5 相同），即 Anubis 作者所称的"一键全关"模板；dblp 是否有意禁止一切自动化访问尚无官方说明 ⚠，澄清前按字面执行。合法替代渠道已核实：Dagstuhl DROPS 托管 dblp 月度 XML 快照，CC0 1.0，最新为 2026-09-01 版 [S61]。）

## 1. 调研范围与方法

### 1.1 范围（主题要求 → 本文章节）

| 主题要求 | 章节 |
|---|---|
| 内容表示：TF-IDF/BM25、SPECTER、SPECTER2（adapters）、SciNCL、SciRepEval/SciDocs；通用嵌入（BGE-M3、Qwen3-Embedding、gte、e5、nomic、jina、OpenAI text-embedding-3、voyage）在科学文本上的表现 | §2.2 |
| 引文图方法：共被引、文献耦合、个性化 PageRank、node2vec/GNN、Connected Papers/Litmaps 公开说明 | §2.3 |
| 协同过滤与隐式反馈（CiteULike/Mendeley 时代） | §2.4 |
| 已知系统：arxiv-sanity、S2 Research Feeds、Scholar Inbox、Google Scholar、zotero-arxiv-daily 等 | §2.5 |
| LLM 用法：重排、画像生成、解释、零样本匹配；成本与延迟 | §2.6 |
| 冷启动：种子论文、ORCID/DBLP、Zotero、兴趣标签树 | §2.7 |
| 在线学习与探索：LinUCB、Thompson sampling、偏好漂移 | §2.8 |
| 评估：nDCG/Recall@k、novelty、serendipity、coverage；离线回放 vs 在线 | §2.9 |
| 双向匹配：审稿人—论文、研究者—研究者、论文找读者、稳定匹配与容量约束 | §2.10 |
| 学科分类体系用于兴趣树：OpenAlex Topics、ACM CCS、JEL、MSC2020、PhySH、MeSH | §2.11 |
| 工业界可借鉴点（X/字节/快手等，仅与学术场景直接相关者） | §2.12 |
| 方法对比表（数据需求/效果/成本/可解释性）与分阶段技术路线 | §2.13、§3.2 |

不在本文范围：来源平台接入与名录（sources 专题）、通用检索索引结构与查询路由（检索专题）、前端交互（前端专题）、竞品商业分析（market 专题 [S98]）。

### 1.2 方法与证据分级

- **一手优先**：论文取 arXiv 摘要/HTML/PDF 原文；DOI 经 Crossref/OpenAlex API 核对题名、年份、作者、出处；系统做法优先读**源码与官方文档**（arxiv-sanity-lite、zotero-arxiv-daily、openreview-expertise/matcher、x-algorithm、SimClusters 均直接读仓库文件）。
- **基准数字**：MTEB 分数不看排行榜截图，而是用 `gh api` 直接读 `embeddings-benchmark/results` 仓库里每个模型每个任务的 JSON（记录 mteb_version 与模型 revision；作者自报结果标 †）[S8]。
- **GitHub 元数据**：`gh api repos/OWNER/REPO` 取 star、license、最近 push、是否归档。
- **定价/限额**：只引官方定价页当日内容（OpenAI、Anthropic、Voyage、OpenAlex）[S14][S15][S58][S48]。
- **中文标注**：`[实测]`、`⚠ 未核验`、`估算`、`设计伪代码` 四类标签贯穿全文。

### 1.3 过程记录（可复现）

- **日期**：全部检索、抓取、API 调用均在 2026-09-26 完成。
- **WebSearch**：成功 1 次——检索式 `Semantic Scholar Research Feeds SPECTER embeddings linear classifier user ratings how it works`；第 2 次检索（`OpenAI embeddings model 2026 new release text-embedding pricing per 1M tokens`）因**会话级 WebSearch 配额已耗尽（200/200，工作流内共享）**被拒。此后改用：Hugging Face Papers 检索（HF MCP `search hf://papers`）、GitHub 检索（`gh search repos/code`）、OpenAlex/Crossref API、以及直接访问已知 URL。
- **HF Papers 检索式**：`Editable User Profiles for Controllable Text Recommendation`；`natural language user profiles transparent scrutable recommendation`；`LLM generated user profile recommendation`；`scientific paper recommendation large language model`；`ComLittee literature discovery personal elected author committees`（无结果）；`Aspire multi-vector models textual similarity scientific documents CSFCube`；`reviewer assignment expertise matching large language models`；`personalized arXiv paper recommendation`；`research paper recommendation user feedback dataset`；`NoteLLM retrievable large language model note recommendation`（未命中目标论文，故正文不引 NoteLLM）；`OneRec generative recommender Kuaishou`。
- **WebFetch（摘要/正文）**：arxiv.org/abs/{2004.07180, 2211.13308, 2202.06671, 2504.08385, 2303.16750, 2407.18940, 2305.08845, 2304.09542, 2403.02939, 2304.04250, 2402.15623, 1003.0146, 1907.06902, 2209.07663, 2606.07454, 2605.27865, 2502.07683}；arxiv.org/html/{2504.08385v2, 2301.10140v2}；allenai.org SPECTER2 博客；developers.openai.com（pricing、embeddings guide）；platform.claude.com pricing；docs.voyageai.com pricing；info.orcid.org Public API；zotero.org Web API v3；en.wikipedia.org（ACM CCS、CiteULike）。**失败**：`www.acm.org/publications/class-2012`（Cloudflare 403，未尝试绕过）、`www.apa.org/.../class-codes`（仅返回 212 字节）、`link.springer.com`（WebFetch 跳转鉴权，改用 curl 读公开摘要）。
- **curl（公开页面/文件，读取后仅存于临时目录）**：connectedpapers.com 前端 bundle 中的 About 文案；docs.litmaps.com 两篇帮助文章；Springer 两篇摘要；TPMS、CTR、SPECTER 三篇 PDF 全文；aeaweb.org JEL XML；msc2020.org CSV；NLM MeSH 首页/介绍页 + `id.nlm.nih.gov/mesh/sparql` 计数查询；dblp 三域名与 drops.dagstuhl.de 的 robots.txt；pub.orcid.org 测试记录与 robots.txt；scholar.googleblog.com 4 篇博文；help.openalex.org 的 `llms.txt` 与 6 个 markdown 页；api.openalex.org 计数查询（每次约 $0.0001）；api.crossref.org 与 api.openalex.org 的 DOI 核对；api.semanticscholar.org 的 recommendations/graph swagger 与 datasets 最新 release。
- **gh api（仓库文件）**：`karpathy/arxiv-sanity-lite/{serve.py,compute.py}`、`TideDra/zotero-arxiv-daily/{README.md,src/zotero_arxiv_daily/reranker/base.py}`、`openreview/openreview-expertise` 与 `openreview-matcher` README、`xai-org/x-algorithm` README、`twitter/the-algorithm/src/scala/com/twitter/simclusters_v2/README.md`、`embeddings-benchmark/results/results/<model>/<rev>/<task>.json`（24 个模型 × 8 个科学相关任务）、`cli99/acm-ccs` SKOS、`physh-org/PhySH`、`malteos/scincl` README、`allenai/scidocs` README、`allenai/asta-paper-finder` README。
- **HF MCP**：`allenai/specter2`、`Qwen/Qwen3-Embedding-8B`、`jinaai/jina-embeddings-v5-text-{small,nano}`、`jinaai/jina-embeddings-v4`、`malteos/scincl` 等模型卡；`hub_repo_details` 批量读许可；`stat hf://papers/<arXiv id>` 核对论文存在。
- **其他**：`gh search repos inciteful`（Inciteful 前端仓库的 About/FAQ 未给出算法细节，正文不引用）；`gh search code ACMComputingClassificationSystemSKOSTaxonomy`（定位 ACM CCS SKOS 镜像）；Crossref 公共池在连续核对时返回 429，随即放慢节奏并改用 OpenAlex 单实体查询（免费）核对剩余 DOI。
- **复现片段**（MTEB 科学任务分数）：`gh api -H "Accept: application/vnd.github.raw" repos/embeddings-benchmark/results/contents/results/Qwen__Qwen3-Embedding-8B/<rev>/SCIDOCS.json` → 读 `scores.test[0].main_score`。

### 1.4 与仓库既有文档的关系

- v1 的"推荐"只有订阅 DSL + 本地过滤 + 日报（[design/09](../../archive-v1.md#docs-design-09-search-filter-md)），§6 第 4 条"噪声反馈回路"是唯一的反馈设想 [S97]；本文从算法层补齐 v2 需要的个性化、反馈学习与匹配。
- [research/github-similar-projects.md](../../archive-v1.md#docs-research-github-similar-projects-md) 已从"增量订阅工程"角度记录 arxiv-sanity-lite [S97]；本文补充其**算法细节**（TF-IDF 配置、每查询 SVM、可解释权重）。
- [research/site-survey/metadata-apis.md](../../archive-v1.md#docs-research-site-survey-metadata-apis-md) 记录了 S2 `/recommendations/v1`、OpenAlex 计费制 [S97]；本文补充 2026-09 的 OpenAlex 语义检索、Topics 文档与 S2 推荐 API 参数。

## 2. 主体内容

### 2.1 问题建模：v2 里的四类匹配任务与信号

| 任务 | 方向 | 典型问题 | 主要约束 |
|---|---|---|---|
| T1 用户找论文 | user → paper | 卡片流排序、个性化检索、"相似论文" | 每用户每日卡片预算；新鲜度；多兴趣 |
| T2 论文找读者 | paper → user | 新论文到达时路由给最可能感兴趣的人（推送/次日卡片流） | 用户侧容量（不刷屏）；论文侧曝光下限（新作者/冷门领域不被淹没） |
| T3 人与人 | user ↔ user | 同行/合作者/同好推荐（互惠） | 双方意愿（opt-in）；隐私 |
| T4 带容量分配 | group ↔ paper | 读书会分配、审稿式指派、曝光预算分配 | 硬配额、冲突回避、公平性 |

**反馈信号分层**（按可信度由高到低；映射权重属设计参数、需实验标定）：

| 类别 | 信号 | 用途 | 依据 |
|---|---|---|---|
| 显式正 | 收藏/加入合集、点赞、高评分、正向评论 | 正样本（权重高） | Scholar Inbox 以显式 up/down 票训练 [S42] |
| 显式负 | 左滑/"不感兴趣"、低评分、"少推此类" | 负样本（与随机负例分权） | Scholar Inbox：显式负例权重 V 从 0→0.9，显式负例特异度 68%→78% [S42]；S2 Feeds 随机负例降权 [S40] |
| 隐式 | 展开摘要、打开原文/PDF、停留时长、分享、导出 BibTeX | 弱正样本/多目标预测 | X 将 favorite/reply/dwell/click 等多动作分别预测再加权 [S86]；Beel & Langer 讨论 click-through、link-through、cite-through 指标 [S35] |
| 隐式负 | 快速划过（not dwelled）、静音作者 | 弱负样本 | X 的 negative actions 含 not interested、mute、block、report、not dwelled [S86] |

手势语义（哪一侧滑动代表"喜欢/不喜欢"）以前端专题定义为准，本文只要求它们映射到上表的正/负类别。**评分与留言的算法用法**（设计建议）：①1–5 星评分按有序标签使用——高分并入正例、低分并入显式负例、中间分只作弱信号或不入模，避免把"读过但一般"当成负例；②留言文本经用户同意后可作为该用户私有画像的补充证据（嵌入后并入长期画像），公开留言属用户生成内容，需审核并与排序解耦（参照 X"排序与可见性分离" [S86]）；③"赞/踩"是最高性价比的信号——Scholar Inbox 的全部模型只靠显式赞/踩训练 [S42]。

### 2.2 内容表示

#### 2.2.1 稀疏词法表示（TF-IDF / BM25）

BM25 的理论基础是概率相关框架 [S18]；以下为它（及 TF-IDF）在学术推荐/检索中的实证表现。

| 证据 | 结论要点 |
|---|---|
| Beel 等综述（>200 篇、16 年）：CBF 占 55%，TF-IDF 是最常用加权方案；81% 的方法忽略用户建模 [S34] | 学术推荐长期以文本相似为主，但"用户建模"才是短板 |
| arxiv-sanity-lite：`TfidfVectorizer(ngram_range=(1,2), max_features=20000, sublinear_tf=True, norm='l2', min_df=5, max_df=0.1, stop_words='english')` [实测][S39] | 极简配置即可支撑一个广泛使用的推荐器 |
| S2 Research Feeds：每用户同时训练 TF-IDF 线性 SVM 与 SPECTER 线性 SVM，取两者分数平均 [S40] | 工业系统本身就是稀疏 + 稠密融合 |
| Scholar Inbox 表 2：TF-IDF(10k 维) nDCG 88.67 为最高；PCA 到 256 维后降至 83.37；AUC 84.41 低于 GTE-large 的 86.75 [S42] | 稀疏表示在"正例 vs 随机负例"排序上很强，在显式负例区分上弱 |
| Stelmakh 等审稿人金标准：给定全文时经典 TF-IDF 与 SPECTER2 表现相当 [S75] | 长文本下词法方法不落后 |
| SPECTER2 模型卡 MDCR 结果：BM25 (MAP 33.7) > SPECTER (30.6)、SciNCL (32.6)；SPECTER2 (38.4) 最好 [S4] | 早期科学嵌入并不稳胜 BM25 |
| LitSearch（597 条 ML/NLP 自然语言检索式）：稠密检索器比 BM25 高 24.8 个 recall@5 点 [S16] | 面向自然语言查询时稠密显著更强 |
| MTEB SCIDOCS：BM25s 0.158 vs Qwen3-Embedding-8B 0.327 [实测][S8]；BRIGHT-Pro（经济/心理/生物）BM25s 0.223/0.171/0.194 反而高于 BGE-M3 0.170/0.148/0.139 [实测][S8][S17] | 结论依任务而变，需融合 |

**对 v2 的含义**：v1 已有 SQLite FTS5（内置 BM25）[S97]，稀疏通道几乎零成本可得；它同时是可解释性的来源（arxiv-sanity 直接展示 SVM 正负权重最大的词 [S39]）。

#### 2.2.2 科学文献专用嵌入：SPECTER → SciNCL → SPECTER2

| 模型 | 训练信号 | 结构 | 许可 | 关键结果 |
|---|---|---|---|---|
| SPECTER（ACL 2020）[S1] | 引文三元组 triplet margin loss（查询论文、被查询引用的正例、"被正例引用但未被查询引用"的难负例）[S1][S73] | SciBERT，标题+摘要，[CLS] 向量 | Apache-2.0（`allenai/specter`，593★，最近 push 2023-06-12）[实测] | SciDocs 平均 80.0 [S6]；线上 A/B：替代基于文本相似的"相似论文"排序，4,113 次点击上 CTR +46.5% [S1] |
| SciNCL（EMNLP 2022）[S6] | 在引文图嵌入空间做**受控近邻采样**产生正负例（连续相似度、难负例、正负间隔） | SciBERT 初始化；S2ORC 引文图 | MIT（`malteos/scincl`，80★）[实测] | SciDocs 平均 81.8（10 seed）[S6]；另有 PubMedNCL 面向生物医学 [S6] |
| SPECTER2（SciRepEval，EMNLP 2023）[S3][S4] | 先在 >600 万引文三元组上训练基座，再在 8 个大规模任务上训练**任务格式适配器** | `specter2_base` + adapters：proximity（=`allenai/specter2`，论文↔论文）、adhoc_query（短查询）、classification、regression [S4] | Apache-2.0 [S4] | SciRepEval 平均 71.1（SPECTER 67.5、SciNCL 68.8、SPECTER2 base 69.1）；MDCR MAP 38.4 [S4]；训练覆盖 23 个学科领域 [S5] |
| Aspire [S7] | 共被引作监督的多向量（aspect）匹配，最优传输对齐 | 多向量 | — | 面向细粒度相似；适合"按方面"匹配（⚠ 本文未取其数值） |

**两个基准**：
- **SciDocs**：7 个任务——MAG、MeSH 分类（F1），co-view、co-read、cite、co-cite（MAP/nDCG），recomm（adj-nDCG、adj-P@1）[S2]。S2 团队自 2022-12 起建议改用 SciRepEval [S2]。
- **SciRepEval**：24 个任务、4 种格式（分类、回归、邻近/排序、检索）[S3]。

**一个被低估的事实**：SciDocs 的 `recomm` 任务来自某公开学术搜索引擎的 2.2 万次点击日志（SPECTER 论文原文；SciDocs README 勘误称论文所列该任务训练样本数 20K 有误、应为 4K [S2]），嵌入只是生产排序器的一个特征 [S1]。所有方法在该任务上几乎持平：随机嵌入 51.3、Doc2Vec 51.7 [S1]，最高的 SciNCL（无泄漏训练）为 54.3 nDCG [S6]（核验修正：原文把两处数字都归到 [S6]）；SPECTER 论文也指出"嵌入变体对整体表现影响的机会更小" [S1]。**含义：个性化效果的主要杠杆在用户建模与反馈，而不只是换嵌入**——与 Beel 综述"81% 忽略用户建模"的判断一致 [S34]。

另：图方法 SGC 在 cite 任务 MAP 91.6，高于 SPECTER 88.3，但 co-view MAP 77.2 低于 SPECTER 83.6 [S6]——**引文结构擅长"引用类"相关，文本擅长"用户行为类"相关**。

S2 已提供预计算向量：Datasets 最新 release（2026-09-22）含 `embeddings-specter_v1`、`embeddings-specter_v2`、`tldrs`、`abstracts`、`citations` 等；Graph API 支持 `fields=embedding.specter_v2` [实测][S41]。（核验补充：该 release 各数据集 README 标注 `embeddings-specter_v1/v2` 为 Apache-2.0，`papers`、`abstracts`、`tldrs`、`citations`、`s2orc` 等为 ODC-BY；全量下载需 API key，并受 S2 API License Agreement（2023-05-17 版）约束——须署名"Semantic Scholar"，不得转售或再许可 API 本身 [S41]。摘要文本本身的版权与展示条款仍见 §4 第 3 条 ⚠。）

#### 2.2.3 通用嵌入模型在科学文本上的表现（MTEB 结果库直读）

基准框架见 MTEB/MMTEB [S9]。`main_score` 为 MTEB 默认主指标（检索类为 nDCG@10；SciDocsRR 为重排主指标；ArXivHierarchicalClusteringP2P 为聚类主指标）。SCIDOCS 的任务定义（mteb 源码）：查询为论文标题、目标为其所引论文的摘要，主指标 nDCG@10，数据许可 CC-BY-SA-4.0 [S8]。† = 模型作者自报（results 库中 revision 标 `external`）；◇ = 结果库旧格式文件（无 `mteb_version` 字段、来源未标注，核验补充）；— = 结果库无该任务文件 [实测][S8]。

| 模型 | SCIDOCS | SciFact | SciDocsRR | ArXiv 层级聚类 | 许可 | 规模 / 维度 / 上下文 |
|---|---|---|---|---|---|---|
| Qwen3-Embedding-8B | **0.327** | 0.785 | **0.902** | 0.649 | Apache-2.0 | 8B / ≤4096（MRL 32–4096）/ 32K [S10] |
| Qwen3-Embedding-4B | 0.314 | 0.783 | 0.894 | 0.648 | Apache-2.0 | 4B / ≤2560 / 32K [S10] |
| voyage-3-large | 0.272 | — | — | — | 商用 API | $0.18/1M tok [S15] |
| gemini-embedding-001 | 0.252 | — | — | 0.649 | 商用 API | 定价未核 ⚠ |
| Qwen3-Embedding-0.6B | 0.244 | 0.697 | 0.868 | 0.637 | Apache-2.0 | 0.6B / ≤1024 / 32K [S10] |
| gte-Qwen2-7B-instruct | 0.235 | 0.791† | 0.891† | **0.682** | Apache-2.0 | 7.6B [S13] |
| gte-large（thenlper） | 0.234† | 0.743† | 0.872† | 0.586 | MIT | 1024 维；仅英文；512 token [S13] |
| OpenAI text-embedding-3-large | 0.231 | 0.778◇ | 0.867◇ | 0.595 | 商用 API | 3072 维，可截短；$0.13/1M tok [S14] |
| jina-embeddings-v5-text-small | 0.230 | 0.765 | — | 0.658 | **CC-BY-NC-4.0** | 677M / 1024 / 32K（2026-02-18 发布）[S12] |
| jina-embeddings-v5-text-nano | 0.226 | 0.758 | — | 0.650 | **CC-BY-NC-4.0** | 239M [S12] |
| NV-Embed-v2 | 0.219† | **0.801** | 0.876† | 0.603 | **CC-BY-NC-4.0** | 7.9B [S13] |
| jina-embeddings-v4 | 0.215 | 0.761 | — | — | **Qwen Research License** | 3.75B [S12] |
| voyage-3.5 | 0.213 | — | — | 0.560 | 商用 API | $0.06/1M tok [S15] |
| snowflake-arctic-embed-l-v2.0 | 0.203 | 0.709 | 0.798 | 0.572 | Apache-2.0 | [S13] |
| jina-embeddings-v3 | 0.199 | 0.725 | 0.849† | 0.589 | **CC-BY-NC-4.0** | 572M [S12] |
| nomic-embed-text-v2-moe | 0.193 | — | — | 0.597 | Apache-2.0 | 475M [S13] |
| multilingual-e5-large-instruct | 0.192 | 0.716 | 0.858 | 0.625 | MIT | 560M [S13] |
| embeddinggemma-300m | 0.184 | — | — | 0.636 | **Gemma 许可（gated）** | 303M [S13] |
| nomic-embed-text-v1.5 | 0.176 | 0.703† | 0.806† | 0.601 | Apache-2.0 | 137M [S13] |
| BGE-M3 | 0.163 | 0.644 | — | 0.528 | MIT | 稠密+稀疏+多向量；8,192 token；100+ 语言 [S11] |
| e5-mistral-7b-instruct | 0.163 | 0.764 | 0.863 | 0.653 | MIT | 7.1B [S13] |
| OpenAI text-embedding-3-small | — | — | — | 0.579 | 商用 API | 1536 维；$0.02/1M tok [S14] |
| BM25s（MTEB 基线） | 0.158 | 0.687 | 0.421‡ | — | — | ‡ 基线实现差异大，慎比较 |

补充事实：
- Qwen3-Embedding-8B 在 2025-06-05 时位列 MTEB 多语言榜第 1（70.58）；指令感知，官方称使用任务指令一般提升 1%–5% [S10]。2026-09 的榜单名次未核验 ⚠。
- jina-v5-text 系列由 Qwen3-Embedding-4B 蒸馏而来；small 自报 MTEB 英文 v2 71.7、MMTEB 67.7 [S12]。
- OpenAI 官方给出的 MTEB 平均：text-embedding-3-small 62.3%、-3-large 64.6%；`dimensions` 参数可截短，3-large 截到 256 维仍优于 1536 维的 ada-002 [S14]。
- Voyage 当前系列 voyage-4-large/4/4-lite 定价 $0.12/$0.06/$0.02 每百万 token，各含 2 亿免费 token [S15]；结果库暂无 voyage-4 的科学任务分数 [实测]。
- 推理型检索（BRIGHT-Pro，StackExchange 问题，ACL 2026）：Qwen3-Embedding-8B 在经济/心理/生物 nDCG@10 为 0.366/0.385/0.436，gte-Qwen2-7B 生物达 0.509 [实测][S8][S17]——对"用长段自然语言描述兴趣"的查询形态有参考意义。
- **直接的个性化评测**（Scholar Inbox，逻辑回归 + 256 维 PCA）：GTE-large F1 84.51 / nDCG 85.83 / 平衡准确率 78.31 / AUC 86.75；GTE-base 84.16/85.42/77.92/86.24；SPECTER2 83.22/84.21/78.16/86.36 [S42]。作者因"显式评分更可靠"最终选 GTE-large，并发现稠密嵌入的余弦更"校准"、利于相似论文检索与 2D 科学地图 [S42]。

#### 2.2.4 小结：表示层选型矩阵

| 需求 | 首选 | 备选 | 理由 |
|---|---|---|---|
| 英文论文↔论文、每用户分类器特征 | gte-large（MIT）或 SPECTER2 proximity（Apache-2.0） | Qwen3-Embedding-0.6B | gte-large 与 OpenAlex 语义检索同空间 [S48]、Scholar Inbox 实证最好 [S42]；SPECTER2 为科学专用、S2 提供现成向量 [S41] |
| 中文/多语查询、长文本、指令式兴趣描述 | Qwen3-Embedding-0.6B/4B（Apache-2.0，32K） | BGE-M3（MIT，8K，自带稀疏） | 科学任务分数领先且许可友好 [S8][S10][S11] |
| 词法/可解释通道 | SQLite FTS5 BM25 + TF-IDF 特征 | — | 零成本、可解释 [S39][S40][S42] |
| 托管 API（不自建 GPU） | text-embedding-3-small / voyage-4-lite（$0.02/1M） | voyage-3-large（科学检索较好） | 成本见 §2.6.6 [S14][S15] |
| 避免 | CC-BY-NC / 研究许可模型用于可能商用的多用户平台 | — | jina v3/v4/v5、NV-Embed-v2、embeddinggemma 的许可限制 [S12][S13] |

### 2.3 引文图方法

| 方法 | 定义 / 做法 | 对新论文 | 数据来源（v2 可得性） | 依据 |
|---|---|---|---|---|
| 共被引 co-citation | A、B 同被第三篇 C 引用的次数 | 差：新论文尚无施引文献 | 需要"谁引了谁"全量：OpenAlex 快照（免费、季度）或 API | Small 1973 [S19] |
| 文献耦合 bibliographic coupling | A、B 共享参考文献的数量 | **好**：新论文有参考文献即可计算 | OpenAlex 作品记录含 `referenced_works` [实测][S48] | Kessler 1963 [S20] |
| 个性化 PageRank / 带重启随机游走 | 以用户种子论文为重启分布在引文/作者/venue 图上游走 | 中：依赖新论文的出边 | 本地子图 | Haveliwala 2002 [S21]；Pixie 在 30 亿节点、170 亿边图上实时游走，单机 1,200 请求/秒、60 ms，贡献 Pinterest 80% 以上互动 [S22] |
| node2vec | 有偏随机游走 + skip-gram 学节点向量 | 差（需重训/增量） | 本地图 | [S23] |
| GNN（PinSage、LightGCN） | 图卷积聚合邻居 + 特征 | 中（PinSage 可用内容特征） | 需大规模交互图 | PinSage 在 30 亿节点/170 亿边上部署 [S24]；LightGCN [S25] |
| Connected Papers | 每张图分析约 5 万篇论文，选出与源论文联系最强的几十篇；相似度基于**共被引 + 文献耦合**；力导向布局；数据来自 S2 语料（ODC-BY）；"Prior works"=图中论文最常引用者，"Derivative works"=引用了图中很多论文者 | — | — | [S26] |
| Litmaps | 三种算法：Shared Citations & References（默认；单输入时取其引用、参考与共被引中连接最密者）、Common Authors、Similar Text（标题摘要语义，唯一不用引文的算法）；库容 2.7 亿+，数据来自 Crossref、Semantic Scholar、OpenAlex，称"法律上只能索引开放元数据" | — | — | [S27] |
| OpenAlex `related_works` | "与本文共享 topic 最多的近期论文" | 好 | 单条查询免费 | [S48] |
| Google Scholar | 推荐模型纳入引文图（2012、2021 两篇官方博文） | — | 不可自动化 | [S43][S45] |

**要点**：引文信号在"找经典/找脉络"（探索页、Connected-Papers 式图谱）上价值最高；在"每日新论文"卡片流里，只有文献耦合与"引用了用户库中论文"（`referenced_works ∩ 用户收藏`）可即时使用。

### 2.4 协同过滤与隐式反馈（CiteULike / Mendeley 时代）

| 工作 | 做法 | 数据 / 结果 | 依据 |
|---|---|---|---|
| CTR（Wang & Blei, KDD 2011） | LDA 主题 + 矩阵分解耦合；区分 in-matrix（有人收藏过的旧文）与 out-of-matrix（全新论文）预测 | CiteULike：5,551 用户、16,980 篇、204,986 个用户-文章对，稀疏度 99.8%，人均 37 篇；纯 CF 不能做 out-of-matrix | [S28] |
| CDL（KDD 2015） | 深度内容表示 + CF | CiteULike 系列数据 | [S29] |
| WRMF / 隐式 ALS（ICDM 2008） | 置信度加权的隐式反馈矩阵分解 | 经典基线 | [S30] |
| EASE（WWW 2019） | 闭式解线性 item-item 模型 | 经典强基线 | [S31] |
| 复现性警示 | 18 个神经推荐算法中仅 7 个可合理复现，其中 6 个常被简单的近邻/图启发式击败 | — | [S32] |
| 点积 vs MLP | 精调的点积（MF）优于 NCF 的 MLP 相似度 | — | [S33] |
| Beel 等综述 | CBF 55%、CF 18%、图方法 16%；评估常基于强剪枝数据集、用户研究样本小 | — | [S34] |
| Mendeley（Hristakeva 等, 2017） | 摘要指出既有学术推荐"主要是基于引文网络或文本相似的 item-to-item 推荐"；个性化方案细节因全文闭源未能核验 ⚠ | — | [S36] |
| Kreutz & Schenkel 2022 | 系统综述 2019-01 至 2021-10 的论文推荐工作（方法、数据集、评估、挑战） | — | [S37] |
| 现状 | CiteULike 已于 2019-03 停运（宣布 2019-03-30 停止运营，信息框记 2019-03-28 起离线）[S38]；当前最大的公开显式评分数据是 Scholar Inbox 的 80 万条（1.43 万用户），数据集仓库 LICENSE 为 **CC BY-NC-ND 4.0**（GitHub API 未能自动识别，故显示 NOASSERTION；核验修正）[S42] | — | — |

**对 v2 的含义**：①新论文永远是 out-of-matrix，内容通道不可缺；②CF 的价值在"同领域研究者的收藏"作为社会证据与探索来源，但需去流行度偏置；③起步期用户少，CF 模型应从 item-kNN/EASE 这类简单强基线开始 [S31][S32]。

### 2.5 已知系统做法拆解

| 系统 | 输入/反馈 | 表示 | 用户模型 | 候选生成 | 排序/解释 | 冷启动 | 依据 |
|---|---|---|---|---|---|---|---|
| arxiv-sanity-lite（1,696★，MIT，最近 push 2023-06） | 用户给论文打标签（tag） | TF-IDF 1-2gram 2 万维 | **每次查询现训** `LinearSVC(class_weight='balanced', C=0.01)`：标签内论文为正，库内其余全部为负（exemplar 式） | 全库 | SVM 决策值；页面展示正权重前 40 与负权重后 20 的词作为解释 | 从单篇论文出发（pid 作正例） | [实测][S39] |
| S2 Research Feeds | 用户正/负标注 | TF-IDF + SPECTER | 两个线性 SVM；负标注补充低权重随机负例 | FAISS 近似 kNN：近 60 天约 100 万篇论文的 SPECTER 向量（每晚刷新），取正例**质心**附近约 500 篇 | 两 SVM 分数平均 | 种子论文 | [S40] |
| S2 Recommendations API | 正/负论文 ID 列表 | — | — | `POST /recommendations/v1/papers/`（`positivePaperIds`、`negativePaperIds`）；`GET /recommendations/v1/papers/forpaper/{paper_id}?from=recent\|all-cs`；`limit` 默认 100、上限 500 | — | 单篇或多篇种子 | [实测][S41]；API key 入门限速 1 RPS（全端点），无 key 请求共享全体未认证用户的 1000 RPS 池（官方 API 页 2026-09-26 复核）[S41] |
| Scholar Inbox（Tübingen，arXiv 2025） | 显式赞/踩 | GTE-large → PCA 256 维 | **每用户逻辑回归**，加权 BCE；每用户 5k 随机负例；超参 (C, V, S)，标准配置 C=0.1、V=0.8、S=5.0；每次评分后重训 | 每日新论文（arXiv、bioRxiv、chemRxiv、medRxiv、会议论文集；S2ORC 补元数据） | 相关度映射到 [-100,100] 显示；移动端高亮与论文主旨最相关的一句；赞/踩、收藏、相似论文按钮 | Scholar Maps（300 万篇 t-SNE 图，Qwen 生成 4 级标签）选种子 + 主动学习（在决策边界附近及以上分层采样） | [S42] |
| Google Scholar | 用户自己 Scholar 档案里的论文 | — | "统计模型"：论文主题、发表场所、合作者与所引作者、同领域作者、引文图、兴趣随时间变化 | 全网新文章 | 按日期组织；手机端可滑动浏览摘要并存入 Library；邮件订阅 | 建公开档案即可；2017 起可"关注某学者的相关研究"（如导师） | [S43][S44][S45] |
| Google Scholar Quick Read（2026-08） | 查询 | LLM | — | — | 针对查询生成 Answers/Approach/Considerations；仅对用户有权访问的论文提供，并与出版社合作开放订阅文章 | — | [S46] |
| zotero-arxiv-daily（5,991★，AGPL-3.0，最近 push 2026-09-01） | 用户 Zotero 库 | 本地嵌入（默认 `jinaai/jina-embeddings-v5-text-nano`）或 API（如 text-embedding-3-large） | 无训练：候选与库内每篇的相似度加权平均，库按加入时间倒序、权重 `w_i = 1/(1+log10(i+1))` 归一化，分数 ×10 | 前一日 arXiv/bioRxiv/medRxiv/chemRxiv 新文 | LLM 生成 TL;DR（全文经 pymupdf4llm） | Zotero 库即种子 | [实测][S47] |
| OpenAlex 语义检索 | 自然语言/摘要（≤2,000 字符） | gte-large 1024 维（标题+摘要） | — | 余弦最近邻，每次最多 50 条，1 req/s，$1/千次 | — | — | [S48] |
| Asta Paper Finder（Ai2） | 自然语言检索式 | 多检索通道 | — | LLM 分析查询→结构化→规划器路由到不同工作流 | LLM 逐条判定摘要/片段相关性；fast 约 30 秒、diligent 约 3 分钟 | — | [S50] |
| PaperFlow（arXiv 2026-06，研究原型） | 异构冷启动证据 + 语义不同的反馈 | — | 可检视的结构化学者画像（Profiling）→ 固定展示预算下多信号聚合排序（Recommending）→ 按反馈更新状态（Adapting） | 按日论文流 | — | — | 基准：24 名模拟用户、50 天、1,200 个用户日、20,727 篇 [S51] |
| X For You（参照系，非学术） | 多动作行为序列 | Phoenix（Transformer）+ 哈希嵌入 | 预测 P(favorite)、P(reply)、P(dwell)…与负向动作 | in-network（Thunder）+ out-of-network（Phoenix 检索、SimClusters） | `Σ w_i·P(action_i)`；作者多样性衰减、站外折扣、新作者提升；候选间互不注意力（分数可缓存）；排序与可见性过滤分离 | 新帖哈希嵌入即刻可表示 | [实测][S86] |

**共性**：①都是"候选池（时间窗）→ 个性化打分 → 预算内展示"的三段式；②个性化模型要么是每用户线性模型，要么是无参数的加权相似度；③解释多为"特征级"（词、相似论文、句子高亮），而非生成式。

### 2.6 LLM 在推荐中的用法

#### 2.6.1 LLM 重排（rerank）

- **RankGPT**（EMNLP 2023）：listwise 排列生成 + 滑动窗口；GPT-4 在 TREC/BEIR 上优于监督式 monoT5；蒸馏得到的 4.4 亿参数模型在 BEIR 上胜过 30 亿参数监督模型 [S52]。
- **LitSearch**：在最强稠密检索器之上，LLM 重排再提升 4.4%（原文表述）[S16]。
- **LLMRank**（ECIR 2024）：LLM 可作零样本推荐排序器，但难以感知历史交互顺序，并受**流行度偏置与候选位置偏置**影响；特制提示与 bootstrapping 可缓解；候选来自多个召回源时可与传统模型相当 [S53]。
- **MERIT**（EMNLP 2026）：用 LLM 裁判按论文专属专长量表给 RL 训练的 4B 评估器打奖励，再蒸馏为嵌入检索器；在 LR-Bench 与 CMU Gold 数据集上达到 SOTA [S77]——"**LLM 做老师、小模型上线**"的范式。

#### 2.6.2 LLM 生成/维护用户画像

- **LFM**（Zhou、Dai、Joachims，WSDM 2024 workshop）：LLM 编码器把评分历史压成简短自然语言画像，LLM 解码器据此预测；实验在 MovieLens（电影评分，非学术场景）上进行，冷启动设置下准确率可高于矩阵分解，紧凑画像常与直接喂全量历史持平或更好，且可解释、输入更短 [S55]（核验修正：补充数据集与"可高于"的限定）。
- **LACE**（SIGIR 2023）：以检索得到的可读"概念"集合表示用户，用户可直接编辑画像；在 3 类任务、6 个数据集的暖启动/冷启动/零样本设置下验证，用户研究显示编辑画像能提升推荐质量 [S56]。
- **PaperFlow**（2026）：强调"结构化、可检视"的学者画像与"语义不同的反馈信号"分别更新 [S51]。
- 相关后续（仅题录与摘要级核验）：LangPTune（端到端训练语言画像）、SteerEval（2026-01，评估自然语言画像的可操控性）、LettinGo、PURE [S57]。

#### 2.6.3 解释生成

- **PaperWeaver**（CHI 2024）：LLM 从用户已收集论文中抽取语境化方面，把新推荐论文与之对照生成个性化描述；15 人用户研究中，比"展示推荐论文的相关工作段落"更能帮助理解相关性、更自信地分拣 [S54]。
- **Scholar Inbox**：移动端高亮"与论文主旨最相关的一句"以加速浏览 [S42]（非生成式，成本近零）。
- **Google Scholar Quick Read**：面向查询的结构化速读，仅限用户有权访问的论文 [S46]——与本项目"auth-gated 全文不跨用户共享"的红线同向。

#### 2.6.4 零样本兴趣/专长匹配：谨慎

- 审稿人金标准（58 位研究者、477 条专长自评）：所有算法都有显著误差，易例误排率 12%–30%、难例 36%–43%；**标题+摘要时 SPECTER2 最好，LLM 表现不如专用方法** [S75]。
- 含义：LLM 不宜直接当主匹配器；更适合作为（a）离线标注/裁判、（b）小范围 top-K 重排、（c）画像与解释的生成器。

#### 2.6.5 延迟

- Agentic 检索：Asta Paper Finder fast 模式约 30 秒、diligent 约 3 分钟 [S50]；
- 结论：LLM 调用应放在**离线（每日批）或近线（后台预取下一批卡片）**，卡片流的滑动路径上只做已缓存结果的读取与轻量重排。

#### 2.6.6 成本估算（按 2026-09-26 官方价）

价格依据 [S14][S58]：gpt-5-nano $0.05/$0.40（批处理 $0.025/$0.20）、gpt-5-mini $0.25/$2.00（批 $0.125/$1.00）、Claude Haiku 4.5 $1/$5（批 $0.50/$2.50）、Claude Sonnet 5 $2/$10（批 $1/$5；官方脚注称该价原为截至 2026-08-31 的引入价，现已转为标准价，原定 2026-09-01 涨至 $3/$15 取消，核验补充），单位为每百万输入/输出 token；Anthropic 缓存命中按 0.1× 输入价计 [S58]；官方说明 Claude 4.7 及以后模型使用新分词器，同文本约多 30% token [S58]（Sonnet 5 属其后发布的模型，下表按 ×1.3 估算；实际以 `count_tokens` 实测为准 ⚠）。嵌入：text-embedding-3-small $0.02、-3-large $0.13 [S14]；voyage-4-lite $0.02、voyage-4 $0.06 [S15]。

**假设（估算）**：每张论文卡片文本（标题+截断摘要）≈300 token；用户画像摘要≈300 token；指令≈200 token；每日新论文 ≈2.5 万篇（依据：OpenAlex 2026-08 出版日期内 type 为 article 或 preprint 的作品 710,965 篇 ÷ 31 天 ≈ 2.3 万/日，向上取整；同月 arXiv 来源（OpenAlex source S4306400194）作品 30,163 篇；因索引滞后这些计数仍会上升）[实测][S49]。

| 场景（估算；格式：每用户·日成本；每千 DAU·月成本） | gpt-5-nano | gpt-5-mini | Claude Haiku 4.5 | Claude Sonnet 5 |
|---|---|---|---|---|
| L1 每用户每日一次 listwise 重排 30 篇（输入 9,500 / 输出 300 token） | $0.0006；≈ $18（批 ≈ $9） | $0.0030；≈ $89（批 ≈ $45） | $0.011；≈ $330（批 ≈ $165） | $0.029；≈ $858（批 ≈ $429） |
| L2 每张展示卡片都生成 LLM 解释（20 卡/日；输入 15,000 / 输出 1,200 token） | $0.0012；≈ $37 | $0.0062；≈ $185 | $0.021；≈ $630 | $0.055；≈ $1,638 |
| L3 论文侧共享预处理（TL;DR/方法/数据集 facet；每篇输入 400 / 输出 150；2.5 万篇/日，批处理；**与用户数无关**） | ≈ $1/日（≈ $30/月） | ≈ $5/日（≈ $150/月） | ≈ $14/日（≈ $431/月） | ≈ $37/日（≈ $1,121/月） |

| 嵌入场景（估算，每篇 350 token） | text-embedding-3-small | text-embedding-3-large | voyage-4-lite | voyage-4 |
|---|---|---|---|---|
| 每日新论文 2.5 万篇（≈2.6 亿 token/月） | ≈ $5/月 | ≈ $34/月 | ≈ $5/月（首 2 亿 token 免费） | ≈ $16/月 |
| 回填 1,000 万篇（35 亿 token，一次性） | ≈ $70 | ≈ $455 | ≈ $70 | ≈ $210 |

另：OpenAlex 语义检索 $1/千次、1 req/s、每次 ≤50 条 [S48]——1,000 DAU × 每日 5 次 ≈ $150/月（估算），且受 1 req/s 限速，只宜近线使用。

**成本结论**：①论文侧共享处理与嵌入**便宜且与用户数无关**，应尽量把 LLM 工作量前移到论文侧；②逐卡 LLM 解释是最贵的用法，应默认模板化解释、用户点"为什么推荐"时再懒生成并缓存；③批处理价普遍对半，日终重排适合批处理。

### 2.7 冷启动

| 路径 | 做法 | 数据/接口事实 | 合规与注意 | 依据 |
|---|---|---|---|---|
| 兴趣树勾选 | 首次进入按 domain→field→subfield→topic 逐级勾选，再挂学科原生标签 | OpenAlex Topics 4/26/252/4,516；topic 带描述与关键词 | 仅元数据，无合规问题；OpenAlex 对 topic 的描述由 LLM 生成 | [实测][S48][S49] |
| 种子论文 | 粘贴 DOI/arXiv/标题，或在科学地图上点选 | S2 推荐 API 直接吃正/负 ID [S41]；Scholar Inbox 用 Scholar Maps 选种子 [S42] | S2 可无 key 调用（未认证请求共享 1000 RPS 池、易被限流），建议申请 API key（入门限速 1 RPS、全端点；2026-09-26 官方页复核，核验修正）[S41] | [S41][S42] |
| 自有论文导入（ORCID） | ORCID OAuth 登录拿到**经认证的 iD**，读公开作品列表 | 公共 API 面向非会员机构，需在开发者工具注册凭证并同意 Public APIs ToS；`pub.orcid.org/v3.0/{iD}/works` 返回 JSON [实测] | `pub.orcid.org/robots.txt` 为 `Disallow: /`（面向爬虫）[实测]——应只走注册凭证的 API，不抓网页；robots 与 API 条款关系需主 agent 裁决 ⚠ | [S59] |
| 自有论文导入（DBLP） | 原计划读 `dblp.org/pid/*.xml` | **2026-09-26 三个 dblp 域名 robots 均为全站 Disallow，且有 Anubis 反爬挑战** [实测] | 当前**不可在线抓取**；该 robots.txt 与 Anubis 默认模板逐字节一致（dblp 是否有意全禁尚无官方说明 ⚠）；**合法替代（核验补充）**：Dagstuhl DROPS 托管 dblp 月度 XML 快照（DOI `10.4230/dblp.xml`，**CC0 1.0**，最新 2026-09-01 版），DROPS robots 仅禁 `/api/*`、`/metadata/*/*`、`/entities/*/metadata/*` [实测]，快照文件的具体下载路径实施前需再核 robots | [S61][S97] |
| Zotero 库导入 | 用户授权 API key 或 OAuth，读 items/collections/tags | `api.zotero.org`；`/users/<id>/items`；增量用 `Last-Modified-Version`/`since=`；遵守 `Backoff`/`Retry-After`/429；建议 ≤4 并发；分页默认 25、上限 100 | 用户自有数据，按用户隔离存放 | [S60] |
| BibTeX/RIS 上传 | 支持从 Google Scholar、Mendeley 等**手动导出**后上传 | — | Google Scholar 不做自动化源（仓库既定红线） | [S97] |
| 关注某学者的"相关研究" | 以导师/名家的作品集作种子 | Google Scholar 2017 起提供同类功能 [S44]；v2 可用 OpenAlex 作者作品（单实体查询免费）[S48] | 只用公开元数据 | [S44][S48] |
| 主动学习 | 冷启动后推送"最能区分兴趣"的一批论文请用户快速评分 | Scholar Inbox：在决策边界附近及以上分层采样，每次评分后重训 [S42] | — | [S42] |
| LLM 画像草稿 | 由种子论文生成可编辑的自然语言兴趣描述，用户确认/修改 | LFM 冷启动优于 MF [S55]；LACE 可编辑画像提升质量 [S56] | 画像属用户私有数据 | [S55][S56] |

### 2.8 在线学习、探索与偏好漂移

| 主题 | 方法与证据 | 在 v2 的落点 |
|---|---|---|
| 上下文老虎机 | **LinUCB**（WWW 2010）：Yahoo! 首页 3,300 万+事件上相对无上下文老虎机点击提升 12.5%，数据越稀疏优势越大；提出用**随机流量日志**离线评估任意老虎机算法 [S62] | 卡片流中的"探索位"：臂 = 主题/来源/作者簇，特征 = 用户×论文特征 |
| Thompson sampling | Chapelle & Li（NIPS 2011）经验评估 [S64] | 按 topic 维护 Beta 后验，决定探索位抽哪个邻近主题 |
| 离线回放评估 | Li 等（WSDM 2011）：基于随机曝光日志的无偏离线评估 [S63] | **前提是记录曝光倾向分**——R0 就要埋点 |
| 位置偏置 | 无偏 LTR（WSDM 2017）[S69]；推荐偏置综述 [S70] | 卡片流天然有位置偏置（第 1 张 vs 第 20 张）；训练需做倾向分校正或随机化插槽 |
| 偏好漂移 | Koren（KDD 2009）时间动态 CF [S65]；Google Scholar 明确把"兴趣随时间变化"纳入模型 [S43]；zotero-arxiv-daily 用按加入顺序的对数衰减权重 [S47] | 长期画像（全量、慢衰减）+ 短期画像（近 N 天、快衰减）双轨 |
| 训练频率 | Scholar Inbox 每次评分后重训逻辑回归 [S42]；ByteDance Monolith 强调实时训练，以系统可靠性换实时性，用无冲突哈希嵌入表、可过期嵌入与频率过滤 [S88]；X 用多哈希嵌入使新帖即刻可表示 [S86] | 每用户线性模型可即时重训；重模型（R2）才需要流式训练 |
| 多兴趣 | Scholar Inbox：单一分类器已能处理多兴趣，但用户要求显式切换多个画像，计划后续提供 [S42]；S2 Feeds 取正例**单一质心**找候选 [S40]；（核验补充）工业界多兴趣召回：MIND（天猫）用动态路由从行为序列抽取多个用户向量用于召回 [S99]，ComiRec（KDD 2020）用多兴趣模块分别召回、再以可控因子聚合以兼顾准确与多样 [S100] | 用户正例聚类成 K 个质心分别召回（避免"平均成谁都不像"）；提供"兴趣频道"；R2 行为序列充足时可换成 MIND/ComiRec 式学习型多兴趣向量 |

### 2.9 评估体系

**离线指标**

| 指标 | 定义/要点 | 依据 |
|---|---|---|
| nDCG@k | 带位置折扣的累积增益 | Järvelin & Kekäläinen [S66] |
| Recall@k / Precision@k | 前 k 命中比例；CTR 论文用 recall@M 评估 CiteULike | [S28] |
| AUC / 平衡准确率 / F1 | Scholar Inbox：F1 与 nDCG 以 100 个随机负例计，平衡准确率以显式负例计 [S42] | [S42] |
| 覆盖率 coverage、意外性 serendipity | "超越准确率"的两类指标 | Ge 等 [S67] |
| 多样性、新颖性 novelty | 系统综述与定义 | Kaminskas & Bridge [S68] |
| 多样化重排 | MMR（最大边际相关）；（核验补充）DPP 行列式点过程的快速贪心 MAP 推断，可只约束结果序列中相邻若干条的相似度，契合卡片流"相邻不重复"（YouTube、X 的 DPP 实践见社媒专题） | [S71][S102] |

**离线 vs 在线**：Beel & Langer 在 Docear 上比较多种 CBF 变体，发现**离线评估结果有时与在线评估、用户研究相矛盾**，并认为离线评估"很可能不适合"研究论文推荐的评估 [S35]。SPECTER 的"相似论文"线上 A/B（CTR +46.5%）则给出了离线进步转化为线上收益的正例 [S1]。**含义**：离线指标只做回归护栏，上线决策必须靠在线实验（A/B 或交错）。

**可用基准/数据**

| 数据 | 规模 | 适合评估 | 依据 |
|---|---|---|---|
| Scholar Inbox 评分 | 80 万条显式正负评分，1.43 万用户 | 每用户分类器（最贴近 v2 R0） | [S42]（**CC BY-NC-ND 4.0**：仅限非商业、禁止演绎；核验修正） |
| SciDocs / SciRepEval | 7 / 24 任务 | 表示层 | [S2][S3] |
| LitSearch | 597 条检索式 | 自然语言检索 + LLM 重排 | [S16] |
| 审稿人金标准（Stelmakh 等） | 477 条专长自评 | 专长匹配 | [S75] |
| exHarmony | 基于 OpenAlex 作者关系与引文的审稿人检索代理任务 | 专长匹配 | [S78] |
| PaperFlow 基准 | 24 模拟用户 × 50 天 | 画像-推荐-适应闭环、兴趣漂移 | [S51] |
| arXivDigest living lab（核验补充） | 在线服务：真实用户 + 多个实验推荐系统经 API 接入 | 可解释论文推荐的在线评测（多策略并行）；仓库与评级见 OSS 专题 | [S101] |
| MTEB 科学子任务 | SCIDOCS、SciFact、SciDocsRR、ArXiv 聚类等 | 嵌入选型 | [S8] |

### 2.10 双向匹配

#### 2.10.1 审稿人—论文匹配（最成熟的"专长匹配"工程）

| 组件 | 事实 | 依据 |
|---|---|---|
| TPMS | 2010 年为 NIPS 构建，2012 起与 Microsoft CMT 集成，被 NIPS、ICML、UAI、AISTATS、CVPR、ICCV、ECCV 等反复使用；专长模型包括对审稿人论文档案词频做 **Dirichlet 平滑的语言模型**、LDA、线性回归、概率矩阵分解；支持主动"打分征集"；分配是带审稿负载与利益冲突约束的优化问题 | [S72] |
| OpenReview 亲和度 | 模型：SPECTER、MFR（多面向量）、SPECTER+MFR（亲和度层面 0.8/0.2 加权）、SPECTER2（proximity adapter）、SciNCL、SPECTER2+SciNCL（论文-论文相似度层面各 0.5）、BM25、TF-IDF；审稿人分数取其论文与投稿相似度的 **max（默认）或 average**；可只取最近 N 篇、排除自选论文、结合竞标（bids）；`sparse_value` 只保留 top-k | [实测][S73] |
| 亲和度评测 | 在 Stelmakh 等公开数据上：TPMS loss 0.28；SPECTER 0.27；SPECTER+MFR 0.24；SPECTER2 0.22；SciNCL 0.22；**SPECTER2+SciNCL 0.21**（易例/难例准确率 0.91/0.65） | [S73][S75] |
| 分配求解器 | **MinMax**（ortools 最小费用流，论文与审稿人最小/最大配额）；**FairFlow / FairIR**（要求每篇论文的分数和不低于公平阈值，阈值二分搜索）；**Randomized**（LP 限定每对的边际概率 + BvN 采样）；**FairSequence**（按分配量/需求比优先的逐个分配，满足 WEF1）；**PerturbedMaximization**（凸二次规划权衡总亲和与随机性，arXiv 2310.05995）；（核验补充）**PeerReview4All**：以"最差论文的审稿质量最大化"为公平目标，基于增量最大流并证明近最优公平（实现为 GPL-3.0 且依赖 Gurobi，见 OSS 专题） | [实测][S74][S76][S103] |
| 新进展 | MERIT（LLM 裁判 + RL + 蒸馏检索器）[S77]；exHarmony（用 OpenAlex 的作者关系/引文作监督代理，学术语料训练的上下文嵌入最好）[S78] | [S77][S78] |

**v2 迁移价值**：①"用户 = 其（自有/收藏）论文集合、用户分 = 与候选论文相似度的 max/avg"就是一个现成的零训练用户模型；②最小费用流/公平分配可直接用于 T4（读书会分配、曝光预算分配）。

#### 2.10.2 论文找读者（反向路由）

| 机制 | 做法 | 依据 |
|---|---|---|
| 时间窗候选池 | S2 Feeds 只从近 60 天的论文中为用户选候选 [S40]；S2 推荐 API 默认 `from=recent` [S41] | [S40][S41] |
| 社区倒排（SimClusters） | 由"关注"二部图算生产者相似度，Metropolis-Hastings 社区发现得到约 14.5 万个社区（覆盖前 2,000 万生产者）；用户的 InterestedIn 向量 = 关注矩阵 × KnownFor；**新推文向量初始为空，每被点赞一次就加上点赞者的 InterestedIn 向量**（实时更新）；话题向量带时间衰减；在线服务为 SimClusters ANN | [实测][S87] |
| 反向 kNN | "影响集"：找把某对象视为最近邻的查询点集合（reverse nearest neighbor） | [S85] |
| 冷启动曝光 | X：展示量低于阈值的作者其帖子被提升到目标位置（New-Author Boost），站外内容乘以 <1 的折扣，同一作者后续帖子多样性衰减 | [实测][S86] |
| 双边公平 | FairRec：为多数生产者保证 MMS 曝光、为每个用户保证 EF1 [S84]；排名曝光公平 [S83] | [S83][S84] |

**规模估算**（估算）：在 1 万用户、每人 ≤5 个兴趣质心、每日 2.5 万篇新论文、256 维时，"全部新论文 × 全部用户质心"的打分约为 5 万 × 2.5 万 × 256 ≈ 3.2×10¹¹ 次乘加，普通 CPU BLAS 为秒到分钟级——**R0/R1 阶段反向路由可用批量矩阵乘而非 ANN**；ANN 只在更大规模时需要。

#### 2.10.3 研究者—研究者 / 合作者推荐

- 链接预测：在大型合作者网络上，仅凭网络拓扑即可预测未来合作，"较精细的邻近度量"可优于直接度量 [S79]。
- 互惠推荐：RECON 首次界定"人既是主体也是对象"的推荐（求职、师生匹配、约会）；在约会数据上引入互惠使 top-10 成功率由 23% 升至 42%，新用户冷启动 top-10 成功率 26% [S80]；综述见 [S81]。
- v2 落点：同行/同好推荐 = 主题重叠（兴趣树节点相似）+ 合作/引用图邻近 + **双方意愿**（opt-in、可见性设置）；默认不暴露个人阅读轨迹。

#### 2.10.4 稳定匹配与容量约束：何时用哪种

| 形式 | 适用 | 不适用 | 依据 |
|---|---|---|---|
| Gale–Shapley 稳定匹配（含容量的"大学录取"版） | 双方都有偏好且需"无人想私奔"的一次性分配：读书会报告人↔论文、导师↔学生 | 连续曝光的卡片流（偏好随时变化） | [S82] |
| 最小费用流 / LP（带上下配额） | 硬配额分配：每篇 ≥k 位读者、每人 ≤m 篇；冲突回避 | 需要随机性/防操纵时 | [S74][S76] |
| 随机化分配（边际概率上限） | 防止被操纵、希望分配多样 | 需确定性复现时 | [S74] |
| 曝光公平重排（MMS/EF1、曝光与相关性成比例） | 卡片流的软约束：新作者/小领域最低曝光 | 硬配额场景 | [S83][S84] |

### 2.11 学科分类体系与兴趣树

| 体系 | 结构与规模 | 许可/获取 | 适用学科 | 依据 |
|---|---|---|---|---|
| OpenAlex Topics | 4 domains → 26 fields → 252 subfields → 4,516 topics；topic 表由 CWTS（莱顿）基于引文网络聚类构建、LLM 命名与描述；分类器用**标题、摘要、引文、期刊名**给作品打分，每篇至多 3 个 topic；约 12% 作品无 topic（2026 年中 3.22 亿中的 3,960 万）；concepts 已弃用；field 编号 11–36 及名称与 Scopus ASJC 两位学科码吻合（OpenAlex 官方说明 topic 即按 Scopus ASJC 类别映射到 subfield/field/domain [S48]，核验补充；ASJC 官方表本身未另行核验） | 快照 `LICENSE.txt` 为 CC0 1.0 [实测]；API 单实体免费；`/text` 自由文本打标签 $0.01/次、1 req/s（费用页标注为 deprecated ⚠） | 全学科骨架 | [实测][S48][S49] |
| arXiv 分类 | 仓库已有全表 | — | 数理、CS、定量生物/金融/经济 | [S97] |
| ACM CCS 2012 | SKOS；2,299 个概念；14 个顶层（13 个学科 + "Proper nouns"）；98 个多父节点；最深 6 层 | 官方页 2026-09-26 Cloudflare 403，数据取自 GitHub 第三方镜像；2012 版之后是否有官方修订 ⚠ 未核验 | 计算机 | [实测][S91] |
| JEL | 20 个一级（A–R、Y、Z）、139 个二级、856 个三级，共 1,015 码 | AEA 官方 XML 公开 | 经济、金融、管理（部分） | [实测][S92] |
| MSC2020 | 63 个二位码、534 个三位码、6,006 个五位码（共 6,603 行）；由 MR 与 zbMATH 联合维护，十年一修，二位码层面不变 | 官方 CSV/PDF/TeX 公开 | 数学 | [实测][S93] |
| PhySH（APS） | 19 个 discipline（ConceptScheme）、9 个 facet、3,882 个概念；DOI 形式标识符；持续发版，最新 v2.8.0（2026-03-24） | CC0（GitHub 官方仓库） | 物理 | [实测][S94] |
| MeSH（NLM） | 当前 RDF 图 30,594 个主题词、84 个限定词；主题词树 16 个类目（A–N、V、Z）；年度更新（官网称 2026 文件已投产、浏览器展示 2026 与 2027 词表） | 公开；SPARQL 当前图对应年份 ⚠ 未核（2025 或 2026；官网称 RDF FTP 目前含 2025 MeSH，故当前 RDF 图较可能为 2025 版） | 生物医学、心理（部分） | [实测][S95] |
| APA PsycInfo 分类码 | ⚠ 未核验（官网页面未能取回） | — | 心理学 | — |

**分类体系的已知局限**（直接影响兴趣树设计）：
1. OpenAlex 分配是**预测**而非查表，存在噪声：例如 SimClusters 这篇推荐系统论文的 primary topic 被判为"Complex Network Analysis Techniques"，第三个 topic 为"Caching and Content Delivery" [实测][S49]；
2. 粒度不均：Economics, Econometrics and Finance 仅 3 个 subfield，Business, Management and Accounting 9 个，Psychology 7 个，Mathematics 10 个，Chemistry 6 个，Medicine 42 个 [实测][S49]——经济金融需要 JEL、数学需要 MSC 才能表达研究者真正的兴趣粒度；
3. 学科原生体系之间**没有现成的官方映射**到 OpenAlex topics（⚠ 本次未发现），需要自建（嵌入相似 + 人工审核）。

### 2.12 工业界社媒推荐的可借鉴点（仅限与学术场景直接相关者）

| 来源 | 可借鉴 | 学术场景改造 | 不建议照搬 |
|---|---|---|---|
| X For You（`xai-org/x-algorithm`，2026-01 开源，Apache-2.0，33,426★）[S86] | 多动作概率 + 显式权重合成分数；作者多样性衰减；新作者提升；排序与可见性过滤分离；候选间隔离使分数可缓存；组件化流水线 | 动作集合换成：收藏、点赞、展开、打开原文、评论、左滑/不感兴趣、静音作者/venue；"新作者提升"用于青年学者/小领域 | 以停留时长为主目标（本文判断：学术场景易奖励标题党） |
| SimClusters（KDD 2020）[S87] | 稀疏、可解释的社区向量同时表示用户与内容；内容向量由点赞者兴趣累加实时更新 | 社区 = 兴趣树节点（固定、可解释），论文的"读者向量" = 收藏者兴趣向量之和 | 从关注图做社区发现（学术场景用引文+主题更稳） |
| Pixie（Pinterest）[S22] | 在内存图上从用户种子做随机游走、剪枝 | "从我的收藏出发的引文/作者图游走"用于探索页 | 30 亿节点级工程 |
| YouTube 双塔与采样偏差校正 [S90] | 召回层双塔、in-batch 负采样的偏差校正 | R2 阶段用户数据充足时的统一召回 | 起步期（数据不足） |
| Monolith（字节跳动）[S88] | 实时训练、无冲突嵌入表 | 仅当 R2 有重模型时参考 | R0/R1（线性模型已可即时重训） |
| OneRec（快手）[S89] | 端到端生成式推荐；技术报告称运营成本为传统级联的 10.6%，承接 25% QPS，停留时长 +0.54%/+1.24% | 研究跟踪 | 需要海量行为数据与 GPU，远超 v2 规模 |

公开的小红书多模态检索数据集 Qilin（含 App 级会话；https://arxiv.org/abs/2503.00501 ，经 HF Papers 检索，2026-09-26，仅题录/摘要级核验）可作为"小红书式"交互研究的参照；抖音/小红书/X 推荐机制的系统性拆解以并行社媒专题为准。

### 2.13 方法对比总表

| 方法 | 数据需求 | 效果证据 | 成本 | 可解释性 | 新论文冷启动 | 建议阶段 |
|---|---|---|---|---|---|---|
| TF-IDF/BM25 + 每用户线性模型 | 每用户数十个正例 + 随机负例 | arxiv-sanity [S39]；S2 Feeds 一半信号 [S40]；Scholar Inbox nDCG 最高 [S42] | 极低（CPU，毫秒到秒级重训，估算） | **高**（词权重） | 好 | R0 |
| 科学嵌入（SPECTER2/SciNCL）+ 线性模型 | 同上 + 嵌入计算 | S2 Feeds [S40]；OpenReview 集成 [S73]；Scholar Inbox AUC 86.36 [S42] | 低（110M 级 BERT；或直接取 S2 预计算向量） | 中（相似论文作解释） | 好 | R0 |
| 通用嵌入（gte-large/Qwen3-Embedding/API）+ 线性模型 | 同上 | Scholar Inbox GTE-large 最佳 AUC [S42]；MTEB 科学任务领先 [S8] | 低—中（API $5–34/月量级，估算） | 中 | 好 | R0 |
| 无训练相似度加权（zotero-arxiv-daily 式） | 用户库 | 5,991★ 的实用工具 [S47]；无公开对照实验 | 极低 | 中 | 好 | R0 冷启动期 |
| 文献耦合 / 共被引 / PPR | 引文数据（OpenAlex 快照或 API） | Connected Papers、Litmaps [S26][S27]；SGC 引文任务强 [S6] | 中（数据体量大：快照 JSONL ≈745 GB）[S48] | **高**（"因为共享 N 篇参考文献"） | 耦合好、共被引差 | R0 探索页 / R1 特征 |
| node2vec / GNN | 大规模图 + 交互 | PinSage/Pixie 工业规模 [S22][S24] | 高 | 低 | 差—中 | R2（可选） |
| 隐式 CF（item-kNN/EASE/ALS） | 足够多用户的共同收藏 | CiteULike 时代研究 [S28][S30]；复现性警示 [S32] | 低—中 | 中（"相似研究者也收藏"） | **差**（out-of-matrix） | R1 |
| 内容 + CF 混合（CTR 式） | 同上 | CTR 解决 out-of-matrix [S28] | 中 | 中 | 好 | R1–R2 |
| 老虎机探索（LinUCB/TS） | 曝光与反馈日志 + 倾向分 | +12.5% 点击 [S62] | 低 | 中 | — | R1（R0 先埋点） |
| 多动作排序（X 式） | 大量多类型行为 | X 生产系统 [S86] | 中—高 | 中（可给出各动作概率） | 依赖内容特征 | R2 |
| LLM listwise 重排 | 用户画像 + 候选 | RankGPT、LitSearch +4.4 [S52][S16]；偏置 [S53] | 中（$0.0006–0.029/用户·日，估算） | 中（可附理由） | 好 | R1（离线批） |
| LLM 自然语言画像（可编辑） | 用户交互摘要 | LFM 冷启动优于 MF [S55]；LACE 用户可编辑提升质量 [S56] | 低（周更，估算） | **高**（用户可读可改） | — | R1 |
| LLM 解释（PaperWeaver 式） | 用户已收藏论文 | 15 人用户研究正面 [S54] | 高（逐卡，估算 $37–1,638/千 DAU·月） | **高** | — | R1 按需 |
| 兴趣树主题亲和（SimClusters 式倒排） | 分类体系 + 反馈 | SimClusters 生产系统 [S87] | 低 | **高**（主题路径） | 好 | R0（骨架）/R1（路由） |
| 带容量分配（最小费用流/公平分配） | 亲和度矩阵 + 配额 | OpenReview 长期生产使用 [S74] | 低—中 | 中 | — | R1（读书会/曝光预算） |

## 3. 对 v2 设计的启示

### 3.1 可直接指导设计的结论

1. **R0 核心 = "共享论文表示 + 每用户轻量线性模型"**：三个独立系统收敛于此（§2.5），Scholar Inbox 在 80 万评分上验证；每次反馈即可重训（Scholar Inbox 做法 [S42]），满足"持续学习"的直观诉求且可解释。
2. **表示层做稀疏 + 稠密双通道并在分数层融合**，不押注单一嵌入：TF-IDF/BM25（FTS5 现成）+ 一个稠密模型；融合方式参考 S2 Feeds 的两模型平均 [S40]。
3. **稠密模型首选 gte-large（英文，MIT）**：与 OpenAlex 语义检索同空间，可把 `search.semantic` 当外部候选源 [S48]；**多语/中文与长文本备选 Qwen3-Embedding-0.6B（Apache-2.0，32K，MRL 可降维）** [S10]；科学专用备选 SPECTER2（可直接取 S2 预计算向量；数据集 README 标注为 Apache-2.0，使用时须按 S2 API 协议署名，核验补充）[S41]。存储降到 256 维（Scholar Inbox 表明 256 维已足够 [S42]；OpenAI 与 Qwen3 均支持截短 [S10][S14]）。
4. **模型许可进入选型门禁**：禁止 CC-BY-NC（jina v3/v5、NV-Embed-v2）、研究许可（jina v4）进入可能商用的多用户平台；Gemma 许可需单独评估 [S12][S13]。
5. **向量要可版本化**：`embedding_model + version + dims` 作为主键一部分，换模型即全量重算；按 §2.6.6 估算，新论文增量 API 成本约 $5–34/月、千万级回填约 $70–455（估算）。
6. **召回多路并行、排序统一**：①时间窗候选池（建议 7–60 天，S2 用 60 天 [S40]；按 OpenAlex 月量估算 60 天约 140 万篇，256 维 float32 约 1.4 GB，估算）上的**每用户多质心**近邻；②v1 订阅 DSL/关注作者/venue；③文献耦合与"引用了我收藏的论文"；④兴趣树邻近节点（探索）；⑤R1 起的协同通道；⑥外部 API（S2 推荐、OpenAlex 语义检索，近线）；⑦反向路由推来的新论文。合并去重复用 v1 的 identifier 合并。
7. **反馈映射分级、负反馈必须入模且与随机负例分权**：Scholar Inbox 表明加大显式负例权重能把显式负例特异度从 68% 提到 78%，代价是 F1/nDCG 单调下降，他们为"让用户能调教分类器"仍取 V=0.8 [S42]——v2 左滑应被视为有效负例，且应向用户明示"左滑会让同类变少"。
8. **排序打分从线性开始、向多动作演进**：R0 = `score = 个性化分 + 词法分 + 主题亲和 + 新鲜度 − 已读/重复惩罚`，再做作者多样性衰减、每日预算；R2 才上 X 式多动作概率模型 [S86]。
9. **冷启动三段式**：兴趣树勾选 →（ORCID OAuth 自有论文 / Zotero API / BibTeX 上传 / 粘贴 DOI / 关注某学者相关研究）→ 5–10 分钟主动学习评分轮（边界附近分层采样 [S42]）。**Google Scholar 只接受用户手动导出上传；DBLP 当前禁抓**（§2.7）。
10. **兴趣树 = OpenAlex Topics 骨架（DAG）+ 学科原生叶子 + 用户自定义标签**：每个节点存嵌入质心（topic 描述/关键词与成员论文的平均），论文除 OpenAlex 给的 ≤3 个 topic 外，再用本地嵌入最近邻补齐多标签；对稀疏反馈做**层级平滑**（子节点亲和向父节点收缩）；经济金融下挂 JEL、数学下挂 MSC、物理下挂 PhySH、生医下挂 MeSH、CS 下挂 ACM CCS 与 arXiv 分类（§2.11）。
11. **探索是一等公民**：保留固定比例探索位（如每 10 张 1–2 张，设计参数），以兴趣树兄弟节点/相邻 subfield 为臂做 Thompson sampling；R0 起记录曝光倾向分，才能在 R1 做回放评估 [S62][S63][S64]。
12. **漂移处理**：长期画像 + 短期画像双轨，按时间或加入顺序衰减（参考 zotero-arxiv-daily 的对数衰减 [S47]、Koren 时间动态 [S65]）；提供显式"兴趣频道/多画像"（Scholar Inbox 用户的明确诉求 [S42]）。
13. **LLM 只做离线/近线增强**：论文侧共享预处理（TL;DR、方法/数据集/领域 facet；与用户数无关、最省）→ 用户侧周更可编辑自然语言画像 → 每日批处理 top-K listwise 重排 → 解释默认模板化、按需懒生成并缓存；**不在滑动路径同步调用 LLM**（§2.6.5–2.6.6）；**不把 LLM 零样本当主匹配器**（专长匹配证据为负 [S75]）。
14. **"论文找读者"的最小实现**：新论文入库 → 嵌入 + 兴趣树节点打分 → 两路找读者（①节点倒排：该节点亲和度高的用户；②与用户质心批量点积）→ 受**每用户日预算**与**每篇曝光下限**约束的分配（贪心即可，读书会等硬配额场景用 ortools 最小费用流 [S74]）→ 写入次日卡片流/推送队列；对低曝光新作者做 X 式提升 [S86]。R0/R1 规模下批量矩阵乘即可完成（§2.10.2 估算）。
15. **论文侧"读者向量"**：仿 SimClusters，每次收藏把收藏者的兴趣树向量累加到论文上 [S87]，形成随时间演化的协同信号；它同时是 CF 冷启动的平滑过渡和"这篇在哪些社群受欢迎"的可解释标签。
16. **人与人匹配默认关闭、双向 opt-in**：打分同时考虑双方（主题重叠 × 双方意愿）；RECON 在约会场景引入互惠后 top-10 成功率由 23% 升至 42% [S80]，学术场景的增益需自行验证；不暴露个人阅读列表，只暴露用户自愿公开的收藏/主页。
17. **评估闸门**：离线（Scholar Inbox 评分数据做 R0 回归基准——该数据为 CC BY-NC-ND 4.0，仅限非商业研究，若平台可能商用须先取得授权或改用自建评测集；nDCG@10/AUC/平衡准确率 + 覆盖/新颖/多样）只作护栏；上线看收藏率、左滑率、D7 回访、每日完成率；每次算法变更走 A/B 或交错（离线与在线可能矛盾 [S35]）。
18. **反作弊与质量**：作者/机构刷赞、评论灌水会污染"读者向量"与 CF；需要用户可信度（X 以关注/互动图上的 PageRank 做 `user-cred` 标签 [S86]）、异常检测与评论审核；排序与可见性过滤分离 [S86]。
19. **合规边界落到数据面**：推荐与路由只使用**可共享元数据**（标题、许可允许的摘要、参考文献、主题）；由用户私有凭证取得的 auth-gated 全文及其派生物（全文嵌入、全文 TL;DR）只能进入该用户的私有空间，**不得进入共享索引、全局模型或他人的推荐/解释**；Google Scholar 不自动化；ORCID 用注册凭证 + OAuth；DBLP 暂停在线访问。
20. **基础设施取向**：R0 可在 SQLite（FTS5）+ sqlite-vec（MIT/Apache-2.0 双许可，最新稳定版 v0.1.9，仍为预 1.0 版）或 FAISS（MIT）上完成；多用户后迁 Postgres + pgvector（PostgreSQL 式许可）[S96]。通用检索索引/路由细节以检索专题为准，推荐侧只需三类索引：论文向量、用户质心向量、主题倒排。

### 3.2 分阶段技术路线建议

| 阶段 | 规模假设 | 核心算法 | 数据/信号 | 基础设施 | 评估闸门（进入下一阶段的条件） | 成本量级（估算） |
|---|---|---|---|---|---|---|
| **R0 MVP** | ≤1 千活跃用户 | 稀疏(BM25/TF-IDF) + 稠密(gte-large 或 Qwen3-Emb-0.6B, 256 维) 双通道；每用户逻辑回归（显式负例 + 随机负例分权，每次反馈重训）；多质心近邻召回；兴趣树主题亲和；作者多样性 + 新鲜度 + 每日预算；模板化解释（匹配主题/相似收藏/关键句高亮）；文献耦合"探索页"；反向路由（批量点积 + 贪心配额） | 收藏/点赞/左滑/展开/打开；冷启动三段式；曝光日志含倾向分 | SQLite + FTS5 + sqlite-vec/FAISS；OpenAlex/Crossref/arXiv 元数据；S2 预计算向量（Apache-2.0，按 S2 协议署名） | Scholar Inbox 数据上 AUC/nDCG 不低于公开基线（该数据 CC BY-NC-ND 4.0，仅限非商业研究，见 §4 第 4 条）；内部 dogfood 收藏率与左滑率稳定；埋点完整 | 嵌入 API ≈ $5–34/月；LLM 可为 0 |
| **R1 多用户增长** | 1 千–5 万 | + item-kNN/EASE 协同通道；SimClusters 式论文"读者向量"；Thompson sampling/LinUCB 探索位 + 回放评估；长短期双画像与兴趣频道；LLM：论文侧共享预处理、周更可编辑画像、每日批 listwise 重排 top-K、按需解释；人与人互惠推荐（opt-in）；读书会/曝光配额用最小费用流 | + 评论/评分；用户可信度；跨用户共现（聚合、去标识） | Postgres + pgvector；任务队列；批处理 LLM | 在线 A/B：收藏率↑、左滑率↓、D7 回访↑；覆盖率/新作者曝光不降 | LLM 重排 ≈ $9–429/千 DAU·月（取决于模型与批处理）；论文侧 ≈ $30–431/月 |
| **R2 规模化（可选）** | >5 万 或 交互 ≥10⁶ 量级（经验阈值，待验证） | 用自有交互微调嵌入/适配器（SciRepEval 式）；LLM 裁判蒸馏的小型重排器（RankGPT/MERIT 范式）；双塔统一召回（采样偏差校正）；X 式多动作排序；可选 LightGCN/PinSage | 大规模多类型行为 | GPU 训练/推理；流式特征 | 离线 + 在线双重显著收益才替换 R1 组件 | 取决于自建 GPU |

**明确推迟/不做**：端到端生成式推荐（OneRec 类）、实时流式训练（Monolith 类）、以停留时长为主目标的排序、LLM 零样本直接做主排序、任何需要跨用户共享 auth-gated 全文派生物的特征。

### 3.3 参考流程（设计伪代码，非实现）

```text
# 设计伪代码：R0 每日卡片流生成（离线批 + 近线补货）
for user u:
    pool      = papers(published_within = W)                     # 时间窗候选池
    cands     = union(
                  ann(pool, centroids(u, k=K)),                  # 多质心近邻（稠密）
                  fts_bm25(pool, profile_terms(u)),              # 词法通道
                  subscriptions_dsl(u),                          # v1 订阅复用
                  coupling(pool, library(u)),                    # 文献耦合/引用了我收藏的论文
                  interest_tree_neighbors(u, explore=True),      # 探索臂（Thompson sampling）
                  routed_inbox(u))                               # "论文找读者"推来的新论文
    cands     = dedupe_by_identifier(cands) - seen(u) - muted(u)
    s(p)      = a*lr_u(dense(p) ⊕ tfidf(p)) + b*topic_affinity(u, p)
                + c*freshness(p) + d*coupling_score(u, p)
    ranked    = author_diversity_decay(sort_by(s, cands))
    feed[u]   = fill_budget(ranked, B_u, explore_slots=E, log_propensity=True)

# 设计伪代码：论文找读者（新论文到达的批处理）
for new paper p:
    v_p       = embed(p); nodes_p = tree_tag(p)                  # 嵌入 + 兴趣树多标签
    readers   = top_users(inverted(nodes_p)) ∪ top_users(v_p · all_user_centroids)
    assign p -> readers subject to: daily_cap(u) , min_exposure(p) , no_duplicate
# 反馈：每次收藏/左滑 -> 重训 lr_u（毫秒到秒级，估算）；收藏 -> paper_reader_vec(p) += tree_vec(u)
```

## 4. 未决问题与风险

1. **【高】DBLP robots 全站禁止（2026-09-26 实测）**：三个 dblp 域名 robots 均为 `User-agent: * / Disallow: /`，且有 Anubis 反爬挑战 [S61]；仓库 v1 DBLP adapter（`src/paper_crawler/adapters/dblp/adapter.py`）按 2026-07 的 `Crawl-delay: 4` 与 `/db/**` 允许规则实现 [S97]。需主 agent 立项复核 v1 合规、决定 DBLP 数据改走何种合法渠道，并同步到 decision-log。核验补充：①该 robots.txt 与 Anubis 项目默认 `web/static/robots.txt` 逐字节一致（Anubis 作者在 issue #532 中称这个默认文件是"一键全关"用的），可能是部署默认值而非 dblp 专门声明的政策，建议联系 dblp 团队确认，确认前按字面执行 ⚠；②月度快照渠道已核实：DROPS 集合 `10.4230/dblp.xml`（CC0 1.0，最新 2026-09-01 版）[S61]。
2. **ORCID robots 与 API 的关系**：`pub.orcid.org/robots.txt` 为 `Disallow: /`，而官方文档提供注册凭证的 Public API [S59]；建议只以注册凭证 + OAuth 方式调用，由主 agent 裁定并写入合规说明。
3. **摘要展示与再分发许可**：多用户卡片流要向许多用户展示摘要；Crossref/出版社摘要、S2 数据（含预计算向量与 TL;DR）、OpenAlex（CC0，但摘要以倒排索引形式提供）的再展示条款需由 sources 专题/法务核实 ⚠。（核验补充：S2 release README 标注 `abstracts`/`tldrs`/`papers` 为 ODC-BY、嵌入为 Apache-2.0，S2 API 协议要求署名 [S41]；但 ODC-BY 管的是数据库，摘要文字本身的著作权人（出版社/作者）是否允许在多用户产品中展示，仍需法务判断。）
4. **嵌入/模型/数据许可**：见 §2.2.4；另 Scholar Inbox 评分数据集为 **CC BY-NC-ND 4.0**（仓库 LICENSE 文件，核验修正）：只能用于非商业研究，且不得分发改编版本。若 v2 可能商用，不能把它当内部回归基准，需先取得作者授权，或改用自建评测集（R0 起按 §2.1 埋点积累）。
5. **外部 API 预算与速率**：S2 有 key 入门限速 1 RPS（全端点；2026-09-26 官方 API 页复核）[S41]；OpenAlex 语义检索 1 req/s、$1/千次、每次 ≤50 条 [S48]；OpenAlex `/text` 打标签在费用表中标注为 deprecated [S48]——兴趣树打标签不应依赖它，需本地替代。
6. **跨学科表示质量未知**：SPECTER2 训练覆盖 23 个领域 [S5]，通用模型的科学基准以 CS/生医为主；数学（公式密集）、经济金融（JEL 细粒度）、化学（实体）等领域的推荐质量需要自建小样本评测（⚠ 本次未找到分学科对比数据）。
7. **中文与跨语言**：gte-large 仅英文 [S13]；若 v2 面向中文用户输入中文兴趣描述，需要多语模型（Qwen3-Embedding、BGE-M3）做查询侧编码，并验证与英文论文的跨语言匹配质量。
8. **马太效应与信息茧房**：Scholar Inbox 批评社媒式推荐偏向热门作者/机构 [S42]；CF 与"读者向量"会放大热门——需要曝光公平约束与新作者提升（§2.10）并监控覆盖率。
9. **位置偏置与评估偏差**：卡片流强位置偏置 [S69][S70]；离线指标可能与在线结果矛盾 [S35]；R0 若不记录倾向分，R1 的回放评估将不可用。
10. **LLM 偏置与成本漂移**：LLM 重排的流行度/位置偏置 [S53]；价格与分词器变化（Claude 4.7+ 约多 30% token [S58]）会改变成本曲线，需把模型选择做成可配置项并按月复核。
11. **隐私与数据最小化**：交互数据用于协同过滤与人与人推荐，需要显式同意、可见性设置与聚合阈值；auth-gated 全文派生数据的隔离需在数据模型层强制（与 design/06 后续 v2 数据模型联动）。
12. **兴趣树映射成本**：学科原生体系 ↔ OpenAlex topics 无官方映射（⚠ 未发现）；自建映射需要人工审核预算，且 OpenAlex topic 分配存在噪声（§2.11 实例）。
13. **SciDocs/MTEB 与真实推荐的落差**：SciDocs `recomm` 任务显示嵌入替换对真实点击排序的边际影响小 [S1][S6]；嵌入选型不应只看 MTEB 排名。
14. **反向路由的"骚扰"风险**：推送过多会伤害留存；每用户日预算、静默时段与"本周不再推此主题"的控制需要产品与前端专题共同定义。

## 5. 参考来源

> 除另注外，访问/核验日期均为 **2026-09-26**。GitHub star/许可/最近 push 均为当日 `gh api` 结果。

**A. 内容表示与基准**
- [S1] Cohan et al., *SPECTER: Document-level Representation Learning using Citation-informed Transformers*, ACL 2020 — https://arxiv.org/abs/2004.07180 ；全文 https://arxiv.org/pdf/2004.07180 （2026-09-26）
- [S2] allenai/scidocs README（任务与 SPECTER 指标；建议改用 SciRepEval）— https://github.com/allenai/scidocs （2026-09-26）
- [S3] Singh et al., *SciRepEval: A Multi-Format Benchmark for Scientific Document Representations*, EMNLP 2023 — https://arxiv.org/abs/2211.13308 ；https://github.com/allenai/scirepeval （2026-09-26）
- [S4] SPECTER2 模型卡（adapters、训练细节、SciRepEval/MDCR 表）— https://huggingface.co/allenai/specter2 ；https://github.com/allenai/SPECTER2 （2026-09-26）
- [S5] Ai2 Blog, *SPECTER2: Adapting scientific document embeddings to multiple fields and task formats*（2023-11-27）— https://allenai.org/blog/specter2-adapting-scientific-document-embeddings-to-multiple-fields-and-task-formats-c95686c06567 （2026-09-26）
- [S6] Ostendorff et al., *Neighborhood Contrastive Learning for Scientific Document Representations with Citation Embeddings*, EMNLP 2022 — https://arxiv.org/abs/2202.06671 ；https://github.com/malteos/scincl ；https://huggingface.co/malteos/scincl （2026-09-26）
- [S7] Mysore, Cohan, Hope, *Multi-Vector Models with Textual Guidance for Fine-Grained Scientific Document Similarity*（Aspire）— https://arxiv.org/abs/2111.08366 （2026-09-26）
- [S8] MTEB 结果仓库 embeddings-benchmark/results（逐模型逐任务 JSON）— https://github.com/embeddings-benchmark/results ；SCIDOCS 任务定义 https://github.com/embeddings-benchmark/mteb/blob/main/mteb/tasks/retrieval/eng/scidocs_retrieval.py （2026-09-26，gh api 读取）
- [S9] *MTEB: Massive Text Embedding Benchmark* — https://arxiv.org/abs/2210.07316 ；*MMTEB: Massive Multilingual Text Embedding Benchmark* — https://arxiv.org/abs/2502.13595 （2026-09-26，经 HF Papers 核对题名）
- [S10] Zhang et al., *Qwen3 Embedding: Advancing Text Embedding and Reranking Through Foundation Models* — https://arxiv.org/abs/2506.05176 ；模型卡 https://huggingface.co/Qwen/Qwen3-Embedding-8B （2026-09-26）
- [S11] Chen et al., *M3-Embedding (BGE-M3)* — https://arxiv.org/abs/2402.03216 ；https://huggingface.co/BAAI/bge-m3 （2026-09-26）
- [S12] *jina-embeddings-v5-text: Task-Targeted Embedding Distillation* — https://arxiv.org/abs/2602.15547 ；https://huggingface.co/jinaai/jina-embeddings-v5-text-small ；https://huggingface.co/jinaai/jina-embeddings-v5-text-nano ；https://huggingface.co/jinaai/jina-embeddings-v3 ；https://huggingface.co/jinaai/jina-embeddings-v4 （2026-09-26）
- [S13] 其他开源嵌入模型卡（许可/参数/语言）— https://huggingface.co/thenlper/gte-large ；https://huggingface.co/Alibaba-NLP/gte-Qwen2-7B-instruct ；https://huggingface.co/intfloat/e5-mistral-7b-instruct ；https://huggingface.co/intfloat/multilingual-e5-large-instruct ；https://huggingface.co/nomic-ai/nomic-embed-text-v1.5 ；https://huggingface.co/nomic-ai/nomic-embed-text-v2-moe ；https://huggingface.co/google/embeddinggemma-300m ；https://huggingface.co/nvidia/NV-Embed-v2 ；https://huggingface.co/Snowflake/snowflake-arctic-embed-l-v2.0 （2026-09-26）
- [S14] OpenAI 嵌入指南 — https://developers.openai.com/api/docs/guides/embeddings ；定价 — https://developers.openai.com/api/docs/pricing （2026-09-26）
- [S15] Voyage AI 定价 — https://docs.voyageai.com/docs/pricing （2026-09-26）
- [S16] Ajith et al., *LitSearch: A Retrieval Benchmark for Scientific Literature Search*, EMNLP 2024 — https://arxiv.org/abs/2407.18940 （2026-09-26）
- [S17] *BRIGHT* — https://arxiv.org/abs/2407.12883 ；*Rethinking Reasoning-Intensive Retrieval*（BRIGHT-Pro，ACL 2026）— https://arxiv.org/abs/2605.04018 ；https://github.com/yale-nlp/Bright-Pro （2026-09-26）
- [S18] Robertson & Zaragoza, *The Probabilistic Relevance Framework: BM25 and Beyond*, 2009 — https://doi.org/10.1561/1500000019 （2026-09-26）

**B. 引文图方法与工具**
- [S19] Small, *Co-citation in the scientific literature*, JASIS 1973 — https://doi.org/10.1002/asi.4630240406 （2026-09-26）
- [S20] Kessler, *Bibliographic coupling between scientific papers*, American Documentation 1963 — https://doi.org/10.1002/asi.5090140103 （2026-09-26）
- [S21] Haveliwala, *Topic-sensitive PageRank*, WWW 2002 — https://doi.org/10.1145/511446.511513 （2026-09-26）
- [S22] Eksombatchai et al., *Pixie*, WWW 2018（摘要经 OpenAlex）— https://doi.org/10.1145/3178876.3186183 （2026-09-26）
- [S23] Grover & Leskovec, *node2vec*, KDD 2016 — https://doi.org/10.1145/2939672.2939754 （2026-09-26）
- [S24] Ying et al., *Graph Convolutional Neural Networks for Web-Scale Recommender Systems*（PinSage）, KDD 2018 — https://doi.org/10.1145/3219819.3219890 （2026-09-26）
- [S25] He et al., *LightGCN*, SIGIR 2020 — https://doi.org/10.1145/3397271.3401063 （2026-09-26）
- [S26] Connected Papers — About（文案取自站点前端 bundle）— https://www.connectedpapers.com/about （2026-09-26）
- [S27] Litmaps 帮助中心 — https://docs.litmaps.com/en/articles/9029858-search-algorithms-in-litmaps ；https://docs.litmaps.com/en/articles/7212085-litmaps-database-coverage-open-access-and-article-indexing （2026-09-26）

**C. 协同过滤与学术推荐综述**
- [S28] Wang & Blei, *Collaborative Topic Modeling for Recommending Scientific Articles*, KDD 2011 — https://doi.org/10.1145/2020408.2020480 ；PDF http://www.cs.columbia.edu/~blei/papers/WangBlei2011.pdf （2026-09-26）
- [S29] Wang, Wang, Yeung, *Collaborative Deep Learning for Recommender Systems*, KDD 2015 — https://doi.org/10.1145/2783258.2783273 （2026-09-26）
- [S30] Hu, Koren, Volinsky, *Collaborative Filtering for Implicit Feedback Datasets*, ICDM 2008 — https://doi.org/10.1109/ICDM.2008.22 （2026-09-26）
- [S31] Steck, *Embarrassingly Shallow Autoencoders for Sparse Data*（EASE）, WWW 2019 — https://doi.org/10.1145/3308558.3313710 （2026-09-26）
- [S32] Ferrari Dacrema et al., *Are we really making much progress?*, RecSys 2019 — https://doi.org/10.1145/3298689.3347058 ；https://arxiv.org/abs/1907.06902 （2026-09-26）
- [S33] Rendle, Krichene, Zhang, Anderson, *Neural Collaborative Filtering vs. Matrix Factorization Revisited*, RecSys 2020 — https://doi.org/10.1145/3383313.3412488 ；https://arxiv.org/abs/2005.09683 （2026-09-26）
- [S34] Beel, Gipp, Langer, Breitinger, *Research-paper recommender systems: a literature survey*, IJDL — https://doi.org/10.1007/s00799-015-0156-0 （摘要：https://link.springer.com/article/10.1007/s00799-015-0156-0 ，2026-09-26）
- [S35] Beel & Langer, *A Comparison of Offline Evaluations, Online Evaluations, and User Studies in the Context of Research-Paper Recommender Systems*, TPDL 2015 — https://doi.org/10.1007/978-3-319-24592-8_12 （2026-09-26）
- [S36] Hristakeva et al., *Building recommender systems for scholarly information*, SWM 2017（摘要经 OpenAlex；全文闭源）— https://doi.org/10.1145/3057148.3057152 （2026-09-26）
- [S37] Kreutz & Schenkel, *Scientific paper recommendation systems: a literature review of recent publications*, IJDL 2022 — https://doi.org/10.1007/s00799-022-00339-w （2026-09-26）
- [S38] Wikipedia, *CiteULike*（下线日期）— https://en.wikipedia.org/wiki/CiteULike （2026-09-26）

**D. 已知系统**
- [S39] karpathy/arxiv-sanity-lite（1,696★，MIT；serve.py、compute.py）— https://github.com/karpathy/arxiv-sanity-lite ；kNN vs SVM 笔记本 https://github.com/karpathy/randomfun/blob/master/knn_vs_svm.ipynb （2026-09-26）
- [S40] Kinney et al., *The Semantic Scholar Open Data Platform*（§3.4.5 Research Feeds；§4.3 Recommendations API）— https://arxiv.org/abs/2301.10140 （2026-09-26）
- [S41] Semantic Scholar Recommendations API swagger — https://api.semanticscholar.org/recommendations/v1/swagger.json ；Graph API swagger — https://api.semanticscholar.org/graph/v1/swagger.json ；Datasets 最新 release — https://api.semanticscholar.org/datasets/v1/release/latest ；限速说明（API 产品页，核验补充）— https://www.semanticscholar.org/product/api ；API License Agreement（2023-05-17 版，核验补充）— https://www.semanticscholar.org/product/api/license （2026-09-26；各数据集许可见上述 release JSON 中每个数据集的 README 字段）
- [S42] Flicke et al., *Scholar Inbox: Personalized Paper Recommendations for Scientists*, arXiv:2504.08385v2（2025-06-14，CC BY 4.0）— https://arxiv.org/abs/2504.08385 ；HTML https://arxiv.org/html/2504.08385v2 ；数据集 https://github.com/avg-dev/scholar_inbox_datasets （2026-09-26）
- [S43] Google Scholar Blog, *Scholar Updates: Making New Connections*（2012-08）— https://scholar.googleblog.com/2012/08/scholar-updates-making-new-connections.html （2026-09-26）
- [S44] Google Scholar Blog, *Follow related research for key authors*（2017-10）— https://scholar.googleblog.com/2017/10/follow-related-research-for-key-authors.html （2026-09-26）
- [S45] Google Scholar Blog, *Scholar Recommendations Reloaded*（2021-02）— https://scholar.googleblog.com/2021/02/scholar-recommendations-reloaded.html （2026-09-26）
- [S46] Google Scholar Blog, *Quick Read*（2026-08）— https://scholar.googleblog.com/2026/08/quick-read-see-how-paper-answers-your.html （2026-09-26）
- [S47] TideDra/zotero-arxiv-daily（5,991★，AGPL-3.0；README 与 `src/zotero_arxiv_daily/reranker/base.py`）— https://github.com/TideDra/zotero-arxiv-daily （2026-09-26）
- [S48] OpenAlex 帮助中心：Topics https://help.openalex.org/data/topics ；Semantic search https://help.openalex.org/api/semantic-search ；Tag aboutness https://help.openalex.org/api/tag-aboutness ；Example costs https://help.openalex.org/access/example-costs ；Snapshot https://help.openalex.org/access/snapshot ；Works attributes https://help.openalex.org/data/works/attributes ；快照许可 https://openalex.s3.amazonaws.com/LICENSE.txt （CC0 1.0）（2026-09-26）
- [S49] OpenAlex API 实测：https://api.openalex.org/topics?per-page=1 ；/subfields、/fields、/domains；/fields?per-page=50；/works?filter=from_publication_date:2026-08-01,to_publication_date:2026-08-31 等；/works/doi:10.1145/3394486.3403370 （2026-09-26）
- [S50] allenai/asta-paper-finder（245★，Apache-2.0）— https://github.com/allenai/asta-paper-finder （2026-09-26）
- [S51] Wang et al., *PaperFlow: Profiling, Recommending, and Adapting Across Daily Paper Streams*, arXiv:2606.07454 — https://arxiv.org/abs/2606.07454 （2026-09-26）

**E. LLM 与推荐**
- [S52] Sun et al., *Is ChatGPT Good at Search? Investigating Large Language Models as Re-Ranking Agents*, EMNLP 2023 — https://arxiv.org/abs/2304.09542 （2026-09-26）
- [S53] Hou et al., *Large Language Models are Zero-Shot Rankers for Recommender Systems*, ECIR 2024 — https://doi.org/10.1007/978-3-031-56060-6_24 ；https://arxiv.org/abs/2305.08845 （2026-09-26）
- [S54] Lee et al., *PaperWeaver*, CHI 2024 — https://doi.org/10.1145/3613904.3642196 ；https://arxiv.org/abs/2403.02939 （2026-09-26）
- [S55] Zhou, Dai, Joachims, *Language-Based User Profiles for Recommendation* — https://arxiv.org/abs/2402.15623 （2026-09-26）
- [S56] Mysore et al., *Editable User Profiles for Controllable Text Recommendation*（LACE）, SIGIR 2023 — https://arxiv.org/abs/2304.04250 （2026-09-26）
- [S57] 自然语言画像后续（题录/摘要级）：https://arxiv.org/abs/2410.18870 ；https://arxiv.org/abs/2601.21105 ；https://arxiv.org/abs/2506.18309 ；https://arxiv.org/abs/2502.14541 （经 https://huggingface.co/papers 检索，2026-09-26）
- [S58] Anthropic 定价（模型、批处理、缓存、分词器说明）— https://platform.claude.com/docs/en/about-claude/pricing （2026-09-26）

**F. 冷启动接口**
- [S59] ORCID Public API — https://info.orcid.org/documentation/features/public-api/ ；实测 https://pub.orcid.org/v3.0/0000-0002-1825-0097/works ；https://pub.orcid.org/robots.txt （2026-09-26）
- [S60] Zotero Web API v3 Basics — https://www.zotero.org/support/dev/web_api/v3/basics （2026-09-26）
- [S61] dblp robots.txt — https://dblp.org/robots.txt ；https://dblp.uni-trier.de/robots.txt ；https://dblp.dagstuhl.de/robots.txt ；Dagstuhl DROPS robots — https://drops.dagstuhl.de/robots.txt ；（核验补充）Anubis 默认 robots 模板 https://github.com/TecharoHQ/anubis/blob/main/web/static/robots.txt 与 issue #532 https://github.com/TecharoHQ/anubis/issues/532 ；dblp 月度 XML 快照集合（CC0 1.0）https://drops.dagstuhl.de/entities/collection/10.4230/dblp.xml （2026-09-26）

**G. 在线学习与评估**
- [S62] Li, Chu, Langford, Schapire, *A Contextual-Bandit Approach to Personalized News Article Recommendation*, WWW 2010 — https://doi.org/10.1145/1772690.1772758 ；https://arxiv.org/abs/1003.0146 （2026-09-26）
- [S63] Li, Chu, Langford, Wang, *Unbiased offline evaluation of contextual-bandit-based news article recommendation algorithms*, WSDM 2011 — https://doi.org/10.1145/1935826.1935878 （2026-09-26）
- [S64] Chapelle & Li, *An Empirical Evaluation of Thompson Sampling*, NIPS 2011 — https://proceedings.neurips.cc/paper/2011/file/e53a0a2978c28872a4505bdb51db06dc-Paper.pdf （2026-09-26）
- [S65] Koren, *Collaborative filtering with temporal dynamics*, KDD 2009 — https://doi.org/10.1145/1557019.1557072 （2026-09-26）
- [S66] Järvelin & Kekäläinen, *Cumulated gain-based evaluation of IR techniques*, TOIS 2002 — https://doi.org/10.1145/582415.582418 （2026-09-26）
- [S67] Ge, Delgado-Battenfeld, Jannach, *Beyond accuracy*（覆盖率与意外性评估）, RecSys 2010 — https://doi.org/10.1145/1864708.1864761 （2026-09-26）
- [S68] Kaminskas & Bridge, *Diversity, Serendipity, Novelty, and Coverage*, ACM TiiS 2016 — https://doi.org/10.1145/2926720 （2026-09-26）
- [S69] Joachims, Swaminathan, Schnabel, *Unbiased Learning-to-Rank with Biased Feedback*, WSDM 2017 — https://doi.org/10.1145/3018661.3018699 （2026-09-26）
- [S70] Chen et al., *Bias and Debias in Recommender System: A Survey and Future Directions*, TOIS 2023 — https://doi.org/10.1145/3564284 （2026-09-26）
- [S71] Carbonell & Goldstein, *The use of MMR, diversity-based reranking…*, SIGIR 1998 — https://doi.org/10.1145/290941.291025 （2026-09-26）

**H. 双向匹配**
- [S72] Charlin & Zemel, *The Toronto Paper Matching System*, ICML 2013 workshop（JMLR W&CP 28）— https://www.cs.toronto.edu/~lcharlin/papers/tpms.pdf （2026-09-26）
- [S73] openreview/openreview-expertise README（51★，MIT）— https://github.com/openreview/openreview-expertise （2026-09-26）
- [S74] openreview/openreview-matcher README（23★，GitHub 未声明许可）— https://github.com/openreview/openreview-matcher （2026-09-26）
- [S75] Stelmakh et al., *A Gold Standard Dataset for the Reviewer Assignment Problem*, arXiv:2303.16750（v 2025-05-30）— https://arxiv.org/abs/2303.16750 （2026-09-26）
- [S76] Kobren, Saha, McCallum, *Paper Matching with Local Fairness Constraints*, KDD 2019 — https://doi.org/10.1145/3292500.3330899 （2026-09-26）
- [S77] Yang et al., *MERIT: Matching Expertise via Rubric-Informed Training for Reviewer Assignment*, EMNLP 2026 — https://arxiv.org/abs/2605.27865 （2026-09-26）
- [S78] Ebrahimi et al., *exHarmony: Authorship and Citations for Benchmarking the Reviewer Assignment Problem* — https://arxiv.org/abs/2502.07683 （2026-09-26）
- [S79] Liben-Nowell & Kleinberg, *The link-prediction problem for social networks*, JASIST 2007 — https://doi.org/10.1002/asi.20591 （2026-09-26）
- [S80] Pizzato, Rej, Chung, Koprinska et al., *RECON*（互惠推荐，在线约会场景；摘要经 OpenAlex）, RecSys 2010 — https://doi.org/10.1145/1864708.1864747 （2026-09-26）
- [S81] Palomares et al., *Reciprocal Recommender Systems: Analysis of state-of-art literature…*, Information Fusion 2021 — https://doi.org/10.1016/j.inffus.2020.12.001 （2026-09-26）
- [S82] Gale & Shapley, *College Admissions and the Stability of Marriage*, 1962 — https://doi.org/10.1080/00029890.1962.11989827 （2026-09-26）
- [S83] Singh & Joachims, *Fairness of Exposure in Rankings*, KDD 2018 — https://doi.org/10.1145/3219819.3220088 （2026-09-26）
- [S84] Patro et al., *FairRec: Two-Sided Fairness for Personalized Recommendations in Two-Sided Platforms*, WWW 2020 — https://doi.org/10.1145/3366423.3380196 （2026-09-26）
- [S85] Korn & Muthukrishnan, *Influence sets based on reverse nearest neighbor queries*, SIGMOD 2000 — https://doi.org/10.1145/342009.335415 （2026-09-26）

**I. 工业参考**
- [S86] xai-org/x-algorithm README（33,426★，Apache-2.0，创建于 2026-01-19）— https://github.com/xai-org/x-algorithm （2026-09-26）
- [S87] SimClusters README — https://github.com/twitter/the-algorithm/blob/main/src/scala/com/twitter/simclusters_v2/README.md ；Satuluri et al., KDD 2020 — https://doi.org/10.1145/3394486.3403370 ；twitter/the-algorithm（73,945★，AGPL-3.0）https://github.com/twitter/the-algorithm （2026-09-26）
- [S88] Liu et al., *Monolith: Real Time Recommendation System With Collisionless Embedding Table* — https://arxiv.org/abs/2209.07663 ；https://github.com/bytedance/monolith（9,287★，已归档）（2026-09-26）
- [S89] *OneRec Technical Report*（快手）— https://arxiv.org/abs/2506.13695 （2026-09-26）
- [S90] Covington et al., *Deep Neural Networks for YouTube Recommendations*, RecSys 2016 — https://doi.org/10.1145/2959100.2959190 ；Yi et al., *Sampling-bias-corrected neural modeling for large corpus item recommendations*, RecSys 2019 — https://doi.org/10.1145/3298689.3346996 （2026-09-26）

**J. 学科分类体系**
- [S91] ACM CCS 2012 SKOS（第三方镜像）— https://github.com/cli99/acm-ccs ；官方页 https://www.acm.org/publications/class-2012 （2026-09-26 返回 Cloudflare 403）
- [S92] AEA JEL 分类树 XML — https://www.aeaweb.org/econlit/classificationTree.xml （2026-09-26）
- [S93] MSC2020 — https://msc2020.org/ ；https://msc2020.org/MSC_2020.csv （2026-09-26）
- [S94] PhySH（APS，CC0）— https://github.com/physh-org/PhySH （2026-09-26）
- [S95] NLM MeSH — https://www.nlm.nih.gov/mesh/meshhome.html ；SPARQL https://id.nlm.nih.gov/mesh/sparql （2026-09-26）

**K. 基础设施与仓库内文档**
- [S96] facebookresearch/faiss（40,985★，MIT）https://github.com/facebookresearch/faiss ；pgvector（23,161★，PostgreSQL 式许可）https://github.com/pgvector/pgvector ；asg017/sqlite-vec（8,137★，仓库含 LICENSE-MIT 与 LICENSE-APACHE 双许可文件（GitHub API 只识别出 Apache-2.0，核验修正）；最新稳定版 v0.1.9 于 2026-03-31，其后仅有 v0.1.10-alpha 预发布）https://github.com/asg017/sqlite-vec ；unum-cloud/USearch（4,320★，Apache-2.0）https://github.com/unum-cloud/USearch （2026-09-26）
- [S97] 仓库内文档与代码：[research/site-survey/metadata-apis.md](../../archive-v1.md#docs-research-site-survey-metadata-apis-md)（S2 限速、OpenAlex 计费）；[research/site-survey/aggregators-unpaywall-dblp-core.md](../../archive-v1.md#docs-research-site-survey-aggregators-unpaywall-dblp-core-md)（2026-07 DBLP robots 勘察）；[design/09-search-filter.md](../../archive-v1.md#docs-design-09-search-filter-md)；[research/github-similar-projects.md](../../archive-v1.md#docs-research-github-similar-projects-md)；`src/paper_crawler/adapters/dblp/adapter.py`（2026-09-26 读取）
- [S98] 并行调研：[market/startups-and-products.md](../market/startups-and-products.md)（2026-09-26）

**L. 核验补充来源**
- [S99] Li et al., *Multi-Interest Network with Dynamic Routing for Recommendation at Tmall*（MIND）— https://arxiv.org/abs/1904.08030 （2026-09-26，arXiv API 核对题名与摘要）
- [S100] Cen et al., *Controllable Multi-Interest Framework for Recommendation*（ComiRec）, KDD 2020 — https://arxiv.org/abs/2005.09347 （2026-09-26）
- [S101] Gingstad, Jekteberg, Balog, *ArXivDigest: A Living Lab for Personalized Scientific Literature Recommendation*, CIKM 2020 — https://arxiv.org/abs/2009.11576 ；https://github.com/iai-group/arXivDigest （28★，MIT）；并行调研 [oss/paper-acquisition-and-search-oss.md](../oss/paper-acquisition-and-search-oss.md)（2026-09-26）
- [S102] Chen, Zhang, Zhou, *Fast Greedy MAP Inference for Determinantal Point Process to Improve Recommendation Diversity* — https://arxiv.org/abs/1709.05135 ；YouTube/X 的 DPP 实践见并行调研 [algorithms/social-media-recsys.md](social-media-recsys.md)（2026-09-26）
- [S103] Stelmakh, Shah, Singh, *PeerReview4All: Fair and Accurate Reviewer Assignment in Peer Review* — https://arxiv.org/abs/1806.06237 ；实现与许可见并行调研 [oss/recommendation-oss.md](../oss/recommendation-oss.md)（2026-09-26）

## 核验记录

> **范围与方法**：对抗式事实核验，默认怀疑，只认一手来源。核验日期统一记为 2026-09-26（按 UTC；被访服务器 `Date` 头为 2026-09-26 19:2x GMT，本地时钟已进入 09-27 凌晨）。本节是文档中唯一的核验记录：核验开始时文档内没有核验记录节，也没有发现前次中断留下的半截修改（文件自 2026-09-26 23:45 定稿后未被改动）。
>
> **过程记录（可复现）**：
> - GitHub：用 `gh api repos/{owner}/{repo}` 取 star、许可、push 时间和归档状态；用 `gh api -H "Accept: application/vnd.github.raw" …/contents/{path}` 直读 arxiv-sanity-lite 的 `compute.py`/`serve.py`、zotero-arxiv-daily 的 `README.md` 与 `reranker/base.py`、x-algorithm、SimClusters、openreview-expertise/matcher、asta-paper-finder、scidocs 的 README，以及 PhySH 的 `physh.ttl` 和 `LICENSE.md`、scholar_inbox_datasets 的 `LICENSE`、Anubis 的 `web/static/robots.txt` 与 issue #532。
> - MTEB：用脚本逐个读取 `embeddings-benchmark/results/results/<model>/<rev>/<task>.json` 的 `main_score`，共抽查 11 个模型。
> - 论文：用 arXiv API（`export.arxiv.org/api/query?id_list=…`）一次批量核对 32 篇、补充核对 5 篇；arXiv HTML（2301.10140v2、2504.08385v2）；PDF 经 `pdftotext` 抽取（SPECTER、SciNCL、CTR、TPMS）；OpenAlex 单实体接口还原摘要（Pixie、PinSage、RECON、FairRec 等）并批量解析 31 个 DOI；Springer 摘要页（Beel 综述、Beel & Langer）。
> - 官方页面：OpenAlex 帮助中心 markdown（semantic-search、topics、example-costs、snapshot、tag-aboutness、works attributes）及 API 计数（约 6 次列表调用，每次约 $0.0001）；S2 swagger、datasets release 与 API 产品页；OpenAI、Anthropic、Voyage 定价页；OpenAI 嵌入指南；ORCID Public API；Zotero Web API；Google Scholar 博客 4 篇；Connected Papers 前端 bundle；Litmaps 帮助文章 2 篇；维基百科 CiteULike 条目；NLM MeSH 首页与 SPARQL；AEA JEL XML；MSC2020 CSV；DROPS dblp 快照集合页。
> - WebSearch 两次：`dblp Anubis bot protection robots.txt 2026`、`dblp XML monthly snapshot release DROPS Dagstuhl CC0 license download`。
> - 合规：全部请求使用诚实、可识别的 UA，只抓取 robots.txt 和 robots 允许的路径，事先查过 Springer、AEA、NLM、Google Scholar 博客、DROPS 的 robots。**没有访问任何被 robots 禁止的 dblp 页面**，因此 dblp 的 Anubis 挑战页未亲自复现，只以 robots.txt 与 Anubis 默认模板逐字节一致作为间接佐证。
> - 结论口径：**确认**＝一手来源与正文一致；**修正**＝已就地改正（正文内标"核验修正/核验补充"）；**删除**＝查无实据已删；**未核验**＝仍无法取得一手来源。本次没有发现需要删除的虚构仓库、论文或数字。

| 断言 | 结论 | 依据来源 URL | 核验日期 |
|---|---|---|---|
| arxiv-sanity-lite 的 TF-IDF 配置：1–2gram、2 万维、sublinear_tf、`min_df=5`、`max_df=0.1`、英文停用词 | 确认 | https://github.com/karpathy/arxiv-sanity-lite/blob/master/compute.py | 2026-09-26 |
| arxiv-sanity-lite 每次查询现训 `LinearSVC(class_weight='balanced', C=0.01)`，展示正权重前 40、负权重后 20 的词；仓库 1,696★、MIT | 确认 | https://github.com/karpathy/arxiv-sanity-lite/blob/master/serve.py | 2026-09-26 |
| S2 Research Feeds 的模型：TF-IDF 与 SPECTER 两个线性 SVM，取分数均值；负标注再补低权重随机负例 | 确认 | https://arxiv.org/html/2301.10140v2 | 2026-09-26 |
| S2 Research Feeds 的候选：FAISS 索引近 60 天约 100 万篇（每晚刷新），取正例质心附近约 500 篇 | 确认 | https://arxiv.org/html/2301.10140v2 | 2026-09-26 |
| Scholar Inbox 的训练：GTE-large 经 PCA 降到 256 维，每用户逻辑回归（加权 BCE），5k 随机负例，(C,V,S)=(0.1,0.8,5.0)，每次评分后重训 | 确认 | https://arxiv.org/html/2504.08385v2 | 2026-09-26 |
| Scholar Inbox 的冷启动：主动学习在决策边界附近及以上分层采样 | 确认 | https://arxiv.org/html/2504.08385v2 | 2026-09-26 |
| Scholar Inbox 的规模：注册用户 23k；80 万条评分来自 1.43 万用户；Scholar Maps 覆盖 300 万篇（Qwen 生成 4 级标签） | 确认 | https://arxiv.org/html/2504.08385v2 | 2026-09-26 |
| Scholar Inbox 表 2 全部数字；V 从 0 升到 0.9 时显式负例特异度 68%→78% | 确认 | https://arxiv.org/html/2504.08385v2 | 2026-09-26 |
| Scholar Inbox 计划支持多兴趣切换，并批评社媒式推荐的马太效应；论文 v2 为 2025-06-14、CC BY 4.0 | 确认 | https://arxiv.org/html/2504.08385v2 | 2026-09-26 |
| Scholar Inbox 评分数据集许可为"NOASSERTION ⚠" | **修正**：`LICENSE` 为 CC BY-NC-ND 4.0，仅限非商业、禁止演绎（GitHub API 未识别许可才显示 NOASSERTION）；§2.4、§2.9、§3.1 第 17 条、§3.2、§4 第 4 条已同步 | https://github.com/avg-dev/scholar_inbox_datasets/blob/main/LICENSE | 2026-09-26 |
| MTEB 科学任务分数（抽查 11 个模型：Qwen3-Emb-8B/0.6B、gte-large、BGE-M3、te3-large、gemini-embedding-001、jina-v5-nano、NV-Embed-v2、voyage-3-large、voyage-3.5、BM25s） | 确认：逐文件读取的 `main_score` 与正文一致 | https://github.com/embeddings-benchmark/results | 2026-09-26 |
| BRIGHT-Pro 经济/心理/生物三项的 nDCG@10（Qwen3-Emb-8B、BGE-M3、BM25s） | 确认 | https://github.com/embeddings-benchmark/results | 2026-09-26 |
| OpenAI te3-large 的 SciFact、SciDocsRR 两列标"—"（结果库无文件） | **修正**：结果库有旧格式文件，分别为 0.778 和 0.867，表中以 ◇ 标注 | https://github.com/embeddings-benchmark/results/tree/main/results/openai__text-embedding-3-large/1 | 2026-09-26 |
| SPECTER2 不在 MTEB 结果库；voyage-4 系列无科学任务分数 | 确认（voyage 条目在 `mongodb__` 前缀下） | https://github.com/embeddings-benchmark/results | 2026-09-26 |
| SCIDOCS 任务定义：以论文标题检索其所引论文摘要，主指标 nDCG@10，数据许可 CC-BY-SA-4.0 | 确认 | https://github.com/embeddings-benchmark/mteb/blob/main/mteb/tasks/retrieval/eng/scidocs_retrieval.py | 2026-09-26 |
| 非商用或研究许可的嵌入模型：jina v3/v5 与 NV-Embed-v2 为 CC-BY-NC-4.0；jina v4 为 Qwen Research License；embeddinggemma 为 Gemma 许可（gated） | 确认 | https://huggingface.co/jinaai/jina-embeddings-v4 ；https://huggingface.co/jinaai/jina-embeddings-v5-text-nano ；https://huggingface.co/nvidia/NV-Embed-v2 ；https://huggingface.co/google/embeddinggemma-300m | 2026-09-26 |
| 可商用许可的嵌入模型：Qwen3-Emb、gte-Qwen2、nomic、snowflake-arctic、SPECTER2 为 Apache-2.0；gte-large、BGE-M3、e5、SciNCL、PubMedNCL 为 MIT | 确认 | https://huggingface.co/Qwen/Qwen3-Embedding-8B ；https://huggingface.co/allenai/specter2 ；https://huggingface.co/thenlper/gte-large 等（见 [S13]） | 2026-09-26 |
| jina-embeddings-v5-text：2026-02-18 发布；small 为 677M、1024 维、32K，自报 MTEB 英文 v2 71.7、MMTEB 67.7；nano 为 239M；由 Qwen3-Embedding-4B 蒸馏 | 确认 | https://huggingface.co/jinaai/jina-embeddings-v5-text-small ；https://arxiv.org/abs/2602.15547 | 2026-09-26 |
| Qwen3-Embedding-8B：截至 2025-06-05 居 MTEB 多语榜第 1（70.58）；任务指令一般提升 1%–5%；输出维度 32–4096 可调；上下文 32K | 确认 | https://huggingface.co/Qwen/Qwen3-Embedding-8B | 2026-09-26 |
| SPECTER2：Apache-2.0；超过 600 万条引文三元组，另在 8 个任务上训练格式适配器；覆盖 23 个领域 | 确认 | https://huggingface.co/allenai/specter2 ；[S5] | 2026-09-26 |
| SPECTER2 模型卡的结果：SciRepEval 平均 71.1；MDCR 上 BM25 33.7 高于 SPECTER 30.6 和 SciNCL 32.6，SPECTER2 为 38.4 | 确认 | https://huggingface.co/allenai/specter2 | 2026-09-26 |
| SPECTER：SciDocs 平均 80.0；recomm 任务 22K 点击；线上 A/B 在 4,113 次点击上 CTR +46.5% | 确认；补充 SciDocs README 勘误：论文所列训练样本数 20K 应为 4K | https://arxiv.org/pdf/2004.07180 ；https://github.com/allenai/scidocs | 2026-09-26 |
| recomm 任务"Doc2Vec 51.7 → SciNCL 54.3"整体引用 [S6] | **修正引用**：51.7（及随机嵌入 51.3）出自 SPECTER 表 1 [S1]；54.3 是 SciNCL 无泄漏训练的结果 [S6] | https://arxiv.org/pdf/2004.07180 ；https://arxiv.org/pdf/2202.06671 | 2026-09-26 |
| SGC 与 SPECTER 对比：cite MAP 91.6 对 88.3，co-view MAP 77.2 对 83.6；SciNCL 平均 81.8（10 个 seed） | 确认 | https://arxiv.org/pdf/2202.06671 | 2026-09-26 |
| zotero-arxiv-daily：5,992★、AGPL-3.0；默认模型 `jina-embeddings-v5-text-nano`；权重 `1/(1+log10(i+1))` 归一化后 ×10；四个来源；pymupdf4llm 抽全文供 LLM 写 TL;DR | 确认 | https://github.com/TideDra/zotero-arxiv-daily | 2026-09-26 |
| OpenAlex 语义检索：gte-large 1024 维（标题+摘要），输入 ≤2,000 字符，每次 ≤50 条，1 req/s，$1/千次 | 确认 | https://help.openalex.org/api/semantic-search ；https://help.openalex.org/access/example-costs | 2026-09-26 |
| OpenAlex Topics 层级：4/26/252/4,516；每篇 ≤3 个 topic；约 12% 无 topic（3.22 亿中的 3,960 万）；CWTS 引文聚类加 LLM 命名 | 确认 | https://help.openalex.org/data/topics | 2026-09-26 |
| OpenAlex 各 field 的 subfield 数（经济 3、商管 9、心理 7、数学 10、化学 6、医学 42）；SimClusters 论文被分到的 topic | 确认 | https://api.openalex.org/fields?per-page=50 ；https://api.openalex.org/works/doi:10.1145/3394486.3403370 | 2026-09-26 |
| OpenAlex field 与 ASJC 吻合（原标"本文比对 ⚠"） | **修正**：官方说明 topic 按 Scopus ASJC 映射到 subfield/field/domain | https://help.openalex.org/data/topics | 2026-09-26 |
| OpenAlex 的计费与快照：`/text` 为 $0.01/次、1 req/s，费用页标 deprecated；快照 JSONL 约 745 GB，许可 CC0 | 确认 | https://help.openalex.org/api/tag-aboutness ；https://help.openalex.org/access/snapshot ；https://openalex.s3.amazonaws.com/LICENSE.txt | 2026-09-26 |
| OpenAlex `related_works` 的定义；2026-08 的 article 与 preprint 共 710,965 篇，arXiv 源 30,163 篇 | 确认（计数复跑一致） | https://help.openalex.org/data/works/attributes ；https://api.openalex.org/works?filter=from_publication_date:2026-08-01,to_publication_date:2026-08-31,type:article%7Cpreprint | 2026-09-26 |
| S2 Datasets 2026-09-22 版含 embeddings-specter_v2、tldrs 等；Graph API 支持 `embedding.specter_v2` | 确认 | https://api.semanticscholar.org/datasets/v1/release/latest ；https://api.semanticscholar.org/graph/v1/swagger.json | 2026-09-26 |
| S2 预计算向量"再分发许可需按 S2 条款核实 ⚠" | **修正/补充**：release README 标注 `embeddings-specter_v1/v2` 为 Apache-2.0，`papers`/`abstracts`/`tldrs`/`citations`/`s2orc` 等为 ODC-BY；API 协议要求署名"Semantic Scholar"、禁止转售或再许可 API；摘要文字本身的版权仍 ⚠ 待法务 | https://api.semanticscholar.org/datasets/v1/release/latest ；https://www.semanticscholar.org/product/api/license | 2026-09-26 |
| S2 推荐 API：正/负论文 ID 列表；`forpaper` 端点 `from=recent\|all-cs`，默认 recent；`limit` 默认 100、上限 500 | 确认 | https://api.semanticscholar.org/recommendations/v1/swagger.json | 2026-09-26 |
| S2 有 key 限速 1 req/s（原仅引仓库 7 月勘察） | 确认：官方页写明入门限速 1 RPS、全端点 | https://www.semanticscholar.org/product/api | 2026-09-26 |
| "S2 需 API key" | **修正**：无 key 也可调用，全体未认证用户共享 1000 RPS 池 | https://www.semanticscholar.org/product/api | 2026-09-26 |
| 三个 dblp 域名的 robots.txt 均为 `User-agent: * / Disallow: /` | 确认：三份文件相同（163 个具名 AI 爬虫加通配全禁，无 Crawl-delay） | https://dblp.org/robots.txt ；https://dblp.uni-trier.de/robots.txt ；https://dblp.dagstuhl.de/robots.txt | 2026-09-26 |
| dblp 的 robots.txt 来源（核验补充） | 与 Anubis 默认 `web/static/robots.txt` 逐字节一致（md5 相同）；这是否 dblp 有意的政策仍 ⚠ **未核验** | https://github.com/TecharoHQ/anubis/blob/main/web/static/robots.txt ；https://github.com/TecharoHQ/anubis/issues/532 | 2026-09-26 |
| "dblp 月度快照渠道与许可 ⚠ 未核验" | **修正/补充**：DROPS 集合 `10.4230/dblp.xml` 为 CC0 1.0，最新 2026-09-01 版；DROPS robots 只禁 `/api/*` 等三类路径 | https://drops.dagstuhl.de/entities/collection/10.4230/dblp.xml ；https://drops.dagstuhl.de/robots.txt | 2026-09-26 |
| v1 DBLP adapter 按 `Crawl-delay: 4` 与 `/db/conf/**` 允许区实现 | 确认：仓库代码与 2026-07-22 勘察一致 | `src/paper_crawler/adapters/dblp/adapter.py` ；[aggregators-unpaywall-dblp-core.md](../../archive-v1.md#docs-research-site-survey-aggregators-unpaywall-dblp-core-md) | 2026-09-26 |
| ORCID：`pub.orcid.org/robots.txt` 为 `Disallow: /`；Public API 面向非会员，需注册凭证并同意 Public APIs ToS | 确认 | https://pub.orcid.org/robots.txt ；https://info.orcid.org/documentation/features/public-api/ | 2026-09-26 |
| Zotero Web API：`limit` 默认 25、上限 100；用 `Last-Modified-Version`/`since=` 做增量；遵守 `Backoff`、429 与 `Retry-After`；一般不超过 4 个并发 | 确认 | https://www.zotero.org/support/dev/web_api/v3/basics | 2026-09-26 |
| OpenAI 定价：gpt-5-nano、gpt-5-mini（含批处理价）；te3-small $0.02、te3-large $0.13 | 确认 | https://developers.openai.com/api/docs/pricing | 2026-09-26 |
| Anthropic 定价：Haiku 4.5 为 $1/$5，Sonnet 5 为 $2/$10，批处理半价，缓存命中 0.1×；Claude 4.7 及以后的新分词器约多 30% token | 确认；补充：Sonnet 5 引入价已转为标准价，原定 2026-09-01 的涨价取消 | https://platform.claude.com/docs/en/about-claude/pricing | 2026-09-26 |
| Voyage 定价：3-large $0.18、3.5 $0.06；4-large/4/4-lite 为 $0.12/$0.06/$0.02，各含 2 亿免费 token | 确认 | https://docs.voyageai.com/docs/pricing | 2026-09-26 |
| §2.6.6 成本表、§2.10.2 与 §3.1 第 6 条的规模估算 | 确认：按上列单价和文中假设逐项复算一致（仍属估算） | 同上三个定价页 | 2026-09-26 |
| OpenAI 嵌入：MTEB 平均 62.3% 与 64.6%；3-large 截到 256 维仍优于 ada-002 | 确认 | https://developers.openai.com/api/docs/guides/embeddings | 2026-09-26 |
| x-algorithm 仓库：2026-01-19 建库、Apache-2.0、33,427★ | 确认 | https://github.com/xai-org/x-algorithm | 2026-09-26 |
| x-algorithm 排序机制：多动作概率加权；作者衰减、站外折扣、New-Author Boost；候选隔离使分数可缓存；哈希嵌入；排序与可见性分离；负向动作清单；user-cred-v2 用 PageRank | 确认 | https://github.com/xai-org/x-algorithm | 2026-09-26 |
| SimClusters：覆盖前 2,000 万生产者，约 14.5 万社区；推文向量初始为空，每次点赞累加点赞者的 InterestedIn；话题向量带时间衰减 | 确认 | https://github.com/twitter/the-algorithm/blob/main/src/scala/com/twitter/simclusters_v2/README.md | 2026-09-26 |
| OpenReview expertise：集成权重 0.8/0.2 与 0.5/0.5；审稿人分数取 max（默认）或 average；损失表 TPMS 0.28 至 SPECTER2+SciNCL 0.21（易/难 0.91/0.65） | 确认 | https://github.com/openreview/openreview-expertise | 2026-09-26 |
| openreview-matcher 的六个求解器 | 确认 | https://github.com/openreview/openreview-matcher | 2026-09-26 |
| Stelmakh 金标准：58 人、477 条自评；误排率 12%–30% 与 36%–43%；标题+摘要时 SPECTER2 最好；给全文时 TF-IDF 持平；现成 LLM 落后 | 确认 | https://arxiv.org/abs/2303.16750 | 2026-09-26 |
| LLM 与检索论文的数字：LitSearch 597 条、24.8 点、+4.4%；RankGPT 的 440M 模型胜过 3B；LLMRank 的偏置；LACE 为 3 个任务、6 个数据集；PaperWeaver N=15 | 确认 | https://export.arxiv.org/api/query?id_list=2407.18940,2304.09542,2305.08845,2304.04250,2403.02939 | 2026-09-26 |
| LFM："冷启动优于矩阵分解，紧凑画像不劣于直接喂全量历史" | **修正**：补充实验用的是 MovieLens（电影评分，非学术场景），且原文措辞为"冷启动下准确率可高于"MF | https://arxiv.org/abs/2402.15623 | 2026-09-26 |
| SciDocs 有 7 个任务，S2 团队自 2022-12 起建议改用 SciRepEval；SciRepEval 为 24 个任务、4 种格式 | 确认 | https://github.com/allenai/scidocs ；https://arxiv.org/abs/2211.13308 | 2026-09-26 |
| 推荐系统论文的数字：LinUCB（3,300 万事件、+12.5%）；Ferrari Dacrema（18/7/6）；RECON（23%→42%、冷启动 26%）；OneRec（10.6%、25% QPS、+0.54%/+1.24%） | 确认 | https://export.arxiv.org/api/query?id_list=1003.0146,1907.06902,2506.13695 ；https://api.openalex.org/works/doi:10.1145/1864708.1864747 | 2026-09-26 |
| Pinterest 图规模：Pixie 为 30 亿节点、170 亿边、单机 1,200 rps、60 ms、贡献 80% 以上互动；PinSage 为 30 亿节点、170 亿边 | 确认 | https://api.openalex.org/works/doi:10.1145/3178876.3186183 ；https://api.openalex.org/works/doi:10.1145/3219819.3219890 | 2026-09-26 |
| CTR 的 CiteULike 数据统计；TPMS 的历史与模型 | 确认 | http://www.cs.columbia.edu/~blei/papers/WangBlei2011.pdf ；https://www.cs.toronto.edu/~lcharlin/papers/tpms.pdf | 2026-09-26 |
| 综述与评估：Beel 综述的 55/18/16/81%；Beel & Langer 发现离线与在线结论矛盾；FairRec 保证 MMS/EF1 | 确认 | https://link.springer.com/article/10.1007/s00799-015-0156-0 ；https://link.springer.com/chapter/10.1007/978-3-319-24592-8_12 ；https://api.openalex.org/works/doi:10.1145/3366423.3380196 | 2026-09-26 |
| 2025–2026 新论文确实存在，元数据相符：MERIT（EMNLP 2026）、PaperFlow（24 名模拟用户、50 天、1,200 个用户日、20,727 篇）、BRIGHT-Pro（ACL 2026）、SteerEval、LangPTune、LettinGo、PURE、Qilin | 确认 | https://export.arxiv.org/api/query?id_list=2605.27865,2606.07454,2605.04018,2601.21105,2410.18870,2506.18309,2502.14541,2503.00501 | 2026-09-26 |
| §5 所列 31 个 DOI 均为真实文献 | 确认：全部解析到对应的题名与作者，未发现虚构文献 | https://api.openalex.org/works/doi:{DOI} | 2026-09-26 |
| Google Scholar 推荐功能：2012 Updates 的建模信号（含"兴趣随时间变化"）；2017 可关注学者相关研究；2021 Reloaded 支持手机滑动与邮件订阅 | 确认 | [S43]–[S45] 所列 scholar.googleblog.com 博文 | 2026-09-26 |
| Google Scholar Quick Read：2026-08-25 发布，仅对用户有权访问的论文提供 | 确认 | https://scholar.googleblog.com/2026/08/quick-read-see-how-paper-answers-your.html | 2026-09-26 |
| Connected Papers：每张图约 5 万篇；相似度基于共被引与文献耦合；力导向布局；数据来自 S2（ODC-BY） | 确认 | https://www.connectedpapers.com/about（前端 bundle 文案） | 2026-09-26 |
| Litmaps：三种算法，默认 Shared Citations & References；库容 2.7 亿篇以上；称法律上只能索引开放元数据 | 确认 | https://docs.litmaps.com/en/articles/9029858-search-algorithms-in-litmaps ；https://docs.litmaps.com/en/articles/7212085-litmaps-database-coverage-open-access-and-article-indexing | 2026-09-26 |
| CiteULike"2019-03-28 关闭" | **修正**：宣布 2019-03-30 停止运营，信息框记 2019-03-28 起离线 | https://en.wikipedia.org/wiki/CiteULike | 2026-09-26 |
| ACM CCS 2012：2,299 个概念、14 个顶层、98 个多父节点、最深 6 层 | 确认（数据来自第三方镜像；官方页仍未取回） | https://github.com/cli99/acm-ccs | 2026-09-26 |
| JEL 20/139/856；MSC2020 为 63/534/6,006（共 6,603 行） | 确认 | https://www.aeaweb.org/econlit/classificationTree.xml ；https://msc2020.org/MSC_2020.csv | 2026-09-26 |
| PhySH：19 个学科、9 个 facet、3,882 个概念；v2.8.0；CC0 | 确认 | https://github.com/physh-org/PhySH | 2026-09-26 |
| MeSH 当前 RDF 图：30,594 个主题词、84 个限定词 | 确认；图对应的年份仍 ⚠ **未核验**（官网称 RDF 目前为 2025 版） | https://id.nlm.nih.gov/mesh/sparql ；https://www.nlm.nih.gov/mesh/meshhome.html | 2026-09-26 |
| GitHub 元数据（faiss、pgvector、USearch、Monolith 已归档、the-algorithm、asta-paper-finder 的 fast≈30 s/diligent≈3 min、specter、scincl、sqlite-vec v0.1.9） | 确认：star 与正文相差不超过 1 | 各仓库 `gh api repos/{owner}/{repo}` | 2026-09-26 |
| sqlite-vec 许可为 Apache-2.0 | **修正**：仓库同时含 MIT 与 Apache-2.0 两份许可文件 | https://github.com/asg017/sqlite-vec | 2026-09-26 |
| 覆盖缺口：学习型多兴趣召回（MIND、ComiRec）、DPP 多样化、PeerReview4All、arXivDigest living lab | **核验补充**：经 arXiv API 核对题名与摘要，经 GitHub 核对仓库，已加入 §2.8、§2.9、§2.10.1 与 [S99]–[S103] | https://arxiv.org/abs/1904.08030 ；https://arxiv.org/abs/2005.09347 ；https://arxiv.org/abs/1709.05135 ；https://arxiv.org/abs/1806.06237 ；https://arxiv.org/abs/2009.11576 | 2026-09-26 |

**仍需注意（未核验或需主 agent 裁决）**：
- dblp 全站 Disallow 究竟是有意政策，还是 Anubis 部署带来的默认值，需要向 dblp 团队确认 ⚠。
- ACM CCS 官方页因 Cloudflare 返回 403，计数只来自第三方镜像。
- MeSH SPARQL 图对应的年份未确认 ⚠。
- S2、Crossref 等来源的摘要文字能否在多用户卡片流中展示，涉及出版社或作者的著作权，数据库层许可（ODC-BY、CC0）不能替代这一判断，需法务裁决 ⚠。
- 依赖 LLM 定价的成本估算需按月复核，Sonnet 5 在 ×1.3 分词器系数下的实际 token 数应以 `count_tokens` 实测为准。
- 以上都已在正文对应位置标注。
