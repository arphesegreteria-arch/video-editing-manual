from __future__ import annotations

from dataclasses import dataclass
from typing import Any


AUTO_KINDS = {"FILLER", "FALSE_START", "SENTENCE_RESTART", "IMMEDIATE_REPEAT", "EXCESS_PAUSE"}


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


def cleanup_cut_ranges(candidates: tuple[CleanupCandidate, ...], fps: float,
                       total_frames: int) -> tuple[tuple[int, int], ...]:
    if fps <= 0 or total_frames <= 0:
        raise ValueError("fps e durata cleanup devono essere positivi")
    raw = sorted((max(0, round(item.start * fps)), min(total_frames, round(item.end * fps)))
                 for item in candidates if item.auto_apply)
    merged: list[list[int]] = []
    for start, end in raw:
        if end <= start:
            continue
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return tuple((start, end) for start, end in merged)


def derived_timeline_names(original_name: str) -> tuple[str, str]:
    base = original_name.strip()
    if not base or base.endswith("_CLEANUP") or base.endswith("_EDITORIAL"):
        raise ValueError("Nome timeline originale non valido")
    return f"{base}_CLEANUP", f"{base}_EDITORIAL"
