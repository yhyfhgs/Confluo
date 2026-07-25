---
title: Adapter 设计 · ACL Anthology
status: implemented
owner: fable5
updated: 2026-07-26
---

# Adapter · `acl_anthology`

> 2026-07-22 全文重写：原稿（`updated: 2026-07-20`）被 pmlr 同批评审的 12 条前车之鉴逐项对照后判定需重写，且 [LIVE] 勘察（24 请求实测，归档 [research/site-survey/acl-anthology.md](../../research/site-survey/acl-anthology.md)）证伪原稿关键断言：**许可证非 "MIT/CC"**（仓库码 Apache-2.0；论文内容按 2016 年二分 CC BY-NC-SA 3.0 / CC BY 4.0）、**默认分支是 `master` 非 `main`**、**EMNLP Findings 不在 `{year}.emnlp.xml` 内而在按年合并的 `{year}.findings.xml`**（跨文件 join，原稿完全未覆盖）。本稿依据勘察逐项闭合。**AC-2.5 的验收载体。**

## 1. 定位

- **family**: `open_access`（无认证、无防护；勘察 §7 实测 24 请求全程匿名，站点侧无 Cloudflare/WAF/Set-Cookie/`Retry-After`/自定义限速头）。
- **服务 venue（catalog/cs-ai-conferences.md §NLP）**：`acl`、`emnlp`、`naacl`、`coling`、`eacl`（Findings 作为各 venue 的一个 track，非独立 venue——见 §4 enumerate）。Phase 2 的 AC-2.5 锚定 **emnlp**。
- **capabilities**: `DISCOVER | ENUMERATE | RESOLVE | FETCH`（四位）。**无 SEARCH**——冻结 `SourceAdapter` 协议无 `search()` 方法、Phase 2 无消费方（先例 arxiv.md §1 / openreview.md §1）；订阅/过滤命中经 enumerate + 本地过滤（`Selector.filter_expr`）达成，DSL 下推推迟 Phase 6。
- **获取策略阶梯的模范生**（design/03 §2 第 1 级"官方 bulk 数据"）：**GitHub 官方数据仓库 bulk 优先，网站仅承担 PDF 全文兜底**。量化理由（勘察 §3）：`/events/emnlp-2023/` 站点页内联全文摘要达 **7.6MB** HTML，而对应结构化 `data/xml/2023.emnlp.xml` 仅 **2.27MB** 且带 schema——bulk 更小、更结构化、更可审计。**本 adapter 不解析任何 landing/listing HTML**（故勘察 §3 记录的 Hugo `content=...` 属性乱序坑对本设计无影响）。

## 2. 站点勘察摘要

来源：[research/site-survey/acl-anthology.md](../../research/site-survey/acl-anthology.md)（[LIVE] 2026-07-21，24 请求实测；⚠ 该 survey 当前暂存 scratchpad，需主 agent 归档至此路径后本文档链接方生效）。要点：

| 事实 | 值 | 出处 |
|---|---|---|
| bulk 仓库 | `acl-org/acl-anthology`，默认分支 **`master`**（非 main），`data/{xml,yaml}`；**`data/` 下无 pdf/attachments 目录**——PDF 托管在 aclanthology.org 自建服务器（README "Hosting a mirror" 自证） | [LIVE] §1 |
| XML 权威结构 | `data/xml/schema.rnc`（RelaxNG，4528B 全文已抓）：`Collection(id) → Volume(id,type) → Paper(id)`；Paper 含 `title/author*/pages?/abstract?/url/bibkey/doi?/attachment*/video*/ingest-date?/removed?/retracted?/erratum*` | [LIVE] §1 |
| 文件命名两代 | 新式 `{year}.{venue}.xml`（如 `2023.emnlp.xml`，2.27MB）；旧式 `{单字母}{YY}.xml`（如 `D19.xml`，EMNLP 2019）——**新旧分界=摄入日期而非发表年份**，故命名非年份的纯函数，须以实际仓库清单为准 | [LIVE] §1/§2 |
| **Findings 跨文件** | EMNLP Findings **不在** `2023.emnlp.xml`，而在按年合并、不按 venue 命名的 `2023.findings.xml`（`collection id="2023.findings"` 内 `volume id="emnlp"` = EMNLP Findings，1059 篇）——enumerate 须跨文件 join | [LIVE] §1（结构性新发现） |
| Anthology ID 两代 | 新式 `2023.emnlp-main.1`（`.` 分隔 paper 号、不零填充）；旧式 `D19-1001`（无分隔、paper 号零填充 3 位）——**两套构造正则不共用** | [LIVE] §1/§2 |
| PDF 直链 | `https://aclanthology.org/{id}.pdf`，**同域 Apache 直挂、0 次重定向**、`Accept-Ranges: bytes` | [LIVE] §4 |
| 空态/404 | `aclanthology.org/{不存在id}/` → 404（Hugo 统一 HTML 页，无 JSON 错误体） | [LIVE] §5 |
| robots | `aclanthology.org/robots.txt` → **404（不存在，非空允许）**；无 `Crawl-delay`；站点无任何机器可读抓取策略 | [LIVE] §6 |
| 许可证 | 仓库码 **Apache-2.0**；论文内容 **<2016：CC BY-NC-SA 3.0；≥2016：CC BY 4.0**；"these policies only cover ACL materials"（协办第三方素材不在范围内） | [LIVE] §6 |
| 无 REST/JSON API | 官方把"GitHub 仓库 + PyPI `acl-anthology` 包"定义为 API；另有 `anthology.bib.gz`（11.8MB，随站点构建再生）批量导出——信息密度低于 XML，仅作交叉核对，不作主源 | [LIVE] §9 |
| GitHub 限速 | `api.github.com` 未认证 **60 req/hr**（`x-ratelimit-limit`）；`raw.githubusercontent.com` 经 Fastly，无观测到的限速头 | [LIVE] §1/§7 |

