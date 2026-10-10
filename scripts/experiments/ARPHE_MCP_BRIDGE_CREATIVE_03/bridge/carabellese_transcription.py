from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid
from typing import Any

from .audio_provenance import media_fingerprint
from .config import CreativeConfig
from .longform_tools import allowed_media
from .safety import ValidationError, arphe_name
from .transcription_worker import ALLOWED_LANGUAGES, ALLOWED_MODELS, JOB_SCHEMA, _atomic_json


JOB_ID = re.compile(r"^carabellese_tx_[0-9a-f]{16}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
ACTIVE_OR_COMPLETE = frozenset({"QUEUED", "RUNNING", "COMPLETED"})
VALID_STATUSES = ACTIVE_OR_COMPLETE | {"INTERRUPTED"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _job_root(config: CreativeConfig) -> Path:
    return config.transcript_root / ".carabellese_jobs" / config.workstation_id


def _validate_options(model: object, language: object) -> None:
    if model not in ALLOWED_MODELS:
        raise ValidationError("Nome modello trascrizione non consentito")
    if language not in ALLOWED_LANGUAGES:
        raise ValidationError("Codice lingua trascrizione non consentito")


def _load_manifest(config: CreativeConfig, path: Path, expected_job_id: str | None = None) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"Manifest trascrizione non leggibile: {exc}") from exc
    required = {"schema", "job_id", "workstation_id", "status", "progress_percent", "source_path",
                "source_name", "source_fingerprint", "media_root", "output_path", "transcript_root",
                "model", "language", "created_at", "updated_at", "error"}
    if not isinstance(payload, dict) or required - set(payload) or payload.get("schema") != JOB_SCHEMA:
        raise ValidationError("Manifest trascrizione Carabellese non valido")
    job_id = payload.get("job_id")
    if not isinstance(job_id, str) or not JOB_ID.fullmatch(job_id) or (
            expected_job_id is not None and job_id != expected_job_id):
        raise ValidationError("Identità job trascrizione non valida")
    if payload.get("workstation_id") != config.workstation_id:
        raise ValidationError("Manifest trascrizione appartenente a un altro workstation")
    if payload.get("status") not in VALID_STATUSES:
        raise ValidationError("Stato job trascrizione non valido")
    _validate_options(payload.get("model"), payload.get("language"))
    try:
        source = Path(payload["source_path"]).resolve(strict=True)
        output = Path(payload["output_path"]).resolve()
        transcript_root = config.transcript_root.resolve(strict=True)
    except (OSError, TypeError) as exc:
        raise ValidationError(f"Path job trascrizione non valido: {exc}") from exc
    if not source.is_file() or not any(source.is_relative_to(root.resolve(strict=True))
                                       for root in config.media_roots):
        raise ValidationError("Sorgente job trascrizione fuori dalle root autorizzate")
    if output.suffix.lower() != ".json" or not output.is_relative_to(transcript_root):
        raise ValidationError("Output job trascrizione fuori dalla root autorizzata")
    return payload


def _public(payload: dict[str, Any]) -> dict[str, Any]:
    status = str(payload["status"])
    return {"ok": status != "INTERRUPTED", "action": "get_carabellese_transcription_job",
            "job_id": payload["job_id"], "status": status,
            "progress_percent": payload.get("progress_percent", 0),
            "source_name": payload["source_name"], "output_name": Path(payload["output_path"]).name,
            "model": payload["model"], "language": payload["language"],
            "resumable": status == "INTERRUPTED"}


def _launch(manifest_path: Path) -> int:
    flags = subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS if os.name == "nt" else 0
    process = subprocess.Popen(
        [sys.executable, "-m", "bridge.transcription_worker", "--job", str(manifest_path.resolve())],
        cwd=str(Path(__file__).resolve().parents[1]), stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
    return int(process.pid)


def _pid_is_running(value: object) -> bool:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return False
    try:
        os.kill(value, 0)
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _matching_manifest(config: CreativeConfig, source_fingerprint: str, model: str,
                       language: str) -> tuple[Path, dict[str, Any]] | None:
    root = _job_root(config)
    if not root.is_dir():
        return None
    matches = []
    for path in sorted(root.glob("carabellese_tx_*.json")):
        payload = _load_manifest(config, path)
        if (payload["source_fingerprint"] == source_fingerprint and payload["model"] == model
                and payload["language"] == language):
            matches.append((path, payload))
    if len(matches) > 1:
        raise ValidationError("Più job trascrizione equivalenti: registry incoerente")
    return matches[0] if matches else None


def start_carabellese_transcription(config: CreativeConfig, media_path: str,
                                    expected_source_fingerprint: str, model: str = "small",
                                    language: str = "it") -> dict[str, object]:
    if not config.flags.get("CAP_CARABELLESE_CLEANUP"):
        raise RuntimeError("CAP_CARABELLESE_CLEANUP non configurata")
    _validate_options(model, language)
    if not isinstance(expected_source_fingerprint, str) or not SHA256.fullmatch(expected_source_fingerprint):
        raise ValidationError("expected_source_fingerprint non valido")
    selected = allowed_media(media_path, config)
    actual_fingerprint = media_fingerprint(selected)
    if actual_fingerprint != expected_source_fingerprint:
        raise ValidationError("Il fingerprint del media non coincide con quello atteso")
    config.transcript_root.mkdir(parents=True, exist_ok=True)
    root = _job_root(config)
    root.mkdir(parents=True, exist_ok=True)
    existing = _matching_manifest(config, actual_fingerprint, model, language)
    if existing is not None:
        manifest_path, payload = existing
        if payload["status"] in {"QUEUED", "COMPLETED"}:
            return _public(payload)
        if payload["status"] == "RUNNING" and _pid_is_running(payload.get("pid")):
            return _public(payload)
        payload.update(status="QUEUED", updated_at=_now(), error=None)
        _atomic_json(manifest_path, payload)
        try:
            _launch(manifest_path)
        except OSError as exc:
            payload.update(status="INTERRUPTED", error=type(exc).__name__)
            _atomic_json(manifest_path, payload)
            raise RuntimeError("Avvio worker trascrizione fallito") from exc
        return _public(payload)

    job_id = "carabellese_tx_" + uuid.uuid4().hex[:16]
    label = arphe_name(selected.stem, "CARABELLESE").removeprefix("ARPHE_")
    output = (config.transcript_root / config.workstation_id /
              f"ARPHE_CARABELLESE_{label}_{job_id[-8:]}.transcript.json").resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    media_root = next(root_path.resolve(strict=True) for root_path in config.media_roots
                      if selected.is_relative_to(root_path.resolve(strict=True)))
    manifest_path = root / f"{job_id}.json"
    created = _now()
    payload: dict[str, Any] = {
        "schema": JOB_SCHEMA, "job_id": job_id, "workstation_id": config.workstation_id,
        "status": "QUEUED", "progress_percent": 0.0, "source_path": str(selected),
        "source_name": selected.name, "source_fingerprint": actual_fingerprint,
        "media_root": str(media_root), "output_path": str(output),
        "transcript_root": str(config.transcript_root.resolve()), "model": model,
        "language": language, "created_at": created, "updated_at": created, "error": None,
    }
    _atomic_json(manifest_path, payload)
    try:
        _launch(manifest_path)
    except OSError as exc:
        payload.update(status="INTERRUPTED", error=type(exc).__name__)
        _atomic_json(manifest_path, payload)
        raise RuntimeError("Avvio worker trascrizione fallito") from exc
    return _public(payload)


def get_carabellese_transcription_job(config: CreativeConfig, job_id: str) -> dict[str, object]:
    if not isinstance(job_id, str) or not JOB_ID.fullmatch(job_id):
        raise ValidationError("job_id trascrizione Carabellese non valido")
    path = _job_root(config) / f"{job_id}.json"
    if not path.is_file():
        raise ValidationError("Job trascrizione Carabellese non trovato")
    return _public(_load_manifest(config, path, job_id))
