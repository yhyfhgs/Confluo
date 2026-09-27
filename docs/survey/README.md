---
title: Survey 目录：v2 重新设计调研归档
status: draft
owner: opus5.5-survey
updated: 2026-09-26
---

# Survey 目录：v2 重新设计调研归档

## 1. 目录说明

本目录归档 Paper Crawler **v2 重新设计**的调研阶段成果，共 14 篇主题调研和 1 篇综合，时点为 2026-09-26（UTC）。它是设计阶段（`docs/plan/v2/01`–`09`）的证据层：

- [00-survey-synthesis.md](00-survey-synthesis.md) 把 14 篇调研合成为设计输入。内容包括：
  - 候选来源总表（187 行）；
  - 按五项需求的结论；
  - 跨主题张力；
  - SI-01…SI-70 设计输入；
  - HC 对照表；
  - 调研缺口。
- [v2 设计决策简报](../plan/v2/00-design-brief.md) 是主 agent 的架构裁决，以本目录为依据。简报与调研的逐条核对见综合 §8。
- 本目录只放调研与证据，不放设计与实现。设计文档引用本目录的结论，本目录不反向引用设计的定稿内容（综合 §8 的核对表除外）。

**目录结构**

```text
docs/survey/
├── README.md                     本文件
├── 00-survey-synthesis.md        综合：v2 重新设计的输入与结论
├── sources/                      ① 来源调研（L1 分学科 4 篇 + L2 聚合 1 篇）
├── oss/                          ⑤ 开源项目调研（获取/检索 1 篇 + 推荐 1 篇）
├── market/                       ⑤ 初创与产品调研
├── algorithms/                   ②③④ 算法与技术调研（社媒推荐、学术推荐、检索路由、卡片内容）
├── ux/                           ④ 卡片流交互调研
└── compliance/                   横切：多用户平台合规调研
```

附件（请求台账、实测数据、仓库指标）放在与文档**同名的子目录**中，文件名带日期后缀（`*-2026-09-26.*`）。

## 2. 文档一览

"核验状态"列的格式为"核验断言数 / 修正数 / 删除数"。前 6 篇的统计取自工作流核验回执，其余取自文内核验记录（部分由综合复算）。口径说明见综合 §1.3。

