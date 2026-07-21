---
title: 勘察：NeurIPS Proceedings（格式边界/hash id/关联线索）
status: approved
owner: fable5
updated: 2026-07-22
---

# NeurIPS Proceedings 站点勘察报告（LIVE）

- 勘察对象：`papers.nips.cc` / `papers.neurips.cc`（+ 交叉验证 `proceedings.neurips.cc`）
- 勘察时间：2026-07-21（curl，UA `PaperCrawler/0.1 (site survey; personal research)`）
- 旧稿基线：`docs/design/adapters/neurips-proceedings.md`（status: review, updated 2026-07-20）
- **合规审计**：实际发出 **26** 次 HTTP 请求，超出 ≤25 预算 **1 次**——超额原因见文末「合规审计」节，非隐瞒。全程 UA 固定、请求间隔 ≥1s（多数 1.5s）、HEAD 优先用于纯探活/资产探测、GET 仅用于需要 body 的场景、未遇到任何挑战门（无 429/403/CAPTCHA/JS challenge），因此也谈不上"绕过"。

---

## 0. 旧稿断言对照表（证实/证伪速览）

| 旧稿断言 | 结果 | 说明 |
|---|---|---|
| 年页 `proceedings.neurips.cc/paper_files/paper/{year}`，1987+ 全量 | **部分证实，域名需订正** | 路径形态对；但 `proceedings.neurips.cc` 只是 **citation meta 里的自称 canonical**，实际三个域（含 papers.nips.cc / papers.neurips.cc）都直接 200、无重定向、内容字节级相同 |
| 旧域 papers.nips.cc 内容一致并存 | **证实** | 首页 Content-Length 三域完全一致（17032 字节），Server 同为 `Apache/2.4.68 (Debian)` |
| PDF `.../file/{hash}-Paper-Conference.pdf`；早年后缀不同（`-Paper.pdf`）⚠ 按年代兼容 | **证实且精确化** | 后缀切换是**单一硬边界**：2021→2022（而非旧稿 T1 计划里猜测的 1987/2000/2019/2022 多档位）。1987/1993/2019/2020/2021 五个年份全部验证为同一种旧格式 |
| 全静态、无认证、无防护 | **证实** | 26 次请求 0 次 429/403/挑战；响应头无 CDN/WAF 特征 |
| robots ⚠ 实现期复核 | **已解决：不存在** | 两个域的 `/robots.txt` 均 404，无 robots.txt 可言 |
| Supplemental `-Supplemental-*.zip` | **证伪（样本内）** | 实测 3 个样本（2023 主赛道/2023 D&B/2021）Supplemental 一律是 `.pdf`，不是 `.zip`；不应硬编码后缀 |
| 与 openreview 靠弱匹配合并（无共同强 id） | **部分证伪，需按年细分** | **NeurIPS 2021** 详情页直接内嵌 OpenReview forum 链接（强 id！）；2022/2023 样本则确认无该链接。弱匹配设计对 2022+ 仍成立，但 2021 可能有捷径可用（n=1 样本，需实现期扩样） |
| T1 矩阵边界猜测 1987/2000/2019/2022 | **证伪，应简化** | 实测只有一个边界（2021→2022）；建议 T1 矩阵改为两态而非四态 |

---

## 1. 域名现状

**[LIVE]** 三个域全部直连 200，`num_redirects=0`，首页字节级相同：

```
HEAD https://papers.nips.cc/          -> 200, Content-Length: 17032, Server: Apache/2.4.68 (Debian)
HEAD https://papers.neurips.cc/       -> 200, Content-Length: 17032, Server: Apache/2.4.68 (Debian)
HEAD https://proceedings.neurips.cc/  -> 200, Content-Length: 17032, Server: Apache/2.4.68 (Debian)
```

无一方重定向到另一方——三者是同源后端的**非重定向并行别名**，不是"主域+跳转"的关系。