**AC-2.5 计数锚点（勘察 §8，全量下载后本地精确计数，EMNLP 2023）**：

| volume | 源文件 | anthology_id 前缀 | 篇数 |
|---|---|---|---|
| main | `2023.emnlp.xml` | `2023.emnlp-main.*` | 1047 |
| tutorial | `2023.emnlp.xml` | `2023.emnlp-tutorial.*` | 6 |
| demo | `2023.emnlp.xml` | `2023.emnlp-demo.*` | 52 |
| industry | `2023.emnlp.xml` | `2023.emnlp-industry.*` | 77 |
| findings | `2023.findings.xml`（`volume id="emnlp"`） | `2023.findings-emnlp.*` | 1059 |
| **合计** | | | **2241** |

## 3. 认证与许可边界（本 adapter 的运行前提）

- **认证**：`auth.level = none`（勘察 §7 全程匿名可读）；venues/cs_ai 各 ACL venue YAML 保持 `auth: {level: none}`。**无 storage_state、无 token、无 AuthProvider 依赖**。
- **许可红线（纠正原稿 "MIT/CC"，勘察 §6）**：
  - **元数据**（本 adapter 解析的 `data/xml/*.xml`）随仓库 **Apache-2.0**，明确为数据消费而公开（勘察 §9 FAQ 自证），程序化 bulk 读取即其设计用途。
  - **论文内容**（PDF）按年二分：**2016 年前 CC BY-NC-SA 3.0（含 NonCommercial）**，**2016 及以后 CC BY 4.0**。本工具为**个人科研检索下载、无再分发、无训练用途**（AGENTS §6 / D-014），满足 NC 限制。**建议**：enumerate 依 paper 年份产出 `PaperStub.meta['license']`（<2016→`CC-BY-NC-SA-3.0`；≥2016→`CC-BY-4.0`），把 NC 边界做成机器可见字段，为未来任何再分发场景预留合规护栏。
  - 协办第三方素材不在 ACL 许可范围内（"only cover ACL materials"）——本期不特殊处理，标注为已知边界。
- **robots/bulk 合规姿态（D-014）**：
  - `aclanthology.org` **实测无 robots.txt**（勘察 §6，404），无 `Crawl-delay`，无机器可读策略——礼貌节流依 NFR-4 默认值（§5），无站点侧依据可参照，直接写明实测结论（不留"实现期复核 robots"悬项）。
  - `raw.githubusercontent.com` / `api.github.com` 为 GitHub 基础设施；我方仅访问**仓库自身公开发布、且官方声明供数据消费**（勘察 §9）的 `data/xml/` 文件与目录树——属文档化 bulk 数据消费，非受网页爬虫公约约束的逐页抓取（推理同 arxiv.md §4 对 API ToU 的处理）。UA 按 D-014 诚实标识（`PaperCrawler/<ver> (personal research; mailto:<user>)`），由 http.py 调用方统一注入。

## 4. 各阶段实现方案

### discover_timeline（venue 时间轴 → IssueRef）

