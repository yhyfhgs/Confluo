---
title: Confluo Scout 来源与爬虫
status: draft
owner: opus5.5-primary
updated: 2026-11-19
---

# Confluo Scout 来源与爬虫

> 本篇回答：venue 列表怎么维护、每个平台从哪里取什么、爬虫怎样做到稳。上游事实注明核实日期；没写日期的是设计取值。总览见 [README.md](README.md)。

## 要点

- **venue 列表分两层**：`scout/registry/venues.yaml` 记录会议与期刊系列的静态知识（平台、届表、评级）；届次运行态在 SQLite 的 `edition` 表里，由各平台的发现器自动补齐，"来源"页可以逐届开关。
- **一个平台一个适配器**：OpenReview、CVF Open Access（含 AcceptedPapers 标签）、ECVA、ACL Anthology、PMLR、AAAI OJS、IJCAI。同一篇论文在多个来源出现时，按"届次 + 规范化标题"合并。
- **公共抓取层**：robots 检查、按主机限速（含每小时预算）、带抖动的指数退避、熔断、挑战页识别、原始响应缓存、断点续爬、结构校验。适配器只写"请求什么、怎么解析"。
- **默认范围**：2024–2027 年的 ICLR、NeurIPS、ICML、CVPR、ICCV、ECCV、ACL、EMNLP、NAACL、AAAI、IJCAI、COLM、CoRL 开启；更早年份、TMLR、AISTATS、UAI、COLT、WACV 登记在列表里，默认关闭。

## venue 列表

`venues.yaml` 每个系列一项，示例（设计伪代码，字段以实现为准）：

```yaml
- id: iclr
  name: International Conference on Learning Representations
  short: ICLR
  kind: conference
  area: ml
  ratings: [CCF-A, ICORE-A*]
  sources:
    - adapter: openreview
      group: "ICLR.cc/{year}/Conference"
      overrides: {2017: "ICLR.cc/2017/conference", 2018: ..., 2019: ...}
  default_years: [2024, 2025, 2026, 2027]
```

- **发现**：OpenReview 读 `venues` 组（2026-11-19 共 4,937 个 id）并按系列前缀匹配新届次；CVF 读 `/menu`；PMLR 读卷级 `feed.xml`；ACL 读 GitHub `data/xml` 目录；AAAI 读期次存档页；IJCAI 探测年页；ECVA 读 `papers.php` 的届次分组。
- **阶段**：`in_review` 表示审稿分可见、尚无决定，每天刷新；`decided` 表示已有决定、未出正式论文集，每周刷新；`published` 表示正式论文集已上线，每 30 天对账一次。阶段由数据推断：有 Decision 帖即 `decided`，正式论文集出现即 `published`。
- **开关**：关闭的届次不排程、不参与检索，数据保留；重新开启后即可检索。

## 平台与适配器

