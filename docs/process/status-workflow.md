---
title: 文档与代码状态流程
status: approved
owner: fable5
updated: 2026-07-20
---

# 状态流程（双状态机）

> 决策依据：D-010。配图：[diagrams/06-status-machine.svg](../diagrams/06-status-machine.svg)。

## 1. 文档状态机

```
draft ──(自审+交叉引用齐)──▶ review ──(评审通过)──▶ approved ──(对应实现落地)──▶ implemented
  ▲                            │                        │                            │
  └────────(重大返工)──────────┘                        └──(实质修改)──▶ review      │
                                任何状态 ──(被替代/放弃)──▶ deprecated ◀─────────────┘
```

| 状态 | 含义 | 进入条件 | 谁能改内容 |
|---|---|---|---|
| draft | 起草中 | 新建即是 | 随意改 |
| review | 待评审 | 作者自审过；无 TBD/占位符；链接有效 | 只按评审意见改 |
| approved | 已定稿，可作为实现依据 | 评审通过（单人项目=维护者通读+勾自查清单） | 实质修改必须先降 review 或走 ADR |
| implemented | 对应代码已 stable | 关联模块 stable | 只允许勘误性修改 |
| deprecated | 已废弃 | 被新文档替代（顶部注明替代者） | 冻结 |

**评审自查清单（review→approved 用）**：无占位符；内部无自相矛盾；对外链接与编号（FR/AC/D）有效；含五要素（功能/方案/测试方法/测试类型/验收标准）或链接到之；事实性断言有来源标注。

## 2. 代码模块状态机（实现阶段生效）

```
planned ─▶ spec_approved ─▶ in_dev ─▶ testing ─▶ stable ─▶ deprecated
              ▲   （门禁：设计文档=approved）      │
              └──────────(设计实质变更打回)────────┘
```

| 状态 | 门禁 |
|---|---|
| spec_approved | 对应设计文档 `approved`（**硬门禁**，AGENTS.md §3） |
| in_dev | 分支已建；负责 agent 唯一 |
| testing | 单测+fixture 过；在线冒烟待跑/进行中 |
| stable | 验收标准（AC-x.x）全过并在 testing/records 留痕；canary 注册 |
| deprecated | 有替代或需求取消；代码保留一个 Phase 后删除 |

## 3. 联动规则（双状态机的耦合点）

1. 模块 `in_dev` 前置 = 文档 `approved`（正向门禁）；
2. 模块 `stable` 后 → 文档转 `implemented`（收尾动作，写进 Phase DoD）；
3. `implemented` 文档被实质修改 → 关联模块自动打回 `testing`（需重跑验收）——"关联"由文档 front matter 未来增加 `modules:` 字段维护；
4. canary 连续 2 周失败的 adapter → 模块降 `testing` + 文档加 `⚠ 站点漂移` 批注（不降文档状态）。

## 4. 状态的记录位置（单一事实来源）

- 文档状态：各文件 front matter `status:`；INDEX.md 汇总视图（脚本未来自动生成，现阶段手工同步）。
- 模块状态：实现阶段在 `docs/plan/progress.md` 增设模块状态表；adapter 的对外状态额外反映在 catalog 各 venue 行（`supported_since` / `⚠`）。
- 变更留痕：状态流转不单独记日志，随所在提交的 message 体现（`docs(design): promote 05-pipeline to approved`）。

## 5. 节奏

- 每 Phase 结束：全文档状态盘点（INDEX 对账）写入阶段报告；
- 每月（实现阶段）：canary 汇总 → adapter 状态例行审视；
- deprecated 清理：每 Phase 结束统一处理，不日常零敲碎打。
