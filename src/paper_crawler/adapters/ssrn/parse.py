"""SSRN 后处理层纯逻辑（design/adapters/ssrn.md §4.2/§4.4；**零网络**）。

消费扩展 `CrossrefAdapter`（prefix 10.2139 + created）产出的 `PaperStub` 流后加工——
全部纯函数，不发任何 HTTP，`*.ssrn.com` 零接触：

- **DOI→abstract_id 抽取**（`abstract_id_from_doi`）+ 增补 `(ssrn, abstract_id)`
  identifier（`augment_with_ssrn_id`）：DOI 形态 `10.2139/ssrn.{id}` 内嵌下载主键；
  crossref `to_paper_stub` 仅产 `(doi,)`，第二 identifier 由本层补（§4.2）。**护栏**：
  前缀 10.2139 下不匹配 `ssrn.` 中缀者 → 抽取返 None（调用方不增补、计 `skipped_non_ssrn`，
  防潜在非-SSRN DOI 误纳）。
- **landing URL 构造**（`landing_url`）：resolve 的 landing 引用（纯串，**不请求**，§4.4）。
- **econ/fin 主题近似过滤谓词**（`topic_field_matches`/`filter_stubs_by_topic`）：AC-5.1a②
  确定性过滤（固定输入→期望输出）。**近似**——信号取自 OpenAlex primary_topic.field
  （非 SSRN 真实 FEN/ERN 成员籍，§3 论据 2）；如实标注为近似，非精确子网枚举。
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import replace
from html import unescape
from urllib.parse import urljoin, urlsplit

from paper_crawler.ids import normalize_doi
from paper_crawler.types import PaperStub

# SSRN identifier scheme（下载主键；DOI 锚点之外的第二 identifier）。
SSRN_SCHEME = "ssrn"

# DOI→abstract_id：SSRN DOI 形态 `10.2139/ssrn.{abstract_id}`（内嵌下载主键）。
# `normalize_doi` 已剥 doi.org 前缀 + 小写化（§7 大小写/前缀矩阵）→ 中缀恒 `ssrn`、
# 前缀恒 `10.2139`。前缀 10.2139 下不匹配此形态者 = 潜在非-SSRN，返 None（护栏信号）。
_SSRN_DOI_RE = re.compile(r"^10\.2139/ssrn\.(\d+)$")

# landing 页下载按钮的 `href`（模式 B 同批解析；design/11 §4.4）——只认 `Delivery.cfm`
# 字面，值取到闭合引号为止。**不含**任何 token 构造知识：本正则是"读出站点给的链接"，
# 不是"拼一个链接"（红线 4 软门禁止依赖）。
_DELIVERY_HREF_RE = re.compile(
    r"href\s*=\s*(['\"])([^'\"]*Delivery\.cfm[^'\"]*)\1",
    re.IGNORECASE,
)

# econ/fin 主题近似过滤集（OpenAlex 顶层 field 规范名，ssrn.md §3）。SSRN 已多学科化
# （勘察：Engineering 22 万 / Medicine 7 万，非纯经济金融站）——本集 opt-in 收窄到 econ/fin
# 近似子集，**如实标注为近似**（过滤信号取自 OpenAlex field，非 SSRN 真实子网成员籍）。
ECON_FIN_FIELDS: frozenset[str] = frozenset(
    {
        "Economics, Econometrics and Finance",
        "Business, Management and Accounting",
    }
)

# 主题 field 值在 `PaperStub.meta` 里的键（OpenAlex enrich 回填约定，§4.5）。**当前
# openalex `_meta_of` 尚未产此键**（只产 is_oa/oa_status/oa_url/pdf_url）——primary_topic.field
# 的 enrich→meta 接线属后续（openalex adapter，本卡零触碰）；本谓词只对**已带该 meta 键**
# 的 stub 确定性判定（AC-5.1a② 固定输入→期望输出，不依赖任何在线 enrich）。
TOPIC_FIELD_META_KEY = "openalex_field"


def abstract_id_from_doi(doi: str) -> str | None:
    """SSRN DOI `10.2139/ssrn.{id}` → abstract_id（十进制串）；非此形态 → None（护栏信号）。

    输入经 `normalize_doi` 归一（剥 doi.org 前缀 + 小写化）后匹配
    ``^10\\.2139/ssrn\\.(\\d+)$``。前缀 10.2139 下的非 `ssrn.` 中缀 DOI（潜在非-SSRN）
    返 None → 调用方（adapter）不增补 `(ssrn)` identifier、计 `skipped_non_ssrn`（§4.2 护栏）。
    """
    match = _SSRN_DOI_RE.match(normalize_doi(doi))
    return match.group(1) if match else None


def doi_of_stub(stub: PaperStub) -> str | None:
    """取 stub 的 `doi` identifier 值（crossref `to_paper_stub` 恒产 (doi,)）；缺 → None。"""
    for scheme, value in stub.identifiers:
        if scheme == "doi":
            return value
    return None


def ssrn_id_of_stub(stub: PaperStub) -> str | None:
    """取 stub 的 `ssrn` abstract_id identifier 值（enumerate 后处理增补）；缺 → None。"""
    for scheme, value in stub.identifiers:
        if scheme == SSRN_SCHEME:
            return value
    return None


def augment_with_ssrn_id(stub: PaperStub, abstract_id: str) -> PaperStub:
    """增补 `(ssrn, abstract_id)` identifier（DOI 锚点保留，跨源强合并 D-007）。

    crossref `to_paper_stub` 仅产 `(doi,)`（§4.2 零改面）——下载主键 `(ssrn)` 由本层补。
    幂等：已含相同 `(ssrn, abstract_id)` 者原样返回（不重复增补）。
    """
    ident = (SSRN_SCHEME, abstract_id)
    if ident in stub.identifiers:
        return stub
    return replace(stub, identifiers=stub.identifiers + (ident,))


def landing_url(abstract_id: str) -> str:
    """SSRN landing 页 URL（**纯串构造，零网络——不请求**，§4.4 landing-only）。

    `papers.ssrn.com/sol3/papers.cfm?abstract_id={id}`——resolve 产此 landing 引用作观测，
    **不产可下载 PDF asset**（SSRN 无第三方 PDF 旁路；全文交 pipeline unpaywall OA-fallback）。
    构造 URL 串 ≠ 请求该 URL：本函数不发任何 HTTP（AC-5.1a③ 零 SSRN 接触不受影响）。
    """
    return f"https://papers.ssrn.com/sol3/papers.cfm?abstract_id={abstract_id}"


def delivery_url_from_landing(body: bytes, *, base_url: str) -> str | None:
    """从 landing 页 HTML 抽 `Delivery.cfm` 下载链接（**纯函数，零网络**；design/11 §4.4）。

    模式 B 同批约束的解析核：landing 页必须**在浏览器上下文内**打开一次，其下载按钮的
    `href` 就是携一次性 token 的 volatile URL。本函数只做"从已取回的 HTML 里读出该 href"，
    **不构造、不猜测** URL——按红线 4（软门禁止依赖），凭 abstract_id 拼 `Delivery.cfm`
    等于绕开站点自己的下载入口，是明令禁止的形态。

    规则：
    - 匹配 `href="…Delivery.cfm…"`（大小写不敏感；单/双引号皆可），取**首个**命中；
    - 相对路径经 `urljoin(base_url, href)` 绝对化（`base_url` = landing 的 `final_url`）；
    - **同源护栏**：绝对化后 host 必须与 `base_url` 同 host，跨站链接一律不采（页面若被
      改写/注入，绝不把下载导航送去任意第三方）；
    - 无命中 → `None`（调用方按 ssrn.md §6.2"无免费副本"映射 `no_entitlement`，不重试）。

    ⚠ **HTML 形态未核验**（design/11 §11 开放问题①/⑤；本机对 CF 前置域 TLS 阻断，
    [LIVE 2026-07-24]）：`Delivery.cfm` 的 href 形态取自 ssrn.md §2 [PRIOR-LIVE 2026-07-20]
    的 URL 记载，站点实际标记结构未取样。匹配失败是**如实的 `None`**（→ no_entitlement +
    可读 detail），不是静默兜底。
    """
    text = body.decode("utf-8", errors="replace")
    match = _DELIVERY_HREF_RE.search(text)
    if match is None:
        return None
    absolute = urljoin(base_url, unescape(match.group(2)))
    if urlsplit(absolute).hostname != urlsplit(base_url).hostname:
        return None
    return absolute


def topic_field_matches(field_value: str | None, allowed: frozenset[str] = ECON_FIN_FIELDS) -> bool:
    """确定性 econ/fin 主题谓词（AC-5.1a②）：field ∈ allowed → True；否则 False。

    `None`（未 enrich / 无 OpenAlex field）→ False：**近似过滤**无法确认 econ/fin 归属时
    诚实排除（opt-in 收窄语义——用户显式要 econ/fin 子集，不可确认者不纳）。精确大小写
    等值比对（OpenAlex 顶层 field 名为规范串），保证 CI 稳定的确定性输出。
    """
    return field_value is not None and field_value in allowed


def stub_topic_field(stub: PaperStub) -> str | None:
    """从 `stub.meta` 取 OpenAlex primary_topic.field 值（`TOPIC_FIELD_META_KEY`）；缺 → None。"""
    for key, value in stub.meta:
        if key == TOPIC_FIELD_META_KEY:
            return value
    return None


def filter_stubs_by_topic(
    stubs: Iterable[PaperStub], allowed: frozenset[str] = ECON_FIN_FIELDS
) -> list[PaperStub]:
    """按 econ/fin 主题近似过滤 stub 序列（确定性、保序；AC-5.1a②）。

    保留 `stub.meta` 的 OpenAlex field ∈ allowed 者；无 field 键者排除（近似过滤诚实语义，
    见 `topic_field_matches`）。**非**精确 FEN/ERN 子网枚举（聚合源无子网过滤维度，§3）。
    """
    return [stub for stub in stubs if topic_field_matches(stub_topic_field(stub), allowed)]


__all__ = [
    "ECON_FIN_FIELDS",
    "SSRN_SCHEME",
    "TOPIC_FIELD_META_KEY",
    "abstract_id_from_doi",
    "augment_with_ssrn_id",
    "delivery_url_from_landing",
    "doi_of_stub",
    "filter_stubs_by_topic",
    "landing_url",
    "ssrn_id_of_stub",
    "stub_topic_field",
    "topic_field_matches",
]
