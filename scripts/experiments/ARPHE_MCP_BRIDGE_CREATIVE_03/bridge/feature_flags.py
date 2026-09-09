from __future__ import annotations

from typing import Any

from .config import CAPABILITY_NAMES, CreativeConfig


IMPLEMENTED = {name: True for name in CAPABILITY_NAMES}
CAPABILITY_STATUS = {
    "CAP_PROJECT": "PARTIAL",
    "CAP_TIMELINE": "PARTIAL",
    "CAP_FUSION": "SUPPORTED",
    "CAP_REVIEW": "PARTIAL",
    "CAP_MOTION": "PENDING",
    "CAP_ASSETS": "PENDING",
    "CAP_RENDER": "PENDING",
}


def _method(obj: Any, name: str) -> bool:
    return callable(getattr(obj, name, None))


def _call(obj: Any, name: str) -> Any:
    try:
        method = getattr(obj, name, None)
        return method() if callable(method) else None
    except Exception:
        return None


def availability(manager: Any, project: Any, timeline: Any) -> dict[str, bool]:
    project_ok = manager is not None and all(_method(manager, name) for name in (
        "CreateProject", "LoadProject", "SaveProject", "GetCurrentProject", "GetProjectListInCurrentFolder",
    ))
    pool = _call(project, "GetMediaPool") if project is not None else None
    timeline_ok = project is not None and pool is not None and all(_method(project, name) for name in (
        "GetMediaPool", "SetCurrentTimeline", "GetTimelineCount", "GetTimelineByIndex",
        "GetSetting", "SetSetting",
    )) and _method(pool, "CreateEmptyTimeline")
    fusion_ok = timeline is not None and _method(timeline, "InsertFusionCompositionIntoTimeline")
    assets_ok = timeline_ok and all(_method(pool, name) for name in ("ImportMedia", "AppendToTimeline"))
    render_ok = project is not None and all(_method(project, name) for name in (
        "SetCurrentRenderFormatAndCodec", "SetRenderSettings", "AddRenderJob", "StartRendering",
    ))
    return {
        "CAP_PROJECT": project_ok,
        "CAP_TIMELINE": timeline_ok,
        "CAP_FUSION": fusion_ok,
        "CAP_REVIEW": fusion_ok,
        "CAP_MOTION": fusion_ok,
        "CAP_ASSETS": assets_ok,
        "CAP_RENDER": render_ok,
    }


def report(config: CreativeConfig, manager: Any = None, project: Any = None, timeline: Any = None) -> dict:
    available = availability(manager, project, timeline)
    capabilities = {}
    for name in CAPABILITY_NAMES:
        enabled = config.flags[name]
        technically_available = available[name]
        active = bool(enabled and IMPLEMENTED[name] and technically_available)
        capabilities[name] = {
            "active": active,
            "configured": enabled,
            "implemented": IMPLEMENTED[name],
            "technically_available": technically_available,
            "validated": CAPABILITY_STATUS[name] == "SUPPORTED",
            "status": CAPABILITY_STATUS[name],
        }
    return capabilities


def require_capability(name: str, config: CreativeConfig, manager: Any, project: Any, timeline: Any) -> None:
    info = report(config, manager, project, timeline)[name]
    if not info["active"]:
        raise RuntimeError(f"{name} non attiva: {info}")
