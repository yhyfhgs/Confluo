# 文档索引

> main 上全部文档的清单。新增、改名或删除文档时，在同一提交内更新本表。status 的取值与流转见 [AGENTS.md](../AGENTS.md)。
> **最后盘点：2026-09-30**：设计、名录与调研都换成了精简版；完整长稿在标签 `v2-drafts`，v1 在分支 `archive/v1`，读法见[归档说明](archive.md)。2026-09-27 新增来源七类分层、候选来源、评级体系与按学科的 venue 名录；2026-09-30 新增连接器标准化计划（`plan/v2/connectors/`）、来源 × 连接器矩阵与接口增量 UI 的 demo。

## 先读

| 文档 | 内容 | status |
|---|---|---|
| [../README.md](../README.md) | 项目入口 | — |
| [plan/v2/README.md](plan/v2/README.md) | v2 方案总览：一篇看完方案与待你拍板的事 | draft |
| [plan/progress.md](plan/progress.md) | 当前进度与下一步 | approved |

## v2 设计（plan/v2/）

| 文档 | 内容 | status |
|---|---|---|
| [01-vision-and-requirements.md](plan/v2/01-vision-and-requirements.md) | 愿景与需求：用户、场景、需求分组、红线、北极星 | draft |
| [02-architecture.md](plan/v2/02-architecture.md) | 总体架构：组件、部署、数据流、出站网关、用户侧取回、API | draft |
| [03-sources-and-corpus-pipeline.md](plan/v2/03-sources-and-corpus-pipeline.md) | 来源接入与语料流水线 | draft |
| [04-retrieval-and-routing.md](plan/v2/04-retrieval-and-routing.md) | 检索、路由与 TSRG | draft |
| [05-data-platform.md](plan/v2/05-data-platform.md) | 多用户数据平台 | draft |
| [06-recommendation-and-matching.md](plan/v2/06-recommendation-and-matching.md) | 推荐、反馈学习与双向匹配 | draft |
| [07-frontend-interaction.md](plan/v2/07-frontend-interaction.md) | 前端交互与视觉 | draft |
| [08-compliance-security-privacy.md](plan/v2/08-compliance-security-privacy.md) | 合规、隐私与安全（含 HC-01…HC-32） | draft |
| [09-roadmap-and-milestones.md](plan/v2/09-roadmap-and-milestones.md) | 路线图与里程碑 V0–V7 | draft |
| [demo/paper-feed-demo.html](plan/v2/demo/paper-feed-demo.html) | 卡片流交互 demo 与视觉案例（已发布为 Artifact） | — |
| [demo/promo-film.html](plan/v2/demo/promo-film.html) | 产品宣传片（约 88 秒动画，突出个性化推荐，演示上面这个 demo 的核心流程；内含分镜脚本） | — |
| [demo/connector-ui-demo.html](plan/v2/demo/connector-ui-demo.html) | 接口相关增量 UI 的交互 demo：来源、我的连接、可得性说明、取回状态与运维控制台（数据为示意） | — |

## 连接器（plan/v2/connectors/）

连接器接口契约 v1、一致性等级与测试、逐族规范、实施计划与接口增量 UI。先读 [README](plan/v2/connectors/README.md)。