- **机制（§9-★4 已裁决：方案 A git-tree）**：以官方仓库 `data/xml/` **文件清单**为权威源——一个 `{...}.xml` 文件存在 ⟺ 该 (venue, year) 有 proceedings。
  - **本稿采用（A）纯 HttpClient 路径**：`GET api.github.com/repos/acl-org/acl-anthology/git/trees/<master 下 data/xml 的 sha>`（一次拿全 1660 条目名），按 venue 的 anthology slug + 两代命名规则匹配出该 venue 的年份集。清单结果**进程内缓存**（供 enumerate 复用，见下），任务级按时间轴新鲜度 **24h** 缓存——discover 实际 ≤1 次/天，60/hr 未认证上限**非约束**（勘察 §1 记录该上限；若未来高频则配认证 token 提至 5000/hr）。
  - **备选（B）shallow clone**（`git clone --depth 1 --branch master` 于 `PAPER_CRAWLER_HOME`，仓库外，`git pull` 刷新）：无速率上限、enumerate 可读本地文件全离线（最强 AC-2.5 姿态），代价是引入 git 子进程依赖。列为**重回填优化**（勘察 §1 结论：clone 适合"全量建目录"、单文件 raw 适合"单年回填"），§8 记为维护项。
- **IssueRef 字段分解（定死，幂等键钉死）**——`issue` 表 `UNIQUE(venue_id, volume, number, label)`（design/06），故 `label` 承担年份区分：
  - `venue_id` = `venue.id`（如 `"emnlp"`）
  - `volume` = **`None`**（track 不建模为 volume，理由见下）
  - `number` = **`None`**（ACL 无"期"概念）
  - `year` = `int(YYYY)`——`--year` selector 过滤的生效列
  - `label` = **`str(year)`**（如 `"2023"`；与 openreview `label='YYYY'` 对齐；`(emnlp,None,None,'2023')` 天然唯一）
  - `pub_date` = `None`（月份是 paper 级事实，非 volume 级可靠字段；同 openreview）
  - `paper_count_claimed` = `None`（discover 不解析文件体；由 enumerate 回填实数，对账用）
- **非年度 venue（NAACL/EACL "非每年"，catalog 标注 + D-012 VenueEra）**：清单里无文件 ⟺ 无 IssueRef，缺届自然表达，无"停办年"假错误。**AC-8.3"官方未举办年 vs 数据缺失年"的区分**：清单缺失只证"仓库无此文件"，是否"官方未举办"须由 §7 锚点表对照外源（DBLP `conf/naacl`）人工核准——本 adapter 只负责如实呈现"有数据的年"，两类缺口的判定交 `--audit`（AC-8.3，跨 Phase）。
- `since` 形参：若给定则过滤 `year >= int(since)`（映射 `backfill --from`）；`--year` 由 pipeline 在 discover 输出上后置过滤（openreview 先例）。

### enumerate_issue（IssueRef → PaperStub*）——AC-2.5 热路径

- **(venue, year) → 源文件解析（deterministic，无逐页爬取）**：由 §discover 的进程内清单缓存把 (venue, year) 映射到**实际**文件名（冷缓存则 enumerate 惰性拉一次 tree），彻底避开"新式还是 D 式"的猜测；无清单时回退**新式→旧式构造探测**（先 `{year}.{venue}.xml`，legal-404 再 `{LETTER}{YY}.xml`，`LETTER` 取 venue YAML `quirks.anthology_legacy_prefix`，如 EMNLP=`D`）。
  - 读取方式：(B) 模式读本地 clone 文件（离线）；(A) 模式 `HttpClient.get_bytes` 拉 `raw.githubusercontent.com/acl-org/acl-anthology/master/data/xml/{file}`（勘察实测 2.27MB / 1.45s）。
- **Findings 跨文件 join（结构性核心）**：主文件 `{year}.{venue}.xml`（含 main/tutorial/demo/industry… 全 volume）之外，**再读 `{year}.findings.xml` 并按 `volume id == venue slug` 过滤**出该 venue 的 Findings 子集（EMNLP → `volume id="emnlp"` → `2023.findings-emnlp.*`）。二者合并为该 issue 的全部 PaperStub。`{year}.findings.xml` 不存在（该年无 Findings track，如 2020 前）→ **legal empty（非错误）**，跳过（见 §6 重分类）。
- **两代 ID 解析（xml.etree，解析器与网络解耦，T3 直喂 bytes）**：
  - anthology_id **优先直接读 `<url>` 元素文本**（schema `url-with-checksum` 的"本地文件名"变体即裸 id，如 `2023.emnlp-main.1`；若为完整 https URL 变体则从中截取）——**读取优先于构造**，规避两套构造正则的错配风险。
  - 构造规则（仅作校验/`<url>` 缺失兜底，T1 覆盖）：新式 `{collection_id}-{volume_id}.{paper_id}`（不零填充）；旧式 `{collection_id}-{volume_id}{paper_id:03d}`（零填充 3 位、无分隔）。
