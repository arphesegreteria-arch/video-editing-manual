"""Isolated, reversible draft application for a reviewed Carabellese proposal.

This module deliberately does not alter the persistent Carabellese job state: the
canonical source job remains marked for human review/apply.  It is used only to
build a separately named Resolve timeline for a private preview.
"""
from __future__ import annotations

from fractions import Fraction
from typing import Any, Iterable

from .carabellese_apply import _ceil, _floor, _fraction, _keep_ranges, _timeline_shape, media_source_identity
from .safety import ValidationError


def _call(target: object, method: str, *args: object) -> Any:
    function = getattr(target, method, None)
    if not callable(function):
        raise ValidationError(f"API draft Carabellese non supportata: {method}")
    try:
        return function(*args)
    except Exception as exc:
        raise ValidationError(f"Resolve {method} fallita: {exc}") from exc


def draft_cuts(candidates: Iterable[dict[str, object]], fps: Fraction, total_frames: int) -> list[dict[str, object]]:
    """Turn explicit source-time candidates into non-overlapping frame cuts."""
    result: list[dict[str, object]] = []
    for candidate in candidates:
        start = _floor(float(candidate["start_seconds"]), fps)
        end = _ceil(float(candidate["end_seconds"]), fps)
        if start < 0 or end <= start or end > total_frames:
            raise ValidationError("Taglio draft fuori dalla timeline")
        result.append({"candidate_id": str(candidate["candidate_id"]),
                       "start_frame": start, "end_frame_exclusive": end})
    result.sort(key=lambda item: int(item["start_frame"]))
    if any(int(current["start_frame"]) < int(previous["end_frame_exclusive"])
           for previous, current in zip(result, result[1:])):
        raise ValidationError("Tagli draft sovrapposti")
    return result


def apply_draft_cleanup(project: object, timeline: object,
                        candidates: Iterable[dict[str, object]]) -> dict[str, object]:
    """Apply candidate removals to an already duplicated one-clip A/V timeline.

    Staging occurs on extra tracks and is read back before the duplicate's
    original clips are touched.  The source timeline is never passed here.
    """
    current = _call(project, "GetCurrentTimeline")
    current_id = _call(current, "GetUniqueId") if callable(getattr(current, "GetUniqueId", None)) else None
    requested_id = _call(timeline, "GetUniqueId") if callable(getattr(timeline, "GetUniqueId", None)) else None
    if current is not timeline and (not current_id or current_id != requested_id):
        raise ValidationError("Timeline draft non corrente")
    video_original, audio_original, media = _timeline_shape(timeline)
    fps = _fraction(_call(timeline, "GetSetting", "timelineFrameRate"), "timelineFrameRate")
    total_frames = int(_call(video_original, "GetDuration"))
    cuts = draft_cuts(candidates, fps, total_frames)
    keep = _keep_ranges(total_frames, cuts)
    pool = _call(project, "GetMediaPool")
    staged = False
    destructive_started = False
    try:
        if not _call(timeline, "AddTrack", "video") or not _call(timeline, "AddTrack", "audio"):
            raise RuntimeError("add_staging_tracks_failed")
        staged = True
        record = int(_call(timeline, "GetStartFrame") or 0)
        for start, end in keep:
            for media_type in (1, 2):
                if not _call(pool, "AppendToTimeline", [{"mediaPoolItem": media,
                          "startFrame": start, "endFrame": end, "recordFrame": record,
                          "trackIndex": 2, "mediaType": media_type}]):
                    raise RuntimeError(f"stage_append_failed:{start}:{end}:{media_type}")
            record += end - start
        staged_video = _call(timeline, "GetItemListInTrack", "video", 2) or []
        staged_audio = _call(timeline, "GetItemListInTrack", "audio", 2) or []
        expected_duration = sum(end - start for start, end in keep)
        if (len(staged_video) != len(keep) or len(staged_audio) != len(keep)
                or sum(int(_call(item, "GetDuration")) for item in staged_video) != expected_duration
                or sum(int(_call(item, "GetDuration")) for item in staged_audio) != expected_duration):
            raise RuntimeError("staging_readback_failed")
        destructive_started = True
        if not _call(timeline, "DeleteClips", [video_original, audio_original], False):
            raise RuntimeError("delete_original_clips_failed")
        if not _call(timeline, "DeleteTrack", "video", 1) or not _call(timeline, "DeleteTrack", "audio", 1):
            raise RuntimeError("delete_original_tracks_failed")
        return {"ok": True, "cut_count": len(cuts), "cuts": cuts,
                "final_frames": expected_duration, "segment_count": len(keep),
                "fps": str(fps), "source_identity": media_source_identity(media)}
    except Exception as exc:
        if staged and not destructive_started:
            if int(_call(timeline, "GetTrackCount", "video") or 0) > 1:
                _call(timeline, "DeleteTrack", "video", 2)
            if int(_call(timeline, "GetTrackCount", "audio") or 0) > 1:
                _call(timeline, "DeleteTrack", "audio", 2)
        raise ValidationError(f"Applicazione draft Carabellese fallita: {type(exc).__name__}:{exc}") from exc
