from __future__ import annotations

from datetime import datetime
from fractions import Fraction
from typing import Any

from .config import CreativeConfig
from .feature_flags import require_capability
from .format_contract import ResolvedFormat, apply_project_format, verify_timeline_format
from .registry import Registry
from .resolve_connection import safe_call
from .safety import (PlaybackFpsActionRequired, ValidationError, arphe_name,
                     ensure_no_collision, require_arphe_name, validate_timeline_settings)


def timelines(project: Any) -> list[Any]:
    count = safe_call(project, "GetTimelineCount") or 0
    return [item for index in range(1, int(count) + 1) if (item := safe_call(project, "GetTimelineByIndex", index))]


def timeline_names(project: Any) -> list[str]:
    return [str(safe_call(item, "GetName")) for item in timelines(project)]


def find_timeline(project: Any, name: str) -> Any:
    return next((item for item in timelines(project) if safe_call(item, "GetName") == name), None)


def _timeline_allowed(project_name: str, timeline_name: str, config: CreativeConfig, registry: Registry) -> bool:
    if (timeline_name.startswith("ARPHE_") or timeline_name in config.allowed_timelines
            or registry.timeline_allowed(project_name, timeline_name)):
        return True
    # Vertical Social owns its provisional timeline by the complete plan id.  It
    # begins with "__" to stay visually distinct, so it cannot use the generic
    # ARPHE_ prefix rule; permit only a name reconstructed from a local plan for
    # this workstation and project, never an arbitrary __ARPHE_* timeline.
    if not timeline_name.startswith("__ARPHE_VERTICAL_VERTICAL_"):
        return False
    try:
        from .vertical_social_apply import provisional_timeline_name
        from .vertical_social_jobs import VerticalSocialPlanStore
        store = VerticalSocialPlanStore(config.vertical_social_plans_path, config.workstation_id)
        return any(
            plan.target.get("project") == project_name
            and provisional_timeline_name(plan.plan_id) == timeline_name
            for plan in store._plans().values()
        )
    except (OSError, ValidationError):
        return False


def create_timeline(project: Any, config: CreativeConfig, registry: Registry,
                    name: str, width: int, height: int, fps: float) -> dict:
    require_capability("CAP_TIMELINE", config, None, project, safe_call(project, "GetCurrentTimeline"))
    project_name = str(safe_call(project, "GetName") or "")
    if not (registry.project_allowed(project_name) or project_name in config.allowed_projects):
        raise ValidationError("Impostazioni timeline consentite solo su un progetto creato/allowlisted dal bridge")
    target = arphe_name(name, "CREATIVE_TIMELINE")
    width, height, fps = validate_timeline_settings(width, height, fps)
    ensure_no_collision(target, timeline_names(project), "Timeline")
    contract = ResolvedFormat(width, height, Fraction(str(fps)), Fraction(str(fps)))
    try:
        applied = apply_project_format(project, contract)
    except PlaybackFpsActionRequired as exc:
        return {
            "ok": False, "action": "create_timeline", "stage": "playback_fps",
            "project": project_name, "requested_timeline": target,
            "error": str(exc), "timeline_created": False, **exc.payload(),
        }
    except ValidationError as exc:
        return {
            "ok": False, "action": "create_timeline", "stage": "project_settings",
            "project": project_name, "requested_timeline": target,
            "error": str(exc), "timeline_created": False,
        }
    pool = safe_call(project, "GetMediaPool")
    created = safe_call(pool, "CreateEmptyTimeline", target)
    if not created:
        return {"ok": False, "action": "create_timeline", "stage": "create", "requested_timeline": target}
    current_set = bool(safe_call(project, "SetCurrentTimeline", created))
    actual = {
        "width": safe_call(created, "GetSetting", "timelineResolutionWidth"),
        "height": safe_call(created, "GetSetting", "timelineResolutionHeight"),
        "fps": safe_call(created, "GetSetting", "timelineFrameRate"),
        "playback_fps": applied["timelinePlaybackFrameRate"],
    }
    created_name = safe_call(created, "GetName")
    try:
        verify_timeline_format(project, created, contract)
        settings_match = True
    except ValidationError:
        settings_match = False
    ok = created_name == target and settings_match and current_set
    if created_name == target:
        registry.add_timeline(str(project_name), target)
    return {"ok": ok, "action": "create_timeline", "project": project_name, "created_timeline": created_name,
            "requested_settings": {"width": width, "height": height, "fps": fps}, "actual_settings": actual,
            "project_setting_results": {key: True for key in applied}, "settings_match": settings_match,
            "current_timeline_set": current_set, "overwrite": False}


