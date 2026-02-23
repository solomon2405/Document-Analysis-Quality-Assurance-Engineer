from __future__ import annotations

import difflib
import re

from rapidfuzz import fuzz

from app.schemas import LayerMismatch, Location
from app.services.ingestion_service import UnifiedDocument

SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
OBLIGATION_WORDS = {"shall", "must", "required", "mandatory"}
OPTIONAL_WORDS = {"may", "optional", "can"}


def _split_sentences(text: str) -> list[str]:
    parts = [p.strip() for p in SENTENCE_SPLIT.split(text) if p.strip()]
    return parts if parts else ([text.strip()] if text.strip() else [])


def _sentence_similarity(a: str, b: str) -> float:
    ratio = fuzz.token_set_ratio(a, b) / 100.0
    seq = difflib.SequenceMatcher(a=a.lower(), b=b.lower(), autojunk=False).ratio()
    return max(0.0, min(1.0, (0.65 * ratio) + (0.35 * seq)))


def _best_match_score(sentence: str, candidates: list[str]) -> float:
    if not candidates:
        return 0.0
    return max(_sentence_similarity(sentence, c) for c in candidates)


def run_semantic_layer(input_doc: UnifiedDocument, output_doc: UnifiedDocument) -> tuple[float, list[LayerMismatch], list[str]]:
    in_sentences = _split_sentences(input_doc.full_text)
    out_sentences = _split_sentences(output_doc.full_text)
    if not in_sentences and not out_sentences:
        return 100.0, [], []
    if not in_sentences or not out_sentences:
        return 0.0, [], ["One side is empty; severe semantic drift."]

    in_scores = [_best_match_score(sentence, out_sentences) for sentence in in_sentences]
    out_scores = [_best_match_score(sentence, in_sentences) for sentence in out_sentences]
    semantic_score = (sum(in_scores) / len(in_scores)) * 100

    mismatches: list[LayerMismatch] = []
    critical: list[str] = []

    for idx, score in enumerate(in_scores):
        if score >= 0.7:
            continue
        sentence = in_sentences[idx]
        risk = "High" if any(w in sentence.lower().split() for w in OBLIGATION_WORDS) else "Medium"
        mismatches.append(
            LayerMismatch(
                layer="semantic",
                change_type="meaning_drift_or_removed_clause",
                input_text=sentence,
                output_text="",
                location=Location(
                    file=input_doc.units[0].file if input_doc.units else "combined_input",
                    page=1,
                    paragraph=idx + 1,
                ),
                context_window="Sentence likely removed or heavily paraphrased.",
                confidence_score=round(max(0.0, min(1.0, 1 - score)), 3),
                risk_level=risk,  # type: ignore[arg-type]
            )
        )
        if risk == "High":
            critical.append(f"Potential removed obligation: {sentence[:120]}")

    for idx, score in enumerate(out_scores):
        if score >= 0.7:
            continue
        sentence = out_sentences[idx]
        risk = "High" if any(w in sentence.lower().split() for w in (OBLIGATION_WORDS | OPTIONAL_WORDS)) else "Medium"
        mismatches.append(
            LayerMismatch(
                layer="semantic",
                change_type="added_or_paraphrased_statement",
                input_text="",
                output_text=sentence,
                location=Location(
                    file=output_doc.units[0].file if output_doc.units else "combined_output",
                    page=1,
                    paragraph=idx + 1,
                ),
                context_window="Statement appears newly introduced.",
                confidence_score=round(max(0.0, min(1.0, 1 - score)), 3),
                risk_level=risk,  # type: ignore[arg-type]
            )
        )

    in_text = input_doc.full_text.lower()
    out_text = output_doc.full_text.lower()
    if any(w in in_text for w in OBLIGATION_WORDS) and any(w in out_text for w in OPTIONAL_WORDS):
        critical.append("Tone shift detected: mandatory language may have become optional.")

    return round(max(0.0, min(100.0, semantic_score)), 2), mismatches[:2500], critical[:30]
