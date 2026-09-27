---
title: 市场调研：学术发现与论文推荐相关初创与产品
status: draft
owner: opus5.5-survey
updated: 2026-09-26
---

# 市场调研：学术发现与论文推荐相关初创与产品

> 本文是 v2 重新设计（多用户论文发现平台 + 类小红书/抖音卡片流推荐）调研阶段的"市场/竞品"子报告。覆盖国内外 54 个产品/项目/事件（核验轮另补 ResearchGate、PubPeer、Paper Skygest、FutureHouse/Edison、NotebookLM Audio Overviews、OpenAI Prism 6 项；续核验轮再补 Read by QxMD、ResearchHub、PaperCrush、ZiNote、PaperTok（UW）、Google Scholar Quick Read 6 项，并依官网存档把 Researcher App 更正为"2024-11 末已关停"），逐一记录定位、核心功能、推荐/发现机制、交互形态、数据来源、商业模式与定价、融资/规模/用户数、口碑痛点，并给出竞品矩阵、交互形态对比、市场空白、差异化定位与商业模式/风险判断。
>
> **证据约定**：文中 `[R#]` 指向 §5 参考来源（均含 URL；除另注外访问/核验日期均为 **2026-09-26**）。证据等级标记：
> - ✅ 一手核验：本轮亲自打开的官方页面/官方公告/论文/仓库 API/平台实时数据；
> - ◐ 二手或仅检索摘要：原页 403/证书错误/JS 渲染未能打开、只见检索摘要，或来自第三方汇编页；
> - ⚠ 未核验：训练知识或推断，须复核后才能进入设计决策。
> - "（推断）"表示作者的分析判断，不是事实断言。
>
> 与既有文档的边界：开源抓取类项目见 [research/github-similar-projects.md](../../archive-v1.md#docs-research-github-similar-projects-md)；数据源 API 事实见 [research/site-survey/metadata-apis.md](../../archive-v1.md#docs-research-site-survey-metadata-apis-md)；抖音/小红书/X 的推荐算法原理由同批"推荐算法"调研承担，本文只记录产品层可观察事实。

## 0. 结论速览

1. **市场已分化为 8 层**（开放基础设施、订阅/个性化流、社区热度流、引文图谱、AI 检索/综述 Agent、阅读与文献管理、出版商围墙内 AI、中文综合平台与社媒；见 §2.1），**没有一家同时做到**"移动优先的卡片滑动 + 可学习的个性化 + 跨学科（含经管金融工作论文）+ 用户自带机构凭证取全文 + 可解释推荐"。这是 v2 的差异化空间（§2.9）。**续核验修正**：单项能力已不稀缺——"机构登录取全文"已是 R Discovery（GetFTR + LibKey）[R31] 与 Read by QxMD（2012 年起）[R82] 的现成功能；"滑动 + 学习"已有 ZiNote（2026-01 上架 iOS）等个人开发者 App [R84]；SSRN/NBER 元数据也已被 OpenAlex 与 S2 收录 [R86]。空白在于上述能力的**组合**与**经管 WP 的新鲜度**，不在任何单项。
2. **数据层已商品化**：Semantic Scholar（225M 论文、2.8B 引文边，2025-05 口径 [R16]；续核验修正，原"200M+"为 2023 年口径）、OpenAlex、Crossref 是多数初创的共同底座——S2 被 Elicit、SciSpace、Asta 等当作基础语料 [R16][R18]，Litmaps 用 OpenAlex + S2 + Crossref [R13]，Keenious 用 OpenAlex [R51]，Scollr 用 OpenAlex + S2 [R69]，Scholar Inbox 用 S2ORC [R21]；各家宣称语料在 1.38 亿–3.1 亿量级（Elicit 138M+ [R4]、Consensus 220M+ [R1]、R Discovery 250M+ [R30]、ResearchRabbit 310M+ [R10]）。**语料规模不再是护城河**；新鲜度、学科覆盖（尤其 SSRN/NBER/RePEc）、交互与个性化质量才是。
3. **推荐算法的已验证强基线很朴素**：Scholar Inbox = GTE-Large 嵌入 + 每用户逻辑回归、每次评分即重训，离线 AUC≈0.87 [R21]；S2 Research Feeds = 对比学习论文嵌入 + "收藏=正/不相关=负"，候选限近 3 个月、每日刷新 [R15]，其平台论文披露的实现是每用户在 TF-IDF 与 SPECTER 上各训一个线性 SVM、FAISS 近邻召回（核验补充）[R16]——两个生产系统都是"共享表示 + 每用户线性头"。冷启动普遍靠"种子论文 + 科学地图 + 主动学习"。
4. **滑动卡片在学术领域只有原型级或个人开发者级先例**：Papr（2017，bioRxiv 摘要四向滑动 = 兴趣 × 可信度，刻意隐藏作者防偏见）[R68]；ArxivTok/ArTok/PapersTok（2025 独立开发，关注度低，多为无算法随机流）[R69]。**续核验补充**：已有上架的 iOS App——PaperCrush（2025-05，在所选 arXiv 分类的每日新文上 Like/Skip 滑动，另有用户热度榜）与 ZiNote（2026-01，右滑保存、左滑跳过，自称"从阅读行为中学习"，免费 20 篇/天）[R84]，但美区评分数分别只有 0 和 2，规模与效果都没有公开证据；华盛顿大学 PaperTok（CHI 2026）把论文生成 45 秒短视频，参与者担心"AI 味太重"会损害学术信誉 [R85]。**形态本身未被证明能留存用户**，必须与推荐质量、摘要/音频、入库工作流捆绑。
5. **商业化普遍困难**：Consensus 2024-08 约 40 万月活、约 1.2 万付费（Verdict），年化收入按官方新闻稿为"近 $2M"（Verdict 报"年收入进度约 $1.5M"）[R2]；scite 被收购时约 2.1 万活跃订阅、年化订阅收入 $3.6M [R5]；Litmaps 收购 ResearchRabbit 后合计用户 200 万+，而 Litmaps 自身 ARR（融资前）约 $1M [R8]。可持续模式集中在**机构/企业授权**与**生态补贴**（Ai2、eLife、Hugging Face、Cactus 作者服务交叉销售）。
6. **平台关停/转向风险真实**：Microsoft Academic（2021-12-31 退役）[R71]、Meta（CZI，个性化论文 feed，2022-03-31 关停）[R72]、Papers with Code（2025-07 无预告下线）[R26]；ResearchRabbit 被收购后转 freemium [R9]。**续核验补充**：与 v2 形态最接近的移动社媒式论文 feed Researcher App（2020 年 160 万用户、长期免费、变现方式未披露）于 **2024-11 月底关停**，官方公告只提示用户自行备份数据和书签 [R32]；Inciteful 的根域名已转向面向患者的医学问答产品，学术工具退到子路径 [R74]。v2 须把"用户数据可导出、不锁定单一上游"写成设计约束。
7. **出版商自有 AI 的共同模式**是"只在自有内容内运行 + 全量/付费内容只对订阅机构开放（公开版仅限 OA，如 Dimensions GPT）"，ScienceDirect AI 还明确声明不存储、不用于训练公共模型（Scopus AI、ScienceDirect AI、WoS Research Assistant、Dimensions GPT）[R61][R62][R63][R64]；**续核验补充**：非出版商的 Google Scholar Quick Read（2026-08）同样只对用户有权访问的论文显示 AI 速读 [R42]。这些先例印证 v2 红线：**auth-gated 全文只能在用户私域内使用；任何跨用户共享的推荐特征、摘要、卡片内容只能来源于开放元数据、摘要与 OA 全文**。

## 1. 调研范围与方法

### 1.1 范围

| 分组 | 条目（任务指定 + 调研中追加★） |
|---|---|
| 个性化推荐与订阅流 | Semantic Scholar Research Feeds/Alerts、Scholar Inbox、Paper Digest、R Discovery、Researcher（2024-11 关停）、Scollr★、AMiner 科技情报订阅；续核验补充：Read by QxMD |
| 社区热度与讨论 | Hugging Face Papers（Daily/Trending）、alphaXiv、Emergent Mind、Papers with Code（关停）、Sciety；核验补充：ResearchGate、PubPeer、Paper Skygest（Bluesky）；续核验补充：ResearchHub |
| 引文图谱探索 | Connected Papers、Litmaps、ResearchRabbit（含 2025 变化）、Inciteful |
| AI 检索/问答/综述 | Elicit、Consensus、scite、SciSpace、Undermind、Iris.ai、Perplexity（学术来源）、OpenAI Deep Research/ChatGPT、Google Scholar（含 Scholar Labs；续核验补充 Quick Read）、Ai2 Asta★；核验补充：FutureHouse Platform/Edison Scientific、OpenAI Prism（仅记于 §2.7 与 §4.1） |
| 阅读、写作与文献管理 | Moonlight、Scholarcy、Keenious、Zotero、Mendeley、Paperpile、ReadCube；核验补充：NotebookLM Audio Overviews |
| 出版商/数据库商 AI | Scopus AI、ScienceDirect AI、Web of Science Research Assistant、Dimensions AI |
| 中文生态 | 玻尔 Bohrium（深势科技）、AMiner/智谱（Z.ai）、ReadPaper、知网 CNKI AI/知网研学、秘塔 AI 学术、Kimi（学术搜索/Kimi-Researcher）、Cool Papers、百度学术、小红书/抖音"论文分享"内容生态 |
| 滑动/短视频式原型 | Papr★、ArxivTok★、ArTok★、PapersTok★；续核验补充：PaperCrush、ZiNote（均为已上架 iOS App）、PaperTok（UW，论文→短视频） |
| 关停/并购参照 | Microsoft Academic★、Meta（CZI）★、Papers with Code、scite、ResearchRabbit、Mendeley；学术对照：arxiv-sanity-lite★、PaperFlow（2026）★；续核验补充：Researcher App（2024-11 关停）、QxMD（2019 被 WebMD 收购）、Inciteful（转向） |

不在范围：开源抓取/推荐项目的代码级调研（见同批 GitHub 调研与既有 github-similar-projects.md）；推荐算法原理与社媒算法拆解（同批算法调研）；各数据源 API 端点/限速（site-survey 系列）。

### 1.2 方法

1. 取证顺序：官方一手页面（定价页、官方博客、新闻稿、论文、仓库）→ 权威二手（Wikipedia、行业媒体）→ 第三方汇编页（仅作 ◐ 补充）。融资/用户数优先取官方公告与论文自述，并注明口径与日期。
2. GitHub 指标：`gh api repos/OWNER/REPO --jq '[.full_name,.stargazers_count,.license.spdx_id,.pushed_at,.archived]'`（2026-09-26）。
3. Hugging Face 论文热度：HF Hub MCP 实时读取 `hf://papers/trending` 与 `hf://papers/daily/2026/09/25`（2026-09-26）。
4. 口碑痛点：优先 Hacker News 帖子、Chrome 商店评分、书评与论文内用户研究；**Reddit/X/知乎/小红书的系统采集未完成**（WebSearch 会话配额耗尽，见 §1.3 与 §4）。

### 1.3 过程记录（可复现）

- **日期**：2026-09-26（单日完成）；执行者：opus5.5-survey（本调研 agent）。
- **WebSearch 检索式**（按执行顺序；共 53 次成功；第 54–56 次因会话级 WebSearch 配额 200 次（含并行 agent）耗尽未执行）：
  1. `ResearchRabbit 2025 new version Litmaps acquisition`
  2. `Elicit AI research assistant Series A funding 2025 valuation users`
  3. `Consensus AI academic search engine funding 2025 users`
  4. `Semantic Scholar Research Feeds how recommendations work thumbs up rate papers`
  5. `scite Research Solutions acquisition price scite.ai 2025`
  6. `Semantic Scholar 2025 Ai2 Asta Paper Finder launch Semantic Scholar feeds changes`
  7. `Scholar Inbox personalized paper recommendations arXiv paper Geiger users ratings active learning`
  8. `alphaXiv seed funding raise 2025 Menlo Ventures`
  9. `Papers with Code shut down July 2025 Hugging Face trending papers redirect`
  10. `Hugging Face Daily Papers how papers are selected upvotes AK curated submit paper`
  11. `R Discovery app Cactus Communications users feed research papers Prime subscription price`
  12. `Researcher app "Researcher" discover latest research papers feed users acquired`
  13. `"TikTok for research papers" OR "TikTok for papers" swipe app arXiv`
  14. `"Tinder for" research papers swipe left right app scientists`
  15. `Researcher app Owen Stephens "Researcher" app journals feed 2024 OR 2025 users funding publisher`（无效检索式，结果不相关）
  16. `Connected Papers pricing plans free graphs per month Academic Business 2025`
  17. `Litmaps pricing Pro plan 2026 monitor alerts seed maps`
  18. `ResearchRabbit premium "RR+" price per year features free tier limits 2026`
  19. `Inciteful citation network tool free Michael Weishuhn paper discovery literature connector`
  20. `Paper Digest daily digest pricing personalized arXiv recommendation company 2025`
  21. `SciSpace funding users 2025 Typeset.io raise Series`
  22. `Undermind AI research search funding pricing Pro 2025 2026`
  23. `Iris.ai researcher workspace 2025 funding news company`
  24. `Google Scholar Labs AI launch November 2025 how it works`
  25. `Perplexity "Academic" focus mode search scholarly sources 2025 2026`
  26. `Google Scholar Labs 2026 update expanded availability OR "Scholar Labs" new features 2026`
  27. `site:perplexity.ai help center academic sources toggle "Academic" search sources`
  28. `Perplexity Wiley partnership 2025 academic content integration announcement`
  29. `OpenAI deep research launch February 2025 academic literature availability free users 2026`
  30. `Emergent Mind AI papers trending arXiv social signals Matt Mazur pricing`
  31. `Moonlight AI colleague for research papers Corca users funding`
  32. `Zotero 8 release 2026 new features`
  33. `Mendeley 2025 2026 changes discontinued features Mendeley Reference Manager Mendeley Suggest`
  34. `ReadCube Papers Digital Science recommendations feed pricing 2026`
  35. `Keenious research recommendation tool Word Google Docs plugin pricing institutions 2025`
  36. `Sciety eLife 2025 2026 preprint evaluation platform status lists follow groups`
  37. `Scholarcy pricing 2026 summary flashcards users`
  38. `Bohrium 玻尔 深势科技 科研 平台 用户数 2025 论文 AI 学术`
  39. `AMiner 智谱 学术 订阅 推荐 论文 2025 功能`
  40. `ReadPaper 论文阅读平台 公司 用户数 2025`
  41. `深势科技 融资 2025 OR 2026 玻尔 Bohrium 用户`
  42. `知网 AI学术研究助手 华知大模型 发布 2025 研学 功能`
  43. `秘塔AI搜索 学术 模式 论文 文库 2025`
  44. `papers.cool Cool Papers 苏剑林 Kimi arXiv 浏览 FAQ`
  45. `Kimi 学术搜索 上线 论文 2025 学术模式`
  46. `百度学术 AI 2025 功能 升级 学术 助手 文献`
  47. `Scopus AI Deep Research launch 2025 Elsevier institutions pricing add-on`
  48. `ScienceDirect AI launch March 2025 Elsevier features full text`
  49. `Web of Science Research Assistant Clarivate launch 2024 2025 features agentic`
  50. `Dimensions Research GPT Digital Science AI assistant 2025 2026 Dimensions AI`
  51. `小红书 科研 论文分享 博主 读论文 笔记 现象 学术 内容 生态`
  52. `抖音 学术 论文 解读 短视频 科研 博主 知识 2025`
  53. `Xiaohongshu RedNote academic researchers share papers science communication study`
  54. ~~`Paper Skygest Bluesky feed research papers shared by people you follow`~~（配额耗尽未执行）
  55. ~~`"小红书" 研究生 找论文 搜索 科研 用户 调查 2025 学术`~~（未执行）
  56. ~~`知乎 论文解读 机器之心 量子位 PaperWeekly 论文分享 公众号 生态 读者`~~（未执行）
- **WebFetch 成功打开（✅）**：consensus.app 融资博客；elicit.com（Series A 博客、定价）；researchrabbit.ai（2025 公告、定价）、learn.researchrabbit.ai（RR+ 说明）；itbrief.co.nz（Litmaps 收购）；litmaps.com（定价、2022 改版）；semanticscholar.org（FAQ 两页）；arxiv.org（2504.08385、2301.10140、2204.10254、2512.20469、2602.23335、2606.07454）；aclanthology.org（Scholar Inbox demo）；prnewswire.com（alphaXiv、scite）；news.ycombinator.com（43755405、39042157、42724317）；scollr.com；blog.google（Scholar Labs）；docs.perplexity.ai；emergentmind.com（about、pricing）；zotero.org（Zotero 8、storage）；blog.mendeley.com；about.readcube.com；paperpile.com；sciety.org；qbitai.com（深势科技、百度学术）；open.aminer.cn；github.com（bojone/papers.cool、Miguel07Alm/arxivtok）；elsevier.com（Scopus AI、ScienceDirect AI 新闻稿）；blog.scopus.com；ir.clarivate.com（2024、2025 新闻稿）；globenewswire.com（Dimensions GPT）；news.qq.com；blog.csdn.net（REDtech 官方号）；metaso.cn（部分）；undermind.ai；ycombinator.com；scite.ai；themoonlight.io；chromewebstore.google.com；paperdigest.org；keenious.com；alphaxiv.org（about、首页）；huggingface.co（Daily Papers 博客）；allenai.org（Asta 博客）；iris.ai；moonshotai.github.io（Kimi-Researcher）；researchoutreach.org；editage.com；ai-bot.cn（CNKI AI、◐ 第三方）；theaiagentindex.com（SciSpace、◐ 第三方）；zmescience.com（Papr）；scholar.google.com（帮助页）；en.wikipedia.org（Semantic Scholar、Mendeley、Google Scholar、Xiaohongshu、Zhipu AI、ChatGPT Deep Research、Microsoft Academic、Meta (academic company)）。
- **WebFetch 失败/受限（✗）**：science.org（403）；nature.com（跳转登录）；perplexity.ai 帮助中心与 /academic（403）；connectedpapers.com（JS 渲染仅得标题）；medium.com（403）；scholarcy.com（403）；katinamagazine.org（403）；kexue.fm（403）；scispace.com（403）；mobihealthnews.com（403）；openai.com（403；另尝试核验 OpenAI 2026 年面向科研写作的新产品页面，403 未能确认，正文不采用）；baike.baidu.com（403）；idea.edu.cn、readpaper.com、finance.sina.com.cn、calsp.cn、tmtpost.com、hub.baai.ac.cn、finance.yahoo.com、apps.apple.com、多所高校图书馆页面（证书链错误）；researcher-app.com（socket closed）；play.google.com（内容截断）；scholar-inbox.com、incitefulmed.com（仅得标题）。
- **gh api**（2026-09-26）：`Miguel07Alm/arxivtok`、`zotero/zotero`、`sciety/sciety`、`huggingface/hub-docs`、`bojone/papers.cool`、`zx33/zotero-cool-paper`、`karpathy/arxiv-sanity-lite`、`AutoLLM/ArxivDigest`、`avg-dev/scholar_inbox_datasets`、`paperswithcode/paperswithcode-data`、`allenai/asta-paper-finder`、`allenai/ai2-scholarqa-lib`。
- **HF Hub MCP**：`ls hf://papers/trending --limit 10`、`ls hf://papers/daily/latest`（空）、`ls hf://papers/daily/2026/09/25`（返回前 22 条）。
- **核验轮（Verify，2026-09-26，另一 agent 对抗式复核）**：会话级 WebSearch 配额已耗尽，改用 WebFetch 直访一手页面（中途 WebFetch 亦触发会话上限，其余用 `curl` 取公开页面/API）；`gh api` 复核全部仓库指标并读取 `jtleek/papr`（UI/推荐源码）、`avg-dev/scholar_inbox_datasets`（LICENSE/README）、`bojone/papers.cool`（更新日志）、`AK391/dailypapersHN`（README 公式）、`allenai/asta-paper-finder`（README）、`paperswithcode/paperswithcode-data` issue #116 评论；arXiv API 检索 `all:Skygest`；SEC EDGAR 全文检索 + Research Solutions FY2024 10-K；HN Firebase API 读取三帖评论树；Wikipedia API 取 OpenAI 产品、PubPeer 条目。逐条结论见文末"核验记录"；正文中"核验补充"/"核验修正"标记即本轮改动。
- **续核验轮（Verify 续，2026-09-26；首轮因用量上限中断后接续）**：先检查首轮留下的改动（表格列数、`[R#]` 引用闭合、首轮"修正"项逐条复核一手源），再用恢复后的 WebSearch 处理首轮"未核验"项与覆盖缺口。WebSearch 检索式（按执行顺序）：`Edison Scientific FutureHouse spinout Kosmos AI scientist funding`；`futurehouse.org announcing Edison Scientific Kosmos November 2025`（限 futurehouse.org、edisonscientific.com）；`Edison Scientific raises $70 million seed Spark Capital Triatomic announcement`；`OpenAI Prism LaTeX workspace scientists launch January 2026`；`Consensus raises $11.5 million Series A Union Square Ventures August 2024`；`Connected Papers pricing free 5 graphs per month Academic plan Business plan price`；`Connected Papers about "Co-citation and Bibliographic Coupling" "Semantic Scholar" similarity metric`；`SciSpace Typeset funding round raised million 2025 users researchers`；`ChatGPT deep research usage limits Plus Pro free tasks per month help center 2026`；`Asta "Find Papers" "108" million abstracts "12" million full-text Ai2`；`"Researcher" app researcher-app.com 2025 OR 2026 journals feed users acquired`；`ResearchHub Brian Armstrong ResearchCoin peer review bounties platform 2025 users funding`；`TikTok-style feed for research papers app 2026 swipe arXiv startup`；`"swipe" research papers app scientists personalized feed launch 2025 OR 2026 ...`；`Papel TikTok-like experience scientific papers ...`；`QxMD acquired by WebMD Medscape Read by QxMD ...`；`X API pricing 2026 pay-per-use Basic tier price posts read limit developer`；`Elicit AI research assistant raises Series B 2026`；`alphaXiv 2026 funding OR launch OR users news`；`alphaXiv raises $70 million Series A`；`AMiner 论文 3.3亿 学者 6000万 专利 1.8亿 科技情报`；`"Scholar Labs" Google Scholar 2026 expanded availability all users update`。直读的一手页面/接口：arxiv.org（2301.10140v2 PDF 全文、2504.08385v2 HTML 表 2、2204.10254 摘要、arXiv API 批量核对 5 篇 2025–2026 论文）；sec.gov（Research Solutions FY2024 10-K Note 9 原文）；`gh api`（14 个仓库指标全量复测、jtleek/papr 的 `ui.R`/`server.R`/`about.md`/`help.md`、scholar_inbox_datasets 的 LICENSE 与 README、hub-docs）；itbrief.co.nz、newsroom.wiley.com、ir.clarivate.com（2025 新闻稿）；Wikipedia MediaWiki API（Semantic Scholar、ResearchGate、PubPeer）；prweb.com（Consensus 2024 官方新闻稿）；finance.yahoo.com（Verdict 原文，curl）；semanticscholar.org/about/publishers；api.openalex.org（`/sources?search=ssrn`、`/sources?search=National Bureau of Economic Research`）；connectedpapers.com（About 页前端包文案，curl）；allenai.org（Asta 博客、《Asta Getting Started Guide》2026-02 PDF）；sciety.org（`/groups`、`/groups/elife`）；docs.aminer.cn；futurehouse.org 与 edisonscientific.com（2025-11-05 分拆公告、2025-12-18 融资公告）；techfundingnews.com（估值，◐）；blog.google（NotebookLM）；scholar.googleblog.com（2026-06-03 Labs 更新、2026-08-25 Quick Read）；huggingface.co（`/.well-known/openapi.json`；HF Hub MCP 复读 trending 与 2026-09-25 日榜）；docs.x.com（API 定价）；editage.com（R Discovery）；itunes.apple.com Lookup/Search API（PaperCrush、ZiNote、Scollr、Read by QxMD、R Discovery 的上架日期、开发者、评分数与描述）；qxmd.com（WebMD 收购公告）；researchhub.com 与 blog.researchhub.foundation、theblock.co；washington.edu（PaperTok 新闻）；incitefulmed.com（首页元数据，curl）；web.archive.org（researcher-app.com 2024-11-19 存档，因现网 TLS 失败）；litmaps.com（定价页 HTML）；scholar-inbox.com（首页元数据）；iris.ai（Series A 博客正文电头）；hacker-news.firebaseio.com（Moonlight 帖评论树复读）；scholar.google.com（帮助页"Off-campus access"一节）。失败/受限：hpcwire.com（403）；researcher-app.com（TLS 失败，改用存档）；apps.apple.com 网页（证书链错误且被重定向到本地区"Today"页，改用 iTunes Lookup API）；medium.com、katinamagazine.org、science.org、scispace.com、scholarcy.com 仍未直读（Cloudflare/403，不绕过）。

## 2. 主体内容

### 2.1 市场地图（分层）

| 层 | 用户任务 | 典型产品 | 主触达形态 | 主要盈利方式 |
|---|---|---|---|---|
| L1 开放基础设施 | 检索/元数据/API | Semantic Scholar + Ai2 Asta、arXiv、HF Papers、OpenAlex/Crossref（另文） | 搜索页、API、MCP | 非营利/生态补贴 |
| L2 订阅与个性化流 | "每天该读什么" | S2 Research Feeds、Scholar Inbox、Paper Digest、R Discovery、Read by QxMD、Scollr、AMiner 订阅、ZiNote/PaperCrush（滑动）；Researcher（2024-11 关停） | 邮件 digest、网页/移动 feed | 免费 + 订阅；作者服务交叉销售（R Discovery）；被收购并入医学媒体（QxMD→WebMD） |
| L3 社区热度与讨论 | "大家在读/在聊什么" | HF Daily/Trending、alphaXiv、Emergent Mind、Sciety、ResearchGate、PubPeer、Paper Skygest、ResearchHub | 热度榜、评论区、社交 feed | 生态引流、订阅、企业服务；代币激励（ResearchHub） |
| L4 引文图谱 | 补课、综述、找遗漏 | Connected Papers、Litmaps、ResearchRabbit、Inciteful | 图谱 + 列表 + 监测提醒 | freemium 订阅、机构版 |
| L5 AI 检索/综述 Agent | 复杂问题、系统综述 | Elicit、Consensus、scite、SciSpace、Undermind、Iris.ai、Perplexity、ChatGPT Deep Research、Scholar Labs、Asta | 对话、报告、表格 | 订阅（$10–200/月）、企业 |
| L6 阅读/写作/文献管理 | 读懂、管理、引用 | Moonlight、Scholarcy、Keenious、Zotero、Mendeley、Paperpile、ReadCube | 阅读器侧栏、插件、库 | 订阅、存储付费、机构 |
| L7 出版商/数据库商 AI | 在订阅库内问答 | Scopus AI、ScienceDirect AI、WoS Research Assistant、Dimensions | 数据库内 AI 助手 | 机构加购 |
| L8 中文综合平台与社媒 | 中文检索/阅读/分享 | 知网 AI、百度学术、秘塔、AMiner、玻尔、ReadPaper、Kimi、Cool Papers；小红书/抖音 | 搜索+AI、微信/小程序推送（◐）、图文/短视频 | 机构采购（◐）、会员（◐）、广告/流量（小红书 ✅） |

### 2.2 产品档案

> 列说明：**机制**=推荐/发现机制；**形态**=交互形态；**规模**=融资/规模/用户（口径与日期）。"—"=未见公开信息；"未采集"=本轮未能采集口碑。

#### 2.2.A 个性化推荐与订阅流

| 产品 | 定位与核心功能 | 机制 | 形态 | 数据来源 | 商业模式·定价 | 规模（日期） | 口碑·痛点 | 证据 |
|---|---|---|---|---|---|---|---|---|
| **Semantic Scholar Research Feeds / Alerts**（Ai2） | 免费学术搜索 + 自适应推荐；另有 TLDR、Semantic Reader、API | Library 文件夹内论文=正例，feed 内标"not relevant"=负例；用"对比学习训练的论文嵌入模型"找相似论文；官方建议先给 5 正 + 3 负；推荐**每日刷新**、候选取自**近 3 个月**论文 ✅。**核验补充**：S2 平台论文（arXiv 2301.10140 v2 §3.4.5）披露实现为 arxiv-sanity 的扩展——每用户用正/负标注训练**两个线性 SVM**（TF-IDF 与 SPECTER 嵌入各一），负例补充降权的随机负样本；候选由 FAISS 在**近 60 天约 100 万篇**（每晚刷新）的 SPECTER 索引中召回，取正例质心最近约 500 篇，按两模型得分均值排序 ✅（论文"60 天"与 FAQ"3 个月"口径不一，以线上为准 ⚠） | 网页列表 feed；Alerts 四类（作者/论文被引/主题/Feed），邮件每日或每周 ✅ | 自有学术图谱：**225M 论文、105M 作者、2.8B 引文边**（S2 平台论文 v2 表 1，2025-05 口径 ✅；**续核验修正**：原文"200M+ 论文、80M+ 作者、2.4B+ 引文边"是 2023 年 v1 口径）；Wikipedia 称 2026 年 214M ✅；数据合作方页列有 SSRN（未列 NBER/RePEc，续核验补充 ✅）；API 2024 年服务 18 亿+ 次请求、已发 3,000+ 个 key（同论文 §4，核验补充 ✅） | 完全免费（Ai2 资助）✅ | 2020 年末约 700 万月活（Wikipedia）✅ | 冷启动需用户主动建文件夹并评分（据 FAQ 推断）；未见移动 App（⚠） | [R15][R16][R18] |
| **Scholar Inbox**（图宾根大学 Andreas Geiger 组） | 免费个性化论文推荐：每日推荐、视觉化摘要、语义检索、相似论文、Collections、会议 poster 规划 | GTE-Large 嵌入（PCA 至 256 维）+ **每用户逻辑回归**，每次评分后重训；显式 👍/👎 + 5k 随机负样本、加权 BCE；冷启动=选种子论文 + **Scholar Maps**（300 万论文 t-SNE 科学地图，LLM 生成层级主题标签）+ **主动学习**（在决策边界附近分层采样让用户评分）✅ | 网页 feed + 按用户设定频率的邮件 digest；论文图 4 为平板/手机网页视图，久未登录会生成 catch-up digest ✅ | arXiv、bioRxiv、medRxiv、ChemRxiv + 会议直采；S2ORC 补元数据与引文 ✅ | 免费；VolkswagenStiftung Momentum 资助 ✅ | 2025-04：注册 23k、近 30 天活跃 8k（35%）；14.3k 用户贡献 80 万条评分（数据集公开）；离线 AUC 86.75、nDCG 85.83（GTE-L 256 维）；1,233 人用户研究评价积极 ✅。**续核验补充**：同表中 TF-IDF 10k 维稀疏基线的 nDCG 为 88.67，高于 GTE-L，但 AUC（84.41）与 F1 较低——稀疏基线在排序指标上并不弱 ✅。**核验补充**：数据集仓库 README 实列显式 👍/👎 评分 774k 条 + 隐式交互（阅读/收藏/分享点击）556k 条 + 摘要句子标注 2,538 条；LICENSE 文件为 **CC BY-NC-ND 4.0**（非商用、禁止演绎）✅ | 学术项目的可持续性依赖资助（推断）；学科以预印本服务器为主，未见经管 WP（推断） | [R21][R22] |
| **Paper Digest**（纽约，2018） | 每日论文 digest + 文献检索 + AI 写作辅助 | 以"估计每篇新论文潜在影响力"的算法排序，结合社交/在线指标；用户选 200+ 类目、跟踪关键词/作者 ✅ | 邮件 digest / 控制台；每篇一句话 highlight ✅ | arXiv、PubMed、bioRxiv、medRxiv、clinicaltrials.gov + 数千会议/期刊 ✅ | 免费日报（arXiv/bioRxiv/medRxiv）+ 付费 $10.99/月、$79.90/年 ✅ | "数万研究者"（自述，daily digest 页 ✅） | 未采集 | [R33] |
| **R Discovery**（Cactus Communications / Editage） | 移动优先的论文发现 App：个性化阅读 feed、摘要、PDF 对话、听论文、30+ 语言翻译 | 基于兴趣的 Reading Feed，"社媒式"个性化推荐；官方页称系统会"从你过往的检索和你在 App 里喜欢的论文类型中学习"来调整推荐（续核验升级 ✅，模型细节未公开） | 移动 App 社媒式信息流；**机构登录取全文**（App Store 描述 2026-08-26 版："GetFTR 与 LibKey 集成"）；新文提醒 ✅（续核验补充） | 250M+ 文章（40M+ OA、32,000 期刊、2M+ 预印本、7.5M+ 专利，自述）✅；来源含 PubMed、PMC、Crossref、Unpaywall、OpenAlex 及 Wiley、Springer Nature 等出版商 ✅；App Store 描述另给 1.5 亿+ 期刊文章、7,800 万+ OA、500 万+ 预印本、6.4 万+ 期刊——厂商自述口径不一 | 免费 + Prime $5/月、$12/季、$39/年；与 Editage Plus（$174/年）捆绑——**作者服务交叉销售** ✅ | "2.5M+ 下载、190+ 国家"；"3M+ academics"（自述）✅；iOS 美区 4.8★（919 条评分，iTunes API，续核验）✅ | 应用商店评论正文未采集 | [R30][R31] |
| **Researcher**（伦敦，Researcher App；**2024-11 已关停**） | "让科学家跟上科学"的社媒式 feed | 关注期刊/关键词/作者 → 新文进入 feed（规则订阅为主）✅ | 移动 feed；书签、分享、送入文献管理器、机构全文 ✅ | 解析 16,000 种期刊、日均约 5,000 篇新文（2020）✅ | 2020 年报道"完全免费"，变现方式未披露 ✅ | 160 万用户（2020-07）✅ | **续核验修正**：官网 2024-11-19 存档为关停公告——"Researcher App will be closing"，**可用至 2024 年 11 月底**，团队"转向正在开发的新项目"，只提示用户自行备份数据与书签 ✅；2026-09-26 官网 TLS 连接失败，与关停一致 | [R32] |
| **Scollr** | 跨学科移动研究 feed（iOS） | 关注主题/作者/期刊 + 从"打开、保存、点赞、回访"中学习 ✅ | 移动 feed + 文献图谱（参考/被引/基础文献）+ 每周趋势简报；App Store 描述另列 TLDR 摘要、可公开或私有的 Collections、论文评论讨论、Following/Discover/Latest 三栏 ✅ | OpenAlex + Semantic Scholar（"数十万篇"）✅ | App 免费下载，其余未披露 | **续核验补充**：iOS 版 2026-04-21 上架（开发者 Chris Colpitts，v1.0.8，美区 0 条评分）✅；用户数未披露 | 未采集 | [R69][R84] |
| **AMiner 科技情报订阅**（智谱/Z.ai） | 学术搜索、学者画像、文献追踪/科技情报订阅 | 用户设定领域/作者/频率/渠道，AI 智能体筛选总结每日新论文，推送邮箱或微信 ◐ | Web + 小程序/邮件 ◐ | 自建学术图谱：3.3 亿论文、6,000 万学者、28 亿引用关系、1.8 亿专利、879 万知识实体（官方文档，统计截至 2026-06；续核验升级 ✅）；2025-09 接入 GLM 升级为 AI 科研助手 ✅ | 高校机构试用/采购（图书馆通知 ◐） | 母公司 Z.ai 2026-01-08 港交所上市（代码 2513）✅ | 未采集 | [R54] |
| **Read by QxMD**（加拿大 QxMD，2019-08-12 被 WebMD 收购，现归 Medscape；**续核验补充**） | 医学与科研文献的"个性化数字期刊"：追踪新研究、专题综述、PubMed 检索、个人收藏 ✅ | 按用户关注的期刊/主题重排为个性化期刊（是否学习型未公开 ⚠） | iPhone/iPad（Android/Web 版据检索摘要 ◐）；**一键取全文 PDF，走用户本人的大学/机构订阅或 OA 出版商**；分享、收藏 ✅ | PubMed + 期刊 + 专题综述库 ✅ | 个人免费（App Store）✅；另有"Read, Institutional Edition"机构版 ✅ | iOS 2012-11-24 上架，美区 4.8★（6,040 条评分）✅；收购公告称"数百万会员"✅ | 应用描述引 iMedicalApps"医学期刊的 Flipboard"；覆盖以医学为主（推断） | [R82] |

#### 2.2.B 社区热度与讨论型

| 产品 | 定位与核心功能 | 机制 | 形态 | 数据来源 | 商业模式·定价 | 规模（日期） | 口碑·痛点 | 证据 |
|---|---|---|---|---|---|---|---|---|
| **Hugging Face Papers**（Daily / Trending） | AI 论文每日精选 + 社区讨论；论文页联通模型/数据集/Space | 最初由 AK 与社区研究者人工精选；已认领论文的用户可提交；upvote 决定可见度；`@librarian-bot` 推荐相关论文 ✅。Trending 榜（2026-09-26 实测）前 10 含 2023-09 的 vLLM/PagedAttention、2024-12 的 TradingAgents——**非纯新鲜度排序**，算法未公开 ✅/⚠。**续核验补充**：同日 19:26 UTC 复读，Trending 榜首是 2026-02 发表、仅 14 票的 SPEED-Bench，147 票的 TradingAgents 排第 2——**Trending 分数也不等于累计票数** ✅ | 网页按日列表；点赞、评论（自动翻译）、作者一键认领；工作日邮件 ✅。**续核验补充**：官方 OpenAPI 规范列出 `GET /api/daily_papers`（参数 `date`/`week`/`month`/`submitter`、`sort=publishedAt\|trending`、`limit`≤100）与 `GET /api/papers/search`（语义 + 全文混合检索）✅；限速与数据使用条款 ⚠ | arXiv 论文 + HF Hub 资源 ✅ | 免费 ✅（服务于 HF 平台生态，推断） | 2024-09：累计精选 3,700+ 篇、邮件订阅 12,000+ ✅；2026-09-25 当日榜点赞长尾：第 1 名 193、第 2 名 62、第 3 名 31（首轮核验时第 2 名为 63；续核验 19:26 UTC 复读为 195/64/32，实时数据漂移），MCP 返回的前 22 篇中 19 篇 ≤ 20 票 ✅ | 领域集中 AI/ML；热度马太效应（推断，据长尾数据） | [R27][R28] |
| **alphaXiv** | arXiv 之上的讨论层 + AI 研究工具，面向应用 AI 团队（新闻稿主题"弥合 AI 研究到实践的鸿沟"；媒体称其目标为"AI 研究的 GitHub"◐） | 首页卡片展示点赞数、浏览数、日期、机构徽标、代码链接；"Researchers to follow"；AI"grounded answers"；排序算法未公开 ✅/⚠ | 网页卡片列表 + 论文评论 + AI 助手 ✅ | arXiv（获 arXiv Labs 支持）✅ | 未公开 | 2025-11-19 种子轮 $7M（Menlo Ventures、Haystack 共同领投；Eric Schmidt、Sebastian Thrun 等天使）；自称"数百万用户" ✅ | 未采集 | [R23][R24][R25] |
| **Emergent Mind** | arXiv（AI/ML 起家）前沿研究探索器 + 研究助手 | 监测 HN、X、Reddit、YouTube、GitHub 对新 arXiv 论文的提及，浮现 trending；GPT 生成概述（2024）✅ | 网页 trending、摘要、邮件 digest、书签、深度研究、讲解视频 ✅ | arXiv + 站外社交信号 ✅ | Basic 免费（5 篇/天）；Pro 年付 $10/月（月付 $12）；Max $25/$30；含 API 请求额度 ✅ | 创始人 Matt Mazur；用户数未披露 ✅ | 依赖第三方社交 API：作者 2024 年称 X API $100/月仅 1 万次读取 ✅（续核验：X API 现为按量计费，读取每条 $0.005 [R87]） | [R44][R81] |
| **Papers with Code**（Meta AI，已关停） | 论文 + 代码 + SOTA 榜单 | — | — | — | 免费 | 2025-07-24/25 无预告下线，域名重定向到 HF Trending Papers；历史数据仓库 941★ ✅/◐。**核验补充**：PwC 联合创始人 Ross Taylor 2025-07-25 在 X 发文说明（推文 ID 解码日期）；HF CEO（GitHub: julien-c）2025-09-04 在 issue #116 称系 HF 向 Meta 提议重定向"而非直接废弃域名"，并承认 Trending 只是"部分替代"；2025-12 起 PwC 论文/数据集页逐页重定向到 HF 对应页；2026-09-26 实测 paperswithcode.com 302 → huggingface.co/papers/trending ✅ | 社区失去 SOTA 榜单基础设施（◐） | [R26] |
| **Sciety**（eLife） | 聚合预印本公开评审/推荐，"关注你信任的评审团体" | 关注评审团体（eLife、Review Commons、PREreview、preLights 等）→ 更新 feed；用户可建列表分享 ✅ | Web feed、列表、newsletter ✅ | 各评审团体评估 + 预印本服务器 ✅ | 非营利；代码开源（sciety/sciety，MIT，17★，2026-09-14 仍有推送）✅ | eLife 组：**53,287 条评估、8,301 篇策展文章、318 名关注者**（sciety.org/groups 2026-09-26 实测；续核验升级 ✅，原文 51,752 条为 2026-07-22 口径）——内容供给大而关注者少 | 覆盖以生命科学为主（推断） | [R52] |
| **ResearchGate**（柏林，2008；**核验补充**） | 学术社交网络：个人主页、上传全文、关注、问答（问题按成员自填专长路由）、基于主页信息推荐相似研究者 ✅ | 关注/主页相似度；Q&A 专长路由 ✅ | 网页 + 社交 feed（移动端 ⚠） | 用户自传论文 + 出版商授权内容 ✅ | 融资含 Bill Gates、Goldman Sachs、Benchmark、Wellcome Trust（2013 年 C 轮 $35M；2015-11 $52.6M）✅ | 2,500 万成员（2023-09）✅ | **版权合规反面先例**：2017-09 STM 出版商协会致函威胁起诉，"负责任分享联盟"（ACS、Brill、Elsevier、Wiley、Wolters Kluwer）发起下架通知，RG 将大量受版权保护文章撤下公开视图；与 Elsevier、ACS 的诉讼于 2023-09-15 和解；另与 Springer Nature、CUP、Thieme 达成上传协议；2022-07 后移除 RG Score ✅ | [R75] |
| **PubPeer**（2012；**核验补充**） | 发表后同行评议/评论平台，允许匿名评论 ✅ | 按论文聚合评论 ✅ | 网页 + 浏览器插件（⚠） | 用户评论 ✅ | 非营利（⚠） | 2021 研究：超 2/3 评论举报不端（多为图像操纵），85.6% 匿名，仅 31.5% 的被评论论文收到 >3 条评论，作者回应率 7.5% ✅ | 曾遭诽谤指控，2016 起要求评论只陈述可公开核实的事实；匿名内容版权归属存疑 ✅ | [R76] |
| **Paper Skygest**（Sophie Greenwood、Nikhil Garg；Bluesky 自定义 feed；**核验补充**） | 在 Bluesky/AT Protocol 上为学者提供"我关注的人分享的论文"个性化 feed ✅ | 以用户社交网络内的论文帖为候选，个性化排序（代码公开）✅ | 社交 App 内原生 feed ✅ | Bluesky 帖子（链接到论文）✅ | 学术项目 ✅ | 周使用 5 万+ 次、日活 1,000+，全部自然增长；采用后用户与科研帖的互动增加（arXiv 2601.04253，2026-01-06）✅ | 依赖去中心化平台的开放 feed 能力，可在不与中心化平台合作的情况下做推荐实验 ✅ | [R77] |
| **ResearchHub**（2019，Brian Armstrong 与 Patrick Joyce 联合创立；**续核验补充**） | 开放科研社区，自述"GitHub 式协作 + 学术同行评议的严谨"：论文/预印本讨论、预注册、赏金市场 ✅ | 点赞（upvote）+ 行内评论排序；内部声誉算法混合传统指标与平台信号 ✅ | 网页 feed + 评论 + 赏金 ✅ | 用户发布或导入的论文与预印本 ✅ | 以加密代币 ResearchCoin（RSC）激励：同行评审每篇 **$150（以 RSC 计付，经资深研究者质检，约 10 天周转）**；作者可按过去 5 年被引领取奖励，预注册翻倍、开放数据三倍 ✅ | 2023-06-15 种子轮 $5M（Open Source Software Capital 领投；The Block 报道 ◐）；用户数未披露 | 用货币化激励换评价，与学术中立存在张力（推断） | [R83] |

#### 2.2.C 引文图谱探索

| 产品 | 定位与核心功能 | 机制 | 形态 | 数据来源 | 商业模式·定价 | 规模（日期） | 口碑·痛点 | 证据 |
|---|---|---|---|---|---|---|---|---|
| **Connected Papers** | 从种子论文生成相似论文图谱（含 prior/derivative works） | 官方 About：相似度基于**共被引（co-citation）与文献耦合（bibliographic coupling）**，"不是引文树"，互不引用的论文也可能紧邻；力导向图把相似论文聚在一起 ✅（续核验：读取官网前端包内文案） | 力导向图 + 列表 | Semantic Scholar Paper Corpus（ODC-BY）✅ | 免费层含全部功能、每月 5 张图 ✅；Academic $3/月（年付）或 $5/月（季付）、Business $10/月（年付）或 $15/月（季付）、团体账户——价格数字仅见检索摘要 ◐ | — | 未采集 | [R14] |
| **Litmaps**（新西兰 Litmap Ltd） | 引文地图 + 发现 + Monitor 提醒；2025-05 收购 ResearchRabbit | 以种子文章追溯引文网络构图；Monitor 按设定间隔对 Map 重跑检索推送新文（免费用默认算法，Pro 可调参）✅ | 地图 + 列表 + 邮件提醒 ✅ | OpenAlex + Semantic Scholar + Crossref（2022 改版起）✅ | Free（月度提醒摘要、20 个输入、每图 100 篇；定价页两处分别写"1 个"与"2 个"Litmap ◐）；Pro 教育版（需学术邮箱）年付 $120（折合 $10/月，页面称年付省 20%）；Team 定制；按国家折扣 ✅（续核验复读定价页 HTML） | 2022-12 "125K+ 研究者"；2025-05 收购后合计 200 万+ 用户；Litmaps 自身 ARR 在融资前翻倍至约 $1M；同时完成一轮 **$1M 融资的首次交割**（首交割折合约 $40.6 万，Scholarly Angels 领投，代表人为 Publons 创始人 Andrew Preston）✅（**核验修正**：原文"融资 $1M"系轮次目标额，非已到账额） | 未采集 | [R8][R12][R13] |
| **ResearchRabbit**（2025-05 起属 Litmaps） | 集合驱动的发现（相似/更早/更晚工作、作者网络 ⚠）；2025-10 起改 freemium | 种子集合推荐（算法未公开）；RR+ 提供"signals alerts"与高级过滤（关键词、日期、期刊分区与 h-index、OA、撤稿信息）✅ | 图谱 + 集合 + 笔记 ✅ | 310M+ 文章（2026 定价页）；2025 版并入 Litmaps 技术扩库 ✅ | 永久免费层（50 个种子、1 个项目、无限检索）；RR+ $12.50/月或 $120/年（100+ 国家平价折扣）；机构版含 LibKey、多用户管理 ✅ | 见 Litmaps | 2025 起由全免费转 freemium（学生群体流失风险，推断） | [R9][R10][R11] |
| **Inciteful** | 免费、免注册的引文网络发现 + Literature Connector（连接两组文献的引文路径） | 围绕种子论文构建引文网络，找"重要"与"相似"论文（链路预测）◐ | 网页图 + 列表 ◐ | ◐ | 免费 ◐ | 2026-09-26 实测 inciteful.xyz 301 跳转至 incitefulmed.com/academic/（原因 ⚠）；**核验补充**：新地址页面标题与描述仍为 "Inciteful \| Using Citations to Explore Academic Literature"，工具仍在运行（非关停），且页面预连接 api.openalex.org（数据源疑含 OpenAlex，⚠）✅；**续核验补充**：根域 incitefulmed.com 现为面向患者的医学循证问答产品"Inciteful Med"（称引用 PubMed 4,000 万+ 篇文献，设有定价页），学术工具退到 /academic/ 子路径——属学术发现工具转向 B2C 医疗的案例（两者同属一个团队只是依域名跳转所作推断 ⚠）✅ | 未采集 | [R74] |

#### 2.2.D AI 检索/问答/综述（Agentic）

| 产品 | 定位与核心功能 | 机制 | 形态 | 数据来源 | 商业模式·定价 | 规模（日期） | 口碑·痛点 | 证据 |
|---|---|---|---|---|---|---|---|---|
| **Elicit** | 证据型研究 AI：检索、系统综述、数据抽取、研究报告、Research Agent；向咨询/制药/医械企业扩张 | 语义检索 + LLM 抽取；Pro 含 10 个个性化研究提醒 ✅ | 对话 + 表格 + 报告 ✅ | 138M+ 论文（无限检索）✅ | Basic 免费；Pro 年付 $588（折合 $49/月）；Scale 年付 $2,028（折合 $169/月）；Enterprise ✅ | 2025-02-26 A 轮 $22M、估值 $100M（Spark Capital、Footwork 领投）；月活 40 万+ ✅ | 价格比发现类工具高一个数量级（事实：定价；判断：推断） | [R3][R4] |
| **Consensus** | AI 学术搜索引擎，目标"研究的 AI 操作系统" | 检索 + LLM 综合（细节 ⚠） | 对话/综合结论 | 220M+ 同行评审论文 ✅ | freemium（定价页未能解析 ⚠）；2024-08 约 1.2 万付费用户（Verdict）✅；年化收入：官方新闻稿称"近 $2M"、2024 年内增长 600%+，Verdict 称"年收入进度 $1.5M"（两处口径不一，续核验补充）✅ | 2024-08-14 A 轮 **$11.5M**（官方新闻稿 ✅，续核验升级；USV 领投，Nat Friedman、Daniel Gross、Draper Associates、Kevin Carter、Path Ventures、Alumni Ventures 参投；Verdict/Yahoo 2024-08-15 取整报"$11m"），40 万月活 ✅；**2026-05-11** 融资 $30M（GreatPoint Ventures 领投，DJ Patil 入董事会；USV、NFDG、Draper 等跟投），**250 万月活** ✅ | 付费转化约 3%（2024，推算） | [R1][R2] |
| **scite**（Research Solutions 旗下） | Smart Citations（支持/反驳/提及）+ Assistant + 引用提醒/仪表盘 + API/MCP | 引文上下文分类（出版商合作获取全文引文）✅ | 检索 + 引文报告 + 助手 ✅ | 1.6B+ 引文、300M+ 来源 ✅ | Connect 免费（MCP 额度）；Basic 年付 $14/月；Pro 年付 $35/月；团队/企业 ✅ | 2023-11-27 宣布被 Research Solutions（NASDAQ: RSSS）收购、2023-12-01 交割；当时约 2.1 万活跃订阅、年化订阅收入 $3.6M（截至 2023-10-31）✅；**核验修正**：SEC 10-K（FY2024）列总对价约 $21.1M（净额）= 现金 $7.2M + 股票 $6.5M + 保留款 $0.2M + 或有 earnout 初始公允价值 $7.2M（至 2024-06-30 重估为 $12.2M）✅；原文"$20.9M、50% 现金 50% 股票"混用了早期口径（50/50 仅指前期协议部分） | 未采集 | [R5][R6][R7] |
| **SciSpace**（原 Typeset.io） | 多 Agent 研究平台：文献综述、PRISMA 系统综述、生物医学 Agent（2025-12）、PDF 对话、Chrome 扩展、移动端 ◐ | Agent + 检索 ◐ | 对话/报告 ◐ | ◐ | 免费 + Premium $20/月（年付 $12）、Advanced $90（年付 $70）、Max $200（年付 $160）◐ | 用户数说法 1M+ 至 6M 不一；融资记载 $0.89M–$3.85M 不一（均 ◐/⚠） | 未采集 | [R34] |
| **Undermind**（YC S24） | 复杂问题的深度学术搜索 Agent：多跳推理、跟随引文与概念联系；全文分析；提醒 ✅ | Agentic 多跳检索 ✅ | 对话/报告 ✅ | 未列明 | Free；Pro 年付 $16/月；Team $15/人/月；Enterprise ✅ | 2023 年成立于旧金山；创始人 Joshua Ramette、Tom Hartke（MIT 量子物理博士）✅ | 未采集 | [R35][R36] |
| **Iris.ai**（奥斯陆，2015） | 面向企业研发与高校的 RSpace：智能检索、过滤、阅读清单分析、自动摘要、数据抽取 ✅ | — | 工作台 ✅ | — | B2B 为主 ✅ | 2024-05-29（新闻稿电头；官方博客 2024-05-30 发布）A 轮 €7.64M（Silverline Capital 领投，EIC Accelerator Fund 匹配投资），累计 €16M ✅ | 未采集 | [R37] |
| **Perplexity**（学术来源） | 通用 AI 答案引擎，来源可切为 "Academic" ◐ | API 侧用 `search_domain_filter` 限定 arxiv/pubmed/nature/semanticscholar 等学术域名（官方 cookbook）✅ | 对话 ✅ | 网页 + 学术站点；2025-05-08 Wiley 成为 Perplexity **首个教育合作方**：订阅机构的 Enterprise Pro 用户可在 Perplexity 内访问本机构**已购的 Wiley 教育类馆藏**（护理、商科、工程等），试点 Texas A&M、Texas State ✅（核验修正：范围为已购教育类馆藏，非泛指全部 Wiley 资源） | 订阅（本文不展开） | — | 未采集 | [R38][R39][R40] |
| **ChatGPT Deep Research**（OpenAI） | 通用深度研究 Agent（非学术专用），浏览 5–30 分钟生成带引用报告 ✅ | Agentic 浏览 ✅ | 报告 ✅ | 开放网页；2026-02 可限定站点、接入 MCP ✅ | 免费 5 次/月轻量；Plus 25；Pro（$200/月）250 ✅（Wikipedia 所载为 2025-06 口径；2026 现行额度 ⚠ 未核验） | 2025-02 上线；2026-02 升级为 GPT-5.2 基座 ✅ | OpenAI 承认会出现事实性幻觉/错误推断 ✅ | [R41] |
| **Google Scholar / Scholar Labs** | 通用学术搜索引擎；Scholar Labs（2025-11-18）把问题拆为主题/方面/关系，批量检索并逐篇解释相关性 ✅ | 被引、相关文章、检索/作者/被引邮件提醒 ✅；Labs=LLM 问题分解 + 逐篇解释 ✅ | 搜索页 + 邮件提醒 ✅ | 网络学术文献索引（覆盖口径未公开） | 免费 | Labs 上线时仅限部分登录用户 ✅。**续核验修正**：2026-06-03 官方博客称 Scholar Labs **已对所有登录用户开放、支持任意语言提问**，新版约快 10 倍、每次扫描论文至多 3 倍、每日可搜次数 10 倍（先上英文）✅；2026-08-25 推出 **Quick Read**：按查询生成单篇速读（概览 + Answers / Approach / Considerations），**只对用户有权访问的论文显示**，与出版商合作对订阅文章开放，目前仅限英文文章、登录用户 ✅ | 无官方 API；引用计数权重高→马太效应、收录掠夺性期刊、指标可被操纵（Wikipedia 综述）✅；帮助页要求自动化访问遵守 robots.txt ✅ | [R42][R43] |
| **Ai2 Asta**（含 Paper Finder / ScholarQA） | 开放科研 Agent 生态：Find Papers（改写查询、跟随引文、解释每篇为何相关）、Summarize Literature、Analyze Data（beta）；AstaBench 与基线 Agent 开源 ✅ | Agentic 检索 + 相关性解释 ✅。**核验补充**：Paper Finder 把查询解析为结构化对象，由执行规划器按"找论文意图"**路由**到不同 workflow，LLM 对召回的摘要/片段逐篇判相关，再结合查询中的"早期工作/有影响力"等约束排序（仓库 README ✅） | 对话/报告 ✅ | S2 200M+ 论文索引、年查询 15 亿+；OA 全文稠密/稀疏检索 ✅；Asta 可检索 108M+ 摘要 + 约 12.4M 全文（Ai2《Asta Getting Started Guide》2026-02 ✅，续核验升级）——全文部分与 S2 平台论文所述 snippet 索引"12M+ 篇论文、2.75 亿段落，mxbai 嵌入 + BM25 混合召回"一致（该指南写作 12.4M+ 篇、2.85 亿段落）✅ | 免费 ✅ | 2025-08-26 发布 ✅；asta-paper-finder 245★、ai2-scholarqa-lib 282★（Apache-2.0）✅ | 2026-02 公开 20 万+ 查询交互数据：查询更长更复杂；用户把 AI 当合作者（起草、找研究空白）；非线性回看输出与证据；经验越多查询越精准，但关键词式检索仍普遍 ✅ | [R19][R20] |
| **FutureHouse Platform / Edison Scientific**（**核验补充**） | 科研 Agent 平台（2025-05-01 上线）：Crow（通用文献问答，适合 API 调用）、Falcon（深度文献综述，可接 OpenTargets 等专业库）、Owl（原 HasAnyone，专答"之前有人做过 X 吗"）、Phoenix（实验性化学 Agent）✅；Edison Scientific 官网推出 "Kosmos: The AI Scientist for R&D"，并把 ChemCrow（2022）、PaperQA（2023，"首个深度研究 Agent"）、Aviary（2024）、Robin（2025）列为团队成果 ✅；**续核验补充**：Edison Scientific 是 FutureHouse 的**商业化分拆公司**（2025-11-05 两家官网同文公告：部分团队转入 Edison，平台管理移交 Edison，承诺保留"慷慨的免费层"，高用量用户付费）✅ | Agentic 文献检索与综合 ✅ | 对话/API ✅ | 科学文献 + 专业数据库 ✅ | Edison 面向药企/机构（官网"Book a demo"）✅；2025-12-18 种子轮 **$70M**（Triatomic Capital、Spark Capital 与一家美国机构型生物技术投资方领投，Pillar VC、Susa Ventures 等跟投；Edison 官网公告 ✅），估值约 $2.5 亿（TechFundingNews，◐） | FutureHouse 非营利团队 2023 年成立 ✅ | "Has anyone done X" 式查新是卡片"深挖"入口的候选集成点（推断） | [R78] |

#### 2.2.E 阅读、写作与文献管理

| 产品 | 定位与核心功能 | 与"发现"的关系 | 商业模式·定价 | 规模（日期） | 口碑·痛点 | 证据 |
|---|---|---|---|---|---|---|
| **Moonlight**（韩国 Corca） | AI 论文阅读伴侣：解释公式/表格、三行摘要、翻译、对话、引用预览、高亮 ✅ | 阅读侧栏，含 "Scholar Deep Search"（Premium）✅ | 免费 3 篇/周；Pro/Premium 无限 + 多模型（页面未显示金额）✅ | Chrome 扩展 10 万用户、4.7★（71 评分），2026-09-23 更新、支持 7 种语言 ✅；2024-05 上线 ◐ | **核验修正**（归因）：HN 帖（仅 1 分）中是 Moonlight 开发者自述——曾用向量嵌入尝试自动化 cs.CL 每日 digest 未做成 MVP，教训为①担心漏掉未经研究者审阅的论文（FOMO）②难界定"好/新颖"：领域趋势与冷启动会把跟风热门话题的论文推为"值得读" ✅ | [R45][R81] |
| **Scholarcy**（英国） | 论文→摘要闪卡 ◐ | 弱 | 约 $9.99/月；机构许可起 $8,000/年 ◐ | 20 万+ 用户 ◐ | 未采集 | [R50] |
| **Keenious** | **从你正在写的文档推荐论文**（Word/Google Docs 插件 + 网页），基于 OpenAlex（官网 FAQ：250M+ 作品、每月更新、经 Unpaywall 标注 OA ✅）；新增 Gemini 生成式功能 ◐ | 写作即查询（冷启动的另一种形态）✅ | Free（每天 3 次对话、每次 5 条 AI 回复）；Plus 年付 $10/月；Team $20/人/月；机构版（SSO/IP/馆藏集成）✅ | 多所高校机构订阅 ◐ | Katina Magazine 2026 书评标题称其"重现了学术检索的部分摩擦"（正文 403，◐） | [R51] |
| **Zotero** | 开源文献管理（zotero/zotero 15.4k★）；Zotero 8（2026-01-22）统一引用对话框、注释可搜索、阅读主题；发版周期改为约 6–10 周 ✅ | 无内置 AI 发现 ✅；社区插件可接入（如 zotero-cool-paper）✅ | 非营利，存储付费：300MB 免费、2GB $20/年、6GB $60/年、无限 $120/年 ✅ | — | — | [R47] |
| **Mendeley**（Elsevier） | 文献管理 + Mendeley Data | 2021-03 移动 App 下架、2022-09 停止 Desktop 下载、Desktop 文献检索被移除 ✅ | 免费为主 | 2013 年被 Elsevier 以约 €50M/$65M（估计）收购 ✅ | 收购引发开放科学社区反弹；2025-07-09 宣布 Desktop "保留"但仅维护、新功能只进 Reference Manager ✅ | [R48] |
| **Paperpile** | Google 生态文献管理 | 定价页未见 AI 发现功能 ✅ | Regular 约 $4.15–8.30/月、Expert 约 $5.75–11.50/月（学术 50% 折扣前后口径）◐；Enterprise 定制 ✅ | — | — | [R46] |
| **ReadCube Papers**（Digital Science） | 文献管理 + AI 助手 | 文献监测（保存检索追新）、AI 邮件摘要（Team）、Research Assistant（Enterprise）✅ | Essentials $10/月或 $95/年；Plus $20/月或 $185/年；Team/Enterprise 定制；文献传递附加项 ✅ | — | — | [R49] |
| **NotebookLM Audio Overviews**（Google；**核验补充**） | 把用户上传的资料（含论文）生成两位 AI 主持人的播客式"深度讨论"，可下载收听 ✅ | 不做发现；是"论文→音频速读"形态的最主要大厂先例（对照 I-11 的 30–60 秒音频） | 2024-09-11 发布时为实验性功能 ✅；定价 ⚠ 未核验 | — | 官方自述局限：发布时仅英语；主持人"有时会引入不准确内容"；不是全面或客观的观点；大笔记本需数分钟生成 ✅ | [R79] |

#### 2.2.F 出版商/数据库商自有 AI

| 产品 | 发布 | 能力 | 内容范围 | 获取方式 | 值得注意的声明 | 证据 |
|---|---|---|---|---|---|---|
| **Scopus AI**（Elsevier） | 2024-01-16 全球发售；2025-08-28 推出 Deep Research | 摘要综述、基础/高影响论文、学者专家检索；Deep Research 生成研究计划→多轮检索→带引用与置信度的报告 | 27,000+ 期刊、7,000+ 出版商、1.8B 引文；报告"仅基于 Scopus 同行评审内容" | Scopus 客户加购 | 负责任 AI 与隐私原则 | [R61] |
| **ScienceDirect AI**（Elsevier） | 2025-03-12 | Ask ScienceDirect AI（全文问答）、Reading Assistant、Compare Experiments（跨文献实验对比表） | 1,400 万篇全文文章与书章 | 面向客户销售 | 声明"不存储、不用于训练公共模型"，数据只在 Elsevier 私有环境 | [R62] |
| **Web of Science Research Assistant**（Clarivate） | 2023-12 beta，2024-09-04 正式；2025-04-10 文献综述 Agent | 多语言自然语言检索、引导任务（理解主题/综述/找期刊）、趋势图/主题图/共被引网络 | WoS 核心合集 120+ 年数据 | 机构订阅 | Clarivate 2025-04-09 称其 2024 年推出的研究/分析/元数据类 AI 助手已被 3,000+ 机构采用（**核验修正**：为多款助手合计口径，未单列 WoS RA） | [R63] |
| **Dimensions Research GPT**（Digital Science） | 2024-02-28（与 OpenAI 合作）；AI Assistant 2023 年 beta（新闻稿只写年份，"08 月" ◐ 未核验） | 在 ChatGPT 内检索并附引用 | 公开版检索 OA 出版物；Enterprise 版覆盖约 3.5 亿条出版物/基金/专利/临床试验记录 | ChatGPT Plus/Enterprise；Enterprise 版需 Dimensions 许可 | 每条回答内嵌来源 | [R64] |

共同模式：**只在自有内容内运行 + 全量内容只对订阅机构开放**（Dimensions 公开版仅限 OA；ScienceDirect AI 另明确声明数据不外流、不训练公共模型）。对本项目的含义见 I-12。

#### 2.2.G 中文生态

| 产品 | 定位与核心功能 | 发现/推荐机制 | 数据/规模 | 商业与现状 | 证据 |
|---|---|---|---|---|---|
| **玻尔 Bohrium**（深势科技 DP Technology） | AI for Science 科研空间站（读-算-做-智）：玻尔·科学导航（文献检索/阅读）、勒贝格智算、赛博实验室、SciMaster 科学智能体、PharmMaster/MatMaster ✅ | 文献检索 + 智能体编排（Bohrium + SciMaster 论文，2025-12）✅ | 1.7 亿+ 英文文献、8,000 万中文文献、2 亿+ 专利（公司口径）；服务 300 多万名科学家、1,000+ 高校与机构 ✅ | 2025-12-24 C 轮超 8 亿元（达晨财智、京国瑞基金、北京市 AI 产业投资基金、联想创投、元禾璞华等）✅ | [R53] |
| **AMiner / 智谱（Z.ai）** | 唐杰 2006 年创建 AMiner，现属 Z.ai；学术搜索、学者画像、文献追踪/科技情报订阅 ✅ | 订阅设定 → AI 筛选总结每日新论文，推送邮件/微信 ◐ | 见 2.2.A | Z.ai 2026-01-08 港交所上市（代码 2513）✅ | [R54] |
| **ReadPaper**（IDEA 研究院） | 论文阅读平台：阅读、翻译、笔记、社区问答 ⚠ | 未核验 | 近 2 亿论文、2.7 亿作者（◐） | 官方页证书错误未能打开（◐） | [R55] |
| **知网 CNKI AI 学术研究助手 / 知网研学** | 华知大模型底座：问答式增强检索（全库/近十年，可溯源）、AI 辅助研读（单篇问答、伴读、全文翻译、多篇主题分析）、AI 辅助创作、"苹果树"智能体（综述/趋势）✅ | 检索与问答为主，未见个性化 feed | 知网自有中文库 | 个人注册或关联机构账户；2025 年多所高校图书馆开通试用；知网研学接入 DeepSeek（◐）；入口 aiplus.cnki.net ✅ | [R56] |
| **秘塔 AI 搜索** | 无广告 AI 搜索；学术搜索（中英文库）、深度研究、专题知识库 ◐ | 检索为主 | — | 首页强调"没有广告，直达结果"，可免费使用 ✅ | [R57] |
| **Kimi（月之暗面）** | Kimi-Researcher（2025-06-20）：端到端强化学习训练的自主研究 Agent，每任务平均约 23 步推理、探索 200+ URL ✅；"Kimi 学术搜索"◐ | Agentic 检索 | — | 渐进开放 + 候补 ✅ | [R59] |
| **Cool Papers**（papers.cool，苏剑林） | "沉浸式刷论文"：按 arXiv 分类（支持并/差集，如 `cs.AI+cs.LG-cs.CY`）与会议 Venue 浏览；Kimi 生成 FAQ 式解读；星标、阅读记录、关键词偏好与词云；BM25（tantivy）站内检索；[REL] 相关论文 ✅ | **非学习型**：关键词偏好 + 星标排序 ✅；[REL] 基于"关键词 + 全文搜索"而非嵌入 ✅ | arXiv 全分类 + 会议 ✅；**核验补充**：2025-04-01 曾接入 bioRxiv，2025-06-04 因 bioRxiv 官网开启 Cloudflare 反爬而**主动下线、选择不对抗**（仓库更新日志）✅——与本项目"不绕反爬"红线一致的同行先例 | 免费；GitHub 809★（未声明 license，2026-07-06 仍有推送）✅ | [R58] |
| **百度学术** | 2025-09-11 "AI 重构"（第 12 届百度 AI Day 发布；日期依据新浪报道 URL，量子位 2025-09-14 报道 ✅）：AI 学术搜索 + 全网搜索、论文图谱、AI 阅读（翻译）、AI 文献总结（批量 100 文件）、选题推荐、创意对比、校对润色 ✅ | 双路召回（6.9 亿元数据向量语义检索 + 全网搜索补灰色文献）、70B 文心学术模型 ◐ | 6.9 亿文献、2.1 亿可获全文、1.6 亿免费、104 万+ 站点、日更 42 万+、420 万学者主页 ✅ | 免费为主 | [R60] |
| **小红书 / 抖音**（社媒"论文分享"生态） | 论文以图文笔记/短视频解读形态在大众平台传播（规模与质量 ⚠ 未系统核验） | 平台通用推荐算法 | 小红书 3 亿+ 月活、2024Q4 日均约 6 亿次搜索 ✅；抖音 2024 年万粉以上知识创作者 32 万、全年知识内容 5.7 亿条 ✅；小红书技术团队 REDtech 2024-06-27 办"大模型论文分享会"，视频号/B 站/抖音/小红书同步直播 ✅ | 广告/电商/创作者激励 | [R65][R66][R67] |

#### 2.2.H 滑动/短视频式原型与小型上架 App（与 v2 前端最相关）

| 项目 | 时间 | 交互 | 推荐 | 数据 | 关注度/反馈 | 证据 |
|---|---|---|---|---|---|---|
| **Papr**（Jeff Leek、Lucy D'Agostino McGowan、Nick Strayer，JHU Data Science Lab） | 2016 末首版（仓库 2016-10-04 建立），2017-06 走红 | Tinder 式**四向滑动**，两问题各两答（是否有趣 × 是否可信）：**右=令人兴奋且可信（probable）、上=令人兴奋但存疑、下=无聊但可信、左=无聊且存疑**（**核验修正**：原文左/下对调；依据仓库 `ui.R` 的滑动图例） | 有推荐引擎（源码公开，见 §2.3）；可导出评分；推荐口味相似的 Twitter 用户（早期"双向匹配"，about 页称仅在用户"选择公开身份"时） | bioRxiv 摘要 | **刻意隐藏作者、不可搜索作者/论文**以防"给名人加分、给对手打低分"；about 页自称"仅供娱乐、随时可能下线"；仓库 19★、最后推送 2019-05-15，现状 ⚠ | [R68] |
| **ArxivTok** | 最后推送 2025-02-07 | TikTok 式纵向滑动；双击点赞；收藏；实时搜索；KaTeX | 无推荐算法 | arXiv、medRxiv、bioRxiv、PubMed、HN | GitHub 91★（MIT） | [R69] |
| **ArTok** | Show HN 2025-04-21 | 滑动浏览；收藏；本地笔记；免注册 | **刻意随机流**（作者称无算法的随机流"用来探索可能挺有趣"） | 近期 ML 会议论文（自建 Postgres，因 arXiv/OpenReview API 不够稳） | HN 8 分/5 评论：希望有 30–60 秒音频摘要；指出学科分布失衡需加权 | [R69][R81] |
| **PapersTok** | 2025（◐） | 受 WikiTok 启发，按 arXiv 分类滚动 | ◐ | arXiv | Medium 页 403，仅检索摘要 ◐ | [R69] |
| **PaperCrush**（iOS，开发者 Naoki Takahashi；**续核验补充**） | 2025-05-04 上架（v1.4.1，2025-07-14） | Tinder 式左右滑："Like"/"Skip" 新论文；Like 列表（检索、分类筛选、已读/未读）；LaTeX 渲染；AI 翻译标题与摘要 | 按用户所选 arXiv 分类每日推送；"Trending"按其他用户关注度排行（描述未称学习型） | arXiv | 免费；美区 0 条评分 | [R84] |
| **ZiNote: Research Paper Reader**（iOS，开发者署名"小双 王"；**续核验补充**） | 2026-01-23 上架（v2.0.4，2026-07-09） | 像刷信息流一样滑论文：**右滑保存、左滑跳过**；期刊追踪（Nature/Science/Cell 等 4,000+ 种，显示影响因子）；一键 AI 摘要；端侧离线翻译 10+ 语言；BibTeX 导出 | 按关键词与兴趣生成每日个性化 feed，自称"从你的阅读行为中学习"（算法未公开 ⚠） | arXiv、PubMed、bioRxiv、medRxiv、Semantic Scholar、OpenAlex | 免费 20 篇/天，升级不限量；美区 5.0★（2 条评分） | [R84] |
| **PaperTok**（华盛顿大学 Prosocial Computing Group；**续核验补充**） | CHI 2026（2026-04-17 报告；UW 新闻 2026-06-25） | 作者上传 PDF → Gemini 生成讲解脚本与 4 个"开场钩子"选项 → 作者迭代修改后生成 **45 秒短视频**并署名 | 不做推荐（内容生成工具） | 作者上传的论文 | 100 名在线参与者 + 18 名学者参与评估：比两款同类 PDF 转视频工具更易用、视频更吸引人；但参与者担心"AI 味太重"、画面瑕疵损害学术信誉，团队也提示"任何人几分钟就能从 PDF 生成视频"带来的错误信息风险 | [R85] |

#### 2.2.I 关停/并购/转向参照

| 事件 | 时间 | 要点 | 证据 |
|---|---|---|---|
| Mendeley 被 Elsevier 收购 | 2013 | 约 €50M/$65M（估计）；后续逐步裁撤移动 App、Desktop 下载与检索 | [R48] |
| Microsoft Academic 退役 | 2016-02 上线；2021-05-04 宣布；2021-12-31 退役 | 数据被 OpenAlex 承接（开放许可使之可能） | [R71] |
| Meta（CZI 个性化论文 feed）关停 | 2017 被 CZI 收购；2021-10-28 宣布；2022-03-31 关停 | 曾提供按领域/基因/疾病/药物/期刊订阅的个性化论文 feed | [R72] |
| QxMD（Read by QxMD）被 WebMD 收购（**续核验补充**） | 2019-08-12 | 移动个性化医学文献 feed 并入 Medscape 体系；收购公告称 Read 服务"数百万会员" | [R82] |
| ResearchGate 与 Elsevier、ACS 诉讼和解（**核验补充**） | 2017-09 STM 致函；2023-09-15 和解 | 多用户学术平台托管出版商 PDF 引发大规模下架与诉讼——v2"auth-gated 全文不跨用户共享"红线的直接先例 | [R75] |
| scite 被 Research Solutions 收购 | 2023-11-27 宣布；2023-12-01 交割 | 2.1 万订阅、$3.6M 年化订阅收入；总对价约 $21.1M（含或有 earnout，SEC 10-K ✅） | [R5][R6] |
| Researcher App 关停（**续核验修正**） | 2024-11 月底 | 移动社媒式论文 feed（2020 年 160 万用户、长期免费、变现方式未披露）宣布关闭，团队转向新项目；公告只提示用户自行备份数据与书签 | [R32] |
| ResearchRabbit 被 Litmaps 收购 | 2025-05-08；2025-10 freemium | 由全免费转"免费层保留 + 可选 RR+ 订阅"（官方公告承诺"免费层会一直在"）✅ | [R8][R9] |
| Papers with Code 下线 | 2025-07-24/25 | 无预告，重定向到 HF Trending Papers | [R26] |
| FutureHouse 分拆 Edison Scientific（**续核验补充**） | 2025-11-05 分拆；2025-12-18 种子轮 $70M | 非营利科研 Agent 平台因药企需求超出非营利结构的承载能力，转由商业实体运营 | [R78] |
| Inciteful 域名跳转与转向 | 2026-09-26 实测 | inciteful.xyz → incitefulmed.com/academic/；根域已是面向患者的医学问答产品 Inciteful Med（续核验补充；同一团队属推断 ⚠） | [R74] |

### 2.3 推荐/发现机制拆解（可观察事实）

| 产品 | 候选召回 | 用户信号 | 排序/学习 | 冷启动 | 推荐解释 | 证据 |
|---|---|---|---|---|---|---|
| S2 Research Feeds | FAISS 在近期论文（论文口径：近 60 天约 100 万篇、每晚刷新；FAQ 口径：近 3 个月）的 SPECTER 索引中召回，取正例质心最近约 500 篇 | 收藏=正；"不相关"=负；另补降权的随机负例 | **每用户两个线性 SVM**（TF-IDF + SPECTER 嵌入），两分均值排序；arxiv-sanity 的扩展（核验补充，S2 平台论文 §3.4.5）；每日刷新 | 建议 5 正 + 3 负 | S2 团队 CHI 2022 研究：附"作者/引文关系"说明显著提升参与度，且作者关系提示未导致偏向高被引作者 | [R15][R16][R17] |
| Scholar Inbox | 每日新预印本 + 会议 | 👍/👎 | GTE-Large(256d) + 每用户 LR，逐评分重训；5k 随机负样本；加权 BCE | 种子论文 + Scholar Maps + 决策边界附近分层主动学习 | — | [R21] |
| arxiv-sanity-lite（开源） | arXiv 新文 | 用户打标签 | tf-idf + SVM | 手动打标签 | — | [R70] |
| Paper Digest | 每日数万新文（多源） | 类目/关键词/作者设置 | "潜在影响力"估计 + 社交/在线指标 | 选 200+ 类目 | 一句话 highlight | [R33] |
| HF Daily/Trending | 人工与社区提交 | 点赞、评论 | 按日 + 点赞；Trending 混入老论文（官方算法未公开；hub-docs 的 paper-pages 文档亦未说明排序）；非官方复刻站 dailypapersHN 用 Hot = upvotes/(小时差+2)^1.5、Rising = upvotes/(小时差+1) 做时间衰减（✅ 仓库 README 原文；仅作公式参考，非 HF 官方算法） | — | librarian-bot 相关推荐 | [R27][R28][R29] |
| Emergent Mind | arXiv 新文 | 站外社交提及（HN/X/Reddit/YouTube/GitHub） | trending 分 | — | GPT 概述 | [R44] |
| alphaXiv | arXiv | 点赞、浏览、评论、关注研究者 | 未公开 | — | AI grounded answers | [R25] |
| Connected Papers | 种子论文邻域 | — | 共被引 + 文献耦合相似度（官方 About ✅，续核验升级） | 1 个种子 | 图中位置 | [R14] |
| Inciteful | 种子引文网络 | — | 重要性 + 链路预测相似 ◐ | 种子（建议 ≥5）◐ | — | [R74] |
| Litmaps / RR | 种子引文网络 + 保存检索 | 收藏/集合 | 引文网络检索；Monitor/signals 定期重跑 | 种子（RR 免费 50/RR+ 300） | 图谱 | [R10][R11][R12] |
| Scollr | 关注主题/作者/期刊 | 打开、保存、点赞、回访（隐式） | 未公开 | 选主题 | — | [R69] |
| Google Scholar Labs | 问题分解 → 多路检索 | — | LLM 评估是否回答问题 | — | **逐篇说明如何回答问题**；2026-08 起 Quick Read 按查询给出 Answers/Approach/Considerations 三段速读，**只对用户有权访问的论文显示**（续核验补充） | [R42] |
| Asta Find Papers | 查询改写 + 跟随引文 | — | LLM | — | **解释每篇为何相关** | [R19] |
| Undermind | 多跳搜索、跟随引文与概念 | — | Agent | — | 报告 | [R35] |
| 百度学术 | 双路召回：向量语义 + 全网搜索 ◐ | — | 70B 文心学术模型 ◐ | — | — | [R60] |
| AMiner 订阅 | 用户设定领域/作者 | — | AI 智能体筛选总结 ◐ | 设定表单 | 摘要 | [R54] |
| Papr | bioRxiv 摘要流（首张按发布日期加权随机） | 四向滑动（兴趣 × 可信度）；**只有"兴趣"维参与推荐**，"可信度"维仅被记录 | **核验修正**（源码公开，非"细节未公开"）：摘要词项 PCA 取 3 维，用户向量随"兴奋"滑动拉向该论文、随"无聊"滑动推向其反向；每次 75% 概率从距离候选中抽取、25% 随机探索（均按发布日期加权）；实现粗糙（`arrange(dist) %>% tail(10)` 实取距离最远的 10 篇，疑似 bug）——**不能作为推荐有效性的证据** | — | 推荐 PC 空间中欧氏距离最近的 Twitter 用户 | [R68] |
| R Discovery（续核验补充） | 兴趣设置 + 多源新文 | 过往检索、App 内点赞 | 官方称"从中学习"，模型未公开 | 选兴趣 | — | [R30] |
| ZiNote（续核验补充） | 按关键词/兴趣的多源每日新文 + 期刊追踪 | 右滑保存、左滑跳过；阅读行为 | 自称学习型，算法未公开 ⚠ | 设关键词/兴趣 | — | [R84] |
| Paper Skygest（核验补充） | 用户 Bluesky 关注网络内的论文帖 ✅ | ⚠ 未核验（仅读摘要，未读正文） | 个性化排序（代码公开）✅ | 复用用户既有关注关系（推断） | — | [R77] |
| PaperFlow（学术工作，2026-06-05） | 每日论文流 | 反馈 | Profiling→Recommending（多信号聚合，受展示位约束）→Adapting（兴趣漂移）；基准含 24 个模拟用户、1,200 用户日、20,727 篇论文 | 多源初始画像 | — | [R73] |

**可提炼的共性**（推断）：①召回通道只有五类——内容相似、引文图、规则关注、社交/热度、人工/社区策展；②学习信号只有三类——显式二元评分、收藏/入库、隐式行为；③可解释性目前只在 Agent 检索类（Scholar Labs、Asta）与学术原型（S2 CHI 2022）中出现，feed 类产品普遍缺失。

### 2.4 交互形态对比

| 形态 | 代表 | 单元信息 | 用户动作/反馈 | 优点 | 局限（含证据） | v2 借鉴 |
|---|---|---|---|---|---|---|
| 邮件/推送 digest | Scholar Inbox、S2 Alerts、Paper Digest、HF 工作日邮件、AMiner 微信推送、Emergent Mind | 标题 + 摘要/一句话 highlight | 点开；Scholar Inbox 可在站内评分 | 低打扰，适合"每日一扫" | 反馈回路弱（推断）；Scholar Inbox 注册用户 30 天活跃仅 35% [R21] | 保留每日/每周 digest 为次要触达，内嵌一键反馈链接 |
| 网页列表 feed（可评分） | S2 Research Feeds、Scholar Inbox、Cool Papers | 标题/作者/摘要/TLDR/Kimi FAQ | 收藏=正、"不相关"=负；星标 | 信息密度高，桌面批量筛 | 启动需多次主动操作（S2 建议 5+3）[R15] | 桌面端提供"列表模式"作为卡片流的高密度视图 |
| 社区热度榜 | HF Daily/Trending、alphaXiv、Emergent Mind | 标题 + 缩略图 + 点赞/浏览 + 机构徽标 + 代码链接 | 点赞、评论、关注研究者 | 社会证明强 | 长尾与马太效应（HF 当日 193 票 vs 多数 ≤20 票）[R28]；领域集中 AI | 作为一条"热度召回"通道，设曝光上限与探索位 |
| 移动社媒式信息流 | R Discovery、Read by QxMD、Scollr；Researcher（2024-11 关停） | 卡片：标题 + 期刊 + 摘要要点；音频/翻译；机构登录取全文（R Discovery、QxMD） | 关注、保存、点赞、打开（隐式） | 碎片时间可用 | Researcher 以规则订阅为主，且长期免费后于 2024-11 关停 [R32]；R Discovery 称从检索与点赞中学习，但模型未公开 [R30] | 移动端主形态 = 卡片流 + 隐式信号采集；变现与数据导出须在上线前设计好 |
| **滑动卡片**（Tinder/TikTok） | Papr、ArxivTok、ArTok、PapersTok；上架 App：PaperCrush、ZiNote（续核验补充） | 仅摘要（Papr 隐藏作者）；标题 + 摘要 + 公式；AI 摘要/翻译（ZiNote、PaperCrush） | 四向语义（Papr）；双击点赞；右滑保存/左滑跳过（ZiNote）；Like/Skip（PaperCrush） | **一次滑动 = 一个训练标签**，反馈成本最低 | 原型或个人开发者级、关注度低（ArTok HN 8 分；ArxivTok 91★；PaperCrush/ZiNote 美区评分 0/2）；多为无算法/随机流（ZiNote 自称学习但未公开）；学科分布失衡 [R69][R84] | 采用 Papr 式"兴趣 × 可信度"分维；滑动即核心反馈事件；必须配推荐与摘要/音频 |
| 论文短视频/音频（续核验补充） | PaperTok（UW，CHI 2026）、NotebookLM Audio Overviews | 45 秒视频（作者审定后署名）；双主持人播客式讨论 | 观看、分享 | 适合碎片时间与社媒分发 | 参与者担心"AI 味"与瑕疵损害学术信誉、易被用于制造错误信息 [R85]；NotebookLM 官方承认会引入不准确内容 [R79] | 作为卡片的可选层：只基于开放内容生成、附原文锚点、优先作者审定版本 |
| 引文图谱 | Connected Papers、Litmaps、ResearchRabbit、Inciteful、百度学术论文图谱、WoS RA 共被引网络 | 节点=论文，边=引文/相似 | 选种子、扩展、Monitor | 系统综述与"补课"利器 | 学习成本高，不适合日常刷（推断） | 作为卡片"展开→相关图谱"的二级页 |
| 对话/报告（Agentic） | Elicit、Consensus、Undermind、Scholar Labs、Asta、Deep Research、Scopus AI DR、CNKI、秘塔、Kimi | 带引用的回答/报告/表格 | 提问、追问、导出 | 解决复杂问题 | 幻觉风险（OpenAI 自承）[R41]；成本高（Elicit Pro 折合 $49/月）[R4] | 以"深挖/搜索页"方式集成（可调用开放服务），不正面竞争 |
| 阅读侧栏/写作嵌入 | Moonlight、Semantic Reader、ReadPaper、Keenious | 解释/翻译/引用预览；基于草稿推荐 | 高亮、提问 | 嵌入工作流 | 与"发现"弱耦合 | 卡片"读原文"走用户自有权限；Keenious 式"从草稿推荐"可作冷启动入口 |
| 社区评审聚合 | Sciety | 预印本 + 评审团体评价 | 关注团体、建列表 | 质量信号可信 | 覆盖以生命科学为主（推断） | 作为卡片质量徽章来源之一 |

### 2.5 竞品能力矩阵（找空白）

图例：✔ 有（已核验）；◐ 部分/受限；✗ 明确没有；— 未见公开说明；? 未核验。

| 产品 | 学习型个性化 | 显式负反馈 | 规则订阅/提醒 | 热度/社交信号 | 引文图谱 | AI 摘要/问答 | 移动 App | 卡片滑动 | SSRN/NBER/RePEc 覆盖 | 用户自带权限取全文 |
|---|---|---|---|---|---|---|---|---|---|---|
| Semantic Scholar | ✔ | ✔ | ✔ | — | ◐ | ✔ | ? | ✗ | ◐（数据合作方含 SSRN；NBER/RePEc 未列） | ? |
| Scholar Inbox | ✔ | ✔ | ◐ | — | ◐ | ◐ | ◐（移动网页视图，非 App） | ✗ | ✗ | — |
| HF Papers | — | — | ◐ | ✔ | — | ◐ | ? | ✗ | ✗ | — |
| alphaXiv | ? | ? | ◐ | ✔ | ? | ✔ | ? | ◐ | ✗ | — |
| Emergent Mind | ? | ? | ✔ | ✔ | ◐ | ✔ | ? | ✗ | ✗ | — |
| Paper Digest | ◐ | ? | ✔ | ✔ | — | ✔ | ? | ✗ | ? | — |
| R Discovery | ✔ | ? | ✔ | ? | — | ✔ | ✔ | ◐ | ?（数据源含 OpenAlex） | ✔（机构登录，GetFTR + LibKey） |
| Read by QxMD（续核验补充） | ? | ? | ✔ | — | — | — | ✔ | — | — | ✔（机构订阅/OA 一键取 PDF） |
| ZiNote / PaperCrush（续核验补充） | ◐（ZiNote 自称学习）/ ✗ | ◐（左滑跳过）/ ◐（Skip） | ✔ / ✔（按分类） | — / ◐（用户热度榜） | — | ✔（AI 摘要）/ ◐（AI 翻译） | ✔ | ✔ | ?（ZiNote 数据源含 OpenAlex）/ ✗（仅 arXiv） | — |
| Scollr | ✔ | ? | ✔ | ? | ✔ | ◐ | ✔ | ◐ | ? | ? |
| Litmaps / ResearchRabbit | ◐ | ? | ✔ | — | ✔ | ? | ? | ✗ | ? | ◐（RR 机构版 LibKey） |
| Elicit / Consensus / Undermind | — | — | ◐ | — | ◐ | ✔ | ? | ✗ | ? | ? |
| Google Scholar（+Labs） | ? | ? | ✔ | — | ◐ | ✔（Labs 2026-06 起全体登录用户；Quick Read 按访问权限显示） | ? | ✗ | ? | ✔（图书馆链接 + 校外访问链接，记录用户在校内的订阅权限） |
| 百度学术 | ? | ? | ? | — | ✔ | ✔ | ? | ✗ | ? | ? |
| AMiner | ◐ | ? | ✔ | ? | ? | ✔ | ◐（小程序） | ✗ | ? | — |
| Cool Papers | ◐（关键词偏好排序，非学习） | ? | ◐ | ◐（星标） | ◐（REL） | ✔ | ? | ✗ | ✗（arXiv + 会议） | — |
| Papr / ArxivTok | ✔ / ✗ | ✔ / ✗ | — | — | — | ✗ | ? | ✔ | ✗ | — |
| Sciety | — | — | ✔ | ◐ | — | — | ? | ✗ | — | — |
| 出版商 AI（Scopus/SD/WoS/Dimensions） | — | — | ◐ | — | ◐ | ✔ | ? | ✗ | ? | ✔（仅机构订阅内） |
| **本项目 v1**（仓库现状） | ✗ | ✗ | ✔（订阅 DSL + watch + 日报） | ✗ | ◐（preprint_of 关系边） | ✗（仅全文抽取） | ✗（CLI） | ✗ | ✔（SSRN/NBER/RePEc/AEA/ECMA） | ✔（cookie/EZProxy/SSO/API key，个人） |
| **v2 目标** | ✔ | ✔ | ✔ | ✔ | ✔ | ✔（仅开放内容） | ✔ | ✔ | ✔ | ✔（仅本人私域） |

读法：表中没有任何一行在"学习型个性化 + 移动 App + 卡片滑动 + SSRN/NBER/RePEc 覆盖 + 自带权限"五列同时为 ✔；"✗"只用于数据源已被官方明确列出且不含这些 WP 源的产品（Scholar Inbox、HF、alphaXiv、Emergent Mind、Cool Papers、Papr/ArxivTok）。v1 恰好在后两列有既有资产（见 README 与 progress.md 的实现状态），前三列是 v2 要补的。

**续核验修正（读表时必须一并考虑）**：①"SSRN/NBER/RePEc 覆盖"列的"?"不能读作"没有"——S2 数据合作方页列有 SSRN，OpenAlex 收录"SSRN Electronic Journal"1,691,849 条、NBER 34,992 条（2026-09-26 API 实测）[R86]，因此基于 S2/OpenAlex 的产品（Litmaps、Keenious、Scollr、R Discovery、ZiNote 等）在元数据层面很可能已含 SSRN/NBER；v1 的真实差异是直连枚举带来的新鲜度、经管顶刊 TOC 与这些能力的组合，不是独家覆盖。②"用户自带权限取全文"列已有多个 ✔：R Discovery（GetFTR + LibKey）[R31]、Read by QxMD（机构订阅）[R82]、Google Scholar（图书馆链接与校外访问链接）[R43]，v2 可主张的差异只剩"任意类型的用户自有凭证 + 多用户平台内的私域隔离"。③"卡片滑动"列已有 ZiNote 这类"滑动 + 自称学习"的上架 App [R84]。五列同时为 ✔ 的产品仍未见。

### 2.6 商业模式与价格锚点

**价格带**（个人版，美元；年付折算除另注）：

| 价格带 | 产品与价格 | 证据 |
|---|---|---|
| 免费（资助/生态） | Semantic Scholar（全免费）、Scholar Inbox（资助）、Sciety（eLife）、HF Papers、Inciteful（◐）、Cool Papers、Asta、Read by QxMD（个人免费，WebMD/Medscape 生态）、Google Scholar Labs | [R15][R21][R52][R27][R19][R58][R82][R42] |
| ≤ $6/月 | R Discovery Prime $5/月或 $39/年；Connected Papers Academic $3/月（年付）或 $5/月（季付）（◐）；Paperpile Regular 约 $4.15 起（◐） | [R30][R14][R46] |
| $10–15/月 | Litmaps Pro（年付 $120）；RR+ $12.50/月或 $120/年；Emergent Mind Pro $10–12；Keenious Plus $10；ReadCube Essentials $10；Paper Digest $10.99（年付约 $6.66）；scite Basic $14；Zotero 无限存储 $120/年 | [R12][R11][R44][R51][R49][R33][R7][R47] |
| $15–20/月 | Undermind Pro $16；Connected Papers Business $15（季付；年付 $10，◐）；ReadCube Plus $20；SciSpace Premium $20（◐） | [R35][R14][R49][R34] |
| $35–50/月 | scite Pro $35；Elicit Pro（年付折合 $49） | [R7][R4] |
| $90–200/月 | Elicit Scale（年付折合 $169）；SciSpace Advanced $90 / Max $200（◐）；ChatGPT Pro $200（含 250 次 Deep Research） | [R4][R34][R41] |
| 机构/企业 | Scopus AI、ScienceDirect AI、WoS RA、Dimensions Enterprise、Iris.ai、Keenious 机构版、RR 机构版（LibKey）、ReadCube Enterprise、Elicit/Undermind Enterprise、Scholarcy 机构版起 $8,000/年（◐）、CNKI/AMiner 机构开通 | [R61][R62][R63][R64][R37][R51][R10][R49][R4][R35][R50][R56][R54] |

**单位经济学参照**：

| 指标 | 数值 | 证据 |
|---|---|---|
| Consensus 付费占比（2024-08） | 约 1.2 万 / 40 万 ≈ 3%（推算；源数据 ✅） | [R2] |
| Consensus 每付费用户年收入（2024-08，核验补充） | 年化收入 $1.5M（Verdict）至"近 $2M"（官方新闻稿）/ 1.2 万 ≈ $125–167/年（推算；两个来源口径不同，收入中可能含非个人订阅，仅作量级参考；续核验修正） | [R2] |
| scite 每订阅年收入（2023-10） | $3.6M / 2.1 万 ≈ $171/年（推算） | [R5] |
| Litmaps（2025-05） | ARR 约 $1M；合并后用户 200 万+（口径不同，不可直接相除） | [R8] |
| Elicit（2025-02） | 估值 $100M；月活 40 万+ | [R3] |
| Consensus（2026-05） | 融资 $30M；月活 250 万 | [R1] |
| alphaXiv（2025-11） | 种子轮 $7M | [R23] |
| 深势科技（2025-12） | C 轮超 8 亿元人民币；300 多万科学家 | [R53] |
| Edison Scientific（2025-12，续核验补充） | 种子轮 $70M（估值约 $2.5 亿 ◐） | [R78] |
| Researcher App（2020→2024，续核验补充） | 160 万用户（2020）、长期免费、变现未披露 → 2024-11 关停 | [R32] |

**已观察到的变现路径**：①个人订阅 freemium（多数初创）；②机构/企业授权（出版商 AI、Keenious、RR 机构版、Iris.ai、Elicit/Undermind Enterprise）；③作者服务交叉销售（R Discovery × Editage Plus）[R30]；④非营利/生态补贴（Ai2、eLife、HF、Scholar Inbox 基金）；⑤被收购退出（scite、ResearchRabbit、Mendeley；续核验补充：QxMD 2019 年被 WebMD 收购）；⑥（续核验补充）代币激励（ResearchHub 以 RSC 支付评审）[R83]；⑦（续核验补充）反例：长期免费、未披露变现的 Researcher App 于 2024-11 关停 [R32]。**未见**以广告为主要收入的海外学术发现产品（本轮样本内，推断）。

### 2.7 融资、规模与关停时间线

| 日期 | 事件 | 证据 |
|---|---|---|
| 2013 | Mendeley 被 Elsevier 收购（约 €50M/$65M，估计） | [R48] |
| 2016-02-22 | Microsoft Academic 上线（2021-12-31 退役） | [R71] |
| 2017 | CZI 收购 Meta（2022-03-31 关停） | [R72] |
| 2017-06 | Papr（Tinder for preprints）走红 | [R68] |
| 2018-05 | Paper Digest 上线 | [R33] |
| 2019-08-12 | WebMD 收购 QxMD（Read by QxMD；续核验补充） | [R82] |
| 2020-07 | Researcher 160 万用户 | [R32] |
| 2020 年末 | Semantic Scholar 约 700 万月活 | [R18] |
| 2022-12-06 | Litmaps 改版（OpenAlex + S2 + Crossref），125K+ 研究者 | [R13] |
| 2023-06-15 | ResearchHub 种子轮 $5M（The Block 报道 ◐；续核验补充） | [R83] |
| 2023-09-15 | ResearchGate 与 Elsevier、ACS 诉讼和解（核验补充） | [R75] |
| 2023-11-27 | scite 被 Research Solutions 收购（宣布；2023-12-01 交割，总对价约 $21.1M） | [R5][R6] |
| 2024-01-16 | Scopus AI 全球发售 | [R61] |
| 2024-01-18 | Emergent Mind Show HN | [R44] |
| 2024-02-28 | Dimensions Research GPT 发布 | [R64] |
| 2024-05-29 | Iris.ai A 轮 €7.64M（新闻稿电头；博客 2024-05-30 发布） | [R37] |
| 2024-06-27 | 小红书 REDtech 大模型论文分享会（多平台直播） | [R67] |
| 2024-08-14 | Consensus A 轮 $11.5M（官方新闻稿，续核验升级；USV 领投；40 万月活、年化收入近 $2M；Verdict 另报约 1.2 万付费） | [R2] |
| 2024-09-04 | Web of Science Research Assistant 正式上线 | [R63] |
| 2024-09-11 | NotebookLM Audio Overviews 发布（核验补充） | [R79] |
| 2024-09-23 | HF Daily Papers：3,700+ 篇、12,000+ 邮件订阅 | [R27] |
| 2024-11 月底 | Researcher App 关停（续核验修正） | [R32] |
| 2025-02 | ChatGPT Deep Research 上线 | [R41] |
| 2025-02-26 | Elicit A 轮 $22M（估值 $100M） | [R3] |
| 2025-03-12 | ScienceDirect AI 发布 | [R62] |
| 2025-04 | Scholar Inbox 论文：23k 注册、80 万评分数据集 | [R21] |
| 2025-04-09/10 | Clarivate 发布 agentic AI（文献综述 Agent） | [R63] |
| 2025-04-21 | ArTok Show HN | [R69] |
| 2025-05-01 | FutureHouse Platform 上线（Crow/Falcon/Owl/Phoenix，核验补充） | [R78] |
| 2025-05-04 | PaperCrush 上架 iOS（arXiv 滑动 Like/Skip；续核验补充） | [R84] |
| 2025-05-08 | Litmaps 收购 ResearchRabbit 并完成 $1M 轮首次交割（约 $40.6 万）；Wiley × Perplexity 教育合作 ✅ | [R8][R38] |
| 2025-06-20 | Kimi-Researcher 发布 | [R59] |
| 2025-07-09 | Mendeley 宣布 Desktop 仅维护 | [R48] |
| 2025-07-24/25 | Papers with Code 下线 | [R26] |
| 2025-08-26 | Ai2 Asta 发布 | [R19] |
| 2025-08-28 | Scopus AI Deep Research | [R61] |
| 2025-09-11 | 百度学术 AI 重构 | [R60] |
| 2025-10 | ResearchRabbit freemium（RR+） | [R9] |
| 2025-11-05 | FutureHouse 分拆商业公司 Edison Scientific（续核验补充） | [R78] |
| 2025-11-18 | Google Scholar Labs | [R42] |
| 2025-11-19 | alphaXiv 种子轮 $7M | [R23] |
| 2025-12-18 | Edison Scientific 种子轮 $70M（续核验补充） | [R78] |
| 2025-12-24 | 深势科技 C 轮超 8 亿元 | [R53] |
| 2026-01-06 | Paper Skygest 论文（Bluesky 学术个性化 feed，周使用 5 万+、日活 1,000+；核验补充） | [R77] |
| 2026-01-08 | Z.ai（智谱）港交所上市 | [R54] |
| 2026-01-22 | Zotero 8 发布 | [R47] |
| 2026-01-23 | ZiNote 上架 iOS（右滑保存/左滑跳过，自称学习型 feed；续核验补充） | [R84] |
| 2026-01-27 | OpenAI 推出 Prism（LaTeX 原生科研写作工作区；核验补充） | [R80] |
| 2026-02 | Deep Research 升级 GPT-5.2 基座；Asta 交互数据集公开（2026-02-26） | [R41][R20] |
| 2026-04-17 | PaperTok（论文→45 秒短视频）在 CHI 2026 报告（续核验补充） | [R85] |
| 2026-04-21 | Scollr iOS 版上架（续核验补充） | [R84] |
| 2026-05-11 | Consensus 融资 $30M，250 万月活 | [R1] |
| 2026-06-03 | Google Scholar Labs 对所有登录用户开放（续核验补充） | [R42] |
| 2026-06-05 | PaperFlow（每日论文流推荐）论文 | [R73] |
| 2026-08-25 | Google Scholar Quick Read（只对有权访问的论文显示 AI 速读；续核验补充） | [R42] |
| 2026-09-26 | 实测：inciteful.xyz 跳转 incitefulmed.com（根域已转向患者医学问答） | [R74] |

### 2.8 中文市场与社媒"论文分享"生态观察

1. **中文平台以"检索 + AI 问答/阅读"为主轴，而非推荐流**：知网 AI 学术研究助手（问答式增强检索/研读/创作）[R56]、百度学术（AI 学术搜索 + 论文图谱 + 选题推荐）[R60]、秘塔（学术搜索 + 深度研究）[R57]、玻尔（科学导航 + 智能体）[R53]。唯一接近"个性化推送"的是 AMiner 科技情报订阅（邮件/微信推送，◐）[R54]；唯一"刷论文"体验是 Cool Papers（非学习型）[R58]。
2. **资本与规模集中在"AI for Science 平台"与大模型公司**：深势科技 C 轮超 8 亿元、300 多万科学家 [R53]；智谱（Z.ai）2026-01 上市并持有 AMiner [R54]；百度学术背靠百度流量与文心模型 [R60]。独立的"论文推荐初创"在本轮样本中未见（推断）。
3. **大众社媒承担了"论文科普/速读"的需求**：小红书月活 3 亿+，2024Q4 日均搜索约 6 亿次，被视为年轻人的搜索入口 [R65]；抖音 2024 年万粉知识创作者 32 万 [R66]；小红书自家技术团队用"论文分享会"在视频号、B 站、抖音、小红书多平台直播 [R67]。**这说明"卡片化、短内容、社交分发"的论文消费方式在中文用户中已被广泛接受**（推断）；但具体的"论文分享笔记"数量、互动与质量本轮未能核验（⚠，见 §4）。
4. **对 v2 的含义**：①中文用户习惯"图文卡片 + 收藏 + 评论"，与 v2 卡片流天然契合；②中文摘要/翻译是刚需（R Discovery 30+ 语言翻译、Moonlight 7 语言、Cool Papers 中文 FAQ 均印证多语言需求）[R30][R45][R58]；③分享卡片（导出为图片/链接）是获客渠道，但分享内容必须限于元数据/摘要/OA（版权与 v2 红线）。

### 2.9 市场空白与差异化定位（个人科研 → 多用户平台）

| 编号 | 空白 | 证据 | 本项目的既有资产 / 对策 |
|---|---|---|---|
| G1 学科空白 | 主流 feed 产品集中在 AI/ML 与生命科学预印本：HF、alphaXiv、Emergent Mind、Cool Papers 以 arXiv 为主；Scholar Inbox 覆盖 arXiv/bioRxiv/medRxiv/ChemRxiv + 会议；Papr=bioRxiv。**经管金融工作论文（SSRN/NBER/RePEc）+ 顶刊 TOC 的个性化卡片流未见成熟产品**（推断，基于本轮样本）。**核验补充**：开放全文底座本身就偏科——S2ORC 全文可得量医学 290 万、生物 220 万、物理 120 万、CS 81 万，而经济仅 21 万、商业 23 万篇（S2 平台论文 Table 4 ✅）。**续核验补充**：元数据层面并非空白——OpenAlex 收录 SSRN 1,691,849 条、NBER 34,992 条，S2 数据合作方含 SSRN（2026-09-26 实测）；真正空白的是"经管 WP 的新鲜度 + 顶刊 TOC + 个性化卡片流"的组合 | [R27][R25][R44][R58][R21][R68][R16][R86] | v1 已实现 SSRN、NBER、RePEc、AEA、Econometric Society 与 Crossref 期刊枚举（README/progress）→ 差异化来自直连枚举的新鲜度与组合，不是独家覆盖（续核验修正） |
| G2 交互空白 | 学习型移动 feed 有 R Discovery、Scollr（信息流，非滑动）；滑动形态除原型（ArxivTok/ArTok，无学习）外，**续核验修正**：已有个人开发者上架的 PaperCrush（2025-05）与 ZiNote（2026-01，自称学习型），但美区评分数仅 0–2，没有规模或效果证据 | [R30][R69][R84] | v2 把"滑动=反馈事件"做成一等公民，并与推荐闭环 |
| G3 合规全文空白（**续核验修正：范围收窄**） | 原判断"机构权限接入仅见 RR 机构版（LibKey）、ReadCube 文献传递、出版商围墙内 AI"不成立——"机构登录后在 feed 中一键取全文"已有成熟先例：R Discovery（GetFTR + LibKey）、Read by QxMD（2012 年起按本人机构订阅一键取 PDF）、Google Scholar（图书馆链接 + 校外访问链接，记录用户在校内的订阅权限）；Google Scholar Quick Read（2026-08）也只对用户有权访问的论文生成 AI 速读。仍未见的是"任意类型用户自有凭证（cookie/EZProxy/SSO/API key，含个人订阅与站点账户）+ 多用户平台内私域存储与隔离"（推断） | [R10][R49][R61][R62][R31][R82][R43][R42] | v1 认证框架（cookie/EZProxy/SSO/API key）+ D-006 人在回路 → v2 做"每用户私有凭证库 + 私有全文存储" |
| G4 可解释与可控 | 解释能提升参与度已被 S2 研究证实，但 feed 类产品普遍缺"为什么推荐给我"；用户可调权重/屏蔽/盲评少见 | [R17][R42][R19] | 每张卡片带一行推荐理由 + 可调频道权重 + 可选"盲评模式" |
| G5 质量信号分散 | scite（支持/反驳）、Sciety（公开评审）、RR+（撤稿、期刊分区过滤）各管一段 | [R7][R52][R11] | 卡片内聚合质量徽章（需逐源核验许可） |
| G6 中英双语与社媒分发 | 中文平台重检索问答；"刷论文"只有 Cool Papers；社媒上论文科普需求大 | [R56][R60][R58][R65][R66] | 中英双语卡片 + 分享卡片（仅开放内容） |
| G7 双向匹配 | 现有只有弱形态：HF 作者认领 + 评论、alphaXiv 关注研究者、Papr 推荐相似口味 Twitter 用户；（续核验补充）ResearchGate 按主页信息推荐相似研究者、Q&A 按自填专长路由提问，Paper Skygest 复用用户既有关注网络 | [R27][R25][R68][R75][R77] | v2 可做"读者↔读者（相似口味）/读者↔作者（认领与回应）"的隐私优先、选择加入式匹配（需求强度 ⚠） |

**定位建议（推断）**：面向跨学科研究者（尤其 CS/AI × 经济/金融/管理交叉）的"合规优先的个性化论文卡片流"——开放元数据全覆盖（含 SSRN/NBER/RePEc 与顶刊）、滑动即反馈的可学习推荐、每卡可解释、用户可控、数据可导出、全文只走用户自有权限。避免与 Elicit/Consensus/Scholar Labs 正面竞争"AI 综述"，改为集成。

**从个人科研到多用户平台的演进路径（建议）**：

1. **阶段 1：实验室/小团队自托管多用户**——共享元数据层与推荐模型，凭证与全文按用户隔离；验证卡片流与反馈闭环（指标见 I-19）。
2. **阶段 2：邀请制托管服务**——推荐与卡片只用开放元数据/摘要/OA 全文；auth-gated 全文只在用户私域（本地或加密私有存储）；上线 digest 与分享卡片。
3. **阶段 3：机构版**——SSO、馆藏链接解析、席位管理；平台**不代理**机构访问给未授权用户（与 AGENTS.md 的"本地个人研究"边界、D-006 的人在回路原则一致；多用户化本身需要新 ADR 重新界定边界）。

### 2.10 本项目潜在商业模式（供决策参考）

| 模式 | 适配度 | 理由与风险 |
|---|---|---|
| B1 开源自托管 + 官方托管版 | 高 | 与 Zotero（开源 + 存储付费）[R47]、Sciety（开源 MIT）[R52] 同路；利于可信与合规审查；风险是托管版运营成本 |
| B2 课题组/机构席位 | 高 | 市场上可持续收入多来自机构（出版商 AI、Keenious、RR 机构版）[R61][R51][R10]；v1 认证与 EZProxy/SSO 能力可复用；风险是销售周期长 |
| B3 个人 Pro（$5–10/月） | 中 | 价格锚点见 §2.6；付费率低（Consensus 约 3%，推算）[R2]；适合"AI 摘要/音频/无限频道"等高成本功能 |
| B4 资助/学术合作 | 中 | Scholar Inbox（VolkswagenStiftung）、Ai2、eLife 先例 [R21][R19][R52] |
| B5 作者服务交叉销售 | 低 | R Discovery × Editage 可行但与平台中立性冲突 [R30] |
| ✗ 广告/付费推广/数据转售 | 不建议 | 与学术中立、推荐可信度冲突；数据转售与"凭证/阅读记录私密"红线冲突（推断） |

## 3. 对 v2 设计的启示

> 编号 I-# 可直接引用到后续 v2 设计文档/ADR；"落点"为建议归属的设计主题。

- **I-1 差异化定位写入需求**：以"跨学科（含经管金融 WP）+ 卡片滑动 + 可学习个性化 + 可解释 + 自带权限取全文"为 v2 的核心价值主张；AI 综述/问答做集成而非自研主战场。依据 §2.5、§2.9。**续核验修正**：上述五项各自都已有先例（机构登录取全文：R Discovery、Read by QxMD、Google Scholar；滑动 + 学习：ZiNote；SSRN/NBER 元数据：OpenAlex/S2），价值主张应写成"组合 + 经管 WP 新鲜度 + 多用户私域合规"，不能写成"唯一提供某项能力"[R31][R82][R84][R86]。落点：v2 需求文档。
- **I-2 数据层不做"规模竞赛"，做"新鲜度 + 学科覆盖"**：语料规模已是行业标配（1.38 亿–3.1 亿）[R4][R1][R30][R10]；v2 的指标应是"新文入库延迟（arXiv/SSRN/NBER/期刊 TOC）"与"学科覆盖率"。落点：数据源名录与 pipeline。
- **I-3 反馈事件模型采用"兴趣 × 质量"两维**：借鉴 Papr 四向滑动（兴趣与可信度分开）[R68]、S2"收藏=正/不相关=负"[R15]、Scholar Inbox 👍/👎 [R21]。建议：右滑=感兴趣（弱正）、左滑=不感兴趣（负）、收藏=强正并入库、点赞=社交正信号、评分/评价面板单独收集质量信号；长按给负反馈原因（不相关/已读/太难/质量存疑）。落点：前端交互 + 事件 schema。
- **I-4 冷启动三件套**：①导入种子（Zotero/BibTeX/DOI/arXiv ID 列表、v1 订阅 preset）；②科学地图/主题选择（Scholar Maps 先例）；③10–20 张"校准卡片"按不确定性采样（Scholar Inbox 主动学习）[R21]。S2 的经验值"5 正 + 3 负"可作为最低门槛 [R15]。落点：onboarding。
- **I-5 个性化模型的第一版用"共享嵌入 + 每用户轻量头"**：Scholar Inbox 证明每用户逻辑回归 + 逐评分重训已能达到 AUC≈0.87 [R21]；**核验补充**：S2 Research Feeds 的线上实现同属此范式——每用户在 TF-IDF 与 SPECTER 嵌入上各训一个线性 SVM、随机负例降权、FAISS 近邻召回后两分取均值 [R16]，即两个生产系统都选择"共享表示 + 每用户线性头"；arxiv-sanity-lite 的 tf-idf + SVM 是更低基线 [R70]。**续核验补充**：Scholar Inbox 表 2 中 TF-IDF 10k 维稀疏表示的 nDCG（88.67）反而高于其最终选用的 GTE-L 256 维（85.83），只是 AUC/F1 较低 [R21]——v2 的离线评测应把稀疏基线列为必测对照，并同时报告排序类与分类类指标。更复杂的序列/双塔模型留给后续迭代（由算法调研给出）。落点：推荐算法设计。
- **I-6 候选池分"新文池"与"常青池"**：S2 只推近期论文（FAQ：近 3 个月；平台论文：近 60 天约 100 万篇、每晚重建索引）、每日刷新 [R15][R16]；HF Trending 混入 2023–2024 老论文 [R28]，说明"经典/被重新关注的论文"也有需求。落点：召回策略。
- **I-7 多路召回至少五通道**：内容相似、引文图邻域（Connected Papers/Litmaps/Inciteful 思路）、规则关注（作者/期刊/关键词/v1 订阅 DSL）、热度/社交（HF 点赞、GitHub 星标等开放信号）、策展/评审（Sciety）；**社交信号优先选开放、低成本、ToS 明确的来源**——Emergent Mind 作者 2024 年即称 X API $100/月仅 1 万次读取 [R44]；**续核验更新**：X API 现为按量计费，读取每条 $0.005、每月上限 300 万条读取，超出需 Enterprise（官方文档，2026-09-26）[R87]；HF 官方 OpenAPI 已列出 `GET /api/daily_papers`（支持 `sort=trending`）与论文检索端点 [R28]，是成本最低的开放热度源（条款与限速仍 ⚠）；**核验补充**：Bluesky/AT Protocol 允许第三方部署自定义 feed，Paper Skygest 已在其上做到周使用 5 万+、日活 1,000+ 的学术个性化 feed 且代码公开 [R77]，可作为"开放社交信号"通道的首选调研对象（条款与限速仍需另行核验 ⚠）。落点：召回与数据源名录。
- **I-8 每张卡片必须有一行"为什么推荐"**：S2 团队 CHI 2022 研究显示关系型解释提升参与度且未偏向高被引作者 [R17]；Scholar Labs 与 Asta 都逐篇解释相关性 [R42][R19]。落点：卡片组件 + 解释生成器。
- **I-9 显式对抗流行度偏置与名人偏见**：Google Scholar 因重引用计数被批马太效应 [R43]；HF 当日点赞呈长尾（193 vs 多数 ≤20）[R28]；Papr 用隐藏作者对抗偏见 [R68]。建议：热度特征设上限、保留探索位（新作者/冷门论文）、评价流可选"盲评模式"。落点：排序与公平性。
- **I-10 质量/可信度徽章**：撤稿与期刊分区（RR+ 过滤维度）[R11]、支持/反驳引文（scite）[R7]、公开评审（Sciety）[R52]；每类徽章须核验数据许可后再上线。落点：卡片组件 + 数据源名录。
- **I-11 卡片内容 = 开放内容的 AI 速读**：Cool Papers 的 Kimi FAQ、Emergent Mind 的 GPT 概述、R Discovery 的音频/翻译都证明"速读层"是核心价值 [R58][R44][R30]；ArTok 用户明确要 30–60 秒音频摘要 [R69]；**核验补充**：大厂先例 NotebookLM Audio Overviews 官方即承认会"引入不准确内容"、发布时仅英语 [R79]，音频摘要须附原文锚点并允许一键回看原摘要；**续核验补充**：UW PaperTok（CHI 2026）的参与者担心"AI 味太重"会损害学术信誉 [R85]，Google Scholar Quick Read 则采用"按用户查询的结构化速读（Answers / Approach / Considerations）"[R42]——v2 的 AI 速读宜结构化、可溯源，视频层可选且优先作者审定版本。建议卡片 = 标题 + 一句话 TL;DR + 3 条要点 + 图（仅 OA）+ 徽章 + 推荐理由 + 可选音频。落点：卡片组件 + 摘要生成服务。
- **I-12 合规分层是 v2 的架构前提（建议立 ADR）**：出版商 AI 都只在自有内容内运行、全量内容只对订阅机构开放 [R61][R63][R64]，ScienceDirect AI 明确声明不存储、不训练公共模型 [R62]；Perplexity × Wiley 仅向已购相应 Wiley 教育类馆藏的机构的 Enterprise Pro 用户开放 ✅ [R38]；**核验补充**：反面先例是 ResearchGate——作为多用户平台托管用户上传的出版商 PDF，2017 年起遭出版商联盟下架通知与诉讼，至 2023-09-15 才与 Elsevier、ACS 和解 [R75]；**续核验补充**：正面先例是 Google Scholar——Quick Read（2026-08-25）只对用户有权访问的论文显示 AI 速读，并与出版商合作对订阅文章开放 [R42]；其"校外访问链接"记录用户在校内时的订阅权限，并向参与的出版商标示该用户的访问权 [R43]——两者都按个人访问权限提供全文或派生内容，而不是全局共享。另外，v1 需求 [00-requirements §5](../../archive-v1.md#docs-design-00-requirements-md) 第 6 条把"Web UI、多用户/团队协作"列为非目标、第 3 条禁止再分发——v2 多用户化须以新 ADR 显式修订第 6 条，并把第 3 条落实为下述分层。因此 v2 必须分为：**共享层**（开放元数据、摘要、OA 全文及其派生特征/摘要，可跨用户使用）与**私域层**（用户自有凭证取回的全文、其派生特征、阅读记录，只服务该用户，不进入全局模型、不缓存给他人、不出现在分享卡片中）。落点：新 ADR + 数据模型（多用户）。
- **I-13 社交层分期引入**：HF/alphaXiv 证明点赞与评论在 AI 社区可运转 [R27][R25]，Sciety 证明"关注评审团体"模式可行 [R52]；但评论需要审核与防刷。**核验补充**：PubPeer 的经验是论文评论区极度长尾且作者很少回应——仅 31.5% 的被评论论文收到 >3 条评论、作者回应率 7.5%，85.6% 为匿名评论且曾引发诽谤指控，平台 2016 年起要求只陈述可公开核实的事实 [R76]；v2 若开评论，应默认实名/ORCID、只允许可核实陈述，并预期多数卡片没有评论。**续核验补充**：ResearchHub 以代币 RSC 为同行评审付费（每篇 $150）并按被引发放奖励 [R83]，说明"激励换评价"可以运转，但货币化激励与学术中立存在张力（推断），v2 早期不建议引入；Sciety 上 eLife 组有 53,287 条评估，关注者却只有 318 人 [R52]，评价内容的供给不等于读者关注。建议阶段 1 只做私有反馈 + 可公开列表；阶段 2 再开评论（ORCID/机构邮箱实名）；"双向匹配"以选择加入的读者↔读者/读者↔作者匹配起步（Papr 推荐相似口味用户、HF 作者认领为先例）[R68][R27]。落点：社交与隐私设计。
- **I-14 保留并前移"订阅/提醒"资产**：几乎所有竞品都有提醒（S2 每日/每周、Elicit Pro 10 个提醒、Litmaps Monitor、RR signals、Undermind、Paper Digest、AMiner 推送）[R15][R4][R12][R11][R35][R33][R54]；v1 的订阅 DSL + watermark + 日报应升级为 v2 的"频道"，与卡片流共享召回。落点：订阅系统迁移。
- **I-15 深度检索做集成**：Elicit/Consensus/Undermind/Scholar Labs/Asta/Deep Research 已高度竞争且大厂下场（Deep Research 免费层 5 次/月）[R41]；Asta 提供免费的 S2 语料 MCP 工具 [R19]。v2 在卡片"深挖"入口调用外部/开放服务即可。落点：集成层。
- **I-16 可移植性与退出预案是硬约束**：Microsoft Academic、Meta（CZI）、Papers with Code 先后关停 [R71][R72][R26]，Mendeley 被收购后功能收缩 [R48]；**续核验补充**：最接近 v2 形态的 Researcher App 于 2024-11 月底关停，公告只让用户"自行备份数据与书签" [R32]。v2：用户库/评分/偏好可一键导出（BibTeX/RIS/JSON）；任何上游（S2 key、OpenAlex 信用额度——见 decision-log D-005 的 2026-07-20 修订与 D-021）必须有降级路径。落点：数据模型 + 数据源名录。
- **I-17 中英双语与分享卡片**：中文用户在小红书/抖音消费知识内容的规模巨大 [R65][R66]；v2 卡片支持中文摘要/翻译与"一键生成分享卡片"，分享内容仅限开放内容。落点：前端 + 国际化。
- **I-18 移动优先但保留桌面列表模式**：移动端（R Discovery、Read by QxMD、Scollr；Researcher 已于 2024-11 关停）走信息流 [R30][R82][R69][R32]，桌面端研究者需要高密度列表与图谱（S2、Scholar Inbox、Litmaps）[R15][R21][R12]。落点：前端信息架构。
- **I-19 用可对标的留存/参与指标立项**：Scholar Inbox 注册用户 30 天活跃 35% [R21]；HF 邮件订阅 1.2 万（2024-09）[R27]。建议 v2 看 D7/D30 留存、每会话滑动数、收藏率、"不相关"率、推荐理由点击率、digest 打开率。落点：可观测性与验收标准。
- **I-20 离线评测数据集**：Scholar Inbox 公开 80 万条评分数据集（仓库实列显式评分 774k + 隐式交互 556k）[R21][R22]。**核验修正**：GitHub API 的 NOASSERTION 只表示未识别为 SPDX 软件许可，仓库 LICENSE 文件实为 **CC BY-NC-ND 4.0**——只可用于非商业评测、不得发布改编后的数据；若 v2 走托管/商业化（§2.10 B1–B3），需另行取得授权或只把它用于内部非商业研究；PaperFlow（2026-06）提供"每日论文流"模拟基准 [R73]。落点：推荐算法测试方法。

## 4. 未决问题与风险

### 4.1 未决问题（需后续调研或用户决策）

1. **口碑数据缺口**：Reddit、X、知乎、小红书上的真实用户讨论本轮未能采集（WebSearch 会话配额耗尽）；应用商店评论因证书/截断未抓到（续核验已用 iTunes Lookup API 取到美区评分与评分数，评论正文仍未采集）。建议下一轮专门做"用户声音"采集（R Discovery、Elicit、Consensus、ResearchRabbit freemium 前后对比、小红书"论文分享"笔记样本）。
2. **待复核数字**：SciSpace 用户数（1M+ 与 6M 冲突）与融资额、Scholarcy 用户数与机构价、Connected Papers 价格数字、AMiner 订阅推送渠道、ReadPaper 语料与功能、ChatGPT Deep Research 2026 现行额度、Edison 估值、R Discovery 语料口径（官网与 App Store 不一）——均标 ◐/⚠。（核验轮已解决：scite 收购对价 → SEC 10-K；Consensus 2024 付费用户数 → Verdict/Yahoo；Perplexity × Wiley 细节 → Wiley 新闻稿。续核验轮已解决：Consensus A 轮 $11.5M 与年化收入 → 官方新闻稿；Connected Papers 算法与数据源 → 官网文案；AMiner 语料规模 → 官方文档；Sciety eLife 评估数 → 组列表页；Asta 108M 摘要 → Ai2 指南；FutureHouse/Edison 关系与融资 → 两家官网公告；Scollr 上线时间 → iTunes API。）
3. **滑动交互在研究者群体的真实接受度未知**：唯一有公开报道的 Papr（2017）未见后续规模数据；2025 年的 ArxivTok/ArTok 关注度低 [R68][R69]；续核验补充：2025–2026 上架的 PaperCrush/ZiNote 美区评分数仅 0/2 [R84]，也不能证明形态有效。需要 v2 原型的用户测试/A-B 验证"滑动 vs 列表"的留存与标注质量。
4. **auth-gated 全文的"私域派生"边界**：用户用自己凭证取回的全文，能否用于该用户自己的个性化特征（如全文嵌入）、能否缓存 AI 摘要？各出版商 TDM/许可条款不同，需逐家法务级核验（建议作为 v2 合规 ADR 的前置任务）。
5. **开放社交信号的可用性与条款**：HF Papers 数据的 API/条款、GitHub 星标、Bluesky 等替代 X 的来源在 2026 年的条款与成本未核验。（核验轮部分补上：Paper Skygest 证明 Bluesky 自定义 feed 可承载学术推荐 [R77]，但 AT Protocol 数据使用条款、限速仍 ⚠。续核验补上：HF 官方 OpenAPI 列出 `/api/daily_papers` 等端点 [R28]；X API 现为按量计费，读取每条 $0.005、每月上限 300 万条 [R87]。HF 的限速与数据条款仍 ⚠。）
6. **Scholar Inbox 数据集许可**：LICENSE 文件为 CC BY-NC-ND 4.0（非商用、禁止演绎）[R22]；未决的是 v2 的使用场景是否构成"商业"——若托管服务收费，需向作者申请授权。
7. **双向匹配的需求强度**：读者↔读者、读者↔作者匹配是否被研究者接受（隐私顾虑）缺乏证据，需用户访谈。
8. **2026 年通用 AI 厂商的科研专用产品线**（OpenAI/Google 等）本轮未系统核验，可能改变"集成而非竞争"的判断。（核验补充：OpenAI 2026-01-27 推出 Prism——LaTeX 原生的科研写作工作区，用于起草论文、管理引用、排公式 [R80]；FutureHouse 2025-05-01 上线科研 Agent 平台 [R78]；Google 有 Scholar Labs [R42] 与 NotebookLM [R79]。均偏写作/综述/问答，尚未见大厂做"个性化论文卡片流"，但需持续跟踪。续核验补充：Prism 免费、内置 GPT-5.2 [R80]；Google Scholar Labs 2026-06-03 起对所有登录用户开放，2026-08-25 又推出按访问权限显示的 Quick Read [R42]；FutureHouse 的平台已移交商业分拆公司 Edison Scientific（2025-12 种子轮 $70M）[R78]。大厂正把"AI 速读"做进搜索结果页，v2 的卡片速读层会直接与之比较。）

### 4.2 风险

| 风险 | 说明 | 缓解 |
|---|---|---|
| 合规与版权 | 多用户后，任何把 auth-gated 全文或其派生内容共享给他人的行为都构成再分发风险；出版商 AI 只在自有内容内运行、全量内容只对订阅机构开放 [R61][R62][R63][R64]；ResearchGate 因托管用户上传的出版商 PDF 遭下架通知与诉讼（2023-09-15 和解）[R75]；Cool Papers 在 bioRxiv 启用 Cloudflare 反爬后选择下线该源而非对抗 [R58] | I-12 分层；私域数据不入全局模型；分享卡片只含开放内容；**不提供用户上传/转存全文的公共托管**；遇反爬即降级到官方 API 或下线该源；新 ADR 明确多用户边界 |
| 上游依赖与关停 | S2 key/限速（D-021）、OpenAlex 信用计费（D-005 修订）、社交 API 收费（X 现为按量计费 [R87]）[R44]；行业关停先例 [R71][R72][R26]，含同类移动 feed Researcher App（2024-11）[R32] | 多源冗余、降级路径、数据可导出（I-16） |
| 变现困难 | 付费率约 3% 量级（推算）[R2]；学生价格敏感；长期免费、变现未披露的 Researcher App 最终关停 [R32] | 机构/课题组席位优先（B2），AI 高成本功能放 Pro；上线前定义可持续的成本与收入模型 |
| 大厂挤压 | Deep Research 免费层、Scholar Labs（2026-06 起全体登录用户）与 Quick Read、出版商 AI 下沉 [R41][R42][R61] | 不做通用综述；专注 feed + 学科覆盖 + 合规全文 |
| 推荐偏差 | 马太效应、名人偏见、信息茧房 [R43][R28][R68] | 探索位、热度上限、盲评模式、用户可控权重（I-9） |
| 社区治理 | 评论与点赞可被刷、需审核 | 分期上线、实名/ORCID、限流与举报（I-13） |
| 隐私 | 阅读记录与研究兴趣属敏感个人信息；多地数据保护法规要求（本轮未逐条核验 ⚠） | 最小化收集、端侧/私域存储选项、明确同意 |
| LLM 成本与幻觉 | 卡片摘要/音频按论文规模化生成成本高；幻觉风险 [R41] | 只对开放内容全局生成一次并缓存；摘要附原文引用锚点；可一键看原摘要 |
| 形态风险 | 滑动卡片未被验证 [R69]；已上架的滑动 App（PaperCrush、ZiNote）采用度极低 [R84]；论文短视频有"AI 味"与错误信息顾虑 [R85] | 列表/卡片双模式，A-B 驱动；视频/音频层可选 |

## 5. 参考来源

> 访问日期：除另注外均为 2026-09-26。标记：✅ 本轮打开核验；◐ 仅检索摘要/第三方/部分内容；⚠ 未核验。

- [R1] ✅ Consensus 融资 $30M 公告（2026-05-11）：https://consensus.app/home/blog/30m-in-new-funding-to-reach-the-next-10m-researchers/
- [R2] ✅（核验轮升级）Consensus A 轮（2024-08）：Verdict 原稿经 Yahoo Finance 转载，Helen Clarke，2024-08-15（"$11m"、40 万月活、1.2 万付费用户、"年化收入进度约 $1.5M"、USV 领投，Draper Associates、Nat Friedman、Daniel Gross 参投；核验时以 curl 取得正文）：https://finance.yahoo.com/news/ai-start-consensus-secures-11m-083505545.html ；✅ USV 投资博文（Jared Hecht，2024-08-14）：https://www.usv.com/writing/2024/08/consensus/ ；✅（续核验）Consensus 官方新闻稿（PRWeb，2024-08-14："$11.5 million in Series A"、USV 领投、"over 400,000 monthly active users"、"nearly $2M in annualized revenue"）：https://www.prweb.com/releases/consensus-raises-11-5-million-in-series-a-funding-to-make-the-worlds-scientific-research-discoverable-and-consumable-302222612.html ；◐ MobiHealthNews 同为 $11.5M（403）：https://www.mobihealthnews.com/news/consensus-raises-115m-ai-research-engine-scientific-papers
- [R3] ✅ Elicit Series A（2025-02-26）：https://elicit.com/blog/series-a/
- [R4] ✅ Elicit 定价：https://elicit.com/pricing
- [R5] ✅ Research Solutions 收购 scite 新闻稿（2023-11-27）：https://www.prnewswire.com/news-releases/research-solutions-announces-acquisition-of-scite-301997608.html
- [R6] ✅（核验轮升级）Research Solutions FY2024 10-K（SEC EDGAR，2024-09-20 提交，Note 9 Acquisition：2023-12-01 交割，总对价约 $21.1M = 现金 $7.2M + 股票 $6.5M + 保留款 $0.2M + earnout 初始公允价值 $7.2M，earnout 于 2024-06-30 重估为 $12.2M）：https://www.sec.gov/Archives/edgar/data/1386301/000155837024012920/rsss-20240630x10k.htm ；◐ 早期口径 $20.9M 与"前期协议 $14.8M、50% 现金 50% 股票"：https://www.marketscreener.com/quote/stock/RESEARCH-SOLUTIONS-INC-15295099/news/Research-Solutions-Inc-completed-the-acquisition-of-Scite-Inc-for-20-9-million-45517866/
- [R7] ✅ scite 定价：https://scite.ai/pricing
- [R8] ✅ Litmaps 收购 ResearchRabbit 并完成 $1M 轮首次交割（2025-05-08；正文："completed the first close of a USD $1 million funding round"，首交割"approximately USD $406,000"）：https://itbrief.co.nz/story/litmaps-acquires-researchrabbit-raises-1-million-for-ai
- [R9] ✅ ResearchRabbit 2025 发布公告：https://www.researchrabbit.ai/announcement-researchrabbit-release-2025
- [R10] ✅ ResearchRabbit 定价：https://www.researchrabbit.ai/pricing
- [R11] ✅ What is ResearchRabbit+（帮助文档，页面日期 2026-04-25）：https://learn.researchrabbit.ai/en/articles/12454495-what-is-researchrabbit
- [R12] ✅ Litmaps 定价：https://www.litmaps.com/pricing
- [R13] ✅ The all-new Litmaps（2022-12-06）：https://www.litmaps.com/spotlight-articles/the-all-new-litmaps
- [R14] ◐ Connected Papers 定价（JS 渲染，价格数字取自检索摘要）：https://www.connectedpapers.com/pricing ；✅（续核验）官网 About 与 FAQ 文案（curl 取前端包 `/assets/index-*.js` 内文本："Our similarity metric is based on the concepts of Co-citation and Bibliographic Coupling"、"connected to the Semantic Scholar Paper Corpus (licensed under ODC-BY)"、"5 Connected Papers graphs for free, every month"）：https://www.connectedpapers.com/about
- [R15] ✅ Semantic Scholar FAQ：https://www.semanticscholar.org/faq ；Research Feeds 调优：https://www.semanticscholar.org/faq/fine-tune-research-feeds
- [R16] ✅ The Semantic Scholar Open Data Platform（arXiv 2301.10140，v2 2025-04-25；核验轮通读 PDF：§3.4.5 推荐器实现、Table 4 分学科全文量、§4 API 规模与 snippet 索引）：https://arxiv.org/abs/2301.10140 、https://arxiv.org/pdf/2301.10140v2
- [R17] ✅ Kang et al., From Who You Know to What You Read（CHI 2022，arXiv 2204.10254）：https://arxiv.org/abs/2204.10254
- [R18] ✅ Semantic Scholar（Wikipedia）：https://en.wikipedia.org/wiki/Semantic_Scholar
- [R19] ✅ Ai2 Asta 发布博客（2025-08-26）：https://allenai.org/blog/asta ；✅（续核验）Ai2《Asta by Ai2 Getting Started Guide》（2026-02 PDF："around 12.4 million full-text papers and more than 108 million abstracts"；Scientific Corpus Tool "225M+ papers … 2.4B+ citation edges"、snippet 索引 "12.4M+ full-text publications, totaling 285M+ passages"）：https://allenai.org/papers/asta-guide ；仓库：https://github.com/allenai/asta-paper-finder （README：查询解析→规划器按意图路由 workflow→LLM 相关性判断）、https://github.com/allenai/ai2-scholarqa-lib （gh api）
- [R20] ✅ Haddad et al., The Asta Interaction Dataset（arXiv 2602.23335，2026-02-26）：https://arxiv.org/abs/2602.23335
- [R21] ✅ Flicke et al., Scholar Inbox（arXiv 2504.08385）：https://arxiv.org/html/2504.08385v1 ；ACL 2025 Demo pp.307–317：https://aclanthology.org/2025.acl-demo.30/
- [R22] ✅ Scholar Inbox 数据集仓库（gh api：6★，API license 字段 NOASSERTION；核验轮读取 LICENSE 文件为 CC BY-NC-ND 4.0，README 列显式评分 774k、隐式交互 556k、摘要句子标注 2,538 条）：https://github.com/avg-dev/scholar_inbox_datasets 、https://github.com/avg-dev/scholar_inbox_datasets/blob/main/LICENSE
- [R23] ✅ alphaXiv 种子轮新闻稿（2025-11-19）：https://www.prnewswire.com/news-releases/alphaxiv-raises-7m-seed-round-to-bridge-the-ai-research-to-practice-divide-302619615.html
- [R24] ◐ SiliconANGLE：AlphaXiv raises $7M in funding to become the GitHub of AI research（2025-11-19，检索摘要）：https://siliconangle.com/2025/11/19/alphaxiv-raises-7m-funding-become-github-ai-research/
- [R25] ✅ alphaXiv About 与首页：https://www.alphaxiv.org/about 、https://www.alphaxiv.org/
- [R26] ✅（核验轮读取评论）Papers with Code 重定向 issue #116（2025-08-14 建立；HF CEO julien-c 2025-09-04、2025-12-12/16 评论说明提议重定向与逐页重定向）：https://github.com/paperswithcode/paperswithcode-data/issues/116 ；◐ 评论中引用的 PwC 联合创始人 Ross Taylor 说明推文（ID 解码为 2025-07-25 UTC，未打开原推）：https://x.com/rosstaylor90/status/1948728240526557580 ；✅ 仓库（gh api：941★）：https://github.com/paperswithcode/paperswithcode-data ；✅ 2026-09-26 `curl` 实测 https://paperswithcode.com/ → 302 https://huggingface.co/papers/trending
- [R27] ✅ Exploring the Daily Papers Page on Hugging Face（2024-09-23）：https://huggingface.co/blog/daily-papers
- [R28] ✅ HF Hub 实时数据（HF MCP，2026-09-26 读取；续核验 19:26 UTC 复读）：`hf://papers/trending`、`hf://papers/daily/2026/09/25`（浏览器地址 https://huggingface.co/papers/trending 、https://huggingface.co/papers/date/2026-09-25 ）；✅（续核验）HF 官方 OpenAPI 规范（`GET /api/daily_papers` 的 `date`/`week`/`month`/`submitter`/`sort`/`limit` 参数，`GET /api/papers/search`）：https://huggingface.co/.well-known/openapi.json （hub-docs 的 api.md 指向该规范）
- [R29] ✅（核验轮升级，gh api 读 README：88★，最后推送 2024-09-23）AK391/dailypapersHN（Daily Papers 的 HN 风格非官方界面，README 中的 Hot/Rising/New 排序公式）：https://github.com/AK391/dailypapersHN ；✅ HF 官方文档 paper-pages.md 未说明 Trending 排序：https://github.com/huggingface/hub-docs/blob/main/docs/hub/paper-pages.md
- [R30] ✅ R Discovery（Editage）：https://www.editage.com/r-discovery
- [R31] ◐ R Discovery（Google Play，内容截断，检索摘要）：https://play.google.com/store/apps/details?id=com.rdiscovery&hl=en_US ；✅（续核验）App Store 元数据（iTunes Lookup API，id 1508182175：2020-04-20 上架、当前版本 2026-08-26、美区 4.8★/919 条评分；描述含"Full-text access with institutional login through GetFTR and LibKey integrations"与 1.5 亿+ 期刊文章等口径）：https://itunes.apple.com/lookup?id=1508182175&country=us
- [R32] ✅ Researcher app（Research Outreach，2020-07-23）：https://researchoutreach.org/articles/researcher-app-keep-scientists-top-science/ ；✅（续核验）官网关停公告存档（Wayback Machine 2024-11-19 快照："Closure of Researcher App … will be accessible until the end of November 2024"；现网 TLS 连接失败）：http://web.archive.org/web/20241119151936/https://www.researcher-app.com/
- [R33] ✅ Paper Digest FAQ：https://www.paperdigest.org/frequently-asked-questions/ ；✅（核验轮升级）Daily Paper Digest 页（"sorted by potential impact, social/online metrics"、200+ 领域、"tens of thousands of researchers"）：https://www.paperdigest.org/daily-paper-digest/
- [R34] ◐ SciSpace 第三方汇编：https://theaiagentindex.com/agents/scispace ；◐ https://tracxn.com/d/companies/scispace/__BgKebNxb1UNRuwBervIPD_az8snNCAA0GA1orTBDWHw （官方定价页 https://scispace.com/pricing 403）
- [R35] ✅ Undermind 定价：https://www.undermind.ai/pricing
- [R36] ✅ Undermind（Y Combinator）：https://www.ycombinator.com/companies/undermind
- [R37] ✅ Iris.ai Series A（正文电头"Oslo, Norway, May 29th"，博客 datePublished 2024-05-30；Silverline Capital 领投、EIC Accelerator Fund 匹配投资、累计 €16M）：https://iris.ai/blog/european-scientific-ai-startup-iris-ai-raises-7-64million-with-its-series-a-funding-round
- [R38] ✅（核验轮升级）Wiley × Perplexity（2025-05-08；Wiley 为 Perplexity 首个教育合作方，范围为订阅机构已购的教育类馆藏，试点 Texas A&M、Texas State）：https://newsroom.wiley.com/press-releases/press-release-details/2025/Wiley-and-Perplexity-Announce-New-AI-Search-Partnership/default.aspx
- [R39] ✅ Perplexity API Academic Search cookbook：https://docs.perplexity.ai/docs/cookbook/articles/academic-search/README
- [R40] ◐ Perplexity 开启 Academic 来源教程：https://www.guideflow.com/tutorial/how-to-enable-academic-sources-in-perplexity （官方帮助中心 403）
- [R41] ✅ ChatGPT Deep Research（Wikipedia）：https://en.wikipedia.org/wiki/ChatGPT_Deep_Research ；◐ https://openai.com/index/introducing-deep-research/ （403）
- [R42] ✅ Google：Introducing Google Scholar Labs（2025-11-18）：https://blog.google/products-and-platforms/products/education/google-scholar-labs/ ；◐ https://scholar.googleblog.com/2025/11/scholar-labs-ai-powered-scholar-search.html ；✅（续核验）Scholar Labs update（2026-06-03："available for all logged in users and supports questions in all languages"、~10x faster、up to 3x more papers、10x more searches/day）：https://scholar.googleblog.com/2026/06/scholar-labs-update-search-10x-faster.html ；✅（续核验）Quick Read（2026-08-25："Quick Read links appear only for papers that you have access to"、与出版商合作开放订阅文章、限英文文章与登录用户）：https://scholar.googleblog.com/2026/08/quick-read-see-how-paper-answers-your.html
- [R43] ✅ Google Scholar（Wikipedia）：https://en.wikipedia.org/wiki/Google_Scholar ；✅ 帮助页（提醒、robots；续核验补读"Off-campus access links"一节：记录用户在校内访问时的订阅、校外提供同样的订阅链接，并向参与的出版商标示用户的订阅访问权；不提供批量访问）：https://scholar.google.com/intl/en/scholar/help.html
- [R44] ✅ Emergent Mind About：https://www.emergentmind.com/about ；定价：https://www.emergentmind.com/pricing ；Show HN（2024-01-18）：https://news.ycombinator.com/item?id=39042157
- [R45] ✅ Moonlight 定价：https://www.themoonlight.io/en/pricing ；Chrome 商店：https://chromewebstore.google.com/detail/moonlight-ai-colleague-fo/lhipdkibljepmfojllcfflfflhflcbgi ；HN（2025-01-16，1 分；核验轮经 HN Firebase API 读取评论树，"FOMO/跟风"两点出自发帖人 treblenalto 的自述回复 id=42725712）：https://news.ycombinator.com/item?id=42724317 ；◐ https://www.corca.ai/en/moonlight
- [R46] ✅ Paperpile 定价（摘要口径混杂，价格标 ◐）：http://paperpile.com/pricing/
- [R47] ✅ Zotero 8（2026-01-22）：https://www.zotero.org/blog/zotero-8/ ；存储：https://www.zotero.org/storage ；仓库（gh api：15.4k★）：https://github.com/zotero/zotero
- [R48] ✅ Mendeley Desktop is Here to Stay（2025-07-09）：https://blog.mendeley.com/2025/07/09/mendeley-is-not-going-anywhere/ ；Mendeley（Wikipedia）：https://en.wikipedia.org/wiki/Mendeley
- [R49] ✅ ReadCube 定价：https://about.readcube.com/pricing
- [R50] ◐ Scholarcy 定价（403，检索摘要）：https://www.scholarcy.com/pricing
- [R51] ✅ Keenious 定价：https://keenious.com/pricing ；✅（核验轮）首页 FAQ（"250+ million academic works from OpenAlex… updated monthly… Unpaywall"）：https://keenious.com/ ；◐ Katina Magazine 书评（403，仅标题）：https://katinamagazine.org/content/article/resource-reviews/2026/ai-tool-recreates-friction-of-academic-search
- [R52] ✅ Sciety About：https://sciety.org/about ；✅（续核验升级）Groups 列表页（eLife："53287 evaluations 8301 curated articles 1 list 318 followers"，最近活动 2026-09-25）：https://sciety.org/groups ；仓库（gh api）：https://github.com/sciety/sciety
- [R53] ✅ 量子位：深势科技完成 C 轮（2025-12）：https://www.qbitai.com/2025/12/365728.html ；✅ Bohrium + SciMaster（arXiv 2512.20469）：https://arxiv.org/abs/2512.20469
- [R54] ✅ Z.ai / Zhipu AI（Wikipedia）：https://en.wikipedia.org/wiki/Zhipu_AI ；✅ AMiner：https://open.aminer.cn/ ；✅（续核验）AMiner 平台概述（官方文档：3.3 亿论文、6,000 万学者、28 亿引用关系、1.8 亿专利、879 万知识实体，统计截至 2026-06；2025-09 接入 GLM 升级）：https://docs.aminer.cn/user-guide/platform-overview/ ；◐ https://ai-bot.cn/sites/14355.html ；◐ 高校图书馆"AMiner AI 科研助手"试用通知（检索摘要）：https://tushu.guc.edu.cn/article/202503/16218.html
- [R55] ◐ ReadPaper（IDEA）：https://www.idea.edu.cn/news/2431.html （证书错误）；https://baike.baidu.com/item/ReadPaper%E8%AE%BA%E6%96%87%E9%98%85%E8%AF%BB%E5%B9%B3%E5%8F%B0/59341886 （403）
- [R56] ✅（第三方详述）CNKI AI 学术研究助手：https://ai-bot.cn/cnki-ai-for-academic/ ；官方入口 https://aiplus.cnki.net/ ；◐ 南方科技大学图书馆试用通知：https://lib.sustech.edu.cn/2025/0225/c29a7927/page.htm
- [R57] ✅（部分）秘塔 AI 搜索：https://metaso.cn/ ；◐ https://zhuanlan.zhihu.com/p/16819577986
- [R58] ✅ Cool Papers 仓库（gh api：809★；核验轮读 README 更新日志：2024-11-25 类别并差集、2024-08-12 偏好排序、2024-08-07 [REL]、2024-05-05 BM25/tantivy、2025-04-01 接入 bioRxiv、2025-06-04 因 Cloudflare 反爬下线 bioRxiv）：https://github.com/bojone/papers.cool ；◐ 作者博客：https://kexue.fm/archives/9907 （403）
- [R59] ✅ Kimi-Researcher（2025-06-20）：https://moonshotai.github.io/Kimi-Researcher/ ；◐ https://ai-bot.cn/kimi-academic-search/
- [R60] ✅ 量子位：科研学术，现在可以百度 AI 一下了（2025-09）：https://www.qbitai.com/2025/09/331407.html ；◐ 双路召回/70B 模型：https://finance.sina.com.cn/roll/2025-09-11/doc-infqcpuc1533654.shtml （证书错误，检索摘要）
- [R61] ✅ Elsevier：Launch of Scopus AI（2024-01-16）：https://www.elsevier.com/about/press-releases/launch-of-scopus-ai-to-help-researchers-navigate-the-world-of-research ；✅ Scopus AI Deep Research（2025-08-28）：https://blog.scopus.com/accelerate-your-workflow-with-deep-research-a-new-scopus-ai-feature/
- [R62] ✅ Elsevier launches ScienceDirect AI（2025-03-12）：https://www.elsevier.com/about/press-releases/elsevier-launches-sciencedirect-ai-to-transform-research-with-rapid-mission
- [R63] ✅ Clarivate：WoS Research Assistant 上线（2024-09-04）：https://ir.clarivate.com/news-events/press-releases/news-details/2024/Clarivate-Launches-Generative-AI-Powered-Web-of-Science-Research-Assistant/default.aspx ；✅ Agentic AI（2025-04-09）：https://ir.clarivate.com/news-events/press-releases/news-details/2025/Clarivate-Expands-its-Academic-AI-Platform-Introducing-Agentic-AI-for-Research-and-Learning/default.aspx
- [R64] ✅ Dimensions Research GPT（2024-02-28）：https://www.globenewswire.com/news-release/2024/02/28/2836711/0/en/Dimensions-Research-GPT-evidence-based-research-insights-for-ChatGPT-platform-users.html
- [R65] ✅ Xiaohongshu（Wikipedia）：https://en.wikipedia.org/wiki/Xiaohongshu
- [R66] ✅ 32 万知识博主"攻占"抖音（2025-04-29）：https://news.qq.com/rain/a/20250429A06LJP00
- [R67] ✅ 小红书技术 REDtech：2024 大模型论文分享会（CSDN 官方号）：https://blog.csdn.net/REDtech_1024/article/details/139864284
- [R68] ✅ Papr（ZME Science，2017-06-16；该文只列出四个类别、**未给出方向与类别的对应**）：https://www.zmescience.com/science/papr-swipe-on-papers/ ；✅（核验轮一手源）Papr 源码仓库 jtleek/papr（gh api：19★、无 license、2016-10-04 建立、最后推送 2019-05-15；`ui.R` 滑动图例、`server.R` 推荐器、`about.md`/`help.md`）：https://github.com/jtleek/papr 、https://github.com/jtleek/papr/blob/master/ui.R 、https://github.com/jtleek/papr/blob/master/server.R ；◐ https://www.science.org/content/article/great-paper-swipe-right-new-tinder-preprints-app （403）
- [R69] ✅ ArxivTok（gh api：91★，MIT，最后推送 2025-02-07）：https://github.com/Miguel07Alm/arxivtok ；✅ ArTok Show HN（2025-04-21）：https://news.ycombinator.com/item?id=43755405 ；◐ PapersTok：https://medium.com/@xinfitok/paperstok-arxiv-papers-with-a-tiktok-like-ux-72e2dc5b156d （403）；✅ Scollr：https://scollr.com/
- [R70] ✅ arxiv-sanity-lite（gh api：1,696★，MIT，最后推送 2023-06-19）：https://github.com/karpathy/arxiv-sanity-lite ；另见本仓库 [github-similar-projects.md](../../archive-v1.md#docs-research-github-similar-projects-md)
- [R71] ✅ Microsoft Academic（Wikipedia）：https://en.wikipedia.org/wiki/Microsoft_Academic
- [R72] ✅ Meta (academic company)（Wikipedia）：https://en.wikipedia.org/wiki/Meta_(academic_company)
- [R73] ✅ Wang et al., PaperFlow（arXiv 2606.07454，2026-06-05）：https://arxiv.org/abs/2606.07454
- [R74] ✅ Inciteful 域名跳转实测（inciteful.xyz → https://incitefulmed.com/academic/ ，301；核验轮复测一致，并读取新地址 HTML 的 title/description 与 `preconnect https://api.openalex.org`）；✅（续核验）根域首页元数据（title "Inciteful Med - Evidence-Based Medical Research for Patients"，称引用 PubMed 4,000 万+ 篇文献，设 Pricing）：https://incitefulmed.com/ ；◐ 功能描述：https://inciteful.xyz/ （检索摘要）、https://journals.library.ualberta.ca/istl/index.php/istl/article/view/2974/2860
- [R75] ✅（核验补充）ResearchGate（Wikipedia：2008 年柏林创立；2,500 万成员（2023-09）；融资；Q&A 专长路由；2017-09 STM 致函与"负责任分享联盟"下架通知；2023-09-15 与 Elsevier、ACS 和解；与 Springer Nature、CUP、Thieme 的上传协议；RG Score 2022-07 后移除）：https://en.wikipedia.org/wiki/ResearchGate
- [R76] ✅（核验补充）PubPeer（Wikipedia，经 MediaWiki API 取正文：2012 年上线；匿名评论；2021 研究的 2/3 举报不端、85.6% 匿名、31.5% 论文 >3 条评论、作者回应率 7.5%；2016 起只许陈述可核实事实）：https://en.wikipedia.org/wiki/PubPeer
- [R77] ✅（核验补充）Greenwood & Garg, Paper Skygest: Personalized Academic Recommendations on Bluesky（arXiv 2601.04253，2026-01-06；经 arXiv API 检索 `all:Skygest` 取得摘要）：https://arxiv.org/abs/2601.04253
- [R78] ✅（核验补充）FutureHouse Platform 发布（2025-05-01，Andrew White、Sam Rodriques 等）：https://www.futurehouse.org/research-announcements/launching-futurehouse-platform-ai-agents （重定向至 /news/launching-futurehouse-platform-ai-agents）；✅ Edison Scientific 官网（Kosmos、团队成果列表）：https://edisonscientific.com/ ；✅（续核验）分拆公告（2025-11-05，Sam Rodriques、Andrew White："a new commercial spinout"、平台移交、承诺"generous free tier"）：https://www.futurehouse.org/research-announcements/announcing-edison-scientific 、https://edisonscientific.com/news/announcing-edison-scientific ；✅（续核验）融资公告（2025-12-18："We have raised a $70M seed … led by Triatomic Capital, Spark Capital, and a major US institutional biotech investor"）：https://edisonscientific.com/news/we-raised-70m-to-accelerate-science ；◐ 估值约 $2.5 亿：https://techfundingnews.com/edison-raises-70m-ai-scientist-platform/
- [R79] ✅（核验补充）Google：NotebookLM Audio Overviews（2024-09-11）：https://blog.google/technology/ai/notebooklm-audio-overviews/
- [R80] ✅（核验补充）Products and applications of OpenAI（Wikipedia，经 MediaWiki API 取正文："On January 27, 2026, OpenAI introduced Prism, a LaTeX-native workspace…"；openai.com 原页 403 未能直读）：https://en.wikipedia.org/wiki/Products_and_applications_of_OpenAI ；✅（续核验）TechCrunch 2026-01-27（与 LaTeX 集成的网页应用，由 GPT-5.2 驱动，任何 ChatGPT 账户免费可用；OpenAI for Science 副总裁 Kevin Weil 称"2026 年之于 AI 与科学，将如 2025 年之于 AI 与软件工程"）：https://techcrunch.com/2026/01/27/openai-launches-prism-a-new-ai-workspace-for-scientists/ ；◐ 官方页（检索结果可见标题，未直读）：https://openai.com/index/introducing-prism/
- [R81] ✅（核验补充）HN Firebase API 原始数据（三帖的分数/评论数/评论树）：https://hacker-news.firebaseio.com/v0/item/39042157.json 、https://hacker-news.firebaseio.com/v0/item/43755405.json 、https://hacker-news.firebaseio.com/v0/item/42724317.json
- [R82] ✅（续核验补充）Read by QxMD App Store 元数据（iTunes Lookup API，id 574041839：WebMD Health Corporation；2012-11-24 上架、当前版本 2026-06-29；美区 4.8★/6,040 条评分；描述含"Get full text PDFs with one tap"与"Access full text through your university/institutional subscription or via open access publishers"）：https://itunes.apple.com/lookup?id=574041839&country=us ；✅ QxMD 官方收购公告（2019-08-12，WebMD 收购 QxMD；Read 服务"millions of members"；"Read, Institutional Edition"）：https://www.qxmd.com/webmd-acquires-qxmd
- [R83] ✅（续核验补充）The ResearchHub Story（2024-10-02：Brian Armstrong 与 Patrick Joyce 联合创立；upvote + 行内评论；声誉算法；RSC 奖励；评审每篇 $150 RSC；按被引发放奖励）：https://blog.researchhub.foundation/the-researchhub-story/ ；✅ 同行评审页（$150/篇、质检、约 10 天周转）：https://www.researchhub.com/peer-review ；◐ The Block（2023-06-15，$5M 种子轮，Open Source Software Capital 领投）：https://www.theblock.co/post/234960/scientists-can-earn-crypto-as-brian-armstrong-startup-raises-5-million
- [R84] ✅（续核验补充）App Store 元数据（iTunes Lookup API，2026-09-26）：PaperCrush（id 6745439518，Naoki Takahashi，2025-05-04 上架，v1.4.1，美区 0 条评分）：https://itunes.apple.com/lookup?id=6745439518&country=us ；ZiNote: Research Paper Reader（id 6756495932，2026-01-23 上架，v2.0.4，美区 5.0★/2 条评分，免费 20 篇/天）：https://itunes.apple.com/lookup?id=6756495932&country=us ；Scollr: Research Papers（id 6761957461，Chris Colpitts，2026-04-21 上架，v1.0.8，美区 0 条评分）：https://itunes.apple.com/lookup?id=6761957461&country=us （apps.apple.com 网页因证书链错误与地区重定向未能直读）
- [R85] ✅（续核验补充）UW News：PaperTok（2026-06-25；华盛顿大学 Prosocial Computing Group，Meziah Ruby Cristobal、Donghoon Shin、Gary Hsieh；CHI 2026 于 2026-04-17 报告；45 秒视频、Gemini 生成脚本与 4 个开场钩子；100 名在线 + 18 名学者参与评估；"too AI-ish"顾虑）：https://www.washington.edu/news/2026/06/25/papertok-an-ai-system-that-helps-users-turn-research-papers-into-short-engaging-videos/
- [R86] ✅（续核验补充）OpenAlex Sources API 实测（2026-09-26）："SSRN Electronic Journal"（S4210172589，works_count 1,691,849）：https://api.openalex.org/sources?search=ssrn ；"National Bureau of Economic Research"（S2809516038，works_count 34,992）：https://api.openalex.org/sources?search=National%20Bureau%20of%20Economic%20Research ；✅ Semantic Scholar 数据合作方页（"More than 50 direct partnerships…"，logo 列表含 SSRN，未见 NBER、RePEc）：https://www.semanticscholar.org/about/publishers
- [R87] ✅（续核验补充）X API 定价文档（按量计费；读取 Post 每条 $0.005；每个计费月上限 300 万条读取，超出需 Enterprise；价格以开发者控制台为准）：https://docs.x.com/x-api/getting-started/pricing

本仓库内部参照：[design/00-requirements.md](../../archive-v1.md#docs-design-00-requirements-md)（§5 非目标与合规：第 3 条禁止再分发、第 5 条 Google Scholar 不做自动化主源、第 6 条 v1 不做 Web UI 与多用户——v2 须以新 ADR 显式修订第 6 条并保留第 3 条实质约束）、[plan/decision-log.md](../../plan/decision-log.md)（D-006 人在回路认证、D-014 尊重 AI-bot 指令、D-005 修订：OpenAlex 2026-02-13 起改信用计费；D-021：S2 无 key 口径与 OpenAlex 成本核销）、[design/09-search-filter.md](../../archive-v1.md#docs-design-09-search-filter-md)（订阅 DSL）、[research/github-similar-projects.md](../../archive-v1.md#docs-research-github-similar-projects-md)。

## 核验记录

> 核验人：对抗式事实核验员（Verify 角色，opus5.5-survey 批次），核验日期统一记为 **2026-09-26**。本节合并两轮结果：**首轮**因会话用量上限中断；**续核验轮**接续完成，先复核首轮全部"修正"项与表格/引用完整性（14 个仓库指标全量复测一致；Papr `ui.R`/`server.R`、Scholar Inbox LICENSE/README、SEC 10-K 原文、S2 平台论文 §3.4.5 与表 4、Litmaps/Wiley/Clarivate 原文、ResearchGate/PubPeer 词条、Paper Skygest 摘要、NotebookLM 博客、Moonlight 的 HN 评论树均复读一致；首轮修正项中只有 Iris.ai 日期属口径选择，已改为"新闻稿 05-29、博客 05-30"并列；另发现首轮一处"确认"（S2 语料规模）已过时并改为修正），再用恢复的 WebSearch 处理首轮"未核验"项与覆盖缺口。方法：默认怀疑，优先一手来源（官方页面/新闻稿、论文原文、仓库源码与 LICENSE、SEC 文件、平台 API 原始数据、官网存档）；首轮 WebSearch 配额耗尽时改用 `curl`、`gh api`、arXiv API、HN Firebase API、MediaWiki API、HF Hub MCP；续核验轮另用 iTunes Lookup API、OpenAlex API、HF OpenAPI 规范与 Wayback Machine。结论口径：**确认**＝一手或权威来源与原文一致；**修正**＝原文有误、过时或口径不当，已就地改正；**核验补充**＝原文缺失的重要条目/事实，已补入；**未核验**＝仍无法取得可靠来源，正文保留 ◐/⚠；**删除/不采信**＝查无实据（两轮均未在正文中发现编造的仓库、产品或论文，删除 0 条；检索中遇到的无据说法记为"不采信"且不写入正文）。
>
> 设计阶段可安全引用的前提：凡正文中仍带 ◐/⚠ 的数字不得直接进入 ADR/需求。**首轮最承重的四处修正**：Papr 四向滑动映射、Papr 推荐器"未公开"说法、Scholar Inbox 数据集许可（CC BY-NC-ND 4.0）、scite 收购对价；**首轮最承重的补充**：S2 Research Feeds 的真实实现（每用户线性 SVM）与 ResearchGate 版权诉讼先例。**续核验轮最承重的修正**：①Researcher App 已于 2024-11 月底关停（原文当作在运营产品）；②G3"机构凭证一键取全文未见"不成立（R Discovery、Read by QxMD、Google Scholar 均已提供），v2 差异收窄为"任意自有凭证 + 多用户私域隔离"；③SSRN/NBER 元数据已被 OpenAlex 与 S2 收录，v1 的差异是新鲜度与组合而非独家覆盖；④滑动卡片已有上架 App（PaperCrush、ZiNote），但采用度极低；⑤Scholar Labs 已对全体登录用户开放，另有按访问权限显示的 Quick Read；⑥S2 语料口径更新为 225M 论文 / 2.8B 引文边（2025-05）；⑦Consensus 2024 年化收入的官方口径为"近 $2M"。

### A. 推荐算法与交互先例（对 v2 算法/前端最承重）

| 断言 | 结论 | 依据来源 URL | 核验日期 |
|---|---|---|---|
| S2 Research Feeds：Library=正例、"not relevant"=负例；对比学习论文嵌入；建议 5 正 + 3 负；每日刷新；候选为近 3 个月；Alerts 四类，每日/每周 | 确认 | https://www.semanticscholar.org/faq/fine-tune-research-feeds ；https://www.semanticscholar.org/faq | 2026-09-26 |
| S2 推荐器内部实现（原文未写） | 核验补充：每用户在 TF-IDF 与 SPECTER 上各训一个线性 SVM，随机负例降权，FAISS 在近 60 天约 100 万篇中召回，取正例质心最近约 500 篇、两分均值排序；与 FAQ"近 3 个月"口径不一 | https://arxiv.org/pdf/2301.10140v2 （§3.4.5） | 2026-09-26 |
| S2 CHI 2022：关系型解释显著提升参与度，且不偏向高被引作者 | 确认 | https://arxiv.org/abs/2204.10254 | 2026-09-26 |
| Scholar Inbox：GTE-Large→PCA 256 维；每用户逻辑回归、每次评分后重训；5k 随机负例 + 加权 BCE；Scholar Maps（300 万篇 t-SNE + LLM 主题标签）；决策边界附近分层主动学习 | 确认 | https://arxiv.org/html/2504.08385v2 | 2026-09-26 |
| Scholar Inbox：注册 23k、30 天活跃 8k（35%）；14.3k 用户 80 万评分；AUC 86.75、nDCG 85.83；1,233 人用户研究；VolkswagenStiftung 资助；ACL 2025 Demo pp.307–317 | 确认（续核验复读 v2 HTML 一致）+ 核验补充：表 2 列依次为 F1/nDCG/Balanced acc./AUC，86.75 与 85.83 分别对应 GTE-L 256 的 AUC 与 nDCG；同表 TF-IDF 10k 的 nDCG 88.67 更高、AUC 84.41 更低 | https://arxiv.org/html/2504.08385v2 ；https://aclanthology.org/2025.acl-demo.30/ | 2026-09-26 |
| Scholar Inbox 数据集"license NOASSERTION，须核验" | **修正**：LICENSE 文件为 CC BY-NC-ND 4.0（非商用、禁止演绎）；仓库实列显式评分 774k + 隐式交互 556k（论文称"80 万"） | https://github.com/avg-dev/scholar_inbox_datasets/blob/main/LICENSE ；https://github.com/avg-dev/scholar_inbox_datasets | 2026-09-26 |
| Papr 四向滑动："左=无聊但可信、下=无聊且存疑" | **修正**：右=兴奋且可信、上=兴奋但存疑、下=无聊但可信、左=无聊且存疑（ZME 原文只列类别、未给映射；以源码 `ui.R` 图例为准；续核验复读 `ui.R` 第 54–70 行一致） | https://github.com/jtleek/papr/blob/master/ui.R ；https://www.zmescience.com/science/papr-swipe-on-papers/ | 2026-09-26 |
| Papr "推荐引擎（细节未公开）" | **修正**：源码公开——摘要词项 PCA 3 维用户向量，75% 按距离候选 / 25% 随机探索，均按日期加权；只用"兴趣"维；相似 Twitter 用户按 PC 空间欧氏距离；实现疑似 bug（取最远 10 篇），不能作为推荐有效性证据（续核验复读 `get_user_pc`/`get_recs`/`rate_paper` 一致；另见 `help.md` 自述"随机挑一篇"，与 75/25 混合实现不完全相符） | https://github.com/jtleek/papr/blob/master/server.R | 2026-09-26 |
| Papr：JHU Jeff Leek；隐藏作者防偏见；bioRxiv 摘要；可导出评分；推荐相似 Twitter 用户 | 确认（补：合作者 Lucy D'Agostino McGowan、Nick Strayer；仓库 19★，2019-05-15 后无推送） | https://www.zmescience.com/science/papr-swipe-on-papers/ ；https://github.com/jtleek/papr | 2026-09-26 |
| ArxivTok：91★、MIT、最后推送 2025-02-07；纵向滑动、双击点赞、收藏、KaTeX、多源 | 确认 | https://github.com/Miguel07Alm/arxivtok | 2026-09-26 |
| ArTok：Show HN 2025-04-21，8 分/5 评论；无算法随机流；因 arXiv/OpenReview API 不稳而自建 Postgres；用户要 30–60 秒音频；学科分布需加权 | 确认 | https://hacker-news.firebaseio.com/v0/item/43755405.json | 2026-09-26 |
| Moonlight HN"自动筛选论文担心漏读、难辨真创新与跟风" | **修正（归因）**：为 Moonlight 开发者自述其自动化 cs.CL 每日 digest 失败的教训，帖子仅 1 分 | https://hacker-news.firebaseio.com/v0/item/42724317.json | 2026-09-26 |
| HF Daily Papers 博客：2024-09-23；3,700+ 篇；1.2 万订阅；认领过论文的用户可提交；librarian-bot；工作日邮件 | 确认 | https://huggingface.co/blog/daily-papers | 2026-09-26 |
| HF 2026-09-25 当日榜 193/62/31、22 篇中 19 篇 ≤ 20 票；Trending 前 10 含 2023-09 vLLM 与 2024-12 TradingAgents | 确认（第 2 名首轮核验时为 63；续核验 19:26 UTC 复读为 195/64/32，实时漂移）+ 核验补充：同一时刻 Trending 榜首为 14 票的 2026-02 论文，147 票的 TradingAgents 居第 2，Trending≠累计票数 | HF Hub MCP `hf://papers/daily/2026/09/25`、`hf://papers/trending`（https://huggingface.co/papers/trending ） | 2026-09-26 |
| HF Papers 有无官方 API（原 §4.1-5"未核验"） | 核验补充：官方 OpenAPI 规范列 `GET /api/daily_papers`（`date`/`week`/`month`/`submitter`、`sort` 取 publishedAt 或 trending、`limit`≤100）、`GET /api/papers`、`GET /api/papers/search`；限速与数据条款仍 **未核验** | https://huggingface.co/.well-known/openapi.json | 2026-09-26 |
| Connected Papers 相似度"共被引 + 文献耦合"、数据源 S2（原 ⚠） | 确认（◐/⚠→✅）：官网 About 文案原句，数据源为 Semantic Scholar Paper Corpus（ODC-BY），免费层每月 5 张图 | https://www.connectedpapers.com/about （curl 取前端包文本） | 2026-09-26 |
| "滑动卡片在学术领域只有原型级先例"（§0-4、G2） | **修正**：已有上架 iOS App——PaperCrush（2025-05-04，Like/Skip + 用户热度榜）、ZiNote（2026-01-23，右滑保存/左滑跳过，自称学习型，免费 20 篇/天）；美区评分数 0 与 2，结论改为"原型或个人开发者级、无规模与效果证据" | https://itunes.apple.com/lookup?id=6745439518&country=us ；https://itunes.apple.com/lookup?id=6756495932&country=us | 2026-09-26 |
| dailypapersHN Hot/Rising 时间衰减公式（原 ◐） | 确认（README 原文；非 HF 官方算法，HF 文档未说明 Trending 排序） | https://github.com/AK391/dailypapersHN ；https://github.com/huggingface/hub-docs/blob/main/docs/hub/paper-pages.md | 2026-09-26 |
| arxiv-sanity-lite：按标签在 tf-idf 上训 SVM；1,696★、MIT、2023-06-19 | 确认 | https://github.com/karpathy/arxiv-sanity-lite | 2026-09-26 |
| Cool Papers：809★、无 license、2026-07-06 推送；类别并/差集、Kimi FAQ、偏好排序、BM25（tantivy）、[REL] | 确认 + 核验补充（2025-06-04 因 bioRxiv 启用 Cloudflare 反爬而下线该源、不对抗；[REL] 基于关键词 + 全文搜索） | https://github.com/bojone/papers.cool | 2026-09-26 |
| Asta Interaction Dataset（arXiv 2602.23335，2026-02-26，20 万+ 查询及四点发现） | 确认 | https://arxiv.org/abs/2602.23335 | 2026-09-26 |
| PaperFlow（arXiv 2606.07454，2026-06-05；24 模拟用户、1,200 用户日、20,727 篇） | 确认（补：50 条日流、497,448 条记录） | https://arxiv.org/abs/2606.07454 | 2026-09-26 |
| Asta Paper Finder 的查询路由架构（原文未写） | 核验补充：查询→结构化对象→规划器按意图路由 workflow→LLM 相关性判断→按"早期/有影响力"等约束排序 | https://github.com/allenai/asta-paper-finder | 2026-09-26 |

### B. 融资、规模、关停与定价（对商业模式与风险判断最承重）

| 断言 | 结论 | 依据来源 URL | 核验日期 |
|---|---|---|---|
| Consensus 2026-05-11 融资 $30M（GreatPoint 领投，DJ Patil 入董事会，USV/NFDG/Draper 跟投），250 万月活，220M+ 论文 | 确认 | https://consensus.app/home/blog/30m-in-new-funding-to-reach-the-next-10m-researchers/ | 2026-09-26 |
| Consensus 2024-08 A 轮 $11.5M、40 万月活、约 1.2 万付费（原 ◐） | 确认（◐→✅）：首轮据 Verdict 确认月活与付费数；续核验以官方新闻稿（2024-08-14）确认 **$11.5M**（Verdict 取整为"$11m"）。**修正**：首轮补入的"年化收入进度约 $1.5M"只是 Verdict 口径，官方新闻稿为"近 $2M 年化收入"，正文两者并列、单位经济学改为区间 | https://www.prweb.com/releases/consensus-raises-11-5-million-in-series-a-funding-to-make-the-worlds-scientific-research-discoverable-and-consumable-302222612.html ；https://finance.yahoo.com/news/ai-start-consensus-secures-11m-083505545.html ；https://www.usv.com/writing/2024/08/consensus/ | 2026-09-26 |
| Elicit A 轮 2025-02-26 $22M、估值 $100M（Spark Capital、Footwork 领投）、每月 40 万+ 研究者 | 确认 | https://elicit.com/blog/series-a/ | 2026-09-26 |
| Elicit 定价（Pro $588/年、Scale $2,028/年）、138M+ 论文、Pro 10 个提醒 | 确认 | https://elicit.com/pricing | 2026-09-26 |
| scite：2023-11-27 宣布被 Research Solutions 收购；约 2.1 万活跃订阅；年化订阅收入 $3.6M（截至 2023-10-31） | 确认（补：2023-12-01 交割） | https://www.prnewswire.com/news-releases/research-solutions-announces-acquisition-of-scite-301997608.html | 2026-09-26 |
| scite 对价"$20.9M，50% 现金 50% 股票" | **修正**：SEC 10-K 列总对价约 $21.1M = 现金 $7.2M + 股票 $6.5M + 保留款 $0.2M + earnout 初始公允价值 $7.2M（2024-06-30 重估 $12.2M）；50/50 只指前期协议部分（续核验复读 Note 9 原文与分配表一致：Total purchase price 21,135 千美元） | https://www.sec.gov/Archives/edgar/data/1386301/000155837024012920/rsss-20240630x10k.htm | 2026-09-26 |
| scite 定价（Connect 免费 25 MCP 额度、Basic $14、Pro $35）与 1.6B+ 引文、300M+ 来源 | 确认 | https://scite.ai/pricing | 2026-09-26 |
| Litmaps 2025-05-08 收购 ResearchRabbit；合计 200 万+ 用户；自身 ARR 翻倍至约 $1M | 确认 | https://itbrief.co.nz/story/litmaps-acquires-researchrabbit-raises-1-million-for-ai | 2026-09-26 |
| Litmaps"同时融资 $1M" | **修正**：完成一轮 $1M 融资的首次交割，首交割约 $40.6 万（Scholarly Angels 领投；续核验复读原文一致） | 同上 | 2026-09-26 |
| ResearchRabbit 2025-10 转 freemium；RR+ $12.50/月或 $120/年；免费 50 种子/1 项目；310M+；RR+ 的关键词/日期/分区与 h-index/OA/撤稿过滤 | 确认（补：官方承诺"免费层会一直在"） | https://www.researchrabbit.ai/announcement-researchrabbit-release-2025 ；https://www.researchrabbit.ai/pricing ；https://learn.researchrabbit.ai/en/articles/12454495-what-is-researchrabbit | 2026-09-26 |
| alphaXiv 2025-11-19 $7M 种子（Menlo、Haystack 领投；Eric Schmidt、Sebastian Thrun 等天使）；"数百万用户"；获 arXiv Labs 支持 | 确认（arXiv Labs 出自 about 页，新闻稿未提） | https://www.prnewswire.com/news-releases/alphaxiv-raises-7m-seed-round-to-bridge-the-ai-research-to-practice-divide-302619615.html ；https://www.alphaxiv.org/about | 2026-09-26 |
| Papers with Code 2025-07 无预告下线并重定向 HF Trending | 确认 + 核验补充（HF CEO 称系 HF 向 Meta 提议重定向；2025-12 起逐页重定向；2026-09-26 实测 302） | https://github.com/paperswithcode/paperswithcode-data/issues/116 ；https://paperswithcode.com/ | 2026-09-26 |
| Microsoft Academic 2016-02-22 上线、2021-05-04 宣布、2021-12-31 退役，数据并入 OpenAlex | 确认 | https://en.wikipedia.org/wiki/Microsoft_Academic | 2026-09-26 |
| Meta（CZI）2017 并入 CZI；2021-10-28 宣布；2022-03-31 关停；按领域/基因/疾病/药物/期刊订阅 feed | 确认 | https://en.wikipedia.org/wiki/Meta_(academic_company) | 2026-09-26 |
| Mendeley：2013 被 Elsevier 收购（传闻 €50M/$65M）；2021-03-15 移动 App 下架；2022-09 停止 Desktop 下载；2025-07-09 Desktop 仅维护 | 确认 | https://blog.mendeley.com/2025/07/09/mendeley-is-not-going-anywhere/ ；https://en.wikipedia.org/wiki/Mendeley | 2026-09-26 |
| Zotero 8 于 2026-01-22 发布；此后约 6–10 周发版；存储 300MB 免费/2GB $20/6GB $60/无限 $120 每年；15.4k★ | 确认 | https://www.zotero.org/blog/zotero-8/ ；https://www.zotero.org/blog/a-faster-release-cycle-for-zotero ；https://www.zotero.org/storage | 2026-09-26 |
| Inciteful：inciteful.xyz 301 → incitefulmed.com/academic/ | 确认 + 核验补充（工具仍在运行，页面预连接 OpenAlex API；续核验：根域 incitefulmed.com 是面向患者的医学问答产品 Inciteful Med，属转向，同一团队系推断） | https://inciteful.xyz/ （curl 实测） | 2026-09-26 |
| Emergent Mind 定价（Basic 5 篇/天；Pro $12 月付/$10 年付；Max $30/$25）；作者称 X API $100/月仅 1 万次读取 | 确认 | https://www.emergentmind.com/pricing ；https://hacker-news.firebaseio.com/v0/item/39042157.json | 2026-09-26 |
| Paper Digest：纽约、2018；按"潜在影响力 + 社交/在线指标"排序；200+ 领域；$10.99/月、$79.90/年；"数万研究者"（原 ◐） | 确认（◐→✅） | https://www.paperdigest.org/frequently-asked-questions/ ；https://www.paperdigest.org/daily-paper-digest/ | 2026-09-26 |
| R Discovery：250M+ 文章等语料口径；Prime $5/月、$12/季、$39/年；Editage Plus $174/年；2.5M+ 下载、3M+ 学者 | 确认 | https://www.editage.com/r-discovery | 2026-09-26 |
| Researcher（2020-07）：160 万用户、16,000 期刊、日均约 5,000 篇、完全免费 | 2020 年数字确认 | https://researchoutreach.org/articles/researcher-app-keep-scientists-top-science/ | 2026-09-26 |
| Researcher 作为"在运营产品"列入个性化流、交互对比、I-18（原文 2026 现状 ⚠） | **修正**：官网 2024-11-19 存档为关停公告，App 可用至 2024-11 月底，团队转向新项目，只提示用户备份数据与书签；现网 TLS 失败与之一致。正文改为"已关停"，并补入关停时间线、商业模式反例与 I-16 | http://web.archive.org/web/20241119151936/https://www.researcher-app.com/ | 2026-09-26 |
| Undermind：YC S24、2023 年旧金山成立、Ramette 与 Hartke 均为 MIT 博士；Pro $16/月（年付）、Team $15/人/月 | 确认 | https://www.ycombinator.com/companies/undermind ；https://www.undermind.ai/pricing | 2026-09-26 |
| Iris.ai A 轮 2024-05-29 €7.64M（Silverline、EIC Fund），累计 €16M | 确认金额与投资方（Silverline Capital 领投，EIC Accelerator Fund 匹配投资）。首轮把日期**修正**为 2024-05-30（博客发布日）；续核验复读正文，新闻稿电头为"May 29th"，因此原文 05-29 也成立——**再修正**为"新闻稿 2024-05-29、博客 2024-05-30"并列 | https://iris.ai/blog/european-scientific-ai-startup-iris-ai-raises-7-64million-with-its-series-a-funding-round | 2026-09-26 |
| Keenious 基于 OpenAlex（原 ◐） | 确认（◐→✅；250M+ 作品、月更、Unpaywall 标 OA） | https://keenious.com/ | 2026-09-26 |
| ReadCube 定价（Essentials $10/月或 $95/年；Plus $20/月或 $185/年） | 确认 | https://about.readcube.com/pricing | 2026-09-26 |
| Moonlight Chrome 扩展 10 万用户、4.7★（71 评分）、2026-09-23 更新 | 确认 | https://chromewebstore.google.com/detail/moonlight-ai-colleague-fo/lhipdkibljepmfojllcfflfflhflcbgi | 2026-09-26 |
| Scollr：OpenAlex + S2 数据；从打开/保存/点赞/回访中学习；iOS | 确认 + 核验补充（原"上线时间 ⚠"）：iOS 版 2026-04-21 上架，开发者 Chris Colpitts，美区 0 条评分；App 描述另含评论讨论与公开/私有 Collections | https://scollr.com/ ；https://itunes.apple.com/lookup?id=6761957461&country=us | 2026-09-26 |
| Sciety：eLife 创建；sciety/sciety MIT、17★、2026-09-14 推送 | 确认；eLife 组评估数续核验升级为 ✅：**53,287 条评估、8,301 篇策展文章、318 名关注者**（原文 51,752 为 2026-07-22 口径） | https://sciety.org/about ；https://github.com/sciety/sciety ；https://sciety.org/groups | 2026-09-26 |
| R Discovery"使用何种信号未公开"、"用户自带权限取全文 ?" | **修正/升级**：官方页称从"过往检索与 App 内点赞的论文类型"中学习；App Store 描述（2026-08-26 版）写明"经 GetFTR 与 LibKey 集成的机构登录取全文"；美区 4.8★/919 条评分；两处语料口径不一（官网 250M+，App Store 1.5 亿+ 期刊文章） | https://www.editage.com/r-discovery ；https://itunes.apple.com/lookup?id=1508182175&country=us | 2026-09-26 |
| Litmaps 免费层"1 图 100 篇" | **修正（口径）**：定价页 HTML 两处写法不一（"2 Litmaps, 100 articles per Map"与"100 articles, 1 Litmap"），正文标 ◐；Pro 教育版需学术邮箱、年付 $120"省 20%" | https://www.litmaps.com/pricing | 2026-09-26 |
| FutureHouse 与 Edison Scientific 的关系、融资（首轮列为未核验） | 确认：Edison 是 FutureHouse 的商业化分拆（2025-11-05 两家官网同文公告）；2025-12-18 种子轮 $70M（Triatomic Capital、Spark Capital 与一家美国机构型生物技术投资方领投）；估值约 $2.5 亿仍 **未核验**（仅 TechFundingNews） | https://www.futurehouse.org/research-announcements/announcing-edison-scientific ；https://edisonscientific.com/news/we-raised-70m-to-accelerate-science ；https://techfundingnews.com/edison-raises-70m-ai-scientist-platform/ | 2026-09-26 |

### C. AI 检索、出版商 AI 与合规边界

| 断言 | 结论 | 依据来源 URL | 核验日期 |
|---|---|---|---|
| S2 语料 200M+ 论文、80M+ 作者、2.4B+ 引文边；Wikipedia 称 2026 年 214M；2020 年末约 700 万月活 | **修正（过时）**：首轮记为"确认"，但 200M+/80M+/2.4B+ 是 2023 年 v1 口径；同一论文 v2（2025-04-25）表 1 为 **225M 论文、105M 作者、650M 署名边、2.8B 引文边（2025-05）**，正文已更新。Wikipedia 的 214M（2026）与约 700 万月活（2020 年末）确认 | https://arxiv.org/pdf/2301.10140v2 （表 1）；https://en.wikipedia.org/wiki/Semantic_Scholar | 2026-09-26 |
| G3"'用户自带凭证、私域取全文、在 feed 中一键打开'未见"及矩阵"用户自带权限取全文"列 | **修正**：机构登录后一键取全文已有成熟先例——R Discovery（GetFTR + LibKey）、Read by QxMD（2012 年起按本人机构订阅）、Google Scholar（图书馆链接 + 校外访问链接）；G3 收窄为"任意类型自有凭证 + 多用户私域隔离"，矩阵相应改为 ✔ | https://itunes.apple.com/lookup?id=1508182175&country=us ；https://itunes.apple.com/lookup?id=574041839&country=us ；https://scholar.google.com/intl/en/scholar/help.html | 2026-09-26 |
| S2 是否覆盖 SSRN/NBER/RePEc（原矩阵"?"）；G1"v1 覆盖 SSRN/NBER → 天然差异化" | 核验补充：S2 数据合作方页 logo 列表含 SSRN，未见 NBER、RePEc；另 OpenAlex 收录"SSRN Electronic Journal"1,691,849 条、NBER 34,992 条。**修正**：G1 对策与矩阵读法改为"差异来自直连枚举的新鲜度与组合，不是独家覆盖" | https://www.semanticscholar.org/about/publishers ；https://api.openalex.org/sources?search=ssrn ；https://api.openalex.org/sources?search=National%20Bureau%20of%20Economic%20Research | 2026-09-26 |
| S2 被 Elicit、SciSpace、Consensus、Undermind、Asta 等用作底座 | 确认（Wikipedia 二手；Consensus 另有 Verdict 独立佐证） | https://en.wikipedia.org/wiki/Semantic_Scholar ；https://finance.yahoo.com/news/ai-start-consensus-secures-11m-083505545.html | 2026-09-26 |
| Google Scholar Labs 2025-11-18 发布，仅向有限数量的登录用户开放 | 发布时属实；**修正（过时）**：2026-06-03 官方博客称已对所有登录用户开放、支持任意语言提问（新版先上英文）；另补 2026-08-25 Quick Read（只对用户有权访问的论文显示按查询生成的速读） | https://blog.google/products-and-platforms/products/education/google-scholar-labs/ ；https://scholar.googleblog.com/2026/06/scholar-labs-update-search-10x-faster.html ；https://scholar.googleblog.com/2026/08/quick-read-see-how-paper-answers-your.html | 2026-09-26 |
| ChatGPT Deep Research：2025-02 上线；5–30 分钟；免费 5/Plus 25/Pro 250 次每月；2026-02 升级 GPT-5.2、可限定站点、接 MCP；OpenAI 承认会有事实性幻觉 | 确认；**修正**：额度为 Wikipedia 所载 2025-06 口径，2026 现行额度 **未核验**（续核验检索只得第三方博客，且称 OpenAI 已不再公布按计划的次数表） | https://en.wikipedia.org/wiki/ChatGPT_Deep_Research | 2026-09-26 |
| Ai2 Asta 2025-08-26 发布；S2 200M+ 论文、年查询 15 亿+；Scientific Corpus Tool 为 S2 API 的 MCP 扩展；两仓库 245★/282★（Apache-2.0） | 确认 | https://allenai.org/blog/asta ；https://github.com/allenai/asta-paper-finder | 2026-09-26 |
| Asta Find Papers 覆盖 108M 摘要 + 12M 全文 | 确认（续核验由"部分确认"升级）：Ai2《Asta Getting Started Guide》（2026-02）原句为约 12.4M 全文、108M+ 摘要；全文部分与 S2 snippet 索引一致（平台论文 12M+ 篇/2.75 亿段落，指南 12.4M+ 篇/2.85 亿段落） | https://allenai.org/papers/asta-guide ；https://arxiv.org/pdf/2301.10140v2 （§4.1） | 2026-09-26 |
| Scopus AI 2024-01-16 全球发售（客户加购；27,000+ 期刊、7,000+ 出版商、1.8B 引文）；Deep Research 2025-08-28，报告"仅基于 Scopus 同行评审内容" | 确认 | https://www.elsevier.com/about/press-releases/launch-of-scopus-ai-to-help-researchers-navigate-the-world-of-research ；https://blog.scopus.com/accelerate-your-workflow-with-deep-research-a-new-scopus-ai-feature/ | 2026-09-26 |
| ScienceDirect AI 2025-03-12；1,400 万篇文章与书章；不存储、不用于训练公共模型，数据只在 Elsevier 私有环境 | 确认 | https://www.elsevier.com/about/press-releases/elsevier-launches-sciencedirect-ai-to-transform-research-with-rapid-mission | 2026-09-26 |
| WoS Research Assistant：2023-12 beta、2024-09-04 正式、120 年数据；2025-04-10 文献综述 Agent | 确认 | https://ir.clarivate.com/news-events/press-releases/news-details/2024/Clarivate-Launches-Generative-AI-Powered-Web-of-Science-Research-Assistant/default.aspx | 2026-09-26 |
| "WoS RA 已被 3,000+ 机构采用" | **修正（归属）**：Clarivate 称其 2024 年推出的研究/分析/元数据类 AI 助手合计被 3,000+ 机构采用，未单列 WoS RA | https://ir.clarivate.com/news-events/press-releases/news-details/2025/Clarivate-Expands-its-Academic-AI-Platform-Introducing-Agentic-AI-for-Research-and-Learning/default.aspx | 2026-09-26 |
| Dimensions Research GPT 2024-02-28；公开版只检索 OA；Enterprise 版约 3.5 亿条记录，需 Dimensions 许可 | 确认；"AI Assistant 2023-08 beta"中的月份 **未核验**（新闻稿只写 2023） | https://www.globenewswire.com/news-release/2024/02/28/2836711/0/en/Dimensions-Research-GPT-evidence-based-research-insights-for-ChatGPT-platform-users.html | 2026-09-26 |
| Perplexity × Wiley（2025-05-08，原 ◐） | 确认（◐→✅）并**修正**范围：Wiley 是 Perplexity 首个教育合作方，覆盖订阅机构已购的教育类馆藏 | https://newsroom.wiley.com/press-releases/press-release-details/2025/Wiley-and-Perplexity-Announce-New-AI-Search-Partnership/default.aspx | 2026-09-26 |
| Perplexity API 用 `search_domain_filter` 限定学术域名 | 确认 | https://docs.perplexity.ai/docs/cookbook/articles/academic-search/README | 2026-09-26 |
| "X API $100/月仅 1 万次读取"（I-7 的依据，2024 口径） | 确认为 2024 年作者自述；核验补充（现行口径）：X API 官方文档为按量计费，读取每条 $0.005、每个计费月上限 300 万条读取，超出需 Enterprise | https://hacker-news.firebaseio.com/v0/item/39042157.json ；https://docs.x.com/x-api/getting-started/pricing | 2026-09-26 |
| Perplexity × Wiley、WoS RA"3,000+ 机构"归属、Litmaps 首交割（首轮修正项） | 续核验复读三份原文，首轮修正均无误 | https://newsroom.wiley.com/press-releases/press-release-details/2025/Wiley-and-Perplexity-Announce-New-AI-Search-Partnership/default.aspx ；https://ir.clarivate.com/news-events/press-releases/news-details/2025/Clarivate-Expands-its-Academic-AI-Platform-Introducing-Agentic-AI-for-Research-and-Learning/default.aspx ；https://itbrief.co.nz/story/litmaps-acquires-researchrabbit-raises-1-million-for-ai | 2026-09-26 |
| Kimi-Researcher 2025-06-20；端到端 RL；平均 23 步、200+ URL；渐进开放 + 候补 | 确认 | https://moonshotai.github.io/Kimi-Researcher/ | 2026-09-26 |

### D. 中文生态

| 断言 | 结论 | 依据来源 URL | 核验日期 |
|---|---|---|---|
| 深势科技 2025-12-24 C 轮超 8 亿元（达晨财智、京国瑞、北京市 AI 产业基金、联想创投、元禾璞华等）；玻尔 1.7 亿英文 + 8,000 万中文文献 + 2 亿专利；服务 1,000+ 机构的 300 多万科学家 | 确认（补：另有北京市医药健康产业投资基金） | https://www.qbitai.com/2025/12/365728.html | 2026-09-26 |
| Bohrium + SciMaster 论文（arXiv 2512.20469） | 确认（2025-12-23 提交） | https://arxiv.org/abs/2512.20469 | 2026-09-26 |
| Z.ai 2026-01-08 港交所上市（2513）；AMiner 由唐杰于 2006 年创建 | 确认 | https://en.wikipedia.org/wiki/Zhipu_AI | 2026-09-26 |
| AMiner 3.3 亿论文、6,000 万学者、1.8 亿专利 | 确认（续核验由"未核验"升级）：官方文档"平台概述"列 3.3 亿论文、6,000 万学者、28 亿引用关系、1.8 亿专利、879 万知识实体（统计截至 2026-06），2025-09 接入 GLM 升级；订阅推送渠道（邮件/微信）仍 ◐ | https://docs.aminer.cn/user-guide/platform-overview/ | 2026-09-26 |
| 百度学术 AI 重构：6.9 亿文献、2.1 亿全文、1.6 亿免费、104 万+ 站点、日更 42 万+、420 万学者主页 | 确认；日期 2025-09-11（第 12 届 AI Day，新浪 URL 日期），量子位 2025-09-14 报道 | https://www.qbitai.com/2025/09/331407.html | 2026-09-26 |
| 小红书 3 亿+ 月活（FT，2024-07）、2024Q4 日均近 6 亿次搜索 | 确认 | https://en.wikipedia.org/wiki/Xiaohongshu | 2026-09-26 |
| 抖音 2024 年万粉以上知识创作者 32 万、全年知识内容 5.7 亿条 | 确认 | https://news.qq.com/rain/a/20250429A06LJP00 | 2026-09-26 |
| 小红书 REDtech 2024-06-27 大模型论文分享会，视频号/B 站/抖音/小红书同步直播 | 确认 | https://blog.csdn.net/REDtech_1024/article/details/139864284 | 2026-09-26 |

### E. 仍未核验（维持 ◐/⚠，设计阶段勿直接引用）

| 断言 | 结论 | 依据来源 URL | 核验日期 |
|---|---|---|---|
| Connected Papers 价格数字（Academic $3 年付/$5 季付、Business $10 年付/$15 季付） | 未核验：价格不在官网前端包文案内（疑由接口下发），只见检索摘要；算法、数据源与免费 5 图/月已在 A 节确认 | https://www.connectedpapers.com/pricing （尝试） | 2026-09-26 |
| SciSpace 用户数/融资/定价；Scholarcy 用户数与机构价 | 未核验（官方页 403；续核验检索只得 Tracxn/Crunchbase 类汇编，口径互相矛盾） | https://scispace.com/pricing 、https://www.scholarcy.com/pricing （尝试） | 2026-09-26 |
| PapersTok 的存在与形态；Katina Magazine 对 Keenious 的书评；Science 对 Papr 的报道 | 未核验正文（Cloudflare 挑战页，不绕过）；续核验检索结果中三者标题均可见，存在性可信 | https://medium.com/@xinfitok/paperstok-arxiv-papers-with-a-tiktok-like-ux-72e2dc5b156d 、https://katinamagazine.org/content/article/resource-reviews/2026/ai-tool-recreates-friction-of-academic-search 、https://www.science.org/content/article/great-paper-swipe-right-new-tinder-preprints-app （尝试） | 2026-09-26 |
| Edison Scientific 估值约 $2.5 亿 | 未核验（只见 TechFundingNews 等二手报道；官方融资公告未写估值） | https://techfundingnews.com/edison-raises-70m-ai-scientist-platform/ | 2026-09-26 |
| "Papel：TikTok 式论文社交发现平台"（检索中出现） | 未核验，**不写入正文**（只见一篇聚合站博文，未找到官网或应用商店条目） | https://ideaverse.ai/blog/papel-tiktok-style-social-discovery-for-scientific-papers-with-on-device-ai-mp1ieu2k （检索结果） | 2026-09-26 |
| "alphaXiv 2026 年融资 $70M"（检索中出现） | **不采信**，不写入正文：只见一篇个人 Medium 帖；官方新闻稿与多家报道均为 2025-11 的 $7M 种子轮，疑为笔误 | https://medium.com/@writertripathi/alphxiv-just-raised-70m-and-it-validates-why-i-built-paper-route-c2c8c7f2daa7 （检索结果）；https://www.prnewswire.com/news-releases/alphaxiv-raises-7m-seed-round-to-bridge-the-ai-research-to-practice-divide-302619615.html | 2026-09-26 |

### F. 核验补充（原文遗漏的主题内重要条目）

| 断言 | 结论 | 依据来源 URL | 核验日期 |
|---|---|---|---|
| ResearchGate：2,500 万成员；2017 起遭出版商联盟下架通知与诉讼，2023-09-15 与 Elsevier/ACS 和解 | 核验补充（多用户学术平台托管全文的版权反面先例，支撑 I-12 与"auth-gated 全文不跨用户共享"红线） | https://en.wikipedia.org/wiki/ResearchGate | 2026-09-26 |
| PubPeer：匿名发表后评议；作者回应率 7.5%、85.6% 匿名、仅 31.5% 被评论论文有 >3 条评论 | 核验补充（评论/评价功能的治理与法律风险基准，I-13） | https://en.wikipedia.org/wiki/PubPeer | 2026-09-26 |
| Paper Skygest：Bluesky 学术个性化 feed，周使用 5 万+、日活 1,000+，代码公开（arXiv 2601.04253） | 核验补充（开放社交信号与"社交网络内论文推荐"的可复用先例，I-7、§4.1-5） | https://arxiv.org/abs/2601.04253 | 2026-09-26 |
| FutureHouse Platform（2025-05-01，Crow/Falcon/Owl/Phoenix）；Edison Scientific 推出 Kosmos | 核验补充（L5 科研 Agent 新进入者；Owl 式查新可作卡片深挖集成点；续核验补齐 Edison 为其商业分拆及 $70M 种子轮，见 B 节） | https://www.futurehouse.org/research-announcements/launching-futurehouse-platform-ai-agents ；https://edisonscientific.com/ | 2026-09-26 |
| NotebookLM Audio Overviews（2024-09-11）：双主持人播客式讨论；官方承认会引入不准确内容、发布时仅英语 | 核验补充（论文音频速读形态的大厂先例与风险，I-11） | https://blog.google/technology/ai/notebooklm-audio-overviews/ | 2026-09-26 |
| OpenAI Prism（2026-01-27）：LaTeX 原生科研写作工作区 | 核验补充（回应 §4.1-8：大厂科研产品目前偏写作，而非个性化论文流；续核验以 TechCrunch 当日报道补证：GPT-5.2 驱动、任何 ChatGPT 账户免费可用） | https://en.wikipedia.org/wiki/Products_and_applications_of_OpenAI ；https://techcrunch.com/2026/01/27/openai-launches-prism-a-new-ai-workspace-for-scientists/ | 2026-09-26 |
| S2ORC 分学科全文可得量：经济 21 万、商业 23 万篇，医学 290 万、生物 220 万篇 | 核验补充（量化 G1"经管学科空白"：开放全文底座本身偏科；续核验复读表 4 一致） | https://arxiv.org/pdf/2301.10140v2 （Table 4） | 2026-09-26 |
| Read by QxMD：移动个性化医学文献 feed，一键经本人机构订阅或 OA 取全文 PDF；2012-11 上架、美区 4.8★/6,040 评分；2019-08-12 被 WebMD 收购，Read 服务"数百万会员" | 续核验补充（推翻 G3"机构凭证在 feed 中一键取全文未见"的判断；移动 feed 的成熟先例） | https://itunes.apple.com/lookup?id=574041839&country=us ；https://www.qxmd.com/webmd-acquires-qxmd | 2026-09-26 |
| Google Scholar 图书馆链接与校外访问链接（记录用户在校内的订阅，并向参与的出版商标示其访问权）；Quick Read 只对有权访问的论文显示 | 续核验补充（"派生内容按个人权限显示"的大厂先例，支撑 I-12；同时说明 G3 不是空白） | https://scholar.google.com/intl/en/scholar/help.html ；https://scholar.googleblog.com/2026/08/quick-read-see-how-paper-answers-your.html | 2026-09-26 |
| ResearchHub：2019 年 Brian Armstrong、Patrick Joyce 创立；upvote + 行内评论 + 声誉算法；以 RSC 代币支付评审（$150/篇、约 10 天周转）与被引奖励；2023-06 种子轮 $5M（◐） | 续核验补充（"点赞/评价/评审激励"的社区先例，I-13） | https://blog.researchhub.foundation/the-researchhub-story/ ；https://www.researchhub.com/peer-review ；https://www.theblock.co/post/234960/scientists-can-earn-crypto-as-brian-armstrong-startup-raises-5-million | 2026-09-26 |
| PaperCrush（2025-05-04，arXiv 分类流 Like/Skip + 用户热度榜）、ZiNote（2026-01-23，右滑保存/左滑跳过、自称学习型、多源含 OpenAlex/S2）两款已上架的学术滑动 App | 续核验补充（§2.2.H 新增两行；滑动 + 学习的最近先例，美区评分数 0/2，采用度极低；A 节据此修正"只有原型"的结论） | https://itunes.apple.com/lookup?id=6745439518&country=us ；https://itunes.apple.com/lookup?id=6756495932&country=us | 2026-09-26 |
| PaperTok（UW，CHI 2026）：论文→45 秒短视频，作者审定后署名；100 名在线 + 18 名学者评估；"AI 味"与错误信息顾虑 | 续核验补充（论文短视频形态的学术先例与风险，I-11） | https://www.washington.edu/news/2026/06/25/papertok-an-ai-system-that-helps-users-turn-research-papers-into-short-engaging-videos/ | 2026-09-26 |