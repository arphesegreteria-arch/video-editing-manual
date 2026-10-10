from __future__ import annotations

from typing import Any

from .safety import ValidationError


_STYLE_ROLES = {"cream", "burgundy", "beige", "warm_brown", "white", "black"}
_GRAPHIC_KINDS = {"LOWER_THIRD", "TITLE", "LOGO_BUG"}


def _frame_range(raw: object, total_frames: int) -> tuple[int, int]:
    if not isinstance(raw, dict):
        raise ValidationError("range GRAPHIC/CTA mancante")
    start, end = raw.get("start_frame"), raw.get("end_frame")
    if not isinstance(start, int) or not isinstance(end, int) or not 0 <= start < end <= total_frames:
        raise ValidationError("range GRAPHIC/CTA non valido")
    return start, end


def approved_graphic_actions(plan: dict[str, Any], total_frames: int) -> tuple[dict[str, Any], ...]:
    selected: list[dict[str, Any]] = []
    for raw in plan.get("actions", []):
        action_type = raw.get("type")
        if action_type not in {"GRAPHIC", "CTA"} or raw.get("state") != "APPROVED":
            continue
        role = str(raw.get("style_role", ""))
        if role not in _STYLE_ROLES:
            raise ValidationError("style_role GRAPHIC/CTA non canonico")
        if not str(raw.get("reason", "")).strip():
            raise ValidationError("reason GRAPHIC/CTA mancante")
        start, end = _frame_range(raw.get("range"), total_frames)
        cleaned = {"action_id": str(raw.get("action_id", "")), "type": action_type,
                   "style_role": role, "range": (start, end), "reason": str(raw["reason"])}
        if not cleaned["action_id"]:
            raise ValidationError("action_id GRAPHIC/CTA mancante")
        if action_type == "GRAPHIC":
            kind, text = str(raw.get("graphic_kind", "")), str(raw.get("text", "")).strip()
            if kind not in _GRAPHIC_KINDS or not text:
                raise ValidationError("GRAPHIC richiede tipo e testo canonici")
            cleaned.update({"graphic_kind": kind, "text": text})
        else:
            headline, text = str(raw.get("headline", "")).strip(), str(raw.get("text", "")).strip()
            if not headline or not text:
                raise ValidationError("CTA richiede headline e testo")
            cleaned.update({"headline": headline, "text": text})
        selected.append(cleaned)
    return tuple(selected)
