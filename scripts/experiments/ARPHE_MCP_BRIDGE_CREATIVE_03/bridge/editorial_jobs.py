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

from .safety import ValidationError


SCHEMA = "ARPHE_EDITORIAL_JOBS_V1"
WORKFLOW_ID = "ARPHE_PODCAST_REELS_CTA"
JOB_ID = re.compile(r"^editorial_[0-9a-f]{16}$")
FINGERPRINT = re.compile(r"^[0-9a-f]{64}$")
JOB_STATES = frozenset({
    "ANALYZED", "MARKED", "REVIEWED", "CUT", "VERIFIED", "CLOSED",
    "STALE", "BLOCKED", "FAILED_RECOVERABLE",
})
NORMAL_NEXT = {
    "ANALYZED": "MARKED",
    "MARKED": "REVIEWED",
    "REVIEWED": "CUT",
    "CUT": "VERIFIED",
    "VERIFIED": "CLOSED",
}
TERMINAL = {"CLOSED", "STALE"}


@dataclass(frozen=True)
class EditorialJob:
    editorial_job_id: str
    workstation_id: str
    workflow_id: str
    workflow_version: int
    state: str
    revision: int
    project_name: str
    timeline_name: str
    timeline_identity: str
    source_fingerprint: str
    transcript_fingerprint: str
    candidate_fingerprint: str
    review_fingerprint: str | None
    resume_state: str | None
    candidates: tuple[dict[str, object], ...]
    markers: tuple[dict[str, object], ...]
    decisions: tuple[dict[str, object], ...]
    operations: tuple[dict[str, object], ...]
    state_timestamps: dict[str, str]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def new_editorial_job(*, workstation_id: str, workflow_version: int, project_name: str,
                      timeline_name: str, timeline_identity: str, source_fingerprint: str,
                      transcript_fingerprint: str, candidate_fingerprint: str,
                      candidates: Sequence[Mapping[str, object]]) -> EditorialJob:
    created = _now()
    job = EditorialJob(
        editorial_job_id="editorial_" + uuid4().hex[:16],
        workstation_id=workstation_id,
        workflow_id=WORKFLOW_ID,
        workflow_version=workflow_version,
        state="ANALYZED",
        revision=0,
        project_name=project_name,
        timeline_name=timeline_name,
        timeline_identity=timeline_identity,
        source_fingerprint=source_fingerprint,
        transcript_fingerprint=transcript_fingerprint,
        candidate_fingerprint=candidate_fingerprint,
        review_fingerprint=None,
        resume_state=None,
        candidates=tuple(dict(item) for item in candidates),
        markers=(),
        decisions=(),
        operations=(),
        state_timestamps={"ANALYZED": created},
    )
    _validate_job(job)
    return job


def _validate_job(job: EditorialJob) -> None:
    if not JOB_ID.fullmatch(job.editorial_job_id):
        raise ValidationError("editorial_job_id non valido")
    if not re.fullmatch(r"PC_[A-Z0-9_]{2,48}", job.workstation_id):
        raise ValidationError("workstation_id editoriale non valido")
    if job.workflow_id != WORKFLOW_ID or job.workflow_version < 1:
        raise ValidationError("Workflow editoriale non supportato")
    if job.state not in JOB_STATES:
        raise ValidationError("Stato editoriale non valido")
    if isinstance(job.revision, bool) or not isinstance(job.revision, int) or job.revision < 0:
        raise ValidationError("Revision editoriale non valida")
    for name in ("project_name", "timeline_name", "timeline_identity"):
        if not isinstance(getattr(job, name), str) or not getattr(job, name).strip():
            raise ValidationError(f"{name} richiesto")
    for name in ("source_fingerprint", "transcript_fingerprint", "candidate_fingerprint"):
        if not FINGERPRINT.fullmatch(getattr(job, name)):
            raise ValidationError(f"{name} non valido")
    if job.review_fingerprint is not None and not FINGERPRINT.fullmatch(job.review_fingerprint):
        raise ValidationError("review_fingerprint non valido")
    if job.resume_state is not None and job.resume_state not in JOB_STATES - {"BLOCKED", "STALE", "CLOSED"}:
        raise ValidationError("resume_state non valido")
    if job.state == "BLOCKED" and job.resume_state is None:
        raise ValidationError("Un job BLOCKED richiede resume_state")
    if job.state not in {"BLOCKED", "FAILED_RECOVERABLE"} and job.resume_state is not None:
        raise ValidationError("resume_state consentito solo per stati recuperabili")
    if not job.candidates:
        raise ValidationError("Il job richiede almeno un candidate")
    if not isinstance(job.state_timestamps, dict) or "ANALYZED" not in job.state_timestamps:
        raise ValidationError("Timeline stati editoriale incompleta")


