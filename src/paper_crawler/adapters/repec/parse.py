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

## DOI↔handle 映射边界（唯一可靠面＝NBER **工作论文（w）** 语法映射）

`10.3386/w{n}` → `RePEc:nbr:nberwo:{n}`，**只映射 `w`（工作论文）**、**零模糊匹配、零启发式**，
series 号归一复用 `adapters/nber/parse.py::series_id_from_doi`（单一权威源，不复制正则）。

**只认 `w`，`t`（技术工作论文）及其余非 `w` 前缀不映射**（P1-R2 收窄，替代原"w/t 同落
`nberwo`"推断）：原实现取 `series_id[1:]` 去掉首字母，令 `10.3386/w9001` 与 `10.3386/t9001`
**塌进同一 handle** `RePEc:nbr:nberwo:9001`——两篇不相交的 NBER 论文被判成同一条，`t` 的
abstract/authors/jel 静默污染 `w` 记录，并落一条高置信 `candidate_duplicate` 把两篇真实不同的
论文判成疑似重复（cli 全库 DOI + `ORDER BY value` 下 `t` 恒撞 `w`，必触发）。快照面（`nberwo`）
本就只含工作论文，`t` 落哪个 series 段亦 [未实测]，故按 D-035 授权的"按实测收窄而非按推断扩张"
**只认 `w`**。`t` 与其余 NBER 旁系 → `handle_from_doi` 返回 None → 调用方计
`MissKind.UNADDRESSABLE`（结构性不可寻址；`uncovered_series_letter` 记 DEBUG 成因字母），
既不污染 `w` 记录、也不落假 candidate。

**id 段前导零的非对称性 [未实测]**：`10.3386/w42` → `…:42`，而 `10.3386/w0042` → `…:0042`
——DOI 侧写几位零，handle 侧就是几位零。上游 handle 是否统一去零**未核实**，故本模块
**原样保留、不做去零归一**：去零是一个未经证实的改写，一旦上游确实带零就会让全部带零条目
join 失败。真实后果被 `MissKind.MISSING_HANDLE`（覆盖缺口）如实记录，T19 实测后按实测处置。

**BOM**：字节按 `utf-8-sig` 解码——带 BOM 的上游文件若按 `utf-8` 解，`\\ufeff` 会粘在首个
字段名上使 `Template-Type` 匹配失败、整份文件静默解析为空。
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

# **不接受续行折叠的身份字段**（P1-1 修复）：`Handle` 是记录的**身份**，一旦被后随的散文
# （archive 页脚、记录间说明文字）折进来，handle 即被污染 ⇒ 本地 join 查无 ⇒ 该 DOI 被静默
# 记成"覆盖缺口"，让**解析伪影伪装成快照陈旧**，直接毒化 D-035 决策 4 的三分观测语义。
# 身份字段宁可截断也不能被拼接：值只取 `Handle:` 那一行。
_NO_FOLD_FIELDS = frozenset({"handle", "template-type"})
# handle 语法：`RePEc:{archive}:{series}:{id}`（[LIVE] `RePEc:nbr:nberwo:3210`）。不合语法者
# **不静默丢弃**——计入 `RedifParseResult.malformed`，由 adapter 作 PARSE 类观测响亮上报。
# 整体大小写不敏感（含 `RePEc:` 前缀本身）：归一后统一写回规范形，见 `canonical_handle`。
_HANDLE_RE = re.compile(r"^RePEc:([A-Za-z0-9]+):([A-Za-z0-9]+):(\S+)$", re.IGNORECASE)

# NBER archive/series 段。**只承载 `w` 工作论文**（`t` 等旁系落哪个 series 段 [未实测]，
# 本通道不映射——见模块 docstring 的"只认 `w`"收窄）。
_ARCHIVE = "nbr"
_SERIES = "nberwo"
_HANDLE_PREFIX = f"RePEc:{_ARCHIVE}:{_SERIES}:"


class MissKind(StrEnum):
    """`enrich_batch` 未命中的三种成因（D-035 决策 4「未命中三分观测」，审计 S1 原则）。

    openalex/s2 的"未命中"只有一种含义（上游没这条），故此三分是 repec 专有的契约要求
    ——三类**各有计数并进摘要行**，不静默合并为一个"没查到"。
    """

    # (a) 非 NBER 工作论文 DOI（非 10.3386，或 t 等非 w 旁系）⇒ 结构性不可寻址（非缺陷）
    UNADDRESSABLE = "unaddressable"
    MISSING_HANDLE = "missing_handle"  # (b) 前缀符但快照内无该 handle ⇒ 覆盖缺口
    NO_JEL = "no_jel"  # (c) handle 命中但无 Classification-JEL ⇒ 增值为空


