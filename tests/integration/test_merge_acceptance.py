"""合并引擎验收用例 AC-3.1 / AC-3.2（Phase 3 T1；plan §6）。

- AC-3.1 强合并：同一 DOI 经**混合双路**注入（arxiv 经既有 `Repo.upsert_paper` pull 路径 +
  crossref 经 `MergeEngine.ingest` aggregator 路径）→ 库内 1 paper、≥2 identifier。
  混合双路是 controller 2026-07-22 条件②的真实形态（不许两路都走 MergeEngine 自证）。
- AC-3.2 弱信号候审：WP↔刊发版（同规范化标题、异 DOI、同首作者）→ 2 paper +
  1 candidate_duplicate(decided=NULL)；绝不自动合并。附「标题真改名」反例：归一后不同 →
  2 paper、无 candidate（宁可两条独立待 identifier 证据，D-007）。
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from paper_crawler.merge import MergeEngine
from paper_crawler.storage.db import Database
from paper_crawler.storage.repo import Repo
from paper_crawler.types import PaperStub, VenueNames, VenueSpec


@pytest.fixture
def env(tmp_path: Path) -> Iterator[tuple[Repo, MergeEngine]]:
    database = Database(tmp_path / "acc.sqlite")
    database.migrate()
    repo = Repo(database)
    repo.upsert_venue(
        VenueSpec(
            id="arxiv_ch",
            kind="preprint_channel",
            names=VenueNames(full="arXiv"),
            field=["cs_ai"],
            metadata_source="arxiv",
            fulltext_source="arxiv",
        )
    )
    yield repo, MergeEngine(repo)
    database.close()


def _paper_count(repo: Repo) -> int:
    return int(repo.db.query("SELECT COUNT(*) AS n FROM paper")[0]["n"])


def _identifiers_of_single_paper(repo: Repo) -> set[tuple[str, str]]:
    rows = repo.db.query("SELECT scheme, value FROM identifier")
    return {(r["scheme"], r["value"]) for r in rows}


# -- AC-3.1 强合并（混合双路） -----------------------------------------------


def test_ac_3_1_mixed_dual_path_one_paper_two_identifiers(
    env: tuple[Repo, MergeEngine],
) -> None:
    repo, engine = env
    # arxiv 路：既有 pull 路径 upsert_paper（携 arxiv + doi）。
    repo.upsert_paper(
        "arxiv_ch",
        None,
        PaperStub(
            title="Attention Is All You Need",
            identifiers=(("arxiv", "1706.03762"), ("doi", "10.5555/aiayn")),
        ),
    )
    # crossref 路：MergeEngine.ingest 注入同一 DOI。
    result = engine.ingest(
        PaperStub(title="Attention Is All You Need", identifiers=(("doi", "10.5555/aiayn"),)),
        source="crossref",
    )

    assert result.action == "merged"
    assert result.matched_identifiers == ("doi:10.5555/aiayn",)
    assert _paper_count(repo) == 1
    ids = _identifiers_of_single_paper(repo)
    assert ("arxiv", "1706.03762") in ids
    assert ("doi", "10.5555/aiayn") in ids
    assert len(ids) >= 2


def test_ac_3_1_mixed_dual_path_merges_across_doi_case_difference(
    env: tuple[Repo, MergeEngine],
) -> None:
    """混合双路的分裂风险已收敛：pull 路径写大小写异形 DOI，两路经 normalize_doi 仍强合并。"""
    repo, engine = env
    repo.upsert_paper(
        "arxiv_ch",
        None,
        PaperStub(
            title="Attention Is All You Need",
            identifiers=(("arxiv", "1706.03762"), ("doi", "10.5555/AIAYN")),  # 大写
        ),
    )
    result = engine.ingest(
        PaperStub(
            title="Attention Is All You Need",
            identifiers=(("doi", "https://doi.org/10.5555/aiayn"),),  # 前缀形
        ),
        source="crossref",
    )
    assert result.action == "merged"
    assert _paper_count(repo) == 1
    ids = _identifiers_of_single_paper(repo)
    assert ("doi", "10.5555/aiayn") in ids  # 两路都归一到同一形
    assert ("arxiv", "1706.03762") in ids


# -- AC-3.2 弱信号候审 -------------------------------------------------------


def test_ac_3_2_wp_vs_published_two_papers_one_candidate(
    env: tuple[Repo, MergeEngine],
) -> None:
    repo, engine = env
    # WP 版（SSRN）
    engine.ingest(
        PaperStub(
            title="The Q-Theory of Investment",
            identifiers=(("ssrn", "3210001"),),
            authors=("Jane Q. Smith", "Bob Lee"),
        ),
        source="s2",
    )
    # 刊发版（journal DOI）——标题排版微异（末尾句点/大小写），归一后与 WP 相等；同首作者。
    result = engine.ingest(
        PaperStub(
            title="The Q-theory of investment.",
            identifiers=(("doi", "10.1111/jofi.12345"),),
            authors=("Jane Q. Smith", "Carol Ng"),
        ),
        source="crossref",
    )

    assert result.action == "candidate_flagged"
    assert result.matched_identifiers == ()  # 弱信号：无 identifier 命中
    assert _paper_count(repo) == 2  # 绝不自动合并
    rels = repo.db.query("SELECT * FROM paper_relation WHERE kind = 'candidate_duplicate'")
    assert len(rels) == 1
    assert rels[0]["decided"] is None
    assert "weak-signal-title-author" in rels[0]["evidence_json"]


def test_ac_3_2_genuinely_renamed_title_no_candidate(
    env: tuple[Repo, MergeEngine],
) -> None:
    """标题归一后确实不同（真改名）→ 2 paper、无 candidate（待 identifier 证据，D-007）。"""
    repo, engine = env
    engine.ingest(
        PaperStub(
            title="A Theory of Investment Under Uncertainty",
            identifiers=(("ssrn", "3210002"),),
            authors=("Jane Q. Smith",),
        ),
        source="s2",
    )
    result = engine.ingest(
        PaperStub(
            title="Investment Dynamics and the Cost of Capital",
            identifiers=(("doi", "10.1111/jofi.12346"),),
            authors=("Jane Q. Smith",),
        ),
        source="crossref",
    )
    assert result.action == "created"
    assert _paper_count(repo) == 2
    assert repo.db.query("SELECT COUNT(*) AS n FROM paper_relation")[0]["n"] == 0
