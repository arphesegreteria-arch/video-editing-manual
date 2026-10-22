"""Exact transcript-to-caption mapping for the approved advbeppe test timeline."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .resolve_connection import safe_call
from .safety import ValidationError
from .timeline_tools import duplicate_timeline
from .vertical_social_captions import apply_caption_action, timeline_edit_fingerprint


FPS = 30
SOURCE_SPANS = (
    (271 / FPS, 580 / FPS, 0),
    (819 / FPS, 1120 / FPS, 309),
    (1240 / FPS, 1275 / FPS, 610),
)


def _caption_words(segments: list[dict[str, Any]]) -> list[tuple[float, float, str, int]]:
    """Retain only words that occur inside an edited source span."""
    mapped: list[tuple[float, float, str, int]] = []
    for segment in segments:
        for word in segment.get("words", []):
            if not isinstance(word, dict):
                continue
            try:
                start, end = float(word["start"]), float(word["end"])
            except (KeyError, TypeError, ValueError):
                continue
            text = str(word.get("word", "")).strip()
            if not text or end <= start:
                continue
            for source_start, source_end, timeline_start in SOURCE_SPANS:
                if source_start <= start and end <= source_end:
                    mapped.append((start, end, text, timeline_start + round((start - source_start) * FPS)))
                    break
    return mapped


def _append_word(text: str, word: str) -> str:
    if word.startswith(("'", "’")):
        return f"{text}{word}"
    return f"{text} {word}".strip()


def caption_cues_from_segments(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build short, non-overlapping lower-third cues; removed source gaps stay empty."""
    words = _caption_words(segments)
    cues: list[dict[str, Any]] = []
    chunk: list[tuple[float, float, str, int]] = []

    def flush() -> None:
        if not chunk:
            return
        text = ""
        for _, _, word, _ in chunk:
            text = _append_word(text, word)
        start = chunk[0][3]
        end_source = chunk[-1][1]
        # Derive the final frame from the span containing the last word.
        end = start + 1
        for span_start, span_end, timeline_start in SOURCE_SPANS:
            if span_start <= end_source <= span_end:
                end = timeline_start + round((end_source - span_start) * FPS)
                break
        cues.append({"cue_id": f"adv_{len(cues) + 1:03d}", "start_frame": start,
                     "end_frame": max(start + 1, end), "text": text, "position": "LOWER"})
        chunk.clear()

    for item in words:
        next_text = _append_word(" ".join(word for _, _, word, _ in chunk), item[2])
        if chunk and (len(chunk) >= 4 or len(next_text) > 42 or item[0] - chunk[-1][1] > 0.45):
            flush()
        chunk.append(item)
        if item[2].endswith((".", "!", "?")):
            flush()
    flush()
    return cues


def caption_action_for_segments(segments: list[dict[str, Any]], *, locked_edit_fingerprint: str,
                                total_frames: int) -> dict[str, Any]:
    cues = caption_cues_from_segments(segments)
    if not cues:
        raise ValidationError("Nessuna parola della trascrizione coincide con la timeline montata")
    return {
        "action_id": "advbeppe_captions",
        "type": "CAPTIONS",
        "state": "APPROVED",
        "phase": "POST_LOCK",
        "reason": "Sottotitoli da ARPHE_TRANSCRIPT_V1 su timeline di prova",
        "locked_edit_fingerprint": locked_edit_fingerprint,
        "cues": cues,
        # This edit has no CTA. The contract still requires an explicit cutoff;
        # the exclusive end of the timeline prevents a caption beyond picture.
        "caption_cutoff_frame": total_frames,
    }


def _segments_from_longform_transcript(config: Any) -> list[dict[str, Any]]:
    transcript = (Path(config.transcript_root) / "video in 3.ARPHE_TRANSCRIPT_V1.json").resolve()
    root = Path(config.transcript_root).resolve()
    if not transcript.is_file() or not transcript.is_relative_to(root):
        raise ValidationError("ARPHE_TRANSCRIPT_V1 non disponibile nella cartella autorizzata")
    data = json.loads(transcript.read_text(encoding="utf-8"))
    segments = data.get("segments") if isinstance(data, dict) else None
    if not isinstance(segments, list):
        raise ValidationError("Formato ARPHE_TRANSCRIPT_V1 non valido")
    return [segment for segment in segments if isinstance(segment, dict)]


def create_advbeppe_caption_test(project: Any, config: Any, registry: Any, source_timeline: str,
                                 target_name: str) -> dict[str, Any]:
    """Create a caption-only test copy for the approved advbeppe seam timeline."""
    if source_timeline != "ARPHE_ADV_SEAM_TEST_20261022":
        raise ValidationError("Caption consentite solo sulla copia audio ARPHE_ADV_SEAM_TEST_20261022")
    original = safe_call(project, "GetCurrentTimeline")
    duplicated = duplicate_timeline(project, config, registry, source_timeline, None, target_name)
    if not duplicated.get("ok"):
        return {**duplicated, "action": "create_advbeppe_caption_test"}
    timeline = safe_call(project, "GetCurrentTimeline")
    start = safe_call(timeline, "GetStartFrame")
    end = safe_call(timeline, "GetEndFrame")
    if not isinstance(start, int) or not isinstance(end, int) or end <= start:
        raise ValidationError("Range timeline caption non leggibile")
    try:
        action = caption_action_for_segments(
            _segments_from_longform_transcript(config),
            locked_edit_fingerprint=timeline_edit_fingerprint(timeline), total_frames=end - start,
        )
        result = apply_caption_action(
            project, timeline, config, action, end - start,
            required_timeline_prefix="ARPHE_ADV_CAPTIONS_",
        )
    except Exception as error:
        restored = bool(original and safe_call(project, "SetCurrentTimeline", original))
        pool = safe_call(project, "GetMediaPool")
        removed = bool(pool and safe_call(pool, "DeleteTimelines", [timeline]))
        if not restored or not removed:
            raise RuntimeError("Caption fallite e rollback della copia non confermato") from error
        raise
    return {
        "ok": True,
        "action": "create_advbeppe_caption_test",
        "source_timeline": source_timeline,
        "created_timeline": safe_call(timeline, "GetName"),
        "source_preserved": True,
        "saved": False,
        "cta_created": False,
        "caption_cutoff_frame": end - start,
        **result,
    }
