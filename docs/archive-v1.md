---
title: v1 归档说明与路径索引
status: approved
owner: opus5.5-primary
updated: 2026-09-27
---

# v1 归档说明与路径索引

> 2026-09-27 起，main 只保留 v2 的调研、计划与 demo。v1 的全部代码、测试、VenueSpec、配置、脚本与设计文档，完整保留在分支 **`archive/v1`** 与附注标签 **`v1-final`**，二者都指向提交 `b1175f8`，即原 `fix/audit-2026-07` 分支末端（main 的 Phase 0–7 + 2026-07 审计修复 R1–R4）。
> v2 文档中凡是指向 v1 文件的链接，都会跳到本页对应路径的锚点；链接文字保持原样。

## 1. 怎么查看 v1

```bash
git show archive/v1:docs/design/06-data-model.md      # 只看某个文件
git switch archive/v1                                  # 切换到 v1（回到 v2：git switch main）
git worktree add ../paper-crawler-v1 archive/v1        # 并排对照：另开一个工作树
```

在 v1 工作树里，`uv sync --extra auth && make check` 仍然可以跑 v1 的门禁。

## 2. v1 概况

- **实现**：Python 3.12 单用户 CLI，六阶段 pipeline（discover → enumerate → resolve → fetch → extract → ingest）；21 个平台 adapter、62 个 VenueSpec；SQLite + FTS5；订阅 DSL + watermark + 日报；认证框架（cookie、EZproxy、SSO、API key）。
- **里程碑**：Phase 0–7 全部完成（标签 `phase-0` … `phase-7`）；Phase 7 收官门禁为 4617 passed / 31 skipped，覆盖率 98.98%；之后是 2026-07 终审审计修复批 R1–R4。
- **ADR**：D-001…D-039 仍保留在 main 的 [decision-log](plan/decision-log.md) 中作为历史；v2 草案 D-040 起会点名修订或取代其中的相关条目。
- **归档规模**：776 个受控文件：`tests` 431、`src` 134、`docs` 123、`venues` 62、`subscriptions` 10、`scripts` 7、`config` 3、`.gitignore` 1、`AGENTS.md` 1、`Makefile` 1、`README.md` 1、`pyproject.toml` 1、`uv.lock` 1。

## 3. 路径索引

v1 的全部文档按目录列出；另外单列 v2 文档引用到的 v1 代码、配图与目录。

### docs/

| 路径 | 标题（v1 front matter） | v1 status |
|---|---|---|
| <a id="docs-glossary-md"></a>`docs/GLOSSARY.md` | 术语表（Glossary） | review |
| <a id="docs-index-md"></a>`docs/INDEX.md` | 文档索引（唯一权威清单） | — |

### docs/catalog/

| 路径 | 标题（v1 front matter） | v1 status |
|---|---|---|
| <a id="docs-catalog-readme-md"></a>`docs/catalog/README.md` | Venue Catalog 总览与登记流程 | approved |
| <a id="docs-catalog-ai-ml-journals-md"></a>`docs/catalog/ai-ml-journals.md` | AI/ML/CS 期刊清单 | review |
| <a id="docs-catalog-cs-ai-conferences-md"></a>`docs/catalog/cs-ai-conferences.md` | CS/AI 顶会清单 | approved |
| <a id="docs-catalog-economics-journals-md"></a>`docs/catalog/economics-journals.md` | 经济学期刊清单 | approved |
| <a id="docs-catalog-finance-journals-md"></a>`docs/catalog/finance-journals.md` | 金融学期刊清单 | approved |
| <a id="docs-catalog-or-ms-journals-md"></a>`docs/catalog/or-ms-journals.md` | 运筹 / 管理科学 期刊清单 | approved |
| <a id="docs-catalog-preprint-platforms-md"></a>`docs/catalog/preprint-platforms.md` | 预印本/工作论文平台清单与订阅范围 | review |
| <a id="docs-catalog-publishers-platforms-md"></a>`docs/catalog/publishers-platforms.md` | 平台 → Adapter 映射总表 | approved |

