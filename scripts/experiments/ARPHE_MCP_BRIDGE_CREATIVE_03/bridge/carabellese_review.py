from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from typing import Mapping, Sequence

from .carabellese_contract import (CarabelleseContract, carabellese_contract_fingerprint)
from .carabellese_jobs import CarabelleseJob, CarabelleseJobStore
from .editorial_selection import TranscriptAnchor, resolve_anchor_span
from .safety import ValidationError


OUTCOMES = frozenset({"KEEP", "REMOVE", "SHORTEN", "MODIFY"})


def _candidate_groups(job: CarabelleseJob) -> tuple[list[str], list[str], list[str]]:
    boundaries, pauses, exceptions = [], [], []
    for candidate in job.candidates:
        candidate_id, kind = str(candidate.get("candidate_id", "")), str(candidate.get("kind", ""))
        if kind in {"BOUNDARY_START", "BOUNDARY_END"}:
            boundaries.append(candidate_id)
        elif kind.startswith("PAUSE_"):
            pauses.append(candidate_id)
        elif kind in {"EDITORIAL_CUE", "MANUAL"} or candidate.get("review_required") is True:
            exceptions.append(candidate_id)
    return boundaries, pauses, exceptions


def carabellese_secretary_instructions(job: CarabelleseJob) -> dict[str, object]:
    if job.state != "MARKED":
        raise ValidationError("Le istruzioni Carabellese richiedono un job MARKED")
    boundaries, pauses, exceptions = _candidate_groups(job)
    return {
        "card_count": 1, "project": job.project_name, "timeline": job.timeline_name,
        "boundary_ids": boundaries, "pause_ids": pauses, "exception_ids": exceptions,
        "instruction": (
            "Ascolta i marker e rispondi in un solo messaggio: una scelta KEEP/REMOVE/SHORTEN/MODIFY "
            "con motivo per ogni boundary e indicazione; per tutte le pause una sola scelta batch con motivo."
        ),
        "reply_shape": {
            "boundaries": "Bxx OUTCOME — motivo", "pause_batch": "PAUSE OUTCOME — motivo",
            "exceptions": "Cxx OUTCOME — motivo",
        },
    }


def _reason(raw: Mapping[str, object], label: str) -> str:
    value = raw.get("reason")
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"Motivo richiesto per {label}")
    return value.strip()


def _outcome(raw: Mapping[str, object], label: str) -> str:
    value = raw.get("outcome")
    if value not in OUTCOMES:
        raise ValidationError(f"Outcome non valido per {label}")
    return str(value)


def _anchor(raw: object, name: str) -> TranscriptAnchor:
    if not isinstance(raw, dict) or set(raw) - {"text", "occurrence"} or "text" not in raw:
        raise ValidationError(f"{name} non valida")
    text, occurrence = raw["text"], raw.get("occurrence")
    if not isinstance(text, str) or not text.strip():
        raise ValidationError(f"{name}.text richiesto")
    if occurrence is not None and (isinstance(occurrence, bool) or not isinstance(occurrence, int)
                                   or occurrence < 1):
        raise ValidationError(f"{name}.occurrence non valida")
    return TranscriptAnchor(text.strip(), occurrence)


def _parse_individual(raw_items: Sequence[Mapping[str, object]], expected: set[str],
                      label: str, transcript: Mapping[str, object]) -> dict[str, dict[str, object]]:
    if not isinstance(raw_items, Sequence) or isinstance(raw_items, (str, bytes)):
        raise ValidationError(f"{label} deve essere una lista")
    parsed = {}
    for raw in raw_items:
        if not isinstance(raw, Mapping) or set(raw) - {"candidate_id", "outcome", "reason",
                                                      "start_anchor", "end_anchor"}:
            raise ValidationError(f"Decisione {label} malformata")
        candidate_id = raw.get("candidate_id")
        if not isinstance(candidate_id, str) or not candidate_id:
            raise ValidationError(f"candidate_id {label} richiesto")
        if candidate_id in parsed:
            raise ValidationError(f"Decisione duplicata per {candidate_id}")
        outcome, reason = _outcome(raw, candidate_id), _reason(raw, candidate_id)
        decision: dict[str, object] = {"candidate_id": candidate_id, "outcome": outcome,
                                      "reason": reason}
        if outcome == "MODIFY":
            start_anchor = _anchor(raw.get("start_anchor"), "start_anchor")
            end_anchor = _anchor(raw.get("end_anchor"), "end_anchor")
            start_span = resolve_anchor_span(transcript, start_anchor)
            end_span = resolve_anchor_span(transcript, end_anchor)
            if end_span[1] <= start_span[0]:
                raise ValidationError(f"Anchor modificate invertite per {candidate_id}")
            decision.update(start_seconds=start_span[0], end_seconds=end_span[1],
                            start_anchor={"text": start_anchor.text, "occurrence": start_anchor.occurrence},
                            end_anchor={"text": end_anchor.text, "occurrence": end_anchor.occurrence})
        elif raw.get("start_anchor") is not None or raw.get("end_anchor") is not None:
            raise ValidationError("Solo MODIFY può fornire nuove anchor")
        parsed[candidate_id] = decision
    if set(parsed) != expected:
        raise ValidationError(f"Review {label} incompleta: mancanti={sorted(expected-set(parsed))}, "
                              f"extra={sorted(set(parsed)-expected)}")
    return parsed


