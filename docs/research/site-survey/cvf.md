---
title: 勘察：CVF Open Access（列表形态/双代路径/供给面）
status: approved
owner: fable5
updated: 2026-07-22
---

# CVF Open Access 站点勘察报告

- 勘察对象：`openaccess.thecvf.com`
- 方法：LIVE 实测（curl，UA `PaperCrawler/0.1 (site survey; personal research)`，间隔 ≥1.5s，HEAD 优先用于仅需状态/头部的重复性检查）
- 实测时间：2026-07-21（响应头 `Date` 均为 `Tue, 21 Jul 2026`）
- 总请求数：**22**（对 openaccess.thecvf.com；另有 1 次 WebSearch 用于核对 item 10，不计入站点请求预算）
- 旧稿：`docs/design/adapters/cvf.md`（review 状态，2026-07-20 更新）——本报告逐条核验/证伪其 §2 断言

---

## 0. 与旧稿断言的核验结论（先给结论，细节见下文各节）

| 旧稿断言 | 结论 | 证据位置 |
|---|---|---|
| 目录 `openaccess.thecvf.com/{CONF}{year}`（如 `CVPR2024`） | ✅ 部分确认，但**不完整**：`{CONF}{year}` bare URL 是"日期选择landing页"，不是论文列表本身；真正列表要 `?day=all` 或 `?day=YYYY-MM-DD` | §2 |
| "按 day/all 分页变体历年略有不同" | ✅ 确认，且比旧稿描述更复杂：现代年份（2021+）有 day1/day2/day3/all 四态；早期年份（2013、ECCV2018）**完全没有 day 分页**，是单一扁平列表 | §2, §9 |
| 单篇 `/content/{CONF}{year}/html/{Author}_{Title}_{CONF}_{year}_paper.html`；PDF 同名 `.pdf`；supplemental 在 `/supplemental/` | ⚠ **部分证伪**：PDF 路径确为 html 路径纯函数改写（`/html/`→`/papers/`, `.html`→`.pdf`）；但 **supplemental 文件名不是 html/pdf slug 的函数**——是独立生成的短 slug，必须从条目 HTML 里解析 `[supp]` 链接，不能靠规则改写推导 | §3, §4 |
| "全静态 HTML、无认证、无防护" | ⚠ **需修正**：详情页（`/content/.../html/*.html`）是静态文件（有 `Last-Modified`/`ETag`）；但列表页/menu 页是 **动态 CGI**（`Content-Location: proceedings.py` / `menu.py`，无缓存头）。匿名可读性、无认证、无 WAF/挑战信号 = 确认 | §8 |
| ECCV："CVF 镜像旧格式 `content_ECCV_{year}`，ECCV2024 新路径实测 403" | ❌ **证伪**：`/ECCV2024` 实测是标准 **404**（不是 403），且 ECCV 根本不在 CVF 任何菜单（含"Other Conferences"）中出现 2022/2024 年份。ECCV 仅 2018 年在 CVF 上（旧格式 `content_ECCV_2018`，flat 列表，相对路径 href）；ECCV2020 的"Main Conference"链接直接指向外部 `ecva.net`，2022+ 完全不在 CVF | §5 |
| CVF 收录 2013+；更早只在 IEEE Xplore | ✅ 确认：`CVPR2013`/`ICCV2013` 是 menu 上最早年份；`CVPR2012` 实测 404 | §9 |
| WACV ~2020+ | ✅ 确认：menu 最早 WACV 是 2020（Snowmass）；`WACV2019` 实测 404 | §9 |
| ICCV 奇数年 | ✅ 确认：menu 列出 2013/15/17/19/21/23/25 全为奇数年；`ICCV2022`（偶数年）实测 404 | §1 |

---

## 1. 会议列表结构（menu 页）

**[LIVE]** `GET https://openaccess.thecvf.com/` → `302 Found`，`Location: https://openaccess.thecvf.com/menu`（首页本身不是内容页，是重定向）

**[LIVE]** `GET https://openaccess.thecvf.com/menu` → `200`，`Content-Location: menu.py`（动态 CGI，非静态文件）

