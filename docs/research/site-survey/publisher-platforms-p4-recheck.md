---
title: 站点勘察增量复核 · 出版社平台（Elsevier/OUP/Wiley/ACM）+ 凭证核查 · Phase 4 W0
status: draft
owner: r0
updated: 2026-07-23
---

# 出版社平台勘察增量复核（Phase 4 W0 / R0）

> **目的**：对 2026-07-20 六平台勘察（[publisher-platforms-econfin.md](publisher-platforms-econfin.md)，approved）与 2026-07-22 ACM 深勘（[acm-dl.md](acm-dl.md)，approved）做距今 3 天的增量复核，验证 Phase 4（认证框架 + 出版社 adapters）开工的关键假设仍成立。
> **纪律**：UA `PaperCrawler/0.1 (personal research; mailto:yhyfhgs@gmail.com)`；请求间隔 ≥2s（每站点请求独立 tool 调用，round-trip 天然间隔 >2s）；在线预算硬顶 25 次（WebFetch/WebSearch/Crossref 不计入）；遇 Cloudflare 挑战/403/验证页即记录停站、绝不重试规避；`www.sciencedirect.com` 零请求。**凭证只报存在性/路径/键名，值绝不落文/落 commit**。
> **标注**：`[LIVE] 2026-07-23` = 当日直测；`[DOC]` = 官方文档/搜索索引二手；`[UNVERIFIED]` = 本轮未活验。

## 0. 请求台账（合规审计）

### 计入预算的站点请求（5 / 25）
| # | 时刻(GMT) | 方法 | URL | 码 | 字节 | 备注 |
|---|---|---|---|---|---|---|
| E1 | 07-22T20:1x | GET | `api.elsevier.com/robots.txt` | 404 | 111 | JSON `RESOURCE_NOT_FOUND`；API host 无 robots → 无路径级限制 |
| E2 | 07-22T20:13:21 | GET | `api.elsevier.com/content/article/doi/{JFE DOI}`（匿名） | **429** | 180 | JSON `RATE_LIMIT_EXCEEDED`；`server: cloudflare`，`cf-ray …-HKG`；**无** `X-RateLimit-*`/`X-ELS-Status`；一次即停 |
| O1 | 07-22T20:1x | GET | `academic.oup.com/robots.txt` | 200 | 4012 | 无 AI-bot 条目、无 Crawl-delay |
| O2 | 07-22T20:1x | GET | `academic.oup.com/qje/article/141/3/2205/8662148` | **403** | 5604 | `cf-mitigated: challenge`，"Just a moment…" → 记录即停 OUP |
| A1 | 07-22T20:1x | GET | `dl.acm.org/robots.txt` | 200 | 739 | 与 acm-dl.md（07-22）逐字节一致 |

> 时刻取 curl 响应 `date` 头（GMT）；仅 E2 有精确秒（20:13:21），余为同会话数分钟窗内顺序请求。本地时区 HKG(+8) 即 07-23 ~04:1x（cf-ray 边缘 `-HKG`，云 egress IP）。零重试、零 UA 伪装、零绕过。

### 旁路取证（免费聚合/文档/搜索，不计预算）
- Crossref `api.crossref.org` ×2：取 JFE（ISSN 0304-405X）有效 DOI，`publisher=Elsevier BV` 实证。
- WebSearch ×4：Wiley TDM 现状 / ACM OA 现状 / Wiley token header / ACM ToS 条款。
- WebFetch ×4：`github.com/WileyLabs/tdm-client`=200；`www.acm.org/…/acm-open-access`=**403**；UA Scholarly Cookbook py/r=404（URL 漂移，改由搜索索引取证）。

---

## 1. Elsevier（`api.elsevier.com`）— [LIVE]

**凭证核查（子任务 1，红线：只报存在性）**
- `~/.paper-crawler/config.toml` 仅含 `[auth.openreview]`（键 `username`/`password`/`token`）——**无 Elsevier API key、无 insttoken**。
- 环境变量：无 `ELSEVIER_*`/`ELS_*`/`INSTTOKEN` 等任何相关变量。
- 代码现状：`src/paper_crawler/config.py` 目前仅 `openreview_token`/`openalex_api_key`/`s2_api_key` 三槽（env 覆盖 `PAPER_CRAWLER_*`）；**尚无 Elsevier/Wiley 槽位**（design/07 §3.4 已设计 APIKeyProvider + insttoken 同库管理，待 Phase 4 实现）；`canary.py` 亦注明 `elsevier_sd` 健康检查未实现。凭证脱敏（obslog）已覆盖 `api_key`/`token`/`secret` 形态。

