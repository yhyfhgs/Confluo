"""HopLoop: converging multi-hop retrieval and ranking (design: docs/plan/scout/retrieval.md).

Each round recalls candidates through BM25 (exact and expanded), dense query and keyword vectors
and, from round 2 on, seed-paper similarity; merges them into a growing pool and a session graph;
scores relevance, quality and decision-model judgments; and stops when the top n list (ids and
order) equals the previous round's. Exact mode runs one lexical round.
"""

from __future__ import annotations

import itertools
import logging
import time
from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass, field

import numpy as np
from qdrant_client import models as qm

from confluo_scout.concepts import get_vocab
from confluo_scout.db import loads
from confluo_scout.records import VISIBLE_STATUSES
from confluo_scout.search.graph import SessionGraph
from confluo_scout.search.highlight import Highlighter
from confluo_scout.search.keywords import FtsVocab, Keyword, KeywordPlanner
from confluo_scout.search.parse import ParsedQuery, exact_expression, parse_query
from confluo_scout.search.text import fts_phrase, words
from confluo_scout.vectors import PAPERS, build_filter

log = logging.getLogger("scout.search")

BM25_WEIGHTS = "4.0, 2.5, 1.5, 1.0, 1.0"  # title, keywords, authors, area, abstract
CHANNEL_WEIGHT = {"bm25_exact": 1.0, "dense_query": 1.0, "dense_kw": 0.7, "dense_seed": 0.6, "bm25_expand": 0.5}
DEFAULTS = {"topn": 10, "seeds": 5, "new_keywords": 4, "judge_top": 40, "max_rounds": 5, "time_budget_s": 25.0,
            "beta": 0.15, "gamma": 0.5, "hop_decay": 0.7, "limit": 50}
SORTS = ("mix", "relevance", "review", "tier", "recent")


@dataclass
class Scope:
    editions: list[str]
    statuses: list[str]
    min_tier: int | None
    restrict: set[int] | None = None  # author / area restrictions resolved through FTS

    def qfilter(self) -> qm.Filter | None:
        return build_filter(self.editions, self.statuses, self.min_tier)


@dataclass
class Session:
    pq: ParsedQuery
    params: dict
    scope: Scope
    qvec: np.ndarray | None = None
    qterm: np.ndarray | None = None
    keywords: list[Keyword] = field(default_factory=list)
    pool: set[int] = field(default_factory=set)
    lists: list[tuple[str, int, list[int]]] = field(default_factory=list)  # (channel, round, ranked ids)
    first_round: dict[int, int] = field(default_factory=dict)
    via: dict[int, set[str]] = field(default_factory=lambda: defaultdict(set))
    cos: dict[int, float] = field(default_factory=dict)
    graph: SessionGraph = field(default_factory=SessionGraph)
    meta: dict[int, dict] = field(default_factory=dict)
    judgments: dict = field(default_factory=dict)
    seeds_used: set[int] = field(default_factory=set)
    kw_sets: dict[str, dict[str, set[int]]] = field(default_factory=dict)
    scores: dict[int, dict] = field(default_factory=dict)
    trace: list[dict] = field(default_factory=list)
    norm: dict = field(default_factory=dict)  # frozen after round 1 so scores only move on new evidence
    t0: float = field(default_factory=time.time)


def _num(params: dict, key: str, cast=float):
    v = params.get(key)
    if v in (None, ""):
        return cast(DEFAULTS[key])
    try:
        return cast(v)
    except (TypeError, ValueError):
        return cast(DEFAULTS[key])


