"""Highlighting with the same tokenization as the FTS index.

Exact hits (query keywords and phrases) become <mark class="hit">, synonym and fuzzy hits
<mark class="near">. Phrases match as consecutive stems.
"""

from __future__ import annotations

import html

from confluo_scout.search.text import spans, stems


class Highlighter:
    def __init__(self, exact: list[str], near: list[str]):
        self.display: dict[tuple[str, ...], str] = {}
        for p in [*near, *exact]:
            if stems(p):
                self.display[tuple(stems(p))] = p
        self.exact = list(dict.fromkeys(tuple(stems(p)) for p in exact if stems(p)))
        self.near = [t for t in dict.fromkeys(tuple(stems(p)) for p in near if stems(p)) if t not in self.exact]
        self.exact.sort(key=len, reverse=True)
        self.near.sort(key=len, reverse=True)

    def _marks(self, toks: list[tuple[int, int, str]]) -> list[str | None]:
        kinds: list[str | None] = [None] * len(toks)
        seq = [t[2] for t in toks]
        for patterns, kind in ((self.exact, "hit"), (self.near, "near")):
            for pat in patterns:
                n = len(pat)
                for i in range(len(seq) - n + 1):
                    if tuple(seq[i:i + n]) == pat and all(k is None for k in kinds[i:i + n]):
                        for j in range(i, i + n):
                            kinds[j] = kind
        return kinds

    def matched(self, text: str) -> tuple[set[str], set[str]]:
        """Which exact / near patterns occur in text (as stem tuples joined by spaces)."""
        seq = [t[2] for t in spans(text)]
        joined = " " + " ".join(seq) + " "
        ex = {self.display[p] for p in self.exact if " " + " ".join(p) + " " in joined}
        nr = {self.display[p] for p in self.near if " " + " ".join(p) + " " in joined}
        return ex, nr

    def render(self, text: str, window: int | None = None) -> str:
        """HTML-escaped text with marks; with `window`, the densest window of that many tokens."""
        if not text:
            return ""
        toks = spans(text)
        kinds = self._marks(toks)
        start_tok, end_tok = 0, len(toks)
        if window and len(toks) > window:
            best, best_i = -1.0, 0
            score = [2.0 if k == "hit" else 1.0 if k == "near" else 0.0 for k in kinds]
            cur = sum(score[:window])
            best, best_i = cur, 0
            for i in range(1, len(toks) - window + 1):
                cur += score[i + window - 1] - score[i - 1]
                if cur > best:
                    best, best_i = cur, i
            start_tok, end_tok = best_i, best_i + window
        out: list[str] = []
        pos = toks[start_tok][0] if start_tok < len(toks) and start_tok > 0 else 0
        stop = toks[end_tok - 1][1] if end_tok < len(toks) else len(text)
        if start_tok > 0:
            out.append("… ")
        i = start_tok
        while i < end_tok:
            s, e, _ = toks[i]
            kind = kinds[i]
            out.append(html.escape(text[pos:s]))
            if kind:
                j = i
                while j + 1 < end_tok and kinds[j + 1] == kind:
                    j += 1
                seg_end = toks[j][1]
                out.append(f'<mark class="{kind}">{html.escape(text[s:seg_end])}</mark>')
                pos = seg_end
                i = j + 1
            else:
                out.append(html.escape(text[s:e]))
                pos = e
                i += 1
        out.append(html.escape(text[pos:stop]))
        if end_tok < len(toks):
            out.append(" …")
        return "".join(out)
