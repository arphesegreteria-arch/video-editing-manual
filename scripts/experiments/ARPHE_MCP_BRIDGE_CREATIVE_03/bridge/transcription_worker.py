from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Callable


SCHEMA = "ARPHE_TRANSCRIPT_V1"
JOB_SCHEMA = "ARPHE_CARABELLESE_TRANSCRIPTION_JOB_V1"
MEDIA_EXTENSIONS = {".mp4", ".mov", ".mxf", ".mkv", ".m4v", ".wav", ".mp3", ".m4a"}
ALLOWED_MODELS = frozenset({"tiny", "base", "small", "medium"})
ALLOWED_LANGUAGES = frozenset({"it"})


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _duration(path: Path) -> float:
    import av
    with av.open(str(path)) as container:
        return float(container.duration / av.time_base)


def _word_payload(word: Any) -> dict[str, Any]:
    return {"start": round(float(word.start), 3), "end": round(float(word.end), 3),
            "word": str(word.word), "probability": round(float(word.probability), 4)}


def _new_payload(source: Path, fingerprint: str, duration: float, model_name: str,
                 language: str) -> dict[str, Any]:
    return {
        "schema": SCHEMA, "status": "running",
        "source": {"name": source.name, "path": str(source), "size_bytes": source.stat().st_size,
                   "fingerprint": fingerprint, "duration_seconds": round(duration, 3)},
        "transcription": {"engine": "faster-whisper", "model": model_name, "device": "cpu",
                          "compute_type": "int8", "requested_language": language,
                          "detected_language": None, "language_probability": None,
                          "word_timestamps": True},
        "segments": [], "created_at": _now(), "updated_at": None,
    }