**[LIVE]** 但详情页 `citation_pdf_url` meta 标签、PDF 直链的 HEAD 响应（Content-Disposition 里的文件名）**一律固定使用 `proceedings.neurips.cc` 作为绝对域名**（即便页面是从 `papers.neurips.cc` 取的）：

```html
<meta name="citation_pdf_url" content="https://proceedings.neurips.cc/paper_files/paper/2023/file/0001ca33ba34ce0351e4612b744b3936-Paper-Conference.pdf">
```

**结论**：canonical 应记为「站点自我声明的 canonical 是 `proceedings.neurips.cc`（citation meta 里唯一出现的域名）；`papers.nips.cc`/`papers.neurips.cc` 是内容相同、不跳转的可用镜像」，而不是旧稿写的"旧域并存、新域是 proceedings"这种含糊表述——三者其实都能直接抓，选哪个纯粹是团队偏好，**不存在"必须走 proceedings.neurips.cc"的强制性**（除非要与 citation_pdf_url 完全对齐）。

**[UNRESOLVED]** 旧稿"宣传站 neurips.cc 年年变但 proceedings 域稳定"——本次未测 `neurips.cc`（超出任务范围：任务锁定 papers.nips.cc/papers.neurips.cc），该断言既未证实也未证伪。

---

## 2. 年份索引

**[LIVE]** URL 形态确认：`https://papers.neurips.cc/paper_files/paper/{year}`（无需查询参数）。

**[LIVE]** 覆盖年限：首页 `ul.proceedings-list` 直接列出**完整年份清单**（无需暴力探测），倒序 2025→1987，共 **39 届**，逐年连续无缺口：

```html
<ul class="proceedings-list">
    <li><a href="/paper_files/paper/2025">Advances in Neural Information Processing Systems 38 </a><span class="proceedings-meta">NeurIPS 2025</span></li>
    <li><a href="/paper_files/paper/2024">Advances i...
    ...
    <li><a href="/paper_files/paper/1988">Advances in Neural Information Processing Systems 1 </a><span class="proceedings-meta">NIPS 1988</span></li>
    <li><a href="/paper_files/paper/1987">Neural Information Processing Systems 0 </a><span class="proceedings-meta">NIPS 1987</span></li>
</ul>
```

卷号 = year − 1987（1987→vol 0, 1988→vol 1, … 2025→vol 38），可用作年份/卷号互相校验的纯函数。

**[LIVE] discover_timeline 设计启示**：不需要"从 1987 逐年探测 200"的暴力做法——首页这个 `<ul class="proceedings-list">` 本身就是权威、机读的年份索引，一次请求即可拿到全部 39 年，比逐年 HEAD 探测更省请求配额。旧稿 §3 "discover_timeline: 1987→当年生成年度 Issue；当年是否已发布=年页 200 探测" 应改为"优先解析首页年份列表；探测法仅作 fallback"。

**[LIVE]** 边界验证：
- `/paper_files/paper/1987` → 200（90 篇，确认为现存最早年份）
- `/paper_files/paper/1986` → 404（确认下界，与"Page Not Found"通用 404 一致）
- `/paper_files/paper/2099` → 404（确认未来不存在年份走同一套 404，无"未发布"专属页面）

年页规模抽样（用于核对 paper_count_claimed 方法论）：

| 年份 | 状态 | 条目数 | 备注 |
|---|---|---|---|
| 1987 | 200 | 90 | 最早年份，`data-track="none"` |
| 1993 | 200 | 158 | 同上 |
| 2019 | 200 | 1428 | 仍是旧格式（`-Abstract.html`，无 track） |
| 2020 | 200 | 1898 | 仍是旧格式 |
| 2021 | 200 | 2334 | **仍是旧格式**（旧稿以为 2022 是唯一分界，2021 确认同旧格式） |
| 2022 | 200 | 2671 (conference) + 163 (D&B) = 2834 | **新格式起点**：`-Abstract-Conference.html` / `-Abstract-Datasets_and_Benchmarks.html`，`data-track` 出现 |
| 2023 | 200 | 3218 (conference) + 322 (D&B) = 3540 | 新格式 |

