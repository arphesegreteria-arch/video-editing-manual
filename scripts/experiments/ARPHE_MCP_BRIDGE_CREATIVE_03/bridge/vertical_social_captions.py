from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from .carabellese_checkpoint import timeline_content_fingerprint
from .fusion_tools import (_media_out, _new_tool, _rgb, _set, _set_color,
                           add_layer, connect_input)
from .resolve_connection import safe_call
from .safety import ValidationError
from .vertical_social_overlay import create_overlay_composition


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
        cues.append({"cue_id": cue_id, "range": (start, end), "text": text,
                     "position": position})
    return {"locked_edit_fingerprint": fingerprint, "cues": tuple(cues)}


def _set_expression(tool: object, input_name: str, expression: str) -> None:
    try:
        input_proxy = getattr(tool, input_name)
        result = input_proxy.SetExpression(expression)
        if result is False:
            raise RuntimeError("SetExpression=False")
    except Exception as exc:
        raise ValidationError(f"Espressione timing CAPTIONS fallita: {exc}") from exc


def build_caption_graph(comp: object, cues: tuple[dict[str, Any], ...],
                        palette: dict[str, str]) -> dict[str, Any]:
    media_out = _media_out(comp)
    if media_out is None:
        raise ValidationError("MediaOut CAPTIONS non trovato")
    canvas = _new_tool(comp, "Background", "ARPHE_VERTICAL_CAPTIONS_CANVAS")
    _set_color(canvas, _rgb(palette.get("black", "#000000"), 0.0))
    if not connect_input(media_out, "Input", canvas):
        raise ValidationError("Collegamento canvas CAPTIONS fallito")
    for index, cue in enumerate(cues, start=1):
        y = 0.24 if cue["position"] == "LOWER" else 0.86
        background = _new_tool(comp, "Background", f"ARPHE_CAPTION_{index:03d}_BG")
        _set_color(background, _rgb(palette["burgundy"], 0.94))
        mask = _new_tool(comp, "RectangleMask", f"ARPHE_CAPTION_{index:03d}_MASK")
        for key, value in (("Width", 0.78), ("Height", 0.105),
                           ("Center", {1: 0.5, 2: y, 3: 0.0}), ("CornerRadius", 0.08)):
            _set(mask, key, value)
        if not connect_input(background, "EffectMask", mask):
            raise ValidationError("Maschera CAPTIONS non collegata")
        text = _new_tool(comp, "TextPlus", f"ARPHE_CAPTION_{index:03d}_TEXT")
        for key, value in (("StyledText", cue["text"]), ("Font", "Satoshi"),
                           ("Style", "Bold"), ("Size", 0.050),
                           ("Center", {1: 0.5, 2: y, 3: 0.0})):
            _set(text, key, value)
        white = _rgb(palette["white"])
        for key, value in (("Red1", white["r"]), ("Green1", white["g"]),
                           ("Blue1", white["b"]), ("Alpha1", 1.0)):
            _set(text, key, value)
        if safe_call(text, "GetInput", "StyledText") != cue["text"]:
            raise ValidationError("Read-back testo CAPTIONS non corrispondente")
        card = _new_tool(comp, "Merge", f"ARPHE_CAPTION_{index:03d}_CARD")
        if not connect_input(card, "Background", background) or not connect_input(card, "Foreground", text):
            raise ValidationError("Grafo card CAPTIONS non collegato")
        outer = add_layer(comp, card, f"ARPHE_CAPTION_{index:03d}_OUTER")
        if outer is None:
            raise ValidationError("Merge timing CAPTIONS non disponibile")
        start, end = cue["range"]
        _set_expression(outer, "Blend", f"iif(time >= {start} and time < {end}, 1, 0)")
    return {"cue_count": len(cues), "text_readback": True, "font": "Satoshi Bold",
            "gap_preserving": True}


def apply_caption_action(project: object, timeline: object, config: Any,
                         action: dict[str, Any], total_frames: int) -> dict[str, Any]:
    plan = validate_caption_action(action, total_frames)
    item, comp = create_overlay_composition(
        project, timeline, config, 0, total_frames, f"CAPTIONS_{action['action_id']}")
    graph = build_caption_graph(comp, plan["cues"], config.palette)
    return {"ok": True, "action_id": str(action["action_id"]),
            "timeline": str(safe_call(timeline, "GetName") or ""),
            "range": [0, total_frames], "timeline_item": str(safe_call(item, "GetName") or ""),
            "locked_edit_fingerprint": plan["locked_edit_fingerprint"], **graph}
