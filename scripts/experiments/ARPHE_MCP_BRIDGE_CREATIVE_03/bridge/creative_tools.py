from __future__ import annotations

import math
from typing import Any

from .config import CreativeConfig
from .feature_flags import require_capability
from .fusion_tools import (_id, _new_tool, _rgb, _set, _set_color, add_layer,
                           MAX_AUTOMATIC_FUSION_FRAMES, add_background, connect_input, create_composition,
                           find_composition, set_visibility_window)
from .motion_presets import motion_plan, stack_plan
from .registry import Registry
from .resolve_connection import safe_call
from .safety import (ValidationError, finite_float, validate_color_role,
                     validate_frame_range, validate_preset, validate_review)


_CANONICAL_SAFE_AREA = {"left": 0.08, "right": 0.84, "top": 0.10, "bottom": 0.82}
_CANONICAL_TYPOGRAPHY = {
    "heading": {"family": "Noto Serif Display", "weight": 300},
    "body": {"family": "Satoshi", "weight": 400},
    "label": {"family": "Satoshi", "weight": 500},
    "button": {"family": "Satoshi", "weight": 700},
}
_WEIGHT_STYLES = {300: "Light", 400: "Regular", 500: "Medium", 700: "Bold"}


def _layout_typography(layout: dict[str, Any], role: str) -> tuple[str, str]:
    typography = layout.get("typography")
    if not isinstance(typography, dict) or role not in typography:
        raise ValidationError("CONTRACT_MISMATCH: typography layout assente")
    entry = typography[role]
    if not isinstance(entry, dict):
        raise ValidationError("CONTRACT_MISMATCH: ruolo tipografico non valido")
    family = str(entry.get("family") or "")
    weight = entry.get("weight")
    expected = _CANONICAL_TYPOGRAPHY.get(role)
    if expected is None or family != expected["family"] or weight != expected["weight"]:
        raise ValidationError("CONTRACT_MISMATCH: tipografia non canonica")
    return family, _WEIGHT_STYLES[int(weight)]


def _portrait_review_geometry(layout: dict[str, Any]) -> dict[str, Any]:
    safe = layout.get("safe_area")
    if safe != _CANONICAL_SAFE_AREA:
        raise ValidationError("CONTRACT_MISMATCH: safe area layout non canonica")
    selected_size = layout.get("selected_size")
    if selected_size not in (0.052, 0.047, 0.042):
        raise ValidationError("CONTRACT_MISMATCH: size tier non canonica")
    line_count = layout.get("line_count")
    if isinstance(line_count, bool) or not isinstance(line_count, int) or not 1 <= line_count <= 7:
        raise ValidationError("TEXT_OVERFLOW: line_count non valido")
    return {
        "body_size": float(selected_size),
        "body_lines": line_count,
        "center_x": 0.46,
        "boxes": {
            "card": (0.08, 0.27, 0.84, 0.73),
            "body": (0.12, 0.355, 0.80, 0.625),
            "stars": (0.12, 0.63, 0.80, 0.69),
            "label": (0.12, 0.34, 0.80, 0.40),
            "highlight": (0.12, 0.40, 0.80, 0.455),
            "intro_panel": (0.08, 0.30, 0.84, 0.70),
            "intro_eyebrow": (0.12, 0.61, 0.80, 0.67),
            "intro_heading": (0.12, 0.39, 0.80, 0.62),
            "intro_subheading": (0.12, 0.30, 0.80, 0.40),
            "cta_heading": (0.12, 0.47, 0.80, 0.63),
            "cta_button": (0.12, 0.38, 0.80, 0.48),
        },
    }


def _fallback_layout() -> dict[str, Any]:
    return {
        "selected_size": 0.052,
        "line_count": 1,
        "safe_area": dict(_CANONICAL_SAFE_AREA),
        "typography": {role: dict(values) for role, values in _CANONICAL_TYPOGRAPHY.items()},
    }


def _box(box: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    left, bottom, right, top = box
    return ((left + right) / 2, (bottom + top) / 2, right - left, top - bottom)


def _frame_to_timecode(frame: int, fps: float) -> str:
    """Convert an absolute Resolve frame to a non-drop-frame timecode."""
    absolute = max(0, int(frame))
    rate = max(1, int(round(float(fps))))
    total_seconds, frames = divmod(absolute, rate)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}:{frames:02d}"


