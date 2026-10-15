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


def _source_end(item: object, source_start: int, timeline_frames: int,
                source_fps: Fraction, timeline_fps: Fraction) -> int:
    explicit = safe_call(item, "GetSourceEndFrame")
    if explicit is not None:
        try:
            end = int(explicit)
            if end >= source_start:
                return end
        except (TypeError, ValueError):
            pass
    source_frames = max(1, round(Fraction(timeline_frames, 1) * source_fps / timeline_fps))
    return source_start + source_frames - 1


def _append_audio(pool: object, media: object, source_start: int, source_end: int,
                  record_start: int, audio_track: int) -> object:
    appended = safe_call(pool, "AppendToTimeline", [{
        "mediaPoolItem": media,
        "startFrame": source_start,
        "endFrame": source_end,
        "recordFrame": record_start,
        "mediaType": 2,
        "trackIndex": audio_track,
    }]) or []
    if len(appended) != 1:
        raise RuntimeError("Inserimento segmento voice-over fallito")
    return appended[0]


def _matching_item(timeline: object, audio_track: int, record_start: int,
                   record_end: int) -> object:
    items = safe_call(timeline, "GetItemListInTrack", "audio", audio_track) or []
    matches = [item for item in items
               if _integer(safe_call(item, "GetStart"), "Inizio audio") == record_start
               and _integer(safe_call(item, "GetEnd"), "Fine audio") == record_end]
    if len(matches) != 1:
        raise ValidationError("Read-back segmento audio non corrispondente")
    return matches[0]


def move_voiceover_tail_to_cta(project: Any, config: CreativeConfig, registry: Registry,
                               source_timeline: str, target_name: str, *, audio_track: int,
                               tail_start_frame: int, cta_start_frame: int) -> dict[str, Any]:
    """Copy one A-track voice-over, placing its tail at an explicit CTA frame.

    This is intentionally narrow: it never edits the source timeline and it does
    not infer words or boundaries from audio.  The caller supplies the reviewed
    frame at which the CTA sentence begins.
    """
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
                  if _integer(safe_call(item, "GetStart"), "Inizio audio")
                  < tail_start_frame <= _integer(safe_call(item, "GetEnd"), "Fine audio")]
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
    original_candidates = safe_call(timeline, "GetItemListInTrack", "audio", audio_track) or []
    original = next((item for item in original_candidates
                     if _integer(safe_call(item, "GetStart"), "Inizio audio")
                     < tail_start_frame <= _integer(safe_call(item, "GetEnd"), "Fine audio")), None)
    if original is None:
        raise ValidationError("La clip A4 non è presente nella timeline duplicata")

    record_start = _integer(safe_call(original, "GetStart"), "Inizio audio")
    record_end = _integer(safe_call(original, "GetEnd"), "Fine audio")
    duration = _integer(safe_call(original, "GetDuration"), "Durata audio")
    media = safe_call(original, "GetMediaPoolItem")
    if media is None:
        raise ValidationError("Media sorgente A4 non disponibile")
    timeline_fps = _frame_rate(safe_call(timeline, "GetSetting", "timelineFrameRate"), Fraction(30, 1))
    source_fps = _frame_rate(safe_call(media, "GetClipProperty", "FPS"), timeline_fps)
    source_start = _integer(safe_call(original, "GetSourceStartFrame"), "Inizio sorgente audio")
    source_end = _source_end(original, source_start, duration, source_fps, timeline_fps)
    source_tail_start = source_start + round(
        Fraction(tail_start_frame - record_start, 1) * source_fps / timeline_fps)
    if not source_start < source_tail_start <= source_end:
        raise ValidationError("Frame coda fuori dal segmento audio sorgente")
    prefix_end = tail_start_frame - 1
    tail_duration = record_end - tail_start_frame + 1
    tail_end = cta_start_frame + tail_duration - 1
    pool = safe_call(project, "GetMediaPool")
    if pool is None:
        raise RuntimeError("Media pool non disponibile")

    inserted: list[object] = []
    deleted = False
    try:
        if not safe_call(timeline, "DeleteClips", [original], False):
            raise RuntimeError("Rimozione della clip A4 dalla copia fallita")
        deleted = True
        inserted.append(_append_audio(pool, media, source_start, source_tail_start - 1,
                                      record_start, audio_track))
        inserted.append(_append_audio(pool, media, source_tail_start, source_end,
                                      cta_start_frame, audio_track))
        prefix = _matching_item(timeline, audio_track, record_start, prefix_end)
        tail = _matching_item(timeline, audio_track, cta_start_frame, tail_end)
    except Exception as exc:
        if inserted:
            safe_call(timeline, "DeleteClips", inserted, False)
        if deleted:
            restored = _append_audio(pool, media, source_start, source_end, record_start, audio_track)
            _matching_item(timeline, audio_track, record_start, record_end)
            if restored is None:
                raise ValidationError("Rollback A4 fallito") from exc
        raise
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
        "readback_source_ends": [_source_end(prefix, _integer(safe_call(prefix, "GetSourceStartFrame"), "Inizio sorgente audio"),
                                                _integer(safe_call(prefix, "GetDuration"), "Durata audio"), source_fps, timeline_fps),
                                  _source_end(tail, _integer(safe_call(tail, "GetSourceStartFrame"), "Inizio sorgente audio"),
                                              _integer(safe_call(tail, "GetDuration"), "Durata audio"), source_fps, timeline_fps)],
        "source_preserved": True,
        "saved": False,
    }