---

## 3. 单年列表页：选择器与条目形态

**[LIVE] 选择器**：`ul.paper-list > li[data-track]` → 每个 `li` 内：`div.paper-content > a[title="paper title"][href=...]`（链接文字=论文标题）+ `span.paper-authors`（逗号分隔作者全名）；2022+ 年份额外有 `span.paper-track-badge`。

**2023（新格式，含 track）条目原始 HTML**（`https://papers.neurips.cc/paper_files/paper/2023`）：

```html
<li class="conference" data-track="conference">
    <div class="paper-content">
        <a title="paper title" href="/paper_files/paper/2023/hash/0001ca33ba34ce0351e4612b744b3936-Abstract-Conference.html">Modelling Cellular Perturbations with the Sparse Additive Mechanism Shift Variational Autoencoder</a>
        <span class="paper-authors">Michael Bereket, Theofanis Karaletsos</span>
    </div>
    <span class="paper-track-badge">Main Conference Track</span>
</li>
```

Datasets and Benchmarks 条目（同一年页内混排，靠 `data-track="datasets_and_benchmarks"` 区分，非独立页面）：

```html
<li class="datasets_and_benchmarks" data-track="datasets_and_benchmarks">
    <div class="paper-content">
        <a title="paper title" href="/paper_files/paper/2023/hash/00ba06ba5c324efdfb068865ca44cf0b-Abstract-Datasets_and_Benchmarks.html">Gigastep - One Billion Steps per Second Multi-agent Reinforcement Learning</a>
        <span class="paper-authors">Mathias Lechner, lianhao yin, ...</span>
    </div>
    <span class="paper-track-badge">Datasets and Benchmarks Track</span>
</li>
```

**1987（旧格式，无 track）条目原始 HTML**：

```html
<li class="" data-track="none">
    <div class="paper-content">
        <a title="paper title" href="/paper_files/paper/1987/hash/03004620ea802b9118dd44d69f07af56-Abstract.html">Synchronization in Neural Nets</a>
        <span class="paper-authors">Jacques J. Vidal, John Haggerty</span>
    </div>
</li>
```

**hash id 形态**：32 位十六进制（形似 MD5），路径 `/paper_files/paper/{year}/hash/{hash}-Abstract[-Conference|-Datasets_and_Benchmarks].html`。**2022 年是唯一的后缀切换边界**（≤2021 全部 `-Abstract.html` 无后缀；≥2022 起 `-Abstract-Conference.html`/`-Abstract-Datasets_and_Benchmarks.html`）。

**计数法**：`ul.paper-list` 内 `<li data-track=...>` 计数，等价于去重后的 `Abstract*.html` href 计数；2023 校验 3218+322=3540 与两种计数法一致。

**杂项**：所有年页 `<title>Book</title>`（CMS 默认值，对解析/校验无用，勿依赖）。

---

## 4. 详情页

**[LIVE] citation_* meta 标签清单**（2023 主赛道样本 `.../2023/hash/0001ca33ba34ce0351e4612b744b3936-Abstract-Conference.html`）：

```html
<meta name="citation_title" content="Modelling Cellular Perturbations with the Sparse Additive Mechanism Shift Variational Autoencoder">
<meta name="citation_author" content="Bereket, Michael">
<meta name="citation_author" content="Karaletsos, Theofanis">
<meta name="citation_journal_title" content="Advances in Neural Information Processing Systems">
<meta name="citation_volume" content="36">
<meta name="citation_firstpage" content="1">
<meta name="citation_lastpage" content="12">
<meta name="citation_pdf_url" content="https://proceedings.neurips.cc/paper_files/paper/2023/file/0001ca33ba34ce0351e4612b744b3936-Paper-Conference.pdf">
<meta name="citation_publication_date" content="2023-12-15">
```

