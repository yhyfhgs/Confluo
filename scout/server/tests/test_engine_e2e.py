"""HopLoop end to end on a tiny corpus with a deterministic hashing embedder and in-memory Qdrant."""

from __future__ import annotations

import hashlib
from types import SimpleNamespace

import numpy as np
import pytest
from qdrant_client import QdrantClient

from confluo_scout.abstracts import AbstractStore
from confluo_scout.concepts import ConceptBuilder, get_vocab
from confluo_scout.db import Database
from confluo_scout.indexer import Indexer
from confluo_scout.records import PaperRecord
from confluo_scout.search.decision import LocalDecider
from confluo_scout.search.engine import SearchEngine
from confluo_scout.search.text import stems
from confluo_scout.store import Store
from confluo_scout.vectors import VectorStore

DIM = 64
PREFIXES = ("task: search result | query: ", "task: sentence similarity | query: ")


class HashEmbedder:
    dim = DIM
    device = "test"

    def _vec(self, text: str) -> np.ndarray:
        for p in PREFIXES:
            text = text.removeprefix(p)
        text = text.replace("title:", " ").replace("| text:", " ")
        v = np.zeros(DIM, dtype=np.float32)
        for s in stems(text):
            h = int(hashlib.md5(s.encode()).hexdigest(), 16)
            v[h % DIM] += 1.0
            v[(h // DIM) % DIM] += 0.5
        n = np.linalg.norm(v)
        return v / n if n else v

    def documents(self, texts, batch_size=32):
        return np.stack([self._vec(t) for t in texts]) if texts else np.zeros((0, DIM), dtype=np.float32)

    queries = documents
    terms = documents


PAPERS = [
    ("Calibrating Verbalized Confidence of Large Language Models", "We calibrate verbalized confidence of large language models with distractors and reduce overconfidence.", ["calibration", "large language models"]),
    ("Uncertainty Estimation for Language Model Answers", "Uncertainty estimation and calibration of language model answers improves selective prediction.", ["uncertainty", "calibration"]),
    ("Expected Calibration Error Revisited", "Expected calibration error is biased; we propose a debiased estimator for classifiers.", ["calibration"]),
    ("Conformal Prediction for LLM Outputs", "Conformal prediction gives coverage guarantees for large language model outputs and uncertainty.", ["conformal prediction"]),
    ("Graph Neural Networks for Molecules", "Graph neural networks predict molecular properties from atoms and bonds.", ["graph neural networks"]),
    ("Equivariant Message Passing", "Equivariant message passing networks for 3D molecular geometry.", ["equivariance"]),
    ("Diffusion Models for Video", "Video diffusion models generate temporally coherent clips.", ["diffusion models"]),
    ("Sparse Autoencoders Find Features", "Sparse autoencoders decompose activations into interpretable features.", ["interpretability"]),
    ("Reward Hacking in RLHF", "Reinforcement learning from human feedback suffers from reward hacking.", ["rlhf"]),
    ("Tokenizer Free Language Models", "Byte level language models without tokenizers.", ["language models"]),
    ("Selective Prediction with Abstention", "Models abstain when uncertainty is high; selective prediction and calibration.", ["abstention", "calibration"]),
    ("Robot Grasping with Vision", "Vision based grasping policies for robot arms.", ["robotics"]),
]


@pytest.fixture
def svc(tmp_path):
    db = Database(tmp_path / "t.sqlite")
    with db.tx() as con:
        con.execute("insert into series(id, short, name, ratings) values('demo','DEMO','Demo Conf','[\"CCF-A\"]')")
        con.execute("insert into edition(id, series_id, year, label, enabled) values('demo-2026','demo',2026,'DEMO 2026',1)")
    store = Store(db, AbstractStore(tmp_path / "abs"))
    recs = [PaperRecord(source="openreview", source_key=f"P{i}", title=t, abstract=a, keywords=k, status="accepted",
                        decision_label="Poster", tier=2) for i, (t, a, k) in enumerate(PAPERS)]
    with db.tx() as con:
        store.upsert_records(con, "demo-2026", recs)
    store.compact_edition("demo-2026")
    store.refresh_edition_stats("demo-2026", 1.0)
    settings = SimpleNamespace(snapshots_dir=tmp_path / "snap", qdrant_url=":memory:")
    s = SimpleNamespace(db=db, store=store, abstracts=store.abstracts, embedder=HashEmbedder(),
                        vectors=VectorStore(settings, dim=DIM, client=QdrantClient(":memory:")),
                        decider=LocalDecider(), settings=settings)
    Indexer(s).embed_pending()
    ConceptBuilder(s).rebuild(min_kw_df=1, min_phrase_df=1, min_acr=1)
    get_vocab(s, refresh=True)
    return s


def test_smart_search_ranks_and_converges(svc):
    res = SearchEngine(svc).search({"q": "calibration of large language model confidence", "topn": 3, "max_rounds": 4})
    titles = [r["title_plain"] for r in res["results"]]
    assert titles[0] == "Calibrating Verbalized Confidence of Large Language Models"
    assert "Robot Grasping with Vision" not in titles[:5]
    assert res["converged"]["reason"] in ("stable", "exhausted", "max_rounds")
    assert len(res["trace"]) == res["converged"]["rounds"]
    top = res["results"][0]
    assert top["matched"]["exact"] and "<mark" in top["title"]
    assert top["decision"]["source"] == "local"


def test_exact_mode_matches_phrase_only(svc):
    res = SearchEngine(svc).search({"q": '"selective prediction"', "mode": "exact"})
    titles = {r["title_plain"] for r in res["results"]}
    assert titles == {"Uncertainty Estimation for Language Model Answers", "Selective Prediction with Abstention"}
    assert res["converged"]["reason"] == "exact"


def test_scope_filters(svc):
    res = SearchEngine(svc).search({"q": "calibration", "venues": ["other"]})
    assert res["results"] == []
