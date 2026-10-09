from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import hashlib
import json
from pathlib import Path
import re
from typing import Mapping, Sequence

from .audio_provenance import VerifiedAudio, verify_audio_manifest
from .carabellese_contract import CarabelleseContract
from .config import CreativeConfig
from .editorial_selection import TranscriptAnchor, load_pinned_transcript, resolve_anchor_span
from .safety import ValidationError


KINDS = frozenset({"PAUSE_CONTEXTUAL", "PAUSE_REDUCE", "BOUNDARY_START", "BOUNDARY_END",
                   "EDITORIAL_CUE", "MANUAL"})
INDIVIDUAL_REVIEW_KINDS = frozenset({"PAUSE_CONTEXTUAL", "BOUNDARY_START", "BOUNDARY_END",
                                     "EDITORIAL_CUE", "MANUAL"})
RAW_KEYS = {"candidate_id", "kind", "start_seconds", "end_seconds", "start_anchor",
            "end_anchor", "context_before", "context_after", "reason", "review_required",
            "residual_seconds", "speaker_turn"}


@dataclass(frozen=True)
class CleanupCandidate:
    candidate_id: str
    kind: str
    start_seconds: float
    end_seconds: float
    start_anchor: str
    end_anchor: str
    context_before: str
    context_after: str
    reason: str
    review_required: bool
    residual_seconds: float | None
    speaker_turn: bool


@dataclass(frozen=True)
class CarabelleseInputs:
    source_fingerprint: str
    transcript_fingerprint: str
    transcript: dict[str, object]
    audio: VerifiedAudio
    words: tuple[dict[str, object], ...]
    silence_windows: tuple[tuple[float, float], ...]