| 路径 | 主题 | 核验状态 | 要点 |
|---|---|---|---|
| [00-survey-synthesis.md](00-survey-synthesis.md) | 调研综合：v2 重新设计的输入与结论 | 综合文档，不单独核验；事实转引自下列已核验文档，未发新的外部请求 | 候选来源总表（187 行，含学科覆盖统计）、五项需求结论、18 项张力与取舍、SI-01…SI-70、HC-01…HC-28 对照、16 项调研缺口、与简报的一致性核对 |
| [sources/natural-sciences.md](sources/natural-sciences.md) | 理科（数学/物理/化学，材料与地学简述）出版商、预印本与平台 | 已核验 2026-09-26：63 / 13 / 0 | Crossref 可枚举 115 刊，但摘要缺口大（Elsevier 为 0，ACS 约 0.1）；arXiv OAI 类目级 set，物理 set 须加 `physics:` 前缀；APS Harvest、SN API、INSPIRE、zbMATH、SCOAP3 为合规通道；IOP、ACS 等站点零自动化；MSC2020 为 CC BY-NC-SA |
| [sources/life-sciences-psychology.md](sources/life-sciences-psychology.md) | 生命科学与心理学来源 | 已核验 2026-09-26：54 / 13 / 0 | Europe PMC、PubMed、PMC 为骨干；心理学的 Crossref 摘要为 0%；openRxiv 启用新前缀 10.64898，`/details` 返回空体；PMC 只允许 4 条自动化通道；共享层按条许可门控 |
| [sources/social-sciences-econ-fin-mgmt.md](sources/social-sciences-econ-fin-mgmt.md) | 经济/金融/商业/管理来源、工作论文与期刊名录 | 已核验 2026-09-26：66 / 7 / 0 | SSRN 商业线关停且 ToU 禁止自动化，只取元数据；NBER 有 18 个月门控；UTD24 中 21/24 在 Atypon 或 Silverchair；央行 WP 走 Crossref、RSS 或 API；期刊名录按许可分级 |
| [sources/cs-ai.md](sources/cs-ai.md) | 计算机与 AI 会议、期刊、预印本与社区信号 | 已核验 2026-09-26：44 / 9 / 0 | dblp 的 robots 全禁，改用 DROPS 快照或 SPARQL；OpenReview 需账号；ACM 全库 OA 但禁止脚本下载；IEEE 零摘要且 DOI 滞后；新鲜度阶梯 L0–L3 |
| [sources/aggregators-repositories.md](sources/aggregators-repositories.md) | 二级来源：仓库与聚合平台 | 已核验 2026-09-26：61 / 7 / 0 | Crossref 按请求类型分池；OpenAlex 按量计费并提供季度快照；S2 为 1 RPS 且未明示允许商用；R1–R17 查询路由表；204 刊分学科的摘要覆盖画像 |
| [oss/paper-acquisition-and-search-oss.md](oss/paper-acquisition-and-search-oss.md) | 论文获取、检索与学术搜索开源（197 项） | 已核验 2026-09-26：44 / 15 / 0，另批量复测 196 个仓库 | R/I/B/X 分级；findpapers 的查询编译；没有开源项目实现"多用户 + 每用户凭证 + 合规分层"；盗版、Scholar 自动化、UA 伪装组件列入排除清单 |
| [oss/recommendation-oss.md](oss/recommendation-oss.md) | 推荐系统与学术推荐开源 | 已核验 2026-09-26（两轮）：40 / 12 / 0 | X 2026 开源管线与权重（commit 4c5cfe8）；Scholar Inbox 配方；S1/S2/S3 推荐栈；许可陷阱（GRID 限非商业，jina 为 NC） |
| [market/startups-and-products.md](market/startups-and-products.md) | 学术发现与论文推荐的初创与产品（约 66 个） | 已核验 2026-09-26（两轮）：99 / 17 / 0 | 8 层市场地图；没有产品同时具备五项能力；机构凭证取全文已有先例；Researcher App 于 2024-11 关停；付费转化率约 3% |
| [algorithms/social-media-recsys.md](algorithms/social-media-recsys.md) | 抖音/TikTok、小红书、X、快手、Meta 等社媒推荐 | 已核验 2026-09-26（两轮）：49 / 17 / 0 | Σ V·P̂ 是官方确认的范式；"八级流量池"与"CES 评分"属民间说法；照搬 C1–C11，改造 M1–M12；北极星为有价值阅读 |
| [algorithms/scholarly-recommendation-and-matching.md](algorithms/scholarly-recommendation-and-matching.md) | 学术推荐、兴趣建模与双向匹配 | 已核验 2026-09-26：74 / 10 / 0 | 共享表示加每用户线性头；没有单一最优嵌入；R0→R1→R2；论文→读者的反向路由与最小费用流；兴趣树以 OpenAlex Topics 为骨架，下挂原生分类 |
| [algorithms/retrieval-routing-indexing.md](algorithms/retrieval-routing-indexing.md) | 多源检索、路由、索引结构与多用户数据平台 | 已核验 2026-09-26：59 / 13 处 / 0 | 先收割后联邦；SCD、主题路由图与健全放宽；PG 单栈混合检索；Roaring 已见集；WatchKey；稳定性四件套；Pool + RLS；T0–T3 分档 |
| [ux/card-feed-interaction.md](ux/card-feed-interaction.md) | 卡片流与滑动交互及实现技术 | 已核验 2026-09-26：55 / 7 / 0 | Deck + 瀑布流 + Sheet；手势映射 A；投影判定与弹簧参数；WCAG 2.2 等价操作；React 19.3 PWA；事件契约 |
| [algorithms/paper-understanding-and-card-content.md](algorithms/paper-understanding-and-card-content.md) | 论文理解与卡片内容生成（TL;DR、关键图、翻译、标签） | 已核验 2026-09-26：32 / 10 / 0 | LLM 费用不是瓶颈；S2 TLDR 的学科覆盖严重偏科；图片许可闸（仅 39.5% 可展示）；翻译属于演绎；三道闸与 AI 标识；按学科定卡片模板 |
| [compliance/multi-user-platform-compliance.md](compliance/multi-user-platform-compliance.md) | 从单用户工具到多用户平台的许可、ToS 与监管边界 | 已核验 2026-09-26：57 / 10 / 0 | HC-01…HC-28；V0–V4 展示级别与 M1–M25 权利矩阵；受限全文在用户侧取回；中欧美监管对照；LQ-01…LQ-18 待法务确认 |

