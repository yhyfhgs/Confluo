"""AEA DOI 双形态容错解析器 + code→venue 8 刊路由表（design/adapters/aea.md §3.2）。

零网络纯函数模块（本模块自身不做任何 I/O 或日志——沿 crossref `parse.py` "解析层只
产结构化结果，观测/日志留给 adapter.py 上层" 的先例）。`10.1257/{code}.{suffix}` 的
`code` 段**不等于** venue id（如 `mac` → `aej_macro`）——`CODE_TO_VENUE` 是权威路由表
（aea.md §7 命名清单）。`suffix` 有三种历史形态（§3.2，仅供展示/元数据，**不作路由
键**）：

- **submission**（近年 8 位投稿号，如 `20230344`，含隐式年）；
- **vol_issue_page**（早年 `卷.期.页`，如 `106.6.i`——页可为罗马数字/front matter）；
- **pnp**（AEA Papers & Proceedings：`aer.p{8 位}` 如 `aer.p20151048`，或独立 code
  `pandp.{...}` 如 `pandp.116.742`）。

**容错契约（§3.2"任一形态不得抛错"）**：`parse_doi` 对任何输入字符串都不抛异常——
非 `10.1257/` 前缀返回 `None`（非本 adapter 的 DOI，调用方按路由错配处理）；前缀匹配
但 code/suffix 形态怪异时仍返回一个 `ParsedAeaDoi`（`doi_form="unknown"`），绝不
raise。

**P&P 特判优先于普通 code 路由**（§7 A-3 裁决："pnp 形态识别，venue 本 Phase 不落"）：
无论 code 是什么，suffix 命中 pnp 形态（或 code 本身即 `pandp`）→ `venue_id=None`，
即便 code 本身在 `CODE_TO_VENUE` 表中（如 `aer.p20151048` 的 code=`aer` 在表中，但
pnp 形态优先判定为暂缓，不路由到 `aer`）。

**未知 code**（不在表中，且非 P&P 形态）→ `venue_id=None`；调用方（`adapter.py`）据此
决定是否记一条 WARN 观测（§3.2"防新子刊上线"）——本模块自身不区分"未知 code"与
"已知但暂缓的 P&P"，两者都表现为 `venue_id=None`，调用方靠 `doi_form=="pnp"` 判别
是否该 WARN（P&P 是预期内暂缓，不该 WARN；真正未知 code 才该 WARN）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final, Literal

# --- 常量 --------------------------------------------------------------------------------------

DOI_PREFIX: Final[str] = "10.1257/"

DoiForm = Literal["submission", "vol_issue_page", "pnp", "unknown"]

# code→venue 路由表（aea.md §7 命名清单；catalog 蛇形命名，A-2 裁决）。`pandp` 故意
# 不入表——P&P venue 暂缓（A-3），查表天然 miss；下方 `parse_doi` 用专属分支识别它
# （`doi_form="pnp"`），不会被误当"未知子刊"。
CODE_TO_VENUE: Final[dict[str, str]] = {
    "aer": "aer",
    "aeri": "aeri",
    "mac": "aej_macro",
    "app": "aej_applied",
    "mic": "aej_micro",
    "pol": "aej_policy",
    "jel": "jel",
    "jep": "jep",
}

_SUBMISSION_RE = re.compile(r"^\d{8}$")  # 8 位投稿号（如 "20230344"）
_PNP_SUFFIX_RE = re.compile(r"^p\d{8}$")  # P&P 投稿号后缀（如 "p20151048"）
_PANDP_CODE = "pandp"


# --- 数据结构 ----------------------------------------------------------------------------------


@dataclass(frozen=True)
class ParsedAeaDoi:
    """`parse_doi` 的解析结果（§3.2"解析器产 (venue_id, doi_form, raw) 三元组"——本类
    额外携 `code`/`suffix` 供调试/观测消费）。"""

    code: str  # 归一小写的 DOI 子前缀（如 "aer"/"mac"/"pandp"）
    suffix: str  # code 之后的原始后缀（如 "20230344"/"106.6.i"/"p20151048"）
    doi_form: DoiForm
    venue_id: str | None  # code→venue 路由结果；P&P/未知 code → None
    raw: str  # 原始 DOI（已 strip，大小写原样保留）


# --- 解析器 ------------------------------------------------------------------------------------


def parse_doi(doi: str) -> ParsedAeaDoi | None:
    """`10.1257/{code}.{suffix}` 容错解析；非该前缀 → `None`（非本 adapter 的 DOI）。

    前缀比对大小写不敏感（Crossref DOI 前缀惯例全小写，但防御性兼容异常大写输入）；
    `code` 归一小写（`CODE_TO_VENUE` 键全小写）；`suffix`/`raw` 保留原始大小写
    （suffix 形态判定——8 位数字/含点——不受大小写影响）。
    """
    raw = doi.strip()
    if not raw.lower().startswith(DOI_PREFIX):
        return None

    rest = raw[len(DOI_PREFIX) :]
    if "." not in rest:
        # 畸形：无 code.suffix 分隔（如裸 "10.1257/aer"）——容错不崩，整串作 code、
        # suffix 空。仍尝试路由（一个只有 code 无 suffix 的 DOI 若恰是已知 code，
        # 宽容地路由；未知则 None，与正常路径一致）。
        code_lower = rest.lower()
        return ParsedAeaDoi(
            code=code_lower,
            suffix="",
            doi_form="unknown",
            venue_id=CODE_TO_VENUE.get(code_lower),
            raw=raw,
        )

    code, suffix = rest.split(".", 1)
    code_lower = code.lower()

    if code_lower == _PANDP_CODE or _PNP_SUFFIX_RE.match(suffix):
        # P&P 特判（§7 A-3）：优先于普通 code 路由判定——恒不路由，不管 code 是否
        # 恰好在表中（如 aer.p*）。
        return ParsedAeaDoi(code=code_lower, suffix=suffix, doi_form="pnp", venue_id=None, raw=raw)

    doi_form: DoiForm
    if _SUBMISSION_RE.match(suffix):
        doi_form = "submission"
    elif "." in suffix:
        doi_form = "vol_issue_page"
    else:
        doi_form = "unknown"

    return ParsedAeaDoi(
        code=code_lower,
        suffix=suffix,
        doi_form=doi_form,
        venue_id=CODE_TO_VENUE.get(code_lower),
        raw=raw,
    )


__all__ = ["CODE_TO_VENUE", "DOI_PREFIX", "DoiForm", "ParsedAeaDoi", "parse_doi"]
