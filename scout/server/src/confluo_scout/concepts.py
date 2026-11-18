"""Concept vocabulary mined from the corpus.

Sources: author keywords, native areas (OpenReview primary areas, AAAI tracks, IJCAI areas),
frequent 2-4 word title phrases, and acronym definitions found in abstracts with the
Schwartz-Hearst rule ("large language models (LLMs)"), plus a small built-in seed list.
Each concept gets a vector in the qdrant `concepts` collection (sentence-similarity prompt) for
synonym expansion and for mapping Chinese query chunks to English search terms.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from collections import Counter, defaultdict

from confluo_scout.db import dumps, loads
from confluo_scout.search.text import STOPWORDS, fold, words

log = logging.getLogger("scout.concepts")

SEED_ACRONYMS = {
    "llm": ["large language model"], "llms": ["large language models"], "vlm": ["vision language model"],
    "mllm": ["multimodal large language model"], "lmm": ["large multimodal model"], "rl": ["reinforcement learning"],
    "rlhf": ["reinforcement learning from human feedback"], "dpo": ["direct preference optimization"],
    "ppo": ["proximal policy optimization"], "gnn": ["graph neural network"], "gcn": ["graph convolutional network"],
    "gan": ["generative adversarial network"], "vae": ["variational autoencoder"], "vit": ["vision transformer"],
    "cnn": ["convolutional neural network"], "rnn": ["recurrent neural network"], "lstm": ["long short-term memory"],
    "nlp": ["natural language processing"], "asr": ["automatic speech recognition"], "tts": ["text to speech"],
    "nerf": ["neural radiance field"], "3dgs": ["3d gaussian splatting"], "moe": ["mixture of experts"],
    "rag": ["retrieval augmented generation"], "cot": ["chain of thought"], "icl": ["in context learning"],
    "sft": ["supervised fine tuning"], "peft": ["parameter efficient fine tuning"], "lora": ["low rank adaptation"],
    "kd": ["knowledge distillation"], "ood": ["out of distribution"], "ssl": ["self supervised learning"],
    "marl": ["multi agent reinforcement learning"], "irl": ["inverse reinforcement learning"],
    "mpc": ["model predictive control"], "slam": ["simultaneous localization and mapping"],
    "vqa": ["visual question answering"], "ocr": ["optical character recognition"], "ner": ["named entity recognition"],
    "kg": ["knowledge graph"], "sde": ["stochastic differential equation"], "ode": ["ordinary differential equation"],
    "pinn": ["physics informed neural network"], "mdp": ["markov decision process"],
    "pomdp": ["partially observable markov decision process"], "sgd": ["stochastic gradient descent"],
    "ntk": ["neural tangent kernel"], "gp": ["gaussian process"], "bo": ["bayesian optimization"],
    "nas": ["neural architecture search"], "fl": ["federated learning"], "dp": ["differential privacy"],
    "xai": ["explainable artificial intelligence"], "sae": ["sparse autoencoder"], "prm": ["process reward model"],
    "orm": ["outcome reward model"], "grpo": ["group relative policy optimization"], "mcts": ["monte carlo tree search"],
    "vla": ["vision language action model"], "ddpm": ["denoising diffusion probabilistic model"],
    "kv cache": ["key value cache"], "ssm": ["state space model"], "cl": ["continual learning", "contrastive learning"],
}


def norm_concept(text: str) -> str:
    t = fold(text).strip().strip(".;:,")
    # Hyphens separate tokens in the FTS index too: "in-context learning" == "in context learning".
    t = re.sub(r"[\s_\-‐–]+", " ", t)
    return t.strip()


_PAREN = re.compile(r"\(([A-Za-z][A-Za-z0-9\-]{1,9}s?)\)")


def mine_acronyms(text: str) -> list[tuple[str, str]]:
    """Schwartz-Hearst style: 'long form (LF)' -> ('lf', 'long form')."""
    out = []
    for m in _PAREN.finditer(text):
        short = m.group(1)
        if sum(1 for c in short if c.isupper()) < 2 and not re.match(r"^[A-Z][a-z]+[A-Z]", short):
            continue
        core = short[:-1] if short.endswith("s") and short[:-1].isupper() else short
        letters = [c.lower() for c in core if c.isalpha()]
        if len(letters) < 2:
            continue
        before = words(text[max(0, m.start() - 160):m.start()])
        n = min(len(before), len(letters) + 3)
        cand = before[-n:]
        # Find the shortest suffix of words whose initials cover the acronym letters in order.
        best = None
        for start in range(len(cand) - 1, -1, -1):
            phrase = cand[start:]
            initials = "".join(w[0].lower() for w in phrase if w)
            joined = "".join(w.lower() for w in phrase)
            if initials == "".join(letters) or (phrase and phrase[0][0].lower() == letters[0]
                                                and _subseq("".join(letters), joined) and len(phrase) <= len(letters) + 1):
                best = phrase
                if initials == "".join(letters):
                    break
        if best and 2 <= len(best) <= 8:
            long_form = " ".join(best).lower()
            if long_form.split()[0] not in STOPWORDS:
                out.append((core.lower(), long_form))
    return out


def _subseq(needle: str, hay: str) -> bool:
    it = iter(hay)
    return all(c in it for c in needle)


class ConceptBuilder:
    def __init__(self, svc):
        self.svc = svc

    def rebuild(self, embed: bool = True, min_kw_df: int = 2, min_phrase_df: int = 5, min_acr: int = 3,
                embedder=None) -> dict:
        t0 = time.time()
        db = self.svc.db
        df: Counter = Counter()
        kind: dict[str, str] = {}
        aliases: dict[str, set[str]] = defaultdict(set)
        display: dict[str, str] = {}

        rows = db.query("select id, edition_id, title, keywords, area_native, area_secondary, abstract_gen, "
                        "abstract_part, abstract_line from paper where status in ('accepted','under_review')")
        phrase_df: Counter = Counter()
        acr_pairs: Counter = Counter()
        for r in rows:
            seen: set[str] = set()
            for k in loads(r["keywords"], []) or []:
                c = norm_concept(k)
                if 2 <= len(c) <= 80 and c not in seen:
                    seen.add(c)
                    df[c] += 1
                    kind.setdefault(c, "keyword")
                    display.setdefault(c, k.strip())
            for a in (r["area_native"], r["area_secondary"]):
                if a:
                    c = norm_concept(a)
                    if c and c not in seen:
                        seen.add(c)
                        df[c] += 1
                        kind[c] = "area"
                        display.setdefault(c, a.strip())
            toks = [w.lower() for w in words(r["title"])]
            grams = set()
            for n in (1, 2, 3, 4):
                for i in range(len(toks) - n + 1):
                    g = toks[i:i + n]
                    if g[0] in STOPWORDS or g[-1] in STOPWORDS or any(t.isdigit() for t in g):
                        continue
                    if n == 1 and (len(g[0]) < 3 or not g[0].isalpha()):
                        continue
                    grams.add(" ".join(g))
            for g in grams:
                phrase_df[g] += 1
        # Acronyms from abstracts (one pass over the shards).
        texts = self.svc.store.abstracts_for(rows)
        for text in texts.values():
            for short, long_form in set(mine_acronyms(text)):
                acr_pairs[(short, long_form)] += 1
        for g, n in phrase_df.items():
            single = " " not in g
            if n >= (10 if single else min_phrase_df) and g not in df:
                df[g] = n
                kind[g] = "word" if single else "phrase"
                display[g] = g
        keep = {c for c, n in df.items() if n >= min_kw_df or kind.get(c) == "area"}
        for (short, long_form), n in acr_pairs.items():
            if n < min_acr:
                continue
            lf = norm_concept(long_form)
            aliases[short].add(lf)
            aliases[lf].add(short)
            for c, k in ((short, "acronym"), (lf, kind.get(lf, "phrase"))):
                if c not in keep:
                    keep.add(c)
                    df[c] = max(df[c], n)
                    kind[c] = k
                    display.setdefault(c, c.upper() if k == "acronym" else c)
        for short, longs in SEED_ACRONYMS.items():
            for lf in longs:
                aliases[short].add(lf)
                aliases[lf].add(short)
                for c, k in ((short, "acronym"), (lf, "phrase")):
                    if c not in keep:
                        keep.add(c)
                        df[c] = max(df[c], 1)
                        kind[c] = k
                        display.setdefault(c, c.upper() if k == "acronym" else c)

        with db.tx() as con:
            existing = {r[0]: r[1] for r in con.execute("select term, id from concept")}
            for c in keep:
                al = sorted(aliases.get(c, set()) - {c})
                if c in existing:
                    con.execute("update concept set df=?, kind=?, aliases=? where id=?",
                                (df[c], kind.get(c, "keyword"), dumps(al), existing[c]))
                else:
                    con.execute("insert into concept(term, kind, df, aliases, embedded) values(?,?,?,?,0)",
                                (c, kind.get(c, "keyword"), df[c], dumps(al)))
            stale = set(existing) - keep
            for c in stale:
                con.execute("update concept set df=0 where id=?", (existing[c],))
        embedded = self.embed_new(embedder=embedder) if embed else 0
        get_vocab(self.svc, refresh=True)
        stats = {"concepts": len(keep), "acronym_pairs": sum(1 for v in acr_pairs.values() if v >= min_acr),
                 "embedded": embedded, "seconds": round(time.time() - t0, 1)}
        log.info("concept vocabulary rebuilt: %s", stats)
        return stats

    def embed_new(self, batch: int = 512, embedder=None) -> int:
        db = self.svc.db
        embedder = embedder or self.svc.embedder
        total = 0
        while True:
            rows = db.query("select id, term, kind, df from concept where embedded=0 and df>0 limit ?", (batch,))
            if not rows:
                break
            vecs = embedder.terms([r["term"] for r in rows])
            self.svc.vectors.upsert_concepts([r["id"] for r in rows], vecs,
                                             [{"term": r["term"], "kind": r["kind"], "df": r["df"]} for r in rows])
            with db.tx() as con:
                con.executemany("update concept set embedded=1 where id=?", [(r["id"],) for r in rows])
            total += len(rows)
        return total


class Vocab:
    """In-memory view of the concept table for fast lookups during search."""

    def __init__(self, rows):
        self.by_term: dict[str, dict] = {}
        self.max_len = 1
        for r in rows:
            entry = {"id": r["id"], "term": r["term"], "kind": r["kind"], "df": r["df"],
                     "aliases": loads(r["aliases"], []) or []}
            self.by_term[r["term"]] = entry
            self.max_len = max(self.max_len, len(r["term"].split()))
        self.loaded_at = time.time()

    def get(self, term: str) -> dict | None:
        return self.by_term.get(norm_concept(term))

    def __len__(self) -> int:
        return len(self.by_term)


_VOCAB: dict = {"vocab": None}
_VOCAB_LOCK = threading.Lock()


def get_vocab(svc, refresh: bool = False, ttl: float = 600) -> Vocab:
    with _VOCAB_LOCK:
        v = _VOCAB["vocab"]
        if v is None or refresh or time.time() - v.loaded_at > ttl:
            v = Vocab(svc.db.query("select id, term, kind, df, aliases from concept where df>0"))
            _VOCAB["vocab"] = v
        return v
