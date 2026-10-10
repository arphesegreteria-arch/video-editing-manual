from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Any


@dataclass(frozen=True)
class EditorialProposal:
    proposal_id: str
    kind: str
    start: float
    end: float
    rationale: str
    profile_id: str
    executable: bool
    blocked_reason: str | None
    start_frame: int
    end_frame: int


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
        visual = kind != "NO_OVERLAY"
        pending = profile_id == "CARABELLESE_LONGFORM_EDITORIAL" and visual
        fps = float(segment.get("fps", 30))
        start, end = float(segment["start"]), float(segment["end"])
        proposals.append(EditorialProposal(
            f"P{index:03d}", kind, start, end, rationale, profile_id,
            not pending, "KIT_PENDING" if pending else None,
            round(start * fps), round(end * fps),
        ))
    return tuple(proposals)


def proposal_card(job_id: str, proposals: tuple[EditorialProposal, ...]) -> dict[str, Any]:
    return {"card_count": 1, "job_id": job_id, "proposals": [asdict(item) for item in proposals],
            "operator_instruction": "Approva, rifiuta o modifica gli ID in una sola risposta."}


def proposal_fingerprint(card: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(card, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()