def set_current_timeline(project: Any, config: CreativeConfig, registry: Registry, name: str) -> dict:
    require_capability("CAP_TIMELINE", config, None, project, safe_call(project, "GetCurrentTimeline"))
    project_name = str(safe_call(project, "GetName"))
    if not _timeline_allowed(project_name, name, config, registry):
        raise ValidationError("Timeline non ARPHE e non allowlisted")
    target = find_timeline(project, name)
    if target is None:
        raise ValidationError("Timeline non trovata")
    previous = safe_call(project, "GetCurrentTimeline")
    changed = bool(safe_call(project, "SetCurrentTimeline", target))
    current = safe_call(project, "GetCurrentTimeline")
    return {"ok": changed and safe_call(current, "GetName") == name, "action": "set_current_timeline",
            "previous_timeline": safe_call(previous, "GetName"), "current_timeline": safe_call(current, "GetName")}


def duplicate_timeline(project: Any, config: CreativeConfig, registry: Registry,
                       source_name: str, requested_suffix: str | None, target_name: str | None) -> dict:
    current = safe_call(project, "GetCurrentTimeline")
    require_capability("CAP_TIMELINE", config, None, project, current)
    project_name = str(safe_call(project, "GetName"))
    if not _timeline_allowed(project_name, source_name, config, registry):
        raise ValidationError("Timeline sorgente non consentita")
    source = find_timeline(project, source_name)
    if source is None:
        raise ValidationError("Timeline sorgente non trovata")
    if target_name:
        target = arphe_name(target_name, "CREATIVE_VERSION")
    else:
        suffix = arphe_name(requested_suffix or "V2", "V2").removeprefix("ARPHE_")
        target = arphe_name(f"{source_name}_{suffix}", "CREATIVE_VERSION")
    ensure_no_collision(target, timeline_names(project), "Timeline target")
    if not safe_call(project, "SetCurrentTimeline", source):
        return {"ok": False, "action": "duplicate_timeline_version", "stage": "select_source"}
    duplicated = safe_call(source, "DuplicateTimeline", target)
    duplicated_name = safe_call(duplicated, "GetName")
    if duplicated_name == target:
        registry.add_timeline(project_name, target)
    return {"ok": duplicated_name == target, "action": "duplicate_timeline_version",
            "source_timeline": source_name, "created_timeline": duplicated_name, "overwrite": False}


def create_safe_working_timeline(project: Any, config: CreativeConfig, registry: Registry, name_prefix: str) -> dict:
    original = safe_call(project, "GetCurrentTimeline")
    if original is None:
        return {"ok": False, "stage": "preflight", "error": "Serve una timeline attiva."}
    name = f"{arphe_name(name_prefix, 'CHATGPT_TEST')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    ensure_no_collision(name, timeline_names(project), "Timeline")
    before = safe_call(project, "GetTimelineCount")
    created = safe_call(safe_call(project, "GetMediaPool"), "CreateEmptyTimeline", name)
    if created is None:
        return {"ok": False, "action": "create_safe_working_timeline", "stage": "create"}
    after = safe_call(project, "GetTimelineCount")
    returned = bool(safe_call(project, "SetCurrentTimeline", original))
    final = safe_call(project, "GetCurrentTimeline")
    count_ok = not isinstance(before, int) or not isinstance(after, int) or after == before + 1
    created_name = safe_call(created, "GetName")
    if created_name == name:
        registry.add_timeline(str(safe_call(project, "GetName")), name)
    return {"ok": created_name == name and returned and safe_call(final, "GetName") == safe_call(original, "GetName") and count_ok,
            "action": "create_safe_working_timeline", "project": safe_call(project, "GetName"),
            "original_timeline": safe_call(original, "GetName"), "created_timeline": created_name,
            "timeline_count_before": before, "timeline_count_after": after, "timeline_count_increment_ok": count_ok,
            "returned_to_original": returned, "current_timeline_final": safe_call(final, "GetName"),
            "clip_edits_performed": 0, "timeline_deletions_performed": 0}
