---
title: 调研综合：v2 重新设计的输入与结论
status: draft
owner: opus5.5-survey
updated: 2026-09-26
---

# 调研综合：v2 重新设计的输入与结论

> **定位**：把 `docs/survey/` 下 14 篇经对抗式核验的调研合成为设计阶段（`docs/plan/v2/01`–`09`）可直接引用的输入。本文只做综合与取舍建议，不含实现代码，文中代码块均为**设计伪代码**。
> **证据口径**：本文**没有发出任何新的外部请求**。所有事实断言都来自下列 14 篇调研的正文或核验记录，其原始 URL 与核验日期（统一记为 2026-09-26，UTC）保存在各篇的"参考来源"与"核验记录"节；本文 §9 汇总最承重的一手来源。凡原文仍标"⚠ 未核验"或"◐"的事实，本文照样标注，不升级其可信度。"⚠ 推断"表示由已核验事实推理得到、未经实测。
> **引用写法**：`NS §3-5` 表示"natural-sciences 文档 §3（对 v2 设计的启示）第 5 条"；`RT §12-7`、`SR §3.1-9`、`RO §3.1-6` 同理，按各篇启示所在节号计；`MK I-4` 指 market 文档的启示编号；`CP HC-05` 指 compliance 文档 §3.1 的硬约束编号。代号与路径对照见 §1.1。为避免锚点随标题改动失效，链接只指向文件，章节号写在文字里。
> **与设计简报的关系**：主 agent 的 [v2 设计决策简报](../plan/v2/00-design-brief.md) 已引用本文。本文是它的证据层；§8 逐条核对两者，列出调研证据支持的细化与需要复核之处，**不改动简报**。

---

## 0. 结论速览

1. **调研规模与可信度**：14 篇共 13,066 行。对抗式核验共复核约 800 组承重断言，就地修正约 150–160 处（各篇计数口径不一），**删除 0 处**，14 篇都没有发现编造的仓库、论文、公司或数字（§1.3）。数字的时点均为 2026-09-26，快变事实（限速、计费、平台迁移、robots）须按季度复核。
2. **来源名录**：5 篇来源调研共登记 249 行，合并去重后得到 **187 行候选来源**（L1 129 行、L2 57 行，另有盗版源 1 个合并行）。建议状态：`v2-P0` 36、`v2-P1` 63、`v2-P2` 44、`metadata-only` 26、`link-only` 2、`user-import-only` 3、`excluded` 13（§3）。元数据主干是 Crossref 加 OpenAlex 快照，再叠加各学科的 L2（Europe PMC/PubMed、INSPIRE、zbMATH、RePEc、dblp 快照）。大多数期刊不需要写代码：登记 SourceSpec 与 venue 后由 `crossref_delegated` 承接。
3. **摘要缺口是跨学科的头号数据问题**。Crossref 摘要覆盖的学科中位数：心理 **0%**（21 刊中 13 刊低于 5%）、化学/材料 11%、CS 期刊 32%、数学 55%、经济 85%（AG §2.6）。按出版方看，Elsevier、APA、AOM、IEEE、UChicago、T&F 均为 0%。因此需要按出版方路由的摘要补齐链，给每条摘要记 `abstract_rights` 分级，卡片按权利降级展示，冷启动不依赖摘要。
4. **上游约束很硬，多用户规模必须"先收割、后联邦"**：
   - Crossref 公共池列表查询 1 次/秒、并发 1；
   - arXiv 全平台合计每 3 秒 1 次、单连接；
   - S2 的 key 只有 1 RPS；
   - OpenAlex 增量过滤需付费计划；
   - robots 全禁的主机很多：dblp、IOP、ScienceDirect、APA、NCBI eutils/ftp、api.osf.io，Springer 则只放行白名单。

   对策是本地底座、全局礼貌调度和一条统一的 robots ADR（AG §3、RT §0）。
5. **2025–2026 年漂移密集**：
   - openRxiv 启用新前缀 10.64898；
   - PMC 删除旧数据集并下线 OA Web Service；
   - ChemRxiv、RSC、Royal Society 迁平台；
   - SSRN 宣布关停商业线，且 ToU 禁止任何自动化；
   - dblp 的 robots 改为全禁；
   - Papers with Code 关停；
   - Crossref Event Data 退役；
   - OpenAlex 改为按美元计费。

   因此策略引擎与漂移探针必须是一等公民（NS §3-9、LS §3-11、SS §3-14）。
6. **检索与数据平台**：PostgreSQL 18 单栈可承载 T1 档（≤1,000 活跃用户、≤1,000 万 work）。检索用 BM25 加 `halfvec` HNSW，经 RRF 融合后以 cross-encoder 重排。路由用主题树挂 `route_stat` 做预算贪心。图数据留在 PG，已见集合用 Roaring 位图。多租户采用 Pool 模式加 RLS（RT §11–§12）。
7. **推荐**：三套独立学术推荐系统（arxiv-sanity-lite、S2 Research Feeds、Scholar Inbox）都收敛到"共享论文表示 + 每用户线性头"（SR §0-1）。社媒可以照搬的是机制：
   - Σ V·P̂ 价值模型；
   - 负反馈分两档；
   - DPP 与作者衰减；
   - 分级曝光；
   - 可见性过滤与排序分离；
   - 只认绑定曝光（impression）的反馈。

   不照搬的是亿级规模的模型（SM §2.14）。北极星指标是每周"有价值阅读数"，时长只作护栏。
8. **双向匹配**："读者↔论文"与"论文→读者"先做：每用户日预算加每篇曝光下限，硬配额用最小费用流。"研究者↔研究者"做成 opt-in，默认关闭（SR §3.1-14/16、CP HC-18）。
9. **前端**：采用三件套——今日分拣 Deck、双列瀑布流、详情 Sheet。手势用映射 A，带中性跳过，撤销免费且不限次。投影判定与弹簧参数已给出，另有有限批次与按钮/键盘等价操作。v2.0 做 Web-first PWA，原生端待留存验证后再做（UX §0、§3）。
10. **卡片内容**：LLM 费用不是瓶颈，卡片基础包每千篇 $0.06–3.44。真正的瓶颈是许可与忠实度：
    - arXiv 新记录中只有 39.5% 的许可允许展示图；
    - OpenAlex 新文章许可未知的占 38.4%；
    - 翻译属于演绎；
    - S2 TLDR 覆盖按学科在 0–98% 之间。

    对应做法是"共享派生"不变量、生成即校验的三道闸，以及法定 AI 标识（PU §0、§3）。
11. **竞品**：没有产品同时具备"学习型个性化 + 移动卡片滑动 + 经管 WP 覆盖 + 自带凭证取全文 + 可解释推荐"（MK §2.5）。但单项能力都不稀缺，机构凭证一键取全文也已有先例（R Discovery、Read by QxMD、Google Scholar）。差异只能落在这几项的组合、经管 WP 的新鲜度，以及多用户下的私域合规上。
12. **合规**：CP §3.1 的 28 条硬约束（HC-01…HC-28）直接决定架构，包括：
    - 共享层与私有层两域，数据只能单向下流；
    - 受限全文在用户侧取回；
    - 按篇的许可白名单；
    - 平台对每个上游只用一个身份，统一礼貌调度；
    - LLM 摘要治理与 AI 标识；
    - 推荐透明与用户控制；
    - UGC 分阶段开放；
    - 商用开关。

---

## 1. 调研范围与方法

### 1.1 范围与文档代号

| 代号 | 文档 | 主题 | 行数 | 主要服务的需求 |
|---|---|---|---:|---|
| NS | [sources/natural-sciences.md](sources/natural-sciences.md) | 理科（数学/物理/化学，材料与地学简述）出版商、预印本与平台 | 1,262 | ① |
| LS | [sources/life-sciences-psychology.md](sources/life-sciences-psychology.md) | 生命科学与心理学来源 | 1,151 | ① |
| SS | [sources/social-sciences-econ-fin-mgmt.md](sources/social-sciences-econ-fin-mgmt.md) | 经济/金融/商业/管理来源、工作论文、期刊名录 | 734 | ① |
| CS | [sources/cs-ai.md](sources/cs-ai.md) | 计算机与 AI 会议、期刊、预印本与社区信号 | 690 | ① |
| AG | [sources/aggregators-repositories.md](sources/aggregators-repositories.md) | 二级来源：仓库与聚合平台 | 1,303 | ①② |
| OSS | [oss/paper-acquisition-and-search-oss.md](oss/paper-acquisition-and-search-oss.md) | 论文获取、检索、学术搜索与推送类开源项目（197 项） | 888 | ②⑤ |
| RO | [oss/recommendation-oss.md](oss/recommendation-oss.md) | 推荐系统与学术推荐开源 | 587 | ③⑤ |
| MK | [market/startups-and-products.md](market/startups-and-products.md) | 学术发现与论文推荐的初创与产品（约 66 个） | 742 | ⑤④ |
| SM | [algorithms/social-media-recsys.md](algorithms/social-media-recsys.md) | 抖音/TikTok、小红书、X、快手、Meta 等社媒推荐算法 | 1,228 | ③ |
| SR | [algorithms/scholarly-recommendation-and-matching.md](algorithms/scholarly-recommendation-and-matching.md) | 学术推荐、兴趣建模与双向匹配 | 739 | ③ |
| RT | [algorithms/retrieval-routing-indexing.md](algorithms/retrieval-routing-indexing.md) | 多源检索、路由、索引结构与多用户数据平台 | 1,189 | ② |
| UX | [ux/card-feed-interaction.md](ux/card-feed-interaction.md) | 卡片流与滑动交互及实现技术 | 920 | ④ |
| PU | [algorithms/paper-understanding-and-card-content.md](algorithms/paper-understanding-and-card-content.md) | 论文理解与卡片内容生成（TL;DR、关键图、翻译、标签） | 810 | ④③ |
| CP | [compliance/multi-user-platform-compliance.md](compliance/multi-user-platform-compliance.md) | 多用户平台的许可、ToS 与监管边界 | 823 | 横切 |

用户五项需求：
- ① 来源名录；
- ② 检索与路由，以及多用户数据库；
- ③ 推荐与双向匹配；
- ④ 卡片流前端；
- ⑤ 开源项目与初创公司。

"横切"指多用户化带来的合规、隐私与内容治理，由 CP 承担，并贯穿其余各篇。

### 1.2 编排方式与 agent 分工

| 阶段 | 角色 | 分工与产出 | 约束 |
|---|---|---|---|
| 1 并行调研 | Survey（14 个 agent，每主题 1 个） | 各自产出一篇调研文档；必要时在同名子目录放附件（请求台账、实测 CSV/JSON、仓库指标 TSV） | 合规红线；每个事实带 URL 与核验日期；不编造；只写分配给自己的文件 |
| 2 对抗核验 | Verify（每篇 1 个独立 agent） | 默认怀疑，回到一手来源复核承重断言；就地修正并标"核验修正/核验补充"；文末写唯一的"核验记录"节 | 同上；遇挑战页即停，不绕过 |
| 3 综合 | Synthesize（本文） | 通读 14 篇原文；合并来源名录；给出分需求结论、冲突取舍、SI 设计输入与 HC 清单；撰写目录 README | 只写 `00-survey-synthesis.md` 与 `README.md`；不发外部请求 |

- 全部 subagent 使用 **Opus 5.5（max effort）**，文档 owner 统一为 `opus5.5-survey`。
- 三个阶段都在 2026-09-26（UTC）完成。
- 有 3 篇的核验中断过一次，随后由续核验复核首轮改动并合并完成，没有留下半截修改，见各篇核验记录：
  - market：核验记录注明因会话用量上限中断；
  - recommendation-oss：未写明中断原因；
  - social-media：未写明中断原因，其中 5 处修正来自中断前的首轮。

### 1.3 核验统计

口径分两类：
- 前 6 篇取自工作流的核验回执（`claims_checked` 等字段），并与文内统计对照过；
- 后 8 篇取自文内核验记录的自述，没有自述统计的由本文按核验表逐行复算，标"复算"。

"未核验/⚠"一列按各篇自己的口径计：有的数核验表中结论为未核验的行，有的数正文里仍保留 ⚠ 的条目，两种口径不可直接相加。

| 文档 | 核验断言（组/行） | 修正 | 未核验/仍 ⚠ | 删除 | 核验补充 | 口径与备注 |
|---|---:|---:|---:|---:|---:|---|
| NS | 63 | 13 | 9 | 0 | 5 | 回执；补 mdpi、osti_gov、cas_scifinder、eudml 与 HAL 注记 |
| LS | 54 | 13 | 2 | 0 | 4 | 回执；与文内统计一致；补 Royal Society、Hogrefe、PubTator3、iCite |
| SS | 66 | 7 | 3 | 0 | 11 | 回执；与文内统计一致（确认 56） |
| CS | 44 | 9 | 2 | 0 | 7 | 回执；与文内统计一致（确认 33） |
| AG | 61 | 7 | 6 | 0 | 3 | 回执；补 Open policy finder、OpenDOAR（⚠）、CiNii Research |
| OSS | 44 | 15 | 4（文内：未核验 1 条） | 0 | 6 | 回执；另批量复测 196 个仓库，star 偏差 ≤8、许可与归档状态零差异 |
| RO | 40 | 12 | 1 行（含 6 个仍 ⚠ 事项） | 0 | 6 | 复算（含续核验 9 行）；补 LensKit、River、bluesky feed-generator、GRID（限非商业）、Yambda-5B、daffidwilde/matching |
| MK | 99 | 17 | 6 | 0 | 16 | 复算（两轮）；产品覆盖约 54+6+6 个；Researcher App 改为"2024-11 月底已关停" |
| SM | 49 | 17 | 1（新标） | 0 | 10 | 文内自述；61 个 arXiv ID 与 17 个 DOI 全部解析 |
| SR | 74 | 10 | 2（叙述段） | 0 | 1 行（多项） | 复算 |
| RT | 59 | 9 行（计 13 处） | 3 | 0 | 12 | 文内自述（确认 47） |
| UX | 55 | 7 | 1 | 0 | 12 个新来源（R104–R115） | 文内自述；3 组原 ⚠ 核实为确认，3 组部分确认 |
| PU | 32 | 10 | 2 | 0 | 5（另有注释性补充） | 文内自述（确认 20） |
| CP | 57 | 10 | 2（1 处新标 + Unpaywall 许可维持 ⚠） | 0 | 12 | 文内自述；新增 DOAJ 与《网络数据安全管理条例》两个条目 |
| **合计** | **约 797** | **约 150–160** | — | **0** | — | 修正多为措辞、时效或口径问题；影响设计的修正见各篇核验记录首段 |

对设计影响最大的核验修正（跨篇摘录）：
1. Crossref 自 2025-12-01 起按请求类型分池：公共池单条 5/s、列表 1/s、并发 1；polite 池 10/s 与 3/s、并发 3；Metadata Plus 150/s（NS 核验、AG §0.1）。
2. Springer Nature 的 TDM API 另行收费；订阅机构免费的只有直接下载，限每秒 1 次（NS 核验）。
3. MSC2020 许可为 CC BY-NC-SA 4.0（NS 核验）。
4. S2 许可并未明确允许商用（AG 核验）。
5. NCBI 与 EBI 的 bulk 主机 robots 同样是 `Disallow: /`（AG 核验）。
6. bioRxiv 旧前缀的记录已整体转到 openRxiv 名下（LS 核验）。
7. Cell Press 属于混合 OA（LS 核验）。
8. Motion 的默认弹簧并不收敛，Deck 动效必须显式传参（UX 核验）。
9. DSA 第 27(3) 条的"界面直达"是硬性义务（UX 核验）。
10. v1 的 GROBID 调用没有请求图坐标（PU 核验）。
11. OpenAlex `/text` 端点已标 deprecated（PU、RT 核验）。
12. Researcher App 已于 2024-11 关停，而"机构凭证一键取全文"早有先例（MK 核验）。

### 1.4 本综合的方法

1. **通读原文**：逐篇读完 14 篇全文（含核验记录），不只看摘要。长文按每次不超过 200 行分段读取，逐篇写成结构化笔记（仅存会话临时目录，不入库）。
2. **名录抽取**：用脚本从 5 篇来源调研中抽出所有含 `source_id` 与"名称"列的名录表行，共 249 行：

   | 来源调研 | 行数 |
   |---|---:|
   | NS | 62（含排除表 5 行） |
   | LS | 42 |
   | SS | 54 |
   | CS | 46 |
   | AG | 45 |

3. **合并去重**：
   - **统一 id**：按 §3.1 的别名表统一 `source_id`，例如把 `springer_nature_link` 并入 `springer_link`，把 `wiley_vch`、`wiley_wol`、`wiley_online` 并入 `wiley`，把 `cell_press` 并入 `elsevier_sd`。
   - **不单列的行**：由母源承载的会议行（JPCS、AIP CP、EPJ WoC、ICM）不单列；仅作说明用的排除行也不单列。
   - **结果**：得到 187 行。
4. **优先级裁决**：同一来源在多篇中优先级不同的，取最高者，并在"出处与各篇原建议"列保留各篇原值。若给出最高优先级的那一篇同时注明"仅元数据"，则记为 `metadata-only（Px）`。裁决清单见 §3.4。
5. **冲突与取舍**：把各篇"启示"与"未决问题"按主题交叉比对，归纳成 §5 的张力表。
6. **一致性核对**：逐条对照设计简报的 B-xx、P-xx、Q1–Q7 与各子系统裁决，写入 §8。
7. **自检**：检查 front matter 四个字段、各表列数一致、相对链接可解析，并确认没有个人数据。

### 1.5 过程记录（可复现）

- **日期**：2026-09-26（UTC；本机时区已进入 09-27 凌晨）。
- **读取的文件**：
  - 14 篇调研原文，行数见 §1.1；
  - 设计简报 `docs/plan/v2/00-design-brief.md`（仅读取，未改动）；
  - 各篇附件目录的文件清单，用于 README 登记。
- **检索式与访问站点**：本综合**没有使用 WebSearch/WebFetch，也没有访问任何外部站点**。各事实的检索式、访问站点与日期见原文"过程记录"一节：

  | 文档 | 过程记录所在节 |
  |---|---|
  | NS | §1.4 |
  | LS | §1.3 |
  | SS | §1.3 |
  | CS | §1.3 |
  | AG | §1.3 |
  | OSS | §1.4 |
  | RO | §1.3 |
  | MK | §1.3 |
  | SM | §1.3 |
  | SR | §1.3 |
  | RT | §1.3 |
  | UX | §1.3 |
  | PU | §1.4 |
  | CP | §1.3 |

  各篇核验阶段的请求另记在其"核验记录"节。
- **本地脚本**（会话临时目录，不入库）：
  - 名录抽取脚本：解析 Markdown 表格时对反引号内的 `|` 不切分；
  - 合并与统计脚本：定义别名表与学科代码，输出 §3.2 各表与 §3.3 统计；
  - 核验表逐行复算脚本：用于 §1.3 中标"复算"的各行。
- **调研阶段的请求纪律偏差**（各篇已自行披露，本文汇总，作为 SI-38 的依据）：
  - NS 事后发现有 2 次请求落在 robots 禁区：IOP RSS 与 PubChem PUG-REST（NS §1.4.5）；
  - AG 有 9 次请求发生在读取 robots 之前；ftp.ncbi 与 ftp.ebi 的 robots 为全禁（AG §1.3.4）；
  - SS 读到 `rss.sciencedirect.com` 的 `Disallow: /` 之后仍发出 1 次请求，另有 2 次请求发往 `api.osf.io`（见 SS 过程记录）；
  - CS 取了 ICORE 门户，而其 robots 禁止 Claude 类 agent；另误发 1 次 `icml.cc/static` 请求（CS §4 第 13 条）。

  这些偏差说明，"先读 robots 再请求"必须由 HTTP 层强制执行，不能依赖调用方自觉。

### 1.6 局限

- **非全量统计**：各篇的实测都是时点小样本，例如 Crossref 覆盖率、S2 TLDR 覆盖、arXiv 许可分布。本文的合并统计只反映调研登记了什么，不等于全量事实。
- **出口 IP 影响**：多篇的 WAF 与挑战结论来自同一个经代理的出口，在校园网或用户本地网络下可能不同（NS 核验、LS §4、SS §4）。
- **仍需一手确认的事项**：法律边界（LQ-01…LQ-18）与部分条款页只有二手或摘要级证据。这些在 §7 列为待确认，设计阶段不得把它们当作已确认的事实写入 ADR。
- **名录列宽取舍**：合并后的名录为了控制列宽，对原文的通道描述做了压缩。实现某个 connector 前，必须回到对应来源调研的逐源详述与名录原行。

---

## 2. 按五项需求的综合结论

### 2.1 ① 自定义来源与支持名录

**关键事实**

| 事实 | 证据 |
|---|---|
| Crossref 几乎能按 ISSN 枚举全部期刊 venue：理科 115 刊（含论文集系列）、经管 107 个 ISSN、聚合篇 204 刊都已实测 | NS §2.8；SS §2.8；AG §2.6 |
| 摘要覆盖（Crossref current 中位数）：数学 55%、物理 54%、化学/材料 11%、生物 51%、心理 0%、经济 85%、金融 76%、商学 78%、管理 64%、CS 期刊 32% | AG §2.6 |
| 分池限速：`/journals/{issn}/works` 与 `/works/{doi}` 走单条池（5/s），`/works?filter` 与 `query.*` 走列表池（1/s），公共池并发 1；`from-index-date` 会把结果放大约 100 倍 | AG §0.1、§2.2.1 |
| arXiv：新 OAI 支持 `group:archive:category` 三级 set；v1 推导的物理 set（如 `cond-mat`）已返回 badArgument；ToU 规定全部机器合计每 3 秒 1 次、单连接；2026-02 起 429 频发，另有伪 200 "Rate exceeded." 的报告；元数据（含摘要）CC0 | NS §2.3.5；CS §2.1.1；CP HC-06 |
| 生命科学骨干是 Europe PMC、PubMed、PMC。PMC 只允许 S3、OAI、E-utilities、BioC 四个自动化通道，OA Web Service 已于 2026-08-25 退役。bioRxiv/medRxiv 由 openRxiv 接管，新前缀 10.64898；`/details` 当日返回 200 空体 | LS §2.2.1、§2.3.2 |
| 经管：SSRN 商业线 2026-12-31 关停，ToU 禁止任何自动化查询；NBER 仍有 18 个月门控；UTD24 中 21/24 刊在 Atypon 或 Silverchair；AOM、Elsevier、UChicago 的 Crossref 摘要为 0；ECB 的 DOI 不在 Crossref，只能走 RSS | SS §2.1–§2.4 |
| CS：dblp 三个主机的 robots 都是 `Disallow: /`，只能用 DROPS 月度 CC0 快照或 SPARQL。OpenReview 的 API 需要账号。ACM 自 2026-01 起全库 OA，但禁止脚本下载。IEEE 在 Crossref 零摘要，DOI 滞后 2–6 个月。PwC 已关停 | CS §0.1、§2.1、§2.6.5 |
| robots/WAF：IOP、ScienceDirect、APA 对 `*` 全禁；Springer 全禁后另设白名单；ACS、AMS、Cambridge、SPIE、Preprints.org 连 robots.txt 都被 WAF 拦截或挑战；Atypon 族禁止 `/rss` 与 `/action` | NS §2.5；LS §2.9；SS §2.2 |
| 合规的结构化通道：APS Harvest、Springer Nature API、INSPIRE、zbMATH、SCOAP3、ADS、eLife API、PLOS API、OSF API、OpenReview API、ACL Anthology 包、EPMC REST、PMC S3 | NS §3-4；LS §3-13；CS §3-3 |
| 需每用户自有凭证的通道：Elsevier key、Wiley TDM token、SN api_key、ADS token、APS Harvest 授权；IEEE API 只限机构内使用，平台层不用；OpenReview API 需要账号，ToS 规定一人一号，平台服务账号须先取得书面确认 | NS §3-7；LS §3-4；CS §3-9；CP HC-04/HC-27 |
| 合并名录共 187 行，状态分布与学科覆盖见 §3 | 本文 §3 |

**推荐方案**

1. **总体结构**：
   - 采用两层来源模型：L1 为 publisher、preprint、journal_platform、conference_platform；L2 为 repository、aggregator。
   - Source 与 Venue 分离；Venue 用多键归一，并带演化边。
   - SourceSpec v2 声明三个通道：metadata、latest、fulltext。每个通道带方法、端点、认证、限速、robots/ToS 结论、许可策略和证据（url 与 verified_at）。

   依据：NS §3-1、SS §3-9、CS §3-1/§3-14，与简报 §6.1 一致。
