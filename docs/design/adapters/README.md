---
title: Adapter 设计文档模板与索引
status: approved
owner: fable5
updated: 2026-07-20
---

# Platform Adapter 设计文档

> 每个 PlatformAdapter（见 [../02-plugin-framework.md](../02-plugin-framework.md)）在此目录有一篇设计文档，文件名=adapter_id（如 `elsevier-sd.md`）。
> 本文件：模板 + 索引 + 通用勘察清单。

## Adapter 设计文档模板

```markdown
---
title: Adapter 设计 · <平台名>
status: draft
owner: <name>
updated: YYYY-MM-DD
---

# Adapter · <adapter_id>

## 1. 定位
- family: open_access | auth_gated | aggregator
- 服务的 venue（链接 catalog 条目）
- capabilities: DISCOVER/ENUMERATE/RESOLVE/FETCH/SEARCH（勾选并说明）
- 元数据源/全文源分工（若本 adapter 只承担部分阶段）

## 2. 站点勘察摘要
- 关键 URL 模式（引用 research/site-survey 中的勘察记录 + 核验日期）
- 认证形态（none/free/subscription/institutional；SSO 类型）
- 反爬特征：Cloudflare？JS 渲染？robots.txt 关键条目？TDM 政策？
- 官方 API / bulk 数据可用性

## 3. 各阶段实现方案
- discover_timeline：数据来源、分页、增量
- enumerate_issue：清单来源、字段映射
- resolve_assets：PDF/SI 定位策略（direct/render/api）、entitlement 预检
- fetch_asset：httpx or browser？一次性 token 处理？
- search（若有）：查询编译

## 4. 限速与礼貌
- 默认 RatePolicy（数值 + 来源依据）
- robots/ToS 合规说明；任何例外的理由

## 5. 失败模式映射
- 站点特有的错误 → 统一 error_class（见 pipeline §4）的映射

## 6. Fixtures 与测试
- 三件套 fixture 清单（正常/空/异常页 URL）
- canary 样本（已知答案）
- 关联 AC 编号

## 7. 风险与维护
- 已知脆弱点、改版历史、监控要点
```

## 通用站点勘察清单（写 adapter 前必过）

1. URL 模式：timeline / issue / paper / pdf 四类 URL 的构造规律（含历史格式变化）；
2. 认证：匿名能到哪一步？付费/订阅边界在哪？SSO 类型？
3. 反爬：`curl robots.txt`（记录 AI-bot 条目、crawl-delay、TDM）；是否 Cloudflare（`cf-mitigated` 头）；是否 SPA（需渲染）；
4. 官方通道：有无 API / bulk / RSS / OAI-PMH（优先级高于爬页面）；
5. 稳定锚点：DOI 前缀、ISSN、DBLP key、OpenReview id 等跨年稳定标识；
6. 限速依据：官方明文的速率/TDM 政策；无则取保守默认并注明。

## Adapter 索引与状态

> `supported_since` 在实现后回填；现阶段全部为设计中。

| adapter_id | family | 主要 venue | 设计文档 | 状态 |
|---|---|---|---|---|
| arxiv | open_access | arXiv | [arxiv.md](arxiv.md) | review |
| ssrn | open_access | SSRN | [ssrn.md](ssrn.md) | review |
| openreview | open_access | ICLR、NeurIPS(评审) | [openreview.md](openreview.md) | review |
| pmlr | open_access | ICML、AISTATS、COLT、UAI、CoRL | [pmlr.md](pmlr.md) | review |
| cvf | open_access | CVPR、ICCV、WACV | [cvf.md](cvf.md) | review |
| acl_anthology | open_access | ACL、EMNLP、NAACL、COLING、EACL | [acl-anthology.md](acl-anthology.md) | review |
| neurips_proceedings | open_access | NeurIPS(正式) | [neurips-proceedings.md](neurips-proceedings.md) | review |
| aaai_ojs | open_access | AAAI、AIES | [aaai-ojs.md](aaai-ojs.md) | review（⚠ OAI-PMH/分页核验中） |
| acm_dl | open_access(D-013) | KDD、WWW、STOC、EC、SIGIR… | [acm-dl.md](acm-dl.md) | review |
| ieee_xplore | auth_gated | ICASSP、ICRA、ICDM、FOCS、IEEE 刊 | [ieee-xplore.md](ieee-xplore.md) | review（⚠ 勘察待并入） |
| aggregators | aggregator | Crossref/OpenAlex/DBLP/S2/Unpaywall | [aggregators.md](aggregators.md) | review |
| elsevier_sd | auth_gated | JFE、JME、JET、EJOR… | [elsevier-sd.md](elsevier-sd.md) | review（⚠ API 配额待并入） |
| wiley | auth_gated | JF、ECMA、RAND | [wiley.md](wiley.md) | review（⚠ TDM 端点待并入） |
| oup_silverchair | auth_gated | QJE、RFS、REStud、RF | [oup-silverchair.md](oup-silverchair.md) | review（⚠ 勘察待并入） |
| uchicago | auth_gated | JPE、JOLE | [uchicago.md](uchicago.md) | review（⚠ 平台栈待辨） |
| informs | auth_gated | MS、OR、MSOM、IJOC | [informs.md](informs.md) | review（⚠ TDM 待并入） |
| sage | auth_gated | POM | （待建，见 catalog 备注 SAGE 归属） | planned |
| aea | auth_gated | AER、AEJ 系 | （待建） | planned |
| econsoc | open_access | TE、QE、ECMA(部分) | （待建） | planned |
| nber | open_access | NBER WP | （待建） | planned |
| siam | auth_gated | SODA | （待建） | planned |
| cambridge / springer / mit_press / jstor / pm_research | auth_gated | JFQA、MathProg、REStat… | （待建） | planned |

> 首批（本设计阶段）撰写详设的代表性 adapter：arxiv、openreview、pmlr、acl_anthology、elsevier_sd、oup_silverchair、informs、ssrn、aggregators、ieee_xplore、acm_dl、cvf、neurips_proceedings、aaai_ojs。其余在对应 Phase 开工前补齐。
