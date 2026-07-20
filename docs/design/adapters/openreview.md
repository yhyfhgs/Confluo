---
title: Adapter 设计 · OpenReview
status: review
owner: fable5
updated: 2026-07-20
---

# Adapter · `openreview`

## 1. 定位

- **family**: `open_access`
- **服务 venue**：ICLR（2013+ 全史主源）、NeurIPS 评审版（2022+，与 `neurips_proceedings` 正式版双 channel）、CoRL/部分 workshop
- **capabilities**: `DISCOVER | ENUMERATE | RESOLVE | FETCH`（API 完整，无需 SEARCH——订阅经 arXiv/聚合源覆盖）

## 2. 站点勘察摘要

来源：[research/site-survey/cs-ai-conferences.md](../../research/site-survey/cs-ai-conferences.md)（[LIVE] 2026-07-20）：

- **双端点**：API v2 `api2.openreview.net`（2023+ venue）；API v1 `api.openreview.net`（更早届）——**必须版本探测路由**；
- venue id 模板：`ICLR.cc/{year}/Conference`（VenueSpec quirks 声明）；早期 venue id 格式有不一致，需兼容表；
- 官方 Python 客户端 `openreview-py`（`get_all_notes()` 按 invitation 批量），实现期直接依赖；
- PDF 直链：`https://openreview.net/pdf?id={note_id}`；
- 认证：读公开数据无需登录（免费账号可选，提高部分 venue 可见性）；无 Cloudflare。
- 官方限速政策未见明文 ⚠ 未核验——取保守默认并观察响应头。

## 3. 各阶段实现方案

- **discover_timeline**：对 venue 的每年探测 group 存在性（`{CONF}.cc/{year}/Conference`）；存在即建 Issue(label=year)。年度追新由 `crawler track` 的 OpenReview 探测器复用本逻辑（design/08 §4）。
- **enumerate_issue**：v2：按 venueid 查 notes（`content.venueid={id}`）→ 过滤 decision（accept 类）；v1：按 invitation（`{id}/-/Blind_Submission`）+ decision notes 关联。字段映射见 design/06 §5（title/abstract/authors 从 `content.*`）。quirks 开关 `include_reviews`（评审/decision 全量入库为可选）。
- **resolve_assets**：`pdf?id=` 直链（`url_strategy=direct`）；SI 在 `content.supplementary_material`（zip，asset kind=si）。
- **fetch_asset**：HttpFetcher 直取。
- **healthcheck**：GET v2 `/notes?id=<已知note>` 比对 title。

## 4. 限速与礼貌

- 默认 **1 req/2s，并发 1**（无官方明文 → NFR-4 保守默认；⚠ 实现期观察 429/头字段再调）；
- 批量拉取用 API 的分页参数（v2 `limit≤1000`）而非高频小请求；
- UA 标识同全局约定（D-014）。

## 5. 失败模式映射

| 站点现象 | error_class | 说明 |
|---|---|---|
| 429 | `rate_limited` | 按 Retry-After 退避 |
| venue group 404（当年未创建） | `gone`（探测语义=候选不存在） | track 探测器按"无候选"处理，非错误 |
| v2 查 v1 时代 venue 返回空 | `parse`（若未走版本路由）| 版本路由表修正；canary 覆盖新旧各一届 |
| decision 字段结构漂移（历年模板不同） | `parse` | 每届 accept 判定规则入 quirks，可按届覆盖 |

## 6. Fixtures 与测试

- **T1 单元**：venue id 模板展开；v1/v2 路由判定（按年边界 2023）；decision 过滤规则表（历届用例）。
- **T3 fixture**：①v2 notes 分页响应 ②v1 Blind_Submission+decision 关联样本 ③空 venue 响应。
- **T5 canary**：ICLR 2024 接收数已知答案（±口径差）；单篇已知 note 的 title。
- **验收关联**：AC-2.1（timeline iclr 2013→今）、AC-2.2（pull iclr 2024 limit 10）。

## 7. 风险与维护

- 历届 decision 表达方式多变（venue 自定义模板）是主要腐化面：quirks 按届覆盖 + canary 每届抽查；
- NeurIPS 评审版与正式版的 identifier 合并依赖 ingest 层（标题+作者强匹配不足时进 candidate 队列，D-007）——本 adapter 只负责打 `openreview` identifier；
- API v1 长期存在退役风险：老届数据一次性回填入库后对 v1 的运行依赖趋零。
