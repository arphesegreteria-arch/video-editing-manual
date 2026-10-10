from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Mapping, Sequence
from uuid import uuid4

from .carabellese_contract import WORKFLOW_ID
from .safety import ValidationError


SCHEMA = "ARPHE_CARABELLESE_JOBS_V1"
JOB_ID = re.compile(r"^carabellese_[0-9a-f]{16}$")
WORKSTATION_ID = re.compile(r"^PC_[A-Z0-9_]{2,48}$")
FINGERPRINT = re.compile(r"^[0-9a-f]{64}$")
JOB_STATES = frozenset({
    "ANALYZED", "MARKED", "REVIEWED", "CHECKPOINTED", "APPLYING", "VERIFIED",
    "FAILED_RECOVERABLE", "BLOCKED", "STALE", "CLOSED",
})
NORMAL_NEXT = {
    "ANALYZED": "MARKED",
    "MARKED": "REVIEWED",
    "REVIEWED": "CHECKPOINTED",
    "CHECKPOINTED": "APPLYING",
    "APPLYING": "VERIFIED",
    "VERIFIED": "CLOSED",
}
TERMINAL = frozenset({"CLOSED", "STALE"})


@dataclass(frozen=True)
class CarabelleseJob:
    carabellese_job_id: str
    workstation_id: str
    workflow_id: str
    workflow_version: int
    state: str
    revision: int
    project_name: str
    timeline_name: str
    timeline_identity: str
    timeline_fingerprint: str
    source_fingerprint: str
    transcript_fingerprint: str
    contract_fingerprint: str
    proposal_fingerprint: str
    review_fingerprint: str | None
    checkpoint_fingerprint: str | None
    checkpoint_manifest: dict[str, object] | None
    resume_state: str | None
    candidates: tuple[dict[str, object], ...]
    decisions: tuple[dict[str, object], ...]
    markers: tuple[dict[str, object], ...]
    operations: tuple[dict[str, object], ...]
    state_timestamps: dict[str, str]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def new_carabellese_job(
    *, workstation_id: str, workflow_version: int, project_name: str, timeline_name: str,
    timeline_identity: str, timeline_fingerprint: str, source_fingerprint: str,
    transcript_fingerprint: str, contract_fingerprint: str, proposal_fingerprint: str,
    candidates: Sequence[Mapping[str, object]],
) -> CarabelleseJob:
    created = _now()
    result = CarabelleseJob(
        carabellese_job_id="carabellese_" + uuid4().hex[:16],
        workstation_id=workstation_id,
        workflow_id=WORKFLOW_ID,
        workflow_version=workflow_version,
        state="ANALYZED",
        revision=0,
        project_name=project_name,
        timeline_name=timeline_name,
        timeline_identity=timeline_identity,
        timeline_fingerprint=timeline_fingerprint,
        source_fingerprint=source_fingerprint,
        transcript_fingerprint=transcript_fingerprint,
        contract_fingerprint=contract_fingerprint,
        proposal_fingerprint=proposal_fingerprint,
        review_fingerprint=None,
        checkpoint_fingerprint=None,
        checkpoint_manifest=None,
        resume_state=None,
        candidates=tuple(dict(item) for item in candidates),
        decisions=(),
        markers=(),
        operations=(),
        state_timestamps={"ANALYZED": created},
    )
    _validate_job(result)
    return result


def _validate_records(name: str, records: object, *, required: bool = False) -> None:
    if not isinstance(records, tuple) or any(not isinstance(item, dict) for item in records):
        raise ValidationError(f"{name} Carabellese non validi")
    if required and not records:
        raise ValidationError(f"Il job richiede almeno un {name}")


