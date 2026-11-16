from __future__ import annotations

from typing import Any

from .resolve_connection import safe_call
from .safety import ValidationError
from .vertical_social_reframe import (
    apply_fusion_reframe,
    reframe_transform_plan,
    validate_reframe_action,
)


def provisional_timeline_name(plan_id: str) -> str:
    suffix = str(plan_id).replace("vertical_", "", 1).upper()
    if len(suffix) != 32 or not suffix.isalnum():
        raise ValidationError("plan_id Vertical Social non valido")
    return f"__ARPHE_VERTICAL_VERTICAL_{suffix}"


def find_provisional_timeline(project: object, plan_id: str) -> object:
    expected = provisional_timeline_name(plan_id)
    matches = []
    for index in range(1, int(safe_call(project, "GetTimelineCount") or 0) + 1):
        timeline = safe_call(project, "GetTimelineByIndex", index)
        if timeline is not None and str(safe_call(timeline, "GetName") or "") == expected:
            matches.append(timeline)
    if len(matches) != 1:
        raise ValidationError(f"Timeline provvisoria Vertical Social non univoca: {expected}")
    return matches[0]


def _exact_video_item(timeline: object, start: int, end: int) -> object:
    matches = [
        item for item in (safe_call(timeline, "GetItemListInTrack", "video", 1) or [])
        if safe_call(item, "GetStart") == start
        and safe_call(item, "GetEnd") == end
    ]
    if len(matches) != 1:
        raise ValidationError("REFRAME deve coincidere con i confini di una clip provvisoria")
    return matches[0]


def _containing_video_item(timeline: object, start: int, end: int) -> object:
    matches = [
        item for item in (safe_call(timeline, "GetItemListInTrack", "video", 1) or [])
        if int(safe_call(item, "GetStart") or 0) <= start
        and int(safe_call(item, "GetEnd") or 0) >= end
    ]
    if len(matches) != 1:
        raise ValidationError("CAMERA_ZOOM deve ricadere in una sola clip provvisoria")
    return matches[0]


def apply_reframe_action(timeline: object, action: dict[str, Any], total_frames: int) -> dict[str, Any]:
    validated = validate_reframe_action(action, total_frames)
    start, end = validated["range"]
    timeline_start = int(safe_call(timeline, "GetStartFrame") or 0)
    absolute_start, absolute_end = timeline_start + start, timeline_start + end
    item = (_containing_video_item(timeline, absolute_start, absolute_end)
            if validated["motion"] is not None
            else _exact_video_item(timeline, absolute_start, absolute_end))
    width = int(safe_call(timeline, "GetSetting", "timelineResolutionWidth") or 0)
    height = int(safe_call(timeline, "GetSetting", "timelineResolutionHeight") or 0)
    item_start = int(safe_call(item, "GetStart") or 0)
    transform = reframe_transform_plan(
        action, width, height, local_start=absolute_start - item_start,
        local_end=absolute_end - item_start,
    )
    if not apply_fusion_reframe(item, transform):
        raise ValidationError("Read-back REFRAME non riuscito")
    return {"ok": True, "action_id": str(action["action_id"]),
            "timeline": str(safe_call(timeline, "GetName") or ""),
            "range": [start, end], "anchor": validated["anchor"],
            "motion": validated["motion"],
            "zoom_samples": transform.get("motion_readback", []),
            "output": transform["output"]}
