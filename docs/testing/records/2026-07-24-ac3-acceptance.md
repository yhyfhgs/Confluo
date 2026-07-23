---
title: AC-3.1~3.4 独立汇总验收记录 — 数据模型与合并引擎（Phase 3 补记收口）
status: approved
owner: g3
updated: 2026-07-24
---

# AC-3.1~3.4 独立汇总验收记录（数据模型与合并引擎，Phase 3 判据补记收口）

> 判定依据：[acceptance-criteria.md](../acceptance-criteria.md) AC-3.1~3.4 原文、[design/06-data-model.md §3/§7](../../design/06-data-model.md)。
> 记录范式：[AC-4 离线验收汇总记录](2026-07-23-ac4-acceptance.md)（逐条判定表 / 证据链 / 亲跑台账 / 签署）。
> **定位**：本记录不新交付判据——AC-3.1~3.4 的判据代码（`MergeEngine`/`verify_store`/CLI `verify`）与对应测试均为 **Phase 3 T1/T2 已交付**（[2026-07-23-phase3-acceptance.md](2026-07-23-phase3-acceptance.md) §1 已含逐条 PASS 判定，本记录结论与之一致、不重判）。本记录是 Phase 3 检查单 #7 → Phase 4 报告 §6 检查单 #10 延续、跨 2 个 Phase 未清零的**独立汇总记录补记收口**——把此前散落 `tests/integration/test_merge_acceptance.py` / `tests/integration/test_merge_property.py` / `tests/integration/test_cli.py` / `tests/unit/test_verify.py` 四个测试文件（本次盘点另补 `tests/unit/test_merge.py` 基础层）的判据首次收口进 `testing/records/` 下的 AC-3 专属独立记录文档，并本次在隔离 worktree 内重新亲跑复现全部计数（非抄旧报告数字）。
> 代码基线：`chore/ledger-close` worktree @ `main` `7a1e571`（本记录**零 `src/` 改动**，纯测试判据实跑 + 文档收口）。

## 0. 与既有 Phase 3 判定的关系（如实说明，避免误读为重复劳动）

[2026-07-23-phase3-acceptance.md](2026-07-23-phase3-acceptance.md) §1 已含 AC-3.1~3.5 的一张综合判定表（PASS 结论 + 证据文件名），但该表**内嵌于覆盖全 Phase 3 的通用汇总记录**（同表还含 AC-3.5、DoD、AC-0、预算台账），并非"独立汇总验收记录"本身。Phase 3 报告与 Phase 4 报告的检查单均明确要求把 AC-3.1~3.4 的判据**收口成 `testing/records/` 下的独立文档**（原始表述"判据分散三个测试文件"，本记录盘点后确认为四个正式载体文件 + 一个基础层文件共五个）。本记录不推翻、不重新裁决 Phase 3 已有 PASS 结论，只做三件事：①独立成文；②在 `chore/ledger-close` worktree 内重新亲跑复现全部计数（§2 台账）；③把判据颗粒度精确到"文件::用例名"。

## 1. AC-3.1~3.4 逐条判定

| AC | 场景（acceptance-criteria.md 原文） | 判定 | 承载载体 |
|---|---|---|---|
| AC-3.1 | 强合并：同一 DOI 经 arXiv 与 Crossref 两路注入 → 1 条 paper、≥2 个 identifier | **PASS（approved）** | `test_merge_acceptance.py::test_ac_3_1_*`（2 例，正式载体）+ `test_merge.py` 强合并/DOI 归一子集（基础层补证） |
| AC-3.2 | 弱信号不自动合并：标题改名的 WP↔刊发版注入 → 2 条 paper + 1 条 candidate_duplicate(decided=null) | **PASS（approved）** | `test_merge_acceptance.py::test_ac_3_2_*`（2 例，正式载体）+ `test_merge.py` 弱信号候审子集（基础层补证） |
| AC-3.3 | verify 对账：人为制造丢文件/孤儿文件/哈希不符三类 → verify 全部检出并给出正确修复建议 | **PASS（approved）** | `test_cli.py::test_verify_*` + `test_pdf_layout_scope_*`（11 例，正式载体）+ `test_verify.py` `verify_store` 单元层（15 例，基础层补证） |
| AC-3.4 | 顺序无关：多源记录随机顺序注入，最终库状态逐行一致（属性测试通过） | **PASS（approved，口径注明，沿 Phase 3 豁免边界）** | `test_merge_property.py::test_ingest_order_independent`（Hypothesis 250 examples，正式载体）+ `test_reingest_whole_batch_is_idempotent`（批级幂等，50 examples，同文件补充） |

