---
title: Adapter 设计 · CVF Open Access
status: implemented
owner: fable5
updated: 2026-07-23
---

# Adapter · `cvf`

> 2026-07-22 全文重写：原稿（Phase 0 产物，`updated: 2026-07-20`）多处关键断言被 [LIVE] 勘察证伪——(1) `{CONF}{year}` bare URL 是"按日选择 landing 页"而非论文列表，真正枚举须 `?day=all`；(2) supplemental 文件名**不可**由 html/pdf slug 规则改写（独立短 slug，必须解析条目 `[supp]` 链接）；(3) ECCV2024 实测为标准 **404** 而非旧稿所称 403，且 ECCV 除 2018 一届旧格式镜像外根本不在 CVF；(4) 列表页/menu 是动态 CGI（`proceedings.py`/`menu.py`）而非纯静态。本稿依据勘察实测（22 次站内请求，归档 [research/site-survey/cvf.md](../../research/site-survey/cvf.md)）逐项闭合。**AC-2.4 的验收载体。**

## 1. 定位

- **family**: `open_access`（匿名可读、无认证——见 §2/§4；与 arXiv 同属无凭证级）
- **服务 venue（Phase 2 范围：`cvpr` / `iccv` / `wacv`）**：CVPR（2013→当前，逐年）、ICCV（2013→当前，**仅奇数年**双年制）、WACV（2020→当前，逐年）。均取 CVF Open Access 主会（Main Conference）卷。见 [catalog/cs-ai-conferences.md](../../catalog/cs-ai-conferences.md) §计算机视觉。
- **capabilities**: `DISCOVER | ENUMERATE | RESOLVE | FETCH`（四位；**无 SEARCH**——冻结 `SourceAdapter` 协议无 `search()` 方法、Phase 2 无消费方；venue 内命中经 **enumerate 全集 + 本地过滤**（`Selector.filter_expr`）达成，先例 arxiv.md §1 / openreview.md §1。`--filter` 语义即 AC-2.4）。
- **历史边界（era 分段，D-012）**：CVF 收录 **2013 起**（[LIVE] `/CVPR2012`→404、menu 最早 CVPR/ICCV 2013）；WACV **2020 起**（[LIVE] `/WACV2019`→404）。2013 前的 CVPR/ICCV 只在 IEEE Xplore（订阅），路由到 [`ieee_xplore`](ieee-xplore.md) adapter；本 adapter 不覆盖，`timeline` 呈现的更早年份属其 era。
- **本期不服务**：
  - **ECCV**：勘察证伪旧稿——CVF 上仅 ECCV **2018** 一届（旧格式 `content_ECCV_2018` 扁平列表），ECCV2020 主会链接直指外部 `ecva.net`，2022+ 完全不在 CVF（`/ECCV2024`→**404**）。ECCV 正式版在 Springer LNCS（catalog：`fulltext_source=springer`），CVF 侧不足以支撑一个稳定 era——**本 adapter 不注册 ECCV**（若未来需要 2018 单届 OA 兜底，另立 quirks，不进 Phase 2）。
  - **Workshop 子卷**（`{CONF}{year}_workshops/{code}`）、**Findings**（`CVPR2026_findings`）、**Demos**（`CVPR2022_demos`）等非主会子卷：本期**不注册为 venue**（先例 openreview "Workshop/TinyPapers 独立 venue 本期不注册"）。identifier 方案预留 workshop 命名空间兼容（§3），但 discover 只产出主会届。理由见 §3 与 §8。

## 2. 站点勘察摘要

来源：[research/site-survey/cvf.md](../../research/site-survey/cvf.md)（[LIVE] 2026-07-21 实测，22 次站内请求）。要点：

