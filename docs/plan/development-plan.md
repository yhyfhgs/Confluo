---
title: 开发计划（Phase 0–7）
status: approved
owner: fable5
updated: 2026-07-21
---

# 开发计划

> 原则：文档先行（设计 `approved` 才开工）、垂直切片（每阶段交付端到端可用的能力，而非水平铺框架）、脆弱面后置（认证类 adapter 放在框架与开源源稳定之后）。
> 各阶段验收标准的完整定义见 [testing/acceptance-criteria.md](../testing/acceptance-criteria.md)，此处只列 DoD 摘要。

## 阶段总览

| Phase | 名称 | 交付物 | 依赖 | 状态 |
|---|---|---|---|---|
| 0 | 设计与文本系统 | 全套设计文档、SVG、清单、流程规范 | — | done |
| 1 | 核心框架 | plugin registry、数据模型与 DB、pipeline 骨架、CLI 骨架、日志 | 0 | done |
| 2 | Open-Access MVP | arXiv + OpenReview + PMLR + CVF + ACL Anthology + NeurIPS + AAAI + ACM adapters | 1 | **in_progress** |
| 3 | 聚合元数据层 | Crossref/OpenAlex/DBLP/S2/Unpaywall 客户端与 metadata spine | 1 | **done** |
| 4 | 认证框架 + 出版社 adapters | AuthProvider 四实现；Elsevier/Wiley/OUP/UChicago/INFORMS/IEEE/ACM/AAAI | 1,3 | planned |
| 5 | SSRN 与特殊源 | SSRN、NBER、AEA、Econometric Society、RePEc adapters | 2,4 | planned |
| 6 | 订阅与搜索 | topic/tag 订阅 DSL、增量 watch、dry-run、日报 | 2,3 | planned |
| 7 | 全文抽取与库增强 | GROBID 集成、全文索引、preprint↔正式版关联审核工具 | 2–5 | planned |

## Phase 0 — 设计与文本系统

**目标**：完成全部设计文档，达到"任何一个模块可以按文档独立开工"的程度。

交付清单：
- [x] 文本系统目录结构 + git 仓库
- [ ] plan/：development-plan、progress、decision-log
- [ ] design/：00–09 十篇核心设计
- [ ] design/adapters/：模板 + 首批平台 adapter 设计（≥12 个平台）
- [ ] catalog/：7 篇 venue/平台清单
- [ ] testing/：test-plan、acceptance-criteria
- [ ] process/：git-workflow、status-workflow、doc-conventions
- [ ] diagrams/：6 张 SVG
- [ ] research/：调研归档（类似项目、数据源勘察）
- [ ] AGENTS.md、README、INDEX

**DoD**：INDEX 中所有 Phase-0 文档状态 ≥ `review`；核心十篇 + 流程三篇 `approved`；SVG 与文档交叉引用一致；git 初始提交完成。

## Phase 1 — 核心框架

**范围**：`src/core` —— VenueRegistry（YAML 加载/校验/entry-point 扫描）、SQLite schema v1 + 迁移器、Task 队列与状态机、六阶段 pipeline 执行器（先串行）、per-domain 限速器、结构化日志、`crawler` CLI 骨架（venues/timeline/pull/status 子命令）、fixture 回放测试基建。

**明确不做**：任何真实站点 adapter（用一个 `mock_platform` 假 adapter 驱动全部测试）。

**DoD**：mock adapter 走通六阶段端到端；断点续爬（kill -9 后重跑不重复不遗漏）通过；单测覆盖核心 ≥80%；文档 01/02/05/06 转 `implemented`。

## Phase 2 — Open-Access MVP

**范围与顺序**（每个 adapter 独立分支、独立验收）：
1. `arxiv`（API + OAI-PMH + listing，含分类过滤）
2. `openreview`（API v2：ICLR/NeurIPS 评审与 camera-ready）
3. `pmlr`（ICML/AISTATS/COLT/UAI 卷结构）
4. `cvf`（CVPR/ICCV/WACV open access）
5. `acl_anthology`（bulk 数据仓库优先）
6. `neurips_proceedings`（papers.nips.cc 历史全量）
7. `aaai_ojs`（AAAI/AIES 的 OJS 结构）
8. ~~`acm_dl`~~（**Phase 2 出列，D-020 2026-07-22**：OA 后实测 Cloudflare 挑战门+ToS 禁自动下载，红线优先无合规路径；Phase 4 重评。2026-07-21 曾按 D-013 勘误补入）

