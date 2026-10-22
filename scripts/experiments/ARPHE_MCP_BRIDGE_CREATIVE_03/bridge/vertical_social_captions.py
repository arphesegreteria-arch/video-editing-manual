from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from .carabellese_checkpoint import timeline_content_fingerprint
from .fusion_tools import (_media_out, _new_tool, _rgb, _set,
                           add_layer, connect_input, set_visibility_window)
from .resolve_connection import safe_call
from .safety import ValidationError
from .vertical_social_overlay import create_overlay_composition


def lower_caption_layout(font_scale: float = 1.0) -> dict[str, Any]:
    """Return the story-safe lower-third geometry in Fusion coordinates.

    Fusion's Y origin is at the bottom; the reported bounds use the usual
    screen convention (top to bottom) so they can be checked against the
    Graphic Kit safe-area contract.
    """
    if isinstance(font_scale, bool) or not isinstance(font_scale, (int, float)) or not 1.0 <= font_scale <= 1.2:
        raise ValidationError("font_scale CAPTIONS deve essere tra 1.0 e 1.2")
    center_x, center_y = 0.46, 0.27
    width, height = 0.68, 0.08 * float(font_scale)
    text_width, text_height = 0.62, 0.065 * float(font_scale)
    bounds = {
        "left": round(center_x - width / 2, 4),
        "right": round(center_x + width / 2, 4),
        "top": round(1 - (center_y + height / 2), 4),
        "bottom": round(1 - (center_y - height / 2), 4),
    }
    if not (bounds["left"] >= 0.08 and bounds["right"] <= 0.84
            and bounds["top"] >= 0.10 and bounds["bottom"] <= 0.82):
        raise ValidationError("Layout CAPTIONS fuori dalla safe area Story")
    text_frame = {
        "left": round(center_x - text_width / 2, 4),
        "right": round(center_x + text_width / 2, 4),
        "top": round(1 - (center_y + text_height / 2), 4),
        "bottom": round(1 - (center_y - text_height / 2), 4),
    }
    if not (bounds["left"] <= text_frame["left"] <= text_frame["right"] <= bounds["right"]
            and bounds["top"] <= text_frame["top"] <= text_frame["bottom"] <= bounds["bottom"]):
        raise ValidationError("Frame testo CAPTIONS fuori dalla card sicura")
    return {"center": {"x": center_x, "y": center_y},
            "width": width, "height": height, "bounds": bounds,
            "text_width": text_width, "text_height": text_height,
            "text_frame": text_frame}


def cues_before_frame(cues: tuple[dict[str, Any], ...], cutoff_frame: int) -> tuple[dict[str, Any], ...]:
    """Keep spoken cues before a CTA and reject a cue that would run into it."""
    retained: list[dict[str, Any]] = []
    for cue in cues:
        start, end = cue["range"]
        if start < cutoff_frame < end:
            raise ValidationError("Un cue CAPTIONS attraversa l'inizio CTA")
        if end <= cutoff_frame:
            retained.append(cue)
    return tuple(retained)


def _input_matches(tool: object, name: str, expected: Any) -> bool:
    actual = safe_call(tool, "GetInput", name)
    if isinstance(expected, float):
        try:
            return abs(float(actual) - expected) < 1e-6
        except (TypeError, ValueError):
            return False
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return False
        try:
            return all(abs(float(actual[key]) - float(value)) < 1e-6
                       for key, value in expected.items())
        except (KeyError, TypeError, ValueError):
            return False
    return actual == expected


def configure_caption_text_frame(tool: object, layout: dict[str, Any]) -> None:
    """Apply and read back the bounded Text+ frame used by lower captions."""
    requested = {
        "Center": {1: layout["center"]["x"], 2: layout["center"]["y"], 3: 0.0},
        "LayoutType": 1.0,
        "LayoutWidth": layout["text_width"],
        "LayoutHeight": layout["text_height"],
        "HorizontalJustificationNew": 3.0,
        "VerticalJustificationNew": 3.0,
    }
    for key, value in requested.items():
        if not _set(tool, key, value):
            raise ValidationError(f"Impostazione Text+ CAPTIONS {key} fallita")
    mismatched = [key for key, value in requested.items() if not _input_matches(tool, key, value)]
    if mismatched:
        raise ValidationError(f"Read-back frame Text+ CAPTIONS non corrispondente: {', '.join(mismatched)}")


