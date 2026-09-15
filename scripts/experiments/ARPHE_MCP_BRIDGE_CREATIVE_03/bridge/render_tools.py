from __future__ import annotations

from typing import Any

from .config import CreativeConfig
from .feature_flags import require_capability
from .registry import Registry
from .resolve_connection import safe_call
from .safety import ValidationError, arphe_name, ensure_no_collision, require_arphe_name


def render_preview(project: Any, timeline: Any, config: CreativeConfig, registry: Registry, output_name: str) -> dict:
    require_capability("CAP_RENDER", config, None, project, timeline)
    project_name = str(safe_call(project, "GetName") or "")
    timeline_name = str(safe_call(timeline, "GetName") or "")
    require_arphe_name(project_name, "progetto")
    require_arphe_name(timeline_name, "timeline")
    if not (registry.timeline_allowed(project_name, timeline_name) or timeline_name in config.allowed_timelines):
        raise ValidationError("Render consentito solo su timeline creata o allowlisted dal bridge")
    config.render_root.mkdir(parents=True, exist_ok=True)
    name = arphe_name(output_name, "PREVIEW")
    existing_outputs = [item.stem for item in config.render_root.iterdir() if item.is_file()]
    ensure_no_collision(name, existing_outputs, "Output render")
    format_ok = bool(safe_call(project, "SetCurrentRenderFormatAndCodec", config.render_format, config.render_codec))
    settings_ok = bool(safe_call(project, "SetRenderSettings", {
        "TargetDir": str(config.render_root), "CustomName": name, "SelectAllFrames": True,
    }))
    if not (format_ok and settings_ok):
        return {"ok": False, "action": "render_preview", "stage": "settings", "status": "PENDING"}
    job_id = safe_call(project, "AddRenderJob")
    started = bool(safe_call(project, "StartRendering", job_id)) if job_id else False
    return {"ok": bool(job_id and started), "action": "render_preview", "job_id": job_id,
            "output_name": name, "output_directory_disclosed": False, "status": "PENDING"}


def _timeline_map(project: Any) -> dict[str, Any]:
    count = int(safe_call(project, "GetTimelineCount") or 0)
    return {str(safe_call(item, "GetName") or ""): item for index in range(1, count + 1)
            if (item := safe_call(project, "GetTimelineByIndex", index))}


def queue_longform_exports(manager: Any, project: Any, config: CreativeConfig, registry: Registry) -> dict:
    require_capability("CAP_LONGFORM", config, manager, project, safe_call(project, "GetCurrentTimeline"))
    project_name = str(safe_call(project, "GetName") or "")
    require_arphe_name(project_name, "progetto")
    batch = registry.longform_batch(project_name)
    if not batch or not batch.get("clip_timelines"):
        raise ValidationError("Nessun batch long-form registrato per il progetto corrente")
    config.render_root.mkdir(parents=True, exist_ok=True)
    timelines = _timeline_map(project)
    existing = [item.stem for item in config.render_root.iterdir() if item.is_file()]
    for name in batch["clip_timelines"]:
        if timelines.get(name) is None or not registry.timeline_allowed(project_name, name):
            raise ValidationError(f"Timeline batch non disponibile: {name}")
        ensure_no_collision(name, existing, "Output render")
    original = safe_call(project, "GetCurrentTimeline")
    jobs = []
    try:
        for name in batch["clip_timelines"]:
            timeline = timelines.get(name)
            if not safe_call(project, "SetCurrentTimeline", timeline):
                raise RuntimeError(f"Impossibile selezionare la timeline {name}")
            format_ok = bool(safe_call(project, "SetCurrentRenderFormatAndCodec",
                                       config.render_format, config.render_codec))
            settings_ok = bool(safe_call(project, "SetRenderSettings", {
                "TargetDir": str(config.render_root), "CustomName": name, "SelectAllFrames": True,
            }))
            if not (format_ok and settings_ok):
                raise RuntimeError(f"Impostazioni render non applicate per {name}")
            job_id = safe_call(project, "AddRenderJob")
            if not job_id:
                raise RuntimeError(f"Job render non creato per {name}")
            jobs.append({"timeline": name, "output_name": name, "job_id": job_id})
    finally:
        if original:
            safe_call(project, "SetCurrentTimeline", original)
    registry.add_element(f"LONGFORM_EXPORTS::{project_name}", {"kind": "longform_exports", "jobs": jobs})
    return {"ok": True, "action": "queue_longform_exports", "project": project_name,
            "job_count": len(jobs), "jobs": jobs, "render_started": False,
            "output_directory_disclosed": False}


def start_longform_exports(project: Any, config: CreativeConfig, registry: Registry) -> dict:
    require_capability("CAP_RENDER", config, None, project, safe_call(project, "GetCurrentTimeline"))
    project_name = str(safe_call(project, "GetName") or "")
    record = registry.element(f"LONGFORM_EXPORTS::{project_name}")
    jobs = record.get("jobs", []) if record else []
    if not jobs:
        raise ValidationError("Prima preparare i job con queue_longform_exports")
    job_ids = [item["job_id"] for item in jobs]
    started = bool(safe_call(project, "StartRendering", job_ids))
    return {"ok": started, "action": "start_longform_exports", "project": project_name,
            "job_count": len(job_ids), "status": "RENDERING" if started else "PENDING"}
