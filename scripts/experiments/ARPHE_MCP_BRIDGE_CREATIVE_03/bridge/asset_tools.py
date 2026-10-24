from __future__ import annotations

from typing import Any

from .config import CreativeConfig
from .feature_flags import require_capability
from .registry import Registry
from .resolve_connection import safe_call
from .safety import ValidationError, allowed_asset, allowed_music_asset, validate_frame_range, validate_music_settings
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
    selected = allowed_asset(path, (config.asset_root, *getattr(config, "media_roots", ())), kind)
    storage = safe_call(project, "GetMediaStorage")
    imported = safe_call(storage, "AddItemListToMediaPool", str(selected)) if storage else None
    if not imported:
        pool = safe_call(project, "GetMediaPool")
        imported = safe_call(pool, "ImportMedia", [str(selected)]) if pool else None
    if not imported:
        return {"ok": False, "action": f"add_{kind}_asset", "stage": "import", "asset_name": selected.name}
    media_item = imported[0]
    pool = safe_call(project, "GetMediaPool")
    created_tracks: list[int] = []

    def rollback(items: list[Any]) -> None:
        rollback_ok = True
        if items and safe_call(timeline, "DeleteClips", items, False) is not True:
            rollback_ok = False
        for created_track in reversed(created_tracks):
            if safe_call(timeline, "DeleteTrack", "video", created_track) is not True:
                rollback_ok = False
        if not rollback_ok:
            raise ValidationError("Rollback inserimento asset incompleto; verifica manuale richiesta")

    current_tracks = safe_call(timeline, "GetTrackCount", "video")
    if isinstance(current_tracks, bool) or not isinstance(current_tracks, int) or current_tracks < 0:
        raise ValidationError("Conteggio tracce video non verificabile")
    for expected_track_count in range(current_tracks + 1, int(track_index) + 1):
        if safe_call(timeline, "AddTrack", "video") is not True:
            rollback([])
            raise ValidationError("Impossibile creare la traccia video richiesta")
        created_tracks.append(expected_track_count)
        if safe_call(timeline, "GetTrackCount", "video") != expected_track_count:
            rollback([])
            raise ValidationError("Read-back creazione traccia video non verificabile")
    # Resolve uses an inclusive source endFrame; bridge and TimelineItem ranges
    # are half-open [start, end).
    appended = safe_call(pool, "AppendToTimeline", [{"mediaPoolItem": media_item,
                                                       "startFrame": 0,
                                                       "endFrame": end - start - 1,
                                                       "recordFrame": start,
                                                       "mediaType": 1,
                                                       "trackIndex": int(track_index)}])

    if not isinstance(appended, (list, tuple)) or len(appended) != 1:
        rollback(list(appended) if isinstance(appended, (list, tuple)) else [])
        raise ValidationError("Inserimento asset non verificabile")
    item = appended[0]
    actual_start, actual_end = safe_call(item, "GetStart"), safe_call(item, "GetEnd")
    if actual_start != start or actual_end != end:
        rollback([item])
        raise ValidationError(
            "Inserimento asset con range non verificabile: "
            f"atteso=[{start},{end}) effettivo=[{actual_start},{actual_end})"
        )
    created_name = arphe_name(selected.stem, "ASSET")
    safe_call(item, "SetName", created_name)
    return {"ok": True, "action": f"add_{kind}_asset", "asset_name": selected.name,
            "created_item_name": created_name, "timeline": timeline_name,
            "frame_range": [start, end], "track_index": int(track_index),
            "absolute_path_returned": False, "status": "PENDING"}