- **字段映射**：
  - `identifier(scheme='anthology').value` = anthology_id **原样**（新式小写 venue slug、旧式大写字母前缀，**不做 lower/upper 归一**——站点侧已是规范形式；此值同时是 PDF URL 与站点 canonical 的反查锚点，满足人工可核验，pmlr B2 先例）。
  - **DOI（★ 需主 agent 裁定）**：XML `<doi>` 如 `10.18653/v1/2023.emnlp-main.1`。**本稿采用方案 A——产 `identifier(scheme='doi')`**（value=裸 DOI，剥 `https://doi.org/` 前缀、大小写按原文保留）。**边界规则**：DOI 的注册前缀由本源发行方自持（`10.18653` = ACL）且与本源原生 id **一一对应**时，它是**本 artifact 自身的规范标识**，产 identifier 正是 AC-3.1"同 DOI 两路注入→1 paper ≥2 identifier"所要的强合并；**这与 arxiv `journal_ref`（指向另一 artifact 的跨源线索→入 meta）的 R3 裁决不冲突——判据是"本 artifact 自身 DOI"还是"指向他源的线索"**。同理 AAAI OJS 的自持 DOI 亦按此产 identifier。**备选方案 B**（保守，严守 arxiv/openreview "Phase 2 不产第二 identifier"）：DOI 入 `PaperStub.meta['doi']`，留 Phase 3 ingest 建标识。（§9-★3 已裁决：方案 A 定稿。）
  - `PaperStub.meta` 键：`track`（`main`/`findings`/`demo`/`industry`/`tutorial`…，即 volume id——**track 入 meta 而非建 Issue 的直接依据：design/06 `paper.meta_json` 注释显式列 "track"**）；`bibkey`（`<bibkey>` 如 `zhang-etal-2023-iag`，人工引用/交叉核对便利）；`license`（§3 按年二分）；`pages`（`<pages>`）；`anthology_collection`（collection id，如 `2023.emnlp`/`2023.findings`）。
  - `title`←`<title>`（含 `<fixed-case>` 等内联标记，取文本）；`authors`←`<author><first><last>`；`abstract`←`<abstract>`（勘察 §1：近年数据 abstract 完整内联，enumerate 阶段即得，无需回站）；`year`/`pub_date`←`<year>`/`<month>`。
  - `paper_count_claimed`（回填至 IssueRef 无处存——IssueRef 由 discover 产出且 frozen 无 meta）：改由 enumerate 返回的 stub 实数经 pipeline 落 `issue.paper_count_claimed`，作 enumerate 完整性对账（design/06 §对账）。
- **空态**：`{year}.{venue}.xml` 与旧式候选**均** 404 → 该 (venue,year) 无 proceedings → **legal empty（非错误）**，返回空序列正常完成（§6）。

### resolve_assets（PaperStub → AssetPlan*）——纯构造零网络

- **PDF**：`https://aclanthology.org/{anthology_id}.pdf`（勘察 §4 同域直挂）；`kind=PDF`、`url_strategy=direct`、`auth_needed=none`、`version=None`。anthology_id 直接读 stub 的 `identifier('anthology')`，**不重新发请求**（真零网络，无 pmlr B3 式"零网络断言与实际矛盾"）。
- **附件 SI**：XML `<attachment>`（如 `D19-1001.Attachment.pdf`）→ `kind=SI`，URL `https://aclanthology.org/attachments/{local-filename}`。✅ **已核实 [LIVE 2026-07-26]**：HEAD `attachments/D19-1001.Attachment.pdf`（样本 = 勘察 §1 真实 `D19.xml` 数据）→ **200**，`Content-Type: application/pdf`、`Content-Length: 956360`、`Last-Modified: 2019-11-03` 与 D19 卷 `ingest-date` 精确吻合（排除软 404/占位页）、Apache 直挂 0 重定向；完整响应头与证据链归档 [survey §10](../../research/site-survey/acl-anthology.md)。原 ⚠ [UNRESOLVED]（"实现期首个 SI fetch 前须 HEAD 核实前缀"）就此闭合，SI plan 撤销"实验性/不计入 AC-2.5"限定语、转正式资产面（AC-2.5 判据本身锚定 enumerate 计数 + 无逐页爬取（§7），SI 不在判据内，判定口径不变）。
- **不产**：`.bib`/`.xml`(MODS) 单篇副产物端点（存在但非 paper artifact，勘察 §2/§9）、`<video>`（媒体，非下载目标）——保持资产面精简。

