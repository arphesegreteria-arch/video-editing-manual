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
