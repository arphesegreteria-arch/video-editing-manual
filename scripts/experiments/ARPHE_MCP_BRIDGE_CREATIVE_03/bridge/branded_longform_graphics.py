from __future__ import annotations

from pathlib import Path
from typing import Any

from .fusion_tools import CARRIER_ASSET_NAME, MAX_AUTOMATIC_FUSION_FRAMES
from .resolve_connection import safe_call
from .safety import ValidationError
from .vertical_social_overlay import build_graphic_graph


def create_longform_overlay_composition(project: object, timeline: object, config: Any,
                                        expected_timeline: str, start: int, end: int,
                                        name: str) -> tuple[object, object]:
    if str(safe_call(timeline, "GetName") or "") != expected_timeline:
        raise ValidationError("Overlay longform richiesto sulla timeline sbagliata")
    duration = end - start
    if duration <= 0 or duration > MAX_AUTOMATIC_FUSION_FRAMES:
        raise ValidationError("Durata overlay longform fuori limite")
    carrier = (Path(config.asset_root) / CARRIER_ASSET_NAME).resolve()
    if not carrier.is_file():
        raise ValidationError("Carrier Fusion tecnico non installato")
    pool = safe_call(project, "GetMediaPool")
    imported = safe_call(pool, "ImportMedia", [str(carrier)]) if pool else None
    if not imported:
        raise ValidationError("Import carrier longform fallito")
    if not safe_call(timeline, "AddTrack", "video"):
        raise ValidationError("Creazione traccia overlay longform fallita")
    track = int(safe_call(timeline, "GetTrackCount", "video") or 0)
    appended = safe_call(pool, "AppendToTimeline", [{
        "mediaPoolItem": imported[0], "startFrame": 0, "endFrame": duration,
        "recordFrame": start, "mediaType": 1, "trackIndex": track,
    }]) or []
    carrier_item = appended[0] if len(appended) == 1 else None
    if carrier_item is None:
        if not safe_call(timeline, "DeleteTrack", "video", track):
            raise ValidationError("Inserimento carrier fallito e rollback traccia incompleto")
        raise ValidationError("Inserimento carrier longform fallito")
    item = carrier_item
    try:
        fusion_item = safe_call(timeline, "CreateFusionClip", [carrier_item])
        item = fusion_item or carrier_item
        added_comp = safe_call(item, "AddFusionComp")
        indexed_comp = safe_call(item, "GetFusionCompByIndex", 1)
        comp = added_comp or indexed_comp
        if comp is None:
            raise ValidationError(
                "Composizione Fusion longform non disponibile: "
                f"create_fusion_clip={fusion_item is not None}, "
                f"item_name={safe_call(item, 'GetName')}, "
                f"fusion_count={safe_call(item, 'GetFusionCompCount')}, "
                f"add_fusion_comp={added_comp is not None}, indexed_comp={indexed_comp is not None}"
            )
        safe_call(item, "SetName", name)
        if (safe_call(item, "GetStart") != start or safe_call(item, "GetEnd") != end
                or safe_call(item, "GetDuration") != duration):
            raise ValidationError("Read-back range overlay longform non corrispondente")
        return item, comp
    except Exception as exc:
        clips_deleted = bool(safe_call(timeline, "DeleteClips", [item], False))
        track_deleted = bool(safe_call(timeline, "DeleteTrack", "video", track))
        if not clips_deleted or not track_deleted:
            raise ValidationError("Rollback carrier longform parziale fallito") from exc
        raise


def apply_editorial_graphic(project: object, timeline: object, config: Any,
                            job: Any, proposal: dict[str, Any]) -> dict[str, Any]:
    if job.profile_id != "ARPHE_LONGFORM_EDITORIAL" or not proposal.get("executable", False):
        raise ValidationError("Graphic Kit pending o proposta non eseguibile")
    proposal_id = str(proposal.get("proposal_id", ""))
    start, end = int(proposal.get("start_frame", -1)), int(proposal.get("end_frame", -1))
    text = str(proposal.get("operator_modification") or proposal.get("copy")
               or proposal.get("rationale") or "").strip()
    if not proposal_id or start < 0 or end <= start or not text:
        raise ValidationError("Proposta grafica longform incompleta")
    previous = safe_call(project, "GetCurrentTimeline")
    if previous is None or not safe_call(project, "SetCurrentTimeline", timeline):
        raise ValidationError("Selezione timeline editoriale longform fallita")
    item = None
    track_count_before = int(safe_call(timeline, "GetTrackCount", "video") or 0)
    try:
        item, comp = create_longform_overlay_composition(
            project, timeline, config, job.editorial_timeline, start, end,
            f"ARPHE_LONGFORM_{proposal_id}")
        action = {"type": "GRAPHIC", "graphic_kind": "TITLE", "text": text,
                  "style_role": "cream"}
        evidence = build_graphic_graph(comp, action, config.palette)
    except Exception as exc:
        if item is not None:
            clips_deleted = bool(safe_call(timeline, "DeleteClips", [item], False))
            track_count_after = int(safe_call(timeline, "GetTrackCount", "video") or 0)
            track_deleted = (track_count_after <= track_count_before or
                             bool(safe_call(timeline, "DeleteTrack", "video", track_count_after)))
            if not clips_deleted or not track_deleted:
                raise ValidationError("Rollback overlay longform parziale fallito") from exc
        raise
    finally:
        if not safe_call(project, "SetCurrentTimeline", previous):
            raise ValidationError("Ripristino timeline dopo overlay longform fallito")
    return {"ok": True, "proposal_id": proposal_id, "timeline": job.editorial_timeline,
            "range": [start, end], "timeline_item": str(safe_call(item, "GetName") or ""), **evidence}
