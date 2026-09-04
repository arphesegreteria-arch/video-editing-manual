from __future__ import annotations

from typing import Any

from .config import CreativeConfig
from .feature_flags import require_capability
from .fusion_tools import (_id, _new_tool, _rgb, _set, _set_color, add_layer,
                           find_composition, set_visibility_window)
from .motion_presets import motion_plan, stack_plan
from .registry import Registry
from .resolve_connection import safe_call
from .safety import (ValidationError, finite_float, validate_color_role,
                     validate_frame_range, validate_preset, validate_review)


def _merge(comp: Any, background: Any, foreground: Any, name: str) -> Any:
    merge = _new_tool(comp, "Merge", name)
    merge.ConnectInput("Background", background)
    merge.ConnectInput("Foreground", foreground)
    return merge


def _text(comp: Any, name: str, value: str, size: float, color: dict[str, float], y: float) -> Any:
    tool = _new_tool(comp, "TextPlus", name)
    _set(tool, "StyledText", value)
    _set(tool, "Size", size)
    _set(tool, "Center", {1: 0.5, 2: y, 3: 0.0})
    for key, channel in (("Red1", "r"), ("Green1", "g"), ("Blue1", "b"), ("Alpha1", "a")):
        _set(tool, key, color[channel])
    return tool


def add_review_card(project: Any, timeline: Any, config: CreativeConfig, registry: Registry,
                    composition_id: str, text: str, stars: int, start_frame: int, end_frame: int,
                    style_role: str, highlight_text: str | None = None,
                    small_label: str | None = None) -> dict:
    require_capability("CAP_REVIEW", config, None, project, timeline)
    start, end = validate_frame_range(start_frame, end_frame)
    validate_review(text, stars, highlight_text, small_label)
    validate_color_role(style_role)
    _, comp = find_composition(timeline, registry, composition_id)
    card_id = _id("CARD")
    background = _new_tool(comp, "Background", f"{card_id}_BG")
    _set_color(background, _rgb(config.palette[style_role]))
    mask = _new_tool(comp, "RectangleMask", f"{card_id}_MASK")
    _set(mask, "Width", 0.78)
    _set(mask, "Height", 0.34)
    _set(mask, "CornerRadius", 0.055)
    background.ConnectInput("EffectMask", mask)

    shadow = _new_tool(comp, "Background", f"{card_id}_SHADOW")
    _set_color(shadow, _rgb(config.palette["black"], 0.13))
    shadow_mask = _new_tool(comp, "RectangleMask", f"{card_id}_SHADOW_MASK")
    _set(shadow_mask, "Width", 0.78)
    _set(shadow_mask, "Height", 0.34)
    _set(shadow_mask, "CornerRadius", 0.055)
    _set(shadow_mask, "Center", {1: 0.512, 2: 0.485, 3: 0.0})
    shadow.ConnectInput("EffectMask", shadow_mask)
    card = _merge(comp, shadow, background, f"{card_id}_CARD_MERGE")

    dark = _rgb(config.palette["dark_brown"])
    review = _text(comp, f"{card_id}_TEXT", text, 0.047, dark, 0.49)
    card = _merge(comp, card, review, f"{card_id}_TEXT_MERGE")
    stars_tool = _text(comp, f"{card_id}_STARS", "★" * stars, 0.042, _rgb(config.palette["burgundy"]), 0.61)
    card = _merge(comp, card, stars_tool, f"{card_id}_STARS_MERGE")
    label_tool = _text(comp, f"{card_id}_LABEL", small_label or "", 0.024, dark, 0.38)
    card = _merge(comp, card, label_tool, f"{card_id}_LABEL_MERGE")
    highlight_tool = _text(comp, f"{card_id}_HIGHLIGHT", highlight_text or "", 0.037,
                           _rgb(config.palette["burgundy"]), 0.43)
    card = _merge(comp, card, highlight_tool, f"{card_id}_HIGHLIGHT_MERGE")

    transform = _new_tool(comp, "Transform", f"{card_id}_TRANSFORM")
    transform.ConnectInput("Input", card)
    outer_merge_name = f"{card_id}_OUTER_MERGE"
    outer_merge = add_layer(comp, transform, outer_merge_name)
    timing_applied = set_visibility_window(comp, outer_merge, start, end)
    registry.add_element(card_id, {
        "kind": "review_card", "composition_id": composition_id,
        "transform_name": f"{card_id}_TRANSFORM",
        "outer_merge_name": outer_merge_name if outer_merge else None,
        "highlight_name": f"{card_id}_HIGHLIGHT",
        "start_frame": start, "end_frame": end,
    })
    return {"ok": True, "action": "add_review_card", "composition_id": composition_id,
            "card_id": card_id, "stars": stars, "frame_range": [start, end],
            "style_role": style_role, "timing_applied": timing_applied, "status": "PENDING"}


def set_review_highlight(project: Any, timeline: Any, config: CreativeConfig, registry: Registry,
                         composition_id: str, card_id: str, highlight_text: str) -> dict:
    require_capability("CAP_REVIEW", config, None, project, timeline)
    if not isinstance(highlight_text, str) or not highlight_text.strip() or len(highlight_text) > 180:
        raise ValidationError("highlight_text richiesto, massimo 180 caratteri")
    record = registry.element(card_id)
    if not record or record.get("kind") != "review_card" or record.get("composition_id") != composition_id:
        raise ValidationError("card_id non valido per questa composizione")
    _, comp = find_composition(timeline, registry, composition_id)
    tool = safe_call(comp, "FindTool", record["highlight_name"])
    changed = bool(_set(tool, "StyledText", highlight_text)) if tool else False
    return {"ok": changed, "action": "set_review_highlight", "card_id": card_id, "status": "PENDING"}


