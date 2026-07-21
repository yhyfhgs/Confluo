"""预印本虚拟月度桶生成（design/adapters/arxiv.md §3 discover_timeline 裁决）。

arXiv 无"期"概念——按 (venue, 年月) 生成虚拟月度桶 `IssueRef`，起点由 venue
YAML `quirks.inception`（'YYYY-MM'）声明（未声明则回退全局起点 `1991-08`——
该回退逻辑属调用方 T5 `discover_timeline` 的职责，本函数只接受已解析好的
`inception` 字符串，不内置默认值）。

字段裁决（arxiv.md §3，逐字执行）：

- ``volume=None``
- ``number='MM'``（两位零填充月份字符串）
- ``year=YYYY``
- ``label='YYYY-MM'``
- ``pub_date=None``
- ``paper_count_claimed=None``（无权威口径）

`upsert_issue` 四列幂等（venue_id, volume, number, label）与 `--year` selector
过滤（走 year 列）由这份字段分解确定性成立。
"""

from collections.abc import Iterator
from datetime import date

from paper_crawler.errors import CrawlerError, ErrorClass
from paper_crawler.types import IssueRef


def month_buckets(venue_id: str, inception: str, until: date) -> Iterator[IssueRef]:
    """从 `inception`（'YYYY-MM'）到 `until` 所在月（含）逐月生成虚拟 Issue 桶。

    `inception` 所在月晚于 `until` 所在月时返回空序列（不抛错——新 venue 的
    inception 尚未到达属正常态，不是异常态）。`inception` 格式非法
    （非 'YYYY-MM'、月份越界等）抛 `CrawlerError(ErrorClass.CONFIG)`——这是
    venue 配置错误，不是抓取到的外部数据解析失败（PARSE 语义）。
    """
    year, month = _parse_inception(inception)
    end_year, end_month = until.year, until.month

    while (year, month) <= (end_year, end_month):
        yield IssueRef(
            venue_id=venue_id,
            volume=None,
            number=f"{month:02d}",
            year=year,
            label=f"{year:04d}-{month:02d}",
            pub_date=None,
            paper_count_claimed=None,
        )
        month += 1
        if month > 12:
            month = 1
            year += 1


def _parse_inception(inception: str) -> tuple[int, int]:
    """把 'YYYY-MM' 解析成 (year, month)；格式非法抛 CrawlerError(CONFIG)。"""
    year_str, sep, month_str = inception.partition("-")
    valid_shape = (
        sep == "-"
        and len(year_str) == 4
        and len(month_str) == 2
        and year_str.isdigit()
        and month_str.isdigit()
    )
    if not valid_shape:
        raise CrawlerError(ErrorClass.CONFIG, f"invalid inception month: {inception!r}")

    year, month = int(year_str), int(month_str)
    if not 1 <= month <= 12:
        raise CrawlerError(ErrorClass.CONFIG, f"invalid inception month: {inception!r}")
    return year, month


__all__ = ["month_buckets"]
