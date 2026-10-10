from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any
from uuid import uuid4

from .safety import ValidationError


SCHEMA = "ARPHE_WORKFLOW_CONTROL_PLANE_V1"
FINGERPRINT = re.compile(r"^[0-9a-f]{64}$")
WORKSTATION = re.compile(r"^PC_[A-Z0-9_]{2,48}$")
FAMILIES = frozenset({"PODCAST_REELS", "VERTICAL_SOCIAL", "CARABELLESE_CLEANUP", "BRANDED_LONGFORM"})
STATES = frozenset({"PROPOSED", "AWAITING_APPROVAL", "EXECUTING", "REVIEW_READY",
                    "DELIVERY_AWAITING_APPROVAL", "CLOSED", "BLOCKED", "STALE",
                    "FAILED_RECOVERABLE"})
ACTIVE_STATES = frozenset({"PROPOSED", "AWAITING_APPROVAL", "EXECUTING", "REVIEW_READY",
                           "DELIVERY_AWAITING_APPROVAL"})


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _digest(value: object) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class WorkflowJob:
    workflow_job_id: str
    workstation_id: str
    workflow_family: str
    native_reference: str
    target: dict[str, object]
    plan_fingerprint: str
    approved_plan_fingerprint: str | None
    state: str
    revision: int
    resume_state: str | None
    evidence: dict[str, object]
    created_at: str
    updated_at: str


def _validate(job: WorkflowJob) -> None:
    if not re.fullmatch(r"^workflow_[0-9a-f]{16}$", job.workflow_job_id):
        raise ValidationError("workflow_job_id non valido")
    if not WORKSTATION.fullmatch(job.workstation_id):
        raise ValidationError("workstation_id non valido")
    if job.workflow_family not in FAMILIES or not job.native_reference:
        raise ValidationError("workflow_family o native_reference non valido")
    if not isinstance(job.target, dict) or not job.target.get("project_name") or not job.target.get("timeline_name"):
        raise ValidationError("target non valido")
    if not FINGERPRINT.fullmatch(job.plan_fingerprint):
        raise ValidationError("plan fingerprint non valido")
    if job.approved_plan_fingerprint is not None and not FINGERPRINT.fullmatch(job.approved_plan_fingerprint):
        raise ValidationError("approved plan fingerprint non valido")
    if job.state not in STATES or job.revision < 0:
        raise ValidationError("stato o revisione non validi")
    if job.state in {"BLOCKED", "FAILED_RECOVERABLE"} and job.resume_state not in ACTIVE_STATES:
        raise ValidationError("resume_state richiesto")
    if job.state not in {"BLOCKED", "FAILED_RECOVERABLE"} and job.resume_state is not None:
        raise ValidationError("resume_state non consentito")
    if not isinstance(job.evidence, dict):
        raise ValidationError("evidence non valida")


def new_workflow_job(workstation_id: str, workflow_family: str, native_reference: str,
                     target: dict[str, object], plan_fingerprint: str) -> WorkflowJob:
    now = _now()
    job = WorkflowJob("workflow_" + uuid4().hex[:16], workstation_id, workflow_family,
                      native_reference, dict(target), plan_fingerprint, None, "PROPOSED", 0,
                      None, {}, now, now)
    _validate(job)
    return job


def workflow_job_fingerprint(job: WorkflowJob) -> str:
    return _digest({"workstation_id": job.workstation_id, "workflow_family": job.workflow_family,
                    "native_reference": job.native_reference, "target": job.target,
                    "plan_fingerprint": job.plan_fingerprint})


