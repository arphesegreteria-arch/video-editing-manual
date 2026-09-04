from __future__ import annotations

from typing import Any
import uuid

from .config import CreativeConfig
from .feature_flags import require_capability
from .registry import Registry
from .resolve_connection import safe_call
from .safety import ValidationError, arphe_name, require_arphe_name, validate_color_role, validate_frame_range


def _id(kind: str) -> str:
    return f"ARPHE_{kind}_{uuid.uuid4().hex[:10].upper()}"


def _timeline_allowed(project: Any, timeline: Any, config: CreativeConfig, registry: Registry) -> None:
    project_name = str(safe_call(project, "GetName") or "")
    name = str(safe_call(timeline, "GetName") or "")
    if not name.startswith("ARPHE_"):
        raise ValidationError("Le write creative richiedono una timeline con prefisso ARPHE_")
    if not (registry.timeline_allowed(project_name, name) or name in config.allowed_timelines):
        raise ValidationError("Timeline non creata o allowlisted per le write creative")


def _all_items(timeline: Any) -> list[Any]:
    items: list[Any] = []
    for track in range(1, int(safe_call(timeline, "GetTrackCount", "video") or 0) + 1):
        items.extend(safe_call(timeline, "GetItemListInTrack", "video", track) or [])
    return items


def _item_id(item: Any) -> str:
    return str(safe_call(item, "GetUniqueId") or safe_call(item, "GetName") or "")


def find_composition(timeline: Any, registry: Registry, composition_id: str) -> tuple[Any, Any]:
    record = registry.element(composition_id)
    if not record or record.get("kind") != "composition":
        raise ValidationError("composition_id non creato dal bridge")
    for item in _all_items(timeline):
        if _item_id(item) == record.get("timeline_item_id") or safe_call(item, "GetName") == record.get("timeline_item_name"):
            comp = safe_call(item, "GetFusionCompByIndex", 1)
            if comp:
                return item, comp
    raise ValidationError("Composizione registrata non trovata nella timeline corrente")


def _tool(comp: Any, name: str) -> Any:
    return safe_call(comp, "FindTool", name)


def _new_tool(comp: Any, reg_id: str, name: str) -> Any:
    tool = safe_call(comp, "AddTool", reg_id, -32768, -32768)
    if not tool:
        raise RuntimeError(f"Fusion AddTool fallita: {reg_id}")
    safe_call(tool, "SetAttrs", {"TOOLS_Name": name})
    return tool


def _set(tool: Any, name: str, value: Any, frame: int | None = None) -> bool:
    try:
        return bool(tool.SetInput(name, value) if frame is None else tool.SetInput(name, value, frame))
    except Exception:
        return False


def _rgb(hex_value: str, alpha: float = 1.0) -> dict[str, float]:
    value = hex_value.lstrip("#")
    return {"r": int(value[0:2], 16) / 255.0, "g": int(value[2:4], 16) / 255.0,
            "b": int(value[4:6], 16) / 255.0, "a": alpha}


def _set_color(tool: Any, color: dict[str, float]) -> None:
    for key, value in (("TopLeftRed", color["r"]), ("TopLeftGreen", color["g"]),
                       ("TopLeftBlue", color["b"]), ("TopLeftAlpha", color["a"])):
        _set(tool, key, value)


def _media_out(comp: Any) -> Any:
    for tool in (safe_call(comp, "GetToolList", False) or {}).values():
        if (safe_call(tool, "GetAttrs") or {}).get("TOOLS_RegID") == "MediaOut":
            return tool
    return None


def _connected_input_tool(media_out: Any) -> Any:
    try:
        input_socket = media_out.FindMainInput(1)
        output_socket = input_socket.GetConnectedOutput() if input_socket else None
        return output_socket.GetTool() if output_socket else None
    except Exception:
        return None


def add_layer(comp: Any, foreground: Any, merge_name: str) -> Any:
    media_out = _media_out(comp)
    if not media_out:
        raise RuntimeError("MediaOut non trovato")
    background = _connected_input_tool(media_out)
    if background is None:
        media_out.ConnectInput("Input", foreground)
        return None
    merge = _new_tool(comp, "Merge", merge_name)
    merge.ConnectInput("Background", background)
    merge.ConnectInput("Foreground", foreground)
    media_out.ConnectInput("Input", merge)
    return merge


def set_visibility_window(comp: Any, merge: Any, start_frame: int, end_frame: int) -> bool:
    """Keep an element visible only in the validated inclusive/exclusive frame window."""
    if not merge:
        return False
    start, end = validate_frame_range(start_frame, end_frame)
    try:
        blend = comp.BezierSpline()
        if start > 0:
            blend[start - 1] = 0.0
        blend[start] = 1.0
        blend[end - 1] = 1.0
        blend[end] = 0.0
        merge.Blend = blend
        return True
    except Exception:
        return False


