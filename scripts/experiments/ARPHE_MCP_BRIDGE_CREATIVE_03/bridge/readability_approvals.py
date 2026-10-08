from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any

from .registry import Registry
from .review_readability import BLOCKED, NEEDS_REVIEW, PASS, SequenceAssessment


STALE_APPROVAL = "STALE_APPROVAL"
ALLOWED_ROLES = {"SEGRETERIA", "TECNICO", "ALESSIO"}
ALLOWED_DECISIONS = {"LONG_SINGLE", "VERBATIM_SPLIT"}


class ReadabilityApprovalError(ValueError):
    pass


@dataclass(frozen=True)
class ReadabilityApproval:
    token: str
    assessment_fingerprint: str
    workstation_id: str
    operator_role: str
    decisions: tuple[dict[str, Any], ...]
    created_at: str


def _canonical_decisions(decisions: list[dict]) -> tuple[dict[str, Any], ...]:
    if not isinstance(decisions, list):
        raise ValueError("decisions deve essere una lista")
    canonical: list[dict[str, Any]] = []
    seen: set[int] = set()
    for decision in decisions:
        if not isinstance(decision, dict):
            raise ValueError("decision deve essere un oggetto")
        kind = decision.get("decision")
        index = decision.get("review_index")
        if kind not in ALLOWED_DECISIONS:
            raise ValueError("decision non consentita")
        if isinstance(index, bool) or not isinstance(index, int) or index < 0:
            raise ValueError("review_index non valido")
        if index in seen:
            raise ValueError("decision duplicata per review_index")
        seen.add(index)
        if kind == "LONG_SINGLE":
            if set(decision) != {"review_index", "decision"}:
                raise ValueError("LONG_SINGLE contiene campi non consentiti")
            canonical.append({"review_index": index, "decision": kind})
        else:
            if set(decision) != {"review_index", "decision", "split_offset"}:
                raise ValueError("VERBATIM_SPLIT richiede solo split_offset")
            offset = decision.get("split_offset")
            if isinstance(offset, bool) or not isinstance(offset, int) or offset <= 0:
                raise ValueError("split_offset non valido")
            canonical.append(
                {"review_index": index, "decision": kind, "split_offset": offset}
            )
    return tuple(sorted(canonical, key=lambda item: item["review_index"]))


def _approval_token(metadata: dict[str, Any]) -> str:
    encoded = json.dumps(
        metadata, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def approve_readability(
    registry: Registry,
    workstation_id: str,
    assessment_fingerprint: str,
    decisions: list[dict],
    operator_role: str,
) -> ReadabilityApproval:
    if operator_role not in ALLOWED_ROLES:
        raise ValueError("operator_role non autorizzato")
    if not re.fullmatch(r"PC_[A-Z0-9_]{2,48}", workstation_id):
        raise ValueError("workstation_id non valido")
    if not re.fullmatch(r"[0-9a-f]{64}", assessment_fingerprint):
        raise ValueError("assessment_fingerprint non valido")
    canonical = _canonical_decisions(decisions)
    created_at = datetime.now(timezone.utc).isoformat()
    metadata = {
        "assessment_fingerprint": assessment_fingerprint,
        "workstation_id": workstation_id,
        "operator_role": operator_role,
        "decisions": list(canonical),
        "created_at": created_at,
    }
    token = _approval_token(metadata)
    approval = ReadabilityApproval(
        token=token,
        assessment_fingerprint=assessment_fingerprint,
        workstation_id=workstation_id,
        operator_role=operator_role,
        decisions=canonical,
        created_at=created_at,
    )
    registry.save_readability_approval(approval)
    return approval


def _from_record(record: dict[str, Any]) -> ReadabilityApproval:
    expected = {
        "token",
        "assessment_fingerprint",
        "workstation_id",
        "operator_role",
        "decisions",
        "created_at",
    }
    if not isinstance(record, dict) or set(record) != expected:
        raise ReadabilityApprovalError(f"{STALE_APPROVAL}: record non valido")
    decisions = _canonical_decisions(record["decisions"])
    approval = ReadabilityApproval(
        token=str(record["token"]),
        assessment_fingerprint=str(record["assessment_fingerprint"]),
        workstation_id=str(record["workstation_id"]),
        operator_role=str(record["operator_role"]),
        decisions=decisions,
        created_at=str(record["created_at"]),
    )
    metadata = {
        "assessment_fingerprint": approval.assessment_fingerprint,
        "workstation_id": approval.workstation_id,
        "operator_role": approval.operator_role,
        "decisions": list(approval.decisions),
        "created_at": approval.created_at,
    }
    if _approval_token(metadata) != approval.token:
        raise ReadabilityApprovalError(f"{STALE_APPROVAL}: token non coerente")
    return approval


def require_current_approval(
    registry: Registry,
    assessment: SequenceAssessment,
    approval_token: str | None,
    workstation_id: str | None = None,
) -> ReadabilityApproval | None:
    if assessment.status == PASS and approval_token is None:
        return None
    if assessment.status == BLOCKED:
        raise ValueError("La leggibilità è bloccata e non può essere approvata")
    if assessment.status != NEEDS_REVIEW:
        raise ValueError("Stato assessment non supportato")
    if not approval_token:
        raise ReadabilityApprovalError(f"{STALE_APPROVAL}: approvazione richiesta")
    record = registry.readability_approval(approval_token)
    if record is None:
        raise ReadabilityApprovalError(f"{STALE_APPROVAL}: token sconosciuto")
    approval = _from_record(record)
    if workstation_id is not None and approval.workstation_id != workstation_id:
        raise ReadabilityApprovalError(f"{STALE_APPROVAL}: workstation diversa")
    if approval.assessment_fingerprint != assessment.fingerprint:
        raise ReadabilityApprovalError(f"{STALE_APPROVAL}: assessment modificato")

    expected_indexes = {
        index for index, review in enumerate(assessment.reviews) if review.status == NEEDS_REVIEW
    }
    decisions_by_index = {
        int(decision["review_index"]): decision for decision in approval.decisions
    }
    if set(decisions_by_index) != expected_indexes:
        raise ValueError("Serve una decisione per ogni recensione NEEDS_REVIEW")
    for index in expected_indexes:
        decision = decisions_by_index[index]
        if decision["decision"] == "VERBATIM_SPLIT":
            suggested = assessment.reviews[index].suggested_split
            if suggested is None or decision["split_offset"] != suggested:
                raise ValueError("split_offset diverso dal confine suggerito e approvabile")
    return approval
