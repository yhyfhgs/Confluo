---
title: Feed 族规范与连接器卡片
status: draft
owner: opus5.5-primary
updated: 2026-09-30
---

# Feed 族（`feed`）

本文回答：RSS、Atom、eTOC 与央行 CB-RSS 怎样用一个族引擎接入；哪些 feed 只作新鲜度信号、哪些官方 WP feed 可作元数据主通道；滚动窗口、去重、漏条与 robots 条件怎样处理。结论：族引擎 `feed` 写一次，实例零代码，按 `profile` 选解析器与映射；`role` 只有 `signal` 与 `metadata` 两种，默认 `signal`——信号 feed 只产出标识符，不存、不展示 feed 的标题与描述（08 R15）；按源登记、robots 允许、ToS 无禁止的官方 feed（ECB、BIS 的 WP feed 与 JMLR）才用 `metadata`；Fed 许可已核为公有领域，默认仍为信号，可评审后升级；PMLR 卷级 RSS 是卷索引，由 `pmlr_volumes` 消费。游标用 `guid_set`（沿用 v1 `IdSetDiff`），条目滚出窗口不算删除，两次轮询之间无重叠即判"窗口溢出"，交由替补通道对账。NBER RSS 因 2026-08-01 条款暂停。

## 要点

- 一个连接器 `feed`，17 个来源的实例；央行解析器是 `profile: cb_rss`，不新建连接器（回答第一阶段清单"CB-RSS 是 profile 还是新连接器"）。
- 启用前提三条同时成立：网关 robots 判定允许（对 Atypon 等父路径被禁的站点，要求显式 `Allow` 命中 feed 路径）；ToS 不禁止自动访问；SourceSpec 通道已登记。缺一条即不启用，与通道模式"只降不升"一致。
- 信号 feed 的价值只在"比常规增量早看到 DOI"：DOI 进语料后由 enrich 经 Crossref 单条查询补全；没有 DOI 的信号 feed（Fed、IACR）需要"调度提示"扩展，首批不启用。
- feed 没有游标参数和删除标记：每次取整个窗口，条件请求（`If-None-Match`、`If-Modified-Since`，契约白名单头）省流量；304 是合法空页。
- 窗口小（ECB 16、Fed 16、BIS 25 条），轮询中断几天就会漏：两次轮询无交集时记 `feed_window_overflow`，由替补通道（RePEc、Crossref、`jmlr_volumes`）对账。
- feed 内容多为"保留全部权利"（Nature 频道 `dc:rights` 为 All rights reserved）：fixture 中的描述文本换等长合成文本。

## 1 本族回答什么、适用边界

