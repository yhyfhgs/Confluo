"""Unpaywall adapter 包（design/adapters/aggregators.md §5.5；plan §4 T5）。

OA（开放获取）副本发现：按 DOI `GET /v2/{doi}?email=<addr>`，capabilities 仅
``RESOLVE``（无 ENUMERATE/SEARCH/FETCH——无搜索端点，必须先有 DOI 清单来自
crossref/dblp；元数据/全文取回归其余源，本 adapter 只定位 OA 位置）。

- `parse`：响应体 → `UnpaywallRecord` 的零网络解析（含 `url_for_pdf` 回退链）。
- `adapter`：`UnpaywallAdapter`（`SourceAdapter` 实现，含真实 HTTP 访问）。
- `report`：OA 命中率报告（T5 DoD 第二项）——对 DOI 清单做单 DOI GET 循环 →
  命中率统计 markdown（纯函数层，CLI 接线在 `cli.py` 的 `oa-report` 命令）。

**先决条款**：本包引入前，`obslog._SENSITIVE_KEYS` 已并入 `email`（阻止
`?email=<addr>` 明文入 jsonl 日志，aggregators.md §3 B-B4）。
"""
