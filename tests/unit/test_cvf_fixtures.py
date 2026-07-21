"""cvf 十件套 fixture 保真/落点测试（design/adapters/cvf.md §6 T3）。

每件 fixture → 预期解析形态或 error_class 落点：§5 全部 error_class（gone/parse/
rate_limited/transient/config）各有落点，覆盖两个层次——纯解析层（`parse.*` 直调
+ golden 快照）与端到端层（`CVFAdapter.enumerate_issue` 经 `httpx.MockTransport`
回放，证真实 URL 探测/双请求分支/错误传播全链路正确，非仅解析器孤立正确）。
零真实网络。
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from helpers import make_cvf_venue
from helpers.cvf_fixtures import fixture_text, http_fixture
from helpers.golden import assert_matches_golden
from paper_crawler.adapters.cvf import parse
from paper_crawler.adapters.cvf.adapter import CVFAdapter
from paper_crawler.errors import CrawlerError, ErrorClass
from paper_crawler.http import HttpClient
from paper_crawler.types import IssueRef

_UA = "PaperCrawler/test (personal research; mailto:test@example.com)"
_GOLDEN_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "cvf" / "golden"

_CVPR2023_URL = "https://openaccess.thecvf.com/CVPR2023?day=all"
_CVPR2013_URL = "https://openaccess.thecvf.com/CVPR2013"


# --- 件①：现代 ?day=all 列表页正常节选（纯解析层 + golden）----------------------------------


def test_01_day_all_normal_parses_four_entries_with_expected_field_combos() -> None:
    entries = parse.parse_list_page(fixture_text("01_cvpr2023_day_all_normal.html"))
    assert len(entries) == 4

    gfpose, diffusion, stereo, minimal = entries
    assert gfpose.title == "GFPose: Learning 3D Human Pose Prior With Gradient Fields"
    assert gfpose.pdf_href and gfpose.supp_href and gfpose.arxiv_href  # 全齐

    assert diffusion.pdf_href and diffusion.arxiv_href
    assert diffusion.supp_href is None  # 有 pdf 无 supp

    assert stereo.pdf_href and stereo.supp_href
    assert stereo.arxiv_href is None  # 有 pdf 无 arXiv

    assert minimal.pdf_href
    assert minimal.supp_href is None and minimal.arxiv_href is None  # 仅 pdf


def test_01_day_all_normal_golden() -> None:
    """Closes: T3 件① 期望解析 golden（design §6 件⑤）。"""
    entries = parse.parse_list_page(fixture_text("01_cvpr2023_day_all_normal.html"))
    stubs = [
        parse.to_paper_stub(e, base_url=_CVPR2023_URL, canonical_dir="CVPR2023", year=2023)
        for e in entries
    ]
    assert_matches_golden(stubs, _GOLDEN_DIR / "01_day_all_normal.json")


# --- 件②：2013 flat 列表页节选（纯解析层 + golden）--------------------------------------------


def test_02_flat_2013_parses_two_entries_with_relative_hrefs() -> None:
    entries = parse.parse_list_page(fixture_text("02_cvpr2013_flat_normal.html"))
    assert len(entries) == 2
    for entry in entries:
        assert entry.pdf_href is not None
        assert not entry.pdf_href.startswith("http")  # 相对路径（era 特征）
        assert entry.pdf_href.startswith("content_cvpr_2013/")  # 旧目录名


def test_02_flat_2013_golden() -> None:
    """Closes: T3 件② 期望解析 golden（design §6 件⑤）。"""
    entries = parse.parse_list_page(fixture_text("02_cvpr2013_flat_normal.html"))
    stubs = [
        parse.to_paper_stub(e, base_url=_CVPR2013_URL, canonical_dir="CVPR2013", year=2013)
        for e in entries
    ]
    assert_matches_golden(stubs, _GOLDEN_DIR / "02_flat_2013.json")


# --- 件③：day-landing 页（触发二次 ?day=all 探测的判据）---------------------------------------


def test_03_day_landing_has_no_entries_but_has_day_all_link() -> None:
    html = fixture_text("03_cvpr2023_day_landing.html")
    assert parse.parse_list_page(html) == []
    assert parse.has_day_all_link(html) is True


# --- 件④：详情页（citation_* meta + abstract；不被 Phase 2 enumerate 消费，留证）---------------


def test_04_detail_page_carries_citation_meta_and_abstract_not_consumed_by_enumerate() -> None:
    html = fixture_text("04_cvpr2023_detail_page.html")
    assert 'name="citation_title"' in html
    assert 'id="abstract"' in html
    assert 'name="citation_doi"' not in html  # CVF 版不分配 DOI（design §3 断言）
    # 本 fixture 是"未来 abstract 回填"留证，Phase 2 enumerate 不读详情页——
    # parse.py 没有详情页解析函数，此处只做存在性/字段留证，不做行为断言。


# --- 件⑦：结构漂移页（端到端：经 CVFAdapter.enumerate_issue 证 PARSE 传播全链路）---------------


def test_07_structural_drift_propagates_parse_through_full_adapter() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        html = fixture_text("07_structural_drift_200.html")
        return httpx.Response(200, content=html.encode("utf-8"))

    client = HttpClient(user_agent=_UA, transport=httpx.MockTransport(handler))
    adapter = CVFAdapter(http=client)
    with pytest.raises(CrawlerError) as exc:
        list(
            adapter.enumerate_issue(
                make_cvf_venue("cvpr"), IssueRef(venue_id="cvpr", year=2023, label="2023")
            )
        )
    assert exc.value.error_class is ErrorClass.PARSE


# --- 端到端：modern day_landing→day_all 与 flat 两条完整流程（拼合件①③②）---------------------


def test_modern_flow_bare_day_landing_then_day_all_uses_fixtures_3_and_1() -> None:
    """件③（day-landing，bare 响应）→ 件①（?day=all，全集）——modern 两请求全流程。"""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("day") == "all":
            html = fixture_text("01_cvpr2023_day_all_normal.html")
        else:
            html = fixture_text("03_cvpr2023_day_landing.html")
        return httpx.Response(200, content=html.encode("utf-8"))

    client = HttpClient(user_agent=_UA, transport=httpx.MockTransport(handler))
    adapter = CVFAdapter(http=client)
    stubs = list(
        adapter.enumerate_issue(
            make_cvf_venue("cvpr"), IssueRef(venue_id="cvpr", year=2023, label="2023")
        )
    )
    assert len(stubs) == 4
    assert stubs[0].title == "GFPose: Learning 3D Human Pose Prior With Gradient Fields"


def test_flat_flow_bare_response_uses_fixture_2_directly() -> None:
    """件②（2013 flat，bare 响应即全集）——早年一请求全流程。"""

    def handler(request: httpx.Request) -> httpx.Response:
        html = fixture_text("02_cvpr2013_flat_normal.html")
        return httpx.Response(200, content=html.encode("utf-8"))

    client = HttpClient(user_agent=_UA, transport=httpx.MockTransport(handler))
    adapter = CVFAdapter(http=client)
    stubs = list(
        adapter.enumerate_issue(
            make_cvf_venue("cvpr"), IssueRef(venue_id="cvpr", year=2013, label="2013")
        )
    )
    assert len(stubs) == 2
    assert stubs[0].identifiers == (
        ("cvf", "CVPR2013/Kim_Deformable_Spatial_Pyramid_2013_CVPR_paper"),
    )


# --- 件⑥/⑧/⑨/⑩：错误状态码件（.http）：真实状态→ErrorClass 映射落点（HttpClient 层）--------


def _client_for(name: str) -> HttpClient:
    status, headers, body = http_fixture(name)

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, headers=headers, content=body)

    return HttpClient(user_agent=_UA, transport=httpx.MockTransport(handler))


def test_06_404_maps_to_gone() -> None:
    with pytest.raises(CrawlerError) as exc:
        _client_for("06_404_apache_default.http").get_text("https://openaccess.thecvf.com/CVPR2099")
    assert exc.value.error_class is ErrorClass.GONE


def test_08a_ratelimit_429_with_header_maps_to_rate_limited_with_retry_after() -> None:
    with pytest.raises(CrawlerError) as exc:
        _client_for("08_ratelimit_429_with_header.http").get_text(
            "https://openaccess.thecvf.com/CVPR2023?day=all"
        )
    assert exc.value.error_class is ErrorClass.RATE_LIMITED
    assert "retry_after_s=30" in exc.value.detail


def test_08b_ratelimit_429_no_header_maps_to_rate_limited_without_retry_after() -> None:
    with pytest.raises(CrawlerError) as exc:
        _client_for("08_ratelimit_429_no_header.http").get_text(
            "https://openaccess.thecvf.com/CVPR2023?day=all"
        )
    assert exc.value.error_class is ErrorClass.RATE_LIMITED
    assert exc.value.detail == ""  # 无 Retry-After 头 → detail 省略该段


def test_09_server_error_500_maps_to_transient() -> None:
    with pytest.raises(CrawlerError) as exc:
        _client_for("09_server_error_500.http").get_text("https://openaccess.thecvf.com/CVPR2023")
    assert exc.value.error_class is ErrorClass.TRANSIENT


def test_10_bad_request_400_maps_to_config() -> None:
    with pytest.raises(CrawlerError) as exc:
        _client_for("10_bad_request_400.http").get_text("https://openaccess.thecvf.com/CVPR2023")
    assert exc.value.error_class is ErrorClass.CONFIG
