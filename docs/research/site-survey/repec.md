---
title: 勘察：RePEc 生态（IDEAS/EconPapers）——角色定位与 adapter 优先级裁决输入
status: approved
owner: fable5
updated: 2026-07-24
---

# 站点勘察 · RePEc 生态（repec.org / ideas.repec.org / econpapers.repec.org）

> **验证元数据**
> - 勘察执行：Phase 5 勘察 agent **R0c（opus）**，2026-07-24。
> - UA 恒为 `PaperCrawler/0.1.0 (personal research; mailto:yhyfhgs@gmail.com)`；curl 逐条串行，同域 ≥2s、第三方 API（crossref/openalex）≥1.5s。
> - **实测请求：13**（本源）；**两源合计 39 / 预算 40**（econsoc 26 + repec 13）。零全文正文下载；零登录零凭证。
> - `[LIVE]` = 2026-07-24 本次直测；`[DOCS]` = 官方文档（getdata/api 页 [LIVE] 取回）转述或既有勘察。
> - **环境障碍说明**：本机网络存在强制代理，对部分 Cloudflare 前置域在 TLS 握手层 reset/协议拒绝（发生在 UA 头发出前）。本文档严格区分：**TLS 层失败＝【环境障碍·未能实测】**（非站点判罚）、**站点 HTTP 403/挑战页＝【站点 BLOCKED】**。`repec.org`（apex）本次 2×TLS-fail（curl35 tlsv1 alert）＝环境障碍；非 CF 对照（api.crossref.org/api.openalex.org）全程可达，故非本机断网。**ideas.repec.org / econpapers.repec.org 均正常 200 可达。**
> - **前置勘察**（本文档增量升级）：[econ-fin-preprints.md §RePEc](econ-fin-preprints.md)（2026-07-20）；对照系：[adapters/aggregators.md](../../design/adapters/aggregators.md)（crossref/dblp=ENUMERATE 主干、openalex/s2=enrich 通道、unpaywall=RESOLVE 的既有分类学）。

## 0. 结论速览（供 controller 范围裁决先读）

**核心裁决（Q2 角色定位）：RePEc 是"分布式书目元数据聚合器"，不是全文源。对本项目的目标 venue（DOI 化的 top 期刊 + NBER/SSRN 专源），RePEc 与既有 crossref/openalex 主干高度重叠——建议 Phase 5 内不建独立 pull adapter，降级为可选 enrich/聚合通道或暂缓。**

| 问题 | 一句结论（[LIVE] 2026-07-24 除注明外） |
|---|---|
| Q1 robots（ideas/econpapers） | 均极宽松：IDEAS `*` 仅禁 `/cgi-bin/`；EconPapers `*` 禁 `/check/ /mirror/ /scripts/ /remilogs/`。无 AI 封禁。PaperCrawler 全可读书目页。 |
| **Q2 角色定位（核心）** | **聚合器，非全文源**。RePEc = 2250+ 机构 archive 各自持 ReDIF 元数据、IDEAS/EconPapers 是同一数据的两个只读前端；条目=元数据+摘要+**链出到源**（NBER 条目 [LIVE] 实测全文链回 nber.org，RePEc 不自托管）。定位 = aggregators.md 谱系里 **openalex/s2 那一档（enrich/补充），而非 crossref/dblp（ENUMERATE 主干）**。 |
| Q3 结构化通道 | **bulk 面齐全**（[LIVE DOCS getdata.html]）：ReDIF / AMF / OAI-PMH（官方自注"sometimes flaky"）/ Rsync / anonymous FTP（各 archive 模板列地址）。**API email-门控**（[LIVE api.html]：邮件 Christian Zimmermann → access code；JSON；getrecentpapers/getpubsfromwpseries 等，无搜索、非批量、可被限流）。CitEc 引文 API 前 500 免 key（[DOCS]）。官方**强烈不建议爬网页**。 |
| Q4 标识符体系 | RePEc handle `RePEc:{archive3}:{series}:{id}`（[LIVE] `RePEc:nbr:nberwo:3210`）。**handle↔DOI 无内建映射**——NBER 条目页 [LIVE] **不显示 DOI**；DOI 关联须外部经 crossref join。handle 是 RePEc 独有主键（crossref/openalex 均不收）。 |
| **Q5 与 openalex/crossref 重叠** | **DOI 化系列高度重叠**：NBER 前缀 10.3386 归 NBER、在 crossref；openalex 亦收（[LIVE] W4323309095，`ids={openalex,doi}`、落地 doi.org、**无 repec 键**）。→ DOI'd 内容经既有主干即得，RePEc 增量≈0。**RePEc 独家增值**：非 DOI 的 WP 长尾 + handle + CitEc 引文 + **JEL 分类**（[LIVE] `nbr:nberwo:35506`→D1/J13/J15；R0b 实测 crossref/openalex/nber.org **三路皆缺 JEL** → RePEc 独家、经济学核心检索维度）+ **wp↔published 版本关联**（[LIVE] `nbr:nberwo:3210`→"Published in" Oxford Economic Papers）。 |
| Q6 兄弟源镜像 | **NBER、CEPR 在 RePEc**（archives 主表 [LIVE] 含 nbr/cpr）；**SSRN 不在**（442KB archives 全表无 "ssrn" 串——SSRN 属 Elsevier 商业源、非 RePEc 志愿网络成员）。→ 经 RePEc 取 NBER/CEPR 书目与直建 NBER adapter **重复**；SSRN 无法经 RePEc 补。 |
| Q7 实施建议 | **Phase 5 不建独立 pull adapter**（主枚举/全文冗余）；但 **JEL 分类 enrich 用例 [LIVE] 成立**（RePEc 独家、经济学核心检索维度）→ 若纳入则定位 enrich 聚合（bulk ReDIF/OAI 补 JEL + 版本关联 + 非 DOI 长尾），**非全文、非目标刊 ENUMERATE 主干；挂 Phase 6 DSL 富化**。 |