| 事实 | 值 | 出处 |
|---|---|---|
| 站点 | `openaccess.thecvf.com`（`/`→302 `/menu`）；**PDF/supp 同源直出**（无 CDN/对象存储跳转，单域） | [LIVE] §1/§4 |
| 页面两类 | 列表/menu 页 = **动态 CGI**（`Content-Location: proceedings.py`/`menu.py`/`workshop_menu.py`，无缓存头）；详情页/PDF = **静态文件**（`Last-Modified`/`ETag`/`Accept-Ranges: bytes`） | [LIVE] §2/§3/§8 |
| 届入口两代 | 2021+ 链接无 `.py` 后缀（`/CVPR2023`）；2020 及更早菜单带 `.py`，但 **`.py` 已是兼容重定向**（`/CVPR2013.py`→307→`/CVPR2013`）——统一用无后缀规范形式 | [LIVE] §1 |
| bare `{CONF}{year}` | **不是论文列表**，是"按日选择 landing 页"（仅 3 个 `?day=YYYY-MM-DD` 链接 + 1 个 `?day=all`）——现代年份如此 | [LIVE] §2a |
| 真列表 | `{CONF}{year}?day=all`（现代年份）。CVPR2023 全集 = **2353 篇**（`dt.ptitle`/`papers/*.pdf`/`>pdf</a>` 三法独立计数一致，AC-2.4 锚点）；站点自警 all 页"may be slow" | [LIVE] §2b |
| 早年扁平列表 | 2013 等**无 day 分页**：bare `/CVPR2013`→200 直接是 471 篇列表；条目为**相对路径**、旧目录名 `content_cvpr_2013/papers/...`（小写下划线）、stem 词序 `_2013_CVPR_paper`（现代为 `_CVPR_2023_paper`） | [LIVE] §9 |
| 条目选择器 | 标题/landing：`dt.ptitle > a` → `/content/{CONF}{year}/html/{stem}.html`；**作者非 `<a href>`** 而是逐位 `<form class="authsearch"><input name="query_author" value="{Full Name}">`（取 value 或 `<a>` 文本，二者一致） | [LIVE] §2b |
| PDF 定位 | 条目内 `[pdf]` 直链；**同时**是 html 路径纯函数（`/html/`→`/papers/`，`.html`→`.pdf`）——可改写，但本设计优先直接采集 href（§3） | [LIVE] §2b/§4 |
| supp 定位 | 条目内 `[supp]` 直链；**文件名不可由 slug 规则推导**（例：html slug `Ci_GFPose_Learning_3D_Human_Pose_Prior_With_Gradient_Fields_CVPR_2023_paper` vs supp `Ci_GFPose_Learning_3D_CVPR_2023_supplemental`，独立生成/截断）——**必须解析 `[supp]` href** | [LIVE] §2b/§4 |
| 列表页自带元数据 | 每条目内嵌完整 **BibTeX**（含 `pages`）；有 arXiv 版时内嵌 `[arXiv]` 直链（CVPR2023 覆盖 **1454/2353 = 62%**）；含 `[supp]` 覆盖 **2018/2353 = 86%**——**无需详情页**即得较全元数据 | [LIVE] §2b/§10 |
| 详情页增量价值 | citation_* meta（title/author×N`Last, First`/publication_date=**仅年**/conference_title/firstpage/lastpage/pdf_url）**无 `citation_doi`（CVF 不分配 DOI）/无 `citation_abstract`/无 volume/issue**；"Related Material" 区块与列表页**完全重复**——详情页唯一增量是 `<div id="abstract">` 正文 | [LIVE] §3 |
| workshop 命名空间 | `{CONF}{year}_workshops/{code}` 内容在**独立** `/content/{CONF}{year}**W**/{code}/...` 目录、stem 标记 `_CVPRW_2023_paper`（`CVPRW` 非 `CVPR`）——与主会**非同一路径规则** | [LIVE] §5 |
| 404 单一形态 | 标准 Apache 默认页，`Content-Length: 284` 恒定；不存在年份/会议（含 ICCV 偶数年、未来年、边界外年、`/robots.txt`、`/sitemap.xml`）**一律 404**，**无"空列表 200"形态** | [LIVE] §6 |
| robots / bulk | `/robots.txt`→404（**无任何 robots 指令**：无 Disallow、无 Crawl-delay）；`/sitemap.xml`→404；**无官方 bulk API/dump**——唯一稳定路径是列表页 HTML 解析 | [LIVE] §7/§10 |
| 反爬 | 22 请求全程匿名可读，无 `Set-Cookie`/`WWW-Authenticate`/`cf-*`/验证码；无 `X-RateLimit-*`/`Retry-After`；HEAD 受支持（含动态端点）。定性：**匿名可读、无认证、未见 WAF/挑战信号**（非"无防护"笼统语；限速阈值未压测，见 §4 ⚠） | [LIVE] §8 |
| 版权/勘误 | 页脚：OA 版除水印外同录用版，正式版在 IEEE Xplore；**版权归作者/原权方**（CVF 不主张论文内容版权）。勘误政策：camera-ready 快照不原地改，更正走 arXiv 版 + 邮件 `errata@thecvf.com` | [LIVE] §7 |