def set_music_bed(project: Any, timeline: Any, config: CreativeConfig, registry: Registry,
                  path: str, gain_db: float = -24.0, fade_in_frames: int = 12,
                  fade_out_frames: int = 12) -> dict:
    """Place one bridge-owned music item. Existing manual audio is deliberately untouched."""
    require_capability("CAP_ASSETS", config, None, project, timeline)
    project_name, timeline_name = str(safe_call(project, "GetName") or ""), str(safe_call(timeline, "GetName") or "")
    if not timeline_name.startswith("ARPHE_") or not (registry.timeline_allowed(project_name, timeline_name) or timeline_name in config.allowed_timelines):
        raise ValidationError("Timeline non autorizzata per la base musicale")
    selected = allowed_music_asset(path, (config.asset_root, *getattr(config, "media_roots", ())))
    gain, fade_in, fade_out = validate_music_settings(gain_db, fade_in_frames, fade_out_frames)
    video_items = [item
                   for index in range(1, int(safe_call(timeline, "GetTrackCount", "video") or 0) + 1)
                   for item in (safe_call(timeline, "GetItemListInTrack", "video", index) or [])]
    video_start = int(safe_call(timeline, "GetStartFrame") or min(
        (int(safe_call(item, "GetStart") or 0) for item in video_items), default=0))
    video_end = max((int(safe_call(item, "GetEnd") or 0) for item in video_items), default=0)
    if video_end <= video_start:
        raise ValidationError("Timeline senza durata video")
    duration = video_end - video_start
    desired = {"asset_name": selected.name, "gain_db": gain, "fade_in_frames": fade_in,
               "fade_out_frames": fade_out, "start_frame": video_start, "end_frame": video_end,
               "item_name": "ARPHE_MUSIC_BED"}
    existing = registry.music_bed(project_name, timeline_name)
    if existing and all(existing.get(key) == value for key, value in desired.items()):
        track = int(existing.get("track_index", 0))
        matches = [item for item in (safe_call(timeline, "GetItemListInTrack", "audio", track) or [])
                   if safe_call(item, "GetName") == "ARPHE_MUSIC_BED" and safe_call(item, "GetStart") == video_start and safe_call(item, "GetEnd") == video_end]
        if len(matches) == 1:
            return {"ok": True, "action": "set_music_bed", "asset_name": selected.name, "status": "UNCHANGED", "absolute_path_returned": False}
    track = 0
    if existing:
        old_track = int(existing.get("track_index", 0))
        owned = [item for item in (safe_call(timeline, "GetItemListInTrack", "audio", old_track) or [])
                 if safe_call(item, "GetName") == "ARPHE_MUSIC_BED"]
        if owned and not safe_call(timeline, "DeleteClips", owned, False):
            raise ValidationError("Impossibile sostituire la base musicale gestita dal bridge")
        if old_track >= 1:
            track = old_track
    if not track:
        if not safe_call(timeline, "AddTrack", "audio"):
            raise ValidationError("Impossibile creare la traccia musicale")
        track = int(safe_call(timeline, "GetTrackCount", "audio") or 0)
    pool = safe_call(project, "GetMediaPool")
    imported = safe_call(pool, "ImportMedia", [str(selected)]) if pool else None
    if not imported:
        return {"ok": False, "action": "set_music_bed", "asset_name": selected.name, "status": "IMPORT_FAILED", "absolute_path_returned": False}
    before = list(safe_call(timeline, "GetItemListInTrack", "audio", track) or [])
    safe_call(pool, "AppendToTimeline", [{"mediaPoolItem": imported[0], "startFrame": 0,
                                            "endFrame": duration, "recordFrame": video_start,
                                            "mediaType": 2, "trackIndex": track}])
    appended = [item for item in (safe_call(timeline, "GetItemListInTrack", "audio", track) or [])
                if item not in before and safe_call(item, "GetStart") == video_start
                and safe_call(item, "GetEnd") == video_end]
    if len(appended) != 1:
        raise ValidationError("Inserimento della base musicale non verificabile")
    inserted_start, inserted_end = safe_call(appended[0], "GetStart"), safe_call(appended[0], "GetEnd")
    if inserted_start != video_start or inserted_end != video_end:
        raise ValidationError("Inserimento della base musicale non verificabile")
    item = appended[0]
    if not safe_call(item, "SetName", "ARPHE_MUSIC_BED") or not safe_call(item, "SetProperty", "AudioVolume", gain):
        raise ValidationError("Applicazione volume base musicale fallita")
    desired["track_index"] = track
    registry.save_music_bed(project_name, timeline_name, desired)
    return {"ok": True, "action": "set_music_bed", "asset_name": selected.name,
            "status": "APPLIED", "track_index": track, "frame_range": [video_start, video_end],
            "absolute_path_returned": False}