def _number(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValidationError(f"{name} deve essere numerico")
    result = float(value)
    if result != result or abs(result) == float("inf") or result < 0:
        raise ValidationError(f"{name} fuori intervallo")
    return result


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{name} context richiesto")
    return value.strip()


def _anchor_text(value: object, name: str) -> str:
    if not isinstance(value, dict) or set(value) - {"text", "occurrence"} or "text" not in value:
        raise ValidationError(f"{name} non valida")
    return _text(value.get("text"), name)


def _flatten_words(transcript: Mapping[str, object]) -> tuple[dict[str, object], ...]:
    segments = transcript.get("segments")
    if not isinstance(segments, list):
        raise ValidationError("Transcript privo di segments")
    result = []
    for segment in segments:
        if not isinstance(segment, dict) or not isinstance(segment.get("words"), list):
            raise ValidationError("Segmento transcript privo di parole temporizzate")
        for word in segment["words"]:
            if not isinstance(word, dict):
                raise ValidationError("Parola transcript non valida")
            result.append(dict(word))
    if not result:
        raise ValidationError("Transcript senza parole temporizzate")
    return tuple(result)


def load_carabellese_inputs(config: CreativeConfig, transcript_path: Path,
                            transcript_fingerprint: str, audio_job_id: str,
                            expected_source_fingerprint: str) -> CarabelleseInputs:
    transcript = load_pinned_transcript(transcript_path, transcript_fingerprint)
    source = transcript.get("source")
    if not isinstance(source, dict) or source.get("fingerprint") != expected_source_fingerprint:
        raise ValidationError("Transcript derivato da una sorgente differente")
    try:
        audio = verify_audio_manifest(config, audio_job_id, expected_source_fingerprint)
    except ValidationError as exc:
        raise ValidationError(f"Audio non associato alla sorgente Carabellese: {exc}") from exc
    return CarabelleseInputs(expected_source_fingerprint, transcript_fingerprint, transcript,
                             audio, _flatten_words(transcript), audio.silence_windows)


def _word(raw: Mapping[str, object]) -> tuple[str, float, float, str | None]:
    text = raw.get("word", raw.get("text"))
    if not isinstance(text, str) or not text.strip():
        raise ValidationError("Parola senza testo")
    start, end = _number(raw.get("start"), "word.start"), _number(raw.get("end"), "word.end")
    if end <= start:
        raise ValidationError("Intervallo parola non valido")
    speaker = raw.get("speaker")
    if speaker is not None and not isinstance(speaker, str):
        raise ValidationError("speaker parola non valido")
    return text.strip(), start, end, speaker


def derive_pause_candidates(words: Sequence[Mapping[str, object]],
                            silence_windows: Sequence[Mapping[str, object] | tuple[float, float]],
                            contract: CarabelleseContract) -> tuple[CleanupCandidate, ...]:
    parsed_words = [_word(raw) for raw in words]
    if any(current[1] < previous[2] for previous, current in zip(parsed_words, parsed_words[1:])):
        raise ValidationError("Parole sovrapposte o non ordinate")
    windows = []
    for raw in silence_windows:
        if isinstance(raw, Mapping):
            start, end = _number(raw.get("start"), "silence.start"), _number(raw.get("end"), "silence.end")
        elif isinstance(raw, tuple) and len(raw) == 2:
            start, end = _number(raw[0], "silence.start"), _number(raw[1], "silence.end")
        else:
            raise ValidationError("Silence window non valida")
        if end <= start:
            raise ValidationError("Silence window vuota")
        windows.append((start, end))
    target_residual = (contract.residual_min_seconds + contract.residual_max_seconds) / 2
    result = []
    for previous, current in zip(parsed_words, parsed_words[1:]):
        gap_start, gap_end = previous[2], current[1]
        gap = gap_end - gap_start
        if gap < contract.retain_below_seconds or previous[3] != current[3]:
            continue
        verified = next((window for window in windows
                         if window[0] <= gap_start + 0.001 and window[1] >= gap_end - 0.001), None)
        if verified is None or gap <= target_residual:
            continue
        removal = gap - target_residual
        cut_start = gap_start + target_residual / 2
        cut_end = cut_start + removal
        safe_start = verified[0] + contract.protected_silence_handle_seconds
        safe_end = verified[1] - contract.protected_silence_handle_seconds
        if cut_start < safe_start or cut_end > safe_end or cut_end <= cut_start:
            continue
        contextual = gap <= contract.contextual_through_seconds
        result.append(CleanupCandidate(
            candidate_id=f"P{len(result) + 1:03d}",
            kind="PAUSE_CONTEXTUAL" if contextual else "PAUSE_REDUCE",
            start_seconds=round(cut_start, 3), end_seconds=round(cut_end, 3),
            start_anchor=previous[0], end_anchor=current[0],
            context_before=previous[0], context_after=current[0],
            reason="pausa contestuale da confermare" if contextual else "riduzione pausa lunga",
            review_required=contextual, residual_seconds=round(target_residual, 3),
            speaker_turn=False,
        ))
    return tuple(result)


def _occurrence(raw: Mapping[str, object]) -> int | None:
    value = raw.get("occurrence")
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def validate_cleanup_candidates(raw: Sequence[Mapping[str, object]],
                                transcript: Mapping[str, object], contract: CarabelleseContract,
                                duration_seconds: float) -> tuple[CleanupCandidate, ...]:
    duration = _number(duration_seconds, "duration_seconds")
    if duration <= 0 or not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        raise ValidationError("Candidates o durata non validi")
    result: list[CleanupCandidate] = []
    ids: set[str] = set()
    for item in raw:
        if not isinstance(item, Mapping) or set(item) != RAW_KEYS:
            raise ValidationError("Campi candidate Carabellese mancanti o sconosciuti")
        candidate_id = _text(item.get("candidate_id"), "candidate_id")
        if candidate_id in ids or not re.fullmatch(r"[A-Z][A-Z0-9_-]{1,31}", candidate_id):
            raise ValidationError("candidate_id duplicato o non valido")
        ids.add(candidate_id)
        kind = item.get("kind")
        if kind not in KINDS:
            raise ValidationError("kind candidate non valido")
        start, end = _number(item.get("start_seconds"), "start_seconds"), _number(item.get("end_seconds"), "end_seconds")
        if end <= start or end > duration:
            raise ValidationError("Intervallo candidate vuoto o oltre la durata")
        start_raw, end_raw = item["start_anchor"], item["end_anchor"]
        start_text, end_text = _anchor_text(start_raw, "start_anchor"), _anchor_text(end_raw, "end_anchor")
        start_span = resolve_anchor_span(transcript, TranscriptAnchor(start_text, _occurrence(start_raw)))
        end_span = resolve_anchor_span(transcript, TranscriptAnchor(end_text, _occurrence(end_raw)))
        if start > end_span[1] or end < start_span[0]:
            raise ValidationError("Intervallo candidate non ancorato alle parole transcript")
        residual_raw = item.get("residual_seconds")
        residual = None if residual_raw is None else _number(residual_raw, "residual_seconds")
        if not isinstance(item.get("review_required"), bool) or not isinstance(item.get("speaker_turn"), bool):
            raise ValidationError("review_required e speaker_turn devono essere booleani")
        review_required = item["review_required"] or kind in INDIVIDUAL_REVIEW_KINDS
        candidate = CleanupCandidate(
            candidate_id=candidate_id, kind=str(kind), start_seconds=start, end_seconds=end,
            start_anchor=start_text, end_anchor=end_text,
            context_before=_text(item.get("context_before"), "context_before"),
            context_after=_text(item.get("context_after"), "context_after"),
            reason=_text(item.get("reason"), "reason"), review_required=review_required,
            residual_seconds=residual, speaker_turn=item["speaker_turn"],
        )
        if result and candidate.start_seconds < result[-1].end_seconds:
            previous = result[-1]
            compatible = (candidate.kind.startswith("PAUSE") and previous.kind.startswith("PAUSE")
                          and candidate.start_anchor == previous.start_anchor
                          and candidate.end_anchor == previous.end_anchor
                          and candidate.residual_seconds is not None
                          and contract.residual_min_seconds <= candidate.residual_seconds <= contract.residual_max_seconds)
            if not compatible:
                raise ValidationError("Candidate sovrapposti")
            result[-1] = replace(previous, end_seconds=max(previous.end_seconds, candidate.end_seconds),
                                 residual_seconds=candidate.residual_seconds)
            continue
        result.append(candidate)
    return tuple(result)


def cleanup_candidate_fingerprint(candidates: Sequence[CleanupCandidate]) -> str:
    encoded = json.dumps([asdict(item) for item in candidates], ensure_ascii=False,
                         sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
