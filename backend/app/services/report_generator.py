from __future__ import annotations

from datetime import datetime, timezone

from app.schemas import ComparisonResponse, EntityDiffRow, LayerMismatch


def build_summary(
    overall_similarity: float,
    structural_similarity: float,
    semantic_similarity: float,
    risk: str,
    critical_changes: list[str],
    mismatches: list[LayerMismatch],
) -> str:
    top_layers: dict[str, int] = {}
    for item in mismatches:
        top_layers[item.layer] = top_layers.get(item.layer, 0) + 1
    dominant = ", ".join(f"{k}:{v}" for k, v in sorted(top_layers.items(), key=lambda x: x[1], reverse=True)[:3])
    critical_txt = " | ".join(critical_changes[:3]) if critical_changes else "No critical changes flagged."
    return (
        f"Overall similarity is {overall_similarity:.2f}%. Structural similarity is {structural_similarity:.2f}% "
        f"and semantic similarity is {semantic_similarity:.2f}%. Risk level is {risk}. "
        f"Dominant change layers: {dominant or 'none'}. Key findings: {critical_txt}"
    )


def build_audit_log(input_files: list[str], output_files: list[str], mismatches: int) -> list[str]:
    timestamp = datetime.now(timezone.utc).isoformat()
    return [
        f"{timestamp} | Job completed",
        f"{timestamp} | Input files count: {len(input_files)}",
        f"{timestamp} | Output files count: {len(output_files)}",
        f"{timestamp} | Total mismatches: {mismatches}",
    ]


def assemble_response(
    overall_similarity_score: float,
    structural_similarity: float,
    semantic_similarity: float,
    risk_assessment: str,
    critical_changes: list[str],
    mismatches: list[LayerMismatch],
    entity_comparison_rows: list[dict[str, str]],
    stage_progress: dict[str, int],
    input_files: list[str],
    output_files: list[str],
) -> ComparisonResponse:
    summary = build_summary(
        overall_similarity_score,
        structural_similarity,
        semantic_similarity,
        risk_assessment,
        critical_changes,
        mismatches,
    )
    audit_log = build_audit_log(input_files, output_files, len(mismatches))
    entities = [EntityDiffRow(**row) for row in entity_comparison_rows]

    return ComparisonResponse(
        overall_similarity_score=round(overall_similarity_score, 2),
        structural_similarity=round(structural_similarity, 2),
        semantic_similarity=round(semantic_similarity, 2),
        risk_assessment=risk_assessment,  # type: ignore[arg-type]
        critical_changes=critical_changes[:100],
        mismatches=mismatches,
        summary_explanation=summary,
        entity_comparison=entities,
        stage_progress=stage_progress,
        audit_log=audit_log,
    )