## 1. robots / 合规（每域 [LIVE] 2026-07-24）

| 域 | robots | 结论 |
|---|---|---|
| `ideas.repec.org` | 200；`User-agent:* / Disallow: /cgi-bin/`（另社交预览 bot 白名单 twimage.cgi、ByteSpider 禁 twimage） | 极宽松；书目页 `/p/ /a/ /s/ /getdata.html /api.html` 全允许 |
| `econpapers.repec.org` | 200；`*` 禁 `/check/ /mirror/ /scripts/ /scripts/check/ /remilogs/` | 宽松；条目页允许 |
| `repec.org`（apex，**非任务必需**） | **2×TLS-fail**（curl35 tlsv1 alert protocol version）＝**环境障碍·未能实测**（非站点 BLOCKED；对照 crossref/openalex 同期可达） | apex 仅项目主页；数据面在 ideas/econpapers，不受影响 |

- 无 AI-bot 封禁（对比 CEPR/SSRN 的 ClaudeBot/GPTBot 封禁）。官方礼貌要求：getdata 页明言"强烈不建议爬网页、用 bulk（FTP/OAI/Rsync）"；隐私红线"Email addresses are released under no circumstances"。→ 本项目若取用一律走 bulk 面、不爬 HTML。

## 2. 角色定位：聚合器 vs 全文源（Q2 核心）

**判定：分布式书目元数据聚合器（去中心）。**

- **去中心架构** [LIVE DOCS getdata.html]：*"Each publisher holds its RePEc metadata on its web or anonymous ftp server. The addresses are listed in their archive templates."* 2250+ archive（[LIVE] archives 主表约 2250 条 `/s|/i` 链）各自维护 ReDIF；IDEAS 与 EconPapers 是同一聚合数据的两个**只读前端**（非权威源）。
- **不自托管全文** [LIVE]：NBER 条目 `RePEc:nbr:nberwo:3210`（"Endogenous Technological Change"）页面全文 **链回 nber.org**（`mentions nber.org=True`），页内无自托管 PDF；外链仅 CDN/社交 + 相关版本（如 MPRA）。与前置勘察"~89% 链出到源、少数镜像例外"一致。
- **对照 aggregators.md 谱系**：RePEc **不是** crossref/dblp 式的目标刊 ENUMERATE 主干（那需要按 ISSN/会议卷精确、权威、去重的枚举——RePEc 是异构志愿元数据、质量参差、以 handle 非 DOI 为轴）；也**不是**全文 fetcher。最贴近 **openalex/s2 的 enrich 补充档**（按已有 key 富化，不承担主枚举、无 FETCH）。