**[UNRESOLVED]（勘察未闭合，标 ⚠ 实现期复核）**：① supplemental 是否总为 PDF，还是也有 zip/视频（仅验 1 例）；② 限速阈值具体数值（故意未压测，超个人调研礼貌边界）；③ `_findings`/`_demos` 非常规子卷的内部列表结构是否与主会一致（仅确认 menu 链接存在）；④ 早年（2013）是否存在 html 详情页、抑或条目仅有 PDF 链接（仅采样到 2013 的 PDF href）。

## 3. Issue 字段分解与各阶段实现方案

### 3.0 IssueRef 字段分解（定死）

一个 venue-年 = 一届 = 一条 IssueRef（主会卷）。字段按冻结 `IssueRef(venue_id, volume, number, year, label, pub_date, paper_count_claimed)` 逐一钉死（先例 openreview.md §4 `year=YYYY`/`label='YYYY'`）：

- `venue_id`：venue id（`cvpr`/`iccv`/`wacv`）。
- `volume`：**`None`**（CVF 无卷号概念；详情页亦无 `citation_volume`）。
- `number`：**`None`**（无"期"/子卷号；主会 Main 是唯一被注册轨；workshop/findings/demos 本期不注册，不占用 number）。
- `year`：**`int`（YYYY）**——`--year` selector 过滤的生效字段（AC-2.4 `pull cvpr --year 2023` 靠它圈定），stages 幂等键 `(venue, volume, issue)` 与 `upsert_issue` 的确定性去重由这四列拼法保证。
- `label`：**`'YYYY'`**（极简，对齐 openreview `label='YYYY'`；CLI 展示口径与 canary 一致）。
- `pub_date`：**`None`**（discover 阶段零网络，不打列表页；会议真实日期在 landing 页 `?day=YYYY-MM-DD` 可得，但需网络——本期不回填，避免让 discover 产生网络依赖）。
- `paper_count_claimed`：**`None`**（discover 阶段无权威口径，留空；enumerate 以实际解析数回填——先例 arxiv"留空"）。

### 3.1 discover_timeline —— 零网络，届表来自内置 cadence 规则 + overrides

- **零网络**（先例 arxiv/openreview——discover 不打站点）。追新（新一届）**不在本方法内**，归 `track` 子系统（[design/08](../08-venue-tracking.md) §4：DBLP 新卷 / 官网 / 探测），confirm 后经 venue YAML 落配置。`discover_timeline` 的 `since` 参数：本 adapter 不实现网络增量，`since` 仅用于**下界裁剪**（只产 `year >= since` 的届，若 `since` 给年份），不触发任何探测。
- **届表编码（本 adapter 内置常量 + venue quirks 覆盖）**：CVF 三会的开届节律经勘察直接验证为**规则**（不同于 ICLR 的 2015/2016 不规则缺届），故用 **cadence 规则生成 + overrides 修正**，而非 openreview 式逐年枚举表：
  - 内置 cadence 表（adapter 常量）：`cvpr → (inception=2013, cadence=annual)`、`iccv → (inception=2013, cadence=biennial_odd)`、`wacv → (inception=2020, cadence=annual)`。[LIVE 依据：menu ICCV 2013/15/17/19/21/23/25 全奇数、`/ICCV2022`→404；CVPR 2013→2026 逐年；WACV 最早 2020、`/WACV2019`→404]。
  - venue YAML `quirks.cvf_edition_overrides`（`dict[year → 'include'|'exclude']`，可选）：任何 cadence 无法表达的例外（临时停办/补办/节律变更）由此修正，**不改常量表**（先例 openreview `openreview_group_overrides`）。
  - 生成区间：`inception → 当前年`（不产未来届）。ICCV 偶数年由 cadence 天然不产；不存在的年份即使误产也会在 enumerate 阶段整页 404（见 §5）。
- **裁决（主 agent 定，2026-07-22）**：采 **cadence 规则 + overrides**——节律系会议本质（ICCV 双年制由会议章程决定）且经 LIVE 直证，逐年显式表冗余；"ICCV 恒双年、无跳届/补届"作为维护假设显式登记（§7 + canary 每年抽验），节律突变由 overrides 兜底（与 openreview 逐年表的差异根源：ICLR 有不规则缺届、CVF 无）。

### 3.2 enumerate_issue —— 双形态解析器 + 列表页一次拿全 + meta 中转

