from __future__ import annotations

from typing import Any

from .branded_longform_kits import LongformKit
from .font_readiness import WindowsGdiTextMeasurer
from .fusion_tools import (
    _media_out,
    _new_tool,
    _rgb,
    _set,
    _set_color,
    add_layer,
    connect_input,
    set_visibility_window,
)
from .resolve_connection import safe_call
from .safety import ValidationError


def validate_kit_font(kit: LongformKit, measurer: Any | None = None) -> None:
    selected = measurer or WindowsGdiTextMeasurer()
    missing = [weight for weight in (400, 500, 700)
               if not selected.font_available(kit.font_family, weight)]
    if missing:
        raise ValidationError(
            f"{kit.font_family} non disponibile nei pesi richiesti: {missing}")


def _copy(proposal: dict[str, Any], fallback: str) -> str:
    value = str(proposal.get("operator_modification") or proposal.get("copy") or fallback).strip()
    if not value or len(value) > 120:
        raise ValidationError("Copy grafica Carabellese mancante o troppo lunga")
    return value


def _node(text: str, x: float, y: float, size: float, weight: int,
          color_role: str, reveal: float = 0.0,
          layout_width: float = 0.28) -> dict[str, Any]:
    return {"text": text, "x": x, "y": y, "size": size, "weight": weight,
            "color_role": color_role, "font": "Space Grotesk", "reveal": reveal,
            "layout_width": layout_width}


def panel_geometry(kind: str) -> dict[str, float]:
    """Keep editorial graphics in a presenter-safe rail instead of a full-frame slab."""
    if kind == "COMPARISON_TABLE":
        return {"center_x": 0.73, "center_y": 0.50, "width": 0.46, "height": 0.66}
    return {"center_x": 0.78, "center_y": 0.50, "width": 0.34, "height": 0.64}


def reveal_motion_plan(start_frame: int, duration_frames: int = 10) -> tuple[dict[str, float], ...]:
    duration = max(6, min(14, int(duration_frames)))
    settle = start_frame + max(4, round(duration * 0.7))
    end = start_frame + duration
    return (
        {"frame": start_frame, "x": 0.035, "scale": 0.94, "opacity": 0.0},
        {"frame": settle, "x": -0.006, "scale": 1.025, "opacity": 1.0},
        {"frame": end, "x": 0.0, "scale": 1.0, "opacity": 1.0},
    )


def component_layout(proposal: dict[str, Any], kit: LongformKit) -> tuple[dict[str, Any], ...]:
    kind = str(proposal.get("kind", ""))
    content = proposal.get("content")
    content = content if isinstance(content, dict) else {}
    nodes: list[dict[str, Any]] = [_node("01 /", 0.78, 0.78, 0.030, 700, "teal")]
    if kind == "KEYWORD_BOX":
        nodes.append(_node(_copy(proposal, "CONCETTO"), 0.78, 0.55, 0.056, 700, "neutral"))
    elif kind == "CHAPTER_CARD":
        nodes.extend((
            _node(_copy(proposal, "NUOVO CAPITOLO"), 0.78, 0.58, 0.052, 700, "neutral"),
            _node("ALESSIO CARABELLESE / PODCAST", 0.78, 0.43, 0.021, 500, "neutral", 0.15),
        ))
    elif kind in {"PROGRESSIVE_LIST", "PROCESS_STEPS"}:
        key = "items" if kind == "PROGRESSIVE_LIST" else "steps"
        values = content.get(key)
        if not isinstance(values, list) or not 3 <= len(values) <= 5:
            raise ValidationError(f"{kind}: richiesti da 3 a 5 elementi")
        start_y, spacing = 0.66, min(0.13, 0.45 / max(1, len(values) - 1))
        for index, value in enumerate(values, 1):
            text = str(value).strip()
            if not text or len(text) > 80:
                raise ValidationError(f"{kind}: elemento non valido")
            nodes.append(_node(f"{index:02d}  {text}", 0.78, start_y - (index - 1) * spacing,
                               0.036, 600, "neutral", index / (len(values) + 2)))
    elif kind == "COMPARISON_TABLE":
        left = str(content.get("left_title", "")).strip()
        right = str(content.get("right_title", "")).strip()
        rows = content.get("rows")
        if not left or not right or not isinstance(rows, list) or not 1 <= len(rows) <= 4:
            raise ValidationError("COMPARISON_TABLE incompleta")
        nodes.extend((_node(left, 0.61, 0.67, 0.034, 700, "neutral", layout_width=0.18),
                      _node(right, 0.82, 0.67, 0.034, 700, "neutral", layout_width=0.18)))
        for index, row in enumerate(rows):
            if not isinstance(row, list) or len(row) != 2:
                raise ValidationError("COMPARISON_TABLE: riga non valida")
            y = 0.56 - index * 0.105
            nodes.extend((_node(str(row[0]).strip(), 0.61, y, 0.027, 400, "neutral",
                                (index + 1) / (len(rows) + 2), 0.18),
                          _node(str(row[1]).strip(), 0.82, y, 0.027, 400, "neutral",
                                (index + 1) / (len(rows) + 2), 0.18)))
    else:
        raise ValidationError(f"Componente Carabellese non supportato: {kind}")
    for node in nodes:
        if (not kit.safe_area["left"] <= node["x"] <= kit.safe_area["right"]
                or not kit.safe_area["top"] <= node["y"] <= kit.safe_area["bottom"]):
            raise ValidationError("Layout Carabellese fuori safe area")
    return tuple(nodes)


