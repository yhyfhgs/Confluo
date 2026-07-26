r"""RePEc 零网络纯逻辑（design/adapters/aggregators.md §5.7；D-035 决策 3/4）。

无网络、无文件 IO、无副作用：ReDIF 记录切分与字段抽取、DOI↔handle 纯语法映射、
`manifest.json` 解析、快照新鲜度计算。只用标准库（`re`/`json`/`datetime`）——不引第三方
（沿 `nber/parse.py`、`crossref/parse.py` 的「stdlib 解析」先例）。

## ReDIF 格式判读（[未实测] 与 [LIVE] 分离标注）

**[LIVE 2026-07-26 探针]** 字段名 `Classification-JEL`（`nbr:nberwo:35506` = `D1; J13; J15`）
与 `Publication-Status` 均在 bulk ReDIF 面确证。**其余形态属实现期判读**：本模块按 ReDIF
规范的通用形态解析，未经上游文件实测（T8-bulk 归 T19，本模块由自造 fixture 驱动）：

- **记录边界＝`Template-Type:` 行**（规范定义的记录起始标记），**不用空行作边界**——摘要
  正文内出现空行（段落分隔）是常态，用空行切分会把一条记录腰斩、丢掉后半截字段。
- **字段名大小写不敏感**（规范允许），归一为小写键比对。
- **续行**：不匹配 `Name: value` 形态的行视为上一字段的续行，按空格拼接（摘要多行折行的
  常见形态）。**续行跨越空行继续**——空行是值内部的段落分隔而非字段终止符；折叠后段落间距
  收敛为单空格（`PaperStub.abstract` 是单值 `str`，本层不保留排版）。
- **可重复字段**：`Author-Name` 逐条累积成有序元组；其余字段取**首次出现**（后续同名视为
  重复声明，不覆盖——保守，避免上游重复块把首条正确值挤掉）。

## DOI↔handle 映射边界（唯一可靠面＝NBER 语法映射）

`10.3386/w{n}` / `10.3386/t{n}` → `RePEc:nbr:nberwo:{n}`，**零模糊匹配、零启发式**，series
号归一复用 `adapters/nber/parse.py::series_id_from_doi`（单一权威源，不复制正则）。

**`t` 系列落哪个 series 段 [未实测]**（D-035 决策 4 / R2 §2.2-2 标 [推断]，明文"不作依据"）：
本模块按 `w`/`t` 同落 `nberwo` 构造，但**不把该推断固化为事实**——快照内查无该 handle 时
计入"覆盖缺口"(b) 而非静默丢弃（见 `MissKind`）。T19 实测若证伪，**按实测收窄**（改为只映射
`w`），不按推断扩张。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from paper_crawler.adapters.nber import parse as nber_parse
from paper_crawler.errors import CrawlerError, ErrorClass
from paper_crawler.types import PaperStub

# --- ReDIF 词法 -------------------------------------------------------------------------------

# `Name: value`——名以字母开头，含字母/数字/连字符（ReDIF 字段名形态，如 `Classification-JEL`）。
_FIELD_RE = re.compile(r"^([A-Za-z][A-Za-z0-9-]*)[ \t]*:[ \t]*(.*)$")
# 记录起始标记（大小写不敏感）。规范定义的边界，非空行——摘要内空行是常态。
_TEMPLATE_TYPE_KEY = "template-type"
# JEL 串分隔符：探针实测形态 `D1; J13; J15`；逗号变体一并容忍（上游多源汇聚，写法不齐）。
_JEL_SPLIT_RE = re.compile(r"[;,]")
# 单个 JEL 码形态（字母 1-2 位 + 可选数字 1-2 位，如 `D1`/`J13`/`C`）。不合形态的碎片丢弃，
# 避免把 "and"、"see also" 之类的自由文本当成分类码入库。
_JEL_CODE_RE = re.compile(r"^[A-Z]{1,2}[0-9]{0,2}$")
# `Creation-Date` 年份抽取：`2022-05` / `2022-05-01` / `2022` 均取前四位年（ReDIF 日期精度不齐）。
_YEAR_RE = re.compile(r"(\d{4})")

# NBER archive/series 段。`t` 系列同落 `nberwo` 属 [未实测] 推断——见模块 docstring。
_ARCHIVE = "nbr"
_SERIES = "nberwo"
_HANDLE_PREFIX = f"RePEc:{_ARCHIVE}:{_SERIES}:"


class MissKind(StrEnum):
    """`enrich_batch` 未命中的三种成因（D-035 决策 4「未命中三分观测」，审计 S1 原则）。

    openalex/s2 的"未命中"只有一种含义（上游没这条），故此三分是 repec 专有的契约要求
    ——三类**各有计数并进摘要行**，不静默合并为一个"没查到"。
    """

    UNADDRESSABLE = "unaddressable"  # (a) DOI 非 10.3386 前缀 ⇒ 结构性不可寻址（非缺陷）
    MISSING_HANDLE = "missing_handle"  # (b) 前缀符但快照内无该 handle ⇒ 覆盖缺口
    NO_JEL = "no_jel"  # (c) handle 命中但无 Classification-JEL ⇒ 增值为空


@dataclass(frozen=True)
class RedifRecord:
    """一条 ReDIF-Paper 记录的解析结果（字段子集——只取本通道消费得到的面）。"""

    handle: str
    title: str
    authors: tuple[str, ...] = ()
    year: int | None = None
    abstract: str | None = None
    jel: tuple[str, ...] = ()
    publication_status: str | None = None


@dataclass(frozen=True)
class SnapshotFile:
    """`manifest.files[]` 一项：原样落盘的 ReDIF 文件名 + 字节数 + sha256。"""

    name: str
    bytes: int
    sha256: str


@dataclass(frozen=True)
class SnapshotManifest:
    """`<config-home>/state/repec/manifest.json`（D-035 决策 3 冻结的快照元数据）。

    **文件名不预设**（决策 3 明文"不预设文件名"）：加载器按 `files[].name` 遍历，
    上游是单大文件还是逐条文件由取快照时实测决定，本契约只认 manifest 的记账。
    """

    schema: int
    archive: str
    series: tuple[str, ...]
    mirror: str
    source_urls: tuple[str, ...]
    fetched_at: str
    files: tuple[SnapshotFile, ...]
    record_count: int


# --- ReDIF 解析 -------------------------------------------------------------------------------


def _iter_raw_records(text: str) -> list[list[tuple[str, str]]]:
    """按 `Template-Type:` 边界切分，产出每条记录的 `(小写字段名, 值)` 有序列表。

    续行（不匹配 `Name: value` 的非空行）拼接进上一字段，**跨空行继续**——空行是值内部的
    段落分隔而非字段终止符，`Template-Type:` 才是唯一的记录边界（见模块 docstring）。
    `Template-Type:` 之前的前言（archive 说明等）整体丢弃。
    """
    records: list[list[tuple[str, str]]] = []
    current: list[tuple[str, str]] | None = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue  # 空行：既不切记录、也不终止续行
        match = _FIELD_RE.match(line)
        if match is not None:
            key = match.group(1).lower()
            value = match.group(2).strip()
            if key == _TEMPLATE_TYPE_KEY:
                current = []
                records.append(current)
                continue
            if current is None:
                continue  # Template-Type 之前的前言，丢弃
            current.append((key, value))
            continue
        # 非字段形态 → 上一字段的续行（空格折叠）
        if current:
            last_key, last_value = current[-1]
            current[-1] = (last_key, f"{last_value} {line}".strip())
    return records


def _first(fields: list[tuple[str, str]], key: str) -> str | None:
    """取首次出现的字段值（后续同名不覆盖，见模块 docstring）；缺失/空白 → None。"""
    for name, value in fields:
        if name == key:
            stripped = value.strip()
            return stripped or None
    return None


def _all(fields: list[tuple[str, str]], key: str) -> tuple[str, ...]:
    """取全部同名字段值（有序，去空白空值）——`Author-Name` 等可重复字段。"""
    return tuple(value.strip() for name, value in fields if name == key and value.strip())


def parse_jel(raw: str) -> tuple[str, ...]:
    """`Classification-JEL` 原串 → 归一 JEL 码元组（探针实测形态 `D1; J13; J15`）。

    分号/逗号切分 → 去空白 → 大写 → 只保留合形态码（`_JEL_CODE_RE`），保序去重。不合形态
    的碎片（自由文本、说明性词）**丢弃而非入库**——JEL 是受控词表，宁缺毋滥。
    """
    seen: dict[str, None] = {}
    for piece in _JEL_SPLIT_RE.split(raw):
        code = piece.strip().upper()
        if code and _JEL_CODE_RE.match(code):
            seen.setdefault(code, None)
    return tuple(seen)


def parse_year(raw: str) -> int | None:
    """`Creation-Date` 串 → 年份 int（取首个四位数）；无四位数 → None。"""
    match = _YEAR_RE.search(raw)
    return int(match.group(1)) if match else None


def parse_redif(data: bytes | str) -> tuple[RedifRecord, ...]:
    """ReDIF 字节/文本 → `RedifRecord` 元组。**无 handle 或无 title 的记录跳过**。

    跳过口径与 crossref「无 DOI 跳过」、nber RSS「无 guid 跳过」同源：没有稳定身份
    （handle）或没有标题（`PaperStub.title` 必填）的记录不产 stub，**不是异常**——上游
    bulk 文件里混入 `ReDIF-Archive`/`ReDIF-Series` 模板块是正常现象，它们本就无 handle
    形态的论文身份。字节按 UTF-8 解码，非法字节 `replace`（上游历史条目编码不齐，
    响亮失败换不来更多信息，且会让一个坏字节炸掉整份快照）。
    """
    text = data.decode("utf-8", errors="replace") if isinstance(data, bytes) else data
    records: list[RedifRecord] = []
    for fields in _iter_raw_records(text):
        handle = _first(fields, "handle")
        title = _first(fields, "title")
        if not handle or not title:
            continue
        jel_raw = _first(fields, "classification-jel")
        creation = _first(fields, "creation-date")
        records.append(
            RedifRecord(
                handle=handle,
                title=title,
                authors=_all(fields, "author-name"),
                year=parse_year(creation) if creation else None,
                abstract=_first(fields, "abstract"),
                jel=parse_jel(jel_raw) if jel_raw else (),
                publication_status=_first(fields, "publication-status"),
            )
        )
    return tuple(records)


# --- DOI↔handle 纯语法映射 --------------------------------------------------------------------


def handle_from_doi(doi: str) -> str | None:
    """`10.3386/w{n}` / `10.3386/t{n}` → `RePEc:nbr:nberwo:{n}`；非此形态 → None。

    series 号归一**复用** `nber.parse.series_id_from_doi`（单一权威源，不复制正则）：大小写
    不敏感、非 NBER 前缀/book chapter/畸形 DOI 一律 None ⇒ 调用方计 `MissKind.UNADDRESSABLE`
    （结构性不可寻址，非缺陷）。`t` 系列同落 `nberwo` 属 [未实测] 推断，见模块 docstring。
    """
    series_id = nber_parse.series_id_from_doi(doi)
    if series_id is None:
        return None
    return f"{_HANDLE_PREFIX}{series_id[1:]}"


def stub_from_record(record: RedifRecord, doi: str) -> PaperStub:
    """`RedifRecord` + 入参 DOI → `PaperStub`（§5.7 映射表）。

    `identifiers = ((doi, 入参 DOI), (repec, handle))`——**`(repec, handle)` 按 D-027 明文
    非跨源合并锚点**（跨源锚仍是 DOI）；但 `MergeEngine` 强合并按 `(scheme,value)` 命中，
    故它入库后天然是 *RePEc 内部* 的幂等锚点（同一 handle 二次 enrich 必落同一 paper）。
    二者不冲突：前者说的是"不拿 handle 去跟别的源对齐身份"，后者说的是"本源自身可重放"。

    `meta` 携 `jel`（JSON 数组串——`PaperStub.meta` 值类型冻结为 `str`，非标量结构一律
    `json.dumps`，aggregators.md §6 A-C1）与 `published_in`（`Publication-Status` 原串直落，
    供 T10 `preprint_of` 建边消费，本函数不建边）。
    """
    meta: list[tuple[str, str]] = []
    if record.jel:
        meta.append(("jel", json.dumps(list(record.jel), ensure_ascii=False)))
    if record.publication_status:
        meta.append(("published_in", record.publication_status))
    return PaperStub(
        title=record.title,
        identifiers=(("doi", doi), ("repec", record.handle)),
        year=record.year,
        abstract=record.abstract,
        authors=record.authors,
        meta=tuple(meta),
    )


# --- manifest 解析与新鲜度 --------------------------------------------------------------------


def parse_manifest(data: bytes | str) -> SnapshotManifest:
    """`manifest.json` 字节 → `SnapshotManifest`；畸形 → `CrawlerError(PARSE)`（响亮）。

    快照是本通道的**唯一数据来源**，manifest 畸形意味着无法知道该读哪些文件、快照有多新
    ——此处静默降级等于让整条通道给出无法解释的空结果（审计 S1 原则），故响亮失败。
    """
    try:
        payload = json.loads(data)
    except json.JSONDecodeError as exc:
        raise CrawlerError(ErrorClass.PARSE, f"repec manifest 不是合法 JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise CrawlerError(ErrorClass.PARSE, "repec manifest 顶层不是 JSON 对象")

    try:
        files = tuple(
            SnapshotFile(
                name=str(item["name"]), bytes=int(item["bytes"]), sha256=str(item["sha256"])
            )
            for item in payload.get("files", [])
        )
        return SnapshotManifest(
            schema=int(payload["schema"]),
            archive=str(payload["archive"]),
            series=tuple(str(s) for s in payload.get("series", ())),
            mirror=str(payload.get("mirror", "")),
            source_urls=tuple(str(u) for u in payload.get("source_urls", ())),
            fetched_at=str(payload["fetched_at"]),
            files=files,
            record_count=int(payload.get("record_count", 0)),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise CrawlerError(ErrorClass.PARSE, f"repec manifest 字段缺失或类型不符: {exc}") from exc


def parse_fetched_at(raw: str) -> datetime | None:
    """`fetched_at`（UTC ISO8601）→ aware `datetime`；不可解析 → None（调用方按"未知"处置）。

    无时区偏移的串按 UTC 补齐（契约要求 UTC，宽容旧写法而非拒绝——新鲜度只驱动一条警告
    文案，不是行为开关）。
    """
    try:
        parsed = datetime.fromisoformat(raw.strip())
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed


def staleness_days(fetched_at: str, *, now: datetime) -> int | None:
    """快照已存放天数（向下取整）；`fetched_at` 不可解析 → None。

    `now` 由调用方注入（adapter 传 `datetime.now(UTC)`；单测传假时钟精确断言跨阈值）。
    负数（`fetched_at` 在未来，时钟偏斜）钳到 0——"负天数"传给用户没有意义。
    """
    parsed = parse_fetched_at(fetched_at)
    if parsed is None:
        return None
    return max(0, (now - parsed).days)


__all__ = [
    "MissKind",
    "RedifRecord",
    "SnapshotFile",
    "SnapshotManifest",
    "handle_from_doi",
    "parse_fetched_at",
    "parse_jel",
    "parse_manifest",
    "parse_redif",
    "parse_year",
    "staleness_days",
    "stub_from_record",
]
