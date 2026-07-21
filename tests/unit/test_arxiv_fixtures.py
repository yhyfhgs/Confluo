"""八件套（+ 补充件）合成 fixture 的有效性验证（Phase 2 T5）。

目的：证明 `tests/fixtures/arxiv/raw/` 的合成 fixture 结构合法、且经解析器/嗅探/HttpClient
状态映射后落到各自声明的 error_class / 形态——既给 fixture 文件本身上覆盖网、又在 T7 用真实
响应重录时充当「回归基线」。真实网络零依赖：⑥/⑧ 的状态码经 `httpx.MockTransport` 复现。
"""

from __future__ import annotations

import httpx
import pytest

from helpers.arxiv_fixtures import fixture_bytes, http_fixture
from paper_crawler.adapters.arxiv import parse
from paper_crawler.adapters.arxiv.adapter import _gone_guarded_stream
from paper_crawler.errors import CrawlerError, ErrorClass
from paper_crawler.http import HttpClient

_UA = "PaperCrawler/test (personal research; mailto:test@example.com)"


def test_fixture_01_query_atom_normal_has_ten_records_both_generations() -> None:
    records = list(parse.parse_atom_feed(fixture_bytes("01_query_atom_normal.xml")))
    assert len(records) == 10
    base_ids = {r.base_id for r in records}
    assert "2401.10001" in base_ids  # 新代
    assert "hep-th/9901001" in base_ids  # 老代
    lead = next(r for r in records if r.base_id == "2401.10001")
    assert lead.version == 2  # v2 后缀
    assert lead.primary_category == "cs.LG"
    assert lead.journal_ref == "Proc. Example ML Conf. 2024, pp. 1-12"
    assert lead.doi == "10.1000/ex.2024.10001"


def test_fixture_02_oai_page1_records_token_and_tombstone_count() -> None:
    page = parse.parse_oai_page(fixture_bytes("02_oai_listrecords_page1.xml"))
    assert tuple(r.base_id for r in page.records) == ("2401.10001", "2401.10002")
    assert page.skipped_tombstones == 1  # 1 条 deleted 墓碑
    assert page.resumption_token == "cs|2024-01|1000"


def test_fixture_02_oai_page2_is_last_page_with_old_style_id() -> None:
    page = parse.parse_oai_page(fixture_bytes("02_oai_listrecords_page2.xml"))
    assert tuple(r.base_id for r in page.records) == ("cs.lg/0401001", "2401.10003")
    assert page.resumption_token is None  # 收割结束
    assert page.skipped_tombstones == 0


def test_fixture_03_query_atom_empty_yields_no_records() -> None:
    assert list(parse.parse_atom_feed(fixture_bytes("03_query_atom_empty.xml"))) == []


def test_fixture_04_total_mismatch_is_parse_error() -> None:
    with pytest.raises(CrawlerError) as exc:
        list(parse.parse_atom_feed(fixture_bytes("04_query_atom_total_mismatch.xml")))
    assert exc.value.error_class is ErrorClass.PARSE


def test_fixture_05_withdrawn_html_is_sniffed_gone() -> None:
    with pytest.raises(CrawlerError) as exc:
        list(_gone_guarded_stream([fixture_bytes("05_pdf_withdrawn.html")]))
    assert exc.value.error_class is ErrorClass.GONE


def test_fixture_06_oai_503_retry_after_maps_to_rate_limited() -> None:
    status, headers, body = http_fixture("06_oai_503_retry_after.http")
    assert status == 503
    assert headers["Retry-After"] == "120"

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, headers=headers, content=body)

    client = HttpClient(user_agent=_UA, transport=httpx.MockTransport(handler))
    with pytest.raises(CrawlerError) as exc:
        client.get_bytes("https://oaipmh.arxiv.org/oai")
    assert exc.value.error_class is ErrorClass.RATE_LIMITED
    assert "retry_after_s=120" in exc.value.detail


def test_fixture_07_bad_resumption_token_is_transient() -> None:
    with pytest.raises(CrawlerError) as exc:
        parse.parse_oai_page(fixture_bytes("07_oai_bad_resumption_token.xml"))
    assert exc.value.error_class is ErrorClass.TRANSIENT


def test_fixture_08_query_400_offset_maps_to_config() -> None:
    body = fixture_bytes("08_query_400_offset.xml")

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, content=body)

    client = HttpClient(user_agent=_UA, transport=httpx.MockTransport(handler))
    with pytest.raises(CrawlerError) as exc:
        client.get_bytes("https://export.arxiv.org/api/query?start=30001")
    assert exc.value.error_class is ErrorClass.CONFIG


def test_fixture_09_healthcheck_canaries_present() -> None:
    feed = parse.parse_atom_feed(fixture_bytes("09_query_atom_healthcheck.xml"))
    records = {r.base_id: r for r in feed}
    assert set(records) == {"2401.00001", "2312.00002", "2311.00003"}
    assert records["2311.00003"].primary_category == "q-fin.PR"


def test_fixture_10_norecordsmatch_is_legal_empty_state() -> None:
    page = parse.parse_oai_page(fixture_bytes("10_oai_norecordsmatch.xml"))
    assert page.records == ()
    assert page.resumption_token is None
