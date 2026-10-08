from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

from .editorial_selection_contract import SelectionContract
from .safety import ValidationError


CANDIDATE_KEYS = {
    "candidate_id", "thesis", "start_anchor", "end_anchor", "indispensable_context",
    "source_start_seconds", "source_end_seconds", "speech_duration_seconds",
    "cta_duration_seconds", "final_duration_seconds", "uniqueness_evidence",
    "quality_rationale",
}
ANCHOR_TIME_TOLERANCE_SECONDS = 1.0
DURATION_TOLERANCE_SECONDS = 0.05
DUPLICATE_OVERLAP_RATIO = 0.80


@dataclass(frozen=True)
class TranscriptAnchor:
    text: str
    occurrence: int | None = None


@dataclass(frozen=True)
class CandidateProposal:
    candidate_id: str
    thesis: str
    start_anchor: TranscriptAnchor
    end_anchor: TranscriptAnchor
    indispensable_context: str
    source_start_seconds: float
    source_end_seconds: float
    speech_duration_seconds: float
    cta_duration_seconds: float
    final_duration_seconds: float
    uniqueness_evidence: str
    quality_rationale: str


@dataclass(frozen=True)
class ResolvedCandidate:
    proposal: CandidateProposal
    source_in_frame: int
    source_out_frame_exclusive: int
    transcript_start_seconds: float
    transcript_end_seconds: float


@dataclass(frozen=True)
class _TimedWord:
    token: str
    start: float
    end: float


