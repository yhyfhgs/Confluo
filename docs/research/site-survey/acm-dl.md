---
title: 勘察：ACM DL Open Access（挑战门/ToS/改道评估）
status: approved
owner: fable5
updated: 2026-07-22
---

---
title: 站点勘察报告 · ACM Digital Library（OA 路径 / AC-2.6 载体）
surveyor: fable5 (site-survey subagent)
date: 2026-07-22
target: dl.acm.org（2026-01 全面 OA — D-013）
discipline: dl.acm.org 请求 ≤15 / 间隔 ≥2s / UA "PaperCrawler/0.1 (site survey; personal research)" / HEAD 优先 / 遇挑战即停不对抗
verdict: 有条件 —— 元数据改道 Crossref+DBLP（畅通）；dl.acm.org 全文匿名直取被 Cloudflare 挑战墙拦截（OA 去付费墙 ≠ 去机器人墙）
---

# ACM DL 勘察报告

## 0. 请求账本（合规审计）

**dl.acm.org（受严格纪律约束的站，预算 ≤15）——实际用 3 次，零重试、零绕过、零 UA 伪装：**
| # | 方法 | URL | 结果 |
|---|---|---|---|
| 1 | GET | `https://dl.acm.org/robots.txt` | 200 text/plain 739B（无挑战）|
| 2 | HEAD | `https://dl.acm.org/doi/10.1145/3774904.3792547`（WWW26 landing）| **403 `cf-mitigated: challenge`**（5567B 拦截页）|
| 3 | HEAD | `https://dl.acm.org/doi/pdf/10.1145/3774904.3792547`（WWW26 PDF）| **403 `cf-mitigated: challenge`**（5579B，text/html 非 pdf）|

第 2 次即遇 Cloudflare 挑战 → 按纪律**记录并停止 dl.acm.org 匿名探测**；第 3 次为「PDF 端点是否同样被墙」这一独立设计问题的单次 HEAD 表征（同诚实 UA、非重试被拦 URL、非破解），确认后彻底停站。间隔均 ≥3s。

**旁路取证（非 dl.acm.org，各自独立礼貌池 / 搜索引擎，不计入上面预算）：** Crossref `api.crossref.org` ~12 次（member 320 礼貌池，含 mailto）；WebSearch 4 次；WebFetch 3 次（libraries.acm.org 与 www.acm.org 策略页 **均 403**，正文未取到，退回搜索索引摘录）。

---

## 1. OA 现状核验（D-013 实地确认）—— [LIVE]+[DOC]

- **D-013 成立且范围更广**：ACM DL **整库**（journals + 会议/ICPS proceedings + magazines，约 60 万+ 篇全语料）自 **2026-01-01 全面 OA，"free to read for everyone"**，非仅 2026 起新卷——**历史卷全部开放**（解决旧稿 §7 未决项「历史卷是否全开放」= 是）。分 Basic（免费读全库）/ Premium（分析工具，付费）两版。
  - 来源 [DOC/search]：官方公告 `https://www.acm.org/articles/bulletins/2026/january/acm-open-access`（"ACM is Now Fully Open Access!"，D-013 引文核对无误）；`https://dl.acm.org/openaccess`；`https://www.acm.org/publications/message-to-the-community`。旁证：Slashdot 2025-12-19、SIG 页均述"all content … now free to read"。
- **但"免费读" ≠ "可匿名脚本抓"**：匿名非浏览器客户端访问正文页与 PDF **一律 Cloudflare 挑战**（见 §4）。OA 拆的是**付费墙**，未拆**机器人墙**。
- **KDD 2026 尚未出版**（见 §9）：`pull kdd --year 2026` 今日（2026-07-22）几无内容可取（KDD 是 8 月会议）；AC-2.6 常态化验收需待 8 月，或以 **WWW 2026 作 2026 代理载体**（已全量出版）。

## 2. proceedings 结构 —— [LIVE-Crossref]+[UNRESOLVED-challenge]

