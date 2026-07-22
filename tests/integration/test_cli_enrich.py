"""`crawler enrich` CLI 集成测试（plan §2-5/§4 T6）。

覆盖 CLI 接线本身（DB 里 DOI 集合的取集/`--venue`/`--source`/`--limit` 过滤/摘要渲染/
退出码/多 source 编排/config 凭证注入是否正确传达到 adapter 实例），不重复
`tests/unit/test_openalex_adapter.py`/`test_s2_adapter.py` 已覆盖的 `enrich_batch`
内部逻辑（批切分/预算熔断/错误映射细节）——本文件把 `enrich_batch` 猴补丁为受控假
实现（同 `test_cli_oa_report.py` 对 `UnpaywallAdapter.lookup` 的既有手法），只验证
CLI 层"取 DOI → 分派 source → 回注 MergeEngine → 渲染摘要"这条链路本身走对。
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from paper_crawler.adapters.openalex.adapter import OpenAlexAdapter
from paper_crawler.adapters.s2.adapter import S2Adapter
from paper_crawler.cli import app
from paper_crawler.errors import CrawlerError, ErrorClass
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


def _make_home(
    tmp_path: Path, *, with_venues_dir: bool = False, extra_config_toml: str = ""
) -> Path:
    """构造一个隔离的 home 目录；`--venue` 用例需 `with_venues_dir=True`（`_require_
    known_venue` 靠 `VenueRegistry`——registry 只识别 `venues_dirs` 下的 YAML 文件，
    单靠 DB 内的 venue 行不够，同 `test_cli_oa_report.py` 的既有手法）。
    `extra_config_toml` 用于追加 T6 凭证/预算段落（`[auth.openalex]`/`[auth.s2]`/
    `[openalex]`），与 `[paths]` 段落合并写入同一份 config.toml。
    """
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    lines = [extra_config_toml] if extra_config_toml else []
    if with_venues_dir:
        venues_dir = home / "venues"
        venues_dir.mkdir(parents=True)
        lines.append('[paths]\nvenues_dirs = ["venues"]\n')
        _write_venue_yaml(venues_dir, _VENUE_A)
        _write_venue_yaml(venues_dir, _VENUE_B)
    if lines:
        (home / "config.toml").write_text("\n".join(lines), encoding="utf-8")
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


def _abstract_of(home: Path, doi: str) -> str | None:
    db = Database(home / "catalog.sqlite")
    rows = db.query(
        "SELECT p.abstract FROM paper p JOIN identifier i ON i.paper_id = p.id "
        "WHERE i.scheme = 'doi' AND i.value = ?",
        (doi,),
    )
    db.close()
    return str(rows[0]["abstract"]) if rows and rows[0]["abstract"] is not None else None


def _stub(doi: str, *, abstract: str | None = None) -> PaperStub:
    return PaperStub(title=f"enriched {doi}", identifiers=(("doi", doi),), abstract=abstract)


# --- 无 DOI ---------------------------------------------------------------------------------


def test_no_dois_in_library_prints_message_and_exits_0(tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    _seed_dois(home, {})

    result = runner.invoke(app, ["enrich", "--home", str(home)])

    assert result.exit_code == 0, result.output
    assert "无" in result.output


# --- 用法错 ----------------------------------------------------------------------------------


def test_unknown_venue_exits_2(tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    _seed_dois(home, {_VENUE_A: ["10.0/a1"]})

    result = runner.invoke(app, ["enrich", "--venue", "not_a_real_venue", "--home", str(home)])

    assert result.exit_code == 2


def test_unknown_source_exits_2(tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    _seed_dois(home, {_VENUE_A: ["10.0/a1"]})

    result = runner.invoke(app, ["enrich", "--source", "bogus", "--home", str(home)])

    assert result.exit_code == 2
    assert "bogus" in result.output


# --- 单 source 正常路径：路由 + MergeEngine 回注 ---------------------------------------------


def test_openalex_source_enriches_and_merges_into_existing_paper(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home = _make_home(tmp_path)
    _seed_dois(home, {_VENUE_A: ["10.0/hit"]})  # 既有 paper：无 abstract

    def _fake_enrich_batch(self: OpenAlexAdapter, dois: Sequence[str]) -> list[PaperStub]:
        assert list(dois) == ["10.0/hit"]
        return [_stub("10.0/hit", abstract="富化后的摘要")]

    monkeypatch.setattr(OpenAlexAdapter, "enrich_batch", _fake_enrich_batch)

    result = runner.invoke(app, ["enrich", "--source", "openalex", "--home", str(home)])

    assert result.exit_code == 0, result.output
    assert "[openalex]" in result.output
    assert "处理 1 篇" in result.output
    assert "merged=1" in result.output
    assert "预算消耗" in result.output  # openalex 专属附注
    assert _abstract_of(home, "10.0/hit") == "富化后的摘要"  # 真正回注入库，非仅计数


def test_s2_source_enriches_without_openalex_budget_note(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home = _make_home(tmp_path)
    _seed_dois(home, {_VENUE_A: ["10.0/hit"]})

    def _fake_enrich_batch(self: S2Adapter, dois: Sequence[str]) -> list[PaperStub]:
        return [_stub("10.0/hit", abstract=None)]

    monkeypatch.setattr(S2Adapter, "enrich_batch", _fake_enrich_batch)

    result = runner.invoke(app, ["enrich", "--source", "s2", "--home", str(home)])

    assert result.exit_code == 0, result.output
    assert "[s2]" in result.output
    assert "处理 1 篇" in result.output
    assert "预算消耗" not in result.output  # s2 无预算护栏概念


def test_created_vs_merged_action_counts_reflected_in_summary(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`enrich_batch` 产出一个库内已有 DOI（→merged）+ 一个全新 DOI（→created，
    openalex 位阶低于官方/crossref/dblp 但仍可对全新 paper 新建）。"""
    home = _make_home(tmp_path)
    _seed_dois(home, {_VENUE_A: ["10.0/existing"]})

    def _fake_enrich_batch(self: OpenAlexAdapter, dois: Sequence[str]) -> list[PaperStub]:
        return [
            _stub("10.0/existing", abstract="new abstract"),
            PaperStub(title="Brand New", identifiers=(("openalex", "W_new_only"),)),
        ]

    monkeypatch.setattr(OpenAlexAdapter, "enrich_batch", _fake_enrich_batch)

    result = runner.invoke(app, ["enrich", "--source", "openalex", "--home", str(home)])

    assert result.exit_code == 0, result.output
    assert "处理 2 篇" in result.output
    assert "created=1" in result.output
    assert "merged=1" in result.output


