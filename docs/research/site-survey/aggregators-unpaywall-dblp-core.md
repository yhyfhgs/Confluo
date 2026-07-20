---
title: 站点勘察：Unpaywall / DBLP / CORE / Google Scholar
status: approved
owner: fable5
updated: 2026-07-20
---

# 站点勘察 · OA 发现与索引层

> 来源：subagent 实测（含 live API 调用验证），2026-07-20。

## Unpaywall

- **API**：`https://api.unpaywall.org/v2/{doi}?email=<addr>`（实测 200）。无 key，仅需 email 参数。**100,000 次/天**。
- **仅 DOI 索引**：无关键词搜索端点（`/v2/search` 实测 500）——必须先有 DOI 清单（来自 Crossref），再逐个查 OA 副本。批量工具走 `POST /v2/dois`（≤1000 DOI/批）。
- **关键字段**：`is_oa`、`oa_status`(gold/green/hybrid/bronze/closed)、`best_oa_location.url_for_pdf`、`oa_locations[].version`(submitted/accepted/published)。
- **⚡ 组织变化（2025-09）**：OpenAlex 成为母品牌，"Unpaywall runs as a subroutine of the OpenAlex codebase"；**独立快照已停发**——bulk 场景直接用 OpenAlex 月度快照（免费 JSONL，超集）。Data Feed（日增量）为付费产品。
- **设计结论**：作 fetch 阶段的 OA fallback（no_entitlement 时找绿色版本）；版本字段映射到 Asset.version（accepted ≠ published，需标注）。

## DBLP

- **搜索 API**：`dblp.org/search/{publ,author,venue}/api?q=..&format=json|xml`，`h`≤1000、`f` 翻页。
- **⚡ 结构化卷目录（实测确认）**：`dblp.org/db/conf/{acr}/{acr}{year}.html` 换后缀 `.xml` 即得结构化 XML（icml2023.xml 实测 200：inproceedings 记录含作者 PID、页码、`ee` 官方外链）——**venue 枚举的首选机器接口**。注意各会 key 命名不规则（nips2023 404，需从 conf 索引页发现实际 key）。
- **限速**：无硬性数字；官方 FAQ 允许爬取，建议 1–2s 间隔；超限 429+Retry-After；**重活用 dump**。
- **Bulk**：`dblp.xml.gz` ~1.0GB（CC0）+ 2024-12 起月度 DOI 快照（`10.4230/dblp.xml.YYYY-MM-01`，Dagstuhl DROPS）。规模：866 万出版物 / 7140 会议 / 1900 期刊。
- **无全文无摘要**：`ee` 外链到官方渠道——定位层/导航层定位（与 D-012 一致）。

## CORE

- **API**：`api.core.ac.uk/v3/`（`/search/works`、`/works/{id}`）；免费 API key（email 注册）；免费档 **~5 单请求/10s**（学术机构可申请提额）。
- Elasticsearch 式查询（`field:value`、AND/OR/NOT、yearFrom/yearTo）；字段含 `downloadUrl`、`fullText`（已抽取纯文本）。
- 规模（2025-11）：431M 记录 / ~323M 带免费全文链接 / **46M 全文直接托管**。
- ⚠ 站点对自动化访问有 Cloudflare 防护（勘察时 403），API 数字为二手corroborated——实现期用真 key 复核。
- **设计结论**：次级 OA 兜底（Unpaywall 之后）；其直接托管的全文可救活死链 green OA。

## Google Scholar（确认不做自动化主源——R4/需求§5）

- 无官方 API；官方帮助页明言不提供 bulk 访问；ToS 禁自动查询；有对 SERP 供应商的诉讼记录；结果硬上限 1000 条/查询；CAPTCHA 激进。
- `scholarly` 库自认 search_pubs/citedby 会被封 IP，需代理层——脆弱依赖。
- 合法轻量替代：Scholar Alerts 邮件订阅（人工配置）；引文导出按钮（人工）。
- **设计结论**：系统内不出现 Scholar 自动化路径；文档在 09-search-filter 中给用户"Alerts 人工搭配"建议。