## 3. 结构化通道盘点（Q3）

| 通道 | 形态 | 门控/条款 | 出处 |
|---|---|---|---|
| ReDIF 模板 | 各 archive 的 web/ftp 上的 ReDIF-{Paper,Article,Series,Archive} 文本记录 | 公开；地址列于 archive 模板 | [LIVE getdata] |
| AMF | 备选元数据格式 | 公开 | [LIVE getdata] |
| **OAI-PMH** | 标准协议收割；官方自注 **"sometimes flaky"** | 公开；**本次未 live 探 endpoint**（避环境 TLS-fail 噪声，见元数据）→ **live 可用性 [PENDING·实现期]** | [LIVE getdata]（endpoint 活性 [DOCS]） |
| Rsync | 增量同步全库 | **需联系**取得 rsync 地址 | [LIVE getdata] |
| anonymous FTP | `ftp.repec.org/opt/ReDIF/RePEc/` 式全库归档 | 公开 | [DOCS 前置勘察] |
| **RePEc API** | JSON；getref/getrecentpapers/getpubsfromwpseries/getauthorshortid | **email 门控**：致信 Christian Zimmermann → 审批 access code；**无搜索、非批量、保留限流权** | [LIVE api.html] |
| CitEc 引文 API | `citec.repec.org/api/{type}/{handle}` XML | 前 500 次免 key | [DOCS 前置勘察] |
| MyIDEAS 搜索 | 仅网页交互检索（非 API） | — | [LIVE api.html] |

- **取用路线（若实施）**：bulk 优先（FTP/Rsync 全库 ReDIF 或 OAI-PMH 收割），**绝不爬 HTML**（官方明禁 + 礼貌）。API 因 email 门控 + 无搜索 + 非批量，仅适作小范围 enrich（如 getpubsfromwpseries 拉某 WP series 近期），不适主收割。

## 4. 标识符体系与 DOI 映射（Q4）

- **handle 形态** [LIVE]：`RePEc:{archive}:{series}:{id}`——`RePEc:nbr:nberwo:3210`（NBER WP）、`RePEc:cpr:ceprdp:{n}`（CEPR DP，[DOCS]）。archive 三字母码（nbr/cpr/…），series 段（nberwo/ceprdp），id 段（序号）。handle 全局唯一、是 RePEc 主键。
- **handle↔DOI 无内建映射** [LIVE]：NBER 条目页**不显示 DOI**（ReDIF `Paper` 模板的 DOI 字段可选、该源未填或未前端化）。而同一 WP 在 crossref 有 DOI `10.3386/w3210`。→ **RePEc handle 与 DOI 是两套独立标识**，互映须外部 join（crossref/openalex 侧）。对本项目 06 数据模型：若纳入，`(repec, handle)` 可作一个 identifier scheme（类比 `(dblp,key)`），但**不是**跨源强合并锚点（DOI 才是）——handle 仅在 RePEc 内唯一，跨源合并仍靠 DOI。
- **wp↔published 版本关联** [LIVE]：IDEAS 条目页含 "Published in:" 段——`nbr:nberwo:3210` 明示已刊于 **Oxford Economic Papers**（链 `/s/oup/oxecpp`）。RePEc 策展的**同一论文 wp↔已刊映射**直接服务 **D-007（preprint↔published）**；crossref/openalex 无此策展关联（各版本独立 DOI——R0b 实测 AEA 订阅版与 NBER wp 版即独立 DOI、靠 D-007 合并引擎非 unpaywall 关联）。

## 5. 与 openalex / crossref 的重叠度（Q5·范围裁决输入）