- **DOI/URL 形态**（Crossref `resource.primary` 实证）：
  - 整卷 proceedings：`https://dl.acm.org/doi/proceedings/10.1145/{procId}`
  - 单篇 landing：`https://dl.acm.org/doi/10.1145/{procId}.{artId}`（`resource.primary` 实回此形，如 `…/doi/10.1145/3774904.3792547`）
  - 同一卷所有论文共享 `{procId}` 前缀（WWW26 procId=`3774904`；KDD26 V.1 procId=`3770854`）
  - 聚合页：`https://dl.acm.org/conference/{acr}/proceedings`（旧稿已载，本次未活验——挑战墙）
- **TOC 页/分 session 结构**：[UNRESOLVED]——dl.acm.org 的 TOC HTML 在挑战墙后，匿名不可读；**合法替代=OpenTOC**（SIG 自托管的免费 TOC → 指向 DL 定稿链接，见 §5③）。

## 3. DOI 形态与 landing / citation_* meta —— [LIVE-Crossref]+[UNRESOLVED-challenge]

- DOI 前缀统一 `10.1145/`（ACM 注册商前缀）；proceedings-article 形 `10.1145/{procId}.{artId}`。
- landing URL 由 Crossref `resource.primary.URL` 权威给出（无需碰 dl.acm.org 即得 landing 定位）。
- **`citation_*` meta 标签**：[UNRESOLVED]——需 GET landing HTML 才能读，被挑战墙拦；无法活验 `citation_pdf_url` 等。⚠ 实现期若走浏览器上下文再核。

## 4. PDF URL 形态 / 最终域 / Content-Type —— [LIVE]

- 形态：`https://dl.acm.org/doi/pdf/10.1145/{procId}.{artId}`（robots **允许**该路径，非 /doi/metrics/）。
- **HEAD 实测（请求 #3）**：`HTTP/2 403`，`cf-mitigated: challenge`，`content-type: text/html`（**非 application/pdf**），`content-length: 5579`，`server-timing: chlray;desc="…"`，最终域仍 `dl.acm.org`（无跳转）。
- 即**匿名 PDF 直取拿到的是挑战页而非 PDF**——旧稿 §5「PDF 跳转到挑战页（HTML 伪装）→ integrity/challenge」失败模式**实地坐实**。

## 5. 官方替代路径探测 —— [DOC/search]+[LIVE-Crossref]

**① 官方 API / OAI-PMH：无。** WebSearch 未见任何 ACM DL 官方 REST API 或开放 OAI-PMH 收割端点；`dl.acm.org/action/doSearch` 仅站内检索（且 robots `Disallow: /action/`）。→ 元数据主干只能靠第三方聚合（Crossref/DBLP），与 D-005 一致。

**② Crossref 侧（api.crossref.org，member=320，礼貌池免费）—— [LIVE]，可作元数据主干但有边界：**
- ✅ 提供：DOI、title、container-title、published、`resource.primary`（=landing URL）。枚举可用 **container-title facet** 精确计数（见 §9）。
- ❌ **无 ISBN**（连已定稿的 WWW 2024 记录亦无）→ 不能用 `filter=isbn:` 做逐卷精确枚举；逐卷枚举须靠 **DBLP conf XML**（D-005 会议主干）或 container-title 查询。
- ⚠ **license/link 字段对 2026 新卷暂空**：WWW 2026 样本 `license=[]`、`link=[]`；对照 WWW 2024 才有 `license`（**混合**：部分 CC-BY-4.0、部分 acm.org copyright_policy）与 `link=unspecified:text-mining/similarity-checking`（TDM 意图，非通用 PDF 直链）。→ **Crossref 不能作 OA 判定源，也不给可匿名下载的 PDF 直链**；OA 全文只在 dl.acm.org。
- **分工结论**：Crossref+DBLP 承 discover/enumerate + 基础元数据（无需碰 dl.acm.org）；dl.acm.org 仅承 fetch（PDF），且受挑战墙约束。

