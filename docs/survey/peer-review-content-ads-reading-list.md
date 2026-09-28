---
title: 同行评审、内容与广告推荐论文精选：算法、EconCS 与博弈论
status: draft
owner: codex
updated: 2026-09-28
---

# 同行评审、内容与广告推荐论文精选：算法、EconCS 与博弈论

本清单收录 **75 篇研究：原有 40 篇算法与系统论文（35 篇正式发表＋5 篇筛选预印本），以及新增 35 篇 EconCS、博弈论和经济学研究**，覆盖传统经典方法、深度学习、LLM、平台激励与福利。新增条目的期刊发表、会议全文、会议摘要和会议录用状态逐项标注。

- **Peer review**：论文—审稿人匹配与同行评审机制，并补充 LLM 辅助评审的实证研究。
- **自媒体内容推荐**：新闻、图文笔记、视频与短视频信息流，以及相关通用推荐基础方法。
- **广告推荐**：CTR/CVR 预测、预算竞价、大模型知识迁移与低延迟服务。
- **经济机制与博弈论**：信息设计、激励相容、创作者供给、审稿努力、策略性反馈、市场均衡及福利。

**检索核验截至 2026-09-28。** 优先使用期刊、会议论文集和作者的一手页面，未下载论文。总结基于出版信息、摘要及可访问正文，不表示逐篇全文精读或实验复现。工业效果为作者报告，不等于独立复现；局限说明包含对证据适用范围的判断。本文是选读清单，不是穷尽式系统综述，也不改变项目设计状态。

**★ 表示建议优先阅读。** 部分正式论文提供 arXiv 作者版链接，其发表状态仍按正式版本标注。生成式推荐、推荐基础模型与通用预训练 LLM 并非同义。

## 目录

