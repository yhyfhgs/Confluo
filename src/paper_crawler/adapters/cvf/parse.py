"""CVF 列表页 HTML 解析器（design/adapters/cvf.md §2/§3.2）。

**零网络**：输入已取回的列表页 HTML 文本，输出中间记录 `RawEntry`。只用标准库
`html.parser.HTMLParser`（仓库无 bs4/lxml 依赖，见 pyproject.toml）——解析器按
[LIVE] 勘察给出的选择器级事实做**流式、按可见文本/属性分类**，不建完整 DOM 树：

- 标题/landing：``dt.ptitle > a`` —— 一个 ``<dt class="ptitle">`` 开始一个新条目，
  紧随其后的第一个 ``<a>`` 即标题锚点（取 href 为 landing、取文本为 title）。
- 作者：条目内所有 ``input[name=query_author]`` **或** ``input[name=query]`` 的
  ``value`` 属性（**不是** `<a href>`——[LIVE] §2b：作者是逐位 `<form
  class="authsearch">` + hidden input，取哪个都行，本解析器取 input value，元组
  顺序即页面顺序）。**双属性名是 era 差异，非笔误**：现代 `?day=all` 页用
  `query_author`（[LIVE] 站点勘察 §2b 转录）；flat 早年页（2013 起，含 CVPR2013/
  ICCV2013 双会核验）用 `query`——设计稿 §3.2 曾把 §2b 的 modern-only 观测误推广为
  跨 era 通用规则（site-survey §2b 本身准确措辞为"`?day=all` 真实列表页"小节内，
  未声称覆盖 flat 页），2026-07-22 复审经站内活取证伪并订正为双属性名兼容。
- 资产链接：条目内 `<a>` 标签按**可见文本**分类——``pdf``/``supp``/``arXiv`` 三个
  精确文本命中对应 href；其余锚文本（作者提交链接、bibtex 折叠开关等）忽略。这一
  分类不依赖 DOM 嵌套关系，只依赖"属于当前条目 + 锚文本命中"，对 CVF 两代路径规则
  （现代绝对路径 vs 2013 相对路径 `content_cvpr_2013/...`）天然中性。

`parse_list_page` 只做机械抽取（不做"标题非空"/"pdf href 必须存在"这类领域校验），
校验逻辑集中在 `to_paper_stub`（单一权威来源，先例 openreview `_parse_note` vs
`to_paper_stub` 的分工）。`has_day_all_link` 是入口探测的第二个判据（§3.2 "按解析
结果分支"：`dt.ptitle` 有 → flat 直解；无但有 `?day=all` 链接 → 二次取全集页）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

from paper_crawler.errors import CrawlerError, ErrorClass
from paper_crawler.types import PaperStub

# --- meta 键（adapter/resolve 共享的字面键名，design §3.2；非 adapter 私有前缀——
# pdf_url/supp_url/landing_url 是 resolve 直接消费的执行字段，非隐藏定位符）------------------
META_PDF_URL = "pdf_url"
META_SUPP_URL = "supp_url"
META_LANDING_URL = "landing_url"
META_ARXIV = "arxiv"

_DAY_ALL_RE = re.compile(r"[?&]day=all\b")
_ARXIV_ABS_MARKER = "/abs/"

# 作者 hidden input 的 name 属性：两代不同（2026-07-22 复审站内活取证实，见模块
# docstring）——modern `?day=all` 用 "query_author"，flat 早年页用 "query"。两个
# 名字互不重叠（无已知形态同时出现两者），接受任一即可，无需按 era 分支代码路径。
_AUTHOR_INPUT_NAMES = frozenset({"query_author", "query"})


# --- 中间记录 --------------------------------------------------------------------------------


@dataclass(frozen=True)
class RawEntry:
    """一条列表页条目的机械解析产物（未做领域校验，见模块 docstring）。"""

    title: str
    landing_href: str | None
    authors: tuple[str, ...]
    pdf_href: str | None
    supp_href: str | None
    arxiv_href: str | None


@dataclass
class _MutableEntry:
    """解析期间的可变累积态；`parse_list_page` 结束时冻结成 `RawEntry`。"""

    title: str = ""
    landing_href: str | None = None
    authors: list[str] = field(default_factory=list)
    pdf_href: str | None = None
    supp_href: str | None = None
    arxiv_href: str | None = None


def _normalize_ws(text: str) -> str:
    return " ".join(text.split())


def _has_class(attrs: dict[str, str | None], name: str) -> bool:
    raw = attrs.get("class") or ""
    return name in raw.split()


class _ListPageParser(HTMLParser):
    """流式列表页解析状态机（见模块 docstring 的分类规则）。"""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.entries: list[_MutableEntry] = []
        self._cur: _MutableEntry | None = None
        # 标题锚点捕获态：dt.ptitle 开始后等待紧随的第一个 <a>。
        self._awaiting_title_anchor = False
        self._capturing_title = False
        self._title_buf: list[str] = []
        # 通用锚点捕获态（pdf/supp/arXiv 按文本分类）。
        self._in_anchor = False
        self._anchor_href: str | None = None
        self._anchor_buf: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        adict = dict(attrs)
        if tag == "dt" and _has_class(adict, "ptitle"):
            self._cur = _MutableEntry()
            self.entries.append(self._cur)
            self._awaiting_title_anchor = True
            return
        if tag == "a":
            href = adict.get("href")
            if self._awaiting_title_anchor:
                self._awaiting_title_anchor = False
                self._capturing_title = True
                self._title_buf = []
                if self._cur is not None:
                    self._cur.landing_href = href
                return
            if self._cur is not None:
                self._in_anchor = True
                self._anchor_href = href
                self._anchor_buf = []
            return
        if tag == "input" and self._cur is not None and adict.get("name") in _AUTHOR_INPUT_NAMES:
            value = adict.get("value")
            if value:
                self._cur.authors.append(value)

    def handle_data(self, data: str) -> None:
        if self._capturing_title:
            self._title_buf.append(data)
        elif self._in_anchor:
            self._anchor_buf.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag != "a":
            return
        if self._capturing_title:
            self._capturing_title = False
            if self._cur is not None:
                self._cur.title = _normalize_ws("".join(self._title_buf))
            self._title_buf = []
            return
        if self._in_anchor:
            self._in_anchor = False
            text = _normalize_ws("".join(self._anchor_buf))
            href = self._anchor_href
            self._anchor_href = None
            self._anchor_buf = []
            if self._cur is None or not href:
                return
            if text == "pdf":
                self._cur.pdf_href = href
            elif text == "supp":
                self._cur.supp_href = href
            elif text == "arXiv":
                self._cur.arxiv_href = href


def parse_list_page(html: str) -> list[RawEntry]:
    """解析一整页列表 HTML（bare flat 或 `?day=all`，两代路径规则统一走此函数）。

    机械抽取——不校验字段完整性（那是 `to_paper_stub` 的职责）。0 条目是合法返回值
    （由调用方结合 `has_day_all_link` 判定属于"day-landing 页需二次取全集"还是
    "结构漂移"，见 design §3.2/§5）。
    """
    parser = _ListPageParser()
    parser.feed(html)
    parser.close()
    return [
        RawEntry(
            title=e.title,
            landing_href=e.landing_href,
            authors=tuple(e.authors),
            pdf_href=e.pdf_href,
            supp_href=e.supp_href,
            arxiv_href=e.arxiv_href,
        )
        for e in parser.entries
    ]


def has_day_all_link(html: str) -> bool:
    """页面是否含 `?day=all`（或 `&day=all`）链接——day-landing 页的判据（§3.2 分支②）。"""
    return _DAY_ALL_RE.search(html) is not None


# --- RawEntry → PaperStub（校验 + URL 绝对化 + identifier 构造，§3.2）-------------------------


def _stem_from_pdf_url(pdf_url: str) -> str:
    """绝对 pdf URL → stem（basename 去 `.pdf`）；不以 `.pdf` 结尾 → PARSE。

    naming-convention-agnostic：只看 basename，不关心是现代 `/content/CVPR2023/papers/...`
    绝对路径、2013 `content_cvpr_2013/papers/...` 相对路径（已被调用方 urljoin 绝对化），
    还是 workshop `/content/CVPR2023W/{code}/...`——三者对本函数是同一种输入形状。
    """
    path = urlparse(pdf_url).path
    name = path.rsplit("/", 1)[-1]
    if not name.endswith(".pdf"):
        raise CrawlerError(ErrorClass.PARSE, f"cvf pdf href 不以 .pdf 结尾: {pdf_url!r}")
    stem = name[: -len(".pdf")]
    if not stem:
        raise CrawlerError(ErrorClass.PARSE, f"cvf pdf href 的 stem 为空: {pdf_url!r}")
    return stem


def _arxiv_id_from_href(href: str) -> str:
    """`[arXiv]` href → 裸 id（`.../abs/{id}` 之后的部分）；不匹配形状则原样返回（防御性）。"""
    idx = href.find(_ARXIV_ABS_MARKER)
    if idx == -1:
        return href.strip()
    return href[idx + len(_ARXIV_ABS_MARKER) :].strip().rstrip("/")


def to_paper_stub(
    entry: RawEntry, *, base_url: str, canonical_dir: str, year: int | None
) -> PaperStub:
    """`RawEntry` → `PaperStub`（design §3.2 字段映射裁决逐字执行）。

    - URL 绝对化：`urljoin(base_url, href)`（`base_url` = 实际取回的列表页 URL；
      现代绝对路径 href 经 urljoin 原样返回，2013 相对路径经此归一为绝对——同一段
      代码处理两代，见 design §3.3 "消除 era 分支"）。
    - identifier：``('cvf', f"{canonical_dir}/{stem}")``——`canonical_dir` 由调用方
      （enumerate 上下文已知的 venue+year）构造传入、不解析；`stem` 取自 `[pdf]` href
      的 basename（两代都有 pdf 链接，不依赖详情页）。大小写原样保留（不 upper/lower）。
    - 缺 `[pdf]` href → `PARSE`（identifier 无法构造，属于结构性缺陷——两代 100%
      覆盖率是本设计的前提，见 §3.2 "两代都有 pdf 链接"）。
    - 标题为空 → `PARSE`（`dt.ptitle > a` 选择器失配的确定性信号）。
    - `abstract` 恒 `None`（列表页不含摘要，§3.2 "list-only abstract=None"裁决）。
    - meta：`pdf_url`/`supp_url`（存在时）/`landing_url`（存在时）/`arxiv`（存在时，
      线索、不产 identifier——防跨源早合并，先例 arxiv/openreview）。
    """
    if not entry.title:
        raise CrawlerError(ErrorClass.PARSE, "cvf 条目标题为空（dt.ptitle > a 选择器失配）")
    if not entry.pdf_href:
        raise CrawlerError(
            ErrorClass.PARSE, f"cvf 条目 {entry.title!r} 缺 [pdf] 链接（identifier 无法构造）"
        )

    pdf_url = urljoin(base_url, entry.pdf_href)
    stem = _stem_from_pdf_url(pdf_url)
    identifier_value = f"{canonical_dir}/{stem}"

    meta: list[tuple[str, str]] = [(META_PDF_URL, pdf_url)]
    if entry.landing_href:
        meta.append((META_LANDING_URL, urljoin(base_url, entry.landing_href)))
    if entry.supp_href:
        meta.append((META_SUPP_URL, urljoin(base_url, entry.supp_href)))
    if entry.arxiv_href:
        meta.append((META_ARXIV, _arxiv_id_from_href(urljoin(base_url, entry.arxiv_href))))

    return PaperStub(
        title=entry.title,
        identifiers=(("cvf", identifier_value),),
        year=year,
        abstract=None,
        authors=entry.authors,
        meta=tuple(meta),
    )


__all__ = [
    "META_ARXIV",
    "META_LANDING_URL",
    "META_PDF_URL",
    "META_SUPP_URL",
    "RawEntry",
    "has_day_all_link",
    "parse_list_page",
    "to_paper_stub",
]
