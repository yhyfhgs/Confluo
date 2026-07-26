"""preprint↔published 关联报告单测（T16；AC-7.4 后半，design/06 §3 preprint_of 语义）。

`build_preprint_report`/`render_preprint_report_markdown` 是纯函数层（同
`adapters/unpaywall/report.py`/`subs/report.py`/`pipeline/report.py` 既有三处先例的
分工：不查 DB、不做 CLI 接线）。`build_preprint_report` 消费
`Repo.list_preprint_relations()` 的真实 `sqlite3.Row` 序列（经一个临时 `Repo` 建出
真实 preprint_of 边取得，覆盖聚合/证据解析/decided 展示五类场景）；
`render_preprint_report_markdown` 用手工构造的 `PreprintRelationRow` 覆盖渲染细节
（分组/表格转义/空报告响亮陈述），不依赖 DB。
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Literal

import pytest

from paper_crawler import preprint_report
from paper_crawler.preprint_report import (
    PreprintRelationRow,
    PreprintReport,
    _evidence_cell,
    _evidence_fields,
)
from paper_crawler.storage.db import Database
from paper_crawler.storage.repo import MergeInput, Repo
from paper_crawler.types import PaperStub, VenueSpec

_JOURNAL_VENUE = "mock_journal"
_ARXIV_VENUE = "arxiv_mock"


def _venue(
    venue_id: str,
    full_name: str,
    *,
    kind: Literal["journal", "conference", "preprint_channel"] = "journal",
) -> VenueSpec:
    return VenueSpec(
        id=venue_id,
        kind=kind,
        names={"full": full_name, "aliases": []},
        field=["cs_ai"],
        identifiers={},
        metadata_source="mock_platform",
        fulltext_source="mock_platform",
    )


@pytest.fixture
def repo(tmp_path: Path) -> Iterator[Repo]:
    database = Database(tmp_path / "repo.sqlite")
    database.migrate()
    r = Repo(database)
    r.upsert_venue(_venue(_JOURNAL_VENUE, "Mock Journal"))
    r.upsert_venue(_venue(_ARXIV_VENUE, "ArXiv Mock", kind="preprint_channel"))
    yield r
    database.close()


def _merge_input(
    *, title: str, meta: tuple[tuple[str, str], ...] = (), source: str = "crossref"
) -> MergeInput:
    return MergeInput(
        title=title,
        title_norm=title.lower(),
        first_author=None,
        abstract=None,
        year=None,
        pub_date=None,
        meta=meta,
        source=source,
        priority={"crossref": 1, "official": 2},
    )


# --- build_preprint_report：聚合逻辑（真实 Repo 建边）-------------------------------------------


def test_build_report_empty_repo_produces_zero_total() -> None:
    rep = preprint_report.build_preprint_report([])
    assert rep.total == 0
    assert rep.rows == ()
    assert rep.pending_count == 0
    assert rep.decided_counts() == {}


def test_build_report_from_real_edge_populates_all_fields(repo: Repo) -> None:
    repo.upsert_paper(
        _JOURNAL_VENUE, None, PaperStub(title="Published X", identifiers=(("doi", "10.1/x"),))
    )
    repo.upsert_paper(
        _ARXIV_VENUE,
        None,
        PaperStub(
            title="Preprint X",
            identifiers=(("arxiv", "2401.11111"),),
            meta=(("doi", "10.1/x"),),
        ),
    )
    rep = preprint_report.build_preprint_report(repo.list_preprint_relations())
    assert rep.total == 1
    row = rep.rows[0]
    assert row.preprint_title == "Preprint X"
    assert row.preprint_venue == "ArXiv Mock"
    assert row.published_title == "Published X"
    assert row.published_venue == "Mock Journal"
    assert row.clue_key == "doi"
    assert row.clue_value == "10.1/x"
    assert row.evidence_source == _ARXIV_VENUE  # pull 路径：venue_id 搭车进 evidence
    assert row.decided is None


def test_build_report_aggregator_path_evidence_source_is_merge_source(repo: Repo) -> None:
    """aggregator 路径（`merge_ingest`）的证据溯源字段是 `source`（非 `venue_id`，两者互斥）。"""
    repo.merge_ingest(
        _merge_input(title="Agg Published", source="crossref"),
        identifiers=(("doi", "10.2/agg"),),
    )
    repo.merge_ingest(
        _merge_input(title="Agg Preprint", meta=(("doi", "10.2/agg"),), source="official"),
        identifiers=(("arxiv", "2401.22222"),),
    )
    rep = preprint_report.build_preprint_report(repo.list_preprint_relations())
    assert rep.total == 1
    assert rep.rows[0].evidence_source == "official"
    assert rep.rows[0].preprint_venue is None
    assert rep.rows[0].published_venue is None


def test_build_report_counts_pending_and_decided_states(repo: Repo) -> None:
    """pending（decided=NULL）与已裁决（rejected）各自计数，互不干扰。"""
    repo.upsert_paper(
        _JOURNAL_VENUE, None, PaperStub(title="Pub Pending", identifiers=(("doi", "10.1/p"),))
    )
    repo.upsert_paper(
        _ARXIV_VENUE,
        None,
        PaperStub(
            title="Pre Pending", identifiers=(("arxiv", "2401.33333"),), meta=(("doi", "10.1/p"),)
        ),
    )
    repo.upsert_paper(
        _JOURNAL_VENUE, None, PaperStub(title="Pub Rejected", identifiers=(("doi", "10.1/r"),))
    )
    repo.upsert_paper(
        _ARXIV_VENUE,
        None,
        PaperStub(
            title="Pre Rejected",
            identifiers=(("arxiv", "2401.44444"),),
            meta=(("doi", "10.1/r"),),
        ),
    )
    repo.db.execute(
        "UPDATE paper_relation SET decided = 'rejected' WHERE kind = 'preprint_of' "
        "AND from_paper = (SELECT paper_id FROM identifier WHERE value = '2401.44444')"
    )

    rep = preprint_report.build_preprint_report(repo.list_preprint_relations())
    assert rep.total == 2
    assert rep.pending_count == 1
    assert rep.decided_counts() == {"rejected": 1}


def test_build_report_malformed_evidence_json_degrades_gracefully(repo: Repo) -> None:
    """evidence_json 若被外部损坏（非法 JSON）→ 证据字段全 None，不整体崩溃（防御性）。"""
    repo.upsert_paper(
        _JOURNAL_VENUE, None, PaperStub(title="Pub Broken", identifiers=(("doi", "10.1/broken"),))
    )
    repo.upsert_paper(
        _ARXIV_VENUE,
        None,
        PaperStub(
            title="Pre Broken",
            identifiers=(("arxiv", "2401.55555"),),
            meta=(("doi", "10.1/broken"),),
        ),
    )
    repo.db.execute(
        "UPDATE paper_relation SET evidence_json = 'not-json{{' WHERE kind = 'preprint_of'"
    )

    rep = preprint_report.build_preprint_report(repo.list_preprint_relations())
    assert rep.total == 1
    assert rep.rows[0].clue_key is None
    assert rep.rows[0].clue_value is None
    assert rep.rows[0].evidence_source is None


# --- render_preprint_report_markdown：渲染（手工构造行，不依赖 DB）------------------------------


def _row(
    *,
    preprint_title: str = "Preprint",
    preprint_venue: str | None = "ArXiv",
    preprint_year: int | None = 2024,
    published_title: str = "Published",
    published_venue: str | None = "Journal",
    published_year: int | None = 2025,
    clue_key: str | None = "doi",
    clue_value: str | None = "10.1/x",
    evidence_source: str | None = "arxiv_mock",
    decided: str | None = None,
) -> PreprintRelationRow:
    return PreprintRelationRow(
        preprint_id="p1",
        preprint_title=preprint_title,
        preprint_venue=preprint_venue,
        preprint_year=preprint_year,
        published_id="p2",
        published_title=published_title,
        published_venue=published_venue,
        published_year=published_year,
        clue_key=clue_key,
        clue_value=clue_value,
        evidence_source=evidence_source,
        decided=decided,
    )


def test_render_empty_report_is_loud_not_silent() -> None:
    """零边空报告：明确陈述"暂无关联边"，不是一份只有标题的空文档（响亮空态）。"""
    md = preprint_report.render_preprint_report_markdown(PreprintReport(total=0, rows=()))
    assert "暂无" in md
    assert "0" in md


def test_render_nonempty_report_includes_overview_and_row_fields() -> None:
    rep = PreprintReport(total=1, rows=(_row(),))
    md = preprint_report.render_preprint_report_markdown(rep)
    assert "边总数: 1" in md
    assert "Preprint" in md
    assert "ArXiv" in md
    assert "2024" in md
    assert "Published" in md
    assert "Journal" in md
    assert "2025" in md
    assert "doi=10.1/x" in md
    assert "arxiv_mock" in md
    assert "待复核" in md  # decided=None 渲染为人类可读的"待复核"


def test_render_decided_state_shown_verbatim() -> None:
    rep = PreprintReport(total=1, rows=(_row(decided="rejected"),))
    md = preprint_report.render_preprint_report_markdown(rep)
    assert "rejected" in md


def test_render_groups_by_published_venue_with_null_bucket_last() -> None:
    rows = (
        _row(published_venue="Zeta Journal", published_title="Z Pub"),
        _row(published_venue=None, published_title="No Venue Pub"),
        _row(published_venue="Alpha Journal", published_title="A Pub"),
    )
    rep = PreprintReport(total=3, rows=rows)
    md = preprint_report.render_preprint_report_markdown(rep)
    # 分组标题均应出现
    assert "### Zeta Journal" in md
    assert "### Alpha Journal" in md
    assert "未挂靠" in md
    # Repo 层已按 venue 排序,本模块只按既有序切分组——这里手工构造的 rows 顺序即分组出现顺序
    zeta_pos = md.index("### Zeta Journal")
    unlinked_pos = md.index("未挂靠")
    alpha_pos = md.index("### Alpha Journal")
    assert zeta_pos < unlinked_pos < alpha_pos


def test_render_missing_evidence_and_venue_fields_use_dash_placeholder() -> None:
    row = _row(
        preprint_venue=None,
        preprint_year=None,
        clue_key=None,
        clue_value=None,
        evidence_source=None,
    )
    rep = PreprintReport(total=1, rows=(row,))
    md = preprint_report.render_preprint_report_markdown(rep)
    assert "-" in md  # 占位符存在（不留空单元格）


def test_render_escapes_pipe_characters_in_titles() -> None:
    row = _row(preprint_title="A | B", published_title="C | D")
    rep = PreprintReport(total=1, rows=(row,))
    md = preprint_report.render_preprint_report_markdown(rep)
    assert "A \\| B" in md
    assert "C \\| D" in md


def test_render_multiple_edges_under_same_published_venue_share_one_table() -> None:
    """两条边同一 published venue → 归入同一分组（唯一一个"### "标题），非各自一段。"""
    rows = (
        _row(published_venue="Shared Journal", published_title="Pub One", preprint_title="Pre One"),
        _row(published_venue="Shared Journal", published_title="Pub Two", preprint_title="Pre Two"),
    )
    rep = PreprintReport(total=2, rows=rows)
    md = preprint_report.render_preprint_report_markdown(rep)
    assert md.count("### Shared Journal") == 1
    assert "Pre One" in md
    assert "Pre Two" in md


# --- 私有小工具的边界直测（补 branch 覆盖：正常调用路径不易触达的组合）------------------------


def test_evidence_fields_none_or_empty_input_returns_all_none() -> None:
    assert _evidence_fields(None) == (None, None, None)
    assert _evidence_fields("") == (None, None, None)


def test_evidence_fields_non_dict_json_returns_all_none() -> None:
    """`evidence_json` 是合法 JSON 但顶层不是对象（如数组）→ 同样降级为全 None。"""
    assert _evidence_fields("[1, 2, 3]") == (None, None, None)


def test_evidence_cell_clue_without_source() -> None:
    row = _row(evidence_source=None)
    assert _evidence_cell(row) == f"{row.clue_key}={row.clue_value}"


def test_evidence_cell_source_without_clue() -> None:
    row = _row(clue_key=None, clue_value=None, evidence_source="some_source")
    assert _evidence_cell(row) == "来源: some_source"
