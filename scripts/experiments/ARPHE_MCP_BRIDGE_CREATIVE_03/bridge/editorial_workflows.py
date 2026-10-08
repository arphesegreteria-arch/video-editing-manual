from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from .safety import ValidationError


WORKFLOW_KEYS = {"workflow_id", "version", "label", "purpose", "recognition_hints", "automation_level", "questions", "format_contract", "allowed_profiles", "technical_override_roles"}
PROFILE_KEYS = {"profile_id", "version", "delivery_class", "container", "video_codec", "video_profile", "audio_codec", "audio_sample_rate", "audio_required", "resolution_mode", "resolution", "frame_rate_mode", "frame_rate", "allowed_workflows", "path_class"}
AUTOMATION_LEVELS = {"AUTOMATIC", "ASSISTED", "EDITOR_LED"}
ROLES = {"SEGRETERIA", "TECNICO", "ALESSIO"}


@dataclass(frozen=True)
class EditorialWorkflow:
    workflow_id: str
    version: int
    label: str
    purpose: str
    recognition_hints: tuple[str, ...]
    automation_level: str
    questions: tuple[str, ...]
    format_contract: dict[str, Any]
    allowed_profiles: tuple[str, ...]
    technical_override_roles: tuple[str, ...]


@dataclass(frozen=True)
class WorkflowRegistry:
    schema_version: int
    workflows: dict[str, EditorialWorkflow]


@dataclass(frozen=True)
class RenderProfile:
    profile_id: str
    version: int
    delivery_class: str
    container: str
    video_codec: str
    video_profile: str | None
    audio_codec: str | None
    audio_sample_rate: int | None
    audio_required: bool
    resolution_mode: str
    resolution: tuple[int, int] | None
    frame_rate_mode: str
    frame_rate: str | None
    allowed_workflows: tuple[str, ...]
    path_class: str


@dataclass(frozen=True)
class RenderProfileRegistry:
    schema_version: int
    profiles: dict[str, RenderProfile]


@dataclass(frozen=True)
class EditorialBrief:
    brief_id: str
    workflow_id: str
    workflow_version: int
    operator_role: str
    primary_source: str | None
    requested_outputs: tuple[str, ...]
    format_request: dict[str, Any]
    answers: dict[str, str]
    unresolved_questions: tuple[str, ...]


def _object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"Registry non leggibile: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValidationError("Il registry deve essere un oggetto JSON")
    return value


def _strict_keys(value: dict[str, Any], allowed: set[str], kind: str) -> None:
    unknown = set(value) - allowed
    if unknown:
        raise ValidationError(f"{kind}: campi sconosciuti: {sorted(unknown)}")


def load_workflow_registry(path: Path) -> WorkflowRegistry:
    raw = _object(path)
    _strict_keys(raw, {"schema_version", "workflows"}, "workflow registry")
    if raw.get("schema_version") != 1 or not isinstance(raw.get("workflows"), list):
        raise ValidationError("Workflow registry schema non supportato")
    loaded: dict[str, EditorialWorkflow] = {}
    for item in raw["workflows"]:
        if not isinstance(item, dict):
            raise ValidationError("Workflow non valido")
        _strict_keys(item, WORKFLOW_KEYS, "workflow")
        missing = WORKFLOW_KEYS - set(item)
        if missing:
            raise ValidationError(f"Workflow incompleto: {sorted(missing)}")
        workflow_id = str(item["workflow_id"])
        if workflow_id in loaded:
            raise ValidationError(f"workflow_id duplicato: {workflow_id}")
        if item["automation_level"] not in AUTOMATION_LEVELS:
            raise ValidationError(f"automation_level non valido: {item['automation_level']}")
        questions = tuple(str(value) for value in item["questions"])
        if len(questions) < 9 or len(questions) != len(set(questions)):
            raise ValidationError(f"Domande mancanti o duplicate: {workflow_id}")
        loaded[workflow_id] = EditorialWorkflow(
            workflow_id=workflow_id,
            version=int(item["version"]),
            label=str(item["label"]),
            purpose=str(item["purpose"]),
            recognition_hints=tuple(str(v) for v in item["recognition_hints"]),
            automation_level=str(item["automation_level"]),
            questions=questions,
            format_contract=dict(item["format_contract"]),
            allowed_profiles=tuple(str(v) for v in item["allowed_profiles"]),
            technical_override_roles=tuple(str(v) for v in item["technical_override_roles"]),
        )
    return WorkflowRegistry(1, loaded)


