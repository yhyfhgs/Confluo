# Phase 1 阶段报告 — 核心框架（2026-07-21）

> 判定依据：[development-plan §Phase 1](../plan/development-plan.md)、[acceptance-criteria AC-1/AC-0](../testing/acceptance-criteria.md)、[验收记录](../testing/records/2026-07-21-phase1-acceptance.md)。
> 代码版本：main `9e158e9` 起收尾提交；tag `phase-1`、`schema-v1`。

## 1. DoD 判定（全项达成）

| DoD 项 | 判定 | 证据 |
|---|---|---|
| mock adapter 走通六阶段端到端 | **PASS** | AC-1.1 测试 + CLI 端到端（dry-run 10 → 实跑 成功 10/失败 0 → verify 一致）；主 agent 与终审 agent 双独立复现 |
| 断点续爬（kill -9 重跑不重复不遗漏） | **PASS** | AC-1.3：SIGKILL×4 真实命中，canonical dump 与一次跑完逐行一致，成功 FetchLog 每 asset ≤1，重跑含 skipped |
| 单测覆盖核心 ≥80% | **PASS** | 覆盖率 99.13%（门禁 80%），519 passed / 12 skipped（stub 占位），`make check` 全绿 |
| 文档 01/02/05/06 转 implemented | **PASS** | 本次收尾完成（含 7 处实现期勘误回填），INDEX 同步 |

## 2. 验收汇总

- **AC-1.1 ~ AC-1.6：全部 PASS**（每条至少一个自动化测试映射，docstring 标 `Closes: AC-1.x`；详见验收记录）。
- **AC-0.1 ~ AC-0.5 红线：全部 PASS**（终审 agent 对 git 全历史扫描：无盗版源集成点、无 CAPTCHA 求解代码、凭证/PDF 零入库、日志脱敏含引号与嵌套形态并有正则扫描断言、限速声明全带出处且 AC-1.4 实测 ≤ 配置×1.05）。

## 3. 交付清单（development-plan §Phase 1 范围逐项）

| 范围项 | 交付 |
|---|---|
| VenueRegistry（YAML 加载/校验/entry-point 扫描） | `registry.py`（七类 lint 校验+路由）+ `adapter.py`（entry point 组扫描）+ venues 三份 YAML（mock/jfe/iclr 全过 lint） |
| SQLite schema v1 + 迁移器 | `storage/`：16 表 DDL（方言中性、无 FTS5）、WAL、逐步事务+备份迁移器、repo 层（identifier 锚点强合并） |
| Task 队列与状态机 | `tasks.py`：7 合法转移全枚举、COALESCE 幂等索引、新鲜度 TTL、BLOCKED 不占重试、recover_running 崩溃恢复 |
| 六阶段 pipeline 执行器（串行） | `pipeline/`：stages+runner（级联/幂等跳过/错误分类路由/整批 BLOCKED/fetch 前 re-resolve）、fetchio（*.part 原子写）、report |
| per-domain 限速器 | `ratelimit.py`：token bucket（注入时钟）+ 最保守值合成；AC-1.4 实测合规 |
| 结构化日志 | `obslog.py`：jsonl + 控制台摘要 + 全形态脱敏（AC-0.4 扫描断言） |
| `crawler` CLI 骨架 | `cli.py`：11 命令、退出码 0/1/2/3 契约、entry point 冒烟 |
| fixture 回放测试基建 | golden helper（UPDATE_GOLDEN 纪律）+ mock golden 双份 + fixtures/README 规范 |
| mock_platform 驱动 | 确定性语料（seed 派生）+ 九类故障注入（quirks，无状态） |

统计：42 提交（收尾前）；测试收集 531（unit 413 / contract 33 / integration 85），执行 519 passed + 12 stub skip；零真实网络流量。

## 4. 过程与质量机制

多 agent 分档并行（fable：T7c 核心+终审；opus：storage/tasks/T9 验收等：sonnet：registry/infra/mock/CLI 等），峰值 5 线 worktree 并行；每任务独立审查+修复循环+复审，主 agent 合并后亲跑门禁；全分支终审（缝合面+红线+backlog triage）。

**审查净化战果**（若无独立审查将带病进入 Phase 2 的缺陷）：redact 引号形态漏网（红线级）、NULL 幂等索引失效、lint 异常穿透、canonical dump 标题碰撞退化、kill 测试 flake 路径——全部在任务内修复并复审确认。

## 5. 已知限制（如实记录）

- fetch 收尾三步（commit/mark_asset/add_fetch_log）非同事务：SIGKILL 缝隙可产生"已 fetched 无成功日志"（fails-safe：文件与状态正确，审计少记方向保守）——**Phase 2 硬化项**。
- `planned_bytes` 恒 0（AssetPlan 无 size 字段），dry-run 字节估算待 Phase 2。
- rate_limit 配置未禁 0/负值；config.toml 损坏为裸 traceback——Phase 2 polish。
- RATE_LIMITED 的 domain 冷却为 Phase 1 近似（连续 >3 转 transient 处置），真实冷却随 Phase 2。

## 6. Phase 2 开工检查单（终审 triage 移交）

1. **【置顶】`fetch_log.url` 脱敏评估**：Phase 2 签名 URL/token 将明文入审计表（AC-0.4 暴露面）。
2. fetch 三步同事务化（repo 组合事务 API）。
3. mock 两处裸 ValueError 转 CrawlerError（非法 error_class→CONFIG、畸形 doi 尾段→PARSE）。
4. 其余 15 项 Minor 备忘见 `.superpowers/sdd/progress.md` backlog 节（load_adapters 单插件容错、rglob 隐藏目录、jsonl 跨午夜、双 is_primary 等）。
5. 流程既定项：外部 API 申请（Elsevier/S2/Kaggle）、adapter 详设逐篇 review→approved、arxiv 先行（`adapter/arxiv` 分支）。
