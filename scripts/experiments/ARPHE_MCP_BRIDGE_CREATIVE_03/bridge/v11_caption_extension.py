"""Narrow, rollback-safe carrier placement for the approved Biorivitalizzazione V11 captions."""
from __future__ import annotations
from pathlib import Path
from typing import Any
from .fusion_tools import CARRIER_ASSET_NAME
from .resolve_connection import safe_call
from .safety import ValidationError

PROJECT = "ARPHE_BIORIVITALIZZAZIONE_ADV_20261013_PERSONALE"
TIMELINE = "ARPHE_BIORIVITALIZZAZIONE_V11_KARAOKE_UPPER_SAMPLE_20261016"

def place_v11_caption_carrier(project: Any, timeline: Any, config: Any, start: int, end: int) -> tuple[Any, Any]:
    if str(safe_call(project, "GetName") or "") != PROJECT or str(safe_call(timeline, "GetName") or "") != TIMELINE:
        raise ValidationError("Estensione caption consentita solo su Biorivitalizzazione V11 approvata")
    # 6.91 s is the first omitted spoken word after the existing V11 sample.
    # 20.13 s is the last non-CTA word; `end` is Resolve-exclusive.
    if not (start == 108177 and end == 108574):
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
