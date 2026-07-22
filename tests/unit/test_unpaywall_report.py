"""OA 命中率报告单测（T5 DoD 第二项；design/adapters/aggregators.md §5.5）。

`build_oa_report`/`render_oa_report_markdown` 是纯函数层（不发 HTTP、不查 DB）——
用假 `lookup` 可调用对象覆盖聚合逻辑（命中率/oa_status 分布/逐条清单/单条出错不中断
整份报告），再用一个基于 `UnpaywallAdapter.lookup`（`httpx.MockTransport` 回放
fixture）的端到端用例锁定"报告消费真实 adapter.lookup 签名"这一集成语义。
"""

from __future__ import annotations

import httpx
import pytest

from helpers.unpaywall_fixtures import fixture_bytes, http_fixture
from paper_crawler.adapters.unpaywall import parse, report
from paper_crawler.adapters.unpaywall.adapter import UnpaywallAdapter
from paper_crawler.errors import CrawlerError, ErrorClass
from paper_crawler.http import HttpClient

_TEST_UA = "PaperCrawler/test (personal research; mailto:test@example.com)"


def _record(
    *,
    doi: str = "10.0/x",
    is_oa: bool = True,
    oa_status: str | None = "gold",
    pdf_url: str | None = "https://x/y.pdf",
    landing_url: str | None = None,
    version: str | None = "publishedVersion",
) -> parse.UnpaywallRecord:
    best = parse.OaLocation(version=version, url_for_pdf=pdf_url, url_for_landing_page=landing_url)
    return parse.UnpaywallRecord(
        doi=doi, is_oa=is_oa, oa_status=oa_status, best_oa_location=best, oa_locations=(best,)
    )


# --- build_oa_report：聚合逻辑（假 lookup）------------------------------------------------------


def test_empty_doi_list_produces_zero_total_and_zero_hit_rate() -> None:
    rep = report.build_oa_report([], lambda doi: None)
    assert rep.total == 0
    assert rep.hit_rate == 0.0
    assert rep.rows == ()


def test_mixed_outcomes_tally_correctly() -> None:
    fixtures: dict[str, parse.UnpaywallRecord | None] = {
        "10.0/pdf-hit": _record(doi="10.0/pdf-hit", oa_status="gold"),
        "10.0/landing-only": _record(
            doi="10.0/landing-only",
            oa_status="green",
            pdf_url=None,
            landing_url="https://x/landing",
        ),
        "10.0/closed": _record(doi="10.0/closed", is_oa=False, oa_status="closed", pdf_url=None),
        "10.0/missing": None,
    }

    def lookup(doi: str) -> parse.UnpaywallRecord | None:
        return fixtures[doi]

    rep = report.build_oa_report(list(fixtures), lookup)

    assert rep.total == 4
    assert rep.is_oa_count == 2  # pdf-hit + landing-only
    assert rep.hit_rate == pytest.approx(0.5)
    assert rep.pdf_count == 1
    assert rep.landing_only_count == 1
    assert rep.not_found_count == 1
    assert rep.error_count == 0
    assert rep.oa_status_counts() == {"gold": 1, "green": 1, "closed": 1}


def test_single_lookup_failure_does_not_abort_the_whole_report() -> None:
    def lookup(doi: str) -> parse.UnpaywallRecord | None:
        if doi == "10.0/boom":
            raise CrawlerError(ErrorClass.RATE_LIMITED, "slow down", detail="retry_after_s=5")
        return _record(doi=doi)

    rep = report.build_oa_report(["10.0/ok1", "10.0/boom", "10.0/ok2"], lookup)

    assert rep.total == 3
    assert rep.error_count == 1
    outcomes = {row.doi: row.outcome for row in rep.rows}
    assert outcomes == {"10.0/ok1": "hit_pdf", "10.0/boom": "error", "10.0/ok2": "hit_pdf"}
    error_row = next(row for row in rep.rows if row.doi == "10.0/boom")
    assert "rate_limited" in error_row.note


