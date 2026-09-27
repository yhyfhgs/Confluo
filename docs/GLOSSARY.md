---
title: 术语表（Glossary）
status: draft
owner: opus5.5-primary
updated: 2026-09-27
---

# 术语表

> v2 的共享术语以 [plan/v2/01 §14 术语登记表](plan/v2/01-vision-and-requirements.md) 为权威，含编号与术语歧义的消解规则。本页只列最常用的术语，供速查；v2 文档评审通过后，01 §14 的术语再并入本页正式章节。
> v1 术语表已归档，见 [archive-v1](archive-v1.md#docs-glossary-md)。

| 术语 | 含义 |
|---|---|
| Source / Venue | 可对接的来源（出版商平台、预印本服务器、聚合器、仓储实例等）与期刊、会议或 WP 系列；两者分开建模 |
| L1 / L2 | 一级来源（publisher、preprint、journal_platform、conference_platform）/ 二级来源（repository、aggregator，含 registry 子类型） |
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
