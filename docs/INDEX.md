# 文档索引（唯一权威清单）

> 本表是全仓库文档的单一事实来源（D-008）。任何新增/改名/废弃文档必须同一提交内更新本表（AGENTS.md §4）。
> status 取值与流转见 [process/status-workflow.md](process/status-workflow.md)。最后盘点：2026-07-26（Phase 6 R1 browser-fetch 详设草案登记）。

## 按意图导航（先于逐目录清单）

| 你想… | 阅读路径 |
|---|---|
| 10 分钟理解系统 | [README](../README.md) → [design/00 需求](design/00-requirements.md) → [design/01 架构](design/01-architecture.md)（配 [图01](diagrams/01-architecture.svg)/[图02](diagrams/02-plugin-modules.svg)）；生词查 [GLOSSARY](GLOSSARY.md) |
| 新增一个期刊/会议 | [catalog/README 登记流程](catalog/README.md) → 对应领域清单 → [publishers-platforms 平台映射](catalog/publishers-platforms.md) |
| 设计/实现一个新 adapter | [design/02 框架](design/02-plugin-framework.md) → [adapters/README 模板](design/adapters/README.md) → 同族样例（Atypon 看 [informs](design/adapters/informs.md)，Silverchair 看 [oup](design/adapters/oup-silverchair.md)，OA 看 [pmlr](design/adapters/pmlr.md)）→ [test-plan fixture 规范](testing/test-plan.md) |
| 理解认证与合规边界 | [design/04](design/04-auth-gated-module.md) → [design/07](design/07-auth-session.md) → [decision-log](plan/decision-log.md) D-006/D-014 → [AC-0 红线](testing/acceptance-criteria.md) |
| 开始 Phase 1 开发 | [development-plan §Phase 1](plan/development-plan.md) → design/01/02/05/06 → [status-workflow 开工门禁](process/status-workflow.md) |
| 查"为什么这样设计" | [plan/decision-log.md](plan/decision-log.md)（D-001…D-030） |
| 了解某站点的实测事实 | research/site-survey/ 对应勘察（各 adapter 文档 §2 已内联引用） |

## 根文档

| 路径 | 标题 | status | updated |
|---|---|---|---|
| [../README.md](../README.md) | 项目总览 | approved | 2026-07-21 |
| [../AGENTS.md](../AGENTS.md) | AI/LLM 协作者工作规范 | approved | 2026-07-21 |
| [GLOSSARY.md](GLOSSARY.md) | 术语表（全库速查） | review | 2026-07-22 |

## plan/ — 计划与决策

| 路径 | 标题 | status | updated |
|---|---|---|---|
| [plan/development-plan.md](plan/development-plan.md) | 开发计划（Phase 0–7） | approved | 2026-07-23 |
| [plan/phase1-implementation-plan.md](plan/phase1-implementation-plan.md) | Phase 1 实施计划（任务切分+接口冻结） | approved | 2026-07-21 |
| [plan/phase2-implementation-plan.md](plan/phase2-implementation-plan.md) | Phase 2 实施计划（Stage A 地基+arxiv；Stage B adapter 滚动） | approved | 2026-07-21 |
| [plan/phase3-implementation-plan.md](plan/phase3-implementation-plan.md) | Phase 3 实施计划（聚合元数据层：五源 adapter + 合并引擎任务切分） | approved | 2026-07-22 |
| [plan/phase4-implementation-plan.md](plan/phase4-implementation-plan.md) | Phase 4 实施计划（认证框架 + 出版社 adapters 任务切分） | approved | 2026-07-23 |
| [plan/phase5-implementation-plan.md](plan/phase5-implementation-plan.md) | Phase 5 实施计划（SSRN 与特殊经济学源 adapters 任务切分） | approved | 2026-07-24 |
| [plan/phase6-implementation-plan.md](plan/phase6-implementation-plan.md) | Phase 6 实施计划（订阅与搜索：DSL + watch + 护栏 + 日报 任务切分） | approved | 2026-07-26 |
| [plan/progress.md](plan/progress.md) | 项目进度跟踪 | approved | 2026-07-26 |
| [plan/decision-log.md](plan/decision-log.md) | 架构决策记录（D-001…D-031） | approved | 2026-07-26 |

## design/ — 核心设计（00–11）

