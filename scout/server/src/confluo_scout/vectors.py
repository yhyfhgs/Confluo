"""Qdrant vector store: `papers` (one vector per paper) and `concepts` (vocabulary terms).

Qdrant keeps its live data on a Docker named volume: on the virtiofs bind mount it reports
"FUSE filesystems may cause data corruption" (checked 2026-11-19). Snapshots go to the data
directory (`$CONFLUO_HOME/scout/qdrant/snapshots`), and an empty collection is restored from the
newest snapshot on start.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
from qdrant_client import QdrantClient
from qdrant_client import models as qm

from confluo_scout.config import Settings

log = logging.getLogger("scout.vectors")

PAPERS = "papers"
CONCEPTS = "concepts"


def build_filter(editions: list[str] | None = None, statuses: list[str] | None = None,
                 min_tier: int | None = None) -> qm.Filter | None:
    must: list = []
    if editions is not None:
        must.append(qm.FieldCondition(key="edition", match=qm.MatchAny(any=list(editions) or ["__none__"])))
    if statuses:
        must.append(qm.FieldCondition(key="status", match=qm.MatchAny(any=list(statuses))))
    if min_tier:
        must.append(qm.FieldCondition(key="tier", range=qm.Range(gte=min_tier)))
    return qm.Filter(must=must) if must else None


class VectorStore:
    def __init__(self, settings: Settings, dim: int = 768, client: QdrantClient | None = None):
        self.settings = settings
        self.dim = dim
        self.client = client or QdrantClient(url=settings.qdrant_url, timeout=120, prefer_grpc=False,
                                             check_compatibility=False)
        self.ensure()

    def ensure(self) -> None:
        existing = {c.name for c in self.client.get_collections().collections}
        for name in (PAPERS, CONCEPTS):
            if name in existing:
                continue
            if self.restore_latest(name):
                continue
            self.client.create_collection(
                name, vectors_config=qm.VectorParams(size=self.dim, distance=qm.Distance.COSINE),
                hnsw_config=qm.HnswConfigDiff(m=32, ef_construct=200),
                optimizers_config=qm.OptimizersConfigDiff(default_segment_number=4),
            )
            log.info("created qdrant collection %s", name)
        if type(getattr(self.client, "_client", None)).__name__ == "QdrantLocal":
            return  # payload indexes only matter on the server
        for field, schema in (("edition", qm.PayloadSchemaType.KEYWORD), ("series", qm.PayloadSchemaType.KEYWORD),
                              ("status", qm.PayloadSchemaType.KEYWORD), ("year", qm.PayloadSchemaType.INTEGER),
                              ("tier", qm.PayloadSchemaType.INTEGER)):
            try:
                self.client.create_payload_index(PAPERS, field, field_schema=schema)
            except Exception:
                pass

    # ---- papers ---------------------------------------------------------------------------

    def upsert_papers(self, ids: list[int], vecs: np.ndarray, payloads: list[dict]) -> None:
        self.client.upsert(PAPERS, points=qm.Batch(ids=ids, vectors=vecs.tolist(), payloads=payloads), wait=True)

    def set_payloads(self, items: list[tuple[int, dict]]) -> None:
        groups: dict[str, tuple[dict, list[int]]] = {}
        for pid, payload in items:
            key = repr(sorted(payload.items()))
            groups.setdefault(key, (payload, []))[1].append(pid)
        for payload, pids in groups.values():
            for i in range(0, len(pids), 1000):
                self.client.set_payload(PAPERS, payload=payload, points=pids[i:i + 1000], wait=False)

    def delete_papers(self, ids: list[int]) -> None:
        if ids:
            self.client.delete(PAPERS, points_selector=qm.PointIdsList(points=ids), wait=True)

    def search(self, vec: np.ndarray, limit: int, flt: qm.Filter | None = None,
               collection: str = PAPERS) -> list[tuple[int, float]]:
        res = self.client.query_points(collection, query=vec.tolist(), limit=limit, query_filter=flt,
                                       search_params=qm.SearchParams(hnsw_ef=max(128, limit)), with_payload=False)
        return [(int(p.id), float(p.score)) for p in res.points]

    def search_many(self, vecs: np.ndarray, limit: int, flt: qm.Filter | None = None,
                    collection: str = PAPERS) -> list[list[tuple[int, float]]]:
        if len(vecs) == 0:
            return []
        reqs = [qm.QueryRequest(query=v.tolist(), limit=limit, filter=flt, with_payload=False,
                                params=qm.SearchParams(hnsw_ef=max(128, limit))) for v in vecs]
        out = self.client.query_batch_points(collection, requests=reqs)
        return [[(int(p.id), float(p.score)) for p in r.points] for r in out]

    def vectors_of(self, ids: list[int], collection: str = PAPERS) -> dict[int, np.ndarray]:
        if not ids:
            return {}
        pts = self.client.retrieve(collection, ids=ids, with_vectors=True, with_payload=False)
        return {int(p.id): np.asarray(p.vector, dtype=np.float32) for p in pts if p.vector is not None}

    def count(self, collection: str = PAPERS) -> int:
        return int(self.client.count(collection, exact=False).count)

    # ---- concepts -------------------------------------------------------------------------

    def upsert_concepts(self, ids: list[int], vecs: np.ndarray, payloads: list[dict]) -> None:
        self.client.upsert(CONCEPTS, points=qm.Batch(ids=ids, vectors=vecs.tolist(), payloads=payloads), wait=True)

    def search_concepts(self, vecs: np.ndarray, limit: int) -> list[list[tuple[int, float, dict]]]:
        if len(vecs) == 0:
            return []
        reqs = [qm.QueryRequest(query=v.tolist(), limit=limit, with_payload=True) for v in vecs]
        out = self.client.query_batch_points(CONCEPTS, requests=reqs)
        return [[(int(p.id), float(p.score), p.payload or {}) for p in r.points] for r in out]

    # ---- snapshots ------------------------------------------------------------------------

    def snapshot(self, keep: int = 2) -> list[str]:
        """Create snapshots of both collections; Qdrant writes them to the mounted snapshots dir."""
        made = []
        for name in (PAPERS, CONCEPTS):
            desc = self.client.create_snapshot(name, wait=True)
            if desc:
                made.append(f"{name}/{desc.name}")
            snaps = sorted(self.client.list_snapshots(name), key=lambda s: s.creation_time or "")
            for old in snaps[:-keep]:
                try:
                    self.client.delete_snapshot(name, old.name, wait=True)
                except Exception:
                    pass
        return made

    def restore_latest(self, name: str) -> bool:
        """Recover an absent collection from the newest snapshot in the data directory."""
        local_dir = self.settings.snapshots_dir / name
        if not local_dir.is_dir():
            return False
        files = sorted(local_dir.glob("*.snapshot"), key=lambda p: p.stat().st_mtime)
        if not files:
            return False
        latest: Path = files[-1]
        location = f"file:///qdrant/snapshots/{name}/{latest.name}"
        try:
            self.client.recover_snapshot(name, location=location, wait=True)
            log.info("restored qdrant collection %s from %s", name, latest.name)
            return True
        except Exception as exc:
            log.warning("could not restore %s from %s: %s", name, latest.name, exc)
            return False
