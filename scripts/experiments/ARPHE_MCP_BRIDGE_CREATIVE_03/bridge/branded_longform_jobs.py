from __future__ import annotations

from dataclasses import dataclass
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


def new_branded_longform_job(project_name: str, original_timeline: str, source_fingerprint: str, profile_fingerprint: str) -> BrandedLongformJob:
    cleanup, editorial = derived_timeline_names(original_timeline)
    return BrandedLongformJob(str(uuid4()), project_name, original_timeline, cleanup, editorial, source_fingerprint, profile_fingerprint)


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
