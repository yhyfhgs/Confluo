"""OpenReview adapter 包（design/adapters/openreview.md；AC-2.1/2.2 验收载体）。

- `venues`：ICLR 逐年届表常量（勘察 §2）+ `quirks.openreview_group_overrides` 合并（零网络）。
- `parse`：v1/v2 双套 note 解析器、groups 的 domain 版本判定、accepted 过滤、PaperStub 映射。
- `adapter`：`OpenReviewAdapter` 主体（含 403→auth_expired 重分类、token cookie 经注入 client）。
"""
