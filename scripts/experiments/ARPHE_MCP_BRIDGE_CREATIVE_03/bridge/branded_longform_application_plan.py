from __future__ import annotations

from typing import Any


def build_application_plan(proposals: dict[str, dict[str, Any]], approved_ids: tuple[str, ...]) -> tuple[dict[str, Any], ...]:
    missing = [proposal_id for proposal_id in approved_ids if proposal_id not in proposals]
    if missing:
        raise ValueError(f"Proposta approvata assente: {missing}")
    return tuple({"proposal_id": proposal_id, **proposals[proposal_id]} for proposal_id in approved_ids)
