---
title: 术语表（Glossary）
status: draft
owner: opus5.5-primary
updated: 2026-09-30
---

# 术语表

> 本页是 v2 最常用术语的速查表。完整的术语登记（含编号与歧义消解规则）在需求长稿的 §14：`git show v2-drafts:docs/plan/v2/01-vision-and-requirements.md`；v2 文档评审通过后再并入本页。
> v1 术语表在 `archive/v1` 的 `docs/GLOSSARY.md`，见[归档说明](archive.md)。

| 术语 | 含义 |
|---|---|
| Scout | 仓库内的单用户 AI 会议论文检索服务（D-077 草案），设计见 [plan/scout/](plan/scout/README.md)；与 v2 平台互不依赖 |
| HopLoop（多跳收敛检索） | Scout 的检索核心：关键词抽取 → BM25、同义模糊与向量召回 → 相关度、质量与决策模型排序 → 从前几篇抽新关键词再召回，直到前 n 名不变 |
| 决策模型（System One） | 不生成文本、一次前向给出 yes/no、多选与分级评分校准概率的判别模型，如 Google 的 Gemini Decision 1（Decisions API）与 TypeSafe 的 Jev；Scout 用它评审候选论文 |
| 摘要分片代（generation） | Scout 把一个届次的全部摘要写成一组 zstd 压缩的 JSONL 分片；每次抓取后整代重写、原子切换，论文按（代、片、行）指针读取 |
| Source / Venue | 可对接的来源（出版商平台、预印本服务器、聚合器、仓储实例等）与期刊、会议或 WP 系列；两者分开建模 |
| 来源七类（M1、M2、L1a–L1c、L2a–L2b） | 元层 M1 出版与托管主体、M2 标识与注册；一级 L1a 期刊与会议、L1b 预印本与工作论文、L1c 长尾一级产出；二级 L2a 文献库与学科仓储、L2b 检索引擎与聚合项目。取代旧的 L1/L2 七种类型，定义见 [来源分层](catalog/source-taxonomy.md) |
| 兼角色（role） | 来源在主类之外承担的职能，如 Crossref 主类 M2、兼 L2b 元数据 API；CNKI 主类 L2a、兼 M1 网络首发 |
| 评级标签（rating tag） | 挂在 venue 上的名录等级或成员资格，如 `CCF-A`、`ICORE-A*`、`UTD24`、`ABDC-A*`、`NI`；体系与许可见 [评级体系](catalog/venue-rankings.md) |
| SourceSpec v2 / SourceChannel | 来源的机读声明；每个来源声明 metadata、latest、fulltext 三条来源通道，以及各自的合规证据 |
| SCD | Source Capability Descriptor：可下推谓词、排序键、增量游标、成本模型与礼貌参数；是路由器的唯一输入 |
| ConnectorFamily | v2 的 adapter 抽象，共九族（含 `bulk_snapshot`，以及复用 v1 adapter 的 `v1_bridge`）；每个 connector 声明 `exec_side ∈ {platform, user}` |
| Egress Gateway（出站网关） | 平台侧唯一的对外出口，执行 robots、五元组令牌桶限速、配额与审计 |
| ConnectorContract v1（连接器接口契约） | 连接器与执行器、网关之间的冻结协议：三层声明、核心类型、判定点、游标、错误分类、映射与版本规则；定义见[契约](plan/v2/connectors/contract.md)（D-074 草案） |
| ConnectorManifest / ConnectorInstance | 连接器级清单 `registry/connectors/<connector_id>.yaml`（族、`exec_side`、`impl`、端点、游标、映射版本、fixture、探针、一致性等级、owner；不含运行态）/ 族实例清单 `registry/instances/<family>/<instance>.yaml`（base URL、OAI 参数、特例旗标）；与 SourceSpec 合称三层声明，合规证据只在 SourceSpec |
| PlatformConnector / RecipeProvider | 连接器的两种协议：平台侧的 `plan/parse/normalize/describe/probes`，由平台 worker 加载；用户侧只产出声明式配方 FulltextRecipe 的数据，没有 `plan()` |
| RequestSpec / Step | 连接器声明的一次请求（端点、上游请求类、参数、白名单头、`AuthRef`、`Expectation`），刻意不含 UA、Cookie、robots 字段 / 执行器回送给 `plan` 生成器的"响应 + 已解析页"，非合法结果只回送响应 |
| CursorEnvelope | 持久化游标的外壳 `{scope_key, cursor, schema, rev}`；游标分七种 kind（`date_watermark`、`oai_datestamp`、`guid_set`、`seq`、`snapshot_release`、`repo_commit`、`window_set`），只在安全提交点随本页数据同一事务推进 |
| NormRecord | `normalize` 从一条原始记录映射出的规范化记录，只输出声明，许可、权利、版本、关系四类字段带依据（`basis`）；许可取原串加 `license_alias` 归一码，权利与共享字段由共享函数 `classify_rights()` 计算、mapper 不得直接给出；不确定即 `unknown`，未知即不共享 |
| EffectiveStatus | 连接器健康（healthy、degraded、suspended、disabled、retired）与策略模式合成的状态，是路由、"来源"页、来源状态通知与运维总览的唯一状态来源 |
| traffic_class / request_class | 平台内流量类别（`background_batch`、`on_demand`），由执行器按任务 lane 盖章、连接器不可设置 / 上游的限速池类（如 Crossref 单条与列表），即 02 的"上游请求类"，用于五元组令牌桶；05 长稿 `ops.fetch_log.request_class` 列现存的是流量类别，改名 `traffic_class` 待拍板 |
| 一致性等级 CL0–CL3 / CLX | 连接器的上线证明：CL0 登记（清单、卡片、证据齐全，第二人合规复核）、CL1 离线一致、CL2 灰度（staging 真实运行）、CL3 生产、CLX 退役；每级有进入门与保持条件，失效自动下调，同时是策略上限。见[一致性与测试](plan/v2/connectors/conformance-and-testing.md)（D-075 草案） |
| CL1 待命 | 受书面确认、传输方式或 ADR 闸门阻塞的连接器做到 CL1、通道保持 deny 或 link_only，在里程碑出口按待命达标计；闸门解除后再进 CL2 计天 |
| error_class | 连接器执行结果的错误分类，契约 v1 共 15 类（如 `transient`、`rate_limited`、`challenge`、`gone`、`parse`、`cursor_expired`），每类只有一个判定者，见 [契约 §7](plan/v2/connectors/contract.md#7-错误矩阵) |
| 评审门 G1 / G2 / G3 | 连接器上线的三道评审：G1 合规（CL0 出口，含第二人合规复核）、G2 技术（CL1→CL2）、G3 上线（CL2→CL3），见 [一致性与测试](plan/v2/connectors/conformance-and-testing.md) |
| QueryRecipe（P-13） | 拟议的用户侧元数据查询配方（本人 token 查询，如 OpenReview、NASA ADS、ORCID）；契约 v1 未收录，相关连接器停在 CL0，待拍板 P-13 |
| 四类 fixture | 每个连接器与实例必备的回放样本：正常页、空页或 200 空体、限流或错误、边界（末页、令牌过期、删除、版本变化）；只经 staging 网关录制并脱敏，受版权正文不入库 |
| 族一致性套件 | 按"实例 × fixture"参数化的族级测试，新增实例不写新测试，引擎改动时全实例回放 |
| 连接器卡片（connector card） | 每个连接器一张的 13 节说明（身份、通道、上游事实、请求、游标、映射、SCD、合规、全文、测试、探针、运维、已知坑），多数节由清单生成；模板见[卡片模板](plan/v2/connectors/connector-card-template.md) |
| impl 代码阶梯 | 连接器实现方式从低到高 `instance < declarative < mapper < custom_plan < v1_bridge`，默认取最低可行级，上调须写理由 |
| 波次 W0–W4 | 连接器实施批次：W0（V0）契约与三个参考连接器，W1、W2（V1）P0 平台侧、快照与 v1 桥接，W3（V3、V5 两批）用户侧通道与 P1，W4（V5 以后）P2 与升为"支持"的登记来源按需升级；用户侧通道的波次记作 W3u、W4u（依赖 V3 的浏览器扩展或 pc-agent，[矩阵](catalog/connector-matrix.md)按来源行标注）；见[实施计划](plan/v2/connectors/implementation-plan.md) |
| TSRG | Topic–Source Routing Graph，主题-来源路由图；以 OpenAlex 四级主题树为骨架，统一服务查询路由、收割调度、兴趣建模与论文→读者反向推送 |
| Query AST / 频道（Channel） | 统一查询语法树，支持五种意图（LOOKUP、SEARCH、SIMILAR、LATEST、EXPAND）；用户保存的查询称为频道，是 v1 Subscription 的 v2 形态 |
| WatchKey / Percolator / FeedInbox | 多用户共享、带引用计数的收割键 / 新论文入库后反向匹配全部频道与兴趣 / 每个用户的待推送收件箱 |
| display_scope | 字段级展示范围：`public_shared` / `per_user_only` / `link_only`；派生物继承其输入中最严的范围 |
| DL0–DL4 | 合规展示级别（调研中记作 V0–V4，为避免与里程碑 V0–V7 冲突而改名） |
| Deck / 有限批次 | 前端"今日分拣"卡叠；默认每日 25 张，看完即结束 |
| ValueModel | 排序打分 Σ V_a·P̂(a)：行为价值权重乘以预测行为概率，可版本化配置 |
| Candidate Pipeline | 推荐管线的六类组件：Source、Hydrator、Filter、Scorer、Selector、SideEffect |
| k_cf / k_reason / k_show | k 匿名门槛：协同信号入模 / 协同类解释 / 公开计数与社会证明 |
| V0–V7 / AC-V | v2 里程碑 / 里程碑验收标准编号 AC-V<m>.<n> |

## 推荐研究中的经济机制术语

以下用于[推荐论文清单](survey/peer-review-content-ads-reading-list.md)的经济学增补，不构成新的已批准架构决策。

| 术语 | 含义 |
|---|---|
| EconCS / EC / TEAC | 经济学与计算机科学交叉领域 / ACM Economics and Computation 会议 / ACM Transactions on Economics and Computation 期刊 |
| Mechanism design（机制设计） | 考虑参与者会策略性行动，设计分配、支付、信息披露等规则以实现明确目标 |
| Incentive compatibility（激励相容） | 在指定信息与博弈假设下，按机制要求诚实报告或遵循建议符合参与者自身利益；不同均衡概念的保证不能混用 |
| Information design / Bayesian persuasion（信息设计／贝叶斯说服） | 通过选择信息披露或信号结构影响接受者信念与行动；发送者最优不自动等于用户福利最优 |
| Peer prediction（同行预测） | 缺少可验证真值时，利用同行报告之间的统计关系设计信息反馈激励；不同意见不自动等于低质量 |
| Supply-side equilibrium（供给侧均衡） | 创作者或卖方响应推荐、报酬和竞争规则后形成的供给结果，区别于固定内容集上的排序效果 |
| Structural counterfactual（结构反事实） | 基于估计的行为模型预测替代政策结果，依赖识别与模型假设，区别于直接随机试验效果 |
| Incrementality（增量效果） | 相对未施加干预时新增的结果，区别于对已曝光样本的点击或转化预测 |
