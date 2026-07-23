"""SSRN adapter 包（design/adapters/ssrn.md；聚合元数据主路径，站点零接触）。

**元数据主路径零 `*.ssrn.com` 接触**（D-029 / AC-5.1a③ 红线）：SSRN 无官方 API、
站点本体 Cloudflare + 环境 TLS 双阻断（勘察 §2）——元数据全经第三方聚合 API：

- `DISCOVER`：**纯生成**零网络年桶（`buckets.year_buckets`，controller 发现①仲裁令
  2026-07-24：真实 Crossref `facet=created:*` 返 HTTP 400，原 §4.3 facet 方案不可实现
  → 改纯本地生成 1990..今年 逐年 `IssueRef`，零请求零 facet 依赖）。
- `ENUMERATE`：**消费扩展后的 `CrossrefAdapter`**（prefix `10.2139` + `created` 日期轴，
  nber.md §3.1 两轴扩展）产 `PaperStub` 流 → **后处理层**（`parse`）抽 abstract_id、
  增补 `(ssrn, abstract_id)` identifier（护栏拒非-`ssrn.` 中缀，计 `skipped_non_ssrn`）。
- `RESOLVE`：**landing-only 零网络**（`resolve_offline=True`）——纯构造 landing 引用、
  **不产 PDF asset**；全文交 pipeline unpaywall OA-fallback（勘察证实 landing-only，
  PDF 命中≈0，§4.4）。**无 `FETCH`**（模式 B 浏览器全文 defer Phase 6，D-029 案 B）；
  **无 `SEARCH`**（冻结协议无 `search()`）。

纯逻辑件（零网络，`parse`/`buckets`）与 `HttpClient`（经内部 `CrossrefAdapter`）组装成
`adapter.SsrnAdapter`。`*.ssrn.com` 域**永不注册、永不请求**（`domains=("api.crossref.org",)`）。
"""
