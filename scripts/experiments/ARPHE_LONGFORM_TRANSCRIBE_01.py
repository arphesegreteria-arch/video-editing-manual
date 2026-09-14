"""Local, checkpointed long-form transcription to ARPHE_TRANSCRIPT_V1 JSON."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any

import av
from faster_whisper import WhisperModel


SCHEMA = "ARPHE_TRANSCRIPT_V1"


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _fingerprint(path: Path) -> str:
    digest = hashlib.sha256()
    size = path.stat().st_size
    with path.open("rb") as handle:
        digest.update(handle.read(1024 * 1024))
        if size > 1024 * 1024:
            handle.seek(max(0, size - 1024 * 1024))
            digest.update(handle.read(1024 * 1024))
    digest.update(str(size).encode("ascii"))
    return digest.hexdigest()


def _duration(path: Path) -> float:
    with av.open(str(path)) as container:
        return float(container.duration / av.time_base)


def _word_payload(word: Any) -> dict[str, Any]:
    return {
        "start": round(float(word.start), 3),
        "end": round(float(word.end), 3),
        "word": str(word.word),
        "probability": round(float(word.probability), 4),
    }


def transcribe(source: Path, output: Path, model_name: str, language: str) -> None:
    source = source.resolve(strict=True)
    if source.suffix.lower() not in {".mp4", ".mov", ".mkv", ".m4v", ".wav", ".mp3", ".m4a"}:
        raise ValueError("Formato sorgente non consentito")

    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "status": "running",
        "source": {
            "name": source.name,
            "path": str(source),
            "size_bytes": source.stat().st_size,
            "fingerprint": _fingerprint(source),
            "duration_seconds": round(_duration(source), 3),
        },
        "transcription": {
            "engine": "faster-whisper",
            "model": model_name,
            "device": "cpu",
            "compute_type": "int8",
            "requested_language": language,
            "detected_language": None,
            "language_probability": None,
            "word_timestamps": True,
        },
        "segments": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": None,
    }
    _atomic_json(output, payload)

    model = WhisperModel(model_name, device="cpu", compute_type="int8")
    segments, info = model.transcribe(
        str(source), language=language, beam_size=5, word_timestamps=True,
        vad_filter=True, condition_on_previous_text=True,
    )
    payload["transcription"]["detected_language"] = info.language
    payload["transcription"]["language_probability"] = round(float(info.language_probability), 4)

    for index, segment in enumerate(segments):
        payload["segments"].append({
            "id": int(segment.id),
            "start": round(float(segment.start), 3),
            "end": round(float(segment.end), 3),
            "text": str(segment.text).strip(),
            "words": [_word_payload(word) for word in (segment.words or [])],
        })
        if index % 20 == 0:
            payload["updated_at"] = datetime.now(timezone.utc).isoformat()
            _atomic_json(output, payload)
            progress = 100.0 * float(segment.end) / payload["source"]["duration_seconds"]
            print(f"progress={progress:.1f}% segment={segment.id} end={segment.end:.1f}s", flush=True)

    payload["status"] = "complete"
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    payload["summary"] = {
        "segment_count": len(payload["segments"]),
        "word_count": sum(len(segment["words"]) for segment in payload["segments"]),
    }
    _atomic_json(output, payload)
    print(f"complete output={output} segments={payload['summary']['segment_count']} "
          f"words={payload['summary']['word_count']}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--model", default="small")
    parser.add_argument("--language", default="it")
    args = parser.parse_args()
    transcribe(args.source, args.output, args.model, args.language)


if __name__ == "__main__":
    main()
