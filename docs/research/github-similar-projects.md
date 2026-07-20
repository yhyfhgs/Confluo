---
title: 调研：GitHub 同类论文获取项目（20 项）与架构横向总结
status: approved
owner: fable5
updated: 2026-07-20
---

# GitHub 同类项目调研

> 来源：Sonnet subagent 于 2026-07-20 调研（WebFetch 仓库主页/README/关键源码 + GitHub REST API 核验 star/license/活跃度）。本文为归档（条目适度压缩，架构要点与可借鉴点保真）；文末"与本项目设计的对照"为主 agent（Fable 5）提炼。
> 两处名称核实纠正：pyalex 真实仓库为 `J535D165/pyalex`（"J-yin/pyalex" 不存在）；pybliometrics 规范仓库为 `pybliometrics-dev/`（ElsevierDev 下是已归档 fork）。

## 总览

| # | 项目 | Star≈ | License | 活跃度 | 定位 |
|---|---|---|---|---|---|
| 1 | jannisborn/paperscraper | 530 | MIT | 活跃 | 多源（PubMed/arXiv/bio-med-chemRxiv）元数据抓取工具包 |
| 2 | lukasschwab/arxiv.py | 1.4k | MIT | 非常活跃 | arXiv API 高质量单源封装范例 |
| 3 | ferru97/PyPaperBot | 630 | MIT | 停滞(2024-12) | Scholar/Crossref 检索+多路径下载（含盗版兜底，**合规排除**） |
| 4 | scholarly | 1877 | Unlicense | 放缓 | Google Scholar 抓取（反封锁工程） |
| 5 | danielnsilva/semanticscholar | 474 | MIT | 活跃 | S2 API 客户端，同步/异步双实现 |
| 6 | J535D165/pyalex | 397 | MIT | 活跃 | OpenAlex 轻封装，链式查询 |
| 7 | sckott/habanero | 250 | MIT | 活跃 | Crossref 薄客户端 |
| 8 | openreview/openreview-py | 249 | MIT | 非常活跃 | OpenReview 官方客户端，v1/v2 双 API |
| 9 | pybliometrics | 495 | MIT | 活跃 | Scopus/SD 官方认可客户端，缓存+多 key 配额池 |
| 10 | karpathy/arxiv-sanity-lite | 1656 | MIT | 定型(2023) | arXiv 订阅/推荐 daemon |
| 11 | zotero/translators | 1654 | AGPLv3+(文件内嵌) | 非常活跃 | 数百 per-site 抽取脚本 + manifest 注册体系 |
| 12 | neuml/paperetl | 697 | Apache-2.0 | 活跃 | 文献 ETL：parser 多态 × backend 多态 |
| 13 | jonatasgrosman/findpapers | 382 | MIT | 主分支活跃/发版滞后 | 8 库统一检索+去重合并+snowballing |
| 14 | monk1337/resp | 488 | Apache-2.0 | 活跃 | 多会议检索聚合（SerpAPI+site: 过滤） |
| 15 | george-gca/ai_papers_scrapper | 53 | MIT | 活跃 | Scrapy 抓 10 个 AI 会议 |
| 16 | pranftw/openreview_scraper | 67 | 无 license | 偏低 | OpenReview 多会场关键词检索 |
| 17 | paperswithcode-client | 188 | Apache-2.0 | 缓慢 | PwC 官方 API 客户端（平台已关，历史参考） |
| 18 | Mahdisadjadi/arxivscraper | 337 | MIT | 非常活跃 | arXiv 分类+日期轻量抓取 |
| 19 | titipata/pubmed_parser | 734 | MIT | 放缓 | PubMed XML 解析库（格式适配器） |
| 20 | mattbierbaum/arxiv-public-datasets | 479 | MIT | 半停滞 | arXiv 全量数据集流水线（OAI 断点续传） |

## 重点项目架构笔记（节选）

