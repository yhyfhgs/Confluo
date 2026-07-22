"""conf 索引页 HTML 与卷 XML 的解析器（design/adapters/aggregators.md §5.2）。

零网络：输入已取回的响应 `bytes`，输出中间记录，供 `adapter.py` 消费（先例
arxiv/pmlr `parse.py` 的"纯函数、无 obslog"分工——跳过计数等观测信号通过返回
值的字段回传，由调用方决定是否记日志）。

两个解析目标：

- `parse_conf_index`：conf 索引页（`/db/conf/{acr}/`）HTML → 该会议已发现的
  卷链接集合。**href 扫描而非 CSS 选择器**——DBLP 页面的具体 class/结构未经
  本次实现的真实网络核验（AC-0.5：本次实现零真实网络，见 fixture 头注释），
  而"存在一个指向 `{slug}.html` 的可点击链接"是索引页存在的**功能性必要条件**
  （用户需要能点进每一届），比任何具体 CSS class 更不容易被站点改版打破。正则
  `_VOLUME_HREF_RE` 只要求 `href="…{slug}.html"`（相对或绝对 URL 皆可，取
  basename）+ `_SLUG_YEAR_RE` 要求 basename 以 4 位年份（可选跟 0-2 位小写
  字母后缀，覆盖 `icml2022a`/`icml2022b` 一类多卷情形）收尾——不要求 slug 前缀
  等于 venue 的 `acr`（`nips2023 404` 教训：conf/nips 的近届实际 slug 是
  `neurips2023` 而非 `nips2023`，前缀不等亦须被发现，见 aggregators.md §5.2）。
- `parse_volume_xml`：卷 XML（`/db/conf/{acr}/{slug}.xml`）→ `DblpVolume`
  （`inproceedings` 记录 + 本文档内 `proceedings` 容器 DOI 集合，供
  `to_paper_stub` 的护栏判定消费）。**双 schema 支持**——见下方专节。

**双 schema（2026-07-23 审查真实交叉验证修订，HIGH 阻断项修复）**：`enumerate_
issue`/`healthcheck` 在生产环境实际请求的 `/db/conf/{acr}/{slug}.xml`
**根元素不是 `<dblp>`**，而是 `<bht>`——`<bht key="db/conf/icml/icml2023.bht"
title="…"><h1>…</h1><dblpcites><r><proceedings>…</proceedings></r><r
style="ee"><inproceedings>…</inproceedings></r>…</dblpcites></bht>`：每条
`proceedings`/`inproceedings` 记录被多包一层 `<r>`（+ `<dblpcites>` 容器 +
一个人读 `<h1>` 标题，均非记录本身）。此形态由本次审查对
`https://dblp.org/db/conf/icml/icml2023.xml` 的真实在线请求核实（HTTP 200,
`content-type: application/xml`；捕获件见
`tests/fixtures/dblp/raw/11_volume_xml_bht_schema_full_real_icml2023.xml`，
1828 条 `inproceedings` + 1 条 `proceedings`，逐字节未改动）——**初版实现误把
公开批量导出 `dblp.xml.gz`（root=`<dblp>`、`proceedings`/`inproceedings` 为
根的直接子元素，无 `<r>`/`<dblpcites>` 包装）的 schema 当成了在线卷 XML 的
schema，导致 `enumerate_issue`/`healthcheck` 对任何真实卷 100% 解析失败**
（`root.tag != "dblp"` 早失败 + 直接子查询在 `<bht>` 下永远找不到记录）。
修复：①根元素校验放宽为 `{"bht", "dblp"}` 两者皆合法；②记录/容器查找从
`root.findall(...)`（仅直接子元素）改为 `root.iter(...)`（任意深度递归查找）
——对 `<dblp>` 根语义不变（记录本就是直接子元素，`iter` 与 `findall` 结果
一致），对 `<bht>` 根则正确穿透 `<dblpcites>/<r>` 两层包装。**两种 schema 都
真实存在生产用途**——`<bht>` 是 `enumerate_issue`/`healthcheck` 实际请求的
在线卷页 schema（本 adapter 当前唯一网络路径）；`<dblp>` 是 `dblp.xml.gz`
批量导出的 schema，本 adapter 当前不发起该请求，但解析器保留兼容——设计
文档（aggregators.md §5.2 "历史回填"一节）把 dump 列为未来 backfill 获取
路径的既定候选，兼容它可避免将来实现 dump 消费时重复踩同一坑，且保留成本
仅一行条件判断。

**`ee`→DOI 同源护栏**（aggregators.md §5.2 "ee→DOI 同源护栏"，A-C3 评审必落项）：
`to_paper_stub` 的 identifier 产出规则——

1. 只看**该 `inproceedings` 元素自身**的 `<ee>` 子元素；`<proceedings>`
   （卷/容器）元素的 `<ee>` **从不**被读作某篇论文的 DOI（结构性保证：
   `parse_volume_xml` 从不把 `<proceedings>` 转成 `DblpRecord`，也从不解析
   `<inproceedings>/crossref` 所引的 `<proceedings>` 条目）。
2. **纵深防御**：即使某条 `inproceedings` 自身的 `<ee>` 恰好是 doi.org 形式，
   若其归一化值与本文档内任一 `<proceedings>` 容器的 `<ee>` DOI 相同（即整卷
   DOI 意外出现在单篇记录上——如 Springer LNCS 全卷 DOI `10.1007/978-…`
   缺 `_N` 后缀误配到某篇论文），一律**不产 `(doi,…)` identifier**（改入
   `meta['ee']` 保留可追溯性，供人工核查异常源）——防止该容器 DOI 被多篇论文
   同时产出、经 identifier 全局唯一性把整卷论文误强合并成一条 paper（"毒性
   缺陷"，aggregators.md §5.2）。
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass

from paper_crawler.errors import CrawlerError, ErrorClass
from paper_crawler.ids import normalize_doi
from paper_crawler.types import PaperStub

# --- conf 索引页（HTML，卷 key 发现）------------------------------------------------------------

# `href="…/{slug}.html"`：捕获组允许相对或绝对 URL（后续取 basename），排除
# `"`/`?`/`#`（不匹配带查询串/片段的链接——真实 conf 索引页的规范卷链接不带这些）。
_VOLUME_HREF_RE = re.compile(r'href="([^"?#]+?)\.html"', re.IGNORECASE)
# basename 须以 4 位年份收尾（可选 0-2 位小写字母后缀，覆盖多卷/workshop 变体）；
# 年份收窄到 [1936, 2099] 做轻量合理性过滤（dblp 现存最早会议记录晚于此下界很多，
# 但不做更紧的假设——避免过度拟合、把未来真实但"意外早/晚"的年份误滤掉）。
_SLUG_YEAR_RE = re.compile(
    r"^(?P<prefix>[A-Za-z][A-Za-z0-9_-]*?)(?P<year>\d{4})(?P<suffix>[a-z]{0,2})$"
)
_MIN_YEAR = 1936
_MAX_YEAR = 2099


@dataclass(frozen=True)
class DblpVolumeLink:
    """索引页发现的一条卷链接：真实 slug（XML/HTML 页 basename）+ 解析出的年份。"""

    slug: str
    year: int


def parse_conf_index(data: bytes) -> tuple[DblpVolumeLink, ...]:
    """conf 索引页 HTML → 该会议已发现的卷链接（按出现顺序去重）。

    零匹配返回空 tuple——**合法态**（索引页存在但会议本届无收录/占位页），
    非错误（对齐 aggregators.md §5.2 "空卷（合法无记录）—非错误"精神，此处是
    索引层的同构情形）。
    """
    text = data.decode("utf-8", errors="replace")
    seen: set[str] = set()
    links: list[DblpVolumeLink] = []
    for match in _VOLUME_HREF_RE.finditer(text):
        href = match.group(1)
        slug = href.rsplit("/", 1)[-1]
        if not slug or slug in seen:
            continue
        year_match = _SLUG_YEAR_RE.match(slug)
        if year_match is None:
            continue
        year = int(year_match.group("year"))
        if not _MIN_YEAR <= year <= _MAX_YEAR:
            continue
        seen.add(slug)
        links.append(DblpVolumeLink(slug=slug, year=year))
    return tuple(links)


# --- 卷 XML（inproceedings 记录 + 容器 DOI 集合）--------------------------------------------------

_DOI_URL_RE = re.compile(r"^https?://(dx\.)?doi\.org/", re.IGNORECASE)


def _is_doi_url(raw: str) -> bool:
    """`raw`（已 strip）是否形如 `https://doi.org/…`（含 dx.doi.org、协议大小写不敏感）。"""
    return bool(_DOI_URL_RE.match(raw))


@dataclass(frozen=True)
class DblpAuthor:
    """`<author pid="…">Name</author>` 的解析产物；`pid` 缺失时为 None。"""

    name: str
    pid: str | None


@dataclass(frozen=True)
class DblpRecord:
    """单条 `<inproceedings>` 的解析产物（`to_paper_stub` 的输入）。"""

    key: str
    title: str
    authors: tuple[DblpAuthor, ...]
    year: int | None
    pages: str | None
    ees: tuple[str, ...]  # 该记录自身的全部 <ee> 原文，文档顺序
    crossref: str | None


@dataclass(frozen=True)
class DblpVolume:
    """一卷 XML 的解析产物：全部合法记录 + 本文档内 `<proceedings>` 容器 DOI 集合。"""

    records: tuple[DblpRecord, ...]
    container_dois: frozenset[str]  # 已 normalize_doi() 的容器/卷级 DOI（护栏判定用）
    skipped_missing_title: int  # 结构合法但缺 <title> 而被跳过的 <inproceedings> 数（观测用）


_VALID_ROOT_TAGS = frozenset({"bht", "dblp"})  # 见模块 docstring"双 schema"专节


def parse_volume_xml(data: bytes) -> DblpVolume:
    """卷 XML → `DblpVolume`。**接受两种根 schema**（模块 docstring"双 schema"
    专节）：`<bht>`（`/db/conf/{acr}/{slug}.xml` 在线卷页，记录嵌在
    `dblpcites/r` 两层包装内）与 `<dblp>`（`dblp.xml.gz` 批量导出，记录是根的
    直接子元素）——记录/容器查找统一用 `Element.iter(tag)`（任意深度递归），
    对两种根形态自动适配，无需按根 tag 分支。

    XML 语法错误、或根元素既非 `<bht>` 也非 `<dblp>`（结构漂移信号）→
    `ErrorClass.PARSE`。`<inproceedings>` 缺 `key` 属性（identifier 构造的
    硬依赖，"dblp 主锚点，恒有"）同样 `PARSE`——这是真实解析失败，不应被静默
    吞掉。缺 `<title>` 则**跳过该条记录**（计入 `skipped_missing_title`，不
    中断整卷解析）而非整卷失败：对齐 crossref 侧"空标题→跳过该记录+观测
    告警，宁缺勿污"的裁决（`paper.title` 是 06 数据模型的 NOT NULL 字段，
    占位符会污染 `title_norm` 弱信号匹配面，见 aggregators.md §5.1 裁决
    原文），dblp 一条记录的结构缺陷不应连累同卷其余上千条完好记录。
    """
    text = data.decode("utf-8", errors="replace")
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise CrawlerError(ErrorClass.PARSE, f"dblp volume xml is not well-formed: {exc}") from exc
    if root.tag not in _VALID_ROOT_TAGS:
        raise CrawlerError(
            ErrorClass.PARSE,
            f"dblp volume xml root element is {root.tag!r}, expected one of "
            f"{sorted(_VALID_ROOT_TAGS)!r} (structural drift)",
        )

    container_dois: set[str] = set()
    for proceedings_el in root.iter("proceedings"):
        for ee_el in proceedings_el.findall("ee"):
            ee_text = (ee_el.text or "").strip()
            if ee_text and _is_doi_url(ee_text):
                container_dois.add(normalize_doi(ee_text))

    records: list[DblpRecord] = []
    skipped_missing_title = 0
    for inproceedings_el in root.iter("inproceedings"):
        key = inproceedings_el.get("key")
        if not key:
            raise CrawlerError(
                ErrorClass.PARSE, "dblp <inproceedings> is missing the required 'key' attribute"
            )
        title = (inproceedings_el.findtext("title") or "").strip()
        if not title:
            skipped_missing_title += 1
            continue
        records.append(_parse_inproceedings(inproceedings_el, key=key, title=title))

    return DblpVolume(
        records=tuple(records),
        container_dois=frozenset(container_dois),
        skipped_missing_title=skipped_missing_title,
    )


def _parse_inproceedings(el: ET.Element, *, key: str, title: str) -> DblpRecord:
    authors = tuple(
        DblpAuthor(name=name, pid=author_el.get("pid"))
        for author_el in el.findall("author")
        if (name := (author_el.text or "").strip())
    )
    year_text = (el.findtext("year") or "").strip()
    year = int(year_text) if year_text.isdigit() else None
    pages = (el.findtext("pages") or "").strip() or None
    ees = tuple(text for ee_el in el.findall("ee") if (text := (ee_el.text or "").strip()))
    crossref = (el.findtext("crossref") or "").strip() or None
    return DblpRecord(
        key=key, title=title, authors=authors, year=year, pages=pages, ees=ees, crossref=crossref
    )


# --- PaperStub 转换（ee→DOI 护栏落地，模块 docstring）---------------------------------------------


def to_paper_stub(record: DblpRecord, container_dois: frozenset[str]) -> PaperStub:
    """把 `DblpRecord` 转成 `PaperStub`（aggregators.md §5.2/§6 字段映射裁决落地）。

    ``identifiers`` 恒含 ``(('dblp', record.key),)``；若该记录自身存在至少一个
    doi.org 形式且**不在** `container_dois` 中的 `ee`，追加 ``('doi', 归一值)``
    （取文档序中第一个满足条件者）。护栏拒收的 ee（doi.org 形式但命中容器 DOI）
    与其余非 DOI 形式的 ee 一律不产 identifier，改入 `meta['ee']`（可重复键，
    保留全部原文供人工核查/追溯）。
    """
    identifiers: list[tuple[str, str]] = [("dblp", record.key)]
    doi_identifier: str | None = None
    for ee in record.ees:
        if not _is_doi_url(ee):
            continue
        normalized = normalize_doi(ee)
        if normalized in container_dois:
            continue  # 护栏：容器/卷级 DOI 意外出现在单篇记录自身 ee 上，绝不产 identifier
        doi_identifier = normalized
        break
    if doi_identifier is not None:
        identifiers.append(("doi", doi_identifier))

    meta: list[tuple[str, str]] = []
    for ee in record.ees:
        if _is_doi_url(ee) and normalize_doi(ee) == doi_identifier:
            continue  # 已产出为 identifier 的那一条，不重复计入 meta
        meta.append(("ee", ee))
    if record.pages:
        meta.append(("pages", record.pages))
    if record.crossref:
        meta.append(("crossref", record.crossref))
    pid_pairs = [[author.name, author.pid] for author in record.authors if author.pid]
    if pid_pairs:
        # PaperStub.meta 值类型冻结为 str（aggregators.md §6 A-C1）：结构化内容
        # 一律 json.dumps 序列化，消费方自行 json.loads 反序列化。
        meta.append(("author_pids", json.dumps(pid_pairs)))

    return PaperStub(
        title=record.title,
        identifiers=tuple(identifiers),
        year=record.year,
        pub_date=str(record.year) if record.year is not None else None,
        abstract=None,  # DBLP 无摘要（aggregators.md §5.2），恒 null，留补充层回填
        authors=tuple(author.name for author in record.authors),
        meta=tuple(meta),
    )


__all__ = [
    "DblpAuthor",
    "DblpRecord",
    "DblpVolume",
    "DblpVolumeLink",
    "parse_conf_index",
    "parse_volume_xml",
    "to_paper_stub",
]
