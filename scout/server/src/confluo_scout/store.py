"""Paper store: upsert and merge records from several sources, keep FTS in sync, compute
review statistics and quality, and compact abstracts into shards."""

from __future__ import annotations

import logging
import math
import sqlite3
from collections import defaultdict
from dataclasses import asdict

from confluo_scout.abstracts import AbstractStore
from confluo_scout.db import Database, dumps, loads, utcnow
from confluo_scout.records import (
    STATUS_ACCEPTED,
    TIER_FINDINGS,
    TIER_ORAL,
    TIER_POSTER,
    TIER_SPOTLIGHT,
    PaperRecord,
    clean_text,
    norm_title,
    sha1,
)

log = logging.getLogger("scout.store")

# Lower number = more trusted for bibliographic fields (title, authors, area).
SOURCE_PRIORITY = {"openreview": 0, "acl": 1, "pmlr": 2, "cvf": 3, "ecva": 4, "aaai": 5, "ijcai": 6,
                   "cvf_accepted": 9}
PROCEEDINGS_SOURCES = ("pmlr", "cvf", "acl", "ecva", "aaai", "ijcai")
_RECORD_FIELDS = ("title", "authors", "keywords", "area", "area_secondary", "tldr", "status", "decision_label",
                  "tier", "track", "forum_url", "pdf_url", "proceedings_url", "doi", "arxiv_id")


def _prio(source: str) -> int:
    return SOURCE_PRIORITY.get(source, 50)


def merge_sources(sources: dict[str, dict]) -> dict:
    """Combine per-source fields into the paper's visible fields (order independent)."""
    srcs = sorted((s for s in sources if not s.startswith("_")), key=_prio)

    def first(field: str):
        for s in srcs:
            v = sources[s].get(field)
            if v not in (None, "", []):
                return v
        return None

    merged: dict = {f: first(f) for f in ("title", "authors", "area", "area_secondary", "tldr", "track", "doi",
                                          "arxiv_id", "forum_url")}
    kws: list[str] = []
    seen = set()
    for s in srcs:
        for k in sources[s].get("keywords") or []:
            key = k.strip().lower()
            if key and key not in seen:
                seen.add(key)
                kws.append(k.strip())
    merged["keywords"] = kws
    # Status: the review platform knows best; proceedings imply acceptance.
    status = sources.get("openreview", {}).get("status")
    if not status and any(s in sources for s in PROCEEDINGS_SOURCES):
        status = STATUS_ACCEPTED
    merged["status"] = status or first("status") or STATUS_ACCEPTED
    # Decision label: the strongest tier any source reports.
    best = (None, None)
    for s in srcs:
        lab, tier = sources[s].get("decision_label"), sources[s].get("tier")
        if lab and (best[1] is None or (tier or 0) > (best[1] or 0)):
            best = (lab, tier)
    merged["decision_label"], merged["tier"] = best
    # Links: proceedings first for the PDF, OpenReview for the forum.
    merged["proceedings_url"] = next((sources[s].get("proceedings_url") for s in PROCEEDINGS_SOURCES
                                      if sources.get(s, {}).get("proceedings_url")), None)
    merged["pdf_url"] = next((sources[s].get("pdf_url") for s in (*PROCEEDINGS_SOURCES, "openreview")
                              if sources.get(s, {}).get("pdf_url")), None)
    return merged


