from __future__ import annotations

from typing import Any

from .safety import ValidationError


def validate_reframe_action(action: dict[str, Any], total_frames: int) -> dict[str, Any]:
    if action.get("type") != "REFRAME" or action.get("state") != "APPROVED":
        raise ValidationError("REFRAME non approvato")
    raw_range = action.get("range")
    if not isinstance(raw_range, dict):
        raise ValidationError("range REFRAME mancante")
    start, end = raw_range.get("start_frame"), raw_range.get("end_frame")
    if not isinstance(start, int) or not isinstance(end, int) or not 0 <= start < end <= total_frames:
        raise ValidationError("range REFRAME non valido")
    target = action.get("target")
    if not isinstance(target, dict) or not str(target.get("kind", "")).strip() or not str(target.get("label", "")).strip():
        raise ValidationError("target REFRAME esplicito richiesto")
    anchor = action.get("anchor")
    if not isinstance(anchor, dict) or not all(isinstance(anchor.get(key), (int, float)) and 0.1 <= float(anchor[key]) <= 0.9 for key in ("x", "y")):
        raise ValidationError("anchor REFRAME non sicuro")
    if not str(action.get("reason", "")).strip():
        raise ValidationError("reason REFRAME mancante")
    return {"range": (start, end), "target": dict(target), "anchor": {"x": float(anchor["x"]), "y": float(anchor["y"])}}
