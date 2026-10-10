from __future__ import annotations
from typing import Any
from .safety import ValidationError


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
    name = f"__ARPHE_VERTICAL_{plan_id.upper()}"
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
    record = 0
    for start, end in keep:
        for media_type in (1, 2):
            appended = _resolve_call(pool, "AppendToTimeline", [{
                "mediaPoolItem": media, "startFrame": start, "endFrame": end,
                "recordFrame": record, "mediaType": media_type,
            }])
            if not appended:
                raise ValidationError(f"Append CUT provvisorio fallito: {start}-{end}")
        record += end - start
    _verify_provisional(provisional, len(keep), expected_frames)
    return provisional
