from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from functools import lru_cache

import numpy as np
from sentence_transformers import SentenceTransformer

from app.config import settings

logger = logging.getLogger(__name__)

SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


@dataclass(slots=True)
class SemanticResult:
    semantic_similarity: float
    summary: str


@lru_cache(maxsize=1)
def _load_model() -> SentenceTransformer:
    logger.info("Loading semantic model: %s", settings.semantic_model_name)
    return SentenceTransformer(settings.semantic_model_name)


def _split_sentences(text: str) -> list[str]:
    items = [s.strip() for s in SENTENCE_SPLIT.split(text) if s.strip()]
    return items if items else ([text.strip()] if text.strip() else [])


def _cosine_similarity_matrix(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    a_norm = a / (np.linalg.norm(a, axis=1, keepdims=True) + 1e-8)
    b_norm = b / (np.linalg.norm(b, axis=1, keepdims=True) + 1e-8)
    return np.dot(a_norm, b_norm.T)


def analyze_semantics(input_text: str, output_text: str) -> SemanticResult:
    if not input_text.strip() and not output_text.strip():
        return SemanticResult(semantic_similarity=100.0, summary="No content provided.")
    if not input_text.strip() or not output_text.strip():
        return SemanticResult(
            semantic_similarity=0.0,
            summary="One side is empty, indicating complete semantic divergence.",
        )

    model = _load_model()
    input_sentences = _split_sentences(input_text)
    output_sentences = _split_sentences(output_text)

    in_embeddings = model.encode(input_sentences, convert_to_numpy=True, normalize_embeddings=False)
    out_embeddings = model.encode(output_sentences, convert_to_numpy=True, normalize_embeddings=False)
    matrix = _cosine_similarity_matrix(in_embeddings, out_embeddings)
    score = float(np.mean(np.max(matrix, axis=1)) * 100)

    removed = [
        input_sentences[idx]
        for idx, max_val in enumerate(np.max(matrix, axis=1))
        if float(max_val) < 0.65
    ][:3]
    added = [
        output_sentences[idx]
        for idx, max_val in enumerate(np.max(matrix, axis=0))
        if float(max_val) < 0.65
    ][:3]
    paraphrased = bool(removed or added) and score > 65

    summary_parts: list[str] = []
    if paraphrased:
        summary_parts.append("Potential paraphrased content detected.")
    if removed:
        summary_parts.append(f"Possibly removed clauses: {' | '.join(removed)}")
    if added:
        summary_parts.append(f"Possibly added statements: {' | '.join(added)}")
    if not summary_parts:
        summary_parts.append("No major semantic shift detected.")

    return SemanticResult(semantic_similarity=max(0.0, min(100.0, score)), summary=" ".join(summary_parts))
