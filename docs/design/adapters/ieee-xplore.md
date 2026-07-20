---
title: Adapter 设计 · IEEE Xplore
status: review
owner: fable5
updated: 2026-07-20
---

# Adapter · `ieee_xplore`

## 1. 定位

- **family**: `auth_gated`（IEEE 无整体 OA 新政，订阅制；OJ 系列开放刊除外）
- **服务 venue**：会议——ICASSP、ICRA、IROS、ICDM、FOCS（IEEE CS 出版）、CVPR/ICCV 的 2013 前 era；期刊——TPAMI、TNNLS、TKDE、TIP、TAFFC、IEEE/ACM TASLP（见 [catalog/ai-ml-journals.md](../../catalog/ai-ml-journals.md)）
- **capabilities**: `RESOLVE | FETCH`（+元数据 API 的 ENUMERATE 兜底）——枚举主干：会议走 DBLP、期刊走 Crossref（D-005）。

## 2. 站点勘察摘要

来源：[research/site-survey/cs-ai-conferences.md](../../research/site-survey/cs-ai-conferences.md) + [publisher-platforms-cs.md](../../research/site-survey/publisher-platforms-cs.md)（均 [LIVE] 2026-07-20）：

- 结构标识三件套：`punumber`（期刊/会议系列号，如 TPAMI=34）、`isnumber`（期号/届卷号）、`arnumber`（文章号）；文章页 `/document/{arnumber}`；
- 会议入口 `xpl/conhome/{conhomeID}/proceeding`——**conhome ID 逐年随机不可推导**（ICDM 2023=10415628），定位途径：DBLP `ee` 外链 / all-proceedings 聚合页 / 官方元数据 API——**不猜测**；
- **PDF 出口（[LIVE] 精确化）**：`stampPDF/getPDF.jsp?arnumber={id}`（加水印版，需登录态）；旧式 `stamp/stamp.jsp?tp=&arnumber=` 查看器仍在——两出口均含 referer/session 语义 → 浏览器上下文内下载最稳；
- **robots.txt（[LIVE]）**：通用 UA 禁 `/rest`、`/ielx*`；**AI 爬虫大面积封禁（25+ UA 含 ClaudeBot/Claude-User/CCBot/GPTBot…）**→ 依据 D-014：元数据绝不爬其页面（走 DBLP/Crossref/官方 API）；用户订阅态的单篇下载属正常授权使用（D-014 第 5 条），但 UA 照常诚实、限速保守；
- 官方 API（developer.ieee.org，[LIVE]）：**元数据 API + 新上线全文 API**（全文需联系销售）；注册+用途说明+机构网址，**人工审批**（工作日 ET）；条款限机构内非商业科研 ⚠ 配额未核验；
- 认证：Shibboleth/OpenAthens "Institutional Sign-In"（需图书馆员预注册）+ 校园 IP 段；**IEEE Access 等 gold OA 刊免登录**（open.ieee.org）。

## 3. 各阶段实现方案

- **enumerate**：**主干在 crossref（期刊 ISSN）/ dblp（会议）**；本 adapter 提供 Metadata API 兜底（若申请可用）：按 punumber+isnumber 列文章（补 DBLP 缺失的最新届）。
- **resolve_assets**：DOI/arnumber → 文章落地页 URL + `stamp.jsp` PDF 计划；`url_strategy=render_page`（referer/查看器语义）+ `auth_needed=institutional`。entitlement 启发式：落地页含 "Access to this document requires…" 即 `no_entitlement` 预判。
- **fetch_asset**：BrowserFetcher：storage_state 加载 → 打开 stamp.jsp → `expect_download`/内嵌 PDF 抓取 → `%PDF` 校验。批内每 20 篇 healthcheck（design/04 §4）。
- **healthcheck**：打开一篇已知有权文章的 stamp 页判定（登录态 + 无挑战 + content-type）。
- **conhome 定位子例程**（供 track/backfill）：year+会议名 → DBLP 该届任一 `ee` 链接提取 arnumber → 文章页读所属 conhome/isnumber → 写入 VenueEra.proceedings_url。

## 4. 限速与礼貌

- **串行 1 req/6s + 日配额 200**（auth_gated 全局纪律 design/04 §4；机构批量异常会触发对全校封禁——宁慢勿封）；
- 工作时段窗口 8:00–23:00；Metadata API 按其官方配额（⚠ 核验后填入）；
- robots 与 TDM 政策条目待勘察并入后补充（本节 status 保持 review 的原因之一）。

## 5. 失败模式映射

| 现象 | error_class |
|---|---|
| stamp.jsp 跳登录页 | `auth_expired` → 整批 BLOCKED |
| 落地页 "purchase/access required" | `no_entitlement`（不重试，Unpaywall/作者版兜底——FOCS/ICDM 作者常挂 arXiv/ECCC） |
| "unusual activity" / CAPTCHA | `challenge` → BLOCKED + 冷却 24h |
| 下载为 HTML 查看器壳 | `integrity`(auth_leak 疑似) → healthcheck |
| conhome 定位失败 | `parse`（记录该届待人工） |

## 6. Fixtures 与测试

- **T1 单元**：punumber/isnumber/arnumber 解析；conhome 定位子例程（DBLP ee→arnumber 抽取）。
- **T3 fixture**：①已登录文章页（脱敏）②未登录跳转页 ③无权限页 ④风控提示页——auth_gated 四件套（test-plan §3）。
- **T6 runbook**：真实机构凭证：login→healthcheck→取 1 篇 ICDM→清 cookie 过期演练（records 留痕）。
- **验收关联**：AC-4.1/4.2/4.3/4.6；AC-8 系（CVPR 2013 前 era 路由到本 adapter）。

## 7. 风险与维护

- conhome 随机性使会议侧永远需要"定位"步骤——已把定位子例程独立并 fixture 化（腐化可单独检测）；
- stampPDF 机制若改版（转 API 网关）需重勘察：canary 每周探测已知 arnumber；
- Metadata API 申请（人工审批、工作日 ET 发放）与配额是外部依赖：Phase 4 开工前提交申请并预留周期（计划依赖项）；全文 API 需销售渠道——个人研究者大概率不可得，设计不依赖；
- 勘察已并入（2026-07-20）：robots/API/PDF 出口/OJ 开放刊——可提交 approved 评审；剩余实现期事项：API 配额实测、OJ 系 gold OA 刊是否纳入 catalog（待用户需求）。
