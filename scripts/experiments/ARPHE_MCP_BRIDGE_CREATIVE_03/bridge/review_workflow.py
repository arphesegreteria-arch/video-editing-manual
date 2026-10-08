from __future__ import annotations

from fractions import Fraction
from pathlib import Path
from typing import Any

from .config import CreativeConfig
from .creative_tools import add_review_card, create_review_sequence
from .font_readiness import WindowsGdiTextMeasurer, check_required_fonts
from .readability_approvals import require_current_approval
from .readability_contract import load_readability_contract
from .registry import Registry
from .resolve_connection import safe_call
from .review_readability import BLOCKED, PASS, SequenceAssessment, assess_sequence
from .safety import ValidationError


CONTRACT_PATH = Path(__file__).resolve().parents[1] / "review_readability_contract.json"


def _rate(value: object) -> Fraction | None:
    try:
        return Fraction(str(value).strip())
    except (ValueError, ZeroDivisionError):
        return None


def _timeline_fps(timeline: Any) -> float:
    value = safe_call(timeline, "GetSetting", "timelineFrameRate")
    rate = _rate(value)
    if rate is None or rate <= 0:
        raise ValidationError("CONTRACT_MISMATCH: timeline frame rate non leggibile")
    return float(rate)


def _require_vertical_30(project: Any, timeline: Any) -> None:
    project_values = {
        "width": safe_call(project, "GetSetting", "timelineResolutionWidth"),
        "height": safe_call(project, "GetSetting", "timelineResolutionHeight"),
        "project_fps": safe_call(project, "GetSetting", "timelineFrameRate"),
        "playback_fps": safe_call(project, "GetSetting", "timelinePlaybackFrameRate"),
    }
    timeline_values = {
        "width": safe_call(timeline, "GetSetting", "timelineResolutionWidth"),
        "height": safe_call(timeline, "GetSetting", "timelineResolutionHeight"),
        "timeline_fps": safe_call(timeline, "GetSetting", "timelineFrameRate"),
    }
    correct = (
        str(project_values["width"]) == "1080"
        and str(project_values["height"]) == "1920"
        and str(timeline_values["width"]) == "1080"
        and str(timeline_values["height"]) == "1920"
        and _rate(project_values["project_fps"]) == Fraction(30)
        and _rate(project_values["playback_fps"]) == Fraction(30)
        and _rate(timeline_values["timeline_fps"]) == Fraction(30)
    )
    if not correct:
        raise ValidationError(
            "UNSAFE_LAYOUT: review verticali richiedono progetto, timeline e playback 1080x1920 a 30 fps"
        )


def _assessment(
    timeline: Any,
    reviews: list[dict],
) -> tuple[SequenceAssessment, Any, Any, Any]:
    policy = load_readability_contract(CONTRACT_PATH)
    measurer = WindowsGdiTextMeasurer()
    fonts = check_required_fonts(policy, measurer)
    assessment = assess_sequence(
        reviews,
        "story_reel_1080x1920",
        _timeline_fps(timeline),
        policy,
        measurer,
        fonts,
    )
    return assessment, policy, measurer, fonts


def inspect_sequence_readability(
    timeline: Any,
    config: CreativeConfig,
    reviews: list[dict],
) -> SequenceAssessment:
    del config
    assessment, _policy, _measurer, _fonts = _assessment(timeline, reviews)
    return assessment


