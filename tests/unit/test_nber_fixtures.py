"""nber T1 契约消费 + fixture 回放（零真实网络；nber.md §3.1/§7）。

**T1 契约消费确认（venue 键→枚举实跑证据）**：nber venue（`identifiers.crossref_prefix=10.3386`、
无 `quirks.crossref_date_field` → 默认 published）驱动 **T1 扩展的 CrossrefAdapter** 走
`/prefixes/10.3386/works` 的 prefix+published 枚举——discover 逐出版年 facet、enumerate 日期窗
cursor → PaperStub（DOI 前缀 10.3386）。证 nber 消费 T1 两轴扩展契约（prefix 基址 + published 轴）
与既有 by-ISSN 期刊同一 parse 路径（`to_paper_stub` 仍产 `(doi,)`，两轴之外零改）。
"""

from __future__ import annotations

import httpx

from helpers import make_nber_venue
from helpers.nber_fixtures import fixture_bytes
from paper_crawler.adapters.crossref.adapter import CrossrefAdapter
from paper_crawler.http import HttpClient
from paper_crawler.types import IssueRef

_UA = "PaperCrawler/test (personal research; mailto:test@example.com)"


def _crossref_for_nber(capture: list[httpx.Request]) -> CrossrefAdapter:
    """CrossrefAdapter（MockTransport）：facet 请求→facet fixture；works 窗请求→works fixture。"""

    def handler(request: httpx.Request) -> httpx.Response:
        capture.append(request)
        if request.url.params.get("facet"):
            return httpx.Response(200, content=fixture_bytes("04_crossref_prefix_facet.json"))
        return httpx.Response(200, content=fixture_bytes("05_crossref_prefix_works.json"))

    client = HttpClient(user_agent=_UA, transport=httpx.MockTransport(handler))
    return CrossrefAdapter(http=client)


def test_nber_venue_drives_prefix_published_discover() -> None:
    """discover：nber venue 键 → /prefixes/10.3386/works?facet=published:* → 逐出版年 IssueRef。"""
    capture: list[httpx.Request] = []
    venue = make_nber_venue()
    issues = list(_crossref_for_nber(capture).discover_timeline(venue))

    # URL 实跑证据：prefix 基址 + published facet（date-field 默认 published）。
    facet_req = capture[0]
    assert "/prefixes/10.3386/works" in str(facet_req.url)
    assert facet_req.url.params.get("facet") == "published:*"

    years = sorted(i.year for i in issues if i.year is not None)
    assert years == [2015, 2024]  # facet fixture 的两年
    for issue in issues:
        assert issue.venue_id == "nber"
        assert issue.paper_count_claimed is not None  # facet 逐年计数


def test_nber_venue_drives_prefix_published_enumerate() -> None:
    """enumerate：(prefix, year) 窗 → /prefixes/10.3386/works?filter=from-pub-date → PaperStub。"""
    capture: list[httpx.Request] = []
    venue = make_nber_venue()
    issue = IssueRef(venue_id="nber", year=2015, label="2015", paper_count_claimed=2)
    stubs = list(_crossref_for_nber(capture).enumerate_issue(venue, issue))

    # URL 实跑证据：prefix 基址 + published 轴日期窗 filter（from-pub-date/until-pub-date）。
    works_req = capture[0]
    assert "/prefixes/10.3386/works" in str(works_req.url)
    flt = works_req.url.params.get("filter", "")
    assert "from-pub-date:2015-01-01" in flt
    assert "until-pub-date:2015-12-31" in flt

    # 枚举产 PaperStub（DOI 前缀 10.3386；两轴之外 to_paper_stub 零改，仍产 (doi,)）。
    dois = {value for stub in stubs for scheme, value in stub.identifiers if scheme == "doi"}
    assert dois == {"10.3386/w30000", "10.3386/t0042"}  # w + t 均折入同 venue（type=report）
    for stub in stubs:
        assert stub.title.strip()
        assert any(scheme == "doi" for scheme, _ in stub.identifiers)
