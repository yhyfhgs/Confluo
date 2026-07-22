"""跨源 identifier 归一工具（DOI 归一唯一入口，plan §2-1 / aggregators.md §6）。

# T1 merge-engine 分支为权威版，合并时以彼为准。

本文件是 `adapter/crossref` 分支为解除对 `ids.normalize_doi()` 的编译期依赖而
自建的**最小实现**：并行的 `feat/merge-engine`（T1）分支正在产权威版
`src/paper_crawler/ids.py`（DOI 归一是 identifier 写入的唯一入口，crossref /
unpaywall / dblp `ee` 回填 / openalex / s2 共用）。合并时以 T1 版为准；本文件
**不过度实现**（不做 DOI 语法校验、不剥查询串等——留待 T1 统一）。

约定（plan §2-1 冻结语义）：`normalize_doi` = 小写化 + 剥 `https://doi.org/`
（含 `http`/`dx.doi.org` 常见变体）与 `doi:` 前缀 + 首尾空白清理。归一后的
`(scheme='doi', value)` 全局唯一，是跨源强合并锚点（AC-3.1）。
"""

from __future__ import annotations

import re

# 剥离的 DOI URL/scheme 前缀（作用在已 `.strip().lower()` 的串上，故只需小写形态）：
#   https://doi.org/ · http://doi.org/ · https://dx.doi.org/ · http://dx.doi.org/ · doi:
_DOI_PREFIX_RE = re.compile(r"^(?:https?://(?:dx\.)?doi\.org/|doi:)")


def normalize_doi(raw: str) -> str:
    """DOI 归一：小写化 + 剥 `https?://(dx.)doi.org/`、`doi:` 前缀 + 首尾空白清理。

    归一后串是 `(doi, value)` identifier 的 value——写入前的唯一入口（plan §2-1）。
    空串/纯空白 → 空串（调用方负责判定"无 DOI"，本函数不抛异常）。
    """
    stripped = raw.strip().lower()
    return _DOI_PREFIX_RE.sub("", stripped)


__all__ = ["normalize_doi"]