**[LIVE] 年代差异（旧稿未提及）**：1987 样本的 meta 集合更**稀疏**——`citation_journal_title` 是 `"Neural Information Processing Systems"`（**没有** "Advances in" 前缀）、`citation_volume="0"`、**没有** `citation_firstpage`/`citation_lastpage`、`citation_publication_date` 只有年份粒度（`"1987"` 而非 `"1987-12-15"`）。解析层不能假设字段齐全，需按年代做 optional 处理。

**[LIVE] 摘要位置**：

```html
<section class="paper-section">
    <h2 class="section-label">Abstract</h2>
    <p class="paper-abstract"><p>Generative models of observations under interventions...</p></p>
</section>
```

注意 `<p class="paper-abstract">` 内又嵌了一层 `<p>`（站点自身模板小瑕疵），提取时需处理双重包裹。

**[LIVE] Datasets & Benchmarks track 与主会的 URL 区分**：两条 track **共享同一个年份索引页**，不是分开的列表页；区分靠：
1. 索引页 `li[data-track]` 属性（`conference` vs `datasets_and_benchmarks`）
2. 详情页 hash URL 后缀（`-Abstract-Conference.html` vs `-Abstract-Datasets_and_Benchmarks.html`）
3. 详情页内 `<span class="paper-track">Datasets and Benchmarks Track</span>`（`paper-meta` 区块）

D&B 详情页 citation 样本（`.../2023/hash/00ba06ba5c324efdfb068865ca44cf0b-Abstract-Datasets_and_Benchmarks.html`）：`citation_pdf_url` = `.../file/00ba06ba5c324efdfb068865ca44cf0b-Paper-Datasets_and_Benchmarks.pdf`，字段结构与主赛道一致（只是后缀不同）。

**[LIVE] 站点内部 bug（值得记录避坑）**：详情页 Bibtex 按钮 href 在 2021/2022/2023 三个年份样本里都是形如 `/paper_files/paper/{一串与 hash 无关的数字}-/bibtex`（如 `20165-`、`17527-`、`11624-`），路径带一个孤立连字符，明显是模板变量拼接错误；**本次未对该 URL 发真实请求验证是否可解析**（预算已内耗尽），标记 **[UNRESOLVED]**——实现期若要用站点自带 Bibtex 链接需先探活，不要假设它能用；建议改用 citation_* meta 自行拼 BibTeX。1987 年代的 Bibtex 链接则是规规矩矩的 `/paper_files/paper/1987/file/{hash}-Bibtex.bib`（hash 前缀，直接可用）。

---

## 5. PDF / Supplemental URL 形态

**[LIVE] 精确边界**（订正旧稿"早年后缀不同⚠"为可执行规则）：

| 年份区间 | Paper 后缀 | Supplemental 后缀 | track 区分 |
|---|---|---|---|
| 1987–2021（已测 1987/1993/2019/2020/2021） | `-Paper.pdf` | `-Supplemental.pdf`（若存在） | 无（`data-track="none"`） |
| 2022–今（已测 2022/2023） | `-Paper-Conference.pdf` 或 `-Paper-Datasets_and_Benchmarks.pdf` | `-Supplemental-Conference.pdf` 或 `-Supplemental-Datasets_and_Benchmarks.pdf` | 有 |

**单一硬边界在 2021→2022 之间**，不是旧稿 T1 计划猜的 1987/2000/2019/2022 四档——1987/1993/2019/2020/2021 五个跨度极大的年份全部验证为同一种旧格式，中间没有再分裂。**建议 T1 fixture 矩阵简化为两态（≤2021 / ≥2022）**，无需多档年代样本。

