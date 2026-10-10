from __future__ import annotations

from typing import Any

from .control_plane import WorkflowJob, WorkflowJobStore, transition_workflow_job
from .safety import ValidationError


_REVIEW_STATES = {"MARKED", "REVIEWED", "VERIFIED", "CUT", "APPLYING", "CHECKPOINTED", "ANALYSED", "APPROVED"}
_RECOVERABLE = {"BLOCKED", "FAILED_RECOVERABLE"}


def native_binding(job: WorkflowJob, native: object) -> dict[str, object]:
    if getattr(native, "workstation_id", None) != job.workstation_id:
        raise ValidationError("workstation nativa non corrispondente")
    project = getattr(native, "project_name", None) or (getattr(native, "target", {}) or {}).get("project")
    timeline = (getattr(native, "timeline_name", None) or getattr(native, "original_timeline", None)
                or (getattr(native, "target", {}) or {}).get("timeline"))
    if project != job.target.get("project_name") or timeline != job.target.get("timeline_name"):
        raise ValidationError("target nativo non corrispondente")
    state = str(getattr(native, "state", ""))
    fingerprint = (getattr(native, "candidate_fingerprint", None) or getattr(native, "proposal_fingerprint", None)
                   or getattr(native, "source_fingerprint", None))
    return {"state": state, "fingerprint": fingerprint, "project_name": project, "timeline_name": timeline}


def next_safe_action(workflow_family: str, native_state: str, approved: bool) -> str:
    if native_state in _RECOVERABLE:
        return "RESUME" if approved else "APPROVE_PLAN"
    if native_state == "MARKED":
        return "SUBMIT_REVIEW"
    if native_state in {"ANALYZED", "ANALYSED", "PROPOSED"}:
        return "APPROVE_PLAN" if not approved else "EXECUTE"
    if native_state in {"REVIEWED", "CHECKPOINTED", "APPROVED"}:
        return "EXECUTE" if approved else "APPROVE_PLAN"
    return "NONE"


def workflow_job_card(job: WorkflowJob, native: object) -> dict[str, object]:
    binding = native_binding(job, native)
    native_state = str(binding["state"])
    if native_state in _RECOVERABLE:
        state = native_state
    elif native_state in _REVIEW_STATES:
        state = "REVIEW_READY"
    else:
        state = job.state
    return {"workflow_job_id": job.workflow_job_id, "workflow_family": job.workflow_family,
            "state": state, "native_reference": job.native_reference,
            "next_safe_action": next_safe_action(job.workflow_family, native_state,
                                                   job.approved_plan_fingerprint is not None),
            "target": dict(job.target), "native_fingerprint": binding["fingerprint"]}


def advance_workflow_job(store: WorkflowJobStore, workflow_job_id: str,
                         approved_plan_fingerprint: str, delegate: object) -> dict[str, object]:
    """Execute one already-approved typed adapter action exactly once.

    The server supplies a private typed delegate after it has revalidated Resolve context.
    Keeping the callback explicit makes the idempotency boundary testable without Resolve.
    """
    job = store.get(workflow_job_id)
    if job.approved_plan_fingerprint != approved_plan_fingerprint:
        raise ValidationError("approvazione del piano non corrispondente")
    if job.state in {"REVIEW_READY", "DELIVERY_AWAITING_APPROVAL", "CLOSED"}:
        return {"workflow_job_id": job.workflow_job_id, "state": job.state,
                "next_safe_action": "NONE", "evidence": dict(job.evidence)}
    if job.state not in {"AWAITING_APPROVAL", "FAILED_RECOVERABLE", "BLOCKED"}:
        raise ValidationError("avanzamento non consentito nello stato corrente")
    executing = transition_workflow_job(store, job.workflow_job_id, job.revision, "EXECUTING", {}, None)
    try:
        if not callable(delegate):
            raise ValidationError("delegate workflow non valido")
        evidence = delegate()
        if not isinstance(evidence, dict):
            raise ValidationError("evidence nativa non valida")
        finished = transition_workflow_job(store, executing.workflow_job_id, executing.revision,
                                           "REVIEW_READY", evidence, None)
        return {"workflow_job_id": finished.workflow_job_id, "state": finished.state,
                "next_safe_action": "NONE", "evidence": dict(finished.evidence)}
    except Exception as exc:
        failed = transition_workflow_job(store, executing.workflow_job_id, executing.revision,
                                         "FAILED_RECOVERABLE", {"error_type": type(exc).__name__},
                                         "AWAITING_APPROVAL")
        if isinstance(exc, ValidationError):
            raise exc
        return {"workflow_job_id": failed.workflow_job_id, "state": failed.state,
                "next_safe_action": "RESUME", "evidence": dict(failed.evidence)}
