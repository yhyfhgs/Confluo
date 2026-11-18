"""Host-side embedding accelerator: `scout embed-serve`.

Runs EmbeddingGemma 2 on the host GPU (MPS) and returns vectors over HTTP on 127.0.0.1. The
container reaches it as host.docker.internal (Colima forwards to the host loopback). It holds no
data and never touches the database; when it is down the container embeds on its own CPU.
Two model instances keep interactive queries from waiting behind bulk batches.
"""

from __future__ import annotations

import base64

import numpy as np
from fastapi import Body, FastAPI, HTTPException

from confluo_scout.config import get_settings
from confluo_scout.embed import Embedder


def create_app() -> FastAPI:
    settings = get_settings()
    models = {"bulk": Embedder(settings), "interactive": Embedder(settings)}
    app = FastAPI(title="Confluo Scout embedding accelerator")

    @app.get("/health")
    def health() -> dict:
        m = models["bulk"]
        return {"device": m.device, "dim": m.dim, "params_m": m.params_m}

    @app.post("/embed")
    def embed(payload: dict = Body(...)) -> dict:
        kind = payload.get("kind")
        texts = payload.get("texts") or []
        if kind not in ("documents", "queries", "terms") or not isinstance(texts, list) or len(texts) > 512:
            raise HTTPException(400, "kind must be documents|queries|terms and at most 512 texts")
        model = models["bulk" if payload.get("purpose") == "bulk" else "interactive"]
        vecs = np.ascontiguousarray(getattr(model, kind)([str(t) for t in texts]), dtype=np.float32)
        return {"dim": int(vecs.shape[1]) if len(vecs) else model.dim,
                "vectors": base64.b64encode(vecs.tobytes()).decode("ascii")}

    return app