### docs/design/

| 路径 | 标题（v1 front matter） | v1 status |
|---|---|---|
| <a id="docs-design-00-requirements-md"></a>`docs/design/00-requirements.md` | 需求规格与边界 | approved |
| <a id="docs-design-01-architecture-md"></a>`docs/design/01-architecture.md` | 总体架构 | implemented |
| <a id="docs-design-02-plugin-framework-md"></a>`docs/design/02-plugin-framework.md` | 可插拔框架（Platform Adapter × Venue Spec） | implemented |
| <a id="docs-design-03-open-access-module-md"></a>`docs/design/03-open-access-module.md` | Open-Access 获取模块 | approved |
| <a id="docs-design-04-auth-gated-module-md"></a>`docs/design/04-auth-gated-module.md` | Auth-Gated 获取模块 | implemented |
| <a id="docs-design-05-pipeline-md"></a>`docs/design/05-pipeline.md` | 六阶段 Pipeline 与任务系统 | implemented |
| <a id="docs-design-06-data-model-md"></a>`docs/design/06-data-model.md` | 数据模型与入库设计 | implemented |
| <a id="docs-design-07-auth-session-md"></a>`docs/design/07-auth-session.md` | 认证与会话管理 | implemented |
| <a id="docs-design-08-venue-tracking-md"></a>`docs/design/08-venue-tracking.md` | Venue 时间轴与年度追踪 | approved |
| <a id="docs-design-09-search-filter-md"></a>`docs/design/09-search-filter.md` | 主题订阅与精确搜索 | implemented |
| <a id="docs-design-10-config-layout-md"></a>`docs/design/10-config-layout.md` | 配置分层与敏感边界规范 | implemented |
| <a id="docs-design-11-browser-fetch-md"></a>`docs/design/11-browser-fetch.md` | Browser-Fetch 横切件（浏览器上下文取回通道）实现级详设 | approved |
| <a id="docs-design-12-fulltext-extract-md"></a>`docs/design/12-fulltext-extract.md` | 全文抽取（stage 5 extract）实现级详设 | approved |
| <a id="docs-design-adapters-readme-md"></a>`docs/design/adapters/README.md` | Adapter 设计文档模板与索引 | approved |
| <a id="docs-design-adapters-aaai-ojs-md"></a>`docs/design/adapters/aaai-ojs.md` | Adapter 设计 · AAAI OJS | implemented |
| <a id="docs-design-adapters-acl-anthology-md"></a>`docs/design/adapters/acl-anthology.md` | Adapter 设计 · ACL Anthology | implemented |
| <a id="docs-design-adapters-acm-dl-md"></a>`docs/design/adapters/acm-dl.md` | Adapter 设计 · ACM Digital Library | review |
| <a id="docs-design-adapters-aea-md"></a>`docs/design/adapters/aea.md` | Adapter 设计 · AEA（AER + AEJ 四系 + AER:Insights + JEL/JEP，实现级） | implemented |
| <a id="docs-design-adapters-aggregators-md"></a>`docs/design/adapters/aggregators.md` | Adapter 设计 · 聚合元数据源（Crossref/DBLP/OpenAlex/S2/Unpaywall/CORE/RePEc） | implemented |
| <a id="docs-design-adapters-arxiv-md"></a>`docs/design/adapters/arxiv.md` | Adapter 设计 · arXiv | implemented |
| <a id="docs-design-adapters-cvf-md"></a>`docs/design/adapters/cvf.md` | Adapter 设计 · CVF Open Access | implemented |
| <a id="docs-design-adapters-econsoc-md"></a>`docs/design/adapters/econsoc.md` | Adapter 设计 · Econometric Society（econsoc，实现级） | implemented |
| <a id="docs-design-adapters-elsevier-sd-md"></a>`docs/design/adapters/elsevier-sd.md` | Adapter 设计 · Elsevier ScienceDirect（实现级） | implemented |
| <a id="docs-design-adapters-ieee-xplore-md"></a>`docs/design/adapters/ieee-xplore.md` | Adapter 设计 · IEEE Xplore | review |
| <a id="docs-design-adapters-informs-md"></a>`docs/design/adapters/informs.md` | Adapter 设计 · INFORMS PubsOnline | review |
| <a id="docs-design-adapters-nber-md"></a>`docs/design/adapters/nber.md` | Adapter 设计 · NBER Working Papers（实现级） | implemented |
| <a id="docs-design-adapters-neurips-proceedings-md"></a>`docs/design/adapters/neurips-proceedings.md` | Adapter 设计 · NeurIPS Proceedings | implemented |
| <a id="docs-design-adapters-openreview-md"></a>`docs/design/adapters/openreview.md` | Adapter 设计 · OpenReview | implemented |
| <a id="docs-design-adapters-oup-silverchair-md"></a>`docs/design/adapters/oup-silverchair.md` | Adapter 设计 · OUP（Silverchair 平台，实现级） | implemented |
| <a id="docs-design-adapters-pmlr-md"></a>`docs/design/adapters/pmlr.md` | Adapter 设计 · PMLR | implemented |
| <a id="docs-design-adapters-ssrn-md"></a>`docs/design/adapters/ssrn.md` | Adapter 设计 · SSRN（实现级 · 聚合元数据主路径） | implemented |
| <a id="docs-design-adapters-uchicago-md"></a>`docs/design/adapters/uchicago.md` | Adapter 设计 · University of Chicago Press | review |
| <a id="docs-design-adapters-wiley-md"></a>`docs/design/adapters/wiley.md` | Adapter 设计 · Wiley Online Library（实现级） | implemented |
| <a id="docs-design-auth-framework-md"></a>`docs/design/auth-framework.md` | 认证框架实现级详设（AuthProvider 四实现 + 凭证库 + CLI + pipeline 接缝） | implemented |

