from __future__ import annotations

from typing import Any
import math
import hashlib
import json
import re

from .safety import ValidationError
from .fusion_tools import _media_out, _new_tool, connect_input, _connected_input_tool
from .resolve_connection import safe_call


def _validated_motion(action: dict[str, Any], duration: int) -> dict[str, Any] | None:
    raw = action.get("motion")
    if raw is None:
        return None
    if not isinstance(raw, dict) or raw.get("preset") != "CAMERA_ZOOM":
        raise ValidationError("Motion ritirato o non supportato: usare CAMERA_ZOOM")
    if not 2 <= duration <= 9000:
        raise ValidationError("Durata CAMERA_ZOOM fuori limite [2,9000]")
    for key in ("start_zoom", "end_zoom"):
        value = raw.get(key)
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or not math.isfinite(value) or not 1. <= value <= 1.6):
            raise ValidationError("Scala CAMERA_ZOOM non sicura")
    if raw["start_zoom"] == raw["end_zoom"]:
        raise ValidationError("CAMERA_ZOOM richiede scale diverse")
    if raw.get("easing", "smooth") not in ("linear", "smooth"):
        raise ValidationError("Easing CAMERA_ZOOM non supportato")
    result = {"preset": "CAMERA_ZOOM", "start_zoom": float(raw["start_zoom"]),
              "end_zoom": float(raw["end_zoom"]), "easing": raw.get("easing", "smooth")}
    if "points" in raw:
        points = raw["points"]
        if not isinstance(points, list) or not 2 <= len(points) <= 64:
            raise ValidationError("CAMERA_ZOOM points richiede da 2 a 64 punti")
        checked = []
        for point in points:
            if not isinstance(point, dict) or set(point) != {"frame", "zoom"}:
                raise ValidationError("Punto CAMERA_ZOOM non valido")
            frame, zoom = point["frame"], point["zoom"]
            if (isinstance(frame, bool) or not isinstance(frame, int) or not 0 <= frame < duration
                    or isinstance(zoom, bool) or not isinstance(zoom, (int, float))
                    or not math.isfinite(zoom) or not 1. <= zoom <= 1.6
                    or (checked and frame <= checked[-1]["frame"])):
                raise ValidationError("Punti CAMERA_ZOOM non ordinati o fuori limite")
            checked.append({"frame": frame, "zoom": float(zoom)})
        if (checked[0] != {"frame": 0, "zoom": result["start_zoom"]}
                or checked[-1] != {"frame": duration - 1, "zoom": result["end_zoom"]}):
            raise ValidationError("Estremi points CAMERA_ZOOM diversi dal range")
        result["points"] = checked
    return result


def reframe_transform_plan(action: dict[str, Any], output_width: int, output_height: int,
                           *, local_start: int = 0, local_end: int | None = None) -> dict[str, Any]:
    """Return explicit Transform parameters for one approved static or animated reframe."""
    anchor = action.get("anchor")
    if (not isinstance(output_width, int) or not isinstance(output_height, int)
            or output_width <= 0 or output_height <= 0):
        raise ValidationError("dimensioni output REFRAME non valide")
    if not isinstance(anchor, dict) or not all(isinstance(anchor.get(key), (int, float)) and 0.1 <= float(anchor[key]) <= 0.9 for key in ("x", "y")):
        raise ValidationError("anchor REFRAME non sicuro")
    duration = (local_end - local_start) if local_end is not None else 0
    motion = _validated_motion(action, duration) if action.get("motion") is not None else None
    replacement = action.get("replace_motion_node")
    if replacement is not None and (motion is None or not isinstance(replacement, str)
            or not re.fullmatch(r"ARPHE_CAMERA_ZOOM_[0-9a-f]{16}", replacement)):
        raise ValidationError("Sostituzione CAMERA_ZOOM richiede un nodo posseduto esplicito")
    if motion is None:
        return {"center": {"x": float(anchor["x"]), "y": float(anchor["y"])}, "zoom": 1.0,
                "output": {"width": output_width, "height": output_height}}
    keys = []
    points = motion.get("points", [{"frame": 0, "zoom": motion["start_zoom"]},
                                    {"frame": duration - 1, "zoom": motion["end_zoom"]}])
    segment = 0
    for index in range(duration):
        while segment < len(points) - 2 and index > points[segment + 1]["frame"]:
            segment += 1
        left, right = points[segment:segment + 2]
        amount = (index - left["frame"]) / (right["frame"] - left["frame"])
        if motion["easing"] == "smooth":
            amount = amount * amount * (3 - 2 * amount)
        keys.append({"frame": local_start + index, "zoom": left["zoom"]
                     + (right["zoom"] - left["zoom"]) * amount})
    return {
        "center": {"x": 0.5, "y": 0.5},
        "pivot": {"x": float(anchor["x"]), "y": float(anchor["y"])},
        "zoom": motion["start_zoom"],
        "motion": motion,
        "motion_keys": keys,
        **({"replace_motion_node": replacement} if replacement is not None else {}),
        "output": {"width": output_width, "height": output_height},
    }