**DoD**：验收场景 AC-2.x 全过（如"列出 ICLR 2024 全部接收论文并下载指定 10 篇"）；每个 adapter 有离线 fixture 测试 + 1 个限量在线冒烟；canary 监控注册。

## Phase 3 — 聚合元数据层

**范围**：Crossref（按 ISSN 枚举 DOI）、OpenAlex（venue/works 过滤——2026-07-22 W0 双评审判定收窄为 enrich 补充通道，见 aggregators.md §5.3/plan §2-5，非枚举源）、DBLP（conf 卷目录）、Semantic Scholar（补充摘要/引用）、Unpaywall（OA 副本发现）。实现 `metadata_source` 与 `fulltext_source` 分离的 VenueSpec 语义（D-005）。

**DoD**：任选 5 本期刊（含 QJE、JFE）不写任何出版社爬虫即可产出完整期目与论文清单；OA 副本命中率报告生成。

## Phase 4 — 认证框架 + 出版社 adapters

**范围**：AuthProvider（CookieSession/EZProxy/SSOFlow/APIKey）、凭证库、`crawler auth login/status` CLI、session 健康检查；随后按平台推进：`elsevier_sd`（优先官方 API）、`wiley`（优先 TDM API）、`oup_silverchair`、`uchicago`、`informs`、`ieee_xplore`、`acm_dl`、`cambridge`、`springer`、`jstor`。

**DoD**：验收场景 AC-4.x（如"保存的机构 session 下载 1 篇 JFE 正式版 PDF；session 过期后被正确检测并提示重登"）；全部认证 adapter 默认限速符合各自文档声明；BLOCKED 人工介入流程演练通过。

## Phase 5 — SSRN 与特殊源

**范围**：`ssrn`（D-011 双模式）、`nber`、`aea`（AER 及 AEJ 系）、`econometric_society`（ECMA + 开放的 TE/QE）、`repec`。

**DoD**：AC-5.x（如"按 FEN 子网增量拉取 SSRN 近 7 天新工作论文清单并按配额下载"）。

## Phase 6 — 订阅与搜索

**范围**：topic/tag 订阅 DSL、`crawler watch` 增量调度、dry-run 计数预览、数量护栏、每日摘要报告（markdown）。

**DoD**：AC-6.x（"3 个自定义 topic 连续 7 天增量无重复无遗漏；单日超阈值时正确熔断并报告"）。

## Phase 7 — 全文抽取与库增强

**范围**：GROBID 可选集成、全文倒排/向量索引（可选）、candidate_duplicate 审核 CLI、preprint↔published 关联报告。

**DoD**：AC-7.x；全库一致性校验工具（文件↔DB 对账）通过。

## 里程碑与节奏

- 每 Phase 完成：打 tag `phase-N`、写 `docs/reports/` 阶段报告、更新 progress.md 与 INDEX。
- 每个 adapter 完成：在 catalog 对应 venue 行标注 `supported_since: phase-N`。
- 风险缓冲：Phase 4 每个出版社平台预留 1 次"站点改版重勘察"迭代。

## 风险登记（Top 5）

| # | 风险 | 影响 | 缓解 |
|---|---|---|---|
| R1 | 出版社反爬升级 / Cloudflare 拦截 | Phase 4/5 进度 | API 优先（D-006）；保守限速；BLOCKED 人工通道；canary 早发现 |
| R2 | 机构 SSO 含 MFA，无法全自动 | 认证自动化程度 | 设计即接受"首登人工"（D-006），只自动化续期检测 |
| R3 | 站点改版导致 adapter 腐化 | 长期维护成本 | fixture 快照测试 + 每周 canary + adapter 状态页（INDEX） |
| R4 | SSRN/Google Scholar 无官方 API | 覆盖率 | SSRN 走浏览器自动化+严限速；Scholar 明确不做主源（仅人工辅助） |
| R5 | 范围膨胀（venue 清单无限扩） | 永远做不完 | catalog 分 tier：T1 必做 / T2 配置即得 / T3 暂缓；每 Phase 锁定范围 |
