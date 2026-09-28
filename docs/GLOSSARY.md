---
title: 术语表（Glossary）
status: draft
owner: opus5.5-primary
updated: 2026-09-28
---

# 术语表

> 本页是 v2 最常用术语的速查表。完整的术语登记（含编号与歧义消解规则）在需求长稿的 §14：`git show v2-drafts:docs/plan/v2/01-vision-and-requirements.md`；v2 文档评审通过后再并入本页。
> v1 术语表在 `archive/v1` 的 `docs/GLOSSARY.md`，见[归档说明](archive.md)。

| 术语 | 含义 |
|---|---|
| Source / Venue | 可对接的来源（出版商平台、预印本服务器、聚合器、仓储实例等）与期刊、会议或 WP 系列；两者分开建模 |
| 来源七类（M1、M2、L1a–L1c、L2a–L2b） | 元层 M1 出版与托管主体、M2 标识与注册；一级 L1a 期刊与会议、L1b 预印本与工作论文、L1c 长尾一级产出；二级 L2a 文献库与学科仓储、L2b 检索引擎与聚合项目。取代旧的 L1/L2 七种类型，定义见 [来源分层](catalog/source-taxonomy.md) |
| 兼角色（role） | 来源在主类之外承担的职能，如 Crossref 主类 M2、兼 L2b 元数据 API；CNKI 主类 L2a、兼 M1 网络首发 |
| 评级标签（rating tag） | 挂在 venue 上的名录等级或成员资格，如 `CCF-A`、`ICORE-A*`、`UTD24`、`ABDC-A*`、`NI`；体系与许可见 [评级体系](catalog/venue-rankings.md) |
| SourceSpec v2 / SourceChannel | 来源的机读声明；每个来源声明 metadata、latest、fulltext 三条来源通道，以及各自的合规证据 |
| SCD | Source Capability Descriptor：可下推谓词、排序键、增量游标、成本模型与礼貌参数；是路由器的唯一输入 |
| ConnectorFamily | v2 的 adapter 抽象，共九族（含 `bulk_snapshot`，以及复用 v1 adapter 的 `v1_bridge`）；每个 connector 声明 `exec_side ∈ {platform, user}` |
| Egress Gateway（出站网关） | 平台侧唯一的对外出口，执行 robots、五元组令牌桶限速、配额与审计 |
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
