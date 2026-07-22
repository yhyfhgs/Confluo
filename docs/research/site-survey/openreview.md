---
title: 勘察：OpenReview API（v1/v2、鉴权、限流、届表）
status: approved
owner: fable5
updated: 2026-07-22
---

# 勘察 · OpenReview API

- 勘察时间：2026-07-21/22（客户端为用户本机 macOS，住宅 IP）
- UA：`PaperCrawler/0.1 (site survey; personal research)`（所有 curl 均带 `-A`；请求间 `sleep 1`）
- 实际发出 HTTP 请求总数：**25**（达到 ≤25 上限；已停止发请求）
- 标注约定：`[LIVE]`=实测证据；`[DOC]`=文档来源；`[UNRESOLVED]`=未能确认+原因
- **红线遵守**：只访问公开只读端点；遇到 403 反爬"挑战"（ChallengeRequiredError / 403 HTML）**未尝试破解或绕过**（未伪造浏览器 UA、未解挑战），仅记录其存在。

---

## ★ 头号发现（对设计影响最大，先读这一段）

**匿名（无 token）读取 `/notes` 与 PDF 目前被反爬"挑战"网关拦截；只有 `/groups` 开放。**

- `GET https://api2.openreview.net/notes?...`（v2）与 `GET https://api.openreview.net/notes?...`（v1）**一律返回 HTTP 403 `ChallengeRequiredError`**，与查询形态无关（`content.venueid=` 和 `invitation=` 都试过，4 次全 403，确定性）。
- `GET https://openreview.net/pdf?id=ryQu7f-RZ` **返回 HTTP 403**，`content-type: text/html`，`content-length: 12692`（即一张 403/挑战 HTML 页，非 PDF）。
- 对照：`GET https://api2.openreview.net/groups?...` 与 `api.openreview.net/groups?...` **正常 200**，返回公开数据（`readers:["everyone"]`）。
- 403 响应含限流头 `x-ratelimit-remaining: 59`（60 里只用了 1），**证明拦截不是限流触发，而是独立的挑战/反爬门**。
- OpenAPI 定义写明鉴权为 cookie 式：安全方案 `cookieAuth`，cookie 名 `openreview.accessToken`，`Required: Yes`。

**设计含义**：适配器**不能假设匿名 curl 能抓 notes / 下载 PDF**。可行路径：(a) 用官方 `openreview-py` 客户端（其登录后携带 `openreview.accessToken`，含 guest 登录也会拿 token）；或 (b) 自行走登录端点取 access token 后以 cookie/Bearer 携带。**唯一可匿名做的是 `/groups`（会场发现、venue-id 发现、存在性检查）**——paper 正文的采集必须鉴权。
（注意：挑战也可能是被我们这条**自定义 UA** 触发；设计阶段应以"携带 token 的官方客户端"复测确认，但无论如何都应把"需要鉴权"作为默认前提。）

---

## 1. API 版本边界 v1 vs v2 — [LIVE]+[DOC]

**判定方法（权威，[DOC] docs.openreview.net/getting-started/using-the-api）**：
> "If the group has a `domain` field → API 2；if `domain` is absent → API 1。" 并且 **无干净的按年切分规则**："API 1 may be used by some venues through 2024."（即不能用"2024 前=v1"这种年份线，必须逐会场探测。）

**[LIVE] 佐证**：`GET https://api2.openreview.net/groups?id=ICLR.cc/2024/Conference` → 该 group **含** `domain":"ICLR.cc/2024/Conference"` → 判定 **v2**。（group 顶层键含 `domain, host, invitations, web, members, readers…`；`invitations` 为 v2 风格 `.../-/Edit`。）

