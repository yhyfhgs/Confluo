---
title: Venue Catalog 总览与登记流程
status: approved
owner: fable5
updated: 2026-07-20
---

# Venue Catalog

> 这是 venue registry 的**文档形态**（人读清单）；实现阶段每条 venue 对应一个 `venues/**/*.yaml`（VenueSpec，见 [../design/02-plugin-framework.md](../design/02-plugin-framework.md)）。
> 本目录只列"抓什么、在哪个平台、什么访问级别"；"怎么抓"在 [../design/adapters/](../design/adapters/)。

## 清单文件

| 文件 | 覆盖 |
|---|---|
| [publishers-platforms.md](publishers-platforms.md) | **平台→adapter 映射总表（先读，D-002 骨架）** |
| [cs-ai-conferences.md](cs-ai-conferences.md) | CS/AI 顶会 |
| [ai-ml-journals.md](ai-ml-journals.md) | AI/ML 期刊（含 IEEE 系、JMLR 等） |
| [economics-journals.md](economics-journals.md) | 经济学顶刊+Field Top |
| [finance-journals.md](finance-journals.md) | 金融顶刊+量化+Field Top |
| [or-ms-journals.md](or-ms-journals.md) | 运筹/管理科学 |
| [preprint-platforms.md](preprint-platforms.md) | 预印本/WP 平台与订阅范围 |

## Tier 分级（范围控制，见 R5 风险缓解）

| Tier | 含义 | 处理 |
|---|---|---|
| **T1** | 必做核心（各领域公认 top） | 优先实现 + 完整 fixture + canary |
| **T2** | 已有平台 adapter，配置即得 | 写 VenueSpec 即可，随时纳入 |
| **T3** | 暂缓（历史过刊、边缘 field、需额外 adapter） | 登记但不排期 |

每条 venue 标注 tier；每个 Phase 只锁定该 Phase 的 T1/T2 范围，避免范围膨胀。

## Venue 登记流程（FR-01 落实）

1. 确认平台已有 adapter（查 publishers-platforms.md）；无则先走 adapter 新建流程（[../design/adapters/README.md](../design/adapters/README.md)）。
2. 在对应清单文件加一行（含下述字段）。
3. 实现阶段：创建 `venues/<field>/<id>.yaml`，`crawler venues lint` 通过。
4. `crawler timeline <id> --dry-run` 冒烟。
5. canary 样本注册（见 test-plan §canary）。

## 清单字段约定（各清单表格通用列）

`id` · `名称/别名` · `tier` · `kind`(journal/conf/preprint) · `平台/adapter` · `标识符`(ISSN/DBLP key/OpenReview id) · `metadata_source` · `fulltext_source` · `auth 级别` · `备注`

> ⚠ 说明：下列清单中的 ISSN/标识符为设计期整理，标 `⚠核验` 者需实现时用 Crossref/DBLP 复核后写入 VenueSpec。平台归属凡经本项目调研 [LIVE] 确认的标注来源。

## 覆盖范围声明（对齐需求）

- **领域**：CS/AI、经济学、金融、运筹/管理科学（需求明确的四域）；预印本额外限定 arXiv `cs.*/stat.ML/econ.*/q-fin.*` 与 SSRN `FEN/ERN` 等，不扩展到其他领域（需求§5 非目标）。
- **完整性目标**：各域 T1 期刊/会议的**全历史**时间轴（Crossref/DBLP 能及的范围）+ 每期清单 + 可选择下载。