def _proposal_fingerprint(job: CarabelleseJob) -> str:
    encoded = json.dumps(list(job.candidates), ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def submit_carabellese_review(
    store: CarabelleseJobStore, job: CarabelleseJob,
    boundary_decisions: Sequence[Mapping[str, object]], pause_decision: Mapping[str, object],
    exception_decisions: Sequence[Mapping[str, object]], contract: CarabelleseContract, *,
    transcript: Mapping[str, object],
) -> CarabelleseJob:
    if job.state not in {"MARKED", "REVIEWED"}:
        raise ValidationError("La review Carabellese richiede un job MARKED o REVIEWED")
    if transcript.get("_pinned_fingerprint") != job.transcript_fingerprint:
        raise ValidationError("Fingerprint transcript Carabellese stale")
    actual_contract = carabellese_contract_fingerprint(contract)
    if job.contract_fingerprint != actual_contract:
        raise ValidationError("Fingerprint contratto Carabellese stale")
    if _proposal_fingerprint(job) != job.proposal_fingerprint:
        raise ValidationError("Fingerprint proposte Carabellese stale")
    boundary_ids, pause_ids, exception_ids = _candidate_groups(job)
    boundary_map = _parse_individual(boundary_decisions, set(boundary_ids), "boundary", transcript)
    exception_map = _parse_individual(exception_decisions, set(exception_ids), "eccezioni", transcript)
    if not isinstance(pause_decision, Mapping) or set(pause_decision) - {"outcome", "reason",
                                                                                "residual_seconds"}:
        raise ValidationError("Decisione batch pause malformata")
    pause_outcome = _outcome(pause_decision, "PAUSE_BATCH")
    pause_reason = _reason(pause_decision, "PAUSE_BATCH")
    residual = pause_decision.get("residual_seconds")
    if pause_outcome == "MODIFY":
        if isinstance(residual, bool) or not isinstance(residual, (int, float)) \
                or not contract.residual_min_seconds <= float(residual) <= contract.residual_max_seconds:
            raise ValidationError("MODIFY pause richiede residual_seconds nel contratto")
    elif residual is not None:
        raise ValidationError("residual_seconds consentito solo per MODIFY pause")

    by_candidate = {str(item["candidate_id"]): item for item in job.candidates}
    decisions = []
    for candidate_id, parsed in {**boundary_map, **exception_map}.items():
        candidate = by_candidate[candidate_id]
        decisions.append({
            **parsed, "decision_scope": "INDIVIDUAL",
            "start_seconds": parsed.get("start_seconds", candidate["start_seconds"]),
            "end_seconds": parsed.get("end_seconds", candidate["end_seconds"]),
        })
    for candidate_id in pause_ids:
        candidate = by_candidate[candidate_id]
        decisions.append({"candidate_id": candidate_id, "outcome": pause_outcome,
                          "reason": pause_reason, "decision_scope": "PAUSE_BATCH",
                          "start_seconds": candidate["start_seconds"],
                          "end_seconds": candidate["end_seconds"],
                          "residual_seconds": (float(residual) if residual is not None
                                               else candidate.get("residual_seconds"))})
    decisions.sort(key=lambda item: str(item["candidate_id"]))
    encoded = json.dumps({
        "job_id": job.carabellese_job_id, "contract_fingerprint": actual_contract,
        "proposal_fingerprint": job.proposal_fingerprint,
        "transcript_fingerprint": job.transcript_fingerprint, "decisions": decisions,
    }, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    review_fingerprint = hashlib.sha256(encoded).hexdigest()
    canonical_decisions = tuple(decisions)
    if job.state == "REVIEWED":
        persisted = store.get(job.carabellese_job_id, job.workstation_id)
        if persisted != job:
            raise ValidationError("Job Carabellese stale durante il replay review")
        if (job.decisions != canonical_decisions
                or job.review_fingerprint != review_fingerprint):
            raise ValidationError("Review Carabellese ripetuta diversa da quella approvata")
        return job
    return store.save(replace(job, state="REVIEWED", decisions=canonical_decisions,
                              review_fingerprint=review_fingerprint), job.revision)