| 路径 | 标题 | status | updated |
|---|---|---|---|
| [design/00-requirements.md](design/00-requirements.md) | 需求规格与边界（FR/NFR/红线） | approved | 2026-07-20 |
| [design/01-architecture.md](design/01-architecture.md) | 总体架构（六层） | implemented | 2026-07-21 |
| [design/02-plugin-framework.md](design/02-plugin-framework.md) | 可插拔框架（Adapter × VenueSpec） | implemented | 2026-07-21 |
| [design/03-open-access-module.md](design/03-open-access-module.md) | Open-Access 获取模块 | approved | 2026-07-20 |
| [design/04-auth-gated-module.md](design/04-auth-gated-module.md) | Auth-Gated 获取模块 | implemented | 2026-07-23 |
| [design/05-pipeline.md](design/05-pipeline.md) | 六阶段 Pipeline 与任务系统 | implemented | 2026-07-26 |
| [design/06-data-model.md](design/06-data-model.md) | 数据模型与入库设计 | implemented | 2026-07-26 |
| [design/07-auth-session.md](design/07-auth-session.md) | 认证与会话管理 | implemented | 2026-07-23 |
| [design/08-venue-tracking.md](design/08-venue-tracking.md) | Venue 时间轴与年度追踪 | approved | 2026-07-20 |
| [design/09-search-filter.md](design/09-search-filter.md) | 主题订阅与精确搜索 | approved | 2026-07-26 |
| [design/auth-framework.md](design/auth-framework.md) | 认证框架实现级详设（07/04 的实现级扩展：四 Provider + 凭证库 + CLI + pipeline 接缝） | implemented | 2026-07-26 |
| [design/10-config-layout.md](design/10-config-layout.md) | 配置归集与分层规范（D-025：config/ 文件夹 + 加载链 + 敏感键护栏） | implemented | 2026-07-23 |
| [design/11-browser-fetch.md](design/11-browser-fetch.md) | Browser-Fetch 横切件详设（三消费方统一浏览器取回通道 + CF-403 冷却缺口方案；D-029 案 B 承接，D-030 定稿） | approved | 2026-07-26 |

## design/adapters/ — 平台 adapter 详设

| 路径 | 标题 | status | updated |
|---|---|---|---|
| [design/adapters/README.md](design/adapters/README.md) | 模板 + 索引 + 勘察清单 | approved | 2026-07-20 |
| [design/adapters/arxiv.md](design/adapters/arxiv.md) | arXiv | implemented | 2026-07-22 |
| [design/adapters/ssrn.md](design/adapters/ssrn.md) | Adapter 设计 · SSRN（聚合主路径/browser-fetch defer） | implemented | 2026-07-26 |
| [design/adapters/nber.md](design/adapters/nber.md) | Adapter 设计 · NBER Working Papers（crossref prefix 枚举扩展 + www/back 双域） | implemented | 2026-07-24 |
| [design/adapters/aea.md](design/adapters/aea.md) | Adapter 设计 · AEA（AER+AEJ 四系+Insights+JEL/JEP，crossref ISSN 枚举） | implemented | 2026-07-26 |
| [design/adapters/econsoc.md](design/adapters/econsoc.md) | Adapter 设计 · Econometric Society（ECMA/TE/QE，OAI-PMH + ECMA 年代分段路由） | implemented | 2026-07-26 |
| [design/adapters/openreview.md](design/adapters/openreview.md) | OpenReview | implemented | 2026-07-22 |
| [design/adapters/pmlr.md](design/adapters/pmlr.md) | PMLR | implemented | 2026-07-26 |
| [design/adapters/cvf.md](design/adapters/cvf.md) | CVF Open Access | implemented | 2026-07-23 |
| [design/adapters/acl-anthology.md](design/adapters/acl-anthology.md) | ACL Anthology | implemented | 2026-07-23 |
| [design/adapters/neurips-proceedings.md](design/adapters/neurips-proceedings.md) | NeurIPS Proceedings | implemented | 2026-07-24 |
| [design/adapters/aaai-ojs.md](design/adapters/aaai-ojs.md) | AAAI OJS | implemented | 2026-07-26 |
| [design/adapters/acm-dl.md](design/adapters/acm-dl.md) | ACM Digital Library（D-020：Phase 2 出列；D-024：Phase 4 重评维持出列，全文改道 unpaywall OA-fallback） | review | 2026-07-23 |
| [design/adapters/ieee-xplore.md](design/adapters/ieee-xplore.md) | IEEE Xplore | review | 2026-07-20 |
| [design/adapters/aggregators.md](design/adapters/aggregators.md) | 聚合元数据源（6 合册） | implemented | 2026-07-26 |
| [design/adapters/elsevier-sd.md](design/adapters/elsevier-sd.md) | Elsevier ScienceDirect（实现级，P4-W0/T3） | implemented | 2026-07-23 |
| [design/adapters/wiley.md](design/adapters/wiley.md) | Wiley Online Library（实现级，P4-W0，D-024 纳入） | implemented | 2026-07-24 |
| [design/adapters/oup-silverchair.md](design/adapters/oup-silverchair.md) | OUP（Silverchair）（实现级，P4-W0/T4） | implemented | 2026-07-23 |
| [design/adapters/uchicago.md](design/adapters/uchicago.md) | UChicago Press | review | 2026-07-21 |
| [design/adapters/informs.md](design/adapters/informs.md) | INFORMS PubsOnline | review | 2026-07-21 |

