from __future__ import annotations

from typing import Any

from .config import CreativeConfig
from .feature_flags import require_capability
from .registry import Registry
from .resolve_connection import safe_call
from .safety import ValidationError, allowed_asset, validate_frame_range
from .safety import arphe_name


def add_asset(project: Any, timeline: Any, config: CreativeConfig, registry: Registry, path: str,
              kind: str, start_frame: int, end_frame: int, track_index: int) -> dict:
    require_capability("CAP_ASSETS", config, None, project, timeline)
    timeline_name = str(safe_call(timeline, "GetName") or "")
    project_name = str(safe_call(project, "GetName") or "")
    if not timeline_name.startswith("ARPHE_"):
        raise ValidationError("Asset consentiti solo su timeline con prefisso ARPHE_")
    if not (registry.timeline_allowed(project_name, timeline_name) or timeline_name in config.allowed_timelines):
        raise ValidationError("Timeline non creata o allowlisted per gli asset")
    start, end = validate_frame_range(start_frame, end_frame)
    selected = allowed_asset(path, config.asset_root, kind)
    storage = safe_call(project, "GetMediaStorage")
    imported = safe_call(storage, "AddItemListToMediaPool", str(selected)) if storage else None
    if not imported:
        pool = safe_call(project, "GetMediaPool")
        imported = safe_call(pool, "ImportMedia", [str(selected)]) if pool else None
    if not imported:
        return {"ok": False, "action": f"add_{kind}_asset", "stage": "import", "asset_name": selected.name}
    media_item = imported[0]
    pool = safe_call(project, "GetMediaPool")
    appended = safe_call(pool, "AppendToTimeline", [{"mediaPoolItem": media_item, "recordFrame": start,
                                                       "endFrame": end - start, "mediaType": 1,
                                                       "trackIndex": int(track_index)}])
    created_name = arphe_name(selected.stem, "ASSET")
    for item in appended or []:
        safe_call(item, "SetName", created_name)
    return {"ok": bool(appended), "action": f"add_{kind}_asset", "asset_name": selected.name,
            "created_item_name": created_name, "timeline": timeline_name,
            "frame_range": [start, end], "track_index": int(track_index),
            "absolute_path_returned": False, "status": "PENDING"}
