"""`crawler oa-report` CLI 集成测试（T5 DoD 第二项）。

覆盖 CLI 接线本身（DB 里 DOI 集合的取集/`--venue` 过滤/`--limit` 截断/退出码），
不重复 `tests/unit/test_unpaywall_report.py`/`test_unpaywall_adapter.py` 已覆盖的
聚合逻辑/解析/错误映射细节。零真实网络：`UnpaywallAdapter.lookup` 经
`monkeypatch.setattr` 猴补丁（同 `test_cli_canary.py` 对 `MockPlatformAdapter.
healthcheck` 的既有手法），未打猴补丁的路径仍受 `tests/conftest.py` 的 socket
禁网护栏兜底。
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from paper_crawler.adapters.unpaywall import parse
from paper_crawler.adapters.unpaywall.adapter import UnpaywallAdapter
from paper_crawler.cli import app
from paper_crawler.storage.db import Database
from paper_crawler.storage.repo import Repo
from paper_crawler.types import PaperStub, VenueSpec

runner = CliRunner()

_VENUE_A = "mock_journal_a"
_VENUE_B = "mock_journal_b"


def _venue_spec(venue_id: str) -> VenueSpec:
    return VenueSpec(
        id=venue_id,
        kind="journal",
        names={"full": venue_id, "aliases": []},
        field=["cs_ai"],
        identifiers={"issn": ["0000-0000"]},
        metadata_source="mock_platform",
        fulltext_source="mock_platform",
    )


def _write_venue_yaml(venues_dir: Path, venue_id: str) -> None:
    doc = {
        "id": venue_id,
        "kind": "journal",
        "names": {"full": venue_id, "aliases": []},
        "field": ["cs_ai"],
        "identifiers": {"issn": ["0000-0000"]},
        "metadata_source": "mock_platform",
        "fulltext_source": "mock_platform",
    }
    (venues_dir / f"{venue_id}.yaml").write_text(
        yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8"
    )


def _make_home(tmp_path: Path, *, with_venues_dir: bool = False) -> Path:
    home = tmp_path / "home"
    if with_venues_dir:
        venues_dir = home / "venues"
        venues_dir.mkdir(parents=True)
        (home / "config.toml").write_text('[paths]\nvenues_dirs = ["venues"]\n', encoding="utf-8")
        _write_venue_yaml(venues_dir, _VENUE_A)
        _write_venue_yaml(venues_dir, _VENUE_B)
    return home


def _seed_dois(home: Path, dois_by_venue: dict[str, list[str]]) -> None:
    """直接经 `Repo` 往 `home/catalog.sqlite` 插入 paper+doi identifier 行（绕过 pull 流水线）。"""
    db = Database(home / "catalog.sqlite")
    db.migrate()
    repo = Repo(db)
    for venue_id, dois in dois_by_venue.items():
        repo.upsert_venue(_venue_spec(venue_id))
        for index, doi in enumerate(dois):
            repo.upsert_paper(
                venue_id, None, PaperStub(title=f"paper {index}", identifiers=(("doi", doi),))
            )
    db.close()


def _record(
    doi: str, *, is_oa: bool = True, oa_status: str | None = "gold"
) -> parse.UnpaywallRecord:
    best = parse.OaLocation(
        version="publishedVersion", url_for_pdf=f"https://x/{doi}.pdf", url_for_landing_page=None
    )
    return parse.UnpaywallRecord(
        doi=doi, is_oa=is_oa, oa_status=oa_status, best_oa_location=best, oa_locations=(best,)
    )


# --- 无 DOI ---------------------------------------------------------------------------------


def test_no_dois_in_library_prints_message_and_exits_0(tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    _seed_dois(home, {})  # 建库但零 paper/identifier

    result = runner.invoke(app, ["oa-report", "--home", str(home)])

    assert result.exit_code == 0, result.output
    assert "无 DOI" in result.output


# --- 正常路径：mock lookup，验证聚合统计与逐条清单出现在输出 ------------------------------------


def test_reports_hit_rate_and_itemized_rows(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home = _make_home(tmp_path)
    _seed_dois(home, {"mock_journal": ["10.0/hit", "10.0/miss"]})

    def _fake_lookup(self: UnpaywallAdapter, doi: str) -> parse.UnpaywallRecord | None:
        if doi == "10.0/hit":
            return _record(doi)
        return None  # 未收录

    monkeypatch.setattr(UnpaywallAdapter, "lookup", _fake_lookup)

    result = runner.invoke(app, ["oa-report", "--home", str(home)])

    assert result.exit_code == 0, result.output
    assert "总数: 2" in result.output
    assert "is_oa 命中数: 1" in result.output
    assert "10.0/hit" in result.output
    assert "10.0/miss" in result.output
    assert "not_found (404)" in result.output


# --- --limit 截断 -----------------------------------------------------------------------------


def test_limit_truncates_queried_dois(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    _seed_dois(home, {"mock_journal": ["10.0/a", "10.0/b", "10.0/c"]})

    queried: list[str] = []

    def _fake_lookup(self: UnpaywallAdapter, doi: str) -> parse.UnpaywallRecord | None:
        queried.append(doi)
        return _record(doi)

    monkeypatch.setattr(UnpaywallAdapter, "lookup", _fake_lookup)

    result = runner.invoke(app, ["oa-report", "--limit", "2", "--home", str(home)])

    assert result.exit_code == 0, result.output
    assert len(queried) == 2
    assert "总数: 2" in result.output


# --- --venue 过滤 -----------------------------------------------------------------------------


def test_venue_filter_only_queries_that_venues_dois(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home = _make_home(tmp_path, with_venues_dir=True)
    _seed_dois(home, {_VENUE_A: ["10.0/a1", "10.0/a2"], _VENUE_B: ["10.0/b1"]})

    queried: list[str] = []

    def _fake_lookup(self: UnpaywallAdapter, doi: str) -> parse.UnpaywallRecord | None:
        queried.append(doi)
        return _record(doi)

    monkeypatch.setattr(UnpaywallAdapter, "lookup", _fake_lookup)

    result = runner.invoke(app, ["oa-report", "--venue", _VENUE_A, "--home", str(home)])

    assert result.exit_code == 0, result.output
    assert sorted(queried) == ["10.0/a1", "10.0/a2"]
    assert "总数: 2" in result.output


def test_unknown_venue_exits_2(tmp_path: Path) -> None:
    home = _make_home(tmp_path, with_venues_dir=True)
    _seed_dois(home, {_VENUE_A: ["10.0/a1"]})

    result = runner.invoke(app, ["oa-report", "--venue", "not_a_real_venue", "--home", str(home)])

    assert result.exit_code == 2


# --- 单 DOI 出错不影响其余 ---------------------------------------------------------------------


def test_single_doi_error_recorded_but_report_still_completes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from paper_crawler.errors import CrawlerError, ErrorClass

    home = _make_home(tmp_path)
    _seed_dois(home, {"mock_journal": ["10.0/ok", "10.0/boom"]})

    def _fake_lookup(self: UnpaywallAdapter, doi: str) -> parse.UnpaywallRecord | None:
        if doi == "10.0/boom":
            raise CrawlerError(ErrorClass.TRANSIENT, "temporary failure")
        return _record(doi)

    monkeypatch.setattr(UnpaywallAdapter, "lookup", _fake_lookup)

    result = runner.invoke(app, ["oa-report", "--home", str(home)])

    assert result.exit_code == 0, result.output
    assert "总数: 2" in result.output
    assert "查询出错: 1" in result.output
