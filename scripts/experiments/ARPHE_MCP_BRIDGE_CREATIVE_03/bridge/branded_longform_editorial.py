from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class EditorialProposal:
    proposal_id: str
    kind: str
    start: float
    end: float
    rationale: str


def validate_proposal(profile_id: str, kind: str) -> None:
    if profile_id == "CARABELLESE_LONGFORM_EDITORIAL" and kind in {"GRAPHIC", "CARD"}:
        raise ValueError("Graphic Kit pending: proposta grafica bloccata")


def propose_editorial(segments: list[dict[str, Any]], profile_id: str) -> tuple[EditorialProposal, ...]:
    proposals: list[EditorialProposal] = []
    for index, segment in enumerate(segments, 1):
        semantic_class = str(segment["class"])
        if semantic_class == "PERSONAL":
            kind, rationale = "NO_OVERLAY", "Passaggio personale: preservare il respiro"
        elif semantic_class == "EXPLAIN" and int(segment.get("items", 0)) >= 3:
            kind, rationale = "PROGRESSIVE_LIST", "Elenco di almeno tre elementi"
        elif semantic_class == "TRANSITION":
            kind, rationale = "CHAPTER_CARD", "Cambio argomento"
        else:
            kind, rationale = "KEYWORD_BOX", "Segnalazione conservativa del concetto"
        if kind != "NO_OVERLAY":
            validate_proposal(profile_id, "CARD")
        proposals.append(EditorialProposal(f"P{index:03d}", kind, float(segment["start"]), float(segment["end"]), rationale))
    return tuple(proposals)