2. **元数据**：
   - 期刊和带 DOI 的 WP 以 Crossref 按 ISSN 枚举为主干，所有历史 ISSN 合并查询；
   - 生命科学以 Europe PMC 与 PubMed 为主干；
   - 预印本走原生通道：arXiv OAI 类目级 set、OSF、openRxiv 经 Crossref 兜底；
   - 学科库作结构化主干：INSPIRE、zbMATH、RePEc bulk、dblp 快照；
   - 本地底座由 OpenAlex 季度快照与 Crossref 年度文件构成，只按全体用户兴趣的并集导入子集。
3. **最新论文**：
   - 默认走 Crossref `from-created-date`（带重叠窗口与标识符去重）、EPMC `FIRST_IDATE`、PubMed EDAT 与 arXiv OAI；
   - `from-index-date` 只用于补漏，因为它会把结果放大约 100 倍；
   - feed 只采用 robots 明确允许的，且只当新鲜度信号。
4. **全文**：分三档——
   - OA 且许可可共享的：进入平台共享层；
   - 订阅内容：每用户凭证、在用户侧取回、私有存放、不预取；
   - ToU 或 robots 禁止的（SSRN、MPRA OAI、OKR OAI 等）：只外链。
5. **合规元数据与策略引擎**：
   - 名录 schema 带 `tos_automation`、`ai_bot_sensitivity`、`crawl_delay_s`、`api_quota`、`tdmrep` 与 `verified_at`；
   - 策略引擎对五类通道的信号取最严结论；
   - 漂移探针定期比对 robots/ToS 哈希、挑战率、配额头、DOI 前缀、member、publisher，以及"200 空体"；
   - 发现漂移即自动降级为"仅元数据"。
6. **只为有官方 API 或协议通道的站点写代码**。新增的官方 API 型 connector 包括：
   - `aps_harvest`
   - `springer_nature_api`
   - `inspire_hep`
   - `zbmath_open`
   - `nasa_ads_scix`
   - `scoap3`
   - `numdam_oai`
   - `europe_pmc`
   - `pubmed`
   - `openreview`（v2 版）
   - `acl_anthology`（包形态）

   长尾由平台族基类承接：Atypon、Silverchair、OJS、DSpace、EPrints、InvenioRDM、HighWire。

**备选与取舍**

- **A. 以 OpenAlex 为单一元数据主干**：接入最省事，但有以下问题，因此 OpenAlex 只作覆盖面主干，不作权威源（AG §2.2.2、§3-1）：
  - 摘要只提供倒排索引；
  - 增量过滤需付费；
  - 会议实体归一化差，NeurIPS 会议实体下只有 4,177 条 works、ICLR 只有 757 条；
  - OA 判定有误，例如 JMLR 的 OA 比例被判为 1%、PVLDB 为 18%；
  - host 字段不能用于路由，Publ. Math. IHÉS 就是反例。
- **B. 沿用 v1 的"每平台一个抓取 adapter"**：在 WAF、robots 与 ToS 双重收紧下不可持续，而且与 HC-26 冲突。只对有官方通道的站点保留。
- **C. 付费档作为规模化杠杆**：
  - Crossref Metadata Plus（150/s）；
  - OpenAlex Member（$5,000/年）或 Member+（$10,000/年，含日同步与 `from_updated_date`）。

  简报 Q3 的默认是不买，建议在路线图里把它列为规模化触发条件（AG §4 Q6）。

### 2.2 ② 检索、路由与多用户数据库

**关键事实**

| 事实 | 证据 |
|---|---|
| Crossref、OpenAlex、S2 都不返回 ETag 或 Last-Modified，无法做 HTTP 条件缓存 | RT §0-1、§2.2 |
| OpenAlex 计费：单实体免费，列表 $0.10/千次，搜索 $1/千次。semantic search 用 GTE-Large，每次最多返回 50 条，1 req/s，只看前 2,000 字符。季度快照 JSONL 约 745 GB，另有删除日志 | RT §2.2；AG §2.2.2 |
| LitSearch 上，最好的稠密检索比 BM25 的 recall@5 高 24.8 个百分点；商业搜索落后 32 个百分点 | RT §4.1 |
| RRF 的常用 k=60，但 Qdrant 默认 k=2。Elasticsearch 的 RRF 只在 Enterprise 版提供。SPLADE 官方权重为 NC 许可，有 Apache 替代品 | RT §4.2、§4.5 |
| pgvector 0.8 支持 iterative scan；`halfvec` 最多 4,000 维；1,000 万条 1024 维 halfvec 向量约 20.5 GB，连同 HNSW 的索引粗估约 23 GB（常驻约 20–25 GB，⚠ 粗估，以实测为准） | RT §5.3 |
| 不宜引入的图数据库：Kùzu 已归档（2025-10），FalkorDB 为 SSPL，Memgraph 为 BSL | RT §0-4；OSS §3-14 |
| OpenAlex Topics 的 4,516 个 topic 可对齐到 13 个本体（Science Data Lake：阈值 ≥0.85 时 F1 0.77）；约 12% 的 work 没有 topic；`/text` 已标 deprecated | RT §6.2；SR §2.11 |
| 已见集合用 Roaring 位图：每用户每年约 150 KB，1 万用户约 1.5 GB | RT §7.2 |
| 事件量估算：1 万 DAU × 每人 200 张卡 × 3 个事件 ≈ 每日 600 万行（每年约 22 亿），T1 后期需要 ClickHouse | RT §10.4 |
| RLS 注意事项：应用角色不是表 owner、不带 BYPASSRLS，用 `SET LOCAL`；PgBouncer 的事务池不支持会话级 SET 与 LISTEN | RT §10.3 |
| v1 本地库只有 179 篇，迁移成本很低 | RT §10.7 |
| 开源参照：只有 findpapers 实现了完整的查询编译（AST → 各源 builder → DNF 并集），但做不到跨请求 AND/NOT；只有 Asta PaperFinder 做了显式意图路由 | OSS §2.3.1、§2.12 |

**推荐方案**（与简报 §6.2–6.3 一致，以下补充证据要点）

1. **先收割、后联邦**：订阅、最新论文与卡片流只读本地语料；即席查询本地优先，覆盖不足时才联邦。缓存用应用层 TTL，TTL 取 min(24h, 0.1/λ̂)，并按源分配美元预算桶。依据 RT §9。
2. **SCD 与路由**：
   - SCD（查询能力、成本模型、礼貌参数、许可）是路由器与健全放宽的唯一输入。
   - TSRG 在主题节点上挂 `route_stat`（覆盖、滞后、λ），按"边际召回/成本"做预算贪心选源。覆盖函数单调次模：只有基数约束时，贪心有 1−1/e 近似；带成本的预算版本要加"单项最优"兜底或部分枚举，才有常数近似。候选源通常少于 20 个，精确枚举可行（RT 标为判断）。
   - 统计来源：OpenAlex group_by（每周约 9,000 次调用，约 $0.90），或离线跑免费快照。
   - 用 Thompson sampling 做源探索，日志足够后换 GBDT pairwise 路由器。

   依据 RT §3.5。
3. **Query AST（LOOKUP/SEARCH/SIMILAR/LATEST/EXPAND）**：
   - 解析顺序：规则快路径 → LLM 受约束 JSON（可选，不进热路径）→ 实体链接（只链到库内 ID）→ 可编辑的筛选条；
   - 同时投机执行本地首屏；
   - 健全放宽：先化为 NNF，再按极性替换，本地做残差过滤，并用属性测试保证 relaxed ⊇ original。

   依据 RT §3.5.3、§4.3。
4. **本地混合检索**：
   - 流程：BM25 与 pgvector `halfvec` HNSW 并行召回，RRF 融合，cross-encoder 重排 top-100；
   - BM25 扩展默认用 pg_textsearch（PostgreSQL 许可，只支持 PG 17/18）；ParadeDB 为 AGPL，只作可选；
   - 组合过滤按选择率规划：候选集 ≤约 2 万时精确算距离，否则走 HNSW 加 iterative scan。

   依据 RT §4.4、§5.4、§6.3。
5. **规模分档**：
   - T1：单 PG 18（64–128 GB 内存加 NVMe）；
   - 触发升级的条件：HNSW 放不进内存、检索 p95 >300 ms，或建索引时间超出夜间窗口；
   - 升级路径：pgvectorscale（StreamingDiskANN 加标签过滤），再往上是 Qdrant、Vespa 或 OpenSearch，PG 始终是真值源。

   依据 RT §5.4、§11。
6. **图与去重**：
   - 图存为 PG 邻接表，在线查询 ≤2 跳；夜间导出 CSR 做 PageRank、共被引等批算。
   - 去重先用标识符图 union-find 物化 `cluster_id`，保留回滚日志；再用 MinHash-LSH 加 Splink 生成候审对。弱信号不自动合并（D-007），WP 与其发表版只建 `preprint_of` 边，不合并。

   依据 RT §6.4、§7。
7. **多租户数据平台**：
   - `corpus` 共享只读；
   - `usr` 全表 RLS；
   - `evt` 只追加、按月分区，客户端生成 event_id 保证幂等；
   - `ops` 放队列、健康状态、配额账本与策略快照；
   - 任务队列用 procrastinate（MIT），pgqueuer 为备选；arq 处于维护模式，不用；
   - 每用户凭证库沿用 v1 D-023，扩为按用户封装。

   依据 RT §10、OSS §3-5/§3-6。
8. **新鲜度与稳定性**：
   - 用户频道编译为带引用计数的 WatchKey，同键只收割一次；
   - 日历型源按发布窗口轮询；连续型源用 Gamma-Poisson 估计 λ，在礼貌约束下做注水分配；
   - Percolator 把新论文写入各用户的 FeedInbox；
   - 稳定性四件套：令牌桶、重试预算（≤3 次/请求，≤10%）、AIMD（上限为书面限额）、按"源 × 端点"熔断；
   - 舱壁分三道：交互、收割、enrich；
   - 不对同一第三方主机发对冲请求。

   依据 RT §8、§9。

**备选与取舍**

- **A. 一开始就上独立检索集群**（OpenSearch、Vespa 或 Qdrant）：换来扩展余量，代价是双写与运维，T1 不划算。保留 outbox/CDC 接口，等触发条件出现再升级。
- **B. Meilisearch 社区版或 Typesense**：Typesense 是 GPL；Meilisearch 的企业版为 BUSL；两者的租户 token 只能当只读视图（OSS §2.10.6）。
- **C. 独立图数据库**：Neo4j 为 GPL，Kùzu 已归档，都不采用。需要 Cypher 时可评估 Apache AGE。
- **D. 特征存储（Feast）**：暂缓，先用 PG 物化表，必要时加 Valkey（BSD）。

### 2.3 ③ 推荐算法与双向匹配

**关键事实**

| 事实 | 证据 |
|---|---|
| 三套独立学术推荐系统做法趋同，都是共享表示加每用户线性模型：arxiv-sanity-lite 用 LinearSVC，S2 Research Feeds 用两个线性 SVM 求平均，Scholar Inbox 用逻辑回归 | SR §0-1、§2.5 |
| Scholar Inbox 配方：GTE-large 经 PCA 降到 256 维；每用户一个 LR（C=0.1、V=0.8、S=5.0）；负例为显式不喜欢加 5k 随机未见；每次评分后重训。规模：23k 注册、8k 月活（35%）、80 万显式评分。数据集为 CC BY-NC-ND 4.0 | RO §2.6；MK 核验 |
| 表示没有绝对赢家。Scholar Inbox 评测中 TF-IDF 10k 维的 nDCG 最高（88.67），GTE-large 的 AUC 最高（86.75，SPECTER2 为 86.36）。SciDocs 推荐任务上各方法差距很小（随机 51.3，最好 54.3）。主要杠杆在用户建模与反馈 | SR §0-2、§2.2；RO §3.1-6 |
| 许可陷阱：jina v3/v5、NV-Embed-v2 为 CC-BY-NC；jina v4 用 Qwen Research 许可。Apache/MIT 可选的有 Qwen3-Embedding、SPECTER2（HF `specter2_base` 为 Apache-2.0）、SciNCL、BGE-M3、gte-large、e5、nomic | SR §0-4；RT §4.5 |
| X 2026 开源（xai-org/x-algorithm，Apache-2.0，commit 4c5cfe8）：ValueModel 为 Σw·P，权重举例 Favorite 0.5、Reply 5、ShareViaCopyLink 20、NotInterested −43.2、Report −234；另有负分偏移、作者多样性衰减、DPP 重排（测试用 θ=0.5）、新作者冷启动加权、候选隔离，且只有曝光在首页时间线上的行为才计入 | RO §2.2.2；SM §2.4.2 |
| 社媒传说的核实：抖音"八级流量池"与小红书"CES 评分"都是 E 级民间说法，不采信。官方可证实的是：综合预测行为概率 × 行为价值权重；北极星为"用户长期价值"；小红书一半流量给粉丝不足 1k 的作者，并用指数遗忘 | SM §0、§2.1.4、§2.3.4 |
| 工业界趋势是生成式、端到端（OneRec、HSTU、Phoenix），需要数十亿级交互。1–1 万用户规模不适用；可迁移的只有语义 ID、不用每用户 ID 嵌入、候选隔离三点 | SM §0-5；RO §2.3 |
| CF 在学术场景偏弱（Beel 综述：CF 18%、CBF 55%），CiteULike 已于 2019 年关闭。共被引依赖未来的引用，对新论文不利；文献耦合可以即时使用 | SR §0-6/7、§2.3–2.4 |
| LLM 放在离线或近线：每用户每日对 30 篇做 listwise 重排，成本 $0.0006（gpt-5-nano）到 $0.029（Sonnet 5）；论文侧预处理与用户数无关，每月 $30–1,121；每张卡都生成解释最贵 | SR §2.6.6 |
| 双向匹配工具链：openreview-expertise（MIT）算亲和度，openreview-matcher 做约束分配（仓库无 LICENSE，只能按论文自行实现）；RECON 的 top-10 成功率从 23% 提到 42%；Hinge 用 Gale–Shapley；SimClusters 解决"论文找读者" | SR §2.10；SM §0-6；RO §2.9 |

**推荐方案**（与简报 §6.4 一致）

1. **R0（≤1k 活跃用户，纯 CPU）**：
   - 表示层：共享论文表示为 256 维稠密向量加 TF-IDF；
   - 用户层：每用户一个 LR，每次反馈即时更新；显式负例与随机负例分开加权；
   - 打分：个人分 + 词法分 + 主题亲和 + 新鲜度，再减去已见或重复惩罚；
   - 重排与出卡：作者多样性衰减，每日预算，解释用模板化理由码；
   - 从第一天起记录 propensity。

   依据 SR §3.2、RO §3.2 的 S1。
2. **ValueModel Σ V_a·P̂(a)**：
   - V 做成版本化配置，用等贡献法初始化；
   - "导出引用"与"收藏"的正向价值最高，类比 X 的 ShareViaCopyLink 20；
   - 左滑是弱负反馈；"不感兴趣 + 原因"是强负反馈，两者至少差一个数量级，强负反馈在当次会话内即生效；
   - 净负分的候选一律排在所有非负候选之后。

   依据 SM §3-1/2/3。
3. **召回至少 5 路**，每条候选带来源归因：
   - 显式关注：频道、作者、venue；
   - 长期与短期兴趣的多质心 ANN；
   - 文献耦合，以及"引用了我的库"；
   - 兴趣树邻近节点（用于探索）；
   - 开放热度信号（HF upvotes 等，逐源核验条款）；
   - 新论文分级曝光池。

   依据 RO §3.1-2、SR §3.1-6、MK I-7。
4. **重排与探索**：
   - 作者衰减、venue/主题配额、DPP（θ 从 0.5 起调）；
   - 预留 10–20% 探索槽，并在卡片上标注"探索"；
   - 新论文与新作者用贝叶斯分级曝光：内容先验加 Thompson sampling，按后验下界逐级扩大受众，并设曝光下限。

   依据 SM §3-8、§3-10。
5. **冷启动**：兴趣树勾选 → 导入种子 → 10–20 张主动学习校准卡（至少 5 正 3 负）。种子来源：
   - ORCID 本人作品；
   - Zotero、BibTeX、DOI；
   - Google Scholar 只接受用户手动导出后上传；
   - dblp 走快照。

   依据 SR §2.7、MK I-4。
6. **双向匹配分三层**：
   - ① 读者↔论文：受众适配加供给侧约束的重排；
   - ② 论文→读者：Percolator 在"每用户日预算 + 每篇曝光下限"约束下分配。R0/R1 阶段用批量矩阵乘，规模约 1 万用户 × 5 个质心 × 2.5 万篇新论文 × 256 维，CPU 上以秒到分钟计；硬配额场景用 ortools 最小费用流；
   - ③ 研究者↔研究者：互惠分取调和平均，加容量与公平约束，只有双方都选择加入才启用，且永不暴露阅读轨迹。

   依据 SR §2.10、§3.1-14/16。
7. **隐私与公共评价**：
   - 社会证明至少需要 k 个不同用户；
   - 私有库中的共现不进入协同信号；
   - 解释不得引用他人的私有行为；
   - 公开评分用 Wilson 下界并设最少评分数；
   - 作者对自己论文的互动不计入。

   依据 RO §3.1-8、SM §3-12/13/14。
8. **分阶段栈 R0 → R1 → R2**：
   - R1：GBDT/LTR、item-kNN 或 EASE、Thompson/LinUCB、DPP；
   - R2：序列多行为模型，只在达到升级阈值后启用；
   - 1 万用户以内不引入生成式端到端推荐，也不引入在线训练集群。

**备选与取舍**

- **Gorse**（Apache-2.0，Go 实现，带多路召回与 LLM 重排）：可作 R1 阶段的引擎候选。代价是多出一份数据副本，而且"私有反馈隔离"能否保证仍 ⚠ 未核验（RO §2.4）。
- **Vowpal Wabbit**（cb_explore_adf 加 IPS/DR 离线评估）：可用于 R1 的探索层，版本须 ≥9.11.6。Azure Personalizer 已于 2026-08-25 退役（RO 核验）。
- **表示模型**：gte-large（MIT，与 OpenAlex semantic 同一向量空间）与 SPECTER2（科学专用）二选一做 A/B；中文与多语侧用 Qwen3-Embedding-0.6B（Apache-2.0）。按许可、跨学科覆盖和成本定型，在 V1 里程碑做分学科小样本评测（简报 Q7）。

### 2.4 ④ 卡片流前端（含卡片内容）

**关键事实**

| 事实 | 证据 |
|---|---|
| 五种信息流形态中，Tinder 式决策卡产生的标签最干净，但有"拒绝心态"：三项研究中，从第一个到最后一个选项，接受概率平均下降 27%。Tinder 把撤销做成付费权益 | UX §2.1；R15 为 Pronk & Denissen |
| 论文版滑动产品都只是原型或小型 App：Papr、ArxivTok、PaperCrush、ZiNote 采用度极低；UW PaperTok 的用户担心"AI 味"。HN 上对 Papel 的反馈：AI 必须可关、首屏零摩擦、学界对"TikTok"这个名字反感 | MK §2.2.H；UX §2.2.4 |
| 判定参数：投影 proj = d + v·0.1 s；横向阈值 0.35W、纵向 0.2H、逃逸速度 800 pt/s。弹簧：回弹 500/36（ζ≈0.80）、次卡升位 600/49（ζ=1.0）、撤销 400/32。Motion 默认弹簧 ζ=0.5，会过冲 16%，必须显式传参 | UX §2.3.3–2.3.5、§2.9.4 |
| 平台限制：iOS WebKit 默认把页面渲染限在约 60 fps；Safari 不支持 Vibration API；View Transitions 支持率约 91.8%；React 19.3 的 `<ViewTransition>` 于 2026-09-09 转为稳定 | UX §2.4.2、§2.3.6、§2.7.1 |
| 合规要求：why-this、标签可删、一键关闭个性化，依据 CAC《算法推荐管理规定》第 16/17 条与 DSA 第 27/38 条。DSA 27(3) 要求能从信息流界面直达这些设置 | UX §2.6.5；CP HC-13 |
| S2 TLDR 覆盖按学科差异极大：cs.CL/cs.CV 92–98%，hep-th 0%；不带 CS/医学/生物学科标签的样本 334 篇中只有 1 篇有 TLDR。arXiv HTML 在近期可得 88.6%；arXiv 新记录中许可允许展示图的（CC BY/BY-SA/CC0）仅 39.5% | PU §0、§2.9 |
| LLM 生成成本：卡片基础包每千篇 $0.06–3.44；最大场景每月 $26–806（Sonnet 5 计入新分词器后约 $1,050，⚠ 推断）。幻觉率：gpt-5.4-nano 3.1%、gemini-2.5-flash-lite 3.3%，推理型模型为 18–23%。科学摘要的过度概括率 26–73% | PU §2.6、§2.1.4 |
| AI 标识是法定义务：中国《人工智能生成合成内容标识办法》自 2025-09-01 施行，要求显式加隐式标识；EU AI Act 第 50 条自 2026-08-02 适用 | PU §2.8.3；CP HC-11/HC-12 |

**推荐方案**（与简报 §6.5–6.6 一致）

1. **信息架构三件套**：
   - 今日分拣 Deck 为默认首页，每批数量有限（20–30 张，⚠ 待 Demo 验证），看完有明确的结束态；
   - 双列瀑布流用于"探索"与"收藏库"；
   - 详情用底部 Sheet，停靠在 60% 与 95% 两档；
   - 纯纵向沉浸流只作实验入口。

   依据 UX §2.1.3、§3-1、§3-7。
2. **手势映射 A**：
   - → 想读
   - ← 不感兴趣
   - ↑ 中性下一篇
   - ↓ 撤回上一张
   - 单击进详情
   - 长按 ≥400 ms 出原因菜单
   - Deck 上不绑定双击

   每个手势都有按钮与键盘等价操作（WCAG 2.2 SC 2.5.1/2.5.7/2.1.1）；撤销以追加事件实现，免费且不限次。依据 UX §2.9.2–2.9.3。
3. **动效与性能**：
   - 采用上表参数，Demo 带调参面板；
   - DOM 中只保留 3 张卡，只动画 transform 与 opacity；
   - 指标：INP p75 ≤200 ms，提交到下一张可交互 ≤100 ms；
   - 低端设备按 5 级阶梯降级；
   - Reduce Motion 时全部改为 150 ms 淡入淡出。

   依据 UX §2.4、§3-17/18。
4. **卡片字段**：
   - P0 共 6 项：标题、AI TL;DR、venue·年份、评审状态、OA 四态、why-this；
   - AI TL;DR 须标注、可关，且永不替代作者摘要；
   - OA 四态中"用你的凭证"一态按用户私有计算；
   - 关键图只对许可闸放行的论文展示，否则用排版封面，排版封面是一等公民；
   - 分拣卡不显示社交计数。

   依据 UX §2.6.2、§3-11/13/14。
5. **内容生成分层**：
   - T0：直接取源；
   - T1：候选论文批量生成 A 包；
   - T2：打开详情时按需生成中文摘要、关键图、结构化要点；
   - T3：私有全文由本地或私有模型生成，只进私有缓存。

   缓存键包含源文本哈希、源版本、模型、prompt 版本与策略版本。依据 PU §2.6.7、§3-1/§3-17。
6. **"共享派生"不变量加三道闸**：
   - 共享卡上的 AI 内容只能由可共享来源派生；
   - 三道闸为规则闸、NLI 闸（MiniCheck-FT5 或 HHEM-2.1-Open）、抽样 LLM 裁判加人工；
   - 不过闸就降级为原文首句；
   - 另建 600 篇双语黄金集。

   依据 PU §3-2/§3-5/§3-21、CP HC-11。
7. **按学科定卡片模板**：
   - CS/生医：全功能；
   - 数学与物理：LaTeX 渲染加排版封面；
   - 社科与心理期刊：在法务结论出来之前，只放元数据与受控标签，再加一个"为我生成中文速读"按钮（私有、即时生成）。

   依据 PU §2.9、§3-23。
8. **技术与接口**：
   - v2.0 做 PWA：React 19.3、Motion 13、Base UI Drawer、scroll-snap、TanStack Virtual 或 masonic；
   - v2.x 待留存验证后再做原生：Expo SDK 57、Reanimated 4、RNGH 3；
   - 事件契约先行：impression、swipe_decision、save、not_interested、undo、rate、open_fulltext、batch_end 等，统一携带 user/paper/session/surface/position/ts 与 reason。

   依据 UX §2.10、§2.9.6。

**备选与取舍**

