"""Session graph: query, keyword and paper nodes with weighted edges, scored by personalized
PageRank from the query node. Papers reached by several strong paths score higher."""

from __future__ import annotations

import numpy as np


class SessionGraph:
    def __init__(self):
        self.index: dict[str, int] = {}
        self.edges: dict[tuple[int, int], float] = {}
        self.node("q")

    def node(self, name: str) -> int:
        idx = self.index.get(name)
        if idx is None:
            idx = len(self.index)
            self.index[name] = idx
        return idx

    def add(self, src: str, dst: str, weight: float) -> None:
        if weight <= 0:
            return
        key = (self.node(src), self.node(dst))
        if weight > self.edges.get(key, 0.0):
            self.edges[key] = weight

    def ppr(self, alpha: float = 0.2, iters: int = 30) -> dict[str, float]:
        n = len(self.index)
        if not self.edges:
            return {name: (1.0 if name == "q" else 0.0) for name in self.index}
        src = np.fromiter((k[0] for k in self.edges), dtype=np.int64, count=len(self.edges))
        dst = np.fromiter((k[1] for k in self.edges), dtype=np.int64, count=len(self.edges))
        w = np.fromiter(self.edges.values(), dtype=np.float64, count=len(self.edges))
        out_w = np.bincount(src, weights=w, minlength=n)
        norm_w = w / out_w[src]
        dangling = out_w == 0
        q = self.index["q"]
        pi = np.zeros(n)
        pi[q] = 1.0
        for _ in range(iters):
            flow = np.bincount(dst, weights=pi[src] * norm_w, minlength=n)
            nxt = (1 - alpha) * flow
            nxt[q] += alpha + (1 - alpha) * pi[dangling].sum()
            pi = nxt
        names = list(self.index)
        return {names[i]: float(pi[i]) for i in range(n)}