### fetch_asset（AssetPlan → FetchResult）

- `HttpClient.stream(url)` 取流交 `io.write_stream`（**唯一持续在线动作**，仅命中 aclanthology.org 的 `*.pdf`）。`%PDF` 魔数权威校验在 pipeline（冻结分工）。
- PDF 404（早期个别无 PDF，或 `<removed>`/`<retracted>` 条目）→ `gone`（HttpClient 404→GONE 正确无需重分类；enumerate 可依 `<removed>`/`<retracted>` 预标跳过，减少无谓 fetch）。

### healthcheck（匿名、轻量）

- **bulk 路径存活**：`GET raw.githubusercontent.com/acl-org/acl-anthology/master/data/xml/schema.rnc`（勘察实测 4528B，稳定小文件）→ 断言 200 且正文含 `Collection`/`Paper` 元素定义——**同时验证 `master` 分支名正确**（catches 分支/URL 系统性错，防 §6 legal-404 重分类掩盖真 bug）。
- **PDF 域存活**：`GET aclanthology.org/`（首页）→ 断言 200。
- 两项均无认证、无解析 landing。

## 5. 限速与礼貌

| domain | 速率 | 依据 |
|---|---|---|
| `raw.githubusercontent.com`（enumerate bulk，主域 [0]） | **30 rpm，并发 1**（1 req/2s） | 无站点声明的机器可读爬取策略；NFR-4"无声明站点 ≤1 req/2s/domain"；bulk 天然低频（单年 1–2 文件） |
| `aclanthology.org`（PDF fetch） | **30 rpm，并发 1**（1 req/2s） | 勘察 §6 实测无 robots.txt、无 Crawl-delay、无限速头；NFR-4 默认 |
| `api.github.com`（discover tree，仅 (A) 模式） | **30 rpm，并发 1** + 遵守 `x-ratelimit-*` | 未认证 60/hr 硬上限（勘察 §1）；24h 缓存下 ≤1/天远低于此；建议认证 token 提至 5000/hr |

- `default_rate` = 30 rpm / burst 1，`source_note` 引"勘察 §6 实测无策略 + NFR-4 默认"（`RatePolicy.source_note` 强制）。UA 按 D-014（http.py 调用方注入，本 adapter 不读 config）。
- bulk 单文件拉取（2.27MB）比逐页爬 7.6MB 站点页更省更礼貌，是设计层的最大礼貌（勘察 §3）。
- **(B) clone 模式**：git 子进程走 github.com，不经本限速器（git 自身节流 + 24h 低频）；离线读本地文件时 enumerate 零在线请求。

## 6. 失败模式映射

| 站点现象 | error_class | 说明 |
|---|---|---|
| `{year}.{venue}.xml` **与旧式候选均** 404（该 venue-year 无 proceedings） | —（**非错误**） | legal empty：返回空 PaperStub 序列正常完成（NAACL/EACL 停办年、venue 起点前）。HttpClient 404→GONE，**adapter 对 enumerate 元数据 GET 的 404 上下文重分类为 legal-empty**（openreview 403→auth_expired 先例）。**防掩盖真 bug**：healthcheck/canary 用同模板断言 `schema.rnc` 200——系统性 URL/分支错会让 healthcheck 先失败，不会被"每年皆空"静默掩盖 |
| `{year}.findings.xml` 404（该年无 Findings track） | —（**非错误**） | 同上重分类；Findings join 得空子集，非故障 |
| XML 畸形 / 与 `schema.rnc` 结构不符（解析失败） | `parse` | canary 标红；锁上一 good commit 继续用（clone 模式）或标红待人工 |
| PDF 404（早期无 PDF / `<removed>` / `<retracted>`） | `gone` | HttpClient 404→GONE 正确；enumerate 预标可提前跳过 |
| raw/aclanthology 超时、5xx | `transient` | HttpClient 统一映射（pipeline 退避 2/8/30s） |
| raw/aclanthology 429 | `rate_limited` | 30rpm 自限下罕见；HttpClient 统一处理 |
| （仅 (A) 模式）`api.github.com` 60/hr 耗尽 → **403** | `rate_limited` | ⚠ GitHub REST 用 **403**（非 429）表限速。**复审修订 2026-07-22：冻结 HttpClient 不透传响应头（get_* 无 headers 出口），无法读 `x-ratelimit-remaining`**——故采**域级上下文重分类**（openreview 403→auth_expired 同款先例）：adapter 对 `api.github.com` 的 403 **一律**重分类 `rate_limited`（该域对公开仓库匿名读的 403 压倒性语义即限流，无"真无权限"场景）。(B) clone 模式不涉此 |
| 请求构造缺陷（未声明能力被调等） | `config` | `CapabilityNotSupported`→CONFIG；HttpClient 其余 4xx→CONFIG，响亮停机转 BLOCKED |

