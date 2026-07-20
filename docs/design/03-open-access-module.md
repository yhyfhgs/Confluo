---
title: Open-Access 获取模块
status: approved
owner: fable5
updated: 2026-07-20
---

# 03 · Open-Access 获取模块

> 覆盖"开源直接可下载"一类源：预印本平台（arXiv、SSRN 公开面）、开放 proceedings（OpenReview、PMLR、CVF、ACL Anthology、NeurIPS、AAAI OJS）、开放期刊（TE、QE、AEJ 部分）、工作论文库（NBER、RePEc）。
> 决策依据：D-003、D-011。逐站细节在 [adapters/](adapters/) 各文档，本文定义模块级共性。

## 1. 功能说明

- 无认证（或可选免费账号）条件下完成 discover/enumerate/resolve/fetch 全链路；
- 尊重开放平台的公共资源属性：**bulk 优先、API 优先、逐页爬取是最后手段**；
- 为预印本源提供 SEARCH 能力（订阅 DSL 的执行端，见 design/09）。

## 2. 获取策略阶梯（模块级原则）

对任一开放源，adapter 设计必须按以下优先级选择获取方式，并在其文档中说明选择：

1. **官方 bulk 数据**：arXiv Kaggle 元数据全量、ACL Anthology 官方数据仓库、DBLP XML dump —— 历史回填一律走 bulk，不打在线接口；
2. **官方 API**：arXiv Query API/OAI-PMH、OpenReview API、Crossref —— 增量与精确查询；
3. **结构化站点页面**：PMLR 卷页、CVF open access 目录页、NeurIPS proceedings 年页 —— 结构稳定的静态 HTML，httpx 直取；
4. **需渲染/带防护页面**：SSRN —— BrowserFetcher，严格限速（D-011）。

## 3. Fetcher 配置（open_access 默认档）

| 参数 | 默认值 | 说明 |
|---|---|---|
| 并发 | per-domain 1，全局 4 | arXiv 官方建议单连接；见各 adapter 文档 |
| 限速 | 按 adapter 声明；无声明 1 req/2s | SSRN 特例 1 req/5s + 日配额 |
| 重试 | 网络类 3 次指数退避(2/8/30s)；4xx 不重试(429 除外) | 429 读 Retry-After |
| 缓存 | ETag/Last-Modified 条件请求；listing 页缓存 24h | 时间轴类结果持久化后不再重复请求 |
| UA | `PaperCrawler/<ver> (personal research; mailto:<user>)` | 表明身份（Crossref polite pool 同款要求） |
| robots.txt | 默认遵守，缓存 7 天 | 例外必须在 adapter 文档声明理由 |

## 4. 关键源的模块级要点

（详设计在各 adapter 文档，此处为跨文档口径）

- **arXiv**：三接口分工——历史回填用 Kaggle bulk / OAI-PMH（`from`/`until` 收割）；订阅增量用 Query API（`submittedDate` 窗口 + category 过滤）；单篇精取用 `abs/{id}` 与 `pdf/{id}v{n}`。版本语义：默认取最新版，DB 记录版本号；`--all-versions` 可选。
- **SSRN**：横跨双模块的特例（D-011）。枚举走 eLibrary 浏览页（按 network/eJournal 分类）与 RSS；`abstract_id` 为主键；下载链接是一次性 `Delivery.cfm` token，需在同一浏览器上下文内解析并即时使用；匿名受限时提示用户配置免费账号（转 free_account 档）。Cloudflare 挑战 → BLOCKED。
- **OpenReview**：API v2（`api2.openreview.net`）按 venue id（如 `ICLR.cc/2025/Conference`）取 notes；注意 2023 前旧 venue 在 API v1，adapter 需双端点路由；PDF 直链 `/pdf?id=`。评审/decision 数据可选入库（quirks 开关）。
- **PMLR**：`proceedings.mlr.press/v{N}/` 卷页 + 每卷 `bibliography.bib`；卷号↔会议年份映射表维护在 VenueSpec quirks（由 catalog 提供初始表）。
- **CVF**：`openaccess.thecvf.com/{CONF}{YYYY}` 目录页，全静态；论文页含 pdf 与 supplemental 链接。
- **ACL Anthology**：优先 `acl-org/acl-anthology` 官方仓库的结构化数据（全量 bib/JSON），网站仅用于兜底；Anthology ID（如 `2024.acl-long.123`）是天然稳定主键。
- **NeurIPS proceedings**：`papers.nips.cc/paper_files/paper/{year}` 年页静态枚举；2022 起同时在 OpenReview 有评审版——VenueSpec 用两条 channel 表达（`neurips`(正式) 与 `neurips_openreview`(评审)），ingest 层用 identifier 合并。
- **NBER**：`nber.org/papers/w{n}`；RSS 增量；PDF 对匿名开放但有礼貌限速要求。
- **TE/QE（Econometric Society 开放刊）**：全文开放，`econsoc` adapter 静态解析。

## 5. 失败模式与处理

| 模式 | 判定 | 处理 |
|---|---|---|
| 结构漂移 | 解析器命中 0 结果/schema 校验失败 | Task FAILED(kind=parse)；canary 报告标红该 adapter；不重试 |
| 资源消失 | 404/410 | Asset 标 `gone`，记录；Wayback 兜底仅对 VenueEra 级链接 |
| 限流 | 429/503+Retry-After | 退避重试；连续 3 次 → 该 domain 冷却 1h |
| 防护挑战 | Cloudflare/JS challenge 特征 | Task BLOCKED；提示人工（浏览器过一次挑战后 session 复用） |
| 部分开放 | PDF 需登录（如 SSRN 部分） | 降级：元数据入库 + Unpaywall 找 OA 副本 + 标记 `needs_auth` |

## 6. 测试与验收

- **单元/fixture**：每 adapter 对"1 个 listing 页 + 1 个详情页 + 1 个异常页"的 HTML/JSON 快照做解析回归（NFR-6）；URL 构造纯函数全参数矩阵单测。
- **契约**：见 design/02 §6。
- **在线冒烟**（手动/nightly，限量）：每 adapter 1 次 timeline + 1 篇下载，验证真网未漂移。
- **验收标准**（对应 AC-2.x/AC-5.x 摘录）：
  - AC-2.1 `crawler timeline iclr` 列出 2013→今全部届；
  - AC-2.2 `crawler pull iclr --year 2024 --limit 10` 成功落盘 10 个合法 PDF 且 DB/文件对账一致；
  - AC-2.3 arXiv 订阅查询窗口连续运行 7 天无重复无遗漏（与官方 listing 对照抽样）；
  - AC-5.1 SSRN 按 network 枚举近 7 天清单成功率 ≥95%，且全程限速合规（日志可审计）。