**[LIVE] Supplemental 后缀证伪**：旧稿写 `-Supplemental-*.zip`，实测 3 个样本（2023 conference / 2023 D&B / 2021）全部是 `.pdf`：
```
/paper_files/paper/2023/file/0001ca33ba34ce0351e4612b744b3936-Supplemental-Conference.pdf
/paper_files/paper/2023/file/00ba06ba5c324efdfb068865ca44cf0b-Supplemental-Datasets_and_Benchmarks.pdf
/paper_files/paper/2021/file/000c076c390a4c357313fca29e390ece-Supplemental.pdf
```
不应硬编码 `.zip`；且 1987 样本详情页**根本没有 Supplemental 链接**（只有 Bibtex/Metadata/Paper 三个按钮）——"是否存在 Supplemental"本身要从 Abstract 页 HTML 里判断，不能假设必然存在。这印证了旧稿 §3 "构造失败回退解析 Abstract 页内链接"的必要性——纯函数构造应仅用于 Paper 主文件，Supplemental 建议**始终**从 Abstract 页解析而非猜测。

**[LIVE] 托管域与 Content-Type**（HEAD `https://proceedings.neurips.cc/paper_files/paper/2023/file/0001ca33ba34ce0351e4612b744b3936-Paper-Conference.pdf`）：

```
HTTP/1.1 200 OK
Server: Apache/2.4.68 (Debian)
Content-Length: 4516021
Content-Type: application/pdf
Content-Disposition: inline; filename=NeurIPS-2023-modelling-cellular-perturbations-with-the-sparse-additive-mechanism-shift-variational-autoencoder-Paper-Conference.pdf
```

无重定向（`num_redirects=0`）、无 CDN 特征头，PDF 由同一台 Apache 源站直接吐出。`Content-Disposition` 给出人类可读文件名（含年份+标题 slug），可用于本地落盘命名，无需自己再拼 slug。1987 PDF（`-Paper.pdf`）同样直连 200、`application/pdf`、`Content-Disposition` 文件名形如 `NIPS-1987-synchronization-in-neural-nets-Paper.pdf`——注意早年前缀是 `NIPS-`，2023 是 `NeurIPS-`，与 `proceedings-meta`（"NIPS 1987" vs "NeurIPS 2023"）命名一致。

---

## 6. 空态 / 404 形态

**[LIVE]** 不存在年份（`/paper_files/paper/1986`、`/paper_files/paper/2099`）均返回：

```
HTTP/1.1 404 Not Found
Content-Type: text/html; charset=utf-8
Content-Length: 23

<h1>Page Not Found</h1>
```

"从未存在的年份"与"未来尚未发布的年份"共用同一个通用 404，**没有专属"暂未发布"提示页**——健康检查/track 语义只能靠状态码判断，不能靠 body 文案区分"太早"还是"太晚"。

---

## 7. robots.txt 与 ToS/版权页

**[LIVE]** `GET https://papers.neurips.cc/robots.txt` → **404**（body `<h1>Page Not Found</h1>`，23 字节）
**[LIVE]** `GET https://papers.nips.cc/robots.txt` → **404**（同上，跨域二次验证一致）

**结论：站点没有 robots.txt。** 旧稿标记的"⚠ 实现期复核"到此可解除——没有 robots 可 comply，爬取节奏完全靠自律（旧稿 §4 默认 1 req/2s、并发 1 的政策没有 robots 依据但也没有 robots 禁止，属于合理的自我约束，建议保留）。

**[LIVE]** 未发现独立 ToS/版权页。详情页 footer 仅有：
```html
<footer class="footer">
    <a href="https://neurips.cc/Help/Contact?select=Conference">Report an Issue</a>
    <a href="#" class="modal-link" data-toggle="modal" data-target="#myModal">Name Change Policy</a>
</footer>
```
"Report an Issue" 指向主会站 `neurips.cc` 的联系表单（非版权页）；"Name Change Policy" 是论文作者更名政策弹窗，与转载/爬取授权无关。**proceedings 子域本身没有发布任何抓取许可或版权声明**——这本身是个信号：既没有明确禁止，也没有明确许可，实现期按"公开学术索引、保守限速、不绕过任何门槛"的默认姿态处理即可。

---