- **DOI 化系列：高度重叠**。[LIVE] NBER 前缀 `10.3386` 归 "National Bureau of Economic Research"、DOI 在 crossref；同一 WP 在 openalex（`W4323309095`，`ids={openalex,doi}`，落地 `doi.org`）。openalex **不单列 RePEc handle**（无 repec 键、按 DOI 去重）。→ 凡 DOI 化的 RePEc 内容（NBER、有 DOI 的期刊/WP），**经既有 crossref/openalex 主干即全覆盖，RePEc 边际增量≈0**。
- **RePEc 独有增量**（crossref/openalex **未**覆盖或弱覆盖）：① **非 DOI 的 WP 长尾**——2250+ 机构 archive 里大量小型 series 从不铸 DOI，故不在 crossref/openalex；② **handle 标识** + 作者消歧（RePEc Author Service short-ID）；③ **CitEc 引文图**（经济学专门引文）；④ **JEL 分类** [LIVE]——`nbr:nberwo:35506` 携 JEL `D1/J13/J15`（IDEAS `/j/{code}.html` 链）；**R0b 实测同一类 NBER WP 的 JEL 在 crossref(10.3386)/openalex/nber.org 三路皆缺** → **RePEc 是 JEL 的独家来源**，而 JEL 是经济学文献检索核心维度（Phase 6 订阅 DSL 高价值过滤键）。**覆盖偏近年**：`nbr:nberwo:3210`(1989) 无 JEL 仅 NBER 程序码（EFG/ITI/IFM），近年 WP 方有 JEL——历史覆盖率待实现期评估；⑤ **wp↔published 版本关联** [LIVE]（见 §4，服务 D-007）。
- **裁决含义**：本项目 Phase 5 目标 = SSRN/NBER/AEA/Econometric Society 等**高价值、多为 DOI 化或有专源**的对象——这些 RePEc 都与主干重叠或有专门 adapter。RePEc 的独有价值（非 DOI 长尾）**不在本项目当前 T1/T2 venue 清单**内。**故重叠度高、优先级可降**（controller 裁决输入成立）。

## 6. 兄弟源镜像关系（Q6·避免重复建设）

| 源 | 在 RePEc？ | 证据 [LIVE] | 含义 |
|---|---|---|---|
| **NBER** | **是** | archives 主表含 "national bureau"/"nber"；handle `RePEc:nbr:nberwo` | 经 RePEc 取 NBER 书目 = 与直建 `nber` adapter（program RSS + landing，Phase 5 兄弟源）**重复**；NBER 有 DOI 10.3386 更宜直取 |
| **CEPR** | **是** | archives 含 "cepr"/"centre for economic policy"；`RePEc:cpr:ceprdp`（[DOCS]） | CEPR 全文订阅 + robots 禁 ClaudeBot（前置勘察）→ 本就"仅收元数据"；RePEc 是其合规元数据面之一 |
| **SSRN** | **否** | 442KB archives 全表 **无 "ssrn" 串** | SSRN（Elsevier 商业源）**不参与 RePEc**；SSRN 覆盖**只能**靠 `ssrn` 专源（D-011 浏览器自动化），RePEc 补不了 |
| Elsevier 期刊 | 是（作 publisher archive） | archives 含 "elsevier" | 期刊层，与 SSRN 平台无关 |

- **结论**：RePEc 与 NBER/CEPR **重叠**（不应重复建设——NBER 直取、CEPR 仅元数据）；与 SSRN **不重叠且无法替代**（SSRN 必须专源）。→ 进一步削弱 RePEc 作独立 adapter 的必要性。

## 7. 结论：adapter 定位建议 + Phase 5 处置

