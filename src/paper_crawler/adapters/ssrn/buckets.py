"""SSRN 零网络虚拟年桶生成（design/adapters/ssrn.md §4.3；controller 发现①仲裁令）。

**纯生成**（controller 仲裁令 2026-07-24，发现①）：T1 在线实测真实 Crossref
`filter=prefix:10.2139&facet=created:*` 返 **HTTP 400 facet-not-available**（`created` 非
该路由合法 facet；活体哨兵见 `tests/online/test_crossref_prefix_smoke.py::
test_prefix_created_facet_ssrn` XFAIL）——原 §4.3「1 请求 created facet 产年桶」**不可实现**。
仲裁改**纯本地生成** 1990..今年 逐年 `IssueRef`：零请求、零 facet 依赖（arxiv 月度桶纯
生成同构，arxiv.md §3）。规模锚（`paper_count_claimed`）职责移交 M1 census——本层恒 None。

字段裁决（§4.3，逐字）：``volume=None``、``number=None``、``year=YYYY``、``label='YYYY'``、
``pub_date=None``、``paper_count_claimed=None``。幂等键 **(venue, year)**——`upsert_issue`
四列 (venue_id, volume, number, label) 在 volume/number=None 下退化为 (venue, label='YYYY')，
`--year` selector 走 year 列过滤（同 arxiv 月度桶字段分解）。
"""

from collections.abc import Iterator

from paper_crawler.types import IssueRef


def year_buckets(venue_id: str, start_year: int, end_year: int) -> Iterator[IssueRef]:
    """从 `start_year` 到 `end_year`（**含**）逐年生成虚拟 Issue 桶（零网络）。

    `start_year > end_year`（下界晚于上界"今年"）→ **空序列**（不抛错——新 venue 起点未到
    或 since 越界属正常态，非异常，同 arxiv `month_buckets` 先例）。**脏未来年天然不产**：
    纯生成连续区间 ``[start, end]``、上界 = 今年（clock 注入），故旧 facet 方案里的脏未来
    年（2077/2103/2104）根本不出现（无 facet 数据可污染，§4.3）。
    """
    for year in range(start_year, end_year + 1):
        yield IssueRef(
            venue_id=venue_id,
            volume=None,
            number=None,
            year=year,
            label=f"{year:04d}",
            pub_date=None,
            paper_count_claimed=None,
        )


__all__ = ["year_buckets"]