def _load_checkpoint(output: Path, source: Path, fingerprint: str, model_name: str,
                     language: str) -> dict[str, Any] | None:
    if not output.is_file():
        return None
    try:
        payload = json.loads(output.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Checkpoint transcript non leggibile: {exc}") from exc
    source_data = payload.get("source") if isinstance(payload, dict) else None
    transcription = payload.get("transcription") if isinstance(payload, dict) else None
    if (not isinstance(payload, dict) or payload.get("schema") != SCHEMA
            or not isinstance(source_data, dict) or source_data.get("fingerprint") != fingerprint
            or source_data.get("path") != str(source) or not isinstance(transcription, dict)
            or transcription.get("model") != model_name
            or transcription.get("requested_language") != language
            or not isinstance(payload.get("segments"), list)):
        raise ValueError("Checkpoint transcript associato a parametri o sorgente differenti")
    return payload


def transcribe_checkpointed(
    source: Path, output: Path, model_name: str, language: str, *,
    expected_source_fingerprint: str,
    model_factory: Callable[..., Any] | None = None,
    duration_reader: Callable[[Path], float] = _duration,
    progress_callback: Callable[[float], None] | None = None,
) -> None:
    source = source.expanduser().resolve(strict=True)
    output = output.expanduser().resolve()
    if source.suffix.lower() not in MEDIA_EXTENSIONS:
        raise ValueError("Formato sorgente non consentito")
    actual_fingerprint = file_sha256(source)
    if actual_fingerprint != expected_source_fingerprint:
        raise ValueError("Fingerprint sorgente diverso da quello atteso")
    duration = float(duration_reader(source))
    if duration <= 0:
        raise ValueError("Durata sorgente non valida")
    payload = _load_checkpoint(output, source, actual_fingerprint, model_name, language)
    if payload is None:
        payload = _new_payload(source, actual_fingerprint, duration, model_name, language)
    elif payload.get("status") == "complete":
        return
    else:
        payload["status"] = "running"
        payload.pop("summary", None)
    _atomic_json(output, payload)

    if model_factory is None:
        from faster_whisper import WhisperModel
        model_factory = WhisperModel
    model = model_factory(model_name, device="cpu", compute_type="int8")
    kwargs: dict[str, Any] = {"language": language, "beam_size": 5, "word_timestamps": True,
                              "vad_filter": True, "condition_on_previous_text": True}
    segments_so_far = payload["segments"]
    resume_second = float(segments_so_far[-1]["end"]) if segments_so_far else 0.0
    if resume_second > 0:
        kwargs["clip_timestamps"] = str(resume_second)
    segments, info = model.transcribe(str(source), **kwargs)
    payload["transcription"]["detected_language"] = info.language
    payload["transcription"]["language_probability"] = round(float(info.language_probability), 4)
    for index, segment in enumerate(segments):
        segments_so_far.append({"id": len(segments_so_far), "start": round(float(segment.start), 3),
                                "end": round(float(segment.end), 3), "text": str(segment.text).strip(),
                                "words": [_word_payload(word) for word in (segment.words or [])]})
        if index % 20 == 0:
            payload["updated_at"] = _now()
            _atomic_json(output, payload)
            progress = min(99.9, 100.0 * float(segment.end) / duration)
            if progress_callback is not None:
                progress_callback(progress)
    payload["status"] = "complete"
    payload["updated_at"] = _now()
    payload["summary"] = {"segment_count": len(segments_so_far),
                          "word_count": sum(len(segment["words"]) for segment in segments_so_far)}
    _atomic_json(output, payload)
    if progress_callback is not None:
        progress_callback(100.0)


def _load_worker_job(job_path: Path) -> dict[str, Any]:
    payload = json.loads(job_path.read_text(encoding="utf-8-sig"))
    required = {"schema", "job_id", "workstation_id", "status", "source_path", "source_name",
                "source_fingerprint", "media_root", "output_path", "transcript_root", "model", "language"}
    if not isinstance(payload, dict) or required - set(payload) or payload.get("schema") != JOB_SCHEMA:
        raise ValueError("Manifest trascrizione Carabellese non valido")
    if payload.get("model") not in ALLOWED_MODELS:
        raise ValueError("Nome modello worker non consentito")
    if payload.get("language") not in ALLOWED_LANGUAGES:
        raise ValueError("Codice lingua worker non consentito")
    source = Path(payload["source_path"]).resolve(strict=True)
    media_root = Path(payload["media_root"]).resolve(strict=True)
    output = Path(payload["output_path"]).resolve()
    transcript_root = Path(payload["transcript_root"]).resolve(strict=True)
    if not source.is_file() or not source.is_relative_to(media_root):
        raise ValueError("Sorgente worker fuori dalla root autorizzata")
    if output.suffix.lower() != ".json" or not output.is_relative_to(transcript_root):
        raise ValueError("Output worker fuori dalla root autorizzata")
    return payload


def run_job(job_path: Path) -> None:
    job_path = job_path.expanduser().resolve(strict=True)
    payload = _load_worker_job(job_path)
    payload.update(status="RUNNING", updated_at=_now(), error=None, pid=os.getpid())
    _atomic_json(job_path, payload)

    def progress(value: float) -> None:
        current = _load_worker_job(job_path)
        current.update(status="RUNNING", progress_percent=round(value, 1), updated_at=_now(),
                       pid=os.getpid())
        _atomic_json(job_path, current)

    try:
        transcribe_checkpointed(Path(payload["source_path"]), Path(payload["output_path"]),
                                str(payload["model"]), str(payload["language"]),
                                expected_source_fingerprint=str(payload["source_fingerprint"]),
                                progress_callback=progress)
        payload = _load_worker_job(job_path)
        payload.update(status="COMPLETED", progress_percent=100.0,
                       transcript_fingerprint=file_sha256(Path(payload["output_path"])),
                       updated_at=_now(), error=None)
        _atomic_json(job_path, payload)
    except BaseException as exc:
        payload = _load_worker_job(job_path)
        payload.update(status="INTERRUPTED", updated_at=_now(), error=type(exc).__name__)
        _atomic_json(job_path, payload)
        raise


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job", required=True, type=Path)
    run_job(parser.parse_args().job)


if __name__ == "__main__":
    main()
