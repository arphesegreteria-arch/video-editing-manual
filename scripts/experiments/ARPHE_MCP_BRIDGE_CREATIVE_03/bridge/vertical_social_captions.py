"""Reusable ARPHÈ caption template for the generic Vertical Social workflow.

The approved route is ``CAPTIONS`` after picture lock: timeline transcription,
timed cues, then this Fusion overlay.  It intentionally uses the validated
karaoke treatment (burgundy card behind the spoken word; white Satoshi Bold
text; word-by-word timing) instead of Resolve's native subtitle presets.

Keep this module generic.  Captions differ through approved cue data and safe
placement only; never add an MCP command, preset, project, timeline, or video
identifier dedicated to a single edit.

Timing has two coordinate systems that must never be mixed: the carrier is
placed at ``timeline.GetStartFrame() + local_start``, while every Fusion cue
keyframe remains local to the composition (``0..duration-1``).  Adding the
timeline timecode offset to Fusion keyframes makes the captions invisible.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from .carabellese_checkpoint import timeline_content_fingerprint
from .fusion_tools import (_media_out, _new_tool, _rgb, _set, _set_color,
                           add_layer, connect_input, set_visibility_window)
from .resolve_connection import safe_call
from .safety import ValidationError
from .vertical_social_overlay import create_overlay_composition


def lower_caption_layout() -> dict[str, Any]:
    """Return the story-safe lower-third geometry in Fusion coordinates.

    Fusion's Y origin is at the bottom; the reported bounds use the usual
    screen convention (top to bottom) so they can be checked against the
    Graphic Kit safe-area contract.
    """
    center_x, center_y = 0.46, 0.27
    width, height = 0.68, 0.07
    text_width, text_height = 0.62, 0.065
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


def upper_karaoke_layout() -> dict[str, float]:
    """Keep the moving word card compact within the established upper safe area."""
    return {"y": 0.86, "height": 0.06, "span": 0.60}


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


STANDARD_FONT_SIZE = 0.050
EMPHASIS_FONT_SIZE = 0.065
CAPTION_CARD_PADDING = 0.016
CAPTION_WORD_GAP = 0.014


def _caption_geometry(position: str) -> tuple[float, float, float, float]:
    if position == "UPPER":
        layout = upper_karaoke_layout()
        return 0.5, layout["y"], layout["span"], 0.075
    layout = lower_caption_layout()
    return layout["center"]["x"], layout["center"]["y"], layout["width"], 0.090


def _word_metrics(word: dict[str, Any]) -> dict[str, Any]:
    emphasized = bool(word.get("emphasis", False))
    display_text = str(word["text"]).upper()
    glyph_units = sum(
        0.82 if character in "MW" else
        0.40 if character in "IJLTF" else
        0.30 if not character.isalnum() else
        0.60
        for character in display_text
    )
    glyph_units = max(1.2, glyph_units)
    font_size = EMPHASIS_FONT_SIZE if emphasized else STANDARD_FONT_SIZE
    width_factor = 0.95 if emphasized else 0.90
    text_width = glyph_units * font_size * width_factor
    return {
        "text": word["text"], "display_text": display_text,
        "range": word["range"], "emphasis": emphasized,
        "font_size": font_size, "text_width": text_width,
        "card_width": text_width + CAPTION_CARD_PADDING,
    }


def _row_width(words: tuple[dict[str, Any], ...]) -> float:
    return (sum(word["card_width"] for word in words)
            + CAPTION_WORD_GAP * max(0, len(words) - 1))


def _caption_rows(words: tuple[dict[str, Any], ...], span: float) -> tuple[tuple[dict[str, Any], ...], ...]:
    if _row_width(words) <= span:
        return (words,)
    candidates: list[tuple[float, float, int, tuple[dict[str, Any], ...], tuple[dict[str, Any], ...]]] = []
    for split_at in range(1, len(words)):
        first, second = words[:split_at], words[split_at:]
        first_width, second_width = _row_width(first), _row_width(second)
        if first_width <= span and second_width <= span:
            candidates.append((max(first_width, second_width),
                               abs(first_width - second_width), split_at, first, second))
    if not candidates:
        raise ValidationError("Frase CAPTIONS troppo densa per due righe a misura fissa")
    _, _, _, first, second = min(candidates, key=lambda item: (item[1], item[0], item[2]))
    return first, second


def phrase_word_layout(phrase: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    """Place fixed-size caption words on one or two centered safe rows."""
    raw_words = tuple(phrase.get("words") or ())
    if not raw_words:
        raise ValidationError("Frase CAPTIONS senza parole")
    center_x, center_y, span, row_spacing = _caption_geometry(str(phrase.get("position", "LOWER")))
    metrics = tuple(_word_metrics(word) for word in raw_words)
    rows = _caption_rows(metrics, span)
    if len(rows) == 1:
        row_y = (center_y,)
    elif phrase.get("position") == "UPPER":
        row_y = (center_y, center_y - row_spacing)
    else:
        row_y = (center_y + row_spacing / 2, center_y - row_spacing / 2)
    placed: list[dict[str, Any]] = []
    for row_index, (row, y) in enumerate(zip(rows, row_y, strict=True)):
        width = _row_width(row)
        cursor = center_x - width / 2
        for word in row:
            card_width = word["card_width"]
            placed.append({**word,
                           "x": round(cursor + card_width / 2, 5),
                           "y": round(y, 5),
                           "row_index": row_index,
                           "slot_width": round(card_width, 5),
                           "font_size": round(word["font_size"], 5),
                           "text_width": round(word["text_width"], 5),
                           "card_width": round(card_width, 5)})
            cursor += card_width + CAPTION_WORD_GAP
    return tuple(placed)


def phrase_groups_from_word_cues(cues: tuple[dict[str, Any], ...], *,
                                 max_words: int = 7, max_characters: int = 30,
                                 pause_frames: int = 15) -> tuple[dict[str, Any], ...]:
    """Group transcript words into readable fixed-size one/two-row phrases."""
    phrases: list[dict[str, Any]] = []
    current: list[dict[str, Any]] = []

    def make_phrase(words: list[dict[str, Any]]) -> dict[str, Any]:
        if sum(bool(word.get("emphasis", False)) for word in words) > 1:
            raise ValidationError("Una frase CAPTIONS può avere al massimo una parola emphasis")
        first, last = words[0], words[-1]
        return {
            "phrase_id": f"phrase_{len(phrases) + 1:03d}",
            "text": " ".join(word["text"] for word in words),
            "range": (first["range"][0], last["range"][1]),
            "position": first["position"],
            "words": tuple({"text": word["text"], "range": word["range"],
                            "emphasis": bool(word.get("emphasis", False))}
                           for word in words),
        }

    def fits(words: list[dict[str, Any]]) -> bool:
        try:
            phrase_word_layout(make_phrase(words))
            return True
        except ValidationError:
            return False

    def flush() -> None:
        if current:
            phrases.append(make_phrase(current))
            current.clear()

    for cue in cues:
        if current:
            previous = current[-1]
            pause = cue["range"][0] - previous["range"][1]
            closes_phrase = previous["text"].endswith((".", "!", "?"))
            different_position = cue["position"] != previous["position"]
            next_text = " ".join([*(word["text"] for word in current), cue["text"]])
            second_emphasis = (bool(cue.get("emphasis", False))
                               and any(bool(word.get("emphasis", False)) for word in current))
            candidate = [*current, cue]
            if (cue.get("phrase_break_before", False) or len(current) >= max_words
                    or len(next_text) > max_characters or pause >= pause_frames
                    or closes_phrase or different_position or second_emphasis
                    or not fits(candidate)):
                flush()
        current.append(cue)
        if not fits(current):
            raise ValidationError("Una parola CAPTIONS non entra nella safe area a misura fissa")
    flush()
    return tuple(phrases)


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


def _is_owned_caption_item(timeline: object, item: object) -> bool:
    """Recognize one exact full-range Fusion caption overlay created by this bridge."""
    if not str(safe_call(item, "GetName") or "").startswith("ARPHE_VERTICAL_CAPTIONS_"):
        return False
    timeline_start = safe_call(timeline, "GetStartFrame")
    timeline_end = safe_call(timeline, "GetEndFrame")
    comp_count = safe_call(item, "GetFusionCompCount")
    comp = safe_call(item, "GetFusionCompByIndex", 1) if comp_count == 1 else None
    return bool(
        isinstance(timeline_start, int) and isinstance(timeline_end, int)
        and safe_call(item, "GetStart") == timeline_start
        and safe_call(item, "GetEnd") == timeline_end
        and safe_call(item, "GetDuration") == timeline_end - timeline_start
        and comp is not None
        and safe_call(comp, "FindTool", "ARPHE_VERTICAL_CAPTIONS_CANVAS") is not None
    )


def remove_owned_caption_overlay(timeline: object) -> dict[str, Any]:
    """Remove exactly one verified bridge-owned caption overlay from a working copy."""
    named: list[tuple[int, object]] = []
    track_count = int(safe_call(timeline, "GetTrackCount", "video") or 0)
    for track in range(1, track_count + 1):
        for item in safe_call(timeline, "GetItemListInTrack", "video", track) or []:
            if str(safe_call(item, "GetName") or "").startswith("ARPHE_VERTICAL_CAPTIONS_"):
                named.append((track, item))
    if len(named) != 1 or not _is_owned_caption_item(timeline, named[0][1]):
        raise ValidationError(
            "Sostituzione CAPTIONS richiede un solo layer bridge verificato")
    track, item = named[0]
    stable_id = safe_call(item, "GetUniqueId")
    if not safe_call(timeline, "DeleteClips", [item], False):
        raise ValidationError("Rimozione layer CAPTIONS esistente fallita")
    remaining = safe_call(timeline, "GetItemListInTrack", "video", track) or []
    if any(
        (stable_id not in (None, "") and safe_call(entry, "GetUniqueId") == stable_id)
        or _is_owned_caption_item(timeline, entry)
        for entry in remaining
    ):
        raise ValidationError("Read-back rimozione layer CAPTIONS non corrispondente")
    if track == track_count and not remaining:
        if not safe_call(timeline, "DeleteTrack", "video", track):
            raise ValidationError("Rimozione traccia CAPTIONS vuota fallita")
    return {"removed": True, "track": track}


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
    replace_existing = action.get("replace_existing_captions", False)
    if not isinstance(replace_existing, bool):
        raise ValidationError("replace_existing_captions CAPTIONS deve essere booleano")
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
        phrase_break_before = raw.get("phrase_break_before", False) if isinstance(raw, dict) else False
        emphasis = raw.get("emphasis", False) if isinstance(raw, dict) else False
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
        if not isinstance(phrase_break_before, bool):
            raise ValidationError("phrase_break_before CAPTIONS deve essere booleano")
        if not isinstance(emphasis, bool):
            raise ValidationError("emphasis CAPTIONS deve essere booleano")
        seen.add(cue_id); previous_end = end
        cues.append({"cue_id": cue_id, "range": (start, end), "text": text,
                     "position": position, "phrase_break_before": phrase_break_before,
                     "emphasis": emphasis})
    cutoff = action.get("caption_cutoff_frame")
    if isinstance(cutoff, bool) or not isinstance(cutoff, int) or not 0 <= cutoff <= total_frames:
        raise ValidationError("caption_cutoff_frame CAPTIONS non valido")
    cues = list(cues_before_frame(tuple(cues), cutoff))
    word_cues = tuple(cues)
    return {"locked_edit_fingerprint": fingerprint, "cues": word_cues,
            "phrases": phrase_groups_from_word_cues(word_cues),
            "caption_cutoff_frame": cutoff,
            "replace_existing_captions": replace_existing}


def _set_expression(tool: object, input_name: str, expression: str) -> None:
    try:
        input_proxy = getattr(tool, input_name)
        result = input_proxy.SetExpression(expression)
        if result is False:
            raise RuntimeError("SetExpression=False")
    except Exception as exc:
        raise ValidationError(f"Espressione timing CAPTIONS fallita: {exc}") from exc


def build_caption_graph(comp: object, phrases: tuple[dict[str, Any], ...],
                        palette: dict[str, str]) -> dict[str, Any]:
    media_out = _media_out(comp)
    if media_out is None:
        raise ValidationError("MediaOut CAPTIONS non trovato")
    canvas = _new_tool(comp, "Background", "ARPHE_VERTICAL_CAPTIONS_CANVAS")
    _set_color(canvas, _rgb(palette.get("black", "#000000"), 0.0))
    if not connect_input(media_out, "Input", canvas):
        raise ValidationError("Collegamento canvas CAPTIONS fallito")
    lower_layout = lower_caption_layout()
    highlight_word_count = 0
    for phrase_index, phrase in enumerate(phrases, start=1):
        is_lower = phrase["position"] == "LOWER"
        upper_layout = upper_karaoke_layout()
        height = lower_layout["height"] if is_lower else upper_layout["height"]
        phrase_start, phrase_end = phrase["range"]
        words = phrase_word_layout(phrase)
        for word_index, word in enumerate(words, start=1):
            prefix = f"ARPHE_PHRASE_{phrase_index:03d}_WORD_{word_index:03d}"
            background = _new_tool(comp, "Background", f"{prefix}_BG")
            _set_color(background, _rgb(palette["burgundy"], 0.94))
            mask = _new_tool(comp, "RectangleMask", f"{prefix}_MASK")
            for key, value in (("Width", word["card_width"]), ("Height", height),
                               ("Center", {1: word["x"], 2: word["y"], 3: 0.0}),
                               ("CornerRadius", 0.16)):
                _set(mask, key, value)
            if not connect_input(background, "EffectMask", mask):
                raise ValidationError("Maschera CAPTIONS non collegata")
            outer = add_layer(comp, background, f"{prefix}_CARD")
            if outer is None or not set_visibility_window(comp, outer, *word["range"]):
                raise ValidationError("Finestra highlight CAPTIONS non impostata")
            highlight_word_count += 1
        for word_index, word in enumerate(words, start=1):
            prefix = f"ARPHE_PHRASE_{phrase_index:03d}_WORD_{word_index:03d}"
            text = _new_tool(comp, "TextPlus", f"{prefix}_TEXT")
            for key, value in (("StyledText", word["display_text"]), ("Font", "Satoshi"),
                               ("Style", "Bold Italic" if word["emphasis"] else "Bold"),
                               ("Size", word["font_size"]),
                               ("Center", {1: word["x"], 2: word["y"], 3: 0.0})):
                if not _set(text, key, value):
                    raise ValidationError(f"Impostazione Text+ CAPTIONS {key} fallita")
            white = _rgb(palette["white"])
            for key, value in (("Red1", white["r"]), ("Green1", white["g"]),
                               ("Blue1", white["b"]), ("Alpha1", 1.0)):
                _set(text, key, value)
            if safe_call(text, "GetInput", "StyledText") != word["display_text"]:
                raise ValidationError("Read-back testo CAPTIONS non corrispondente")
            outer = add_layer(comp, text, f"{prefix}_TEXT_OUTER")
            if outer is None or not set_visibility_window(comp, outer, phrase_start, phrase_end):
                raise ValidationError("Finestra frase CAPTIONS non impostata")
    return {"cue_count": sum(len(phrase["words"]) for phrase in phrases),
            "phrase_count": len(phrases), "highlight_word_count": highlight_word_count,
            "text_readback": True, "font": "Satoshi Bold",
            "gap_preserving": True, "lower_layout": lower_layout}


def apply_caption_action(project: object, timeline: object, config: Any,
                         action: dict[str, Any], total_frames: int) -> dict[str, Any]:
    plan = validate_caption_action(action, total_frames)
    replaced = (remove_owned_caption_overlay(timeline)
                if plan["replace_existing_captions"] else None)
    item, comp = create_overlay_composition(
        project, timeline, config, 0, total_frames, f"CAPTIONS_{action['action_id']}")
    graph = build_caption_graph(comp, plan["phrases"], config.palette)
    return {"ok": True, "action_id": str(action["action_id"]),
            "timeline": str(safe_call(timeline, "GetName") or ""),
            "range": [0, total_frames], "timeline_item": str(safe_call(item, "GetName") or ""),
            "locked_edit_fingerprint": plan["locked_edit_fingerprint"],
            "replaced_existing_captions": bool(replaced), **graph}