- **映射 B（纯 Tinder，↑ 为收藏）与映射 C（纯纵向）**：映射 B 与国内"上滑下一条"的肌肉记忆冲突，可能造成误收藏（⚠ 推断）。两者都放进 Demo 做 A/B。
- **列表模式**：保留"列表 vs 卡片"双模式 A/B，桌面端默认侧栏详情，以对冲"滑动形态未经验证"的风险（MK §4.2、I-18）。
- **Capacitor 8 壳**：可作从 PWA 到原生的过渡，但不作主线（UX §2.10）。

### 2.5 ⑤ 开源与初创

- **开源**：OSS 篇调研 197 个项目，RO 篇另有约 90 个推荐与表示项目。没有一个开源项目实现"多用户 + 每用户凭证 + 合规分层共享"（OSS §2.12-f、§2.13）。滑动与卡片类开源项目全部低于 100 star。可直接复用的集中在基础设施、表示与评测，分级清单见 §4.4。
- **市场**：分为 8 层（MK §2.1）。
  - 数据层已商品化：S2 有 225M 论文（2025-05 口径），Elicit 有 138M+。
  - 可验证的强基线都很简单（MK I-5）。
  - 付费转化率低：Consensus 约 3%（MK §2.6）。
  - 关停与转向风险真实存在：Microsoft Academic、Meta（CZI）、PwC、Researcher App（MK §2.7）。
  - 定位与商业模式建议见 §4.3。

---
## 3. 来源总览：候选来源总表（草案）

> 本表把 NS、LS、SS、CS、AG 五篇的名录合并去重，作为支持名录 `docs/catalog/source-directory.md`（简报 §1 与 §6.1 规划，由主 agent 在设计阶段创建，本文撰写时尚不存在）和机读注册表 `registry/sources/*.yaml` 的**种子**。本表不替代原文逐源详述：实现任何 connector 前，必须回到对应来源调研，复核端点、限速与条款。

### 3.1 合并口径

**id 统一（别名表）**

| 统一 `source_id` | 合并的原 id（出处） | 说明 |
|---|---|---|
| `arxiv` | `arxiv`（NS、CS）、`arxiv_qbio`（LS）、`arxiv_econ_qfin`（SS） | q-bio、econ、q-fin 只是类目级 VenueSpec，不单列为来源 |
| `s2` | `s2`（AG）、`semantic_scholar`（CS） | 沿用 v1 id |
| `springer_link` | `springer_nature_link`（NS）、`springer_link`（LS、SS、CS） | NS 建议新增官方 API 型 connector `springer_nature_api`，作为该来源的元数据与 OA 通道 |
| `wiley` | `wiley_vch`（NS）、`wiley_online`（LS）、`wiley_wol`（SS） | 沿用 v1 id |
| `elsevier_sd` | `elsevier_sd`（NS、LS、SS、CS）、`cell_press`（LS） | Cell Press 与 ScienceDirect 共用 adapter，只是 VenueSpec 不同 |
| `oup_academic` | `oup`（NS）、`oup_academic`（LS、SS） | v1 adapter 名为 `oup_silverchair` |
| `cambridge_core` | `cambridge_core`（NS、LS）、`cup_core`（SS） | — |
| `tandf_online` | `tandf`（NS）、`tandf_online`（LS、SS） | — |
| `siam` | `siam`（NS）、`siam_epubs`（CS） | — |
| `nasa_ads_scix` | `nasa_ads_scix`（NS）、`nasa_ads`（AG） | ADS 正向 SciX 迁移 |
| `osf_preprints` | `osf_preprints`（LS）、`osf`（AG） | `psyarxiv`、`socarxiv` 按学科单列 |
| `worldbank_prwp` | `worldbank_prwp`、`worldbank_okr`（SS） | OKR 的 OAI/API 被 robots 禁止，已并入 |
| `ssrn` | `ssrn`（SS）、`ssrn_life`（LS 生医通道） | — |
| `crossref` | `crossref`（CS、AG）、SS 的"crossref（及 openalex/unpaywall/core/s2）"合并行 | — |
| 同名跨篇合并 | `pnas`、`mdpi`、`research_square`、`preprints_org`、`royal_society`、`apa_psycnet`、`annual_reviews`、`degruyter_brill`、`mit_press_direct`、`aaas_science`、`sage_journals`、`europe_pmc`、`pubmed`、`pmc`、`inspire_hep`、`zbmath_open`、`repec`、`econstor`、`econbiz`、`datacite`、`hal`、`chinaxiv`、`mathscinet`、`dblp`、`openalex`、`unpaywall`、`google_scholar` | — |
| 不单列 | NS §2.2.4 中由母源承载的 JPCS（`iop`）、AIP Conf. Proc.（`aip`）、EPJ WoC（`edp_sciences`）、ICM/Oberwolfach（`ems_press`）；NS §2.2.5 的"`acs`、`ams`、`cambridge_core`、`preprints_org`、`spie_dl` 的站点层面"说明行；LS 的"—（Google Scholar；Sci-Hub/LibGen）"排除行 | 这些内容已并入对应来源或排除行 |

**状态映射**：沿用设计简报 §6.1 的枚举。

- `v1-implemented` 不单独作为状态，而是由"v1"列为"是"来表达。这类来源在 v2 经 `v1_bridge` 包装迁移，"建议状态"列给出它们在 v2 的目标优先级。
- 各篇给出 "Px" 且不带"仅元数据"限定的，记为 `v2-Px`。
- 给出最高优先级的那一篇若注明"仅元数据"或"元数据经 Crossref、全文零自动化"，记为 `metadata-only（Px）`，括号里是登记优先级。
- 只做外链的记为 `link-only`；只能由用户导入题录的记为 `user-import-only`；被红线、条款或授权排除的记为 `excluded`。

**学科代码**

| 代码 | 学科组 |
|---|---|
| 数 | 数学（含统计） |
| 物 | 物理/天文 |
| 化 | 化学/材料 |
| 地 | 地学 |
| 生 | 生命/医学 |
| 心 | 心理 |
| 经 | 经济/金融 |
| 管 | 商业/管理（含社科） |
| CS | 计算机/AI |
| 区 | 中文/区域 |
| 全 | 全学科、通用 |

大型出版商按调研实际覆盖的学科逐一标注，不笼统记为"全"。

**列说明**

- "接入通道"压缩了原文的元数据通道与最新论文通道。
- "全文门控"给出全文能以什么方式获取，以及共享边界。
- "v1"一列取值为：是、部分、设计（仅有设计或名录登记）、否。
- "出处与各篇原建议"保留每篇调研的原始建议，便于回溯裁决过程（见 §3.4）。

### 3.2 总表（187 行）

#### 3.2.1 L2 通用聚合、DOI 注册与注册表（17 行）

| source_id | 名称 | 层级类型 | 学科 | 接入通道（元数据 / 最新） | 全文门控 | 建议状态 | v1 | 出处与各篇原建议 |
|---|---|---|---|---|---|---|---|---|
| `crossref` | Crossref | L2-aggregator（DOI 注册） | 全 | `/journals/{issn}/works` 与 `/works/{doi}`（单条池 5/s）；列表池 1/s、并发 1；polite 池 10/3；年度公共数据文件 208 GB | 无全文（仅 TDM/出版方链接）；摘要版权归出版方 | v2-P0 | 是 | AG P0；CS P0；SS P0 |
| `openalex` | OpenAlex | L2-aggregator | 全 | 季度 CC0 快照（约 745 GB）+ 计量 API（免费 key $1/日；增量过滤需 Member+）；semantic search 1 req/s | OA 定位；content PDF/TEI 保留原版权；摘要仅倒排索引 | v2-P0 | 是 | AG P0；CS P0（受预算约束） |
| `s2` | Semantic Scholar | L2-aggregator | 全 | Graph/Recommendations API（key 1 RPS）+ Datasets 周更（SPECTER2 Apache-2.0；TLDR/摘要 ODC-BY） | openAccessPdf 链接；须署名、不得再分发 API；商用未明示 | v2-P1 | 是 | AG P1（拿到 key 升 P0）；CS P1 |
| `unpaywall` | Unpaywall | L2-aggregator（OA 叠加层） | 全 | DOI 单查 API（email 参数；日限额 ⚠）；已并入 OpenAlex | OA 位置定位 | v2-P1 | 是 | AG P1；CS P1 |
| `core` | CORE | L2-repository（仓储聚合） | 全 | API key（个人 1,000/日、学术 5,000/日） | OA 全文（需注册）；推荐/发现类产品须联系 CORE；受商用开关门控 | v2-P1 | 设计 | AG P1 |
| `doaj` | DOAJ | L2-aggregator（OA 期刊目录） | 全 | API v4（2 req/s）+ OAI-PMH + CSV；元数据 CC0 | 全部 OA（按文章许可） | v2-P1 | 否 | AG P1 |
| `openaire` | OpenAIRE Graph | L2-aggregator | 全 | Graph API（匿名 60/h、认证 7,200/h）+ Zenodo dump（CC BY） | 链接 | v2-P2 | 否 | AG P2 |
| `opencitations` | OpenCitations | L2-aggregator（引文） | 全 | REST v2 + SPARQL + CC0 dump（180/min/IP） | 无 | v2-P1 | 否 | AG P1 |
| `datacite` | DataCite | L2-aggregator（DOI 注册） | 全 | REST（500→1,000→3,000 次/5 min）+ 年度 CC0 文件；arXiv 与 LIPIcs DOI 在此 | 无 | v2-P1 | 否 | CS P1；AG P2 |
| `orcid` | ORCID | L2-aggregator（注册表） | 全 | Public API（用户 OAuth；pub.orcid.org robots Disallow /）+ 年度 CC0 文件 | 无；公共 API 限非商业 | v2-P1 | 否 | AG P1 |
| `ror` | ROR | L2-aggregator（注册表） | 全 | REST v2（2,000 次/5 min）+ CC0 dump | — | v2-P1 | 否 | AG P1 |
| `zenodo` | Zenodo | L2-repository | 全 | OAI-PMH `/oai2d`（30/min；robots 禁 `/api`，Crawl-delay 10） | 按记录许可 | v2-P2 | 否 | AG P2 |
| `hal` | HAL | L2-repository | 全 | API v3（search/OAI；API 主机 robots 禁 `/search/`、`/oai/`，与文档邀请冲突 → needs_confirmation）；元数据 CC0 | OA 全文按许可 | v2-P2 | 否 | AG P2；CS P2 |
| `wikidata` | Wikidata / WikiCite | L2-aggregator（知识图谱） | 全 | SPARQL（学术子图已拆分）+ CC0 dump | 无 | v2-P2 | 否 | AG P2 |
| `open_policy_finder` | Jisc Open policy finder（原 Sherpa） | L2-aggregator（政策注册表） | 全 | 新 API（2026-02）；内容 CC BY-NC-ND 4.0 | 无（政策信息，辅助全文共享判定） | v2-P2 | 否 | AG P2 |
| `fatcat_ia_scholar` | Fatcat / IA Scholar | L2-aggregator（保存副本） | 全 | fatcat 不可达；Scholar 检索有 ALTCHA 挑战 | IA 保存副本链接 | metadata-only | 否 | AG 仅元数据/观察 |
| `lens` | Lens.org | L2-aggregator（机构订阅） | 全 | token API（机构订阅；须展示 logo） | 无 | metadata-only（用户自带 token） | 否 | AG 仅元数据 |

#### 3.2.2 L2 学科库、学科仓储与信号层（22 行）

| source_id | 名称 | 层级类型 | 学科 | 接入通道（元数据 / 最新） | 全文门控 | 建议状态 | v1 | 出处与各篇原建议 |
|---|---|---|---|---|---|---|---|---|
| `europe_pmc` | Europe PMC | L2-aggregator + repository | 生 心 | REST（143 字段、cursorMark、FIRST_IDATE 增量；数值限速未公布 ⚠）；ftp.ebi robots Disallow / | OA 子集 JATS（按 LICENSE） | v2-P0 | 否 | LS P0；AG P0 |
| `pubmed` | PubMed / MEDLINE | L2-aggregator | 生 心 | 年度 baseline + 日更文件（ftp.ncbi robots Disallow / → 需 robots ADR）+ E-utilities（3/10 rps） | 无全文；部分摘要受版权 | v2-P0 | 否 | LS P0；AG P0 |
| `pmc` | PubMed Central | L2-repository | 生 | 仅 4 条自动化通道：S3（带 license_code）、OAI-PMH（3 rps、禁并发）、E-utilities、BioC；OA Web Service 2026-08 退役 | OA 子集与作者手稿按 license_code 门控 | v2-P0 | 否 | LS P0；AG P1 |
| `pubtator3` | NCBI PubTator3 | L2-aggregator（实体标注层） | 生 | REST（BioC JSON；限速/许可 ⚠） | 仅标注 | v2-P1 | 否 | LS P1 |
| `icite` | NIH iCite | L2-aggregator（引文指标层） | 生 | REST（RCR、引文；限速/许可 ⚠） | 仅指标 | v2-P1 | 否 | LS P1 |
| `psycharchives` | PsychArchives（ZPID） | L2-repository | 心 | OAI-PMH（Crawl-delay 2） | OA，按条许可 ⚠ | v2-P2 | 否 | LS P2 |
| `inspire_hep` | INSPIRE-HEP | L2-aggregator（学科） | 物 | REST（15 次/5 s/IP；size ≤1000；元数据多为 CC0） | 链接（arXiv/DOI） | v2-P0 | 否 | NS P0；AG P1 |
| `nasa_ads_scix` | NASA ADS / SciX | L2-aggregator（学科） | 物 地 | token API（每用户 token；5,000 次/日/端点）；向 SciX 迁移（日期 ⚠） | 链接 | v2-P1 | 否 | NS P1；AG P2 |
| `zbmath_open` | zbMATH Open | L2-aggregator（学科） | 数 | REST + OAI-PMH + KG dump；数据 CC BY-SA 4.0（须署名、评估相同方式共享） | 无（链接） | v2-P0 | 否 | NS P0；AG P1 |
| `scoap3_repo` | SCOAP3 Repository | L2-repository | 物 | 官方 API `/api/records/`（87,667 条） | OA 全文 CC BY、元数据 CC0（可入共享层） | v2-P1 | 否 | NS P1 |
| `osti_gov` | OSTI.GOV | L2-repository | 物 化 地 | 官方 REST（entry_date 增量；限额 ⚠） | 链接/接受稿（许可 ⚠） | v2-P2 | 否 | NS P2（核验补充） |
| `pubchem` | PubChem | L2-aggregator（化合物） | 化 生 | PUG-REST（robots 禁 `/rest/pug/`，与文档化 API 冲突 → needs_confirmation） | 不适用（非论文源，仅关联） | v2-P2 | 否 | NS 仅作关联（P2） |
| `eudml` | EuDML | L2-aggregator（数学回溯） | 数 | OAI-PMH（robots 与 Identify 均 403） | 链接 | v2-P2 | 否 | NS 不优先（核验补充） |
| `repec` | RePEc（IDEAS/EconPapers） | L2-aggregator（学科，分布式） | 经 | FTP/rsync ReDIF bulk（官方推荐，勿抓网页）；OAI 不稳定 | 链接 | v2-P0 | 是（enrich，D-035） | SS P0（enrich）；AG P1（维持） |
| `econstor` | EconStor（ZBW） | L2-repository | 经 管 | OAI-PMH（秒级粒度；按学科/类型 set） | OA 全文（机构 WP 为主） | v2-P1 | 否 | SS P1；AG 仅元数据 |
| `econbiz` | EconBiz（ZBW） | L2-aggregator（学科） | 经 管 | API v1 beta（当前无配额；禁大规模复制；STW 标引） | 链接 | v2-P1 | 否 | SS P1；AG P2 |
| `fraser` | FRASER（St. Louis Fed） | L2-repository | 经 | API ⚠ 未核；robots Crawl-delay 10 | 免费 | v2-P2 | 否 | SS P2 |
| `ssoar` | SSOAR | L2-repository | 管 | ⚠（本轮连接失败） | OA 全文 | metadata-only | 否 | AG 仅元数据 |
| `dblp` | dblp | L2-aggregator（人工策展） | CS | 仅 DROPS 月度 XML 快照（CC0）+ sparql.dblp.org（Crawl-delay 10）；主站 robots 全禁 | 无（ee 外链） | v2-P0 | 部分（代码保留，D-037 出列） | CS P0（快照）；AG P1（离线） |
| `hf_papers` | Hugging Face Papers | L2-aggregator（社区信号） | CS | Hub API（daily_papers、papers/{id}；匿名 500 次/5 min） | 无（链 arXiv） | v2-P0 | 否 | CS P0（信号层） |
| `pwc_archive` | Papers with Code 存档 | L2-aggregator（静态） | CS | HF Datasets `pwc-archive/*`（CC BY-SA 4.0；2025-07-28 冻结） | 无 | v2-P1 | 否 | CS P1（一次性导入） |
| `alphaxiv` | alphaXiv | L2-aggregator（讨论与热度） | CS | 仅 MCP（OAuth/个人 API key；配额未公开） | 链 arXiv | v2-P2 | 否 | CS P2（仅用户自连） |

#### 3.2.3 L1 预印本与工作论文（30 行）

| source_id | 名称 | 层级类型 | 学科 | 接入通道（元数据 / 最新） | 全文门控 | 建议状态 | v1 | 出处与各篇原建议 |
|---|---|---|---|---|---|---|---|---|
| `arxiv` | arXiv | L1-preprint | 数 物 CS 生 经 | OAI-PMH 类目级 set（物理加 `physics:` 前缀）+ Query API；平台合计 ≤1 req/3 s 单连接；bulk 走 S3/Kaggle | 元数据含摘要 CC0；PDF 多为非独占许可 → 外链或用户私有，CC 许可者可共享 | v2-P0 | 是 | NS P0；LS P0（q-bio）；SS P0（econ/q-fin）；CS P0 |
| `chemrxiv` | ChemRxiv | L1-preprint | 化 | 委托 Crossref（10.26434，`/v{n}` 版本 DOI，摘要约 98%）；2026-01 迁 Wiley REX，站点 `/rss` 被 robots 禁 | 预印本公开，许可逐篇 ⚠ | v2-P0 | 否 | NS P0 |
| `biorxiv` | bioRxiv（openRxiv） | L1-preprint | 生 | 委托 Crossref（member 54368 / 前缀 10.64898）+ 官方 API（`/details` 2026-09-26 返回空 200 ⚠）+ RSS（Crawl-delay 10） | OA，许可 6 选 1（约 19% no-reuse）→ 按条门控；S3 不得作再分发源 | v2-P0 | 否 | LS P0 |
| `medrxiv` | medRxiv（openRxiv） | L1-preprint | 生 心 | 同 bioRxiv | 同 bioRxiv | v2-P0 | 否 | LS P0（默认只订心理/神经相关学科） |
| `psyarxiv` | PsyArXiv（OSF） | L1-preprint | 心 | OSF API v2（api.osf.io robots Disallow / → needs_confirmation）+ 委托 Crossref（10.31234）+ EPMC | OA，按条许可（CC BY/CC0 为主） | v2-P0 | 否 | LS P0 |
| `osf_preprints` | OSF Preprints（其余社区） | L1-preprint（OSF 基础设施） | 心 管 | 委托 Crossref（COS 名下 23 个前缀）；OSF API 同上 | OA，按条许可 | v2-P1 | 否 | LS P1；AG P1（经 Crossref） |
| `socarxiv` | SocArXiv（OSF） | L1-preprint | 管 经 | 委托 Crossref（10.31235，摘要 99%） | OA（osf.io Crawl-delay 10） | v2-P1 | 否 | SS P1 |
| `research_square` | Research Square | L1-preprint | 全 生 | 委托 Crossref（10.21203）+ EPMC；官方 API 申请制 ⚠；robots 禁 `/api/` | CC BY 4.0（Crossref 100%） | v2-P1 | 否 | NS P2；LS P1 |
| `preprints_org` | Preprints.org（MDPI） | L1-preprint | 全 | 委托 Crossref（10.20944）+ EPMC；站点 Akamai 403 | CC BY 4.0（100%） | v2-P1 | 否 | NS P2；LS P1 |
| `authorea` | Authorea Preprints（Wiley） | L1-preprint | 全 | 委托 Crossref（10.22541）+ EPMC | 许可 ⚠（Crossref 无 license 元数据） | v2-P2 | 否 | LS P2 |
| `ess_open_archive` | ESS Open Archive（AGU/Wiley） | L1-preprint | 地 | 委托 Crossref（10.22541） | 预印本公开 | v2-P2 | 否 | NS P2 |
| `eartharxiv` | EarthArXiv | L1-preprint | 地 | Crossref（10.31223）+ Janeway REST | 预印本公开 | v2-P2 | 否 | NS P2 |
| `optica_open` | Optica Open | L1-preprint | 物 | Crossref（10.1364/opticaopen，含版本 DOI） | 预印本公开 | v2-P2 | 否 | NS P2 |
| `techrxiv` | TechRxiv（IEEE） | L1-preprint | CS | 委托 Crossref（10.36227，带摘要） | OA，逐篇 license | v2-P1 | 否 | CS P1 |
| `iacr_eprint` | IACR Cryptology ePrint | L1-preprint | CS | OAI-PMH + RSS（robots 注释声明的元数据通道；`*` 为 Disallow /） | 各篇 license；全文只外链 | metadata-only（P1） | 否 | CS P1（仅元数据） |
| `eccc` | ECCC | L1-preprint | CS | ⚠ 未核 | OA ⚠ | v2-P2 | 设计（暂缓） | CS P2 |
| `ssrn` | SSRN | L1-preprint | 经 管 生 | 委托 Crossref（10.2139，新 DOI 当日可见）；ToU 禁止任何自动化查询 | 只外链；删除 v1 浏览器 opt-in 模式 B（新 ADR 取代 D-029/D-030） | metadata-only（P0） | 是（元数据） | SS P0（元数据）；LS P2/仅元数据（生医通道） |
| `nber_wp` | NBER Working Papers | L1-preprint | 经 | back RSS（Crawl-delay 10）+ Crossref（10.3386，摘要 0）；周更元数据文件需授权（data.nber.org 403）/ RePEc | 18 个月门控；机构 IP；不利用软门（D-014） | v2-P0 | 是 | SS P0（维护） |
| `cepr_dp` | CEPR Discussion Papers | L1-preprint | 经 | RePEc（Crossref 无系列记录） | 订阅/单篇购买 | metadata-only | 部分（经 RePEc 元数据） | SS 仅元数据 |
| `iza_dp` | IZA Discussion Papers | L1-preprint | 经 | RePEc 优先 + 站点列表页（robots 全允许） | 免费 PDF | v2-P1 | 否 | SS P1 |
| `fed_board_wp` | Fed Board FEDS/IFDP | L1-preprint | 经 | Crossref（10.17016，摘要 99%）+ RSS | 免费 | v2-P1 | 否 | SS P1 |
| `ecb_wp` | ECB Working Papers | L1-preprint | 经 | RSS（含摘要，Crawl-delay 5）；DOI 由欧盟出版局登记，不在 Crossref | 免费 PDF | v2-P1 | 否 | SS P1 |
| `bis_wp` | BIS Working Papers | L1-preprint | 经 | RSS 1.0 + CB-RSS 扩展（可做通用央行解析器） | 免费 PDF | v2-P1 | 否 | SS P1 |
| `imf_wp` | IMF Working Papers | L1-preprint | 经 | Crossref（10.5089，须过滤 component/chapter）/ RePEc；RSS 403 已停手 | 免费 | v2-P1 | 否 | SS P1 |
| `worldbank_prwp` | World Bank PRWP（含 OKR） | L1-preprint | 经 | 官方 D&R API v3（11,380 篇）；OKR 的 OAI/API 被 robots 禁，不用 | 免费（许可逐篇 ⚠） | v2-P1 | 否 | SS P1（OKR 并入） |
| `hbs_wp` | HBS Working Papers | L1-preprint | 管 | 经 SSRN/RePEc ⚠ | 免费 PDF ⚠ | metadata-only（P2） | 否 | SS 仅元数据（P2） |
| `mpra` | MPRA | L1-preprint（仓储型） | 经 | RePEc；EPrints OAI 在 robots 禁区 | 免费 PDF | metadata-only（P2） | 否 | SS 仅元数据（P2） |
| `cesifo_wp` | CESifo Working Papers | L1-preprint | 经 | RePEc ⚠ | 免费 ⚠ | v2-P2 | 否 | SS P2 |
| `other_cb_wp` | 其他央行/国际组织 WP（NY Fed、BoE、OECD 等，组） | L1-preprint | 经 | 优先 RePEc/Crossref；各自 RSS ⚠ | 多为免费 | v2-P2 | 否 | SS P2（按需逐个接入） |
| `chinaxiv` | ChinaXiv | L1-preprint | 全 区 | ⚠（robots.txt 返回 403 维护页） | OA 预印本 | v2-P2 | 否 | NS 待复核（P2）；AG 仅元数据/观察 |

