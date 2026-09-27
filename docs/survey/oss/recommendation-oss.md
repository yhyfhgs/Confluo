---
title: 开源调研：推荐系统与学术推荐相关 GitHub 项目
status: draft
owner: opus5.5-survey
updated: 2026-09-26
---

# 开源调研：推荐系统与学术推荐相关 GitHub 项目

> 定位：为 v2 重设计中"算法部分 2：匹配与推荐"（打分反馈、点赞/收藏/评论、持续学习、双向匹配、刷卡式交互）提供开源基线。覆盖工业级开源推荐系统（X、字节、快手、Meta、NVIDIA、小红书场景）、小团队可用的推荐库与引擎、学术文献推荐与科学文献表示、审稿人匹配、双向/互惠推荐，并在第 3 节末给出 v2 推荐栈候选组合。
>
> 口径：所有 GitHub star/fork/license/活跃度为 **2026-09-26** 通过 `gh api` 读取的快照；论文、文档、模型卡事实均附 URL，访问日期均为 2026-09-26（另注者除外）。来源编号 `[Rxx]` 对应第 5 节参考来源。
>
> 与既有文档的关系：[`docs/research/github-similar-projects.md`](../../archive-v1.md#docs-research-github-similar-projects-md)（2026-07-20）调研的是"论文获取"类项目，arxiv-sanity-lite 仅从增量订阅角度出现；本文只讨论推荐/匹配算法与其工程形态，不重复获取层结论。

## 0. 结论速览

1. **X 已再次开源 For You 算法（核实为真）**：新仓库 `xai-org/x-algorithm`（Apache-2.0，33,426 star）于 2026-01-20 首次提交，2026-05-15、2026-08-13 两次大更新，此后近乎每个工作日同步一次，HEAD 为 2026-09-26 的 `4c5cfe8` [R5][R12]。相对 2023 年 `twitter/the-algorithm`（AGPL-3.0，排序前拉取约 6000 个特征 [R2]），2026 版用从 Grok-1 移植的 transformer（Phoenix）做多行为预测，首发 README 称"去除了全部人工特征与大部分启发式" [R6]（核验修正：该表述在 2026-08-13 提交 `47c1bcd` 的 README 中已删除，现行管线仍含 SimClusters 召回、作者衰减、站外折扣、新作者扶持等规则/启发式 [R5][R69]）；召回为 two-tower + 语义 ID（RQ 6 层×256 码）[R7]，重排有 DPP 多样性服务 [R10]，可见性过滤与排序分离并开源了打标系统 [R5]。在本文覆盖的工业开源中，它是许可宽松（Apache-2.0，与 HSTU、Monolith 同级）、组件最完整、且可单卡跑通的"推荐管线参考实现"，但目标函数是参与度，学术场景须替换目标。
2. **工业生成式推荐已开源，但不是 v2 的起点**：快手 OneRec 系（OpenOneRec 1.7B/8B 权重与训练管线 [R16]）、Meta HSTU（`meta-recsys/generative-recommenders` [R24]）、社区复现 MiniOneRec [R20] 的收益均以海量行为日志与 GPU 为前提（OneRec 承担快手/快手极速版 25% QPS [R18]；HSTU 面向十亿级用户平台 [R24]）。对 v2（1–1 万用户、百万级论文）应"预留数据形态、暂不采用"。
3. **最贴近 v2 规模与场景的公开配方是 Scholar Inbox**（平台闭源，论文与评分数据集公开）：GTE-large 向量经 PCA 降到 256 维 + 每用户逻辑回归（显式点踩 + 5k 随机负样本加权）+ 每次评分后重训 + "科学地图 + 主动学习"冷启动 + NGT 近邻索引；23k 注册用户（8k 月活）、300 万论文、80 万显式评分 [R46]；该系统论文已收录于 ACL 2025 System Demonstrations（2025.acl-demo.30，核验补充 [R63]）。这套配方几乎可以直接映射为 v2 "刷卡即主动学习"的极简方案。Semantic Scholar 自家 feed 也公开了同构配方（每用户 TF-IDF 与 SPECTER 两个线性 SVM，核验补充，见 2.7 [R62]）。
4. **小团队引擎现状**：在本文覆盖范围内，Gorse（Go，Apache-2.0，9,836 star，v0.5.11）是唯一"开箱即用且持续活跃"的通用推荐引擎（多源召回、BPR/eALS、FM 或 LLM 重排、Dashboard）[R30]；Metarank 由少数维护者小步维护（近 12 个月 57 次提交中 24 次为自动依赖升级）[R31]；LightFM 停更且 Python 3.12 无法安装（issue #709 未关闭）[R32]；implicit 活跃（cp39–cp314 wheel）[R33]；Vowpal Wabbit 2026 年恢复发版（9.11.x；9.11.4 起含 5 个模型加载/DSJSON 解析堆越界安全修复，pip 可得的首个修复版为 9.11.6）[R34][R67]，而其商业载体 Azure Personalizer 已于 2026-08-25 退役 [R35]。
5. **学术表示与匹配**：SPECTER2（Apache-2.0，按任务格式切换 proximity/adhoc_query/classification/regression adapter）与 SciNCL（MIT）是开源首选 [R48][R50]；openreview-expertise 中 SPECTER2+SciNCL（论文相似度层各 0.5 集成、按审稿人论文取 max）在其 README 对比表里最好 [R53]；但审稿匹配金标准研究显示最佳算法在易/难样本上仍误排 12–30% / 36–43% [R57]——内容相似度只能做召回与冷启动，排序必须靠用户反馈闭环。
6. **双向/互惠推荐**：开源实现稀少、多为论文附带代码（RECON 调和平均、CyberAgent 公平互惠 RecSys'24/'26）[R58]；最成熟的"双边容量约束匹配"开源是 `openreview-matcher`（min-cost flow、FairFlow、FairSequence、PerturbedMaximization）[R54]；X 2026-07 的"互关回复加权"（bidirectional follow reply boost）是工业界可审计的双向信号样例 [R11]。
7. **推荐栈**：S1 极简（SPECTER2/GTE + pgvector/Qdrant + 每用户 LR + 规则融合，纯 CPU）→ S2 中等（+ implicit 协同召回 + 多行为 LTR + bandit 探索 + DPP，或以 Gorse 引擎化）→ S3 进阶（HSTU/Phoenix 式序列多行为模型 + 语义 ID + 生成式检索，需 GPU）。建议 v2 以 S1 起步，同时在数据模型层为 S2/S3 预留曝光日志、行为序列与语义 ID 字段（见 3.2）。

---

## 1. 调研范围与方法

### 1.1 范围

- **纳入**：(a) 任务书点名的全部项目；(b) 与 v2 需求直接相关的补充项：Cornac、RecAI、NoteLLM（小红书笔记推荐场景）、PERSIA（快手）、HLLM（字节）、OneRec-Think / MiniOneRec（OneRec 衍生）、LLM 型 arXiv 日报类项目、bandit 与离策略评估库、与推荐强耦合的向量检索底座最小集合；(c) 双向/互惠推荐与审稿人匹配。
- **排除**：纯论文获取/爬取项目（见既有 github-similar-projects.md）；商业闭源推荐 SaaS 与初创公司（由初创调研负责）；抖音/小红书等社媒推荐的非开源部分（由社媒算法调研负责）；检索引擎/索引结构的深度对比（由检索/索引调研负责，本文仅列与推荐直接耦合的能力）。

### 1.2 核验口径

| 字段 | 口径 |
|---|---|
| Star / fork / license / archived | `gh api repos/{owner}/{repo}`，2026-09-26 读数。license 以 GitHub SPDX 识别为准；识别为 NOASSERTION/none 时读取仓库 LICENSE、setup.py 或 README 原文并注明 |
| 活跃度 | 默认分支最后提交日期；近 12 个月提交数（`commits?since=2025-09-26`，单页上限 100，记作"≥100"）；最新 release |
| 规模假设 | 取自 README/论文对硬件、数据量的陈述；本文自行推算的数字一律标"估算" |
| v2 可用性分级 | 针对 v2 初期（1–1 万用户、论文库百万级、Python 3.12 主栈、多用户凭证与全文私有隔离）：**A 直接采用**（可作依赖/组件）；**B 条件采用**（特定阶段、可选组件或仅离线评估）；**C 借鉴设计**（不引入代码，借鉴算法/架构）；**D 不建议**（停更/归档/许可冲突/规模严重不匹配） |

### 1.3 过程记录（可复现）

- **日期**：全部访问发生在 2026-09-26。
- **工具**：`gh api`（GitHub REST，只读）、`gh search repos` / `gh search issues`、WebFetch、Hugging Face Hub API（`hub_repo_details`、`hf_fs cat`）、PyPI JSON API（curl）、Semantic Scholar Recommendations API 的 swagger.json（curl，带可识别 UA）。
- **WebSearch 检索式**（会话共享配额在本 agent 第 3 次检索时耗尽，200/200，因此 2025–2026 事实改为直接核验一手来源；二手报道仅用于定位并标注）：
  1. `xai-org x-algorithm open source For You feed January 2026 Grok transformer Phoenix`
  2. `Semantic Scholar research feeds recommendation algorithm SPECTER embeddings linear classifier positive negative ratings blog`
  3. `"Scholar Inbox" ACL 2025 system demonstrations aclanthology`（未执行：配额耗尽）
- **gh search 检索式**：`OneRec`、`OpenOneRec`、`"scholar inbox"`、`"reciprocal recommender"`、`"reciprocal recommendation"`、`"arxiv recommendation"`、`"paper recommendation"`、`"arxiv daily personalized"`（0 结果）、`NoteLLM`、`"xiaohongshu recommendation"`、`KuaiRec`、`KuaiSAR`、`--owner allenai paper`；issue：`--repo lyst/lightfm "3.12"`。
- **逐文件阅读的源码/文档**（默认分支，2026-09-26）：x-algorithm 的 `README.md`、`phoenix/README.md`、`home-mixer/params/param.rs`、`home-mixer/scorers/author_cold_start.rs`、`xai-value-model/scoring.rs`、`xai-value-model/weights.rs`、`vm-ranker/dpp.rs`、`docs/BIDIRECTIONAL_BOOST_CHANGE.md`、首个提交 `aaa167b` 的 README、提交历史；the-algorithm 的 `README.md`、`home-mixer/README.md`、2025-09-03 提交 `c54bec0` 的统计；the-algorithm-ml 的 `projects/home/recap/README.md`；zotero-arxiv-daily 的 `src/zotero_arxiv_daily/reranker/base.py`；arxiv-sanity-lite 的 `serve.py`；m-ochi/recon 的 `recon.py`；openreview-matcher 的 `setup.py`；Monolith/VW/S2AND/daily-arXiv-ai-enhanced/Scholar Inbox 数据集的 LICENSE 原文；其余项目 README。
- **Hugging Face 模型卡**：allenai/specter2、allenai/specter2_base、allenai/specter、malteos/scincl、OpenOneRec/OneRec-8B、jinaai/jina-embeddings-v5-text-nano、thenlper/gte-large、Alibaba-NLP/gte-large-en-v1.5（许可、参数量、下载量）。
- **PyPI**：lightfm、implicit、vowpalwabbit、cornac、recbole、recommenders 的最新版本、wheel 覆盖的 CPython 版本与上传日期。
- **核验**：首轮与续核验的方法、接口与逐条结论见文末"核验记录"。
- **访问受限与替代**：blog.x.com 2023 工程博客返回 403（改用仓库 README 数据）；docs.vespa.ai 旧教程路径重定向（改读 `/en/learn/tutorials/news-5-recommendation`）；api.semanticscholar.org 文档页为 JS 渲染（改读 swagger.json）；docs.openalex.org 301 至 help.openalex.org（与本主题无关，未跟进）。

---

## 2. 主体内容

### 2.1 总览表 A：工业级与通用推荐系统

| 项目 | 仓库 | Star | License | 活跃度（最后提交；近 12 月提交；最新发版） | 算法要点 | 规模假设 | v2 |
|---|---|---|---|---|---|---|---|
| X 2023 推荐系统 | twitter/the-algorithm | 73,945 | AGPL-3.0 | 2025-09-03（"update for-you recommendations code"，+65,319/−3,195 行）；此前 2023-07 | 多候选源（Earlybird 搜索索引约占 50% 帖子、UTEG/GraphJet 图游走、CR-Mixer、FRS、SimClusters、TwHIN）→ 约 6000 特征 → light/heavy ranker → 启发式过滤 → 混排（home-mixer/product-mixer，Scala） | 依赖 Twitter 全套基础设施；无顶层 BUILD/WORKSPACE，不可独立构建 | C |
| X 2023 ML 模型 | twitter/the-algorithm-ml | 10,603 | AGPL-3.0 | 2023-04-05 | heavy ranker = 并行 MaskNet，10 个行为概率头 × 配置权重求和；TwHIN 图嵌入（TorchRec） | Linux + NVIDIA GPU；只提供随机合成数据 | C |
| X 2026 For You 算法 | xai-org/x-algorithm | 33,426 | Apache-2.0 | 2026-09-26；首发 2026-01-20，05-15 与 08-13 大更新，08 月后近乎日更；无 release | Thunder（内存 in-network）+ Phoenix 检索（two-tower，语义 ID）+ SimClusters；Phoenix 排序 transformer 多行为预测 + candidate isolation；Σw·P(a) + 负分偏移 + 作者衰减 + OON 折扣 + 新作者扶持；VMRanker DPP；可见性过滤独立 | 生产为 xAI 集群；`phoenix/` 提供单 GPU nano 配置与合成数据，可端到端训练与 gRPC 服务 | C（模式）；B（S3 离线实验） |
| 字节 Monolith | bytedance/monolith | 9,287 | Apache-2.0（LICENSE 原文；GitHub 识别为 Other） | 已归档；最后提交 2023-11-08 | 无冲突嵌入表（可过期嵌入、频次过滤）+ 容错在线实时训练（TensorFlow 之上） | 分布式异步训练 + 实时流；Bazel 3.1、仅 Linux 编译 | D（C：实时训练思想） |
| 字节 HLLM | bytedance/HLLM | 626 | Apache-2.0 | 已归档（pushed 2025-08-26） | 分层 LLM：Item LLM 编码物品文本，User LLM 建模行为序列（arXiv 2409.12740） | LLM 级 GPU 训练 | D |
| 快手 OpenOneRec | Kuaishou-OneRec/OpenOneRec | 935 | README 声明 Apache-2.0（GitHub 未识别 LICENSE 文件）；HF 权重卡 Apache-2.0 | 2026-05-18；仓库创建 2025-12-29 | Qwen3 骨干 + itemic tokens（层次向量量化）；联合预训练 → 多任务 SFT → on-policy 蒸馏 → RL；RecIF-Bench | 1.7B/8B 模型，多 GPU（FSDP/VeRL） | C |
| OneRec-Think | wangshy31/OneRec-Think | 281 | Apache-2.0 | 2025-10-26 | itemic 对齐 + 推理激活（CoT SFT）+ 推荐奖励 RL；README 称线上 App 停留时长 +0.159% | LLM 级 GPU | C |
| MiniOneRec（社区复现） | AkaliKong/MiniOneRec | 1,845 | Apache-2.0 | 2026-09-07 | SID 构建（RQ-VAE、RQ-Kmeans、constrained RQ-Kmeans、RQ-Kmeans+）→ SFT → GRPO 推荐 RL；Qwen 0.5B–7B | 多 GPU 为宜；Amazon Review 数据 | B（S3 实验） |
| PERSIA（快手 + ETH） | PersiaML/PERSIA | 411 | MIT | README 声明"因公司重组不再维护" | 基于 PyTorch 的异构混合加速并行训练（README：可在普通硬件上训练最多 100 万亿参数的推荐模型，曾服务亿级 DAU 业务） | GPU 集群 | D |
| Meta generative-recommenders（HSTU） | meta-recsys/generative-recommenders | 1,996 | Apache-2.0 | 2026-09-25；≥100；无 release | 生成式推荐：HSTU 序列转导 + M-FALCON 推理；DLRM-v3 基准；Triton/CUDA 核（基于 FlashAttention V3） | 公开实验单卡 ≥24GB HBM；DLRM-v3 示例 4 GPU | B（S3） |
| TorchRec | meta-pytorch/torchrec | 2,607 | BSD-3-Clause | 2026-09-26；≥100；v1.9.0-rc1（2026-09-11） | 嵌入表分片（table/row/column-wise 等）、自动分片规划、FBGEMM 核、流水线训练 | 多 GPU/多机 | D（v2 规模不需要） |
| NVIDIA Merlin | NVIDIA-Merlin/Merlin（及 NVTabular 1,151 star、HugeCTR 1,073 star、Transformers4Rec 1,281 star、models 304 star） | 908 | Apache-2.0 | meta 仓库 2024-07 后仅 2026-07 一次合规提交；v24.06.00（2024-06-14）；HugeCTR v26.03.00（2026-03-12）；Transformers4Rec v23.12.00（2024-01-11） | GPU ETL、超显存嵌入表训练、会话推荐 | TB 级数据、NVIDIA GPU | D |
| Microsoft Recommenders | recommenders-team/recommenders | 21,921 | MIT | 2026-08-17；≥100；1.2.1（2024-12-24） | 算法与评估工具合集：ALS、BPR（Cornac）、SAR、LightGCN、SASRec、NRMS/NAML 新闻推荐、TF-IDF 内容推荐（示例笔记本 `tfidf_covid.ipynb`）、VW、LightGBM 等；LF AI & Data 项目 | 单机 CPU/GPU/Spark | B（评估与参考实现） |
| RecBole | RUCAIBox/RecBole | 4,569 | MIT | 2025-02-24；0；v1.2.1（2025-02-23） | 94 个算法、44 个数据集的统一实验框架 | 研究用单机 GPU | B（离线基准；已停更） |
| Cornac | PreferredAI/cornac | 1,056 | Apache-2.0 | 2026-09-14；47；v3.0.1（2026-09-14，cp310–cp314 wheel） | 多模态推荐比较框架：CTR/CDL/ConvMF 等文本模型、citeulike 数据集、TIGER/RPG 语义 ID、ANN（Annoy/FAISS/hnswlib/ScaNN）、Flask serving 与 Cornac-AB | 单机 CPU/GPU | B（原型与离线） |
| Gorse | gorse-io/gorse | 9,836 | Apache-2.0 | 2026-09-22；≥100；v0.5.11（2026-07-14） | 多源召回（latest/popular、item-to-item〔embedding/标签〕、user-to-user、MF〔BPR/eALS〕、外部）+ 排序（FM 或 LLM 重排）+ Dashboard + REST | 单节点训练、分布式预测；存储 MySQL/Postgres/MongoDB/ClickHouse，缓存 Redis 等 | B（S2 引擎化选项） |
| Metarank | metarank/metarank | 2,444 | Apache-2.0 | 2026-09-25；57（24 次为 Scala Steward 自动依赖升级，33 次人工提交，主要来自 2 名维护者）；0.8.1（2026-09-07） | 事件流特征工程 + LambdaMART 二次重排；trending、similar-items（MF ALS）；bi/cross-encoder 语义特征；多模型 A/B | JVM 服务 + Redis 状态；README 称大结果集重排 10–20ms | B/C |
| LightFM | lyst/lightfm | 5,112 | Apache-2.0 | 2023-04-30；0；1.17（2023-03-20，仅 sdist） | 混合 MF：用户/物品 = 其特征嵌入之和，BPR/WARP 损失，缓解冷启动 | 单机 CPU | D（Py3.12 安装失败 issue #709 未关闭）；C（混合思想） |
| implicit | benfred/implicit | 3,824 | MIT | 2026-05-08；18；v0.7.3（2026-05-08，cp39–cp314 wheel） | 隐式反馈 ALS、BPR、LMF、item-item（cosine/TF-IDF/BM25）；ALS/BPR 有 CUDA 核；可接 ANN | 单机 CPU（可选 GPU） | A（S2 协同召回） |
| Vowpal Wabbit | VowpalWabbit/vowpal_wabbit | 8,721 | BSD-3-Clause（LICENSE 原文；GitHub 识别为 Other） | 2026-09-24；≥100；9.11.6（2026-09-23） | 在线学习 + 上下文 bandit：`--cb`、`--cb_explore`、`--cb_explore_adf`；探索 `--first/--epsilon/--bag/--cover/--softmax`；评估 ips/dr/dm/mtr | 单机 CPU 在线学习 | B（S2 探索槽） |
| Vespa 推荐样例 | vespa-engine/sample-apps（引擎 vespa-engine/vespa 7,110 star） | 412 | Apache-2.0 | 2026-09-22；≥100 | news 教程：MIND 数据、用户/新闻向量 + `nearestNeighbor`（HNSW）+ 遍历中过滤；album-recommendation；commerce-product-ranking；vector-streaming-search（按用户分组的个人数据检索） | 分布式引擎；Docker ≥4GB 起步 | C（若检索层选 Vespa 则 B） |
| RecAI（微软） | microsoft/RecAI | 1,198 | MIT | 2026-01-27 | LLM4Rec 工具集：推荐 Agent（InteRecAgent）、知识插件、RecLM-emb/gen、RecExplainer、评估器 | LLM 调用或微调成本 | C |
| NoteLLM / NoteLLM-2（小红书笔记场景） | Applied-Machine-Learning-Lab/NoteLLM | 156 | Apache-2.0 | 2025-04-17 | 把"生成话题标签/类目"与"笔记 embedding"合并为一个任务训练 I2I 表示；NoteLLM-2 加入多模态（mICL、late fusion） | LLM 微调（DeepSpeed） | C |

补充（同类/底座，均为 2026-09-26 读数）：

| 类别 | 项目（Star／License／最后提交） | 备注 |
|---|---|---|
| bandit / 离策略评估 | david-cortes/contextualbandits（840／BSD-2-Clause／2026-06-28）；st-tech/zr-obp（Open Bandit Pipeline，710／Apache-2.0／2022-11）；fidelity/mabwiser（293／Apache-2.0／2024-08）；microsoft/learning-loop（12／MIT／2024-11） | learning-loop 是微软对 Personalizer 退役给出的迁移目标 [R35]；OBP 停更但 OPE 估计器可参考 |
| 其他推荐库 | tensorflow/recommenders（2,033／Apache-2.0／2026-07-08，近 12 月 12 次提交）；NicolasHug/Surprise（6,818／BSD-3／2026-05-30）；pmixer/SASRec.pytorch（614／Apache-2.0／2026-09-17）；reczoo/FuxiCTR（1,481／Apache-2.0／2026-09-14）；alibaba/EasyRec（2,361／Apache-2.0／pushed 2026-04-15）；massquantity/LibRecommender（490／MIT／2025-07-17，近 12 月 0 次） | SASRec 可作 S2/S3 的序列基线 |
| 前车之鉴 | apache/predictionio（12,517／已归档／2021-01）；twitter/GraphJet（740／Apache-2.0／2023-04） | 推荐服务器项目可能整体退役，选型需有退出路径 |
| 向量检索底座（与推荐耦合的最小集） | facebookresearch/faiss（40,985／MIT）；nmslib/hnswlib（5,334／Apache-2.0）；NGT-labs/NGT（1,374／Apache-2.0，原 yahoojapan/NGT，Scholar Inbox 在用）；unum-cloud/USearch（4,320／Apache-2.0）；pgvector/pgvector（23,161／PostgreSQL License，tag v0.8.6）；qdrant/qdrant（34,834／Apache-2.0）；asg017/sqlite-vec（8,137／Apache-2.0，v0.1.9 于 2026-03-31）；lightgbm-org/LightGBM（18,814／MIT，原 microsoft/LightGBM） | 深度对比留给检索/索引调研；sqlite-vec（核验修正）：稳定版 v0.1.9 无 ANN 索引（暴力 KNN），ANN 索引（rescore、DiskANN；IVF 为实验性且未启用）仅见于 v0.1.10-alpha 预发布（alpha.1 于 2026-03-31，最新 alpha.4 于 2026-05-18）[R68] |
| 核验补充：离线评估 / 在线学习 | lenskit/lkpy（LensKit，314／MIT〔PyPI license_expression；GitHub 识别为 Other〕／2026-09-23，v2026.3.0 于 2026-08-06，要求 Python ≥3.12.5）；online-ml/river（6,109／BSD-3-Clause／2026-09-26，0.26.1 于 2026-08-21，cp311–cp315 wheel） | LensKit 是与 v2 Python 3.12 主栈直接兼容的离线评估框架；River 提供纯 Python 在线学习：`linear_model`（在线 LR）、`bandit`（EpsilonGreedy/UCB/BayesUCB/Thompson/LinUCB/Exp3）、`reco`（Baseline/BiasedMF/FunkMF），可作 S1/S2"逐次滑动更新 + 探索槽"的无 VW 备选 [R65] |
| 核验补充：可订阅/可选择的 feed 算法 | bluesky-social/feed-generator（2,067／MIT／2026-09-25） | Bluesky"自定义 feed"：第三方服务只返回帖子 URI 骨架（`app.bsky.feed.getFeedSkeleton`），由用户侧服务器 hydrate 后下发；用户可订阅多个算法 feed。对应 v2"用户自定义检索/订阅即 feed"与"骨架—水合分离"（与 X 的 Source/Hydrator 分离一致）[R65] |
| 核验补充：刷卡式论文 feed 的开源实现 | `gh search repos`："paper tinder"、"arxiv swipe"、"arxiv tiktok"、"wikitok"（2026-09-26） | 论文刷卡类仓库均为 ≤1 star 的个人项目；IsaacGemal/wikitok（1,324／MIT／2025-03-18）为 TikTok 式维基百科**随机**文章流，纯前端、无个性化——刷卡交互没有可复用的开源推荐后端，需自建 [R65] |
| 核验补充：语义 ID 生成式推荐框架 | snap-research/GRID（745／**仅限非商业研究**的 Snap 自定义许可〔LICENSE 原文；GitHub 识别为 Other〕／2025-10-15） | Snap Research 出品，配套论文为 arXiv 2507.22224《Generative Recommendation with Semantic IDs: A Practitioner's Handbook》。流程分三步：LLM 生成物品 embedding，用 RQ-KMeans/RQ-VAE/RVQ 学习层次语义 ID，再由 transformer 生成 SID 序列。可作为 S3 语义 ID 方案的对照阅读，但许可禁止商用，v2 不得引入代码 [R70] |
| 核验补充：区分"自然 / 推荐驱动"的反馈数据集 | Yandex Yambda-5B（HF `yandex/yambda`，Apache-2.0，2025-05-27 上架；论文 arXiv 2505.22238） | 共 47.9 亿次交互（100 万用户、939 万曲目）。显式反馈包含 like、dislike 及其撤销事件 unlike、undislike；每条事件带 `is_organic` 标记，区分自然行为与推荐驱动行为。这正对应 v2"只认已曝光反馈 + 来源字段 + 可撤销操作"的事件建模，可用于离线评估。领域为音乐，结论迁移到学术场景需谨慎 [R72] |

### 2.2 X / Twitter：2023 与 2026 两次开源（深读）

#### 2.2.1 2023：twitter/the-algorithm 与 the-algorithm-ml

- **构成**：README 将组件分为数据（tweetypie、unified-user-actions、user-signal-service）、模型（SimClusters 社区检测稀疏嵌入、TwHIN 稠密知识图嵌入、real-graph 用户交互预测、tweepcred PageRank 声誉）、框架（navi Rust 模型服务、product-mixer 信息流框架、timelines 聚合特征框架、twml TF1 旧框架）[R1]。For You 的候选源中 search-index（Earlybird）"约 50% 帖子来自此源" [R1]；home-mixer 在排序前"拉取排序所需的约 6000 个特征"，之后有作者多样性、in/out-network 内容平衡、反馈疲劳、去重、可见性过滤等启发式 [R2]。
- **heavy ranker**：并行 MaskNet，输出 10 个行为概率并按配置权重加权求和；README 公布的 2023-04-05 权重为 fav 0.5、retweet 1.0、reply 13.5、good_profile_click 12.0、video_playback50 0.005、reply_engaged_by_author 75.0、good_click 11.0、good_click_v2 10.0、negative_feedback_v2 −74.0、report −369.0；权重"最初设定为每个加权概率对总分贡献近似相等，之后按平台指标周期性调整"；因隐私不公开训练数据，只给随机数据生成脚本 [R4]。
- **状态**：the-algorithm-ml 默认分支最后提交 2023-04-05 [R4]。the-algorithm 在 2025-09-03 有一次大提交"update for-you recommendations code"（stats：+65,319/−3,195 行；API 单次最多返回 300 个文件，实际变更 ≥300 个文件）[R3]，此后未再更新。
- **许可证含义**：两仓库均为 AGPL-3.0。v2 是多用户网络服务，把 AGPL 代码并入服务端会触发对外公开源码义务——只宜借鉴设计。

#### 2.2.2 2026：xai-org/x-algorithm（真实存在，内容已逐文件核验）

**发布时间线**

| 日期（UTC） | 事件 | 来源 |
|---|---|---|
| 2026-01-19 23:12 | 仓库创建 | `gh api` created_at [R5] |
| 2026-01-20 | 首个提交 `aaa167b`：Home Mixer、Thunder、Phoenix（从 Grok-1 开源版移植的 transformer 样例）、Candidate Pipeline；README 原文称 "We have eliminated every single hand-engineered feature and most heuristics from the system" | 该提交的 README [R6] |
| 2026-05-15 | 两次同步提交（`e414c17` +18,263/−926 行、187 个文件；`0bfc279` 仅改 phoenix 1 个文件）。核验修正（原为"二手报道、⚠ 未逐文件核验"，现按提交文件清单确认）：新增 `.gitattributes` 以 Git LFS 分发 `*.npz`/`*.zip`；`phoenix/run_pipeline.py` 端到端推理与 `phoenix/artifacts/oss-phoenix-artifacts.zip`（README 称 mini Phoenix 为 128 维、4 层 transformer 的冻结 checkpoint）；`home-mixer/ads/*`、`ads_source.rs`、`blender_selector.rs` 广告混排；另新增 `grox/` 内容分类器 59 个文件 | 提交 `e414c17` [R69]；二手 [R13] 仅作定位 |
| 2026-08-13 | 公开关键配置参数（含行为权重）、可见性过滤与打标系统（botmaker、scarecrow、agatha、bdsm、user-cred-v2、media-model-proxy、clip、abuse-enforcement-service）、用生产训练代码替换 Phoenix 演示模型并附合成数据生成、新增 SimClusters 候选源；配套 "Under the Hood" 标签透明度工具 | README "Notable Updates" [R5] |
| 2026-08-14 | 补充"权重乘的是预测概率而非计数"的说明；巴西 2026 选举过滤器 `Brazil2026ElectionFilter` | README [R5] |
| 2026-08-17 起 | 几乎每个工作日一次 "Open-source X Recommendation Algorithm" 同步提交 | 提交历史 [R12] |
| 2026-09-03 | 外部贡献者 PR #88（in_network_ids 在可见性查询前去重）被合并——截至 2026-09-26 全部 37 个提交中唯一一次 PR 合并 | 提交历史 [R12] |
| 2026-09-18 | Under the Hood 报告增加"因法律合规被限制可见性"的信息 | README [R5] |

仓库语言（字节数）以 Rust、Python 为主，另有 Scala、Java、C++、CUDA 等 [R5]。README 表示其目标是让"占流量显著比例（如 10% 及以上）的实验"在仓库中可见，并用定时脚本把代码中的默认参数同步为生产主值 [R5]。未公开部分：Grox 的 LLM prompt（j2 文件）、部分 botmaker 规则，以及部署基础设施 [R5]。

**请求路径（Post Pipeline + Blending Pipeline）** [R5]：

1. Query hydration：用户近期行为序列（模型主输入）、关注列表、屏蔽/静音、静音词、已看/已推、关注话题等。
2. Candidate sources（并行）：Thunder（关注账号的近期帖子，常驻内存）；Phoenix retrieval（向量近邻）；SimClusters（按"谁与什么互动"聚类找候选）。
3. Candidate hydration：正文与媒体、作者信息与账号标签、引用帖、语言、互动计数、订阅状态等。
4. Pre-scoring filters（17 个，按序）：跨源去重、核心数据加载失败、**超过 48 小时**、自己的帖子、站外转推/回复、站外成人内容作者、重复转推、无权访问的订阅帖、**已看（两路记录）/本会话已推**、静音词、屏蔽/静音作者、视频开关、话题包含/排除、新用户站外最低互动门槛、确定性留存（`InventoryHoldoutFilter`）。
5. Scoring：`PhoenixScorer`（逐行为概率）→ `RankingScorer`（加权和，再做同作者衰减、站外折扣、新作者扶持）→ `VMRanker`（调用独立的 vm-ranker 服务做 DPP 重排）。
6. Selection：按最终分取 Top-K。
7. Post-selection filters：`VFFilter`（可见性服务判定 drop）、`AncillaryVFFilter`（父帖/引用帖被 drop 则连带）、`DedupConversationFilter`；之后 Blending 插入广告、Who-to-Follow、提示，Side effects 记录已推、刷新缓存、写日志。

**Phoenix 模型** [R7]：

- 检索为 two-tower：用户塔是对"行为历史 + 一个用户特征 token（国家、语言等粗粒度画像）"的 transformer，**生产检索不使用逐用户 ID 嵌入**（`use_user_embedding=False`）；候选塔用**语义 ID**（由多模态 embedding 残差量化得到，6 层 × 256 码）加哈希作者 ID 表示帖子，同主题帖子共享 SID 前缀以泛化到新帖；每次存 checkpoint 时把候选索引写进 checkpoint，服务端直接加载；点积 Top-K。
- 排序为 transformer，**candidate isolation**：推理时候选之间不能互相 attention，只能看用户上下文，使每条候选的分数与同批其他候选无关、可缓存。
- 哈希嵌入（多哈希函数，无词表，新帖可立即表示）；JAX 训练 + Rust gRPC 服务；提供单 GPU 的 nano 预设（排序 `home_direct_packed_nano`、检索 `xrecsys_two_tower_nano`），训练"数分钟级"；提供确定性合成数据生成器（`reference/world_snapshots.py`、`reference/dump_gen.py`、`reference/train_synth.py`），无需下载任何数据或 checkpoint。披露的一处替换：旧 dense 优化器配置导出为 AdamW，旗舰排序配置与 nano 使用生产的 Muon 配方。
- 预测的行为：Engagement（favorite、reply、repost、quote、share、share via DM、share via copy link）、Clicks（post、profile、link、photo expand、video open、quoted post）、Attention（video quality view、dwell、dwell time、click dwell time、active seconds）、Author（follow author）、Negative（not interested、mute author、block author、report、not dwelled）[R5]。

**打分公式与 2026-09-26 生产默认权重**（`home-mixer/params/param.rs` @ `4c5cfe8` [R8]；公式 `Final Score = Σ weight_i × P(action_i)` [R5]）：

| 行为 | 权重 | 行为 | 权重 |
|---|---|---|---|
| Favorite | 0.5 | Share | 2.0 |
| Reply | 5.0 | ShareViaDm | 5.0 |
| BidirectionalFollowReplyWeightBoost（互关作者回复加权） | 15.0 | ShareViaCopyLink | 20.0 |
| BidirectionalFollowDwellWeightBoost | 0.0 | Dwell | 0.05 |
| Retweet | 1.0 | ContDwellTime | 0.004 |
| Quote | 5.0 | FollowAuthor | 4.0 |
| Click | 0.4 | PostUnexplored | 0.02 |
| OpenLink | 0.2 | NotInterested | −43.2 |
| PhotoExpand / VideoOpen | 0.05 / 0.07 | MuteAuthor | −58.8 |
| ProfileClick / VQV | 0.0 / 0.0 | BlockAuthor | −31.2 |
| QuotedClick | 0.05 | Report | −234.0 |
| NotDwelled | −0.02 | 冷启动：ColdStartImpressionThreshold / SlotMin / SlotMax | 1000 / 15 / 16 |

- 代码注释解释：权重乘的是**该用户自己的预测概率**（或连续值），不是原始计数，"一个举报抵消 468 个赞"的解读是错误的；举报基率比点赞低 1000 倍以上，所以需要大权重才能影响排序 [R8][R9]。
- **负分偏移**：`offset_score` 把加权和 <0 的候选按 `(score + negative_sum) / total_sum × OFFSET` 压缩到 `[0, OFFSET)`，≥0 的整体加 `OFFSET`（`NEGATIVE_SCORES_OFFSET = 0.001`，`negative_sum` 为负向权重绝对值之和），净负分候选必然排在所有非负候选之后 [R9]。
- **融合后乘子**：最终分再乘 `author_diversity × oon`；作者衰减 `diversity_multiplier = (1 − floor) × decay^k + floor`，k 由排序中同作者已出现次数得到（`author_pool_counts`）[R9]。
- **DPP 重排**（`vm-ranker/dpp.rs` [R10]）：质量 `q_i = exp(α · score_i / max_score)`，`α = θ / (2(1−θ))`；核 `L_ij = q_i · cos(e_i, e_j) · q_j`（embedding 余弦相似度）；增量 Cholesky 贪心 MAP 选择 Top-K，可带"种子"抑制近重复；单测默认 `θ = 0.5`。
- **新作者冷启动**（README 的 New-Author Boost + `home-mixer/scorers/author_cold_start.rs` + param.rs 默认值 [R5][R8]）：README 表述为"作者曝光低于阈值"，但核验代码（`apply_cold_start`）发现阈值实际作用于**候选帖自身的首页曝光** `view_count_on_home < ColdStartImpressionThreshold（1000）`；其余条件为非回复/非转推、作者粉丝不超过 `ColdStartFollowerCap = 1000`、帖龄不超过 `ColdStartMaxPostAgeSecs = 172800`（48 小时）、当前名次低于 `LowImpressionsMaxPositionRatio（0.85）× 非零分候选数`，并受作者/观看者实验分桶约束；每次请求**至多提升 1 条**，把其分数抬到目标名次的分数，目标名次在 `[ColdStartSlotMin, ColdStartSlotMax) = [15, 16)` 中随机抽取（0 起算，即第 16 位）；代码另有 Beta 先验（α0 = 0.75、β0 = 49.25，先验均值 1.5%）的 Thompson sampling 分支（`EnableColdStartThompsonSampling` 默认 `false`，`ColdStartTsTopK = 2`）。这是"供给侧冷启动 = 小流量 bandit 探索"的工业实现样例。
- **防刷口径**（param.rs 注释 [R8]）：只有发生在"首页时间线中被下发的帖子"上的行为才计入推荐系统，直接跳转访问（如群聊协同）无排序影响；预测是个性化的，恶意批量举报主要影响与恶意者相似用户的推荐。

**"双向"样例：bidirectional follow boost**（`docs/BIDIRECTIONAL_BOOST_CHANGE.md` [R11]）：2026-07-10 起 A/B，小比例用户随机分到互关回复加权 5/10/15/20（多数为 0）；2026-07-13 对大量用户上线 20；2026-07-24 根据实验结果与用户反馈（如世界杯期间站外讨论可见度不足）调为 15。实现为一个 hydrator（查询候选作者是否回关，写入 `is_mutual_follow_author`）加一个权重参数；同期测试的"互关 dwell 加权"未上线（参数 0.0）。

**2023 与 2026 对照**

| 维度 | 2023 twitter/the-algorithm(-ml) | 2026 xai-org/x-algorithm |
|---|---|---|
| License | AGPL-3.0 | Apache-2.0 |
| 语言 | Scala/Java 为主，TF1（twml），Rust（navi） | Rust + Python(JAX)，另含 Scala/Java（SimClusters 等） |
| 特征 | 排序前拉取约 6000 个特征 [R2] | 首发即声明去除全部人工特征，由 transformer 从行为序列学习 [R6]；核验修正：2026-08-13 起 README 不再含此表述，Phoenix 仍使用用户特征 token（国家、语言等）与语义 ID 等输入 [R7][R69] |
| 召回 | search-index（约 50%）、UTEG/GraphJet、CR-Mixer、FRS、SimClusters/TwHIN | Thunder（in-network 内存）、Phoenix two-tower（语义 ID）、SimClusters（2026-08 加入） |
| 排序 | light ranker + heavy ranker（并行 MaskNet，10 头） | Phoenix transformer（README 列出 24 类行为，含停留时长等连续值；输出逐候选×逐行为 logits 加 dwell 回归；candidate isolation） |
| 融合 | Σw·P（reply_engaged_by_author 75、report −369，2023-04-05） | Σw·P（share via copy link 20、report −234，2026-09-26）+ 负分偏移 + 作者衰减 + 站外折扣 + 新作者扶持 |
| 多样性 | 作者多样性、内容平衡、反馈疲劳等启发式 | 作者衰减 + 独立 DPP 重排服务 |
| 可见性 | visibilitylib | visibility-filtering + 打标系统开源 + Under the Hood 透明度 |
| 可运行性 | 无顶层构建文件；ML 仓库仅随机数据 | phoenix 附 Cargo/pyproject/QUICKSTART 与合成数据，可单卡端到端训练与服务 |
| 更新节奏 | 2023 后仅 2025-09-03 一次大更新 | 首发后两次大更新，2026-08 起近乎日更 |

### 2.3 其他工业开源：字节、快手、Meta、NVIDIA、小红书场景

**字节跳动**

- **Monolith**（论文 arXiv 2209.07663，v1 2022-09-16）：无冲突嵌入表 + "可过期嵌入与频次过滤"降内存；训练与服务不再分离的在线训练架构，并论证"可以用系统可靠性换实时学习"；已落地 BytePlus Recommend [R14]。仓库已归档，最后提交 2023-11-08，需 Bazel 3.1.0、仅 Linux [R14]。本次核验的 3 个字节仓库——monolith、HLLM 与机器学习分布式训练调度框架 primus——均已归档 [R14][R15]。
- **对 v2**：可借鉴"近实时更新"思想（每次反馈后更新用户侧模型），但 v2 的轻量线性模型天然支持，无需 Monolith 式基础设施。

**快手 OneRec 系**

| 条目 | 核验事实 | 来源 |
|---|---|---|
| OneRec（arXiv 2502.18965，2025-02-26） | encoder-decoder 编码用户行为序列、逐步解码视频；稀疏 MoE 扩容；session-wise 生成取代逐点预测；Iterative Preference Alignment + DPO + 奖励模型；快手主场景观看时长 +1.6% | [R17] |
| OneRec Technical Report（arXiv 2506.13695，2025-06-16） | 端到端生成式替代级联；计算 FLOPs 提升 10×；训练/推理 MFU 23.7%/28.8%；OPEX 仅为传统管线 10.6%；承担快手/快手极速版 25% QPS；App 停留时长 +0.54%/+1.24% | [R18] |
| OpenOneRec（arXiv 2512.24762，v1 2025-12-31；仓库创建 2025-12-29） | RecIF-Bench：短视频/广告/电商三域、8 个任务 4 层能力；数据规模两处口径不一（核验修正）——仓库 README 称"来自 20 万用户的 1 亿交互"，技术报告摘要（arXiv v2）称公开训练集为"来自 16 万用户的 9600 万交互"；OneRec-Foundation 1.7B/8B（Qwen3 骨干；Standard 约 33B tokens，Pro 约 130B tokens，含快手工业语料）；README 称"代码与详细用法即将发布"，但仓库已含 `pretrain/`、`verl_distillation/`、`verl_rl/`、`tokenizer/`、`benchmarks/`；路线图含一键复现与 Docker 镜像；账号类型为 GitHub User 而非 Organization，README 引用的技术报告作者为快手 OneRec 团队 | [R16] |
| OneRec-8B 权重 | HF：8.39B 参数，Apache-2.0，累计下载约 9.1K（近 30 天 623） | [R16] |
| Kuaishou-OneRec/KSA | "Kwai Summary Attention"，60 star，Apache-2.0，2026-08-31 | [R21] |
| KuaiRec 数据集 | chongminggao/KuaiRec，"全观测"推荐数据集，242 star，CC-BY-SA-4.0 | [R23] |

**Meta**

- **HSTU / Generative Recommenders**（arXiv 2402.17152，ICML'24）：1.5 万亿参数；合成与公开数据集 NDCG 最高 +65.8%；8192 长度序列上比 FlashAttention2 transformer 快 5.3×–15.2×；线上 A/B +12.4%；部署于"数十亿用户的大型互联网平台"多个场景；质量随训练算力呈幂律扩展，跨三个数量级直至 GPT-3/LLaMA-2 规模 [R24]。
- 仓库公开实验（ML-1M/ML-20M/Amazon Books）：ML-1M 上 HSTU-large HR@10 0.3294，对比 SASRec（sampled softmax 版）0.2853（+15.5%）；需单卡 ≥24GB HBM，测试环境 Ubuntu 22.04 / CUDA 12.4 / Python 3.10 [R24]。
- **TorchRec**：嵌入表分片、自动规划、FBGEMM 核、流水线训练；README 列出 the-algorithm-ml 也基于 TorchRec [R25]。v2 的用户/论文 ID 规模（≤1 万用户、百万论文）单卡可容纳，不需要分片训练。

**NVIDIA Merlin**：面向 TB 级数据与超显存嵌入表；meta 仓库最新 release v24.06.00（2024-06-14），2024-07 后仅有一次合规类提交 [R26]。对 v2 规模不适用。

**小红书场景 NoteLLM**：把"为笔记生成话题标签/类目"与"压缩笔记信息为 embedding"视为同一任务联合训练，提升 I2I 召回表示；NoteLLM-2 端到端多模态微调并用 mICL 与 late fusion 缓解"视觉忽视" [R38]。对学术场景的启示：可让表示模型同时学习"生成领域/方法标签"，使 embedding 与可读标签一致（用于卡片标签与解释）。本次检索（`NoteLLM`、`"xiaohongshu recommendation"`）未发现小红书或抖音线上推荐系统本身的开源实现。

### 2.4 小团队可用的库与引擎（深读）

**Gorse**（Go）[R30]

- 功能：多源召回（latest、user-to-user、item-to-item、协同过滤等）、多模态内容经 embedding 接入、经典与 LLM 推荐器、GUI Dashboard（管线编辑、监控、数据管理）、REST API；Docker playground 一条命令起一个 GitHub 仓库推荐演示。
- 架构：master（训练、非个性化推荐、配置与成员管理）+ worker（离线逐用户推荐）+ server（REST 与在线实时推荐）；数据存 MySQL/MariaDB、MongoDB、Postgres 或 ClickHouse，中间结果缓存于 Redis、MySQL、MongoDB 或 Postgres；"单节点训练、分布式预测"。
- 算法：MF 两种训练法 BPR 与 eALS（`[recommend.collaborative] type = "mf"`），按 `optimize_period`（默认 180m）与 `optimize_trials`（默认 10）做超参搜索；排序可选 FM（`type = "fm"`，使用负反馈）、LLM 重排（`type = "llm"`，配置 `reranker_api` 与 query/document 模板，`recommend.context_size` 控制带入的历史反馈条数）或不排序。
- v2 评价：最接近"拿来即用"的中等方案；代价是引入 Go 服务与第二份数据副本（users/items/feedback 需同步），私有数据隔离要求只推送共享元数据与反馈；需评估其多用户"私有反馈不外泄"的保证（⚠ 未核验）。

**Metarank**（Scala）[R31]：事件流驱动的特征工程（CTR、会话画像、时间等"数十种典型排序信号"）+ LambdaMART 二次重排，trending 与 similar-items（MF ALS）推荐，bi/cross-encoder 语义特征，多模型 A/B；状态放 Redis，可水平扩展。近 12 个月 57 次提交：24 次为 Scala Steward 自动依赖升级，其余为人工提交（Roman Grebennikov 24 次、Michael Schmid 7 次、其他 2 次），最新 0.8.1 于 2026-09-07 发布；商业公司运营状态 ⚠ 未核验。适合作为"学习排序服务"的设计参照。

**implicit / LightFM**：implicit 提供 ALS（Hu et al. 隐式反馈加权最小二乘，含共轭梯度版）、BPR、Logistic MF 与 item-item 近邻，多线程 + CUDA 核，PyPI 有 cp39–cp314 wheel [R33][R60]，可直接用于 S2 的协同召回。LightFM 的混合模型（物品 = 特征嵌入之和）对冷启动论文很合适，但 PyPI 仅有 2023 年 sdist，issue #709"Can't install on Python 3.12"自 2024-05-17 未关闭 [R32][R60]——与 v2 的 Python ≥3.12 冲突；其思想可用"内容向量 + 线性/FM"自行实现。

**Vowpal Wabbit 与 bandit 生态**：VW 支持 `--cb`（离线已收集数据学习）、`--cb_explore`（固定动作集）、`--cb_explore_adf`（动作集变化、动作带丰富特征——正对应"候选论文集每天变化"），探索算法 `--first/--epsilon/--bag/--cover/--softmax`（softmax 仅 ADF），离策略评估 `--cb_type ips/dr/dm/mtr`，标签格式 `action:cost:probability` [R34]。VW 在 9.10.0（GitHub 2024-08-01）后约 19 个月无发版；核验修正：2026-03-03/04 发布 9.11.1/9.11.2（PyPI 于 2026-03-07 即已上传 9.11.2，并非 2026-09 才恢复 PyPI）；2026-09-14 的 9.11.4 是安全补丁，修复 5 个在加载模型（`vw -i`）或解析 slates/CCB DSJSON 时可触发的堆越界读写公告；9.11.5 发布说明称此前 .NET/Python/WASM 包靠手工发布、NuGet 停在 9.3.0、PyPI 停在 9.11.2，9.11.5 的自动发布失败，9.11.6（2026-09-23）是 pip/NuGet 首个含安全修复的版本；续核验修正：9.11.5/9.11.6 发布说明另称 Java 制品改经 Sonatype Central Portal 发布（OSSRH 已于 2025-06-30 关停），但截至 2026-09-26 Maven Central 上 `com.github.vowpalwabbit:vw-jni` 最新仍为 9.11.1，不含上述安全修复 [R34][R67]。v2 若采用 VW，须锁定 Python 包 ≥9.11.6、不用 Java 绑定，且不加载不可信模型文件。Azure AI Personalizer（基于强化学习的托管服务）自 2023-09-20 起不能新建，**2026-08-25 退役**，官方建议迁移到开源 `microsoft/learning-loop` [R35]（续核验注：Azure Updates 该条公告的 id 仍是原定日期 `…-retired-on-1-october-2026`，但现标题、正文与 Learn 文档均为 2026-08-25；搜索引擎摘要与部分旧资料仍显示 2026-10-01，引用时以前者为准）；Personalizer 文档建议每次 Rank 不超过约 50 个动作、每天至少约 1000 个事件才能有效学习 [R35]——可作为 v2 探索槽规模的量级参考。

**Cornac / Microsoft Recommenders / RecBole（离线评估三件套）**：Cornac 对"物品有文本"场景最友好：内置 CTR（协同主题回归，2011）、CDL（2015）、ConvMF、CVAE 等文本模型与 citeulike 数据集，也包含语义 ID 类生成式模型 TIGER（2023 论文）与 RPG（并行生成长语义 ID，2025 论文），集成 Annoy/FAISS/hnswlib/ScaNN，并有 Flask serving 与 A/B 扩展；README 称被 ACM RecSys 2023 推荐为评估与复现框架 [R29]。Microsoft Recommenders 提供评估指标、数据切分与约 30 个算法的示例笔记本（含 TF-IDF 内容推荐示例 `tfidf_covid.ipynb`、NRMS/NAML 新闻推荐），属 LF AI & Data 项目 [R27]。RecBole 覆盖 94 个算法、44 个数据集，但 2025-02 后无提交 [R28]。

**Vespa 与 Qdrant（推荐相关能力）**：Vespa news 教程用 MIND 数据，用户与新闻向量经 `nearestNeighbor` 检索、HNSW 近似，并支持在 ANN 遍历中施加过滤（如只取 sports 类）[R36]；Vespa streaming 模式为"个人数据"设计：文档 ID 带用户组（`id:namespace:type:g=userid:localid`），查询只扫描该用户子集，无索引开销、约 45 字节/文档内存，官方不建议与 indexed 模式混在同一集群 [R36]。Qdrant 的 Recommendation API 直接接受正/负样例：`average_vector`（默认，`avg_pos + avg_pos − avg_neg`）、`best_score`（v1.6.0+，逐样例取最佳正/负分，耗时随样例数线性增长，可只给负样例）、`sum_scores`；另有 Discovery（v1.7+）与 Context search [R39]。这两类能力分别对应 v2 的"私有全文检索"和"左滑/右滑即正负样例"。

### 2.5 总览表 B：学术推荐、科学文献表示与审稿匹配

| 项目 | 仓库/来源 | Star | License | 活跃度 | 算法要点 | 规模假设 | v2 |
|---|---|---|---|---|---|---|---|
| arxiv-sanity-lite | karpathy/arxiv-sanity-lite | 1,696 | MIT | 最后提交 2022-02-14（pushed 2023-06-19） | 每个用户标签训练一个 LinearSVC（`class_weight='balanced'`，默认 C=0.01）于摘要 TF-IDF 上；展示正向前 40 与负向后 20 权重词；每日邮件推荐 | README：1GB Nanode（$5/月）索引约 3 万篇 | C（可解释基线思路） |
| arxiv-sanity-preserver | karpathy/arxiv-sanity-preserver | 5,794 | MIT | 2021-11 | 前代，已被 lite 取代 | — | D |
| zotero-arxiv-daily | TideDra/zotero-arxiv-daily | 5,991（fork 5,243） | AGPL-3.0 | 2026-09-01；≥100；v1.1.0（2026-04-14） | 以用户 Zotero 库为画像：候选与库内论文摘要 embedding 相似度按"加入顺序"衰减加权求和；LLM 生成 TL;DR；源 arXiv/bioRxiv/medRxiv/chemRxiv | GitHub Actions 零成本（公开仓库每次 ≤6h） | C |
| gpt_paper_assistant | tatsu-lab/gpt_paper_assistant | 551 | Apache-2.0 | 2024-03 | GPT-4 按自然语言主题 prompt 过滤 + 关注作者匹配（S2 作者 ID） | README：2024-02-07 跑完 cs.CL 花费 $0.07 | C |
| ArxivDigest | AutoLLM/ArxivDigest | 467 | MIT | 默认分支最后提交 2023-07-13（pushed 2024-05-26；续核验修正） | 自然语言兴趣描述 + `gpt-3.5-turbo-16k` 给每篇 1–10 相关性分 | LLM API 成本 | C |
| daily-arXiv-ai-enhanced | dw-dengwei/daily-arXiv-ai-enhanced | 3,012 | 自定义"Modified Apache License"（GitHub 识别为 Other） | 2026-09-08 | GitHub Actions/Pages 零服务器；DeepSeek 中文摘要（约 0.2 元/天）；按关键词/作者本地高亮；README 有合规审查警示 | 零服务器 | C |
| PaperFlow | OpenRaiser/PaperFlow | 167 | MIT | 2026-08-22 | 反馈闭环：推送中被选中=正、同批未选=弱跳过、"none"=全否、精读=保守正信号；长短期兴趣漂移状态；SQLite | 本地单机 | C（注意：其冷启动 agent 会在服务端抓取用户给出的 Google Scholar 个人主页，见 `agents/coldstart-agent/main.py` 的 `_fetch_google_scholar_profile_pages`（续核验确认），触及本项目"Google Scholar 不做自动化主源"的红线，不可照搬） |
| customize-arxiv-daily | JoeLeelyf/customize-arxiv-daily | 160 | MIT | 2025-09-24 | 自定义 arXiv 每日推荐 | — | C |
| Scholar Inbox（平台闭源） | 论文 arXiv 2504.08385；数据 avg-dev/scholar_inbox_datasets | 6（数据仓库） | 数据 CC BY-NC-ND 4.0 | 数据仓库 2026-01-05 | 见 2.6 | 3M 论文、23k 注册用户 | C（配方）；B（数据仅限非商业研究评估） |
| SPECTER | allenai/specter；HF allenai/specter | 593 | Apache-2.0 | 最后提交 2023-05-10（pushed 2023-06-12；续核验修正） | SciBERT 初始化，引文三元组（查询/被引/引文的引文）margin loss，标题+摘要编码（arXiv 2004.07180） | BERT-base 级推理 | D（被 SPECTER2 取代） |
| SPECTER2 | allenai/SPECTER2；HF allenai/specter2、specter2_base | 144（HF base 累计下载约 11.4M） | Apache-2.0（GitHub 仓库与 specter2_base；HF `allenai/specter2` proximity adapter 卡片未声明 license 字段） | GitHub 最后提交 2025-10-24 | 600 万引文三元组预训练（SPECTER 的 10 倍，23 个学科）+ 任务格式 adapter：proximity、adhoc_query、classification、regression；另有基于 2018 年后论文的 aug2023refresh 版本 | bert-base 架构，max_length 512；CPU 可推理，批量回填宜用 GPU | A |
| SciRepEval | allenai/scirepeval（arXiv 2211.13308，EMNLP 2023） | 92 | Apache-2.0 | 2026-01-22 | 24 个任务（8 个新任务）、4 种格式；格式专用 adapter/control code 比单一 embedding SOTA 高 2 分以上 | — | B（评估） |
| SciNCL | HF malteos/scincl（arXiv 2202.06671，EMNLP 2022） | HF 累计下载约 2.5M | MIT | HF 更新 2024-06 | 在引文图嵌入空间取近邻构造三元组，缓解 SPECTER 离散引文的偏差；109.9M 参数 | BERT-base 级 | A（备选/集成） |
| Semantic Scholar 相关开源 | allenai/s2search、S2AND、S2APLER、s2orc、citeomatic、s2_fos、papermage、asta-paper-finder、ai2-scholarqa-lib、scidocs | 见 2.7 | 见 2.7 | 见 2.7 | 检索重排、作者消歧、论文聚类去重、引文推荐等 | — | 见 2.7 |
| S2 Recommendations API（服务，闭源） | api.semanticscholar.org/recommendations/v1 | — | 服务条款 | — | `POST /papers/`（positivePaperIds、negativePaperIds，limit 默认 100、最大 500）；`GET /papers/forpaper/{paper_id}?from=recent\|all-cs` | 外部服务；限速（核验补充）：无 key 时所有匿名用户共享 1000 req/s，API key 入门额度 1 RPS（全端点）[R64]；平台论文 §4.3 称该 API 的候选取自近 60 天发表的论文（v1 2023-01-24，v2 2025-04-25 仍如此）[R62]，现行 swagger 的 forpaper 端点另有 `all-cs` 池 [R52] | B（冷启动种子；许可协议要求署名 "Semantic Scholar"、禁止 repackage/sell/distribute/sublicense API [R64]；多用户平台缓存与再展示结果的边界 ⚠ 未核验） |
| openreview-expertise | openreview/openreview-expertise | 51 | MIT | 2026-08-31；78 | 审稿人-论文 affinity：SPECTER+MFR（0.8/0.2 分数级集成）、SPECTER2+SciNCL（0.5/0.5 论文相似度级集成）、BM25、TF-IDF；按审稿人论文取 max（默认）或 mean | SPECTER 服务会生成约 1GB 临时文件；GPU 可选 | B/C |
| openreview-matcher | openreview/openreview-matcher | 23 | 仓库无 LICENSE 文件（setup.py 声明 MIT） | 2026-08-26；78 | 约束分配：MinMax（OR-Tools 最小费用流）、FairFlow、FairIR、Randomized（LP + BvN 采样）、FairSequence（WEF1）、PerturbedMaximization（凸 QP） | 依赖 ortools 与 gurobipy（部分求解器需 Gurobi 许可） | B（仅容量约束分配场景） |
| PeerReview4All | niharshah/peerreview4all | 4 | GPL-3.0 | 2023-01 | 最大化"最差论文"的审稿质量（JMLR 2021），迭代 LP | gurobipy；10k×10k 实例单轮约 90 分钟（README） | C |
| ACL reviewer-paper-matching | acl-org/reviewer-paper-matching | 26 | BSD-3-Clause | 2021-05 | ACL 2021 使用：摘要相似度 + S2 语料 | S2 全量 dump 约 150GB（可选精简路径） | C |

### 2.6 Scholar Inbox：与 v2 规模最接近的公开配方（深读）

来源：arXiv 2504.08385（v1 2025-04-11，v2 2025-06-14；作者含 Andreas Geiger 等）与数据集仓库 [R46]。

| 维度 | 公开事实 |
|---|---|
| 论文来源 | arXiv、bioRxiv、chemRxiv、medRxiv 与公开会议论文集；缺失字段用 Semantic Scholar 开放语料补齐 |
| 规模 | 数据库 300 万论文；注册用户 23k，其中 8k（35%）近 30 天活跃；来自 14.3k 用户的 80 万条显式正/负评分（数据仓库 README 计为 774k 条显式评分 + 556k 条隐式交互） |
| 表示 | 标题与摘要以 [SEP] 拼接，用 GTE-large 编码（论文描述为"多阶段对比学习训练"的编码器，与 thenlper/gte-large〔MIT，arXiv 2308.03281〕一致，具体 checkpoint ⚠ 未核验），PCA 降至 256 维以节省时间与内存 |
| 每用户模型 | 逻辑回归，按用户单独训练；负样本 = 用户显式点踩 + 5k 条该用户未交互的随机论文；加权二元交叉熵，对正评分、负评分、随机负样本分别赋权；消融标准配置 (C=0.1, V=0.8, S=5.0)（C 为正则强度倒数，V、S 控制显式/随机负样本比例与负样本权重尺度）。核验补充（论文 §3.1.1 原式）：用户平均只有 78 条正评分，类别严重不平衡；约束 n_P·w_P = S·(n_N·w_N + n_R·w_R)，中间权重 w̃_P = 1/n_P，w̃_N = S·V/(V·n_N + (1−V)·n_R)，w̃_R = S·(1−V)/(V·n_N + (1−V)·n_R)。显式点踩越多，随机负样本的影响越小。附录消融：V 从 0 升到 0.9 时，显式负例特异度由 68% 升到 78%，F1/nDCG 单调下降；作者取 V=0.8，以便让点踩更有效；S>5 后召回明显下降 |
| 在线更新 | "每提交一条评分，推荐器就重新训练" |
| 冷启动 | Scholar Maps：对 300 万论文 embedding 做 t-SNE 的二维科学地图，叠加 Qwen 生成的四级主题标签（field/subfield/subsubfield/method）；用户在地图上找到领域并选若干感兴趣论文，再由主动学习"分层采样、优先决策边界附近及其上方的论文"请用户评分 |
| 交付 | 每日/每周 digest（主功能）+ 邮件（可选星期几） |
| 基础设施 | NGT 近邻索引；Celery 分布式任务（GPU 计算 embedding 与图表抽取，可 SSH 接入远程 worker）；NGINX、React、deepscatter、papermage |
| 表示对比（表 2，256 维，F1 / nDCG / Balanced acc / AUC） | TF-IDF 10k 维：83.60 / 88.67 / 75.74 / 84.41；TF-IDF 256：81.03 / 83.37 / 74.52 / 82.28；SPECTER2：83.22 / 84.21 / 78.16 / 86.36；GTE-B：84.16 / 85.42 / 77.92 / 86.24；GTE-L：84.51 / 85.83 / 78.31 / 86.75。作者因"在显式评分上更优"选 GTE-L |
| 开放程度 | 平台闭源；公开评分数据集与摘要句子高亮数据（2,538 条，problem/task/idea/result 四类），许可 CC BY-NC-ND 4.0（禁止商用与演绎）；第三方非官方 CLI 如 mrshu/scholarinboxcli（MIT）存在，使用条款 ⚠ 未核验 |
| 会议录用 | 核验修正（原为"⚠ 未核验"）：已收录于 ACL 2025 System Demonstrations（维也纳），ACL Anthology ID `2025.acl-demo.30` [R63]；arXiv v2 本身为 CC BY 4.0 |

对 v2 的映射：刷卡界面天然产生"显式正/负"标签，与 Scholar Inbox 的点赞/点踩同构；"每次评分重训"在 256 维 LR 上是 CPU 毫秒到秒级（估算），可以做到"右滑一张、下一张就变"。

### 2.7 Semantic Scholar 相关开源与服务

| 项目 | Star／License／最后活动 | 作用 | v2 |
|---|---|---|---|
| allenai/s2search | 113／Apache-2.0／2020-10 | Semantic Scholar 搜索的第二阶段重排器（首阶段如 Elasticsearch），特征化与模型都快；需 kenlm，环境为 Python 3.7 | C |
| allenai/S2AND | 116／CC-BY-4.0（LICENSE 原文）／2026-09-05 | 作者消歧算法与评测套件 | B（作者画像与"关注作者"去歧义） |
| allenai/S2APLER | 23／Apache-2.0／2026-07-08 | 论文聚类（同一论文多版本/多来源合并）数据集与生产模型 | B（多源去重的参考） |
| allenai/s2orc | 1,088／未识别 license／2024-04 | 开放语料构建代码 | C |
| allenai/citeomatic | 197／Apache-2.0／2020-01 | 为草稿推荐引文 | D |
| allenai/s2_fos | 34／Apache-2.0／2024-01 | 学科分类 | C |
| allenai/papermage | 803／Apache-2.0／2024-11 | 论文结构化解析（Scholar Inbox 用于图表抽取） | B（抽取层参考） |
| allenai/asta-paper-finder | 245／Apache-2.0／2026-03-17 | "冻结版" Paper Finder agent，用于复现评测 | C |
| allenai/ai2-scholarqa-lib | 282／Apache-2.0／2026-06-25 | ScholarQA 应用与库 | C |
| allenai/scidocs | 149／CC-BY-4.0（核验修正：LICENSE 原文为 CC BY 4.0；GitHub 识别为 Other/NOASSERTION）／2022-12 | SPECTER 配套评测数据 | C |
| allenai/s2-folks | 278／已归档 | API 用户社区 | D |

- AI2 官方博客（2023-11-27）说明 SPECTER 为 Semantic Scholar 的用户 research feeds、作者消歧、论文聚类等提供 embedding；SPECTER2 用 600 万三元组（SPECTER 的 10 倍）、覆盖 23 个学科 [R48]。
- **S2 feed 推荐器配方（核验修正：原文称"具体算法未公开"，实为已公开）**：《The Semantic Scholar Open Data Platform》（arXiv 2301.10140，v1 2023-01-24，v2 2025-04-25）§3.4.5 "Recent Paper Recommendations" 描述了三步流程 [R62]：① Ranker Training 是 arxiv-sanity 的扩展，按每个用户的正/负标注训练**两个线性 SVM**（一个用 TF-IDF 表示，一个用 SPECTER embedding），负标注再补充随机负样本并赋较低权重；② Candidate Selection 用 FAISS 在近 60 天发表的约 100 万篇论文的 SPECTER 向量上做近似 kNN（每晚刷新）；③ Candidate Ranking 取与正样本质心最近的约 500 篇，用两个模型分数的平均值排序。该配方与 Scholar Inbox（2.6）同构，再次说明"内容向量 + 每用户线性模型 + 随机负样本"是学术 feed 的主流起点；论文未给出线上效果数字。
- SPECTER2 模型卡的对比（SciRepEval 平均 / MDCR 的 MAP 与 Recall@5）：BM25 —／(33.7, 28.5)；SPECTER 67.5／(30.6, 25.5)；SciNCL 68.8／(32.6, 27.3)；SciRepEval-Adapters 70.7／(35.3, 29.6)；SPECTER2 Base 69.1／(38.0, 32.4)；SPECTER2-Adapters 71.1／(38.4, 33.0) [R48]。
- S2 Recommendations API 由 swagger.json 核验（见 2.5 表）[R52]；其返回的是 S2 语料内的论文（平台论文 §4.3 称候选限近 60 天，v2 2025-04-25 未改 [R62]；`forpaper` 端点现另有 `all-cs` 池），适合作为 v2 新用户冷启动的"种子扩展"，但它是外部闭源服务，推荐质量与配额不可控（key 入门额度 1 RPS [R64]）。

### 2.8 审稿人匹配：学术场景中最成熟的"双边"开源

- **affinity 计算**（openreview-expertise）[R53]：README 描述的集成方案有 SPECTER+MFR（在审稿人-论文分数层按 0.8/0.2 集成）与 SPECTER2+SciNCL（在论文-论文相似度层按 0.5/0.5 集成），另有 BM25/TF-IDF 基线；审稿人对投稿的分数默认取"与其各篇论文相似度的最大值"（`max_score`），可改为平均（`average_score`）；画像可限定"最近 N 篇或最近 x%"（`top_recent_pubs`）与"某日期之后"（`minimum_pub_date`），允许审稿人排除自己的部分论文（`exclusion_inv`），并可融合审稿人主动 bid（`bid_inv`）。
- **离线精度**（同 README，数据来自 Stelmakh 等金标准）：Loss / Easy / Hard 三元组准确率——TPMS 0.28/0.80/0.62；ELMo 0.34/0.70/0.57；SPECTER 0.27/0.85/0.57；SPECTER+MFR 0.24/0.88/0.60；ACL 0.30/0.78/0.62；SPECTER2 0.22/0.89/0.61；SciNCL 0.22/0.90/0.65；SPECTER2+SciNCL 0.21/0.91/0.65 [R53]。
- **金标准研究**（arXiv 2303.16750，2023-03-23）：58 位研究者对读过的论文给出 477 条自评熟悉度；所有算法都有显著误差，易例误排 12%–30%、难例 36%–43%；仅用标题+摘要时 SPECTER2 最好，给全文时经典 TF-IDF 可追平 SPECTER2；通用 LLM 不如专用模型 [R57]。
- **约束分配**（openreview-matcher）[R54]：MinMax 用 OR-Tools 最小费用流满足论文/审稿人上下限配额；FairFlow/FairIR 以二分搜索找"每篇论文分数和的公平阈值"；Randomized 以 LP 求满足"每对匹配边际概率上限"的随机分配再 BvN 采样；FairSequence 满足加权 envy-free up to 1 item（WEF1）；PerturbedMaximization 以凸 QP 在总分与随机性之间权衡（arXiv 2310.05995，NeurIPS 2023 spotlight；核验修正：论文定位为同时服务多种随机化动机——防恶意操纵、评估替代分配、审稿人多样性与匿名性——的通用方法，不只是防操纵）。PeerReview4All（GPL-3.0，Gurobi）最大化最差论文的匹配质量 [R55]。

### 2.9 总览表 C：双向 / 互惠推荐开源实现

| 项目 | 仓库 | Star／License／最后提交 | 要点 | v2 |
|---|---|---|---|---|
| RECON（RecSys'10 在线约会） | m-ochi/recon | 7／MIT／2015-04 | 互惠分 = 两个方向兼容度的调和平均 `2/(1/s_xy + 1/s_yx)`（`recon.py`） | C（公式直接可用） |
| Chaos RRS | kdevo/chaos-rrs | 12／无 license／2021-11 | 人-人隐式反馈混合互惠推荐研究框架（硕士论文配套），自述非生产用 | C |
| Fair Reciprocal Recommendation（RecSys'24）及 Nash 社会福利工作论文 | CyberAgentAILab/FairReciprocalRecommendation | 6／MIT／2025-09-05 | 匹配市场中的公平互惠推荐：envy-freeness 检验、naive/prod/TU-matching/iterative LP 等基线；依赖 cvxpy、torch | C/B |
| MODE（RecSys'26） | CyberAgentAILab/mode | 0／MIT／2026-08-20 | 互惠推荐直接效应的相互最优（arXiv 2608.01731），合成数据实验，Python 3.12 + uv | C |
| MotifGNN | RManLuo/MotifGNN | 9／无 license／2022-06 | 基于 motif 的 GNN 在线约会互惠推荐 | D |
| KAERR（AAAI 2024） | AllminerLab/Code-for-KAERR-master | 7／无 license／2023-12 | 知识感知可解释互惠推荐 | D |
| ReciprocalRecommender | BinFuPKU/ReciprocalRecommender | 4／无 license／2020-08 | 2019–2020 多个互惠 CF 模型复现（TF1.13） | D |
| biDeepFM | ezyil/biDeepFM | 3／无 license／2021-05 | 多目标 DeepFM 用于互惠推荐 | D |
| 工业样例：X 互关回复加权 | xai-org/x-algorithm `BIDIRECTIONAL_BOOST_CHANGE.md` | Apache-2.0 | 互相关注的作者，其帖子"被回复概率"的权重加成（2026-07 A/B 后定为 15） | C |
| 双边容量匹配 | openreview-matcher、PeerReview4All | 见 2.5 | 见 2.8 | B/C |
| 核验补充：稳定匹配（双方偏好 + 容量） | daffidwilde/matching | 168／MIT／默认分支最后提交 2023-10-04（PyPI 1.4.3 同日，纯 Python + NumPy） | 覆盖四类匹配博弈：稳定婚姻（SM）、带容量的医院-住院医分配（HR）、学生-项目分配（SA）、稳定室友（SR）；有 JOSS 论文（10.21105/joss.02169）。与 openreview-matcher 最大化总分/公平性的目标不同，它求的是"无阻塞对"的稳定解 [R71] | C/B（读书会、组内分工这类场景若要求双方偏好稳定，可用作参照或依赖；已近 3 年无新提交） |

**"双向匹配"在学术平台上的三种语义与建议**

| 语义 | 需求 | 开源参照 | v2 建议 |
|---|---|---|---|
| 读者 ↔ 论文（供需双边） | 读者得到相关论文；新论文/新作者/小领域得到最低曝光 | X 新作者扶持与冷启动槽位 [R8]；CyberAgent 公平互惠 [R58] | 在排序后加"供给侧约束"：新论文最低曝光、单作者/单 venue 上限；不是互惠打分而是约束重排 |
| 研究者 ↔ 研究者（互惠） | 关注/合作/讨论对象推荐，需双方都有兴趣 | RECON 调和平均 [R58]；X 互关加权 [R11] | 互惠分 = 调和平均(兴趣 u→v, 兴趣 v→u)，兴趣用画像向量相似 + 显式行为；仅对 opt-in 公开画像的用户启用 |
| 论文 ↔ 评审/读书会成员（容量约束） | 每篇需 k 人、每人至多 m 篇、冲突回避 | openreview-matcher、openreview-expertise [R53][R54] | 仅在"组内分工/读书会"功能中使用；affinity 用 SPECTER2+SciNCL 按人取 max |

---

## 3. 对 v2 设计的启示

### 3.1 可直接指导设计的结论

1. **管线骨架**：采用"候选管线"六类组件抽象——Source / Hydrator / Filter / Scorer / Selector / SideEffect，独立阶段并行执行、按参数开关、错误可降级、执行与监控分离（x-algorithm `candidate-pipeline` [R5]）。这与 v1 六阶段 pipeline 的纪律一致，用 Python 实现即可，不引入 Rust/JAX。
2. **候选源映射**：X 的 in-network 对应 v2 的"用户显式关注"（订阅 DSL、关注作者/venue/主题）；out-of-network 对应语义 ANN、协同过滤、主题社区（SimClusters 的学术类比：共引/合著社区或主题体系）。每个候选源独立配额并在候选上记录来源归因；多源重复在过滤阶段去重（`DropDuplicatesFilter` [R5]）。
3. **打分口径**：多行为预测 + 显式权重融合 `Σ w_k·P(a_k)`，权重作用于"该用户的预测概率"而非计数；低基率的负向行为取大绝对值权重；净负分候选整体沉底（负分偏移）[R8][R9]。建议的 v2 行为集合：右滑/赞、收藏、展开摘要、打开 PDF/全文、停留时长、评论、评分（1–5）、左滑/不感兴趣、屏蔽作者或主题、举报。起步时各头可共用一个每用户 LR，数据足够后再拆多头。
4. **冷启动即刷卡**：新用户先选领域（可做 Scholar Maps 式二维地图或学科树）并挑几篇种子论文，之后前 N 张卡按主动学习选择"决策边界附近及其上方"的论文 [R46]；每次滑动后立刻重训该用户模型（Scholar Inbox 每次评分后重训 [R46]）。S2 Recommendations API 可作可选的种子扩展（正/负样例接口）[R52]。
5. **每用户模型起步配方**：256 维内容向量上的逻辑回归；负样本 = 显式负反馈 + 约 5k 随机未交互论文，分三类加权；以 (C=0.1, V=0.8, S=5.0) 为超参起点 [R46]。优点：可解释、CPU 秒级、天然按用户隔离、与"持续学习"需求直接吻合。Semantic Scholar feed 的公开配方（TF-IDF 与 SPECTER 两个线性 SVM 取平均、随机负样本低权重、按正样本质心取约 500 个候选 [R62]）可作第二条对照基线（核验补充）。
6. **内容表示**：SPECTER2（论文用 proximity adapter，检索 query 用 adhoc_query adapter [R48]）与 GTE-large 二选一做 A/B；两者在 Scholar Inbox 实验中 AUC 相差 0.39 个百分点（86.75 vs 86.36）[R46]，因此选择应由许可（Apache-2.0/MIT）、跨学科覆盖（SPECTER2 覆盖 23 个学科 [R48]）、推理成本与多语言需求决定。PCA 到 256 维时百万论文的原始向量约 1.0GB（float32，估算），768 维约 3.1GB（估算）。默认配置不得使用非商业许可模型（如 zotero-arxiv-daily 默认的 `jinaai/jina-embeddings-v5-text-nano-retrieval`〔v5-text-nano 的检索变体〕为 CC-BY-NC-4.0 [R59]）。核验补充：SPECTER2 与 GTE-large 均以英文语料为主；若 v2 需要覆盖中文论文或中文查询，可把许可宽松的多语言模型 `Qwen/Qwen3-Embedding-0.6B`（Apache-2.0，2025-06-03 上架 HF）与 `BAAI/bge-m3`（MIT）列入 A/B 候选，二者在学术推荐任务上的效果 ⚠ 未核验 [R66]。
7. **共享层与私有层分离（合规硬约束）**：共享层只包含论文公开元数据与开放获取内容派生的 embedding、索引、主题簇；私有层包含每用户的反馈、画像、模型、auth-gated 全文及由其派生的任何特征、摘要与解释。auth-gated 全文不得进入共享 embedding、共享模型训练、他人可见的解释或协同信号；个人全文检索采用"按用户分组"的分区/流式索引（Vespa streaming 模式的 `g=userid` 文档 ID [R36] 是一种成熟形态）。
8. **协同信号的隐私阈值**（设计推论）：item-to-item 协同（"收藏此文的人也收藏"）在 1–1 万用户的小社区可能暴露具体个人行为，需设最小支持度（k-匿名式阈值），并排除仅由私有馆藏产生的共现；推荐理由不得引用他人的私有行为。
9. **只认"已曝光"的反馈**：训练用反馈必须绑定 impression/request id；经分享链接直达产生的点赞只作弱信号或不入训练（X："只有被下发到首页时间线的帖子上的行为才计入" [R8]）。这同时是防刷与防协同操纵的最低成本手段。
10. **过滤与排序分离**：能否展示（授权可用性、撤稿、屏蔽词/作者、已看/已推、主题排除）与如何排序分属不同阶段（X Key Design Decision "Ranking and Visibility Are Separate" [R5]），并提供"为什么看到/为什么没看到"的透明度视图（Under the Hood 类比 [R5]）。
11. **多样性与探索**：作者衰减乘子 `(1−floor)·decay^k+floor` [R9]、venue/主题配额、DPP 重排（θ 控制相关性与多样性权衡，默认可从 0.5 起调 [R10]），加少量探索槽（VW `--cb_explore_adf` 或 ε-greedy [R34]）；新论文/新作者设最低曝光，可采用 X 的形态：低曝光、新发布（48 小时内）的供给提升到固定位置附近，并可用 Beta 先验的 Thompson sampling 在冷启动候选间分配曝光（X 参数只作量级参考 [R8]：帖子首页曝光 <1000、作者粉丝 ≤1000、每次请求至多提升 1 条到第 16 位附近、Beta(0.75, 49.25) 先验且默认关闭）。
12. **兴趣漂移**：长期画像（收藏、自有论文，可用 zotero-arxiv-daily 的按加入顺序衰减 `w_i ∝ 1/(1+log10(i+1))` [R44]）+ 短期画像（本次会话滑动）；允许用户"只用最近 N 篇/排除某些条目"定义画像（openreview-expertise 的 `top_recent_pubs`、`minimum_pub_date`、`exclusion_inv` [R53]）。
13. **检索与推荐同一向量空间**：向量库需同时支持"过滤条件下的 ANN"（Vespa 在 HNSW 遍历中过滤 [R36]）与"正负样例推荐"（Qdrant `average_vector`/`best_score`/`sum_scores` [R39]），以支撑"只看 2026 年 + 金融 + 与我兴趣相近 + 排除已读"这类组合查询；左滑/右滑直接转化为负/正样例。
14. **可解释卡片**：卡片附一行理由——近邻证据（"与你收藏的 X 相近"）或线性模型最强正向词（arxiv-sanity-lite 展示 SVM 正负权重词 [R43]）；摘要可按 problem/task/idea/result 四类句子高亮（Scholar Inbox 高亮数据的标签体系 [R46]）。可解释性同时提升反馈质量。
15. **双向匹配三分法**：读者↔论文用供给侧约束重排；研究者↔研究者用互惠分（调和平均 [R58]）+ 互关加权（X [R11]）；容量约束分配用 openreview-matcher 的求解器（注意无 LICENSE 文件与 Gurobi 依赖 [R54]）；若目标是"双方偏好下的稳定解"而非总分最大，可参照 MIT 许可的 `matching` 库，它实现了 HR/SA 等带容量的稳定匹配（核验补充 [R71]）。具体采用哪几种由产品定义决定（见 4 节）。
16. **实验机制**：参数集中定义、带生产默认值、可按实验桶覆盖（X `param!` + 配置系统 + 定时同步默认值 [R5][R8]）；确定性 holdout（`InventoryHoldoutFilter` [R5]）；探索日志记录倾向分以便离策略评估（VW `ips/dr` [R34]、OBP [R41]）；离线基准用 Cornac/RecBole/Recommenders [R27][R28][R29]。Scholar Inbox 数据集可用于算法研究对比，但 CC BY-NC-ND 禁止商用与演绎 [R46]。
17. **生成式推荐只预留不起步**：OneRec/HSTU/Phoenix 的收益依赖海量行为与 GPU [R18][R24]。v2 现在只需在数据模型中预留：曝光日志与行为序列表、可空的语义 ID 字段（残差量化码，参考 Phoenix 6×256 [R7]、MiniOneRec RQ-Kmeans [R20]）、embedding 版本号与维度。
18. **LLM 的位置**：LLM 用于小候选集的重排、推荐理由与摘要（Gorse `type = "llm"` 重排 [R30]；ArxivDigest 1–10 相关性分 [R45]），不作为百万级召回主路径；按用户配额计费；由私有全文生成的摘要只对本人可见（与第 7 条一致）。
19. **依赖许可筛选**：优先 Apache/MIT/BSD/PostgreSQL 许可；不把 AGPL（twitter/the-algorithm、zotero-arxiv-daily）或 GPL（PeerReview4All）代码并入多用户服务端；无 LICENSE 文件的仓库（openreview-matcher、s2orc、chaos-rrs 等）只借鉴思想或先确认许可；模型与数据许可单独审查（jina v5 nano 及其 retrieval 变体 CC-BY-NC，Scholar Inbox 数据 CC BY-NC-ND，S2AND 与 scidocs CC-BY-4.0）；GitHub 显示为 "Other" 的仓库须读 LICENSE 原文，例如 snap-research/GRID 实为仅限非商业研究的许可（核验补充 [R70]）；VW 须 ≥9.11.6 以包含模型加载安全修复，Java 绑定在 Maven Central 暂无修复版 [R67]。
20. **离线相似度不等于满意度**：即使专用模型，审稿匹配金标准中易/难样本误排仍达 12–30% / 36–43% [R57]；v2 以在线反馈闭环为主，内容相似度负责召回与冷启动，排序由个体反馈模型决定。

### 3.2 v2 推荐栈候选组合（极简 / 中等 / 进阶）

| 层 | S1 极简（MVP） | S2 中等 | S3 进阶 |
|---|---|---|---|
| 适用阶段（阈值为估算，需实验校准） | ≤约 1k 活跃用户；反馈稀疏 | 约 1k–1 万用户；日显式反馈约 10^4 条以上 | 1 万用户以上或累计行为约 10^7 条以上且有 GPU 预算 |
| 论文表示 | SPECTER2 proximity 或 GTE-large → PCA 256 维；TF-IDF 作可解释辅特征 | 同 S1 + SPECTER2 adhoc_query 统一检索空间；作者/共引图特征；S2AND/S2APLER 辅助作者消歧与多源去重 | + 语义 ID（RQ-Kmeans/RQ-VAE）与行为序列表示 |
| 索引与召回 | pgvector 或 Qdrant 的 ANN（带过滤）+ 订阅 DSL 新论文 + 关注作者/venue | + implicit ALS/BPR 协同召回 + 主题社区召回 + Qdrant 正负样例推荐；或整体交给 Gorse 多源召回 | + two-tower 检索（Phoenix 检索式）或生成式检索（Cornac TIGER / MiniOneRec） |
| 排序 | 每用户 LR（Scholar Inbox 配方）+ 新鲜度与质量先验的规则融合 | 多行为预测（每行为一个轻量模型或 LightGBM 多任务）→ Σw·P(a)；可选 Metarank/LambdaMART 式二次重排 | HSTU / Phoenix 式 transformer 多行为模型（candidate isolation，可缓存） |
| 重排、多样性、探索 | 作者衰减 + MMR/简化 DPP + ε-greedy 探索槽 | DPP + VW `--cb_explore_adf` 或 contextualbandits 探索槽 + 新论文/新作者最低曝光 | DPP + 供给侧约束优化 + bandit；LLM 重排与理由（可选） |
| 反馈学习 | 每次滑动后重训该用户 LR（CPU 秒级，估算） | 在线 bandit 更新 + 夜间批训练协同与排序模型 | 近实时训练（Monolith 式思想）——仅当规模需要 |
| 双向匹配 | 研究者互惠分（RECON 调和平均，规则版） | + 互关加权、供给侧曝光约束 | 公平互惠（CyberAgent RecSys'24/'26 思路）+ 容量约束匹配（openreview-matcher） |
| 离线评估 | 自有日志回放；Scholar Inbox 数据（仅研究） | Cornac / RecBole / Recommenders；OBP 离策略评估 | + 在线 A/B 与确定性 holdout |
| GPU | 不需要（百万论文 embedding 一次性回填：单卡约数十分钟量级，纯 CPU 约数十小时量级，均为估算 ⚠ 未实测） | 可选单卡 | 需要（HSTU 公开实验 ≥24GB [R24]；Phoenix nano 单卡 [R7]） |
| 主要依赖许可 | Apache-2.0（SPECTER2、Qdrant）、MIT（thenlper/gte-large）、BSD-3-Clause（scikit-learn，67,381 star，2026-09-26 核验）、PostgreSQL License（pgvector） | + MIT（implicit、LightGBM）、BSD-3（VW）、Apache-2.0（Gorse/Metarank） | + Apache-2.0（generative-recommenders、x-algorithm、MiniOneRec） |
| 最大风险 | 模型简单、跨用户协同发现弱、易形成个人茧房 | 组件多、运维与特征一致性复杂 | 数据不足时收益为负、成本高 |

**选择理由**

- **S1 以 Scholar Inbox 为蓝本**：规模同量级（其 3M 论文、23k 用户 [R46]），全部组件为宽松许可，纯 CPU，天然满足"每人私有画像"的隔离要求；刷卡交互与"每次评分重训"的主动学习一一对应；X 式的管线抽象与 Σw·P 打分口径从第一天就用上，后续升级不改接口。
- **S2 的两条路**：自建（implicit + 多行为 LTR + VW）保持 Python 主栈与数据单副本，适合已有 v1 工程纪律的团队；引擎化（Gorse）上线更快、自带 Dashboard 与 LLM 重排，但要维护 Go 服务与第二份数据副本并逐项确认私有数据隔离。两者都应保持"共享内容层 + 私有反馈层"的分离。
- **S3 只在数据说话后启动**：生成式/序列模型的公开收益来自十亿级用户或快手级流量 [R18][R24]；v2 先积累曝光与行为序列、预留语义 ID，再以 Phoenix nano 或 MiniOneRec 在离线回放上验证增益，确认正收益后再上线。

**现在就应在数据模型中预留的字段/表**（设计建议，不含实现）：

- 曝光日志：request_id、user_id、paper_id、位置、候选源、各打分分量、实验桶、倾向分（探索槽）。
- 行为事件：动作类型（显式/隐式、强弱）、评分值、停留毫秒数、评论 id、关联 impression_id、来源（下发/直达）。核验补充：撤销类事件（取消赞、取消踩）单独记录，不直接删除原事件；来源字段可参照 Yambda 的 `is_organic` 标记 [R72]。
- 模型与表示版本：每用户模型版本与超参、embedding 模型名/版本/维度/PCA 版本、可空语义 ID。
- 可见性标记：授权可见范围（共享/私有）、撤稿/质量标签、屏蔽规则命中记录（支撑"为什么没看到"）。

设计伪代码（非实现，仅说明 S1 的数据流）：

```text
# 设计伪代码：S1 每用户在线更新与打分
on_feedback(user, paper, action, impression_id):
    if not served(impression_id, user, paper): record_weak_signal(); return   # 只认已曝光（口径同 X）
    append_event(user, paper, action, dwell_ms, impression_id)
    if action in {right_swipe, like, save, rate>=4}: add_label(user, paper, +1)
    elif action in {left_swipe, not_interested, rate<=2}: add_label(user, paper, -1)
    model[user] = fit_weighted_logreg(pos=E[pos], neg_explicit=E[neg],
                                      neg_random=sample_unseen(user, 5000),
                                      C=0.1, V=0.8, S=5.0)                    # Scholar Inbox 起点
score_feed(user):
    cands = union(subscription_new(user), ann(user_centroids), followed_authors(user))
    cands = visibility_filter(user, cands)            # 授权/撤稿/屏蔽/已看，与排序分离
    s = sum_k w_k * p_k(user, cand)                   # 多行为头；负向头取大负权重；净负分沉底
    s = s * author_decay(k) * freshness(cand)
    return dpp_rerank(s, embeddings, theta) with exploration_slots(epsilon)
```

---

## 4. 未决问题与风险

1. **目标函数错位**：X 与 OneRec 优化的是参与度与停留时长 [R5][R18]；学术场景需要"相关、重要、可信"。v2 的最终分是否纳入质量先验（同行评审状态、venue 等级、引用、撤稿标记）以及权重如何设定，需要产品决策；纯参与度优化可能放大标题党与热门偏置。
2. **X 参数是滚动快照**：x-algorithm 近乎日更，本文权重来自 2026-09-26 的 `4c5cfe8` [R8]；任何引用需锁定 commit。2026-05-15 版本的细节已按提交 `e414c17` 的文件清单核验（核验修正，见 2.2.2 时间线 [R69]）；README 叙述与代码可能不一致（如新作者扶持的阈值实为帖子曝光，见 2.2.2），引用参数时以代码为准。
3. **OneRec 开源的可复现性与许可**：OpenOneRec 的 README 声明 Apache-2.0 但 GitHub 未识别 LICENSE 文件，README 同时称"代码与详细用法即将发布"，权重"受各自许可约束" [R16]；复现需多 GPU。
4. **Scholar Inbox 口径与许可**：论文称 80 万评分、数据仓库计 774k 条显式评分，口径差异未解释；数据集 CC BY-NC-ND 禁止商用与演绎；ACL 2025 Demo 录用已核验（2025.acl-demo.30 [R63]），具体 GTE checkpoint 仍 ⚠ 未核验 [R46]。
5. **引擎依赖的维护风险**：Gorse 活跃但为 Go 生态、独立服务；Metarank 依赖少数维护者、公司状态 ⚠ 未核验 [R31]；PredictionIO 已归档、Personalizer 已退役 [R35][R42]、Merlin 低活跃 [R26]、RecBole 停更 [R28]、LightFM 与 Python 3.12 不兼容 [R32]——任何引擎都要有替换路径（保持"候选管线"接口在自有代码中）。
6. **许可证污染**：AGPL（twitter/the-algorithm、zotero-arxiv-daily）、GPL（PeerReview4All）、无 LICENSE（openreview-matcher 仓库、s2orc、chaos-rrs、多个互惠推荐仓库）、非商业模型/数据/代码（jina v5 nano、Scholar Inbox 数据；核验补充：snap-research/GRID 代码仅限非商业研究）[R1][R44][R54][R55][R59][R46][R70]。
7. **隐私侧信道**：协同共现、推荐理由、LLM 摘要、"热门"统计都可能泄露个人或私有馆藏信息；k 阈值、差分隐私或仅用公开交互的具体策略未定（第 3.1 节第 8 条为推论，需隐私设计评审）。
8. **数据稀疏**：1–1 万用户下协同与序列模型的收益不确定；S1→S2→S3 的升级阈值仅为估算，需在曝光日志积累后用离线回放与 A/B 验证。
9. **评论/留言的双重性**：评论可能是批评而非喜好，不宜直接作为强正反馈；UGC 需要最小审核能力（举报、隐藏、限速）。X 的可见性体系复杂度 [R5] 提示此处投入不能为零，但 v2 应保持极简。
10. **外部推荐服务**：S2 Recommendations API 闭源。核验补充：限速为匿名共享 1000 req/s、API key 入门 1 RPS（全端点）；API 许可协议（页面标注 2023-05-17 更新）授予有限、不可转让、不可再许可、可随时终止的"访问与展示"许可，要求署名 "Semantic Scholar"，禁止 repackage/sell/distribute/sublicense API [R64]。多用户平台缓存推荐结果并长期再展示是否在许可范围内 ⚠ 未核验，需由 API 政策调研或向 AI2 书面确认 [R52][R64]。
11. **表示模型升级成本**：换 embedding 模型需全库重算与索引重建（百万级，估算 GPU 小时级以内），必须版本化并支持双写/灰度。
12. **"双向匹配"产品定义未决**：读者↔论文、研究者↔研究者、容量约束分配三种语义是否都做、先做哪种，影响数据模型（是否需要公开的研究者画像与 opt-in 机制）。
13. **调研自身局限**：star 为单日快照；近 12 月提交数单页上限 100；WebSearch 配额耗尽导致部分二手信息无法交叉验证（首轮核验同样没有 WebSearch 配额，全部改用 `gh api`、arXiv API、HF API、PyPI JSON 与官方页面直取；续核验只执行了 1 次 WebSearch，用于定位 Personalizer 退役公告，结论以 Microsoft 发布通信 API 的一手记录为准）；未对任何项目做本地运行或基准测试。
14. **口径不一致（核验补充）**：OpenOneRec 数据规模 README（20 万用户/1 亿交互）与技术报告摘要（16 万用户/9600 万交互）不一致 [R16]；x-algorithm README 与代码在新作者扶持条件上表述不一致 [R8]；引用时需注明出处层级。

---

## 5. 参考来源

访问日期均为 **2026-09-26**。GitHub 仓库的 star/fork/license/活跃度均通过 `gh api repos/{owner}/{repo}`、`commits`、`releases` 端点读取。

**X / Twitter**

- [R1] twitter/the-algorithm：https://github.com/twitter/the-algorithm
- [R2] twitter/the-algorithm home-mixer README：https://github.com/twitter/the-algorithm/blob/main/home-mixer/README.md
- [R3] twitter/the-algorithm 2025-09-03 提交：https://github.com/twitter/the-algorithm/commit/c54bec0d4e029fe34926ef3258a86ccacc0d0182
- [R4] twitter/the-algorithm-ml 与 heavy ranker README：https://github.com/twitter/the-algorithm-ml ；https://github.com/twitter/the-algorithm-ml/blob/main/projects/home/recap/README.md
- [R5] xai-org/x-algorithm README（HEAD `4c5cfe8`）：https://github.com/xai-org/x-algorithm
- [R6] x-algorithm 首个提交 `aaa167b` 的 README：https://github.com/xai-org/x-algorithm/blob/aaa167b3de8a674587c53545a43c90eaad360010/README.md
- [R7] Phoenix README：https://github.com/xai-org/x-algorithm/blob/main/phoenix/README.md
- [R8] 参数与权重：https://github.com/xai-org/x-algorithm/blob/main/home-mixer/params/param.rs ；新作者冷启动打分器：https://github.com/xai-org/x-algorithm/blob/main/home-mixer/scorers/author_cold_start.rs
- [R9] 打分融合：https://github.com/xai-org/x-algorithm/blob/main/xai-value-model/scoring.rs ；权重常量：https://github.com/xai-org/x-algorithm/blob/main/xai-value-model/weights.rs
- [R10] DPP 重排：https://github.com/xai-org/x-algorithm/blob/main/vm-ranker/dpp.rs
- [R11] 互关加权变更说明：https://github.com/xai-org/x-algorithm/blob/main/docs/BIDIRECTIONAL_BOOST_CHANGE.md
- [R12] x-algorithm 提交历史：https://github.com/xai-org/x-algorithm/commits/main
- [R13] 二手时间线（仅辅助定位）：https://keywordseverywhere.com/news/social-algorithm-updates/x-algorithm-open-source/

**字节 / 快手 / Meta / NVIDIA / 小红书场景**

- [R14] bytedance/monolith：https://github.com/bytedance/monolith ；论文 https://arxiv.org/abs/2209.07663
- [R15] bytedance/HLLM：https://github.com/bytedance/HLLM ；bytedance/primus：https://github.com/bytedance/primus
- [R16] Kuaishou-OneRec/OpenOneRec：https://github.com/Kuaishou-OneRec/OpenOneRec ；技术报告 https://arxiv.org/abs/2512.24762 ；权重 https://huggingface.co/OpenOneRec/OneRec-8B
- [R17] OneRec：https://arxiv.org/abs/2502.18965
- [R18] OneRec Technical Report：https://arxiv.org/abs/2506.13695
- [R19] wangshy31/OneRec-Think：https://github.com/wangshy31/OneRec-Think
- [R20] AkaliKong/MiniOneRec：https://github.com/AkaliKong/MiniOneRec ；论文 https://arxiv.org/abs/2510.24431
- [R21] Kuaishou-OneRec/KSA：https://github.com/Kuaishou-OneRec/KSA
- [R22] PersiaML/PERSIA：https://github.com/PersiaML/PERSIA
- [R23] chongminggao/KuaiRec：https://github.com/chongminggao/KuaiRec
- [R24] meta-recsys/generative-recommenders：https://github.com/meta-recsys/generative-recommenders ；HSTU 论文 https://arxiv.org/abs/2402.17152
- [R25] meta-pytorch/torchrec：https://github.com/meta-pytorch/torchrec
- [R26] NVIDIA Merlin：https://github.com/NVIDIA-Merlin/Merlin ；https://github.com/NVIDIA-Merlin/NVTabular ；https://github.com/NVIDIA-Merlin/HugeCTR ；https://github.com/NVIDIA-Merlin/Transformers4Rec ；https://github.com/NVIDIA-Merlin/models
- [R38] Applied-Machine-Learning-Lab/NoteLLM：https://github.com/Applied-Machine-Learning-Lab/NoteLLM

**推荐库、引擎与底座**

- [R27] recommenders-team/recommenders：https://github.com/recommenders-team/recommenders
- [R28] RUCAIBox/RecBole：https://github.com/RUCAIBox/RecBole
- [R29] PreferredAI/cornac：https://github.com/PreferredAI/cornac
- [R30] gorse-io/gorse：https://github.com/gorse-io/gorse ；排序文档 https://gorse.io/docs/concepts/ranking.html ；协同过滤文档 https://gorse.io/docs/concepts/recommenders/collaborative.html ；推荐器总览 https://gorse.io/docs/concepts/recommenders/
- [R31] metarank/metarank：https://github.com/metarank/metarank
- [R32] lyst/lightfm：https://github.com/lyst/lightfm ；issue #709 https://github.com/lyst/lightfm/issues/709
- [R33] benfred/implicit：https://github.com/benfred/implicit
- [R34] VowpalWabbit/vowpal_wabbit：https://github.com/VowpalWabbit/vowpal_wabbit ；CB 教程 https://vowpalwabbit.org/docs/vowpal_wabbit/python/latest/tutorials/python_Contextual_bandits_and_Vowpal_Wabbit.html
- [R35] Azure AI Personalizer 退役说明：https://learn.microsoft.com/en-us/azure/ai-services/personalizer/what-is-personalizer （现重定向到 previous-versions）；Azure Updates 公告：https://azure.microsoft.com/en-us/updates?id=ai-services-personalizer-will-be-retired-on-1-october-2026 （页面由 JS 渲染，正文取自 https://www.microsoft.com/releasecommunications/api/v2/azure/ai-services-personalizer-will-be-retired-on-1-october-2026 ，续核验）；microsoft/learning-loop：https://github.com/microsoft/learning-loop
- [R36] Vespa：https://github.com/vespa-engine/sample-apps ；https://github.com/vespa-engine/vespa ；新闻推荐教程 https://docs.vespa.ai/en/learn/tutorials/news-5-recommendation ；streaming search https://docs.vespa.ai/en/streaming-search.html
- [R37] microsoft/RecAI：https://github.com/microsoft/RecAI
- [R39] Qdrant Explore/Recommendation API：https://qdrant.tech/documentation/concepts/explore/ ；https://github.com/qdrant/qdrant
- [R40] 向量与排序底座：https://github.com/pgvector/pgvector ；https://github.com/facebookresearch/faiss ；https://github.com/nmslib/hnswlib ；https://github.com/NGT-labs/NGT ；https://github.com/unum-cloud/USearch ；https://github.com/asg017/sqlite-vec ；https://github.com/lightgbm-org/LightGBM ；https://github.com/scikit-learn/scikit-learn
- [R41] bandit/OPE：https://github.com/david-cortes/contextualbandits ；https://github.com/st-tech/zr-obp ；https://github.com/fidelity/mabwiser
- [R42] 其他：https://github.com/tensorflow/recommenders ；https://github.com/NicolasHug/Surprise ；https://github.com/pmixer/SASRec.pytorch ；https://github.com/reczoo/FuxiCTR ；https://github.com/alibaba/EasyRec ；https://github.com/massquantity/LibRecommender ；https://github.com/apache/predictionio ；https://github.com/twitter/GraphJet

**学术推荐与科学文献表示**

- [R43] karpathy/arxiv-sanity-lite（README 与 serve.py）：https://github.com/karpathy/arxiv-sanity-lite ；https://github.com/karpathy/arxiv-sanity-preserver
- [R44] TideDra/zotero-arxiv-daily（README 与 reranker/base.py）：https://github.com/TideDra/zotero-arxiv-daily ；https://github.com/TideDra/zotero-arxiv-daily/blob/main/src/zotero_arxiv_daily/reranker/base.py
- [R45] LLM 日报类：https://github.com/tatsu-lab/gpt_paper_assistant ；https://github.com/AutoLLM/ArxivDigest ；https://github.com/dw-dengwei/daily-arXiv-ai-enhanced ；https://github.com/OpenRaiser/PaperFlow （docs/feedback-loop.md）；https://github.com/JoeLeelyf/customize-arxiv-daily
- [R46] Scholar Inbox：https://arxiv.org/abs/2504.08385 ；https://arxiv.org/html/2504.08385v2 ；数据 https://github.com/avg-dev/scholar_inbox_datasets ；平台 https://www.scholar-inbox.com/ ；第三方 CLI https://github.com/mrshu/scholarinboxcli
- [R47] SPECTER：https://github.com/allenai/specter ；https://huggingface.co/allenai/specter
- [R48] SPECTER2：https://github.com/allenai/SPECTER2 ；https://huggingface.co/allenai/specter2 ；https://huggingface.co/allenai/specter2_base ；AI2 博客 https://allenai.org/blog/specter2-adapting-scientific-document-embeddings-to-multiple-fields-and-task-formats-c95686c06567
- [R49] SciRepEval：https://github.com/allenai/scirepeval ；https://arxiv.org/abs/2211.13308
- [R50] SciNCL：https://huggingface.co/malteos/scincl
- [R51] Semantic Scholar 相关开源：https://github.com/allenai/s2search ；https://github.com/allenai/S2AND ；https://github.com/allenai/S2APLER ；https://github.com/allenai/s2orc ；https://github.com/allenai/citeomatic ；https://github.com/allenai/s2_fos ；https://github.com/allenai/s2-folks ；https://github.com/allenai/papermage ；https://github.com/allenai/asta-paper-finder ；https://github.com/allenai/ai2-scholarqa-lib ；https://github.com/allenai/scidocs
- [R52] S2 Recommendations API：https://api.semanticscholar.org/recommendations/v1/swagger.json ；https://api.semanticscholar.org/api-docs/recommendations

**审稿匹配与互惠推荐**

- [R53] openreview/openreview-expertise：https://github.com/openreview/openreview-expertise
- [R54] openreview/openreview-matcher：https://github.com/openreview/openreview-matcher
- [R55] niharshah/peerreview4all：https://github.com/niharshah/peerreview4all
- [R56] acl-org/reviewer-paper-matching：https://github.com/acl-org/reviewer-paper-matching
- [R57] A Gold Standard Dataset for the Reviewer Assignment Problem：https://arxiv.org/abs/2303.16750
- [R58] 互惠推荐：https://github.com/m-ochi/recon ；https://github.com/kdevo/chaos-rrs ；https://github.com/CyberAgentAILab/FairReciprocalRecommendation ；https://github.com/CyberAgentAILab/mode ；https://github.com/RManLuo/MotifGNN ；https://github.com/AllminerLab/Code-for-KAERR-master ；https://github.com/BinFuPKU/ReciprocalRecommender ；https://github.com/ezyil/biDeepFM

**模型卡与包索引**

- [R59] Embedding 模型许可：https://huggingface.co/jinaai/jina-embeddings-v5-text-nano ；https://huggingface.co/thenlper/gte-large ；https://huggingface.co/Alibaba-NLP/gte-large-en-v1.5
- [R60] PyPI JSON：https://pypi.org/pypi/lightfm/json ；https://pypi.org/pypi/implicit/json ；https://pypi.org/pypi/vowpalwabbit/json ；https://pypi.org/pypi/cornac/json ；https://pypi.org/pypi/recbole/json ；https://pypi.org/pypi/recommenders/json

**仓库内既有文档**

- [R61] 论文获取类 GitHub 项目调研：[docs/research/github-similar-projects.md](../../archive-v1.md#docs-research-github-similar-projects-md)

**核验补充来源**（访问日期 2026-09-26）

- [R62] Kinney et al., *The Semantic Scholar Open Data Platform*（§3.4.5 Recent Paper Recommendations；§4.3 Recommendations）：https://arxiv.org/abs/2301.10140 ；https://arxiv.org/html/2301.10140
- [R63] ACL Anthology，Scholar Inbox（ACL 2025 System Demonstrations）：https://aclanthology.org/2025.acl-demo.30/ ；卷目录 https://aclanthology.org/volumes/2025.acl-demo/
- [R64] Semantic Scholar API 产品页（限速）：https://www.semanticscholar.org/product/api ；API License Agreement：https://www.semanticscholar.org/product/api/license
- [R65] 核验补充仓库：https://github.com/lenskit/lkpy ；https://pypi.org/pypi/lenskit/json ；https://github.com/online-ml/river （`river/bandit`、`river/reco` 目录）；https://pypi.org/pypi/river/json ；https://github.com/bluesky-social/feed-generator ；https://github.com/IsaacGemal/wikitok
- [R66] 多语言 embedding 模型卡：https://huggingface.co/Qwen/Qwen3-Embedding-0.6B ；https://huggingface.co/BAAI/bge-m3
- [R67] Vowpal Wabbit 9.11.x 发布说明：https://github.com/VowpalWabbit/vowpal_wabbit/releases/tag/9.11.4 ；https://github.com/VowpalWabbit/vowpal_wabbit/releases/tag/9.11.5 ；https://github.com/VowpalWabbit/vowpal_wabbit/releases/tag/9.11.6 ；https://pypi.org/pypi/vowpalwabbit/json ；Maven Central 元数据（续核验）https://repo1.maven.org/maven2/com/github/vowpalwabbit/vw-jni/maven-metadata.xml
- [R68] sqlite-vec 发布记录：https://github.com/asg017/sqlite-vec/releases/tag/v0.1.9 ；https://github.com/asg017/sqlite-vec/releases/tag/v0.1.10-alpha.1 ；https://github.com/asg017/sqlite-vec/releases/tag/v0.1.10-alpha.4
- [R69] x-algorithm 关键提交：2026-05-15 `e414c17` https://github.com/xai-org/x-algorithm/commit/e414c171ed68266341193330bc4864bf3f3534e3 ；2026-08-13 `47c1bcd`（README 删除"no hand-engineered features"表述）https://github.com/xai-org/x-algorithm/commit/47c1bcdadfe4911568fd6db4f8838b194325beab ；HEAD `4c5cfe8` https://github.com/xai-org/x-algorithm/tree/4c5cfe8f07f1c76d4f04277e803f20e6039f5191
- [R70] snap-research/GRID（续核验补充）：https://github.com/snap-research/GRID ；LICENSE 原文 https://github.com/snap-research/GRID/blob/main/LICENSE ；论文 https://arxiv.org/abs/2507.22224
- [R71] daffidwilde/matching（续核验补充）：https://github.com/daffidwilde/matching ；https://pypi.org/pypi/matching/json ；JOSS https://doi.org/10.21105/joss.02169
- [R72] Yambda-5B（续核验补充）：https://huggingface.co/datasets/yandex/yambda ；论文 https://arxiv.org/abs/2505.22238

---

## 核验记录

核验人：对抗式事实核验（Verify，opus5.5）。方法：逐条回到一手来源复读——GitHub 仓库元数据、提交、发布与源码用 `gh api`（只读）；论文用 arXiv API/HTML 与 ACL Anthology；模型卡用 Hugging Face API；包版本与 wheel 用 PyPI JSON；官方文档与条款页用 curl/WebFetch（带可识别 UA）。首轮核验时 WebSearch 会话配额已耗尽，未使用任何二手报道作依据。"核验日期"按 UTC 记为 2026-09-26。

**续核验（合并说明）**：首轮核验在写完本节后中断。续核验先检查了首轮留下的全部修改：正文与本表一致，引用编号无悬空，本节唯一，没有发现半截编辑。随后按"默认怀疑"原则独立复核了本表所列断言，逐条回到一手来源；x-algorithm 的 param.rs、author_cold_start.rs、scoring.rs、dpp.rs、README、phoenix/README 及提交历史全部重新读取。复核后首轮结论除 VW/Maven 一条外全部成立，该条已在下表更正。续核验新增的结论见表末"续核验"各行。续核验中途发现 /tmp 是多代理共享目录，其中文件可能被他人覆盖，此后临时文件改写到会话专属 scratchpad。此前取自 /tmp 的结果，要么在同一条命令内下载即解析，要么已用 WebFetch 或重新下载复核（S2 swagger、Scholar Inbox HTML 均已复核）。

| 断言 | 结论 | 依据来源 URL | 核验日期 |
|---|---|---|---|
| xai-org/x-algorithm 存在，Apache-2.0，33,426 star，2026-01-19 创建，首个提交 `aaa167b`（2026-01-20），HEAD `4c5cfe8`（2026-09-26），共 37 个提交，PR #88 为唯一 PR 合并 | 确认 | https://github.com/xai-org/x-algorithm ；https://github.com/xai-org/x-algorithm/commits/main | 2026-09-26 |
| 2026 版"去除了全部人工特征与大部分启发式" | 修正：首发 README 原文确认，但自 2026-08-13 `47c1bcd` 起 README 已删除该表述；现行管线仍有 SimClusters、作者衰减、站外折扣、新作者扶持等规则 | https://github.com/xai-org/x-algorithm/blob/aaa167b3de8a674587c53545a43c90eaad360010/README.md ；https://github.com/xai-org/x-algorithm/commit/47c1bcdadfe4911568fd6db4f8838b194325beab | 2026-09-26 |
| param.rs 默认权重（Favorite 0.5、Reply 5、互关回复加成 15、ShareViaCopyLink 20、NotInterested −43.2、Block −31.2、Mute −58.8、Report −234、NotDwelled −0.02 等）；负分偏移 `NEGATIVE_SCORES_OFFSET = 0.001` 与公式；作者衰减 `(1−floor)·decay^k+floor` | 确认 | https://github.com/xai-org/x-algorithm/blob/main/home-mixer/params/param.rs ；https://github.com/xai-org/x-algorithm/blob/main/xai-value-model/scoring.rs ；https://github.com/xai-org/x-algorithm/blob/main/xai-value-model/weights.rs | 2026-09-26 |
| DPP 重排：`q=exp(α·s/max)`、`α=θ/(2(1−θ))`、余弦核、增量 Cholesky 贪心、单测 θ=0.5 | 确认 | https://github.com/xai-org/x-algorithm/blob/main/vm-ranker/dpp.rs | 2026-09-26 |
| 新作者冷启动："作者曝光 <1000、粉丝 ≤1000、48 小时内，提升到第 15–16 位"；Thompson sampling Beta(0.75, 49.25) 默认关闭、TopK=2 | 修正：阈值作用于候选帖自身的 `view_count_on_home`（README 写作"作者曝光"，与代码不一致）；另需非回复/非转推、名次低于 0.85×非零分候选数；每次请求至多 1 条，目标名次取自 [15,16)（0 起算）；TS 参数确认 | https://github.com/xai-org/x-algorithm/blob/main/home-mixer/scorers/author_cold_start.rs ；https://github.com/xai-org/x-algorithm/blob/main/home-mixer/params/param.rs | 2026-09-26 |
| Phoenix：two-tower、语义 ID 6×256、`use_user_embedding=False`、candidate isolation、nano 单卡预设、AdamW/Muon；README 列 24 类行为、17 个 pre-scoring filter（含 48 小时 AgeFilter）、六类 stage | 确认 | https://github.com/xai-org/x-algorithm/blob/main/phoenix/README.md ；https://github.com/xai-org/x-algorithm | 2026-09-26 |
| 互关回复加权：2026-07-10 A/B（5/10/15/20）、07-13 上线 20、07-24 调为 15；互关 dwell 加成未上线 | 确认 | https://github.com/xai-org/x-algorithm/blob/main/docs/BIDIRECTIONAL_BOOST_CHANGE.md | 2026-09-26 |
| 2026-05-15 更新：Git LFS 分发 mini Phoenix、端到端推理、广告混排（原标"二手报道 ⚠ 未核验"） | 修正：按提交 `e414c17` 文件清单确认，并补充同批新增 `grox/` 分类器 | https://github.com/xai-org/x-algorithm/commit/e414c171ed68266341193330bc4864bf3f3534e3 | 2026-09-26 |
| twitter/the-algorithm：73,945 star、AGPL-3.0、`c54bec0`（2025-09-03）+65,319/−3,195（API 返回 300 个文件）、排序前拉取"~6000 features"、search-index 约 50%；the-algorithm-ml heavy ranker 2023-04-05 权重（reply_engaged_by_author 75、report −369 等） | 确认；措辞修正："约 6000 个人工特征"改为"约 6000 个特征"（原文未称人工） | https://github.com/twitter/the-algorithm/commit/c54bec0d4e029fe34926ef3258a86ccacc0d0182 ；https://github.com/twitter/the-algorithm/blob/main/home-mixer/README.md ；https://github.com/twitter/the-algorithm-ml/blob/main/projects/home/recap/README.md | 2026-09-26 |
| OneRec（2502.18965）观看时长 +1.6%；OneRec 技术报告（2506.13695）FLOPs 10×、MFU 23.7%/28.8%、OPEX 10.6%、25% QPS、停留时长 +0.54%/+1.24% | 确认 | https://arxiv.org/abs/2502.18965 ；https://arxiv.org/abs/2506.13695 | 2026-09-26 |
| OpenOneRec：RecIF-Bench"20 万用户、1 亿交互"；无 LICENSE 文件、README 声明 Apache-2.0、账号类型 User；OneRec-8B 8.39B 参数、Apache-2.0、"下载 9.1K" | 修正：技术报告摘要称公开训练集为 16 万用户/9600 万交互，与 README 不一致，已并列标注；下载量为累计值（近 30 天 623）；其余确认 | https://github.com/Kuaishou-OneRec/OpenOneRec ；https://arxiv.org/abs/2512.24762 ；https://huggingface.co/OpenOneRec/OneRec-8B | 2026-09-26 |
| HSTU（2402.17152，ICML'24）：1.5 万亿参数、NDCG 最高 +65.8%、8192 长度快 5.3–15.2×、线上 A/B +12.4%；仓库 ML-1M HR@10 0.3294 vs SASRec 0.2853、单卡 ≥24GB HBM | 确认 | https://arxiv.org/abs/2402.17152 ；https://github.com/meta-recsys/generative-recommenders | 2026-09-26 |
| 字节 Monolith 已归档、LICENSE 原文为 Apache-2.0、Bazel 3.1.0/仅 Linux、落地 BytePlus Recommend；HLLM、primus 已归档；PERSIA README 声明"因公司重组不再维护" | 确认 | https://github.com/bytedance/monolith ；https://arxiv.org/abs/2209.07663 ；https://github.com/bytedance/HLLM ；https://github.com/bytedance/primus ；https://github.com/PersiaML/PERSIA | 2026-09-26 |
| Scholar Inbox 配方与规模：GTE-large + PCA 256、每用户加权 LR、5k 随机负样本、(C,V,S)=(0.1,0.8,5.0)、每次评分重训、23k 注册/8k（35%）月活、14.3k 用户 80 万评分、3M 论文、NGT、表 2 数值；数据集 CC BY-NC-ND 4.0（774k 显式 + 556k 隐式、2,538 条高亮） | 确认 | https://arxiv.org/html/2504.08385v2 ；https://github.com/avg-dev/scholar_inbox_datasets | 2026-09-26 |
| Scholar Inbox ACL Demo"录用情况 ⚠ 未核验" | 修正：已收录 ACL 2025 System Demonstrations，Anthology ID 2025.acl-demo.30 | https://aclanthology.org/2025.acl-demo.30/ | 2026-09-26 |
| "Semantic Scholar feed 推荐器的具体算法未公开" | 修正：S2 平台论文 §3.4.5 公开了配方（TF-IDF 与 SPECTER 两个线性 SVM、随机负样本低权重、FAISS 取近 60 天约 100 万篇、质心近邻约 500 篇、两模型分数平均） | https://arxiv.org/abs/2301.10140 | 2026-09-26 |
| SPECTER2：6M 三元组；模型卡 SciRepEval 平均 71.1、MDCR (38.4, 33.0)，SciNCL 68.8/(32.6, 27.3) 等；AI2 博客（2023-11-27）称 10 倍于 SPECTER、23 个学科、SPECTER 支撑 research feeds；SciNCL MIT、109.9M 参数 | 确认；下载量口径修正为累计；`allenai/specter2` adapter 卡片无 license 字段（base 为 Apache-2.0） | https://huggingface.co/allenai/specter2_base ；https://huggingface.co/allenai/specter2 ；https://allenai.org/blog/specter2-adapting-scientific-document-embeddings-to-multiple-fields-and-task-formats-c95686c06567 ；https://huggingface.co/malteos/scincl | 2026-09-26 |
| openreview-expertise 对比表（SPECTER2+SciNCL 0.21/0.91/0.65 等）与 0.8/0.2、0.5/0.5 集成；金标准（2303.16750）477 条自评/58 人、易例误排 12–30%、难例 36–43%、全文时 TF-IDF 追平 SPECTER2、通用 LLM 落后 | 确认 | https://github.com/openreview/openreview-expertise ；https://arxiv.org/abs/2303.16750 | 2026-09-26 |
| openreview-matcher 无 LICENSE 文件、setup.py 声明 MIT、依赖 ortools 与 gurobipy、含 MinMax/FairFlow/FairIR/Randomized/FairSequence/PerturbedMaximization 求解器 | 确认 | https://github.com/openreview/openreview-matcher | 2026-09-26 |
| PerturbedMaximization（2310.05995）"防操纵动机" | 修正：论文为 NeurIPS 2023 spotlight，定位为兼顾防操纵、评估替代分配、审稿人多样性与匿名性的通用随机化方法 | https://arxiv.org/abs/2310.05995 | 2026-09-26 |
| 互惠推荐：RECON `2/(1/s_xy+1/s_yx)`；CyberAgent 公平互惠（RecSys'24）与 Nash 社会福利工作论文；MODE（2608.01731，RecSys'26，Python 3.12 + uv）；chaos-rrs 为硕士论文配套、非生产用 | 确认 | https://github.com/m-ochi/recon/blob/master/recon.py ；https://github.com/CyberAgentAILab/FairReciprocalRecommendation ；https://arxiv.org/abs/2608.01731 ；https://github.com/kdevo/chaos-rrs | 2026-09-26 |
| Gorse 9,836 star、Apache-2.0、v0.5.11（2026-07-14）、排序 none/fm/llm、MF 用 BPR/eALS、`optimize_period` 默认 180m、`optimize_trials` 默认 10；Metarank 近 12 月 57 个提交（Scala Steward 24）、0.8.1（2026-09-07） | 确认 | https://github.com/gorse-io/gorse/releases ；https://gorse.io/docs/concepts/ranking.html ；https://gorse.io/docs/concepts/recommenders/collaborative.html ；https://github.com/metarank/metarank | 2026-09-26 |
| LightFM issue #709"Can't install on Python 3.12"自 2024-05-17 未关闭、PyPI 仅 1.17 sdist（2023-03-20）；implicit v0.7.3（2026-05-08）cp39–cp314 wheel | 确认 | https://github.com/lyst/lightfm/issues/709 ；https://pypi.org/pypi/lightfm/json ；https://pypi.org/pypi/implicit/json | 2026-09-26 |
| VW"9.10.0 后停发一年半，2026-03 恢复 9.11.x，2026-09 恢复向 PyPI/npm/NuGet/Maven 发布" | 修正：PyPI 于 2026-03-07 已上传 9.11.2；2026-09 的变化是 9.11.4 安全补丁（5 个堆越界公告）与 9.11.5/9.11.6 自动发布，9.11.6 为 pip/NuGet 首个修复版。续核验再修正首轮"说明未提及 Maven"的判断：9.11.5/9.11.6 说明写明 Java 制品改经 Sonatype Central Portal 发布（#4958，OSSRH 已于 2025-06-30 关停）；但 Maven Central 上 `vw-jni` 最新仍为 9.11.1，无修复版 | https://github.com/VowpalWabbit/vowpal_wabbit/releases/tag/9.11.5 ；https://github.com/VowpalWabbit/vowpal_wabbit/releases/tag/9.11.6 ；https://pypi.org/pypi/vowpalwabbit/json ；https://repo1.maven.org/maven2/com/github/vowpalwabbit/vw-jni/maven-metadata.xml | 2026-09-26 |
| Azure Personalizer：2023-09-20 起不可新建、2026-08-25 退役、建议迁移 microsoft/learning-loop；每次 Rank 建议 ≲50 个动作、每天 ≳1000 个事件 | 确认（页面现已归档至 previous-versions）。续核验交叉核对：WebSearch 摘要与 Azure Updates 条目 id 都写着原定的"2026-10-01"，但该条目经 Microsoft 发布通信 API 取回的现行标题与正文均为"August 25, 2026"（availabilities：Retirement 2026-August），Learn 的 what-is 与 whats-new 页也是 25 August 2026。以 2026-08-25 为准，正文已加注 | https://learn.microsoft.com/en-us/azure/ai-services/personalizer/what-is-personalizer ；https://learn.microsoft.com/en-us/azure/ai-services/personalizer/whats-new ；https://www.microsoft.com/releasecommunications/api/v2/azure/ai-services-personalizer-will-be-retired-on-1-october-2026 | 2026-09-26 |
| S2 Recommendations API：`POST /papers/`（positive/negativePaperIds）、`GET /papers/forpaper/{paper_id}?from=recent\|all-cs`、limit 默认 100/上限 500；"ToS/限速 ⚠" | 确认参数；核验补充限速（匿名共享 1000 req/s、key 1 RPS）与许可要点（署名、禁止 repackage/distribute API、可随时终止）；缓存与再展示边界仍 ⚠ 未核验 | https://api.semanticscholar.org/recommendations/v1/swagger.json ；https://www.semanticscholar.org/product/api ；https://www.semanticscholar.org/product/api/license | 2026-09-26 |
| zotero-arxiv-daily：AGPL-3.0、5,991 star、按加入顺序衰减 `1/(1+log10(i+1))`、默认 jina-embeddings-v5-text-nano（CC-BY-NC-4.0） | 修正：默认模型实为 `jinaai/jina-embeddings-v5-text-nano-retrieval`，许可同为 CC-BY-NC-4.0；其余确认 | https://github.com/TideDra/zotero-arxiv-daily/blob/main/config/base.yaml ；https://github.com/TideDra/zotero-arxiv-daily/blob/main/src/zotero_arxiv_daily/reranker/base.py ；https://huggingface.co/jinaai/jina-embeddings-v5-text-nano-retrieval | 2026-09-26 |
| arxiv-sanity-lite：`LinearSVC(class_weight='balanced')`、默认 C=0.01、展示正向前 40/负向后 20 权重词、Nanode 1GB（$5/月）约 3 万篇 | 确认 | https://github.com/karpathy/arxiv-sanity-lite/blob/master/serve.py ；https://github.com/karpathy/arxiv-sanity-lite | 2026-09-26 |
| Qdrant：`average_vector`（avg_pos + avg_pos − avg_neg）、`best_score`（v1.6.0+，耗时随样例线性增长，可只用负样例）、`sum_scores`、Discovery（v1.7）；Vespa streaming：约 45 字节/文档、`g=userid`、不建议与 indexed 混部；sqlite-vec"ANN 能力 ⚠ 未核验" | Qdrant/Vespa 确认；sqlite-vec 修正为已核验：稳定版 v0.1.9 无 ANN 索引，ANN 仅见 v0.1.10-alpha 预发布 | https://qdrant.tech/documentation/concepts/explore/ ；https://docs.vespa.ai/en/streaming-search.html ；https://github.com/asg017/sqlite-vec/releases | 2026-09-26 |
| allenai/scidocs 许可"NOASSERTION" | 修正：LICENSE 原文为 CC BY 4.0（S2AND 同为 CC BY 4.0，确认） | https://github.com/allenai/scidocs ；https://github.com/allenai/S2AND | 2026-09-26 |
| 全文约 90 个仓库的 star/fork/license/最后提交/归档状态快照 | 确认：逐一复读，与文中一致（qdrant 34,834→34,836 属当日正常波动）。续核验又复读约 80 个仓库，star 仅有 ±1–3 的波动（如 x-algorithm 33,427、zotero-arxiv-daily 5,992、qdrant 34,837），正文保留首轮快照；按 1.2 节"默认分支最后提交"口径，修正 ArxivDigest（2023-07-13，原填的是 pushed 日期 2024-05）与 allenai/specter（2023-05-10）两处活跃度；2.7 表列名为"最后活动"，沿用 pushed 日期，不改；未发现不存在的仓库、论文或产品，故无删除项 | `gh api repos/{owner}/{repo}`、`/commits`、`/releases`（清单见第 5 节） | 2026-09-26 |
| 覆盖缺口：离线评估/在线学习库、可订阅 feed 架构、刷卡式 feed 开源实现、多语言 embedding | 核验补充：LensKit、River、Bluesky feed-generator、刷卡类仓库检索结论（见 2.1 补充表），以及 Qwen3-Embedding-0.6B / BGE-M3（见 3.1 第 6 条） | https://github.com/lenskit/lkpy ；https://github.com/online-ml/river ；https://github.com/bluesky-social/feed-generator ；https://github.com/IsaacGemal/wikitok ；https://huggingface.co/Qwen/Qwen3-Embedding-0.6B ；https://huggingface.co/BAAI/bge-m3 | 2026-09-26 |
| 续核验：x-algorithm 细节——param.rs 全部权重与冷启动参数（含 `EnableViewerColdStart` 默认 true）、`apply_cold_start` 的资格条件与"每次请求至多 1 条"、目标名次 `random_range(15..16)`、offset/作者衰减/DPP 公式、README 的 24 类行为与 17 个 pre-scoring filter、37 个提交与 PR #88、`47c1bcd` 删除 hand-engineered 表述、`e414c17` 为 18,263/−926 行 187 个文件（含 59 个 `grox/` 文件）、语言字节数以 Rust/Python/Scala/Java 为主 | 确认（独立复核首轮结论） | https://github.com/xai-org/x-algorithm/blob/4c5cfe8f07f1c76d4f04277e803f20e6039f5191/home-mixer/scorers/author_cold_start.rs ；https://github.com/xai-org/x-algorithm/blob/4c5cfe8f07f1c76d4f04277e803f20e6039f5191/home-mixer/params/param.rs ；https://github.com/xai-org/x-algorithm/commits/main | 2026-09-26 |
| 续核验：论文存在性与数字——OneRec 1.6%；技术报告的 10×/23.7%/28.8%/10.6%/25%/0.54%/1.24%；OpenOneRec v2 摘要"9600 万交互、16 万用户"；HSTU 65.8%/5.3–15.2×/12.4%/1.5 万亿；金标准 477/58/12–30%/36–43%；SciRepEval"24 任务、8 个新任务、>2 分"；MiniOneRec"Qwen 0.5B–7B、RQ-VAE"；MODE"RecSys2026"；PerturbedMaximization"neurips 2023 spotlight" | 确认（arXiv API 摘要与 comment 字段逐条比对；16 篇论文全部存在，标题、日期与正文一致） | https://export.arxiv.org/api/query?id_list=2502.18965,2506.13695,2512.24762,2510.24431,2402.17152,2504.08385,2303.16750,2310.05995,2608.01731,2202.06671,2211.13308,2209.07663,2409.12740,2301.10140,2004.07180,2308.03281 | 2026-09-26 |
| 续核验：Scholar Inbox 每用户模型细节 | 确认并补充原式：用户平均 78 条正评分；n_P·w_P = S·(n_N·w_N + n_R·w_R)；w̃_N、w̃_R 由 V 分配；V=0.8 的选取理由与 S>5 时召回下降（已补入 2.6 表） | https://arxiv.org/html/2504.08385v2 | 2026-09-26 |
| 续核验：S2 平台论文"近 60 天"表述的时效 | 确认并补充：v2（2025-04-25）的 §3.4.5 与 §4.3 仍写近 60 天、约 100 万篇、约 500 篇、两模型取平均；正文日期已补为 v1/v2 | https://arxiv.org/html/2301.10140 | 2026-09-26 |
| 续核验：S2 API 限速与许可、Recommendations swagger 参数 | 确认（WebFetch 独立复读：匿名共享 1000 req/s、key 入门 1 RPS；许可 2023-05-17 版要求署名、禁止 repackage/distribute API、可随时终止，未明文约定缓存，缓存边界维持 ⚠ 未核验；swagger 的 limit 默认 100/上限 500，from 取 recent 或 all-cs） | https://www.semanticscholar.org/product/api ；https://www.semanticscholar.org/product/api/license ；https://api.semanticscholar.org/recommendations/v1/swagger.json | 2026-09-26 |
| 续核验：PaperFlow"输入含 Google Scholar 页面" | 确认并收紧表述：冷启动 agent 在服务端抓取 Google Scholar 个人主页（`_fetch_google_scholar_profile_pages`），带"轻量回退" | https://github.com/OpenRaiser/PaperFlow/blob/main/agents/coldstart-agent/main.py | 2026-09-26 |
| 续核验：Gorse 排序类型 none/fm/llm 与 LLM 重排配置、MF 的 BPR/eALS 及默认值；Metarank 57 个提交的作者分布（Roman Grebennikov 以两种署名计 24 次）；VW CB 教程；Qdrant/Vespa 能力；SPECTER2/SciNCL 模型卡；openreview-expertise 表与参数；arxiv-sanity-lite 的 C=0.01 与 40/20 权重词；zotero-arxiv-daily 衰减式与默认模型；OpenOneRec README；HSTU README（SASRec 行确为 sampled softmax 版） | 确认 | https://gorse.io/docs/concepts/ranking.html ；https://github.com/metarank/metarank ；https://qdrant.tech/documentation/concepts/explore/ ；https://docs.vespa.ai/en/streaming-search.html ；https://huggingface.co/allenai/specter2_base ；https://github.com/openreview/openreview-expertise ；https://github.com/meta-recsys/generative-recommenders | 2026-09-26 |
| 续核验覆盖缺口：语义 ID 框架的许可陷阱、带"自然/推荐"来源标记的反馈数据、双边稳定匹配库 | 核验补充：snap-research/GRID（745 star，LICENSE 原文为仅限非商业研究，GitHub 识别为 Other）、Yambda-5B（Apache-2.0，`is_organic`，含撤销事件）、daffidwilde/matching（MIT，SM/HR/SA/SR）；分别补入 2.1 补充表、2.9 表 C、3.1 第 15/19 条、3.2 数据模型与 4 节第 6 条 | https://github.com/snap-research/GRID/blob/main/LICENSE ；https://arxiv.org/abs/2507.22224 ；https://huggingface.co/datasets/yandex/yambda ；https://arxiv.org/abs/2505.22238 ；https://github.com/daffidwilde/matching | 2026-09-26 |
| 续核验：仍未核验项 | 未核验（保留 ⚠）：Metarank 商业公司运营状态（续核验时 metarank.ai 主页两次连接超时，docs.metarank.ai 返回 200，不足以判断公司是否仍在运营）；Scholar Inbox 具体 GTE checkpoint（论文只写 GTE_large 并引 Li et al. 2023）；S2 推荐结果在多用户平台的缓存与再展示边界；Gorse 多用户私有反馈隔离保证；多语言 embedding 在学术推荐上的效果；embedding 回填耗时估算 | — | 2026-09-26 |

**核验过程记录（可复现）**：`gh api repos/{owner}/{repo}`（约 90 个仓库）、`gh api repos/xai-org/x-algorithm/contents/{path}?ref=4c5cfe8`（param.rs、author_cold_start.rs、scoring.rs、weights.rs、dpp.rs、BIDIRECTIONAL_BOOST_CHANGE.md、README.md、phoenix/README.md）、`gh api repos/xai-org/x-algorithm/commits/{e414c17,0bfc279,47c1bcd,aaa167b}`、`gh search code view_count_on_home repo:xai-org/x-algorithm`、`gh api .../commits?since=2025-09-26T00:00:00Z`（Metarank、Cornac、implicit、tensorflow/recommenders 等）；arXiv API `export.arxiv.org/api/query?id_list=2512.24762,2510.24431,2303.16750,2310.05995,2608.01731,2202.06671,2211.13308,2209.07663,2409.12740,2301.10140`；arXiv HTML `2504.08385v2`、`2301.10140`；ACL Anthology 卷 `2025.acl-demo`；HF API `api/models/{id}?expand[]=downloadsAllTime&expand[]=cardData`；PyPI JSON（lightfm、implicit、vowpalwabbit、cornac、river、lenskit）；官方页面 curl（qdrant explore、vespa streaming-search、semanticscholar product/api 与 api/license、Microsoft Learn Personalizer）；`gh search repos`："paper tinder"、"arxiv swipe"、"arxiv tiktok"、"tiktok papers"、"papers swipe recommend"、"wikitok"、"scroll arxiv"。

**续核验过程记录（可复现，2026-09-26 UTC）**：
- `gh api`：复读约 80 个仓库的 repos 元数据、`commits?per_page=1`（默认分支最后提交）、`commits?since=2025-09-26T00:00:00Z`（Metarank 按作者计数；另有 Cornac、implicit、tensorflow/recommenders、RecBole、LibRecommender、openreview-expertise/matcher）、`releases`（VW、Gorse、Metarank、Cornac、TorchRec、implicit、Recommenders、RecBole、HugeCTR、Transformers4Rec、Merlin、sqlite-vec）、`releases/tags/9.11.{4,5,6}` 正文、`contents/{path}?ref=4c5cfe8`、`commits/e414c17…`、`users/Kuaishou-OneRec`、`repos/.../license`（scidocs、S2AND、GRID、daily-arXiv-ai-enhanced、pgvector、Scholar Inbox 数据集）、`search/code?q=scholar.google+repo:OpenRaiser/PaperFlow`。
- 其他接口与页面：arXiv API（16 篇论文，另加 2507.22224、2505.22238）；arXiv HTML `2504.08385v2`（按 math alttext 取原式）与 `2301.10140`（v2）；ACL Anthology `2025.acl-demo.30`；HF API `api/models/{id}?expand[]=downloadsAllTime…` 与 `api/datasets/yandex/yambda`；PyPI JSON（vowpalwabbit、implicit、lightfm、cornac、river、lenskit、recbole、recommenders、matching）；Maven Central `repo1.maven.org/.../vw-jni/maven-metadata.xml` 与 `search.maven.org`（后者索引滞后，显示 9.9.0，以 repo1 元数据为准）；Microsoft Learn 的 what-is 与 whats-new 页；Microsoft 发布通信 API `releasecommunications/api/v2/azure/{id}`；WebFetch 读取 S2 product/api、api/license、recommendations swagger、Qdrant explore、Vespa streaming-search 与 news-5 教程、Gorse ranking/collaborative 文档、VW CB 教程、AI2 SPECTER2 博客。
- WebSearch：1 次，检索式为 `Azure AI Personalizer retirement date 2026 retire`（限 learn.microsoft.com、azure.microsoft.com、techcommunity.microsoft.com），仅用于定位公告，结论以一手 API 记录为准。
- 覆盖缺口检索：`gh api repos/{snap-research/GRID, daffidwilde/matching, facebookresearch/dlrm, google-research/recsim_ng}`；`gh search repos "scholar inbox"`（确认 avg-dev 组织下只有数据仓库公开，平台代码不公开）。
