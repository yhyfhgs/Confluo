"""`DblpAdapter.healthcheck` 单测（design/adapters/aggregators.md §5.2/§7）。

**数据来源诚实声明**（先例 `test_pmlr_canary.py`）：固定 canary 目标是真实卷
`conf/icml/icml2023`（design §5.2/§7 明文选定）。**2026-07-23 审查真实交叉
验证**：`GET https://dblp.org/db/conf/icml/icml2023.xml` 已被真实请求一次
（HTTP 200，`content-type: application/xml`），证实该 URL 可达且响应可解析
出 1828 条 `inproceedings`（根 schema 为 `<bht>`，见 `parse.py` 模块 docstring
"双 schema"专节与本文件末尾使用未裁剪真实响应
`11_volume_xml_bht_schema_full_real_icml2023.xml` 的测试）——记录数下限 50
对 1828 显然自洽。**仍然 [PENDING] 的只剩**首条记录标题的逐字精确比对锚点
（本文件/`healthcheck()` 均不做该比对，理由不变：单次审查抓取不构成"人工
核准的 UPDATE_GOLDEN 锚点"，真正的锚点核准走 T5 在线冒烟常态化流程）。

`healthcheck()` 本身**只做结构性判定**（可达 + 能解析 + 记录数不低于保守
下限 + 首条记录字段存在——由 `parse.py` 的构造不变量保证，见
`adapter.py::healthcheck` 注释），不把任何标题精确值当作生产判据硬编码。
本文件前半用可控的合成响应验证该结构性判定逻辑本身的正确性（健康/各类不
健康分支，合成响应现改用与生产一致的 `<bht>/<dblpcites>/<r>` 包装——
2026-07-23 修复前误用了批量导出 `<dblp>` 平铺 schema，对生产实际请求路径
不具代表性）；末尾追加对未裁剪真实响应的端到端验证。
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
    """构造 `record_count` 条合法 `inproceedings` 的合成卷 XML（供"记录数达标"分支）。

    包装用生产实际 schema（`<bht><dblpcites><r>…</r></dblpcites></bht>`，
    2026-07-23 修复：此前误用 `<dblp>{records}</dblp>` 批量导出平铺 schema，
    `healthcheck()` 在生产环境永远不会收到那种响应体）。
    """
    records = "".join(
        f'<r style="ee"><inproceedings key="conf/icml/Canary{i}23">'
        f"<title>Canary Paper {i}.</title>"
        f"<year>2023</year></inproceedings></r>"
        for i in range(record_count)
    )
    return f"<bht><dblpcites>{records}</dblpcites></bht>".encode()


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
    """5 条记录的真实形态 fixture（`10_volume_xml_bht_schema_normal.xml`，
    2 条真实 ICML + 3 条护栏专用合成）本身就低于保守下限——用它验证"记录数
    不足"分支（"结构正常但量级不够"的诚实态：不是 404/解析失败，只是这份
    fixture 本非用于满足 healthcheck 量级判据）。
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=fixture_bytes("10_volume_xml_bht_schema_normal.xml"))

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


# --- 未裁剪真实响应端到端验证（2026-07-23 审查阻断项修复的核心证据）------------------------


def test_healthcheck_healthy_against_full_real_1828_record_capture() -> None:
    """对未裁剪的真实 `icml2023.xml` 响应（1828 条，见 fixture 头注释的抓取
    出处）跑 `healthcheck()`：这是"记录数下限 50 对 1828 成立"这一自洽性
    要求的直接证据——不是靠推断，而是真把这份响应喂给 `healthcheck()` 本体
    走一遍完整逻辑（fetch→parse→阈值判定），零 PARSE、零"记录数不足"。
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=fixture_bytes("11_volume_xml_bht_schema_full_real_icml2023.xml")
        )

    report = _adapter_with(httpx.MockTransport(handler)).healthcheck()
    assert report.healthy is True, report.detail
    assert "1828 record(s)" in report.detail
    assert "conf/icml/AamandACINS23" in report.detail
