---
title: Phase 3 验收汇总记录 — 聚合元数据层
status: approved
owner: fable5
updated: 2026-07-23
---

# Phase 3 验收汇总记录（AC-3 全条 + AC-0 + DoD）

> 判定依据：[acceptance-criteria.md](../acceptance-criteria.md) AC-3/AC-0、[development-plan §Phase 3](../../plan/development-plan.md)、[phase3-implementation-plan.md](../../plan/phase3-implementation-plan.md)。
> 证据链：本 Phase 全部实现/审查报告（SDD ledger 索引）、[AC-3.5 在线验收记录](2026-07-23-ac35-acceptance.md)、AC-0 系统性扫描（2026-07-23，本记录 §3 摘录）。
> 代码基线：main @ `f114a09`（2154 passed / 8+16 skipped / 覆盖率 99.18%，`make check` exit 0）。

## 1. AC-3 逐条判定

| AC | 场景 | 判定 | 证据 |
|---|---|---|---|
| AC-3.1 | 强合并：同 DOI 经 arXiv 与 Crossref 两路注入 → 1 paper、≥2 identifier | **PASS** | `tests/integration/test_merge_acceptance.py` 混合双路真实形态（arxiv 经 `upsert_paper` 原路径 + crossref 经 `MergeEngine.ingest`，含大小写异形 DOI 变体）；fable 档审查验证非自证（2026-07-23） |
| AC-3.2 | 弱信号不自动合并：改名 WP↔刊发版 → 2 paper + 1 candidate_duplicate(decided=NULL) | **PASS** | 同文件 AC-3.2 用例 + 真改名反例；`paper_relation` 语义经审查逐行核 |
| AC-3.3 | verify 三类检出 + 正确修复建议 | **PASS** | `tests/integration/test_cli.py` 三类人为制造+组合场景+干净库零误报；修复建议经实测核实（`pull --force` 唯一真实路径），含两条"照建议执行→复检转清洁"强验证 |
| AC-3.4 | 顺序无关（属性测试） | **PASS**（口径注明） | Hypothesis 250 examples（derandomize）+ 720 排列穷举收敛；**豁免边界经 fable 档审查实验裁决**：桥接冲突输入类顺序敏感系已定语义数学必然，任意顺序**零丢失**（identifier 值集不变、不删行），冲突标记保守侧（candidate 待人审）；docstring 如实记载 |
| AC-3.5 | 五刊（含 QJE/JFE）零爬取完整期目+清单；篇数差异有解释 | **PASS**（双层） | 在线层：5 刊实跑抽样年 parsed==claimed 全部 **diff=0**（46/123/122/165/178），QJE 全史 6655≥锚点；离线层：fixture 回放全绿。issue 字段 OUP/Elsevier 存缴差异与 online-first 口径解释完备（[AC-3.5 记录](2026-07-23-ac35-acceptance.md)）。timeline 年粒度口径=W0 裁决（Crossref API 无卷期维度） |

## 2. Phase 3 DoD 判定（development-plan 原文逐项）

| DoD 项 | 判定 | 证据 |
|---|---|---|
| "任选 5 本期刊（含 QJE、JFE）不写任何出版社爬虫即可产出完整期目与论文清单" | **PASS** | AC-3.5 上表；venues/econ+finance 5 份 YAML `metadata_source: crossref`，零出版社爬虫 |
| "OA 副本命中率报告生成" | **PASS** | `crawler oa-report`（T5 交付，单 DOI GET 循环，markdown 统计）；离线测试锁定；unpaywall 金锚点在线复证 |
| 范围五源客户端 | **PASS**（5/5） | crossref/dblp/unpaywall（六阶段/RESOLVE 面）+ openalex/s2（enrich 通道，能力面诚实空集）；`crawler enrich` CLI 经 MergeEngine 回注 |
| metadata_source/fulltext_source 分离语义（D-005） | **PASS** | VenueSpec 纯附加字段+registry 三条校验+route 回退；既有 venue YAML 零改动零回归 |

## 3. AC-0 红线（系统性扫描 2026-07-23，独立执行）

五条全 **PASS**：①盗版源集成点 0（docs 3 处命中均为红线条款自述）；②CAPTCHA 求解 0（~20 处命中均为 BLOCKED 处置设计）；③git 全历史 942 blob 零 PDF、零真实凭证（占位样例逐个语境判定）；④obslog 8 敏感键（本 Phase 新增 email）+26 脱敏专测，records/reports 零凭证值（email 4 处均为 UA mailto 合规声明 D-014）；⑤13 adapter `source_note` 全备且与出处交叉核对（dblp 15rpm==Crawl-delay:4）、代码面零 robots 禁区构造。

## 4. 在线预算台账（plan §2-4 契约 ≤100）

| 分项 | 实际 | 备注 |
|---|---|---|
| 勘察增量复核（W0） | 19 | 合规，DBLP 一段间隔 3.90s<4s 已如实记录（正是促成 D-021 的佐证） |
| C-D 修复实测 | 15 | 15/15 顶格，token 零泄漏 |
| 审查期真实交叉验证（T3/T4/T5/T6） | 5+5+5+3 = 18 | 各台账在审查报告；T4 抓到 HIGH（bht schema） |
| AC-3.5 实跑+冒烟批量（T7） | 33 | 台账在 AC-3.5 记录 |
| **合计** | **85** | 预算内（W0 勘察与 C-D 属修复线预算，若仅计 §2-4 口径的冒烟+AC-3.5+锚点=51/100）——两种口径均合规 |

## 5. 纪律事项（如实）

- 本 Phase **零预算超支**（Phase 2 C-A 教训吸取：T7 33/50 远离硬顶即停）。
- controller 两次返工如实入档：①盲改未读测试区域（C2/C3 落地时，一轮返工后 Read-before-Edit）；②改共享 fixture 后未跑全量门禁，漏 `test_parse_single_work_title` 消费者（文档收尾 agent 全量实跑抓获，`f114a09` 跟修）。
- T4 实现 fixture 照抄 dump schema 的合成自证盲区（生产 100% 失败级）被审查期限量真实交叉验证拦截——该防线自 Phase 2 制度化以来第三次立功（pmlr/cvf/dblp）。

## 6. 移交与已知限制

- S2 key 用户申请中：s2 在线冒烟 skipif 门控（诚实 skip），key 到位后补跑（Phase 4 检查单）。
- aaai_ojs 锚点全库 OAI 补跑（Phase 2 检查单 #3 残项）：**移交 Phase 4/运维**（请求量大，本 Phase 预算未列）。
- 402 文本嗅探已知脆弱点、OpenAlex 预算单进程原子性、canary 凭证注入缺口：均已文档化，Phase 4 检查单在案。

## 7. 签署

- **初判（2026-07-23）**：AC-3.1~3.5 全 PASS（3.4 豁免口径注明）、DoD 全项 PASS、AC-0 全 PASS、预算合规——**待全分支终审放行后最终签署**。
