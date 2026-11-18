"""Keyword planning: extraction from the query, synonym and fuzzy expansion, and new keywords
from seed papers between HopLoop rounds."""

from __future__ import annotations

import math
import threading
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import ClassVar

import numpy as np
from rapidfuzz import process
from rapidfuzz.distance import Levenshtein

from confluo_scout.concepts import Vocab, norm_concept
from confluo_scout.search.text import ACRONYM, STOPWORDS, cjk_chunks, stem, words

VALIDATE_KEY = ("Is '{c}' one of the key concepts of this research query, or a term the query clearly refers to "
                "(including a translation, abbreviation or synonym)?")
VALIDATE_SEED = ("Is '{c}' a concept that is directly relevant to this research query and worth searching for to "
                 "find more papers on it?")


@dataclass
class Keyword:
    text: str
    weight: float = 1.0
    round: int = 1
    origin: str = "query"          # query | translation | seed
    source: str | None = None      # Chinese chunk or seed paper uid
    synonyms: list[str] = field(default_factory=list)
    fuzzy: list[str] = field(default_factory=list)

    @property
    def norm(self) -> str:
        return norm_concept(self.text)

    def public(self) -> dict:
        return {"text": self.text, "weight": round(self.weight, 3), "round": self.round, "origin": self.origin,
                "source": self.source, "synonyms": self.synonyms, "fuzzy": self.fuzzy}


class FtsVocab:
    """Document frequency per stemmed FTS term (from the fts5vocab view)."""

    _cache: ClassVar[dict] = {"data": None, "at": 0.0}
    _lock: ClassVar[threading.Lock] = threading.Lock()

    def __init__(self, db, ttl: float = 900):
        with self._lock:
            if self._cache["data"] is None or time.time() - self._cache["at"] > ttl:
                rows = db.query("select term, doc from paper_fts_v")
                n = int(db.scalar("select count(*) from paper") or 1)
                df = {r[0]: r[1] for r in rows}
                frequent = [t for t, d in df.items() if d >= 3 and t.isalpha() and len(t) >= 4]
                self._cache.update(data=(df, n, frequent), at=time.time())
            self.df, self.n, self.frequent = self._cache["data"]

    def idf(self, text: str) -> float:
        toks = [stem(w) for w in words(text) if w.lower() not in STOPWORDS] or [stem(w) for w in words(text)]
        if not toks:
            return 0.0
        vals = [math.log((self.n + 1) / (self.df.get(t, 0) + 1)) for t in toks]
        return sum(vals) / len(vals) + 0.15 * (len(toks) - 1)

    def doc_freq(self, text: str) -> int:
        """Upper bound of the number of papers containing the phrase (min over its tokens)."""
        toks = [stem(w) for w in words(text)]
        return min((self.df.get(t, 0) for t in toks), default=0)

    def exists(self, text: str) -> bool:
        return all(self.df.get(stem(w), 0) > 0 for w in words(text))

    def near_terms(self, word: str, limit: int = 3) -> list[str]:
        s = stem(word)
        if len(s) < 5 or (s in self.df and self.df[s] >= 20):
            return []
        hits = process.extract(s, self.frequent, scorer=Levenshtein.distance, score_cutoff=2 if len(s) >= 7 else 1,
                               limit=limit + 1)
        return [h[0] for h in hits if h[0] != s][:limit]


class Background:
    """A random sample of concept vectors: turns compressed term similarities into z-scores."""

    _cache: ClassVar[dict] = {"vecs": None, "at": 0.0}
    _lock: ClassVar[threading.Lock] = threading.Lock()

    def __init__(self, svc, size: int = 512, ttl: float = 3600):
        with self._lock:
            if self._cache["vecs"] is None or time.time() - self._cache["at"] > ttl:
                pts, _ = svc.vectors.client.scroll("concepts", limit=size, with_vectors=True, with_payload=False)
                vecs = np.asarray([p.vector for p in pts if p.vector is not None], dtype=np.float32)
                self._cache.update(vecs=vecs if len(vecs) else None, at=time.time())
            self.vecs = self._cache["vecs"]

    def z(self, anchor: np.ndarray, sims: np.ndarray) -> np.ndarray:
        if self.vecs is None or not len(self.vecs):
            return (sims - 0.8) / 0.03
        bg = self.vecs @ anchor
        return (sims - float(bg.mean())) / max(1e-6, float(bg.std()))


