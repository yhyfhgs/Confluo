"""Background work inside the service process: crawl queues, embedding and maintenance."""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from datetime import UTC, datetime

from confluo_scout.db import loads, utcnow

log = logging.getLogger("scout.scheduler")

FAMILIES = ("openreview", "cvf", "ecva", "acl", "pmlr", "aaai", "ijcai")
BACKUP_EVERY = 6 * 3600
KEEP_BACKUPS = 4


def write_backup(svc) -> str:
    """A consistent online copy of the live database in the data directory (newest 4 kept)."""
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M")
    folder = svc.settings.backups_dir
    dest = folder / f"scout-{stamp}.sqlite"
    svc.db.backup_to(dest)
    for leftover in folder.glob("*.tmp"):
        leftover.unlink(missing_ok=True)
    backups = sorted(folder.glob("scout-*.sqlite"), key=lambda p: p.stat().st_mtime)
    for old in backups[:-KEEP_BACKUPS]:
        old.unlink(missing_ok=True)
    log.info("database backup written: %s", dest.name)
    return dest.name


class Scheduler:
    def __init__(self, svc):
        self.svc = svc
        self.stop = threading.Event()
        self.queues: dict[str, deque[str]] = {f: deque() for f in FAMILIES}
        self.running: dict[str, str | None] = dict.fromkeys(FAMILIES)
        self.cv = threading.Condition()
        self.threads: list[threading.Thread] = []
        self.last_maintenance = {"concepts": 0.0, "daily": 0.0, "backup": 0.0}
        self.papers_at_concepts = -1
        from confluo_scout.indexer import Indexer

        self.indexer = Indexer(svc)

    # ---- lifecycle --------------------------------------------------------------------------

    def start(self) -> None:
        with self.svc.db.tx() as con:
            con.execute("update edition set status='idle' where status in ('running','queued')")
            # Jobs cut short by a restart: their cursors resume them, the records must not stay "running".
            con.execute("update crawl_job set status='interrupted', finished_at=coalesce(finished_at, ?) "
                        "where status='running'", (utcnow(),))
        for fam in FAMILIES:
            self._spawn(f"crawl-{fam}", self._worker, fam)
        self._spawn("tick", self._tick)
        if self.svc.settings.embed_enabled:
            self._spawn("embed", self._embed_loop)
        self._spawn("maintenance", self._maintenance_loop)
        log.info("scheduler started")

    def shutdown(self) -> None:
        self.stop.set()
        self.svc.crawler.stop.set()
        self.indexer.stop.set()
        with self.cv:
            self.cv.notify_all()

    def _spawn(self, name: str, fn, *args) -> None:
        t = threading.Thread(target=self._guard, args=(fn, *args), name=name, daemon=True)
        t.start()
        self.threads.append(t)

    def _guard(self, fn, *args) -> None:
        while not self.stop.is_set():
            try:
                fn(*args)
                return
            except Exception as exc:
                log.exception("background thread %s crashed: %s", threading.current_thread().name, exc)
                time.sleep(30)

    # ---- queueing ---------------------------------------------------------------------------

    def family_of(self, edition_id: str) -> str:
        row = self.svc.db.one("select sources from edition where id=?", (edition_id,))
        sources = loads(row["sources"], []) if row else []
        first = sources[0]["adapter"] if sources else "openreview"
        return "cvf" if first == "cvf_accepted" else first

    def enqueue(self, edition_id: str, front: bool = False) -> bool:
        fam = self.family_of(edition_id)
        if fam not in self.queues:
            return False
        with self.cv:
            q = self.queues[fam]
            if edition_id in q or self.running.get(fam) == edition_id:
                if front and edition_id in q:
                    q.remove(edition_id)
                    q.appendleft(edition_id)
                return True
            q.appendleft(edition_id) if front else q.append(edition_id)
            self.cv.notify_all()
        with self.svc.db.tx() as con:
            con.execute("update edition set status='queued' where id=?", (edition_id,))
        return True

    def _tick(self) -> None:
        while not self.stop.is_set():
            now = datetime.now(UTC).replace(microsecond=0).isoformat()
            due = self.svc.db.query(
                "select id from edition where enabled=1 and status not in ('running','queued') "
                "and (next_due_at is null or next_due_at <= ?) order by year desc", (now,))
            for r in due:
                self.enqueue(r["id"])
            self.stop.wait(60)

    def _worker(self, fam: str) -> None:
        while not self.stop.is_set():
            with self.cv:
                while not self.queues[fam] and not self.stop.is_set():
                    self.cv.wait(timeout=30)
                if self.stop.is_set():
                    return
                eid = self.queues[fam].popleft()
                self.running[fam] = eid
            try:
                self.svc.crawler.crawl_edition(eid, trigger="schedule")
                try:
                    self.indexer.refresh_payloads(eid)
                except Exception as exc:
                    log.warning("payload refresh for %s failed: %s", eid, exc)
            finally:
                with self.cv:
                    self.running[fam] = None

    # ---- embedding --------------------------------------------------------------------------

    def _embed_loop(self) -> None:
        while not self.stop.is_set():
            if self.svc.interactive.is_set():
                self.stop.wait(1.0)
                continue
            pending = self.indexer.pending_count()
            if pending:
                self.indexer.embed_pending(limit=256, batch=16, embedder=self.svc.bg_embedder,
                                           yield_to=self.svc.interactive)
            else:
                self.stop.wait(30)

    # ---- maintenance ------------------------------------------------------------------------

    def _maintenance_loop(self) -> None:
        self.stop.wait(120)
        while not self.stop.is_set():
            now = time.time()
            try:
                from confluo_scout.areas import backfill

                backfill(self.svc, embedder=self.svc.bg_embedder)
            except Exception as exc:
                log.warning("area backfill failed: %s", exc)
            n_papers = int(self.svc.db.scalar("select count(*) from paper where embed_hash is not null") or 0)
            if now - self.last_maintenance["concepts"] > 6 * 3600 and n_papers != self.papers_at_concepts and n_papers:
                try:
                    from confluo_scout.concepts import ConceptBuilder

                    ConceptBuilder(self.svc).rebuild(embedder=self.svc.bg_embedder)
                    self.papers_at_concepts = n_papers
                except Exception as exc:
                    log.warning("concept rebuild failed: %s", exc)
                self.last_maintenance["concepts"] = now
            if now - self.last_maintenance["backup"] > BACKUP_EVERY:
                try:
                    write_backup(self.svc)
                except Exception as exc:
                    log.warning("database backup failed: %s", exc)
                self.last_maintenance["backup"] = now
            if now - self.last_maintenance["daily"] > 24 * 3600:
                self._daily()
                self.last_maintenance["daily"] = now
            self.stop.wait(600)

    def _daily(self) -> None:
        try:
            self.svc.vectors.snapshot()
        except Exception as exc:
            log.warning("qdrant snapshot failed: %s", exc)
        try:
            from confluo_scout.discovery import discover_all

            res = discover_all(self.svc)
            if res["added"]:
                log.info("discovered editions: %s", res["added"])
        except Exception as exc:
            log.warning("discovery failed: %s", exc)

    # ---- status -----------------------------------------------------------------------------

    def status(self) -> dict:
        with self.cv:
            queues = {f: list(q) for f, q in self.queues.items() if q}
            running = {f: e for f, e in self.running.items() if e}
        return {"running": running, "queued": queues, "indexer": dict(self.indexer.progress),
                "hosts": self.svc.fetcher.host_status(), "time": utcnow()}
