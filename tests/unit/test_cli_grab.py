"""`crawler grab` CLI 测试（T5：单篇 DOI 全链 + 三退出码 + 未入库建行路径）。

零真实网络：crossref 单篇 lookup 经 `monkeypatch.setattr`（同 test_cli_oa_report 手法）；
mock_platform 的 resolve/fetch 本地确定性（%PDF 字节，无 http）；socket 禁网护栏兜底。
退出码契约（design/05 Task 口径 / auth-framework grab 补规格）：
0=成功（资产落盘） / 1=业务失败（未收录 / 无资产） / 2=用法·配置错（缺 --doi / 未知/无法定 venue）。
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from paper_crawler.adapters.crossref.adapter import CrossrefAdapter
from paper_crawler.cli import app
from paper_crawler.storage.db import Database
from paper_crawler.storage.repo import Repo
from paper_crawler.types import PaperStub, VenueSpec

runner = CliRunner()

_VENUE = "mock_journal"
# mock_platform 的 DOI 形态 10.9999/{venue}.{v}.{n}.{i}（resolve 据此算期内序号）。
_DOI = "10.9999/mock_journal.1.1.0"


def _make_home(tmp_path: Path) -> Path:
    """建带 mock_journal（mock_platform 全链 adapter）venues 目录的 home。"""
    home = tmp_path / "home"
    venues_dir = home / "venues"
    venues_dir.mkdir(parents=True)
    (home / "config.toml").write_text('[paths]\nvenues_dirs = ["venues"]\n', encoding="utf-8")
    doc = {
        "id": _VENUE,
        "kind": "journal",
        "names": {"full": "Mock Journal", "aliases": []},
        "field": ["cs_ai"],
        "identifiers": {"issn": ["0000-0000"]},
        "metadata_source": "mock_platform",
        "fulltext_source": "mock_platform",
    }
    (venues_dir / f"{_VENUE}.yaml").write_text(yaml.safe_dump(doc), encoding="utf-8")
    return home


def _seed_paper(home: Path, venue_id: str, doi: str) -> None:
    """预入库一个绑定 venue 的 paper+doi（走 grab 的"库内反查"路径）。"""
    db = Database(home / "catalog.sqlite")
    db.migrate()
    repo = Repo(db)
    repo.upsert_venue(
        VenueSpec(
            id=venue_id,
            kind="journal",
            names={"full": venue_id, "aliases": []},
            field=["cs_ai"],
            identifiers={"issn": ["0000-0000"]},
            metadata_source="mock_platform",
            fulltext_source="mock_platform",
        )
    )
    repo.upsert_paper(venue_id, None, PaperStub(title="seeded", identifiers=(("doi", doi),)))
    db.close()


def _pdf_files(home: Path) -> list[Path]:
    return list((home / "data" / "pdf").rglob("*.pdf"))


# -- 退出码 2：用法·配置错 ----------------------------------------------------


def test_missing_doi_exits_2(tmp_path: Path) -> None:
    result = runner.invoke(app, ["grab", "--home", str(_make_home(tmp_path))])
    assert result.exit_code == 2, result.output


def test_unknown_venue_exits_2(tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    result = runner.invoke(
        app, ["grab", "--doi", _DOI, "--venue", "not_a_venue", "--home", str(home)]
    )
    assert result.exit_code == 2, result.output


def test_undetermined_venue_exits_2(tmp_path: Path) -> None:
    """无 --venue 且 DOI 不在库 → 无法确定 venue → 配置错（退出 2，不误触网络）。"""
    home = _make_home(tmp_path)
    result = runner.invoke(app, ["grab", "--doi", _DOI, "--home", str(home)])
    assert result.exit_code == 2, result.output


def test_browser_flag_without_config_exits_2(tmp_path: Path) -> None:
    """`--browser` 但 `[browserfetch].enabled` 未开 → **响亮拒绝**（退出 2），不静默降级
    （11-browser-fetch §7.1 L1 三级门；D-029 该通道默认关）。"""
    home = _make_home(tmp_path)
    _seed_paper(home, _VENUE, _DOI)
    result = runner.invoke(app, ["grab", "--doi", _DOI, "--browser", "--home", str(home)])
    assert result.exit_code == 2, result.output
    assert "[browserfetch].enabled" in result.output
    assert _pdf_files(home) == []  # 拒绝发生在任何取回动作之前


def test_browser_flag_with_config_opens_channel(tmp_path: Path) -> None:
    """三级门全开：flag 只置 `ctx.browser_fetch`——mock venue 产 direct 计划，既有路径
    逐字不变（分支只对 render_page 计划生效，非 render_page 零回归）。"""
    home = _make_home(tmp_path)
    (home / "config.toml").write_text(
        '[paths]\nvenues_dirs = ["venues"]\n\n[browserfetch]\nenabled = true\n', encoding="utf-8"
    )
    _seed_paper(home, _VENUE, _DOI)
    result = runner.invoke(app, ["grab", "--doi", _DOI, "--browser", "--home", str(home)])
    assert result.exit_code == 0, result.output
    assert len(_pdf_files(home)) == 1


# -- 退出码 1：业务失败 -------------------------------------------------------


def test_crossref_not_found_exits_1(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """未入库 DOI 且 crossref 未收录（lookup→None）→ 无法建 paper → 业务失败（退出 1）。"""
    home = _make_home(tmp_path)
    monkeypatch.setattr(CrossrefAdapter, "lookup", lambda self, doi: None)
    result = runner.invoke(app, ["grab", "--doi", _DOI, "--venue", _VENUE, "--home", str(home)])
    assert result.exit_code == 1, result.output
    assert _pdf_files(home) == []  # 未建行、未取回


# -- 退出码 0：成功（库内反查 / 未入库建行两路）--------------------------------


def test_in_db_paper_reverse_lookup_succeeds(tmp_path: Path) -> None:
    """库内已绑定 venue 的 paper：无 --venue 经反查确定 venue → resolve+fetch 落盘。"""
    home = _make_home(tmp_path)
    _seed_paper(home, _VENUE, _DOI)
    result = runner.invoke(app, ["grab", "--doi", _DOI, "--home", str(home)])
    assert result.exit_code == 0, result.output
    assert len(_pdf_files(home)) == 1


def test_not_in_db_creates_row_via_crossref(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """未入库建行路径：crossref 单篇 lookup → MergeEngine.ingest(source='crossref') 建最小
    paper 行并绑定 venue → resolve+fetch 单篇全链（AC-4.1 runbook 的 JFE DOI 即此场景）。"""
    home = _make_home(tmp_path)
    seen: list[str] = []

    def _fake_lookup(self: CrossrefAdapter, doi: str) -> PaperStub:
        seen.append(doi)
        return PaperStub(title=f"grabbed {doi}", identifiers=(("doi", doi),))

    monkeypatch.setattr(CrossrefAdapter, "lookup", _fake_lookup)
    result = runner.invoke(app, ["grab", "--doi", _DOI, "--venue", _VENUE, "--home", str(home)])

    assert result.exit_code == 0, result.output
    assert seen == [_DOI]  # 走了 crossref 单篇 lookup
    assert len(_pdf_files(home)) == 1  # 资产落盘
    # 建了 paper 行且绑定到目标 venue（fetch 路由前提）
    db = Database(home / "catalog.sqlite")
    rows = db.query(
        "SELECT p.venue_id FROM paper p JOIN identifier i ON i.paper_id = p.id "
        "WHERE i.scheme = 'doi' AND i.value = ?",
        (_DOI,),
    )
    db.close()
    assert len(rows) == 1 and rows[0]["venue_id"] == _VENUE