菜单分两段：
1. **"CVF Sponsored Conferences"**（主菜单，CVPR/WACV/ICCV，2013→2026 全量列出）
2. **"Other Computer Vision Conferences and Workshops"** → 链接到独立页 `/menu_other.html`（ACCV + ECCV，见 §5）

原始摘录（`menu.html` 部分年份，完整列表见 raw HTML）：
```html
<dd>CVPR 2026, Denver Colorado [<a href="CVPR2026">Main Conference</a>] ... [<a href="CVPR2026_findings">Findings</a>] ... [<a href="CVPR2026_workshops">Workshops</a>] ...</dd>
<dd>WACV 2026, Tucson Arizona [<a href="WACV2026">Main Conference</a>] [<a href="/WACV2026_workshops/menu">Workshops</a>] ...</dd>
<dd>ICCV 2023, Paris France [<a href="ICCV2023">Main Conference</a>] ... [<a href="/ICCV2023_workshops/menu">Workshops</a>] ...</dd>
<dd>CVPR 2022, New Orleans Louisiana [<a href="CVPR2022">Main Conference</a>] [<a href="/CVPR2022_workshops/menu">Workshops</a>] [<a href="CVPR2022_demos">Demos</a>] ...</dd>
<dd>CVPR 2020, Virtual [<a href="CVPR2020.py">Main Conference</a>] [<a href="/CVPR2020_workshops/menu.py">Workshops</a>]</dd>
<dd>CVPR 2013, Portland Oregon [<a href="CVPR2013.py">Main Conference</a>] [<a href="/CVPR2013_workshops/menu.py">Workshops</a>]</dd>
```

**关键发现——URL 形态按年代分两代**：
- **2021+**（CVPR2021/ICCV2021/WACV2021 起）：链接无 `.py` 后缀，如 `CVPR2023`、`/CVPR2023_workshops/menu`
- **2020 及更早**：菜单链接显式带 `.py`，如 `CVPR2020.py`、`/CVPR2020_workshops/menu.py`
- **[LIVE] 但旧后缀已变成兼容重定向**：`GET /CVPR2013.py` → `307 Temporary Redirect` → `Location: https://openaccess.thecvf.com/CVPR2013`（即站点已统一到无后缀规范形式，`.py` 只是历史链接的重定向垫片，两种写法目前都可用）

**新发现（旧稿未提及）——非常规分类**：
- CVPR2026 除 Main/Workshops 外还有 **`CVPR2026_findings`**（Findings track，类似 ACL Findings 概念，CVF 新增分类）
- CVPR2022 除 Main/Workshops 外还有 **`CVPR2022_demos`**（Demos track）
- 这些是 venue 内部的"子卷"变体，AC-2.4 `pull cvpr --year 2023` 的口径需要明确排除/包含策略（2023 年这两个变体都不存在，仅 Main+Workshops）

**ICCV 双年制**：**[LIVE]** 确认。menu 列出 ICCV 年份 2013/2015/2017/2019/2021/2023/2025，全部奇数年，无一偶数年。`GET /ICCV2022` → **404**（见 §9 原始响应）。

---

## 2. 单会年列表页结构

### 2a. Bare `{CONF}{year}` = 日期 landing 页，不是论文列表

**[LIVE]** `GET https://openaccess.thecvf.com/CVPR2023` → `200`，`Content-Location: proceedings.py`

完整页面内容（`<div id="content">` 部分，逐字摘录）：
```html
<h3>Papers</h3>
<dl>
<dd>[<a href="/CVPR2023?day=2023-06-20">Day 1: 2023-06-20</a>]<br><br></dd>
<dd>[<a href="/CVPR2023?day=2023-06-21">Day 2: 2023-06-21</a>]<br><br></dd>
<dd>[<a href="/CVPR2023?day=2023-06-22">Day 3: 2023-06-22</a>]<br><br></dd>
<dd>[<a href="/CVPR2023?day=all">All Papers</a> <div class="icon-tooltip">...
<span class="tooltiptext">Loading all papers from this conference may be slow.</span></div>]<br><br></dd>
</dl>
```
即 bare URL 只给出 3 个"按天"链接 + 1 个 "All Papers" 链接（`?day=all`），**不含任何论文条目**。这与旧稿"目录 `{CONF}{year}`"暗示"目录页即列表页"的表述不符——真正枚举需要显式加 `?day=all`（或遍历 day 参数再去重/合并）。站点自己提示 all 页加载慢。

