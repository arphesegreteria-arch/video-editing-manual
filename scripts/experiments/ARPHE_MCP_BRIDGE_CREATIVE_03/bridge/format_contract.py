from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any

from .editorial_workflows import EditorialBrief, load_workflow_registry
from .resolve_connection import safe_call
from .safety import PlaybackFpsActionRequired, ValidationError


SUPPORTED_RATES = {
    Fraction(24000, 1001), Fraction(24), Fraction(25),
    Fraction(30000, 1001), Fraction(30), Fraction(50),
    Fraction(60000, 1001), Fraction(60),
}
RATE_LABELS = {
    Fraction(24000, 1001): "23.976",
    Fraction(30000, 1001): "29.97",
    Fraction(60000, 1001): "59.94",
}


@dataclass(frozen=True)
class SourceFormat:
    width: int
    height: int
    frame_rate: Fraction


@dataclass(frozen=True)
class ResolvedFormat:
    width: int
    height: int
    project_rate: Fraction
    playback_rate: Fraction


def _rate(value: Any) -> Fraction:
    text = str(value).strip()
    known = {"23.976": Fraction(24000, 1001), "29.97": Fraction(30000, 1001), "59.94": Fraction(60000, 1001)}
    try:
        result = known.get(text, Fraction(text))
    except (ValueError, ZeroDivisionError):
        raise ValidationError(f"Frame rate non leggibile: {value}") from None
    if result not in SUPPORTED_RATES:
        raise ValidationError(f"Frame rate non supportato: {value}")
    return result


def _rate_label(rate: Fraction) -> str:
    return RATE_LABELS.get(rate, str(rate.numerator) if rate.denominator == 1 else f"{float(rate):.6f}".rstrip("0"))


def _equivalent(actual: Any, expected: Fraction) -> bool:
    try:
        return _rate(actual) == expected
    except ValidationError:
        return False


def resolve_format_contract(brief: EditorialBrief, sources: list[SourceFormat]) -> ResolvedFormat:
    if brief.unresolved_questions:
        raise ValidationError("Il brief contiene domande irrisolte")
    registry = load_workflow_registry(Path(__file__).resolve().parents[1] / "editorial_workflows.json")
    workflow = registry.workflows.get(brief.workflow_id)
    if workflow is None:
        raise ValidationError("Workflow non disponibile")
    contract = workflow.format_contract
    normalized = [SourceFormat(int(source.width), int(source.height), _rate(source.frame_rate)) for source in sources]
    if contract["resolution_mode"] == "source" or contract["frame_rate_mode"] == "source":
        if not normalized:
            raise ValidationError("Formato della sorgente primaria richiesto")
    selected_rate = None
    if contract["frame_rate_mode"] == "source":
        source_rates = {source.frame_rate for source in normalized}
        confirmed = brief.format_request.get("primary_frame_rate")
        if confirmed is not None:
            selected_rate = _rate(confirmed)
            if source_rates and selected_rate not in source_rates:
                raise ValidationError("Il frame rate primario confermato non appartiene alle sorgenti")
        elif len(source_rates) == 1:
            selected_rate = next(iter(source_rates))
        elif len(source_rates) > 1:
            raise ValidationError("Con sorgenti miste serve la conferma della frequenza primaria")

    if contract["resolution_mode"] == "fixed":
        width, height = (int(value) for value in contract["resolution"])
    elif contract["resolution_mode"] == "source":
        width, height = normalized[0].width, normalized[0].height
    else:
        try:
            width = int(brief.format_request["width"])
            height = int(brief.format_request["height"])
        except (KeyError, TypeError, ValueError):
            raise ValidationError("Risoluzione esplicita richiesta") from None

    if contract["frame_rate_mode"] == "fixed":
        rate = _rate(contract["frame_rate"])
    elif contract["frame_rate_mode"] == "source":
        if selected_rate is None:
            raise ValidationError("Frame rate della sorgente primaria richiesto")
        rate = selected_rate
    else:
        if "frame_rate" not in brief.format_request:
            raise ValidationError("Frame rate esplicito richiesto")
        rate = _rate(brief.format_request["frame_rate"])
    return ResolvedFormat(width, height, rate, rate)


def apply_project_format(project: Any, contract: ResolvedFormat) -> dict[str, str]:
    requested = {
        "timelineResolutionWidth": str(contract.width),
        "timelineResolutionHeight": str(contract.height),
        "timelineFrameRate": _rate_label(contract.project_rate),
    }
    previous = {key: safe_call(project, "GetSetting", key) for key in requested}
    changed: list[str] = []
    for key, value in requested.items():
        if not safe_call(project, "SetSetting", key, value):
            for restore_key in reversed(changed):
                if previous[restore_key] is not None:
                    safe_call(project, "SetSetting", restore_key, str(previous[restore_key]))
            raise ValidationError(f"Resolve ha rifiutato {key}")
        changed.append(key)
    actual = {key: safe_call(project, "GetSetting", key) for key in requested}
    actual["timelinePlaybackFrameRate"] = safe_call(project, "GetSetting", "timelinePlaybackFrameRate")
    matches = (
        str(actual["timelineResolutionWidth"]) == str(contract.width)
        and str(actual["timelineResolutionHeight"]) == str(contract.height)
        and _equivalent(actual["timelineFrameRate"], contract.project_rate)
    )
    if not matches:
        raise ValidationError("Project format read-back non conforme")
    require_project_playback(project, contract.playback_rate,
                             actual=actual["timelinePlaybackFrameRate"])
    return {key: str(value) for key, value in actual.items()}


def require_project_playback(project: Any, required: Fraction,
                             actual: object | None = None) -> str:
    """Fail closed when Resolve's read-only playback rate needs operator action."""
    value = safe_call(project, "GetSetting", "timelinePlaybackFrameRate") if actual is None else actual
    if not _equivalent(value, required):
        raise PlaybackFpsActionRequired(value, _rate_label(required))
    return str(value)


def verify_timeline_format(project: Any, timeline: Any, contract: ResolvedFormat) -> None:
    project_values = {
        "width": safe_call(project, "GetSetting", "timelineResolutionWidth"),
        "height": safe_call(project, "GetSetting", "timelineResolutionHeight"),
        "rate": safe_call(project, "GetSetting", "timelineFrameRate"),
        "playback": safe_call(project, "GetSetting", "timelinePlaybackFrameRate"),
    }
    timeline_values = {
        "width": safe_call(timeline, "GetSetting", "timelineResolutionWidth"),
        "height": safe_call(timeline, "GetSetting", "timelineResolutionHeight"),
        "rate": safe_call(timeline, "GetSetting", "timelineFrameRate"),
    }
    correct = (
        str(project_values["width"]) == str(contract.width)
        and str(project_values["height"]) == str(contract.height)
        and _equivalent(project_values["rate"], contract.project_rate)
        and _equivalent(project_values["playback"], contract.playback_rate)
        and str(timeline_values["width"]) == str(contract.width)
        and str(timeline_values["height"]) == str(contract.height)
        and _equivalent(timeline_values["rate"], contract.project_rate)
    )
    if not correct:
        raise ValidationError("Timeline format read-back non conforme")
