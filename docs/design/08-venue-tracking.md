---
title: Venue 时间轴与年度追踪
status: approved
owner: fable5
updated: 2026-07-20
---

# 08 · Venue 时间轴与年度追踪

> 解决两个需求：FR-02（完整出版时间轴/期数历史）与 FR-03（会议每年换网址、新一届自动追踪）。决策依据：D-012。

## 1. 问题形态

- **期刊**：卷期结构稳定，Crossref 按 ISSN 可一次性枚举全部历史（含 1900 年代过刊的 DOI 化部分）；早于 DOI 时代的过刊在 JSTOR 等归档（tier 3 需求）。
- **会议**：三重漂移——①宣传官网年年换域名（www2024.thewebconf.org）；②proceedings 平台随年代迁移（COLT: ACM→Springer→PMLR；ITCS: 自建→ACM→LIPIcs；UAI: AUAI Press→PMLR）；③会议改名（NIPS→NeurIPS、EC 前身 Electronic Commerce、WINE 前身）。
- **预印本渠道**：无"期"概念，用虚拟月度桶（arXiv `cs.LG/2024-07`）统一进 Issue 模型。

## 2. VenueEra：时间轴的数据结构（见 design/06 §2）

每个会议每届一条 era；期刊在平台迁移/改名时开新 era。era 携带 `metadata_source`——**同一 venue 不同年代可指向不同 adapter**（例：COLT 2013+ → pmlr；1988–2000 → acm_dl；2001–2012 → springer）。Registry 路由因此按 (venue, year) 二维解析，而非只按 venue。

VenueSpec 中以 `eras` 段声明（catalog 初始化时人工整理，来源：DBLP + 本项目调研）：

```yaml
# venues/cs_ai/colt.yaml 片段（示例）
eras:
  - {from: 2013, metadata_source: pmlr, quirks: {volume_map: {2024: 247, 2025: 291, 2026: 336}}}
  - {from: 2001, to: 2012, metadata_source: springer}
  - {from: 1988, to: 2000, metadata_source: acm_dl}
```

## 3. 历史回填（backfill）策略

优先级顺序：
1. **DBLP conf 目录**：`dblp.org/db/conf/{key}/` 列出全部年份卷；卷页 `.xml` 直接给出该届论文清单与官方外链（勘察已实测）——**历史主干，一次性拿全**；
2. **平台官方结构**：PMLR 全卷列表、papers.nips.cc 年索引、ACL Anthology 仓库、CVF 目录——与 DBLP 交叉对账（paper_count_claimed 字段）；
3. **Wayback Machine**：死链 era（BMVC 老站、AUAI Press 旧 proceedings）的兜底，仅到"找到 PDF 链接"级，不批量爬 archive.org（其自身限速严格）；
4. **人工登记**：无任何机器可读源的年代（如 1980s 纸质 only）→ era 标 `status: offline_only`，明确不在系统能力内。

## 4. 年度追新（探测任务）

`crawler track --all` （建议 cron 每周）对每个 active 会议执行探测链，产出**候选 era**（不自动转正）：

| 探测器 | 逻辑 | 置信度 |
|---|---|---|
| DBLP 新卷 | conf 目录出现 {year+1} 卷 | 高（可自动预填全部字段） |
| OpenReview 新 venue | `{CONF}.cc/{year+1}/Conference` group 存在 | 高 |
| PMLR 新卷 | 全卷列表新增且标题含会议名 | 高 |
| 官网链接跟踪 | 上届官网/常设主站（icml.cc）解析 "next conference" 链接 | 中 |
| CFP 源 | WikiCFP 按会议名查询（辅助信号） | 低 |

候选处理流程：`crawler track review` 逐条展示（year、发现的 URL、证据）→ 人工 confirm/reject → confirm 后写入 VenueSpec 的 eras 段（工具自动编辑 YAML + 提示 git commit）。**时间轴数据的变更走与代码相同的 review 流程**——它本质是配置即代码。

## 5. 期刊侧的"追新"

简单得多：watch 任务对每个 active 期刊定期（默认周）调 Crossref `from-pub-date` 增量 → 新 Issue/Paper 入库 → 汇入订阅日报（design/09）。期刊改版（出版社迁移，如某刊从 Wiley 转 Elsevier）由 canary 失败暴露 → 人工开新 era。

## 6. 完整性对账

- `paper_count_claimed`（源头宣称的每期篇数，如 DBLP 卷记录数）vs 实际 enumerate 入库数：差异 >0 即在报告中列出（常见原因：front matter、勘误条目的计数口径）；
- 会议双源核对：DBLP 数 vs proceedings 平台数，长期背离的 venue 在 catalog 标注口径说明；
- `crawler timeline <venue> --audit`：输出该 venue 全部 era 覆盖区间、缺口年份（如 NAACL 未举办年 vs 数据缺失要区分——catalog 记录官方停办年）。

## 7. 测试与验收

- **单元**：era 路由解析（(venue,year)→adapter 的边界年）；候选去重（同一届多探测器发现合并为一条候选）。
- **fixture**：DBLP conf 索引页/卷 XML 快照的解析回归。
- **验收**（AC-8.x）：
  - AC-8.1 `timeline colt` 正确显示三段 era 且各段路由到不同 adapter；
  - AC-8.2 模拟 DBLP 出现新卷后 `track` 产出候选、`track review` confirm 后 YAML 被正确更新；
  - AC-8.3 `timeline naacl --audit` 区分"官方未举办"与"数据缺失"。