def _text(comp: object, name: str, node: dict[str, Any], kit: LongformKit) -> object:
    tool = _new_tool(comp, "TextPlus", name)
    style = "Bold" if node["weight"] >= 700 else "Medium" if node["weight"] >= 500 else "Regular"
    for key, value in (("StyledText", node["text"]), ("Font", kit.font_family),
                       ("Style", style), ("Size", node["size"]),
                       ("Center", {1: node["x"], 2: node["y"], 3: 0.0}),
                       ("LayoutType", 1.0), ("LayoutWidth", node["layout_width"]),
                       ("LayoutHeight", 0.12),
                       ("HorizontalJustification", -1.0)):
        if not _set(tool, key, value):
            raise ValidationError(f"Impostazione Text+ Carabellese {key} fallita")
    rgb = _rgb(kit.palette[node["color_role"]])
    for key, value in (("Red1", rgb["r"]), ("Green1", rgb["g"]),
                       ("Blue1", rgb["b"]), ("Alpha1", 1.0)):
        _set(tool, key, value)
    if safe_call(tool, "GetInput", "StyledText") != node["text"]:
        raise ValidationError("Read-back testo Carabellese non corrispondente")
    return tool


def build_carabellese_longform_graph(comp: object, proposal: dict[str, Any],
                                     kit: LongformKit) -> dict[str, object]:
    media_out = _media_out(comp)
    if media_out is None:
        raise ValidationError("MediaOut Carabellese non trovato")
    canvas = _new_tool(comp, "Background", "CARABELLESE_LONGFORM_CANVAS")
    _set_color(canvas, _rgb("#000000", 0.0))
    if not connect_input(media_out, "Input", canvas):
        raise ValidationError("Collegamento canvas Carabellese fallito")
    panel = _new_tool(comp, "Background", "CARABELLESE_LONGFORM_PANEL")
    _set_color(panel, _rgb(kit.palette["ink"], 0.90))
    mask = _new_tool(comp, "RectangleMask", "CARABELLESE_LONGFORM_PANEL_MASK")
    geometry = panel_geometry(str(proposal.get("kind", "")))
    for key, value in (("Center", {1: geometry["center_x"], 2: geometry["center_y"], 3: 0.0}),
                       ("Width", geometry["width"]), ("Height", geometry["height"]),
                       ("CornerRadius", 0.065)):
        if not _set(mask, key, value):
            raise ValidationError(f"Impostazione pannello Carabellese {key} fallita")
    if not connect_input(panel, "EffectMask", mask):
        raise ValidationError("Maschera pannello Carabellese non collegata")
    add_layer(comp, panel, "CARABELLESE_LONGFORM_PANEL_MERGE")
    layout = component_layout(proposal, kit)
    duration = int(proposal.get("end_frame", 0)) - int(proposal.get("start_frame", 0))
    progressive_reveal_count = 0
    motion_reveal_count = 0
    for index, node in enumerate(layout):
        tool = _text(comp, f"CARABELLESE_LONGFORM_TEXT_{index + 1:02d}", node, kit)
        transform = _new_tool(comp, "Transform", f"CARABELLESE_LONGFORM_TEXT_TRANSFORM_{index + 1:02d}")
        if not connect_input(transform, "Input", tool):
            raise ValidationError("Collegamento Transform testo Carabellese fallito")
        merge = add_layer(comp, transform, f"CARABELLESE_LONGFORM_TEXT_MERGE_{index + 1:02d}")
        reveal = int(round(max(0.0, min(0.9, float(node["reveal"]))) * duration))
        for key in reveal_motion_plan(reveal, 10):
            frame = int(key["frame"])
            if (not _set(transform, "Center", {1: 0.5 + key["x"], 2: 0.5, 3: 0.0}, frame)
                    or not _set(transform, "Size", key["scale"], frame)):
                raise ValidationError("Motion reveal Carabellese fallito")
        motion_reveal_count += 1
        if reveal > 0 and duration > reveal and not set_visibility_window(comp, merge, reveal, duration):
            raise ValidationError("Reveal progressivo Carabellese fallito")
        if reveal > 0 and duration > reveal:
            progressive_reveal_count += 1
    return {"text_readback": True, "text_node_count": len(layout),
            "font": kit.font_family, "component": str(proposal.get("kind", "")),
            "profile_id": kit.profile_id,
            "progressive_reveal_count": progressive_reveal_count,
            "motion_reveal_count": motion_reveal_count,
            "presenter_safe_panel": geometry}