**关于"ICLR 2013/2014 能否从 v2 查到"**：
- notes 端点在 v1 与 v2 **都被挑战 403**，故**无法 LIVE 取到任一届的 note 正文**来直接对比。
- 但 `groups?id=venues` 在 **v1 与 v2 两个端点返回完全相同的主表**（各 4380 成员、179 个 ICLR id，见 §2）——说明 group/venue 目录是跨版本镜像的；**notes 正文归属版本要靠该会场 group 的 `domain` 字段判定**，而非端点本身。
- 结论（[DOC] 推断）：老会场（2013/2014，group 无 `domain`）应走 **v1 `api.openreview.net`**；2024 走 **v2 `api2.openreview.net`**。适配器应"先查 group 的 `domain` 字段 → 决定用哪个 base URL 查 notes"。
- base URLs（[DOC] OpenAPI）：prod `https://api2.openreview.net`（v2）、`https://api.openreview.net`（v1）；dev `https://devapi2.openreview.net`。

**注意**：本项"v2 查不到 v1 数据 → 必须走 v1"这一因果，因 notes 全被挑战，**未能 LIVE 直证**，仅由 `domain` 判定法 [DOC] 推出。

---

## 2. Venue group id 逐年表（2013→2027）— [LIVE] ★权威表

来源：`GET https://api2.openreview.net/groups?id=venues`（v1 端点结果**逐字相同**）。响应为 `{"groups":[{"id":"venues","members":[...4380...]}],"count":1,...}`；下表为 members 中 `ICLR.cc/*` 的**实测**结果（含大小写原样）。

| 年 | Conference 主会 venue id（**注意大小写**） | 其它卷（实测存在） |
|----|------------------------------------------|--------------------|
| 2013 | `ICLR.cc/2013/conference`（**小写 conference**） | — |
| 2014 | `ICLR.cc/2014/conference`（**小写**） | `ICLR.cc/2014/workshop`（小写） |
| 2015 | **缺失**（venues 主表无 `ICLR.cc/2015/*`） | — |
| 2016 | **无 conference 卷**；仅 `ICLR.cc/2016/workshop` | workshop only |
| 2017 | `ICLR.cc/2017/conference`（**小写**） | `ICLR.cc/2017/workshop` |
| 2018 | `ICLR.cc/2018/Conference`（**大写 C，自此起大写**） | `ICLR.cc/2018/Workshop` |
| 2019 | `ICLR.cc/2019/Conference` | 4 个 Workshop（DeepGenStruct/LLD/RML/drlStructPred） |
| 2020 | `ICLR.cc/2020/Conference` | 5 个 Workshop |
| 2021 | `ICLR.cc/2021/Conference` | 9 个 Workshop |
| 2022 | `ICLR.cc/2022/Conference` | Track/Blog + 多个 Workshop |
| 2023 | `ICLR.cc/2023/Conference` | `TinyPapers`、`BlogPosts`、多 Workshop |
| 2024 | `ICLR.cc/2024/Conference` | `TinyPapers`、`BlogPosts`、多 Workshop |
| 2025 | `ICLR.cc/2025/Conference` | `BlogPosts`、多 Workshop |
| 2026 | `ICLR.cc/2026/Conference` | `BlogPosts`、大量 Workshop（未来届，已建） |
| 2027 | `ICLR.cc/2027/Conference` | —（占位已存在） |

**设计要点**：
- **大小写不一致**：2013/2014/2016/2017 用小写 `conference`/`workshop`；**2018 起**用大写 `Conference`/`Workshop`。适配器**不能硬编码** `ICLR.cc/{year}/Conference`。
- **2015 conference、2016 conference 在 OpenReview venues 主表缺失**（ICLR 2015/2016 主会大概率不在 OpenReview 上，或用了别的 id）。适配器需对 2015/2016 特判。
- 只有 conference 卷是主会论文；Workshop/TinyPapers/BlogPosts 是独立 venue，按需过滤。

---

## 3. Note JSON 结构 — [DOC]（notes 被挑战，无法 LIVE 取实例）

**因 §★ 的挑战门，无法 LIVE 取到 ICLR 2024 单篇 note。** 以下为文档实测证据：

- **content 嵌套（v2）**：字段为 `content.<field>.value`。[LIVE-DOC] 来自 `https://docs.openreview.net/llms-full.txt` 的示例：
  `'content': {'abstract': {'value': 'This is an abstract 1'}, 'title': {'value': 'Paper title 1'}}`
  即 `note['content']['title']['value']`、`note['content']['abstract']['value']`。
