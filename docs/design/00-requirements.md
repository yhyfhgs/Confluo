---
title: 需求规格与边界
status: approved
owner: fable5
updated: 2026-07-20
---

# 00 · 需求规格与边界

## 1. 背景与目标

研究者需要系统性地获取三个领域的学术文献：**CS/AI**（顶会为主）、**经济学**（顶刊+Field Top）、**金融学**（顶刊+量化）以及 **OR/MS**。文献散落在两类载体上：

- **开放载体**：arXiv、SSRN、OpenReview、PMLR、CVF、ACL Anthology、各会议 proceedings 站——可直接下载；
- **闭源载体**：Elsevier、Wiley、OUP、UChicago、INFORMS、IEEE、ACM 等出版社平台——需订阅/机构认证。

目标：一个**可插拔**的获取系统，统一"发现 venue 时间轴 → 枚举每期清单 → 精确选择 → 下载全文 → 入库管理"的全流程，且新增 venue 的成本尽可能低。

## 2. 用户画像与使用场景（User Stories）

单用户（研究者本人），具备：合法机构访问权限（校园网/EZProxy/SSO）、个人 SSRN/OpenReview 免费账号、基本命令行能力。

| # | 场景 | 示例指令（目标形态） |
|---|---|---|
| US-1 | 下载某期刊某卷某期全部论文 | `crawler pull jf --volume 79 --issue 3` |
| US-2 | 下载某会议某届全部/部分论文 | `crawler pull iclr --year 2025 --filter "LLM OR agent" --limit 50` |
| US-3 | 查看期刊完整出版时间轴 | `crawler timeline qje`（1886→今的卷期清单） |
| US-4 | 查看某期论文清单再决定下载 | `crawler list jfe --volume 160 → crawler pull jfe --doi 10.1016/...` |
| US-5 | 订阅 arXiv 主题增量 | `crawler watch arxiv --preset llm-agents --daily` |
| US-6 | 订阅 SSRN 子网增量 | `crawler watch ssrn --network FEN --keywords "asset pricing"` |
| US-7 | 回填某会议全部历史届 | `crawler backfill neurips --from 1987` |
| US-8 | 首次配置机构登录 | `crawler auth login elsevier`（弹浏览器人工登录一次） |
| US-9 | 单篇精确抓取（含元数据+全文+SI） | `crawler grab --doi 10.1093/qje/qjad001` |
| US-10 | 查看库内容与对账 | `crawler status / crawler verify` |

## 3. 功能需求（FR）

> 每条 FR 的验收标准见 [testing/acceptance-criteria.md](../testing/acceptance-criteria.md)，编号一一对应。

### 3.1 Venue 管理
- **FR-01 Venue 注册表**：以声明式配置（YAML）登记期刊/会议/预印本源；字段含标识符（ISSN、DBLP key、OpenReview venue id、arXiv category）、所属平台、认证需求、限速覆盖。
- **FR-02 时间轴发现**：对任一已注册 venue，获取其完整出版时间轴——期刊：卷/期/出版日期；会议：届/年份/proceedings 地址（含历年网址漂移的 VenueEra 记录）。
- **FR-03 年度追新**：会议新一届、期刊新一期的自动探测与登记（候选→人工确认）。

### 3.2 清单与选择
- **FR-04 期/届清单枚举**：展开任一期/届得到论文级清单（标题、作者、DOI/id、页码、摘要尽力而为）。
- **FR-05 精确选择**：支持按卷期、DOI/id、序号区间、标题关键词过滤选择要下载的子集；支持 dry-run 只看数量与清单不下载。

### 3.3 获取
- **FR-06 开放源下载**（open_access 模块）：对 OA 源直接下载 PDF 与附属资产（SI、HTML、BibTeX）。
- **FR-07 认证源下载**（auth_gated 模块）：使用用户自有凭证（cookie session / EZProxy / SSO / 官方 API key）下载订阅内容。
- **FR-08 会话管理**：首次人工登录、session 持久化与复用、过期检测、重登提示；多机构 profile。
- **FR-09 礼貌爬取**：per-domain 限速、并发上限、robots.txt 尊重（文档记载例外需注明理由）、标识性 UA、重试退避。
- **FR-10 断点续爬**：任意阶段中断后重跑，不重复下载、不遗漏；下载文件校验（大小/魔数/可选哈希）。