def _job_payload(job: EditorialJob) -> dict[str, Any]:
    return asdict(job)


def _job_from_payload(raw: object) -> EditorialJob:
    if not isinstance(raw, dict):
        raise ValidationError("Record job editoriale non valido")
    expected = set(EditorialJob.__dataclass_fields__)
    if set(raw) != expected:
        raise ValidationError("Campi job editoriale non validi")
    try:
        job = EditorialJob(
            editorial_job_id=str(raw["editorial_job_id"]),
            workstation_id=str(raw["workstation_id"]),
            workflow_id=str(raw["workflow_id"]),
            workflow_version=int(raw["workflow_version"]),
            state=str(raw["state"]),
            revision=int(raw["revision"]),
            project_name=str(raw["project_name"]),
            timeline_name=str(raw["timeline_name"]),
            timeline_identity=str(raw["timeline_identity"]),
            source_fingerprint=str(raw["source_fingerprint"]),
            transcript_fingerprint=str(raw["transcript_fingerprint"]),
            candidate_fingerprint=str(raw["candidate_fingerprint"]),
            review_fingerprint=None if raw["review_fingerprint"] is None else str(raw["review_fingerprint"]),
            resume_state=None if raw["resume_state"] is None else str(raw["resume_state"]),
            candidates=tuple(dict(item) for item in raw["candidates"]),
            markers=tuple(dict(item) for item in raw["markers"]),
            decisions=tuple(dict(item) for item in raw["decisions"]),
            operations=tuple(dict(item) for item in raw["operations"]),
            state_timestamps={str(key): str(value) for key, value in raw["state_timestamps"].items()},
        )
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise ValidationError(f"Record job editoriale malformato: {exc}") from exc
    _validate_job(job)
    return job


def _validate_transition(current: EditorialJob, requested: EditorialJob) -> None:
    if current.state in TERMINAL and requested.state != current.state:
        raise ValidationError(f"Stato terminale {current.state}")
    if requested.state == current.state:
        return
    if current.state == "BLOCKED":
        if requested.state != current.resume_state or requested.resume_state is not None:
            raise ValidationError("BLOCKED può tornare soltanto al resume_state registrato")
        return
    if current.state == "FAILED_RECOVERABLE":
        if requested.state not in {"CUT", "FAILED_RECOVERABLE", "BLOCKED", "STALE"}:
            raise ValidationError("FAILED_RECOVERABLE può solo riprendere il cut")
        return
    if requested.state == "STALE":
        return
    if requested.state == "BLOCKED":
        if requested.resume_state != current.state:
            raise ValidationError("BLOCKED deve registrare lo stato di ripresa")
        return
    if requested.state == "FAILED_RECOVERABLE":
        if current.state not in {"REVIEWED", "CUT"} or requested.resume_state not in {"REVIEWED", "CUT"}:
            raise ValidationError("FAILED_RECOVERABLE consentito soltanto durante il cut")
        return
    if NORMAL_NEXT.get(current.state) != requested.state:
        raise ValidationError(f"Transizione non consentita: {current.state}->{requested.state}")