- **v1 结构对比**：v1 为 `content.<field>` 直接取值（无 `.value` 包裹）。[DOC]（openreview-py 迁移说明）——本次未 LIVE 直证。
- **id 与 forum**：均为 note 标识；`forum` 指向讨论主帖 id；顶层论文帖自身 `id == forum`（回帖/评论的 `forum` 指回主帖，`id` 为自身）。[DOC]，本次未 LIVE 直证。
- **accepted 判定（venueid 语义）**：[DOC] docs.openreview.net：
  - **接收**：`content.venueid.value` == 该会**原始 venue id**（如 `ICLR.cc/2024/Conference`）；`venue` 字段为人读串（示例 `'venue': {'value': '... Conference Submission'}`，接收态通常形如 "ICLR 2024 poster/spotlight/oral"）。
  - **未接收/其它态**：用**不同字段/值**区分——`submission_venue_id`（在投/被拒仍挂"Submission"）、`withdrawn_venue_id`、`desk_rejected_venue_id`（原文："Other statuses use different fields like submission_venue_id, withdrawn_venue_id, and desk_rejected_venue_id"）。即**被拒论文的 venueid 不等于主会 id**，而是形如 `ICLR.cc/2024/Conference/Submission` 一类。
- **pdf 字段**：[LIVE-DOC] llms-full.txt 示例 `'pdf': {'value': '/pdf/pppppppppppppppppppppppppppppppppppppppp.pdf'}`——即 `content.pdf.value` 为**相对路径 `/pdf/<40位hex>.pdf`**。下载 URL 见 §7。

---

## 4. 空结果形态 — [LIVE]（envelope/404）+ [DOC]（notes 空数组）

- **[LIVE] id 未命中 → 404，不是空数组**：`GET https://api2.openreview.net/groups?id=ICLR.cc/1999/Conference` →
  `{"name":"NotFoundError","message":"Group Not Found: ICLR.cc/1999/Conference (2026-...)","status":404,"details":{"reqId":"..."}}`，HTTP **404**，`application/json`。
- **[LIVE] 命中 envelope 形态**：`groups?id=ICLR.cc/2024/Conference` → `{"groups":[...],"count":1,"fromCache":...}`（顶层 `<plural>` 数组 + `count` + `fromCache`）。
- **[DOC] notes 用合法但无匹配的过滤器**（如 `content.venueid=ICLR.cc/1999/Conference`）应返回 `{"notes":[],"count":0}`，HTTP 200——**本次因挑战门无法 LIVE 直证**。
- **设计要点**：错误处理需区分两类"空"：**按 id 精确查未命中=404 NotFoundError**；**按过滤器查零匹配=200 空数组 count:0**。

---

## 5. 分页 — [LIVE]（count 语义）+ [DOC]（limit 上限/offset）

- **[LIVE] count 语义**：响应顶层 `count` = **匹配总数**（非本页条数）。实测 `groups?id=ICLR.cc/2024/Conference` → `count:1`（单一匹配）。
- **[DOC] limit 上限 = 1000**：来源为 openreview-py 客户端行为（`get_all_notes` 按 1000/页翻页；超过 1000 服务端截断到 1000）。docs 散文页未明写数值（"cannot find max limit … in the docs"），故标 [DOC]；**本次未 LIVE 直证 limit=2000 的截断行为**（预算耗尽）。
- **[DOC] offset**：从第 offset 条起返回（0 基），配合 limit 翻页。
- **默认 limit**：未在文档明确（常见默认较小，如 25/1000 视端点）——[UNRESOLVED] 精确默认值。
- **设计要点**：全量抓取需 `offset += 1000` 循环直到累计达 `count`；单请求最多 1000。

---

## 6. 限流形态 — [LIVE] ★

