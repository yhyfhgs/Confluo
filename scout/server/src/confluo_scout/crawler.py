"""Run one edition crawl: all configured sources, checkpointed batch by batch, then finalize
(abstract compaction, review statistics, quality, counts, next due time)."""

from __future__ import annotations

import logging
import threading
import traceback
from datetime import UTC, datetime, timedelta

from confluo_scout.adapters.base import AuthError, CrawlContext, StructureDrift
from confluo_scout.db import Database, dumps, loads, utcnow
from confluo_scout.fetch import ChallengeError, CircuitOpen, Fetcher, FetchError, RobotsDenied
from confluo_scout.records import norm_title
from confluo_scout.store import Store, venue_quality_from_ratings

log = logging.getLogger("scout.crawler")

# How long until an edition is due again, by phase.
REFRESH = {"in_review": timedelta(hours=24), "decided": timedelta(days=7), "published": timedelta(days=30),
           "unknown": timedelta(days=7)}
RETRY = [timedelta(hours=1), timedelta(hours=4), timedelta(hours=24)]


def _iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat()


class Crawler:
    def __init__(self, db: Database, store: Store, fetcher: Fetcher, adapters: dict):
        self.db = db
        self.store = store
        self.fetcher = fetcher
        self.adapters = adapters
        self.stop = threading.Event()
        self.on_progress = None  # optional callback(edition_id, note)

    def crawl_edition(self, edition_id: str, trigger: str = "schedule") -> dict:
        ed = self.db.one("select e.*, s.ratings from edition e join series s on s.id=e.series_id where e.id=?",
                         (edition_id,))
        if ed is None:
            raise KeyError(edition_id)
        sources = loads(ed["sources"], []) or []
        meta = loads(ed["meta"], {}) or {}
        started = utcnow()
        with self.db.tx() as con:
            job_id = con.execute("insert into crawl_job(edition_id, trigger, started_at, status) values(?,?,?,?)",
                                 (edition_id, trigger, started, "running")).lastrowid
            con.execute("update edition set status='running', last_crawl_at=? where id=?", (started, edition_id))
        totals: dict = {"batches": 0, "records": 0}
        phase = None
        error: str | None = None
        status = "ok"
        for src in sources:
            adapter = self.adapters.get(src["adapter"])
            if adapter is None:
                log.warning("%s: no adapter %s", edition_id, src["adapter"])
                continue
            sid = adapter.source_id(src)
            row = self.db.one("select cursor from crawl_cursor where edition_id=? and source=?", (edition_id, sid))
            saved = loads(row["cursor"], {}) if row else {}
            cursor = {} if not saved or saved.get("complete") else saved.get("state", {})
            ctx = CrawlContext(
                fetcher=self.fetcher, edition_id=edition_id, year=ed["year"], label=ed["label"], cursor=cursor,
                has_abstract=lambda tn, eid=edition_id: self._has_abstract(eid, tn),
                known_titles=lambda eid=edition_id: self._known_titles(eid),
                stop=self.stop, log=log, include_rejected=bool(meta.get("include_rejected")),
            )
            try:
                for batch in adapter.crawl(src, ctx):
                    with self.db.tx() as con:
                        stats = self.store.upsert_records(con, edition_id, batch.records)
                        con.execute(
                            "insert into crawl_cursor(edition_id, source, cursor, updated_at) values(?,?,?,?) "
                            "on conflict(edition_id, source) do update set cursor=excluded.cursor, "
                            "updated_at=excluded.updated_at",
                            (edition_id, sid, dumps({"state": batch.cursor, "complete": False}), utcnow()),
                        )
                    totals["batches"] += 1
                    totals["records"] += len(batch.records)
                    for k, v in stats.items():
                        totals[k] = totals.get(k, 0) + v
                    if batch.phase and (phase is None or batch.phase == "in_review"):
                        if phase != batch.phase:
                            with self.db.tx() as con:  # show the phase while the crawl is still running
                                con.execute("update edition set phase=? where id=?", (batch.phase, edition_id))
                        phase = batch.phase
                    if self.on_progress:
                        self.on_progress(edition_id, batch.note or "")
                    if self.stop.is_set():
                        break
                if self.stop.is_set():
                    status, error = "stopped", "stopped"
                    break
                with self.db.tx() as con:
                    con.execute("update crawl_cursor set cursor=?, updated_at=? where edition_id=? and source=?",
                                (dumps({"state": {}, "complete": True}), utcnow(), edition_id, sid))
            except (ChallengeError, AuthError, RobotsDenied) as exc:
                status, error = "blocked", f"{sid}: {exc}"
                log.error("%s blocked: %s", edition_id, error)
            except StructureDrift as exc:
                status, error = "drift", f"{sid}: {exc}"
                log.error("%s structure drift: %s", edition_id, error)
            except (FetchError, CircuitOpen) as exc:
                status, error = "failed", f"{sid}: {exc}"
                log.error("%s fetch failed: %s", edition_id, error)
            except Exception as exc:
                status, error = "failed", f"{sid}: {type(exc).__name__}: {exc}"
                log.error("%s crashed: %s\n%s", edition_id, error, traceback.format_exc())

        finalize = {}
        try:
            finalize["compact"] = self.store.compact_edition(edition_id)
            finalize["stats"] = self.store.refresh_edition_stats(edition_id,
                                                                 venue_quality_from_ratings(loads(ed["ratings"], [])))
        except Exception as exc:
            log.error("%s finalize failed: %s\n%s", edition_id, exc, traceback.format_exc())
            finalize["error"] = str(exc)

        now = datetime.now(UTC)
        fail_count = 0 if status == "ok" else (ed["fail_count"] or 0) + 1
        if status == "ok":
            next_due = now + REFRESH.get(phase or ed["phase"] or "unknown", REFRESH["unknown"])
            ed_status = "idle"
        elif status == "stopped":
            next_due = now
            ed_status = "idle"
        else:
            next_due = now + RETRY[min(fail_count - 1, len(RETRY) - 1)]
            ed_status = "attention" if fail_count >= 3 or status in ("blocked", "drift") else "error"
        with self.db.tx() as con:
            con.execute(
                "update edition set status=?, phase=coalesce(?, phase), next_due_at=?, fail_count=?, last_error=?, "
                "last_success_at=case when ?='ok' then ? else last_success_at end where id=?",
                (ed_status, phase, _iso(next_due), fail_count, error, status, utcnow(), edition_id),
            )
            con.execute("update crawl_job set finished_at=?, status=?, stats=?, error=? where id=?",
                        (utcnow(), status, dumps({**totals, **finalize}), error, job_id))
        log.info("%s crawl %s: %s", edition_id, status, totals)
        return {"edition": edition_id, "status": status, "error": error, **totals, **finalize}

    def _has_abstract(self, edition_id: str, title_norm: str) -> bool:
        row = self.db.one("select abstract_len from paper where edition_id=? and title_norm=?",
                          (edition_id, title_norm))
        return bool(row and row[0])

    def _known_titles(self, edition_id: str) -> set[str]:
        return {r[0] for r in self.db.query("select title_norm from paper where edition_id=?", (edition_id,))}


__all__ = ["Crawler", "norm_title"]