- **入口探测（按解析结果分支，不按年份硬编 era）**（免疫前车之鉴 #9"勿臆断"）：
  1. `GET {CONF}{year}`（bare，规范无后缀形式）。
  2. 若响应含 `dt.ptitle` 条目（**早年扁平列表**，如 2013）→ 直接解析，**1 请求**完成。
  3. 若是"按日 landing 页"（有 `?day=all` 链接、无 `dt.ptitle`）→ 再 `GET {CONF}{year}?day=all` 解析（**2 请求**）。
  - 不假设 `?day=all` 对早年可用（勘察未测），改用**解析特征判分支**，对边界年漂移稳健。venue quirks 可声明 `list_mode: flat|day_all` 作为逃生覆盖（默认自动探测）。
- **单条目解析（选择器级，[LIVE] §2b）**：
  - `title` = `dt.ptitle > a` 文本；`landing href` = 其 `@href`。
  - `authors` = 该条目内所有 `input[name=query_author]` 的 `value`（元组顺序即页面顺序）。
  - `[pdf]`/`[supp]`/`[arXiv]` 三类 `<a href>` 分别取（后二者可缺）。
  - **URL 绝对化**：早年相对路径（`content_cvpr_2013/...`）用 `urljoin(列表页 URL, href)` 归一为绝对 URL；现代已是绝对路径。所有落 meta 的 URL 均为绝对形态（消除 era 差异，见 3.3）。
- **identifier 归一（定死）**（免疫前车之鉴 #4）：
  - `scheme` = **`cvf`**（design/06 §identifier 已预注册该 scheme——line 84 开放枚举含 `cvf`）。
  - `value` = **`f"{canonical_dir}/{stem}"`**，其中：
    - `canonical_dir` = 规范大写形式 `{CONF}{year}`（主会，如 `CVPR2023`）/ `{CONF}{year}W/{code}`（workshop 命名空间预留）——**由 enumerate 上下文已知的 venue+year 构造，不解析**；
    - `stem` = PDF href 的 basename 去 `.pdf`（如 `Ci_GFPose_Learning_3D_Human_Pose_Prior_With_Gradient_Fields_CVPR_2023_paper`）——**取自 `[pdf]` href**（两代都有 pdf 链接：现代 2353、2013 有 471；不依赖 html 详情页是否存在）。
  - **大小写原样保留**（不做 `lower()`/`upper()`——`canonical_dir` 用站点惯用大写 `CVPR`，`stem` 为站点侧生成的规范 slug，原样即规范；显式断言此点而非留白，先例 openreview/pmlr-B2）。
  - 示例：`cvf` : `CVPR2023/Ci_GFPose_Learning_3D_Human_Pose_Prior_With_Gradient_Fields_CVPR_2023_paper`。
  - **裁决（主 agent 定，2026-07-22）**：采**候选 A** `{canonical_dir}/{stem}`——`(scheme,value)` 全局唯一、可直接反查 landing、workshop-ready。否决 B（裸 stem 无法重建 workshop 路径）与 C（BibTeX key `{首作者姓}_{年}_{会}` 同姓同年碰撞，非唯一）。
- **元数据映射与 meta 中转（resolve 零网络的前提，先例 arxiv/openreview meta 通道；直击 pmlr-B3）**：`PaperStub` 除 `title`/`identifiers`/`year=issue.year`/`authors` 外，弹性字段 `meta`（tuple-of-tuples）写入：
  - `pdf_url`：绝对化 `[pdf]` href（resolve 据此建 kind=pdf plan）；
  - `supp_url`：绝对化 `[supp]` href（**仅在条目有 `[supp]` 时**；resolve 据此建 kind=si plan）；
  - `landing_url`：绝对化 landing href（records/UI，可选）；
  - `arxiv`：`[arXiv]` href/id（**meta 线索，不产 identifier**——防跨源早合并，Phase 3 ingest 依 D-007 建 `preprint_of` 边；先例 arxiv R3 / openreview）；
  - `pages`（可选）：从内嵌 BibTeX 解析（列表页已含，零额外请求）——低优先，enrichment。
  - `abstract` = **`None`**：列表页不含 abstract（仅详情页 `<div id="abstract">` 有）；**本期不逐篇抓详情页**（CVPR2023 逐篇 = 2353 额外请求，违背克制体量）。abstract 回填（详情页取）**deferred**，不阻塞 AC-2.4——AC-2.4 的 `--filter` 是对 enumerate 全集本地过滤的**自洽不变式**，与是否含 abstract 无关（过滤字段 = title + 可用 meta，与 arxiv 同口径）。
