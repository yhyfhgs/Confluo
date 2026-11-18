from confluo_scout.abstracts import AbstractStore
from confluo_scout.db import Database
from confluo_scout.records import PaperRecord, ReviewRecord
from confluo_scout.store import Store, quality_score, review_stats


def make_store(tmp_path):
    db = Database(tmp_path / "t.sqlite")
    with db.tx() as con:
        con.execute("insert into series(id, short, name) values('icml','ICML','ICML')")
        con.execute("insert into edition(id, series_id, year, label, enabled) values('icml-2025','icml',2025,'ICML 2025',1)")
    return db, Store(db, AbstractStore(tmp_path / "abs", part_size=2))


def test_abstract_generations(tmp_path):
    st = AbstractStore(tmp_path / "abs", part_size=2)
    gen, ptr = st.write_generation("e-1", [(1, "e/a", "alpha"), (2, "e/b", "beta"), (3, "e/c", "gamma")])
    st.commit_generation("e-1", gen)
    assert st.read("e-1", gen, *ptr[3]) == "gamma"
    assert st.verify("e-1")[0]
    gen2, ptr2 = st.write_generation("e-1", [(1, "e/a", "alpha 2")])
    st.commit_generation("e-1", gen2)
    assert st.generations("e-1") == [gen2] and st.read("e-1", gen2, *ptr2[1]) == "alpha 2"


def test_merge_sources_and_labels(tmp_path):
    db, store = make_store(tmp_path)
    orv = PaperRecord(source="openreview", source_key="F1", title="Deep Nets Are Calibrated", authors=["A. B"],
                      abstract="We study calibration of deep networks.", status="accepted", decision_label="Poster", tier=2,
                      forum_url="https://openreview.net/forum?id=F1", pdf_url="https://openreview.net/pdf?id=F1",
                      reviews=[ReviewRecord("r1", 6.0, "6", 4.0), ReviewRecord("r2", 8.0, "8", 3.0)])
    pmlr = PaperRecord(source="pmlr", source_key="v267-x", title="Deep nets are calibrated!", authors=["A. B"],
                       abstract="We study calibration of deep networks in depth, with proofs.",
                       proceedings_url="https://proceedings.mlr.press/v267/x.html", pdf_url="https://pmlr/x.pdf")
    with db.tx() as con:
        store.upsert_records(con, "icml-2025", [orv])
        store.upsert_records(con, "icml-2025", [pmlr])
        out = store.upsert_records(con, "icml-2025", [PaperRecord(source="cvf_accepted", source_key="t",
                                                                   title="Deep Nets Are Calibrated", decision_label="Oral",
                                                                   tier=4, label_only=True)])
    assert out == {"label_applied": 1}
    rows = db.query("select * from paper")
    assert len(rows) == 1
    p = rows[0]
    assert p["forum_url"].endswith("F1") and p["proceedings_url"].startswith("https://proceedings")
    assert p["pdf_url"] == "https://pmlr/x.pdf"  # proceedings PDF preferred
    assert p["decision_label"] == "Oral" and p["tier"] == 4  # strongest label wins
    assert "proofs" in store.abstract_of(p)  # longer abstract kept
    assert db.query("select rowid from paper_fts where paper_fts match 'calibrated'")
    stats = store.refresh_edition_stats("icml-2025", 1.0)
    assert stats["reviews"] == 2
    store.compact_edition("icml-2025")
    p = db.one("select * from paper")
    assert p["abstract_gen"] == 1 and "proofs" in store.abstract_of(p)
    assert db.scalar("select count(*) from abstract_pending") == 0


def test_review_stats_and_quality():
    s = review_stats([(8.0, 4.0), (6.0, 3.0)], mean=5.0, std=1.5)
    assert s["n"] == 2 and 0.5 < s["R"] < 1.0
    hi = quality_score(s["R"], 4, "accepted", 1.0)
    lo = quality_score(0.2, 2, "accepted", 0.5)
    assert hi > lo
    assert quality_score(None, None, "under_review", 1.0) == 1.0  # only the venue term remains
