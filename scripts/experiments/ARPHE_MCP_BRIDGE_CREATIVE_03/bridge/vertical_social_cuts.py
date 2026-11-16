from __future__ import annotations
from typing import Any
import hashlib
import json
from .safety import ValidationError
from .vertical_social_apply import provisional_timeline_name


def preserved_timeline_fingerprint(timeline: object) -> str:
    """Bind timing, media identities, inspector settings and local color version.

    No paths or settings are returned to the caller. DuplicateTimeline carries
    the native effects, audio processing and stabilization; this signature
    detects stale sources and verifies the copy without rebuilding media.
    """
    from .vertical_social_captions import timeline_edit_fingerprint
    tracks = []
    for kind in ('video', 'audio'):
        for index in range(1, int(_resolve_call(timeline, 'GetTrackCount', kind) or 0) + 1):
            items = []
            for item in _resolve_call(timeline, 'GetItemListInTrack', kind, index) or []:
                properties = _resolve_call(item, 'GetProperty')
                if not isinstance(properties, dict):
                    raise ValidationError('Proprieta clip non verificabili per copia motion')
                version = getattr(item, 'GetCurrentVersion', None)
                offsets = [_resolve_call(item, 'GetLeftOffset'), _resolve_call(item, 'GetRightOffset')]
                if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in offsets):
                    raise ValidationError('Offset sorgente clip non verificabili per copia motion')
                items.append({'properties': properties,
                              'source_offsets': offsets,
                              'color_version': version() if callable(version) and kind == 'video' else None})
            tracks.append({'kind': kind, 'index': index, 'items': items})
    payload = {'edit': timeline_edit_fingerprint(timeline), 'tracks': tracks}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def duplicate_preserved_timeline(project: object, source: object, plan: dict[str, Any], config: object) -> object:
    target = plan.get('target', {})
    if (_resolve_call(source, 'GetUniqueId') != target.get('timeline_identity')
            or preserved_timeline_fingerprint(source) != target.get('source_state_fingerprint')):
        raise ValidationError('Sorgente motion cambiata dopo approvazione')
    duration = int(_resolve_call(source, 'GetEndFrame')) - int(_resolve_call(source, 'GetStartFrame'))
    if duration != target.get('total_frames'):
        raise ValidationError('Durata sorgente motion diversa dal piano')
    name = provisional_timeline_name(plan['plan_id'])
    clone = _existing_timeline(project, name)
    from .timeline_tools import preserve_fusion_compositions
    if clone is not None:
        # Motion can have added a Fusion composition, but must retain all media,
        # timing, inspector settings and color versions on replay.
        if preserved_timeline_fingerprint(clone) != target['source_state_fingerprint']:
            raise ValidationError('Copia motion esistente non corrispondente')
        preserve_fusion_compositions(source, clone, config, allow_added_motion=True)
        return clone
    clone = _resolve_call(source, 'DuplicateTimeline', name)
    if clone is None or _resolve_call(clone, 'GetName') != name:
        raise ValidationError('Duplicazione completa per motion fallita')
    preserve_fusion_compositions(source, clone, config)
    if preserved_timeline_fingerprint(clone) != target['source_state_fingerprint']:
        raise ValidationError('Read-back copia motion non corrispondente')
    return clone


def _resolve_call(target: object, method: str, *args: object) -> Any:
    function = getattr(target, method, None)
    if not callable(function):
        raise ValidationError(f"API Vertical Social non supportata: {method}")
    try:
        return function(*args)
    except Exception as exc:
        raise ValidationError(f"Resolve {method} fallita: {exc}") from exc

def approved_cut_ranges(plan: dict[str, Any], total_frames: int) -> tuple[tuple[int, int], ...]:
    if total_frames <= 0:
        raise ValidationError("durata timeline non valida")
    ranges: list[tuple[int, int]] = []
    for action in plan.get("actions", []):
        if action.get("type") != "CUT" or action.get("state") != "APPROVED":
            continue
        raw = action.get("range")
        if not isinstance(raw, dict):
            raise ValidationError("range CUT mancante")
        start, end = raw.get("start_frame"), raw.get("end_frame")
        if not isinstance(start, int) or not isinstance(end, int) or not 0 <= start < end <= total_frames:
            raise ValidationError("range CUT non valida")
        if not str(action.get("reason", "")).strip():
            raise ValidationError("reason CUT mancante")
        ranges.append((start, end))
    ordered = tuple(sorted(ranges))
    for previous, current in zip(ordered, ordered[1:]):
        if current[0] < previous[1]:
            raise ValidationError("CUT overlap")
    return ordered


def _keep_ranges(total_frames: int, cuts: tuple[tuple[int, int], ...]) -> tuple[tuple[int, int], ...]:
    cursor = 0
    keep: list[tuple[int, int]] = []
    for start, end in cuts:
        if cursor < start:
            keep.append((cursor, start))
        cursor = end
    if cursor < total_frames:
        keep.append((cursor, total_frames))
    if not keep:
        raise ValidationError("I CUT approvati rimuovono l'intera timeline")
    return tuple(keep)


