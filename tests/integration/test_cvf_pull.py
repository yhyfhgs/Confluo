"""cvf T4 集成 + AC-2.4 离线层（design/adapters/cvf.md §6/§7）。

零真实网络：CLI `pull` 全链路经 `cli._http_client_factory` seam 注入
`httpx.MockTransport` client（cvf 无认证，只需一个共享 client，不同于 openreview
的 token 专属 client 双 seam）。覆盖：

- **T4 全链**（非 CLI，直调 adapter）：discover（注入固定 current_year）→
  enumerate（双 era：一届 2023 内混合有/无 supp 条目）→ resolve（零网络，断言
  MockTransport 零命中）→ fetch（%PDF）。
- **AC-2.4 离线层**：`pull cvpr --year 2023 --filter "diffusion"` 全链回放——
  (a) 全集 enumerate 数 == fixture 条目数；(b) 过滤命中数 == 对全集本地
  `filter_expr` 过滤数（大小写不敏感子串，本测试标题故意覆盖大小写混合形态）；
  (c) 下载子集 == 过滤子集（按标题精确比对，非仅计数）、每个 `%PDF` 魔数过、
  `crawler verify` DB↔文件对账一致。`--limit`/`--dry-run` 附加覆盖。
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import httpx
import pytest
import yaml
from typer.testing import CliRunner

from helpers import FakeFetchIO, make_cvf_venue
from paper_crawler import cli as cli_module
from paper_crawler.adapters.cvf.adapter import CVFAdapter
from paper_crawler.cli import app
from paper_crawler.config import Config
from paper_crawler.http import HttpClient
from paper_crawler.ratelimit import RateLimiter
from paper_crawler.storage.db import Database
from paper_crawler.types import AssetKind

runner = CliRunner()

_MOCK_UA = "PaperCrawler/test (personal research; mailto:test@example.com)"
_PDF = b"%PDF-1.7\n" + b"cvf-synthetic-pdf\n" + b"0" * 400 + b"\n%%EOF\n"


# --- home 装配（cvpr venue + rate scale 快进）------------------------------------------------


def _write_cvpr_home(base: Path) -> Path:
    home = base / "home"
    venues_dir = home / "venues"
    venues_dir.mkdir(parents=True)
    config_lines = ["[paths]", 'venues_dirs = ["venues"]', "", "[rate]", "scale = 1000.0"]
    (home / "config.toml").write_text("\n".join(config_lines) + "\n", encoding="utf-8")
    doc = {
        "id": "cvpr",
        "kind": "conference",
        "names": {
            "full": "IEEE/CVF Conference on Computer Vision and Pattern Recognition",
            "aliases": ["CVPR"],
        },
        "field": ["cs_ai"],
        "tier": "T1",
        "identifiers": {"dblp_key": "conf/cvpr"},
        "metadata_source": "cvf",
        "fulltext_source": "cvf",
        "quirks": {"cvf_edition_overrides": {}},
        "status": "active",
    }
    (venues_dir / "cvpr.yaml").write_text(yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8")
    return home


# --- 合成响应构造（day-landing → ?day=all，忠实还原现代年份两请求流程）--------------------------

_DAY_LANDING_HTML = (
    b'<div id="content"><h3>Papers</h3><dl>'
    b'<dd>[<a href="/CVPR2023?day=2023-06-20">Day 1: 2023-06-20</a>]</dd>'
    b'<dd>[<a href="/CVPR2023?day=all">All Papers</a>]</dd>'
    b"</dl></div>"
)

# 12 个标题：5 条含 "diffusion"（大小写形态各异：首字母大写/句中/全小写/全大写），
# 7 条不含——AC-2.4 过滤自洽不变式的非平凡（非全命中/全不命中）样本。
_TITLES: tuple[str, ...] = (
    "Diffusion Models for Robust 3D Pose Estimation",  # 含（首字母大写）
    "Learning Sparse Representations via Contrastive Coding",
    "A Unified Framework for Video Diffusion Synthesis",  # 含（句中）
    "Efficient Transformers for Dense Prediction",
    "diffusion-Guided Point Cloud Completion",  # 含（全小写开头）
    "Neural Radiance Fields for Sparse Views",
    "DIFFUSION-Based Data Augmentation for Segmentation",  # 含（全大写）
    "Cross-Modal Retrieval with Graph Attention Networks",
    "Self-Supervised Depth Estimation from Monocular Video",
    "Text-to-Image Diffusion with Explicit Layout Control",  # 含（句中）
    "Robust Object Detection under Domain Shift",
    "Multi-Task Learning for Autonomous Driving Perception",
)


def _entry_html(index: int, title: str, *, with_supp: bool) -> str:
    stem = f"paper{index:03d}_CVPR_2023_paper"
    links = f'[<a href="/content/CVPR2023/papers/{stem}.pdf">pdf</a>]'
    if with_supp:
        links += f'[<a href="/content/CVPR2023/supplemental/{stem}_supp.pdf">supp</a>]'
    return (
        f'<dt class="ptitle"><br><a href="/content/CVPR2023/html/{stem}.html">{title}</a></dt>\n'
        f'<dd><input type="hidden" name="query_author" value="Author {index}"></dd>\n'
        f"<dd>{links}</dd>\n"
    )


def _day_all_html(titles: tuple[str, ...], *, mix_supp: bool = False) -> bytes:
    """`mix_supp=True`：偶数 index 条目附 supp（T4 "有/无 supp 两路"覆盖，仅供直调
    adapter 的 T4 全链测试使用）。CLI 驱动的 AC-2.4 `pull` 测试恒 `mix_supp=False`
    ——Phase 1/2 pipeline 的 `_asset_final_path`（stages.py）目前只落地 pdf 资产，
    si 资产的 fetch 任务会因 kind != pdf 被 CONFIG 拒绝进而 BLOCKED（框架既有限制，
    非 cvf adapter 缺陷；openreview AC-2.2 的 pull 测试同样从不让 SI 走满 pull
    级联，只在 resolve 单测里验证 SI plan 产出——见 test_openreview_adapter.py
    ``test_resolve_si_yields_additional_plan``，本文件遵循同一先例）。
    """
    body = "\n".join(
        _entry_html(i, t, with_supp=(mix_supp and i % 2 == 0)) for i, t in enumerate(titles)
    )
    return f'<html><body><div id="content"><dl>\n{body}\n</dl></div></body></html>'.encode()


def _make_handler(
    titles: tuple[str, ...], *, mix_supp: bool = False
) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith(".pdf"):
            return httpx.Response(200, content=_PDF)
        if request.url.params.get("day") == "all":
            return httpx.Response(200, content=_day_all_html(titles, mix_supp=mix_supp))
        return httpx.Response(200, content=_DAY_LANDING_HTML)

    return handler


def _patch_shared_client(
    monkeypatch: pytest.MonkeyPatch, handler: Callable[[httpx.Request], httpx.Response]
) -> None:
    """cvf 无认证，只需共享 seam（不同于 openreview 的 token 专属 client 双 seam）。"""

    def shared_factory(_config: Config, _rate_limiter: RateLimiter | None = None) -> HttpClient:
        return HttpClient(user_agent=_MOCK_UA, transport=httpx.MockTransport(handler))

    monkeypatch.setattr(cli_module, "_http_client_factory", shared_factory)


# --- DB 探针 -----------------------------------------------------------------------------------


def _papers(home: Path) -> int:
    db = Database(home / "catalog.sqlite")
    try:
        return int(db.query("SELECT COUNT(*) AS n FROM paper WHERE venue_id='cvpr'")[0]["n"])
    finally:
        db.close()


def _fetched_titles(home: Path) -> set[str]:
    db = Database(home / "catalog.sqlite")
    try:
        rows = db.query(
            "SELECT DISTINCT p.title FROM paper p JOIN asset a ON a.paper_id = p.id "
            "WHERE p.venue_id = 'cvpr' AND a.state = 'fetched'"
        )
        return {str(r["title"]) for r in rows}
    finally:
        db.close()


def _cvf_identifiers(home: Path) -> set[str]:
    db = Database(home / "catalog.sqlite")
    try:
        rows = db.query("SELECT value FROM identifier WHERE scheme='cvf'")
        return {str(r["value"]) for r in rows}
    finally:
        db.close()


def _pdf_files(home: Path) -> list[Path]:
    root = home / "data" / "pdf"
    return sorted(root.rglob("*.pdf")) if root.is_dir() else []


# --- AC-2.4 离线层：pull cvpr --year 2023 --filter "diffusion" --------------------------------


def test_ac_2_4_pull_cvpr_2023_filter_diffusion_offline_layer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Closes: AC-2.4 (offline layer).

    (a) 全集 enumerate 数 == fixture 条目数；(b) 过滤命中数 == 对全集本地
    filter_expr 过滤数（AC-2.4 自洽不变式）；(c) 下载子集 == 过滤子集（按标题
    精确比对）、每个 %PDF 魔数过、DB↔文件对账一致。
    """
    home = _write_cvpr_home(tmp_path)
    _patch_shared_client(monkeypatch, _make_handler(_TITLES))

    result = runner.invoke(
        app, ["pull", "cvpr", "--year", "2023", "--filter", "diffusion", "--home", str(home)]
    )
    assert result.exit_code == 0, result.output

    # (a) enumerate 全集不受 filter 影响：DB 里 12 篇全部落库。
    assert _papers(home) == len(_TITLES)
    assert len(_cvf_identifiers(home)) == len(_TITLES)

    # (b) 过滤命中数 == 对全集本地重算的 filter_expr 命中数（AC-2.4 自洽不变式；
    # 大小写不敏感子串，与 pipeline._select_papers 的 .lower() in .lower() 同口径）。
    expected_hits = {t for t in _TITLES if "diffusion" in t.lower()}
    assert len(expected_hits) == 5  # 非平凡子集（非全命中/全不命中）

    # (c) 下载子集 == 过滤子集（按标题精确比对，非仅计数）。
    assert _fetched_titles(home) == expected_hits
    pdfs = _pdf_files(home)
    assert len(pdfs) == len(expected_hits)
    assert all(f.read_bytes().startswith(b"%PDF-") for f in pdfs)  # 魔数

    # DB↔文件对账一致（crawler verify 零问题）。
    verify_result = runner.invoke(app, ["verify", "--home", str(home)])
    assert verify_result.exit_code == 0, verify_result.output
    assert "一致，未发现问题" in verify_result.output


