from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class BatchApproval:
    proposal_fingerprint: str
    approved_ids: tuple[str, ...]
    modified: dict[str, str]


def approve_proposal_batch(proposal_fingerprint: str, decisions: list[dict[str, Any]], operator_role: str) -> BatchApproval:
    if operator_role not in {"ALESSIO", "TECNICO"}:
        raise ValueError("ruolo non autorizzato all'approvazione")
    approved: list[str] = []
    modified: dict[str, str] = {}
    for decision in decisions:
        proposal_id = str(decision.get("proposal_id", ""))
        state = str(decision.get("decision", ""))
        if not proposal_id or state not in {"APPROVE", "REJECT", "MODIFY"}:
            raise ValueError("Decisione proposta non valida")
        if state in {"APPROVE", "MODIFY"}:
            approved.append(proposal_id)
        if state == "MODIFY":
            replacement = str(decision.get("replacement", "")).strip()
            if not replacement:
                raise ValueError("Modifica senza istruzione")
            modified[proposal_id] = replacement
    return BatchApproval(proposal_fingerprint, tuple(approved), modified)
