from __future__ import annotations

import difflib
import re
from dataclasses import dataclass

from rapidfuzz.distance import Levenshtein

from app.config import settings
from app.schemas import LayerMismatch, Location
from app.services.ingestion_service import UnifiedDocument, TextUnit

NUMERIC_PATTERN = re.compile(r"^\$?\d[\d,]*(\.\d+)?%?$")


@dataclass(slots=True)
class DiffResult:
    structural_similarity: float
    lexical_similarity: float
    mismatches: list[LayerMismatch]
    critical_changes: list[str]
    stage_progress: dict[str, int]
    entity_table: list[dict[str, str]]


def _context(units: list[TextUnit], index: int, width: int = 5) -> str:
    start = max(0, index - width)
    end = min(len(units), index + width + 1)
    return " ".join(u.text for u in units[start:end])


def _risk_for_change(layer: str, change: str) -> str:
    if layer in {"numeric", "semantic", "ocr"}:
        return "High"
    if change in {"removed_block", "missing", "replaced"}:
        return "Medium"
    return "Low"


def _structural_diff(input_doc: UnifiedDocument, output_doc: UnifiedDocument) -> tuple[float, list[LayerMismatch], list[str]]:
    in_sections = list(input_doc.section_map.keys())
    out_sections = list(output_doc.section_map.keys())
    matcher = difflib.SequenceMatcher(a=[s.lower() for s in in_sections], b=[s.lower() for s in out_sections], autojunk=False)
    struct_changes: list[LayerMismatch] = []
    critical: list[str] = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        if tag == "delete":
            for key in in_sections[i1:i2]:
                units = input_doc.section_map[key]
                head = units[0]
                struct_changes.append(
                    LayerMismatch(
                        layer="structural",
                        change_type="removed_block",
                        input_text=key,
                        output_text="",
                        location=Location(file=head.file, page=head.page, paragraph=head.paragraph),
                        context_window="Section present in input but missing in output",
                        confidence_score=0.95,
                        risk_level="Medium",
                    )
                )
                critical.append(f"Missing section/block in output: {key}")
        elif tag == "insert":
            for key in out_sections[j1:j2]:
                units = output_doc.section_map[key]
                head = units[0]
                struct_changes.append(
                    LayerMismatch(
                        layer="structural",
                        change_type="added_block",
                        input_text="",
                        output_text=key,
                        location=Location(file=head.file, page=head.page, paragraph=head.paragraph),
                        context_window="Block newly added in output",
                        confidence_score=0.92,
                        risk_level="Low",
                    )
                )
        else:
            left = in_sections[i1:i2]
            right = out_sections[j1:j2]
            shared = min(len(left), len(right))
            for offset in range(shared):
                li = left[offset]
                ri = right[offset]
                if li.lower() == ri.lower():
                    continue
                in_head = input_doc.section_map[li][0]
                struct_changes.append(
                    LayerMismatch(
                        layer="structural",
                        change_type="reordered_or_heading_changed",
                        input_text=li,
                        output_text=ri,
                        location=Location(file=in_head.file, page=in_head.page, paragraph=in_head.paragraph),
                        context_window="Section order or heading text changed",
                        confidence_score=0.9,
                        risk_level="Medium",
                    )
                )

    return matcher.ratio() * 100, struct_changes, critical


def _lexical_diff(input_doc: UnifiedDocument, output_doc: UnifiedDocument) -> tuple[float, list[LayerMismatch], list[str]]:
    in_words = [u.text for u in input_doc.units]
    out_words = [u.text for u in output_doc.units]
    in_norm = [w.lower() for w in in_words]
    out_norm = [w.lower() for w in out_words]
    if in_norm == out_norm:
        return 100.0, [], []

    matcher = difflib.SequenceMatcher(a=in_norm, b=out_norm, autojunk=False)
    mismatches: list[LayerMismatch] = []
    critical: list[str] = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue

        if tag == "delete":
            for idx in range(i1, i2):
                token = input_doc.units[idx]
                mismatches.append(
                    LayerMismatch(
                        layer="lexical",
                        change_type="removed",
                        input_text=token.text,
                        output_text="",
                        location=Location(file=token.file, page=token.page, paragraph=token.paragraph),
                        context_window=_context(input_doc.units, idx),
                        confidence_score=0.96,
                        risk_level="Medium",
                    )
                )
            continue

        left = input_doc.units[i1:i2]
        right = output_doc.units[j1:j2]
        shared = min(len(left), len(right))
        for offset in range(shared):
            ltok = left[offset]
            rtok = right[offset]
            l, r = ltok.text, rtok.text
            if l == r:
                continue

            if l.lower() == r.lower():
                change_type = "case_mismatch"
            elif NUMERIC_PATTERN.match(l) and NUMERIC_PATTERN.match(r):
                change_type = "numeric_change"
                critical.append(f"Numeric changed: {l} -> {r} at {ltok.file}")
            elif Levenshtein.distance(l.lower(), r.lower()) <= 2:
                change_type = "typo_or_spelling"
            elif re.sub(r"\w", "", l) != re.sub(r"\w", "", r):
                change_type = "punctuation_change"
            else:
                change_type = "replaced"

            layer = "numeric" if change_type == "numeric_change" else "lexical"
            mismatches.append(
                LayerMismatch(
                    layer=layer,  # type: ignore[arg-type]
                    change_type=change_type,
                    input_text=l,
                    output_text=r,
                    location=Location(file=ltok.file, page=ltok.page, paragraph=ltok.paragraph),
                    context_window=f"IN: {_context(input_doc.units, i1 + offset)} | OUT: {_context(output_doc.units, j1 + offset)}",
                    confidence_score=0.88 if layer == "lexical" else 0.95,
                    risk_level=_risk_for_change(layer, change_type),  # type: ignore[arg-type]
                )
            )

        for idx in range(shared, len(left)):
            ltok = left[idx]
            mismatches.append(
                LayerMismatch(
                    layer="lexical",
                    change_type="missing",
                    input_text=ltok.text,
                    output_text="",
                    location=Location(file=ltok.file, page=ltok.page, paragraph=ltok.paragraph),
                    context_window=_context(input_doc.units, i1 + idx),
                    confidence_score=0.93,
                    risk_level="Medium",
                )
            )

    return matcher.ratio() * 100, mismatches[: settings.top_mismatches_limit], critical


