from __future__ import annotations

from typing import Any

from .resolve_connection import safe_call
from .safety import ValidationError
from .timeline_tools import duplicate_timeline


MONOCHROME_CDL = {"NodeIndex": "1", "Slope": "1.000000 1.000000 1.000000", "Offset": "0.000000 0.000000 0.000000", "Power": "1.000000 1.000000 1.000000", "Saturation": "0.000000"}


def build_monochrome_segments(clip_start: int, clip_end: int, source_start: int, window_start: int, window_end: int) -> list[dict[str, int]]:
    if not clip_start <= window_start < window_end <= clip_end:
        raise ValueError("Finestra monocromatica fuori dalla clip")
    cuts = (clip_start, window_start, window_end, clip_end)
    return [{"source_start": source_start + cuts[index] - clip_start, "source_end": source_start + cuts[index + 1] - clip_start, "record_start": cuts[index], "record_end": cuts[index + 1]} for index in range(3) if cuts[index] != cuts[index + 1]]


def _matching(timeline: Any, track: int, media: Any, start: int, end: int) -> list[Any]:
    media_id = str(safe_call(media, "GetMediaId") or "")
    return [item for item in (safe_call(timeline, "GetItemListInTrack", "video", track) or []) if str(safe_call(safe_call(item, "GetMediaPoolItem"), "GetMediaId") or "") == media_id and safe_call(item, "GetStart") == start and safe_call(item, "GetEnd") == end]


def _append(pool: Any, timeline: Any, media: Any, track: int, segment: dict[str, int]) -> Any:
    inserted = safe_call(pool, "AppendToTimeline", [{"mediaPoolItem": media, "startFrame": segment["source_start"], "endFrame": segment["source_end"], "recordFrame": segment["record_start"], "mediaType": 1, "trackIndex": track}]) or []
    matches = _matching(timeline, track, media, segment["record_start"], segment["record_end"])
    if len(matches) != 1:
        observed = [{"start": safe_call(item, "GetStart"), "end": safe_call(item, "GetEnd")} for item in (safe_call(timeline, "GetItemListInTrack", "video", track) or [])]
        raise RuntimeError(f"Inserimento segmento video non verificato: expected={segment['record_start']}-{segment['record_end']}, observed={observed}")
    return matches[0]


def apply_monochrome_segment(project: Any, config: Any, registry: Any, source_timeline: str, target_name: str, window_start: int, window_end: int, video_track: int = 1) -> dict[str, Any]:
    duplicated = duplicate_timeline(project, config, registry, source_timeline, None, target_name)
    if not duplicated.get("ok"):
        return {**duplicated, "action": "apply_monochrome_segment"}
    timeline = safe_call(project, "GetCurrentTimeline")
    candidates = [item for item in (safe_call(timeline, "GetItemListInTrack", "video", video_track) or []) if int(safe_call(item, "GetStart") or -1) <= window_start and int(safe_call(item, "GetEnd") or -1) >= window_end]
    if len(candidates) != 1:
        raise ValidationError("La finestra deve ricadere in una sola clip video")
    original = candidates[0]
    clip_start, clip_end = int(safe_call(original, "GetStart")), int(safe_call(original, "GetEnd"))
    source_start = int(safe_call(original, "GetSourceStartFrame"))
    media, pool = safe_call(original, "GetMediaPoolItem"), safe_call(project, "GetMediaPool")
    if media is None or pool is None:
        raise ValidationError("Sorgente video o media pool non disponibile")
    segments = build_monochrome_segments(clip_start, clip_end, source_start, window_start, window_end)
    if safe_call(timeline, "DeleteClips", [original], False) is not True:
        raise RuntimeError("Rimozione clip video dalla copia fallita")
    inserted: list[Any] = []
    try:
        for segment in segments:
            inserted.append(_append(pool, timeline, media, video_track, segment))
        middle = next(item for item, segment in zip(inserted, segments) if segment["record_start"] == window_start)
        if safe_call(middle, "SetCDL", dict(MONOCHROME_CDL)) is not True:
            raise RuntimeError("Applicazione CDL monocromatica fallita")
    except Exception:
        if inserted:
            safe_call(timeline, "DeleteClips", inserted, False)
        restored = _append(pool, timeline, media, video_track, {"source_start": source_start, "source_end": source_start + (clip_end - clip_start), "record_start": clip_start, "record_end": clip_end})
        if restored is None:
            raise RuntimeError("Rollback clip video fallito")
        raise
    return {"ok": True, "action": "apply_monochrome_segment", "created_timeline": safe_call(timeline, "GetName"), "window_start": window_start, "window_end": window_end, "video_track": video_track, "segments": [{"start": safe_call(item, "GetStart"), "end": safe_call(item, "GetEnd")} for item in inserted], "source_preserved": True}