来自被挑战请求（`api2.openreview.net/notes`）的**实测响应头**：
```
x-ratelimit-limit: 60
x-ratelimit-remaining: 59
x-ratelimit-reset: 1784651936      # epoch 秒
ratelimit-policy: 60;w=60          # 60 请求 / 60 秒窗口
ratelimit-limit: 60
ratelimit-remaining: 59
ratelimit-reset: 60                # 距重置秒数
set-cookie: GCILB="..."; HttpOnly  # GCP 负载均衡会话粘连 cookie，非鉴权
server: nginx ; via: 1.1 google    # OpenReview 托管在 GCP
```
- **结论**：每客户端约 **60 请求 / 60 秒滑动窗**。适配器应把节流设在 <1 req/s（本次 ≥1s/请求即合规）。
- 未故意触发 429；**未观测到 429**（挑战门在限流之前就拦截了）。挑战门与限流是**两套独立机制**。

---

## 7. PDF 下载 — [LIVE]（当前被 403 拦截）

- URL 形态：`https://openreview.net/pdf?id=<forum_id>`（主站 `openreview.net`，非 api2）。所用 id 来自 DBLP：`ryQu7f-RZ`（ICLR 2018）。
- **[LIVE] `HEAD https://openreview.net/pdf?id=ryQu7f-RZ`（带 PaperCrawler UA）→ HTTP 403**，`content-type: text/html`，`content-length: 12692`，`server: nginx`，`via: 1.1 google`。即返回一张 403/挑战 HTML，**不是 `application/pdf`**。
- **结论**：**PDF 端点同样被反爬门拦截**（与 §★ 一致）。预期正常态应为 `200 application/pdf`（可能 302 跳转到存储/CDN 域），但**本次匿名 UA 无法取得**。适配器下载 PDF 也需鉴权/官方客户端。
- [UNRESOLVED] 正常 PDF 的最终服务域名与 `Content-Type`（因被 403，未能观测；未尝试绕过）。

---

## 8. robots / ToS — robots [LIVE] / ToS [UNRESOLVED]

- **[LIVE] `https://openreview.net/robots.txt`（HTTP 200 text/plain）全文**：
  ```
  User-agent: *
  Disallow: /*?*email=
  ```
- **[LIVE] `https://api2.openreview.net/robots.txt`（HTTP 200 text/plain）全文**：**与上完全相同**
  ```
  User-agent: *
  Disallow: /*?*email=
  ```
- **结论**：robots **仅禁止含 `?...email=` 参数的 URL**；对 `/notes`、`/pdf`、`/groups` 等**无 robots 层禁止**（抓取受阻是应用层挑战门，非 robots）。适配器只需避免带 `email=` 查询参数即合规。
- **[LIVE 2026-07-22 主 agent 补抓] ToS（openreview.net/legal/terms）关键条款**：①API 为官方定义的程序化接口（"The OpenReview API is a programmatic interface providing functionality for data upload, search, and download, according to the privacy and access control rules"）——程序化访问系明确许可用途；②禁止绕过访问控制（"Users must not attempt to circumvent" readers/nonreaders/writers 规则）与破坏系统（DoS/bug exploitation）；③平台有权设传输上限（"set upper limits on the number of transmissions"）；④数据许可：元数据 CC0 1.0、评论 CC-BY-4.0、文章作者保留版权；⑤账号：真实身份、单账号（"Each user may have only one registered OpenReview account"）、密码不得授权第三方。**设计含义**：官方 token 鉴权+自限速+不代注册＝合规路径；挑战门是访问控制的一部分，不得绕过（我们不绕——走 cookieAuth）。

---

## 9. DBLP 锚点表（AC-2.1 golden 比对）— 存在性 [LIVE] / 篇数 [DOC-约值]

来源：`https://dblp.org/db/conf/iclr/index.html`（[LIVE] 200）；`.../iclr2018.html`、`.../iclr2014.html`（[LIVE]）。
**重要限制**：DBLP TOC 页大（+WebFetch 截断，且 DBLP 导出"first 1000 hits only"），**未能对每届做干净的 LIVE 计数**；下表"篇数"为**约值/公开常识 [DOC]，需后续用鉴权后的 OpenReview `count` 或完整 DBLP 页复核**。存在性/卷结构为 LIVE。