#### 3.2.4 L1 出版商与学会平台（44 行）

| source_id | 名称 | 层级类型 | 学科 | 接入通道（元数据 / 最新） | 全文门控 | 建议状态 | v1 | 出处与各篇原建议 |
|---|---|---|---|---|---|---|---|---|
| `elsevier_sd` | Elsevier ScienceDirect（含 Cell Press） | L1-publisher | 数 物 化 生 心 经 管 CS | 委托 Crossref（摘要约 0%）+ PubMed；Elsevier API（每用户 key）；SD robots `*` Disallow / | 订阅/混合 OA（Cell 系按条 CC）；全文只经 Article Retrieval API（用户 key，非商业 TDM，输出 ≤200 字符） | v2-P0 | 是 | NS P0；LS P1（cell_press 同 adapter）；SS P0；CS P1 |
| `wiley` | Wiley Online Library（含 Wiley-VCH） | L1-publisher | 数 物 化 地 生 心 经 管 | 委托 Crossref（摘要 61–93%）；`/feed/{eissn}/most-recent` 允许；Atypon `/action`、`/rss` 禁 | 订阅/混合；TDM API（每用户 token；3 篇/s 且 60 次/10 min） | v2-P0 | 是 | NS P0；LS P1；SS P0 |
| `springer_link` | Springer Nature Link（Springer、BMC、EMBO、Palgrave） | L1-publisher | 数 物 化 生 心 经 管 CS | 官方 Meta/OA/Full-text API（每用户 api_key；OA 免费档 500/日；禁多 key）+ Crossref；robots 全禁+白名单（search.rss 不在内） | OA API（CC BY）；订阅 TDM：直接下载免费 1/s，TDM API 另付费；限机构内服务器、不得第三方访问 | v2-P0 | 设计 | NS P0（新 springer_nature_api）；LS P1；SS P1；CS P1 |
| `nature_portfolio` | Nature Portfolio | L1-publisher | 物 化 生 心 | 委托 Crossref（摘要 10–47%）+ `nature.com/{code}.rss`（允许）+ SN Meta API | 订阅+部分 OA；TDM 同 SN 条款 | v2-P0 | 否 | NS P0（元数据+RSS）；LS P1 |
| `oup_academic` | Oxford Academic | L1-publisher | 数 物 生 心 经 管 | 委托 Crossref（摘要 78–99%）；部分刊 RSS | 订阅/混合；无公开 TDM API；机构 SSO 仅在用户侧 | v2-P0 | 是（oup_silverchair） | NS P1；LS P1；SS P0 |
| `cambridge_core` | Cambridge Core | L1-publisher | 数 物 心 经 管 | 委托 Crossref（摘要 76–99%）；robots.txt 本身被 CF 挑战 | 订阅/混合；每小时 >500 PDF 可撤销；TDMRep | v2-P1 | 设计 | NS P1；LS P1/P2；SS P1（cup_core） |
| `tandf_online` | Taylor & Francis Online | L1-publisher | 数 物 化 心 经 管 | 委托 Crossref（多刊摘要 0%）；`/feed/rss/{code}` 允许 | 订阅/混合；STM 非商业 TDM（邮件报备）；有 tdmrep.json | v2-P1 | 否 | NS P1（元数据）；LS P1/P2；SS P1 |
| `sage_journals` | SAGE Journals | L1-publisher | 心 管 | 委托 Crossref（摘要 39–99%） | 混合（Psych Sci 2026 年 61% 为 CC）；AI 用途须另获许可 | v2-P1 | 设计 | LS P1；SS P1 |
| `aaas_science` | Science / AAAS | L1-publisher | 全 | 委托 Crossref + `/action/showFeed`（robots 明确 Allow） | Science 订阅；Science Advances 全 OA（经 PMC） | v2-P1 | 否 | NS P1；LS P1 |
| `pnas` | PNAS | L1-publisher | 全 | 委托 Crossref + showFeed（允许） | 2026 年约 99% 带 CC；PMC 覆盖 98%（6 个月） | v2-P0 | 否 | NS P1；LS P0 |
| `royal_society` | Royal Society Publishing | L1-publisher | 数 物 生 | 委托 Crossref（Proc B 须用 eISSN） | 2026 年 S2O 转 OA（门槛已达成） | v2-P1 | 部分 | NS P2；LS P1（核验补充） |
| `annual_reviews` | Annual Reviews | L1-publisher | 生 心 经 管 | 委托 Crossref（摘要 93–96%）；RSS 被 CF 挑战 | S2O：当年卷多为 CC | v2-P1 | 否 | LS P1；SS P2 |
| `mdpi` | MDPI | L1-publisher | 数 物 化 生 心 | OAI-PMH（不稳定，504）+ Crossref（摘要 100%）；www Akamai 403 | 全 OA（CC BY） | v2-P1 | 否 | NS P1（核验补充）；LS P1 |
| `frontiers` | Frontiers | L1-publisher | 生 心 | 委托 Crossref（摘要约 90%）+ RSS（允许） | 全 OA（CC BY）；PMC 覆盖高 | v2-P1 | 否 | LS P1 |
| `plos` | PLOS | L1-publisher | 生 心 | 官方 Search API（10/min、300/h、7,200/日、≤5 并发）+ Crossref（须用 eISSN）；allofplos 全量 | 全 OA（CC BY）；JATS | v2-P1 | 否 | LS P1 |
| `apa_psycnet` | APA PsycNet | L1-publisher | 心 管 | 委托 Crossref（摘要 0%）+ PubMed（部分）；robots `*` Disallow /；Imperva | 订阅；PsycInfo 为订阅库 | metadata-only（P2） | 否 | LS 仅元数据；SS 仅元数据（P2） |
| `cshl_press` | CSHL Press | L1-publisher | 生 | 委托 Crossref（注意 10.1101 前缀与旧 bioRxiv 共用） | 订阅/延迟开放；PMC 100% | v2-P2 | 否 | LS P2 |
| `hogrefe` | Hogrefe | L1-publisher | 心 | 委托 Crossref（摘要 71–81%） | 混合 | metadata-only（P2） | 否 | LS P2 仅元数据（核验补充） |
| `ucpress_online` | UC Press 期刊 | L1-publisher | 心 | 委托 Crossref（摘要 99%） | 全 OA（Collabra，CC BY） | v2-P2 | 否 | LS P2 |
| `aps` | American Physical Society | L1-publisher | 物 | Harvest API（OA 集免认证；全量需 JWT/IP/CHORUS）+ Crossref + RSS（小时级，个人使用） | PRX 系全 OA、单篇 CC BY；其余订阅；ToS 禁系统化下载 | v2-P0 | 部分 | NS P0 |
| `iop` | IOP Publishing（含 AAS 刊、JPCS） | L1-publisher | 物 | 委托 Crossref（摘要 0.98–1.00）；robots `*` Disallow /；2026-07 起机器访问需书面协议 | OA 或订阅；TDM 邮件申请、SFTP 交付 | metadata-only（P0） | 部分 | NS P0（仅元数据） |
| `aip` | AIP Publishing | L1-publisher | 物 | 委托 Crossref（摘要 0.98–0.99） | 订阅为主（S2O 试点 2025 年底结束） | v2-P1 | 部分 | NS P1 |
| `optica` | Optica Publishing Group | L1-publisher | 物 | 委托 Crossref（摘要 0.98） | 旗舰刊全 OA；其余订阅 | v2-P1 | 部分 | NS P1 |
| `edp_sciences` | EDP Sciences（A&A、EPJ WoC） | L1-publisher | 物 | 委托 Crossref | A&A 全 OA；EPJ WoC 为 OA 论文集 | v2-P1 | 部分 | NS P1 |
| `world_scientific` | World Scientific | L1-publisher | 物 数 | 委托 Crossref（robots 禁 `/rss`） | 订阅；短时下载阈值（二手 ⚠） | metadata-only（P2） | 否 | NS P2（元数据） |
| `degruyter_brill` | De Gruyter Brill | L1-publisher | 数 物 化 经 | 委托 Crossref | 订阅/OA；robots 依 §44b 保留 TDM | metadata-only（P1） | 否 | NS P1（元数据）；SS P2 |
| `acs` | ACS Publications | L1-publisher | 化 | 委托 Crossref（摘要 0.07–0.15）；站点 WAF 403 | 订阅；TDM 为付费方案；不做任何站点自动化（HC-27） | metadata-only（P0） | 部分 | NS P0（仅元数据） |
| `rsc` | Royal Society of Chemistry | L1-publisher | 化 | 委托 Crossref；迁 Silverchair 中（完成后重勘） | Chem Sci 等全 OA；TDM 须申请 | v2-P1 | 部分 | NS P1 |
| `ccs_chemistry` | CCS Chemistry | L1-publisher | 化 区 | 委托 Crossref（摘要 0） | 全 OA（DOAJ） | v2-P2 | 否 | NS P2 |
| `ams` | American Mathematical Society | L1-publisher | 数 | 委托 Crossref（摘要 0.70–0.87）；站点 CF 挑战 | 订阅；5 年滑动墙（二手 ⚠） | v2-P1 | 部分 | NS P1 |
| `siam` | SIAM | L1-publisher | 数 CS | 委托 Crossref + `/action/showFeed`（Allow） | 订阅 | v2-P1 | 设计 | NS P1；CS P2（siam_epubs） |
| `ems_press` | EMS Press | L1-publisher | 数 | 委托 Crossref（摘要 1.00） | 22 刊 S2O 全 OA（CC BY 4.0） | v2-P1 | 否 | NS P1 |
| `msp` | Mathematical Sciences Publishers | L1-publisher | 数 | 委托 Crossref（摘要 0）+ sitemap；摘要从 arXiv/zbMATH 补 | 订阅 | v2-P1 | 否 | NS P1 |
| `intl_press` | International Press | L1-publisher | 数 | 委托 Crossref（摘要 0–0.03） | Acta Math. OA；其余订阅 | v2-P2 | 否 | NS P2 |
| `uchicago_journals` | UChicago Press Journals | L1-publisher | 经 管 | 委托 Crossref（摘要 0%） | 订阅；批量下载需事先许可 | v2-P1 | 设计 | SS P1 |
| `mit_press_direct` | MIT Press Direct | L1-publisher | 经 CS | 委托 Crossref；TACL/CL 全文走 ACL Anthology | 订阅；TDM 需书面特批；TACL/CL 钻石 OA | metadata-only（P1） | 设计 | CS P1（仅元数据）；SS P2/仅按需单篇 |
| `emerald_insight` | Emerald Insight | L1-publisher | 管 经 | 委托 Crossref | 订阅/混合；TDM ⚠ | metadata-only（P2） | 否 | SS 仅元数据（P2；CFR 可 P1） |
| `pm_research` | PM Research | L1-publisher | 经 | 委托 Crossref（摘要 0） | 订阅 | v2-P2 | 设计 | SS P2 |
| `hbp_hbr` | Harvard Business Review | L1-publisher（实务刊） | 管 | ISSN 在 Crossref 不存在（404），无 DOI 枚举 | 订阅 | excluded | 否 | SS 排除 |
| `mit_smr` | MIT Sloan Management Review | L1-publisher（实务刊） | 管 | Crossref 新前缀 10.63383（仅 135 DOI） | 订阅 | metadata-only（P2） | 否 | SS 仅元数据（P2，观望） |
| `acm_dl` | ACM Digital Library | L1-publisher | CS | 委托 Crossref（摘要 15.5%）；无官方 API/OAI；ToS 禁脚本下载 | 2026-01 起全库 OA（CC BY/BY-NC-ND），匿名遇 CF；只外链（HC-27） | metadata-only（P1） | 设计（D-020/D-024） | CS P1（仅元数据） |
| `ieee_xplore` | IEEE Xplore | L1-publisher | CS | 委托 Crossref（零摘要，DOI 滞后 2–6 月）；平台层不用 IEEE API（HC-27） | 订阅；全文只在用户自己机构会话中 | v2-P1 | 设计 | CS P1 |
| `iospress_faia` | IOS Press FAIA（ECAI 等） | L1-publisher | CS | Crossref（10.3233，带摘要） | OA（样本 CC BY-NC 4.0） | v2-P1 | 否 | CS P1 |
| `now_publishers` | now publishers（FnT） | L1-publisher | CS 经 | Crossref（10.1561） | 订阅 | metadata-only（P2） | 设计 | CS P2（仅元数据） |

#### 3.2.5 L1 期刊平台（24 行）

| source_id | 名称 | 层级类型 | 学科 | 接入通道（元数据 / 最新） | 全文门控 | 建议状态 | v1 | 出处与各篇原建议 |
|---|---|---|---|---|---|---|---|---|
| `informs_pubsonline` | INFORMS PubsOnline | L1-journal_platform | 管 经 | 委托 Crossref（摘要 85–97%） | 订阅；条款页 CF 挑战 | v2-P0 | 设计 | SS P0（UTD24 中 7 刊） |
| `aom_journals` | AOM Journals | L1-journal_platform | 管 | 委托 Crossref（摘要 0%；OpenAlex 摘要滞后） | 订阅/会员 | v2-P0 | 否 | SS P0 |
| `aea_journals` | AEA Journals | L1-journal_platform | 经 | 委托 Crossref（摘要 80–94%） | 订阅；JEP 钻石 OA | v2-P0 | 是 | SS P0（维护） |
| `econsoc_journals` | Econometric Society（ECMA/TE/QE） | L1-journal_platform | 经 | Crossref + TE/QE OJS OAI-PMH | TE/QE 全 OA；ECMA 混合（按单篇 license） | v2-P0 | 是 | SS P0（维护） |
| `aaa_pubs` | AAA Publications（TAR 等） | L1-journal_platform | 管 | 委托 Crossref（摘要 91%） | 订阅 | v2-P1 | 否 | SS P1 |
| `misq` | MIS Quarterly | L1-journal_platform | 管 | 委托 Crossref（摘要 90%） | 订阅 | v2-P1 | 否 | SS P1 |
| `jstor` | JSTOR | L1-journal_platform（过刊） | 全 | Crossref（10.2307）；数据集人工申请；robots 具名禁 AI UA | 订阅 | metadata-only（P2） | 设计 | SS 仅元数据（P2） |
| `scipost` | SciPost | L1-journal_platform | 物 | 委托 Crossref（10.21468）+ `/feeds` | 全 OA | v2-P1 | 否 | NS P1 |
| `quantum_journal` | Quantum | L1-journal_platform | 物 | Crossref + RSS `/feed/`（允许） | 全 OA（arXiv overlay） | v2-P2 | 否 | NS P2 |
| `project_euclid` | Project Euclid | L1-journal_platform | 数 | 委托 Crossref（Duke/IMS 摘要 ≤0.14）；OAI ⚠ | 80% 以上开放 | v2-P1 | 否 | NS P1 |
| `centre_mersenne_numdam` | Centre Mersenne / Numdam | L1-journal_platform（兼仓储） | 数 | Crossref（10.5802）+ Numdam OAI-PMH（Crawl-delay 2） | 钻石 OA 为主 ⚠ | v2-P1 | 否 | NS P1 |
| `episciences` | Episciences | L1-journal_platform | 数 CS | Crossref/DataCite ⚠；OAI ⚠ | 钻石 OA ⚠ | v2-P2 | 否 | NS P2 |
| `annals_math` | Annals of Mathematics | L1-journal_platform | 数 | 委托 Crossref（摘要 0.11） | 订阅 | metadata-only | 否 | NS 仅元数据 |
| `geoscienceworld` | GeoScienceWorld | L1-journal_platform | 地 | Crossref ⚠ 未测 | 订阅 | v2-P2 | 否 | NS P2 |
| `sciengine` | SciEngine（中国科学等） | L1-journal_platform | 全 区 | Crossref ⚠ 未测 | 订阅/OA 混合 ⚠ | metadata-only（P2） | 否 | NS P2（仅元数据） |
| `wulixb` | 物理学报 | L1-journal_platform | 物 区 | Crossref ⚠ 未测 | ⚠ | v2-P2 | 否 | NS P2 |
| `elife` | eLife | L1-journal_platform | 生 | 官方 API（articles、reviewed-preprints；API 主机 robots Disallow / → needs_confirmation）+ Crossref + RSS | 全 OA（CC BY/CC0）；eLife Assessment 词表为质量信号 | v2-P1 | 否 | LS P1 |
| `peerj` | PeerJ | L1-journal_platform | 生 | 委托 Crossref（RSS 被 CF 挑战） | 全 OA；PMC 100% | v2-P2 | 否 | LS P2 |
| `sfn_journals` | SfN（J Neurosci、eNeuro） | L1-journal_platform | 生 | 委托 Crossref | 约 6 个月后 CC BY-NC-SA；PMC | v2-P1 | 否 | LS P1 |
| `f1000_platforms` | F1000Research 等 | L1-journal_platform（发表后评审） | 生 全 | EPMC + Crossref | OA ⚠ | v2-P2 | 否 | LS P2 |
| `jmlr` | JMLR | L1-journal_platform | CS | RSS（含摘要）+ citation meta；无 DOI | OA（CC BY 4.0） | v2-P0 | 设计 | CS P0 |
| `tmlr` | TMLR | L1-journal_platform | CS | OpenReview venue + jmlr.org 列表；无 DOI | 免费阅读（逐篇许可 ⚠） | v2-P0 | 否 | CS P0（随 openreview） |
| `jair` | JAIR | L1-journal_platform | CS | Crossref（10.1613，摘要 100%） | 钻石 OA | v2-P1 | 否 | CS P1 |
| `jstage` | J-STAGE | L1-journal_platform（兼聚合） | 全 区 | WebAPI（Atom；商业用途须申请；禁大批量下载；robots 禁 `/*_pdf`） | OA 为主，各刊不同 ⚠ | v2-P2 | 否 | AG P2 |

#### 3.2.6 L1 会议平台（29 行）

| source_id | 名称 | 层级类型 | 学科 | 接入通道（元数据 / 最新） | 全文门控 | 建议状态 | v1 | 出处与各篇原建议 |
|---|---|---|---|---|---|---|---|---|
| `openreview` | OpenReview | L1-conference_platform | CS | REST API v2（需免费账号；限流按请求而异，读响应头）；active_venues 匿名；平台服务账号须书面确认 | 元数据 CC0；PDF 作者版权，不缓存 | v2-P0 | 部分 | CS P0 |
| `pmlr` | PMLR | L1-conference_platform | CS | 卷页 + BibTeX；无 DOI | OA PDF | v2-P0 | 部分 | CS P0 |
| `neurips_proceedings` | NeurIPS Proceedings | L1-conference_platform | CS | 年页 + citation meta；Crossref（Curran 10.52202，约晚 8 个月） | OA PDF（未声明开放许可 ⚠） | v2-P0 | 是 | CS P0 |
| `cvf_open_access` | CVF Open Access | L1-conference_platform | CS | 目录页 + 论文 html（含摘要）；正式 DOI 在 IEEE | OA 录用版（作者版权） | v2-P0 | 是 | CS P0 |
| `ecva` | ECVA（ECCV 开放版） | L1-conference_platform | CS | `papers.php` + Springer DOI 外链 | OA PDF（许可未声明 ⚠） | v2-P1 | 否 | CS P1 |
| `acl_anthology` | ACL Anthology | L1-conference_platform | CS | GitHub XML + `acl-anthology` Python 包；Crossref 10.18653（无摘要） | OA；2016 起 CC BY 4.0（此前 CC BY-NC-SA 3.0） | v2-P0 | 部分 | CS P0 |
| `aaai_ojs` | AAAI OJS | L1-conference_platform | CS | OAI-PMH + Crossref（摘要 100%） | 免费阅读（© AAAI，非 CC） | v2-P0 | 是 | CS P0 |
| `ijcai_proceedings` | IJCAI Proceedings | L1-conference_platform | CS | 年页 + Crossref 10.24963（与 KR 共用前缀，按 container-title 分流） | 免费阅读（© IJCAI） | v2-P0 | 设计 | CS P0 |
| `usenix` | USENIX | L1-conference_platform | CS | 会议页 + citation meta；无 DOI（Crawl-delay 10） | OA | v2-P1 | 设计 | CS P1 |
| `ndss` | NDSS | L1-conference_platform | CS | Crossref 10.14722（无摘要） | OA PDF | v2-P1 | 否 | CS P1 |
| `pvldb` | PVLDB | L1-conference_platform | CS | Crossref 10.14778（摘要 100%） | OA（CC BY-NC-ND 4.0） | v2-P1 | 设计 | CS P1 |
| `isca_archive` | ISCA Archive | L1-conference_platform | CS | 年页 + Crossref 10.21437；当年卷被 robots 禁 | 免费阅读 | v2-P1 | 设计 | CS P1 |
| `lipics_drops` | Dagstuhl LIPIcs（DROPS） | L1-conference_platform | CS 数 | DataCite（10.4230）+ OAI-PMH | OA（CC BY 4.0） | v2-P1 | 设计 | CS P1 |
| `rss_proceedings` | Robotics: Science and Systems | L1-conference_platform | CS | 卷页 | OA | v2-P2 | 设计 | CS P2 |
| `mlsys_proceedings` | MLSys Proceedings | L1-conference_platform | CS | ⚠ 未核 | OA ⚠ | v2-P2 | 否 | CS P2 |
| `ceur_ws` | CEUR Workshop Proceedings | L1-conference_platform | CS | 卷页（robots 声明 License URL） | OA（许可 ⚠） | v2-P2 | 否 | CS P2 |
| `aamas_ifaamas` | IFAAMAS AAMAS Proceedings | L1-conference_platform | CS | Crossref 10.65109（按 container-title）+ 年度页 | 免费阅读（© IFAAMAS） | v2-P2 | 否 | CS P2（核验补充） |
| `cogsci_proceedings` | CogSci Proceedings | L1-conference_platform | 心 | eScholarship OAI-PMH（set=cognitivesciencesociety；网页 403） | OA（CC BY） | v2-P1 | 否 | LS P1 |
| `psb_proceedings` | Pacific Symposium on Biocomputing | L1-conference_platform | 生 | PubMed | ⚠ | v2-P2 | 否 | LS P2 |
| `pos_sissa` | Proceedings of Science（SISSA） | L1-conference_platform | 物 | Crossref（10.22323）+ INSPIRE | OA（许可逐卷 ⚠） | v2-P2 | 否 | NS P2 |
| `spie_dl` | SPIE Digital Library | L1-conference_platform | 物 | 委托 Crossref（10.1117）；站点 Incapsula 挑战 | 订阅/单篇购买 ⚠ | metadata-only | 否 | NS 仅元数据 |
| `assa_meetings` | ASSA 年会（含 AFA 等分会场） | L1-conference_platform | 经 | 程序 HTML（JEL + 摘要；robots 仅禁 GPTBot/Amazonbot） | 部分作者上传 PDF | v2-P1 | 否 | SS P1 |
| `nber_conferences` | NBER Summer Institute 与会议 | L1-conference_platform | 经 | 会议页 + 议程（复用 nber adapter 加会议标签） | 多链至 NBER WP | v2-P1 | 部分 | SS P1 |
| `wfa_meeting` | WFA 年会 | L1-conference_platform | 经 | 程序在登录门户，不自动化 | 作者自存（多在 SSRN） | metadata-only | 否 | SS 仅元数据（经 SSRN） |
| `sfs_cavalcade` | SFS Cavalcade | L1-conference_platform | 经 | 程序页 ⚠；`/acceptedpaper` 被 robots 禁 | 排除全文 | metadata-only（仅会议标签） | 否 | SS 排除全文、仅会议标签 |
| `efa_meeting` | EFA 年会 | L1-conference_platform | 经 | ⚠ 未核 | ⚠ | v2-P2 | 否 | SS P2 |
| `aom_proceedings` | AOM Annual Meeting Proceedings | L1-conference_platform | 管 | Crossref（10.5465/amproc，摘要 0%） | 会员 | v2-P2 | 否 | SS P2 |
| `ais_icis` | ICIS / AIS eLibrary | L1-conference_platform | 管 | bepress OAI 路径在 robots 禁区（`/do/`） | 多为 OA | v2-P2 | 否 | SS P2 |
| `sed_meetings` | SED Meetings | L1-conference_platform | 经 | RePEc ⚠ | ⚠ | v2-P2 | 否 | SS P2 |

