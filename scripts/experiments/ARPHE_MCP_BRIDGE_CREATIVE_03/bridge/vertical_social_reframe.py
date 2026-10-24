from __future__ import annotations

import math
from typing import Any

from .safety import ValidationError
from .fusion_tools import _media_out, _new_tool, connect_input
from .resolve_connection import safe_call


def _rotation_keys(action: dict[str, Any], start: int, end: int) -> list[tuple[int, float]]:
    raw = action.get("rotation_keys")
    if raw is None:
        return []
    if not isinstance(raw, list) or len(raw) < 2:
        raise ValidationError("rotation_keys REFRAME richiede almeno due punti")
    keys: list[tuple[int, float]] = []
    for entry in raw:
        if not isinstance(entry, dict):
            raise ValidationError("rotation_keys REFRAME non valide")
        frame, angle = entry.get("frame"), entry.get("angle")
        if (not isinstance(frame, int) or isinstance(frame, bool)
                or not isinstance(angle, (int, float)) or isinstance(angle, bool)
                or not math.isfinite(float(angle)) or abs(float(angle)) > 7.5):
            raise ValidationError("rotation_keys REFRAME non sicure")
        keys.append((frame, float(angle)))
    if any(frame < start or frame >= end for frame, _ in keys):
        raise ValidationError("rotation_keys REFRAME fuori range")
    if any(current[0] >= following[0] for current, following in zip(keys, keys[1:])):
        raise ValidationError("rotation_keys REFRAME non ordinate")
    if keys[0][0] != start or keys[-1][0] != end - 1:
        raise ValidationError("rotation_keys REFRAME deve ancorare entrambi gli estremi")
    return keys


def _center_keys(action: dict[str, Any], start: int, end: int) -> list[tuple[int, float, float]]:
    raw = action.get("center_keys")
    if raw is None:
        return []
    if not isinstance(raw, list) or len(raw) < 2:
        raise ValidationError("center_keys REFRAME richiede almeno due punti")
    keys: list[tuple[int, float, float]] = []
    for entry in raw:
        if not isinstance(entry, dict):
            raise ValidationError("center_keys REFRAME non valide")
        frame, x, y = entry.get("frame"), entry.get("x"), entry.get("y")
        if (not isinstance(frame, int) or isinstance(frame, bool)
                or not isinstance(x, (int, float)) or isinstance(x, bool)
                or not isinstance(y, (int, float)) or isinstance(y, bool)
                or not math.isfinite(float(x)) or not math.isfinite(float(y))
                or not 0.1 <= float(x) <= 0.9 or not 0.1 <= float(y) <= 0.9):
            raise ValidationError("center_keys REFRAME non sicure")
        keys.append((frame, float(x), float(y)))
    if any(frame < start or frame >= end for frame, _, _ in keys):
        raise ValidationError("center_keys REFRAME fuori range")
    if any(current[0] >= following[0] for current, following in zip(keys, keys[1:])):
        raise ValidationError("center_keys REFRAME non ordinate")
    if keys[0][0] != start or keys[-1][0] != end - 1:
        raise ValidationError("center_keys REFRAME deve ancorare entrambi gli estremi")
    return keys


def _zoom(action: dict[str, Any]) -> float:
    value = action.get("zoom", 1.0)
    if (not isinstance(value, (int, float)) or isinstance(value, bool)
            or not math.isfinite(float(value)) or not 1.0 <= float(value) <= 1.15):
        raise ValidationError("zoom REFRAME non sicuro")
    return float(value)