**附件**

| 所属文档 | 附件（同名子目录） | 内容 |
|---|---|---|
| natural-sciences | `request-ledger-2026-09-26.tsv`、`venue-verification-2026-09-26.csv` | 请求台账；107 行刊级实测（DOI 数、摘要覆盖等） |
| aggregators-repositories | `conference-crossref-check-2026-09-26.json`、`crossref-stats-2026-09-26.json`、`openalex-field-stats-2025.json`、`venue-verification-2026-09-26.jsonl` | 12 个 CS 会议的 Crossref 检查；Crossref 统计；OpenAlex 2025 学科画像；204 刊的核验原始结果 |
| paper-acquisition-and-search-oss | `repo-metrics-2026-09-26.tsv`、`repo-metrics-verify-2026-09-26.tsv` | 仓库的 star、许可、推送时间，以及核验复测结果 |
| multi-user-platform-compliance | `access-ledger-2026-09-26.tsv` | 访问台账 |
| paper-understanding-and-card-content | `arxiv-html-availability-`、`arxiv-license-dist-`、`arxiv-sample-stats-`、`hf-papers-coverage-`、`openalex-license-groupby-2026-09-26.json`；`price-inputs-`、`repo-metrics-`、`request-ledger-`、`s2-tldr-coverage-2026-09-26.tsv` | 实测 E1–E8、价格输入、41 个仓库的指标、225 次外部请求的台账 |

## 3. 调研过程记录

- **日期**：2026-09-26（UTC）。各篇核验记录统一以 UTC 记日期；执行时本机时区已进入 09-27 凌晨。
- **编排方式**：分三个阶段。
  1. **14 个主题并行调研**：每个主题由一个 Survey agent 独立完成。
  2. **逐篇对抗核验**：每篇由一个独立的 Verify agent 复核。核验时默认怀疑，只认一手来源；错误就地修正，标"核验修正/核验补充"，并在文末写唯一的"核验记录"节。
  3. **综合**：一个 Synthesize agent 通读 14 篇原文，产出 `00-survey-synthesis.md` 与本 README。
- **模型**：全部 subagent 使用 **Opus 5.5（max effort）**；文档 owner 统一为 `opus5.5-survey`。
- **共同约束**：
  - **合规红线**：只经合法来源与用户自有授权凭证获取；遵守 robots.txt 与 ToS，保守限速，使用诚实可识别的 UA；不绕付费墙或 CAPTCHA；不集成盗版源；不冒充；Google Scholar 不作自动化主源；多用户化后，auth-gated 全文不在用户间共享。
  - **写作规范**：front matter 四个字段；事实断言带来源 URL 与核验日期；无法核验的标"⚠ 未核验"；不编造仓库、论文、公司或数字。
  - **文件纪律**：只写分配给自己的文件，附件放同名子目录；不改 `docs/INDEX.md`、`docs/plan/progress.md`、`docs/plan/decision-log.md`。