def _sequence_boundaries(card_count: int, total_duration_frames: int) -> list[int]:
    """Return integer boundaries that cover the whole composition without gaps."""
    return [(index * total_duration_frames) // card_count
            for index in range(card_count + 1)]


def _sequence_windows(card_count: int, total_duration_frames: int,
                      transition_overlap_frames: int = 10) -> list[tuple[int, int]]:
    """Return contiguous starts with enough tail for an incoming-card crossfade."""
    boundaries = _sequence_boundaries(card_count, total_duration_frames)
    overlap = min(max(0, int(transition_overlap_frames)),
                  max(0, total_duration_frames // card_count - 1))
    return [
        (boundaries[index], min(total_duration_frames, boundaries[index + 1] +
                                (overlap if index < card_count - 1 else 0)))
        for index in range(card_count)
    ]


def _review_reading_frames(review: dict[str, Any]) -> int:
    """Return the canonical four-words-per-second duration at 30 fps."""
    words = len(str(review.get("text") or "").split())
    seconds = max(3, math.ceil(words / 4.0) + 1)
    return seconds * 30


def _automatic_sequence_windows(reviews: list[dict[str, Any]],
                                transition_overlap_frames: int = 10,
                                readability_layouts: list[dict[str, Any]] | None = None) -> tuple[list[tuple[int, int]], int]:
    """Allocate individual card windows from their actual reading times."""
    base_durations = (
        [int(layout["duration_frames"]) for layout in readability_layouts]
        if readability_layouts is not None
        else [_review_reading_frames(review) for review in reviews]
    )
    windows: list[tuple[int, int]] = []
    cursor = 0
    for index, duration in enumerate(base_durations):
        end = cursor + duration
        visible_end = end + (transition_overlap_frames if index < len(reviews) - 1 else 0)
        windows.append((cursor, visible_end))
        cursor = end
    return windows, cursor


def _fixed_readability_windows(
    readability_layouts: list[dict[str, Any]],
    total_duration_frames: int,
    transition_overlap_frames: int = 10,
) -> list[tuple[int, int]]:
    """Distribute surplus time without shortening any assessed card."""
    durations = [int(layout["duration_frames"]) for layout in readability_layouts]
    minimum = sum(durations)
    if total_duration_frames < minimum:
        raise ValidationError(
            f"Durata recensioni inferiore alla leggibilità ({minimum})"
        )
    surplus, remainder = divmod(total_duration_frames - minimum, len(durations))
    allocated = [
        duration + surplus + (1 if index < remainder else 0)
        for index, duration in enumerate(durations)
    ]
    windows: list[tuple[int, int]] = []
    cursor = 0
    for index, duration in enumerate(allocated):
        end = cursor + duration
        visible_end = end + (transition_overlap_frames if index < len(allocated) - 1 else 0)
        windows.append((cursor, visible_end))
        cursor = end
    return windows


def _cta_duration_frames(cta: dict[str, Any]) -> int:
    """Give the end card a calm but concise fixed reading window."""
    words = len(f"{cta.get('headline') or ''} {cta.get('text') or ''}".split())
    return max(120, min(180, int(words / 4.5 + 1.999) * 30))


def _intro_duration_frames(_intro: dict[str, Any]) -> int:
    """Keep a concise, recognisable opening card before the reviews."""
    return 90


def _timeline_is_vertical(timeline: Any) -> bool:
    """Return whether the current timeline is portrait, without guessing from its name."""
    try:
        width = int(float(safe_call(timeline, "GetSetting", "timelineResolutionWidth") or 0))
        height = int(float(safe_call(timeline, "GetSetting", "timelineResolutionHeight") or 0))
    except (TypeError, ValueError):
        return False
    return height > width > 0


def create_review_sequence(project: Any, timeline: Any, config: CreativeConfig, registry: Registry,
                           name: str, reviews: list[dict[str, Any]],
                           total_duration_frames: int = 0,
                           style_role: str = "cream", cta: dict[str, Any] | None = None,
                           intro: dict[str, Any] | None = None,
                           *, readability_layouts: list[dict[str, Any]]) -> dict:
    """Create a gap-free review sequence inside one Fusion composition.

    Pass ``0`` (the default) to let the bridge derive every card's time on
    screen from its text.  A positive value remains available for a deliberate
    fixed-duration edit.
    """
    require_capability("CAP_REVIEW", config, None, project, timeline)
    require_capability("CAP_FUSION", config, None, project, timeline)
    if not isinstance(reviews, list) or not 1 <= len(reviews) <= 8:
        raise ValidationError("reviews deve contenere 1-8 card")
    if any(not isinstance(review, dict) for review in reviews):
        raise ValidationError("Ogni review deve essere un oggetto")
    if len(readability_layouts) != len(reviews):
        raise ValidationError("readability_layouts deve corrispondere alle review")
    if cta is not None:
        if not isinstance(cta, dict):
            raise ValidationError("cta deve essere un oggetto")
        if not isinstance(cta.get("headline"), str) or not cta["headline"].strip():
            raise ValidationError("cta.headline richiesto")
        if not isinstance(cta.get("text"), str) or not cta["text"].strip():
            raise ValidationError("cta.text richiesto")
    if intro is not None:
        if not isinstance(intro, dict):
            raise ValidationError("intro deve essere un oggetto")
        if not isinstance(intro.get("headline"), str) or not intro["headline"].strip():
            raise ValidationError("intro.headline richiesto")
        if not isinstance(intro.get("text"), str) or not intro["text"].strip():
            raise ValidationError("intro.text richiesto")
    if (isinstance(total_duration_frames, bool)
            or not isinstance(total_duration_frames, int)
            or not 0 <= total_duration_frames <= MAX_AUTOMATIC_FUSION_FRAMES):
        raise ValidationError(
            f"total_duration_frames deve essere 0 (automatico) oppure tra il numero di card e {MAX_AUTOMATIC_FUSION_FRAMES}"
        )
    automatic_duration = total_duration_frames == 0
    if automatic_duration:
        windows, review_duration_frames = _automatic_sequence_windows(
            reviews, readability_layouts=readability_layouts
        )
        intro_duration_frames = _intro_duration_frames(intro) if intro else 0
        windows = [(start + intro_duration_frames, end + intro_duration_frames)
                   for start, end in windows]
        cta_duration_frames = _cta_duration_frames(cta) if cta else 0
        total_duration_frames = intro_duration_frames + review_duration_frames + cta_duration_frames
    elif total_duration_frames < len(reviews):
        raise ValidationError(
            f"total_duration_frames deve essere almeno il numero di card ({len(reviews)})"
        )
    else:
        intro_duration_frames = _intro_duration_frames(intro) if intro else 0
        cta_duration_frames = _cta_duration_frames(cta) if cta else 0
        review_duration_frames = total_duration_frames - intro_duration_frames - cta_duration_frames
        if review_duration_frames < len(reviews):
            raise ValidationError("Durata insufficiente dopo aver riservato la CTA")
        transition_overlap_frames = min(10, max(0, review_duration_frames // len(reviews) - 1))
        windows = [(start + intro_duration_frames, end + intro_duration_frames)
                   for start, end in _fixed_readability_windows(
                       readability_layouts, review_duration_frames, transition_overlap_frames
                   )]
    validate_color_role(style_role)
    timeline_name = str(safe_call(timeline, "GetName") or "")
    if not timeline_name.startswith("ARPHE_"):
        raise ValidationError("La sequenza richiede una timeline ARPHE")
    composition = create_composition(project, timeline, config, registry,
                                     name, 0, total_duration_frames)
    if not composition.get("ok"):
        return {"ok": False, "action": "create_review_sequence",
                "stage": "composition", "composition": composition}
    composition_id = composition["composition_id"]
    # Beige gives the sequence a warmer ARPHÈ canvas while retaining enough
    # contrast for the cream review cards to read as distinct objects.
    background = add_background(project, timeline, config, registry, composition_id, "beige")
    if not background.get("ok"):
        return {"ok": False, "action": "create_review_sequence",
                "stage": "background", "composition_id": composition_id,
                "background": background}
    intro_result = None
    if intro:
        intro_result = add_intro_card(project, timeline, config, registry, composition_id,
                                      intro["headline"], intro["text"], 0,
                                      intro_duration_frames,
                                      readability_layout=readability_layouts[0])

    # Windows cover the whole composition.  Automatic mode uses independent
    # reading times; explicit mode preserves the fixed-duration contract.
    transition_overlap_frames = min(10, max(0, total_duration_frames // len(reviews) - 1))
    results: list[dict[str, Any]] = []
    for index, review in enumerate(reviews):
        text = review.get("text")
        stars = review.get("stars", 5)
        label = review.get("small_label")
        start, end = windows[index]
        card = add_review_card(project, timeline, config, registry, composition_id,
                               text, stars, start, end, style_role,
                               review.get("highlight_text"), label,
                               readability_layout=readability_layouts[index])
        results.append({"index": index, "card_id": card["card_id"],
                        "frame_range": [start, end]})
    cta_result = None
    if cta:
        # Resolve evaluates the final carrier frame at the composition's end
        # tick.  Keep the CTA visibility spline alive for that one additional
        # tick so the final exported frame stays branded rather than flashing
        # back to the ivory carrier.
        cta_result = add_end_card(project, timeline, config, registry, composition_id,
                                  cta["headline"], cta["text"], intro_duration_frames + review_duration_frames,
                                  total_duration_frames + 1, cta.get("style_role", "burgundy"),
                                  readability_layout=readability_layouts[0])
        cta_result["timeline_frame_range"] = [intro_duration_frames + review_duration_frames,
                                                 total_duration_frames]
    return {"ok": True, "action": "create_review_sequence", "timeline": timeline_name,
            "composition_id": composition_id,
            "timeline_item": composition.get("timeline_item"),
            "cards": results, "total_duration_frames": total_duration_frames,
            "coverage": [0, total_duration_frames], "gap_free": True,
            "transition_overlap_frames": transition_overlap_frames,
            "duration_mode": "automatic_reading_time" if automatic_duration else "fixed_total",
            "maximum_automatic_duration_frames": MAX_AUTOMATIC_FUSION_FRAMES,
            "intro": intro_result,
            "cta": cta_result,
            "status": "PENDING"}


def _merge(comp: Any, background: Any, foreground: Any, name: str) -> Any:
    merge = _new_tool(comp, "Merge", name)
    if not connect_input(merge, "Background", background):
        raise RuntimeError(f"Collegamento background fallito: {name}")
    if not connect_input(merge, "Foreground", foreground):
        raise RuntimeError(f"Collegamento foreground fallito: {name}")
    return merge


def _input_matches(tool: Any, name: str, expected: Any) -> bool:
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


def _text(comp: Any, name: str, value: str, size: float, color: dict[str, float], y: float,
          *, font: str = "Open Sans", style: str = "Regular", layout_type: float = 0.0,
          frame_width: float | None = None, frame_height: float | None = None,
          x: float = 0.5) -> Any:
    tool = _new_tool(comp, "TextPlus", name)
    requested: dict[str, Any] = {
        "StyledText": value,
        "Font": font,
        "Style": style,
        "Size": float(size),
        "Center": {1: x, 2: y, 3: 0.0},
        "LayoutType": float(layout_type),
        "HorizontalJustificationNew": 3.0,
        "VerticalJustificationNew": 3.0,
    }
    if frame_width is not None:
        requested["LayoutWidth"] = float(frame_width)
    if frame_height is not None:
        requested["LayoutHeight"] = float(frame_height)
    required = {key: _set(tool, key, value) for key, value in requested.items()}
    for key, channel in (("Red1", "r"), ("Green1", "g"), ("Blue1", "b"), ("Alpha1", "a")):
        requested[key] = float(color[channel])
        required[key] = _set(tool, key, requested[key])
    failed = [key for key, ok in required.items() if not ok]
    if failed:
        raise RuntimeError(f"Configurazione Text+ incompleta per {name}: {', '.join(failed)}")
    mismatched = [key for key, expected in requested.items()
                  if not _input_matches(tool, key, expected)]
    if mismatched:
        raise RuntimeError(f"Read-back Text+ non corrispondente per {name}: {', '.join(mismatched)}")
    return tool


def _tool_name(tool: Any) -> str | None:
    attrs = safe_call(tool, "GetAttrs") or {}
    name = attrs.get("TOOLS_Name") if isinstance(attrs, dict) else None
    return name if isinstance(name, str) and name else None


def _tool_snapshot(comp: Any) -> set[str]:
    tools = safe_call(comp, "GetToolList") or {}
    values = tools.values() if isinstance(tools, dict) else tools
    return {name for tool in values if (name := _tool_name(tool))}


def _remove_tools_created_after(comp: Any, snapshot: set[str]) -> int:
    """Best-effort rollback limited to tools created by the current primitive."""
    tools = safe_call(comp, "GetToolList") or {}
    values = list(tools.values()) if isinstance(tools, dict) else list(tools)
    removed = 0
    for tool in reversed(values):
        name = _tool_name(tool)
        # Never delete an unnamed or non-ARPHE tool during recovery.
        if not name or name in snapshot or not name.startswith("ARPHE_"):
            continue
        try:
            tool.Delete()
            removed += 1
        except Exception:
            pass
    return removed


def add_review_card(project: Any, timeline: Any, config: CreativeConfig, registry: Registry,
                    composition_id: str, text: str, stars: int, start_frame: int, end_frame: int,
                    style_role: str, highlight_text: str | None = None,
                    small_label: str | None = None,
                    *, readability_layout: dict[str, Any]) -> dict:
    require_capability("CAP_REVIEW", config, None, project, timeline)
    start, end = validate_frame_range(start_frame, end_frame)
    validate_review(text, stars, highlight_text, small_label)
    validate_color_role(style_role)
    _, comp = find_composition(timeline, registry, composition_id)
    card_id = _id("CARD")
    snapshot = _tool_snapshot(comp)
    undo_started = False
    try:
        start_undo = getattr(comp, "StartUndo", None)
        if callable(start_undo):
            start_undo(f"ARPHE add review card {card_id}")
            undo_started = True
    except Exception:
        pass
    try:
        # Text nodes come first: their live schema/read-back is the most fragile part.
        # Any failure below removes every node created by this primitive.
        dark = _rgb(config.palette["dark_brown"])
        vertical = _timeline_is_vertical(timeline)
        if vertical:
            # A phone is the primary viewing distance for a Reel.  Use a much
            # larger type scale and let the card grow vertically rather than
            # preserving desktop proportions.
            geometry = _portrait_review_geometry(readability_layout)
            body_font, body_style = _layout_typography(readability_layout, "body")
            label_font, label_style = _layout_typography(readability_layout, "label")
            card_x, card_y, card_width, card_height = _box(geometry["boxes"]["card"])
            text_x, text_y, text_width, text_height = _box(geometry["boxes"]["body"])
            stars_x, stars_y, stars_width, stars_height = _box(geometry["boxes"]["stars"])
            review_size = geometry["body_size"]
            stars_size = 0.045
        else:
            body_font, body_style = "Satoshi", "Regular"
            label_font, label_style = "Satoshi", "Medium"
            review_size = 0.036 if len(text) <= 180 else 0.031
            card_x, card_y = 0.5, 0.5
            card_width, card_height = 0.78, 0.38
            text_x, text_y = 0.5, 0.49
            text_width, text_height = 0.66, 0.17
            stars_size, stars_x, stars_y, stars_width, stars_height = 0.035, 0.5, 0.62, 0.66, 0.06
        review = _text(comp, f"{card_id}_TEXT", text, review_size, dark, text_y,
                       font=body_font, style=body_style, layout_type=1.0,
                       frame_width=text_width, frame_height=text_height, x=text_x)
        stars_tool = _text(comp, f"{card_id}_STARS", " ".join("★" for _ in range(stars)),
                           stars_size, _rgb(config.palette["burgundy"]), stars_y,
                           font="Segoe UI Symbol", style="Regular", layout_type=1.0,
                           frame_width=stars_width, frame_height=stars_height, x=stars_x)
        label_tool = (_text(comp, f"{card_id}_LABEL", small_label, 0.019, dark, 0.37,
                            font=label_font, style=label_style, layout_type=1.0,
                            frame_width=0.68, frame_height=0.06, x=0.46 if vertical else 0.5)
                      if small_label else None)
        highlight_tool = (_text(comp, f"{card_id}_HIGHLIGHT", highlight_text, 0.028,
                                _rgb(config.palette["burgundy"]), 0.405,
                                font=label_font, style=label_style, layout_type=1.0,
                                frame_width=0.68 if vertical else 0.60, frame_height=0.055,
                                x=0.46 if vertical else 0.5)
                          if highlight_text else None)

        background = _new_tool(comp, "Background", f"{card_id}_BG")
        _set_color(background, _rgb(config.palette[style_role]))
        mask = _new_tool(comp, "RectangleMask", f"{card_id}_MASK")
        _set(mask, "Width", card_width)
        _set(mask, "Height", card_height)
        _set(mask, "Center", {1: card_x, 2: card_y, 3: 0.0})
        _set(mask, "CornerRadius", 0.055)
        if not connect_input(background, "EffectMask", mask):
            raise RuntimeError("Collegamento maschera card fallito")

        shadow = _new_tool(comp, "Background", f"{card_id}_SHADOW")
        _set_color(shadow, _rgb(config.palette["black"], 0.13))
        shadow_mask = _new_tool(comp, "RectangleMask", f"{card_id}_SHADOW_MASK")
        _set(shadow_mask, "Width", card_width)
        _set(shadow_mask, "Height", card_height)
        _set(shadow_mask, "CornerRadius", 0.055)
        _set(shadow_mask, "Center", {1: card_x + 0.012, 2: card_y - 0.015, 3: 0.0})
        if not connect_input(shadow, "EffectMask", shadow_mask):
            raise RuntimeError("Collegamento maschera ombra fallito")
        card = _merge(comp, shadow, background, f"{card_id}_CARD_MERGE")
        card = _merge(comp, card, review, f"{card_id}_TEXT_MERGE")
        card = _merge(comp, card, stars_tool, f"{card_id}_STARS_MERGE")
        if label_tool:
            card = _merge(comp, card, label_tool, f"{card_id}_LABEL_MERGE")
        if highlight_tool:
            card = _merge(comp, card, highlight_tool, f"{card_id}_HIGHLIGHT_MERGE")

        transform = _new_tool(comp, "Transform", f"{card_id}_TRANSFORM")
        if not connect_input(transform, "Input", card):
            raise RuntimeError("Collegamento card al Transform fallito")
        outer_merge_name = f"{card_id}_OUTER_MERGE"
        outer_merge = add_layer(comp, transform, outer_merge_name)
        timing_applied = set_visibility_window(comp, outer_merge, start, end)
        registry.add_element(card_id, {
            "kind": "review_card", "composition_id": composition_id,
            "transform_name": f"{card_id}_TRANSFORM",
            "outer_merge_name": outer_merge_name if outer_merge else None,
            "highlight_name": f"{card_id}_HIGHLIGHT" if highlight_tool else None,
            "start_frame": start, "end_frame": end,
        })
    except Exception as exc:
        removed = _remove_tools_created_after(comp, snapshot)
        if undo_started:
            safe_call(comp, "EndUndo", True)
        raise RuntimeError(f"add_review_card annullata; nodi rimossi={removed}: {exc}") from exc
    if undo_started:
        safe_call(comp, "EndUndo", True)
    return {"ok": True, "action": "add_review_card", "composition_id": composition_id,
            "card_id": card_id, "stars": stars, "frame_range": [start, end],
            "style_role": style_role, "timing_applied": timing_applied,
            "review_layout": "portrait_frame" if vertical else "landscape_frame", "review_font": "Satoshi",
            "stars_font": "Segoe UI Symbol", "text_readback_verified": True,
            "status": "PENDING"}


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
                 end_frame: int, style_role: str = "burgundy", *,
                 readability_layout: dict[str, Any] | None = None) -> dict:
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
    vertical = _timeline_is_vertical(timeline)
    layout = readability_layout or _fallback_layout()
    heading_font, heading_style = _layout_typography(layout, "heading")
    button_font, button_style = _layout_typography(layout, "button")
    heading = _text(comp, f"{element_id}_HEADLINE", headline, 0.092 if vertical else 0.07,
                    _rgb(config.palette["white"]), 0.55, font=heading_font, style=heading_style,
                    layout_type=1.0, frame_width=0.68 if vertical else 0.70,
                    frame_height=0.16, x=0.46 if vertical else 0.5)
    merged = _merge(comp, background, heading, f"{element_id}_HEADLINE_MERGE")
    cta_tool = _text(comp, f"{element_id}_CTA", cta, 0.055 if vertical else 0.045,
                     _rgb(config.palette["cream"]), 0.43, font=button_font, style=button_style,
                     layout_type=1.0, frame_width=0.68 if vertical else 0.70,
                     frame_height=0.10, x=0.46 if vertical else 0.5)
    merged = _merge(comp, merged, cta_tool, f"{element_id}_CTA_MERGE")
    transform = _new_tool(comp, "Transform", f"{element_id}_TRANSFORM")
    if not connect_input(transform, "Input", merged):
        raise RuntimeError("Collegamento end card al Transform fallito")
    outer_name = f"{element_id}_OUTER_MERGE"
    outer = add_layer(comp, transform, outer_name)
    timing_applied = set_visibility_window(comp, outer, start, end)
    registry.add_element(element_id, {"kind": "end_card", "composition_id": composition_id,
                                      "transform_name": f"{element_id}_TRANSFORM",
                                      "outer_merge_name": outer_name if outer else None,
                                      "start_frame": start, "end_frame": end})
    return {"ok": True, "action": "add_end_card", "element_id": element_id,
            "frame_range": [start, end], "timing_applied": timing_applied, "status": "PENDING"}


def add_intro_card(project: Any, timeline: Any, config: CreativeConfig, registry: Registry,
                   composition_id: str, headline: str, subheading: str, start_frame: int,
                   end_frame: int, *, readability_layout: dict[str, Any] | None = None) -> dict:
    """Add a layered ARPHÈ opening card using only the canonical kit palette."""
    start, end = validate_frame_range(start_frame, end_frame)
    _, comp = find_composition(timeline, registry, composition_id)
    element_id = _id("INTRO_CARD")
    background = _new_tool(comp, "Background", f"{element_id}_BG")
    _set_color(background, _rgb(config.palette["beige"]))
    # A restrained editorial panel is more recognisable than a bare pair of
    # lines: cream card and generous ivory negative space.  There is
    # deliberately no vertical rule: beside a large first letter it reads as
    # an accidental glyph rather than an intentional brand element.
    vertical = _timeline_is_vertical(timeline)
    layout = readability_layout or _fallback_layout()
    heading_font, heading_style = _layout_typography(layout, "heading")
    body_font, body_style = _layout_typography(layout, "body")
    label_font, label_style = _layout_typography(layout, "label")
    panel = _new_tool(comp, "Background", f"{element_id}_PANEL")
    _set_color(panel, _rgb(config.palette["cream"]))
    panel_mask = _new_tool(comp, "RectangleMask", f"{element_id}_PANEL_MASK")
    _set(panel_mask, "Width", 0.76 if vertical else 0.58)
    _set(panel_mask, "Height", 0.40 if vertical else 0.46)
    if vertical:
        _set(panel_mask, "Center", {1: 0.46, 2: 0.50, 3: 0.0})
    _set(panel_mask, "CornerRadius", 0.07)
    if not connect_input(panel, "EffectMask", panel_mask):
        raise RuntimeError("Collegamento pannello intro fallito")
    merged = _merge(comp, background, panel, f"{element_id}_PANEL_MERGE")
    eyebrow = _text(comp, f"{element_id}_EYEBROW", "ARPHE POLIAMBULATORIO", 0.024 if vertical else 0.020,
                    _rgb(config.palette["warm_brown"]), 0.64 if vertical else 0.65,
                    font=label_font, style=label_style, layout_type=1.0,
                    frame_width=0.68 if vertical else 0.44, frame_height=0.06,
                    x=0.46 if vertical else 0.5)
    merged = _merge(comp, merged, eyebrow, f"{element_id}_EYEBROW_MERGE")
    display_headline = "Dicono\ndi noi" if headline.strip().casefold() == "dicono di noi" else headline
    heading = _text(comp, f"{element_id}_HEADLINE", display_headline, 0.098 if vertical else 0.078,
                    _rgb(config.palette["burgundy"]), 0.505 if vertical else 0.515,
                    font=heading_font, style=heading_style,
                    layout_type=1.0, frame_width=0.68 if vertical else 0.44,
                    frame_height=0.23 if vertical else 0.20,
                    x=0.46 if vertical else 0.5)
    merged = _merge(comp, merged, heading, f"{element_id}_HEADLINE_MERGE")
    subheading_tool = _text(comp, f"{element_id}_SUBHEADING", subheading, 0.044 if vertical else 0.038,
                            _rgb(config.palette["warm_brown"]), 0.35 if vertical else 0.365,
                            font=body_font, style=body_style, layout_type=1.0,
                            frame_width=0.68 if vertical else 0.44, frame_height=0.10,
                            x=0.46 if vertical else 0.5)
    merged = _merge(comp, merged, subheading_tool, f"{element_id}_SUBHEADING_MERGE")
    transform = _new_tool(comp, "Transform", f"{element_id}_TRANSFORM")
    if not connect_input(transform, "Input", merged):
        raise RuntimeError("Collegamento intro al Transform fallito")
    outer_name = f"{element_id}_OUTER_MERGE"
    outer = add_layer(comp, transform, outer_name)
    timing_applied = set_visibility_window(comp, outer, start, end)
    registry.add_element(element_id, {"kind": "intro_card", "composition_id": composition_id,
                                      "transform_name": f"{element_id}_TRANSFORM",
                                      "outer_merge_name": outer_name if outer else None,
                                      "start_frame": start, "end_frame": end})
    return {"ok": True, "action": "add_intro_card", "element_id": element_id,
            "frame_range": [start, end], "timing_applied": timing_applied, "status": "PENDING"}


def _animate(comp: Any, record: dict, plan: dict, reverse: bool = False) -> bool:
    transform = safe_call(comp, "FindTool", record.get("transform_name"))
    if not transform:
        return False
    outer = safe_call(comp, "FindTool", record.get("outer_merge_name"))
    keys = list(reversed(plan["keys"])) if reverse else plan["keys"]
    static_transform = all(
        float(key["x"]) == 0.0 and float(key["y"]) == 0.0
        and float(key["scale"]) == 1.0 and float(key["rotation"]) == 0.0
        for key in keys
    )
    # Attach modifiers before populating them; Resolve 21 otherwise creates the
    # spline nodes but continues evaluating the inputs at their defaults.
    # Center is a 2D point, so Resolve evaluates it through a Path modifier.
    # BezierSpline silently accepts the assignment but leaves Center static.
    center = size = angle = None
    if not static_transform:
        transform.Center = comp.Path()
        transform.Size = comp.BezierSpline()
        transform.Angle = comp.BezierSpline()
        center = transform.Center
        size = transform.Size
        angle = transform.Angle
    opacity = None
    if outer:
        outer.Blend = comp.BezierSpline()
        opacity = outer.Blend
    # Transform.Blend is the transform contribution, not card opacity. Keep it
    # fully enabled; opacity belongs on the outer composite merge.
    transform.Blend = 1.0
    for index, key in enumerate(keys):
        frame = key["frame"]
        if center is not None:
            center[frame] = {1: 0.5 + key["x"], 2: 0.5 + key["y"], 3: 0.0}
            size[frame] = key["scale"]
            angle[frame] = key["rotation"]
        if opacity is not None:
            opacity[frame] = key["opacity"]
    if opacity is not None and static_transform and len(keys) >= 2:
        # Fusion's Bezier spline can sag between distant opacity keys even
        # when both endpoints are 1.  CTA fades are short, so write their
        # eased opacity explicitly frame by frame and remove that ambiguity.
        ordered = sorted(keys, key=lambda item: int(item["frame"]))
        for first, second in zip(ordered, ordered[1:]):
            first_frame, second_frame = int(first["frame"]), int(second["frame"])
            span = max(1, second_frame - first_frame)
            for frame in range(first_frame, second_frame + 1):
                progress = (frame - first_frame) / span
                eased = progress * progress * (3.0 - 2.0 * progress)
                opacity[frame] = float(first["opacity"]) + (
                    float(second["opacity"]) - float(first["opacity"])
                ) * eased
    if opacity is not None and record.get("end_frame") is not None:
        # Motion and visibility must share one Blend spline.  Replacing the
        # visibility spline with only the two entry keys makes Fusion ease the
        # card back towards zero for its whole lifetime.  Explicit zero/hold
        # keys preserve a crisp card after the entrance through its final
        # visible frame.
        start_frame = int(record.get("start_frame") or 0)
        end_frame = int(record["end_frame"])
        if start_frame > 0:
            opacity[0] = 0.0
            opacity[start_frame - 1] = 0.0
        hold_frame = max(start_frame, end_frame - 1)
        if static_transform:
            last_motion_frame = max(int(key["frame"]) for key in keys)
            for frame in range(last_motion_frame, hold_frame + 1):
                opacity[frame] = 1.0
        else:
            opacity[hold_frame] = 1.0
        # Resolve can extrapolate Path/Bezier values beyond the last motion
        # keyframe. Pin every transform channel through the visibility hold,
        # otherwise CTA text may drift out of frame while its full-screen
        # background still appears correct.
        if center is not None:
            center[hold_frame] = {1: 0.5, 2: 0.5, 3: 0.0}
            size[hold_frame] = 1.0
            angle[hold_frame] = 0.0
        opacity[end_frame] = 0.0
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