- `paper_count_claimed`：以解析出的条目数回填 IssueRef（供 §6 完整性对账）。
- **空态判定**：见 §5——CVF **无"200 空列表"合法态**（不存在即 404），故 200 页解析出 0 条 = `parse`（结构漂移），此为正确归类（勘察实证，非遗漏）。

### 3.3 resolve_assets —— 纯读 meta、零网络

- **零网络**（免疫前车之鉴 #5"零网络断言与实际网络路径矛盾"）：`resolve_assets(venue, paper, session)` 只读 `paper.meta`，不发任何请求：
  - `meta['pdf_url']` → `AssetPlan(kind=pdf, url=<pdf_url>, expected_type='application/pdf', url_strategy=direct, auth_needed=none, version=None)`。
  - `meta['supp_url']` 存在 → `AssetPlan(kind=si, url=<supp_url>, expected_type=<按扩展名推断>, url_strategy=direct, auth_needed=none)`；**不存在则不产 si plan**（正常非错误——14% 条目无 supp）。
  - `expected_type` 推断：supp 扩展名 `.pdf`→`application/pdf`、`.zip`→`application/zip`、`.mp4`→`video/mp4`，未知 → `application/octet-stream`（⚠ 勘察仅验 1 例 PDF supp，非 PDF 形态实现期复核；pipeline 的 `%PDF` 魔数校验只对 kind=pdf 生效，kind=si 任意类型放行）。
- **为何读 meta 而非规则改写**（设计裁决，直击 pmlr-B3 与旧稿缺陷）：
  1. **supp 文件名不可推导**（[LIVE] §2b/§4）——必须用采集的 `[supp]` href，规则改写会产错 URL。
  2. **PDF 虽可规则改写，仍优先采集 href**：(a) 与 supp 统一；(b) **消除 era 分支**——早年（`content_cvpr_2013/...` 相对、小写目录、stem 词序不同）与现代路径规则不同，若 resolve 靠规则改写需按 era 双套正则；采集 href（enumerate 已绝对化）则 resolve 对两代同一段代码。PDF 路径改写规则仅保留为 **T1 交叉校验断言**（验证采集 href 与规则改写一致），非运行时来源。
- **网络成本口径**：discover 0 请求 + enumerate 1–2 请求/届（列表页）+ resolve **0 请求** + fetch 每资产 1 请求（真实下载）。§4"一届≈1–2 元数据请求"由此成立。

### 3.4 fetch_asset —— HttpClient 流式直取

- 经共享 `HttpClient.stream(url)` 取流交 `FetchIO.write_stream`（冻结分工）；PDF/supp 均同源直出、`Accept-Ranges: bytes`。
- **`%PDF` 魔数权威校验在 pipeline**（冻结分工）；adapter 职责限于对异常响应判 error_class（个别 asset 404→`gone`，见 §5）。kind=si 非 PDF 形态不做魔数校验（pipeline 分工）。

### 3.5 healthcheck —— 匿名、轻量

- `GET {最近一届 CVPR}?day=all` 的**首个** `dt.ptitle` 条目解析成功，或退化为 `GET /menu` 断言 200 且含 `CVPR <当前年>` 锚点。断言 200 + 结构可解析。匿名可用（无 token 依赖）。canary 具体样本见 §6。

## 4. 限速与礼貌

| domain | 速率 | 依据 |
|---|---|---|
| openaccess.thecvf.com | **1 req/2s（30 rpm），并发 1** | NFR-4 无声明站点保守默认（[LIVE] §7 robots 404 = 无 Crawl-delay 声明、§8 无 `X-RateLimit-*`）；站点为社区公益托管，克制体量 |

