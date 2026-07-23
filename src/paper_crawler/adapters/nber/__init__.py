"""NBER Working Papers adapter 包（design/adapters/nber.md；AC-5.2 载体）。

`open_access`/无认证档——元数据主干走 Crossref 前缀 `10.3386` 枚举（D-005，与
elsevier_sd 同构；venue `identifiers.crossref_prefix` 驱动 CrossrefAdapter 的 prefix
模式，nber.md §3.1）；全文=`www.nber.org/system/files` 匿名直链**仅 >18 月开放段**，
<18 月软门=`no_entitlement` 终态（**不绕过、不利用 3 篇/年匿名配额**）→ 既有 OA-fallback
天然兜底（auth-framework §8.1）。

- `parse`：DOI→series 号抽取 + 18 月开放窗离线谓词（红线核心）+ 全文 PDF URL 构造 +
  RSS `<item>` 反解（watch 通道设计，Phase 6 转主）+ 软门 HTML 嗅探判据（零网络纯函数）。
- `adapter`：`NberAdapter`——resolve（零网络 18 月窗 → 开放 PDF 计划 / <窗 no_entitlement 不产计划）
  + fetch（匿名直取 + `%PDF` 魔数双守卫，软门返非 PDF → no_entitlement 非 integrity）
  + healthcheck（w30000 PDF 首 chunk `%PDF` 结构性探测）。

**双域分桶**（§4）：`www.nber.org` 1 req/5s（domains[0]，www2 别名共享）；`back.nber.org`
（RSS/sitemap，Crawl-delay:10）**独立桶** 1 req/10s（`NberAdapter.BACK_RATE_POLICY`，
**不进 domains** 避 route_for alias 陷阱）。
"""
