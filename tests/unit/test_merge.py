"""`MergeEngine` 单测（Phase 3 T1；plan §2-1 全裁决点。Phase 6 F1 补审计 P1/P3 定向用例）。

覆盖：source 校验 / 纯新建 / 强合并 / 字段级来源优先级收敛（升/降/补空/同级 tie-break）/
未知 provenance 保护（upsert_paper 存量字段不被覆盖）/ 弱信号候审（正反例 + 观测级键集合）/
跨 paper identifier 冲突 / candidate 单行不重复与证据刷新规则 / 幂等 / matched_identifiers
口径 / DOI 归一强合并 / preprint_of 建边（T10：MergeEngine.ingest() 路径；pull 路径
`upsert_paper` 的对应用例见 test_repo.py）。
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from pathlib import Path

import pytest

from paper_crawler.merge import MergeEngine
from paper_crawler.storage.db import Database
from paper_crawler.storage.repo import Repo, _evidence_strength
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


def _meta(repo: Repo, paper_id: str) -> dict[str, object]:
    row = repo.db.query("SELECT meta_json FROM paper WHERE id = ?", (paper_id,))[0]
    return dict(json.loads(row["meta_json"]))


def _field_src(repo: Repo, paper_id: str) -> dict[str, str]:
    return dict(_meta(repo, paper_id).get("_field_src", {}))  # type: ignore[arg-type]


def _weak_keys(repo: Repo) -> list[tuple[str, str]]:
    rows = repo.db.query(
        "SELECT title_norm, first_author FROM paper_weak_key ORDER BY title_norm, first_author"
    )
    return [(r["title_norm"], r["first_author"]) for r in rows]


def _weak_keys_of(repo: Repo, paper_id: str) -> list[tuple[str, str]]:
    rows = repo.db.query(
        "SELECT title_norm, first_author FROM paper_weak_key WHERE paper_id = ? "
        "ORDER BY title_norm, first_author",
        (paper_id,),
    )
    return [(r["title_norm"], r["first_author"]) for r in rows]


def _paper_id_by_identifier(repo: Repo, scheme: str, value: str) -> str:
    rows = repo.db.query(
        "SELECT paper_id FROM identifier WHERE scheme = ? AND value = ?", (scheme, value)
    )
    return str(rows[0]["paper_id"])


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


@pytest.mark.parametrize("reversed_order", [False, True])
def test_same_source_reobservation_tie_break_is_deterministic(
    env: tuple[Repo, MergeEngine, Path], reversed_order: bool
) -> None:
    """同源二次观测异值 → 确定性 tie-break（审计 P3「先到胜」修复），两种到达序同终值。

    文本（abstract/title）**更长者胜**（同源复查最常见形态是信息增补）；有序标量
    （year/pub_date）取 min（= 更早的那次观测）。
    """
    repo, engine, _ = env
    first = _stub(
        title="T",
        ids=(("doi", "10.1/a"),),
        abstract="short abstract",
        year=2020,
        pub_date="2020-02",
    )
    second = _stub(
        title="T",
        ids=(("doi", "10.1/a"),),
        abstract="short abstract, now with the full text",
        year=2019,
        pub_date="2019-01",
    )
    order = [second, first] if reversed_order else [first, second]
    for stub in order:
        engine.ingest(stub, source="crossref")

    paper = _papers(repo)[0]
    assert paper["abstract"] == "short abstract, now with the full text"  # 文本取长
    assert paper["year"] == 2019  # 有序标量取小
    assert paper["pub_date"] == "2019-01"
    assert _field_src(repo, paper["id"])["year"] == "crossref"  # 同源，provenance 不变
    # 取证抓手：三个字段都发生过同源异值（集合并，与到达顺序无关）。
    assert _meta(repo, paper["id"])["_field_tie"] == ["abstract", "pub_date", "year"]


def test_equal_length_text_tie_break_takes_lexicographically_smaller(
    env: tuple[Repo, MergeEngine, Path],
) -> None:
    """文本等长 → 复合序退到字典序取小（`(-len, str)` 仍是全序，min 幂等/交换/结合）。"""
    repo, engine, _ = env
    engine.ingest(_stub(title="T", ids=(("doi", "10.1/a"),), abstract="b-abs"), source="crossref")
    engine.ingest(_stub(title="T", ids=(("doi", "10.1/a"),), abstract="a-abs"), source="crossref")
    assert _papers(repo)[0]["abstract"] == "a-abs"


def test_field_tie_mark_cleared_when_higher_priority_source_takes_over(
    env: tuple[Repo, MergeEngine, Path],
) -> None:
    """更高优先源改写该字段 → 清掉旧来源留下的 tie 记号（记号只描述**当前生效来源**）。

    否则 `[openalex_a, openalex_b, dblp]` 留记号而 `[dblp, openalex_a, openalex_b]` 不留
    ——记号本身变成顺序敏感面（补强后的 property 生成器实测捕获过该形态）。
    """
    repo, engine, _ = env
    engine.ingest(_stub(title="T", ids=(("doi", "10.1/a"),), year=2001), source="openalex")
    engine.ingest(_stub(title="T", ids=(("doi", "10.1/a"),), year=2002), source="openalex")
    paper_id = _papers(repo)[0]["id"]
    assert _meta(repo, paper_id)["_field_tie"] == ["year"]

    engine.ingest(_stub(title="T", ids=(("doi", "10.1/a"),), year=2003), source="dblp")
    paper = _papers(repo)[0]
    assert paper["year"] == 2003  # dblp > openalex：跨级由优先级表裁决
    assert "_field_tie" not in _meta(repo, paper_id)


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
    """已有 identifier-conflict 边的一对 paper 再撞弱信号键 → 不降级为弱信号证据。

    用例刻意让桥接 stub 给胜者带来一个**新**键（胜者原键与之不同），否则 `_apply_weak_signal`
    在"键已存在"处早返回、强度守卫根本走不到（空转用例杀不掉守卫变异体）。胜者由 identifier
    数唯一确定（P1 两个、P2 一个），不依赖 ULID 平局。
    """
    repo, engine, _ = env
    engine.ingest(  # P1：2 个 identifier → 冲突裁决的胜者
        _stub(
            title="Alpha Study",
            ids=(("doi", "10.1/a"), ("openalex", "W1")),
            authors=("Jane Smith",),
        ),
        source="official",
    )
    engine.ingest(  # P2：异标题异姓氏 → 此刻与 P1 无弱信号
        _stub(title="Gamma Study", ids=(("arxiv", "2401.9"),), authors=("Bob Jones",)),
        source="official",
    )
    assert _relations(repo) == []

    engine.ingest(  # 桥接 stub：冲突建边，且给胜者带来 P2 的键 → 走到强度守卫
        _stub(
            title="Gamma Study",
            ids=(("doi", "10.1/a"), ("arxiv", "2401.9")),
            authors=("Bob Jones",),
        ),
        source="crossref",
    )
    winner_id = _paper_id_by_identifier(repo, "openalex", "W1")
    assert ("gamma study", "jones") in _weak_keys_of(repo, winner_id)  # 守卫确实被走到
    rels = _relations(repo)
    assert len(rels) == 1
    assert "identifier-conflict" in rels[0]["evidence_json"]  # 强证据留存、未被弱信号覆盖
    assert rels[0]["confidence"] == 0.9


def test_conflict_path_records_observation_key_for_later_weak_signal(
    env: tuple[Repo, MergeEngine, Path],
) -> None:
    """冲突并入路径也记本次观测的键：后到的同键 stub 必须被候审（删该记键调用即红）。"""
    repo, engine, _ = env
    engine.ingest(
        _stub(
            title="Alpha Study",
            ids=(("doi", "10.1/a"), ("openalex", "W1")),
            authors=("Jane Smith",),
        ),
        source="official",
    )
    engine.ingest(
        _stub(title="Beta Study", ids=(("arxiv", "2401.9"),), authors=("Bob Jones",)),
        source="official",
    )
    engine.ingest(  # 桥接 stub 携第三个键（Delta/Nguyen），并入胜者
        _stub(
            title="Delta Study",
            ids=(("doi", "10.1/a"), ("arxiv", "2401.9")),
            authors=("Carl Nguyen",),
        ),
        source="crossref",
    )
    result = engine.ingest(  # 后到的独立 work 与该键相撞
        _stub(title="Delta Study", ids=(("doi", "10.1/z"),), authors=("Ann Nguyen",)),
        source="crossref",
    )
    assert result.action == "candidate_flagged"
    winner_id = _paper_id_by_identifier(repo, "openalex", "W1")
    assert ("delta study", "nguyen") in _weak_keys_of(repo, winner_id)


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


def test_unregistered_evidence_reason_ranks_strongest() -> None:
    """未登记的 evidence reason（如 0002 迁移写的 doi 归一碰撞边）强度视为最强——直测默认分支。"""
    assert _evidence_strength("doi-normalization-collision") == float("inf")
    assert _evidence_strength(None) == float("inf")  # 读不出 reason 同样视为最强
    assert _evidence_strength("weak-signal-title-author") < _evidence_strength(
        "identifier-conflict"
    )
    assert _evidence_strength("identifier-conflict") < _evidence_strength("doi-collision-x")


@pytest.mark.parametrize(
    "stored_evidence",
    [
        None,
        '"not-an-object"',
        '{"doi_normalized": "10.1/a", "reason": "doi-normalization-collision"}',
    ],
)
def test_unreadable_existing_evidence_is_not_overwritten(
    env: tuple[Repo, MergeEngine, Path], stored_evidence: str | None
) -> None:
    """既有边证据读不出 reason / reason 未登记（如迁移的 doi 归一碰撞）→ 最强，弱信号不覆盖。"""
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


# -- preprint_of 建边（T10；design/06 §3 单一事实源，检查单 #5）-------------
#
# `MergeEngine.ingest()`（aggregator/enrich 路径）与 `upsert_paper`（pull 路径，见
# test_repo.py 对应节）共享同一个 `Repo._apply_preprint_clues` 机制——本节验证该机制经
# `MergeEngine.ingest()` 触达时行为一致。**如实注记**：今天真正携带 doi/arxiv 线索的
# adapter（arxiv/cvf/openreview）实际走的是 `upsert_paper`（pull 路径），并不经过
# `MergeEngine.ingest()`；本节的 `source=` 仅取 `SOURCE_PRIORITY` 的合法值作 provenance
# 标签，不代表现实中存在"arxiv adapter 经 MergeEngine.ingest 接入"的数据流——纯粹验证
# 机制本身在这条写路径上同样可达（任务报告 NEEDS_DECISION 已如实记录该接线决策）。


def _preprint_edges(repo: Repo) -> list[object]:
    return [r for r in _relations(repo) if r["kind"] == "preprint_of"]


def test_ingest_doi_clue_builds_preprint_of_edge_via_merge_engine(
    env: tuple[Repo, MergeEngine, Path],
) -> None:
    """arxiv 先例：meta['doi'] 回填命中既有 identifier → 建边，自身=from（预印本）。"""
    repo, engine, _ = env
    engine.ingest(_stub(title="Published", ids=(("doi", "10.1/pub"),)), source="crossref")
    result = engine.ingest(
        _stub(title="Preprint", ids=(("arxiv", "2401.5"),), meta=(("doi", "10.1/pub"),)),
        source="official",
    )
    edges = _preprint_edges(repo)
    assert len(edges) == 1
    preprint_id = _paper_id_by_identifier(repo, "arxiv", "2401.5")
    published_id = _paper_id_by_identifier(repo, "doi", "10.1/pub")
    assert edges[0]["from_paper"] == preprint_id
    assert edges[0]["to_paper"] == published_id
    assert result.action == "created"  # 冻结口径不变：preprint_of 只是 DB 副作用


def test_ingest_arxiv_clue_builds_reverse_direction_edge(
    env: tuple[Repo, MergeEngine, Path],
) -> None:
    """cvf/openreview 先例：meta['arxiv'] 线索命中 → from=目标（预印本），自身=to（发表版）。"""
    repo, engine, _ = env
    engine.ingest(_stub(title="Preprint", ids=(("arxiv", "2401.06001"),)), source="official")
    engine.ingest(
        _stub(title="Published", ids=(("cvf", "cvpr2024/x"),), meta=(("arxiv", "2401.06001"),)),
        source="official",
    )
    edges = _preprint_edges(repo)
    assert len(edges) == 1
    preprint_id = _paper_id_by_identifier(repo, "arxiv", "2401.06001")
    published_id = _paper_id_by_identifier(repo, "cvf", "cvpr2024/x")
    assert edges[0]["from_paper"] == preprint_id
    assert edges[0]["to_paper"] == published_id


def test_ingest_dangling_doi_clue_skipped_no_edge(
    env: tuple[Repo, MergeEngine, Path], caplog: pytest.LogCaptureFixture
) -> None:
    """查不到目标端＝线索悬空：DEBUG 记录后跳过，不建悬空边（controller 裁决③）。"""
    repo, engine, _ = env
    with caplog.at_level(logging.DEBUG, logger="paper_crawler"):
        engine.ingest(
            _stub(title="Preprint", ids=(("arxiv", "2401.7"),), meta=(("doi", "10.1/missing"),)),
            source="official",
        )
    assert _preprint_edges(repo) == []
    assert any("dangling" in r.getMessage() for r in caplog.records)


def test_ingest_preprint_clue_evidence_refreshes_on_change(
    env: tuple[Repo, MergeEngine, Path],
) -> None:
    """未裁决边 + 线索值变化（journal_ref 更新）→ 刷新证据（同构 `_upsert_candidate` 刷新规则，
    本 kind 线索强度对等、无需强度序，仅"未裁决+证据有变化"即刷新）。"""
    repo, engine, _ = env
    engine.ingest(_stub(title="Published", ids=(("doi", "10.1/pub2"),)), source="crossref")
    engine.ingest(
        _stub(
            title="Preprint",
            ids=(("arxiv", "2401.8"),),
            meta=(("doi", "10.1/pub2"), ("journal_ref", "v1 draft note")),
        ),
        source="official",
    )
    before = _preprint_edges(repo)[0]["evidence_json"]
    assert "v1 draft note" in before

    engine.ingest(
        _stub(
            title="Preprint",
            ids=(("arxiv", "2401.8"),),
            meta=(("doi", "10.1/pub2"), ("journal_ref", "v2 final ref")),
        ),
        source="official",
    )
    after = _preprint_edges(repo)[0]["evidence_json"]
    assert "v2 final ref" in after
    assert "v1 draft note" not in after


def test_ingest_decided_preprint_edge_is_never_rewritten(
    env: tuple[Repo, MergeEngine, Path],
) -> None:
    """已人工裁决（decided 非空）的 preprint_of 边不被后续观测刷新——绝不覆盖人工结论
    （controller 裁决⑤：decided=NULL 是"有效待复核"而非"待审阻塞"，但已裁决行仍受保护）。"""
    repo, engine, _ = env
    engine.ingest(_stub(title="Published", ids=(("doi", "10.1/pub3"),)), source="crossref")
    engine.ingest(
        _stub(
            title="Preprint",
            ids=(("arxiv", "2401.9"),),
            meta=(("doi", "10.1/pub3"), ("journal_ref", "v1")),
        ),
        source="official",
    )
    repo.db.execute("UPDATE paper_relation SET decided = 'merged' WHERE kind = 'preprint_of'")
    before = _preprint_edges(repo)[0]["evidence_json"]

    engine.ingest(
        _stub(
            title="Preprint",
            ids=(("arxiv", "2401.9"),),
            meta=(("doi", "10.1/pub3"), ("journal_ref", "v2")),
        ),
        source="official",
    )
    edges = _preprint_edges(repo)
    assert len(edges) == 1
    assert edges[0]["decided"] == "merged"
    assert edges[0]["evidence_json"] == before


def test_ingest_preprint_clue_idempotent_reingest(env: tuple[Repo, MergeEngine, Path]) -> None:
    """同一线索重复观测 → 边只一行（幂等）。"""
    repo, engine, _ = env
    engine.ingest(_stub(title="Published", ids=(("doi", "10.1/pub4"),)), source="crossref")
    stub = _stub(title="Preprint", ids=(("arxiv", "2401.10"),), meta=(("doi", "10.1/pub4"),))
    engine.ingest(stub, source="official")
    engine.ingest(stub, source="official")
    assert len(_preprint_edges(repo)) == 1


def test_ingest_conflicting_doi_and_arxiv_clues_same_target_keeps_doi_direction(
    env: tuple[Repo, MergeEngine, Path],
) -> None:
    """独立审查 P1-1：`MergeEngine.ingest()` 路径同一场景（同调用内 doi/arxiv 两线索解析到
    同一 target）——doi 优先、arxiv 侧跳过，不建反向边（见 test_repo.py 同名场景的 pull
    路径对应用例）。"""
    repo, engine, _ = env
    engine.ingest(
        _stub(title="Aggregated Target", ids=(("doi", "10.1/conflict"), ("arxiv", "2401.06013"))),
        source="official",
    )
    engine.ingest(
        _stub(
            title="Self",
            ids=(("cvf", "cvpr2024/conflict"),),
            meta=(("doi", "10.1/conflict"), ("arxiv", "2401.06013")),
        ),
        source="official",
    )
    edges = _preprint_edges(repo)
    assert len(edges) == 1
    self_id = _paper_id_by_identifier(repo, "cvf", "cvpr2024/conflict")
    target_id = _paper_id_by_identifier(repo, "doi", "10.1/conflict")
    assert edges[0]["from_paper"] == self_id
    assert edges[0]["to_paper"] == target_id
    assert json.loads(edges[0]["evidence_json"])["clue_key"] == "doi"


def test_ingest_preprint_clue_evidence_includes_source(
    env: tuple[Repo, MergeEngine, Path],
) -> None:
    """独立审查 P1-2：evidence_json 记 source（`MergeEngine.ingest` 的 `incoming.source`）
    ——controller 裁决③（openreview doi 语义存疑靠 evidence 溯源核实）的前提。"""
    repo, engine, _ = env
    engine.ingest(_stub(title="Published", ids=(("doi", "10.1/pub6"),)), source="crossref")
    engine.ingest(
        _stub(title="Preprint", ids=(("arxiv", "2401.12"),), meta=(("doi", "10.1/pub6"),)),
        source="official",
    )
    evidence = json.loads(_preprint_edges(repo)[0]["evidence_json"])
    assert evidence["source"] == "official"
    assert "venue_id" not in evidence  # aggregator 路径 venue-agnostic（paper.venue_id=NULL）


def test_ingest_arxiv_clue_normalizes_versioned_form(
    env: tuple[Repo, MergeEngine, Path],
) -> None:
    """独立审查 P1-3：`MergeEngine.ingest()` 路径同样需要版本号归一（与 test_repo.py 的
    参数化用例同构，机制在 repo.py 共享，此处单点验证不重复穷举各形态）。"""
    repo, engine, _ = env
    engine.ingest(_stub(title="Preprint", ids=(("arxiv", "2401.06014"),)), source="official")
    engine.ingest(
        _stub(title="Published", ids=(("cvf", "cvpr2024/y"),), meta=(("arxiv", "2401.06014v2"),)),
        source="official",
    )
    assert len(_preprint_edges(repo)) == 1


def test_ingest_preprint_clue_does_not_merge_papers(
    env: tuple[Repo, MergeEngine, Path],
) -> None:
    """preprint_of 是纯 DB 副作用：不改变 `IngestResult.action`、两 paper 各自保留（design/06
    §3 明文：双条 paper 双份全文、preprint_of 是关联边不是去重合并）。"""
    repo, engine, _ = env
    engine.ingest(_stub(title="Published", ids=(("doi", "10.1/pub5"),)), source="crossref")
    result = engine.ingest(
        _stub(title="Preprint", ids=(("arxiv", "2401.11"),), meta=(("doi", "10.1/pub5"),)),
        source="official",
    )
    assert result.action == "created"
    assert len(_papers(repo)) == 2  # 两条 paper 都保留，未被合并成一条
    # 独立审查 P2-3：补边存在性断言——否则"正确建边未合并"与"啥也没建"两种变异体
    # 在本测试下不可分（前两条断言单独成立于两者）。
    assert len(_preprint_edges(repo)) == 1


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
