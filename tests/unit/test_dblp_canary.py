"""`DblpAdapter.healthcheck` 单测（design/adapters/aggregators.md §5.2/§7）。

**数据来源诚实声明**（先例 `test_pmlr_canary.py`）：固定 canary 目标是真实卷
`conf/icml/icml2023`（design §5.2/§7 明文选定），但其"已知答案"精确值（首条
记录的真实 title、真实记录数）**未经本次实现的在线核验** [PENDING]——本次
实现零真实网络（`PAPER_CRAWLER_CONTACT_EMAIL` 未设，按 D-014 约定全走合成
路径）。因此 `healthcheck()` 本身**只做结构性判定**（可达 + 能解析 + 记录数
不低于保守下限 + 首条记录字段存在——由 `parse.py` 的构造不变量保证，见
`adapter.py::healthcheck` 注释），**不**把任何合成标题当作生产判据硬编码；
本文件用可控的合成响应验证该结构性判定逻辑本身的正确性（健康/各类不健康
分支），真实站点是否漂移是 T5 在线冒烟与 `crawler canary` 的职责，不在本文件
范围。真实记录数/首条 title 的精确锚点待 T5 在线冒烟实测后按 UPDATE_GOLDEN
纪律补充（同 aggregators.md §7 dblp 行 [PENDING] 标注）。
"""

from __future__ import annotations

import httpx

from helpers.dblp_fixtures import fixture_bytes, http_fixture
from paper_crawler.adapters.dblp.adapter import DblpAdapter
from paper_crawler.http import HttpClient

_UA = "PaperCrawler/test (personal research; mailto:test@example.com)"
_HEALTHCHECK_URL = "https://dblp.org/db/conf/icml/icml2023.xml"


def _adapter_with(handler: httpx.MockTransport) -> DblpAdapter:
    return DblpAdapter(http=HttpClient(user_agent=_UA, transport=handler))


def _synthetic_volume_xml(record_count: int) -> bytes:
    """构造 `record_count` 条合法 `inproceedings` 的合成卷 XML（供"记录数达标"分支）。"""
    records = "".join(
        f'<inproceedings key="conf/icml/Canary{i}23"><title>Canary Paper {i}.</title>'
        f"<year>2023</year></inproceedings>"
        for i in range(record_count)
    )
    return f"<dblp>{records}</dblp>".encode()


def test_healthcheck_fetches_the_fixed_icml2023_canary_url() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, content=_synthetic_volume_xml(50))

    _adapter_with(httpx.MockTransport(handler)).healthcheck()
    assert seen == [_HEALTHCHECK_URL]


def test_healthcheck_healthy_when_record_count_meets_conservative_floor() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=_synthetic_volume_xml(50))

    report = _adapter_with(httpx.MockTransport(handler)).healthcheck()
    assert report.healthy is True
    assert "50 record(s)" in report.detail
    assert "conf/icml/Canary0" in report.detail


def test_healthcheck_unhealthy_when_below_conservative_floor() -> None:
    """真实的 5 条记录合成 fixture（`04_volume_xml_normal.xml`）本身就低于保守下限
    ——用它直接验证"记录数不足"分支（同时是"结构正常但量级不够"的诚实态：不是
    404/解析失败，只是这份 fixture 本非用于满足 healthcheck 量级判据）。
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=fixture_bytes("04_volume_xml_normal.xml"))

    report = _adapter_with(httpx.MockTransport(handler)).healthcheck()
    assert report.healthy is False
    assert "conservative floor" in report.detail


def test_healthcheck_unhealthy_when_zero_records() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=fixture_bytes("05_volume_xml_empty.xml"))

    report = _adapter_with(httpx.MockTransport(handler)).healthcheck()
    assert report.healthy is False
    assert "0 inproceedings records" in report.detail


def test_healthcheck_unhealthy_when_parse_fails() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=fixture_bytes("06_volume_xml_malformed.xml"))

    report = _adapter_with(httpx.MockTransport(handler)).healthcheck()
    assert report.healthy is False
    assert "parse failed" in report.detail


def test_healthcheck_unhealthy_when_unreachable() -> None:
    status, headers, body = http_fixture("09_server_error_500.http")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, headers=headers, content=body)

    report = _adapter_with(httpx.MockTransport(handler)).healthcheck()
    assert report.healthy is False
    assert "unreachable" in report.detail
    assert "transient" in report.detail
