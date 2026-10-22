"""Generic, safe transcript-to-caption test primitive."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .resolve_connection import safe_call
from .safety import ValidationError
from .timeline_tools import duplicate_timeline
from .vertical_social_captions import apply_caption_action, timeline_edit_fingerprint


def _parse_fps(timeline: Any) -> float:
    try:
        fps = float(safe_call(timeline, "GetSetting", "timelineFrameRate"))
    except (TypeError, ValueError):
        raise ValidationError("FPS timeline non leggibile") from None
    if fps not in {24.0, 25.0, 30.0}:
        raise ValidationError("FPS timeline CAPTIONS non supportato")
    return fps


def validate_source_spans(raw_spans: list[dict[str, int]], fps: float) -> tuple[dict[str, int], ...]:
    """Validate an explicit source-to-timeline frame map without guessing edits."""
    if not isinstance(raw_spans, list) or not raw_spans:
        raise ValidationError("source_spans CAPTIONS obbligatorio")
    spans: list[dict[str, int]] = []
    previous_timeline_end = -1
    for raw in raw_spans:
        if not isinstance(raw, dict):
            raise ValidationError("source_spans CAPTIONS non valido")
        start = raw.get("source_start_frame")
        end = raw.get("source_end_frame")
        timeline_start = raw.get("timeline_start_frame")
        if any(isinstance(value, bool) or not isinstance(value, int)
               for value in (start, end, timeline_start)):
            raise ValidationError("frame source_spans CAPTIONS devono essere interi")
        if start < 0 or end <= start or timeline_start < 0:
            raise ValidationError("range source_spans CAPTIONS non valido")
        timeline_end = timeline_start + (end - start)
        if timeline_start < previous_timeline_end:
            raise ValidationError("source_spans CAPTIONS sovrapposti nella timeline")
        spans.append({"source_start_frame": start, "source_end_frame": end,
                      "timeline_start_frame": timeline_start})
        previous_timeline_end = timeline_end
    return tuple(spans)


def _load_segments(config: Any, transcript_file: str) -> list[dict[str, Any]]:
    root = Path(config.transcript_root).resolve()
    candidate = (root / transcript_file).resolve()
    if not candidate.is_file() or not candidate.is_relative_to(root):
        raise ValidationError("Trascrizione non disponibile nella cartella autorizzata")
    try:
        data = json.loads(candidate.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError("Trascrizione CAPTIONS non leggibile") from exc
    segments = data.get("segments") if isinstance(data, dict) else None
    if not isinstance(segments, list):
        raise ValidationError("Formato trascrizione CAPTIONS non valido")
    return [segment for segment in segments if isinstance(segment, dict)]


def _append_word(text: str, word: str) -> str:
    return f"{text}{word}" if word.startswith(("'", "’")) else f"{text} {word}".strip()


def caption_cues_from_segments(segments: list[dict[str, Any]], spans: tuple[dict[str, int], ...],
                               fps: float, caption_mode: str = "STANDARD",
                               uppercase: bool = False) -> list[dict[str, Any]]:
    """Map word timestamps only through caller-supplied frame spans; preserve removed gaps."""
    mapped: list[tuple[float, float, str, int, int]] = []
    for segment in segments:
        for word in segment.get("words", []):
            if not isinstance(word, dict):
                continue
            try:
                start_seconds, end_seconds = float(word["start"]), float(word["end"])
            except (KeyError, TypeError, ValueError):
                continue
            text = str(word.get("word", "")).strip()
            if not text or end_seconds <= start_seconds:
                continue
            for span in spans:
                source_start = span["source_start_frame"] / fps
                source_end = span["source_end_frame"] / fps
                if source_start <= start_seconds and end_seconds <= source_end:
                    mapped.append((start_seconds, end_seconds, text,
                                   span["timeline_start_frame"] + round((start_seconds - source_start) * fps),
                                   span["timeline_start_frame"] + round((end_seconds - source_start) * fps)))
                    break
    if caption_mode not in {"STANDARD", "KARAOKE_WORD"}:
        raise ValidationError("caption_mode CAPTIONS non valido")
    if not isinstance(uppercase, bool):
        raise ValidationError("uppercase CAPTIONS deve essere booleano")
    if caption_mode == "KARAOKE_WORD":
        words: list[tuple[float, float, str, int, int]] = []
        for item in mapped:
            if item[2].startswith(("'", "’")) and words:
                previous = words[-1]
                words[-1] = (previous[0], item[1], previous[2] + item[2],
                             previous[3], max(previous[3] + 1, item[4]))
            else:
                words.append(item)
        return [
            {"cue_id": f"caption_{index:03d}", "start_frame": word[3],
             "end_frame": max(word[3] + 1, word[4]),
             "text": word[2].upper() if uppercase else word[2], "position": "LOWER"}
            for index, word in enumerate(words, start=1)
        ]

    cues: list[dict[str, Any]] = []
    chunk: list[tuple[float, float, str, int, int]] = []

    def flush() -> None:
        if not chunk:
            return
        text = ""
        for _, _, word, _, _ in chunk:
            text = _append_word(text, word)
        start = chunk[0][3]
        end = max(start + 1, chunk[-1][4])
        cues.append({"cue_id": f"caption_{len(cues) + 1:03d}", "start_frame": start,
                     "end_frame": end, "text": text, "position": "LOWER"})
        chunk.clear()

    for item in mapped:
        proposed = _append_word(" ".join(word for _, _, word, _, _ in chunk), item[2])
        joins_previous_token = item[2].startswith(("'", "’"))
        if chunk and not joins_previous_token and (
                len(chunk) >= 4 or len(proposed) > 42 or item[0] - chunk[-1][1] > 0.45):
            flush()
        chunk.append(item)
        if item[2].endswith((".", "!", "?")):
            flush()
    flush()
    if uppercase:
        for cue in cues:
            cue["text"] = cue["text"].upper()
    return cues


def remove_owned_caption_overlay(timeline: Any) -> dict[str, Any]:
    """Remove one exact bridge-owned caption layer from a duplicate timeline."""
    matches: list[tuple[int, Any]] = []
    track_count = int(safe_call(timeline, "GetTrackCount", "video") or 0)
    for track in range(1, track_count + 1):
        for item in safe_call(timeline, "GetItemListInTrack", "video", track) or []:
            if safe_call(item, "GetName") == "ARPHE_VERTICAL_CAPTIONS_captions":
                matches.append((track, item))
    if len(matches) != 1:
        raise ValidationError("Sostituzione CAPTIONS richiede un solo layer bridge esistente")
    track, item = matches[0]
    if not safe_call(timeline, "DeleteClips", [item], False):
        raise ValidationError("Rimozione layer CAPTIONS esistente fallita")
    remaining = safe_call(timeline, "GetItemListInTrack", "video", track) or []
    if any(safe_call(entry, "GetName") == "ARPHE_VERTICAL_CAPTIONS_captions"
           for entry in remaining):
        raise ValidationError("Read-back rimozione layer CAPTIONS non corrispondente")
    if track == track_count and not remaining:
        if not safe_call(timeline, "DeleteTrack", "video", track):
            raise ValidationError("Rimozione traccia CAPTIONS vuota fallita")
    return {"removed": True, "track": track}


def create_caption_test(project: Any, config: Any, registry: Any, source_timeline: str,
                        target_name: str, transcript_file: str,
                        source_spans: list[dict[str, int]], caption_cutoff_frame: int,
                        caption_mode: str = "STANDARD", uppercase: bool = False,
                        font_scale: float = 1.0,
                        replace_existing_captions: bool = False) -> dict[str, Any]:
    """Duplicate an allowed timeline, apply generic lower captions, and never save automatically."""
    original = safe_call(project, "GetCurrentTimeline")
    duplicated = duplicate_timeline(project, config, registry, source_timeline, None, target_name)
    if not duplicated.get("ok"):
        return {**duplicated, "action": "create_caption_test"}
    timeline = safe_call(project, "GetCurrentTimeline")
    start, end = safe_call(timeline, "GetStartFrame"), safe_call(timeline, "GetEndFrame")
    if not isinstance(start, int) or not isinstance(end, int) or end <= start:
        raise ValidationError("Range timeline caption non leggibile")
    total_frames = end - start
    if isinstance(caption_cutoff_frame, bool) or not isinstance(caption_cutoff_frame, int) or not 0 <= caption_cutoff_frame <= total_frames:
        raise ValidationError("caption_cutoff_frame CAPTIONS non valido")
    try:
        replaced = remove_owned_caption_overlay(timeline) if replace_existing_captions else None
        fps = _parse_fps(timeline)
        spans = validate_source_spans(source_spans, fps)
        cues = caption_cues_from_segments(_load_segments(config, transcript_file), spans, fps,
                                          caption_mode=caption_mode, uppercase=uppercase)
        if not cues:
            raise ValidationError("Nessuna parola della trascrizione coincide con source_spans")
        action = {"action_id": "captions", "type": "CAPTIONS", "state": "APPROVED",
                  "phase": "POST_LOCK", "reason": "Sottotitoli da trascrizione con mappa esplicita",
                  "locked_edit_fingerprint": timeline_edit_fingerprint(timeline), "cues": cues,
                  "caption_cutoff_frame": caption_cutoff_frame,
                  "style": {"caption_mode": caption_mode, "uppercase": uppercase,
                            "font_scale": font_scale}}
        result = apply_caption_action(project, timeline, config, action, total_frames,
                                      required_timeline_prefix="ARPHE_")
    except Exception as error:
        restored = bool(original and safe_call(project, "SetCurrentTimeline", original))
        pool = safe_call(project, "GetMediaPool")
        removed = bool(pool and safe_call(pool, "DeleteTimelines", [timeline]))
        if not restored or not removed:
            raise RuntimeError("Caption fallite e rollback della copia non confermato") from error
        raise
    return {"ok": True, "action": "create_caption_test", "source_timeline": source_timeline,
            "created_timeline": safe_call(timeline, "GetName"), "source_preserved": True,
            "saved": False, "cta_created": False, "caption_cutoff_frame": caption_cutoff_frame,
            "source_spans": list(spans), "replaced_existing_captions": bool(replaced), **result}