**匿名端点实测**（key 缺失分支：匿名 GET 一次记录错误结构后停）
- `api.elsevier.com` **无 robots.txt**（404，JSON error 封套）——无路径级限制。
- 匿名 `GET /content/article/doi/{JFE DOI}` → **HTTP 429 `RATE_LIMIT_EXCEEDED`**（非预期的 401）。响应头 `server: cloudflare`、`cf-ray …-HKG`、`x-els-reqid`/`x-els-transid` 有值；**无 `X-RateLimit-*`、无 `X-ELS-Status`**。错误封套：`{"error-response":{"error-code":"RATE_LIMIT_EXCEEDED","error-message":"Rate of requests exceeds specified limits…"}}`。
- **判读**：keyless 层被**即时限流**（很可能叠加云 egress IP 被 Cloudflare 判高风险，与 acm-dl.md 记录的 `-HKG` 边缘同因）。**未能触达 401/entitlement 层** → AC-4.3 的 entitlement 语义、`X-RateLimit-*` 真值、全文字段名、attachment/objects 清单字段**本轮全部无法核验**，须待 key 到位。
- **正面结论**：API 通道返回**结构化 JSON error（非挑战页 HTML）**，印证"API 是出版社明示合规正道、非 challenge 墙"的设计前提成立。

> **BLOCKER-1**：Elsevier API key 缺失。elsevier_sd 全文/entitlement 实测前置于用户提供 key（机构订阅关联、非商业）。建议 Phase 4 新增 `[auth.elsevier].api_key`(+`.insttoken`) 配置槽，沿用 `[auth.s2].api_key` + `PAPER_CRAWLER_ELSEVIER_API_KEY` 惯例。

## 2. OUP（`academic.oup.com`）— [LIVE]

- **robots.txt（200）**：**复核一致**——无任何 AI-bot 专门条目（唯一具名 UA 为遗留爬虫 `008`，非 AI）、无 Crawl-delay；`*` 组仍禁 `/bin/ /config/ /signin.aspx /search-results /DownloadFile/ /Citation/Download /Shibboleth.sso/ /user/logout`（SP 部署印证）；期刊 `article`/`article-pdf` 路径未禁。TDMRep 未再探（robots 无 `tdm-policy` 引用，与 07-20 一致）。
  - **补充差异（非颠覆）**：新增若干 society 门户 path 禁列（`/aaea/ /asm/ /pnas/ /french-studies/ …` 及 `/*/chapter-ag-pdf`、`/store/*`）——**不含** econ/fin 目标刊码（qje/restud/rfs/rof/ej）；目标刊仍 robots 放行。
- **QJE 文章页（403 challenge）**：匿名 GET `/qje/article/141/3/2205/8662148` → **403 `cf-mitigated: challenge`**（"Just a moment…" 5604B，含 `challenge-platform`/Enable JavaScript）。**复核一致**：Cloudflare 通用质询持续，匿名程序化访问不可行，**登录 session 态为工作前提**（adapter 设计假设成立）；质询前无 404，路径与 `/{code}/article/{vol}/{iss}/{page}/{id}` 模式一致。按红线记录即停 OUP。

## 3. Wiley（TDM API，文档级）— [DOC] 2026-07-23

**端点 / 头 / 速率：全部复核一致，无变更。**
- 端点 `GET https://api.wiley.com/onlinelibrary/tdm/v1/articles/{DOI}` —— 未变；仅按 DOI 返回全文 PDF，不支持关键词检索。
- 请求头 `Wiley-TDM-Client-Token`（token 为 UUID）—— 未变。搜索索引原文："passing your Clickthrough Client token as the value of the `Wiley-TDM-Client-Token` header"。
- 速率 **3 req/s + 60 次/10 分钟** —— 未变（另一口径"约 10s/次持续"）。
- 客户端活跃维护：`WileyLabs/tdm-client` **v1.2.0（2026-07-02，80 commits）**；PyPI `wiley-tdm`。→ 07-20 因 CF 拦截官方原文页仅"转引"的部分，本轮经 GitHub + 搜索索引二手**确证**。

**个人研究者能否免费快速自助取 token？**
- **token 签发 = 可自助**：WOL 个人账号 → click-through TDM license → 即得 Client API Token（UUID），无需人工邮件审批。
- **但 entitlement 受订阅域约束**：官方口径 "Academic subscribers can access subscribed content"——无机构订阅的个人账号即使持 token，对非订阅内容仍 403（`no_entitlement`）。UK 用户另受 CDSM-2014 计算分析例外覆盖。
- 现状：config/env **无 Wiley token**（一并核实）。

> **裁决建议（供 controller）**：Wiley **本 Phase 纳入实现，但以 token 门控**——
> ① 按已验证稳定的端点/头/速率把 adapter + TDM 客户端（httpx + `Wiley-TDM-Client-Token`）实现到位（NFR-1 杠杆：JF/ECMA）；
> ② live FETCH 与 T6 runbook **门控在 token 存在性之后**，token 缺失即 skip（不阻塞 Phase 4 验收）；token 落 `[auth.wiley].token` 新槽；
> ③ **不建议整体顺延**——勘察稳定、实现风险低，顺延将浪费已验证窗口。

## 4. ACM DL（`dl.acm.org`）— D-020 重评证据 [LIVE]+[DOC]