### 2b. `?day=all` 真实列表页 + 单条目原始 HTML

**[LIVE]** `GET https://openaccess.thecvf.com/CVPR2023?day=all` → `200`，`Content-Location: proceedings.py`，正文 6,273,839 字节 / 91,968 行

**总篇数（AC-2.4 锚点）**：三种独立计数方式互相印证，均为 **2353**：
- `<dt class="ptitle">` 出现次数：2353
- `papers/*.pdf` 链接数：2353
- pdf 标签 `>pdf</a>` 出现次数：2353

附加统计（同一份 HTML 内 grep 得出）：
- 含 `[supp]` 链接的条目：2018 / 2353（86%）
- 含 `[arXiv]` 链接的条目：1454 / 2353（62%）——见 §10

**单条目原始 HTML（完整摘录，第一条 "GFPose"）**：
```html
<dt class="ptitle"><br><a href="/content/CVPR2023/html/Ci_GFPose_Learning_3D_Human_Pose_Prior_With_Gradient_Fields_CVPR_2023_paper.html">GFPose: Learning 3D Human Pose Prior With Gradient Fields</a></dt>
<dd>
<form id="form-HaiCiGFPoseLearning3D" action="/CVPR2023" method="post" class="authsearch">
<input type="hidden" name="query_author" value="Hai Ci">
<a href="#" onclick="document.getElementById('form-HaiCiGFPoseLearning3D').submit();">Hai Ci</a>,
</form>
<!-- ... 每位作者一个独立 <form>，重复 6 次 ... -->
</dd>
<dd>
[<a href="/content/CVPR2023/papers/Ci_GFPose_Learning_3D_Human_Pose_Prior_With_Gradient_Fields_CVPR_2023_paper.pdf">pdf</a>]
[<a href="/content/CVPR2023/supplemental/Ci_GFPose_Learning_3D_CVPR_2023_supplemental.pdf">supp</a>]
[<a href="http://arxiv.org/abs/2212.08641">arXiv</a>]
<div class="link2">[<a class="fakelink" onclick="$(this).siblings('.bibref').slideToggle()">bibtex</a>]
<div class="bibref pre-white-space">@InProceedings{Ci_2023_CVPR,
    author    = {Ci, Hai and Wu, Mingdong and Zhu, Wentao and Ma, Xiaoxuan and Dong, Hao and Zhong, Fangwei and Wang, Yizhou},
    title     = {GFPose: Learning 3D Human Pose Prior With Gradient Fields},
    booktitle = {Proceedings of the IEEE/CVF Conference on Computer Vision and Pattern Recognition (CVPR)},
    month     = {June},
    year      = {2023},
    pages     = {4800-4810}
}</div>
</div>
</dd>
```

**关键选择器级发现（旧稿完全未提及，对 `enumerate_issue` 设计有直接影响）**：
1. **标题/链接**：`dt.ptitle > a` —— 稳定、简单。
2. **作者不是普通 `<a href>` 链接**，而是逐位作者的 `<form method="post" class="authsearch">` + `<input type="hidden" name="query_author" value="{Full Name}">`。作者名要从 `input[name=query_author]` 的 `value` 属性取，或退化为 `<a>` 标签内文本——两者一致，取哪个都行，但**不能假设作者是可直接跟随的 `<a href>`**。
3. **PDF 链接**是 html 路径的纯函数（`/html/`→`/papers/`，`.html`→`.pdf`），旧稿"由 html 路径规则改写"对 PDF 成立。
4. **Supplemental 文件名不可由规则推导**：本例 html/pdf slug 是 `Ci_GFPose_Learning_3D_Human_Pose_Prior_With_Gradient_Fields_CVPR_2023_paper`，supplemental 文件名却是 `Ci_GFPose_Learning_3D_CVPR_2023_supplemental`（明显截断/独立生成，无法通过后缀替换推出）。**必须解析条目 HTML 里的 `[supp]` `<a href>` 才能拿到真实 URL**，`resolve_assets` 不能对 supplemental 用"纯函数改写"。
5. **列表页本身即含 arXiv 链接 + 完整 BibTeX**（含 `pages` 字段），不需要访问详情页就能拿到较完整元数据——见 §10。