| 文档 | 内容 | status |
|---|---|---|
| [README.md](plan/v2/connectors/README.md) | 连接器工作总览：文档地图、与 02/03/05/07/08/09 的关系、ADR 草案 D-074…D-076、待你拍板 | draft |
| [contract.md](plan/v2/connectors/contract.md) | 连接器接口契约 v1（ConnectorContract）：三层声明、核心类型、执行模型、游标、错误矩阵、映射、版本 | draft |
| [conformance-and-testing.md](plan/v2/connectors/conformance-and-testing.md) | 一致性等级 CL0–CL3/CLX、测试分层、fixture 政策、DoD 与评审门、CI 门禁 | draft |
| [connector-card-template.md](plan/v2/connectors/connector-card-template.md) | 连接器卡片 13 节模板与填写说明 | draft |
| [implementation-plan.md](plan/v2/connectors/implementation-plan.md) | 实施计划：波次 W0–W4、工作量、依赖、分工、风险与决策门 | draft |
| [connector-ui.md](plan/v2/connectors/connector-ui.md) | 接口相关增量 UI：用户面与运维面 | draft |
| [families/aggregator-api.md](plan/v2/connectors/families/aggregator-api.md) | 族规范与卡片：聚合器与学科库 API | draft |
| [families/oai-pmh.md](plan/v2/connectors/families/oai-pmh.md) | 族规范与卡片：OAI-PMH | draft |
| [families/feed.md](plan/v2/connectors/families/feed.md) | 族规范与卡片：RSS、Atom、eTOC | draft |
| [families/crossref-delegated.md](plan/v2/connectors/families/crossref-delegated.md) | 族规范与卡片：Crossref 委托 | draft |
| [families/bulk-snapshot.md](plan/v2/connectors/families/bulk-snapshot.md) | 族规范与卡片：官方快照与年度文件 | draft |
| [families/platform-family.md](plan/v2/connectors/families/platform-family.md) | 族规范与卡片：托管平台与仓储软件 | draft |
| [families/official-tdm-api.md](plan/v2/connectors/families/official-tdm-api.md) | 族规范与卡片：用户本人 key 的出版商 TDM API | draft |
| [families/site-special.md](plan/v2/connectors/families/site-special.md) | 族规范与卡片：专站 | draft |
| [families/v1-bridge.md](plan/v2/connectors/families/v1-bridge.md) | 族规范与卡片：v1 adapter 桥接与退役 | draft |

## 查阅

| 文档 | 内容 | status |
|---|---|---|
| [catalog/source-taxonomy.md](catalog/source-taxonomy.md) | 来源七类分层与收集现状总表 | draft |
| [catalog/source-directory.md](catalog/source-directory.md) | 来源支持名录（187 条，按七类分节，标支持层级） | draft |
| [catalog/source-candidates.md](catalog/source-candidates.md) | 本轮调研的候选来源（156 个，未入名录） | draft |
| [catalog/connector-matrix.md](catalog/connector-matrix.md) | 来源 × 连接器矩阵：169 个非排除来源的连接器、族、波次与一致性等级目标，18 个不接入来源简表 | draft |
| [catalog/venue-rankings.md](catalog/venue-rankings.md) | 期刊会议评级体系（45 个）与评级标签词表 | draft |
| [catalog/venues/README.md](catalog/venues/README.md) | 按学科的 venue 名录总览（866 个，核心 305）、支持分级与关联总图 | draft |
| [catalog/source-support-catalog.xlsx](catalog/source-support-catalog.xlsx) | 支持名录 Excel：各学科 M、L1、L2 来源与 venue 的支持层级，合并单元格标隶属关系（由名录生成） | — |
| [plan/decision-log.md](plan/decision-log.md) | ADR 登记：v2 草案 D-040…D-076 与 v1 索引 | approved |
| [GLOSSARY.md](GLOSSARY.md) | 术语速查 | draft |
| [archive.md](archive.md) | 归档说明：v2 完整长稿与 v1 | approved |
| [../AGENTS.md](../AGENTS.md) | AI 协作者规范 | — |