| 年 | DBLP 存在性 | 卷/track（DBLP） | 电子版链接指向 | 篇数（**约值，待核**） |
|----|-----------|------------------|--------------|----------------------|
| 2013 | 导航含 2013（LIVE-推断，未单独抓页）；OpenReview 有 `2013/conference` | conference（早期） | **arxiv.org**（2013 走 arxiv） | 十几篇量级 |
| 2014 | **LIVE 抓取确认** `iclr2014.html` 有条目 | "Oral Presentations" + "Poster Presentations"（会议 track）；OpenReview 另有 `2014/workshop` | **arxiv.org**（例 `arxiv.org/abs/1312.6173`）；proceedings 挂 `openreview.net/group?id=ICLR.cc/2014` | 数十篇量级 |
| 2015 | **DBLP index 未出现**（LIVE） | — | — | ICLR 2015 实际办过，但**不在此 DBLP index/OpenReview venues**——特判 |
| 2016 | **DBLP index 未出现**（LIVE） | — | — | 同上；OpenReview 仅有 `2016/workshop` |
| 2017 | **LIVE**（index） | conference | openreview.net | ~200 |
| 2018 | **LIVE**（index + 抓页）；slug `iclr2018.html` | conference + **workshop 卷** `conf/iclr/2018w` | **openreview.net**（例 id `ryQu7f-RZ`, `BJ8vJebC-`） | ~330 |
| 2019 | **LIVE**（index） | conference + **3 个 workshop 卷**（`2019drlsp/2019dgs/2019rml`） | openreview.net | ~500 |
| 2020 | **LIVE**（index） | conference | openreview.net | ~690 |
| 2021 | **LIVE**（index） | conference | openreview.net | ~860 |
| 2022 | **LIVE**（index） | conference | openreview.net | ~1095 |
| 2023 | **LIVE**（index） | conference + **Tiny Papers 卷** `conf/iclr/2023tiny` | openreview.net | ~1570 |
| 2024 | **LIVE**（index） | conference + **Tiny Papers 卷** `conf/iclr/2024tiny` | openreview.net | ~2260 |
| 2025 | **LIVE**（index） | conference | openreview.net | ~3600+（待核） |
| 2026 | DBLP 尚无 proceedings（未来届）；OpenReview 有 `2026/Conference` | — | — | — |

**DBLP slug 规律**：TOC 页为 `dblp.org/db/conf/iclr/iclr<year>.html`（注意 `2024.html` 会 404，须用 `iclr2024.html`）；workshop/tiny 卷有独立 slug（`2018w`、`2023tiny`、`2024tiny`）。
**设计要点**：(1) 2013/2014 论文正文在 **arxiv**（OpenReview 只存评审）——golden 比对要注意跨源；(2) **2015/2016 主会不在 OpenReview**（勘误 2026-07-22：DBLP index **有**这两卷、电子版在 iclr.cc——原"两侧同缺"表述被在线补验证伪），golden 表按平台 era 口径标注；(3) 每届篇数**必须用鉴权后 OpenReview `count`（venueid 过滤）重新生成**，本表约值仅供量级参考。

---

## 10. 可选认证 / guest 访问 — [LIVE]+[DOC]

- **[DOC] OpenAPI**：鉴权方案 `cookieAuth`，cookie 名 `openreview.accessToken`，`Required: Yes`。
- **[LIVE] 无 token 后果**：即 §★——匿名 `/notes`（v1+v2）403 ChallengeRequiredError、`/pdf` 403 HTML；仅 `/groups` 匿名可读（`readers:["everyone"]`）。
- **结论**：guest/匿名对**公开 venue 的 group 元数据**可读；但**note 正文与 PDF 需 access token**（或用会自动登录取 token 的 `openreview-py`）。"guest 无 token 直读 notes"在本次实测中**不成立/被挑战门拒**。数据差异层面（guest vs 登录能看到的字段/更严限流）**无法进一步 LIVE 对比**（无 token 连数据都取不到）。

---

## 完成度小结（10 项）

