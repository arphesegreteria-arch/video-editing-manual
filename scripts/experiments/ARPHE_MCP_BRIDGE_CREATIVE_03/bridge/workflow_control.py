from __future__ import annotations

import hashlib
import json
from typing import Any

from .control_plane import WorkflowJob, WorkflowJobStore, transition_workflow_job
from .editorial_jobs import EditorialJobStore
from .carabellese_jobs import CarabelleseJobStore
from .vertical_social_jobs import VerticalSocialPlanStore
from .branded_longform_jobs import BrandedLongformJobStore
from .safety import ValidationError


_REVIEW_STATES = {"MARKED", "REVIEWED", "VERIFIED", "CUT", "APPLYING", "CHECKPOINTED", "ANALYSED", "APPROVED"}
_RECOVERABLE = {"BLOCKED", "FAILED_RECOVERABLE"}


def _fingerprint_payload(value: object) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def native_plan_fingerprint(workflow_family: str, native: object) -> str:
    """Return the immutable native content fingerprint that the operator approves."""
    if workflow_family == "PODCAST_REELS":
        value = getattr(native, "review_fingerprint", None) or getattr(native, "candidate_fingerprint", None)
    elif workflow_family == "CARABELLESE_CLEANUP":
        value = getattr(native, "review_fingerprint", None) or getattr(native, "proposal_fingerprint", None)
    elif workflow_family == "BRANDED_LONGFORM":
        card = getattr(native, "proposal_card", None)
        proposal = card.get("fingerprint") if isinstance(card, dict) else None
        approval = getattr(native, "approval", None)
        value = _fingerprint_payload({
            "proposal_fingerprint": proposal,
            "approval": approval if isinstance(approval, dict) else None,
            "source_fingerprint": getattr(native, "source_fingerprint", None),
            "profile_fingerprint": getattr(native, "profile_fingerprint", None),
            "original_timeline_fingerprint": getattr(native, "original_timeline_fingerprint", None),
        }) if proposal else getattr(native, "source_fingerprint", None)
    elif workflow_family == "VERTICAL_SOCIAL":
        from .vertical_social_jobs import plan_fingerprint
        value = plan_fingerprint(native)
    else:
        raise ValidationError("workflow_family non supportato")
    if not isinstance(value, str) or len(value) != 64:
        raise ValidationError("fingerprint nativa non disponibile")
    return value


def control_plan_fingerprint(workstation_id: str, workflow_family: str, native_reference: str,
                             target: dict[str, object], native: object) -> str:
    payload = {"workstation_id": workstation_id, "workflow_family": workflow_family,
               "native_reference": native_reference, "target": target,
               "native_plan_fingerprint": native_plan_fingerprint(workflow_family, native)}
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def load_native_binding(config: object, workflow_family: str, native_reference: str) -> object:
    """Load exactly one existing, workstation-owned specialized record."""
    workstation_id = str(getattr(config, "workstation_id"))
    if workflow_family == "PODCAST_REELS":
        return EditorialJobStore(getattr(config, "editorial_jobs_path"), workstation_id).get(native_reference, workstation_id)
    if workflow_family == "CARABELLESE_CLEANUP":
        return CarabelleseJobStore(getattr(config, "carabellese_jobs_path"), workstation_id).get(native_reference, workstation_id)
    if workflow_family == "VERTICAL_SOCIAL":
        return VerticalSocialPlanStore(getattr(config, "vertical_social_plans_path"), workstation_id).get(native_reference)
    if workflow_family == "BRANDED_LONGFORM":
        return BrandedLongformJobStore(getattr(config, "branded_longform_jobs_path"), workstation_id).get(native_reference)
    raise ValidationError("workflow_family non supportato")


