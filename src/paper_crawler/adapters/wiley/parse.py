"""Wiley TDM 路径的零网络纯函数（design/adapters/wiley.md §3；实现级）。

零网络、零 obslog（沿 s2/unpaywall/crossref parse.py 先例）。只用标准库 + `ids.normalize_doi`。
本模块承载三件纯逻辑，全部可假数据精确断言：

- `is_wiley_doi`：DOI 前缀路由（`10.1111` / `10.1002`，wiley.md §1）——归一后判前缀。
  **用于 enumerate/routing 层判定"该 DOI 是否 Wiley 平台"**（enumerate 本身走 crossref，
  本函数不发请求，只做前缀甄别）。**`10.3982` 已移除**（D-028）：该前缀归 Econometric Society
  自持、三刊共用（ECMA/TE/QE，仅后缀区分），裸前缀不可判平台/年代段——ECMA 过刊归属改由
  econsoc 运行时域名分段路由（econsoc.md §3.3），wiley 侧不持 10.3982 知识。
- `tdm_article_url`：按 DOI 构造 TDM 端点 URL（`GET api.wiley.com/onlinelibrary/tdm/v1/
  articles/{DOI}`，wiley.md §2 [LIVE 2026-07-23]）。DOI 内的 `/` 是路径分隔符保留
  （`quote(safe="/")`，同 unpaywall `_resolve_url` 先例）。
- `looks_like_pdf`：`%PDF-` 魔数轻校验（healthcheck 探针用；FETCH 阶段的**权威** `%PDF`
  校验归 pipeline，冻结分工，见 types.FetchIO docstring 与 arxiv 先例）。
"""

from __future__ import annotations

from urllib.parse import quote

from paper_crawler.ids import normalize_doi

# DOI 前缀（归一后小写；wiley.md §1）——Wiley Online Library 主用两段：10.1111（学会刊）/
# 10.1002（商业刊）。**`10.3982` 已移除（D-028，R0c [LIVE 2026-07-24] 证伪）**：该前缀归
# Econometric Society 自持、ECMA/TE/QE 三刊共用（仅 DOI 后缀 ECTA/TE/QE 区分刊），裸前缀
# `10.3982→wiley` 会把 TE/QE（econsoc OA）误路由、把当前段自营 ECMA 误交 Wiley TDM（大概率
# no_entitlement）。ECMA 过刊（doi.wiley.com）归属改由 econsoc 运行时域名分段路由承担
# （econsoc.md §3.3 方向 a）——wiley 侧不持 10.3982；is_wiley_doi 单入参无域名/年代信息、
# 无法判过刊段，取移除非收窄。
_WILEY_DOI_PREFIXES: tuple[str, ...] = ("10.1111/", "10.1002/")

# TDM 端点前缀（wiley.md §2；R0 [LIVE 2026-07-23] 端点活验）。
_TDM_ENDPOINT = "https://api.wiley.com/onlinelibrary/tdm/v1/articles/"

# PDF 魔数（RFC/ISO 32000：文件以 `%PDF-` 起）。
_PDF_MAGIC = b"%PDF-"


def is_wiley_doi(doi: str) -> bool:
    """`doi` 归一后是否落在 Wiley 平台 DOI 前缀（`10.1111`/`10.1002`，wiley.md §1）。

    归一经 `ids.normalize_doi`（剥 `https://doi.org/`/`doi:` 前缀 + 小写化），故对带 URL
    前缀或大小写混写的输入同样正确判定。空串/非 Wiley 前缀 → False。**`10.3982` 不再命中**
    （D-028）：归 Econometric Society、经 econsoc 域名分段路由，非 Wiley 裸前缀面。
    """
    normalized = normalize_doi(doi)
    return any(normalized.startswith(prefix) for prefix in _WILEY_DOI_PREFIXES)


def tdm_article_url(doi: str) -> str:
    """构造 TDM 全文端点 URL：`api.wiley.com/onlinelibrary/tdm/v1/articles/{DOI}`（wiley.md §2）。

    `doi` 先归一（与全库 identifier 单一同源，`ids.normalize_doi`），再 `quote(safe="/")`
    保留 DOI 内的 `/`（DOI 后缀常含斜杠，是路径的一部分而非需转义的分隔符——同 unpaywall
    `_resolve_url` 先例），其余不安全字符（空格/括号等罕见 DOI 字符）转义。
    """
    normalized = normalize_doi(doi)
    return f"{_TDM_ENDPOINT}{quote(normalized, safe='/')}"


def looks_like_pdf(data: bytes) -> bool:
    """`data` 是否以 `%PDF-` 魔数起（healthcheck 探针轻校验）。

    **非** FETCH 阶段的权威校验——落盘 PDF 的 `%PDF` 权威校验归 pipeline（冻结分工，
    types.FetchIO docstring / arxiv fetch_asset 先例）；本函数只供 healthcheck 探针判定
    "TDM token 连通且返回 PDF"这一 canary 信号。
    """
    return data.startswith(_PDF_MAGIC)


__all__ = ["is_wiley_doi", "looks_like_pdf", "tdm_article_url"]
