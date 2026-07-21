"""arXiv adapter 包（design/adapters/arxiv.md）。

本包当前只含零网络的纯逻辑件（T4）：

- `ids`：两代 arXiv id 的解析/归一（§3 identifier 归一裁决）。
- `buckets`：预印本虚拟月度桶生成（§3 discover_timeline 裁决）。
- `parse`：Query API Atom 与 OAI-PMH ListRecords 解析器（§3 字段映射）。

`SourceAdapter` 实现本体（`discover_timeline`/`enumerate_issue`/`resolve_assets`/
`fetch_asset`/`healthcheck`，含真实 HTTP 访问）留给 T5，不在本包当前版本。
"""
