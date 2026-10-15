from __future__ import annotations

from fractions import Fraction
from typing import Any

from .config import CreativeConfig
from .feature_flags import require_capability
from .registry import Registry
from .resolve_connection import safe_call
from .safety import ValidationError
from .timeline_tools import duplicate_timeline, find_timeline


def _integer(value: object, label: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{label} non leggibile") from exc


def _frame_rate(value: object, fallback: Fraction) -> Fraction:
    try:
        parsed = Fraction(str(value))
        return parsed if parsed > 0 else fallback
    except (TypeError, ValueError, ZeroDivisionError):
        return fallback


def _source_frame_count(timeline_frames: int, source_fps: Fraction,
                        timeline_fps: Fraction) -> int:
    converted = Fraction(timeline_frames, 1) * source_fps / timeline_fps
    if converted.denominator != 1:
        raise ValidationError("Clip A4 con velocita' non compatibile: servono confini di frame esatti")
    return int(converted)


def _item_range(item: object) -> tuple[int, int]:
    """Return the bridge's half-open [start, end) timeline range."""
    return (_integer(safe_call(item, "GetStart"), "Inizio audio"),
            _integer(safe_call(item, "GetEnd"), "Fine audio"))


def _matching_items(timeline: object, audio_track: int, media: object,
                    record_start: int, record_end: int) -> list[object]:
    return [item for item in (safe_call(timeline, "GetItemListInTrack", "audio", audio_track) or [])
            if safe_call(item, "GetMediaPoolItem") is media
            and _item_range(item) == (record_start, record_end)]


def _one_matching_item(timeline: object, audio_track: int, media: object,
                       record_start: int, record_end: int) -> object:
    matches = _matching_items(timeline, audio_track, media, record_start, record_end)
    if len(matches) != 1:
        raise ValidationError("Read-back segmento audio non corrispondente")
    return matches[0]


def _append_audio(pool: object, timeline: object, media: object, source_start: int,
                  source_end_exclusive: int, record_start: int, record_end_exclusive: int,
                  audio_track: int, *, require_return_item: bool) -> object:
    if source_end_exclusive <= source_start or record_end_exclusive <= record_start:
        raise ValidationError("Segmento A4 senza durata")
    # Resolve's AppendToTimeline payload is inclusive, unlike every public
    # bridge range and every TimelineItem read-back used in this module.
    appended = safe_call(pool, "AppendToTimeline", [{
        "mediaPoolItem": media,
        "startFrame": source_start,
        "endFrame": source_end_exclusive - 1,
        "recordFrame": record_start,
        "mediaType": 2,
        "trackIndex": audio_track,
    }]) or []
    if require_return_item and len(appended) != 1:
        raise RuntimeError("Inserimento segmento voice-over fallito")
    return _one_matching_item(timeline, audio_track, media, record_start, record_end_exclusive)


def _delete_exact_items(timeline: object, audio_track: int, media: object,
                        ranges: list[tuple[int, int]]) -> None:
    owned: list[object] = []
    for record_start, record_end in ranges:
        owned.extend(_matching_items(timeline, audio_track, media, record_start, record_end))
    if owned:
        safe_call(timeline, "DeleteClips", owned, False)
    remaining = [item for record_start, record_end in ranges
                 for item in _matching_items(timeline, audio_track, media, record_start, record_end)]
    if remaining:
        raise ValidationError("Rollback segmento voice-over fallito")


def move_voiceover_tail_to_cta(project: Any, config: CreativeConfig, registry: Registry,
                               source_timeline: str, target_name: str, *, audio_track: int,
                               tail_start_frame: int, cta_start_frame: int) -> dict[str, Any]:
    """Copy one reviewed A-track voice-over tail to an explicit CTA frame.

    This PC_PERSONALE-only helper never changes the source timeline. It does
    not infer spoken words: callers provide the reviewed, half-open boundary.
    """
    if config.workstation_id != "PC_PERSONALE":
        raise ValidationError("Questa funzione e' abilitata solo su PC_PERSONALE")
    current = safe_call(project, "GetCurrentTimeline")
    require_capability("CAP_TIMELINE", config, None, project, current)
    if (not isinstance(audio_track, int) or isinstance(audio_track, bool) or audio_track < 1
            or not isinstance(tail_start_frame, int) or isinstance(tail_start_frame, bool)
            or not isinstance(cta_start_frame, int) or isinstance(cta_start_frame, bool)):
        raise ValidationError("Traccia e frame CTA devono essere interi positivi")
    source = find_timeline(project, source_timeline)
    if source is None:
        raise ValidationError("Timeline sorgente non trovata")
    audio_count = _integer(safe_call(source, "GetTrackCount", "audio"), "Numero tracce audio")
    if audio_track > audio_count:
        raise ValidationError("Traccia audio richiesta non presente")
    candidates = [item for item in (safe_call(source, "GetItemListInTrack", "audio", audio_track) or [])
                  if _item_range(item)[0] < tail_start_frame < _item_range(item)[1]]
    if len(candidates) != 1:
        raise ValidationError("Il frame di inizio coda deve cadere in una sola clip A4")
    if cta_start_frame <= tail_start_frame:
        raise ValidationError("La CTA deve iniziare dopo la coda voce")

    duplicated = duplicate_timeline(project, config, registry, source_timeline, None, target_name)
    if not duplicated.get("ok"):
        return {**duplicated, "action": "move_voiceover_tail_to_cta"}
    timeline = safe_call(project, "GetCurrentTimeline")
    if timeline is None:
        raise RuntimeError("Timeline duplicata non selezionata")
    original = next((item for item in (safe_call(timeline, "GetItemListInTrack", "audio", audio_track) or [])
                     if _item_range(item)[0] < tail_start_frame < _item_range(item)[1]), None)
    if original is None:
        raise ValidationError("La clip A4 non e' presente nella timeline duplicata")

    record_start, record_end = _item_range(original)
    duration = record_end - record_start
    media = safe_call(original, "GetMediaPoolItem")
    if media is None:
        raise ValidationError("Media sorgente A4 non disponibile")
    timeline_fps = _frame_rate(safe_call(timeline, "GetSetting", "timelineFrameRate"), Fraction(30, 1))
    source_fps = _frame_rate(safe_call(media, "GetClipProperty", "FPS"), timeline_fps)
    source_start = _integer(safe_call(original, "GetSourceStartFrame"), "Inizio sorgente audio")
    source_end = source_start + _source_frame_count(duration, source_fps, timeline_fps)
    source_tail_start = source_start + _source_frame_count(
        tail_start_frame - record_start, source_fps, timeline_fps)
    if not source_start < source_tail_start < source_end:
        raise ValidationError("Frame coda fuori dal segmento audio sorgente")
    prefix_range = (record_start, tail_start_frame)
    tail_range = (cta_start_frame, cta_start_frame + (record_end - tail_start_frame))
    pool = safe_call(project, "GetMediaPool")
    if pool is None:
        raise RuntimeError("Media pool non disponibile")

    # Do not create an ambiguous duplicate over another A4 segment.
    for start, end in (prefix_range, tail_range):
        existing = _matching_items(timeline, audio_track, media, start, end)
        if existing and existing != [original]:
            raise ValidationError("La destinazione CTA contiene gia' un segmento A4 identico")

    original_range = (record_start, record_end)
    try:
        safe_call(timeline, "DeleteClips", [original], False)
        original_removed = not _matching_items(timeline, audio_track, media, *original_range)
        if not original_removed:
            raise RuntimeError("Rimozione della clip A4 dalla copia fallita")
        prefix = _append_audio(pool, timeline, media, source_start, source_tail_start,
                               *prefix_range, audio_track, require_return_item=True)
        tail = _append_audio(pool, timeline, media, source_tail_start, source_end,
                             *tail_range, audio_track, require_return_item=True)
    except Exception as exc:
        _delete_exact_items(timeline, audio_track, media, [prefix_range, tail_range])
        if not _matching_items(timeline, audio_track, media, *original_range):
            _append_audio(pool, timeline, media, source_start, source_end, *original_range,
                          audio_track, require_return_item=False)
        _one_matching_item(timeline, audio_track, media, *original_range)
        raise exc
    return {
        "ok": True,
        "action": "move_voiceover_tail_to_cta",
        "source_timeline": source_timeline,
        "created_timeline": safe_call(timeline, "GetName"),
        "audio_track": audio_track,
        "tail_start_frame": tail_start_frame,
        "cta_start_frame": cta_start_frame,
        "readback_record_starts": [safe_call(prefix, "GetStart"), safe_call(tail, "GetStart")],
        "readback_record_ends": [safe_call(prefix, "GetEnd"), safe_call(tail, "GetEnd")],
        "readback_source_starts": [safe_call(prefix, "GetSourceStartFrame"), safe_call(tail, "GetSourceStartFrame")],
        "readback_source_ends": [source_tail_start, source_end],
        "source_preserved": True,
        "saved": False,
    }
