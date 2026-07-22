"""OUP（Silverchair 平台）落地页 HTML 解析器（design/adapters/oup-silverchair.md §3.1）。

**零网络**：输入已取回的落地页 HTML 文本，输出页内资产 URL（PDF / Supplementary）。
只用标准库 `html.parser.HTMLParser`（仓库无 bs4/lxml 依赖，见 pyproject.toml；同 cvf
先例的流式解析派）。

**PDF `file_id` 不可构造，必须从页面解析**（design §2/§3.1）：`article-pdf` 路径里的
`file_id`（如 `61701561`）是站点内部黑盒标识，无法由 DOI/vol/iss/page 推导。故本模块
**只抽取页面已给出的完整链接**，两路互补、`citation_pdf_url` meta 首选：

- **首选** `<meta name="citation_pdf_url" content="…article-pdf/…/{file_id}/{name}.pdf">`
  —— Highwire/Silverchair 标准引文 meta，全文页恒有；content 即完整 PDF URL。
- **回退** 页内含 `article-pdf` 的 `<a href>`（下载按钮锚点）—— meta 缺失时的兜底。

`silverchair_base` 共享基类（PDF/SI 抽取、entitlement 判定）在 oup 本 Phase 落地、
uchicago/mit_press 顺延后续 Phase 继承（design §8）——本 Phase 抽取逻辑先落在 oup 包内，
基类抽象待第二个 Silverchair 部署落地时再提取（避免单实现过早抽象）。

领域校验分工（cvf/openreview 先例）：本模块只做机械抽取（返回 URL 或 None/空列表）；
"OK 落地页解析出 0 PDF 链接 → PARSE（改版信号）"这类领域判定集中在 `adapter.py`
（单一权威来源，见 design §5 失败模式表）。
"""

from __future__ import annotations

from html.parser import HTMLParser
from urllib.parse import urljoin

# --- 解析目标标记（design §2/§3.1；比对一律小写化）------------------------------------------
_CITATION_PDF_META_NAME = "citation_pdf_url"
# article-pdf 路径片段（PDF 下载链接的判据，design §2 URL 模式 `/{code}/article-pdf/…`）。
_ARTICLE_PDF_MARKER = "article-pdf"
# Supplementary data 附件链接的判据（design §3.1④；保守只认显式 supplementary 片段，
# 避免在全文页误抓无关锚点——⚠ 合成 fixture 期的最小启发式，runbook 真样本到位后校准）。
_SUPPLEMENTARY_MARKER = "supplementary"


class _LandingPageParser(HTMLParser):
    """流式落地页解析状态机：捕 citation_pdf_url meta + article-pdf/supplementary 锚点。

    `convert_charrefs=True`：实体自动解码（本模块只读属性值，不累积可见文本，故实体
    解码对 href/content 无副作用）。属性名由 `HTMLParser` 统一小写化，值原样保留。
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.citation_pdf_url: str | None = None
        self.article_pdf_hrefs: list[str] = []
        self.supplementary_hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        adict = dict(attrs)
        if tag == "meta":
            name = (adict.get("name") or "").strip().lower()
            content = adict.get("content")
            # 首个 citation_pdf_url meta 生效（Silverchair 全文页恒单例；防御性只取首个）。
            if name == _CITATION_PDF_META_NAME and content and self.citation_pdf_url is None:
                self.citation_pdf_url = content.strip()
            return
        if tag == "a":
            href = adict.get("href")
            if not href:
                return
            lowered = href.lower()
            # supplementary 优先判：Silverchair 的 SI 附件也走 `article-pdf` 路径
            # （如 `…/article-pdf/…/{name}_supplementary_appendix.pdf`），故先认
            # supplementary 片段，避免 SI 锚点被误归到正文 PDF 桶。
            if _SUPPLEMENTARY_MARKER in lowered:
                self.supplementary_hrefs.append(href.strip())
            elif _ARTICLE_PDF_MARKER in lowered:
                self.article_pdf_hrefs.append(href.strip())


def _parse(html: str) -> _LandingPageParser:
    parser = _LandingPageParser()
    parser.feed(html)
    parser.close()
    return parser


def extract_pdf_url(html: str, *, base_url: str) -> str | None:
    """落地页 HTML → 完整 `article-pdf` URL（绝对化）；无命中返回 None（design §3.1②）。

    抽取优先级（**不构造 file_id**，只取页面已给出的完整链接）：
    ① `<meta name="citation_pdf_url">` 的 content（首选，全文页标准引文 meta）；
    ② 页内首个含 `article-pdf` 的 `<a href>`（回退）。

    绝对化经 `urljoin(base_url, url)`（`base_url` = 实际落地页 URL）：站点既有相对
    (`/qje/article-pdf/…`) 也有绝对 (`https://academic.oup.com/qje/article-pdf/…`)
    形态，urljoin 对二者中性（绝对原样返回、相对归一为绝对）。命中的 URL 仍以
    `article-pdf` 片段做形态校验，非该形态 → 视为未命中（防御 meta 指向非 PDF 资源）。
    """
    parser = _parse(html)
    candidate = parser.citation_pdf_url
    if candidate is None and parser.article_pdf_hrefs:
        candidate = parser.article_pdf_hrefs[0]
    if candidate is None:
        return None
    absolute = urljoin(base_url, candidate)
    if _ARTICLE_PDF_MARKER not in absolute.lower():
        return None
    return absolute


def extract_supplementary_urls(html: str, *, base_url: str) -> list[str]:
    """落地页 HTML → Supplementary data 附件 URL 列表（绝对化，去重保序；design §3.1④）。

    ⚠ **最小启发式**（合成 fixture 期）：只认 href 含 `supplementary` 片段的锚点——真实
    Silverchair 的 SI 区结构待 runbook 真样本到位后校准（design §8）。无命中返回空列表
    （非错误：多数文章无 SI）。
    """
    parser = _parse(html)
    seen: set[str] = set()
    urls: list[str] = []
    for href in parser.supplementary_hrefs:
        absolute = urljoin(base_url, href)
        if absolute not in seen:
            seen.add(absolute)
            urls.append(absolute)
    return urls


__all__ = ["extract_pdf_url", "extract_supplementary_urls"]