### 2c. day 单页 vs all 页的关系

**[LIVE]** `GET /CVPR2023?day=2023-06-20` → `200`，条目数 **785**。785×3 ≈ 2355，与 all 页 2353 基本吻合（三天条目并集 = all 页全集，个别边界差异可能来自跨天口头报告/撤稿等，未细究）。结论：day 分页是 all 列表的**互斥切分**，`day=all` 服务端做的是同一份数据的合并渲染，不是另一套数据源。

---

## 3. 详情页（html 论文页）结构

**[LIVE]** `GET https://openaccess.thecvf.com/content/CVPR2023/html/Ci_GFPose_..._paper.html` → `200`
```
Last-Modified: Wed, 31 May 2023 16:18:01 GMT
ETag: "182b-5fcffa9ea1425"
Accept-Ranges: bytes
```
（**静态文件**，与列表页/menu 的动态 CGI 响应头形成对比——无 `Last-Modified`/`ETag`/`Accept-Ranges`）

**citation_\* meta 标签（完整清单，逐字摘录）**：
```html
<meta name="citation_title" content="GFPose: Learning 3D Human Pose Prior With Gradient Fields">
<meta name="citation_author" content="Ci, Hai">
<meta name="citation_author" content="Wu, Mingdong">
<!-- ... 每作者一条 citation_author，"Last, First" 格式 ... -->
<meta name="citation_publication_date" content="2023">
<meta name="citation_conference_title" content="Proceedings of the IEEE/CVF Conference on Computer Vision and Pattern Recognition">
<meta name="citation_firstpage" content="4800">
<meta name="citation_lastpage" content="4810">
<meta name="citation_pdf_url" content="https://openaccess.thecvf.com/content/CVPR2023/papers/Ci_GFPose_..._paper.pdf">
```
**没有**：`citation_doi`（CVF 版不分配 DOI，DOI 归属 IEEE Xplore 正式版）、`citation_abstract`、`citation_volume`/`citation_issue`。`citation_publication_date` 只精确到年，无月日。

**摘要位置**：不在 meta 标签里，在正文 `<div id="abstract">纯文本</div>`：
```html
<div id="content">    <dl>
    <div id="papertitle">
        GFPose: Learning 3D Human Pose Prior With Gradient Fields
    <dd></div>
    <div id="authors">        <br><b><i>Hai Ci, Mingdong Wu, ...</i></b>; Proceedings of the IEEE/CVF Conference on Computer Vision and Pattern Recognition (CVPR), 2023, pp. 4800-4810</div>
    <font size="5"><br><b>Abstract</b></font><br><br>
    <div id="abstract">
    Learning 3D human pose prior is essential to human-centered AI. ...
    </div>
    <font size="5"><br><b>Related Material</b></font><br><br>
    <dd>[pdf] [supp] [arXiv] [bibtex-toggle-div] </dd>
</div>
```
详情页的 "Related Material" 区块与列表页条目内容**完全重复**（同样的 pdf/supp/arXiv/bibtex）——意味着 `enumerate_issue` 阶段如果已经解析了列表页，详情页对 asset 解析是冗余的；详情页的增量价值仅在于**摘要正文**。

---

## 4. PDF / Supplemental URL 与托管

**[LIVE]** `HEAD /content/CVPR2023/papers/Ci_GFPose_..._paper.pdf`：
```
HTTP/1.1 200 OK
Last-Modified: Mon, 08 May 2023 16:08:16 GMT
ETag: "17ebca-5fb30d8b07c00"
Accept-Ranges: bytes
Content-Length: 1567690
Content-Type: application/pdf
```
**[LIVE]** `HEAD /content/CVPR2023/supplemental/Ci_GFPose_Learning_3D_CVPR_2023_supplemental.pdf`：
```
HTTP/1.1 200 OK
Last-Modified: Thu, 30 Mar 2023 16:13:02 GMT
Content-Length: 777635
Content-Type: application/pdf
```
两者均**同源直出**（`openaccess.thecvf.com` 本域，无 302 跳转到 CDN/对象存储，无最终域名变化），`Content-Type: application/pdf` 准确，`Accept-Ranges: bytes` 支持断点续传。本例 supplemental 恰好也是 PDF，但文件名规则见 §2b（不可推导，需解析页面）；其他论文的 supplemental 也可能是其他格式（未逐一验证，标记 **[UNRESOLVED]** — 未见 zip/mp4 案例，仅验证了 1 篇）。

