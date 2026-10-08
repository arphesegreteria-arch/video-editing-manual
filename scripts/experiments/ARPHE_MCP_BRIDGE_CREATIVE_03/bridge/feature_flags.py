from __future__ import annotations

from typing import Any

from .config import CAPABILITY_NAMES, CreativeConfig


IMPLEMENTED = {name: True for name in CAPABILITY_NAMES}
IMPLEMENTED["CAP_CLEANUP"] = False
CAPABILITY_STATUS = {
    "CAP_PROJECT": "PARTIAL",
    "CAP_TIMELINE": "PARTIAL",
    "CAP_FUSION": "SUPPORTED",
    "CAP_REVIEW": "PARTIAL",
    "CAP_MOTION": "PENDING",
    "CAP_ASSETS": "PENDING",
    "CAP_RENDER": "PENDING",
    "CAP_LONGFORM": "PENDING",
    "CAP_CLEANUP": "PENDING",
    "CAP_ARTIFACT_MAINTENANCE": "PENDING",
    "CAP_RESOLVE_RETIREMENT": "PENDING",
    "CAP_READABILITY_GUARD": "PARTIAL",
    "CAP_EDITORIAL_SELECTION": "PENDING",
}


def _method(obj: Any, name: str) -> bool:
    return callable(getattr(obj, name, None))


def _call(obj: Any, name: str) -> Any:
    try:
        method = getattr(obj, name, None)
        return method() if callable(method) else None
    except Exception:
        return None


def _readability_guard_available() -> bool:
    try:
        from . import review_workflow
        from .readability_contract import load_readability_contract

        load_readability_contract(review_workflow.CONTRACT_PATH)
        return all(callable(getattr(review_workflow, name, None)) for name in (
            "inspect_sequence_readability",
            "add_guarded_review_card",
            "create_guarded_review_sequence",
        ))
    except Exception:
        return False


def _editorial_selection_available(project: Any, timeline: Any) -> bool:
    try:
        from . import editorial_cut_workflow, editorial_learning, editorial_markers, editorial_review
        pool = _call(project, "GetMediaPool") if project is not None else None
        modules_ok = all(callable(function) for function in (
            editorial_cut_workflow.apply_or_resume_editorial_cuts,
            editorial_learning.append_local_outcome,
            editorial_markers.mark_candidates,
            editorial_review.submit_structured_review,
        ))
        project_ok = project is not None and pool is not None and all(_method(project, name) for name in (
            "GetName", "GetTimelineCount", "GetTimelineByIndex", "GetMediaPool", "SetCurrentTimeline",
            "GetSetting",
        ))
        timeline_ok = timeline is not None and all(_method(timeline, name) for name in (
            "GetName", "GetUniqueId", "GetSetting", "GetMarkers", "AddMarker",
            "DeleteMarkerAtFrame", "GetItemListInTrack",
        ))
        pool_ok = pool is not None and all(_method(pool, name) for name in (
            "CreateEmptyTimeline", "AppendToTimeline", "GetRootFolder",
        ))
        return modules_ok and project_ok and timeline_ok and pool_ok
    except Exception:
        return False


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
    retirement_ok = manager is not None and project is not None and pool is not None and all(
        _method(manager, name) for name in (
            "SaveProject", "ExportProject", "GetProjectLastModifiedTime",
            "GetProjectListInCurrentFolder", "CloseProject", "DeleteProject", "ImportProject",
        )
    ) and _method(pool, "DeleteTimelines")
    return {
        "CAP_PROJECT": project_ok,
        "CAP_TIMELINE": timeline_ok,
        "CAP_FUSION": fusion_ok,
        "CAP_REVIEW": fusion_ok,
        "CAP_MOTION": fusion_ok,
        "CAP_ASSETS": assets_ok,
        "CAP_RENDER": render_ok,
        "CAP_LONGFORM": project_ok and assets_ok,
        "CAP_CLEANUP": False,
        "CAP_ARTIFACT_MAINTENANCE": True,
        "CAP_RESOLVE_RETIREMENT": retirement_ok,
        "CAP_READABILITY_GUARD": _readability_guard_available(),
        "CAP_EDITORIAL_SELECTION": _editorial_selection_available(project, timeline),
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
