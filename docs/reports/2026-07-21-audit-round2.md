# 深度审计第 2 轮报告 — 语义级一致性 + 可读性增强

> 日期：2026-07-21 · 执行：fable5 · 触发：用户指令（再次审计全部文档与项目内容，完善方案与可阅读性）
> 与第 1 轮（[2026-07-20-consistency-review.md](2026-07-20-consistency-review.md)，结构级）的分工：本轮下沉到**语义级**——数值口径、术语、需求↔验收双向映射、CLI 命令一致性、逐篇内容通读；并做可读性专项。

## 1. 审计方法与范围

- 机器审计四项新检查：FR↔AC 双向映射扫描、`crawler <cmd>` 全库用例 vs CLI 定义对账、限速数值多处出现口径对账（SSRN 5s / 闭源 6s / arXiv 3s / 日配额）、术语漂移扫描（族名/连字符变体）；
- 人工通读：INDEX 全文、四篇 auth adapter（wiley/oup/uchicago/informs）以读者视角复核；全库"待并入/待办"标记搜捕；
- 前轮修复回归验证（13 项全部保持）。

## 2. 发现与处置

### 2.1 真实问题（10 项，已修复）

| # | 发现 | 处置 |
|---|---|---|
| 1 | **7 条 FR（04/06/08/09/11/12/13）在需求文档外无显式验收回引**——可追溯性断链 | 新增 FR/NFR→AC 覆盖映射总表（acceptance-criteria 附表，D-016）；度量型 NFR-1/2/5/7 明确"Phase 报告实测记录"验收形态 |
| 2–7 | **6 处过时"⚠ 待并入/待办"标记**：wiley §4/§7、informs §2 尾/§4×2、uchicago §4、oup §4——勘察实际已并入（或如 INFORMS 属"设计期不可达"应改口径） | 逐处更新：已并入者改"已并入+剩余实现期事项"；INFORMS 改为明确的"云 IP 不可达 → 实现期登录态勘察首项，完成前停留 review" |
| 8 | uchicago 限速与其"批量下载须事先许可"条款未联动（仍写全局 200/日） | 日配额降为 50/日 + 大批量引导先申请许可；补 robots Crawl-delay 与 TDMRep 的遵守说明 |
| 9 | INDEX 过时三处：decision-log 标题停在 D-014、reports 未列册、盘点日期 | 全部更新（现 D-016、三份报告列册） |
| 10 | README 状态行仍写"设计阶段（Phase 0）"，未反映 Phase 0 完成 | 更新状态行 + 链接阶段报告 |

### 2.2 误报（2 项，判定不改）

- `crawler resume/retry`"未定义"——实为 CLI 清单合并写法（`status / resume / retry` 一行），定义存在；
- decision-log 的 "D-XXX"、status-workflow 的 "TBD"——均为规范文本自身用词，非占位符（与第 1 轮同款误报，已在自审脚本中留注释）。

### 2.3 可读性增强（3 项交付，D-016）

1. **[GLOSSARY.md](../GLOSSARY.md)**：50+ 全库共用术语的单点定义（六主题分组：领域对象/插件路由/获取认证/pipeline 任务/测试质量/流程治理），每条附权威出处链接——45 篇文档的专有名词首次可速查；
2. **INDEX"按意图导航"层**：七条任务式阅读路径（理解系统/加 venue/写 adapter/合规/开发/查决策/查勘察）前置于逐目录清单——新读者与回访者各取所需；
3. **README/AGENTS 联动**：README 状态与 GLOSSARY 入口；AGENTS.md §4 checklist 增两项义务（FR→AC 映射表同步、新术语入 GLOSSARY）。

## 3. 数值与术语对账结果（无漂移）

- 限速口径五组多处出现全一致：arXiv 1 req/3s、SSRN 1 req/5s（+抖动）、闭源 1 req/6s、Crossref 动态头、日配额 200（uchicago 例外 50 为本轮有意收紧）；
- 术语无连字符/下划线混用（open_access/auth_gated/aggregator 全库统一）；
- adapter 计数口径（~40）三处一致（D-015 后无回潮）。

## 4. 遗留

- GLOSSARY（review）与 16 篇 adapter 同批次走评审；
- informs 文档停留 review 的明确前置：实现期登录态 robots/TDM 勘察（其余 5 篇 auth adapter 勘察已闭环，可随时评审转 approved）；
- 自审脚本已含五类检查（链接/front matter/INDEX/注册对账/占位符）+ 本轮四类语义检查——Phase 1 时合并为 `make lint-docs` 固化（写入 Phase 1 开工清单）。

## 5. 结论

第 2 轮审计：10 项真实问题全部修复，2 项误报判定留档，3 项可读性交付落地。两轮合计 23 项修复后，全库结构级+语义级检查均 CLEAN。**设计基线可进入 Phase 1，文档体系的可读性与可追溯性达到"新协作者（人类或 agent）可自行导航"的目标。**
