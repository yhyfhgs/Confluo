---
title: AC-7 验收记录骨架 — 全文抽取与库增强（Phase 7，T18 转正卡产出）
status: draft
owner: t18
updated: 2026-07-27
---

# AC-7 验收记录骨架（全文抽取与库增强，Phase 7）

> **本记录为骨架**（T18 卡产出，纯文档卡，零副作用）：[acceptance-criteria.md AC-7](../acceptance-criteria.md) 四条
> 判据/载体/执行结果/日期栏先行搭建。**在线部分全部 `pending`**——填写由 T19（在线验收批，phase7-plan §3
> `T19-nber`/机动行）与 fable 亲验完成，本卡不越权预判。离线部分：仅当上游实现卡已合并、有真实载体可引用时
> 才预填"PASS"，未合并的一律如实标 `pending`，不虚构判定。
>
> 判定依据：[acceptance-criteria.md AC-7](../acceptance-criteria.md)、
> [design/12-fulltext-extract.md](../../design/12-fulltext-extract.md)、
> [plan/phase7-implementation-plan.md §4 T7/T13/T14/T16 + §7 AC 映射](../../plan/phase7-implementation-plan.md)。
> 记录范式沿 [AC-6 离线端到端验收记录](2026-07-26-ac6-acceptance.md)（骨架简化：本卡不新增测试，只登记既有
> 载体 + 如实标注缺口）。
>
> **代码基线**：`docs/p7-t18-ac-registry`（T18 执行 worktree）@ `b3b8502`——W0/W1 阶段已合并：T1（D-033 ADR）/
> T6（browser-fetch 核心）/T7（extract 落地）/T8（repec）/T10（preprint_of 建边引擎）/T11（browser-fetch 三消费方）。
> **W2 阶段未合并（截至本卡）**：T13（dedupe review CLI）/T14（verify 全库扩展）/T16（preprint↔published 报告），
> grep 现状逐条见下表。

## 1. 四条判据/载体/执行结果/日期骨架

| AC | 场景（acceptance-criteria.md 原文摘） | 判据（离线/在线两层） | 载体 | 执行结果 | 日期 |
|---|---|---|---|---|---|
| AC-7.1 | 抽样 PDF 经 extract 得非空文本，标题与 DB 记录匹配（编辑距离阈值内） | 离线：非空文本 + 标题编辑距离阈值断言（纯文本/GROBID 两路径各一）；在线：真实抽样（T19，phase7-plan §7"T7 离线 fixture + T19 真实抽样"） | 离线（**已存在**，T7 已合并）：`tests/unit/test_extract_pypdf.py::test_ac_7_1_plain_text_path_title_within_first_window` + `test_ac_7_1_grobid_path_title_ratio`；在线：**pending**（归 T19） | 离线：**PASS**（本卡 2026-07-27 亲跑 2/2，见 §2）；在线：**pending** | 离线：2026-07-27；在线：pending |
| AC-7.2 | GROBID 开/关两模式均产出，关闭时降级为纯文本抽取不报错 | 离线：三态各一例（未配置/配置且在线/配置但降级不报错）；在线：条件项（本机 GROBID 可用才跑，phase7-plan §7"条件:本机GROBID可用"） | 离线（**已存在**，T7 已合并）：`tests/integration/test_extract_stage.py::test_ac_7_2_state_1_unconfigured_is_plain_text` + `test_ac_7_2_state_2_configured_and_online_is_tei` + `test_ac_7_2_state_3_configured_but_down_degrades_without_failing` | 离线：**PASS**（本卡 2026-07-27 亲跑 3/3，见 §2）；在线：**pending**（本机 GROBID 可用性未核） | 离线：2026-07-27；在线：pending |
| AC-7.3 | `dedupe review` 逐条展示证据，merge/reject 后 same_as/rejected 正确落库且可回滚（物理不删行） | `crawler dedupe review` 逐条展示 evidence_json + merge/reject 后 `same_as`/`rejected` 正确落库 + 可回滚（物理不删行）三件套 | **待 T13 落地**——本卡 grep 现状：`src/paper_crawler/storage/repo.py` 无 `list_candidates`/`decide_candidate`；`src/paper_crawler/cli.py` 无 `dedupe` 命令组；全仓无 `dedupe review` 任何命中 | **pending**（T13 未合并，无载体可判，不预支判定） | pending |
| AC-7.4 | 全库 `verify` 通过；preprint↔published 关联报告生成 | 全库 `verify`（pdf/ + si/ + fulltext/ 三段扩展）通过 + preprint_of 边聚合报告生成 | **部分就绪、部分待落地**：paper_relation(kind=preprint_of) 建边引擎**已合并**（T10，`src/paper_crawler/merge.py`，回归见 `tests/unit/test_merge.py`/`tests/unit/test_repo.py`）；`verify.py` 扫描范围**仍限于** `data_dir/pdf/**`（模块 docstring 原文如实自陈"si/fulltext/export/tmp 等子目录留待…扩展"，T14 未合并）；preprint↔published 关联报告生成器（T16）本卡 grep 现状：全仓无 `preprint_of` 关联报告脚本任何命中 | **pending**（T14/T16 均未合并，"全库 verify 三段扩展 + 报告生成"两件套均不完整，不能判定） | pending |