**已知冻结限制（本期承认，arxiv.md §5 / openreview.md §6 同批口径）**：①`FetchResult` 无 `http_status`，`fetch_log.http_status` 本期恒 NULL；②metadata 阶段请求（discover 的 tree、enumerate 的 bulk XML 拉取）**不入 FetchLog**——其限速审计证据为 **obslog jsonl**（http.py 每请求 debug 事件：`domain`/redact `url`/`status`/`elapsed_ms`），这正是 AC-2.5 日志证据的载体（§7）；③`Retry-After` 仅解析入 detail 供观测，不驱动重试调度；④**`HttpClient` 无 HEAD 方法**——故 healthcheck/canary 的存活探测用小文件 GET（`schema.rnc` 4.5KB）而非 HEAD，`anthology.bib.gz`（11.8MB）不作 GET 型 canary；⑤**`HttpClient` 不透传响应头**（get_* 无 headers 出口）——adapter 读不到 `x-ratelimit-*`，github 限流判定采域级 403 重分类（§6，复审修订）。

## 7. Fixtures 与测试

- **T1 单元**：①两代 anthology_id **解析（优先读 `<url>`）+ 构造 + 归一**矩阵（新式 `2023.emnlp-main.1` 不零填充点分隔 × 旧式 `D19-1001` 零填充 3 位无分隔 × 非法形态拒绝 × 大小写原样断言）；②(venue,year)→源文件名映射（新式 `{year}.{venue}.xml` × 旧式 `{LETTER}{YY}.xml`，prefix 来自 venue YAML）；③volume→`track` 提取 + Findings 跨文件 `volume id==venue` 过滤；④DOI 归一（剥前缀/保大小写）与"本源自持 vs 跨源线索"边界判定；⑤license 按年二分推断。
- **T3 fixture（覆盖 §6 全部 error_class，test-plan §6 强制；难录形态合成并标注"合成 fixture"，arxiv 先例）**：①`2023.emnlp.xml` 节选（≥2 volume、含带 `<doi>`/`<attachment>`/`<abstract>` 各一的 paper）②`2023.findings.xml` 节选（含 `volume id="emnlp"` **及另一 venue volume**，验 join 过滤）③旧式 `D19.xml` 节选（旧式 id 端到端）④对①②③的 golden 解析输出 ⑤畸形 XML→`parse` ⑥raw 404（不存在的 `{year}.{venue}.xml`）→legal-empty**（证重分类，非 error）** ⑦PDF 404 响应→`gone` ⑧5xx（合成）→`transient` ⑨429（合成）→`rate_limited` ⑩（(A) 模式）`api.github.com` 403（合成）→`rate_limited` 域级重分类 ⑪400（合成）→`config`。
- **T4 集成（MockTransport 全链路）**：`pull emnlp --year 2023` discover→enumerate→resolve 全链，**断言 enumerate 产 2241 stub、跨 5 volume、计数与 §7 anchor 全等**；两代路径各一；resolve 产 2241 个 PDF plan（URL=`aclanthology.org/{id}.pdf`）。
- **AC-2.5 验收机制（D-019 锚点快照 + 日志证据双判据）**：
  - **anchor golden 表** `tests/fixtures/acl_anthology/anchor-emnlp-2023.json`——逐 volume `{anthology_volume_id, source_file, paper_count}` + `total` + `cross_source={dblp:'conf/emnlp', note}`（本例见 §2 表，total 2241）。**D-019 人工 DBLP 核准已闭合 [LIVE 2026-07-23]**：DBLP `conf/emnlp` 下 5 个子卷（`emnlp2023{,t,d,i,f}`，经 `/db/conf/emnlp/` 索引页发现，一一对应 main/tutorial/demo/industry/findings）逐一实测——main/tutorial/demo/industry 四卷剔除 DBLP 各卷唯一的 1 条 "Frontmatter." 封面条目后与本表 `paper_count` **精确匹配**；findings 剔除 Frontmatter 后仍余 **+1 未消解残差**（DBLP 1060 篇 vs 本表 1059，预算内未进一步查明，如实标注非强行凑合）。核准出处见 fixture `cross_source.dblp_toc_counts`/`note`。
  - **日志证据 grep 判据（"无逐页在线爬取"）**：跑 `pull emnlp --year 2023` 后对 obslog jsonl——
    - **正向**：含 `domain=raw.githubusercontent.com` 且 `url` 匹配 `data/xml/2023\.emnlp\.xml` 与 `data/xml/2023\.findings\.xml` 的事件（bulk 路径确被使用）；
    - **负向（核心）**：`grep 'aclanthology\.org' obslog.jsonl | grep -E '/(events|venues)/|/[^/]+/$'` **返回 0 行**（无任何 `/events/`、`/venues/`、或 `/{id}/` landing 逐页抓取）；aclanthology.org 事件**仅** `*.pdf`（fetch 阶段资产，非页面爬取）。
  - **证据分层（D-018 模式）**：T4 离线（fixture 全链，2241 计数/plan/魔数/对账 + 上述 grep 判据在离线 obslog 上成立）＋ T5 在线冒烟（真响应可解析入库）＝ **Phase 2 AC-2.5 判定**。
