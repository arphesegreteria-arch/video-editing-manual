from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import CreativeConfig
from .feature_flags import require_capability
from .registry import Registry
from .resolve_connection import safe_call
from .safety import ValidationError, arphe_name, ensure_no_collision


MAX_CLIPS = 32
MAX_CLIP_SECONDS = 180.0
MEDIA_EXTENSIONS = {".mp4", ".mov", ".mxf", ".mkv", ".m4v"}


def _inside_roots(path: Path, roots: tuple[Path, ...]) -> bool:
    selected = path.expanduser().resolve(strict=True)
    return selected.is_file() and any(selected.is_relative_to(root.resolve(strict=True)) for root in roots)


def allowed_media(path_value: str, config: CreativeConfig) -> Path:
    if not isinstance(path_value, str) or not path_value.strip():
        raise ValidationError("media_path richiesto")
    selected = Path(path_value).expanduser().resolve(strict=True)
    if selected.suffix.lower() not in MEDIA_EXTENSIONS or not _inside_roots(selected, config.media_roots):
        raise ValidationError("Media fuori dalle cartelle allowlisted o con formato non consentito")
    return selected


def allowed_transcript(path_value: str, config: CreativeConfig) -> Path:
    selected = Path(path_value).expanduser().resolve(strict=True)
    root = config.transcript_root.resolve(strict=True)
    if selected.suffix.lower() != ".json" or not selected.is_file() or not selected.is_relative_to(root):
        raise ValidationError("Transcript fuori dalla cartella allowlisted")
    return selected


def transcript_metadata(path_value: str, config: CreativeConfig) -> dict[str, Any]:
    selected = allowed_transcript(path_value, config)
    data = json.loads(selected.read_text(encoding="utf-8-sig"))
    if data.get("schema") != "ARPHE_TRANSCRIPT_V1" or data.get("status") != "complete":
        raise ValidationError("Transcript non completo o schema non supportato")
    return {"ok": True, "action": "get_transcript_metadata", "name": selected.name,
            "source": {k: data.get("source", {}).get(k) for k in ("name", "size_bytes", "fingerprint", "duration_seconds")},
            "transcription": data.get("transcription", {}), "summary": data.get("summary", {})}


def list_media(config: CreativeConfig) -> dict[str, Any]:
    items = []
    for root in config.media_roots:
        if not root.is_dir():
            continue
        for path in root.iterdir():
            if path.is_file() and path.suffix.lower() in MEDIA_EXTENSIONS:
                items.append({"name": path.name, "path": str(path.resolve()), "size_bytes": path.stat().st_size})
    return {"ok": True, "action": "list_longform_media", "items": sorted(items, key=lambda v: v["name"].casefold())}


def transcript_chunk(path_value: str, config: CreativeConfig, start_second: float,
                     end_second: float) -> dict[str, Any]:
    selected = allowed_transcript(path_value, config)
    start, end = float(start_second), float(end_second)
    if start < 0 or end <= start or end - start > 600:
        raise ValidationError("Chunk richiesto: 0 <= start < end, massimo 600 secondi")
    data = json.loads(selected.read_text(encoding="utf-8-sig"))
    segments = [item for item in data.get("segments", [])
                if float(item["end"]) > start and float(item["start"]) < end]
    return {"ok": True, "action": "get_transcript_chunk", "start_second": start,
            "end_second": end, "segments": segments}


def validate_plan(clips: list[dict[str, Any]], fps: float = 30.0) -> list[dict[str, Any]]:
    if not isinstance(clips, list) or not 1 <= len(clips) <= MAX_CLIPS:
        raise ValidationError(f"clips deve contenere 1-{MAX_CLIPS} elementi")
    rate = float(fps)
    if rate not in {24.0, 25.0, 30.0}:
        raise ValidationError("fps non consentito")
    clean: list[dict[str, Any]] = []
    ids: set[str] = set()
    for index, raw in enumerate(clips, 1):
        if not isinstance(raw, dict):
            raise ValidationError("Ogni clip deve essere un oggetto")
        clip_id = arphe_name(str(raw.get("clip_id") or f"LONGFORM_{index:02d}"), f"LONGFORM_{index:02d}")
        if clip_id in ids:
            raise ValidationError("clip_id duplicato")
        ids.add(clip_id)
        start = float(raw.get("start_second"))
        end = float(raw.get("end_second"))
        if start < 0 or end <= start or end - start > MAX_CLIP_SECONDS:
            raise ValidationError("Ogni estratto deve durare più di 0 e al massimo 180 secondi")
        source_in = int(round(start * rate))
        source_out_exclusive = int(round(end * rate))
        clean.append({"clip_id": clip_id, "title": str(raw.get("title") or clip_id)[:120],
                      "start_second": start, "end_second": end,
                      "source_in_frame": source_in, "source_out_frame_exclusive": source_out_exclusive,
                      "duration_frames": source_out_exclusive - source_in,
                      "boundary_method": str(raw.get("boundary_method") or "approved_semantic_boundary"),
                      "confidence": str(raw.get("confidence") or "needs_av_review")})
    return clean


