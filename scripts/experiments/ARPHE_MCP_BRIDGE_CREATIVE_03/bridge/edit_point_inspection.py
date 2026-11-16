"""Read-only A/V edit-point inspection for an allowed Resolve timeline."""
from __future__ import annotations

from typing import Any

from .resolve_connection import safe_call


def _source_name(item: object) -> str | None:
    media = safe_call(item, "GetMediaPoolItem")
    if media is None:
        return None
    value = safe_call(media, "GetClipProperty", "File Name")
    return str(value) if value else None


def _track_report(timeline: object, kind: str) -> dict[str, Any]:
    tracks: list[dict[str, Any]] = []
    track_count = int(safe_call(timeline, "GetTrackCount", kind) or 0)
    for track_index in range(1, track_count + 1):
        items = sorted(
            safe_call(timeline, "GetItemListInTrack", kind, track_index) or [],
            key=lambda item: int(safe_call(item, "GetStart") or 0),
        )
        clips = [{
            "start_frame": int(safe_call(item, "GetStart") or 0),
            "end_frame": int(safe_call(item, "GetEnd") or 0),
            "duration_frames": int(safe_call(item, "GetDuration") or 0),
            "source_start_frame": int(safe_call(item, "GetSourceStartFrame") or 0),
            "source_name": _source_name(item),
        } for item in items]
        edit_points = []
        for previous, following in zip(clips, clips[1:]):
            delta = following["start_frame"] - previous["end_frame"]
            relationship = "contiguous" if delta == 0 else "gap" if delta > 0 else "overlap"
            edit_points.append({
                "timeline_range": (previous["end_frame"], following["start_frame"]),
                "relationship": relationship,
                "delta_frames": delta,
            })
        tracks.append({"track_index": track_index, "clips": clips, "edit_points": edit_points})
    first = tracks[0] if tracks else {"track_index": 1, "clips": [], "edit_points": []}
    return {"track_count": track_count, "tracks": tracks, "clips": first["clips"],
            "edit_points": first["edit_points"]}


def inspect_edit_points(timeline: object) -> dict[str, Any]:
    """Return exact A/V boundaries; never infer which editorial correction to apply."""
    return {"audio": _track_report(timeline, "audio"),
            "video": _track_report(timeline, "video")}
