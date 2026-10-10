from __future__ import annotations

from typing import Any


def final_vertical_social_check(plan: dict[str, Any], picture_locked: bool) -> dict[str, Any]:
    target = plan.get("target", {})
    actions = list(plan.get("actions", []))
    issues: list[str] = []
    if (target.get("width"), target.get("height")) != (1080, 1920):
        issues.append("vertical_format_mismatch")
    if str(target.get("fps", "")) != str(target.get("playback_fps", "")):
        issues.append("playback_fps_mismatch")
    in_flight = [str(action.get("action_id", "")) for action in actions
                 if action.get("state") in {"PROPOSED", "APPROVED", "APPLIED"}]
    blocked = [str(action.get("action_id", "")) for action in actions
               if action.get("state") == "BLOCKED"]
    if in_flight:
        issues.append("actions_not_verified")
    if any(action.get("type") == "CAPTIONS" and not picture_locked for action in actions):
        issues.append("caption_before_picture_lock")
    review_ready = not any(issue in issues for issue in (
        "vertical_format_mismatch", "playback_fps_mismatch", "actions_not_verified",
        "caption_before_picture_lock"))
    return {"ready_for_human_review": review_ready,
            "ready_for_delivery": review_ready and not blocked,
            "issues": issues, "in_flight_actions": in_flight,
            "blocked_actions": blocked}