- **T5 在线冒烟（预算 `MAX_REAL_REQUESTS` ≤6）**：healthcheck 1（`schema.rnc`）＋ enumerate 真拉 `2023.emnlp.xml` + `2023.findings.xml` 各 1 ＋ 单篇 PDF fetch 1 ＋ discover tree 1（(A) 模式）；结构未漂移、限速合规、grep 判据在真实 obslog 上复现。
- **canary（3 样本 + 存活基线，抗 flake；比对规整化 title + 稳定字段，非纯计数——pmlr #12）**：
  - (a) `2023.emnlp-main.1`：规整化 title "IAG: Induction-Augmented Generation Framework…" + `track=main`（新式）；
  - (b) `D19-1001`：title "Attending to Future Tokens for Bidirectional Sequence Generation" + 旧式 id 路径（旧式）；
  - (c) `2023.findings-emnlp.<N>`：任一 Findings 样本，验跨文件 join + `2023.findings-emnlp.*` id 构造（Findings 路径）；
  - **存活基线** `schema.rnc` GET 200（无 parse 的 bulk 存活哨兵，openreview 匿名基线 canary 先例；`bib.gz` HEAD 因 HttpClient 无 HEAD + 11.8MB 体积不用）。
- **验收关联**：AC-2.5（本 adapter 主载体）；AC-8.3（NAACL 缺口区分，跨 Phase）；测试类型定义见 [testing/test-plan.md](../../testing/test-plan.md)。

## 8. 风险与维护

- **命名两代边界（摄入日期非发表年份）**：某 (venue,year) 是 `{year}.{venue}.xml` 还是 `{LETTER}{YY}.xml` 不可按年份硬切——**以仓库实际清单为准**（§discover 清单缓存已据此），历史补录卷会迁到新式；canary 每年抽查两代样本各一。
- **discover 机制（★，见文末）**：(A) REST-tree 纯 HttpClient / (B) shallow-clone git 子进程 二选一；(B) 是重回填的净收益优化（离线枚举、无速率上限），(A) 是最小新机制（与 arxiv/openreview 同为纯 httpx）。
- **仓库准实时更新**（勘察 §1：距勘察 1.5h 内有提交）：`git pull` / tree 重取延迟可很低；bulk 导出 `bib.gz` 随站点构建同步再生，可作独立对账源。
- **schema 演进**：`schema.rnc` 社区维护、变更有 PR 史可追；解析失败即 `parse` 并锁上一 good commit（(B) 模式天然支持）。
- **[UNRESOLVED] 清单**（实现期须闭合，勘察已标）：①attachment/SI URL 前缀——**已闭合 [LIVE 2026-07-26]**（§4，HEAD 200 实证，survey §10 归档，Phase 6 §3「机动」预算划支 1）；②`/papers/index.xml` XML feed（勘察 §9 未验证，非主路径，低优先）；③单一 `main` volume 内是否有 `type` 属性区分 long/short（勘察 §8，fixture 期核实——若无则 main=long+short 合并，2241 口径不变）。
- **风险定档**：最低档——官方仓库即权威源、无认证无防护、bulk 单文件路径可审计；主要维护面是两代命名边界与 discover 机制选型，均已定位。

---

## ★ 裁决点清单（§9 裁决记录已全部落定——本节保留为方案论证存档）