def create_composition(project: Any, timeline: Any, config: CreativeConfig, registry: Registry,
                       name: str, start_frame: int, end_frame: int) -> dict:
    require_capability("CAP_FUSION", config, None, project, timeline)
    _timeline_allowed(project, timeline, config, registry)
    start, end = validate_frame_range(start_frame, end_frame)
    item_name = arphe_name(name, "FUSION_COMP")
    # Resolve inserts at the current playhead. Gate B must visually verify placement;
    # no destructive reposition fallback is attempted.
    item = safe_call(timeline, "InsertFusionCompositionIntoTimeline")
    if not item:
        return {"ok": False, "action": "create_fusion_composition", "stage": "insert"}
    safe_call(item, "SetName", item_name)
    comp = safe_call(item, "GetFusionCompByIndex", 1)
    if not comp:
        return {"ok": False, "action": "create_fusion_composition", "stage": "get_comp", "timeline_item": item_name}
    safe_call(comp, "SetAttrs", {"COMPN_RenderStart": start, "COMPN_RenderEnd": end})
    canvas = _new_tool(comp, "Background", "ARPHE_CANVAS")
    _set_color(canvas, _rgb(config.palette["ivory"], 0.0))
    media_out = _media_out(comp)
    if media_out:
        media_out.ConnectInput("Input", canvas)
    composition_id = _id("COMP")
    registry.add_element(composition_id, {"kind": "composition", "timeline": safe_call(timeline, "GetName"),
                                          "timeline_item_id": _item_id(item), "timeline_item_name": safe_call(item, "GetName"),
                                          "start_frame": start, "end_frame": end})
    return {"ok": bool(media_out), "action": "create_fusion_composition", "composition_id": composition_id,
            "timeline_item": safe_call(item, "GetName"), "requested_frame_range": [start, end],
            "placement_note": "Insert at current Resolve playhead; verify manually in Gate B.", "status": "PENDING"}


def add_background(project: Any, timeline: Any, config: CreativeConfig, registry: Registry,
                   composition_id: str, color_role: str) -> dict:
    require_capability("CAP_FUSION", config, None, project, timeline)
    validate_color_role(color_role)
    _, comp = find_composition(timeline, registry, composition_id)
    canvas = _tool(comp, "ARPHE_CANVAS")
    if not canvas:
        raise RuntimeError("Canvas ARPHE non trovato")
    _set_color(canvas, _rgb(config.palette[color_role]))
    return {"ok": True, "action": "add_brand_background", "composition_id": composition_id,
            "color_role": color_role, "status": "PENDING"}


def add_text(project: Any, timeline: Any, config: CreativeConfig, registry: Registry,
             composition_id: str, text: str, start_frame: int, end_frame: int,
             style_role: str, size: float = 0.06) -> dict:
    require_capability("CAP_FUSION", config, None, project, timeline)
    validate_frame_range(start_frame, end_frame)
    validate_color_role(style_role)
    if not isinstance(text, str) or not text.strip() or len(text) > 800:
        raise ValidationError("Testo richiesto, massimo 800 caratteri")
    _, comp = find_composition(timeline, registry, composition_id)
    element_id = _id("TEXT")
    text_tool = _new_tool(comp, "TextPlus", element_id)
    _set(text_tool, "StyledText", text)
    _set(text_tool, "Size", float(size))
    color = _rgb(config.palette[style_role])
    for key, value in (("Red1", color["r"]), ("Green1", color["g"]), ("Blue1", color["b"]), ("Alpha1", color["a"])):
        _set(text_tool, key, value)
    merge_name = _id("MERGE")
    merge = add_layer(comp, text_tool, merge_name)
    timing_applied = set_visibility_window(comp, merge, start_frame, end_frame)
    registry.add_element(element_id, {"kind": "text", "composition_id": composition_id,
                                      "tool_name": element_id, "merge_name": merge_name if merge else None,
                                      "start_frame": int(start_frame), "end_frame": int(end_frame)})
    return {"ok": True, "action": "add_text_plus", "composition_id": composition_id,
            "element_id": element_id, "style_role": style_role,
            "timing_applied": timing_applied, "status": "PENDING"}


def retime(project: Any, timeline: Any, config: CreativeConfig, registry: Registry,
           composition_id: str, duration_frames: int) -> dict:
    require_capability("CAP_FUSION", config, None, project, timeline)
    record = registry.element(composition_id)
    if not record:
        raise ValidationError("composition_id non registrato")
    if isinstance(duration_frames, bool) or not isinstance(duration_frames, int):
        raise ValidationError("duration_frames deve essere un intero")
    start = int(record["start_frame"])
    _, end = validate_frame_range(start, start + duration_frames)
    _, comp = find_composition(timeline, registry, composition_id)
    result = bool(safe_call(comp, "SetAttrs", {"COMPN_RenderStart": start, "COMPN_RenderEnd": end}))
    return {"ok": result, "action": "retime_creative_duration", "composition_id": composition_id,
            "frame_range": [start, end], "timeline_item_duration_adjusted": False,
            "limitation": "Fusion work range updated; timeline item trim requires manual Gate validation.", "status": "PENDING"}