### docs/logs/

| 路径 | 标题（v1 front matter） | v1 status |
|---|---|---|
| <a id="docs-logs-2026-07-20-session-001-md"></a>`docs/logs/2026-07-20-session-001.md` | 2026-07-20 Session 001（补记） | — |
| <a id="docs-logs-2026-07-20-session-002-md"></a>`docs/logs/2026-07-20-session-002.md` | 2026-07-20 Session 002 | — |
| <a id="docs-logs-2026-07-20-session-003-md"></a>`docs/logs/2026-07-20-session-003.md` | 2026-07-20 Session 003 | — |
| <a id="docs-logs-2026-07-21-session-004-md"></a>`docs/logs/2026-07-21-session-004.md` | 2026-07-21 Session 004 | — |
| <a id="docs-logs-2026-07-21-session-005-md"></a>`docs/logs/2026-07-21-session-005.md` | Session 005 · 2026-07-21 · Phase 1 核心框架全程实施 | — |
| <a id="docs-logs-2026-07-22-session-006-md"></a>`docs/logs/2026-07-22-session-006.md` | Session 006 · 2026-07-21~22 · Phase 2 Open-Access MVP 全程实施 | — |
| <a id="docs-logs-2026-07-26-session-007-md"></a>`docs/logs/2026-07-26-session-007.md` | Session 007（2026-07-24 → 2026-07-26 凌晨收尾） | — |
| <a id="docs-logs-2026-07-26-session-008-md"></a>`docs/logs/2026-07-26-session-008.md` | 2026-07-26 · session 008 —— acl_anthology SI 附件 URL 前缀 LIVE 核实闭合 | — |
| <a id="docs-logs-2026-07-26-session-009-md"></a>`docs/logs/2026-07-26-session-009.md` | 2026-07-26 · session 009 —— Phase 6 全程（订阅与搜索） | — |
| <a id="docs-logs-2026-07-26-session-010-md"></a>`docs/logs/2026-07-26-session-010.md` | 2026-07-26 · session-010 —— D-032：config-home 迁入仓库根（用户架构令：config 归集） | — |

### docs/plan/