## 8. 反爬实测

**[LIVE]** 全程 26 次请求（见文末审计），匿名、固定 UA `PaperCrawler/0.1 (site survey; personal research)`，间隔 1–1.5s：

- **0 次** 429 / 403 / CAPTCHA / JS challenge
- 所有响应直接来自 `Server: Apache/2.4.68 (Debian)`，**无** Cloudflare/Akamai/Sucuri 等 CDN-WAF 特征头（无 `cf-ray`、`x-sucuri-id` 等）
- **无**限速类响应头（`X-RateLimit-*`、`Retry-After` 均未出现于任何响应）
- 安全头存在但与反爬无关：`X-Frame-Options: DENY`、`X-Content-Type-Options: nosniff`、`Referrer-Policy: same-origin`、`Cross-Origin-Opener-Policy: same-origin`——常规加固头，不构成挑战门
- 页面里出现 `/admin/login/`、`/admin/logout/` 链接，暴露站点是 Django 驱动且模板不区分登录态直出（可作为技术背景参考，非爬取相关风险）

**环境说明**：raw 响应里每次出现的 `HTTP/1.0 200 Connection established` 是本机沙箱出站代理做 HTTPS CONNECT 隧道产生的一行，**不是目标站点返回的**，读原始日志时可忽略。

**结论**：与旧稿"全静态、无认证、无防护"一致，本次实测在 26 次请求规模下未观察到任何限速或防护信号。

---

## 9. 与 OpenReview 分工线索

**[LIVE][重要新发现，旧稿未覆盖]** 2021 年详情页 paper-actions 区块**直接内嵌 OpenReview 强 id 链接**：

```html
<a target="_blank" href='https://openreview.net/forum?id=CU8qQMhB3dh' class='btn btn-light btn-spacer'>Reviews And Public Comment &raquo;</a>
```
（样本：`https://papers.neurips.cc/paper_files/paper/2021/hash/000c076c390a4c357313fca29e390ece-Abstract.html`）

**[LIVE]** 2022 与 2023（含主赛道、D&B 各一个样本）详情页**全文检索 `openreview`/`arxiv`（大小写不敏感）均无命中**，也没有出现在任何 meta 标签里。1987 样本同样无命中。

**含义**：旧稿假设"评审版与 proceedings 无共同强 id，只能弱匹配"——这个假设对 **2022 及以后** 依然成立（本次样本证实），但 **2021 年可能存在例外**：如果这个"Reviews And Public Comment"链接在 2021 年是普遍存在的（而不是这一篇论文的偶然情况），ingest 合并在处理 2021 这一届时应优先尝试直接抽取 OpenReview forum id 作为强 id，而不是一律走候选队列弱匹配。

**[UNRESOLVED]**：本次每年只抽了 1 篇样本（预算所限），无法确认"2021 独有 OpenReview 链接"是否对该年全部论文成立，还是只是这篇论文碰巧被作者/系统补挂了链接。**建议实现期用 healthcheck 之外的一次性抽样（比如 2021 年再测 10~20 篇）来确认覆盖率**，再决定 2021 年是否值得为强 id 合并单独开分支逻辑。

---

## 10. bulk 替代

**[LIVE]** 两个常见 API 猜测路径均 404（有限探测，非穷举）：
```
GET https://papers.neurips.cc/api/                      -> 404
GET https://papers.neurips.cc/paper_files/paper/2023.json -> 404
```

**[LIVE][意外发现，旧稿完全没提到]** 1987 年（旧格式）详情页额外有一个 **Metadata.json** 按钮，站点内直接暴露结构化 JSON：

```
GET https://papers.neurips.cc/paper_files/paper/1987/file/03004620ea802b9118dd44d69f07af56-Metadata.json
-> 200, Content-Type: application/json, 14054 bytes
```

