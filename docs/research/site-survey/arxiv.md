---
title: 站点勘察：arXiv（全接口）
status: approved
owner: fable5
updated: 2026-07-20
---

# 站点勘察 · arXiv

> 来源：subagent 实测 + 官方文档核验（info.arxiv.org），核验日期 2026-07-20。
> 本文是原始勘察记录；设计结论见 [design/adapters/arxiv.md](../../design/adapters/arxiv.md)。

## 接口总表

| 接口 | Base URL | 认证 | 限速（官方） | 格式 | venue+时间过滤 | 全文 |
|---|---|---|---|---|---|---|
| Query API | `http://export.arxiv.org/api/query` | 无 | **1 req/3s，单连接**（ToU，全机器合计） | Atom 1.0 XML | `cat:` + `submittedDate:[A TO B]` | 返回 PDF 链接 |
| OAI-PMH | `https://oaipmh.arxiv.org/oai`（**2025-03 迁移**；旧 `export.arxiv.org/oai2` 301 跳转） | 无 | 同上 1 req/3s | OAI XML（`oai_dc`/`arXiv`/`arXivRaw`） | `set=`（archive 级）+ `from/until` | 否（仅元数据） |
| RSS | `https://rss.arxiv.org/rss/{cat}`（Atom 变体 `/atom/`） | 无 | 同上 | RSS 2.0 | 分类可 `+` 组合，单日快照，2000 条上限 | 否 |
| Kaggle bulk | `kaggle.com/datasets/Cornell-University/arxiv` | Kaggle 免费账号 | —（文件下载） | JSONL（~1GB 压缩） | 下载后按 `categories` 字段过滤 | 否（元数据，CC0，周更） |
| S3 bulk | `s3://arxiv`（requester-pays，us-east-1） | AWS 账号计费 | — | 月度 .tar（PDF ~2.7TB+，src ~2.9TB+，合计 ~9.2TB@2025-04） | 按月组织非按分类 | **是**（全量 PDF+LaTeX） |
| listing 页 | `arxiv.org/list/{cat}/{YYYY-MM}?skip=N&show=M`（show 最大 2000） | 无 | robots.txt **Crawl-delay: 15s** | HTML | 分类+年月 | 链接到 abs/pdf |
| abs/pdf | `arxiv.org/abs/{id}`、`arxiv.org/pdf/{id}`（`.pdf` 后缀可选） | 无 | 1 req/3s 口径 | HTML / PDF | 无（按 id 直取） | 是 |

## 关键机制

- **Query API 分页**：`max_results` ≤2000/次；翻页总量硬上限 **30000**（超出 HTTP 400）→ 大结果集必须用日期窗口切片。
- **字段前缀**：`ti/au/abs/co/jr/cat/rn/all`；布尔 `AND/OR/ANDNOT`；短语用引号；日期 `submittedDate:[YYYYMMDDTTTT TO YYYYMMDDTTTT]`（GMT）。
- **OAI-PMH**：官方明文"**preferred way to bulk-download or keep an up-to-date copy**"；resumptionToken **每日过期**；set 只到 archive 级（cs/stat/econ/q-fin），子分类需客户端过滤。
- **版本语义**：id 无版本后缀 = 最新版；`v{n}` 指定版本；RSS guid 形如 `oai:arXiv.org:{id}v{n}`；`arXivRaw` 前缀含完整版本史。
- **ID 两代**：2007-04 起 `YYMM.NNNNN`（2015-01 起序号 5 位）；此前 `archive.subject/YYMMNNN`（如 `hep-th/9901001`）——历史回填解析器必须兼容两代。
- **robots**：`arxiv.org` 允许 `/list /abs /pdf`（15s delay），禁 `/search /api` 等；`export.arxiv.org/robots.txt` 全禁通用爬虫（只应经文档化 API 访问）；页面明示 "Indiscriminate automated downloads are not permitted"。
- **S3 manifest**：`pdf/arXiv_pdf_manifest.xml` 含每 tar 的 MD5/首末 id/数量——可编程增量同步。

## 分类体系（本项目相关，已双源核验）

- **cs.\***（40 个）：重点 cs.AI、cs.LG、cs.CL、cs.CV、cs.IR、cs.GT、cs.MA、cs.NE、cs.DS、cs.CC、cs.CR、cs.RO、cs.SD、cs.SI…（全表 40 个见官方 taxonomy）
- **stat.\***（6）：**stat.ML**、stat.ME、stat.TH、stat.AP、stat.CO、stat.OT
- **econ.\***（3）：econ.EM（计量）、econ.GN（一般）、econ.TH（理论）
- **q-fin.\***（9）：q-fin.CP、q-fin.EC、q-fin.GN、q-fin.MF、q-fin.PM、q-fin.PR、q-fin.RM、q-fin.ST、q-fin.TR

## 对 adapter 设计的直接结论

1. 历史回填：Kaggle bulk（元数据）→ 需全文时 S3 或按清单限速逐篇；**绝不用 Query API 翻全量**（30000 上限+ToU）。
2. 增量订阅：OAI-PMH `from/until` 日收割（元数据主干）+ Query API 精确查询（用户 DSL）；RSS 仅作"今日速览"轻通道。
3. 限速器配置：`export.arxiv.org` 与 `oaipmh.arxiv.org` 域：1 req/3s、并发 1；`arxiv.org` listing：1 req/15s（robots）；PDF 下载归入 1 req/3s 口径。
4. 解析器需兼容两代 ID；版本号入库（`Asset.version`）。
