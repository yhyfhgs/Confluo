# Phase 1 验收执行记录（AC-1.1 ~ AC-1.6）

- 执行日期：2026-07-21 · 执行者：fable5（主 agent 亲自执行）
- 代码版本：main `9e158e9`（fd2b750 起 42 提交）
- 环境：macOS (Darwin 25.5.0) · Python 3.13.5 · uv 0.11.28
- 门禁命令：`uv run make check` → **exit 0**（ruff + ruff format --check + mypy strict + pytest）
- 全量结果：**519 passed / 12 skipped**（skip 均为 stub adapter 契约占位，reason 标注 until Phase 2/3/4），分支覆盖率 **99.13%**（门禁 ≥80%）
- AC 专项复跑：`uv run pytest tests/integration/test_ac_*.py tests/unit/test_venue_yaml_lint.py -q` → **29 passed in 13.47s**
- 独立复核：Phase 1 终审 agent（fable 档）另行亲跑门禁与 CLI 端到端（dry-run 预览 10 → 实跑 成功 10/失败 0 → verify 篡改检出退出 1），结论一致

## 逐条判定

| AC | 场景 | 判据（acceptance-criteria.md 原文口径） | 证据（测试映射，docstring 均标 Closes） | 结果 |
|---|---|---|---|---|
| AC-1.1 | mock venue 端到端 pull | DB 计数符合 mock；data/ 文件数=Asset(fetched)；报告"成功=N 失败=0" | `test_pipeline_e2e.py::test_pull_year_end_to_end`（counts issues=2/papers=10/assets=10/10、魔数、parent_id 溯源）+ `test_cli.py::test_pull_report_shows_succeeded_n_failed_0` | **PASS** |
| AC-1.2 | dry-run 不落盘 | dry-run 后 data/ 无新增、DB 无 fetched；"将下载 N 篇"=随后实跑数；实跑报告无预览行 | `test_ac_dryrun.py`（rglob 全树快照为空、planned==10==实跑 succeeded、非 dry-run 无"将下载"） | **PASS** |
| AC-1.3 | 断点续爬幂等 | 随机 kill 后重跑，最终 DB dump 与不中断跑逐行一致；日志含 skipped 且无重复 FetchLog | `test_ac_killresume.py`（subprocess+SIGKILL×4 真实命中≥3、canonical_dump 双库全等【口径=tests/helpers/dbdump.py，复合业务键含标题碰撞消歧】、每 asset 成功 fetch_log ≤1、重跑含 skipped） | **PASS** |
| AC-1.4 | 限速合规 | FetchLog 时间戳统计：实际速率 ≤ 配置×1.05 | `test_ac_ratelimit.py`（rpm=600、30 fetch 真实时钟：actual_rpm ≤630 上界 + 总时长 ≥2.755s 下界防"限速未生效"假绿；domain 取自 fetch_log 审计行） | **PASS** |
| AC-1.5 | 状态机与 BLOCKED | 注入 auth_expired → BLOCKED 不占重试；resume 后回 PENDING 并完成 | `test_ac_blocked_resume.py`（CLI 退出 3、5 BLOCKED 全部 attempts==0【1 触发+4 同批连带】、status --blocked 呈原因与指引、修 YAML→resume --all→重跑退出 0、文件齐） | **PASS** |
| AC-1.6 | VenueSpec 校验 | 非法 spec 被 venues lint 拒绝并给定位信息 | `test_venue_yaml_lint.py`（未知 adapter/auth 不兼容/id 冲突/缺 issn/格式/小写 x/混合列表逐索引定位/编码异常→LintIssue）+ `test_cli.py` lint 退出 2 输出 `file:venue_id:field` | **PASS** |

## 附注（执行口径与已知窗口）

1. **AC-1.3 canonical dump 口径**：比较表 venue/issue/paper/identifier/asset/paper_issue_link；剔除 volatile 列（ULID 主键/时间戳/file_path）；外键翻译为业务键，paper 侧用 (title, 主 identifier) 复合键消歧标题碰撞（对抗用例双向验证）；task/fetch_log 不参与逐行对比，改以"每 asset 成功记录 ≤1"专项断言。完整可执行定义见 `tests/helpers/dbdump.py` docstring。
2. **已知窗口（fails-safe）**：`mark_asset` 与 `add_fetch_log` 为两次独立提交，SIGKILL 落于缝隙时该 asset 成功日志可为 0（文件与状态正确，审计少记方向保守）；fetch 收尾三步同事务化列入 Phase 2 硬化项。
3. **AC-0 红线**：终审 agent 对 git 全历史执行了 AC-0.1~0.5 扫描（盗版源/CAPTCHA/凭证入库/日志脱敏/限速声明），五条全过，详见阶段报告。