def load_render_profile_registry(path: Path) -> RenderProfileRegistry:
    raw = _object(path)
    _strict_keys(raw, {"schema_version", "profiles"}, "render profile registry")
    if raw.get("schema_version") != 1 or not isinstance(raw.get("profiles"), list):
        raise ValidationError("Render profile registry schema non supportato")
    loaded: dict[str, RenderProfile] = {}
    for item in raw["profiles"]:
        if not isinstance(item, dict):
            raise ValidationError("Render profile non valido")
        _strict_keys(item, PROFILE_KEYS, "render profile")
        required = PROFILE_KEYS - {"resolution", "frame_rate"}
        missing = required - set(item)
        if missing:
            raise ValidationError(f"Render profile incompleto: {sorted(missing)}")
        profile_id = str(item["profile_id"])
        if profile_id in loaded:
            raise ValidationError(f"profile_id duplicato: {profile_id}")
        resolution = item.get("resolution")
        loaded[profile_id] = RenderProfile(
            profile_id=profile_id,
            version=int(item["version"]),
            delivery_class=str(item["delivery_class"]),
            container=str(item["container"]),
            video_codec=str(item["video_codec"]),
            video_profile=None if item["video_profile"] is None else str(item["video_profile"]),
            audio_codec=None if item["audio_codec"] is None else str(item["audio_codec"]),
            audio_sample_rate=None if item["audio_sample_rate"] is None else int(item["audio_sample_rate"]),
            audio_required=bool(item["audio_required"]),
            resolution_mode=str(item["resolution_mode"]),
            resolution=None if resolution is None else (int(resolution[0]), int(resolution[1])),
            frame_rate_mode=str(item["frame_rate_mode"]),
            frame_rate=None if item.get("frame_rate") is None else str(item["frame_rate"]),
            allowed_workflows=tuple(str(v) for v in item["allowed_workflows"]),
            path_class=str(item["path_class"]),
        )
    return RenderProfileRegistry(1, loaded)


def validate_editorial_brief(raw: dict[str, Any], workflows: WorkflowRegistry) -> EditorialBrief:
    if not isinstance(raw, dict):
        raise ValidationError("Brief non valido")
    _strict_keys(raw, {"brief_id", "workflow_id", "operator_role", "primary_source", "requested_outputs", "format_request", "answers"}, "brief")
    role = str(raw.get("operator_role", ""))
    if role not in ROLES:
        raise ValidationError("operator_role non valido")
    workflow_id = str(raw.get("workflow_id", ""))
    workflow = workflows.workflows.get(workflow_id)
    if workflow_id and workflow is None:
        raise ValidationError(f"workflow_id sconosciuto: {workflow_id}")
    primary_source = raw.get("primary_source")
    requested = tuple(str(v) for v in raw.get("requested_outputs", []))
    format_request = raw.get("format_request", {})
    answers = raw.get("answers", {})
    if not isinstance(format_request, dict) or not isinstance(answers, dict):
        raise ValidationError("format_request e answers devono essere oggetti")
    unresolved: list[str] = []
    if workflow is None:
        unresolved.append("workflow_id")
    if not isinstance(primary_source, str) or not primary_source.strip():
        unresolved.append("primary_source")
        primary_source = None
    if not requested:
        unresolved.append("requested_outputs")
    if workflow is not None:
        unresolved.extend(question for question in workflow.questions if not str(answers.get(question, "")).strip())
    source_rates = {str(value) for value in format_request.get("source_rates", [])}
    needs_source_rate = workflow is None or workflow.format_contract.get("frame_rate_mode") != "fixed"
    if needs_source_rate and len(source_rates) > 1 and not format_request.get("primary_frame_rate"):
        unresolved.append("primary_frame_rate")
    return EditorialBrief(
        brief_id=str(raw.get("brief_id") or uuid4()),
        workflow_id=workflow_id,
        workflow_version=0 if workflow is None else workflow.version,
        operator_role=role,
        primary_source=primary_source,
        requested_outputs=requested,
        format_request=dict(format_request),
        answers={str(key): str(value) for key, value in answers.items()},
        unresolved_questions=tuple(dict.fromkeys(unresolved)),
    )


def resolve_delivery_profile(brief: EditorialBrief, profile_id: str, profiles: RenderProfileRegistry) -> RenderProfile:
    profile = profiles.profiles.get(profile_id)
    if profile is None:
        raise ValidationError(f"Render profile sconosciuto: {profile_id}")
    if brief.workflow_id not in profile.allowed_workflows:
        raise ValidationError(f"Render profile non consentito per {brief.workflow_id}")
    if brief.format_request.get("override") and brief.operator_role not in {"TECNICO", "ALESSIO"}:
        raise ValidationError("Override consentito soltanto a un ruolo tecnico")
    if profile.delivery_class not in brief.requested_outputs:
        raise ValidationError(f"Classe {profile.delivery_class} non richiesta dal brief")
    return profile
