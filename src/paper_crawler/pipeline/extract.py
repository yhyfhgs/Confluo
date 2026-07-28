"""stage 5 全文抽取的抽取器层与取代规则（design/12-fulltext-extract；D-033）。

职责边界：本模块只做「路径进、值对象出」的抽取，以及**纯函数**形态的全序比较小件。
它**不知道 DB、不知道 Config、不落盘**——幂等键求值、落位、upsert、`ingest_state`
推进全部在 `stages.py::_stage_extract`（§4.1 分工线：**抽取器报「看到的是什么」，
handler 决「算不算失败、落哪个 state」**）。

两条路径（§1.2）：

- **纯文本基线** `PypdfExtractor`：恒可用、零配置、零外部服务，产 `.txt`（AC-7.1 载体）。
- **GROBID 可选增强** `GrobidExtractor`：`[extract] grobid_url` 配置且服务在线时产
  `.tei.xml`；任何不可用形态一律降级为基线路径且**不报错**（AC-7.2）。

合规（§2，硬约束先于一切方案）：

1. GROBID 的 `consolidateHeader` / `consolidateCitations` / `consolidateFunders`
   **三者逐一硬编码 "0"、不设 config 槽**——consolidation 会让 GROBID 代为访问
   biblio-glutton/Crossref，开启即在用户不知情下从 extract 阶段发出外网请求，越过本
   项目的限速/预算/FetchLog 全部记账面；漏写一个就漏一条外网通道，且**不得依赖 GROBID
   的默认值**（其默认值随版本变动过）。见 `_CONSOLIDATE_OFF`。
2. 加密 PDF 姿态（§2.3，fable 已裁决 approve，五条实现约束）：允许**空口令**打开
   （等价于任何阅读器打开该文件的常规行为）；`decrypt("")` **至多调用一次**，失败即止；
   **不得存在任何候选口令常量/口令文件/「常见 owner password」集合**（存在该数据结构
   本身即违规）；**不实现权限位改写/绕过**；`note` 对一切非空口令情形一律只记
   `'encrypted'` 单一 token，**不分化**出携带破解线索的取值。见 `_read_encrypted`。
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ElementTree
from collections.abc import Callable
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

import pypdf

from paper_crawler.errors import CrawlerError, ErrorClass

if TYPE_CHECKING:  # 运行时不 import（避免 pipeline→http 的运行时依赖；构造期局部 import）
    from paper_crawler.http import HttpClient

# ---------------------------------------------------------------------------
# 常量：extractor 名 / 落位后缀 / fulltext.state / note 闭集
# ---------------------------------------------------------------------------

EXTRACTOR_PYPDF = "pypdf"
EXTRACTOR_GROBID = "grobid"
EXTRACTOR_NOOP = "noop"  # Phase 1 占位行（无任何抽取事实）

SUFFIX_TXT = ".txt"
SUFFIX_TEI = ".tei.xml"

STATE_EXTRACTED = "extracted"
STATE_EXTRACT_FAILED = "extract_failed"
STATE_NOOP = "noop"

# §6.1 `note` token 闭集（新增须同步 design/12 §6.1 表）。token 由**抽取器**作为判别信息
# 给出（只有它分得清加密/无文本层/结构损坏/有文本层但抽出空），handler 只做「算不算失败」。
NOTE_ENCRYPTED = "encrypted"
NOTE_IMAGE_ONLY = "image_only"
NOTE_CORRUPT = "corrupt"
NOTE_EMPTY_TEXT = "empty_text"
NOTE_TOKENS = frozenset({NOTE_ENCRYPTED, NOTE_IMAGE_ONLY, NOTE_CORRUPT, NOTE_EMPTY_TEXT})

# §5.3 rank：**登记的**真实抽取器序。未登记的 extractor 名 → `RANK_NOOP` 并 WARN
# （不得压制已登记的真实抽取器）。
_EXTRACTOR_RANK: dict[str, int] = {EXTRACTOR_GROBID: 2, EXTRACTOR_PYPDF: 1}
RANK_EXTRACT_FAILED = 0
RANK_NOOP = -1
# 「陈旧行」（source_sha256 ≠ 其 asset 当前 sha256）与「产物校验不过的行」共用最低档：
# 前者出自一份已被替换的源文件、后者的落盘产物已不在/已被改坏，二者都**不再有资格支配
# 任何候选**。设计（§5.2 r3 ④b）只要求后者「按 extract_failed 之下处理」，−2 满足之，
# 且与陈旧同档语义一致（都是「这行的产物不可用」）。
RANK_INVALID = -2

# GROBID 降级链的 obslog reason token 闭集（§7.2；T19 从 obslog 取证）。
REASON_UNREACHABLE = "grobid_unreachable"
REASON_TIMEOUT = "grobid_timeout"
REASON_BAD_TEI = "grobid_bad_tei"
REASON_EMPTY_TEI = "grobid_empty_tei"

_TEI_NS = "{http://www.tei-c.org/ns/1.0}"
_XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"
_VERSION_SEGMENT_RE = re.compile(r"\d+")
_MAX_VERSION_LEN = 64


# ---------------------------------------------------------------------------
# 共用小件
# ---------------------------------------------------------------------------


def visible_char_count(text: str) -> int:
    """**可见文本**字符数——两条路径唯一同口径的量（§7.3）。

    口径统一是硬要求而非洁癖：`char_count` 参与 §5.3 全序比较，若 TEI 路径混入标签/缩进
    字节而纯文本路径不混，该维度跨 extractor 立即失去可比性，全序就会系统性偏袒 TEI。
    故两条路径都走本函数：空白折叠后计长——纯空白（无任何可见字符）恒得 0，正是 §4.1
    「零输出」的唯一判据（取 `char_count == 0` 而非 `text == ""`：GROBID 路径的 `text` 是
    TEI **XML 源码**，header-only 空产物时 XML 非空而可见文本为零）。
    """
    return len(" ".join(text.split()))


def version_key(raw: str | None) -> tuple[int, int, int]:
    """版本串 → 可比较三元组（§5.3）：取串中前三段数字，不足补 0；无数字 → `(0, 0, 0)`。

    `"5.1.0"` → `(5, 1, 0)`；`"0.8.2-SNAPSHOT"` → `(0, 8, 2)`；`"unknown"` → `(0, 0, 0)`
    （GROBID 版本端点取回失败时的兜底值，语义安全——不会凭空压制已登记版本）。
    """
    if not raw:
        return (0, 0, 0)
    parts = [int(seg) for seg in _VERSION_SEGMENT_RE.findall(raw)[:3]]
    while len(parts) < 3:
        parts.append(0)
    return (parts[0], parts[1], parts[2])


def extractor_rank(name: str | None) -> int | None:
    """已登记抽取器的 rank；未登记（含 None/noop）→ None，由调用方按 §5.3 落 `RANK_NOOP`。"""
    if not name:
        return None
    return _EXTRACTOR_RANK.get(name)


def order_key(
    *, rank: int, extractor_ver: str | None, char_count: int | None, asset_id: str | None
) -> tuple[int, tuple[int, int, int], int, str]:
    """§5.3 全序键 `(rank, ver_key, char_count, asset_id)`——取 max 即取代规则。

    max 是幂等 + 交换 + 结合的半格运算 ⇒ 终态是**输入集合**的函数、与注入顺序无关
    （沿 D-031 已付过一次学费的纪律）。`ver_key` 位序**高于** `char_count`：版本是抽取器
    能力的显式声明，字数只是启发式；同版本内才用 `char_count` 分胜负（同 paper 两个 pdf
    asset 时更长者通常是完整版）。`asset_id` 是最终 tie-break，保证全序无并列；legacy 行
    `asset_id IS NULL` 归一为 `""`（空串排在一切 ULID 之前 ⇒ 同键时 legacy 必败，语义正确）。
    """
    return (rank, version_key(extractor_ver), int(char_count or 0), asset_id or "")


# ---------------------------------------------------------------------------
# §4：`ExtractedText` 值对象 + `TextExtractor` Protocol
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ExtractedText:
    """一次抽取的全部产物（纯值对象，无 DB/文件副作用）。

    `note` 是**判别信息、不是判决**（§4.1 末条）：只有抽取器能分辨「加密 / 无文本层 /
    结构损坏 / 有文本层但抽出空」——这是观测，不是分类学决策；handler 拿到零输出却无从
    复原是哪一种，§6.1 的四元闭集就不可生产。抽取器**不得**据此自行落库/抛异常/降级。
    """

    text: str  # 落盘正文（.txt 全文 / .tei.xml 的 XML 源）
    extractor: str  # "pypdf" | "grobid"（落 fulltext.extractor）
    extractor_ver: str  # 抽取器版本串（库版本 / GROBID 服务版本）
    suffix: str  # ".txt" | ".tei.xml"——决定落位文件名（由抽取器给，非 handler 查表）
    char_count: int  # **可见文本**字符数（§7.3 同口径）
    lang: str | None = None  # TEI @xml:lang；纯文本路径恒 None（§4.2 不引入语言识别依赖）
    title: str | None = None  # TEI titleStmt/title；纯文本路径 None（AC-7.1 判据分叉）
    note: str | None = None  # 判别信息（§6.1 闭集），成功抽取恒 None

    def __post_init__(self) -> None:
        """§4.1 断言锁定：`char_count > 0` ⇒ `note` 恒 None；`== 0` ⇒ `note` **必须**非空。

        这条不变式是 §6.1 四元 `note` 闭集可生产的前提——放任一个「零输出但无 note」的
        产物流出，handler 就只能落一个原因不明的 `extract_failed`，长尾诊断面即刻消失。
        """
        if self.char_count < 0:
            raise ValueError("char_count must be >= 0")
        if self.char_count == 0 and not self.note:
            raise ValueError("zero-output ExtractedText must carry a note token (§4.1)")
        if self.char_count > 0 and self.note:
            raise ValueError("successful ExtractedText must not carry a note token (§4.1)")
        if self.note is not None and self.note not in NOTE_TOKENS:
            raise ValueError(f"note must be one of {sorted(NOTE_TOKENS)}, got {self.note!r}")


class TextExtractor(Protocol):
    """抽取器契约：路径进、值对象出。无 DB、无 Config、无网络语义泄漏。

    `version` **构造期即可知**（属性，而非 `extract()` 的返回派生）——这是 §5.2「幂等键
    抽取前可判」的硬前提：若版本只能在抽完后知道，「幂等跳过」就退化成「抽完再比」。
    """

    name: str
    version: str

    def extract(self, source: Path) -> ExtractedText: ...


def _missing_source(source: Path, detail: str) -> CrawlerError:
    """§6.1 第 1 类（库↔文件不一致）：文件不存在/不可读 → 响亮 `INTEGRITY`，不静默记失败。"""
    return CrawlerError(
        ErrorClass.INTEGRITY, f"extract source unreadable: {source} ({detail})", detail=detail
    )


# ---------------------------------------------------------------------------
# §3：纯文本基线抽取器 = pypdf
# ---------------------------------------------------------------------------


def _failed(note: str, *, extractor: str, version: str, suffix: str) -> ExtractedText:
    """零输出产物（`char_count == 0` + 判别 token）；「算不算失败」由 handler 判（§6.1）。"""
    return ExtractedText(
        text="", extractor=extractor, extractor_ver=version, suffix=suffix, char_count=0, note=note
    )


def _has_image_xobject(reader: pypdf.PdfReader) -> bool:
    """页面资源里是否存在 `/Subtype /Image` 的 XObject（区分 image_only 与 empty_text）。

    纯图像扫描件（无文本层）与「有文本层但抽出空」是两种不同的长尾成因，§6.1 要求二者
    落**不同**的 note token；本判据是二者唯一的结构性差异。任何解析异常一律按「无图像」
    保守处理——本函数只服务 note 的精度，不参与成败判决，不该因它自身出错而改变结论。
    """
    try:
        for page in reader.pages:
            resources = page.get("/Resources")
            if resources is None:
                continue
            xobjects = resources.get_object().get("/XObject")
            if xobjects is None:
                continue
            for ref in xobjects.get_object().values():
                if str(ref.get_object().get("/Subtype", "")) == "/Image":
                    return True
    except Exception:  # 见 docstring：note 精度不得反过来影响成败判决
        return False
    return False


# P1-7：pypdf 6.x 的 `_cmap.py` 在解析内嵌字体 CMap（字符编码表）时 5 处使用
# `bytes.decode("utf-16-be", "surrogatepass")`——`surrogatepass` 错误处理器允许**未配对**
# 的 UTF-16 代理码元原样穿透进 Python str（标准 UTF-16 解码下这本是 `UnicodeDecodeError`）。
# 畸形/截断的 CMap 数据因此可让 `page.extract_text()` 产出**孤立代理字符**（如 U+D800）：
# 它是合法的 Python str 元素，却不是合法的 Unicode 标量值——下游 `str.encode("utf-8")`
# （stages.py 落盘/DB upsert 前必经）会对其抛 `UnicodeEncodeError`。该异常不是
# `CrawlerError`，被 runner 误判 TRANSIENT 并按 RETRY_TABLE 重试 4 次（每次 100% 复现同一
# 畸形 CMap）后判 FAILED——而畸形 PDF 本应是 §6.1「第 2 类：不失败任务」的长尾。
#
# 在本抽取器的**唯一出口**清洗（单一源头 ⇒ visible_char_count/落盘/upsert 全部天然干净）：
# 孤立代理码点一律替换为 U+FFFD（Unicode 官方「替换字符」，与 GROBID 路径 `_post()` 对
# 不可解码字节的处理口径一致，见本文件 `raw.decode("utf-8", errors="replace")`）。这里选
# 正则而非同款 `text.encode("utf-8", errors="replace").decode("utf-8")`：后者对**已经是
# str**、其中含不可编码字符的情形，替换字节是 ASCII `?`（0x3F）而不是 U+FFFD，达不到「替换
# 为 U+FFFD」的目标（`errors="replace"` 的替换符随方向而异：decode 缺字节→U+FFFD，encode
# 缺字节→`?`）。正则单趟 O(n) 扫描，且只匹配代理区间本身——不触碰任何其他字符（含非 BMP
# 的合法字符：Python str 用单个码点表示它们，从不落在 U+D800–U+DFFF 区间，不会被误伤）。
_LONE_SURROGATE_RE = re.compile("[\ud800-\udfff]")


def _sanitize_lone_surrogates(text: str) -> str:
    """孤立代理码点 → U+FFFD（见上）；不含代理字符时等价于原样返回。"""
    return _LONE_SURROGATE_RE.sub("�", text)


def _read_encrypted(reader: pypdf.PdfReader) -> bool:
    """加密 PDF：**只试一次空口令**（§2.3 五条约束）。成功打开返回 True，否则 False。

    - `decrypt("")` 调用**至多一次**，失败即止——不重试、不变形（不试 `" "`、不试 `None`、
      不试 doi/标题等文档相关串）；本函数是全模块**唯一**的 `decrypt` 调用点。
    - **不存在任何回退口令列表**：本模块无候选口令常量、无口令文件读取、无「常见 owner
      password」集合——存在这样的数据结构本身即违规，与它是否被执行无关。
    - **不实现权限位改写/绕过**：pypdf 默认行为如何即如何，不为「禁止提取」权限位写旁路。
    - 失败原因**不分化**：调用方一律记 `note='encrypted'` 单一 token（口令强度线索本身
      就是破解辅助面）。
    """
    try:
        return bool(reader.decrypt(""))
    except Exception:  # 任何解密失败（含不支持的加密算法）都归 encrypted，不分化 note
        return False


class PypdfExtractor:
    """纯文本基线抽取器（§3 裁决①）：文本层直取，零外部服务、零传递依赖。

    已知能力缺口（§3.4，如实入档不修）：AES 加密 PDF（无 `cryptography` 时不能解）、
    纯图像扫描件（不引入 OCR——重依赖 + 质量不可控 + 无消费场景）、多栏阅读序不保证
    （需要正确阅读序的消费方走 GROBID 路径）。
    """

    name = EXTRACTOR_PYPDF

    def __init__(self) -> None:
        self.version = str(pypdf.__version__)

    def extract(self, source: Path) -> ExtractedText:
        """抽取正文；「文件在但抽不出」**不抛异常**，返回 `char_count == 0` + note（§4.1）。"""
        try:
            data = source.read_bytes()
        except OSError as exc:
            raise _missing_source(source, type(exc).__name__) from exc

        def fail(note: str) -> ExtractedText:
            return _failed(note, extractor=self.name, version=self.version, suffix=SUFFIX_TXT)

        try:
            reader = pypdf.PdfReader(BytesIO(data))
        except Exception:  # pypdf 的解析异常族不稳定（随版本变动），一律归「结构损坏」
            return fail(NOTE_CORRUPT)
        if reader.is_encrypted and not _read_encrypted(reader):
            return fail(NOTE_ENCRYPTED)
        try:
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception:  # 页面遍历/解码期的损坏同归 corrupt
            return fail(NOTE_CORRUPT)
        text = _sanitize_lone_surrogates(text)  # P1-7：畸形 CMap → 孤立代理字符清洗（见上）

        count = visible_char_count(text)
        if count == 0:
            return fail(NOTE_IMAGE_ONLY if _has_image_xobject(reader) else NOTE_EMPTY_TEXT)
        return ExtractedText(
            text=text,
            extractor=self.name,
            extractor_ver=self.version,
            suffix=SUFFIX_TXT,
            char_count=count,
            lang=None,  # §4.2：不引入语言识别依赖——错误的 lang 比 NULL 更坏
            title=None,  # 纯文本路径无结构化标题（AC-7.1 走正文前 2000 字符窗判据）
        )


# ---------------------------------------------------------------------------
# §7：GROBID 可选增强 + 降级链
# ---------------------------------------------------------------------------

# §2.1 + §7.2 末段：三个 consolidate 参数**逐一显式置 0**，不设 config 槽、不依赖默认值。
_CONSOLIDATE_OFF: dict[str, str] = {
    "consolidateHeader": "0",
    "consolidateCitations": "0",
    "consolidateFunders": "0",
}
_GROBID_BACKOFF_S = 5.0  # §7.2：503（队列背压）退避重试一次；不做指数三退


class GrobidUnavailable(Exception):
    """GROBID 本次无有效产出 —— **一律降级纯文本，绝不逃逸出 extract handler**。

    语义收敛为一句话（§6.1）：**「GROBID 无有效产出 → 纯文本」**，不区分成因是服务不可用、
    超时、非法 TEI、还是 header-only 空产物。`remember=True` 表示该成因是**持久态**
    （服务未起/被 kill/路径配错），本次运行内此后不再调用 GROBID（含探活）——逐篇重试是
    纯空转；记忆只活在进程内，**不落库、不跨运行**（用户起好服务后无需清任何状态）。
    """

    def __init__(self, reason: str, *, remember: bool, hint: str = "") -> None:
        super().__init__(f"{reason}{f': {hint}' if hint else ''}")
        self.reason = reason
        self.remember = remember
        self.hint = hint


def _parse_version_text(raw: str) -> str:
    """`/api/version` 响应 → 版本串。

    [UNRESOLVED]（design/12 §13）：GROBID 服务的版本端点格式未实测（纯文本 vs JSON）。
    两形态都兜住：JSON object 取其 `version` 键，否则取整串。语义安全——取不到数字时
    `version_key` 返回 `(0,0,0)`，不会凭空压制已登记版本。
    """
    text = raw.strip()
    if text.startswith("{"):
        try:
            parsed = json.loads(text)
        except (json.JSONDecodeError, ValueError):
            return "unknown"
        if isinstance(parsed, dict) and parsed.get("version"):
            return str(parsed["version"])[:_MAX_VERSION_LEN]
        return "unknown"
    return text[:_MAX_VERSION_LEN] if text else "unknown"


def _classify(exc: CrawlerError) -> GrobidUnavailable:
    """把逐篇请求的 `CrawlerError` 映射为 §7.2 处置矩阵的一行。

    **判别键 = `CrawlerError.detail`**（r3 修正 (i)）：连接失败与读超时的 `error_class`
    同为 TRANSIENT，但**并非不可区分**——`http.py` 的两个 except 分支给了确定性判别位
    （`TimeoutException` → `detail="timeout"`；其余 `HTTPError` → `detail=<类名>`）。
    二者的记忆语义**相反**：读超时是 per-文档 的（大 PDF 慢，不代表服务不可用）故不记忆；
    连接失败/重置与「探活失败」同类（服务不在了——本机 GROBID 常跑在会被随手关掉的容器
    里，探活只证明**那一刻**在线）故整轮降级并记忆。
    """
    status = getattr(exc, "status_code", None)
    if status == 404:
        return GrobidUnavailable(
            "grobid_http_404",
            remember=True,
            hint="检查 [extract] grobid_url 是否指向服务根（应为 http://host:port，不含 /api）",
        )
    if status is not None:
        return GrobidUnavailable(f"grobid_http_{status}", remember=False)
    if exc.detail == "timeout":
        return GrobidUnavailable(REASON_TIMEOUT, remember=False)
    # 其余无状态码情形 = 连接失败/重置（`http.py` 的 `HTTPError` 分支，detail=<异常类名>）：
    # 与「探活失败」同类（服务不在了），整轮降级并记忆。
    return GrobidUnavailable(REASON_UNREACHABLE, remember=True, hint=str(exc.detail or ""))


@dataclass
class GrobidRuntime:
    """一次运行内的 GROBID 客户端 + 探活缓存 + 本轮记忆（`StageContext` 的可选字段）。

    **每轮运行一次前置探活**（不是每篇）：`GET /api/isalive` + `GET /api/version`，惰性
    触发并缓存。前置探活是结构性选择：①「服务根本没起」是最常见的关闭形态，一次判定即可，
    避免 N 篇 × 连接超时的空转；②它把「服务不可用」与「本篇处理失败」在**信号层面**分开
    ——探活给出的是一个显式的可用性事实，而不是从异常里反推的推测。

    **不注册限速桶、不写 FetchLog**（§7.1）：GROBID 是本机服务不是站点，限速无意义；更要紧
    的是 **FetchLog 是在线预算的唯一事实源**（D-030 §7.2），把本地调用记进去会直接污染预算
    派生口径。故客户端构造时 `rate_limiter=None`。
    """

    client: HttpClient
    base_url: str
    sleeper: Callable[[float], None]
    probed: bool = False
    version: str = "unknown"
    disabled: bool = False  # 「记忆本轮」：此后不再调用 GROBID（含探活）

    def close(self) -> None:
        """释放底层 HTTP 连接池（幂等；`HttpClient.close()` 本身可重复调用）。

        调用点两处（都在 pipeline 侧）：①`disable()` —— 本轮此后不再调用 GROBID，连接池
        当即无用；②运行收尾（`runner._finalize`）—— 本轮结束，连接池随之释放。二者合起来
        使「每次运行泄漏一个连接池至进程退出」不可能发生。**不改 `disabled`**：关闭是资源
        动作，不是降级判决（读超时等不记忆的形态不得因收尾关闭而被误记成整轮不可用）。
        """
        self.client.close()

    def disable(self) -> None:
        """「记忆本轮」：此后不再调用 GROBID（含探活），并**当即**释放连接池。"""
        self.disabled = True
        self.close()

    def extractor(self) -> GrobidExtractor:
        """探活（每轮一次）并返回可用的抽取器；不可用 → `GrobidUnavailable`（**只抛一次**）。

        首次失败即置 `disabled`，故 handler 只需在 `disabled` 为真时静默走纯文本——WARN
        恰好一条，不会逐篇刷屏。
        """
        if not self.probed:
            self.probed = True
            try:
                self.client.get_text(f"{self._base()}/api/isalive", accept="text/plain")
            except CrawlerError as exc:
                self.disable()
                raise GrobidUnavailable(
                    REASON_UNREACHABLE, remember=True, hint=str(exc.detail or "")
                ) from exc
            try:
                raw = self.client.get_text(f"{self._base()}/api/version", accept="text/plain")
            except CrawlerError:
                self.version = "unknown"  # 探活成功但版本端点失败（§7.2 末段）
            else:
                self.version = _parse_version_text(raw)
        return GrobidExtractor(self)

    def process(self, pdf_bytes: bytes, filename: str) -> str:
        """`POST /api/processFulltextDocument`，返回 TEI 文本；失败 → `GrobidUnavailable`。

        503 是 GROBID 的**队列背压**信号（其文档明示）——**退避重试一次**（经注入的 sleeper）
        常能过；再 503 则降级。不做指数三退：本地批量堆积无意义。
        """
        url = f"{self._base()}/api/processFulltextDocument"
        files = {"input": (filename, pdf_bytes, "application/pdf")}
        try:
            return self._post(url, files)
        except CrawlerError as exc:
            if getattr(exc, "status_code", None) != 503:
                raise _classify(exc) from exc
        self.sleeper(_GROBID_BACKOFF_S)
        try:
            return self._post(url, files)
        except CrawlerError as exc:
            raise _classify(exc) from exc

    def _post(self, url: str, files: dict[str, tuple[str, bytes, str]]) -> str:
        raw = self.client.post_multipart(
            url, files=files, data=dict(_CONSOLIDATE_OFF), accept="application/xml"
        )
        return raw.decode("utf-8", errors="replace")

    def _base(self) -> str:
        return self.base_url.rstrip("/")


class GrobidExtractor:
    """GROBID 路径抽取器：TEI **原样**落盘（结构化产物即交付物）。

    版本 = 探活取得的服务版本（构造期可知，§5.2 幂等键前置可判的前提）。一切「无有效产出」
    形态——含 200 + 合法 TEI 但 `char_count == 0` 的 header-only 空产物——都抛
    `GrobidUnavailable` 触发纯文本兜底，**绝不返回零输出产物**：否则空 TEI 会以 rank 2
    压制同 paper 已有的 pypdf 正文（§6.1 审查实测反例），一次「增强」反而抹掉基线成果。
    """

    name = EXTRACTOR_GROBID

    def __init__(self, runtime: GrobidRuntime) -> None:
        self._runtime = runtime
        self.version = runtime.version

    def extract(self, source: Path) -> ExtractedText:
        try:
            data = source.read_bytes()
        except OSError as exc:
            raise _missing_source(source, type(exc).__name__) from exc
        tei = self._runtime.process(data, source.name)
        return parse_tei(tei, version=self.version)


def parse_tei(tei: str, *, version: str) -> ExtractedText:
    """TEI → `ExtractedText`（§7.3 消费口径）。无有效产出 → `GrobidUnavailable`。

    `char_count` 取 `<text>` 元素的**可见文本**字符数（stdlib ElementTree + `itertext()`，
    零新依赖），**不是 XML 源码长度**——该值参与全序比较，混入标签会使维度跨 extractor
    失去可比性并系统性偏袒 TEI。
    """
    try:
        root = ElementTree.fromstring(tei)
    except ElementTree.ParseError as exc:
        raise GrobidUnavailable(REASON_BAD_TEI, remember=False, hint=str(exc)) from exc
    if root.tag != f"{_TEI_NS}TEI":
        raise GrobidUnavailable(REASON_BAD_TEI, remember=False, hint=f"root={root.tag}")

    body = root.find(f"./{_TEI_NS}text")
    count = visible_char_count("".join(body.itertext())) if body is not None else 0
    if count == 0:
        # §6.1 P0-2：header-only 空产物与「服务不可用」同类处置 —— 立即纯文本兜底。
        raise GrobidUnavailable(REASON_EMPTY_TEI, remember=False)

    title_el = root.find(
        f"./{_TEI_NS}teiHeader/{_TEI_NS}fileDesc/{_TEI_NS}titleStmt/{_TEI_NS}title"
    )
    title = "".join(title_el.itertext()).strip() if title_el is not None else None
    return ExtractedText(
        text=tei,
        extractor=EXTRACTOR_GROBID,
        extractor_ver=version,
        suffix=SUFFIX_TEI,
        char_count=count,
        lang=root.get(_XML_LANG),
        title=title or None,
    )


__all__ = [
    "EXTRACTOR_GROBID",
    "EXTRACTOR_NOOP",
    "EXTRACTOR_PYPDF",
    "NOTE_CORRUPT",
    "NOTE_EMPTY_TEXT",
    "NOTE_ENCRYPTED",
    "NOTE_IMAGE_ONLY",
    "NOTE_TOKENS",
    "RANK_EXTRACT_FAILED",
    "RANK_INVALID",
    "RANK_NOOP",
    "REASON_BAD_TEI",
    "REASON_EMPTY_TEI",
    "REASON_TIMEOUT",
    "REASON_UNREACHABLE",
    "STATE_EXTRACTED",
    "STATE_EXTRACT_FAILED",
    "STATE_NOOP",
    "SUFFIX_TEI",
    "SUFFIX_TXT",
    "ExtractedText",
    "GrobidExtractor",
    "GrobidRuntime",
    "GrobidUnavailable",
    "PypdfExtractor",
    "TextExtractor",
    "extractor_rank",
    "order_key",
    "parse_tei",
    "version_key",
    "visible_char_count",
]
