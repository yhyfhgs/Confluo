"""Bring the abstract shards and the vector store back in line with the database after a restore."""

from __future__ import annotations

import json
import logging

import zstandard

from confluo_scout.vectors import CONCEPTS, PAPERS

log = logging.getLogger("scout.reconcile")


def repair_abstract_pointers(svc) -> dict:
    """Point every paper at the line that holds its abstract in the current shard generation."""
    fixed = missing = 0
    for (eid,) in svc.db.query("select distinct edition_id from paper where abstract_len>0"):
        man = svc.abstracts.manifest(eid)
        if not man:
            continue
        gen = man["gen"]
        # Papers whose text still waits in abstract_pending need no shard pointer.
        base = ("select count(*) from paper p where p.edition_id=? and p.abstract_len>0 and not exists "
                "(select 1 from abstract_pending a where a.paper_id=p.id)")
        ok_rows = svc.db.query(base + " and p.abstract_gen=?", (eid, gen))[0][0]
        total = svc.db.query(base, (eid,))[0][0]
        if ok_rows == total:
            continue
        uid_to_id = {r[0]: r[1] for r in svc.db.query("select uid, id from paper where edition_id=?", (eid,))}
        updates = []
        for part_no, part in enumerate(man.get("parts", [])):
            path = svc.settings.abstracts_dir / eid / f"g{gen:04d}" / part["name"]
            if not path.is_file():
                continue
            raw = zstandard.ZstdDecompressor().decompress(path.read_bytes()).decode("utf-8")
            for line_no, line in enumerate(x for x in raw.splitlines() if x):
                pid = uid_to_id.get(json.loads(line).get("uid"))
                if pid is not None:
                    updates.append((gen, part_no, line_no, pid))
        with svc.db.tx() as con:
            con.executemany("update paper set abstract_gen=?, abstract_part=?, abstract_line=? where id=?", updates)
        fixed += len(updates)
        missing += max(0, total - len(updates))
    return {"repointed": fixed, "unresolved": missing}


def drop_orphan_vectors(svc) -> dict:
    """Delete vectors whose ids no longer exist (ids are reused after a restore)."""
    from qdrant_client import models as qm

    out = {}
    for collection, table in ((PAPERS, "paper"), (CONCEPTS, "concept")):
        max_id = svc.db.scalar(f"select coalesce(max(id), 0) from {table}") or 0
        n_before = svc.vectors.count(collection)
        stale = []
        offset = None
        while True:
            pts, offset = svc.vectors.client.scroll(collection, limit=2048, offset=offset, with_payload=False,
                                                    with_vectors=False)
            stale += [int(p.id) for p in pts if int(p.id) > max_id]
            if offset is None:
                break
        for i in range(0, len(stale), 1000):
            svc.vectors.client.delete(collection, points_selector=qm.PointIdsList(points=stale[i:i + 1000]), wait=True)
        out[collection] = {"before": n_before, "deleted": len(stale), "max_id": max_id}
    return out


def reconcile_after_restore(svc) -> dict:
    res = {"abstracts": repair_abstract_pointers(svc)}
    try:
        res["vectors"] = drop_orphan_vectors(svc)
    except Exception as exc:
        res["vectors"] = f"skipped: {exc}"
    log.warning("reconciled after restore: %s", res)
    return res
