"""OUP（Silverchair 平台）adapter 包（Phase 4 T4；design/adapters/oup-silverchair.md）。

`auth_gated`（HTTP + session cookie）平台 adapter，能力 RESOLVE|FETCH；enumerate 走
crossref（DOI 前缀 10.1093）。经 entry point 组 `paper_crawler.adapters` 注册
（`oup_silverchair = …:OupSilverchairAdapter`）。`parse` 为零网络落地页解析器。
"""

from paper_crawler.adapters.oup_silverchair.adapter import (
    CookieSupplier,
    OupSilverchairAdapter,
)

__all__ = ["CookieSupplier", "OupSilverchairAdapter"]
