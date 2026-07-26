"""`crawler preprint-report` CLI 集成测试（T16；AC-7.4 后半，design/06 §3）。

覆盖 CLI 接线本身（`Repo` 装配、空库响亮空态、退出码），不重复
`tests/unit/test_preprint_report.py`/`tests/unit/test_repo.py` 已覆盖的聚合/证据解析/
join 排序细节。零真实网络：本命令只读 DB，不经任何 adapter，天然零网络，同时仍受
`tests/conftest.py` 的 socket 禁网护栏兜底（同 `test_cli_oa_report.py` 既有手法）。
"""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from paper_crawler.cli import app
from paper_crawler.storage.db import Database
from paper_crawler.storage.repo import Repo
from paper_crawler.types import PaperStub, VenueSpec

runner = CliRunner()

_VENUE_JOURNAL = "mock_journal"
_VENUE_ARXIV = "arxiv_mock"


def _venue_spec(venue_id: str, full_name: str) -> VenueSpec:
    return VenueSpec(
        id=venue_id,
        kind="journal" if venue_id != _VENUE_ARXIV else "preprint_channel",
        names={"full": full_name, "aliases": []},
        field=["cs_ai"],
        identifiers={},
        metadata_source="mock_platform",
        fulltext_source="mock_platform",
    )


def _make_home(tmp_path: Path) -> Path:
    return tmp_path / "home"


def _seed_preprint_of_edge(home: Path) -> None:
    """直接经 `Repo` 往 `home/catalog.sqlite` 建一条真实 preprint_of 边（绕过 pull 流水线，
    同 `test_cli_oa_report.py::_seed_dois` 既有手法）。"""
    db = Database(home / "catalog.sqlite")
    db.migrate()
    repo = Repo(db)
    repo.upsert_venue(_venue_spec(_VENUE_JOURNAL, "Mock Journal"))
    repo.upsert_venue(_venue_spec(_VENUE_ARXIV, "ArXiv Mock"))
    repo.upsert_paper(
        _VENUE_JOURNAL, None, PaperStub(title="Published X", identifiers=(("doi", "10.1/x"),))
    )
    repo.upsert_paper(
        _VENUE_ARXIV,
        None,
        PaperStub(
            title="Preprint X",
            identifiers=(("arxiv", "2401.11111"),),
            meta=(("doi", "10.1/x"),),
        ),
    )
    db.close()


# --- 空库：响亮空态,非静默 ------------------------------------------------------------------


def test_empty_library_prints_loud_empty_state_and_exits_0(tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    db = Database(home / "catalog.sqlite")
    db.migrate()  # 建库但零 paper/paper_relation
    db.close()

    result = runner.invoke(app, ["preprint-report", "--home", str(home)])

    assert result.exit_code == 0, result.output
    assert "暂无" in result.output


# --- 正常路径：真实边 → 报告出现总览与逐边字段 -----------------------------------------------


def test_reports_edge_overview_and_row_fields(tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    _seed_preprint_of_edge(home)

    result = runner.invoke(app, ["preprint-report", "--home", str(home)])

    assert result.exit_code == 0, result.output
    assert "边总数: 1" in result.output
    assert "Preprint X" in result.output
    assert "Published X" in result.output
    assert "ArXiv Mock" in result.output
    assert "Mock Journal" in result.output
    assert "doi=10.1/x" in result.output
    assert "待复核" in result.output
