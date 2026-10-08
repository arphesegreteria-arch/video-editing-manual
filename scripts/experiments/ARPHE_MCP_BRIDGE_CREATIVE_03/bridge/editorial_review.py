from __future__ import annotations

from dataclasses import dataclass, replace
import re
from typing import Mapping, Sequence

from .editorial_jobs import EditorialJob, EditorialJobStore
from .editorial_selection import TranscriptAnchor, resolve_anchor_span
from .editorial_selection_contract import SelectionContract, canonical_digest
from .safety import ValidationError


OUTCOMES = frozenset({"APPROVE", "MODIFY", "REJECT"})
DECISION_KEYS = {
    "candidate_id", "outcome", "reason", "start_anchor", "end_anchor",
    "normalized_reason_tags",
}
TAG = re.compile(r"^[a-z][a-z0-9_]{1,63}$")


@dataclass(frozen=True)
class ReviewDecision:
    candidate_id: str
    outcome: str
    reason: str
    start_anchor: TranscriptAnchor | None = None
    end_anchor: TranscriptAnchor | None = None
    normalized_reason_tags: tuple[str, ...] = ()


def secretary_instructions(job: EditorialJob) -> dict[str, object]:
    if job.state != "MARKED":
        raise ValidationError("Le istruzioni di ascolto richiedono un job MARKED")
    return {
        "project": job.project_name,
        "timeline": job.timeline_name,
        "candidate_count": len(job.candidates),
        "steps": [
            "Ascolta da ogni marker ARPHE_Rxx_IN al relativo ARPHE_Rxx_OUT.",
            "Non spostare e non eliminare i marker.",
            "Rispondi una volta con OK, MODIFICA o RIFIUTA e un motivo breve per ogni Rxx.",
        ],
        "example": (
            'R01 OK — chiaro e diretto\n'
            'R02 MODIFICA — inizia da "..." e termina dopo "..." — parte lentamente\n'
            'R03 RIFIUTA — ripete R01'
        ),
    }


def _anchor(raw: object, name: str) -> TranscriptAnchor:
    if not isinstance(raw, dict) or set(raw) - {"text", "occurrence"} or "text" not in raw:
        raise ValidationError(f"{name} non valida")
    text = raw["text"]
    occurrence = raw.get("occurrence")
    if not isinstance(text, str) or not text.strip():
        raise ValidationError(f"{name}.text richiesto")
    if occurrence is not None and (isinstance(occurrence, bool) or not isinstance(occurrence, int)):
        raise ValidationError(f"{name}.occurrence non valida")
    return TranscriptAnchor(text.strip(), occurrence)


def _parse_decision(raw: Mapping[str, object]) -> ReviewDecision:
    if set(raw) - DECISION_KEYS:
        raise ValidationError(f"Campi decisione sconosciuti: {sorted(set(raw) - DECISION_KEYS)}")
    candidate_id = raw.get("candidate_id")
    outcome = raw.get("outcome")
    reason = raw.get("reason")
    if not isinstance(candidate_id, str) or not re.fullmatch(r"R(?:0[1-9]|1[0-9]|20)", candidate_id):
        raise ValidationError("candidate_id decisione non valido")
    if outcome not in OUTCOMES:
        raise ValidationError("outcome deve essere APPROVE, MODIFY o REJECT")
    if not isinstance(reason, str) or not reason.strip():
        raise ValidationError(f"Motivo richiesto per {candidate_id}")
    tags_raw = raw.get("normalized_reason_tags", [])
    if not isinstance(tags_raw, list) or any(
        not isinstance(tag, str) or not TAG.fullmatch(tag) for tag in tags_raw
    ) or len(tags_raw) != len(set(tags_raw)):
        raise ValidationError("normalized_reason_tags non validi")
    if outcome == "MODIFY":
        start_anchor = _anchor(raw.get("start_anchor"), "start_anchor")
        end_anchor = _anchor(raw.get("end_anchor"), "end_anchor")
    else:
        if raw.get("start_anchor") is not None or raw.get("end_anchor") is not None:
            raise ValidationError("Solo MODIFY può fornire nuove anchor")
        start_anchor = end_anchor = None
    return ReviewDecision(candidate_id, str(outcome), reason.strip(), start_anchor, end_anchor,
                          tuple(tags_raw))