## catalog/ — venue 清单

| 路径 | 标题 | status | updated |
|---|---|---|---|
| [catalog/README.md](catalog/README.md) | 总览与登记流程 | approved | 2026-07-20 |
| [catalog/publishers-platforms.md](catalog/publishers-platforms.md) | 平台→Adapter 映射总表 | approved | 2026-07-23 |
| [catalog/cs-ai-conferences.md](catalog/cs-ai-conferences.md) | CS/AI 顶会 | approved | 2026-07-23 |
| [catalog/ai-ml-journals.md](catalog/ai-ml-journals.md) | AI/ML/CS 期刊 | review | 2026-07-20 |
| [catalog/economics-journals.md](catalog/economics-journals.md) | 经济学期刊 | approved | 2026-07-26 |
| [catalog/finance-journals.md](catalog/finance-journals.md) | 金融学期刊 | approved | 2026-07-20 |
| [catalog/or-ms-journals.md](catalog/or-ms-journals.md) | OR/MS 期刊 | approved | 2026-07-20 |
| [catalog/preprint-platforms.md](catalog/preprint-platforms.md) | 预印本/WP 平台与订阅范围 | review | 2026-07-24 |

## testing/ — 测试

| 路径 | 标题 | status | updated |
|---|---|---|---|
| [testing/test-plan.md](testing/test-plan.md) | 测试计划与测试类型（T1–T6） | approved | 2026-07-26 |
| [testing/acceptance-criteria.md](testing/acceptance-criteria.md) | 验收标准总表（AC-0…AC-8） | approved | 2026-07-24 |
| testing/records/ | 测试执行留痕（目录，随执行追加） | — | — |
| [testing/records/2026-07-21-phase1-acceptance.md](testing/records/2026-07-21-phase1-acceptance.md) | Phase 1 验收记录（AC-1 全过） | — | 2026-07-21 |
| [testing/records/2026-07-22-arxiv-acceptance.md](testing/records/2026-07-22-arxiv-acceptance.md) | arXiv 验收记录（AC-2.3 双层 PASS） | — | 2026-07-22 |
| [testing/records/2026-07-22-phase2-acceptance.md](testing/records/2026-07-22-phase2-acceptance.md) | Phase 2 验收汇总（AC-2 达成；openreview 在线层待 token） | — | 2026-07-22 |
| [testing/records/2026-07-23-ac35-acceptance.md](testing/records/2026-07-23-ac35-acceptance.md) | AC-3.5 验收记录（五刊零爬取枚举，在线实跑 PASS 建议·待 controller 终签） | — | 2026-07-23 |
| [testing/records/2026-07-23-phase3-acceptance.md](testing/records/2026-07-23-phase3-acceptance.md) | Phase 3 验收汇总记录（AC-3/AC-0/DoD 最终签署：达成） | approved | 2026-07-23 |
| [testing/records/2026-07-23-ac4-acceptance.md](testing/records/2026-07-23-ac4-acceptance.md) | AC-4 离线端到端验收汇总记录（AC-4.2~4.6 离线 DoD 达成，T7a draft；AC-4.1 真实凭证归 T7b） | approved | 2026-07-23 |
| [testing/records/2026-07-24-ac3-acceptance.md](testing/records/2026-07-24-ac3-acceptance.md) | AC-3.1~3.4 独立汇总验收记录（数据模型与合并引擎，Phase 3 判据补记收口） | approved | 2026-07-24 |
| [testing/records/2026-07-24-ac5-acceptance.md](testing/records/2026-07-24-ac5-acceptance.md) | AC-5 离线端到端汇总验收记录（AC-5.1a/5.2/5.3/5.4 离线 DoD 达成，T7 draft；AC-5.1b defer Phase 6） | approved | 2026-07-24 |
| [testing/records/canary/README.md](testing/records/canary/README.md) | Canary 健康矩阵记录目录（`crawler canary --record` 落盘，按日覆盖；+周跑 launchd/cron 模板说明） | approved | 2026-07-26 |

