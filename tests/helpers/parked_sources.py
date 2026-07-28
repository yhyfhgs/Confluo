"""watch 侧"停放源"清单——`SOURCE_FIELDS` 收缩后各张源表的差集**单一权威源**（R2b/P0-4）。

放在 `helpers/` 而非某个测试模块里，理由同 `zero_network.py`：该差集有**四个**消费方
（`test_subs_watch.py` 的 `_COMPOSERS`/`MERGE_SOURCE`/`_DELIVERABLE_PARAMS` 三条集合
断言 + `test_subs_watermark.py` 的 `STRATEGIES` 一条 + `test_subs_types.py` 的
`DATE_WINDOW_PARAMS` 一条），各写一份字面量必然漂移。

## 为什么会有差集

openalex/s2 的 `capabilities` 是空集（enrich-only），watch 侧结构性不可达，故已退出
`model.SOURCE_FIELDS`（用户不能再声明这两个源）。但 `subs/watch.py`（请求合成器、
来源身份表、参数下达面表）与 `subs/watermark.py`（增量策略表）里对应的条目**保留**：

1. R2b 的授权范围明确排除"碰 watch.py 主体逻辑"；
2. 这些条目是纯数据/纯函数，没有它们就没有"跑必炸"那条路——真正的断裂点是
   `AdapterFetcher` 调 `discover_timeline`，那一步现在已被白名单挡在门外；
3. R4 若裁决实装两源的 DISCOVER/ENUMERATE 时间轴，这几张表逐字可用。

## 断言形态：包含 + 差集等值，而不是放宽成 `>=`

只写 `set(表) >= set(SOURCE_FIELDS)` 会把"某张表多出一个**别的**源"这种真漂移一并
放行。故各消费方一律两条一起断言：覆盖全部 DSL 源 **且** 多出来的恰好是本集合。
"""

from __future__ import annotations

from collections.abc import Iterable

PARKED_WATCH_SOURCES = frozenset({"openalex", "s2"})


def assert_covers_dsl_sources(
    table_keys: Iterable[str], dsl_sources: Iterable[str], *, name: str
) -> None:
    """某张 watch 侧源表的键集 == DSL 源集 ∪ 停放集（两个方向都锁死）。

    两个入参都按可迭代收进 `set`——传 dict 即取其键集（`_COMPOSERS`/`MERGE_SOURCE`/
    `STRATEGIES`/`DATE_WINDOW_PARAMS` 都是 dict），传 frozenset 即其本身
    （`SUPPORTED_SOURCES`）。
    """
    keys = set(table_keys)
    sources = set(dsl_sources)
    assert keys >= sources, f"{name} 漏了 DSL 源: {sorted(sources - keys)}"
    assert keys - sources == PARKED_WATCH_SOURCES, (
        f"{name} 多出的键必须恰为停放源 {sorted(PARKED_WATCH_SOURCES)}，"
        f"实际多出 {sorted(keys - sources)}"
    )


__all__ = ["PARKED_WATCH_SOURCES", "assert_covers_dsl_sources"]
