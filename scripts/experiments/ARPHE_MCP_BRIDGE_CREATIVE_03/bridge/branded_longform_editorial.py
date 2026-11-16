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
    asset_path: str | None = None
    source_start_frame: int | None = None
    source_end_frame: int | None = None
    content: dict[str, Any] | None = None


def validate_proposal(profile_id: str, kind: str) -> None:
    if profile_id not in {"ARPHE_LONGFORM_EDITORIAL", "CARABELLESE_LONGFORM_EDITORIAL"}:
        raise ValueError("Profilo longform sconosciuto")


def _text_list(value: object, name: str, minimum: int, maximum: int) -> list[str]:
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        raise ValueError(f"{name}: richiesti da {minimum} a massimo {maximum} elementi")
    clean = [str(item).strip() for item in value]
    if any(not item or len(item) > 80 for item in clean):
        raise ValueError(f"{name}: testo vuoto o troppo lungo")
    return clean


def _comparison(value: object) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {"left_title", "right_title", "rows"}:
        raise ValueError("comparison non valida")
    left, right = str(value["left_title"]).strip(), str(value["right_title"]).strip()
    if not left or not right or len(left) > 40 or len(right) > 40:
        raise ValueError("comparison: titoli non validi")
    rows = value["rows"]
    if not isinstance(rows, list) or not 1 <= len(rows) <= 4:
        raise ValueError("comparison: richieste da 1 a massimo 4 righe")
    clean_rows = []
    for row in rows:
        if not isinstance(row, list) or len(row) != 2:
            raise ValueError("comparison: ogni riga richiede due celle")
        cells = [str(cell).strip() for cell in row]
        if any(not cell or len(cell) > 80 for cell in cells):
            raise ValueError("comparison: cella vuota o troppo lunga")
        clean_rows.append(cells)
    return {"left_title": left, "right_title": right, "rows": clean_rows}


def propose_editorial(segments: list[dict[str, Any]], profile_id: str) -> tuple[EditorialProposal, ...]:
    proposals: list[EditorialProposal] = []
    for index, segment in enumerate(segments, 1):
        semantic_class = str(segment["class"])
        confidence = float(segment.get("confidence", 1.0))
        content: dict[str, Any] | None = None
        if confidence < 0.7:
            kind, rationale = "REVIEW_ONLY", "Confidenza bassa: serve giudizio editoriale"
        elif segment.get("provided_broll"):
            kind, rationale = "B_ROLL_PROVIDED", "Esempio concreto: B-roll fornito da verificare"
        elif segment.get("generated_broll"):
            kind, rationale = "B_ROLL_GENERATED", "B-roll generato: solo proposta, mai import automatico"
        elif segment.get("camera_cut_available"):
            kind, rationale = "CAMERA_CUT", "Cambio camera preferibile a una grafica"
        elif semantic_class in {"PERSONAL", "STORY"}:
            kind, rationale = "NO_OVERLAY", "Passaggio personale: preservare il respiro"
        elif segment.get("comparison") is not None:
            kind, rationale = "COMPARISON_TABLE", "Confronto esplicito"
            content = _comparison(segment["comparison"])
        elif segment.get("process_steps") is not None:
            kind, rationale = "PROCESS_STEPS", "Processo in passaggi"
            content = {"steps": _text_list(segment["process_steps"], "process_steps", 3, 5)}
        elif semantic_class == "EXPLAIN" and isinstance(segment.get("items"), list):
            kind, rationale = "PROGRESSIVE_LIST", "Elenco di almeno tre elementi"
            content = {"items": _text_list(segment["items"], "items", 3, 5)}
        elif semantic_class == "EXPLAIN" and int(segment.get("items", 0)) >= 3:
            kind, rationale = "PROGRESSIVE_LIST", "Elenco di almeno tre elementi"
        elif semantic_class == "TRANSITION":
            kind, rationale = "CHAPTER_CARD", "Cambio argomento"
        else:
            kind, rationale = "KEYWORD_BOX", "Segnalazione conservativa del concetto"
        visual = kind not in {"NO_OVERLAY", "REVIEW_ONLY", "CAMERA_CUT", "B_ROLL_GENERATED"}
        executable = kind not in {"REVIEW_ONLY", "CAMERA_CUT", "B_ROLL_GENERATED"}
        blocked_reason = ("LOW_CONFIDENCE" if kind == "REVIEW_ONLY" else
                          "NATIVE_CAMERA_SWITCH_PENDING" if kind == "CAMERA_CUT" else
                          "GENERATED_MEDIA_REQUIRES_PROVIDER" if kind == "B_ROLL_GENERATED" else None)
        fps = float(segment.get("fps", 30))
        start, end = float(segment["start"]), float(segment["end"])
        broll = segment.get("provided_broll")
        asset_path = str(broll.get("asset_path", "")).strip() if isinstance(broll, dict) else None
        source_start = int(broll["source_start_frame"]) if isinstance(broll, dict) and "source_start_frame" in broll else None
        source_end = int(broll["source_end_frame"]) if isinstance(broll, dict) and "source_end_frame" in broll else None
        if kind == "B_ROLL_PROVIDED" and (not asset_path or source_start is None or source_end is None):
            executable, blocked_reason = False, "BROLL_ASSET_REQUIRED"
        proposals.append(EditorialProposal(
            f"P{index:03d}", kind, start, end, rationale, profile_id,
            executable, blocked_reason,
            round(start * fps), round(end * fps),
            asset_path, source_start, source_end, content,
        ))
    return tuple(proposals)


def proposal_card(job_id: str, proposals: tuple[EditorialProposal, ...]) -> dict[str, Any]:
    return {"card_count": 1, "job_id": job_id, "proposals": [asdict(item) for item in proposals],
            "operator_instruction": "Approva, rifiuta o modifica gli ID in una sola risposta."}


def proposal_fingerprint(card: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(card, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()
