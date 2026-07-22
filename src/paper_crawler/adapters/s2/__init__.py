"""Semantic Scholar (S2) adapter 包（design/adapters/aggregators.md §5.4；plan §2-5/§4 T6）。

**enrich 通道，非 pull 六阶段成员**：capabilities 空集（无 DISCOVER/ENUMERATE/RESOLVE/
FETCH/SEARCH）。次级补充源——**生产必须 key**（无 key 实质不可用，D2 [LIVE]：无 key
单请求现症状是 404 "not found"，连已收录 DOI 亦然，非 429）；本包 `enrich_batch` 对
"无 key"的处置是**直接判定、不靠状态码推断**：未配置 key 时不发任何请求，直接
`raise CrawlerError(CONFIG)` 提示申请 key。

- `parse`：`POST /paper/batch` 响应体（与输入 id 同序对齐的数组，未命中位为 `null`）→
  `PaperStub` 列表的零网络解析。
- `adapter`：`S2Adapter`——`enrich_batch` 真实网络实现（1 req/s，有 key）+ healthcheck
  （无 key → `NotImplementedError`→canary SKIP，同 openalex 统一口径）。

**x-api-key 头凭证隔离**：有 key 时经**专属** `HttpClient`（携 `x-api-key` 头）注入，
绝不复用跨 adapter 共享的 client——否则该头会随其它域（crossref/dblp/...）的请求外泄
（沿 openreview token 专属 client 先例，`cli.py::_bind_openreview_token_client`）。
"""
