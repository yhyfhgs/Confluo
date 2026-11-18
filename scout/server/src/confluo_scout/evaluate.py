"""Known-item evaluation: an author's TL;DR is the query, the paper itself is the target.

Compares three configurations on the same queries: lexical only (exact mode with OR semantics),
dense only (one round, no expansion) and full HopLoop. Reports recall@1/@10 and MRR@10.
No manual labels are needed, so the numbers are a proxy: they reward finding one specific paper,
not the full set of relevant papers.
"""

from __future__ import annotations

import random
import statistics
import time

from confluo_scout.search.text import STOPWORDS, words


def sample_queries(svc, n: int, seed: int = 7) -> list[dict]:
    rows = svc.db.query(
        "select p.id, p.uid, p.title, p.tldr from paper p join edition e on e.id=p.edition_id "
        "where e.enabled=1 and p.tldr is not null and length(p.tldr) between 40 and 300 "
        "and p.embed_hash is not null and p.embed_hash=p.content_hash and p.status='accepted'")
    random.Random(seed).shuffle(rows)
    return [{"id": r["id"], "uid": r["uid"], "title": r["title"], "q": r["tldr"]} for r in rows[:n]]


def _rank(results: list[dict], pid: int) -> int | None:
    for i, r in enumerate(results, 1):
        if r["id"] == pid:
            return i
    return None


def run(svc, n: int = 40) -> dict:
    engine = svc.engine
    qs = sample_queries(svc, n)
    configs = {
        "bm25_or": lambda q: engine.search({"q": " OR ".join(w for w in words(q) if w.lower() not in STOPWORDS),
                                            "mode": "exact", "limit": 10}),
        "dense_1round": lambda q: engine.search({"q": q, "max_rounds": 1, "limit": 10}),
        "hoploop": lambda q: engine.search({"q": q, "limit": 10}),
    }
    out: dict = {"queries": len(qs)}
    for name, fn in configs.items():
        ranks, times = [], []
        for item in qs:
            t0 = time.time()
            res = fn(item["q"])
            times.append(time.time() - t0)
            ranks.append(_rank(res.get("results", []), item["id"]))
        hit1 = sum(1 for r in ranks if r == 1) / len(ranks)
        hit10 = sum(1 for r in ranks if r and r <= 10) / len(ranks)
        mrr = sum(1 / r for r in ranks if r and r <= 10) / len(ranks)
        out[name] = {"recall@1": round(hit1, 3), "recall@10": round(hit10, 3), "mrr@10": round(mrr, 3),
                     "median_s": round(statistics.median(times), 2)}
    return out
