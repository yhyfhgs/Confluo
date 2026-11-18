from types import SimpleNamespace

import numpy as np

from confluo_scout.abstracts import AbstractStore
from confluo_scout.db import Database
from confluo_scout.embed import HybridEmbedder
from confluo_scout.reconcile import repair_abstract_pointers
from confluo_scout.records import PaperRecord
from confluo_scout.services import restore_if_missing
from confluo_scout.store import Store


def test_restore_from_newest_backup(tmp_path):
    backups = tmp_path / "db" / "backups"
    backups.mkdir(parents=True)
    old = Database(backups / "scout-20261118-0000.sqlite")
    old.set_setting("marker", "old")
    old.close()
    new = Database(backups / "scout-20261119-0000.sqlite")
    new.set_setting("marker", "new")
    new.close()
    import os

    os.utime(backups / "scout-20261118-0000.sqlite", (1, 1))
    live = tmp_path / "volume" / "scout.sqlite"
    settings = SimpleNamespace(db_path=live, backups_dir=backups)
    assert restore_if_missing(settings) == "scout-20261119-0000.sqlite"
    assert Database(live).get_setting("marker") == "new"
    assert restore_if_missing(settings) is None  # present now: untouched


def test_hybrid_embedder_falls_back(tmp_path):
    settings = SimpleNamespace(embed_url="http://127.0.0.1:9", model_dir=tmp_path, device="cpu", torch_threads=1)
    h = HybridEmbedder(settings, purpose="interactive")
    fake = SimpleNamespace(queries=lambda texts: np.ones((len(texts), 768), dtype=np.float32), device="cpu")
    h._local = fake
    out = h.queries(["a", "b"])
    assert out.shape == (2, 768)
    assert h._remote_down_until > 0  # the dead accelerator is skipped for a minute


def test_repair_abstract_pointers(tmp_path):
    db = Database(tmp_path / "t.sqlite")
    with db.tx() as con:
        con.execute("insert into series(id, short, name) values('s','S','S')")
        con.execute("insert into edition(id, series_id, year, label) values('s-1','s',2026,'S 2026')")
    store = Store(db, AbstractStore(tmp_path / "abs", part_size=2))
    with db.tx() as con:
        store.upsert_records(con, "s-1", [PaperRecord(source="x", source_key=str(i), title=f"Paper {i}",
                                                      abstract=f"abstract number {i}") for i in range(5)])
    store.compact_edition("s-1")
    with db.tx() as con:  # simulate pointers from an older generation (database restored from a backup)
        con.execute("update paper set abstract_gen=99, abstract_part=0, abstract_line=0")
    svc = SimpleNamespace(db=db, abstracts=store.abstracts, settings=SimpleNamespace(abstracts_dir=tmp_path / "abs"))
    res = repair_abstract_pointers(svc)
    assert res == {"repointed": 5, "unresolved": 0}
    row = db.one("select * from paper where title='Paper 3'")
    assert store.abstract_of(row) == "abstract number 3"