@dataclass(frozen=True)
class RedifRecord:
    """一条 ReDIF-Paper 记录的解析结果（字段子集——只取本通道消费得到的面）。

    `handle` 已经 `canonical_handle` 归一（archive/series 段小写化）——RePEc handle 的
    archive/series 段惯例大小写不敏感，不归一则上游一次大小写漂移就会让本地 join 全线查无、
    并被误记成"覆盖缺口"。
    """

    handle: str
    title: str
    authors: tuple[str, ...] = ()
    year: int | None = None
    abstract: str | None = None
    jel: tuple[str, ...] = ()
    publication_status: str | None = None


@dataclass(frozen=True)
class RedifParseResult:
    """一份 ReDIF 文本的解析结果 + **解析伪影观测**（P1-1 修复）。

    `malformed` / `stray_lines` 是 **PARSE 类观测**，与 `MissKind` 三分**计数分离**：三分说的是
    "快照与查询的关系"（不可寻址／覆盖缺口／增值为空），解析伪影说的是"快照文件本身没读懂"。
    把后者混进前者会让一个页脚散文伪装成"快照该刷新了"——正是本项修复要根除的误导。
    """

    records: tuple[RedifRecord, ...] = ()
    malformed: tuple[str, ...] = ()  # 语法不合的 handle 原值（截断保留，供人工核对）
    stray_lines: int = 0  # 悬空续行：紧跟身份字段、无处可归的行（记录间散文/页脚的典型症状）
    skipped_blocks: int = 0  # 无 handle 或无 title 的块（如 ReDIF-Series 模板块，正常现象）


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


def _iter_raw_records(text: str) -> tuple[list[list[tuple[str, str]]], int]:
    """按 `Template-Type:` 边界切分，产出每条记录的 `(小写字段名, 值)` 有序列表 + 悬空续行数。

    续行（不匹配 `Name: value` 的非空行）拼接进上一字段，**跨空行继续**——空行是值内部的
    段落分隔而非字段终止符，`Template-Type:` 才是唯一的记录边界（见模块 docstring）。
    `Template-Type:` 之前的前言（archive 说明等）整体丢弃。

    **例外：`_NO_FOLD_FIELDS`（`Handle`/`Template-Type`）不接受续行**（P1-1 修复）。紧跟身份
    字段的非字段行是**悬空续行**：丢弃而非折叠，并计数返回——记录间散文与 archive 页脚正是
    以这种形态出现，折进来会污染 handle、把解析伪影伪装成"覆盖缺口"。
    """
    records: list[list[tuple[str, str]]] = []
    current: list[tuple[str, str]] | None = None
    stray = 0

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
        # 非字段形态 → 上一字段的续行（空格折叠），身份字段除外
        if not current:
            continue
        last_key, last_value = current[-1]
        if last_key in _NO_FOLD_FIELDS:
            stray += 1  # 悬空：身份字段不吃续行，该行无处可归
            continue
        current[-1] = (last_key, f"{last_value} {line}".strip())
    return records, stray


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


def canonical_handle(raw: str) -> str | None:
    """handle 语法校验 + 归一：`RePEc:{archive}:{series}:{id}`，archive/series 段小写化。

    RePEc handle 的 archive/series 段惯例大小写不敏感（`RePEc:NBR:NBERWO:5` 与
    `RePEc:nbr:nberwo:5` 指同一条）；不归一则上游一次大小写漂移会让本地 join 全线查无，
    并被误记成"覆盖缺口"。**id 段原样保留**——其大小写/前导零是否可归一 [未实测]
    （见模块 docstring 的前导零注记），归一未经证实的面等于用推断改写数据。

    语法不合（含被散文污染的 handle）→ None，调用方计 `RedifParseResult.malformed`。
    """
    match = _HANDLE_RE.match(raw.strip())
    if match is None:
        return None
    archive, series, ident = match.groups()
    return f"RePEc:{archive.lower()}:{series.lower()}:{ident}"


