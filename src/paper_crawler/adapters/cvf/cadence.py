"""CVF 届表生成：cadence 规则 + overrides（design/adapters/cvf.md §3.1）。

**零网络纯逻辑**：CVF 三会（cvpr/iccv/wacv）的开届节律经勘察证实为**规则**（不同于
ICLR 那样需要逐年查表——见 openreview `venues.py` docstring 的对照），故用内置
「起点 + 节律」常量表生成年份序列，而非逐年显式登记：

- ``cvpr``：起点 2013，逐年（annual）。
- ``iccv``：起点 2013，仅奇数年（biennial_odd，双年制会议）。
- ``wacv``：起点 2020，逐年（annual）。

[LIVE 依据（research/site-survey/cvf.md）]：menu 页 ICCV 年份 2013/15/17/19/21/23/25
全为奇数、``/ICCV2022``（偶数年）404；CVPR 2013→2026 逐年在 menu 出现；WACV 最早
2020、``/WACV2019``→404；``/CVPR2012``→404（CVF 收录边界）。

`quirks.cvf_edition_overrides`（``dict[year → 'include'|'exclude']``，可选）是
cadence 规则无法表达的例外（临时停办/补办/节律变更）的修正通道，**不改常量表**
（先例 openreview ``openreview_group_overrides``）；仅在 ``[inception, current_year]``
窗口内生效——不用于延伸生成区间本身（该区间恒为"起点→当前年，不产未来届"）。

`current_year` 由调用方（adapter）显式传入而非本模块读取时钟：cadence 生成依赖
"现在是哪一年"，把它做成参数而非模块内 ``datetime.now()`` 调用，使上层可以在测试中
注入固定年份保证确定性（design §6 T4 "测试注入固定当前年"裁决）。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from paper_crawler.errors import CrawlerError, ErrorClass
from paper_crawler.types import VenueSpec


class Cadence(StrEnum):
    """一个 venue 的开届节律。"""

    ANNUAL = "annual"
    BIENNIAL_ODD = "biennial_odd"  # 仅奇数年（ICCV 双年制）


@dataclass(frozen=True)
class CadenceSpec:
    """一个 venue 的 cadence 常量：起点年 + 节律。"""

    inception: int
    cadence: Cadence


# 内置 cadence 表（design §3.1；venue id 键取，Phase 2 范围仅这三个）。
_CADENCE_TABLE: dict[str, CadenceSpec] = {
    "cvpr": CadenceSpec(inception=2013, cadence=Cadence.ANNUAL),
    "iccv": CadenceSpec(inception=2013, cadence=Cadence.BIENNIAL_ODD),
    "wacv": CadenceSpec(inception=2020, cadence=Cadence.ANNUAL),
}

_OVERRIDES_QUIRK = "cvf_edition_overrides"
_VALID_ACTIONS = frozenset({"include", "exclude"})


def _cadence_default_included(spec: CadenceSpec, year: int) -> bool:
    """cadence 规则本身（无 overrides 介入）对 `year` 的默认取舍。"""
    if year < spec.inception:
        return False
    if spec.cadence is Cadence.ANNUAL:
        return True
    return year % 2 == 1  # BIENNIAL_ODD


def _coerce_year(raw: object) -> int:
    """把 overrides 的年键归一为 int（YAML 未加引号得 int，加引号得 str）。"""
    if isinstance(raw, bool):  # bool 是 int 子类——显式挡掉，避免 True→1 之类的怪值
        raise CrawlerError(ErrorClass.CONFIG, f"{_OVERRIDES_QUIRK} 的年键不能是布尔: {raw!r}")
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str):
        try:
            return int(raw.strip())
        except ValueError:
            raise CrawlerError(
                ErrorClass.CONFIG, f"{_OVERRIDES_QUIRK} 的年键不是合法年份: {raw!r}"
            ) from None
    raise CrawlerError(ErrorClass.CONFIG, f"{_OVERRIDES_QUIRK} 的年键类型非法: {raw!r}")


def _coerce_action(raw: object) -> str:
    """overrides 的值必须是 'include'/'exclude' 字符串（大小写不敏感、去空白）。"""
    if isinstance(raw, str) and raw.strip().lower() in _VALID_ACTIONS:
        return raw.strip().lower()
    raise CrawlerError(
        ErrorClass.CONFIG,
        f"{_OVERRIDES_QUIRK} 的值必须是 'include' 或 'exclude'，实际: {raw!r}",
    )


def resolve_overrides(venue: VenueSpec) -> dict[int, str]:
    """解析 `quirks.cvf_edition_overrides` 为 ``dict[year, 'include'|'exclude']``。

    缺省（未声明该 quirk）返回空 dict——纯 cadence 规则生效、无修正。畸形值
    （非 dict / 年键非法 / 值非 include|exclude）早失败为 CONFIG（venue 配置缺陷，
    响亮停机，不是抓取到的外部数据解析失败）。
    """
    raw_overrides = venue.quirks.get(_OVERRIDES_QUIRK)
    if raw_overrides is None:
        return {}
    if not isinstance(raw_overrides, dict):
        kind = type(raw_overrides).__name__
        raise CrawlerError(
            ErrorClass.CONFIG,
            f"quirks.{_OVERRIDES_QUIRK} 必须是 dict[year→'include'|'exclude']，实际是 {kind}",
        )
    return {_coerce_year(k): _coerce_action(v) for k, v in raw_overrides.items()}


def edition_years(
    venue: VenueSpec, *, current_year: int, since_year: int | None = None
) -> list[int]:
    """`venue` 的 cadence 届年列表（升序）：``[inception, current_year]`` 窗口内。

    每年的默认取舍由 cadence 规则给出（`_cadence_default_included`），overrides
    可在该窗口内 include/exclude 单年修正（不延伸窗口本身——`current_year` 恒为
    上界，"不产未来届"）。`since_year` 非 None 时收窄下界到 ``>= since_year``
    （discover_timeline 的 `since` 增量发现下界裁剪，§3.1）。

    `venue.id` 不在内置 cadence 表中（超出 Phase 2 范围的 cvpr/iccv/wacv 三会）
    → CONFIG（路由缺陷：venue YAML 把 metadata_source 指向本 adapter 却给了
    未登记的 id）。
    """
    spec = _CADENCE_TABLE.get(venue.id)
    if spec is None:
        raise CrawlerError(
            ErrorClass.CONFIG,
            f"cvf adapter 无 venue {venue.id!r} 的内置 cadence（已登记: {sorted(_CADENCE_TABLE)}）",
        )
    overrides = resolve_overrides(venue)

    years: list[int] = []
    for year in range(spec.inception, current_year + 1):
        included = _cadence_default_included(spec, year)
        action = overrides.get(year)
        if action == "include":
            included = True
        elif action == "exclude":
            included = False
        if included:
            years.append(year)

    if since_year is not None:
        years = [y for y in years if y >= since_year]
    return years


__all__ = ["Cadence", "CadenceSpec", "edition_years", "resolve_overrides"]