#### 3.2.7 区域来源，以及仅外链、仅导入与排除项（21 行）

| source_id | 名称 | 层级类型 | 学科 | 接入通道（元数据 / 最新） | 全文门控 | 建议状态 | v1 | 出处与各篇原建议 |
|---|---|---|---|---|---|---|---|---|
| `cinii_research` | CiNii Research | L2-aggregator（区域） | 全 区 | OpenSearch（appid；robots 禁 `/opensearch`）；ResourceSync 允许 | 链接 | v2-P2 | 否 | AG P2（核验补充） |
| `scielo` | SciELO | L2-aggregator（OA 期刊网络） | 全 区 | ArticleMeta API（Crawl-delay 10）；OAI ⚠ | OA | v2-P2 | 否 | AG P2 |
| `redalyc` | Redalyc | L2-aggregator（OA） | 全 区 | OAI ⚠；robots.txt 返回 403 | OA | metadata-only | 否 | AG 仅元数据 |
| `paper_edu_cn` | 中国科技论文在线 | L2-repository | 全 区 | 全站维护停服 | OA | v2-P2（暂缓） | 否 | AG 暂缓 |
| `cnki` | 中国知网 | L2-aggregator（商业） | 全 区 | 无开放 API；robots Disallow / | 订阅 | user-import-only | 否 | AG 排除自动化（用户导入题录） |
| `wanfang` | 万方数据 | L2-aggregator（商业） | 全 区 | 无开放 API；检索子域 WAF | 订阅 | user-import-only | 否 | AG 排除自动化（用户导入题录） |
| `cqvip` | 维普 | L2-aggregator（商业） | 全 区 | 无开放 API；robots 部分禁止 | 订阅 | user-import-only | 否 | AG 排除自动化（用户导入题录） |
| `mathscinet` | MathSciNet | L2-aggregator（订阅 A&I） | 数 | 无开放 API；robots 基本全禁 | — | link-only | 否 | NS 排除自动化、只做外链；AG 排除自动化 |
| `cas_scifinder` | CAS SciFinder | L2-aggregator（订阅库） | 化 | 条款禁脚本批量抽取、自动化与 AI 用途 | — | link-only | 否 | NS 排除自动化、只做外链（核验补充） |
| `econlit` | EconLit | L2-aggregator（订阅书目） | 经 | 无公开 API；All rights reserved | 订阅 | excluded | 否 | SS 排除（仅作 JEL 参考） |
| `scopus` | Scopus | L2-aggregator（商业 A&I） | 全 | API key + 机构订阅；按用例授权 | 无 | excluded（平台层；用户自带 key 私用可选） | 否 | AG 排除（平台层） |
| `web_of_science` | Web of Science | L2-aggregator（商业 A&I） | 全 | Starter/Expanded API | 无 | excluded（平台层；用户自带 key 私用可选） | 否 | AG 排除（平台层） |
| `dimensions` | Dimensions | L2-aggregator（商业） | 全 | API/BigQuery（合同；仅非商业科学计量免费） | 无 | excluded | 否 | AG 排除（平台层） |
| `base` | BASE | L2-aggregator | 全 | API 需 IP 白名单；API 主机 robots Disallow / | 链接 | excluded（未获授权前） | 否 | AG 排除 |
| `microsoft_academic` | Microsoft Academic | L2-aggregator（历史） | 全 | 2021-12-31 关停 | — | excluded（仅兼容 `mag` ID） | 否 | AG 排除 |
| `google_scholar` | Google Scholar | L2-aggregator | 全 | 无 API；robots 禁 `/scholar`、`/search`；ToS 禁自动查询 | — | excluded（红线；仅支持用户手动导出后上传） | 否（明确排除） | NS、LS、CS、AG 均排除 |
| `scirate` | SciRate | L2-aggregator | 物 CS | 连 robots.txt 都被 CF 挑战 | — | excluded | 否 | CS 排除 |
| `paper_copilot` | Paper Copilot / paperlists | L2-aggregator（第三方整理） | CS | GitHub 数据无 license | — | excluded（仅参考字段设计） | 否 | CS 仅参考 |
| `conf_virtual_sites` | icml.cc / neurips.cc / iclr.cc（miniconf） | L1-conference_platform | CS | 数据在未文档化 `/static` JSON；robots 禁 `/static`、`/search` | — | excluded（仅人工核对） | 否 | CS 排除 |
| `informs_annual` | INFORMS Annual Meeting | L1-conference_platform | 管 | 仅摘要级程序 ⚠ | 无论文 | excluded | 否 | SS 排除 |
| `pirate_sources` | Sci-Hub / LibGen / Anna's Archive（盗版源，合为一行） | — | 全 | — | — | excluded（项目红线） | 否 | NS、LS 排除 |
### 3.3 学科覆盖统计

**总体分布（187 行）**

| 维度 | 分布 |
|---|---|
| 层级 | L1 129 行（出版商/学会 44、预印本与 WP 30、期刊平台 24、会议平台 31，其中 2 行在"区域与排除"组）；L2 57 行；盗版源合并行 1 |
| 建议状态 | `v2-P0` 36；`v2-P1` 63；`v2-P2` 44；`metadata-only` 26；`link-only` 2（MathSciNet、CAS SciFinder）；`user-import-only` 3（知网、万方、维普）；`excluded` 13 |
| v1 现状 | 是 16；部分 15；设计 21；否 135 |

**按学科组**

- 一个来源可以标注多个学科，因此各行之和大于 187。
- "全学科（通用）"一行统计的是标"全"的来源；这些来源同时服务所有学科，不计入各学科行。
- "仅外链/仅导入/排除"一列合并了 `link-only`、`user-import-only` 与 `excluded` 三种状态。

| 学科组 | 标注该学科的来源 | 其中 L1 | 其中 L2 | v2-P0 | v2-P1 | v2-P2 | metadata-only | 仅外链/仅导入/排除 | P0 来源 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 数学 | 24 | 21 | 3 | 6 | 11 | 3 | 3 | 1 | `zbmath_open`、`arxiv`、`elsevier_sd`、`wiley`、`springer_link`、`oup_academic` |
| 物理/天文 | 28 | 23 | 5 | 8 | 10 | 5 | 4 | 1 | `inspire_hep`、`arxiv`、`elsevier_sd`、`wiley`、`springer_link`、`nature_portfolio`、`oup_academic`、`aps` |
| 化学/材料 | 14 | 11 | 3 | 5 | 3 | 3 | 2 | 1 | `chemrxiv`、`elsevier_sd`、`wiley`、`springer_link`、`nature_portfolio` |
| 地学 | 6 | 4 | 2 | 1 | 1 | 4 | 0 | 0 | `wiley` |
| 生命/医学 | 27 | 21 | 6 | 11 | 10 | 5 | 1 | 0 | `europe_pmc`、`pubmed`、`pmc`、`arxiv`、`biorxiv`、`medrxiv`、`elsevier_sd`、`wiley`、`springer_link`、`nature_portfolio`、`oup_academic` |
| 心理 | 22 | 19 | 3 | 9 | 9 | 2 | 2 | 0 | `europe_pmc`、`pubmed`、`medrxiv`、`psyarxiv`、`elsevier_sd`、`wiley`、`springer_link`、`nature_portfolio`、`oup_academic` |
| 经济/金融 | 41 | 36 | 5 | 10 | 15 | 6 | 9 | 1 | `repec`、`arxiv`、`nber_wp`、`elsevier_sd`、`wiley`、`springer_link`、`oup_academic`、`informs_pubsonline`、`aea_journals`、`econsoc_journals` |
| 商业/管理（含社科） | 27 | 24 | 3 | 6 | 11 | 2 | 6 | 2 | `elsevier_sd`、`wiley`、`springer_link`、`oup_academic`、`informs_pubsonline`、`aom_journals` |
| CS/AI | 40 | 34 | 6 | 14 | 12 | 7 | 4 | 3 | `dblp`、`hf_papers`、`arxiv`、`elsevier_sd`、`springer_link`、`jmlr`、`tmlr`、`openreview`、`pmlr`、`neurips_proceedings`、`cvf_open_access`、`acl_anthology`、`aaai_ojs`、`ijcai_proceedings` |
| 中文/区域 | 12 | 5 | 7 | 0 | 0 | 7 | 2 | 3 | — |
| 全学科（通用） | 41 | 10 | 30 | 3 | 11 | 12 | 5 | 10 | `crossref`、`openalex`、`pnas` |

**覆盖评估**（结合各篇实测）：

| 学科组 | 评估 | 主要缺口与对策 |
|---|---|---|
| 数学 | 结构化主干较好：zbMATH、arXiv 类目、EMS S2O、Numdam；MathSciNet 只做外链 | MSP、IMS、Duke、Annals 的 Crossref 摘要接近 0，用 arXiv/zbMATH 补齐（NS §3-2）。MSC2020 为 CC BY-NC-SA，zbMATH 数据为 CC BY-SA，标签空间与派生发布须评估许可（NS 核验） |
| 物理/天文 | 通道丰富：INSPIRE、APS Harvest、SCOAP3、ADS；arXiv 为第一来源 | IOP 站点零自动化，只取元数据；PRL/PRB 摘要覆盖偏低，走 Harvest → arXiv → OpenAlex 补齐链；ADS token 须每用户自持 |
| 化学/材料 | **最弱的理科**：摘要中位数 11%；ACS 只取元数据；CAS SciFinder 只外链；缺开放的细粒度分类法 | 摘要走 ChemRxiv 版本 → OpenAlex 补齐（NS §3-2）；化学侧的冷启动靠 OpenAlex subfield 与嵌入。材料来源未单独调研（§7.3 G-05） |
| 地学 | **最薄**：仅 6 行（Wiley、GeoScienceWorld、ESSOAr、EarthArXiv、OSTI、ADS） | AGU、EGU/Copernicus、GSA 等未调研，列为补充调研（NS §4、§7.3 G-05） |
| 生命/医学 | **最强的 L2**：Europe PMC、PubMed、PMC 的许可字段完善；预印本（bioRxiv/medRxiv）量大 | PMC 自动化通道收缩；bioRxiv `/details` 返回空体，须监控并经 Crossref 兜底；bulk 主机的 robots 冲突需 ADR（LS §4、AG 核验） |
| 心理 | 覆盖依赖 Crossref，但 APA 摘要与参考文献均为 0%；PubMed 覆盖残缺；PsyArXiv 与 CogSci OAI 可用 | APA 只取元数据；心理学用"关联 PsyArXiv、OpenAlex 摘要（计费）、用户导入 PsycInfo/RIS、OpenURL"补齐（LS §3-15）；心理学会议（Psychonomics、SPSP、CCN）未核验 |
| 经济/金融 | **行数最多（41）**：NBER、央行与国际组织 WP、RePEc bulk、AEA、ECMA、ASSA | SSRN 只取元数据加外链；NBER 周更文件需授权；ECB 只能走 RSS；IMF 在 Crossref 中须过滤 component（SS §3-12） |
| 商业/管理 | UTD24 中 21/24 刊在 Atypon 或 Silverchair，INFORMS 与 AOM 列为 P0 | AOM、UChicago 的摘要为 0；期刊名录（FT50、AJG、ABDC）的许可只允许用户私有导入（SS §2.7、§3-10） |
| CS/AI | **P0 最多（14）**：OpenReview、ACL Anthology、PMLR、CVF、AAAI、IJCAI、JMLR/TMLR、dblp 快照、HF 信号 | IEEE 与 ACM 只取元数据；无 DOI 的 venue 要靠原生通道；DOI 时滞需实测（CS §3-5）；MLSys、RSS、ECCC 未核验 |
| 中文/区域 | **没有 P0/P1**：知网、万方、维普只能由用户导入；ChinaXiv 维护中；J-STAGE、SciELO、CiNii 列 P2 | 中文覆盖靠用户导入题录，加上 OpenAlex/Crossref 中已有的中文刊元数据（AG §3-17）；需补一轮中文生态调研（§7.3 G-05） |

### 3.4 优先级冲突的裁决记录

| 来源 | 各篇原建议 | 采用 | 理由 |
|---|---|---|---|
| `pnas` | NS P1；LS P0 | v2-P0 | 2026 年约 99% 带 CC，PMC 覆盖 98%，全文可走 PMC，完全不接触出版商站点（LS §2.4.4） |
| `research_square` / `preprints_org` | NS P2；LS P1 | v2-P1 | Crossref 登记为 100% CC BY，经 L2 即可接入，接入成本低 |
| `econstor` | SS P1；AG 仅元数据 | v2-P1 | OAI 可用、robots 未禁；AG 的"仅元数据"指经 CORE/OpenAlex 取元数据，与 SS 的 OAI 方案不矛盾 |
| `inspire_hep` / `zbmath_open` | NS P0；AG P1 | v2-P0 | 分别是本学科的检索主干（NS §3-4）；zbMATH 须署名并评估 ShareAlike |
| `nasa_ads_scix` | NS P1；AG P2 | v2-P1 | 天文检索主干，token 由每用户自持 |
| `pmc` | LS P0；AG P1 | v2-P0 | 生医 OA 全文的主通道，只走 4 条自动化通道 |
| `datacite` | CS P1；AG P2 | v2-P1 | arXiv 与 LIPIcs 的 DOI 都在 DataCite |
| `dblp` | CS P0（快照）；AG P1（离线） | v2-P0（快照形态） | CS 的 venue、会议卷与作者 PID 主干；在线访问停止 |
| `repec` / `econbiz` | SS P0（enrich）/P1；AG P1/P2 | v2-P0 / v2-P1 | 经管 JEL 与"WP↔发表版"关联主干；EconBiz 的 STW 词表用于补经管路由 |
| `elsevier_sd`、`wiley`、`springer_link`、`oup_academic`、`nature_portfolio` | 各篇 P0–P1 不等 | v2-P0 | 跨学科体量最大；元数据零接触（走 Crossref），全文走每用户官方 API 或用户侧会话 |
| `royal_society`、`annual_reviews`、`siam`、`tandf_online`、`cambridge_core` | P1–P2 不等 | v2-P1 | 取最高值；全文限用户侧 |
| `mit_press_direct`、`degruyter_brill` | CS P1（仅元数据）；SS P2；NS P1（元数据） | metadata-only（P1） | 给出最高值的那一篇带"仅元数据"限定 |
| `apa_psycnet` | LS 仅元数据；SS 仅元数据（P2） | metadata-only（P2） | robots `*` 全禁，且有 Imperva 防护 |
| `ssrn` | SS P0（元数据）；LS P2/仅元数据 | metadata-only（P0） | 新 DOI 当日可见，价值高；但 ToU 禁止自动化，只取元数据加外链 |
| `s2` | AG P1；CS P1 | v2-P1 | key 只有 1 RPS，商用未获书面确认；二者落实后可升 P0 |
| `chinaxiv` | NS 待复核（P2）；AG 仅元数据/观察 | v2-P2（观察） | 站点维护中 |

### 3.5 名录维护建议

1. **单一事实来源**：机读注册表（`registry/sources/*.yaml`，实现期落地）是唯一事实来源，文档形态的支持名录由它生成（简报 §6.1-7）。本表的 187 行作为首版种子导入，每行都带上原始调研章节号。
2. **证据时效**：每个通道带 `evidence {url, verified_at}`。超过 90 天未复核的，由策略引擎降为 `needs_confirmation`。
3. **快变事实按季度复核**，包括：
   - arXiv 独立非营利后的 ToU 与 bulk 渠道；
   - ADS→SciX 的切换；
   - bioRxiv API；
   - PMC 通道；
   - OpenAlex 计费与快照节奏；
   - Crossref 分池；
   - SSRN 平台变更；
   - dblp 的 robots；
   - X 算法参数（按 commit 固定引用）。
4. **状态变更留痕**：状态变更须写明依据，例如 `metadata-only → v2-P1` 需要一手条款或书面确认。凡涉及 robots 与文档化 API 冲突的，须引用 robots 统一 ADR（简报 §7-2）。
5. **缺口来源**：地学、材料、中文生态、心理学会议、部分 CS venue 按 §7.3 补充调研后再增行。新增行沿用本表的列与状态枚举。

---
## 4. 竞品地图、定位与可复用开源

### 4.1 竞品地图（8 层）

| 层（MK §2.1） | 代表产品（核验要点） | 对 v2 的含义 |
|---|---|---|
| L1 开放基础设施 | Semantic Scholar + Ai2 Asta、arXiv、HF Papers、OpenAlex/Crossref | 它们是 v2 的数据与信号来源，不是竞争对象。借鉴 Asta Paper Finder 的显式意图路由（快速模式约 30 s、深入模式约 3 min）（OSS §2.5.1） |
| L2 订阅与个性化流 | S2 Research Feeds（每用户线性 SVM）；Scholar Inbox（23k 注册、8k 月活，ACL 2025 Demo）；Paper Digest；R Discovery（GetFTR + LibKey 机构登录）；Read by QxMD（机构一键取 PDF）；Scollr；AMiner 订阅；ZiNote、PaperCrush（滑动，采用度极低）；Researcher（2024-11 关停） | 最直接的竞品。借鉴每用户线性模型、科学地图冷启动、主动学习与 digest。避免依赖单一上游，也避免没有退出方案（MK §2.2.A、§2.2.I） |
| L3 社区热度与讨论 | HF Daily/Trending；alphaXiv（2025-11 获 $7M 种子轮）；Emergent Mind；Sciety；ResearchGate（版权诉讼，2023-09-15 和解）；PubPeer（作者回应率 7.5%，匿名评论 85.6%）；Paper Skygest（Bluesky 自定义 feed，每周使用 5 万次以上）；ResearchHub（代币激励） | 可作开放热度信号，逐源核验条款；评论治理有先例可循；早期不做代币激励（MK I-7、I-13） |
| L4 引文图谱 | Connected Papers（共被引 + 文献耦合）；Litmaps（2025-05 收购 ResearchRabbit）；ResearchRabbit；Inciteful（已转向） | 放在详情页"相关论文"与探索页，不作主形态（SR §2.3） |
| L5 AI 检索/综述 Agent | Elicit（约 40 万月活，Pro $49/月）；Consensus（2024-08 年化收入"近 $2M"，付费率约 3%）；scite；SciSpace（◐）；Undermind；Iris.ai；Perplexity；ChatGPT Deep Research；Google Scholar Labs（2026-06-03 起对全体登录用户开放）与 Quick Read（只对有访问权的论文显示） | 不正面竞争，深度检索靠集成（MK I-15）。Quick Read"只对有权限的论文出现"印证了私域原则 |
| L6 阅读/写作/文献管理 | Zotero、Mendeley、Paperpile、ReadCube、Scholarcy、Keenious、Moonlight、NotebookLM Audio（官方承认存在不准确） | 用于导入导出与冷启动种子（Zotero API、BibTeX）；"导出引用"是价值最高的正向行为（SM §3-2） |
| L7 出版商/数据库商 AI | Scopus AI、ScienceDirect AI、WoS Research Assistant、Dimensions | AI 只作用于订阅内容，不存储、不训练公共模型。这是 v2 私域原则的行业先例（MK §0-7、§2.2.F） |
| L8 中文综合平台与社媒 | 知网 AI、百度学术（2025-09-11 AI 重构）、秘塔、AMiner/Z.ai（2026-01-08 港股上市）、玻尔（深势科技，C 轮 >¥8 亿）、ReadPaper、Kimi、Cool Papers（非学习型排序）；小红书、抖音 | 中文市场以"检索 + AI 问答"为主轴，推荐流稀缺，论文科普靠社媒传播。双语卡片与分享卡（只限开放内容）是切入点（MK §2.8） |

### 4.2 能力空白（MK §2.9 G1–G7，含续核验修正）

| 缺口 | 现状 | v2 的机会 |
|---|---|---|
| G1 学科 | 主流 feed 集中在 AI/ML 与生命科学。经管的元数据并不缺（OpenAlex 收录 SSRN 1,691,849 条、NBER 34,992 条），缺的是 WP 新鲜度、顶刊 TOC 与个性化卡片流的组合 | v1 已有 SSRN（仅元数据）、NBER、RePEc、AEA、ECMA 资产，加上 §3 的央行 WP 与 UTD24 平台族 |
| G2 交互 | 学习型移动 feed 已经存在（R Discovery），滑动形态只有采用度极低的小 App | 滑动加学习型推荐加可解释。形态风险用列表/卡片 A/B 对冲 |
| G3 合规全文 | "机构凭证一键取全文"已有先例，不是空白 | 收窄为"任意类型的用户自有凭证，加多用户平台下的私域隔离" |
| G4 可解释可控 | 解释只出现在 agentic 搜索与学术原型里；S2 的 CHI 2022 研究表明关系型解释能提高参与度 | why-this 理由码、可删标签、非个性化视图（也是合规义务） |
| G5 质量信号分散 | 撤稿、scite、Sciety、eLife Assessment 各自为政 | 质量与可信度徽章，逐源核验许可（MK I-10、LS §3-8） |
| G6 双语与社交分发 | 中文用户接受卡片与短内容；社媒承担论文传播 | 双语卡片与分享卡，只限开放内容（MK I-17、CP HC-01） |
| G7 双向匹配 | 只有弱形态 | 三层匹配，研究者↔研究者需 opt-in（SR §2.10） |

### 4.3 定位建议

1. **一句话**：面向跨学科研究者（尤其是 CS/AI 与经管金融的交叉人群）的合规优先、可解释的个性化论文卡片流（MK §2.9，与简报 §2 一致）。
2. **差异化只能来自组合**：同时做到学习型个性化、移动卡片分拣、经管 WP 覆盖、自带凭证取全文与可解释推荐（MK §2.5 的矩阵中没有任何一行五列全满），再加上经管 WP 的新鲜度与多用户私域合规。语料规模不构成护城河：S2、OpenAlex、Elicit、Consensus 都有上亿篇（MK §0-2）。
3. **形态演进**：
   - 阶段 1：实验室或团队自托管多用户；
   - 阶段 2：邀请制托管；
   - 阶段 3：机构版，提供 SSO、link resolver 与席位，平台不代理机构访问（MK §2.9）。

   这与简报 B-02 的 platform/personal 同码部署一致。
4. **商业模式备选**（MK §2.10，简报 Q1 默认非商业）：

   | 编号 | 模式 | 适配度 |
   |---|---|---|
   | B1 | 开源自托管 + 官方托管 | 高 |
   | B2 | 实验室/机构席位 | 高 |
   | B3 | 个人 Pro（$5–10/月） | 中 |
   | B4 | 资助 | 中 |
   | B5 | 作者服务交叉销售 | 低 |

   明确不做广告、付费推广与数据转售。无论最终是否商用，依赖选型都按"可能商用"的最严口径（简报 B-06、CP DI-07）。
5. **成功指标**：
   - 北极星：每周每活跃用户的有价值阅读数；
   - 护栏：D7/D30 留存、每会话滑动数、收藏率、"不相关"比例、理由点击率、digest 打开率（Scholar Inbox 的 30 天活跃率为 35%）（MK I-19、SM §3-4）。
6. **退出与可移植**：从第一天起支持导出 BibTeX、RIS、JSON，并为 S2 key、OpenAlex 额度等外部依赖设计降级路径（MK I-16）。

### 4.4 可复用开源清单（复用 / 集成 / 借鉴 / 排除）

以 OSS §6 的 R/I/B/X 分级为骨架，合并 RO、RT、UX、PU、SR 的结论。

**许可口径**：
- 核心链路只接受 Apache、MIT、BSD、PostgreSQL 许可（简报 B-06）；
- 模型权重与数据集的许可单独审查；
- 没有 LICENSE 的仓库只能借鉴思路。

**复用**（作为依赖或组件）

