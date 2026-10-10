from __future__ import annotations

from dataclasses import asdict, replace
from typing import Any

from .branded_longform_apply import approve_proposal_batch
from .branded_longform_application_plan import build_application_plan
from .branded_longform_editorial import proposal_card, proposal_fingerprint, propose_editorial
from .branded_longform_jobs import BrandedLongformJob, BrandedLongformJobStore
from .safety import ValidationError


def propose_batch(store: BrandedLongformJobStore, job_id: str,
                  segments: list[dict[str, Any]]) -> BrandedLongformJob:
    job = store.get(job_id)
    if job.state not in {"ANALYSED", "PROPOSED"}:
        raise ValidationError("Il job non è nello stato di proposta")
    proposals = propose_editorial(segments, job.profile_id)
    card = proposal_card(job.job_id, proposals)
    card["fingerprint"] = proposal_fingerprint(card)
    if job.state == "PROPOSED" and job.proposal_card == card:
        return job
    return store.update(replace(job, state="PROPOSED", proposal_card=card, approval=None), job.revision)


def approve_batch(store: BrandedLongformJobStore, job_id: str, fingerprint: str,
                  decisions: list[dict[str, Any]], operator_role: str) -> BrandedLongformJob:
    job = store.get(job_id)
    if job.state not in {"PROPOSED", "APPROVED"} or not isinstance(job.proposal_card, dict):
        raise ValidationError("Il job non ha una proposta approvabile")
    expected = str(job.proposal_card.get("fingerprint", ""))
    if fingerprint != expected:
        raise ValidationError("fingerprint proposta non corrispondente")
    approved = approve_proposal_batch(fingerprint, decisions, operator_role)
    payload = {"proposal_fingerprint": approved.proposal_fingerprint,
               "approved_ids": list(approved.approved_ids), "modified": approved.modified,
               "operator_role": operator_role}
    if job.state == "APPROVED" and job.approval == payload:
        return job
    return store.update(replace(job, state="APPROVED", approval=payload), job.revision)


def application_for_job(job: BrandedLongformJob) -> tuple[dict[str, Any], ...]:
    if job.state not in {"APPROVED", "BLOCKED"} or not isinstance(job.proposal_card, dict) or not isinstance(job.approval, dict):
        raise ValidationError("Job branded longform non approvato")
    proposals = {str(item["proposal_id"]): dict(item) for item in job.proposal_card.get("proposals", [])}
    approved_ids = tuple(str(value) for value in job.approval.get("approved_ids", []))
    terminal = {str(item.get("proposal_id")) for item in job.operations
                if item.get("status") in {"VERIFIED", "BLOCKED"}}
    plan = [item for item in build_application_plan(proposals, approved_ids)
            if str(item.get("proposal_id")) not in terminal]
    for item in plan:
        replacement = job.approval.get("modified", {}).get(item["proposal_id"])
        if replacement:
            item["operator_modification"] = replacement
    return tuple(plan)