| 适配器 | 覆盖 | 取得 | 通道与事实（核实 2026-11-19） | 节奏 |
|---|---|---|---|---|
| `openreview` | ICLR、NeurIPS（主会与 D&B / E&D 轨）、ICML、COLM、CoRL、TMLR，及 CVPR 2026 元数据 | 标题、作者、关键词、`primary_area`、摘要、TL;DR、录用标签、状态、审稿分与置信度、forum 与 PDF 链接 | API v2 `api2.openreview.net`；匿名 `/notes` 返回 403 `ChallengeRequiredError`；登录后 `ratelimit-policy: 500;w=3600`。`/notes?content.venueid=<group>` 取录用论文，`invitation=<group>/-/Submission` 取全部投稿。`details=replies` 时每页 100 篇约 7 MB、8–14 s；不带 replies 时每页 1,000 篇。返回不含 `count`，翻到不满页为止。2023 年及以前的届次在 API v1 `api.openreview.net` | 每小时 ≤400 次；单线程 |
| `cvf` | CVPR、ICCV、WACV | 标题、作者、摘要、PDF 与 HTML 链接 | `openaccess.thecvf.com` 无 robots（404）；`/{CONF}{year}?day=all` 单页列全届（CVPR 2025 共 2,871 篇，8.4 MB）；论文页有 `<div id="abstract">` 与 `citation_*` | 间隔 1.5 s |
| `cvf_accepted` | CVPR、ICCV 的录用等级 | Highlight 标记 | `cvpr.thecvf.com/Conferences/{year}/AcceptedPapers`，robots 允许；每行 `<strong>` 是标题，`<img title="Highlight">` 是标记（CVPR 2025 共 388 篇，ICCV 2025 共 263 篇）；页面不标 Oral，所以这两个会议只区分 Highlight 与 Poster；CVPR 2026 页面 404 | 每届 1 次 |
| `ecva` | ECCV | 标题、作者、PDF、DOI、摘要 | `www.ecva.net/papers.php` 单页（3.6 MB），包含 ECCV 2018–2024，还没有 2026；robots 只对 Googlebot 写了规则；摘要在逐篇 `.php` 页 | 间隔 2 s |
| `acl` | ACL、EMNLP、NAACL、EACL、COLING、Findings、TACL | 标题、作者、摘要、卷别（long、short、findings、industry、demo）、PDF 与 Anthology 链接 | GitHub `acl-org/acl-anthology` 的 `data/xml/{year}.{event}.xml`（2025.acl.xml 共 1,966 篇，篇篇有摘要）；aclanthology.org 无 robots；2016 年起 CC BY 4.0 | 每文件 1 次 |
| `pmlr` | ICML 论文集、COLT、AISTATS、UAI、CoRL | 标题、作者、摘要、正式版与 PDF 链接 | 每卷 `assets/bib/bibliography.bib` 带 `abstract` 字段（v267 约 7 MB，下载 >60 s）；卷级 `feed.xml`；无 robots | 每卷 1 次 |
| `aaai` | AAAI | 标题、作者、摘要、技术分轨（OAI set 名作领域）、链接 | OAI-PMH `ojs.aaai.org/index.php/AAAI/oai`，`ListRecords` 每页 100 条，按 `dc:source` 的卷号归届；robots 只禁 `/cache/`；`from` 按修改时间过滤，且部分页稳定返回 HTTP 500（2026-03-14 当天的记录），所以按月窗口收割，失败窗口对半拆分，拆到单日仍失败就改用 `ListIdentifiers` 加逐条 `GetRecord` | 间隔 2 s |
| `ijcai` | IJCAI | 标题、作者、DOI、PDF、分轨与领域（年页 section、subsection），摘要与关键词 | 年页 `/proceedings/{year}/`（2025 年约 1,280 篇）；每篇的 URL 加 `.json` 返回含摘要的元数据（`/llms.txt` 声明），HTML 详情页作备用；robots 现在只禁 `/wp-admin/` 并写明欢迎爬虫，9 月记录的 `Crawl-delay: 10` 已撤 | 间隔 2 s |

补充说明：

- **NeurIPS 与 ICML 的正式论文集**（proceedings.neurips.cc、PMLR）只用来补正式版链接，论文主体来自 OpenReview。
- **CVPR 2025、ICCV 2025、ECCV、WACV、AAAI、ACL、IJCAI、KDD** 的录用论文在 OpenReview 上不公开（2026-11-19 按 `content.venueid` 查询，返回 0 篇），所以走各自的官方站点。
- **不使用的通道**：会议官网 virtual 站点的 JSON 在 `/static` 下，被 robots 禁止；Paper Copilot 等第三方汇总站不作数据源；Google Scholar 不做自动化。

## OpenReview 细节

- **登录**：`POST /login` 换取 token，请求头写 `Authorization: Bearer`（v1 适配器用 Cookie 头、把 403 当成登录过期，这两点都已作废）。401 时重新登录一次；403 挑战时停用该主机 24 小时。
- **届表**：沿用 v1 的 ICLR 届表（2013、2014、2017 年的 group 是小写 `conference`，2015、2016 年没有主会），以及 2018、2019 年的录用判定规则。其他系列按模板 `<Series>/{year}/Conference` 生成，可在 YAML 里覆盖。
- **录用标签**：从 `content.venue` 解析，规则不区分大小写。实测写法有 `ICLR 2026 Oral`、`ICLR 2026 Poster`、`NeurIPS 2026 spotlight`、`ICML 2026 regular`、`ICML 2026 spotlight`、`CoRL 2025 Oral`、`COLM 2026`。
	- 等级映射：oral → 4；spotlight 与 highlight → 3；poster、regular、accept → 2。
	- 状态由 `venueid` 后缀判定：`/Rejected_Submission` 为 rejected，`/Withdrawn_Submission` 为 withdrawn，`/Desk_Rejected_Submission` 为 desk_rejected，`/Submission` 为 under_review。