| 路径 | 标题（v1 front matter） | v1 status |
|---|---|---|
| <a id="docs-plan-decision-log-md"></a>`docs/plan/decision-log.md` | 架构决策记录（ADR） | approved |
| <a id="docs-plan-development-plan-md"></a>`docs/plan/development-plan.md` | 开发计划（Phase 0–7） | approved |
| <a id="docs-plan-phase1-implementation-plan-md"></a>`docs/plan/phase1-implementation-plan.md` | Phase 1 实施计划（核心框架） | approved |
| <a id="docs-plan-phase2-implementation-plan-md"></a>`docs/plan/phase2-implementation-plan.md` | Phase 2 实施计划 — Open-Access MVP | approved |
| <a id="docs-plan-phase3-implementation-plan-md"></a>`docs/plan/phase3-implementation-plan.md` | Phase 3 实施计划 — 聚合元数据层 | approved |
| <a id="docs-plan-phase4-implementation-plan-md"></a>`docs/plan/phase4-implementation-plan.md` | Phase 4 实施计划 — 认证框架 + 出版社 adapters | approved |
| <a id="docs-plan-phase5-implementation-plan-md"></a>`docs/plan/phase5-implementation-plan.md` | Phase 5 实施计划 — SSRN 与特殊经济学源 adapters | approved |
| <a id="docs-plan-phase6-implementation-plan-md"></a>`docs/plan/phase6-implementation-plan.md` | Phase 6 实施计划（订阅与搜索：DSL + watch + 护栏 + 日报 任务切分） | approved |
| <a id="docs-plan-phase7-implementation-plan-md"></a>`docs/plan/phase7-implementation-plan.md` | Phase 7 实施计划 — 全文抽取与库增强 | approved |
| <a id="docs-plan-progress-md"></a>`docs/plan/progress.md` | 项目进度跟踪 | approved |

### docs/process/

| 路径 | 标题（v1 front matter） | v1 status |
|---|---|---|
| <a id="docs-process-doc-conventions-md"></a>`docs/process/doc-conventions.md` | 文档写作与目录规范 | approved |
| <a id="docs-process-git-workflow-md"></a>`docs/process/git-workflow.md` | Git 工作流程规范 | approved |
| <a id="docs-process-online-budget-md"></a>`docs/process/online-budget.md` | 在线预算共享行记账规范 | approved |
| <a id="docs-process-status-workflow-md"></a>`docs/process/status-workflow.md` | 文档与代码状态流程 | approved |

### docs/reports/

| 路径 | 标题（v1 front matter） | v1 status |
|---|---|---|
| <a id="docs-reports-2026-07-20-consistency-review-md"></a>`docs/reports/2026-07-20-consistency-review.md` | Phase-0 收官一致性审查报告（开发前第一次修订） | — |
| <a id="docs-reports-2026-07-20-phase0-report-md"></a>`docs/reports/2026-07-20-phase0-report.md` | Phase 0 阶段报告 — 设计与文本系统 | — |
| <a id="docs-reports-2026-07-21-audit-round2-md"></a>`docs/reports/2026-07-21-audit-round2.md` | 深度审计第 2 轮报告 — 语义级一致性 + 可读性增强 | — |
| <a id="docs-reports-2026-07-21-phase1-report-md"></a>`docs/reports/2026-07-21-phase1-report.md` | Phase 1 阶段报告 — 核心框架（2026-07-21） | — |
| <a id="docs-reports-2026-07-22-phase2-report-md"></a>`docs/reports/2026-07-22-phase2-report.md` | Phase 2 阶段报告 — Open-Access MVP（2026-07-22） | — |
| <a id="docs-reports-2026-07-23-phase3-report-md"></a>`docs/reports/2026-07-23-phase3-report.md` | Phase 3 阶段报告 — 聚合元数据层（2026-07-23） | — |
| <a id="docs-reports-2026-07-23-phase4-report-md"></a>`docs/reports/2026-07-23-phase4-report.md` | Phase 4 阶段报告 — 认证框架 + 出版社 adapters（2026-07-23） | — |
| <a id="docs-reports-2026-07-24-phase5-report-md"></a>`docs/reports/2026-07-24-phase5-report.md` | Phase 5 阶段报告 — SSRN 与特殊经济学源 adapters（2026-07-24） | — |
| <a id="docs-reports-2026-07-24-post-phase5-audit-md"></a>`docs/reports/2026-07-24-post-phase5-audit.md` | Phase 5 终审后独立代码审计报告（2026-07-24） | — |
| <a id="docs-reports-2026-07-26-phase6-report-md"></a>`docs/reports/2026-07-26-phase6-report.md` | Phase 6 阶段报告 — 订阅与搜索（2026-07-26） | — |
| <a id="docs-reports-2026-07-27-db-construction-audit-md"></a>`docs/reports/2026-07-27-db-construction-audit.md` | 全库 `Database` 构造审计报告（2026-07-27，Phase 7 T17） | — |
| <a id="docs-reports-2026-07-27-phase7-report-md"></a>`docs/reports/2026-07-27-phase7-report.md` | Phase 7 阶段报告 — 全文抽取与库增强（2026-07-27） | — |

