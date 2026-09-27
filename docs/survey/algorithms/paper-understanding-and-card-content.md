---
title: 技术调研：论文理解与卡片内容生成（TL;DR、关键图、翻译、标签）
status: draft
owner: opus5.5-survey
updated: 2026-09-26
---

# 技术调研：论文理解与卡片内容生成（TL;DR、关键图、翻译、标签）

> **定位**：v2 重设计中"把一篇论文变成一张好卡片"所需的内容理解技术、成本与合规边界的调研底稿。本文只做调研与设计建议，**不含实现代码**；文中代码块均为**设计伪代码**。
> **引用约定**：正文 `[Rxx]` 对应 §5 参考来源（URL + 访问日期；除另注外均为 2026-09-26 访问核验）；`[Ex]` 为本轮一手实测（§1.4，原始数据在同名子目录 `paper-understanding-and-card-content/`）。
> **证据分级**：**A** 官方文档/源码/论文/法规原文；**B** 本轮一手实测（API 返回、页面解析、离线计量）；**C** 二手媒体/检索摘要。"⚠ 未核验" = 本轮无法用一手来源证实；"⚠ 推断" = 由已核验事实推理得到、未经实测；【合规】= 硬约束。
> **与既有文档的分工**：PDF 解析器的 star/许可全表见 [oss/paper-acquisition-and-search-oss §2.9](../oss/paper-acquisition-and-search-oss.md)；卡片信息架构与 UI 见 [ux/card-feed-interaction §2.6](../ux/card-feed-interaction.md)；聚合源字段/摘要法律边界见 [sources/aggregators-repositories](../sources/aggregators-repositories.md)；许可门控共享层规则见 [sources/life-sciences-psychology §3 第 3 条](../sources/life-sciences-psychology.md)；竞品"AI 速读"先例见 [market/startups-and-products I-11/I-12](../market/startups-and-products.md)。本文不重复这些内容，只在其上补"内容生成"这一层的事实、实测与方案。

---

## 0. 结论先行（TL;DR）

1. **LLM 生成费用不是瓶颈**：按实测 token（标题+摘要均值 257 tokens）与 2026-09-26 官方价，"卡片基础包"（EN/ZH TL;DR + 中文标题 + 关键词）每千篇 **$0.06（gpt-5-nano Batch）～ $3.44（Claude Sonnet 5 标准价）**；日增 3 万篇、30% 进候选集、5% 打开详情的最大场景，月成本 **$26～$806**（按 o200k 计数；Claude Sonnet 5 属官方所称"Claude 4.7 及以后"新分词器，同文本约多 30% token，计入后上限约 $1,050——核验补充，⚠ 推断）。真正的成本与风险在 **全文获取/解析、质检人力与版权合规**（§2.6）。
2. **Semantic Scholar TLDR 不能当主源**：字段免费（ODC-BY，需署名），但实测覆盖严重偏科——arXiv 样本 cs.CL/cs.CV 92–98%、q-bio.NC 72–88%，而 hep-th **0%**、cond-mat 8–10%、math.PR 12–15%；带 CS/医学/生物 fieldsOfStudy 的论文 85% 有 TLDR，其余 **334 篇仅 1 篇**有 [E1]。模型 `tldr@v2.0.0` 高度抽取式（平均 81% 的 4-gram 直接取自摘要），2.4% 出现复读退化 [E1]。定位为 **CS/生医的零成本兜底与对照**。
3. **幻觉控制要选"非推理小模型 + 规则/NLI 双闸"**：Vectara HHEM 榜（2026-09-22）上 gpt-5.4-nano 3.1%、gemini-2.5-flash-lite 3.3%、qwen3-8b 4.8% 幻觉率，远低于推理型（o4-mini 18.6%、o3-pro 23.3%）[R14]（核验注：gpt-5.4-nano 本身支持推理，`reasoning.effort` 默认 `none`，榜单未注明调用时的推理档 [R81]，故"非推理"指以默认/最低推理档调用）；LLM 科学摘要的**过度概括**是比"编造"更隐蔽的风险（26–73%，比人写摘要高 4.85 倍；新模型更差）[R13]。
4. **关键图优先"免解析"通道**：arXiv HTML（LaTeXML）在近期列表中 **88.6%** 可得 [E4]，页面直接给出图片文件（SVG/PNG）、图注与**论文许可行**；生医走 PMC/Europe PMC JATS；PDF 解析（GROBID 坐标 + pypdfium2 裁剪，或 Docling）只做兜底。
5. **图片展示的许可闸决定了"有图卡片"的上限**：arXiv 新记录中仅 **39.5%** 为 CC BY/BY-SA/CC0（可含商用展示），51.6% 为 arXiv 非独占许可（**不可再利用**）[E3]；OpenAlex 2026-03 全部新文章中许可**未知 38.4%**、CC BY 38.1% [E6]。无许可 = 用排版封面（UX 文档已定）。
6. **翻译 = 演绎**：CC 4.0 法律文本把"translated"明列为 Adapted Material [R39]；arXiv 摘要属 CC0 元数据可自由翻译 [R30][R31]，但 Crossref 中的出版商摘要"可能受版权保护、第三方转载需版权人明确许可"[R40]——**共享层的中文摘要只能来自可共享来源**。
7. **用一次 LLM 调用替代 NMT API**：DeepL/Google NMT 翻译一篇标题+摘要约 **$17–31/千篇**，比小模型贵约 100 倍，且 29% 的 arXiv 摘要含 LaTeX（math.PR 67%）[E8] 需原样保留。
8. **标签用受控词表，关键词只做检索扩展**：OpenAlex Topics（4 domains/26 fields/252 subfields/4,516 topics，记录自带、免费）、arXiv 155 个类目（CC0）、PhySH（CC0）等作展示/过滤标签；KeyBERT（MIT）或 LLM 关键词只用于检索扩展与"why-this"。
9. **按需生成 + 内容寻址缓存**：只对进入候选集的论文生成基础包；中文全文摘要、关键图、结构化要点在详情打开时生成；auth-gated 内容只在私有层为本人生成（不进共享缓存）。
10. **AI 标识是法定义务而非可选 UI**：中国《人工智能生成合成内容标识办法》2025-09-01 起施行（文本需显式提示 + 文件元数据隐式标识）[R68]；EU AI Act 第 50 条自 2026-08-02 适用（无人工编辑责任的公共议题文本需披露）[R71]。
11. **学科差异决定卡片形态**：CS/生医可做"全功能卡片"（S2 兜底 + 关键图 + 代码链接）；数学/物理以自生成 + LaTeX 渲染为主；经济/金融/管理与心理的主干期刊摘要虽在 Crossref 可得（样本 18–20/20）但版权保留，**共享 TL;DR/翻译要等法务结论**，在此之前只能私有即时生成（§2.9）。

---

## 1. 调研范围与方法

### 1.1 范围

| # | 子主题 | 本文回答的问题 |
|---|---|---|
| ① | TL;DR / 一句话摘要 | 现成来源（S2 TLDR、HF ai_summary）可得性与许可；LLM 生成的提示设计、质量评估与幻觉控制 |
| ② | 关键图 | 取图通道（arXiv HTML、PMC JATS、PDF 解析器）对比；如何选"关键图"；各源许可字段与展示闸 |
| ③ | 多语种 | 中文标题/摘要翻译的模型选择、成本、许可与质量评估 |
| ④ | 自动标签 | OpenAlex Topics、arXiv 类目、LLM 零样本、KeyBERT 等的可得性、精度与许可 |
| ⑤ | 结构化要点 + 代码/数据链接 | 贡献/方法/数据集/结论/局限抽取；GitHub/数据集链接来源 |
| ⑥ | 成本 | 本地小模型 vs API（2026-09 价格）每千篇成本、延迟、缓存与按需策略 |
| ⑦ | 质量评估 | 每类字段的离线/在线指标、工具与许可 |
| — | 输出 | 卡片内容生成流水线（取源/生成/按需/私有）+ 合规注意 |

**不在范围**：推荐排序（见 [algorithms/scholarly-recommendation-and-matching](scholarly-recommendation-and-matching.md)）、卡片 UI 动效（见 UX 文档）、全文抽取器横评（见 OSS 文档 §2.9）。本轮**未调用任何付费 LLM API、未使用用户凭证**（S2/OpenAlex 均为匿名额度），因此没有"生成质量"的一手对比，只有价格、覆盖率与结构类实测。

### 1.2 方法

1. **一手实测（B 级）**：对 arXiv、Semantic Scholar、Hugging Face Papers、OpenAlex、Crossref 做 8 项小样本测量（§1.4），全部遵守 robots.txt / ToU 与保守限速（arXiv API 1 请求/3.5 s 单连接，arxiv.org 页面遵守 `Crawl-delay: 15`，S2 匿名池遇 429 指数退避，Crossref 公共池 1 请求/2 s）。
2. **官方文档/源码核验（A 级）**：价格页、许可文本、API 文档、GitHub README（`gh api` 取 star/license/pushed_at）、论文摘要（arXiv API 按 id_list 一次核验 27 篇）。
3. **法规原文核验**：国家网信办官网（标识办法、深度合成规定、生成式 AI 暂行办法）与欧盟委员会 FAQ。
4. **既有调研复用**：兄弟文档已核验的事实以"见 xx 文档"引用，不重复请求。

### 1.3 与 v1 的衔接点（实现现状）

