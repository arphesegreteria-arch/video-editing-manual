"""Managed native Resolve 21 transcription for one timeline media item."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from .resolve_connection import safe_call
from .review_export21 import validate_review_target
from .safety import ValidationError


JOB_ID = re.compile(r"^native_tx_[0-9a-f]{16}$")
SCHEMA = "ARPHE_RESOLVE_NATIVE_TRANSCRIPTION_V2"
TRANSCRIPTION_TIMEOUT_SECONDS = 30 * 60


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _root(config: Any, *, create: bool) -> Path:
    root = (Path(config.state_path).resolve().parent / "resolve21-native-transcription"
            / str(config.workstation_id)).resolve()
    if create:
        root.mkdir(parents=True, exist_ok=True)
    return root


def _fingerprint(value: object) -> str:
    try:
        canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise ValidationError("Trascrizione nativa non serializzabile") from exc
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _media_fingerprint(media: Any) -> str:
    identity = {
        "unique_id": str(safe_call(media, "GetUniqueId") or ""),
        "name": str(safe_call(media, "GetName") or ""),
        "file_path": str(safe_call(media, "GetClipProperty", "File Path") or ""),
    }
    return _fingerprint(identity)


def _binding(project: Any, timeline: Any, config: Any, clip_id: str,
             use_speaker_detection: bool, media: Any) -> dict[str, Any]:
    return {
        "workstation_id": str(config.workstation_id),
        "project_name": str(safe_call(project, "GetName") or ""),
        "timeline_name": str(safe_call(timeline, "GetName") or ""),
        "clip_id": clip_id,
        "use_speaker_detection": use_speaker_detection,
        "source_fingerprint": _media_fingerprint(media),
    }


def _job_id(binding: dict[str, Any]) -> str:
    canonical = json.dumps(binding, sort_keys=True, separators=(",", ":"))
    return "native_tx_" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def _manifest_path(config: Any, job_id: str, *, create_root: bool) -> Path:
    if not isinstance(job_id, str) or not JOB_ID.fullmatch(job_id):
        raise ValidationError("job_id trascrizione nativa non valido")
    return _root(config, create=create_root) / f"{job_id}.json"


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    temporary.replace(path)


def _find_media(timeline: Any, clip_id: str) -> Any:
    if not isinstance(clip_id, str) or not clip_id or len(clip_id) > 256:
        raise ValidationError("clip_id non valido")
    for track_type in ("video", "audio"):
        try:
            count = int(safe_call(timeline, "GetTrackCount", track_type) or 0)
        except (TypeError, ValueError):
            count = 0
        for index in range(1, count + 1):
            for item in safe_call(timeline, "GetItemListInTrack", track_type, index) or []:
                media = safe_call(item, "GetMediaPoolItem")
                if str(safe_call(media, "GetUniqueId") or "") == clip_id:
                    return media
    raise ValidationError("Clip sorgente non trovato nella timeline corrente")


def _public(payload: dict[str, Any], *, status: str | None = None,
            language: str | None = None, segments: list[dict[str, Any]] | None = None,
            segment_count: int = 0, start_segment: int = 0,
            action: str = "read_native_transcription21") -> dict[str, Any]:
    shown = segments or []
    return {
        "ok": True,
        "action": action,
        "job_id": payload["job_id"],
        "status": status or payload["status"],
        "clip_id": payload["binding"]["clip_id"],
        "language": language if language is not None else payload.get("language"),
        "segment_count": segment_count,
        "start_segment": start_segment,
        "returned_segments": len(shown),
        "has_more": start_segment + len(shown) < segment_count,
        "segments": shown,
        "transcription_replaced": False,
    }


def start_native_transcription21(project: Any, timeline: Any, config: Any, registry: Any,
                                 clip_id: str, use_speaker_detection: bool = True) -> dict[str, Any]:
    validate_review_target(project, timeline, config, registry)
    if not isinstance(use_speaker_detection, bool):
        raise ValidationError("use_speaker_detection deve essere booleano")
    media = _find_media(timeline, clip_id)
    binding = _binding(project, timeline, config, clip_id, use_speaker_detection, media)
    job_id = _job_id(binding)
    path = _manifest_path(config, job_id, create_root=True)
    if path.is_file():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValidationError(f"Manifest trascrizione nativa non leggibile: {exc}") from exc
        if payload.get("schema") != SCHEMA or payload.get("binding") != binding:
            raise ValidationError("Manifest trascrizione nativa non coerente")
        return _public(payload, action="start_native_transcription21")
    if not callable(getattr(media, "TranscribeAudio", None)) or not callable(getattr(media, "GetTranscription", None)):
        raise ValidationError("Resolve non espone la trascrizione nativa richiesta")
    baseline_fingerprint = _fingerprint(safe_call(media, "GetTranscription"))
    if safe_call(media, "TranscribeAudio", use_speaker_detection) is not True:
        raise RuntimeError("Avvio trascrizione nativa rifiutato da Resolve")
    created = _now()
    payload = {
        "schema": SCHEMA,
        "job_id": job_id,
        "status": "TRANSCRIBING",
        "binding": binding,
        "use_speaker_detection": use_speaker_detection,
        "baseline_transcription_sha256": baseline_fingerprint,
        "language": None,
        "created_at": created,
        "updated_at": created,
    }
    _atomic_json(path, payload)
    return _public(payload, action="start_native_transcription21")


def _segments(transcription: object) -> tuple[str | None, list[dict[str, Any]]]:
    if transcription is None or transcription == {}:
        return None, []
    if not isinstance(transcription, dict):
        raise ValidationError("Trascrizione nativa non valida")
    raw_segments = transcription.get("segments")
    if not isinstance(raw_segments, list):
        raise ValidationError("Segmenti trascrizione nativa non validi")
    cleaned: list[dict[str, Any]] = []
    for raw in raw_segments:
        if not isinstance(raw, dict) or not all(isinstance(raw.get(key), str) and raw.get(key)
                                               for key in ("start", "end", "text")):
            raise ValidationError("Segmento trascrizione nativa non valido")
        words = raw.get("words") or []
        if not isinstance(words, list):
            raise ValidationError("Parole trascrizione nativa non valide")
        public_words = []
        for word in words[:500]:
            if not isinstance(word, dict) or not all(isinstance(word.get(key), str)
                                                     for key in ("start", "end", "text")):
                raise ValidationError("Parola trascrizione nativa non valida")
            public_words.append({key: str(word[key])[:200] for key in ("start", "end", "text")})
        cleaned.append({
            "start": raw["start"], "end": raw["end"], "text": raw["text"][:2000],
            "speaker": raw.get("speaker") if isinstance(raw.get("speaker"), str) else None,
            "words": public_words,
        })
    language = transcription.get("language")
    return (language if isinstance(language, str) else None), cleaned


def _timed_out(created_at: object) -> bool:
    try:
        created = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        raise ValidationError("Timestamp job trascrizione nativa non valido") from None
    if created.tzinfo is None:
        raise ValidationError("Timestamp job trascrizione nativa senza timezone")
    return (datetime.now(timezone.utc) - created.astimezone(timezone.utc)).total_seconds() >= TRANSCRIPTION_TIMEOUT_SECONDS


def read_native_transcription21(project: Any, timeline: Any, config: Any, registry: Any,
                                job_id: str, start_segment: int = 0,
                                max_segments: int = 50) -> dict[str, Any]:
    validate_review_target(project, timeline, config, registry)
    if isinstance(start_segment, bool) or not isinstance(start_segment, int) or start_segment < 0:
        raise ValidationError("start_segment non valido")
    if isinstance(max_segments, bool) or not isinstance(max_segments, int) or not 1 <= max_segments <= 100:
        raise ValidationError("max_segments deve essere compreso tra 1 e 100")
    path = _manifest_path(config, job_id, create_root=False)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"Job trascrizione nativa non leggibile: {exc}") from exc
    binding = payload.get("binding", {})
    clip_id = str(binding.get("clip_id") or "")
    speaker_mode = payload.get("use_speaker_detection")
    if not isinstance(speaker_mode, bool):
        raise ValidationError("Job trascrizione nativa senza modalità speaker valida")
    media = _find_media(timeline, clip_id)
    expected = _binding(project, timeline, config, clip_id, speaker_mode, media)
    if (payload.get("schema") != SCHEMA or payload.get("job_id") != job_id
            or binding != expected or payload.get("baseline_transcription_sha256") is None):
        raise ValidationError("Job trascrizione nativa non coerente con la timeline")
    transcription = safe_call(media, "GetTranscription")
    current_fingerprint = _fingerprint(transcription)
    language, segments = _segments(transcription)
    fresh = current_fingerprint != payload["baseline_transcription_sha256"] and bool(segments)
    if fresh:
        status = "COMPLETED"
        shown = segments[start_segment:start_segment + max_segments]
        return _public(payload, status=status, language=language, segments=shown,
                       segment_count=len(segments), start_segment=start_segment)
    status = "TIMED_OUT" if _timed_out(payload.get("created_at")) else "TRANSCRIBING"
    return _public(payload, status=status, start_segment=start_segment)