def add_end_card(project: Any, timeline: Any, config: CreativeConfig, registry: Registry,
                 composition_id: str, headline: str, cta: str, start_frame: int,
                 end_frame: int, style_role: str = "burgundy") -> dict:
    require_capability("CAP_REVIEW", config, None, project, timeline)
    start, end = validate_frame_range(start_frame, end_frame)
    validate_color_role(style_role)
    if not isinstance(headline, str) or not headline.strip() or len(headline) > 160:
        raise ValidationError("headline richiesto, massimo 160 caratteri")
    if not isinstance(cta, str) or not cta.strip() or len(cta) > 100:
        raise ValidationError("cta richiesto, massimo 100 caratteri")
    _, comp = find_composition(timeline, registry, composition_id)
    element_id = _id("END_CARD")
    background = _new_tool(comp, "Background", f"{element_id}_BG")
    _set_color(background, _rgb(config.palette[style_role]))
    heading = _text(comp, f"{element_id}_HEADLINE", headline, 0.07, _rgb(config.palette["white"]), 0.55)
    merged = _merge(comp, background, heading, f"{element_id}_HEADLINE_MERGE")
    cta_tool = _text(comp, f"{element_id}_CTA", cta, 0.045, _rgb(config.palette["cream"]), 0.43)
    merged = _merge(comp, merged, cta_tool, f"{element_id}_CTA_MERGE")
    transform = _new_tool(comp, "Transform", f"{element_id}_TRANSFORM")
    transform.ConnectInput("Input", merged)
    outer_name = f"{element_id}_OUTER_MERGE"
    outer = add_layer(comp, transform, outer_name)
    timing_applied = set_visibility_window(comp, outer, start, end)
    registry.add_element(element_id, {"kind": "end_card", "composition_id": composition_id,
                                      "transform_name": f"{element_id}_TRANSFORM",
                                      "outer_merge_name": outer_name if outer else None,
                                      "start_frame": start, "end_frame": end})
    return {"ok": True, "action": "add_end_card", "element_id": element_id,
            "frame_range": [start, end], "timing_applied": timing_applied, "status": "PENDING"}


def _animate(comp: Any, record: dict, plan: dict, reverse: bool = False) -> bool:
    transform = safe_call(comp, "FindTool", record.get("transform_name"))
    if not transform:
        return False
    keys = list(reversed(plan["keys"])) if reverse else plan["keys"]
    center = comp.BezierSpline()
    size = comp.BezierSpline()
    angle = comp.BezierSpline()
    for index, key in enumerate(keys):
        frame = plan["keys"][index]["frame"]
        center[frame] = {1: 0.5 + key["x"], 2: 0.5 + key["y"], 3: 0.0}
        size[frame] = key["scale"]
        angle[frame] = key["rotation"]
    transform.Center = center
    transform.Size = size
    transform.Angle = angle
    merge = safe_call(comp, "FindTool", record.get("outer_merge_name")) if record.get("outer_merge_name") else None
    if merge:
        blend = comp.BezierSpline()
        record_start = int(record["start_frame"])
        record_end = int(record["end_frame"])
        if record_start > 0:
            blend[record_start - 1] = 0.0
        blend[record_start] = 1.0
        for index, key in enumerate(keys):
            blend[plan["keys"][index]["frame"]] = key["opacity"]
        if not reverse:
            blend[record_end - 1] = 1.0
        blend[record_end] = 0.0
        merge.Blend = blend
    return True


def animate_element(project: Any, timeline: Any, config: CreativeConfig, registry: Registry,
                    composition_id: str, element_id: str, preset: str, duration_frames: int,
                    direction: str, easing: str, settle: bool, exit_motion: bool = False) -> dict:
    require_capability("CAP_MOTION", config, None, project, timeline)
    validate_preset(preset)
    record = registry.element(element_id)
    if not record or record.get("composition_id") != composition_id:
        raise ValidationError("element_id non valido per questa composizione")
    _, comp = find_composition(timeline, registry, composition_id)
    start = int(record["end_frame"] - duration_frames if exit_motion else record["start_frame"])
    plan = motion_plan(preset, start, duration_frames, direction=direction, easing=easing, settle=settle)
    ok = _animate(comp, record, plan, reverse=exit_motion)
    return {"ok": ok, "action": "animate_card_exit" if exit_motion else "animate_card_entry",
            "element_id": element_id, "motion": plan, "status": "PENDING"}


def animate_stack(project: Any, timeline: Any, config: CreativeConfig, registry: Registry,
                  composition_id: str, card_ids: list[str], start_frame: int,
                  stagger_frames: int, overlap: float, direction: str,
                  rotation_pattern: str, position_offsets: list[float] | None,
                  scale_start: float, opacity_start: float, duration_frames: int,
                  easing: str, settle: bool) -> dict:
    require_capability("CAP_MOTION", config, None, project, timeline)
    plans = stack_plan(card_ids, start_frame, stagger_frames, overlap, direction, rotation_pattern,
                       position_offsets, scale_start, opacity_start, duration_frames, easing, settle)
    _, comp = find_composition(timeline, registry, composition_id)
    results = []
    for plan in plans:
        record = registry.element(plan["card_id"])
        if not record or record.get("composition_id") != composition_id:
            raise ValidationError(f"card_id non valido: {plan['card_id']}")
        results.append({"card_id": plan["card_id"], "ok": _animate(comp, record, plan)})
    return {"ok": all(item["ok"] for item in results), "action": "animate_review_stack",
            "composition_id": composition_id, "preset": "ARPHE_PAPER_STACK",
            "results": results, "plans": plans, "status": "PENDING"}
