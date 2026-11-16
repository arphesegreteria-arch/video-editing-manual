"""Strict read-only facts used by the voice-over CTA workflow.

The Resolve API exposes a few frame values with inconsistent inclusive versus
exclusive conventions.  This module turns an *observed* A4 item into explicit
half-open ranges and refuses to guess where the values do not reconcile.
"""
from __future__ import annotations

from fractions import Fraction
from typing import Any

from .safety import ValidationError


def exact_rate(value: object, label: str) -> Fraction:
    """Parse a positive, integral FPS value; never select a fallback FPS."""
    try:
        rate = Fraction(str(value))
    except (TypeError, ValueError, ZeroDivisionError) as exc:
        raise ValidationError(f"FPS {label} mancante o non leggibile") from exc
    if rate <= 0 or rate.denominator != 1:
        raise ValidationError(f"FPS {label} non supportato: serve un valore intero positivo")
    return rate


def _source_frame_count(timeline_frames: int, source_rate: Fraction,
                        timeline_rate: Fraction) -> int:
    if timeline_frames <= 0:
        raise ValidationError("Durata A4 non valida")
    converted = Fraction(timeline_frames, 1) * source_rate / timeline_rate
    if converted.denominator != 1:
        raise ValidationError("FPS A4/timeline non riconciliabili su frame esatti")
    return int(converted)


def normalize_source_range(*, source_start: int, source_end_raw: int,
                           record_duration: int, source_rate: Fraction,
                           timeline_rate: Fraction) -> tuple[int, int, str]:
    """Return `[start, end)` after proving how the API's end value behaves.

    Resolve builds differ in whether ``GetSourceEndFrame`` is inclusive.  The
    returned convention records the evidence, and an unknown/mismatched value
    blocks the workflow instead of allowing a one-frame edit error.
    """
    if isinstance(source_start, bool) or isinstance(source_end_raw, bool):
        raise ValidationError("source-end A4 non valido")
    try:
        start, raw_end, duration = int(source_start), int(source_end_raw), int(record_duration)
    except (TypeError, ValueError) as exc:
        raise ValidationError("source-end A4 non leggibile") from exc
    expected = _source_frame_count(duration, source_rate, timeline_rate)
    if raw_end - start + 1 == expected:
        return start, raw_end + 1, "inclusive"
    raise ValidationError("source-end A4 non coincide con la durata registrata")


def media_id(media: Any) -> str:
    """Get a stable media id from a bridge observation, not Python identity."""
    if isinstance(media, dict):
        value = media.get("media_id")
    else:
        getter = getattr(media, "GetMediaId", None)
        value = getter() if callable(getter) else None
    if not isinstance(value, str) or not value.strip():
        raise ValidationError("Identificatore media A4 mancante")
    return value


def same_media(left: Any, right: Any) -> bool:
    return media_id(left) == media_id(right)