- **[LIVE] 为主：7 项** — #1(边界/domain判定 LIVE 佐证)、#2(venue 表)、#4(空/404 envelope)、#6(限流头)、#7(PDF 被 403)、#9(存在性)、#10(匿名被拒)
- **[DOC] 为主：2 项** — #3(note 结构/venueid 语义)、#5(limit 上限/offset)
- **[UNRESOLVED]/部分：1 项** — #8 的 **ToS 条款未抓**（robots.txt 两站已 LIVE 全文；ToS 因预算耗尽未取）

## 给设计文档（openreview.md）的可执行建议

1. **默认需鉴权**：把"匿名不可读 notes/PDF、须持 `openreview.accessToken`（或用 openreview-py，含 guest login 取 token）"写进适配器前提；只有 venue 发现走匿名 `/groups`。
2. **版本判定**：先 `groups?id=<venue>` 看有无 `domain` → v2(api2) / v1(api)；勿用年份线。
3. **venue-id 生成**：查表而非拼接——2013/2014/2016/2017 小写、2018+ 大写、2015/2016 主会缺；用 `groups?id=venues` 过滤 `ICLR.cc/*` 动态获取最稳。
4. **accepted 判定**：`content.venueid.value == 主会 venue id` 为接收；`*_Submission/Withdrawn/Desk_Rejected` 类为未收。**⚠ 勘误见 §11**：此惯例**只对 2017、2020-2026 成立**；2013/2014/2018/2019 的接收态**不在 venueid**（详见 §11 逐届表）。
5. **分页/限流**：limit≤1000 + offset 循环到 `count`；节流 <1 req/s（60/60s 窗）。
6. **golden 篇数**：本报告 §9 约值仅量级参考，正式 golden 须鉴权后按 venueid 过滤取 `count` 重生成；2015/2016、2013/2014(arxiv 源) 特别标注。

---

## 11. 逐届 accepted 判定惯例（[LIVE] 2026-07-22 · 缺陷 C-D 实测）★权威表

> 触发：Phase 2 终检缺陷 **C-D**——adapter 的 `content.venueid == 主会 id` accepted 过滤对
> ICLR **2018/2019 枚举出 0 篇**。本节以带 token 实测（**15 请求**，间隔 ≥1.6s，UA 携 mailto，
> 全 200 除 1 次故意 404，token 零回显）逐届搞清接收判定的真实出处。**结论：venueid 规约是
> 后期（2020+）才统一的惯例；早届接收态另有出处，逐届异构。**

**头号发现**：ICLR **2018/2019 的 blind submission 帖根本没有 `content.venueid`/`content.venue`
字段**（在真实接收论文 forum `ryQu7f-RZ`（2018）与 `rJl0r3R9KX`（2019，Meta_Review 明言"could
be accepted"）上实证）。§3 的 "接收 = venueid==主会 id、未收落 `*_Submission` 类" [DOC] 推断对这
两届**不成立**——它们的 venueid 是**缺席**而非"另一个值"。接收态记在**独立的决定帖**里。

### 11.1 逐届 accepted 判定表

| 届 | note 存储 | group `domain` | 接收态出处（[LIVE]） | 可靠过滤谓词 | accepted 数（[LIVE]） |
|----|-----------|----------------|----------------------|--------------|------------------------|
| 2013 | v1 | 无 | **submission 自身** `content.decision`（值 'reject' / 'conferencePoster-iclr2013-workshop' 等） | submission `content.decision` ∈ 主会 accept 词表 | 未全量 tally（67 投稿）；**Phase 3** |
| 2014 | v1 | 无 | **submission 自身** `content.decision`（值 'submitted, no decision' / 'reject' 等） | 同上 | 未全量 tally（69 投稿）；**Phase 3** |
| 2017 | v1 | 无 | `content.venueid`（存在） | **venueid==主会 id**（默认） | 543（上一 session；含面偏宽，未 DBLP 交叉） |
| **2018** | **v1** | **无** | **venue 级决定帖** `ICLR.cc/2018/Conference/-/Acceptance_Decision` 的 `content.decision` | **决定帖 `decision` startswith 'Accept'** | **337**（314 Poster + 23 Oral；935 决定帖：Reject 508 + Invite-to-Workshop 90 排除） |
| **2019** | **v1** | **无** | **per-paper 决定帖** `…/Paper<N>/Meta_Review` 的 `content.recommendation`（**非** venue 级——venue 级 `-/Meta_Review` 查询 count=0） | **submission `details=directReplies` 里 Meta_Review `recommendation` startswith 'Accept'** | **~500**；page-1 [LIVE] 391/1000（372 Poster + 19 Oral + 609 Reject）；exact 待 fixed-adapter smoke |
| 2020-2023 | v1 | 无 | `content.venueid`（存在） | venueid==主会 id | 825 / 860 / **2617** / **3792**（2022/2023 **含非接收**，见 11.3） |
| 2024-2026 | v2 | 有 | `content.venueid`（存在） | venueid==主会 id | 2260（==DBLP✓）/ 3703 / 5351 |

