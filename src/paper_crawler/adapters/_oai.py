"""共享 OAI-PMH **信封层**核（★C 裁决，design/adapters/aaai-ojs.md §9）。

把 OAI-PMH 协议的"信封"部分——错误码表、`noRecordsMatch` 空态、墓碑遍历+计数、
`resumptionToken`、`ListRecords` 页形状——抽成与具体元数据 schema 无关的共享核，
供 arxiv（``arXiv`` 私有 schema）与 aaai_ojs（``oai_dc`` Dublin Core）各自的
**体层**解析器复用。信封层 100% 同构（勘察证实：两站错误码表逐条相同），把它抽
出避免"错误码表/墓碑逻辑"在两个 adapter 里重复漂移。

**分层边界**：本模块只认 OAI-PMH 协议形态（`<OAI-PMH>`/`<error>`/`<ListRecords>`/
`<record>`/`<header>`/`<metadata>`/`<resumptionToken>`），**不认**任何 `<metadata>`
内部的具体元数据 schema。"从 `<metadata>` 元素解析出一条中间记录"由调用方经
``record_parser`` 回调注入（arxiv 找 `<arXiv>`、aaai 找 `<oai_dc:dc>`）——回调也
负责"`<metadata>` 存在但缺本 schema 的体元素"这一**真实解析失败**（`PARSE`，非
墓碑）的判定，因为那是 schema 相关知识。

错误码 → `ErrorClass` 归类（design/adapters/arxiv.md §5 + 2026-07-22 勘误，两站逐条
相同）：

- ``noRecordsMatch`` → **非错误**：解析为空记录序列正常完成（空窗口/空桶/空届的
  OAI 合法响应；误归 `PARSE` 会使空态假故障）；
- ``badResumptionToken`` → `TRANSIENT`（token 过期，任务级重跑天然重建收割窗口）；
- ``badArgument`` / ``badVerb`` / ``cannotDisseminateFormat`` → `CONFIG`（我方请求
  构造缺陷，响亮停机，与 http.py 4xx→CONFIG 口径平行）；
- ``idDoesNotExist`` → `GONE`（单 id 查询场景，如 GetRecord canary 未命中）；
- 其余未知 code → `PARSE`（保守兜底）。

墓碑（``<header status="deleted">`` 或整条缺 ``<metadata>``）计入跳过数而非静默
丢弃——``OaiListPage.skipped_tombstones`` 让墓碑可观测（adapter 经 obslog 记 debug
事件）。任何 XML 语法错误（截断响应等）→ `PARSE`。
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass

from paper_crawler.errors import CrawlerError, ErrorClass

# --- 命名空间 --------------------------------------------------------------------------------

_OAI_NS = "http://www.openarchives.org/OAI/2.0/"


def oai(name: str) -> str:
    """OAI-PMH 协议命名空间下的限定标签名（供体层解析器定位 `<GetRecord>` 等外壳）。"""
    return f"{{{_OAI_NS}}}{name}"


# --- 页形状（信封层产物，参数化记录类型）-------------------------------------------------------


@dataclass(frozen=True)
class OaiListPage[T]:
    """一页 OAI-PMH `ListRecords` 的完整解析产物（供 adapter 单遍消费）。

    把"记录序列 + 续爬令牌 + 墓碑跳过数"三者在一次 XML 解析里一并给出，避免 adapter
    对同一份响应体重复 `ET.fromstring`，并让墓碑跳过数可观测。

    - ``records``：已解析、**未过滤**的中间记录（子分类/卷号客户端过滤是 adapter 的
      职责，不在解析层做——解析层只认 OAI 协议形态）。记录类型 ``T`` 由 ``record_parser``
      决定（arxiv 为 ``ArxivRecord``、aaai 为 ``AaaiRecord``）。
    - ``resumption_token``：下一页令牌；收割结束（无 token 或空 token 文本）为 None。
    - ``skipped_tombstones``：本页被跳过的墓碑记录数（``status="deleted"`` 或整条缺
      ``<metadata>`` 二者合计）。
    """

    records: tuple[T, ...]
    resumption_token: str | None
    skipped_tombstones: int


# --- 错误码表 --------------------------------------------------------------------------------

# OAI-PMH 顶层错误码 → ErrorClass（见模块 docstring）。noRecordsMatch 不在表内——它是
# 合法空态，由 raise_if_oai_error 直接 return 吸收。
_OAI_ERROR_CLASS: dict[str, ErrorClass] = {
    "badResumptionToken": ErrorClass.TRANSIENT,
    "badArgument": ErrorClass.CONFIG,
    "badVerb": ErrorClass.CONFIG,
    "cannotDisseminateFormat": ErrorClass.CONFIG,
    "idDoesNotExist": ErrorClass.GONE,
}


def raise_if_oai_error(root: ET.Element) -> None:
    """顶层 `<error>` → 抛对应 `CrawlerError`；`noRecordsMatch` 是合法空态，直接返回。

    供体层解析器在 `ListRecords`/`GetRecord` 两种响应上共用同一套错误识别（如 aaai
    的 GetRecord canary 依赖 ``idDoesNotExist`` → `GONE`）。
    """
    error_el = root.find(oai("error"))
    if error_el is None:
        return
    code = error_el.get("code", "")
    if code == "noRecordsMatch":
        return  # 空窗口/空桶/空届的合法响应，非错误
    message = (error_el.text or "").strip()
    error_class = _OAI_ERROR_CLASS.get(code, ErrorClass.PARSE)
    raise CrawlerError(error_class, f"OAI-PMH error code={code!r}: {message}", detail=code)


# --- ListRecords 单页解析（信封遍历，参数化体层回调）------------------------------------------


def parse_oai_page[T](data: bytes, *, record_parser: Callable[[ET.Element], T]) -> OaiListPage[T]:
    """解析一页 OAI-PMH `ListRecords`：一次解析给出记录 + 续爬令牌 + 墓碑跳过数。

    顶层 `<error>` 先于任何记录被识别：`noRecordsMatch` 视为空页正常返回（records 空、
    token None、skipped 0）；其余错误码按模块 docstring 归类抛出。每条非墓碑 `<record>`
    的 ``<metadata>`` 元素交 ``record_parser`` 解析为一条中间记录 ``T``——``record_parser``
    自负"缺本 schema 体元素 → `PARSE`"的判定（见模块 docstring 分层边界）。
    """
    root = fromstring(data)
    raise_if_oai_error(root)  # noRecordsMatch 在此被吸收为"不抛"，落到下方空页
    records, skipped = _iter_records(root, record_parser)
    return OaiListPage(
        records=tuple(records),
        resumption_token=resumption_token_from(root),
        skipped_tombstones=skipped,
    )


def _iter_records[T](
    root: ET.Element, record_parser: Callable[[ET.Element], T]
) -> tuple[list[T], int]:
    """遍历 `<ListRecords>` 下的 `<record>`，返回 (记录列表, 墓碑跳过数)。

    墓碑（``status="deleted"`` 或整条缺 ``<metadata>``）计入跳过数而非静默丢弃；存在
    ``<metadata>`` 的记录交 ``record_parser``——"``<metadata>`` 存在但缺本 schema 体
    元素"由 ``record_parser`` 判 `PARSE`（非墓碑）。调用前须已过 `raise_if_oai_error`。

    调用到这里时若顶层原本有 `<error>`，必为 `noRecordsMatch`（其余 code 已在
    `raise_if_oai_error` 响亮抛出）——这类响应体本就没有 `<ListRecords>`（错误码响应
    的合法形态），缺 `<ListRecords>` 是**预期之内**的合法空窗口/空桶，故仍返回空页。
    但若 `<error>` 与 `<ListRecords>` **两者皆无**（如误配成 `Identify` 端点响应体、
    代理返回了非预期页面等），说明响应形态本身不合规——**不是**合法空页，静默
    `return [], 0` 会把这类结构性异常伪装成"本页恰好没有记录"（S1 审计"OAI 空信封"
    发现），故改为响亮 `PARSE`。
    """
    list_records = root.find(oai("ListRecords"))
    if list_records is None:
        if root.find(oai("error")) is not None:
            return [], 0  # 已确认是 noRecordsMatch 吸收后的合法空态（见上）
        raise CrawlerError(
            ErrorClass.PARSE,
            "OAI-PMH ListRecords response has neither <error> nor <ListRecords> "
            "(malformed/unexpected response shape, not a legitimate empty page)",
        )
    records: list[T] = []
    skipped = 0
    for record in list_records.findall(oai("record")):
        header = record.find(oai("header"))
        if header is not None and header.get("status") == "deleted":
            skipped += 1
            continue
        metadata = record.find(oai("metadata"))
        if metadata is None:
            skipped += 1
            continue
        records.append(record_parser(metadata))
    return records, skipped


def resumption_token_from(root: ET.Element) -> str | None:
    """从 `ListRecords` 取 `resumptionToken` 文本；缺失或为空文本（收割结束）→ None。"""
    list_records = root.find(oai("ListRecords"))
    if list_records is None:
        return None
    token_el = list_records.find(oai("resumptionToken"))
    if token_el is None or token_el.text is None:
        return None
    token = token_el.text.strip()
    return token or None


# --- 共享 XML 小工具（信封与体层通用）---------------------------------------------------------


def fromstring(data: bytes) -> ET.Element:
    """`ET.fromstring` 的错误归一：任何 XML 语法错误（截断响应等）→ `PARSE`。"""
    try:
        return ET.fromstring(data)
    except ET.ParseError as exc:
        raise CrawlerError(ErrorClass.PARSE, f"malformed xml: {exc}") from exc


def normalize_ws(text: str) -> str:
    """空白规整化：折行/连续空白压成单空格（标题跨行、缩进 XML 的常见形态）。"""
    return " ".join(text.split())


def optional_text(parent: ET.Element, tag: str) -> str | None:
    """取 ``parent`` 下 ``tag`` 的规整化文本；缺失或纯空白 → None。"""
    raw = parent.findtext(tag)
    if raw is None:
        return None
    cleaned = normalize_ws(raw)
    return cleaned or None


def required_text(parent: ET.Element, tag: str, *, context: str) -> str:
    """取 ``parent`` 下 ``tag`` 的规整化文本；缺失/空白 → `PARSE`（记录级必需字段缺失）。"""
    value = optional_text(parent, tag)
    if value is None:
        raise CrawlerError(ErrorClass.PARSE, f"{context}: missing required element {tag!r}")
    return value


__all__ = [
    "OaiListPage",
    "fromstring",
    "normalize_ws",
    "oai",
    "optional_text",
    "parse_oai_page",
    "raise_if_oai_error",
    "required_text",
    "resumption_token_from",
]