def load_pinned_transcript(path: Path, expected_fingerprint: str) -> dict[str, object]:
    if not isinstance(expected_fingerprint, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_fingerprint):
        raise ValidationError("Transcript fingerprint non valido")
    try:
        encoded = path.read_bytes()
        data = json.loads(encoded.decode("utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValidationError(f"Transcript non leggibile: {exc}") from exc
    if hashlib.sha256(encoded).hexdigest() != expected_fingerprint:
        raise ValidationError("Transcript fingerprint non corrispondente")
    if not isinstance(data, dict) or data.get("schema") != "ARPHE_TRANSCRIPT_V1" or data.get("status") != "complete":
        raise ValidationError("Transcript non completo o schema non supportato")
    if not isinstance(data.get("source"), dict) or not isinstance(data.get("segments"), list):
        raise ValidationError("Transcript privo di source o segments")
    return data


def _tokens(text: str) -> list[str]:
    return re.findall(r"\w+", text.casefold(), flags=re.UNICODE)


def _plain_seconds(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValidationError(f"{name} deve essere numerico")
    result = float(value)
    if result < 0 or result == float("inf") or result != result:
        raise ValidationError(f"{name} fuori intervallo")
    return result


def _timed_words(transcript: Mapping[str, object]) -> tuple[_TimedWord, ...]:
    if transcript.get("schema") != "ARPHE_TRANSCRIPT_V1" or transcript.get("status") != "complete":
        raise ValidationError("Transcript non completo o schema non supportato")
    segments = transcript.get("segments")
    if not isinstance(segments, list):
        raise ValidationError("segments transcript non validi")
    words: list[_TimedWord] = []
    for segment in segments:
        if not isinstance(segment, dict) or not isinstance(segment.get("words"), list):
            raise ValidationError("Ogni segmento deve contenere parole temporizzate")
        for raw in segment["words"]:
            if not isinstance(raw, dict):
                raise ValidationError("Parola transcript non valida")
            raw_text = raw.get("word", raw.get("text"))
            if not isinstance(raw_text, str):
                raise ValidationError("Parola transcript senza testo")
            normalized = _tokens(raw_text)
            if len(normalized) != 1:
                raise ValidationError("Ogni parola temporizzata deve produrre un token")
            start = _plain_seconds(raw.get("start"), "word.start")
            end = _plain_seconds(raw.get("end"), "word.end")
            if end <= start:
                raise ValidationError("Intervallo parola transcript non valido")
            words.append(_TimedWord(normalized[0], start, end))
    if not words:
        raise ValidationError("Transcript senza parole temporizzate")
    if any(current.start < previous.start for previous, current in zip(words, words[1:])):
        raise ValidationError("Parole transcript non ordinate")
    return tuple(words)


def _anchor_matches(transcript: Mapping[str, object], anchor: TranscriptAnchor,
                    near_seconds: tuple[float, float] | None = None) -> list[tuple[float, float]]:
    if not isinstance(anchor.text, str) or not anchor.text.strip():
        raise ValidationError("Anchor testuale vuota")
    wanted = _tokens(anchor.text)
    if not wanted:
        raise ValidationError("Anchor priva di parole")
    words = _timed_words(transcript)
    matches: list[tuple[float, float]] = []
    size = len(wanted)
    for index in range(0, len(words) - size + 1):
        window = words[index:index + size]
        if [word.token for word in window] != wanted:
            continue
        match = (window[0].start, window[-1].end)
        if near_seconds is not None and not (
            match[0] >= float(near_seconds[0]) and match[1] <= float(near_seconds[1])
        ):
            continue
        matches.append(match)
    if anchor.occurrence is not None:
        if isinstance(anchor.occurrence, bool) or not isinstance(anchor.occurrence, int) or anchor.occurrence < 1:
            raise ValidationError("occurrence deve essere un intero da 1 in su")
        if anchor.occurrence > len(matches):
            raise ValidationError("Occurrence anchor non trovata")
        return [matches[anchor.occurrence - 1]]
    return matches


def _resolved_anchor(transcript: Mapping[str, object], anchor: TranscriptAnchor,
                     near_seconds: tuple[float, float] | None = None) -> tuple[float, float]:
    matches = _anchor_matches(transcript, anchor, near_seconds)
    if not matches:
        raise ValidationError("Anchor non trovata nel transcript fissato")
    if len(matches) != 1:
        raise ValidationError("Anchor ambigua nel transcript fissato")
    return matches[0]


def resolve_anchor(transcript: Mapping[str, object], anchor: TranscriptAnchor,
                   *, near_seconds: tuple[float, float] | None = None) -> float:
    return _resolved_anchor(transcript, anchor, near_seconds)[0]


def _anchor(raw: object, name: str) -> TranscriptAnchor:
    if not isinstance(raw, dict) or set(raw) - {"text", "occurrence"} or "text" not in raw:
        raise ValidationError(f"{name} non valida")
    occurrence = raw.get("occurrence")
    if occurrence is not None and (isinstance(occurrence, bool) or not isinstance(occurrence, int)):
        raise ValidationError(f"{name}.occurrence non valida")
    return TranscriptAnchor(str(raw["text"]), occurrence)


def _required_text(raw: Mapping[str, object], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{key} richiesto")
    return value.strip()


def _proposal(raw: Mapping[str, object], expected_id: str) -> CandidateProposal:
    if set(raw) != CANDIDATE_KEYS:
        raise ValidationError(
            f"Candidate fields mancanti={sorted(CANDIDATE_KEYS - set(raw))}, "
            f"sconosciuti={sorted(set(raw) - CANDIDATE_KEYS)}"
        )
    candidate_id = _required_text(raw, "candidate_id")
    if candidate_id != expected_id:
        raise ValidationError(f"candidate_id atteso {expected_id}, ricevuto {candidate_id}")
    return CandidateProposal(
        candidate_id=candidate_id,
        thesis=_required_text(raw, "thesis"),
        start_anchor=_anchor(raw["start_anchor"], "start_anchor"),
        end_anchor=_anchor(raw["end_anchor"], "end_anchor"),
        indispensable_context=_required_text(raw, "indispensable_context"),
        source_start_seconds=_plain_seconds(raw["source_start_seconds"], "source_start_seconds"),
        source_end_seconds=_plain_seconds(raw["source_end_seconds"], "source_end_seconds"),
        speech_duration_seconds=_plain_seconds(raw["speech_duration_seconds"], "speech_duration_seconds"),
        cta_duration_seconds=_plain_seconds(raw["cta_duration_seconds"], "cta_duration_seconds"),
        final_duration_seconds=_plain_seconds(raw["final_duration_seconds"], "final_duration_seconds"),
        uniqueness_evidence=_required_text(raw, "uniqueness_evidence"),
        quality_rationale=_required_text(raw, "quality_rationale"),
    )


def _floor_frame(seconds: float, fps: Fraction) -> int:
    value = Fraction(str(seconds)) * fps
    return value.numerator // value.denominator


def _ceil_frame(seconds: float, fps: Fraction) -> int:
    value = Fraction(str(seconds)) * fps
    return -(-value.numerator // value.denominator)


def _thesis_key(value: str) -> str:
    return " ".join(_tokens(value))


def validate_candidate_batch(raw: Sequence[Mapping[str, object]], *,
                             transcript: Mapping[str, object], fps: Fraction,
                             contract: SelectionContract) -> tuple[ResolvedCandidate, ...]:
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        raise ValidationError("Candidates deve essere una sequenza")
    if not 1 <= len(raw) <= contract.max_candidates:
        raise ValidationError(f"Candidates deve contenere 1-{contract.max_candidates} elementi")
    if not isinstance(fps, Fraction) or fps <= 0 or fps > 120:
        raise ValidationError("FPS deve essere una Fraction positiva e plausibile")
    theses: set[str] = set()
    resolved: list[ResolvedCandidate] = []
    for index, item in enumerate(raw, 1):
        if not isinstance(item, Mapping):
            raise ValidationError("Ogni candidate deve essere un oggetto")
        proposal = _proposal(item, f"R{index:02d}")
        thesis_key = _thesis_key(proposal.thesis)
        if thesis_key in theses:
            raise ValidationError("Tesi duplicata: consolidare le proposte")
        theses.add(thesis_key)
        start_match = _resolved_anchor(transcript, proposal.start_anchor)
        end_match = _resolved_anchor(transcript, proposal.end_anchor)
        transcript_start = start_match[0]
        transcript_end = end_match[1]
        if transcript_end <= transcript_start or proposal.source_end_seconds <= proposal.source_start_seconds:
            raise ValidationError("Intervallo candidate vuoto o invertito")
        if abs(proposal.source_start_seconds - transcript_start) > ANCHOR_TIME_TOLERANCE_SECONDS:
            raise ValidationError("Source start non corrisponde all'anchor")
        if abs(proposal.source_end_seconds - transcript_end) > ANCHOR_TIME_TOLERANCE_SECONDS:
            raise ValidationError("Source end non corrisponde all'anchor")
        interval = proposal.source_end_seconds - proposal.source_start_seconds
        if abs(interval - proposal.speech_duration_seconds) > DURATION_TOLERANCE_SECONDS:
            raise ValidationError("speech_duration_seconds non corrisponde all'intervallo")
        if abs(proposal.cta_duration_seconds - contract.cta_duration_seconds) > 0.001:
            raise ValidationError("cta_duration_seconds non corrisponde al contratto")
        if abs(proposal.final_duration_seconds - (
            proposal.speech_duration_seconds + proposal.cta_duration_seconds
        )) > DURATION_TOLERANCE_SECONDS:
            raise ValidationError("final_duration_seconds non include correttamente la CTA")
        if proposal.final_duration_seconds > contract.max_final_seconds:
            raise ValidationError("Durata finale oltre il limite assoluto di 180 secondi")
        current = ResolvedCandidate(
            proposal=proposal,
            source_in_frame=_floor_frame(proposal.source_start_seconds, fps),
            source_out_frame_exclusive=_ceil_frame(proposal.source_end_seconds, fps),
            transcript_start_seconds=transcript_start,
            transcript_end_seconds=transcript_end,
        )
        if current.source_out_frame_exclusive <= current.source_in_frame:
            raise ValidationError("Intervallo candidate inferiore a un frame")
        for previous in resolved:
            left = max(proposal.source_start_seconds, previous.proposal.source_start_seconds)
            right = min(proposal.source_end_seconds, previous.proposal.source_end_seconds)
            overlap = max(0.0, right - left)
            shorter = min(interval, previous.proposal.source_end_seconds - previous.proposal.source_start_seconds)
            if shorter > 0 and overlap / shorter >= DUPLICATE_OVERLAP_RATIO:
                raise ValidationError("Proposte con sovrapposizione materiale: consolidarle")
        resolved.append(current)
    return tuple(resolved)