class Store:
    def __init__(self, db: Database, abstracts: AbstractStore):
        self.db = db
        self.abstracts = abstracts

    # ---- abstracts --------------------------------------------------------------------------

    def abstract_of(self, row: sqlite3.Row | dict, con: sqlite3.Connection | None = None) -> str | None:
        con = con or self.db.con
        pend = con.execute("select text from abstract_pending where paper_id=?", (row["id"],)).fetchone()
        if pend:
            return pend[0]
        return self.abstracts.read(row["edition_id"], row["abstract_gen"], row["abstract_part"],
                                   row["abstract_line"])

    def abstracts_for(self, rows: list[sqlite3.Row]) -> dict[int, str]:
        out = {}
        if not rows:
            return out
        ids = [r["id"] for r in rows]
        pend = {}
        for chunk in range(0, len(ids), 500):
            part = ids[chunk:chunk + 500]
            q = f"select paper_id, text from abstract_pending where paper_id in ({','.join('?' * len(part))})"
            pend.update({r[0]: r[1] for r in self.db.query(q, tuple(part))})
        for r in rows:
            text = pend.get(r["id"]) or self.abstracts.read(r["edition_id"], r["abstract_gen"], r["abstract_part"],
                                                            r["abstract_line"])
            if text:
                out[r["id"]] = text
        return out

    # ---- upsert -----------------------------------------------------------------------------

    def find_paper(self, con: sqlite3.Connection, edition_id: str, rec: PaperRecord) -> sqlite3.Row | None:
        if not rec.label_only and rec.source_key:
            row = con.execute(
                "select p.* from paper_key k join paper p on p.id = k.paper_id where k.source=? and k.key=?",
                (rec.source, f"{edition_id}|{rec.source_key}"),
            ).fetchone()
            if row:
                return row
        tn = norm_title(rec.title)
        if not tn:
            return None
        return con.execute("select * from paper where edition_id=? and title_norm=? order by id limit 1",
                           (edition_id, tn)).fetchone()

    def upsert_records(self, con: sqlite3.Connection, edition_id: str, records: list[PaperRecord]) -> dict:
        stats = defaultdict(int)
        for rec in records:
            if not clean_text(rec.title):
                stats["skipped_no_title"] += 1
                continue
            try:
                outcome = self._upsert_one(con, edition_id, rec)
            except sqlite3.IntegrityError as exc:  # pragma: no cover - defensive
                log.warning("upsert failed for %s %s: %s", rec.source, rec.source_key, exc)
                outcome = "error"
            stats[outcome] += 1
        return dict(stats)

    def _upsert_one(self, con: sqlite3.Connection, edition_id: str, rec: PaperRecord) -> str:
        now = utcnow()
        row = self.find_paper(con, edition_id, rec)
        if rec.label_only:
            if row is None:
                return "label_unmatched"
            sources = loads(row["sources"], {}) or {}
            entry = sources.get(rec.source, {})
            entry.update({"decision_label": rec.decision_label, "tier": rec.tier})
            sources[rec.source] = entry
            self._apply_merge(con, row, sources, now)
            return "label_applied"

        fields = {k: v for k, v in asdict(rec).items() if k in _RECORD_FIELDS}
        fields["title"] = clean_text(fields["title"])
        fields = {k: v for k, v in fields.items() if v not in (None, "", [])}
        fields["key"] = rec.source_key
        new_abstract = clean_text(rec.abstract) if rec.abstract else ""

        if row is None:
            uid = f"{edition_id}/{rec.source}:{rec.source_key}"
            sources = {rec.source: fields}
            merged = merge_sources(sources)
            cur = con.execute(
                "insert into paper(uid, edition_id, title, title_norm, content_hash, created_at, updated_at) "
                "values(?,?,?,?,?,?,?)",
                (uid, edition_id, merged["title"], norm_title(merged["title"]), "", now, now),
            )
            pid = cur.lastrowid
            row = con.execute("select * from paper where id=?", (pid,)).fetchone()
            outcome = "inserted"
        else:
            sources = loads(row["sources"], {}) or {}
            sources[rec.source] = fields
            outcome = "updated"
        con.execute("insert or ignore into paper_key(source, key, paper_id) values(?,?,?)",
                    (rec.source, f"{edition_id}|{rec.source_key}", row["id"]))

        # Abstract choice: keep the longest; a newer text from the same source replaces it.
        abs_src = sources.get("_abstract", {}).get("source")
        current_len = row["abstract_len"] or 0
        if new_abstract and (current_len == 0 or abs_src == rec.source or len(new_abstract) > current_len * 1.05):
            h = sha1(new_abstract)
            if h != row["abstract_hash"]:
                con.execute(
                    "insert into abstract_pending(paper_id, edition_id, text, hash) values(?,?,?,?) "
                    "on conflict(paper_id) do update set text=excluded.text, hash=excluded.hash",
                    (row["id"], edition_id, new_abstract, h),
                )
                con.execute("update paper set abstract_hash=?, abstract_len=? where id=?",
                            (h, len(new_abstract), row["id"]))
            sources["_abstract"] = {"source": rec.source}
        self._apply_merge(con, row, sources, now)

        if rec.reviews is not None:
            keep = {r.key for r in rec.reviews}
            existing = {r[0] for r in con.execute("select review_key from review where paper_id=?", (row["id"],))}
            for gone in existing - keep:
                con.execute("delete from review where paper_id=? and review_key=?", (row["id"], gone))
            for r in rec.reviews:
                con.execute(
                    "insert into review(paper_id, review_key, rating, rating_raw, confidence, subscores, updated_at) "
                    "values(?,?,?,?,?,?,?) on conflict(paper_id, review_key) do update set rating=excluded.rating, "
                    "rating_raw=excluded.rating_raw, confidence=excluded.confidence, subscores=excluded.subscores, "
                    "updated_at=excluded.updated_at",
                    (row["id"], r.key, r.rating, r.rating_raw, r.confidence, dumps(r.subscores), r.updated_at),
                )
        return outcome

    def _apply_merge(self, con: sqlite3.Connection, row: sqlite3.Row, sources: dict, now: str) -> None:
        merged = merge_sources(sources)
        fresh = con.execute("select abstract_hash from paper where id=?", (row["id"],)).fetchone()
        abstract_hash = fresh[0] if fresh else row["abstract_hash"]
        title = merged["title"] or row["title"]
        kw = merged["keywords"] or []
        content_hash = sha1("|".join([title, ";".join(kw), merged["area"] or "", abstract_hash or ""]))
        authors = merged["authors"] or []
        fts_hash = sha1("|".join([content_hash, ";".join(authors)]))
        con.execute(
            "update paper set title=?, title_norm=?, authors=?, keywords=?, area_native=?, area_secondary=?, tldr=?, "
            "status=?, decision_label=?, tier=?, track=?, forum_url=?, pdf_url=?, proceedings_url=?, doi=?, "
            "arxiv_id=?, sources=?, content_hash=?, updated_at=? where id=?",
            (title, norm_title(title), dumps(authors), dumps(kw), merged["area"], merged["area_secondary"],
             merged["tldr"], merged["status"], merged["decision_label"], merged["tier"], merged["track"],
             merged["forum_url"], merged["pdf_url"], merged["proceedings_url"], merged["doi"], merged["arxiv_id"],
             dumps(sources), content_hash, now, row["id"]),
        )
        if fts_hash != row["fts_hash"]:
            pend = con.execute("select text from abstract_pending where paper_id=?", (row["id"],)).fetchone()
            abstract = pend[0] if pend else (self.abstracts.read(row["edition_id"], row["abstract_gen"],
                                                                 row["abstract_part"], row["abstract_line"]) or "")
            con.execute("delete from paper_fts where rowid=?", (row["id"],))
            con.execute(
                "insert into paper_fts(rowid, title, keywords, authors, area, abstract) values(?,?,?,?,?,?)",
                (row["id"], title, " ; ".join(kw), " ; ".join(authors),
                 " ; ".join(x for x in (merged["area"], merged["area_secondary"]) if x), abstract),
            )
            con.execute("update paper set fts_hash=? where id=?", (fts_hash, row["id"]))

    # ---- statistics and quality -------------------------------------------------------------

    def refresh_edition_stats(self, edition_id: str, venue_quality: float) -> dict:
        """Recompute per-edition rating moments, per-paper review stats and quality."""
        rows = self.db.query(
            "select r.paper_id, r.rating, r.confidence from review r join paper p on p.id=r.paper_id "
            "where p.edition_id=?", (edition_id,))
        ratings = [r["rating"] for r in rows if r["rating"] is not None]
        mean = sum(ratings) / len(ratings) if ratings else None
        std = math.sqrt(sum((x - mean) ** 2 for x in ratings) / len(ratings)) if ratings and len(ratings) > 1 else None
        per_paper: dict[int, list[tuple[float, float | None]]] = defaultdict(list)
        for r in rows:
            if r["rating"] is not None:
                per_paper[r["paper_id"]].append((r["rating"], r["confidence"]))
        papers = self.db.query("select id, tier, status from paper where edition_id=?", (edition_id,))
        updates = []
        for p in papers:
            revs = per_paper.get(p["id"], [])
            stats = review_stats(revs, mean, std)
            q = quality_score(stats.get("R") if stats else None, p["tier"], p["status"], venue_quality)
            updates.append((dumps(stats) if stats else None, q, p["id"]))
        now = utcnow()
        with self.db.tx() as con:
            con.executemany("update paper set review_stats=?, quality=? where id=?", updates)
            con.execute(
                "insert into edition_stats(edition_id, rating_mean, rating_std, n_reviews, updated_at) values(?,?,?,?,?) "
                "on conflict(edition_id) do update set rating_mean=excluded.rating_mean, rating_std=excluded.rating_std, "
                "n_reviews=excluded.n_reviews, updated_at=excluded.updated_at",
                (edition_id, mean, std, len(ratings), now),
            )
            self._refresh_counts(con, edition_id)
        return {"papers": len(papers), "reviews": len(ratings), "rating_mean": mean, "rating_std": std}

    def _refresh_counts(self, con: sqlite3.Connection, edition_id: str) -> None:
        c = con.execute(
            "select count(*), sum(abstract_len>0), sum(embed_hash is not null and embed_hash=content_hash) "
            "from paper where edition_id=?", (edition_id,)).fetchone()
        nrev = con.execute("select count(*) from review r join paper p on p.id=r.paper_id where p.edition_id=?",
                           (edition_id,)).fetchone()[0]
        con.execute("update edition set paper_count=?, abstract_count=?, embedded_count=?, review_count=? where id=?",
                    (c[0] or 0, c[1] or 0, c[2] or 0, nrev, edition_id))

    def refresh_counts(self, edition_id: str) -> None:
        with self.db.tx() as con:
            self._refresh_counts(con, edition_id)

    # ---- compaction -------------------------------------------------------------------------

    def compact_edition(self, edition_id: str) -> dict:
        """Rewrite the edition's abstracts as a new shard generation and switch pointers."""
        pending = self.db.scalar("select count(*) from abstract_pending where edition_id=?", (edition_id,))
        if not pending:
            return {"compacted": False, "pending": 0}
        rows = self.db.query(
            "select id, uid, edition_id, abstract_gen, abstract_part, abstract_line from paper "
            "where edition_id=? and abstract_len>0", (edition_id,))
        texts = self.abstracts_for(rows)
        items = [(r["id"], r["uid"], texts[r["id"]]) for r in rows if r["id"] in texts]
        gen, pointers = self.abstracts.write_generation(edition_id, items)
        with self.db.tx() as con:
            con.executemany("update paper set abstract_gen=?, abstract_part=?, abstract_line=? where id=?",
                            [(gen, part, line, pid) for pid, (part, line) in pointers.items()])
            con.execute("delete from abstract_pending where edition_id=?", (edition_id,))
        self.abstracts.commit_generation(edition_id, gen)
        return {"compacted": True, "pending": pending, "gen": gen, "abstracts": len(items)}