- **请求纪律**：
  - 各篇使用诚实 UA，同站串行并保守间隔，遇 Cloudflare、Akamai、Imperva 等挑战页即停，不重试、不绕过；
  - 各篇记载的出版商与学术 API 请求都**没有使用用户的机构凭证或出版商账号**。NS、LS、AG、RT、PU 明确记载未登录，也未使用凭证、API key 或 cookie；SS 记载使用诚实 UA、不携带任何个人邮箱。PU 明确记载没有调用付费 LLM API；GitHub 元数据经 `gh api` 只读获取；
  - 请求台账见各附件与各篇"过程记录"。
- **中断与续核验**：
  - market、recommendation-oss、social-media 三篇的核验中断过一次（market 注明原因是会话用量上限，另两篇未写原因），之后由续核验复核首轮改动并合并完成，没有留下半截修改；
  - 本综合在一次会话用量上限中断后续做完成；
  - 部分篇在会话共享的 WebSearch 配额耗尽后，改用 curl、`gh api` 或官方 API 直读，见各篇"过程记录"。
- **偏差披露**：调研期间有少量请求落在 robots 禁区，或发生在读取 robots 之前，各篇已自行披露，综合 §1.5 汇总：
  - natural-sciences：IOP RSS、PubChem PUG-REST；
  - aggregators：9 次请求先于读取 robots；
  - social-sciences：`rss.sciencedirect.com`；
  - cs-ai：ICORE 门户与 `icml.cc/static`。

  这些偏差是设计输入 SI-38（robots 先行闸由框架强制）的依据，不构成对上游的持续访问。

## 4. 引用规范

1. **引用调研**：写"文档路径（或综合 §1.1 的代号）+ 节号"，链接只指向文件，节号写在文字里，例如 `RT §3.5.3`。"启示"条目写成"§3-n"（RT 为"§12-n"，SR 与 RO 为"§3.1-n"，MK 为"I-n"）。
2. **引用数字**：必须带时点，写"截至 2026-09-26"。限速、计费、版本、计数等快变事实，进入 ADR 或需求前须按 §5 的清单复核。
3. **标记含义**（各篇在"证据分级"一节另有 A–E 或 A/B/C 等级定义）：
   - "⚠ 未核验"：没有一手来源；
   - "◐"：部分核验或只有二手来源；
   - "⚠ 推断"：由已核验事实推理得到，未经实测；
   - "[SEC]" 或 "C/D/E 级"：二手、泄露或民间来源。

   设计文档**不得**把带 ⚠ 或 ◐ 的事实写成需求或 ADR 的确定性条款；需要时先补核验。
4. **合规约束**：引用写"CP HC-xx"（编号局部于 compliance 文档）。设计文档 08 统一登记全库唯一的 HC 编号时，须保留与 CP 编号的对照。
5. **设计输入**：引用写"SI-xx"（编号局部于综合文档）。设计文档采纳时写"依据 SI-xx"；不采纳时，在该文档的"异议与备选"一节说明证据（简报 §0 的规则）。
6. **一手来源**：转引一手来源时，保留原 URL 与原访问日期，不改写成本目录的引用。

## 5. 后续维护方式

