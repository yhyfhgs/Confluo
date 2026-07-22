"""DOI 归一化（Phase 3 接口冻结件 plan §2-1 的最小先行实现）。

# T1 merge-engine 分支为权威版，合并时以彼为准。

`main` 在本文件落地时尚无 `src/paper_crawler/ids.py`（T1 合并引擎与 T4 dblp
adapter 并行开发，T1 是该文件的权威产出方——见 phase3-implementation-plan.md
§2-1 "DOI 规范化：`ids.normalize_doi()`…identifier 写入的唯一入口经过它
（crossref/unpaywall/dblp ee 回填共用）"）。T4 按该冻结语义先行落地一个最小版，
仅供 dblp adapter 的 `ee`→DOI 回填（aggregators.md §5.2）复用，避免 dblp 阻塞
等待 T1 落盘。**合并时若 T1 分支的实现/公开接口与本文件有出入，一律以 T1 分支
为权威、覆盖本文件**——本文件不应被反向要求 T1 迁就。

冻结语义（plan §2-1，逐字）：`normalize_doi()` = 小写化 + 剥
`https://doi.org/`（含 `http://`、`dx.doi.org`、协议大小写变体）前缀 +
`doi:` scheme 前缀。

`acl_anthology` 包内已有一个同名但语义更窄的 `normalize_doi`（
`adapters/acl_anthology/ids.py`：只剥 URL 前缀、不剥 `doi:`、不小写化，
§4/§9-★3 裁决专属该 adapter）——两者服务不同的冻结契约，互不覆盖、互不复用，
命名巧合不代表语义等价。
"""

import re

# `https://doi.org/…`、`http://…`、`dx.doi.org` 三种 URL 外壳，协议大小写不敏感。
_DOI_URL_PREFIX_RE = re.compile(r"^https?://(dx\.)?doi\.org/", re.IGNORECASE)
# 剥完 URL 外壳后可能残留的 `doi:` scheme 前缀（如 `doi:10.1145/xxx`）。
_DOI_SCHEME_PREFIX_RE = re.compile(r"^doi:\s*", re.IGNORECASE)


def normalize_doi(raw: str) -> str:
    """DOI 归一：剥 URL 外壳 + `doi:` scheme 前缀后小写化（plan §2-1 冻结语义）。

    顺序：先 `strip()` 空白，再剥 `https://doi.org/`（或 `dx.doi.org`，协议/
    大小写不敏感）URL 前缀，再剥可能残留的 `doi:` scheme 前缀，最后整体
    `lower()`。三步均为幂等操作（重复调用不变），故对已归一的输入调用本函数
    是安全的空操作。
    """
    text = raw.strip()
    text = _DOI_URL_PREFIX_RE.sub("", text)
    text = _DOI_SCHEME_PREFIX_RE.sub("", text)
    return text.lower()


__all__ = ["normalize_doi"]