## 2. 离线可预填部分的现状口径（本卡 2026-07-27 亲跑，供 T19/fable 复现）

```
uv run pytest tests/unit/test_extract_pypdf.py::test_ac_7_1_plain_text_path_title_within_first_window \
  tests/unit/test_extract_pypdf.py::test_ac_7_1_grobid_path_title_ratio \
  tests/integration/test_extract_stage.py::test_ac_7_2_state_1_unconfigured_is_plain_text \
  tests/integration/test_extract_stage.py::test_ac_7_2_state_2_configured_and_online_is_tei \
  tests/integration/test_extract_stage.py::test_ac_7_2_state_3_configured_but_down_degrades_without_failing -v
=== 5 passed in 0.52s ===
```

**全量门禁**（本卡分支 `docs/p7-t18-ac-registry` @ `b3b8502`，纯文档改动前后不变）：`make check`
**4296 passed / 31 skipped / 98.93% coverage / EXIT=0**——数字出处 = 本 worktree 当前合并态门禁（含
T1/T6/T7/T8/T10/T11），非专指"T7/T11 两卡独立门禁"（W0/W1 已滚动合入同一基线，无法回退单独复现两卡
各自独立的历史门禁数字，如实注明）。

## 3. 已知缺口（如实列，供 T19/fable 参考，非本卡新发现）

1. **AC-7.3**：T13（dedupe review CLI + `list_candidates`/`decide_candidate`）未合并，无任何载体，本记录
   不预判、不填充占位测试名。
2. **AC-7.4**：T14（`verify.py` 扩展 si/+fulltext/ 两段）与 T16（preprint↔published 关联报告生成器）均未
   合并；仅数据层（T10 建边引擎）就绪，尚不构成"全库对账通过 + 报告生成"两件套的完整判据载体。
3. **AC-7.1/7.2 在线半区**：结构性归 T19（真实抽样 / 本机 GROBID 可用性核验），本卡不越权预判，亦不虚构
   "建议 PASS"这类需要真实执行支撑的判断。

## 4. 移交

- **T19（在线验收批）**：填 AC-7.1/AC-7.2 两行"在线"列（真实抽样 + 条件性 GROBID 可用性）。
- **T13/T14/T16 各自卡合并后**：本记录 AC-7.3/AC-7.4 两行需回填新载体与离线执行结果——**非本卡职责**，
  登记供后续卡与 controller（fable）追踪；建议由 T21（文档一致性收尾）或 T19 顺带回填，或另开小卡。
- **fable 亲验**：全表最终签署，转 `status: approved`。

## 5. 签署

- **T18 初稿（2026-07-27）**：骨架四行搭建完成；AC-7.1/AC-7.2 离线列已引用现存 T7 测试载体并如实标注
  PASS（本次亲跑 5/5，§2）；AC-7.3/AC-7.4 因上游卡（T13/T14/T16）未合并，如实标 `pending`，不预支判定、
  不虚构载体。**status: draft**，待 T13/T14/T16 落地回填 + T19 在线批 + fable 亲验后方可转 `approved`。