- **审稿字段**：只取 `/-/Official_Review` 帖。不同届次的字段名不同：
	- ICLR 2026：`rating`、`confidence`、`soundness`、`presentation`、`contribution`；
	- ICLR 2027：`rating`、`confidence`、`soundness`、`presentation`、`informativeness`；
	- NeurIPS 2025/2026：`rating`、`confidence`、`quality`、`clarity`、`significance`、`originality`；
	- ICML 2025：只有 `overall_recommendation`；
	- ICML 2026：`overall_recommendation`、`confidence`、`soundness`、`presentation`、`significance`、`originality`；
	- COLM：`rating`、`confidence`。
	- 解析规则：总分依次取 `rating`、`overall_recommendation`、`recommendation`、`overall_assessment`、`score` 中第一个存在的字段；值可能是整数，也可能是 `"6: marginally above..."` 这样的字符串，取开头的数字。同一审稿人改分时，取最新版本。
- **范围**：已决定的届次只取录用论文；在审届次（目前是 ICLR 2027）取全部活跃投稿，排除 withdrawn 和 desk_rejected；被拒论文默认不取，可在 YAML 中打开。
- **预算**：ICLR 2027 约 2–3 万篇投稿，带 replies 约 250 次请求；默认范围首轮全量约 700 次，在每小时 400 次的预算下约 2 小时完成。在审届次每天刷新一次。

## 公共抓取层

- **robots**：每个主机缓存 24 小时；robots 为 4xx 视为不限制，为 5xx 或网络错误视为全部禁止（RFC 9309）；Crawl-delay 作为最小间隔的下限。
- **限速**：按主机设最小间隔（见上表）与并发 1；OpenReview 另加滑动窗口预算（每小时 400 次），并读取 `ratelimit-remaining` 响应头动态收紧。
- **重试**：只对网络错误、超时、429、5xx 重试，每个请求最多 4 次，间隔指数退避加抖动；有 `Retry-After` 时按它等待。
- **熔断**：同一主机连续失败达到阈值后暂停 15 分钟。阈值默认 5 次；AAAI 的 OAI 主机设为 30 次，因为适配器会有意试探失败窗口。挑战页（403 JSON 挑战，或 200 但正文含 `cf-chl`、"Just a moment"）直接冷却 24 小时，不重试、不换 UA。熔断与挑战会让本次抓取立即中止、保留断点，而不是被当作普通失败去拆分窗口或跳过记录。
- **配额**：上游响应头显示剩余额度 ≤1 时，按 `ratelimit-reset` 暂缓发送，不报错；登录接口有自己的小额度，它的响应头不参与主机节奏。
- **缓存**：原始响应 gzip 存放在 `cache/http/<host>/<sha1>.gz`，同时记录 ETag 与 Last-Modified，用于条件请求和离线重解析。
- **断点**：每个"届次 × 来源"在 `crawl_cursor` 里记录游标（OpenReview 记 offset，列表页记已完成的条目集合）；每页数据与游标在同一事务里提交，崩溃后从断点续爬。
- **结构校验**：每个解析器声明必需字段和最小条目数；整页命中率 <90%，或条目数比上次少 20% 以上，就判为结构漂移：本次结果不入库，任务标红，届次保留旧数据。
- **合并**：同一届次内，先按来源键找已有论文，找不到再按规范化标题（小写，只保留字母和数字）找。合并时字段取优先级最高的来源：审稿分与录用标签以 OpenReview 为准；正式版链接以论文集为准；摘要选最长的非空版本。
- **摘要落盘**：抓取时新增或变化的摘要先写 `abstract_pending` 表；届次抓完后压实，把旧分片与待写摘要一起重写成新一代分片（每片 ≤2,000 条），写完 `manifest.json` 再原子切换，最后删除旧代。

## 调度

- 后台调度线程每 5 分钟检查一次到期的届次，到期间隔按阶段决定（见 venue 列表一节）；每个平台族一个工作线程，不同主机可以并行，同一主机串行。
- 抓取完成后依次触发：摘要压实、FTS 更新、嵌入、概念词表增量更新。
- "来源"页可以手动"立即抓取"；失败按指数退避重新排期（1 小时、4 小时、24 小时），连续失败 3 次的届次标为"需关注"。

## 怎么验收

- 每个解析器都有正常、空页、错误、边界四类 fixture（截短的真实页面），离线全部通过。
- 每个适配器真实抓取一届，计数与官方录用数的偏差 ≤2%；标题、作者、链接、摘要的完整率 ≥95%（IJCAI 的摘要在慢补完成后再计）。
- 人为制造 429、超时和挑战页时，重试、熔断和停用行为符合本篇规则。
- 运行中杀掉进程，重启后从断点续爬，不产生重复论文。