| 领域 | 组件（许可） | 用途与前置条件 | 证据 |
|---|---|---|---|
| 存储与检索 | PostgreSQL 18、pgvector（PostgreSQL）、pgvectorscale（PostgreSQL）、pg_textsearch（PostgreSQL；仅 PG 17/18）、pg_roaringbitmap（Apache-2.0）、Qdrant（Apache-2.0，T2 外置时用）、faiss、hnswlib | 单栈检索与已见位图；按 §2.2 的触发条件升级 | RT §5、§6.3；OSS §6.1 |
| 队列与缓存 | procrastinate（MIT）、pgqueuer（MIT）、Valkey（BSD） | PG 原生队列；LISTEN 需要直连或会话池 | RT §10.5–10.6 |
| 稳定性与采集 | tenacity、stamina、aiolimiter、PyrateLimiter、pybreaker、hishel；protego（robots 解析）；sickle（OAI-PMH） | 重试、限速、熔断与 HTTP 缓存；robots 先行闸 | RT §9.2；OSS §2.10.5 |
| 客户端与数据件 | openreview-py（MIT）、acl-anthology 包、pubmed_parser、metapub、pyzotero（Blue Oak 1.0.0）、grobid-client-python、citation.js、splink（MIT，实体消解） | 第三方客户端须锁版本并配契约测试 | OSS §6.1、§3-18、§3-20 |
| 表示与重排 | sentence-transformers、text-embeddings-inference、FlagEmbedding/BGE-M3（MIT）、Qwen3-Embedding/Reranker（Apache-2.0）、gte-large（MIT）、SPECTER2 base（Apache-2.0；adapter 的许可字段 ⚠ 待核） | 按 V1 里程碑的分学科评测定型；向量带版本并双写 | SR §2.2.4；RT §4.5；RO §3.1-6 |
| 推荐库 | implicit（MIT）、LensKit（MIT）、River（BSD-3）、Vowpal Wabbit（BSD-3，须 ≥9.11.6）、daffidwilde/matching（MIT，稳定匹配） | R1 起的协同过滤、在线学习、探索与离线评估（OPE） | RO §2.4、核验补充 |
| 文档解析与卡片内容 | Docling（MIT）与 DocumentFigureClassifier-v2.5（MIT）、pypdfium2（Apache-2.0/BSD-3）、KeyBERT（MIT） | 选图兜底与关键词；arXiv HTML 优先 | PU §2.2、§2.4.2 |
| 质量评测 | MiniCheck-FT5（MIT）、HHEM-2.1-Open（Apache-2.0）、AlignScore（MIT）、SummaC（Apache-2.0）、FineSurE（Apache-2.0）、MetricX-24（Apache-2.0）、COMET-22（Apache-2.0） | 三道闸与翻译质量评估 | PU §2.7 |
| 前端 | React 19.3、Motion 13、Base UI（Drawer）、TanStack Virtual、masonic、KaTeX、pdf.js | 自建约 200 行的 Deck；Motion 须显式传弹簧参数 | UX §2.8、§2.10；PU §3-7 |
| 冷启动与评测 | ASReview（主动学习）、pyserini（检索基线） | 冷启动校准卡；离线基线 | OSS §6.1、§3-22 |

**集成**（独立服务、外部接口，或有条件使用）

| 组件 | 条件 | 证据 |
|---|---|---|
| GROBID（Apache-2.0，服务）、biblio-glutton | 选图须新增 `teiCoordinates=figure`（属于 design/12 的变更） | PU §1.3、§3-22 |
| Zotero translation-server（AGPL） | 作为独立进程运行，改用诚实 UA，只在用户触发时调用并限速 | OSS §6.2、§3-17 |
| olmOCR、DeepSeek-OCR（MIT）、dots.ocr（MIT）、PaddleOCR；MinerU、Marker/Surya、Chandra | MinerU 有规模门槛与署名义务；Marker/Surya 权重仅在融资或营收 <$5M 时免费；Chandra 限 <$2M、不得与其 API 竞争，商用自托管需另获许可。须在自有样本上用 olmOCR-Bench 复测后再选型 | OSS §6.2、§3-19 |
| OpenSearch（Apache-2.0）、Vespa、Meilisearch 社区版、Apache AGE（Apache-2.0）、ParadeDB（AGPL，需法务评估） | 只在 T2 或特定需求时启用；PG 始终是真值源 | RT §5.2；OSS §6.2 |
| Gorse（Apache-2.0） | 可作 R1 推荐引擎候选；私有反馈隔离 ⚠ 待验证 | RO §2.4 |
| ClickHouse | 事件量超过 10⁹ 行/年后引入 | RT §10.4 |
| Expo SDK 57、Reanimated 4、RNGH 3 | v2.x 原生端，待移动端留存验证后启动 | UX §2.10 |
| 外部接口：OpenAlex API/CLI/官方 MCP、HF Hub API、Zotero Web API、NASA ADS、INSPIRE、OSF、eLife、PLOS API；pybliometrics（用户自带 Scopus key） | 按量计费或需账号的接口一律由用户自带 key 或 OAuth；结果按许可分层 | OSS §6.2、§3-5 |
| 仓储平台族：DSpace、EPrints、InvenioRDM、OJS | 实例注册表，加 robots/ToS 快照与保守限速 | OSS §3-16 |

**借鉴**（只借思路，不引入代码或数据）

| 主题 | 项目与借鉴点 | 证据 |
|---|---|---|
| 查询编译与意图路由 | findpapers（AST 查询编译与 DNF 并集；需补跨请求的 AND/NOT）、Asta PaperFinder（意图路由；仓库已冻结）、paper-search-mcp（能力矩阵）、arxiv-mcp-server（HTML 优先、按大纲逐节读）、OpenAlex 官方 MCP（规范化 OQL，额度归用户） | OSS §2.3.1、§2.4、§3-1/2/21 |
| 推荐与反馈 | xai-org/x-algorithm（Apache-2.0，按 commit 引用：Σw·P、负分偏移、DPP、新作者冷启动、候选隔离）、twitter/the-algorithm（AGPL，只借设计）、Scholar Inbox 与 S2 Research Feeds 配方、arxiv-sanity-lite、zotero-arxiv-daily（AGPL，时间衰减权重）、daily-paper-reader（MIT，多路召回配额）、PaperFlow（反馈语义）、arXivDigest（living lab）、SimClusters、Community Notes 的 bridging 排序；OneRec 与 HSTU 只预留数据形态 | RO §2.2、§2.6–2.7；SM §2.4；OSS §3-8/§3-10 |
| 双向匹配 | openreview-expertise（MIT，亲和度）、openreview-matcher（无 LICENSE，按论文自行实现最小费用流、FairFlow、FairSequence）、RECON、Hinge 的 Gale–Shapley | SR §2.10；RO §2.9 |
| 研究助手 | PaperQA2、OpenScholar、Ai2 ScholarQA、PaSa（排除其 Serper 依赖）、STORM、local-deep-research（每用户加密库） | OSS §2.5 |
| 前端与形态 | papertok（scroll-snap、诚实标签、Base UI Drawer）、arxivtok、Wispar（GPL；每用户 EZproxy、可配置手势）、Cool Papers；wikitok 是反例：它丢弃无缩略图的条目 | UX §2.2.2–2.2.3；OSS §2.6 |
| 检索与知识组织 | arxiv-at-home（行锁保证恰好一次索引、标题模糊匹配加权）、abstracts-search（证明离线全局语义索引可行）、LocalCitationNetwork、ORKG | OSS §2.7 |

**排除**

| 原因 | 项目或组件 | 证据 |
|---|---|---|
| 盗版源（红线） | PyPaperBot、SciDownl、Sci-Hub-MCP-Server、libgen-mcp；paper-search-mcp、gs-skills、gpt_academic、paper-search-mcp-nodejs 中的 Sci-Hub 组件 | OSS §2.11、§6.4；CP HC-26 |
| Google Scholar 自动化或绕封锁 | scholarly（作为来源）、Google-Scholar-MCP-Server、mcp-scholarly、gs-skills、SearXNG（作为学术主源）、PaperFlow 的 Scholar 主页抓取 | OSS §6.4；CP HC-26 |
| 冒充或浏览器自动化 | paper-search-mcp 的"Mozilla UA 升级重试"、findpapers 的 `web_scraping`（curl_cffi 冒充 Chrome TLS 指纹）、cnki-skills、PaSa 的 serper.dev 依赖 | OSS §6.4 |
| 淘汰或停更 | paperswithcode-client（平台关停）、Kùzu（已归档）、science-parse、CERMINE、Nougat（另有权重非商用问题）、arq（维护模式）、Azure Personalizer（2026-08-25 退役）、LightFM（Py3.12 不可用）、use-gesture（2024-07 起停更）、vaul（无人维护）、react-tinder-card（停更） | OSS §6.4；RT §10.6；RO §2.4；UX §2.8 |
| 许可与 B-06 冲突（不得进入默认路径） | FalkorDB（SSPL）、Memgraph（BSL）、Elasticsearch 的 RRF（仅 Enterprise）、Dolphin（Qwen 研究许可）、MonkeyOCR v1 权重（非商用）、jina-embeddings v3/v5 与 NV-Embed-v2（CC-BY-NC）、SPLADE 官方权重（NC）、NLLB（CC-BY-NC）、CometKiwi/XCOMET（CC BY-NC-SA）、snap-research/GRID（仅非商业）、Hunyuan-MT/HY-MT（许可排除欧盟、英国、韩国）、YAKE（AGPL）、CSRankings 数据（CC BY-NC-ND）、Scholar Inbox 数据集（CC BY-NC-ND，只可用于非商业内部评测）、MSC2020（CC BY-NC-SA，作标签空间时受商用开关约束） | OSS §6.4；SR §0-4；RT §4.5；PU §2.3；CS §2.5；RO 核验 |

---

## 5. 跨主题的冲突与张力

| # | 张力 | 一端的证据 | 另一端的证据 | 建议取舍 | 承接 |
|---|---|---|---|---|---|
| T1 | 社媒式参与度优化 vs 科研质量 | 社媒以时长与互动为目标；Douyin 的目标是"用户长期价值"；YouTube 转向 valued watch time（SM §2.1、§2.6） | 论文推荐的目标是有价值的阅读；参与度诱饵与争议会放大评论权重（SM §2.13.2）；S2 与 Scholar Inbox 刻意压低流行度偏差（SR §0-7） | 北极星取"每周有价值阅读数"，时长只作护栏；有限批次加"今日已刷完"；分拣卡不显示社交计数；给流行度特征设上限；探索槽带标注（SM §3-4；UX §3-7/§3-22；MK I-9） | 01、06、07 |
| T2 | 个性化 vs 合规与隐私 | 个性化需要画像、行为日志与协同信号（RO §3.1） | CAC《算法推荐管理规定》第 16/17 条与 PIPL 第 24 条要求非个性化选项和可删标签；DSA 第 27 条要求透明；小样本下的社会证明可反推个人行为（CP HC-13、HC-20；SM §3-14） | 全球统一内建：why-this、可删标签、一键非个性化视图（关闭后按时间或来源排序）；社会证明至少 k 个不同用户；私有库共现不入协同；日志留存 ≥6 个月；画像可删除 | 06、08 |
| T3 | 多用户 vs 凭证与全文不共享 | 多用户平台天然想做去重、缓存与预取，以降本增效（RT §7） | 出版商 TDM 条款、SERU 与 EZproxy 规则禁止共享和系统化下载，否则可能封禁整个机构；跨用户去重会泄露"别人有访问权"（CP §2.3.3–2.3.4、HC-01/02/03/04） | 两域单向流；受限全文在用户侧执行（浏览器扩展或本地代理）；私有全文不跨用户去重；OA 四态中"用你的凭证"一态按用户私有计算；凭证端到端加密或客户端加密，不池化 | 05、08 |
| T4 | 实时性 vs 上游限速 | 用户期望"刚发的论文马上看到"（CS §2.6.5） | arXiv 每 3 秒 1 次；Crossref 列表 1/s；S2 1 RPS；OpenAlex 增量需付费；IEEE DOI 滞后 2–6 个月（AG §0.1；CS §2.1） | 先收割、后联邦；WatchKey 共享收割；日历型源在发布窗口后轮询；按新鲜度阶梯标注"预印本、已接收、已出版"；显示数据时点；付费档作为规模化杠杆 | 03、04 |
| T5 | 卡片丰富度 vs 版权 | 卡片越丰富，分拣效率越高，例如中文 TL;DR、关键图、要点（PU §0；UX §2.6） | 翻译属于演绎；Crossref 摘要的版权归出版方；只有 39.5% 的 arXiv 新记录允许展示图；OpenAlex 许可未知占 38.4%（PU §2.2.3、§2.3.3；CP LQ-01/02/05） | "共享派生"不变量；许可闸以"未知 = 拒绝"为默认；排版封面是一等公民；B 类摘要只作短片段加链接（V3）；社科与心理期刊的 AI 速读只在私有侧即时生成 | 03、07、08 |
| T6 | 滑动的数据效率 vs 拒绝心态与未经验证的形态 | 单卡二元决策给出最干净的标签，冷启动数据效率高（UX §2.1.2；SM §2.3.3） | 接受概率平均下降 27%；滑动类学术 App 采用度极低；学界对"TikTok"观感负面（UX §2.1；MK §2.2.H） | 映射 A 带中性跳过；会话后段的负反馈降权；撤销免费；列表与卡片双模式 A/B；不用"TikTok"命名 | 06、07 |
| T7 | 社交功能 vs 监管与稀疏度 | 需求原文要求点赞、留言、评价（简报 R3） | 中国的跟帖评论要求实名、审核与信用评级；欧盟 DSA 要求通知—处理机制；PubPeer 的作者回应率只有 7.5%，alphaXiv 评论稀疏（CP HC-15/17；MK §2.2.B） | 分三阶段：先做私有笔记、评分、收藏与公开列表，公开评论与计数放到 V6；公开评论要求实名锚定并经审核；公开评分用 Wilson 下界 | 06、08 |
| T8 | robots vs 文档化 API | NCBI、ORCID、OSF、eLife、HAL 的 API 文档邀请程序化使用（LS §4；AG §4 Q1） | 这些 API 主机的 robots 为 `Disallow: /`；bulk 主机（ftp.ncbi、ftp.ebi）也一样（AG 核验） | 起草统一 robots ADR（修订或补充 D-014）：站点 robots 必须遵守；文档化 API 按 ToS 与书面限额低频调用，标 `needs_confirmation`，取得书面确认前不做后台批量收割；遇挑战即停（简报 Q4） | 03、08、09 |
| T9 | PG 单栈 vs 规模与许可 | 单栈运维简单、事务一致，可承载 ≤1,000 万 work（RT §0-3） | BM25 扩展 ParadeDB 为 AGPL；ES 的 RRF 只在 Enterprise 版；1,000 万条 1024 维的 halfvec HNSW 索引粗估约 23 GB（RT §5.3） | 采用 pg_textsearch（PostgreSQL 许可）；写明升级触发条件并预留 outbox/CDC；许可以简报 B-06 为准 | 04、05 |
| T10 | LLM 的价值 vs 成本、幻觉与监管 | LLM 能生成双语 TL;DR、要点、重排与解释（PU；SR §2.6） | 过度概括率 26–73%；推理型模型幻觉率 18–23%；中国生成式 AI 服务的备案与标识；数据出境（PU §2.1.4、§2.8.3；CP HC-11/12/22） | LLM 不进热路径；选低幻觉的非推理小模型；三道闸；AI 标识双通道；境内用户默认路由到已备案模型或自托管模型（⚠ 需法务）；私有全文不发给第三方 API（PU Q11） | 03、06、08 |
| T11 | 商业化 vs NC 许可 | 可持续运营需要商业模式（MK §2.10） | CORE、ORCID 公共 API、J-STAGE、CC BY-NC 内容、MSC2020、Scholar Inbox 数据集等都限非商业（CP HC-23） | 商用开关作为架构参数：`platform.commercial=true` 时自动关闭相关来源与共享（CP DI-07）；依赖选型按最严口径 | 02、08 |
| T12 | 开源复用 vs 许可传染 | 高星项目功能完整，例如 zotero-arxiv-daily、translation-server（OSS §2.6、§2.8） | AGPL 在网络服务中有传染性；openreview-matcher 没有许可；多个 NC 权重（OSS §4；RO §3.1-19） | 按 §4.4 四级分类；AGPL 组件只作独立进程或只借思路；无许可的仓库按论文自行实现 | 02、09 |
| T13 | 覆盖广度 vs 数据质量 | 聚合器覆盖广（OpenAlex 3.27 亿条） | OpenAlex topic 有噪声，约 12% 的 work 没有 topic；OA 误判（JMLR 1%）；被引数不一致（9,262 vs 10,801）；Crossref ISSN 登记错误（AG §3-19、§4 Q10） | 建"字段 × 学科 × 源"可信度矩阵；OA 状态多源投票；卡片显示来源徽标；用户反馈校正 topic | 03、04 |
| T14 | 跨学科统一表示 vs 学科差异 | 同一向量空间便于检索与推荐统一（RO §3.1-13） | SciDocs 推荐任务上各方法几乎持平；经济学在 OpenAlex 中只有 3 个 subfield；数学公式多（math.PR 67% 的摘要含 LaTeX）；中文查询（SR §2.11；PU §2.9） | 分学科小样本评测（每学科 ≥200 条金标）后定型；主题树挂原生分类叶子（JEL、MSC、PhySH、MeSH）；中文查询侧用多语模型 | 04、06 |
| T15 | 双向匹配 vs 隐私与骚扰 | 需求原文要求双向匹配（简报 R3） | PIPL 第 27 条等要求单独同意；反向推送可能构成骚扰；阅读轨迹属于敏感信息（CP HC-18；SR §4） | ①② 先做；③ 默认关闭，需双方选择加入；每日推送预算与免打扰时段，可设"本周不看此主题"；永不暴露阅读轨迹 | 06、08 |
| T16 | 可解释 vs 隐私泄露 | why-this 能提升信任（UX §2.6.5；MK G4） | "相似研究者也喜欢"这类解释可能泄露他人行为；私有全文派生的解释会越界（UX §4；CP HC-01） | 理由码只引用本人数据或开放数据；协同类理由要求满足 k 匿名；私有派生只对本人可见 | 06、07 |
| T17 | 零摩擦上手 vs 合规门槛 | HN 反馈要求首屏零摩擦、稍后再登录（UX §2.2.4） | 需要最低年龄门槛与数据最小化；地区合规开关（CP HC-19/20/21） | 首屏用公开 CC0 样本（arXiv 元数据）；登录后再做画像与凭证；年龄中性声明 | 07、08 |
| T18 | 本地底座 vs bulk 主机的 robots 与存储 | 快照底座能省下 API 预算，并提供稳定性（AG §3-2） | OpenAlex 快照约 745 GB；ftp.ncbi 与 ftp.ebi 的 robots 为全禁（AG 核验） | 按全体用户兴趣并集导入子集；bulk 通道纳入 robots ADR 逐项登记；S3 等官方 bulk 渠道优先 | 03、05 |

---
## 6. 对 v2 设计的启示：设计输入清单（SI）与合规硬约束（HC）

> SI 编号（以及 §5 的 T、§7 的 R 与 G 编号）只在本文内有效，不占用全库的 FR/NFR/D/AC/R 编号空间；SI 供 `docs/plan/v2/01`–`09` 引用。设计文档采纳某条 SI 时，请写明"依据 SI-xx"。若证据被新的核验推翻，由本文更新并在 README 登记。"承接"列用简报 §9 的文档号：01 愿景与需求、02 架构、03 来源与语料、04 检索与路由、05 数据平台、06 推荐与匹配、07 前端、08 合规安全隐私、09 路线图。

### 6.1 设计输入清单

**A. 来源与语料（①）**

| 编号 | 设计输入 | 证据来源 | 承接 |
|---|---|---|---|
| SI-01 | Source 与 Venue 分离；多数期刊只需登记 SourceSpec 与 venue，由 `crossref_delegated` 承接元数据与最新论文，不写站点代码 | NS §3-1；SS §3-1；CS §3-3；AG §3-1 | 03 |
| SI-02 | Crossref 调用按请求类型分池设计：venue 枚举走 `/journals/{issn}/works`（单条池），禁止用全局 filter 或关键词查询去打列表池；平台用 polite 池（部署方配置联系邮箱），Metadata Plus 作为规模化杠杆 | AG §0.1、§2.2.1；NS 核验；SS §4 | 03、04 |
| SI-03 | VenueSpec 登记全部历史 ISSN（印本/电子版、新/旧）、DOI 前缀历史与平台历史；以 member、container-title、前缀三方校验归属，禁止只按 DOI 前缀路由 | NS §3-1；LS §3-12；CS §3-14 | 03 |
| SI-04 | 摘要补齐链按出版方路由，每条摘要记 `abstract_source` 与 `abstract_rights`；缺摘要时卡片降级为"标题 + venue + 作者 + 分类码"，冷启动不依赖摘要 | NS §3-2；LS §3-2；SS §3-3/§3-13；AG §2.6 | 03、07 |
| SI-05 | arXiv 改为 OAI 类目级 set，修正物理 set 前缀，用 arXivRaw 版本历史区分新稿与更新；全平台单连接，每 3 秒不超过 1 次；识别 429 与伪 200 "Rate exceeded."；按要求放置致谢语 | NS §2.3.5；CS §3-6；CP HC-06 | 03 |
| SI-06 | 生命科学以 Europe PMC、PubMed、PMC 为骨干。PMC 只用 4 条自动化通道；bioRxiv/medRxiv 以 `member:54368` 或前缀 10.64898 经 Crossref 兜底，并监控 `/details` 返回空体 | LS §2.2.1、§2.3.2、§3-1 | 03 |
| SI-07 | dblp 改用 DROPS 月度 CC0 快照加 SPARQL，停止在线访问 dblp.org（补充 D-037） | CS §0.1；AG §2.2.12；SR §0-11 | 03、09 |
| SI-08 | SSRN 降为"只取元数据 + 外链"，删除浏览器 opt-in 全文模式（新 ADR 取代 D-029/D-030 的相关部分） | SS §2.1、§3-4 | 03、09 |
| SI-09 | 只为有官方 API 或协议通道的站点写 connector，包括 aps_harvest、springer_nature_api、inspire_hep、zbmath_open、nasa_ads_scix、scoap3、numdam_oai、europe_pmc、pubmed、openreview、acl_anthology；WAF 或 robots 全禁的站点零抓取 | NS §3-4；LS §3-13；SS §3-7/§3-8 | 03 |
| SI-10 | 长尾用平台族基类承接：Atypon、Silverchair、HighWire、OJS、DSpace、EPrints、InvenioRDM，配实例注册表（baseURL、set、限速、robots 快照） | SS §2.2、§3-8；OSS §3-16 | 03 |
| SI-11 | 名录 schema 带合规字段（`tos_automation`、`ai_bot_sensitivity`、`crawl_delay_s`、`api_quota`、`tdm_policy_url`、`tdmrep`、`verified_at`），每个通道带证据 `{url, verified_at}`；策略引擎对五类信号取最严结论 | SS §3-9；CS §3-1/§3-2 | 03、08 |
| SI-12 | 漂移探针：周期比对 robots/ToS 哈希、tdmrep、挑战率、配额头、DOI 前缀/member/publisher 变化与"200 空体"；发现漂移即告警，并自动降级为"仅元数据" | NS §3-9；LS §3-11；SS §3-14；RT §12-31 | 03、08 |
| SI-13 | 最新论文默认走 Crossref `from-created-date`（带重叠窗口与标识符去重）、EPMC `FIRST_IDATE`、PubMed EDAT 与 arXiv OAI；`from-index-date` 会把结果放大约 100 倍，只作补漏；feed 只采用 robots 明确允许的，且只当新鲜度信号 | AG §0.1；NS §2.6；LS §2.9；SS §3-1 | 03、04 |
| SI-14 | CS 采用新鲜度阶梯：L0 arXiv/作者预发布 → L1 OpenReview/会议 OA 平台 → L2 DOI → L3 OpenAlex/S2；用 Crossref 的 `created` 实测各 venue 的 DOI 时滞并写回 | CS §2.6.5、§3-5 | 03、07 |
| SI-15 | 本地底座由 OpenAlex 季度快照、Crossref 年度文件、PubMed baseline 与 DROPS dblp 构成，按全体用户兴趣的并集导入子集；计量 API 只做增量与补查 | AG §3-2；RT §0-1；OSS §3-4 | 03、05 |
| SI-16 | 身份模型采用 Work/Version/Manifestation 三层，加多 ID 图（DOI、arXiv、PMID/PMCID、OpenAlex W、S2 corpusId、dblp key、ADS bibcode、zbMATH、INSPIRE、RePEc、SSRN）；预印本↔正式版的边由多源投票确定，WP↔发表版只建关系边、不合并 | LS §3-7；SS §3-5；AG §3-7；RT §7.1 | 03、05 |
| SI-17 | 主题骨架用 OpenAlex Topics（4/26/252/4,516），下挂原生分类叶子（arXiv、MeSH、JEL、MSC2020、PhySH、ACM CCS）。注意 MSC2020 为 CC BY-NC-SA、PhySH 为 CC0。约 12% 没有 topic 的 work 用本地嵌入补标；`/text` 端点已 deprecated | SR §2.11；RT §6.2；PU §2.4；NS §3-11 | 03、04、06 |
| SI-18 | 学科 L2 作为结构化主干与质量信号：INSPIRE、zbMATH（须署名）、ADS（每用户 token）、RePEc bulk、EconBiz STW、eLife Assessment、EPMC 评审标记与撤稿标记 | NS §3-4/§3-12；SS §3-6；LS §3-8 | 03、06 |
| SI-19 | 中文与区域来源以用户导入题录（RIS/BibTeX）为主，知网、万方、维普零自动化；J-STAGE、SciELO、CiNii 列 P2 | AG §2.2.28、§3-17 | 03、07 |
| SI-20 | 会议建模按学科区分：经管会议是论文的 `presented_at` 事件（ASSA、NBER SI）；理科是 `proceedings_series`；CS 是多键 venue 加演化边（`renamed_to`、`journalized_as`、`co_hosted_on`） | SS §3-11；NS §3-1；CS §3-14 | 03 |

