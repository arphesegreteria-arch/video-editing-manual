from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import json
import os
from pathlib import Path
from uuid import uuid4

from .branded_longform_cleanup import derived_timeline_names


@dataclass(frozen=True)
class BrandedLongformJob:
    job_id: str
    project_name: str
    original_timeline: str
    cleanup_timeline: str
    editorial_timeline: str
    source_fingerprint: str
    profile_fingerprint: str
    state: str = "ANALYSED"
    workstation_id: str = "PC_PERSONALE"
    revision: int = 0
    proposal_card: dict | None = None
    approval: dict | None = None
    operations: tuple[dict, ...] = ()
    profile_id: str = "ARPHE_LONGFORM_EDITORIAL"


def new_branded_longform_job(project_name: str, original_timeline: str, source_fingerprint: str,
                             profile_fingerprint: str, workstation_id: str = "PC_PERSONALE",
                             profile_id: str = "ARPHE_LONGFORM_EDITORIAL") -> BrandedLongformJob:
    cleanup, editorial = derived_timeline_names(original_timeline)
    return BrandedLongformJob(str(uuid4()), project_name, original_timeline, cleanup, editorial,
                              source_fingerprint, profile_fingerprint, workstation_id=workstation_id,
                              profile_id=profile_id)


def verify_job_binding(job: BrandedLongformJob, project_name: str, original_timeline: str,
                       source_fingerprint: str, profile_fingerprint: str) -> None:
    if job.project_name != project_name:
        raise ValueError("Progetto del job cambiato")
    if job.original_timeline != original_timeline:
        raise ValueError("Timeline originale cambiata")
    if job.source_fingerprint != source_fingerprint:
        raise ValueError("Fingerprint sorgente cambiata")
    if job.profile_fingerprint != profile_fingerprint:
        raise ValueError("Fingerprint profilo cambiata")


class BrandedLongformJobStore:
    def __init__(self, path: Path, workstation_id: str):
        self.path = path
        self.workstation_id = workstation_id
        if path.is_file() and self._read()["workstation_id"] != workstation_id:
            raise ValueError("Registro branded longform appartenente a un'altra workstation")

    def _read(self) -> dict:
        if not self.path.is_file():
            return {"schema": "ARPHE_BRANDED_LONGFORM_JOBS_V1", "workstation_id": self.workstation_id, "jobs": {}}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"Registro branded longform non leggibile: {exc}") from exc
        if (not isinstance(data, dict) or data.get("schema") != "ARPHE_BRANDED_LONGFORM_JOBS_V1"
                or not isinstance(data.get("jobs"), dict)):
            raise ValueError("Registro branded longform non valido")
        return data

    def _write(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False, sort_keys=True), encoding="utf-8")
        os.replace(temporary, self.path)

    @staticmethod
    def _decode(raw: dict) -> BrandedLongformJob:
        payload = dict(raw)
        payload["operations"] = tuple(dict(item) for item in payload.get("operations", []))
        return BrandedLongformJob(**payload)

    def create(self, job: BrandedLongformJob) -> BrandedLongformJob:
        if job.workstation_id != self.workstation_id:
            raise ValueError("Job di un'altra workstation")
        data = self._read()
        existing = data["jobs"].get(job.job_id)
        if existing is not None:
            decoded = self._decode(existing)
            if decoded != job:
                raise ValueError("job_id esistente con contenuto differente")
            return decoded
        data["jobs"][job.job_id] = asdict(job)
        self._write(data)
        return job

    def get(self, job_id: str) -> BrandedLongformJob:
        raw = self._read()["jobs"].get(job_id)
        if raw is None:
            raise ValueError("Job branded longform non trovato")
        job = self._decode(raw)
        if job.workstation_id != self.workstation_id:
            raise ValueError("Job di un'altra workstation")
        return job

    def update(self, job: BrandedLongformJob, expected_revision: int) -> BrandedLongformJob:
        data = self._read()
        raw = data["jobs"].get(job.job_id)
        if raw is None:
            raise ValueError("Job branded longform non trovato")
        current = self._decode(raw)
        if current.revision != expected_revision:
            raise ValueError("revision branded longform stale")
        immutable = ("job_id", "workstation_id", "project_name", "original_timeline",
                     "cleanup_timeline", "editorial_timeline", "source_fingerprint",
                     "profile_fingerprint", "profile_id")
        if any(getattr(current, name) != getattr(job, name) for name in immutable):
            raise ValueError("Identità immutabile del job modificata")
        saved = replace(job, revision=current.revision + 1)
        data["jobs"][saved.job_id] = asdict(saved)
        self._write(data)
        return saved
