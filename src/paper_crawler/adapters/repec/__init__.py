"""RePEc adapter 包（design/adapters/aggregators.md §5.7；D-035；plan §4 T8）。

**enrich 通道，且是全仓库唯一的零网络源**：capabilities 空集（不进 `SourceAdapter`
冻结协议的枚举/取回语义，不参与 `crawler pull`），只经 duck-typed `enrich_batch(dois)`
（`adapter.EnrichmentSource` 协议）由 `crawler enrich --source repec` 驱动。与
openalex/s2 的**本质差异**：那两源按 DOI 在线批查，本源对**本地 bulk ReDIF 快照**做
join，`enrich_batch` **全程零网络**。

**"零网络"是结构事实、不是自律**（D-035 决策 3 的结构性要点）：唯一的网络动作——取
快照——落在 `scripts/repec_snapshot.py`（不入本包、不占门禁覆盖）。故本包内不存在任何
HTTP 客户端、不实现 `HttpClientConsumer`、`domains = ()`（结构性宣告无网络面），该性质
由 socket 猴补专测**正向锁定**（`tests/unit/test_repec_adapter.py`）而非靠约定。

- `parse`：ReDIF 记录切分与字段抽取、DOI↔handle 纯语法映射、manifest 解析、新鲜度
  计算——零网络零 IO 纯函数。
- `adapter`：`RepecAdapter`——快照惰性加载（进程内 dict 缓存）+ 本地 join + 未命中
  三分计数 + healthcheck。

**独家增值**：`Classification-JEL`（JEL 分类）与 `Publication-Status`（wp↔published 版本
关联）——crossref/openalex/nber.org 三路皆缺（[LIVE 2026-07-24]）。重叠字段
（title/authors/year/abstract）照常产出：`merge.SOURCE_PRIORITY` 给 repec 最低非-heuristic
位（`repec 1`），天然只补空，**无须实现特殊"只补不覆盖"逻辑**。

**零 HTML 硬红线**（AC-0.5 / AGENTS §6.3）：只走 ReDIF bulk 面，**绝不解析
`ideas.repec.org` / `econpapers.repec.org` 的 HTML 条目页**（哪怕其 robots 允许）——RePEc
官方明文强烈不建议爬 HTML 并设隐私红线（"Email addresses are released under no
circumstances"）。本包无任何 HTML 解析代码，该红线在结构上不可违反。
"""
