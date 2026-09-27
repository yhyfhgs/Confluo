---
title: 文档写作与目录规范
status: approved
owner: fable5
updated: 2026-07-20
---

# 文档写作与目录规范

## 1. 命名与放置

- 文件名：kebab-case 英文（`auth-session.md`）；设计文档带序号（`07-auth-session.md`）表达推荐阅读序；
- 目录职责表见 [AGENTS.md](../../AGENTS.md) §2（唯一权威，此处不重复）；
- 日志：`docs/logs/YYYY-MM-DD-session-NNN.md`；报告：`docs/reports/YYYY-MM-DD-<topic>.md`；测试记录：`docs/testing/records/YYYY-MM-DD-<what>.md`。

## 2. Front matter（必需，logs/reports/INDEX 除外）

```yaml
---
title: 中文标题
status: draft | review | approved | implemented | deprecated
owner: fable5            # 主责作者（人或 agent 名）
updated: YYYY-MM-DD      # 最后实质修改日
---
```

## 3. 行文规则

- 中文行文；技术术语、代码标识符、产品名保留英文原形；不生造中译名；
- 事实性断言（URL 模式、rate limit、政策）必须带：来源 + 核验日期；未核验标 `⚠ 未核验`；调研原始出处放 `docs/research/`，设计文档只引用结论；
- 伪代码块前注明"设计伪代码"；不追求可运行；
- 每篇设计文档必含或链接五要素：功能说明 / 实现方案 / 测试方法 / 测试类型 / 验收标准；
- 编号体系（全库唯一，勿复用已废编号）：需求 `FR-xx`/`NFR-x`、决策 `D-xxx`、验收 `AC-<phase>.<n>`、风险 `R<x>`。

## 4. 图表规范

- 架构/流程图：SVG 手工绘制或工具导出，源文件即交付物，存 `docs/diagrams/`，命名 `NN-topic.svg`；
- 文档内以相对路径引用图（`![](../diagrams/03-pipeline.svg)` 或链接形式）；图改动与相关文档同一提交；
- 简单示意允许文档内 ASCII 图（≤30 行），复杂结构必须 SVG；
- 表格用于可枚举事实；解释性内容写正文不塞表格。

## 5. 日志与报告模板

**Session 日志**（每工作 session 一份）：

```markdown
# YYYY-MM-DD Session NNN
## 目标
## 完成
- （做了什么，动了哪些文件——链接）
## 决策/发现
- （新 ADR？调研推翻了什么？）
## 遗留与下一步
## 耗时与工具（可选：subagent 使用记录）
```

**阶段报告**：目标回顾 / 交付清单与状态 / 验收结果汇总（链接 records）/ 偏差与原因 / 风险更新 / 下阶段建议。

**测试记录**：环境（日期、代码版本、真网 or fixture）/ 用例与结果表 / 失败分析 / 结论（通过｜有条件通过｜不通过）。

## 6. INDEX 同步

`docs/INDEX.md` 是唯一权威清单：路径、标题、status、updated 四列。任何新增/改名/废弃文档，同一提交内更新 INDEX（AGENTS.md §4 义务）。
