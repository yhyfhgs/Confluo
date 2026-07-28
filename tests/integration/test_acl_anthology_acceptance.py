"""ACL Anthology T4 全链集成 + AC-2.5 离线层验收（design/adapters/acl-anthology.md §7）。

**Closes: AC-2.5 (offline layer)。** D-019 锚点快照 + 日志证据双判据（§7）：

1. `test_enumerate_and_resolve_full_2023_matches_anchor_new_style`：adapter 直调
   discover→enumerate→resolve 全链（`tests/helpers/acl_anthology_bulk.py` 的全量规模
   合成体，篇数精确匹配 `anchor-emnlp-2023.json`），断言 enumerate 产 2241 stub、
   跨 5 track、每 track 计数与锚点表逐项全等；resolve 产 2241 个 PDF plan。
2. `test_enumerate_old_style_path_via_discover_primed_cache`："两代路径各一"的旧式
   一侧（新式一侧即①）：git-tree 清单只含 `D19.xml`，discover 正确识别年份 2019，
   enumerate（清单热）正确取回并解析。
3. `test_ac_2_5_pull_cli_matches_anchor_and_log_evidence_is_bulk_not_page_scraping`：
   真正跑一次 `pull emnlp --year 2023 --limit N`（`cli_module._http_client_factory`
   seam 注入 MockTransport，零真实网络）——DB 落库 2241 篇与锚点 total 全等；随后对
   当次 obslog jsonl 做 grep 判据：**正向** `raw.githubusercontent.com` 命中两份 bulk
   XML；**负向（核心）** `aclanthology.org` 事件里**没有一行**匹配
   `/(events|venues)/` 或尾部 `/{id}/` landing 逐页抓取形态——`fetch --limit` 截断
   出的少量 aclanthology.org 事件**全部**是 `*.pdf`（fetch 阶段资产，非页面爬取）。

零真实网络（`tests/conftest.py` 的 socket 护栏 + 全程 MockTransport）。
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
import yaml
from typer.testing import CliRunner

from helpers import make_acl_anthology_venue
from helpers.acl_anthology_bulk import (
    MAIN_VOLUME_COUNTS,
    TOTAL_EMNLP_2023,
    synthetic_emnlp_main_2023_xml,
    synthetic_findings_2023_xml,
)
from helpers.acl_anthology_fixtures import fixture_bytes
from paper_crawler import cli as cli_module
from paper_crawler.adapters.acl_anthology.adapter import AclAnthologyAdapter
from paper_crawler.config import Config
from paper_crawler.http import HttpClient
from paper_crawler.ratelimit import RateLimiter
from paper_crawler.storage.db import Database
from paper_crawler.types import AssetKind, IssueRef

runner = CliRunner()


@pytest.fixture(autouse=True)
def _fast_rate_limiter(no_rate_limit_wait: None) -> None:
    """③的真实 CLI pull 不测限速本身——中和 `RateLimiter.acquire`，见
    `integration/conftest.py::no_rate_limit_wait`（`rate.scale` R1b 后拒绝 >1，
    不能再靠调大它快进）。①②直调 adapter，不经 CLI/RateLimiter，本 fixture 对它们
    是无操作。"""


_MOCK_UA = "PaperCrawler/test (personal research; mailto:test@example.com)"

_ANCHOR_PATH = (
    Path(__file__).resolve().parents[1] / "fixtures" / "acl_anthology" / "anchor-emnlp-2023.json"
)
_ANCHOR = json.loads(_ANCHOR_PATH.read_text(encoding="utf-8"))
_ANCHOR_BY_VOLUME: dict[str, int] = {
    v["anthology_volume_id"]: v["paper_count"] for v in _ANCHOR["volumes"]
}


# --- ① adapter 直调：discover→enumerate→resolve 全链，2241 篇匹配锚点（新式一侧）-----------------


def _bulk_tree_response(*extra_files: str) -> httpx.Response:
    tree = [{"path": "data/xml/2023.emnlp.xml", "type": "blob"}]
    tree.append({"path": "data/xml/2023.findings.xml", "type": "blob"})
    for name in extra_files:
        tree.append({"path": f"data/xml/{name}", "type": "blob"})
    body = json.dumps({"truncated": False, "tree": tree}).encode("utf-8")
    return httpx.Response(200, content=body)


def _bulk_handler(
    *, pdf_body: bytes = b"%PDF-1.4\nsynthetic\n%%EOF\n"
) -> Callable[[httpx.Request], httpx.Response]:
    main_xml = synthetic_emnlp_main_2023_xml()
    findings_xml = synthetic_findings_2023_xml()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.github.com":
            return _bulk_tree_response()
        if request.url.host == "raw.githubusercontent.com":
            if request.url.path.endswith("2023.emnlp.xml"):
                return httpx.Response(200, content=main_xml)
            if request.url.path.endswith("2023.findings.xml"):
                return httpx.Response(200, content=findings_xml)
            return httpx.Response(404, content=b"synthetic 404")
        if request.url.path.endswith(".pdf"):
            return httpx.Response(200, content=pdf_body)
        return httpx.Response(404, content=b"synthetic 404")

    return handler


def test_enumerate_and_resolve_full_2023_matches_anchor_new_style() -> None:
    """Closes: AC-2.5 (offline layer) — T4 全链 ①：篇数/track 明细与 D-019 锚点表全等。"""
    adapter = AclAnthologyAdapter(
        http=HttpClient(user_agent=_MOCK_UA, transport=httpx.MockTransport(_bulk_handler()))
    )
    venue = make_acl_anthology_venue()

    issues = list(adapter.discover_timeline(venue))
    issue_2023 = next(i for i in issues if i.year == 2023)
    stubs = list(adapter.enumerate_issue(venue, issue_2023))

    assert len(stubs) == TOTAL_EMNLP_2023 == _ANCHOR["total"] == 2241

    tracks: dict[str, int] = {}
    for stub in stubs:
        track = dict(stub.meta)["track"]
        tracks[track] = tracks.get(track, 0) + 1

    for volume_id, expected_count in MAIN_VOLUME_COUNTS.items():
        assert tracks[volume_id] == expected_count == _ANCHOR_BY_VOLUME[volume_id]
    assert tracks["findings"] == _ANCHOR_BY_VOLUME["findings"]
    assert set(tracks) == {"main", "tutorial", "demo", "industry", "findings"}  # 跨 5 track

    plans = [plan for stub in stubs for plan in adapter.resolve_assets(venue, stub)]
    pdf_plans = [p for p in plans if p.kind is AssetKind.PDF]
    assert len(pdf_plans) == 2241
    assert all(
        p.url.startswith("https://aclanthology.org/") and p.url.endswith(".pdf") for p in pdf_plans
    )


# --- ② 旧式一侧（两代路径各一）：discover 经清单识别 2019，enumerate 清单热取回 ------------------


def test_enumerate_old_style_path_via_discover_primed_cache() -> None:
    """两代路径各一的旧式一侧：git-tree 只含 D19.xml，discover 识别年份，enumerate 清单热取回。"""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.github.com":
            body = json.dumps(
                {"truncated": False, "tree": [{"path": "data/xml/D19.xml", "type": "blob"}]}
            ).encode("utf-8")
            return httpx.Response(200, content=body)
        if request.url.host == "raw.githubusercontent.com" and request.url.path.endswith("D19.xml"):
            return httpx.Response(200, content=fixture_bytes("03_d19_legacy_excerpt.xml"))
        return httpx.Response(404, content=b"synthetic 404")

    adapter = AclAnthologyAdapter(
        http=HttpClient(user_agent=_MOCK_UA, transport=httpx.MockTransport(handler))
    )
    venue = make_acl_anthology_venue()

    issues = list(adapter.discover_timeline(venue))
    assert [i.year for i in issues] == [2019]  # 清单仅含 D19.xml → 唯一候选年
    assert issues[0] == IssueRef(
        venue_id="emnlp",
        volume=None,
        number=None,
        year=2019,
        label="2019",
        pub_date=None,
        paper_count_claimed=None,
    )

    stubs = list(adapter.enumerate_issue(venue, issues[0]))
    assert len(stubs) == 4
    assert stubs[0].identifiers[0] == ("anthology", "D19-1001")  # 大写前缀原样


# --- ③ AC-2.5 离线层核心：真实 CLI pull + obslog jsonl 日志证据 grep 判据 -------------------------


def _write_emnlp_home(base: Path) -> Path:
    home = base / "home"
    venues_dir = home / "venues"
    venues_dir.mkdir(parents=True)
    config_lines = ["[paths]", 'venues_dirs = ["venues"]', "", "[rate]", "scale = 1.0"]
    (home / "config.toml").write_text("\n".join(config_lines) + "\n", encoding="utf-8")
    doc = {
        "id": "emnlp",
        "kind": "conference",
        "names": {
            "full": "Conference on Empirical Methods in Natural Language Processing",
            "aliases": ["EMNLP"],
        },
        "field": ["cs_ai"],
        "tier": "T1",
        "identifiers": {"dblp_key": "conf/emnlp"},
        "metadata_source": "acl_anthology",
        "fulltext_source": "acl_anthology",
        "auth": {"level": "none"},
        "quirks": {"anthology_legacy_prefix": "D"},
        "status": "active",
    }
    (venues_dir / "emnlp.yaml").write_text(
        yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8"
    )
    return home


def _patch_client_factory(monkeypatch: pytest.MonkeyPatch) -> None:
    handler = _bulk_handler()

    def factory(_config: Config, rate_limiter: RateLimiter | None = None) -> HttpClient:
        return HttpClient(
            user_agent=_MOCK_UA, transport=httpx.MockTransport(handler), rate_limiter=rate_limiter
        )

    monkeypatch.setattr(cli_module, "_http_client_factory", factory)


def _papers_count(home: Path) -> int:
    db = Database(home / "catalog.sqlite")
    try:
        return int(db.query("SELECT COUNT(*) AS n FROM paper WHERE venue_id='emnlp'")[0]["n"])
    finally:
        db.close()


def _pdf_asset_count(home: Path) -> int:
    db = Database(home / "catalog.sqlite")
    try:
        rows = db.query(
            "SELECT COUNT(*) AS n FROM asset a JOIN paper p ON a.paper_id = p.id "
            "WHERE p.venue_id = 'emnlp' AND a.kind = 'pdf'"
        )
        return int(rows[0]["n"])
    finally:
        db.close()


def _obslog_events(home: Path) -> list[dict[str, object]]:
    date_str = datetime.now(UTC).strftime("%Y%m%d")
    path = home / "logs" / f"crawler-{date_str}.jsonl"
    events: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            events.append(json.loads(line))
    return events


_LANDING_PAGE_RE = re.compile(r"/(events|venues)/|/[^/]+/$")


def test_ac_2_5_pull_cli_matches_anchor_and_log_evidence_is_bulk_not_page_scraping(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Closes: AC-2.5 (offline layer). pull emnlp --year 2023 --limit 25 全链回放。"""
    home = _write_emnlp_home(tmp_path)
    _patch_client_factory(monkeypatch)

    result = runner.invoke(
        cli_module.app, ["pull", "emnlp", "--year", "2023", "--limit", "25", "--home", str(home)]
    )
    assert result.exit_code == 0, result.output

    # D-019 锚点判据：DB 落库 2241 篇（enumerate 全量含 Findings join，不受 --limit 影响）。
    # resolve 前置（缺陷 C-C）：--limit 25 只对前 25 篇建 resolve → 25 个 pdf plan（前 25 篇
    # 均无 attachment，故其 pdf 恰是候选前 25 个 asset——落盘子集与全量 resolve 时逐字一致）。
    assert _papers_count(home) == TOTAL_EMNLP_2023 == _ANCHOR["total"]
    assert _pdf_asset_count(home) == 25

    events = _obslog_events(home)
    urls = [str(e["url"]) for e in events if "url" in e]

    # 正向：raw.githubusercontent.com 确实被用于两份 bulk XML（enumerate 走 bulk 路径）。
    raw_urls = [u for u in urls if "raw.githubusercontent.com" in u]
    assert any(re.search(r"data/xml/2023\.emnlp\.xml", u) for u in raw_urls)
    assert any(re.search(r"data/xml/2023\.findings\.xml", u) for u in raw_urls)

    # 负向（核心）：aclanthology.org 事件里没有一行是 /events/、/venues/ 或尾部 /{id}/
    # landing 逐页抓取形态——照抄设计 §7 的 grep 判据。
    acl_site_urls = [u for u in urls if "aclanthology.org" in u]
    assert acl_site_urls  # --limit 25 应确有若干 fetch 事件，不是"因为没跑所以恰好 0 行"
    page_scrape_hits = [u for u in acl_site_urls if _LANDING_PAGE_RE.search(u)]
    assert page_scrape_hits == []
    # aclanthology.org 事件仅 *.pdf（fetch 阶段资产，非页面爬取）；同一次 fetch 会在
    # http.py（"http exchange" DEBUG）与 stages.py（"fetched N bytes" INFO）各落一条
    # 携 url 的事件，故按去重后的 URL 集合断言 --limit 截断的资产数，不依赖具体日志
    # 行数这一实现细节。
    assert all(u.endswith(".pdf") for u in acl_site_urls)
    assert len(set(acl_site_urls)) == 25  # --limit 25 截断的去重资产数