### docs/research/

| 路径 | 标题（v1 front matter） | v1 status |
|---|---|---|
| <a id="docs-research-enrich-eval-p6-md"></a>`docs/research/enrich-eval-p6.md` | R2 合并评估：repec aggregator-enrich 通道 + ssrn 覆盖候补 ladder | approved |
| <a id="docs-research-github-similar-projects-md"></a>`docs/research/github-similar-projects.md` | 调研：GitHub 同类论文获取项目（20 项）与架构横向总结 | approved |
| <a id="docs-research-site-survey-aaai-ojs-md"></a>`docs/research/site-survey/aaai-ojs.md` | 勘察：AAAI OJS（OAI-PMH 主路径/分页/覆盖边界） | approved |
| <a id="docs-research-site-survey-acl-anthology-md"></a>`docs/research/site-survey/acl-anthology.md` | 勘察：ACL Anthology（GitHub bulk/Findings 结构/许可二分） | approved |
| <a id="docs-research-site-survey-acm-dl-md"></a>`docs/research/site-survey/acm-dl.md` | 勘察：ACM DL Open Access（挑战门/ToS/改道评估） | approved |
| <a id="docs-research-site-survey-aea-md"></a>`docs/research/site-survey/aea.md` | 站点勘察：AEA（aeaweb.org / pubs.aeaweb.org）— AER + AEJ 四系 + AER:Insights + JEL/JEP | approved |
| <a id="docs-research-site-survey-aggregators-unpaywall-dblp-core-md"></a>`docs/research/site-survey/aggregators-unpaywall-dblp-core.md` | 站点勘察：Unpaywall / DBLP / CORE / Google Scholar | approved |
| <a id="docs-research-site-survey-ai-journals-preprints-verification-md"></a>`docs/research/site-survey/ai-journals-preprints-verification.md` | 事实核验：AI/ML 期刊与预印本平台分类体系（subagent 原始报告归档） | approved |
| <a id="docs-research-site-survey-arxiv-md"></a>`docs/research/site-survey/arxiv.md` | 站点勘察：arXiv（全接口） | approved |
| <a id="docs-research-site-survey-cs-ai-conferences-md"></a>`docs/research/site-survey/cs-ai-conferences.md` | 站点勘察：CS/AI 顶会获取渠道（原始调研） | approved |
| <a id="docs-research-site-survey-cvf-md"></a>`docs/research/site-survey/cvf.md` | 勘察：CVF Open Access（列表形态/双代路径/供给面） | approved |
| <a id="docs-research-site-survey-econ-fin-preprints-md"></a>`docs/research/site-survey/econ-fin-preprints.md` | 站点勘察：Econ/Fin 预印本与工作论文（SSRN/RePEc/NBER/CEPR） | approved |
| <a id="docs-research-site-survey-econometric-society-md"></a>`docs/research/site-survey/econometric-society.md` | 勘察：Econometric Society 三刊（ECMA/TE/QE）——平台迁移实测与 adapter 路线 | approved |
| <a id="docs-research-site-survey-metadata-apis-md"></a>`docs/research/site-survey/metadata-apis.md` | 站点勘察：元数据 API（Crossref / OpenAlex / Semantic Scholar） | approved |
| <a id="docs-research-site-survey-nber-md"></a>`docs/research/site-survey/nber.md` | 站点勘察：NBER Working Papers（nber.org / back.nber.org） | approved |
| <a id="docs-research-site-survey-neurips-proceedings-md"></a>`docs/research/site-survey/neurips-proceedings.md` | 勘察：NeurIPS Proceedings（格式边界/hash id/关联线索） | approved |
| <a id="docs-research-site-survey-openreview-md"></a>`docs/research/site-survey/openreview.md` | 勘察：OpenReview API（v1/v2、鉴权、限流、届表） | approved |
| <a id="docs-research-site-survey-pmlr-md"></a>`docs/research/site-survey/pmlr.md` | 勘察：PMLR（双托管/bibkey/卷结构） | approved |
| <a id="docs-research-site-survey-publisher-platforms-cs-md"></a>`docs/research/site-survey/publisher-platforms-cs.md` | 站点勘察：CS 学会与其他出版平台（IEEE/AEA/SIAM/MIT Press） | approved |
| <a id="docs-research-site-survey-publisher-platforms-econfin-md"></a>`docs/research/site-survey/publisher-platforms-econfin.md` | 站点勘察：经济金融闭源出版社六平台（Elsevier/Wiley/OUP/UChicago/Cambridge/JSTOR） | approved |
| <a id="docs-research-site-survey-publisher-platforms-p4-recheck-md"></a>`docs/research/site-survey/publisher-platforms-p4-recheck.md` | 站点勘察增量复核 · 出版社平台（Elsevier/OUP/Wiley/ACM）+ 凭证核查 · Phase 4 W0 | draft |
| <a id="docs-research-site-survey-repec-md"></a>`docs/research/site-survey/repec.md` | 勘察：RePEc 生态（IDEAS/EconPapers）——角色定位与 adapter 优先级裁决输入 | approved |
| <a id="docs-research-site-survey-ssrn-md"></a>`docs/research/site-survey/ssrn.md` | 站点勘察：SSRN（Elsevier/Cloudflare 高危站 · 聚合 API 优先） | approved |

