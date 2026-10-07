from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from fractions import Fraction
import hashlib
import json
from typing import Any
from uuid import uuid4

from .editorial_workflows import EditorialBrief, RenderProfile
from .format_contract import ResolvedFormat
from .safety import ValidationError


STATES = {"DRAFT", "CONFIRMED", "PREPARED", "APPROVED", "RENDERING", "VERIFYING", "VERIFIED",
          "CANCELLED", "FAILED_PREPARE", "FAILED_RENDER", "FAILED_VERIFY"}
TRANSITIONS = {
    "DRAFT": {"CONFIRMED", "CANCELLED"},
    "CONFIRMED": {"PREPARED", "FAILED_PREPARE", "CANCELLED"},
    "PREPARED": {"APPROVED", "FAILED_PREPARE", "CANCELLED"},
    "APPROVED": {"RENDERING", "CANCELLED"},
    "RENDERING": {"VERIFYING", "FAILED_RENDER", "CANCELLED"},
    "VERIFYING": {"VERIFIED", "FAILED_VERIFY"},
}


@dataclass(frozen=True)
class RenderBatch:
    batch_id: str
    brief_id: str
    workflow_id: str
    workflow_version: int
    profile_id: str
    profile_version: int
    delivery_class: str
    project_name: str
    timeline_names: tuple[str, ...]
    output_names: tuple[str, ...]
    workstation_id: str
    width: int
    height: int
    frame_rate: str
    playback_rate: str
    container: str
    video_codec: str
    video_profile: str | None
    audio_codec: str | None
    audio_sample_rate: int | None
    audio_required: bool
    attempt: int
    previous_batch_id: str | None
    status: str
    requires_technical: bool = False
    queue_before: tuple[str, ...] = ()
    created_job_ids: tuple[str, ...] = ()
    expected_outputs: tuple[str, ...] = ()
    staging_directory: str | None = None
    evidence: dict[str, Any] | None = None
    approval_token: str | None = None
    approved_by_role: str | None = None


def _fraction_text(value: Fraction) -> str:
    return f"{value.numerator}/{value.denominator}"


def create_render_batch(brief: EditorialBrief, profile: RenderProfile, resolved_format: ResolvedFormat,
                        project_name: str, timeline_names: tuple[str, ...], output_names: tuple[str, ...],
                        workstation_id: str, attempt: int = 1,
                        previous_batch_id: str | None = None) -> RenderBatch:
    if attempt < 1 or (attempt > 1 and not previous_batch_id):
        raise ValidationError("Tentativo batch non valido")
    return RenderBatch(
        batch_id=str(uuid4()), brief_id=brief.brief_id, workflow_id=brief.workflow_id,
        workflow_version=brief.workflow_version, profile_id=profile.profile_id,
        profile_version=profile.version, delivery_class=profile.delivery_class,
        project_name=project_name, timeline_names=tuple(timeline_names), output_names=tuple(output_names),
        workstation_id=workstation_id, width=resolved_format.width, height=resolved_format.height,
        frame_rate=_fraction_text(resolved_format.project_rate),
        playback_rate=_fraction_text(resolved_format.playback_rate), container=profile.container,
        video_codec=profile.video_codec, video_profile=profile.video_profile, audio_codec=profile.audio_codec,
        audio_sample_rate=profile.audio_sample_rate, audio_required=profile.audio_required,
        attempt=attempt, previous_batch_id=previous_batch_id,
        status="DRAFT" if brief.unresolved_questions else "CONFIRMED",
        requires_technical=bool(brief.format_request.get("override")), evidence={},
    )


def batch_fingerprint(batch: RenderBatch) -> str:
    data = asdict(batch)
    for key in ("status", "approval_token", "approved_by_role"):
        data.pop(key, None)
    encoded = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def transition_batch(registry: Any, batch_id: str, expected: str, target: str,
                     evidence: dict[str, Any]) -> RenderBatch:
    batch = registry.render_batch(batch_id)
    if batch is None or batch.status != expected:
        raise ValidationError("Stato batch inatteso")
    if target not in STATES or target not in TRANSITIONS.get(expected, set()):
        raise ValidationError(f"Transizione batch non valida: {expected} -> {target}")
    values: dict[str, Any] = {"status": target, "evidence": {**(batch.evidence or {}), **evidence}}
    if "queue_before" in evidence:
        values["queue_before"] = tuple(str(v) for v in evidence["queue_before"])
    if "created_job_ids" in evidence:
        values["created_job_ids"] = tuple(str(v) for v in evidence["created_job_ids"])
    if "expected_outputs" in evidence:
        values["expected_outputs"] = tuple(str(v) for v in evidence["expected_outputs"])
    if "staging_directory" in evidence:
        values["staging_directory"] = str(evidence["staging_directory"])
    updated = replace(batch, **values)
    registry.save_render_batch(updated)
    return updated


def approve_render_batch(registry: Any, batch_id: str, operator_role: str) -> RenderBatch:
    batch = registry.render_batch(batch_id)
    if batch is None or batch.status != "PREPARED":
        raise ValidationError("Solo un batch PREPARED può essere approvato")
    if operator_role not in {"SEGRETERIA", "TECNICO", "ALESSIO"}:
        raise ValidationError("Ruolo approvatore non valido")
    if batch.requires_technical and operator_role not in {"TECNICO", "ALESSIO"}:
        raise ValidationError("Questo batch richiede un ruolo tecnico")
    token = batch_fingerprint(batch)
    approved = replace(batch, status="APPROVED", approval_token=token, approved_by_role=operator_role)
    registry.save_render_batch(approved)
    return approved


def render_batch_from_dict(raw: dict[str, Any]) -> RenderBatch:
    data = dict(raw)
    data.setdefault("video_profile", None)
    for key in ("timeline_names", "output_names", "queue_before", "created_job_ids", "expected_outputs"):
        data[key] = tuple(data.get(key, ()))
    return RenderBatch(**data)
