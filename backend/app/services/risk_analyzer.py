from __future__ import annotations

from app.schemas import LayerMismatch


def assess_risk(mismatches: list[LayerMismatch], critical_changes: list[str], semantic_similarity: float) -> str:
    high_count = sum(1 for m in mismatches if m.risk_level == "High")
    medium_count = sum(1 for m in mismatches if m.risk_level == "Medium")
    numeric_or_semantic = sum(1 for m in mismatches if m.layer in {"numeric", "semantic", "ocr"})

    if critical_changes or high_count >= 8 or numeric_or_semantic >= 10 or semantic_similarity < 70:
        return "High"
    if medium_count >= 12 or high_count >= 2 or semantic_similarity < 85:
        return "Medium"
    return "Low"
