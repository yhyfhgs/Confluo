"""Decision model: Gemini Decisions API (gemini-decision-1), with a local fallback.

Gemini Decision 1 is a "System One" model (the Jev class): one forward pass scores typed questions
(noul = yes/no, choice, score = ordered rubric) and returns calibrated probabilities with zero
output tokens (Google AI Studio docs, checked 2026-11-19: v1beta, google-genai >= 3.2,
`client.decisions.create`, up to 1,000 questions and 262,144 tokens per request, $0.10 per 1M
input tokens, no batch API or context caching). Scout asks one request per candidate paper:
a relevance rubric, one coverage question per query keyword and one "logical extension" question.
"""

from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field

from confluo_scout.db import Database, dumps, loads, utcnow
from confluo_scout.records import sha1

log = logging.getLogger("scout.decision")

RELEVANCE_LEVELS = [
    "Unrelated: the paper does not address the research query.",
    "Same broad field only: it shares the general area but not the specific topic.",
    "Partially relevant: it addresses one important aspect of the query.",
    "Relevant: it addresses the core topic of the query.",
    "Highly relevant: it directly answers the query or is a central reference for it.",
]
EXTENSION_Q = ("Would a researcher investigating the research query need this paper as a logical extension of it, "
               "for example a method, setting, evaluation or finding that the query's topic directly builds on or "
               "leads to, even if the paper uses different wording?")


@dataclass
class Judgment:
    relevance: float                      # expected rubric level, 0..4
    kw: dict[str, float] = field(default_factory=dict)
    extension: float = 0.5
    confidence: float = 0.5
    source: str = "local"
    rel_probs: dict[str, float] = field(default_factory=dict)

    @property
    def value(self) -> float:
        kw = sum(self.kw.values()) / len(self.kw) if self.kw else self.relevance / 4
        return 0.6 * self.relevance / 4 + 0.25 * kw + 0.15 * self.extension


def paper_card(query: str, keywords: list[str], p: dict, max_abstract: int = 2200) -> str:
    venue = p.get("venue") or ""
    if p.get("decision_label"):
        venue += f" ({p['decision_label']})"
    kw = "; ".join((p.get("keywords") or [])[:10])
    abstract = (p.get("abstract") or "")[:max_abstract]
    return (f"Research query: {query}\nKey concepts: {'; '.join(keywords)}\n\nCandidate paper\n"
            f"Title: {p.get('title_plain') or p.get('title')}\nVenue: {venue}\n"
            + (f"Keywords: {kw}\n" if kw else "") + f"Abstract: {abstract}\n")


class LocalDecider:
    """Approximates the decision questions from retrieval features. Marked as local in results."""

    name = "local"
    remote = False

    def status(self) -> dict:
        return {"model": "local", "available": True, "remote": False}

    def judge(self, query: str, keywords: list[str], papers: list[dict]) -> dict[int, Judgment]:
        out = {}
        for p in papers:
            cos = float(p.get("cos") or 0.0)
            cov = float(p.get("coverage") or 0.0)
            rel = 4.0 * (0.6 * min(1.0, max(0.0, (cos - 0.30) / 0.40)) + 0.4 * cov)
            kw = {}
            for k in keywords:
                m = (p.get("kw_match") or {}).get(k, 0.0)
                kw[k] = 0.9 if m >= 1 else 0.7 if m >= 0.6 else 0.45 if m >= 0.3 else 0.1
            out[p["id"]] = Judgment(relevance=round(rel, 3), kw=kw, extension=float(p.get("ppr_norm") or 0.0),
                                    confidence=0.5, source="local")
        return out

    def validate(self, query: str, candidates: list[str], instruction: str) -> dict[str, float]:
        return {}


