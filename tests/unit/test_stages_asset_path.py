"""`stages._asset_final_path` / `_asset_url_basename` 单测（design/06 §4 落位布局）。

背景：`_asset_final_path` 曾经只认 `kind=pdf`，si 资产必然撞见
`CrawlerError(CONFIG)`——经 pipeline 特判转 BLOCKED 且永不自愈（si 落位从未被实现，
不是"报错待修复配置"）。本文件钉死修复后的三条分支：pdf 落位不变（零回归）、si
落位按 design/06 §4"保持原名"取 `AssetPlan.url` 的 basename、其余 kind（html/
bibtex/source，§4 未给出布局）响亮抛 CONFIG（而非静默产出一个未经设计审的路径）。

全链集成覆盖（经 mock_platform 的 `emit_si` quirk 走完整 pull 级联）见
`tests/integration/test_asset_landing_paths.py`；本文件只钉纯函数级契约。
"""

from __future__ import annotations

import sqlite3

import pytest

from paper_crawler.config import Config
from paper_crawler.errors import CrawlerError, ErrorClass
from paper_crawler.pipeline.stages import _asset_final_path, _asset_url_basename
from paper_crawler.types import AssetKind, AssetPlan, AuthLevel

PAPER_ULID = "01ARZ3NDEKTSV4RRFFQ69G5FAV"
VENUE = "mock_journal"


def _paper_row(*, paper_id: str = PAPER_ULID, year: int | None = 2024) -> sqlite3.Row:
    """构造一个只含 `_asset_final_path` 所需两列（id/year）的真实 `sqlite3.Row`。

    `_asset_final_path` 只读 `paper["id"]`/`paper["year"]`；没有全量 `paper` 表
    schema 依赖，没必要拉起 `Database.migrate()` 这套重量级夹具——一条内存态
    ad-hoc SELECT 足够，且 `sqlite3.Row` 取出后不再依赖连接存活。
    """
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT ? AS id, ? AS year", (paper_id, year)).fetchone()
    conn.close()
    assert row is not None
    return row


def _config(tmp_path_factory: pytest.TempPathFactory) -> Config:
    home = tmp_path_factory.mktemp("asset-path-home")
    return Config(
        home=home,
        data_dir=home / "data",
        db_path=home / "catalog.sqlite",
        log_dir=home / "logs",
        reports_dir=home / "reports",
        venues_dirs=(home / "venues",),
    )


def _pdf_plan(url: str = "https://mock.local/pdf/10.9999/mock_journal.1.1.0") -> AssetPlan:
    return AssetPlan(kind=AssetKind.PDF, url=url, expected_type="application/pdf")


def _si_plan(url: str) -> AssetPlan:
    return AssetPlan(kind=AssetKind.SI, url=url, expected_type="application/zip")


# --- _asset_url_basename -----------------------------------------------------------------


def test_basename_plain_filename() -> None:
    assert _asset_url_basename("https://mock.local/si/doi/supplement.zip") == "supplement.zip"


def test_basename_strips_query_string() -> None:
    url = "https://mock.local/si/doi/supplement.zip?token=abc&exp=1"
    assert _asset_url_basename(url) == "supplement.zip"


def test_basename_strips_fragment() -> None:
    assert _asset_url_basename("https://host/path/appendix.pdf#page=3") == "appendix.pdf"


def test_basename_strips_query_and_fragment_together() -> None:
    url = "https://host/path/data.csv?x=1#section"
    assert _asset_url_basename(url) == "data.csv"


def test_basename_falls_back_when_url_ends_with_slash() -> None:
    assert _asset_url_basename("https://mock.local/si/doi/") == "si.bin"


def test_basename_falls_back_when_path_is_empty() -> None:
    assert _asset_url_basename("https://mock.local") == "si.bin"
    assert _asset_url_basename("https://mock.local?x=1") == "si.bin"


# --- _asset_final_path: pdf（零回归）------------------------------------------------------