**B. 检索、路由与多用户数据平台（②）**

| 编号 | 设计输入 | 证据来源 | 承接 |
|---|---|---|---|
| SI-21 | 先收割、后联邦：订阅、最新论文与卡片流只读本地；上游不返回 ETag，缓存用应用层 TTL，与 λ̂ 挂钩 | RT §0-1、§9、§12-1/§12-20 | 04 |
| SI-22 | SCD（查询能力、成本模型、礼貌参数、许可）是路由器与健全放宽的唯一输入；每个关键能力至少有 2 级同能力替补链 | RT §3.4、§3.5.5、§12-2/§12-7；AG §2.4.2 | 03、04 |
| SI-23 | TSRG：主题节点挂 `route_stat`；预算贪心选源，带"单项最优"兜底；用 Thompson sampling 探索，日志足够后换 GBDT pairwise；统计每周用 OpenAlex group_by（约 $0.90）或离线跑快照 | RT §3.5、§12-3/§12-4 | 04 |
| SI-24 | Query AST 覆盖 LOOKUP、SEARCH、SIMILAR、LATEST、EXPAND 五种意图。解析顺序：规则快路径 → 受约束 LLM（可选）→ 只链到库内 ID 的实体链接 → 可编辑筛选条；本地首屏投机执行；规范化查询兼作缓存键与复现凭据 | RT §4.3；OSS §3-1/§3-2 | 04、07 |
| SI-25 | 健全放宽：先化为 NNF，按极性替换，本地做残差过滤；用属性测试保证 relaxed ⊇ original；本地分析器与远端对齐，并统计"远端命中、本地拒绝"的数量 | RT §3.5.3、§12-6 | 04 |
| SI-26 | 本地混合检索：BM25 与 `halfvec` HNSW（带 iterative scan）并行召回，RRF（k=60）融合，cross-encoder 重排 top-100。BM25 扩展默认用 pg_textsearch；ES 的 RRF 与 SPLADE 官方权重不进默认路径 | RT §4、§5；§12-9/§12-12 | 04 |
| SI-27 | T1 用单 PG 18。升级触发条件：HNSW 放不进内存、p95 >300 ms，或建索引时间超出夜间窗口。升级顺序为 pgvectorscale，再到外置引擎（PG 始终为真值源） | RT §5.4、§11 | 02、04、05 |
| SI-28 | 图数据放 PG 邻接表，在线查询 ≤2 跳（递归 CTE 加 CYCLE），夜间导出 CSR 做批算；不引入独立图数据库 | RT §6.1、§6.4；OSS §3-14 | 04、05 |
| SI-29 | 去重：标识符图 union-find 物化 `cluster_id`，保留回滚日志；MinHash-LSH 加 Splink 生成候审对；弱信号不自动合并（D-007） | RT §7 | 03、05 |
| SI-30 | 用户已见集合用 Roaring 位图（1 万用户约 1.5 GB/年） | RT §7.2 | 05、06 |
| SI-31 | 用户频道编译为带引用计数的 WatchKey；日历型源按发布窗口轮询，连续型源用 Gamma-Poisson λ 在礼貌约束下注水分配；Percolator 把新论文写入 FeedInbox | RT §8.3 | 04、06 |
| SI-32 | 稳定性四件套：响应头驱动的令牌桶、重试预算（≤3 次/请求，≤10%）、AIMD（上限为书面限额）、按"源 × 端点"熔断；另设三道舱壁、截止时间与部分结果；不对同一第三方主机发对冲请求 | RT §9；AG §3-5 | 04 |
| SI-33 | Pool 多租户：`corpus` 只读；`usr` 全表 RLS（应用角色不是 owner、无 BYPASSRLS、用 `SET LOCAL`；注意 PgBouncer 事务池不支持会话级 SET/LISTEN）；`evt` 只追加、按月分区，事件 id 由客户端生成以实现幂等；另设 `ops` | RT §10.2–10.4 | 05 |
| SI-34 | 任务队列用 PG 原生方案（procrastinate，pgqueuer 为备选）；arq 处于维护模式，不用；长流程可评估 DBOS 或 absurd | RT §10.6 | 02、05 |
| SI-35 | 迁移：新建 schema，用 Python ETL（COPY）导入；v1 本地库只有 179 篇，迁移成本低；用 PG 18 | RT §10.7 | 05、09 |
| SI-36 | 每用户凭证库：把 v1 的 D-023 扩为按用户加密封装；私有全文放按用户命名空间，不跨用户去重 | OSS §3-5/§3-6；RT §10.2；CP HC-02/HC-04 | 05、08 |
| SI-37 | 限速账本的键为 source × host × 请求类 × 凭证主体（× 出口 IP）；解析 IETF RateLimit、`x-ratelimit-*`、`x-rate-limit-*`、`x-api-pool` 等响应头；OpenAlex 单独设美元预算桶 | CS §3-12；AG §3-5；RT §9.3 | 04 |
| SI-38 | robots 先行闸：HTTP 层在发出请求前检查 robots 快照并检测挑战页，由框架强制执行，不依赖调用方自觉；调研期间多次"先请求后读 robots"的偏差就是反证 | AG §3-15、§1.3.4；NS §1.4.5；CS §4；本文 §1.5 | 03、08 |

**C. 推荐与双向匹配（③）**

| 编号 | 设计输入 | 证据来源 | 承接 |
|---|---|---|---|
| SI-39 | R0 采用共享论文表示加每用户轻量线性头（Scholar Inbox 的 LR 配方；S2 的双 SVM 作基线），每次反馈即时更新；稀疏 TF-IDF 基线必须同时评测 | SR §0-1、§3.1-1；RO §2.6；MK I-5 | 06 |
| SI-40 | 表示模型候选：gte-large（MIT，与 OpenAlex semantic 同一空间）、Qwen3-Embedding-0.6B（Apache-2.0，多语）、SPECTER2（`specter2_base` 为 Apache-2.0，adapter 许可 ⚠ 待核）；统一存 256 维，默认不用 NC 模型；分学科小样本评测后定型 | SR §2.2.4；RO §3.1-6；RT §4.5；简报 Q7 | 06 |
| SI-41 | Candidate Pipeline 由 Source、Hydrator、Filter、Scorer、Selector、SideEffect 六类组件组成；召回源至少 5 路，每条候选带来源归因 | RO §3.1-1/§3.1-2；SM §2.14；SR §3.1-6；MK I-7 | 06 |
| SI-42 | ValueModel Σ V_a·P̂(a) 的 V 做版本化配置，按等贡献法初始化；"导出引用"与"收藏"的正向价值最高；负反馈分两档，差一个数量级以上，强负反馈当次会话即生效；净负分沉底 | SM §3-1/§3-2/§3-3；RO §3.1-3 | 06 |
| SI-43 | 北极星指标是每周每活跃用户的有价值阅读数，时长只作护栏；每日推送是有限批次，看完显示"今日已刷完" | SM §3-4；UX §3-7；MK I-19 | 01、06、07 |
| SI-44 | 重排：作者衰减、venue/主题配额、DPP（θ 从 0.5 起调）、10–20% 标注"探索"的槽位；新论文与新作者用贝叶斯分级曝光并设曝光下限；可见性过滤与排序分开 | SM §3-8/§3-10；RO §3.1-10/§3.1-11 | 06 |
| SI-45 | 只有绑定 impression 的反馈才能用于训练和公共热度；撤销以追加事件实现；从 R0 起记录 propensity | RO §3.1-9；SM §3-13；SR §2.8 | 05、06 |
| SI-46 | 冷启动三件套：兴趣树勾选 → 导入种子（ORCID、Zotero、BibTeX、DOI；Google Scholar 只接受手动导出后上传；dblp 走快照）→ 10–20 张主动学习校准卡（至少 5 正 3 负） | SR §2.7、§3.1-9；MK I-4；UX §3-16 | 06、07 |
| SI-47 | LLM 只做离线或近线任务：论文侧共享预处理（每月 $30–1,121，与用户数无关）、每周生成可编辑画像、每日批量 top-K 重排、懒生成解释；逐卡解释的默认形态是模板 | SR §2.6.6、§3.1-13；PU §2.6 | 06 |
| SI-48 | 双向匹配分三层：① 读者↔论文；② 论文→读者，受每用户日预算与每篇曝光下限约束，R0/R1 用批量矩阵乘，硬配额用最小费用流；③ 研究者↔研究者，互惠调和平均加容量约束，默认关闭、双方选择加入才启用 | SR §2.10、§3.1-14/§3.1-16；RO §2.9；SM §3-16 | 06 |
| SI-49 | 协同信号的隐私门槛：社会证明至少 k 个不同用户；私有库共现不入协同信号；解释不引用他人私有行为 | RO §3.1-8；SM §3-14；CP HC-01/HC-02 | 06、08 |
| SI-50 | 公开评价与个人信号分开：公开评分用 Wilson 下界并设最少评分数；作者自己的互动不计；评分者达到数百人后再启用 bridging | SM §3-12/§3-13 | 06 |
| SI-51 | 实验：小样本阶段优先用 interleaving；随机插卡并保留库存 holdout；离线相似度只作护栏，线上看收藏率、左滑率、D7 回访与完成率 | SM §3-17；SR §2.9、§3.1-17；RO §3.1-16/§3.1-20 | 06、09 |
| SI-52 | 分阶段栈 R0 → R1 → R2，R2 须满足升级阈值；1 万用户以内不做生成式端到端推荐与在线训练集群，但预留曝光日志、行为序列、可空语义 ID 与嵌入版本 | SR §3.2；RO §3.2、§3.1-17；SM §2.14.5 | 06、09 |

**D. 前端与卡片内容（④）**

| 编号 | 设计输入 | 证据来源 | 承接 |
|---|---|---|---|
| SI-53 | 三件套：今日分拣 Deck（有限批，20–30 张 ⚠ 待 Demo 验证）、双列瀑布流（探索/收藏库）、详情 Sheet；纯纵向沉浸流只作实验入口 | UX §2.1.3、§3-1 | 07 |
| SI-54 | 手势映射 A：→ 想读、← 不感兴趣、↑ 中性下一篇、↓ 撤回、单击进详情、长按出原因菜单；所有手势都有按钮与键盘等价；撤销免费且不限次 | UX §2.9.2–2.9.3、§3-2/§3-8/§3-9 | 07 |
| SI-55 | 动效参数：proj = d + v·0.1 s；阈值 0.35W / 0.2H / 800 pt/s；弹簧回弹 500/36、次卡 600/49、撤销 400/32；Motion 必须显式传参；Reduce Motion 时改为 150 ms 淡入淡出 | UX §2.3.3–2.3.5、§2.9.4 | 07 |
| SI-56 | 性能预算：DOM 中保留 3 张卡，只动画 transform 与 opacity；INP p75 ≤200 ms；提交到下一张可交互 ≤100 ms；低端设备按 5 级降级；iOS WebKit 默认约 60 fps | UX §2.4、§3-17 | 07 |
| SI-57 | v2.0 做 PWA：React 19.3 `<ViewTransition>`、Motion 13、Base UI Drawer、scroll-snap、TanStack Virtual/masonic；Expo 原生端延后到留存验证之后 | UX §2.7、§2.10 | 02、07 |
| SI-58 | 卡片 P0 字段 6 项；排版封面是一等公民；分拣卡不显示社交计数；OA 四态中"用你的凭证"一态按用户私有计算 | UX §2.6.2、§3-11/§3-13/§3-14 | 07 |
| SI-59 | 内容字段分四层：T0 取源、T1 候选批量生成 A 包、T2 详情按需生成、T3 私有生成；内容寻址缓存键含源哈希、源版本、模型、prompt 版本与策略版本 | PU §2.6.7、§3-1/§3-17 | 03、05 |
| SI-60 | "共享派生"不变量：共享卡上的 AI 内容只由可共享来源派生；许可闸以"未知 = 拒绝"为默认，多源投票后取最严结论 | PU §3-2/§3-9；LS §3-3；CP HC-05/HC-08/HC-11 | 03、08 |
| SI-61 | 生成即校验，设三道闸：规则闸、NLI 闸（MiniCheck-FT5 或 HHEM-2.1-Open）、抽样 LLM 裁判与人工审计；不过闸就降级为原文首句；建 600 篇双语黄金集作为上线门槛 | PU §2.7、§3-5/§3-21 | 03、06 |
| SI-62 | AI 标识双通道：界面显式角标，导出与分享图写入隐式元数据；S2 TLDR 标注"来自 Semantic Scholar" | PU §2.8.3、§3-19；CP HC-11/HC-24 | 07、08 |
| SI-63 | 按学科定卡片模板：CS/生医为全功能；数学/物理用 LaTeX 渲染加排版封面；社科与心理期刊在法务结论前只放元数据与受控标签，外加私有即时生成的"为我生成中文速读"；模板由 VenueSpec 或学科标签驱动 | PU §2.9、§3-23 | 07 |
| SI-64 | 事件契约先行：定义 impression、swipe_decision、save、not_interested、undo、rate、open_fulltext、batch_end 等事件，公共字段为 user/paper/session/surface/position/ts 加理由码 | UX §2.9.6、§3-21 | 05、06、07 |

**E. 开源、市场与横切治理（⑤）**

| 编号 | 设计输入 | 证据来源 | 承接 |
|---|---|---|---|
| SI-65 | 定位于五项能力的组合，加上经管 WP 的新鲜度与多用户私域合规；深度综述与问答通过集成开放服务提供，不自建 | MK §2.9、I-1、I-15 | 01 |
| SI-66 | 数据可导出、不锁定单一上游是设计约束；先例有 Researcher App、Microsoft Academic、Meta、PwC 的关停 | MK §0-6、I-16 | 01、02、05 |
| SI-67 | 依赖许可门禁：核心链路只用 Apache、MIT、BSD、PostgreSQL 许可；AGPL、SSPL、BUSL 与 NC 许可的组件只作可插拔项且默认关闭；没有 LICENSE 的仓库只借思路；模型与数据的许可单独审 | OSS §3-19/§3-20；RO §3.1-19；RT §12-30 | 02、09 |
| SI-68 | 评测从第一天开始。离线：LitSearch、SciRepEval、SciDocs、PaperFlow-Bench、olmOCR-Bench，Scholar Inbox 数据集只限非商业使用；在线：参照 arXivDigest 的 living lab | OSS §3-22；SR §2.9；MK I-20；RT §12-21 | 06、09 |
| SI-69 | 社交功能分阶段：v2.0 只做私有笔记、评分、收藏与公开列表；公开评论与计数须等实名锚定、审核、DSA 与 DMCA 流程就绪 | MK I-13；UX §3-23；CP HC-15 | 06、08 |
| SI-70 | 对外提供自有的只读 MCP：工具少而精，回显规范化查询与预算，按大纲逐节读，附引用核验 | OSS §3-21 | 02 |

### 6.2 合规硬约束清单（引用 CP §3.1 编号）

> HC 编号是 CP 文档内的**局部编号**。按简报 §5 的约定，设计文档 08 会统一登记全库唯一的 HC 编号；登记时请保留"CP HC-xx"的对照。下表是摘要，完整措辞与法源见 CP §3.1、§2.x 与参考来源。

| HC | 约束（摘要） | 对应简报原则 | 主要承接 |
|---|---|---|---|
| HC-01 | 共享与私有两个数据域，数据只能由共享流向私有；任何私有→共享的路径都禁止，包括索引、嵌入、TL;DR、特征、分享卡与日志样本 | P-02 | 05、08 |
| HC-02 | 不做跨用户复用或去重，不提供"他人已取回/有访问权"之类的信号 | P-02、P-03 | 05、06 |
| HC-03 | auth-gated 取回在用户侧执行（浏览器扩展或本地代理）；平台服务器不以平台出口代用户访问出版商 | P-03 | 02、08 |
| HC-04 | 平台不收机构密码；用户 key 只供本人使用，客户端或端到端加密，不池化（AC-0.3、AC-0.4） | P-03 | 05、08 |
| HC-05 | 按篇许可白名单：可共享的只有 CC BY、BY-SA、CC0 与公有领域；NC 只在非商业部署下可用；ND 只能原样使用；许可未知的一律不可共享 | P-02 | 03、08 |
| HC-06 | arXiv：元数据与摘要（CC0）可缓存并全文展示；e-print（PDF、源文件、抽取的图）不得存储与提供，CC 许可者除外；全平台每 3 秒不超过 1 次、单连接；批量走 OAI、S3 或 Kaggle；不暗示 arXiv 背书 | P-04、P-05 | 03 |
| HC-07 | 字段级权利标注：`source`、`license`、`rights_class`（M1–M25）、`fetched_at`、`display_level_max`（V0–V4）、`shareable`、`commercial_ok`、`attribution_text` | P-02 | 03、05 |
| HC-08 | 摘要分级展示：A 类（CC0 或开放）最高到 V4；B 类（有版权但公开分发）最高 V3；C 类（出版商 API 个人用途）不进共享层；优先展示 arXiv 摘要 | P-02；简报 §6.6 | 03、07 |
| HC-09 | 图片门控：只展示 M11 类（CC 许可）图片，按 TASL 规则署名；ND 许可不裁剪、不做 AI 重绘；许可未知则不展示图 | 简报 §6.5-4 | 07 |
| HC-10 | 对每个上游只用一个平台身份，全局调度；禁止多 key、IP 轮换、住宅代理与 UA 伪装；用请求合并、共享缓存，优先快照 | P-04 | 03、04 |
| HC-11 | LLM TL;DR 治理：(a) 共享版的输入只取自共享层；(b) 检查 Content-Signal `ai-input`、TDMRep 与 robots 中的 AI 规则；(c) IEEE 与 Elsevier API 的内容不进共享 LLM；(d) 显式加隐式、机器可读的标识；(e) 限长度、不逐字复制、不替代摘要、始终附原文链接；(f) 不把生成内容归到作者名下 | P-07；简报 §6.6 | 03、06、07 |
| HC-12 | 中国境内使用 LLM 的条件：已备案模型、属地登记、展示模型名与备案号 | Q2 | 08 |
| HC-13 | 推荐透明与控制全球统一：公示原理、why-this、即时生效的非个性化模式、标签可查看可删除、过滤违法关键词、申诉渠道 | P-06 | 06、07 |
| HC-14 | 算法合规工程化：影响评估记录保存 ≥3 年；日志保存 ≥6 个月；备案材料可导出 | P-06、P-08 | 05、08 |
| HC-15 | UGC 分阶段：第一阶段只有私有反馈；公开评论与计数须先具备实名（中国）、审核、举报、DSA 通知—处理与理由说明、DMCA 代理、信用评级、反欺诈与 AI 声明 | Q6；简报 §6.4-6 | 06、08 |
| HC-16 | 不允许公开上传或转载全文，评论中不得附 PDF；个人上传只存私有域（见 LQ-15） | P-02 | 06、08 |
| HC-17 | 学术评论规范：只陈述可核验的事实，提供作者回应与申诉渠道 | 简报 §6.4-6 | 06 |
| HC-18 | 双向匹配须单独同意：默认关闭、可撤回、不涉及敏感信息、尊重作者拒绝（PIPL 第 27 条等） | Q5 | 06、08 |
| HC-19 | 设最低年龄（建议 ≥16 岁），年龄声明保持中性，不做面向儿童的功能 | — | 08 |
| HC-20 | 数据最小化与留存矩阵；日志 ≥6 个月；画像可删除；注销账号时删除私有全文及其派生物 | P-06 | 05、08 |
| HC-21 | 地区合规开关：中国的 ICP、等保、安全评估、算法备案与生成式 AI 登记，须在开启公开评论、LLM 或个性化之前完成；欧盟代表人 | Q2 | 08、09 |
| HC-22 | 跨境：中国用户个人信息默认境内存储；每年少于 10 万人的豁免档另行评估 | Q2 | 05、08 |
| HC-23 | 商用开关门控"需许可或限非商业"的来源：CORE、ORCID 公共 API、J-STAGE、CC BY-NC 内容 | Q1；B-06 | 03、08 |
| HC-24 | 按出处自动渲染署名：NLM 致谢与时效说明、NCBI 免责声明、"Semantic Scholar"、CORE、CC TASL | P-06 | 07 |
| HC-25 | 出版商 TDM 的输出规则：只输出事实与聚合结果；Elsevier 片段 ≤200 字符并附 DOI；不输出图；限非商业 | P-02、P-03 | 03、06 |
| HC-26 | v1 的反对抗红线：不接盗版源（AC-0.1）、不解 CAPTCHA（AC-0.2）、遇挑战即标 BLOCKED、不自动化 Google Scholar、不做任何规避 | P-04 | 03 |
| HC-27 | IEEE、ACS、ACM：平台层不用 IEEE API；不对 ACS 做任何自动化；不自动访问 ACM DL（D-020/D-024）；三者的元数据经 Crossref 获取 | P-05 | 03 |
| HC-28 | 可审计：记录许可出处与 FetchLog，定期审计，监测条款变更 | P-05、P-08 | 03、08 |

**相关设计启示与待法务问题**（均见 CP §3.2、§4.1）：
- **DI-01** 权利引擎作为一等组件。
- **DI-02** 取回采用"用户侧代理 + 平台编排"，或 OpenURL/WAYFless 链接。
- **DI-03** 全局模型只用共享底座与聚合、去标识的行为数据。
- **DI-07** 商用开关是架构参数。
- **DI-09** 数据驻留分区。
- 法务须确认的问题：
  - LQ-01 摘要可展示的片段长度 N；
  - LQ-02 B 类摘要能否进入内部索引与嵌入；
  - LQ-03 何为"商业"；
  - LQ-04 ND 许可作品的摘要与裁剪是否构成演绎；
  - LQ-05 对有版权的摘要做 LLM TL;DR 的门槛；
  - LQ-07 服务器代取、用户侧代理与 OpenURL 三种架构的取舍；
  - LQ-10 中国境内私有点赞是否算"发表信息"；
  - LQ-13 OpenAlex 多 key 的边界；
  - LQ-15 用户私有 PDF 上传；
  - LQ-17 Content-Signal 如何映射到嵌入用途。

---

## 7. 未决问题、风险与补充调研建议

### 7.1 待用户拍板的问题（对应简报 §8 的 Q1–Q7）

| # | 问题 | 调研证据 | 建议 |
|---|---|---|---|
| Q1 | 是否商业化 | CORE、ORCID、J-STAGE、CC BY-NC、MSC2020、Scholar Inbox 数据集等受非商业限制（CP HC-23）；各商业模式的适配度（MK §2.10） | 维持简报默认（非商业）。把商用开关做成配置并写进 ADR，届时切换无需改架构 |
| Q2 | 是否面向中国大陆公众运营 | 公开评论、个性化与 LLM 会依次触发安全评估、算法备案与生成式 AI 登记；数据须境内存储（CP §2.5.1、HC-12/21/22） | 维持默认（否），但 HC-13 的透明与控制能力全球统一内建 |
| Q3 | 是否购买 OpenAlex Member/Member+ 或 Crossref Plus | 免费 key 每日 $1，约可做 1 万次列表或 1,000 次搜索；增量过滤需 Member+（$10,000/年）；Crossref 公共池列表只有 1/s（AG §2.3.3、§4 Q6） | 维持默认（否）。在 09 路线图中写明触发条件，例如每日联邦查询超过免费额度 80%，或新鲜度 SLA 不达标 |
| Q4 | robots 与文档化 API 冲突时的处置 | NCBI、ORCID、OSF、eLife、HAL、Zenodo、arXiv export、PubChem，以及 ftp.ncbi/ftp.ebi bulk（AG 核验；LS §4；NS §4） | 维持保守默认。统一 ADR 逐站列出，并附书面确认的邮件模板 |
| Q5 | 双向匹配先做哪种 | 读者↔论文与论文→读者已有成熟工具链；研究者↔研究者须单独同意（SR §2.10；CP HC-18） | 维持默认。③ 上线前先做用户调研，确认真实需求（MK §4.1） |
| Q6 | 评论是否公开 | 中国跟帖评论的实名与审核义务、欧盟 DSA 流程；学术评论稀疏（CP §2.6；MK §2.2.B） | 维持默认（V6 再开放） |
| Q7 | 表示模型选型 | gte-large（MIT）、Qwen3-Embedding-0.6B（Apache-2.0）、SPECTER2（HF `specter2_base` 为 Apache-2.0；proximity adapter 模型卡没有许可字段，⚠ 待核）；Scholar Inbox 实验中 AUC 只差 0.39 个百分点（RO §3.1-6；RT §4.5） | 简报中"SPECTER2 许可待核"可更新为"base 已确认 Apache-2.0，adapter 待核"；V1 里程碑做分学科评测 |