class GeminiDecider:
    name = "gemini"
    remote = True

    def __init__(self, db: Database, api_key: str, model: str = "gemini-decision-1", workers: int = 8):
        from google import genai

        self.db = db
        self.model = model
        self.client = genai.Client(api_key=api_key, http_options={"api_version": "v1beta"})
        self.pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="decision")
        self.local = LocalDecider()
        self.cooldown_until = 0.0
        self.last_error: str | None = None
        self.calls = 0
        self.input_tokens = 0
        self._lock = threading.Lock()

    def status(self) -> dict:
        return {"model": self.model, "available": time.time() >= self.cooldown_until, "remote": True,
                "calls": self.calls, "input_tokens": self.input_tokens, "last_error": self.last_error}

    # ---- low level ----------------------------------------------------------------------------

    def _create(self, input_text: str, questions: dict) -> dict:
        res = self.client.decisions.create(model=self.model, input=input_text, questions=questions)
        answers = {}
        for key, ans in (res.answers or {}).items():
            a = ans.model_dump() if hasattr(ans, "model_dump") else dict(ans)
            answers[key] = a
        usage = getattr(res, "usage", None)
        tokens = getattr(usage, "total_input_tokens", None) if usage is not None else None
        with self._lock:
            self.calls += 1
            self.input_tokens += int(tokens or 0)
        return answers

    def _fail(self, exc: Exception) -> None:
        msg = f"{type(exc).__name__}: {exc}"
        self.last_error = msg[:300]
        status = getattr(exc, "code", None) or getattr(exc, "status_code", None)
        cool = 120 if status in (429, 500, 502, 503, 504, None) else 600
        self.cooldown_until = time.time() + cool
        log.warning("decision model unavailable for %ss: %s", cool, self.last_error)

    def _cache_get(self, key: str) -> dict | None:
        raw = self.db.scalar("select value from decision_cache where key=?", (key,))
        return loads(raw, None) if raw else None

    def _cache_put(self, key: str, value: dict) -> None:
        with self.db.tx() as con:
            con.execute("insert into decision_cache(key, value, created_at) values(?,?,?) "
                        "on conflict(key) do update set value=excluded.value, created_at=excluded.created_at",
                        (key, dumps(value), utcnow()))

    # ---- public ---------------------------------------------------------------------------------

    def judge(self, query: str, keywords: list[str], papers: list[dict]) -> dict[int, Judgment]:
        kws = keywords[:6]
        out: dict[int, Judgment] = {}
        todo = []
        for p in papers:
            key = sha1("|".join([self.model, query.strip().lower(), ";".join(sorted(k.lower() for k in kws)),
                                 p["uid"], p.get("content_hash") or ""]))
            hit = self._cache_get(key)
            if hit:
                out[p["id"]] = Judgment(**hit)
            else:
                todo.append((key, p))
        if todo and time.time() >= self.cooldown_until:
            questions = {"relevance": {"type": "score", "instructions": "How relevant is the candidate paper to the "
                                       "research query?", "criteria": RELEVANCE_LEVELS},
                         "extension": {"type": "noul", "instructions": EXTENSION_Q}}
            for i, k in enumerate(kws):
                questions[f"kw_{i}"] = {"type": "noul", "instructions": f"Does the candidate paper substantively "
                                        f"address the concept '{k}' (more than a passing mention)?"}

            def run(item):
                key, p = item
                if time.time() < self.cooldown_until:
                    return None
                try:
                    ans = self._create(paper_card(query, kws, p), questions)
                except Exception as exc:
                    self._fail(exc)
                    return None
                rel = ans.get("relevance", {})
                confs = [float(a.get("confidence", 0.5)) for a in ans.values()]
                j = Judgment(relevance=float(rel.get("score", 0.0)),
                             kw={k: float(ans.get(f"kw_{i}", {}).get("noul", 0.5)) for i, k in enumerate(kws)},
                             extension=float(ans.get("extension", {}).get("noul", 0.5)),
                             confidence=sum(confs) / len(confs) if confs else 0.5, source=self.model,
                             rel_probs={str(k): float(v) for k, v in (rel.get("probabilities") or {}).items()})
                self._cache_put(key, asdict(j))
                return p["id"], j

            for res in self.pool.map(run, todo):
                if res:
                    out[res[0]] = res[1]
        missing = [p for p in papers if p["id"] not in out]
        if missing:
            out.update(self.local.judge(query, kws, missing))
        return out

    def validate(self, query: str, candidates: list[str], instruction: str) -> dict[str, float]:
        """One request: P(yes) per candidate concept for an instruction with a {c} placeholder."""
        if not candidates or time.time() < self.cooldown_until:
            return {}
        key = sha1("|".join([self.model, "validate", instruction, query.strip().lower(), ";".join(candidates)]))
        hit = self._cache_get(key)
        if hit:
            return hit
        questions = {f"c{i}": {"type": "noul", "instructions": instruction.format(c=c)}
                     for i, c in enumerate(candidates[:200])}
        try:
            ans = self._create(f"Research query: {query}", questions)
        except Exception as exc:
            self._fail(exc)
            return {}
        out = {c: float(ans.get(f"c{i}", {}).get("noul", 0.0)) for i, c in enumerate(candidates[:200])}
        self._cache_put(key, out)
        return out


def build_decider(db: Database, secrets, model: str):
    if secrets.has_gemini:
        try:
            return GeminiDecider(db, secrets.gemini_api_key, model)
        except Exception as exc:
            log.warning("Gemini client unavailable (%s); using local scoring", exc)
    return LocalDecider()
