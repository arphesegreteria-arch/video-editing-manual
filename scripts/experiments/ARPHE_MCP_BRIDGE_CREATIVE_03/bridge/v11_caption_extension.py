"""Narrow, rollback-safe carrier placement for the approved Biorivitalizzazione V11 captions."""
from __future__ import annotations
from pathlib import Path
from typing import Any
from .fusion_tools import CARRIER_ASSET_NAME, set_visibility_window
from .resolve_connection import safe_call
from .safety import ValidationError

PROJECT = "ARPHE_BIORIVITALIZZAZIONE_ADV_20261013_PERSONALE"
TIMELINE = "ARPHE_BIORIVITALIZZAZIONE_V11_KARAOKE_UPPER_SAMPLE_20261016"
R3_TIMELINE = "ARPHE_BIORIVITALIZZAZIONE_V11_KARAOKE_UPPER_SAMPLE_R3_20261016"

_APPROVED_RANGES = {
    TIMELINE: (108177, 108574),
    # R3 replaces both defective carrier layers on a copy, including the
    # original 13 opening words, with one transparent caption carrier.
    R3_TIMELINE: (108014, 108574),
}

def apply_caption_visibility(comp: Any, merge: Any, start: int, end: int) -> bool:
    """Use Resolve-owned keyframes; Text+ SetExpression is not persisted in Resolve 21."""
    return set_visibility_window(comp, merge, start, end)

def place_v11_caption_carrier(project: Any, timeline: Any, config: Any, start: int, end: int) -> tuple[Any, Any]:
    timeline_name = str(safe_call(timeline, "GetName") or "")
    if str(safe_call(project, "GetName") or "") != PROJECT or timeline_name not in _APPROVED_RANGES:
        raise ValidationError("Estensione caption consentita solo su Biorivitalizzazione V11 approvata")
    # 6.91 s is the first omitted spoken word after the existing V11 sample.
    # 20.13 s is the last non-CTA word; `end` is Resolve-exclusive.
    if (start, end) != _APPROVED_RANGES[timeline_name]:
        raise ValidationError("Range caption V11 non approvato")
    carrier = (Path(config.asset_root) / CARRIER_ASSET_NAME).resolve()
    if not carrier.is_file(): raise ValidationError("Carrier Fusion tecnico non installato")
    pool = safe_call(project, "GetMediaPool")
    imported = safe_call(pool, "ImportMedia", [str(carrier)]) if pool else None
    if not imported: raise ValidationError("Import carrier fallito")
    track = int(safe_call(timeline, "GetTrackCount", "video") or 0)
    if not safe_call(timeline, "AddTrack", "video"): raise ValidationError("Track overlay non disponibile")
    item = None
    fusion = None
    try:
        appended = safe_call(pool, "AppendToTimeline", [{"mediaPoolItem": imported[0], "startFrame": 0,
            "endFrame": end-start, "recordFrame": start, "mediaType": 1, "trackIndex": track+1}]) or []
        item = appended[0] if len(appended) == 1 else None
        if item is None or safe_call(item,"GetStart") != start or safe_call(item,"GetEnd") != end: raise ValidationError("Read-back placement carrier non corrisponde")
        fusion = safe_call(timeline, "CreateFusionClip", [item]) or item
        comp = safe_call(fusion, "AddFusionComp") or safe_call(fusion, "GetFusionCompByIndex", 1)
        if comp is None: raise ValidationError("Composizione Fusion non disponibile")
        safe_call(fusion,"SetName","ARPHE_V11_KARAOKE_FULL_CUES")
        return fusion, comp
    except Exception:
        # Prefer the Fusion wrapper: deleting only the pre-wrap item can leave
        # a visible orphan when the comp setup fails after wrapping.
        rollback_item = fusion or item
        if rollback_item is not None: safe_call(timeline,"DeleteClips",[rollback_item],False)
        # This is the fresh, last video track we added above.  It is removed
        # only after its one carrier item was rolled back.
        safe_call(timeline, "DeleteTrack", "video", track + 1)
        raise