---

## 5. Workshop 卷 vs 主会区分

**[LIVE]** `GET /CVPR2023_workshops/menu` → `200`，`Content-Location: workshop_menu.py`。这是**workshop 分卷索引页**，非论文列表：
```html
<h3>CVPR 2023 Workshops</h3>
<dl>
<dd><a href="/CVPR2023_workshops/TCV">The Fourth Workshop on Fair, Data-Efficient, and Trusted Computer Vision</a></dd>
<dd><a href="/CVPR2023_workshops/WAD">Workshop on Autonomous Driving</a></dd>
<!-- ... -->
</dl>
```
CVPR2023 共 **60 个 workshop 分卷**（`/CVPR2023_workshops/{CODE}` 去重计数）。

**[LIVE]** `GET /CVPR2023_workshops/WAD` → `200`，`Content-Location: proceedings.py`（与主会列表页同一套渲染逻辑），16 篇论文。**关键差异（旧稿未提及）**：workshop 论文的 content 路径和 CVPR2023 主会**不是同一目录**：
```html
<dt class="ptitle"><br><a href="/content/CVPR2023W/WAD/html/Singh_..._CVPRW_2023_paper.html">...</a></dt>
```
- 目录是 `/content/CVPR2023W/{workshop_code}/...`（注意 **`CVPR2023W`** 带 W 后缀，不是 `CVPR2023`）
- 文件名 slug 里的会议标记是 **`_CVPRW_2023_paper`**（`CVPRW` 不是 `CVPR`）

即"workshop 是主会的子目录"这个假设是错的——workshop 内容在完全独立的 `{CONF}{year}W` 命名空间下，`resolve_assets` 的路径改写规则对 main/workshops 不能共用同一套正则。

**区分主会/workshop 的判定**：URL 路径段 `_workshops` 存在与否 + 内容目录带不带 `W` 后缀，是两个独立但一致的信号。

---

## 6. 空态 / 404 形态

**[LIVE]** 标准 404（Apache 默认页，`Content-Length: 284` 恒定，无自定义 404 模板）：
```
HTTP/1.1 404 Not Found
Content-Type: text/html; charset=iso-8859-1

<!DOCTYPE HTML PUBLIC "-//IETF//DTD HTML 2.0//EN">
<html><head><title>404 Not Found</title></head><body>
<h1>Not Found</h1>
<p>The requested URL was not found on this server.</p>
<hr><address>Apache/2.4.58 (Ubuntu) Server at openaccess.thecvf.com Port 443</address>
</body></html>
```
命中该 404 的实测 URL：`/robots.txt`、`/CVPR2027`（未来/不存在年份）、`/ICCV2022`（偶数年）、`/ECCV2024`（不存在）、`/CVPR2012`（早于覆盖边界）、`/WACV2019`（早于 WACV 覆盖）、`/sitemap.xml`。**全部同一形态**，是可靠的"不存在"判别信号：`status==404 && Content-Length==284`。没有观察到"空列表但 200"的情况——不存在的年份/会议一律 404，不是空页面。

---

## 7. robots.txt + 页脚 ToS/版权声明

**[LIVE]** `GET /robots.txt` → **404**（文件不存在，同 §6 标准错误页）。即**站点未发布任何 robots 指令**，无 Disallow 规则可循，也无 Crawl-delay 声明。（旧稿 §4 "robots ⚠ 实现期复核"——现已核实：不是"待复核"，是"根本没有 robots.txt"，NFR-4 限速只能靠礼貌自律，无站点声明可参照。）

**[LIVE] 页脚/头部原文摘录**（`menu.html` 与所有会议页一致出现）：

