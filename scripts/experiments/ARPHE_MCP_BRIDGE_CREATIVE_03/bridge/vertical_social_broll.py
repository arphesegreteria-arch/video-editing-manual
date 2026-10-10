from __future__ import annotations

from typing import Any

from .safety import ValidationError
from .longform_tools import allowed_media, import_media_item
from .resolve_connection import safe_call


def _range(raw: object, label: str, maximum: int) -> tuple[int, int]:
    if not isinstance(raw, dict):
        raise ValidationError(f"range {label} mancante")
    start, end = raw.get("start_frame"), raw.get("end_frame")
    if not isinstance(start, int) or not isinstance(end, int) or not 0 <= start < end <= maximum:
        raise ValidationError(f"range {label} non valido")
    return start, end


def validate_provided_broll(action: dict[str, Any], total_frames: int) -> dict[str, Any]:
    if action.get("type") != "B_ROLL_PROVIDED" or action.get("state") != "APPROVED":
        raise ValidationError("B-roll fornito non approvato")
    if not isinstance(total_frames, int) or total_frames <= 0:
        raise ValidationError("durata timeline non valida")
    asset = str(action.get("asset_path", "")).strip()
    if not asset:
        raise ValidationError("asset B-roll fornito mancante")
    if not str(action.get("reason", "")).strip():
        raise ValidationError("reason B-roll mancante")
    timeline_range = _range(action.get("timeline_range"), "timeline B-roll", total_frames)
    source_range = _range(action.get("source_range"), "sorgente B-roll", 10**9)
    if timeline_range[1] - timeline_range[0] != source_range[1] - source_range[0]:
        raise ValidationError("durata B-roll sorgente/timeline diversa")
    return {"asset_path": asset, "timeline_range": timeline_range, "source_range": source_range}


def validate_generated_broll(action: dict[str, Any]) -> None:
    del action
    raise ValidationError("B-roll generato bloccato: provider e approvazione locale richiesti")


def apply_provided_broll(resolve: object, project: object, timeline: object, config: Any,
                         action: dict[str, Any], total_frames: int) -> dict[str, Any]:
    """Insert an approved, allowlisted B-roll clip only on the selected provisional timeline."""
    plan = validate_provided_broll(action, total_frames)
    name = str(safe_call(timeline, "GetName") or "")
    if not name.startswith("__ARPHE_VERTICAL_"):
        raise ValidationError("B-roll consentito solo sulla timeline provvisoria Vertical Social")
    asset = allowed_media(plan["asset_path"], config)
    pool = safe_call(project, "GetMediaPool")
    media = import_media_item(resolve, pool, asset) if pool else None
    if media is None:
        raise ValidationError("Import B-roll fornito fallito")
    start, end = plan["timeline_range"]
    source_start, source_end = plan["source_range"]
    if not safe_call(timeline, "AddTrack", "video"):
        raise ValidationError("Creazione traccia B-roll fallita")
    track = int(safe_call(timeline, "GetTrackCount", "video") or 0)
    appended = safe_call(pool, "AppendToTimeline", [{"mediaPoolItem": media, "startFrame": source_start,
                                                        "endFrame": source_end, "recordFrame": start,
                                                        "mediaType": 1, "trackIndex": track}]) or []
    if len(appended) != 1 or int(safe_call(appended[0], "GetDuration") or 0) != end - start:
        raise ValidationError("Read-back B-roll non corrisponde al piano")
    return {"ok": True, "timeline": name, "track_index": track,
            "timeline_range": [start, end], "source_range": [source_start, source_end]}