def _phi(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def review_stats(revs: list[tuple[float, float | None]], mean: float | None, std: float | None) -> dict | None:
    """Confidence-weighted, shrunk z-score of a paper's ratings within its edition."""
    if not revs:
        return None
    ratings = [r for r, _ in revs]
    confs = [c for _, c in revs if c is not None]
    out = {
        "n": len(revs),
        "mean": round(sum(ratings) / len(ratings), 3),
        "min": min(ratings),
        "max": max(ratings),
        "std": round(math.sqrt(sum((x - sum(ratings) / len(ratings)) ** 2 for x in ratings) / len(ratings)), 3),
        "confidence": round(sum(confs) / len(confs), 3) if confs else None,
    }
    if mean is not None and std:
        weights = [(c if c is not None else 3.0) for _, c in revs]
        z = sum(w * (r - mean) / std for (r, _), w in zip(revs, weights, strict=True)) / sum(weights)
        z_shrunk = len(revs) / (len(revs) + 2.0) * z
        out["z"] = round(z_shrunk, 4)
        out["R"] = round(_phi(z_shrunk), 4)
    return out


TIER_QUALITY = {TIER_ORAL: 1.0, TIER_SPOTLIGHT: 0.85, TIER_POSTER: 0.65, TIER_FINDINGS: 0.5}


def quality_score(R: float | None, tier: int | None, status: str | None, venue_quality: float) -> float:
    parts: list[tuple[float, float]] = []
    if R is not None:
        parts.append((0.5, R))
    if status == "rejected":
        parts.append((0.35, 0.2))
    elif tier is not None:
        parts.append((0.35, TIER_QUALITY.get(tier, 0.6)))
    elif status == STATUS_ACCEPTED:
        parts.append((0.35, 0.6))
    parts.append((0.15, venue_quality))
    total = sum(w for w, _ in parts)
    return round(sum(w * v for w, v in parts) / total, 4)


def venue_quality_from_ratings(ratings: list[str]) -> float:
    tags = {r.upper() for r in ratings}
    if "CCF-A" in tags or "ICORE-A*" in tags:
        return 1.0
    if "CCF-B" in tags or "ICORE-A" in tags:
        return 0.8
    if tags:
        return 0.6
    return 0.5