def test_ac_2_4_filter_limit_truncates_the_filtered_subset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`--limit` 截断的是**过滤后**候选集（FR-05），非全集——5 命中截到 2。"""
    home = _write_cvpr_home(tmp_path)
    _patch_shared_client(monkeypatch, _make_handler(_TITLES))

    result = runner.invoke(
        app,
        [
            "pull",
            "cvpr",
            "--year",
            "2023",
            "--filter",
            "diffusion",
            "--limit",
            "2",
            "--home",
            str(home),
        ],
    )
    assert result.exit_code == 0, result.output
    assert _papers(home) == len(_TITLES)  # enumerate 仍是全集
    assert len(_pdf_files(home)) == 2  # fetch 被 limit 截到 2


def test_ac_2_4_filter_dry_run_stops_at_resolve(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`--dry-run` 止于 resolve：enumerate+过滤圈定生效，但 0 落盘。"""
    home = _write_cvpr_home(tmp_path)
    _patch_shared_client(monkeypatch, _make_handler(_TITLES))

    result = runner.invoke(
        app,
        [
            "pull",
            "cvpr",
            "--year",
            "2023",
            "--filter",
            "diffusion",
            "--dry-run",
            "--home",
            str(home),
        ],
    )
    assert result.exit_code == 0, result.output
    assert _papers(home) == len(_TITLES)
    assert _pdf_files(home) == []