class EditorialJobStore:
    def __init__(self, path: Path, workstation_id: str):
        if not re.fullmatch(r"PC_[A-Z0-9_]{2,48}", workstation_id):
            raise ValidationError("workstation_id store non valido")
        self.path = path
        self.workstation_id = workstation_id

    def _load(self) -> dict[str, Any]:
        if not self.path.is_file():
            return {"schema": SCHEMA, "workstation_id": self.workstation_id, "jobs": {}}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValidationError(f"Registry job editoriale non leggibile: {exc}") from exc
        if not isinstance(data, dict) or set(data) != {"schema", "workstation_id", "jobs"}:
            raise ValidationError("Registry job editoriale malformato")
        if data["schema"] != SCHEMA:
            raise ValidationError("Schema registry job editoriale non supportato")
        if data["workstation_id"] != self.workstation_id:
            raise ValidationError("Registry job editoriale appartenente a un altro workstation")
        if not isinstance(data["jobs"], dict):
            raise ValidationError("Jobs registry non valido")
        for key, raw in data["jobs"].items():
            job = _job_from_payload(raw)
            if key != job.editorial_job_id or job.workstation_id != self.workstation_id:
                raise ValidationError("Identità job/workstation incoerente")
        return data

    def _save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=self.path.name + ".", dir=str(self.path.parent), text=True)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False, indent=2, sort_keys=True)
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def create(self, job: EditorialJob) -> EditorialJob:
        _validate_job(job)
        if job.workstation_id != self.workstation_id or job.state != "ANALYZED" or job.revision != 0:
            raise ValidationError("Nuovo job non appartiene allo store o non è ANALYZED/revision 0")
        data = self._load()
        existing = data["jobs"].get(job.editorial_job_id)
        if existing is not None:
            loaded = _job_from_payload(existing)
            if replace(loaded, revision=0) == job:
                return loaded
            raise ValidationError("editorial_job_id già esistente")
        created = replace(job, revision=1)
        data["jobs"][created.editorial_job_id] = _job_payload(created)
        self._save(data)
        return created

    def get(self, job_id: str, workstation_id: str) -> EditorialJob:
        if workstation_id != self.workstation_id:
            raise ValidationError("Richiesta job da workstation differente")
        data = self._load()
        raw = data["jobs"].get(job_id)
        if raw is None:
            raise ValidationError("Job editoriale non trovato")
        return _job_from_payload(raw)

    def _assert_marker_ownership(self, data: Mapping[str, Any], requested: EditorialJob) -> None:
        if not requested.markers or requested.state == "CLOSED":
            return
        for raw in data["jobs"].values():
            other = _job_from_payload(raw)
            if (other.editorial_job_id != requested.editorial_job_id
                    and other.timeline_identity == requested.timeline_identity
                    and other.markers and other.state != "CLOSED"):
                raise ValidationError("Un altro job non chiuso possiede marker sulla timeline")

    def save(self, job: EditorialJob, expected_revision: int) -> EditorialJob:
        _validate_job(job)
        if job.workstation_id != self.workstation_id:
            raise ValidationError("Job appartenente a un altro workstation")
        data = self._load()
        raw = data["jobs"].get(job.editorial_job_id)
        if raw is None:
            raise ValidationError("Job editoriale non trovato")
        current = _job_from_payload(raw)
        if job == current:
            return current
        if current.revision != expected_revision:
            raise ValidationError("Revision job editoriale stale")
        if job.revision != current.revision:
            raise ValidationError("Il chiamante non può impostare revision")
        immutable = (
            "editorial_job_id", "workstation_id", "workflow_id", "workflow_version",
            "project_name", "timeline_name", "timeline_identity", "source_fingerprint",
            "transcript_fingerprint", "candidate_fingerprint", "candidates",
        )
        if any(getattr(job, name) != getattr(current, name) for name in immutable):
            raise ValidationError("Identità immutabile del job modificata")
        _validate_transition(current, job)
        self._assert_marker_ownership(data, job)
        timestamps = dict(current.state_timestamps)
        if job.state != current.state:
            timestamps[job.state] = _now()
        saved = replace(job, revision=current.revision + 1, state_timestamps=timestamps)
        _validate_job(saved)
        data["jobs"][saved.editorial_job_id] = _job_payload(saved)
        self._save(data)
        return saved

    def active_for_timeline(self, timeline_identity: str) -> EditorialJob | None:
        data = self._load()
        active = [
            _job_from_payload(raw)
            for raw in data["jobs"].values()
            if raw.get("timeline_identity") == timeline_identity
            and raw.get("markers")
            and raw.get("state") != "CLOSED"
        ]
        if len(active) > 1:
            raise ValidationError("Registry incoerente: più job possiedono marker sulla timeline")
        return active[0] if active else None
