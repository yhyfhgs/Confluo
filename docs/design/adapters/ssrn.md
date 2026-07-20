---
title: Adapter 设计 · SSRN
status: review
owner: fable5
updated: 2026-07-20
---

# Adapter · `ssrn`

## 1. 定位

- **family**: `open_access`（D-011：`auth_level: free_account_preferred`——匿名可用但受限，免费账号更稳）
- **服务 venue**：SSRN 各 network/eJournal 切分的 `preprint_channel`（重点 FEN 金融、ERN 经济；见 [catalog/preprint-platforms.md](../../catalog/preprint-platforms.md)）
- **capabilities**: `ENUMERATE | RESOLVE | FETCH | SEARCH*`（无 DISCOVER——network/eJournal 清单人工维护于 VenueSpec；SEARCH* 受限：仅分类浏览下推，关键词全在本地过滤，design/09 §3）
- Econ/Fin 领域地位等同 arXiv 之于 CS，值得为其承担浏览器自动化成本（D-011）。

## 2. 站点勘察摘要

来源：[research/site-survey/econ-fin-preprints.md](../../research/site-survey/econ-fin-preprints.md)（[LIVE-TESTED] 2026-07-20）：

- **Cloudflare bot 管理已证实**：stateless 抓取 403 + "verify you are human"；robots.txt 禁 GPTBot/ChatGPT-User/Google-Extended，crawl-delay 5s；
- 结构：Networks（FEN/ERN/…）→ 各含数十 eJournals（FEN ~30 个）；浏览页 `ssrn.com/index.cfm/en/fen/`；
- 单篇：`ssrn.com/abstract={id}` → `papers.ssrn.com/sol3/papers.cfm?abstract_id={id}`；下载 `Delivery.cfm/...pdf?abstractid={id}&mirid=1`——**一次性 token 语义，必须同一浏览器上下文内即时使用**；
- 无官方 API；**内部 `api.ssrn.com` 未文档化端点明确禁用**（D-014 第 4 条，AC-0 红线）；
- 访问分层：作者自传 WP 免费（多数）；出版商定价内容需登录付费——本系统只取免费层。

## 3. 各阶段实现方案

- **enumerate_issue**：Issue=虚拟周桶（`fen/2026-W29`）。BrowserFetcher 打开 eJournal 浏览页按日期倒序翻页，解析条目（title/authors/abstract_id/post date）直至越过水位线；`abstract_id` 为 identifier(ssrn) 主键。增量语义：最近 N 页 id 集合差分（design/09 §5，无可靠时间过滤时的通用法）。
- **resolve_assets**：在浏览器上下文内打开 abstract 页 → 定位 "Download This Paper" → 生成 AssetPlan（`url_strategy=render_page`，URL 即 Delivery.cfm 链接但**标记为易失**，fetch 必须与 resolve 同上下文批次执行）。无下载按钮（仅摘要/付费）→ Asset 标 `needs_auth` 并降级元数据入库 + Unpaywall 兜底（design/03 §5"部分开放"）。
- **fetch_asset**：Playwright `expect_download` 在同一 context 内点击下载 → `*.part` → `%PDF` 校验 → 落盘。免费账号 session（若配置）经 CookieSessionProvider 注入同一 context。
- **search**：只下推 network/eJournal 选择；关键词/正则一律本地过滤（AC-6.3 验收一致率 ≥95%）。
- **healthcheck**：打开 FEN 浏览页首屏，判定：正常清单 / Cloudflare 挑战页（特征：`cf-chl` 元素、"verify you are human"文案）→ `CHALLENGED`。

## 4. 限速与礼貌

- **1 req/5s 为底线**（= robots crawl-delay 5s），实际执行时叠加 2–5s 随机抖动 → 有效间隔 5–10s（既守下限又不呈机械节律）；**日配额默认 100 篇/日**（可配）；并发 1；
- 遇 Cloudflare 挑战：**立即 BLOCKED(challenge) + 平台冷却 24h**，绝不自动过挑战（AC-0.2）；人工在有头浏览器过一次后 session 复用（D-006）；
- 尊重 robots：不访问其 Disallow 路径；不使用未文档化内部 API（AC-0 静态扫描项）。

## 5. 失败模式映射

| 站点现象 | error_class | 说明 |
|---|---|---|
| Cloudflare 挑战页 / 403 | `challenge` | BLOCKED + 冷却 24h |
| Delivery.cfm 返回 HTML 登录页 | `auth_expired`（有账号）/ `no_entitlement`（付费内容） | 前者触发 healthcheck；后者标记+兜底 |
| Delivery token 过期（跨批次复用） | `config` | 设计违规信号：resolve/fetch 必须同批 |
| 浏览页结构漂移（0 条目） | `parse` | canary 标红 |
| 慢响应/超时（站点惯常） | `transient` | 退避重试 3 次 |

## 6. Fixtures 与测试

- **T1 单元**：abstract_id 抽取（多种 URL 形态）；水位线差分算法（重叠页、删帖场景）。
- **T3 fixture**：①eJournal 浏览页快照（脱敏）②abstract 页（含下载按钮/无按钮两种）③Cloudflare 挑战页特征样本。
- **T4 集成**：mock 浏览器上下文验证 resolve→fetch 同批次约束；挑战页注入 → BLOCKED 流程。
- **T6 runbook**：真实免费账号首登→枚举 FEN 近 3 天→限量下载 3 篇→日志审计限速（testing/records 留痕）。
- **验收关联**：AC-5.1（枚举成功率 ≥95% + 限速审计 + 挑战正确 BLOCKED）、AC-6.3。

## 7. 风险与维护

- SSRN 属 Elsevier，风控策略随时收紧：canary 每周跑 healthcheck，连续 CHALLENGED 时在 catalog 标注降级（仅元数据经 RePEc 补充）；
- eJournal 名称/分类会调整：VenueSpec quirks 存 eJournal 浏览 URL 而非拼名称；名称核验列入实现期首项；
- 页面为服务端渲染但依赖 cookie 状态：fixture 录制必须脱敏（无活 session cookie，test-plan §2 快照纪律）。
