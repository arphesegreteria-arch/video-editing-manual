"""Read-only Resolve 21 capability inspection."""
from __future__ import annotations

import re
from typing import Any

from .resolve_connection import safe_call


MINIMUM_NATIVE_VERSION = (21, 1)


def parse_resolve_version(value: object) -> tuple[int, ...]:
    match = re.match(r"^\s*(\d+)(?:\.(\d+))?(?:\.(\d+))?(?:\.(\d+))?", str(value or ""))
    if not match:
        return ()
    return tuple(int(part) for part in match.groups(default="0"))


def _has(obj: Any, method: str) -> bool:
    return callable(getattr(obj, method, None))


def _timeline_media_item(timeline: Any) -> Any:
    for track_type in ("video", "audio"):
        try:
            count = int(safe_call(timeline, "GetTrackCount", track_type) or 1)
        except (TypeError, ValueError):
            count = 1
        for index in range(1, max(1, count) + 1):
            for item in safe_call(timeline, "GetItemListInTrack", track_type, index) or []:
                media = safe_call(item, "GetMediaPoolItem")
                if media is not None:
                    return media
    return None


def compatibility_card(resolve: Any, manager: Any, project: Any, timeline: Any) -> dict[str, Any]:
    version_value = safe_call(resolve, "GetVersionString") or safe_call(resolve, "GetVersion")
    version = parse_resolve_version(version_value)
    supported = bool(version and version[:2] >= MINIMUM_NATIVE_VERSION)
    media = _timeline_media_item(timeline) if timeline is not None else None
    native_api = {
        "export_frame": _has(timeline, "ExportFrame"),
        "export_thumbnails": _has(timeline, "ExportThumbnails"),
        "native_transcription": _has(media, "TranscribeAudio") and _has(media, "GetTranscription"),
        "native_subtitles": _has(timeline, "CreateSubtitlesFromAudio"),
    }
    if resolve is None:
        state = "RESOLVE_UNREACHABLE"
    elif not supported:
        state = "UNSUPPORTED_VERSION"
    elif project is None:
        state = "PROJECT_MANAGER"
    elif timeline is None:
        state = "PROJECT_OPEN_NO_TIMELINE"
    else:
        state = "READY"
    return {
        "ok": resolve is not None,
        "action": "inspect_resolve21_compatibility",
        "state": state,
        "resolve_version": version_value,
        "supported": supported,
        "minimum_version": "21.1",
        "project_open": project is not None,
        "timeline_open": timeline is not None,
        "native_api": native_api,
    }