def _single_synced_av_source(timeline: object) -> object:
    for kind in ("video", "audio"):
        if int(_resolve_call(timeline, "GetTrackCount", kind) or 0) != 1:
            raise ValidationError("Timeline sorgente deve avere una sola traccia video e audio")
    video = _resolve_call(timeline, "GetItemListInTrack", "video", 1) or []
    audio = _resolve_call(timeline, "GetItemListInTrack", "audio", 1) or []
    if len(video) != 1 or len(audio) != 1:
        raise ValidationError("Timeline sorgente deve contenere una sola clip A/V")
    if (_resolve_call(video[0], "GetStart") != _resolve_call(audio[0], "GetStart")
            or _resolve_call(video[0], "GetDuration") != _resolve_call(audio[0], "GetDuration")):
        raise ValidationError("Clip A/V sorgenti non allineate")
    media = _resolve_call(video[0], "GetMediaPoolItem")
    audio_media = _resolve_call(audio[0], "GetMediaPoolItem")
    identity = getattr(media, "GetUniqueId", None)
    audio_identity = getattr(audio_media, "GetUniqueId", None)
    same_source = (media is audio_media or (callable(identity) and callable(audio_identity)
                   and identity() and identity() == audio_identity()))
    if media is None or audio_media is None or not same_source:
        raise ValidationError("Clip A/V non collegate alla stessa sorgente")
    return media


def _verify_provisional(timeline: object, expected_segments: int, expected_frames: int) -> None:
    for kind in ("video", "audio"):
        if int(_resolve_call(timeline, "GetTrackCount", kind) or 0) != 1:
            raise ValidationError("Timeline provvisoria con tracce A/V non valide")
        items = _resolve_call(timeline, "GetItemListInTrack", kind, 1) or []
        if (len(items) != expected_segments
                or sum(int(_resolve_call(item, "GetDuration")) for item in items) != expected_frames):
            raise ValidationError("Read-back timeline provvisoria non corrisponde ai CUT approvati")


def _existing_timeline(project: object, name: str) -> object | None:
    count = getattr(project, "GetTimelineCount", None)
    get_at = getattr(project, "GetTimelineByIndex", None)
    if not callable(count) or not callable(get_at):
        return None
    for index in range(1, int(_resolve_call(project, "GetTimelineCount") or 0) + 1):
        candidate = _resolve_call(project, "GetTimelineByIndex", index)
        if candidate is not None and _resolve_call(candidate, "GetName") == name:
            return candidate
    return None


def _append_exact_range(pool: object, timeline: object, media: object,
                        start: int, end: int, record: int, media_type: int) -> object:
    """Append an exact half-open source range, adapting to Resolve's one-short edge case."""
    expected = end - start

    def append(selected_end: int) -> object:
        result = _resolve_call(pool, "AppendToTimeline", [{
            "mediaPoolItem": media, "startFrame": start, "endFrame": selected_end,
            "recordFrame": record, "mediaType": media_type,
        }])
        if not isinstance(result, (list, tuple)) or len(result) != 1:
            raise ValidationError(f"Append CUT provvisorio non univoco: {start}-{selected_end}")
        return result[0]

    item = append(end)
    duration = int(_resolve_call(item, "GetDuration") or 0)
    if duration == expected:
        return item
    if duration != expected - 1:
        raise ValidationError(f"Durata Append CUT inattesa: {duration} invece di {expected}")
    if not _resolve_call(timeline, "DeleteClips", [item], False):
        raise ValidationError("Rollback Append CUT corto fallito")
    corrected = append(end + 1)
    corrected_duration = int(_resolve_call(corrected, "GetDuration") or 0)
    right_offset = _resolve_call(corrected, "GetRightOffset")
    if corrected_duration != expected or (isinstance(right_offset, int) and right_offset < 0):
        raise ValidationError("Correzione Append CUT di un fotogramma non verificata")
    return corrected


def create_provisional_cut_timeline(project: object, source_timeline: object, plan: dict[str, Any],
                                    *, total_frames: int) -> object:
    """Build a non-destructive, named provisional timeline from approved Vertical Social CUTs."""
    plan_id = str(plan.get("plan_id", "")).strip()
    if not plan_id:
        raise ValidationError("plan_id Vertical Social mancante")
    cuts = approved_cut_ranges(plan, total_frames)
    keep = _keep_ranges(total_frames, cuts)
    media = _single_synced_av_source(source_timeline)
    pool = _resolve_call(project, "GetMediaPool")
    name = provisional_timeline_name(plan_id)
    expected_frames = sum(end - start for start, end in keep)
    provisional = _existing_timeline(project, name)
    if provisional is not None:
        _verify_provisional(provisional, len(keep), expected_frames)
        if not _resolve_call(project, "SetCurrentTimeline", provisional):
            raise ValidationError("Impossibile riselezionare la timeline provvisoria")
        return provisional
    provisional = _resolve_call(pool, "CreateEmptyTimeline", name)
    if provisional is None or _resolve_call(provisional, "GetName") != name:
        raise ValidationError("Creazione timeline provvisoria Vertical Social fallita")
    if not _resolve_call(project, "SetCurrentTimeline", provisional):
        raise ValidationError("Impossibile selezionare la timeline provvisoria")
    record = int(_resolve_call(provisional, "GetStartFrame") or 0)
    for start, end in keep:
        for media_type in (1, 2):
            _append_exact_range(pool, provisional, media, start, end, record, media_type)
        record += end - start
    _verify_provisional(provisional, len(keep), expected_frames)
    return provisional