### docs/testing/

| 路径 | 标题（v1 front matter） | v1 status |
|---|---|---|
| <a id="docs-testing-acceptance-criteria-md"></a>`docs/testing/acceptance-criteria.md` | 验收标准总表 | approved |
| <a id="docs-testing-records-2026-07-21-phase1-acceptance-md"></a>`docs/testing/records/2026-07-21-phase1-acceptance.md` | Phase 1 验收执行记录（AC-1.1 ~ AC-1.6） | — |
| <a id="docs-testing-records-2026-07-22-arxiv-acceptance-md"></a>`docs/testing/records/2026-07-22-arxiv-acceptance.md` | arXiv 验收执行记录（AC-2.3） | approved |
| <a id="docs-testing-records-2026-07-22-phase2-acceptance-md"></a>`docs/testing/records/2026-07-22-phase2-acceptance.md` | Phase 2 验收汇总记录（AC-2） | approved |
| <a id="docs-testing-records-2026-07-23-ac35-acceptance-md"></a>`docs/testing/records/2026-07-23-ac35-acceptance.md` | 期刊聚合层验收执行记录（AC-3.5 · 五刊零爬取枚举全史） | approved |
| <a id="docs-testing-records-2026-07-23-ac4-acceptance-md"></a>`docs/testing/records/2026-07-23-ac4-acceptance.md` | AC-4 离线端到端验收汇总记录 — 认证与出版社（离线载体收口） | approved |
| <a id="docs-testing-records-2026-07-23-phase3-acceptance-md"></a>`docs/testing/records/2026-07-23-phase3-acceptance.md` | Phase 3 验收汇总记录 — 聚合元数据层 | approved |
| <a id="docs-testing-records-2026-07-24-ac3-acceptance-md"></a>`docs/testing/records/2026-07-24-ac3-acceptance.md` | AC-3.1~3.4 独立汇总验收记录 — 数据模型与合并引擎（Phase 3 补记收口） | approved |
| <a id="docs-testing-records-2026-07-24-ac5-acceptance-md"></a>`docs/testing/records/2026-07-24-ac5-acceptance.md` | AC-5 离线端到端汇总验收记录 — ssrn/nber/aea/econsoc 四 adapter（Phase 5 离线口径） | approved |
| <a id="docs-testing-records-2026-07-26-ac6-acceptance-md"></a>`docs/testing/records/2026-07-26-ac6-acceptance.md` | AC-6 离线端到端验收 + 在线冒烟记录 — 订阅与搜索（Phase 6 T9） | approved |
| <a id="docs-testing-records-2026-07-27-ac7-acceptance-md"></a>`docs/testing/records/2026-07-27-ac7-acceptance.md` | AC-7 验收记录 — 全文抽取与库增强（Phase 7，T18 骨架 + T19 在线批回填） | approved |
| <a id="docs-testing-records-canary-2026-07-23-canary-md"></a>`docs/testing/records/canary/2026-07-23-canary.md` | Canary 健康矩阵 — 2026-07-23 | — |
| <a id="docs-testing-records-canary-readme-md"></a>`docs/testing/records/canary/README.md` | Canary 健康矩阵记录目录 | approved |
| <a id="docs-testing-test-plan-md"></a>`docs/testing/test-plan.md` | 测试计划与测试类型 | approved |