def apply_transform_parameters(tool: object, plan: dict[str, Any], comp: object | None = None) -> bool:
    """Apply and read back the two Transform controls used by a static reframe."""
    center = plan.get("center")
    zoom = plan.get("zoom")
    if not isinstance(center, dict) or not isinstance(zoom, (int, float)):
        raise ValidationError("piano Transform REFRAME non valido")
    value = {1: float(center["x"]), 2: float(center["y"]), 3: 0.0}
    try:
        tool.SetInput("Center", value)
        pivot = plan.get("pivot")
        if isinstance(pivot, dict):
            tool.SetInput("Pivot", {1: float(pivot["x"]), 2: float(pivot["y"]), 3: 0.0})
        keys = plan.get("motion_keys")
        if keys is None:
            tool.SetInput("Size", float(zoom))
            return tool.GetInput("Center") == value and float(tool.GetInput("Size")) == float(zoom)
        if comp is None or not isinstance(keys, list) or len(keys) < 2:
            raise ValidationError("spline CAMERA_ZOOM non disponibile")
        attrs = safe_call(comp, "GetAttrs") or {}
        offset = int(attrs.get("COMPN_RenderStart", attrs.get("COMPN_GlobalStart", 0)))
        spline = comp.BezierSpline()
        if spline is None:
            raise ValidationError("spline CAMERA_ZOOM non disponibile")
        # Resolve 21 drops keys from detached modifiers when they are attached.
        # Give Fusion ownership first, then populate and verify the animation.
        tool.Size = spline
        keyframes = {int(key["frame"]) + offset: {1: float(key["zoom"]), "Flags": {"Linear": True}}
                     for key in keys}
        if safe_call(spline, "SetKeyFrames", keyframes, True) is False:
            raise ValidationError("Keyframe CAMERA_ZOOM rifiutati")
        return verify_transform_parameters(tool, plan, comp)
    except Exception as exc:
        raise ValidationError(f"Transform REFRAME non applicabile: {exc}") from exc