- **回答**：RSS 1.0（RDF）、RSS 2.0、Atom、PRISM 命名空间与 CB-RSS 的定时轮询；输出信号记录或元数据记录。执行位置 `platform`，后台轮询依策略（[03 九族](../../03-sources-and-corpus-pipeline.md#连接器九族与执行位置)）。
- **与 `crossref_delegated` 的分界**：期刊与多数 WP 系列的元数据主通道是 Crossref；信号 feed 只提前触发同一 DOI 的单条补全，不替代 Crossref 增量（见 [crossref-delegated](crossref-delegated.md)）。
- **与 `site_special` 的分界**：只解析 feed 文档本身。需要再抓卷页、论文页的（PMLR 卷页、JMLR `citation_*`）归 `site_special` 或 `v1_bridge` 的连接器，它们可以复用本族解析器库，但卡片在各自族文档（见 [site-special](site-special.md)、[v1-bridge](v1-bridge.md)）。
- **与 `platform_family` 的分界**：平台族的 `feed_rule(inst)` 给出 Atypon `/action/showFeed` 等 URL 模式与"仅 robots 显式 Allow 的实例启用"规则；实例化与轮询在本族（见 [platform-family](platform-family.md)）。
- **与 `oai_pmh` 的分界**：IACR 的元数据走 OAI（见 [oai-pmh](oai-pmh.md#oai_pmh)），RSS/Atom 只作 latest 信号。
- **不做**：不抓 feed 链接指向的正文或 PDF；不把信号 feed 的标题、描述写进共享层或展示给用户；不用 feed 做回填（feed 没有历史）。

## 2 族专有接口

通用类型以 [contract](../contract.md) 为准，本节只写本族专有部分。

```python
# 设计伪代码 —— feed 族专有部分（通用协议见 ../contract.md；字段名以契约为准）

class FeedFormat(Enum):
    RSS1_RDF = "rss1_rdf"; RSS2 = "rss2"; ATOM = "atom"     # PRISM、dc、cc 命名空间在三者之上按需解析
class FeedProfile(Enum):                  # 封闭枚举；新增 profile = 引擎改动 + 全实例回放
    GENERIC_SIGNAL = "generic_signal"     # 只抽标识符
    JMLR_RSS = "jmlr_rss"                 # 作者串拆分、http→https、pubDate 只有年
    ECB_RSS = "ecb_rss"                   # 按 URL 路径分系列（scpwps / scpdps），WP 号取自 PDF 文件名
    CB_RSS = "cb_rss"                     # BIS 与其他央行：cb:person、cb:keyword、JEL、期号
    VOLUME_INDEX = "volume_index"         # 每个条目是一卷（PMLR feed.xml），供 site_special 消费

@dataclass(frozen=True)
class FeedInstance:                       # registry/instances/feed/<instance>.yaml 的内存形态
    instance_id: str
    source_id: str
    url: str
    format: FeedFormat
    profile: FeedProfile
    role: Literal["signal", "metadata"]   # metadata 须 SourceSpec 登记为官方 WP feed 例外（08 R15）
    id_field: list[str]                   # 主键优先序，如 ["prism:doi", "dc:identifier", "guid", "link"]
    signal_target: Literal["lookup_doi", "bump_increment", "none"] = "lookup_doi"
    robots_allow: Literal["explicit_allow", "not_disallowed", "robots_4xx"]   # 登记时的放行依据，探针盯变化；与契约 AccessDecision.robots_basis 无关
    poll_every: str = "PT6H"              # 每刊每日 ≤4 次（第一阶段调研建议上限）；WP feed 每日 1 次
    window_hint: int | None = None        # 实测条目数；溢出检测与探针用
    on_gap: str | None = None             # 溢出时对账的替补 connector_id（repec_redif、jmlr_volumes、crossref_delegated）

class Feed(PlatformConnector):
    def plan(self, task, ctx) -> Generator[RequestSpec, Step, TaskOutcome]:
        inst = ctx.instance
        cur = task.cursor.cursor if task.cursor else GuidSet.empty()   # guid_set；首轮为空
        step = yield fetch(inst, if_none_match=cur.etag, if_modified_since=cur.last_modified)
        if step.page is None:
            return stop_at_last_safe_point(step)              # 游标不动
        if step.page.signals.legit_empty:                     # 304：只更新 last_poll_at
            return completed(next_cursor=cur.polled(ctx.now))
        keys = {r.source_key for r in step.page.records}
        new = keys - cur.guids                                # IdSetDiff（v1 语义）：新键只用于计数与溢出判定
        overflow = bool(cur.guids) and not (keys & cur.guids)
        return completed(next_cursor=cur.merge(keys, etag=..., last_modified=..., now=ctx.now),
                         reason="feed_window_overflow" if overflow else None)   # new 计入 records 统计

    def parse(self, resp, ctx) -> Page:                      # ParseCtx 不含游标：整窗全部产出，重复由 upsert 吸收
        items = parse_feed(resp.body, ctx.instance.format)    # 禁外部实体；RDF/RSS2/Atom 三套解析器
        if ctx.instance.role == "signal":
            recs = [signal_projection(it) for it in items]    # 只留 {key, doi, url}；标题与描述不进载荷、不进哈希
        else:
            recs = [raw_item(it) for it in items]             # 元数据角色：条目原样入 RawRecord.payload
        return Page(records=recs, next_cursor=None, signals=signals_of(resp, items))
    # 单页任务：commit_page 同事务 upsert（载荷哈希不变即无变化），整窗完成后 runner 写 plan 返回的游标
```

**游标 `guid_set`**：契约字段 `guids`、`window_started_at`、`first_seen_at`（逐键，供淘汰）、`etag`、`last_modified`、`last_poll_at`、`last_window_n`（契约 §6 已收录）。容量上限 `max(4 × window_hint, 500)` 个键，淘汰 `first_seen_at` 超过 180 天的键（设计值）；淘汰只影响溢出判定，重复记录由 `(source_id, source_key)` upsert 与 identify 的 DOI 去重吸收。键规范化：DOI 小写；URL 统一 https、小写主机、去 `utm_*` 参数与尾部斜杠。

**信号记录**：`RawRecord(kind="upsert", channel="latest", payload={key, doi, url})`；normalize 只输出标识符与 `first_seen_at`；SourceSpec 在该通道声明不展示，`classify_rights()` 据此给出不可展示。identify 为新 DOI 建 Work 桩，enrich 经 Crossref `works/{doi}` 单条查询补全；在出现可展示的元数据来源之前，Work 桩不交 percolate（本条需 04/05 认可，见未决事项）。`signal_target = bump_increment`（无 DOI 的 feed）需要在 `TaskOutcome` 上加"调度提示"，属本族对契约的补充提案，确认前这类实例不启用。

## 3 实例与清单字段

**ConnectorInstance**（`registry/instances/feed/<instance>.yaml`）：必填 `instance_id`、`source_id`、`url`、`format`、`profile`、`role`、`id_field`、`robots_allow`、`poll_every`；`role=metadata` 必填 `on_gap` 与 SourceSpec 中的"官方 WP feed 例外"登记；`signal_target=bump_increment` 必填目标 WatchKey 范围。实例只能选 §2 的封闭 `profile`；profile 外的怪癖升级为引擎改动或 `site_special`。

**ConnectorManifest 的本族字段**：每来源一个端点，`endpoint_id` 按契约写 `<source_id>.feed`（如 `ecb_wp.feed`；同源多实例共用，路径 `{instance.base_url}` 取实例 `url`，如 Nature 逐刊、Fed 四个 feed；profile 或 Expectation 不同时才加后缀），`method=GET`、无 `paginator`、`cursor.kind=guid_set`、`request_class=feed`；`hosts_touched` 由实例 URL 主机生成并经 lint 校验；`Expectation`：`content_types ∈ {application/rss+xml, application/rdf+xml, application/atom+xml, application/xml, text/xml}`，`root` 按实例 `format` 取 `rss`、`rdf:RDF` 或 `feed`，`min_bytes = 200`，`empty = error`（零条目按计数骤降处理），`legit_status = [200, 304]`；304 按 HTTP 语义无正文，不做 `min_bytes`、`empty` 检查，parse 产 `legit_empty` 空页（契约 Expectation 未写 304，列入未决）；返回 HTML（如 HighWire RSS 302 到登录页）先过网关挑战检测，否则归 `parse`。`mappers[]`：`feed_signal`、`jmlr_rss`、`ecb_rss`、`cb_rss`，各带 `mapper_version`。

**实例清单**（事实 [URL, 2026-09-30] 实测，除非标"长稿"或"未核"）：

| 实例 | source_id | URL | 格式 · profile | 角色 | 主键 | 窗口 | robots 依据 | 优先级 · 波次 | 证据 |
|---|---|---|---|---|---|---|---|---|---|
| `nature_<code>` | `nature_portfolio` | `https://www.nature.com/{code}.rss`（逐刊） | rss1_rdf · generic_signal | signal | `prism:doi` | Nature 主刊 75 | not_disallowed；频道 All rights reserved | P0 · W1 | [nature.rss](https://www.nature.com/nature.rss)、[robots](https://www.nature.com/robots.txt) |
| `pnas` | `pnas` | `https://www.pnas.org/action/showFeed?type=etoc&feed=rss&jc=pnas` | rss1_rdf · generic_signal | signal | `prism:doi` | 94 | explicit_allow（`Allow: /action/showFeed`） | P0 · W1 | [feed](https://www.pnas.org/action/showFeed?type=etoc&feed=rss&jc=pnas)、[robots](https://www.pnas.org/robots.txt) |
| `biorxiv_<subject>`、`medrxiv_<subject>` | `biorxiv`、`medrxiv` | connect.biorxiv.org 学科 RSS（长稿） | 未核 · generic_signal | signal | DOI（未核） | 未核 | 长稿记 Crawl-delay 10，未复核 | P0 · W1（⚑DRIFT） | 长稿 |
| `jmlr` | `jmlr` | `https://www.jmlr.org/jmlr.xml` | rss2 · jmlr_rss | metadata | `link` | 205 | robots_4xx（404） | P0 · W1 | [jmlr.xml](https://www.jmlr.org/jmlr.xml) |
| `nber_new` 与 19 个学部 feed | `nber_wp` | `https://back.nber.org/rss/new.xml` 等 | 未核 | — | — | 未核 | robots 允许，但 T&C 禁止一切未经许可的自动访问 | P0 · **暂停** | [T&C](https://www.nber.org/terms-and-conditions)、[RSS 页](https://back.nber.org/rss/) |
| `science_<jc>` | `aaas_science` | `https://www.science.org/action/showFeed?...`（jc 未核） | rss1_rdf · generic_signal | signal | `prism:doi`（未核） | 未核 | explicit_allow | P1 · W3 | [robots](https://www.science.org/robots.txt) |
| `siam_<jc>` | `siam` | `https://epubs.siam.org/action/showFeed?...`（jc 未核） | rss1_rdf · generic_signal | signal | 未核 | 未核 | explicit_allow | P1 · W3 | [robots](https://epubs.siam.org/robots.txt) |
| `frontiers_<j>` | `frontiers` | 未核（长稿） | 未核 | signal | 未核 | 未核 | 未核 | P1 · W3 | 长稿 |
| `scipost` | `scipost` | 未核（长稿） | 未核 | signal | 未核 | 未核 | 未核 | P1 · W3 | 长稿 |
| `elife` | `elife` | 未核（长稿） | 未核 | signal | 未核 | 未核 | 未核（⚑ROBOTS 仅指官方 API） | P1 · W3 | 长稿 |
| `iacr` | `iacr_eprint` | RSS/Atom 最新 100 条（长稿） | 未核 | signal（bump_increment） | 未核 | 100（长稿） | robots 注释称元数据经 OAI、RSS、Atom 以 CC0 提供 | metadata-only（P1）· W3（待调度提示扩展） | [robots](https://eprint.iacr.org/robots.txt) |
| `fed_working_papers` | `fed_board_wp` | `https://www.federalreserve.gov/feeds/working_papers.xml`（另 `feds.xml`、`ifdp.xml`、`feds_notes.xml`） | rss2 · generic_signal | signal（可升 metadata，待评审） | `guid` | 16（`feds.xml`） | robots_4xx（404） | P1 · W3（待调度提示扩展） | [feeds 页](https://www.federalreserve.gov/feeds/feeds.htm)、[许可](https://www.federalreserve.gov/disclaimer.htm) |
| `ecb_wp` | `ecb_wp` | `https://www.ecb.europa.eu/rss/wppub.html` | rss2 · ecb_rss | metadata | `guid` → WP 号 | 16 | not_disallowed（Crawl-delay 5） | P1 · W3 | [feed](https://www.ecb.europa.eu/rss/wppub.html) |
| `bis_wp` | `bis_wp` | `https://www.bis.org/doclist/wppubls.rss` | rss1_rdf · cb_rss | metadata | `link` / 期号 | 25 | not_disallowed | P1 · W3 | [feed](https://www.bis.org/doclist/wppubls.rss) |
| `quantum` | `quantum_journal` | 未核 | 未核 | signal | — | — | 未核 | 登记 · CL0，按需补卡 | 长稿 |
| `boe_publications` 等 | `other_cb_wp` | BoE `https://www.bankofengland.co.uk/rss/publications`；NY Fed 无 feed | 未核 · cb_rss（候选） | 待定 | — | — | 未核 | 登记 · CL0，按需补卡 | [BoE RSS](https://www.bankofengland.co.uk/rss) |

**相关 feed（卡片不在本族）**：PMLR 卷级 RSS `https://proceedings.mlr.press/feed.xml`（RSS 2.0，326 个条目，每条一卷；robots 404）[https://proceedings.mlr.press/feed.xml, 2026-09-30]，profile `volume_index`，由 `pmlr_volumes` 消费，可替代长稿"首页卷表 diff + 卷号探测"。**候选信号 feed（不在第一阶段清单，待拍板）**：APS（main 名录写"RSS 仅信号"，长稿记"Personal use only"）、Wiley `/feed/{eissn}/most-recent`（RSS 2.0）[https://onlinelibrary.wiley.com/feed/15406261/most-recent, 2026-09-30]、T&F `/feed/rss/{code}`（RSS 1.0）[https://www.tandfonline.com/feed/rss/uasa20, 2026-09-30]、OUP（Silverchair）`/rss/site_*`（长稿，未复核）；是否放行由 [platform-family](platform-family.md) 的 `feed_rule()` 按 robots 判定；INFORMS 的 `/action` 被 robots 禁，eTOC 不可用。

## 4 族一致性套件

契约通用测试之外（见 [conformance-and-testing](../conformance-and-testing.md)），本族按"实例 × fixture"参数化：

| rule_id | 断言 | 必备 fixture |
|---|---|---|
| `FS-FEED-01` 三种格式 | RSS 1.0 RDF、RSS 2.0、Atom 与 PRISM、dc、cb 命名空间解析一致 | 每 profile 一份原文 |
| `FS-FEED-02` IdSetDiff 恰一次 | 随机轮询时刻、窗口重叠与不重叠混排：每个键在语料中恰好一条记录，新键计数与真值一致；淘汰不造成重复 | 两次相邻轮询 |
| `FS-FEED-03` 窗口溢出 | 前后两次无交集 → `reason = feed_window_overflow`，游标照常推进，告警与对账任务由 runner 发出 | 构造的无交集两轮 |
| `FS-FEED-04` 滚出不是删除 | 条目从窗口消失不产 tombstone | 前后两轮 |
| `FS-FEED-05` 信号投影 | signal 角色的 RawRecord 载荷只含 `{key, doi, url}`；标题、描述、`content:encoded` 不进载荷与哈希 | Nature、PNAS 原文 |
| `FS-FEED-06` 条件请求 | 游标带 ETag/Last-Modified 时发条件头；304 为合法空页，只更新 `last_poll_at` | 304 响应 |
| `FS-FEED-07` robots 依据 | 父路径被禁的实例须 `robots_allow = explicit_allow` 且 robots 快照含对应 `Allow`；否则 lint 失败 | robots 快照 |
| `FS-FEED-08` 映射细节 | JMLR 作者拆分、http→https、年精度日期；ECB 按路径分 WP/DP；BIS 的 JEL 与 `cb:person` | 各 profile 黄金 |
| `FS-FEED-09` 键规范化 | guid 由 http 改 https、带跟踪参数时键不变，不整窗重复产出 | 改写后的同一窗口 |
| `FS-FEED-10` 异常体 | 零条目 → `empty_body/count_drop`；HTML 登录页 → 挑战检测或 `parse` | 空 feed、HTML 体 |

fixture 四类按长稿 §15.1；信号 feed 与未声明开放许可的 WP feed，描述与摘要换等长合成文本；只经 staging 网关录制。

## 5 连接器清单总表

| connector_id | 服务来源数 | 最高优先级 | 波次 | exec_side | impl | 代码量级 | v1 复用 | 前置依赖 | 当前 → 目标 CL |
|---|---:|---|---|---|---|---|---|---|---|
| [`feed`](#feed) | 17（支持 14，其中 Fed、IACR 待调度提示扩展；暂停 1；登记 2） | v2-P0 | W1（P0 实例）/ W3（P1 实例） | platform | `instance`（引擎为族核心代码，profile 映射为代码） | 族核心 1.5 人日（粗估） | v1 `adapters/nber/rss.py`（436 行，v1 唯一实跑的 feed 通道）与 `IdSetDiff` | 契约 SDK（W0） | — → CL3（P0 实例 V1 出口） |

人日为第一阶段清单粗估，未与 v2-drafts 任务卡核对；零代码实例按 SOP C（新来源、已有族）另计来源级复核。复用本族解析器但卡片在他族的：[`pmlr_volumes`](site-special.md#pmlr_volumes)、[`jmlr_volumes`](site-special.md#jmlr_volumes)、[`nber_site`](site-special.md#nber_site)（NBER 全部自动化暂停，平台侧与用户侧都不排波次）。

## 6 连接器卡片

### feed

**1 身份**：`connector_id=feed`；族 `feed`；`contract_version=1`；`connector_version=0.1.0`（草案）；`impl=instance`（实例零代码；`jmlr_rss`、`ecb_rss`、`cb_rss` 三个映射是引擎内代码，按 `mapper_id` 选用）；`lifecycle=active`；CL 当前 —，目标 CL3（P0 实例在 V1 出口，P1 实例随 P1 批次一在 V3 出口，同实施计划）；owner、backup_owner 待指派（P0 两人）；服务来源 17 个（§3 表）；venue 范围：逐刊或逐系列一个实例；波次 W1（`nature_portfolio`、`pnas`、`biorxiv`、`medrxiv`、`jmlr`），W3（P1 实例），`nber_wp` 暂停，登记级不排波次。

**2 通道与操作**：

| Operation | metadata | latest | fulltext | 说明 |
|---|---|---|---|---|
| `increment` | ✓（仅 metadata 角色） | ✓ | — | 每次取整个窗口 |
| `probe` | ✓ | ✓ | — | robots、结构、计数 |
| `locate_fulltext` | — | — | ✓（仅 metadata 角色） | ECB、BIS、JMLR 的 PDF 链接只作外链 |
| `enumerate`、`lookup`、`search`、`snapshot_import` | — | — | — | feed 无历史、无检索；回填由替补通道承担 |

exec_side 全部 `platform`。

**3 上游接口事实**：共性：无游标或 since 参数，只给当前窗口；条目数固定、滚动；无删除与撤稿标记；版权多为保留全部权利 [https://www.nature.com/nature.rss、https://www.pnas.org/action/showFeed?type=etoc&feed=rss&jc=pnas、https://www.tandfonline.com/feed/rss/uasa20, 2026-09-30]。Nature 条目带 `prism:doi`、`dc:identifier`、`dc:date`、`dc:title`、`dc:creator`，响应带 `ETag` 与 `Cache-Control: public, max-age=600` [https://www.nature.com/nature.rss, 2026-09-30]。JMLR：205 条，字段 `title`、`link`（http）、`pdf`、`pubDate`（只有年份）、`author`（逗号拼接）、`description`（摘要），无 DOI [https://www.jmlr.org/jmlr.xml, 2026-09-30]。Fed：4 个官方 feed，`feds.xml` 16 条，`description` 首行为作者、无 DOI；站点声明除另有说明外为公有领域 [https://www.federalreserve.gov/feeds/feeds.htm, https://www.federalreserve.gov/disclaimer.htm, 2026-09-30]。ECB：16 条，`link` 直指 PDF，混有 `scpdps` 讨论稿系列，无作者、无 DOI；robots Crawl-delay 5 [https://www.ecb.europa.eu/rss/wppub.html, 2026-09-30]；转载须 ECB 书面授权（二手，出自银行监管站免责页检索摘要）。BIS：RSS 1.0，含 `dc`、`cb`、`content`、`sy` 命名空间，25 条，含 JEL、`cb:person`、PDF 链接与期号 [https://www.bis.org/doclist/wppubls.rss, 2026-09-30]；转载设许可申请（二手）。Atypon eTOC 只在 robots 显式放行 `/action/showFeed` 的站可用（PNAS、Science、SIAM 实测 Allow；INFORMS 被禁）[https://www.pnas.org/robots.txt, https://www.science.org/robots.txt, https://epubs.siam.org/robots.txt, https://pubsonline.informs.org/robots.txt, 2026-09-30]。NBER：T&C 2026-08-01 禁止未经许可的任何自动访问（含 monitoring）与数据挖掘 [https://www.nber.org/terms-and-conditions, 2026-09-30]。认证：全部无。限速：均未文档化，按 robots `Crawl-delay` 与保守默认。

**4 请求声明**：`endpoint_id = <source_id>.feed`（同源实例共用，URL 取自实例）；`request_class = feed`；令牌桶五元组 `(source, host, feed, 部署身份, 出口 IP)`，同主机多个实例（Nature 逐刊）共用主机桶；轮询间隔 `poll_every`：信号 feed 每刊每日 ≤4 次，WP feed 每日 1 次，同主机实例错峰；条件请求头 `If-None-Match`、`If-Modified-Since`（契约 AllowedHeader 白名单内）；`hosts_touched` 由实例生成；`Expectation` 见 §3；`budget`：$0，`planned_daily` = Σ 实例每日轮询次数（W1 约 100 次量级，设计值）；`personal_params`：无。

**5 游标与增量**：`guid_set`（字段见 §2）；`ordered`、`granularity`、`bounds`：不适用（整窗）；`overlap`：天然整窗重叠；`lag_bound`：未核（feed 更新相对上游发布的延迟）；`late_path = none`；`window_max`：不适用。重启语义：单页任务，失败即游标不动、下次整窗重取，幂等。删除：无；条目滚出窗口不算删除（契约）。完成后推进：`commit_page` 成功后把新键并入 `guids` 并更新 ETag、Last-Modified、`last_poll_at`；两次轮询无交集记 `feed_window_overflow`，runner 按实例 `on_gap` 发替补对账（ECB → `repec_redif` 的 `RePEc:ecb:ecbwps`，JMLR → `jmlr_volumes`，信号 feed → 无需，Crossref 增量已覆盖）。`migrate_cursor`：v1 NBER `IdSetDiff` 状态不迁移（NBER 暂停）；新实例首轮全量产出，由 identify 去重。

**6 映射**：

| mapper_id | 输入 | 关键字段 | 标识符（粒度） | Version | 许可与摘要权利 |
|---|---|---|---|---|---|
| `feed_signal` | 信号投影 | 无标题、无摘要，只 `first_seen_at` | `doi`（作品级）或 `landing_url` | 不给 | 通道声明不展示，`classify_rights()` 计算 |
| `jmlr_rss` | JMLR 条目 | 标题、作者（按逗号与 "and" 拆）、摘要、PDF、年（`date_precision=year`） | `jmlr:<vol>/<id>`（取自 URL，作品级）、`landing_url`（https 规范化） | `vor`（basis：来源性质） | 长稿记 PDF 首页 CC BY 4.0，未复核；由 SourceSpec 与 `classify_rights()` 决定 |
| `ecb_rss` | ECB 条目 | 标题、摘要、PDF、`pubDate`、系列（WP/DP） | `ecb_wp:<号>`（作品级）；DOI 10.2866 在欧盟出版局，不在 Crossref（长稿，未复核），首版不输出 | `wp` | 未知（转载须书面授权，二手）→ 不共享 |
| `cb_rss` | BIS 与其他央行 | 标题、作者（`cb:person`/`dc:creator`）、摘要、JEL、关键词、期号、PDF | `bis_wp:<期号>`（作品级）、`landing_url` | `wp` | 未知（转载须申请，二手）→ 不共享 |

作者、JEL 缺失（ECB）由 enrich 从 RePEc 补。许可、权利、版本字段带 `basis`；`identifiers_emitted = [doi, landing_url, jmlr, ecb_wp, bis_wp]`。

**7 SCD**：无可下推谓词（固定窗口）；无排序、无分页；批量上限不适用；窗口大小作为静态事实写入 manifest（JMLR 205、ECB 16、Fed 16、BIS 25、Nature 主刊 75）；成本：每次轮询 1 个请求，304 几乎零字节。

**8 合规**：策略输入：文档化 API = 官方 feed（是）；bulk 无；robots 逐主机，要求 §3 的 `robots_allow`；ToS：NBER 禁止 → deny；APS 类"Personal use only" → 只可 signal；TDM/AI：Nature、Springer 站点 TDMRep `tdm-reservation: 1` [https://www.nature.com/.well-known/tdmrep.json, 2026-09-30]——信号投影不含正文与摘要，不构成 TDM 输入。08 R15（长稿）：只用 robots 明确允许的 feed（本族解释为 robots 求值允许，含 RFC 9309 的 4xx；父路径被禁时须显式 Allow，见未决），内容只作信号、不展示；例外为 SourceSpec 登记、robots 允许、ToS 无禁止的官方 WP feed（ECB、BIS、JMLR）。模式上限：`increment` = background（⚑ROBOTS 未解除的 `iacr_eprint` 只到 on_demand，HC-31），`locate_fulltext` = link_only，其余 deny（不声明）。闸门：`nature_portfolio` ⚑COMM（范围以 SourceSpec 为准）、`iacr_eprint` ⚑ROBOTS、`elife` ⚑ROBOTS（仅官方 API）、`biorxiv`/`medrxiv` ⚑DRIFT、`nber_wp` ⚑LIC（仅周更文件）加 T&C 暂停。书面确认：NBER（RSS 轮询频率、摘要展示）；ECB、BIS 若要共享摘要须许可。具名 AI 禁令（Nature 点名 ClaudeBot、GPTBot；Science 点名 anthropic-ai、GPTBot）[https://www.nature.com/robots.txt, https://www.science.org/robots.txt, 2026-09-30]：平台 UA 不是具名爬虫，robots 按 `*` 组求值；按 [08](../../08-compliance-security-privacy.md) 这类站点只取元数据、内容不作 LLM 输入，信号投影只含标识符，符合该口径；用途映射待 LQ-17。

**9 全文**：metadata 角色产 `FulltextOption{kind: oa_link, url: PDF 链接, license, basis}`；ECB、BIS 许可未知只外链，不进共享缓存；JMLR 待许可复核后按白名单处理；signal 角色不产全文选项；本族无 `FulltextRecipe`。

**10 测试**：fixture：每实例原文一份（信号 feed 描述换合成文本）、304、空 feed、HTML 登录页、畸形 XML、两轮无交集、guid 改写；黄金 NormRecord：Nature 信号条目、JMLR 条目（作者拆分、年精度）、ECB WP 与 DP 各一、BIS 条目（JEL、`cb:person`）；属性测试：`FS-FEED-02`、`FS-FEED-09`；契约测试 CT-01…CT-12 全过。

**11 探针与替补**：`robots`（每主机日检；Atypon 实例盯 `Allow: /action/showFeed` 是否被删）；`structure`（命名空间集合、`prism:doi` 缺失率、Fed `description` 首行格式、ECB 系列路径）；`count`（每次轮询条目数对 `window_hint`，零条目或骤降 → `empty_body/count_drop`）；`tos_hash`（NBER T&C 的 Last Updated、Fed 免责页、ECB 法律页）；`deprecation`（feed URL 3xx/404）。降级：robots 或 ToS 收紧立即停用该实例；结构失败冻结晋级。替补：信号 feed → Crossref 增量（本来就是主通道）；ECB → RePEc `ecb:ecbwps`（IDEAS 与 RSS 基本同周更新）[https://ideas.repec.org/s/ecb/ecbwps.html, 2026-09-30]；BIS → RePEc（系列句柄未核）；JMLR → `jmlr_volumes` 与 dblp 快照 `journals/jmlr`。

**12 运维**：新鲜度：信号条目出现后 ≤6 小时完成 Crossref 补全（设计值）；WP feed 条目 ≤24 小时入库；SLO：每实例轮询成功率 ≥99%（设计值，未核）；告警：`feed_window_overflow`、计数骤降、robots 变化、403 或挑战；runbook：溢出 → 触发 `on_gap` 对账；guid 格式变化 → 核键规范化；feed 迁址 → 改实例 URL（SOP C 复核）；`review_every`：P0 月看健康、季复核卡片，P1 季；`points`：instance 0.1/实例，profile 映射各 1（未核）。

**13 已知坑与待决**：①NBER：长稿把 back.nber.org RSS 当增量并补 Crossref 缺失的摘要，现按 T&C 暂停，元数据改走 Crossref 10.3386 + RePEc `nbr:nberwo`，影响 `nber_wp` 的 v2-P0 验收口径（待拍板）；②Fed 许可已核为公有领域（长稿"待核"），可评审升 metadata，但作者要从 `description` 首行解析，脆弱，优先 Crossref；③ECB feed 混入讨论稿，WP 号以 PDF 文件名为主键，URL 带哈希不稳定；feed 路径以 `.html` 结尾，Content-Type 未核，录 fixture 时核对，不放宽族 `content_types`；④JMLR `pubDate` 只有年、链接为 http；⑤窗口小，停机数日必漏，靠 `on_gap`；⑥Frontiers、SciPost、eLife、bioRxiv、Science、SIAM 的具体 feed URL 与字段未核，实例 PR 时实测；⑦第一阶段清单指出 6 行仅信号 feed 若首批不接，"需要写"的行数会变，首批范围待拍板。

## 7 本族风险与坑

- **信号被误当内容**：信号 feed 的标题、描述若进入共享层，违反 08 R15 与版权声明 → 解析时就丢弃，fixture 扫描断言。
- **robots 父路径禁止**：Atypon 站 `/action` 被禁、只放行 `/action/showFeed`，放行规则一旦删除必须立即停用 → 实例登记 `explicit_allow` 并由 robots 探针盯住。
- **条款比 robots 更严**：NBER 的 robots 不禁 RSS，但 T&C 禁止自动访问；启用条件必须同时看 ToS。
- **小窗口漏条**：ECB、Fed 各 16 条；轮询中断或上游一次推送过多即漏 → 溢出检测 + 替补对账。
- **键漂移造成整窗重复**：出版商改 guid 形式会让整窗被当成新条目 → 键规范化与 identify 去重双保险。

## 怎么验收

- 族套件 `FS-FEED-01–10` 与契约通用测试离线全过（CL1）；每个 P0 实例四类 fixture 与黄金 NormRecord 齐全。
- 回放 30 天轮询序列（含停机 3 天与 guid 改写）：每键恰好产出一次，溢出全部被检出并触发替补对账。
- 共享层审计：信号实例产出的记录中标题、描述字段为空（全量扫描）；平台出口访问 nber.org 各主机为 0。
- staging 经网关运行 P0 实例 ≥14 天：零 robots 违例、零挑战、零未声明主机。

## 未决事项

- 信号记录的 Work 桩在元数据到达前不交 percolate：需 04 与 05 认可存放与判定位置。
- 304 与 Expectation：条件请求依赖"304 无正文、不做 `min_bytes`/`empty` 检查、parse 产 `legit_empty`"，须写进契约 §3。
- R15"robots 明确允许"本族按求值允许解释（JMLR、Fed 为 robots 404）；JMLR 作 metadata 依赖此解释，须合规评审（G1）确认。
- `TaskOutcome` 的"调度提示"（`bump_increment`、PMLR 新卷触发）是本族对契约的补充提案；确认前 Fed、IACR 的信号实例不启用，PMLR 由 `pmlr_volumes` 自行轮询 `feed.xml`。
- NBER：是否发函 `subs@nber.org` 申请 RSS 与周更文件许可；许可前 `nber_wp` 验收改为"Crossref + RePEc"（已列入 [README](../README.md) 待拍板）。
- Fed feed 是否升为 metadata 角色；ECB、BIS 摘要能否展示须许可或法务结论；ECB DOI 10.2866 是否作为标识符输出。
- 候选信号 feed（APS、Wiley、T&F）与"仅信号 feed 是否计入首批"由矩阵与实施计划定；本批不改名录。
- `other_cb_wp` 合并行是否拆出 BoE（有总 feed）单独成行（第一阶段调研待决）。
- 新标识符方案 `jmlr`、`ecb_wp`、`bis_wp` 须登记进标识符注册表（粒度表），登记前 mapper 不输出（契约 §8"只输出声明"）。

更细的材料：`git show v2-drafts:docs/plan/v2/03-sources-and-corpus-pipeline.md`（§5.3–§5.4、§10.3、§15.1）；08 判定表 R15 见 `git show v2-drafts:docs/plan/v2/08-compliance-security-privacy.md` §4.2；逐源证据见 [支持名录](../../../../catalog/source-directory.md) 与[连接器矩阵](../../../../catalog/connector-matrix.md)。
