---
title: Adapter 设计 · NeurIPS Proceedings
status: review
owner: fable5
updated: 2026-07-20
---

# Adapter · `neurips_proceedings`

## 1. 定位

- **family**: `open_access`
- **服务 venue**：NeurIPS 正式 proceedings（1987 至今全量）；评审版（2022+）由 `openreview` 承担，双 channel 经 ingest identifier 合并（design/03 §4）
- **capabilities**: `DISCOVER | ENUMERATE | RESOLVE | FETCH`

## 2. 站点勘察摘要

来源：[research/site-survey/cs-ai-conferences.md](../../research/site-survey/cs-ai-conferences.md)（[LIVE] 2026-07-20）：

- 年页：`proceedings.neurips.cc/paper_files/paper/{year}`（1987+ 全量在线）；旧域 papers.nips.cc 内容一致并存；
- 单篇：`.../paper/{year}/hash/{hash}-Abstract-Conference.html`；PDF `.../file/{hash}-Paper-Conference.pdf`；早年文件名后缀不同（`-Paper.pdf`）⚠ 按年代兼容；
- 全静态、无认证、无防护；宣传站 neurips.cc 年年变但 proceedings 域稳定（域名稳定性分级见勘察 §末）。

## 3. 各阶段实现方案

- **discover_timeline**：1987→当年生成年度 Issue；当年是否已发布=年页 200 探测（track 复用）。
- **enumerate_issue**：抓年页解析条目（title + hash + 作者行）；`paper_count_claimed`=条目数，与 DBLP `conf/nips` 对账。identifier：`neurips` scheme（hash）。
- **resolve_assets**：hash → Abstract 页 URL + PDF URL（按年代后缀规则纯函数构造；构造失败回退解析 Abstract 页内链接）；Supplemental（`-Supplemental-*.zip`）附属资产。
- **fetch_asset**：HttpFetcher 直取。
- **healthcheck**：GET 最近年页 200 且条目 >0。

## 4. 限速与礼貌

- 默认 **1 req/2s，并发 1**（NFR-4）；一届枚举 1 个年页请求，负载极低；
- robots ⚠ 实现期复核。

## 5. 失败模式映射

| 现象 | error_class |
|---|---|
| 年页 404（当年未发布） | `gone`（track 候选语义） |
| 文件名后缀规则不中（年代边界） | `gone` → 回退 Abstract 页解析；连续多篇则 `parse` 标红 |
| 年页结构漂移 | `parse` |

## 6. Fixtures 与测试

- **T1 单元**：按年代的文件名后缀规则矩阵（1987/2000/2019/2022 边界）。
- **T3 fixture**：①某年年页快照 ②Abstract 页 ③404 年页。
- **T5 canary**：NeurIPS 2023 论文数已知答案；单篇 hash 的 title 匹配。
- **验收关联**：AC-2 系（backfill neurips --from 1987 全史回填）。

## 7. 风险与维护

- 双域并存（proceedings.neurips.cc / papers.nips.cc）：主用前者，后者作兜底镜像写入 quirks；
- 与 openreview 评审版的合并质量依赖 ingest 弱匹配（无共同强 id）——candidate 队列人工审核是设计内行为（D-007），canary 抽查合并正确率。