def verify_transform_parameters(tool: object, plan: dict[str, Any], comp: object) -> bool:
    center = plan["center"]
    if safe_call(tool, "GetInput", "Center") != {1: float(center["x"]), 2: float(center["y"]), 3: 0.}:
        raise ValidationError("Read-back Center CAMERA_ZOOM fallito")
    pivot = plan.get("pivot")
    if pivot and safe_call(tool, "GetInput", "Pivot") != {1: float(pivot["x"]), 2: float(pivot["y"]), 3: 0.}:
        raise ValidationError("Read-back Pivot CAMERA_ZOOM fallito")
    keys = plan.get("motion_keys")
    if not keys:
        actual = safe_call(tool, "GetInput", "Size")
        return isinstance(actual, (int, float)) and math.isclose(actual, plan["zoom"], abs_tol=1e-5)
    attrs = safe_call(comp, "GetAttrs") or {}
    offset = int(attrs.get("COMPN_RenderStart", attrs.get("COMPN_GlobalStart", 0)))
    readback = []
    indices = {0, len(keys)//4, len(keys)//2, 3*len(keys)//4, len(keys)-1}
    indices.update(point["frame"] for point in plan.get("motion", {}).get("points", []))
    for index in sorted(indices):
        key = keys[index]
        actual = safe_call(tool, "GetInput", "Size", int(key["frame"]) + offset)
        if not isinstance(actual, (int, float)) or not math.isclose(actual, key["zoom"], abs_tol=1e-5):
            raise ValidationError("Read-back intermedio CAMERA_ZOOM fallito")
        readback.append({"composition_frame": int(key["frame"]) + offset, "zoom": actual})
    plan["motion_readback"] = readback
    return True


def _delete_camera_tool(comp: object, tool: object) -> None:
    name = (safe_call(tool, "GetAttrs") or {}).get("TOOLS_Name")
    if not str(name or "").startswith("ARPHE_CAMERA_ZOOM_"):
        raise ValidationError("Rimozione consentita soltanto per un nodo camera posseduto")
    delete = getattr(tool, "Delete", None)
    if callable(delete):
        delete()
    else:
        safe_call(comp, "DeleteTool", tool)
    if any((safe_call(candidate, "GetAttrs") or {}).get("TOOLS_Name") == name
           for candidate in (safe_call(comp, "GetToolList", False) or {}).values()):
        raise ValidationError("Rimozione nodo CAMERA_ZOOM non verificata")


def apply_fusion_reframe(item: object, plan: dict[str, Any]) -> bool:
    count = safe_call(item, "GetFusionCompCount")
    if isinstance(count, int) and count > 1:
        raise ValidationError("Selezione composizione REFRAME ambigua")
    comp = safe_call(item, "GetFusionCompByIndex", 1) or safe_call(item, "AddFusionComp")
    if not comp:
        raise ValidationError("Composizione Fusion REFRAME non disponibile")
    media_out = _media_out(comp)
    upstream = _connected_input_tool(media_out) if media_out is not None else None
    if media_out is None or upstream is None:
        raise ValidationError("Connessione MediaOut REFRAME non verificabile")
    encoded = json.dumps({key: value for key, value in plan.items()
                          if key not in {"motion_readback", "replace_motion_node"}}, sort_keys=True)
    node_name = "ARPHE_CAMERA_ZOOM_" + hashlib.sha256(encoded.encode()).hexdigest()[:16]
    tools = list((safe_call(comp, "GetToolList", False) or {}).values())
    owned = [tool for tool in tools
             if str((safe_call(tool, "GetAttrs") or {}).get("TOOLS_Name", "")).startswith("ARPHE_CAMERA_ZOOM")
             and ((safe_call(tool, "GetAttrs") or {}).get("TOOLS_RegID")
                  or (safe_call(tool, "GetAttrs") or {}).get("TOOLST_RegID")) == "Transform"]
    replacing = None
    original_upstream = upstream
    if owned:
        matching = [tool for tool in owned if (safe_call(tool, "GetAttrs") or {}).get("TOOLS_Name") == node_name]
        if (len(owned) == 1 and len(matching) == 1
                and (safe_call(upstream, "GetAttrs") or {}).get("TOOLS_Name") == node_name):
            if _connected_input_tool(matching[0]) is None:
                raise ValidationError("Ingresso CAMERA_ZOOM esistente non verificabile")
            return verify_transform_parameters(matching[0], plan, comp)
        expected = plan.get("replace_motion_node")
        if (len(owned) != 1 or not expected
                or (safe_call(owned[0], "GetAttrs") or {}).get("TOOLS_Name") != expected
                or (safe_call(upstream, "GetAttrs") or {}).get("TOOLS_Name") != expected):
            observed = [str((safe_call(tool, "GetAttrs") or {}).get("TOOLS_Name", ""))[:80]
                        for tool in owned[:4]]
            raise ValidationError("CAMERA_ZOOM esistente diverso dal piano; nodi posseduti: "
                                  + ", ".join(observed))
        replacing = owned[0]
        upstream = _connected_input_tool(replacing)
        if upstream is None:
            raise ValidationError("Ingresso CAMERA_ZOOM da sostituire non verificabile")
    elif plan.get("replace_motion_node"):
        raise ValidationError("CAMERA_ZOOM da sostituire assente")
    transform = None
    safe_call(comp, "Lock")
    try:
        transform = _new_tool(comp, "Transform", node_name)
        if not connect_input(transform, "Input", upstream):
            raise ValidationError("Collegamento ingresso CAMERA_ZOOM fallito")
        if not apply_transform_parameters(transform, plan, comp):
            raise ValidationError("Read-back CAMERA_ZOOM non riuscito")
        if not connect_input(media_out, "Input", transform):
            raise ValidationError("Collegamento uscita CAMERA_ZOOM fallito")
        if (safe_call(_connected_input_tool(media_out), "GetAttrs") or {}).get("TOOLS_Name") != node_name:
            raise ValidationError("Read-back collegamento uscita CAMERA_ZOOM fallito")
        if replacing is not None:
            _delete_camera_tool(comp, replacing)
        return True
    except Exception:
        restored = connect_input(media_out, "Input", original_upstream)
        restored = restored and (
            (safe_call(_connected_input_tool(media_out), "GetAttrs") or {}).get("TOOLS_Name")
            == (safe_call(original_upstream, "GetAttrs") or {}).get("TOOLS_Name"))
        if transform is not None:
            _delete_camera_tool(comp, transform)
        if not restored:
            raise ValidationError("Rollback CAMERA_ZOOM fallito")
        raise
    finally:
        safe_call(comp, "Unlock")


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
    motion = _validated_motion(action, end - start)
    return {"range": (start, end), "target": dict(target),
            "anchor": {"x": float(anchor["x"]), "y": float(anchor["y"])},
            "motion": motion}
