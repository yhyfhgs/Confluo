"""ACL Anthology adapter 包（design/adapters/acl-anthology.md；AC-2.5 验收载体）。

- `ids`：两代 anthology_id 解析（优先读 `<url>`）/构造/归一 + DOI 归一 + license 年份二分。
- `tree`：GitHub git-tree 清单解析（零网络，纯逻辑）——(venue,year)→文件名 解析、
  两代文件名候选构造、legacy 前缀读取。
- `parse`：`schema.rnc` 描述的 Collection→Volume→Paper XML 解析器 + Findings 跨文件
  join 的 volume 过滤 + `PaperStub` 字段映射。
- `adapter`：`AclAnthologyAdapter` 主体（git-tree 24h 进程内缓存、构造探测回退、
  raw 404→legal-empty 重分类、api.github.com 403→rate_limited 域级重分类）。
"""
