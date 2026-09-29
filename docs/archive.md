---
title: 归档说明
status: approved
owner: opus5.5-primary
updated: 2026-09-27
---

# 归档说明

main 只放当前文档。旧内容都保存在下面两个位置，用 `git show` 就能直接读，不用切换分支。

## v2 完整草稿：标签 `v2-drafts`

2026-09-26/27 设计阶段写出的全部长稿。main 上的设计文档是它们的精简版，并已吸收设计简报第 2、3 轮裁决；两者不一致时以 main 为准。

| 在 `v2-drafts` 上的路径 | 内容 | main 上对应 |
|---|---|---|
| `docs/plan/v2/00-design-brief.md` | 设计简报：原则与三轮架构裁决 | [v2 总览](plan/v2/README.md) 与各篇 |
| `docs/plan/v2/01-…09-*.md` | 设计长稿：DDL、算法、113 张任务卡、全部验收条目、评审与审计记录 | 同路径的精简版 |
| `docs/plan/v2/adr-proposals.md` | ADR D-040…D-071 全文 | [decision-log](plan/decision-log.md) 的一行摘要 |
| `docs/plan/v2/design-process-record.md` 及同名目录 | 设计过程记录与首轮 agent 返回 JSON | — |
| `docs/catalog/source-directory.md` | 名录长稿：通道、限速、条款与证据列 | 同路径的精简版 |
| `docs/survey/` | 14 个主题的调研全文、综合与原始数据 | [调研结论](survey/README.md) |
| `docs/logs/2026-09-27-session-011.md`…`013.md` | 设计阶段工作日志 | — |
| `docs/archive-v1.md` | v1 全部路径的逐条索引 | 本页 v1 一节 |

```bash
git show v2-drafts:docs/plan/v2/04-retrieval-and-routing.md   # 读一篇长稿
git worktree add ../confluo-v2-drafts v2-drafts          # 整套并排对照
```

配图 `docs/diagrams/v2-*.svg` 的图注里写的章节号，指的是这些长稿。

## v1：分支 `archive/v1`（标签 `v1-final`）

v1 是 Python 3.12 单用户 CLI：六阶段 pipeline，21 个平台 adapter，62 个 VenueSpec，SQLite + FTS5。Phase 0–7 全部完成（标签 `phase-0`…`phase-7`），收官门禁 4617 passed / 31 skipped，覆盖率 98.98%。

- **代码**：`src/`、`tests/`、`venues/`、`subscriptions/`、`config/`、`scripts/`。整个分支共 776 个受控文件。
- **文档**：`docs/` 下的设计、名录、站点勘察、计划、流程规范、测试记录、阶段报告与日志。
- **ADR**：D-001…D-039 的全文在 `docs/plan/decision-log.md`。

```bash
git show archive/v1:docs/design/01-architecture.md     # 读一个文件
git worktree add ../confluo-v1 archive/v1        # 并排对照；在其中 uv sync --extra auth && make check 仍可跑 v1 门禁
```

v1 的本地运行数据（数据库、凭证、日报）不进 git。v1 代码没有随 v2 改名：它只读 `PAPER_CRAWLER_HOME`，未设置时默认 `~/.paper-crawler`，不识别 `CONFLUO_HOME` 或 `.confluo/`。在 v1 worktree 里运行时，保留旧环境变量或用 `--home` 显式指向数据所在目录。
