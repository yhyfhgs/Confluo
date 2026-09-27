---
title: Git 工作流程规范
status: approved
owner: fable5
updated: 2026-07-20
---

# Git 工作流程

> 决策依据：D-009。适用于人类与 AI 协作者。

## 1. 分支模型（trunk-based 轻量变体）

- `main`：唯一长期分支，任何时刻可用（文档可读、代码可跑）。
- 短生命分支（实现阶段强制，设计阶段可直提 main）：
  - `feat/<scope>-<短描述>`：新功能（`feat/core-task-queue`）
  - `adapter/<platform>`：单个平台 adapter 全套（设计文档更新+代码+fixture）（`adapter/elsevier-sd`）
  - `fix/<issue>`、`docs/<topic>`、`chore/<what>`
- 分支寿命目标 ≤3 天；超期先合 main 再续。
- 多 agent 并行约定：一个分支一个 agent；adapter 分支间无共享文件（天然可并行）；core 改动需要串行——先到先合，后者 rebase。

## 2. 提交规范（Conventional Commits）

```
<type>(<scope>): <subject>

[body: 为什么改；与哪条 FR/ADR/AC 相关]
```

- type：`feat` `fix` `docs` `test` `refactor` `chore` `perf`
- scope 约定表：`core`（框架）、`pipeline`、`auth`、`model`（数据模型）、`adapter:<id>`（如 `adapter:arxiv`）、`catalog`、`plan`、`testing`、`process`
- subject 英文小写祈使句 ≤72 字符；body 中文可。
- 示例：
  - `docs(plan): add ADR D-013 acm open access reclassification`
  - `feat(adapter:pmlr): volume-year mapping and bib parsing`
  - `test(pipeline): kill-9 resume property test`
- 关联引用：body 中写 `Refs: FR-07, D-006` / `Closes: AC-4.1`——让提交历史可追溯到需求与验收。

## 3. 提交粒度与内容规则

- 一个提交=一个逻辑变更；文档与其直接派生的图（SVG）同提交；代码与其测试同提交。
- **禁止入库**（.gitignore 已挡 + review 双保险）：凭证/session/state 文件、下载的 PDF/数据、`*.sqlite`、大二进制。fixture HTML/JSON 快照**允许**入库（测试资产，需脱敏：删 cookie/token/个人信息）。
- 生成物（运行报告 data/ 区）不入库；`docs/reports/` 的阶段报告是手写文档，入库。

## 4. PR 与自查（单人+AI 项目的轻量形态）

实现阶段每个分支合入前过一遍 PR 自查清单（无平台 PR 时以 `docs/logs/` 中的 merge 记录代替）：

**通用**：[ ] 提交信息合规 [ ] 无禁入文件 [ ] INDEX/进度已同步（若动文档）
**文档 PR**：[ ] front matter 状态正确流转 [ ] 交叉链接有效 [ ] 事实性内容标注来源与核验日期
**代码 PR**：[ ] 对应设计文档 `approved` [ ] 单测+fixture 过 [ ] 新增网络行为已声明限速 [ ] 日志脱敏 [ ] 错误分类映射完整
**adapter PR 附加**：[ ] adapter 设计文档同批更新 [ ] fixture 三件套（正常/空/异常页） [ ] canary 样本已注册 [ ] catalog 行更新

## 5. Tag 与里程碑

- Phase 完成：`phase-0` … `phase-7`（annotated tag，指向该阶段报告提交）。
- adapter 稳定：不打 tag，在 catalog 标 `supported_since`。
- schema 迁移：`schema-v<N>` tag 便于回溯。

## 6. 当前阶段的执行口径

Phase 0（纯文档）：直接提交 `main`；本 session 结束做首次提交（`chore: bootstrap text system and phase-0 design docs`），之后每完成一个文档簇一次提交。进入 Phase 1 起启用分支+自查清单全套。