> "These research papers are the Open Access versions, provided by the Computer Vision Foundation. Except for the watermark, they are identical to the accepted versions; the final published version of the proceedings is available on IEEE Xplore."

> "This material is presented to ensure timely dissemination of scholarly and technical work. Copyright and all rights therein are retained by authors or by other copyright holders. All persons copying this information are expected to adhere to the terms and constraints invoked by each author's copyright."

**Errata 政策原文**（仅主菜单页出现，详细说明勘误流程）：

> "It is the policy of the Computer Vision Foundation to maintain PDF copies of conference papers as submitted during the camera-ready paper collection. These papers are considered the final published versions of the work. We recognize the need for minor corrections after publication, and thus provide links to arXiv versions of the papers where available. If a correction must be made, it should be made as an update to the arXiv version of the paper by the authors. The CVF maintainers should then be notified of the update via email (errata@thecvf.com)."

要点：CVF 明确"版权归作者/原版权方所有"，不主张自己对论文内容的版权；CVF 版是 camera-ready 快照，不做原地修改，勘误走 arXiv 侧更新 + 邮件通知（`errata@thecvf.com`）。

---

## 8. 反爬实测

**匿名可读性**：全部 22 次请求（含首页、menu、列表页、详情页、PDF HEAD、supplemental HEAD、workshop 页、跨年份/跨会 404 探测）均**无需任何认证**，未见 `Set-Cookie`、`WWW-Authenticate`、Cloudflare/WAF 特征头（`cf-*`）、验证码页面。**[LIVE]** 对 `/CVPR2023?day=all` 额外做 `HEAD` 验证（非仅 GET）同样 `200`，确认 HEAD 方法本身被正常支持（对动态 `proceedings.py` 端点也成立，非仅静态资源）。

**限速信号**：抓取全部 22 次响应头，**未发现** `X-RateLimit-*`、`Retry-After`、`Retry-Later` 等限速相关头部。不代表没有限速（未做压力测试去验证阈值，这超出"个人调研"的礼貌范围），只能说：**服务端未通过响应头主动暴露限速策略**，也未在本次~15分钟、22 请求、间隔≥1.5s 的克制节奏下触发任何 4xx/5xx 异常或质询。

**结论**：站点是纯 Apache 静态+CGI 混合站，无可见反爬层；旧稿"无防护"的定性成立，但应改写为"匿名可读、无认证、未见 WAF/挑战信号"这类可证伪表述，而非笼统"无防护"。

---

## 9. 早年覆盖边界

**[LIVE]** menu 页最早年份：**CVPR 2013**（Portland Oregon）、**ICCV 2013**（Sydney Australia）。无 CVPR/ICCV 2012 或更早出现在任何菜单。

**[LIVE]** `GET /CVPR2012` → 404（同 §6 标准形态），确认边界。

**[LIVE]** `GET /CVPR2013.py` → `307` → `Location: /CVPR2013`；`GET /CVPR2013` → `200`，`Content-Location: CVPR2013.py`，**471 篇论文，无 day 分页**（不同于 2021+ 年份的 day1/2/3/all 四态），条目 href 为**相对路径**、旧式目录名：
```html
href="content_cvpr_2013/papers/Kim_Deformable_Spatial_Pyramid_2013_CVPR_paper.pdf"
```
（对比 CVPR2023 是绝对路径 `/content/CVPR2023/papers/...`）—— 目录命名 `content_cvpr_2013`（全小写+下划线）vs 现代 `/content/CVPR2023/`（大小写年份紧跟），是两套不同的路径规则，`enumerate_issue`/`resolve_assets` 需要按"era"分支处理，不是单一正则能覆盖。

**WACV 边界**：**[LIVE]** menu 最早 WACV 是 **2020**（Snowmass Colorado）；`GET /WACV2019` → 404。确认旧稿"WACV ~2020+"准确。

**更早年份去哪了**：菜单和站内搜索均未提供 2012 年及更早的 CVPR/ICCV 入口；旧稿称此前只在 IEEE Xplore，本次未直接验证 IEEE Xplore（超出 CVF 站点勘察范围），但 CVF 侧确认"边界之外 = 404，站内无替代入口/无跳转提示"，与旧稿的 era 分段设计（D-012，2013 前→`ieee_xplore`）在**站点行为**层面自洽。