def reframe_transform_plan(action: dict[str, Any], output_width: int, output_height: int) -> dict[str, Any]:
    """Return explicit static or keyframed Transform parameters for an approved reframe."""
    anchor = action.get("anchor")
    if (not isinstance(output_width, int) or not isinstance(output_height, int)
            or output_width <= 0 or output_height <= 0):
        raise ValidationError("dimensioni output REFRAME non valide")
    if not isinstance(anchor, dict) or not all(isinstance(anchor.get(key), (int, float)) and 0.1 <= float(anchor[key]) <= 0.9 for key in ("x", "y")):
        raise ValidationError("anchor REFRAME non sicuro")
    raw_range = action.get("range") or {}
    start, end = raw_range.get("start_frame"), raw_range.get("end_frame")
    rotation_keys: list[tuple[int, float]] = []
    center_keys: list[tuple[int, float, float]] = []
    if action.get("rotation_keys") is not None or action.get("center_keys") is not None:
        if not isinstance(start, int) or not isinstance(end, int) or start >= end:
            raise ValidationError("range REFRAME non valido")
        rotation_keys = _rotation_keys(action, start, end)
        center_keys = _center_keys(action, start, end)
    return {
        "center": {"x": float(anchor["x"]), "y": float(anchor["y"])},
        "zoom": _zoom(action),
        "rotation_keys": [
            {"frame": frame - int(start), "angle": angle} for frame, angle in rotation_keys
        ],
        "center_keys": [
            {"frame": frame - int(start), "x": x, "y": y}
            for frame, x, y in center_keys
        ],
        "output": {"width": output_width, "height": output_height},
    }


def apply_transform_parameters(tool: object, plan: dict[str, Any], comp: object | None = None) -> bool:
    """Apply and read back static framing plus optional Resolve-owned rotation keys."""
    center = plan.get("center")
    zoom = plan.get("zoom")
    if not isinstance(center, dict) or not isinstance(zoom, (int, float)):
        raise ValidationError("piano Transform REFRAME non valido")
    value = {1: float(center["x"]), 2: float(center["y"]), 3: 0.0}
    try:
        center_keys = plan.get("center_keys") or []
        if center_keys:
            if comp is None:
                raise ValidationError("Composizione Fusion richiesta per center_keys REFRAME")
            tool.Center = comp.BezierSpline()
            animated_center = tool.Center
            for key in center_keys:
                animated_center[int(key["frame"])] = {
                    1: float(key["x"]), 2: float(key["y"]), 3: 0.0,
                }
            if any(
                abs(float(animated_center[int(key["frame"])][1]) - float(key["x"])) > 1e-6
                or abs(float(animated_center[int(key["frame"])][2]) - float(key["y"])) > 1e-6
                for key in center_keys
            ):
                return False
        else:
            tool.SetInput("Center", value)
        tool.SetInput("Size", float(zoom))
        keys = plan.get("rotation_keys") or []
        if keys:
            if comp is None:
                raise ValidationError("Composizione Fusion richiesta per rotation_keys REFRAME")
            tool.Angle = comp.BezierSpline()
            angle = tool.Angle
            for key in keys:
                angle[int(key["frame"])] = float(key["angle"])
            if any(abs(float(angle[int(key["frame"])]) - float(key["angle"])) > 1e-6
                   for key in keys):
                return False
        center_ok = bool(center_keys) or tool.GetInput("Center") == value
        return center_ok and float(tool.GetInput("Size")) == float(zoom)
    except Exception as exc:
        raise ValidationError(f"Transform REFRAME non applicabile: {exc}") from exc


def apply_fusion_reframe(item: object, plan: dict[str, Any]) -> bool:
    comp = safe_call(item, "AddFusionComp") or safe_call(item, "GetFusionCompByIndex", 1)
    if not comp:
        raise ValidationError("Composizione Fusion REFRAME non disponibile")
    tools = list((safe_call(comp, "GetToolList", False) or {}).values())
    media_in = next((tool for tool in tools if (safe_call(tool, "GetAttrs") or {}).get("TOOLS_RegID") == "MediaIn"), None)
    media_out = _media_out(comp)
    if not media_in or not media_out:
        raise ValidationError("MediaIn/MediaOut REFRAME non trovati")
    transform = _new_tool(comp, "Transform", "ARPHE_VERTICAL_REFRAME")
    if not connect_input(transform, "Input", media_in) or not connect_input(media_out, "Input", transform):
        raise ValidationError("Collegamento Transform REFRAME fallito")
    return apply_transform_parameters(transform, plan, comp)


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
    rotation_keys = _rotation_keys(action, start, end)
    center_keys = _center_keys(action, start, end)
    return {
        "range": (start, end), "target": dict(target),
        "anchor": {"x": float(anchor["x"]), "y": float(anchor["y"])},
        "zoom": _zoom(action), "rotation_keys": rotation_keys, "center_keys": center_keys,
    }