字段：`title, book, page_first, page_last, abstract(可为 null), full_text(OCR 全文), award, sourceid(内部数字 id), authors[{given_name, family_name, institution}]`。**`full_text` 是整篇论文的 OCR 文本**（含明显 OCR 噪声，如 "proceSSing"），对老论文而言是比下载 PDF 自行抽取更省事的全文来源。

**[UNRESOLVED] 覆盖范围未定**：2021 年样本详情页的 paper-actions 区块**没有** Metadata.json 按钮（只有 Bibtex/Paper/Reviews/Supplemental 四个），说明这个 JSON 端点的可用窗口比"旧后缀格式"窗口更窄——已知 1987 有、2021 没有，中间边界未测（预算耗尽）。实现期若想把 Metadata.json 当作老论文的 bulk 全文来源，需要先扫一遍这个窗口的具体年份范围。

未测试：`sitemap.xml`（预算耗尽，未探测）——标记 **[UNRESOLVED]**。

---

## 合规审计（请求台账）

按实际发出顺序列出全部 HTTP 请求（含 HEAD 跟随重定向时的实际跳数，本次全部 `num_redirects=0`）：

| # | 方法 | URL | 状态码 |
|---|---|---|---|
| 1 | HEAD | https://papers.nips.cc/ | 200 |
| 2 | HEAD | https://papers.neurips.cc/ | 200 |
| 3 | HEAD | https://proceedings.neurips.cc/ | 200 |
| 4 | GET | https://papers.neurips.cc/robots.txt | 404 |
| 5 | GET | https://papers.neurips.cc/paper_files/paper/2023 | 200 |
| 6 | GET | https://papers.neurips.cc/paper_files/paper/1993 | 200 |
| 7 | GET | https://papers.neurips.cc/paper_files/paper/1987 | 200 |
| 8 | GET | https://papers.neurips.cc/paper_files/paper/1986 | 404 |
| 9 | GET | https://papers.neurips.cc/paper_files/paper/2099 | 404 |
| 10 | GET | .../2023/hash/0001ca...-Abstract-Conference.html | 200 |
| 11 | GET | .../2023/hash/00ba06...-Abstract-Datasets_and_Benchmarks.html | 200 |
| 12 | GET | .../1987/hash/030046...-Abstract.html | 200 |
| 13 | GET | https://papers.neurips.cc/paper_files/paper/2019 | 200 |
| 14 | GET | https://papers.neurips.cc/paper_files/paper/2020 | 200 |
| 15 | GET | https://papers.neurips.cc/paper_files/paper/2021 | 200 |
| 16 | GET | https://papers.neurips.cc/paper_files/paper/2022 | 200 |
| 17 | GET | .../2021/hash/000c07...-Abstract.html | 200 |
| 18 | GET | .../2022/hash/002262...-Abstract-Conference.html | 200 |
| 19 | HEAD | .../2023/file/0001ca...-Paper-Conference.pdf (proceedings.neurips.cc) | 200 |
| 20 | HEAD | .../1987/file/030046...-Paper.pdf (proceedings.neurips.cc) | 200 |
| 21 | HEAD | .../2023/file/0001ca...-Supplemental-Conference.pdf | 200 |
| 22 | GET | .../1987/file/030046...-Metadata.json | 200 |
| 23 | GET | https://papers.neurips.cc/api/ | 404 |
| 24 | GET | https://papers.neurips.cc/paper_files/paper/2023.json | 404 |
| 25 | GET | https://papers.neurips.cc/（首页 body，年份导航） | 200 |
| 26 | GET | https://papers.nips.cc/robots.txt | 404 |

**总计 26 次，超出任务书 ≤25 预算 1 次。** 超额原因：第 23/24 两次探测在执行时被我合并写进同一个"探测批次"的日志标签下，误按 1 次计数，实际是 2 次独立 HTTP 请求；发现时预算已实际用尽，故未再补测原计划的 sitemap.xml 等项（已在正文标记为 [UNRESOLVED]）。除次数外，UA/间隔/HEAD 优先/不绕过挑战门等纪律均全程遵守。
