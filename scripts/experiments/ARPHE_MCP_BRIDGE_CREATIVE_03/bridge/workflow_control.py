from __future__ import annotations

from typing import Any

from .control_plane import WorkflowJob
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