## process/ — 流程规范

| 路径 | 标题 | status | updated |
|---|---|---|---|
| [process/git-workflow.md](process/git-workflow.md) | Git 工作流程 | approved | 2026-07-20 |
| [process/status-workflow.md](process/status-workflow.md) | 双状态机流程 | approved | 2026-07-20 |
| [process/doc-conventions.md](process/doc-conventions.md) | 文档写作与目录规范 | approved | 2026-07-20 |

## research/ — 调研归档

| 路径 | 标题 | status | updated |
|---|---|---|---|
| [research/site-survey/arxiv.md](research/site-survey/arxiv.md) | 勘察：arXiv 全接口 | approved | 2026-07-20 |
| [research/site-survey/openreview.md](research/site-survey/openreview.md) | 勘察：OpenReview API（v1/v2、鉴权、限流、届表） | approved | 2026-07-22 |
| [research/site-survey/acm-dl.md](research/site-survey/acm-dl.md) | 勘察：ACM DL OA（挑战门/ToS/改道评估，D-020 依据） | approved | 2026-07-22 |
| [research/site-survey/pmlr.md](research/site-survey/pmlr.md) | 勘察：PMLR（双托管/bibkey/卷结构） | approved | 2026-07-22 |
| [research/site-survey/cvf.md](research/site-survey/cvf.md) | 勘察：CVF Open Access（列表形态/双代路径） | approved | 2026-07-22 |
| [research/site-survey/acl-anthology.md](research/site-survey/acl-anthology.md) | 勘察：ACL Anthology（GitHub bulk/Findings/许可二分） | approved | 2026-07-22 |
| [research/site-survey/neurips-proceedings.md](research/site-survey/neurips-proceedings.md) | 勘察：NeurIPS Proceedings（格式边界/hash id） | approved | 2026-07-24 |
| [research/site-survey/aaai-ojs.md](research/site-survey/aaai-ojs.md) | 勘察：AAAI OJS（OAI-PMH 主路径/分页/覆盖边界） | approved | 2026-07-26 |
| [research/site-survey/metadata-apis.md](research/site-survey/metadata-apis.md) | 勘察：Crossref/OpenAlex/S2 | approved | 2026-07-22 |
| [research/site-survey/cs-ai-conferences.md](research/site-survey/cs-ai-conferences.md) | 勘察：CS/AI 顶会渠道 | approved | 2026-07-20 |
| [research/site-survey/econ-fin-preprints.md](research/site-survey/econ-fin-preprints.md) | 勘察：SSRN/RePEc/NBER/CEPR | approved | 2026-07-20 |
| [research/site-survey/ssrn.md](research/site-survey/ssrn.md) | 勘察：SSRN（聚合主路径/CF 门界定） | approved | 2026-07-24 |
| [research/site-survey/nber.md](research/site-survey/nber.md) | 勘察：NBER（crossref 主干/开放全文窗） | approved | 2026-07-24 |
| [research/site-survey/aea.md](research/site-survey/aea.md) | 勘察：AEA（crossref 元数据/订阅墙边界） | approved | 2026-07-24 |
| [research/site-survey/econometric-society.md](research/site-survey/econometric-society.md) | 勘察：Econometric Society 三刊（ECMA 迁移分段/TE-QE OJS-OAI） | approved | 2026-07-26 |
| [research/site-survey/repec.md](research/site-survey/repec.md) | 勘察：RePEc 生态（enrich 定位/JEL 独家） | approved | 2026-07-24 |
| [research/site-survey/aggregators-unpaywall-dblp-core.md](research/site-survey/aggregators-unpaywall-dblp-core.md) | 勘察：Unpaywall/DBLP/CORE/Scholar | approved | 2026-07-22 |
| [research/site-survey/ai-journals-preprints-verification.md](research/site-survey/ai-journals-preprints-verification.md) | 核验：AI 期刊+预印本分类 | approved | 2026-07-20 |
| [research/site-survey/publisher-platforms-econfin.md](research/site-survey/publisher-platforms-econfin.md) | 勘察：Econ/Fin 六出版社平台 | approved | 2026-07-20 |
| [research/site-survey/publisher-platforms-cs.md](research/site-survey/publisher-platforms-cs.md) | 勘察：IEEE/AEA/SIAM/MIT Press | approved | 2026-07-20 |
| [research/site-survey/publisher-platforms-p4-recheck.md](research/site-survey/publisher-platforms-p4-recheck.md) | 复核：出版社平台增量勘察（Elsevier/OUP/Wiley/ACM）+凭证核查 [LIVE 07-23] | draft | 2026-07-23 |
| [research/enrich-eval-p6.md](research/enrich-eval-p6.md) | 评估：repec enrich 通道 + ssrn 覆盖候补 ladder（P6-R2，待 fable 裁决） | draft | 2026-07-26 |
| [research/github-similar-projects.md](research/github-similar-projects.md) | 调研：GitHub 同类项目（20 项）+架构总结 | approved | 2026-07-20 |

