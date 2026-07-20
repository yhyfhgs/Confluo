---
title: 测试计划与测试类型
status: approved
owner: fable5
updated: 2026-07-20
---

# 测试计划

> 爬虫系统测试的根本矛盾：**被测对象（外部网站）不受我们控制且随时漂移**。本计划的解法：把"解析逻辑正确性"（离线可测、每次提交跑）与"站点未漂移"（在线探测、定期跑）彻底分离。

## 1. 测试类型学（六类）

| # | 类型 | 测什么 | 网络 | 触发 | 位置 |
|---|---|---|---|---|---|
| T1 | 单元测试 | 纯函数：URL 构造、解析器、去重、DSL 编译、状态机、脱敏 | 无 | 每次提交（CI 必过门禁） | `tests/unit/` |
| T2 | 契约测试 | 所有 adapter 对协议的一致性（能力声明↔行为） | 无 | 每次提交 | `tests/contract/` |
| T3 | Fixture 回放测试 | adapter 解析真实页面快照的回归 | 无 | 每次提交 | `tests/fixtures/<adapter>/` |
| T4 | 集成测试（mock 网络） | pipeline 六阶段、断点续爬、限速器、auth 生命周期（假 IdP） | 本地 mock | 每次提交 | `tests/integration/` |
| T5 | 在线冒烟 + canary | 真网小样本：结构未漂移、限速合规 | **真网，限量** | 手动 / nightly / 周 | `tests/smoke/`、`crawler canary` |
| T6 | 手动 runbook（半自动） | 真实凭证的认证流程、端到端场景验收 | 真网 | 里程碑 / 按需 | `tests/manual/` + records 留痕 |

**门禁规则**：T1–T4 绿是合并前提；T5 失败不阻塞合并但必须开跟踪任务（站点漂移≠代码错误）；T6 结果决定验收（AC）判定。

## 2. Fixture 体系（T3 的核心机制）

- **三件套最低配**：每 adapter 至少保存"正常 listing 页 / 正常详情页 / 一种异常页（空结果、登录墙、404）"的原始响应快照 + 期望解析输出（golden JSON）；
- **录制**：`crawler devtools record <adapter> <url>` 抓取并脱敏（剥 cookie/token/个人数据）后存 `tests/fixtures/`（入 git）；`_staging/` 为重录暂存（不入 git）；
- **重录流程**：canary 报漂移 → 人工确认站点真变 → 重录 fixture → 修解析器 → golden 更新走 diff review——**golden 变更必须人工过目**（防解析器错改把错误固化为预期）；
- **快照纪律**：认证站点 fixture 一律来自登录态人工导出并脱敏，绝不含活 session。

## 3. 各设计域 → 测试映射（细目在各设计文档 §测试与验收）

| 设计域 | T1 重点 | T3/T4 重点 | T5/T6 重点 |
|---|---|---|---|
| plugin 框架 (02) | VenueSpec 校验、路由解析 | 契约套件全 adapter 跑 | — |
| open_access (03) | URL 构造矩阵 | 各源三件套解析 | 每源 1 timeline+1 下载 |
| auth_gated (04) | 判定器（登录墙/风控页识别）、文件验证器 | 假 IdP 生命周期 | 每平台 runbook（真凭证） |
| pipeline (05) | 状态机、幂等键、错误分类映射 | kill-9 注入、限速压力 | 端到端场景（AC） |
| data model (06) | 标题规范化、合并规则 | 多源乱序注入属性测试 | verify 对账真库 |
| auth (07) | URL 重写、脱敏、加密 round-trip | mock IdP 全周期 | 首登/过期/登出 runbook |
| tracking (08) | era 路由边界年 | DBLP 快照解析 | track 探测真网候选 |
| search (09) | DSL 编译用例表 | 下推/本地一致性 | 7 天连续 watch |

## 4. Canary（站点漂移的哨兵，T5 常态化）

- 每个 adapter 注册 1–3 个**已知答案样本**（如：ICLR 2024 应有论文 N 篇 ±口径差、DOI 10.1016/j.jfineco.xxx 的 resolve 应产出 pdf 计划）；
- `crawler canary` 逐 adapter 限速执行：PASS / DRIFT(解析失败) / DEGRADED(可解析但字段缺失) / BLOCKED(认证/风控)；
- 输出健康矩阵（markdown）到 `docs/testing/records/canary/`；连续 2 周 DRIFT → 模块降级流程（status-workflow §3.4）；
- 频率：周跑（cron）；发布前必跑。

## 5. 在线测试的礼貌预算

- T5 全套单次运行 ≤50 个请求、走生产同款限速器；nightly 只跑 open_access 族，auth 族 canary 每周一次且避开工作日高峰；
- 在线测试 UA 与生产一致（不伪装）；任何在线测试触发 429/风控 → 该 adapter 测试冷却 48h。

## 6. 覆盖率与质量目标

- T1 行覆盖：core ≥80%，adapter 解析器 ≥90%（解析器是故障主发地）；
- 变异测试（可选，Phase 7）：对合并规则与错误分类映射做 mutation testing 抽查；
- 每个 FAILED error_class 至少一条测试用例证明其触发路径（错误分类学不退化为文档摆设）。

## 7. 测试记录规范

- 里程碑验收与 T6 runbook 每次执行都在 `docs/testing/records/YYYY-MM-DD-<what>.md` 留痕（模板见 doc-conventions §5）；
- canary 周报自动落 `records/canary/`；
- 记录含复现信息：代码 commit、venue、样本、结果、日志片段路径。

## 8. CI 形态（实现阶段落地）

- 本地优先：`make test`（T1–T4）、`make smoke`（T5 手动）；
- 若托管远端（GitHub 私库）：push 跑 T1–T4；schedule 跑 canary——secrets 管理遵守 design/07（CI 中仅注入只读 API key，**绝不注入机构 session**；auth 族 canary 只在本机跑）。