def _candidate_fingerprint(job: EditorialJob) -> str:
    return canonical_digest({"candidates": list(job.candidates)})


def submit_structured_review(store: EditorialJobStore, job: EditorialJob,
                             raw_decisions: Sequence[Mapping[str, object]],
                             transcript: Mapping[str, object],
                             contract: SelectionContract) -> EditorialJob:
    if job.state != "MARKED":
        raise ValidationError("La review richiede un job MARKED")
    if transcript.get("_pinned_fingerprint") != job.transcript_fingerprint:
        raise ValidationError("Fingerprint transcript stale")
    if _candidate_fingerprint(job) != job.candidate_fingerprint:
        raise ValidationError("Fingerprint candidate stale")
    if not isinstance(raw_decisions, Sequence) or isinstance(raw_decisions, (str, bytes)):
        raise ValidationError("decisions deve essere una sequenza")
    parsed = [_parse_decision(raw) for raw in raw_decisions]
    ids = [decision.candidate_id for decision in parsed]
    expected_ids = [str(candidate["candidate_id"]) for candidate in job.candidates]
    if len(ids) != len(set(ids)):
        raise ValidationError("Decisione duplicata per lo stesso candidate")
    if set(ids) != set(expected_ids) or len(ids) != len(expected_ids):
        missing = sorted(set(expected_ids) - set(ids))
        extra = sorted(set(ids) - set(expected_ids))
        raise ValidationError(f"Review incompleta: mancanti={missing}, extra={extra}")
    by_id = {decision.candidate_id: decision for decision in parsed}
    resolved: list[dict[str, object]] = []
    for candidate in job.candidates:
        candidate_id = str(candidate["candidate_id"])
        decision = by_id[candidate_id]
        proposed_start = float(candidate["source_start_seconds"])
        proposed_end = float(candidate["source_end_seconds"])
        start = proposed_start
        end = proposed_end
        start_anchor: dict[str, object] | None = None
        end_anchor: dict[str, object] | None = None
        if decision.outcome == "MODIFY":
            lower = max(0.0, proposed_start - contract.modified_anchor_window_seconds)
            upper = proposed_end + contract.modified_anchor_window_seconds
            assert decision.start_anchor is not None and decision.end_anchor is not None
            start_span = resolve_anchor_span(transcript, decision.start_anchor,
                                             near_seconds=(lower, upper))
            end_span = resolve_anchor_span(transcript, decision.end_anchor,
                                           near_seconds=(lower, upper))
            start, end = start_span[0], end_span[1]
            start_anchor = {"text": decision.start_anchor.text,
                            "occurrence": decision.start_anchor.occurrence}
            end_anchor = {"text": decision.end_anchor.text,
                          "occurrence": decision.end_anchor.occurrence}
        if end <= start:
            raise ValidationError(f"Boundary modificate invertite per {candidate_id}")
        speech_seconds = end - start
        final_seconds = speech_seconds + contract.cta_duration_seconds
        if final_seconds > contract.max_final_seconds:
            raise ValidationError(
                f"Durata finale di {candidate_id} oltre il limite assoluto di 180 secondi"
            )
        resolved.append({
            "candidate_id": candidate_id,
            "outcome": decision.outcome,
            "reason": decision.reason,
            "normalized_reason_tags": list(decision.normalized_reason_tags),
            "proposed_start_seconds": proposed_start,
            "proposed_end_seconds": proposed_end,
            "source_start_seconds": start,
            "source_end_seconds": end,
            "speech_duration_seconds": speech_seconds,
            "cta_duration_seconds": contract.cta_duration_seconds,
            "final_duration_seconds": final_seconds,
            "start_anchor": start_anchor,
            "end_anchor": end_anchor,
        })
    fingerprint = canonical_digest({
        "editorial_job_id": job.editorial_job_id,
        "candidate_fingerprint": job.candidate_fingerprint,
        "transcript_fingerprint": job.transcript_fingerprint,
        "decisions": resolved,
    })
    return store.save(
        replace(job, state="REVIEWED", decisions=tuple(resolved), review_fingerprint=fingerprint),
        job.revision,
    )
