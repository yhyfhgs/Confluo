"""neurips_proceedings discover→enumerate→resolve→fetch→upsert 全链路集成
（design/adapters/neurips-proceedings.md §6 T4）。

用 `httpx.MockTransport` 喂 T3 fixture ②③（2021 legacy / 2022 modern，跨单一后缀边界的
两态）走全链路，断言：字段落库（identifier scheme='neurips'/meta/year）、legacy＋modern
双 era × conference/D&B 双 track 的 PDF 后缀构造断言、`paper_count_claimed` 式计数断言
（enumerate 产出数＝年页 li 计数）、重叠窗口去重（identifier 锚点）、错误路由（404/503/400
→ 各自 ErrorClass）经完整 enumerate→upsert 路径。零真实网络。
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
import yaml
from typer.testing import CliRunner

from helpers import FakeFetchIO, make_neurips_venue
from helpers.neurips_proceedings_fixtures import fixture_bytes, http_fixture
from paper_crawler import cli as cli_module
from paper_crawler.adapters.neurips_proceedings.adapter import NeuripsProceedingsAdapter
from paper_crawler.cli import app
from paper_crawler.config import Config
from paper_crawler.errors import CrawlerError, ErrorClass
from paper_crawler.http import HttpClient
from paper_crawler.ratelimit import RateLimiter
from paper_crawler.storage.db import Database
from paper_crawler.storage.repo import Repo
from paper_crawler.types import AssetKind, IssueRef

_UA = "PaperCrawler/test (personal research; mailto:test@example.com)"
_VENUE_ID = "neurips"


def _issue_2021() -> IssueRef:
    return IssueRef(venue_id=_VENUE_ID, year=2021, label="2021")


def _issue_2022() -> IssueRef:
    return IssueRef(venue_id=_VENUE_ID, year=2022, label="2022")


def _adapter(handler: object) -> NeuripsProceedingsAdapter:
    client = HttpClient(user_agent=_UA, transport=httpx.MockTransport(handler))  # type: ignore[arg-type]
    return NeuripsProceedingsAdapter(http=client)


def _year_page_handler(request: httpx.Request) -> httpx.Response:
    if request.url.path.endswith("/2021"):
        return httpx.Response(200, content=fixture_bytes("02_year_page_2021_legacy.html"))
    if request.url.path.endswith("/2022"):
        return httpx.Response(200, content=fixture_bytes("03_year_page_2022_modern.html"))
    raise AssertionError(f"unexpected year page request: {request.url}")


@pytest.fixture
def repo(tmp_path: Path) -> Iterator[Repo]:
    db = Database(tmp_path / "neurips.sqlite")
    db.migrate()
    r = Repo(db)
    r.upsert_venue(make_neurips_venue())  # paper/issue.venue_id 外键前置
    yield r
    db.close()


def _harvest(repo: Repo, adapter: NeuripsProceedingsAdapter, issue: IssueRef, issue_id: str) -> int:
    venue = make_neurips_venue()
    count = 0
    for stub in adapter.enumerate_issue(venue, issue):
        repo.upsert_paper(_VENUE_ID, issue_id, stub)
        count += 1
    return count


def _neurips_identifiers(repo: Repo) -> set[str]:
    rows = repo.db.query("SELECT value FROM identifier WHERE scheme='neurips'")
    return {str(r["value"]) for r in rows}


# --- enumerate→upsert 字段落库（legacy 2021）------------------------------------------------------


def test_enumerate_upserts_all_2021_legacy_papers_with_fields(repo: Repo) -> None:
    issue = _issue_2021()
    issue_id = repo.upsert_issue(issue, source="neurips_proceedings")
    harvested = _harvest(repo, _adapter(_year_page_handler), issue, issue_id)

    # design §3.2"本届回填"式计数断言：产出数 == 年页 li 计数（本 fixture 3 篇）。
    assert harvested == 3
    assert _neurips_identifiers(repo) == {
        "000c076c390a4c357313fca29e390ece",
        "0bad0bad0bad0bad0bad0bad0bad0bad",
        "feedfeedfeedfeedfeedfeedfeedfeed",
    }

    papers = {str(p["title"]): p for p in repo.list_papers(_VENUE_ID)}
    canary = papers["SYNTHETIC placeholder canary title pending T5 real-value replacement (2021)"]
    assert canary["year"] == 2021
    meta = json.loads(str(canary["meta_json"]))
    assert meta == {"track": "none", "asset_suffix": ""}


# --- enumerate→upsert 字段落库（modern 2022，双 track）--------------------------------------------


def test_enumerate_upserts_all_2022_modern_papers_with_mixed_tracks(repo: Repo) -> None:
    issue = _issue_2022()
    issue_id = repo.upsert_issue(issue, source="neurips_proceedings")
    harvested = _harvest(repo, _adapter(_year_page_handler), issue, issue_id)

    assert harvested == 4  # design §3.2 计数断言：本 fixture 4 篇（2 conference + 2 D&B）
    papers = {str(p["title"]): p for p in repo.list_papers(_VENUE_ID)}
    conf_canary_title = (
        "SYNTHETIC placeholder canary title pending T5 real-value replacement (2022 conference)"
    )
    db_canary_title = (
        "SYNTHETIC placeholder canary title pending T5 real-value replacement "
        "(2022 datasets_and_benchmarks)"
    )
    conf_meta = json.loads(str(papers[conf_canary_title]["meta_json"]))
    db_meta = json.loads(str(papers[db_canary_title]["meta_json"]))
    assert conf_meta == {"track": "conference", "asset_suffix": "-Conference"}
    assert db_meta == {
        "track": "datasets_and_benchmarks",
        "asset_suffix": "-Datasets_and_Benchmarks",
    }
    assert papers[conf_canary_title]["year"] == 2022


def test_paper_issue_link_created_for_both_years(repo: Repo) -> None:
    issue_2021, issue_2022 = _issue_2021(), _issue_2022()
    id_2021 = repo.upsert_issue(issue_2021, source="neurips_proceedings")
    id_2022 = repo.upsert_issue(issue_2022, source="neurips_proceedings")
    adapter = _adapter(_year_page_handler)
    _harvest(repo, adapter, issue_2021, id_2021)
    _harvest(repo, adapter, issue_2022, id_2022)

    assert len(repo.list_papers(_VENUE_ID, issue_id=id_2021)) == 3
    assert len(repo.list_papers(_VENUE_ID, issue_id=id_2022)) == 4
    assert len(repo.list_papers(_VENUE_ID)) == 7


# --- 重叠重收去重（identifier 锚点）---------------------------------------------------------------


def test_overlapping_reharvest_does_not_duplicate(repo: Repo) -> None:
    issue = _issue_2021()
    issue_id = repo.upsert_issue(issue, source="neurips_proceedings")
    adapter = _adapter(_year_page_handler)
    first = _harvest(repo, adapter, issue, issue_id)
    second = _harvest(repo, adapter, issue, issue_id)
    assert first == second == 3
    assert len(repo.list_papers(_VENUE_ID)) == 3
    assert len(_neurips_identifiers(repo)) == 3


# --- 全链路：discover→enumerate→resolve→fetch，legacy+modern 双 era × 双 track --------------------


def test_full_chain_discover_enumerate_resolve_fetch_dual_era_dual_track(repo: Repo) -> None:
    pdf_bytes = b"%PDF-1.4\nsynthetic contract pdf\n%%EOF\n"

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url).endswith(".pdf"):
            return httpx.Response(200, content=pdf_bytes)
        return _year_page_handler(request)

    adapter = _adapter(handler)
    venue = make_neurips_venue()  # 默认 quirks 范围 [2021, 2022]（单一后缀边界两侧各一年）

    issues = list(adapter.discover_timeline(venue))
    assert [i.year for i in issues] == [2021, 2022]

    urls_by_infix: dict[str, set[str]] = {
        "": set(),
        "-Conference": set(),
        "-Datasets_and_Benchmarks": set(),
    }
    for issue in issues:
        papers = list(adapter.enumerate_issue(venue, issue))
        assert len(papers) in (3, 4)  # 2021=3、2022=4（design §3.2 计数断言）

        for paper in papers:
            plans = adapter.resolve_assets(venue, paper)
            assert len(plans) == 1
            plan = plans[0]
            assert plan.kind is AssetKind.PDF
            assert plan.url.startswith("https://proceedings.neurips.cc/paper_files/paper/")
            assert "/file/" in plan.url
            assert "/hash/" not in plan.url
            assert "-Abstract" not in plan.url

            io = FakeFetchIO()
            result = adapter.fetch_asset(plan, io)
            assert result.ok is True
            assert io.data == pdf_bytes

            for infix, bucket in urls_by_infix.items():
                if plan.url.endswith(f"-Paper{infix}.pdf") and (
                    infix != "" or not plan.url.endswith("-Conference.pdf")
                ):
                    bucket.add(plan.url)

    # 三种后缀形态全覆盖：legacy 无后缀 + modern 两 track 各自后缀（design §3.3 T1 矩阵
    # 的端到端佐证——本测试断言实际产出的 URL 集合，而非只信任 T1 单测的孤立函数调用）。
    assert any(u.endswith("-Paper.pdf") for u in urls_by_infix[""])
    assert urls_by_infix["-Conference"]
    assert urls_by_infix["-Datasets_and_Benchmarks"]


# --- 0 条目结构漂移经完整 enumerate→upsert 路径 → parse ------------------------------------------


def test_structural_drift_error_propagates_through_full_chain(repo: Repo) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=fixture_bytes("06_year_page_structural_drift.html"))

    issue = _issue_2021()
    issue_id = repo.upsert_issue(issue, source="neurips_proceedings")
    with pytest.raises(CrawlerError) as exc:
        _harvest(repo, _adapter(handler), issue, issue_id)
    assert exc.value.error_class is ErrorClass.PARSE
    assert repo.list_papers(_VENUE_ID) == []  # 未提交部分数据


# --- 错误路由（adapter 边界的 ErrorClass 契约，经 T3 .http fixture 回放）--------------------------


def test_error_routing_year_page_404_is_gone(repo: Repo) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, content=fixture_bytes("05_year_page_404.html"))

    issue = _issue_2021()
    issue_id = repo.upsert_issue(issue, source="neurips_proceedings")
    with pytest.raises(CrawlerError) as exc:
        _harvest(repo, _adapter(handler), issue, issue_id)
    assert exc.value.error_class is ErrorClass.GONE


def test_error_routing_503_retry_after_is_rate_limited(repo: Repo) -> None:
    status, headers, body = http_fixture("09_year_page_503_retry_after.http")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, headers=headers, content=body)

    issue = _issue_2021()
    issue_id = repo.upsert_issue(issue, source="neurips_proceedings")
    with pytest.raises(CrawlerError) as exc:
        _harvest(repo, _adapter(handler), issue, issue_id)
    assert exc.value.error_class is ErrorClass.RATE_LIMITED
    assert "retry_after_s=90" in exc.value.detail


def test_error_routing_5xx_no_retry_after_is_transient(repo: Repo) -> None:
    status, headers, body = http_fixture("10_year_page_5xx_no_retry_after.http")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, headers=headers, content=body)

    issue = _issue_2021()
    issue_id = repo.upsert_issue(issue, source="neurips_proceedings")
    with pytest.raises(CrawlerError) as exc:
        _harvest(repo, _adapter(handler), issue, issue_id)
    assert exc.value.error_class is ErrorClass.TRANSIENT


def test_error_routing_400_is_config(repo: Repo) -> None:
    status, headers, body = http_fixture("11_year_page_400.http")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, headers=headers, content=body)

    issue = _issue_2021()
    issue_id = repo.upsert_issue(issue, source="neurips_proceedings")
    with pytest.raises(CrawlerError) as exc:
        _harvest(repo, _adapter(handler), issue, issue_id)
    assert exc.value.error_class is ErrorClass.CONFIG


# --- CLI `pull neurips --year 2023 --limit 10` 全链（design §6："复用 AC-2.2 测试模式，
# 虽无 AC 绑定"）--------------------------------------------------------------------------------
#
# 与 openreview 的 AC-2.2 测试同一套路（10 plan/魔数/DB↔文件对账），但省去 openreview 特有的
# token/cookie 双 client seam——neurips 无认证，只需 monkeypatch 共享的 `cli._http_client_factory`
# 一个 seam（同 arxiv/pmlr 走法）。研究确认（本次实现期核查 cli.py/pipeline/runner.py/stages.py）：
# `--year 2023` 只让 2023 这一届的 IssueRef 存活过 discover 阶段的内存过滤（discover_timeline
# 本身零网络，过滤发生在 upsert 之前），enumerate 阶段只对这一届发 1 次真实请求；`--limit`
# 只截断 fetch 候选（resolve 对全部匹配论文照常产 plan），不影响 discover/enumerate/resolve
# 的请求数。


def _write_neurips_home(base: Path) -> Path:
    home = base / "home"
    venues_dir = home / "venues"
    venues_dir.mkdir(parents=True)
    config_lines = [
        "[paths]",
        'venues_dirs = ["venues"]',
        "",
        "[rate]",
        "scale = 1000.0",  # 快进限速闸，避免真实 sleep 拖慢测试（openreview AC-2.2 同款）
    ]
    (home / "config.toml").write_text("\n".join(config_lines) + "\n", encoding="utf-8")
    doc = {
        "id": "neurips",
        "kind": "conference",
        "names": {
            "full": "Conference on Neural Information Processing Systems",
            "aliases": ["NeurIPS", "NIPS"],
        },
        "field": ["cs_ai"],
        "tier": "T1",
        "identifiers": {"dblp_key": "conf/nips"},
        "metadata_source": "neurips_proceedings",
        "fulltext_source": "neurips_proceedings",
        "auth": {"level": "none"},
        "quirks": {"first_year": 2023, "known_through_year": 2023},
        "status": "active",
    }
    yaml_text = yaml.safe_dump(doc, allow_unicode=True)
    (venues_dir / "neurips.yaml").write_text(yaml_text, encoding="utf-8")
    return home


_PULL_PDF = b"%PDF-1.7\n" + b"neurips-pull-synthetic-pdf\n" + b"0" * 200 + b"\n%%EOF\n"


def _modern_2023_page_with_n_papers(n: int) -> bytes:
    """合成 2023（modern era）年页，`n` 篇 conference track——足够多以让 `--limit 10` 真正截断。"""
    lis = []
    for i in range(n):
        hash_ = f"{i:032x}"  # 逐条不同、合法 32-hex（如 00...00, 00...01, ...）
        lis.append(
            '<li class="conference" data-track="conference">'
            '<div class="paper-content">'
            f'<a title="paper title" href="/paper_files/paper/2023/hash/{hash_}'
            f'-Abstract-Conference.html">Pull Test Paper {i}</a>'
            f'<span class="paper-authors">Author {i}</span>'
            "</div>"
            '<span class="paper-track-badge">Main Conference Track</span>'
            "</li>"
        )
    body = "\n".join(lis)
    return f"<html><body><ul class='paper-list'>{body}</ul></body></html>".encode()


def _pull_handler(request: httpx.Request) -> httpx.Response:
    if str(request.url).endswith(".pdf"):
        return httpx.Response(200, content=_PULL_PDF)
    if request.url.path.endswith("/2023"):
        return httpx.Response(200, content=_modern_2023_page_with_n_papers(12))
    raise AssertionError(f"unexpected pull request: {request.url}")


def _patch_http_client_factory(monkeypatch: pytest.MonkeyPatch) -> None:
    def factory(_config: Config, _rate_limiter: RateLimiter | None = None) -> HttpClient:
        return HttpClient(user_agent=_UA, transport=httpx.MockTransport(_pull_handler))

    monkeypatch.setattr(cli_module, "_http_client_factory", factory)


def _pull_papers(home: Path) -> int:
    db = Database(home / "catalog.sqlite")
    try:
        return int(db.query("SELECT COUNT(*) AS n FROM paper")[0]["n"])
    finally:
        db.close()


def _pull_fetched_assets(home: Path) -> int:
    db = Database(home / "catalog.sqlite")
    try:
        return int(db.query("SELECT COUNT(*) AS n FROM asset WHERE state='fetched'")[0]["n"])
    finally:
        db.close()


def _pull_pdf_files(home: Path) -> list[Path]:
    root = home / "data" / "pdf"
    return sorted(root.rglob("*.pdf")) if root.is_dir() else []


def test_pull_neurips_year_2023_limit_10_full_chain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = _write_neurips_home(tmp_path)
    _patch_http_client_factory(monkeypatch)

    runner_cli = CliRunner()
    result = runner_cli.invoke(
        app, ["pull", "neurips", "--year", "2023", "--limit", "10", "--home", str(home)]
    )
    assert result.exit_code == 0, result.output

    # resolve 对全部 12 篇产 plan/落库；--limit 10 只截断 fetch。
    assert _pull_papers(home) == 12
    pdfs = _pull_pdf_files(home)
    assert len(pdfs) == 10
    assert all(f.read_bytes().startswith(b"%PDF-") for f in pdfs)  # 魔数校验（pipeline 权威）
    assert _pull_fetched_assets(home) == 10


def test_pull_neurips_dry_run_stops_at_resolve(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = _write_neurips_home(tmp_path)
    _patch_http_client_factory(monkeypatch)

    runner_cli = CliRunner()
    result = runner_cli.invoke(
        app, ["pull", "neurips", "--year", "2023", "--dry-run", "--home", str(home)]
    )
    assert result.exit_code == 0, result.output
    assert _pull_papers(home) == 12
    assert _pull_pdf_files(home) == []  # 止于 resolve，无下载（同 openreview AC-2.2 先例）