- **findpapers**（分层最规范的多源聚合）：`connectors/` 一源一文件，**能力 mixin 基类**（SearchBase / DOILookupBase / URLLookupBase 组合继承）+ 唯一 HTTP/限速基座 `ConnectorBase`；限速=线程安全 per-source `min_request_interval`；重试=一般错误与 429 **独立预算**各 3 次、指数退避封顶 60s、遵守 Retry-After、0–25% 抖动；`Paper` 统一模型 23+ 字段，`__eq__`=DOI（不区分大小写）或无 DOI 时标题匹配，**`merge()` 字段级合并**（不覆盖已有 DOI、authors token 去重）。
- **zotero/translators**（per-site 插件注册体系标杆）：一站一 `.js`；文件头内嵌 JSON manifest（translatorID GUID、`target` URL 正则、`priority` 数字消解冲突、`translatorType` 能力位掩码 import/export/web/search）；**search 型 translator 不可直接触发、只能被其他 translator 调用**（=可复用查询服务层）；`loadTranslator` 对象组合+回调劫持复用；**文件内置 testCases（样例 URL→期望字段）+ Scaffold 自动回归**——数百人维护数百个易腐脚本的质量关键。
- **openreview-py**（重试实现最完整）：`requests.Session` + 自定义 `LogRetry(Retry)`：`total=8, backoff_factor=1, backoff_max=120, jitter=1, status_forcelist=[429,500,502,503,504], respect_retry_after_header=True`；两代 API 并存=两个 Client 类不强行合并。
- **pybliometrics**（缓存与配额池标杆）：**磁盘缓存一等公民**（按 source/endpoint/view 分目录、查询哈希做文件名、命中即不耗配额）；**多 API key 池**（逗号分隔配置，耗尽自动切换）+ 配额自省（`get_key_remaining_quota()`）；配置文件+首次交互式 `init()` 凭证范式。
- **paperetl**（存储分层）：输入 parser 多态（按**格式**非按站点：arXiv XML/PubMed XML/TEI/CSV/PDF→GROBID）× 输出 backend 多态（SQLite/ES/JSON，URI scheme 工厂分发）；**articles/sections/citations 三表**关系模型；主键冲突捕获+Entry 时间戳决定覆盖=幂等增量批处理。
- **arxiv-sanity-lite**（增量订阅唯一完整范例）：cron daemon；**连续 N 页无新增提前终止**；paper id 存在性判重+时间戳比较处理改版（v1→v2）；退出码驱动"仅有新数据才算特征"的下游触发。
- **scholarly**（反封锁工程，反面上限参照）：ProxyGenerator 策略对象（主备代理分级）；**基于响应体内容（非状态码）检测验证码/封锁**；Selenium 人工解锁兜底——印证本项目"Scholar 不做自动化源"决策（R4）。
- **arxiv.py**：`Client`（连接池+限速+重试）/`Search`（查询）/`Result`（类型化结果）三段式——单 adapter 内部分层模板。
- **arxiv-public-datasets**：OAI resumptionToken 断点续传持久化——OAI-PMH 类源中断恢复标准做法。
- **PyPaperBot** ⚠ 合规排除：下载兜底链含 Sci-Hub/SciDB——仅借鉴其"来源优先级顺序尝试"编排形态，数据源本身排除（AC-0.1）。

## 横向架构总结（四维度）

**(a) 多源适配层**：行业默认起点=一源一模块目录约定；成熟度三层——零抽象（硬编码 dict 分发：paperscraper/resp）→ 能力组合基类（findpapers mixin、Scrapy BaseSpider 模板方法）→ **运行时自注册**（仅 zotero：manifest+正则匹配+优先级消解+testCases）。教训：两位数以上源必须"目录约定+自注册+Protocol 强约束"，但不必到 zotero 的重量级（数百站点场景才需要）。

**(b) 元数据统一模型**：单源客户端一致选择"贴源直通"（省维护）；只有真正多源聚合项目投入统一 schema，且全部收敛到**"核心强字段 + source-specific raw dict"折中**（纯联合 schema 不现实：各源字段交集小并集大）；paperetl 三表拆分（元数据/正文/引用）优于大 JSON blob。

**(c) 下载与限速**：值得直接复用的生产级重试仅 openreview-py 与 findpapers 两例；**"最好的限速是不请求"**——pybliometrics/pyalex 用磁盘缓存从根上减请求；限速/重试/缓存/凭证池应为**正交中间件**，不在每个 adapter 里重复实现；基于响应体内容判封锁（scholarly）对任何反爬源通用。

**(d) 增量订阅**：**全场最薄弱维度，无教科书级实现**——可拼装的最佳组合=arxiv-sanity-lite 心跳轮询+提前终止 ＋ paperetl/PwC 的主键/external_id upsert ＋ arxiv-public-datasets 的 resumption token 断点续传。这是本项目最有机会建立差异化架构价值之处。

## 与本项目设计的对照（主 agent 提炼）

| 调研发现 | 对本项目设计的意义 |
|---|---|
| findpapers 能力 mixin + 唯一 HTTP 基座 | **印证 D-002/D-003**：Capability 声明 + adapter 不自管限速（L2 统一）与业界最佳实践一致 |
| zotero manifest/priority/testCases | **印证** entry-points 注册（design/02 §4）与 fixture+canary 体系（test-plan）；testCases 内嵌思想已由"每 adapter 三件套 fixture + canary 已知答案"覆盖 |
| openreview-py/findpapers 重试参数 | **采纳为实现基准**：design/05 §4 重试策略数值与其同型；实现期直接参照两者代码 |
| pybliometrics 缓存+多 key 池 | **增补启发**：APIKeyProvider（design/07 §3.4）实现时预留多 key 轮换；HttpFetcher 的 ETag 缓存（design/03 §3）扩展为"配额敏感源的响应缓存" |
| 统一 schema 折中（核心字段+raw） | **印证 D-007/design/06**：paper.meta_json 弹性字段即该折中；三表思想与 paper/fulltext/relation 分离一致 |
| 增量订阅无成熟范式 | **印证 design/09 自研必要性**：watermark+重叠窗口+identifier 主键去重的组合在开源界无现成对标——按设计推进 |
| paperetl 幂等 upsert | **印证 D-004 幂等键**与 enumerate 批量 upsert（design/05 §5） |
| scholarly 反封锁上限 | **印证 R4/需求§5**：Scholar 自动化的工程与合规成本不可承受，不做 |