def _validate_job(job: CarabelleseJob) -> None:
    if not JOB_ID.fullmatch(job.carabellese_job_id):
        raise ValidationError("carabellese_job_id non valido")
    if not WORKSTATION_ID.fullmatch(job.workstation_id):
        raise ValidationError("workstation_id Carabellese non valido")
    if job.workflow_id != WORKFLOW_ID or isinstance(job.workflow_version, bool) \
            or not isinstance(job.workflow_version, int) or job.workflow_version < 1:
        raise ValidationError("Workflow Carabellese non supportato")
    if job.state not in JOB_STATES:
        raise ValidationError("Stato Carabellese non valido")
    if isinstance(job.revision, bool) or not isinstance(job.revision, int) or job.revision < 0:
        raise ValidationError("Revision Carabellese non valida")
    for name in ("project_name", "timeline_name", "timeline_identity"):
        value = getattr(job, name)
        if not isinstance(value, str) or not value.strip():
            raise ValidationError(f"{name} richiesto")
    for name in (
        "timeline_fingerprint", "source_fingerprint", "transcript_fingerprint",
        "contract_fingerprint", "proposal_fingerprint",
    ):
        value = getattr(job, name)
        if not isinstance(value, str) or not FINGERPRINT.fullmatch(value):
            raise ValidationError(f"{name} non valido")
    for name in ("review_fingerprint", "checkpoint_fingerprint"):
        value = getattr(job, name)
        if value is not None and (not isinstance(value, str) or not FINGERPRINT.fullmatch(value)):
            raise ValidationError(f"{name} non valido")
    if (job.checkpoint_fingerprint is None) != (job.checkpoint_manifest is None):
        raise ValidationError("Fingerprint e manifest del checkpoint devono essere entrambi presenti")
    if job.checkpoint_manifest is not None and not isinstance(job.checkpoint_manifest, dict):
        raise ValidationError("checkpoint_manifest non valido")
    evidence_state = job.resume_state if job.state in {"BLOCKED", "FAILED_RECOVERABLE"} else job.state
    if evidence_state in {"REVIEWED", "CHECKPOINTED", "APPLYING", "VERIFIED", "CLOSED"} \
            and job.review_fingerprint is None:
        raise ValidationError("review_fingerprint richiesto dallo stato del job")
    if evidence_state in {"CHECKPOINTED", "APPLYING", "VERIFIED", "CLOSED"} \
            and job.checkpoint_fingerprint is None:
        raise ValidationError("checkpoint richiesto dallo stato del job")
    _validate_records("candidate", job.candidates, required=True)
    _validate_records("decisioni", job.decisions)
    _validate_records("marker", job.markers)
    _validate_records("operazioni", job.operations)
    if job.state == "BLOCKED":
        if job.resume_state not in {"ANALYZED", "MARKED", "REVIEWED", "CHECKPOINTED", "APPLYING", "VERIFIED"}:
            raise ValidationError("Un job BLOCKED richiede un resume_state attivo")
    elif job.state == "FAILED_RECOVERABLE":
        if job.resume_state not in {"CHECKPOINTED", "APPLYING"}:
            raise ValidationError("FAILED_RECOVERABLE richiede lo stadio interrotto")
    elif job.resume_state is not None:
        raise ValidationError("resume_state consentito solo per stati recuperabili")
    if not isinstance(job.state_timestamps, dict) or "ANALYZED" not in job.state_timestamps:
        raise ValidationError("Timeline stati Carabellese incompleta")
    if any(not isinstance(key, str) or key not in JOB_STATES or not isinstance(value, str)
           or not value for key, value in job.state_timestamps.items()):
        raise ValidationError("Timestamp stati Carabellese non validi")


def _job_payload(job: CarabelleseJob) -> dict[str, Any]:
    return asdict(job)