def _guard_and_expand(
    project: Any,
    timeline: Any,
    config: CreativeConfig,
    registry: Registry,
    reviews: list[dict],
    approval_token: str | None,
) -> tuple[list[dict], list[dict[str, Any]], SequenceAssessment]:
    if not config.flags.get("CAP_READABILITY_GUARD", False):
        raise ValidationError("Capability disabilitata: CAP_READABILITY_GUARD")
    _require_vertical_30(project, timeline)
    assessment, policy, measurer, fonts = _assessment(timeline, reviews)
    if assessment.status == BLOCKED:
        reasons = ",".join(assessment.reason_codes)
        raise ValidationError(f"readability BLOCKED: {reasons}")
    approval = require_current_approval(registry, assessment, approval_token)
    decisions = {
        int(item["review_index"]): item for item in (approval.decisions if approval else ())
    }
    expanded: list[dict] = []
    layouts: list[dict[str, Any]] = []
    safe_area = dict(policy.canvases["story_reel_1080x1920"]["essential_safe_area"])
    typography = {role: dict(values) for role, values in policy.typography.items()}

    def layout_for(item: Any) -> dict[str, Any]:
        return {
            "duration_frames": item.duration_frames,
            "selected_size": item.selected_size,
            "line_count": item.line_count,
            "safe_area": dict(safe_area),
            "typography": {role: dict(values) for role, values in typography.items()},
        }

    for index, (review, item_assessment) in enumerate(zip(reviews, assessment.reviews)):
        decision = decisions.get(index)
        if decision and decision["decision"] == "VERBATIM_SPLIT":
            offset = int(decision["split_offset"])
            text = review["text"]
            parts = (text[:offset], text[offset:])
            if "".join(parts) != text:
                raise ValidationError("STALE_APPROVAL: split non verbatim")
            for part in parts:
                payload = dict(review)
                payload["text"] = part
                part_assessment = assess_sequence(
                    [payload],
                    "story_reel_1080x1920",
                    30.0,
                    policy,
                    measurer,
                    fonts,
                ).reviews[0]
                if part_assessment.status != PASS:
                    raise ValidationError("TEXT_OVERFLOW: parte split non leggibile")
                expanded.append(payload)
                layouts.append(layout_for(part_assessment))
        else:
            expanded.append(dict(review))
            layouts.append(layout_for(item_assessment))
    return expanded, layouts, assessment


def create_guarded_review_sequence(
    project: Any,
    timeline: Any,
    config: CreativeConfig,
    registry: Registry,
    name: str,
    reviews: list[dict],
    total_duration_frames: int,
    style_role: str,
    cta: dict | None,
    intro: dict | None,
    approval_token: str | None,
) -> dict:
    expanded, layouts, assessment = _guard_and_expand(
        project, timeline, config, registry, reviews, approval_token
    )
    minimum = sum(int(layout["duration_frames"]) for layout in layouts)
    if total_duration_frames and total_duration_frames < minimum:
        raise ValidationError(
            f"total_duration_frames non può essere inferiore alla leggibilità ({minimum})"
        )
    result = create_review_sequence(
        project,
        timeline,
        config,
        registry,
        name,
        expanded,
        0,
        style_role,
        cta,
        intro,
        readability_layouts=layouts,
    )
    result["readability"] = assessment.to_dict()
    result["readability"]["expanded_card_count"] = len(expanded)
    return result


def add_guarded_review_card(
    project: Any,
    timeline: Any,
    config: CreativeConfig,
    registry: Registry,
    composition_id: str,
    text: str,
    stars: int,
    start_frame: int,
    end_frame: int,
    style_role: str,
    highlight_text: str | None,
    small_label: str | None,
    approval_token: str | None,
) -> dict:
    reviews = [{"text": text, "stars": stars}]
    expanded, layouts, assessment = _guard_and_expand(
        project, timeline, config, registry, reviews, approval_token
    )
    if len(expanded) != 1:
        raise ValidationError("VERBATIM_SPLIT richiede create_review_sequence_v2")
    if end_frame - start_frame < int(layouts[0]["duration_frames"]):
        raise ValidationError("Intervallo card inferiore alla durata di leggibilità")
    result = add_review_card(
        project,
        timeline,
        config,
        registry,
        composition_id,
        text,
        stars,
        start_frame,
        end_frame,
        style_role,
        highlight_text,
        small_label,
        readability_layout=layouts[0],
    )
    result["readability"] = assessment.to_dict()
    return result