def test_error_note_is_redacted() -> None:
    def lookup(doi: str) -> parse.UnpaywallRecord | None:
        raise CrawlerError(ErrorClass.CONFIG, "bad request ?api_key=deadbeef123456")

    rep = report.build_oa_report(["10.0/x"], lookup)

    assert "deadbeef123456" not in rep.rows[0].note
    assert "***" in rep.rows[0].note


def test_hit_no_location_edge_case_is_oa_true_but_no_locations() -> None:
    record = parse.UnpaywallRecord(
        doi="10.0/x", is_oa=True, oa_status="gold", best_oa_location=None, oa_locations=()
    )
    rep = report.build_oa_report(["10.0/x"], lambda doi: record)
    assert rep.rows[0].outcome == "hit_no_location"
    assert rep.is_oa_count == 1


def test_informal_version_note_recorded_in_row() -> None:
    record = _record(version="acceptedVersion")
    rep = report.build_oa_report(["10.0/x"], lambda doi: record)
    assert "informal" in rep.rows[0].note
    assert rep.rows[0].version == "acceptedVersion"


def test_published_version_row_has_empty_note() -> None:
    record = _record(version="publishedVersion")
    rep = report.build_oa_report(["10.0/x"], lambda doi: record)
    assert rep.rows[0].note == ""


# --- render_oa_report_markdown ------------------------------------------------------------------


def test_render_markdown_contains_summary_and_table_headers() -> None:
    rep = report.build_oa_report(
        ["10.0/a", "10.0/b"],
        lambda doi: _record(doi=doi) if doi == "10.0/a" else None,
    )
    md = report.render_oa_report_markdown(rep)

    assert "# Unpaywall OA 命中率报告" in md
    assert "总数: 2" in md
    assert "is_oa 命中数: 1" in md
    assert "50.0%" in md
    assert "## oa_status 分布" in md
    assert "## 逐条清单" in md
    assert "10.0/a" in md
    assert "10.0/b" in md
    assert "not_found (404)" in md


def test_render_markdown_empty_report_has_placeholder_status_row() -> None:
    rep = report.build_oa_report([], lambda doi: None)
    md = report.render_oa_report_markdown(rep)
    assert "总数: 0" in md
    assert "| - | 0 |" in md


def test_render_markdown_escapes_pipe_characters_in_note() -> None:
    rep = report.OaReport(
        total=1,
        rows=(
            report.OaReportRow(
                doi="10.0/x",
                outcome="hit_pdf",
                is_oa=True,
                oa_status="gold",
                version="publishedVersion",
                pdf_url="https://x/y.pdf",
                landing_url=None,
                note="weird | note | with pipes",
            ),
        ),
    )
    md = report.render_oa_report_markdown(rep)
    assert "weird \\| note \\| with pipes" in md


# --- 端到端：真实 UnpaywallAdapter.lookup（MockTransport 回放）作为 build_oa_report 的 lookup ---


def test_build_oa_report_consumes_real_adapter_lookup_end_to_end() -> None:
    """锁定"OA 报告以直接 adapter.lookup 调用驱动"的集成语义（无 pipeline 兜底接线，见
    adapter.py 模块 docstring「触发条件语义」）：单 DOI GET 循环里混合命中/未收录两态。
    """
    fixture_by_path: dict[str, bytes] = {
        "/v2/10.1371/journal.pmed.0020124": fixture_bytes("01_normal_gold_fallback.json"),
    }
    not_found_status, not_found_headers, not_found_body = http_fixture("07_not_found_404.http")

    def handler(request: httpx.Request) -> httpx.Response:
        body = fixture_by_path.get(request.url.path)
        if body is not None:
            return httpx.Response(200, content=body)
        return httpx.Response(not_found_status, headers=not_found_headers, content=not_found_body)

    client = HttpClient(user_agent=_TEST_UA, transport=httpx.MockTransport(handler))
    adapter = UnpaywallAdapter(http=client, email="test@example.com")

    rep = report.build_oa_report(
        ["10.1371/journal.pmed.0020124", "10.9999/does-not-exist"], adapter.lookup
    )

    assert rep.total == 2
    assert rep.is_oa_count == 1
    assert rep.not_found_count == 1
    assert rep.oa_status_counts() == {"gold": 1}
