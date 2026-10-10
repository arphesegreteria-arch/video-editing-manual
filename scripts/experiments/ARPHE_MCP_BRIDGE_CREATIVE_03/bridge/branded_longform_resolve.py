from __future__ import annotations

import hashlib
import json
from typing import Any

from .branded_longform_jobs import BrandedLongformJob
from .resolve_connection import safe_call
from .safety import ValidationError


def _timelines(project: object) -> list[object]:
    return [item for index in range(1, int(safe_call(project, "GetTimelineCount") or 0) + 1)
            if (item := safe_call(project, "GetTimelineByIndex", index)) is not None]


def _find(project: object, name: str) -> object | None:
    matches = [item for item in _timelines(project) if str(safe_call(item, "GetName") or "") == name]
    if len(matches) > 1:
        raise ValidationError(f"Più timeline con nome {name}")
    return matches[0] if matches else None


def timeline_structure_fingerprint(timeline: object) -> str:
    tracks: list[dict[str, Any]] = []
    for kind in ("video", "audio"):
        for index in range(1, int(safe_call(timeline, "GetTrackCount", kind) or 0) + 1):
            items = []
            for item in safe_call(timeline, "GetItemListInTrack", kind, index) or []:
                pool_item = safe_call(item, "GetMediaPoolItem")
                items.append({
                    "name": str(safe_call(item, "GetName") or ""),
                    "start": safe_call(item, "GetStart"),
                    "end": safe_call(item, "GetEnd"),
                    "duration": safe_call(item, "GetDuration"),
                    "media": str(safe_call(pool_item, "GetName") or "") if pool_item else "",
                })
            tracks.append({"kind": kind, "index": index, "items": items})
    payload = {"name": str(safe_call(timeline, "GetName") or ""), "tracks": tracks}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def find_owned_timeline(project: object, job: BrandedLongformJob, name: str) -> object:
    _check_project(project, job)
    if name not in {job.original_timeline, job.cleanup_timeline, job.editorial_timeline}:
        raise ValidationError("Timeline non posseduta dal job")
    result = _find(project, name)
    if result is None:
        raise ValidationError(f"Timeline job non trovata: {name}")
    return result


def _check_project(project: object, job: BrandedLongformJob) -> None:
    if str(safe_call(project, "GetName") or "") != job.project_name:
        raise ValidationError("Progetto corrente diverso dal job branded longform")
    if job.original_timeline_fingerprint:
        original = _find(project, job.original_timeline)
        if original is None or timeline_structure_fingerprint(original) != job.original_timeline_fingerprint:
            raise ValidationError("Timeline originale modificata dopo la creazione del job")


def _duplicate(project: object, job: BrandedLongformJob, source_name: str, target_name: str) -> dict[str, Any]:
    _check_project(project, job)
    original = safe_call(project, "GetCurrentTimeline")
    if original is None:
        raise ValidationError("Serve una timeline corrente")
    source = _find(project, source_name)
    if source is None:
        raise ValidationError(f"Timeline sorgente non trovata: {source_name}")
    existing = _find(project, target_name)
    if existing is not None:
        return {"ok": True, "created_timeline": target_name, "existing": True, "returned_to_original": True}
    try:
        if not safe_call(project, "SetCurrentTimeline", source):
            raise ValidationError("Selezione timeline sorgente fallita")
        duplicated = safe_call(source, "DuplicateTimeline", target_name)
        if duplicated is None or str(safe_call(duplicated, "GetName") or "") != target_name:
            raise ValidationError("Duplicazione timeline fallita")
        return {"ok": True, "created_timeline": target_name, "existing": False, "returned_to_original": True}
    finally:
        if not safe_call(project, "SetCurrentTimeline", original):
            raise ValidationError("Ripristino timeline originale fallito")


def _keep_ranges(total: int, cuts: tuple[tuple[int, int], ...]) -> tuple[tuple[int, int], ...]:
    cursor, keep = 0, []
    for start, end in cuts:
        if start < cursor or end <= start or end > total:
            raise ValidationError("Range cleanup non validi o sovrapposti")
        if start > cursor:
            keep.append((cursor, start))
        cursor = end
    if cursor < total:
        keep.append((cursor, total))
    if not keep:
        raise ValidationError("Cleanup rimuoverebbe l'intera sorgente")
    return tuple(keep)