def apply_plan(resolve: Any, manager: Any, config: CreativeConfig, registry: Registry, media_path: str,
               project_name: str, master_timeline_name: str, clips: list[dict[str, Any]],
               fps: float = 30.0, enhanced_audio_path: str | None = None) -> dict[str, Any]:
    current_project = safe_call(manager, "GetCurrentProject")
    current_timeline = safe_call(current_project, "GetCurrentTimeline")
    require_capability("CAP_LONGFORM", config, manager, current_project, current_timeline)
    media = allowed_media(media_path, config)
    enhanced_audio = None
    if enhanced_audio_path:
        from .audio_tools import allowed_audio
        enhanced_audio = allowed_audio(enhanced_audio_path, config)
    plan = validate_plan(clips, fps)
    project_name = arphe_name(project_name, "LONGFORM")
    master_name = arphe_name(master_timeline_name, "LONGFORM_MASTER")
    existing_projects = safe_call(manager, "GetProjectListInCurrentFolder") or []
    ensure_no_collision(project_name, existing_projects, "Progetto")
    project = safe_call(manager, "CreateProject", project_name)
    if not project:
        return {"ok": False, "action": "apply_longform_edit_plan", "stage": "create_project"}
    registry.add_project(project_name)
    setting_results = {
        "timelineResolutionWidth": bool(safe_call(project, "SetSetting", "timelineResolutionWidth", "1920")),
        "timelineResolutionHeight": bool(safe_call(project, "SetSetting", "timelineResolutionHeight", "1080")),
        "timelineFrameRate": bool(safe_call(project, "SetSetting", "timelineFrameRate", str(rate := float(fps)))),
    }
    if not all(setting_results.values()):
        return {"ok": False, "action": "apply_longform_edit_plan", "stage": "project_settings",
                "project": project_name, "setting_results": setting_results}
    pool = safe_call(project, "GetMediaPool")
    media_storage = safe_call(resolve, "GetMediaStorage")
    imported = safe_call(media_storage, "AddItemListToMediaPool", str(media)) if media_storage else None
    if not imported:
        imported = safe_call(pool, "ImportMedia", [str(media)])
    item = imported[0] if imported else None
    if not item:
        return {"ok": False, "action": "apply_longform_edit_plan", "stage": "import_media",
                "project": project_name}
    audio_item = None
    if enhanced_audio is not None:
        imported_audio = safe_call(media_storage, "AddItemListToMediaPool", str(enhanced_audio)) if media_storage else None
        if not imported_audio:
            imported_audio = safe_call(pool, "ImportMedia", [str(enhanced_audio)])
        audio_item = imported_audio[0] if imported_audio else None
        if not audio_item:
            return {"ok": False, "action": "apply_longform_edit_plan", "stage": "import_enhanced_audio",
                    "project": project_name}

    def append_range(record_frame: int, start: int, end_inclusive: int) -> bool:
        if audio_item is None:
            return bool(safe_call(pool, "AppendToTimeline", [{"mediaPoolItem": item, "startFrame": start,
                                                               "endFrame": end_inclusive,
                                                               "recordFrame": record_frame}]))
        video = safe_call(pool, "AppendToTimeline", [{"mediaPoolItem": item, "mediaType": 1,
                                                        "startFrame": start, "endFrame": end_inclusive,
                                                        "recordFrame": record_frame}])
        audio = safe_call(pool, "AppendToTimeline", [{"mediaPoolItem": audio_item, "mediaType": 2,
                                                        "startFrame": start, "endFrame": end_inclusive,
                                                        "recordFrame": record_frame}])
        return bool(video and audio)
    master = safe_call(pool, "CreateEmptyTimeline", master_name)
    if not master:
        return {"ok": False, "action": "apply_longform_edit_plan", "stage": "create_master"}
    registry.add_timeline(project_name, master_name)
    record = int(safe_call(master, "GetStartFrame") or 0)
    created_timelines: list[str] = []
    for clip in plan:
        start = clip["source_in_frame"]
        end_inclusive = clip["source_out_frame_exclusive"] - 1
        if not safe_call(project, "SetCurrentTimeline", master):
            return {"ok": False, "action": "apply_longform_edit_plan", "stage": "select_master",
                    "failed_clip": clip["clip_id"], "project": project_name,
                    "master_timeline": master_name}
        appended = append_range(record, start, end_inclusive)
        if not appended:
            return {"ok": False, "action": "apply_longform_edit_plan", "stage": "append_master",
                    "failed_clip": clip["clip_id"], "project": project_name, "master_timeline": master_name}
        record += clip["duration_frames"]
        timeline_name = arphe_name(clip["clip_id"], f"CLIP_{len(created_timelines)+1:02d}")
        individual = safe_call(pool, "CreateEmptyTimeline", timeline_name)
        if not individual:
            return {"ok": False, "action": "apply_longform_edit_plan", "stage": "create_clip_timeline",
                    "failed_clip": clip["clip_id"]}
        registry.add_timeline(project_name, timeline_name)
        individual_start = int(safe_call(individual, "GetStartFrame") or 0)
        if not safe_call(project, "SetCurrentTimeline", individual):
            return {"ok": False, "action": "apply_longform_edit_plan",
                    "stage": "select_clip_timeline", "failed_clip": clip["clip_id"]}
        one = append_range(individual_start, start, end_inclusive)
        if not one:
            return {"ok": False, "action": "apply_longform_edit_plan", "stage": "append_clip_timeline",
                    "failed_clip": clip["clip_id"]}
        created_timelines.append(timeline_name)
    registry.set_longform_batch(project_name, master_name, created_timelines)
    safe_call(project, "SetCurrentTimeline", master)
    return {"ok": True, "action": "apply_longform_edit_plan", "project": project_name,
            "master_timeline": master_name, "clip_timelines": created_timelines,
            "clip_count": len(plan), "total_frames": sum(v["duration_frames"] for v in plan),
            "fps": rate, "resolution": {"width": 1920, "height": 1080},
            "source_preserved": True, "overwrite": False, "saved": False,
            "enhanced_audio_used": audio_item is not None,
            "plan": plan}
