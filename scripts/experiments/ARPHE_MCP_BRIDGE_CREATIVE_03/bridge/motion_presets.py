from __future__ import annotations

from .safety import ValidationError, finite_float, validate_preset


DIRECTIONS = {"top", "bottom", "left", "right"}
EASINGS = {"linear", "ease_out", "ease_in_out"}
ROTATION_PATTERNS = {"none", "alternate", "clockwise", "counterclockwise"}


def motion_plan(
    preset: str,
    start_frame: int,
    duration_frames: int,
    direction: str = "top",
    x_offset: float = 0.025,
    y_offset: float = 0.18,
    scale_start: float = 0.94,
    opacity_start: float = 0.0,
    rotation: float = 1.5,
    easing: str = "ease_out",
    settle: bool = True,
) -> dict:
    validate_preset(preset)
    if isinstance(start_frame, bool) or not isinstance(start_frame, int) or start_frame < 0:
        raise ValidationError("start_frame deve essere un intero non negativo")
    if direction not in DIRECTIONS:
        raise ValidationError("direction non consentita")
    if easing not in EASINGS:
        raise ValidationError("easing non consentito")
    if isinstance(duration_frames, bool) or not isinstance(duration_frames, int) or not 2 <= duration_frames <= 300:
        raise ValidationError("duration_frames deve essere tra 2 e 300")
    x = finite_float(x_offset, "x_offset", -0.5, 0.5)
    y = finite_float(y_offset, "y_offset", 0.0, 1.0)
    scale = finite_float(scale_start, "scale_start", 0.1, 2.0)
    opacity = finite_float(opacity_start, "opacity_start", 0.0, 1.0)
    angle = finite_float(rotation, "rotation", -15.0, 15.0)
    dx, dy = 0.0, 0.0
    if direction == "top": dy = -y
    elif direction == "bottom": dy = y
    elif direction == "left": dx = -abs(x or 0.15)
    else: dx = abs(x or 0.15)
    if direction in {"top", "bottom"}: dx = x
    end = int(start_frame) + int(duration_frames)
    keys = [
        {"frame": int(start_frame), "x": dx, "y": dy, "scale": scale, "opacity": opacity, "rotation": angle},
        {"frame": end, "x": 0.0, "y": 0.0, "scale": 1.0, "opacity": 1.0, "rotation": 0.0},
    ]
    if settle and preset in {"ARPHE_SOFT_DROP", "ARPHE_CTA_SETTLE"}:
        settle_frame = max(int(start_frame) + 1, end - max(2, int(duration_frames) // 5))
        keys.insert(1, {"frame": settle_frame, "x": 0.0, "y": 0.012, "scale": 1.012, "opacity": 1.0, "rotation": -angle * 0.15})
    return {"preset": preset, "easing": easing, "settle": bool(settle), "keys": keys}


def stack_plan(card_ids: list[str], start_frame: int, stagger_frames: int, overlap: float,
               direction: str, rotation_pattern: str, position_offsets: list[float] | None,
               scale_start: float, opacity_start: float, duration_frames: int,
               easing: str, settle: bool) -> list[dict]:
    if not 1 <= len(card_ids) <= 8 or len(set(card_ids)) != len(card_ids):
        raise ValidationError("card_ids deve contenere 1-8 ID unici")
    if rotation_pattern not in ROTATION_PATTERNS:
        raise ValidationError("rotation_pattern non consentito")
    if isinstance(start_frame, bool) or not isinstance(start_frame, int) or start_frame < 0:
        raise ValidationError("start_frame deve essere un intero non negativo")
    if isinstance(stagger_frames, bool) or not isinstance(stagger_frames, int) or not 0 <= stagger_frames <= 120:
        raise ValidationError("stagger_frames non valido")
    overlap_value = finite_float(overlap, "overlap", 0.0, 1.0)
    offsets = position_offsets or [0.018, 0.025]
    if not 1 <= len(offsets) <= 8:
        raise ValidationError("position_offsets deve contenere 1-8 valori")
    plans = []
    for index, card_id in enumerate(card_ids):
        offset = finite_float(offsets[index % len(offsets)], "position_offset", -0.25, 0.25)
        rotation = 0.0
        if rotation_pattern == "alternate": rotation = 1.2 if index % 2 == 0 else -1.2
        elif rotation_pattern == "clockwise": rotation = 1.2
        elif rotation_pattern == "counterclockwise": rotation = -1.2
        frame = int(start_frame) + index * int(round(int(stagger_frames) * (1.0 - overlap_value)))
        plan = motion_plan("ARPHE_PAPER_STACK", frame, duration_frames, direction, offset, 0.18,
                           scale_start, opacity_start, rotation, easing, settle)
        plan.update({"card_id": card_id, "z_order": index + 1, "rest_x": offset * index, "rest_y": 0.018 * index})
        plans.append(plan)
    return plans
