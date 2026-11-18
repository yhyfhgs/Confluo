"""Query parsing shared by smart and exact mode.

Syntax: "phrase", -exclude, venue:iclr | venue:iclr-2026, year:2025 | year:2024..2026 | year:>=2025,
author:"Name", status:oral|spotlight|highlight|poster|findings|accepted|review|rejected,
area:"reinforcement learning", and in exact mode AND / OR / NOT, word* (prefix), title:... abstract:...
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from confluo_scout.search.text import fts_phrase, is_cjk, words

FIELD_RE = re.compile(r'(?<![\w"])(?P<neg>-)?(?P<field>venue|conf|year|author|status|label|area|title|abstract)'
                      r':(?P<val>"[^"]*"|\S+)', re.I)
LABELS = {"oral": 4, "spotlight": 3, "highlight": 3, "poster": 2, "findings": 1}
STATUS_ALIASES = {"accepted": "accepted", "accept": "accepted", "review": "under_review", "reviewing": "under_review",
                  "under_review": "under_review", "submitted": "under_review", "rejected": "rejected",
                  "reject": "rejected", "withdrawn": "withdrawn"}


@dataclass
class ParsedQuery:
    raw: str
    text: str = ""
    plain: str = ""
    phrases: list[str] = field(default_factory=list)
    excludes: list[str] = field(default_factory=list)
    venues: list[str] = field(default_factory=list)
    years: tuple[int, int] | None = None
    authors: list[str] = field(default_factory=list)
    labels: list[str] = field(default_factory=list)
    statuses: list[str] = field(default_factory=list)
    areas: list[str] = field(default_factory=list)
    columns: list[tuple[str, str]] = field(default_factory=list)
    has_ops: bool = False
    cjk: bool = False

    @property
    def min_tier(self) -> int | None:
        tiers = [LABELS[x] for x in self.labels if x in LABELS]
        return min(tiers) if tiers else None


def _unquote(v: str) -> str:
    return v[1:-1] if len(v) >= 2 and v[0] == v[-1] == '"' else v


def _years(val: str) -> tuple[int, int] | None:
    v = val.strip()
    m = re.fullmatch(r"(\d{4})\s*(?:\.\.|-|–|~)\s*(\d{4})", v)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        return (min(a, b), max(a, b))
    m = re.fullmatch(r"(>=|>|<=|<)?(\d{4})", v)
    if m:
        op, y = m.group(1), int(m.group(2))
        if op in (">=", None) and op:
            return (y, 9999)
        if op == ">":
            return (y + 1, 9999)
        if op == "<=":
            return (0, y)
        if op == "<":
            return (0, y - 1)
        return (y, y)
    return None


def parse_query(raw: str) -> ParsedQuery:
    pq = ParsedQuery(raw=raw.strip())
    rest = pq.raw
    for m in list(FIELD_RE.finditer(rest)):
        fld, val, neg = m.group("field").lower(), _unquote(m.group("val")), bool(m.group("neg"))
        if fld in ("venue", "conf"):
            pq.venues += [v.strip().lower() for v in val.split(",") if v.strip()]
        elif fld == "year":
            pq.years = _years(val) or pq.years
        elif fld == "author":
            pq.authors.append(val)
        elif fld in ("status", "label"):
            for v in val.lower().split(","):
                v = v.strip()
                if v in LABELS:
                    pq.labels.append(v)
                elif v in STATUS_ALIASES:
                    pq.statuses.append(STATUS_ALIASES[v])
        elif fld == "area":
            pq.areas.append(val)
        elif fld in ("title", "abstract"):
            if neg:
                pq.excludes.append(val)
            else:
                pq.columns.append((fld, val))
        rest = rest.replace(m.group(0), " ")
    pq.text = re.sub(r"\s+", " ", rest).strip()
    for m in re.finditer(r'(?<![\w])(-)?"([^"]+)"', pq.text):
        (pq.excludes if m.group(1) else pq.phrases).append(m.group(2).strip())
    for m in re.finditer(r"(?:(?<=\s)|^)-([^\s\"]+)", pq.text):
        pq.excludes.append(m.group(1))
    pq.has_ops = bool(re.search(r"(^|\s)(AND|OR|NOT)(\s|$)|\*|\(|\)", pq.text)) or bool(pq.columns)
    plain = re.sub(r'(?:(?<=\s)|^)-("[^"]+"|\S+)', " ", pq.text)
    plain = re.sub(r"(^|\s)(AND|OR|NOT)(?=\s|$)", " ", plain)
    plain = plain.replace('"', " ").replace("*", " ").replace("(", " ").replace(")", " ")
    pq.plain = re.sub(r"\s+", " ", plain).strip()
    pq.cjk = is_cjk(pq.plain)
    return pq


def exact_expression(pq: ParsedQuery) -> str | None:
    """Compile the free text into an FTS5 MATCH expression (implicit AND)."""
    tokens = re.findall(r'-?"[^"]+"|\(|\)|[^\s()]+', pq.text)
    parts: list[str] = []
    depth = 0
    for tok in tokens:
        if tok in ("AND", "OR", "NOT"):
            if parts and parts[-1] not in ("AND", "OR", "NOT", "("):
                parts.append(tok)
            continue
        if tok == "(":
            if parts and parts[-1] not in ("AND", "OR", "NOT", "("):
                parts.append("AND")
            parts.append("(")
            depth += 1
            continue
        if tok == ")":
            if depth > 0 and parts and parts[-1] != "(":
                while parts and parts[-1] in ("AND", "OR", "NOT"):
                    parts.pop()
                parts.append(")")
                depth -= 1
            continue
        if tok.startswith("-"):
            continue  # exclusions are added at the end
        if tok.startswith('"'):
            ph = fts_phrase(tok.strip('"'))
        elif tok.endswith("*") and len(tok) > 1:
            ws = words(tok[:-1])
            ph = (fts_phrase(" ".join(ws)) + "*") if ws else None
        else:
            ph = fts_phrase(tok)
        if not ph:
            continue
        if parts and parts[-1] not in ("AND", "OR", "NOT", "("):
            parts.append("AND")
        parts.append(ph)
    while parts and parts[-1] in ("AND", "OR", "NOT", "("):
        if parts[-1] == "(":
            depth -= 1
        parts.pop()
    parts += [")"] * max(0, depth)
    for col, val in pq.columns:
        ph = fts_phrase(val)
        if ph:
            col_name = "abstract" if col == "abstract" else "title"
            parts += (["AND"] if parts else []) + [f"{col_name} : {ph}"]
    expr = " ".join(parts)
    excl = [p for p in (fts_phrase(x) for x in pq.excludes) if p]
    if excl and expr:
        expr = f"({expr}) NOT ({' OR '.join(excl)})"
    return expr or None
