"""dedupe 审核语义与 `same_as(decided='merged')` 查询层聚合（T13；AC-7.3）。

覆盖三层：
1. **候审列表**（`Repo.list_candidates`）：只认 `candidate_duplicate`（kind 隔离——
   `preprint_of` 边有独立的 `decided` 语义，绝不进本流程）、state 过滤、确定性排序、
   逐条证据载荷（两 paper 标题/venue/year/identifier/asset 数 + reason + 原始 evidence）。
2. **裁决**（`decide_candidate`/`revert_candidate`）：merge → 候审行置 `merged` +
   落 `same_as(decided='merged')`；reject → 置 `rejected` 且无聚合；两者幂等、可改判、
   **物理零删行**、可回滚（回滚后 paper/identifier/asset 三表逐字节还原）。
3. **聚合**（`merged_groups`/`merged_view`/`fold_merged`/`list_papers(aggregate=True)`）：
   传递闭包成类、主行选择确定、结果集内折叠（**永不让一篇著作整体消失**）、
   `aggregate` 默认关（pull 级联 `runner._select_papers` 零回归）。
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from paper_crawler.errors import CrawlerError, ErrorClass
from paper_crawler.merge import MergeEngine
from paper_crawler.storage.db import Database
from paper_crawler.storage.repo import Repo
from paper_crawler.types import AssetKind, AssetPlan, AuthLevel, IssueRef, PaperStub, VenueSpec

VENUE_ID = "mock_journal"


@pytest.fixture
def repo(tmp_path: Path, venue: VenueSpec) -> Iterator[Repo]:
    database = Database(tmp_path / "dedupe.sqlite")
    database.migrate()
    r = Repo(database)
    r.upsert_venue(venue)
    yield r
    database.close()


def _paper(repo: Repo, *, doi: str, title: str, year: int | None = 2024) -> str:
    return repo.upsert_paper(
        VENUE_ID, None, PaperStub(title=title, identifiers=(("doi", doi),), year=year)
    )


def _candidate(
    repo: Repo,
    paper_a: str,
    paper_b: str,
    *,
    confidence: float = 0.5,
    reason: str = "weak-signal-title-author",
    decided: str | None = None,
    kind: str = "candidate_duplicate",
) -> None:
    """直插一条关系边（模拟 ingest 侧 `_upsert_candidate` 的产物；端点顺序原样保留，
    以便同时锁定"消费方按无序对处理、不依赖 from/to 字面顺序"）。"""
    repo.db.execute(
        "INSERT INTO paper_relation "
        "(from_paper, to_paper, kind, confidence, evidence_json, decided) VALUES (?,?,?,?,?,?)",
        (
            paper_a,
            paper_b,
            kind,
            confidence,
            json.dumps({"reason": reason}, sort_keys=True),
            decided,
        ),
    )


def _same_as_rows(repo: Repo) -> list[sqlite3.Row]:
    return repo.db.query("SELECT * FROM paper_relation WHERE kind = 'same_as' ORDER BY from_paper")


def _candidate_row(repo: Repo) -> sqlite3.Row:
    rows = repo.db.query("SELECT * FROM paper_relation WHERE kind = 'candidate_duplicate'")
    assert len(rows) == 1
    return rows[0]


def _entity_dump(repo: Repo) -> list[tuple[object, ...]]:
    """paper / identifier / asset 三表的确定性快照——"物理不删行 + 可回滚"的证据面。"""
    dump: list[tuple[object, ...]] = []
    for table, order in (
        ("paper", "id"),
        ("identifier", "scheme, value"),
        ("asset", "id"),
    ):
        for row in repo.db.query(f"SELECT * FROM {table} ORDER BY {order}"):
            dump.append((table, *tuple(row)))
    return dump


# ---------------------------------------------------------------------------
# 1. 候审列表
# ---------------------------------------------------------------------------


def test_list_candidates_returns_pending_pairs_with_both_briefs(repo: Repo) -> None:
    """逐条展示证据：两侧 paper 的标题/venue/year/identifier/asset 数 + reason + 原始证据。"""
    a = _paper(repo, doi="10.9999/a", title="Deep Learning for Finance", year=2023)
    b = _paper(repo, doi="10.9999/b", title="Deep learning for finance", year=2024)
    repo.plan_asset(a, AssetPlan(kind=AssetKind.PDF, url="u", auth_needed=AuthLevel.NONE), "mock")
    _candidate(repo, b, a, confidence=0.5)

    candidates = repo.list_candidates()

    assert len(candidates) == 1
    cand = candidates[0]
    # 无序对归一：paper_a 恒为字典序小者，不随插入时的 from/to 摆动。
    assert (cand.paper_a.paper_id, cand.paper_b.paper_id) == tuple(sorted((a, b)))
    briefs = {brief.paper_id: brief for brief in (cand.paper_a, cand.paper_b)}
    assert briefs[a].title == "Deep Learning for Finance"
    assert briefs[a].year == 2023
    assert briefs[a].venue_id == VENUE_ID
    assert briefs[a].identifiers == ("doi:10.9999/a",)
    assert briefs[a].asset_count == 1
    assert briefs[b].asset_count == 0
    assert cand.reason == "weak-signal-title-author"
    assert cand.confidence == 0.5
    assert cand.decided is None
    assert cand.evidence == {"reason": "weak-signal-title-author"}


def test_list_candidates_excludes_preprint_of_edges(repo: Repo) -> None:
    """kind 隔离：`preprint_of` 的 `decided=NULL` 是"有效待可选复核"，不是待审阻塞
    （merge.py 裁决 7），绝不进 dedupe review 流程。"""
    a = _paper(repo, doi="10.9999/pre", title="Preprint")
    b = _paper(repo, doi="10.9999/pub", title="Published")
    _candidate(repo, a, b, kind="preprint_of", confidence=1.0, reason="meta-clue:doi")

    assert repo.list_candidates(state="all") == []


def test_list_candidates_orders_by_confidence_then_ids(repo: Repo) -> None:
    """确定性排序：强证据在前，同强度按无序对（小 id, 大 id）字典序——同一库态恒同序。"""
    a = _paper(repo, doi="10.9999/o1", title="One")
    b = _paper(repo, doi="10.9999/o2", title="Two")
    c = _paper(repo, doi="10.9999/o3", title="Three")
    _candidate(repo, a, b, confidence=0.5)
    _candidate(repo, b, c, confidence=0.99, reason="identifier-conflict")
    _candidate(repo, a, c, confidence=0.5)

    pairs = [(cand.paper_a.paper_id, cand.paper_b.paper_id) for cand in repo.list_candidates()]

    assert pairs[0] == tuple(sorted((b, c)))  # confidence 0.99 最强
    assert pairs[1:] == sorted([tuple(sorted((a, b))), tuple(sorted((a, c)))])


def test_list_candidates_state_filter_and_limit(repo: Repo) -> None:
    """reject/merge 后不再出现在待审列表，但可按 state 查历史；`limit` 截断。"""
    a = _paper(repo, doi="10.9999/s1", title="One")
    b = _paper(repo, doi="10.9999/s2", title="Two")
    c = _paper(repo, doi="10.9999/s3", title="Three")
    _candidate(repo, a, b, confidence=0.9, decided="rejected")
    _candidate(repo, a, c, confidence=0.8, decided="merged")
    _candidate(repo, b, c, confidence=0.7)

    assert [cand.decided for cand in repo.list_candidates()] == [None]
    assert [cand.decided for cand in repo.list_candidates(state="rejected")] == ["rejected"]
    assert [cand.decided for cand in repo.list_candidates(state="merged")] == ["merged"]
    assert len(repo.list_candidates(state="all")) == 3
    assert len(repo.list_candidates(state="all", limit=2)) == 2
    # `count_candidates` 与列表同口径（CLI 据它判断是否被 --limit 截断）。
    assert (repo.count_candidates(), repo.count_candidates(state="all")) == (1, 3)


def test_list_candidates_unknown_state_raises_config_error(repo: Repo) -> None:
    with pytest.raises(CrawlerError) as excinfo:
        repo.list_candidates(state="nonsense")
    assert excinfo.value.error_class is ErrorClass.CONFIG


def test_list_candidates_tolerates_unparseable_evidence(repo: Repo) -> None:
    """人工手改/未来标签写坏 evidence_json → 降级为空证据，不炸列表（审核工具是只读诊断面）。"""
    a = _paper(repo, doi="10.9999/e1", title="One")
    b = _paper(repo, doi="10.9999/e2", title="Two")
    _candidate(repo, a, b)
    repo.db.execute("UPDATE paper_relation SET evidence_json = ?", ("{not json",))

    cand = repo.list_candidates()[0]
    assert cand.evidence == {}
    assert cand.reason is None


def test_list_candidates_consumes_real_weak_signal_edge(repo: Repo) -> None:
    """端到端：真实 ingest（弱信号候审）产出的边可被审核工具原样消费。"""
    engine = MergeEngine(repo)
    engine.ingest(
        PaperStub(
            title="Order Flow and Prices", identifiers=(("doi", "10.1/x"),), authors=("Jane Smith",)
        ),
        source="crossref",
    )
    engine.ingest(
        PaperStub(
            title="Order flow and prices",
            identifiers=(("arxiv", "2401.00001"),),
            authors=("Jane Smith",),
        ),
        source="s2",
    )

    candidates = repo.list_candidates()
    assert len(candidates) == 1
    assert candidates[0].reason == "weak-signal-title-author"
    assert candidates[0].evidence["keys"] == [["order flow and prices", "smith"]]


# ---------------------------------------------------------------------------
# 2. 裁决：merge / reject / revert
# ---------------------------------------------------------------------------


def test_decide_merge_sets_decided_and_writes_same_as_without_deleting_rows(repo: Repo) -> None:
    """merge = 候审行置 merged + 新增 `same_as(decided='merged')`；两 paper 行原样保留。"""
    a = _paper(repo, doi="10.9999/m1", title="One")
    b = _paper(repo, doi="10.9999/m2", title="Two")
    _candidate(repo, b, a, confidence=0.99, reason="identifier-conflict")
    before = _entity_dump(repo)

    outcome = repo.decide_candidate(a, b, "merge")

    assert outcome.decided == "merged"
    assert outcome.changed is True
    assert _candidate_row(repo)["decided"] == "merged"
    same_as = _same_as_rows(repo)
    assert len(same_as) == 1
    # same_as 端点定向：字典序归一（无序语义 + 主键唯一，不随 CLI 参数顺序摆动）。
    assert (same_as[0]["from_paper"], same_as[0]["to_paper"]) == tuple(sorted((a, b)))
    assert same_as[0]["decided"] == "merged"
    evidence = json.loads(same_as[0]["evidence_json"])
    assert evidence["reason"] == "dedupe-review-merge"
    assert evidence["candidate_reason"] == "identifier-conflict"
    assert evidence["decided_at"]
    assert _entity_dump(repo) == before  # 物理零删行、零改行


def test_decide_accepts_the_pair_in_either_argument_order(repo: Repo) -> None:
    """无序对：`decide B A` 与 `decide A B` 等价（merge.py 裁决 5）。"""
    a = _paper(repo, doi="10.9999/u1", title="One")
    b = _paper(repo, doi="10.9999/u2", title="Two")
    _candidate(repo, a, b)

    repo.decide_candidate(b, a, "merge")

    assert _candidate_row(repo)["decided"] == "merged"
    assert len(_same_as_rows(repo)) == 1


def test_decide_merge_twice_is_idempotent(repo: Repo) -> None:
    a = _paper(repo, doi="10.9999/i1", title="One")
    b = _paper(repo, doi="10.9999/i2", title="Two")
    _candidate(repo, a, b)

    first = repo.decide_candidate(a, b, "merge")
    second = repo.decide_candidate(a, b, "merge")

    assert (first.changed, second.changed) == (True, False)
    assert len(_same_as_rows(repo)) == 1
    assert len(repo.merged_groups()) == 1


def test_decide_reject_sets_rejected_and_leaves_no_aggregation(repo: Repo) -> None:
    a = _paper(repo, doi="10.9999/r1", title="One")
    b = _paper(repo, doi="10.9999/r2", title="Two")
    _candidate(repo, a, b)

    outcome = repo.decide_candidate(a, b, "reject")

    assert outcome.decided == "rejected"
    assert _candidate_row(repo)["decided"] == "rejected"
    assert _same_as_rows(repo) == []
    assert repo.merged_groups() == []
    assert repo.list_candidates() == []  # 出待审队列
    assert len(repo.list_candidates(state="rejected")) == 1  # 但可查历史


def test_reject_after_merge_demotes_the_same_as_edge(repo: Repo) -> None:
    """改判：merge 后再 reject → 聚合撤销（same_as.decided 置回 NULL），行仍在（审计痕迹）。"""
    a = _paper(repo, doi="10.9999/c1", title="One")
    b = _paper(repo, doi="10.9999/c2", title="Two")
    _candidate(repo, a, b)
    repo.decide_candidate(a, b, "merge")

    repo.decide_candidate(a, b, "reject")

    assert _candidate_row(repo)["decided"] == "rejected"
    rows = _same_as_rows(repo)
    assert len(rows) == 1  # 绝不删行
    assert rows[0]["decided"] is None
    assert json.loads(rows[0]["evidence_json"])["reverted_at"]
    assert repo.merged_groups() == []


def test_decide_unknown_decision_raises(repo: Repo) -> None:
    a = _paper(repo, doi="10.9999/d1", title="One")
    b = _paper(repo, doi="10.9999/d2", title="Two")
    _candidate(repo, a, b)

    with pytest.raises(CrawlerError) as excinfo:
        repo.decide_candidate(a, b, "delete")
    assert excinfo.value.error_class is ErrorClass.CONFIG


def test_decide_unknown_paper_id_raises(repo: Repo) -> None:
    a = _paper(repo, doi="10.9999/k1", title="One")

    with pytest.raises(CrawlerError) as excinfo:
        repo.decide_candidate(a, "01NOSUCHPAPER", "merge")
    assert "01NOSUCHPAPER" in str(excinfo.value)


def test_decide_without_candidate_edge_raises(repo: Repo) -> None:
    """两 paper 之间只有 preprint_of（或无边）→ 响亮拒绝，绝不凭空造 same_as。"""
    a = _paper(repo, doi="10.9999/n1", title="One")
    b = _paper(repo, doi="10.9999/n2", title="Two")
    _candidate(repo, a, b, kind="preprint_of", reason="meta-clue:doi")

    with pytest.raises(CrawlerError) as excinfo:
        repo.decide_candidate(a, b, "merge")
    assert excinfo.value.error_class is ErrorClass.CONFIG
    assert _same_as_rows(repo) == []


def test_decide_same_paper_twice_raises(repo: Repo) -> None:
    a = _paper(repo, doi="10.9999/self", title="One")

    with pytest.raises(CrawlerError):
        repo.decide_candidate(a, a, "merge")


def test_revert_restores_pending_state_and_undoes_aggregation(repo: Repo) -> None:
    """AC-7.3 可回滚：回滚后待审队列/聚合视图/实体三表全部还原到裁决前。"""
    a = _paper(repo, doi="10.9999/v1", title="One")
    b = _paper(repo, doi="10.9999/v2", title="Two")
    repo.plan_asset(a, AssetPlan(kind=AssetKind.PDF, url="u", auth_needed=AuthLevel.NONE), "mock")
    _candidate(repo, a, b)
    before_entities = _entity_dump(repo)
    before_pending = [c.paper_a.paper_id for c in repo.list_candidates()]

    repo.decide_candidate(a, b, "merge")
    assert len(repo.merged_groups()) == 1
    outcome = repo.revert_candidate(a, b)

    assert (outcome.decided, outcome.changed) == (None, True)
    assert _candidate_row(repo)["decided"] is None
    assert repo.merged_groups() == []
    assert [c.paper_a.paper_id for c in repo.list_candidates()] == before_pending
    assert _entity_dump(repo) == before_entities
    assert len(_same_as_rows(repo)) == 1  # 关系行留痕，不物理删


def test_revert_then_merge_again_reuses_the_same_row(repo: Repo) -> None:
    a = _paper(repo, doi="10.9999/w1", title="One")
    b = _paper(repo, doi="10.9999/w2", title="Two")
    _candidate(repo, a, b)
    repo.decide_candidate(a, b, "merge")
    repo.revert_candidate(a, b)

    repo.decide_candidate(a, b, "merge")

    rows = _same_as_rows(repo)
    assert len(rows) == 1
    assert rows[0]["decided"] == "merged"
    assert "reverted_at" not in json.loads(rows[0]["evidence_json"])
    assert len(repo.merged_groups()) == 1


def test_revert_on_undecided_pair_is_a_noop(repo: Repo) -> None:
    a = _paper(repo, doi="10.9999/q1", title="One")
    b = _paper(repo, doi="10.9999/q2", title="Two")
    _candidate(repo, a, b)

    outcome = repo.revert_candidate(a, b)

    assert (outcome.decided, outcome.changed) == (None, False)


def test_revert_unknown_pair_raises(repo: Repo) -> None:
    a = _paper(repo, doi="10.9999/z1", title="One")
    b = _paper(repo, doi="10.9999/z2", title="Two")

    with pytest.raises(CrawlerError):
        repo.revert_candidate(a, b)


# ---------------------------------------------------------------------------
# 3. 聚合语义
# ---------------------------------------------------------------------------


def _merge_pair(repo: Repo, a: str, b: str) -> None:
    _candidate(repo, a, b)
    repo.decide_candidate(a, b, "merge")


def test_merged_groups_take_transitive_closure(repo: Repo) -> None:
    """A~B、B~C 两次独立裁决 → 一个三元类（否则聚合视图会同时显示 A 与 C，自相矛盾）。"""
    a = _paper(repo, doi="10.9999/t1", title="One")
    b = _paper(repo, doi="10.9999/t2", title="Two")
    c = _paper(repo, doi="10.9999/t3", title="Three")
    _merge_pair(repo, a, b)
    _merge_pair(repo, b, c)

    groups = repo.merged_groups()

    assert len(groups) == 1
    assert groups[0].members == tuple(sorted((a, b, c)))
    assert repo.merged_group(a) == groups[0]
    assert repo.merged_group(_paper(repo, doi="10.9999/t4", title="Lonely")) is None

    # 冗余边：人再把 A~C 也裁决为 merge（类内第三条边）→ 仍是同一个三元类，幂等。
    _merge_pair(repo, a, c)
    assert repo.merged_groups() == groups


def test_canonical_is_the_richest_row_then_smallest_id(repo: Repo) -> None:
    """主行 = identifier 最多者，平局取 paper_id 字典序最小者（同 merge.py 裁决 3 的胜者
    规则）——是当前库态的函数，不看边方向、不看裁决顺序。"""
    a = _paper(repo, doi="10.9999/g1", title="Sparse")
    b = _paper(repo, doi="10.9999/g2", title="Rich")
    repo.upsert_paper(
        VENUE_ID,
        None,
        PaperStub(title="Rich", identifiers=(("doi", "10.9999/g2"), ("arxiv", "2402.00002"))),
    )
    _merge_pair(repo, a, b)

    assert repo.merged_groups()[0].canonical == b

    # 平局（各 1 个 identifier）→ 字典序最小 id 胜。
    c = _paper(repo, doi="10.9999/g3", title="Tie A")
    d = _paper(repo, doi="10.9999/g4", title="Tie B")
    _merge_pair(repo, c, d)
    tie_group = next(g for g in repo.merged_groups() if c in g.members)
    assert tie_group.canonical == min(c, d)


def test_only_merged_same_as_edges_aggregate(repo: Repo) -> None:
    """kind/decided 双重隔离：candidate_duplicate(decided='merged') 本身**不**聚合
    （聚合的唯一载体是 same_as），preprint_of 与 same_as(NULL) 同样不聚合。"""
    a = _paper(repo, doi="10.9999/y1", title="One")
    b = _paper(repo, doi="10.9999/y2", title="Two")
    c = _paper(repo, doi="10.9999/y3", title="Three")
    _candidate(repo, a, b, decided="merged")  # 只有候审行被置 merged，无 same_as
    _candidate(repo, a, c, kind="preprint_of", reason="meta-clue:doi")
    _candidate(repo, b, c, kind="same_as", reason="manual", decided=None)

    assert repo.merged_groups() == []


def test_merged_view_unions_identifiers_and_assets(repo: Repo) -> None:
    """归并视图 = 类内并集（identifier 去重升序、asset 全保留）；字段不跨行收敛。"""
    a = _paper(repo, doi="10.9999/vw1", title="Canonical Side")
    b = _paper(repo, doi="10.9999/vw2", title="Folded Side")
    repo.upsert_paper(
        VENUE_ID,
        None,
        PaperStub(title="Canonical Side", identifiers=(("doi", "10.9999/vw1"), ("s2", "s2-1"))),
    )
    repo.plan_asset(a, AssetPlan(kind=AssetKind.PDF, url="u1", auth_needed=AuthLevel.NONE), "mock")
    repo.plan_asset(b, AssetPlan(kind=AssetKind.PDF, url="u2", auth_needed=AuthLevel.NONE), "mock")
    _merge_pair(repo, a, b)

    view = repo.merged_view(b)

    assert view is not None
    assert view.canonical.paper_id == a  # identifier 更多者
    assert tuple(m.paper_id for m in view.members) == tuple(sorted((a, b)))
    assert view.identifiers == ("doi:10.9999/vw1", "doi:10.9999/vw2", "s2:s2-1")
    assert view.asset_count == 2
    assert repo.merged_views() == [view]
    assert repo.merged_view(_paper(repo, doi="10.9999/vw3", title="Lonely")) is None


def test_fold_merged_drops_duplicate_rows_without_reordering(repo: Repo) -> None:
    """折叠 = 结果集上的纯过滤：同类只留代表（identifier 平局 → id 小者），幸存行不重排。"""
    a = _paper(repo, doi="10.9999/f1", title="AAA")
    b = _paper(repo, doi="10.9999/f2", title="BBB")
    c = _paper(repo, doi="10.9999/f3", title="CCC")
    _merge_pair(repo, a, c)

    rows = repo.list_papers(VENUE_ID)
    folded = [str(r["id"]) for r in repo.fold_merged(rows)]

    assert [str(r["title"]) for r in rows] == ["AAA", "BBB", "CCC"]
    assert folded == [pid for pid in (a, b, c) if pid in folded]  # 原序不变
    assert set(folded) == {min(a, c), b}  # 类内只剩代表行


def test_fold_merged_never_drops_a_work_when_canonical_is_absent(repo: Repo) -> None:
    """结果集内折叠（而非全局过滤）：主行不在本次结果集时，该类仍以集内成员出现——
    绝不让一篇著作从某个 issue/venue 的清单里静默消失。"""
    a = _paper(repo, doi="10.9999/h1", title="In Scope")
    # aggregator 路径建的 paper 是 venue-agnostic（venue_id=NULL），天然不在本 venue 清单内。
    b = (
        MergeEngine(repo)
        .ingest(
            PaperStub(title="Out Of Scope", identifiers=(("doi", "10.9999/h2"), ("s2", "s2-h"))),
            source="crossref",
        )
        .paper_id
    )
    _merge_pair(repo, a, b)
    assert repo.merged_groups()[0].canonical == b  # 主行（identifier 更多）不在本次结果集内

    rows = repo.list_papers(VENUE_ID, aggregate=True)

    assert [str(r["id"]) for r in rows] == [a]


def test_list_papers_aggregate_defaults_off(repo: Repo) -> None:
    """默认关：pull 级联（`runner._select_papers`）必须看到全部行，否则被折叠的一侧
    永远拿不到 resolve/fetch——聚合是显示层语义，不是数据过滤。"""
    a = _paper(repo, doi="10.9999/p1", title="AAA")
    b = _paper(repo, doi="10.9999/p2", title="BBB")
    _merge_pair(repo, a, b)

    assert len(repo.list_papers(VENUE_ID)) == 2
    assert len(repo.list_papers(VENUE_ID, aggregate=True)) == 1


def test_list_papers_aggregate_within_issue_scope(repo: Repo) -> None:
    issue_id = repo.upsert_issue(
        IssueRef(venue_id=VENUE_ID, volume="1", number="1", year=2024, label=None), source="mock"
    )
    a = repo.upsert_paper(
        VENUE_ID, issue_id, PaperStub(title="AAA", identifiers=(("doi", "10.9999/is1"),))
    )
    b = repo.upsert_paper(
        VENUE_ID, issue_id, PaperStub(title="BBB", identifiers=(("doi", "10.9999/is2"),))
    )
    _merge_pair(repo, a, b)

    rows = repo.list_papers(VENUE_ID, issue_id=issue_id, aggregate=True)

    assert [str(r["id"]) for r in rows] == [min(a, b)]


def test_fold_merged_is_identity_without_merged_edges(repo: Repo) -> None:
    a = _paper(repo, doi="10.9999/id1", title="AAA")
    b = _paper(repo, doi="10.9999/id2", title="BBB")
    _candidate(repo, a, b)  # 待审边不聚合

    rows = repo.list_papers(VENUE_ID)
    assert [str(r["id"]) for r in repo.fold_merged(rows)] == [str(r["id"]) for r in rows]
