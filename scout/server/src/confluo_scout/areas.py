"""Unified research areas: one taxonomy for every venue.

Native areas exist only on some platforms (OpenReview primary areas, AAAI tracks, IJCAI
sections). Scout also assigns each paper the nearest area of a fixed AI taxonomy by cosine
between the paper's document vector and an embedded area description (zero-shot), so CVF,
ECVA and ACL papers get an area too. The native area stays the authority where it exists.
"""

from __future__ import annotations

import logging
import threading

import numpy as np

log = logging.getLogger("scout.areas")

# id, Chinese label, English description used for the embedding
TAXONOMY: list[tuple[str, str, str]] = [
    ("llm", "大模型与基础模型", "large language models, foundation models, pretraining, instruction tuning, LLM reasoning"),
    ("nlp", "自然语言处理", "natural language processing, machine translation, parsing, information extraction, question answering"),
    ("vision", "计算机视觉", "computer vision, image recognition, detection, segmentation, 3D vision, video understanding"),
    ("generative", "生成模型", "generative models, diffusion models, flow matching, GANs, image and video generation"),
    ("multimodal", "多模态学习", "multimodal learning, vision-language models, image-text models, audio-visual learning"),
    ("rl", "强化学习与决策", "reinforcement learning, policy optimization, bandits, sequential decision making"),
    ("robotics", "机器人与具身智能", "robotics, embodied agents, manipulation, navigation, autonomous driving"),
    ("agents", "智能体与多智能体", "LLM agents, tool use, multi-agent systems, game theory, mechanism design"),
    ("graph", "图学习", "graph neural networks, graph representation learning, knowledge graphs, networks"),
    ("theory", "学习理论", "learning theory, generalization bounds, statistical learning, sample complexity"),
    ("optimization", "优化", "optimization algorithms, stochastic gradient methods, convex and nonconvex optimization"),
    ("probabilistic", "概率方法与因果", "probabilistic models, Bayesian inference, uncertainty, causal inference"),
    ("representation", "表示与自监督学习", "representation learning, self-supervised learning, contrastive learning, embeddings"),
    ("interpretability", "可解释性", "interpretability, explainability, mechanistic interpretability, attribution, probing"),
    ("safety", "安全、对齐与隐私", "AI safety, alignment, robustness, adversarial attacks, privacy, fairness"),
    ("efficient", "高效机器学习与系统", "efficient machine learning, model compression, quantization, ML systems, hardware"),
    ("science", "AI for Science", "AI for science, biology, protein, chemistry, molecules, physics, materials"),
    ("health", "医疗与健康", "medical imaging, healthcare, clinical data, biomedicine"),
    ("timeseries", "时间序列", "time series forecasting, temporal data, spatiotemporal modeling"),
    ("speech", "语音与音频", "speech recognition, speech synthesis, audio and music processing"),
    ("retrieval", "检索、推荐与数据挖掘", "information retrieval, recommender systems, search, data mining"),
    ("benchmarks", "数据集与评测", "datasets, benchmarks, evaluation methodology, leaderboards"),
    ("reasoning", "知识表示、推理与规划", "knowledge representation, logic, symbolic reasoning, automated planning, constraint satisfaction"),
]
LABELS = {k: zh for k, zh, _ in TAXONOMY}


class AreaClassifier:
    def __init__(self, embedder):
        self.ids = [k for k, _, _ in TAXONOMY]
        self.vecs = embedder.queries([f"research papers on {desc}" for _, _, desc in TAXONOMY])

    def classify(self, doc_vecs: np.ndarray) -> list[tuple[str, float]]:
        if not len(doc_vecs):
            return []
        sims = doc_vecs @ self.vecs.T
        best = sims.argmax(axis=1)
        return [(self.ids[b], float(sims[i, b])) for i, b in enumerate(best)]


_CACHE: dict = {"clf": None}
_LOCK = threading.Lock()


def classifier(embedder) -> AreaClassifier:
    with _LOCK:
        if _CACHE["clf"] is None:
            _CACHE["clf"] = AreaClassifier(embedder)
        return _CACHE["clf"]


def backfill(svc, embedder=None, batch: int = 512) -> int:
    """Assign unified areas to embedded papers that have none, using their stored vectors."""
    clf = classifier(embedder or svc.embedder)
    done = 0
    while True:
        rows = svc.db.query("select id from paper where embed_hash is not null and area_unified is null limit ?",
                            (batch,))
        if not rows:
            break
        ids = [r[0] for r in rows]
        vecs = svc.vectors.vectors_of(ids)
        have = [i for i in ids if i in vecs]
        labels = clf.classify(np.stack([vecs[i] for i in have])) if have else []
        with svc.db.tx() as con:
            con.executemany("update paper set area_unified=? where id=?",
                            [(a, i) for i, (a, _s) in zip(have, labels, strict=True)])
            # Rows without a vector yet are retried after they are embedded.
            missing = [i for i in ids if i not in vecs]
            con.executemany("update paper set embed_hash=null where id=?", [(i,) for i in missing])
        done += len(have)
    if done:
        log.info("unified areas assigned to %d papers", done)
    return done