---

## 10. Bulk 替代线索 / arXiv 交叉

**[LIVE] arXiv 线索——非常强，且比预期更直接**：CVPR2023 列表页每个条目在有 arXiv 版本时，直接内嵌 `[<a href="http://arxiv.org/abs/{id}">arXiv</a>]` 链接（本次样本 1454/2353 = 62% 条目有此链接），**不需要访问详情页**、**不需要额外请求**，随列表页一次性拿到。同时每条目自带完整 BibTeX（含 `pages` 字段），这部分元数据比旧稿设想的"只有 pdf/html 路径"丰富得多。

**[DOC]（WebSearch，非站内请求）官方 bulk dump/API**：未找到 CVF 官方维护的批量下载 API 或数据集 dump。搜索命中的都是第三方/社区工具：
- GitHub `ElhamKhan859/CVF-Scrapper-Public`（Python 批量下载脚本，覆盖 WACV/ICCV/CVPR）
- GitHub `MarkHershey/arxiv-dl`（命令行下载器，同时支持 arXiv/NeurIPS/CVF/ECVA）
- Apify `automation-lab/cvf-papers-scraper`（付费云爬虫）
- Parse.bot 的非官方 API 封装

**[LIVE] 站内交叉验证**：`GET /sitemap.xml` → 404；`GET /robots.txt` → 404（见 §7）。站点本身没有暴露 sitemap、API 端点或结构化 bulk 入口的任何痕迹。**结论：不存在官方 bulk 通道，唯一稳定路径是"列表页 HTML 解析"（本报告 §2b 已给出选择器级证据），第三方工具本质也是做同样的事**。

---

## 附：本次请求清单（22 次，全部 openaccess.thecvf.com）

| # | 方法 | URL | 状态 | 用途 |
|---|---|---|---|---|
| 1 | GET | /robots.txt | 404 | §7 |
| 2 | GET | / | 302→/menu | §1 |
| 3 | GET | /menu | 200 | §1 |
| 4 | GET | /menu_other.html | 200 | §5(ECCV/ACCV) |
| 5 | GET | /CVPR2023 | 200 | §2a |
| 6 | GET | /CVPR2023?day=all | 200 | §2b 主数据 |
| 7 | GET | /content/CVPR2023/html/Ci_GFPose..._paper.html | 200 | §3 |
| 8 | HEAD | /content/CVPR2023/papers/Ci_GFPose..._paper.pdf | 200 | §4 |
| 9 | HEAD | /content/CVPR2023/supplemental/Ci_GFPose..._supplemental.pdf | 200 | §4 |
| 10 | GET | /CVPR2023_workshops/menu | 200 | §5 |
| 11 | GET | /CVPR2027 | 404 | §6 |
| 12 | GET | /CVPR2023_workshops/WAD | 200 | §5 |
| 13 | GET | /ICCV2022 | 404 | §1(双年制) |
| 14 | GET | /ECCV2024 | 404 | §5(证伪旧稿403) |
| 15 | GET | /ECCV2018 | 200 | §5 |
| 16 | GET | /CVPR2012 | 404 | §9 |
| 17 | GET | /WACV2019 | 404 | §9 |
| 18 | GET | /CVPR2013.py | 307→/CVPR2013 | §9 |
| 19 | GET | /sitemap.xml | 404 | §10 |
| 20 | GET | /CVPR2013 | 200 | §9 |
| 21 | HEAD | /CVPR2023?day=all | 200 | §8(HEAD支持) |
| 22 | GET | /CVPR2023?day=2023-06-20 | 200 | §2c |

## 未解决项 [UNRESOLVED]

- Supplemental 是否总是 PDF，还是也有 zip/视频等格式——仅验证 1 例，未广泛抽样。
- 限速阈值具体数值——未做压力测试（超出个人调研礼貌边界，故意不测）。
- IEEE Xplore 侧 2013 年前的可用性——不在 CVF 站点勘察范围内，未验证。
- CVPR2026 的 `_findings` / CVPR2022 的 `_demos` 等非常规子卷，其内部列表页结构是否与主会/workshop 一致——未展开测试，仅确认链接存在于 menu。
