from __future__ import annotations

from dataclasses import replace
from typing import Any

from .carabellese_apply import read_carabellese_journal
from .carabellese_checkpoint import (
    restore_timeline_checkpoint,
    timeline_content_fingerprint,
    verify_timeline_checkpoint,
)
from .carabellese_jobs import CarabelleseJob, CarabelleseJobStore
from .carabellese_markers import cleanup_carabellese_markers
from .config import CreativeConfig
from .editorial_markers import timeline_identity
from .resolve_connection import RESOLVE_ACCESS_LOCK
from .safety import ValidationError


def _call(target: object, method: str, *args: object) -> Any:
    function = getattr(target, method, None)
    if not callable(function):
        raise ValidationError(f"API recovery Carabellese non supportata: {method}")
    try:
        return function(*args)
    except Exception as exc:
        raise ValidationError(f"Resolve {method} fallita: {exc}") from exc


def _failed_fingerprint(job: CarabelleseJob, config: CreativeConfig) -> str:
    failures = [event for event in read_carabellese_journal(config, job.carabellese_job_id)
                if event.get("schema") == "ARPHE_CARABELLESE_JOURNAL_V1"
                and event.get("status") == "FAILED"]
    operations = [operation for operation in job.operations
                  if operation.get("operation") == "apply"
                  and operation.get("status") == "FAILED"]
    if not failures or not operations:
        raise ValidationError("Evidenza di failure Carabellese assente")
    journal_value = failures[-1].get("timeline_fingerprint")
    operation_value = operations[-1].get("timeline_fingerprint_at_failure")
    if not isinstance(journal_value, str) or journal_value != operation_value:
        raise ValidationError("Journal e job discordano sulla timeline fallita")
    return journal_value


def recover_carabellese_cleanup(resolve: object, manager: object, config: CreativeConfig,
                                 store: CarabelleseJobStore, job_id: str) -> CarabelleseJob:
    with RESOLVE_ACCESS_LOCK:
        job = store.get(job_id, config.workstation_id)
        if job.state != "FAILED_RECOVERABLE":
            raise ValidationError("Il recovery richiede un job FAILED_RECOVERABLE")
        verify_timeline_checkpoint(job)
        expected_failed = _failed_fingerprint(job, config)
        project = _call(manager, "GetCurrentProject")
        timeline = _call(project, "GetCurrentTimeline")
        if (_call(project, "GetName") != job.project_name
                or _call(timeline, "GetName") != job.timeline_name
                or timeline_identity(timeline) != job.timeline_identity):
            raise ValidationError("Target recovery diverso dal job Carabellese")
        if timeline_content_fingerprint(timeline) != expected_failed:
            raise ValidationError("Timeline cambiata dopo la failure: recovery bloccato")
        restored = restore_timeline_checkpoint(resolve, project, store, job)
        operation = restored.operations[-1]
        restored_identity = operation.get("restored_timeline_identity")
        if not isinstance(restored_identity, str) or not restored_identity:
            raise ValidationError("Restore privo della nuova identità timeline")
        return store.save(replace(restored, state="CHECKPOINTED", resume_state=None,
                                  timeline_identity=restored_identity), restored.revision)


def close_carabellese_cleanup(timeline: object, store: CarabelleseJobStore,
                              job: CarabelleseJob) -> CarabelleseJob:
    with RESOLVE_ACCESS_LOCK:
        current = store.get(job.carabellese_job_id, job.workstation_id)
        if current != job:
            raise ValidationError("Job Carabellese stale durante la chiusura")
        if current.state != "VERIFIED":
            raise ValidationError("La chiusura richiede un job VERIFIED")
        verify_timeline_checkpoint(current)
        if timeline_identity(timeline) != current.timeline_identity:
            raise ValidationError("Timeline di chiusura diversa dal job")
        cleanup = cleanup_carabellese_markers(timeline, current)
        operation = {
            "operation": "close_cleanup",
            "status": "VERIFIED",
            "markers_removed": cleanup["removed"],
            "foreign_markers_preserved": cleanup["foreign_preserved"],
            "checkpoint_retained": True,
            "checkpoint_sha256": current.checkpoint_fingerprint,
            "checkpoint_size_bytes": current.checkpoint_manifest["size_bytes"],
        }
        return store.save(replace(current, state="CLOSED",
                                  operations=current.operations + (operation,)), current.revision)