def _create_cut_cleanup(project: object, job: BrandedLongformJob,
                        cleanup_cuts: tuple[tuple[int, int], ...]) -> dict[str, Any]:
    _check_project(project, job)
    original = safe_call(project, "GetCurrentTimeline")
    source = _find(project, job.original_timeline)
    if source is None or original is None:
        raise ValidationError("Timeline originale non disponibile per cleanup")
    if _find(project, job.cleanup_timeline) is not None:
        return {"ok": True, "created_timeline": job.cleanup_timeline, "existing": True,
                "returned_to_original": True, "cleanup_cuts": len(cleanup_cuts)}
    video = safe_call(source, "GetItemListInTrack", "video", 1) or []
    audio = safe_call(source, "GetItemListInTrack", "audio", 1) or []
    if (int(safe_call(source, "GetTrackCount", "video") or 0) != 1
            or int(safe_call(source, "GetTrackCount", "audio") or 0) != 1
            or len(video) != 1 or len(audio) != 1):
        raise ValidationError("Cleanup automatico richiede una sorgente A/V singola; usa review per multicam o timeline complessa")
    media_video, media_audio = safe_call(video[0], "GetMediaPoolItem"), safe_call(audio[0], "GetMediaPoolItem")
    video_id, audio_id = safe_call(media_video, "GetUniqueId"), safe_call(media_audio, "GetUniqueId")
    same_media = media_video is media_audio or (video_id and audio_id and video_id == audio_id)
    if media_video is None or media_audio is None or not same_media:
        raise ValidationError("Cleanup automatico richiede video e audio dalla stessa sorgente")
    total = int(safe_call(video[0], "GetDuration") or 0)
    keep = _keep_ranges(total, cleanup_cuts)
    source_offset = int(safe_call(video[0], "GetLeftOffset") or 0)
    pool = safe_call(project, "GetMediaPool")
    cleanup = None
    try:
        cleanup = safe_call(pool, "CreateEmptyTimeline", job.cleanup_timeline) if pool else None
        if cleanup is None or str(safe_call(cleanup, "GetName") or "") != job.cleanup_timeline:
            raise ValidationError("Creazione timeline CLEANUP fallita")
        if not safe_call(project, "SetCurrentTimeline", cleanup):
            raise ValidationError("Selezione timeline CLEANUP fallita")
        record = 0
        for start, end in keep:
            for media_type in (1, 2):
                appended = safe_call(pool, "AppendToTimeline", [{
                    "mediaPoolItem": media_video, "startFrame": source_offset + start,
                    "endFrame": source_offset + end, "recordFrame": record,
                    "mediaType": media_type,
                }])
                if not appended:
                    raise ValidationError(f"Append cleanup fallito: {start}-{end}")
            record += end - start
        return {"ok": True, "created_timeline": job.cleanup_timeline, "existing": False,
                "returned_to_original": True, "cleanup_cuts": len(cleanup_cuts),
                "kept_frames": record}
    except Exception:
        if cleanup is not None:
            safe_call(pool, "DeleteTimelines", [cleanup])
        raise
    finally:
        if not safe_call(project, "SetCurrentTimeline", original):
            raise ValidationError("Ripristino timeline originale fallito")


def create_cleanup_timeline(project: object, job: BrandedLongformJob,
                            cleanup_cuts: tuple[tuple[int, int], ...] = ()) -> dict[str, Any]:
    if cleanup_cuts:
        return _create_cut_cleanup(project, job, cleanup_cuts)
    return _duplicate(project, job, job.original_timeline, job.cleanup_timeline)


def create_editorial_timeline(project: object, job: BrandedLongformJob) -> dict[str, Any]:
    return _duplicate(project, job, job.cleanup_timeline, job.editorial_timeline)


def add_proposal_markers(project: object, job: BrandedLongformJob,
                         proposals: list[dict[str, Any]]) -> dict[str, Any]:
    _check_project(project, job)
    timeline = _find(project, job.cleanup_timeline)
    if timeline is None:
        raise ValidationError("Timeline CLEANUP non trovata")
    existing = safe_call(timeline, "GetMarkers") or {}
    added = 0
    for proposal in proposals:
        proposal_id = str(proposal.get("proposal_id", ""))
        frame = int(proposal.get("start_frame", -1))
        if not proposal_id or frame < 0:
            raise ValidationError("Proposta marker non valida")
        custom = f"BRANDED_LONGFORM:{job.job_id}:{proposal_id}"
        actual = existing.get(frame) or existing.get(str(frame))
        if actual is not None:
            if actual.get("customData") == custom:
                continue
            raise ValidationError(f"Collisione marker al frame {frame}")
        if not safe_call(timeline, "AddMarker", frame, "Blue", f"BL_{proposal_id}",
                         f"{proposal.get('kind')}: {proposal.get('rationale')}", 1, custom):
            raise ValidationError(f"AddMarker fallita al frame {frame}")
        added += 1
        existing = safe_call(timeline, "GetMarkers") or {}
    return {"ok": True, "timeline": job.cleanup_timeline, "added": added,
            "proposal_count": len(proposals)}


def verify_branded_longform_timelines(project: object, job: BrandedLongformJob) -> dict[str, Any]:
    _check_project(project, job)
    names = {str(safe_call(item, "GetName") or "") for item in _timelines(project)}
    missing = [name for name in (job.original_timeline, job.cleanup_timeline, job.editorial_timeline)
               if name not in names]
    if missing:
        raise ValidationError(f"Timeline branded longform mancanti: {missing}")
    return {"ok": True, "original": job.original_timeline, "cleanup": job.cleanup_timeline,
            "editorial": job.editorial_timeline}