- v1 的 `s2` enrich 通道已按 `fields=title,externalIds,citationCount,tldr,fieldsOfStudy,openAccessPdf` 批查，并把 `tldr.text` 写入 `meta["tldr"]`（`src/paper_crawler/adapters/s2/adapter.py`、`parse.py`；设计见 [design/adapters/aggregators.md §5](../../archive-v1.md#docs-design-adapters-aggregators-md)）——v2 可直接沿用为兜底/对照字段。
- v1 的 stage 5 extract 为 **pypdf 基线 + GROBID 可选增强**，且 GROBID 的三个 `consolidate*` 参数硬编码为 0（零外网）[design/12-fulltext-extract](../../archive-v1.md#docs-design-12-fulltext-extract-md)——v2 的"结构化要点"可复用其落盘的 `.tei.xml`。**核验修正（2026-09-26 读源码）**：v1 请求 `processFulltextDocument` 时只传三个 `consolidate*=0`（`src/paper_crawler/pipeline/extract.py` 的 `_CONSOLIDATE_OFF`），**未传 `teiCoordinates`**，现有 TEI 中没有图坐标；若要复用于选图，需新增 `teiCoordinates=figure` 参数（属 design/12 的变更）。
- v1 schema 无许可字段（相关的只有 `paper.abstract`、`paper.meta_json` 与 `fulltext`/`asset` 表；`fulltext_asset` 是 0004 迁移文件名而非表名——核验修正），v2 必须新增字段级许可/可共享性/AI 生成标记（§3 启示 16）。

### 1.4 过程记录（可复现）

**一手实测清单**（原始数据：[`paper-understanding-and-card-content/`](paper-understanding-and-card-content/)）：

| 编号 | 实测 | 方法（端点/参数） | 样本 | 时间（UTC） | 数据文件 |
|---|---|---|---|---|---|
| E1 | S2 TLDR 覆盖与质量（arXiv） | arXiv Query API `cat:{c} AND submittedDate:[…]` 各取最新 40 篇 × 10 类 × 2 窗（2026-03 / 2026-09-14..24）→ S2 `POST /graph/v1/paper/batch?fields=tldr,externalIds,s2FieldsOfStudy,publicationDate`（匿名） | 744 条（730 篇去重），743 篇在 S2 | 19:25–19:31 | `s2-tldr-coverage-2026-09-26.tsv`、`arxiv-sample-stats-2026-09-26.json` |
| E2 | S2 TLDR 覆盖（期刊） | Crossref `/journals/{issn}/works?filter=from-pub-date:2026-01-01,until-pub-date:2026-06-30,type:journal-article&rows=20` × 9 刊 → S2 batch（DOI） | 176 篇 | 19:42 | 同上 |
| E3 | arXiv 许可分布 | OAI-PMH `ListRecords&metadataPrefix=arXiv&set={cs,math,physics,q-bio,q-fin,stat,econ,eess}&from=until=2026-09-22`（每 set 仅首页）[R33] | 4,568 条记录 | 19:33 | `arxiv-license-dist-2026-09-26.json` |
| E4 | arXiv HTML 可得率 | `arxiv.org/list/{c}/recent?skip=0&show=250`，统计列表中带 `arxiv.org/html/` 链接的比例（请求间隔 16 s） | 989 篇 × 7 类 | 19:35–19:37 | `arxiv-html-availability-2026-09-26.json` |
| E5 | HF Papers 覆盖 | `GET huggingface.co/api/papers/{arxiv_id}`（robots 全允许，1 请求/1.2 s） | 158 篇（2026-03 窗 4 类） | 19:30–19:34 | `hf-papers-coverage-2026-09-26.json` |
| E6 | OpenAlex 许可字段覆盖 | `/works?filter=…&group_by=best_oa_location.license`（无 key，单次 $0.0001）[R44] | arXiv 2026-03：34,212；全部文章 2026-03：778,166 | 19:41 | `openalex-license-groupby-2026-09-26.json` |
| E7 | Token 计量 | `tiktoken` o200k_base 离线计 730 篇标题/摘要；中文 token/字比用标识办法原文 2,620 字测 | 730 篇 | 19:37 | `arxiv-sample-stats-2026-09-26.json` |
| E8 | LaTeX 与代码链接占比 | 正则统计标题+摘要中的 `$…$`/`\cmd`；摘要+arXiv comments 中的 github/gitlab/huggingface 链接 | 730 篇 | 19:30 | 同上 |

**请求台账**：共 225 次外部请求（arXiv Query API 21、OAI-PMH 9、arxiv.org 列表/HTML/分类页 9、S2 13（含 9 次 429 退避）、HF Papers 160（143 次 404 = 未收录）、OpenAlex 4（合计 $0.0013 匿名额度）、Crossref 9），逐条见 `request-ledger-2026-09-26.tsv`。另有约 60 次 WebFetch/curl 读取官方文档页（见 §5）。

**robots/访问边界**：arxiv.org `Crawl-delay: 15`，允许 `/list /abs /pdf /html`、禁 `/api /search` 等 [R32]；export.arxiv.org 为 `Disallow: /`，本轮与 v1 一致只走 ToU 明示的 Query API（依据见 [design/adapters/arxiv.md](../../archive-v1.md#docs-design-adapters-arxiv-md)）；oaipmh.arxiv.org 无 robots（404）；huggingface.co `Allow: /`。**受阻未绕过**：kexue.fm（Cool Papers 作者博客）403；DeepL 帮助中心 403；ieeexplore.ieee.org 的 robots 对 GPTBot 等 AI 爬虫全禁，本轮未访问；智谱开放平台价格页为纯 JS，未取得价格。

**主要检索式**（WebSearch，2026-09-26）：`Semantic Scholar TLDR feature launch 2020`；`Peters Chin-Yee generalization bias LLM summarization`；`arXiv HTML LaTeXML December 2023 success rate`；`"Identifying the Central Figure of a Scientific Paper" ICDAR 2019`；`OpenAlex topic classification model Hugging Face`；`vLLM benchmark Llama 3.1 8B H100 throughput`；`qwen-mt-flash price`；`DeepL API pricing 2026`；`人工智能生成合成内容标识办法 显式标识 隐式标识`；`生成式人工智能服务管理暂行办法 第十七条`；`Digital Omnibus AI Act Article 50(2) grace period`；`Data Citation Corpus DataCite`；`Google Scholar Quick Read 2026`；`Cool Papers papers.cool Kimi FAQ`。

**复现提示**：E1/E2/E5 依赖 S2 匿名共享池（常 429），复测建议用平台 S2 key；E3 只取了每个 set 的首页（cs/math/physics 各 1,300 条，非全日量），E4 为"recent"列表快照，二者都是**时点抽样**而非全量统计。

---

## 2. 主体内容

### 2.1 TL;DR / 一句话摘要

#### 2.1.1 现成来源一：Semantic Scholar TLDR

| 维度 | 事实 | 证据 |
|---|---|---|
| 任务起源 | SciTLDR（Cachola、Lo、Cohan、Weld，Findings of EMNLP 2020）：5.4K 条 TLDR 覆盖 3.2K 篇论文，含作者写与专家（评审意见改写）两类；方法 CATTS 以标题生成为辅助训练信号 | [R01] A |
| 数据/代码 | `allenai/scitldr`：761★，Apache-2.0（仓库），最近推送 2023-05-22；60/20/20 划分；8 个 BART/CATTS 权重（⚠ 数据集本身未单列许可） | [R02] A |
| 上线 | 2020-11-16 上线 S2 搜索结果页，首批约 1,000 万篇 CS 论文（Beta） | [R04] C |
| 当前覆盖（官方口径） | 产品页：约 6,000 万篇"计算机、生物、医学"论文；"约 20 词" | [R03] A |
| 当前规模（数据集） | Datasets 最新 release **2026-09-22**：`tldrs` 5,800 万条（30 个 200 MB 文件） | [R06] B |
| 模型 | BART + CATTS，训练集为 SciTLDR + 另收集的生医论文摘要；API 返回 `tldr: {model: "tldr@v2.0.0", text}` | [R05][R07] A；[E1] B |
| 许可 | `tldrs` 数据集 README：**ODC-BY**，产品/服务中使用须引用 Cachola et al. 2020；API 协议（2023-05-17）要求在网站或出版物中署名"Semantic Scholar"，不得转售/再许可/再分发 API 本身 | [R06][R08] A |
| 获取 | Graph API `fields=tldr`（批查 ≤500 id/请求，有 key 入门 1 RPS，见 [aggregators §2.2.3](../sources/aggregators-repositories.md)）；全量用 Datasets + 周增量 diff（需 key） | [R07] A |

**E1 实测覆盖（arXiv，n=744；百分比以抽样数为分母）**：

| 类目 | 2026-03 窗（成熟） | 2026-09-14..24 窗（新） |
|---|---|---|
| cs.CV | 39/40（97.5%） | 39/40（97.5%） |
| cs.CL | 37/40（92.5%） | 37/40（92.5%） |
| q-bio.NC | 29/40（72.5%） | 21/24（87.5%） |
| stat.ME | 22/40（55.0%） | 24/40（60.0%） |
| q-fin.ST | 18/32（56.3%） | 4/8（50.0%） |
| econ.GN | 13/40（32.5%） | 21/40（52.5%） |
| physics.chem-ph | 10/40（25.0%） | 11/40（27.5%） |
| math.PR | 6/40（15.0%） | 5/40（12.5%） |
| cond-mat.mtrl-sci | 4/40（10.0%） | 3/40（7.5%） |
| hep-th | 0/40（0%） | 0/40（0%） |
| **合计** | — | **343/744（46.1%）**；743/744 已被 S2 收录 |

**E1 关键观察**：

- **按领域门控**：`s2FieldsOfStudy` 含 Computer Science/Medicine/Biology 的论文 335/395（84.8%）有 TLDR；三者都不含的 **1/334（0.3%）**。这与"CS、生物、医学"的官方口径一致，即 S2 **不为数学、物理、化学、经济主体论文生成 TLDR**（经济类的 TLDR 几乎都落在被同时标为 CS 的论文上，⚠ 推断）。
- **时效**：2026-09-24 提交（约 2026-09-25/26 公告）的 cs.CL/cs.CV/q-bio.NC/stat.ME 论文，在 2026-09-26 19:30 UTC 已有 85/98 带 TLDR——**公告后 1–2 天内可得**（核验注：85/98 的逐篇明细未存入子目录，⚠ 未能复核；抽查 2609.30226〔2026-09-24 17:50 UTC 提交〕已有 TLDR，与结论相符）。
- **长度**：均值 36.6 词（中位 36，17–61），明显长于产品页的"约 20 词"。
- **抽取性**：TLDR 的 4-gram 平均 81%（中位 82%）直接出现在摘要中；336 篇里 199 篇 ≥80%，只有 5 篇 <30%。
- **退化**：8/336（2.4%）出现 6-gram 复读，例如 2609.30226 的 TLDR 为"PoEM, a framework to predict … is introduced by introducing PoEM, a framework to predict …"（原句重复两遍）。

**E2 期刊覆盖（2026-01..06 出版，每刊 20 篇）**：

| 期刊（学科） | S2 收录 | 有 TLDR | Crossref 有摘要 | S2 有摘要 |
|---|---|---|---|---|
| Cell（生物） | 19/20 | **18** | 0 | 18 |
| IEEE TPAMI（CS） | 19/20 | **14** | 0 | 19 |
| Management Science（管理） | 14/20 | 5 | 18 | 12 |
| Psychological Science（心理） | 20/20 | 2 | 20 | 20 |
| JACS（化学） | 19/20 | 2 | 1 | 17 |
| Phys Rev Lett（物理） | 20/20 | 1 | 4 | 19 |
| AER（经济） | 10/20 | 1 | 19 | 10 |
| J Finance（金融） | 11/20 | 0 | 19 | 11 |
| Annals of Math（数学） | 10/16 | 0 | 0 | 5 |
| **合计** | 142/176（81%） | **43/176（24%）** | 81 | 131 |

结论：对 v2 的社科（经济/金融/管理）与理科（数/理/化/心理）主干，S2 TLDR 基本不可用；S2 返回的摘要覆盖面比 Crossref 广（JACS/Cell/TPAMI），但这些摘要文本的版权属性见 §4 Q4。

#### 2.1.2 现成来源二：Hugging Face Papers 的 AI 摘要

- `GET https://huggingface.co/api/papers/{arxiv_id}` 对已收录论文返回 `ai_summary`、`ai_keywords`、`ai_summary_model`、`githubRepo`、`githubRepoAddedBy`（如 `auto`）、`githubStars`、`linkedModels/Datasets/Spaces`；例如 2004.15011 的 `ai_summary_model` 为 `Qwen/Qwen2.5-Coder-32B-Instruct`，`githubRepo` 为 `allenai/scitldr` [R09] B。
- **E5 覆盖**：2026-03 窗样本中 cs.CL 6/38（16%）、cs.CV 9/40（23%）被收录，stat.ME 1/40，cond-mat.mtrl-sci 0/40；被收录的 cs 论文 15/15 有 `ai_summary` 与 `ai_keywords`，4 篇有 `githubRepo`；摘要模型为 Qwen2.5-Coder-32B-Instruct（13）与 thinkingmachines/Inkling-Small（2）。
- **定位**：只覆盖已建 paper page 的论文——Hub 仓库卡片引用 arXiv 时自动关联、提交到 Daily Papers，或任何用户在 `hf.co/papers/{arxiv_id}` 手动索引 [R82]（核验修正：并非仅 Daily Papers）；实测以 AI 论文为主；再使用许可未声明（⚠ 未核验）→ **仅作对照与代码链接线索，不入共享卡片正文**。

#### 2.1.3 LLM 生成：先例与提示设计

| 先例 | 输入 | 输出形态 | 触发方式 | 证据 |
|---|---|---|---|---|
| zotero-arxiv-daily（5,992★，AGPL-3.0） | 标题 + 摘要 + 正文预览，**截断到 4,000 tokens**（gpt-4o 分词器估算） | "one-sentence TLDR in {lang}"；失败回退为原摘要 | 每日批量（GitHub Actions） | [R10] A |
| HF Papers | 未公开（⚠） | `ai_summary`（一句）+ `ai_keywords` | 收录时生成 | [R09] B |
| Cool Papers（809★，无许可声明） | PDF 全文交给 Kimi | 中文/英文可选的 FAQ 式解读 | **用户点击 [Kimi] 才触发**，新论文需排队；2025-06-04 因 bioRxiv 启用 Cloudflare 反爬而下线该源（"选择下线而不是对抗"） | [R11] A |
| Google Scholar Quick Read（2026-08-25） | 用户查询 + Scholar Labs / Scholar 搜索结果中"深入讨论该问题"的论文（官方未说明是否读全文，⚠ 推断为全文） | 概述 + **Answers / Approach / Considerations** 三段，可展开细节 | 用户点击；**只对用户有访问权的论文出现**，与出版商合作开放订阅文章；仅英文、需登录 | [R12] A |
| Scholar Inbox | — | 论文未描述 AI 摘要功能（⚠ 未核验线上是否已有）；卡片展示标题/摘要/作者 + 前五张图表 | — | [R37] A |

**提示设计要点**（综合上述先例与 §2.1.4 的风险证据；以下为设计伪代码）：

```text
# 设计伪代码：卡片基础包（A 包）——一次调用产出多个字段，结构化输出
system: 你是科学论文编辑。只能使用 <source> 中的信息；不得引入 source 未出现的数字、数据集、
        机构、结论或因果关系；保留原文的限定语（may/suggest/preliminary/in mice 等）；
        数学公式与 LaTeX 片段原样保留；信息不足时对应字段返回 null。
user:   <source license="CC0|CC-BY|…" lang="en">TITLE + ABSTRACT</source>
output_schema (strict JSON):
  tldr_en:  string ≤ 30 words, 必须以 "研究对象/方法 + 主要发现" 结构，禁止评价性形容词
  tldr_zh:  string ≤ 60 汉字，与 tldr_en 语义一致
  title_zh: string，术语保留英文缩写（如 "RAG"），专有名词不音译
  keywords: [≤5 个短语，必须是 source 中出现的片段（便于校验）]
  claim_type: enum{method, empirical, theoretical, survey, dataset, position}
  hedged: bool   # source 是否含限定语；为真时 tldr 必须保留限定
  numbers_used: [tldr 中出现的全部数字]  # 供规则闸核对
params: temperature=0；非推理模型或最低推理档（GPT-5.4 系 reasoning.effort=none〔默认〕，GPT-5 系为 minimal）；max_output≈300 tokens
```

设计理由：①一次调用摊薄固定提示成本（§2.6 表 2.6-B）；②`keywords`/`numbers_used` 让规则闸能做字符串级核对；③`claim_type` 与 `hedged` 服务于"过度概括"防护；④语言双输出便于一致性校验（中英互译回检，⚠ 推断）。

#### 2.1.4 幻觉与过度概括：证据与控制

| 证据 | 要点 | 对设计的含义 | 来源 |
|---|---|---|---|
| Peters & Chin-Yee 2025（R. Soc. Open Sci. 12(4):241776） | 10 个主流 LLM、4,900 份摘要：即使明确要求准确，多数模型仍把结论**泛化**得比原文更宽；DeepSeek、ChatGPT-4o、LLaMA 3.3 70B 过度概括率 26–73%；与人写科普摘要相比 OR=4.85（95% CI 3.06–7.70）；**新模型往往更差**；建议降低温度、对"概括准确性"做基准 | TL;DR 需专门检查限定语与适用范围（人群、物种、条件），不能只查"事实是否存在" | [R13] A |
| Vectara HHEM 榜（2026-09-22 更新，7,700+ 篇文档，温度 0） | 幻觉率：gpt-5.4-nano **3.1%**、gemini-2.5-flash-lite **3.3%**、Phi-4 3.7%（应答率仅 80.7%）、Llama-3.3-70B 4.1%、gemma-3-12b 4.4%、qwen3-8b 4.8%、gpt-5.4-mini 5.5%（核验补充）、qwen3-4b 5.7%、DeepSeek-V3.2 6.3%、gemini-3.1-flash-lite-preview 8.2%、Claude Haiku 4.5 9.8%、gpt-5-nano 10.5%、Claude Sonnet 4.6 10.6%、gpt-5-mini 12.9%、o4-mini 18.6%、o3-pro 23.3% | 摘要任务优先选**低幻觉的非推理小模型**；"更大/更新/推理"不等于更忠实；该榜为混合领域（新闻、科技、科学、医学、法律、体育、商业、教育），非专门的科学论文摘要，需自测 | [R14] A（榜单本身）；方法依赖 Vectara 自家 HHEM-2.3 |
| S2 TLDR 实测 | 抽取性强（81% 4-gram 来自摘要）→ 编造少，但会出现复读退化（2.4%）与"只摘方法、漏掉结论"（例：Scholar Inbox 的 TLDR 只写了科学地图与主动学习，没提"个性化推荐"本身） | 抽取式模型的风险在**信息选择**而非编造；生成式 LLM 的风险在**编造与泛化** | [E1] B |

**控制手段（按成本从低到高，均为设计建议）**：

1. **来源约束**：只喂标题+摘要（或许可允许的全文片段），禁止模型"联网补充"；温度 0（与 [R13] 建议一致）。
2. **规则闸（零成本，必做）**：`numbers_used` ⊆ source 中的数字；大写缩写/方法名/数据集名 ⊆ source；source 含限定语时 TL;DR 必须含对应限定；长度与语言检查；LaTeX 片段一致。不过闸 → 丢弃并回退到"摘要首句"。
3. **NLI/事实一致性小模型（低成本，必做）**：MiniCheck-FT5（770M，EMNLP 2024，自报达到 GPT-4 精度、成本低 400 倍；`lytang/MiniCheck-Flan-T5-Large` 为 MIT）[R16]，或 HHEM-2.1-Open（Apache-2.0）[R15]；对 TL;DR 每个分句与摘要做蕴含判定，低于阈值即降级。
4. **抽样 LLM 裁判 + 人工审计（中成本，持续做）**：FineSurE（ACL 2024）按句给出忠实度，并补"完整性/简洁性"两维 [R17]；G-Eval（MIT 代码）作通用评分框架 [R18]；每日抽样 1–5% 做人工复核（§2.7）。
5. **展示侧兜底**：卡片 TL;DR 带"AI"角标，一键展开原摘要；用户"内容不准确"反馈直接进入审计队列（与 UX 文档 §2.6.2 一致）。

### 2.2 关键图提取

#### 2.2.1 取图通道对比

| 通道 | 能拿到什么 | 许可信息 | 成本/限速 | 维护与许可（代码/权重） | 适用 | 证据 |
|---|---|---|---|---|---|---|
| **arXiv HTML（LaTeXML）** | 每图一个 `<figure class="ltx_figure">`：栅格图 `<img src="{id}v{n}/xxx.png">`，矢量图常为 `<object type="image/svg+xml" data="{id}v{n}/Figure1.svg">`；图注 `<figcaption>`（含 MathML） | 页面带"License: CC BY 4.0"之类的许可行（本轮 1 篇实例核验） | arxiv.org `Crawl-delay: 15`（≈5,760 请求/日上限）；免解析 | 2023-12-18 起为 2023-12-01 后提交的 TeX 论文生成 HTML，标为实验性；旧论文见 ar5iv（`dginev/ar5iv` 874★ MIT） | arXiv 首选 | [R28][R29] A；[E4] B |
| **PMC / Europe PMC JATS** | `<fig>` + `<graphic xlink:href>` + `<caption>`，图文件在 OA 包/`fullTextXML` | 逐篇 `license_code` / `LICENSE` 字段 | 见生命科学文档（PMC OAI 3 rps、禁并发等） | 官方服务 | 生医/心理 OA 首选 | [life-sciences §2](../sources/life-sciences-psychology.md) |
| **GROBID 0.9.1** | `teiCoordinates=figure` 给出图/表的页码与坐标（`figure` 同时覆盖 figure 与 table）+ `<figDesc>` 图注；内嵌位图可经批处理导出为 PNG，`processFulltextAssetDocument`（返回 zip）**仍可用但已弃用**；矢量图需按坐标自行渲染裁剪 | 能识别版权方与 CC 许可声明（OSS 文档） | README：16 线程/32 GB 单机、node.js 客户端连续一周约 **10.6 PDF/s**（≈91.5 万 PDF/日；引 2019 年 issue #443 实测，未注明模型配置——核验修正） | 5,143★ Apache-2.0；v1 已集成（D-033） | PDF 兜底首选（CPU、零外网） | [R23] A |
| **PDFFigures 2.0** | 每图：页码、72 DPI 坐标框、图内文字、图注及其坐标、编号、图/表类别；只抽"有图注"的图；可存栅格图 | — | Scala/JVM | 759★ Apache-2.0，最近推送 2024-03 | 可作对照；停更 | [R21] A |
| **DeepFigures** | 神经网络图检测；用 arXiv/PubMed 的 LaTeX/XML 远程监督诱导 550 万标注（标注平均精度 96.8%）；曾在 S2 上为 1,300 万篇文档抽图 | — | 需 GPU | 149★ Apache-2.0，最近推送 2022-06 | 历史参考 | [R22] A |
| **Docling v2.130**（v2.130.0，2026-09-22 发布，核验确认） | `PdfPipelineOptions.generate_picture_images=True` + `images_scale` 导出 `PictureItem`/`TableItem` 图片；`do_picture_classification`（`DocumentFigureClassifier-v2.5`：EfficientNet-B0、26 类如 logo/line_chart/bar_chart/flow_chart/pie_chart/bar_code，MIT）；`do_picture_description` 可接 SmolVLM-256M（Apache-2.0）或 Granite Vision | — | GPU 可选；olmOCR-bench 上 2.1 页/s（Marker README 自报口径） | 67,991★ **MIT** | 许可最干净的通用兜底 | [R24] A；[R26] A；技术报告见 [R80] |
| **MinerU 4.x** | `images/page_{page_idx}_{parent_type}_{parent_index}.{ext}` 形式的图片文件 + 结构化 content list（含图注；是否为区域裁剪与字段名 ⚠ 未逐一核验） | — | pipeline 0.54 页/s（同上口径） | 80,679★；Apache-2.0 **+ 附加条款：MAU>1 亿或月收入>2,000 万美元需商业许可，且须在产品界面或公开文档致谢**；两项任一未履行则许可自动终止（核验补充） | 中文文档强；需接受致谢条款 | [R25] A |
| **Marker v2** | 默认抽取并保存图片（`--disable_image_extraction` 可关）；JSON 块树含图片块 | — | 单 B200：fast 无 OCR 23.7 页/s（纯 CPU）、fast 7.4、balanced 2.9 页/s | 39,987★；代码 Apache-2.0，**权重为修改版 OpenRAIL-M（研究/个人/融资或营收 <500 万美元免费）** | 有条件可选 | [R26] A |
| **Nougat** | 输出 `.mmd`（文本/公式），**不导出图片** | — | GPU | 10,079★；代码 MIT，**权重 CC-BY-NC**，最近推送 2025-02 | 不适用 | [R27] A |
| **papermage** | Scholar Inbox 用它抽"前五张图表" | — | GPU 加速 | 803★ Apache-2.0，最近推送 2024-11（停更） | 先例 | [R37] A |

**E4 arXiv HTML 可得率（2026-09-26 recent 列表）**：cs.CL 232/250（92.8%）、math.PR 235/247（95.1%）、hep-th 222/227（97.8%）、q-bio.NC 16/19（84.2%）、econ.GN 17/25（68.0%）、cond-mat.mtrl-sci 145/212（68.4%）、q-fin.ST 9/9；**合计 876/989（88.6%）**。缺失的多为非 TeX 投稿或转换失败（⚠ 推断）；arXiv 官方未公布当前成功率（本轮只找到二手口径"约 75% 完全成功、97% 部分成功"，C 级，未采信）。

**栅格化裁剪**：GROBID 只给坐标时，用 `pypdfium2` 按坐标渲染裁剪（Apache-2.0 / BSD-3-Clause，PDFium 为 BSD）[R73]——延续 v1 "PyMuPDF 因 AGPL 出局"的取舍（design/12 §3）。

#### 2.2.2 "关键图"如何选

- **研究证据**：Yang 等（ICDAR 2019）对 6,263 位作者、8,353 篇论文的调查显示 **87% 以上的论文被作者认为存在"中心图"**，起图形摘要作用，多用于概括重要结果（核验补充：受访者为 PubMed 收录论文的作者，外推到 CS/数理需谨慎；C 级：数字来自检索摘要；数据集 7,295 篇、5,841/721/733 划分为 A 级 GitHub README）[R36]。
- **先例**：Scholar Inbox 直接展示"前五张图表"，并指出抽取 teaser 图计算量大、需 GPU [R37]。
- **建议的选图规则（设计伪代码）**：

```text
# 设计伪代码：key_figure 选择（只在"许可闸通过"的论文上运行）
candidates = figures(source=arxiv_html | jats | pdf_parser)
drop c if classifier(c) in {logo, icon, bar_code, qr_code, signature, stamp, page_thumbnail}
     # DocumentFigureClassifier-v2.5 的真实类名（核验修正）；无"作者照片"类，最接近 photograph，需结合版面位置规则
drop c if c.caption matches /(reprinted|adapted|reproduced) (with|by) permission|©|courtesy of/i  # 第三方素材
score(c) = 3·[c.label == "Figure 1"] + 2·[caption ~ /overview|framework|pipeline|architecture|illustration|teaser/]
         + 1·[type in {flow_chart, engineering_drawing}] + 1·[c.is_first_in_intro_or_method]   # v2.5 无 diagram 类
         − 2·[type == table] − 1·[aspect_ratio > 4 or area < θ]
key_figure = argmax(score) if max(score) ≥ τ else None                       # None ⇒ 排版封面
optional: VLM rerank Top-3（仅详情页、仅可共享论文）
```

- **按需**：选图依赖取图，取图受 arXiv 15 s crawl-delay 或 PDF 解析算力约束 → 只对"进入候选集且排名靠前"或"详情被打开"的论文执行（§2.6.7）。
- **图注改写/生成**：若要为图注过长或缺失的图生成卡片短说明，可参考 SciCap（EMNLP 2021 Findings：29 万余篇 CS arXiv 论文、200 万余张图；基线只针对占比最高的 graph plot 类，占 19.2%，并指出任务挑战很大）[R75]；AI 改写图注属于演绎，同样受 §2.2.3 许可闸约束，且须标"AI 生成"。

#### 2.2.3 许可闸：各源许可字段与实测分布

| 源 | 许可字段 | 实测/事实 | 证据 |
|---|---|---|---|
| arXiv | OAI-PMH `metadataPrefix=arXiv` 的 `<license>`（URL）；HTML 页许可行 | 作者可选 CC BY 4.0、CC BY-SA 4.0、CC BY-NC-SA 4.0、CC BY-NC-ND 4.0、arXiv 永久非独占许可 1.0、CC0；**许可不可撤销**；非独占许可"限制其他实体或个人任何类型的再利用"；**全部元数据适用 CC0** | [R30] A |
| arXiv（E3 实测，datestamp 2026-09-22） | 同上 | （核验注：OAI datestamp 记录含旧论文新版本与元数据变更，并非严格的"当日新投稿"）4,568 条：arXiv 非独占 **51.6%**、CC BY 36.8%、BY-NC-ND 6.0%、BY-NC-SA 3.0%、BY-SA 1.4%、CC0 1.3%；按 set：cs CC BY 39%、math 30%、physics 44%、stat 34%、eess 28%、q-bio 40%、q-fin 46%、econ 38% | [E3] B |
| arXiv ToU | — | 描述性元数据（**含标题、摘要**、作者、标识、分类）CC0；**不得从自有服务器存储并提供 e-print（PDF、源文件或其他内容）**，除非获版权人许可或许可证允许；遗留 API 每 3 秒 ≤1 次、单连接 | [R31] A |
| OpenAlex | `best_oa_location.license`、`primary_location.license`、`locations[].license` | **E6**：arXiv 2026-03 的 34,212 篇中许可已知 53.8%（CC BY 42.6%、BY-NC-ND 4.8%、BY-NC-SA 3.2%、BY-SA 1.6%、CC0 1.2%），**null 46.2%**（与 arXiv 非独占占比同量级，⚠ 推断 null≈非 CC）；全部文章 2026-03 的 778,166 篇：CC BY 38.1%、BY-NC-ND 9.1%、CC0 5.0%、BY-NC 4.3%、BY-SA 3.0%、BY-NC-SA 1.5%、BY-ND 0.2%、other-oa 0.5%，**null 38.4%**；OA 状态 green 34.3%、closed 22.7%、diamond 14.8%、gold 13.5%、hybrid 12.2%、bronze 2.6% | [E6] B |
| Crossref | `license[]`（URL + `content-version` + `delay-in-days` + `start`） | 大量出版商给 TDM 许可而非 CC（生命科学文档实测：Elsevier TDM、SAGE TDM、T&F TDM 等） | [life-sciences §2](../sources/life-sciences-psychology.md) A/B |
| PMC / Europe PMC | `license_code`（CC 代码或 `TDM`）/ `LICENSE` | PMC README：只再分发许可允许的数据 | 同上 |
| bioRxiv/medRxiv | Crossref license URL；含 no-reuse | 生命科学文档样本中 no-reuse 14.7% | 同上 |

**CC 规则要点（A 级）**：CC 4.0 允许"在任何媒介和格式中行使权利并作必要的技术修改"，单纯格式修改"从不"产生演绎作品 [R39]；ND 许可禁止分享演绎作品，但 CC FAQ 认为**把未修改的摘录用于说明观点或举例**时一般不构成演绎、只行使复制权 [R38]；NC 许可禁止商业目的；署名需给出作者、来源、许可链接并**注明是否修改** [R39]；TDM 结果若构成演绎则不应挖掘 ND 材料，商业 TDM 不应挖掘 NC 材料 [R38]。

**由此得出的展示闸（设计建议）**：

| 许可 | 共享卡片展示原图 | 裁剪（从整页/整图中取子图） | 缩放/格式转换 | 备注 |
|---|---|---|---|---|
| CC0 / CC BY / CC BY-SA | ✅ | ✅（标注"已裁剪"） | ✅ | 附作者、来源、许可链接；BY-SA 的修改版须同许可 |
| CC BY-NC / BY-NC-SA | 仅**非商业部署** ✅ | 同左 | 同左 | 平台一旦商业化即关闭 |
| CC BY-ND / BY-NC-ND | ⚠ 原样整图可能可行（摘录说），**裁剪/加水印/配 AI 解说 ⚠ 需法务** | ❌（默认） | ✅（技术修改） | 默认不上卡片，只在详情页外链 |
| arXiv 非独占 / 出版商版权 / TDM 许可 / 未知 | ❌ | ❌ | ❌ | 排版封面；详情页链接到原文 |
| 图注含"with permission/©"等第三方声明 | ❌（无论论文许可） | ❌ | ❌ | CC 许可不覆盖第三方素材 ⚠ 推断 |

### 2.3 多语种：中文标题/摘要翻译

#### 2.3.1 需求特征（实测）

- 长度：标题均值 15.8 tokens、摘要均值 241.4 tokens（中位 243，P90 333；o200k 分词）；摘要均值 176.8 词、1,298 字符 [E7]。
- **LaTeX**：29% 的标题/摘要含 `$…$` 或 `\命令`，math.PR 67%、hep-th 58%、cond-mat 39%、chem-ph 28%、stat.ME 24%、cs.CL 14%、econ.GN 6% [E8]——翻译必须原样保留公式，前端需 KaTeX 渲染。
- 中文输出 token：o200k 对中文约 0.675 token/字 [E7]（核验复算：办法第一至十四条正文 2,101 字符 → 1,447 tokens，即 0.689 token/字符、按汉字计 0.765 token/字，量级一致）；一篇摘要的中文译文按 300–450 字估算约 200–300 tokens（⚠ 推断，未实测真实译文）。

#### 2.3.2 方案对比（价格为 2026-09-26 官方价）

| 方案 | 代表 | 价格 | 许可/条款要点 | 适配度 | 证据 |
|---|---|---|---|---|---|
| **通用小 LLM，与 TL;DR 同一次调用** | gpt-5-nano / gemini-2.5-flash-lite / qwen3.8-flash / deepseek-flash | 见 §2.6（中文标题+TL;DR 已含在 A 包内，边际成本≈0；全文摘要翻译 B 任务 $0.07–0.51/千篇） | 商用 API 条款；Gemini 免费层数据会用于改进产品，须用付费层 | ★★★ 首选 | [R54][R55][R56][R57] A |
| **专用翻译 LLM（API）** | Qwen-MT：plus/flash/turbo 支持 92 种语言，lite 31 种；均支持**术语干预、翻译记忆**，plus/flash/turbo 另支持领域提示；turbo 不再更新，官方推荐 flash | qwen-mt-flash 北京 $0.101/$0.280（国际 $0.16/$0.49）；qwen-mt-plus 北京 $0.259/$0.775 | 同上 | ★★★ 需要术语表时首选 | [R57] A |
| **开源 MT 专用模型（本地）** | Hunyuan-MT-7B / Chimera-7B（2025-09-01 开源，33 种语言，WMT25 通用赛道 31 个语向中 30 个第一） | GPU 自托管 | **腾讯混元社区许可：不适用于欧盟、英国、韩国地区（"Territory"排除三地，且禁止在该地域使用模型输出）；MAU>1 亿需另行授权** | ★★ 面向欧盟/英国/韩国用户的部署不可用（核验修正：许可并非"仅限中国境内"） | [R63] A |
| 同上（核验补充） | HY-MT1.5-1.8B / HY-MT1.5-7B（2025-12-30 开源，33 种语言 + 5 种民族语/方言；新增术语干预、上下文翻译、格式化翻译；1.8B 量化后可端侧部署） | GPU/端侧自托管 | 腾讯 HY 社区许可，同样排除欧盟、英国、韩国 | ★★ 同上 | [R63] A |
| 同上 | Seed-X-7B（字节，28 种语言，自报可比 Gemini-2.5 与 GPT-4o） | GPU 自托管 | OpenMDW 许可（HF 卡片） | ★★ | [R64] A |
| 同上 | NLLB-200 | GPU 自托管 | **CC-BY-NC-4.0**（非商用） | ✗（商用） | [R65] A |
| 通用开源 LLM（本地） | Qwen3-4B/8B/14B（Apache-2.0）、Phi-4（MIT）、granite-4.0-h-small（Apache-2.0）；Gemma（Gemma 条款，gated）、Llama 3.1（llama3.1 许可，gated） | GPU 自托管 | 以 Apache/MIT 为先 | ★★ 私有层首选 | [R76] A |
| **NMT API** | DeepL API Growth：€29.75/月 + **€22/百万字符**（Developer 免费 100 万字符/月，DE 站点价） | 标题+摘要 ≈1,380 字符 → **≈€30/千篇** | 企业数据安全仅 Growth 起 | ✗ 贵约 100×；LaTeX 保真 ⚠ | [R59] A |
| 同上 | Google Cloud Translation NMT：超 50 万字符/月后 **$20/百万字符**；Translation LLM $10/百万输入字符 + $10/百万输出字符；Adaptive $25/$25 | ≈$27.6/千篇（NMT）、≈$17.3/千篇（LLM） | — | ✗ 同上 | [R60] A |
| **全文 PDF 保版式翻译**（核验补充） | PDFMathTranslate（37,202★，AGPL-3.0，EMNLP 2025 System Demonstrations；保留公式/图表/目录）/ BabelDOC（9,611★，AGPL-3.0） | 自托管 + 任一翻译后端（Google/DeepL/OpenAI/Ollama 等） | AGPL（以网络服务提供需公开修改后源码）；全文译文属演绎，只可用于可共享许可全文或用户私有层 | ★ 仅作私有层"为我翻译全文"候选 | [R83] A；另见 [OSS 文档](../oss/paper-acquisition-and-search-oss.md) |

#### 2.3.3 许可：什么能翻、什么不能共享

- **翻译属于演绎**：CC 4.0 的 Adapted Material 定义明列"translated"；CC FAQ 以"小说翻译"为典型演绎 [R38][R39]。
- **arXiv 摘要可以翻**：标题、摘要属 CC0 描述性元数据 [R30][R31]，与论文正文许可无关——这是 v2 中文化的最大"安全区"（arXiv 是 CS、数理与量化金融预印本的主渠道，⚠ 推断，覆盖比例见各 sources 文档）。
- **CC BY/BY-SA/CC0 论文摘要可以翻**（附署名与"机器翻译"标记）；**BY-ND/BY-NC-ND 不得做共享的翻译/改写**；NC 类仅限非商业部署。
- **Crossref 中的出版商摘要**："可能受出版商或作者版权保护"，Crossref 声明第三方只有在获得版权人明确许可时才能转载（I4OA 页面转述 Crossref 立场）[R40]；OpenAlex 出于法律原因只给倒排索引（见聚合源文档 [S23]）。→ 共享层**不存储**这类摘要的译文/TL;DR；用户可在详情页"即时翻译给自己看"（不落共享缓存），其合法性 ⚠ 需法务（§4 Q1）。

#### 2.3.4 翻译质量评估

| 工具 | 用途 | 许可 | 结论 | 证据 |
|---|---|---|---|---|
| MetricX-24（hybrid，含无参考 QE 模式） | 自动评分/回归测试 | 模型 Apache-2.0 | 商用可用，首选 | [R67] A |
| COMET（wmt22-comet-da，需参考译文） | 有参考评分 | Apache-2.0 | 可用于黄金集 | [R66] A |
| CometKiwi / XCOMET | 无参考 QE / 错误片段定位 | **CC BY-NC-SA 4.0**（gated） | 仅内部研究，不进生产 | [R66] A |
| 术语一致性 | 领域术语表（每学科 200–500 条）命中率 | 自建 | 与 Qwen-MT 术语干预配合 | 设计建议 |
| 人工 MQM 抽检 | 严重/主要/次要错误计数 | — | 黄金集与季度抽检 | 设计建议 |

### 2.4 自动标签与主题分类

#### 2.4.1 现成分类体系（优先"取源"）

| 体系 | 规模/结构 | 如何得到 | 许可 | 精度/局限 | 证据 |
|---|---|---|---|---|---|
| **arXiv 类目** | 155 个类目（cs 40、math 32、physics 22、q-bio 10、cond-mat 9、q-fin 9、astro-ph 6、stat 6、nlin 5、eess 4、econ 3 等） | 作者选主类目 + 交叉列表，元数据自带 | CC0 | 作者自选，粒度粗；无跨学科层级 | [R34] B；[R30] A |
| **OpenAlex Topics** | 4 domains → 26 fields → 252 subfields → **4,516 topics**；每篇 ≤3 个 topic（带 score），最高分为 `primary_topic` | 记录自带（免费）；**`/text` 端点**对任意标题/摘要打 topics + keywords：20–2,000 字符、**1 请求/秒、$0.01/请求**；⚠ 核验补充：OpenAlex 定价页（Example costs）已把 "Text / Aboutness" 标为 **deprecated**（$10/千次），而端点文档（2026-09-22 更新）仍可用——有下线风险 | 数据 CC0 | 与 CWTS 合作，topic 由引文聚类 + LLM 命名；分类器输入为标题、摘要、引文、期刊名；**约 12% 的作品无 topic（2026 年中 3,960 万/3.22 亿）** | [R41][R42] A |
| OpenAlex 分类器（开源） | 代码 `ourresearch/openalex-topic-classification`（59★，MIT）；标题+摘要版 mBERT 权重（Apache-2.0，2024-05） | 自托管 | Apache-2.0 | 模型卡：**不是**线上完整模型（线上还用期刊与引文特征）；4,516 类**训练集准确率 0.4846**（模型卡 "Train Accuracy" 第 7 轮；验证集只报 loss 3.07，未报准确率——核验确认）——细粒度 topic 不宜直接当卡片标签 | [R43] A |
| S2 fieldsOfStudy | 粗粒度大类：本轮 730 篇样本共观察到 23 个取值；`s2FieldsOfStudy` 每项带 `source`（`external` 964 项 / `s2-fos-model` 1,180 项） | Graph API 自带 | S2 API 协议 | 粗粒度；S2FOS 模型 `allenai/s2_fos`（34★ Apache-2.0，2024-01 后未更新）；它同时是 S2 TLDR 的领域门控依据（§2.1.1） | [R05][R49] A；[E1] B |
| 学科专用体系 | PhySH（CC0，APS Harvest 直接返回）；MSC2020（**CC BY-NC-SA 4.0**）；JEL（RePEc/AEA/NBER 元数据）；MeSH（PubMed/EPMC） | 各源元数据 | 各异 | 精度最高但只覆盖本学科 | 见 [natural-sciences](../sources/natural-sciences.md)（PhySH/MSC 许可条目）、[social-sciences](../sources/social-sciences-econ-fin-mgmt.md)（JEL 来源）、[life-sciences](../sources/life-sciences-psychology.md)（MeSH） |
| 跨体系对齐 | Science Data Lake（arXiv 2603.03126）用句向量把 4,516 个 OpenAlex topic 映射到 13 个科学本体 | — | — | 可作为多体系标签归一的参考 | 见 [retrieval-routing-indexing](retrieval-routing-indexing.md) |

#### 2.4.2 关键词抽取

| 方法 | 原理 | 许可 | 证据与评价 |
|---|---|---|---|
| **KeyBERT**（4,221★，最近推送 2026-08-25） | 文档嵌入与 n-gram 候选嵌入的余弦相似度；Max Sum Distance / MMR 做多样化；可换任意嵌入模型 | **MIT** | 轻量、可复用 v2 已有的论文向量 [R45] A |
| YAKE（1,883★） | 无监督、无需语料的统计特征 | **AGPL-3.0**（另可购商业许可） | 网络服务形态有 AGPL 义务，默认不选 [R46] A |
| LLM 零样本关键词 | 直接提示 | 取决于 API | Song 等（arXiv 2312.15156）：ChatGPT 零样本关键短语抽取**仍明显落后**于 SOTA 无监督/有监督模型 [R47] A |
| PromptRank（ACL 2023） | 用 PLM 生成概率给候选短语打分 | 研究代码 | 无监督 SOTA 路线之一 [R48] A |
| OpenAlex keywords | 作品级关键词（新 tagger 正在重打全库；`/text/keywords` 的部分 id 为临时 id） | CC0 | 免费取源 [R42] A |
| HF `ai_keywords` | Qwen2.5-Coder-32B 等生成 | 未声明 | 仅对照 [E5] B |

#### 2.4.3 LLM 零样本打标签（受控标签集）

- **做法（设计建议）**：先用嵌入检索从受控词表召回 Top-20 候选标签（OpenAlex subfield/topic、arXiv 类目、PhySH/JEL/MeSH 子树），再让 LLM 在候选内单选/多选并给出依据片段；这样把"开放生成"变成"有限集合分类"，可用规则校验（标签必须 ∈ 候选集）。
- **何时需要**：①源无分类（如部分会议论文、SSRN）；②用户订阅 DSL 的主题需要映射到统一标签空间；③双语标签（中文展示名由词表维护，不由 LLM 临场翻译）。
- **成本**：可并入 A 包（输出 +30 tokens），几乎零边际成本。

#### 2.4.4 卡片上的标签策略

- 卡片 ≤3 个标签、单行（UX 文档 §2.6.2）；**展示用受控词表的中英名**（OpenAlex subfield/field 级或学科体系），不展示 4,516 级 topic 的长名。
- 自由关键词（KeyBERT/LLM）不做过滤维度，只用于检索扩展、why-this 文案与相似论文召回。

### 2.5 结构化要点与代码/数据链接

#### 2.5.1 结构化要点（贡献/方法/数据集/结论/局限）

| 资源/先例 | 事实 | 可借鉴 | 证据 |
|---|---|---|---|
| Google Scholar Quick Read | 概述 + Answers / Approach / **Considerations**（局限与注意事项），每点可展开支持细节；只对有访问权的论文出现 | 结构化 + "局限"栏 + 证据展开；访问权门控 | [R12] A |
| SciRIFF（EMNLP 2025） | 137K 条专家写的指令样本、54 个任务，覆盖信息抽取、摘要、问答、声明核验、分类；微调后在 9 个留出任务上平均提升 70.6% | 可作开源模型微调/评测集 | [R50] A |
| SciREX（ACL 2020） | 文档级 IE：显著实体识别 + N 元关系（任务/数据集/指标/方法）；模型与人类差距大 | "数据集/指标"抽取的评测集 | [R51] A |
| AxCell（2020，PwC） | 从 ML 论文表格抽取结果（表格分割子任务） | 结果数字抽取先例；439★ Apache-2.0，2022 年后停更 | [R51] A |
| Paper2Poster（NeurIPS 2025） | 论文→海报的多智能体流水线；开源 Qwen-2.5 变体在多数指标上胜过 4o 驱动系统，token 少 87%，22 页论文生成可编辑海报约 $0.005 | "视觉化卡片/分享图"远期参考（3,956★ MIT） | [R74] A |

**抽取规格（设计伪代码）**：

```text
# 设计伪代码：结构化要点（C 任务），按需、证据锚定
input: sections(intro, method_head, results_head, conclusion, figure/table captions) ≤ 8k tokens
       # 来源：arXiv HTML / JATS / GROBID TEI；仅当 source.shareable 或 owner==当前用户
output_schema:
  contributions: [ {text ≤ 40 words, evidence: [sentence_id]} ] (≤3)
  method:        {text, evidence}
  data:          [ {name, url?, evidence} ]      # 数据集/语料/样本
  results:       [ {text, numbers[], evidence} ] # 数字必须逐字出现在 evidence 中
  limitations:   [ {text, evidence} ]            # 对应 Quick Read 的 Considerations
  code_links:    [url]                           # 只能来自正文/脚注中的 URL
rules: evidence 句子必须存在；numbers ⊆ evidence；否则该条丢弃
```

【合规】结构化要点基于**全文**，派生内容能否跨用户共享取决于全文许可：CC BY/BY-SA/CC0（NC 视部署）可共享；arXiv 非独占许可论文的全文派生要点 ⚠ 需法务（§4 Q3），默认仅用摘要派生；auth-gated 全文只为本人生成、存私有层（与 [recommendation-oss §3 第 7 条](../oss/recommendation-oss.md)一致）。

#### 2.5.2 代码链接

| 来源 | 覆盖/事实 | 许可 | 证据 |
|---|---|---|---|
| 摘要 + arXiv comments 正则 | **E8**：cs.CL 12/80（15%）、cs.CV 9/73（12%）、math.PR 3/79、hep-th 3/80、q-bio.NC 2/64、chem-ph 1/76、stat.ME 1/79，econ.GN、q-fin.ST、cond-mat **0** | 事实链接 | [E8] B |
| HF Papers `githubRepo` | 收录论文中 4/15 有；`githubRepoAddedBy: auto` 表示自动关联 | 未声明 | [E5] B |
| Papers with Code 归档 | PwC 已于 2025-07 关停，paperswithcode.com 现 302 到 `huggingface.co/papers/trending`（核验 2026-09-26）；归档数据 `pwc-archive/links-between-paper-and-code`（**CC BY-SA 4.0**，300,161 条；HF 数据集卡明示"不再更新，对应 2025-07-28 最后一次公开快照"，最后修改 2025-09-10；GitHub `paperswithcode-data` README 仍写"每日重生成"，已过时——核验修正） | CC BY-SA 4.0 | [R52] A |
| 全文 URL 抽取 | GROBID TEI / arXiv HTML 中的脚注与正文链接 | 事实链接 | 设计建议 |
| 校验 | GitHub REST API 校验仓库存在、许可、star、最近推送（需平台 token，限额见官方文档 ⚠） | — | 设计建议 |

#### 2.5.3 数据链接

- **Data Citation Corpus**（DataCite × Make Data Count，Wellcome 资助）：数据集↔论文引用关系；**CC0**；Zenodo（概念 DOI 10.5281/zenodo.11196858）+ 仪表板。核验修正（2026-09-26 读 Zenodo 记录）：最新 v4.1（2025-08-15）含 **10,697,745 条**数据引用记录（9,682,257 个唯一"数据集-论文"对），来源为 DataCite Event Data、CZI Science Knowledge Graph、Aligning Science Across Parkinson's（ASAP）、Europe PMC [R53] A。
- DataCite `relatedIdentifiers`（如 `IsSupplementedBy`）、Zenodo/figshare DOI、HF `linkedDatasets` 可作补充（⚠ 未逐一实测覆盖率）。

### 2.6 成本测算

#### 2.6.1 假设

| 项 | 取值 | 依据 |
|---|---|---|
| 日新增 | S1 = 2,000 篇/日（CS/AI + 经济金融 + 选定理科）；S2 = 10,000；S3 = 30,000 | arXiv 2026 年月投稿 30,045（3 月）、31,604（5 月）、32,040（6 月）[R35]，约 1,000 篇/日；OpenAlex 2026-03 出版文章 778,166 篇 ≈ 2.5 万篇/日 [E6] |
| 库规模 | 1M–10M | 任务书 |
| 候选集比例 | S1 100%；S2/S3 30%（设计假设，需埋点校准） | — |
| 详情打开率 | 候选卡片的 5%（设计假设） | — |
| Token（o200k） | A 包：输入 620（提示 360 + 标题摘要 ~260）/ 输出 220；B（中文摘要）：420 / 320；C（结构化要点）：8,400（全文截断 8k）/ 450 | [E7]；提示长度为设计值；Claude 4.7+ 新分词器约多 30% token [R58]（表 2.6-B/2.6.4 均未计入此系数，只影响 Sonnet 5；Haiku 4.5 仍用旧分词器——核验补充），其他厂商分词器差异 ±30% ⚠ |

#### 2.6.2 价格输入（2026-09-26 核验）

| 厂商 | 模型/计划 | 标准价 输入/输出（$/百万 tokens） | Batch | 备注 | 证据 |
|---|---|---|---|---|---|
| OpenAI | gpt-5-nano | 0.05 / 0.40 | 0.025 / 0.20 | 缓存输入 0.005；Flex 同 Batch | [R54] A |
| OpenAI | gpt-6-luna | 0.10 / 0.50 | 0.05 / 0.25 | 当前旗舰族最小档 | [R54] A |
| OpenAI | gpt-5.4-nano | 0.20 / 1.25 | 0.10 / 0.625 | HHEM 幻觉率 3.1% | [R54][R14] A |
| OpenAI | gpt-5.4-mini | 0.75 / 4.50 | 0.375 / 2.25 | — | [R54] A |
| Google | gemini-2.5-flash-lite | 0.10 / 0.40 | 0.05 / 0.20 | 免费层数据用于改进产品 | [R55] A |
| Google | gemini-3.1-flash-lite | 0.25 / 1.50 | 0.125 / 0.75 | 官方定位含"翻译、简单数据处理" | [R55] A |
| Google | gemini-3.8-flash | 0.75 / 3.75（至 2026-12-31；2027 起 1.50 / 7.50） | 0.375 / 1.875 | 页面 2026-09-24 更新 | [R55] A |
| DeepSeek | deepseek-flash（V4.1-Flash） | 峰时 0.30 / 1.20；谷时 0.15 / 0.60 | — | 峰时 = 工作日 01–04、06–10 UTC；缓存命中 0.006/0.003 | [R56] A |
| 阿里云 | qwen3.8-flash | 国际 0.15 / 0.47；北京 0.113 / 0.382 | 北京标注 Batch 5 折 | — | [R57] A |
| 阿里云 | qwen-mt-flash | 北京 0.101 / 0.280；国际 0.16 / 0.49 | — | 仅翻译 | [R57] A |
| Anthropic | Claude Haiku 4.5 | 1.00 / 5.00 | 0.50 / 2.50 | 缓存读 0.10；Batch 多数 <1 小时完成 | [R58] A |
| Anthropic | Claude Sonnet 5 | 2.00 / 10.00 | 1.00 / 5.00 | 新分词器约多 30% token；$2/$10 原为至 2026-08-31 的首发价，官方已改为标准价，原定 2026-09-01 涨至 $3/$15 取消（核验补充） | [R58] A |
| DeepL | API Growth | €22/百万字符 + €29.75/月 | — | DE 站点价 | [R59] A |
| Google Cloud | Translation NMT / LLM | $20/百万字符；LLM $10 入 + $10 出 | — | 月前 50 万字符免费 | [R60] A |
| RunPod | H100 SXM / H100 PCIe / B200 / L4（按需 Pod 价） | $3.49 / $2.89 / $6.79 / $0.49 每小时 | — | 本地模型估算用 | [R61] A |

完整价格与链接见 `price-inputs-2026-09-26.tsv`。

#### 2.6.3 每千篇成本（表 2.6-B；标准价 / Batch 价，美元）

| 模型 | A 卡片基础包 | B 中文摘要 | C 结构化要点（全文 8k） |
|---|---:|---:|---:|
| OpenAI gpt-5-nano | 0.119 / **0.059** | 0.149 / 0.074 | 0.600 / 0.300 |
| OpenAI gpt-6-luna | 0.172 / 0.086 | 0.202 / 0.101 | 1.065 / 0.532 |
| Google gemini-2.5-flash-lite | 0.150 / 0.075 | 0.170 / 0.085 | 1.020 / 0.510 |
| 阿里云 qwen3.8-flash（北京） | 0.154 / 0.077 | 0.170 / 0.085 | 1.121 / 0.561 |
| 阿里云 qwen3.8-flash（国际） | 0.196 | 0.213 | 1.472 |
| 阿里云 qwen-mt-flash（北京，仅翻译） | — | 0.132 | — |
| DeepSeek deepseek-flash（谷时 / 峰时） | 0.225 / 0.450 | 0.255 / 0.510 | 1.530 / 3.060 |
| OpenAI gpt-5.4-nano | 0.399 / 0.200 | 0.484 / 0.242 | 2.243 / 1.121 |
| Google gemini-3.1-flash-lite | 0.485 / 0.242 | 0.585 / 0.292 | 2.775 / 1.387 |
| Google gemini-3.8-flash | 1.290 / 0.645 | 1.515 / 0.757 | 7.987 / 3.994 |
| OpenAI gpt-5.4-mini | 1.455 / 0.728 | 1.755 / 0.877 | 8.325 / 4.162 |
| Anthropic Claude Haiku 4.5 | 1.720 / 0.860 | 2.020 / 1.010 | 10.650 / 5.325 |
| Anthropic Claude Sonnet 5 | 3.440 / 1.720 | 4.040 / 2.020 | 21.300 / 10.650 |
| **对照：NMT API（仅 B）** | — | DeepL ≈ €30.4；Google NMT ≈ $27.6；Google Translation LLM ≈ $17.3 | — |

#### 2.6.4 场景月成本（30 天；A 进入候选集时生成，B+C 在详情打开时生成）

| 场景 | gpt-5-nano（A Batch，B/C 标准） | qwen3.8-flash 北京（标准） | gemini-3.1-flash-lite（标准） | Claude Haiku 4.5（A Batch，B/C 标准） | Claude Sonnet 5（同左） |
|---|---:|---:|---:|---:|---:|
| S1：2,000/日 × 100% | $5.82 | $13.12 | $39.18 | $89.61 | $179.22 |
| S2：10,000/日 × 30% | $8.73 | $19.68 | $58.77 | $134.42 | $268.83 |
| S3：30,000/日 × 30% | $26.18 | $59.03 | $176.31 | $403.25 | $806.49 |
| 库回填 100 万篇 × A 包（一次性） | $60（Batch） | $154 | $485 | $860（Batch） | $1,720（Batch） |

口径：每日按需量 = 日新增 × 候选比例 × 5%（S1 100 篇、S2 150 篇、S3 450 篇）；按需任务（B/C）不能走 24 小时 Batch，一律按标准价计。

**解读**：①所有方案的月成本都在"百美元级以内"（核验补充：Sonnet 5 若按新分词器 +30% 计，S3 升至约 $1,050/月、略超千美元，但不改变"成本非瓶颈"的结论，⚠ 推断），**模型选择应由忠实度、合规（数据出境/驻留、备案）与延迟决定，而非价格**；②按需策略把 C（全文要点）压到 A 的同量级；③回填不必一次性做——按"首次曝光时生成"即可。

#### 2.6.5 本地小模型 vs API

- **吞吐参照**：Llama-3.1-8B-Instruct 在单卡 H100 80GB、bf16、ShareGPT 1,000 提示 × 10 轮离线批量：SGLang 16,215、LMDeploy 16,132、vLLM 0.11.0（FlashInfer）12,553 **输出 tokens/s**（AIMultiple，2026-04-15 发布、2026-09-25 更新）[R62] A（第三方基准）。
- **折算（⚠ 推断）**：按 vLLM 12,553 tok/s、A 包输出 220 tokens，满载约 20.5 万篇/小时；RunPod H100 SXM $3.49/h → **$0.017/千篇**（利用率 50% 时 $0.034、25% 时 $0.068）；B 任务 $0.025–0.099/千篇。**满载边际成本低于最便宜的 API**，但：①S1/S2 的日量只需 GPU 运行数分钟，闲置或冷启动成本与运维人力占主导；②C 任务为长输入（prefill 为主），上述输出吞吐不适用，需 PoC 实测；③8B 级模型在科学摘要上的忠实度需自测（HHEM：qwen3-8b 4.8%、qwen3-4b 5.7% 为通用领域数据）[R14]。
- **建议**：共享层批量生成用 API Batch（最省事）；**私有层（auth-gated 全文）优先本地/私有部署**，以避免把订阅内容发送给第三方模型（§4 Q11）。

**全文解析成本（C 任务上游）**：GROBID（CPU）约 10.6 PDF/s/16 核机 [R23]，千篇约 94 机器秒；Marker 在单 B200（$6.79/h）上 balanced 2.9 页/s、fast 7.4 页/s [R26][R61] → 以 15 页/篇计约 **$9.8 / $3.8 每千篇**（⚠ 推断）；arXiv HTML 免解析但受 15 s crawl-delay 限制（≈5,760 页/日）。**全文路径（解析 + C 任务）以 Marker GPU 解析计每千篇约 $4–31，是同模型 A 包的约 9–70 倍；改用 CPU 的 GROBID 时解析降到每千篇美分级，但 C 任务 LLM 费用（$0.3–21/千篇）仍是 A 包的约 5–6 倍**（⚠ 推断），另有 PDF 获取的请求配额与合规约束——这是"按需"的主要理由。

#### 2.6.6 延迟

| 环节 | 延迟 | 证据 |
|---|---|---|
| S2 TLDR 可得 | arXiv 公告后 1–2 天（CS/生医） | [E1] B |
| OpenAI Batch | 24 小时完成窗口（常更快）；单批 ≤5 万请求、≤200 MB | [R54] A |
| Anthropic Message Batches | **多数 <1 小时**；24 小时过期；单批 ≤10 万请求或 256 MB；结果保留 29 天 | [R58] A |
| 实时生成（详情打开） | 小模型首 token/总时延 ⚠ 未实测（本轮无 key）；PoC 需测 P50/P95 | — |
| arXiv HTML 取图 | 受 15 s crawl-delay 串行约束 | [R32] A |

#### 2.6.7 缓存与按需生成策略（设计建议）

```text
# 设计伪代码：内容寻址缓存
cache_key = sha256( field ∥ target_lang ∥ source_text_hash ∥ source_version(arXiv vN / DOI 版本)
                    ∥ model_id ∥ prompt_version ∥ policy_version )
shareable(field) = all(src.license ∈ SHAREABLE[deployment] for src in field.sources)
store: shareable ? shared_cache : private_cache[owner_user_id]
tiers:
  T0 ingest      : 取源字段（标题/作者/venue/年份/topics/类目/许可/链接/OA/S2 TLDR）——零生成
  T1 candidate   : 进入任一用户候选集 → A 包（Batch，夜间/谷时）→ 规则闸 + NLI 闸 → shared_cache
  T2 on-demand   : 详情打开 → B 中文摘要、key_figure、C 要点（仅可共享源）→ 闸 → shared_cache
  T3 private     : auth-gated 全文 → 本地/私有模型 → private_cache（永不进入共享层、推荐特征或他人可见解释）
invalidate: 新版本（arXiv vN+1、勘误/撤稿）、许可变更、prompt/model 升级（灰度重算热门 Top-N）
dedupe: 同一 work 的预印本与正式版共享 A 包，除非摘要文本哈希不同
```

### 2.7 质量评估方法

| 字段 | 离线指标 | 自动化工具（许可） | 在线指标 | 上线门槛（设计建议） |
|---|---|---|---|---|
| EN/ZH TL;DR | 事实一致性（分句级）、过度概括率（限定语保留）、信息覆盖（是否含"对象+方法+发现"）、长度 | MiniCheck-FT5（MIT）[R16]、HHEM-2.1-Open（Apache-2.0）[R15]、AlignScore（MIT）[R20]、SummaC（Apache-2.0）[R19]、FineSurE（Apache-2.0）[R17]、G-Eval（MIT）[R18] | "AI 摘要有帮助"👍率、"不准确"举报率、展开原摘要率 | 黄金集分句忠实错误率 ≤2%，过度概括 ≤5% |
| 中文标题/摘要 | MetricX-24 QE、COMET（有参考）、术语命中率、LaTeX 一致性 | MetricX-24（Apache-2.0）、COMET-22（Apache-2.0） | 双语切换率、翻译纠错反馈 | 严重错误（MQM major）≤1/篇 |
| 标签 | 与 arXiv 类目/OpenAlex subfield 一致率、人工 P@3 | 规则 + 抽检 | 标签点击率、"标签不对"反馈 | P@3 ≥ 0.9（subfield 级） |
| 关键图 | 图框 precision/recall、"代表性"人工评分、**许可闸精度必须 100%** | DocumentFigureClassifier（MIT）+ 人工 | 图片点击/停留、举报 | 许可误放行 = 0 |
| 结构化要点 | 证据句存在率、数字一致率、条目完整度 | 规则 + NLI + LLM 裁判 | 详情页停留、"要点有用"率 | 数字不一致 = 0 |
| 代码/数据链接 | 链接有效率、与论文对应正确率 | GitHub API、HTTP HEAD | 点击率 | 死链 <2% |

**评测协议（设计建议）**：黄金集 = 10 个学科 × {arXiv, 期刊} × 30 篇 = 600 篇，含中英双语参考与标注（3 人标注、仲裁）；任何 prompt/模型/策略变更须在黄金集上回归并与上一版做配对比较；线上每日随机抽 1% A 包、每周抽 0.5% 翻译做人工 MQM；LLM 裁判须先用 100 篇人工标注校准一致性（κ）后再用于放量。参考基准：SciTLDR 测试集（ROUGE 仅作辅助，FineSurE 指出 ROUGE 与人类判断相关性差）[R01][R17]、SciRIFF-Eval [R50]、LLM-AggreFact（MiniCheck 统一基准）[R16]。

### 2.8 卡片内容生成流水线建议

#### 2.8.1 字段级决策表

| 卡片字段 | 取源（首选 → 兜底） | 生成方式 | 时机 | 可共享条件 | AI 标识 |
|---|---|---|---|---|---|
| 原文标题 | arXiv / Crossref / OpenAlex | — | T0 | 事实性元数据 | 否 |
| 中文标题 | — | A 包 | T1 | 源为 CC0 元数据或 CC 许可；出版商题名的译名 ⚠（短语、风险低） | 是 |
| 作者·机构·venue·年份·徽章 | OpenAlex / Crossref / VenueSpec | — | T0 | 是 | 否 |
| 原文摘要 | arXiv（CC0）→ CC 许可 OA 版本 → Europe PMC（按 LICENSE）→ Crossref/S2（版权保留：仅短片段 + 链接 ⚠） | — | T0 | 视来源 | 否 |
| EN TL;DR | 自生成（开放摘要）→ S2 TLDR（CS/生医，ODC-BY + 署名）→ 摘要首句 | A 包 | T1 | 源可共享 | 是（S2 TLDR 标"来自 Semantic Scholar"） |
| 中文 TL;DR | 自生成 | A 包 | T1 | 源可共享 | 是 |
| 中文摘要全文 | — | B（通用小模型或 qwen-mt-flash + 术语表） | T2 | 仅 CC0/BY/BY-SA（NC 视部署）；Crossref 摘要只做用户即时私有翻译 ⚠ | 是 |
| 主题标签（≤3） | OpenAlex subfield/topic → arXiv 类目 → PhySH/JEL/MeSH → `/text`（$0.01/篇，仅未收录；⚠ 已标 deprecated）或自托管分类器 | 受控集 LLM 分类（兜底） | T0/T1 | 是 | 自动标签可标"自动" |
| 关键词（检索用） | OpenAlex keywords | KeyBERT / A 包 | T1 | 源可共享 | 是（不展示或弱展示） |
| 关键图 | arXiv HTML → PMC/EPMC JATS → GROBID 坐标 + pypdfium2 / Docling | 规则 + 分类器选图 | T2（或候选 Top-N） | 仅许可闸通过 | 否（原图，附署名/许可/"已裁剪"） |
| 结构化要点 | — | C（证据锚定） | T2 | 仅可共享全文；auth-gated → T3 私有 | 是 |
| 代码/数据链接 | 摘要/comments → HF githubRepo → PwC 归档 → 全文 URL → Data Citation Corpus | 正则 + 校验 | T0/T1 | 是 | 否 |
| 引用数/OA 状态 | OpenAlex | — | T0 | 是 | 否 |

#### 2.8.2 流水线（设计伪代码）

```text
ingest(record):
  meta   = normalize(record)                               # v1 MergeEngine 延续
  lic    = resolve_license(arxiv_oai, crossref.license[vor], pmc.license_code,
                           openalex.best_oa_location.license, html_license_line)   # 多源投票，null=UNKNOWN
  share  = shareability(lic, deployment={commercial|noncommercial})
  fields.T0 = take_from_source(meta)                       # 标题/作者/topics/类目/链接/S2 TLDR(若有)
on_candidate(paper):                                       # 首次进入任一用户候选集
  if share.abstract: enqueue_batch(A_pack(paper.abstract)) → gates(rule, nli) → shared_cache
on_detail_open(user, paper):
  B  = translate_if(share.abstract)                        # 否则：用户即时私有翻译 or 仅原文
  F  = key_figure_if(share.figures)                        # 否则：排版封面
  C  = highlights_if(share.fulltext)                       # 否则：仅摘要派生
  if user.has_private_fulltext(paper): C_private = local_model(fulltext) → private_cache[user]
render(card):
  every AI field → 显式"AI 生成"角标 + 可展开原文；导出/分享图 → 元数据隐式标识
```

#### 2.8.3 合规注意（汇总）

1. 【合规】**摘要版权**：arXiv 元数据（含摘要）CC0 [R31]；Crossref 摘要保留出版商/作者版权 [R40]；OpenAlex 因法律原因只给倒排索引；PubMed 声明部分摘要受版权保护（见聚合源文档 Q2）。共享层只存可共享来源的摘要及其派生物。
2. 【合规】**图片**：只展示许可闸通过的图，并按 CC 要求署名、给许可链接、注明修改 [R39]；图注含第三方许可声明的一律不展示；arXiv 非独占许可论文不得"存储并提供"其 e-print 内容 [R31]。
3. 【合规】**AI 标识（中国）**：《人工智能生成合成内容标识办法》（网信办等四部门 2025-03-14 发布、2025-09-01 施行）第四条：属于深度合成规定第十七条第一款情形的服务，须"在文本的起始、末尾或者中间适当位置添加文字提示或者通用符号提示等标识，或者在交互场景界面、文字周边添加显著的提示标识"，提供下载/复制/导出时文件须含显式标识；第五条：文件元数据须含隐式标识（内容属性、服务提供者名称或编码、内容编号），鼓励数字水印 [R68]。深度合成规定第十七条第一款第（一）项即"智能对话、智能写作等模拟自然人进行文本的生成或者编辑服务"（可能导致公众混淆或误认时须显著标识）[R69]。配套强制性国标 GB 45438—2025《网络安全技术 人工智能生成合成内容标识方法》（2025-02-28 发布）同日实施，全文已在国家标准全文公开系统公开（核验补充：发布/实施日期经国家标准全文公开系统条目页直读确认；⚠ 标准正文本轮仍未读）[R72]。
4. 【合规】**备案与安全评估（中国）**：《生成式人工智能服务管理暂行办法》（2023-08-15 施行）适用于向境内公众提供生成文本等内容的服务（第二条）；具有"舆论属性或者社会动员能力"的，须开展安全评估并履行算法备案（第十七条）[R70]；深度合成规定第十九条对深度合成服务亦有同类备案要求 [R69]。v2 若开放评论/分享卡片，是否构成"舆论属性"⚠ 需法务。
5. 【合规】**AI 标识（欧盟）**：AI Act 第 50 条自 2026-08-02 适用；50(4) 要求部署者对"为向公众告知公共利益事项而发布"的 AI 生成文本进行披露，经实质性人工审核且有人承担编辑责任的除外（拼写/语法检查不算）；50(2) 要求提供者对合成文本做机器可读标记，2026-08-02 前已上市的系统宽限至 2026-12-02；欧盟委员会另有自愿性《AI 生成内容透明度行为准则》[R71]。
6. 【合规】**auth-gated 内容**：用户凭证取回的全文及其派生摘要/要点/图片只存私有层，不进入共享缓存、共享模型训练、他人可见的解释或分享卡片（与兄弟文档一致）；是否可把订阅内容发送给第三方 LLM API 取决于机构/出版商许可条款 ⚠（§4 Q11）。
7. **来源署名**：使用 S2 TLDR 须署名"Semantic Scholar"并引用 Cachola et al. 2020 [R06][R08]；OpenAlex CC0 无强制署名但建议标注；MinerU 若入链路须在产品界面或公开文档致谢 [R25]。

### 2.9 按学科的卡片内容可得性矩阵（实测汇总）

> 均为本轮小样本实测（B 级），用于判断各学科卡片"能自动得到什么"，不代表全量统计。

| 学科（样本） | S2 TLDR 覆盖 | 开放摘要来源 | arXiv HTML 可得 | 图可展示许可（arXiv CC BY/BY-SA/CC0） | LaTeX 占比 | 代码链接 | 对卡片的含义 |
|---|---|---|---|---|---|---|---|
| CS/AI（cs.CL、cs.CV；TPAMI） | arXiv 92–98%；TPAMI 14/20 | arXiv CC0 为主；TPAMI 的 Crossref 摘要 0/20 | 92.8%（cs.CL） | cs 约 42% | 14–16% | 12–15%；HF 收录 16–23% | 最容易做"全功能卡片"：自生成 TL;DR + S2 对照 + 关键图 + 代码链接 |
| 经济/金融/管理（econ.GN、q-fin.ST；AER、JF、Mgmt Sci） | arXiv 32–56%；期刊 AER 1/20、JF 0/20、Mgmt Sci 5/20 | arXiv 部分；**期刊 Crossref 摘要 18–19/20 但版权保留** | econ.GN 68%、q-fin.ST 9/9 | econ 约 38%、q-fin 约 49% | 6–18% | 0 | 主干期刊的共享 TL;DR/翻译受 §4 Q1 阻塞：默认私有即时生成或只展示元数据 + 受控标签；工作论文源（NBER/SSRN 等）的摘要许可需逐源确认 ⚠ |
| 数学（math.PR；Annals） | arXiv 12–15%；Annals 0/16 | arXiv CC0；Annals 的 Crossref 摘要 0/16 | 95.1% | math 约 33% | **67%** | 4% | 以自生成为主，LaTeX 保真与渲染是第一要务；图少，排版封面为常态 |
| 物理（hep-th、cond-mat；PRL） | hep-th **0%**、cond-mat 8–10%；PRL 1/20 | arXiv CC0；PRL 的 Crossref 摘要 4/20 | hep-th 97.8%、cond-mat 68.4% | physics 约 46% | 39–58% | 0–4% | 同数学；APS OA 集可经 Harvest 取 CC BY 全文（见 natural-sciences 文档） |
| 化学（physics.chem-ph；JACS） | arXiv 25–28%；JACS 2/20 | arXiv CC0；JACS 的 Crossref 摘要 1/20 | —（未测） | — | 28% | 1% | 期刊摘要 Crossref 基本缺失（1/20），S2 有（17/20）但版权属性待定（§4 Q4）；卡片以元数据 + 受控标签为主 |
| 生物/医学（q-bio.NC；Cell） | q-bio.NC 72–88%；Cell 18/20 | arXiv/bioRxiv（按许可）/ Europe PMC（按 LICENSE）；Cell 的 Crossref 摘要 0/20 | q-bio.NC 84.2% | q-bio 约 42% | 14% | 3% | S2 TLDR 可用作兜底；OA 论文走 JATS 取图；PMC 许可字段完善 |
| 心理（Psychological Science） | 2/20 | Crossref 摘要 20/20 但版权保留 | — | — | — | — | 同经济期刊：共享生成受 Q1 阻塞；PsyArXiv 等预印本按许可处理（见 life-sciences 文档） |

数据来源：[E1][E2][E3][E4][E8]；"图可展示许可"一列为 E3 中 CC BY + CC BY-SA + CC0 的合计（cs 39.0+2.2+0.6、math 29.6+0.8+2.4、physics 43.9+0.9+1.5、econ 38.5、q-fin 45.9+2.7、q-bio 40.3+1.6，单位 %）。

---

## 3. 对 v2 设计的启示

1. **字段三分 + 私有第四层**：每个卡片字段在数据模型中标注 `origin ∈ {source, generated_batch, generated_on_demand, private}`；T0 取源零成本，T1 批量只做 A 包，T2 按需做翻译/选图/全文要点，T3 私有层只为凭证持有人生成。
2. **"共享派生"不变量**：共享卡片上的一切 AI 内容只能由**可共享来源**派生——arXiv 元数据（CC0）、CC BY/BY-SA/CC0 全文（NC 视部署）；来源不可共享时，要么不生成，要么只在私有层为本人生成。这条应写入 v2 的合规 ADR（与生命科学文档的"许可证门控共享层"合并为一条）。
3. **TL;DR 来源优先级**：自生成（开放摘要）> S2 TLDR（仅 CS/生医有效，按类目覆盖 0–98% 剧烈变化 [E1]，期刊样本平均 24% [E2]）> 摘要首句。S2 TLDR 保留为零成本首版与"抽取式对照"，不作主源。
4. **模型选型原则**：摘要类任务选低幻觉的非推理小模型、温度 0、结构化输出；把"过度概括"作为单独评测维度 [R13][R14]。候选：gpt-5.4-nano（以默认 `reasoning.effort=none` 调用）/ gemini-2.5-flash-lite（HHEM 3.1%/3.3%）；境内部署候选 qwen3.8-flash（北京）或自托管 Qwen3-8B（Apache-2.0）。
5. **生成即校验（三闸）**：规则闸（数字/实体/限定语/LaTeX）+ NLI 闸（MiniCheck-FT5 MIT / HHEM-2.1-Open Apache-2.0）+ 抽样 LLM 裁判与人工审计；不过闸即降级为原文首句，不"带病上卡"。
6. **一次调用多字段**：EN/ZH TL;DR、中文标题、关键词、claim_type、hedged 合并为 A 包；不为标题/摘要单独调用 NMT API（贵约 100 倍）[R59][R60]。
7. **LaTeX 保真是翻译与摘要的硬需求**：29% 的 arXiv 摘要含公式（math.PR 67%）[E8]；提示要求原样保留，校验闸比对公式片段，前端 KaTeX 渲染。
8. **关键图"免解析优先"**：arXiv HTML（近期 88.6% 可得、自带许可行）[E4] → PMC/EPMC JATS → GROBID 坐标 + pypdfium2 / Docling（MIT）兜底；Marker/MinerU 因权重营收门槛/致谢条款列为可选；Nougat 不适用。
9. **许可闸前置且以"未知=拒绝"为默认**：许可取多源投票（arXiv OAI `license`、Crossref `license[vor]`、PMC `license_code`、OpenAlex、HTML 许可行）；arXiv 新记录仅 39.5% 可在商用场景展示图 [E3]，OpenAlex 新文章许可 38.4% 未知 [E6]——"有图卡片"天然是少数，排版封面必须是一等公民。
10. **选图规则化 + 可选 VLM 重排**：Figure 1/overview/framework 类优先，分类器剔除 logo/条码，图注含第三方许可声明者剔除；只在详情页或候选 Top-N 上运行。
11. **标签用受控词表**：展示与过滤用 OpenAlex subfield/field、arXiv 类目、PhySH/JEL/MeSH（注意 MSC2020 为 CC BY-NC-SA）；OpenAlex 细粒度 topic（top-1 训练准确率 0.48 [R43]）只作召回特征；自由关键词只用于检索扩展与 why-this。
12. **OpenAlex topics 取源优先**：记录自带 topics 免费；`/text` 端点 $0.01/篇 [R42] 只用于未收录文本，且因定价页已标 deprecated 不作长期依赖（核验修正）；兜底以自托管 Apache-2.0 的标题+摘要分类器为主。
13. **结构化要点借鉴 Quick Read 的"Considerations"**：把"局限/注意事项"作为必填栏，要点逐条证据锚定（句子 ID/页码），数字必须逐字出现在证据中；只对可共享全文生成，auth-gated 全文走私有层 [R12]。
14. **代码/数据链接多源合并 + 按学科隐藏空位**：摘要/comments 正则在 CS 只有 12–15% 命中，在经济/金融/凝聚态为 0 [E8]；合并 HF githubRepo、PwC 归档（CC BY-SA，已冻结）、全文 URL 与 Data Citation Corpus（CC0），经 GitHub API 校验；非 CS 学科卡片不预留代码位。
15. **成本不是选型主因**：最大场景月成本 $26–$806 [§2.6.4]（Sonnet 5 计入新分词器约 +30% 后约 $1,050，⚠ 推断）；应把预算与精力放在全文获取/解析（全文路径每千篇约为同模型 A 包的 5–70 倍，取决于解析器）、黄金集与人工质检、法务评审上。
16. **数据模型新增 `card_field` 表**（设计建议）：`(work_id, field, lang, value, origin, sources[], license_basis, shareable, model_id, prompt_version, policy_version, source_hash, gate_results, ai_generated, created_at, owner_user_id NULL=共享)`；v1 `meta.tldr` 迁移为 `origin=source, sources=[s2]` 的一行。
17. **内容寻址缓存与版本失效**：缓存键含源文本哈希、源版本、模型与 prompt 版本；arXiv 新版本、撤稿、许可变更触发重算；预印本与正式版在摘要哈希相同时共享 A 包。
18. **批处理节奏**：T1 走 Batch/谷时（DeepSeek 谷时价减半、各家 Batch 5 折；Anthropic 多数 <1 小时、OpenAI ≤24 小时）[R54][R56][R58]；卡片首屏只读缓存字段，按需字段异步生成并用骨架屏占位。
19. **AI 标识双通道**：卡片显式"AI 生成"角标 + 一键看原文；API/导出/分享图写入隐式元数据（生成方、模型、内容编号、时间），满足标识办法第四、五条与 EU AI Act 50(2)/(4) [R68][R71]；S2 TLDR 等第三方生成内容同样标注来源。
20. **境内上线前置法务项**：评估生成式 AI 暂行办法第二、十七条与深度合成规定第十九条下的备案/安全评估义务，以及使用境外模型 API 的数据出境问题；在 ADR 中把"境内用户→境内已备案模型或自托管"列为默认路由（⚠ 需法务确认）。
21. **质量体系先于放量**：600 篇双语黄金集 + 回归门槛（忠实错误 ≤2%、过度概括 ≤5%、许可误放行 0）+ 线上"有帮助/不准确"反馈闭环；LLM 裁判须经人工校准后才能替代抽检。
22. **v1 资产复用**：s2 enrich（`fields=tldr`）直接变 T0 字段；stage 5 extract 落盘的 GROBID TEI（consolidate=0）供 C 任务；选图需在请求中新增 `teiCoordinates=figure`（v1 现未传，核验修正）；v1 FTS（title+abstract）可加入中文译文列以支持中文检索（⚠ 需评估索引体积）。
23. **按学科配置卡片模板与降级链**（依据 §2.9）：CS/生医模板 = TL;DR + 关键图 + 代码/数据链接；数理模板 = TL;DR（LaTeX 渲染）+ 排版封面 + 受控标签；社科/心理期刊模板在 Q1 定论前 = 原文元数据 + 受控标签 + why-this + "为我生成中文速读"按钮（私有、即时、不入共享缓存）。模板选择由 VenueSpec/学科标签驱动，写入卡片服务配置而非前端硬编码。

---

## 4. 未决问题与风险

| # | 问题/风险 | 影响 | 建议处置 |
|---|---|---|---|
| Q1 | 对**出版商版权摘要**做 AI 摘要/翻译并跨用户展示，是否构成侵权演绎（中/美/欧；合理使用与 TDM 例外的边界） | 决定社科/理科期刊论文能否有共享中文 TL;DR | 法务意见；在此之前共享层只对 arXiv（CC0 元数据）与 CC 许可论文生成；期刊论文用"用户即时私有生成、不落共享缓存" |
| Q2 | CC BY-ND / BY-NC-ND 论文的图"原样整图展示"与"裁剪子图"是否构成演绎（CC FAQ 倾向"摘录说明不构成"，但裁剪/配 AI 解说未定） | 约 6–9% 的新论文 [E3][E6] | 默认不上卡片，法务确认后再放开"原样整图" |
| Q3 | arXiv 非独占许可论文（约 52%）的**全文派生要点**能否共享（ToU 禁止存储并提供 e-print 内容，派生摘要是否属于"其他内容"未明） | 决定 CS/数理论文的结构化要点覆盖面 | 默认只用摘要派生；全文要点仅 CC 许可论文或私有层 |
| Q4 | S2 API 返回的期刊摘要（如 JACS/Cell/TPAMI，Crossref 无而 S2 有 [E2]）的文本许可：S2 数据集为 ODC-BY，但单篇摘要的著作权仍属出版商 ⚠。核验补充：S2 Graph API 响应的 `openAccessPdf.disclaimer` 自带声明"论文或摘要……受作者或版权人提供的许可约束，请到源头核实许可与版权信息"（2026-09-26 实测 arXiv:2004.15011、arXiv:2609.30226） | 能否用作生成输入与展示 | 仅作检索/嵌入特征（经法务确认后），不展示、不作共享生成输入 |
| Q5 | HF Papers `ai_summary`/`ai_keywords` 的再使用许可未声明 | 能否在卡片中引用 | 只作内部对照与链接线索 |
| Q6 | OpenAlex `license=null` 的语义混杂（arXiv 非独占、闭源、未知）；Crossref `license` 多条并存（vor/am/tdm） | 许可闸误拒或误放 | 多源投票 + 以最严格结论为准；许可闸精度作为 P0 验收项 |
| Q7 | 成本估算的 token 假设：分词器差异（Claude 4.7+ 多约 30%）、中文输出 token（仅以法规文本测 0.675 token/字，未测真实译文） | 成本 ±30–50% | PoC 用各厂商 token 计数接口复核；结论（百美元级）不因此改变 |
| Q8 | 本地模型的真实吞吐与质量（prefill 为主的长输入、8B 级模型的科学摘要忠实度）未实测 | 私有层方案可行性 | PoC：vLLM/SGLang 在 L4/H100 上跑 A/B/C 三类负载，测 tokens/s 与黄金集指标 |
| Q9 | HHEM 榜为通用领域；Peters 研究的模型较旧；科学摘要（尤其数学/理论物理）上的幻觉/过度概括率未知 | 模型选择 | 以 §2.7 黄金集为准，分学科报告 |
| Q10 | 实时（详情打开）生成的延迟与失败率未测（本轮无 API key） | T2 体验 | PoC 测 P50/P95；超时回退原文 |
| Q11 | 把**订阅内容**（auth-gated 全文）发送给第三方 LLM API 是否违反机构订阅合同/出版商 AI 条款 ⚠ 未核验 | 私有层实现路径 | 默认私有层用本地/私有部署模型；逐出版商核对 TDM/AI 条款（接入各 adapter 文档） |
| Q12 | GB 45438—2025 的具体标识格式、EU《AI 生成内容透明度行为准则》细则本轮未读原文（核验补充：GB 45438—2025 全文可在国家标准全文公开系统在线阅读 [R72]） | 标识实现细节 | 实现前补读标准原文，纳入 ADR |
| Q13 | arXiv HTML 的转换质量（SVG 图、失败率）与 15 s crawl-delay 对批量取图的约束；bulk 需走 arXiv S3 源文件（requester pays）+ 自跑 LaTeXML | 取图覆盖与成本 | 只按需取图；若需批量，评估 S3 源文件 + LaTeXML 的成本与许可 |
| Q14 | 境内部署：使用境外模型 API 的数据出境、以及"模型备案/登记"要求 ⚠ | 上线合规 | 法务评估；境内默认路由到已备案模型或自托管开源模型 |
| Q15 | 平台商业化与否改变 NC 许可内容（图片、翻译、要点）的可用性 | 许可闸配置 | 在需求层先定商业属性，许可闸按部署模式参数化 |
| Q16（核验补充） | OpenAlex `/text`（Tag aboutness）已在定价页标为 deprecated，但端点文档仍在更新，下线时间未公布 | 未收录文本的 topic 兜底 | 以自托管 Apache-2.0 分类器为主，`/text` 仅作可选 |

---

## 5. 参考来源

> 除另注外，访问与核验日期均为 **2026-09-26**。"A/B/C"为证据等级。

**TL;DR 与摘要**

- [R01] Cachola, Lo, Cohan, Weld. *TLDR: Extreme Summarization of Scientific Documents*. Findings of EMNLP 2020. arXiv:2004.15011（CC BY 4.0）— https://arxiv.org/abs/2004.15011 （A）
- [R02] allenai/scitldr（761★，Apache-2.0，pushed 2023-05-22）— https://github.com/allenai/scitldr （A）
- [R03] Semantic Scholar, *TLDR* 产品页 — https://www.semanticscholar.org/product/tldr （A）
- [R04] MIT Technology Review, *An AI helps you summarize the latest in AI*（2020-11-18）— https://www.technologyreview.com/2020/11/18/1012259/ai-summarizes-science-papers-ai2-semantic-scholar/ （C，经检索摘要）
- [R05] Kinney et al. *The Semantic Scholar Open Data Platform*. arXiv:2301.10140（§3.4.1 TLDR 模型）— https://arxiv.org/abs/2301.10140 （A）
- [R06] Semantic Scholar Datasets API，release 列表与各数据集 README（latest = 2026-09-22；`tldrs` 58M，ODC-BY）— https://api.semanticscholar.org/datasets/v1/release/latest （B）
- [R07] Semantic Scholar Graph API swagger（`Tldr` 定义：`model`、`text`）— https://api.semanticscholar.org/graph/v1/swagger.json （A）
- [R08] Semantic Scholar API License Agreement（2023-05-17）— https://www.semanticscholar.org/product/api/license （A）
- [R09] Hugging Face Papers API — https://huggingface.co/api/papers/2004.15011 ；https://huggingface.co/api/daily_papers （B）
- [R10] TideDra/zotero-arxiv-daily（5,992★，AGPL-3.0），`src/zotero_arxiv_daily/protocol.py` — https://github.com/TideDra/zotero-arxiv-daily （A）
- [R11] bojone/papers.cool（Cool Papers）README 与更新日志 — https://github.com/bojone/papers.cool （A）
- [R12] Google Scholar Blog, *Quick Read: see how a paper answers your question*（2026-08-25）— https://scholar.googleblog.com/2026/08/quick-read-see-how-paper-answers-your.html （A）
- [R13] Peters & Chin-Yee. *Generalization bias in large language model summarization of scientific research*. R. Soc. Open Sci. 12(4):241776（2025）；arXiv:2504.00025 — https://arxiv.org/abs/2504.00025 ；https://royalsocietypublishing.org/rsos/article/12/4/241776/235656/Generalization-bias-in-large-language-model （A）
- [R14] vectara/hallucination-leaderboard（3,313★，Apache-2.0；Last updated 2026-09-22）— https://github.com/vectara/hallucination-leaderboard （A）
- [R15] vectara/hallucination_evaluation_model（HHEM-2.1-Open，Apache-2.0）— https://huggingface.co/vectara/hallucination_evaluation_model （A）
- [R16] Tang, Laban, Durrett. *MiniCheck*. EMNLP 2024. arXiv:2404.10774；Liyan06/MiniCheck（228★，Apache-2.0）；lytang/MiniCheck-Flan-T5-Large（MIT）— https://arxiv.org/abs/2404.10774 ；https://github.com/Liyan06/MiniCheck ；https://huggingface.co/lytang/MiniCheck-Flan-T5-Large （A）
- [R17] Song et al. *FineSurE*. ACL 2024. arXiv:2407.00908；DISL-Lab/FineSurE-ACL24（Apache-2.0）— https://arxiv.org/abs/2407.00908 （A）
- [R18] Liu et al. *G-Eval*. arXiv:2303.16634；nlpyang/geval（429★，MIT）— https://arxiv.org/abs/2303.16634 （A）
- [R19] Laban et al. *SummaC*. TACL. arXiv:2111.09525；tingofurro/summac（Apache-2.0）— https://arxiv.org/abs/2111.09525 （A）
- [R20] Zha et al. *AlignScore*. ACL 2023. arXiv:2305.16739；yuh-zha/AlignScore（MIT）— https://arxiv.org/abs/2305.16739 （A）

**关键图与文档解析**

- [R21] allenai/pdffigures2 README（759★，Apache-2.0，pushed 2024-03-10）；Clark & Divvala, *PDFFigures 2.0*, JCDL 2016 — https://github.com/allenai/pdffigures2 （A）
- [R22] Siegel et al. *Extracting Scientific Figures with Distantly Supervised Neural Networks*. JCDL 2018. arXiv:1804.02445；allenai/deepfigures-open — https://arxiv.org/abs/1804.02445 （A）
- [R23] GROBID 文档：`doc/Grobid-service.md`、`doc/Coordinates-in-PDF.md`、`doc/Frequently-asked-questions.md`、README（10.6 PDF/s）；grobidOrg/grobid（5,143★，Apache-2.0，0.9.1）— https://github.com/grobidOrg/grobid （A）
- [R24] Docling：`docs/examples/export_figures.py`；Enrichment 文档；docling-project/DocumentFigureClassifier-v2.5（MIT）— https://github.com/docling-project/docling ；https://docling-project.github.io/docling/usage/enrichments/ ；https://huggingface.co/docling-project/DocumentFigureClassifier-v2.5 （A）
- [R25] MinerU LICENSE.md 与输出文件说明 — https://github.com/opendatalab/MinerU/blob/master/LICENSE.md ；https://opendatalab.github.io/MinerU/reference/output_files/ （A）
- [R26] datalab-to/marker README（39,987★；吞吐与 olmOCR-bench 表）— https://github.com/datalab-to/marker （A，自报数据）
- [R27] facebookresearch/nougat README（代码 MIT、权重 CC-BY-NC）；arXiv:2308.13418 — https://github.com/facebookresearch/nougat （A）
- [R28] arXiv Blog, *Accessibility update: arXiv now offers papers in HTML format*（2023-12-21）— https://blog.arxiv.org/2023/12/21/accessibility-update-arxiv-now-offers-papers-in-html-format/ （A）
- [R29] arXiv HTML 实例 2609.30226v1（figure 标记与许可行）— https://arxiv.org/html/2609.30226v1 ；ar5iv：https://github.com/dginev/ar5iv （B/A）
- [R36] Yang et al. *Identifying the Central Figure of a Scientific Paper*. ICDAR 2019 — https://www.semanticscholar.org/paper/bbcb64958c280b5abc3c741457effe30a90dea45 （C，数字经检索摘要）；数据 https://github.com/viziometrics/centraul_figure （A）
- [R37] Flicke et al. *Scholar Inbox*. arXiv:2504.08385v2（ACL 2025 Demo；CC BY 4.0）— https://arxiv.org/html/2504.08385v2 （A）
- [R73] pypdfium2 README Licensing（Apache-2.0 / BSD-3-Clause）— https://github.com/pypdfium2-team/pypdfium2 （A）
- [R74] Pang et al. *Paper2Poster*. arXiv:2505.21497；Paper2Poster/Paper2Poster（3,956★，MIT）；showlab/Paper2Video（2,381★，MIT）— https://arxiv.org/abs/2505.21497 （A）
- [R75] Hsu et al. *SciCap*. arXiv:2110.11624 — https://arxiv.org/abs/2110.11624 （A）
- [R80] 文档解析技术报告：Docling arXiv:2408.09869；MinerU arXiv:2409.18839；MinerU2.5 arXiv:2509.22186；olmOCR arXiv:2502.18443；DocLayout-YOLO arXiv:2410.12628（仓库 AGPL-3.0）— https://arxiv.org/abs/2408.09869 等 （A）
- [R81]（核验补充）OpenAI 模型页 *gpt-5.4-nano*（`reasoning.effort` 支持 none〔默认〕/low/medium/high/xhigh；快照 gpt-5.4-nano-2026-03-17）— https://developers.openai.com/api/docs/models/gpt-5.4-nano （A）
- [R82]（核验补充）Hugging Face Hub 文档 *Paper Pages*（仓库卡片引用 arXiv 自动关联；可在 `hf.co/papers/{id}` 手动索引任意 arXiv 论文）— https://huggingface.co/docs/hub/paper-pages （A）
- [R83]（核验补充）PDFMathTranslate/PDFMathTranslate（37,202★，AGPL-3.0，EMNLP 2025 System Demonstrations）；funstory-ai/BabelDOC（9,611★，AGPL-3.0）— https://github.com/PDFMathTranslate/PDFMathTranslate ；https://github.com/funstory-ai/BabelDOC ；https://aclanthology.org/2025.emnlp-demos.71/ （A）

**arXiv 政策与数据**

- [R30] arXiv, *License and copyright*（许可选项、非独占许可、元数据 CC0）— https://info.arxiv.org/help/license/index.html （A）
- [R31] arXiv, *API Terms of Use*（元数据 CC0 含摘要；不得存储并提供 e-print；3 秒 1 次单连接）— https://info.arxiv.org/help/api/tou.html （A）
- [R32] arXiv robots.txt（`Crawl-delay: 15`；Allow `/list /abs /pdf /html`）— https://arxiv.org/robots.txt （A）
- [R33] arXiv OAI-PMH（ListSets / ListRecords `metadataPrefix=arXiv`）— https://oaipmh.arxiv.org/oai （B）
- [R34] arXiv Category Taxonomy（155 个类目）— https://arxiv.org/category_taxonomy （B）
- [R35] arXiv Blog, *arXiv now hosts over 3 million articles*（2026-07-09；月投稿 30,045–32,040）— https://blog.arxiv.org/2026/07/09/arxiv-now-hosts-over-3-million-articles/ （A）

**许可与版权**

- [R38] Creative Commons FAQ（ND 摘录、何为演绎、TDM）— https://creativecommons.org/faq/ （A）
- [R39] CC BY 4.0 Legal Code（Adapted Material 定义含 translated；2(a)(4) 技术修改；3(a) 署名与修改标注）— https://creativecommons.org/licenses/by/4.0/legalcode.en （A）
- [R40] Initiative for Open Abstracts（2020-09-24 启动；转述 Crossref：摘要可能受版权保护、转载需版权人明确许可）— https://i4oa.org/ （A）
- 聚合源文档引用：Crossref *Metadata Retrieval*（事实 CC0、摘要保留版权）https://www.crossref.org/documentation/retrieve-metadata/ ；OpenAlex *Works attributes*（`abstract_inverted_index` 的法律说明）https://help.openalex.org/data/works/attributes/ ——见 [aggregators-repositories](../sources/aggregators-repositories.md) [S8][S23]

**标签与主题**

- [R41] OpenAlex Help, *Topics*（4/26/252/4,516；输入与 12% 无 topic）— https://help.openalex.org/data/topics （A）
- [R42] OpenAlex Help, *Tag aboutness*（`/text`；20–2,000 字符；1 rps；$0.01/请求；页面 2026-09-22 更新）— https://help.openalex.org/api/tag-aboutness ；核验补充：OpenAlex *Example costs*（"Text / Aboutness (deprecated)" $10/千次；List+filter $0.10/千次；无 key 每日额度 $0.10、有 key $1）— https://help.openalex.org/access/example-costs （A）
- [R43] ourresearch/openalex-topic-classification（59★，MIT）；OpenAlex/bert-base-multilingual-cased-finetuned-openalex-topic-classification-title-abstract（Apache-2.0）— https://github.com/ourresearch/openalex-topic-classification ；https://huggingface.co/OpenAlex/bert-base-multilingual-cased-finetuned-openalex-topic-classification-title-abstract （A）
- [R44] OpenAlex API 实时查询（group_by 许可/OA 状态，2026-09-26）— https://api.openalex.org/works?filter=from_publication_date:2026-03-01,to_publication_date:2026-03-31,type:article&group_by=best_oa_location.license （B）
- [R45] MaartenGr/KeyBERT（4,221★，MIT）— https://github.com/MaartenGr/KeyBERT （A）
- [R46] INESCTEC/yake LICENSE（AGPL-3.0 + 可购商业许可）— https://github.com/INESCTEC/yake （A）
- [R47] Song et al. *Large Language Models as Zero-Shot Keyphrase Extractors*. arXiv:2312.15156 — https://arxiv.org/abs/2312.15156 （A）
- [R48] Kong et al. *PromptRank*. ACL 2023. arXiv:2305.04490 — https://arxiv.org/abs/2305.04490 （A）
- [R49] allenai/s2_fos（34★，Apache-2.0）— https://github.com/allenai/s2_fos （A）

**结构化抽取与链接**

- [R50] Wadden et al. *SciRIFF*. arXiv:2406.07835（EMNLP 2025）— https://arxiv.org/abs/2406.07835 （A）
- [R51] Jain et al. *SciREX*. ACL 2020. arXiv:2005.00512；Kardas et al. *AxCell*. arXiv:2004.14356；paperswithcode/axcell（439★，Apache-2.0）— https://arxiv.org/abs/2005.00512 ；https://arxiv.org/abs/2004.14356 （A）
- [R52] paperswithcode/paperswithcode-data README（CC-BY-SA；仍写"data is regenerated daily"）；HF 数据集 pwc-archive/links-between-paper-and-code（cc-by-sa-4.0，300,161 条，最后修改 2025-09-10；数据集卡："will not be updated … snapshot … retrieved on July 28th, 2025"）— https://github.com/paperswithcode/paperswithcode-data ；https://huggingface.co/datasets/pwc-archive/links-between-paper-and-code （A）
- [R53] DataCite, *Data Citation Corpus*（页面更新 2026-08-07）；Make Data Count 数据引用页；核验补充：Zenodo 记录 *Data Citation Corpus Data File* v4.1（2025-08-15，cc-zero，10,697,745 条）— https://support.datacite.org/docs/data-citation-corpus ；https://makedatacount.org/data-citation/ ；https://zenodo.org/records/16901115 （A）

**价格与算力**

- [R54] OpenAI API Pricing；Batch 指南（24h 窗口、≤5 万请求、≤200 MB）— https://developers.openai.com/api/docs/pricing ；https://developers.openai.com/api/docs/guides/batch （A）
- [R55] Gemini API Pricing（页面更新 2026-09-24）— https://ai.google.dev/gemini-api/docs/pricing （A）
- [R56] DeepSeek API, *Models & Pricing* — https://api-docs.deepseek.com/quick_start/pricing （A）
- [R57] Alibaba Cloud Model Studio, *Model pricing*（更新 2026-09-24）；*Machine translation (Qwen-MT)* — https://www.alibabacloud.com/help/en/model-studio/model-pricing ；https://www.alibabacloud.com/help/en/model-studio/machine-translation （A）
- [R58] Anthropic, *Pricing*（含脚注：Sonnet 5 的 $2/$10 由首发价转为标准价、原定 2026-09-01 涨价取消；"Claude 4.7 及以后"新分词器同文本约多 30% token，Sonnet 4.6 及更早仍用旧分词器）；*Batch processing*（≤10 万请求或 256 MB；多数 1 小时内完成；24 小时过期；结果保留 29 天）— https://platform.claude.com/docs/en/about-claude/pricing ；https://platform.claude.com/docs/en/build-with-claude/batch-processing （A）
- [R59] DeepL API 页面（内嵌计划 JSON：api-developer 免费 100 万字符/月；api-growth €29.75/月 + €22/百万字符）— https://www.deepl.com/en/pro-api （A/B）
- [R60] Google Cloud, *Cloud Translation pricing* — https://cloud.google.com/translate/pricing （A）
- [R61] RunPod, *Pricing*（按需 GPU 小时价）— https://www.runpod.io/pricing （A）
- [R62] AIMultiple, *LLM Inference Engines: vLLM vs LMDeploy vs SGLang*（2026-04-15，更新 2026-09-25）— https://aimultiple.com/inference-engines （A，第三方基准）

**翻译模型与评测**

- [R63] Tencent-Hunyuan/Hunyuan-MT（722★；License.txt 地域条款）；*Hunyuan-MT Technical Report* arXiv:2509.05209（WMT2025 General MT 31 个语向中 30 个第一）；核验补充：Tencent-Hunyuan/HY-MT（826★；HY-MT1.5，2025-12-30；TENCENT HY COMMUNITY LICENSE 同样排除欧盟/英国/韩国）— https://github.com/Tencent-Hunyuan/Hunyuan-MT ；https://arxiv.org/abs/2509.05209 ；https://github.com/Tencent-Hunyuan/HY-MT （A）
- [R64] *Seed-X*. arXiv:2507.13618；ByteDance-Seed/Seed-X-PPO-7B（OpenMDW）— https://arxiv.org/abs/2507.13618 ；https://huggingface.co/ByteDance-Seed/Seed-X-PPO-7B （A）
- [R65] facebook/nllb-200-distilled-600M（cc-by-nc-4.0）— https://huggingface.co/facebook/nllb-200-distilled-600M （A）
- [R66] Rei et al. *COMET*. arXiv:2009.09025；Unbabel/wmt22-comet-da（Apache-2.0）；Unbabel/wmt22-cometkiwi-da、Unbabel/XCOMET-XL（cc-by-nc-sa-4.0）— https://huggingface.co/Unbabel/wmt22-comet-da （A）
- [R67] Juraska et al. *MetricX-24*. arXiv:2410.03983；google/metricx-24-hybrid-large-v2p6（Apache-2.0）— https://arxiv.org/abs/2410.03983 ；https://huggingface.co/google/metricx-24-hybrid-large-v2p6 （A）
- [R76] Hugging Face 模型卡许可字段（Qwen/Qwen3-4B、Qwen/Qwen3-8B、Qwen/Qwen3-14B：apache-2.0；microsoft/phi-4：mit；google/gemma-3-12b-it：gemma；meta-llama/Llama-3.1-8B-Instruct：llama3.1；ibm-granite/granite-4.0-h-small：apache-2.0）— https://huggingface.co/api/models/{id} （B）

**法规**

- [R68] 国家网信办等四部门，《人工智能生成合成内容标识办法》（2025-03-14 发布，2025-09-01 施行）— https://www.cac.gov.cn/2025-03/14/c_1743654684782215.htm （A）
- [R69] 《互联网信息服务深度合成管理规定》（2023-01-10 施行；第十六至十九条）— https://www.cac.gov.cn/2022-12/11/c_1672221949354811.htm （A）
- [R70] 《生成式人工智能服务管理暂行办法》（2023-08-15 施行；第二、十二、十七条）— https://www.cac.gov.cn/2023-07/13/c_1690898327029107.htm （A）
- [R71] EU AI Act Article 50 — https://artificialintelligenceact.eu/article/50/ ；European Commission, *Transparency obligations under Article 50 of the AI Act* FAQ（更新 2026-07-24）— https://digital-strategy.ec.europa.eu/en/faqs/transparency-obligations-under-article-50-ai-act （A）
- [R72] 新华网，《9月1日起 AI生成合成内容必须添加标识》（2025-09-01；提及 GB 45438—2025）— https://www.news.cn/legal/20250901/a12108b0b10249e5bae4435269e40c91/c.html （C）；核验补充：国家标准信息公共服务平台 / 国家标准全文公开系统 GB 45438-2025 条目（现行；2025-02-28 发布、2025-09-01 实施；发布单位国家市场监督管理总局、国家标准化管理委员会；提供在线预览/下载，经条目页直读确认）— https://openstd.samr.gov.cn/bzgk/std/newGbInfo?hcno=F32EA2A561F1886CD8D606513512D547 ；https://std.samr.gov.cn/gb/search/gbDetailed?id=301E0388CB75788DE06397BE0A0AE1B4 （A，未读正文）

**项目内文档（兄弟调研与 v1 设计）**

- [ux/card-feed-interaction](../ux/card-feed-interaction.md)（卡片字段优先级、许可硬约束 §2.6.6）；[oss/paper-acquisition-and-search-oss](../oss/paper-acquisition-and-search-oss.md)（PDF 解析器全表 §2.9、PwC 关停、MinerU/Marker 许可）；[sources/aggregators-repositories](../sources/aggregators-repositories.md)（S2/OpenAlex/Crossref 字段与摘要法律边界 Q2）；[sources/life-sciences-psychology](../sources/life-sciences-psychology.md)（PMC/EPMC 许可字段与共享层门控）；[sources/natural-sciences](../sources/natural-sciences.md)（PhySH/MSC 许可）；[sources/social-sciences-econ-fin-mgmt](../sources/social-sciences-econ-fin-mgmt.md)（JEL 来源）；[market/startups-and-products](../market/startups-and-products.md)（AI 速读先例 I-11、合规分层 I-12）；[oss/recommendation-oss](../oss/recommendation-oss.md)（共享层/私有层分离 §3-7）；[algorithms/retrieval-routing-indexing](retrieval-routing-indexing.md)（跨分类体系对齐）；v1 [design/12-fulltext-extract](../../archive-v1.md#docs-design-12-fulltext-extract-md)、[design/adapters/aggregators](../../archive-v1.md#docs-design-adapters-aggregators-md)、[design/adapters/arxiv](../../archive-v1.md#docs-design-adapters-arxiv-md)。

**本轮一手实测数据（B 级，同名子目录）**：`s2-tldr-coverage-2026-09-26.tsv`（E1/E2）、`arxiv-sample-stats-2026-09-26.json`（E1/E7/E8）、`arxiv-license-dist-2026-09-26.json`（E3）、`arxiv-html-availability-2026-09-26.json`（E4）、`hf-papers-coverage-2026-09-26.json`（E5）、`openalex-license-groupby-2026-09-26.json`（E6）、`price-inputs-2026-09-26.tsv`（§2.6.2）、`repo-metrics-2026-09-26.tsv`（41 个仓库的 star/许可/推送时间）、`request-ledger-2026-09-26.tsv`（225 次外部请求台账）。

---

## 核验记录

> **核验角色**：对抗式事实核验（Verify），核验日期 2026-09-26（外部请求实际发生在 UTC 2026-09-26/27 之交）。这是本文唯一的核验记录节。核验前文中没有"核验记录"类章节，也没有前次中断留下的半截修改：表格列数一致、`[R#]` 引用全部闭合，均已用脚本检查。正文中的核验改动统一标为"核验修正 / 核验补充 / 核验注 / 核验复算"。

**核验方法与过程记录（可复现）**：

- **一手源直读**：
  - `gh api`：约 30 个仓库的 star/license/pushed_at/最新 release；另读 MinerU `LICENSE.md`、YAKE `LICENSE`、Hunyuan-MT 与 HY-MT 的 `License.txt`、Marker/GROBID/Nougat/pypdfium2/PDFFigures2 README 与 GROBID FAQ/Coordinates 文档、HHEM 榜 README、zotero-arxiv-daily `protocol.py`、Cool Papers README。
  - HF Hub API：19 个模型卡的 license 字段、DocumentFigureClassifier-v2.5 卡、OpenAlex 分类器卡、`pwc-archive` 数据集卡，以及 HF Papers API（2004.15011）。
  - 论文与学术数据接口：arXiv Query API 两次 `id_list` 批查 20 篇摘要；S2 Graph API 成功 2 次（其中 1 次先遇 429，退避 20 s 后重试成功）；S2 Datasets `release/latest` 与 swagger；OpenAlex group_by 复测 1 次（$0.0001）；Crossref `works/10.1098/rsos.241776`；Zenodo records API。
  - 价格页：OpenAI（含模型页与 Batch 指南）、Gemini、DeepSeek、阿里云（价格页与 Qwen-MT 文档）、Anthropic（价格页与 Batch 文档）、DeepL（页面内嵌计划 JSON）、Google Cloud Translation（原始 HTML）、RunPod。
  - 法规与标准：网信办三份法规原文、欧盟委员会 Article 50 FAQ、国家标准全文公开系统 GB 45438-2025 条目。
  - 许可与政策：CC BY 4.0 法律文本与 CC FAQ（原始 HTML）、I4OA；arXiv 许可页、API ToU、robots（arxiv.org 与 export.arxiv.org）、HTML 上线博客、300 万篇博客、分类页、HTML 实例 2609.30226v1。
  - 其他：Google Scholar Blog（原始 HTML）、AIMultiple、HF Paper Pages 文档，以及本仓库源码 `src/paper_crawler/pipeline/extract.py`、`src/paper_crawler/adapters/s2/`、`src/paper_crawler/storage/migrations/`。
- **WebSearch 检索式**（2026-09-26）：`Semantic Scholar TLDR launch November 2020 "10 million" computer science papers beta`；`"Scholar Inbox: Personalized Paper Recommendations for Scientists" ACL 2025 System Demonstrations aclanthology`；`"Identifying the Central Figure of a Scientific Paper" ICDAR 2019 87% authors surveyed central figure`；`GB 45438-2025 网络安全技术 人工智能生成合成内容标识方法 2025年9月1日 实施 强制性国家标准`；`MSC2020 Mathematics Subject Classification license "Creative Commons" CC BY-NC-SA msc2020.org`。
- **复算**：
  - 表 2.6-B 全部单元格与 §2.6.4 场景月成本逐项重算，与原文一致。
  - E1–E6、E8 的百分比按子目录原始文件逐项重算，一致；E6 用 OpenAlex 实时接口复测，计数完全一致。
  - E7 用 `tiktoken` o200k 复算为 0.689 token/字符，与原文量级一致。
- **受阻与处置**：多个页面的 WebFetch 摘要不可靠，均改为取原始 HTML 或重问后以原文为准——DeepL、Google Cloud Translation、Google Scholar Blog 的摘要失败或被截断（改用 curl 解析）；Qwen-MT 的第一次摘要把领域提示支持范围说错（二次读取功能表更正）；CC FAQ 的摘要误报"无 TDM 内容"（改用 curl 读原文）。全程未绕过任何访问控制。

| 断言 | 结论（确认/修正/删除/未核验） | 依据来源 URL | 核验日期 |
|---|---|---|---|
| S2 TLDR 覆盖与上线：产品页称近 6,000 万篇 CS/生物/医学论文、约"20 词"；2020-11-16 上线，首批约 1,000 万篇 CS 论文（Beta） | 确认；上线数字为 C 级，两处二手来源一致 | https://www.semanticscholar.org/product/tldr ；https://x.com/semanticscholar/status/1328360185597812736 ；https://www.infodocket.com/2020/11/17/research-tools-semantic-scholar-launches-tldr-beta-feature-uses-nlp-to-place-single-sentence-automatically-generated-paper-summaries-on-search-results-pages/ | 2026-09-26 |
| S2 Datasets 最新 release 为 2026-09-22；`tldrs` 58M 条（30 个 200 MB 文件）；ODC-BY，用于产品须引用 Cachola et al. 2020 | 确认 | https://api.semanticscholar.org/datasets/v1/release/latest | 2026-09-26 |
| S2 API 协议（2023-05-17）：须署名"Semantic Scholar"，不得转售、再许可、再分发 API；batch 每次 ≤500 id；有 key 时入门额度 1 RPS | 确认；另核得 batch 单次响应 ≤10 MB | https://www.semanticscholar.org/product/api/license ；https://api.semanticscholar.org/graph/v1/swagger.json ；https://www.semanticscholar.org/product/api | 2026-09-26 |
| TLDR 模型 `tldr@v2.0.0` 为 BART + CATTS，训练集是 SciTLDR 加 S2 另收集的生医论文摘要；SciTLDR 含 5.4K 条 TLDR、覆盖 3.2K 篇论文，发表于 Findings of EMNLP 2020；scitldr 仓库 761★、Apache-2.0；复读实例为 2609.30226 | 确认 | https://api.semanticscholar.org/graph/v1/paper/arXiv:2609.30226?fields=tldr ；https://arxiv.org/abs/2301.10140 ；https://arxiv.org/abs/2004.15011 ；https://github.com/allenai/scitldr | 2026-09-26 |
| Peters & Chin-Yee：测 10 个 LLM、4,900 份摘要；DeepSeek、ChatGPT-4o、LLaMA 3.3 70B 过度概括率 26–73%；OR=4.85（95% CI 3.06–7.70）；新模型更差；刊于 R. Soc. Open Sci. 12(4):241776 | 确认 | https://arxiv.org/abs/2504.00025 ；https://api.crossref.org/works/10.1098/rsos.241776 | 2026-09-26 |
| Vectara HHEM 榜（2026-09-22 更新，7,700+ 篇、温度 0、HHEM-2.3）上 15 个模型的幻觉率，从 gpt-5.4-nano 3.1% 到 o3-pro 23.3%；仓库 3,313★ | 确认，15 个数字逐一对上；另补 gpt-5.4-mini 5.5% | https://github.com/vectara/hallucination-leaderboard | 2026-09-26 |
| 称 gpt-5.4-nano 为"非推理小模型"，并在提示参数中写 `reasoning_effort=minimal` | 修正：该模型支持推理，`reasoning.effort` 可取 none（默认）/low/medium/high/xhigh，没有 minimal | https://developers.openai.com/api/docs/models/gpt-5.4-nano | 2026-09-26 |
| 评测工具：MiniCheck-FT5 为 770M，达 GPT-4 精度、成本低 400 倍（EMNLP 2024），HF 权重 MIT；HHEM-2.1-Open 为 Apache-2.0；FineSurE 发表于 ACL 2024 并补"完整性/简洁性"两维；G-Eval 代码 MIT | 确认 | https://arxiv.org/abs/2404.10774 ；https://huggingface.co/lytang/MiniCheck-Flan-T5-Large ；https://huggingface.co/vectara/hallucination_evaluation_model ；https://arxiv.org/abs/2407.00908 ；https://github.com/nlpyang/geval | 2026-09-26 |
| arXiv 许可与访问规则：共 6 种许可、不可撤销，非独占许可限制他人任何再利用；元数据（含标题、摘要）为 CC0；不得存储并提供 e-print；API 每 3 秒 ≤1 次、单连接；arxiv.org `Crawl-delay: 15`，export.arxiv.org `Disallow: /` | 确认 | https://info.arxiv.org/help/license/index.html ；https://info.arxiv.org/help/api/tou.html ；https://arxiv.org/robots.txt ；https://export.arxiv.org/robots.txt | 2026-09-26 |
| arXiv HTML：2023-12-18 起为 2023-12-01 之后的 TeX 投稿提供（实验性），页面含 `ltx_figure`、SVG/PNG 图与许可行；arXiv 共 155 个类目；2026 年月投稿 30,045（3 月）/31,604（5 月）/32,040（6 月） | 确认；复读 2609.30226v1，有 15 个 figure 与"License: CC BY 4.0"行 | https://blog.arxiv.org/2023/12/21/accessibility-update-arxiv-now-offers-papers-in-html-format/ ；https://arxiv.org/html/2609.30226v1 ；https://arxiv.org/category_taxonomy ；https://blog.arxiv.org/2026/07/09/arxiv-now-hosts-over-3-million-articles/ | 2026-09-26 |
| GROBID 0.9.1，5,143★，Apache-2.0；`teiCoordinates=figure` 同时覆盖图与表；`processFulltextAssetDocument` 已弃用；"CRF 模型 16 核机约 10.6 PDF/s" | 修正措辞：README 原文为"16 CPU/16 线程、32 GB 单机，node.js 客户端，约 10.6 PDF/s"，未提 CRF；其余确认 | https://github.com/grobidOrg/grobid ；https://github.com/grobidOrg/grobid/blob/master/doc/Frequently-asked-questions.md ；https://github.com/grobidOrg/grobid/blob/master/doc/Coordinates-in-PDF.md | 2026-09-26 |
| v1 的 stage 5 GROBID TEI 可直接提供图坐标（`teiCoordinates=figure`）；v1 有 `fulltext_asset` 表 | 修正：v1 只传 3 个 `consolidate*=0`，未传 `teiCoordinates`；`fulltext_asset` 是迁移文件名，实际表名为 `fulltext`/`asset` | 本仓库 `src/paper_crawler/pipeline/extract.py`（`_CONSOLIDATE_OFF`、`_post`）；`src/paper_crawler/storage/migrations/0001_init.sql`、`0004_fulltext_asset.sql` | 2026-09-26 |
| Docling v2.130.0，67,991★，MIT；`do_picture_classification` 使用 DocumentFigureClassifier-v2.5（EfficientNet-B0、26 类、MIT）；`do_picture_description` 可接 SmolVLM-256M（Apache-2.0）或 Granite Vision；选图伪代码使用 `photo_of_author`、`diagram` 类 | 前半确认；修正伪代码：这两个类名不存在，已改为该分类器的真实类名 | https://github.com/docling-project/docling ；https://docling-project.github.io/docling/usage/enrichments/ ；https://huggingface.co/docling-project/DocumentFigureClassifier-v2.5 | 2026-09-26 |
| MinerU 4.x：Apache-2.0，附加条款要求 MAU>1 亿或月收入>2,000 万美元时取得商业许可，并须标明使用 MinerU。Marker v2：代码 Apache-2.0，权重为修改版 OpenRAIL-M（融资或营收 <500 万美元免费），单 B200 吞吐 23.7/7.4/2.9 页/s。Nougat：代码 MIT，权重 CC-BY-NC | 确认；补：MinerU 附加条款违约即自动终止 | https://github.com/opendatalab/MinerU/blob/master/LICENSE.md ；https://github.com/datalab-to/marker ；https://github.com/facebookresearch/nougat | 2026-09-26 |
| 取图研究数字：DeepFigures 550 万条标注、精度 96.8%、在 S2 为 1,300 万篇文档抽图；PDFFigures2 按 72 DPI 给坐标，只抽带图注的图；SciCap graph plot 类占 19.2%；Yang 等调查 6,263 位作者、8,353 篇论文，87% 以上有中心图 | 确认（Yang 为 C 级）；补：Yang 的受访者是 PubMed 论文作者 | https://arxiv.org/abs/1804.02445 ；https://github.com/allenai/pdffigures2 ；https://arxiv.org/abs/2110.11624 ；https://www.semanticscholar.org/paper/bbcb64958c280b5abc3c741457effe30a90dea45 ；https://github.com/viziometrics/centraul_figure | 2026-09-26 |
| 先例：Scholar Inbox 展示前五张图表（papermage 抽取），为 ACL 2025 Demo；zotero-arxiv-daily 截断到 4,000 tokens、生成一句 TLDR、失败时回退摘要；Cool Papers 于 2025-06-04 因 bioRxiv 启用 Cloudflare 而下线该源 | 确认 | https://arxiv.org/html/2504.08385v2 ；https://aclanthology.org/2025.acl-demo.30/ ；https://github.com/TideDra/zotero-arxiv-daily ；https://github.com/bojone/papers.cool | 2026-09-26 |
| Google Scholar Quick Read（2026-08-25）：概述加 Answers/Approach/Considerations 三段；只对用户有访问权的论文出现；与出版商合作开放订阅文章；需登录、仅英文；输入为"论文全文" | 修正：官方未说明是否读全文，改标 ⚠ 推断；其余确认 | https://scholar.googleblog.com/2026/08/quick-read-see-how-paper-answers-your.html | 2026-09-26 |
| HF Papers API 返回 `ai_summary`、`ai_keywords`、`ai_summary_model`、`githubRepo`、`githubRepoAddedBy` 等字段；称"只覆盖被提交到 Daily Papers 的论文" | 字段确认；修正覆盖描述：仓库卡片引用会自动关联建页，用户也可手动索引，不限于 Daily Papers 提交 | https://huggingface.co/api/papers/2004.15011 ；https://huggingface.co/docs/hub/paper-pages | 2026-09-26 |
| OpenAlex Topics 共 4/26/252/4,516 级，约 12% 作品无 topic；`/text` 端点 20–2,000 字符、1 rps、$0.01/次；分类器"top-1 训练准确率 0.4846"；E6 许可分布 | 确认，E6 复测计数完全一致；修正为最新：定价页已把 Text/Aboutness 标为 deprecated；准确率改用模型卡原词 "Train Accuracy" | https://help.openalex.org/data/topics ；https://help.openalex.org/api/tag-aboutness ；https://help.openalex.org/access/example-costs ；https://huggingface.co/OpenAlex/bert-base-multilingual-cased-finetuned-openalex-topic-classification-title-abstract ；https://api.openalex.org/works?filter=from_publication_date:2026-03-01,to_publication_date:2026-03-31,type:article&group_by=best_oa_location.license | 2026-09-26 |
| LLM API 价格（OpenAI gpt-5-nano/gpt-6-luna/gpt-5.4-nano/gpt-5.4-mini 及 Batch 限额；Gemini 2.5/3.1 Flash-Lite 与 3.8 Flash；DeepSeek deepseek-flash 峰谷价；阿里云 qwen3.8-flash 与 qwen-mt） | 确认，逐项对上，gpt-5-nano 的 Flex 价同 Batch | https://developers.openai.com/api/docs/pricing ；https://developers.openai.com/api/docs/guides/batch ；https://ai.google.dev/gemini-api/docs/pricing ；https://api-docs.deepseek.com/quick_start/pricing ；https://www.alibabacloud.com/help/en/model-studio/model-pricing | 2026-09-26 |
| Anthropic：Haiku 4.5 $1/$5、Sonnet 5 $2/$10，Batch 打 5 折；新分词器约多 30% token；Batch ≤10 万请求、多数 <1 小时完成、结果保留 29 天 | 确认；补：Sonnet 5 的 $2/$10 已由首发价转为标准价；成本表未计入分词器系数，Sonnet 5 上限约 +30% | https://platform.claude.com/docs/en/about-claude/pricing ；https://platform.claude.com/docs/en/build-with-claude/batch-processing | 2026-09-26 |
| DeepL API Growth €29.75/月 + €22/百万字符；Google Cloud Translation NMT $20/百万字符、LLM $10+$10；RunPod H100 SXM $3.49/小时；AIMultiple 测得 vLLM 0.11.0 为 12,553 tok/s | 确认 | https://www.deepl.com/en/pro-api ；https://cloud.google.com/translate/pricing ；https://www.runpod.io/pricing ；https://aimultiple.com/inference-engines | 2026-09-26 |
| 翻译模型：Qwen-MT 支持 92/31 种语言、有术语干预与翻译记忆；Hunyuan-MT-7B（2025-09-01 开源、33 种语言、WMT2025 中 31 个语向拿下 30 个第一）标为"仅限境内部署"；Seed-X 许可为 OpenMDW；NLLB 为 CC-BY-NC；COMET-22 为 Apache，CometKiwi/XCOMET 为 CC BY-NC-SA；MetricX-24 为 Apache | 确认；修正：许可排除的是欧盟/英国/韩国，并非"仅限境内"；补 HY-MT1.5 | https://www.alibabacloud.com/help/en/model-studio/machine-translation ；https://github.com/Tencent-Hunyuan/Hunyuan-MT ；https://arxiv.org/abs/2509.05209 ；https://huggingface.co/ByteDance-Seed/Seed-X-PPO-7B ；https://huggingface.co/Unbabel/XCOMET-XL | 2026-09-26 |
| CC 规则：演绎作品（Adapted Material）包含翻译；技术修改不产生演绎；须注明是否修改；ND 许可下未修改的摘录一般不构成演绎；商业 TDM 不挖 NC 材料；I4OA 称 Crossref 摘要转载需版权人明确许可 | 确认 | https://creativecommons.org/licenses/by/4.0/legalcode.en ；https://creativecommons.org/faq/ ；https://i4oa.org/ | 2026-09-26 |
| 中国法规：标识办法 2025-03-14 发布、2025-09-01 施行，第四、五条原文；深度合成规定第十七、十九条；暂行办法第二、十七条；GB 45438—2025 与办法同日实施 | 确认；补：GB 45438—2025 于 2025-02-28 发布，全文公开 | https://www.cac.gov.cn/2025-03/14/c_1743654684782215.htm ；https://www.cac.gov.cn/2022-12/11/c_1672221949354811.htm ；https://www.cac.gov.cn/2023-07/13/c_1690898327029107.htm ；https://openstd.samr.gov.cn/bzgk/std/newGbInfo?hcno=F32EA2A561F1886CD8D606513512D547 | 2026-09-26 |
| EU AI Act 第 50 条自 2026-08-02 适用；50(2) 对已上市系统宽限至 2026-12-02；50(4) 设人工审核豁免；另有自愿性行为准则 | 确认（欧盟委员会 FAQ 2026-07-24 更新） | https://digital-strategy.ec.europa.eu/en/faqs/transparency-obligations-under-article-50-ai-act | 2026-09-26 |
| PwC 于 2025-07 关停并重定向到 HF；称"README 仍写每日重生成但已冻结" | 修正：HF 数据集卡已明示"不再更新、2025-07-28 为最后快照"，仍写"每日重生成"的是 GitHub README；重定向实测为 302 到 /papers/trending | https://paperswithcode.com/ ；https://huggingface.co/datasets/pwc-archive/links-between-paper-and-code ；https://github.com/paperswithcode/paperswithcode-data | 2026-09-26 |
| Data Citation Corpus：CC0；来源为"DataCite/Crossref 关系、CZI SciBERT、Europe PMC"；规模各处口径不一 | 修正：Zenodo 最新 v4.1（2025-08-15）有 10,697,745 条，来源为 DataCite Event Data、CZI、ASAP、Europe PMC；CC0 确认 | https://zenodo.org/records/16901115 ；https://support.datacite.org/docs/data-citation-corpus | 2026-09-26 |
| 抽取与标签先例：SciRIFF（137K 条、54 任务、平均提升 70.6%、EMNLP 2025）；Paper2Poster（token 少 87%、每张 $0.005、NeurIPS 2025）；KeyBERT 为 MIT；YAKE 为 AGPL + 商业许可；MSC2020 为 CC BY-NC-SA；Science Data Lake 把 4,516 个 topic 映射到 13 个本体 | 确认 | https://arxiv.org/abs/2406.07835 ；https://arxiv.org/abs/2505.21497 ；https://github.com/MaartenGr/KeyBERT ；https://github.com/INESCTEC/yake ；https://msc2020.org/ ；https://arxiv.org/abs/2603.03126 | 2026-09-26 |
| 实测 E1–E8 的数字与 §2.9 合计列，以及 E7 的中文 0.675 token/字 | 确认：按原始文件逐项重算一致；E7 复算为 0.689 token/字符 | 本文子目录 `paper-understanding-and-card-content/`（json/tsv）；本地 `tiktoken` o200k 复算 | 2026-09-26 |
| S2 TLDR"公告后 1–2 天可得（85/98）" | 未核验：逐篇明细未存档；抽查 1 例相符 | https://export.arxiv.org/api/query?id_list=2609.30226 ；https://api.semanticscholar.org/graph/v1/paper/arXiv:2609.30226?fields=tldr | 2026-09-26 |
| HF `ai_summary`/`ai_keywords` 的再使用许可 | 未核验：HF 文档与 API 均未声明，维持 ⚠ | https://huggingface.co/docs/hub/paper-pages | 2026-09-26 |

**核验补充条目**（正文已标"核验补充"）：

1. 腾讯 HY-MT1.5-1.8B/7B（2025-12-30 开源），见 §2.3.2。
2. 全文 PDF 保版式翻译工具 PDFMathTranslate / BabelDOC，均为 AGPL-3.0，只适合私有层，见 §2.3.2 与 [R83]。
3. S2 API 响应中 `openAccessPdf.disclaimer` 的版权声明，见 Q4。
4. OpenAlex `/text` 已被标为 deprecated，新增 Q16，并同步到 §2.4.1、§2.8.1 与启示 12。
5. HHEM 榜 gpt-5.4-mini 的幻觉率 5.5%，见 §2.1.4。
6. 注释性补充：
   - Sonnet 5 的价格状态与分词器系数，见 §0、§2.6、启示 15；
   - MinerU 附加条款违约即自动终止；
   - GB 45438—2025 的发布日期与全文公开；
   - Yang 等调查的受访者是 PubMed 论文作者；
   - E3 按 OAI datestamp 取样，记录并非严格的"当日新投稿"；
   - E7 的复算结果。

**统计**：核验 32 行（每行含若干关联断言），其中确认 20、修正 10、删除 0、未核验 2。本轮没有发现编造的仓库、论文、公司或数字；修正项都属于措辞、过时或表述不准。影响最大的三项：v1 的 GROBID 未请求图坐标、OpenAlex `/text` 已被标为 deprecated、Hunyuan-MT 的许可地域并非"仅限境内"。