- **单域**：PDF/supp [LIVE] 同源直出（无 CDN 跨域），`domains = ("openaccess.thecvf.com",)`——`[0]` 即主域（对比 pmlr 双域教训：本站无此问题，已实测确认）。
- `default_rate.source_note` 引勘察 §7/§8 与 NFR-4；UA 按 D-014（`PaperCrawler/<ver> (personal research; mailto:<email>)`，由 HttpClient 调用方注入，本 adapter 不读 config）。
- **robots 合规（实测结论，非"待复核"）**：`/robots.txt`→**404**，站点**未发布任何 robots 指令**——无 Disallow 路径可循、无 Crawl-delay。故合规姿态 = **无站点声明可参照，纯礼貌自律**：诚实 UA + 上表保守限速 + 不压测阈值（D-014 默认保守；AGENTS §6 对无声明站仍取保守默认）。**批量枚举走 `?day=all` 一次拿全**（而非逐日/逐篇高频小请求）以最小化请求数。
- **版权/ToU 姿态（[LIVE] §7）**：CVF 明示论文版权归作者/原权方、CVF 不主张内容版权；OA 版为 camera-ready 快照。本 adapter 仅下载公开 OA 副本供个人检索，不做再分发/训练用途（D-014）。**未见任何 ToU 禁止程序化访问的条款**（无 robots、无 API ToS）；勘误渠道 `errata@thecvf.com` 记录备查（非本 adapter 行为）。
- ⚠ **实现期复核义务（T5 首次在线冒烟）**：以克制节奏（≤上表速率）实跑若干请求，确认无隐藏限速/质询（勘察仅 22 请求、未压测）；若发现 429/挑战信号，立即下调速率并记 decision-log（AC-0.5 红线优先）。

## 5. 失败模式映射

| 站点现象 | error_class | 说明 |
|---|---|---|
| bare `{CONF}{year}` 整页 404（届不存在：未来年 / 未上线 / ICCV 偶数年 / 边界外） | `gone` | HttpClient 404→GONE。语义 = 该届无数据；cadence 规则前置已避免产 ICCV 偶数年，此路径主要兜底"cadence 内但尚未上线的当前年届"→交 `track` 候选复核（D-012）。`Content-Length==284` 为 Apache 默认 404 佐证信号（[LIVE] §6），但判定以 status 为准 |
| 单条目 pdf/supp href fetch 404（个别 asset 缺失/下架） | `gone` | 对该 asset 标 gone；不牵连整届。区别于上一行的"整页 404" |
| 200 页但 `dt.ptitle` 解析出 **0 条** / 选择器失配 / 双形态探测失败 | `parse` | canary 标红。**CVF 无"200 空列表"合法态**（[LIVE] §6：不存在即 404，从未见空 200）——故 0 条即结构漂移，归 parse **是正确归类，非把合法空态误判为错误**（前车之鉴 #6 的反向情形：此站确无合法空态，已据实证据确认）。⚠ 若未来观测到"当前年届上传中的空 200"新形态，再评估补合法空态行 |
| 列表页 HTML 结构漂移（`.py` 渲染变更 / 作者 form 结构变 / day 分页形态变） | `parse` | 同上；quirks `list_mode` 可临时覆盖分支；canary 跨年+跨 era 抽验早发现 |
| 超时 / 连接错 | `transient` | HttpClient 统一映射（重试表 4 次 2/8/30s） |
| 429 / 503+Retry-After | `rate_limited` | HttpClient 统一（本站未主动暴露限速头，30rpm 自限下罕见；⚠ §4 复核） |
| 其余 5xx | `transient` | HttpClient 统一 |
| 其余 4xx（400/405…） | `config` | HttpClient 兜底（请求构造缺陷，响亮停机转 BLOCKED） |

- **无 auth 相关行**（`auth_expired`/`challenge`/`no_entitlement`）：站点匿名可读、无认证、未见挑战门（[LIVE] §8）——故本 adapter 不产生这三类，与 openreview（free_account）对比明确。`integrity` 由 pipeline 魔数校验产生，非 adapter 职责。
- **404 双语义已拆分**（前车之鉴对应项）：整届 404（届不存在，可能是 track 候选）vs 单 asset 404（个别缺失）——上表前两行分列，消费方按调用阶段（enumerate 整页 vs fetch 单资产）自然区分。

**已知冻结限制（本期承认，收紧随 Phase 4 走接口仲裁——arxiv.md §5 / openreview.md §6 同批先例）**：①`FetchResult` 无 `http_status` 字段，`fetch_log.http_status` 本期恒 NULL；②metadata 阶段请求（enumerate 列表页 GET）**不入 FetchLog**——其限速审计证据为 obslog jsonl（HttpClient 每请求 debug 事件：domain/url 脱敏/status/elapsed_ms）；③`Retry-After` 仅观测（写 `CrawlerError.detail`）不驱动重试调度。

### 网络层需求（Phase 2 共享 `HttpClient`）

