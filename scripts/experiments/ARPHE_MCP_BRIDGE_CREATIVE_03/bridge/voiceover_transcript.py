"""Exact, review-gated phrase lookup for ARPHE_TRANSCRIPT_V1 word timestamps."""
from __future__ import annotations

from fractions import Fraction
import re
import unicodedata
from typing import Any

from .safety import ValidationError


def _tokens(value: object) -> list[str]:
    if not isinstance(value, str):
        return []
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    plain = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.findall(r"[a-z0-9]+", plain)


def _word_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if payload.get("schema") != "ARPHE_TRANSCRIPT_V1":
        raise ValidationError("Transcript voice-over con schema non supportato")
    source = payload.get("source")
    if not isinstance(source, dict) or not isinstance(source.get("fingerprint"), str):
        raise ValidationError("Transcript voice-over senza fingerprint sorgente")
    rows: list[dict[str, Any]] = []
    for segment in payload.get("segments", []):
        if not isinstance(segment, dict):
            continue
        for word in segment.get("words", []):
            if not isinstance(word, dict):
                continue
            tokens = _tokens(word.get("word"))
            if len(tokens) != 1:
                continue
            try:
                start = Fraction(str(word["start"]))
                end = Fraction(str(word["end"]))
            except (KeyError, TypeError, ValueError, ZeroDivisionError) as exc:
                raise ValidationError("Timestamp parola voice-over non leggibile") from exc
            if start < 0 or end < start:
                raise ValidationError("Timestamp parola voice-over non valido")
            rows.append({"token": tokens[0], "start": start, "end": end, "word": word["word"]})
    return rows


def _timeline_frame(start_seconds: Fraction, *, record_start: int, source_start: int,
                    source_rate: Fraction, timeline_rate: Fraction) -> tuple[int, Fraction]:
    source_position = start_seconds * source_rate
    timeline_offset = (source_position - source_start) * timeline_rate / source_rate
    if timeline_offset < 0:
        raise ValidationError("La frase cade prima dell'inizio della clip A4")
    containing_offset = timeline_offset.numerator // timeline_offset.denominator
    return record_start + containing_offset, timeline_offset - containing_offset


def resolve_phrase(payload: dict[str, Any], phrase: str, *, record_start: int,
                   source_start: int, source_rate: Fraction,
                   timeline_rate: Fraction) -> dict[str, Any]:
    """Locate one literal word sequence, leaving final approval to a reviewer."""
    expected = _tokens(phrase)
    if not expected:
        raise ValidationError("Frase CTA vuota o non leggibile")
    if source_rate <= 0 or timeline_rate <= 0:
        raise ValidationError("FPS voice-over non valido")
    words = _word_rows(payload)
    matches: list[dict[str, Any]] = []
    for index in range(0, len(words) - len(expected) + 1):
        candidate = words[index:index + len(expected)]
        if [row["token"] for row in candidate] != expected:
            continue
        frame, residual = _timeline_frame(candidate[0]["start"], record_start=record_start,
                                          source_start=source_start, source_rate=source_rate,
                                          timeline_rate=timeline_rate)
        matches.append({
            "word_index": index,
            "words": [row["word"] for row in candidate],
            "start_seconds": str(candidate[0]["start"]),
            "end_seconds": str(candidate[-1]["end"]),
            "containing_frame": frame,
            "subframe_residual": str(residual),
        })
    if not matches:
        return {"status": "BLOCKED", "blockers": ["phrase_not_found"], "matches": []}
    if len(matches) != 1:
        return {"status": "BLOCKED", "blockers": ["phrase_ambiguous"], "matches": matches}
    return {"status": "REVIEW_REQUIRED", "blockers": [], "matches": matches}
