from __future__ import annotations

from pathlib import Path
from typing import Any

from .fusion_tools import (
    CARRIER_ASSET_NAME,
    MAX_AUTOMATIC_FUSION_FRAMES,
    _media_out,
    _new_tool,
    _rgb,
    _set,
    _set_color,
    add_layer,
    connect_input,
)
from .resolve_connection import safe_call
from .safety import ValidationError
from .vertical_social_graphics import approved_graphic_actions


def create_overlay_composition(project: object, timeline: object, config: Any,
                               start: int, end: int, name: str) -> tuple[object, object]:
    timeline_name = str(safe_call(timeline, "GetName") or "")
    if not timeline_name.startswith("__ARPHE_VERTICAL_"):
        raise ValidationError("Overlay consentito solo sulla timeline provvisoria Vertical Social")
    duration = end - start
    if duration <= 0 or duration > MAX_AUTOMATIC_FUSION_FRAMES:
        raise ValidationError("Durata overlay fuori limite")
    carrier = (Path(config.asset_root) / CARRIER_ASSET_NAME).resolve()
    if not carrier.is_file():
        raise ValidationError("Carrier Fusion tecnico non installato")
    pool = safe_call(project, "GetMediaPool")
    imported = safe_call(pool, "ImportMedia", [str(carrier)]) if pool else None
    if not imported:
        raise ValidationError("Import carrier overlay fallito")
    if not safe_call(timeline, "AddTrack", "video"):
        raise ValidationError("Creazione traccia overlay fallita")
    track = int(safe_call(timeline, "GetTrackCount", "video") or 0)
    appended = safe_call(pool, "AppendToTimeline", [{
        "mediaPoolItem": imported[0], "startFrame": 0, "endFrame": duration,
        "recordFrame": start, "mediaType": 1, "trackIndex": track,
    }]) or []
    carrier_item = appended[0] if len(appended) == 1 else None
    if carrier_item is None:
        raise ValidationError("Inserimento carrier overlay fallito")
    item = safe_call(timeline, "CreateFusionClip", [carrier_item]) or carrier_item
    comp = safe_call(item, "AddFusionComp") or safe_call(item, "GetFusionCompByIndex", 1)
    if comp is None:
        raise ValidationError("Composizione Fusion overlay non disponibile")
    safe_call(item, "SetName", f"ARPHE_VERTICAL_{name}")
    if (safe_call(item, "GetStart") != start or safe_call(item, "GetEnd") != end
            or safe_call(item, "GetDuration") != duration):
        raise ValidationError("Read-back range overlay non corrispondente")
    return item, comp


def _text(comp: object, name: str, value: str, color: str, size: float, y: float) -> object:
    tool = _new_tool(comp, "TextPlus", name)
    for key, entry in (("StyledText", value), ("Font", "Satoshi"), ("Style", "Bold"),
                       ("Size", size), ("Center", {1: 0.5, 2: y, 3: 0.0})):
        if not _set(tool, key, entry):
            raise ValidationError(f"Impostazione Text+ {key} fallita")
    rgb = _rgb(color)
    for key, entry in (("Red1", rgb["r"]), ("Green1", rgb["g"]),
                       ("Blue1", rgb["b"]), ("Alpha1", 1.0)):
        _set(tool, key, entry)
    if safe_call(tool, "GetInput", "StyledText") != value:
        raise ValidationError("Read-back testo overlay non corrispondente")
    return tool


def build_graphic_graph(comp: object, action: dict[str, Any], palette: dict[str, str]) -> dict[str, Any]:
    media_out = _media_out(comp)
    if media_out is None:
        raise ValidationError("MediaOut overlay non trovato")
    action_type = str(action["type"])
    canvas = _new_tool(comp, "Background", f"ARPHE_VERTICAL_{action_type}_CANVAS")
    if action_type == "CTA":
        _set_color(canvas, _rgb(palette[action["style_role"]]))
    else:
        _set_color(canvas, _rgb(palette.get("black", "#000000"), 0.0))
    if not connect_input(media_out, "Input", canvas):
        raise ValidationError("Collegamento canvas overlay fallito")
    texts: list[object] = []
    if action_type == "GRAPHIC":
        y = 0.20 if action["graphic_kind"] == "LOWER_THIRD" else 0.50
        text = _text(comp, "ARPHE_VERTICAL_GRAPHIC_TEXT", action["text"],
                     palette[action["style_role"]], 0.055, y)
        add_layer(comp, text, "ARPHE_VERTICAL_GRAPHIC_MERGE")
        texts.append(text)
    else:
        heading = _text(comp, "ARPHE_VERTICAL_CTA_HEADLINE", action["headline"],
                        palette.get("white", "#FFFFFF"), 0.085, 0.56)
        body = _text(comp, "ARPHE_VERTICAL_CTA_TEXT", action["text"],
                     palette.get("cream", "#EFE3CF"), 0.050, 0.43)
        add_layer(comp, heading, "ARPHE_VERTICAL_CTA_HEADLINE_MERGE")
        add_layer(comp, body, "ARPHE_VERTICAL_CTA_TEXT_MERGE")
        texts.extend((heading, body))
    return {"text_readback": True, "text_node_count": len(texts), "font": "Satoshi"}


def apply_graphic_or_cta(project: object, timeline: object, config: Any,
                         action: dict[str, Any], total_frames: int) -> dict[str, Any]:
    selected = approved_graphic_actions({"actions": [action]}, total_frames)
    if len(selected) != 1:
        raise ValidationError("Azione GRAPHIC/CTA approvata mancante")
    plan = selected[0]
    start, end = plan["range"]
    item, comp = create_overlay_composition(
        project, timeline, config, start, end, f"{plan['type']}_{plan['action_id']}")
    graph = build_graphic_graph(comp, plan, config.palette)
    return {"ok": True, "action_id": plan["action_id"], "type": plan["type"],
            "timeline": str(safe_call(timeline, "GetName") or ""),
            "range": [start, end], "timeline_item": str(safe_call(item, "GetName") or ""),
            **graph}