# --- 双 source（省略 --source）------------------------------------------------------------------


def test_omitting_source_runs_both_openalex_and_s2(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home = _make_home(tmp_path)
    _seed_dois(home, {_VENUE_A: ["10.0/a"]})

    calls: list[str] = []

    def _fake_openalex(self: OpenAlexAdapter, dois: Sequence[str]) -> list[PaperStub]:
        calls.append("openalex")
        return []

    def _fake_s2(self: S2Adapter, dois: Sequence[str]) -> list[PaperStub]:
        calls.append("s2")
        return []

    monkeypatch.setattr(OpenAlexAdapter, "enrich_batch", _fake_openalex)
    monkeypatch.setattr(S2Adapter, "enrich_batch", _fake_s2)

    result = runner.invoke(app, ["enrich", "--home", str(home)])

    assert result.exit_code == 0, result.output
    assert set(calls) == {"openalex", "s2"}
    assert "[openalex]" in result.output
    assert "[s2]" in result.output


# --- --venue 过滤 / --limit 截断 ------------------------------------------------------------------


def test_venue_filter_only_passes_that_venues_dois(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home = _make_home(tmp_path, with_venues_dir=True)
    _seed_dois(home, {_VENUE_A: ["10.0/a1", "10.0/a2"], _VENUE_B: ["10.0/b1"]})

    seen: list[str] = []

    def _fake_enrich_batch(self: OpenAlexAdapter, dois: Sequence[str]) -> list[PaperStub]:
        seen.extend(dois)
        return []

    monkeypatch.setattr(OpenAlexAdapter, "enrich_batch", _fake_enrich_batch)

    result = runner.invoke(
        app, ["enrich", "--source", "openalex", "--venue", _VENUE_A, "--home", str(home)]
    )

    assert result.exit_code == 0, result.output
    assert sorted(seen) == ["10.0/a1", "10.0/a2"]


def test_limit_truncates_scanned_dois(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    _seed_dois(home, {_VENUE_A: ["10.0/a", "10.0/b", "10.0/c"]})

    seen: list[str] = []

    def _fake_enrich_batch(self: OpenAlexAdapter, dois: Sequence[str]) -> list[PaperStub]:
        seen.extend(dois)
        return []

    monkeypatch.setattr(OpenAlexAdapter, "enrich_batch", _fake_enrich_batch)

    result = runner.invoke(
        app, ["enrich", "--source", "openalex", "--limit", "2", "--home", str(home)]
    )

    assert result.exit_code == 0, result.output
    assert len(seen) == 2


# --- 中途错误：提前终止但不崩溃、退出码仍 0 --------------------------------------------------


def test_error_mid_run_records_stopped_reason_but_exits_0(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home = _make_home(tmp_path)
    _seed_dois(home, {_VENUE_A: ["10.0/a"]})

    def _fake_enrich_batch(self: OpenAlexAdapter, dois: Sequence[str]) -> list[PaperStub]:
        raise CrawlerError(ErrorClass.RATE_LIMITED, "openalex daily budget exhausted")

    monkeypatch.setattr(OpenAlexAdapter, "enrich_batch", _fake_enrich_batch)

    result = runner.invoke(app, ["enrich", "--source", "openalex", "--home", str(home)])

    assert result.exit_code == 0, result.output
    assert "提前终止" in result.output
    assert "rate_limited" in result.output
    assert "处理 0 篇" in result.output


def test_s2_no_key_configured_shows_config_stop_reason_when_run_via_both_sources(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """未打猴补丁的真实 `S2Adapter.enrich_batch`（无 key）在 CLI 编排下自然产出
    "提前终止: config: ..." 摘要行，不影响 openalex 分支继续跑完（不同 source 互相
    独立，见 `enrich` 命令 docstring）。"""
    home = _make_home(tmp_path)
    _seed_dois(home, {_VENUE_A: ["10.0/a"]})

    def _fake_openalex(self: OpenAlexAdapter, dois: Sequence[str]) -> list[PaperStub]:
        return [_stub("10.0/a")]

    monkeypatch.setattr(OpenAlexAdapter, "enrich_batch", _fake_openalex)
    # S2Adapter.enrich_batch 未打补丁：真实实现在无 key 时直接 CONFIG，不发网络请求。

    result = runner.invoke(app, ["enrich", "--home", str(home)])

    assert result.exit_code == 0, result.output
    assert "[openalex]" in result.output
    assert "[s2]" in result.output
    assert "提前终止: config" in result.output


# --- config 凭证注入确实传达到 adapter 实例 -----------------------------------------------------


def test_openalex_api_key_from_config_toml_reaches_adapter_instance(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home = _make_home(
        tmp_path,
        extra_config_toml=(
            '[auth.openalex]\napi_key = "openalex-secret"\n[openalex]\ndaily_budget_usd = 1.25\n'
        ),
    )
    _seed_dois(home, {_VENUE_A: ["10.0/a"]})

    seen_keys: list[str | None] = []
    seen_budgets: list[float] = []

    def _fake_enrich_batch(self: OpenAlexAdapter, dois: Sequence[str]) -> list[PaperStub]:
        seen_keys.append(self._api_key)
        seen_budgets.append(self._daily_budget_usd)
        return []

    monkeypatch.setattr(OpenAlexAdapter, "enrich_batch", _fake_enrich_batch)

    result = runner.invoke(app, ["enrich", "--source", "openalex", "--home", str(home)])

    assert result.exit_code == 0, result.output
    assert seen_keys == ["openalex-secret"]
    assert seen_budgets == [1.25]


def test_s2_api_key_from_config_toml_reaches_adapter_and_request_header(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home = _make_home(tmp_path, extra_config_toml='[auth.s2]\napi_key = "s2-secret"\n')
    _seed_dois(home, {_VENUE_A: ["10.0/a"]})

    seen_keys: list[str | None] = []
    seen_headers: list[str | None] = []

    def _fake_enrich_batch(self: S2Adapter, dois: Sequence[str]) -> list[PaperStub]:
        seen_keys.append(self._api_key)
        # 专属 client 应携正确的 x-api-key 头（CLI 装配期构造，见 cli.py
        # `_prepare_enrich_source` docstring 的凭证隔离说明）。
        seen_headers.append(self._client()._client.headers.get("x-api-key"))
        return []

    monkeypatch.setattr(S2Adapter, "enrich_batch", _fake_enrich_batch)

    result = runner.invoke(app, ["enrich", "--source", "s2", "--home", str(home)])

    assert result.exit_code == 0, result.output
    assert seen_keys == ["s2-secret"]
    assert seen_headers == ["s2-secret"]
