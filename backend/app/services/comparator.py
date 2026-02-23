from __future__ import annotations

import difflib
import re
from dataclasses import dataclass

from rapidfuzz.distance import Levenshtein

from app.config import settings
from app.schemas import Mismatch
from app.services.file_processor import Token

NUMERIC_PATTERN = re.compile(r"^\d+([.,]\d+)?$")


@dataclass(slots=True)
class ComparisonResult:
    mismatches: list[Mismatch]
    lexical_similarity: float


def _context(tokens: list[Token], index: int, window: int = 5) -> str:
    start = max(0, index - window)
    end = min(len(tokens), index + window + 1)
    return " ".join(token.text for token in tokens[start:end])


def _is_spelling_variant(a: str, b: str) -> bool:
    al, bl = a.lower(), b.lower()
    if al == bl:
        return False
    if abs(len(al) - len(bl)) > 2:
        return False
    return Levenshtein.distance(al, bl) <= 2


def _classify_modified(input_word: str, output_word: str) -> str:
    if input_word.lower() == output_word.lower() and input_word != output_word:
        return "case"
    if NUMERIC_PATTERN.match(input_word) and NUMERIC_PATTERN.match(output_word):
        return "numeric"
    if _is_spelling_variant(input_word, output_word):
        return "spelling"
    return "modified"


def compare_tokens(
    input_tokens: list[Token],
    output_tokens: list[Token],
    include_added: bool = True,
) -> ComparisonResult:
    input_words = [token.text for token in input_tokens]
    output_words = [token.text for token in output_tokens]
    input_norm = [w.lower() for w in input_words]
    output_norm = [w.lower() for w in output_words]

    if input_norm == output_norm:
        return ComparisonResult(mismatches=[], lexical_similarity=100.0)

    matcher = difflib.SequenceMatcher(a=input_norm, b=output_norm, autojunk=False)

    mismatches: list[Mismatch] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue

        if tag == "delete":
            for idx in range(i1, i2):
                token = input_tokens[idx]
                mismatches.append(
                    Mismatch(
                        type="missing",
                        word=token.text,
                        input_location=token.location,
                        output_location="",
                        context=_context(input_tokens, idx),
                    )
                )
            continue

        if tag == "insert":
            if not include_added:
                continue
            for idx in range(j1, j2):
                token = output_tokens[idx]
                mismatches.append(
                    Mismatch(
                        type="added",
                        word=token.text,
                        input_location="",
                        output_location=token.location,
                        context=_context(output_tokens, idx),
                    )
                )
            continue

        # replace
        left = input_tokens[i1:i2]
        right = output_tokens[j1:j2]
        shared = min(len(left), len(right))
        for offset in range(shared):
            ltok = left[offset]
            rtok = right[offset]
            mismatch_type = _classify_modified(ltok.text, rtok.text)
            mismatches.append(
                Mismatch(
                    type=mismatch_type,  # type: ignore[arg-type]
                    word=f"{ltok.text} -> {rtok.text}",
                    input_location=ltok.location,
                    output_location=rtok.location,
                    context=f"IN: {_context(input_tokens, i1 + offset)} | OUT: {_context(output_tokens, j1 + offset)}",
                )
            )

        for offset in range(shared, len(left)):
            ltok = left[offset]
            mismatches.append(
                Mismatch(
                    type="missing",
                    word=ltok.text,
                    input_location=ltok.location,
                    output_location="",
                    context=_context(input_tokens, i1 + offset),
                )
            )

        if include_added:
            for offset in range(shared, len(right)):
                rtok = right[offset]
                mismatches.append(
                    Mismatch(
                        type="added",
                        word=rtok.text,
                        input_location="",
                        output_location=rtok.location,
                        context=_context(output_tokens, j1 + offset),
                    )
                )

    if len(mismatches) > settings.top_mismatches_limit:
        mismatches = mismatches[: settings.top_mismatches_limit]

    lexical_similarity = matcher.ratio() * 100
    return ComparisonResult(mismatches=mismatches, lexical_similarity=lexical_similarity)
