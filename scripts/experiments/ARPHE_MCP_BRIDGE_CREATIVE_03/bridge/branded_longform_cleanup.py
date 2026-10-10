from __future__ import annotations

from dataclasses import dataclass
from typing import Any


AUTO_KINDS = {"FILLER", "FALSE_START", "IMMEDIATE_REPEAT", "EXCESS_PAUSE"}


@dataclass(frozen=True)
class CleanupCandidate:
    kind: str
    start: float
    end: float
    confidence: float
    auto_apply: bool
    review_required: bool


def plan_cleanup(events: list[dict[str, Any]], confidence_threshold: float = 0.9) -> tuple[CleanupCandidate, ...]:
    candidates: list[CleanupCandidate] = []
    for event in events:
        kind = str(event["kind"])
        confidence = float(event["confidence"])
        auto_apply = kind in AUTO_KINDS and confidence >= confidence_threshold
        candidates.append(CleanupCandidate(kind, float(event["start"]), float(event["end"]), confidence, auto_apply, not auto_apply))
    return tuple(candidates)


def derived_timeline_names(original_name: str) -> tuple[str, str]:
    base = original_name.strip()
    if not base or base.endswith("_CLEANUP") or base.endswith("_EDITORIAL"):
        raise ValueError("Nome timeline originale non valido")
    return f"{base}_CLEANUP", f"{base}_EDITORIAL"