---

### AC-3.1 · 强合并 — **PASS**

**场景原文**：同一 DOI 经 arXiv 与 Crossref 两路注入 → 1 条 paper、≥2 个 identifier。

**承载载体（`tests/integration/test_merge_acceptance.py`）**：
- `test_ac_3_1_mixed_dual_path_one_paper_two_identifiers`：**混合双路真实形态**（非两路都走 `MergeEngine` 自证）——arXiv 路经既有 pull 路径 `Repo.upsert_paper` 写入 `(arxiv, doi)` 双 identifier；crossref 路经 `MergeEngine.ingest` 注入同一 DOI → `result.action=="merged"`、`matched_identifiers==("doi:10.5555/aiayn",)`、库内 `paper` 计数 `==1`、identifier 并集 `≥2`（含 arxiv + doi 两条）。
- `test_ac_3_1_mixed_dual_path_merges_across_doi_case_difference`：DOI 大小写异形（`AIAYN` vs `aiayn`）+ `https://doi.org/` 前缀形两路仍经 `normalize_doi()` 强合并——防止归一化缺口把同一 DOI 误判成两个不同 identifier。

**基础层补证（`tests/unit/test_merge.py`，Phase 3 T1）**：`test_strong_merge_same_doi_two_sources_one_paper_two_identifiers`、`test_doi_normalization_enables_strong_merge` 在纯单元层单独锁定同一决策点（`MergeEngine` 裁决本身，非 CLI/pipeline 集成路径）。

**亲跑（本记录，2026-07-24，`uv run pytest`，零真实网络）**：`test_merge_acceptance.py` **4 passed**；`test_merge.py` **18 passed**（全文件，含 AC-3.1/3.2 相关子集与其余 `MergeEngine` 决策点单测）。

---

### AC-3.2 · 弱信号不自动合并 — **PASS**

**场景原文**：标题改名的 WP↔刊发版注入 → 2 条 paper + 1 条 candidate_duplicate(decided=null)。

**承载载体（`tests/integration/test_merge_acceptance.py`）**：
- `test_ac_3_2_wp_vs_published_two_papers_one_candidate`：SSRN WP 版（`ssrn` id）与期刊刊发版（`doi`，标题末尾标点/大小写微异，归一化后相等，同首作者姓氏）分两路 `ingest` → `result.action=="candidate_flagged"`、`matched_identifiers==()`（无 identifier 命中，纯弱信号）、`paper` 计数 `==2`（绝不自动合并）、`paper_relation(kind='candidate_duplicate')` 恰 1 行且 `decided IS NULL`、`evidence_json` 含 `"weak-signal-title-author"`。
- `test_ac_3_2_genuinely_renamed_title_no_candidate`（反例，锁定不误判边界）：标题归一化后确实不同（真改名，非排版异形）→ `result.action=="created"`、`paper` 计数 `==2`、`paper_relation` 计数 `==0`（不产生候审边，D-007「宁可两条独立待 identifier 证据」）。

**基础层补证（`tests/unit/test_merge.py`）**：`test_weak_signal_same_title_and_surname_flags_candidate`、`test_weak_signal_different_surname_no_candidate`、`test_weak_signal_missing_author_no_candidate`、`test_weak_signal_blank_author_no_candidate`、`test_weak_signal_against_pull_path_paper_without_author`、`test_weak_signal_latex_unicode_title_variants_match` 六例覆盖弱信号判界的更细粒度边界（作者缺失/空白、LaTeX/Unicode 标题变体）。