def native_binding(job: WorkflowJob, native: object) -> dict[str, object]:
    if getattr(native, "workstation_id", None) != job.workstation_id:
        raise ValidationError("workstation nativa non corrispondente")
    project = getattr(native, "project_name", None) or (getattr(native, "target", {}) or {}).get("project")
    timeline = (getattr(native, "timeline_name", None) or getattr(native, "original_timeline", None)
                or (getattr(native, "target", {}) or {}).get("timeline"))
    if project != job.target.get("project_name") or timeline != job.target.get("timeline_name"):
        raise ValidationError("target nativo non corrispondente")
    native_identity = getattr(native, "timeline_identity", None)
    expected_identity = job.target.get("timeline_identity")
    if expected_identity is not None and native_identity != expected_identity:
        raise ValidationError("identità timeline nativa non corrispondente")
    native_source = getattr(native, "source_fingerprint", None)
    expected_source = job.target.get("source_fingerprint")
    if expected_source is not None and native_source != expected_source:
        raise ValidationError("sorgente nativa non corrispondente")
    state = str(getattr(native, "state", ""))
    fingerprint = (getattr(native, "candidate_fingerprint", None) or getattr(native, "proposal_fingerprint", None)
                   or getattr(native, "source_fingerprint", None))
    return {"state": state, "fingerprint": fingerprint, "project_name": project, "timeline_name": timeline,
            "timeline_identity": native_identity, "source_fingerprint": native_source}


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
    current_fingerprint = control_plan_fingerprint(
        job.workstation_id, job.workflow_family, job.native_reference, job.target, native)
    stale = job.approved_plan_fingerprint is not None and current_fingerprint != job.plan_fingerprint
    if stale:
        state = "STALE"
    elif native_state in _RECOVERABLE:
        state = native_state
    elif native_state in _REVIEW_STATES:
        state = "REVIEW_READY"
    else:
        state = job.state
    action = ("PREPARE_NEW_PLAN" if stale else
              next_safe_action(job.workflow_family, native_state,
                               job.approved_plan_fingerprint is not None))
    return {"workflow_job_id": job.workflow_job_id, "workflow_family": job.workflow_family,
            "state": state, "native_reference": job.native_reference,
            "next_safe_action": action,
            "target": dict(job.target), "native_fingerprint": binding["fingerprint"]}


def advance_workflow_job(store: WorkflowJobStore, workflow_job_id: str,
                         approved_plan_fingerprint: str, delegate: object,
                         operation_key: str | None = None) -> dict[str, object]:
    """Execute one already-approved typed adapter action exactly once.

    The server supplies a private typed delegate after it has revalidated Resolve context.
    Keeping the callback explicit makes the idempotency boundary testable without Resolve.
    """
    job = store.get(workflow_job_id)
    if job.approved_plan_fingerprint != approved_plan_fingerprint:
        raise ValidationError("approvazione del piano non corrispondente")
    if job.state == "EXECUTING":
        recovered = transition_workflow_job(
            store, job.workflow_job_id, job.revision, "FAILED_RECOVERABLE",
            {"_operation_key": job.evidence.get("_operation_key"),
             "recovery": "interrupted_execution_requires_native_reconciliation"},
            "AWAITING_APPROVAL",
        )
        return {"workflow_job_id": recovered.workflow_job_id, "state": recovered.state,
                "next_safe_action": "RESUME", "evidence": dict(recovered.evidence)}
    recorded_key = job.evidence.get("_operation_key")
    if job.state == "CLOSED" or (job.state in {"REVIEW_READY", "DELIVERY_AWAITING_APPROVAL"}
                                 and operation_key is None) or (
            job.state in {"REVIEW_READY", "DELIVERY_AWAITING_APPROVAL"}
            and recorded_key == operation_key):
        return {"workflow_job_id": job.workflow_job_id, "state": job.state,
                "next_safe_action": "NONE", "evidence": dict(job.evidence)}
    if job.state not in {"AWAITING_APPROVAL", "REVIEW_READY", "DELIVERY_AWAITING_APPROVAL",
                          "FAILED_RECOVERABLE", "BLOCKED"}:
        raise ValidationError("avanzamento non consentito nello stato corrente")
    claim = {"_operation_key": operation_key} if operation_key is not None else {}
    executing = transition_workflow_job(store, job.workflow_job_id, job.revision, "EXECUTING", claim, None)
    try:
        if not callable(delegate):
            raise ValidationError("delegate workflow non valido")
        evidence = delegate()
        if not isinstance(evidence, dict):
            raise ValidationError("evidence nativa non valida")
        evidence = dict(evidence)
        if operation_key is not None:
            evidence["_operation_key"] = operation_key
        next_state = "CLOSED" if str(evidence.get("state")) == "CLOSED" else "REVIEW_READY"
        finished = transition_workflow_job(store, executing.workflow_job_id, executing.revision,
                                           next_state, evidence, None)
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
