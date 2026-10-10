from __future__ import annotations

from typing import Any

from .longform_tools import allowed_media, import_media_item
from .resolve_connection import safe_call
from .safety import ValidationError


def apply_provided_broll(resolve: object, project: object, timeline: object,
                         config: Any, job: Any, proposal: dict[str, Any]) -> dict[str, Any]:
    if job.profile_id != "ARPHE_LONGFORM_EDITORIAL" or proposal.get("kind") != "B_ROLL_PROVIDED":
        raise ValidationError("B-roll longform non autorizzato per il profilo")
    asset_path = str(proposal.get("asset_path") or "").strip()
    source_start, source_end = proposal.get("source_start_frame"), proposal.get("source_end_frame")
    start, end = int(proposal.get("start_frame", -1)), int(proposal.get("end_frame", -1))
    if (not asset_path or not isinstance(source_start, int) or not isinstance(source_end, int)
            or not 0 <= source_start < source_end or end - start != source_end - source_start):
        raise ValidationError("Piano B-roll longform incompleto o durata non corrispondente")
    if str(safe_call(timeline, "GetName") or "") != job.editorial_timeline:
        raise ValidationError("B-roll longform richiesto sulla timeline editoriale sbagliata")
    asset = allowed_media(asset_path, config)
    pool = safe_call(project, "GetMediaPool")
    media = import_media_item(resolve, pool, asset) if pool else None
    if media is None or not safe_call(timeline, "AddTrack", "video"):
        raise ValidationError("Preparazione B-roll longform fallita")
    track = int(safe_call(timeline, "GetTrackCount", "video") or 0)
    appended = safe_call(pool, "AppendToTimeline", [{"mediaPoolItem": media,
        "startFrame": source_start, "endFrame": source_end, "recordFrame": start,
        "mediaType": 1, "trackIndex": track}]) or []
    if len(appended) != 1 or int(safe_call(appended[0], "GetDuration") or 0) != end - start:
        raise ValidationError("Read-back B-roll longform non corrisponde al piano")
    return {"ok": True, "proposal_id": proposal["proposal_id"], "timeline": job.editorial_timeline,
            "track_index": track, "range": [start, end], "asset": asset.name}