class WorkflowJobStore:
    def __init__(self, path: Path, workstation_id: str):
        if not WORKSTATION.fullmatch(workstation_id):
            raise ValidationError("workstation_id store non valido")
        self.path, self.workstation_id = path, workstation_id
        if path.is_file() and self._read()["workstation_id"] != workstation_id:
            raise ValidationError("Registro appartenente a un'altra workstation")

    def _read(self) -> dict[str, Any]:
        if not self.path.is_file():
            return {"schema": SCHEMA, "workstation_id": self.workstation_id, "jobs": {}}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValidationError(f"Registro control plane non leggibile: {exc}") from exc
        if not isinstance(data, dict) or set(data) != {"schema", "workstation_id", "jobs"}:
            raise ValidationError("Registro control plane non valido")
        if data["schema"] != SCHEMA or data["workstation_id"] != self.workstation_id or not isinstance(data["jobs"], dict):
            raise ValidationError("Registro control plane di un'altra workstation o non valido")
        return data

    def _save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=self.path.name + ".", dir=str(self.path.parent), text=True)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False, sort_keys=True)
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    @staticmethod
    def _decode(raw: object) -> WorkflowJob:
        if not isinstance(raw, dict) or set(raw) != set(WorkflowJob.__dataclass_fields__):
            raise ValidationError("Record control plane non valido")
        try:
            job = WorkflowJob(**raw)
        except TypeError as exc:
            raise ValidationError("Record control plane malformato") from exc
        _validate(job)
        return job

    def create(self, job: WorkflowJob) -> WorkflowJob:
        _validate(job)
        if job.workstation_id != self.workstation_id:
            raise ValidationError("Job di un'altra workstation")
        data = self._read()
        raw = data["jobs"].get(job.workflow_job_id)
        if raw is not None:
            existing = self._decode(raw)
            if existing != job:
                raise ValidationError("job_id esistente con contenuto differente")
            return existing
        data["jobs"][job.workflow_job_id] = asdict(job)
        self._save(data)
        return job

    def get(self, workflow_job_id: str) -> WorkflowJob:
        raw = self._read()["jobs"].get(workflow_job_id)
        if raw is None:
            raise ValidationError("Workflow job sconosciuto")
        return self._decode(raw)

    def save(self, job: WorkflowJob, expected_revision: int) -> WorkflowJob:
        current = self.get(job.workflow_job_id)
        if current.revision != expected_revision:
            raise ValidationError("revision workflow job stale")
        immutable = ("workflow_job_id", "workstation_id", "workflow_family", "native_reference", "target", "plan_fingerprint", "created_at")
        if any(getattr(current, field) != getattr(job, field) for field in immutable):
            raise ValidationError("Identità immutabile del workflow job modificata")
        saved = replace(job, revision=current.revision + 1, updated_at=_now())
        _validate(saved)
        data = self._read()
        data["jobs"][saved.workflow_job_id] = asdict(saved)
        self._save(data)
        return saved


def approve_workflow_job(store: WorkflowJobStore, workflow_job_id: str, plan_fingerprint: str,
                         operator_role: str) -> WorkflowJob:
    job = store.get(workflow_job_id)
    if not operator_role.strip() or plan_fingerprint != job.plan_fingerprint:
        raise ValidationError("fingerprint approvazione non corrispondente")
    if job.approved_plan_fingerprint == plan_fingerprint:
        return job
    if job.state not in {"PROPOSED", "AWAITING_APPROVAL"}:
        raise ValidationError("approvazione non consentita nello stato corrente")
    return store.save(replace(job, approved_plan_fingerprint=plan_fingerprint, state="AWAITING_APPROVAL"), job.revision)


def transition_workflow_job(store: WorkflowJobStore, workflow_job_id: str, expected_revision: int,
                            next_state: str, evidence: dict[str, object], resume_state: str | None = None) -> WorkflowJob:
    job = store.get(workflow_job_id)
    if next_state not in STATES:
        raise ValidationError("stato richiesto non valido")
    allowed = {"PROPOSED": {"AWAITING_APPROVAL", "BLOCKED", "STALE"},
               "AWAITING_APPROVAL": {"EXECUTING", "REVIEW_READY", "BLOCKED", "STALE"},
               "EXECUTING": {"REVIEW_READY", "DELIVERY_AWAITING_APPROVAL", "CLOSED", "BLOCKED", "STALE", "FAILED_RECOVERABLE"},
               "REVIEW_READY": {"EXECUTING", "DELIVERY_AWAITING_APPROVAL", "CLOSED", "BLOCKED", "STALE"},
               "DELIVERY_AWAITING_APPROVAL": {"EXECUTING", "CLOSED", "BLOCKED", "STALE"},
               "BLOCKED": set(ACTIVE_STATES), "FAILED_RECOVERABLE": set(ACTIVE_STATES), "STALE": set(), "CLOSED": set()}
    if next_state != job.state and next_state not in allowed[job.state]:
        raise ValidationError("transizione workflow job non consentita")
    return store.save(replace(job, state=next_state, evidence=dict(evidence), resume_state=resume_state), expected_revision)