def configure_caption_style(tool: object, requested: dict[str, Any], role: str) -> None:
    """Apply every visual property and fail closed on silent Fusion mismatches."""
    for key, value in requested.items():
        if not _set(tool, key, value):
            raise ValidationError(f"Impostazione stile CAPTIONS {role}.{key} fallita")
    mismatched = [key for key, value in requested.items() if not _input_matches(tool, key, value)]
    if mismatched:
        raise ValidationError(
            f"Read-back stile CAPTIONS {role} non corrispondente: {', '.join(mismatched)}")


def timeline_edit_fingerprint(timeline: object) -> str:
    """Bind a picture lock to timing, settings and opaque source-media identities."""
    media_items: list[dict[str, Any]] = []
    for kind in ("video", "audio"):
        count = int(safe_call(timeline, "GetTrackCount", kind) or 0)
        for track_index in range(1, count + 1):
            for item in safe_call(timeline, "GetItemListInTrack", kind, track_index) or []:
                media = safe_call(item, "GetMediaPoolItem")
                unique_id = str(safe_call(media, "GetUniqueId") or "") if media else ""
                properties = safe_call(media, "GetClipProperty") if media else {}
                file_path = str(properties.get("File Path", "")) if isinstance(properties, dict) else ""
                opaque_source = unique_id or hashlib.sha256(
                    file_path.encode("utf-8")).hexdigest()
                media_items.append({
                    "kind": kind, "track": track_index,
                    "start": safe_call(item, "GetStart"), "end": safe_call(item, "GetEnd"),
                    "duration": safe_call(item, "GetDuration"), "source": opaque_source,
                })
    payload = {
        "timeline": timeline_content_fingerprint(timeline),
        "media_items": media_items,
    }
    return hashlib.sha256(json.dumps(
        payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def validate_caption_action(action: dict[str, Any], total_frames: int, *,
                            allow_picture_lock_placeholder: bool = False) -> dict[str, Any]:
    if action.get("type") != "CAPTIONS" or action.get("state") != "APPROVED":
        raise ValidationError("CAPTIONS non approvate")
    fingerprint = str(action.get("locked_edit_fingerprint", ""))
    if (fingerprint != "AT_PICTURE_LOCK" or not allow_picture_lock_placeholder) and not re.fullmatch(
            r"[0-9a-f]{64}", fingerprint):
        raise ValidationError("locked edit fingerprint CAPTIONS non valido")
    if not str(action.get("reason", "")).strip():
        raise ValidationError("reason CAPTIONS mancante")
    raw_style = action.get("style") or {}
    if not isinstance(raw_style, dict):
        raise ValidationError("style CAPTIONS non valido")
    caption_mode = str(raw_style.get("caption_mode", "STANDARD"))
    uppercase = raw_style.get("uppercase", False)
    font_scale = raw_style.get("font_scale", 1.0)
    if caption_mode not in {"STANDARD", "KARAOKE_WORD"}:
        raise ValidationError("caption_mode CAPTIONS non valido")
    if not isinstance(uppercase, bool):
        raise ValidationError("uppercase CAPTIONS deve essere booleano")
    if isinstance(font_scale, bool) or not isinstance(font_scale, (int, float)) or not 1.0 <= font_scale <= 1.2:
        raise ValidationError("font_scale CAPTIONS deve essere tra 1.0 e 1.2")
    raw_cues = action.get("cues")
    if not isinstance(raw_cues, list) or not 1 <= len(raw_cues) <= 200:
        raise ValidationError("CAPTIONS richiede da 1 a 200 cue")
    cues: list[dict[str, Any]] = []
    previous_end = -1
    seen: set[str] = set()
    for raw in raw_cues:
        cue_id = str(raw.get("cue_id", "")) if isinstance(raw, dict) else ""
        start = raw.get("start_frame") if isinstance(raw, dict) else None
        end = raw.get("end_frame") if isinstance(raw, dict) else None
        text = str(raw.get("text", "")).strip() if isinstance(raw, dict) else ""
        position = str(raw.get("position", "")) if isinstance(raw, dict) else ""
        if not cue_id or cue_id in seen:
            raise ValidationError("cue_id CAPTIONS mancante o duplicato")
        if not isinstance(start, int) or not isinstance(end, int) or not 0 <= start < end <= total_frames:
            raise ValidationError("range cue CAPTIONS non valido")
        if start < previous_end:
            raise ValidationError("cue CAPTIONS sovrapposte")
        if not text or len(text) > 84 or text.count("\n") > 1:
            raise ValidationError("testo cue CAPTIONS massimo 84 caratteri e due righe")
        if position not in {"LOWER", "UPPER"}:
            raise ValidationError("position CAPTIONS non sicura")
        seen.add(cue_id); previous_end = end
        cues.append({"cue_id": cue_id, "range": (start, end),
                     "text": text.upper() if uppercase else text,
                     "position": position})
    cutoff = action.get("caption_cutoff_frame")
    if isinstance(cutoff, bool) or not isinstance(cutoff, int) or not 0 <= cutoff <= total_frames:
        raise ValidationError("caption_cutoff_frame CAPTIONS non valido")
    cues = list(cues_before_frame(tuple(cues), cutoff))
    if not cues:
        raise ValidationError("Nessun cue CAPTIONS rimane prima del cutoff")
    if caption_mode == "KARAOKE_WORD" and any(cue["position"] != "LOWER" for cue in cues):
        raise ValidationError("KARAOKE_WORD supporta solo la posizione LOWER verificata")
    return {"locked_edit_fingerprint": fingerprint, "cues": tuple(cues),
            "caption_cutoff_frame": cutoff, "caption_mode": caption_mode,
            "uppercase": uppercase, "font_scale": float(font_scale)}


def build_caption_graph(comp: object, cues: tuple[dict[str, Any], ...],
                        palette: dict[str, str], caption_mode: str = "STANDARD",
                        font_scale: float = 1.0) -> dict[str, Any]:
    media_out = _media_out(comp)
    if media_out is None:
        raise ValidationError("MediaOut CAPTIONS non trovato")
    canvas = _new_tool(comp, "Background", "ARPHE_VERTICAL_CAPTIONS_CANVAS")
    canvas_color = _rgb(palette.get("black", "#000000"), 0.0)
    configure_caption_style(canvas, {
        "TopLeftRed": canvas_color["r"], "TopLeftGreen": canvas_color["g"],
        "TopLeftBlue": canvas_color["b"], "TopLeftAlpha": canvas_color["a"],
    }, "canvas")
    if not connect_input(media_out, "Input", canvas):
        raise ValidationError("Collegamento canvas CAPTIONS fallito")
    lower_layout = lower_caption_layout(font_scale)
    highlight_role = "cream" if caption_mode == "KARAOKE_WORD" else "white"
    for index, cue in enumerate(cues, start=1):
        is_lower = cue["position"] == "LOWER"
        x = lower_layout["center"]["x"] if is_lower else 0.5
        y = lower_layout["center"]["y"] if is_lower else 0.86
        width = lower_layout["width"] if is_lower else 0.78
        height = lower_layout["height"] if is_lower else 0.105
        background = _new_tool(comp, "Background", f"ARPHE_CAPTION_{index:03d}_BG")
        card_color = _rgb(palette["burgundy"], 0.94)
        configure_caption_style(background, {
            "TopLeftRed": card_color["r"], "TopLeftGreen": card_color["g"],
            "TopLeftBlue": card_color["b"], "TopLeftAlpha": card_color["a"],
        }, f"card_{index:03d}")
        mask = _new_tool(comp, "RectangleMask", f"ARPHE_CAPTION_{index:03d}_MASK")
        configure_caption_style(mask, {
            "Width": width, "Height": height,
            "Center": {1: x, 2: y, 3: 0.0}, "CornerRadius": 0.08,
        }, f"mask_{index:03d}")
        if not connect_input(background, "EffectMask", mask):
            raise ValidationError("Maschera CAPTIONS non collegata")
        text = _new_tool(comp, "TextPlus", f"ARPHE_CAPTION_{index:03d}_TEXT")
        configure_caption_style(text, {
            "StyledText": cue["text"], "Font": "Satoshi", "Style": "Bold",
            "Size": 0.050 * font_scale,
        }, f"text_{index:03d}")
        if is_lower:
            configure_caption_text_frame(text, lower_layout)
        else:
            for key, value in (("Center", {1: x, 2: y, 3: 0.0}), ("LayoutType", 1.0),
                               ("LayoutWidth", 0.70), ("LayoutHeight", 0.09),
                               ("HorizontalJustificationNew", 3.0),
                               ("VerticalJustificationNew", 3.0)):
                if not _set(text, key, value):
                    raise ValidationError(f"Impostazione Text+ CAPTIONS {key} fallita")
        text_color = _rgb(palette[highlight_role])
        configure_caption_style(text, {
            "Red1": text_color["r"], "Green1": text_color["g"],
            "Blue1": text_color["b"], "Alpha1": 1.0,
        }, f"text_color_{index:03d}")
        card = _new_tool(comp, "Merge", f"ARPHE_CAPTION_{index:03d}_CARD")
        if not connect_input(card, "Background", background) or not connect_input(card, "Foreground", text):
            raise ValidationError("Grafo card CAPTIONS non collegato")
        outer = add_layer(comp, card, f"ARPHE_CAPTION_{index:03d}_OUTER")
        if outer is None:
            raise ValidationError("Merge timing CAPTIONS non disponibile")
        start, end = cue["range"]
        if not set_visibility_window(comp, outer, start, end):
            raise ValidationError("Keyframe timing CAPTIONS non applicati")
    return {"cue_count": len(cues), "text_readback": True, "font": "Satoshi Bold",
            "font_size": round(0.050 * font_scale, 4), "caption_mode": caption_mode,
            "highlight_role": highlight_role, "gap_preserving": True,
            "lower_layout": lower_layout}


def apply_caption_action(project: object, timeline: object, config: Any,
                         action: dict[str, Any], total_frames: int,
                         required_timeline_prefix: str = "__ARPHE_VERTICAL_") -> dict[str, Any]:
    plan = validate_caption_action(action, total_frames)
    timeline_start = safe_call(timeline, "GetStartFrame")
    timeline_end = safe_call(timeline, "GetEndFrame")
    if (not isinstance(timeline_start, int) or isinstance(timeline_start, bool)
            or not isinstance(timeline_end, int) or isinstance(timeline_end, bool)
            or timeline_end - timeline_start != total_frames):
        raise ValidationError("Range assoluto timeline CAPTIONS non corrispondente")
    item, comp = create_overlay_composition(
        project, timeline, config, timeline_start, timeline_end,
        f"CAPTIONS_{action['action_id']}",
        required_timeline_prefix=required_timeline_prefix)
    # The carrier is placed in Resolve's absolute timeline coordinates, while
    # the Fusion Clip evaluates its tools on its own zero-based local clock.
    graph = build_caption_graph(comp, plan["cues"], config.palette,
                                caption_mode=plan["caption_mode"],
                                font_scale=plan["font_scale"])
    return {"ok": True, "action_id": str(action["action_id"]),
            "timeline": str(safe_call(timeline, "GetName") or ""),
            "range": [timeline_start, timeline_end], "relative_range": [0, total_frames],
            "timeline_item": str(safe_call(item, "GetName") or ""),
            "locked_edit_fingerprint": plan["locked_edit_fingerprint"], **graph}