def parse_redif_result(data: bytes | str) -> RedifParseResult:
    """ReDIF 字节/文本 → 记录元组 + **解析伪影观测**（P1-1；`parse_redif` 是其便捷包装）。

    **两类"没产出"严格分离**：
    - **正常跳过**（`skipped_blocks`）：无 handle 或无 title 的块——上游 bulk 文件里混入
      `ReDIF-Archive`/`ReDIF-Series` 模板块是正常现象，它们本就无论文身份。口径与 crossref
      「无 DOI 跳过」、nber RSS「无 guid 跳过」同源，**不是异常**。
    - **解析伪影**（`malformed` / `stray_lines`）：handle 语法不合（典型成因＝记录间散文被
      折进 handle，本函数已从源头堵死，此处是纵深防御）或悬空续行。这类**必须响亮**——静默
      吞掉会让它们伪装成"覆盖缺口"，毒化三分观测。

    字节按 **UTF-8-SIG** 解码（自动剥 BOM——上游历史文件带 BOM 时，`\\ufeff` 会粘在首个字段名
    上使 `Template-Type` 匹配失败、整份文件解析为空），非法字节 `replace`（上游历史条目编码
    不齐，响亮失败换不来更多信息，且会让一个坏字节炸掉整份快照）。
    """
    text = data.decode("utf-8-sig", errors="replace") if isinstance(data, bytes) else data
    blocks, stray = _iter_raw_records(text)
    records: list[RedifRecord] = []
    malformed: list[str] = []
    skipped = 0

    for fields in blocks:
        raw_handle = _first(fields, "handle")
        title = _first(fields, "title")
        if not raw_handle or not title:
            skipped += 1
            continue
        handle = canonical_handle(raw_handle)
        if handle is None:
            malformed.append(raw_handle[:120])
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
    return RedifParseResult(
        records=tuple(records),
        malformed=tuple(malformed),
        stray_lines=stray,
        skipped_blocks=skipped,
    )


def parse_redif(data: bytes | str) -> tuple[RedifRecord, ...]:
    """`parse_redif_result(data).records` 的便捷包装（只要记录、不要伪影观测时用）。"""
    return parse_redif_result(data).records


# --- DOI↔handle 纯语法映射 --------------------------------------------------------------------


def handle_from_doi(doi: str) -> str | None:
    """`10.3386/w{n}` → `RePEc:nbr:nberwo:{n}`（**只映射 `w` 工作论文**）；其余一律 None。

    series 号归一**复用** `nber.parse.series_id_from_doi`（单一权威源，不复制正则）：大小写
    不敏感、非 NBER 前缀/book chapter/畸形 DOI 一律 None ⇒ 调用方计 `MissKind.UNADDRESSABLE`
    （结构性不可寻址，非缺陷）。

    **`t`（技术工作论文）及其余非 `w` 前缀同样返回 None**（P1-R2 收窄）：原实现 `series_id[1:]`
    去首字母，会把 `w{n}` 与 `t{n}` 塌进同一 handle（假重复 + 静默污染根因，见模块 docstring）。
    快照面只含 `nberwo` 工作论文、`t` 的 series 段亦 [未实测]，故只认 `w`；`t` 与旁系的成因由
    `uncovered_series_letter` 供 DEBUG 记录，与"非 NBER 前缀"同归 `unaddressable` 但可辨。

    产出经 `canonical_handle` 同款归一（archive/series 段小写），与快照侧的键口径**同源**
    ——两侧各自归一就会漂移。**前导零原样保留**（`10.3386/w0042` → `…:0042`）：上游是否
    去零 [未实测]，去零是未经证实的改写（见模块 docstring 的前导零注记）。
    """
    series_id = nber_parse.series_id_from_doi(doi)
    if series_id is None or nber_parse.series_letter(series_id) != "w":
        return None
    return f"{_HANDLE_PREFIX}{series_id[1:]}"


def uncovered_series_letter(doi: str) -> str | None:
    """合法 NBER series DOI 但**非 `w` 工作论文**时返回其 series 首字母（如 `t`）；否则 None。

    `handle_from_doi` 只映射 `w`——`t`（技术工作论文）等其余 NBER series 虽是合法 `10.3386`
    DOI，本通道刻意不覆盖（`nberwo` 快照只含工作论文面，且 `t` 落哪个 series 段 [未实测]）。
    这类**与"非 NBER 前缀"同计入 `unaddressable`**（都属结构性不可寻址），但成因不同：本函数
    供调用方在 DEBUG **记下具体成因字母**，使"刻意不覆盖的 NBER 旁系"与"根本不是 NBER"在观测
    上可辨，而非混为一个哑数字。`w` 本身是被覆盖面（非"未覆盖旁系"）→ None。
    """
    series_id = nber_parse.series_id_from_doi(doi)
    if series_id is None:
        return None
    letter = nber_parse.series_letter(series_id)
    return letter if letter != "w" else None


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
    "RedifParseResult",
    "RedifRecord",
    "SnapshotFile",
    "SnapshotManifest",
    "canonical_handle",
    "handle_from_doi",
    "parse_fetched_at",
    "parse_jel",
    "parse_manifest",
    "parse_redif",
    "parse_redif_result",
    "parse_year",
    "staleness_days",
    "stub_from_record",
    "uncovered_series_letter",
]