1. **状态流转**：本目录文档目前均为 `draft`，按 [status-workflow](../archive-v1.md#docs-process-status-workflow-md) 流转。
   - 主 agent 复核后可提升为 `approved`，作为证据基线；
   - 调研文档不进入 `implemented`；
   - 被新调研替代的文档改为 `deprecated`，在顶部注明替代者，文件保留。
2. **INDEX 登记**：由主 agent 在 [docs/INDEX.md](../INDEX.md) 登记本目录。本轮文件纪律不允许调研 agent 修改 INDEX；登记时建议以本 README 为入口。
3. **事实修正**：发现过时或错误时，在原文就地修正，标"核验修正（YYYY-MM-DD）"，并在该篇"核验记录"表追加一行。若影响 SI、名录或 HC，同步更新综合文档的对应节，并在综合 §1.3 的统计中注明。
4. **新增调研**：
   - 放在对应子目录，文件名用 kebab-case；
   - front matter 四个字段齐全；
   - 必含章节：调研范围与方法（含过程记录）、主体内容、对 v2 设计的启示（编号）、未决问题与风险、参考来源（URL 与访问日期）；
   - 附件放同名子目录，文件名带日期后缀；
   - 完成后须经独立的对抗式核验，并更新本 README 的"文档一览"。

   综合 §7.3 已列出建议的补充调研：G-01 用户之声、G-05 地学/材料/中文生态等覆盖缺口、G-06 分学科表示评测等。
5. **名录的权威迁移**：设计阶段建立 `registry/sources/*.yaml` 与 `docs/catalog/source-directory.md` 后，来源状态以它们为准。综合 §3 的总表之后只作为历史证据，不再单独维护。
6. **快变事实按季度复核**（以 2026-09-26 为基线）：

| 事实 | 基线值 | 出处 | 复核频率 |
|---|---|---|---|
| Crossref 分池限速 | 公共池：单条 5/s、列表 1/s、并发 1；polite 池：10/s 与 3/s、并发 3；Plus 150/s | AG §0.1 | 季度 |
| OpenAlex 计费与快照 | 列表 $0.10/千次、搜索 $1/千次、PDF $0.01/次；免费 key 每日 $1；季度快照 | AG §2.2.2；RT §2.2 | 季度 |
| arXiv ToU 与限速 | 全部机器合计每 3 秒 1 次、单连接；自 2026-07-01 起为独立非营利机构 | CS §2.1.1；NS §2.3.5 | 季度 |
| Semantic Scholar API | key 为 1 RPS；许可未明示允许商用 | AG §2.2.3 | 季度 |
| bioRxiv/medRxiv API | `/details` 返回 200 空体（2026-09-26） | LS §2.2.1 | 月度 |
| PMC 自动化通道 | 仅 S3、OAI-PMH、E-utilities、BioC；OA Web Service 已退役 | LS §2.3.2 | 季度 |
| dblp | 三个主机的 robots 均为 `Disallow: /`；只用 DROPS 月度快照与 SPARQL | CS §0.1；AG §2.2.12 | 季度 |
| SSRN | 商业线 2026-12-31 关停；ToU 禁止自动化 | SS §2.1 | 2027-01 |
| ADS→SciX | 切换日期 ⚠ 未核验 | NS §4 | 切换后 |
| X 推荐参数 | 固定在 commit 4c5cfe8 引用 | RO §2.2.2；SM §2.4.2 | 引用时按 commit |
| LLM 与翻译 API 价格 | 见 PU §2.6.2（附件 `price-inputs-2026-09-26.tsv`） | PU §2.6.2 | 月度 |
| 前端框架版本 | React 19.3、Motion 13、Expo SDK 57 等 | UX §2.7.1 | 季度 |

## 6. 已知局限

- **时点抽样**：各篇的实测都是时点小样本，不代表全量统计。WAF 与挑战的观察受出口 IP 影响，在校园网或用户本地网络下可能不同。
- **法律边界未决**：LQ-01…LQ-18 仍待法务确认，涉及摘要展示长度、B 类摘要能否进索引、商用定义、LLM 摘要门槛等。相关结论只能作为默认假设。
- **覆盖缺口**：地学、材料、中文生态、心理学会议与部分 CS venue 的覆盖不全，见综合 §3.3、§7.3。

## 7. 参考

- [00-survey-synthesis.md](00-survey-synthesis.md)——综合与设计输入
- [v2 设计决策简报](../plan/v2/00-design-brief.md)——上游架构裁决
- [文档写作与目录规范](../archive-v1.md#docs-process-doc-conventions-md)、[状态流程](../archive-v1.md#docs-process-status-workflow-md)——本目录遵循的写作与状态规则