1. [同行评审：匹配、分配机制与 LLM](#peer-review)
2. [自媒体与内容推荐](#content-recommendation)
3. [广告推荐](#ads-recommendation)
4. [跨方向基础与评测](#foundations)
5. [最新 arXiv 补充](#arxiv)
6. [经济学增补范围与口径](#econ-scope)
7. [同行评审的经济机制](#econ-peer)
8. [信息设计与激励相容](#econ-information)
9. [内容平台与多边市场](#econ-platform)
10. [广告市场与定价](#econ-ads)
11. [深度学习与 LLM 机制设计](#econ-llm)
12. [建议阅读顺序](#reading-order)

<a id="peer-review"></a>

## 一、同行评审：论文—审稿人匹配、分配机制与 LLM 辅助评审

这一方向需要区分三个问题：谁懂这篇论文、怎样在约束下分配审稿人、怎样改善实际评审质量。三者不能仅用一个文本相似度指标替代。

### 1. A Framework for Optimizing Paper Matching

Charlin, Zemel & Boutilier，**UAI 2011**，正式会议论文。以少量审稿人评分学习论文—审稿人适配度，再用整数规划处理审稿负载与分配约束，讨论预测误差与最终匹配效用的关系。经典价值是把“学出分数”和“全局受约束分配”拆清楚；实验来自两场会议，不能把文本相似度等同于真实评审质量。[作者机构论文页](https://research.google/pubs/a-framework-for-optimizing-paper-matching-2/)；[作者预印本摘要](https://arxiv.org/abs/1202.3706)。

### 2. ★ PeerReview4All: Fair and Accurate Reviewer Assignment in Peer Review

Stelmakh, Shah & Singh，**JMLR 22(163), 2021**，正式期刊论文。用增量最大流改善匹配最差论文的审稿质量，并给出公平性与接受论文恢复的统计保证；适合研究长尾论文不会被总效用目标牺牲的问题。保证依赖论文里的打分模型与适配度输入，不能自动消除亲和度估计偏差。[JMLR 原文页](https://jmlr.org/papers/v22/20-190.html)。

### 3. Mitigating Manipulation in Peer Review via Randomized Reviewer Assignments

Jecmen et al.，**NeurIPS 2020**，正式主会论文。对论文—审稿人被配对的概率施加上界，再优化期望相似度，以缓解串通、恶意压分及分配反推身份。历史会议数据表明概率约束可以在保留较高匹配效用的同时降低攻击成功率；随机化减少风险，并非彻底防串通的策略无关保证。[NeurIPS 原文页](https://proceedings.neurips.cc/paper/2020/hash/93fb39474c51b8a82a68413e2a5ae17a-Abstract.html)。

### 4. SPECTER: Document-level Representation Learning using Citation-informed Transformers

Cohan et al.，**ACL 2020**，正式主会论文。利用引用关系监督 Transformer 学习整篇论文表示，在推断时仅需论文标题与摘要，适合为新投稿构建语义匹配分数。它是审稿人画像匹配的基础表示模型，并非完整审稿人分配算法；仍需另行处理利益冲突、负载和团队覆盖。[ACL 原文页](https://aclanthology.org/2020.acl-main.207/)。

### 5. Counterfactual Evaluation of Peer-Review Assignment Policies

Saveski et al.，**NeurIPS 2023**，正式主会论文。利用随机分配日志评估替代匹配政策，并在缺少支持集重叠时以单调性、Lipschitz 条件进行部分识别。TPDP 2021 与 AAAI 2022 数据把“增加文本相似度权重是否有用”“随机化质量代价多大”变成可评估问题；结论取决于评审质量度量及识别假设。[NeurIPS 原文页](https://proceedings.neurips.cc/paper_files/paper/2023/hash/b7d795e655c1463d7299688d489e8ef4-Abstract.html)。

### 6. Are Key-Phrases All That Reviewers Care About? A Comprehensive Benchmarking of Reviewer Matchmaking Systems

Dasgupta et al.，**AAAI 2025**，正式主会论文。比较 6 种文档表示匹配模型与 14 种关键词抽取匹配模型，并质疑若干惯用评测指标的可靠性。关键词方法在部分指标上可比甚至略优于 SPECTER2，说明专业知识匹配不能只看模型规模；领先幅度小，且离线专家熟悉度不等于实际审稿质量。[AAAI 原文页](https://ojs.aaai.org/index.php/AAAI/article/view/34545)。

### 7. ★ RATE: Reviewer Profiling and Annotation-free Training for Expertise Ranking in Peer Review Systems

Liu et al.，**ACL 2026**，正式主会长文。以近期论文生成紧凑关键词画像，通过启发式检索构造弱偏好监督微调 embedding，使投稿直接对齐审稿人专业画像；新增 LR-bench 含 2024–2025 年稿件与 1,055 条专家熟悉度标注。它把 LLM 画像能力接入匹配链条，是直接相关的新进展；评估仍集中于 AI/NLP、自报熟悉度与离线排序，尚不能推出真实大会接受决策更可靠。[ACL 原文页](https://aclanthology.org/2026.acl-long.2035/)。

### 8. Can Large Language Models Provide Useful Feedback on Research Papers? A Large-Scale Empirical Analysis

Liang et al.，**NEJM AI 1(8), 2024**，正式期刊论文（注意是 NEJM AI，不是 NEJM 正刊）。对比 GPT-4 与 Nature 系列、ICLR 等人工意见，并进行 308 名研究者前瞻用户研究，发现不少用户认可模型反馈的帮助。关键意义是量化“辅助作者改稿”的价值；意见重合及用户感知有用并不证明审稿事实正确，更不能证明可替代录用决策。[期刊 DOI](https://doi.org/10.1056/AIoa2400196)；[核验所用 NSF 机构版](https://par.nsf.gov/servlets/purl/10617069)。

### 9. ★ A large-scale randomized study of large language model feedback in peer review

Thakkar et al.，**Nature Machine Intelligence 8, 326–336, 2026**，正式期刊论文，2026-02-23 发表。Review Feedback Agent 给人类审稿意见提供具体性、可操作性和专业表达建议，在 ICLR 2025 大规模随机试验中促成更多修改，盲评显示修订意见更有信息量。这是“LLM 帮助审稿人改进评语”的较强现场证据；评语长度与清晰度提升仍不等于论文质量或录用准确度提升。[期刊原文](https://doi.org/10.1038/s42256-026-01188-x)。

<a id="content-recommendation"></a>

## 二、自媒体与内容推荐：经典探索、深度序列模型、多模态与 LLM

本节结合通用序列推荐方法与新闻、视频、图文平台研究。生成物品 ID 的推荐模型，与理解自然语言的通用 LLM，不是同一个概念。

### 10. ★ A Contextual-Bandit Approach to Personalized News Article Recommendation

Lihong Li et al., **WWW 2010，正式发表**。把新闻推荐写成上下文 bandit，在利用既有偏好与探索新文章之间权衡，提出 LinUCB 并用随机流量日志进行离线评估。价值在于理解实时兴趣、新内容冷启动与探索；其点击收益和回放评估不等于长期满意度，可靠评估依赖随机日志条件。[论文与作者机构页](https://www.microsoft.com/en-us/research/publication/a-contextual-bandit-approach-to-personalized-news-article-recommendation-3/?lang=fr-ca)

### 11. ★ Deep Neural Networks for YouTube Recommendations

Paul Covington, Jay Adams, Emre Sargin，**RecSys 2016，正式发表**。经典的深度候选召回与独立排序两阶段架构，展示如何将超大视频库与丰富用户行为压缩为可在线服务的模型。适合作为内容推荐工程底座；论文描述的是当年的系统，不能当成今日 YouTube 实际架构说明。[Google Research](https://research.google/pubs/deep-neural-networks-for-youtube-recommendations/)

### 12. Self-Attentive Sequential Recommendation（SASRec）

Wang-Cheng Kang, Julian McAuley，**ICDM 2018，正式发表**。以自注意力从行为序列中选择相关历史，兼顾短期转移与长期兴趣，是后续序列推荐和生成式推荐的重要强基线。它是通用序列方法，并非专为新闻或短视频验证；使用 Transformer 不意味着使用预训练 LLM。[论文](https://arxiv.org/abs/1808.09781)；[作者出版记录核验 ICDM](https://cseweb.ucsd.edu/~jmcauley/)

### 13. Neural News Recommendation with Multi-Head Self-Attention（NRMS）

Chuhan Wu et al.，**EMNLP-IJCNLP 2019，正式发表**。分别在新闻标题内部和用户已读新闻之间使用多头自注意力，再以 additive attention 聚合，形成新闻与用户编码器。是新闻推荐可复现基线的重要入口；标题语义与点击历史不能完整表示真实性、信息多样性或用户长期价值。[ACL Anthology](https://aclanthology.org/D19-1671/)

### 14. Recommending What Video to Watch Next: A Multitask Ranking System

Zhe Zhao et al.，**RecSys 2019，正式发表**。讨论大规模视频排序中的多目标冲突和隐式反馈选择偏差，用 MMoE 等软参数共享方法联合建模多个排序目标，并结合 Wide & Deep 处理偏差。值得与 YouTube 2016 对照阅读，理解从单一准确率到多目标产品优化；其工业收益依赖具体目标与流量，不能直接移植为其他平台的预期收益。[Google Research](https://research.google/pubs/recommending-what-video-to-watch-next-a-multitask-ranking-system/)

### 15. KuaiRand: An Unbiased Sequential Recommendation Dataset with Randomly Exposed Videos

Chongming Gao et al.，**CIKM 2022，正式发表**。在快手推荐流中插入随机曝光视频，收集点击、点赞、观看时长等 12 种反馈，并提供历史行为与侧信息，支持曝光偏差、长序列和多任务研究。不是新的排序算法，但对判断短视频论文是否真正改进偏好估计非常关键；“无偏”针对特定随机曝光机制，不能消除所有抽样与平台外推限制。[作者论文页](https://arxiv.org/abs/2208.08696)；[作者数据项目](https://kuairand.com/)。发表 DOI：10.1145/3511808.3557624。

### 16. Recommender Systems with Generative Retrieval（TIGER）

Shashank Rajput et al.，**NeurIPS 2023 主会，正式发表**。为内容构造具有语义结构的离散 Semantic ID，再用序列到序列模型自回归生成下一物品 ID，改变“向量检索 + ANN”的召回路径。适合研究内容冷启动与生成式召回；它是生成式推荐，不应直接写成“通用 LLM 推荐”，且论文主要证明召回能力而非整个信息流长期价值。[NeurIPS 官方论文页](https://proceedings.nips.cc/paper_files/paper/2023/hash/20dcab0f14046a5c6b02b61da9f13229-Abstract-Conference.html)

### 17. ★ Actions Speak Louder than Words: Trillion-Parameter Sequential Transducers for Generative Recommendations（HSTU）

Jiaqi Zhai et al.，**ICML 2024，正式发表**。把高基数、非平稳用户行为建模为序列转导，提出 HSTU，并研究模型效果随计算量扩大的规律，同时报告工业线上实验。价值在于推荐基础模型的系统与规模化路径；它不是直接拿文本 LLM 来聊天推荐，标题中的万亿参数也不能按稠密语言模型口径直觉比较。[PMLR 官方论文页](https://proceedings.mlr.press/v235/zhai24a.html)

### 18. RecPrompt: A Self-tuning Prompting Framework for News Recommendation Using Large Language Models

Dairui Liu et al.，**CIKM 2024，正式发表，5 页短篇**。由新闻推荐器与提示优化器迭代改进提示，利用 LLM 推断用户感兴趣的主题，并提出 TopicScore 评价主题解释。适合了解无需重训大型排序器的 LLM 重排/解释方向；实验只覆盖 400 名用户，不能据其离线提升推断平台级性能。[正式出版页](https://doi.org/10.1145/3627673.3679987)；[作者摘要与规模](https://arxiv.org/abs/2312.10463)

### 19. ★ NoteLLM-2: Multimodal Large Representation Models for Recommendation

Chao Zhang et al.，**KDD 2025，ADS Track，正式发表**。面向图文笔记推荐，将 LLM 与视觉编码器转为多模态表征模型，针对微调后忽视图像的问题使用多模态 in-context learning 与 late fusion；报告线上、线下验证。与小红书式 UGC 内容尤其贴近，展示 LLM 作为可检索 embedding 编码器的路径；结果不等于端到端自由生成推荐，也不能自动推广至所有短视频场景。[论文 DOI](https://doi.org/10.1145/3690624.3709440)；[作者机构摘要和出版状态](https://scholars.cityu.edu.hk/en/publications/notellm-2-multimodal-large-representation-models-for-recommendati/)；[作者团队确认 ADS Track](https://aml-cityu.github.io/publications/)

### 20. Personalized News Recommendation Towards the Era of LLMs: Review and Prospect

**IEEE TKDE 37(9), 5551–5567，2025，正式综述**。以新闻建模、用户建模与匹配三个核心环节组织 LLM 新闻推荐研究，适合连接传统新闻编码器与新的 LLM 路线。其价值是建立方法地图与研究问题，不能将综述中的方向讨论当作已经通过线上实验的技术收益。[IEEE 正式论文页](https://ieeexplore.ieee.org/document/11045522/)；DOI：10.1109/TKDE.2025.3581806。

### 21. ★ OneRec-Think: In-Text Reasoning for Generative Recommendation

Zhanyu Liu et al.，**ACL 2026 Long Papers，正式发表**。通过 Item-Textual Alignment 将物品 token 与文本语义对齐，再用推理激活及推荐特定奖励把对话、显式推理和个性化推荐放入统一框架，并以 Think-Ahead 结构满足工业部署。论文报告公共基准和 App 停留时长线上改善，是“生成式 ID 预测”走向“语言推理 + 推荐”的直接代表；推理文字是否忠实反映真实决策，以及其长期用户价值，仍需单独评估。[ACL 官方论文页](https://aclanthology.org/2026.acl-long.123/)

<a id="ads-recommendation"></a>

## 三、广告推荐：特征交互、兴趣建模、转化预测、预算与 LLM

广告系统不仅需要预测点击，还要处理点击后转化、预算、回报约束、出价以及服务延迟，因此同时保留预测模型与决策机制论文。

### 22. Factorization Machines

Steffen Rendle，**ICDM 2010，正式会议论文**。用低秩因子参数表示特征交互，缓解推荐和广告中极稀疏类别特征的组合估计问题，并支持线性时间计算。它是理解 FM→DeepFM 的起点；不负责时序兴趣、竞价和因果增量效果。

- [IEEE 论文页](https://ieeexplore.ieee.org/document/5694074/)，DOI 10.1109/ICDM.2010.127。IEEE 官方搜索结果已核验标题、会议、摘要、日期。

### 23. ★ Ad Click Prediction: a View from the Trenches

H. Brendan McMahan 等，**KDD 2013，正式会议论文**。以 Google 广告 CTR 系统说明 FTRL-Proximal、按坐标学习率、稀疏模型和在线更新，也讨论校准、内存、置信度和无效尝试。价值在于完整工业建模方法论；模型和分布属于当时场景，不能直接代表今日最优架构。

- [Google Research 论文页](https://research.google/pubs/ad-click-prediction-a-view-from-the-trenches/)。官方元数据与摘要核验。

### 24. DeepFM: A Factorization-Machine based Neural Network for CTR Prediction

Huifeng Guo 等，**IJCAI 2017 Main Track，正式论文**。FM 与深度网络共享 embedding，联合学习低阶与高阶交互，减少人工组合特征工程。适合作为 CTR 强基线和消融参照；本身没有显式长序列兴趣建模，也没有消除曝光偏差。

- [IJCAI 官方论文页](https://www.ijcai.org/Proceedings/2017/239)，DOI 10.24963/ijcai.2017/239。官方 proceedings 摘要核验。

### 25. ★ Deep Interest Network for Click-Through Rate Prediction

Guorui Zhou 等，**KDD 2018，正式论文**。DIN 根据候选广告对历史行为进行局部激活，获得随候选变化的用户兴趣向量，而非对所有候选共用一个固定用户表示。是广告行为序列建模的重要经典；公开数据与阿里内部数据支持其效果，但线上收益和系统规模仍依赖具体平台。

- [KDD 官方论文页](https://www.kdd.org/kdd2018/accepted-papers/view/deep-interest-network-for-click-through-rate-prediction)，[作者版本](https://arxiv.org/abs/1706.06978)。DOI 10.1145/3219819.3219823。

### 26. Entire Space Multi-Task Model: An Effective Approach for Estimating Post-Click Conversion Rate

Xiao Ma 等，**SIGIR 2018，正式短论文**。ESMM 利用曝光→点击→转化的概率分解，联合学习 CTR 与点击且转化概率，以全曝光样本和共享表征缓解 CVR 的样本选择与稀疏问题。它是广告从点击优化走向转化优化的必读；“整个曝光空间”不应理解为已经获得无偏的因果广告效果。

- [正式 DOI](https://doi.org/10.1145/3209978.3210104)，[作者摘要](https://arxiv.org/abs/1804.07931)。标题/会议/DOI交叉核验，方法来自作者摘要。

### 27. DCN V2: Improved Deep & Cross Network and Practical Lessons for Web-scale Learning to Rank Systems

Ruoxi Wang 等，**The Web Conference 2021，正式论文**。改进显式交叉网络的表达能力，并用低秩混合结构控制成本；重点在规模化排序下的准确率、算力和调参。适合作为可部署的特征交互模块；高质量表格特征与平台工程仍是效果的一部分。

- [正式 DOI](https://doi.org/10.1145/3442381.3450078)，[作者摘要](https://arxiv.org/abs/2008.13535)。ACM直连403，发表元数据交叉核验；方法来自作者页面。

### 28. A Field Guide for Pacing Budget and ROS Constraints

Santiago R. Balseiro 等，**ICML 2024，正式论文**。比较预算控制与支出回报约束的串行、最小耦合 min-pacing 和联合对偶优化，给出理论保证并用广告拍卖数据构造的半合成实验验证。提醒系统设计者：CTR/CVR 排序之外，还必须考虑预算与 ROS；实验不等同于真实在线随机试验。

- [Google Research 官方论文页](https://research.google/pubs/a-field-guide-for-pacing-budget-and-ros-constraints/)，[作者版本](https://arxiv.org/abs/2302.08530)。官方页面明确 ICML 2024，版本摘要明确 semi-synthetic。

### 29. Bid2X: Revealing Dynamics of Bidding Environment in Online Advertising from A Foundation Model Lens

Jiahao Ji 等，**KDD 2025 Applied Data Science Track，正式论文**。把出价到消耗、GMV 等结果的映射作为跨场景基础函数，用变量与时间注意力及零膨胀建模学习动态竞价环境。论文报告多场景离线评估与淘宝线上 A/B；属于竞价基础模型，不是语言 LLM，其平台收益不可直接外推。

- [正式 DOI](https://doi.org/10.1145/3711896.3737197)，[作者版本](https://arxiv.org/abs/2510.23410)。发表状态由 [KDD 官方 ADS 名单](https://www.kdd.org/kdd2025/applied-data-science-ads-track-papers-2/) 核验。

### 30. ★ ELEC: Efficient Large Language Model-Empowered Click-Through Rate Prediction

Rui Dong、Wentao Ouyang、Xiangzheng Liu，**SIGIR 2025，正式论文**。将 LLM 文本语义向量加入协同 CTR 模型，再通过分数与表征双层蒸馏迁移到只输入表格特征的小模型，使线上预测避免实时调用 LLM。是“LLM 语义知识如何进入广告排序且保留低延迟”的直接论文；摘要只支持真实数据实验，不应补写未核验的线上营收提升。

- [SIGIR 官方论文介绍](https://sigir2025.dei.unipd.it/detailed-program/paper?paper=66be31e4c40d676991f2405aaecc6934)，[正式 DOI](https://doi.org/10.1145/3726302.3730188)，[作者版本](https://arxiv.org/abs/2509.07594)。官方 accepted papers 与摘要核验。

### 31. External Large Foundation Model: How to Efficiently Serve Trillions of Parameters for Online Ads Recommendation

Mingfu Liang 等，**WWW 2025 Industrial Track，发表于 Companion Proceedings，正式产业论文**。ExFM 以外部教师模型、数据增强服务及蒸馏向多个垂直广告模型迁移知识，并处理流数据分布变化。价值是把大模型能力转化为可服务的低延迟学生模型；标题的万亿参数包含推荐系统规模语境，不能误解为同规模稠密语言 LLM。

- [正式 DOI](https://doi.org/10.1145/3701716.3715223)，[作者版本](https://arxiv.org/abs/2502.17494)。arXiv comments 明确 WWW 2025 Industrial Oral，作者正式版本首页明确 Companion Proceedings。

<a id="foundations"></a>

## 四、跨方向基础：排序目标、去偏评估与 LLM 方法地图

这四篇有助于判断前述方法究竟解决了什么，也可作为阅读前沿论文时的评估依据。

### 32. BPR: Bayesian Personalized Ranking from Implicit Feedback

Rendle 等，**UAI 2009，正式会议论文**，经典隐式反馈排序。

从贝叶斯视角推导成对排序目标，让用户已交互物品排在未交互物品之前，是隐式反馈推荐的重要基础。阅读时要注意：未交互不必然代表不喜欢，负采样与曝光机制会影响学习结果。

[文章地址：作者版](https://arxiv.org/abs/1205.2618)

### 33. ★ Recommendations as Treatments: Debiasing Learning and Evaluation

Schnabel 等，**ICML 2016，正式会议论文**，因果视角与选择偏差。

将推荐视为处理，借助倾向得分等方法校正观测反馈的选择偏差，同时讨论学习与评测。对内容和广告系统都重要；无偏性质依赖相应假设与倾向概率质量，权重过大还会带来方差问题。

[文章地址：PMLR](https://proceedings.mlr.press/v48/schnabel16.html)

### 34. Are We Really Making Much Progress? A Worrying Analysis of Recent Neural Recommendation Approaches

Ferrari Dacrema、Cremonesi、Jannach，**RecSys 2019，正式会议论文**，可复现性与强基线。

复查多种神经推荐方法，发现其中不少在充分调优的简单基线面前优势消失。适合培养阅读前沿论文时对基线、调参公平性和复现条件的敏感度；结论针对所研究的方法，不能推导为深度推荐普遍无效。

[文章地址：ACM](https://doi.org/10.1145/3298689.3347058)

### 35. How Can Recommender Systems Benefit from Large Language Models: A Survey

Lin 等，**ACM TOIS 2025，正式期刊综述**。

从“LLM 放在推荐流程哪里”和“如何训练、如何推断”两条轴，梳理特征工程、编码、排序、交互和流程控制。适合用来区分语义增强、蒸馏、直接推荐与智能体等路线；正式刊年较新，但覆盖文献存在整理截止时间。

[文章地址：ACM TOIS](https://doi.org/10.1145/3678004)

<a id="arxiv"></a>

## 五、最新 arXiv 补充：5 篇值得跟踪的预印本

以下均为本轮未核验到正式会议或期刊版本的论文。入选依据是明确任务、可检查的资源或真实系统评估；工业实验仍是作者报告，不能视为独立复现。按方向排列，保留首发日期与证据边界。

### 36. Use and Effects of LLMs in Peer Review: A Randomized Experiment and Survey at ICML 2026

Kim et al.，**arXiv:2609.19420，2026-09-16**，预印本。随机分配禁止 LLM 与允许有限辅助的政策，发现政策对录用、评分、信心影响接近零，宽松组评语更长；1,486 份问卷显示明显不遵从政策。入选因最新真实大会政策实验，研究识别的是分配政策的意向处理效应，不能据此推断实际使用 LLM 没有影响，且大会总体论文/审稿人数不是随机实验样本数。[arXiv 原文页](https://arxiv.org/abs/2609.19420)。

### 37. OpenOneRec Technical Report

Guorui Zhou et al.，**arXiv:2512.24762，2025-12-31 首发，预印本，未在本轮核验到正式会议/期刊版本**。提供覆盖 8 类任务的 RecIF-Bench、9600 万交互与 16 万用户训练数据、共同预训练和后训练流程，以及 1.7B/8B 模型，探索推荐能力与通用知识共同学习。入选理由是可复现资源、明确基准与跨数据集评估，而非只有愿景；基准由作者构建，需关注数据泄漏、独立复现和跨平台外推。[arXiv](https://arxiv.org/abs/2512.24762)；[官方模型卡](https://huggingface.co/OpenOneRec/OneRec-1.7B)

### 38. Multi-Decoder OneRec: Controllable Generative Retrieval for Multi-Objective Industrial Recommendation

You Wang et al.，**arXiv:2607.26500，2026-07-29，预印本，未在本轮核验到正式会议/期刊版本**。通过共享主干、目标独立 LoRA 专家和带配额的协调 beam search，在统一生成式召回中保留不同业务目标的控制，减少候选重复。入选理由是公开 Kwai26 大规模基准、固定候选预算对照及生产 A/B 报告；线上提升是作者报告的单平台证据，尚需同行评审与外部复现。[arXiv](https://arxiv.org/abs/2607.26500)

### 39. LLM-HYPER: Generative CTR Modeling for Cold-Start Ad Personalization via LLM-Based Hypernetworks

Luyi Ma 等，**arXiv，2026-04-13**。用少样本提示让 LLM 根据广告文本/图像直接生成线性 CTR 模型参数，以相似历史活动检索与校准缓解新广告冷启动。入选因为任务明确、方法能形成可服务预测器，且作者报告离线实验及生产 A/B；未见接收信息，内部平台实验与大幅离线收益需独立复验。

- [arXiv 摘要与版本记录](https://arxiv.org/abs/2604.12096)。作者报告的 NDCG@10 相对提升不等同于普遍 CTR 提升。

### 40. From Language to Behavior: Scaling Sequence Transformers for Industrial Recommendation Ranking with Rec-Native Designs

Jie Chen 等，**arXiv，2026-09-01**。ReST 为广告长行为序列设计门控注意力及时间编码，并把重用户编码器与轻候选解码器拆开，复用共享历史计算。入选因为同时讨论排序质量、规模扩展、线上延迟和一周 A/B；这是推荐专用 Transformer 而非通用语言模型，实验短且平台数据不可完全复现，目前应作为前沿跟踪而非定论。

- [arXiv 摘要与版本记录](https://arxiv.org/abs/2609.01240)。作者报告 P99 50ms预算、在线AUC和收入指标提升；摘要中的效果数值不构成跨平台效果保证。

<a id="econ-scope"></a>

## 经济学增补的范围与阅读口径

本轮新增 **35 篇（#41–#75）**，按研究问题而非仅按 venue 排列。这里的 **EC** 指 ACM Conference on Economics and Computation（会议）；对应专业期刊是 **ACM Transactions on Economics and Computation（TEAC）**。Management Science（MS）与 Marketing Science 为不同期刊。

| 补充问题 | 核心变量与机制 | 对前文算法研究的补充 |
|---|---|---|
| 审稿人与用户是否真实反馈 | 努力、支付、同行预测、策略行为 | 匹配到合适的人之后，仍需处理反馈质量与激励 |
| 新内容为什么能获得探索 | 个体试错成本、信息披露、激励相容 | 算法希望探索，不代表用户自愿承担探索成本 |
| 排序怎样改变未来内容 | 创作者进入、质量投入、奖励与均衡 | 内容供给和行为日志会随算法改变，不能总视为固定输入 |
| 广告和平台收益来自哪里 | 拍卖、定向、价格、增量转化 | 预测准确率、收入和消费者福利是不同结果变量 |
| LLM 怎样进入经济机制 | 可微拍卖、生成内容分配、语言信息设计 | 不仅用 LLM 预测或解释，还研究规则本身与参与者激励 |

**核验口径（2026-09-28）：**本轮针对 ACM EC/TEAC、Management Science、Marketing Science、Information Systems Research、Operations Research，以及 AER、AEJ: Microeconomics、QJE、JPE、Econometrica、ReStud、RAND、JEP、IJIO 等来源进行主题检索，另用 JACM、WWW、NeurIPS 的直接相关论文连接算法与机制设计；不声称遍历这些 venue 的全部文献。期刊卷期年与 online first 日期分别列出，EC 单页／两页摘要与完整会议论文分别标注。期刊扩展版、会议摘要及 arXiv/SSRN 全文只计一项研究。尚在返修（R&R）的工作论文和仅有题名的候选不进入本轮核心增补。

**证据边界：**理论结果在相应信息、偏好、成本和均衡假设下成立；计算实验不是现场因果证据；结构反事实依赖识别假设与模型；随机实验也受平台、样本和时间窗限制。摘要基于官方网页及可访问作者材料，并非全部全文精读；未下载 PDF。部分 ACM 页面无法直接打开时，以官方会议目录、作者机构页与 DOI 交叉核验。原 #36–#40 保留为首轮筛选的预印本，本轮未重新审查其全部发表状态。

<a id="econ-peer"></a>

## 六、同行评审的经济机制：努力、真实报告与制度偏差

<a id="paper-41"></a>

### 41. Informed Truthfulness in Multi-Task Peer Prediction

- 作者：Victor Shnayder、Arpit Agarwal、Rafael Frongillo、David C. Parkes。
- 状态：ACM EC 2016，正式会议论文；理论机制设计。
- 总结：在没有可验证真值的环境中，利用多个任务之间的报告相关性设计 Correlated Agreement 机制，使认真获取信息并诚实报告优于无信息策略，并给出不需要设计者预知分布的近似版本。它补充原清单 #1–#3 的匹配与抗操纵：分到合适的人之后，还须激励其认真报告。保证依赖信号与多任务结构，不等于真实评审中唯一均衡或彻底抗串通。
- 链接：[正式 DOI](https://doi.org/10.1145/2940716.2940790)；[作者 arXiv 摘要](https://arxiv.org/abs/1603.03151)；[EC 官方论文目录](https://sigecom.org/proceedings16.html)。

<a id="paper-42"></a>

### 42. Peer Prediction with Heterogeneous Users

- 作者：Arpit Agarwal、Debmalya Mandal、David C. Parkes、Nisarg Shah。
- 状态：ACM TEAC 8(1), Article 2，2020，正式期刊；扩展自 EC 2017；理论＋真实数据验证。
- 总结：放松同质评估者假设，将具有不同偏好或信号分布的人分组，并结合聚类、统计估计与同行评分，保留近似 informed truthfulness。真实数据用于检查有限分组下的近似是否合理。对跨学科审稿特别有启发：合理分歧不能简单视为低质量。它连接原 #7 的专业画像与报告激励，但不能把聚类自动解释为学科真值或已部署的审稿系统。
- 链接：[正式 DOI](https://doi.org/10.1145/3381519)；[作者出版清单（核验期刊版本）](https://agarpit.github.io/publications/)；[EC 2017 DOI，仅用于版本追踪](https://doi.org/10.1145/3033274.3085127)。

<a id="paper-43"></a>

### 43. Measurement Integrity in Peer Prediction: A Peer Assessment Case Study

- 作者：Noah Burrell、Grant Schoenebeck。
- 状态：ACM EC 2023，369–389，正式会议全文；代理模拟＋真实同行评分数据。
- 总结：提出 measurement integrity，检查最终获得的报酬是否真实反映贡献，而不只看诚实报告的期望激励。通过代理模拟与真实课程互评数据比较机制，发现理论激励性质对实际表现的预测有噪声，准确衡量贡献与抗策略操纵之间存在权衡；加入贴近数据的参数模型可改善两者。补充原 #5、#9 的效果评估，但课堂互评结论不能直接外推至研究论文审稿。
- 链接：[正式 DOI](https://doi.org/10.1145/3580507.3597744)；[作者 arXiv 摘要](https://arxiv.org/abs/2108.05521)；[EC 官方目录](https://sigecom.org/proceedings23.html)。

<a id="paper-44"></a>

### 44. ★ Peer Review Market Design: Effort-Based Matching and Admission Control

- 作者：Craig Fernandes、James Siderius、Raghav Singal。
- 状态：ACM EC 2025，论文集一页摘要（p.540），全文为作者 SSRN 版本；理论＋模拟，未核实正式期刊版。
- 总结：把作者同时承担审稿角色建模为单边市场，比较随机匹配、对称匹配和将投稿资格与审稿努力挂钩的 admission control。完美观察努力时获得一阶最优；在文中噪声设定下仍给出福利近似保证。它直接补充原 #2 的相似度公平分配：专业匹配不自动诱发努力。关键限制是努力识别误差与惩罚机制的现实公平性，结果来自模型及模拟而非大会随机试验。
- 链接：[正式会议摘要 DOI](https://doi.org/10.1145/3736252.3742586)；[作者全文 SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5205896)；[作者所在大学摘要](https://math.dartmouth.edu/~acms/seminar_pages/SingalS25.html)。

<a id="paper-45"></a>

### 45. ★ What Policies Increase Prosocial Behavior? An Experiment with Referees at the Journal of Public Economics

- **作者/发表**：Raj Chetty、Emmanuel Saez、Laszlo Sandor；Journal of Economic Perspectives，28(3):169–188，2014，正式论文。
- **类型**：现场随机实验；审稿激励。
- **总结**：将约1500名审稿人随机分配到不同截止日期、按时提交现金奖励及公布审稿耗时的社会激励组，发现缩短期限和现金奖励明显加速审稿，社会激励也有效且对资深教授更明显。它直接补充“匹配到谁”之后的履约机制设计。研究未发现多数质量指标显著恶化，但评语长度与编辑采纳等代理指标不能完全衡量科学判断质量，单一期刊结果也不宜无条件外推。
- **文章地址/DOI**：[AEA正式页面](https://www.aeaweb.org/articles?id=10.1257%2Fjep.28.3.169)。
- **避免误标**：研究现场是Journal of Public Economics；实际发表期刊是Journal of Economic Perspectives。

<a id="paper-46"></a>

### 46. Are Referees and Editors in Economics Gender Neutral?

- **作者/发表**：David Card、Stefano DellaVigna、Patricia Funk、Nagore Iriberri；The Quarterly Journal of Economics，135(1):269–327，2020（2019在线），正式论文。
- **类型**：观察数据与引用基准的制度评估，非随机实验。
- **总结**：用四家经济学期刊投稿记录研究作者性别、审稿意见与编辑决定的关系。男性和女性审稿人的相对评价差异不明显，但在控制评语等条件后，女性作者论文获得更多后续引用，提示相对于引用最大化基准存在更高门槛。适合提醒审稿匹配模型勿把历史录用标签当作无偏真值；引用不是完整质量标准，文章也不能识别所有偏差来源或证明个别评审者歧视。
- **文章地址/DOI**：[QJE文章](https://doi.org/10.1093/qje/qjz035)；[期刊卷期目录](https://academic.oup.com/qje/issue/135/1)核实年卷页；[作者所在学会研究摘要](https://eeassoc.org/committees/wine/research-highlights/are-referees-and-editors-economics-gender-neutral)核对结论。

<a id="econ-information"></a>

## 七、信息设计与激励相容：谁愿意探索、谁会迎合算法

<a id="paper-47"></a>

### 47. ★ Bayesian Persuasion

- **作者/发表**：Emir Kamenica、Matthew Gentzkow；American Economic Review，101(6):2590–2615，2011，正式论文。
- **类型**：信息设计理论；基础。
- **总结**：研究掌握信号设计权的一方，如何通过选择公开的信息结构影响理性接收者的行动，并刻画使发送者受益的条件及最优信号。其意义是把“给用户展示什么”写成明确优化问题，为推荐、广告披露和解释策略提供共同语言。它并非推荐算法实证研究；共识先验、可承诺的信息政策和收益结构等假设决定结论，也不能将发送者最优误写为消费者最优。
- **文章地址/DOI**：[AEA正式页面](https://pubs.aeaweb.org/doi/10.1257/aer.101.6.2590)。

<a id="paper-48"></a>

### 48. Incentivizing Exploration

- 作者：Peter I. Frazier、David Kempe、Jon Kleinberg、Robert Kleinberg。
- 状态：ACM EC 2014，5–22，正式会议全文；理论。
- 总结：将多臂老虎机扩展为平台依赖短视、自利用户进行探索的情形，研究如何通过报酬协调个体行动与平台长期信息价值，并刻画福利与激励成本的关系。适合与原 #10 的 LinUCB 对读：算法希望探索，并不意味着用户会自愿承担试错成本。其价值在激励约束而非新推荐网络；效用、折扣与支付假设需要在实际业务中重新验证。
- 链接：[正式 DOI](https://doi.org/10.1145/2600057.2602897)；[作者原文链接（仅供用户阅读）](https://david-kempe.com/publications/IncentivizingExploration.pdf)。

<a id="paper-49"></a>

### 49. Bayesian Exploration: Incentivizing Exploration in Bayesian Games

- 作者：Yishay Mansour、Aleksandrs Slivkins、Vasilis Syrgkanis、Zhiwei Steven Wu。
- 状态：Operations Research 70(2):1105–1127，2022（2021-12-29 online），正式期刊；理论。
- 总结：平台通过控制过去经验向后续用户的信息披露，在不支付金钱的条件下推荐探索，同时满足贝叶斯激励相容。每轮允许多个用户在共同环境中互动，并通过“可探索行动”刻画可实现学习的边界，给出相应遗憾保证。它把原 #10 的探索问题连接到信息设计与博弈；保证限于模型定义的可探索基准，不能理解为任意行动和任意先验都能无代价探索。
- 链接：[INFORMS 正式页面与摘要](https://pubsonline.informs.org/doi/10.1287/opre.2021.2205)。

<a id="paper-50"></a>

### 50. ★ Scoring Strategic Agents

Ian Ball｜**American Economic Journal: Microeconomics 17(1), 97–129，2025；正式期刊论文**｜理论：策略性评分。

研究被评分者能以私人已知成本修改特征时，中介应该如何构造预测分数。最优规则可能降低某些特征的权重以抑制迎合，同时调整其他权重保持平均校准；最优预测不再只是拟合固定数据。它补充前文 CTR 与审稿匹配模型忽略的策略性反应，可用于思考创作者迎合、刷指标和学术画像包装；这些场景是迁移解释，并非论文已验证的应用，结论依赖其信息和成本结构。

[AEA 正式论文](https://www.aeaweb.org/articles?id=10.1257/mic.20230275)；DOI：10.1257/mic.20230275。

<a id="paper-51"></a>

### 51. Market Segmentation Through Information

- **作者/发表**：Matthew Elliott、Andrea Galeotti、Andrew Koh、Wenhao Li；The Review of Economic Studies，2026-06-17在线发表，文章号rdag067；正式论文，尚不填未核实卷期。
- **类型**：信息设计与寡头竞争理论；前沿。
- **总结**：把掌握消费者偏好数据的平台建模为信息设计者，由它决定向竞争企业披露哪些信息，随后企业进行差异化产品Bertrand定价。论文刻画消费者和生产者剩余可达边界，说明同样的数据可被用于强化或缓和竞争。对广告定向、平台中介权力及推荐福利非常相关；结论依赖平台观察偏好与信息承诺等模型设定，并非算法上线后的因果福利估计。
- **文章地址/DOI**：[ReStud正式页面](https://doi.org/10.1093/restud/rdag067)。
- **去重说明**：正文致谢明确本篇吸收同作者旧稿“Matching and Information Design in Marketplaces”和Wenhao Li旧稿“Using Information to Amplify Competition”，不要另列重复项。

<a id="paper-52"></a>

### 52. ★ Information Design of Online Platforms

- **作者／发表：**T. Tony Ke、Song Lin、Michelle Y. Lu；Management Science **Articles in Advance，online 2026-06-15**；已正式发表，尚无卷期页码。
- **类型／定位：**信息设计／博弈理论；前沿；自然推荐与定向广告的统一机制。
- **内容：**用信息设计统一分析平台如何引导消费者搜索，同时影响商家的定向广告竞争。平台在提高匹配效率与通过显著展示位置竞争抽取商家剩余之间权衡，利润最优方案可能限制搜索，并把匹配商品与大量不匹配商品混合推荐。因此，更精细的信息并不保证社会效率更高；这是给定信息、搜索与竞争结构的理论结果，尚非真实平台干预效应。
- **文章：**[INFORMS 官方页](https://pubsonline.informs.org/doi/10.1287/mnsc.2025.03083)；DOI `10.1287/mnsc.2025.03083`。
- **去重：**官方页面明确注明短版本发表于 **EC 2023**，早期题名 **Personalization Trap**；与这些版本只计一篇。

<a id="paper-53"></a>

### 53. Impact of Rankings and Personalized Recommendations in Marketplaces

- 作者：Omar Besbes、Yash Kanoria、Akshit Kumar。
- 状态：ACM EC 2025 收录（正式目录核实，已核会议收录，未核实全文页数及论文集刊载形式）；作者机构仍标 Working Paper；理论。
- 总结：将效用分为公共质量与个体契合度，比较公共榜单和个性化推荐在供给无限及供给受限市场的福利效果。受限市场中，所有人都知道同一公共质量带来的收益有限，个性化匹配则更有价值。它将原 #13、#19 的相关性建模连接到市场约束，也解释论文审稿人有限容量与数字内容可重复消费的区别；结论依赖风格化偏好分布与分配模型。
- 链接：[EC 正式 DOI](https://doi.org/10.1145/3736252.3742547)；[作者机构摘要](https://business.columbia.edu/faculty/research/impact-rankings-and-personalized-recommendations-marketplaces)；[作者全文摘要](https://arxiv.org/abs/2506.03369)。

<a id="econ-platform"></a>

## 八、内容平台与多边市场：供给、多样性、策略行为与经济价值

<a id="paper-54"></a>

### 54. Blockbuster Culture's Next Rise or Fall: The Impact of Recommender Systems on Sales Diversity

- **作者／发表：**Daniel Fleder、Kartik Hosanagar；Management Science **55(5):697–712，2009**；online 2009-03-06。
- **类型／定位：**理论＋选择模型仿真；经典；流行度反馈、多样性。
- **内容：**通过解析模型和结合实际推荐算法的选择仿真，研究推荐如何改变销售分布。基于历史销量与评分的推荐可能强化热门产品，使个体消费种类扩大、市场总体销量却更加集中。这解释了“用户发现新东西”和“平台头部化”可以同时发生，适合确定多样性指标。结论来自模型与仿真，不是平台现场因果效应，也不意味着所有推荐算法必然降低多样性。
- **文章：**[INFORMS 官方页](https://pubsonline.informs.org/doi/10.1287/mnsc.1080.0974)；DOI `10.1287/mnsc.1080.0974`。

<a id="paper-55"></a>

### 55. When and How to Diversify—A Multicategory Utility Model for Personalized Content Recommendation

- **作者／发表：**Yicheng Song、Nachiketa Sahoo、Elie Ofek；Management Science **65(8):3737–3757，2019**；online 2019-04-03。
- **类型／定位：**结构效用模型＋点击流估计＋反事实仿真；经典；动态多样性。
- **内容：**把阅读会话视为连续效用最大化选择，联合刻画内容类别偏好、消费饱和与搜索成本，让推荐多样性随会话动态变化。使用媒体网站点击流估计模型，显示可以改善预测并更贴近读者的多样性需求。它将“多样性约束”转化为有行为基础的排序设计；额外阅读量与效用提升是政策仿真结果，不能写成已实现的随机实验收益。
- **文章：**[INFORMS 官方页](https://pubsonline.informs.org/doi/10.1287/mnsc.2018.3127)；DOI `10.1287/mnsc.2018.3127`。

<a id="paper-56"></a>

### 56. ★ The Editor and the Algorithm: Recommendation Technology in Online News

- **作者／发表：**Christian Peukert、Ananya Sen、Jörg Claussen；Management Science **70(9):5816–5831，2024**；online 2023-10-17。
- **类型／定位：**理论＋新闻网站现场随机实验；人机混合策展。
- **内容：**通过新闻网站现场实验比较编辑策展与个性化推荐，发现算法平均点击表现更好，但用户数据不足或偏好差异较大时编辑相对占优。理论将算法可扩展但较窄的信息，与编辑广泛却难以规模化的知识联系起来，支持按场景组合两者。混合策略的收益计算与实际随机化干预范围需要区分，研究没有证明点击提升等同于新闻质量、公共知识或长期福利提高。
- **文章：**[INFORMS 官方页](https://pubsonline.informs.org/doi/10.1287/mnsc.2023.4954)；DOI `10.1287/mnsc.2023.4954`。

<a id="paper-57"></a>

### 57. ★ Digital Content Creation: An Analysis of the Impact of Recommendation Systems

- **作者／发表：**Kun Qian、Sanjay Jain；Management Science **70(12):8668–8684，2024**；online 2024-03-05。
- **类型／定位：**博弈论；创作者努力、广告分成与推荐偏置。
- **内容：**把平台广告分成、推荐流量分配与创作者质量努力放入同一均衡模型。偏离消费者即时最佳匹配的推荐，在一定条件下能通过强化创作激励提高质量，并使平台、创作者与消费者共同受益。直接说明排序目标需要考虑供给侧反应，而不只预测固定内容的点击率；“有偏推荐可能有益”是条件性理论结论，不是任意操纵推荐的实证支持。
- **文章：**[INFORMS 官方页](https://pubsonline.informs.org/doi/10.1287/mnsc.2022.03655)；DOI `10.1287/mnsc.2022.03655`。

<a id="paper-58"></a>

### 58. ★ Quality-Variety Tradeoffs in Recommendation Systems on Content Platforms

- **作者／发表：**Tianxin Zou、Yue Wu、Miklos Sarvary；Management Science **72(8):6970–6992，2026**；online **2025-11-19**。已进入正式卷期，不能仅标为forthcoming。
- **类型／定位：**博弈／均衡理论；前沿；创作者进入、质量和爆款。
- **内容：**显式建模创作者进入、质量投入以及少数爆款的不确定需求，研究推荐对内容供给的长期影响。更强调质量可能压缩创作者进入和内容品类，减少爆款出现，反而降低消费者对平台的评价；消费多样性对质量权重还可能呈U形。适合解释质量、个性化和生态繁荣为何不是同一目标；方向依赖进入壁垒、创作灵活性与消费者偏好等模型条件。
- **文章：**[INFORMS 官方页](https://pubsonline.informs.org/doi/10.1287/mnsc.2025.00300)；DOI `10.1287/mnsc.2025.00300`。

<a id="paper-59"></a>

### 59. Measuring Strategization in Recommendation: Users Adapt Their Behavior to Shape Future Content

- 作者：Sarah H. Cen、Andrew Ilyas、Jennifer Allen、Hannah Li、Aleksander Mądry（按正式目录，非早期议程中额外列出的作者）。
- 状态：ACM EC 2024，203–204，正式会议短摘要；完整研究为作者 arXiv；实验室实验＋问卷。
- 总结：通过定制音乐播放器改变用户对算法利用点赞和停留时间的认知及激励，发现用户会调整行为以影响未来推荐，而非被动表达固定偏好。获知算法重视点赞的参与者更频繁使用相关按钮。它挑战原 #12、#17 等行为序列模型的外生反馈假设；实验室证据识别策略行为，问卷自报则不能单独证明真实平台上的效应大小。
- 链接：[正式摘要 DOI](https://doi.org/10.1145/3670865.3673634)；[作者全文摘要](https://arxiv.org/abs/2405.05596)；[EC 官方作者目录](https://sigecom.org/proceedings24.html)。

<a id="paper-60"></a>

### 60. Supply-Side Equilibria in Recommender Systems

- 作者：Meena Jagadeesan、Nikhil Garg、Jacob Steinhardt。
- 状态：NeurIPS 2023，正式会议全文；EconCS 理论桥接，不冒充 EC 论文。
- 总结：把内容生产者选择建模为多维内容向量，把用户表示为异质偏好，分析个性化推荐诱发的供给侧均衡。通过对偶方法刻画创作者专业化的充要条件，并指出专业化提高内容差异性的同时，也可能减少市场竞争并保留利润。它补充原 #11、#19 的召回表征：表征和分发规则会反向塑造未来供给。结论属于模型均衡分析，不是现实平台多样性的因果估计。
- 链接：[NeurIPS 正式摘要](https://proceedings.neurips.cc/paper_files/paper/2023/hash/2f1486343c2c942a617e4f5bb0cc64c8-Abstract-Conference.html)。

<a id="paper-61"></a>

### 61. Rethinking Incentives in Recommender Systems: Are Monotone Rewards Always Beneficial?

- 作者：Fan Yao、Chuanhao Li、Karthik Abinav Sankararaman、Yiming Liao、Yan Zhu、Qifan Wang、Hongning Wang、Haifeng Xu。
- 状态：NeurIPS 2023，正式会议全文；EconCS 机制理论＋模拟。
- 总结：研究创作者为平台报酬竞争时的内容供给，证明一类看似合理的单调奖励机制仍会产生不可消除的福利损失。提出 Backward Rewarding Mechanisms，使博弈形成势函数结构，并将其与目标福利联系。与原 #14 的多目标排序不同，这里调节的是创作者激励；均衡存在与势函数改善不意味着必然找到全局最优，也未提供长期平台因果实验。
- 链接：[NeurIPS 正式摘要](https://proceedings.neurips.cc/paper_files/paper/2023/hash/ebfabf372037aaa4a8d92c9b457ece3e-Abstract-Conference.html)。

<a id="paper-62"></a>

### 62. Optimal Match Recommendations in Two-sided Marketplaces with Endogenous Prices

- **作者／发表：**Peng Shi；Management Science **71(9):7431–7448，2025**；online 2024-12-19。
- **类型／定位：**市场设计与优化理论；供需均衡、推荐与定价。
- **内容：**把服务提供者根据供需自主定价的反应纳入匹配推荐优化，给出可有效计算的政策结构，并说明可以用向不同用户群推荐各供给者的频率来编码政策。若把价格当作固定输入，即使价格重新均衡后反复优化推荐，也可能停在严格次优结果。适合把静态排序升级为均衡感知设计；其最优性保证依赖论文市场模型，不能直接推广到所有内容或广告拍卖。
- **文章：**[INFORMS 官方页](https://pubsonline.informs.org/doi/10.1287/mnsc.2022.02691)；DOI `10.1287/mnsc.2022.02691`。

<a id="paper-63"></a>

### 63. Targeted Advertising as Implicit Recommendation: Strategic Mistargeting and Personal Data Opt-out

- **作者／发表：**Z. Eddie Ning、Jiwoong Shin、Jungju Yu；Marketing Science **44(2):390–410，2025**；online 2024-08-02。
- **类型／定位：**信号与博弈理论；定向广告、消费者信念、隐私选择。
- **内容：**当消费者不知道自身与商品的匹配程度时，收到定向广告本身成为隐含推荐，广告主因此可能策略性触达低匹配消费者。研究发现，预测更准并不必然减少错误定向；允许价格内生后，广告主可能利用推荐信号涨价，降低消费者福利并刺激退出数据收集。它把预测准确率与利益一致性区分开来，结论依赖价格和隐私默认规则等均衡条件。
- **文章：**[INFORMS 官方页](https://pubsonline.informs.org/doi/10.1287/mksc.2023.0117)；DOI `10.1287/mksc.2023.0117`。

<a id="paper-64"></a>

### 64. Recommending for a Multi-Sided Marketplace: A Multi-Objective Hierarchical Approach

- **作者／发表：**Yuyan Wang、Long Tao、Xian Xing Zhang；Marketing Science **44(1):1–29，2025**；online 2024-08-14。
- **类型／定位：**机器学习＋消费者行为模型＋约束优化＋线上实验；MOHR。
- **内容：**提出MOHR，把机器学习、概率化层级浏览模型和多目标约束优化结合，兼顾首页横排内容组与单个条目的排序。在Uber Eats线上实验中改善转化、留存和交易表现，并被部署到全球首页。对内容平台的价值在于提供用户、供给者和平台目标的可解释权衡方法；这是外卖平台证据，业务收益不能直接当作消费者剩余或社会福利，也不能照搬至短视频。
- **文章：**[INFORMS 官方页](https://pubsonline.informs.org/doi/10.1287/mksc.2022.0238)；DOI `10.1287/mksc.2022.0238`。

<a id="paper-65"></a>

### 65. To Brush or Not to Brush: Product Rankings, Consumer Search, and Fake Orders

- **作者／发表：**Chen Jin、Luyi Yang、Kartik Hosanagar；Information Systems Research **34(2):532–552，2023**；online 2022-05-20。
- **类型／定位：**动态排序与博弈理论；反操纵机制。
- **内容：**建模商家通过虚假订单争夺搜索排名，以及排名、搜索摩擦和真实购买之间的反馈。提高刷单成本、降低搜索成本或改用近期销量排序，都未必单调改善消费者福利，因为不同类型商家会重新选择操纵强度。适合提醒算法设计者把对抗性行为纳入评估；基础模型高度简化，聚焦排名可见度，未完整刻画假评论欺骗等其他通道。
- **文章：**[INFORMS 官方页](https://pubsonline.informs.org/doi/10.1287/isre.2022.1128)；DOI `10.1287/isre.2022.1128`。

<a id="paper-66"></a>

### 66. ★ The Value of Personalized Recommendations: Evidence from Netflix

- 作者：Kevin Zielnicki、Guy Aridor、Aurélien Bibaut、Allen Tran、Winston Chou、Nathan Kallus。
- 状态：International Journal of Industrial Organization，2026-06-09 在线发表；卷 108，103304 标注 October 2026。同一研究亦列入 EC 2026 官方录用名单，只计一篇。旧机构页面仍标 Working Paper，采用新出版社状态。
- 方法：结构需求估计＋随机实验验证＋模型反事实；不是全篇纯随机试验。
- 总结：以约两百万美国 Netflix 用户的数据估计含动态偏好与推荐效用的离散选择模型，并用随机扰动推荐的分流比例验证模型。反事实表明替换为矩阵分解或热门榜会使参与度下降约 4% 和 12%，且有效定向比机械曝光更重要，中等热门内容获益最大。它连接原 #11、#12、#17 的算法进步与经济价值；数值依赖条件外生性与结构模型，参与度不等于消费者福利。
- 链接：[出版社正式页面](https://www.sciencedirect.com/science/article/abs/pii/S0167718726000561)；[DOI](https://doi.org/10.1016/j.ijindorg.2026.103304)；[作者 arXiv](https://arxiv.org/abs/2511.07280)。

<a id="econ-ads"></a>

## 九、广告市场与定价：拍卖、增量效果和算法竞争

<a id="paper-67"></a>

### 67. ★ Internet Advertising and the Generalized Second-Price Auction: Selling Billions of Dollars Worth of Keywords

- **作者/发表**：Benjamin Edelman、Michael Ostrovsky、Michael Schwarz；American Economic Review，97(1):242–259，2007，正式论文。
- **类型**：博弈论／机制设计；经典。
- **总结**：分析搜索广告的广义第二价格拍卖（GSP），解释为什么它虽然外观类似VCG，却通常不具备占优策略均衡，诚实报价一般也不构成均衡。通过对应的广义英式拍卖刻画均衡与支付，为理解位置分配、广告质量与策略出价提供基础。适合连接CTR预测和真正的广告分配规则；结论来自特定静态拍卖设定，不能直接套用预算约束、自动竞价和动态市场。
- **文章地址/DOI**：[AEA正式页面](https://pubs.aeaweb.org/doi/10.1257/aer.97.1.242)。

<a id="paper-68"></a>

### 68. Targeting in advertising markets: implications for offline versus online media

- **作者/发表**：Dirk Bergemann、Alessandro Bonatti；The RAND Journal of Economics，42(3):417–443，2011，正式论文。
- **类型**：均衡理论；经典。
- **总结**：在多广告主、多媒体市场中研究定向精度如何改变消费者—产品匹配及广告市场竞争。更精准的定向提高匹配数量与广告社会价值，却也提高每个细分市场中广告主的集中度，导致均衡广告价格对定向能力呈非单调变化。它说明更准确的推荐并不保证平台广告收入单调增加；这是模型内的均衡结论，不能当作隐私政策或现实广告收益的因果估计。
- **文章地址/DOI**：[Wiley正式页面](https://onlinelibrary.wiley.com/doi/abs/10.1111/j.1756-2171.2011.00143.x)。

<a id="paper-69"></a>

### 69. ★ Consumer Heterogeneity and Paid Search Effectiveness: A Large-Scale Field Experiment

- **作者/发表**：Thomas Blake、Chris Nosko、Steven Tadelis；Econometrica，83(1):155–174，2015，正式论文。
- **类型**：大规模现场随机实验；广告增量效果。
- **总结**：借助eBay付费搜索广告实验，区分广告带来的新增购买和用户原本已有的购买意愿。品牌关键词广告未显示可测短期收益，非品牌广告对新用户和低频用户更有效，而大量费用投向原本就会购买的高频用户。它是“预测点击或转化不等于增量效果”的关键读物；结果依赖成熟品牌、用户构成和短期窗口，不能推出所有品牌或所有搜索广告均无效。
- **文章地址/DOI**：[Wiley正式页面](https://onlinelibrary.wiley.com/doi/abs/10.3982/ECTA12423)。

<a id="paper-70"></a>

### 70. ★ Reserve Prices in Internet Advertising Auctions: A Field Experiment

- **作者/发表**：Michael Ostrovsky、Michael Schwarz；Journal of Political Economy，131(12):3352–3376，2023，正式论文。
- **类型**：拍卖理论＋现场实验。
- **总结**：把最优拍卖理论适配到搜索广告场景，并在大型实际广告拍卖中实验不同保留价。研究报告新保留价显著提高卖方收入，展示机制设计如何从理论转化为平台决策，是连接排序分数和商业变现的强证据。需要区分平台收入与广告主、消费者福利；原生产数据及生成保留价代码为专有，公开复核材料使用合成数据，且2023是发表年而非实验发生年。
- **文章地址/DOI**：[JPE正式页面](https://www.journals.uchicago.edu/doi/full/10.1086/725702)。

<a id="paper-71"></a>

### 71. Artificial Intelligence, Algorithmic Pricing, and Collusion

- **作者/发表**：Emilio Calvano、Giacomo Calzolari、Vincenzo Denicolò、Sergio Pastorello；American Economic Review，110(10):3267–3297，2020，正式论文。
- **类型**：重复博弈＋Q-learning计算实验。
- **总结**：让Q-learning定价算法在重复寡头竞争模型中交互，发现它们在未直接通信的情况下可能学出高于竞争基准的价格，并用惩罚和恢复路径维持这些结果。适合研究推荐、竞价或定价代理彼此适应时的战略风险，也提供从独立预测走向多智能体分析的入口。这里是计算机模拟市场，既非真实平台随机试验，也非LLM实验证据，更不能据此断言现实算法普遍合谋。
- **文章地址/DOI**：[AEA正式页面](https://www.aeaweb.org/articles?id=10.1257%2Faer.20190623)。

<a id="paper-72"></a>

### 72. Dynamic Pricing With Recommendation and Consumer Feedback

- **作者/发表**：Wenji Xu、Shuoguang Yang；The RAND Journal of Economics，57(2):349–367，2026（期刊卷期年；较早online记录可显示2025），正式论文。
- **类型**：动态信息设计／定价理论；前沿。
- **总结**：联合研究新产品的动态价格与推荐政策：更多销售会加快消费者反馈，从而改善后续决策。最优政策可能交替推荐已验证产品与尚未验证产品，并出现早期或后期折扣、价格回调甚至低于成本的价格。它把推荐探索的价值与商业激励连接起来；模型采用长期卖方、短期消费者及特定反馈到达机制，不是深度强化学习效果比较，也不直接覆盖多卖方平台竞争。
- **文章地址/DOI**：[Wiley正式页面](https://onlinelibrary.wiley.com/doi/10.1111/1756-2171.70016)。
- **核验交叉来源**：[作者主页](https://www.wenji-xu.com/)、[期刊当前卷期目录](https://onlinelibrary.wiley.com/toc/17562171/current)。卷期页码另用[RePEc记录](https://ideas.repec.org/a/bla/randje/v57y2026i2p349-367.html)交叉确认。

<a id="econ-llm"></a>

## 十、深度学习与 LLM 的机制设计

<a id="paper-73"></a>

### 73. ★ Optimal Auctions through Deep Learning: Advances in Differentiable Economics

Paul Dütting、Zhe Feng、Harikrishna Narasimhan、David C. Parkes、Sai Srivatsa Ravindranath｜**Journal of the ACM 71(1), Article 5，2024；正式期刊扩展版**｜可微机制设计：理论与计算实验。

将拍卖的分配和支付规则参数化为神经网络，把收入最大化与激励相容约束写成可训练问题，研究泛化并在多物品拍卖中恢复已知机制、探索未知机制。它与前文 DeepFM、DIN 的区别是学习“市场规则”，而非仅学习点击概率；有限样本上很小的偏离收益不等于对任意参与者、任意分布都已证明严格激励相容。ICML 2019 早期版和 JACM 扩展版只计一篇。

[JACM 正式 DOI](https://doi.org/10.1145/3630749) · [作者机构出版记录](https://parkes.seas.harvard.edu/publication-authors/duetting-paul) · [作者版](https://arxiv.org/abs/1706.03459)。

<a id="paper-74"></a>

### 74. Mechanism Design for Large Language Models

Paul Dütting、Vahab Mirrokni、Renato Paes Leme、Haifeng Xu、Song Zuo｜**The Web Conference（WWW）2024, 144–155；正式会议论文**｜LLM 生成内容拍卖：理论与模型演示。

让参与者的偏好由语言模型表示，通过逐 token 拍卖和单维出价影响生成内容，建立激励性质与聚合单调性的关系，并据此设计支付规则。连接广告机制与 LLM 生成，而不是仅提高 CTR；模型演示尚不足以证明用户信任、长期福利或真实广告营收提高。该文在 EC 2024 的 Highlights Beyond EC 出现过，但原始发表 venue 是 WWW，不能重复算成另一篇 EC 论文。

[Google Research 正式出版信息与摘要](https://research.google/pubs/mechanism-design-for-large-language-models/) · [作者版](https://arxiv.org/abs/2310.10826)。

<a id="paper-75"></a>

### 75. ★ Information Design with Large Language Models

Paul Dütting、Safwan Hossain、Tao Lin、Renato Paes Leme、Sai Srivatsa Ravindranath、Haifeng Xu、Song Zuo（作者版顺序）｜**ACM EC 2026，官方录用名单已核验；完整作者版 arXiv:2509.25565v2（2026-03-03）**｜信息设计：理论与计算实证。

把自然语言措辞产生的 framing 效应与贝叶斯信号设计结合，刻画仅优化措辞和联合优化措辞、信号时的可计算性，并用 LLM 搜索语言空间。它把“推荐解释怎么说”纳入经济机制，而不只优化推什么；以 LLM 近似接受者的信念响应，不保证能准确表示真实用户或福利。已确认会议录用，未在本轮确认 proceedings 的全文或单页摘要形式，故不编造页码或 DOI，也不再标为仅预印本。

[EC 2026 官方录用名单（第 55 项）](https://ec26.sigecom.org/program/accepted-papers/) · [完整作者版与版本记录](https://arxiv.org/abs/2509.25565)。

<a id="reading-order"></a>

## 建议阅读顺序

| 研究方向 | 建议阅读顺序 |
|---|---|
| 审稿匹配与评审机制 | #1 匹配框架 → #2 公平分配 → #4 科学文献表示 → #7 RATE → #9 LLM 评审反馈试验 |
| 自媒体内容推荐 | #10 探索机制 → #11 两阶段系统 → #14 多目标排序 → #19 多模态笔记 → #21 推理推荐 |
| 广告推荐 | #23 FTRL → #24 DeepFM → #25 DIN → #26 ESMM → #28 预算约束 → #30 LLM 蒸馏 |

经济机制补充阅读路径：

| 研究方向 | 建议阅读顺序 |
|---|---|
| 审稿市场 | #2 公平分配 → [#41 真实报告](#paper-41) → [#44 努力与准入](#paper-44) → [#45 审稿激励实验](#paper-45) |
| 内容与创作者生态 | #14 多目标排序 → [#54 多样性](#paper-54) → [#57 创作者努力](#paper-57) → [#58 质量—品类权衡](#paper-58) → [#66 Netflix 经济价值](#paper-66) |
| 推荐信息设计 | [#47 Bayesian Persuasion](#paper-47) → [#49 激励探索](#paper-49) → [#52 平台信息设计](#paper-52) → [#75 LLM 信息设计](#paper-75) |
| 广告与可微机制 | #25 DIN → [#67 GSP](#paper-67) → [#69 广告增量](#paper-69) → [#70 保留价实验](#paper-70) → [#73 深度拍卖](#paper-73) → [#74 LLM 拍卖](#paper-74) |

回到[项目文档索引](../INDEX.md)。