缓冲 GET→文本（列表页 HTML 解析输入）；流式 GET→`Iterator[bytes]`（喂 `FetchIO.write_stream`）；3xx 跟随（`.py`→无后缀的 307 兼容重定向）+ obslog 事件；UA 注入；超时/连接错→`transient`；状态码→ErrorClass 映射（404→gone 等）。**属 adapter 自身职责**：HTML 解析（`dt.ptitle`/作者 form/`[pdf]`/`[supp]`/`[arXiv]`）、双形态（flat/day_all）分支、URL 绝对化、identifier 构造、cadence 届表生成。**不归 adapter**：限速（pipeline `acquire_and_wait` 依 `default_rate`）、`%PDF` 校验（pipeline）、落盘（FetchIO）。

## 6. Fixtures 与测试

- **T1 单元**（与网络解耦，bytes 进 / 中间记录出）：
  - identifier 构造/归一矩阵（现代 stem `_CVPR_2023_paper` × 早年 stem `_2013_CVPR_paper` × workshop `_CVPRW_2023_paper` × 大小写保留 × 非法/缺 pdf href 拒绝）；
  - PDF 路径改写规则 **交叉校验**（规则改写结果 == 采集 href，Unicode 作者名 slug）；
  - cadence 届表生成边界（CVPR 逐年、ICCV 奇数年、WACV 2020 起点、overrides 合并优先级、`since` 下界裁剪）；
  - 双形态解析器（`day_all` 列表 vs flat 早年列表 vs day-landing 页三态判分支）；作者 form 提取；URL 绝对化（相对→绝对）；meta 线索（arxiv/supp_url/pdf_url）提取。
- **T3 fixture 全 error_class 落点**（覆盖 §5 全部 error_class，test-plan §6 强制；难录形态合成并标注"合成 fixture"；参照 arxiv.md 八件套模式）：
  1. **现代 `?day=all` 列表页正常节选**（≥3 条：含 pdf+supp+arXiv+BibTeX 全齐 1 条、有 pdf 无 supp 1 条、有 pdf 无 arXiv 1 条）——主 parse fixture；
  2. **早年（2013）flat 列表页节选**（相对路径、旧目录名、stem 词序不同）——双 era 解析器覆盖；
  3. **day-landing 页**（bare `{CONF}{year}`：仅 day 链接 + `?day=all`，无 `dt.ptitle`）——触发"再取 `?day=all`"分支；
  4. **详情页**（单篇 html：citation_* meta + `<div id="abstract">`）——三件套"正常详情页"+ 未来 abstract 回填路径 T1；
  5. **对 1/2 的期望解析 golden**（PaperStub 列表：identifiers/authors/meta）；
  6. **404 页**（Apache 默认，`Content-Length: 284`）→ `gone`；
  7. **200 但 `dt.ptitle` 缺失/结构漂移页**（合成）→ `parse`；
  8. **429 含/不含 ratelimit 头**（合成——站点不暴露）→ `rate_limited`；
  9. **5xx 响应**（合成）→ `transient`；
  10. **400/405 响应**（合成）→ `config`。
- **T4 集成（MockTransport 全链路）**：discover→enumerate→resolve→fetch。断言：cadence 届列表正确（**测试注入固定"当前年"**——cadence 生成依赖时钟，D-019/T4 断言须钉死注入年保证确定性，复审 A 增补 2026-07-22）；双 era 解析计数；resolve 零网络（无 MockTransport 命中）产出 pdf(+si) plan；有/无 supp 两路。
- **AC-2.4 验收机制（D-018 证据分层 + D-019 锚点）**：
  - **离线层（T4，CI 化，机制正确性）**：以 fixture 现代列表页跑 `pull cvpr --year 2023 --filter "diffusion"` 全链——断言 (a) 全集 enumerate 数 == fixture 条目数；(b) **过滤命中数 == 对全集本地 `filter_expr` 过滤数**（AC-2.4 自洽不变式）；(c) 下载子集 == 过滤子集、每个 `%PDF` 魔数过、DB↔文件对账一致。
  - **在线层（T5 限量冒烟，真实解析入库）**：预算 `MAX_REAL_REQUESTS ≤ 6`——healthcheck 1 + `CVPR2023?day=all` 实拉 1（一次得全集，验真实计数对锚点）+ `--filter` 后 `--limit 2` 下载 2 PDF。**在线只跑限量子集**（全量 diffusion 命中过多，靠 `--limit` 封顶）。
  - **D-019 锚点快照**：`tests/fixtures/cvf/dblp-cvf-anchor.json`——逐 (venue, year) `{venue, year, paper_count_claimed, dblp_slug, note}`；**人工对照 DBLP TOC**（`dblp.org/db/conf/cvpr/cvpr2023.html`）核准（UPDATE_GOLDEN 纪律、records 留痕）。种子行：CVPR2023 = **2353**（[LIVE] 三法计数）。**D-019 人工 DBLP 核准已闭合 [LIVE 2026-07-23]**：实测 `class="entry inproceedings"` 计数 = 2353，与站内三法计数**精确匹配**（无 front matter/口径差异；另测得 3 条 `entry withdrawn` 撤稿记录，DBLP 单列不计入主计数）；核准出处见 fixture 该行 `note`/`dblp_toc_count`/`dblp_cross_check`。其余 27 届仍 `PENDING_DBLP_CROSSCHECK`（`count_status` 表级仍为 `PARTIAL_SEED`，未变）。**enumerate 完整性判定 = `?day=all` 全集数 == anchor 表**（"与 DBLP ±0"经人工核准的 anchor 传递，勘察 2353 为量级锚点）。
