from __future__ import annotations

from typing import Any

from .safety import ValidationError
from .fusion_tools import _media_out, _new_tool, connect_input
from .resolve_connection import safe_call


def reframe_transform_plan(action: dict[str, Any], output_width: int, output_height: int) -> dict[str, Any]:
    """Return the explicit, non-animated Transform parameters for one approved reframe."""
    anchor = action.get("anchor")
    if (not isinstance(output_width, int) or not isinstance(output_height, int)
            or output_width <= 0 or output_height <= 0):
        raise ValidationError("dimensioni output REFRAME non valide")
    if not isinstance(anchor, dict) or not all(isinstance(anchor.get(key), (int, float)) and 0.1 <= float(anchor[key]) <= 0.9 for key in ("x", "y")):
        raise ValidationError("anchor REFRAME non sicuro")
    return {"center": {"x": float(anchor["x"]), "y": float(anchor["y"])}, "zoom": 1.0,
            "output": {"width": output_width, "height": output_height}}


def apply_transform_parameters(tool: object, plan: dict[str, Any]) -> bool:
    """Apply and read back the two Transform controls used by a static reframe."""
    center = plan.get("center")
    zoom = plan.get("zoom")
    if not isinstance(center, dict) or not isinstance(zoom, (int, float)):
        raise ValidationError("piano Transform REFRAME non valido")
    value = {1: float(center["x"]), 2: float(center["y"]), 3: 0.0}
    try:
        tool.SetInput("Center", value)
        tool.SetInput("Size", float(zoom))
        return tool.GetInput("Center") == value and float(tool.GetInput("Size")) == float(zoom)
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
    return apply_transform_parameters(transform, plan)


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