1. **AC-2.5 "EMNLP 全量"口径**：推荐 **含 Findings 的 2241**（main+tutorial+demo+industry 于 `2023.emnlp.xml` ＋ `2023.findings.xml` 内 `volume=emnlp` 的 1059，跨文件 join）。"全量"字面 + Findings 体量（近 main 之半）支持纳入；若仅锚主会取 1047。anchor 表逐 volume 已备（§2/§7）。
2. **Issue 建模**：推荐 **一 (venue,year) 一 IssueRef**（`volume=None/number=None/year=int/label=str(year)`），track 入 `PaperStub.meta['track']`——依据 design/06 `paper.meta_json` 显式列 "track"、`UNIQUE(...,label)` 以 label 载年、openreview 先例、AC-2.5"全量"单元=一年、volume 逐年可变不宜作 Issue 键。（备选：逐 volume 一 Issue，换取 `--volume` 细粒度，但 discover 需解析 volume 结构且 track 键随年漂移。）
3. **DOI 去向**：推荐 **方案 A 产 `identifier('doi')`**（本源自持 `10.18653` 前缀、与原生 id 一一对应 = 本 artifact 自身标识，正是 AC-3.1 强合并所需；边界规则区分于 arxiv `journal_ref` 跨源线索）；备选 **B 入 meta**（严守 Phase-2 不产第二 identifier）。AAAI 同题按同边界规则。
4. **discover 机制**：推荐 **(A) api.github.com git-tree 纯 HttpClient**（最小新机制、24h 缓存下 60/hr 非约束）；**(B) shallow-clone** 列为重回填优化。影响 `domains` 是否含 `api.github.com`（(A) 含）。
5. **次要**：`PaperStub.meta['license']` 按年二分产出（NC 边界机器可见）建议采纳；attachment/SI URL、`papers/index.xml`、main 卷 long/short `type` 三项 [UNRESOLVED] 留实现期闭合。

## 12 条前车之鉴自评

1. 增量/游标超签名——✓ ACL 无 watch，discover `since`→年下界、enumerate 重读 bulk 无持久游标；2. 声明协议外能力位——✓ 无 SEARCH 且述理由；3. Issue 幂等键字段分解——✓ §4 逐字段定死（label 载年）；4. identifier 归一——✓ anthology 原样(优先读 `<url>`)、DOI 剥前缀保大小写 + 边界规则；5. 零网络断言矛盾——✓ resolve 真零网络(读 stub)、discover/enumerate 网络路径显式；6. 合法空态误归——✓ 双 legal-empty 行(venue-year 缺 / findings 缺) + 重分类 + 防掩盖 bug 守卫；7. fixture 全 error_class——✓ ⑤–⑪ 覆盖 parse/gone/transient/rate_limited(含 github 403 重分类)/config + legal-empty；8. 外源比对无锚点——✓ D-019 `anchor-emnlp-2023.json` 逐 volume 对 DBLP 人工核准；9. 未 LIVE 验证假设——✓ 全部引勘察 §，未证项标 [UNRESOLVED] + 实现期义务；10. robots/ToU + 限速出处——✓ aclanthology robots 404 实测直写、github bulk 消费姿态(D-014)、§5 表带 source_note；11. 冻结限制承认块——✓ §6 末四点(含 HttpClient 无 HEAD)；12. canary 抗 flake——✓ 3 样本(新/旧/findings) + 规整化 title+track、非纯计数 + 存活基线。

## 9. 主 agent 裁决记录（2026-07-22，正文 ★ 各点就此落定）

| ★ | 裁决 | 理由 |
|---|---|---|
| ★1 AC-2.5 全量口径 | **含 Findings = 2241**（main 1047 + tutorial 6 + demo 52 + industry 77 + findings-of-EMNLP 1059；跨 emnlp.xml/findings.xml 两文件 join） | "EMNLP 全量"的用户语义含正式接收的 Findings；anchor 表逐 volume 呈现拆分，验收判定按总量与分量双口径 |
| ★2 Issue 建模 | **一 (venue,year) 一 IssueRef**（volume/number=None、label=str(year)），track 入 `PaperStub.meta['track']` | 与 aaai ★A 届/年聚合同款；track 是条目属性非期结构 |
| ★3 DOI | **产 `identifier('doi')`**（本源自持 10.18653 前缀） | aaai ★B 通用原则直接适用：本源官方 DOI 产 identifier、他源线索入 meta |
| ★4 discover 机制 | **api.github.com git-tree 经纯 HttpClient**（domains 加 api.github.com，24h 缓存）；shallow-clone 仅列为未来重回填优化备注 | 最小新机制、零新依赖；60/hr 匿名限额在缓存下非约束 |
| ★5 license 线索 | **采纳** `meta['license']` 按 2016 年二分产出（CC BY-NC-SA 3.0 / CC BY 4.0）；三项 [UNRESOLVED]（attachment/index.xml/long-short type）留实现期闭合义务 | NC 边界机器可见是合规增强 |
