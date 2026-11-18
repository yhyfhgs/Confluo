"""Background indexing: embed papers whose content changed and keep vector payloads fresh."""

from __future__ import annotations

import logging
import threading
import time

from confluo_scout.areas import classifier
from confluo_scout.db import loads
from confluo_scout.embed import document_text

log = logging.getLogger("scout.indexer")


class Indexer:
    def __init__(self, svc):
        self.svc = svc
        self.stop = threading.Event()
        self.progress = {"embedded": 0, "pending": 0, "rate": 0.0, "running": False, "last_error": None}

    def pending_count(self) -> int:
        return int(self.svc.db.scalar(
            "select count(*) from paper where embed_hash is null or embed_hash != content_hash") or 0)

    def embed_pending(self, limit: int = 0, batch: int = 64, embedder=None, yield_to=None) -> int:
        """Embed stale papers, newest editions first. Returns the number embedded."""
        db, store = self.svc.db, self.svc.store
        embedder = embedder or self.svc.embedder
        done = 0
        self.progress.update(running=True, pending=self.pending_count())
        t0 = time.time()
        try:
            while not self.stop.is_set():
                while yield_to is not None and yield_to.is_set() and not self.stop.is_set():
                    time.sleep(0.5)
                rows = db.query(
                    "select p.id, p.uid, p.edition_id, p.title, p.keywords, p.area_native, p.status, p.tier, "
                    "p.content_hash, p.abstract_gen, p.abstract_part, p.abstract_line, e.series_id, e.year "
                    "from paper p join edition e on e.id = p.edition_id "
                    "where p.embed_hash is null or p.embed_hash != p.content_hash "
                    "order by e.enabled desc, e.year desc, p.id limit ?", (batch,))
                if not rows:
                    break
                texts_by_id = store.abstracts_for(rows)
                docs = [document_text(r["title"], texts_by_id.get(r["id"]), loads(r["keywords"], []) or [],
                                      r["area_native"]) for r in rows]
                vecs = embedder.documents(docs)
                areas = classifier(embedder).classify(vecs)
                payloads = [{"edition": r["edition_id"], "series": r["series_id"], "year": r["year"],
                             "status": r["status"], "tier": r["tier"] or 0} for r in rows]
                self.svc.vectors.upsert_papers([r["id"] for r in rows], vecs, payloads)
                with db.tx() as con:
                    con.executemany("update paper set embed_hash=?, area_unified=? where id=?",
                                    [(r["content_hash"], a, r["id"]) for r, (a, _s) in zip(rows, areas, strict=True)])
                done += len(rows)
                elapsed = max(1e-6, time.time() - t0)
                self.progress.update(embedded=self.progress["embedded"] + len(rows), rate=round(done / elapsed, 1),
                                     pending=max(0, self.progress["pending"] - len(rows)))
                if limit and done >= limit:
                    break
            for eid in {r[0] for r in db.query("select id from edition where enabled=1 or paper_count>0")}:
                self.svc.store.refresh_counts(eid)
        except Exception as exc:
            self.progress["last_error"] = str(exc)
            log.error("embedding failed: %s", exc)
            raise
        finally:
            self.progress["running"] = False
        if done:
            log.info("embedded %d papers (%.1f/s)", done, done / max(1e-6, time.time() - t0))
        return done

    def refresh_payloads(self, edition_id: str) -> None:
        """After a crawl: status and tier can change without a content change."""
        rows = self.svc.db.query(
            "select p.id, p.edition_id, p.status, p.tier, e.series_id, e.year from paper p "
            "join edition e on e.id=p.edition_id where p.edition_id=? and p.embed_hash is not null", (edition_id,))
        items = [(r["id"], {"edition": r["edition_id"], "series": r["series_id"], "year": r["year"],
                            "status": r["status"], "tier": r["tier"] or 0}) for r in rows]
        if items:
            self.svc.vectors.set_payloads(items)