**版本/端点边界**：2018/2019 的 group 无 `domain` → 判定 **v1（api.openreview.net）**；notes 亦只在 v1
存储（`id=ryQu7f-RZ` 在 api2 查 **404**、在 api 查 **200**）。adapter 现有"groups 判 domain → 定
base URL"逻辑对这两届路由正确，缺陷纯在 accepted 过滤谓词。

### 11.2 决定帖形态（[LIVE] 实测样例，供 fixture 保真）

- **2018 决定帖**（v1 直取）：`invitation=ICLR.cc/2018/Conference/-/Acceptance_Decision`，`forum`=blind
  submission id，`content.decision` ∈ {`Accept (Oral)`, `Accept (Poster)`, `Reject`, `Invite to
  Workshop Track`}。venue 级单一 invitation → 一次翻页即得全届 935 决定。
- **2019 决定帖**（v1 直取）：`invitation=…/Paper<N>/Meta_Review`（**per-paper**），`content` 键
  `{metareview, recommendation, confidence, title}`，`recommendation` ∈ {`Accept (Poster)`,
  `Accept (Oral)`, `Reject`}。因 per-paper，无 venue 级聚合 invitation——须走 submission
  `details=directReplies`（v1 [LIVE] 支持）一遍取 submission+其决定。
- **2013/2014 submission**（v1 直取）：`invitation=…/-/submission`，`content` 含 `decision` **与
  `pdf`** 字段——即这两届 OpenReview **有** pdf（勘误 §9/design §4 的"2013/2014 note 无 pdf、正文只在
  arXiv"表述：pdf 字段**存在**；但正文仍多在 arXiv，跨源发现归 Phase 3）。

### 11.3 顺带疑点（预算所限未逐一实测，如实标注）

- **2022/2023 v1 `content.venueid==主会 id` 计数 2617/3792 >> survey accepted ~1095/~1570**：说明这两届
  venueid 过滤**含非接收**（over-count）。**本 session 未再单独实测其分辨谓词**（15 请求预算优先给了
  C-D 核心的 2018/2019/2013/2014）。此为**独立缺陷**（over-count，非 C-D 的 under-count-to-zero），
  留 Phase 3 跟进：疑似 rejected/withdrawn 也被赋了主会 venueid，或 venueid 精确匹配对这两届失真——
  须实测 rejected 论文的真实 venueid 值再定谓词。

### 11.4 对设计/实现的落地结论

1. **accepted 判定必须逐届数据驱动**，不能全局 `venueid==id`。已落地 `adapters/openreview/acceptance.py`
   的逐届规则表（`_ICLR_RULES`）：默认 `VenueidRule`；2018=`DecisionInvitationRule`；2019=`DirectRepliesRule`。
2. **2013/2014 保留默认（→0）**：符合 design §4 的"正文在 arXiv、跨源 Phase 3"口径；submission
   `content.decision` 惯例已实证记档，Phase 3 可补 `SubmissionDecisionRule`。
3. **2022/2023 over-count** 与 **2019 exact 数**：留 Phase 3 / 下次在线补验（见 11.3、anchor
   `cd_resolution`）。
