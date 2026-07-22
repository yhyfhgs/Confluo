"""Crossref 聚合元数据 adapter（期刊主干；design/adapters/aggregators.md §5.1）。

包结构（沿 arxiv 分层先例）：`parse`（零网络 JSON 解析/字段映射）+ `adapter`
（`SourceAdapter` 主体：discover/enumerate + healthcheck + 限速/错误映射）。DOI 归一
经顶层 `paper_crawler.ids.normalize_doi`（identifier 写入唯一入口，plan §2-1）。
"""