### v2 文档引用到的其他 v1 路径（代码、目录、根文件）

| 路径 | 说明 | — |
|---|---|---|
| <a id="docs-diagrams-03-pipeline-svg"></a>`docs/diagrams/03-pipeline.svg` | v1 文件 | — |
| <a id="docs-research-site-survey"></a>`docs/research/site-survey` | v1 目录 | — |
| <a id="src-paper-crawler-adapters-dblp-adapter-py"></a>`src/paper_crawler/adapters/dblp/adapter.py` | v1 文件 | — |
| <a id="src-paper-crawler-storage-migrations-0001-init-sql"></a>`src/paper_crawler/storage/migrations/0001_init.sql` | v1 文件 | — |
| <a id="src-paper-crawler-storage-migrations-0003-paper-weak-key-sql"></a>`src/paper_crawler/storage/migrations/0003_paper_weak_key.sql` | v1 文件 | — |
| <a id="src-paper-crawler-storage-migrations-0004-fulltext-asset-sql"></a>`src/paper_crawler/storage/migrations/0004_fulltext_asset.sql` | v1 文件 | — |
| <a id="src-paper-crawler-storage-migrations-0005-fts-paper-sql"></a>`src/paper_crawler/storage/migrations/0005_fts_paper.sql` | v1 文件 | — |
| <a id="src-paper-crawler-storage-migrations-0006-perf-indexes-sql"></a>`src/paper_crawler/storage/migrations/0006_perf_indexes.sql` | v1 文件 | — |
| <a id="src-paper-crawler-storage-migrations-0007-enrich-cursor-sql"></a>`src/paper_crawler/storage/migrations/0007_enrich_cursor.sql` | v1 文件 | — |

### docs/diagrams/（v1 配图）

| 路径 | 说明 | — |
|---|---|---|
| <a id="docs-diagrams-01-architecture-svg"></a>`docs/diagrams/01-architecture.svg` | v1 配图 | — |
| <a id="docs-diagrams-02-plugin-modules-svg"></a>`docs/diagrams/02-plugin-modules.svg` | v1 配图 | — |
| <a id="docs-diagrams-04-auth-flow-svg"></a>`docs/diagrams/04-auth-flow.svg` | v1 配图 | — |
| <a id="docs-diagrams-05-data-model-svg"></a>`docs/diagrams/05-data-model.svg` | v1 配图 | — |
| <a id="docs-diagrams-06-status-machine-svg"></a>`docs/diagrams/06-status-machine.svg` | v1 配图 | — |