调研结论与论文精选（同行评审、内容与广告推荐，75 篇）在 TeamHub 维护：[v2 调研结论](https://github.com/Orbit-Labs-AI/team-hub/blob/main/%E9%A1%B9%E7%9B%AE/Confluo/03-%E7%A0%94%E7%A9%B6/v2%E8%B0%83%E7%A0%94%E7%BB%93%E8%AE%BA.md)、[论文精选](https://github.com/Orbit-Labs-AI/team-hub/blob/main/%E9%A1%B9%E7%9B%AE/Confluo/03-%E7%A0%94%E7%A9%B6/%E5%90%8C%E8%A1%8C%E8%AF%84%E5%AE%A1%E3%80%81%E5%86%85%E5%AE%B9%E4%B8%8E%E5%B9%BF%E5%91%8A%E6%8E%A8%E8%8D%90%E8%AE%BA%E6%96%87%E7%B2%BE%E9%80%89.md)。

## venue 名录（catalog/venues/）

按学科分文件，每个文件开头有"学科 → 子领域 → 核心 venue"的关联图，正文先列核心、后列登记。总览、数字与跨学科关联总图见 [catalog/venues/README.md](catalog/venues/README.md)。

| 文件 | 学科组 | venue 数（核心） | status |
|---|---|---:|---|
| [math.md](catalog/venues/math.md) | 数学（含统计、概率） | 63（20） | draft |
| [physics-astronomy.md](catalog/venues/physics-astronomy.md) | 物理与天文 | 61（22） | draft |
| [chemistry.md](catalog/venues/chemistry.md) | 化学 | 47（17） | draft |
| [earth-sciences.md](catalog/venues/earth-sciences.md) | 地学 | 52（16） | draft |
| [materials.md](catalog/venues/materials.md) | 材料 | 36（12） | draft |
| [life-sciences-medicine.md](catalog/venues/life-sciences-medicine.md) | 生命科学与医学 | 104（37） | draft |
| [psychology-cognition.md](catalog/venues/psychology-cognition.md) | 心理与认知 | 57（21） | draft |
| [economics.md](catalog/venues/economics.md) | 经济 | 98（27） | draft |
| [finance.md](catalog/venues/finance.md) | 金融 | 45（16） | draft |
| [business-management.md](catalog/venues/business-management.md) | 商业与管理 | 124（37） | draft |
| [computer-science-ai.md](catalog/venues/computer-science-ai.md) | 计算机与 AI | 154（70） | draft |
| [multidisciplinary.md](catalog/venues/multidisciplinary.md) | 跨学科综合 | 25（10） | draft |

## 配图（diagrams/）

| 图 | 内容 |
|---|---|
| [v2-01-architecture.svg](diagrams/v2-01-architecture.svg) | 分层组件与四个数据域 |
| [v2-02-dataflow.svg](diagrams/v2-02-dataflow.svg) | 主数据流与合规边界 |
| [v2-03-source-model.svg](diagrams/v2-03-source-model.svg) | Source、通道、Venue、连接器与策略引擎的关系 |
| [v2-04-tsrg.svg](diagrams/v2-04-tsrg.svg) | TSRG 主题-来源路由图及四种用途 |
| [v2-05-query-execution.svg](diagrams/v2-05-query-execution.svg) | 从 Query AST 到并行联邦执行与合并 |
| [v2-06-data-domains.svg](diagrams/v2-06-data-domains.svg) | 四个数据域、主要表与 RLS 边界 |
| [v2-07-rec-pipeline.svg](diagrams/v2-07-rec-pipeline.svg) | 推荐管线与学习闭环 |
| [v2-08-bidirectional-matching.svg](diagrams/v2-08-bidirectional-matching.svg) | 三层双向匹配 |
| [v2-09-card-anatomy.svg](diagrams/v2-09-card-anatomy.svg) | 论文卡片解剖 |
| [v2-10-data-boundaries.svg](diagrams/v2-10-data-boundaries.svg) | 共享、私有、用户侧与上游之间的数据流与禁止路径 |
| [v2-11-source-confluence.svg](diagrams/v2-11-source-confluence.svg) | 宣传概念图：一级、二级来源汇入统一语料（按旧的 L1/L2 口径绘制） |

图注里的章节号指 `v2-drafts` 上的完整长稿。

## 工作日志（logs/）

| 日志 | 内容 |
|---|---|
| [2026-09-30-session-018.md](logs/2026-09-30-session-018.md) | 连接器标准化计划：接口契约、一致性等级、逐族规范、实施计划与接口增量 UI |
| [2026-09-28-session-017.md](logs/2026-09-28-session-017.md) | 更名为 Confluo，迁入团队组织（现名 Orbit Labs） |
| [2026-09-27-session-014.md](logs/2026-09-27-session-014.md) | 精简 docs，清理仓库与分支 |
| [2026-09-27-session-015.md](logs/2026-09-27-session-015.md) | 来源七类分层、评级体系与按学科的 venue 名录 |
| [2026-09-28-session-016.md](logs/2026-09-28-session-016.md) | 推荐系统论文清单及 EconCS、博弈论与经济学增补（75篇） |

更早的日志：设计阶段的 011–013 在标签 `v2-drafts`，v1 的 001–010 在分支 `archive/v1`。里程碑报告从 V0 起写入 `reports/`。
