"""DBLP adapter 包（design/adapters/aggregators.md §5.2；会议元数据主干，T4）。

`SourceAdapter` 实现（`discover_timeline`/`enumerate_issue`/`healthcheck`）与
零网络纯解析逻辑（`parse`）拆分同 arxiv/pmlr 先例。DBLP capabilities 恒为
``DISCOVER | ENUMERATE``（无 SEARCH——`/search/**` 是 robots 禁区；无
RESOLVE/FETCH——聚合源不下载全文，见 aggregators.md §1/plan §2-3）。
"""
