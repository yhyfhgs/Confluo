"""OpenReview 届表常量与解析（design/adapters/openreview.md §2/§4）。

**零网络纯逻辑**：把「年 → 主会 venue group id」的权威映射编码为内置常量表，并提供
`quirks.openreview_group_overrides` 覆盖通道的合并逻辑。届表**不能硬编码模板拼接**
（勘察 §2 证伪：2013-2017 小写 `conference`、2018+ 大写 `Conference`、2015/2016 主会
缺失）——必须逐年查表。

内置表按 venue id 键取（Phase 2 范围仅 `iclr`）；未登记的 venue 内置表为空，只有
overrides 生效。表值语义：``str`` = 该年主会 group id（大小写原样、精确）；``None``
= 该年主会不在 OpenReview（平台事实缺届，discover 不产 Issue）。
"""

from __future__ import annotations

from paper_crawler.errors import CrawlerError, ErrorClass
from paper_crawler.types import VenueSpec

# --- ICLR 权威届表（勘察 §2 [LIVE] 逐年实测；2013→2027）---------------------------------------
#
# 大小写不一致是平台事实、不可硬编码：2013/2014/2017 小写 `conference`，2018 起大写
# `Conference`。2015 主会在 venues 主表缺失、2016 仅有 workshop 无 conference 卷——两届
# 均 None（timeline 呈现「缺届」，与 AC-2.1 anchor 表同口径）。2026/2027 为已建的未来届。
_ICLR_TABLE: dict[int, str | None] = {
    2013: "ICLR.cc/2013/conference",  # 小写
    2014: "ICLR.cc/2014/conference",  # 小写
    2015: None,  # 主会缺失（venues 主表无 ICLR.cc/2015/*）
    2016: None,  # 仅 workshop，无 conference 卷
    2017: "ICLR.cc/2017/conference",  # 小写
    2018: "ICLR.cc/2018/Conference",  # 自此起大写 C
    2019: "ICLR.cc/2019/Conference",
    2020: "ICLR.cc/2020/Conference",
    2021: "ICLR.cc/2021/Conference",
    2022: "ICLR.cc/2022/Conference",
    2023: "ICLR.cc/2023/Conference",
    2024: "ICLR.cc/2024/Conference",
    2025: "ICLR.cc/2025/Conference",
    2026: "ICLR.cc/2026/Conference",  # 未来届（已建）
    2027: "ICLR.cc/2027/Conference",  # 占位已存在
}

# venue id → 内置届表。Phase 2 仅 iclr（design §1）；NeurIPS/其它系列推迟。
_BUILTIN_TABLES: dict[str, dict[int, str | None]] = {
    "iclr": _ICLR_TABLE,
}

_OVERRIDES_QUIRK = "openreview_group_overrides"


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


def _coerce_venueid(raw: object) -> str | None:
    """overrides 的值归一：非空 str = 该年 group id；None/空白 = 掩掉该年（不产 Issue）。"""
    if raw is None:
        return None
    if isinstance(raw, str):
        stripped = raw.strip()
        return stripped or None
    raise CrawlerError(ErrorClass.CONFIG, f"{_OVERRIDES_QUIRK} 的值必须是字符串或 null: {raw!r}")


def resolve_venue_table(venue: VenueSpec) -> dict[int, str | None]:
    """内置届表 ∪ `quirks.openreview_group_overrides`（overrides 覆盖/新增/掩届）。

    合并语义：以内置表为底，overrides 逐年覆盖——值为字符串即设/改该年 group id，
    值为 null 即掩掉该年（新届修正、命名规约漂移的兜底通道，design §4/§8）。年键经
    `_coerce_year` 归一为 int；畸形键/值早失败为 CONFIG（venue YAML 缺陷，响亮停机）。
    """
    table: dict[int, str | None] = dict(_BUILTIN_TABLES.get(venue.id, {}))
    raw_overrides = venue.quirks.get(_OVERRIDES_QUIRK)
    if raw_overrides is None:
        return table
    if not isinstance(raw_overrides, dict):
        kind = type(raw_overrides).__name__
        raise CrawlerError(
            ErrorClass.CONFIG,
            f"quirks.{_OVERRIDES_QUIRK} 必须是 dict[year→id]，实际是 {kind}",
        )
    for raw_year, raw_id in raw_overrides.items():
        table[_coerce_year(raw_year)] = _coerce_venueid(raw_id)
    return table


def issue_years(venue: VenueSpec, *, since_year: int | None = None) -> list[tuple[int, str]]:
    """产出 (year, venueid) 有序列表：仅含有主会 group id 的年（None 掩届被剔除）。

    升序（年份即时间序）；`since_year` 非 None 时收窄到 ``>= since_year``（增量发现）。
    2015/2016（内置 None）天然不出现——discover「缺届」与 anchor 表同口径。
    """
    table = resolve_venue_table(venue)
    out: list[tuple[int, str]] = []
    for year in sorted(table):
        venueid = table[year]
        if venueid is None:
            continue
        if since_year is not None and year < since_year:
            continue
        out.append((year, venueid))
    return out


__all__ = ["issue_years", "resolve_venue_table"]