def _ocr_visual_diff(input_doc: UnifiedDocument, output_doc: UnifiedDocument) -> list[LayerMismatch]:
    out_by_name = {img.file.lower(): img for img in output_doc.image_docs}
    out_by_fp = {img.fingerprint: img for img in output_doc.image_docs}
    mismatches: list[LayerMismatch] = []

    for image in input_doc.image_docs:
        matched = out_by_name.get(image.file.lower()) or out_by_fp.get(image.fingerprint)
        if matched is None:
            mismatches.append(
                LayerMismatch(
                    layer="ocr",
                    change_type="image_missing_in_output",
                    input_text=image.file,
                    output_text="",
                    location=Location(file=image.file, page=1, paragraph=1),
                    context_window="Input image has no matching image in output",
                    confidence_score=0.99,
                    risk_level="High",
                )
            )
            continue

        in_text = [w.text for w in image.words]
        out_text = [w.text for w in matched.words]
        if [t.lower() for t in in_text] == [t.lower() for t in out_text]:
            continue

        matcher = difflib.SequenceMatcher(a=[t.lower() for t in in_text], b=[t.lower() for t in out_text], autojunk=False)
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "equal":
                continue
            first_idx = i1 if i1 < len(image.words) else max(0, len(image.words) - 1)
            loc_word = image.words[first_idx] if image.words else None
            in_seg = " ".join(in_text[i1:i2])
            out_seg = " ".join(out_text[j1:j2])
            mismatches.append(
                LayerMismatch(
                    layer="ocr",
                    change_type="visual_text_changed",
                    input_text=in_seg,
                    output_text=out_seg,
                    location=Location(
                        file=image.file,
                        page=1,
                        paragraph=loc_word.paragraph if loc_word else 1,
                    ),
                    context_window=f"OCR blocks changed; input confidence={image.avg_confidence:.2f}, output confidence={matched.avg_confidence:.2f}",
                    confidence_score=0.86,
                    risk_level="High" if any(ch.isdigit() for ch in in_seg + out_seg) else "Medium",
                )
            )

    return mismatches


def _entity_numeric_table(input_doc: UnifiedDocument, output_doc: UnifiedDocument) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for etype, in_values in input_doc.entities.items():
        out_values = output_doc.entities.get(etype, set())
        for value in sorted(in_values):
            rows.append(
                {
                    "entity_type": etype,
                    "input_value": value,
                    "output_value": value if value in out_values else "",
                    "status": "matched" if value in out_values else "missing_in_output",
                }
            )
        for value in sorted(out_values - in_values):
            rows.append(
                {
                    "entity_type": etype,
                    "input_value": "",
                    "output_value": value,
                    "status": "added_in_output",
                }
            )
    return rows[:1000]


def run_diff_layers(input_doc: UnifiedDocument, output_doc: UnifiedDocument) -> DiffResult:
    structural_similarity, struct_mismatches, struct_critical = _structural_diff(input_doc, output_doc)
    lexical_similarity, lexical_mismatches, lexical_critical = _lexical_diff(input_doc, output_doc)
    ocr_mismatches = _ocr_visual_diff(input_doc, output_doc)
    entity_table = _entity_numeric_table(input_doc, output_doc)

    all_mismatches = struct_mismatches + lexical_mismatches + ocr_mismatches
    stage_progress = {"structural": 100, "lexical": 100, "ocr": 100}
    critical_changes = struct_critical + lexical_critical
    if any("missing_in_output" in row["status"] and row["entity_type"] in {"DATE", "MONEY"} for row in entity_table):
        critical_changes.append("Critical entity/date/currency differences detected.")

    return DiffResult(
        structural_similarity=round(structural_similarity, 2),
        lexical_similarity=round(lexical_similarity, 2),
        mismatches=all_mismatches[: settings.top_mismatches_limit],
        critical_changes=critical_changes[:50],
        stage_progress=stage_progress,
        entity_table=entity_table,
    )