# --- T4 全链（非 CLI，直调 adapter）：discover→enumerate→resolve→fetch -------------------------


def test_t4_full_chain_discover_enumerate_resolve_fetch(monkeypatch: pytest.MonkeyPatch) -> None:
    """T4：注入固定 current_year 的 cadence 届列表正确；混合 supp 两路；resolve 零网络。"""
    request_count = 0

    def counting_handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        path = request.url.path
        if path.endswith(".pdf"):
            return httpx.Response(200, content=_PDF)
        if request.url.params.get("day") == "all":
            return httpx.Response(200, content=_day_all_html(_TITLES[:4], mix_supp=True))
        return httpx.Response(200, content=_DAY_LANDING_HTML)

    client = HttpClient(user_agent=_MOCK_UA, transport=httpx.MockTransport(counting_handler))
    adapter = CVFAdapter(http=client, current_year=2026)
    venue = make_cvf_venue("cvpr")

    # discover：注入固定 current_year 保证确定性（cadence 生成依赖时钟，design §6 裁决）。
    issues = list(adapter.discover_timeline(venue))
    assert [i.year for i in issues] == list(range(2013, 2027))
    issue2023 = next(i for i in issues if i.year == 2023)

    # enumerate：day-landing→?day=all 两请求；4 条目，偶数 index 有 supp、奇数无。
    papers = list(adapter.enumerate_issue(venue, issue2023))
    assert request_count == 2
    assert len(papers) == 4
    with_supp = [p for p in papers if dict(p.meta).get("supp_url")]
    without_supp = [p for p in papers if not dict(p.meta).get("supp_url")]
    assert len(with_supp) == 2 and len(without_supp) == 2  # 有/无 supp 两路

    # resolve：零网络——请求计数在 resolve 前后不变。
    before = request_count
    plans_with_supp = adapter.resolve_assets(venue, with_supp[0])
    plans_without_supp = adapter.resolve_assets(venue, without_supp[0])
    assert request_count == before  # 无新增 MockTransport 命中

    assert {p.kind for p in plans_with_supp} == {AssetKind.PDF, AssetKind.SI}
    assert {p.kind for p in plans_without_supp} == {AssetKind.PDF}

    # fetch：%PDF 落盘。
    io = FakeFetchIO()
    fetch_result = adapter.fetch_asset(plans_without_supp[0], io)
    assert fetch_result.ok is True
    assert io.data.startswith(b"%PDF-")
    assert issue2023.venue_id == "cvpr" and issue2023.label == "2023"
