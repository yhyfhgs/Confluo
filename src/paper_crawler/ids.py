"""标识符与标题规范化（Phase 3 T1；接口冻结件 plan §2-1）。

两枚纯函数，是合并引擎的弱信号/强合并匹配键的唯一构造入口：

- `normalize_doi`：DOI 写入的唯一归一入口（plan §2-1「identifier 写入的唯一入口经过
  它」）——crossref / unpaywall / dblp `ee` 回填 / openalex / s2 共用。小写化、剥
  `https://doi.org/`（含 `dx.` 与协议大小写）与 `doi:` 前缀、去首尾空白。
- `normalize_title`：弱信号候审的标题匹配键（plan §2-1 / 06 §3）——去标点、大小写折叠、
  LaTeX 宏剥离、Unicode 重音折叠、空白折叠。

二者均为**规范化器而非校验器**：见 `normalize_doi` docstring 的设计权衡。无任何 I/O、
无内部依赖（叶子模块，可被 storage.db 迁移器安全 import 用于回填）。
"""

from __future__ import annotations

import re
import unicodedata

# ---------------------------------------------------------------------------
# DOI 归一
# ---------------------------------------------------------------------------

# 已知 DOI URL/scheme 前缀（大小写不敏感）：`https://doi.org/`、`http://dx.doi.org/`、
# `doi:`。剥前缀后剩下裸 DOI（`10.xxxx/...`）。与 adapters 内既有两处 normalize_doi
# （aaai_ojs / acl_anthology）口径归一到此单点。
_DOI_PREFIX_RE = re.compile(r"^(?:https?://(?:dx\.)?doi\.org/|doi:)", re.IGNORECASE)


def normalize_doi(raw: str) -> str:
    """DOI 归一：去首尾空白 → 剥已知前缀 → 小写化。

    DOI 语法本身大小写不敏感（DOI Handbook §2.4），故小写化得到稳定的全局唯一键
    （identifier `(scheme,value)` 主键，天然强合并锚点，AC-3.1）。

    **设计权衡——归一而非校验（非 DOI 形态原样返回，不 raise）**：本函数是 identifier
    写入的唯一入口，输入已由上游 adapter 断言为 DOI（aggregators.md §6：各源从
    `DOI` / `ee` / `externalIds.DOI` 字段提取）。对"看不出是 DOI"的输入选择**原样归一
    返回**而非抛异常，理由：①一个"错但一致"归一的值仍是稳定、可确定性合并的键，不会污染
    其它 paper；②抛异常会让合并热路径对上游数据小瑕疵脆弱（宁可入库待人工核，不可炸
    ingest）；③校验属 adapter 职责，不在归一层重复。内部空白不动（DOI 不含空白，保守起见
    不臆测切分）。空串归一为空串。
    """
    cleaned = _DOI_PREFIX_RE.sub("", raw.strip())
    return cleaned.strip().lower()


# ---------------------------------------------------------------------------
# 标题归一（弱信号匹配键）
# ---------------------------------------------------------------------------

# LaTeX 重音宏的重音符号集合（`\'{e}` 里的 `'`）。字符类内均为字面量。
_ACCENT_SYMS = r"`'^\"~=."
# `\'{e}` / `\"{o}` 形——符号重音 + 花括号包一个字母 → 取内层字母。
_LATEX_ACCENT_BRACED = re.compile(r"\\[" + _ACCENT_SYMS + r"]\{([A-Za-z])\}")
# `\'e` / `\^a` 形——符号重音 + 裸字母。
_LATEX_ACCENT_BARE = re.compile(r"\\[" + _ACCENT_SYMS + r"]([A-Za-z])")
# `\c{c}`（cedilla）/ `\H{o}`（double acute）/ `\v{s}` / `\u{a}` 形——单字母命令 +
# 花括号包一个字母 → 取内层字母。单字母命令限定使 `\emph{x}` 类多字母命令不误伤
# （落到下方通用命令剥离）。
_LATEX_LETTER_ACCENT = re.compile(r"\\[A-Za-z]\{([A-Za-z])\}")
# 独立字母宏（`\o`→o、`\ss`→ss、`\ae`→ae…）；负向前瞻避免把 `\lambda` 误切成 `\l`。
_LATEX_STANDALONE = re.compile(r"\\(ss|ae|AE|oe|OE|aa|AA|[oOlLij])(?![A-Za-z])")
_STANDALONE_MAP = {
    "ss": "ss",
    "ae": "ae",
    "AE": "ae",
    "oe": "oe",
    "OE": "oe",
    "aa": "a",
    "AA": "a",
    "o": "o",
    "O": "o",
    "l": "l",
    "L": "l",
    "i": "i",
    "j": "j",
}
# 剩余通用命令（`\emph`、`\textbf`…）——剥命令保留其后花括号里的内容（下一步去括号）。
_LATEX_COMMAND = re.compile(r"\\[A-Za-z]+")
_BRACES = re.compile(r"[{}]")
# 非(字母/数字/空白)一律替换为空格（去标点）；`\w` 保留 Unicode 字母数字（CJK 标题不丢）。
_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)
_WS = re.compile(r"\s+")


