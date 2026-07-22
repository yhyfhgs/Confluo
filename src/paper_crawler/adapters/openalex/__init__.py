"""OpenAlex adapter 包（design/adapters/aggregators.md §5.3；plan §2-5/§4 T6）。

**enrich 通道，非 pull 六阶段成员**：capabilities 空集（无 DISCOVER/ENUMERATE/RESOLVE/
FETCH/SEARCH——不进 `SourceAdapter` 冻结协议的枚举/取回语义，不参与 `crawler pull`）。
本包只经 duck-typed 可选接口 `enrich_batch(dois)`（`adapter.EnrichSource` 协议，立于
冻结协议之外，沿 `HttpClientConsumer`/`EmailConsumer` 先例）驱动，由 `crawler enrich`
CLI 调用：按 DOI 批量补摘要/OA 链接/topics，经 `MergeEngine.ingest` 回注既有 paper
（字段级来源优先级收敛天然补缺不覆盖）。

- `parse`：响应体 → `PaperStub` 列表的零网络解析（含 `abstract_inverted_index` 倒排
  索引重建、`meta.cost_usd` 提取）。
- `budget`：每日 credit 预算状态的原子 read-modify-write（`<config-home>/state/
  openalex-budget.json`，§4 伪代码落地）。
- `adapter`：`OpenAlexAdapter`——`enrich_batch` 真实网络实现 + 预算熔断 + healthcheck。

**key 可选**：匿名请求现状 [LIVE] 200（`meta.cost_usd` 仍计费但不拦截）；有 key 经
config 注入（`api_key` 查询参数）提升每日额度。healthcheck 侧另有更严格的口径——
未配置 key 时 `raise NotImplementedError`（`crawler canary` 现有语义显示 SKIP），
即使 enrich 本身匿名可用（见 `adapter.py` 模块 docstring 的取舍说明）。
"""