class KeywordPlanner:
    def __init__(self, svc, vocab: Vocab, decider, fts: FtsVocab):
        self.svc = svc
        self.vocab = vocab
        self.decider = decider
        self.fts = fts
        self.bg = Background(svc)
        self.query_term: np.ndarray | None = None

    # ---- extraction -------------------------------------------------------------------------

    def extract(self, pq, query_term_vec: np.ndarray | None, max_kw: int = 6) -> list[Keyword]:
        self.query_term = query_term_vec
        cands: list[tuple[str, float, str, str | None]] = []  # text, score, origin, source
        for ph in pq.phrases:
            cands.append((ph, 99.0, "query", None))
        text = pq.plain
        for ph in pq.phrases:
            text = text.replace(ph, " ")
        if pq.cjk:
            cands += self._from_chinese(text, query_term_vec)
            ascii_part = " ".join(w for w in words(text) if w.isascii())
            cands += self._from_english(ascii_part)
        else:
            cands += self._from_english(text)
        # Deduplicate by normalized form; keep the best score.
        best: dict[str, tuple[str, float, str, str | None]] = {}
        order: list[str] = []
        for t, s, o, src in cands:
            key = norm_concept(t)
            if not key or key in STOPWORDS:
                continue
            if key not in best:
                order.append(key)
                best[key] = (t, s, o, src)
            elif s > best[key][1]:
                best[key] = (t, s, o, src)
        ranked = sorted(order, key=lambda k: -best[k][1])
        if self.decider.remote and len(ranked) > 1:
            probs = self.decider.validate(pq.plain, [best[k][0] for k in ranked[:20]], VALIDATE_KEY)
            if probs:
                keep = [k for k in ranked[:20] if probs.get(best[k][0], 0.0) >= 0.5 or best[k][1] >= 99]
                ranked = keep or ranked[:max_kw]
        if pq.cjk:
            max_kw = max(max_kw, 8)
        # Drop whole-query neighbours that only extend an already chosen keyword ("llm" -> "llm fine-tuning").
        pruned: list[str] = []
        for k in ranked:
            if best[k][3] is None and best[k][2] == "translation" and any(p in k for p in pruned):
                continue
            pruned.append(k)
        chosen = pruned[:max_kw]
        chosen.sort(key=lambda k: order.index(k))
        return [Keyword(text=best[k][0], weight=1.0, round=1, origin=best[k][2], source=best[k][3]) for k in chosen]

    def _from_english(self, text: str) -> list[tuple[str, float, str, str | None]]:
        toks = words(text)
        out = []
        chunk: list[str] = []
        chunks: list[list[str]] = []
        for w in [*toks, "the"]:
            if w.lower() in STOPWORDS:
                if chunk:
                    chunks.append(chunk)
                chunk = []
            else:
                chunk.append(w)
        for ch in chunks:
            i = 0
            while i < len(ch):
                matched = None
                for n in range(min(self.vocab.max_len, len(ch) - i), 1, -1):
                    span = " ".join(ch[i:i + n])
                    if self.vocab.get(span):
                        matched = (span, n)
                        break
                if matched:
                    span, n = matched
                    out.append((span, self.fts.idf(span) * 1.5 + 0.5 * n, "query", None))
                    i += n
                    continue
                w = ch[i]
                if len(w) >= 2 and not w.isdigit():
                    bonus = 1.2 if ACRONYM.match(w) else (1.3 if self.vocab.get(w) else 1.0)
                    out.append((w, self.fts.idf(w) * bonus, "query", None))
                i += 1
            if 2 <= len(ch) <= 4 and not self.vocab.get(" ".join(ch)) and self.fts.exists(" ".join(ch)):
                out.append((" ".join(ch), self.fts.idf(" ".join(ch)) * 1.1, "query", None))
        return out

    def _from_chinese(self, text: str, qvec: np.ndarray | None) -> list[tuple[str, float, str, str | None]]:
        chunks = [c for c in cjk_chunks(text) if not c.isascii()]
        if not chunks and qvec is None:
            return []
        out = []
        emb = self.svc.embedder
        vecs = emb.terms(chunks) if chunks else np.zeros((0, emb.dim), dtype=np.float32)
        queries = list(vecs) + ([qvec] if qvec is not None else [])
        hits = self.svc.vectors.search_concepts(np.asarray(queries), limit=10)
        for ci, chunk in enumerate(chunks):
            cand = [(p["term"], s, p.get("df") or self._df(p["term"])) for _, s, p in hits[ci]
                    if p.get("term") and (p.get("df") or 0) > 0]
            if not cand:
                continue
            z = self.bg.z(vecs[ci], np.asarray([s for _, s, _ in cand]))
            best = max(s for _, s, _ in cand)
            # Near-ties go to the more common (canonical) spelling.
            near = [(t, s, df, zz) for (t, s, df), zz in zip(cand, z, strict=True) if s >= best - 0.012 and zz >= 3.0]
            near.sort(key=lambda x: (-(x[1] + 0.004 * math.log1p(x[2]))))
            kept: list[str] = []
            for t, _s, _df, zz in near:
                if any(Levenshtein.distance(t, k) <= 2 for k in kept):
                    continue  # spelling variant of a more common term
                kept.append(t)
                out.append((t, 9.0 + float(zz) / 2, "translation", chunk))
                if len(kept) == 2:
                    break
        if qvec is not None:
            cand = [(p["term"], s) for _, s, p in hits[-1] if p.get("term") and (p.get("df") or 0) > 0]
            if cand:
                z = self.bg.z(qvec, np.asarray([s for _, s in cand]))
                for (t, _s), zz in zip(cand[:3], z[:3], strict=True):
                    if zz >= 3.5:
                        out.append((t, 8.0 + float(zz) / 2, "translation", None))
        return out

    def _df(self, term: str) -> int:
        e = self.vocab.get(term)
        return int(e["df"]) if e else 0

    # ---- expansion --------------------------------------------------------------------------

    def expand(self, kws: list[Keyword], neighbors: bool = True) -> None:
        todo = [k for k in kws if not k.synonyms and not k.fuzzy]
        if not todo:
            return
        for k in todo:
            e = self.vocab.get(k.text)
            syn = list(e["aliases"]) if e else []
            if not e and ACRONYM.match(k.text):
                e2 = self.vocab.get(k.text.lower())
                syn = list(e2["aliases"]) if e2 else []
            k.synonyms = [s for s in syn if norm_concept(s) != k.norm][:4]
            if len(words(k.text)) == 1 and not ACRONYM.match(k.text):
                k.fuzzy = self.fts.near_terms(k.text)
        if not neighbors:
            return
        vecs = self.svc.embedder.terms([k.text for k in todo])
        hits = self.svc.vectors.search_concepts(vecs, limit=8)
        remote = self.decider.remote
        for k, hs in zip(todo, hits, strict=True):
            raw = [(p.get("term"), s) for _, s, p in hs if p.get("term")]
            raw = [(t, s) for t, s in raw if norm_concept(t) != k.norm and t not in k.synonyms
                   and s >= (0.85 if remote else 0.93)]
            if raw and self.query_term is not None and not remote:
                tv = self.svc.embedder.terms([t for t, _ in raw])
                zq = self.bg.z(self.query_term, tv @ self.query_term)
                raw = [(t, s) for (t, s), z in zip(raw, zq, strict=True) if z >= 3.0]
            cands = [t for t, _ in raw]
            if cands and remote:
                probs = self.decider.validate(
                    k.text, cands, "Is '{c}' a synonym, an abbreviation or an equivalent name of the concept "
                                   f"'{k.text}' in AI research?")
                if probs:
                    cands = [c for c in cands if probs.get(c, 0) >= 0.5]
            k.synonyms += cands[: max(0, 4 - len(k.synonyms))]

    # ---- seeds ------------------------------------------------------------------------------

    def from_seeds(self, query: str, seeds: list[dict], existing: list[Keyword], round_no: int, max_new: int,
                   pool_scores: dict[int, float], top_ids: list[int], match_set) -> list[Keyword]:
        """New keywords from the top papers, kept only when papers containing them rank above the pool
        average (relevance-model lift), several top papers share them and they are not generic."""
        known = {k.norm for k in existing} | {norm_concept(s) for k in existing for s in k.synonyms}
        sal: Counter = Counter()
        src_of: dict[str, str] = {}
        n_docs = max(1, self.fts.n)
        for s in seeds:
            weight = float(s.get("score", 1.0))
            text = f"{s.get('title_plain', '')}. {s.get('abstract', '')}"
            toks = [w.lower() for w in words(text)]
            tf: Counter = Counter()
            for n in range(1, min(4, self.vocab.max_len) + 1):
                for i in range(len(toks) - n + 1):
                    gram = " ".join(toks[i:i + n])
                    if n == 1 and (gram in STOPWORDS or len(gram) < 4):
                        continue
                    e = self.vocab.by_term.get(gram)
                    # Single title words only help translation; expansion needs phrases, author keywords or acronyms.
                    if e and e["kind"] not in ("area", "word") and e["df"] >= 3:
                        tf[gram] += 1
            for kw in s.get("keywords") or []:
                tf[norm_concept(kw)] += 2
            for gram, c in tf.items():
                if gram in known or any(gram in k or k in gram for k in known if len(k) > 3):
                    continue
                if " " not in gram and len(gram) < 5 and (self.vocab.by_term.get(gram) or {}).get("kind") != "acronym":
                    continue
                sal[gram] += weight * (1 + math.log(c))
                src_of.setdefault(gram, s.get("uid"))
        if not sal or not pool_scores:
            return []
        pool = set(pool_scores)
        top = set(top_ids)
        base = sum(pool_scores.values()) / len(pool_scores)
        scored = []
        for gram, _ in sal.most_common(40):
            if any(len(t) < 2 for t in gram.split()):
                continue
            df = self.fts.doc_freq(gram) or 1
            single = " " not in gram
            if df / n_docs > (0.01 if single else 0.05):
                continue
            ph = '"' + " ".join(words(gram)).replace('"', '""') + '"'
            hits = match_set(ph, pool)
            support = len(hits & top)
            if support < 2:
                continue
            lift = sum(pool_scores[i] for i in hits) / len(hits) - base
            if lift <= (0.06 if single else 0.03):
                continue
            scored.append((gram, lift * math.log1p(support) * math.log((n_docs + 1) / (df + 1)), lift, support))
        scored.sort(key=lambda x: -x[1])
        picked = [g for g, *_ in scored[: max_new * 3]]
        if picked and self.decider.remote:
            probs = self.decider.validate(query, picked, VALIDATE_SEED)
            if probs:
                picked = [g for g in picked if probs.get(g, 0) >= 0.5]
        info = {g: (lift, support) for g, _, lift, support in scored}
        out = []
        for g in picked[:max_new]:
            e = self.vocab.by_term.get(g)
            lift, support = info[g]
            out.append(Keyword(text=g, weight=round(0.7 ** round_no * min(1.0, 0.5 + lift / 0.2), 4),
                               round=round_no + 1, origin="seed", source=src_of.get(g),
                               synonyms=list(e["aliases"])[:3] if e else []))
        return out
