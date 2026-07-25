"""`MergeEngine` 单测（Phase 3 T1；plan §2-1 全裁决点。Phase 6 F1 补审计 P1/P3 定向用例）。

覆盖：source 校验 / 纯新建 / 强合并 / 字段级来源优先级收敛（升/降/补空/同级 tie-break）/
未知 provenance 保护（upsert_paper 存量字段不被覆盖）/ 弱信号候审（正反例 + 观测级键集合）/
跨 paper identifier 冲突 / candidate 单行不重复与证据刷新规则 / 幂等 / matched_identifiers
口径 / DOI 归一强合并。
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from paper_crawler.merge import MergeEngine
from paper_crawler.storage.db import Database
from paper_crawler.storage.repo import Repo
from paper_crawler.types import PaperStub, VenueSpec


def _stub(
    *,
    title: str,
    ids: tuple[tuple[str, str], ...],
    abstract: str | None = None,
    year: int | None = None,
    pub_date: str | None = None,
    authors: tuple[str, ...] = (),
    meta: tuple[tuple[str, str], ...] = (),
) -> PaperStub:
    return PaperStub(
        title=title,
        identifiers=ids,
        abstract=abstract,
        year=year,
        pub_date=pub_date,
        authors=authors,
        meta=meta,
    )


@pytest.fixture
def env(tmp_path: Path) -> Iterator[tuple[Repo, MergeEngine, Path]]:
    db_path = tmp_path / "merge.sqlite"
    database = Database(db_path)
    database.migrate()
    repo = Repo(database)
    engine = MergeEngine(repo)
    yield repo, engine, db_path
    database.close()


def _papers(repo: Repo) -> list[object]:
    return repo.db.query("SELECT * FROM paper")


def _identifiers(repo: Repo) -> list[object]:
    return repo.db.query("SELECT * FROM identifier ORDER BY scheme, value")


def _relations(repo: Repo) -> list[object]:
    return repo.db.query("SELECT * FROM paper_relation")


def _field_src(repo: Repo, paper_id: str) -> dict[str, str]:
    row = repo.db.query("SELECT meta_json FROM paper WHERE id = ?", (paper_id,))[0]
    return dict(json.loads(row["meta_json"]).get("_field_src", {}))


def _weak_keys(repo: Repo) -> list[tuple[str, str]]:
    rows = repo.db.query(
        "SELECT title_norm, first_author FROM paper_weak_key ORDER BY title_norm, first_author"
    )
    return [(r["title_norm"], r["first_author"]) for r in rows]


# -- source 校验 -------------------------------------------------------------


def test_ingest_rejects_unknown_source(env: tuple[Repo, MergeEngine, Path]) -> None:
    _, engine, _ = env
    with pytest.raises(ValueError, match="unknown source"):
        engine.ingest(_stub(title="X", ids=(("doi", "10.1/x"),)), source="bogus")


# -- 纯新建 / 强合并 ----------------------------------------------------------


def test_ingest_creates_new_paper(env: tuple[Repo, MergeEngine, Path]) -> None:
    repo, engine, _ = env
    result = engine.ingest(_stub(title="A", ids=(("doi", "10.1/a"),)), source="crossref")
    assert result.action == "created"
    assert result.matched_identifiers == ()
    assert len(_papers(repo)) == 1


def test_strong_merge_same_doi_two_sources_one_paper_two_identifiers(
    env: tuple[Repo, MergeEngine, Path],
) -> None:
    repo, engine, _ = env
    engine.ingest(_stub(title="A", ids=(("arxiv", "2401.1"), ("doi", "10.1/a"))), source="dblp")
    result = engine.ingest(_stub(title="A", ids=(("doi", "10.1/a"),)), source="crossref")
    assert result.action == "merged"
    assert result.matched_identifiers == ("doi:10.1/a",)
    assert len(_papers(repo)) == 1
    schemes = {r["scheme"] for r in _identifiers(repo)}
    assert schemes == {"arxiv", "doi"}


def test_doi_normalization_enables_strong_merge(env: tuple[Repo, MergeEngine, Path]) -> None:
    """大小写/前缀异形 DOI 经 normalize_doi 归一后强合并到同一 paper。"""
    repo, engine, _ = env
    engine.ingest(_stub(title="A", ids=(("doi", "10.1/ABC"),)), source="crossref")
    result = engine.ingest(
        _stub(title="A", ids=(("doi", "https://doi.org/10.1/abc"),)), source="openalex"
    )
    assert result.action == "merged"
    assert len(_papers(repo)) == 1
    assert [r["value"] for r in _identifiers(repo)] == ["10.1/abc"]


# -- 字段级来源优先级收敛 -----------------------------------------------------


def test_convergence_higher_priority_overwrites(env: tuple[Repo, MergeEngine, Path]) -> None:
    repo, engine, _ = env
    engine.ingest(
        _stub(title="T", ids=(("doi", "10.1/a"),), abstract="s2-abs", year=2019), source="s2"
    )
    engine.ingest(
        _stub(title="T", ids=(("doi", "10.1/a"),), abstract="cr-abs", year=2020),
        source="crossref",
    )
    paper = _papers(repo)[0]
    assert paper["abstract"] == "cr-abs"
    assert paper["year"] == 2020
    src = _field_src(repo, paper["id"])
    assert src["abstract"] == "crossref"
    assert src["year"] == "crossref"


def test_convergence_lower_priority_does_not_overwrite(
    env: tuple[Repo, MergeEngine, Path],
) -> None:
    repo, engine, _ = env
    engine.ingest(_stub(title="T", ids=(("doi", "10.1/a"),), abstract="cr-abs"), source="crossref")
    engine.ingest(_stub(title="T", ids=(("doi", "10.1/a"),), abstract="oa-abs"), source="openalex")
    assert _papers(repo)[0]["abstract"] == "cr-abs"


def test_convergence_fills_empty_regardless_of_priority(
    env: tuple[Repo, MergeEngine, Path],
) -> None:
    repo, engine, _ = env
    # 低优先源先建、缺 abstract；高优先... 反之：高优先先建缺 abstract，低优先补空。
    engine.ingest(_stub(title="T", ids=(("doi", "10.1/a"),)), source="crossref")
    engine.ingest(_stub(title="T", ids=(("doi", "10.1/a"),), abstract="oa-abs"), source="openalex")
    assert _papers(repo)[0]["abstract"] == "oa-abs"  # 空 → 任意来源可补


def test_convergence_meta_keys_union_and_priority(env: tuple[Repo, MergeEngine, Path]) -> None:
    repo, engine, _ = env
    engine.ingest(
        _stub(title="T", ids=(("doi", "10.1/a"),), meta=(("pages", "1-10"),)), source="s2"
    )
    engine.ingest(
        _stub(
            title="T",
            ids=(("doi", "10.1/a"),),
            meta=(("pages", "1-20"), ("jel", "G12")),
        ),
        source="crossref",
    )
    meta = json.loads(_papers(repo)[0]["meta_json"])
    assert meta["pages"] == "1-20"  # crossref > s2 覆盖同键
    assert meta["jel"] == "G12"  # 新键并入


def test_same_source_reobservation_tie_break_takes_smaller_value(
    env: tuple[Repo, MergeEngine, Path],
) -> None:
    """同源二次观测异值 → 取值序更小者（确定性 tie-break，审计 P3「先到胜」修复）。

    优先级表只对跨源定序；同源两次给出不同值时原实现"先到者胜"=顺序敏感。取 min 使两种
    到达顺序收敛同一终值（本例反向序由 `test_merge_property.py` 的全排列属性统一锁）。
    """
    repo, engine, _ = env
    engine.ingest(
        _stub(title="T", ids=(("doi", "10.1/a"),), abstract="b-abs", year=2020, pub_date="2020-02"),
        source="crossref",
    )
    engine.ingest(
        _stub(title="T", ids=(("doi", "10.1/a"),), abstract="a-abs", year=2019, pub_date="2019-01"),
        source="crossref",
    )
    paper = _papers(repo)[0]
    assert paper["abstract"] == "a-abs"  # 字符串值序取小
    assert paper["year"] == 2019  # 数值取小（= 更早的那次观测）
    assert paper["pub_date"] == "2019-01"
    assert _field_src(repo, paper["id"])["year"] == "crossref"  # 同源，provenance 不变


def test_same_source_reobservation_keeps_smaller_value_when_larger_arrives_later(
    env: tuple[Repo, MergeEngine, Path],
) -> None:
    """同上的反向到达序：小值先到、大值后到 → 终值仍为小值（不覆盖）。"""
    repo, engine, _ = env
    engine.ingest(
        _stub(title="T", ids=(("doi", "10.1/a"),), abstract="a-abs", year=2019), source="crossref"
    )
    engine.ingest(
        _stub(title="T", ids=(("doi", "10.1/a"),), abstract="b-abs", year=2020), source="crossref"
    )
    paper = _papers(repo)[0]
    assert paper["abstract"] == "a-abs"
    assert paper["year"] == 2019


# -- 未知 provenance 保护（并存策略核心） -------------------------------------


def test_unknown_provenance_field_not_overwritten_but_empty_filled(
    env: tuple[Repo, MergeEngine, Path],
) -> None:
    """upsert_paper（pull 路径，无 provenance）写的非空字段视为最高优先——只补空不覆盖。"""
    repo, engine, _ = env
    repo.upsert_venue(
        VenueSpec(
            id="v",
            kind="journal",
            names={"full": "V"},  # type: ignore[arg-type]
            field=["finance"],
            metadata_source="crossref",
            fulltext_source="crossref",
        )
    )
    repo.upsert_paper(
        "v", None, _stub(title="Official", ids=(("doi", "10.1/a"),), abstract="official-abs")
    )
    engine.ingest(
        _stub(title="Official", ids=(("doi", "10.1/a"),), abstract="cr-abs", year=2020),
        source="crossref",
    )
    paper = _papers(repo)[0]
    assert paper["abstract"] == "official-abs"  # 存量非空不被覆盖
    assert paper["year"] == 2020  # 存量空字段可补


# -- 弱信号候审 --------------------------------------------------------------


def test_weak_signal_same_title_and_surname_flags_candidate(
    env: tuple[Repo, MergeEngine, Path],
) -> None:
    repo, engine, _ = env
    engine.ingest(
        _stub(title="Deep Learning Survey", ids=(("doi", "10.1/a"),), authors=("Jane Smith",)),
        source="dblp",
    )
    result = engine.ingest(
        _stub(title="Deep Learning Survey", ids=(("doi", "10.1/b"),), authors=("John Smith",)),
        source="crossref",
    )
    assert result.action == "candidate_flagged"
    assert result.matched_identifiers == ()  # 无 identifier 命中（弱信号）
    assert len(_papers(repo)) == 2  # 绝不自动合并
    rels = _relations(repo)
    assert len(rels) == 1
    assert rels[0]["kind"] == "candidate_duplicate"
    assert rels[0]["decided"] is None
    assert "weak-signal-title-author" in rels[0]["evidence_json"]


def test_weak_signal_different_surname_no_candidate(
    env: tuple[Repo, MergeEngine, Path],
) -> None:
    repo, engine, _ = env
    engine.ingest(
        _stub(title="Same Title", ids=(("doi", "10.1/a"),), authors=("Jane Smith",)),
        source="dblp",
    )
    result = engine.ingest(
        _stub(title="Same Title", ids=(("doi", "10.1/b"),), authors=("Bob Jones",)),
        source="crossref",
    )
    assert result.action == "created"
    assert len(_papers(repo)) == 2
    assert _relations(repo) == []


def test_weak_signal_missing_author_no_candidate(
    env: tuple[Repo, MergeEngine, Path],
) -> None:
    repo, engine, _ = env
    engine.ingest(
        _stub(title="Same Title", ids=(("doi", "10.1/a"),), authors=("Jane Smith",)),
        source="dblp",
    )
    result = engine.ingest(_stub(title="Same Title", ids=(("doi", "10.1/b"),)), source="crossref")
    assert result.action == "created"
    assert _relations(repo) == []


def test_weak_signal_blank_author_no_candidate(env: tuple[Repo, MergeEngine, Path]) -> None:
    """首作者名仅空白 → 取姓得 None → 不触发弱信号。"""
    repo, engine, _ = env
    engine.ingest(
        _stub(title="Same Title", ids=(("doi", "10.1/a"),), authors=("Jane Smith",)),
        source="dblp",
    )
    result = engine.ingest(
        _stub(title="Same Title", ids=(("doi", "10.1/b"),), authors=("   ",)), source="crossref"
    )
    assert result.action == "created"
    assert _relations(repo) == []


def test_weak_signal_against_pull_path_paper_without_author(
    env: tuple[Repo, MergeEngine, Path],
) -> None:
    """既有 paper 由 upsert_paper（pull 路径）建、无 _first_author → 弱信号无从确认姓氏 →
    保守不建 candidate（并存策略的弱信号降级）。"""
    repo, engine, _ = env
    repo.upsert_venue(
        VenueSpec(
            id="v",
            kind="journal",
            names={"full": "V"},  # type: ignore[arg-type]
            field=["finance"],
            metadata_source="crossref",
            fulltext_source="crossref",
        )
    )
    repo.upsert_paper("v", None, _stub(title="Shared Title", ids=(("doi", "10.1/a"),)))
    result = engine.ingest(
        _stub(title="Shared Title", ids=(("doi", "10.1/b"),), authors=("Jane Smith",)),
        source="crossref",
    )
    assert result.action == "created"
    assert _relations(repo) == []


def test_weak_signal_latex_unicode_title_variants_match(
    env: tuple[Repo, MergeEngine, Path],
) -> None:
    """标题 LaTeX 形与 Unicode 形归一后 title_norm 相等 → 弱信号命中。"""
    repo, engine, _ = env
    engine.ingest(
        _stub(title=r"Erd\H{o}s Graphs", ids=(("doi", "10.1/a"),), authors=("A. Erdos",)),
        source="dblp",
    )
    result = engine.ingest(
        _stub(title="Erdős Graphs", ids=(("doi", "10.1/b"),), authors=("B. Erdos",)),
        source="crossref",
    )
    assert result.action == "candidate_flagged"
    assert len(_relations(repo)) == 1


# -- 弱信号键集合：收敛不得抹掉匹配面（审计 P1 定向用例，Phase 6 F1） ---------


def test_weak_signal_matches_superseded_title_after_convergence(
    env: tuple[Repo, MergeEngine, Path],
) -> None:
    """高优先源改写标题后，**被顶掉的旧标题**仍留在匹配面上（观测级键集合单调只增）。

    原实现只保留 paper 行的当前 title_norm，此处第三条 stub 会静默漏标候审（审计 P1 的
    fail-safe 侧）。
    """
    repo, engine, _ = env
    engine.ingest(
        _stub(title="Alpha Study", ids=(("doi", "10.1/a"),), authors=("Jane Smith",)), source="s2"
    )
    engine.ingest(  # official > s2 → 改写 title/title_norm
        _stub(title="Beta Study", ids=(("doi", "10.1/a"),), authors=("Jane Smith",)),
        source="official",
    )
    assert _papers(repo)[0]["title"] == "Beta Study"
    assert _weak_keys(repo) == [("alpha study", "smith"), ("beta study", "smith")]

    result = engine.ingest(  # 与**旧**标题撞键
        _stub(title="Alpha Study", ids=(("doi", "10.1/c"),), authors=("John Smith",)),
        source="crossref",
    )
    assert result.action == "candidate_flagged"
    assert len(_papers(repo)) == 2  # 绝不自动合并
    assert len(_relations(repo)) == 1


def test_strong_merge_new_key_flags_candidate_against_existing_paper(
    env: tuple[Repo, MergeEngine, Path],
) -> None:
    """强合并引入新键时也重判候审——审计复现序 `C,A,B` 的那一侧（原实现此处 0 条边）。

    action 仍报 `merged`（`IngestResult` 三枚举是冻结件），候审边作为 DB 副作用落库。
    """
    repo, engine, _ = env
    engine.ingest(  # C：独立 work，键 (beta study, smith)
        _stub(title="Beta Study", ids=(("doi", "10.1/c"),), authors=("John Smith",)),
        source="crossref",
    )
    engine.ingest(  # A：另一 work，键 (alpha study, smith) —— 此时无匹配
        _stub(title="Alpha Study", ids=(("doi", "10.1/a"),), authors=("Jane Smith",)), source="s2"
    )
    assert _relations(repo) == []

    result = engine.ingest(  # B：并入 A 的 paper 并带来键 (beta study, smith) → 撞上 C
        _stub(title="Beta Study", ids=(("doi", "10.1/a"),), authors=("Jane Smith",)),
        source="official",
    )
    assert result.action == "merged"
    assert result.matched_identifiers == ("doi:10.1/a",)
    assert len(_papers(repo)) == 2
    rels = _relations(repo)
    assert len(rels) == 1
    assert "weak-signal-title-author" in rels[0]["evidence_json"]


def test_candidate_pair_single_row_and_evidence_accumulates_shared_keys(
    env: tuple[Repo, MergeEngine, Path],
) -> None:
    """两 paper 共享两个键 → 仍只一行 candidate，证据记**共享键全交**（顺序无关）。"""
    repo, engine, _ = env
    engine.ingest(
        _stub(title="Alpha Study", ids=(("doi", "10.1/a"),), authors=("Jane Smith",)), source="s2"
    )
    engine.ingest(
        _stub(title="Beta Study", ids=(("doi", "10.1/a"),), authors=("Jane Smith",)),
        source="official",
    )
    engine.ingest(
        _stub(title="Alpha Study", ids=(("doi", "10.1/c"),), authors=("John Smith",)),
        source="crossref",
    )
    engine.ingest(  # 第二个共享键
        _stub(title="Beta Study", ids=(("doi", "10.1/c"),), authors=("John Smith",)),
        source="official",
    )
    rels = _relations(repo)
    assert len(rels) == 1  # 一对 paper 至多一行（含反向）
    assert json.loads(rels[0]["evidence_json"])["keys"] == [
        ["alpha study", "smith"],
        ["beta study", "smith"],
    ]


def test_weak_signal_does_not_downgrade_identifier_conflict_evidence(
    env: tuple[Repo, MergeEngine, Path],
) -> None:
    """已有 identifier-conflict 边的一对 paper 再撞弱信号键 → 不降级为弱信号证据。"""
    repo, engine, _ = env
    engine.ingest(
        _stub(title="Alpha Study", ids=(("doi", "10.1/a"),), authors=("Jane Smith",)),
        source="official",
    )
    engine.ingest(
        _stub(title="Alpha Study", ids=(("arxiv", "2401.9"),), authors=("John Smith",)),
        source="official",
    )
    engine.ingest(  # 桥接 stub：两 paper 冲突 → identifier-conflict 边
        _stub(
            title="Alpha Study",
            ids=(("doi", "10.1/a"), ("arxiv", "2401.9")),
            authors=("Jill Smith",),
        ),
        source="crossref",
    )
    rels = _relations(repo)
    assert len(rels) == 1
    assert "identifier-conflict" in rels[0]["evidence_json"]  # 强证据留存
    assert rels[0]["confidence"] == 0.9


def test_decided_candidate_edge_is_never_rewritten(
    env: tuple[Repo, MergeEngine, Path],
) -> None:
    """已人工裁决的候审边（decided 非空）不被后续观测刷新证据（绝不覆盖人工结论）。"""
    repo, engine, _ = env
    engine.ingest(
        _stub(title="Alpha Study", ids=(("doi", "10.1/a"),), authors=("Jane Smith",)), source="s2"
    )
    engine.ingest(
        _stub(title="Alpha Study", ids=(("doi", "10.1/c"),), authors=("John Smith",)),
        source="crossref",
    )
    repo.db.execute("UPDATE paper_relation SET decided = 'rejected'")
    before = _relations(repo)[0]["evidence_json"]
    engine.ingest(  # 给两 paper 再添一个共享键——证据本会刷新，但该边已裁决
        _stub(title="Beta Study", ids=(("doi", "10.1/a"),), authors=("Jane Smith",)),
        source="official",
    )
    engine.ingest(
        _stub(title="Beta Study", ids=(("doi", "10.1/c"),), authors=("John Smith",)),
        source="official",
    )
    rels = _relations(repo)
    assert len(rels) == 1
    assert rels[0]["decided"] == "rejected"
    assert rels[0]["evidence_json"] == before


@pytest.mark.parametrize("stored_evidence", [None, '"not-an-object"'])
def test_unreadable_existing_evidence_is_not_overwritten(
    env: tuple[Repo, MergeEngine, Path], stored_evidence: str | None
) -> None:
    """既有边证据为空/非本模块所写（读不出 reason）→ 视为最强，弱信号不覆盖。"""
    repo, engine, _ = env
    engine.ingest(
        _stub(title="Alpha Study", ids=(("doi", "10.1/a"),), authors=("Jane Smith",)), source="s2"
    )
    engine.ingest(
        _stub(title="Alpha Study", ids=(("doi", "10.1/c"),), authors=("John Smith",)),
        source="crossref",
    )
    repo.db.execute("UPDATE paper_relation SET evidence_json = ?", (stored_evidence,))
    engine.ingest(
        _stub(title="Beta Study", ids=(("doi", "10.1/a"),), authors=("Jane Smith",)),
        source="official",
    )
    engine.ingest(
        _stub(title="Beta Study", ids=(("doi", "10.1/c"),), authors=("John Smith",)),
        source="official",
    )
    rels = _relations(repo)
    assert len(rels) == 1
    assert rels[0]["evidence_json"] == stored_evidence


# -- 跨 paper identifier 冲突 -------------------------------------------------


def test_cross_paper_conflict_flags_candidate_not_merge(
    env: tuple[Repo, MergeEngine, Path],
) -> None:
    repo, engine, _ = env
    engine.ingest(_stub(title="P1", ids=(("doi", "10.1/a"),)), source="official")
    engine.ingest(_stub(title="P2", ids=(("arxiv", "2401.9"),)), source="official")
    result = engine.ingest(
        _stub(title="Bridge", ids=(("doi", "10.1/a"), ("arxiv", "2401.9"))), source="crossref"
    )
    assert result.action == "candidate_flagged"
    assert set(result.matched_identifiers) == {"doi:10.1/a", "arxiv:2401.9"}
    assert len(_papers(repo)) == 2  # 两 paper 不合并
    rels = _relations(repo)
    assert len(rels) == 1
    assert "identifier-conflict" in rels[0]["evidence_json"]
    assert rels[0]["decided"] is None


def test_cross_paper_conflict_winner_has_more_identifiers(
    env: tuple[Repo, MergeEngine, Path],
) -> None:
    """胜者=identifier 数多者：桥接 stub 的字段并入它。"""
    repo, engine, _ = env
    # P1 有 2 个 identifier，P2 有 1 个。
    engine.ingest(_stub(title="P1", ids=(("doi", "10.1/a"), ("openalex", "W1"))), source="official")
    engine.ingest(_stub(title="P2", ids=(("arxiv", "2401.9"),)), source="official")
    engine.ingest(
        _stub(title="Bridge", ids=(("doi", "10.1/a"), ("arxiv", "2401.9")), abstract="bridged"),
        source="crossref",
    )
    # 胜者是 P1（2 identifier）——它拿到桥接 stub 的 abstract。
    p1 = repo.db.query(
        "SELECT * FROM paper WHERE id = (SELECT paper_id FROM identifier WHERE value='W1')"
    )[0]
    assert p1["abstract"] == "bridged"
    p2 = repo.db.query(
        "SELECT * FROM paper WHERE id = (SELECT paper_id FROM identifier WHERE value='2401.9')"
    )[0]
    assert p2["abstract"] is None  # 败者不被并入


# -- 幂等 --------------------------------------------------------------------


def test_ingest_idempotent(env: tuple[Repo, MergeEngine, Path]) -> None:
    repo, engine, _ = env
    stub = _stub(
        title="T",
        ids=(("doi", "10.1/a"), ("arxiv", "2401.1")),
        abstract="abs",
        year=2020,
        authors=("Jane Smith",),
        meta=(("pages", "1-10"),),
    )
    first = engine.ingest(stub, source="crossref")
    before = repo.db.query("SELECT * FROM paper")[0]["meta_json"]
    second = engine.ingest(stub, source="crossref")
    after = repo.db.query("SELECT * FROM paper")[0]["meta_json"]
    assert first.paper_id == second.paper_id
    assert second.action == "merged"
    assert before == after  # meta_json（含 _field_src）不变
    assert len(_papers(repo)) == 1
    assert len(_identifiers(repo)) == 2