### 3.4 入库与管理
- **FR-11 元数据入库**：论文、venue、期/届、作者、identifier 多源合并入 SQLite；跨源同文关联（DOI/arXiv id 强合并，模糊匹配进待审）。
- **FR-12 文件管理**：PDF 按 `venue/year` 布局落盘，与 DB 双向对账；重命名/去重策略。
- **FR-13 全文抽取**：本地 PDF → 文本（可选 GROBID 结构化）；抽取结果入库可检索。
- **FR-14 观测性**：结构化日志、每次运行的 fetch 记录、失败清单、canary 腐化报告。

### 3.5 搜索与订阅
- **FR-15 主题订阅 DSL**：字段级（title/abstract/category/network）布尔查询；预置 topic 包（可自定义扩展）；范围限定 CS/AI、Econ、Fin（arXiv：cs.*、stat.ML、econ.*、q-fin.*；SSRN：FEN/ERN 等子网）。
- **FR-16 增量与护栏**：watermark 增量、数量阈值熔断、每日摘要报告。

## 4. 非功能需求（NFR）

| # | 需求 | 量化目标 |
|---|---|---|
| NFR-1 | 新增同平台期刊成本 | ≤30 分钟（仅写 VenueSpec YAML + 冒烟） |
| NFR-2 | 新平台 adapter 成本 | ≤2 人日（含调研、fixture、文档） |
| NFR-3 | 断点续爬 | 任意 kill 后重跑零重复零遗漏 |
| NFR-4 | 限速默认值 | 开放 API 按官方建议；无声明站点 ≤1 req/2s/domain；SSRN ≤1 req/5s |
| NFR-5 | 可观测 | 任何失败可在日志中定位到 (venue, stage, url, 原因分类) |
| NFR-6 | 离线可测 | 所有 adapter 解析逻辑可用 fixture 离线回归，不打真网 |
| NFR-7 | 单机资源 | 常驻内存 <1GB；SQLite 库 100 万论文级可用 |
| NFR-8 | 凭证安全 | 凭证/由凭证派生的 session 永不入 git、日志中脱敏 |

## 5. 非目标与合规（Out of Scope / Red Lines）

**明确不做：**
1. 绕过付费墙：无有效凭证时不通过任何灰色渠道获取闭源全文（不集成 Sci-Hub/LibGen 等）。
2. 对抗风控：不破解/外包 CAPTCHA，不伪造指纹对抗检测；遇风控 → BLOCKED 人工处理。
3. 再分发：不提供任何将下载内容公开、共享、批量导出给第三方的功能。
4. 全网采集：不做通用爬虫；只处理注册表内 venue。
5. Google Scholar 作为自动化主源（封锁激烈且违反其 ToS；仅允许人工辅助场景）。
6. Web UI（Phase ≤7 内）；多用户/团队协作；OCR 扫描件。

**合规基线：** 各站默认遵守 robots.txt 与 ToS；机构订阅内容的批量下载遵守出版社对机构用户的速率惯例（各 adapter 文档必须声明具体数值）；下载物仅本地个人科研使用。

## 6. 约束与假设

- 单机 macOS/Linux 运行；Python 3.12+（D-001）。
- 用户拥有至少一种机构访问方式；无机构权限的 venue 自动降级为"仅元数据 + OA 副本（Unpaywall）"。
- 磁盘：全量目标库预估 200GB 级（数万篇 PDF）。

## 7. 需求→设计文档映射

| 需求 | 设计文档 |
|---|---|
| FR-01..03 | [02-plugin-framework](02-plugin-framework.md)、[08-venue-tracking](08-venue-tracking.md) |
| FR-04..05 | [05-pipeline](05-pipeline.md)（enumerate/resolve 阶段） |
| FR-06 | [03-open-access-module](03-open-access-module.md) |
| FR-07..08 | [04-auth-gated-module](04-auth-gated-module.md)、[07-auth-session](07-auth-session.md) |
| FR-09..10 | [05-pipeline](05-pipeline.md) |
| FR-11..13 | [06-data-model](06-data-model.md) |
| FR-14 | [05-pipeline](05-pipeline.md) §observability、[testing/test-plan](../testing/test-plan.md) |
| FR-15..16 | [09-search-filter](09-search-filter.md) |