def test_pdf_lands_under_pdf_venue_year_paper_ulid(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    config = _config(tmp_path_factory)
    paper = _paper_row(year=2024)
    path = _asset_final_path(config, VENUE, paper, _pdf_plan())
    assert path == config.data_dir / "pdf" / VENUE / "2024" / f"{PAPER_ULID}.pdf"


def test_pdf_null_year_lands_under_unknown(tmp_path_factory: pytest.TempPathFactory) -> None:
    config = _config(tmp_path_factory)
    paper = _paper_row(year=None)
    path = _asset_final_path(config, VENUE, paper, _pdf_plan())
    assert path == config.data_dir / "pdf" / VENUE / "unknown" / f"{PAPER_ULID}.pdf"


# --- _asset_final_path: si（design/06 §4 新增支持）----------------------------------------


def test_si_lands_under_si_venue_year_paper_dir_with_original_filename(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    config = _config(tmp_path_factory)
    paper = _paper_row(year=2024)
    plan = _si_plan("https://mock.local/si/10.9999/mock_journal.1.1.0/supplement.zip")

    path = _asset_final_path(config, VENUE, paper, plan)

    assert path == config.data_dir / "si" / VENUE / "2024" / PAPER_ULID / "supplement.zip"


def test_si_strips_query_string_from_landed_filename(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    config = _config(tmp_path_factory)
    paper = _paper_row(year=2024)
    plan = _si_plan("https://mock.local/si/doi/supplement.zip?sig=abc123&exp=999")

    path = _asset_final_path(config, VENUE, paper, plan)

    assert path.name == "supplement.zip"


def test_si_empty_basename_falls_back_to_si_bin(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    config = _config(tmp_path_factory)
    paper = _paper_row(year=2024)
    plan = _si_plan("https://mock.local/si/doi/")

    path = _asset_final_path(config, VENUE, paper, plan)

    assert path == config.data_dir / "si" / VENUE / "2024" / PAPER_ULID / "si.bin"


def test_si_null_year_lands_under_unknown(tmp_path_factory: pytest.TempPathFactory) -> None:
    config = _config(tmp_path_factory)
    paper = _paper_row(year=None)
    plan = _si_plan("https://mock.local/si/doi/supplement.zip")

    path = _asset_final_path(config, VENUE, paper, plan)

    assert path == config.data_dir / "si" / VENUE / "unknown" / PAPER_ULID / "supplement.zip"


def test_si_and_pdf_paths_never_collide_for_same_paper(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """同一 paper 的 pdf 与 si 落位互不相交（不同顶层子树），互不覆盖。"""
    config = _config(tmp_path_factory)
    paper = _paper_row(year=2024)

    pdf_path = _asset_final_path(config, VENUE, paper, _pdf_plan())
    si_path = _asset_final_path(
        config, VENUE, paper, _si_plan("https://mock.local/si/doi/supplement.zip")
    )

    assert pdf_path != si_path
    assert pdf_path.is_relative_to(config.data_dir / "pdf")
    assert si_path.is_relative_to(config.data_dir / "si")


# --- _asset_final_path: 不支持的 kind（响亮 CONFIG，非静默 BLOCKED）------------------------


@pytest.mark.parametrize("kind", [AssetKind.HTML, AssetKind.BIBTEX, AssetKind.SOURCE])
def test_unsupported_kind_raises_loud_config_error(
    tmp_path_factory: pytest.TempPathFactory, kind: AssetKind
) -> None:
    """design/06 §4 未给出布局的 kind：响亮 CrawlerError(CONFIG)，消息点名具体 kind。"""
    config = _config(tmp_path_factory)
    paper = _paper_row(year=2024)
    plan = AssetPlan(
        kind=kind, url=f"https://mock.local/{kind.value}/doi", auth_needed=AuthLevel.NONE
    )

    with pytest.raises(CrawlerError) as exc_info:
        _asset_final_path(config, VENUE, paper, plan)

    assert exc_info.value.error_class is ErrorClass.CONFIG
    assert "unsupported asset kind" in str(exc_info.value)
    assert kind.value in str(exc_info.value)