## diagrams/ — SVG 图（源文件即交付物）

| 文件 | 内容 | 对应文档 |
|---|---|---|
| [diagrams/01-architecture.svg](diagrams/01-architecture.svg) | 六层总体架构 | design/01 |
| [diagrams/02-plugin-modules.svg](diagrams/02-plugin-modules.svg) | 插件两层结构与三族 adapter | design/02 |
| [diagrams/03-pipeline.svg](diagrams/03-pipeline.svg) | 六阶段 pipeline + 任务状态机 + 错误分类 | design/05 |
| [diagrams/04-auth-flow.svg](diagrams/04-auth-flow.svg) | 认证会话生命周期 | design/07 |
| [diagrams/05-data-model.svg](diagrams/05-data-model.svg) | 数据模型 ER | design/06 |
| [diagrams/06-status-machine.svg](diagrams/06-status-machine.svg) | 双状态机与联动 | process/status-workflow |

## logs/ · reports/ — 留痕（无 front matter 义务）

| 路径 | 内容 |
|---|---|
| logs/ | 每 session 工作日志（YYYY-MM-DD-session-NNN.md，现有 001–007） |
| [reports/2026-07-20-phase0-report.md](reports/2026-07-20-phase0-report.md) | Phase 0 阶段报告（DoD 判定） |
| [reports/2026-07-20-consistency-review.md](reports/2026-07-20-consistency-review.md) | 一致性审查第 1 轮（需求矩阵 + 13 项修复，D-015） |
| [reports/2026-07-21-audit-round2.md](reports/2026-07-21-audit-round2.md) | 深度审计第 2 轮（语义级 + 可读性增强，D-016） |
| [reports/2026-07-21-phase1-report.md](reports/2026-07-21-phase1-report.md) | Phase 1 阶段报告（DoD 判定 + 终审 + Phase 2 检查单） |
| [reports/2026-07-22-phase2-report.md](reports/2026-07-22-phase2-report.md) | Phase 2 阶段报告（DoD 判定 + 终审 + Phase 3 检查单） |
| [reports/2026-07-23-phase3-report.md](reports/2026-07-23-phase3-report.md) | Phase 3 阶段报告（DoD 判定 + 收尾中草稿，判定列待 controller 终验签署 + Phase 4 检查单） |
| [reports/2026-07-23-phase4-report.md](reports/2026-07-23-phase4-report.md) | Phase 4 阶段报告（DoD 判定 + AC-0 系统性扫描 + 收尾中草稿，判定列待 controller 终验签署 + Phase 5 检查单） |
| [reports/2026-07-24-phase5-report.md](reports/2026-07-24-phase5-report.md) | Phase 5 阶段报告（8 卡 4 波次交付 + D-027/028/029 + AC-5 引用 + 事件教训 + Phase 6 检查单，判定：**达成**——controller 合并裁决签署，tag `phase-5`） |
| [reports/2026-07-24-post-phase5-audit.md](reports/2026-07-24-post-phase5-audit.md) | Phase 5 终审后独立全库审计报告（8 subagent：4 Opus 深审+4 Sonnet 面审；八域附条件达标、零 P0；P1×3/P2×12 台账 + AC-0 复核全 PASS + Phase 6 处置建议） |
