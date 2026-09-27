---
title: 检索、路由与 TSRG 索引（查询 / 最新 / 筛选 / 多来源 / 组合）
status: draft
owner: opus5.5-design
updated: 2026-09-27
---

# 04 · 检索、路由与 TSRG 索引（查询 / 最新 / 筛选 / 多来源 / 组合）

> **定位**：本文是用户需求 R2（检索算法、多用户后台、图/树结构、快速查找、并行查找、路由、准确率与稳定性）的主承接文档。它定义 Query AST、意图与解析、TSRG 的结构与算法、路由器、健全放宽、并行联邦执行器、本地检索索引、新鲜度调度、Percolator 和出站稳定性。按简报 §9，这些是 04 的接口，05、06 引用。
>
> **上游约束**：[v2 设计决策简报](00-design-brief.md)（B-01…B-06、P-01…P-09、§5 术语、§6.2 子系统裁决、§8 默认假设）。与简报不一致或需细化之处集中写在 §19"异议与备选"，未静默偏离。
>
> **证据口径**：事实引用 `docs/survey/` 下经 2026-09-26 对抗式核验的调研，写法如"RT §3.5.3"，代号见 [调研综合 §1.1](../../survey/00-survey-synthesis.md)。调研未覆盖、由本文在 2026-09-27 补查的一手来源，在正文括注"（一手来源，2026-09-27 查阅）"，并列入 §21.3。标注约定：
> - `⚠`：调研中未核验的事实，沿用其标注；
> - `[估算]`：本文按明示公式计算；
> - `[判断]`：工程判断或设计参数初值，须在实现期压测或实验校准；
> - `（示意数值）`：只为演示算法，不是实测数据。
>
> 文中代码块均为**设计伪代码**（Python 风格；DDL 标"设计伪代码 DDL"），不是接口冻结。DDL 定稿归 [05](05-data-platform.md)，本文 DDL 只表达 04 对表结构的需求。
>
> **配图**：
> - [v2-04-tsrg.svg](../../diagrams/v2-04-tsrg.svg)：TSRG 结构与四种用途；
> - [v2-05-query-execution.svg](../../diagrams/v2-05-query-execution.svg)：从 AST 到并行执行与合并。

**阅读指引**（任务书内容要求 ①–⑬ → 本文章节）

| 要求 | 章节 | 要求 | 章节 |
|---|---|---|---|
| ① Query AST 规范 | §3 | ⑧ 本地索引 | §9 |
| ② 五类查询端到端示例 | §10 | ⑨ 新鲜度调度 | §11 |
| ③ 意图与解析流水线 | §4 | ⑩ Percolator | §12 |
| ④ TSRG 完整规格 | §5 | ⑪ 稳定性 | §13 |
| ⑤ 路由算法 | §6 | ⑫ 准确率与性能 | §14 |
| ⑥ 健全放宽 | §7 | ⑬ 多用户 | §15 |
| ⑦ 并行联邦执行器 | §8 | 五要素：功能说明 §1；实现方案 §2–§15；测试方法与测试类型 §16；验收 §17 | §1、§2–§15、§16、§17 |

---

## 0. 结论速览

1. **总体形态**：本文把 R2 落成三件东西——一棵树加一张图（TSRG），一种查询语言（Query AST），一条并行流水线（联邦执行器）。订阅、最新论文、卡片流只读本地语料（P-01）。即席查询也先查本地，按 §6.3 的量化判据判定覆盖不足时，才在查询时联邦到远端；查询被硬过滤限定在已完整收割的 venue 或 arXiv 类目内时，按"范围完整性"直接判为本地完整，不联邦（§6.3）。
2. **Query AST**：
   - 硬谓词 `where` 与软打分 `rank` 分离。`where` 包含布尔、字段、短语、邻近、ID、分面、区间、引文关系、个人谓词、频道引用与集合运算；`rank` 包含相关性、语义、时间、被引、个性化。
   - "来源限定"区分两种含义：`src:` 是作品来源谓词，`via:` 是执行约束。
   - 缺失值用 Kleene 三值逻辑。v1 订阅 DSL 可以逐字段映射，映射后在 closed-world 兼容模式下与 v1 语义逐条等价（§3.8）。
3. **意图与解析**：五意图为 LOOKUP、SEARCH、SIMILAR、LATEST、EXPAND。简报 §6.2-1 规定四意图，EXPAND 是本文按 01 §16-5 的授权增设的第五意图，理由见 §19-13。解析分四步，规则快路径约 20 ms 出结构并投机执行本地首屏。LLM 只作可选的异步增强，不阻塞首屏（P-07）。实体链接只链到库内 ID，解析结果以可编辑筛选条交给用户。即席检索中，未加引号、前缀或算子的裸词是**软检索文本**（`rank.relevance.text`），驱动 BM25 与稠密召回，不作硬谓词；频道与按非相关性键排序时，裸词才编译为硬 AND 门（§3.2）。
4. **TSRG**：
   - 节点：OpenAlex Topics 骨架（4/26/252/4,516）、默认约 3.8 万个学科原生叶子（MSC2020 为默认不加载的可选插件，R2-22）、Venue、≤50 个 Source 端点、能力。
   - 边权 `route_stat = (cov, lag, λ, η, uniq, fidelity)`；端点另带成本、礼貌、健康、预算四类属性。
   - PG 表是真值；路由读只读内存快照（约 45–55 MB，为叶子建质心时约 65–140 MB [估算]，§5.6），计算在毫秒级。
   - 同一张图服务四件事：查询路由、收割调度、兴趣挂点、论文→读者反向路由。
5. **路由**：
   - 主题后验 P(t|q) 由三路证据融合：显式过滤、质心分类器、本地命中直方图。
   - 目标函数是"覆盖素描"上的概率覆盖函数，单调次模。
   - 求解用"比值贪心 + 最佳单源取大者"。可证下界是 (1−1/e)/2 ≈ 0.316；Tang 等（2021）证明至少 0.405；上界 0.42945（Kulik 等 2021）。边际增益过小的端点在选定后按加入次序**事后剪枝**，损失有加性上界（§6.7）。
   - 候选 ≤10 且枚举规模 2ⁿ·K·P ≤ 2²⁰ 时在线精确枚举（掩码模式压缩后在乘积域逐层倍增，不用超越函数）；超出规模闸时用贪心加兜底；离线用"≤3 元种子部分枚举"取得 (1−1/e)，并做全枚举校验（§6.4、§19-16）。
   - 放宽先于选源：候选端点先做健全放宽，剔除无界者，再按子查询数计成本；单项成本已超预算的端点在选源前剔除，这是预算贪心近似界成立的前提（§6.6）。
   - 检索有效率 η 按"端点 × 节点"估计，观测口径为"top-k 中已知被该端点收录的作品，该端点取回了多少"，与同时被选的其他端点无关（§5.3）。η 后验按 05 落在聚合区 `evt.agg_route_eta`，检索服务每日载入。
   - 探索用 Thompson sampling，日志足够后升级为 GBDT pairwise 路由器；新源用 LLM 零样本先验冷启动。
   - 路由的全部输入（P(t|q) 用的首屏命中、确定命中数 `n_local_T`、η 的观测集合）都取共享层、非个性化的本地召回，不经个人谓词、个性化挂点与私有列表；GBDT 的训练集经聚合闸抽取（R2-40、HC-01，§6.2、§6.9）。
6. **健全放宽**：
   - 先化为 NNF，再把不支持的文字替换为 true（与"按极性替换"等价），保证 P ⇒ P_s。
   - OR 拆分与 DNF 展开属于等价改写。语义替身和跨分类转译都是近似，结果中显式标注。
   - 本地残差按源对齐分析器、三值求值；"远端命中、本地拒绝"逐源计数并告警。
   - 本文对调研中的放宽规则做了三处更正：邻近退化为短语不健全，应退化为 AND；负文字不能做字段泛化或短语弱化；跨分类体系转译不是健全放宽（§7.4、§19-3）。
7. **执行器**：
   - fan-out 带截止时间（总 3 s），流式合并；部分失败时标注缺源并给出完整性报告。
   - 同能力替补链只在不同主机之间对冲，额外负载 ≤5%。
   - 先在各列表内按 `cluster_id` 折叠，再做 RRF（k=60），再用 cross-encoder 重排。top-100 是上限：纯 CPU 的 T1 从小模型 int8、top-50 起步，超预算先发 RRF 结果，重排结果以 `upgrade` 补发（R2-39，§8.7）。
8. **本地索引**：
   - 词法两件：pg_textsearch 做 BM25 排序，PG 原生 tsvector/GIN 求布尔与短语谓词。
   - 稠密：`halfvec` HNSW 加 iterative scan。索引维度随 Q7 的模型而定：支持 MRL 截短的模型（如 Qwen3-Embedding）建 256 维索引并用全维精排；不支持的（gte-large、SPECTER2）用全维索引，或经评测证明无损后再降维（§9.3、§19-15）。
   - 分面：Roaring 位图给出精确候选基数，用于选择率规划；|C| ≤ 2 万时精确扫描。各 API 进程的位图按入库水位增量同步，水位之后的尾部用 SQL 补查，新作品不因位图滞后而漏检（§9.4）。
   - Roaring 已见集合；图查询用 PG 邻接表 ≤2 跳并做枢纽剪枝，夜间导出 CSR 批算。
9. **新鲜度**：频道编译为带引用计数的 WatchKey。日历型源按发布窗轮询；连续型源用 Gamma-Poisson 估计 λ̂，在礼貌预算下按"平方根注水"分配轮询频率，f ∝ √(wλ/c)（§11.4 推导）。
10. **Percolator**：输入是出箱主题 `corpus.change` 上的新作品，以及新增版本或匹配字段变更的已有作品（R2-07、R2-35）。三路匹配：节点倒排、质心批量点积、锚点倒排上的 AST 谓词求值。三路的候选生成算法都由 04 定义，执行节奏分两档：频道命中是近线微批，直接写入 FeedInbox；节点与质心两路按日批执行，候选读者交给 06 在"每用户日预算 + 资格集合的曝光下限"约束下分配（R2-41，06 §11.3）。日预算分配需要当日全部供给，所以不宜切成 10 分钟微批，这与 02 P11、06 §8 的夜间反向推送一致（§12.1、§19-14）。1 万用户、每日 3 万篇新论文的规模，在 CPU 批处理下可行（§12.4）。
11. **稳定性**：所有平台侧出站请求都经过出站网关，由它执行以下机制：
    - robots 先行闸；
    - 响应头驱动的配额账本；
    - AIMD（只降不超书面限额）；
    - 重试预算（≤3 次/请求，≤10%）；
    - 按"源 × 端点"熔断，含不自动恢复的 POLICY 态（robots 与 TDM 漂移立即进入，ToS 哈希变化先给 7 天宽限，R2-15）；
    - 交互、收割、enrich 三道舱壁；
    - 应用层 TTL 缓存，TTL 与 λ̂ 挂钩。
12. **准确率与性能**：
    - 路由评测看"对照全源穷举的召回保持率与成本比"；
    - 检索评测用 LitSearch、SciRepEval 与分学科金标（每学科 ≥200 条）；
    - 系统评测看新鲜度滞后和 p50/p95/p99；
    - 升级触发条件写死在 §14.4。

---

## 1. 功能说明

### 1.1 承接的需求

用户需求 R2 已由 [01](01-vision-and-requirements.md) 登记为下列 FR 与 NFR（01 草稿，2026-09-27；最终编号以 01 与 09 为准）。对照如下：

| 需求 | 要点（按 01 的登记） | 本文承接 |
|---|---|---|
| FR-34 | Query AST 与意图路由；v1 订阅与 preset 无损转换；规范 AST 兼作缓存键与复现凭据 | §3、§4 |
| FR-35 | 查询论文：本地混合检索、RRF、CE 重排、按 `cluster_id` 折叠、标注来源与数据时点 | §8、§9、§10.1 |
| FR-36 | 最新论文：只读本地语料；新鲜度阶梯标注；显示数据时点 | §10.2、§11 |
| FR-37 | 筛选：主题（含原生叶子）、venue、来源、日期窗、OA、评审状态、类型、语言、已读；按选择率规划；筛选条可编辑、可存为频道 | §3.3、§4.4、§9.4–9.6、§10.3 |
| FR-38 | 多来源查询：TSRG 预算贪心、健全放宽、3 s 截止、流式补齐、缺源标注 | §6、§7、§8、§10.4 |
| FR-39 | 组合查询：布尔组合与频道的并、交、差，结果可存为新频道 | §3.5、§10.5 |
| FR-40 | 用户频道、WatchKey 引用计数、Percolator 写 FeedInbox | §11、§12、§15.1 |
| FR-41 | TSRG 统一索引及其四种用途 | §5、§6 |
| FR-42 | 自然语言与中文查询的四步解析，投机执行 | §4 |
| FR-43 | 相关论文与引文邻域（在线 ≤2 跳） | §4.6、§9.7、§10.6 |
| FR-44 | venue 浏览与关注 | §10.6 |
| FR-28 | 用户级来源偏好作用于频道、检索与推荐候选（04 协同） | §15.3 |
| FR-84 | 检索个性化挂点（06 主责，04 决定融合方式） | §8.8 |
| NFR-10 | 检索性能：端到端 p95 ≤800 ms；单路召回 p95 >300 ms 为升级触发线（R2-39）；联邦截止 3 s；路由计算毫秒级 | §14.2、§14.4 |
| NFR-12 | 新鲜度：日历型源公告后 ≤6 h 进入 FeedInbox，增量源 ≤24 h；显示数据时点 | §11、§12、§14.1(c) |
| NFR-13 | 可用与降级：同能力替补链、三道舱壁 | §8.4、§13.5、§13.9 |
| NFR-14 | 礼貌与配额 | §13 |
| NFR-15 | 隐私 | §15.4 |
| NFR-19 | 成本：美元预算桶 80% 告警、100% 降级 | §13.1、§14.3 |
| NFR-23 | 许可门禁：核心链路的依赖、模型与数据只用宽松许可 | §1.6、§8.7、§9.3 |

本文另给出两项细化目标 [判断]，供 09 定稿：
- 路由计算 p95 ≤5 ms，是 NFR-10"毫秒级"的量化；
- 频道命中从入库到写入 FeedInbox 的滞后 p95 ≤30 min，是 NFR-12 之下分给 Percolator 这一段的预算。

**调研设计输入（SI）的承接**：调研综合 §6.1 要求设计文档写明所依据的 SI。"承接"列含 04 的各条，以及 04 协同承接的几条，对照如下。"部分"表示本文与该 SI 的表述有差异，理由写在对应章节。

| SI | 设计输入（摘要） | 本文落点 | 状态 |
|---|---|---|---|
| SI-02 | Crossref 按请求类分池；venue 枚举走 single 池；不用全局 filter 或关键词查询打列表池；平台用 polite 池 | §11.1 基础收割；§8.4 标题匹配链末级的 `query.bibliographic` | 部分：03 §4.1 把 `works_query` 登记为交互道 SEARCH 端点，与本条及 AG §2.2.1、§2.4 R6 不一致（§6.12、§20 第 33 项） |
| SI-13 | 最新论文增量：Crossref `from-created-date` 为主、`from-index-date` 补漏；EPMC `FIRST_IDATE`；feed 只作新鲜度信号 | §11.2、§11.5 | 已承接；官方 WP feed 按 R2-17 例外 |
| SI-14 | CS 新鲜度阶梯 L0–L3 | §11.1 | 已承接；OpenReview 平台侧收割按 R2-20 停用 |
| SI-17 | OpenAlex Topics 骨架加原生叶子；MSC2020 为 NC；约 12% 无 topic 由本地补标；`/text` 已弃用 | §5.1、§5.5、§6.2 | 已承接；MSC2020 按 R2-22 改为默认不加载的插件 |
| SI-21 | 先收割、后联邦；应用层 TTL 缓存与 λ̂ 挂钩 | §6.3、§13.7 | 已承接 |
| SI-22 | SCD 是路由与放宽的唯一输入；每项关键能力两级同能力替补 | §6.3、§7、§8.4 | 已承接；PMCID 与语义探索两条链的远端级受限，见 §8.4、§20 第 3 项 |
| SI-23 | TSRG `route_stat`；预算贪心加单项兜底；Thompson 探索，日志足够后换 GBDT；统计周更或离线跑快照 | §5、§6 | 已承接；近似界按 R2-38 精确化 |
| SI-24 | 五意图；四步解析；投机首屏；规范查询兼作缓存键与复现凭据 | §3.6、§4 | 已承接 |
| SI-25 | NNF 健全放宽；属性测试；分析器对齐；"远端命中、本地拒绝"计数 | §7 | 已承接；更正三处放宽规则（§19-3） |
| SI-26 | BM25 + `halfvec` HNSW + RRF（k=60）+ CE；BM25 默认 pg_textsearch；ES 的 RRF 与 SPLADE 官方权重不进默认路径 | §8.6、§8.7、§9.2、§9.3 | 已承接；学习稀疏不进 v2.0 默认路径（SPLADE 官方权重为 CC BY-NC-SA，Apache-2.0 替代品留待评测，RT §4.1、§4.5） |
| SI-27 | 单 PG 18；升级触发与升级顺序 | §14.4 | 已承接；口径按 R2-39 |
| SI-28 | 图存 PG 邻接表，在线 ≤2 跳加 `CYCLE`；夜间 CSR；不引入图数据库 | §9.7 | 已承接 |
| SI-29 | union-find 物化 `cluster_id`；弱信号不自动合并 | §8.5（04 只消费） | 已承接 |
| SI-30 | 已见集合用 Roaring 位图 | §9.6 | 已承接 |
| SI-31 | 频道编译为带引用计数的 WatchKey；日历型与连续型调度；Percolator 写 FeedInbox | §11、§12 | 已承接 |
| SI-32 | 稳定性四件套、三道舱壁、截止时间与部分结果、不对同一主机对冲 | §8.2–§8.4、§13 | 已承接 |
| SI-37 | 账本键含出口 IP；解析各类限流响应头；OpenAlex 美元预算桶 | §13.1 | 已承接 |
| SI-38 | robots 先行闸由框架强制 | §13（出站网关） | 已承接；08 登记为 HC-29 |
| SI-40 | 表示模型候选；统一存 256 维 | §9.3 | 部分：检索索引维度随 Q7 选型（§19-15） |
| SI-49 | 协同信号的 k 门槛 | §6.8、§6.9、§11.1、§15.4 | 已承接：η 与 GBDT 训练集经聚合闸，细粒度收割键按 R2-19 |
| SI-51 | 小样本阶段优先 interleaving | §6.9 | 已承接 |
| SI-68 | 评测从第一天开始 | §14.1 | 已承接；评测数据的许可见 §1.6 |

### 1.2 范围与接口边界

04 **定义**：
- Query AST 与规范化；
- 意图识别与解析流水线；
- TSRG 的节点、边、统计、存储需求与更新作业；
- 路由器；
- 健全放宽与本地残差；
- 联邦执行器；
- 本地检索索引的结构与查询规划；
- WatchKey 编译与调度；
- Percolator 的候选生成与 FeedInbox 写入路径；
- 出站稳定性机制（出站网关）。

04 **引用**，不重复定义：

| 接口 | 定义方 | 04 如何使用 |
|---|---|---|
| SourceSpec v2、SCD、ConnectorFamily、Policy Engine、语料流水线 | [03](03-sources-and-corpus-pipeline.md) | SCD 是路由与放宽的唯一能力输入（SI-22）。流水线的 `index` 与 `percolate` 两段由 04 定义算法，在 03 的流水线里执行 |
| DDL、RLS、角色、分区、事件表 | [05](05-data-platform.md) | 本文的 DDL 片段只表达需求，表名与列以 05 为准（§5.4 列出映射与增补）。Percolator 与调度器分别以 05 定义的 `pc_sys_percolator`、`pc_sys_scheduler` 角色运行，05 的 RLS 已按列授权（§12.5、§11.1） |
| 事件契约、画像、ValueModel、Candidate Pipeline、Deck 组装与分配 | [06](06-recommendation-and-matching.md) | FeedInbox 是 06 的召回源。Percolator 近线写入频道命中；节点倒排与质心点积由 06 的日批作业调用本文的候选生成，产出的候选读者由 06 分配（06 §11.3，§12.1–§12.2）。检索个性化挂点 `personal_score` 见 §8.8 |
| 筛选条渲染、结果流式更新的交互 | [07](07-frontend-interaction.md) | FilterChip 契约（§4.4）、流式事件（§8.2）与完整性报告（§8.3）由本文给出字段，07 定义呈现 |
| 权利引擎、HC 登记、日志留存、LLM 路由与出境 | [08](08-compliance-security-privacy.md) | 索引资格（§9.1）、查询日志（§15.4）与 LLM 解析的区域路由（§4.5）以 08 为准 |
| 服务拓扑、API 面、传输 | [02](02-architecture.md) | 02 已把本文的检索服务落为 P3"Router 与联邦执行器"（API 进程内模块），出站网关落为 P13 Egress Gateway（单例，唯一公网出口）；Harvest Scheduler（P6）、Percolator（P11）、推理服务（P12）也由 02 部署（02 §2.3） |

### 1.3 设计原则在本文的落点

- **P-01 先收割、后联邦**：LATEST、频道与卡片流只读本地；SEARCH/SIMILAR/EXPAND 按 §6.3 的判据决定是否联邦；"按需刷新"只提升 WatchKey 的收割优先级，不做查询时联邦（§11.6）。
- **P-02 合规数据三域**：
  - 共享索引只收 §9.1 权利闸放行的字段；
  - 个人谓词永不下推到远端（§7.2）；
  - 私有层检索与共享检索隔离，只在本人响应中融合（§9.8）；
  - 路由日志不带用户标识；路由的输入不含个人画像、个人谓词的求值结果与私有列表（§6.2、§15.3）；η 与 GBDT 训练集经聚合闸（§6.8、§6.9）。
- **P-03 用户侧取回**：`exec_side=user` 的端点不进入平台路由（§6.3）。
- **P-04 全局礼貌**：出站网关统一执行配额账本、AIMD、重试预算、舱壁，并禁止同主机对冲（§13）。
- **P-05 最严者为准**：候选端点先经 Policy Engine 判定本请求类（交互、用户触发）是否允许（§6.3）。
- **P-06 可解释可控**：每条结果带来源归因；每次响应带完整性报告（§8.3）；提供非个性化视图（§15.3）。
- **P-07 LLM 不进热路径**：LLM 解析异步、可选、不阻塞首屏（§4.2）；新源的 LLM 先验只在离线生成（§6.10）。
- **P-08 评测先行**：每次路由决策都记录 `tsrg_version`、候选特征、采样值与结果（§6.9、§14.1）。
- **P-09 可降级**：每项关键能力都有同能力替补链（§8.4）；上游全失败时降级为"仅本地"（§13.9）。

### 1.4 术语（新增共享术语，供 01 汇总登记）

| 术语 | 含义 | 首次定义 |
|---|---|---|
| SourceEndpoint（源端点） | Source 在某个来源通道（`source_channel`）下可调用的具体端点，例如 Crossref `/journals/{issn}/works`、OpenAlex `works?search=`。它是 TSRG 中的 S 节点，也是路由与配额的最小单位 | §5.1 |
| route_stat | TSRG 中"节点 × 端点 × 窗口"的边权统计：覆盖 cov、滞后 lag、到达率 λ、检索有效率 η、独有贡献 uniq、字段完整度 fidelity | §5.2 |
| Coverage Sketch（覆盖素描） | 每个主题节点抽 M 篇样本作品，记录它们被各端点收录的位矩阵，用来估计任意端点集合的并集覆盖 | §5.3 |
| Topic Posterior（主题后验）π(t)=P(t\|q) | 查询在 TSRG 主题节点上的概率分布，路由的输入 | §6.2 |
| Sound Relaxation（健全放宽）/ Residual（本地残差） | 为源生成满足 P ⇒ P_s 的可下推查询；本地再用原谓词 P 过滤 | §7 |
| Pushdown Fidelity（下推保真度）φ | 原谓词中被源原生求值的"选择率信息量"占比 | §7.4 |
| Egress Gateway（出站网关） | 平台侧全部第三方出站请求的统一执行点，负责 robots 闸、配额账本、AIMD、重试预算、熔断、缓存与 singleflight。即 02 的 P13、08 的 "Egress Gate"。名称按 R2-08 统一；03 的 PoliteHttp 是网关内部使用的客户端库，不是另一个组件 | §13 |
| Quota Ledger（配额账本） | 以 (source, host, request_class, credential, egress_ip) 为键、由响应头驱动的限额与余量记录（SI-37） | §13.1 |
| Lane（舱壁道） | 每个上游的三道并发与令牌份额：interactive / harvest / enrich | §13.5 |
| Canonical Query / query_hash | 规范化后的 AST 及其 SHA-256 哈希，兼作缓存键、复现凭据与日志主键（SI-24） | §3.6 |
| FilterChip（筛选条） | AST 顶层合取项的可编辑呈现单元，是 04↔07 的契约 | §4.4 |
| Speculative First Screen（投机首屏） | AST 定稿前，用快路径 AST 先跑本地检索得到的首屏结果；只读本地、不出网，其命中还供路由估计 P(t\|q) | §4.2 |
| Completeness Report（完整性报告） | 响应中关于计划源、成功源、截断、近似与数据时点的说明 | §8.3 |
| Anchor Index（锚点倒排） | Percolator 为频道谓词建立的"可索引文字 → (频道, 子句)"倒排 | §12.3 |
| Base Harvest（基础收割） | 与具体频道无关、覆盖全体用户兴趣并集的常驻收割集合 | §11.1 |
| Index Eligibility（索引资格） | 权利引擎给出的字段级"能否进入共享索引或嵌入"的结论 | §9.1 |
| Transient Candidate（临时候选） | 联邦结果中尚未入库的作品，在本次会话中以规范化标识符临时成组 | §8.5 |
| Missing Semantics（缺失语义） | 残差求值时字段缺失的处理：`kleene`（默认）或 `closed_world`（v1 兼容） | §3.5 |
| Relevance Text（软检索文本） | 即席检索中未加引号、前缀或算子的裸词，存于 `rank.relevance.text`。它驱动 BM25（OR 语义打分）与稠密召回，也作为远端端点的相关性查询下推，但不进入硬谓词 `where` | §3.2 |
| Known-Member Recall（已知成员召回） | η 的观测口径：一次联邦查询的最终 top-k 中，已知被端点 s 收录的作品里，s 实际取回的比例 | §5.3 |
| Scope Completeness（范围完整性） | 查询的硬过滤把结果限定在一组 venue、系列或 arXiv 类目内，且这些范围在查询时间窗内已完整收割（回填覆盖窗口起点、latest 水位不早于窗口终点）。成立时本地覆盖取 1，不联邦 | §6.3 |
| Exact-Enumeration Gate（精确枚举规模闸） | 在线精确枚举的规模上限：候选数 n ≤ 10 且 2ⁿ·K·P ≤ 2²⁰（K·P 为压缩后的样本模式列数）；超出时改用"比值贪心 + 最佳单源" | §6.4、§6.6 |

> 术语对齐：简报 §5 中"Channel"同时指 SourceSpec 的三个通道（metadata/latest/fulltext）和用户频道。R2-02 已裁定：SourceSpec 内的通道称 **SourceChannel（来源通道）**，标识符写 `source_channel`；用户保存的查询称 **Channel（频道）**，标识符写 `channel`。本文遵循这一约定（§19-6）。`route_stat`、健全放宽、同能力替补链、舱壁已由 01 §14.2 登记；上表对其中几项给出更精确的定义，供 01 更新。

### 1.5 合规硬约束对照（HC）

HC 编号沿用 CP §3.1（调研综合 §6.2），由 08 §2.2 统一登记；08 另登记了 HC-29…HC-32。下表逐条给出本文的落点，"不适用"表示本文不处理相应的数据或功能。

| HC | 约束（摘要） | 本文的落点 |
|---|---|---|
| HC-01 | 共享与私有两域，只许共享流向私有 | 共享索引只收权利闸放行的字段（§9.1）；私有检索只在本人域（§9.8）；路由的全部输入取共享层、非个性化的召回（§6.2、§6.3）；η 与 GBDT 训练集经聚合闸（§6.8、§6.9）；个人谓词永不下推（§7.3 的 I-2） |
| HC-02 | 不跨用户复用，不暴露"他人有权限"一类信号 | 跨用户缓存只用不含用户信息的 `plan_key`；不暴露缓存命中与查询即入库的来由（§15.4 第 5 条）；OA 定位只给公开的 OA 位置，"用你的凭证"一态不由本文计算 |
| HC-03 | 受限全文在用户侧取回 | `exec_side=user` 的端点不进平台路由（§6.3 第 1 条）；OA 定位链只定位，PDF 下载走用户侧（§8.4） |
| HC-04 | 不收机构口令；用户 key 存端侧或端到端加密 | 平台联邦只用部署级凭证，由出站网关独占（R2-30，§13）；用户级凭证（含按 R2-14 处理的 SN、ADS）不进平台路由（§6.3 第 1 条） |
| HC-05 | 按篇许可白名单 | 共享层不建全文索引（§9.1）；查询即入库与 TTL 缓存只收来源允许平台级缓存的数据，并保留字段级权利标签（§8.5、§13.7） |
| HC-06 | arXiv：e-print 不存储、不提供；全平台每 3 秒 1 次、单连接 | 只用 arXiv 元数据（CC0）；e-print 及从中抽取的文本与图不进任何共享索引或缓存（§9.1）；交互道只留 LOOKUP 的极小份额（§8.4、§13.5） |
| HC-07 | 字段级权利标注 | 索引资格由权利引擎的字段级结论派生（§9.1） |
| HC-08 | 摘要分级展示 | 本文只决定索引与 CE 输入；B 类的展示上限 DL3 由 08 的展示闸执行（§9.1） |
| HC-09 | 图片门控 | 不适用 |
| HC-10 | 每个上游一个平台身份、全局调度 | 单例出站网关；账本键为五元组，限额跨出口 IP 汇总；禁止多 key、多 IP（§2、§13.1） |
| HC-11 | LLM TL;DR 治理 | 本文不生成 TL;DR；其 (b)(c) 两项输入约束同样用于 EXPAND 深度模式的 LLM（§4.6），以及嵌入与 CE 的输入（§9.1） |
| HC-12 | 中国境内使用 LLM 的条件 | 查询解析与深度模式只用自托管模型；面向境内用户开放时仍须备案、登记与公示（§4.5；Q2 默认否） |
| HC-13 | 推荐透明与可控 | 非个性化视图（`personalize=off`、`np_time`/`np_source`）、"已按你的兴趣排序"标注、可直达的关闭个性化筛选条（§4.4、§8.8、§15.3）；非个性化排序可复现 |
| HC-14 | 算法合规工程化 | 路由决策日志与检索执行记录按 R2-31 留存；评测记录版本以便复现（§6.9、§15.4、§16） |
| HC-15 | UGC 分阶段 | 频道的公开共享尚未定义；开放时按 UGC 处理（§15.1、§20 第 10 项） |
| HC-16 | 禁止公共全文上传 | 私有全文只在本人域检索（§9.8） |
| HC-17 | 学术评论规范 | 不适用 |
| HC-18 | 双向匹配须单独同意 | 节点倒排与质心点积只用于论文→读者（层②）；研究者↔研究者（层③）不得复用本文的用户倒排，除非只读已单独同意的用户（§15.4 第 9 条） |
| HC-19 | 最低年龄 | 不适用 |
| HC-20 | 数据最小化与留存 | 检索历史本人可删；ops 日志只记聚合指标；`route_decision` 去标识（§12.5、§15.4） |
| HC-21 | 地区开关 | LLM 解析与个性化挂点受 08 的地区开关约束（§4.5、§8.8） |
| HC-22 | 跨境 | 联邦会把不带用户标识的查询文本发往 OpenAlex、S2 等第三方；面向中国境内用户时，这是向境外服务提供数据，按 HC-22 评估是否构成个人信息出境；在隐私告知中说明，并提供"仅本地检索"（§15.4 第 2 条） |
| HC-23 | 商用开关 | CORE 取得许可前不进路由；`platform.commercial=true` 时自动关闭受限来源；S2 的商用边界待 LQ-08（§6.3 第 8 条） |
| HC-24 | 署名自动渲染 | 远端结果携带来源字段，NLM、S2、arXiv 等署名由 07 渲染（§8.3、§10.1、§10.4） |
| HC-25 | 出版商 TDM 产出外发 | 不适用 |
| HC-26 | 反对抗红线 | 挑战页进入 POLICY_BLOCKED，不自动恢复；不路由到 Google Scholar（§13.4） |
| HC-27 | IEEE、ACS、ACM | 三家不作平台端点，元数据经 Crossref；IEEE API 内容属 C 类，不入任何索引（§6.3、§9.1） |
| HC-28 | 可审计 | 每个出站请求写 FetchLog；路由决策记 `tsrg_version`（§5.4、§13） |
| HC-29…HC-32（08 新增） | robots 先行；小样本隐私门槛；`needs_confirmation` 通道；受限全文只由用户触发、单篇取回 | HC-29：网关内的 robots 闸（§13）；HC-30：不适用，本文的 k 门槛用于 η、GBDT 训练集与细粒度收割键，取 `k_cf`（§6.8、§6.9、§11.1）；HC-31：只接受低频、用户触发的调用，WatchKey 要求 background（§6.3 第 2 条、§11.1）；HC-32：本文不做全文取回 |

### 1.6 依赖、模型与数据的许可门禁（B-06、R2-01）

按 R2-01 采用 08 §10.6 的四级口径：放行、评审、可选、禁止。本文用到的依赖、模型与数据逐项核对如下。调研没有记录许可的项，由本文补查一手来源（2026-09-27 查阅 GitHub 仓库元数据、仓库 LICENSE 文件与 Hugging Face 模型卡，列于 §21.3）；仍不能确认的标 ⚠，启用前核验。

| 类别 | 对象（用途） | 许可 | 门禁 | 依据 |
|---|---|---|---|---|
| 依赖 | PostgreSQL 18、pg_trgm、pgvector、pg_textsearch 1.4.0 | PostgreSQL | 放行 | B-01；RT §5.2、§6.3 |
| 依赖 | pg_roaringbitmap；CRoaring、PyRoaringBitMap | Apache-2.0；Apache-2.0/MIT、MIT | 放行 | RT §6.3、附表 A |
| 依赖 | procrastinate；hishel；Valkey（可选） | MIT；BSD-3；BSD-3 | 放行 | RT §9.2、§10.5、§10.6 |
| 依赖 | psycopg 3 | LGPL-3.0 | 评审级，按 R2-01 放行（不修改、以库形式动态导入） | R2-01 |
| 依赖 | outlines、xgrammar、llguidance（受约束解码） | Apache-2.0 或 MIT | 放行 | RT §4.3.2 |
| 依赖 | rustworkx、scipy（夜间图批算） | Apache-2.0；BSD-3-Clause | 放行 | RT §6.1；scipy 为一手来源 |
| 依赖 | LightGBM、XGBoost（GBDT 路由器） | MIT；Apache-2.0 | 放行 | 一手来源 |
| 依赖 | Hypothesis（属性测试，只作开发依赖） | MPL-2.0 | 评审级并放行；不进分发产物 | 一手来源 |
| 依赖 | pgvectorscale、Apache AGE、OpenSearch、Qdrant、Vespa（升级路径） | PostgreSQL；Apache-2.0 | 放行 | RT §5.2、§6.1 |
| 依赖 | igraph | GPL-2.0 | 不进分发产物 | RT §6.1 |
| 依赖 | ParadeDB pg_search | AGPL-3.0 | 可选，默认关 | RT §5.2；B-06 |
| 依赖 | Elasticsearch（含 RRF） | AGPL/SSPL/ELv2 三选一；RRF 属 Enterprise 档 | 不采用 | RT §4.2、§5.2 |
| 模型 | gte-large、Qwen3-Embedding-0.6B、specter2_base（嵌入，Q7 候选） | MIT；Apache-2.0；Apache-2.0 | 放行；SPECTER2 proximity adapter 的许可 ⚠ 待核 | RT §4.5；简报 Q7 |
| 模型 | SPLADE 官方权重（学习稀疏） | CC BY-NC-SA 4.0 | 不进默认路径（SI-26） | RT §4.5 |
| 模型 | Qwen3-Reranker-0.6B（有 GPU 时的 CE） | Apache-2.0 | 放行 | 一手来源 |
| 模型 | 小型交叉编码器，如 cross-encoder/ms-marco-MiniLM-L6-v2（T1 的 CE 候选） | 权重 Apache-2.0；训练数据为 MS MARCO，HF 上该数据集的元数据未声明许可 | 评审：训练数据条款核清前不作默认 ⚠ | 一手来源 |
| 模型 | OpenAlex topic 分类器，标题+摘要版（长查询的 P(t\|q)） | 权重 Apache-2.0，代码 MIT | 放行 | PU §2.4 |
| 模型 | 自托管 LLM（查询解析、深度模式，均为可选） | 未选型 | 须为放行级；Gemma 等自定义许可单独评审；NC 与研究许可禁止 | RT §4.5；SR §3.1-4 |
| 数据 | OpenAlex、Crossref 书目、arXiv 元数据、ROR、OpenCitations | CC0 或事实 | 放行 | AG §2.3.4；CP §2.1 |
| 数据 | S2 API 与数据集 | API 协议加 ODC-BY | 评审：须署名"Semantic Scholar"；商用待 LQ-08 | AG §2.2.3；CP §2.1 |
| 数据 | Europe PMC、PubMed | NLM 条款：须声明来源、保持最新；摘要为 B 类 | 放行（按 HC-24 署名）；PubMed 的通道按 R2-13 在 NCBI 书面确认前不调用，这是 robots 问题，不是许可问题 | CP §2.1；AG §2.2.11 |
| 数据 | arXiv 类目、PhySH、MeSH（原生叶子） | CC0；CC0；NLM 公开，须标版本 | 放行 | PU §2.4；SR §2.11；LS §3-9 |
| 数据 | JEL、ACM CCS（原生叶子） | AEA 官方公开 XML，再分发许可 ⚠；第三方镜像，许可 ⚠ | 评审：内置前核验 | SR §2.11 |
| 数据 | MSC2020 | CC BY-NC-SA | 可选插件，默认不加载 | R2-22 |
| 数据 | ABDC JQL、EconBiz STW、APA PsycInfo 分类码 | 站点声明版权所有、第三方版本未获授权；许可 ⚠；受许可限制 | 不内置（前两者待许可确认） | SS §3-10；LS §3-9 |
| 数据 | LitSearch、SciRepEval（离线评测） | MIT；代码 Apache-2.0，HF 数据集元数据未声明许可 ⚠ | 只作离线评测，不进分发产物 | RT 附表 A；一手来源 |

---

## 2. 总体架构

检索子系统由两个同步组件（检索服务、出站网关）和四类后台作业组成。完整数据流见 [v2-05-query-execution.svg](../../diagrams/v2-05-query-execution.svg)，TSRG 的结构与用途见 [v2-04-tsrg.svg](../../diagrams/v2-04-tsrg.svg)。组件边界如下（ASCII 示意）：

```text
 前端/API ──► 检索服务（Search Service，交互道）
               ├─ Parser：规则快路径 →（异步）受约束 LLM → 实体链接 → FilterChip
               ├─ Router：读 TSRG 快照；P(t|q) → 覆盖判据（范围完整性优先）→ 候选硬约束 → 放宽（剔无界、估成本、剔超预算）→ 预算选源（+TS）
               ├─ Local Executor：Roaring 分面 → 选择率规划 → BM25 ∥ tsvector ∥ HNSW ∥ 图
               ├─ Federation Executor：放宽 → 子查询 → 出站网关（截止时间、流式）
               └─ Merger：规范化 → cluster 折叠 → 残差 → RRF → CE 重排 → 个性化挂点 → 流
 出站网关（Egress Gateway）：robots 闸 · 配额账本 · AIMD · 重试预算 · 熔断 · 缓存/singleflight
               └─► 第三方 API（每个上游只用一个平台身份，HC-10）
 后台作业（worker，收割道/enrich 道）：
   WatchKey 调度器 → 收割 → 03 流水线（normalize→identify→enrich→index）→ Percolator（频道命中，近线）→ FeedInbox
   日批：节点倒排 + 质心点积（04 的候选生成）→ 06 分配（P4）→ FeedInbox
   TSRG 构建器（周更统计 + 日志驱动更新 + 快照发布）
   图批算（夜间 CSR：PageRank、共被引/耦合邻居）
   评测作业（路由穷举对照、检索金标回归、新鲜度金丝雀）
 数据：corpus（共享只读）｜usr（RLS：频道、已见、FeedInbox、兴趣边；私有索引仅 personal 本机部署，§9.8）｜evt（查询与路由事件）｜ops（端点、route_stat、素描、账本、缓存）
```

两个同步组件在 02 中已落到拓扑：
- "检索服务"即 02 的 P3"Router 与联邦执行器"，是 API 进程内模块，随 API 水平扩展；
- "出站网关"即 02 的 P13 Egress Gateway，是单例服务，也是平台唯一的公网出口（02 AD-01）。

对 04 而言，唯一的硬要求是：**配额账本与熔断状态在平台内全局唯一**，不能按进程或按用户各自计数（P-04、HC-10）。单例出站网关天然满足这一点。

---

## 3. Query AST 规范

### 3.1 设计目标

1. **一种 AST 服务全部入口**：即席检索的五意图、用户频道、Percolator 的谓词求值、WatchKey 编译，都用同一种 AST（SI-24）。
2. **硬谓词与软打分分离**：
   - `where` 决定"哪些作品算结果"，可以下推、放宽、做残差；
   - `rank` 决定"怎么排"，不改变结果集合。
   
   这样健全放宽的正确性只需对 `where` 论证（§7）。
3. **可规范化、可哈希、可复现**：规范形与 `query_hash` 兼作缓存键和复现凭据（SI-24；OpenAlex 官方 MCP 回显 canonical OQL 的先例见 OSS §2.4.1）。
4. **语义明确**：缺失值、分析器、时间字段、语义阈值都有定义。v1 订阅 DSL 可以逐字段映射，并能复现 v1 的判定结果（§3.8）。
5. **隐私可检查**：个人谓词（已见、在库、评分）只能在本地求值，编译期静态检查（§7.2）。

### 3.2 表面语法（EBNF，设计伪代码）

表面语法面向高级用户与 API。主界面以筛选条（§4.4）呈现同一 AST，不要求普通用户手写。语法向下兼容 v1 的 arXiv 布尔式：`ti:`/`abs:`、`AND`/`OR`/`ANDNOT`（`AND NOT` 归一为 `ANDNOT`）、引号短语，且 AND/ANDNOT 的结合力强于 OR（v1 `subs/types.py`）。

```text
(* 设计伪代码 —— EBNF，非接口冻结 *)
query       = [ intent_kw ] , expr , { modifier } ;
intent_kw   = "lookup:" | "search:" | "similar:" | "latest:" | "expand:" ;   (* 缺省按 §4.1 规则推断 *)
expr        = or_expr ;
or_expr     = and_expr , { or_op , and_expr } ;
or_op       = "OR" | "|" | "∪" ;
and_expr    = not_expr , { [ and_op ] , not_expr } ;                       (* 省略 and_op 即并列 AND *)
and_op      = "AND" | "&" | "∩" | diff_op ;
diff_op     = "ANDNOT" | "−" | "\" ;                                       (* a diff b ≡ a AND NOT b *)
not_expr    = { "NOT" | "-" } , primary ;
primary     = "(" , expr , ")" | channel_ref | atom ;
channel_ref = "@" , name , [ "#v" , int ] ;                                (* 用户频道引用；#v 钉历史版本须 05 提供版本历史，见 §20 *)
atom        = id_ref | field_term | facet | range | rel | sem | personal | regex | required | bare_term ;
id_ref      = id_scheme , ":" , token ;
id_scheme   = "doi" | "arxiv" | "pmid" | "pmcid" | "ssrn" | "openalex" | "s2" | "isbn" ;
field_term  = field , ":" , term_val ;
field       = "ti" | "abs" | "au" | "venue" | "any" | "full" ;
term_val    = phrase , [ "~" , int ] | word , [ "*" ] ;                  (* "a b"~3 为邻近；w* 为前缀 *)
facet       = facet_dim , ":" , value_list ;
facet_dim   = "domain" | "field" | "subfield" | "topic" | "cat" | "jel" | "msc" | "mesh" | "physh" | "ccs"
            | "venue" | "series" | "author" | "inst" | "type" | "pubtype" | "lang" | "oa" | "review"
            | "status" | "license" | "src" ;
            (* type = 文献类型（article、preprint…）；pubtype = 研究类型（RCT、meta-analysis…，MEDLINE PT 等）；
               status = 撤稿/更正状态（05 corpus.work_badge） *)
value_list  = value | "(" , value , { "," , value } , ")" ;
range       = range_dim , ":" , [ value ] , ".." , [ value ] | range_dim , cmp , value ;
range_dim   = "year" | "date" | "created" | "cites" ;
rel         = rel_kind , ":" , ref ;
rel_kind    = "cites" | "citedby" | "coupled" | "cocited" | "versionof" ;
sem         = "~(" , text , ")" , [ ">=" , float ]  |  "like:" , ref , [ ">=" , float ] ;
personal    = "is:" , ( "unseen" | "saved" | "inlib" | "rated" ) ;
regex       = field , "~/" , pattern , "/" ;                              (* 仅为 v1 兼容，只在本地残差求值 *)
required    = "+" , ( phrase | word ) ;                                   (* 硬性包含：等价 any:，进入 where *)
bare_term   = phrase | word ;        (* 即席检索中为软检索文本 rank.relevance.text；频道中为 any: 硬谓词；见下文约定 *)
modifier    = "window:" , duration | "sort:" , sort_key | "k:" , int
            | "via:" , src_list | "-via:" , src_list | "mode:" , ( "local" | "auto" | "force" ) ;
sort_key    = "relevance" | "recency" | "cites" | "personal" | "issue" | "graph" ;
```

四条解析约定：
- **裸词是软检索文本**。即席检索（SEARCH、SIMILAR、EXPAND）中，未加引号、字段前缀、`+` 或布尔算子的裸词，按原顺序拼成 `rank.relevance.text`，不进 `where`：
  - 它驱动本地 BM25（OR 语义打分）与稠密召回，也作为相关性排序端点的查询下推；结果集合由"各路召回的并集 ∩ 硬谓词"给出（§3.5）。
  - 这样稠密通道能召回措辞不同、但不含全部查询词的论文。若把裸词当作硬 AND，"papers using transformers to forecast returns"这类自然语言查询会因"papers""using"等词被系统性漏检，混合检索也就退化成了对 BM25 结果的重排（RT §4.1、§4.3.2 第 5 步、§4.4）。
  - 引号短语、`ti:`/`abs:` 等字段前缀、`+词`、显式 AND/OR/NOT 组合都是硬谓词。
  - 两种情形下裸词编译为硬 AND 门 `And(Term(any, t_i))`，并以"须包含全部词"筛选条呈现、可编辑：一是频道（频道需要清晰的成员判定，§12）；二是 `rank` 为 recency、cites、issue 或 personal 等非相关性排序时，包括 LATEST（否则按日期或被引排序会把不相关的论文排上来）。
- 不带阈值的语义原子 `~(text)` 不进 `where`，解析器把它提升为 `rank.semantic`。只有带阈值的写法（`~(text)>=0.62`）才是硬谓词，阈值为余弦相似度，绑定嵌入模型版本。
- 符号集合算子（`∪`、`∩`、`−`、`\`）在同一层与任何其他二元算子（含文字算子 AND/OR/ANDNOT 与省略算子的并列）混用且无括号时，解析器拒绝并提示加括号。按上面的文法，AND 类算子结合力强于 OR，`A ∪ B − C` 会读作 `A ∪ (B − C)`，与集合代数的直觉 `(A ∪ B) − C` 不同。这条优先级只为兼容 v1 的文字算子 AND/OR/ANDNOT 而保留（v1 `subs/types.py`），纯文字算子的混用照常按优先级解析。
- ASCII 连字符 `-` 只在词首且前面是空白或左括号时才是 NOT 前缀；词内连字符（`COVID-19`、`state-of-the-art`）属于词本身。
- `src:` 与 `via:` 是两种不同的"来源限定"：
  - `src:arxiv` 是作品谓词，含义为"该作品在 arXiv 有记录"，按来源溯源（provenance）求值，可以在本地求值；
  - `via:openalex` 是执行约束，含义为"本次只允许路由到这些端点"，不改变结果的定义。

  两者混淆会让"只看 arXiv 论文"和"只问 arXiv 的 API"得到不同的结果集，而用户难以察觉。

### 3.3 节点类型

| 类别 | 节点 | 关键字段 | 语义与求值 | 下推注意 |
|---|---|---|---|---|
| 布尔 | `And` / `Or` / `Not` | children | 标准布尔；集合运算 ∪/∩/− 归约到此三者 | 源的布尔能力见 SCD `kw.bool` |
| 字段词项 | `Term` | field ∈ {title, abstract, author, venue, any, fulltext}；text；mode ∈ {word, phrase, prefix, near(n)}；match ∈ {analyzed, substring_ci} | `analyzed` 按分析器档案匹配（§3.5）；`substring_ci` 为 v1 兼容的不区分大小写子串匹配。`near(n)` 的定义：各词在同一字段内出现，任意两相邻命中词的词位间距 ≤ n，顺序不限（PG 的 `<N>` 是"间距恰为 N"，编译方式见 §9.2） | 放宽规则见 §7.4：短语→AND、邻近→AND、字段泛化 |
| 标识符 | `IdRef` | scheme, value | 规范化后精确匹配（DOI 小写去前缀、arXiv 去版本号等，RT §7.3） | LOOKUP 走替补链 |
| 分面 | `Facet` | dim, values, match ∈ {primary, any} | 集合成员；topic 类的 `match=primary` 只看首要主题，`any` 看全部至多 3 个 topic（RT §4.3.1） | 本地走 Roaring/GIN；远端按 SCD 的值映射 |
| 区间 | `Range` | dim ∈ {year, first_public, published, created, ingested, cites}；lo, hi | 闭区间；时间字段见 §3.5 | 放宽可扩到整年（§7.4） |
| 关系 | `Rel` | kind ∈ {cites, cited_by, coupled_with, co_cited_with, version_of}；ref | 在本地引文图上求值（§9.7） | 远端只有少数源支持（OpenAlex `cites:`；AG §2.3.1 的字段可得性矩阵） |
| 语义（硬） | `SemAtom` | text 或 work_ref；min_sim；model | cos(emb(w), emb(ref)) ≥ min_sim | 远端不支持时替换为 true（健全），见 §7.4 |
| 个人 | `Personal` | kind ∈ {unseen, saved, in_library, rated_ge}；user | 在 usr 域求值（RLS） | **永不下推**（§7.2） |
| 正则 | `Regex` | field, pattern, flags | 仅为 v1 兼容。语义以 Python `re`（v1 的求值引擎，v1 `subs/filter.py`）为准，最终判定在应用层执行。PG 的正则方言不同：`\b` 在 PG 中是退格符，词边界要写 `\y`、`\m`、`\M`（PG 18 文档表 9.20、9.22，一手来源，2026-09-27 查阅）。v1 预置包大量使用 `\b`（如 `\bagent(s\|ic)?\b`），直接交给 PG 的 `~*` 会让这些条件全部失配。若用 pg_trgm 在 PG 中预筛，须先把模式转写为 PG 方言，且预筛结果只作超集 | 永不下推 |
| 频道引用 | `ChannelRef` | channel_id, ast_hash | 编译期内联为该频道当前的 `where`，并在规范 AST 中记录其 `ast_hash`（05 `usr.channel.ast_hash`）以便复现；循环引用拒绝；内联深度 ≤4 [判断] | 内联后按普通谓词处理 |
| 排序 | `RankSpec` | relevance（软检索文本 `text`，及 BM25/dense 权重）、semantic（文本或种子）、recency、cites、personal、issue（卷期序）、graph（图分）、tie_break | 不改变硬谓词定义的集合；`relevance.text` 另决定召回候选（§3.2、§3.5）；默认值按意图（§4.1） | `relevance.text` 作为相关性排序端点的查询下推；远端排序只影响各列表内部顺序（§8.6） |
| 时间窗 | `TimeWindow` | field（默认 first_public）、from、to 或 last=duration | 对 LATEST 必填；语义等价于一个 `Range` 合取项，单列是为了路由和缓存 | 与 WatchKey 水位联动（§11.5） |
| 来源限定 | `SourceScope` | via（允许端点）、exclude、mode ∈ {local, auto, force} | 执行约束，不改变结果定义 | `mode=local` 时禁止联邦 |
| 预算 | `Budget` | deadline_ms、max_cost_cu、max_requests | 缺省取策略默认值（§6.5）；超额时先预览（§3.7） | — |

### 3.4 Query 结构（设计伪代码）

```python
# 设计伪代码 —— 非接口冻结；字段名以实现期 Pydantic 模型为准
class Query(BaseModel):
    v: Literal[2] = 2
    intent: Literal["LOOKUP", "SEARCH", "SIMILAR", "LATEST", "EXPAND"]
    where: Pred | None = None                 # 硬谓词：决定结果集合
    rank: RankSpec = RankSpec()               # 软打分：决定顺序；rank.relevance.text 为软检索文本（§3.2），另参与召回
    window: TimeWindow | None = None          # LATEST 必填
    scope: SourceScope = SourceScope(mode="auto")
    k: int = 20                               # 每页条数
    budget: Budget | None = None              # 缺省取策略默认（§6.5）
    missing: Literal["kleene", "closed_world"] = "kleene"
    accept: Literal["strict", "lenient"] = "lenient"   # 仅 kleene 下生效（§3.5）
    lang_pref: list[str] = []
    personalize: Literal["default", "off"] = "default"  # off = 非个性化视图（HC-13）

Pred = And | Or | Not | Term | IdRef | Facet | Range | Rel | SemAtom | Personal | Regex | ChannelRef

class Term(BaseModel):
    field: Literal["title", "abstract", "author", "venue", "any", "fulltext"]
    text: str
    mode: Literal["word", "phrase", "prefix"] | Near    # Near(n=3)
    match: Literal["analyzed", "substring_ci"] = "analyzed"
```

### 3.5 语义

**求值域**：
- 即席检索的结果集合 = 本地语料中满足 `where` 的作品 ∪ 本次联邦取回并通过残差的临时候选（§8.5）；
  - 有软检索文本时，本地部分改为：各路召回（BM25 的 OR 语义打分、稠密、其他本地召回路）**在 `where` 约束下**各取前 N_rec 条，再取并集（每路 N_rec = 100 [判断]；过滤在召回内部执行，先过滤、后取前 N_rec，§9.5）。不能写成"先取全库前 N 条、再与 `where` 求交"：`where` 选择性高时（例如只限三本期刊），全库前 N 条与它的交集可能为空，而满足条件的作品其实很多，这就是后过滤的召回塌陷。这部分由召回深度而不是谓词定义，因此完整性报告对它只给"召回深度"，不作完整性宣称；
  - 远端端点把软检索文本作为相关性查询，残差只检查硬谓词；
- 频道与 Percolator 只在本地语料上求值（P-01）；
- 结果以 `cluster_id` 为单位呈现（§8.5）。05 的一个 `corpus.work` 就是一个 cluster。

**缺失值（三值逻辑）**：
- 残差求值时，字段缺失或未知的文字取 U（unknown），公式按 Kleene 三值逻辑计算（¬U=U，U∧F=F，U∨T=T）。
- `accept=strict` 只接受 T。
- `accept=lenient` 同时接受 T 与 U：U 结果排在 T 结果之后，并带"未验证条件"标记，例如"出版类型未能确认"。

该区分针对跨学科的真实数据缺口：心理学期刊的 Crossref 摘要覆盖为 0%，Elsevier、APA、AOM 等出版方也为 0（AG §2.6）。以摘要为条件的查询在严格模式下会系统性漏掉这些学科。两种模式的默认用法：
- 交互检索默认 `lenient`；
- 频道与 Percolator 默认 `strict`，用户可以开启"包含未能确认条件的论文"；
- v1 迁移来的频道用 `closed_world`：在文字层把缺失当作 F，因此 `NOT abs:"x"` 在摘要缺失时为 T。这与 v1 `_evaluate_arxiv_query`"字段缺失 → 该原子 False"的规则逐条一致（v1 `subs/filter.py`）。

**分析器**：
- `Term(match=analyzed)` 的匹配口径由分析器档案（`analyzer_profile`；在 03 的 SCD 中记作 `analyzer`）决定。本地默认 `pg_english_v1`：小写、去重音、英文词干，与 PG `english` 配置一致。
- 对下推到源 s 的文字，残差用源对齐档案重算，例如 OpenAlex `search` 做词干化与停用词处理（RT §3.5.3）。档案登记在 SCD（03）。
- `match=substring_ci` 只用于 v1 兼容。

**时间字段**：
- `first_public` = 同一 cluster 任一版本最早公开的时间（arXiv 公告时间、DOI created、出版日中取最早）；
- `published` = 出版方给出的出版日；
- `created` = DOI 注册时间；
- `ingested` = 进入本地语料的时间。

LATEST 默认用 `first_public`。原因：IEEE 系会议的 DOI 比会期晚 2–6 个月，NeurIPS 的 Curran DOI 晚约 8 个月（CS §2.6.5）。如果按 `published` 判断"新"，预印本早已流通的论文会被重复当作新论文。正式版到达这类"版本更新"作为更新通知处理，不作为新卡片（§9.6）。

**语义原子**：`SemAtom.min_sim` 绑定 `(model, dim)`。模型换代时，频道中的阈值按新旧模型在同一校准集上的分位数映射迁移 [判断]，在迁移完成前两套向量双写（RT §12-10）。

**集合运算**：∪ ≡ Or，∩ ≡ And，A − B ≡ And(A, Not B)。`ChannelRef` 内联时只取被引频道的 `where`，丢弃它的 `rank` 与推送偏好；集合运算的结果由外层查询的 `rank` 排序。外层未给 `rank` 时，默认对各子频道的本地排序做 RRF（§8.6）。

### 3.6 规范化与 query_hash（设计伪代码）

```python
# 设计伪代码
def canonicalize(q: Query, ctx) -> tuple[Query, str]:
    q = inline_channels(q, ctx.user, max_depth=4)      # 解析 @name → (channel_id, ast_hash)；检测环
    q = lift_soft_semantics(q)                         # 无阈值 SemAtom → rank.semantic
    w = to_nnf(q.where)                                # De Morgan 下推否定，消双重否定
    w = flatten(w)                                     # And(And(a,b),c) → And(a,b,c)
    w = normalize_values(w)                            # DOI 小写去前缀；ISSN → ISSN-L；arXiv 去版本；
                                                       # topic 名 → 节点 ID；日期 → UTC 闭区间
    w = sort_commutative(w)                            # And/Or 子节点按规范序列化字典序排序、去重
    q = q.copy(where=w, window=normalize_window(q.window, ctx.now_bucket))
    q = q.copy(rank=normalize_text(q.rank))            # relevance.text：Unicode NFKC、折叠空白；保留词序与大小写原文
    blob = json.dumps(q.model_dump(exclude={"budget", "k"}), sort_keys=True, separators=(",", ":"))
    return q, sha256(blob).hexdigest()                 # query_hash：缓存键 + 复现凭据 + 日志主键
```

三处取舍：
- 相对时间窗（如"近 7 天"）按 `now_bucket`（默认 15 min [判断]）取整后再哈希，同一时段内的相同查询可以共享缓存。
- `budget` 不参与哈希：预算改变结果完整性，不改变查询的定义；完整性由完整性报告记录（§8.3）。
- 每页条数 `k` 不参与哈希：它只影响分页，不影响结果集合；否则同一查询换页大小就无法命中缓存。

`query_hash` 含个人谓词与内联频道的内容，所以它只作本人检索历史与本人结果快照的键。跨用户共享的缓存一律用不含个人谓词的子计划键 `plan_key`（§8.1、§15.4）；写入去标识日志时只存它的密钥哈希（§6.9）。

### 3.7 校验与成本预览

1. **Schema 校验**：类型、取值域、正则可编译（沿用 v1"拒载而非静默忽略"的 fail-loud 纪律，v1 `subs/model.py`）。
2. **能力可行性**：
   - `fulltext` 字段只能路由到支持全文检索的端点，或本人私有全文索引（§9.8；platform 部署默认不在服务端处理私有全文，R2-27）；
   - `Rel` 只在本地图上求值；远端只有支持相应关系过滤的端点（如 OpenAlex `cites:`）可参与；
   - 没有任何可行执行路径时，响亮报错。
3. **隐私检查**：`Personal`、`Regex` 与内联频道中的个人谓词只能在本地求值；编译器保证它们不出现在任何远端子查询中（§7.2 的不变式 I-2）。
4. **成本预览**：路由器预估远端请求数与费用。超过 `Budget.max_cost_cu` 时，交互检索提示收窄；"深度检索"类作业要求用户确认（RT §4.3.2 第 4 步）。
5. **版本**：`Query.v` 是 AST 的 schema 版本，频道另存 `ast_schema_version`（§15.1）。schema 升级时，迁移工具把存量频道逐条改写到新版本；改写前后的判定在回归样本上逐条一致才替换，否则频道进入 `needs_review`。求值器只接受当前版本与上一版本 [判断]。

**错误与降级的对外口径**（下表定义语义；其中的 HTTP 状态码是建议值，最终以 02 的 API 面为准）：

| 代码 | 触发 | 客户端看到 | 是否重试 |
|---|---|---|---|
| `invalid_query` | schema 校验失败、正则不可编译、未加括号的符号算子混用（§3.2） | 400，附出错位置与修改建议 | 否 |
| `channel_ref_invalid` | `@name` 不存在、不属于本人（§20 第 10 项）、循环引用、内联深度 >4 | 400 | 否 |
| `infeasible` | 没有任何可行执行路径（第 2 条），如 `fulltext` 条件而本人没有私有全文索引 | 422，说明缺哪种能力 | 否 |
| `preview_required` | 预估成本超过 `Budget.max_cost_cu` 的深度检索 | 409，附成本预览；用户确认后带确认令牌重发 | 确认后 |
| 降级（非错误） | 用户的联邦配额用完（§13.5）、全部远端不可用（§13.9）、LLM 超时（§4.2） | 200，仍返回本地结果；完整性报告写明降级原因 | 不适用 |

检索请求不改变语料与频道的语义状态。它的两个写入副作用都幂等：检索历史按 `query_hash` 合并为同一条记录，只更新最近检索时间 [判断]；查询即入库经 03 流水线按来源记录键去重（§8.5）。重复提交得到同一 `query_hash`，可安全重试；流式响应按事件 `seq` 续传（§8.2）。

### 3.8 与 v1 订阅 DSL 的兼容映射

v1 订阅由四部分组成（v1 `subs/model.py`、design/09 §2）：
- `sources.<源>` 专属选择器，白名单只有 arxiv、ssrn、nber、crossref 四源；
- `filters` 三键，跨源统一执行；
- `actions`；
- `guard`。

v2 中频道只读本地语料，因此 v1 的"每源选择器"改写为作品谓词。v1 的整体语义是"各源选择器结果的并集，再与 filters 做合取"，映射后保持这一结构：

```text
v1:  ⋃_src ( selector_src ∧ query_src ) ∧ filters
v2:  And( Or_src( And( src_pred, query_pred ) ), filters_pred )    # missing = closed_world
```

| v1 字段 | v2 AST | 说明 |
|---|---|---|
| `name` | `Channel.name` | 迁移后文件名 stem 与 name 一致的约束不再需要 |
| `sources.arxiv.categories` | `Facet(cat ∈ {…})` | arXiv 分类是 TSRG 原生叶子；隐含 `src=arxiv` |
| `sources.arxiv.query` | `Term(field∈{title,abstract}, mode=phrase, match=substring_ci)` 的布尔组合 | v1 只支持 `ti`/`abs` 与 OR/AND/ANDNOT（v1 `ARXIV_QUERY_FIELDS`）；ANDNOT → `And(·, Not ·)` |
| `sources.crossref.issns` | `Facet(venue ∈ resolve_issn(p/e 双号, ISSN-L))` | 期刊印本号可能已停用，须 p/e 双查（LS §3-11） |
| `sources.nber.programs` | `Facet(series=nber, nber_program ∈ {…})` | v1 只实证映射 AP/CF/EFG/IFM/ME 五个 program（design/09 §5），迁移不扩表 |
| `sources.ssrn.networks` / `ejournals` | **无等价项** → 频道状态 `needs_review` | SSRN ToU 禁止任何自动化查询（SS §3-4），v2 取不到 network/eJournal 分类。迁移工具给出 JEL/subfield 近似建议，用户确认后频道才启用 |
| `filters.title_regex_any` | `Or(Regex(title, p_i, flags=i) …)` | 仅作用于标题、不区分大小写（v1 `filter_papers`） |
| `filters.exclude_regex` | `Not(Or(Regex(title, p_j, flags=i) …))` | 同上：v1 只对标题排除 |
| `filters.min_year` | `Range(year ≥ y)` | closed_world 下年份缺失即不通过，与 v1 一致 |
| `actions.ingest` / `auto_fetch_limit` | 废弃 | 全文 fetch 已移出后台流水线（简报 §6.1-6，P-03 不预取）。personal 部署如需"OA 全文自动缓存"，作为 03 定义的偏好项 |
| `guard.max_new_per_run` | 频道推送偏好 `daily_cap` 加过载报告 | 保留 v1 FR-16 语义：超限时不刷屏，出过载报告并给出收窄建议（§12.6） |
| `guard.dedupe_against_library` | `Personal(in_library)` 的否定，默认开启 | 在 Deck 组装时求值（延迟谓词，§12.2） |
| `schedule_hint` | 频道的摘要节奏（06/07） | 收割节奏由 WatchKey 全局调度决定，与频道无关（§11） |
| `watermark_json` | 不迁移 | 水位归 WatchKey（按端点）；频道的"新"由 FeedInbox 的写入时点定义（§12.6） |
| 源专属固定谓词 `ssrn.topic_filter` | 不迁移 | 依赖的 `openalex_field` 信号在 v1 生产路径上本就未接线，v1 以放行兜底（v1 `subs/filter.py`） |

迁移示例（v1 预置包 llm-agents 的 arXiv 段）：

```text
# v1（design/09 §2 示例一，arXiv 部分）
categories: [cs.AI, cs.LG, cs.CL, cs.MA]
query: (ti:"agent" OR abs:"agentic" OR abs:"tool use") AND NOT ti:"survey"
filters: {title_regex_any: ["\\bagent(s|ic)?\\b", "LLM"], exclude_regex: ["quantum"], min_year: 2024}

# v2 频道 where（missing = closed_world；设计伪代码）
And(
  Facet(cat ∈ {cs.AI, cs.LG, cs.CL, cs.MA}),
  Or(Term(title,"agent",phrase,substring_ci), Term(abstract,"agentic",phrase,substring_ci),
     Term(abstract,"tool use",phrase,substring_ci)),
  Not(Term(title,"survey",phrase,substring_ci)),
  Or(Regex(title, r"\bagent(s|ic)?\b", i), Regex(title, "LLM", i)),
  Not(Regex(title, "quantum", i)),
  Range(year ≥ 2024)
)
```

**兼容性验证**：迁移工具把 v1 的 9 个预置包和用户订阅逐一翻译。在 v1 AC-6 的 fixture 与预置包回归样本上，v2 谓词的判定必须与 v1 `filter_papers` + `arxiv.query_bool` 逐条一致（AC-V2.2）。迁移后，用户可以在界面上把频道切到 `kleene` + `analyzed` 的 v2 语义；切换前系统展示两种语义下的结果差异样本。

两点实现约束：
- **正则引擎**：`Regex` 文字用 Python `re`（`IGNORECASE`）在应用层求值，与 v1 同一引擎。v1 预置包的 `title_regex_any` 与 `exclude_regex` 普遍使用 `\b` 词边界（如 `subscriptions/presets/llm-agents.yaml` 的 `\bagent(s|ic)?\b`、多个预置包的 `\ba survey\b`）。PG 正则里 `\b` 是退格符（§3.3），交给 `~*` 求值会让这些条件静默失配：`title_regex_any` 拒掉一切，`exclude_regex` 什么也排除不了。
- **"逐条一致"的范围**：一致性针对同一条记录的判定。v2 在 cluster 合并后的字段上求值，预印本与正式版的标题、摘要可能不同，所以系统级结果可以与 v1 不同。迁移报告列出这类差异样本，不把它们算作不一致。

---

## 4. 意图与解析流水线

### 4.1 五意图

前四个意图取自简报 §6.2-1；EXPAND 取自 RT §4.3.1 与 SI-24，01 §16-5 把"是否独立成意图"交由本文决定，本文将其设为第五意图，理由见 §19-13。显式意图路由的开源先例只有 Asta PaperFinder（OSS §2.5、§2.12(c)），它把查询路由到若干"找论文意图"工作流之一，调研未记载具体个数。OSS §3-2 参照它为 v2 建议了四类工作流（known-item、metadata、content、feed），与本文的前四个意图一一对应。

| 意图 | 定义 | 规则快路径的触发条件 | 默认 rank | 默认 scope | 执行路径 |
|---|---|---|---|---|---|
| LOOKUP | 精确找某一篇 | 输入整体是一个标识符（DOI、arXiv 新旧两代 ID、PMID、PMCID、SSRN id、OpenAlex W id，或可解析出 ID 的 URL）；或为引号包裹、≥6 个词的类标题串 | 精确度 | auto | 本地标识符索引 → 同能力替补链（§8.4） |
| SEARCH | 关键词与元数据检索 | 缺省意图 | relevance（BM25 ⊕ dense，RRF） | auto | 本地混合检索；按 §6.3 判据决定是否联邦 |
| SIMILAR | 语义相似 | 含"相似 / similar to / like:"加种子；或输入是长文本（>200 字符 [判断]） | semantic | auto | 本地 ANN + 可选远端语义源（§4.6） |
| LATEST | 新论文 | 含时间表达（"最新""本周""近 N 天"/latest/new/this week），且其余内容只有主题、分类、venue、频道类过滤 | recency；登录且开启个性化时为 personal | **local（强制，P-01）** | 分面位图 ∩ 时间窗 → 排序（§10.2） |
| EXPAND | 引文扩展 | "cites / cited by / 引用了 / 被…引用 / 参考文献"加 ID；或在卡片上点"从这篇扩展" | 图分（耦合、共被引） | auto | 本地图 ≤2 跳 + 远端引文源（§4.6） |

短关键词串可能是标题。此时 SEARCH 照常执行，同时并行做一次本地标题三元组匹配。若 top-1 相似度 ≥0.9 且无并列 [判断]，在结果顶部置入"精确匹配"条目。这样不必先猜对意图，也不增加远端请求。

空查询（没有文本，也没有任何筛选条）不进入解析与路由。搜索层的空查询态就是"发现"入口（R2-49），内容由 06 的推荐管线提供；04 只在用户开始输入或加筛选条后接管。

### 4.2 解析四步与投机首屏

```python
# 设计伪代码 —— 交互道；时间预算为 [判断]，由压测校准
async def handle_query(text, ctx) -> ResultStream:
    ast0, chips0 = fast_parse(text)                  # ① 规则快路径 ≤20 ms：ID 正则、字段前缀、引号短语、
                                                     #    布尔算子、时间表达、分面词典（venue 缩写、arXiv 类目、JEL 码）
    ast0 = link_entities(ast0, ctx)                  # ③ 快路径抽出的名字先链接（只链库内 ID）
    q0, h0 = canonicalize(ast0, ctx)
    stream = ResultStream(query_hash=h0, chips=chips0)
    first = stream.run(execute(q0, ctx, speculative=True))   # 投机首屏（后台任务）：只读本地、不出网、不等 LLM；
                                                             #    await first 得到本地召回列表（召回完成即可用）
    q = q0                                           # 定稿 AST：默认即快路径结果
    if llm_enabled(ctx) and needs_llm(text, ast0):   # ② 可选：自然语言样式或快路径置信度低；区域策略放行（§4.5）
        ast1 = await with_timeout(llm_parse(text), GRACE_MS)   # 与首屏并行；GRACE_MS 默认 1,500 [判断]
        if ast1 is not None:
            ast1 = link_entities(ast1, ctx)                     # ③ LLM 只给名字，ID 一律由链接器给出
            q1, h1 = canonicalize(ast1, ctx)
            if h1 != h0:
                if stream.user_idle() and stream.elapsed_ms() < GRACE_MS:
                    q = q1                                      # 采纳 LLM 的理解：本地结果随后以 upgrade 原位替换
                    stream.set_chips(to_chips(q1))
                else:
                    stream.suggest(chips=to_chips(q1))       # ④ 以建议筛选条呈现："按此理解重新检索？"
    stream.run(execute(q, ctx, first_screen=first))  # 定稿后才路由与联邦（§8.2）：远端费用只花在定稿 AST 上
    return stream
```

- **①规则快路径**：
  - 标识符正则沿用 v1 的 arXiv 新旧两代 ID 兼容（RT §4.3.2）；
  - 时间表达覆盖中英两种写法（"2023 年以来""近三个月"/since 2023/last week）；
  - 分面词典是本地的小型词表（venue 缩写、arXiv 类目、JEL 码、学科中英名），不查远端；
  - 快路径失败时，把整串当作 `any` 字段词项。
- **投机首屏**：LLM 解析期间先用快路径 AST 跑本地 BM25 与向量检索，保证首屏延迟（RT §4.3.2 第 5 步）。首屏只读本地，不产生远端费用。
- **定稿后联邦**：路由与联邦只对定稿 AST 执行，远端费用不花在可能被 LLM 改写的 AST 上。
  - 不需要 LLM 时（默认配置），定稿即快路径 AST，本地召回一完成就路由；
  - 需要 LLM 时，等其返回或宽限期满再路由。联邦总截止仍从请求到达起算，不顺延 [判断]；
  - 路由的 p_r 取首屏命中中共享层、个人谓词与个性化之前的部分（§6.2）。定稿与首屏是同一 AST 时，本地结果直接复用，不重跑（§8.2）。
- **②LLM**：可选、异步，不阻塞首屏（P-07）。约束见 §4.5。
- **③实体链接**：见 §4.3。
- **④筛选条**：见 §4.4。筛选条的每次编辑都生成新 AST 与新 `query_hash`。执行器按子计划键（`plan_key`，§8.1）复用缓存中的子结果，所以编辑后的重查是增量的。

结果替换遵循"用户已看到的不乱跳"：用户未交互且仍在宽限期内，才允许原位升级；否则只给建议。与 07 的交互约定见 §8.2 的流式事件。

### 4.3 实体链接

| 实体 | 库内来源 | 链接方法 | 自动链接条件 [判断] | 歧义时 |
|---|---|---|---|---|
| Venue | venue 名称、缩写、全部 ISSN（p/e、历史号）、OpenAlex source id、DBLP key | pg_trgm 相似度（RT §6.3）+ 名称嵌入近邻；ISSN 精确 | top-1 ≥0.92 且与 top-2 的差距 ≥0.08 | 候选筛选条（≤5 个） |
| 主题节点 | OpenAlex topic/subfield/field 名，原生叶子名，中文名词表（PU §2.4：中文展示名由词表维护） | 同上，另加节点质心近邻 | 同上 | 候选筛选条；同时保留一个 `any` 词项作兜底 |
| 作者 | 作者表（ORCID、OpenAlex A id） | 姓名规范化 + 合作者、venue 上下文 | **不按姓名单独自动链接**（重名普遍） | 必须由用户选 |
| 机构 | ROR（CC0，AG §2.3.4） | 名称与别名 | 同 venue | 候选筛选条 |

链接器**只输出库内已有 ID**，从不生成新 ID。这就排除了 LLM 虚构 venue 或作者的风险（RT §13-10）。链不上的名字保留为 `Term(any, name)`，关键词兜底，不丢失意图。

### 4.4 可编辑筛选条契约（04 ↔ 07）

规范化 AST 的每个顶层合取项渲染为一个 FilterChip。映射规则：
- OR 组 → 一个复合条（"任一：A / B / C"）；
- NOT → "排除：…"；
- `window` → 时间条；`scope.via` → 来源条；`rank` → 排序条；
- `rank.relevance.text` → 检索词条，标"软条件"，可一键转为"须包含全部词"的硬条件；频道和非相关性排序下裸词已编译为硬 AND 门时，直接显示为"须包含"条（§3.2）；
- 另设"关闭个性化"条（HC-13）。依据 DSA 第 27(3) 条正文，该设置须能在信息流界面直达（UX 核验修正）。

```json
{
  "chip_id": "c3",
  "ast_path": "where.and[2]",
  "kind": "venue",
  "label": {"zh": "期刊：Journal of Financial Economics", "en": "Venue: JFE"},
  "op": "in",
  "value": {"venue_ids": [4021]},
  "editable": true,
  "removable": true,
  "alternatives": [{"label": {"zh": "…"}, "value": {"venue_ids": [5170]}, "score": 0.71}],
  "provenance": "rule | llm | linker | user | channel",
  "confidence": 0.93,
  "flags": ["approx_taxonomy", "unverified_field", "semantic_soft"]
}
```

契约约束：
- 前端只能通过"编辑、删除、选择候选、接受建议"四种操作改 AST，不得自行拼接查询；
- 每个筛选条的 `label` 由后端按词表给出，前端不翻译；
- `flags` 是完整性报告在筛选条上的呈现：例如某条件在部分结果上"未能确认"，对应 §3.5 的 U。

### 4.5 LLM 结构化输出（可选组件）

1. **部署与区域**：
   - T1 默认关闭。T1 默认不配 GPU（R2-45），CPU 上的自托管 LLM 难以在 `GRACE_MS` 内返回，启用前须压测；
   - 启用时只用自托管模型。查询文本属于用户数据，可能暴露研究方向；R2-45 只放行"只处理开放内容的论文侧预处理"使用第三方 API，查询解析不在此列，所以不发往第三方 LLM API [判断：按 R2-45 的从严读法，§20 第 27 项请主 agent 确认]；
   - 自托管满足 P-07 与 R2-45 的路由要求，查询文本也不出境（HC-22）。但自托管本身不等于"已备案"：CP §2.2.3 与 HC-12 要求面向中国境内用户的生成式服务使用已备案模型、完成地方登记，并公示模型名称与备案号。所以面向境内用户开放时仍须满足 HC-12 与 HC-21 的前置条件（Q2 默认"否"，T1 不涉及）。
   - 模型的权重许可须过 B-06 门禁（§1.6）。
2. **受约束解码**：以 AST 的 JSON Schema 约束输出，自托管时用 outlines、xgrammar 或 llguidance（Apache-2.0/MIT，RT §4.3.2）。
3. **输出内容**：LLM 只输出结构和名字，ID 由 §4.3 的链接器给出。提示词中**不含**用户画像或历史，只含本次查询文本与 schema，避免私有数据进入第三方模型。
4. **失败处理**：校验不通过即丢弃，快路径结果照常有效。
5. **缓存**：以规范化查询文本为键缓存 AST（RT §4.3.2 第 6 步），按语言分桶。
6. **中文查询**：LLM 同时产出英文检索词，原文保留给多语向量通道（RT §4.3.2）。

### 4.6 SIMILAR 与 EXPAND 的补充规则

**SIMILAR**：

1. **种子向量**：单个种子直接用其嵌入。多个种子时，对每个种子分别做 kNN，再用 RRF 融合，不求平均。多兴趣种子取平均会"平均成谁都不像"（SR §2.8）。可选负种子：把负种子近邻从结果中降权。
2. **本地检索**：本地 ANN 在检索索引上召回（索引维度随 Q7 的选型，§9.3）；索引维度低于全维时，对候选做全维精排。
3. **远端补充**：
   - OpenAlex `search.semantic`：GTE-Large 1,024 维，单次 ≤50 条，1 req/s，只看输入前 2,000 字符，按搜索计价（RT §2.2）。若本地也选 gte-large（简报 Q7 候选），远端结果可在同一向量空间重打分（SR §0-5）。该功能仍是 beta，官方不建议用于敏感生产（AG §2.4 R7 ⚠），所以只作补充，失败即跳过。
   - S2 Recommendations：接受正负论文 ID，单次最多返回 500 条，key 限 1 RPS（AG §0-4）。这 1 RPS 由 S2 的全部端点共用，包括标题匹配、成员探测与引文（AG §2.2.3）；AG §3-11 的结论是它只能作离线或批量基线，不能给多用户实时调用。本文只在用户显式发起的 SIMILAR 中低频调用它，交互道份额用尽即跳过，并在完整性报告中标注缺源。
   - 因此语义探索链的两级远端都承接不了稳定的交互流量，这条链上 P-09 的"两级替补"实际由本地 ANN 兜底（§8.4）。
4. **隐私约束**：远端相似检索**只在用户显式发起时**发送种子 ID。后台推荐（06）不得把用户库中的论文 ID 发往第三方。

**EXPAND**：

1. **本地图**：参考文献（出边 1 跳）、被引（入边 1 跳）、文献耦合（出→入 2 跳）、共被引（入→出 2 跳）。老论文直接读夜间批算的近邻表（§9.7）。新论文只有参考文献，文献耦合对它们立即可用，共被引依赖未来的引用、对它们天然不利（SR §0-6）。
2. **远端**：OpenAlex `cites:` 过滤（列表计价），OpenCitations（CC0，180 次/分钟/IP，AG §2.3.3），S2 citations（key 1 RPS）。同一论文在不同源的被引数不一致（OpenCitations 9,262 对 OpenAlex 10,801，AG §3-19），因此结果合并时不相加被引数。
3. **深度模式**（可选，后续里程碑）：参照 PaSa 的"检索—阅读—沿引文扩展—逐篇判定"范式，做成异步、可取消、事先预览成本的作业（RT §4.4、OSS §2.5.1）。LLM 部分只在近线运行；它以用户的查询为输入，按 R2-45 只用自托管模型。输入与输出另有三条约束：
   - LLM 读入的论文文本只取 §9.1 中 CE 输入为 ✓ 的字段，即书目元数据、A 类摘要、S2 TLDR，以及按 R2-21 默认纳入的 B 类摘要（08 规定 B 类摘要只进自托管模型，与此一致）；
   - C 类与出版商 API 内容（IEEE、Elsevier、SN）一律不输入（HC-11(c)）；来源带 Content-Signal `ai-input=no`、TDMRep 保留或具名禁止 AI UA 的，也不输入（HC-11(b)，CP §2.2.3）；
   - 逐篇判定的结果是本人查询的派生物，只存本人域，不进共享缓存与任何全局统计（P-02、HC-01）。

---

## 5. TSRG 规格

TSRG 回应的是用户所说的"图/树算法"：
- 树：OpenAlex Topics 骨架与学科原生分类，负责把查询、论文和用户映射到同一坐标系；
- 图：主题—来源—能力的带权二部结构，负责回答"这件事该问谁、多久问一次、新论文该给谁"。

两者合在一张图里，一次维护，服务四件事（§5.7）。结构图见 [v2-04-tsrg.svg](../../diagrams/v2-04-tsrg.svg)。

### 5.1 节点

| 节点类 | 内容 | 规模 | 来源与许可 | 存储域 |
|---|---|---|---|---|
| TopicNode（骨架） | OpenAlex domain → field → subfield → topic | 4 / 26 / 252 / 4,516，合计 4,798 | OpenAlex 快照 CC0（SR §2.11）。编号：field 为 11–36，subfield 最大 3616，topic 最大 T14521，均可入 `smallint`（RT 核验 V07、SR §2.11） | corpus |
| 原生叶子 | 默认：arXiv 类目、JEL、PhySH、MeSH、ACM CCS；可选插件：MSC2020 | arXiv 155 个类目（PU §0-8 口径）；JEL 1,015；PhySH 3,882；MeSH 30,594 个主题词；ACM CCS 2,299。默认合计约 3.8 万（37,945）；加载 MSC2020 插件（6,603 行）后约 4.45 万 | arXiv 类目 CC0；PhySH CC0；JEL 为 AEA 官方公开 XML（SR §2.11），再分发许可调研未核 ⚠，内置前按 B-06 核验（§1.6）；MeSH 公开，须标版本（LS §3-9）；**MSC2020 为 CC BY-NC-SA：按 R2-22 不作默认叶子，作可选插件，默认不加载（非商业部署也不加载）；数学子树用 arXiv math 分类 + OpenAlex topics**；ACM CCS 数据取自第三方镜像，官方页 403，许可 ⚠（SR §2.11）；APA PsycInfo 分类码受许可限制，不内置（LS §3-9） | corpus |
| 用户标签 | 用户自建标签，映射到共享节点 | 每用户数十个 [判断] | 用户数据 | **usr 覆盖层**（RLS）。不进共享快照，不参与任何全局统计（P-02；§19-5） |
| Venue | 期刊、会议、WP 系列；多键归一（ISSN 集合、ISSN-L、OpenAlex source id、DBLP key、OpenReview 前缀），带演化边 | 起步数千 | 03 的 SourceSpec；会议实体不依赖 OpenAlex（NeurIPS 在 OpenAlex 会议实体下只有 4,177 条，AG §0-10） | corpus（03/05 定义） |
| SourceEndpoint | 各 Source 在某个来源通道下的可调用端点 | ≤50（RT §3.5.6） | 03 的 SourceSpec 与 SCD | 03 的来源注册表（SCD） |
| Capability | `kw.bool`、`kw.phrase`、`kw.near`、`kw.field.*`、`sem.search`、`filter.date.*`、`filter.topic`、`filter.venue`、`filter.type`、`filter.oa`、`id.lookup.<scheme>`、`incr.since`、`sort.recency`、`rel.cites`、`rec.pos_neg` 等 | 数十 | SCD 词表（03；RT §3.5.1） | ops |

骨架中 OpenAlex 部分是树，但整体是 **DAG**：MeSH 一个概念可以有多个树号（LS §3-9），ACM CCS 有 98 个多父节点（SR §2.11）。TSRG 的上卷与平滑按 DAG 处理：多个父节点时按 `maps_to` 置信度分摊权重。

粒度不均是分类骨架的已知缺陷。例如 Economics, Econometrics and Finance 只有 3 个 subfield，Medicine 有 42 个（SR §2.11）。因此经济金融挂 JEL、数学挂 arXiv math 类目（MSC2020 只在加载可选插件时参与，R2-22）、物理挂 PhySH、生医挂 MeSH、CS 挂 ACM CCS 与 arXiv 类目，这些原生叶子承担细粒度的兴趣与过滤。表面语法的 `msc:` 分面只在插件加载时可用，未加载时解析器按 `infeasible` 报错，并提示改用 arXiv math 类目（如 `cat:math.PR`）或对应的 OpenAlex topic（§3.7）。经管的学科路由另有 ABDC FoR 码与 EconBiz STW 两条轴（SS §3-6）。ABDC 站点声明版权所有，并称第三方的可检索版本未经授权（SS §3-10）；EconBiz STW 词表的许可调研未核 ⚠。两者内置前都须确认许可，列为后续扩展。

### 5.2 边与权重

| 边 | 方向 | 权重与属性 | 含义 | 生产者 |
|---|---|---|---|---|
| `is_a` | 子 → 父 | 1 | 分类层级 | 各分类体系 |
| `maps_to`（05 DDL 中记作 `crosswalk`） | 原生叶子 → OpenAlex 节点 | conf ∈ [0,1] | 跨体系对齐。Science Data Lake 用句向量映射，阈值 ≥0.85 时 F1 为 0.77（RT §6.2），因此须人工审核 | 离线对齐作业 |
| `venue_topic` | Venue → 节点 | share、n、window | venue 的主题画像 | 作品主题标注的聚合 |
| `work_topic` | 作品 → 节点 | score、origin | 作品的节点标注。来源：OpenAlex ≤3 个 topic、本地分类器、原生叶子、venue 先验 | 03 enrich |
| `route_stat` | 节点 → 端点 | cov、lag、λ、uniq、fidelity，分窗口 `recent90` 与 `all`；η 概念上属于同一条边，但它由用户查询的结果算出，后验按 05 存于聚合区（§5.4） | 见下文定义 | §5.3 |
| `served_by` | Venue → 端点 | role ∈ {metadata, latest, fulltext}、lag、ladder_rank | venue 由哪个端点承担哪种职能；latest 通道按新鲜度阶梯排序（CS §2.6.5） | 03 SourceSpec |
| `supports` | 端点 → 能力 | 支持等级 native / native_approx（带 `analyzer`）/ emulated / none（03 的 SCD 口径），及 fidelity | 能力矩阵（AG §2.4.2 的 SourceCapability 形态） | SCD（03） |
| 端点属性 | — | cost（$/次与翻页模型）、politeness（最小间隔、书面并发与速率上限）、health（成功率 EWMA、p95、熔断态）、budget_remaining、policy_mode、exec_side | 路由与调度的成本侧 | SCD、出站网关、策略引擎 |
| usr 覆盖边 | 用户、频道、WatchKey → 节点 | w_long、w_short、anchor、refcount | 兴趣与订阅挂点 | usr（RLS），不入共享快照 |

`route_stat(n, s, W)` 各分量的定义。U_{n,W} 表示主题为 n、处于窗口 W 内的作品全集，其估计方法见 §5.3：

- **cov**：U_{n,W} 中被端点 s 收录的比例，即 P(w ∈ s | w ∈ U_{n,W})，按 Beta 后验存储。
- **η**：检索有效率。给定作品在 s 中、且与查询相关，s 的（放宽后）查询在取回页内返回它的概率。η 吸收了源的检索质量、放宽损失和分页截断，由日志学习（§5.3）。
- **lag**：作品最早公开到在 s 中可见的时差分布，记 p50 与 p90。
- **λ**：主题 n 的新作品经端点 s 到达的速率，单位篇/天，Gamma 后验。
- **uniq**：U_{n,W} 中只有 s 能提供、平台其他收割端点都没有的比例。
- **fidelity**：s 对 n 类作品的字段完整度，如摘要、许可、参考文献覆盖。依据之一是 Crossref 摘要覆盖的学科差异：心理 0%，经济 85%（AG §2.6）。

### 5.3 统计估计

**全集估计 Û_{n,W}**：
- 主估计取 OpenAlex 计数：快照离线计算或 `group_by`。OpenAlex core 语料有 3.27 亿 works（AG §0-3），约 12% 没有 topic，由本地分类器补标（简报 §6.6）。
- 对 OpenAlex 覆盖或归一化偏弱的领域（会议实体碎片化，AG §0-10；SSRN 走 Crossref 前缀，D-029），取 max(OpenAlex 计数, 本地溯源计数)。
- 两个近似独立的源重叠时，可以用捕获—再捕获估计 Û = n₁n₂/m 作合理性上界 [判断]。学术源之间的独立性常不成立，该估计只作告警参考，不直接入统计。

**覆盖素描（Coverage Sketch）**：
- **样本框**：样本必须取自与本地语料无关的框。若从本地语料抽样，本地位恒为 1，cov_local 恒为 1，联邦永远不会触发。两个窗口分别处理：
  - `all` 窗口：对每个 OpenAlex 节点（4,798 个），从季度快照中均匀抽 M 篇（M=256 [判断]），零 API 成本；
  - `recent90` 窗口：季度快照最多滞后一个季度，覆盖不了近 90 天，因此改为每周经 OpenAlex API 的 `sample` 参数（AG §2.2.2 列出该参数）按 subfield 与 `publication_date` 窗口抽样。只建到 subfield 级（252 个），与路由主分辨率一致；topic 与叶子经上卷使用 subfield 的素描。成本约 252 × ⌈256/100⌉ ≈ 760 次列表调用/周，按列表价约 $0.08/周 [估算]，计入 OpenAlex 的 enrich 道美元份额（§13.1）。
  - 已知偏差：样本框只含 OpenAlex 已收录的作品。OpenAlex 自身的入库滞后使最近几天的作品在框中不足；OpenAlex 缺失的作品（例如部分 WP）不在框内，只收录它们的端点的增益被低估。前者只影响 SEARCH 的近期查询（LATEST 不联邦）；两者都由 uniq 统计与 §14.1(a) 的穷举评测监控 [判断]。
- **抽样与存储**：对每个节点 n 与窗口 W，在上述样本框中抽 M 篇样本。每篇样本记一个成员掩码，第 s 位表示"已知该作品被端点 s 收录"：
  - 第 0 位固定为本地位 `local`（该作品已在本地语料），它是联邦判据 cov_local 的输入（§6.3）；
  - 端点位按快照元数据中的位序分配。T1 端点 ≤50，一个 64 位字够用；超过 63 个端点时按 64 的倍数加宽；
  - 同时保存样本作品的 OpenAlex W id（M × 8 字节）。成员探测、本地位刷新与掩码重建都要按 ID 对账，只存位图则无法完成这些作业（DDL 见 §5.4）。
- **掩码来源**：
  1. 本地溯源：`corpus.source_record` 记录我们从哪些源拿到过该记录（RT §10.2）；
  2. 快照派生：OpenAlex 记录的 locations 与 ids 可推出 arXiv、PubMed（有 PMID）、PMC（有 PMCID）、SSRN 等成员关系；
  3. 成员探测：只查询不收割的端点（如 S2）用批量 ID 查询探测。S2 `/paper/batch` 每次 ≤500 个 ID，限 1 RPS（AG §2.3.2）。`recent90` 每周约 252 × 256 ≈ 6.5 万个样本，约 130 次调用；`all` 窗口 4,798 × 256 ≈ 123 万个样本，约 2,460 次调用，按 1 RPS 约 41 分钟 [估算]，随季度快照做一次，按节点分批排在非高峰时段的 enrich 道内执行。
- **用途**：素描使任意端点集合 S 的并集覆盖都可估计（§6.4），解决了 `group_by` 计数只有边际、没有重叠信息的问题。两者口径不一致时，以 `group_by` 的边际对素描做重加权 [判断]。
- **刷新**：
  - 样本与端点位：`recent90` 窗口每周重抽样本并重建端点位，`all` 窗口随季度快照更新；`recent90` 窗口的 route_stat.cov 也取自这份独立样本，不取自本地溯源（后者只含本地已有的作品，会高估覆盖）；
  - 本地位：每日按样本 ID 与本地 `corpus.identifier` 对账刷新（作业 `sketch_local_refresh`，§5.5）。本地语料每日新增 1–3 万篇（B-04），本地位若跟着端点位周更，近期窗口的 cov_local 会系统性偏低，引发不必要的联邦。

**各分量的估计方法**：
- **cov**：Beta(a₀ + 命中数, b₀ + 未命中数)，a₀ 与 b₀ 取父节点收缩后的先验。
- **η**：Beta 后验，从路由日志学习，观测口径为"已知成员召回"，与 §5.2 的定义一致：
  - 对一次选中了端点 s 的联邦查询，取最终 top-k 中通过残差的结果集合 T，作为相关集合的代理。T 取个人谓词过滤与个性化挂点**之前**的非个性化排序：`Personal` 文字（已见、在库、评分）与 `personal_score` 只作用于返回给本人的列表（§8.8），不进入 T。否则 η 会随提问者的已见集合与画像变化，而 η 进入全局路由（R2-40、HC-01）；
  - T_s = T 中"已知被 s 收录"的作品。判定口径与素描掩码的来源相同：本地溯源、标识符推断（如有 PMID 即在 PubMed）、快照派生；无法判定的作品不计入；
  - 成功数 = T_s 中由 s 实际取回的篇数，试验数 = |T_s|；按作品的节点标注计入对应"端点 × 节点"格子：a += 成功数，b += 试验数 − 成功数。
  - **不用"独有贡献"作奖励**。独有与否取决于同时被选的其他端点。若按独有贡献学习，与 OpenAlex 高度重叠、又总与它同选的端点（如 S2）的 η 会被压向 0，重叠被扣了两次：素描的并集结构已经扣过一次。等到 OpenAlex 当日额度耗尽而被剔除时（§13.1、§13.9），路由器会低估正该顶上的替补端点。独有贡献仍然写入日志，用作评测指标（§14.1）和 GBDT 特征（§6.9）。
  - 已知偏差：T 只含本次被选端点与本地能找到的作品，s 漏掉、别的端点也没取回的相关作品不可见，η 因此偏高。离线的全源穷举基线（§14.1(a)）用来校准这项偏差。
- **λ**：Gamma(α, β)，单位篇/天。每次观测到 Δt 天内 n 篇新作，更新 α ← γα + n，β ← γβ + Δt。遗忘因子 γ = 2^(−Δt/h)，半衰期 h = 30 天 [判断]。后验均值为 α/β。
- **lag**：近 180 天、节点 n 内的作品，按 `first_seen_via_s − first_public` 计经验分位数。
- **层级收缩**：θ_n = (n_obs·θ̂_n + α_s·θ_parent)/(n_obs + α_s)，α_s = 20 [判断]（RT §6.2）。topic 级样本不足时，逐级回退到 subfield、field。

回退有具体依据：OpenAlex 开源的标题+摘要分类器在 4,516 类上的训练集准确率只有 0.4846（PU §2.4），topic 级标注噪声大。因此路由统计的**主分辨率取 subfield（252）**，topic 级只在样本充足时参与。

**建模假设**：f 的乘积形式（§6.1）假设"给定作品被收录，各端点是否取回它"相互独立。实际多为正相关：同为关键词检索的端点，会对同一种措辞差异一起失配。因此 f 会高估多源并集的召回，选源因此偏向多选。η 按"端点 × 节点"学习，只吸收边际效果，吸收不了这种相关性；偏差由 §14.1(a) 的穷举评测按学科校准，τ_cov 与 EPS_GAIN 随之调整 [判断]。

### 5.4 存储：与 05 DDL 的映射与增补需求

TSRG 的持久化以 05 的 DDL 为准（05 §3.1.6、§3.1.7、§3.2、§3.4）。下表把本文的概念映射到 05 的表，并列出 04 需要 05 增补的列或表：

| TSRG 概念 | 05 的表 | 04 的增补需求 |
|---|---|---|
| TopicNode 与原生叶子 | `corpus.topic_node`：scheme 含 oa_domain…oa_topic 与 arxiv、jel、msc2020、physh、mesh、acm_ccs；另有 `centroid`、`license_code`、`commercial_ok` 列 | 无。`node_id` 由 05 分配。pgvectorscale 的标签过滤用 OpenAlex 原生编号（subfield ≤3616、topic ≤14521，可入 smallint），不用 `node_id` |
| `is_a` 与 `maps_to` 边 | `corpus.topic_edge`：`kind` ∈ {is_a, crosswalk}，带 `method` 与 `reviewed` | 本文的 `maps_to` 即 05 的 `crosswalk`，置信度记在 `weight` |
| 作品标注 | `corpus.work_topic`，含 `(node_id, score DESC)` 倒排索引 | 无 |
| 节点质心 | `corpus.topic_node.centroid` 与 `centroid_model` | 无 |
| route_stat | `corpus.route_stat`：coverage、unique_contrib、lag p50/p90、λ 的 Gamma 参数、`ts_alpha/ts_beta`、`win`、`fidelity`、`sample_n`、`stat_origin` | 窗口维与 `fidelity` 已由 05 采纳（05 §3.1.7）。`ts_alpha/ts_beta` 只存非个人先验，如 §6.10 的 LLM 零样本先验 |
| η 后验 | `evt.agg_route_eta(endpoint, node_id, a, b, n_users, k_applied)`（05 §3.3.5） | 由 `pc_sys_aggregator` 经聚合闸写入：某格子当日的不同用户数（按 `day_token` 计）达到 `k_cf` 才写入，否则顺延。检索服务每日载入内存，路由时与快照合并（05 §3.1.7）。输入口径按 §5.3 的"已知成员召回"，不用"独有贡献" |
| 覆盖素描 | `ops.coverage_sketch`（05 §3.4 ⑨） | 需增列 `sample_ids`（见下），供成员探测、本地位刷新与掩码重建按 ID 对账 |
| 快照登记 | `ops.tsrg_snapshot`（05 §3.4 ⑨） | 无 |
| 源端点与 SCD | 03 的来源注册表；`route_stat.endpoint` 为 SCD 的端点 id（文本） | 路由所需的端点属性由 03 的 SCD 提供：能力位、成本、礼貌上限、分析器档案、`exec_side`。策略结论读 05 的 `ops.policy_snapshot.mode`，按 R2-09 直接用 03 §6.2 的五档全序 `deny < link_only < user_side < on_demand < background`，外加 `needs_confirmation` 标志；不读 05 视图派生的 verdict 词表（该词表把 on_demand 与 user_side 合并为 user_triggered_only，对路由不够用）。交互联邦与 LOOKUP 要求本端点该操作的模式 ≥ on_demand（03 §6.2 的操作表），WatchKey 收割要求 = background（§11.1） |
| 兴趣挂点（usr 覆盖层） | `usr.interest_node_weight`：horizon 分 long 与 short，另有探索臂的 Beta 参数 | 无；语义归 06 |
| 用户标签 | `usr.user_tag`：经锚点挂到 `topic_node`，不进 corpus | 无 |
| 频道与 WatchKey | `usr.channel`、`usr.channel_watch`、`ops.watch_key`、`ops.corpus_scope` | 见 §11.1、§15.1 |

`route_stat` 只从非个人数据计算：入库日志、OpenAlex 统计与快照。凡由用户查询或行为派生的路由信号（η、收藏与打开等后验信号）都须先经过 05 §2.5 的聚合闸，产物放 `evt.agg_*`，不写入 `route_stat`（05 §3.1.7）。这与 §6.8 的 k 匿名要求一致。

TSRG 的两张运维表已由 05 落表（05 §3.4 ⑨）。本文对覆盖素描表另有一项增列需求（设计伪代码 DDL，定稿归 05）：

```sql
-- 设计伪代码 DDL：ops.coverage_sketch（05 §3.4 ⑨）及本文增列（定稿归 05）
CREATE TABLE ops.coverage_sketch (
  node_id     integer NOT NULL REFERENCES corpus.topic_node,
  win         text NOT NULL,               -- recent90 | all
  member_bits bytea NOT NULL,              -- M × 8 字节：每个样本一个 64 位掩码；第 0 位为本地位，其余位序记在快照元数据
  sample_ids  bytea NOT NULL,              -- 增列：M × 8 字节的 OpenAlex W id（整数部分），与 member_bits 按样本对齐
  built_at    timestamptz NOT NULL,
  local_refreshed_at timestamptz,          -- 增列：本地位最近一次对账刷新的时间（§5.3）
  PRIMARY KEY (node_id, win)
);
-- ops.tsrg_snapshot 以 05 §3.4 ⑨ 为准（version、built_at、blob_key、checksum、notes；保留最近 3 版），本文无增列
```

**内存快照**（只读、版本化，`tsrg_version = YYYYMMDD.n`）包含：
- 节点数组、`is_a` 与 `maps_to` 的 CSR；
- OpenAlex 节点的质心矩阵（float16，N × 256）；
- `route_stat` 稠密张量（N_openalex × E × 2 窗口 × F 分量）加叶子的稀疏表；
- 素描矩阵（uint64，N × 2 × M）；
- 端点摘要：能力位图、成本参数、礼貌上限、分析器档案、policy_mode、exec_side。

快照序列化为单个二进制包，存对象存储或 PG 大对象，带校验和。检索服务启动时加载，更新时原子替换引用。**变化快或来自聚合区的量不进快照**：
- 健康度、熔断态、余量、实时 λ 读自出站网关与调度器的在线状态，路由时合并；
- η 后验每日从 `evt.agg_route_eta` 载入（检索服务以 `pc_app` 只读聚合区，05 §4.1）；格子缺失时回退到 `route_stat.ts_alpha/ts_beta` 的非个人先验，再回退到父节点；
- 本地位随素描表每日刷新，检索服务每日重载素描矩阵；
- venue、系列与 arXiv 类目的完整区间每日由 `scope_complete_daily` 算出并载入（§5.5、§6.3）。

每条路由决策记录它用的 `tsrg_version` 与 η 载入日期（P-08）。

### 5.5 更新作业

| 作业 | 频率 | 输入 | 输出 | 成本 |
|---|---|---|---|---|
| taxonomy_sync | 季度；MeSH 年度；PhySH 随发版 | OpenAlex Topics 快照与各原生词表 | `topic_node`、`is_a` | 离线 |
| mapping_align | 季度，及词表变更时 | 节点名称与描述的嵌入 | `maps_to`；低于阈值者进人工审队列 | 离线（方法参考 SDL，RT §6.2） |
| work_tagging | 作品入库时（03 enrich） | OpenAlex topics、本地分类器（补标无 topic 的约 12%，简报 §6.6）、原生分类 | `work_topic` | 近线 |
| centroid_build | 周 | `work_topic` × 嵌入 | 05 的 `topic_node.centroid` | 离线 |
| route_stat_weekly | 周 | 默认用季度快照离线计算 `all` 窗口（零 API 成本）；`recent90` 窗口的 cov 取自独立抽样的素描（§5.3），lag 与 λ 取自收割日志，uniq 取自本地溯源；OpenAlex `group_by` 只作可选补充：全量约 9,000 次调用、按列表价约 $0.90（RT §3.5.1 [估算]；每次计 1 credit，已实测，RT 核验 V03） | cov、lag、uniq、fidelity | 默认零 API 成本。若启用 `group_by`，须摊到 7 天（每日约 1,300 次、约 $0.13），并计入 OpenAlex 的 enrich 道美元份额（§13.1）。一次性跑完会在当天吃掉免费 key 每日 $1 额度的 90%，挤占交互联邦（§14.3） |
| sketch_build | `recent90` 周更（subfield 级），`all` 季更（全部 OpenAlex 节点） | 独立样本框：`all` 取季度快照，`recent90` 取 OpenAlex `sample` 抽样（§5.3），不从本地语料抽样；加成员探测 | `coverage_sketch` 的端点位与 `sample_ids` | `recent90` 约 760 次列表调用/周（约 $0.08）与约 130 次 S2 批量调用；`all` 约 2,460 次 S2 批量调用/季；均在 enrich 道预算内 [估算] |
| sketch_local_refresh | 日 | `coverage_sketch.sample_ids` 与 `corpus.identifier` | 本地位（第 0 位）与 `local_refreshed_at` | 约 130 万次标识符主键查找（`all` 约 123 万 + `recent90` 约 6.5 万），批量连接，分钟级 [估算]；零 API |
| scope_complete_daily | 日 | `ops.harvest_run`（回填与增量的完成记录）、`ops.watch_key.watermark` | 每个 venue、系列与 arXiv 类目的完整区间 [complete_from, complete_to]，随 η 一起每日载入检索服务（§6.3 的范围完整性） | 零 API |
| λ_update | 每次轮询后（在线） | WatchKey 轮询结果 | λ 后验，按节点日汇总 | 零 |
| η_update | 日（由 `pc_sys_aggregator` 执行，05 §3.3.5） | `ops.route_decision` 中各端点的已知成员召回计数（§5.3、§6.9） | `evt.agg_route_eta`（Thompson 采样的输入）；格子当日不同用户数 < `k_cf` 时顺延 | 零 |
| snapshot_publish | 周更，重大变更时触发 | 上述全部 | 新 `tsrg_version`；原子切换；旧版保留 2 个以便回滚 [判断] | 零 |
| drift_invalidate | 事件驱动 | 03 的漂移探针、SCD 变更与策略快照 | 按 R2-15、R2-16 分档：robots 或 TDM 信号漂移，相关端点立即降级并进入 POLICY_BLOCKED（§13.4）；ToS 哈希变化给 7 天宽限，宽限内照常路由，期满未复核则模式降为 on_demand（不再做后台收割，仍可参与交互联邦）；证据复核逾期（`review_overdue`）在探针全绿时有 30 天宽限，期满或任一探针告警降为 on_demand；元数据或 latest 通道本身受影响时暂停，WatchKey 与路由改走 SourceSpec 的替补链（RT §12-31） | 零 |

### 5.6 内存与规模估算

| 部分 | 规模 | 估算 [估算] |
|---|---|---|
| 节点与 CSR | 默认约 4.27 万节点（4,798 + 约 3.8 万叶子；加载 MSC2020 插件时约 4.93 万），`maps_to` 按每叶子 ≤5 条计 | ≤3 MB |
| 质心（OpenAlex 节点） | 4,798 × d × 2 B，d 为查询嵌入维度（§9.3） | d=256 时 ≈2.5 MB，d=1,024 时 ≈9.8 MB（为全部默认叶子建质心时另加约 19 MB 或 78 MB；加载 MSC 插件时约 23 MB 或 91 MB） |
| route_stat 稠密张量 | 4,798 × 50 端点 × 2 窗口 × 12 个 float32 | ≈23 MB |
| 覆盖素描 | `all`：4,798 × 256 × 8 B；`recent90`：252 × 256 × 8 B（§5.3） | ≈10 MB |
| 端点与其他 | 含每日载入的 η 与范围完整区间 | ≤5 MB |
| **快照合计** | — | **≈45–55 MB**；为叶子建质心时 d=256 约 65 MB、d=1,024 约 130 MB（加载 MSC 插件约 140 MB） |

路由单次计算量 [估算]：
- P(t|q) 的质心相似度：4,798 × d 次乘加，d=256 时约 1.2×10⁶，d=1,024 时约 4.9×10⁶，均为亚毫秒到毫秒级；
- 选源：η 是 (0,1) 间的概率，f 的求值是浮点乘加，不是按位运算；掩码只用于把样本按"候选端点上的成员模式"分组（§6.4）。求值在乘积域进行，不用 exp 或 log（§6.4）。设候选 n ≤20、保留主题 K ≤32、每题去重后的模式数 P ≤ M=256，且按下文护栏 K·P ≤ 4,096：
  - 比值贪心每轮是一次 n × K·P 的矩阵–向量乘，共 n 轮，约 n² · K · P ≤ 20 × 20 × 4,096 ≈ 1.6×10⁶ 次乘加；
  - 精确枚举按子集逐层倍增，约 2 · 2ⁿ · K·P 次乘加，峰值内存 2ⁿ × K·P 个 float32。规模闸 2ⁿ·K·P ≤ 2²⁰ 把它限制在约 2.1×10⁶ 次乘加、约 4 MB 以内；超出规模闸时改用贪心（§6.6）。
  - Thompson 探索需要判定端点是否"因采样才被选中"，要按后验均值再做一次选源（§6.8），上述计算量翻倍。

原稿按"一次 2ⁿ × n × K·P 的对数域矩阵乘"估为约 3 ms（1,024 × 10 × 8,192 ≈ 8.4×10⁷ 次乘加）。这一估算漏掉了两项：其一，结果矩阵的每个元素都要求一次 exp，约 8.4×10⁶ 次，按 NumPy 每元素数纳秒计已达数十毫秒；其二，结果矩阵本身约 67 MB（float64），每次查询都要分配并扫过。乘积域倍增加规模闸之后，最坏情形回到 5 ms 预算内 [估算，须实测]。学术源的成员模式高度集中，去重后 P 通常远小于 256（待实测），多数查询的 n ≤ 10 仍能精确枚举。

主要开销是 Python 调度与数组分配，因此设 p95 ≤5 ms 的目标（§1.1 对 NFR-10 的细化），与 RT §3.5.6"≤50 源、≤5,000 节点时毫秒级"的判断一致。为守住这一目标，候选超过 20 个时先按单源比值保留前 20 个 [判断]；K·P 超过 4,096 时把 π 截到前 16 个节点 [判断]。

### 5.7 四种用途

1. **查询路由**（§6）：查询得到 π(t) 后，沿节点上的 `route_stat` 与覆盖素描做预算贪心选源。节点层级提供平滑与回退。
2. **收割调度**（§11）：
   - WatchKey 挂在节点或 venue 与端点上，λ̂ 取自对应的 `route_stat` 先验与在线后验；
   - 每个源的礼貌预算在其 WatchKey 之间做平方根注水；
   - 主题型频道的收割编译复用路由算法，只把目标从"查询召回"换成"节点新作覆盖"。
3. **兴趣建模挂点**（06）：
   - 用户画像是节点上的权重，长短期两套，存在 usr 覆盖层；
   - 层级提供稀疏反馈的平滑，兄弟节点作为探索臂（SR §3.1-10/11）；
   - 节点路径就是 why-this 的解释路径，例如"cs.LG → 人工智能 → 你关注的 X"。

   TSRG 只提供结构与质心；画像的学习与使用归 06。
4. **论文→读者反向路由**（§12）：新论文先得到节点标注，再经节点倒排得到候选用户，与质心点积、锚点倒排上的 AST 谓词求值合起来构成三路。频道命中近线写入 FeedInbox；节点与质心两路按日批产出候选读者，交 06 分配（§12.1）。这对应 SimClusters 的"社区倒排"思路，但社区换成固定、可解释的主题节点（SR §2.10.2、§2.12）。

---

## 6. 路由算法

### 6.1 问题形式化

**输入**：
- 规范化查询 q；
- TSRG 快照；
- 出站网关与调度器的在线状态（健康、熔断、余量）。

**输出**：一个执行计划 = 本地计划（永远参与）+ 远端端点集合 S 及各自的放宽子查询（§7）。

**记号**：
- π(t) = P(t|q)：查询在 OpenAlex 节点上的主题后验（§6.2）；
- M_t：节点 t 的覆盖素描样本集合；
- b_{w,s} ∈ {0,1}：样本作品 w 是否被端点 s 收录；
- η_{s,t}：端点 s 在节点 t 上的检索有效率（§5.2）；
- c_s(q)：端点 s 为本查询付出的成本（§6.5）；
- B：本查询的预算。

**目标函数**（期望并集召回）：

```text
f(S) = Σ_t π(t) · F_t(S)
F_t(S) = (1/|M_t|) · Σ_{w ∈ M_t} [ 1 − Π_{s ∈ S ∪ {local}} (1 − η_{s,t} · b_{w,s}) ]      其中 η_{local,t} := 1
求   max f(S)   s.t.  Σ_{s∈S} c_s(q) ≤ B，且 S 中每个端点都满足 §6.3 的硬约束
```

**引理（单调次模）**：对单个样本 w，g_w(S) = 1 − Π_{s∈S}(1 − p_s)，其中 p_s ∈ [0,1]。向 S 加入 x 的边际增益为 p_x · Π_{s∈S}(1 − p_s)，随 S 增大而不增，因此 g_w 单调次模。f 是这些函数的非负加权和，同样单调次模。这是 §6.7 近似保证成立的前提，也是 RT §3.5.2 所说"覆盖函数单调次模"在本设计中的具体形态。

f(∅) 就是本地覆盖 `cov_local(q) = Σ_t π(t) · share_{w∈M_t}(b_{w,local}=1)`，它同时是是否联邦的判据（§6.3）。

四点补充：
- **条件独立假设**：乘积形式假设给定收录后，各端点是否取回相互独立。它不影响单调次模性（引理对任意 p_s 成立），只影响 f 的校准：端点间正相关时 f 高估并集召回，见 §5.3 的"建模假设"。
- **未归一化的 f**：f(∅) = cov_local > 0。§6.7 的近似保证对增益 g(S) = f(S) − f(∅) 成立（g 是 f 在"已含本地"条件下的收缩，仍单调次模，且 g(∅)=0），由此推出的对 f 本身的保证只会更强。反过来，用 f 本身的比值衡量路由质量会被 cov_local 稀释：§6.12 的例子里一个端点都不选，f(∅)/f(OPT) 也有 0.80。所以验收用增益比（§14.1、AC-V2.26）。
- **窗口选择**：查询在 `first_public` 上的时间约束整体落在近 90 天内时用 `recent90` 窗口的素描与统计（subfield 级，§5.3），否则用 `all`。
- **η 的索引**：η_{s,t} 按 π 支撑集中的每个节点分别取值（§6.8），不是每个端点一个标量。

### 6.2 主题后验 P(t|q)

三路证据：

1. **显式过滤 p_f**：
   - 查询中的 Facet（topic、subfield、arXiv 类目、JEL、MeSH 等）经 `maps_to` 映射到 OpenAlex 节点，按置信度分摊；
   - Venue 过滤经 `venue_topic` 给出分布。
2. **质心分类 p_c**：查询嵌入与 topic 质心求余弦，取 top-64 做 softmax（温度 τ），再上卷。长文本查询可改用自托管的 OpenAlex 开源分类器（Apache-2.0 权重，PU §2.4）。OpenAlex `/text` 端点已被标为 deprecated，**不使用**（RT §3.5.2 核验补充）。
3. **本地命中直方图 p_r**：取投机首屏（§4.2）的 top-N 本地结果，统计其 `work_topic` 分布，按 1/(60+rank) 加权。这是 ReDDE"估计相关文档在各源的分布"思想（RT §3.1）的直接落地：本地语料就是那个"中心样本库"，而且投机首屏本来就要跑，不额外花钱。
   这里的"首屏命中"专指共享层本地召回在个人谓词与个性化**之前**的列表：不含 `private` 列表（§9.8），不经 `Personal` 文字（已见、在库、评分）过滤，也不按 `personal_score` 重排（§8.8）。否则 π 会随提问者的已见集合、画像与私有文献变化，而 π 写入 `ops.route_decision` 并参与全局路由学习（§6.9），这就构成私有到共享的派生路径（HC-01），也违背"路由不使用个人画像"（R2-40）以及"同一规范查询在同一快照下得到同一计划"的可复现性（§15.3）。SR §3.1-19 同样要求推荐与路由只使用可共享的元数据。

```python
# 设计伪代码
def topic_posterior(q, snap, first_screen_hits) -> dict[int, float]:   # first_screen_hits：共享层、非个性化召回（见上）
    p_f = filter_prior(q, snap)                          # 显式过滤 → OpenAlex 节点分布（可能为空）
    p_c = centroid_softmax(embed_query(q), snap.centroids, top=64, tau=TAU)
    p_r = hit_histogram(first_screen_hits, snap, weight=lambda r: 1 / (60 + r))
    if p_f:          w = (0.60, 0.25, 0.15)               # 有显式过滤时以过滤为主 [判断]
    elif len(first_screen_hits) >= 5:
                     w = (0.00, 0.50, 0.50)
    else:            w = (0.00, 0.80, 0.20)               # 本地命中少时 p_r 不可靠
    pi = normalize(w[0] * p_f + w[1] * p_c + w[2] * p_r)  # 缺失的证据项为零向量；normalize 只在总质量 > 0 时进行
    if pi.total() == 0:                                  # 无文本、无主题类过滤、首屏无命中（如只有 au: 或 IdRef 的查询）
        pi = snap.subfield_prior()                       # 退回按 Û 规模加权的 252 个 subfield 分布 [判断]；
                                                         #   信息量低，截断后路由自然偏向覆盖面最广的端点
    pi = rollup(pi, level="subfield")                    # 主分辨率 subfield（§5.3：topic 级标注噪声大）；只向上卷
    return normalize(truncate(pi, top_k=32, mass=0.95))  # 截断到 32 个节点或 95% 质量后重新归一
```

截断后必须重新归一：否则 f 的上限只有约 0.95，cov_local 会因截断本身低于 τ_cov = 0.9，触发不必要的联邦。

混合权重是初值。有路由日志后，以最终 top-k 中通过残差的结果集合 T（§5.3 的相关集合代理）的节点分布为目标，按对数似然重新拟合 [判断]。不用"独有贡献"作拟合目标，理由同 §5.3：它取决于同时被选的其他端点。

路由**不使用个人画像**，理由见 §15.3：一是合规，个人画像派生的决策不应进入全局路由统计；二是缓存，路由与用户无关时，不同用户的同一查询得到同一计划，可以共享缓存；三是复现。用户画像只影响本地结果的个性化排序（06）和消歧候选的排序。

### 6.3 联邦判据与候选端点

**是否联邦**（P-01 的量化）：

```text
# 设计伪代码
federate(q) =  intent ∈ {SEARCH, SIMILAR, EXPAND}
             ∧ scope.mode ≠ local
             ∧ ( scope.mode = force
                 ∨ ( ¬scope_complete(q)                  # 范围完整性成立时不联邦（见下）
                     ∧ ( cov_local(q) < τ_cov            # τ_cov = 0.9 [判断]
                         ∨ n_local_T(q) < n_min ) ) )    # 本地"确定命中"（T）不足 n_min = 10 条 [判断]
```

- **"确定命中"的口径**：n_local_T 计本地结果中硬谓词三值求值为 T 的条目，在去掉 `Personal` 文字后的 `where` 上、对共享层召回计数。理由同 §6.2 的 p_r：是否联邦不得取决于提问者的已见集合与私有文献。查询带软检索文本时，还要求该条目"相关性过阈"：BM25 列表中命中全部分析后词项，或稠密余弦 ≥ θ_rel（初值 0.5 [判断]，按模型校准）。否则只有软文本、没有硬谓词的查询，所有本地作品都算"满足 where"，这条判据永远不会触发。阈值名写作 `n_min`，避免与 k 匿名阈值混淆（08 早期稿统称 `k_min`，已按 R2-04 改为 `k_cf`/`k_reason`/`k_show`）。
- **范围完整性 `scope_complete(q)`**：cov_local 由主题素描估计，只以主题为条件，不看查询的其他硬过滤。反例：§10.3 的查询限定在 JFE、RFS、JF 三刊，三刊由基础收割完整覆盖，但 Finance subfield 素描的本地位可能只有 0.7，于是 cov_local < τ_cov，引发不必要的联邦。修正规则：`where` 的顶层合取项若把结果限定在一组范围 R 内（`Facet(venue|series ∈ V)`、`Facet(cat ∈ C)`，或 `src:` 指向本地整源镜像的来源），且同时满足以下三条，则 `scope_complete(q)` 为真，cov_local 取 1：
  1. R 中每个范围在查询时间窗内完整：由每日作业 `scope_complete_daily`（§5.5）给出的完整区间 [complete_from, complete_to] 覆盖查询窗口（回填已完成到窗口起点，latest 水位不早于窗口终点）；
  2. 查询的硬文字与软检索文本不依赖本地缺失的字段：只涉及标题、元数据与分面；或范围内作品的摘要可检索率（通过 §9.1 权利闸进入 `abstract_text` 的比例）≥ 0.9 [判断]；
  3. 不含 `fulltext` 条件。

  三条任一不满足时，按 cov_local 与 n_local_T 照常判断。无硬范围的查询不受影响。
- LATEST 恒不联邦（P-01）。
- LOOKUP 不做选源：直接走同能力替补链（§8.4）。
- 查询性能预测（QPP）只作弱信号：它只能在 ±0.05 的范围内调整 τ_cov，不能单独触发联邦。依据是 QPP 跨范式泛化差，驱动选择性处理只带来约 4% 的 NDCG 增益（RT §3.2）。

**候选端点的硬约束**（全部满足才进入选源）：
1. 端点 active，且 `exec_side = platform`（P-03：用户侧端点不进入平台路由）。按 R2-14，Springer Nature OA/Meta API 与 NASA ADS 在条款书面确认前按用户级凭证处理，不进平台路由。
2. 策略引擎对该端点本次操作（LOOKUP 或 SEARCH）给出的模式 ≥ `on_demand`（03 §6.2 的五档全序，R2-09；P-05）。带 `needs_confirmation` 的文档化 API 按简报 Q4 的默认（08 登记为 HC-31）只接受低频、用户触发的调用；交互检索属于用户触发，可以参与，但受该端点的交互道配额约束。例外：`pubmed`（NCBI E-utilities）按 R2-13 在 NCBI 书面确认前不启用，也不进 LOOKUP 替补链；确认前生命科学的联邦与查找由 Europe PMC、OpenAlex 与 Crossref（按 DOI）承担（§8.4）。03 §6.8 把 E-utilities 记为"on_demand（单个 PMID 补查）"，本文按 R2-13 的更严读法执行（§20 第 3 项）。
3. 熔断器处于 CLOSED；或处于 HALF_OPEN 且有空闲的探测名额（§13.4）。
4. 具备意图所需的能力。意图先映射到 SCD 的 `serves` 操作（03）：LOOKUP → LOOKUP，SEARCH、SIMILAR、EXPAND → SEARCH；LATEST 不联邦。在此之上：LOOKUP 需要 `id_lookup` 含相应标识符方案；远端 SIMILAR 需要语义检索或正负样本推荐能力；远端 EXPAND 需要引文关系过滤能力。arXiv legacy API 的 SCD 不声明 SEARCH（arXiv 只做中心镜像，用户检索只查本地索引，CS §3-6），由本条排除；LOOKUP 替补链仍可在交互道的极小份额内调用其 `id_list`（§8.4）。
5. 放宽结果不"无界"（§7.2）：P_s ≡ true 且没有可下推的软检索文本时，一律剔除；不按相关性排序的端点，若放宽后预计总数超过其分页上限，也剔除。本条依赖放宽结果，所以放宽在选源之前执行（§6.6 的 `plan_route`）。
6. 满足 `scope.via` 与 `scope.exclude`。
7. 延迟可行：该端点交互道的 p95 ≤ 剩余截止时间。
8. 许可与商用开关放行：
   - CORE 声明"推荐、检索、发现类产品须先取得许可"（CP §2.1），因此在取得许可前不进入任何路由；
   - S2 的商用边界待 LQ-08；
   - `platform.commercial=true` 时，按 HC-23 自动关闭受限来源。
9. 交互道余量 > 0（§13.1）。

### 6.4 目标函数的计算

位运算只用于分组，f 本身按浮点计算（η ∈ (0,1)）：

1. **模式压缩**：对 π 截断后的每个节点 t，把 M 个样本的掩码限制到"本地位 + 候选端点位"，按相同模式 p 分组，得到计数 c_{t,p}。本地位为 1 的模式恒被覆盖，其贡献 π(t)·c_{t,p}/M 计入常数 f(∅)，不参与优化。
2. **未覆盖因子矩阵**：Q[s, (t,p)] = 1 − η_{s,t} · b_{p,s} ∈ [0, 1]。列权重 ω_{(t,p)} = π(t) · c_{t,p} / M。
3. **求值**：f(S) = f(∅) + Σ_{(t,p)} ω_{(t,p)} · (1 − Π_{s∈S} Q[s,(t,p)])。
4. **贪心**：维护未覆盖向量 v = Π_{s∈G} Q[s,:]（初值全 1）。候选 x 的边际增益为 Σ ω · v · (1 − Q[x,:])，即 (1 − Q) · (ω ∘ v) 这一次矩阵–向量乘，一次求出全部候选的增益；选中 x 后令 v ← v ∘ Q[x,:]。每轮 O(n · K·P) 次乘加，不用 exp 或 log，也不做除法。
5. **精确枚举**：按子集逐层倍增。从只含空集的一行 [1, …, 1] 起，依次加入第 i 个候选：把现有各行复制一份，副本逐元素乘以 Q[x_i, :]。n 步后得到 2ⁿ 行，每行是一个子集的未覆盖向量；再与 ω 做一次矩阵–向量乘，得到全部子集的 f。总计约 2 · 2ⁿ · K·P 次乘加，峰值内存 2ⁿ × K·P 个 float32。倍增只做乘法，不需要 Gray 码增量更新时的除以 (1 − η)（η 接近 1 时数值不稳），也不需要对数域方案对每个元素求 exp（§5.6 的对比）。
6. **规模闸**：只有 n ≤ N_EXACT = 10 且 2ⁿ · K·P ≤ W_EXACT = 2²⁰ [判断] 时在线精确枚举（约 2.1×10⁶ 次乘加、约 4 MB）；否则用 §6.6 的比值贪心加最佳单源。学术源的成员模式高度集中，P 通常远小于 256，多数 n ≤ 10 的查询都在闸内（须实测）。

复杂度见 §5.6 与 §6.11。

### 6.5 成本与预算

**成本**只含可加的部分：

```text
c_s(q) = usd_s(q) / u  +  ρ_s · req_s(q)
  u        = $0.001（1 个成本单位 cu，约等于一次 OpenAlex 搜索调用的费用；OpenAlex 搜索按 $1/千次计费，RT §2.2）[判断]
  req_s(q) = 预计请求数 = Σ_{子查询 j} ⌈d_j / page_size_s⌉           （含放宽拆分出的子查询，§7.2）
  d_j      = 按相关性排序的端点：k_remote = min(page_size_s, N_rec)，默认只取一页 [判断]；
             不按相关性排序的端点：est_count(P_{s,j})，必须取完才能在本地排序（§7.2 的无界判断保证它 ≤ page_cap）
  ρ_s      = ρ0_s / max(0.05, r_s)                                    （礼貌影子价格 [判断]）
  r_s      = 该端点交互道在当前窗口内剩余令牌的比例（取自配额账本，§13.1）
  下限      c_s(q) ≥ C_MIN = 0.01 cu [判断]：免费且余量充足的端点成本不为零，比值贪心不会除零
```

影子价格让礼貌约束变成价格信号。某个上游的交互份额越紧张，路由器就越少选它，直至自动退回"仅本地"。这样不必写"某源每天最多联邦 N 次"之类的硬规则，也天然满足 P-04"不随用户数线性放大"。ρ0_s 按上游的稀缺度设定 [判断]，从紧到松：
- Europe PMC 最稀缺。`www.ebi.ac.uk` 的 robots 对通用 UA 设 `Crawl-Delay: 10`，按 P-05 取最严，全平台每 10 秒至多 1 次，且与 `FIRST_IDATE` 收割共用同一账本键；数值限额未公布 ⚠（AG §2.2.10、§2.3.3；03 §4.4 已登记 `min_interval_s: 10`，§8.5 估算每日至多约 8,640 次）；
- arXiv 旧 API：全平台每 3 秒 1 次、单连接（RT §2.2），交互道本就只留 LOOKUP 的极小份额（§13.5）；
- S2：key 为 1 RPS，由全部端点共用（AG §2.2.3）；OpenAlex `search.semantic`：1 req/s（RT §2.2）；
- Crossref polite 池：单条 10/s、列表 3/s（AG §0-1），较宽松。

**预算**：交互检索默认 B = 5 cu [判断]，深度检索按 §3.7 事先预览。单项成本 c_s(q) > B 的端点不可能出现在任何可行解里，选源前先剔除；影子价格在余量紧张时可把成本推到 B 以上（ρ_s 最多放大 20 倍），这一步因此不是空操作（§6.6、§6.7 的适用条件）。

**延迟不进预算**。RT §3.5.2 的伪代码把 `w_lat·p95` 放进了 cost，但并行 fan-out 下查询延迟取各端点延迟的 max，而不是和，不满足背包约束要求的可加性。本文把延迟改为可行性约束（§6.3 第 7 条）加截止时间传播（§8.2）。顺序执行的替补链里延迟是可加的，只用于链内排序（§8.4）。这一改动记入 §19-2。

### 6.6 算法

```python
# 设计伪代码
N_EXACT = 10                     # 候选数不超过该值时考虑在线精确枚举 [判断]
W_EXACT = 2 ** 20                # 精确枚举的规模闸：2ⁿ · K·P 不超过该值（§6.4 第 6 条）[判断]
N_MAX = 20                       # 候选超过该值时按单源比值预筛（§5.6 的延迟护栏）[判断]
EPS_GAIN = 1e-3                  # 边际增益低于该值的端点事后剪掉（避免白花礼貌预算）[判断]
C_MIN = 0.01                     # 成本下限，单位 cu（§6.5）[判断]

def plan_route(q, snap, live, first_screen_hits) -> RoutePlan:
    pi = topic_posterior(q, snap, first_screen_hits)                      # §6.2
    if q.intent == "LOOKUP":                                              # LOOKUP 不做选源（§6.3）
        if lookup_hit(first_screen_hits) or q.scope.mode == "local":      # 标识符命中，或标题 top-1 ≥0.9 且唯一（§10.1）
            return RoutePlan.local_only(pi)
        return RoutePlan.lookup_chain(q, live)                            # §8.4 替补链：作为一个远端任务，链内顺序执行、
                                                                          #   跨主机对冲；链内各级同样过 §6.3 第 1–3、6、8 条
    if not federate(q, pi, snap, live, first_screen_hits):                # §6.3：意图、scope、范围完整性、cov_local、n_min
        return RoutePlan.local_only(pi)
    cands = [s for s in snap.endpoints if hard_ok(s, q, live)]            # §6.3 第 1–4、6–9 条
    relaxed = {s: relax(q.where, q.rank.relevance.text, s.scd, snap.local_stats, pi)
               for s in cands}                                            # §7.2：放宽先于选源
    cands = [s for s in cands if not relaxed[s].unbounded]                # §6.3 第 5 条
    cost = {s: max(C_MIN, c_s(q, relaxed[s], live)) for s in cands}       # §6.5：子查询数取自放宽结果
    B = q.budget_cu()
    cands = [s for s in cands if cost[s] <= B]                            # 单项超预算者不可能可行；近似界的前提（§6.7）
    post = live.eta_posterior                                             # 每日从 evt.agg_route_eta 载入（§5.4）
    draw = {s: sample_beta if live.explore_ok(s) else mean_beta for s in cands}   # 探索额度由网关按端点控制（§6.8）
    eta = {s: {t: draw[s](post(s, t)) for t in pi} for s in cands}        # 按"端点 × 节点"取值（§6.8）
    S = select_endpoints(pi, cands, cost, B, snap.sketch[window_of(q)], eta)   # 窗口选择见 §6.1
    return RoutePlan(pi=pi, remote={s: relaxed[s].subs for s in S}, eta=eta, cost=cost)

def select_endpoints(pi, cands, cost, B, sketch, eta) -> list:
    f = CoverageObjective(pi, sketch, eta, cands)                         # §6.4：模式压缩 + 乘积域；f(∅) = cov_local
    if len(cands) > N_MAX:
        cands = sorted(cands, key=lambda s: f.gain([], s) / cost[s], reverse=True)[:N_MAX]
    if len(cands) <= N_EXACT and 2 ** len(cands) * f.n_cols <= W_EXACT:  # 规模闸；n_cols = K·P
        S = exact_best(f, cands, cost, B)                                 # 逐层倍增求出全部子集（§6.4）
    else:
        G, spent, rest = [], 0.0, set(cands)
        while rest:                                                       # 比值贪心（KMN99 算法 1 的形态）
            x = max(rest, key=lambda s: f.gain(G, s) / cost[s])
            rest.discard(x)
            if spent + cost[x] <= B:                                      # 放不下就跳过，继续扫描
                G.append(x); spent += cost[x]
        s1 = max((s for s in cands if cost[s] <= B), key=lambda s: f([s]), default=None)
        S = G if s1 is None or f(G) >= f([s1]) else [s1]                  # 最佳单源兜底
    return prune_small_gains(f, S, EPS_GAIN)

def exact_best(f, cands, cost, B):
    subsets = all_subsets(cands)                                          # 最多 1,024 个
    vals = f.batch(subsets)                                               # 乘积域逐层倍增，再与 ω 做一次矩阵–向量乘
    ok = [i for i, S in enumerate(subsets) if sum(cost[s] for s in S) <= B]
    return list(subsets[max(ok, key=lambda i: vals[i])])                  # 空集恒可行

def prune_small_gains(f, S, eps):
    kept = []
    for x in sorted(S, key=lambda s: f.gain([], s), reverse=True):        # 次序任意均满足下文界；取单源增益降序
        if f.gain(kept, x) >= eps:
            kept.append(x)
    return kept
```

**事后剪枝的界**：原稿在贪心循环内跳过增益小于 `EPS_GAIN` 的端点。循环内过滤会改变之后的贪心轨迹，"只损失 n × EPS_GAIN"的说法因此没有依据。本文改为选定之后再剪枝，损失有严格上界。设剪掉的集合为 R，保留集合为 K。由次模性，f(S) − f(K) = f(K ∪ R) − f(K) ≤ Σ_{x∈R} [f(K ∪ {x}) − f(K)] ≤ Σ_{x∈R} [f(K_{<x} ∪ {x}) − f(K_{<x})] < |R| · EPS_GAIN。其中 K_{<x} 是考察 x 时已保留的集合，K_{<x} ⊆ K，所以对 x 的边际增益更大。因此 f(K) ≥ f(S) − |R| · EPS_GAIN ≥ f(S) − n · EPS_GAIN，且 K 的成本不超过 S 的成本。§6.7 的各项保证在减去这一加性项后对 K 成立。

### 6.7 近似保证：准确表述与适用条件

1. **只有基数约束时**（每个端点成本相同，最多选 k 个），贪心得到至少 (1−1/e) ≈ 0.632 倍最优值（Nemhauser、Wolsey、Fisher 1978，RT 引 [Submod78]）。
2. **带成本的预算约束下，纯比值贪心没有常数保证**，可以任意差（KMN99 指出；Krause & Guestrin 技术报告复述，一手来源，2026-09-27 查阅）。所以必须加兜底。
3. **"比值贪心 + 最佳单源取大者"**（§6.6 的形态）：
   - 可证下界：由 f(G_l) + f(x*) ≥ (1−1/e)·OPT 可得至少 (1−1/e)/2 ≈ 0.316。其中 G_l 是贪心在第一次"放不下"之前得到的前缀，x_{l+1} 是那个放不下的端点，x* 是单独可行的端点中价值最高者。推导为 f(G_l) + f({x_{l+1}}) ≥ f(G_l ∪ {x_{l+1}}) ≥ (1−1/e)·OPT，再用 f({x_{l+1}}) ≤ f(x*)。最后这一步要求 x_{l+1} 单独可行，所以单项成本超过 B 的端点必须先剔除（§6.5、§6.6）。反例：若不剔除，一个成本为 2B、比值最高的端点会在第 1 轮被判为放不下，此时 G_l 为空，推导链断开。KMN99 对覆盖函数给出此结论，Krause & Guestrin（2005 技术报告）推广到一般单调次模函数（一手来源，2026-09-27 查阅）。
   - 更紧的结论：文献中广泛引用的 (1−1/√e) ≈ 0.393，原证明有缺口。Tang 等（ACM SIGMETRICS 2021，arXiv:2008.05391）证明该算法至少达到 0.405，从而补上了这一缺口（一手来源，2026-09-27 查阅）。
   - 上界：Kulik、Schwartz、Shachnai（2021，arXiv:2102.12879）证明该算法的近似比不超过 0.42945（一手来源，2026-09-27 查阅）。
4. **部分枚举**：先枚举所有 ≤3 个端点的可行子集，各自用比值贪心补全，取最好者，达到 (1−1/e)。KMN99 对覆盖函数证明，Sviridenko（2004）推广到一般单调次模函数；KMN99 同时指出，除非 NP ⊆ DTIME(n^{O(log log n)})，这一比值不可再改进（一手来源的二手复述，2026-09-27 查阅）。代价为 O(n⁵) 次函数求值，n=20 时约 3.2×10⁶ 次 [估算]。因此只在离线校验中使用，不用于每次查询。

**适用条件**（缺一则上述保证不成立）：
- f 单调次模：由 §6.1 的引理保证。
- 成本非负、可加，且单次决策内固定：影子价格在一次决策内按当时余量取定值，满足。
- 单项成本超过预算的端点已在选源前剔除（§6.6 的 `plan_route`），否则第 3 条的推导不成立。
- f 精确求值：实际求值的是素描上的 f̂，保证针对 f̂ 成立。f̂ 与真实期望覆盖之间有抽样误差：M=256 时，单节点覆盖率的标准误 ≤ √(0.25/256) ≈ 0.031 [估算]。这部分误差作为加性项计入，误差版本的分析见 Krause & Guestrin。
- 探索时用的是采样值 η̃：保证针对"采样后的 f"成立。
- 保证针对增益 g(S) = f(S) − f(∅)，并扣除事后剪枝的加性项 n · EPS_GAIN（§6.6）。
- 候选超过 N_MAX = 20 时的单源比值预筛是启发式，保证只相对预筛后的候选集成立；预筛丢掉的端点在离线全枚举中单独统计（§14.1）。
- 所有保证都是最坏情形。实际近似比用离线精确枚举测量（§14.1、AC-V2.26）。

**选定的组合**：
- 候选 ≤10 个且在规模闸内（2ⁿ·K·P ≤ 2²⁰，§6.4）时在线精确枚举，得到（素描上的）最优，再扣剪枝项；
- 其余情形用"比值贪心 + 最佳单源"，增益可证 ≥0.405 · g(OPT) − n · EPS_GAIN；
- 离线对日志样本做全枚举，或做 ≤3 元部分枚举，校验实际比值。

候选数通常少于 20（RT §3.5.2 [判断]），经 §6.3 的硬约束过滤后多数查询 ≤10。规模闸是对 R2-38"在线精确枚举"的细化：它只在枚举代价会冲破 5 ms 预算时退回贪心，近似保证照上一条成立（§19-16）。

### 6.8 Thompson sampling 探索

- **臂与后验**：每个"端点 × subfield"维护检索有效率 η 的 Beta(a, b) 后验，存于 05 的 `evt.agg_route_eta`，检索服务每日载入（§5.4）。
- **采样与选源**：每次联邦查询对 π 支撑集中的每个"端点 × 节点"各采样一次 η̃_{s,t} ~ Beta(a, b)（≤20 × 32 次），代入 f，再用 §6.6 选源。不确定的端点于是偶尔被选中，统计不会冻结（RT §3.5.4）。
- **奖励与更新**：奖励取 §5.3 的"已知成员召回"计数：成功数 = top-k 中已知被 s 收录、且由 s 取回的篇数；失败数 = 已知被 s 收录、但 s 未取回的篇数；按作品的节点标注计入。计数写入 `ops.route_decision`（§6.9），由 `pc_sys_aggregator` 日批汇总：某个"端点 × 节点"格子当日的不同用户数（按 `day_token` 计）达到 `k_cf` 才写入 `evt.agg_route_eta`，否则顺延（05 §3.3.5；与 SI-49 的 k 匿名门槛同向）。收藏、打开等后验信号走同一聚合闸，只作 GBDT 标签的辅助（§6.9）。因此后验每日更新一次；TS 对批量延迟反馈是稳健的，日内不做进程内更新，也就不会出现多个 API 进程各自持有不一致的后验。
- **非平稳**：Beta 计数按半衰期 60 天衰减 [判断]。
- **探索预算**：端点"因采样才被选中"（精确枚举或贪心在采样值下选中、在后验均值下不选）的请求，带 `explore=true` 标记发给出站网关。判定它要按后验均值再做一次选源，路由计算量因此翻倍，已计入 §5.6。它们仍从交互道同一个令牌桶领取令牌，网关另为每个端点维护探索日计数器：每天不超过其交互道预算的 10% [判断]，超出即拒绝探索请求，并通知路由器关闭该端点的采样（`live.explore_ok(s)` 变为假，§6.6），其他端点照常采样。检索服务是多进程部署（02 P3），这个上限不能靠进程内计数。

**理论边界**：Wang 与 Chen（arXiv:1803.04623）指出，组合半老虎机上的 Thompson sampling 需要精确的离线 oracle；即使在经典多臂老虎机问题中，也不能直接把它换成近似 oracle（一手来源，2026-09-27 查阅）。因此：
- 候选 ≤10 且在规模闸内时用精确枚举作 oracle，理论保证在"素描近似"的意义下可用；
- 其余情形（候选 >10，或超出规模闸），TS 只是有预算上限的启发式探索，效果由离线回放监控（§14.1）。

这一点对简报 §6.2-2 的"用 Thompson sampling 做源探索"是细化，不是否定（§19-7）。

### 6.9 GBDT pairwise 升级

- **日志**（从第一天记录，P-08）：每次联邦决策写一行 05 的 `ops.route_decision`（05 §3.4 ⑩）。表按 05 去标识：无 `user_id`、无请求 id、无查询原文；时间截到小时；`day_token = HMAC(k_day, user_id)` 只供当日聚合按不同用户计 k，日作业结束即置空。记录内容：
  - `query_key = HMAC(k_route_epoch, query_hash)`，密钥按季度轮换。**不存 `query_hash` 本身**：本人的 `usr.search_history.ast_hash` 与 `evt.search_log` 都能与原值连接，存原值等于把"去标识"日志重新挂回用户；
  - `tsrg_version`、η 载入日期、意图、π 的 top-k；
  - 每个候选的特征、被选集合、采样值 η̃、成本、是否探索；
  - 每个端点的结果：状态、延迟、返回数、折叠后独有数、残差拒绝数、失配数（§7.5）、进入 top-k 数，以及 η 的观测"已知成员数 |T_s| 与其中由 s 取回的篇数"（§5.3），按节点分列。

  这张表是**假名化**而非匿名：同一查询在同一密钥周期内的 `query_key` 相同。访问按 05 §4 的角色矩阵执行（只追加者 `pc_app`，读取者 `pc_sys_aggregator`，以及 `day_token` 已置空分区上的 `pc_analytics`）。
- **特征**：
  - 按 π 聚合的 cov、η 的均值与方差、λ、lag、uniq、fidelity；
  - 下推保真度 φ_s(q)（§7.4）；
  - 预计结果数；
  - 意图与查询结构（文字数、短语、语义、过滤维度）；
  - 成本与健康；
  - OpenAlex 当日余额；
  - 同节点上的历史独有贡献率：按 π 的 top 节点聚合 `route_decision`，不按查询嵌入做近邻。查询嵌入由查询原文派生，存进路由日志会违背 05 对该表"无查询原文"的约束。
- **标签**：每次决策中端点 s 的已知成员召回 η_s(q) = 成功数 / |T_s|（|T_s| = 0 时不作样本）。标签与 f 中 η 的语义一致，模型输出才能校准后直接替换 η。"独有贡献"与"被打开或收藏"（聚合口径）只作评测指标和辅助特征，不作标签：它们依赖同选的其他端点，理由同 §5.3。
- **训练集经聚合闸抽取**：GBDT 是全局模型。CP §2.7 的 M19 与 DI-03 要求用户行为只以"聚合、去标识"的形式进入全局模型（HC-01），而 `route_decision` 是逐次决策的假名化记录，只做到了去标识。所以训练集不直接读明细行，而由 `pc_sys_aggregator` 在当日 `day_token` 置空之前抽取到 `archive/train/`（05 §4.1 已授予它写该路径的权限）：只保留所属"意图 × π 首节点"格子当日不同用户数 ≥ `k_cf` 的决策，其余丢弃；样本中的 T 按 §5.3 取非个性化排序。代价是长尾查询的样本变少，由 η 的先验与离线穷举评测（§14.1(a)）补足 [判断]。05 §16 第 8 项已把"路由日志的去标识是否足够"列为待 08 评审的问题；本条是 04 这一侧的收紧，抽取规则的落表转 05（§20 第 35 项）。
- **模型**：成对 GBDT（LambdaRank 或 pairwise 目标）。LTRR 发现成对排序的 XGBoost 效果最好，且分布外泛化更强（RT §3.1）。实现选 LightGBM（MIT）或 XGBoost（Apache-2.0），两者均为放行级（§1.6；许可据仓库元数据，2026-09-27 查阅）。
- **接入方式**：模型分数经保序回归校准为 η̂_s(q)，替换 f 中的 η，**不改变**"覆盖目标 + 预算选源"的结构。这样次模性与预算处理原样保留，也避免"直接取 top-k 端点"忽略端点之间的重叠。
- **升级闸门** [判断]：
  1. 经聚合闸抽取后的已标注联邦查询 ≥2 万条；
  2. 在留出的一个月日志上回放，同成本下召回保持率提高 ≥2 个百分点，或同召回下成本降低 ≥20%；
  3. 影子模式运行 2 周；
  4. 对合并结果做交错实验，再全量（SI-51）。

### 6.10 新源冷启动：LLM 零样本先验

- **触发**：03 登记一个新的 SourceSpec 端点时，离线作业启动。
- **与审核的先后**（FR-29 按 R2-23 的限定）：新来源审核通过前，平台不得向该来源的主机发出任何上游请求。所以先验作业只用不触及新主机的输入：SourceSpec 草稿、SCD 能力摘要，以及经**已登记**来源取得的样本（例如按该来源的 ISSN、DOI 前缀或 OpenAlex source id 查 Crossref 或 OpenAlex，与 03 §2.5 对 `user_proposed` venue 的核验同级；新来源的审核队列见 03 §13.1）。成员探测与任何对新主机的请求，都等审核通过、策略快照给出的模式允许之后才发出（§5.3）。审核未通过时，先验只存在草稿里，不进路由。
- **输入与打分**：输入包括来源描述、SCD 能力摘要、≤50 条样本记录的标题与 venue（样本来源见上一条）。LLM 先对 26 个 field 打 0–4 分并给出理由，再对高分 field 下的 subfield 打分（ReSLLM 零样本源选择形态，RT §3.1、§3.5.4）。
- **转成先验**：均值 m = 分数/4，伪计数 n₀ = 4 [判断]，a₀ = m·n₀，b₀ = (1−m)·n₀。伪计数很小，几十条真实观测即可覆盖先验。
- **先验作用在覆盖上，不在 η 上**：新端点在成员探测完成前，素描里它的位全为 0。若照常用 b_{w,s} 计算，f 中它的增益恒为 0，永远不会被选中，Thompson 探索也无从发生。所以探测完成前，f 对该端点改用 1 − η_{s,t} · cov₀(s,t) 代替 1 − η_{s,t} · b_{w,s}（即 §6.4 的 Q 矩阵中该端点在节点 t 的各列取同一个常数），把成员关系视为与其他端点独立、概率为 cov₀ 的伯努利变量；cov₀ 的 Beta 参数存 `route_stat.ts_alpha/ts_beta`（05 §3.1.7：这两列只存非个人先验）。η 的先验取能力最相近的 3 个已有端点的均值。探测写入真实位后，这一替代自动失效。
- **非 LLM 备选先验**：按来源描述嵌入与能力向量，找最相近的 3 个已有端点，取其统计的平均 [判断]。
- **后续动作**：审核通过、端点启用后立即启动成员探测（§5.3），尽快用实测覆盖替换先验。
- **合规**：作业离线运行，符合 P-07。LLM 的供应方与区域按 08。作业只处理来源描述与公开元数据，不含用户数据。

### 6.11 复杂度汇总

| 步骤 | 复杂度 | T1 量级 [估算] |
|---|---|---|
| P(t\|q)：质心相似度 | O(N_node · d) | 4,798 × 256 ≈ 1.2×10⁶ 次乘加（d=1,024 时 ≈4.9×10⁶） |
| P(t\|q)：命中直方图 | O(N_hits · 3) | 可忽略 |
| 候选过滤 | O(E) | E ≤ 50 |
| 放宽与拆分（§7），先于选源 | O(\|P\| · 候选端点数) | \|P\| ≤ 数十个文字，候选 ≤50 |
| 模式压缩（§6.4） | O(K · M) 次位运算与分组 | 32 × 256 = 8,192 |
| f 的一次边际求值 | O(K · P) 次浮点乘加，P ≤ M 为去重后的模式数 | ≤ 4,096（K·P 护栏，§5.6） |
| 在线精确枚举（n ≤ 10 且 2ⁿ·K·P ≤ 2²⁰） | 乘积域逐层倍增，约 2 · 2ⁿ · K·P 次乘加 | ≤ 2.1×10⁶ 次乘加，峰值约 4 MB（float32） |
| 比值贪心（预筛后 n ≤ 20） | O(n² · K · P)，每轮一次矩阵–向量乘 | ≤ 1.6×10⁶ 次乘加 |
| 探索判定（按后验均值再选一次） | 同上 | 路由计算量 ×2 |
| 事后剪枝 | O(n · K · P)（增量维护未覆盖向量 v） | 可忽略 |
| 离线部分枚举 | O(n⁵) 次求值 | n=20 时约 3.2×10⁶ 次，只离线运行 |

### 6.12 路由示例（示意数值）

查询："machine learning asset pricing since 2023"，意图为 SEARCH。快路径把"since 2023"解析为硬谓词 `Range(year ≥ 2023)`，其余裸词成为软检索文本（§3.2）。
- **主题后验**（示意数值）：Finance 0.45，Artificial Intelligence 0.30，Economics and Econometrics 0.15，Statistics and Probability 0.10。
- **本地覆盖**（示意数值，recent 窗口）：各 subfield 依次为 0.70、0.92、0.60、0.80。cov_local = 0.45×0.70 + 0.30×0.92 + 0.15×0.60 + 0.10×0.80 = 0.761 < 0.9，因此联邦。
- **候选端点**：
  - arXiv legacy API 不在候选中：它的 SCD 不声明 SEARCH（§6.3 第 4 条；arXiv 只做中心镜像，CS §3-6）；
  - S2 取相关性检索 `s2.search`（`/paper/search`，每页 ≤100、合计 ≤1,000，RT §3.4、AG §2.2.3）。`s2.search_bulk` 不在候选中：它只能按 paperId、publicationDate 或 citationCount 排序（AG §2.2.3、§2.3.2），不是相关性端点，软文本不下推给它（§7.2 的 `bind_relevance_text`）；放宽后只剩 `year ≥ 2023`，预计总数远超分页上限，按 §6.3 第 5 条判为无界；
  - EPMC 在这些节点上的边际增益低于 `EPS_GAIN`。即便它进入精确枚举的最优集合，也会在事后剪枝时被剔除（§6.6），下表从略；
  - Crossref `works_query` 按 03 §4.1 的现行登记留作第三个候选（见表后说明）。数值见下表。

| 端点 | 成本 cu | 单独增益 Δf | 选中 OpenAlex 后的增益 | 比值（第 1 轮 / 第 2 轮） |
|---|---|---|---|---|
| openalex.works_search | 1.0 | 0.150 | — | 0.150 / — |
| s2.search | 3.0 | 0.090 | 0.035 | 0.030 / 0.0117 |
| crossref.works_query（按 03 现行登记） | 2.0 | 0.050 | 0.008 | 0.025 / 0.004 |

预算 B = 5 cu，候选 n = 3，在规模闸内，在线精确枚举。结论与贪心一致：
- 贪心第 1 轮选 OpenAlex（花费 1）；第 2 轮选 S2（花费 4）；
- 第 3 轮 Crossref 的剩余增益约 0.005，但加入后花费为 6，超出预算，跳过；
- 选定 {OpenAlex, S2}，f = 0.761 + 0.150 + 0.035 = 0.946 ≥ τ_cov；
- 最佳单源 {OpenAlex} 的 f = 0.911，小于贪心集合，取贪心集合。

本例的检索文本是软文本，Crossref `works_query` 以 `query.bibliographic` 按相关性返回，不算无界，所以按 03 的现行登记留在候选中，由目标函数淘汰；它走列表池（平台用 polite 池，3/s、并发 3，AG §0-1），影子价格也高。若查询含 Crossref 不能下推的硬短语，如 §7.4 的例子，它会在选源前就被第 5 条剔除。硬约束与目标函数两道关都能挡住不合适的源。

但按调研的结论，它本不该是 SEARCH 候选：AG 的 v2 结论是关键词检索不打 Crossref，`query.bibliographic` 只用于引文串匹配（AG §2.2.1、§2.4 R6）；SI-02 也要求不用关键词查询去打列表池。本文建议 Crossref 的 SCD 不为 `works_query` 声明 SEARCH，只把 `query.bibliographic` 留在 LOOKUP 标题匹配链的末级（§8.4）。本例的结论不受影响，因为它本来就被目标函数淘汰。该差异转 03 与主 agent（§20 第 33 项）。

---

## 7. 健全放宽

### 7.1 定义

- **放宽目标**：P 是规范化后的 `where`（NNF），s 是端点。放宽为 s 生成可下推的谓词 P_s，要求 **P ⇒ P_s**：按 s 所见的字段值，任何满足 P 的作品都满足 P_s。这样源侧只会多返回、不会少返回，精度由本地残差恢复（RT §3.5.3）。
- **等价改写**：P_s ≡ ∨_i P_{s,i}，把一个查询拆成多个子查询，再取并集。
- **残差**：本地对远端结果 R_s 再求一次原谓词 P，按 §3.5 的三值规则接受。
- **近似**：既不健全也不等价的变换，例如语义替身、跨分类转译、分页截断。近似可以用，但必须显式标注，且不能据此宣称完整。

### 7.2 算法（设计伪代码）

```python
# 设计伪代码
def relax(P: Pred, text: str | None, scd: SCD, stats, pi) -> RelaxResult:   # text = rank.relevance.text（软检索文本）
    P = to_nnf(P)                                  # 否定只作用于原子；此后 P 对每个文字都是单调的
    P = mark_local_only(P)                         # 不变式 I-2：Personal / Regex / 私有派生文字一律视为"不支持"
    approx = []

    def rx(node):
        match node:
            case And(children): return simplify(And([rx(c) for c in children]))
            case Or(children):  return simplify(Or([rx(c) for c in children]))
            case Lit(atom, neg):
                if scd.native(atom, neg):          # 原生支持（含否定支持；否定常被限制在 AND NOT 位置）
                    return node
                w = sound_weakening(atom, neg, scd)   # 正文字 a：找 a ⇒ w；负文字 ¬a：找 a' ⇒ a，用 ¬a'
                if w is not None:
                    return w
                if (a := approximation(atom, neg, scd, allow=scd.allow_approx)) is not None:
                    approx.append(a.kind)          # 仅在调用方允许近似时使用；否则落到 TRUE
                    return a.pred
                return TRUE                         # 不支持 → true（NNF 下 true 是最弱的替换）

    Ps = rx(P)
    subs = split_exact(Ps, scd)                    # OR 值表超限、URL 超长：等价拆分，并集不变
    subs = dnf_if_needed(subs, scd, max_clauses=8) # 源无 OR 能力时展开；超限则合并子句（健全但不再等价）
    text_q = bind_relevance_text(text, scd)        # 端点按相关性排序且有关键词检索能力时下推软文本，否则为 None
    # 无界判断必须针对最终下发的子查询，而不是 Ps：DNF 合并可能把某个子句弱化成 true（例如 9 个子句两两
    # 没有公共文字），此时 Ps 本身不是 true，却会下发一个无约束的子查询。
    unbounded = any((is_true(sj) and text_q is None) or
                    (not scd.ranked and est_count(sj, scd, stats, pi) > scd.page_cap)
                    for sj in subs)
    Pe = Or(subs)                                  # 实际下推的谓词（Ps 的健全弱化，§7.3 引理 1）
    return RelaxResult(Pe, subs, text_q, unbounded=unbounded, phi=fidelity(P, Pe), approx=approx)

def est_count(Pj, scd, stats, pi) -> float:        # 远端满足 Pj 的作品数的粗估 [判断]
    n_loc = stats.count(Pj)                        # 本地对 Pj 的计数（位图与 tsvector 的有界计数，§9.5）
    cov_s = sum(pi[t] * stats.cov(scd.endpoint, t) for t in pi)      # 端点在查询主题上的覆盖（route_stat）
    cov_l = sum(pi[t] * stats.cov_local(t) for t in pi)
    return n_loc * cov_s / max(0.05, cov_l)        # 按覆盖比外推；远端首页的总数（如 Crossref total-results）到达后
                                                   # 只用于修正截断标注，不回头改变本次选源
```

`unbounded=True` 的端点被路由器剔除（§6.3 第 5 条）。φ 与失配计数（§7.5 用对齐分析器重算下推谓词）都按实际下推的谓词 `Pe` 计算，因为 DNF 合并后的 `Pe` 可能比 `Ps` 更弱；本地残差仍用原谓词 P。按相关性排序的端点不做"预计总数超过分页上限"的检查：即使放宽很宽，只要带着软检索文本或非平凡的 P_s，它们的 top-k 仍有意义，召回损失由 η 与 φ 体现，结果标注 `truncated`。但 P_s ≡ true 且没有可下推的软文本时，排序端点同样剔除。

### 7.3 正确性论证

**引理 1（NNF 的单调性）**：设公式 F 只由文字经 ∧、∨ 构成（即 NNF）。若把每个文字 ℓ 替换为满足 ℓ ⇒ ℓ' 的 ℓ'，得到 F'，则 F ⇒ F'。

证明：对结构归纳。基例 ℓ ⇒ ℓ'。若 A ⇒ A′、B ⇒ B′，则 A∧B ⇒ A′∧B′，A∨B ⇒ A′∨B′。∎

**推论**：在 NNF 中，把不支持的文字替换为 true，或替换为健全弱化形式（正文字 a ⇒ w；负文字 ¬a ⇒ ¬a′，其中 a′ ⇒ a），都得到 P ⇒ P_s。

**为什么必须先化为 NNF**：在非 NNF 的树里，处于奇数层否定之下的原子是负极性。对它"替换为 true"反而会收紧查询。RT §3.5.3 给出的反例：`Not(A And Not(B))` ≡ ¬A ∨ B。若在原树中把 `Not(B)` 删掉（视为 true），得到 `Not(A)`，丢掉了所有"满足 B 且满足 A"的作品。

在原树上，等价的做法是"正极性原子替换为 true，负极性原子替换为 false"。本文统一先化为 NNF，因为 NNF 同时让下推更容易：很多源只支持 AND NOT 形式的否定。

**引理 2（残差完备）**：若同时满足
- (i) P ⇒ P_s；
- (ii) 源返回了全部满足 P_s 的作品，没有截断；
- (iii) 对下推文字，残差用与源一致的字段值与分析器语义；

则 {d ∈ R_s : P(d)} = {d ∈ s : P(d)}。

证明：⊆ 显然。⊇：任取 d ∈ s 且 P(d)。由 (i) 得 P_s(d)，由 (ii) 得 d ∈ R_s，残差保留 d。∎

**保证在哪里失效，以及对策**：
- (ii) 被分页上限或截止时间打破：
  - 各源的上限：OpenAlex 基础分页 ≤1 万条；Crossref offset ≤1 万；arXiv 合计 ≤3 万；S2 relevance 检索 ≤1,000（RT §2.2、§3.4、核验 V10/V15）；
  - 对策：标注 `truncated`，并在完整性报告中给出预计总数。
- (iii) 被分析器差异打破：见 §7.5 的监控与信任策略。
- 字段视图不同：源对自己缺失的字段做过滤时，通常直接排除该作品，所以完备性只相对于"源所见的字段值"成立。本地残差用三值逻辑处理本地的缺失（§3.5）。

**三条不变式**（属性测试的对象，§7.6）：
- **I-1 健全**：对任意 P 与 SCD，`relax` 的输出满足 P ⇒ P_s。
- **I-2 隐私**：`Personal`、`Regex` 与任何私有派生文字不出现在任何远端子查询中。编译器做静态检查，出站网关做审计复核（§15.4）。
- **I-3 不静默近似**：任何非健全变换都记入 `approx`，并出现在完整性报告中。

### 7.4 放宽规则表与下推保真度

**健全弱化**（正文字与负文字规则不同，这是 RT §3.5.3 表格未区分、本文补全的部分）：

| 原文字 | 源的限制 | 正文字的健全弱化 | 负文字的健全弱化 | 本地残差 |
|---|---|---|---|---|
| 短语 `"a b"` | 只支持词 | `a ∧ b` | **不可弱化**：¬"a b" 不蕴含 ¬(a∧b)，替换为 true | 短语匹配 |
| 邻近 `"a b"~n` | 支持短语或词 | `a ∧ b`。**不可**退化为短语：邻近不蕴含相邻（RT §3.5.3 原表的"退化为短语"不健全） | 源支持短语时用 `¬"a b"`（短语 ⇒ 邻近，故 ¬邻近 ⇒ ¬短语）；否则替换为 true | 邻近匹配 |
| 字段 `ti:x` | 只支持全字段检索 | `any:x`（前提：源的全字段检索覆盖标题） | **不可泛化**：¬ti:x 不蕴含 ¬any:x，替换为 true | 字段匹配 |
| 字段 `any:x` | 只支持标题检索 | 替换为 true | `¬ti:x`（因 ti:x ⇒ any:x，故 ¬any:x ⇒ ¬ti:x） | 全字段匹配 |
| 前缀 `mach*` | 不支持通配 | 替换为 true | 替换为 true | 前缀匹配 |
| 日期区间 | 只支持年份 | 扩到整年区间 | 替换为 true | 精确日期 |
| 分面 `dim ∈ V` | 只能映射 V 的一部分值 | 能映射全部值时按值映射；否则替换为 true | `¬(dim ∈ V′)`，V′ 为可映射的子集（因 dim∈V′ ⇒ dim∈V） | 分面 |
| 被引数区间 | 不支持 | 替换为 true | 替换为 true | 本地 |

**等价改写**：
- 超长 OR 值表按分配律拆成多个子查询，客户端取并集，结果集不变。OpenAlex 单个过滤的 OR 不超过 100 个值，请求 URL 约 4 KB 上限（RT §2.2）。
- 源只支持合取时展开为 DNF，每个子句一个请求。子句数上限为 8 [判断]；超限时把子句替换为它们公共文字的合取，即最小一般化。这一步健全，但不再等价。

**近似**（只在调用方允许时使用；一律标注，不用于完整性宣称）：
- 语义原子 → 关键词替身：远端没有语义能力时，从文本抽取关键词形成 `kw` 查询，最终排序在本地用向量重打（RT §3.5.3 表末行）。这一变换不健全，召回无保证。
- 跨分类体系转译：例如 topic → MeSH 或 JEL 集合。`maps_to` 的对齐并不完整（阈值 ≥0.85 时 F1 为 0.77，RT §6.2），直接转译会丢结果。默认只在"丢掉该过滤会导致无界"时启用，并标注 `approx_taxonomy`。
- 分页截断与截止时间截断：标注 `truncated`。

**下推保真度**：

```text
φ_s(P) = Σ_{ℓ 被 s 原生求值} I(ℓ)  /  Σ_{ℓ ∈ P} I(ℓ)
I(ℓ)   = −log₂ sel(ℓ)        （sel 为本地统计估计的选择率，越稀有的条件信息量越大）[判断]
```

φ=1 表示全部条件下推；φ≈0 表示源返回的几乎全是要在本地扔掉的候选。φ 有两个用途：作为 GBDT 路由特征（§6.9）；在截断标注中说明结果精度主要靠残差。原稿还让 η 按 φ 分三档学习，但 05 的 `evt.agg_route_eta` 以"端点 × 节点"为格子，分档会让每格的样本与不同用户数降到约三分之一，更多格子被 `k_cf` 聚合闸顺延（§6.8）；R0 因此不分档，有足够日志后再评估 [判断]。

**多源放宽示例**。查询：`(ti:"asset pricing" OR abs:"cross-section") AND NOT ti:"survey" AND year ≥ 2023 AND oa:true`。

| 端点 | 能力要点（以 03 的 SCD 为准） | P_s | 结论 |
|---|---|---|---|
| 本地 | tsvector 支持布尔、短语与字段；分面；年份 | P 全部 | φ = 1 |
| OpenAlex `search` | 布尔、短语（词干化）；年份与 OA 过滤（RT §3.4）；字段级限定 ⚠ | `search("asset pricing" OR "cross-section") ∧ year≥2023 ∧ is_oa` | 正文字做字段泛化，健全；¬ti:"survey" 不可泛化，替换为 true，交给残差。φ 较高 |
| S2 `/paper/search/bulk` | 布尔（RT §3.4）；年份、`openAccessPdf` 过滤（AG §2.2.3）；不按相关性排序 | `bulk("asset pricing" \| "cross-section") ∧ year≥2023 ∧ openAccessPdf` | 同上：去掉负文字。它不按相关性排序（AG §2.2.3），按 §7.2 须取完全部匹配；预计总数在续传上限（合计 ≤1,000 万，RT §2.2）内，不算无界，请求数按 ⌈总数 / 1,000⌉ 计入成本 |
| Crossref `/works` | `query.*` 无布尔或短语语法（RT §3.4）；日期过滤；无 OA 状态 | `from-pub-date:2023` | OR 不可下推，替换为 true；OA 也替换为 true。未按相关性排序，结果无界 → **剔除** |

### 7.5 残差、分析器对齐与"远端命中、本地拒绝"

**失配定义**：对端点 s 返回的每条记录 d，本地用 s 对齐的分析器档案重算 P_s(d)。结果为 F（而不是 U）时，计一次失配事件，记录端点与涉及的文字类型。因为远端声称 P_s(d) 为真，本地却判为假，这正是 RT §3.5.3 与 §12-6 要求单独计数的"远端命中、本地拒绝"。

**监控**：每日计算失配率 r_mis(s) = 失配数 / 返回数。超过 2% [判断] 时告警，并附失配样本，便于判断是分析器差异（如词干变体），还是源的语义变化（漂移）。

**信任策略**：每个端点在 SCD 中带 `residual_trust` 字段（04 向 03 提出的增补字段，见 §7.7）。
- `recheck`（默认）：残差对全部文字用对齐分析器重算。
- `trust_native`：对 s 原生求值过的文字，若 d 由 s 返回，直接取 T，只重算未下推的文字。启用条件：失配审计表明远端语义可接受（例如词干化召回的变体本就是用户想要的）；由人工在端点上显式开启，并留痕。

**补水后再残差**：远端记录经标识符解析命中本地作品时，先用本地合并后的记录补全字段，再做残差，减少 U。某些字段注定为 U：例如 Crossref 记录没有 OA 状态（AG §2.3.1 的字段可得性矩阵）。路由器通过 fidelity 偏好能提供残差所需字段的端点。

### 7.6 属性测试方案

测试框架用 Hypothesis。v1 dev 依赖已包含它（`pyproject.toml` 的 dev 组）。

- **生成器**：
  - 随机 AST：深度 ≤5，1–12 个文字，覆盖 Term 的各种 mode、Facet、Range、Not、ChannelRef；
  - 随机 SCD：能力原子的子集，含否定支持、字段限定能力、OR 能力、部分值映射；
  - 随机文档：字段可缺失，文本取自小词表，以便制造命中与近似命中。
- **性质**：
  - **P1 健全**：∀d，eval₂(P, d) ⇒ eval₂(P_s, d)（二值求值，使用源视图的字段）。
  - **P2 残差完备**：无截断、分析器一致时，`residual(simulated_source(P_s, corpus)) == filter(P, corpus)`。
  - **P3 等价改写**：`split_exact` 的各子查询结果的并集等于 P_s 的结果；DNF 子句合并之后只要求 P_s ⇒ Pe（健全），且任一子查询退化为 true 而无可下推软文本时 `unbounded` 为真。
  - **P4 隐私**：任何子查询都不含 Personal 或 Regex 文字。
  - **P5 规范化**：
    - canon(canon(q)) == canon(q)；
    - 子节点置换或 And/Or 重结合时，哈希不变；
    - NNF 保语义（在随机文档上求值结果相同）。
  - **P6 v1 兼容**：closed_world 求值与 v1 `filter_papers` + `arxiv.query_bool` 在生成样本上逐条一致。测试环境以 v1 代码为 oracle。
  - **P7 蜕变**：加一个合取项结果不增；加一个析取项结果不减。
- **固定回归用例**：
  - `Not(A And Not(B))` 的极性反例；
  - ¬ti:x 被泛化为 ¬any:x；
  - ¬"a b" 被弱化为 ¬(a∧b)；
  - 邻近被退化为短语。

  这四个错误变换都必须被测试判为违反 P1。另加一例无界回归：9 个两两没有公共文字的合取子句、源无 OR 能力时，DNF 合并得到 true，端点必须被判为无界并剔除（只看 `Ps` 的旧写法会漏判）。
- **实现层回归用例**（不属 P1，属求值器与编译器的等价性）：
  - 正则方言：v1 预置包的全部 `title_regex_any` 与 `exclude_regex` 模式（含 `\bagent(s|ic)?\b`、`\ba survey\b`），在应用层求值结果与 v1 `filter_papers` 逐条一致；若启用 PG 预筛，预筛结果必须是应用层结果的超集；
  - 邻近编译：`near(n)` 编译成的 tsquery 与参考实现（按词位间距 ≤ n、顺序不限）在随机文档上逐条一致；直接写成单个 `<n>` 的错误编译必须被测出（§9.2）。
- **规模** [判断]：CI 每次 2,000 例，夜间 10 万例。

### 7.7 对 SCD 的字段需求（供 03 核对）

SCD 的 schema 由 03 定义，是路由与放宽的唯一能力输入（SI-22）。本文所用的是 03 草稿中的字段口径：`predicates` 的支持等级 native / native_approx（带 `analyzer`）/ emulated / none，以及 `bool`、`serves`、`id_lookup`、`sort_keys`、`paging`、`cost`、`politeness`、`returns`。放宽编译器与路由器还需要以下细节：

| 需求 | 用途 | 03 草稿现状 |
|---|---|---|
| 文本谓词细分：短语、邻近、前缀或通配、字段限定（标题、摘要、全字段）各自的支持等级 | §7.4 的正、负文字弱化规则依赖这些区分 | 目前只有 `text.keyword` 一项，请细分 |
| 否定的位置限制，例如"只支持 AND NOT" | 判断负文字能否原生下推 | `bool.not` 已有；位置限制请在 note 中写明 |
| 分面的值映射表，例如文献类型、OA 状态的取值对照 | 判断分面可否整体映射，否则替换为 true（§7.4） | 请补 |
| 是否按相关性排序 | 判断放宽后结果是否"无界"（§7.2） | 可由 `sort_keys` 是否含 relevance 推出 |
| 分页与总量上限 | 截断标注与 η 学习 | `paging` 已有 |
| `analyzer`（native_approx 时） | 残差的分析器对齐（§7.5） | 已有 |
| `residual_trust ∈ {recheck, trust_native}`，默认 recheck | 残差信任策略（§7.5） | 新增 |
| `returns.fields` 与权利 | 预判残差中哪些文字会为 U；索引资格与查询即入库 | 已有 |
| `politeness.fake_success_patterns` | 伪 200 判为失败（§13.4） | 已有 |

---

## 8. 并行联邦执行器

执行器的全貌见 [v2-05-query-execution.svg](../../diagrams/v2-05-query-execution.svg)。

### 8.1 执行计划

路由器输出的计划是一张 DAG：
- **本地支路**：分面位图 → 选择率规划 → {BM25、tsvector 谓词、HNSW 或精确扫描、图邻域} → 本地列表；
- **远端支路**：每个被选端点的每个放宽子查询 → 出站网关 → 规范化 → 远端列表；
- **汇合**：各列表先在本列表内按 cluster 折叠，再做残差 → RRF 融合 → cross-encoder 重排 → 个性化挂点 → 流式输出。

每个远端子查询有一个 `plan_key = (endpoint_id, 规范化的下推参数, 页号)`。`plan_key` 不含任何用户信息，同时用作缓存键与 singleflight 键（§13.7、§13.8）。筛选条编辑后重新执行时，未改变的子查询直接命中缓存。

### 8.2 截止时间、fan-out 与流式合并

```python
# 设计伪代码 —— 交互道
async def execute(q, ctx, speculative=False, first_screen=None) -> AsyncIterator[Event]:
    D = ctx.deadline_ms or 3000                                   # 联邦总截止（简报 §3），自请求到达起算
    fs = await first_screen if first_screen is not None else None # 投机首屏的本地召回列表（§4.2）
    if fs is not None and fs.query_hash == q.hash:                # q.hash 即 canonicalize 返回的 query_hash（§3.6）
        lists = [fs]                                              # 定稿 AST 与首屏相同：复用，不重跑
    else:
        lists = [await run_local(plan_local(q, ctx.idx, depth=N_REC), ctx)]   # 本地支路永远执行（§9.5）；
                                                                  #   每路召回深度 N_REC，不是每页条数 q.k（§3.5）
        yield Event("snapshot" if fs is None else "upgrade",      # 采纳了 LLM 改写时：原位替换尚未看到的部分
                    merge(lists, q, ctx), completeness=partial(done=["local"]))
    if speculative:
        return                                                    # 投机首屏：只读本地，不路由、不出网
    plan = plan_route(q, ctx.snap, ctx.live, lists[0].pre_personal())   # §6.6；定稿后才路由。p_r 与 n_local_T 只取共享层、
                                                                  #   个人谓词与挂点之前的召回（§6.2）；不含 private 列表；
                                                                  #   LOOKUP 未命中时 plan.remote 只含一个替补链任务（§8.4）
    remote = {(s, sub.plan_key): spawn(run_remote(sub, deadline=min(D - ctx.elapsed() - MERGE_RESERVE, p99(s))))
              for s, subs in plan.remote.items() for sub in subs}  # 键含 plan_key：同一端点的多个子查询不互相覆盖
                                                                   # 不联邦时为空；MERGE_RESERVE = 150 ms [判断]
    async for (s, key), res in as_completed(remote, until=ctx.t0 + D):
        lists.append(normalize(res, endpoint=s))                  # 标识符解析、临时候选成组（§8.5）；同端点子查询在 merge 中先交错合并（§8.6）
        yield Event("source_status", s, res.status, res.counts)
        if res.ok:
            yield Event("upgrade" if ctx.user_idle() else "append", merge(lists, q, ctx, delta_from=s))
    for key in pending(remote):                                   # 截止后仍未返回者
        detach_to_cache(remote[key])                              # 礼貌成本已付：迟到结果写缓存，不丢弃
    yield Event("done", completeness=final(plan, remote))         # 每个 Event 带单调递增的 seq（见下文）
```

规则：
- **本地首屏**：本地首屏的 p95 目标 ≤800 ms（简报 §3），不等任何远端。
- **路由时点**：路由在本地召回完成之后、对定稿 AST 执行（§4.2），p_r 取首屏中共享层、个人谓词与个性化之前的命中（§6.2）。不需要 LLM 时，按 §14.2 的预算，远端 fan-out 约在 0.35 s 发出 [判断]，不等首屏的重排与序列化。
- **远端子截止**：子截止取剩余时间与该端点 p99 的较小者。出站网关在限速排队时，若预计等待会超过子截止，直接以 `budget_exhausted` 快速失败，而不是排队等待（§13.1）。
- **迟到结果**：截止后才返回的结果不进入本次响应，但写入缓存（§13.7），下一页或刷新时可用。
- **分页**：第一页之后的结果从本人的结果快照读取（02 §2.7(d) 的 PG 结果快照，键为 `query_hash`）。快照不足 n·k 条时：本地支路把各路召回深度加一个 N_REC 后重跑；远端支路只对未截断耗尽、且上一页已返回的端点取下一页（`plan_key` 页号加一），同样受交互道配额与影子价格约束，不重新选源。换页不改变 `query_hash`，已展示条目的顺序保持不变。
- **增量重排**：每次 `merge` 都走一遍"折叠 → 残差 → RRF → CE → 个性化挂点"（§8.1），但 CE 分数按 `(query_hash, work_id)` 在本次请求内缓存，只对新进入前 N 名的候选打分。`MERGE_RESERVE` 是 150 ms，而 CE 对 50 对样本约需 0.1–0.2 s（§8.7 的估算按比例折算），所以一次到达若带来的新候选打分预计超出剩余时间，先按 RRF 名次追加，CE 结果随后以 `upgrade` 替换未看到的部分。截止之后不再发起新的 CE 打分。
- **事件序号与续传**：每个事件带请求内单调递增的 `seq`，02 以它作为 SSE 的事件 id，断线后按 `Last-Event-ID` 从 PG 结果快照续传（02 §2.7(d)）。事件可重放：前端按 `seq` 去重，同一 `seq` 的事件重复到达时忽略。
- **流式事件**：流式事件与 07 的约定如下。
  - `snapshot`：首屏；
  - `upgrade`：只替换用户**尚未看到**的部分；
  - `append`：追加到可视区下方，或"更多来源"分组；
  - `source_status`：单个源的状态；
  - `done`：最终完整性报告。
  
  用户已看到的条目不移动，前端以 `cluster_id` 维持位置。

  02 §2.7(d) 的 SSE 流程图原稿用了另一套事件名：`meta`、`local`、`rerank`、`supplement`、`done`、`refine_suggestion`。一致性审计（2026-09-27）已把 02 §2.7(d)、§2.8.7 统一为本文的事件名、合并顺序与联邦意图集合（`suggest` 对应 §4.2 的 `stream.suggest`）。旧名对照如下，仅供追溯：

  | 本文（07 已按此消费） | 02 §2.7(d) |
  |---|---|
  | `snapshot` | `local` |
  | `upgrade`（CE 延后替换，或 LLM 采纳后的原位替换） | `rerank` |
  | `append` 与 `upgrade`（远端结果到达） | `supplement{source}` |
  | `source_status` | 无单独事件，可并入 `supplement` |
  | `done`（带完整性报告） | `done{missing_sources, budget}` |
  | §4.2 的建议筛选条（`stream.suggest`） | `refine_suggestion` |
  | 无（`query_hash` 与规范 AST 随 `snapshot` 下发） | `meta{query_id, canonical_query}` |

### 8.3 部分结果、缺源标注与完整性报告

每次响应都带完整性报告（P-06、P-09；SI-32"部分失败时返回部分结果并标注缺源"）：

```json
{
  "planned": ["local", "openalex.works_search", "s2.search"],
  "ok": ["local", "openalex.works_search"],
  "failed": [{"endpoint": "s2.search", "reason": "timeout"}],
  "est_coverage_planned": 0.946,
  "est_coverage_achieved": 0.911,
  "truncated": [{"endpoint": "openalex.works_search", "fetched": 50, "est_total": 1830}],
  "recall_depth": {"local_bm25": 100, "local_dense": 100},
  "approx": [],
  "unverified_results": 7,
  "data_as_of": {"local_corpus": "2026-09-27T05:40Z", "arxiv_watermark": "2026-09-26T22:30-04:00"}
}
```

- **覆盖估计**：`est_coverage_*` 用 §6.4 的 f 计算，所以"缺了哪个源、大约少了多少"可以量化，而不只是一句"部分失败"。
- **召回深度**：查询带软检索文本时，本地部分由各路召回的深度决定（§3.5），`recall_depth` 如实给出各路深度，不作完整性宣称。
- **数据时点**：`data_as_of` 给出本地语料与关键 WatchKey 的水位，回应"刚发的论文为什么看不到"（T4：实时性与上游限速的张力，调研综合 §5）。
- **前端呈现**（07 定义）：一行简短说明，例如"来自 本地 + OpenAlex；Semantic Scholar 超时（结果可能不全）"；点开可见明细。

### 8.4 同能力替补链与对冲

每项关键能力至少有两级替补（SI-22、P-09）。下表在 RT §3.5.5 与 AG §2.4 的基础上补充了合规闸门：

| 能力 | 替补链（首选 → 兜底） | 说明 |
|---|---|---|
| DOI 元数据（LOOKUP） | 本地 → Crossref `/works/{doi}`（single 池）→ OpenAlex 单实体 → S2 | OpenAlex 单实体不计费（RT §3.5.5）；DataCite DOI 改走 DataCite（AG §2.4 R1） |
| arXiv ID | 本地 → OpenAlex 单实体（按 arXiv 的 DataCite DOI `10.48550/arXiv.<id>` 单查）→ arXiv API（`id_list`） | arXiv DOI 由 DataCite 注册（CS §2.1.1）；OpenAlex 按该 DOI 单查可用，有实测实例（UX 核验 #30）。arXiv 全平台每 3 秒 1 次、单连接（RT §2.2）；交互道只留极小份额。CS §2.1.1 与 §3-6 建议多用户检索不把用户请求透传给 arXiv API；本文只在"本地与 OpenAlex 都未命中"的单篇 LOOKUP 上保留这一级，全平台一个令牌桶（HC-06），交互份额不随用户数增长，用尽即以 `budget_exhausted` 快速失败 |
| PMID / PMCID | 本地 → Europe PMC → OpenAlex 单实体（按 PMID 单查已实测可用；按 PMCID ⚠ 未核）→ PubMed E-utilities（NCBI 书面确认后才加入） | E-utilities 主机 robots 全禁与文档化 API 冲突（AG §3-14），且 AG §2.2.11 结论为须等 robots ADR 逐源登记后启用；按 R2-13，确认前不调用。OpenAlex 按 PMID 单查已实测可用且免费（一手来源，2026-09-27：`/works/pmid:16060722` 返回 W2144981148，`x-ratelimit-cost-usd: 0`），所以确认前 PMID 链仍有 EPMC 与 OpenAlex 两级远端，满足 P-09（§20 第 3 项）；按 PMCID 单查未核 ⚠（样本记录的 `ids` 中没有 pmcid，返回 404，不能据此判断是否支持），确认前 PMCID 链的远端实际只有 EPMC 一级。EPMC 受 Crawl-delay 10 秒约束（见"生命科学检索"行），链内顺序按网关给出的预计等待动态排定：EPMC 令牌要等数秒时，OpenAlex 单实体（免费）先行 |
| 标题精确匹配 | 本地三元组 → S2 `/paper/search/match` → Crossref `query.bibliographic` | 后者走列表池（平台用 polite 池：3/s、并发 3；public 池为 1/s，AG §0-1）。引文串与标题匹配正是调研认可的 Crossref 列表类用法（AG §2.4 R6） |
| OA 全文定位 | 本地（快照中的 `best_oa_location`）→ OpenAlex 单实体 `best_oa_location`（免费）→ Unpaywall → CORE | Unpaywall 已于 2025 年末迁入 OpenAlex 数据库，两者同源（AG §2.2.4、CP §2.1）：它只提供主机级替补，不是独立数据源。按 AG §2.4 R11 与 CP §2.4，OA 定位以 OpenAlex 为主、Unpaywall 只作兼容补查。CORE 在取得许可前停用（CP §2.1）；PDF 下载仍走用户侧通道（P-03） |
| 语义探索 | 本地 ANN → OpenAlex `search.semantic` → S2 Recommendations | 远端只作补充；种子隐私见 §4.6。OpenAlex 语义检索仍是 beta（AG §2.4 R7 ⚠）；S2 推荐受全端点共用的 1 RPS 约束，AG §3-11 认为它不能支撑多用户实时调用。两级远端都只低频、用户显式触发，交互道份额用尽即跳过 |
| 引文扩展 | 本地图 → OpenAlex `cites:` → OpenCitations → S2 citations | 各源被引数不一致，不相加（AG §3-19） |
| 生命科学检索 | 本地 → Europe PMC → OpenAlex search（NCBI 书面确认后再加入 PubMed，R2-13） | EPMC 可作可下推的联邦后端（LS §3-10），但 `www.ebi.ac.uk` 的 robots 对通用 UA 设 `Crawl-Delay: 10`，按 P-05 全平台每 10 秒至多 1 次，并与 `FIRST_IDATE` 收割共用账本键（AG §2.2.10、§2.3.3；03 §4.4、§8.5）；数值限额未公布 ⚠，LS §2.3.3 建议多用户上线前与 EBI 约定用量。交互份额因此极小：同一时段的第二个生命科学查询多半以 `budget_exhausted` 快速失败，由 OpenAlex 承担（§10.4） |
| 最新论文 | 本地（P-01），无远端链 | "按需刷新"只提升 WatchKey 优先级（§11.6） |

**执行**：链默认顺序执行，上一级失败或未命中时才走下一级。链内排序依据：预计延迟（顺序执行时可加）、成本、字段完整度。

**对冲**：首选端点超过其 p95 仍未返回时，并行发出链中下一个**不同主机**的端点（Tail at Scale：等到 p95 再对冲，额外负载约 5%，RT §9.1）。约束：
- 每个端点每小时的对冲请求 ≤ 该链请求数的 5% [判断]，并计入预算；
- **绝不对同一第三方主机对冲**（P-04、RT §9.1）。计划构建器做静态检查，出站网关做运行时拒绝。

### 8.5 按 cluster_id 折叠

1. **标识符规范化**：DOI 小写、去前缀；arXiv 去版本号；PMID、PMCID、OpenAlex W、S2 corpusId、SSRN id 按各自规则处理（RT §7.3）。
2. **解析**：经 05 的 `corpus.identifier(scheme, value)` 找到 `version_id`，再经 `corpus.version.work_id` 得到作品。05 的一个 `corpus.work` 就是一个 cluster，`work_id` 即简报 §5 所说的 `cluster_id`（05 §3.1.2）。它由 03 的 identify 阶段物化，04 只消费。
3. **临时候选**：解析不到的远端记录，在本会话内按**强标识符**做 union-find 成组。远端记录本身常同时带 DOI 与 PMID，可据此成组。**弱信号不合并**（D-007）：同标题、首作者、年份只作"可能重复"的展示提示。
4. **先列内、后列间**：
   - 每个排序列表内先折叠，cluster 在该列表的名次取其成员的最小名次；
   - 然后才跨列表做 RRF。

   否则同一作品的预印本与正式版在同一列表里会被重复计分。例如 OpenAlex 常把两者作为两条记录分别返回。本地列表的粒度本来就是作品（§9.2），列内折叠主要针对远端列表。
5. **代表版本**：取 05 的 `corpus.work.canonical_version_id`（展示用首选版本）。临时候选没有该字段时，沿用 v1 的确定性规则，取类内（−identifier 数, id）最小者（v1 design/06 §3 T13）。卡片上用版本徽标呈现"预印本 v3 / 已发表于 JFE"。
6. **折叠只发生在结果集内**：沿用 v1 语义，幸存条目不重排，一篇著作不会从清单中整体消失（v1 design/06 §3）。
7. **查询即入库**：许可允许共享的临时候选，在 enrich 道排入 03 的流水线（normalize → identify → enrich）。能否入库由 03 的来源通道许可与 `display_scope` 判定，并参考 SCD 的 `returns.rights`，04 不另设判断。语料因此按真实需求增长，贴合 B-04 的"全体用户兴趣并集"。允许平台级缓存、但不允许进入共享语料的记录（例如只可展示到受限级别的字段），只进入 TTL 缓存。TTL 缓存同样是跨用户的平台级存储：只收来源条款允许平台级缓存的数据（AG §2.3.4 的"可缓存"列），条目保留字段级权利标签（HC-07），展示仍经 08 的展示闸；条款不允许平台级缓存的来源（如 Lens、Scopus、WoS，AG §2.3.4）本就不进入平台路由。入库与缓存的记录都不保存触发它的查询或用户（§15.4 第 5 条）。

### 8.6 RRF 融合

```text
score(c) = Σ_L  w_L / (k + rank_L(c))        k = 60，rank 从 1 起（RRF09；RT §4.2）
```

- **列表**：
  - 本地 BM25（标题）、本地 BM25（标题+摘要）、本地稠密；
  - 每个远端端点一个列表：同一端点的多个子查询先按名次交错合并。
- **无相关性排序的远端列表**（如按日期返回的过滤列表）：先用本地语料的 IDF 对返回记录做 BM25 打分排序，再参与融合 [判断]。
- **权重**：w_L 默认 1。有日志后按意图分桶学习（RT §4.2），并约束远端列表的权重不高于本地列表 [判断]，防止单个远端源的噪声主导。
- **外置引擎**：若将来改用外置引擎，须显式设 k。Qdrant 的默认 k=2 且名次从 0 起（RT §4.2）。
- **不融合的情况**：`rank.sort` 为 recency 或 cites 时，不做相关性融合，按键排序，并列时用融合分决胜。LATEST 为单一本地列表，不需要融合。

### 8.7 Cross-encoder 重排

- **输入**：查询文本 + 标题 + 通过 §9.1 权利闸的摘要，截断到 ≤192 token [判断]。
- **范围**：简报 §6.2-4 的 top-100 按 R2-39 改为上限：纯 CPU 的 T1 从小模型 int8、top-50 起步；超预算时先发 RRF 结果，重排结果经流式 `upgrade` 补发。
- **成本估算** [估算]：Transformer 前向约为 2 × 非嵌入参数量 × token 数 FLOPs。
  - 约 1,000 万非嵌入参数的小型交叉编码器，192 token × 100 对 ≈ 3.8×10¹¹ FLOPs。
  - 0.6B 级重排器（如 Qwen3-Reranker 系列，RT §4.1）≈ 2.3×10¹³ FLOPs。
  - 若 CPU 的有效吞吐按 5×10¹¹ FLOP/s 计（**假设值，须在目标硬件实测**），前者约 0.8 s，int8 量化后约 0.2–0.4 s；后者在纯 CPU 上约 46 s，不可行。
- **结论**：
  1. T1 默认用小型交叉编码器，int8，≤192 token。先对 top-50 重排，若压测余量允许再扩到 top-100。
  2. 有 GPU 推理服务时（与嵌入服务共用，由 02 决定），可以启用 0.6B 级重排器。
  3. 重排可以延后：本地首屏若会超出 800 ms 预算，先发未重排的 `snapshot`，重排结果以 `upgrade` 事件替换尚未看到的部分。

  "top-100"因此是上限而非硬性要求（§19-4）。
- **收益验证**：LitSearch 上，LLM 重排在最佳稠密检索器之上还能提升 4.4%（RT §4.1）。本平台的收益以自有评测为准（§14.1）。若某学科的重排不优于融合基线，就在该学科关闭重排。
- **权利**：重排器只读通过索引资格的文本，与建索引同一道闸（§9.1）。
- **许可**：候选模型的权重许可与训练数据条款都要过 B-06 门禁（§1.6）。Qwen3-Reranker-0.6B 为 Apache-2.0；常见的小型交叉编码器（如 cross-encoder/ms-marco-MiniLM-L6-v2，约 2,270 万参数，与上文"约 1,000 万非嵌入参数"同一量级）权重为 Apache-2.0，但以 MS MARCO 训练，HF 上该数据集的元数据未声明许可（均据 HF 模型卡与数据集页，一手来源，2026-09-27 查阅）。训练数据条款对"可能商用"部署的影响 ⚠ 未核，核清前不作默认，V1 选型时一并登记。

### 8.8 个性化挂点（与 06 的接口）

挂点的打分函数由 06 提供，名称与签名以 06 为准（06 §7.9 与接口表）；融合方式由 04 决定（FR-84）。

```text
# 设计伪代码：挂点接口与融合公式
personal_score(u, work_ids) → [(work_id, ŝ)]                    # 06 提供：校准后的个人分
s_final(c) = z(s_ce(c)) + β · z(max_{w∈c} ŝ(w))                  # 04 融合；z 为本次候选内的标准化；β 默认 0.3 [判断]
```

- **调用时机**：交叉编码器重排之后，对前 100 条（06 §7.9 约定的范围）调用，运行于用户上下文（RLS）。cluster 的个人分取其成员的最大值。
- **位移上限**：SEARCH 中每个条目最多移动 Δ = 5 位 [判断]，查询相关性优先。LATEST 与频道视图是信息流，不设上限，排序由 06 的 ValueModel 决定。
- **LATEST 与频道视图的两段式**：这两类视图没有 CE 顺序可依。若按时间取前 100 条再交给挂点，个性化只会在最近的 100 篇里重排。仅 cs.LG 一周就约有 1,861 条 OAI 记录（含替换版与交叉列表，CS §2.6.1；§10.2），其余的都排不上来。因此：
  1. 先做本人质心预排：对候选集 C′ 精确计算其推荐空间嵌入（与 `usr.user_vector` 同一模型）与本人各质心的最大余弦。|C′| ≤ 2 万时算术约 2×10⁴ × 5 × 256 ≈ 2.6×10⁷ 次乘加，毫秒级；但要从 PG 读出 2 万条 256 维 halfvec，约 10 MB，热缓存下为数十毫秒 [估算]，这才是主要开销。|C′| > 2 万，或实测超出 §14.2 中本阶段的预算时，改为以各质心为查询向量、带时间窗与分面过滤做 HNSW 迭代扫描（§9.5），各取前 100 条后合并 [判断]；
  2. 取预排前 100 条调用 `personal_score`，按其分数排序；
  3. 其余条目按 `first_public` 倒序接在后面，翻页时对下一段重复以上步骤。

  质心在本人 RLS 上下文中读取，预排结果不进任何共享缓存。06 §7.9 把挂点范围写作"04 的前 100 条结果"，在这两类视图中即指上述预排的前 100 条（§20）。
- **可见与可关**：开启时结果页标注"已按你的兴趣排序"（FR-84）。本次查询 `personalize=off`、用户的 `profile.personalization_mode ∈ {np_time, np_source}`（R2-05，05 的取值）或挂点失败时跳过，排序只取决于 `query_hash` 与语料版本，可复现（HC-13）。非个性化模式下 LATEST 与频道视图的排序：`np_time` 按 `first_public` 倒序；`np_source` 按来源或 venue 分组，组内按 `first_public` 倒序（06 §13.5 的两种排序）。06 写作"首见时间"，本文 LATEST 按 §3.5 用 `first_public`：回填进来的旧作品首见时间很新，按首见时间排会被当成新论文排在前面。口径差异请 06 对齐（§20 第 28 项）。
- **输出隔离**：个人分与理由码只对本人可见，不进入任何共享统计或缓存（P-02）。

---

## 9. 本地索引

### 9.1 索引资格（权利闸）

共享索引（BM25、tsvector、嵌入）以及交叉编码器的输入，只收权利引擎放行的字段。权利引擎属于 08（DI-01），按 HC-07 为每个字段给出 `rights_class`（M1–M25）、`display_level_max`（DL0–DL4，即 CP 的展示级别 V0–V4，按 R2-03 改名）、`shareable`、`commercial_ok`。04 由此派生 `index_scope ∈ {index_and_embed, index_only, none}`。

默认规则如下（**默认假设**，待 08 与法务就 LQ-02、LQ-17 定论）：

| 字段与权利类（CP §2.7） | 共享词法索引 | 共享嵌入 | CE 输入 | 依据 |
|---|---|---|---|---|
| 书目元数据（M1） | ✓ | ✓ | ✓ | 事实或 CC0 |
| A 类摘要（M4：CC0 或开放许可） | ✓ | ✓ | ✓ | CP M4 |
| B 类摘要（M5：版权保留、公开分发） | ✓（默认，R2-21） | ✓（默认，R2-21） | ✓（默认假设） | CP §2.3 的判断为"⚠ 可用于内部索引和嵌入（LQ-02），只展示到 V3"，即 DL3；R2-21 已裁定默认纳入、不展示、设开关；展示仍受 HC-08 限制 |
| B 类且出版方有机器可读的 TDM 或 AI 输入保留（TDMRep、Content-Signal） | ✗ | ✗ | ✗ | 与 HC-11(b) 同类的信号；对应规则待 LQ-17 |
| B 类且出版方只在条款中以自然语言保留 TDM（如 SN、Elsevier，CP §2.3.2） | ✓（R2-21 默认，⚠ 待裁定） | ✓（同左） | ✓（同左） | CP §2.3.2 建议"把自然语言保留也当作有效保留"（欧盟 DSM 第 4 条）。照此执行，Elsevier、SN 的 B 类摘要将退出共享索引，心理、金融等学科的检索会明显退化（AG §2.6）。本文暂按 R2-21 默认纳入，由权利引擎的字段级标签（HC-07）区分保留类型，裁定后按下文的可逆机制定向重建；由主 agent、08 与法务裁定（§19-18、§20 第 34 项） |
| C 类摘要（M6：出版商 API 个人许可，含 IEEE API） | ✗ | ✗ | ✗ | CP M6；IEEE ToU 禁止用程序"index any portion of the Content"（CS §3-8） |
| S2 TLDR（M7） | ✓ | ✓ | ✓ | 须署名"Semantic Scholar"（CP M7） |
| 平台 TL;DR（M8 / M9） | M8 ✓；M9 待 LQ-05 | 同左 | 同左 | CP M8/M9 |
| 私有全文及其派生（M10、M16、M17、M25） | 共享 ✗；本人私有索引 ✓ | 同左 | 仅本人 | P-02、HC-01 |

**全文不进共享索引**：共享层不建全文索引。arXiv e-print（PDF、源文件，以及从中抽取的文本和图）不进入任何共享索引或缓存（HC-06、CP §2.1）；CC 许可的 OA 全文若将来要建共享全文索引，须按篇过许可白名单（HC-05）。`fulltext` 条件（§3.7）只发往支持远端全文检索的端点，本地不留存全文。

**为什么 B 类默认纳入**：
- 心理学与多家出版方的 Crossref 摘要覆盖为 0（AG §2.6）。这些学科的摘要文本主要来自 OpenAlex 倒排索引、PubMed、Europe PMC，全部属于 B 类。若排除 B 类，这些学科的语义检索与主题标注都会严重退化。
- 法律上，美国先例支持"合法取得副本做索引、只展示有限片段"的模式：HathiTrust 与 Google Books 案（CP §2.3 法域表，◐）。欧盟法下另有一层：为索引与嵌入复制摘要可能落入 DSM 第 4 条的 TDM 例外，而权利人明示保留时例外不适用；CP §2.3.2 建议把条款中的自然语言保留也视为有效（上表对应一行）。
- R2-21 已按此裁定：默认纳入词法索引与嵌入，不展示（展示上限 DL3），可逆重建并设开关；LQ-02 结论为否时关闭并重建。法务结论仍待 08（§19-11、§20）。

**开关**：部署配置 `index.b_class_abstracts ∈ {on, off}`，默认 `on`（R2-21）[判断：配置名由 02 定]。改为 `off` 时触发下述定向重建；重建完成前，查询照常使用旧索引，重建按行原子切换。

**可逆性**：
- 05 的检索文本与嵌入都记录输入的权利血缘：`corpus.work_search.input_rights_max` 与 `corpus.work_embedding.input_rights_max` ∈ {A, B}（05 §3.1.8–§3.1.9）；
- 策略变化时，按该列定向重建受影响的行。例如 LQ-02 结论为否定时，把 `input_rights_max='B'` 的行改为只索引标题与元数据，并重算嵌入；
- 重建作业须在夜间窗口内完成（AC-V2.20）。

### 9.2 词法：pg_textsearch BM25 + tsvector/GIN

检索文本表以 05 的 `corpus.work_search` 为准（05 §3.1.9）。它按作品一行（即 cluster 级），不分区；`search_text` 为题名、展示选用的摘要与关键词的拼接；另有 `input_rights_max` 与冗余的过滤列。05 把 tsvector + GIN 列为 pg_textsearch 不可用时的降级路径；本文需要它作为**常设的谓词层**，因此提出以下增补需求：

```sql
-- 设计伪代码 DDL：本文对 corpus.work_search 的增补，05 已采纳（05 §3.1.9，title_text 为 NOT NULL）
ALTER TABLE corpus.work_search
  ADD COLUMN title_text    text,           -- 单独保存标题：供标题 BM25 列表与 ti: 谓词
  ADD COLUMN abstract_text text,           -- 只放通过 §9.1 权利闸的摘要，否则为 NULL：供 abs: 谓词
  ADD COLUMN tsv tsvector GENERATED ALWAYS AS (
      setweight(to_tsvector('english', coalesce(title_text, '')),    'A') ||
      setweight(to_tsvector('english', coalesce(abstract_text, '')), 'B')) STORED;
CREATE INDEX work_search_tsv ON corpus.work_search USING gin (tsv);
-- 布尔（& | !）、短语（<->）、定距（<N>）；'x:A' 限定标题，'x:B' 限定摘要
-- BM25（pg_textsearch）：search_text 与 title_text 各建一个索引，作为两个排序列表进入 RRF [判断]
```

两处编译细节：
- **邻近**：PG 文档对 `<N>` 的定义是"指定两个词位之间的距离"，`<->` 等价于 `<1>`（PG 18 文档 §8.11.2；`phraseto_tsquery` 用 `<N>` 为被去掉的停用词占位，见 §12.3.2；一手来源，2026-09-27 查阅）。它表达的是定距，不是"距离不超过 N"。本文的 `near(n)`（§3.3）因此编译为 ∨_{d=1..n} (a <d> b ∨ b <d> a)，多词时逐对展开；直接写成 `a <n> b` 会漏掉距离更近或顺序相反的命中。
- **跨字段误配**：`tsv` 是标题与摘要两段 tsvector 的拼接。拼接时右段的词位整体加上左段的最大词位（PG 18 文档 §12.4.1，一手来源，2026-09-27 查阅），标题末词与摘要首词因此在词位上相邻。`ti:`、`abs:` 的短语与邻近须带权重限定（`'a':A <-> 'b':A`）；`any:` 的短语不限定字段，会有极少量跨字段误配，由残差在原文上复核。

- **分工**：
  - **pg_textsearch** 负责 BM25 排序。它是 PostgreSQL 许可，v1.4.0，正式支持 PG 17/18，k1 与 b 可配，Block-Max WAND，支持表达式、部分与分区索引（RT §5.2）。简报 B-01/B-06 的默认 BM25 扩展即它，ParadeDB 为 AGPL，只作可选。
  - **PG 原生 tsvector/GIN** 负责谓词求值：布尔 `& | !`、短语 `<->`、邻近 `<N>`。频道、残差与布尔检索都用它。

  RT 对 pg_textsearch 的记录中没有提到短语或布尔查询能力 ⚠，谓词语义因此不交给它。PG 原生全文正是 D-034 决策 6 为 PG 路径规划的方案（tsvector 生成列 + GIN），v2 把它保留为谓词层，在其上加 BM25 排序层。
- **不分区**：pg_textsearch 的 BM25 统计（IDF）按分区各自计算，跨分区分数不可比（RT §5.2 核验补充）。05 的 `work_search` 刻意不分区，T1 ≤1,000 万行。
- **分析器对齐 ⚠**：pg_textsearch 的分词与 PG `english` 配置是否一致，未经核验，实现期须实测。不一致时以 tsvector 为匹配语义的权威，BM25 只负责打分。
- **多语种**：
  - 中文查询经可选的 LLM 生成英文检索词，同时走多语向量通道（§4.5）；
  - 中文作品多为用户导入，属私有索引（SI-19）；
  - 共享层的中文全文分词能力 ⚠ 未核验，列为后续工作。
- **存储** [估算]：05 按 v1 FTS5 实测口径估算 `work_search` 连同 BM25 索引在 300 万篇时约 8 GB、1,000 万篇时约 26.5 GB（05 §8.2）。增补的 tsvector 与 GIN 会在此之上增加同量级的体量，待实测。

### 9.3 稠密：halfvec HNSW + iterative scan

- **表**：05 的 `corpus.work_embedding(work_id, model_key, vec, input_rights_max, input_hash, …)`（05 §3.1.8）。
  - 按模型建部分 HNSW 索引，形如 `USING hnsw ((vec::halfvec(d)) halfvec_cosine_ops) WHERE model_key = …`；
  - **索引维度 d 随 Q7 的选型而定**。SI-40 的"统一存 256 维"依据是 Scholar Inbox 在推荐任务上的结论，以及 Qwen3-Embedding 与 OpenAI 模型支持截短（SR §3.1-3）。调研没有记载 gte-large 或 SPECTER2 支持 MRL 截短，直接截到 256 维对检索质量的影响 ⚠ 未经评测。因此：
    - 选中支持 MRL 的模型（如 Qwen3-Embedding-0.6B）时，建 256 维索引，全维向量作为另一个 `model_key` 行保存，只对召回候选做全维精排、不建索引 [判断]；
    - 选中不支持 MRL 的模型（gte-large 1,024 维、SPECTER2 768 维）时，用全维建索引，与 02 §2.11 的 A-6"检索用 1,024 维"一致；若要降到 256 维（PCA 等），须在 V1 的分学科评测中证明检索质量不低于全维，否则不降；
    - 推荐用的 256 维向量（06、02 A-6）是另一个 `model_key`，与检索索引互不替代。§4.6 所说"与 OpenAlex `search.semantic` 同空间重打分"要求保存 gte-large 的全维向量；
  - 两份文档的差异（本文原稿写"统一 256 维"，02 A-6 与 05 `embedding_model.purpose` 写"检索 1,024 维"）交主 agent 定稿（§19-15）；
  - `input_rights_max ∈ {A, B}` 记录嵌入输入的权利血缘，与 §9.1 的索引资格一致；
  - 模型换代时新旧模型同时处于 active/shadow，双写（RT §12-10）。
- **HNSW 参数**（RT §5.2、§5.4）：
  - 建索引 m=16，ef_construction 取 64–128；
  - 在线用 `SET LOCAL hnsw.ef_search = max(depth, 2k)` [判断]，depth 默认为 N_REC = 100，翻页时随召回深度增加（§8.2）。k 是每页条数，depth 是每路召回深度（§3.5）；不开迭代扫描时 HNSW 最多返回 ef_search 条，取 2k 会让稠密通道只贡献 40 条，与 §8.3 报告的召回深度不符；
  - 带过滤的查询开启 `hnsw.iterative_scan = relaxed_order`，用物化 CTE 恢复顺序；`hnsw.max_scan_tuples` 默认 20,000。
- **内存** [估算]：按 RT 的粗估口径，每向量 = 向量字节 + 约 2m×6 B 邻居指针 + 约 64 B ⚠。256 维 halfvec 约 768 B/向量，300 万篇约 2.3 GB，1,000 万篇约 7.7 GB。1,024 维约 2,304 B/向量，300 万篇约 6.9 GB，1,000 万篇约 23 GB（RT §5.3），仍在 T1 参考硬件 64–128 GB 内存的常驻范围内（RT §5.3 的判断）。

### 9.4 分面：Roaring 位图 + GIN/B-tree

- **位图缓存**：检索服务在进程内维护分面位图，每个 (dim, value) 一张 Roaring 位图（CRoaring/PyRoaringBitMap，Apache/MIT，RT §6.3）。维度包括：subfield（252）、topic（4,516）、年份、`first_public` 日桶、类型（`type`）、研究类型（`pubtype`）、OA 状态、语言、venue、arXiv 类目、评审状态、撤稿与更正状态（`status`，取自 05 `corpus.work_badge`）、许可类、来源溯源（`src:`）。
- **内存** [估算]：1,000 万篇、每篇约 10 个分面成员时共 1×10⁸ 个成员。稀疏分面按数组容器约 2 B/成员，稠密分面按位图容器约 1 bit/成员，合计 ≤250 MB。
- **维护与一致性**：检索服务随 API 水平扩展（02 P3，2–4 个副本，每副本可有多个工作进程），而 `index` 段运行在后台工作者里，写不到这些进程的内存。原稿"入库时在 `index` 段追加 ID"因此无法生效，新作品会在夜间重建之前一直不出现在 LATEST 与分面检索里，违背 NFR-12。改为：
  - `index` 段为每行写入单调递增的 `index_seq`（或复用 `work_search.updated_at` 水位，列由 05 定）；
  - 每个进程每 ≤60 s [判断] 拉取水位之后的新行与变更行，把 ID 并入位图，并记下自己的水位 `bm_seq`；
  - 求值时对 `index_seq > bm_seq` 的尾部用 SQL（B-tree/GIN）补查，与位图结果合并。这样即使某个进程的同步滞后，结果也不漏；
  - 作品合并后，候选 ID 一律经 `merged_into` 映射到存活作品再去重（与 §9.6 同一规则）；撤稿等状态变化走同一增量通道；
  - 夜间全量重建，并抽样与 PG 计数对账（§9.9）。
- **多进程内存**：位图（≤250 MB）与 TSRG 快照（约 45–140 MB，§5.6）按进程常驻，每台主机的占用要乘以工作进程数。同机多进程共享只读基线的方式（如按 CRoaring 的可移植格式落盘后映射）实现期定 ⚠；容量表按进程数折算（§14.3）。
- **PG 侧**：`topic_ids int[]` 建 GIN；`year`、`venue_id`、`first_public_at` 建 B-tree。这些供 SQL 路径与 Percolator 使用。
- **ID 约束**：`work_id < 2³²`，32 位 Roaring 可用；超出时切换 64 位 Roaring。

### 9.5 选择率规划

```python
# 设计伪代码
T_EXACT = 20_000                 # 与 pgvector hnsw.max_scan_tuples 默认值同量级（RT §5.2、§6.3）
N_REC = 100                      # 每路召回深度（§3.5）[判断]；分页时按 N_REC 递增（§8.2）

def plan_local(q, idx, depth=N_REC):                          # depth 是每路召回深度，不是每页条数 q.k
    bm, ts, rel, sem, resid, pers = split_literals(q.where)   # 位图可求 / tsvector / 图 / 语义 / 仅残差 / 个人
    C = eval_bitmaps(bm, idx.facets) | idx.tail_since(idx.bm_seq, bm)   # AND→∩，OR→∪，NOT→差；尾部补查（§9.4）
    if ts:                                                    # 硬性 tsvector 谓词可能极具选择性，须计入候选基数
        C_ts = gin_probe(ts, facets_sql=bm, limit=T_EXACT + 1)   # 一条 SQL：GIN 谓词与分面条件一起下推（PG 以
                                                              #   BitmapAnd 组合 GIN 与分面索引），最多取 T_EXACT+1 条
        if len(C_ts) <= T_EXACT:
            C, ts = C_ts, []                                  # 已精确求得交集，后续不再重复过滤
    N = idx.n_works
    if q.rank.kind in ("recency", "cites", "issue", "personal"):   # 非相关性排序（personal 的两段式见 §8.8）
        return SortedScan(C, key=q.rank.kind, filters=[ts, rel, sem, resid])
    if len(C) <= T_EXACT:                                     # 小候选集：精确计算
        return ExactScore(C, bm25=q.rank.relevance.text, dense=True, depth=depth, filters=[ts, rel, sem, resid])
    sigma = len(C) / N
    if depth / sigma <= 0.5 * idx.max_scan_tuples:            # 迭代扫描预计能凑满 depth 条（过滤与向量近邻独立时）
        return IndexScan(hnsw_iterative(C, ef=max(depth, 2 * q.k), limit=depth),
                         bm25_filtered(C, q.rank.relevance.text, limit=depth),
                         filters=[ts, rel, sem, resid])
    return ExactScore(C, parallel=True, depth=depth, flag="large_exact")   # 大候选集、低选择率：并行精确扫描；
                                                              #   更大规模时走 §14.4 升级
```

原稿只用位图估计选择率。硬性的 tsvector 谓词（如一个罕见短语）选择率可低到 10⁻⁵，候选集 C 却仍按位图算作"大"，于是走 HNSW 迭代扫描；扫满 `max_scan_tuples` 也凑不齐 k 条，召回塌陷。有界 GIN 探测把这类查询导向精确路径，代价以 T_EXACT+1 行封顶。分面条件必须和 GIN 谓词写在同一条 SQL 里：若先单独探测 GIN 再在应用层与 C 求交，常见短语的 GIN 结果会先撞到 T_EXACT+1 的上限，而它与罕见 venue 的交集其实很小，探测就失去作用。

- **精确路径的依据**：pgvector 文档的示例中，过滤选择率 10%、ef_search=40 时平均只剩约 4 行结果（RT §6.3），因此"过滤 + HNSW"必须开迭代扫描，或改走精确路径。
- **成本** [估算]：|C| ≤ 2 万时，精确距离计算在 256 维 halfvec 下约读 10 MB，1,024 维下约读 40 MB（RT §6.3）。距离算术本身是毫秒级；PG 逐元组的执行开销与堆页访问才是主要部分，热缓存下约为十到数十毫秒，冷缓存下取决于随机读，须实测。
- **阈值**：阈值取法与 Qdrant `full_scan_threshold` 的思路一致（RT §6.3），须实测校准。
- **求值顺序**：先位图求交，再 tsvector 谓词，最后仅残差的谓词。个人谓词在最后用位图做差（§9.6）。

### 9.6 已见集合（Roaring）

- **存储**：05 的 `usr.seen_segment(user_id, kind, period, bm)`（05 §3.2.5）。用 pg_roaringbitmap（Apache-2.0）按月分段存 `work_id` 集合，`kind` 分 `served`（已下发）与 `decided`（已决策）；RLS 保护。每用户一年约 150 KB，1 万用户约 1.5 GB（RT §7.2 [估算]）。
- **求值**：`NotSeen` 对最近 N 个 `served` 分段取并集后做差（N 默认 12，即一年 [判断]）。
- **更新**：由 06 的下发与事件驱动，按批次写入（05 §3.2.5）。本会话内另有一份内存排除表，使已见立即生效。
- **cluster 语义**：05 的 `work_id` 就是 cluster（§8.5），位图天然是作品级的。两个作品合并时，被并入的一方成为墓碑，经 `merged_into` 重定向（05 §3.1.2）。`NotSeen` 求值时，先把候选与位图中的 ID 都映射到存活作品，再做差 [判断]；也可以由维护作业在合并时改写位图，二者择一由 05 决定。
- **版本更新**：已见作品新增版本（如正式版到达，是 `corpus.version` 的新行，`work_id` 不变）时，不生成新卡片，而是发"更新通知"（06/07）。
- **删除**：画像可删、注销即删，留存规则按 08（HC-20）。

### 9.7 图：PG 邻接表 ≤2 跳 + 夜间 CSR

引文表的结构以 05 为准：`corpus.citation(citing_work, ref_key, cited_work, sources)`，另有 `cited_work` 与 `ref_key` 两个索引（05 §3.1.5）。其中 `ref_key` 是被引文献的全局键，被引文献不在库内时也有值，因此两篇论文引用同一篇库外文献时仍能算出文献耦合（SR §0-6）。

```sql
-- 设计伪代码 SQL：文献耦合（2 跳：出 → 入），带枢纽剪枝与 IDF 式降权 [判断]
WITH refs AS (
  SELECT ref_key FROM corpus.citation WHERE citing_work = :seed
), deg AS (                                        -- 有界计数：最多数到 5,001 行，便足以识别枢纽
  SELECT r.ref_key,
         (SELECT count(*) FROM (SELECT 1 FROM corpus.citation c
                                 WHERE c.ref_key = r.ref_key LIMIT 5001) t) AS n_citing
  FROM refs r
)
SELECT c2.citing_work AS neighbor, sum(1.0 / ln(2 + d.n_citing)) AS score
FROM deg d JOIN corpus.citation c2 ON c2.ref_key = d.ref_key
WHERE d.n_citing <= 5000                           -- 剪掉施引数超过 5,000 的枢纽文献
  AND c2.citing_work <> :seed
GROUP BY c2.citing_work ORDER BY score DESC LIMIT 50;
```

- **查询约束**：
  - 在线图查询只做 ≤2 跳；
  - 递归 CTE 必带 `CYCLE` 与 `LIMIT`（RT §6.4；PG 14 起支持 `SEARCH`/`CYCLE`，RT §6.1）。
- **枢纽剪枝**：跳过施引数超过 D_max（5,000 [判断]）的中间文献，其余按 1/ln(2+deg) 降权。像通用优化器论文这类被极高频引用的文献，几乎不提供相似性信号，却会让 2 跳结果爆炸。有界计数（`LIMIT 5001`）让识别枢纽不必全扫它的全部施引行。
- **夜间批算**：
  - 用 COPY 导出为 int32 CSR。1,000 万篇、平均约 30 条参考文献时约 3×10⁸ 条边，约 1.2 GB 加偏移数组（RT §6.1 [估算]）。
  - 用 rustworkx（Apache-2.0）或 scipy（BSD-3-Clause，§1.6）计算 PageRank、共被引与耦合的 top-50 近邻。图特征写回 05 的 `corpus.work_feature`，近邻表的表名由 05 定。igraph 为 GPL，不进入分发产物（RT §6.1）。
- **在线读取**：老论文的 EXPAND 直接读近邻表。新论文的耦合在线计算，因为它们只有参考文献，共被引尚未出现（SR §0-6）。
- **体量**：边表体量的估算，以及"边表超过 20 GB 或耦合查询 p95 超预算时，改为每个 work 一行数组 + GIN"的备选形态，见 05 §3.1.5 与 §8.2。备选形态不改变上述查询语义。
- **边来源**：OpenAlex `referenced_works`（快照内）、Crossref 公开参考文献、OpenCitations（CC0）、S2（key）。各源覆盖差异尚未量化（G-15），因此用 05 的 `sources` 位掩码记录每条边的出处（RT §6.4）。
- **图数据库**：不引入独立图数据库（RT §0-4）。出现多跳模式查询需求时，先评估 Apache AGE（同库，Apache-2.0）。

### 9.8 私有层检索（per_user）

- **执行位置**（R2-27、R2-28）：服务端切块、嵌入、建 tsvector 都要读私有全文的明文，而 R2-27 规定 platform 部署的私有 PDF 默认只存设备本地；开启同步时服务端只存端到端密文，不可解密；服务端私有处理默认关闭。因此：
  - platform 部署：服务端不建 `usr.private_chunk`，也没有服务端 `private` 列表。私有全文检索只能在用户设备上执行（配套扩展、本地代理或 PWA 本地索引，后续里程碑），结果在客户端与服务端返回的共享结果合并；服务端看不到私有命中，也不据此改排序；
  - personal 部署且 `deployment.host_is_user_device=true`：可用下述服务端私有索引。personal 部署跑在云主机上时不视为用户本机（R2-28），按 platform 处理。
- **存储**（仅上条第二种情形）：用户私有全文（本人上传，或用户侧取回后选择上传，HC-16）切块后写入 `usr.private_chunk(user_id, asset_id, chunk_no, emb halfvec(256), tsv tsvector)`，启用 RLS。
- **检索方式**：每用户的私有语料小，默认按用户精确扫描，不建共享 ANN。超过阈值时改为按用户分区（pgvector 建议用 list 分区实现租户隔离，RT §5.2）。
- **隔离规则**：
  - 私有结果只作为 `private` 列表，在本人的响应中参与 RRF；
  - 不进共享缓存，不进任何共享统计；
  - 不参与 P(t|q) 与路由（P-02 派生继承最严）。
- **里程碑**：依赖 03/05 的私有资产，以及 08 对 LQ-15（个人 PDF 私有上传）的结论，列为后续里程碑。

### 9.9 索引维护与一致性

- **写路径**：03 流水线的 `index` 段写入 `work_search`、`work_topic`、分面位图（追加）。嵌入由 enrich 段异步写入。
- **夜间对账**：
  1. `corpus.work` 与各索引表之间的双向差集；
  2. 行数与一对多检查；
  3. 位图与 PG 分面计数的抽样比对。

  任一项不一致即告警，并定向重建。这吸取了 v1 D-034 的教训：只做索引自检查不出目标漂移，必须与源表对账。
- **单一入口**：全部检索经检索服务的 API 调用，方言 SQL 只封装在一处，沿用 D-034 决策 6 的查询面单点封装原则。

---

## 10. 五类查询端到端示例

以下五例依次对应用户所说的"查询论文、最新论文、筛选论文、多来源查询、组合查询"。每例按同一顺序展开：输入 → AST → 执行计划 → 触达的索引与源 → 返回形态。示例中的主题后验与覆盖率都是示意数值。§10.6 另给出相关论文与 venue 浏览两个入口。

### 10.1 查询论文（LOOKUP）

**输入 A**：`doi:10.1145/1571941.1572114`。这是 RRF 原论文，RT 曾用它做线上响应头探针（RT §1.3 #20）。
**输入 B**：`"Reciprocal rank fusion outperforms Condorcet and individual rank learning methods"`（引号标题）。

```json
{"intent": "LOOKUP", "where": {"IdRef": {"scheme": "doi", "value": "10.1145/1571941.1572114"}}, "k": 1}
```

**执行计划（输入 A）**：
1. 本地 `corpus.identifier` 主键查找（05 §3.1.2），约 1 ms。命中则经 `version_id` 得到作品（即 cluster），补全卡片字段后返回，不出网。
2. 未命中时走 DOI 替补链（§8.4）：
   - 先查 Crossref `/works/{doi}`，走 single 池（AG §0-1）；
   - 超过 p95 仍未返回时，对冲到 OpenAlex 单实体（不同主机，免费）；
   - 取先成功的结果。
3. 返回后排入 03 的入库流水线（书目事实为 CC0），下次查找即本地命中。

**执行计划（输入 B）**：
1. 本地规范化标题做 pg_trgm 相似度匹配，同时做标题 BM25。
2. top-1 相似度 ≥0.9 且唯一时直接返回。
3. 否则依次走 S2 `/paper/search/match`（key 1 RPS）与 Crossref `query.bibliographic`（列表池，公共池 1/s）。多个候选时以筛选条形式请用户消歧。

**触达**：
- 本地：`corpus.identifier` 的 B-tree 主键、`corpus.version.title_norm` 的三元组 GIN（05 §3.1.2）；
- 远端（仅未命中时）：Crossref、OpenAlex，或 S2。

**返回**：
- 1 个 cluster 卡片，带版本徽标与来源徽标；
- 完整性报告：本地命中时 `planned=[local]`；
- 远端命中时注明来源，按 HC-24 渲染署名。

### 10.2 最新论文（LATEST）

**输入**："cs.LG 和 stat.ML 本周新论文，不要综述"。

```json
{"intent": "LATEST",
 "where": {"And": [{"Facet": {"dim": "cat", "values": ["cs.LG", "stat.ML"]}},
                   {"Not": {"Term": {"field": "title", "text": "survey", "mode": "word"}}}]},
 "window": {"field": "first_public", "last": "P7D"},
 "rank": {"kind": "personal", "fallback": "recency"},
 "scope": {"mode": "local"}}
```

**解析**：
- "综述"由快路径的中英分面词典映射为标题词 `survey`；
- "本周"映射为 7 天时间窗；
- LATEST 意图强制 `scope=local`（P-01）。

**执行计划**：
1. 位图运算：先把 7 个按日分桶的 `first_public` 位图取并集，再与 `cat:cs.LG ∪ cat:stat.ML` 求交，得到 |C|；加上水位之后的尾部补查（§9.4）。作为量级参考，2026-09-21 至 25 这一周，arXiv cs 集的 OAI 记录共 7,083 条，其中 cs.LG 1,861 条（均含替换版与交叉列表，CS §2.6.1）。
2. 用 tsvector GIN 排除标题含 survey 的作品。
3. 与已见位图做差（`NotSeen`，§9.6）；撤稿作品按 06 的可见性规则排除（`status` 分面）。
4. 排序：登录且开启个性化时，按 §8.8 的两段式处理：本人质心预排取前 100 条，交 06 的挂点打分，其余按时间接后；否则按 `first_public` 倒序。
5. 分页，每页 k 条。

**触达**：
- 分面位图（类目、日桶）、tsvector GIN、已见位图；
- **零远端请求**。

**返回**：
- 结果列表与 `data_as_of`，例如"arXiv 数据截至 9-24（周四）20:00 ET 公告批次，已于 22:30 ET 后收割"；
- 背景：arXiv 周日至周四 20:00 ET 公告，OAI 约 22:30 ET 可取（CS §2.6.1）；
- 用户点"刷新"时只触发 §11.6 的按需刷新，公告前没有新数据时如实说明。

### 10.3 筛选论文（SEARCH + 多维过滤）

**输入**："2020 年以来 JFE、RFS、JF 上关于 climate risk 的论文，偏实证，按被引排序"。

```json
{"intent": "SEARCH",
 "where": {"And": [{"Term": {"field": "any", "text": "climate risk", "mode": "phrase"}},
                   {"Facet": {"dim": "venue", "values": [4021, 4388, 4102]}},
                   {"Range": {"dim": "year", "lo": 2020}},
                   {"Facet": {"dim": "type", "values": ["article"]}}]},
 "rank": {"kind": "cites", "tie_break": "relevance", "semantic": {"text": "empirical study", "weight": 0.2}}}
```

**解析**：
- JFE、RFS、JF 经实体链接得到 venue ID，筛选条上展示全部 ISSN。上例中的 ID 为示意。
- "偏实证"没有可靠的分面，作为软条件放进 `rank.semantic`，筛选条标"软条件"。这是 §3.2"硬谓词与软打分分离"的直接体现。
- "climate risk"按 §3.2 本应是软检索文本，但本例按被引排序（非相关性排序），所以编译为硬条件，筛选条显示为"须包含"。解析器把这个两词概念识别为短语，于是写成短语词项；用户可以改为"须包含全部词"或删除。

**执行计划**：
1. 位图运算：venue 三者之并 ∩ year ≥ 2020 ∩ type=article，得到 |C|。三刊五年合计为数千篇量级，因此 |C| ≤ T_EXACT，走精确路径。
2. 在 C 上用 tsvector 短语匹配 "climate risk"。
3. 按被引数排序，被引数取自 05 的 `corpus.work_feature` 或缓存的 OpenAlex 计数。并列时按"BM25 与语义的融合分"决胜。
4. 判断是否联邦：`where` 的顶层合取项把结果限定在三本已登记期刊内。三刊都在基础收割的 Crossref ISSN WatchKey 中，假设完整区间覆盖 2020 年至今（由 `scope_complete_daily` 给出）。短语条件作用于 `any` 字段，涉及摘要，所以还要看第 2 条：Elsevier 在 Crossref 的摘要覆盖为 0（AG §2.6），JFE 的摘要只能来自 OpenAlex 倒排索引等 B 类来源（R2-21 默认纳入索引）。若三刊合计的摘要可检索率 ≥0.9，`scope_complete(q)` 为真，不联邦；否则回到 cov_local 与 n_local_T 的判断（§6.3）。范围完整性检查先于素描执行：它成立时，不会因为 Finance subfield 的素描本地位偏低（例如 0.7）而联邦。

**触达**：
- 分面位图（venue、year、type）、tsvector GIN、图特征表；
- 范围完整时零远端请求。

**返回**：
- 结果列表；
- 分面计数（按年、按期刊），由位图直接得出，可供继续筛选；
- 注记"被引数来源：OpenAlex；各源口径不一"（AG §3-19）。

### 10.4 多来源查询（SEARCH，联邦）

**输入**："psilocybin treatment-resistant depression randomized controlled trial"。

```json
{"intent": "SEARCH",
 "where": {"Facet": {"dim": "pubtype", "values": ["RCT"]}},
 "rank": {"kind": "relevance", "text": "psilocybin treatment-resistant depression"},
 "accept": "lenient"}
```

**解析**：快路径的分面词典把 "randomized controlled trial" 识别为研究类型分面 `pubtype`（硬谓词），并生成筛选条；其余裸词成为软检索文本（§3.2），筛选条标"软条件"。用户若要求结果必须含 psilocybin，可把它转为"须包含"。

**路由**：
- 主题后验集中在精神病学、药理学等 subfield（示意）。假设平台用户以 CS 与经管为主，这些节点的本地覆盖只有约 0.35（示意），因此联邦。
- 硬约束过滤后的候选为 Europe PMC、OpenAlex search 与 S2 search（相关性检索）：
  - Europe PMC 支持 Lucene 语法与 `FIRST_PDATE` 等字段，可作可下推的联邦后端（LS §3-10、AG §2.3.2）。研究类型按 `PUB_TYPE` 字段下推，这个字段名调研未核 ⚠（LS §2.3.3 只列出 `/fields` 中 143 个字段里的 32 个），实现期对照 `/fields` 核验；核验不通过时该文字替换为 true，φ 降为 0，精度改由残差保证（§7.4）。它还受 Crawl-delay 10 秒约束（§8.4）；
  - PubMed E-utilities 在 NCBI 书面确认前不启用（R2-13，§6.3 第 2 条），不在候选中；
  - OpenAlex search 按搜索计价；
  - S2 bulk 不在候选中：它不按相关性排序，软文本不下推给它，放宽后只剩研究类型过滤。若 RCT 映射不到 S2 的 `publicationTypes` 取值（取值表调研未核 ⚠），该文字替换为 true，子查询无界，按 §6.3 第 5 条剔除；即便能映射，也须取完全部匹配，请求数远超交互预算，按 §6.6 的单项超预算规则在选源前剔除。
- 贪心选源（示意）：EPMC 单独增益最大；OpenAlex 能补足非 MEDLINE 期刊；S2 与两者重叠高，在预算内的边际增益低于阈值，事后剪掉。最终选定 {EPMC, OpenAlex}。NCBI 确认后 PubMed 进入候选，但它与 EPMC 重叠极高，EPMC 之后的边际增益同样很低。

**放宽**：

| 端点 | P_s 与软文本 | φ |
|---|---|---|
| EPMC | `PUB_TYPE` 原生下推（字段名待核 ⚠）；软检索文本作为 Lucene 相关性查询下推 | 1（唯一的硬文字已下推；字段核验不通过时为 0） |
| OpenAlex | 研究类型不受支持，替换为 true（健全）；软检索文本走 `search=`，结果按相关性排序，不算无界（§7.2） | 0（硬文字未下推，结果精度全靠残差） |

对 OpenAlex 独有的记录，残差中的研究类型会因缺少字段而为 U。lenient 模式下这些记录保留，标"未验证：试验类型"，排在 T 结果之后（§3.5）。

**执行**：
1. 按子截止时间并行 fan-out。EPMC 的令牌空闲时，它通常先返回；若出站网关预计排队（Crawl-delay 10 秒，全平台共用）会超过子截止，它以 `budget_exhausted` 快速失败，完整性报告标注缺源，OpenAlex 的结果照常返回（§8.2、§13.1）。
2. 规范化：用 PMID 或 DOI 解析，多数不在本地，成为临时候选，按强标识符成组。
3. 各列表内先折叠，然后依次做残差、RRF、CE 重排，流式输出。
4. 查询即入库：许可允许共享的记录排入 03 流水线。NLM 来源须按 HC-24 带致谢与时效说明，摘要属 B 类，按 §9.1 处理。

**返回**：
- 来源徽标（EPMC、OpenAlex）；
- 标注"未验证"的结果；
- 完整性报告：计划源与成功源、预计覆盖、截断情况；
- NLM 署名。

### 10.5 组合查询（频道集合运算 + 多维过滤 + 语义 + 个人谓词）

**输入**（高级语法）：`(@llm-agents ∪ @rl-theory) − @surveys  oa:yes  window:30d  like:doi:<种子DOI>  is:unseen`。

```json
{"intent": "SIMILAR",
 "where": {"And": [{"Or": [{"ChannelRef": {"id": "<uuid-A>", "ast_hash": "<h-A>"}},
                           {"ChannelRef": {"id": "<uuid-B>", "ast_hash": "<h-B>"}}]},
                   {"Not": {"ChannelRef": {"id": "<uuid-S>", "ast_hash": "<h-S>"}}},
                   {"Facet": {"dim": "oa", "values": ["gold", "green", "hybrid", "bronze"]}},
                   {"Personal": {"kind": "unseen"}}]},
 "window": {"field": "first_public", "last": "P30D"},
 "rank": {"kind": "semantic", "seed": {"doi": "<种子DOI>"}},
 "scope": {"mode": "local"}}
```

**规则**：含 `ChannelRef` 的查询默认 `scope=local`。频道本身就是定义在本地语料上的视图（P-01），用户可以显式改为 `force`。

**执行计划**：
1. 内联三个频道，在规范 AST 中记录各自当时的 `ast_hash`。化为 NNF，`Not(@surveys)` 的否定下推到其原子。
2. 位图：30 天窗口 ∩ OA 分面，得到 C₀。
3. 用 Percolator 同一套"频道编译匹配器"（§12.3）在 C₀ 上求值，得到 C = (A ∪ B) − S。
   - 另有一条更快的路径：直接取 FeedInbox 中这些频道近 30 天的命中。
   - 默认仍用精确求值：FeedInbox 只保存推送上限内的频道命中，且保留期有限（§12.6），可能不全。
4. 与已见位图做差，得到 C′。|C′| 通常 ≤ T_EXACT，直接与种子嵌入算精确余弦并排序。
5. 可选调用个性化挂点。

**触达**：
- 分面位图、tsvector GIN（频道中的词项）、稠密向量（种子）、已见位图；
- 零远端请求。

**返回**：结果列表，每条带理由码，例如"来自频道 llm-agents；与种子论文的相似度 0.78"。理由只引用本人的数据，与 HC-13、T16 一致。

### 10.6 其他入口：相关论文与 venue 浏览（FR-43、FR-44）

**相关论文（EXPAND，FR-43）**：用户在卡片上点"从这篇扩展"。

```json
{"intent": "EXPAND",
 "where": {"Or": [{"Rel": {"kind": "coupled_with", "ref": "<work>"}},
                  {"Rel": {"kind": "co_cited_with", "ref": "<work>"}},
                  {"Rel": {"kind": "cites", "ref": "<work>"}},
                  {"Rel": {"kind": "cited_by", "ref": "<work>"}}]},
 "rank": {"kind": "graph"}, "k": 30}
```

- **本地图 ≤2 跳**（§9.7）：老论文读夜间近邻表，新论文在线计算文献耦合。所以尚无被引的新论文也能得到相关论文。
- **关联理由**：每条结果带理由，例如"共享 7 篇参考文献""被 3 篇论文共同引用"。
- **联邦补充**：本地图稀疏时（例如库外的老文献），按 §8.4 的引文扩展替补链联邦：OpenAlex `cites:` → OpenCitations → S2 citations。

**venue 浏览（FR-44）**：按期刊卷期或会议届次浏览论文目录。

```json
{"intent": "SEARCH", "where": {"Facet": {"dim": "venue", "values": ["<venue-id>"]}},
 "window": {"field": "published", "from": "2024-01-01"}, "rank": {"kind": "issue"}}
```

- **执行**：venue 分面位图配合 `issue` 排序（卷、期倒序，页码正序）。卷期元数据由 03 按 ISSN 枚举提供，是 v1 FR-02、FR-04 的 v2 形态。
- **关注 venue**：经 02 的 `/me/follows` 资源写入 05 的 `usr.follow(target_kind='venue')`，同时产生 06 定义的 `follow` / `unfollow` 事件（R2-47）。关注可以一键转成只含 `Facet(venue)` 的频道；该频道编译为此 venue 的 latest WatchKey（§11.1）。关注作者按 §11.1 的细粒度键规则处理（R2-19）。

---

## 11. 新鲜度调度

### 11.1 WatchKey 的来源与编译

- **定义**：WatchKey = (endpoint_id, 规范化的下推参数)。例如：
  - (arxiv.oai, set=cs:cs:LG)；
  - (crossref.journals_works, issn_l=…)；
  - (openalex.works_filter, topics.id=…, 窗口)；
  - (epmc.search, MeSH=…)。

  同一个键只收割一次，所有引用它的频道与用户共享结果（RT §8.3、SI-31）。

WatchKey 有两个来源：

1. **基础收割（Base Harvest）**：与具体频道无关，覆盖全体用户兴趣并集（B-04）。兴趣并集的节点集合取自 05 的 `ops.corpus_scope`，它只含计数。基础收割包括：
   - 用户关注到的 arXiv 类目级 set（NS §2.3.5、CS §3-6）；
   - 全部已登记 venue 的 latest 通道。期刊走 Crossref `/journals/{issn}/works`（single 池，AG §0-1）；会议按新鲜度阶梯选通道；
   - 生命科学关注区域的 EPMC 增量，加 Crossref 与 PMC 允许的通道；PubMed 增量在 NCBI 书面确认后才加入（R2-13）。bioRxiv、medRxiv、PsyArXiv 以 Crossref 为首选、原生 API 为补充（R2-13）。
2. **频道编译**：对频道谓词中的正锚点逐类处理：
   - **venue 或系列锚点**：取 `served_by(role=latest)`，按新鲜度阶梯选最早的合规通道。阶梯为 L0 arXiv 或作者预发布 → L1 会议 OA 平台 → L2 DOI → L3 聚合层（CS §2.6.5、SI-14）。OpenReview 在书面确认前停用平台侧共享收割（R2-20），ICLR、TMLR、COLM 等走 arXiv 版本加 DROPS dblp 快照，外链到 OpenReview forum；用户本人的 OpenReview token 只在用户侧供本人查询，不用于共享收割。
   - **arXiv 类目锚点**：对应的 OAI 类目级 set。
   - **主题锚点**（subfield、topic，或 MeSH、JEL 叶子）：先用 `recent90` 素描的**本地位**估计该节点近期新作已在本地的比例 cov_recent(local, t)（本地位每日刷新，§5.3）。不能用端点位：端点位表示"该作品在端点 s 里"，而基础收割的 WatchKey 只拉了端点的一部分（例如 Crossref 只拉已登记 ISSN），所以端点位会高估已收割的覆盖。若 cov_recent(local, t) ≥ 0.9 [判断]，不加键；否则复用 §6.6 的预算覆盖算法，只把成本换成"每日轮询成本"、目标换成"节点 t 的近期新作覆盖"，补选端点并生成 WatchKey。`recent90` 素描只建到 subfield 级，topic 与叶子节点经上卷与 `maps_to` 取其 subfield 的素描。这就是 TSRG 的第二种用途（§5.7-2）。
   - **作者与引文邻域锚点**（`au:`、`Rel(cites|cited_by|coupled_with …)`，以及关注作者）：这是细粒度键，单个用户就能让它出现在 ops 域与上游请求里，暴露个人研究兴趣。按 R2-19，只有至少 `k_cf` 个不同用户共有同一个键时才建平台 WatchKey；不足时不建键，该用户的这类频道依赖基础收割，加上本人触发的按需查询（交互道，受 §13.5 的用户配额约束）。R2-19 的原文针对"由私有文献库派生"的键，本文把频道与关注产生的同类键一并纳入 [判断]。计数方式：`usr.channel_watch` 以外键指向 `ops.watch_key`，未达门槛的键不能先在 ops 建行，否则门槛形同虚设。所以未达门槛的细粒度键只以带密钥的哈希存在本人的 usr 行里；调度器按哈希统计不同 `user_id` 数，达到 `k_cf` 才在 `ops.watch_key` 建行并补建映射 [判断]。存放该哈希的列须由 05 增补（§20 第 32 项）。
   - **只有关键词的频道**：关键词无法廉价地按键收割，不生成专用键，依赖基础收割。保存频道时，筛选条提示"该频道依赖通用收割，覆盖可能不全" [判断]。

**策略闸**：WatchKey 只分配给该操作策略模式为 `background` 的端点（03 §6.2）。端点降为 `on_demand`（带 `needs_confirmation`、ToS 宽限期满未复核、`review_overdue` 宽限期满，R2-15、R2-16）或更低时，调度器暂停其 WatchKey，按 SourceSpec 的替补链改派到其他端点，水位保留；恢复 `background` 后从水位续拉。

**引用计数**：
- 引用关系存于 05 的 `usr.channel_watch(user_id, channel_id, watch_key_id)`（RLS）。映射本身属于私有数据。
- 调度器以 05 定义的 `pc_sys_scheduler` 角色只读该表，把它聚合成 `ops.watch_key` 的 `refcount` 与 `weight`。ops 域不存用户标识（P-02）。
- `weight` = 各引用频道的活跃度权重之和（主人 7 天内活跃计 1，否则按指数衰减 [判断]），再加上基础收割的权重。
- `refcount` 降为 0 且不属于基础收割的键，经 14 天宽限期 [判断] 后退役。水位保留，以便日后复用。

WatchKey 表以 05 的 `ops.watch_key` 为准（05 §3.4）：键为 `(source_id, endpoint, query_hash)`，另有 `pushdown_query`、`refcount`、`weight`、λ 的 Gamma 参数、`calendar`、`watermark`、`cost_per_poll`、`next_due_at`、`last_poll_at`、`status`。本文对它有三点约定：
- `calendar` 非空即日历型，为空即连续型；
- 重叠窗口记在 `watermark` 中，与 v1 的 DateCursor、IdSetDiff 一致；
- 该表的 `query_hash` 是规范化**下推参数**的哈希，与本文 §3.6 的用户查询 `query_hash` 不是同一个量，二者也不得互相连接（后者只作本人键）。

**职责划分**：按 R2-34，WatchKey 编译算法（本节）与新鲜度调度算法（§11.2–§11.6）由 04 定义，由 02 的 harvest scheduler（P6）执行，03 的 connector 消费并负责收割执行与水位推进。02 组件表把"WatchKey 编译"记在 03 名下的表述随之由 02 修正。

### 11.2 日历型与连续型

**日历型**：
- **arXiv**：周日至周四 20:00 ET 公告，OAI 约 22:30 ET 可取，周五、周六不公告，2026 年有 9 个节假日（CS §2.6.1）。每个公告日在 22:30 ET 后轮询一次。若批次条数显著低于日历模型的预期，在 +1 h 与 +3 h 各补一次 [判断]。限流检测同时看 429 与伪 200 的 "Rate exceeded."（CS §3-6、SI-05）。
- **有固定出刊节奏的期刊**：可在 VenueSpec 中声明日历（03）。未声明的一律按连续型处理。

**连续型**：
- Crossref：DOI 注册持续发生；
- EPMC：按 `FIRST_IDATE`；
- PubMed：按 EDAT（NCBI 书面确认后才启用，R2-13）；
- bioRxiv/medRxiv/PsyArXiv：以 Crossref（按 member 或前缀）为首选通道，原生 API 为补充（R2-13），并监控 bioRxiv `/details` 返回 200 空体的漂移（LS §2.2.1、§3-11，SI-06）；
- OpenAlex：免费档没有 created/updated 增量过滤，只能按 `publication_date` 窗口，靠季度快照对账（AG §3-3）；
- feed：一般 feed 只作新鲜度信号，到达后触发对应 WatchKey 提前轮询（SI-13）；按 R2-17 在 SourceSpec 中登记、robots 允许、ToS 无禁止的官方 WP feed（ECB、BIS、JMLR 等）可作元数据主通道，按连续型调度，用 `IdSetDiff` 水位。

**时段约束**：NCBI 批量作业（确认后）安排在美东非高峰时段（CP §2.4、LS §3-5）。调度器按源读取可用时段。

### 11.3 Gamma-Poisson 估计 λ

- **模型**：WatchKey k 的新条目到达近似为速率 λ_k（篇/天）的 Poisson 过程。学术源关心的是新条目流，而不是页面变化（RT §8.2）。
- **先验**：取自 TSRG：λ₀ = λ(s, t)·sel_k，其中 sel_k 是该键的下推选择率，例如某 ISSN 在节点中的份额。伪观测 n₀ = 7 天 [判断]，即 α₀ = λ₀·n₀，β₀ = n₀。
- **更新**：每次轮询观测到 Δt 天内 n 个新条目，α ← γα + n，β ← γβ + Δt，γ = 2^(−Δt/h)，h = 30 天 [判断]。
- **使用**：后验均值 λ̂ = α/β，方差 α/β²。对高权重键可以改用上分位数 λ̂₉₀ 做保守分配 [判断]。连续型源可选学习"按星期分桶"的乘子 [判断]。

这里观测到的是**计数**，而不是"两次访问间是否变化"的二值结果，Gamma-Poisson 的计数更新因此直接适用。不需要 Cho 与 Garcia-Molina 针对二值变化的修正估计量；该公式在 RT 中也标为 ⚠ 未核验（RT §8.1）。

### 11.4 礼貌约束下的注水分配（推导与伪代码）

**目标**：最小化单位时间内的加权期望发现延迟。

**延迟模型**：Poisson 到达、周期轮询时，一个条目在两次轮询之间均匀到达，期望等待时间为 I_k/2 = 1/(2f_k)，其中 f_k 为轮询频率。源侧自身的滞后与 f 无关。

**成本模型**：每次轮询至少 1 个请求，加上重叠窗口带来的重复页，c_k = 1 + ⌈λ_k·overlap_k / page_size⌉。新条目本身必须取回，其页数约为 Σ_k λ_k / page_size，与 f 无关，不进入权衡，但要先从预算里扣掉。

```text
min_f   Σ_k  w_k · λ_k / (2 f_k)
s.t.    Σ_k  c_k · f_k ≤ B_s          （源 s 收割道的每日预算，已扣除日历型键的固定消耗与新条目本身的取回页数）
        f_min ≤ f_k ≤ f_max,k
拉格朗日：∂/∂f_k [ w_k λ_k /(2 f_k) + μ c_k f_k ] = 0   ⇒   f_k* = √( w_k λ_k / (2 μ c_k) )
```

**解的形态**：f_k* ∝ √(w·λ/c)，对 λ 是**次线性**的。这与 Cho & Garcia-Molina 的定性结论一致：预算有限时，不应把轮询都压在最活跃的源上，按变化率成比例刷新并非最优（RT §8.1）。

本推导的目标函数（新条目的发现延迟）不同于网页新鲜度，是标准拉格朗日推导 [判断]，不是引自某篇文献。严格同时考虑主机级礼貌、非均匀重要性与爬虫请求上限的最优调度见 Kolobov 等（SIGIR 2019）。近线性时间的精确求解见 Azar 等（PNAS 2018）。二者均见 RT §8.1。

```python
# 设计伪代码
def water_fill(keys, budget, eps=1e-6):
    def freq(mu):
        return {k: clip(sqrt(k.w * k.lam / (2 * mu * k.c)), k.f_min, k.f_max) for k in keys}
    lo, hi = 1e-12, 1e12
    for _ in range(100):                                     # 花费关于 μ 单调递减，二分求 μ
        mu = sqrt(lo * hi)
        spend = sum(k.c * f for k, f in freq(mu).items())
        lo, hi = (mu, hi) if spend > budget else (lo, mu)
        if abs(spend - budget) <= eps * budget:
            break
    return freq(hi)                                          # 取可行侧

def plan_day(source):
    keys = [k for k in source.keys if k.policy_mode == "background"]   # 策略闸（§11.1）：其余键暂停，改走替补链
    cal = [k for k in keys if k.kind == "calendar"]
    con = [k for k in keys if k.kind == "continuous"]
    B = (source.harvest_lane_budget_per_day - fixed_cost(cal)          # 日历型先占用固定预算
         - sum(ceil(k.lam / k.page_size) for k in con))                # 新条目本身的取回页数，与 f 无关
    con = shed_until_feasible(con, B)                                  # 预算不可行时按 w·λ 从低到高降级或暂停并告警（见下）
    f = water_fill(con, B)
    return schedule(cal_slots(cal) + grid(f, step="15min", jitter=True, windows=source.allowed_windows))
```

- **频率上下限**：
  - f_max 取源的合理粒度，例如 Crossref 单键不高于每 15 分钟一次 [判断]；
  - f_min 至少每周一次，保证水位落在游标与重叠窗口的有效期内。
- **预算不可行**：若 Σ_k c_k · f_min > B_s，即便全部取下限也超预算，二分会停在 f_min 上而实际超支。`plan_day` 先做此检查：不可行时按 w_k·λ_k 从低到高把键降为"随基础收割顺带覆盖"或暂停，直到可行，并告警。这种情况说明该源的键过多或预算过紧，需要人工调整（例如合并键、申请更高额度）。水位保证暂停的键恢复后不漏。
- **会话连续性**：Zenodo 的 resumptionToken 2 分钟过期，同一次收割会话必须连续续拉（AG §3-3）。
- **计算量**：K 个键二分约 60–100 轮，每轮 O(K)。每天全量重算的代价可忽略（RT §8.1：Azar 等的方法可对数万键每日重算）。

### 11.5 正确性与调度分离

- **分工**：调度器只决定"何时拉"，"不漏不重"由水位、重叠窗口与标识符去重保证（v1 design/09 §5；RT §8.3）。
- **水位策略**：沿用 v1 的三种：
  - `DateCursor`：Crossref `from-created-date` 加重叠窗口；
  - `IdSetDiff`：NBER RSS；
  - OAI 的 from/until：arXiv 按日粒度，加 1 天重叠。
- **Crossref 的主次**：以 `from-created-date` 加重叠窗口为主。`from-index-date` 会把结果放大约 100 倍，只作补漏，并做标识符去重（简报 §6.1-2、SI-13）。
- **水位归属**：水位属于 WatchKey，不属于频道。新建频道不会触发重复收割。
- **新频道回看**：频道创建或修改时，立即在本地语料的近期窗口（默认 30 天 [判断]）上求值，写入 FeedInbox，保证"新频道立即有内容"。若频道所在节点的本地覆盖偏低，另做一次有预算上限的回填收割，走收割道或 enrich 道；回填只用 venue、类目、主题这类粗粒度键，作者与引文邻域键不因单个频道触发平台回填（R2-19，§11.1）。

### 11.6 按需刷新

用户在 LATEST 视图点"刷新"时，对支撑该视图的 WatchKey：
- 若距上次轮询已超过其最小间隔（默认 1 h [判断]），把该键提前到下一个调度槽，仍受预算与日历约束；
- 日历型源在下一次公告前不会有新数据，此时不发请求，只说明原因，例如 arXiv 在周五、周六不公告。

每个键有全局的最小间隔，与发起刷新的用户数无关。因此用户数增加不会放大上游请求（P-04、NFR-14）。

---

## 12. Percolator

### 12.1 输入与输出

- **两档执行节奏**：三路候选生成的算法都由本文定义，执行分两档：
  - **近线档**（02 的 P11 Percolator）：只做频道谓词这一路，微批为每 10 分钟或每 500 篇 [判断]，目标是入库到 FeedInbox p95 ≤30 min。触发源是出箱主题 `corpus.change`（R2-07；载荷见 03 §10.7），02 §2.8 所写的 `work.enriched` 按 R2-07 并入该主题。该事件由 identify 段发出，早于 index 段完成，所以近线档按 `work_search.index_seq` 水位取批：只处理 index 段已完成、且在出箱中有对应变更的作品（就绪条件见下）；
  - **日批档**（06 的反向推送规划器，02 P4 的夜间作业）：节点倒排与质心点积两路，按当日全部新作品一次生成候选，交 06 分配。
  - 原稿把后两路也放进 10 分钟微批，并在同一作业内交给 06 分配。06 的分配受"每用户日预算 + 资格集合的曝光下限"约束（R2-41；06 §11.3 的贪心与最小费用流），这是一个以当日全部供给为输入的整体问题。切成 144 个微批逐批贪心，当天早到的论文会先耗尽预算，这是在线 b-matching 的短视问题；要避免它，得另做预算节奏控制。02 P11 与 06 §8 都已把兴趣反向推送放在夜间，本文与之对齐（§19-14）。
- **输入**（R2-35）：
  - `reason=new` 的新作品；
  - 已有作品新增了版本（`version_ids` 非空），或匹配字段发生变更（`changed_fields` 与频道谓词、节点标注、嵌入所用字段有交集，如标题、摘要、`topic_ids`、`venue_ids`、类型、OA、撤稿状态）；
  - `merge` 只做 FeedInbox 与已见集合的墓碑重定向，不产生推送；`retraction` 不产生推送，由 06 的可见性过滤处理；`split` 产生的作品按"已有作品变更"处理 [判断]。

  已有作品重新匹配时有两条护栏，都不需要读收件箱：
  1. 只有 `first_public` 在近 30 天内（与 §11.5 的新频道回看窗口一致 [判断]）的作品才写入 FeedInbox；更早的作品不推送，但在频道列表视图中照常可见（§12.6）。这样摘要补齐或主题重标不会把多年前的旧论文当作新论文推给用户。
  2. 已经推送过的 (用户, 作品)：保留期（14 天）内，主键 `(user_id, work_id)` 使重复插入成为空操作；保留期外即使重新写入，Deck 组装时的已见过滤（`NotSeen`，§9.6）也会挡住它。给看过该作品的用户发"新版本"更新通知，由 06 按已见集合与文献库生成（§9.6），不由 Percolator 判断。
- **就绪条件**：`index` 段完成，`work_topic` 已写入（节点倒排需要），嵌入已写入（质心点积需要）。近线档只需要前两项与频道谓词所需字段（tsvector、分面）；嵌入由 enrich 异步写入（§9.9），近线档不等它。每篇作品带：
  - `work_id`（05 中即 cluster）；
  - 节点标注 T(w)，来自 `work_topic`；
  - 嵌入 e_w（日批档；推荐空间的 256 维向量，与 `usr.user_vector` 同一模型）；
  - 谓词求值所需的字段：tsvector、分面。
- **输出一：频道命中，直接写入 FeedInbox**（近线档）。
  - 在 05 的 `usr.feed_inbox` 中写一行：`push_reason='channel_hit'`，带 `channel_id`，`score` 为空，`expires_at` = 创建后 14 天（05 §3.2.5；列名与取值以 06 §11.3 为准）。
  - 频道命中不占 06 的软推送预算，但受频道推送上限约束（§12.6）。
- **输出二：候选读者对，交给 06 分配**（日批档）。
  - 节点倒排与质心点积产出候选对 (u, w, 分量分)，每篇取前 L = 200 个读者（06 §11.3）。
  - 06 按 ValueModel 计算边权，在每用户软推送预算、每篇上限与资格集合的曝光下限（R2-41：只对资格集合生效，受 ≤5% 期望曝光的全局预算约束）下做贪心或最小费用流分配，再写入 FeedInbox（06 §11.3）。
  - 候选生成作为 04 提供的库函数，在 06 的日批作业进程内调用，交接用内存结构，不另落表 [判断]。
  - 已有 `channel_hit` 行的 (u, w) 对在分配前剔除：频道命中已送达，不再占用软推送预算。写入角色对 `usr.feed_inbox` 没有 SELECT 权限，所以剔除不靠读收件箱：日批作业以同一角色对当日作品重放频道谓词求值（纯函数，与近线档结果相同，§12.5），得到当日的频道命中对。否则分配器会把预算花在一条会被主键静默丢弃的插入上。
- **写入语义**（以 05 §3.2.5 为准）：
  - 写入者 `pc_sys_percolator` 只有 INSERT、没有 SELECT。表主键为 `(user_id, work_id)`；写入语句为 `INSERT … ON CONFLICT DO NOTHING`，**不写冲突目标**，重复行由主键静默跳过，写入端无需读权限（⚠ 待 05 的 T-RLS-7 实测）。若实测不成立，05 退回"只追加、读取时 `DISTINCT ON (work_id)` 去重"的形态，两种形态下读取结果相同。
  - 主键使"先写者决定 `push_reason`"。同一作品若既命中频道又被日批分配，近线档早于日批写入，归因为 `channel_hit`；日批的剔除规则（上一条）保证分配器不会把预算花在这类对上。
  - 05 的 `work_id` 就是 cluster，去重已是作品级。04 另要求：读取时跟随合并墓碑（`merged_into`）重定向，避免合并前后的两个 ID 各占一条（§20）。
- **更新通知**：已命中的 cluster 新增版本（如正式版到达）时，不产生新条目；更新通知由 06 按已见集合与文献库生成（§9.6、上文护栏 2）。

### 12.2 三路匹配

1. **节点倒排**（对应 SimClusters 的"社区倒排"，社区换成 TSRG 节点，SR §2.10.2）：
   - 对 n ∈ T(w)，只取 subfield、topic 与原生叶子层级。domain 与 field 太宽，不参与。
   - 在 05 的 `usr.interest_node_weight` 上，按 (node_id, 权重降序) 取长期或短期权重 ≥ θ_node 的用户，θ_node = 0.05 [判断]。
   - 候选分 score_A = Σ_n score(w, n) · w(u, n)。
2. **质心点积**（日批档）：
   - 当日新作品矩阵 E（N × 256）乘以全体用户质心矩阵 Cᵀ（256 × U·K）。质心取自 05 的 `usr.user_vector`，每用户 K ≤ 5 个（SR §2.10.2）。
   - 每个用户保留超过阈值的高分项。
   - 节点倒排对每个节点只取权重最高的 2,000 个用户（§12.4），热门节点会截掉一部分用户；质心点积对全体用户质心做稠密矩阵乘，不截断，所以这些用户仍由本路覆盖。
3. **频道谓词**（近线档）：经锚点倒排（§12.3）得到候选 (频道, 子句)，再对子句做完整求值。默认 strict 三值（§3.5）。
   - 子句含带阈值的硬语义原子（`SemAtom`）时需要作品嵌入。嵌入未就绪的作品，其这类子句延到嵌入写入后的下一个微批再求值，其余子句照常。
   - 频道语义原子的向量随频道编译结果缓存在进程内（按内联后的规范哈希，§12.3），与本批作品嵌入做一次小矩阵乘。

**前置过滤**：命中用户屏蔽规则的候选直接丢弃。屏蔽规则见 05 的 `usr.mute_rule`，由强负反馈在事件接入事务内同步写入（R2-33），Percolator 只读。R2-33 给 `block.target_type` 增加了 `source`：作品的来源溯源只含被屏蔽来源时丢弃，另有未屏蔽来源时保留（与 FR-28 的口径一致，§15.3）。

**延迟谓词**：`Personal` 类原子（未读、不在库中）会随时间变化，Percolator 不求值。它们留到 Deck 组装（06）或视图读取时再求。

**职责边界**：04 定义三路候选生成的算法；近线档（P11）负责频道谓词求值与频道命中的写入，节点与质心两路在 06 的日批作业内以库函数形式执行。节点与质心候选的打分（ValueModel）与分配，即每用户日预算与资格集合曝光下限（R2-41）约束下的贪心或最小费用流，属于 06（简报 §6.4-5 ②；06 §11.3）。

### 12.3 锚点倒排

1. **编译为 DNF**：把频道谓词（NNF）编译成 DNF 子句，上限 16 个 [判断]。超限时对子句做最小一般化，得到健全的超集，再对命中的候选做完整求值。编译在 Percolator 进程内完成：05 只向 Percolator 授予 `usr.channel` 的 `user_id`、`channel_id`、`ast`、`status` 四列，编译结果缓存在内存中，不落库。缓存键是**内联之后**的规范 AST 哈希，包含全部被引频道当前的 `ast_hash`（§3.3 的 `ChannelRef`）。若只用组合频道自身的 `ast_hash`，被引频道修改后组合频道的键不变，会一直用旧谓词匹配。被引频道修改时，引用它的组合频道随之重编译，并按 §11.5 做回看。
2. **选锚点**：每个子句选一个锚点文字——带索引键、预期频率最低的正文字。例如 `cat:cs.LG`、`venue:JFE`、`node:subfield`、短语中最稀有的词。
   - **锚点必须满足"文字为真 ⇒ 作品的键集合含该键"**，否则倒排会漏配。合格的有：分面、节点、`analyzed` 词项（短语或邻近取其中任一词，通常取最稀有者）。
   - `substring_ci` 词项、`Regex` 与前缀词项不合格。例如 v1 兼容的子串 "agent" 会命中含 "reagent" 的标题，而该标题分析后的词键里没有 "agent"；以它为锚就会漏掉这条命中，破坏 v1 等价（AC-V2.2）。
   - 含这类文字的子句改选同一子句中的其他合格正文字（v1 迁移来的频道都带 arXiv 类目或 venue 分面，§3.8）；没有合格者则放入残余表。
   - **lenient 频道的缺失字段**：用户开启"包含未能确认条件的论文"后，频道按 Kleene 语义接受 U（§3.5）。锚点所在字段缺失时，该文字为 U，子句可以是 U 而被接受，但作品的键集合里没有这个锚点，倒排会漏掉它。例如锚点取摘要词 "agentic"，而某篇心理学论文没有摘要。对策是给键集合加缺失伪键：作品缺失字段 f 时，keys(w) 另含 `missing:f`；lenient 频道的每个子句除挂在锚点键下，还挂在 `missing:field(锚点)` 下。strict 与 closed_world 频道只接受 T，缺失字段的锚点文字不可能为 T，不需要伪键。
3. **倒排与残余表**：
   - 倒排为"锚点键 → [(channel_id, clause_id)]"；
   - 没有正向可索引文字的子句（只有否定、区间或语义），放入"残余表"，对每篇新作品都求值；
   - 保存频道时提示"宽频道"，并限制每用户的此类频道数 [判断]。
4. **逐篇求值**：作品的键集合 keys(w) = 分面 ∪ 节点 ∪ 标题与可索引摘要中经分析的词 ∪ 缺失伪键 `missing:f`。查倒排得到候选子句，对候选子句做完整求值，任一子句被接受（strict 为 T，lenient 为 T 或 U）即命中该频道。

这是发布/订阅中的"布尔表达式索引"思路的简化版。Whang 等（PVLDB 2(1):37–48, 2009）研究如何索引 DNF/CNF 布尔表达式，以便对给定的属性赋值快速找出全部为真的表达式，应用于广告定向与 pub/sub（一手来源，2026-09-27 查阅）。T2 规模可以评估 OpenSearch 的 percolate 查询（Apache-2.0，RT §8.3、§13-11）。

### 12.4 复杂度与批处理 [估算]

| 部分 | 量级（1 万用户、每用户 ≤5 质心、每日 3 万新作、5 万个频道） | 说明 |
|---|---|---|
| 质心点积（日批档） | 每日 3×10⁴ × 5×10⁴ × 256 ≈ 3.8×10¹¹ 次乘加，CPU BLAS 为秒到分钟级 | 与 SR §2.10.2、02 §2.11 的估算同量级："R0/R1 阶段用批量矩阵乘即可，不必 ANN"。按每块 1,000 篇分块计算并在块内取每篇前 L 个读者，每块得分矩阵 1,000 × 5×10⁴ float32 约 200 MB [估算]；整日一次性物化约 6 GB，不可取 |
| 节点倒排 | Σ_{n∈T(w)} \|U_n\|。每节点只取权重最高的 2,000 个用户 [判断]，每篇 ≤2×10⁴ 对 | 在 PG 中对 `work_topic × interest_node_weight` 做连接，或用内存 CSR 向量化 |
| 锚点倒排 | 1.5×10⁵ 个子句；每篇查询约 200–400 个键，得到 10–100 个候选子句 | 每日约 10⁷ 次哈希查找，可忽略 |
| FeedInbox 写入 | 每用户每日 ≤ 06 的软推送预算（06 §11.3 取 50 ⚠）+ 各频道的推送上限之和（按平均 100 计 [判断]），合计 ≤1.5×10⁶ 行/日；保留 14 天（05 默认）约 2.1×10⁷ 行，按约 80 B/行计约 1.7 GB | 过期行由 05 的保留作业清理（05 §3.2.5） |
| 端到端滞后 | 频道命中：微批周期（10 min）+ 主题标注延迟；含硬语义原子的子句另加嵌入延迟。兴趣反向推送：日批，次日可见 | 目标：频道命中从入库到 FeedInbox 的 p95 ≤30 min（§1.1 对 NFR-12 的细化；02 AC-V4.14）。兴趣反向推送按 06 §8 的夜间批，次日 06:00 前完成 |

**扩展上限**：频道数超过 10⁵，或批处理滞后越过目标时，评估 OpenSearch percolate（§14.4）。RT 已把"订阅数达 10⁵ 级时的 percolate 成本"列为未知风险（RT §13-11；综合 R-12）。

### 12.5 访问控制、幂等与不遗漏

- **访问控制**（以 05 §4 为准）：
  - Percolator 以 `pc_sys_percolator` 角色运行；
  - 近线档只需读 `usr.channel`（列级授权：`user_id`、`channel_id`、`ast`、`status`）与 `usr.mute_rule` 中的所需列；日批档的节点倒排与质心点积还需 `usr.interest_node_weight`、`usr.user_vector`。05 §4 已把这些列授予 `pc_sys_percolator`；06 的日批作业调用候选生成时须使用同一角色，或由 05 为其另设等价的列级授权（§20）；
  - 对 `usr.feed_inbox` 只有 INSERT。它能写任何用户的收件箱，却读不到任何收件箱；应用角色不变。
- **日志**：ops 日志只记聚合指标（批大小、滞后、各路候选数），不记"谁命中了什么"。
- **幂等**：
  - 每个近线微批登记在 05 的 `ops.percolate_batch`：批次号、`index_seq` 区间、所用频道 `ast_hash` 集合排序后的摘要（`channel_set_digest`，不存集合本身）、频道数与完成时间（05 §3.4 ⑩）。批次必须按 `index_seq` 区间而不是作品 ID 区间登记：R2-35 要求重新匹配的已有作品 ID 很小，落不进"新 ID 区间"；按 ID 区间登记会让它们永远不被处理，或与旧批次重叠。05 当前的列是 `work_id_lo/hi`，须改为 `index_seq_lo/hi`（§20 第 29 项）。
  - 已完成的批次不重跑。崩溃后只重跑未完成的批次，其中已写入的行由主键静默跳过（或在退回形态下由读取端去重，§12.1）。
  - 因嵌入未就绪而延后的语义子句，在嵌入就绪后的批次中按作品重算；重复写入同样被主键吸收。
  - 日批档的幂等与重跑由 06 的作业框架负责；候选生成是纯函数（同一输入得到同一候选），可安全重跑。
- **不遗漏**：某批运行期间新建或修改的频道，由 §11.5 的回看覆盖。

### 12.6 频道语义与护栏（延续 v1 FR-16）

- **"新"的定义**：频道的"新"= 用户上次查看该频道之后的命中。每频道的游标存在 usr 域。
- **过载护栏只限推送，不限可见**：
  - 当日写入某频道的命中达到 `daily_cap` 后，后续命中不再写入 FeedInbox。顺序按 `index_seq` 先到先得，结果是确定的。原稿写"只保留得分最高的 `daily_cap` 条"，但它落不了地：频道命中的 `score` 为空（§12.1），近线档按 10 分钟微批写入、当天后续命中尚未到达，写入角色又只有 INSERT，无法事后择优替换。频道命中之间的先后由 06 在读取时按其打分决定；
  - 计数只在 Percolator 进程内存中按 (频道, 自然日) 维护，不落库。崩溃恢复时，对当日已完成批次（`ops.percolate_batch` 的 `index_seq` 区间）重放频道求值来重建计数：候选生成是纯函数，重放得到同一命中序列（§12.5）；
  - 频道设置页展示过载报告：命中按 subfield 与 venue 的分布、溢出数，以及收窄建议（例如加一个 venue 或主题筛选条）。这些数字由设置页按 §10.5 的方式对语料直接求值得出，不另存；
  - 频道收件箱列表（07）按 §10.5 的方式对语料直接求值，因此全部命中仍然可见，满足 06 §11.3 的"订阅不漏"承诺。

  这沿用了 v1 design/09 §6"熔断出过载报告、建议收窄"的语义，只把"不入库"改为"不推送"。语料是共享的，入库本身不受影响。
- **版本更新**：见 §12.1 与 §9.6。

---

## 13. 稳定性工程

平台侧一切第三方出站请求都经过**出站网关**，包括交互检索、收割、enrich、成员探测。出站网关即 02 的 P13 Egress Gateway，是平台唯一的公网出口（02 AD-01；名称与"网络隔离强制"按 R2-08）。部署级上游 API key 由网关独占读取（R2-30），检索服务与 worker 都拿不到明文 key。下列机制在网关内统一执行，调用方不得绕过。每个出站请求写一条 FetchLog，落表为 05 的 `ops.fetch_log`，满足 HC-28 的可审计要求（02 §2.3.13）。robots 先行闸也在网关内执行：HTTP 层在发出请求前检查 robots 快照并检测挑战页（SI-38；08 登记为 HC-29），规则由 03 定义。robots 中的 `Crawl-delay` 按 P-05 取最严，与书面限额一起构成账本的上限（例如 Europe PMC 的 10 秒，§8.4）。调研期间出现过多次"先请求、后读 robots"的偏差（调研综合 §1.5），说明这一闸门必须由框架强制，不能依赖调用方的纪律。

### 13.1 配额账本（响应头驱动）

- **键**：(source, host, request_class, credential_principal, egress_ip)。其中 egress_ip 按综合 §8 对 P-04 的细化建议补入（SI-37）。
  - egress_ip 维只用于记账与审计，以及遵守按 IP 计额的源（ORCID、OpenCitations、ROR、Zenodo，AG §3-6）。**限额在 (source, host, request_class, credential_principal) 上跨出口 IP 汇总执行**：出口 IP 增加时，总速率不得随之增加。否则按 IP 分桶就等于用多 IP 扩容，正是 P-04 与 AG §3-6 禁止的做法。T1 的出站网关是单例、单出口（02 AD-01），这一维通常只有一个值。
  - 同一账本键被多个端点、多条舱壁道共享。例如 Crossref polite 单条池（10 req/s、并发 3）由 `journal_works` 与 `works_doi` 等端点共用（AG §0-1、03 §4.2），见 §13.2。polite 池的数值来自公告、文档与第三方观测，调研没有用平台联系邮箱实测（AG §4 Q4 ⚠），账本以实际响应头为准。
- **读取的响应头**：
  - IETF `RateLimit` / `RateLimit-Policy`（HF、OpenReview；CS §3-12）；
  - `x-ratelimit-*`（OpenReview、OpenAlex；OpenAlex 另有美元额度头，并在响应体 `meta.cost_usd` 中核销，D-021）；
  - Crossref 的 `x-rate-limit-limit`、`x-rate-limit-interval`、`x-concurrency-limit`、`x-api-pool`（AG §0-1）；
  - CORE、Zenodo、INSPIRE、ADS 的 `X-RateLimit-*`（AG §2.3.3）。其中 CORE 在取得许可前、ADS 在 R2-14 的条款确认前都不经平台网关调用，这两项只为将来启用保留；
  - `Retry-After`，优先于本地退避（RT §9.1）。

  无响应头时退回 SourceSpec 中登记的书面限额（03，带 verified_at）。
- **有效上限**：有效上限 = min(书面限额, 响应头声明) × 0.8 [判断]。**永不超过书面限额，不探测上限**（RT §2.3-1）。
- **预算类型**：
  - 令牌桶：速率与并发；
  - 美元预算：OpenAlex 免费 key 每日 $1（RT §2.2）。简报 Q3 的默认是不购买付费档；
  - 每日配额：有配额的源按日计。
- **快速失败**：交互请求的预计排队时间若超过其子截止，立即返回 `budget_exhausted`，不排队（§8.2）。
- **OpenAlex 预算闸**：
  - 美元额度按舱壁道切分 [判断]：交互道 80%，收割与 enrich 道合计 20%。可选的 `group_by` 统计与成员补查计入后者（§5.5）。
  - 当日支出达到 80% 时，路由器把 OpenAlex 的影子价格大幅上调并告警。这对应 Q3 的升级触发条件"每日联邦查询超过免费额度 80%"（调研综合 §7.1）。
  - 达到 100% 时，当日剩余时间内 OpenAlex 不参与交互路由。基于快照的收割不受影响。
- **状态持久化**：账本状态在网关内存中，周期性写入 `ops.quota_ledger`，供审计与重启。重启后从保守窗口起步。

### 13.2 AIMD 自适应并发

- **粒度与初值**：每个（端点, 舱壁道）维护并发窗口 W 与速率 R。初值 W=1，R = 书面速率 / 2 [判断]。
- **共享上限**：(端点, 道) 只是调节粒度。令牌与并发名额从所属账本键（§13.1）的共享桶中领取，同一账本键下各端点、各道的速率之和与并发之和都不超过有效上限。例如 Crossref polite 单条池的 10 req/s 与并发 3，由 `journal_works` 与 `works_doi` 的收割道和交互道共同分享；各自的 AIMD 只在自己的份额内加减，份额按 §13.5 的舱壁比例分配。
- **加性增**：连续 20 个请求 [判断] 都成功，且延迟没有膨胀（近期 p50 ≤ 1.5 × minRTT [判断]）时，W += 1，R 加性增加，直到书面上限。例如 arXiv 并发为 1；Crossref polite 书面并发为 3，v2 起步为 2（RT §9.3）。
- **乘性减**：出现 429、503、超时、5xx 或延迟膨胀时，W = max(1, W/2)，R 减半，并遵守 `Retry-After`。
- **上限**：上限永远是书面限额，只在其下调节，只降不超（RT §9.1）。

### 13.3 重试预算

- **两层上限**：每个请求最多尝试 3 次；每个端点在滑动 2 分钟窗口内，重试占比 ≤10%，超出则只报错、不重试（RT §9.1，依据 Google SRE）。
- **退避**：Full Jitter，基数 1 s，封顶 60 s；`Retry-After` 优先。
- **截止时间感知**：剩余截止时间小于该端点 p50 时不再重试。
- **可重试的错误类**：沿用 v1 的错误分类学（design/05 §4）。
  - 可重试：`transient`、`rate_limited`（退避后重试，并计入预算）；
  - 不重试：`gone`、`auth_expired`、`no_entitlement`、`challenge`、`parse`、`config`。
- **客户端自适应节流**：近 2 分钟内 requests > 2 × accepts 时，按概率在本地丢弃低优先级请求，先丢 harvest 与 enrich 道（RT §9.1）。

### 13.4 熔断状态机（按"源 × 端点"）

```text
                 5 连败，或 60s 内 ≥20 请求且错误率 >50%，或退避后 429 仍持续（≥10 次/60s）[判断]
   ┌──────────┐ ─────────────────────────────────────────────► ┌──────────┐
   │  CLOSED  │                                                │   OPEN   │
   └──────────┘ ◄─────────── 探测成功 ────────┐                 └──────────┘
        ▲                                     │                     │ 冷却期满（30s 起，逐次 ×2，封顶 30min）
        │                               ┌───────────┐ ◄────────────┘
        │                               │ HALF_OPEN │ ── 探测失败 → OPEN（冷却 ×2）
        │                               └───────────┘    （仅 1 个探测名额，交互请求可占用）
        │
        │  策略引擎重评通过，且人工确认（沿用 v1 BLOCKED 语义，D-006）
        │
   ┌────────────────┐ ◄── 任意状态：挑战页（含 403 + cf-mitigated: challenge，D-030），
   │ POLICY_BLOCKED │      robots 闸拒绝，robots 或 TDM 信号漂移（立即，R2-15），
   └────────────────┘      策略模式降到 on_demand 以下（link_only / deny）
                           （不自动恢复；挑战时该主机冷却 24h，D-030）
```

- **ToS 哈希变化不直接进入 POLICY_BLOCKED**（R2-15）：7 天宽限内照常路由与收割；期满未复核时模式降为 `on_demand`，只停后台收割（WatchKey 改走替补链，§11.1），交互联邦照常。`review_overdue` 同理，宽限 30 天（R2-16，§5.5）。

- **失败的计数口径**：计入 `transient`、超时、5xx、`parse`，以及两类"可疑成功"：
  - 200 空体：bioRxiv `/details` 曾返回 200 空体（LS §2.2.1、§3-11）；
  - 伪 200 "Rate exceeded."：arXiv（CS §3-6）。

  两者都判为失败，并送 03 的漂移探针（SI-12）。404 是有效答案，不计入。
- **熔断粒度**：按"源 × 端点"（简报 §6.2-5、RT §9.1），一个端点熔断不影响同源的其他端点。

### 13.5 舱壁（三道）

| 道 | 承载 | 份额 [判断] | 执行位置 |
|---|---|---|---|
| interactive | LOOKUP 替补链、联邦检索 | 默认每个上游的令牌与并发 ≥50%（RT §9.1）；可按源覆盖（见下） | 检索服务的异步执行器 |
| harvest | WatchKey 轮询（含按需刷新提前的轮询，§11.6）、基础收割、快照下载（03 的 `bulk_snapshot` 家族，R2-11） | 与 enrich 分享其余份额 | procrastinate 队列（B-05），独立 worker 池 |
| enrich | 摘要补齐、成员探测、查询即入库的规范化 | 同上 | procrastinate 独立队列 |

- **按源覆盖份额**：只做中心镜像、交互检索不走远端的源，交互道只留极小份额。典型是 arXiv：全平台每 3 秒 1 次、单连接，日历型收割必须优先，交互道只保留 LOOKUP 替补链的偶发 `id_list` 调用（§8.4、CS §3-6）。份额写在 SourceSpec 的礼貌参数里（03）。
- **借用**：舱壁是工作保持型的，空闲份额可以出借。交互道需要时立即收回，已发出的请求不被抢占。
- **用户间公平**：交互道是所有用户共享的。为防止单个用户耗尽它，02 在 API 侧按用户扣减联邦配额（02 §2.3.13）；出站网关本身不感知用户身份。用户配额用完时，其检索降级为"仅本地"并给出提示。
- **连接池**：procrastinate 的 LISTEN 需要直连 PG 或会话池（RT §10.6）。
- **与 v1 的关系**：这重新评估了 v1 D-039"任务优先级队列 defer"。v1 是单用户，FIFO 已够用；v2 多用户下，交互与后台必须分道。ADR 候选见 §18。

### 13.6 禁止对同一第三方主机对冲

- **允许的对冲**：只在"同能力、不同主机"的端点之间对冲。额外负载 ≤5%，并计入预算（RT §9.1、P-04）。
- **两道检查**：计划构建器静态检查"对冲目标主机 ≠ 主请求主机"；网关在运行时再拒绝一次。
- **同主机的额外尝试**：同主机只能在重试预算内做带退避的顺序重试，不能并发复制请求。

### 13.7 应用层 TTL 缓存与 λ̂

- **只能做应用层缓存**：Crossref、OpenAlex、S2 的单条 GET 都不返回 ETag 或 Last-Modified（RT §2.2 实测），无法做 HTTP 条件缓存。
- **缓存结构**：
  - 键为 `plan_key`（端点 + 规范化下推参数 + 页号），不含用户信息；
  - 值为规范化记录、fetched_at 与许可标签；
  - 存 PG 表（可为 UNLOGGED [判断]），或可选 Valkey（BSD）。
- **列表与检索结果的 TTL** = min(24 h, 0.1/λ̂_key)（RT §9.1 [判断]）。含义：在 Poisson 假设下，TTL 内至少出现 1 条新匹配的概率约为 λ̂·TTL；取 0.1/λ̂，即把"缓存过期而不自知"的概率控制在约 10%。λ̂_key 用与 WatchKey 相同的 Gamma-Poisson 估计器（§11.3）：每次刷新时，比较新旧结果，以新增条目数作为观测；先验取 TSRG 的 λ(s, t) 乘以该键的选择率。
- **实体缓存**：单条记录的 TTL 为 7 天 [判断]，后台刷新；404 的负缓存 1 h [判断]（RT §9.1）。
- **迟到结果**：截止后才到的结果写缓存（§8.2）。
- **HTTP 缓存库**：hishel（BSD-3）只用于确实支持缓存头的源（RT §9.1）。

### 13.8 singleflight 与请求合并

- **singleflight**：`plan_key` 相同的在途请求合并为一次上游调用，结果分发给所有等待者（CP §2.4 调度原则 2）。
- **批量化**：在 enrich 道，把 DOI 查找批量化。例如 S2 `/paper/batch` 每次 ≤500 个；OpenAlex 单个过滤的 OR 值 ≤100 个（AG §2.3.2、RT §2.2）。

### 13.9 降级矩阵

| 故障 | 受影响能力 | 自动降级 | 用户可见 |
|---|---|---|---|
| OpenAlex 失败或当日预算耗尽 | 联邦检索、语义探索、route_stat 周更 | 从路由中剔除，走替补链下一级；周更改用季度快照离线计算 | 完整性报告："OpenAlex 暂不可用 / 今日额度已用完" |
| Crossref 失败 | DOI LOOKUP、期刊增量收割 | LOOKUP 改走 OpenAlex 单实体；收割延后，由水位保证不漏 | 数据时点标注延后 |
| arXiv 限流（429 或伪 200） | 预印本增量收割 | 日历内补轮询，RSS 作轻量通道，指数退避 | 数据时点标注 |
| S2 失败 | 标题匹配、远端推荐 | 跳过 | 完整性报告 |
| EPMC 失败，或 Crawl-delay 令牌在子截止内拿不到（`budget_exhausted`） | 生命科学联邦检索、PMID LOOKUP | 改走 OpenAlex；NCBI 书面确认后 PubMed 也可替补（R2-13） | 完整性报告 |
| 出站网关整体故障 | 全部远端能力 | 全站"仅本地"模式 | 顶部提示"外部来源暂不可用" |
| TSRG 快照损坏或加载失败 | 路由 | 回滚到上一个版本；仍失败时用静态路由（本地优先 + 固定替补链） | 无 |
| 检索服务故障 | 全部检索 | 高可用方案由 02 定义；卡片流（06）读取已生成的 Deck，不受影响 | 检索页提示 |

---

## 14. 准确率与性能

### 14.1 评测体系

**(a) 路由评测：对照全源穷举**（RT §12-22）
- **查询集**：
  - LitSearch 的 597 条 ML/NLP 查询（MIT 许可，RT 附表 A）；
  - 分学科金标，数学、物理、化学材料、生命科学、心理、经济、金融、商管、CS 各 ≥200 条（SI-68、G-06）；
  - 去标识的真实查询抽样，是否可用以 08 的同意规则为准。
- **穷举基线**：对每条查询，用宽裕预算跑全部可行端点。在 enrich 道的非高峰时段执行，受限速约束，并充分利用缓存。结果经残差与折叠后得到 R_all。
- **指标**：
  - 召回保持率 RR = |R_router ∩ R_all| / |R_all|，另报一个 top-k 加权版本；
  - 成本比 = cost_router / cost_all；
  - 延迟；
  - 以上均按学科、按意图分别报告。
- **近似比**：对抽样的路由决策做精确枚举，报告 f(ALG)/f(OPT) 的分布（§6.7）。
- **离线回放**：用路由决策日志评估 TS 与 GBDT 路由器（P-08、§6.9）。

**(b) 检索质量**
- **LitSearch**：对 BM25、稠密、混合（RRF）、混合 + CE 四种配置，报告 recall@5、recall@20 与 nDCG@10。外部参照：最佳稠密检索器的 recall@5 比 BM25 高 24.8 个百分点；LLM 重排在其上再提升 4.4%（RT §4.1）。
- **SciRepEval**：用其检索类任务（RT §4.1、§12-21）。代码仓库为 Apache-2.0，HF 上数据集的元数据未声明许可（一手来源，2026-09-27 查阅）⚠：只作离线评测，不进分发产物，许可核清前不把它的样本并入自有金标（§1.6）。
- **分学科金标**：recall@k、nDCG@10，另对 LOOKUP 报告 MRR。
- **LOOKUP**：标识符解析成功率；标题 top-1 准确率，测试集含拼写噪声。
- **实体链接**：在标注集上的 venue 与主题链接准确率。
- **放宽**：健全性的属性测试（§7.6），以及各端点的失配率（§7.5）。

**(c) 新鲜度**
- 金丝雀样本：arXiv OAI 的新 ID、Crossref `created`、EPMC `FIRST_IDATE`。
- 各源分别统计"源可见 → 入库 → 写入 FeedInbox"的滞后，报告 p50 与 p95。用 Crossref `created` 测量各 venue 时滞的建议见 CS §3-5 与 §3-17。

**(d) 性能**：快路径、实体链接、路由、本地各路召回、CE、本地端到端、联邦首屏与完成、Percolator 批次，各报 p50/p95/p99；另报路由快照的内存。

**(e) 稳定性演练**（RT §12-23）：
- 注入故障：429 风暴、延迟尖峰、5xx、挑战页、伪 200、200 空体、响应头异常；
- 验证：熔断、重试与预算、降级、禁止同主机对冲；
- 复用 v1 的 fixture 回放体系。

**(f) 容量压测**：在目标硬件上，用自有语料与查询集复测 recall@k、p50/p95/p99、建索引时间与常驻内存（RT §5.3 的方法论提醒）。

### 14.2 性能预算（T1，设计目标）

本地检索端到端 p95 ≤800 ms（简报 §3），各阶段拆分如下 [判断]：

| 阶段 | p95 预算 |
|---|---|
| 规则快路径 | 20 ms |
| 实体链接 | 50 ms |
| 查询嵌入（缓存未命中；按查询哈希缓存，OSS §3-8） | 60 ms |
| 路由（含 P(t\|q)；在本地召回之后执行，不在首屏关键路径上，保守计入，§8.2） | 5 ms |
| 分面位图与选择率规划 | 20 ms |
| BM25、tsvector、HNSW 或精确扫描（并行） | 200 ms |
| 折叠、残差、RRF | 30 ms |
| CE 重排（超出预算则改为 `upgrade` 事件，§8.7） | 300 ms |
| 补水、权利闸、序列化 | 60 ms |
| **合计** | **745 ms**（留 55 ms 余量） |

两个口径的区别：
- 简报 §3 的 ≤800 ms 是**端到端**口径；
- SI-27 的升级触发条件"检索 p95 >300 ms"是**单路召回**口径（HNSW 或 BM25 单独计）。

二者并不矛盾，本文分别采用（§19-8）。

### 14.3 容量估算（T1）

| 组件 | 起步 300 万篇 | 1,000 万篇 | 依据 |
|---|---|---|---|
| HNSW（256 维 halfvec；选中支持 MRL 的模型时） | ≈2.3 GB | ≈7.7 GB | §9.3 [估算] |
| 全维向量（1,024 维，在磁盘；只作精排） | ≈6.1 GB | ≈20.5 GB | RT §5.3 |
| HNSW（1,024 维 halfvec；选中不支持 MRL 的模型时，与上两行二选一） | ≈6.9 GB | ≈23 GB | §9.3、RT §5.3 [估算] |
| 推荐向量（256 维，06 与 02 A-6） | ≈1.5 GB | ≈5.1 GB | 02 §2.11 |
| 词法：`work_search` 与 BM25 索引 | ≈8 GB | ≈26.5 GB | 05 §8.2 [估算] |
| 词法：增补的 tsvector 与 GIN（§9.2） | 同量级，待实测 | 同左 | [估算] |
| 引文表与索引 | ≈10 GB | ≈35 GB | 05 §8.2 [估算]；超过 20 GB 时考虑数组化（05 §3.1.5） |
| 分面位图（进程内） | ≈75 MB/进程 | ≈250 MB/进程 | §9.4 [估算]；按工作进程数折算 |
| TSRG 快照 | ≈45–55 MB/进程（为叶子建质心时 d=256 约 65 MB、d=1,024 约 130 MB；加载 MSC 插件约 140 MB） | 同左 | §5.6 [估算]；按工作进程数折算 |
| 已见位图（1 万用户、每年） | ≈1.5 GB | 同左 | RT §7.2 |
| FeedInbox（保留 14 天，05 默认） | ≈1.7 GB | 同左 | §12.4 [估算] |

**硬件**：T1 的参考硬件是单主 PG 18，64–128 GB 内存，NVMe（RT §11）。1,000 万篇、检索 ≤50 QPS 时单节点足够（RT §4.4 [判断]）。以上所有数值都须在目标硬件上实测（§14.1(f)）。

**OpenAlex 费用模型** [估算]。假设：每个活跃用户每天 3 次检索，其中 30% 联邦，每次联邦调用 1 次 OpenAlex 搜索（$0.001）。
- 1,000 个活跃用户约 900 次/日，约 $0.90/日。按 §13.1 的切分，交互道只有免费 key 每日 $1 的 80%，即 $0.80：预算闸会在当日后段调高影子价格，约 10% 的联邦改走 S2 等替补端点或只返回本地结果。换言之，T1 的 1,000 DAU 已触及免费额度，Q3 的 80% 触发条件在 T1 就可能成立（§14.4）。02 §2.11 按每人每日 5 次、15% 联邦估算为约 $0.75/日，结论相同：已接近免费额度；
- 若把 `route_stat` 的 `group_by` 全量统计放在同一天（约 $0.90，§5.5），当天交互联邦几乎全部被挤出 OpenAlex。所以 `route_stat` 默认用快照离线计算，`group_by` 只作分摊到 7 天的补充；
- 1 万个活跃用户约 $9/日，超出免费额度。须触发 Q3（Member 档每日 $20 起，AG §2.3.3），或把更多查询导向 OpenAlex 过滤接口（$0.0001/次）与本地。

这些假设比例须上线后用实测替换。

### 14.4 升级触发条件

| 触发条件 | 阈值 | 升级动作 | 依据 |
|---|---|---|---|
| HNSW 不能常驻内存 | 索引 > 可用内存的 60% [判断] | pgvectorscale：StreamingDiskANN + SBQ + `smallint[]` 标签过滤。subfield 与 topic 编号都可入 smallint | RT §5.4、SI-27 |
| 单路召回 p95 | 连续 7 天 >300 ms | 同上；再不够则上外置引擎（Qdrant、Vespa、OpenSearch 三选一），经 outbox/CDC 同步，PG 仍是真值 | SI-27、RT §5.4 |
| 建索引时间 | 超出夜间维护窗口 | 同上 | SI-27 |
| 语料规模 | >1,000 万篇 | 评估 pgvectorscale 与按主题分片（selective search） | RT §5.4、§3.1 |
| BM25 延迟或建索引时间 | 不达标 | 评估 ParadeDB（AGPL，仅作可选）或外置 OpenSearch | RT §5.2、B-06 |
| 频道数或 Percolator 滞后 | 频道 >10⁵，或滞后 p95 >30 min | OpenSearch percolate | RT §13-11 |
| 路由日志量 | ≥2 万条已标注的联邦查询 | GBDT 路由器（按 §6.9 的闸门） | RT §3.5.4 |
| OpenAlex 支出 | 连续 7 天 >80% 免费额度 | Q3：评估 Member；或提高快照频度 | 调研综合 §7.1 Q3 |
| 事件表规模 | >10⁹ 行/年 | ClickHouse（05 负责） | RT §10.4 |
| 多跳图查询 | 出现稳定需求 | Apache AGE（同库） | RT §6.4 |

---

## 15. 多用户

### 15.1 每用户频道

频道表以 05 的 `usr.channel` 为准（05 §3.2.4），列包括：
- `channel_id`（uuid）、`name`、`status`（active / paused / needs_review）、`push_prefs`；
- `ast`：Query AST，按 04 的 JSON Schema 校验；
- `ast_schema_version`；
- `ast_hash`：规范化哈希，即本文的 `query_hash`；
- `legacy_dsl`：v1 迁移时保留的原 DSL。

04 对它有三点要求：
- `ast` 中须同时保存 `missing` 与 `accept`（§3.5）。v1 迁移来的频道为 `closed_world`；
- `push_prefs` 至少包含 `daily_cap`（§12.6）、摘要节奏与免打扰时段；
- 若要支持 `@name#v` 钉住历史版本，需要 05 增补不可变的版本历史表；否则 `ChannelRef` 只能引用当前版本，并在规范 AST 中记录其 `ast_hash` 以供复现（§3.3、§20）。

其他约定：
- **上限**：每用户 ≤50 个频道，其中宽频道 ≤3 个 [判断]，以约束 Percolator 的成本。
- **保存的检索即频道**：保存一个 SEARCH 查询，就是一个关闭推送的频道。
- **共享**：频道的共享（公开或团队）目前没有定义，列为待决问题（§20）。公开频道的名称与说明属于用户发布的内容，若开放，须等 HC-15 的 UGC 阶段条件就绪（审核、举报、通知—处理等）。

### 15.2 已见集合

见 §9.6。已见集合存于 05 的 `usr.seen_segment`：按 `work_id` 存储、按 cluster 求值，由 06 的下发与事件驱动。

### 15.3 个性化与偏好挂点（与 06 的接口）

| 挂点 | 04 提供 | 06 或 05 提供 | 约束 |
|---|---|---|---|
| 检索结果个性化重排（FR-84） | 候选与特征、融合方式（§8.8） | 06 的 `personal_score(u, work_ids)` | SEARCH 中位移 ≤5；`personalize=off` 或处于 `np_time`/`np_source` 时跳过（R2-05） |
| FeedInbox | 频道命中（直接写入）；节点与质心候选读者（交 06 分配） | 06 的层② 分配与 Candidate Pipeline 的 Source 组件 | 归因以 `origin`/`push_reason` 表示（§12.1） |
| 兴趣树结构 | 节点层级、质心、兄弟节点 | 06 的画像学习与探索臂（Thompson） | 画像只存 usr 域（05 `usr.interest_node_weight`） |
| 已见与隐藏 | `NotSeen` 求值 | 06 的下发与事件；05 的 `usr.seen_segment` | 按批次写入；会话内即时排除 |
| 用户级来源偏好（FR-28） | 执行约束 `scope.exclude`，以及本地残差谓词"排除只来自被屏蔽来源的作品" | 05 的关注与屏蔽数据（`usr.follow`、`usr.mute_rule`；R2-33 的 `block.target_type=source` 在事件接入事务内同步写入，当次检索即生效；关注经 02 的 `/me/follows`，R2-47） | 偏好是用户显式设置，不属于画像；只影响本人的计划，不写入全局路由统计。`usr.session_suppress`（R2-33）只作用于 Deck（06），检索结果不隐藏被标记"不感兴趣"的条目 [判断] |
| 查询历史 | 查询原文与规范 AST 写入 05 的 `usr.search_history`（RLS，用户可查看、可随时清空）；执行记录写入 `evt.search_log`，只含 `query_id` 引用、意图、所用来源、是否联邦、费用、延迟与结果数，不含查询原文（05 §3.3.3） | 06：经同意后作为短期兴趣信号 | 留存规则按 08 |
| 非个性化模式 | 读取 05 的 `profile.personalization_mode`，取值 `personalized`/`np_time`/`np_source`（R2-05）；非个性化时 LATEST 与频道视图的排序见 §8.8 | 06 §13.5 | 立即生效（HC-13） |

**路由不使用个人画像**，有三个理由：
1. P-02：由个人画像派生的路由决策属于个人派生物，其结果统计不能进入全局路由学习；
2. 缓存复用：路由与用户无关时，不同用户的同一查询得到同一计划，可以共享缓存；
3. 可复现：同一 `query_hash` 在同一快照版本下的计划确定。

这一条覆盖的不只是画像：个人谓词（已见、在库、评分）的求值结果、`personal_score` 的重排与 `private` 列表，同样不进入路由的任何输入，包括 §6.2 的 p_r、§6.3 的 `n_local_T` 与 §5.3 的 η 观测集合 T。否则第 1 条的派生路径与第 3 条的可复现性都会失守：两名用户提交同一规范查询，会因已见集合不同而得到不同的 π 与计划（AC-V2.28）。

个人画像只用于消歧候选的排序，结果只对本人可见（§4.3）。用户的显式来源偏好（FR-28）与此不同：它是用户明确的设置，以执行约束的形式进入本人的计划。它只会减少子查询，不会产生依赖用户的缓存键。

### 15.4 隐私要点

1. **出站不带用户身份**：只用平台身份（HC-10）。个人谓词永不下推（I-2）。远端相似检索的种子只在用户显式操作时发送（§4.6）。
2. **联邦会把查询文本发给第三方**：例如 OpenAlex、S2。须在隐私告知中说明（08）；设置中提供"仅本地检索"开关，即 `scope=local`。
3. **检索日志**：按 05 的落表，查询原文与规范 AST 只存在 `usr.search_history`（原稿写作"写入 `evt.event`，记录规范 AST"，与 05、07 §16.4 的"查询原文不进事件"冲突，已改）。`evt.search_log` 只记执行元数据，结果条目的曝光与点击按 06 的事件契约绑定 `impression_id`（surface=search）。三者都属个人信息。事件留存按 R2-31：可识别形态 6 个月，假名化 13 个月（PG 热存 6 个月，冷数据归档为 Parquet）；`usr.search_history` 是本人可见、可随时清空的私有数据，不归入事件留存。`ops.route_decision` 是假名化数据，保留 13 个月（05 §3.4 ⑩），与 R2-31 的假名化期限一致。用户可以查看并删除自己的检索历史（P-06）。
4. **路由学习的去标识**：`ops.route_decision` 不写 `user_id`、请求 id 与查询原文，查询只以 `query_key = HMAC(k_route_epoch, query_hash)` 出现，密钥按季度轮换（05 §3.4 ⑩；§6.9）。它是假名化数据：同一密钥周期内同一查询可被关联，但无法与 `usr.search_history.ast_hash` 或 `evt.search_log` 直接连接。基于查询结果与参与行为的奖励，先经 05 §2.5 的聚合闸，只以聚合形式进入：每个格子当日须有 ≥`k_cf` 个不同用户（§6.8）。GBDT 的训练集同样经聚合闸抽取，不直接读明细行（§6.9）。
5. **缓存与用户无关**：跨用户共享的缓存键只用 `plan_key`，个人过滤在取出缓存之后执行；`query_hash` 键控的结果快照只属本人（§3.6）。残余风险：缓存命中的时延可能暴露"近期有人查过同一查询"，查询即入库（§8.5）也可能让语料增长暴露"有人检索过某篇论文"。对策是 API 与界面都不暴露缓存状态与入库来由。风险较低，此处如实记录（与 T16"可解释与隐私泄露"同类）。
6. **私有层隔离**：私有层检索与共享层隔离；platform 部署的私有全文检索只在用户设备上执行（§9.8，R2-27）。
7. **LLM 提示词**：LLM 解析的提示词只含查询文本，且只发给自托管模型（§4.5，R2-45）。
8. **细粒度收割键**：作者与引文邻域键须有 ≥`k_cf` 个不同用户共有才进入 ops 域与上游请求（§11.1，R2-19）。
9. **反向路由不作人与人匹配**：节点倒排（`usr.interest_node_weight` → 用户）与质心点积只用于论文→读者（层②）。研究者↔研究者匹配（层③）须按 HC-18 单独同意、默认关闭，由 06 负责；它若复用这里的用户倒排，只能读取已同意用户的数据（08 §2.2 中 HC-18 的执行点）。候选读者对只交给 06 的分配器，作者一侧看不到论文推给了谁。

---

## 16. 测试方法与测试类型

默认测试全部离线运行，与 AGENTS.md 及 v1 NFR-6 一致。真网验证只在显式开关下执行，形态参照 v1 的 `make smoke`。

| 测试类型 | 对象 | 方法 | 运行方式 |
|---|---|---|---|
| 单元测试 | 解析器（含裸词软/硬判定、符号集合算子混用报错、词内连字符）、规范化、错误码（§3.7）、放宽规则（含 DNF 合并后的无界判断）、三值残差、折叠与 RRF、注水（含预算不可行分支与策略闸）、选源（乘积域求值与逐层倍增对照朴素求值；单项超预算端点被剔除，含"成本 2B、比值最高"的反例；规模闸两侧切换；事后剪枝满足 f(K) > f(S) − n·EPS_GAIN）、范围完整性判定、`near(n)` 编译、Regex 方言、AIMD 与熔断状态机（含 ToS 宽限与 robots 漂移两种路径） | 用例表与边界值；§7.6 列出的固定反例 | CI，离线 |
| 属性测试 | 规范化、NNF、放宽的健全性、隐私不变式、v1 兼容、蜕变关系、选源近似比 | Hypothesis（v1 dev 依赖已有）；生成器见 §7.6 | CI 每次 2,000 例；夜间 10 万例 |
| 契约测试 | 与 03 的 SCD 与放宽；与 07 的 FilterChip 与流式事件；与 06 的 FeedInbox 与 impression 事件；与 05 的 DDL | schema 快照加双向用例；任一方改动都须同时改契约 | CI |
| 集成测试 | PG 18 容器（pgvector、pg_textsearch、pg_roaringbitmap）；检索服务加出站网关，上游用模拟服务；多进程下的位图增量同步与水位尾部补查；账本键跨端点、跨道的共享上限（含 robots `Crawl-delay`）；路由输入与个人数据无关（两名已见集合、画像与私有文献不同的用户提交同一规范查询，比对 RoutePlan 与 `route_decision`） | fixture 回放，沿用 v1 回放体系 | CI，离线 |
| 故障注入 | 出站网关、执行器、降级矩阵 | 模拟上游注入：429 风暴、延迟尖峰、5xx、挑战页、伪 200、200 空体、响应头异常 | CI 跑子集，夜间全量 |
| 离线评测 | 路由（对照穷举）、检索质量、实体链接、近似比 | §14.1；穷举基线在 enrich 道的预算内运行，不进 CI | 夜间或每周 |
| 仿真 | 注水调度（Poisson 到达流）、Percolator 批处理（含 R2-35 的已有作品重新匹配、lenient 频道的缺失字段锚点、`daily_cap` 崩溃恢复后的计数重建）、WatchKey 去重与细粒度键的 `k_cf` 门槛、η 估计器（同一端点"与 OpenAlex 同选"和"单独被选"两种情形下的估计之差只来自抽样误差）、新端点冷启动（审核通过前零出站；探测完成前可被选中并探索）、素描样本框（本地语料增长不改变 cov_local 的无偏性） | 合成数据 | CI 小规模；每周大规模 |
| 性能与容量压测 | 本地检索、路由、Percolator、内存 | 目标硬件，自有语料与查询集（RT §5.3） | 里程碑门禁 |
| 线上金丝雀（门控） | 新鲜度滞后、各源健康、失配率 | 真网小样本；须显式开关与平台联系邮箱，类似 v1 `make smoke` | 定时执行；不属于默认测试 |
| 在线实验 | 路由器升级、融合权重、CE 开关 | 影子模式与交错实验（SI-51） | 上线后 |
| 静态检查 | 禁止同主机对冲；递归 CTE 必带 CYCLE 与 LIMIT；个人谓词不下推；远端子查询不含 user 字段；路由函数不读 usr 域与 `Personal` 求值结果；依赖与模型清单只含 §1.6 中放行或已评审的项 | lint 规则，加编译产物的 AST 检查；依赖清单与模型配置扫描 | CI |

另有两项测试方法：
- **出站审计**：集成测试截获所有出站请求，对照不变式 I-2 与 §15.4，断言请求中不含个人谓词或用户标识。
- **评测复现**：每次评测记录 `tsrg_version`、索引版本、模型版本与查询集版本，使结果可复现（P-08）。

---

## 17. 验收标准（草案）

编号已由 [09](09-roadmap-and-milestones.md) 定稿为正式编号 `AC-V<m>.<n>`，编号中的 `V<m>` 即所属里程碑（起草期为 401 起的占位序号，新旧对照见 09 附录 A）。"01 需求"列给出每条验收对应的 FR 或 NFR；01 为 FR-34…FR-44 登记的验收要点，以及本文协同承接的 FR-28（AC-V4.17）与 FR-84（AC-V6.10）的验收要点，都被下表覆盖或细化，并已按 09 的合并规则与下表对应条目合为同一编号。标注 [判断] 的阈值是设计目标，V1 压测与评测后由 09 定稿。"能力组"列只供 09 映射里程碑参考。

| 编号 | 能力组 | 验收内容 | 度量与阈值 | 测试类型 | 01 需求 | 章节 |
|---|---|---|---|---|---|---|
| AC-V2.1 | AST | 规范化与往返 | 随机 AST 100% 满足：打印后再解析与原树一致；canon 幂等；子节点置换或重结合时 `query_hash` 不变；NNF 保语义 | 属性 | FR-34 | §3.6、§7.6 |
| AC-V2.2 | AST | v1 订阅兼容 | 9 个预置包与存量用户订阅全部可迁移，SSRN 分类项进入 `needs_review` 而非静默丢弃；在 v1 AC-6 fixture 与预置包回归样本上，closed_world 判定与 v1 `filter_papers` + `arxiv.query_bool` 逐条一致（100%），其中含 `\b` 的全部预置包正则按 Python `re` 语义求值；若启用 PG 预筛，预筛结果是应用层结果的超集（100%） | 单元 + 属性（v1 代码作 oracle） | FR-34、FR-47 | §3.8、§7.6 |
| AC-V2.4 | 解析 | 标识符抽取 | ≥1,000 条混合样本（DOI、arXiv 新旧、PMID、PMCID、SSRN、OpenAlex、URL）上，精确率 ≥99.5%，召回率 ≥99% [判断] | 单元 | FR-34、FR-42 | §4.2 |
| AC-V2.5 | 解析 | 意图识别 | ≥500 条中英标注查询上，LOOKUP 与 LATEST 的规则识别准确率 ≥95%，五意图总体 ≥85% [判断] | 离线评测 | FR-34、FR-42 | §4.1 |
| AC-V2.6 | 解析 | 实体链接 | 只输出库内 ID（虚构 ID = 0，构造性检查）；venue 的 top-1 准确率 ≥90%（≥300 条标注）[判断]；歧义时 100% 给出候选筛选条，不静默选择 | 离线评测 + 单元 | FR-42 | §4.3 |
| AC-V2.7 | 解析 | LLM 不阻塞首屏；定稿后联邦 | LLM 超时或失败时首屏正常；首屏 p95 在 LLM 开、关两种配置下相差 ≤5% [判断]；投机首屏阶段截获的出站请求为 0，远端子查询只针对定稿 AST 发出 | 集成 + 压测 | FR-42 | §4.2、§8.2 |
| AC-V2.46 | 本地检索 | 端到端延迟 | 300 万篇语料、目标硬件、T1 负载下，本地检索端到端 p95 ≤800 ms、p99 ≤1.5 s；单路召回 p95 ≤300 ms（超出即按 §14.4 触发升级评估，R2-39）；CE 从小模型 int8、top-50 起步，超预算、先发 RRF 结果再以 `upgrade` 替换的降级路径占全部检索 ≤5%（01 NFR-10、02 AC-V2.46） | 压测 | FR-35、NFR-10 | §8.7、§14.2 |
| AC-V2.11 | 本地检索 | 选择率规划 | 过滤选择率 0.01%–50% 的带过滤向量查询，返回 ≥k 条的比例 100%，recall@k ≥0.95（对照精确计算）[判断]；每路召回在 `where` 约束下返回 min(N_REC, 满足 `where` 的作品数) 条，"罕见短语 + 常见分面""常见短语 + 罕见 venue"两类构造用例不出现后过滤塌陷（100%） | 集成 + 压测 | FR-37 | §3.5、§9.5 |
| AC-V2.9 | 本地检索 | 检索质量 | LitSearch 上混合检索的 recall@20 不低于最佳单路（自然语言查询按软检索文本执行，§3.2）；分学科金标（每学科 ≥200 条）逐学科报告 recall@k 与 nDCG@10，且每学科不低于纯 BM25 基线（01 AC-V2.9）；中文金标报告召回（01 AC-V2.6）；回归门：任一学科下降超过 2 个百分点即阻断发布 [判断] | 离线评测 | FR-35、FR-42 | §14.1 |
| AC-V2.13 | 本地检索 | 已见过滤 | 1 万次抽样请求中，已见 cluster 出现在 LATEST 或频道结果中的次数为 0；正式版到达只生成更新通知 | 集成 | FR-37、FR-46 | §9.6 |
| AC-V2.17 | 本地检索 | 图查询 | 1 跳与 2 跳查询 p95 ≤200 ms（含枢纽剪枝）[判断]；静态检查 100% 的递归 CTE 带 CYCLE 与 LIMIT；尚无被引的新论文经文献耦合得到相关论文，并带"共享 N 篇参考文献"理由（构造用例 100%，01 AC-V2.17） | 压测 + 静态检查 + 集成 | FR-43 | §9.7、§10.6 |
| AC-V2.19 | 本地检索 | 索引一致性 | 夜间对账对注入的三类漂移（漏索引、孤儿行、位图偏差）100% 告警；无漂移时报告各项计数，不静默通过 | 集成 | FR-35、NFR-26 | §9.9 |
| AC-V2.22 | TSRG | 快照 | 构建 ≤30 min、快照 ≤200 MB [判断]；热切换期间零请求报错；100% 的路由决策日志带 `tsrg_version` 与 η 载入日期；四种用途（路由、调度、兴趣挂点、反向推送）引用同一套 `topic_node.node_id`（契约测试，01 AC-V2.25）；素描本地位的刷新滞后 ≤1 天 | 集成 + 压测 + 契约 | FR-41 | §5.3、§5.4 |
| AC-V2.24 | 路由 | 计算延迟 | 50 个端点、4,798 个节点时，路由计算 p95 ≤5 ms，含探索判定的第二次选源；最坏构造（n=10 且 K·P=1,024 的规模闸边界；n=20 且 K·P=4,096 的贪心）单次 ≤5 ms；选源过程不调用 exp/log（代码检查） | 压测 + 静态检查 | FR-41、NFR-10 | §5.6、§6.4、§6.11 |
| AC-V2.25 | 路由 | 路由效率 | ≥1,000 条评测查询上，对照全源穷举的召回保持率 ≥0.95，成本 ≤穷举的 50% [判断]；同等预算下召回保持率不低于"按成本均匀分配"与"随机选源"两个朴素基线（01 AC-V2.25） | 离线评测 | FR-38、FR-41 | §14.1 |
| AC-V2.26 | 路由 | 近似比 | 在素描目标上按**增益**计算近似比 (f(ALG) − f(∅)) / (f(OPT) − f(∅))（f(OPT) > f(∅) 的样本；直接用 f 的比值会被 cov_local 稀释，§6.1）。抽样决策的第 10 百分位 ≥0.9 [判断]；任何样本都不得低于 0.316 − n·EPS_GAIN / (f(OPT) − f(∅))，作为算法实现正确性的护栏（OPT 在剔除单项超预算端点后的候选集上计算）；另报预筛（n > 20）丢弃端点的比例，以及 n ≤10 却因规模闸改用贪心的决策比例 | 离线评测 | FR-41 | §6.6、§6.7 |
| AC-V2.27 | 路由 | 探索预算 | 多个 API 进程并发时，每个端点每日的探索请求 ≤其交互道预算的 10%，由出站网关的全局计数执行（故障注入：人为调高采样方差也不越限） | 集成 | FR-41、NFR-14 | §6.8 |
| AC-V2.30 | 放宽 | 健全性 | 夜间 ≥10 万例属性测试 100% 满足 I-1、I-2、I-3；§7.6 的四个错误变换都被判为违规 | 属性 | FR-38 | §7.3、§7.6 |
| AC-V2.31 | 放宽 | 失配监控 | 注入分析器差异后，当日触发失配告警；生产目标：各端点失配率 ≤2% [判断] | 集成 + 线上监控 | FR-38 | §7.5 |
| AC-V2.32 | 执行 | 截止与流式 | 联邦总截止 3 s 内 100% 发出 `done`；迟到结果 100% 写入缓存；用户已看到的条目在 `upgrade`/`append` 中不移位（前端契约测试） | 集成 + 契约 | FR-38、NFR-10 | §8.2 |
| AC-V2.33 | 执行 | 部分失败 | 逐一注入各上游故障时，API 的 5xx 为 0；结果 100% 带缺源标注与完整性报告 | 故障注入 | FR-38、NFR-13 | §8.3、§13.9 |
| AC-V2.10 | 执行 | 折叠 | 同一作品的多个版本在同一列表内不重复计分（构造用例 100%）；弱信号不合并（D-007 用例 100%） | 单元 | FR-35 | §8.5 |
| AC-V2.38 | 调度 | WatchKey 去重与礼貌 | 把同一组频道复制给 N = 1、10、1,000 个用户，收割道的上游请求量不变（确定性仿真，差值 0，01 AC-V2.38 与 NFR-14 的口径）；交互道请求量受交互道令牌上限约束，不随用户数越过上限；同一个键只收割一次；引用计数在并发增删频道下最终一致，归零并过宽限期后停止收割（属性测试） | 仿真 + 属性 + 压测 | FR-40、NFR-14 | §11.1 |
| AC-V2.39 | 调度 | 注水分配 | 各源收割道每日预算 100% 不超；Poisson 仿真中加权发现延迟不劣于均匀分配 | 仿真 | FR-40、NFR-14 | §11.4 |
| AC-V2.40 | 调度 | 新鲜度 | arXiv：公告日 OAI 可取后到写入 FeedInbox 的滞后 p95 ≤3 h，即公告后约 5.5 h 以内，满足 NFR-12 的 ≤6 h；Crossref 代理的 venue：从 `created` 到入库 p95 ≤24 h [判断] | 线上金丝雀（门控） | FR-36、NFR-12 | §14.1 |
| AC-V2.42 | Percolator | 正确性与时效 | 回放一天数据，频道命中与暴力求值逐条一致（100%，含 `substring_ci` 与 Regex 子句，以及 lenient 频道遇到字段缺失的作品）；重跑批次零重复；每日 3 万篇、5 万个频道时，频道命中从入库到 FeedInbox 滞后 p95 ≤30 min；日批档的节点与质心候选对照"全体用户质心暴力点积"的每篇前 L 读者，召回 ≥0.99 [判断] | 仿真 + 压测 | FR-40、NFR-12 | §12 |
| AC-V1.1 | 稳定性 | 礼貌与闸门 | 压测与故障注入中，任何 (source, host, class, credential) 的请求率与并发超过书面限额或 robots `Crawl-delay`（如 Europe PMC 的 10 秒）的次数为 0；robots 闸 100% 拦截禁区路径；同主机对冲次数为 0 | 故障注入 + 静态检查 | NFR-14 | §13 |
| AC-V1.2 | 稳定性 | 重试与熔断 | 5xx 风暴下，每个端点 2 分钟窗口内重试占比 ≤10%，单请求 ≤3 次；5 连败内熔断打开；挑战页与 robots 漂移使端点进入 POLICY_BLOCKED 且不自动恢复；ToS 哈希变化在 7 天宽限内不影响路由与收割，期满未复核只停后台收割（假时钟用例 100%，R2-15） | 故障注入 | NFR-13、NFR-14 | §5.5、§13.3、§13.4 |
| AC-V2.35 | 稳定性 | 缓存新鲜度 | 抽样的缓存命中与即时重取相比，遗漏新条目的比例 ≤10%，与 0.1/λ̂ 的设计一致 | 线上抽样（门控） | NFR-14 | §13.7 |
| AC-V2.37 | 隐私 | 出站审计 | 集成测试截获的全部出站请求中，个人谓词与用户标识出现 0 次；`ops.route_decision` 不含 `user_id`、请求 id、查询原文与 `query_hash` 原值，只含 HMAC 的 `query_key`（schema 检查）；`evt.search_log` 不含查询原文；GBDT 训练抽取物中，所属"意图 × π 首节点"格子当日不同用户数 < `k_cf` 的决策为 0（抽取作业断言） | 集成 + 静态检查 | NFR-15 | §6.9、§7.3、§15.4 |
| AC-V2.20 | 合规 | 索引资格 | 共享索引中 C 类字段为 0（审计查询）；切换 B 类策略后，受影响行在一个夜间窗口内完成定向重建 | 集成 | FR-24、NFR-15 | §9.1 |
| AC-V2.36 | 合规 | OpenAlex 预算闸 | 日支出 ≤配置上限；达到 80% 时告警并提高影子价格 | 集成 + 仿真 | NFR-19 | §13.1 |
| AC-V2.16 | 组合 | 频道集合运算 | 频道的并、交、差，与"逐一执行各频道、再在本地做集合运算"的结果逐条相等（属性测试 100%）；组合结果可保存为新频道 | 属性 | FR-39 | §3.5、§10.5 |
| AC-V2.12 | 筛选 | 组合过滤等价 | 任意组合过滤的结果，与"全量取出后在本地过滤"的结果相等（属性测试 100%）；已读过滤基于本人的已见集合 | 属性 | FR-37 | §9.4–§9.6 |
| AC-V2.14 | 最新 | LATEST 零远端调用 | LATEST 请求在出站审计日志中产生的远端调用为 0；结果带各来源的数据时点 | 集成（审计日志） | FR-36 | §10.2 |
| AC-V4.17 | 筛选 | 用户级来源偏好 | 屏蔽某来源后，本人检索结果中"只来自该来源"的作品为 0；同一作品另有未屏蔽来源时照常出现，但不展示被屏蔽来源的链接；其他用户的结果不变（01 AC-V4.17） | 集成 | FR-28 | §15.3 |
| AC-V6.10 | 个性化 | 挂点可关与可复现 | `personalize=off` 或 `np_time`/`np_source` 模式下，检索排序与无画像基线逐条一致；开启时 SEARCH 中条目位移 ≤5 且结果页标注"已按你的兴趣排序"（01 AC-V6.10）；LATEST 的个性化排序覆盖整个候选集，而非只重排最近 100 条（构造用例） | 对照测试 + 集成 | FR-84 | §8.8 |
| AC-V2.18 | venue | venue 浏览 | 抽样 venue 的卷期目录与 Crossref 按 ISSN 枚举的结果一致（沿用 01 AC-V2.18 与 v1 AC-3.5 口径） | 集成（fixture） | FR-44 | §10.6 |
| AC-V2.15 | 本地检索 | 新作品可检时效 | 新作品在 `index` 段完成后，≤2 min [判断] 即可被 LATEST 与分面检索命中，即使某个 API 进程的位图同步滞后（水位尾部补查兜底） | 集成 | FR-36、NFR-12 | §9.4 |
| AC-V2.8 | 本地检索 | 软检索文本语义 | 构造用例中，稠密通道召回的、不含全部查询词的相关作品能进入 SEARCH 结果；`rank` 为 recency、cites、issue、personal 时，裸词编译为硬 AND 门并以"须包含"筛选条呈现（100%）；频道中的裸词一律为硬谓词 | 单元 + 集成 | FR-35、FR-42 | §3.2 |
| AC-V2.29 | 路由 | 范围完整性 | 构造用例：查询限定在完整收割的 venue 或 arXiv 类目内、只涉及标题与元数据条件时，联邦触发率为 0（100%）；完整区间不覆盖查询窗口，或涉及摘要而摘要可检索率 <0.9 时，改按 cov_local 与 n_local_T 判断（100%） | 单元 + 集成 | FR-37、FR-38 | §6.3、§10.3 |
| AC-V2.23 | TSRG | 素描无偏 | 仿真：本地语料对某主题的真实覆盖从 0.1 增长到 0.9 的过程中，≥95% 的节点满足 \|cov̂_local − cov_true\| ≤ 0.1（约 3 倍 M=256 的抽样标准误）；样本框中不出现"只因已在本地才被抽中"的作品（构造检查：抽样作业不读 `corpus` 表） | 仿真 + 静态检查 | FR-41 | §5.3 |
| AC-V1.12 | 合规 | 未启用来源零出站 | 出站审计中：审核通过前指向新来源主机的请求为 0（先验作业与成员探测均计入，FR-29、R2-23）；NCBI 书面确认登记前指向 `eutils.ncbi.nlm.nih.gov` 的请求为 0（R2-13）；OpenReview 书面确认前平台侧共享收割请求为 0（R2-20） | 集成（审计日志） | FR-29、NFR-14 | §6.3、§6.10、§11.1 |
| AC-V2.43 | Percolator | 已有作品的重新匹配 | 构造用例 100%：已有作品新增版本或匹配字段变更后，`first_public` 在 30 天内的新命中写入 FeedInbox；窗口外的旧作品不写入，但在频道列表视图可见；已推送过的 (用户, 作品) 不产生第二条 FeedInbox 条目，也不在 Deck 中再次出现；`merge` 不产生推送；批次按 `index_seq` 区间登记，重放零重复（R2-35） | 仿真 | FR-40、NFR-12 | §12.1、§12.5 |
| AC-V3.11 | 调度 | 细粒度收割键 | 作者与引文邻域锚点：不同用户数 < `k_cf` 时，`ops.watch_key` 中无对应键，出站审计中无对应上游请求（100%）；达到 `k_cf` 后的下一次编译建键；降到 `k_cf` 以下后按宽限期退役（R2-19） | 仿真 + 集成 | FR-40、NFR-15 | §11.1 |
| AC-V2.3 | 接口 | 错误与降级契约 | §3.7 的四类错误码与降级在契约测试中 100% 按定义返回；降级场景返回 200 且完整性报告写明原因；重复提交同一查询得到同一 `query_hash` 与同一计划（快照版本不变时） | 契约 | FR-34、FR-38 | §3.7、§8.3 |
| AC-V2.28 | 路由 | 路由输入与个人数据无关 | 两名已见集合、画像与私有文献都不同的用户提交同一规范查询（含相同的 `Personal` 文字）时，在同一快照与同一在线状态的确定性回放中，RoutePlan 的端点集合与写入 `ops.route_decision` 的 π、特征与 η 观测逐字段相同（100%）；p_r、`n_local_T` 与 T 的输入列表不含 `private` 列表与个性化重排（构造用例 100%） | 集成 + 静态检查 | FR-41、NFR-15 | §5.3、§6.2、§6.3、§15.3 |
| AC-V0.13 | 合规 | 许可门禁 | 默认构建与默认配置中，§1.6 列为"不采用"或"可选"的依赖、模型与数据出现 0 次（可选项须显式开关）；标 ⚠ 的项在启用前都有核验记录；CE 与嵌入模型的配置项只接受登记过许可的模型标识（依赖清单与模型配置扫描） | 静态检查 | NFR-23 | §1.6、§8.7、§9.3 |

---

## 18. 与 v1 的关系与迁移

### 18.1 模块与文档

| v1 资产 | v2 处置 | 说明 |
|---|---|---|
| `subs/types.py`（`parse_arxiv_query` 语法树） | 复用于迁移工具 | 作为兼容解析器，把 v1 布尔式翻译为 v2 AST（§3.8） |
| `subs/filter.py`（`filter_papers`、`PREDICATE_REGISTRY`、"字段缺失→原子 False"） | 作为语义基准 | v2 在 closed_world 模式下重新实现同一语义；v1 代码只在测试中作 oracle（AC-V2.2）。`Regex` 沿用同一求值引擎（Python `re`），不交给 PG 正则（§3.3、§3.8） |
| `subs/compile.py`（每源下推 + 本地补偿） | 由本文取代 | 推广为能力感知的健全放宽编译器（§7）。v1"下推尽可能多，正确性以本地过滤为准"的原则（design/09 §3）原样保留 |
| `subs/watermark.py`（DateCursor / IdSetDiff / 重叠窗口） | 改造复用 | 成为 WatchKey 的水位策略（§11.5），经 03 的 `v1_bridge` 接入 |
| `subs/guard.py`（`max_new_per_run` 熔断） | 改造 | 频道 `daily_cap` 加过载报告（§12.6） |
| `subs/watch.py`、`subs/report.py` | 由 WatchKey 调度器、FeedInbox 与 06/07 的摘要取代 | v1 代码冻结（B-03） |
| `ratelimit.py`、`http.py`（按域令牌桶、多方声明取最保守值、Retry-After、挑战冷却） | 改造为出站网关 | 保留"取最保守值"与挑战即 BLOCKED；新增响应头驱动、AIMD、重试预算、按"源×端点"熔断、舱壁（§13） |
| design/05 §4 错误分类学 | 复用 | 用于网关的错误分类与熔断计数口径（§13.3–13.4） |
| FTS5 `paper_fts`、`repo.search_papers`、`crawler search/reindex`（D-034） | v1 冻结；v2 取代 | v2 用 pg_textsearch（BM25）加 tsvector/GIN（谓词）。沿用两条原则：D-034 决策 6 的"查询面单点封装"，以及 `--check` 的"与源表对账"（§9.9） |
| `merge.py` 与 dedupe 聚合（D-007、D-031、D-036 与 T13 的折叠语义） | 语义复用 | 折叠只在结果集内发生；代表行按确定性规则选取；弱信号不自动合并（§8.5） |
| adapter `capabilities()`（D-002） | 由 03 的 SCD 细化 | 04 只消费 SCD |
| design/09-search-filter.md（implemented） | v2 中由本文取代其设计职能 | v1 文档保持 implemented，v1 冻结代码仍按它运行；兼容映射见 §3.8 |
| design/05 §3 的优先级分层（D-039 defer） | v2 以三道舱壁实现 | 见 §13.5 与 ADR 候选 4 |

### 18.2 与既有 ADR 的关系

- **D-005**（元数据主干）：一致。OpenAlex 从 v1 的 enrich-only 升级为"快照驱动的覆盖面主干 + 预算内 API"（OSS §3-4），即 TSRG 统计与联邦候选。
- **D-007**（Identifier 图，预印本与正式版不合并）：延续。v2 由 03 物化 `cluster_id`，04 做查询期折叠。
- **D-014、D-026、D-030**（诚实 UA 与 robots、robots 路径级最长匹配、CF-403 挑战与冷却）：延续。它们在出站网关的 robots 闸与 POLICY_BLOCKED 态中落地。
- **D-029**（SSRN 元数据经 Crossref 前缀）：延续。SSRN 的 network/eJournal 分类不可得，v1 相应订阅迁移为 `needs_review`。
- **D-034**（FTS5；决策 6 规划的 PG 路径为 tsvector 生成列 + GIN）：v2 保留 tsvector/GIN 作谓词层，另加 pg_textsearch 作 BM25 排序层。这是对决策 6 的实质修订，**须新 ADR 点名修订 D-034 决策 6**。
- **D-037**（dblp 出列）：延续。TSRG 不含 dblp 在线端点；CS venue 的历史主干改经 DROPS 快照（03）。
- **D-039**（优先级队列 defer）：v2 多用户场景下须分道，**须新 ADR 在 v2 范围内取代 D-039 的 defer**。v1 维持原状。

**ADR 候选**（编号由 09 分配，状态 proposed）：
1. **TSRG 作为统一索引结构**：同一张图服务路由、调度、兴趣挂点、反向推送（简报 §7-7）。
2. **Query AST v2 与用户频道取代 v1 订阅**：含 closed_world 兼容模式与迁移规则，以及裸词在即席检索中为软检索文本、在频道与非相关性排序中为硬 AND 门的语义（§3.2）。
3. **检索索引选型**：pg_textsearch（BM25）+ tsvector/GIN（谓词）+ `halfvec` HNSW（维度随 Q7 的选型，§9.3、§19-15）；修订 D-034 决策 6。
4. **出站网关、全局配额账本与三道舱壁**：P-04 与 HC-10 的实现形态；在 v2 范围内取代 D-039 的 defer。
5. **共享索引资格规则**：明确 B 类摘要默认纳入的前提、开关与可逆重建。也可以并入 08 的权利 ADR。

### 18.3 数据迁移

- **v1 订阅**：本地库有 2 个订阅（RT v1-db-count），外加 9 个预置包。迁移工具逐一翻译为频道（closed_world 模式）；SSRN 分类项进入 `needs_review`。
- **v1 论文**：本地库 179 篇，走 05 的 ETL。BM25、tsvector、向量、`cluster_id`、`route_stat` 都在 PG 侧重建，不搬运（RT §10.7）。
- **v1 CLI**：`crawler search` 随 v1 冻结（B-03），用户改用 v2 的 API 与界面。

---

## 19. 异议与备选

以下各条均附证据，交主 agent 复核。第 1、2、3、7、8 条是对简报或调研的精确化，不改变裁决方向。第 5、6 条是术语层面的澄清。第 4、9、10、11 条引入了新的约束或默认值。第 12 条记录一项已知代价。第 13–15 条由早先的可行性评审补入：第 13 条扩展了简报的四意图，第 14 条细化简报 §5、§6.4-5② 中 Percolator 的执行节奏，第 15 条是与 02 A-6 的口径冲突。第 16、17 条由第 2 轮裁决之后的 FEAS 评审补入。第 18 条由其后的 EVID 评审补入，是对 R2-21 的风险提示。

**第 2 轮裁决（简报 §10）后的状态**：第 1、7 条已由 R2-38 采纳；第 4、8 条已由 R2-39 采纳；第 5、10 条已由 R2-40 采纳；第 6 条已由 R2-02 定名；第 11 条已由 R2-21 采纳（法务结论仍待 LQ-02）。第 2、3、9、12 条是对调研的更正或已知代价，简报未另作裁决，按本文执行。第 13、14、15 条简报 §10 未涉及，仍待主 agent 确认。第 16、17 条是对 R2-38、R2-19 的细化，请主 agent 确认。第 18 条请主 agent、08 与法务裁定。

1. **近似保证的具体表述**（简报 §6.2-2 写作"常数近似"）：
   - 本文给出具体常数：可证 ≥(1−1/e)/2，Tang 等证明 ≥0.405，上界 0.42945。
   - 给出适用条件：单调次模、成本可加、f 在素描上求值。
   - 给出在线与离线分工：候选 ≤10 时在线精确枚举；离线用 ≤3 元种子部分枚举达到 (1−1/e)。
   - 证据：§6.7 所列一手来源。
   - 备选：所有查询都用部分枚举。代价 O(n⁵)，不适合在线，不采纳。
2. **延迟不能作为背包成本**（RT §3.5.2 伪代码把 `w_lat·p95` 放进 cost）：
   - 理由：并行 fan-out 下延迟取 max 而非和，不满足可加性，近似保证随之失效。
   - 本文改为可行性约束加截止时间传播；顺序替补链里延迟可加，只用于链内排序（§6.5）。
   - 备选：保留标量化，但失去近似保证，不采纳。
3. **放宽规则的三处更正**（RT §3.5.3 表格）：
   - 邻近退化为短语不健全：邻近不蕴含相邻，应退化为 AND；
   - 负文字的字段泛化、短语弱化不健全：¬ti:x 不蕴含 ¬any:x；
   - 跨分类体系转译不是健全放宽，只能作为标注的近似。
   
   证据：§7.3 的引理与 §7.4 的规则表；§7.6 把这些错误变换列为属性测试的固定反例。
4. **cross-encoder 重排 top-100 在纯 CPU 上的可行性**（简报 §6.2-4）：
   - 按 FLOPs 估算，0.6B 级重排器在纯 CPU 上对 100 对样本约需数十秒，远超 800 ms 预算（§8.7 [估算]，吞吐为假设值）。
   - 本文把"top-100"改为上限：小模型、int8、输入截断；有 GPU 时才启用大模型；超出预算时改为延后的 `upgrade` 事件。
   - 备选：只做离线的 LLM listwise 重排（P-07 允许），但它不服务即席检索。
5. **用户标签不能作为共享 TopicNode 的叶子**（简报 §5 TopicNode 定义含"用户标签"）：
   - 依据 P-02 的派生继承最严规则，用户标签属于 per_user 数据。
   - 本文改为 usr 域覆盖层（RLS），不进共享快照，也不参与全局统计（§5.1）。
   - 建议 01 在术语表中注明。
6. **"Channel"一词的冲突**（简报 §5）：该词同时指 SourceSpec 的三个通道与用户频道。R2-02 已裁定：前者称 SourceChannel（来源通道，标识符 `source_channel`），后者称 Channel（频道，标识符 `channel`）。本文已按此对齐，此条仅作记录，无需再裁。
7. **Thompson sampling 与近似 oracle**（简报 §6.2-2）：
   - Wang 与 Chen 指出，组合 Thompson sampling 的保证依赖精确 oracle，不能直接换成近似 oracle（§6.8）。
   - 本文：候选 ≤10 时用精确枚举作 oracle；候选 >10 时，TS 只作有预算上限的启发式探索，并用离线回放监控。
8. **性能口径**：
   - 简报 §3 的"本地检索 p95 ≤800 ms"是端到端口径；SI-27 的"检索 p95 >300 ms 触发升级"是单路召回口径。
   - 本文分别定义，避免误触发或漏触发（§14.2、§14.4）。
9. **pg_textsearch 不承担谓词求值**：
   - RT 对它的记录中未见短语或布尔能力 ⚠。本文让 PG 原生 tsvector/GIN 承担谓词，pg_textsearch 只做排序；代价是词法索引体量约翻倍 [估算]（§9.2）。
   - 备选 A：只用 tsvector + `ts_rank_cd`，放弃 BM25，排序质量下降。
   - 备选 B：ParadeDB，AGPL，只能作可选组件（B-06）。
   - 实现期若证实 pg_textsearch 支持短语与布尔，并且分析器与 tsvector 一致，可以取消 tsvector 这一层。
10. **路由不使用个人画像**（§15.3）：
    - 理由：P-02、缓存复用、可复现。
    - 备选：个性化路由，但把它的日志与全局学习隔离。实现复杂，且牺牲跨用户的缓存复用，不采纳。
    - 06 如需"按用户兴趣扩展联邦范围"，请在 06 中提出，由主 agent 裁定。
11. **B 类摘要默认进入共享索引**（LQ-02 未决）：
    - 默认纳入，同时保留开关与定向重建能力（§9.1）。
    - 证据：
      - Crossref 摘要对心理学与多家出版方为 0（AG §2.6），排除 B 类会使这些学科的语义检索与主题标注严重退化；
      - CP 对此的判断为"⚠ 可用于内部索引和嵌入"（CP §2.3）；
      - 美国有支持"索引 + 有限片段"的先例（◐）；欧盟法下出版方 TDM 保留的问题见第 18 条。
    - 备选：保守地默认关闭。
    - 须 08 与主 agent 裁定，并列入法务优先问题（G-02）。
12. **LATEST 恒不联邦的代价**：
    - 最新论文的时效受收割节奏约束，例如日历型源须等到公告之后。
    - 本文用"按需刷新"只提升收割优先级（§11.6），并在结果中展示数据时点。
    - 备选：对刷新开放查询时联邦。这违背 P-01，且会随用户数放大上游请求，不采纳。
13. **EXPAND 独立成第五意图**（简报 §6.2-1 规定 LOOKUP/SEARCH/SIMILAR/LATEST 四意图）：
    - 01 §16-5 把"EXPAND 是否独立成意图"交由本文决定（01 待决第 12 项）。RT §4.3.1 与 SI-24 也列为五意图。
    - 理由：EXPAND 的执行路径与另外四个意图都不同。本地走引文图 ≤2 跳（§9.7）；远端只有具备引文关系过滤能力的端点可参与（§6.3 第 4 条）；默认排序是图分。若并入 SEARCH，路由的能力检查、默认排序与筛选条都要按"是否含 `Rel` 原子"特判。
    - 备选：把 EXPAND 并入 SEARCH，用 `Rel` 原子表达。结果集合相同，但特判散落各处，不采纳。
    - 影响：01 的 FR-34 标题"四意图"与 AC-V2.2 的意图口径须同步。
14. **Percolator 的执行节奏**（简报 §5："新论文入库时反向匹配全部频道与兴趣画像"；§6.4-5②："Percolator 按节点倒排与用户质心点积找读者，在每用户日预算 + 每篇曝光下限约束下分配"）：
    - 本文保留"三路候选由 04 定义、打分与分配由 06 负责"的分工。频道命中仍是近线微批；节点与质心两路改在日批执行（§12.1）。
    - 证据：06 §11.3 的分配以"每用户日预算 + 曝光下限"为约束（R2-41 之后下限只对资格集合生效，受 ≤5% 期望曝光的全局预算约束），贪心与最小费用流都以当日全部供给为输入。切成 10 分钟微批逐批贪心，当天早到的论文会先耗尽预算，这是在线 b-matching 的短视问题。02 P11 与 06 §8 已把兴趣反向推送定为夜间作业，本文原稿与之冲突。
    - 备选：保留近线微批，另加按日预算的节奏控制，例如按到达率为每个用户预留逐时额度。可行但复杂，收益只是兴趣推送早于次日可见；而显式订阅（频道命中）已经是近线的。不采纳。
    - 须主 agent 确认：简报 §5 所说的"Percolator"覆盖"近线频道命中 + 日批兴趣反向推送"两档。
15. **稠密索引维度**（SI-40 写"统一存 256 维"；02 §2.11 A-6 写"检索用 1,024 维、推荐用 256 维"；本文原稿写统一 256 维）：
    - 256 维的依据是推荐任务上的结论（Scholar Inbox），以及 Qwen3、OpenAI 模型支持 MRL 截短（SR §3.1-3）。Q7 候选中的 gte-large 与 SPECTER2 未见 MRL 截短的记载，截到 256 维对检索质量的影响 ⚠ 未评测。
    - 本文改为：索引维度随 Q7 的选型而定。支持 MRL 时用 256 维索引加全维精排；否则用全维索引，降维须经 V1 的分学科评测证明无损（§9.3）。两种情形的内存与延迟都在 T1 硬件范围内（§14.3）。
    - 备选：一律 1,024 维（02 A-6）。检索质量有保障，但若最终选 Qwen3，HNSW 内存约为 256 维方案的 3 倍。
    - 须主 agent 在 02、04、05 之间统一口径（05 `corpus.embedding_model.purpose` 已按 02 写作"检索 1,024 维"）。
16. **在线精确枚举加规模闸**（R2-38："在线精确枚举，离线部分枚举"）：
    - 细化：候选 ≤10 时，只有枚举规模 2ⁿ·K·P ≤ 2²⁰ 才在线精确枚举，否则用"比值贪心 + 最佳单源"（§6.4 第 6 条）。
    - 证据：原稿按"一次 2ⁿ × n × K·P 的对数域矩阵乘约 3 ms"估算最坏情形，漏掉了结果矩阵逐元素求 exp（n=10、K·P=8,192 时约 8.4×10⁶ 次）与约 67 MB 的中间矩阵，实际为数十毫秒，冲破 5 ms 的路由预算（§5.6）。改为乘积域逐层倍增后不再需要 exp，但峰值内存仍与 2ⁿ·K·P 成正比，所以要设闸。
    - 影响：闸外的查询失去"素描上最优"，保证退回 ≥0.405 · g(OPT)；TS 在这些查询上只是启发式探索（§6.8）。学术源的成员模式高度集中，预计多数 n ≤10 的查询仍在闸内，比例由 AC-V2.26 报告。
    - 备选：把枚举放到 C 扩展或按列分块流式求值，内存降到 O(n·K·P)，可以取消规模闸。实现成本高于收益，V1 实测若闸外比例高再考虑。
17. **细粒度收割键的 `k_cf` 门槛扩到频道与关注**（R2-19 原文："由私有文献库派生的细粒度键"）：
    - 细化：作者与引文邻域锚点无论来自私有文献库、频道还是"关注作者"，都要 ≥`k_cf` 个不同用户共有才建平台 WatchKey（§11.1）。
    - 理由：单个用户的频道锚点同样会以 WatchKey 的形式出现在 ops 域，并变成上游可见的、指向特定作者的规律性请求，泄露面与库派生的键相同。
    - 代价：只有少数人关注的作者，其新论文要靠基础收割或本人触发的按需查询才能到达，时效变差。
    - 备选：按 R2-19 字面只管库派生键，频道与关注的作者键照常建。泄露面更大，不采纳；若主 agent 认为频道属于用户主动表达、可以放宽，本条可撤回。
18. **B 类摘要遇到出版方的自然语言 TDM 保留**（R2-21："B 类摘要默认纳入词法索引与嵌入"）：
    - 证据：CP §2.3.2 指出，欧盟 DSM 第 4 条的一般 TDM 例外在权利人"以适当方式明示保留"时不适用，SN、Elsevier 已在条款中作出保留。汉堡高等法院 2025-12-10 认定网站条款中的自然语言保留不满足"机器可读"，但该案已上诉至德国联邦最高法院，截至调研日未见裁判（CP 标 ◐）；CP 的设计建议是不依赖这一判例，把自然语言保留也当作有效保留。本文原稿只排除带机器可读保留（TDMRep、Content-Signal）的 B 类摘要，等于默认依赖了该判例。
    - 影响：照 CP 的建议执行，Elsevier、SN 的 B 类摘要要退出共享词法索引、嵌入与 CE 输入。Elsevier 在 Crossref 的摘要覆盖为 0（AG §2.6），心理、金融等学科的检索会明显退化，§10.3 的 JFE 例子也会因摘要可检索率不足而改走联邦。
    - 本文处置：暂按 R2-21 默认纳入，在 §9.1 单列一行并标 ⚠；由权利引擎的字段级标签区分保留类型，保证裁定后可以按 `input_rights_max` 的同一机制定向重建。
    - 备选 A：按 CP 的建议立即排除。合规风险最低，代价是上述学科的检索质量。备选 B：只在涉及欧盟的部署或地区单元中排除（借用 HC-21 的地区开关）。
    - 须主 agent、08 与法务裁定（LQ-02、LQ-17），并确认 R2-21 是否需要补充。

---

## 20. 待决问题

| # | 问题 | 影响 | 默认假设或处置 | 负责方 |
|---|---|---|---|---|
| 1 | LQ-02：B 类摘要能否进入内部索引与嵌入 | 共享检索的覆盖面 | 默认纳入，可逆（§9.1、§19-11） | 08 + 法务 |
| 2 | LQ-17：Content-Signal 与 TDMRep 如何映射到"索引、嵌入"用途 | 哪些出版方的 B 类摘要须排除 | 有机器可读保留者一律排除 | 08 |
| 3 | 简报 Q4 与 R2-13：robots 全禁与文档化 API 的冲突（NCBI、ORCID 等）；R2-13 的"确认后启用"是否也禁止 E-utilities 的低频、用户触发调用（03 §6.8 记为 on_demand 单个 PMID 补查） | PubMed 能否参与交互联邦与 PMID LOOKUP；确认前 PMID 替补链能否满足 P-09 的两级要求（OpenAlex 按 PMID 单查已于 2026-09-27 实测可用，PMID 链满足；PMCID 单查仍 ⚠，§8.4） | 按更严读法：NCBI 书面确认前不调用 E-utilities（§6.3 第 2 条、§8.4） | 主 agent；robots ADR（简报 §7-2）；03 同步 §6.8 |
| 4 | CORE 对检索与推荐类产品的许可 | OA 定位替补链的第三级 | 取得许可前停用 | 03、08 |
| 5 | S2 商用边界（LQ-08） | 商用开关打开后 S2 端点的去留 | 非商业默认可用，带署名 | 08 |
| 6 | 简报 Q3：是否购买付费档 | OpenAlex 联邦的成本上限 | 免费 key 加预算闸；触发条件见 §14.4 | 用户 |
| 7 | 简报 Q7：表示模型选型 | 索引维度；能否与 OpenAlex 语义检索同空间重打分；中文能力 | 索引维度随选型（§9.3、§19-15）；V1 做分学科评测后定型 | 06 |
| 8 | pg_textsearch 的分析器一致性与中文分词 ⚠ | 词法层 | 实现期实测；不一致时以 tsvector 为准 | 04 实现 |
| 9 | Europe PMC 的数值限速未公布 ⚠；`www.ebi.ac.uk` 对通用 UA 设 `Crawl-Delay: 10`（AG §2.2.10） | 生命科学联邦与 PMID LOOKUP 的交互容量：全平台每 10 秒至多 1 次，且与收割共用 | 按 Crawl-delay 限速（03 §4.4 已登记），响应头驱动；多用户上线前与 EBI 约定用量（LS §2.3.3）。约定前 EPMC 在交互道只承接低频请求，缺源时由 OpenAlex 承担（§8.4、§10.4） | 03、主 agent |
| 10 | 频道能否公开或在团队内共享 | ChannelRef 的可引用范围；公开频道的名称与说明属于 UGC | 本期只允许引用本人频道；若开放公开共享，须满足 HC-15 的 UGC 阶段条件（§15.1） | 01、06、08 |
| 11 | lenient/strict 默认值的用户接受度 | 检索与频道体验 | 检索默认 lenient，频道默认 strict | 07 的用户测试（G-01、G-07） |
| 12 | 覆盖全集估计的偏差 | 联邦判据 τ_cov 的可靠性 | 捕获—再捕获只作告警参考；上线后用穷举评测校准 | 04 实现 |
| 13 | 10⁵ 级频道下的 Percolator 成本 ⚠（综合 R-12） | 扩展性 | 压测后决定是否引入 OpenSearch percolate | 04、09 |
| 14 | arXiv 限流阈值不透明（CS §4-2） | 日历型收割的稳定性 | OAI 优先，RSS 兜底，发布窗内重试 | 03 |
| 15 | 检索日志的留存与用途：HC-14 要求日志保留，HC-20 要求最小化 | 学习数据的可用性 | 留存期限已由 R2-31 定（可识别 6 个月、假名化 13 个月）；路由学习去标识；检索历史用户可删（§15.4）。用途边界仍由 08 定 | 08 |
| 16 | OpenReview 平台服务账号（简报 §7-12） | CS 会议的最新通道 | 按 R2-20：书面确认前停用平台侧共享收割，ICLR、TMLR、COLM 等走 arXiv 版本 + DROPS dblp 快照 + 外链；V0 即发函（§11.1） | 03 + ADR |
| 17 | 频道版本历史：`@name#v` 钉版本、Percolator 批次复现 | ChannelRef 的可复现性 | 本期只引用当前版本，并记录 `ast_hash`；若需钉版本，请 05 增补不可变版本表 | 05 |
| 18 | FeedInbox 读取时跟随合并墓碑重定向 | 作品合并前后的 ID 重复出现 | 读取时先把 `work_id` 映射到存活作品再去重。列名已统一为 `push_reason`（05 §3.3.6），本文已对齐 | 05、06 |
| 19 | 02 的组件表把"WatchKey 编译"记在 03 名下 | 职责归属 | 已由 R2-34 裁定：算法由 04 定义，02 的 harvest scheduler 执行，03 的 connector 消费；02 组件表待随之修正（§11.1） | **已关闭**：02 §2.2、§2.3.7 已按 R2-34 改写（一致性审计） |
| 20 | TSRG 存储的剩余增补：`ops.coverage_sketch` 增列 `sample_ids` 与 `local_refreshed_at`；`work_search` 的 `index_seq` 水位列（§9.4）。窗口维、`fidelity` 与两张运维表已由 05 采纳 | 成员探测、本地位刷新与位图增量同步无法按 ID 对账 | 见 §5.4、§9.4 | **已关闭**：05 已有 `sample_ids`、`local_refreshed_at`；`corpus.work_search.index_seq` 由一致性审计补入 05 §3.1.9 |
| 21 | 02 §2.7(d) 与本文的执行器契约不一致：① SSE 事件名（`meta/local/rerank/supplement/done/refine_suggestion` 对本文 `snapshot/upgrade/append/source_status/done`）；② 02 流程图的合并顺序为"RRF → 残差 → 折叠"，本文为"列内折叠 → 残差 → RRF"，后者才能避免同一作品的多个版本在同一列表内重复计分（§8.5）；③ 02 的联邦意图集合为 {LOOKUP, SEARCH, SIMILAR}，本文为 {SEARCH, SIMILAR, EXPAND}，LOOKUP 走替补链不做选源 | 前后端契约、融合正确性 | 以本文 §8.2 的映射表与 §8.1 的顺序为准；07 已按本文消费 | ①② **已关闭**：02 §2.7(d)、§2.8.7 已按本文统一事件名与合并顺序（一致性审计）；③ LOOKUP 走替补链已写入 02，EXPAND 是否为第五意图仍待主 agent（§19-13） |
| 22 | 稠密索引维度（§19-15） | 内存、检索质量、05 表结构 | 随 Q7 选型；V1 评测后定 | 主 agent（02、04、05） |
| 23 | Percolator 的执行节奏（§19-14），以及 06 日批作业调用候选生成时的数据库角色（§12.5） | 兴趣推送的时效；最小权限 | 频道命中近线；兴趣反向推送日批，沿用 `pc_sys_percolator` 的列级授权 | 主 agent（02、05、06） |
| 24 | 05 §3.3.5 对 `evt.agg_route_eta` 的输入注释写作"独有结果进入 top-k"，须改为 §5.3 的"已知成员召回"计数；`ops.route_decision.results` 需含各端点按节点分列的已知成员数与成功数（§6.9） | η 若按独有贡献学习，重叠端点会被系统性低估，OpenAlex 失效时替补选错 | 按本文口径 | **已关闭**：05 注释已改为"已知成员召回"口径（一致性审计） |
| 25 | 06 §7.9 的挂点范围"04 的前 100 条结果"，在 LATEST 与频道视图中指质心预排的前 100 条（§8.8） | LATEST 个性化的覆盖面 | 按本文 §8.8 | 06 |
| 26 | 01 FR-34 的标题"四意图"与本文的第五意图 EXPAND（§19-13）；01 待决第 12 项可据此关闭 | 需求与设计一致 | 按本文 | 01 |
| 27 | R2-45 对查询解析的适用：查询文本是用户数据，R2-45 只放行"只处理开放内容的论文侧预处理"使用第三方 API | LLM 解析能否用第三方 API | 按更严读法：只用自托管模型，T1 默认关闭（§4.5） | 主 agent；08 |
| 28 | 06 §13.5 的 `np_time` 按"首见时间"排序，本文 LATEST 按 `first_public`（§3.5、§8.8） | 回填的旧作品会被当作新论文排前 | 按本文：LATEST 与频道视图用 `first_public` | 06 |
| 29 | 05 `ops.percolate_batch` 以 `work_id_lo/hi` 登记批次，R2-35 的已有作品重新匹配落不进 ID 区间 | Percolator 幂等与不遗漏 | 改为 `index_seq_lo/hi`（§12.5） | **已关闭**：05 已改为 `index_seq_lo/hi`（一致性审计） |
| 30 | 范围完整性所需的完整区间（§6.3、§5.5 `scope_complete_daily`）：由 `ops.harvest_run` 与 `ops.watch_key.watermark` 汇总；需要 03 的回填任务（EnumerateTask）按 venue、类目记录完成的时间窗 | 范围完整性能否判定；判定不了时退回素描，只会多联邦、不会漏结果 | 04 定义计算，03 保证 harvest 运行记录带范围与窗口 | 03、05 |
| 31 | 02 §2.8 的 `work.enriched` 事件与 R2-07 的出箱主题 `corpus.change` | Percolator 触发源的命名 | 按 R2-07 以 `corpus.change` 为准；近线档按 `index_seq` 取批（§12.1） | **已关闭**：02 §2.3.6、§2.7(c)、§2.9.2 已改为 `corpus.change` 与 `index_seq` 水位（一致性审计） |
| 32 | 细粒度收割键（作者、引文邻域）在达到 `k_cf` 之前的计数载体：`usr.channel_watch` 外键指向 `ops.watch_key`，无法先建行 | R2-19 门槛能否落地 | 未达门槛的键以带密钥的哈希存在本人 usr 行，调度器按哈希数不同用户（§11.1）；须 05 增补存放列 | **已关闭**：05 新增 `usr.watch_key_pending(key_hmac)`，`pc_sys_scheduler` 只读哈希列（一致性审计；明文建键由本人上下文作业完成） |
| 33 | Crossref `works_query` 是否作为交互 SEARCH 端点：03 §4.1 把它登记为交互道 SEARCH 端点；AG §2.2.1、§2.4 R6 的结论是关键词检索不打 Crossref，`query.bibliographic` 只用于引文串匹配；SI-02 要求不用关键词查询打列表池 | SEARCH 的候选集合；列表池（polite 3/s）的占用 | 本文建议 SCD 不为 `works_query` 声明 SEARCH，只保留 LOOKUP 标题匹配链的末级（§6.12、§8.4）；目标函数与影子价格已使它极少被选，改动不影响现有示例 | 03、主 agent |
| 34 | B 类摘要遇到出版方的自然语言 TDM 保留（SN、Elsevier）时，是否排除出共享索引、嵌入与 CE 输入（CP §2.3.2；§19-18） | 心理、金融等学科的检索质量；欧盟法下的合规风险 | 暂按 R2-21 默认纳入，标注保留类型，可定向重建（§9.1） | 主 agent、08、法务 |
| 35 | GBDT 路由器的训练集经聚合闸抽取（§6.9）：`pc_sys_aggregator` 在 `day_token` 置空前，按"意图 × π 首节点"格子的 `k_cf` 门槛抽取到 `archive/train/`。需要 05 在 §3.4 ⑩ 与 §4.1 写明抽取规则，08 确认它满足 HC-01 与 CP M19 的"聚合、去标识"（05 §16 第 8 项） | 路由学习的合规性与样本量 | 按本文执行；样本不足时推迟 GBDT 升级（§14.4） | 05、08 |
| 36 | 许可待核 ⚠：JEL、EconBiz STW、ACM CCS 的再分发许可；SciRepEval 数据集许可；小型 CE 的 MS MARCO 训练数据条款（§1.6） | B-06 门禁 | 内置或默认启用前逐项核验；未核清的不进默认配置（AC-V0.13） | 04 实现、08 |

---

## 21. 参考

### 21.1 调研文档（2026-09-26 对抗式核验）

- [调研综合](../../survey/00-survey-synthesis.md)：§2.2、§6.1（SI，承接对照见 §1.1）、§6.2（HC，对照见 §1.5）、T4/T9/T13/T14、§7、§8
- RT：[检索、路由、索引与数据平台](../../survey/algorithms/retrieval-routing-indexing.md)，全文
- AG：[聚合与仓储](../../survey/sources/aggregators-repositories.md)，§0、§2.2.1（Crossref 分池与"关键词检索不走 Crossref"）、§2.2.2（OpenAlex 的 `sample` 等查询参数）、§2.2.3（S2 端点、排序键与过滤）、§2.2.4（Unpaywall 并入 OpenAlex）、§2.2.10（Europe PMC 的 Crawl-Delay）、§2.2.11（PubMed 的启用前提）、§2.3、§2.4（R6、R7、R11 等路由行）、§2.6、§3（含第 11 条 S2 推荐不能支撑多用户实时）
- OSS：[获取与检索开源](../../survey/oss/paper-acquisition-and-search-oss.md)，§2.3.1、§2.4.1、§2.5、§2.12、§3
- SR：[学术推荐与匹配](../../survey/algorithms/scholarly-recommendation-and-matching.md)，§2.8、§2.10、§2.11、§3.1、§3.3
- CS：[计算机与 AI 来源](../../survey/sources/cs-ai.md)，§2.1.1（arXiv DOI 由 DataCite 注册）、§2.6（含 §2.6.1 的周量）、§3
- LS：[生命科学与心理学来源](../../survey/sources/life-sciences-psychology.md)，§2.2.1（bioRxiv 200 空体）、§2.3.3（Europe PMC 字段、Crawl-Delay 与用量约定）、§3
- SS：[经管社科来源](../../survey/sources/social-sciences-econ-fin-mgmt.md)，§3（含第 6 条路由三主轴、第 10 条名录许可）
- NS：[理科来源](../../survey/sources/natural-sciences.md)，§2.3.5、§3
- PU：[论文理解与卡片内容](../../survey/algorithms/paper-understanding-and-card-content.md)，§2.4
- CP：[多用户合规](../../survey/compliance/multi-user-platform-compliance.md)，§2.1、§2.2.3（LLM 输入与输出义务）、§2.3（含 §2.3.2 的 TDM 保留、§2.3.5 的共享缓存边界）、§2.4、§2.7（M1–M25）、§3.1（HC）、§4.1
- MK：[市场与初创](../../survey/market/startups-and-products.md)，I-2、I-14、I-15
- UX：[卡片流交互](../../survey/ux/card-feed-interaction.md)，§2.6.5；核验表第 30 行（OpenAlex 按 `doi:10.48550/arXiv.*` 单查的实测实例）

### 21.2 仓库内文档与代码

- [v2 设计决策简报](00-design-brief.md)，含 §10 第 2 轮裁决（本文已对齐 R2-01、R2-02、R2-03、R2-04、R2-05、R2-07、R2-08、R2-09、R2-11、R2-13、R2-14、R2-15、R2-16、R2-17、R2-19、R2-20、R2-21、R2-22、R2-23、R2-27、R2-28、R2-30、R2-31、R2-33、R2-34、R2-35、R2-38、R2-39、R2-40、R2-41、R2-45、R2-47、R2-49）
- v2 同批文档（2026-09-27 草稿）：
  - [01](01-vision-and-requirements.md)：FR-34…FR-44、FR-84，NFR-10、NFR-12…NFR-15，§14 术语；
  - [02](02-architecture.md)：§2.3 组件表（P3、P6、P11、P12、P13），§2.3.13 Egress Gateway；
  - [03](03-sources-and-corpus-pipeline.md)：SourceSpec v2、SCD、流水线；§6.2 策略模式全序与操作表、§6.8 robots 冲突清单、§10.7 出箱事件 `corpus.change`、§13.1 新来源审核；
  - [05](05-data-platform.md)：§3.1.5–§3.1.8、§3.2.4–§3.2.5、§3.4 的 DDL，§4 的角色与 RLS，§8 的容量；
  - [06](06-recommendation-and-matching.md)：§7.9 检索挂点，§11.3 论文→读者与 FeedInbox 写入语义；
  - [07](07-frontend-interaction.md)；
  - [08](08-compliance-security-privacy.md)：§2.2 的 HC 登记表（含新增 HC-29…HC-32）、§10.6 的许可四级口径（R2-01）；LLM 的"地区 × 数据类"路由（B 类摘要只进自托管模型）。
- v1 设计：[09-search-filter](../../archive-v1.md#docs-design-09-search-filter-md)、[05-pipeline](../../archive-v1.md#docs-design-05-pipeline-md)、[06-data-model](../../archive-v1.md#docs-design-06-data-model-md)
- [决策日志](../decision-log.md)：D-002、D-005、D-006、D-007、D-014、D-021、D-026、D-029、D-030、D-034、D-037、D-039
- v1 代码（语义基准）：`src/paper_crawler/subs/{types,filter,model,compile,watermark}.py`；v1 预置包 `subscriptions/presets/*.yaml`（其 `title_regex_any` 与 `exclude_regex` 普遍使用 `\b`，§3.8）

### 21.3 一手来源（本文补查，2026-09-27 查阅）

- Khuller, Moss, Naor. *The budgeted maximum coverage problem*. Information Processing Letters 70(1):39–45, 1999. DOI 10.1016/S0020-0190(99)00031-9（DOI 经 RT 核验）。"部分枚举 k≥3 达到 (1−1/e)，且除非 NP ⊆ DTIME(n^{O(log log n)}) 不可改进"的表述，经 https://en.wikipedia.org/wiki/Maximum_coverage_problem 与 arXiv:2202.03093（VDLS 论文的相关工作一节）复述核对，原文未直读。
- Krause, Guestrin. *A Note on the Budgeted Maximization of Submodular Functions*. CMU-CALD-05-103, 2005（2011-11-15 修订）. https://snap.stanford.edu/class/cs224w-readings/krause05note.pdf 。已直读：纯比值贪心的近似比无界；"贪心 + 最佳单元素"的推导；误差版本。
- Tang, Tang, Lim, Han, Li, Yuan. *Revisiting Modified Greedy Algorithm for Monotone Submodular Maximization with a Knapsack Constraint*. ACM SIGMETRICS 2021. https://arxiv.org/abs/2008.05391 。已读摘要：0.405；此前的 0.357（Wolsey）与 (1−1/e)/2（Khuller 等）；补上了 (1−1/√e) 的证明缺口。
- Kulik, Schwartz, Shachnai. *A Refined Analysis of Submodular Greedy*. 2021. https://arxiv.org/abs/2102.12879 。已读摘要：该算法近似比的上界为 0.42945。
- Sviridenko. *A note on maximizing a submodular set function subject to a knapsack constraint*. Operations Research Letters 32(1), 2004。经 Krause–Guestrin 与 Kulik 等的摘要引述，⚠ 原文未直读。
- Wang, Chen. *Thompson Sampling for Combinatorial Semi-Bandits*. https://arxiv.org/abs/1803.04623 。已读摘要：近似 oracle 不能直接替换精确 oracle。
- Whang, Brower, Shanmugasundaram, Vassilvitskii, Vee, Yerneni, Garcia-Molina. *Indexing Boolean Expressions*. PVLDB 2(1):37–48, 2009. DOI 10.14778/1687627.1687633. http://www.vldb.org/pvldb/vol2/vldb09-83.pdf 。经检索结果核对书目与摘要。
- PostgreSQL 18 文档（第 1 轮可行性评审补查，2026-09-27 直读）：
  - §8.11.2 tsquery：`<N>` 是 FOLLOWED BY 的变体，N 指定两个词位之间的距离，`<->` 等价于 `<1>`。https://www.postgresql.org/docs/current/datatype-textsearch.html
  - §12.3.2：`phraseto_tsquery` 用 `<N>` 为被去掉的停用词占位。https://www.postgresql.org/docs/current/textsearch-controls.html
  - §12.4.1：`tsvector || tsvector` 把右段词位加上左段的最大词位。https://www.postgresql.org/docs/current/textsearch-features.html
  - §9.7.3 表 9.20 与表 9.22：ARE 正则中 `\b` 为退格符；词边界约束为 `\m`、`\M`、`\y`、`\Y`。https://www.postgresql.org/docs/current/functions-matching.html
- OpenAlex API 实测（第 2 轮 EVID 评审，2026-09-27；匿名请求、诚实 UA，先读 `api.openalex.org/robots.txt`，其内容为 `Allow: /`；共 2 次请求）：`GET /works/pmid:16060722` 返回 200，得到 W2144981148（DOI 10.1371/journal.pmed.0020124），响应头 `x-ratelimit-cost-usd: 0`；`GET /works/pmcid:PMC1182327` 返回 404，该作品的 `ids` 中没有 pmcid，所以不能据此判断 PMCID 单查是否受支持（§8.4）。
- 许可核对（第 2 轮 EVID 评审补查，2026-09-27 查阅，用于 §1.6、§8.7、§14.1）：
  - GitHub 仓库元数据（`gh api repos/<owner>/<repo>` 的 license 字段）：scipy/scipy 为 BSD-3-Clause；microsoft/LightGBM 为 MIT；dmlc/xgboost 为 Apache-2.0；allenai/scirepeval 为 Apache-2.0（只指代码）；Qiskit/rustworkx 为 Apache-2.0（与 RT 一致）。
  - HypothesisWorks/hypothesis 仓库的 LICENSE.txt：MPL-2.0（GitHub 元数据显示 NOASSERTION，以文件正文为准）。
  - Hugging Face 模型卡与数据集页：Qwen/Qwen3-Reranker-0.6B 为 apache-2.0；cross-encoder/ms-marco-MiniLM-L6-v2 为 apache-2.0，约 2,270 万参数，训练数据标注为 sentence-transformers/msmarco；microsoft/ms_marco、sentence-transformers/msmarco 与 allenai/scirepeval 三个数据集页的元数据都未声明许可。

---

## 评审记录

第 1 轮（2026-09-27，视角 FEAS）在简报 §10 第 2 轮裁决之后执行。对照简报（含 R2-01…R2-50）、调研综合 §2.2 与 §6.1、RT 全文、AG §2.2.2/§2.2.11/§2.6/§3、OSS §3、SR 的兴趣树章节、CS/LS/SS 的路由建议、v1 `design/09`、`subs/{types,filter}.py`、D-034，以及 02、03、05、06 的现行草稿，逐项核对算法正确性、接口完整性、复杂度依据、R2 对齐与需求承接，并就地修订正文与两张配图（v2-04-tsrg.svg、v2-05-query-execution.svg）。此前一次可行性评审留下的修改（§19-13…15、§9.2 邻近编译、§3.8 正则方言等）已在正文中，当时未单独留记录。

本轮对齐的 R2 条目：R2-02、R2-03、R2-05、R2-07、R2-08、R2-09、R2-11、R2-13、R2-14、R2-15、R2-16、R2-17、R2-19、R2-20、R2-21、R2-22、R2-23、R2-27、R2-28、R2-30、R2-31、R2-33、R2-34、R2-35、R2-38、R2-39、R2-40（核对一致）、R2-41、R2-45、R2-47、R2-49。

用户原始需求 2 的承接核对：五类查询（查询、最新、筛选、多来源、组合）各有端到端示例（§10.1–§10.5）；多用户的自定义检索与偏好落在频道、已见、检索历史、来源偏好（§15）；"图/树算法、快速与并行查找、路由、准确率与稳定性"分别落在 TSRG（§5–§6）、LOOKUP 快路径与本地索引（§9）、并行联邦执行器（§8）、稳定性（§13）与评测（§14）。本轮补齐了其中的接口缺口（错误码、分页、版本）与几处落不了地的算法细节，未发现整条缺失的要点。

第 2 轮（2026-09-27，视角 EVID）核对合规与证据：逐条对照调研综合 §6.2 的 HC-01…HC-28 与 08 §2.2 新登记的 HC-29…HC-32；按 B-06 与 R2-01 核对依赖、模型与数据的许可；把正文的事实性断言回溯到 RT（全文）、AG §0/§2.2/§2.3/§2.4/§3/§4、CP §2.1–§2.7/§3.1、CS §2.1–§2.6/§3、LS §2.2–§2.3/§3、SS §3、SR §2.8–§2.11/§3.1、OSS §2.4–§2.5/§3、PU §2.4、UX 核验表，以及 03 §4、05 §4.1/§16、08 §2.2 的现行草稿；并检查综合 §6.1 中与本文相关的 SI 是否承接。调研没有记录许可的依赖、模型与数据集，本轮补查了一手来源（GitHub 仓库元数据与 LICENSE 文件、Hugging Face 模型卡与数据集页，以及 2 次先读 robots 的 OpenAlex API 实测，2026-09-27，列于 §21.3）。正文与两张配图（v2-04-tsrg.svg、v2-05-query-execution.svg）就地修订，配图经 XML 校验与无头 Chrome 渲染检查，无溢出与重叠。

本轮对齐或复核的 R2 条目：R2-01（新增 §1.6 许可门禁）、R2-04（GBDT 训练集的门槛取 `k_cf`）、R2-13（Europe PMC 在过渡期的实际交互容量）、R2-14（SN、ADS 不经平台网关）、R2-21（B 类摘要遇自然语言 TDM 保留，§19-18）、R2-30（核对一致）、R2-40（路由输入扩到个人谓词与私有列表）、R2-45（深度模式的 LLM 输入与 HC-12 措辞）。

| 轮次 | 视角 | 问题 | 严重度 | 处理 |
|---|---|---|---|---|
| 1 | FEAS | 覆盖素描的样本框未定义，且写有"本地样本"：从本地语料抽样会使本地位恒为 1、cov_local 恒为 1，联邦永不触发；季度快照也覆盖不了近 90 天 | 高 | 已修：`all` 用季度快照、`recent90` 每周经 OpenAlex `sample` 按 subfield 独立抽样，给出成本与偏差说明；`recent90` 的 cov 改取自素描（§5.3、§5.5）；新增 AC-V2.23 |
| 1 | FEAS | 精确枚举的"约 3 ms"估算漏掉逐元素 exp（约 8.4×10⁶ 次）与约 67 MB 中间矩阵，实际为数十毫秒，冲破 5 ms 路由预算；§5.6 说"f 只是乘加"与 §6.4 的对数域做法自相矛盾 | 高 | 已修：改为乘积域（贪心为矩阵–向量乘、枚举为逐层倍增，均无 exp/log/除法），加规模闸 2ⁿ·K·P ≤ 2²⁰；更新 §5.6、§6.4、§6.6、§6.11 与 AC-V2.24、AC-V2.26；作为对 R2-38 的细化写入 §19-16，转主 agent 确认 |
| 1 | FEAS | "比值贪心 + 最佳单源"的下界推导要求放不下的那个端点单独可行；影子价格可把单项成本推到预算以上，反例（成本 2B、比值最高）使推导链断开 | 高 | 已修：选源前剔除 c_s > B 的端点，§6.5、§6.6、§6.7 写明前提与反例，AC-V2.26 的 OPT 按剔除后的候选计算 |
| 1 | FEAS | §3.5 把软检索文本的本地结果定义为"全库前 N 条 ∩ where"，即后过滤；where 选择性高时召回塌陷，且与 §9.5 的先过滤规划矛盾 | 高 | 已修：改为各路召回在 where 约束下各取前 N_REC 条再并；AC-V2.11 加两类构造用例 |
| 1 | FEAS | 联邦判据只用主题素描的 cov_local，不看 venue/类目等硬范围；§10.3 自己的例子（三刊已完整收割）按公式会被误判为覆盖不足而联邦 | 高 | 已修：新增范围完整性 `scope_complete(q)` 与每日作业 `scope_complete_daily`，§10.3 按新规则重写；新增 AC-V2.29；所需的回填区间记录列 §20 第 30 项（03、05） |
| 1 | FEAS | §7.2 的无界判断只看 `Ps`，DNF 子句合并退化为 true 的子查询会漏判而下发无约束请求；`est_count`、`k_remote` 未定义；不按相关性排序的端点请求数按"取一页"计，实际须取完 | 高 | 已修：无界判断改在最终子查询上做，φ 与失配按实际下推的 `Pe` 计算；补 `est_count` 定义与 d_j 口径（§6.5）；§7.6 加回归用例 |
| 1 | FEAS / R2-27、R2-28 | §9.8 在服务端建 `usr.private_chunk` 需要私有全文明文，与 R2-27（platform 私有 PDF 默认只存设备、服务端私有处理默认关）冲突 | 高 | 已修：platform 部署的私有检索只在用户设备执行；服务端私有索引只在 personal 且 `host_is_user_device=true` 时可用；§2、§3.7、§15.4 与配图同步 |
| 1 | R2-13 | PubMed E-utilities 仍在 PMID 替补链、生命科学联邦候选、基础收割与降级矩阵里，与"NCBI 书面确认后启用"不符 | 高 | 已修：按更严读法，确认前不调用 E-utilities；PMID 链改为 EPMC → OpenAlex（按 PMID ⚠）；bioRxiv/medRxiv/PsyArXiv 改以 Crossref 为首选。03 §6.8 记为 on_demand 的差异与 P-09 两级要求转主 agent（§20 第 3 项）；新增 AC-V1.12 |
| 1 | FEAS / R2-35、R2-07 | Percolator 只处理新作品；微批按作品 ID 区间登记，重新匹配的已有作品（ID 小）落不进区间；触发事件名 `work.enriched` 与 R2-07 不符 | 高 | 已修：输入按 R2-35 扩到新增版本与匹配字段变更，加 30 天窗口护栏；触发源改为 `corpus.change`，按 `index_seq` 取批与登记；新增 AC-V2.43；05 列名改动转 §20 第 29 项，02 事件名转 §20 第 31 项 |
| 1 | FEAS | `plan_route` 对 LOOKUP 直接返回 local_only，替补链在执行器里从未被调用 | 中 | 已修：LOOKUP 分支在本地未命中时返回替补链任务（尊重 `scope.mode=local`），`execute` 注明链作为单个远端任务执行 |
| 1 | FEAS | 本地召回深度用了每页条数 k（20）：`ef_search = max(40, 2k)` 使稠密通道最多 40 条，与完整性报告的召回深度 100 不符 | 中 | 已修：引入 N_REC = 100，`plan_local(depth)`、`ef_search = max(N_REC, 2k)`，§3.5、§8.2、§9.3、§9.5 同步 |
| 1 | FEAS | 有界 GIN 探测在应用层与位图求交：常见短语先撞上 T_EXACT+1 上限，与罕见 venue 的小交集探测不到 | 中 | 已修：分面条件与 GIN 谓词写进同一条 SQL（BitmapAnd） |
| 1 | FEAS | 锚点倒排在 lenient 频道下会漏配：锚点字段缺失时文字为 U 而子句被接受，但键集合没有该锚点 | 中 | 已修：键集合加缺失伪键 `missing:f`，lenient 子句另挂在伪键下；AC-V2.42 加用例 |
| 1 | FEAS | `daily_cap`"只保留得分最高的条目"落不了地：频道命中 score 为空、近线微批、写入角色只有 INSERT | 中 | 已修：按 `index_seq` 先到先得，计数在进程内存、崩溃后重放重建；溢出报告在设置页对语料直接求值 |
| 1 | FEAS | 日批剔除"已有 channel_hit 的 (u, w)"要读收件箱，而写入角色没有 SELECT | 中 | 已修：日批以同一角色重放当日频道求值得到命中对；更新通知改由 06 按已见与文献库生成 |
| 1 | FEAS | 组合频道的编译缓存按自身 `ast_hash` 键控，被引频道修改后仍用旧谓词匹配 | 中 | 已修：缓存键改为内联后的规范哈希，被引频道修改时重编译并回看 |
| 1 | FEAS / R2-23 | 新源冷启动的样本记录与成员探测会在审核通过前向新来源主机发请求，违反 FR-29 | 中 | 已修：先验只用草稿、SCD 与经已登记来源取得的样本；探测等审核通过后执行；AC-V1.12 |
| 1 | R2-19 | WatchKey 编译没有细粒度键（作者、引文邻域）的 `k_cf` 门槛 | 中 | 已修：不足 `k_cf` 个不同用户时不建平台键，回填也不触发；未达门槛的键以带密钥的哈希在 usr 侧计数（存放列转 05，§20 第 32 项）；本文把频道与关注来源的同类键一并纳入，作为细化写入 §19-17，转主 agent 确认；新增 AC-V3.11 |
| 1 | R2-15、R2-16、R2-09 | 漂移处置一律"立即失效"；POLICY_BLOCKED 把 ToS 变化也算进去；策略结论读 05 派生的 verdict 词表，WatchKey 未按策略模式闸控 | 中 | 已修：分档处置（robots/TDM 立即，ToS 7 天宽限，`review_overdue` 30 天）；路由要求模式 ≥ on_demand、WatchKey 要求 background，直接用 03 的五档全序；AC-V1.2 加假时钟用例 |
| 1 | R2-22 | MSC2020 仍作默认叶子，节点数与快照内存按 4.45 万叶子估算 | 中 | 已修：MSC 改为默认不加载的插件，数学用 arXiv math + OpenAlex topics；节点数、质心与快照内存重算（§5.1、§5.6、§14.3），配图同步 |
| 1 | R2-45 | LLM 解析允许"经 08 放行"的第三方 API；查询文本属用户数据 | 中 | 已修：T1 默认关，只用自托管模型；从严读法转主 agent（§20 第 27 项） |
| 1 | R2-20 | 新鲜度阶梯的 L1 仍含 OpenReview 平台侧收割 | 中 | 已修：确认前停用平台侧共享收割，改走 arXiv + DROPS + 外链；§20 第 16 项更新 |
| 1 | FEAS | 接口缺错误码、AST 版本迁移、幂等与分页约定 | 中 | 已修：§3.7 增加错误与降级表、版本规则与幂等说明，§8.2 增加分页规则；新增 AC-V2.3 |
| 1 | FEAS | §7.4 让 η 按 φ 分三档学习，与 05 `evt.agg_route_eta` 的"端点 × 节点"格子及 `k_cf` 聚合闸不兼容 | 中 | 已修：R0 不分档，φ 只作 GBDT 特征与截断说明 |
| 1 | FEAS | §5.6 快照合计与自身分项不符（d=1,024 且含叶子质心时实为约 130–150 MB，而非 70–90 MB） | 低 | 已修：按新口径重算并与 §14.3 对齐 |
| 1 | FEAS | 乘积形式隐含"各端点取回事件条件独立"，未声明；正相关会让 f 高估并集召回 | 低 | 已修：§5.3、§6.1 写明假设、影响与校准方式 |
| 1 | FEAS | §6.2 的无证据兜底先给 domain 分布再"上卷"到 subfield（方向不对）；混合权重按"独有贡献"拟合，与 §5.3 的理由矛盾 | 低 | 已修：兜底直接给 subfield 先验；拟合目标改为 top-k 结果集合的节点分布 |
| 1 | FEAS | 表面语法的符号集合算子与文字算子混用、词内连字符的歧义未定义 | 低 | 已修（§3.2） |
| 1 | FEAS | 联邦阈值名 `k_min` 与 08 的 k 匿名阈值同名 | 低 | 已修：改名 `n_min`（R2-04） |
| 1 | FEAS | LATEST 两段式与精确扫描的"毫秒级"只算了算术，漏了从 PG 读 2 万条向量的开销 | 低 | 已修：§8.8、§9.5 改为十到数十毫秒量级，并给超预算时的 HNSW 替代路径 |
| 1 | FEAS | 注水预算未扣除新条目本身的取回页数；伪代码缺预算不可行检查与策略闸 | 低 | 已修（§11.4） |
| 1 | R2-39、R2-41、R2-03、R2-21、R2-05 | "top-100"、300 ms、"每篇曝光下限"、展示级 V0–V4、B 类开关、非个性化取值的旧口径 | 低 | 已修：按各条裁决改写；`np_time` 用"首见时间"还是 `first_public` 的口径差异转 06（§20 第 28 项） |
| 1 | R2-02、R2-08、R2-11、R2-14、R2-17、R2-30、R2-31、R2-33、R2-34、R2-47、R2-49 | 术语、网关名称与密钥归属、`bulk_snapshot`、SN/ADS 按用户级凭证、官方 WP feed、事件留存、`block.target_type=source`、WatchKey 职责、`/me/follows`、空查询态 | 低 | 已修：逐条落到 §1.4、§4.1、§6.3、§10.6、§11.1、§11.2、§12.2、§13、§15.3、§15.4；§20 第 15、19 项更新 |
| 1 | FEAS | §4.6、§20 第 7 项与 ADR 候选 3 仍写"256 维索引"，与 §9.3"维度随 Q7"矛盾；执行器的探索开关是全局的，与"按端点关闭采样"不符 | 低 | 已修 |
| 1 | FEAS | 配图与正文不一致：MSC、PubMed、OpenReview、LLM 部署、曝光下限、范围完整性、私有层、B 类摘要 | 低 | 已修：两张 SVG 同步更新，经无头 Chrome 渲染检查无重叠 |
| 1 | FEAS | §19-13（EXPAND 第五意图）、§19-14（Percolator 两档节奏）、§19-15（稠密索引维度）简报 §10 未涉及 | 中 | 保留：理由见 §19 各条，仍转主 agent 裁定 |
| 1 | FEAS | 02 §2.7(d) 的 SSE 事件名与合并顺序、联邦意图集合仍与本文不一致 | 低 | 保留：属 02 的修改，维持 §20 第 21 项转主 agent |
| 2 | EVID / HC-01、R2-40 | 路由的输入含个人数据：p_r 取首屏命中，而首屏可能已经过 `Personal` 谓词过滤、`personal_score` 重排，并含 `private` 列表；`n_local_T` 与 η 的观测集合 T 同样取个性化之后的结果。π 与 η 写入 `route_decision` 并进入全局路由学习，构成私有到共享的派生路径，也使"同一规范查询同一计划"不成立 | 高 | 已修：§5.3、§6.2、§6.3、§8.2 伪代码、§1.3、§15.3 统一为共享层、个人谓词与挂点之前的召回；新增 AC-V2.28；配图同步 |
| 2 | EVID / P-05、R2-13 | 漏掉 Europe PMC 的 `Crawl-Delay: 10`（AG §2.2.10、§2.3.3；LS §2.3.3；03 §4.4 已登记）：正文只写"限速未公布、取保守值"，把 EPMC 当作生命科学首选联邦后端与 PMID 链首级，§6.5 还称 arXiv"最稀缺"。按最严口径，全平台每 10 秒至多 1 次，且与收割共用 | 高 | 已修：§6.5 稀缺度排序、§8.4 两行、§10.4 路由与执行、§13 引言、§13.9、§20 第 9 项；AC-V1.1 纳入 Crawl-delay；配图同步。与 EBI 约定用量转主 agent |
| 2 | EVID | S2 `/paper/search/bulk` 被当作相关性端点，承接 §6.12、§8.3、§10.4 的软检索文本。AG §2.2.3、§2.3.2 表明 bulk 只能按 paperId、publicationDate、citationCount 排序，相关性检索是 `/paper/search`（RT §3.4）；按本文 §7.2，bulk 在这些查询上应判为无界而剔除 | 高 | 已修：示例与完整性报告改用 `s2.search`；§6.12、§10.4 写明 bulk 被剔除的原因；§7.4 标注 bulk 须取完全部匹配；TSRG 配图同步 |
| 2 | EVID / R2-21 | B 类摘要的索引资格只排除机器可读的 TDM 保留，没有反映 CP §2.3.2 的建议"把自然语言保留也当作有效保留"（SN、Elsevier 已明示保留），等于默认依赖一件已上诉、未终审的判例 | 高 | 部分修正：§9.1 单列一行并标 ⚠，补欧盟法角度；新增 §19-18 与 §20 第 34 项。是否排除须主 agent、08 与法务裁定 |
| 2 | EVID / HC-01 | GBDT 路由器直接用逐次决策的假名化 `route_decision` 训练全局模型，达不到 CP §2.7 M19 与 DI-03 要求的"聚合、去标识" | 中 | 已修：§6.9 改为由 `pc_sys_aggregator` 按"意图 × π 首节点"格子的 `k_cf` 门槛抽取训练集；AC-V2.37 补断言；落表与 08 确认转 §20 第 35 项 |
| 2 | EVID / SI-02 | Crossref `works_query` 作为 SEARCH 候选，与 AG §2.2.1、§2.4 R6（关键词检索不打 Crossref，`query.bibliographic` 只用于引文串匹配）和 SI-02 不一致；"公共池 1/s"对使用 polite 池的平台也不准确 | 中 | 已修措辞（列表池 polite 3/s），§6.12 示例标注"按 03 现行登记"并说明调研结论；建议 SCD 不声明 SEARCH，转 03 与主 agent（§20 第 33 项） |
| 2 | EVID | OA 定位链把 Unpaywall 排在 OpenAlex 之前，未反映 Unpaywall 已于 2025 年末并入 OpenAlex、两者同源的事实（AG §2.2.4、§2.4 R11；CP §2.1、§2.4） | 中 | 已修：OpenAlex 单实体在前，Unpaywall 作同源兼容补查，并注明它只提供主机级替补 |
| 2 | EVID / P-09 | 语义探索链的两级远端都有调研约束未写入：OpenAlex 语义检索为 beta、官方不建议敏感生产（AG §2.4 R7）；S2 推荐受全端点共用的 1 RPS 约束，AG §3-11 认为不能支撑多用户实时调用 | 中 | 已修：§4.6、§8.4 标注并限定为低频、用户显式触发；该链的"两级替补"实际由本地 ANN 兜底，转主 agent 知悉 |
| 2 | EVID / HC-05、HC-07 | §8.5 写"许可不允许存储的来源，只进入 TTL 缓存"。跨用户的 TTL 缓存本身就是平台级存储，与 AG §2.3.4 的"可缓存"列及字段级权利标签要求冲突 | 中 | 已修：TTL 缓存只收来源允许平台级缓存的数据并保留权利标签；不允许缓存的来源本就不进平台路由；记录不保存触发的查询或用户 |
| 2 | EVID / HC | 缺少 HC 逐条对照：HC-02、03、05、06、15、18、22、25、26、27 与 HC-29…32 在正文中没有落点说明 | 中 | 已修：新增 §1.5；§9.1 补"全文不进共享索引"（HC-06）；§15.1 公开频道按 UGC（HC-15）；§15.4 第 9 条限定层③不复用用户倒排（HC-18）；§13 引 HC-29，§6.3 引 HC-31 |
| 2 | EVID / B-06、R2-01 | 许可门禁没有成体系核对：T1 默认的小型 CE、自托管 LLM、GBDT 库、scipy、Hypothesis、JEL、EconBiz STW、SciRepEval 的许可未核或未标 | 中 | 已修：新增 §1.6（一手来源补查）；§8.7 增"许可"条，指出常用小型 CE 以 MS MARCO 训练、数据集许可未声明 ⚠；§5.1 给 JEL、STW 标 ⚠；§14.1 标 SciRepEval；新增 AC-V0.13；待核项列 §20 第 36 项 |
| 2 | EVID / HC-11、R2-45 | EXPAND 深度模式的 LLM 读入论文文本，未受索引资格、C 类内容与 AI 输入保留信号的约束，输出的归属也未说明 | 中 | 已修：§4.6 规定输入只取 CE 输入为 ✓ 的字段，排除 C 类与带 `ai-input=no`、TDMRep 保留的来源，输出只存本人域 |
| 2 | EVID / HC-12 | §4.5 称"自托管模型同样满足 HC-12"。CP §2.2.3 与 HC-12 要求已备案模型、地方登记与公示，自托管本身不等于已备案 | 中 | 已修：自托管只解决路由与数据不出境，面向境内开放仍须满足 HC-12、HC-21。简报 P-07 的"已备案模型或自托管模型"措辞转主 agent |
| 2 | EVID | §10.4 的 EPMC `PUB_TYPE` 字段调研未核（LS §2.3.3 只列出 143 个字段中的 32 个），却作为 φ=1 的依据 | 中 | 已修：标 ⚠，写明实现期对照 `/fields` 核验及核验不通过时的处置；S2 bulk 的剔除理由补上取值表未核的情形 |
| 2 | EVID / 综合 §6.1 | 正文未按综合的要求写明所依据的 SI；SI-26 中"SPLADE 官方权重不进默认路径"未承接 | 中 | 已修：§1.1 新增 SI 承接对照表，标出 SI-02、SI-40 两条"部分"承接及理由 |
| 2 | EVID / P-09、R2-13 | 前轮遗留的 ⚠："确认前 PMID 链的第二级远端依赖 OpenAlex 按 PMID 单查"未经核验，P-09 是否满足悬而未决 | 中 | 已修：一手实测（2 次匿名请求，先读 robots）确认 OpenAlex 按 PMID 单查可用且免费，PMID 链满足两级；PMCID 单查仍 ⚠（样本记录无 pmcid）。§8.4、§20 第 3 项、§21.3 同步 |
| 2 | EVID | §8.8"一周约 7,000 篇的 cs.LG ∪ stat.ML"与 §10.2"arXiv cs 各集合一周约 7,083 条"误读 CS：7,083 是 cs 全集一周的 OAI 记录（含替换版），cs.LG 为 1,861 条 | 低 | 已修（CS §2.6.1） |
| 2 | EVID | bioRxiv"200 空体"两处引用 LS §2.3.2，该节是 PMC | 低 | 已修：改为 LS §2.2.1、§3-11 |
| 2 | EVID | 把 OSS §3-2 建议的四类工作流说成 Asta PaperFinder 自身的四类；调研未记载其工作流个数 | 低 | 已修 |
| 2 | EVID | arXiv ID 替补链：OpenAlex 单查的键与证据缺失；末级把用户请求透传给 arXiv API，与 CS §2.1.1、§3-6 的建议不一致而未说明 | 低 | 已修：按 DataCite DOI `10.48550/arXiv.<id>` 单查（CS §2.1.1），附 UX 核验表的实测实例；末级只在本地与 OpenAlex 都未命中的单篇 LOOKUP 上触发，全平台一个令牌桶，份额用尽即快速失败 |
| 2 | EVID | §0 与 §9.4 的快照体量（约 50–90 MB、≤90 MB）与 §5.6 的估算（45–55 MB，为叶子建质心时约 65–140 MB）不一致 | 低 | 已修 |
| 2 | EVID | Crossref polite 池数值未标证据等级（公告与第三方观测，调研未用平台邮箱实测，AG §4 Q4）；§13.1 响应头清单含当前不经网关的 CORE、ADS | 低 | 已修：补 ⚠ 与说明 |
| 2 | EVID | 引用细节：§3.3 的 `cites:` 出处应为 AG §2.3.1；§7.4 S2 bulk 的 `openAccessPdf` 过滤缺出处（AG §2.2.3） | 低 | 已修 |
| 2 | EVID | §21 的调研章节与一手来源清单、§21.2 的 R2 对齐清单未随正文更新 | 低 | 已修：补 AG、CS、LS、SS、CP、UX、08 的具体章节与本轮一手来源；R2 清单加 R2-01、R2-04 |
| 2 | EVID | 配图与正文不一致：S2 端点、EPMC 限速、JEL 许可、路由输入的个人数据口径 | 低 | 已修：两张 SVG 同步，XML 校验与渲染检查通过 |
| 审计 | 一致性（2026-09-27） | §20 第 19、20、21、24、29、31、32 项所指 02、05 的缺口；阅读指引未标注"功能说明/实现方案" | 低 | 已修：02 的组件表、出箱主题与 SSE 契约已按本文改写；05 已补 `work_search.index_seq`、`percolate_batch.index_seq_lo/hi`、`usr.watch_key_pending`、`agg_route_eta` 输入口径；§8.2 注记与 §20 状态同步；EXPAND 仍待主 agent |