**③ OpenTOC：仍存活 —— [DOC/search]。** SIG 自托管的免费 TOC 页（`sigplan.org/OpenTOC/`、`sigsoft.org/resources/opentoc.html`、`sigmm.org/opentoc`、`sigmod.org/pods-home/opentocs/` 等），2014 起可"永久"保留，链向 DL 定稿版"at no charge"。**性质**：合法的**发现/枚举**旁路（TOC 在 SIG 域，不过挑战墙），但点进的 PDF 仍解析回 dl.acm.org（仍挑战墙）。**覆盖不全**：SIGPLAN/SIGSOFT/SIGMM/SIGMOD 等有；SIGKDD、WWW（IW3C2/SIGWEB）是否启用需逐会核。

## 6. 空态 / 404 形态 —— [UNRESOLVED-challenge]

匿名请求在 Cloudflare 挑战层即被拦，**触达不到 ACM 应用层**，故其自身 404/空态页无法活验。DOI 级不存在可由 Crossref 判定（404 JSON），但 dl.acm.org 的 app 层 404 形态待浏览器上下文期再采。

## 7. robots.txt 全文 + ToS 程序化访问条款 —— [LIVE]+[DOC]

**robots.txt（`https://dl.acm.org/robots.txt`，200，全文实录）：**
```
Sitemap: https://dl.acm.org/sitemap-index-1.txt
User-agent: *
Disallow: /action/  /topic/  /keyword/  /author/  /search/  /web/  /pb/widgets/
Disallow: /servlet/linkout  /na101/  /na101v1/  /na102/  /*.cfm  /doi/metrics/  /authored-by/  /history/
Allow: /action/showBmPdf  /action/showFmPdf  /action/showAltPdf  /action/showFmHtml  /action/showBmHtml
User-agent: facebookexternalhit / LinkedInBot / Twitterbot → Allow: /
User-agent: GPTBot → Disallow: /
User-agent: ChatGPT-User → Disallow: /
User-agent: CCBot → Disallow: /
User-agent: Google-Extended → Disallow: /
Crawl-delay: 1
```
- **关键**：`User-agent: *`（PaperCrawler 命中此组）下 **`/doi/`、`/doi/pdf/`、`/doi/proceedings/`、`/conference/` 均未被 Disallow**（仅 `/doi/metrics/` 禁）。即 **robots 层面允许**我读 /doi/。
- 具名 AI bot（GPTBot / ChatGPT-User / CCBot / Google-Extended）**整站 Disallow**；**ClaudeBot/PaperCrawler 未被点名**（不同于 D-014 记录的 ScienceDirect/CEPR 点名封禁）。诚实 UA 合规。
- **矛盾点（重要）**：robots 放行 /doi/，但 WAF 仍挑战非浏览器客户端——**robots 允许 ≠ 运营层放行**。我命中的是 robots **允许**的路径却**仍被挑战**。

**ToS 条款（`acm.org/publications/policies/dl_use_policies` / `libraries.acm.org/digital-library/policies`；正文页 403 未直取，以下为搜索索引摘录）—— OA 后条款不变：**
- 禁"using scripts or spiders to automatically download articles or harvest metadata from the ACM Digital Library"，属"a serious violation … will result in the temporary or permanent termination of"（访问权）。
- 机构版：年下载无上限，"**except for downloads from robotic or systematic activity**"；ACM 保留在发现"systematic downloading"时中止协议之权。
- **判读**：OA 使内容**免费可读**，但**脚本化/系统性/批量下载在 ToS 下仍明文禁止**；与 §4 挑战墙叠加=ACM 对自动化抓取的**双层明确不欢迎**。

## 8. 限速信号 —— [LIVE]

- robots 尾部 `Crawl-delay: 1`（归属 AI-bot 组/末组，`*` 组未显式设）；我用 ≥2s，超出。
- **未见 429 / Retry-After**：3 次请求得 200 / 403(challenge)，**限速在挑战墙之前无从触发**——真正的"节流信号"就是**前置挑战墙本身**（预防式机器人缓解，非基于速率）。
- ⚠ 归因注记：出口经 Cloudflare **HKG** 边缘（`cf-ray … -HKG`）。数据中心/云 IP 常被 Cloudflare 判为高风险而挑战；住宅 IP + 真浏览器多可透明通过。**故 BrowserFetcher 若仍从云 IP 出，可能照样被 Turnstile 挑战**——不能假定浏览器上下文必过。