1. **定位建议**：**聚合/enrich 通道**（aggregators.md 的 openalex/s2 档），**非全文源、非目标刊 ENUMERATE 主干**。**JEL enrich 用例 [LIVE] 成立、且是 RePEc 对本项目的首个具体独家价值**——RePEc 携 JEL 分类（`nbr:nberwo:35506`→D1/J13/J15），而 crossref/openalex/nber.org 三路皆缺（R0b 实测）；JEL 是经济学检索核心维度。若纳入，capabilities 仅 enrich（duck-typed `enrich_batch` + `crawler enrich`，沿 openalex/s2 机制），产 `(repec, handle)` identifier + **JEL 分类 + wp↔published 版本关联 + CitEc 引文**入 meta（补 crossref/openalex 空缺字段，字段级优先级低位、只补不覆盖）；**不声明 ENUMERATE/FETCH**；收割走 bulk（FTP/OAI/Rsync ReDIF），零 HTML 爬取。
2. **Phase 5 处置：不建独立 pull adapter（降级为 enrich 候选）**。理由：① 目标 venue 多 DOI 化、与 crossref/openalex 高度重叠（§5）；② NBER/CEPR 已由专源/元数据面覆盖、重复建设（§6）；③ SSRN 无法经 RePEc 补（§6）；④ RePEc 主枚举/全文价值（非 DOI WP 长尾）**不在当前 tier 清单**。**唯一提升项 = JEL/版本 enrich**（§5④⑤），但那是 **Phase 6 订阅 DSL 的富化输入、非 Phase 5 pull 主流程依赖**。**建议排序：SSRN/NBER 专源优先落地 > RePEc enrich（挂 Phase 6）**。
3. **若未来纳入（触发条件）**：项目 venue 清单扩张到"非 DOI 经济学 WP series 长尾"时，再以 **bulk ReDIF/OAI enrich 通道**实现（预算：一次全库 ReDIF dump + 增量 OAI；实现前 live 复核 OAI endpoint 活性与 FTP 结构）。
4. **须回改/登记**：development-plan Phase 5 `repec` 由"adapter"注记为 **"enrich 通道候选（R0c 勘察：主枚举/全文与 crossref/openalex 高度重叠→降级；独家增值＝JEL 分类 + wp↔published 版本关联，挂 Phase 6 DSL 富化）"**；catalog 若有 repec 行，`role: aggregator-enrich`、`fulltext: none(links out)`、`enrich_fields: [jel, versions, citec]`。

**[UNRESOLVED / PENDING·实现期]**：① OAI-PMH endpoint live 活性与"flaky"程度（本次未探，避环境 TLS-fail 噪声）；② 非 DOI WP 长尾的规模量级（决定未来 enrich 价值）；③ CitEc API live 形态与配额（[DOCS] 未 live 复核）；④ **JEL 分类的历史覆盖率**（[LIVE] 近年 WP 有、1989 无——enrich 价值随年代衰减，实现期抽样评估）。均不阻塞"降级为 enrich 候选"裁决。

## 附. 请求台账（12 次；[LIVE] 2026-07-24；同域 ≥2s / API ≥1.5s）

| # | 方法 | 目标 | 结果 |
|---|---|---|---|
| 1 | GET | ideas.repec.org/robots.txt | 200（* 仅禁 /cgi-bin/） |
| 2 | GET | econpapers.repec.org/robots.txt | 200（* 禁 check/mirror/scripts/remilogs） |
| 3 | GET | repec.org/robots.txt | **TLS-fail**（curl35，环境障碍·未能实测） |
| 4 | GET | ideas.repec.org/getdata.html | 200（ReDIF/AMF/OAI"flaky"/Rsync/FTP + 隐私条款） |
| 5 | GET | ideas.repec.org/api.html | 200（email 门控 access code；getrecent/getpubs；无搜索） |
| 6 | GET | repec.org/robots.txt（retry） | **TLS-fail**（2×确认环境障碍→停手该 host） |
| 7 | GET | api.crossref.org（非 CF 对照连通性） | 响应（400=参数，证可达；连通性正常） |
| 8 | GET | ideas.repec.org/s/nbr/nberwo.html | 200（NBER series 页；item URL 形态 /p/nbr/nberwo/{id}.html） |
| 9 | GET | ideas.repec.org/archives.html | 200（442KB 主表；ssrn 缺席、nbr/cpr 在列） |
| 10 | GET | ideas.repec.org/p/nbr/nberwo/3210.html | 200（handle RePEc:nbr:nberwo:3210；无 DOI；链回 nber.org） |
| 11 | GET | api.crossref.org/prefixes/10.3386 | 200（owner=National Bureau of Economic Research） |
| 12 | GET | api.openalex.org/works/{NBER DOI} | 200（ids={openalex,doi}；无 repec 键；落地 doi.org） |
| 13 | GET | ideas.repec.org/p/nbr/nberwo/35506.html | 200（近年 WP；**JEL D1/J13/J15 [LIVE]**；程序码 CH/POL） |

（另：item 3210(1989) 已取回件复用抽取——[LIVE] 携 "Published in" Oxford Economic Papers 版本关联、仅 NBER 程序码无 JEL；零新请求。未 live 探 oai.repec.org / citec.repec.org：避强制代理对 CF 域 TLS-fail 噪声，且官方 getdata/api 页已 [LIVE] 覆盖通道形态；活性 live 复核留实现期。）
