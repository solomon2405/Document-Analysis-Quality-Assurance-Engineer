from __future__ import annotations

import logging
import re
from functools import lru_cache

import numpy as np
from sentence_transformers import SentenceTransformer

from app.config import settings
from app.schemas import LayerMismatch, Location
from app.services.ingestion_service import UnifiedDocument

logger = logging.getLogger(__name__)
SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
OBLIGATION_WORDS = {"shall", "must", "required", "mandatory"}
OPTIONAL_WORDS = {"may", "optional", "can"}


@lru_cache(maxsize=1)
def _model() -> SentenceTransformer:
    logger.info("Loading semantic model: %s", settings.semantic_model_name)
    return SentenceTransformer(settings.semantic_model_name)


def _split(text: str) -> list[str]:
    parts = [p.strip() for p in SENTENCE_SPLIT.split(text) if p.strip()]
    return parts if parts else ([text.strip()] if text.strip() else [])


def _embed_chunks(sentences: list[str]) -> np.ndarray:
    model = _model()
    chunks: list[np.ndarray] = []
    size = settings.semantic_chunk_size
    for i in range(0, len(sentences), size):
        batch = sentences[i : i + size]
        chunks.append(model.encode(batch, convert_to_numpy=True, normalize_embeddings=False))
    return np.vstack(chunks) if chunks else np.zeros((0, 384), dtype=np.float32)


def _cosine(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    if a.size == 0 or b.size == 0:
        return np.zeros((a.shape[0], b.shape[0]), dtype=np.float32)
    a_norm = a / (np.linalg.norm(a, axis=1, keepdims=True) + 1e-8)
    b_norm = b / (np.linalg.norm(b, axis=1, keepdims=True) + 1e-8)
    return np.dot(a_norm, b_norm.T)


def run_semantic_layer(input_doc: UnifiedDocument, output_doc: UnifiedDocument) -> tuple[float, list[LayerMismatch], list[str]]:
    in_sentences = _split(input_doc.full_text)
    out_sentences = _split(output_doc.full_text)
    if not in_sentences and not out_sentences:
        return 100.0, [], []
    if not in_sentences or not out_sentences:
        return 0.0, [], ["One side is empty; severe semantic drift."]

    in_emb = _embed_chunks(in_sentences)
    out_emb = _embed_chunks(out_sentences)
    sim = _cosine(in_emb, out_emb)
    in_max = np.max(sim, axis=1) if sim.size else np.zeros((len(in_sentences),))
    out_max = np.max(sim, axis=0) if sim.size else np.zeros((len(out_sentences),))
    semantic_score = float(np.mean(in_max) * 100)

    mismatches: list[LayerMismatch] = []
    critical: list[str] = []
    for idx, score in enumerate(in_max):
        if float(score) >= 0.68:
            continue
        sentence = in_sentences[idx]
        risk = "High" if any(w in sentence.lower().split() for w in OBLIGATION_WORDS) else "Medium"
        mismatches.append(
            LayerMismatch(
                layer="semantic",
                change_type="meaning_drift_or_removed_clause",
                input_text=sentence,
                output_text="",
                location=Location(file=input_doc.units[0].file if input_doc.units else "combined_input", page=1, paragraph=idx + 1),
                context_window="Sentence likely removed or heavily paraphrased",
                confidence_score=max(0.0, min(1.0, 1 - float(score))),
                risk_level=risk,  # type: ignore[arg-type]
            )
        )
        if risk == "High":
            critical.append(f"Potential removed obligation: {sentence[:120]}")

    for idx, score in enumerate(out_max):
        if float(score) >= 0.68:
            continue
        sentence = out_sentences[idx]
        risk = "High" if any(w in sentence.lower().split() for w in OBLIGATION_WORDS | OPTIONAL_WORDS) else "Medium"
        mismatches.append(
            LayerMismatch(
                layer="semantic",
                change_type="added_or_paraphrased_statement",
                input_text="",
                output_text=sentence,
                location=Location(file=output_doc.units[0].file if output_doc.units else "combined_output", page=1, paragraph=idx + 1),
                context_window="Statement appears newly introduced",
                confidence_score=max(0.0, min(1.0, 1 - float(score))),
                risk_level=risk,  # type: ignore[arg-type]
            )
        )

    # Tone shift heuristic.
    in_text = input_doc.full_text.lower()
    out_text = output_doc.full_text.lower()
    if any(w in in_text for w in OBLIGATION_WORDS) and any(w in out_text for w in OPTIONAL_WORDS):
        critical.append("Tone shift detected: mandatory language may have become optional.")

    return round(max(0.0, min(100.0, semantic_score)), 2), mismatches[:3000], critical[:30]
