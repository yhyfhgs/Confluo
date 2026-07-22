---
title: 站点勘察：Unpaywall / DBLP / CORE / Google Scholar
status: approved
owner: fable5
updated: 2026-07-22
---

# 站点勘察 · OA 发现与索引层

> 来源：subagent 实测（含 live API 调用验证），2026-07-20。
> **2026-07-22 增量复核（Phase 3 开工前）**：本文档就 DBLP robots/限速、CORE 限速数字、Unpaywall version 精度三处同步小修（以下正文内 `【2026-07-22 更正】` 标注）。跨源合并复核记录见 [metadata-apis.md#2026-07-22-增量复核phase-3-开工前](metadata-apis.md)。

## Unpaywall

- **API**：`https://api.unpaywall.org/v2/{doi}?email=<addr>`（实测 200）。无 key，仅需 email 参数。**100,000 次/天**。
- **仅 DOI 索引**：无关键词搜索端点（`/v2/search` 实测 500）——必须先有 DOI 清单（来自 Crossref），再逐个查 OA 副本。批量工具走 `POST /v2/dois`（≤1000 DOI/批）。
- **关键字段**：`is_oa`、`oa_status`(gold/green/hybrid/bronze/closed)、`best_oa_location.url_for_pdf`、`oa_locations[].version`。**【2026-07-22 更正】** version 实测为**全拼串** `submittedVersion`/`acceptedVersion`/`publishedVersion`（非「submitted/accepted/published」简写）；`best_oa_location.url_for_pdf` 可为 **null**（gold/publisher 场景 landing 页有、pdf 无——[LIVE] 复核 `10.1371/journal.pmed.0020124`：`is_oa:true`、`oa_status:"gold"`、`version:"publishedVersion"`、`url_for_pdf:null`、`oa_locations` 4 条）。映射须回退遍历 `oa_locations[]` 找带 pdf 项。
- **⚡ 组织变化（2025-09）**：OpenAlex 成为母品牌，"Unpaywall runs as a subroutine of the OpenAlex codebase"；**独立快照已停发**——bulk 场景直接用 OpenAlex 月度快照（免费 JSONL，超集）。Data Feed（日增量）为付费产品。
- **设计结论**：作 fetch 阶段的 OA fallback（no_entitlement 时找绿色版本）；版本字段映射到 Asset.version（accepted ≠ published，需标注）。

## DBLP

- **搜索 API**：`dblp.org/search/{publ,author,venue}/api?q=..&format=json|xml`，`h`≤1000、`f` 翻页。**【2026-07-22 更正】robots-disallowed，不用于自动化**：`dblp.org/robots.txt` 明写 `Disallow: /search`、`/search/publ`（[LIVE]）——本系统 venue 枚举**不走 search API**，只走 `/db/**` 结构化 XML + dump（下条）。
- **⚡ 结构化卷目录（实测确认）**：`dblp.org/db/conf/{acr}/{acr}{year}.html` 换后缀 `.xml` 即得结构化 XML（icml2023.xml 实测 200：inproceedings 记录含作者 PID、页码、`ee` 官方外链）——**venue 枚举的首选机器接口**。注意各会 key 命名不规则（nips2023 404，需从 conf 索引页发现实际 key）。
- **限速**：**【2026-07-22 更正】** 非「无硬性数字」——`robots.txt` 明写 **`Crawl-delay: 4`**（[LIVE]），限速固化为 **≥4s/req**（此前「1–2s FAQ 建议」作废）；超限 429+Retry-After；**重活用 dump**。robots 允许区：`/db,/pid,/pers,/rec,/xml`；`/rec/xml`（per-record XML）在禁区（`Disallow: /rec/{xml,bib,ris,nt,rdf}`）——单篇取用不走 `/rec/xml`。
- **Bulk**：`dblp.xml.gz` ~1.0GB（CC0）+ 2024-12 起月度 DOI 快照（`10.4230/dblp.xml.YYYY-MM-01`，Dagstuhl DROPS）。规模：866 万出版物 / 7140 会议 / 1900 期刊。
- **无全文无摘要**：`ee` 外链到官方渠道——定位层/导航层定位（与 D-012 一致）。

## CORE

- **API**：`api.core.ac.uk/v3/`（`/search/works`、`/works/{id}`、`/works/{id}/download`、`/recommend`）；免费 API key（email 注册）。**【2026-07-22 更正】** 限速为 **token 制**（非「~5 单请求/10s」）[DOCS]：未认证 **100 token/日·最多 10/分**；注册免费 **1,000 token/日·最多 25/分**；更高档 **5,000 token/日**。计费：简单查询 1 token、复杂（recommender/scroll/bulk）3–5 token。
- Elasticsearch 式查询（`field:value`、AND/OR/NOT、yearFrom/yearTo）；字段含 `downloadUrl`、`fullText`（已抽取纯文本）。
- 规模（2025-11）：431M 记录 / ~323M 带免费全文链接 / **46M 全文直接托管**。
- **【2026-07-22 更正】** 原「⚠ Cloudflare 防护（勘察时 403）」未复现：本次 `GET /docs/v3` → 200（Redoc HTML）、`GET /robots.txt` → 200（仅 Cloudflare content-signal 样板，无 `User-agent/Disallow/Crawl-delay` 指令），两路径均无挑战门/验证码。API 数字改为上述 [DOCS] token 制。**注**：CORE 属 Phase 3 五源范围外（development-plan 五源字面），本条仅清账，不实现。
- **设计结论**：次级 OA 兜底（Unpaywall 之后）；其直接托管的全文可救活死链 green OA。

## Google Scholar（确认不做自动化主源——R4/需求§5）

- 无官方 API；官方帮助页明言不提供 bulk 访问；ToS 禁自动查询；有对 SERP 供应商的诉讼记录；结果硬上限 1000 条/查询；CAPTCHA 激进。
- `scholarly` 库自认 search_pubs/citedby 会被封 IP，需代理层——脆弱依赖。
- 合法轻量替代：Scholar Alerts 邮件订阅（人工配置）；引文导出按钮（人工）。
- **设计结论**：系统内不出现 Scholar 自动化路径；文档在 09-search-filter 中给用户"Alerts 人工搭配"建议。