def _job_from_payload(raw: object) -> CarabelleseJob:
    if not isinstance(raw, dict) or set(raw) != set(CarabelleseJob.__dataclass_fields__):
        raise ValidationError("Record job Carabellese non valido")
    try:
        result = CarabelleseJob(
            carabellese_job_id=raw["carabellese_job_id"],
            workstation_id=raw["workstation_id"],
            workflow_id=raw["workflow_id"],
            workflow_version=raw["workflow_version"],
            state=raw["state"],
            revision=raw["revision"],
            project_name=raw["project_name"],
            timeline_name=raw["timeline_name"],
            timeline_identity=raw["timeline_identity"],
            timeline_fingerprint=raw["timeline_fingerprint"],
            source_fingerprint=raw["source_fingerprint"],
            transcript_fingerprint=raw["transcript_fingerprint"],
            contract_fingerprint=raw["contract_fingerprint"],
            proposal_fingerprint=raw["proposal_fingerprint"],
            review_fingerprint=raw["review_fingerprint"],
            checkpoint_fingerprint=raw["checkpoint_fingerprint"],
            checkpoint_manifest=None if raw["checkpoint_manifest"] is None
            else dict(raw["checkpoint_manifest"]),
            resume_state=raw["resume_state"],
            candidates=tuple(dict(item) for item in raw["candidates"]),
            decisions=tuple(dict(item) for item in raw["decisions"]),
            markers=tuple(dict(item) for item in raw["markers"]),
            operations=tuple(dict(item) for item in raw["operations"]),
            state_timestamps=dict(raw["state_timestamps"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValidationError(f"Record job Carabellese malformato: {exc}") from exc
    _validate_job(result)
    return result


def _validate_transition(current: CarabelleseJob, requested: CarabelleseJob) -> None:
    if current.state in TERMINAL and requested.state != current.state:
        raise ValidationError(f"Stato terminale {current.state}")
    if requested.state == current.state:
        return
    if current.state == "BLOCKED":
        if requested.state != current.resume_state or requested.resume_state is not None:
            raise ValidationError("BLOCKED può tornare soltanto al resume_state registrato")
        return
    if current.state == "FAILED_RECOVERABLE":
        if requested.state == "CHECKPOINTED" and requested.resume_state is None:
            operation = requested.operations[-1] if requested.operations else {}
            if (operation.get("operation") != "restore_checkpoint"
                    or operation.get("status") != "VERIFIED"):
                raise ValidationError("Il ritorno a CHECKPOINTED richiede un restore verificato")
            return
        if requested.state != current.resume_state or requested.resume_state is not None:
            raise ValidationError("FAILED_RECOVERABLE può soltanto riprendere lo stadio interrotto")
        return
    if requested.state == "STALE":
        return
    if requested.state == "BLOCKED":
        if requested.resume_state != current.state:
            raise ValidationError("BLOCKED deve registrare lo stato di ripresa")
        return
    if requested.state == "FAILED_RECOVERABLE":
        if current.state not in {"CHECKPOINTED", "APPLYING"} or requested.resume_state != current.state:
            raise ValidationError("FAILED_RECOVERABLE consentito soltanto durante l'applicazione")
        return
    if NORMAL_NEXT.get(current.state) != requested.state:
        raise ValidationError(f"Transizione non consentita: {current.state}->{requested.state}")


class CarabelleseJobStore:
    def __init__(self, path: Path, workstation_id: str):
        if not WORKSTATION_ID.fullmatch(workstation_id):
            raise ValidationError("workstation_id store Carabellese non valido")
        self.path = path
        self.workstation_id = workstation_id

    def _load(self) -> dict[str, Any]:
        if not self.path.is_file():
            return {"schema": SCHEMA, "workstation_id": self.workstation_id, "jobs": {}}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValidationError(f"Registry job Carabellese non leggibile: {exc}") from exc
        if not isinstance(data, dict) or set(data) != {"schema", "workstation_id", "jobs"}:
            raise ValidationError("Registry job Carabellese malformato")
        if data["schema"] != SCHEMA:
            raise ValidationError("Schema registry job Carabellese non supportato")
        if data["workstation_id"] != self.workstation_id:
            raise ValidationError("Registry job Carabellese appartenente a un altro workstation")
        if not isinstance(data["jobs"], dict):
            raise ValidationError("Jobs registry Carabellese non validi")
        for key, raw in data["jobs"].items():
            loaded = _job_from_payload(raw)
            if key != loaded.carabellese_job_id or loaded.workstation_id != self.workstation_id:
                raise ValidationError("Identità job/workstation Carabellese incoerente")
        return data

    def _save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(
            prefix=self.path.name + ".", dir=str(self.path.parent), text=True
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def create(self, job: CarabelleseJob) -> CarabelleseJob:
        _validate_job(job)
        if job.workstation_id != self.workstation_id:
            raise ValidationError("Nuovo job appartenente a un altro workstation")
        if job.state != "ANALYZED" or job.revision != 0:
            raise ValidationError("Nuovo job non è ANALYZED/revision 0")
        data = self._load()
        existing = data["jobs"].get(job.carabellese_job_id)
        if existing is not None:
            loaded = _job_from_payload(existing)
            if replace(loaded, revision=0) == job:
                return loaded
            raise ValidationError("carabellese_job_id già esistente")
        for raw in data["jobs"].values():
            active = _job_from_payload(raw)
            if active.timeline_identity == job.timeline_identity and active.state not in TERMINAL:
                raise ValidationError("Un altro job Carabellese è già attivo sulla timeline")
        created = replace(job, revision=1)
        data["jobs"][created.carabellese_job_id] = _job_payload(created)
        self._save(data)
        return created

    def get(self, job_id: str, workstation_id: str) -> CarabelleseJob:
        if workstation_id != self.workstation_id:
            raise ValidationError("Richiesta job da workstation differente")
        data = self._load()
        raw = data["jobs"].get(job_id)
        if raw is None:
            raise ValidationError("Job Carabellese non trovato")
        return _job_from_payload(raw)

    def save(self, job: CarabelleseJob, expected_revision: int) -> CarabelleseJob:
        _validate_job(job)
        if job.workstation_id != self.workstation_id:
            raise ValidationError("Job appartenente a un altro workstation")
        data = self._load()
        raw = data["jobs"].get(job.carabellese_job_id)
        if raw is None:
            raise ValidationError("Job Carabellese non trovato")
        current = _job_from_payload(raw)
        if job == current:
            return current
        if current.revision != expected_revision:
            raise ValidationError("Revision job Carabellese stale")
        if job.revision != current.revision:
            raise ValidationError("Il chiamante non può impostare revision")
        immutable = (
            "carabellese_job_id", "workstation_id", "workflow_id", "workflow_version",
            "project_name", "timeline_name", "timeline_fingerprint",
            "source_fingerprint", "transcript_fingerprint", "contract_fingerprint",
            "proposal_fingerprint", "candidates",
        )
        if any(getattr(job, name) != getattr(current, name) for name in immutable):
            raise ValidationError("Identità o evidenza immutabile del job modificata")
        if job.timeline_identity != current.timeline_identity:
            operation = job.operations[-1] if job.operations else {}
            identity_restored = (
                current.state == "FAILED_RECOVERABLE"
                and job.state == "CHECKPOINTED"
                and job.resume_state is None
                and operation.get("operation") == "restore_checkpoint"
                and operation.get("status") == "VERIFIED"
                and operation.get("previous_timeline_identity") == current.timeline_identity
                and operation.get("restored_timeline_identity") == job.timeline_identity
            )
            if not identity_restored:
                raise ValidationError("Identità timeline immutabile senza restore verificato")
        _validate_transition(current, job)
        timestamps = dict(current.state_timestamps)
        if job.state != current.state:
            timestamps[job.state] = _now()
        saved = replace(job, revision=current.revision + 1, state_timestamps=timestamps)
        _validate_job(saved)
        data["jobs"][saved.carabellese_job_id] = _job_payload(saved)
        self._save(data)
        return saved

    def active_for_timeline(self, timeline_identity: str) -> CarabelleseJob | None:
        data = self._load()
        active = [
            _job_from_payload(raw)
            for raw in data["jobs"].values()
            if raw.get("timeline_identity") == timeline_identity and raw.get("state") not in TERMINAL
        ]
        if len(active) > 1:
            raise ValidationError("Registry incoerente: più job Carabellese attivi sulla timeline")
        return active[0] if active else None