class SearchEngine:
    def __init__(self, svc):
        self.svc = svc
        self.db = svc.db

    # ---- public -------------------------------------------------------------------------------

    def search(self, params: dict) -> dict:
        final = None
        for ev in self.stream(params):
            if ev["event"] == "done":
                final = ev["data"]
        return final or {}

    def stream(self, params: dict) -> Iterator[dict]:
        q = (params.get("q") or "").strip()
        mode = params.get("mode") or "smart"
        pq = parse_query(q)
        scope = self._scope(pq, params)
        if mode == "exact":
            yield from self._exact(pq, params, scope)
        else:
            yield from self._smart(pq, params, scope)

    # ---- scope ------------------------------------------------------------------------------

    def _scope(self, pq: ParsedQuery, params: dict) -> Scope:
        rows = self.db.query("select id, series_id, year, enabled from edition")
        venues = [v.lower() for v in (params.get("venues") or [])] + pq.venues
        lo, hi = pq.years or (None, None)
        if params.get("year_from"):
            lo = int(params["year_from"])
        if params.get("year_to"):
            hi = int(params["year_to"])
        eds = []
        for r in rows:
            if venues:
                if r["id"] not in venues and r["series_id"] not in venues:
                    continue
            elif not r["enabled"]:
                continue
            if (lo and r["year"] < lo) or (hi and r["year"] > hi):
                continue
            eds.append(r["id"])
        statuses = list(params.get("statuses") or pq.statuses or VISIBLE_STATUSES)
        if pq.labels and not params.get("statuses"):
            statuses = ["accepted"]
        restrict = None
        for name in pq.authors:
            ph = fts_phrase(name)
            if ph:
                ids = {r[0] for r in self.db.query("select rowid from paper_fts where paper_fts match ?",
                                                   (f"authors : {ph}",))}
                restrict = ids if restrict is None else restrict & ids
        for area in pq.areas:
            ph = fts_phrase(area)
            if ph:
                ids = {r[0] for r in self.db.query("select rowid from paper_fts where paper_fts match ?",
                                                   (f"area : {ph} OR keywords : {ph}",))}
                restrict = ids if restrict is None else restrict & ids
        return Scope(editions=eds, statuses=statuses, min_tier=pq.min_tier, restrict=restrict)

    # ---- recall primitives ------------------------------------------------------------------

    def _fts(self, expr: str, scope: Scope, limit: int) -> list[tuple[int, float]]:
        if not expr or not scope.editions:
            return []
        eds = ",".join("?" * len(scope.editions))
        sts = ",".join("?" * len(scope.statuses))
        sql = (f"select f.rowid, bm25(paper_fts, {BM25_WEIGHTS}) as s from paper_fts f join paper p on p.id=f.rowid "
               f"where paper_fts match ? and p.edition_id in ({eds}) and p.status in ({sts})")
        args: list = [expr, *scope.editions, *scope.statuses]
        if scope.min_tier:
            sql += " and coalesce(p.tier, 0) >= ?"
            args.append(scope.min_tier)
        sql += " order by s limit ?"
        args.append(limit * 3 if scope.restrict is not None else limit)
        try:
            rows = self.db.query(sql, tuple(args))
        except Exception as exc:
            log.info("fts expression rejected (%s): %s", exc, expr)
            return []
        out = [(int(r[0]), -float(r[1])) for r in rows]
        if scope.restrict is not None:
            out = [x for x in out if x[0] in scope.restrict]
        return out[:limit]

    def _match_set(self, expr: str, pool: set[int]) -> set[int]:
        if not expr or not pool:
            return set()
        try:
            rows = self.db.query("select rowid from paper_fts where paper_fts match ?", (expr,))
        except Exception:
            return set()
        return {int(r[0]) for r in rows} & pool

    def _dense(self, vecs: np.ndarray, scope: Scope, limit: int) -> list[list[tuple[int, float]]]:
        if not len(vecs) or not scope.editions:
            return [[] for _ in range(len(vecs))]
        lists = self.svc.vectors.search_many(vecs, limit=limit * (3 if scope.restrict is not None else 1),
                                             flt=scope.qfilter())
        if scope.restrict is not None:
            lists = [[x for x in lst if x[0] in scope.restrict][:limit] for lst in lists]
        return lists

    def _cos_for(self, qvec: np.ndarray, ids: list[int]) -> dict[int, float]:
        if not ids:
            return {}
        res = self.svc.vectors.client.query_points(
            PAPERS, query=qvec.tolist(), limit=len(ids), with_payload=False,
            query_filter=qm.Filter(must=[qm.HasIdCondition(has_id=ids)]),
            search_params=qm.SearchParams(exact=True))
        return {int(p.id): float(p.score) for p in res.points}

    def _load_meta(self, s: Session, ids: list[int]) -> None:
        need = [i for i in ids if i not in s.meta]
        labels = {r["id"]: (r["label"], r["year"], r["series_id"]) for r in
                  self.db.query("select id, label, year, series_id from edition")}
        for i in range(0, len(need), 500):
            chunk = need[i:i + 500]
            rows = self.db.query(
                "select id, uid, edition_id, title, authors, keywords, area_native, area_secondary, status, "
                "decision_label, tier, track, quality, review_stats, content_hash, forum_url, pdf_url, "
                "proceedings_url, doi, abstract_gen, abstract_part, abstract_line, tldr from paper "
                f"where id in ({','.join('?' * len(chunk))})", tuple(chunk))
            for r in rows:
                d = dict(r)
                lab, year, series = labels.get(r["edition_id"], (r["edition_id"], None, None))
                d.update(venue=lab, year=year, series=series, authors=loads(r["authors"], []) or [],
                         keywords=loads(r["keywords"], []) or [], review_stats=loads(r["review_stats"], None),
                         title_plain=r["title"])
                s.meta[r["id"]] = d

    def _abstracts(self, s: Session, ids: list[int]) -> None:
        rows = [s.meta[i] for i in ids if i in s.meta and "abstract" not in s.meta[i]]
        texts = self.svc.store.abstracts_for(rows)
        for r in rows:
            r["abstract"] = texts.get(r["id"], "")

    # ---- smart mode ---------------------------------------------------------------------------

    def _smart(self, pq: ParsedQuery, params: dict, scope: Scope) -> Iterator[dict]:
        s = Session(pq=pq, params=params, scope=scope)
        topn, max_rounds = _num(params, "topn", int), _num(params, "max_rounds", int)
        budget = _num(params, "time_budget_s")
        decider = self.svc.decider
        vocab = get_vocab(self.svc)
        planner = KeywordPlanner(self.svc, vocab, decider, FtsVocab(self.db))
        text = pq.plain or pq.raw
        if not text:
            yield {"event": "done", "data": self._final(s, {"reason": "empty", "rounds": 0})}
            return
        emb = self.svc.embedder
        s.qvec = emb.queries([text])[0]
        s.qterm = emb.terms([text])[0]
        s.keywords = planner.extract(pq, s.qterm)
        planner.expand(s.keywords)
        yield {"event": "plan", "data": {"mode": "smart", "keywords": [k.public() for k in s.keywords],
                                         "decision": decider.status(), "scope": self._scope_public(scope),
                                         "cjk": pq.cjk}}
        prev_top: list[int] | None = None
        reason = "max_rounds"
        new_kws = list(s.keywords)
        new_seeds: list[int] = []
        rnd = 0
        for rnd in range(1, max_rounds + 1):
            t_round = time.time()
            added = self._recall_round(s, rnd, new_kws, new_seeds)
            judged = self._score(s, rnd, decider)
            ranked = self._ranked(s)
            top = ranked[:topn]
            entered = [i for i in top if prev_top is None or i not in prev_top]
            left = [i for i in (prev_top or []) if i not in top]
            seeds = [i for i in ranked if i not in s.seeds_used][: _num(params, "seeds", int)]
            info = {"round": rnd, "new_keywords": [k.public() for k in new_kws] if rnd > 1 else [],
                    "seeds": [s.meta[i]["uid"] for i in new_seeds if i in s.meta], "added": added,
                    "pool": len(s.pool), "judged": judged, "top": [s.meta[i]["uid"] for i in top if i in s.meta],
                    "entered": [s.meta[i]["uid"] for i in entered if i in s.meta],
                    "left": [s.meta[i]["uid"] for i in left if i in s.meta],
                    "ms": int((time.time() - t_round) * 1000)}
            s.trace.append(info)
            yield {"event": "round", "data": info}
            yield {"event": "results", "data": {"round": rnd, "results": self._results(s, ranked, params)}}
            if prev_top is not None and self._same_order(s, top, prev_top):
                reason = "stable"
                break
            prev_top = top
            if rnd == max_rounds:
                reason = "max_rounds"
                break
            if time.time() - s.t0 > budget:
                reason = "time_budget"
                break
            # Expand: seeds -> new keywords and similar papers.
            self._abstracts(s, seeds)
            seed_docs = [dict(s.meta[i], score=s.scores[i]["score"]) for i in seeds if i in s.meta]
            new_kws = planner.from_seeds(text, seed_docs, s.keywords, rnd, _num(params, "new_keywords", int),
                                         pool_scores={i: s.scores[i]["score"] for i in s.pool},
                                         top_ids=ranked[:30], match_set=self._match_set)
            planner.expand(new_kws, neighbors=False)
            for k in new_kws:
                s.graph.add("q", f"k:{k.norm}", k.weight)
                if k.source:
                    sid = next((i for i in seeds if s.meta[i]["uid"] == k.source), None)
                    if sid is not None:
                        s.graph.add(f"p:{sid}", f"k:{k.norm}", 0.5)
            s.keywords += new_kws
            new_seeds = seeds
            s.seeds_used.update(seeds)
            if not new_kws and not new_seeds:
                reason = "exhausted"
                break
        yield {"event": "done", "data": self._final(s, {"reason": reason, "rounds": rnd})}

    def _recall_round(self, s: Session, rnd: int, kws: list[Keyword], seeds: list[int]) -> int:
        before = len(s.pool)
        decay = _num(s.params, "hop_decay") ** (rnd - 1)
        lists: list[tuple[str, list[tuple[int, float]], str | None]] = []
        if rnd == 1:
            lists.append(("dense_query", self._dense(s.qvec[None, :], s.scope, 200)[0], None))
        phrases = [(k, fts_phrase(k.text)) for k in kws]
        exact_expr = " OR ".join(p for _, p in phrases if p)
        if exact_expr:
            lists.append(("bm25_exact", self._fts(exact_expr, s.scope, 200), None))
        for k, p in phrases:
            if p:
                lists.append(("bm25_kw", self._fts(p, s.scope, 60), k.norm))
        expand_terms = []
        for k in kws:
            expand_terms += [x for x in (fts_phrase(t) for t in k.synonyms) if x]
            expand_terms += [f'"{t}"' for t in k.fuzzy]
        if expand_terms:
            lists.append(("bm25_expand", self._fts(" OR ".join(expand_terms), s.scope, 200), None))
            for k in kws:
                syn = [x for x in (fts_phrase(t) for t in k.synonyms) if x] + [f'"{t}"' for t in k.fuzzy]
                if syn:
                    lists.append(("bm25_kw_syn", self._fts(" OR ".join(syn), s.scope, 40), k.norm))
        if kws:
            kvecs = self.svc.embedder.queries([k.text for k in kws])
            for k, lst in zip(kws, self._dense(kvecs, s.scope, 50), strict=True):
                lists.append(("dense_kw", lst, k.norm))
        if seeds:
            svecs = self.svc.vectors.vectors_of(seeds)
            sids = [i for i in seeds if i in svecs]
            if sids:
                for sid, lst in zip(sids, self._dense(np.stack([svecs[i] for i in sids]), s.scope, 50), strict=True):
                    lists.append(("dense_seed", [x for x in lst if x[0] != sid], f"p:{sid}"))
        for channel, lst, anchor in lists:
            if not lst:
                continue
            ids = [i for i, _ in lst]
            if channel in CHANNEL_WEIGHT:
                s.lists.append((channel, rnd, ids))
            top = max(v for _, v in lst) or 1.0
            for i, v in lst:
                if i not in s.pool:
                    s.pool.add(i)
                    s.first_round[i] = rnd
                tag = channel if anchor is None or channel == "dense_seed" else f"{channel}:{anchor}"
                s.via[i].add(tag)
                if channel == "dense_query":
                    s.graph.add("q", f"p:{i}", max(0.0, v))
                elif channel in ("bm25_kw", "dense_kw"):
                    w = (v / top) if channel == "bm25_kw" else max(0.0, v)
                    s.graph.add(f"k:{anchor}", f"p:{i}", w * decay)
                elif channel == "bm25_kw_syn":
                    s.graph.add(f"k:{anchor}", f"p:{i}", 0.6 * (v / top) * decay)
                elif channel == "dense_seed":
                    s.graph.add(anchor, f"p:{i}", max(0.0, v) * decay)
        for k in kws:
            s.graph.add("q", f"k:{k.norm}", k.weight)
        return len(s.pool) - before

    def _coverage(self, s: Session) -> dict[int, dict[str, float]]:
        cov: dict[int, dict[str, float]] = defaultdict(dict)
        for k in s.keywords:
            sets = s.kw_sets.get(k.norm)
            missing = s.pool if sets is None else s.pool - sets["_checked"]
            if sets is None:
                sets = {"exact": set(), "syn": set(), "fuzzy": set(), "_checked": set()}
                s.kw_sets[k.norm] = sets
            if missing:
                ph = fts_phrase(k.text)
                sets["exact"] |= self._match_set(ph, missing) if ph else set()
                syn = [x for x in (fts_phrase(t) for t in k.synonyms) if x]
                if syn:
                    sets["syn"] |= self._match_set(" OR ".join(syn), missing)
                if k.fuzzy:
                    sets["fuzzy"] |= self._match_set(" OR ".join(f'"{t}"' for t in k.fuzzy), missing)
                sets["_checked"] |= missing
            for i in s.pool:
                m = 1.0 if i in sets["exact"] else 0.6 if i in sets["syn"] else 0.3 if i in sets["fuzzy"] else 0.0
                cov[i][k.norm] = m
        return cov

    def _score(self, s: Session, rnd: int, decider) -> int:
        pool = list(s.pool)
        self._load_meta(s, pool)
        missing = [i for i in pool if i not in s.cos]
        for i in range(0, len(missing), 1000):
            s.cos.update(self._cos_for(s.qvec, missing[i:i + 1000]))
        decay = _num(s.params, "hop_decay")
        rrf: dict[int, float] = defaultdict(float)
        for channel, rnd_l, ids in s.lists:
            w = CHANNEL_WEIGHT[channel] * decay ** (rnd_l - 1)
            for rank, i in enumerate(ids):
                rrf[i] += w / (60 + rank + 1)
        cov = self._coverage(s)
        wsum = sum(k.weight for k in s.keywords) or 1.0
        ppr = s.graph.ppr()

        if not s.norm:
            cos_vals = np.asarray([s.cos.get(i, 0.0) for i in pool] or [0.0])
            top_cos = np.sort(cos_vals)[-min(len(cos_vals), 50):]
            s.norm = {"cos_lo": float(np.percentile(cos_vals, 10)), "cos_hi": float(top_cos.mean() + top_cos.std()),
                      "rrf_max": max(rrf.values()) if rrf else 1.0}
        lo, hi = s.norm["cos_lo"], max(s.norm["cos_hi"], s.norm["cos_lo"] + 1e-3)
        n_cos = {i: min(1.0, max(0.0, (s.cos.get(i, 0.0) - lo) / (hi - lo))) for i in pool}
        n_rrf = {i: min(1.0, rrf.get(i, 0.0) / (s.norm["rrf_max"] or 1.0)) for i in pool}
        ppr_vals = {i: ppr.get(f"p:{i}", 0.0) for i in pool}
        ppr_max = max(ppr_vals.values()) if ppr_vals else 1.0
        n_ppr = {i: (v / ppr_max if ppr_max > 0 else 0.0) for i, v in ppr_vals.items()}
        beta, gamma = _num(s.params, "beta"), _num(s.params, "gamma")
        rel: dict[int, float] = {}
        for i in pool:
            kw_cov = sum(k.weight * cov[i].get(k.norm, 0.0) for k in s.keywords) / wsum
            rel[i] = 0.30 * n_rrf[i] + 0.40 * n_cos[i] + 0.20 * kw_cov + 0.10 * n_ppr[i]
            s.scores[i] = {"rel": rel[i], "rrf": n_rrf[i], "cos": s.cos.get(i, 0.0), "coverage": kw_cov,
                           "ppr": n_ppr[i], "kw_match": cov[i]}
        # Decision model on the current top J that has not been judged yet.
        judge_top = _num(s.params, "judge_top", int)
        pre = sorted(pool, key=lambda i: -((1 - beta) * rel[i] + beta * (s.meta[i]["quality"] or 0.5)))
        todo = [i for i in pre[:judge_top] if i not in s.judgments]
        if todo:
            self._abstracts(s, todo)
            papers = []
            for i in todo:
                p = dict(s.meta[i])
                p.update(cos=s.cos.get(i, 0.0), coverage=s.scores[i]["coverage"], ppr_norm=n_ppr[i],
                         kw_match={k.text: cov[i].get(k.norm, 0.0) for k in s.keywords if k.round == 1})
                papers.append(p)
            orig = [k.text for k in s.keywords if k.round == 1]
            s.judgments.update(decider.judge(s.pq.plain or s.pq.raw, orig, papers))
        g = gamma if decider.remote else 0.0
        for i in pool:
            j = s.judgments.get(i)
            dec = j.value if j else rel[i]
            dec_star = (j.confidence * dec + (1 - j.confidence) * rel[i]) if j else rel[i]
            q = s.meta[i]["quality"]
            q = 0.5 if q is None else q
            score = (1 - beta) * ((1 - g) * rel[i] + g * dec_star) + beta * q
            s.scores[i].update(dec=dec_star if j else None, quality=q, score=score)
        return len(todo)

    @staticmethod
    def _same_order(s: Session, top: list[int], prev: list[int], tol: float = 0.01) -> bool:
        """Same papers, same order; adjacent swaps within the score resolution count as ties."""
        if set(top) != set(prev):
            return False
        pos = {pid: k for k, pid in enumerate(prev)}
        for a, b in itertools.pairwise(top):
            if pos[a] > pos[b] and abs(s.scores[a]["score"] - s.scores[b]["score"]) >= tol:
                return False
        return True

    def _ranked(self, s: Session) -> list[int]:
        return sorted(s.pool, key=lambda i: (-s.scores[i]["score"], i))

    # ---- exact mode ---------------------------------------------------------------------------

    def _exact(self, pq: ParsedQuery, params: dict, scope: Scope) -> Iterator[dict]:
        s = Session(pq=pq, params=params, scope=scope)
        expr = exact_expression(pq)
        terms = pq.phrases + [w for w in words(pq.plain) if w not in ("AND", "OR", "NOT")] + [v for _, v in pq.columns]
        s.keywords = [Keyword(text=t, origin="query") for t in dict.fromkeys(terms)]
        yield {"event": "plan", "data": {"mode": "exact", "expression": expr, "keywords": [k.public() for k in s.keywords],
                                         "decision": {"model": "none", "remote": False}, "scope": self._scope_public(scope)}}
        hits = self._fts(expr, scope, 500) if expr else []
        beta = _num(params, "beta")
        if hits:
            ids = [i for i, _ in hits]
            self._load_meta(s, ids)
            lo, hi = min(v for _, v in hits), max(v for _, v in hits)
            for rank, (i, v) in enumerate(hits):
                s.pool.add(i)
                s.first_round[i] = 1
                s.via[i].add("bm25")
                nb = (v - lo) / ((hi - lo) or 1.0)
                q = s.meta[i]["quality"]
                q = 0.5 if q is None else q
                s.scores[i] = {"rel": nb, "bm25": v, "rank": rank, "quality": q, "score": (1 - beta) * nb + beta * q,
                               "kw_match": {}}
        ranked = self._ranked(s)
        info = {"round": 1, "pool": len(s.pool), "top": [s.meta[i]["uid"] for i in ranked[:_num(params, "topn", int)]],
                "ms": int((time.time() - s.t0) * 1000), "added": len(s.pool), "judged": 0, "new_keywords": [],
                "seeds": [], "entered": [], "left": []}
        s.trace.append(info)
        yield {"event": "round", "data": info}
        yield {"event": "results", "data": {"round": 1, "results": self._results(s, ranked, params)}}
        yield {"event": "done", "data": self._final(s, {"reason": "exact", "rounds": 1})}

    # ---- results ------------------------------------------------------------------------------

    def _sorted(self, s: Session, ranked: list[int], sort: str) -> list[int]:
        if sort in ("mix", "relevance") or not ranked:
            if sort == "relevance":
                return sorted(s.pool, key=lambda i: (-s.scores[i]["rel"], i))
            return ranked
        head = ranked[:max(50, _num(s.params, "topn", int))]
        if sort == "review":
            return sorted(head, key=lambda i: (-((s.meta[i]["review_stats"] or {}).get("R") or -1),
                                               -s.scores[i]["score"]))
        if sort == "tier":
            return sorted(head, key=lambda i: (-(s.meta[i]["tier"] or 0), -s.scores[i]["score"]))
        if sort == "recent":
            return sorted(head, key=lambda i: (-(s.meta[i]["year"] or 0), -s.scores[i]["score"]))
        return ranked

    def _results(self, s: Session, ranked: list[int], params: dict) -> list[dict]:
        sort = params.get("sort") or "mix"
        order = self._sorted(s, ranked, sort if sort in SORTS else "mix")[: _num(params, "limit", int)]
        self._abstracts(s, order)
        exact = [k.text for k in s.keywords if k.round == 1 or k.origin != "seed"]
        near = [t for k in s.keywords for t in k.synonyms] + [k.text for k in s.keywords if k.origin == "seed"]
        hl = Highlighter(exact, near)
        out = []
        for rank, i in enumerate(order, 1):
            m = s.meta[i]
            sc = s.scores[i]
            j = s.judgments.get(i)
            abstract = m.get("abstract") or ""
            ex_hit, near_hit = hl.matched(f"{m['title']} . {abstract} . {' ; '.join(m['keywords'])}")
            out.append({
                "rank": rank, "id": i, "uid": m["uid"], "title": hl.render(m["title"]), "title_plain": m["title"],
                "authors": m["authors"], "venue": m["venue"], "series": m["series"], "year": m["year"],
                "edition": m["edition_id"], "status": m["status"], "decision_label": m["decision_label"],
                "tier": m["tier"], "track": m["track"], "area": m["area_native"], "keywords": m["keywords"][:8],
                "tldr": m.get("tldr"), "snippet": hl.render(abstract, window=70), "has_abstract": bool(abstract),
                "review": m["review_stats"], "quality": round(sc.get("quality") or 0.0, 4),
                "score": round(sc["score"], 4), "relevance": round(sc["rel"], 4),
                "components": {k: round(v, 4) for k, v in sc.items() if isinstance(v, float)},
                "matched": {"exact": sorted(ex_hit), "near": sorted(near_hit)},
                "hop": s.first_round.get(i, 1), "via": sorted(s.via.get(i, [])),
                "decision": None if j is None else {"source": j.source, "relevance": round(j.relevance, 3),
                                                    "keywords": {k: round(v, 3) for k, v in j.kw.items()},
                                                    "extension": round(j.extension, 3),
                                                    "confidence": round(j.confidence, 3)},
                "links": {"forum": m["forum_url"], "pdf": m["pdf_url"], "proceedings": m["proceedings_url"],
                          "doi": f"https://doi.org/{m['doi']}" if m["doi"] else None},
            })
        return out

    def _scope_public(self, scope: Scope) -> dict:
        return {"editions": len(scope.editions), "statuses": scope.statuses, "min_tier": scope.min_tier,
                "restricted": None if scope.restrict is None else len(scope.restrict)}

    def _final(self, s: Session, converged: dict) -> dict:
        ranked = self._ranked(s) if s.scores else []
        return {
            "query": s.pq.raw, "mode": s.params.get("mode") or "smart", "keywords": [k.public() for k in s.keywords],
            "results": self._results(s, ranked, s.params) if ranked else [], "trace": s.trace,
            "converged": converged | {"stable": converged.get("reason") in ("stable", "exact")},
            "total_candidates": len(s.pool), "elapsed_ms": int((time.time() - s.t0) * 1000),
            "decision": self.svc.decider.status() if s.params.get("mode") != "exact" else None,
            "scope": self._scope_public(s.scope),
        }

