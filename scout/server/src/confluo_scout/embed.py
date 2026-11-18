"""EmbeddingGemma 2 encoder.

The full 740M checkpoint (`google/embeddinggemma-2`) is on disk; papers are text, so Scout loads
the 270M text path (vision and audio encoders off). Both setups share one 768-d space.
Prompts follow the model card: queries `task: search result | query: ...`, documents
`title: {title} | text: {content}`, term-to-term similarity `task: sentence similarity | query: ...`.
"""

from __future__ import annotations

import logging
import threading
import time

import numpy as np

from confluo_scout.config import Settings

log = logging.getLogger("scout.embed")

QUERY_PROMPT = "task: search result | query: "
TERM_PROMPT = "task: sentence similarity | query: "
DIM = 768


def document_text(title: str, abstract: str | None, keywords: list[str] | None = None, area: str | None = None) -> str:
    parts = [abstract.strip()] if abstract else []
    if keywords:
        parts.append("Keywords: " + "; ".join(keywords[:12]) + ".")
    if area:
        parts.append(f"Area: {area}.")
    content = " ".join(parts) if parts else "none"
    return f"title: {title.strip()} | text: {content}"


class Embedder:
    def __init__(self, settings: Settings):
        import torch
        from sentence_transformers import SentenceTransformer

        device = settings.device
        if device == "auto":
            device = "mps" if torch.backends.mps.is_available() else "cpu"
        if device == "cpu":
            torch.set_num_threads(settings.torch_threads)
        t0 = time.time()
        self.model = SentenceTransformer(
            str(settings.model_dir), device=device,
            config_kwargs={"vision_config": None, "audio_config": None},
            model_kwargs={"dtype": torch.float32},
            local_files_only=True,
        )
        self.model.max_seq_length = 512
        self.device = device
        getter = getattr(self.model, "get_embedding_dimension", None) or self.model.get_sentence_embedding_dimension
        self.dim = getter() or DIM
        self.params_m = round(sum(p.numel() for p in self.model.parameters()) / 1e6, 1)
        self._lock = threading.Lock()
        log.info("EmbeddingGemma 2 text path loaded on %s in %.1fs (%sM params, dim %s)",
                 device, time.time() - t0, self.params_m, self.dim)

    def _encode(self, texts: list[str], batch_size: int) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        with self._lock:
            vecs = self.model.encode(texts, batch_size=batch_size, normalize_embeddings=True,
                                     convert_to_numpy=True, show_progress_bar=False)
        return np.asarray(vecs, dtype=np.float32)

    def documents(self, texts: list[str], batch_size: int = 32) -> np.ndarray:
        return self._encode(texts, batch_size)

    def queries(self, texts: list[str]) -> np.ndarray:
        return self._encode([QUERY_PROMPT + t for t in texts], 16)

    def terms(self, texts: list[str], batch_size: int = 128) -> np.ndarray:
        return self._encode([TERM_PROMPT + t for t in texts], batch_size)
