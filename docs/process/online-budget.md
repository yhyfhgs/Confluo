---
title: 在线预算共享行记账规范
status: approved
owner: fable5
updated: 2026-07-27
---

# 在线预算共享行记账规范

> 依据：Phase 7 T4（[phase7-implementation-plan.md](../plan/phase7-implementation-plan.md) §3/§4
> 检查单 #16）处置 [phase6-report §4 事件⑤](../reports/2026-07-26-phase6-report.md)如实记录的
> 协调缺口。工具：[`scripts/budget_ledger.py`](../../scripts/budget_ledger.py)。

## 1. 背景

各 Phase 实施计划的"在线预算分项表"（如 phase7-implementation-plan.md §3）里有若干
**共享行**——多个任务卡/会话都可能消费同一行额度（典型如"机动"：突发复核，任何卡遇到
需要临时核实的情形都可能占用）。Phase 6 期间，三次独立在线活动（repec 探针 6 次、
acl_anthology 补拉 1 次、T7 nber 坐实 4 次）都引用了同一条"机动 ≤10"行，但各自的记录
方式是"占用 6/10"与"余 9"——没有一份文档在写"余额"时核对过**另外两次**已经消耗的
部分，三者合计 11，**超出该行名义上限 1**。这不是红线违规（AC-0 与总预算均未触碰），
但暴露了真实的协调缺口：共享行在多会话并行消费时，若只靠各会话各自静态推算余额，
累计值会悄悄超出声明上限而无人发现。

`scripts/budget_ledger.py` 把共享行的累计消耗落一份单一 JSON 文件（`<config-home>/
state/budget.json`），三条纪律（§2）配合该工具即可闭合上述缺口。

## 2. 三条纪律

1. **消费共享行前必读账本**：发起任何计入共享行（如"机动"）的在线动作前，先跑
   `budget_ledger.py status --row <行名>`，核对该行**当前**累计消耗——不要只凭自己
   记忆或早先看到的"余量"静态推算，其余并行会话可能已经记过账。
2. **消费后必记**：动作完成后立即 `budget_ledger.py record --row <行名> --session
   <会话/任务标识> --batch <本次批次描述> --count <本次实际请求数>`——"读账本"与
   "记一笔"两步都不可省，省任何一步都会让下一个读账本的会话看到过期/不完整的数据。
3. **超线入档**：`record` 后若该行累计消耗（`status` 输出的 `consumed`）已超过当期
   `phase<N>-implementation-plan.md` §3 表declared 的上限，如实记入当期阶段报告
   （`docs/reports/`）或 `decision-log.md`——说明超支多少、原因、是否属于 AC-0 红线
   触碰（通常不是——本纪律解决的是协调可见性问题，不是新增一条禁止性规则）。

行名与当期计划表 §3 的行名保持一致（如"机动"/`T8-robots`/`T19-bf`）；账本工具本身
**不记录/不校验预算上限**——上限随 Phase 计划表变化，账本只管"这一行迄今被消耗了
多少"，人/agent 在 `status` 输出旁核对当期计划表的 `≤N` 声明。

## 3. 账本文件格式

`<config-home>/state/budget.json`（config-home 解析同源 `config.resolve_home()`——
D-032 红线，禁 `Path.home()` 硬编码；该文件是运行时产物，由工具首次 `record` 时
创建，**不随仓库分发、不入库**，见 `.gitignore` 的 `/.paper-crawler/` 锚定项）：

```json
{
  "机动": {
    "consumed": 11,
    "entries": [
      {"ts": "2026-07-26T08:00:00+00:00", "session": "repec-probe", "batch": "探针遗留", "count": 6},
      {"ts": "2026-07-26T09:30:00+00:00", "session": "acl-anthology", "batch": "补拉", "count": 1},
      {"ts": "2026-07-26T11:00:00+00:00", "session": "T7-nber", "batch": "坐实", "count": 4}
    ]
  },
  "T8-robots": {"consumed": 2, "entries": ["..."]}
}
```

顶层键=共享预算行名（自由文本）；每行 `consumed`=该行累计消耗（全部 `entries[].count`
之和）、`entries`=消费记录数组（追加写，时间顺序），每条记录四字段：`ts`（ISO 8601
UTC 时间戳）、`session`（会话/任务标识，便于事后追溯"谁在何时用了多少"）、`batch`
（本次批次的简短描述）、`count`（本次消费的请求数）。

并发安全：`record` 的读→加→写整段包在 `fcntl.flock` 排他锁下（POSIX；锁文件
`budget.json.lock` 与账本文件分离），多会话并行 `record` 不会互相覆盖对方的增量。

## 4. 工具用法

```bash
# 消费前：核对账本
uv run python scripts/budget_ledger.py status                # 列全部行一览
uv run python scripts/budget_ledger.py status --row 机动      # 只看一行明细

# 消费后：记一笔
uv run python scripts/budget_ledger.py record --row 机动 \
    --session T19-nber --batch "nber 坐实" --count 4
```

`--home <path>` 可显式覆盖 config-home 解析（测试/隔离场景；生产用途省略，走
`resolve_home()` 默认链：`$PAPER_CRAWLER_HOME` > `~/.paper-crawler`）。

## 5. 定位说明

`budget_ledger.py` 是编排/记账流程工具，非爬虫功能——不入 `src/paper_crawler` 包
（不占门禁覆盖率、不入 mypy 扫描面），仍需过 `ruff check .`/`ruff format --check .`
（两者扫全仓库）。先例：`scripts/canary_weekly.sh`、`scripts/gen_arxiv_venues.py` 等
既有独立小工具同样不入 src 包。

本 Phase（7）§3 预算行自本账本起记；Phase 6 及更早的历史消费（如事件⑤的 6+1+4）
不补录——`docs/reports/2026-07-26-phase6-report.md` §4 事件⑤已如实记录在案，无需
在账本里重现历史数据。