**亲跑**：同 AC-3.1（同文件同批次），`test_merge_acceptance.py` **4 passed**、`test_merge.py` **18 passed**（已含本条子集，不重复计数）。

---

### AC-3.3 · verify 对账 — **PASS**

**场景原文**：人为制造丢文件/孤儿文件/哈希不符三类不一致 → `verify` 全部检出并给出正确修复建议。

**承载载体（CLI 集成层，`tests/integration/test_cli.py`，Phase 3 T2；AC-3.3 正式验收载体）**：
- `test_verify_clean_exits_0`：干净库 `verify` 零误报，exit 0。
- `test_verify_detects_missing_file_exits_1` / `test_verify_detects_orphan_file_exits_1` / `test_verify_detects_hash_mismatch_exits_1`：三类不一致各自独立场景，逐类检出 + exit 1 + 建议文本含正确动作词（`re-fetch`/`--force`/`crawler pull`；`adopt`/"纳管"；`quarantine`/`corrupt`/`--force`）。
- `test_verify_detects_all_three_kinds_combined_exits_1`：三类同时人为制造 → 一次 `verify` 全部检出（"发现 3 处不一致"）。
- `test_verify_missing_file_fix_command_actually_repairs_it` / `test_verify_hash_mismatch_fix_command_actually_repairs_it`：**建议不是空话**的最强验证——按建议命令（`crawler pull <venue> --year <year> --force`）实际执行一遍，`verify` 复检转清洁、文件内容与原始一致。
- `test_pdf_layout_scope_*`（4 例）：`_pdf_layout_scope` 私有辅助函数的边界直测（空 file_path / 相对路径 / pdf 树外路径 / year 非数字段），补 CLI 端到端难自然触达的分支，为上述修复建议路径的辅助证据（非独立判据）。

**基础层补证（`tests/unit/test_verify.py`，Phase 1 T8a；`verify_store` 单元层）**：15 例覆盖 `verify_store` 本身（三类检出各自的正/反例、只读语义、排序稳定性、边界如 `planned` 资产不报 missing、`sha256` 缺省不做哈希校验等）——文件 docstring 自陈"AC-3.3 正式验收在 Phase 3"，本层是该判据函数的更细粒度基础覆盖，非本条判定的独立正式载体。

**亲跑**：`test_cli.py`（`-k "verify or pdf_layout_scope"` 子集）**11 passed**（同文件另 44 项无关 CLI 用例 deselected，不计入本条）；`test_verify.py`（全文件）**15 passed**。

---

### AC-3.4 · 顺序无关 — **PASS**（口径注明，沿 Phase 3 既有豁免边界）

**场景原文**：多源记录随机顺序注入，最终库状态逐行一致（属性测试通过）。

**承载载体（`tests/integration/test_merge_property.py`，Phase 3 T1）**：
- `test_ingest_order_independent`：Hypothesis 属性测试，`max_examples=250`、`derandomize=True`（固定种子可复现，防 CI flaky）——同一批多源观测（6 源 `official/crossref/dblp/openalex/s2/heuristic`）以两条独立随机排列分别注入两个隔离 SQLite 库，比对 `canonical_dump`（行序无关视图，按 `repr` 重排）与 `paper_relation` dump **逐行相等**。
- `test_reingest_whole_batch_is_idempotent`：同批整体注入两遍与一遍等价（批级幂等，`max_examples=50`），同文件内的补充属性，非 AC-3.4 字面判据但同属"顺序/重复无关"性质簇。