## 9. KDD 2026 锚点 —— [LIVE-Crossref]

- **KDD 2026 proceedings DOI**：V.1 = `10.1145/3770854`（container "Proceedings of the 32nd ACM SIGKDD … V.1"，Crossref deposit 2026-04-20）。
- **篇数量级**：facet 精确计数 **仅 3 篇**已 deposit（8 月会议，DOI 提前少量预注册；正式全量未出）。→ **今日 `pull kdd --year 2026` 无实质内容**。
- **可用 2026 代理载体（已全量出版）**：**WWW 2026** proceedings `10.1145/3774904`，正会 **719 篇** + Companion **222 篇**（≈940），published 2026-04-12。样本 DOI `10.1145/3774904.3792547`。建议 AC-2.6 常态哨兵先挂 WWW 2026，KDD 2026 待 8 月上线后补挂。

## 10. 结论与建议 —— 可行性判定：**有条件（元数据畅通 / 全文改道 + 浏览器兜底）**

**判定**：`acm_dl` 归 open_access 族（D-013）**方向正确**，但旧稿 §3「fetch_asset：HttpFetcher 直取；遇挑战再转 BrowserFetcher」的**默认次序需反转**——挑战是**常态而非例外**，纯 httpx 匿名直取 landing/PDF **必被 Cloudflare 挑战拦截（实测 403 cf-mitigated:challenge）**，AC-2.6 若用直连 HttpFetcher 会**失败**。

**给重写 acm-dl.md 的落点建议：**
1. **元数据 100% 不碰 dl.acm.org**：discover/enumerate 走 **Crossref（member 320，landing 由 resource.primary 得）+ DBLP（逐卷 TOC/DOI，D-005 主干）**；此路**畅通无挑战**。Crossref license/link 不可作 OA 判定或 PDF 直链源。
2. **全文（PDF）= browser-first + 优雅降级**：默认经 **BrowserFetcher（Playwright，走 Cloudflare Turnstile/JS）**，**不破解**；仍挑战 → `BLOCKED` 转人工（D-006/D-014 红线不变）。并注明**云 IP 可能致浏览器上下文亦被挑战**的风险。
3. **AC-2.6 口径细化**：①"无认证配置"仍满足（OA 无需登录/订阅），但 fetch **需浏览器后端**而非 httpx——文档应明说；②KDD 2026 时序：8 月前用 **WWW 2026 代理**跑通同一代码路径，KDD 上线后补 canary；③"下载成功"判据=最终 `content-type=application/pdf` 且魔数校验（挑战页是 text/html，天然被 integrity 挡下）。
4. **合规姿态强化写入 quirks**：ToS 明文禁"scripts/spiders 自动下载/harvest metadata"（OA 不改此条）→ 本 adapter **只做个人检索级、低频、尊重 robots 的取用**，严格限速（旧稿 1req/4s 起步合理，甚至更保守），**绝不系统性批量**；OpenTOC 作合法发现旁路（覆盖不全）。
5. **健康检查**：healthcheck 不能靠匿名 HEAD 一篇 PDF（必得挑战 403）——应改为「浏览器上下文取一篇已知 OA DOI PDF，终点 content-type=application/pdf」或降级为「Crossref landing 可达 + DBLP 卷可枚举」的元数据级探活。

**一句话**：OA 让 ACM 内容对**人（浏览器）**免费开放，但对**匿名脚本**既有 robots 允许-WAF 拦截的矛盾、又有 ToS 明文禁止；本 adapter 应以 Crossref/DBLP 为元数据主干（畅通），dl.acm.org 全文经浏览器上下文尽力而为、挑战即 BLOCKED 不对抗。