def _strip_combining(text: str) -> str:
    """Unicode NFKD 分解后剔除组合重音记号：`é`→`e`、`ő`→`o`、`ñ`→`n`。"""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def normalize_title(raw: str) -> str:
    """标题归一为弱信号匹配键（06 §3：去标点/大小写/LaTeX 宏/空白折叠）。

    步骤（顺序有意）：LaTeX 重音宏剥离（`\\'{e}`→e、`\\H{o}`→o、`\\c{c}`→c、独立字母宏、
    通用命令）→ 去花括号 → Unicode NFKD 重音折叠（`é`→e）→ 大小写折叠 → 去标点（替换为
    空格）→ 空白折叠。目的是让「工作论文版」与「刊发版」在标题排版差异（重音编码/连字符/
    大小写/LaTeX vs Unicode）下仍得到同一匹配键——但**只做精确匹配**，不去停用词、不做词干
    化（06 §3 明确「宁可两条待审」，弱信号只作候审证据，绝不自动合并）。

    覆盖边界：大小写混合、Unicode 重音（NFKD 可分解的拉丁重音）、LaTeX `\\'{e}` 类宏、
    连字符/标点、多空白。非分解型字母（ø/ł/ß 的 Unicode 直写形）保持原样——其 LaTeX 形
    经独立字母宏映射，两形的轻微不对称对弱信号可接受（仅影响候审召回，不影响正确性）。
    空标题→空串。
    """
    text = _LATEX_ACCENT_BRACED.sub(r"\1", raw)
    text = _LATEX_LETTER_ACCENT.sub(r"\1", text)
    text = _LATEX_ACCENT_BARE.sub(r"\1", text)
    text = _LATEX_STANDALONE.sub(lambda m: _STANDALONE_MAP[m.group(1)], text)
    text = _LATEX_COMMAND.sub("", text)
    text = _BRACES.sub("", text)
    text = _strip_combining(text)
    text = text.casefold()
    text = text.replace("_", " ")
    text = _PUNCT.sub(" ", text)
    return _WS.sub(" ", text).strip()


# ---------------------------------------------------------------------------
# identifier 归一（写入唯一入口）
# ---------------------------------------------------------------------------

# doi identifier 归一经 `normalize_doi`；其余 scheme（arxiv/openalex/s2/dblp/anthology…）
# 原样（各自 scheme 语义由 adapter 保证，aggregators.md §6）。
DOI_SCHEME = "doi"


def normalize_identifier(scheme: str, value: str) -> tuple[str, str]:
    """identifier `(scheme, value)` 归一：scheme==doi 的值经 `normalize_doi`，其余原样。

    这是 identifier 写入的**唯一归一入口**（plan §2-1）——`Repo.upsert_paper`（pull 路径）
    与 `MergeEngine`（aggregator/enrich 路径）共用，使两条写路径的 DOI 键归一到同一规范形，
    identifier `(scheme,value)` 全局唯一锚点在大小写/前缀差异下仍天然强合并（D-裁决
    2026-07-22：ISO 26324 DOI 大小写不敏感，归一属语义修正）。
    """
    if scheme == DOI_SCHEME:
        return (scheme, normalize_doi(value))
    return (scheme, value)


__all__ = ["DOI_SCHEME", "normalize_doi", "normalize_identifier", "normalize_title"]