### 7.2 主要风险

| # | 风险 | 影响 | 缓解 | 证据 |
|---|---|---|---|---|
| R-01 | 机构级封禁：用户或平台触发 SERU、EZproxy 规则或出版商条款，导致整个机构的访问被暂停 | 用户失去全文访问，也伤害平台声誉 | 全文只在用户侧、由用户触发、单篇、低频获取；不预取；平台出口不代取 | CP RK-01、§2.3.4 |
| R-02 | 条款漂移：arXiv 独立后调整 ToU；SSRN 平台调整；IOP 自 2026-07 起机器访问须签协议；dblp 的 robots | 通道失效或违规 | 漂移探针（SI-12）、证据时效降级、季度复核 | CP RK-02；NS 核验；CS §0.1 |
| R-03 | 许可元数据缺失：OpenAlex 许可为 null 的语义混杂；Crossref 同一篇有多条 license | 许可闸误放行或误拒 | 多源投票、取最严结论、未知即拒；把许可闸精度列为 P0 验收项 | CP RK-04；PU Q6 |
| R-04 | LLM 幻觉与错误归因 | 误导读者，产生法律责任 | 三道闸、明确标识、不替代原文、不把生成内容归给作者 | CP RK-06；PU §2.1.4 |
| R-05 | 上游关停或收费（OpenAlex、S2、Crossref） | 覆盖与新鲜度下降 | 本地底座、多源替补链、预算桶、数据导出 | CP RK-10；MK §0-6 |
| R-06 | 推荐偏差：信息茧房、马太效应、位置偏差 | 学术多样性受损，评估失真 | DPP、配额、探索槽、propensity 日志、interleaving | SR §4；SM §4 |
| R-07 | 小样本隐私：社会证明、解释或流行度统计反推出个人行为 | 隐私事故 | k 匿名阈值、私有派生只对本人可见、解释只引用本人数据 | RO §4；SM §4 |
| R-08 | 形态风险：滑动形态不被研究者接受 | 留存不达标 | 列表与卡片双模式 A/B；以有价值阅读为北极星 | MK §4.2；UX §4 |
| R-09 | 依赖健康度：Kùzu 归档、arq 维护模式、use-gesture 与 vaul 停更、sqlite-vec 仍为 pre-v1 | 被迫迁移 | 依赖放在内部接口之后，锁定版本，配契约测试 | RT §13；UX §4；OSS §3-20 |
| R-10 | 中国合规成本（若将来改变 Q2） | 上线延迟 | 地区开关（HC-21）；境内模型路由 | CP RK-05；PU Q14 |
| R-11 | 分学科的数据质量与表示质量不均（化学、心理、中文） | 推荐效果参差 | 分学科金标、可信度矩阵、用户导入 | AG §3-19；SR §4 |
| R-12 | 容量估算偏差：厂商基准互相矛盾，percolate 在 10⁵ 个订阅时的成本未知 | 性能不达标 | 在目标硬件上用自有语料压测（RT §12-24） | RT §5.3、§13 |

### 7.3 调研缺口与建议的补充调研

| # | 缺口 | 影响的设计 | 建议的补充调研（方法） | 优先级 |
|---|---|---|---|---|
| G-01 | 缺少用户之声：没有 Reddit、X、知乎、小红书上研究者对卡片流与 AI 摘要的真实反馈 | 01、07 | 定性调研，加上 Demo 可用性测试（5–8 人 × 3 学科） | 高 |
| G-02 | 法律问题 LQ-01…LQ-18 没有法务意见 | 03、07、08 | 按 CP §4.1 的清单委托法务；先解决 LQ-01、LQ-02、LQ-05、LQ-07 | 高 |
| G-03 | robots 与文档化 API 的冲突没有书面确认：NCBI、ORCID、OSF、eLife、HAL、Zenodo、EBI/NCBI bulk、PubChem；另有 OpenReview 服务账号、dblp 的真实意图 | 03、08 | 按统一 ADR 的模板逐站发函，并记录回复 | 高 |
| G-04 | 规模化时的配额与费用不明：Crossref polite 池容量、Metadata Plus 价格、OpenAlex 预算、S2 的 key 与商用书面许可 | 03、04、09 | 在 T1 负载模型下做配额仿真，并正式询价 | 中 |
| G-05 | 名录覆盖不全：地学（AGU、EGU/Copernicus、GSA）、材料、化学开放分类、心理学会议（Psychonomics、SPSP、CCN）、ISMB/RECOMB、MLSys/RSS/ECCC/now/SIAM 的枚举方式、中文生态（含 Gitee 开源）、OpenDOAR（⚠） | 03 | 按本文 §3 的列做补充调研，每个缺口 1 篇短文 | 中 |
| G-06 | 分学科的表示质量：数学公式、经济 JEL 粒度、化学实体、中文查询 | 04、06 | 各学科建 ≥200 条金标，评测 gte-large、Qwen3-Embedding、SPECTER2、BM25 | 高 |
| G-07 | 交互参数未验证：每批张数、单卡决策时长、iOS PWA 帧率、映射 A/B/C | 07 | 在 Demo 中埋点做 A/B，并在 iOS 与 Android 真机测帧率 | 高 |
| G-08 | 学术场景下 ValueModel 的 V 没有参考值 | 06 | 小规模实验加"值得读吗"问卷校准 | 中 |
| G-09 | LLM 在科学文本上的忠实度、延迟与本地模型吞吐未实测 | 03、06 | PoC：在黄金集上分学科报告，测 P50/P95 延迟，测 vLLM/SGLang 在 L4/H100 上的吞吐 | 中 |
| G-10 | 出口 IP 影响了 WAF 与挑战的观察结论 | 03 | 在校园网与用户本地网络复测 auth 族站点 | 中 |
| G-11 | 一批条款只有二手证据：ACS、SIAM、De Gruyter 的 TDM；AMS 的 5 年墙；WSP 的下载阈值；APA、SAGE、PNAS、AAAS 的政策页；Research Square API；PubTator3/iCite 的限速；Europe PMC 的数值限速 | 03、08 | 人工阅读条款原文或发函确认，再录入名录证据字段 | 中 |
| G-12 | 市场数字有 ◐：Connected Papers 定价、SciSpace、Scholarcy 等；Scholar Inbox 数据集在商用场景下能否使用 | 01 | 设计阶段不引用 ◐ 数字；需要时再补核 | 低 |
| G-13 | 标识与监管细则：GB 45438—2025 正文、欧盟《AI 生成内容透明度行为准则》、DSA 的中小企业豁免边界、最低年龄 | 07、08 | 法规原文阅读与法务确认 | 中 |
| G-14 | 研究者↔研究者匹配的真实需求与滥用场景 | 06 | 用户访谈；参照 RECON 与 Hinge 的边界设计 | 低 |
| G-15 | 引文边的覆盖差异（OpenAlex、Crossref、S2、OpenCitations）没有量化 | 04、06 | 抽样比较四源的引文边 | 低 |
| G-16 | 时点事实会过期（arXiv、bioRxiv、PMC、OpenAlex 计费、Crossref 分池、X 参数、价格表） | 全部 | 按季度重核；在 README 维护"快变事实清单" | 持续 |

---
## 8. 与设计简报的一致性核对

> 对照对象：[docs/plan/v2/00-design-brief.md](../plan/v2/00-design-brief.md)（updated 2026-09-27）。结论分三类：
> - **一致**：调研证据支持简报裁决；
> - **建议细化**：方向一致，但调研给出了简报未写明的约束或参数；
> - **需复核**：调研证据与简报措辞存在出入，需主 agent 裁定。
>
> 本节只提出建议，不改动简报。

| 简报条目 | 调研证据 | 结论 | 说明 |
|---|---|---|---|
| §2 产品定义、北极星 | MK I-1、§2.9；SM §3-4 | 一致；建议细化 | SM 定义的"有价值阅读"是收藏、≥4 星、导出引用三项，简报另加了"打开全文"。建议 06 注明：`open_fulltext` 只用于本人模型与北极星统计，不进入公共热度，否则会暴露"有人拥有访问权"（CP HC-02） |
| B-01 PG18 单栈 | RT §0-3、§5.4、§11 | 一致；建议细化 | BM25 扩展按 B-06 默认选 pg_textsearch（PostgreSQL 许可，仅支持 PG 17/18），ParadeDB（AGPL）只作可选 |
| B-02 platform/personal 同码 | MK §2.9；RT §11 T0 | 一致 | OSS §6.1 的 sqlite-vec 与 LanceDB 本地模式在 v2 服务端不再需要，只在保留 v1 离线版时才有意义 |
| B-04 T1 档位 | RT §11 T1（≤1,000 用户、≤1,000 万 work、≤10⁷ 事件/日） | 一致 | 容量须在目标硬件上用自有语料压测（RT §12-24） |
| B-05 技术栈 | UX §2.10；RT §10.6 | 一致；建议细化 | Motion 的默认弹簧不收敛（ζ=0.5），Deck 必须显式传参（UX 核验）；procrastinate 的 LISTEN 需要直连或会话池（RT §10.6） |
| B-06 许可门禁 | OSS §6；RO §3.1-19；SR §0-4 | 一致；建议细化 | §4.4 的"许可与 B-06 冲突"清单可作为 09 的依赖白名单与黑名单初稿；MSC2020（NC-SA）与 zbMATH（BY-SA）作为标签或数据时同样受门禁约束 |
| P-01 先收割、后联邦 | RT §0-1、§12-1 | 一致 | 上游不返回 ETag，这进一步支持本地优先 |
| P-02 三域、`display_scope`、派生继承最严 | CP HC-01/05/07/08；PU §3-2；LS §3-3 | 一致；建议细化 | ① `public_shared` 的派生输入须排除 B 类摘要（出版方版权、公开分发），直到 LQ-05 有结论（CP HC-08、HC-11a）；② 08 须定义 `display_scope` 与 CP 展示级别 V0–V4、权利类别 M1–M25 的映射，例如 V4/V3 ↔ `public_shared`、V1 ↔ `link_only` |
| P-03 用户自有凭证，"在其本人会话内单篇取回" | CP HC-03、LQ-07；CP §2.3.3–2.3.4 | **需复核** | HC-03 要求执行位置在用户侧（浏览器扩展或本地代理），平台服务器不以平台出口代为访问。若"本人会话"指服务器持用户 cookie 代取，仍与 HC-03 冲突。建议 02 与 08 明确执行位置，并把 LQ-07 列为法务问题 |
| P-04 全局礼貌 | CP HC-10；RT §9；AG §3-5 | 一致 | 限速账本的键建议补上出口 IP（SI-37） |
| P-05 最严者为准，`needs_confirmation` | CS §3-2；SS §3-9；NS §4 | 一致 | — |
| P-06 可解释、可控、可导出 | CP HC-13/HC-20；UX §3-15；MK I-16 | 一致 | DSA 27(3) 要求能从信息流直达设置（UX 核验） |
| P-07 LLM 不进热路径 | SR §3.1-13；PU §3 | 一致；建议细化 | 补两点：境内用户的 LLM 路由到已备案模型（CP HC-12，Q2 为"否"时可暂缓）；私有全文默认不发给第三方 LLM API（PU Q11） |
| P-08 评测先行 | SR §2.9；RO §3.1-16；SM §3-17；RT §12-21 | 一致 | 小样本阶段优先用 interleaving |
| P-09 可降级 | RT §3.5.5、§12-7 | 一致 | — |
| §5 术语 Deck/Batch（20–30 张） | UX §3-7 | 一致（⚠） | 张数是待 Demo 验证的假设 |
| §6.1-2 最新论文用 `from-created-date` / `from-index-date` | AG §0.1（`from-index-date` 放大约 100 倍） | 建议细化 | 以 `from-created-date` 加重叠窗口为主，`from-index-date` 只补漏并做标识符去重（SI-13） |
| §6.1-2 本地底座含 PubMed baseline 等 bulk | AG 核验：ftp.ncbi 与 ftp.ebi 的 robots 均为 `Disallow: /` | 建议细化 | 简报 §7-2 的 robots ADR 须明确把 bulk 主机纳入逐站登记范围 |
| §6.1-7 状态枚举 | 本文 §3.1 | 一致；建议细化 | 建议允许 `metadata-only（Px）` 写法，区分登记优先级 |
| §6.2-2 TSRG："贪心有 (1−1/e) 近似；源数 <50 时可精确枚举校验" | RT §3.5.2、§3.5.6 | **需复核（措辞）** | RT 的原意：只有基数约束时贪心才有 1−1/e；带成本的预算版本要加"单项最优"兜底才有常数近似。"精确枚举可行"针对的是候选源 <20（判断）；"≤50 个源"指的是路由计算在毫秒级 |
| §6.2-4 RRF（k=60 起） | RT §4.2 | 一致 | 若外置 Qdrant，须显式设 k，因为它的默认值为 2 |
| §6.3-2 公开评论须实名锚定（ORCID 或机构邮箱） | CP HC-15、§2.6 | 建议细化 | 在 Q2 为"否"的前提下可行；若面向中国大陆，跟帖评论须后台实名，ORCID 或机构邮箱不一定满足 |
| §6.3-3 凭证库"主密钥由部署方 KMS 或 keyring 管理" | CP HC-04（用户 key 客户端或端到端加密）；OSS §3-5 | **需复核** | 服务端 KMS 封装与客户端加密是两种信任模型。建议 08 比较两案，至少对 auth-gated 凭证采用客户端或端到端加密 |
| §6.4-1 召回源含开放热度信号 | CS §3-11；MK I-7 | 一致 | HF API 匿名额度为 500 次/5 min；X API 按次计费；各源条款须逐一核验 |
| §6.4-3 ValueModel 与负反馈两档 | SM §3-1/§3-3；RO §3.1-3 | 一致 | — |
| §6.4-5 双向匹配三层 | SR §2.10；CP HC-18 | 一致 | — |
| §6.4-6 社会证明 k | SM §4；RO §3.1-8 | 一致（待定参数） | k 的初值与是否加差分隐私，仍是 SM §4 的开放问题 |
| §6.5 前端 | UX §2.9–2.10 | 一致 | — |
| §6.6 内容理解 | PU §2.8、§3 | 一致；建议细化 | 补两点：S2 TLDR 作零成本兜底与对照（ODC-BY，须署名；覆盖按学科在 0–98%）；社科与心理期刊采用"元数据 + 私有速读"模板（PU §3-23） |
| §7 待起草的 ADR（8 项） | 各篇 §3/§4 | 一致；建议补充 | 另建议 5 项 ADR 候选：① 许可闸与商用开关（CP DI-07）；② 受限全文的执行位置（HC-03、LQ-07）；③ LLM 路由、AI 标识与数据出境（HC-11/12/22）；④ OpenReview 平台服务账号（CS §3-9）；⑤ GROBID 增加 `teiCoordinates=figure`（design/12 变更，PU §3-22） |
| §8 Q7"SPECTER2 许可待核" | RO §2.5 与核验；RT §4.5 | 建议更新 | `specter2_base` 已确认为 Apache-2.0；`allenai/specter2` 的 proximity adapter 卡片没有许可字段，⚠ 待核 |

---

## 9. 参考来源

> 本文的事实均转引自下列调研文档。除另注外，调研与核验日期均为 **2026-09-26（UTC）**。一手来源的完整清单见各篇"参考来源"与"核验记录"。

### 9.1 本目录调研文档（全部经对抗式核验，核验日期 2026-09-26）

1. [sources/natural-sciences.md](sources/natural-sciences.md)——理科来源；附件见 `sources/natural-sciences/`
2. [sources/life-sciences-psychology.md](sources/life-sciences-psychology.md)——生命科学与心理学来源
3. [sources/social-sciences-econ-fin-mgmt.md](sources/social-sciences-econ-fin-mgmt.md)——经管来源
4. [sources/cs-ai.md](sources/cs-ai.md)——CS/AI 来源
5. [sources/aggregators-repositories.md](sources/aggregators-repositories.md)——L2 聚合与仓库；附件见 `sources/aggregators-repositories/`
6. [oss/paper-acquisition-and-search-oss.md](oss/paper-acquisition-and-search-oss.md)——获取与检索开源；附件见 `oss/paper-acquisition-and-search-oss/`
7. [oss/recommendation-oss.md](oss/recommendation-oss.md)——推荐开源
8. [market/startups-and-products.md](market/startups-and-products.md)——市场与竞品
9. [algorithms/social-media-recsys.md](algorithms/social-media-recsys.md)——社媒推荐算法
10. [algorithms/scholarly-recommendation-and-matching.md](algorithms/scholarly-recommendation-and-matching.md)——学术推荐与双向匹配
11. [algorithms/retrieval-routing-indexing.md](algorithms/retrieval-routing-indexing.md)——检索、路由、索引与数据平台
12. [ux/card-feed-interaction.md](ux/card-feed-interaction.md)——卡片流交互
13. [algorithms/paper-understanding-and-card-content.md](algorithms/paper-understanding-and-card-content.md)——卡片内容生成；附件见 `algorithms/paper-understanding-and-card-content/`
14. [compliance/multi-user-platform-compliance.md](compliance/multi-user-platform-compliance.md)——多用户合规；附件见 `compliance/multi-user-platform-compliance/`

### 9.2 最承重的一手来源（经括注的调研文档核验，访问与核验日期 2026-09-26）

**上游接口、限速与计费**
- Crossref，*Announcing changes to REST API rate limits*：https://www.crossref.org/blog/announcing-changes-to-rest-api-rate-limits/ ；社区公告 https://community.crossref.org/t/updates-to-rest-api-rate-limits/14872 （AG）
- Crossref，*Metadata Retrieval*（事实 CC0，摘要版权保留）：https://www.crossref.org/documentation/retrieve-metadata/ （AG、PU）
- Crossref，*2026 public data file now available*：https://www.crossref.org/blog/2026-public-data-file-now-available/ （AG）
- OpenAlex 定价与示例成本：https://help.openalex.org/access/pricing/ ；https://help.openalex.org/access/example-costs/ （AG、PU、RT）
- OpenAlex 快照、works 字段（摘要倒排索引的法律说明）与 Topics：https://help.openalex.org/access/snapshot/ ；https://help.openalex.org/data/works/attributes/ ；https://help.openalex.org/data/topics （AG、PU、RT、SR）
- Semantic Scholar API License Agreement：https://www.semanticscholar.org/product/api/license （AG、CP、PU）
- arXiv API Terms of Use、许可说明、robots 与 OAI-PMH：https://info.arxiv.org/help/api/tou.html ；https://info.arxiv.org/help/license/index.html ；https://arxiv.org/robots.txt ；https://oaipmh.arxiv.org/oai （NS、CS、PU、CP）
- arXiv，*arXiv is becoming an independent nonprofit*：https://blog.arxiv.org/2026/04/02/arxiv-is-becoming-an-independent-nonprofit/ （NS、CP）
- dblp robots、DROPS 快照与 SPARQL 下载：https://dblp.org/robots.txt ；https://drops.dagstuhl.de/entities/artifact/10.4230/dblp.xml.2026-09-01 ；https://sparql.dblp.org/download/ （CS、AG）
- PMC 开发者工具（自动化通道）：https://pmc.ncbi.nlm.nih.gov/tools/developers/ （LS、CP）
- NCBI 与 EBI 的 robots：https://eutils.ncbi.nlm.nih.gov/robots.txt ；https://ftp.ncbi.nlm.nih.gov/robots.txt ；https://ftp.ebi.ac.uk/robots.txt （AG、LS）
- bioRxiv API：https://api.biorxiv.org/ （LS）
- OSF 与 ORCID API 主机的 robots：https://api.osf.io/robots.txt ；https://pub.orcid.org/robots.txt （AG、LS、SS、SR）
- SSRN Terms of Use 与 2026-04-13 战略更新：https://www.ssrn.com/index.cfm/en/terms-of-use/ ；https://blog.ssrn.com/2026/04/13/ssrn-strategic-update-renewed-focus-on-core-research-sharing-mission/ （SS）

**出版商 TDM 与许可**
- Elsevier TDM 政策：https://www.elsevier.com/about/policies-and-standards/text-and-data-mining （NS、SS、CP）
- Springer Nature TDM：https://www.springernature.com/gp/researchers/text-and-data-mining （NS、LS、CP）
- IEEE API Terms of Use：https://developer.ieee.org/API_Terms_of_Use2 （CS、CP）
- Initiative for Open Abstracts：https://i4oa.org/ （AG、CP、PU）
- CC BY 4.0 Legal Code（Adapted Material 含翻译）：https://creativecommons.org/licenses/by/4.0/legalcode.en （CP、PU）
- Cloudflare，*Content Signals Policy*：https://blog.cloudflare.com/content-signals-policy/ （CP）

**法规**
- 《人工智能生成合成内容标识办法》：https://www.cac.gov.cn/2025-03/14/c_1743654684782215.htm （CP、PU）
- 《互联网信息服务算法推荐管理规定》：https://www.cac.gov.cn/2022-01/04/c_1642894606364259.htm （CP、SM、UX）
- EU AI Act 第 50 条：https://artificialintelligenceact.eu/article/50/ （CP、PU）
- EU Digital Services Act（Reg. (EU) 2022/2065）：https://eur-lex.europa.eu/eli/reg/2022/2065/oj/eng （CP、SM、UX）
- EU DSM Directive（Dir. (EU) 2019/790）：https://eur-lex.europa.eu/eli/dir/2019/790/oj/eng （CP）

**算法、模型与工程**
- xai-org/x-algorithm（Apache-2.0；参数固定在 commit 4c5cfe8）：https://github.com/xai-org/x-algorithm ；https://github.com/xai-org/x-algorithm/blob/4c5cfe8f07f1c76d4f04277e803f20e6039f5191/home-mixer/params/param.rs （RO、SM）
- Scholar Inbox（arXiv:2504.08385，ACL 2025 Demo）：https://arxiv.org/abs/2504.08385 （RO、SR、MK）
- The Semantic Scholar Open Data Platform（arXiv:2301.10140，§3.4.5 Research Feeds）：https://arxiv.org/abs/2301.10140 （RO、SR、PU）
- Pronk & Denissen，*A Rejection Mind-Set*：https://doi.org/10.1177/1948550619866189 （UX）
- 模型卡：https://huggingface.co/allenai/specter2_base ；https://huggingface.co/thenlper/gte-large ；https://huggingface.co/Qwen/Qwen3-Embedding-0.6B （RO、SR、RT）
- pgvector、pg_textsearch、ParadeDB、procrastinate：https://github.com/pgvector/pgvector ；https://github.com/timescale/pg_textsearch ；https://github.com/paradedb/paradedb ；https://github.com/procrastinate-org/procrastinate （RT、OSS）
- openreview-matcher（无 LICENSE）与 findpapers：https://github.com/openreview/openreview-matcher ；https://github.com/jonatasgrosman/findpapers （OSS、SR）
- React 19.3 发布说明与 Motion 拖拽文档：https://react.dev/blog/2026/09/09/react-19-3 ；https://motion.dev/docs/react-drag （UX）
- Google Scholar，*Quick Read*（2026-08-25）：https://scholar.googleblog.com/2026/08/quick-read-see-how-paper-answers-your.html （MK、PU、SR）

### 9.3 仓库内文档

- [v2 设计决策简报](../plan/v2/00-design-brief.md)（上游约束，本文 §8 与之对照）
- [决策日志](../plan/decision-log.md)（D-001、D-002、D-007、D-014、D-020、D-021、D-023、D-024、D-029、D-030、D-035、D-037 等，本文只引用编号）
- [v1 全文抽取设计](../archive-v1.md#docs-design-12-fulltext-extract-md)（GROBID 参数现状，见 PU §1.3）
- [v1 adapter 设计目录](../archive-v1.md#docs-design-adapters-readme-md)