- **canary 样本（抗 flake，arxiv/openreview 先例）**：**3 个跨年+跨 era 固定样本**——CVPR2023（现代 day_all）、某 ICCV 奇数年（如 ICCV2021，验双年制路由）、CVPR2013（**flat 早年**，验双形态解析器不退化）；每样本比对**空白规整化 title + 第二稳定字段**（首作者 `query_author` 或 identifier stem），**不做原串精确匹配**（避免折行/微调误报 DRIFT）；另附 1 条计数锚点（`CVPR2023?day=all` 条目数 == 2353，容 `note` 记录的口径差）。
- **T6 runbook**：无（AC-2.4 为一次性验收，无 7 日类场景）。
- **验收关联**：AC-2.4；测试类型定义见 [testing/test-plan.md](../../testing/test-plan.md)。

## 7. 风险与维护

- **cadence 届表假设**：ICCV 恒双年（奇数）、CVPR/WACV 无跳届——若节律突变（某年停办/改制），cadence 会误产/漏产届；对策：`quirks.cvf_edition_overrides` 修正 + 每年 canary 抽验 + `track` 追新交叉验证（[design/08](../08-venue-tracking.md)）。
- **双代路径规则**：早年（≤2013 观测）相对路径/旧目录/stem 词序 vs 现代绝对路径——本设计以"采集 href + 解析特征判分支"抹平，但早年是否有 html 详情页、`?day=all` 是否早年可用等属 **[UNRESOLVED] ④**（§2），实现期需补录 2013 fixture 确认；若早年更早期（若未来纳入）出现第三代格式，加解析分支 + fixture。
- **动态 CGI 渲染漂移**：列表页是 `proceedings.py` 动态渲染，HTML 结构变更（作者 form、day 分页、`.py` 后缀策略）会致 `parse`——canary 跨 era 抽验早发现；quirks `list_mode` 逃生。
- **非常规子卷扩张**：`_findings`（CVPR2026）/`_demos`（CVPR2022）等 CVF 新增子卷本期排除（§1）；若未来纳入，需确认其列表结构（[UNRESOLVED] ③）并按 workshop 命名空间模式扩 identifier/discover。
- **workshop 纳入路径（未来）**：identifier value 已预留 `{CONF}{year}W/{code}/{stem}` 形态；纳入时 discover 增产 workshop 子卷 Issue（`number` 或 `label` 携 workshop code）、resolve 复用 meta 中转（workshop 页同 `proceedings.py` 渲染，[LIVE] §5）——路径规则差异（`W` 目录、`_CVPRW_` stem）由采集 href 天然吸收。
- **supp 非 PDF 形态**（[UNRESOLVED] ①）：实现期抽样确认 zip/mp4 等；`expected_type` 按扩展名推断已预留，pipeline 魔数校验仅约束 kind=pdf。
- **限速阈值未知**（[UNRESOLVED] ②）：保守默认 1 req/2s；T5 复核；若站点未来引入 Cloudflare/WAF（当前无 [LIVE] §8），canary 会以 403/挑战暴露 → 停用并升 decision-log。
- **DOI 缺失是设计前提非缺陷**：CVF 版无 DOI（[LIVE] §3），identifier 用 `cvf` slug scheme；正式版 DOI 归 IEEE Xplore，跨源合并（cvf slug ↔ IEEE DOI ↔ arXiv）由 Phase 3 ingest 依 D-007 处理（arxiv 线索已入 meta）。