**口径注明（与 Phase 3 判定一致，本记录不新增、不改变豁免边界）**：顺序无关性**限定于无跨 paper 桥接冲突的输入类**——源码 docstring 显式论证：桥接 identifier 冲突裁决本身是既定语义下的数学必然顺序敏感（先到者静默成单 paper、无候审痕迹；后到者裂两 paper + 候审边；平局胜者随 ULID 摆动），但**零丢失**（identifier 值集不变、绝不删行），该确定性由 `tests/unit/test_merge.py::test_cross_paper_conflict_flags_candidate_not_merge` / `test_cross_paper_conflict_winner_has_more_identifiers`（本记录 AC-3.1/3.2 节已计入 `test_merge.py` 的 18 例内）单独定向锁定，不纳入本随机属性测试范围。此边界与 [2026-07-23-phase3-acceptance.md](2026-07-23-phase3-acceptance.md) §1 AC-3.4 行记录的豁免口径一致。

**亲跑**：`test_merge_property.py`（全文件）**2 passed**（4.10s，含 250+50 examples 两条属性测试）。

## 2. 亲跑台账（本 worktree `chore/ledger-close` @ `main` `7a1e571`，`uv sync --extra auth` 后 `uv run pytest`，零真实网络）

| 载体 | 计数 | 承载 AC | 角色 |
|---|---|---|---|
| `tests/integration/test_merge_acceptance.py`（全文件） | **4 passed** | AC-3.1 / AC-3.2 | 正式判据（混合双路真实形态） |
| `tests/integration/test_merge_property.py`（全文件） | **2 passed** | AC-3.4 | 正式判据（属性测试） |
| `tests/integration/test_cli.py`（`-k "verify or pdf_layout_scope"` 子集） | **11 passed**（另 44 deselected） | AC-3.3 | 正式判据（CLI 集成层） |
| `tests/unit/test_verify.py`（全文件） | **15 passed** | AC-3.3 | 基础层补证（`verify_store` 单元覆盖） |
| `tests/unit/test_merge.py`（全文件） | **18 passed** | AC-3.1 / AC-3.2 / AC-3.4（跨 paper 冲突确定性锁，间接） | 基础层补证（`MergeEngine` 决策点单测） |
| **五文件合计**（显式 node-id 列出、单次 pytest 会话验证互不干扰） | **50 passed / 0 failed**（6.86s） | AC-3.1~3.4 全条 | — |

## 3. 结论

AC-3.1/3.2/3.3/3.4 判据（正式载体 + 基础层补证）本次在隔离 worktree 内**实跑全部复现 PASS**，零 failed、零 skipped、零真实网络。四条判据代码本身为 **Phase 3 T1/T2 已交付**（本记录零 `src/` 改动）；本记录的收口动作是：①把此前"分散三个测试文件"的实际范围厘清为五个文件（含两个基础层文件）并逐条列出承载载体到用例名颗粒度；②本次独立成文进 `testing/records/`；③以本次实跑数字（非旧报告转抄）落定 §2 台账。**AC-3.1~3.4 判定：approved（达成）**。

## 4. 移交/收尾

- Phase 3 检查单 #7 → Phase 3 报告 §5/§6 两次记录残项 → Phase 4 报告 §6 检查单 #10 延续 → **本记录成文收口**，跨 2 个 Phase 未清零的移交项闭合，无残留移交。
- `docs/INDEX.md` 新记录登记不在本任务范围（controller 合并时处理）。
- 本记录不改变 [2026-07-23-phase3-acceptance.md](2026-07-23-phase3-acceptance.md) 已有 AC-3 判定结论，两文档并存：后者是 Phase 3 整体汇总记录的一部分，本记录是 AC-3.1~3.4 的独立专属记录（检查单 #10 字面要求的交付物）。

## 5. 签署

- **G3 实跑核验（2026-07-24）**：AC-3.1/3.2/3.3/3.4 四条判据在 `chore/ledger-close` 隔离 worktree 内实跑全部 PASS（§1 逐条 + §2 台账，50 passed / 0 failed），与 [2026-07-23-phase3-acceptance.md](2026-07-23-phase3-acceptance.md) 既有判定结论一致，无矛盾发现，零 `src/` 改动。**结论：approved**。