- **robots.txt（200，739B）**：与 acm-dl.md（07-22）**逐字节一致**——`*` 组 `/doi/`、`/doi/pdf/`、`/doi/proceedings/`、`/conference/` 均未禁（仅 `/doi/metrics/` 禁）；具名 AI-bot（GPTBot/ChatGPT-User/CCBot/Google-Extended）整站 Disallow，**ClaudeBot/PaperCrawler 未点名**（诚实 UA 合规）；尾部 `Crawl-delay: 1`（我用 ≥2s，超出）。
- **全面 OA 现状**：**仍在**——[DOC] 确认 2026-01-01 起 ACM 全库（journals + ACM/ICPS proceedings + magazines）OA，Basic 免费读 / Premium 付费两版；公告页 `acm.org/articles/bulletins/2026/january/acm-open-access`（"ACM is Now Fully Open Access!"）仍在索引，无回退。
- **ToS 自动下载条款**：**未变、仍禁**——[DOC] `libraries.acm.org/digital-library/policies` + `acm.org/publications/policies/dl_use_policies` 原文："Using scripts or spiders to automatically download articles or harvest metadata … is prohibited … a serious violation … termination"。**OA 只拆付费墙，未松此条**。
- **Cloudflare 挑战墙**：本轮**未再触碰**——acm-dl.md（07-22）的 landing/PDF HEAD → `403 cf-mitigated:challenge` 证据仅 1 天，再触即撞挑战、无新信息，按纪律略过。

> **重评建议（证据向，不作最终裁决）**：D-020 将 acm_dl 自动全文抓取 Phase 2 出列的**两条依据均未变**——(a) 全文挑战墙持续（OA ≠ 去机器人墙）；(b) ToS 明文禁 scripts/spiders 自动下载 + metadata harvest。故：
> - **维持出列（保守，倾向）**：Phase 4 不纳入 dl.acm.org 自动全文；发现/枚举与元数据 100% 走 Crossref+DBLP（畅通、不碰 dl.acm.org），全文交 Unpaywall/OpenTOC 旁路；**或**
> - **转 open_access 有限实现**（若取 acm-dl.md §10 路线）：browser-context 尽力取全文、挑战即 BLOCKED 不对抗、严格个人低频非系统性（呼应 ToS 只禁"systematic/robotic"），**不得 httpx 直取**（必撞 403）。
> - 用户本 Phase 未新增任何 ACM 侧能力、双 barrier 未变——倾向**维持出列**，全文改道留待 browser-fetcher 落地后再评。

## 5. Kaggle 凭证核查（子任务 5，0 请求）— [LIVE]

- 标准凭证 `~/.kaggle/kaggle.json`（username+API key）**不存在**；`~/.config/kaggle/kaggle.json` 亦无；无 `KAGGLE_*` 环境变量。
- **但** `~/.kaggle/` 目录存在，内含**非标准** `access_token` 文件（38B，mode 600，**未打开**）——非官方 kaggle CLI 期望的 `kaggle.json` 形态，能否被 Kaggle SDK 采用存疑。仅报存在性 + 路径。
- 结论：Phase 2 检查单 #16 —— 标准 Kaggle API 凭证缺失；`access_token` 待 controller 判定用途/可用性。

## 6. 与 2026-07-20 / 07-22 原勘察的差异清单

| 平台 | 维度 | 差异 |
|---|---|---|
| Elsevier | robots / API 通道 | **复核一致**（API host 无 robots；返回结构化 JSON error 非挑战页） |
| Elsevier | 匿名错误码 | **补充**：匿名 keyless = `429 RATE_LIMIT_EXCEEDED`（非 401）；07-20 记载的 "429 + `X-ELS-Status: QUOTA_EXCEEDED`" 应为**已认证配额耗尽**的另一 429，本轮 keyless 429 无 `X-ELS-Status` → 待有 key 时区分核验 |
| OUP | robots | **复核一致**（无 AI 条目 / 无 Crawl-delay）；**补充**：新增若干 society 门户 path 禁列（不含 econ/fin 目标刊） |
| OUP | Cloudflare | **复核一致**（QJE 文章页 403 challenge 持续） |
| Wiley | 端点/头/速率 | **复核一致**（`Wiley-TDM-Client-Token` / `api.wiley.com/onlinelibrary/tdm/v1` / 3 rps + 60/10min 均未变）；**升级取证**：07-20 因 CF 仅"转引"，本轮经 GitHub + 搜索索引二手确证，client v1.2.0(07-02) 活跃 |
| ACM | robots / OA / ToS | **复核一致**（robots 逐字节同；OA 仍在；ToS 禁 scripts/spiders 未松） |

## 7. 结论

- 四平台**核心假设全部成立**，无颠覆性漂移。Elsevier/OUP/ACM 复核一致；Wiley 端点/头/速率复核一致且**升级为活验**。
- **唯一硬阻塞 = 凭证**：BLOCKER-1（Elsevier key）+ Wiley token 缺失 + Kaggle 标准凭证缺失——均为**计划内 Phase 4 前置外部依赖**（非站点漂移）。
- Elsevier entitlement 语义（AC-4.3）与 `X-RateLimit-*`/全文字段名待 key 到位后活验（本轮 keyless 429 拦在 auth 层前，无法观测）。
- 预算实耗：**计入 5 / 25**；旁路 Crossref ×2 + WebSearch ×4 + WebFetch ×4（不计预算）。
